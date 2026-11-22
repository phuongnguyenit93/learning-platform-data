# Phối hợp SQL đặc thù với dbms, preconditions và rollback trong Liquibase

## 1. Bối cảnh và mục tiêu

Liquibase cung cấp các change type có tính khai báo như <code>createTable</code>, <code>addColumn</code>, <code>createIndex</code> và <code>addForeignKeyConstraint</code>. Các change type này cho phép Liquibase sinh câu lệnh phù hợp với hệ quản trị cơ sở dữ liệu (DBMS) khi công cụ và phiên bản hỗ trợ. Tuy nhiên, không phải mọi thao tác đều biểu diễn được trọn vẹn bằng change type chung. Ví dụ: tạo chỉ mục đồng thời trên PostgreSQL, khai báo hàm PL/pgSQL, điều khiển khóa khi thay đổi bảng trong MySQL hoặc sử dụng một cấu trúc DDL đặc thù của Oracle.

Khi đó ta có thể đưa **SQL đặc thù DBMS** vào changelog. Đổi lại, migration phải trả lời ba câu hỏi bổ sung:

1. **DBMS nào được phép chạy?** Dùng thuộc tính <code>dbms</code> để giới hạn changeset hoặc SQL change.
2. **Trạng thái nào phải có trước khi chạy?** Dùng <code>preConditions</code> để kiểm tra các giả định về bảng, cột, dữ liệu và tài khoản thực thi.
3. **Nếu cần hoàn tác hoặc xử lý sự cố, phải làm gì?** Khai báo <code>rollback</code> có chủ đích, hiểu giới hạn transaction và phương án khôi phục dữ liệu.

Bài thuộc chương **SQL và đối tượng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào việc phối hợp các cơ chế đó để một câu SQL phụ thuộc DBMS không vô tình được thực thi sai môi trường hoặc để lại trạng thái khó truy vết.

Sau bài học, người học có thể:

- Phân biệt bộ lọc <code>dbms</code> với precondition kiểm tra loại DBMS.
- Viết một changeset dùng SQL đặc thù, có điều kiện an toàn và rollback tương ứng.
- Tổ chức hai nhánh SQL cho hai DBMS mà không tạo ra lịch sử triển khai mơ hồ.
- Kiểm soát statement splitting, transaction, lệnh DDL không thể chạy trong transaction và SQL nhiều câu lệnh.
- Kiểm chứng thay đổi bằng <code>validate</code>, <code>status</code>, SQL preview, thử nghiệm trên DBMS mục tiêu và trạng thái đối tượng thực tế.

## 2. Khi nào dùng SQL đặc thù thay vì change type chung?

Nguyên tắc thiết kế ưu tiên là **dùng change type khai báo khi nó biểu đạt được yêu cầu và có hỗ trợ tốt trên DBMS đích**. Chỉ chuyển sang SQL thuần khi cần tận dụng tính năng riêng hoặc khi change type không thể biểu diễn chính xác thao tác mong muốn.

| Nhu cầu | Hướng tiếp cận | Lý do |
|---|---|---|
| Thêm một cột thông thường | <code>addColumn</code> | Dễ đọc, dễ phát sinh SQL tương ứng và thường có khả năng rollback tốt |
| Tạo bảng và khóa chính | <code>createTable</code> | Tránh viết riêng DDL cho mỗi DBMS không cần thiết |
| Tạo index thông thường | <code>createIndex</code> | Diễn đạt ý định ở cấp Liquibase |
| Tạo index PostgreSQL bằng <code>CONCURRENTLY</code> | SQL riêng cho PostgreSQL nếu change type/phiên bản không đáp ứng | Yêu cầu cú pháp và quy tắc transaction đặc thù |
| Thực hiện hàm hoặc thủ tục DBMS-specific | <code>sql</code>, <code>sqlFile</code> hoặc change chuyên dụng nếu được hỗ trợ | Cần giữ đúng cú pháp khối lệnh và dấu phân cách |
| Dùng hint, online DDL hoặc tùy chọn chỉ tồn tại ở một DBMS | SQL theo từng DBMS | Không có ý nghĩa tương đương an toàn trên mọi engine |
| Chuyển dữ liệu với biểu thức phức tạp khác nhau | SQL/changeset tách theo DBMS, kết hợp điều kiện kiểm tra | Cần tự quản lý khả năng lặp lại và rollback dữ liệu |

Không phải cứ dùng SQL trực tiếp là nhanh hơn hoặc an toàn hơn. SQL thuần làm giảm khả năng Liquibase tự suy ra rollback và có thể làm tăng độ phụ thuộc vào cú pháp, driver, quyền, kiểu dữ liệu, transaction và phiên bản DBMS.

### 2.1. Ba lớp kiểm soát

Một cách nhìn hữu ích:

~~~text
Chọn changeset cần xét
    │
    ├── dbms / context / label filter
    │         │
    │         ▼
    │    Kiểm tra tiền điều kiện
    │    (preConditions)
    │         │
    │         ▼
    │    Thực thi SQL đặc thù
    │         │
    │         ▼
    │    Ghi lịch sử triển khai
    │         │
    │         ▼
    └── Rollback / xử lý sự cố khi cần
~~~

Đây là sơ đồ khái niệm. Liquibase còn kiểm tra định danh changeset, trạng thái trong <code>DATABASECHANGELOG</code>, checksum và thuộc tính thực thi khác. Không coi thứ tự biểu diễn ở đây là cam kết về mọi bước nội bộ trên tất cả phiên bản Liquibase.

## 3. Thuộc tính dbms: xác định nơi SQL được áp dụng

Trong Liquibase, thuộc tính <code>dbms</code> thường được dùng ở **mức changeset** để chọn loại DBMS được phép thực hiện changeset đó. Một số change type, trong đó có <code>sql</code>, cũng có cấu hình <code>dbms</code> riêng; khả năng và cú pháp phải được kiểm tra theo phiên bản.

Ví dụ changeset chỉ dành cho PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-pg-only-example
      author: db-team
      dbms: postgresql
      changes:
        - sql:
            sql: |
              COMMENT ON TABLE orders
              IS 'Bảng đơn hàng nghiệp vụ';
      rollback:
        - sql:
            sql: |
              COMMENT ON TABLE orders IS NULL;
~~~

Trên PostgreSQL, changeset đủ điều kiện xét thực thi; trên DBMS không khớp, nó không được thực thi theo bộ lọc DBMS của Liquibase. **Việc bị lọc không phải là bằng chứng rằng changelog hợp lệ về mặt nghiệp vụ với DBMS còn lại**; cần có nhánh tương ứng nếu release thực sự phải hỗ trợ thêm engine khác.

