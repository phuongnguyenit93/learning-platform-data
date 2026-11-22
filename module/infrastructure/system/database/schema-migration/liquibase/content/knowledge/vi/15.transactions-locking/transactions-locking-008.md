# Thiết kế changeset giảm thời gian khóa và phạm vi ảnh hưởng

## 1. Vì sao một migration đúng vẫn gây gián đoạn?

Một changeset Liquibase có thể đúng cú pháp, vượt qua <code>validate</code> và thực hiện thành công trên database thử nghiệm, nhưng vẫn gây gián đoạn ở production. Ví dụ: thêm ràng buộc vào bảng có hàng chục triệu bản ghi, cập nhật toàn bộ dữ liệu trong một transaction, hoặc tạo chỉ mục bằng cơ chế chặn ghi. Dù cuối cùng schema hợp lệ, ứng dụng có thể gặp timeout, hàng đợi kết nối tăng, truy vấn bị chặn hoặc độ trễ nhân bản dữ liệu kéo dài.

**Thiết kế changeset giảm thời gian khóa và phạm vi ảnh hưởng** không chỉ là làm cho câu SQL “chạy nhanh”. Mục tiêu là kiểm soát **thời gian chờ lấy khóa, thời gian giữ khóa, số hàng/đối tượng chịu tác động, số ứng dụng bị ảnh hưởng, khả năng dừng an toàn và khả năng khôi phục khi lỗi**.

Bài học thuộc chương **Giao dịch và khóa** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng tới việc quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trong bối cảnh đó, một changeset tốt phải có **phạm vi rõ ràng, hành vi khóa dự kiến, cơ chế triển khai phù hợp DBMS và bằng chứng kiểm chứng sau chạy**, chứ không đơn thuần là một nhóm DDL/DML.

Sau bài học, người đọc có thể:

1. Phân biệt khóa điều phối Liquibase với khóa do DBMS đặt lên bảng, hàng hoặc metadata.
2. Nhận diện những thay đổi dễ giữ khóa lâu, như quét bảng, backfill lớn và xây dựng chỉ mục.
3. Chia một thay đổi lớn thành các changeset và các giai đoạn triển khai an toàn.
4. Áp dụng chiến lược *expand–migrate–contract*, backfill theo lô và DDL trực tuyến khi DBMS hỗ trợ.
5. Dự trù transaction, lock timeout, quan sát vận hành, retry và rollback theo phạm vi ảnh hưởng.

## 2. Hai loại khóa cần phân biệt

### 2.1. Khóa điều phối migration của Liquibase

Liquibase dùng bảng <code>DATABASECHANGELOGLOCK</code> để phối hợp việc thực thi changelog, tránh nhiều tiến trình Liquibase cùng cập nhật lịch sử/schema theo những luồng bình thường được công cụ quản lý. Một tiến trình có thể chờ nếu một tiến trình khác đang giữ khóa điều phối.

Khóa này **không đồng nghĩa với khóa bảng nghiệp vụ của DBMS**. Khi Liquibase đã lấy được khóa điều phối, SQL bên trong vẫn phải cạnh tranh các khóa do PostgreSQL, MySQL, SQL Server, Oracle hoặc DBMS khác quản lý.

Ví dụ, một job Liquibase duy nhất có thể giữ thành công khóa trong <code>DATABASECHANGELOGLOCK</code> nhưng câu <code>ALTER TABLE orders</code> vẫn phải chờ một transaction ứng dụng đang truy cập bảng <code>orders</code>.

### 2.2. Khóa và cơ chế đồng bộ của DBMS

DBMS có các loại khóa và cơ chế đồng bộ khác nhau. Các ví dụ thường gặp:

| Hiện tượng | Nguồn gốc | Ảnh hưởng có thể xảy ra |
|---|---|---|
| Row-level lock | Transaction cập nhật các hàng đang dùng | Writer khác đợi trên cùng hàng, tăng latency |
| Table/relation lock | DDL hoặc một số thao tác bảo trì | Có thể chặn đọc, ghi hoặc các DDL khác tùy chế độ khóa |
| Metadata lock | DBMS bảo vệ định nghĩa đối tượng khi có truy vấn/DDL | DDL chờ truy vấn cũ; request mới có thể xếp hàng |
| Deadlock | Các transaction chờ khóa theo vòng | DBMS chọn một transaction làm nạn nhân và trả lỗi |
| Lock wait timeout | Không lấy được khóa trong thời gian quy định | Changeset hoặc câu lệnh thất bại, cần xử lý trạng thái thực |
| Replication lag | DDL/DML lớn gây tải lên luồng sao chép | Replica chậm, ảnh hưởng dịch vụ đọc và khả năng chuyển đổi dự phòng |

Không gán một quy tắc khóa chung cho mọi DBMS. Ngay cả trong cùng DBMS, dạng DDL, phiên bản, kiểu bảng và tùy chọn online/concurrent có thể thay đổi loại khóa hoặc thời gian giữ khóa.

**Bài học quan trọng:** “migration chỉ có một câu SQL” không có nghĩa “phạm vi ảnh hưởng nhỏ”. Một câu <code>ALTER TABLE</code> có thể phải quét, sao chép hoặc khóa bảng lớn; ngược lại, một thay đổi được chia thành nhiều changeset có kiểm soát có thể cho phép ứng dụng tiếp tục phục vụ phần lớn thời gian.

## 3. Đánh giá rủi ro trước khi thiết kế changeset

Trước khi chọn <code>addColumn</code>, <code>addNotNullConstraint</code> hay <code>sql</code>, cần khảo sát dữ liệu và cách sử dụng bảng đích.

| Câu hỏi khảo sát | Bằng chứng cần thu |
|---|---|
| Bảng lớn đến đâu? | Số hàng, kích thước dữ liệu/index, tốc độ tăng |
| Những luồng nào đang dùng bảng? | API đọc/ghi, batch, job nền, ETL, dịch vụ tích hợp |
| Có transaction dài không? | Query/transaction tuổi lớn, phiên giữ khóa, giờ cao điểm |
| DDL có cần quét/rewrite bảng? | Tài liệu DBMS/version, kế hoạch thực thi, chạy thử trên dữ liệu đại diện |
| Có thể tách thay đổi thành giai đoạn tương thích ngược? | Khả năng ứng dụng đọc cả schema cũ và mới, dual-read/dual-write |
| Dữ liệu đang có vi phạm điều kiện mới không? | Truy vấn đếm NULL, orphan records, duplicate, giá trị ngoài miền |
| Ràng buộc hoặc chỉ mục đã tồn tại một phần không? | Metadata/catalog hiện tại, bao gồm trạng thái hợp lệ |
| Rủi ro khi lỗi giữa chừng? | Khả năng rollback DDL của DBMS, trạng thái từng bước, backup/forward fix |
| Có phiên bản ứng dụng cũ đang chạy không? | Chiến lược rolling/canary deploy, thời gian tồn tại instance cũ |

