# Unknown database/table/column và phân biệt lỗi tên với thiếu quyền

Các lỗi Unknown database, Table doesn't exist và Unknown column thường xuất hiện khi ứng dụng truy vấn sai tên hoặc schema chưa được triển khai đúng. Tuy nhiên, lỗi Access denied, SELECT command denied hay UPDATE command denied có nguyên nhân khác: tài khoản MySQL không có quyền thực hiện thao tác. Phân biệt đúng hai nhóm lỗi giúp tránh sửa schema không cần thiết hoặc cấp quyền quá rộng để che giấu lỗi cấu hình.

Quy trình chẩn đoán nên bắt đầu bằng việc xác nhận server, tài khoản, database mặc định và câu SQL thực tế. Sau đó kiểm tra sự tồn tại của database/table/column bằng metadata mà tài khoản hiện tại được phép xem, rồi mới kiểm tra grants. Một lỗi có thể phát sinh từ sai môi trường, sai chữ hoa/chữ thường, thiếu migration, sai alias hoặc quyền bị giới hạn ở cấp database, table hay column.

Bài học thuộc chương **Xử lý sự cố** của module DATABASE_MYSQL. Module bao quát thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Ví dụ tập trung vào MySQL 8.0, InnoDB và tài khoản ứng dụng có quyền tối thiểu.

Sau bài học, bạn có thể:

- Phân biệt lỗi database/table/column không tồn tại với lỗi thiếu quyền.
- Đọc mã lỗi MySQL, SQLState và ngữ cảnh phát sinh.
- Xác nhận database hiện tại, server và account thực sự được MySQL chọn.
- Kiểm tra tên object, metadata, chữ hoa/chữ thường và câu SQL.
- Phát hiện migration chưa chạy hoặc ứng dụng đang kết nối nhầm môi trường.
- Đọc grants và xác định quyền thiếu ở cấp database, table hoặc column.
- Sửa lỗi theo nguyên tắc least privilege và kiểm chứng lại bằng account ứng dụng.
- Tránh các cách xử lý làm lộ dữ liệu hoặc cấp quyền vượt nhu cầu.

## 1. Nhận diện hai nhóm lỗi

Khi MySQL báo lỗi, không nên chỉ đọc phần message. Hãy ghi nhận ít nhất:

- Mã lỗi MySQL (vendor error code).
- SQLState.
- Câu SQL đã thực thi, sau khi loại bỏ dữ liệu nhạy cảm.
- Database mặc định và host/server mà connection đang dùng.
- Account MySQL được xác thực và account mà MySQL dùng để kiểm tra quyền.
- Thời điểm, phiên bản ứng dụng và phiên bản schema đang triển khai.

Các lỗi định danh phổ biến:

| Mã lỗi | SQLState thường gặp | Thông báo | Ý nghĩa chính |
|---|---|---|---|
| 1046 | 3D000 | No database selected | Connection chưa chọn database mặc định và câu SQL không chỉ rõ schema. |
| 1049 | 42000 | Unknown database | Tên database được yêu cầu không tồn tại hoặc không được nhận diện trên server đó. |
| 1054 | 42S22 | Unknown column | Cột được tham chiếu không tồn tại trong ngữ cảnh câu SQL. |
| 1146 | 42S02 | Table doesn't exist | Table hoặc view được tham chiếu không tồn tại trong schema đã xác định. |

Các lỗi quyền phổ biến:

| Mã lỗi | SQLState thường gặp | Thông báo | Ý nghĩa chính |
|---|---|---|---|
| 1044 | 42000 | Access denied for user to database | Account không có quyền truy cập database được yêu cầu. |
| 1045 | 28000 | Access denied for user | Xác thực thất bại hoặc account/host/password/plugin không phù hợp. |
| 1142 | 42000 | Command denied to user for table | Thiếu quyền thực hiện lệnh trên table. |
| 1143 | 42000 | Command denied to user for column | Thiếu quyền thực hiện lệnh trên column cụ thể. |
| 1227 | 42000 | Access denied; need privilege | Thao tác cần một privilege quản trị hoặc đặc quyền cụ thể. |

Mã lỗi và SQLState trên là các trường hợp MySQL thường gặp. Lỗi có thể được bọc trong exception của JDBC, ORM hoặc framework; hãy xem cả exception cause và thông tin lỗi gốc thay vì chỉ đọc message ngoài cùng.

**Quy tắc ban đầu:** Unknown ... thường hướng tới tên object, schema, ngữ cảnh truy vấn hoặc phiên bản cấu trúc; Access denied/command denied hướng tới xác thực hoặc quyền. Tuy vậy, không kết luận chỉ từ một chuỗi message. Cần xác nhận đúng server, account và metadata.

## 2. Bắt đầu bằng xác nhận server và session

Một trong những nguyên nhân dễ bị bỏ qua là ứng dụng đang kết nối nhầm MySQL instance hoặc nhầm database. Ví dụ, migration đã chạy trên staging nhưng ứng dụng lại kết nối tới một server development khác; hoặc biến môi trường của pod mới chưa được cập nhật.

Chạy truy vấn chẩn đoán trên chính connection gặp lỗi:

~~~sql
SELECT
  VERSION() AS mysql_version,
  @@hostname AS server_hostname,
  @@port AS server_port,
  @@server_uuid AS server_uuid,
  DATABASE() AS current_database,
  USER() AS login_identity,
  CURRENT_USER() AS privilege_identity;
~~~

Ý nghĩa:

- VERSION() cho biết phiên bản MySQL Server.
- @@hostname, @@port và @@server_uuid giúp nhận diện server.
- DATABASE() trả về database mặc định hiện tại; kết quả NULL nghĩa là session chưa chọn database.
- USER() cho biết user và host mà client dùng khi kết nối.
- CURRENT_USER() cho biết account MySQL được chọn để kiểm tra quyền.

USER() và CURRENT_USER() có thể khác nhau. MySQL chọn account theo quy tắc khớp user/host; khi kiểm tra grants, CURRENT_USER() là thông tin quan trọng hơn. Một account cùng tên nhưng host khác nhau có thể có quyền khác nhau.

Trong JDBC, có thể kiểm tra thêm:

~~~java
try (Connection connection = dataSource.getConnection()) {
    System.out.println("Catalog: " + connection.getCatalog());
    System.out.println("Schema: " + connection.getSchema());
    System.out.println("Auto commit: " + connection.getAutoCommit());
}
~~~

Đừng in password hoặc toàn bộ JDBC URL nếu URL có chứa secret. Khi cần đối chiếu môi trường, log hostname, port, database và một định danh cấu hình không nhạy cảm.

## 3. Lỗi No database selected (1046)

Lỗi 1046 xuất hiện khi câu SQL dùng tên table không kèm schema, nhưng connection chưa chọn database mặc định.

Ví dụ:

~~~sql
SELECT * FROM orders;
~~~

Nếu session chưa chạy USE sales, server không biết cần tìm table orders trong database nào.

Kiểm tra:

~~~sql
SELECT DATABASE();
~~~

Nếu kết quả là NULL, có thể chọn database:

~~~sql
USE sales;
SELECT * FROM orders;
~~~

Hoặc ghi rõ schema trong câu SQL:

~~~sql
SELECT * FROM sales.orders;
~~~

Cách ghi rõ schema hữu ích cho ứng dụng có nhiều database, job nền hoặc connection pool. Nó giảm sự phụ thuộc vào database mặc định của session. Tuy nhiên, tên schema phải đúng với môi trường và tài khoản phải có quyền truy cập.

Với JDBC, database thường được đặt trong JDBC URL:

~~~text
jdbc:mysql://mysql.example.internal:3306/sales
~~~

Nếu URL không có database hoặc pool thay đổi catalog sau khi connection được tạo, câu SQL không qualify schema có thể phát sinh 1046. Kiểm tra Connection.getCatalog() và cấu hình DataSource.

## 4. Lỗi Unknown database (1049)

Ví dụ:

~~~sql
USE sales_prod;
~~~

Nếu server trả Unknown database 'sales_prod', hãy xác minh:

1. Tên database có chính xác không.
2. Connection có trỏ tới đúng server không.
3. Database có được tạo trên môi trường này chưa.
4. Deployment/migration có chạy thành công không.
5. Tên database có khác chữ hoa/chữ thường trên hệ điều hành đích không.
6. Tài khoản và cách kiểm tra metadata có đủ quyền để nhìn thấy database không.

Kiểm tra danh sách database mà account hiện tại được phép nhìn thấy:

~~~sql
SHOW DATABASES;
~~~

Có thể truy vấn metadata:

~~~sql
SELECT SCHEMA_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'sales_prod';
~~~

Không thấy database trong kết quả SHOW DATABASES không luôn chứng minh database chưa tồn tại. MySQL giới hạn khả năng nhìn thấy metadata theo quyền của account. Nếu nghi ngờ thiếu quyền, nhờ DBA xác nhận sự tồn tại của schema bằng account quản trị và so sánh với CURRENT_USER() của ứng dụng.

Phân biệt:

- 1049: server không nhận diện database được chỉ định.
- 1044: database được yêu cầu nhưng account không được phép truy cập.
- 1045: không xác thực được account/host hoặc thông tin đăng nhập.

Không tạo database mới ngay khi gặp 1049. Nếu ứng dụng đang trỏ nhầm server hoặc sai tên, tạo schema trùng tên ở nơi không đúng có thể khiến sự cố phức tạp hơn.

## 5. Lỗi Table doesn't exist (1146)

Ví dụ:

~~~sql
SELECT order_id, status
FROM sales.orders;
~~~

Nếu sales.orders không tồn tại, MySQL có thể trả lỗi 1146. Các nguyên nhân thường gặp:

- Sai tên database hoặc table.
- Table chưa được tạo bởi migration.
- Ứng dụng kết nối nhầm môi trường hoặc nhầm replica.
- Migration thất bại một phần hoặc chưa được triển khai.
- Table đã được đổi tên/xóa trong một đợt release.
- Table là temporary table nhưng đã ra khỏi session tạo nó.
- Khác biệt chữ hoa/chữ thường giữa hệ điều hành nguồn và đích.