Ví dụ có cùng một thay đổi SQL nhưng giới hạn tại SQL change:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-postgres-sql-change
      author: db-team
      changes:
        - sql:
            dbms: postgresql
            sql: |
              COMMENT ON TABLE orders
              IS 'Chỉ phát sinh trên PostgreSQL';
      rollback:
        - sql:
            dbms: postgresql
            sql: |
              COMMENT ON TABLE orders IS NULL;
~~~

Mức giới hạn khác nhau cần được hiểu đúng: nếu cả changeset có nhiều change, chỉ một change bên trong có <code>dbms</code>, các change còn lại có thể vẫn được xét theo quy tắc của chúng. Nếu **toàn bộ changeset** phụ thuộc PostgreSQL, việc giới hạn ở cấp changeset thường dễ review hơn. Không dựa vào giới hạn của một change để suy rằng mọi change trong cùng changeset đã được bảo vệ.

### 3.1. dbms không phải kiểm tra server đích

<code>dbms: postgresql</code> chỉ nói về **loại** cơ sở dữ liệu, không xác nhận:

- Đang kết nối đúng server staging hay production.
- Tên database/catalog và schema có khớp release không.
- Phiên bản PostgreSQL hỗ trợ cú pháp đang dùng hay không.
- Bảng, cột, chỉ mục và dữ liệu đầu vào có đáp ứng điều kiện không.
- Tài khoản migration có đủ quyền hoặc DDL có an toàn với tải đang chạy không.

Vì vậy, cần kiểm chứng cấu hình kết nối và điều kiện dữ liệu độc lập với bộ lọc dbms.

### 3.2. Bộ lọc dbms khác precondition dbms

| Cơ chế | Ý nghĩa | Điều cần tránh |
|---|---|---|
| <code>dbms</code> ở changeset | Chọn những DBMS mà changeset được áp dụng | Coi changeset bị bỏ qua là lỗi dừng triển khai |
| <code>dbms</code> trên SQL change | Giới hạn SQL change cụ thể | Quên rằng các change khác vẫn có thể được xử lý |
| <code>preConditions</code> chứa <code>dbms</code> | Đánh giá một điều kiện đúng/sai, chịu chính sách <code>onFail</code> | Nhầm failure với cơ chế lọc tự nhiên |

Ví dụ precondition yêu cầu DBMS PostgreSQL:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - dbms:
      type: postgresql
~~~

Đoạn này là **mảnh cấu hình precondition**, phải được đặt ở đúng phạm vi changelog hoặc changeset. Khi điều kiện được đánh giá và DBMS không đúng, <code>onFail: HALT</code> yêu cầu dừng. Ngược lại, một changeset đơn thuần có <code>dbms: postgresql</code> trên MySQL có thể chỉ bị lọc khỏi kế hoạch thực thi. Hai cơ chế giải quyết hai mục đích khác nhau.

Nếu dùng cả <code>dbms</code> trên changeset lẫn precondition <code>dbms</code> bên trong chính changeset đó, precondition không nhất thiết được đánh giá trên DBMS mà changeset đã bị lọc. Muốn pipeline **thất bại khi toàn bộ changelog được chạy trên sai DBMS**, cần một bước gate riêng ở phạm vi thích hợp hoặc kiểm tra đích kết nối trước khi gọi Liquibase.

### 3.3. Hỗ trợ nhiều DBMS

Tùy phiên bản, giá trị <code>dbms</code> có thể chấp nhận danh sách DBMS và cú pháp chọn/loại trừ. Ví dụ <code>dbms: postgresql,mysql</code> trong những phiên bản hỗ trợ cho phép changeset được xét trên cả hai engine. Nhưng nếu SQL bên trong chỉ đúng trên PostgreSQL, việc thêm MySQL vào bộ lọc **không làm SQL tự trở nên tương thích**.

Khi có hai cú pháp khác nhau, nên dùng hai changeset riêng, có id riêng và rollback được kiểm chứng riêng; hoặc chọn change type chung khi cùng ý nghĩa.

## 4. preConditions: kiểm tra trạng thái trước SQL đặc thù

<code>preConditions</code> giúp mô tả những giả định mà câu SQL cần để chạy an toàn: bảng đã tồn tại, cột chưa tồn tại, index chưa có, dữ liệu đạt yêu cầu hay tài khoản/DBMS phù hợp.

Một số điều kiện thường dùng:

| Precondition | Mục đích |
|---|---|
| <code>tableExists</code> | Bảng cần thao tác đã tồn tại |
| <code>columnExists</code> | Cột làm đầu vào cho index, constraint hoặc data migration có mặt |
| <code>indexExists</code> | Index đã tồn tại để tránh tạo trùng hoặc phát hiện trạng thái trước đó |
| <code>foreignKeyConstraintExists</code> | Khóa ngoại đã tồn tại theo thông tin metadata |
| <code>dbms</code> | Loại DBMS phù hợp |
| <code>runningAs</code> | Vai trò thực thi phù hợp nếu điều kiện được DBMS hỗ trợ |
| <code>sqlCheck</code> | Kiểm tra một biểu thức dữ liệu/metadata không có precondition chuyên dụng |
| <code>and</code>, <code>or</code>, <code>not</code> | Kết hợp hoặc phủ định các điều kiện |

Ví dụ, điều kiện để tạo index là: bảng <code>orders</code> tồn tại, cột <code>created_at</code> tồn tại và index <code>idx_orders_created_at</code> chưa có.

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - and:
      - tableExists:
          tableName: orders
      - columnExists:
          tableName: orders
          columnName: created_at
      - not:
          - indexExists:
              tableName: orders
              indexName: idx_orders_created_at
~~~

Đây là mảnh precondition sẽ được đặt trong changeset hoàn chỉnh. Phép AND yêu cầu mọi giả định cùng đúng; NOT diễn đạt yêu cầu index chưa có. Đối với index cùng tên nhưng ở schema khác, cần xác định schema bằng cấu hình hoặc tham số thích hợp. Tên tồn tại cũng không chứng minh index có định nghĩa hoặc trạng thái hợp lệ đúng như mong đợi.

### 4.1. onFail và onError không đồng nghĩa

- <code>onFail</code> xử lý trường hợp **điều kiện được đánh giá bình thường nhưng sai**; ví dụ bảng không tồn tại.
- <code>onError</code> xử lý trường hợp **không đánh giá được**; ví dụ truy vấn metadata thất bại, mất kết nối hoặc SQL trong <code>sqlCheck</code> bị lỗi.

Đối với thao tác DDL rủi ro cao, <code>HALT</code> thường là lựa chọn mặc định phù hợp. <code>WARN</code> có thể cho phép xử lý tiếp dù giả định sai; <code>CONTINUE</code> hoặc <code>MARK_RAN</code> có ý nghĩa đặc biệt và chỉ dùng ở phạm vi được Liquibase hỗ trợ.

Không dùng <code>MARK_RAN</code> để né lỗi “đối tượng đã tồn tại” nếu chưa chứng minh đối tượng đó **đúng định nghĩa**. Đánh dấu một changeset là đã chạy trong khi SQL chưa thực hiện có thể làm lịch sử triển khai lệch với schema thực tế.

