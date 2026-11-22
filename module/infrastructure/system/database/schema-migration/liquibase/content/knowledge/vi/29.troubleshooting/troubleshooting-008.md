# Migration thất bại do dữ liệu, ràng buộc hoặc phụ thuộc

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Khi migration thất bại do dữ liệu, ràng buộc hoặc phụ thuộc, nhiệm vụ đầu tiên là xác định **điều kiện nào khiến changeset không thể hoàn tất và database đang ở trạng thái nào**.

Một thông báo như duplicate key, cannot insert NULL, foreign key violation hoặc relation does not exist thường chỉ cho biết điểm thất bại. Nó chưa trả lời liệu DDL trước đó đã commit chưa, dữ liệu nào đã được cập nhật, changeset đã được ghi vào DATABASECHANGELOG chưa, hoặc có thể retry an toàn hay không.

Quy trình xử lý tốt phải dựa trên bằng chứng: đọc lỗi gốc, xác định đúng database và changeset, kiểm tra lịch sử cùng trạng thái vật lý, tìm dữ liệu vi phạm, sửa theo quy tắc nghiệp vụ, rồi mới chạy lại. Không xóa lịch sử Liquibase hoặc chạy lại toàn bộ migration theo phản xạ.

## 1. Phân loại lỗi trước khi sửa

Migration có thể thất bại ở nhiều giai đoạn. Phân loại đúng giúp tránh sửa nhầm lớp.

| Giai đoạn | Dấu hiệu thường gặp | Điều cần xác minh |
|---|---|---|
| Đọc changelog | YAML/XML/JSON parse error, include not found | Cú pháp, encoding, đường dẫn và resource |
| Khởi tạo runtime | Không tải được driver/extension, class not found | Dependency, classpath, version |
| Kết nối database | Authentication failed, timeout, connection refused | URL, network, TLS, credential, DB availability |
| Lấy lock | Waiting for changelog lock | Runner khác, transaction hoặc lock còn giữ |
| Precondition | Preconditions failed hoặc error | Điều kiện dữ liệu/schema, onFail/onError |
| Thực thi SQL | Constraint violation, syntax error, permission denied | SQL, dữ liệu, DBMS, quyền và dependency |
| Ghi lịch sử | Lỗi khi ghi DATABASECHANGELOG | Metadata schema, quyền, kết nối và trạng thái DDL |
| Khởi động ứng dụng | Spring context không khởi tạo, startup timeout | Liquibase bean, thứ tự khởi tạo, DataSource |

Đừng bắt đầu bằng cách thay đổi changelog khi lỗi thực chất là database không kết nối được. Ngược lại, đổi credential không giải quyết được lỗi duplicate key hoặc foreign key violation.

### 1.1. Thu thập bằng chứng tối thiểu

Trước khi can thiệp, ghi lại:

- Môi trường, database/catalog, schema và DBMS/version.
- Application version, migration artifact và Liquibase version.
- Root changelog, changeset id, author và filename.
- Context, label, DBMS filter và property được dùng.
- Thời điểm bắt đầu/kết thúc, deployment/job ID.
- Lỗi gốc từ JDBC/DBMS và câu SQL liên quan nếu log có.
- Changeset nào đã hoàn tất trước lỗi.
- DATABASECHANGELOG và DATABASECHANGELOGLOCK hiện tại.
- Dữ liệu/đối tượng liên quan có tồn tại hoặc đã thay đổi không.

Log cần được redacted trước khi chia sẻ. Không đưa password, token, JDBC URL chứa credential hoặc dữ liệu cá nhân vào ticket.

### 1.2. Xác định đúng target

Một hệ thống có thể có nhiều DataSource, database hoặc schema. Trước khi đọc history, hãy xác nhận kết nối mà Liquibase thực sự sử dụng. Truy vấn nhầm database có thể khiến bạn kết luận changeset chưa chạy trong khi nó đã chạy ở target khác.

Với Spring Boot, kiểm tra DataSource/qualifier và root changelog của bean Liquibase. Với CLI hoặc CI/CD, kiểm tra defaults file, biến môi trường, profile, context và target đã được resolve.

## 2. Hiểu trạng thái changeset sau khi lỗi

Liquibase theo dõi changeset trong DATABASECHANGELOG. Một dòng lịch sử thường chứa id, author, filename, checksum, thời điểm chạy và execution type. Bảng này là bằng chứng quan trọng, nhưng không thay thế việc kiểm tra schema và dữ liệu thực tế.

### 2.1. Ba trạng thái cần phân biệt

| Tình huống | Ý nghĩa | Hành động |
|---|---|---|
| Changeset chưa có trong history, database chưa đổi | Có thể chưa thực thi hoặc bị dừng trước SQL | Điều tra nguyên nhân rồi chạy lại khi điều kiện đã sẵn sàng |
| Changeset chưa có trong history nhưng database đã đổi một phần | Có thể có DDL auto-commit hoặc SQL không transactional | Kiểm tra catalog/data, hoàn tất hoặc dọn trạng thái dở dang có kiểm soát |
| Changeset đã có trong history | Liquibase đã ghi nhận execution type tương ứng | Không chạy lại bằng cách xóa history; xác minh hậu điều kiện và dùng changeset mới nếu cần sửa |

Không suy luận database không đổi chỉ vì changeset không có trong DATABASECHANGELOG. Một số DBMS tự commit DDL; changeset dùng runInTransaction=false; hoặc một chuỗi SQL có thể hoàn tất một phần trước khi lỗi.

### 2.2. Transaction không giống nhau giữa các DBMS

Liquibase thường thực thi changeset trong transaction theo cấu hình mặc định khi DBMS hỗ trợ. Tuy nhiên, khả năng rollback DDL phụ thuộc engine và câu lệnh. Một số DDL tự commit hoặc không được phép chạy trong transaction.

Vì vậy, sau lỗi:

