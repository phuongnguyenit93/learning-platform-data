# Duplicate entry và xung đột PRIMARY/UNIQUE

Bài học này thuộc module **DATABASE_MYSQL**. Lỗi **Duplicate entry** xuất hiện khi một thao tác ghi tạo ra giá trị vi phạm khóa chính (PRIMARY KEY) hoặc chỉ mục duy nhất (UNIQUE). Trong MySQL, lỗi thường có mã **1062** và SQLSTATE **23000**. Lỗi có thể do dữ liệu đã tồn tại, do hai request đồng thời cùng tạo một bản ghi, do quy tắc so sánh của collation, do khóa ghép hoặc do ứng dụng gửi lại một thao tác đã thành công trước đó.

Cách xử lý đúng phụ thuộc vào ý nghĩa nghiệp vụ. Có trường hợp đây là xung đột cần trả về cho người dùng; có trường hợp là retry trùng lặp cần được xử lý idempotent; có trường hợp dữ liệu cũ đã vi phạm quy tắc mới và cần làm sạch trước khi thêm UNIQUE index. Không nên coi mọi lỗi 1062 là lỗi hệ thống, cũng không nên bỏ qua tất cả lỗi duplicate bằng INSERT IGNORE mà chưa xác định tác động.

## 1. PRIMARY KEY và UNIQUE bảo vệ điều gì?

Khóa chính và unique index đều bảo đảm tính duy nhất, nhưng có vai trò khác nhau.

- **PRIMARY KEY:** định danh duy nhất mỗi hàng trong bảng. Mỗi bảng chỉ có một primary key; các cột thuộc khóa chính không được NULL.
- **UNIQUE:** bảo đảm không có hai hàng cùng giá trị theo quy tắc so sánh của index. Một bảng có thể có nhiều unique index.
- **Unique composite key:** bảo đảm tổ hợp giá trị của các cột là duy nhất, không nhất thiết từng cột riêng lẻ phải duy nhất.

Ví dụ:

~~~sql
CREATE TABLE users (
    user_id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(255) NOT NULL,
    external_ref VARCHAR(80) NULL,
    display_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_tenant_email (tenant_id, email),
    UNIQUE KEY uq_users_external_ref (external_ref)
) ENGINE=InnoDB;
~~~

Trong bảng này:

- user_id là định danh duy nhất của mỗi hàng.
- Một tenant không thể có hai hàng cùng email theo collation của cột.
- external_ref phải duy nhất khi có giá trị khác NULL; MySQL cho phép nhiều NULL trong unique index.
- Hai hàng có cùng email nhưng thuộc tenant khác nhau có thể hợp lệ vì unique key là tổ hợp (tenant_id, email).

Nếu ứng dụng cần email duy nhất trên toàn hệ thống, unique key phải được thiết kế trên email thay vì cặp tenant/email. Ràng buộc phải phản ánh chính xác phạm vi duy nhất của nghiệp vụ.

## 2. Nhận diện lỗi Duplicate entry

Một câu lệnh chèn trùng primary key:

~~~sql
CREATE TABLE account_demo (
    account_id BIGINT PRIMARY KEY,
    account_name VARCHAR(100) NOT NULL
);

INSERT INTO account_demo (account_id, account_name)
VALUES (10, 'An');

INSERT INTO account_demo (account_id, account_name)
VALUES (10, 'Binh');
~~~

Câu lệnh thứ hai bị từ chối vì account_id = 10 đã tồn tại. MySQL thường trả lỗi dạng:

~~~text
ERROR 1062 (23000): Duplicate entry '10' for key 'account_demo.PRIMARY'
~~~

Tạo unique index trên email cũng có thể gây lỗi:

~~~sql
CREATE TABLE account_email_demo (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_account_email (email)
);

INSERT INTO account_email_demo VALUES (1, 'user@example.com');
INSERT INTO account_email_demo VALUES (2, 'user@example.com');
~~~

Lỗi có thể xuất hiện ở các thao tác:

- INSERT tạo hàng có khóa đã tồn tại.
- UPDATE thay giá trị khóa thành giá trị của một hàng khác.
- INSERT ... ON DUPLICATE KEY UPDATE kích hoạt nhánh cập nhật khi có xung đột.
- Thêm unique index vào bảng đã có dữ liệu trùng.
- Import hoặc replication áp dụng một sự kiện tạo ra khóa trùng ở đích.