### 4.2. Precondition là phép kiểm tra, không phải khóa giao dịch

Nếu precondition <code>NOT indexExists</code> đạt ở thời điểm T1 nhưng một tiến trình khác tạo index cùng tên trước T2, câu SQL ở T2 vẫn có thể thất bại. Tương tự, kiểm tra dữ liệu bằng <code>sqlCheck</code> không ngăn writer khác ghi dữ liệu mới sau lúc kiểm tra.

Precondition giúp phát hiện lệch trạng thái sớm; nó **không tự bảo đảm tính nguyên tử** của mọi thao tác DDL hoặc chặn mọi thay đổi đồng thời. Cần cơ chế điều phối migration, quyền truy cập và hiểu biết transaction/locking của DBMS.

## 5. Ví dụ hoàn chỉnh: tạo index PostgreSQL bằng CONCURRENTLY

Trên PostgreSQL, câu lệnh <code>CREATE INDEX CONCURRENTLY</code> được thiết kế để giảm tác động chặn thao tác ghi so với một số cách tạo index thông thường, nhưng có quy tắc quan trọng: **không được chạy bên trong một transaction block**. Đây là ví dụ thích hợp để phối hợp SQL đặc thù, bộ lọc DBMS, preconditions, cấu hình transaction và rollback.

Giả sử bảng <code>orders</code> đã có cột <code>created_at</code>. Một changeset YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-orders-created-at-index-pg
      author: db-team
      dbms: postgresql
      runInTransaction: false
      preConditions:
        - onFail: HALT
        - onError: HALT
        - and:
            - tableExists:
                tableName: orders
            - columnExists:
                tableName: orders
                columnName: created_at
            - not:
                - indexExists:
                    tableName: orders
                    indexName: idx_orders_created_at
      changes:
        - sql:
            dbms: postgresql
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY idx_orders_created_at
              ON orders (created_at);
      rollback:
        - sql:
            dbms: postgresql
            splitStatements: false
            sql: |
              DROP INDEX CONCURRENTLY IF EXISTS idx_orders_created_at;
~~~

**Giải thích từng lớp:**

1. <code>dbms: postgresql</code> tại changeset giới hạn nhánh này cho PostgreSQL.
2. <code>runInTransaction: false</code> cần thiết vì PostgreSQL không cho phép <code>CREATE INDEX CONCURRENTLY</code> trong transaction block.
3. <code>preConditions</code> xác nhận bảng, cột tồn tại và index cùng tên chưa có.
4. <code>sql</code> giữ cú pháp đặc thù mà dự án muốn kiểm soát. <code>splitStatements: false</code> phù hợp với ví dụ một lệnh SQL hoàn chỉnh.
5. <code>rollback</code> gỡ index bằng câu SQL tương ứng của PostgreSQL; <code>DROP INDEX CONCURRENTLY</code> cũng không được chạy trong transaction block.

**Rủi ro quan trọng:** <code>runInTransaction: false</code> làm giảm tính nguyên tử ở cấp changeset. Nếu thao tác thất bại hoặc bị ngắt giữa chừng, PostgreSQL có thể để lại một **index không hợp lệ (invalid index)**. Lần chạy sau không được mặc định rằng có thể tạo lại như cũ; cần kiểm tra catalog và xử lý index invalid theo quy trình DBA được duyệt.

Precondition <code>indexExists</code> chỉ là kiểm tra tồn tại, chưa chứng minh index có trạng thái <code>indisvalid</code>/<code>indisready</code> hoặc định nghĩa cột/biểu thức đúng. Cần xác minh metadata thực tế khi có sự cố.

### 5.1. Xác minh index thực tế trên PostgreSQL

Trên môi trường kiểm thử, sau khi chạy migration có thể đọc catalog:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index i
JOIN pg_class idx
  ON idx.oid = i.indexrelid
JOIN pg_class tbl
  ON tbl.oid = i.indrelid
JOIN pg_namespace ns
  ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'public'
  AND tbl.relname = 'orders'
  AND idx.relname = 'idx_orders_created_at';
~~~

Ví dụ giả định bảng nằm trong schema <code>public</code>; thay bằng schema thực tế. Nếu query không trả hàng hoặc cho thấy index không hợp lệ, không coi deployment là thành công chỉ vì log từng bước trước đó không có lỗi. Kết hợp kết quả catalog với log Liquibase và trạng thái trong <code>DATABASECHANGELOG</code>.

### 5.2. Rollback không phải bảo đảm khôi phục tức thời

Rollback <code>DROP INDEX CONCURRENTLY</code> có thể cần thời gian chờ các transaction khác và chịu giới hạn riêng của PostgreSQL. Nếu bản thân changeset đã thất bại trước khi ghi lịch sử hoàn tất, lệnh rollback tiêu chuẩn của Liquibase có thể **không** được gọi tự động để dọn một index invalid còn sót lại.

Quy trình phục hồi khi gặp sự cố:

1. Xác định chính xác index có tồn tại và hợp lệ không.
2. Kiểm tra trạng thái changeset trong <code>DATABASECHANGELOG</code>.
3. Xác nhận có tiến trình tạo index khác đang chạy không.
4. Lựa chọn gỡ/tạo lại index bằng SQL được review hoặc dùng changeset khắc phục phù hợp.
5. Không xóa/sửa bảng lịch sử hoặc checksum để ép rerun mà chưa đối chiếu đối tượng vật lý.

## 6. Ví dụ nhánh MySQL cho cùng mục tiêu

Nếu ứng dụng cũng chạy trên MySQL, không thể đưa <code>CREATE INDEX CONCURRENTLY</code> vào đó. Một thay đổi có ý định tương tự về mặt nghiệp vụ có thể dùng cú pháp MySQL hỗ trợ online DDL, chẳng hạn trên **InnoDB và phiên bản hỗ trợ**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 011-create-orders-created-at-index-mysql
      author: db-team
      dbms: mysql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: created_at
        - not:
            - indexExists:
                tableName: orders
                indexName: idx_orders_created_at
      changes:
        - sql:
            dbms: mysql
            sql: |
              ALTER TABLE orders
              ADD INDEX idx_orders_created_at (created_at),
              ALGORITHM=INPLACE, LOCK=NONE;
      rollback:
        - sql:
            dbms: mysql
            sql: |
              ALTER TABLE orders
              DROP INDEX idx_orders_created_at;
~~~

Ví dụ này minh họa **một lựa chọn phụ thuộc tính năng**. Trên MySQL, khả năng dùng <code>ALGORITHM=INPLACE</code>/<code>LOCK=NONE</code> phụ thuộc phiên bản, storage engine, loại index và trạng thái bảng. Nếu engine không hỗ trợ một mức online DDL như yêu cầu, cần cho migration thất bại rõ ràng hoặc chọn kế hoạch khác đã được đánh giá, không bỏ <code>LOCK=NONE</code> tùy tiện trên production rồi chấp nhận thời gian khóa không kiểm soát.