Đặt mục tiêu vận hành **có thể đo lường** cho đợt triển khai. Ví dụ minh họa, không phải ngưỡng chung: chỉ chấp nhận chờ khóa vài giây, duy trì p99 latency của API trong mức SLO đã duyệt, và không để replication lag vượt giới hạn giám sát của hệ thống. Những ngưỡng cụ thể phải do đội vận hành xác định theo dịch vụ và DBMS, không lấy từ ví dụ học tập làm giá trị production.

### 3.1. Ba đại lượng dễ bị nhầm

- **Thời gian thực thi SQL:** tổng thời gian câu lệnh hoàn tất.
- **Thời gian chờ khóa:** khoảng thời gian câu lệnh chờ được cấp khóa cần thiết.
- **Thời gian giữ khóa:** khoảng thời gian transaction hoặc câu lệnh nắm khóa và có thể chặn bên khác.

Một câu DDL chạy nhanh sau khi lấy khóa vẫn có thể chờ lâu và gây xếp hàng. Ngược lại, một thao tác tạo index đồng thời có thể chạy nhiều phút nhưng hạn chế chặn ghi so với cách tạo truyền thống. Phải theo dõi cả ba đại lượng và tác động tới ứng dụng.

## 4. Thiết kế ranh giới changeset theo “một trách nhiệm, một trạng thái kiểm chứng”

### 4.1. Tránh changeset chứa quá nhiều bước không liên quan

Ví dụ anti-pattern:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-all-in-one
      author: db-team
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: status_code
                  type: varchar(24)
        - sql:
            sql: |
              UPDATE orders SET status_code = 'NEW'
              WHERE status_code IS NULL;
        - addNotNullConstraint:
            tableName: orders
            columnName: status_code
            columnDataType: varchar(24)
        - createIndex:
            tableName: orders
            indexName: idx_orders_status_code
            columns:
              - column:
                  name: status_code
~~~

Nếu bảng <code>orders</code> có rất nhiều hàng, câu <code>UPDATE</code> có thể giữ transaction lâu và tạo nhiều WAL/redo/binlog, gây tải và giữ khóa. Bước thêm NOT NULL có thể phải xác minh toàn bảng; bước xây dựng index cũng có khả năng chặn hoặc tạo tải lớn. Gộp tất cả khiến khó xác định bước nào đang gây ảnh hưởng, khó dừng an toàn và khó xử lý khi một thao tác thất bại.

Với PostgreSQL và nhiều DDL có tính giao dịch, transaction dài còn có thể kéo dài thời gian giữ một số khóa đến khi transaction kết thúc. Với MySQL hoặc Oracle, các quy tắc implicit commit khiến việc gộp changes không mang lại tính nguyên tử như dự đoán. Cách xử lý phải dựa vào DBMS cụ thể.

### 4.2. Tách theo kết quả có thể xác minh

Nên tổ chức thành các chặng:

1. **Expand:** thêm cấu trúc mới tương thích ngược, thường nullable và chưa áp ràng buộc nghiêm ngặt.
2. **Chuyển ứng dụng:** phiên bản mới biết ghi/đọc cấu trúc mới; instance cũ vẫn có thể hoạt động trong giai đoạn chuyển tiếp.
3. **Backfill:** chuyển dữ liệu hiện hữu theo lô nhỏ, giám sát tải.
4. **Validate:** kiểm tra các hàng đã được chuyển đầy đủ và phù hợp.
5. **Enforce:** bổ sung NOT NULL, CHECK, FOREIGN KEY hoặc chỉ mục với kỹ thuật giảm khóa phù hợp.
6. **Contract:** chỉ xóa cấu trúc cũ sau khi mọi phiên bản ứng dụng còn hoạt động đã ngừng phụ thuộc.

Không nhất thiết mỗi bước chỉ có một câu SQL. Điểm cốt lõi là **mỗi changeset thực hiện một thay đổi có ý nghĩa, có thể kiểm tra trạng thái và có chiến lược khắc phục riêng**. Những công việc backfill kéo dài hoặc cần throttle có thể thuộc về một job chuyên trách thay vì một transaction Liquibase dài.

### 4.3. Vì sao “càng nhiều changeset càng tốt” cũng không đúng?

Chia nhỏ không phải mục tiêu tự thân. Quá nhiều thay đổi nhỏ có thể kéo dài tổng thời gian, tăng số lần lấy khóa, tạo thêm điểm thất bại và làm phức tạp phụ thuộc. Chia nhỏ có lợi khi mỗi đoạn thực sự giảm phạm vi khóa, cho phép kiểm tra trạng thái hoặc tạo một điểm dừng an toàn.

Nên thiết kế ranh giới dựa trên **rủi ro và khả năng quan sát**: thay đổi metadata nhanh, backfill lâu, validate dữ liệu và thay đổi ràng buộc là những trách nhiệm có tính vận hành khác nhau.

## 5. Chiến lược expand–migrate–contract cho bảng đang phục vụ

Giả sử một ứng dụng quản lý đơn hàng muốn chuyển trạng thái văn bản cũ <code>orders.legacy_state</code> sang <code>orders.status_code</code>, yêu cầu cuối cùng là cột mới bắt buộc có giá trị và có index để truy vấn.

### Giai đoạn 1: Expand — thêm cột tương thích ngược

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-add-orders-status-code
      author: db-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: orders
        - not:
            - columnExists:
                tableName: orders
                columnName: status_code
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: status_code
                  type: varchar(24)
      rollback:
        - dropColumn:
            tableName: orders
            columnName: status_code
~~~

Đây là **changeset minh họa**; khi đưa vào production phải cân nhắc nguy cơ mất dữ liệu nếu rollback <code>dropColumn</code> sau khi ứng dụng đã ghi dữ liệu vào cột mới.

Việc thêm một cột nullable không kèm biểu thức mặc định phức tạp thường là bước mở rộng có khả năng ít ảnh hưởng hơn so với gộp thêm cột, backfill và ràng buộc vào một câu lệnh. Nhưng **không cam kết là thao tác metadata-only trên mọi DBMS/phiên bản**. Một số tùy chọn ALTER TABLE có thể làm bảng bị rewrite hoặc giữ khóa mạnh; cần kiểm tra loại DDL mà Liquibase sẽ sinh.

### Giai đoạn 2: chuyển ứng dụng

Ứng dụng mới có thể được sửa để:

- Ghi <code>status_code</code> cho bản ghi mới.
- Tạm thời đọc từ <code>status_code</code>, và có chính sách fallback có kiểm soát cho hàng chưa được backfill.
- Không xóa hay ngừng cập nhật <code>legacy_state</code> ngay khi còn instance cũ đang đọc/ghi nó.
- Giám sát số bản ghi mới vẫn có <code>status_code IS NULL</code>.

