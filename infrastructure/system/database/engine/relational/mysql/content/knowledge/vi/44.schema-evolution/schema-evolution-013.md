# Đổi tên bảng/cột, dependency và hợp đồng ứng dụng

Trong module **DATABASE_MYSQL**, thay đổi schema không chỉ là sửa một câu lệnh DDL. Một bảng hoặc cột có thể được sử dụng đồng thời bởi nhiều phiên bản ứng dụng, view, trigger, stored routine, job nền, báo cáo, pipeline CDC và hệ thống tích hợp. Đổi tên trực tiếp khi các thành phần này vẫn đang hoạt động có thể khiến truy vấn lỗi ngay sau khi DDL hoàn tất.

Bài học này trình bày cách kiểm kê dependency, đổi tên bảng và cột bằng MySQL, giữ tương thích trong lúc triển khai nhiều phiên bản ứng dụng, kiểm soát metadata lock và chọn thời điểm loại bỏ tên cũ. Trọng tâm là quản lý hợp đồng giữa schema và ứng dụng qua các giai đoạn **expand, migrate, contract**.

Trong phạm vi DATABASE_MYSQL, chủ đề này kết nối với thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời; đồng thời liên quan đến đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý sự cố vận hành cơ sở dữ liệu quan hệ.

## 1. Mục tiêu và khái niệm

Sau bài học, bạn có thể:

- Xác định các thành phần phụ thuộc vào tên bảng và tên cột.
- Phân biệt đổi tên trực tiếp với thay đổi schema có giai đoạn tương thích.
- Sử dụng RENAME TABLE và RENAME COLUMN đúng cách.
- Nhận diện rủi ro khi dùng CHANGE COLUMN và khi thay đổi cột có dependency.
- Thiết kế rollout để phiên bản ứng dụng cũ và mới cùng hoạt động trong thời gian chuyển tiếp.
- Kiểm tra metadata lock, replication và các truy vấn đang sử dụng schema cũ.
- Xác định điều kiện an toàn để xóa cột/bảng cũ và chuẩn bị rollback.

**Hợp đồng ứng dụng** là tập hợp những giả định mà ứng dụng và các hệ thống liên quan dựa vào khi truy cập database: tên schema, bảng, cột, kiểu dữ liệu, nullability, default, index, constraint, quyền và ngữ nghĩa dữ liệu. Một thay đổi tên có thể không làm thay đổi dữ liệu, nhưng vẫn phá vỡ hợp đồng nếu client còn gửi câu SQL dùng tên cũ.

Một schema có thể được sử dụng bởi nhiều thành phần:

- API, worker, cron job, batch và các phiên bản ứng dụng đang triển khai dần.
- ORM mapping, prepared statement, query builder và SQL viết trực tiếp.
- View, trigger, stored procedure, function và event.
- Foreign key, index, generated column và partition.
- Báo cáo BI, ETL, CDC consumer, data warehouse và script vận hành.
- Dashboard, công cụ hỗ trợ khách hàng và truy vấn ad hoc.
- Backup, restore, migration tool và quy trình kiểm tra dữ liệu.

Vì vậy, trước khi đổi tên cần biết ai đang dùng đối tượng, dùng theo cách nào và có thể chuyển sang tên mới vào thời điểm nào.

## 2. Kiểm kê dependency trước khi thay đổi

### 2.1. Tìm dependency trong MySQL

Information Schema giúp tìm nhiều tham chiếu được lưu trong metadata. Ví dụ, liệt kê các cột của một bảng:

~~~sql
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME,
       COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
       EXTRA, GENERATION_EXPRESSION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

Tìm foreign key tham chiếu đến bảng hoặc cột:

~~~sql
SELECT CONSTRAINT_SCHEMA, TABLE_NAME, COLUMN_NAME,
       CONSTRAINT_NAME, REFERENCED_TABLE_SCHEMA,
       REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = 'appdb'
  AND REFERENCED_TABLE_NAME = 'orders';
~~~

Tìm view có sử dụng bảng:

~~~sql
SELECT VIEW_SCHEMA, VIEW_NAME, TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.VIEW_TABLE_USAGE
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders';
~~~

Tìm trigger gắn với bảng:

~~~sql
SELECT TRIGGER_SCHEMA, TRIGGER_NAME, EVENT_OBJECT_SCHEMA,
       EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION,
       ACTION_STATEMENT
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE EVENT_OBJECT_SCHEMA = 'appdb'
  AND EVENT_OBJECT_TABLE = 'orders';
~~~

Tìm index sử dụng cột:

~~~sql
SELECT TABLE_SCHEMA, TABLE_NAME, INDEX_NAME,
       COLUMN_NAME, SEQ_IN_INDEX, NON_UNIQUE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
  AND COLUMN_NAME = 'customer'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

Có thể xem định nghĩa view, routine và event qua các bảng Information Schema tương ứng như VIEWS, ROUTINES và EVENTS. Tuy nhiên, metadata không phải lúc nào cũng thể hiện đầy đủ dependency. SQL động được ghép bằng chuỗi, tên bảng lấy từ cấu hình hoặc truy vấn do ứng dụng tạo ra có thể không được ghi nhận thành quan hệ dependency tĩnh.

### 2.2. Tìm dependency ngoài database

Kết hợp kiểm tra metadata với tìm kiếm trong mã nguồn và cấu hình:

- Tìm tên bảng/cột cũ trong repository, migration, query template và file cấu hình.
- Kiểm tra ORM entity, mapping, serializer và API contract.
- Kiểm tra job scheduler, stored procedure gọi gián tiếp và trigger trên bảng khác.
- Kiểm tra CDC connector, schema registry, ETL, dashboard và báo cáo.
- Kiểm tra các consumer đang chạy ở phiên bản cũ trong quá trình rollout.
- Kiểm tra script hỗ trợ, notebook và truy vấn vận hành được lưu ngoài repository chính.

Một truy vấn tìm kiếm không thấy tên cũ không chứng minh rằng không còn dependency. Ví dụ, ứng dụng có thể tạo tên bảng từ biến cấu hình hoặc ghép SQL động. Cần xác định cả đường đi của dữ liệu và chủ sở hữu từng consumer.

### 2.3. Lập bảng dependency và kế hoạch chuyển

Trước khi thực hiện DDL, ghi lại:

| Dependency | Dùng tên cũ ở đâu? | Người/hệ thống sở hữu | Cách chuyển | Điều kiện kết thúc |
|---|---|---|---|---|
| API phiên bản cũ | SQL đọc/ghi | Nhóm ứng dụng | Triển khai bản tương thích | Không còn instance cũ |
| Worker nền | Query cập nhật trạng thái | Nhóm vận hành | Nâng cấp worker và drain job cũ | Không còn job dùng tên cũ |
| View báo cáo | SELECT từ bảng cũ | Nhóm dữ liệu | Cập nhật định nghĩa view | Báo cáo xác nhận đúng |
| Trigger | Ghi audit | DBA/nhóm ứng dụng | Kiểm tra và sửa trigger | Kiểm thử ghi thành công |
| CDC/ETL | Mapping cột cũ | Nhóm dữ liệu | Cập nhật schema mapping | Consumer đọc schema mới |
| Script hỗ trợ | SQL thủ công | Nhóm vận hành | Cập nhật tài liệu và script | Không còn quy trình gọi tên cũ |

Chỉ định một chủ sở hữu cho từng dependency. Nếu không xác định được chủ sở hữu hoặc không biết một consumer còn hoạt động hay không, hãy coi đó là rủi ro chưa được giải quyết trước khi contract.

## 3. Đổi tên bảng và cột trực tiếp

### 3.1. Đổi tên bảng bằng RENAME TABLE

Cú pháp cơ bản:

~~~sql
RENAME TABLE appdb.orders TO appdb.customer_orders;
~~~

Lệnh thay đổi tên đối tượng trong metadata. Dữ liệu của bảng không được sao chép sang một bảng mới chỉ vì tên thay đổi. Tuy nhiên, thao tác vẫn cần metadata lock và có thể phải chờ transaction hoặc truy vấn đang giữ metadata lock trên bảng.

Có thể thực hiện nhiều thao tác đổi tên trong cùng một câu lệnh:

~~~sql
RENAME TABLE
  appdb.orders TO appdb.orders_archive,
  appdb.orders_next TO appdb.orders;
~~~