MySQL có nhiều thao tác DDL **implicit commit**; khai báo <code>runInTransaction</code> hoặc cố dùng transaction ở phía Liquibase không làm cho mọi DDL có rollback transaction giống PostgreSQL. Vì thế phải có kế hoạch lỗi giữa chừng và xác minh catalog trước retry.

### 6.1. Vì sao dùng id changeset riêng?

Hai changeset <code>010-...-pg</code> và <code>011-...-mysql</code> tạo hai đường triển khai được nhận diện riêng. Mỗi đường có:

- Bộ lọc DBMS độc lập.
- SQL và điều kiện tương ứng.
- Rollback có ý nghĩa trên engine đó.
- Lịch sử và checksum gắn với chính nội dung changeset của nó.

Không nên dùng cùng id/author/path cho nhiều nội dung SQL không tương thích trong các nhánh không được quản lý rõ ràng. Đối với changelog chung đa DBMS, cần test rằng mỗi engine chọn đúng nhánh và **không chọn cả hai hoặc bỏ sót cả hai**.

Nếu không thực sự cần online DDL đặc thù, <code>createIndex</code> của Liquibase có thể là lựa chọn đơn giản hơn và ít nhánh hơn. Hai biến thể SQL không được coi là tương đương về thời gian khóa, kế hoạch thực thi hoặc đặc tính rollback; chúng chỉ cùng nhắm tới mục tiêu có index trên cột <code>created_at</code>.

## 7. Kết hợp điều kiện dữ liệu bằng sqlCheck

Các precondition metadata như <code>tableExists</code> chưa đủ khi SQL tác động tới **dữ liệu hiện hữu**. Nếu migration sắp thêm một ràng buộc yêu cầu dữ liệu sạch, hãy dùng <code>sqlCheck</code> trả về một giá trị đơn.

Ví dụ PostgreSQL: cần bảo đảm bảng <code>invoice</code> không có số tiền âm trước khi bổ sung CHECK constraint.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-invoice-amount-check-pg
      author: db-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - and:
            - tableExists:
                tableName: invoice
            - columnExists:
                tableName: invoice
                columnName: amount
            - sqlCheck:
                expectedResult: "0"
                sql: |
                  SELECT COUNT(*)
                  FROM invoice
                  WHERE amount < 0
      changes:
        - sql:
            dbms: postgresql
            sql: |
              ALTER TABLE invoice
              ADD CONSTRAINT ck_invoice_amount_nonnegative
              CHECK (amount >= 0);
      rollback:
        - sql:
            dbms: postgresql
            sql: |
              ALTER TABLE invoice
              DROP CONSTRAINT ck_invoice_amount_nonnegative;
~~~

Ý nghĩa: yêu cầu bảng/cột tồn tại và số dòng có <code>amount &lt; 0</code> bằng 0. Khi điều kiện sai, <code>onFail: HALT</code> chặn SQL; khi SQL check không thể đánh giá, <code>onError: HALT</code> chặn triển khai.

Những giới hạn phải đánh giá:

- PostgreSQL coi <code>CHECK (amount >= 0)</code> là đạt với giá trị NULL; nếu nghiệp vụ cấm NULL, cần ràng buộc <code>NOT NULL</code> riêng sau khi làm sạch dữ liệu.
- Nếu constraint đã có cùng tên, SQL có thể thất bại; cần kiểm tra catalog/định nghĩa hoặc precondition tương ứng.
- Truy vấn COUNT trên bảng lớn có thể tốn thời gian. Cần kế hoạch đo chi phí hoặc dùng cơ chế validate theo giai đoạn của DBMS khi phù hợp.
- Nếu writer khác cập nhật dữ liệu sau khi <code>sqlCheck</code> đạt, thao tác DDL vẫn có thể gặp cạnh tranh hoặc thất bại. Precondition không phải khóa đồng bộ.
- Rollback gỡ constraint, **không hoàn nguyên** các lần sửa dữ liệu đã thực hiện trước migration.

### 7.1. Xử lý dữ liệu vi phạm trước khi áp dụng constraint

Nếu truy vấn <code>SELECT COUNT(*) ... WHERE amount &lt; 0</code> khác 0, phải có quyết định xử lý nghiệp vụ trước. Không tự chuyển giá trị âm thành 0 hay xóa hóa đơn chỉ để migration đi qua.

Một chuỗi hành động có thể kiểm toán:

1. Xuất danh sách bản ghi vi phạm và xác định nguyên nhân.
2. Đối chiếu nguồn dữ liệu đúng; phân công người duyệt cách sửa.
3. Thử bản sửa trong môi trường an toàn với dữ liệu đại diện.
4. Chạy lại <code>sqlCheck</code> bằng đúng kết nối/schema dự kiến.
5. Chỉ sau đó mới thực hiện changeset tạo constraint.

Nếu data cleanup có thể mất dữ liệu hoặc không đảo ngược được, phải có phương án backup/restore hoặc forward fix riêng. Không nên viết rollback giả định rằng có thể suy ra giá trị cũ từ giá trị đã làm sạch.

## 8. Thiết kế rollback cho SQL thuần

Đối với nhiều change type khai báo, Liquibase có thể hỗ trợ rollback tự động. **Với SQL thuần, không nên giả định Liquibase tự tạo được câu SQL đảo ngược đúng ý nghĩa nghiệp vụ.** Hãy khai báo rollback có chủ đích và thử nghiệm.

| SQL thay đổi | Ý tưởng rollback | Giới hạn cần giải thích |
|---|---|---|
| <code>CREATE INDEX</code> | <code>DROP INDEX</code> | Phụ thuộc cú pháp DBMS, schema, tên và tình trạng index |
| <code>ADD CONSTRAINT</code> | <code>DROP CONSTRAINT</code> | Không hoàn nguyên dữ liệu đã sửa trước đó |
| <code>CREATE VIEW</code> mới | <code>DROP VIEW</code> | Chỉ an toàn khi view chưa tồn tại trước migration và không có phụ thuộc mới |
| <code>ALTER TABLE ... ADD COLUMN</code> | <code>DROP COLUMN</code> | Có thể mất dữ liệu cột mới; cần đánh giá |
| <code>UPDATE</code> dữ liệu | Phục hồi từ snapshot/mapping có lưu vết | Không thể mặc định khôi phục giá trị cũ bằng phép đảo |
| <code>DELETE</code> dữ liệu | Restore từ backup hoặc bảng lưu trước | Không thể khôi phục dữ liệu đã xóa nếu không lưu trạng thái trước |
| <code>CREATE OR REPLACE FUNCTION/VIEW</code> | Khôi phục định nghĩa phiên bản trước | <code>DROP</code> có thể làm mất đối tượng vốn đã tồn tại |