Kiểm tra tên table:

~~~sql
SHOW FULL TABLES FROM sales;
~~~

Hoặc truy vấn metadata:

~~~sql
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  TABLE_TYPE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders';
~~~

TABLE_TYPE giúp phân biệt BASE TABLE và VIEW. Một view có thể bị thiếu hoặc invalid do dependency, nhưng lỗi object cần được điều tra từ DDL và dependency của view.

Nếu table không xuất hiện, xác nhận account có quyền nhìn thấy metadata. information_schema chỉ cung cấp metadata mà account được phép truy cập; kết quả rỗng không luôn phân biệt được object không tồn tại với metadata bị giới hạn.

### 5.1. Temporary table và phạm vi session

Temporary table chỉ tồn tại trong session đã tạo nó:

~~~sql
CREATE TEMPORARY TABLE tmp_order_ids (
  order_id BIGINT PRIMARY KEY
);
~~~

Nếu tạo temporary table trên một connection rồi truy vấn trên connection khác từ pool, connection thứ hai sẽ không thấy table đó và có thể báo 1146.

Điều này thường xảy ra khi code lấy hai connection riêng cho hai bước, hoặc trả connection về pool giữa lúc tạo và sử dụng temporary table.

Giữ cùng Connection trong toàn bộ phạm vi sử dụng temporary table:

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Tạo temporary table.
    // Nạp dữ liệu.
    // Truy vấn temporary table.
    // Đóng connection sau khi hoàn tất.
}
~~~

Không lưu tên temporary table vào biến toàn cục rồi giả định mọi connection đều nhìn thấy nó.

## 6. Chữ hoa/chữ thường của database và table

Tên database và table có thể phân biệt chữ hoa/chữ thường tùy hệ điều hành và cấu hình lower_case_table_names.

Kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'lower_case_table_names';
~~~

Các giá trị thường gặp:

| Giá trị | Hành vi tổng quát |
|---|---|
| 0 | Lưu tên theo cách khai báo và so sánh phân biệt chữ hoa/chữ thường; thường gặp trên hệ thống Unix/Linux với filesystem phân biệt hoa thường. |
| 1 | Lưu tên ở dạng chữ thường và so sánh không phân biệt hoa thường; thường gặp trên Windows. |
| 2 | Lưu tên theo cách khai báo nhưng so sánh dạng chữ thường; có thể gặp trên filesystem không phân biệt hoa thường khi nền tảng hỗ trợ. |

Hành vi chính xác phụ thuộc nền tảng và phiên bản. Trong MySQL 8.0, lower_case_table_names là thiết lập cần được xác định khi khởi tạo data directory; không tự ý thay đổi trên server đã có dữ liệu để sửa lỗi tên. Thay đổi cấu hình này có thể không được hỗ trợ hoặc gây sai lệch tên object.

Khuyến nghị:

- Dùng một quy ước tên database/table thống nhất, thường là chữ thường.
- Giữ nguyên cách viết tên object trong DDL, migration và code.
- Kiểm tra cấu hình nguồn và đích trước khi chuyển môi trường.
- Thử migration trên cùng loại hệ điều hành/filesystem với production.
- Không tạo hai table chỉ khác chữ hoa/chữ thường với kỳ vọng hoạt động giống nhau trên mọi nền tảng.

Tên column và index không chịu cùng quy tắc filesystem như tên database/table; dù vậy, luôn dùng đúng tên được khai báo để tránh lỗi do typo hoặc khác biệt trong SQL được sinh ra.

## 7. Lỗi Unknown column (1054)

Ví dụ:

~~~sql
SELECT order_id, customer_nmae
FROM sales.orders;
~~~

Nếu table có customer_name nhưng không có customer_nmae, MySQL trả Unknown column ... in field list.

Kiểm tra cấu trúc table:

~~~sql
SHOW COLUMNS FROM sales.orders;
~~~

Hoặc:

~~~sql
SHOW CREATE TABLE sales.orders;
~~~

Có thể truy vấn metadata column:

~~~sql
SELECT
  COLUMN_NAME,
  DATA_TYPE,
  IS_NULLABLE,
  COLUMN_DEFAULT,
  ORDINAL_POSITION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

Đối chiếu tên column với DDL thật. Đừng chỉ dựa vào tên field trong DTO, entity hoặc tài liệu cũ.

### 7.1. Alias không dùng được ở mọi vị trí

Một lỗi 1054 phổ biến là tham chiếu alias trong mệnh đề WHERE:

~~~sql
SELECT
  total_amount * 1.1 AS amount_with_tax
FROM sales.orders
WHERE amount_with_tax > 100;
~~~

Trong MySQL, alias của select list không được dùng trong WHERE cùng cấp theo cách trên vì WHERE được xử lý trước khi select expression tạo alias.

Viết lại biểu thức:

~~~sql
SELECT
  total_amount * 1.1 AS amount_with_tax
FROM sales.orders
WHERE total_amount * 1.1 > 100;
~~~

Hoặc dùng derived table:

~~~sql
SELECT amount_with_tax
FROM (
  SELECT total_amount * 1.1 AS amount_with_tax
  FROM sales.orders
) AS calculated
WHERE amount_with_tax > 100;
~~~

Alias có thể được dùng ở một số mệnh đề khác như ORDER BY, GROUP BY và HAVING theo quy tắc MySQL. Khi truy vấn phức tạp, kiểm tra đúng scope của alias và tên cột.

### 7.2. Tên column trùng hoặc thiếu qualifier

Khi join nhiều table, qualify column để tránh mơ hồ:

~~~sql
SELECT
  o.order_id,
  c.customer_name
FROM sales.orders AS o
JOIN sales.customers AS c
  ON c.customer_id = o.customer_id;
~~~

Nếu viết customer_name nhưng column nằm trong table khác hoặc alias table không đúng, MySQL có thể báo unknown column. Kiểm tra alias khai báo trong FROM và JOIN, không chỉ tên cột.

Ví dụ sai:

~~~sql
SELECT o.order_id
FROM sales.orders AS o
WHERE orders.status = 'PAID';
~~~

Sau khi khai báo alias o, dùng alias đó:

~~~sql
SELECT o.order_id
FROM sales.orders AS o
WHERE o.status = 'PAID';
~~~

### 7.3. Identifier và string literal

MySQL dùng dấu nháy đơn cho string literal và backtick để quote identifier:

~~~sql
SELECT `order_id`, `status`
FROM `sales`.`orders`
WHERE `status` = 'PAID';
~~~

Không viết:

~~~sql
SELECT 'order_id'
FROM sales.orders;
~~~

'order_id' là một string literal, không phải tên column. Tùy câu lệnh, nó có thể trả về chuỗi cố định thay vì dữ liệu trong cột.

Dấu nháy kép thường được dùng cho string; nếu bật ANSI_QUOTES, dấu nháy kép được diễn giải là identifier. Để SQL rõ ràng và ít phụ thuộc SQL mode, dùng backtick cho identifier cần quote và nháy đơn cho string literal.

## 8. Sai tên do migration chưa chạy hoặc chạy lệch phiên bản

Ứng dụng có thể đã được deploy với code truy vấn column mới nhưng database chưa được migrate.

Ví dụ code mới chạy:

~~~sql
SELECT order_id, fulfillment_status
FROM sales.orders;
~~~

Trong khi schema đích vẫn chỉ có column status. Kết quả là 1054. Đây là lỗi lệch phiên bản code/schema, không phải thiếu quyền.

Quy trình xác minh:

1. Xác nhận server và database bằng @@server_uuid, @@hostname và DATABASE().
2. Kiểm tra SHOW CREATE TABLE sales.orders.
3. Xác định migration tạo fulfillment_status đã chạy trên đúng database chưa.
4. Kiểm tra migration log/status từ công cụ triển khai mà đội dự án đang dùng.
5. Xem ứng dụng và migration có được release theo đúng thứ tự không.
6. Kiểm tra replica nếu truy vấn đọc đang được định tuyến tới replica có thể chưa apply DDL.

Không sửa bằng cách thêm column thủ công vào production nếu migration chính thức vẫn chưa được xác định. Thao tác thủ công có thể khiến migration sau đó thất bại vì object đã tồn tại hoặc schema drift giữa các môi trường.

### 8.1. Schema evolution an toàn

Với thay đổi schema cần hỗ trợ nhiều phiên bản ứng dụng:

- Thêm column mới ở trạng thái tương thích trước.
- Deploy code có thể làm việc với cả cấu trúc cũ và mới.
- Chạy backfill nếu cần.
- Chuyển đọc/ghi sang column mới.
- Chỉ xóa column cũ sau khi không còn phiên bản ứng dụng nào phụ thuộc.

Trình tự này giảm lỗi unknown column trong thời gian rolling deployment. Không deploy code phụ thuộc column mới trước khi DDL tương ứng đã sẵn sàng trên mọi database endpoint mà code có thể truy cập.

## 9. Phân biệt lỗi tên với lỗi thiếu quyền

Đây là phần quan trọng nhất khi chẩn đoán. Hãy so sánh message, mã lỗi, thao tác và account:

| Thao tác | Lỗi định danh thường gặp | Lỗi quyền thường gặp |
|---|---|---|
| USE sales | 1049 Unknown database | 1044 Access denied to database |
| SELECT ... FROM sales.orders | 1146 Table doesn't exist | 1142 SELECT command denied for table |
| SELECT secret_col FROM sales.orders | 1054 Unknown column | 1143 SELECT command denied for column |
| UPDATE sales.orders ... | 1146 nếu table không tồn tại | 1142 UPDATE command denied for table hoặc 1143 ở cấp column |
| CREATE TABLE sales.t ... | Lỗi tên/schema hoặc cú pháp tùy ngữ cảnh | 1044/1142/1227 tùy quyền cần thiết |

Lỗi quyền thường nói rõ command và object bị từ chối. Ví dụ:

~~~text
ERROR 1142 (42000): SELECT command denied to user 'app'@'10.%' for table 'orders'
~~~