Cách này hữu ích khi cần hoán đổi tên giữa bảng hiện tại và bảng đã chuẩn bị. Phải xác nhận tất cả tên nguồn/đích tồn tại đúng trạng thái và không có xung đột tên. Hành vi atomic/crash-safe phụ thuộc phiên bản MySQL và storage engine được hỗ trợ; hãy xác minh theo phiên bản triển khai và thử nghiệm trên môi trường tương đương trước khi dùng làm cutover.

Đổi tên bảng không tự sửa mọi câu SQL bên ngoài database. Ứng dụng, script, query template và cấu hình CDC vẫn có thể gọi tên cũ. Cũng không nên giả định mọi định nghĩa view, routine hoặc SQL động sẽ được viết lại theo tên mới. Hãy kiểm tra và triển khai lại các đối tượng phụ thuộc theo thứ tự đã lập kế hoạch.

### 3.2. Đổi tên cột bằng RENAME COLUMN

Với MySQL 8.0 trở lên, có thể dùng:

~~~sql
ALTER TABLE appdb.customer_orders
  RENAME COLUMN customer TO customer_name;
~~~

RENAME COLUMN đổi tên mà không yêu cầu viết lại toàn bộ định nghĩa kiểu dữ liệu của cột. Đây thường là lựa chọn rõ ràng hơn khi mục tiêu chỉ là đổi tên.

Trước khi chạy, kiểm tra:

- View, routine, trigger và ứng dụng còn tham chiếu tên cũ.
- Generated column hoặc biểu thức phụ thuộc vào cột.
- Index, unique key và foreign key liên quan.
- CDC mapping và schema consumer.
- Phiên bản MySQL và thuật toán DDL được hỗ trợ cho cấu trúc bảng cụ thể.

Không suy luận rằng tất cả dependency đều được tự động chuyển đổi chỉ vì câu lệnh ALTER TABLE thành công. Hãy đọc lại định nghĩa các đối tượng phụ thuộc và kiểm thử truy vấn thực tế.

### 3.3. Phân biệt RENAME COLUMN và CHANGE COLUMN

CHANGE COLUMN có thể đổi tên và đồng thời thay đổi định nghĩa cột:

~~~sql
ALTER TABLE appdb.customer_orders
  CHANGE COLUMN customer customer_name
  VARCHAR(150) NOT NULL;
~~~

Câu lệnh CHANGE COLUMN yêu cầu khai báo lại định nghĩa cột. Nếu bỏ sót UNSIGNED, NULL/NOT NULL, DEFAULT, COMMENT, charset, collation, thuộc tính generated hoặc các thuộc tính khác, schema có thể bị thay đổi ngoài ý muốn.

Nếu chỉ đổi tên, ưu tiên RENAME COLUMN trên phiên bản hỗ trợ. Nếu buộc phải dùng CHANGE COLUMN do phiên bản cũ hoặc cần thay đổi định nghĩa cùng lúc, hãy lấy định nghĩa hiện tại từ SHOW CREATE TABLE, giữ nguyên mọi thuộc tính cần thiết và so sánh DDL trước/sau.

~~~sql
SHOW CREATE TABLE appdb.customer_orders;
~~~

Không dùng CHANGE COLUMN như một thao tác đổi tên đơn giản khi chưa kiểm tra lại toàn bộ định nghĩa.

## 4. Vì sao đổi tên trực tiếp có thể phá vỡ ứng dụng?

Giả sử ứng dụng phiên bản A chạy câu SQL:

~~~sql
SELECT order_id, customer
FROM appdb.orders
WHERE order_id = ?;
~~~

DBA chạy:

~~~sql
RENAME TABLE appdb.orders TO appdb.customer_orders;
~~~

Sau DDL, truy vấn phiên bản A vẫn yêu cầu appdb.orders và sẽ lỗi vì tên cũ không còn tồn tại. Tương tự, đổi cột customer thành customer_name khiến truy vấn cũ không còn phân giải được cột.

Trong môi trường triển khai liên tục, không phải mọi instance ứng dụng cùng đổi phiên bản trong một khoảnh khắc. Có thể tồn tại:

- Instance cũ đang xử lý request.
- Instance mới đã bắt đầu nhận traffic.
- Worker cũ đang chạy một job dài.
- Consumer CDC đang đọc schema cũ.
- Script batch chỉ chạy vào ban đêm.
- Connection pool giữ prepared statement được tạo trước khi DDL xảy ra.

Do đó, DDL tương thích cần được phối hợp với lịch triển khai và vòng đời của mọi client.

## 5. Chiến lược expand, migrate, contract

Đối với hệ thống có yêu cầu hoạt động liên tục, hãy chia thay đổi thành các giai đoạn để cả phiên bản cũ và mới có thể cùng tồn tại trong một khoảng thời gian.

### 5.1. Expand: thêm cấu trúc mới

Ví dụ cần đổi cột customer thành customer_name. Thay vì đổi tên ngay, thêm cột mới:

~~~sql
ALTER TABLE appdb.orders
  ADD COLUMN customer_name VARCHAR(150) NULL;
~~~

Ở giai đoạn này:

- Cột cũ vẫn tồn tại để ứng dụng cũ tiếp tục hoạt động.
- Cột mới được tạo với kiểu dữ liệu và nullability đã thống nhất.
- Index hoặc constraint mới được thêm theo kế hoạch.
- Kiểm tra chi phí DDL, metadata lock và dung lượng trước khi triển khai.

Nếu cần đổi tên bảng, có thể cân nhắc tạo bảng mới với schema mục tiêu, rồi chuẩn bị đồng bộ dữ liệu. Việc sao chép toàn bảng có thể tốn tài nguyên; chọn công cụ online schema change phù hợp khi cần giữ thời gian dừng thấp.

### 5.2. Migrate: chuyển ứng dụng và dữ liệu

Triển khai ứng dụng theo cách vẫn tương thích với schema đang tồn tại:

1. Bản ứng dụng trung gian có thể đọc cột cũ và cột mới, hoặc ghi đồng thời theo một quy tắc rõ ràng.
2. Backfill dữ liệu cũ sang cột mới theo batch nhỏ.
3. Đảm bảo mọi thay đổi mới trong thời gian backfill cũng được đồng bộ.
4. So sánh số hàng, NULL, checksum hoặc giá trị nghiệp vụ giữa hai cột.
5. Chuyển ứng dụng đọc từ cột mới sau khi dữ liệu đã đầy đủ.
6. Theo dõi lỗi và số lần truy cập cột cũ trước khi dừng ghi vào cột cũ.

Ví dụ backfill theo batch dựa trên khóa tăng dần:

~~~sql
UPDATE appdb.orders
SET customer_name = customer
WHERE order_id > 0
  AND order_id <= 10000
  AND customer_name IS NULL;
~~~

Lặp lại theo từng khoảng khóa đã chọn, theo dõi thời gian transaction, lock, redo log và replication lag. Batch size cần được điều chỉnh dựa trên tải thực tế. Tránh chạy một UPDATE khổng lồ làm tăng undo/redo, giữ lock lâu hoặc khiến replica tụt xa.

Nếu dữ liệu mới vẫn được ghi vào customer trong lúc backfill, cần bảo đảm customer_name được cập nhật tương ứng. Có thể dùng dual-write trong ứng dụng hoặc trigger tạm thời, nhưng phải chọn một nguồn dữ liệu chuẩn và xác định thứ tự cập nhật để tránh vòng lặp hoặc ghi đè giá trị mới bằng dữ liệu cũ. Kiểm thử các tình huống insert, update, NULL, retry và transaction rollback.

Ví dụ dual-write ở tầng ứng dụng:

~~~sql
UPDATE appdb.orders
SET customer = ?,
    customer_name = ?
WHERE order_id = ?;
~~~

Hai giá trị cần được tạo từ cùng một dữ liệu đầu vào và cập nhật trong cùng transaction. Không triển khai hai luồng ghi độc lập mà không có quy tắc giải quyết xung đột.

### 5.3. Contract: loại bỏ cấu trúc cũ

Chỉ xóa cột cũ khi đã xác nhận:

- Tất cả ứng dụng và worker đã chuyển sang cột mới.
- Không còn truy vấn, view, routine, trigger hoặc job cần cột cũ.
- CDC, báo cáo, ETL và consumer đã dùng schema mới.
- Backfill hoàn tất và kiểm tra dữ liệu đạt yêu cầu.
- Có backup/restore hoặc phương án phục hồi đã kiểm thử.
- Hết thời hạn rollback đã thống nhất với chủ hệ thống.