Ví dụ UPDATE tạo ra xung đột với một hàng khác:

~~~sql
UPDATE users
SET email = 'taken@example.com'
WHERE user_id = 102;
~~~

Nếu một hàng khác trong cùng tenant đã có email taken@example.com, thao tác cập nhật sẽ bị từ chối bởi unique key (tenant_id, email).

Mã 1062 cho biết một unique constraint đã bị vi phạm. Nó không tự cho biết nguyên nhân nghiệp vụ là request lặp, người dùng nhập trùng, dữ liệu migration lỗi hay một cuộc đua đồng thời.

### 2.1. Phân biệt với các lỗi khóa khác

| Lỗi | Ý nghĩa |
|---|---|
| 1062 / SQLSTATE 23000 | Duplicate entry: vi phạm PRIMARY hoặc UNIQUE |
| 1452 | Không thể thêm/cập nhật hàng con vì thiếu hàng cha được tham chiếu (foreign key) |
| 1451 | Không thể xóa/cập nhật hàng cha vì còn hàng con tham chiếu |
| 1213 | Deadlock: InnoDB chọn transaction làm nạn nhân để giải phóng deadlock |
| 1205 | Lock wait timeout |
| 1048 | Cột không được NULL nhưng nhận NULL |

Không xử lý lỗi 1213, 1205 hoặc lỗi foreign key như lỗi duplicate. Mỗi loại có nguyên nhân và chiến lược khắc phục riêng.

## 3. Xác định unique key nào bị vi phạm

Bắt đầu bằng việc đọc định nghĩa bảng và các index:

~~~sql
SHOW CREATE TABLE users\G
SHOW INDEX FROM users;
~~~

Trong kết quả SHOW INDEX, cột Non_unique = 0 cho biết index là duy nhất. Key_name là tên index; Seq_in_index cho biết thứ tự cột trong index; Column_name cho biết cột tương ứng.

Có thể truy vấn metadata:

~~~sql
SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX,
       COLUMN_NAME, SUB_PART, COLLATION
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

Với unique index ghép, phải xem đủ các cột theo đúng thứ tự. Không kết luận một cột riêng lẻ là duy nhất chỉ vì nó nằm trong unique composite index.

Ví dụ, unique index (tenant_id, email) cho phép:

~~~sql
INSERT INTO users
    (user_id, tenant_id, email, external_ref, display_name)
VALUES
    (101, 1, 'same@example.com', NULL, 'User A'),
    (102, 2, 'same@example.com', NULL, 'User B');
~~~

Hai hàng trên không xung đột vì tenant_id khác nhau. Nếu chèn một hàng mới có cả tenant_id = 1 và email giống hàng đầu tiên, MySQL sẽ báo duplicate.

### 3.1. Tìm các nhóm dữ liệu trùng

Với unique key một cột:

~~~sql
SELECT email, COUNT(*) AS duplicate_count
FROM users
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Với unique key ghép:

~~~sql
SELECT tenant_id, email, COUNT(*) AS duplicate_count
FROM users
GROUP BY tenant_id, email
HAVING COUNT(*) > 1;
~~~

GROUP BY áp dụng quy tắc so sánh của các biểu thức/cột. Nếu cột dùng collation không phân biệt hoa thường, các giá trị như User@example.com và user@example.com có thể được gom vào cùng nhóm. Đây là điều cần kiểm tra khi điều tra duplicate mà chuỗi nhìn bằng mắt có vẻ khác nhau.

Với cột nullable, nhóm NULL có thể xuất hiện trong kết quả GROUP BY, nhưng điều đó không có nghĩa unique index cấm nhiều NULL. Quy tắc unique index của MySQL cho phép nhiều NULL; hãy diễn giải kết quả theo định nghĩa index thực tế.

### 3.2. Tìm hàng xung đột cụ thể

Nếu ứng dụng gửi email user@example.com, dùng điều kiện tương đương với unique key:

~~~sql
SELECT user_id, tenant_id, email, external_ref
FROM users
WHERE tenant_id = 1
  AND email = 'user@example.com';
~~~

Với unique key ghép, phải kiểm tra toàn bộ thành phần. Với collation không phân biệt hoa thường, phép so sánh có thể tìm được giá trị khác kiểu chữ nhưng vẫn được xem là trùng theo index.

Không chỉ dựa vào phần duplicate value trong thông báo lỗi. Với index nhiều cột hoặc chuỗi được chuyển đổi/chuẩn hóa, thông báo không phải lúc nào cũng đủ để tái tạo chính xác quy tắc xung đột.

