# ENUM, SET và đánh đổi khi thay đổi tập giá trị

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích cách MySQL lưu và biểu diễn giá trị của ENUM và SET.
- Chọn ENUM, SET hay bảng danh mục quan hệ theo đặc điểm của miền dữ liệu.
- Tránh các lỗi thường gặp liên quan đến giá trị không hợp lệ, thứ tự phần tử và ép kiểu số.
- Thiết kế thay đổi tập giá trị an toàn khi ứng dụng đang hoạt động.
- Lập kế hoạch thêm, đổi tên, thay thế hoặc loại bỏ giá trị mà không làm sai lệch dữ liệu.
- Kiểm tra ảnh hưởng của DDL, migration, index, ứng dụng và các phiên bản đang chạy.

Trong MySQL, ENUM và SET là hai kiểu dữ liệu chuỗi có miền giá trị được khai báo ngay trong định nghĩa cột. ENUM biểu diễn một lựa chọn đơn từ danh sách cố định; SET biểu diễn một tập gồm không hoặc nhiều lựa chọn từ danh sách cố định. Chúng giúp ràng buộc dữ liệu ở database, nhưng mỗi kiểu có quy tắc lưu trữ, sắp xếp và thay đổi schema riêng.

Điểm cần cân nhắc không chỉ là cách khai báo ban đầu. Một tập giá trị có thể thay đổi theo nghiệp vụ: thêm trạng thái mới, ngừng dùng một kênh, đổi tên một lựa chọn hoặc tách một trạng thái thành nhiều trạng thái. Nếu chọn kiểu dữ liệu không phù hợp hoặc thay đổi thiếu thứ tự, ứng dụng cũ, dữ liệu cũ và schema mới có thể không còn tương thích.

## 1. ENUM: một giá trị trong danh sách cố định

### 1.1. Khai báo và sử dụng

ENUM (enumeration) cho phép một cột nhận một giá trị trong danh sách đã khai báo. Ví dụ, một ticket chỉ có một trạng thái tại một thời điểm:

~~~sql
CREATE TABLE support_ticket (
    ticket_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    subject VARCHAR(200) NOT NULL,
    status ENUM(
        'new',
        'in_progress',
        'waiting_customer',
        'resolved',
        'closed'
    ) NOT NULL DEFAULT 'new',
    PRIMARY KEY (ticket_id)
) ENGINE = InnoDB;
~~~

Giá trị của cột status phải thuộc danh sách. Một số thao tác:

~~~sql
INSERT INTO support_ticket (subject, status)
VALUES ('Không đăng nhập được', 'new');

UPDATE support_ticket
SET status = 'in_progress'
WHERE ticket_id = 1;

SELECT ticket_id, subject, status
FROM support_ticket
WHERE status = 'in_progress';
~~~

Khi đọc bằng truy vấn thông thường, MySQL trả về nhãn chuỗi như 'new' hoặc 'in_progress'. Ứng dụng thường xử lý giá trị theo nhãn đã khai báo, không cần biết chỉ số lưu trữ nội bộ.

ENUM phù hợp khi tất cả điều kiện sau phần lớn đều đúng:

- Mỗi hàng chỉ có một giá trị trong miền lựa chọn.
- Danh sách tương đối nhỏ và thay đổi không thường xuyên.
- Các giá trị có ý nghĩa rõ ràng trong mô hình dữ liệu.
- Mỗi giá trị không cần nhiều thuộc tính riêng như mô tả, người quản lý, ngày hiệu lực hoặc cấu hình.
- Nhóm phát triển kiểm soát được quy trình thay đổi schema và triển khai ứng dụng.

### 1.2. ENUM được lưu như thế nào?

MySQL lưu ENUM bằng một chỉ số số nguyên nội bộ tương ứng với vị trí phần tử trong danh sách khai báo. Phần tử đầu tiên có chỉ số 1, phần tử thứ hai có chỉ số 2, tiếp tục như vậy. Chỉ số 0 là giá trị lỗi đặc biệt, được hiển thị thành chuỗi rỗng trong một số trường hợp giá trị không hợp lệ được chấp nhận ở chế độ không strict.

Ví dụ:

~~~sql
CREATE TABLE enum_demo (
    state ENUM('draft', 'published', 'archived') NOT NULL
);

INSERT INTO enum_demo (state)
VALUES ('draft'), ('published'), ('archived');

SELECT state, state + 0 AS internal_index
FROM enum_demo;
~~~

Kết quả minh họa:

| state | internal_index |
|---|---:|
| draft | 1 |
| published | 2 |
| archived | 3 |

Việc MySQL có chỉ số nội bộ không có nghĩa ứng dụng nên dùng chỉ số đó làm mã nghiệp vụ. Nếu danh sách thay đổi thứ tự, ý nghĩa của chỉ số có thể thay đổi. Hãy lưu và trao đổi nhãn ổn định như 'published', không lưu ordinal trong code rồi giả định ordinal luôn bất biến.

