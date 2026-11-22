# Tổ chức bằng chứng để tái hiện lỗi và đánh giá hồi quy

Một lỗi MySQL chỉ có thể được sửa chắc chắn khi nhóm phát triển tái hiện được nó, hiểu điều kiện làm lỗi xuất hiện và chứng minh bản sửa không làm hỏng hành vi đã hoạt động. Một ảnh chụp màn hình hoặc một dòng thông báo lỗi thường chưa đủ. Cần thu thập bằng chứng có cấu trúc: phiên bản và cấu hình môi trường, schema, dữ liệu tối thiểu, câu SQL cùng tham số, ranh giới transaction, trình tự các thao tác đồng thời, kết quả mong đợi và kết quả thực tế.

Evidence packet là tập hợp những thông tin và tệp cần thiết để một người khác có thể chạy lại tình huống lỗi trong môi trường được kiểm soát. Với MySQL, packet tốt giúp phân biệt lỗi dữ liệu, lỗi SQL, lỗi transaction/concurrency, lỗi kế hoạch thực thi, lỗi driver hoặc khác biệt cấu hình. Sau khi sửa, chính packet đó trở thành đầu vào để tạo regression test và ngăn lỗi quay lại.

Bài học này thuộc phạm vi làm chủ MySQL từ thiết kế bảng, truy vấn, index và transaction đến đọc execution plan, phân quyền và xử lý vận hành. Trọng tâm là biến một báo cáo lỗi khó hiểu thành một trường hợp kiểm thử có thể lặp lại và có tiêu chí đánh giá rõ ràng.

## 1. Bằng chứng cần trả lời những câu hỏi nào?

Một báo cáo lỗi có ích phải giúp người nhận trả lời được:

1. **Điều gì xảy ra?** Mô tả hành vi quan sát được, thông báo lỗi, SQLSTATE, mã lỗi MySQL, số hàng bị ảnh hưởng và thời điểm xảy ra.
2. **Điều gì đáng lẽ phải xảy ra?** Nêu kết quả nghiệp vụ hoặc hợp đồng API cụ thể, tránh mô tả chung như “dữ liệu phải đúng”.
3. **Ở đâu và với phiên bản nào?** Ghi phiên bản server, driver, framework, cấu hình session, schema và môi trường triển khai.
4. **Làm thế nào để tái hiện?** Cung cấp fixture, câu SQL, kiểu và giá trị tham số, thứ tự thao tác, transaction boundary và điều kiện đồng thời.
5. **Tái hiện thành công được bao nhiêu lần?** Ghi tỷ lệ xuất hiện, thời gian chờ, điều kiện kích hoạt và các lần thử không gặp lỗi.
6. **Điều gì chứng minh đã sửa?** Có test tái hiện trước đây, test hồi quy sau sửa, kết quả kiểm tra dữ liệu và số đo hiệu năng khi cần.

Không gộp expected result và actual result vào cùng một câu. Ví dụ tốt: “Với hai yêu cầu đặt cùng sản phẩm còn một đơn vị, chỉ một transaction được commit; tồn kho cuối bằng 0 và chỉ có một đơn hàng thành công.” Ví dụ yếu: “Đôi lúc tồn kho bị sai.”

## 2. Cấu trúc một evidence packet

Tổ chức packet theo cấu trúc dễ lưu trữ và chuyển giao:

~~~text
mysql-bug-2026-014/
  README.md
  manifest.json
  environment/
    server-version.txt
    session-variables.txt
    schema.sql
    grants-redacted.sql
    application-dependencies.txt
  reproduction/
    setup.sql
    reproduce.sql
    parameters.txt
    expected-result.md
    actual-result.txt
    session-timeline.md
  diagnostics/
    explain.txt
    explain-analyze.txt
    processlist-redacted.txt
    innodb-status-redacted.txt
    relevant-log-excerpts.txt
  regression/
    test-case.md
    test-output.txt
~~~

Không phải lỗi nào cũng cần mọi tệp. Chỉ đính kèm bằng chứng có liên quan, nhưng README phải chỉ ra phần nào không áp dụng và vì sao. Một packet nhỏ, sạch và có thể chạy lại thường hữu ích hơn một thư mục chứa log lớn không có chỉ dẫn.

README nên ghi:

- Mã lỗi nội bộ, mức độ ảnh hưởng và chủ sở hữu điều tra.
- Tóm tắt điều kiện tái hiện và kết quả mong đợi/thực tế.
- Phiên bản và môi trường đã dùng để thu thập.
- Các bước chạy theo đúng thứ tự.
- Cách reset dữ liệu về trạng thái ban đầu.
- Tệp nào chứa dữ liệu nhạy cảm đã được làm sạch hoặc thay thế.
- Kết quả gần nhất và giới hạn đã biết của packet.