## 4. Collation và chuẩn hóa dữ liệu

Unique index tuân theo quy tắc so sánh của collation và kiểu dữ liệu. Vì vậy, hai chuỗi có cách viết khác nhau vẫn có thể bị xem là bằng nhau.

Kiểm tra charset và collation:

~~~sql
SHOW FULL COLUMNS FROM users;
~~~

Hoặc:

~~~sql
SELECT COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users';
~~~

Một collation có hậu tố _ci thường không phân biệt hoa thường. Hậu tố _ai thường không phân biệt dấu (accent). Một số collation có quy tắc xử lý dấu cách cuối chuỗi khác nhau; cần kiểm tra đúng collation đang dùng, không suy luận chỉ từ chuỗi hiển thị.

Ví dụ, nếu email được so sánh theo collation không phân biệt chữ hoa/thường, hai giá trị sau có thể xung đột:

~~~sql
INSERT INTO users (user_id, tenant_id, email, display_name)
VALUES (201, 1, 'Alice@example.com', 'Alice');

INSERT INTO users (user_id, tenant_id, email, display_name)
VALUES (202, 1, 'alice@example.com', 'alice');
~~~

Nếu quy tắc nghiệp vụ xem hai địa chỉ này là cùng một định danh, hành vi đó là phù hợp. Nếu nghiệp vụ cần phân biệt, phải chọn kiểu so sánh/collation có chủ đích và kiểm thử các trường hợp chữ hoa, chữ thường, dấu và dấu cách.

### 4.1. Chuẩn hóa dữ liệu trước khi tạo unique key

Có thể cần chuẩn hóa email, mã bên ngoài hoặc số điện thoại trước khi lưu. Ví dụ, ứng dụng có thể loại bỏ khoảng trắng ở hai đầu và áp dụng quy tắc chữ hoa/thường đã thống nhất.

Không nên tự động LOWER() mọi trường dữ liệu mà không xét quy tắc nghiệp vụ. Đặc biệt, email, tên người dùng và mã định danh có thể có chính sách chuẩn hóa riêng.

Một cách triển khai là lưu giá trị gốc và cột chuẩn hóa:

~~~sql
CREATE TABLE customer_contacts (
    contact_id BIGINT PRIMARY KEY,
    email_original VARCHAR(255) NOT NULL,
    email_normalized VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_email_normalized (email_normalized)
);
~~~

Ứng dụng chịu trách nhiệm tạo email_normalized theo một hàm chuẩn hóa được thống nhất. Nếu nhiều hệ thống cùng ghi, cần bảo đảm mọi writer dùng cùng một quy tắc. Có thể cân nhắc generated column nếu biểu thức được MySQL hỗ trợ và có tính xác định phù hợp.

Trước khi đổi quy tắc chuẩn hóa, cần tìm các giá trị hiện tại sẽ trở thành trùng. Không thể chỉ thêm unique index rồi hy vọng MySQL tự chọn hàng giữ lại.

## 5. Vì sao kiểm tra trước khi INSERT vẫn có thể bị duplicate?

Một lỗi thiết kế phổ biến là kiểm tra bằng SELECT trước khi chèn:

~~~sql
SELECT user_id
FROM users
WHERE tenant_id = 1
  AND email = 'new@example.com';

-- Nếu không thấy hàng, ứng dụng thực hiện INSERT
INSERT INTO users (user_id, tenant_id, email, display_name)
VALUES (301, 1, 'new@example.com', 'New User');
~~~

Trong môi trường có nhiều request đồng thời, hai transaction có thể cùng đọc và đều không thấy hàng. Sau đó cả hai cùng chèn. Unique index chỉ cho phép một transaction thành công; transaction còn lại nhận lỗi duplicate.

~~~text
Request A                    Request B
---------                    ---------
SELECT: chưa có hàng         SELECT: chưa có hàng
INSERT email X               INSERT email X
COMMIT thành công            nhận duplicate 1062
~~~

Đây là race condition giữa bước kiểm tra và bước ghi. Tăng isolation level hoặc thêm một lần SELECT trước INSERT không thay thế được unique constraint. Unique index trong MySQL/InnoDB mới là lớp bảo vệ cuối cùng cho tính duy nhất.

### 5.1. Cách xử lý đúng