ENUM dùng 1 byte khi số phần tử nằm trong giới hạn có thể biểu diễn bằng 1 byte, và 2 byte khi cần nhiều hơn. Danh sách có thể có tối đa 65.535 phần tử khác nhau; mỗi nhãn có giới hạn độ dài theo quy tắc của MySQL. Đây là giới hạn kỹ thuật, không phải mục tiêu thiết kế. Một ENUM hàng trăm lựa chọn thường là dấu hiệu nên xem xét bảng danh mục.

### 1.3. Thứ tự của ENUM

Một đặc điểm quan trọng: phép sắp xếp ENUM theo thứ tự chỉ số khai báo, không phải thứ tự từ điển của chuỗi.

~~~sql
SELECT state
FROM enum_demo
ORDER BY state;
~~~

Với danh sách khai báo là draft, published, archived, kết quả sắp xếp theo đúng thứ tự đó, dù theo alphabet archived sẽ đứng trước draft.

Nếu nghiệp vụ cần thứ tự khác với thứ tự định nghĩa, hãy chỉ rõ thứ tự trong truy vấn:

~~~sql
SELECT ticket_id, status
FROM support_ticket
ORDER BY FIELD(
    status,
    'new',
    'in_progress',
    'waiting_customer',
    'resolved',
    'closed'
);
~~~

Đừng thay đổi thứ tự khai báo chỉ để sửa một màn hình báo cáo. Việc đó có thể tác động đến thứ tự sắp xếp ở những truy vấn khác và đến chỉ số số nguyên nội bộ. Thứ tự trình bày nên thuộc về truy vấn hoặc lớp ứng dụng khi nó là yêu cầu hiển thị.

### 1.4. Giá trị không hợp lệ và SQL mode

Nếu gán một chuỗi không có trong danh sách ENUM, kết quả phụ thuộc SQL mode. Ở chế độ strict, MySQL thường từ chối câu lệnh với lỗi. Ở chế độ không strict, MySQL có thể chuyển giá trị không hợp lệ thành chuỗi rỗng đặc biệt có chỉ số 0 và phát cảnh báo.

~~~sql
INSERT INTO enum_demo (state)
VALUES ('under_review');

SHOW WARNINGS;

SELECT state, state + 0
FROM enum_demo
WHERE state = '';
~~~

Chỉ số 0 khác với một phần tử chuỗi rỗng được khai báo hợp lệ trong ENUM. Để kiểm tra giá trị lỗi đặc biệt, phép so sánh với chuỗi rỗng cần được xem cùng chỉ số số nguyên; không nên dựa vào hiển thị chuỗi đơn lẻ để phân biệt mọi trường hợp.

Hãy giữ SQL mode nghiêm ngặt phù hợp với ứng dụng và kiểm tra cảnh báo sau các thao tác nạp dữ liệu. Đừng để dữ liệu không hợp lệ âm thầm trở thành giá trị rỗng rồi tiếp tục đi vào báo cáo hoặc quy trình nghiệp vụ.

Một trường hợp dễ nhầm khác là gán số cho ENUM. MySQL có thể diễn giải số nguyên như chỉ số phần tử, thay vì nhãn chuỗi. Nếu danh sách có nhãn trông giống số, hoặc ứng dụng gửi tham số số, kết quả có thể khó đoán. Hãy truyền nhãn chuỗi rõ ràng và tránh dùng giá trị số làm giao diện lưu trữ cho ENUM.

## 2. SET: không hoặc nhiều giá trị trong danh sách cố định

### 2.1. Khai báo và sử dụng

SET cho phép một cột chứa một hoặc nhiều thành viên từ danh sách khai báo. Ví dụ, một bài viết có thể được phân phối qua nhiều kênh:

~~~sql
CREATE TABLE article (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    channels SET('web', 'mobile', 'email') NOT NULL DEFAULT 'web',
    PRIMARY KEY (article_id)
) ENGINE = InnoDB;
~~~

Một hàng có thể chọn một thành viên hoặc nhiều thành viên:

~~~sql
INSERT INTO article (title, channels)
VALUES
    ('Thông báo bảo trì', 'web'),
    ('Bản tin tuần', 'web,email'),
    ('Thông báo ứng dụng', 'mobile,email');

SELECT article_id, title, channels
FROM article;
~~~

Giá trị trả về được biểu diễn thành chuỗi gồm các thành viên được chọn, ngăn cách bằng dấu phẩy. MySQL xuất các thành viên theo thứ tự khai báo trong định nghĩa SET, không phụ thuộc thứ tự chuỗi đầu vào.