1. Xác định changeset có runInTransaction=false hay không.
2. Xác định DBMS có transactional DDL cho câu lệnh đó không.
3. Kiểm tra các đối tượng đã được tạo/sửa/xóa.
4. Kiểm tra dữ liệu đã được cập nhật đến đâu.
5. Kiểm tra changeset có được ghi vào history không.
6. Chỉ sau đó mới quyết định retry, repair, rollback hay forward-fix.

### 2.3. Không sửa trực tiếp DATABASECHANGELOG để cho qua

Không tự xóa dòng history, sửa MD5SUM hoặc chèn một dòng giả để khiến Liquibase tin rằng migration đã chạy. Việc đó phá vỡ bằng chứng triển khai và có thể khiến database khác biệt với changelog.

Nếu cần khôi phục history sau một sự cố đặc biệt, phải có quy trình được review, backup bằng chứng và xác nhận trạng thái database. Thông thường, sửa nguyên nhân rồi chạy changeset còn pending hoặc tạo changeset forward-fix là hướng dễ kiểm toán hơn.

## 3. Đọc lỗi DBMS thay vì chỉ nhìn thông báo Liquibase

Thông báo Liquibase thường bao bọc lỗi JDBC. Phần có giá trị chẩn đoán nhất có thể nằm ở nested exception hoặc SQLState/vendor error code.

Ví dụ:

~~~text
Migration failed for changeset orders/045-add-customer-fk.yaml
Reason: liquibase.exception.DatabaseException
Caused by: SQLIntegrityConstraintViolationException
Message: foreign key constraint violated
SQL: ALTER TABLE ...
~~~

Hãy truy tìm:

- Changeset id và filename.
- Câu SQL thực tế.
- DBMS error code/SQLState.
- Tên constraint hoặc đối tượng.
- Giá trị khóa gây lỗi nếu DBMS cung cấp.
- Transaction/connection state.
- Dòng log đầu tiên và root cause cuối cùng.

Không chỉ copy dòng Migration failed. Cần đọc stack trace đủ sâu để xác định lỗi phát sinh trong parser, Liquibase, JDBC driver hay database engine.

### 3.1. Phân biệt lỗi dữ liệu và lỗi quyền

Ví dụ permission denied for table orders là lỗi quyền; violates check constraint là lỗi dữ liệu. Hai lỗi cần hướng xử lý khác nhau.

Không cấp quyền owner/superuser chỉ để vượt qua một lỗi constraint. Không bỏ constraint để khắc phục lỗi quyền. Giữ nguyên invariant dữ liệu và sửa đúng quyền tối thiểu.

## 4. Migration thất bại vì NOT NULL

Lỗi thường gặp khi thêm hoặc bật NOT NULL:

~~~text
ERROR: column "delivery_status" contains null values
~~~

Nguyên nhân: vẫn còn dòng có NULL ở cột cần bắt buộc, hoặc một writer tiếp tục ghi NULL trong lúc migration chạy.

### 4.1. Đếm dòng vi phạm

Ví dụ PostgreSQL:

~~~sql
SELECT COUNT(*) AS null_count
FROM app.orders
WHERE delivery_status IS NULL;
~~~

Để xem một số bản ghi:

~~~sql
SELECT id, created_at, status
FROM app.orders
WHERE delivery_status IS NULL
ORDER BY id
LIMIT 100;
~~~

Không chỉ nhìn số lượng. Cần xác định nhóm dữ liệu nào bị thiếu, nguồn tạo ra chúng và giá trị đúng theo nghiệp vụ.

### 4.2. Tìm writer tiếp tục tạo NULL

Kiểm tra tất cả nguồn ghi:

- API/service phiên bản cũ.
- Batch import và scheduled job.
- Message consumer.
- Script vận hành.
- Integration bên ngoài.
- Trigger hoặc stored procedure.
- Một ứng dụng khác dùng chung database.

Nếu chỉ backfill mà không chặn nguồn tạo NULL mới, số dòng có thể giảm rồi tăng lại. Triển khai writer tương thích trước, hoặc dùng cơ chế database bảo vệ ghi mới phù hợp DBMS.

### 4.3. Backfill đúng quy tắc nghiệp vụ

Ví dụ cập nhật các dòng có thể xác định chắc chắn:

~~~sql
UPDATE app.orders
SET delivery_status = 'PENDING'
WHERE delivery_status IS NULL
  AND status = 'CREATED';
~~~

Giá trị PENDING ở đây chỉ là ví dụ. Không gán cùng một default cho mọi dòng nếu trạng thái thực tế phụ thuộc lịch sử nghiệp vụ. Với các dòng không thể suy ra, cần mapping, đối soát nguồn chuẩn hoặc quy trình xử lý dữ liệu ngoại lệ.

Trên bảng lớn, chia backfill theo batch và commit từng phần. Lưu checkpoint, đếm số dòng xử lý, đo thời gian và replication lag. Điều kiện UPDATE phải idempotent, ví dụ chỉ sửa dòng vẫn còn NULL, để retry không ghi đè giá trị đã được ứng dụng cập nhật.

### 4.4. Xác minh trước khi enforce

Sau backfill, chạy truy vấn kiểm tra chính xác. Đồng thời kiểm tra constraint tạm nếu đã dùng. Nếu database hỗ trợ CHECK NOT VALID/VALIDATE, cần hiểu ngữ nghĩa của engine: một số cơ chế bỏ qua xác minh dòng cũ tại lúc tạo nhưng vẫn áp dụng với INSERT/UPDATE mới. Một UPDATE trên dòng cũ có thể bị kiểm tra lại dù chỉ sửa cột khác.

Chỉ đặt NOT NULL khi:

- Dữ liệu hiện hữu đã đạt invariant.
- Mọi writer bắt buộc đã tương thích.
- Không có job cũ đang chạy.
- Có kế hoạch xử lý lock và timeout.
- Đã thử trên DBMS/version đại diện.

## 5. Migration thất bại vì UNIQUE hoặc duplicate key

Lỗi thường gặp:

~~~text
duplicate key value violates unique constraint
~~~

Có thể phát sinh khi thêm UNIQUE constraint/index hoặc khi insert dữ liệu seed. Nguyên nhân thường là dữ liệu cũ có duplicate, collation/normalization khiến hai giá trị được xem như nhau, hoặc hai writer đồng thời tạo cùng khóa.

### 5.1. Tìm duplicate

Ví dụ kiểm tra email:

~~~sql
SELECT lower(email) AS normalized_email, COUNT(*) AS row_count
FROM app.customers
WHERE email IS NOT NULL
GROUP BY lower(email)
HAVING COUNT(*) > 1
ORDER BY row_count DESC;
~~~

Đây là ví dụ khi quy tắc nghiệp vụ coi email không phân biệt hoa thường. Hãy dùng đúng normalization, collation và quy tắc NULL của DBMS. Kiểm tra duplicate theo biểu thức mà unique index thực sự sử dụng; truy vấn GROUP BY đơn giản trên cột gốc có thể bỏ sót xung đột.

### 5.2. Chọn bản ghi chuẩn và xử lý tham chiếu

Không tự xóa các dòng duplicate. Trước tiên:

1. Xác định tiêu chí bản ghi chuẩn.
2. Tìm bảng con đang tham chiếu từng bản ghi.
3. Chuyển tham chiếu sang bản ghi chuẩn nếu nghiệp vụ cho phép.
4. Xử lý khác biệt dữ liệu và audit.
5. Kiểm tra writer không tạo duplicate mới.
6. Chạy lại kiểm tra duplicate.
7. Tạo UNIQUE constraint/index sau khi dữ liệu hợp lệ.

Nếu cần giữ cả hai bản ghi vì chúng đại diện hai thực thể khác nhau, phải sửa mô hình khóa hoặc quy tắc unique. Không ép dữ liệu vào một constraint sai.

### 5.3. Race condition giữa kiểm tra và tạo UNIQUE

Một truy vấn duplicate trả 0 không bảo đảm không có duplicate mới được ghi trước khi index/constraint được tạo. Cần phối hợp writer, lock/constraint tạm hoặc cơ chế unique build phù hợp DBMS để đóng khoảng thời gian race.

Với PostgreSQL, có thể dùng unique index concurrently trong một quy trình có kiểm soát; nếu dữ liệu vi phạm xuất hiện trong lúc build, thao tác có thể thất bại và để lại index invalid. Kiểm tra catalog trước khi retry.

## 6. Migration thất bại vì FOREIGN KEY

Lỗi foreign key thường có dạng:

~~~text
insert or update on table "orders" violates foreign key constraint
Key (customer_id)=(...) is not present in table "customers"
~~~

Có hai tình huống chính:

- Dữ liệu cũ trong bảng con tham chiếu tới khóa cha không tồn tại.
- Dữ liệu mới được ghi đồng thời với migration và tạo orphan.

### 6.1. Tìm orphan rows

Ví dụ:

~~~sql
SELECT o.id, o.customer_id
FROM app.orders o
LEFT JOIN app.customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL
ORDER BY o.id
LIMIT 100;
~~~

Đếm tổng:

~~~sql
SELECT COUNT(*) AS orphan_count
FROM app.orders o
LEFT JOIN app.customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Trên bảng lớn, anti-join có thể nặng. Dùng index phù hợp và kiểm tra trên môi trường đại diện. Truy vấn giới hạn 100 dòng giúp xem ví dụ, nhưng không chứng minh tổng số orphan bằng 0.

### 6.2. Xử lý orphan theo nghiệp vụ

Các lựa chọn có thể gồm:

- Khôi phục bản ghi cha từ nguồn dữ liệu chuẩn.
- Sửa customer_id sang khóa đúng sau khi đối soát.
- Đặt NULL nếu quan hệ thực sự optional và schema cho phép.
- Chuyển dòng vào quy trình quarantine có audit.
- Dừng migration nếu không thể xác định quan hệ đúng.

Không tạo một parent row giả hoặc xóa child row chỉ để FK validation qua được.

### 6.3. Thứ tự triển khai FK

Một thứ tự thường gặp:

1. Bảo đảm bảng cha và khóa PRIMARY KEY/UNIQUE tồn tại.
2. Kiểm tra kiểu dữ liệu và schema của hai cột.
3. Tạo index trên cột khóa ngoại nếu workload/DBMS cần.
4. Ngăn writer mới tạo orphan.
5. Sửa orphan hiện hữu.
6. Thêm FK theo chế độ phù hợp DBMS.
7. Validate dữ liệu cũ nếu engine hỗ trợ tách bước.
8. Kiểm tra metadata constraint đã validated.

Với PostgreSQL, ADD FOREIGN KEY NOT VALID rồi VALIDATE CONSTRAINT có thể giúp tách bước xác minh dữ liệu cũ. Không áp dụng cú pháp này cho DBMS khác nếu chưa kiểm tra hỗ trợ.

## 7. Migration thất bại vì CHECK constraint

CHECK constraint có thể thất bại khi giá trị không nằm trong miền cho phép, ví dụ:

~~~sql
ALTER TABLE app.orders
ADD CONSTRAINT ck_orders_total_nonnegative
CHECK (total_amount >= 0);
~~~

Nếu dữ liệu cũ có total_amount âm, việc thêm constraint trực tiếp có thể thất bại.

Tìm dữ liệu vi phạm:

~~~sql
SELECT id, total_amount
FROM app.orders
WHERE total_amount < 0
ORDER BY id
LIMIT 100;
~~~

Trước khi sửa, xác định số âm có phải dữ liệu lỗi hay có ý nghĩa nghiệp vụ như khoản hoàn tiền/điều chỉnh. Có thể mô hình hiện tại cần biểu diễn giao dịch đảo riêng thay vì cấm số âm.