Manifest có thể ghi checksum của các tệp để xác nhận packet không bị thay đổi khi chuyển giữa nhóm. Không ghi password, token, private key, connection string có secret hoặc dữ liệu cá nhân thật vào manifest hay log.

## 3. Ghi nhận fingerprint của MySQL và ứng dụng

Hai môi trường cùng ghi “MySQL 8” vẫn có thể khác nhau về patch version, SQL mode, timezone, collation, optimizer settings, plugin và schema. Thu thập fingerprint từ chính instance và connection gây lỗi.

### 3.1. Phiên bản server và cấu hình session

Chạy các câu lệnh sau trên connection liên quan:

~~~sql
SELECT
  VERSION() AS server_version,
  @@version_comment AS distribution,
  @@hostname AS server_host,
  @@port AS server_port;

SELECT
  @@session.sql_mode AS sql_mode,
  @@session.time_zone AS session_time_zone,
  @@global.time_zone AS global_time_zone,
  @@session.transaction_isolation AS transaction_isolation,
  @@session.autocommit AS autocommit,
  @@character_set_connection AS character_set_connection,
  @@collation_connection AS collation_connection,
  @@character_set_results AS character_set_results;
~~~

Một số biến hoặc tên biến khác nhau theo phiên bản MySQL. Nếu truy vấn không tương thích, ghi phiên bản trước rồi điều chỉnh danh sách cho đúng; đừng bỏ qua việc ghi nhận biến chỉ vì một tên biến không tồn tại.

Khi lỗi có liên quan đến truy vấn hoặc hiệu năng, bổ sung các biến phù hợp như optimizer_switch, optimizer_search_depth, innodb_flush_log_at_trx_commit, innodb_buffer_pool_size, innodb_lock_wait_timeout, max_connections và binlog_format. Không cần chụp toàn bộ cấu hình hàng nghìn biến nếu chúng không liên quan; hãy nêu rõ tập biến được chọn và lý do.

### 3.2. Schema, index và quyền

Lấy định nghĩa chính xác của các bảng liên quan:

~~~sql
SHOW CREATE TABLE app_db.orders;
SHOW CREATE TABLE app_db.inventory;
SHOW INDEX FROM app_db.orders;
~~~

Schema cần giữ nguyên kiểu dữ liệu, NULL/NOT NULL, default, collation, generated column, partition, foreign key, check constraint và index. Chỉ chép lại một phần DDL có thể làm mất nguyên nhân, chẳng hạn unique index hoặc collation khiến hai giá trị được xem là trùng nhau.

Nếu lỗi phụ thuộc quyền, ghi tài khoản kết nối và quyền hiệu lực ở dạng đã loại bỏ thông tin bí mật:

~~~sql
SELECT CURRENT_USER(), USER();
SHOW GRANTS;
~~~

CURRENT_USER() cho biết account MySQL được dùng để kiểm tra quyền; USER() thể hiện user và host mà client cung cấp. Hai giá trị có thể khác nhau do quy tắc chọn account. Không xuất password hash hoặc dữ liệu xác thực.

### 3.3. Phiên bản ứng dụng và driver

Ghi phiên bản thực tế của:

- Java runtime và vendor JDK.
- MySQL Connector/J và JDBC API.
- Spring Boot, Spring Framework, Hibernate/JPA hoặc MyBatis.
- HikariCP hoặc connection pool khác.
- Flyway/Liquibase và phiên bản migration schema.
- Container image, hệ điều hành và timezone của tiến trình.

Ghi dependency tree hoặc danh sách artifact được đóng gói. Phiên bản ghi trong file build có thể khác phiên bản runtime do BOM, dependency transitive hoặc override. Với lỗi chỉ xuất hiện trong ứng dụng, lưu cả JDBC URL đã loại secret và các connection properties liên quan.

## 4. Tái hiện bằng dữ liệu tối thiểu và có thể reset

### 4.1. Tạo fixture nhỏ nhất vẫn giữ được lỗi

Fixture là schema và dữ liệu cần thiết để chạy lại một tình huống. Hãy bắt đầu từ dữ liệu gây lỗi, sau đó loại dần bảng, cột và hàng không cần thiết cho đến khi vẫn tái hiện được cùng kết quả. Quá trình thu nhỏ giúp xác định điều kiện cốt lõi và làm test chạy nhanh hơn.

Ví dụ lỗi cập nhật tồn kho không nguyên tử có thể chỉ cần hai bảng:

Ví dụ dùng CHECK constraint được MySQL thực thi từ phiên bản 8.0.16. Nếu kiểm thử trên phiên bản cũ hơn, không dùng constraint này làm bằng chứng rằng server đã ngăn giá trị âm.

~~~sql
CREATE TABLE inventory (
  product_id BIGINT PRIMARY KEY,
  quantity INT NOT NULL,
  CONSTRAINT chk_quantity_nonnegative CHECK (quantity >= 0)
) ENGINE = InnoDB;

CREATE TABLE orders (
  order_id BIGINT PRIMARY KEY,
  product_id BIGINT NOT NULL,
  quantity INT NOT NULL,
  status VARCHAR(20) NOT NULL,
  CONSTRAINT fk_orders_inventory
    FOREIGN KEY (product_id) REFERENCES inventory(product_id)
) ENGINE = InnoDB;

INSERT INTO inventory (product_id, quantity)
VALUES (101, 1);
~~~

Fixture cần có dữ liệu đủ để kích hoạt điều kiện lỗi. Nếu lỗi phụ thuộc duplicate key, phải giữ unique index và hai giá trị va chạm. Nếu lỗi phụ thuộc optimizer, dữ liệu cần giữ phân bố và độ chọn lọc đủ gần thực tế; một bảng chỉ có hai hàng có thể không tái hiện kế hoạch truy vấn trên bảng hàng triệu hàng.

### 4.2. Tạo trạng thái ban đầu lặp lại được

Script setup phải có thể chạy nhiều lần mà không để dữ liệu từ lần trước ảnh hưởng kết quả. Có thể xóa theo thứ tự phụ thuộc khóa ngoại rồi chèn lại fixture trong một transaction, hoặc tạo database/schema mới cho từng lượt.

~~~sql
START TRANSACTION;

DELETE FROM orders WHERE product_id = 101;
DELETE FROM inventory WHERE product_id = 101;

INSERT INTO inventory (product_id, quantity)
VALUES (101, 1);

COMMIT;
~~~

Trong môi trường test, reset phải đảm bảo không có worker hoặc session khác ghi vào fixture cùng lúc. Không chạy script reset trên production. Với test tự động, mỗi test nên dùng dữ liệu có khóa riêng hoặc schema/database cô lập để tránh đua dữ liệu giữa các test.

### 4.3. Giữ đặc tính dữ liệu quan trọng

Không chỉ giữ số lượng hàng. Lỗi có thể phụ thuộc:

- Tỷ lệ NULL, giá trị trùng và phân bố giá trị của cột.
- Độ lệch phân bố, skew, cardinality và selectivity của predicate.
- Chuỗi Unicode, collation, hoa/thường, dấu hoặc khoảng trắng cuối.
- Giá trị DECIMAL có scale, số âm, biên BIGINT và phép ép kiểu.
- Ngày nhuận, timezone, fractional seconds hoặc zero date trong dữ liệu cũ.
- Quan hệ foreign key, thứ tự insert và cascade.
- Số hàng mỗi partition, index statistics và dữ liệu lịch sử.

Nếu phải dùng dữ liệu tổng hợp thay production, hãy giữ những đặc tính gây lỗi nhưng thay danh tính và giá trị nhạy cảm. Ghi rõ cách tạo dữ liệu để người khác có thể tái tạo cùng fixture.

## 5. Ghi lại SQL, bind parameter và kết quả

### 5.1. SQL phải đi kèm kiểu và giá trị tham số

Prepared statement không chỉ là câu SQL có dấu hỏi. Cần ghi thứ tự, kiểu dữ liệu JDBC và giá trị đã được làm sạch của từng tham số. Ví dụ:

~~~sql
UPDATE inventory
SET quantity = quantity - ?
WHERE product_id = ?
  AND quantity >= ?;
~~~

| Vị trí | Kiểu JDBC | Giá trị test |
|---:|---|---:|
| 1 | INTEGER | 1 |
| 2 | BIGINT | 101 |
| 3 | INTEGER | 1 |

Nếu driver bind một tham số là VARCHAR thay vì BIGINT, MySQL có thể thực hiện conversion khác, ảnh hưởng index hoặc kết quả so sánh. Ghi cả cách ứng dụng bind, không chỉ câu SQL được copy từ log.

Không thay parameter bằng literal một cách tùy tiện khi tái hiện. Literal có thể khiến optimizer chọn execution plan khác với prepared statement hoặc thay đổi kiểu suy luận.

### 5.2. Ghi expected và actual result

Với mỗi bước, ghi:

- Số hàng trả về.
- Giá trị cột liên quan, kể cả NULL.
- Số hàng bị ảnh hưởng (executeUpdate hoặc affected rows).
- SQLSTATE, mã lỗi vendor và thông báo lỗi nguyên văn.
- Warning nếu có, ví dụ SHOW WARNINGS ngay sau câu lệnh liên quan.
- Thời gian thực thi và timeout.
- Trạng thái transaction: active, committed hoặc rolled back.

Kết quả truy vấn không có ORDER BY không có thứ tự hàng được bảo đảm. Nếu lỗi liên quan thứ tự, thêm ORDER BY rõ ràng vào test theo hợp đồng mong đợi; không coi thứ tự tình cờ của một execution plan là kết quả ổn định.

Với giá trị số thập phân, so sánh theo precision/scale nghiệp vụ; không chuyển DECIMAL sang double rồi so sánh bằng phép bằng tuyệt đối. Với thời gian, ghi timezone session và precision cột.

## 6. Ghi lại transaction boundary và tính đồng thời

Nhiều lỗi chỉ xuất hiện khi hai hoặc nhiều transaction chạy xen kẽ. Một câu SQL riêng lẻ không tái hiện được lost update, write skew, deadlock hoặc đọc dữ liệu chưa commit.

### 6.1. Ghi đầy đủ trình tự các session

Với mỗi session, ghi:

- Tên session logic và connection/thread ID nếu có.
- Thời điểm bắt đầu/kết thúc từng câu lệnh.
- START TRANSACTION, COMMIT, ROLLBACK và autocommit.
- Isolation level.
- Dữ liệu đọc được trước khi ghi.
- Lock được yêu cầu, lock wait và lỗi nhận được.

Ví dụ lịch xen kẽ của hai session:

~~~text
Session A                         Session B
BEGIN                             BEGIN
SELECT quantity = 1               SELECT quantity = 1
UPDATE quantity = quantity - 1
                                  UPDATE quantity = quantity - 1
COMMIT                            COMMIT hoặc lỗi/rollback
~~~

Đây chỉ là khung timeline. Packet thực tế phải ghi kết quả và thời điểm chính xác để xác định session nào chờ, session nào commit và transaction nào bị rollback.

### 6.2. Ghi isolation level và autocommit

Thu thập:

~~~sql
SELECT
  @@session.transaction_isolation,
  @@session.autocommit,
  @@session.innodb_lock_wait_timeout;
~~~

Isolation level ảnh hưởng snapshot và hành vi khóa. READ COMMITTED, REPEATABLE READ và SERIALIZABLE có thể tạo kết quả quan sát khác nhau. Autocommit cũng quyết định mỗi câu lệnh là một transaction riêng hay thuộc transaction do ứng dụng mở.

Khi tái hiện, phải giữ đúng ranh giới transaction của ứng dụng. Chạy từng câu lệnh trong SQL console với autocommit mặc định có thể không tái hiện lỗi xảy ra trong @Transactional hoặc transaction JDBC nhiều câu.

### 6.3. Thu thập thông tin lock và deadlock

Trong MySQL 8, Performance Schema có thể cung cấp dữ liệu lock hiện tại:

~~~sql
SELECT * FROM performance_schema.data_locks;
SELECT * FROM performance_schema.data_lock_waits;
~~~

Các bảng này cần Performance Schema được bật và quyền đọc phù hợp; cấu trúc chi tiết phụ thuộc phiên bản. Với deadlock InnoDB, thu thập:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Phần LATEST DETECTED DEADLOCK có thể cho biết transaction, index và lock liên quan. Lưu log ngay sau sự kiện vì thông tin “latest” có thể bị thay thế bởi deadlock mới. Với lỗi metadata lock, kiểm tra metadata_locks trong Performance Schema và transaction đang giữ DDL/DML liên quan.

Không chỉ ghi “deadlock xảy ra”. Cần lưu hai câu lệnh tranh chấp, index/record được khóa, thứ tự lấy khóa và transaction bị chọn làm victim. Đây là cơ sở để sửa thứ tự cập nhật, rút ngắn transaction hoặc bổ sung retry an toàn.

## 7. Thu thập execution plan và bằng chứng hiệu năng

Khi lỗi liên quan truy vấn chậm, timeout hoặc tải tăng, packet cần chứa cả SQL, tham số, schema, index và execution plan. Chỉ lưu ảnh chụp thời gian chạy không giúp xác định optimizer đã chọn access path nào.

### 7.1. EXPLAIN và EXPLAIN ANALYZE

Với truy vấn đọc, thu thập plan:

~~~sql
EXPLAIN FORMAT=TREE
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 9001
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