SET có thể chứa tối đa 64 thành viên khác nhau. Mỗi thành viên có giới hạn độ dài theo quy tắc MySQL. Kiểu này phù hợp với một tập lựa chọn nhỏ, ổn định, có tính chất giống các cờ độc lập và chỉ cần lưu trong một cột.

### 2.2. SET được lưu như thế nào?

MySQL lưu SET bằng bitmask. Mỗi thành viên được gán một bit theo vị trí khai báo. Một giá trị SET là tổ hợp các bit được bật tương ứng với thành viên đã chọn. Dung lượng lưu trữ phụ thuộc số thành viên, từ 1 đến 8 byte.

Ví dụ:

~~~sql
CREATE TABLE set_demo (
    features SET('search', 'export', 'share', 'comment') NOT NULL
);

INSERT INTO set_demo (features)
VALUES ('search,share'), ('export'), ('search,export,comment');

SELECT features, features + 0 AS bitmask
FROM set_demo;
~~~

Mỗi thành viên tương ứng với một bit; tổ hợp nhiều thành viên tạo thành giá trị số. Giống ENUM, số nội bộ là chi tiết triển khai. Không dùng bitmask làm mã nghiệp vụ được lưu ở hệ thống khác nếu không có hợp đồng ổn định về thứ tự thành viên.

Nếu đổi thứ tự thành viên trong khai báo, ánh xạ giữa tên và bit thay đổi. Vì vậy, không nên tùy tiện sắp xếp lại danh sách SET sau khi đã có dữ liệu hoặc ứng dụng phụ thuộc vào giá trị số.

### 2.3. Tìm kiếm thành viên của SET

Có thể dùng FIND_IN_SET để kiểm tra một thành viên có nằm trong giá trị SET hay không:

~~~sql
SELECT article_id, title, channels
FROM article
WHERE FIND_IN_SET('email', channels) > 0;
~~~

MySQL có tối ưu riêng cho trường hợp đối số đầu là hằng số và đối số thứ hai là cột SET. Tuy vậy, điều đó không biến SET thành mô hình quan hệ nhiều-nhiều tổng quát. Khi cần truy vấn linh hoạt theo thành viên, join, ràng buộc khóa ngoại hoặc thống kê theo từng thành viên, bảng liên kết thường phù hợp hơn.

Không dùng LIKE '%email%' để tìm thành viên. LIKE có thể khớp nhầm một phần chuỗi và không diễn đạt chính xác ngữ nghĩa tập thành viên.

Một thành viên SET không thể chứa dấu phẩy vì dấu phẩy là ký tự phân tách các thành viên trong giá trị. Khi gán một thành viên không tồn tại, SQL mode cũng có ảnh hưởng: strict mode thường từ chối câu lệnh; ở chế độ không strict, MySQL có thể bỏ qua thành viên không hợp lệ và phát cảnh báo. Ví dụ:

~~~sql
INSERT INTO article (title, channels)
VALUES ('Thử nghiệm kênh không tồn tại', 'web,fax');

SHOW WARNINGS;
~~~

Trong chế độ không strict, hàng có thể chỉ còn thành viên hợp lệ 'web'. Hãy kiểm tra cảnh báo ngay sau câu lệnh ghi để tránh dữ liệu đầu vào bị mất một phần mà ứng dụng không nhận ra.

### 2.4. Khi nào SET không phù hợp?

SET trở nên khó quản lý khi:

- Danh sách thành viên thay đổi thường xuyên.
- Một thành viên cần metadata riêng, ví dụ tên hiển thị, thứ tự, trạng thái hoạt động hoặc quyền hạn.
- Cần khóa ngoại bảo đảm thành viên được chọn phải tồn tại trong bảng danh mục.
- Cần lọc, join, đếm, phân trang hoặc phân quyền theo từng thành viên với truy vấn phong phú.
- Tập lựa chọn có thể vượt quá 64 thành viên.
- Các lựa chọn không phải những cờ độc lập mà có quan hệ nghiệp vụ phức tạp.

Ví dụ, quyền của người dùng thường có quan hệ với vai trò, phạm vi tài nguyên, thời hạn và người cấp quyền. Dùng một cột SET để giữ mọi quyền sẽ khiến việc kiểm tra và thay đổi quyền khó mở rộng. Mô hình bảng user_role, role_permission hoặc bảng liên kết phù hợp hơn.

## 3. Chọn ENUM, SET hay bảng danh mục?