Điều này cho biết MySQL nhận diện được đối tượng cần truy cập nhưng account hiện tại không có quyền SELECT theo phạm vi cần thiết.

Lỗi column-level có thể giống:

~~~text
ERROR 1143 (42000): SELECT command denied to user 'app'@'10.%' for column 'salary' in table 'employees'
~~~

Trong trường hợp này, account có thể được phép đọc một số column nhưng không được đọc column nhạy cảm.

Không cố tình suy luận sự tồn tại của object chỉ từ một thông báo lỗi trong mọi cấu hình bảo mật. Hãy xác minh bằng DBA hoặc account có quyền phù hợp, đồng thời giữ nguyên nguyên tắc không cấp thêm quyền cho account ứng dụng chỉ để kiểm tra.

## 10. Xác định account MySQL thực sự được áp dụng

MySQL account có dạng 'user'@'host'. Hai account cùng username nhưng khác host là hai account khác nhau, có thể có grants khác nhau.

Kiểm tra:

~~~sql
SELECT
  USER() AS client_identity,
  CURRENT_USER() AS matched_account;
~~~

Ví dụ client kết nối từ 10.20.1.15 với username app, nhưng MySQL có thể chọn account 'app'@'10.%', 'app'@'%' hoặc một account host cụ thể hơn. Quyền phải được kiểm tra trên account được match.

Xem grants hiện tại:

~~~sql
SHOW GRANTS;
~~~

Hoặc:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

Nếu dùng role, kiểm tra role đang hoạt động:

~~~sql
SELECT CURRENT_ROLE();
~~~

Một role đã được grant cho account chưa chắc đang active trong session nếu cấu hình default role hoặc câu lệnh SET ROLE không như dự kiến. Vì vậy, đối chiếu cả grants và active roles.

Không yêu cầu người vận hành gửi mật khẩu, hash mật khẩu hoặc file secret để chẩn đoán. Chỉ cần thông tin account identity, host, grants đã được làm sạch dữ liệu nhạy cảm và mã lỗi.

## 11. Hiểu phạm vi quyền MySQL

MySQL hỗ trợ quyền ở nhiều phạm vi:

| Phạm vi | Ví dụ | Ý nghĩa |
|---|---|---|
| Global | ON *.* | Áp dụng toàn server cho các object thuộc quyền đó. |
| Database | ON sales.* | Áp dụng các object trong database sales. |
| Table | ON sales.orders | Áp dụng trên table cụ thể. |
| Column | ON sales.employees (salary) | Áp dụng trên column cụ thể cho các privilege hỗ trợ phạm vi column. |
| Routine | ON PROCEDURE sales.recalculate | Quyền như EXECUTE/ALTER ROUTINE trên routine theo hỗ trợ. |
| Dynamic privilege | Quyền quản trị riêng | Phạm vi và tên phụ thuộc phiên bản MySQL. |

Ví dụ account chỉ được đọc database sales:

~~~sql
GRANT SELECT
ON sales.*
TO 'sales_reader'@'10.%';
~~~

Ví dụ chỉ cho phép đọc một table:

~~~sql
GRANT SELECT
ON sales.orders
TO 'order_reader'@'10.%';
~~~

Ví dụ cấp quyền đọc một số column:

~~~sql
GRANT SELECT (employee_id, display_name)
ON hr.employees
TO 'directory_reader'@'10.%';
~~~

Cú pháp và privilege có thể cần điều chỉnh theo loại object, phiên bản và account thực tế. Lệnh GRANT phải do DBA hoặc account có quyền quản trị tương ứng thực hiện.

Không cấp ALL PRIVILEGES ON *.* để sửa lỗi 1142/1143. Hãy xác định đúng thao tác, database/table/column và cấp quyền tối thiểu cần thiết.

## 12. Đọc SHOW GRANTS và tìm quyền thiếu

Ví dụ kết quả:

~~~sql
SHOW GRANTS FOR 'sales_app'@'10.%';
~~~

Có thể thấy:

~~~sql
GRANT USAGE ON *.* TO `sales_app`@`10.%`;
GRANT SELECT, INSERT, UPDATE ON `sales`.* TO `sales_app`@`10.%`;
~~~

Account trên có thể đọc, thêm và cập nhật object trong database sales, nhưng không có DELETE nếu chưa được cấp. Nếu ứng dụng chạy DELETE FROM sales.orders, lỗi quyền là hợp lý.

Đối chiếu quyền theo operation:

- SELECT: đọc dữ liệu.
- INSERT: thêm hàng.
- UPDATE: cập nhật dữ liệu; column-level privilege có thể giới hạn các cột được sửa.
- DELETE: xóa hàng.
- CREATE/ALTER/DROP: thay đổi cấu trúc database/table.
- INDEX: tạo hoặc xóa index.
- REFERENCES: tạo foreign key tham chiếu trong các trường hợp cần privilege này.
- EXECUTE: gọi stored procedure/function.
- TRIGGER: tạo hoặc xóa trigger.

Một câu lệnh có thể cần nhiều quyền. Ví dụ INSERT ... ON DUPLICATE KEY UPDATE cần quyền INSERT và UPDATE phù hợp. CREATE TABLE ... SELECT có thể cần quyền tạo table và đọc dữ liệu nguồn.