Sau đó mới thực hiện:

~~~sql
ALTER TABLE appdb.orders
  DROP COLUMN customer;
~~~

DROP COLUMN là thay đổi không nên thực hiện sớm. Sau khi xóa, quay lại ứng dụng cũ sẽ không thể hoạt động nếu cột cũ không được phục hồi và đồng bộ dữ liệu.

## 6. Đổi tên bảng trong giai đoạn tương thích

Đổi tên bảng phức tạp hơn đổi tên cột vì nhiều thành phần có thể tham chiếu đến bảng và foreign key.

Một cách tiếp cận có thể cân nhắc là dùng bảng mới và một đối tượng tương thích dưới tên cũ trong thời gian chuyển tiếp. Ví dụ, một view đơn giản có thể cung cấp tên cũ cho truy vấn đọc:

~~~sql
CREATE VIEW appdb.orders AS
SELECT order_id, customer_name, created_at
FROM appdb.customer_orders;
~~~

Đây chỉ là ví dụ minh họa. Không phải mọi view đều updatable; view có JOIN, aggregate, DISTINCT, GROUP BY hoặc cấu trúc khác có thể không hỗ trợ ghi như bảng. View cũng không thay thế được bảng trong vai trò đích của foreign key. Trước khi dùng view tương thích, phải kiểm tra quyền, trigger, khả năng ghi, hiệu năng và mọi consumer.

Nếu ứng dụng cũ cần ghi vào tên bảng cũ, cần chọn phương án đồng bộ có kiểm soát:

- Nâng cấp toàn bộ writer trước khi đổi tên.
- Dùng một lớp tương thích được kiểm thử và có cơ chế ghi rõ ràng.
- Tạo bảng mới, đồng bộ dữ liệu bằng CDC/trigger hoặc công cụ online schema change, rồi chuyển endpoint trong một cửa sổ ngắn.

Không tạo hai bảng độc lập rồi để ứng dụng cũ ghi bảng này và ứng dụng mới ghi bảng kia mà không có cơ chế đồng bộ giao dịch. Điều đó có thể tạo dữ liệu phân nhánh.

Với bảng có foreign key, trigger hoặc nhiều view phụ thuộc, lập kế hoạch riêng cho từng đối tượng. Kiểm tra metadata sau khi đổi tên và xác minh ràng buộc vẫn trỏ đúng bảng đích. Không dựa vào giả định rằng mọi dependency đều được tự động đổi tên.

## 7. Metadata lock và tác động vận hành

### 7.1. DDL cần metadata lock

MySQL dùng metadata lock để bảo vệ định nghĩa đối tượng khi truy vấn và DDL diễn ra. Một transaction đang sử dụng bảng có thể giữ metadata lock đến khi transaction kết thúc. Vì vậy, ALTER TABLE hoặc RENAME TABLE có thể phải chờ một truy vấn/transaction dài.

Ngay cả khi một thao tác DDL hỗ trợ INSTANT hoặc INPLACE, nó vẫn cần metadata lock ở một số giai đoạn. "Online DDL" không có nghĩa là hoàn toàn không chặn hoặc không ảnh hưởng hiệu năng.

Kiểm tra metadata lock đang chờ:

~~~sql
SELECT OBJECT_TYPE, OBJECT_SCHEMA, OBJECT_NAME,
       LOCK_TYPE, LOCK_DURATION, LOCK_STATUS,
       OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'appdb'
  AND OBJECT_NAME = 'orders';
~~~

Tìm transaction lâu:

~~~sql
SELECT trx_id, trx_started, trx_state,
       trx_mysql_thread_id, trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Kết hợp với PROCESSLIST và log ứng dụng để xác định client đang giữ transaction. Không kill connection một cách tùy tiện; trước tiên đánh giá transaction có thể rollback được không và ảnh hưởng nghiệp vụ.

### 7.2. Kiểm soát thời gian chờ

Có thể đặt lock wait timeout cho phiên DDL để tránh chờ vô hạn:

~~~sql
SET SESSION lock_wait_timeout = 10;
~~~