ENUM và SET là kiểu dữ liệu hữu ích khi miền giá trị nhỏ và ổn định. Nếu danh sách giá trị có vòng đời riêng hoặc cần mở rộng thường xuyên, hãy biểu diễn danh sách đó bằng dữ liệu quan hệ.

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Một trạng thái nhỏ, ổn định cho mỗi hàng | ENUM | Ràng buộc một giá trị tại database, định nghĩa đơn giản |
| Một tập cờ nhỏ, ổn định, không cần join | SET | Biểu diễn nhiều lựa chọn trong một cột |
| Danh mục có mô tả, thứ tự, trạng thái hoạt động hoặc ngày hiệu lực | Bảng danh mục + foreign key | Giá trị trở thành dữ liệu có thể quản lý độc lập |
| Một bản ghi liên kết với nhiều danh mục | Bảng liên kết nhiều-nhiều | Chuẩn hóa quan hệ và hỗ trợ khóa ngoại |
| Danh sách giá trị thay đổi liên tục qua cấu hình nghiệp vụ | Bảng danh mục | Có thể thêm/sửa/ngừng dùng mà không đổi schema |
| Thuộc tính dạng cờ độc lập, luôn có cùng ý nghĩa | Cột BOOLEAN riêng hoặc kiểu phù hợp | Truy vấn rõ ràng và tránh tập hợp chuỗi khó kiểm soát |

### 3.1. Ví dụ chuyển ENUM sang bảng danh mục

Giả sử trạng thái đơn hàng ban đầu chỉ gồm các giá trị cố định:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    status ENUM('pending', 'paid', 'shipped', 'cancelled')
        NOT NULL DEFAULT 'pending',
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
~~~

Sau này, nghiệp vụ cần thêm mô tả, thứ tự hiển thị, trạng thái kết thúc và cờ cho biết trạng thái có cho phép hủy hay không. Thay vì tiếp tục mở rộng ENUM, có thể tạo bảng danh mục:

~~~sql
CREATE TABLE order_status (
    status_code VARCHAR(32) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    sort_order SMALLINT NOT NULL,
    is_terminal BOOLEAN NOT NULL DEFAULT FALSE,
    allows_cancel BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (status_code),
    UNIQUE KEY uq_order_status_sort (sort_order)
) ENGINE = InnoDB;

INSERT INTO order_status
    (status_code, display_name, sort_order, is_terminal, allows_cancel)
VALUES
    ('pending', 'Chờ thanh toán', 10, FALSE, TRUE),
    ('paid', 'Đã thanh toán', 20, FALSE, TRUE),
    ('shipped', 'Đã giao', 30, TRUE, FALSE),
    ('cancelled', 'Đã hủy', 40, TRUE, FALSE);
~~~

Khi chuyển đổi, thêm cột mới, backfill theo mã trạng thái, xác nhận không có giá trị không ánh xạ, rồi tạo foreign key sau khi dữ liệu hợp lệ:

~~~sql
ALTER TABLE orders
    ADD COLUMN status_code VARCHAR(32) NULL;

UPDATE orders
SET status_code = CAST(status AS CHAR);

SELECT status, COUNT(*) AS row_count
FROM orders
GROUP BY status;

SELECT COUNT(*) AS missing_status
FROM orders
WHERE status_code IS NULL;
~~~

Ví dụ trên minh họa bước backfill; trong một migration thực tế cần kiểm tra đầy đủ tập giá trị và dữ liệu lỗi trước khi chuyển ứng dụng. Sau khi cột mới được điền đầy đủ và ứng dụng đã chuyển sang dùng nó, có thể bổ sung ràng buộc:

~~~sql
ALTER TABLE orders
    MODIFY status_code VARCHAR(32) NOT NULL,
    ADD CONSTRAINT fk_orders_status
        FOREIGN KEY (status_code)
        REFERENCES order_status(status_code);
~~~

Việc đổi tên hoặc xóa cột ENUM cũ là bước riêng, chỉ thực hiện sau khi không còn phiên bản ứng dụng nào đọc hoặc ghi cột cũ và đã có kế hoạch rollback/roll-forward.

## 4. Những rủi ro khi thay đổi tập giá trị

Thay đổi định nghĩa ENUM hoặc SET là thay đổi schema, không chỉ là sửa một chuỗi trong ứng dụng. Cần đánh giá dữ liệu hiện có, thứ tự phần tử, giá trị mặc định, NULL, index, câu truy vấn, ORM, phiên bản ứng dụng và chi phí DDL.

### 4.1. Thêm một giá trị ENUM

Giả sử cần thêm trạng thái 'refunded'. Thay đổi định nghĩa:

~~~sql
ALTER TABLE support_ticket
    MODIFY COLUMN status ENUM(
        'new',
        'in_progress',
        'waiting_customer',
        'resolved',
        'closed',
        'refunded'
    ) NOT NULL DEFAULT 'new';
~~~

Khi dùng MODIFY COLUMN, phải khai báo lại đầy đủ thuộc tính cột cần giữ như NULL/NOT NULL, DEFAULT, COMMENT, CHARACTER SET/COLLATE và các thuộc tính khác. Bỏ sót một thuộc tính có thể làm định nghĩa cột thay đổi ngoài dự kiến.

