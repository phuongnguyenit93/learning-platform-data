# Schema drift, thứ tự migration và khóa triển khai đồng thời

Schema của MySQL thay đổi theo vòng đời ứng dụng: thêm bảng, thêm cột, tạo index, đổi kiểu dữ liệu hoặc loại bỏ cấu trúc cũ. Khi nhiều môi trường, nhiều nhánh phát triển hoặc nhiều dịch vụ cùng thay đổi database, cấu trúc thực tế có thể lệch khỏi cấu trúc mà mã nguồn và migration mong đợi. Hiện tượng đó gọi là **schema drift**. Nếu các migration chạy sai thứ tự hoặc chạy đồng thời, ứng dụng có thể gặp lỗi ngay cả khi từng migration riêng lẻ đã được kiểm thử.

Bài học này tập trung vào ba vấn đề liên quan chặt chẽ: phát hiện và xử lý schema drift, quản lý thứ tự migration, và khóa để chỉ một tiến trình triển khai schema thực hiện thay đổi tại một thời điểm. Trong module `DATABASE_MYSQL`, nội dung kết nối thiết kế bảng, DDL, transaction, metadata lock và vận hành triển khai.

Sau bài học, bạn có thể:

- Phân biệt schema drift với một migration hợp lệ chưa được triển khai.
- So sánh schema thực tế với schema chuẩn và xác định sai lệch.
- Quản lý migration có thứ tự, checksum và lịch sử thực thi.
- Hiểu ảnh hưởng của implicit commit và metadata lock trong MySQL DDL.
- Ngăn nhiều pipeline hoặc nhiều phiên bản ứng dụng chạy migration đồng thời.
- Triển khai thay đổi tương thích theo mô hình expand-contract.
- Xử lý migration lỗi giữa chừng và lập quy trình kiểm tra sau triển khai.

## 1. Schema drift là gì?

Schema drift xảy ra khi cấu trúc database đang chạy khác với cấu trúc được khai báo trong migration, schema manifest hoặc mô hình dữ liệu chuẩn của dự án. Sai lệch có thể xuất hiện ở nhiều nơi:

- Một cột được thêm thủ công trên production nhưng không có migration tương ứng trong repository.
- Migration đã chạy trên staging nhưng chưa chạy trên production.
- Một nhánh phát triển đổi kiểu cột trong khi nhánh khác thêm index dựa trên định nghĩa cũ.
- Một hotfix thay đổi default, nullability hoặc collation mà không cập nhật migration.
- Một bảng hoặc index bị xóa thủ công trong lúc xử lý sự cố.
- Hai môi trường chạy các phiên bản migration khác nhau dù cùng được gọi là staging.

Không phải mọi khác biệt đều là lỗi. Một môi trường có thể cố ý có thêm bảng phục vụ kiểm thử hoặc có cấu hình khác về tài nguyên. Điều quan trọng là phân loại sai lệch: cấu trúc nào thuộc hợp đồng ứng dụng, cấu trúc nào là cấu hình riêng của môi trường và cấu trúc nào là thay đổi ngoài quy trình.

### 1.1. Drift có thể ảnh hưởng điều gì?

| Loại sai lệch | Ví dụ | Hậu quả có thể xảy ra |
|---|---|---|
| Thiếu cấu trúc | Thiếu cột `customer_status` | Ứng dụng mới lỗi khi truy vấn cột |
| Cấu trúc thừa | Production có bảng do hotfix tạo | Migration sau đó có thể gặp tên đối tượng đã tồn tại |
| Khác kiểu dữ liệu | `VARCHAR(100)` ở môi trường này, `VARCHAR(255)` ở môi trường khác | Khác hành vi lưu trữ, index hoặc kiểm tra dữ liệu |
| Khác null/default | Một môi trường cho phép `NULL`, môi trường khác yêu cầu `NOT NULL` | Insert có thể thành công ở nơi này và thất bại ở nơi khác |
| Khác index/constraint | Thiếu unique index hoặc foreign key | Truy vấn chậm hoặc dữ liệu trùng, mồ côi |
| Khác charset/collation | `utf8mb4_0900_ai_ci` so với collation khác | So sánh chuỗi, sort và tính duy nhất khác nhau |
| Lịch sử migration lệch | Bảng migration ghi version đã chạy nhưng schema thực tế chưa hoàn tất | Công cụ triển khai bỏ qua bước cần thiết hoặc migration tiếp theo thất bại |