Rollback cho SQL đặc thù cần đáp ứng **tính đúng đối tượng**, **tính đúng trạng thái ban đầu** và **cú pháp đúng DBMS**.

### 8.1. Không dùng DROP khi đang thay thế đối tượng cũ

Giả sử changeset:

~~~sql
CREATE OR REPLACE VIEW v_order_summary AS
SELECT id, created_at FROM orders;
~~~

Nếu view <code>v_order_summary</code> đã tồn tại trước migration, rollback bằng <code>DROP VIEW v_order_summary</code> không phải hoàn nguyên: nó xóa luôn view cũ. Cần lưu và phục hồi định nghĩa trước đó bằng artifact được quản lý hoặc tạo changeset khôi phục có kiểm chứng.

Trường hợp này khác với một <code>CREATE VIEW</code> dành cho đối tượng chắc chắn chưa tồn tại, có precondition kiểm tra vắng mặt và rollback tương ứng.

### 8.2. Rollback trong formatted SQL

Nếu dự án dùng changelog dạng **Liquibase formatted SQL**, có thể khai báo thay đổi và rollback bằng chú thích đặc biệt của Liquibase. Ví dụ minh họa:

~~~sql
--liquibase formatted sql

--changeset db-team:030-create-index-pg dbms:postgresql runInTransaction:false
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON orders (created_at);

--rollback DROP INDEX CONCURRENTLY IF EXISTS idx_orders_created_at;
~~~

Đây là ví dụ **một cách biểu diễn khác** cho mục tiêu đã nêu, không phải changeset bổ sung chạy cùng lúc với changeset YAML ở phần 5. Formatted SQL yêu cầu cú pháp metadata và phiên bản hỗ trợ phù hợp. Nếu dùng lệnh nhiều statement, stored procedure hoặc custom delimiter, cần kiểm tra cách parser tách lệnh của phiên bản Liquibase đang dùng.

### 8.3. Kiểm tra rollback trước khi deploy

Nên review bản SQL rollback bằng lệnh xem trước rollback của phiên bản CLI tương ứng và kiểm thử trong môi trường cô lập. Một rollback được kiểm chứng phải xác nhận:

- Nó nhắm đúng đối tượng được tạo/sửa và đúng schema.
- Nó không phá hủy dữ liệu hoặc định nghĩa tồn tại trước migration.
- Nó chạy được với quyền của migration role.
- Nó phù hợp với transaction/locking của DBMS, kể cả khi DDL có implicit commit.
- Nó không dựa vào giả định các changeset khác chưa chạy hoặc ứng dụng không còn truy cập đối tượng.

Đừng chọn rollback chỉ vì có cú pháp hợp lệ. Với thao tác dữ liệu hoặc DDL rủi ro, **forward fix** hoặc restore từ backup có thể an toàn hơn rollback tự động.

## 9. runInTransaction và sự khác biệt giữa các DBMS

Liquibase thường cố gắng bao changeset trong transaction khi DBMS hỗ trợ. Tuy nhiên, SQL riêng của engine có thể yêu cầu chạy ngoài transaction, hoặc DDL của engine có thể commit theo cơ chế riêng.

| Tình huống | Hệ quả vận hành |
|---|---|
| PostgreSQL DDL thông thường trong transaction | Nhiều DDL có thể rollback theo transaction, nhưng không phải mọi câu DDL đều được phép trong transaction |
| PostgreSQL <code>CREATE INDEX CONCURRENTLY</code> | Không chạy trong transaction block; cần <code>runInTransaction: false</code> |
| MySQL DDL như <code>ALTER TABLE</code> | Có thể implicit commit; đừng suy rằng rollback transaction sẽ đảo ngược DDL |
| SQL Server/Oracle hoặc DBMS khác | Quy tắc transaction, locking, commit và loại DDL hỗ trợ khác nhau |
| Changeset có nhiều SQL khi <code>runInTransaction: false</code> | Thao tác thành công trước đó có thể còn tồn tại khi câu sau lỗi; rủi ro ghi lịch sử lệch trạng thái vật lý |

Nguyên tắc: nếu một thao tác yêu cầu <code>runInTransaction: false</code>, **ưu tiên changeset nhỏ, tập trung một hành động**. Đừng gộp tạo index, sửa dữ liệu và đổi ràng buộc không liên quan vào cùng changeset không có transaction. Sau lỗi, kiểm tra catalog và lịch sử thay vì rerun mù quáng.

### 9.1. Tính nguyên tử không đồng nghĩa với khả năng rollback nghiệp vụ

Một transaction thành công hoặc có thể rollback ở DBMS không tự đảm bảo dữ liệu nghiệp vụ có thể phục hồi khi đã deploy ứng dụng mới. Ví dụ, nếu đổi ý nghĩa một cột tiền tệ bằng <code>UPDATE</code> thì rollback SQL có thể cần dữ liệu gốc mà transaction đã commit không còn giữ.

Phân biệt:

- **Rollback transaction:** DBMS hủy thao tác chưa commit trong phạm vi nó hỗ trợ.
- **Rollback Liquibase:** thực thi tập change ngược/SQL ngược trên các changeset được chọn.
- **Khôi phục nghiệp vụ:** đưa schema và dữ liệu về trạng thái ứng dụng có thể sử dụng, có thể cần backup, logic nghiệp vụ hoặc forward migration.

Đừng đánh đồng ba hình thức này khi phê duyệt release.

## 10. SQL nhiều câu lệnh, sqlFile và dấu phân cách

SQL đặc thù thường chứa các khối như procedure, trigger, anonymous block hoặc cú pháp có dấu chấm phẩy bên trong. Nếu công cụ tự tách lệnh theo dấu <code>;</code> mà không hiểu cú pháp DBMS, SQL có thể bị chia sai.

Liquibase có các tùy chọn liên quan trên một số change type:

| Tùy chọn | Vai trò |
|---|---|
| <code>splitStatements</code> | Điều khiển việc tách SQL thành các câu lệnh |
| <code>endDelimiter</code> | Xác định chuỗi kết thúc lệnh theo cấu hình được hỗ trợ |
| <code>stripComments</code> | Điều khiển việc lược bỏ chú thích SQL |
| <code>sqlFile.path</code> | Đường dẫn tệp SQL bên ngoài changelog |
| <code>relativeToChangelogFile</code> | Diễn giải đường dẫn tương đối theo changelog trong trường hợp được hỗ trợ |
| <code>encoding</code> | Cách giải mã nội dung tệp SQL |

Ví dụ mảnh change <code>sqlFile</code> ở trong changeset:

~~~yaml
changes:
  - sqlFile:
      path: sql/postgresql/create-order-audit-function.sql
      relativeToChangelogFile: true
      dbms: postgresql
      encoding: UTF-8
      splitStatements: false
      stripComments: false