Thêm giá trị mới vào cuối danh sách thường dễ kiểm soát hơn vì giữ nguyên thứ tự của các giá trị hiện có. Tuy nhiên, vẫn cần kiểm tra phiên bản MySQL và điều kiện DDL: một số thay đổi có thể thực hiện nhanh theo metadata, trong khi thay đổi khác có thể cần rebuild table hoặc giữ metadata lock. Không giả định mọi ALTER ENUM đều là instant hoặc không gây ảnh hưởng.

### 4.2. Thêm một thành viên SET

Giả sử cần thêm kênh 'push':

~~~sql
ALTER TABLE article
    MODIFY COLUMN channels
        SET('web', 'mobile', 'email', 'push')
        NOT NULL DEFAULT 'web';
~~~

Thêm thành viên vào cuối danh sách giúp giữ nguyên bit của các thành viên cũ. Việc thêm thành viên có thể thay đổi kích thước lưu trữ khi số thành viên vượt ranh giới byte. Khả năng áp dụng DDL online/instant phụ thuộc phiên bản MySQL và thay đổi cụ thể; cần kiểm tra trên đúng phiên bản và dữ liệu đại diện.

### 4.3. Đổi tên một giá trị

ENUM và SET không có thao tác rename member độc lập. Đổi tên thường được thực hiện bằng cách thay đổi định nghĩa cột và chuyển dữ liệu.

Ví dụ đổi 'waiting_customer' thành 'waiting_user'. Trước tiên cần bổ sung nhãn mới trong schema, sau đó cập nhật dữ liệu:

~~~sql
ALTER TABLE support_ticket
    MODIFY COLUMN status ENUM(
        'new',
        'in_progress',
        'waiting_customer',
        'waiting_user',
        'resolved',
        'closed',
        'refunded'
    ) NOT NULL DEFAULT 'new';

UPDATE support_ticket
SET status = 'waiting_user'
WHERE status = 'waiting_customer';
~~~

Sau khi backfill, ứng dụng phải đọc/ghi nhãn mới. Chỉ loại nhãn cũ khỏi ENUM trong một lần migration sau khi xác nhận không còn dữ liệu cũ và không còn ứng dụng phiên bản cũ gửi nhãn đó.

Không đổi tên trong một bước duy nhất khi nhiều phiên bản ứng dụng cùng chạy. Phiên bản cũ có thể tiếp tục ghi nhãn cũ sau khi schema đã loại bỏ nhãn này.

### 4.4. Loại bỏ một giá trị đang được sử dụng

Trước khi loại bỏ một giá trị, xác định số hàng đang dùng nó:

~~~sql
SELECT status, COUNT(*) AS row_count
FROM support_ticket
GROUP BY status
ORDER BY status;
~~~

Nếu có hàng đang mang giá trị cần loại bỏ, hãy quyết định ánh xạ nghiệp vụ. Ví dụ, có thể chuyển trạng thái cũ sang một trạng thái thay thế sau khi được nghiệp vụ xác nhận:

~~~sql
UPDATE support_ticket
SET status = 'closed'
WHERE status = 'resolved';
~~~

Không dùng ví dụ ánh xạ trên như quy tắc chung; trạng thái thay thế phải đúng ý nghĩa nghiệp vụ. Sau khi dữ liệu đã được chuyển và xác minh, mới sửa định nghĩa ENUM để bỏ giá trị cũ.

Nếu định nghĩa mới không còn chứa giá trị đang có trong dữ liệu, quá trình chuyển đổi có thể tạo giá trị lỗi đặc biệt hoặc bị từ chối tùy SQL mode và cách DDL được thực hiện. Không dựa vào hành vi ép kiểu để âm thầm loại bỏ dữ liệu.

Với SET, trước khi bỏ một thành viên, phải tìm mọi hàng có chứa thành viên đó, quyết định giữ hay bỏ thành viên khỏi từng tập, rồi mới sửa định nghĩa. Ví dụ:

~~~sql
SELECT article_id, channels
FROM article
WHERE FIND_IN_SET('mobile', channels) > 0;
~~~

MySQL không có một hàm xóa thành viên SET theo tên đơn giản. Với danh sách nhỏ, có thể ánh xạ từng tổ hợp đã biết sang tổ hợp mới bằng CASE; ví dụ dưới đây bao phủ bốn tổ hợp có 'mobile' trong danh sách ba thành viên của bài học:

~~~sql
UPDATE article
SET channels = CASE channels
    WHEN 'mobile' THEN ''
    WHEN 'web,mobile' THEN 'web'
    WHEN 'mobile,email' THEN 'email'
    WHEN 'web,mobile,email' THEN 'web,email'
    ELSE channels
END
WHERE FIND_IN_SET('mobile', channels) > 0;
~~~