- Giữ PRIMARY/UNIQUE constraint trong database.
- Thực hiện thao tác ghi trực tiếp theo ý nghĩa nghiệp vụ.
- Bắt lỗi 1062 và chuyển thành kết quả nghiệp vụ phù hợp, chẳng hạn “email đã được sử dụng”.
- Nếu đây là request lặp có chủ đích, dùng idempotency key hoặc upsert có ngữ nghĩa rõ.
- Nếu cần đọc lại hàng đã tồn tại, thực hiện sau khi xử lý conflict và trong transaction phù hợp.

Không coi kết quả SELECT trước INSERT là bằng chứng rằng thao tác INSERT chắc chắn thành công.

## 6. Xử lý Duplicate entry trong Java/JDBC

Với JDBC, SQLException cung cấp SQLState và vendor error code. Với lỗi duplicate phổ biến của MySQL:

- Vendor code: 1062.
- SQLState: 23000 (integrity constraint violation).

Ví dụ:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO users (user_id, tenant_id, email, display_name) "
      + "VALUES (?, ?, ?, ?)")) {

    ps.setLong(1, userId);
    ps.setLong(2, tenantId);
    ps.setString(3, email);
    ps.setString(4, displayName);
    ps.executeUpdate();

} catch (SQLException e) {
    if (e.getErrorCode() == 1062) {
        throw new EmailAlreadyUsedException(email, e);
    }
    throw e;
}
~~~

Ví dụ này giả định unique conflict liên quan email. Trong thực tế, bảng có thể có nhiều unique index; không nên mặc định mọi lỗi 1062 đều là email đã tồn tại. Cần xác định constraint bị vi phạm theo ngữ cảnh câu lệnh hoặc metadata lỗi được driver cung cấp, rồi ánh xạ đúng lỗi nghiệp vụ.

Không dùng cách phân tích chuỗi thông báo lỗi làm cơ chế duy nhất để quyết định logic. Nội dung message có thể thay đổi theo phiên bản, tên schema, bảng và index.

### 6.1. Spring và Hibernate

Với Spring, lỗi có thể được chuyển thành các exception thuộc hệ thống DataAccessException, ví dụ DuplicateKeyException hoặc một dạng DataIntegrityViolationException tùy đường thực thi và translator.

Ví dụ xử lý ở service/controller:

~~~java
try {
    userRepository.save(user);
    userRepository.flush();
} catch (DataIntegrityViolationException ex) {
    if (isDuplicateKey(ex)) {
        throw new EmailAlreadyRegisteredException(user.getEmail(), ex);
    }
    throw ex;
}
~~~

save() có thể chưa gửi SQL ngay vì Hibernate trì hoãn flush đến cuối transaction. Gọi flush() trong phạm vi cần bắt lỗi giúp phát hiện sớm hơn, nhưng không làm transaction đã thất bại có thể tiếp tục an toàn. Sau lỗi constraint, transaction thường phải rollback; không tiếp tục dùng persistence context như thể thao tác đã thành công.

Hàm isDuplicateKey cần kiểm tra cause chain và mã lỗi của JDBC driver một cách cụ thể. Đừng chỉ bắt mọi DataIntegrityViolationException rồi trả về “đã tồn tại”, vì exception này còn có thể đại diện cho lỗi NOT NULL, foreign key hoặc các constraint khác.

## 7. Chọn INSERT, INSERT IGNORE hay ON DUPLICATE KEY UPDATE

Ba dạng câu lệnh có hành vi khác nhau. Chọn theo nghiệp vụ, không chỉ theo mong muốn tránh exception.

### 7.1. INSERT thông thường

~~~sql
INSERT INTO users (user_id, tenant_id, email, display_name)
VALUES (401, 1, 'new@example.com', 'New User');
~~~

Nếu vi phạm unique key, statement thất bại. Đây là lựa chọn phù hợp khi duplicate thực sự là conflict cần được báo cho caller.

### 7.2. INSERT IGNORE

~~~sql
INSERT IGNORE INTO users (user_id, tenant_id, email, display_name)
VALUES (401, 1, 'new@example.com', 'New User');
~~~

Với duplicate key, MySQL có thể bỏ qua hàng xung đột và phát warning thay vì dừng bằng lỗi. Tuy nhiên, IGNORE còn có thể biến một số lỗi dữ liệu khác thành warning hoặc điều chỉnh giá trị tùy tình huống. Điều đó có thể khiến dữ liệu không hợp lệ được chấp nhận theo cách khó nhận biết.