Schema drift có thể âm thầm tồn tại lâu trước khi gây lỗi. Ví dụ, thiếu index không làm ứng dụng dừng ngay nhưng có thể khiến truy vấn chậm khi dữ liệu tăng. Thiếu unique constraint có thể tạo bản ghi trùng mà ứng dụng chỉ phát hiện nhiều tuần sau.

## 2. Chọn một nguồn sự thật cho schema

Một dự án cần xác định rõ nguồn nào mô tả schema mong muốn. Thông thường, đó là các migration có phiên bản được lưu trong repository. Một số hệ thống còn sinh schema manifest hoặc DDL chuẩn từ công cụ quản lý schema.

Các nguyên tắc quan trọng:

1. **Mọi thay đổi schema phải có migration được review.** Thay đổi trực tiếp trên môi trường dùng chung chỉ nên dành cho tình huống khẩn cấp và phải được ghi nhận thành migration ngay sau đó.
2. **Migration đã áp dụng là bất biến.** Không sửa nội dung migration cũ sau khi đã chạy trên bất kỳ môi trường dùng chung nào. Tạo migration mới để sửa tiếp.
3. **Mỗi migration có định danh duy nhất và thứ tự rõ ràng.** Có thể dùng số thứ tự hoặc timestamp cùng tên mô tả.
4. **Lịch sử thực thi phải được lưu trong database.** Công cụ cần biết migration nào đã chạy, checksum nào đã được áp dụng và kết quả ra sao.
5. **Không đồng nhất lịch sử migration với trạng thái schema.** Bảng lịch sử cho biết công cụ đã ghi nhận điều gì; kiểm tra schema thực tế vẫn cần thiết.

Ví dụ tên migration:

```text
202611190900_add_customer_status.sql
202611190930_create_customer_status_index.sql
202611191000_backfill_customer_status.sql
202611191100_enforce_customer_status_not_null.sql
```

Tên thời gian chỉ là ví dụ. Nếu nhiều nhánh có thể tạo migration cùng lúc, nhóm cần quy ước cấp số hoặc tạo timestamp đủ độ phân giải và xử lý xung đột khi merge. Không để hai migration khác nội dung dùng chung một version.

## 3. Phát hiện schema drift

Phát hiện drift cần so sánh cấu trúc thực tế với cấu trúc chuẩn. Nên so sánh ở mức metadata có cấu trúc thay vì chỉ so chuỗi `SHOW CREATE TABLE`, vì output có thể khác do phiên bản MySQL, thứ tự hiển thị hoặc các thuộc tính mặc định.

### 3.1. Kiểm kê bảng và engine

Chạy trên từng môi trường:

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_COLLATION,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

`TABLE_ROWS` của InnoDB thường là ước lượng, không phải số đếm chính xác. Truy vấn này dùng để kiểm kê cấu trúc và nhận biết khác biệt về engine/collation; không dùng `TABLE_ROWS` làm bằng chứng đối soát chính xác dữ liệu.

### 3.2. So sánh cột

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

Xuất kết quả từ các môi trường và so sánh với manifest đã được review. Cần chú ý `COLUMN_TYPE`, nullability, default, `EXTRA` (ví dụ auto increment hoặc generated column), charset và collation. Với default biểu thức, hãy kiểm tra cách server biểu diễn giá trị để tránh coi khác biệt định dạng là drift thực.

### 3.3. So sánh index và khóa

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

Kiểm tra cả thứ tự cột trong composite index, unique/non-unique và loại index. Hai index có cùng tập cột nhưng khác thứ tự cột không tương đương cho mọi truy vấn.

Kiểm tra foreign key:

```sql
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
```

Có thể kiểm tra riêng `CHECK_CONSTRAINTS`, `TABLE_CONSTRAINTS`, trigger, view và routine nếu chúng thuộc hợp đồng schema của ứng dụng.

### 3.4. Chuẩn hóa kết quả so sánh

Một công cụ so sánh nên:

- Lấy schema chuẩn từ migration hoặc manifest đã được review.
- Lấy metadata thực tế từ `INFORMATION_SCHEMA` và `SHOW CREATE` khi cần xác minh chi tiết.
- Chuẩn hóa các giá trị mặc định, tên schema, kiểu dữ liệu và thuộc tính phụ thuộc phiên bản.
- Bỏ qua các thuộc tính môi trường đã được cho phép khác nhau.
- Xuất diff có loại đối tượng, giá trị mong đợi, giá trị thực tế và mức độ ảnh hưởng.