Trong hệ thống thực tế, phải bao phủ đầy đủ mọi tổ hợp có thể xuất hiện hoặc chuyển dữ liệu qua logic ứng dụng đã kiểm thử. Sau đó xác minh lại không còn hàng nào chứa thành viên đó trước khi loại khỏi định nghĩa.

### 4.5. Đổi thứ tự phần tử

Thứ tự phần tử không phải chi tiết trình bày vô hại:

- ENUM sắp xếp theo chỉ số khai báo; đổi thứ tự có thể thay đổi kết quả ORDER BY và ánh xạ chỉ số nội bộ.
- SET gán bit theo vị trí thành viên; đổi thứ tự làm thay đổi bitmask nội bộ.
- Ứng dụng hoặc báo cáo dựa trên giá trị số có thể diễn giải sai sau thay đổi.

Giữ nguyên thứ tự phần tử hiện có và chỉ thêm giá trị mới vào cuối danh sách nếu cần mở rộng. Nếu thật sự phải đổi thứ tự, hãy coi đó là migration dữ liệu có kiểm soát, kiểm thử đầy đủ và xác nhận không có hệ thống nào phụ thuộc vào ordinal/bitmask.

## 5. Quy trình migration an toàn khi ứng dụng vẫn đang chạy

Một thay đổi schema cần tính đến việc nhiều phiên bản ứng dụng có thể cùng tồn tại trong thời gian triển khai. Ví dụ, bản mới có thể gửi trạng thái 'refunded', trong khi một worker cũ vẫn chỉ biết các trạng thái trước đó.

Một quy trình mở rộng rồi thu hẹp (expand/contract) thường an toàn hơn:

~~~mermaid
flowchart TD
    A[Đánh giá thay đổi và dữ liệu hiện tại] --> B[Expand schema: thêm giá trị mới]
    B --> C[Deploy code tương thích cả cũ và mới]
    C --> D[Backfill / chuyển dữ liệu nếu cần]
    D --> E[Kiểm tra dữ liệu và log]
    E --> F[Chuyển toàn bộ luồng đọc ghi sang giá trị mới]
    F --> G[Chờ hết phiên bản ứng dụng cũ]
    G --> H[Contract: bỏ giá trị/cột cũ]
    H --> I[Theo dõi sau migration]
~~~

### Bước 1: Kiểm kê trước thay đổi

Trước khi sửa schema, hãy ghi lại:

- Định nghĩa cột đầy đủ bằng SHOW CREATE TABLE.
- Số hàng theo từng giá trị và các giá trị bất thường.
- DEFAULT, NULL/NOT NULL, charset/collation và index liên quan.
- Các truy vấn, view, trigger, stored procedure và job có sử dụng cột.
- Phiên bản ứng dụng, ORM, API và consumer đang đọc/ghi giá trị.
- Dung lượng bảng, tốc độ ghi, metadata lock và giới hạn thời gian triển khai.

Lấy định nghĩa và phân bố dữ liệu:

~~~sql
SHOW CREATE TABLE support_ticket;

SELECT status, COUNT(*) AS row_count
FROM support_ticket
GROUP BY status
ORDER BY status;
~~~

### Bước 2: Expand schema

Thêm nhãn mới vào cuối danh sách, giữ nguyên các nhãn cũ, DEFAULT và nullability. Xác nhận DDL có thể chạy trong cửa sổ triển khai dự kiến. Nếu cần online schema change, đánh giá công cụ, khóa, trigger, foreign key và giới hạn vận hành trước khi chọn.

### Bước 3: Deploy ứng dụng tương thích

Triển khai code có thể đọc các giá trị cũ và mới. Chỉ bắt đầu ghi giá trị mới sau khi tất cả thành phần đọc quan trọng đã hiểu được giá trị đó, bao gồm API, consumer, báo cáo, batch job và worker nền.

Nếu hệ thống có nhiều dịch vụ, hãy xác định thứ tự triển khai. Một service chưa được cập nhật có thể từ chối dữ liệu mới hoặc hiển thị sai trạng thái.

### Bước 4: Chuyển dữ liệu và xác minh

Nếu thay đổi yêu cầu đổi tên hoặc thay thế giá trị, backfill theo lô với điều kiện rõ ràng. Với bảng lớn, tránh một UPDATE khổng lồ giữ lock lâu, tạo undo lớn hoặc làm tăng replication lag. Ghi nhận tiến độ và cho phép chạy lại an toàn khi cần.

Sau backfill, kiểm tra:

- Không còn hàng sử dụng giá trị cũ ngoài dự kiến.
- Không có giá trị lỗi đặc biệt của ENUM.
- Số hàng trước và sau chuyển đổi khớp với quy tắc nghiệp vụ.
- Replica theo kịp và không có lỗi apply.
- Các truy vấn, báo cáo và luồng ghi hoạt động đúng.