Với PostgreSQL, CHECK NOT VALID có thể cho phép thêm constraint mà chưa quét dữ liệu cũ, sau đó sửa dữ liệu và VALIDATE. Lưu ý các thao tác UPDATE trên dòng cũ vẫn có thể phải tuân thủ CHECK mới. Thiết kế backfill và writer tương thích trước khi bật constraint.

## 8. Migration thất bại vì chuyển đổi kiểu dữ liệu

Các lỗi chuyển kiểu thường xuất hiện khi đổi VARCHAR sang INTEGER/DATE/DECIMAL, thu hẹp độ dài hoặc thay đổi precision/scale.

Ví dụ:

~~~sql
ALTER TABLE app.orders
ALTER COLUMN external_code TYPE BIGINT
USING external_code::BIGINT;
~~~

Lệnh trên là cú pháp PostgreSQL. Nó thất bại nếu có giá trị không thể cast, vượt range hoặc có định dạng không hợp lệ.

### 8.1. Tìm dữ liệu không chuyển đổi được

Với PostgreSQL, có thể dùng biểu thức kiểm tra định dạng trước khi cast, ví dụ:

~~~sql
SELECT id, external_code
FROM app.orders
WHERE external_code IS NOT NULL
  AND external_code !~ '^[0-9]+$'
ORDER BY id
LIMIT 100;
~~~

Regex chỉ kiểm tra dạng chữ số; vẫn cần kiểm tra range của BIGINT và quy tắc dấu/leading zero. Nếu external_code là mã định danh, chuyển sang số có thể làm mất số 0 đầu và làm sai ý nghĩa. Đừng chuyển kiểu chỉ vì cột hiện chứa chuỗi trông giống số.

### 8.2. Dùng cột mới cho chuyển đổi rủi ro

Với bảng lớn hoặc conversion phức tạp, cân nhắc:

1. Thêm cột mới với kiểu đích.
2. Triển khai ứng dụng dual-write hoặc đọc tương thích.
3. Backfill cột mới theo batch.
4. Đối chiếu giá trị cũ/mới.
5. Chuyển consumer sang cột mới.
6. Enforce constraint trên cột mới.
7. Giữ cột cũ trong giai đoạn tương thích.
8. Xóa cột cũ ở release sau.

Cách này tốn thời gian nhưng giảm rủi ro rewrite và giúp quan sát dữ liệu trước cutover.

## 9. Migration thất bại vì dữ liệu seed hoặc loadData

Dữ liệu seed có thể vi phạm UNIQUE, FK, NOT NULL hoặc CHECK. Ngoài ra, CSV có thể sai header, encoding, delimiter, quote hoặc thứ tự cột.

Kiểm tra:

- File được đóng gói đúng và đúng version.
- Header khớp mapping cột.
- Encoding UTF-8 và ký tự đặc biệt.
- NULL, empty string và giá trị mặc định có phân biệt đúng không.
- Dữ liệu tham chiếu đã được nạp trước chưa.
- Unique key có trùng với dữ liệu hiện tại không.
- Changeset seed có cần idempotent không.

Ví dụ dữ liệu tham chiếu:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: reference-010-seed-order-status
      author: database-team
      changes:
        - loadData:
            schemaName: app
            tableName: order_status
            file: data/order-status.csv
            relativeToChangelogFile: true
            encoding: UTF-8
            separator: ","
~~~

Nếu chạy seed lại và gặp duplicate, cần xác định changeset đã được thực thi chưa và dữ liệu đã có từ nguồn nào. Không xóa dòng history để ép loadData chạy lại. Với dữ liệu cần cập nhật lặp lại, thiết kế loadUpdateData hoặc upsert theo khả năng DBMS và quy tắc nghiệp vụ; vẫn phải kiểm soát khóa và tác động.

## 10. Migration thất bại vì phụ thuộc đối tượng

Một changeset có thể phụ thuộc vào bảng, cột, sequence, view, function, trigger, type, extension hoặc quyền được tạo trước đó.

Ví dụ lỗi:

~~~text
relation "customers" does not exist
column "customer_code" does not exist
function normalize_code(...) does not exist
permission denied for schema app
~~~

### 10.1. Kiểm tra thứ tự changelog

Root changelog phải nạp các changeset theo thứ tự dependency:

~~~text
Create schema
    |
    v
Create parent table / primary key
    |
    v
Create child table
    |
    v
Create supporting index
    |
    v
Load or backfill data
    |
    v
Add and validate foreign key
    |
    v
Create view / trigger / dependent function
~~~

Đây chỉ là sơ đồ minh họa; thứ tự thật phụ thuộc DBMS và loại đối tượng. Một view có thể cần function trước; trigger cần bảng và function; FK cần parent key; dữ liệu seed cần bảng tham chiếu.

### 10.2. Kiểm tra include/includeAll

Nếu root changelog include file sai đường dẫn hoặc includeAll lấy thứ tự không như mong đợi, dependency có thể chưa được tạo khi changeset chạy.

Kiểm tra:

- Root changelog thực tế được cấu hình.
- Tất cả include path tồn tại trong artifact.
- File con có include tiếp file khác không.
- includeAll có chứa file ngoài phạm vi không.
- Tên file và thứ tự sắp xếp có ổn định không.
- File được include có đúng context/label/DBMS filter không.

Không giả định tên file theo số thứ tự luôn đảm bảo thứ tự nếu includeAll, filter hoặc cấu trúc thư mục khác nhau giữa artifact.

### 10.3. Phụ thuộc vào schema/search path

Một bảng tồn tại trong schema khác vẫn có thể bị báo không tìm thấy nếu search_path/default schema không đúng. Dùng schemaName/catalogName rõ ràng khi phù hợp và xác minh connection thực tế.

Với PostgreSQL, kiểm tra current_database(), current_schema() và search_path. Với DBMS khác, dùng catalog/session metadata tương ứng. Không sửa tên object trước khi xác nhận target schema.

### 10.4. Phụ thuộc vào extension và quyền