Không tự động chạy `ALTER TABLE` cho mọi khác biệt mà công cụ phát hiện. Một diff có thể cần quyết định của người sở hữu dữ liệu, nhất là khi thay đổi liên quan đến xóa cột, thu hẹp kiểu dữ liệu hoặc thêm constraint trên dữ liệu hiện hữu.

## 4. Lịch sử migration và checksum

Một bảng migration history thường lưu version, checksum và thời điểm áp dụng. Ví dụ đơn giản:

```sql
CREATE TABLE schema_migrations (
    version VARCHAR(100) NOT NULL,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    execution_ms BIGINT UNSIGNED NULL,
    applied_by VARCHAR(128) NULL,
    PRIMARY KEY (version)
) ENGINE=InnoDB;
```

Các công cụ như Flyway, Liquibase hoặc framework migration riêng có thể dùng schema và tên cột khác. Hãy để công cụ sở hữu bảng lịch sử của nó; không tự đổi cấu trúc bảng do công cụ quản lý nếu chưa theo tài liệu.

Checksum giúp phát hiện file migration đã bị sửa sau khi chạy. Khi công cụ phát hiện checksum khác, hãy xem đó là dấu hiệu cần điều tra. Không cập nhật checksum trong bảng history để che giấu thay đổi file.

Một quy trình migration có thể thực hiện:

1. Đọc danh sách migration theo thứ tự.
2. Đối chiếu version đã chạy với file hiện có.
3. Xác minh checksum của migration đã áp dụng.
4. Kiểm tra điều kiện trước migration mới.
5. Chạy một migration theo đúng thứ tự.
6. Xác minh kết quả DDL và ghi lịch sử theo cơ chế của công cụ.
7. Chuyển sang migration tiếp theo sau khi bước trước thành công.

Nếu migration lỗi giữa chừng, không mặc định MySQL đã rollback toàn bộ thay đổi. Kiểm tra schema thực tế, log, bảng history và trạng thái kết nối trước khi quyết định sửa hoặc chạy lại.

## 5. Thứ tự migration và phụ thuộc giữa thay đổi

Migration cần chạy theo thứ tự sao cho mọi trạng thái trung gian đều an toàn. Ví dụ, nếu ứng dụng cần đọc cột mới, cột đó phải tồn tại trước khi phiên bản ứng dụng sử dụng nó được triển khai. Nếu một index cần được tạo trước khi bật truy vấn mới, phải xác nhận index đã sẵn sàng trước khi chuyển traffic.

Một migration có thể phụ thuộc vào:

- Bảng hoặc cột được tạo trong migration trước.
- Dữ liệu được backfill trước khi thêm `NOT NULL` hoặc constraint.
- Index được tạo trước khi truy vấn mới nhận tải lớn.
- Phiên bản ứng dụng đã ngừng đọc/ghi cột cũ trước khi drop cột.
- Một dịch vụ khác đã triển khai tương thích với schema dùng chung.

Không dựa vào thứ tự file tình cờ của filesystem. Công cụ migration phải sắp xếp theo version rõ ràng và từ chối xung đột version hoặc checksum không khớp.

### 5.1. Tránh migration song song từ nhiều nhánh

Giả sử nhánh A thêm `customer_status`, còn nhánh B tạo index trên `customer_status`. Nếu migration của nhánh B chạy trước migration tạo cột, lệnh `CREATE INDEX` sẽ thất bại. Khi merge, cần xác định phụ thuộc và thứ tự version trước khi triển khai.

Các quy ước hữu ích:

- Mỗi migration có version duy nhất trên toàn repository.
- Không rebase hoặc đổi nội dung migration đã áp dụng ở môi trường dùng chung.
- Migration phụ thuộc phải khai báo hoặc thể hiện rõ trong thứ tự version.
- CI tạo database sạch và chạy toàn bộ migration theo thứ tự để phát hiện phụ thuộc bị thiếu.
- CI cũng thử nâng cấp từ schema gần production, vì chạy từ database rỗng không phát hiện được mọi drift.

## 6. MySQL DDL, implicit commit và giới hạn rollback