~~~

Đường dẫn trên **chỉ mang tính minh họa** cho cấu trúc một dự án. Không có tệp SQL nào được tạo trong bài học này. Khi dùng thật, cần xác nhận đường dẫn, artifact đóng gói và khả năng hỗ trợ các thuộc tính trên phiên bản Liquibase.

### 10.1. Ví dụ khối PL/pgSQL

Một anonymous block của PostgreSQL có thể chứa nhiều dấu <code>;</code> bên trong:

~~~sql
DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'orders'
    ) THEN
        RAISE EXCEPTION 'orders table is missing';
    END IF;
END;
$migration$;
~~~

Nếu đưa nguyên khối vào <code>sql</code> hoặc <code>sqlFile</code>, hãy kiểm tra cấu hình tách lệnh và cách Liquibase gửi SQL tới JDBC driver. <code>splitStatements: false</code> thường phù hợp khi muốn gửi nguyên khối có nhiều dấu chấm phẩy nội bộ. Nó không tự đảm bảo driver/DBMS hỗ trợ nhiều statement trong một lần thực thi.

Không dùng ví dụ này làm phương án thay thế mặc định cho precondition <code>tableExists</code>: chỉ dùng SQL đặc thù khi điều kiện không thể diễn đạt rõ bằng precondition sẵn có hoặc khi có yêu cầu riêng. Đồng thời, không đưa SQL có tác dụng sửa dữ liệu vào <code>sqlCheck</code> hay vào logic kiểm tra điều kiện.

### 10.2. Cẩn thận với comment và delimiter

Những lỗi thường gặp:

- Parser hiểu sai dấu chấm phẩy trong thân procedure.
- Một dấu delimiter từ tệp SQL của SQL client không có cùng ý nghĩa với JDBC/Liquibase.
- Chú thích chứa ký hiệu đặc biệt bị lược bỏ hoặc đi vào SQL ngoài ý định.
- Dùng <code>splitStatements: false</code> cho nhiều statement độc lập mà driver không chấp nhận một lần gửi.
- Đường dẫn <code>sqlFile</code> được resolve từ working directory khác ở CI so với local.

Giải pháp là chạy <code>validate</code>, review SQL thực tế và thử đúng bản Liquibase/JDBC driver/DBMS trong môi trường cô lập. Không xem kết quả hiển thị đẹp trong editor là bằng chứng parser sẽ xử lý đúng.

## 11. Thứ tự phối hợp: dbms, preconditions, rollback

Một thay đổi SQL đặc thù được thiết kế tốt thường có trình tự suy nghĩ như sau:

1. **Xác định ý định:** đối tượng và trạng thái sau thay đổi phải như thế nào?
2. **Xác định engine:** SQL phụ thuộc DBMS nào, phiên bản tối thiểu nào và cần quyền gì?
3. **Xác định schema/tenant:** bảng, cột, index nằm ở đâu; có phụ thuộc default schema hoặc changelog parameter không?
4. **Chọn bộ lọc:** đặt <code>dbms</code> ở cấp phù hợp để không chạy SQL trên engine sai.
5. **Xác định giả định:** bảng/cột tồn tại, index chưa có, dữ liệu sạch; viết <code>preConditions</code> với <code>HALT</code> cho điều kiện bắt buộc.
6. **Thiết kế SQL:** chọn change type chung hay SQL thuần; xử lý dấu phân cách và transaction.
7. **Thiết kế rollback:** phải gỡ đúng đối tượng, khôi phục định nghĩa cũ hoặc có phương án backup/forward fix.
8. **Kiểm chứng:** dùng SQL preview, thử nghiệm lỗi, xem catalog và kết quả rollback.
9. **Đóng gói release:** cố định changelog, phiên bản Liquibase và bộ tham số cho từng môi trường.

### 11.1. Ví dụ ma trận quyết định

| Môi trường | DBMS | orders tồn tại? | created_at tồn tại? | Index đã có? | Hành động kỳ vọng với nhánh PG |
|---|---|---|---|---|---|
| staging | PostgreSQL | Có | Có | Chưa | Chạy tạo index sau khi precondition đạt |
| production | PostgreSQL | Có | Có | Chưa | Chạy sau review và phê duyệt |
| test | PostgreSQL | Có | Không | Chưa | HALT; không tạo index |
| test | PostgreSQL | Có | Có | Có | HALT nếu policy yêu cầu kiểm tra định nghĩa trước |
| staging | MySQL | Có | Có | Chưa | Bị lọc bởi <code>dbms: postgresql</code>, không chạy nhánh PG |
| staging | PostgreSQL | Không | Không | Chưa | HALT; dữ liệu/schema không đúng giả định |

Nếu chính sách phát hành yêu cầu **tất cả môi trường đều phải có index sau deploy**, việc nhánh PostgreSQL bị lọc trên MySQL phải được bù bằng nhánh MySQL tương ứng. Đừng coi “pipeline không báo lỗi” là chứng minh mục tiêu chung đã đạt.

## 12. Kiểm soát phạm vi bằng context, label và tham số

<code>dbms</code> trả lời “SQL dành cho engine nào?”. Các cơ chế khác phục vụ câu hỏi khác:

- **Context filter:** chọn nhóm changeset theo ngữ cảnh thực thi, ví dụ một giai đoạn migration cụ thể.
- **Label filter:** chọn changeset theo nhãn release, tính năng hoặc nhóm triển khai.
- **Changelog parameters:** thay giá trị như tên schema hoặc tên đối tượng trong định nghĩa.
- **Preconditions:** kiểm tra giả định thực tế trước khi chạy.

Ví dụ cấu trúc:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 040-pg-add-audit-index
      author: db-team
      dbms: postgresql
      contextFilter: migration
      labels: performance
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: audit_event
      changes:
        - sql:
            dbms: postgresql
            sql: |
              CREATE INDEX idx_audit_event_created_at
              ON audit_event (created_at);
      rollback:
        - sql:
            dbms: postgresql
            sql: |
              DROP INDEX IF EXISTS idx_audit_event_created_at;
~~~

Ở ví dụ này, phải hiểu cả bốn lớp: DBMS, context/label, precondition và SQL. Tên thuộc tính filter và cú pháp biểu thức có thể phụ thuộc phiên bản Liquibase; hãy dùng đúng công cụ được dự án cố định. Đặc biệt, **không mặc định một changeset gắn context hoặc label sẽ luôn bị bỏ qua khi không truyền filter**; phải kiểm tra quy tắc lựa chọn thực tế.

### 12.1. Không nhầm parameter với cách chọn DBMS

Tham số <code>${app.schema}</code> chỉ cung cấp giá trị để thay thế tên schema khi Liquibase đọc changelog. Nó không tự chọn engine. Một SQL PostgreSQL vẫn là SQL PostgreSQL dù tham số tên schema trỏ đúng schema trên MySQL.