Nếu DDL không lấy được metadata lock trong thời gian này, nó sẽ thất bại và có thể thử lại ở cửa sổ phù hợp. Giá trị cần chọn theo chính sách vận hành. Không lặp lại DDL liên tục trong khi blocker chưa được xử lý, vì các lần chờ có thể làm hàng đợi metadata lock ảnh hưởng thêm truy vấn mới.

### 7.3. Chọn thuật toán DDL

MySQL có các thuật toán DDL như INSTANT, INPLACE và COPY; khả năng hỗ trợ phụ thuộc loại thay đổi, phiên bản, storage engine và cấu trúc bảng.

- INSTANT thường chỉ thay đổi metadata và tránh rebuild toàn bảng đối với các thao tác được hỗ trợ.
- INPLACE có thể tránh copy toàn bộ bảng nhưng vẫn có thể đọc/ghi lại dữ liệu hoặc xây dựng index.
- COPY tạo bảng mới và sao chép dữ liệu; thường cần nhiều I/O, dung lượng và thời gian hơn.

Không tự thêm ALGORITHM=INSTANT hoặc LOCK=NONE vào mọi câu ALTER TABLE. Nếu thao tác không hỗ trợ lựa chọn đó, câu lệnh có thể thất bại; nếu bỏ chỉ định, MySQL có thể chọn thuật toán khác với tác động lớn hơn dự kiến. Hãy kiểm tra tài liệu theo phiên bản, thử trên bản sao dữ liệu tương đương và đo thời gian/lock trước production.

## 8. Replication, CDC và thứ tự triển khai

DDL thường được ghi vào binary log dưới dạng statement event và được áp dụng trên replica. Khi đổi tên bảng/cột ở nguồn, replica cũng phải có cấu trúc tương ứng trước khi các truy vấn hoặc ứng dụng mới sử dụng tên mới trên replica.

Với CDC consumer:

- Kiểm tra connector có phát hiện schema change không.
- Xác định consumer nhận tên cột mới hay cần mapping tương thích.
- Kiểm tra schema registry và định dạng sự kiện downstream.
- Tránh đổi tên và đổi kiểu dữ liệu cùng lúc nếu không cần thiết; tách thay đổi giúp xác định nguyên nhân lỗi.
- Đảm bảo consumer có thể xử lý sự kiện trước và sau thời điểm schema thay đổi.

Một thứ tự rollout thường dễ kiểm soát:

1. Triển khai thay đổi schema theo hướng tương thích.
2. Cập nhật consumer, view và các thành phần có thể chuẩn bị trước.
3. Triển khai ứng dụng phiên bản mới theo batch.
4. Backfill và kiểm tra dữ liệu.
5. Chuyển đọc/ghi sang cấu trúc mới.
6. Theo dõi đủ lâu để xác nhận không còn consumer cũ.
7. Contract bằng cách xóa đối tượng cũ.

Đối với read replica, chờ DDL đã được áp dụng và kiểm tra trạng thái replication trước khi chuyển truy vấn đọc sang cột/bảng mới. Với replication lag, một ứng dụng mới đọc ngay trên replica có thể gặp lỗi "unknown column" nếu DDL chưa tới nơi.

## 9. Rollback và phục hồi

### 9.1. Rollback trước khi contract

Trong giai đoạn expand/migrate, nếu cột cũ vẫn tồn tại và dữ liệu được đồng bộ đúng, có thể chuyển ứng dụng đọc về cột cũ. Trước khi rollback:

- Dừng rollout phiên bản mới.
- Xác định nguồn dữ liệu chuẩn và chiều đồng bộ.
- Kiểm tra các cập nhật chỉ ghi vào cột mới.
- Đồng bộ ngược nếu cột cũ đã ngừng được cập nhật.
- Xác nhận ứng dụng cũ đọc được dữ liệu hiện tại.

Nếu chỉ đổi tên trực tiếp, rollback có thể dùng RENAME TABLE hoặc RENAME COLUMN ngược lại khi không có dependency mới và không phát sinh dữ liệu ngoài kế hoạch. Tuy nhiên, đổi tên ngược không tự sửa ứng dụng, view hoặc SQL đã triển khai theo tên mới.

### 9.2. Sau khi contract