MySQL xử lý nhiều câu DDL như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` và `CREATE INDEX` với implicit commit. Điều đó có nghĩa là không thể coi một chuỗi DDL như một transaction InnoDB thông thường rồi mong `ROLLBACK` khôi phục tất cả cấu trúc.

Ví dụ:

```sql
START TRANSACTION;

ALTER TABLE customers
    ADD COLUMN customer_status VARCHAR(20) NULL;

ROLLBACK;
```

Không nên kỳ vọng `ROLLBACK` xóa cột vừa thêm. DDL có thể đã commit ngầm trước hoặc sau thao tác tùy câu lệnh và phiên bản. MySQL 8.0 hỗ trợ atomic DDL cho nhiều thao tác được hỗ trợ, giúp thao tác DDL có tính nguyên tử trước sự cố trong phạm vi server; **atomic DDL không đồng nghĩa DDL tham gia transaction ứng dụng hoặc có thể rollback bằng `ROLLBACK`**.

Vì vậy:

- Chia thay đổi thành các bước nhỏ có thể kiểm tra.
- Có migration khắc phục rõ ràng thay vì trông chờ rollback transaction.
- Sao lưu và thử trên dữ liệu có quy mô gần thực tế trước thay đổi lớn.
- Xác minh trạng thái schema sau mỗi DDL quan trọng.
- Lập phương án xử lý khi DDL hoàn tất nhưng migration history chưa được ghi.

Nếu lệnh DDL lỗi, một số thao tác có thể chưa thay đổi schema, nhưng cũng có trường hợp migration gồm nhiều DDL và các câu trước đã hoàn tất. Luôn kiểm tra trạng thái thực tế trước khi chạy lại toàn bộ file.

## 7. Metadata lock và thời gian chờ DDL

MySQL dùng metadata lock (MDL) để bảo vệ metadata của bảng và các đối tượng schema. Truy vấn đang sử dụng bảng hoặc transaction chưa kết thúc có thể giữ metadata lock, khiến DDL cần lock tương thích phải chờ. Ngược lại, DDL đang chờ có thể làm các truy vấn mới xếp hàng phía sau, tạo ra hiện tượng nghẽn bất ngờ.

Ví dụ, một session mở transaction, đọc bảng `orders` rồi để transaction ở trạng thái idle. Một session khác chạy `ALTER TABLE orders ...`. DDL có thể phải chờ transaction đầu kết thúc để lấy metadata lock cần thiết.

Kiểm tra metadata lock qua Performance Schema:

```sql
SELECT
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    th.PROCESSLIST_ID,
    th.PROCESSLIST_USER,
    th.PROCESSLIST_TIME,
    th.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
    ON th.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_SCHEMA = DATABASE()
ORDER BY ml.OBJECT_NAME, ml.LOCK_STATUS;
```

`LOCK_STATUS` cho biết lock đang được cấp (`GRANTED`) hay đang chờ (`PENDING`). Cần xem cả session đang giữ lock và session đang chờ. Quyền xem Performance Schema và các cột khả dụng phụ thuộc cấu hình/phiên bản.

Có thể xem thêm:

```sql
SHOW FULL PROCESSLIST;
```

Không kết thúc session chỉ vì nó đang chạy lâu. Xác định ứng dụng, transaction và tác động trước khi kill. Với production, cần có quy trình xử lý transaction idle kéo dài và giới hạn thời gian chờ metadata lock.

### 7.1. Giảm rủi ro khi chạy ALTER TABLE

Trước DDL lớn:

- Xác định bảng có transaction dài hoặc truy vấn lâu.
- Kiểm tra dung lượng đĩa, I/O, replica lag và tải ứng dụng.
- Kiểm tra thuật toán DDL có thể dùng trên phiên bản hiện tại.
- Đặt `lock_wait_timeout` phù hợp cho session migration để không chờ vô hạn.
- Chạy trong cửa sổ triển khai và có kế hoạch dừng nếu vượt ngưỡng.
- Theo dõi metadata lock, processlist và trạng thái replication trong lúc chạy.

Ví dụ đặt timeout cho session migration:

```sql
SET SESSION lock_wait_timeout = 15;
```

Giá trị 15 giây chỉ là ví dụ. Nếu timeout, DDL có thể thất bại do không lấy được metadata lock; hãy xử lý nguyên nhân rồi thử lại theo runbook. Đừng tăng timeout vô hạn khi production đang có truy vấn bị xếp hàng.

## 8. Online DDL: ALGORITHM và LOCK

InnoDB hỗ trợ nhiều thuật toán DDL. Tùy thao tác, phiên bản, cấu trúc bảng và loại index, MySQL có thể dùng `INSTANT`, `INPLACE` hoặc `COPY`; mức khóa cho phép cũng khác nhau.

Ví dụ minh họa:

```sql
ALTER TABLE customers
    ADD COLUMN customer_note VARCHAR(200) NULL,
    ALGORITHM=INSTANT;