Khi SQL thuần ghép tên đối tượng từ tham số, còn có rủi ro:

- Tên schema chứa chữ hoa/thường cần quoting phù hợp DBMS.
- Tên không hợp lệ, từ khóa dành riêng hoặc tham số chứa dấu quote làm SQL lỗi.
- Dữ liệu đầu vào không đáng tin cậy làm chèn thêm cú pháp SQL.

Chỉ lấy giá trị từ cấu hình triển khai được kiểm soát, dùng convention tên nhất quán và review SQL **sau khi tham số đã được resolve**. Không đưa user input tùy ý vào identifier trong migration.

## 13. Kiểm chứng trước triển khai trên Spring Boot và CI/CD

Trong hệ thống Spring Boot, Liquibase có thể chạy khi ứng dụng khởi động hoặc chạy qua job CI/CD chuyên trách. SQL đặc thù DBMS thường nhạy cảm với quyền DDL, thời gian khóa và trạng thái dữ liệu; cần chọn rõ **một chiến lược điều phối**.

Pipeline tham khảo:

| Bước | Kiểm tra |
|---|---|
| 1. Chốt artifact | Commit/release, changelog và tệp SQL kèm theo; không sửa trong lúc deploy |
| 2. Chốt runtime | Phiên bản Liquibase, JDBC driver, DBMS và cấu hình connection |
| 3. Kiểm tra filter | <code>dbms</code>, context, label, tham số và schema đích |
| 4. Validate | Changelog có thể được Liquibase đọc và các cấu trúc/định danh hợp lệ |
| 5. Status | Changesets nào chưa được ghi nhận ở database đích |
| 6. SQL preview | SQL dự kiến và rollback SQL trong phạm vi phiên bản công cụ hỗ trợ |
| 7. Kiểm tra dữ liệu | Metadata catalog, orphan/NULL/điều kiện nghiệp vụ và chi phí truy vấn |
| 8. Thử nghiệm | Test đúng DBMS/phiên bản, thử lỗi và phương án rollback/forward fix |
| 9. Phê duyệt | DDL rủi ro, downtime, lock, backup/restore và thời điểm chạy |
| 10. Triển khai | Chạy cùng artifact và bộ cấu hình đã được review |
| 11. Xác minh | Đối tượng thực, trạng thái validation, DATABASECHANGELOG và lỗi ứng dụng |

Ví dụ thao tác CLI để kiểm tra:

~~~bash
liquibase --version
liquibase --defaults-file=./config/liquibase-staging.properties validate
liquibase --defaults-file=./config/liquibase-staging.properties status --verbose
liquibase --defaults-file=./config/liquibase-staging.properties update-sql
~~~

Ở một số phiên bản, lệnh sinh SQL xem trước được trình bày với tên khác như <code>updateSQL</code>; cần dùng cú pháp đúng phiên bản đang chạy. Những lệnh này chỉ là ví dụ quy trình, không dùng trực tiếp trên database thật trước khi kiểm chứng URL/schema và quyền.

**Giới hạn:** <code>validate</code> không chứng minh SQL chạy an toàn; <code>status</code> không chạy thử DDL; <code>update-sql</code> không mô phỏng đầy đủ locking, transaction, dữ liệu và precondition của tất cả chế độ thực thi. Với SQL phụ thuộc DBMS, cần chạy thử trên engine thật và kiểm tra catalog sau triển khai.

### 13.1. Trường hợp nhiều instance Spring Boot

Nếu mỗi instance Spring Boot đều bật Liquibase auto-run, các instance có thể khởi động và cạnh tranh thời điểm thực hiện migration. Liquibase có bảng <code>DATABASECHANGELOGLOCK</code> để phối hợp triển khai, nhưng điều đó **không loại bỏ ảnh hưởng lên startup** hoặc giải quyết mọi va chạm với writer nghiệp vụ.

Với migration DDL lớn hoặc yêu cầu kiểm soát downtime, nhóm có thể dùng job chuyên trách chạy trước giai đoạn khởi động ứng dụng và tắt auto-run ở instance thông qua cấu hình hiệu lực như <code>spring.liquibase.enabled=false</code>. Đây là lựa chọn kiến trúc cần được vận hành thống nhất, không phải quy tắc bắt buộc cho mọi dự án.

### 13.2. Giữ nhất quán giữa preview và update

Không được review SQL trên staging với <code>dbms=postgresql</code> rồi mặc định nhánh MySQL đã an toàn. Mỗi nhánh SQL phải được kiểm thử riêng. Không được đổi changelog, context, label, JDBC URL hay tham số giữa preview và update mà vẫn sử dụng cùng bản phê duyệt.

Nếu cần hỗ trợ production có nhiều phiên bản DBMS, xây dựng ma trận kiểm thử theo engine/version; đừng chỉ đối chiếu tên engine trong bộ lọc.

## 14. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Changeset không chạy trên môi trường dự kiến | <code>dbms</code>, context hoặc label filter không phù hợp | Kiểm tra filter hiệu lực và danh sách pending |
| Pipeline thành công nhưng đối tượng không được tạo | Changeset dành cho engine khác bị lọc | Có nhánh tương ứng hoặc gate bắt buộc cho DBMS đích |
| SQL báo sai cú pháp chỉ trên một engine | Cú pháp đặc thù được dùng trên DBMS không hỗ trợ | Tách changeset theo DBMS; thử trên đúng phiên bản |
| PostgreSQL báo CREATE INDEX CONCURRENTLY không được trong transaction | Thiếu <code>runInTransaction: false</code> | Điều chỉnh changeset phù hợp, test rollback và trạng thái lỗi |
| Sau lỗi tạo index tồn tại nhưng không dùng được | Index PostgreSQL invalid sau concurrent build | Kiểm tra <code>pg_index</code>, xử lý theo kế hoạch khôi phục |
| Precondition đạt nhưng DDL vẫn thất bại | Dữ liệu/metadata đổi giữa check và update hoặc thiếu quyền | Xác định thời điểm, writer và giao dịch/khóa DBMS |
| SQL không được tách đúng | <code>splitStatements</code> hoặc delimiter không phù hợp | Chạy đúng driver/version, điều chỉnh tách lệnh |
| SQL trong procedure bị chia giữa chừng | Dấu chấm phẩy nội bộ hoặc dollar quoting không được xử lý như mong đợi | Dùng <code>sqlFile</code>/<code>splitStatements:false</code> có kiểm chứng |
| Rollback thất bại hoặc xóa nhầm đối tượng | Schema/tên/quote sai, đối tượng đã có trước migration | Review SQL rollback và catalog gốc |
| <code>MARK_RAN</code> nhưng schema không đổi | Dùng onFail để bỏ qua thay đổi chưa đạt điều kiện | HALT, điều tra trạng thái và sửa dữ liệu/schema |
| SQL thay đổi dữ liệu không khôi phục được | Không lưu giá trị cũ, rollback chỉ là phép đảo giả định | Snapshot/backup hoặc forward fix được duyệt |
| Schema đúng trên local nhưng sai production | Default schema hoặc tham số khác nhau | Xác minh connection, property và SQL sau thay thế |
| Rollback script không chạy ở DBMS thứ hai | Rollback dùng SQL đặc thù của engine đầu | Tách và test rollback theo từng nhánh DBMS |
| DDL bị giữ khóa lâu | Locking/online DDL khác dự tính | Đo trên bản sao dữ liệu, cân nhắc chia giai đoạn |
| Checksum không khớp sau sửa SQL cũ | Changeset đã triển khai bị chỉnh sửa | So sánh artifact gốc, không xóa checksum tùy tiện |