### Bước 5: Contract schema

Chỉ bỏ giá trị cũ sau khi đã hết phiên bản ứng dụng có thể ghi nó, hết consumer chưa cập nhật và dữ liệu đã được chuyển hoàn tất. Contract có thể là một lần ALTER TABLE riêng. Nếu thay đổi có rủi ro cao, giữ khả năng roll forward bằng migration tiếp theo và lưu backup phù hợp.

Không xem ROLLBACK SQL là cách phục hồi chung cho DDL. Nhiều câu lệnh DDL trong MySQL gây implicit commit. Hãy thiết kế hướng tiến an toàn và có phương án phục hồi dữ liệu được kiểm chứng.

## 6. Tác động đến index, truy vấn và ứng dụng

### 6.1. Index trên ENUM và SET

Có thể tạo index trên cột ENUM hoặc SET:

~~~sql
CREATE INDEX idx_ticket_status
ON support_ticket (status);
~~~

Index có thể hỗ trợ truy vấn lọc theo trạng thái, nhưng lợi ích phụ thuộc độ chọn lọc, phân bố dữ liệu và truy vấn thực tế. Nếu hầu hết hàng có cùng một trạng thái, index đơn cột có thể không đem lại lợi ích như mong đợi. Hãy kiểm tra kế hoạch bằng EXPLAIN và đo trên dữ liệu đại diện.

~~~sql
EXPLAIN
SELECT ticket_id, subject
FROM support_ticket
WHERE status = 'in_progress';
~~~

Khi thay đổi tập ENUM/SET, đánh giá lại index, thống kê và truy vấn có dùng so sánh số hoặc sắp xếp theo cột. Đặc biệt, truy vấn ORDER BY ENUM có thứ tự theo định nghĩa; đổi danh sách có thể làm thay đổi kết quả báo cáo dù dữ liệu chuỗi nhìn vẫn giống nhau.

### 6.2. Ứng dụng và ORM

Một số ORM ánh xạ enum của ngôn ngữ sang tên chuỗi, số ordinal hoặc kiểu native tùy cấu hình. Cần kiểm tra cách ánh xạ thực tế.

Với Java, nếu ứng dụng dùng enum, ưu tiên lưu tên hoặc mã chuỗi ổn định bằng mapping tường minh. JPA EnumType.STRING lưu tên hằng enum (Enum.name()), nên chỉ phù hợp trực tiếp khi tên hằng trùng với nhãn trong database. Nếu tên Java khác nhãn database hoặc cần mã lưu trữ ổn định riêng, hãy dùng AttributeConverter. Tránh EnumType.ORDINAL vì thứ tự khai báo enum trong source code có thể thay đổi và làm dữ liệu số cũ mang ý nghĩa khác.

Một enum Java có thể được viết như sau:

~~~java
public enum TicketStatus {
    NEW("new"),
    IN_PROGRESS("in_progress"),
    WAITING_CUSTOMER("waiting_customer"),
    RESOLVED("resolved"),
    CLOSED("closed");

    private final String databaseValue;

    TicketStatus(String databaseValue) {
        this.databaseValue = databaseValue;
    }

    public String databaseValue() {
        return databaseValue;
    }
}
~~~

Đây là ví dụ về mã lưu trữ tường minh. Cần cấu hình converter hoặc mapping tương ứng để JDBC/ORM thật sự dùng databaseValue; chỉ thêm method không tự thay đổi hành vi mặc định của JPA.

Nếu ứng dụng nhận dữ liệu từ API, không nên giả định mọi client được nâng cấp cùng lúc. API cần xử lý giá trị chưa biết một cách có chủ đích: từ chối với lỗi rõ ràng, giữ nguyên chuỗi nếu hợp đồng cho phép hoặc ánh xạ về trạng thái dự phòng phù hợp. Không âm thầm biến giá trị mới thành một trạng thái nghiệp vụ khác.

## 7. Các kiểm tra vận hành trước và sau DDL

Trước khi thay đổi:

~~~sql
SELECT VERSION() AS mysql_version,
       @@sql_mode AS sql_mode,
       @@autocommit AS autocommit_mode;

SHOW CREATE TABLE support_ticket;

SELECT status, COUNT(*) AS row_count
FROM support_ticket
GROUP BY status;
~~~

Kiểm tra kiểu cột và định nghĩa trong metadata:

~~~sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'support_ticket'
  AND COLUMN_NAME = 'status';
~~~

Ngay sau câu lệnh ALTER, hãy kiểm tra cảnh báo trước khi chạy câu SQL khác; SHOW WARNINGS hiển thị cảnh báo của câu lệnh gần nhất:

~~~sql
SHOW WARNINGS;

SHOW CREATE TABLE support_ticket;

SELECT status, status + 0 AS enum_index, COUNT(*) AS row_count
FROM support_ticket
GROUP BY status, status + 0
ORDER BY enum_index;
~~~