Sau khi DROP COLUMN hoặc DROP TABLE, rollback không còn là một câu lệnh đổi tên đơn giản. Cần khôi phục cấu trúc, phục hồi dữ liệu từ backup/binlog hoặc tái tạo từ nguồn dữ liệu chuẩn, rồi xác minh các dependency.

Hãy xác định trước:

- Backup nào có thể khôi phục và mất bao lâu?
- Có binary log đủ để replay đến mốc cần thiết không?
- Có thể tái tạo cột từ dữ liệu khác hay không?
- Việc phục hồi có cần dừng ghi không?
- Ai phê duyệt quyết định rollback?

Đừng xóa đối tượng cũ chỉ vì bản ứng dụng mới đã triển khai thành công. Cần có bằng chứng rằng mọi consumer đã chuyển và dữ liệu đã được đối soát.

## 10. Ví dụ kế hoạch đổi tên cột customer

Giả sử bảng orders có cột customer và cần chuyển sang customer_name.

| Giai đoạn | Schema | Ứng dụng | Kiểm tra |
|---|---|---|---|
| Ban đầu | Chỉ có customer | Bản cũ đọc/ghi customer | Ghi nhận số hàng và dependency |
| Expand | Thêm customer_name NULL | Bản cũ vẫn hoạt động | DDL hoàn tất, không có lock bất thường |
| Migrate 1 | Cả hai cột | Bản trung gian ghi cả hai | Backfill theo batch, đối soát |
| Migrate 2 | Cả hai cột | Bản mới đọc customer_name | Theo dõi lỗi, truy cập cột cũ |
| Contract | Xóa customer | Chỉ còn bản mới | Xác nhận không còn consumer cũ |

Các câu lệnh minh họa:

~~~sql
-- 1. Expand
ALTER TABLE appdb.orders
  ADD COLUMN customer_name VARCHAR(150) NULL;

-- 2. Backfill theo batch; lặp lại với các khoảng khóa tiếp theo
UPDATE appdb.orders
SET customer_name = customer
WHERE order_id > 0
  AND order_id <= 10000
  AND customer_name IS NULL;

-- 3. Đối soát
SELECT COUNT(*) AS mismatch_count
FROM appdb.orders
WHERE NOT (customer_name <=> customer);

-- 4. Chỉ contract sau khi mọi consumer đã chuyển
ALTER TABLE appdb.orders
  DROP COLUMN customer;
~~~

Toán tử NULL-safe equality **<=>** giúp so sánh hai giá trị kể cả khi một hoặc cả hai là NULL. Nếu nghiệp vụ cho phép hai cột có giá trị khác nhau sau một thời điểm, cần xác định quy tắc đồng bộ trước khi dùng truy vấn đối soát này.

Ví dụ trên giả định cả hai cột biểu diễn cùng một thông tin và đã có cơ chế dual-write. Không chạy bước DROP COLUMN cho đến khi xác nhận đầy đủ điều kiện contract.

## 11. Checklist trước khi đổi tên

### Khám phá và thiết kế

- [ ] Xác định chính xác đối tượng, schema và tên mới.
- [ ] Kiểm kê foreign key, index, view, trigger, routine, event và generated column.
- [ ] Tìm dependency trong ứng dụng, worker, báo cáo, CDC, ETL và script vận hành.
- [ ] Xác định phiên bản ứng dụng cũ/mới có thể chạy đồng thời trong bao lâu.
- [ ] Chọn đổi tên trực tiếp hay expand/migrate/contract.
- [ ] Xác định cách đồng bộ dữ liệu và nguồn dữ liệu chuẩn.

### Trước DDL

- [ ] Có backup và phương án phục hồi đã kiểm tra.
- [ ] Đã thử DDL trên bản sao có kích thước và cấu hình tương đương.
- [ ] Đã đánh giá thuật toán DDL, metadata lock và dung lượng.
- [ ] Đóng băng các thay đổi DDL cạnh tranh trên cùng đối tượng.
- [ ] Có kế hoạch xử lý replication lag và CDC schema change.

### Sau DDL và trước contract