Kiểm tra quyền theo đúng SQL thực tế thay vì suy luận chỉ từ tên màn hình chức năng.

## 13. Sửa lỗi quyền theo nguyên tắc least privilege

Quy trình cấp quyền:

1. Xác định account bằng CURRENT_USER().
2. Xác định thao tác bị từ chối và object cụ thể.
3. Xác định quyền ở phạm vi nhỏ nhất có thể.
4. Xác nhận host pattern đúng với ứng dụng.
5. Nhờ DBA cấp quyền trên đúng database/table/column.
6. Mở connection mới hoặc làm mới role/session nếu cần.
7. Kiểm tra lại bằng chính account ứng dụng.
8. Ghi lại lý do và phạm vi quyền được cấp.

Ví dụ, nếu service cần SELECT và UPDATE trên sales.orders:

~~~sql
GRANT SELECT, UPDATE
ON sales.orders
TO 'sales_app'@'10.%';
~~~

Nếu service cần INSERT thêm đơn hàng:

~~~sql
GRANT INSERT
ON sales.orders
TO 'sales_app'@'10.%';
~~~

Không cấp quyền CREATE, ALTER hoặc DROP cho account runtime chỉ vì ứng dụng có một luồng migration. Nên dùng account migration riêng, chỉ được cấp quyền DDL trong cửa sổ triển khai và được quản lý như secret đặc quyền.

### 13.1. Quyền column-level

Giả sử account được phép xem employee_id và display_name, nhưng không được đọc salary. Query:

~~~sql
SELECT employee_id, salary
FROM hr.employees;
~~~

có thể trả 1143 vì thiếu SELECT trên column salary. Không nên cấp SELECT toàn table nếu nghiệp vụ chỉ cần một số cột. Hãy điều chỉnh query để chỉ lấy các column được phép hoặc yêu cầu DBA cấp đúng quyền nếu có lý do nghiệp vụ và phê duyệt bảo mật.

Tương tự, UPDATE column nhạy cảm cần được giới hạn. Quyền ở mức table rộng hơn quyền ở mức column; hãy hiểu grants hiện tại trước khi đề xuất thay đổi.

## 14. Phân biệt lỗi xác thực 1045

1045 thường xảy ra trước khi ứng dụng thực hiện câu SQL. Ví dụ:

~~~text
ERROR 1045 (28000): Access denied for user 'sales_app'@'10.20.1.15' (using password: YES)
~~~

Các nguyên nhân có thể:

- Password sai hoặc secret đã rotate nhưng ứng dụng chưa nhận giá trị mới.
- Account không tồn tại với host pattern phù hợp.
- Authentication plugin không tương thích hoặc chưa được cấu hình.
- Account bị khóa hoặc chính sách xác thực không cho phép đăng nhập.
- Kết nối tới nhầm server có account khác.
- TLS hoặc yêu cầu xác thực bổ sung chưa được đáp ứng.

Kiểm tra account và plugin bằng account DBA:

~~~sql
SELECT
  user,
  host,
  plugin,
  account_locked,
  password_expired
FROM mysql.user
WHERE user = 'sales_app';
~~~

Bảng mysql.user là dữ liệu quản trị nhạy cảm; chỉ account được phép mới nên truy cập. Không yêu cầu ứng dụng runtime đọc bảng này. Có thể nhờ DBA xác nhận trạng thái account và cung cấp thông tin đã được làm sạch.

1045 khác 1044: 1045 là lỗi kết nối/xác thực account; 1044 là account đã được xác thực nhưng không có quyền truy cập database được yêu cầu trong thao tác tương ứng.

## 15. Quy trình chẩn đoán từng bước

Khi nhận ticket Unknown database/table/column hoặc Access denied, làm theo trình tự:

### Bước 1: Thu thập lỗi gốc

Ghi mã lỗi, SQLState, exception class, thao tác và object được nhắc tới. Với ứng dụng Java, kiểm tra chuỗi SQLException.getNextException() và cause của exception ORM.

### Bước 2: Xác nhận endpoint

Chạy truy vấn:

~~~sql
SELECT
  @@hostname,
  @@port,
  @@server_uuid,
  VERSION(),
  DATABASE(),
  USER(),
  CURRENT_USER();
~~~

So sánh endpoint với cấu hình môi trường mà ứng dụng cần dùng.

### Bước 3: Xác nhận tên object

- Với database: SHOW DATABASES hoặc information_schema.SCHEMATA.
- Với table: SHOW FULL TABLES FROM db_name.
- Với column: SHOW COLUMNS FROM db_name.table_name hoặc information_schema.COLUMNS.
- Với DDL đầy đủ: SHOW CREATE TABLE db_name.table_name.

Chú ý metadata có thể bị giới hạn theo grants của account.

### Bước 4: Xác nhận câu SQL và scope

Kiểm tra schema qualifier, alias table, alias column, identifier quoting, typo và thứ tự migration. Nếu SQL do ORM sinh ra, bật logging SQL an toàn trong môi trường phù hợp và xem bind parameter mà không làm lộ dữ liệu nhạy cảm.