Một changeset có thể cần extension DBMS, function hoặc quyền tạo đối tượng. Nếu extension chưa được cài, kiểm tra version, owner và quyền cài đặt. Nếu lỗi permission denied, xác định privilege cụ thể cần cấp; tránh dùng tài khoản DBA toàn quyền cho toàn bộ migration.

## 11. Phụ thuộc vòng và thay đổi nhiều bước

Một số mô hình có quan hệ vòng: bảng A tham chiếu B, B tham chiếu A; view phụ thuộc view; trigger gọi function tham chiếu bảng khác.

Không cố tạo mọi constraint ngay trong bước tạo bảng nếu đối tượng phía bên kia chưa tồn tại. Có thể:

1. Tạo các bảng và khóa chính trước.
2. Nạp hoặc chuyển đổi dữ liệu cần thiết.
3. Thêm FK sau khi cả hai bảng tồn tại.
4. Tạo view/function theo thứ tự dependency.
5. Validate các constraint sau cùng.

Với quan hệ vòng có thể cần cho phép NULL tạm thời, deferrable constraint nếu DBMS hỗ trợ, hoặc chia quy trình ghi dữ liệu. Cần xác định semantics nghiệp vụ và kiểm tra engine trước khi chọn.

## 12. Context, label và DBMS filter khiến dependency bị bỏ qua

Một changeset tạo bảng cha có thể bị loại bởi context/label, trong khi changeset tạo FK vẫn được chọn. Kết quả là lỗi object missing dù file include đúng.

Khi điều tra:

- Xem context/label truyền cho đúng lệnh update.
- Kiểm tra context/label khai báo ở changelog và changeset.
- Kiểm tra DBMS filter.
- Xác nhận profile Spring Boot và biến môi trường.
- So sánh SQL preview của đúng artifact/config.
- Xác định changeset bị lọc là chủ đích hay lỗi cấu hình.

Không xóa filter để chạy cho qua nếu nó bảo vệ dữ liệu test hoặc môi trường khác. Sửa cấu hình selection theo phạm vi đã được phê duyệt.

## 13. Precondition thất bại hoặc được đánh giá sai

Precondition kiểm tra điều kiện trước khi chạy changeset, ví dụ bảng tồn tại, cột có mặt hoặc SQL query trả kết quả mong đợi.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-070-add-customer-index
      author: database-team
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: orders
        - columnExists:
            schemaName: app
            tableName: orders
            columnName: customer_id
      changes:
        - createIndex:
            schemaName: app
            tableName: orders
            indexName: idx_orders_customer
            columns:
              - column:
                  name: customer_id
~~~

Nếu precondition fail, đọc rõ điều kiện nào không đạt. Có thể schemaName sai, connection đang ở database khác, đối tượng chưa được include, hoặc một changeset trước đó đã bị filter.

### 13.1. Phân biệt onFail và onError

- onFail áp dụng khi precondition chạy thành công nhưng điều kiện không thỏa.
- onError áp dụng khi có lỗi trong lúc đánh giá precondition, chẳng hạn truy vấn không thực thi được.

Các hành vi thường gặp gồm HALT, WARN, CONTINUE và MARK_RAN tùy phạm vi/cấu hình Liquibase. Phải hiểu hành vi chính xác của phiên bản đang dùng và vị trí khai báo precondition.

Với migration bắt buộc, HALT thường giúp dừng an toàn khi giả định sai. WARN có thể cho phép tiếp tục; chỉ dùng nếu điều đó được thiết kế và review. CONTINUE có thể bỏ qua changeset trong lần chạy hiện tại. MARK_RAN ghi nhận changeset như đã chạy dù change không được thực thi; nó không tạo ra đối tượng bị thiếu.

### 13.2. Không dùng MARK_RAN để che lỗi dependency

Nếu bảng cha hoặc constraint bắt buộc chưa tồn tại, MARK_RAN có thể làm history trông như đã hoàn tất trong khi schema chưa đạt. Chỉ dùng MARK_RAN cho trường hợp migration thực sự không cần chạy vì hậu điều kiện đã tồn tại và đã được xác minh, không phải để bỏ qua một thay đổi còn thiếu.

### 13.3. SQL check phải có chi phí hợp lý

Precondition SQL có thể chạy mỗi lần Liquibase kiểm tra changelog tùy cấu hình. Một COUNT(*) trên bảng hàng trăm triệu dòng có thể làm chậm startup. Ưu tiên metadata/catalog check hoặc native constraint validation khi phù hợp; dùng query dữ liệu chính xác ở bước kiểm tra có kế hoạch và có đo tải.

## 14. Dependency và quyền database

Lỗi dependency đôi khi thực chất là lỗi quyền:

- Không có quyền USAGE trên schema.
- Không có quyền CREATE trong schema.
- Không có quyền ALTER/DROP đối tượng.
- Không có quyền tạo extension hoặc function.
- Không có quyền ghi DATABASECHANGELOG/LOCK.
- Đối tượng được tạo bởi owner khác và migration user không có quyền.

Kiểm tra principal thực tế của connection, role membership, schema owner và grants. Cấp đúng quyền trên đúng schema/đối tượng. Không đổi owner hàng loạt hoặc cấp superuser nếu chưa hiểu tác động.

### 14.1. Tách quyền migration và runtime

Migration user có thể cần quyền DDL, trong khi runtime user chỉ cần quyền nghiệp vụ. Nếu migration chạy qua Spring Boot startup, xác định rõ DataSource nào được Liquibase sử dụng và DataSource nào phục vụ request.

Tách credentials giúp giảm tác động khi ứng dụng bị xâm nhập. Secret phải được inject lúc runtime và không ghi vào changelog, properties đã commit hoặc log.

## 15. Liquibase báo lỗi checksum hoặc changeset đã chạy

Khi changeset đã được triển khai, sửa nội dung file có thể tạo checksum mismatch. Đây không phải lỗi dữ liệu trực tiếp, nhưng có thể khiến update dừng trước khi đến changeset tiếp theo.