```

`ALGORITHM=INSTANT` có thể thay đổi metadata mà không rebuild toàn bộ bảng cho những thao tác được hỗ trợ. Không phải mọi kiểu thêm cột, vị trí cột, loại bảng hoặc phiên bản đều hỗ trợ instant. Nếu yêu cầu thuật toán không được hỗ trợ, câu lệnh có thể thất bại thay vì tự chuyển sang thuật toán khác.

Một ví dụ khác:

```sql
ALTER TABLE orders
    ADD INDEX idx_orders_created_at (created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

`LOCK=NONE` cho phép concurrent DML trong những thao tác và điều kiện được hỗ trợ. Nó không có nghĩa không cần metadata lock ở mọi giai đoạn, không có I/O hoặc không ảnh hưởng hiệu năng. Tạo index vẫn đọc dữ liệu, dùng CPU/I/O và có thể tạo tải đáng kể.

Trước khi chỉ định `ALGORITHM` hoặc `LOCK`, kiểm tra tài liệu MySQL theo đúng phiên bản và thao tác. Thử trên bản sao dữ liệu gần thực tế. Nếu cần bảo đảm DDL không âm thầm dùng thuật toán copy nặng, hãy chỉ định thuật toán/lock mong muốn để MySQL báo lỗi khi không đáp ứng thay vì tự giả định online.

## 9. Khóa triển khai migration đồng thời

Trong môi trường CI/CD, hai pipeline có thể cùng phát hiện migration chưa chạy và cùng cố áp dụng. Một pipeline có thể tạo bảng trong khi pipeline khác cũng tạo bảng đó; hoặc migration thứ hai chạy khi migration đầu chưa hoàn tất.

Hệ thống cần cơ chế khóa để chỉ một migration runner giữ quyền thực thi tại một thời điểm trên cùng database/topology. Có thể dùng:

- Cơ chế lock tích hợp của công cụ migration.
- MySQL advisory lock bằng `GET_LOCK()`.
- Một bảng điều phối lock do ứng dụng triển khai, nếu được thiết kế đúng.
- Distributed lock service bên ngoài trong kiến trúc có nhiều database endpoint.

Ưu tiên cơ chế lock được công cụ migration chính thức hỗ trợ. Không tự thêm một cơ chế song song nếu công cụ đã có lock, vì hai cơ chế có thể tạo deadlock vận hành hoặc gây hiểu nhầm ai đang sở hữu lock.

### 9.1. Dùng MySQL advisory lock

MySQL cung cấp `GET_LOCK(name, timeout)` để một session yêu cầu named lock. Ví dụ minh họa:

```sql
SELECT GET_LOCK('shop-schema-migration', 30) AS lock_acquired;
```

Kết quả thường là:

- `1`: session lấy được lock.
- `0`: hết thời gian chờ mà không lấy được lock.
- `NULL`: có lỗi khi thực hiện yêu cầu.

Chỉ chạy migration khi đã lấy lock thành công. Sau khi hoàn tất hoặc gặp lỗi, phải giải phóng lock trên cùng session:

```sql
SELECT RELEASE_LOCK('shop-schema-migration') AS lock_released;
```

Advisory lock gắn với connection. Nếu connection bị đóng, lock được giải phóng. Vì vậy migration runner phải giữ connection ổn định từ lúc lấy lock đến khi kết thúc migration. Nếu runner lấy lock qua một connection rồi thực thi DDL qua connection khác, lock không bảo vệ được vùng thực thi như dự kiến.

Named lock chỉ điều phối các tiến trình kết nối tới cùng MySQL server và dùng cùng tên lock. Nó không tự khóa các pipeline đang chạy trên một server khác hoặc một môi trường độc lập. Tên lock nên đại diện cho phạm vi cần tuần tự hóa, ví dụ database/schema hoặc một topology dùng chung.

### 9.2. Mẫu điều phối trong migration runner

Pseudocode:

```text
connection = openMigrationConnection()

try:
    result = connection.query(
        "SELECT GET_LOCK('shop-schema-migration', 30)"
    )

    if result != 1:
        fail("Không lấy được migration lock")

    verifyMigrationHistoryAndChecksums(connection)

    for migration in pendingMigrationsInVersionOrder:
        verifyPreconditions(connection, migration)
        executeMigration(connection, migration)
        verifyPostconditions(connection, migration)
        recordMigrationHistory(connection, migration)
finally:
    connection.query(
        "SELECT RELEASE_LOCK('shop-schema-migration')"
    )
    connection.close()
```

Đây là luồng logic, không phải mã hoàn chỉnh cho một framework cụ thể. Cần xử lý lỗi khi connection mất trước khi giải phóng lock, lỗi giữa các câu DDL và trường hợp lịch sử migration chưa được ghi. Nếu connection mất, MySQL sẽ giải phóng advisory lock của session đó; runner mới phải kiểm tra schema thực tế trước khi tiếp tục.

### 9.3. Vì sao khóa hàng trong migration history có thể chưa đủ?

Một số hệ thống định khóa hàng trong bảng history bằng `SELECT ... FOR UPDATE`. Cách này chỉ bảo vệ trong transaction. Nhiều câu DDL MySQL gây implicit commit, do đó transaction có thể kết thúc và nhả row lock trước khi toàn bộ chuỗi migration hoàn tất.

Nếu dùng bảng lock, phải hiểu rõ cách công cụ giữ lock xuyên suốt migration và cách nó phục hồi khi process chết. Không tự cho rằng một transaction bao quanh DDL sẽ giữ được khóa từ đầu tới cuối.

## 10. Expand-contract: triển khai schema không làm gãy ứng dụng

Khi nhiều phiên bản ứng dụng cùng chạy trong quá trình rolling deployment, schema cần tương thích cả phiên bản cũ lẫn mới trong giai đoạn chuyển tiếp. Mô hình expand-contract chia thay đổi phá vỡ tương thích thành các bước nhỏ.

Ví dụ cần đổi `customers.name` thành `customers.display_name`:

### Giai đoạn 1: Expand

Thêm cột mới nhưng vẫn giữ cột cũ:

```sql
ALTER TABLE customers
    ADD COLUMN display_name VARCHAR(150) NULL;
```

Phiên bản ứng dụng cũ vẫn đọc/ghi `name`; phiên bản mới có thể bắt đầu hiểu `display_name`.

### Giai đoạn 2: Dual write hoặc đồng bộ dữ liệu

Triển khai ứng dụng ghi giá trị tương thích vào cả hai cột trong thời gian chuyển tiếp, hoặc dùng một job backfill theo lô để điền `display_name` từ `name`. Phải xác định một nguồn dữ liệu ưu tiên và tránh hai cột lệch nhau khi có cập nhật đồng thời.

Ví dụ backfill theo khóa chính:

```sql
UPDATE customers
SET display_name = name
WHERE customer_id > 0
  AND customer_id <= 10000
  AND display_name IS NULL;
```

Tiếp tục theo từng khoảng khóa nhỏ, đo tải và xác minh số hàng đã cập nhật. Không chạy một câu UPDATE toàn bảng trên bảng lớn nếu chưa đánh giá lock, undo, redo, replication lag và dung lượng.

### Giai đoạn 3: Switch read

Triển khai ứng dụng đọc `display_name`, theo dõi lỗi và đối soát dữ liệu giữa hai cột. Giữ khả năng quay lại phiên bản cũ trong khoảng thời gian đã định.

### Giai đoạn 4: Contract

Khi tất cả phiên bản ứng dụng đã ngừng dùng `name`, job backfill hoàn tất và không còn consumer cũ, mới tạo migration xóa cột cũ:

```sql
ALTER TABLE customers
    DROP COLUMN name;
```

Đây là thao tác phá vỡ tương thích. Cần xác nhận không còn truy vấn, job, báo cáo hoặc dịch vụ nào phụ thuộc cột trước khi chạy. Với bảng lớn, đánh giá thuật toán DDL và ảnh hưởng vận hành.

Expand-contract áp dụng cho đổi tên cột, đổi kiểu dữ liệu, thay cấu trúc bảng hoặc chuyển khóa. Không nhất thiết phải dual write trong mọi trường hợp; có thể dùng view, trigger hoặc quy trình backfill khác, nhưng cần đánh giá rõ nguồn sự thật và tính nhất quán.

## 11. Xử lý migration lỗi giữa chừng

Do DDL có implicit commit, một migration chứa nhiều câu lệnh có thể hoàn tất một phần. Ví dụ migration tạo cột thành công nhưng tạo index sau đó thất bại. Bảng history có thể chưa ghi version, trong khi schema đã thay đổi.

Khi gặp lỗi:

1. Dừng các migration runner khác bằng cơ chế lock.
2. Ghi nhận lỗi, câu DDL đã chạy, connection ID, thời điểm và log server.
3. Kiểm tra schema thực tế bằng `INFORMATION_SCHEMA` và `SHOW CREATE TABLE`.
4. Đối chiếu migration history và checksum.
5. Xác định trạng thái: chưa thay đổi, thay đổi một phần hay đã hoàn tất nhưng chưa ghi history.
6. Tạo migration khắc phục hoặc dùng quy trình repair được công cụ hỗ trợ.
7. Chỉ đánh dấu migration đã áp dụng khi đã xác minh toàn bộ postcondition.

Không chạy lại migration một cách mù quáng. `CREATE TABLE` hoặc `ADD COLUMN` có thể thất bại vì đối tượng đã tồn tại; dùng `IF NOT EXISTS` không phải lúc nào cũng đủ vì đối tượng có thể tồn tại nhưng định nghĩa sai.

Nếu phải sửa production bằng hotfix, ghi lại chính xác DDL và dữ liệu đã thay đổi, sau đó tạo migration để các môi trường khác có thể đạt cùng trạng thái. Không chỉnh sửa file migration đã được áp dụng để giả vờ rằng hotfix vốn nằm trong lịch sử.

## 12. Quy trình CI/CD cho migration

Một pipeline triển khai schema nên tách kiểm tra, thực thi và xác minh:

1. **Validate:** kiểm tra cú pháp, version duy nhất, checksum và quy tắc đặt tên migration.
2. **Build sạch:** tạo database mới và chạy toàn bộ migration theo thứ tự.
3. **Upgrade test:** tạo schema từ version gần production rồi chạy migration mới.
4. **Drift check:** so sánh schema thực tế với manifest mong đợi ở môi trường mục tiêu.
5. **Review:** đánh giá DDL, thuật toán, thời gian, metadata lock, dung lượng và ảnh hưởng replication.
6. **Serialize:** lấy migration lock trước khi kiểm tra và thực thi migration.
7. **Apply:** chạy migration theo thứ tự và lưu lịch sử/checksum.
8. **Verify:** kiểm tra schema, index, constraint, dữ liệu backfill và trạng thái ứng dụng.
9. **Release:** triển khai phiên bản ứng dụng tương thích theo đúng thứ tự expand-contract.
10. **Observe:** theo dõi lỗi truy vấn, metadata lock, replication lag và hiệu năng sau triển khai.

Với môi trường có nhiều database hoặc shard, xác định phạm vi khóa cho từng database và thứ tự triển khai. Không để một migration chạy trên một shard trong khi shard khác vẫn dùng schema cũ nếu ứng dụng giả định mọi shard có cùng phiên bản.

## 13. Sự cố thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Migration báo cột đã tồn tại | Drift do hotfix hoặc migration đã chạy một phần | Kiểm tra `INFORMATION_SCHEMA.COLUMNS`, history và checksum |
| Migration tạo index thất bại | Sai thứ tự, index đã tồn tại hoặc giới hạn DDL | Kiểm tra `INFORMATION_SCHEMA.STATISTICS` và định nghĩa bảng |
| Migration chờ rất lâu | Metadata lock bị giữ bởi transaction hoặc query dài | Kiểm tra `performance_schema.metadata_locks` và processlist |
| Hai pipeline cùng chạy migration | Chưa có lock hoặc lock không bao phủ đúng phạm vi | Kiểm tra migration runner, connection và named lock |
| Checksum không khớp | File migration đã bị sửa sau khi áp dụng | Đối chiếu repository, history và quy trình release |
| Ứng dụng cũ lỗi sau khi deploy schema | DDL phá vỡ tương thích quá sớm | Kiểm tra thứ tự rollout và áp dụng expand-contract |
| Migration history thiếu version nhưng DDL đã tồn tại | DDL implicit commit, runner chết trước khi ghi history | Kiểm tra postcondition rồi dùng repair có kiểm soát |
| Replica lag tăng sau DDL/backfill | DDL hoặc cập nhật lớn tạo tải replication | Theo dõi applier, binlog volume, batch size và tốc độ backfill |

Trong điều tra, lưu schema diff trước/sau, migration file và checksum, log migration runner, processlist, metadata lock và trạng thái replication. Không xóa dòng history hoặc drop đối tượng để làm cho lần chạy tiếp theo “sạch” nếu chưa biết tác động dữ liệu.

## 14. Checklist trước khi triển khai schema

- [ ] Migration có version duy nhất và checksum được kiểm tra.
- [ ] Migration đã chạy ở môi trường trước theo cùng thứ tự.
- [ ] Schema drift của môi trường đích đã được phân loại và xử lý.
- [ ] DDL tương thích với phiên bản MySQL và engine hiện tại.
- [ ] Đã đánh giá `ALGORITHM`, `LOCK`, metadata lock và thời gian dự kiến.
- [ ] Có migration lock để ngăn runner chạy đồng thời.
- [ ] Ứng dụng cũ và mới tương thích trong thời gian rolling deployment.
- [ ] Backfill chia lô và có thể tiếp tục sau lỗi.
- [ ] Có backup/restore plan và cách khắc phục khi DDL hoàn tất một phần.
- [ ] Có postcondition để xác minh schema và dữ liệu sau migration.
- [ ] Có người theo dõi replication lag, lỗi ứng dụng và hiệu năng.

## 15. Tình huống thực hành

Một ứng dụng thương mại có ba môi trường development, staging và production. Production có một hotfix thêm cột `delivery_note` trực tiếp. Migration tương ứng chưa được đưa vào repository. Một nhánh khác thêm index trên `delivery_note` và pipeline đang chuẩn bị chạy hai migration cùng lúc.

Thực hiện trong môi trường lab:

1. Tạo ba database đại diện cho ba môi trường với schema khác nhau.
2. Thêm `delivery_note` thủ công vào database production giả lập để tạo drift.
3. Dùng `INFORMATION_SCHEMA.COLUMNS` so sánh ba môi trường và ghi nhận sai lệch.
4. Viết migration chuẩn hóa để mọi môi trường có cùng định nghĩa cột.
5. Tạo migration index có version sau migration tạo cột.
6. Mô phỏng hai migration runner cùng chạy và quan sát lỗi khi không có lock.
7. Dùng `GET_LOCK()` để tuần tự hóa runner; xác nhận runner thứ hai phải chờ hoặc timeout.
8. Mở một transaction đọc bảng rồi thử DDL từ session khác; kiểm tra metadata lock và processlist.
9. Thử mô hình expand-contract để đổi tên cột mà ứng dụng cũ và mới vẫn hoạt động trong giai đoạn chuyển tiếp.
10. Mô phỏng migration tạo cột thành công nhưng bước tạo index thất bại; kiểm tra schema và history rồi lập migration repair.

**Câu hỏi tự đánh giá:**

- Schema drift khác gì với migration mới chưa được áp dụng?
- Vì sao không nên sửa migration đã chạy trên môi trường dùng chung?
- Vì sao bảng migration history không đủ để chứng minh schema thực tế đúng?
- MySQL DDL có implicit commit ảnh hưởng thế nào tới rollback và xử lý lỗi giữa chừng?
- Metadata lock có thể khiến một DDL và các truy vấn mới bị nghẽn ra sao?
- `GET_LOCK()` gắn với connection như thế nào và vì sao runner phải giữ cùng connection?
- Vì sao khóa hàng trong transaction có thể không bảo vệ toàn bộ chuỗi DDL?
- Expand-contract giúp rolling deployment an toàn như thế nào?

## Kết luận

Quản lý schema an toàn cần một nguồn sự thật rõ ràng, migration có thứ tự và bất biến, cơ chế phát hiện drift, cùng khóa triển khai để tránh nhiều runner thay đổi database đồng thời. Với MySQL, implicit commit và metadata lock khiến DDL cần được lập kế hoạch, giám sát và xác minh riêng. Hãy triển khai theo từng bước tương thích, kiểm tra schema thực tế sau mỗi thay đổi và giữ quy trình repair rõ ràng khi migration thất bại giữa chừng.