### Bước 5: Xác nhận grants

Dùng CURRENT_USER(), SHOW GRANTS và CURRENT_ROLE(). So sánh privilege cần cho statement với privilege thực tế.

### Bước 6: Sửa đúng nguyên nhân

- Sai server/database: sửa endpoint hoặc cấu hình catalog.
- Sai tên object: sửa SQL hoặc migration theo thiết kế.
- Migration chưa chạy: triển khai migration đúng quy trình.
- Thiếu quyền: yêu cầu DBA cấp privilege tối thiểu.
- Sai host account/authentication: sửa account mapping hoặc secret theo quy trình quản trị.

### Bước 7: Kiểm thử bằng account ứng dụng

Chạy lại chính thao tác đã thất bại trên đúng môi trường và account. Kiểm tra cả đường đọc/ghi cần thiết, không chỉ dùng account DBA để chứng minh query chạy được.

## 16. Java/JDBC: lấy thông tin lỗi có ích

Ví dụ xử lý SQLException:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "SELECT order_id FROM sales.orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
        }
    }

} catch (SQLException e) {
    logger.error(
        "Database operation failed: sqlState={}, vendorCode={}, type={}",
        e.getSQLState(),
        e.getErrorCode(),
        e.getClass().getSimpleName()
    );

    for (SQLException next = e.getNextException();
         next != null;
         next = next.getNextException()) {
        logger.error(
            "Additional database error: sqlState={}, vendorCode={}",
            next.getSQLState(),
            next.getErrorCode()
        );
    }

    throw e;
}
~~~

Trong log production, không ghi password, token, dữ liệu cá nhân hoặc toàn bộ bind values. Nếu cần tái hiện query, log SQL template và request/correlation ID, sau đó lấy dữ liệu thử nghiệm đã được làm sạch.

Với Spring JDBC/JPA, exception có thể được chuyển thành DataAccessException. Hãy xem root cause và SQLState/vendor code để phân biệt BadSqlGrammarException, DataIntegrityViolationException, lỗi quyền hoặc lỗi kết nối. Không chuyển mọi lỗi thành một thông báo chung kiểu database unavailable.

## 17. ORM và lỗi tên column

Hibernate/JPA có thể tạo SQL dựa trên entity mapping. Nếu mapping không khớp DDL, MySQL có thể báo 1054 dù code Java compile thành công.

Ví dụ:

~~~java
@Entity
@Table(name = "orders", schema = "sales")
public class Order {
    @Id
    private Long id;

    @Column(name = "fulfillment_status")
    private String fulfillmentStatus;
}
~~~

Nếu table thật chỉ có column status, mapping này sẽ tạo truy vấn dùng fulfillment_status và gặp unknown column.

Kiểm tra:

- @Table(schema = ..., name = ...).
- @Column(name = ...).
- Naming strategy chuyển camelCase sang snake_case.
- Schema mặc định và JDBC URL.
- DDL thực tế từ SHOW CREATE TABLE.
- Migration đã được áp dụng ở đúng database chưa.
- Native query có dùng tên column vật lý đúng không.

Không sửa DDL chỉ để làm entity mapping chạy nếu tên cột chuẩn trong database là đúng theo hợp đồng hiện tại. Chọn một nguồn sự thật cho schema và mapping; tránh để migration, ORM naming strategy và native SQL tự phát triển lệch nhau.

## 18. Quyền metadata và khả năng nhìn thấy object

Các lệnh SHOW DATABASES, SHOW TABLES và truy vấn information_schema có thể chỉ hiển thị object mà account được phép nhìn thấy. Vì vậy:

- Kết quả rỗng không luôn chứng minh object không tồn tại.
- SHOW CREATE TABLE có thể cần quyền phù hợp.
- Account có SELECT column-level có thể chỉ nhìn thấy một phần dữ liệu.
- Account runtime không nên được cấp quyền quản trị chỉ để hỗ trợ chẩn đoán.

Khi cần xác nhận object, dùng một account DBA hoặc quy trình kiểm tra được phê duyệt, nhưng giữ thao tác đó ở chế độ đọc. Sau đó so sánh kết quả với account ứng dụng để xác định vấn đề nằm ở tên hay quyền.

Không thử truy cập dữ liệu nhạy cảm bằng account khác để vượt qua giới hạn đã đặt. Mục tiêu là xác định privilege thiếu, rồi quyết định có cấp quyền hợp lệ hay sửa query để không truy cập object/cột ngoài phạm vi.

## 19. Các lỗi xử lý thường gặp