Từ MySQL 8.0.18, có thể dùng EXPLAIN ANALYZE để thực thi câu SELECT và ghi thời gian thực tế, số vòng lặp và số hàng qua từng iterator:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 9001
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

EXPLAIN ANALYZE thực sự chạy câu truy vấn. Chỉ dùng với câu lệnh đọc an toàn, trên môi trường được phép và sau khi đánh giá chi phí. Không áp dụng trực tiếp cho câu lệnh có side effect hoặc truy vấn có thể quét lượng dữ liệu rất lớn trên production trong giờ cao điểm.

Ghi lại các dấu hiệu:

- Access type và index được chọn.
- Estimated rows so với actual rows.
- Filter và điều kiện được đẩy xuống storage engine.
- Sort, temporary table, materialization và join order.
- Iterator có thời gian hoặc số vòng lặp bất thường.
- Chênh lệch lớn giữa ước lượng và thực tế.

Plan có thể thay đổi theo phiên bản server, statistics, kích thước dữ liệu, parameter value và trạng thái cache. Khi so sánh hai môi trường, dùng cùng fixture hoặc dữ liệu đại diện, cùng kiểu tham số và cùng cách chạy.

### 7.2. Ghi nhận statistics và cấu trúc index

Optimizer dựa vào statistics để ước lượng cardinality và chọn kế hoạch. Ghi lại:

~~~sql
SHOW INDEX FROM orders;
SHOW TABLE STATUS LIKE 'orders';
~~~

Với MySQL 8, có thể xem histogram nếu bảng đã tạo histogram:

~~~sql
SELECT *
FROM information_schema.column_statistics
WHERE schema_name = 'app_db'
  AND table_name = 'orders';
~~~

Không chạy ANALYZE TABLE chỉ để làm packet “đẹp hơn” trước khi ghi nhận trạng thái ban đầu. Lệnh này có thể cập nhật statistics và làm thay đổi plan; nếu cần kiểm tra tác động, ghi rõ thời điểm, lệnh đã chạy và plan trước/sau.

### 7.3. Slow query log và Performance Schema

Khi có quyền và cấu hình cho phép, lấy log truy vấn chậm hoặc thống kê digest từ Performance Schema. Digest giúp nhóm các câu SQL cùng cấu trúc dù giá trị tham số khác nhau. Nên ghi:

- Digest hoặc câu SQL đã làm sạch.
- Số lần thực thi và tổng thời gian.
- Thời gian trung bình, tối đa và phân vị nếu hệ thống thu thập.
- Rows examined, rows sent và temporary table.
- Thời điểm thu thập, cửa sổ quan sát và cấu hình slow query log.

Slow query log có thể chứa literal nhạy cảm. Làm sạch giá trị trước khi đưa vào packet. Không bật logging nặng hoặc thay đổi global configuration trên production khi chưa đánh giá tác động và quy trình phê duyệt.

## 8. Thiết kế regression test từ lỗi đã tái hiện

Regression test phải thất bại khi lỗi còn tồn tại và thành công sau khi bản sửa được áp dụng. Nếu test chỉ kiểm tra code path mới mà không tái hiện điều kiện gây lỗi, nó có thể bỏ sót chính lỗi ban đầu.

### 8.1. Chọn đúng tầng kiểm thử

| Loại test | Dùng để kiểm tra | Ví dụ MySQL |
|---|---|---|
| Unit test | Logic thuần không cần database | Tính số lượng, quy tắc làm tròn hoặc validate input |
| Repository/integration test | SQL, mapping, constraint và transaction thật | Query lọc, join, generated key, rollback |
| Migration test | Thay đổi schema qua các phiên bản | Upgrade schema cũ, kiểm tra index và dữ liệu sau migration |
| Concurrency test | Tương tác nhiều transaction | Trừ tồn kho đồng thời, chống double booking |
| Performance test | Throughput, latency và tài nguyên | So sánh plan và p95 sau thay index |
| Security test | Quyền và cách ly dữ liệu | Account chỉ đọc không thể INSERT/UPDATE |

Lỗi phụ thuộc MySQL behavior nên có integration test chạy trên đúng dòng server mục tiêu. H2 hoặc database giả lập có thể hữu ích cho một số unit test nhưng không thay thế MySQL khi cần xác minh dialect, collation, locking, JSON, index hoặc transaction semantics.

### 8.2. Viết test có trạng thái ban đầu và kết quả rõ ràng

Một test repository nên:

1. Tạo fixture có khóa riêng.
2. Chạy đúng câu lệnh hoặc service method đã gây lỗi.
3. Đọc lại trạng thái từ database trong transaction phù hợp.
4. Assert kết quả nghiệp vụ, affected rows và constraint.
5. Dọn dữ liệu hoặc rollback theo cơ chế test.