Điều tra:

1. Đọc id, author, filename và checksum trong DATABASECHANGELOG.
2. So với file trong artifact đang chạy.
3. Xác định changeset đã được deploy ở môi trường nào.
4. Kiểm tra thay đổi có chủ đích hay file bị sửa ngoài quy trình.
5. Khôi phục nội dung đã phát hành hoặc tạo changeset mới theo yêu cầu.

Không sửa changeset lịch sử để sửa dữ liệu hiện tại. Tạo changeset mới hoặc quy trình forward-fix. Không chạy clear-checksums nếu chưa xác định nguyên nhân và tác động.

### 15.1. File path là một phần của định danh

Liquibase thường nhận diện changeset qua id, author và logical file path. Di chuyển changelog hoặc đổi đường dẫn có thể làm thay đổi định danh nếu không giữ logicalFilePath phù hợp. Khi lỗi báo changeset chưa từng chạy nhưng database có đối tượng tương ứng, kiểm tra filename/path và lịch sử trước khi thêm lại DDL.

## 16. Phân biệt lỗi SQL và trạng thái dở dang

Đây là bước quan trọng nhất trước retry.

Ví dụ changeset gồm:

~~~sql
CREATE TABLE app.invoice (...);
CREATE INDEX idx_invoice_customer ON app.invoice(customer_id);
ALTER TABLE app.invoice ADD CONSTRAINT fk_invoice_customer ...;
~~~

Nếu statement đầu và thứ hai đã commit nhưng statement thứ ba thất bại, database có thể còn bảng và index nhưng thiếu FK. Tình huống này phụ thuộc transaction behavior của DBMS và changeset.

### 16.1. Quy trình kiểm tra partial execution

- Kiểm tra bảng có tồn tại không.
- Kiểm tra định nghĩa cột, default, nullability.
- Kiểm tra index có tồn tại và hợp lệ không.
- Kiểm tra constraint có tồn tại/validated không.
- Kiểm tra dữ liệu đã được insert/update đến đâu.
- Kiểm tra history có dòng tương ứng không.
- Xác định statement nào đã commit.

Không chỉ kiểm tra tên object. So sánh định nghĩa thực tế với mục tiêu changelog.

### 16.2. Quyết định retry

| Trạng thái vật lý | Cách xử lý |
|---|---|
| Chưa có thay đổi | Sửa nguyên nhân và retry khi an toàn |
| Đối tượng đã tồn tại đúng | Xác minh nguồn gốc và dùng changeset repair/điều chỉnh có review |
| Đối tượng tồn tại nhưng sai định nghĩa | Lập kế hoạch ALTER/replace có backup và kiểm thử |
| Index invalid | Xử lý index invalid theo DBMS trước retry |
| Dữ liệu đã chuyển đổi một phần | Tiếp tục backfill idempotent hoặc phục hồi theo checkpoint |
| Changeset đã ghi history nhưng hậu điều kiện sai | Điều tra execution type; tạo forward-fix, không xóa history tùy tiện |

Nếu changeset chứa nhiều statement và có thể chạy một phần, hãy cân nhắc tách thành changeset nhỏ ở thiết kế mới. Với changeset đã phát hành, không tự sửa lịch sử trên mọi môi trường mà chưa đánh giá checksum và trạng thái từng database.

## 17. Lock và timeout trong lúc migration lỗi

Migration có thể dừng vì chờ DATABASECHANGELOGLOCK hoặc lock do transaction/DDL khác giữ. Cần phân biệt Liquibase lock với lock nghiệp vụ của DBMS.

### 17.1. Khi Liquibase chờ changelog lock

Kiểm tra:

- Có một Liquibase process khác đang chạy không?
- Job trước có bị kill khi đang migration không?
- Database nào chứa bảng lock?
- Lock có được giữ bởi runner còn sống không?
- Deployment có chạy song song hai instance ứng dụng cùng auto-migrate không?

Không xóa lock chỉ vì thấy trạng thái locked. Trước tiên xác nhận process giữ lock đã kết thúc và không còn transaction/DDL đang chạy. Sau đó dùng cơ chế release lock được Liquibase hỗ trợ theo quy trình vận hành, đúng database và đúng môi trường.

### 17.2. Khi DDL chờ lock

Tìm blocker và transaction dài theo công cụ của DBMS. Đánh giá có nên chờ, cancel DDL, dừng writer hay chuyển sang cửa sổ triển khai khác. Nếu hủy câu lệnh, kiểm tra trạng thái đối tượng sau đó; không giả định lệnh chưa tạo ra bất kỳ thay đổi nào.

Đặt lock timeout/statement timeout có chủ đích. Timeout giúp DDL thất bại nhanh hơn thay vì gây hàng đợi request kéo dài, nhưng sau timeout vẫn cần kiểm tra partial state.

## 18. Quy trình xử lý sự cố theo từng bước

Dùng quy trình sau cho một migration production thất bại:

### Bước 1. Dừng rollout liên quan

Nếu schema có thể đang ở trạng thái trung gian, dừng rollout ứng dụng phụ thuộc thay đổi đó. Không tự động chạy lại pipeline hoặc khởi động thêm Liquibase runner.

### Bước 2. Xác nhận target và artifact

Ghi nhận database, schema, root changelog, artifact version/digest, Liquibase version, context/label và migration user. Xác minh đang điều tra đúng môi trường.

### Bước 3. Xác định changeset và lỗi gốc

Đọc nested exception, SQLState/vendor code và SQL statement. Xác định lỗi dữ liệu, constraint, dependency, quyền, lock hay kết nối.

### Bước 4. Kiểm tra history và database state

Đọc DATABASECHANGELOG, checksum, execution type và DATABASECHANGELOGLOCK. Kiểm tra catalog và dữ liệu thực tế liên quan.

### Bước 5. Chụp bằng chứng trước khi sửa