Với SET, có thể thống kê từng tổ hợp đang tồn tại. Nếu cần đếm từng thành viên riêng lẻ, tách thành viên bằng truy vấn hoặc xử lý dữ liệu phù hợp; không đếm số chuỗi SET như thể mỗi chuỗi là một thành viên độc lập.

Trong production, cần theo dõi metadata lock, thời gian ALTER, dung lượng tạm, I/O, replica lag và tỷ lệ lỗi ứng dụng. Tránh chạy migration thay đổi định nghĩa trên bảng lớn vào thời điểm tải cao khi chưa thử nghiệm trên dữ liệu đại diện.

## 8. Checklist quyết định kiểu dữ liệu

Trước khi chọn ENUM hoặc SET, hãy tự hỏi:

- [ ] Miền giá trị có nhỏ và ổn định trong vòng đời hệ thống không?
- [ ] Mỗi hàng cần đúng một lựa chọn (ENUM) hay một tập nhỏ các cờ độc lập (SET)?
- [ ] Giá trị có cần mô tả, bản dịch, thứ tự, ngày hiệu lực hoặc metadata riêng không?
- [ ] Có cần foreign key đến từng giá trị không?
- [ ] Nhiều dịch vụ hoặc client có thể phát triển độc lập không?
- [ ] Việc thêm/bỏ giá trị có thể triển khai qua migration được kiểm soát không?
- [ ] Truy vấn lọc, sắp xếp và thống kê có phù hợp với ngữ nghĩa ENUM/SET không?
- [ ] Ứng dụng có phụ thuộc vào ordinal hoặc bitmask không?

Nếu miền giá trị thay đổi thường xuyên, cần metadata riêng hoặc cần quan hệ khóa ngoại, hãy ưu tiên bảng danh mục hoặc bảng liên kết. Nếu danh sách nhỏ, ổn định và được kiểm soát chặt, ENUM/SET có thể là lựa chọn đơn giản và hiệu quả.

## 9. Bài tập thực hành

### Bài 1: Khám phá ENUM

Tạo bảng ticket với ENUM status. Thêm một số hàng, truy vấn status và status + 0, sau đó thử ORDER BY status và ORDER BY FIELD. Ghi nhận thứ tự khác nhau.

### Bài 2: Quan sát SQL mode

Thử ghi một giá trị không có trong danh sách ENUM ở chế độ strict và non-strict trong một database thực hành riêng. Chạy SHOW WARNINGS và quan sát chỉ số 0. Khôi phục SQL mode sau bài tập.

### Bài 3: Khám phá SET

Tạo cột SET gồm web, mobile và email. Thêm hàng có một và nhiều thành viên, truy vấn bằng FIND_IN_SET, rồi xem giá trị số bằng phép cộng 0. Thử nhập thành viên không hợp lệ và quan sát kết quả theo SQL mode.

### Bài 4: Thêm giá trị mới không làm gián đoạn code cũ

Thêm một thành viên mới vào cuối ENUM hoặc SET. Viết kiểm thử chứng minh dữ liệu cũ vẫn đọc được, DEFAULT không đổi và ứng dụng cũ không ghi giá trị mới. Lập kế hoạch triển khai ứng dụng trước khi cho phép ghi giá trị mới.

### Bài 5: Thay ENUM bằng bảng danh mục

Tạo bảng order_status, thêm cột status_code vào orders, backfill dữ liệu, xác minh phân bố và tạo foreign key. Lập các bước deploy ứng dụng tương thích trước khi loại bỏ cột ENUM cũ.

### Bài 6: Viết kế hoạch loại bỏ giá trị

Chọn một giá trị cũ đang được sử dụng. Viết kế hoạch kiểm kê dữ liệu, ánh xạ nghiệp vụ, backfill theo lô, xác nhận mọi consumer đã cập nhật, rồi mới loại giá trị khỏi định nghĩa. Ghi rõ cách xử lý nếu một bước thất bại.

## Kết luận

ENUM phù hợp với một lựa chọn đơn trong miền giá trị nhỏ, ổn định. SET phù hợp với một tập nhỏ các lựa chọn độc lập. Cả hai đều có quy tắc lưu trữ và thứ tự nội bộ cần hiểu rõ; thay đổi danh sách là thay đổi schema và phải được triển khai cùng dữ liệu, ứng dụng và các consumer liên quan.

Khi danh sách có vòng đời riêng, metadata phong phú, quan hệ khóa ngoại hoặc thay đổi thường xuyên, hãy chuyển sang bảng danh mục hay bảng liên kết. Một thiết kế tốt cần giữ được ý nghĩa dữ liệu qua nhiều lần phát hành, kể cả khi các phiên bản ứng dụng cũ và mới cùng hoạt động.