Cần chọn rõ thời điểm bật *dual-write* và cách xử lý lỗi một phía; không tự giả định hai thao tác ghi ở các service khác nhau sẽ nguyên tử.

### Giai đoạn 3: backfill theo lô

Chuyển dữ liệu cũ thành cột mới theo những transaction có kích thước và thời lượng giới hạn. Có thể dùng job ứng dụng hoặc công cụ migration dữ liệu chuyên trách (xem mục 6).

### Giai đoạn 4: kiểm tra dữ liệu

~~~sql
SELECT COUNT(*) AS not_migrated
FROM orders
WHERE status_code IS NULL;
~~~

Số lượng bằng 0 chỉ chứng minh trạng thái tại thời điểm kiểm tra; cần xác nhận writer đã chuyển sang ghi cột mới và không tạo NULL trở lại.

### Giai đoạn 5: enforce

Sau khi dữ liệu và ứng dụng sẵn sàng, áp NOT NULL hoặc ràng buộc tương đương theo phương án được DBMS hỗ trợ. Trên bảng lớn, nên xem xét kỹ cách database xác thực ràng buộc, lock mode và khả năng tách giai đoạn.

### Giai đoạn 6: contract

Chỉ sau khi toàn bộ truy vấn, API, báo cáo, job nền và phiên bản ứng dụng cũ đã ngừng phụ thuộc <code>legacy_state</code>, mới tạo changeset riêng để bỏ cột cũ. <code>DROP COLUMN</code> là thay đổi có thể gây mất dữ liệu và có hành vi khóa phụ thuộc DBMS.

**Lợi ích:** thay vì đặt toàn bộ rủi ro trong một thời điểm khóa dài, hệ thống có nhiều điểm kiểm chứng và điểm dừng có kiểm soát, đồng thời giảm yêu cầu dừng ứng dụng.

## 6. Backfill lớn: giữ transaction ngắn và có khả năng tiếp tục

Backfill toàn bảng trong một <code>UPDATE</code> thường là nguồn phát sinh áp lực lớn:

~~~sql
-- Anti-pattern trên bảng rất lớn đang phục vụ:
UPDATE orders
SET status_code = 'NEW'
WHERE status_code IS NULL;
~~~

Ngay cả khi lệnh sử dụng index, nó vẫn có thể sửa rất nhiều hàng trong một transaction, tạo nhiều log, giữ các khóa hàng và gây replication lag. Để giảm phạm vi ảnh hưởng, nên dùng **batching/throttling** khi bài toán và DBMS cho phép.

### 6.1. Quy tắc thiết kế batch

- Chọn một khóa phân trang ổn định như ID và một hướng duyệt rõ ràng.
- Giới hạn số hàng hoặc thời gian cho mỗi batch; commit sau từng batch.
- Có checkpoint để resume khi job bị ngắt.
- Thực hiện cập nhật theo điều kiện có thể chạy lại mà không sửa sai dữ liệu đã hoàn tất.
- Theo dõi số hàng thay đổi, p95/p99 latency, replication lag, lock wait và tốc độ xử lý.
- Tự động giảm tốc hoặc dừng khi chỉ số vượt ngưỡng vận hành.
- Không chạy đồng thời nhiều worker trên cùng hàng nếu chưa có cơ chế phân phối an toàn.

Kích thước batch tốt phụ thuộc DBMS, kích thước hàng, index, TPS và giới hạn log/replication. Một batch 1.000 hàng chỉ là ví dụ, không phải khuyến nghị cố định cho mọi hệ thống.

### 6.2. Ví dụ PostgreSQL: cập nhật một batch

Đây là SQL **minh họa cho job backfill có vòng lặp và transaction riêng**, không phải một changeset Liquibase tự động lặp lại mãi:

~~~sql
WITH batch AS (
    SELECT id
    FROM orders
    WHERE status_code IS NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET status_code = 'NEW'
FROM batch
WHERE o.id = batch.id
RETURNING o.id;
~~~

Job gọi câu lệnh trong từng transaction nhỏ, commit rồi đánh giá chỉ số trước khi chạy batch tiếp. <code>SKIP LOCKED</code> có thể giúp tránh chờ những hàng đang bị worker khác khóa, nhưng **không bảo đảm công bằng hoặc mọi hàng đều được xử lý sau một lượt**: phải quét/kiểm tra lại các hàng bị bỏ qua cho tới khi đạt điều kiện kết thúc.

Ví dụ dùng trạng thái <code>'NEW'</code> để minh họa kỹ thuật. Trong nghiệp vụ thực, giá trị <code>status_code</code> phải được suy ra bằng mapping có căn cứ từ dữ liệu gốc. Không được đặt tất cả hàng thành một trạng thái chỉ để hoàn thành backfill nhanh.

Nếu backfill nhiều cột/tính toán phức tạp, cần kiểm tra tính nhất quán theo giao dịch hoặc tổ chức versioning, tránh đọc dữ liệu nguồn ở một thời điểm nhưng ghi đích sau khi dữ liệu nguồn đã bị đổi.

### 6.3. Có nên đưa batch vào một changeset Liquibase?

Không nên tạo một changeset chứa vòng lặp cập nhật hàng triệu bản ghi chỉ để “mọi thứ nằm trong changelog”. Liquibase quản lý changeset và lịch sử triển khai; nó không mặc định là bộ điều phối job dữ liệu dài có throttle, checkpoint và khả năng pause/resume chi tiết.

Có thể chọn:

1. **Changeset nhỏ, hữu hạn:** phù hợp khi khối lượng dữ liệu thấp và có thể đánh giá trước chi phí.
2. **Job backfill chuyên trách:** phù hợp khi dữ liệu lớn, cần throttle, checkpoint, đo tiến độ và retry.
3. **Quy trình lai:** Liquibase mở rộng schema, job chuyển dữ liệu, Liquibase xác thực/enforce rồi thu hẹp schema.

Trong phương án lai, job cần ghi nhận artifact/version, điều kiện hoàn tất và kết quả đối soát để pipeline không áp ràng buộc quá sớm. Không đánh dấu changeset enforce hoàn tất khi backfill vẫn đang chạy.

## 7. Tạo index với mức chặn thấp

Index trên bảng lớn có thể tốn nhiều tài nguyên dù SQL rất ngắn. Thời gian tạo index, loại khóa và khả năng tiếp tục ghi phụ thuộc DBMS và cú pháp.

### 7.1. PostgreSQL: CREATE INDEX CONCURRENTLY

PostgreSQL hỗ trợ <code>CREATE INDEX CONCURRENTLY</code> để giảm việc chặn các thao tác ghi thông thường trong lúc xây dựng index. Nhưng lệnh này **không được chạy trong transaction block**.

Ví dụ Liquibase YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-create-orders-status-index-pg
      author: db-team
      dbms: postgresql
      runInTransaction: false
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: status_code
        - not:
            - indexExists:
                tableName: orders
                indexName: idx_orders_status_code
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY idx_orders_status_code
              ON orders (status_code);
      rollback:
        - sql:
            splitStatements: false
            sql: |
              DROP INDEX CONCURRENTLY IF EXISTS idx_orders_status_code;
~~~

**Tại sao tách thành changeset riêng?**

- <code>runInTransaction: false</code> ảnh hưởng tính nguyên tử. Không nên trộn nhiều thao tác độc lập trong changeset này.
- Concurrent build có thể kéo dài và tiêu thụ CPU/I/O, dù giảm chặn ghi.
- Nếu quá trình bị ngắt, PostgreSQL có thể để lại index ở trạng thái **invalid**, cần kiểm tra catalog thay vì chỉ dựa vào precondition <code>indexExists</code>.
- <code>DROP INDEX CONCURRENTLY</code> ở rollback cũng có hạn chế transaction; phải thử đúng phiên bản Liquibase và PostgreSQL.

Truy vấn kiểm tra trạng thái index trong PostgreSQL:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index i
JOIN pg_class idx ON idx.oid = i.indexrelid
JOIN pg_class tbl ON tbl.oid = i.indrelid
JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'public'
  AND tbl.relname = 'orders'
  AND idx.relname = 'idx_orders_status_code';
~~~

Schema <code>public</code> chỉ là giả định ví dụ; cần thay bằng schema thực tế. Một index có tên đúng nhưng <code>indisvalid = false</code> không được coi là đáp ứng yêu cầu.

### 7.2. MySQL và các lựa chọn online DDL

Một số phiên bản MySQL/InnoDB hỗ trợ tùy chọn DDL như <code>ALGORITHM=INPLACE</code> và <code>LOCK=NONE</code> cho những thao tác phù hợp:

~~~sql
ALTER TABLE orders
ADD INDEX idx_orders_status_code (status_code),
ALGORITHM=INPLACE, LOCK=NONE;
~~~

Khả năng hỗ trợ phụ thuộc phiên bản, storage engine, loại index và trạng thái bảng. Không suy rằng <code>LOCK=NONE</code> sẽ loại bỏ **mọi** metadata lock hoặc không cần kiểm thử. Nếu thao tác không được hỗ trợ, phải có kế hoạch khác; không tự bỏ tùy chọn online để chạy một ALTER TABLE gây khóa dài.

MySQL có các trường hợp DDL implicit commit; transaction của Liquibase không tự làm mọi DDL trở nên có thể rollback bằng transaction. Phải thử SQL trên đúng engine/version và đánh giá thời gian chặn thực tế.

### 7.3. Chọn kỹ thuật theo DBMS chứ không chỉ theo Liquibase

| DBMS | Khả năng cần khảo sát | Điểm thận trọng |
|---|---|---|
| PostgreSQL | Concurrent index, NOT VALID/VALIDATE constraint, phiên bản và lock modes | Concurrent index không dùng transaction block; có thể để lại invalid index |
| MySQL/InnoDB | Instant/in-place/copy algorithm và mức LOCK của ALTER TABLE | Hỗ trợ thay đổi theo phiên bản và loại thao tác; metadata lock vẫn quan trọng |
| SQL Server | Online index operation, cấu hình và edition/version | Không mặc định mọi loại index/edition đều hỗ trợ online |
| Oracle | Online index/DDL options và lock behavior theo phiên bản | DDL và implicit commit có đặc tính riêng |

Không ghép một SQL đặc thù vào changeset chung cho tất cả DBMS. Dùng change type chung khi đáp ứng yêu cầu hoặc tách nhánh theo <code>dbms</code> và kiểm thử từng nhánh.

## 8. Thêm constraint trên bảng lớn: kiểm tra dữ liệu theo giai đoạn

Áp <code>NOT NULL</code>, <code>CHECK</code> hay FK trên bảng có dữ liệu thường phải xét tính hợp lệ của hàng hiện hữu. Việc quét và khóa bảng có thể đáng kể tùy DBMS.

### 8.1. Phân biệt “đã khai báo” và “đã xác thực”

Một số DBMS cho phép tạo constraint để bảo vệ dữ liệu mới trước, rồi xác thực dữ liệu cũ trong một giai đoạn riêng. Ví dụ PostgreSQL hỗ trợ <code>NOT VALID</code> đối với một số loại constraint như CHECK và FOREIGN KEY.

~~~sql
-- PostgreSQL: giai đoạn 1, tạo CHECK nhưng chưa quét xác thực toàn bộ dữ liệu cũ.
ALTER TABLE orders
ADD CONSTRAINT ck_orders_status_nonempty
CHECK (status_code IS NOT NULL)
NOT VALID;

-- PostgreSQL: giai đoạn 2, kiểm tra dữ liệu lịch sử.
ALTER TABLE orders
VALIDATE CONSTRAINT ck_orders_status_nonempty;
~~~

Sau khi tạo một CHECK <code>NOT VALID</code> trên PostgreSQL, các hàng cũ chưa được chứng minh hợp lệ; các thay đổi dữ liệu mới chịu kiểm tra theo quy tắc của constraint. Khi <code>VALIDATE CONSTRAINT</code> thành công, DBMS xác nhận hàng thuộc phạm vi kiểm tra hợp lệ.

Tách hai bước có thể giúp lập kế hoạch thời gian xác thực độc lập với thời điểm bắt đầu bảo vệ dữ liệu mới, nhưng vẫn có thể cần khóa và tiêu thụ I/O. Hãy kiểm tra lock mode, khả năng chạy đồng thời và chi phí trên phiên bản DBMS thực tế.

### 8.2. Chuyển tới NOT NULL cuối cùng

Nếu mục tiêu là cột <code>status_code</code> bắt buộc khác NULL, chỉ tạo CHECK tương đương không nhất thiết có cùng metadata với ràng buộc NOT NULL nguyên thủy. Có thể cần bước riêng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 030-enforce-orders-status-code-not-null
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: status_code
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM orders
              WHERE status_code IS NULL
      changes:
        - addNotNullConstraint:
            tableName: orders
            columnName: status_code
            columnDataType: varchar(24)
~~~

Trên bảng lớn, <code>COUNT(*)</code> với điều kiện và bước enforce đều có thể tốn thời gian. Một số phiên bản PostgreSQL có thể tối ưu việc xác thực NOT NULL khi đã có CHECK phù hợp được xác thực, nhưng vẫn có thao tác DDL và khóa cần xem xét; **không áp dụng giả định tối ưu này cho mọi phiên bản hoặc mọi DBMS**.

Nếu áp ràng buộc bằng nhiều changeset, phải lưu cả trạng thái của từng bước trong kế hoạch vận hành: “CHECK đã khai báo”, “dữ liệu cũ đã validate”, “NOT NULL đã áp dụng” là ba mốc khác nhau.

### 8.3. Với khóa ngoại

Việc thêm FK trên bảng con lớn có thể cần kiểm tra hàng cũ, đồng thời ảnh hưởng thao tác ghi trên bảng cha và con. Trước khi tạo FK:

1. Kiểm tra khóa được tham chiếu có PRIMARY KEY/UNIQUE hợp lệ.
2. Phát hiện orphan records và xử lý dữ liệu bằng quy trình nghiệp vụ.
3. Xem có cần index trên cột con để giảm chi phí tra cứu/thao tác cha không; DBMS có yêu cầu và hành vi khác nhau.
4. Nếu dùng cơ chế chưa validate rồi validate sau, phải có owner và deadline rõ cho giai đoạn xác thực.

Không coi deployment thành công nếu chỉ mới tạo FK chưa validate nhưng báo cáo lại khẳng định “toàn bộ dữ liệu lịch sử đã sạch”.

## 9. Giao dịch ngắn, lock timeout và thất bại an toàn

Một thay đổi giảm khóa tốt không chỉ tối ưu đường chạy thành công, mà còn **giới hạn thời gian bị kẹt** khi không thể lấy khóa.

### 9.1. Tham số transaction trong Liquibase

Liquibase có thuộc tính <code>runInTransaction</code> ở mức changeset. Trong những DBMS và trường hợp hỗ trợ, mặc định thông thường là chạy changeset trong transaction.

- **<code>runInTransaction: true</code>:** có thể phù hợp để giữ tính nhất quán giữa một số change nhỏ khi DBMS hỗ trợ transaction cho SQL đó.
- **<code>runInTransaction: false</code>:** cần cho một số SQL đặc thù không thể ở trong transaction; làm tăng khả năng tồn tại kết quả một phần nếu thay đổi có nhiều lệnh.

**Không đặt <code>runInTransaction: false</code> một cách máy móc để “giảm khóa”.** Tắt transaction ở Liquibase không cam kết câu DDL dùng khóa yếu hơn, và có thể khiến failure recovery khó hơn. Phải xem đúng loại SQL, quy tắc transaction của DBMS và cách Liquibase ghi lịch sử.

### 9.2. Phân biệt lock timeout với statement timeout

- **Lock timeout:** giới hạn thời gian chờ có được khóa.
- **Statement timeout:** giới hạn thời gian câu SQL được phép chạy, thường bao gồm cả thời gian chờ trong những hệ thống hỗ trợ.

Ví dụ các setting của PostgreSQL trong một phiên quản trị được kiểm soát:

~~~sql
SET lock_timeout = '5s';
SET statement_timeout = '10min';
~~~

Hai giá trị là ví dụ minh họa, **không phải khuyến nghị cho production**. Chúng cần phù hợp SLO và loại migration. Chú ý các setting dạng <code>SET</code> có phạm vi phiên; cần kiểm soát lifecycle kết nối và khôi phục setting sau tác vụ, đặc biệt nếu dùng pool hoặc runner có kết nối tái sử dụng.

Đối với một transaction PostgreSQL rõ ràng, <code>SET LOCAL</code> có phạm vi transaction. Nhưng không dùng <code>SET LOCAL</code> rồi kỳ vọng nó vẫn áp dụng cho SQL chạy ngoài transaction trong changeset <code>runInTransaction: false</code>. Phải xác minh câu lệnh thực tế và phạm vi setting trong đúng kết nối mà Liquibase sử dụng.

Trên DBMS khác, tên tham số và cách cấu hình có thể khác. Không mang nguyên cặp PostgreSQL settings sang MySQL hoặc SQL Server.

### 9.3. Chiến lược fail-fast có kiểm soát

Nếu một ALTER TABLE không thể lấy khóa trong ngưỡng đã duyệt, nên **dừng và lên lịch thử lại**, thay vì chờ vô hạn để rồi chặn hàng đợi request mới.

Quy trình khi timeout:

1. Ghi lại SQL, thời điểm, tình trạng lock wait và các phiên liên quan.
2. Kiểm tra DBMS đã áp dụng phần nào của thao tác chưa.
3. Đối chiếu lịch sử <code>DATABASECHANGELOG</code> và metadata object.
4. Chỉ retry sau khi xác nhận trạng thái, lý do bị chặn và quyền triển khai.
5. Không giải phóng khóa Liquibase, kill session hoặc sửa lịch sử bằng tay khi chưa xác minh tiến trình đang chạy.

Hành vi transaction và DDL sau timeout phụ thuộc DBMS; không giả định mọi lỗi sẽ rollback toàn bộ.

## 10. Giảm phạm vi ảnh hưởng theo schema, tenant và tính năng

Một migration ảnh hưởng ít hàng chưa chắc ảnh hưởng ít người dùng. Ví dụ, đổi kiểu cột trên bảng khách hàng dùng chung có thể tác động mọi tenant; thêm ràng buộc trên một schema phụ có thể chỉ tác động một nhóm.

Các cách giới hạn phạm vi:

- **Theo schema/tenant:** xác định rõ schema đích; tránh câu SQL không có schema khi database chứa nhiều schema.
- **Theo tính năng:** dùng feature flag hoặc rollout theo nhóm để ứng dụng hỗ trợ cả schema cũ và mới.
- **Theo đợt dữ liệu:** backfill theo khoảng ID, ngày tạo hoặc shard; tránh giao dịch cập nhật toàn bộ.
- **Theo phụ thuộc:** thay đổi bảng cha, bảng con, view, stored procedure theo thứ tự tương thích.
- **Theo địa lý/cluster:** triển khai theo một kế hoạch điều phối phù hợp kiến trúc; không chạy một changeset tưởng là “global” lên nhiều primary độc lập mà thiếu kiểm soát.

### 10.1. Multi-tenant: kiểm tra schema đích trước khi chạy

Với Liquibase, tham số changelog như <code>${tenant.schema}</code> có thể giúp tái sử dụng cấu trúc migration. Tuy nhiên, nguồn tham số, default schema, nơi lưu <code>DATABASECHANGELOG</code> và URL kết nối là các yếu tố riêng.

Nếu các tenant có schema độc lập, cần quyết định rõ:

- Một lịch sử migration cho mỗi tenant/schema hay lịch sử quản lý tập trung phù hợp kiến trúc?
- Có chạy tuần tự hay cho phép song song nhiều tenant? Bao nhiêu worker là an toàn cho DBMS?
- Job có thể dừng giữa danh sách tenant và tiếp tục từ tenant chưa hoàn tất không?
- Có chứng cứ rằng precondition kiểm tra đúng schema sẽ bị sửa không?

Giới hạn concurrency và theo dõi lock/CPU/I/O trên toàn database; nhiều migration “nhỏ” chạy song song vẫn có thể bão hòa một server dùng chung.

## 11. Preconditions và checksum không thay thế giám sát khóa

Một precondition giúp xác nhận trạng thái như “cột chưa tồn tại” hoặc “số bản ghi NULL bằng 0”. Nhưng:

- Điều kiện đạt tại thời điểm kiểm tra không đảm bảo không có writer làm thay đổi trạng thái ngay sau đó.
- <code>sqlCheck</code> đếm hàng trên bảng lớn cũng có thể gây tải.
- <code>validate</code> kiểm tra cấu trúc changelog theo phạm vi của Liquibase, không mô phỏng toàn bộ khóa/tải.
- <code>status</code> đối chiếu lịch sử changeset, không dự đoán lock time.
- <code>update-sql</code> giúp review SQL nhưng không phản ánh đầy đủ điều kiện runtime và transaction kéo dài.
- Checksum cho biết một phần tính nhất quán của changelog đã triển khai, **không phải chứng nhận database không bị khóa lâu hoặc dữ liệu luôn tương thích**.

Ví dụ precondition ngăn enforce NOT NULL nếu còn bản ghi NULL có thể dùng <code>HALT</code>:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - tableExists:
      tableName: orders
  - columnExists:
      tableName: orders
      columnName: status_code
  - sqlCheck:
      expectedResult: "0"
      sql: SELECT COUNT(*) FROM orders WHERE status_code IS NULL
~~~

Đây là mảnh YAML minh họa để đặt trong changeset. Nó giúp dừng khi dữ liệu chưa sẵn sàng; không đo thời gian sẽ chờ/giữ khóa khi áp DDL. Nếu dữ liệu liên tục được cập nhật, cần phối hợp ứng dụng để bảo đảm không tạo ra giá trị không hợp lệ giữa lúc check và enforce.

**Không dùng <code>MARK_RAN</code> chỉ để vượt qua điều kiện dữ liệu sai.** Điều đó có thể ghi nhận migration đã xử lý trong khi schema thực tế chưa đạt trạng thái mong muốn.

## 12. Quan sát trong lúc triển khai: nhìn cả database và ứng dụng

Một migration có thể tăng độ trễ dịch vụ dù thời gian chạy SQL vẫn trong mức dự kiến. Dashboard chỉ đo thời gian Liquibase update là chưa đủ.

| Tầng quan sát | Chỉ số / dấu hiệu nên theo dõi |
|---|---|
| Liquibase | Changeset đang chạy, thời điểm bắt đầu/kết thúc, lỗi, trạng thái lịch sử và khóa điều phối |
| Database | Blocking sessions, lock wait, active transactions, deadlock, CPU/I/O, log generation |
| Data migration | Batch throughput, số hàng còn lại, retry, số hàng lỗi/không hợp lệ |
| Replication | Độ trễ replica, backlog log, trạng thái đồng bộ |
| Connection pool | Số kết nối đang dùng, hàng đợi lấy kết nối, timeout |
| Ứng dụng | p95/p99 latency, HTTP errors, timeout, các API ghi trọng yếu |
| Nghiệp vụ | Số giao dịch thành công, lỗi tạo đơn, lỗi cập nhật khách hàng, lag của job nền |

### 12.1. Ví dụ quan sát PostgreSQL

Một truy vấn **chỉ đọc** để xem các phiên đang chờ lock:

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock'
ORDER BY query_start;
~~~

Để tìm blocker, PostgreSQL còn có hàm <code>pg_blocking_pids(pid)</code>; quyền xem toàn bộ SQL/phiên có thể bị giới hạn theo vai trò. Truy vấn trên không tự chỉ ra mọi nguyên nhân chờ hoặc mức khóa cụ thể: cần đối chiếu catalog, log và công cụ quan sát DBA.

Không tự động kill một phiên lâu chỉ vì nó xuất hiện trong kết quả. Một transaction đang phục vụ nghiệp vụ quan trọng có thể cần quy trình phối hợp và phê duyệt trước khi can thiệp.

### 12.2. Quy tắc dừng / tiếp tục

Đặt trước ngưỡng dừng và người có quyền quyết định, ví dụ:

- p99 độ trễ hoặc lỗi API vượt SLO trong khoảng quan sát đã quy định.
- Replication lag vượt giới hạn phục hồi/đọc dữ liệu được duyệt.
- Migration chờ khóa quá thời gian đã đặt.
- Batch throughput giảm mạnh trong khi CPU/I/O/lock wait tăng.
- Phát hiện dữ liệu không hợp lệ, kết quả backfill không đối soát được.

Sau khi dừng, phải xác minh trạng thái schema và dữ liệu trước khi resume. Các changeset đã ghi trong <code>DATABASECHANGELOG</code>, index invalid hoặc thay đổi không có transaction đầy đủ là những bằng chứng quan trọng cho quyết định tiếp theo.

## 13. Rollback, forward fix và khả năng dừng giữa chừng

Một thiết kế giảm phạm vi ảnh hưởng phải trả lời: **Nếu dừng sau mỗi chặng, ứng dụng có còn chạy được không?**

| Giai đoạn | Trạng thái nếu dừng | Hướng xử lý |
|---|---|---|
| Sau thêm cột nullable | Schema đã mở rộng, ứng dụng cũ thường vẫn dùng cột cũ | Giữ nguyên, sửa lỗi, chưa cần drop cột mới |
| Giữa backfill | Một phần dữ liệu đã chuyển, phần còn lại chưa | Job idempotent tiếp tục theo batch; app đọc theo chính sách chuyển tiếp |
| Sau tạo index concurrent thất bại | Có thể có index invalid | Kiểm tra catalog, gỡ/tạo lại có kiểm soát |
| Sau tạo CHECK NOT VALID | Dữ liệu mới bị kiểm tra, dữ liệu cũ chưa xác thực | Tiếp tục cleanup và VALIDATE; báo trạng thái trung gian rõ ràng |
| Sau enforce NOT NULL | Dữ liệu và ứng dụng phải sẵn sàng cho điều kiện mới | Tránh deploy app cũ có khả năng ghi NULL; rollback ứng dụng cần tương thích |
| Sau drop cột cũ | Dữ liệu có thể không còn; backward compatibility bị phá | Chỉ chạy khi đã hết phụ thuộc; cần backup/forward fix nếu gặp lỗi |

### 13.1. Rollback Liquibase không hoàn nguyên mọi thứ

Đối với thay đổi schema, Liquibase có thể chạy các thao tác rollback được định nghĩa hoặc được công cụ hỗ trợ. Nhưng:

- Gỡ một constraint không phục hồi dữ liệu đã xóa hoặc sửa.
- Gỡ index không hoàn nguyên hiệu ứng đã xảy ra trong lúc index tồn tại.
- Drop một cột có thể làm mất dữ liệu; rollback bằng addColumn không tạo lại giá trị cũ.
- DDL có implicit commit hoặc <code>runInTransaction: false</code> có thể để lại kết quả một phần sau sự cố.
- Rollback ứng dụng sang phiên bản cũ có thể không tương thích schema đã contract.

**Forward fix** thường thích hợp hơn khi không thể phục hồi chính xác dữ liệu cũ. Nếu migration phá hủy dữ liệu, phải có phương án backup/restore hoặc biến đổi khôi phục có kiểm chứng.

### 13.2. Không chỉnh sửa changeset đã chạy để giảm khóa

Khi nhận ra changeset cũ gây khóa lâu, đừng sửa SQL hoặc đặt lại <code>runInTransaction</code> của changeset đã triển khai rồi kỳ vọng mọi môi trường tự đồng bộ. Điều đó có thể làm checksum khác hoặc tạo lịch sử không nhất quán. Với thay đổi mới, tạo changeset mới hoặc kế hoạch refactor có kiểm chứng; riêng database đã chạy cần xác minh trạng thái trước khi lập kế hoạch.

## 14. Tích hợp với Spring Boot và CI/CD

### 14.1. Chọn nơi chạy migration

Spring Boot có thể tự khởi chạy Liquibase khi khởi tạo ứng dụng nếu được cấu hình bật. Điều này tiện cho hệ thống nhỏ, nhưng một DDL kéo dài hoặc chờ lock có thể khiến instance mới chưa sẵn sàng, ảnh hưởng rolling deployment.

Một lựa chọn phổ biến cho migration rủi ro là chạy **job Liquibase chuyên trách trong CI/CD**, có quan sát và approval riêng, sau đó mới rollout ứng dụng. Khi chọn cách này, cần bảo đảm các instance production không đồng thời auto-run một bản migration khác (ví dụ đặt <code>spring.liquibase.enabled=false</code> ở cấu hình hiệu lực của ứng dụng).

Không có một chiến lược bắt buộc cho mọi tổ chức: điều cần có là **một chủ thể điều phối được xác định, artifact bất biến và kế hoạch dừng/tiếp tục rõ ràng**.

### 14.2. Pipeline đề xuất

~~~text
Chốt release + xác minh DBMS/schema
            |
            v
Kiểm tra kết nối, quyền, transaction dài, kích thước bảng
            |
            v
Validate changelog + status + SQL preview
            |
            v
Đánh giá lock/online DDL + chạy thử trên dữ liệu đại diện
            |
            v
Approval và cửa sổ vận hành
            |
            v
Expand changeset
            |
            v
Ứng dụng tương thích + backfill batch + giám sát
            |
            v
Validate dữ liệu + enforce constraint + kiểm tra index
            |
            v
Xác minh catalog/DATABASECHANGELOG/app metrics
            |
            v
Contract ở một release sau khi hết phụ thuộc cũ
~~~

Các lệnh CLI có ích cho kiểm tra trước:

~~~bash
liquibase --version
liquibase --defaults-file=./config/liquibase-staging.properties validate
liquibase --defaults-file=./config/liquibase-staging.properties status --verbose
liquibase --defaults-file=./config/liquibase-staging.properties update-sql
~~~

Cú pháp có thể khác theo phiên bản Liquibase; ở một số phiên bản, cách gọi lệnh xem trước SQL được trình bày là <code>updateSQL</code>. Dù lệnh nào được hỗ trợ, phải chạy với **cùng artifact, DBMS, schema, contexts/labels và tham số** đã dùng để review.

Lệnh preview không tự cho biết toàn bộ lock mode, số hàng sẽ ghi hoặc khả năng rollback transaction trên production. Cần kế hoạch kiểm thử và quan sát độc lập.

### 14.3. Chống tình trạng “hai release cùng động vào một bảng”

Bảng <code>DATABASECHANGELOGLOCK</code> có thể phối hợp các tiến trình Liquibase, nhưng không ngăn ứng dụng, cronjob hoặc công cụ DBA khác chạy DML/DDL. Pipeline nên ghi rõ cửa sổ migration và quy tắc không chạy các job thay đổi schema khác trên cùng đối tượng khi chưa điều phối.

Nếu nhiều service dùng một database, cần quản lý phụ thuộc: một changeset thay đổi khóa/cột của bảng dùng chung có thể ảnh hưởng nhiều service. Lịch rollout và rollback phải xét tất cả phía sử dụng.

## 15. Tình huống thực hành: thiết kế lại một migration khóa lâu

### 15.1. Bài toán

Hệ thống <code>orders</code> có lượng truy cập ghi liên tục, hàng triệu đơn hàng và ứng dụng được deploy theo rolling update. Yêu cầu cuối cùng:

- Có cột <code>status_code</code> không cho phép NULL.
- Dữ liệu lịch sử được chuyển sang mã trạng thái chuẩn.
- Có index phục vụ truy vấn lọc theo trạng thái.
- Sau cùng có thể bỏ cột <code>legacy_state</code>.

Một kế hoạch “làm tất cả trong một transaction” gây rủi ro chặn ứng dụng và rollback khó.

### 15.2. Kế hoạch chia giai đoạn

| Bước | Đầu ra kiểm chứng | Phạm vi ảnh hưởng dự kiến | Điều kiện đi tiếp |
|---|---|---|---|
| 1. Add nullable column | Cột mới xuất hiện, app cũ còn chạy | Một thay đổi cấu trúc | SQL DDL đã review; có khả năng triển khai với lock budget |
| 2. Deploy app hỗ trợ hai cột | Request mới ghi status_code hợp lệ | Ứng dụng mới, còn giữ tương thích cũ | Không tăng lỗi ghi/đọc |
| 3. Batch backfill | Số NULL giảm theo các lô | Transaction nhỏ, có throttle | Checkpoint, metrics, retry hoạt động |
| 4. Validate dữ liệu | NULL = 0; mapping đạt chuẩn | Truy vấn đọc/đối soát | Writer mới không tạo NULL trở lại |
| 5. Create index online/concurrent | Index đúng và hợp lệ | DDL có tính engine-specific | Catalog hợp lệ, latency/lag đạt ngưỡng |
| 6. Enforce NOT NULL | Ràng buộc cuối cùng đã có | Có thể cần scan/lock | Tiền điều kiện đạt, DBMS hỗ trợ kế hoạch |
| 7. Contract | Cột cũ được loại bỏ | Phá vỡ tương thích nếu còn code cũ | Đã hết instance/job phụ thuộc legacy_state |

### 15.3. Các kịch bản phải thử

1. Bảng đã có <code>status_code</code> nhưng backfill chưa xong: pipeline enforce phải dừng.
2. Batch bị ngắt giữa chừng: chạy lại không đổi sai dữ liệu đã hoàn tất.
3. Một transaction ứng dụng giữ khóa lâu: DDL tuân thủ lock timeout và dừng thay vì chờ vô hạn.
4. Index PostgreSQL đồng thời thất bại: phát hiện invalid index và có cách xử lý.
5. Instance ứng dụng cũ còn chạy: giai đoạn contract chưa được phép bắt đầu.
6. Replication lag hoặc p99 API vượt ngưỡng: job giảm tốc/dừng, không chỉ chờ đến khi changeset kết thúc.

Những kiểm thử này giúp đánh giá tính an toàn vận hành, điều mà thử nghiệm “migration chạy xong trên database trống” không chứng minh được.

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả có thể xảy ra | Cách khắc phục |
|---|---|---|
| Gộp DDL, UPDATE toàn bảng và tạo index trong một changeset | Khóa lâu, log lớn, khó phục hồi khi lỗi | Tách expand/backfill/enforce/index thành bước có checkpoint |
| Nghĩ <code>runInTransaction: false</code> tự giảm lock | Không giảm lock mode và tăng nguy cơ kết quả một phần | Chọn đúng kỹ thuật DDL và transaction theo DBMS |
| Dùng <code>CREATE INDEX</code> thông thường trên bảng lớn mà không đo tải | Có thể chặn ghi và ảnh hưởng SLA | Xem online/concurrent index nếu engine hỗ trợ |
| Quên giới hạn lock wait | DDL có thể chờ dài, yêu cầu mới xếp hàng | Cấu hình lock timeout/cửa sổ triển khai phù hợp |
| Chỉ tính thời gian SQL, không theo dõi app/replica | Deployment “thành công” nhưng người dùng bị timeout | Theo dõi p99, errors, pool, replication lag |
| Backfill tất cả trong một transaction | Nhiều hàng bị khóa, WAL/redo lớn, rollback tốn thời gian | Batch nhỏ, commit, throttle và checkpoint |
| Dùng SKIP LOCKED nhưng không quét lại | Có thể bỏ sót những hàng bị khóa | Đối soát đến khi dữ liệu còn lại đúng điều kiện kết thúc |
| Thêm NOT NULL khi app cũ còn ghi NULL | DML của phiên bản cũ thất bại | Expand–migrate–contract và điều phối app rollout |
| Tạo constraint NOT VALID rồi báo “dữ liệu đã sạch” | Dữ liệu lịch sử có thể vẫn vi phạm | VALIDATE riêng và xác nhận catalog |
| Để nhiều tenant chạy migration song song không giới hạn | Tăng lock contention và I/O tổng | Giới hạn concurrency, theo dõi toàn DB |
| Rerun mù quáng sau DDL lỗi | Có thể gặp đối tượng đã tồn tại hoặc invalid | Kiểm tra metadata + DATABASECHANGELOG trước retry |
| Chỉnh changeset đã triển khai để tối ưu lại | Checksum/lịch sử lệch giữa môi trường | Tạo changeset mới và kế hoạch refactor có kiểm chứng |
| Chỉ test bằng DB trống | Không thấy scan, khóa, backfill và data inconsistency | Test trên dữ liệu đại diện và tải gần thực tế |
| Chọn rollback DROP COLUMN sau khi đã ghi dữ liệu mới | Mất dữ liệu | Dùng forward fix, backup hoặc kế hoạch khôi phục riêng |

## 17. Checklist review trước khi chạy

- [ ] Đã xác định **DBMS và phiên bản** cùng schema/catalog đích, không chỉ xem tên changelog.
- [ ] Đã đo kích thước bảng, số hàng, luồng ghi, index hiện hữu và transaction dài.
- [ ] Đã xác định dạng DDL có quét/rewrite bảng, loại khóa và thời gian chờ dự kiến.
- [ ] Một changeset không gộp các thao tác không liên quan khiến transaction kéo dài.
- [ ] Có các điểm dừng an toàn giữa expand, backfill, validate, enforce và contract.
- [ ] Backfill lớn có batch, commit, checkpoint, idempotence, throttle và đối soát.
- [ ] Online/concurrent DDL đã được kiểm tra theo DBMS/version, không giả định tương thích đa DBMS.
- [ ] <code>runInTransaction</code> chỉ được đổi khi có lý do kỹ thuật, kèm kế hoạch xử lý kết quả một phần.
- [ ] Có lock wait budget, giới hạn thời gian chạy và quy tắc dừng khi app/replica bị ảnh hưởng.
- [ ] Preconditions kiểm tra đúng bảng/cột/dữ liệu nhưng không bị xem là cơ chế thay thế khóa giao dịch.
- [ ] SQL preview và rollback SQL đã được review; metadata sau triển khai có bước xác minh.
- [ ] Những changeset đã chạy không bị chỉnh sửa trực tiếp để tránh lệch checksum.
- [ ] Spring Boot auto-run hoặc job CI/CD được điều phối rõ, tránh nhiều đường migration cạnh tranh.
- [ ] Các phiên bản ứng dụng cũ và các service liên quan vẫn tương thích cho đến giai đoạn contract.
- [ ] Có owner, approval, giám sát và kế hoạch pause/retry/forward fix hoặc restore.

## 18. Tổng kết

Giảm thời gian khóa không đơn giản là đặt <code>runInTransaction: false</code> hay chia mỗi câu SQL thành một changeset. Cần hiểu **Liquibase điều phối migration thế nào, DBMS lấy và giữ khóa ra sao, thay đổi dữ liệu kéo dài bao lâu và ứng dụng nào còn phụ thuộc vào schema cũ**. Các cách thực tế gồm tách giai đoạn expand–migrate–contract, dùng backfill theo lô, chọn online/concurrent DDL đúng engine, đặt ngưỡng chờ khóa và giám sát tác động của migration lên ứng dụng.

Một trình tự đáng tin cậy là: **khảo sát schema và tải → chọn phạm vi changeset → chuẩn bị phiên bản ứng dụng tương thích → triển khai expand → chuyển dữ liệu có checkpoint → validate → áp constraint/index có kiểm soát → kiểm tra catalog và lịch sử → contract khi hết phụ thuộc**. Từng bước phải có bằng chứng hoàn tất và hướng xử lý khi dừng. Cách làm này giúp migration với Liquibase vừa truy vết được bằng changelog/changeset/checksum, vừa giảm rủi ro khóa kéo dài và phạm vi ảnh hưởng trong các môi trường Spring Boot hoặc CI/CD.
