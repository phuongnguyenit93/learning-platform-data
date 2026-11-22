# Luồng từ yêu cầu ứng dụng đến câu lệnh SQL và dữ liệu trên đĩa

Khi một chức năng ứng dụng cần lưu hoặc đọc dữ liệu, yêu cầu đó phải đi qua nhiều lớp trước khi trở thành thao tác vật lý trên thiết bị lưu trữ. Với MySQL, câu lệnh SQL là giao diện làm việc ở mức logic; phía sau nó là bộ phân tích cú pháp, bộ tối ưu hóa, bộ thực thi, giao diện với storage engine và các cấu trúc lưu trữ như chỉ mục, trang dữ liệu, bộ đệm và nhật ký giao dịch.

Hiểu được luồng này giúp lập trình viên kết nối yêu cầu nghiệp vụ với thiết kế bảng, kiểu dữ liệu, khóa, truy vấn, index và transaction. Nó cũng giúp giải thích vì sao một câu SQL có thể chạy nhanh hoặc chậm, vì sao dữ liệu đã được cập nhật trong bộ nhớ nhưng vẫn cần cơ chế bảo đảm độ bền, và vì sao việc đọc một hàng dữ liệu không nhất thiết tương ứng với một lần đọc đĩa.

Bài viết mô tả luồng phổ biến trong MySQL 8.x sử dụng InnoDB. Một số chi tiết có thể khác theo phiên bản, cấu hình, storage engine hoặc cách triển khai máy chủ.

## 1. Bắt đầu từ yêu cầu nghiệp vụ

Ứng dụng thường không bắt đầu bằng câu SQL. Nó bắt đầu bằng một hành động mà người dùng hoặc một hệ thống khác muốn thực hiện, chẳng hạn:

- Hiển thị thông tin một đơn hàng.
- Tạo đơn hàng mới và trừ số lượng tồn kho.
- Cập nhật địa chỉ giao hàng.
- Tìm các đơn hàng của một khách hàng trong một khoảng thời gian.

Yêu cầu nghiệp vụ cần được chuyển thành các thao tác dữ liệu rõ ràng. Trước khi viết SQL, cần xác định:

1. **Dữ liệu nào tham gia?** Ví dụ: khách hàng, đơn hàng, sản phẩm và chi tiết đơn hàng.
2. **Điều kiện nào phải đúng?** Ví dụ: sản phẩm còn đủ hàng, khách hàng tồn tại, đơn hàng thuộc về người đang đăng nhập.
3. **Những thay đổi nào phải cùng thành công hoặc cùng thất bại?** Ví dụ: tạo đơn hàng và giảm tồn kho phải nằm trong cùng một transaction.
4. **Kết quả nào cần trả về?** Ví dụ: mã đơn hàng, tổng tiền và trạng thái tạo đơn.
5. **Khối lượng và tần suất truy cập ra sao?** Thông tin này ảnh hưởng đến kiểu dữ liệu, chỉ mục và cách truy vấn.

Đây là điểm nối giữa phân tích nghiệp vụ và thiết kế cơ sở dữ liệu. Nếu mô hình dữ liệu không thể hiện đúng quan hệ hoặc ràng buộc, SQL phía sau sẽ phức tạp và dễ phát sinh lỗi.

## 2. Từ mô hình dữ liệu đến câu lệnh SQL

Giả sử hệ thống bán hàng cần lưu khách hàng, đơn hàng và các dòng sản phẩm trong đơn. Có thể mô hình hóa bằng ba bảng:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    email       VARCHAR(255) NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status      VARCHAR(30) NOT NULL,
    total       DECIMAL(13, 2) NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
    order_id   BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity   INT UNSIGNED NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders(order_id)
) ENGINE = InnoDB;
~~~

Ví dụ trên minh họa một số quyết định thiết kế:

- **BIGINT UNSIGNED** phù hợp với mã định danh không âm có thể tăng đến phạm vi lớn.
- **VARCHAR** lưu chuỗi có độ dài thay đổi; giới hạn độ dài nên dựa trên quy tắc nghiệp vụ.
- **DECIMAL** phù hợp với số tiền cần độ chính xác thập phân. Không nên dùng **FLOAT** hoặc **DOUBLE** để lưu số tiền cần so sánh và tính toán chính xác theo đơn vị tiền tệ.
- Khóa chính định danh duy nhất một hàng. Khóa ngoại thể hiện quan hệ và giúp InnoDB kiểm tra tính toàn vẹn tham chiếu.
- Chỉ mục ghép trên **(customer_id, created_at)** hỗ trợ các truy vấn lọc theo khách hàng và sắp xếp hoặc giới hạn theo thời gian, tùy hình dạng truy vấn.

Mô hình thực tế còn cần bảng sản phẩm, tồn kho, thanh toán và các ràng buộc phù hợp. Ví dụ này chỉ tập trung vào đường đi của yêu cầu qua MySQL.

Từ mô hình đó, một yêu cầu đọc danh sách đơn hàng của khách hàng có thể chuyển thành:

~~~sql
SELECT order_id, status, total, created_at
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC
LIMIT 20;
~~~

Dấu hỏi là tham số được truyền riêng khi dùng prepared statement. Ứng dụng không nên ghép trực tiếp dữ liệu đầu vào của người dùng vào chuỗi SQL. Truy vấn tham số hóa giúp tách câu lệnh khỏi dữ liệu, giảm nguy cơ SQL injection và làm rõ kiểu dữ liệu được truyền.

## 3. Ứng dụng gửi SQL đến MySQL như thế nào?

Ứng dụng thường giao tiếp với MySQL qua giao thức MySQL trên TCP/IP hoặc qua socket phù hợp với môi trường triển khai. Thư viện kết nối của ngôn ngữ lập trình đảm nhiệm việc đóng gói giao thức, gửi câu lệnh và đọc kết quả.

Một luồng phổ biến gồm:

1. Ứng dụng lấy một kết nối từ connection pool. Pool tái sử dụng các kết nối đã mở để tránh chi phí thiết lập kết nối liên tục.
2. Nếu cần, client và server thực hiện bắt tay giao thức, xác thực tài khoản và thương lượng các tùy chọn kết nối như mã hóa TLS.
3. Client gửi câu lệnh SQL hoặc gửi yêu cầu prepare rồi truyền các giá trị tham số ở bước execute.
4. MySQL xử lý yêu cầu trong ngữ cảnh phiên kết nối, bao gồm tài khoản, cơ sở dữ liệu mặc định, biến phiên và trạng thái transaction.
5. Server gửi kết quả, số hàng bị ảnh hưởng hoặc thông tin lỗi về client.

Ví dụ Java 15+ dùng JDBC (sử dụng text block):