Nếu dùng, cần kiểm tra ROW_COUNT(), warning và số hàng thực tế được chèn. Không dùng INSERT IGNORE như cách chung để che lỗi.

### 7.3. INSERT ... ON DUPLICATE KEY UPDATE

Dùng khi nghiệp vụ xác định rõ phải cập nhật hàng hiện có nếu xung đột một unique key:

~~~sql
INSERT INTO inventory (product_id, quantity)
VALUES (501, 5)
ON DUPLICATE KEY UPDATE
    quantity = quantity + 5;
~~~

Nếu product_id = 501 chưa có, MySQL chèn hàng mới với quantity bằng 5. Nếu đã có, MySQL tăng quantity thêm 5.

Câu lệnh này là thao tác nguyên tử tại database và thường hữu ích cho counter hoặc tổng hợp có quy tắc cộng dồn. Nhưng cần kiểm tra mọi unique index trên bảng: bất kỳ xung đột PRIMARY/UNIQUE nào cũng có thể kích hoạt nhánh UPDATE. Nếu bảng có nhiều unique key với các hàng khác nhau cùng khớp, kết quả có thể không tương ứng với định danh mà ứng dụng dự định cập nhật. Thiết kế upsert an toàn nên tránh các unique key phụ gây mơ hồ hoặc bảo đảm mọi xung đột đều trỏ tới cùng một hàng nghiệp vụ.

Với MySQL 8.0.19 trở lên, có cú pháp row alias để tham chiếu hàng mới trong nhánh UPDATE. Cần kiểm tra phiên bản trước khi dùng; VALUES(column) trong nhánh update đã bị deprecated từ MySQL 8.0.20. Không sao chép cú pháp mới vào hệ thống cần tương thích phiên bản cũ mà chưa kiểm tra.

### 7.4. REPLACE INTO không giống UPDATE

~~~sql
REPLACE INTO users (user_id, tenant_id, email, display_name)
VALUES (401, 1, 'new@example.com', 'New Name');
~~~

REPLACE có thể xóa hàng xung đột rồi chèn hàng mới. Nếu xung đột với unique index khác, hành vi có thể ảnh hưởng đến nhiều hàng. Việc xóa rồi chèn có thể kích hoạt trigger, foreign key cascade, thay đổi auto-increment và làm mất giá trị ở các cột không được cung cấp.

Không dùng REPLACE chỉ vì tên nghe giống “thay thế một vài cột”. Nếu mục tiêu là cập nhật hàng hiện có, UPDATE hoặc ON DUPLICATE KEY UPDATE thường diễn đạt đúng hơn.

## 8. Thiết kế idempotency để xử lý request gửi lại

Duplicate entry thường xuất hiện khi client gửi lại request do timeout, mất kết nối hoặc không nhận được phản hồi dù transaction đã commit. Nếu ứng dụng tạo đơn hàng, thanh toán hoặc ghi sự kiện, retry có thể tạo bản ghi trùng.

Một cách phổ biến là dùng idempotency key duy nhất cho một yêu cầu nghiệp vụ:

~~~sql
CREATE TABLE payment_requests (
    request_key VARCHAR(100) NOT NULL,
    payment_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (request_key),
    UNIQUE KEY uq_payment_id (payment_id)
);
~~~

Ứng dụng gửi cùng request_key khi retry cùng một yêu cầu. Database bảo đảm chỉ có một hàng cho key đó. Khi nhận duplicate, ứng dụng đọc kết quả đã lưu và trả lại kết quả tương ứng thay vì thực hiện thanh toán lần nữa.

Thiết kế idempotency cần xác định:

- Key được tạo ở client hay server và có đủ entropy/không đoán được không.
- Key có phạm vi theo tenant, user hoặc endpoint không.
- Cùng key nhưng payload khác nhau được xử lý thế nào.
- Kết quả nghiệp vụ và trạng thái cuối cùng được lưu ra sao.
- Thời gian lưu key và cách xử lý retry đến muộn.
- Transaction bao gồm cả bản ghi idempotency và thay đổi nghiệp vụ nào.

Không chỉ dùng một unique key rồi bỏ qua lỗi. Cần bảo đảm việc ghi key và kết quả nghiệp vụ nằm trong cùng transaction hoặc có quy trình khôi phục rõ ràng để không tồn tại key đã ghi nhưng nghiệp vụ chưa hoàn tất.