Không sửa <code>DATABASECHANGELOG</code> hoặc xóa checksum để che giấu một nhánh SQL không chạy được. Lịch sử và trạng thái vật lý phải được đối chiếu, đặc biệt sau DDL không có transaction đầy đủ.

## 15. Thực hành: ba bài toán cần giải quyết

### 15.1. Bài A — Index đặc thù PostgreSQL

**Yêu cầu:** bảng <code>orders</code> có <code>created_at</code>, cần tạo index bằng <code>CONCURRENTLY</code> để giảm ảnh hưởng ghi.

Hãy:

1. Viết changeset PostgreSQL-only có <code>dbms</code> và <code>runInTransaction:false</code>.
2. Kiểm tra bảng/cột có trước và index chưa có bằng preconditions.
3. Ghi rollback phù hợp với PostgreSQL.
4. Thử trường hợp index chưa tồn tại, index đã tồn tại và bảng chưa có.
5. Trong database thử, mô phỏng một lần tạo index bị gián đoạn rồi kiểm tra trạng thái catalog trước retry.

Kỳ vọng: hiểu rằng <code>HALT</code> khi giả định sai, và <code>runInTransaction:false</code> có hậu quả về failure recovery.

### 15.2. Bài B — Cùng mục tiêu trên hai DBMS

**Yêu cầu:** MySQL và PostgreSQL đều cần index trên <code>orders(created_at)</code>; mỗi engine có một tùy chọn online DDL được phép.

Hãy:

1. Tạo hai changeset với id và <code>dbms</code> riêng.
2. Thử trên PostgreSQL: nhánh PG chạy, nhánh MySQL không được thực thi.
3. Thử trên MySQL: nhánh MySQL chạy khi engine/version hỗ trợ, nhánh PG không thực thi.
4. Đọc SQL preview và metadata index ở cả hai engine.
5. Chạy rollback trên database thử để xác nhận index đúng bị gỡ.

Kỳ vọng: cùng kết quả nghiệp vụ không đồng nghĩa cùng đặc tính locking/transaction. Nếu không cần tính năng riêng, so sánh lại với <code>createIndex</code>.

### 15.3. Bài C — Constraint có dữ liệu vi phạm

**Yêu cầu:** thêm CHECK <code>invoice.amount >= 0</code>, dữ liệu cũ có một số hóa đơn âm.

Hãy:

1. Viết <code>sqlCheck</code> đếm bản ghi âm, kết hợp với <code>tableExists</code>/<code>columnExists</code>.
2. Xác minh khi dữ liệu chưa sạch, changeset dừng với <code>onFail: HALT</code>.
3. Phân loại và sửa dữ liệu trong database thử theo một mapping được duyệt, không tùy ý đặt về 0.
4. Chạy lại changeset; kiểm tra constraint trong catalog.
5. Xác minh hành vi NULL của CHECK và đề xuất NOT NULL riêng nếu nghiệp vụ yêu cầu.
6. Thử rollback: gỡ constraint không làm dữ liệu quay lại các giá trị trước khi làm sạch.

Kỳ vọng: hiểu sự khác nhau giữa tính hợp lệ của SQL, điều kiện dữ liệu và khả năng hoàn nguyên nghiệp vụ.

## 16. Checklist review trước phát hành

- [ ] SQL đặc thù thực sự cần thiết; change type chung không biểu đạt đủ yêu cầu.
- [ ] <code>dbms</code> đã giới hạn đúng ở cấp changeset hoặc SQL change và đã thử trên engine mục tiêu.
- [ ] Nếu mọi engine đều bắt buộc đạt trạng thái sau release, đã có nhánh cho từng engine hoặc gate fail rõ ràng.
- [ ] Tên database/schema, tham số, context và label được resolve đúng môi trường.
- [ ] Preconditions diễn đạt đúng bảng/cột/index/dữ liệu cần có; <code>onFail</code> và <code>onError</code> được chọn có chủ đích.
- [ ] Không dùng <code>MARK_RAN</code> để giấu sự khác biệt giữa catalog và lịch sử.
- [ ] SQL/SQL file được đọc đúng đường dẫn, encoding và dấu phân cách.
- [ ] <code>runInTransaction</code> phù hợp với yêu cầu engine; biết trạng thái có thể còn lại sau lỗi.
- [ ] Rollback có SQL phù hợp DBMS, đúng schema và không phá hủy đối tượng đã tồn tại trước.
- [ ] Thao tác dữ liệu có backup/mapping để phục hồi hoặc hướng forward fix.
- [ ] SQL preview và rollback được review trên phiên bản Liquibase/DBMS tương ứng.
- [ ] Đã thử PASS, FAIL và ERROR của các điều kiện quan trọng.
- [ ] Changelog artifact và bộ tham số giữ nguyên giữa preview và update.
- [ ] Sau deploy có bước kiểm tra metadata, lịch sử <code>DATABASECHANGELOG</code> và chức năng ứng dụng.

## 17. Kết luận

Phối hợp SQL đặc thù với Liquibase đòi hỏi tách rõ **lựa chọn nơi chạy**, **điều kiện được phép chạy** và **cách phục hồi khi cần**. Thuộc tính <code>dbms</code> chọn engine; <code>preConditions</code> kiểm tra trạng thái database; <code>rollback</code> mô tả hành động ngược hoặc giới hạn khôi phục. Với SQL không thể chạy trong transaction hoặc DDL có implicit commit, còn cần quản lý rủi ro khi lỗi giữa chừng và kiểm tra đối tượng vật lý sau mỗi lần triển khai.

Quy trình thực hành đáng tin cậy là **chọn change type phù hợp → giới hạn DBMS → kiểm tra preconditions → review SQL và transaction → thiết kế rollback → thử trên engine thực → triển khai bằng artifact bất biến → xác minh catalog và lịch sử**. Nhờ vậy, những thao tác khó tránh khỏi tính phụ thuộc DBMS vẫn có thể được quản lý bằng changelog, changeset, checksum và lịch sử triển khai rõ ràng, phù hợp khi Liquibase chạy qua Spring Boot hoặc CI/CD.