Ví dụ kiểm tra cập nhật có điều kiện:

~~~java
@Test
void shouldNotDecreaseInventoryBelowZero() {
    inventoryRepository.insert(101L, 1);

    int firstUpdate = inventoryRepository.reserve(101L, 1);
    int secondUpdate = inventoryRepository.reserve(101L, 1);

    assertThat(firstUpdate).isEqualTo(1);
    assertThat(secondUpdate).isZero();
    assertThat(inventoryRepository.quantityOf(101L)).isZero();
}
~~~

Đoạn test minh họa giả định reserve dùng một câu UPDATE có điều kiện tương đương:

~~~sql
UPDATE inventory
SET quantity = quantity - ?
WHERE product_id = ?
  AND quantity >= ?;
~~~

Affected rows bằng 0 có nghĩa không có hàng thỏa điều kiện để cập nhật. Trong ứng dụng thật, cần phân biệt sản phẩm không tồn tại với tồn kho không đủ nếu hợp đồng nghiệp vụ yêu cầu hai lỗi khác nhau.

### 8.3. Test transaction atomicity

Nếu một nghiệp vụ cập nhật nhiều bảng, kiểm tra rằng lỗi ở bước sau không để lại một phần thay đổi đã commit. Ví dụ, tạo order và giảm inventory phải cùng commit hoặc cùng rollback trong một transaction.

Kiểm tra:

- Khi mọi bước thành công, cả hai thay đổi đều tồn tại.
- Khi bước thứ hai thất bại, order không được lưu một phần.
- Khi ứng dụng ném exception, transaction manager có rollback theo quy tắc đã định.
- Không có external side effect được phát đi trước khi transaction commit nếu nghiệp vụ yêu cầu tính nguyên tử.

### 8.4. Test concurrency có đồng bộ

Test concurrency cần điều khiển được điểm hai transaction cùng bắt đầu. Dùng CountDownLatch, CyclicBarrier hoặc cơ chế đồng bộ tương đương để tạo lịch chạy có chủ đích. Tránh dùng Thread.sleep làm công cụ đồng bộ chính vì thời gian chạy phụ thuộc máy và tải.

Với bài toán đặt chỗ cuối cùng, tạo một bản ghi còn một chỗ, khởi chạy hai transaction gần như đồng thời và xác minh:

- Tối đa một transaction đặt chỗ thành công.
- Transaction còn lại nhận kết quả “hết chỗ” hoặc lỗi đã được định nghĩa.
- Số chỗ cuối cùng không âm.
- Không có hai reservation hợp lệ cho cùng một slot duy nhất.

Chạy test nhiều lần với barrier và connection riêng cho mỗi worker. Ghi isolation level, autocommit, transaction boundary và cách xử lý deadlock/lock timeout. Retry chỉ an toàn nếu thao tác có tính idempotent hoặc có khóa nghiệp vụ ngăn tạo bản ghi trùng.

## 9. Chạy test trên MySQL thật và môi trường cô lập

### 9.1. Pin phiên bản server

Dùng MySQL container hoặc instance test được quản lý để tạo môi trường cô lập. Pin image theo patch tag hoặc digest đã duyệt; không dùng tag latest vì cùng một test có thể chạy trên server khác nhau ở các lần build.

Môi trường test nên khớp các yếu tố ảnh hưởng đến lỗi:

- Phiên bản và edition MySQL.
- SQL mode, timezone, charset và collation.
- Storage engine, plugin và cấu hình transaction.
- Schema migration và index.
- Authentication, TLS và quyền ứng dụng nếu test liên quan.

Testcontainers là một lựa chọn cho Java integration test. Ví dụ dưới đây minh họa cách cấp JDBC URL từ container cho Spring Boot; thay image bằng patch version hoặc digest đã được dự án phê duyệt:

~~~java
@Testcontainers
@SpringBootTest
class OrderRepositoryIT {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4.4");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
    }
}
~~~

Ví dụ dùng một tag cụ thể để minh họa. Khi áp dụng, cần chọn patch tag/digest còn được hỗ trợ trong dự án và dùng cùng image trong CI lẫn môi trường tái hiện. Nếu lỗi phụ thuộc cấu hình production, bổ sung các biến và script khởi tạo tương ứng.

### 9.2. Không để test phụ thuộc thứ tự

Mỗi test cần tự tạo dữ liệu và không dựa vào kết quả của test chạy trước. Cần xử lý:

- Tên khóa và dữ liệu duy nhất để các test chạy song song không va chạm.
- Transaction rollback không dọn được dữ liệu do test commit.
- Event scheduler, trigger hoặc background worker gây thay đổi ngoài dự kiến.
- Timezone, clock và ngày hiện tại khiến test thay đổi theo thời điểm chạy.
- Random seed không được ghi lại khiến lỗi không tái hiện.
- Test chạy song song dùng chung database hoặc schema.

Nếu test phụ thuộc thời gian, inject Clock trong ứng dụng để cố định instant. Nếu cần kiểm tra NOW() của MySQL, ghi timezone session và tạo khoảng thời gian test rõ ràng; không giả định đồng hồ JVM và server hoàn toàn trùng nhau.

## 10. Đánh giá hồi quy hiệu năng

Một bản sửa có thể làm kết quả đúng nhưng truy vấn chậm hơn, tạo thêm lock hoặc tăng số connection. Với lỗi hiệu năng, cần so sánh baseline trước và sau trên môi trường tương đương.

Các số đo nên có:

| Chỉ số | Điều cần so sánh |
|---|---|
| Throughput | Số transaction hoặc truy vấn thành công mỗi giây |
| Latency | p50, p95, p99 và timeout |
| Rows examined | Số hàng MySQL phải đọc để trả kết quả |
| Rows sent | Số hàng trả về client |
| Execution plan | Access path, join order, sort, temporary table và iterator |
| Locking | Lock wait, deadlock và transaction duration |
| Resource | CPU, memory, I/O và connection count |

Chạy cùng dữ liệu, cùng tham số, cùng mức tải và cùng cấu hình. Thực hiện nhiều lượt sau warm-up; ghi rõ test cache nóng hay lạnh. Không so sánh một lượt chạy đơn lẻ khi biến động hệ thống lớn.

Đặt ngưỡng hồi quy theo SLO và baseline thực tế. Ví dụ, p95 không tăng quá ngưỡng đã thống nhất trong khi throughput giữ hoặc tăng. Không dùng một execution plan text làm tiêu chí duy nhất: optimizer có thể chọn plan khác nhưng vẫn nhanh hơn trên dữ liệu thực tế.

## 11. Phân loại lỗi từ bằng chứng

Evidence packet giúp khoanh vùng theo nhóm:

| Dấu hiệu | Nhóm cần điều tra | Bằng chứng tiếp theo |
|---|---|---|
| Kết quả hàng sai nhưng SQL chạy thành công | Logic SQL hoặc dữ liệu | Fixture, parameter, schema, expected/actual |
| Duplicate key hoặc constraint violation | Schema và quy tắc nghiệp vụ | SHOW CREATE TABLE, index, transaction timeline |
| Lỗi chỉ xuất hiện khi có nhiều request | Concurrency/locking | Session timeline, isolation, data_locks, deadlock |
| Query chậm sau deploy | Optimizer/schema/configuration | EXPLAIN, statistics, SQL mode, version và benchmark |
| App lỗi nhưng SQL console chạy được | JDBC/ORM/pool/session | Bind types, driver version, connection properties, session variables |
| Chỉ một account bị lỗi | Privilege/authentication | CURRENT_USER, SHOW GRANTS, plugin và TLS |
| Test chạy riêng thành công nhưng CI thất bại | Isolation/flaky test/environment | Seed, timezone, shared database, parallelism và server image |
| Lỗi sau migration | Schema evolution/data compatibility | Migration order, DDL, data conversion và schema diff |

Không kết luận ngay lỗi thuộc MySQL chỉ vì stack trace có SQLException. SQLException có thể phản ánh lỗi từ server, network, driver, timeout của pool hoặc transaction manager. Hãy dùng SQLSTATE, vendor error code, nested cause và thời điểm lỗi để phân lớp.

## 12. Bảo vệ dữ liệu trong evidence packet

Log và dữ liệu tái hiện có thể chứa thông tin cá nhân, thông tin thanh toán, token hoặc bí mật kết nối. Trước khi chia sẻ:

- Thay tên, email, số điện thoại, địa chỉ và mã định danh bằng dữ liệu giả.
- Loại bỏ password, token, private key, cookie và secret trong JDBC URL.
- Không xuất password hash từ mysql.user.
- Giữ lại kiểu dữ liệu, độ dài, phân bố, quan hệ và đặc tính gây lỗi sau khi ẩn danh.
- Giới hạn quyền truy cập packet và thời gian lưu giữ theo chính sách tổ chức.
- Ghi rõ dữ liệu đã được thay đổi để người nhận không nhầm với dữ liệu gốc.

Không gửi dump production nguyên vẹn chỉ vì nó tái hiện lỗi dễ hơn. Nếu cần một mẫu dữ liệu lớn để kiểm tra optimizer, tạo dữ liệu tổng hợp có phân bố tương tự và ghi script tạo dữ liệu.