Lưu log đã redacted, truy vấn kết quả, schema definition, trạng thái constraint/index, số dòng vi phạm và backup/snapshot theo mức độ rủi ro.

### Bước 6. Tìm nguyên nhân gốc

Xác định nguồn dữ liệu sai, writer tạo vi phạm, dependency thiếu, filter sai, quyền không đủ hay DBMS behavior khác dự kiến. Không chỉ sửa biểu hiện.

### Bước 7. Chọn phương án sửa

Có thể là sửa dữ liệu, triển khai writer tương thích, bổ sung dependency, cấp quyền tối thiểu, tạo index, thay đổi thứ tự, backfill, retry hoặc forward-fix. Chọn phương án giữ nguyên invariant nghiệp vụ.

### Bước 8. Kiểm thử trên bản sao

Chạy đúng artifact và cấu hình trên database có schema/data đại diện. Kiểm tra cả fresh install và upgrade path khi cần. Đo thời gian, lock và tác động.

### Bước 9. Thực thi có kiểm soát

Chỉ chạy lại khi đã xác minh retry an toàn. Nếu cần repair trạng thái dở dang, ghi lại từng thao tác và người phê duyệt.

### Bước 10. Hậu kiểm và đóng sự cố

Xác minh schema, dữ liệu, constraint, index, history, ứng dụng và replication. Ghi nguyên nhân gốc, tác động, cách sửa và hành động ngăn tái diễn.

## 19. Chọn retry, rollback hay forward-fix

Không có một hành động mặc định cho mọi lỗi.

| Lựa chọn | Khi phù hợp | Rủi ro cần xem |
|---|---|---|
| Retry | Nguyên nhân tạm thời đã hết, changeset idempotent và trạng thái trước được xác minh | DDL/data có thể đã chạy một phần |
| Rollback | Có rollback đã kiểm thử và đảo ngược an toàn trạng thái hiện tại | Mất dữ liệu, DDL không transactional, ứng dụng đã ghi dữ liệu mới |
| Forward-fix | Database đã tiến một phần hoặc rollback gây mất dữ liệu | Cần thiết kế changeset mới và kiểm tra tương thích |
| Restore/PITR | Dữ liệu hoặc schema không thể sửa an toàn tại chỗ | RPO/RTO, mất giao dịch sau thời điểm backup |
| Dừng và điều tra | Chưa rõ trạng thái hoặc ảnh hưởng | Cần giữ hệ thống ở trạng thái an toàn và truyền thông vận hành |

### 19.1. Retry phải có điều kiện

Trước retry, xác nhận:

- Nguyên nhân lỗi đã được khắc phục.
- Changeset chưa được ghi nhận là hoàn tất, hoặc có thiết kế rerun rõ ràng.
- Database không còn đối tượng dở dang gây xung đột.
- Dữ liệu đã đạt điều kiện.
- Không có runner khác đang giữ lock.
- Artifact/config đúng với lần đã kiểm thử.
- Retry không ghi trùng hoặc ghi đè dữ liệu.

### 19.2. Forward-fix khi changeset đã được triển khai

Nếu changeset đã chạy ở một số môi trường, tạo changeset mới để sửa trạng thái. Không sửa nội dung cũ chỉ nhằm khiến mọi môi trường có checksum giống nhau.

Ví dụ: changeset tạo FK đã chạy thành công ở staging nhưng production có orphan. Sửa dữ liệu production theo quy trình nghiệp vụ, sau đó chạy bước validate phù hợp; không thay đổi changeset đã triển khai ở staging.

## 20. Ví dụ cấu trúc precondition và repair có kiểm soát

Ví dụ kiểm tra dữ liệu trước khi thêm constraint:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-080-require-valid-customer-reference
      author: database-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.orders o
              LEFT JOIN app.customers c ON c.id = o.customer_id
              WHERE o.customer_id IS NOT NULL
                AND c.id IS NULL
      changes:
        - addForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: orders
            baseColumnNames: customer_id
            referencedTableSchemaName: app
            referencedTableName: customers
            referencedColumnNames: id
            constraintName: fk_orders_customers
~~~

Ví dụ này minh họa kiểm tra orphan trước khi tạo FK trực tiếp. Trên bảng lớn, query precondition có thể quét nhiều dữ liệu và thao tác ADD FK có thể giữ lock lâu. Với PostgreSQL, cân nhắc tách ADD NOT VALID và VALIDATE thành các bước riêng. Với DBMS khác, chọn cơ chế tương ứng.

Không thêm precondition COUNT(*) vào mọi lần startup nếu chi phí không phù hợp. Có thể đưa kiểm tra dữ liệu lớn thành một job/approval gate riêng, lưu kết quả và chỉ chạy changeset enforce sau khi đã đạt.

## 21. Bảng tra cứu lỗi nhanh

| Lỗi | Truy vấn/kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| Cannot insert NULL | Đếm NULL, xác định writer | Sửa dữ liệu và writer, rồi enforce |
| Duplicate key | GROUP BY theo unique expression | Hợp nhất/đối soát duplicate, chặn ghi trùng |
| Foreign key violation | Anti-join tìm orphan | Khôi phục/sửa quan hệ, rồi validate |
| Check constraint violation | Query các dòng không thỏa biểu thức | Sửa theo nghiệp vụ hoặc xem lại invariant |
| Invalid input syntax/type cast | Tìm giá trị không chuyển đổi được | Chuẩn hóa hoặc dùng cột mới/backfill |
| Relation/table not found | Kiểm tra target, schema, include và thứ tự | Sửa root/path/dependency |
| Column not found | Kiểm tra changeset tạo cột, filter, case | Sửa thứ tự hoặc filter |
| Function/sequence missing | Kiểm tra object dependency và quyền | Tạo object trước, xác minh owner/grant |
| Permission denied | Kiểm tra principal và grants | Cấp quyền tối thiểu đúng schema |
| Checksum mismatch | So file với DATABASECHANGELOG | Khôi phục lịch sử hoặc forward-fix |
| Changelog lock timeout | Xác minh runner và lock owner | Chờ/dừng process đúng cách, release lock có kiểm soát |
| Index already exists/invalid | Kiểm tra catalog và định nghĩa index | Xử lý index dở dang trước retry |
| Migration chỉ lỗi ở production | So DBMS/version/data/filter/privilege | Tái hiện trên dữ liệu và cấu hình tương đương |