## 9. Xử lý dữ liệu trùng trước khi thêm UNIQUE index

Một migration có thể thất bại khi thêm unique index vì dữ liệu cũ đã có duplicate:

~~~sql
ALTER TABLE users
ADD UNIQUE KEY uq_users_email (email);
~~~

Trước khi chạy, kiểm tra:

~~~sql
SELECT email, COUNT(*) AS duplicate_count
FROM users
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Với unique composite:

~~~sql
SELECT tenant_id, external_ref, COUNT(*) AS duplicate_count
FROM orders
WHERE external_ref IS NOT NULL
GROUP BY tenant_id, external_ref
HAVING COUNT(*) > 1;
~~~

Nếu có duplicate, không xóa tùy tiện một hàng. Trước tiên xác định:

1. Những hàng nào là bản ghi hợp lệ và cần giữ.
2. Các hàng có quan hệ foreign key, lịch sử, thanh toán hoặc audit nào.
3. Có thể hợp nhất dữ liệu hay phải giữ lại các hàng riêng.
4. Các hệ thống bên ngoài có đang tham chiếu ID của hàng bị loại bỏ không.
5. Quy tắc chuẩn hóa mới có làm phát sinh thêm duplicate không.

Một kế hoạch làm sạch nên có backup, bảng staging hoặc bản sao dữ liệu, tiêu chí chọn bản ghi giữ lại, mapping ID nếu hợp nhất và kiểm tra số lượng trước/sau.

### 9.1. Tìm duplicate với ROW_NUMBER trên MySQL 8.0+

Có thể đánh số hàng trong mỗi nhóm trùng để lập danh sách cần rà soát:

~~~sql
WITH ranked AS (
    SELECT
        user_id,
        tenant_id,
        email,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, email
            ORDER BY user_id
        ) AS row_num
    FROM users
)
SELECT *
FROM ranked
WHERE row_num > 1;
~~~

Truy vấn trên chỉ tạo danh sách ứng viên trùng; nó không quyết định rằng hàng có row_num > 1 là bản ghi được phép xóa. ORDER BY user_id chỉ là quy tắc sắp xếp minh họa. Quy tắc giữ lại phải dựa trên trạng thái nghiệp vụ, dữ liệu liên quan và audit.

Trên MySQL 5.7 không có window function, có thể dùng GROUP BY để tìm nhóm trùng rồi join lại với bảng gốc để xem chi tiết.

### 9.2. Thêm UNIQUE index sau khi làm sạch

Sau khi dữ liệu đã được chuẩn hóa và không còn duplicate, tạo unique index:

~~~sql
ALTER TABLE users
    ADD UNIQUE KEY uq_users_tenant_email (tenant_id, email);
~~~

Với bảng lớn, kiểm tra dung lượng, metadata lock, thời gian DDL và tác động tới replication trước khi triển khai. Việc thêm unique index có thể phải quét dữ liệu và thất bại nếu một transaction đồng thời tạo duplicate trong lúc xây index. Hãy phối hợp chặn/kiểm soát ghi hoặc dùng quy trình migration online phù hợp với phiên bản và workload.

Sau khi tạo, xác minh:

~~~sql
SHOW INDEX FROM users;
SHOW CREATE TABLE users\G
~~~

## 10. Duplicate với AUTO_INCREMENT và khóa ghép

### 10.1. AUTO_INCREMENT không bảo đảm mọi INSERT đều không trùng

Thông thường MySQL tự cấp giá trị AUTO_INCREMENT mới, nhưng duplicate vẫn có thể xảy ra khi:

- Ứng dụng tự gửi giá trị primary key đã tồn tại.
- Import dữ liệu chứa ID đã có trên đích.
- Hai nguồn ghi độc lập tạo ID đụng nhau trong kiến trúc multi-source.
- Các biến auto_increment_increment/auto_increment_offset trong topology nhiều writer được cấu hình không phù hợp.
- Dữ liệu được restore hoặc đồng bộ với trạng thái auto-increment không phù hợp.

Kiểm tra giá trị hiện tại và định nghĩa:

~~~sql
SHOW CREATE TABLE orders\G

SELECT AUTO_INCREMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

Không sửa AUTO_INCREMENT để né một lỗi duplicate nếu chưa xác định nguồn ID. Nếu hệ thống có nhiều writer, phải thiết kế cách phân bổ ID duy nhất như vùng ID, increment/offset có kiểm soát hoặc ID phân tán.

### 10.2. Khóa chính ghép