| Cách xử lý sai | Rủi ro | Cách làm đúng |
|---|---|---|
| Gặp 1049 là tạo database mới ngay | Tạo nhầm schema trên sai server hoặc che giấu lỗi endpoint | Xác nhận server UUID, database và migration trước. |
| Gặp 1146 là chạy CREATE TABLE thủ công | Schema drift, migration sau thất bại | Kiểm tra DDL, release và migration status. |
| Gặp 1054 là thêm column theo tên trong code | Có thể tạo sai cấu trúc hoặc sai semantics | Đối chiếu entity, query và DDL đã phê duyệt. |
| Gặp 1142 là cấp ALL PRIVILEGES | Mở rộng quyền quá mức cho account runtime | Cấp đúng SELECT/INSERT/UPDATE/DELETE trên object cần thiết. |
| Dùng USER() để kiểm tra grants | Có thể kiểm tra nhầm account host | Dùng CURRENT_USER() và SHOW GRANTS. |
| Dùng account DBA để test ứng dụng | DBA có quyền rộng nên che giấu lỗi quyền runtime | Kiểm thử bằng chính account ứng dụng. |
| Dùng SHOW TABLES rỗng để kết luận table không tồn tại | Metadata có thể bị ẩn bởi quyền | Xác minh bằng account được phép và kiểm tra grants. |
| Sửa lower_case_table_names trên server đang chạy | Có thể không được hỗ trợ hoặc gây vấn đề với data directory | Chuẩn hóa tên và migration; không đổi cấu hình tùy tiện. |
| Ghép tên table từ input người dùng | SQL injection hoặc truy vấn nhầm object | Dùng whitelist cho identifier; bind parameter cho giá trị. |
| Ghi toàn bộ SQL và credentials vào log | Rò rỉ secret hoặc dữ liệu nhạy cảm | Log mã lỗi, SQL template, endpoint và correlation ID. |

## 20. Bài tập thực hành

### Bài 1: Phân biệt 1046 và 1049

Mở connection không chọn database, chạy SELECT * FROM orders và quan sát lỗi. Sau đó chạy USE database_khong_ton_tai để quan sát lỗi khác. Giải thích sự khác biệt giữa database chưa được chọn và database không tồn tại.

### Bài 2: Phân biệt 1146 và 1142

Tạo table thử nghiệm sales.orders. Dùng một account có quyền SELECT rồi thu hồi SELECT trong môi trường lab. So sánh lỗi khi table không tồn tại với lỗi khi account không có quyền đọc table. Khôi phục grants sau bài tập.

### Bài 3: Tái hiện 1054

Chạy truy vấn với tên column sai, sau đó kiểm tra SHOW COLUMNS và SHOW CREATE TABLE. Thử thêm alias trong SELECT rồi tham chiếu alias trong WHERE; giải thích vì sao alias chưa có trong scope của WHERE.

### Bài 4: Kiểm tra account mapping

Kết nối bằng account có cùng username nhưng host pattern khác nhau. Chạy USER(), CURRENT_USER() và SHOW GRANTS. Xác định account nào thực sự được MySQL dùng để kiểm tra quyền.

### Bài 5: Mô phỏng schema migration lệch phiên bản

Tạo table ở phiên bản schema cũ, chạy query dùng column mới rồi quan sát 1054. Áp dụng migration trên đúng database và chạy lại bằng account ứng dụng. Ghi nhận cách xác nhận migration đã chạy đúng endpoint.

### Bài 6: Cấp quyền tối thiểu

Tạo account chỉ đọc một table hoặc một nhóm column. Thử SELECT, UPDATE và truy cập column bị giới hạn. Cấp đúng privilege cần thiết, chạy lại kiểm thử và xác nhận không cấp quyền toàn server.

## 21. Checklist xử lý sự cố

- [ ] Đã lưu mã lỗi MySQL, SQLState và exception gốc.
- [ ] Đã xác nhận @@hostname, @@server_uuid, port và phiên bản.
- [ ] Đã kiểm tra DATABASE() và database mặc định của JDBC connection.
- [ ] Đã kiểm tra USER() và CURRENT_USER().
- [ ] Đã xác minh database/table/column bằng metadata phù hợp.
- [ ] Đã kiểm tra schema qualifier, alias, typo và identifier quoting.
- [ ] Đã kiểm tra lower_case_table_names khi lỗi chỉ xảy ra trên một nền tảng.
- [ ] Đã xác minh migration và phiên bản schema trên đúng server.
- [ ] Đã đọc grants và active roles của account được match.
- [ ] Đã phân biệt lỗi database access, table privilege và column privilege.
- [ ] Đã đề xuất quyền tối thiểu ở đúng phạm vi nếu thực sự thiếu quyền.
- [ ] Đã kiểm thử lại bằng account ứng dụng, không chỉ bằng DBA.
- [ ] Đã tránh ghi secret hoặc dữ liệu nhạy cảm vào log.
- [ ] Đã ghi lại nguyên nhân gốc và cách phòng ngừa tái diễn.

Unknown database, Table doesn't exist và Unknown column thường yêu cầu kiểm tra tên, ngữ cảnh session, schema và migration. Access denied cùng các lỗi command denied yêu cầu kiểm tra account được MySQL match và grants ở đúng phạm vi. Bằng cách xác nhận endpoint trước, kiểm tra metadata sau, rồi đối chiếu quyền bằng CURRENT_USER() và SHOW GRANTS, bạn có thể tìm đúng nguyên nhân và sửa với thay đổi nhỏ nhất. Luôn kiểm thử bằng account ứng dụng thực tế để bảo đảm lỗi đã được xử lý mà không mở rộng quyền ngoài nhu cầu.