~~~java
String sql = """
    SELECT order_id, status, total
    FROM orders
    WHERE customer_id = ?
    ORDER BY created_at DESC
    LIMIT 20
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            BigDecimal total = resultSet.getBigDecimal("total");
            // Chuyển dữ liệu sang đối tượng phục vụ tầng ứng dụng.
        }
    }
}
~~~

Tên phương thức và cách quản lý tài nguyên có thể khác giữa các thư viện. Điểm quan trọng là ứng dụng truyền giá trị qua tham số, quản lý vòng đời kết nối và đóng các đối tượng truy vấn đúng cách. Với connection pool, ứng dụng thường trả kết nối về pool thay vì tự đóng kết nối vật lý sau mỗi câu lệnh.

## 4. MySQL phân tích và kiểm tra câu lệnh

Sau khi nhận câu SQL, MySQL xử lý nó ở phía server. Có thể hình dung các bước chính như sau:

**Phân tích cú pháp (parsing):** server kiểm tra câu lệnh có đúng ngữ pháp SQL hay không và xây dựng cấu trúc biểu diễn nội bộ. Một lỗi cú pháp, chẳng hạn thiếu dấu phẩy hoặc dùng sai thứ tự mệnh đề, thường bị phát hiện ở bước này.

**Phân giải tên và kiểm tra ngữ nghĩa:** server xác định bảng, cột, hàm và các đối tượng được tham chiếu; kiểm tra kiểu sử dụng có hợp lệ hay không. Server cũng kiểm tra quyền của tài khoản đối với thao tác được yêu cầu. Tên bảng không tồn tại, cột không tồn tại hoặc tài khoản thiếu quyền có thể khiến câu lệnh thất bại trước khi truy cập dữ liệu.

**Chuẩn bị và tối ưu hóa:** server xác định các phương án thực thi có thể dùng. Với prepared statement, việc chuẩn bị câu lệnh và việc thực thi với giá trị tham số là các giai đoạn có phân biệt; việc tối ưu hóa cụ thể còn phụ thuộc loại statement, phiên bản và thông tin thống kê.

Không nên hiểu rằng MySQL chuyển nguyên văn câu SQL thành một lệnh đọc hoặc ghi đĩa. SQL mô tả kết quả logic mà ứng dụng muốn có. Server phải tìm cách thực hiện kết quả đó dựa trên cấu trúc dữ liệu, chỉ mục, thống kê và trạng thái hiện tại.

## 5. Bộ tối ưu hóa chọn kế hoạch thực thi

Một câu SELECT có thể có nhiều cách thực hiện. Bộ tối ưu hóa (optimizer) ước lượng chi phí của các phương án rồi chọn một kế hoạch thực thi. Những quyết định thường gặp gồm:

- Đọc toàn bộ bảng hay dùng một chỉ mục.
- Dùng chỉ mục nào và đọc bao nhiêu phần của chỉ mục.
- Thứ tự kết hợp các bảng trong truy vấn JOIN.
- Áp dụng điều kiện lọc ở bước nào.
- Có thể dùng chỉ mục để đáp ứng thứ tự sắp xếp hay vẫn phải thực hiện thao tác sort.
- Có thể lấy đủ các cột từ chỉ mục (covering index) hay phải truy cập thêm dữ liệu của hàng.

Với truy vấn:

~~~sql
SELECT order_id, status, total, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

Chỉ mục **(customer_id, created_at)** có thể giúp MySQL tìm vùng dữ liệu của khách hàng 42 và đọc theo thứ tự thời gian phù hợp. Tuy nhiên, optimizer vẫn phải dựa trên thống kê và chi phí ước lượng. Việc có một chỉ mục không bảo đảm chỉ mục đó luôn được chọn.

Có thể xem kế hoạch bằng:

~~~sql
EXPLAIN
SELECT order_id, status, total, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

Từ MySQL 8.0.18, **EXPLAIN ANALYZE** thực thi câu SELECT và báo thêm số liệu thực tế như thời gian và số hàng quan sát được ở các iterator. Chỉ dùng nó khi có thể chấp nhận truy vấn thực sự chạy trên dữ liệu hiện tại và tạo tải đọc tương ứng.

Kế hoạch tốt phụ thuộc vào truy vấn và phân bố dữ liệu. Khi phân tích hiệu năng, hãy so sánh số hàng ước lượng với số hàng thực tế, kiểm tra loại truy cập, thứ tự JOIN và lượng dữ liệu phải đọc. Đừng chỉ kết luận rằng truy vấn nhanh hay chậm dựa trên việc nó có dùng index hay không.

## 6. Bộ thực thi chuyển kế hoạch thành thao tác dữ liệu

Sau khi có kế hoạch, executor điều phối các bước thực thi. Với một truy vấn đọc, nó có thể yêu cầu storage engine tìm bản ghi theo chỉ mục, đọc các hàng phù hợp, kiểm tra điều kiện, kết hợp kết quả, sắp xếp hoặc giới hạn số hàng rồi chuyển dữ liệu lên server layer.

MySQL server layer không tự định nghĩa toàn bộ cách một engine lưu từng hàng. Nó làm việc với storage engine thông qua một giao diện nội bộ. Storage engine chịu trách nhiệm thực hiện các thao tác lưu trữ và nhiều cơ chế liên quan đến transaction.

Trong các hệ thống MySQL phổ biến, InnoDB là storage engine mặc định. InnoDB cung cấp transaction, khóa ở mức hàng, khóa ngoại, MVCC và cơ chế phục hồi sau sự cố. MySQL cũng có thể làm việc với engine khác, nhưng đặc tính và khả năng của từng engine không giống nhau.

## 7. InnoDB tìm dữ liệu trong bộ nhớ và trên đĩa

InnoDB tổ chức dữ liệu theo trang (page). Bảng và chỉ mục được lưu trong các cấu trúc trang, thường nằm trong tablespace. Một thao tác logic trên một hàng có thể cần đọc hoặc cập nhật nhiều trang liên quan.

### 7.1. Khóa chính và clustered index

Với bảng InnoDB có khóa chính, dữ liệu hàng được tổ chức trong clustered index theo khóa chính. Các nút lá của cấu trúc B+Tree chứa dữ liệu hàng. Vì vậy, tìm một hàng theo khóa chính thường là đi theo cây chỉ mục đến nút lá chứa hàng đó.

Nếu bảng không khai báo khóa chính, InnoDB chọn một khóa UNIQUE phù hợp không chứa cột NULL làm clustered index nếu có; nếu không có khóa như vậy, InnoDB tạo một định danh hàng nội bộ. Dù vậy, thiết kế bảng ứng dụng nên khai báo khóa chính rõ ràng.

### 7.2. Secondary index

Chỉ mục phụ (secondary index) có cấu trúc B+Tree riêng. Ở các nút lá, mục chỉ mục lưu giá trị cột được đánh chỉ mục cùng giá trị khóa chính của hàng. Khi truy vấn cần cột không có trong chỉ mục, InnoDB có thể dùng khóa chính tìm tiếp hàng trong clustered index.

Điều này giải thích vì sao một truy vấn dùng secondary index đôi khi phải thực hiện thêm bước tra cứu hàng. Nếu chỉ mục chứa đủ các cột cần thiết, truy vấn có thể được phục vụ ngay từ chỉ mục, được gọi là covering index. Chỉ mục giúp đọc nhanh hơn trong các trường hợp phù hợp nhưng cũng tốn dung lượng và làm tăng công việc khi INSERT, UPDATE hoặc DELETE.

### 7.3. Buffer pool và I/O

InnoDB dùng buffer pool để lưu các trang dữ liệu và chỉ mục thường được truy cập trong bộ nhớ. Khi cần một trang:

1. InnoDB kiểm tra trang có sẵn trong buffer pool hay không.
2. Nếu có, thao tác có thể tiếp tục đọc từ bộ nhớ.
3. Nếu chưa có, InnoDB yêu cầu đọc trang từ tablespace trên thiết bị lưu trữ vào buffer pool.
4. Sau khi trang được nạp, thao tác tiếp tục trên trang trong bộ nhớ.

Vì vậy, truy vấn có thể đọc dữ liệu mà không tạo ra I/O đĩa vật lý ở mỗi lần chạy. Ngược lại, một truy vấn quét nhiều trang hoặc làm việc trên tập dữ liệu vượt quá vùng nhớ hữu ích có thể gây nhiều I/O hơn.

Khi thay đổi dữ liệu, InnoDB thường sửa trang trong buffer pool trước. Trang đã thay đổi nhưng chưa được ghi về tablespace được gọi là dirty page. Các cơ chế ghi nền sẽ đưa dirty page xuống thiết bị lưu trữ theo chính sách của InnoDB. Việc ghi trang dữ liệu không nhất thiết xảy ra ngay tại thời điểm câu lệnh UPDATE trả kết quả.

## 8. Điều gì xảy ra khi ứng dụng ghi dữ liệu?

Xét thao tác giảm tồn kho và tạo đơn hàng. Các câu lệnh liên quan cần được đặt trong một transaction để tránh trạng thái chỉ một phần công việc được lưu:

~~~sql
START TRANSACTION;

UPDATE products
SET stock_quantity = stock_quantity - 2
WHERE product_id = 1001
  AND stock_quantity >= 2;

-- Ứng dụng phải kiểm tra số hàng bị ảnh hưởng.
-- Nếu không có hàng nào được cập nhật, cần hủy transaction.

INSERT INTO orders (customer_id, status, total)
VALUES (42, 'PENDING', 199.98);

-- Ứng dụng lấy mã đơn hàng vừa tạo rồi thêm order_items.

COMMIT;
~~~

Đây là ví dụ luồng nghiệp vụ, không phải một script hoàn chỉnh có thể chạy độc lập trong mọi schema. Ứng dụng cần kiểm tra kết quả UPDATE, xử lý lỗi, lấy mã đơn hàng và thực hiện ROLLBACK khi bất kỳ bước bắt buộc nào thất bại. Các câu lệnh phải chạy trên cùng một kết nối và trong cùng transaction.

Khi ghi, InnoDB thường thực hiện nhiều công việc phối hợp:

- Tìm trang chứa hàng hoặc vị trí chỉ mục cần thay đổi.
- Lấy các khóa cần thiết để bảo vệ dữ liệu và duy trì tính nhất quán.
- Ghi thông tin undo để hỗ trợ rollback và các phiên đọc nhất quán.
- Thay đổi trang trong buffer pool; các trang được sửa trở thành dirty page.
- Ghi redo log để có thể phát lại thay đổi cần thiết khi phục hồi sau sự cố.
- Kiểm tra ràng buộc như khóa chính, khóa UNIQUE và khóa ngoại.

Một thao tác UPDATE có thể làm thay đổi cả trang dữ liệu lẫn một hoặc nhiều trang chỉ mục. Nếu giá trị của cột được đánh chỉ mục thay đổi, các mục chỉ mục tương ứng cũng cần được cập nhật.

### 8.1. Undo log và MVCC

Undo log lưu thông tin cần thiết để hoàn tác thay đổi và xây dựng phiên bản hàng cũ phục vụ consistent read. InnoDB sử dụng MVCC (Multi-Version Concurrency Control) để các transaction đọc có thể quan sát một ảnh chụp dữ liệu phù hợp với quy tắc isolation đang áp dụng mà không phải khóa mọi hàng đang đọc.

Ví dụ, transaction A đang đọc một tập dữ liệu nhất quán trong khi transaction B cập nhật một hàng. Tùy isolation level và thời điểm tạo read view, A có thể tiếp tục nhìn thấy phiên bản cũ thông qua thông tin undo, trong khi B làm việc với phiên bản mới. Điều này giảm xung đột giữa một số thao tác đọc và ghi.

Undo log không phải bản sao lưu dài hạn. Khi không còn cần các phiên bản cũ cho transaction hoặc read view đang hoạt động, InnoDB có thể dọn dẹp chúng theo cơ chế purge.

### 8.2. Redo log và độ bền

Redo log ghi lại thông tin cần thiết để phục hồi thay đổi đã được ghi nhận khi hệ thống gặp sự cố trước khi tất cả dirty page được ghi xuống tablespace. Đây là cơ chế write-ahead logging: thông tin redo liên quan phải được ghi bền vững theo quy tắc cấu hình trước khi trang dữ liệu tương ứng được phép ghi xuống vị trí lưu trữ cuối cùng.

Nhờ vậy, InnoDB không cần buộc mọi trang dữ liệu liên quan phải được ghi xuống đĩa ngay trong thời điểm COMMIT. Khi khởi động lại sau sự cố, InnoDB có thể phát lại redo cần thiết để đưa dữ liệu về trạng thái nhất quán.

### 8.3. Binary log và phối hợp commit

MySQL có binary log (binlog) ở tầng server. Binlog ghi nhận các thay đổi dữ liệu theo định dạng và cấu hình được chọn, thường phục vụ replication và point-in-time recovery. Binlog có vai trò khác với redo log của InnoDB:

| Cơ chế | Vai trò chính |
|---|---|
| Undo log | Hoàn tác thay đổi và hỗ trợ đọc phiên bản cũ theo MVCC |
| Redo log | Phục hồi thay đổi của InnoDB sau sự cố |
| Binary log | Ghi nhận thay đổi ở tầng MySQL server, phục vụ replication và phục hồi theo thời điểm |

Khi binlog được bật và transaction thay đổi dữ liệu được commit, MySQL phối hợp trạng thái transaction của InnoDB với việc ghi binlog để hai phần có thể phục hồi nhất quán sau crash. Có thể hình dung đơn giản rằng InnoDB chuẩn bị transaction, MySQL ghi nhận transaction vào binlog theo cấu hình đồng bộ, rồi engine hoàn tất commit. Cơ chế nội bộ có các bước phối hợp chi tiết hơn và có thể dùng group commit để gom công việc đồng bộ.

Độ bền thực tế phụ thuộc vào cấu hình như **innodb_flush_log_at_trx_commit**, **sync_binlog**, hệ điều hành, bộ điều khiển lưu trữ và khả năng bảo đảm flush của thiết bị. Nếu yêu cầu là không mất transaction đã xác nhận khi máy chủ hoặc hệ điều hành gặp sự cố, cần hiểu và cấu hình các tùy chọn này có chủ đích. Không nên giả định rằng mọi cấu hình mặc định hoặc mọi thiết bị đều cung cấp cùng một mức độ bền.

## 9. COMMIT không có nghĩa mọi trang dữ liệu đã được ghi ngay

Đây là điểm quan trọng để hiểu đường đi từ SQL đến đĩa. Khi **COMMIT** trả về thành công, transaction đã được commit theo mức bảo đảm mà cấu hình và hệ thống lưu trữ cung cấp. Điều đó không có nghĩa tất cả trang dữ liệu đã được ghi ngay vào các file tablespace.

InnoDB có thể xác nhận commit sau khi các bản ghi log cần thiết đã được ghi bền vững theo cấu hình. Các dirty page còn lại được ghi xuống sau bởi các tiến trình nền và cơ chế quản lý checkpoint. Nếu xảy ra crash trước khi chúng được ghi, redo log hỗ trợ phục hồi.

Có thể phân biệt ba thời điểm:

- **Thay đổi trong bộ nhớ:** trang trong buffer pool được sửa.
- **Commit được xác nhận:** transaction hoàn tất theo quy tắc transaction và durability đang cấu hình.
- **Trang dữ liệu được ghi xuống tablespace:** dirty page được flush xuống thiết bị lưu trữ; thời điểm này có thể muộn hơn commit.

Phân biệt ba thời điểm này giúp tránh kết luận sai khi quan sát I/O, kiểm tra file dữ liệu hoặc điều tra hiệu năng ghi.

## 10. Kết quả quay về ứng dụng

Với câu lệnh đọc, sau khi executor nhận được các hàng phù hợp từ storage engine và hoàn tất các bước còn lại, server đóng gói kết quả theo giao thức MySQL rồi gửi về client. Driver chuyển các cột thành kiểu dữ liệu của ngôn ngữ lập trình để ứng dụng xử lý.

Với câu lệnh ghi, server trả trạng thái thành công hoặc lỗi, thường kèm số hàng bị ảnh hưởng và thông tin liên quan như mã định danh được tạo tự động. Ứng dụng cần kiểm tra kết quả này trước khi báo thành công cho người dùng.

Luồng tổng quát có thể tóm tắt như sau:

~~~text
Yêu cầu nghiệp vụ
       |
       v
Tầng ứng dụng: xác thực, kiểm tra dữ liệu, xác định transaction
       |
       v
Repository / DAO / Driver
       |
       v
Giao thức kết nối MySQL
       |
       v
MySQL Server: phân tích, kiểm tra quyền và ngữ nghĩa
       |
       v
Optimizer: chọn kế hoạch thực thi
       |
       v
Executor
       |
       v
Storage engine InnoDB
       |
       +---- Buffer pool: trang dữ liệu và chỉ mục trong bộ nhớ
       |
       +---- Undo / MVCC: phiên bản cũ và rollback
       |
       +---- Redo log: phục hồi thay đổi
       |
       +---- Tablespace: trang dữ liệu và chỉ mục trên lưu trữ
       |
       +---- Binary log ở tầng MySQL: replication và phục hồi theo thời điểm
       |
       v
Kết quả / trạng thái transaction trả về ứng dụng
~~~

Sơ đồ là mô hình khái niệm. Một số thành phần hoạt động đan xen hoặc bất đồng bộ; chẳng hạn việc flush dirty page có thể diễn ra sau khi transaction đã commit.

## 11. Đọc và ghi có đường đi khác nhau ở điểm nào?

| Khía cạnh | Truy vấn đọc | Thao tác ghi |
|---|---|---|
| Mục tiêu | Tìm và trả về dữ liệu thỏa điều kiện | Thay đổi dữ liệu và trạng thái chỉ mục |
| Kế hoạch | Chọn cách quét bảng, truy cập index, JOIN, lọc và sắp xếp | Tìm hàng cần đổi, kiểm tra ràng buộc và cập nhật các cấu trúc liên quan |
| Bộ nhớ | Có thể đọc trang từ buffer pool hoặc nạp từ tablespace | Thường sửa trang trong buffer pool và đánh dấu dirty |
| Transaction | Phụ thuộc isolation level và loại read | Cần quản lý khóa, undo, redo và commit/rollback |
| Nhật ký | Một SELECT thông thường không tạo thay đổi dữ liệu cần ghi redo như DML | InnoDB ghi undo/redo; binlog có thể ghi thay đổi theo cấu hình |
| Kết quả | Trả tập hàng hoặc metadata | Trả trạng thái, số hàng bị ảnh hưởng hoặc lỗi |

Một SELECT cũng có thể cần khóa trong một số trường hợp, chẳng hạn **SELECT ... FOR UPDATE**, và không phải mọi thao tác đọc đều có cùng hành vi. Ngược lại, thao tác ghi có thể đọc dữ liệu trước khi sửa để tìm hàng và kiểm tra điều kiện.

## 12. Những yếu tố làm thay đổi hiệu năng của luồng

Hiệu năng không chỉ phụ thuộc vào tốc độ ổ đĩa. Mỗi lớp có thể trở thành điểm nghẽn:

- **Tầng ứng dụng:** mở quá nhiều kết nối, giữ transaction quá lâu hoặc gửi truy vấn tuần tự không cần thiết làm tăng độ trễ.
- **Câu SQL:** lấy quá nhiều cột, lọc không chọn lọc, JOIN sai điều kiện hoặc trả về quá nhiều hàng làm tăng công việc.
- **Chỉ mục:** thiếu chỉ mục phù hợp có thể dẫn đến quét nhiều trang; quá nhiều chỉ mục làm tăng dung lượng và chi phí ghi.
- **Optimizer và thống kê:** thống kê không phản ánh tốt phân bố dữ liệu có thể khiến lựa chọn kế hoạch chưa phù hợp.
- **Khóa và transaction:** transaction dài hoặc cập nhật cùng một tập hàng có thể gây chờ khóa và deadlock.
- **Bộ nhớ và lưu trữ:** buffer pool không đủ cho tập dữ liệu hoạt động có thể làm tăng đọc đĩa; tốc độ ghi log và flush có thể giới hạn throughput của transaction.

Một quy trình điều tra hợp lý là:

1. Xác định chính xác câu SQL và tham số thực tế mà ứng dụng gửi.
2. Đo thời gian ở phía ứng dụng và phía MySQL để phân biệt độ trễ mạng, chờ pool, thời gian thực thi và thời gian xử lý kết quả.
3. Dùng **EXPLAIN** hoặc **EXPLAIN ANALYZE** phù hợp để hiểu kế hoạch và số hàng thực tế.
4. Kiểm tra chỉ mục, số hàng phải đọc, lượng dữ liệu trả về và trạng thái thống kê.
5. Kiểm tra transaction, lock wait, deadlock và thời gian giữ khóa.
6. Đánh giá buffer pool, I/O và cấu hình ghi log khi bằng chứng cho thấy chúng là điểm nghẽn.
7. Thay đổi từng yếu tố có giả thuyết rõ ràng rồi đo lại bằng dữ liệu đại diện.

Ví dụ, nếu truy vấn lọc theo **customer_id** nhưng phải quét toàn bảng, hãy kiểm tra chỉ mục và kiểu dữ liệu của điều kiện trước khi tăng tài nguyên máy chủ. Nếu truy vấn đã dùng chỉ mục nhưng vẫn chậm, hãy kiểm tra số lần tra cứu hàng, số hàng trả về, thứ tự sắp xếp và độ chọn lọc của điều kiện.

## 13. Các nhầm lẫn thường gặp

**“Một câu SQL tương ứng với một lần đọc đĩa.”** Không đúng. Một câu SQL có thể cần nhiều trang; các trang có thể đã ở trong buffer pool. Một thao tác đọc logic không đồng nghĩa một I/O vật lý.

**“Có index là truy vấn chắc chắn nhanh.”** Không đúng. Index có chi phí duy trì và chỉ hữu ích khi phù hợp với điều kiện, thứ tự truy cập và lượng dữ liệu cần lấy. Optimizer có thể chọn quét bảng nếu phương án đó rẻ hơn.

**“COMMIT xong là toàn bộ dữ liệu đã được ghi vào file bảng.”** Không đúng. Commit dựa trên cơ chế log và cấu hình durability; dirty page có thể được flush sau.

**“MySQL server tự lưu từng hàng.”** Cần phân biệt server layer và storage engine. MySQL server tiếp nhận và điều phối SQL; InnoDB thực hiện nhiều chức năng lưu trữ, khóa, transaction và phục hồi.

**“Rollback chỉ cần xóa câu SQL vừa chạy.”** Không đúng. Rollback là một phần của cơ chế transaction; InnoDB sử dụng thông tin undo và trạng thái transaction để hoàn tác các thay đổi phù hợp.

**“Mọi transaction đều tự động bảo đảm cùng mức độ bền trên mọi máy chủ.”** Không đúng. Mức độ bền còn phụ thuộc cấu hình MySQL và khả năng flush thực tế của hệ thống lưu trữ.

## 14. Cách vận dụng khi phát triển tính năng

Khi triển khai một tính năng mới dùng MySQL, hãy đi theo chuỗi câu hỏi sau:

1. **Yêu cầu:** thao tác nghiệp vụ cần đọc hoặc thay đổi dữ liệu nào?
2. **Mô hình:** bảng, kiểu dữ liệu, khóa chính, khóa ngoại và ràng buộc nào biểu diễn đúng dữ liệu?
3. **SQL:** câu lệnh nào thực hiện thao tác; tham số nào được truyền riêng?
4. **Transaction:** những thay đổi nào phải cùng commit; lỗi ở bước nào cần rollback?
5. **Kế hoạch:** MySQL có thể dùng index nào; cần kiểm tra bằng EXPLAIN ra sao?
6. **Lưu trữ:** InnoDB cần đọc hoặc sửa các trang nào; thao tác có ảnh hưởng đến index và khóa không?
7. **Độ bền:** cấu hình redo log, binlog và chính sách sao lưu có đáp ứng yêu cầu vận hành không?
8. **Phản hồi:** ứng dụng cần kiểm tra số hàng bị ảnh hưởng và chuyển lỗi MySQL thành phản hồi nghiệp vụ như thế nào?

Khi hiểu chuỗi này, việc tối ưu không còn dừng ở sửa một câu SQL. Có thể lần theo đúng lớp gây ra vấn đề: thiết kế dữ liệu, cách ứng dụng gửi truy vấn, kế hoạch thực thi, chỉ mục, transaction, bộ nhớ hay lưu trữ.

## Kết luận

Một yêu cầu ứng dụng đi qua tầng nghiệp vụ, driver và giao thức kết nối trước khi được MySQL phân tích, kiểm tra, tối ưu hóa và thực thi. Executor phối hợp với storage engine; với InnoDB, dữ liệu và chỉ mục được tổ chức thành các trang, được truy cập qua buffer pool và được bảo vệ bởi transaction, MVCC, undo log và redo log. Binary log hỗ trợ replication và phục hồi theo thời điểm. Kết quả hoặc trạng thái commit sau đó được trả về ứng dụng.

Nắm được luồng từ yêu cầu đến SQL và dữ liệu trên đĩa là nền tảng để học sâu hơn về thiết kế bảng, index, transaction, khóa, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành MySQL.