## 22. Bài thực hành: điều tra một FK migration thất bại

**Mục tiêu:** thực hành toàn bộ quy trình trên database lab có thể tạo lại. Không dùng dữ liệu production.

### Bước 1. Chuẩn bị dữ liệu

~~~sql
CREATE TABLE app.customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE app.orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT
);

INSERT INTO app.customers (id, name)
VALUES (1, 'An'), (2, 'Binh');

INSERT INTO app.orders (id, customer_id)
VALUES (101, 1), (102, 2), (103, 999);
~~~

Dòng 103 cố ý tham chiếu customer không tồn tại.

### Bước 2. Chạy migration thêm FK trực tiếp

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-010-add-orders-customer-fk
      author: lab
      changes:
        - addForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: orders
            baseColumnNames: customer_id
            referencedTableSchemaName: app
            referencedTableName: customers
            referencedColumnNames: id
            constraintName: fk_orders_customers
~~~

Dự kiến migration thất bại do orphan row. Đọc root cause từ log và ghi changeset id.

### Bước 3. Kiểm tra history và trạng thái vật lý

- Xem changeset có trong DATABASECHANGELOG không.
- Xác minh FK có tồn tại hay không.
- Chạy anti-join tìm orphan.
- Không xóa history hoặc chạy lại ngay.

Ghi lại kết quả trước khi sửa.

### Bước 4. Sửa dữ liệu theo quy tắc lab

Trong lab, có thể xóa dòng 103 vì đây là dữ liệu synthetic được tạo để thử lỗi. Trong hệ thống thật, phải khôi phục/sửa quan hệ theo nghiệp vụ và audit.

~~~sql
DELETE FROM app.orders
WHERE id = 103;
~~~

### Bước 5. Xác minh dữ liệu và retry

Chạy anti-join lần nữa, xác nhận không còn orphan. Kiểm tra FK chưa tồn tại và changeset chưa được ghi nhận thành công. Sau đó chạy lại migration bằng đúng artifact/config.

### Bước 6. Hậu kiểm

Xác minh:

- FK tồn tại và được validate.
- Insert một customer_id hợp lệ thành công.
- Insert customer_id không tồn tại bị DBMS từ chối.
- DATABASECHANGELOG ghi nhận đúng changeset.
- Ứng dụng vẫn đọc/ghi dữ liệu đúng.

### Bước 7. Thử biến thể NOT VALID trên PostgreSQL

Trong một database lab mới, thêm FK NOT VALID, sửa orphan rồi VALIDATE CONSTRAINT. Quan sát rằng dữ liệu cũ được kiểm tra ở bước validate, trong khi các ghi mới phải tuân thủ FK sau khi constraint được thêm. So sánh lock và thời gian với cách thêm FK trực tiếp.

## 23. Checklist trước khi chạy lại migration

- [ ] Đã xác định đúng database, schema, DataSource và artifact.
- [ ] Đã lưu changeset id, author, filename và root cause.
- [ ] Đã đọc nested exception, SQLState/vendor code và SQL gây lỗi.
- [ ] Đã kiểm tra DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- [ ] Đã xác định DDL/DML có thể đã commit một phần không.
- [ ] Đã kiểm tra schema/catalog và dữ liệu thực tế.
- [ ] Đã tìm nguồn tạo NULL, duplicate, orphan hoặc giá trị sai.
- [ ] Đã xác nhận parent key, object dependency, schema và quyền.
- [ ] Đã kiểm tra context/label/DBMS filter và thứ tự include.
- [ ] Dữ liệu đã được sửa theo quy tắc nghiệp vụ và có audit.
- [ ] Writer mới không tiếp tục tạo vi phạm.
- [ ] Retry đã được đánh giá idempotent và không xung đột đối tượng dở dang.
- [ ] Rollback/forward-fix đã được chọn theo trạng thái thật.
- [ ] Đã test trên database có dữ liệu đại diện.
- [ ] Không sửa hoặc xóa history tùy tiện.
- [ ] Không dùng MARK_RAN để che migration bắt buộc chưa thực hiện.
- [ ] Hậu kiểm constraint, index, schema, dữ liệu và ứng dụng đạt.
- [ ] Log/ticket đã redacted secret và dữ liệu nhạy cảm.

## 24. Kết luận

Khi migration thất bại do dữ liệu, ràng buộc hoặc phụ thuộc, hãy bắt đầu bằng việc phân loại giai đoạn lỗi, đọc root cause và xác định đúng target. Sau đó đối chiếu DATABASECHANGELOG với trạng thái schema/dữ liệu thật để biết changeset chưa chạy, đã chạy hay đã để lại thay đổi một phần. Đây là cơ sở để quyết định sửa dữ liệu, bổ sung dependency, điều chỉnh quyền, retry, rollback hoặc forward-fix.

NOT NULL cần xử lý NULL và mọi writer; UNIQUE cần tìm duplicate theo đúng biểu thức/collation; FOREIGN KEY cần tìm orphan và bảo đảm parent key; CHECK cần xác định dòng vi phạm; chuyển kiểu cần kiểm tra khả năng chuyển đổi và ý nghĩa dữ liệu. Dependency cần được kiểm tra qua thứ tự include, schema, filter, object và quyền. Liquibase quản lý lịch sử và điều phối changeset, nhưng không tự bảo đảm mọi DDL có thể rollback hoặc retry an toàn. Chỉ tiếp tục sau khi trạng thái vật lý được xác minh, nguyên nhân gốc đã được xử lý và hậu điều kiện có thể kiểm chứng.