- [ ] Đọc lại SHOW CREATE TABLE và metadata dependency.
- [ ] Kiểm thử truy vấn đọc/ghi của các phiên bản ứng dụng.
- [ ] Kiểm tra trigger, view, routine và job nền.
- [ ] Đối soát dữ liệu cũ/mới và kiểm tra lỗi ứng dụng.
- [ ] Xác nhận không còn client dùng tên cũ.
- [ ] Có phê duyệt của chủ sở hữu dữ liệu trước khi DROP.

## 12. Tự kiểm tra

**Tình huống 1:** Ứng dụng có nhiều instance đang chạy. DBA đổi tên bảng orders thành customer_orders ngay trong giờ cao điểm. Điều gì có thể xảy ra?

**Gợi ý:** Instance cũ và job nền còn dùng tên orders sẽ nhận lỗi truy vấn. DDL cũng có thể phải chờ metadata lock từ transaction đang sử dụng bảng.

**Tình huống 2:** Cần đổi tên cột customer thành customer_name trên MySQL 8.0. Khi chỉ đổi tên, nên ưu tiên cú pháp nào?

**Gợi ý:** Dùng ALTER TABLE ... RENAME COLUMN để không phải khai báo lại toàn bộ định nghĩa cột. Sau đó kiểm tra các dependency và consumer.

**Tình huống 3:** Một migration dùng CHANGE COLUMN nhưng vô tình bỏ thuộc tính UNSIGNED và DEFAULT. Hậu quả có thể là gì?

**Gợi ý:** Câu lệnh có thể thay đổi kiểu và hành vi dữ liệu ngoài ý muốn. Cần so sánh SHOW CREATE TABLE trước/sau và giữ nguyên các thuộc tính cần thiết.

**Tình huống 4:** Backfill đã chạy xong nhưng ứng dụng cũ vẫn có thể cập nhật customer. Có thể xóa cột customer chưa?

**Gợi ý:** Chưa. Cần bảo đảm mọi cập nhật mới cũng được đồng bộ sang customer_name, chuyển tất cả writer và xác minh không còn consumer cũ.

**Tình huống 5:** Sau khi DROP COLUMN, nhóm muốn rollback bằng cách đổi tên cột mới về tên cũ. Có đủ không?

**Gợi ý:** Không. Cột cũ đã bị xóa cùng dữ liệu của nó. Cần phục hồi cấu trúc và dữ liệu từ backup/binlog hoặc nguồn dữ liệu chuẩn, rồi kiểm tra lại dependency.

## 13. Điểm cần ghi nhớ

- Tên bảng/cột là một phần của hợp đồng giữa database và mọi client sử dụng nó.
- Kiểm kê dependency trong Information Schema, mã nguồn, job, CDC, ETL và báo cáo trước khi đổi tên.
- RENAME TABLE và RENAME COLUMN thực hiện thay đổi metadata; chúng không tự sửa mọi câu SQL bên ngoài database.
- CHANGE COLUMN yêu cầu khai báo lại định nghĩa cột và có thể vô tình thay đổi thuộc tính.
- Expand/migrate/contract cho phép nhiều phiên bản ứng dụng cùng hoạt động trong thời gian chuyển tiếp.
- Backfill cần batch phù hợp và cơ chế đồng bộ các cập nhật mới.
- Online DDL vẫn có thể cần metadata lock; phải thử nghiệm thuật toán và thời gian chờ trên môi trường tương đương.
- Chỉ DROP cấu trúc cũ sau khi mọi consumer đã chuyển, dữ liệu được đối soát và rollback đã được đánh giá.
- Sau khi contract, phục hồi cần backup/binlog hoặc tái tạo dữ liệu; đổi tên ngược không khôi phục dữ liệu đã xóa.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: RENAME TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/rename-table.html) — cú pháp và điều kiện đổi tên bảng.
- [MySQL 8.4 Reference Manual: ALTER TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/alter-table.html) — RENAME COLUMN, CHANGE COLUMN và các thuật toán DDL.
- [MySQL 8.4 Reference Manual: Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html) — thuật toán và mức khóa của các thao tác InnoDB.
- [MySQL 8.4 Reference Manual: Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html) — cách MySQL quản lý metadata lock.
- [MySQL 8.4 Reference Manual: INFORMATION_SCHEMA](https://dev.mysql.com/doc/refman/8.4/en/information-schema.html) — metadata phục vụ kiểm kê dependency.