Với bảng quan hệ nhiều-nhiều:

~~~sql
CREATE TABLE user_roles (
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    assigned_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_id, role_id)
);
~~~

Một cặp user/role chỉ được gán một lần. Duplicate ở đây thường có nghĩa ứng dụng đang gán lại một role đã tồn tại. Nếu nghiệp vụ cho phép thao tác lặp an toàn, có thể coi kết quả là “đã được gán” sau khi xác nhận hàng hiện có; không nhất thiết tạo thêm một bản ghi.

Nếu cần lưu nhiều lần gán/thu hồi theo lịch sử, mô hình hiện tại không đủ. Có thể dùng một assignment_id riêng và unique constraint có trạng thái hoặc thời gian phù hợp với quy tắc nghiệp vụ. Đừng xóa unique constraint chỉ để cho phép dữ liệu lặp nếu tính duy nhất vẫn là yêu cầu nghiệp vụ.

## 11. Transaction và cạnh tranh đồng thời

InnoDB sử dụng khóa và kiểm tra unique index để bảo vệ tính duy nhất trong các transaction đồng thời. Khi hai transaction cùng chèn một khóa mới giống nhau, một transaction có thể phải chờ transaction kia kết thúc. Nếu transaction kia commit, thao tác còn lại sẽ nhận duplicate; nếu transaction kia rollback, thao tác đang chờ có thể tiếp tục thành công.

Ví dụ logic:

~~~text
Transaction A                  Transaction B
-------------                  -------------
BEGIN                          BEGIN
INSERT key = K                 INSERT key = K
                               chờ kết quả khóa/index
COMMIT                         nhận duplicate 1062
~~~

Đây là hành vi bảo vệ tính toàn vẹn. Không nên tìm cách loại bỏ unique index để tránh chờ hoặc tránh lỗi.

### 11.1. Không retry mù lỗi duplicate

Lỗi 1062 thường là xung đột xác định theo dữ liệu, không phải lỗi transient để retry vô hạn. Retry cùng câu INSERT với cùng giá trị thường tiếp tục thất bại.

Chỉ retry khi nghiệp vụ xác định đó là request lặp có thể trả lại kết quả cũ, hoặc khi đã thay đổi dữ liệu đầu vào theo một quy trình có kiểm soát. Với deadlock 1213, chiến lược retry transaction có thể phù hợp hơn, nhưng phải retry toàn bộ transaction và bảo đảm thao tác idempotent.

### 11.2. Kiểm tra rồi cập nhật

Nếu nghiệp vụ muốn “tạo nếu chưa có, nếu có thì cập nhật”, dùng thao tác upsert nguyên tử phù hợp với unique key thay vì SELECT rồi INSERT rồi UPDATE nhiều bước. Nếu nhánh update cần nhiều điều kiện, hãy dùng transaction và khóa hàng theo mô hình đã thiết kế.

SELECT ... FOR UPDATE có thể khóa hàng đã tồn tại, nhưng không phải giải pháp tổng quát để khóa một hàng chưa tồn tại trong mọi isolation level và access path. Cần hiểu next-key/gap lock, isolation level và index của truy vấn trước khi dùng nó để ngăn race condition.

## 12. Quy trình điều tra lỗi trong production

Khi gặp lỗi duplicate, thu thập thông tin trước khi thay đổi dữ liệu:

1. Ghi nhận thời điểm, request/correlation ID, câu lệnh hoặc SQL template và mã lỗi.
2. Xác định bảng, unique key hoặc primary key bị vi phạm.
3. Đọc SHOW CREATE TABLE và SHOW INDEX để biết đầy đủ định nghĩa index.
4. Xác định hàng hiện có bằng toàn bộ cột của unique key và đúng collation.
5. Kiểm tra request có bị retry, gửi lặp, chạy song song hoặc xử lý lại từ queue không.
6. Kiểm tra các luồng import, batch, replication và job nền có cùng ghi vào bảng không.
7. Xác định duplicate là conflict hợp lệ, dữ liệu cũ, race condition hay lỗi sinh ID.
8. Chọn cách xử lý theo nghiệp vụ: trả conflict, trả kết quả idempotent, upsert hoặc làm sạch dữ liệu.
9. Theo dõi số lỗi 1062 theo constraint và endpoint sau khi triển khai sửa lỗi.