## 13. Checklist tái hiện và đánh giá hồi quy

### Trước khi tái hiện

- [ ] Viết expected result và actual result riêng biệt.
- [ ] Ghi phiên bản MySQL, driver, framework và cấu hình session.
- [ ] Thu thập schema, index, quyền và migration version.
- [ ] Tạo fixture tối thiểu, ẩn danh và có thể reset.
- [ ] Ghi SQL, kiểu bind parameter và giá trị tham số.
- [ ] Ghi transaction boundary, isolation và autocommit.
- [ ] Với lỗi đồng thời, ghi timeline của từng session.
- [ ] Với lỗi hiệu năng, lưu EXPLAIN và số đo baseline.

### Sau khi sửa

- [ ] Chạy lại đúng test tái hiện ban đầu.
- [ ] Thêm regression test ở đúng tầng kiểm thử.
- [ ] Chạy test trên phiên bản MySQL mục tiêu.
- [ ] Chạy migration test nếu schema thay đổi.
- [ ] Kiểm tra atomicity, constraint và dữ liệu sau commit/rollback.
- [ ] Chạy concurrency test nếu lỗi liên quan nhiều transaction.
- [ ] So sánh latency, throughput và tài nguyên nếu có ảnh hưởng hiệu năng.
- [ ] Lưu test output và cập nhật manifest của evidence packet.

## 14. Tình huống thực hành

Một API bán hàng thỉnh thoảng tạo hai đơn hàng thành công dù sản phẩm chỉ còn một đơn vị tồn kho. Nhóm chỉ có log “order created” và một ảnh chụp bảng inventory sau sự cố.

Hãy lập packet để tái hiện:

1. Ghi phiên bản MySQL, engine, schema, index, SQL mode, isolation level và autocommit.
2. Tạo fixture gồm một sản phẩm với quantity bằng 1 và bảng orders có khóa chính/foreign key như production.
3. Thu thập câu SQL thực tế dùng để đọc tồn kho, tạo đơn và trừ kho; ghi bind parameter cùng transaction boundary.
4. Dựng hai session có connection riêng, đồng bộ điểm bắt đầu bằng barrier để tạo hai yêu cầu đồng thời.
5. Ghi timeline đọc/ghi/commit, affected rows, lock wait và kết quả cuối của cả hai session.
6. Xác định invariant: không có quantity âm và tối đa một đơn hàng được xác nhận cho một đơn vị tồn kho.
7. Tạo test hồi quy kiểm tra hai transaction đồng thời; chạy nhiều lần trên đúng phiên bản MySQL.
8. Sau khi sửa, xác minh một transaction thành công, transaction còn lại bị từ chối hoặc retry theo quy tắc, dữ liệu cuối đúng và không phát sinh deadlock ngoài dự kiến.

Một giải pháp có thể là UPDATE có điều kiện và kiểm tra affected rows trong cùng transaction tạo order. Nếu cập nhật tồn kho không thành công, không được commit đơn hàng. Test phải xác minh toàn bộ trạng thái sau commit/rollback, không chỉ mã HTTP trả về.

## 15. Câu hỏi tự kiểm tra

1. Một evidence packet cần những thành phần nào để người khác chạy lại lỗi?
2. Vì sao phải ghi SQL cùng kiểu và giá trị bind parameter?
3. Vì sao schema cần giữ cả index, constraint, collation và storage engine?
4. Những thông tin nào cần có trong timeline của lỗi deadlock hoặc lost update?
5. EXPLAIN ANALYZE khác EXPLAIN ở điểm nào và cần thận trọng ra sao khi chạy?
6. Vì sao H2 không thay thế được MySQL integration test cho lỗi locking hoặc collation?
7. Làm thế nào tạo concurrency test ổn định mà không phụ thuộc Thread.sleep?
8. Khi nào cần đánh giá regression hiệu năng ngoài việc kiểm tra kết quả dữ liệu?
9. Làm thế nào ẩn danh fixture mà vẫn giữ đặc tính dữ liệu gây lỗi?
10. Vì sao một regression test cần thất bại trước bản sửa và thành công sau bản sửa?

Bằng chứng tốt biến lỗi khó tái hiện thành một tình huống có thể chạy lại, quan sát và kiểm chứng. Khi packet giữ đủ fingerprint môi trường, schema, fixture, SQL, tham số, transaction timeline và expected result, nhóm có thể tìm đúng nguyên nhân, tạo regression test đáng tin cậy và đánh giá tác động của bản sửa trước khi phát hành.