Không log toàn bộ dữ liệu nhạy cảm chỉ để điều tra duplicate. Có thể ghi tên constraint, ID request và giá trị đã được mask/hash phù hợp chính sách.

## 13. Ví dụ: API đăng ký tài khoản

Giả sử mỗi tenant chỉ được có một tài khoản cho một email. Schema:

~~~sql
CREATE TABLE tenant_users (
    id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_tenant_users_email (tenant_id, email)
) ENGINE=InnoDB;
~~~

Service không cần dựa vào một truy vấn kiểm tra trước để đảm bảo không có duplicate. Service có thể thực hiện INSERT và xử lý lỗi unique constraint:

~~~java
public User register(long tenantId, String email, String displayName) {
    try {
        return userRepository.insertNew(tenantId, email, displayName);
    } catch (DuplicateKeyException ex) {
        throw new EmailAlreadyRegisteredException(tenantId, email, ex);
    }
}
~~~

Nếu API cần trả lại cùng kết quả khi client retry, hãy thêm request idempotency key riêng. Email unique và idempotency key giải quyết hai vấn đề khác nhau:

- Unique email: không cho một tenant đăng ký cùng email hai lần.
- Idempotency key: không xử lý một yêu cầu gửi lại như một nghiệp vụ mới.

Nếu tenant khác đăng ký cùng email, unique composite key cho phép. Nếu nghiệp vụ yêu cầu email toàn cục, cần đổi constraint và test dữ liệu hiện có trước khi migration.

## 14. Checklist xử lý Duplicate entry

- [ ] Đã lấy mã lỗi MySQL và xác nhận có phải 1062 không.
- [ ] Đã xác định đúng bảng và tên PRIMARY/UNIQUE index.
- [ ] Đã đọc SHOW CREATE TABLE và toàn bộ cột của unique key.
- [ ] Đã kiểm tra collation, charset và quy tắc so sánh chuỗi.
- [ ] Đã xác định unique key đơn cột hay composite.
- [ ] Đã kiểm tra giá trị NULL và quy tắc unique index của MySQL.
- [ ] Đã tìm hàng hiện có bằng toàn bộ khóa và đúng ngữ nghĩa so sánh.
- [ ] Đã kiểm tra request retry, batch, queue và các writer đồng thời.
- [ ] Đã phân biệt conflict nghiệp vụ với lỗi transient như deadlock/timeout.
- [ ] Đã chọn INSERT, INSERT IGNORE hoặc ON DUPLICATE KEY UPDATE theo đúng ý nghĩa.
- [ ] Đã kiểm tra tác động của REPLACE nếu có ai đề xuất sử dụng.
- [ ] Đã thiết kế idempotency nếu request có thể được gửi lại.
- [ ] Đã làm sạch và đối soát dữ liệu trước khi thêm UNIQUE index.
- [ ] Đã backup, kiểm thử và chuẩn bị kế hoạch rollback cho migration.
- [ ] Đã theo dõi lỗi duplicate theo constraint sau khi sửa.

## 15. Tự kiểm tra

1. PRIMARY KEY và UNIQUE index khác nhau như thế nào về số lượng, NULL và vai trò?
2. Vì sao hai hàng có cùng email vẫn có thể hợp lệ khi unique key là (tenant_id, email)?
3. Lỗi 1062 và SQLSTATE 23000 cho biết điều gì?
4. Vì sao hai chuỗi khác hoa/thường có thể vi phạm cùng một unique index?
5. Vì sao SELECT kiểm tra trước INSERT không ngăn được race condition?
6. Khi nào nên dùng ON DUPLICATE KEY UPDATE và khi nào cần trả lỗi conflict?
7. Vì sao INSERT IGNORE có thể che giấu lỗi dữ liệu ngoài duplicate?
8. REPLACE INTO khác upsert như thế nào và có thể ảnh hưởng tới foreign key/trigger ra sao?
9. Vì sao cần idempotency key cho API có thể được retry sau timeout?
10. Hãy lập quy trình làm sạch dữ liệu trước khi thêm unique key (tenant_id, email) cho một bảng có hàng chục triệu bản ghi.

Khi gặp Duplicate entry, hãy bắt đầu từ constraint bị vi phạm và quy tắc so sánh thực tế của index. Sau đó xác định xung đột đến từ dữ liệu, retry hay cạnh tranh đồng thời; chọn cách xử lý đúng với nghiệp vụ và giữ unique constraint làm lớp bảo vệ cuối cùng cho tính toàn vẹn dữ liệu.
