# Thiết kế changelog cho nhiều hệ quản trị

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Nhiều cơ sở dữ liệu**, một ứng dụng có thể phải triển khai cùng một mô hình dữ liệu lên nhiều hệ quản trị như PostgreSQL, MySQL/MariaDB, Microsoft SQL Server hoặc Oracle. Mục tiêu thường là giữ **hợp đồng schema và hành vi nghiệp vụ nhất quán**, dù cú pháp DDL, kiểu dữ liệu, cơ chế sinh khóa, index, transaction và khả năng của từng DBMS không hoàn toàn giống nhau.

Liquibase giúp mô tả thay đổi bằng **changelog** và **changeset**, sinh SQL theo database đang kết nối, kiểm tra điều kiện bằng **precondition**, lưu lịch sử trong **DATABASECHANGELOG**, đối chiếu **checksum** và hỗ trợ rollback. Tuy nhiên, một changelog dùng được trên nhiều DBMS không tự xuất hiện chỉ bằng cách đổi JDBC URL. Người thiết kế phải quyết định phần nào có thể dùng change type chung, phần nào cần nhánh theo DBMS và phần nào phải viết SQL riêng.

Mục tiêu của bài học là thiết kế changelog có cấu trúc rõ ràng cho nhiều hệ quản trị, lựa chọn đúng thuộc tính **dbms**, sử dụng thay đổi portable khi có thể, cô lập khác biệt dialect, giữ kết quả schema tương đương và kiểm chứng từng DBMS trong CI/CD. Đây là nền tảng để quản lý thay đổi schema và dữ liệu có thể truy nguyên qua nhiều môi trường.

## 1. “Nhiều hệ quản trị” nghĩa là gì?

Trước hết cần phân biệt hai tình huống:

- **Nhiều database cùng một DBMS**: ví dụ development, staging và production đều dùng PostgreSQL. Phần lớn changelog có thể dùng chung; khác biệt chủ yếu nằm ở dữ liệu, cấu hình, quyền, phiên bản và trạng thái triển khai.
- **Nhiều DBMS khác nhau**: ví dụ cùng ứng dụng hỗ trợ PostgreSQL cho một khách hàng, SQL Server cho khách hàng khác và MySQL cho môi trường tích hợp. Khi đó cần xử lý khác biệt cú pháp, kiểu dữ liệu, tính năng và hành vi của database engine.

Bài này tập trung vào tình huống thứ hai. Một thiết kế tốt không nhất thiết làm mọi DBMS dùng cùng một câu SQL. Điều cần giữ thống nhất là **ý nghĩa của schema**: bảng nào tồn tại, cột có kiểu và ràng buộc gì, quan hệ dữ liệu ra sao, ứng dụng có thể dựa vào những hành vi nào.

Ví dụ cùng một hợp đồng nghiệp vụ:

~~~text
Bảng customer
- id: khóa chính, không NULL, tự sinh giá trị
- email: chuỗi tối đa 320 ký tự, có thể NULL
- created_at: thời điểm tạo bản ghi
- status: trạng thái nghiệp vụ, không NULL

Bảng sales_order
- id: khóa chính
- customer_id: tham chiếu customer.id
- amount: số thập phân có độ chính xác xác định
~~~

PostgreSQL, MySQL và SQL Server có thể biểu diễn một số chi tiết khác nhau, nhưng ứng dụng vẫn cần hiểu cùng ý nghĩa của các cột và quan hệ.

## 2. Ba chiến lược thiết kế changelog đa DBMS

Có ba chiến lược chính. Trong dự án thực tế thường kết hợp cả ba.

| Chiến lược | Cách làm | Khi phù hợp | Đánh đổi |
|---|---|---|---|
| **Portable changes** | Dùng change type và kiểu dữ liệu trừu tượng của Liquibase | DDL phổ biến, được hỗ trợ trên các DBMS mục tiêu | Không bao phủ hết tính năng đặc thù |
| **DBMS-specific changesets** | Tạo changeset riêng với thuộc tính **dbms** | Cùng mục đích nhưng DDL/khả năng khác nhau | Phải kiểm thử và duy trì nhiều nhánh |
| **SQL theo dialect** | Dùng sql/sqlFile hoặc extension riêng cho từng DBMS | Procedure, index đặc thù, JSON, partition, DDL đặc biệt | Tăng phụ thuộc vào DBMS và khó portable hơn |

Một nguyên tắc thực tế:

1. Bắt đầu bằng change type chung của Liquibase nếu nó biểu đạt chính xác yêu cầu.
2. Chỉ tách nhánh DBMS khi có khác biệt thực sự về tính năng hoặc SQL.
3. Giữ các nhánh riêng có **cùng kết quả schema và hợp đồng dữ liệu** nếu ứng dụng cần hỗ trợ các DBMS đó.
4. Cô lập SQL đặc thù trong changeset/file riêng để reviewer biết rõ phạm vi.
5. Kiểm thử trên từng DBMS thật sự được hỗ trợ, không suy ra từ một DBMS khác.

Không nên tạo các nhánh DBMS chỉ vì thói quen hoặc vì muốn thay tên cú pháp. Mỗi nhánh làm tăng số trường hợp cần kiểm thử và có thể khiến các môi trường lệch nhau theo thời gian.

## 3. Change type portable: để Liquibase sinh SQL theo DBMS

Các change type phổ biến như **createTable**, **addColumn**, **addPrimaryKey**, **addForeignKeyConstraint**, **createIndex**, **addNotNullConstraint** và **dropNotNullConstraint** giúp mô tả mục tiêu thay đổi ở mức cao hơn SQL cụ thể.

Ví dụ tạo bảng dùng chung:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "platform"
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
                  constraints:
                    nullable: true
              - column:
                  name: status
                  type: VARCHAR(24)
                  defaultValue: NEW
                  constraints:
                    nullable: false
~~~

Đây là một khai báo có tính portable tương đối cao, nhưng không có nghĩa mọi DBMS/version sẽ sinh DDL giống hệt nhau hoặc hỗ trợ mọi thuộc tính như nhau. Ví dụ **autoIncrement**, default, identity, kiểu chuỗi và cách đặt tên constraint có thể được ánh xạ khác nhau.

Liquibase đóng vai trò tạo SQL tương ứng với database đang kết nối. Cần xác minh bằng **update-sql** trên từng DBMS, sau đó thử thực thi. Nếu một change type không được hỗ trợ hoặc có hành vi khác với yêu cầu, hãy tách nhánh hoặc dùng SQL riêng thay vì giả định engine sẽ tự giải quyết mọi khác biệt.

### 3.1. Kiểu dữ liệu trừu tượng và kiểu cụ thể

Các kiểu như **BIGINT**, **VARCHAR(320)**, **DECIMAL(18,2)**, **DATE**, **TIMESTAMP**, **BOOLEAN**, **CLOB** hoặc **BLOB** giúp diễn đạt ý nghĩa dữ liệu. Liquibase và DBMS có thể ánh xạ chúng thành kiểu vật lý phù hợp.

Tuy nhiên, cần xem xét:

- **BOOLEAN**: một số DBMS có kiểu boolean riêng; nơi khác có thể dùng kiểu số hoặc cách biểu diễn khác.
- **TIMESTAMP**: khác biệt về timezone, độ chính xác phần giây và semantics giữa timestamp with/without time zone.
- **CLOB/BLOB**: cách lưu trữ, giới hạn kích thước và driver có thể khác nhau.
- **UUID**: DBMS có thể có kiểu native hoặc lưu dưới dạng chuỗi/nhị phân.
- **JSON**: PostgreSQL có JSON/JSONB; DBMS khác có thể hỗ trợ JSON theo kiểu hoặc cơ chế khác.
- **DECIMAL/NUMERIC**: cần giữ precision và scale nhất quán để tránh làm tròn hoặc overflow.

Không chọn kiểu chỉ vì tên giống nhau. Hãy xác định **hợp đồng dữ liệu mà ứng dụng cần**, rồi thử đọc/ghi và so sánh hành vi trên các DBMS mục tiêu.

### 3.2. Auto-increment, identity và sequence

Cơ chế sinh khóa khác nhau đáng kể: identity column, auto_increment, sequence kết hợp default hoặc cơ chế riêng. Thuộc tính **autoIncrement** của Liquibase có thể giúp biểu diễn mục tiêu chung cho nhiều DBMS, nhưng cần kiểm tra cách sinh SQL, start value, increment và khả năng tương thích với dữ liệu đã tồn tại.

Nếu cần kiểm soát sequence cụ thể, có thể dùng change type sequence tương ứng hoặc nhánh DBMS riêng. Không tạo một sequence thủ công song song với identity/auto-increment nếu không có thiết kế rõ, vì có thể gây trùng khóa hoặc sai lệch giá trị tiếp theo.

## 4. Thuộc tính dbms trên changeset

Khi một changeset chỉ áp dụng cho một hoặc một số DBMS, có thể dùng thuộc tính **dbms** ở cấp changeset.

Ví dụ PostgreSQL dùng kiểu JSONB:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010-add-customer-metadata-postgresql"
      author: "platform"
      dbms: postgresql
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: metadata
                  type: JSONB
~~~

Ví dụ SQL Server dùng kiểu JSON lưu trong NVARCHAR với kiểm tra JSON riêng nếu cần:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-011-add-customer-metadata-mssql"
      author: "platform"
      dbms: mssql
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: metadata
                  type: NVARCHAR(MAX)
~~~

Hai changeset diễn đạt cùng một mục tiêu ở mức ứng dụng nhưng có kiểu vật lý khác nhau. Nếu ứng dụng truy vấn metadata, tầng repository/DAO cũng phải xử lý sự khác biệt JSONB và NVARCHAR/JSON function tương ứng. Chỉ giữ cùng tên cột không đảm bảo API database giống nhau.

### 4.1. Nhiều giá trị dbms

Thuộc tính dbms có thể dùng để giới hạn một changeset cho nhiều DBMS theo cú pháp mà Liquibase hỗ trợ, ví dụ danh sách DBMS phân tách bằng dấu phẩy. Có thể dùng phủ định theo cú pháp dbms của phiên bản tương ứng, nhưng cần xác nhận chính xác cách diễn giải.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-020-create-common-audit"
      author: "platform"
      dbms: postgresql,mysql
      changes:
        - createTable:
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: event_name
                  type: VARCHAR(120)
                  constraints:
                    nullable: false
~~~

Nếu một DBMS không nằm trong điều kiện dbms, changeset đó không được thực thi trên DBMS ấy. Cần kiểm tra cách Liquibase ghi nhận/hiển thị changeset không áp dụng trong đúng phiên bản và không nhầm trạng thái **không phù hợp DBMS** với trạng thái **đã thực thi**.

**DBMS identifier phải đúng tên mà Liquibase nhận diện**, chẳng hạn postgresql, mysql, mariadb, mssql, oracle, db2 hoặc h2 tùy database implementation/version. Không tự suy từ tên sản phẩm hoặc JDBC URL. Xác nhận DBMS thực tế trong log/runtime và tài liệu phiên bản.

## 5. Cùng một mục đích, nhiều changeset theo DBMS

Khi một yêu cầu có cách triển khai khác nhau, hãy tạo các changeset riêng, có ID khác nhau và mỗi nhánh được giới hạn rõ.

Ví dụ cần tạo index theo điều kiện trên PostgreSQL, nhưng DBMS khác không có cùng khả năng hoặc syntax:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-030-index-customer-active-postgresql"
      author: "platform"
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX ix_customer_active_email
              ON customer (email)
              WHERE status = 'ACTIVE';

  - changeSet:
      id: "20261119-031-index-customer-active-mysql"
      author: "platform"
      dbms: mysql
      changes:
        - createIndex:
            tableName: customer
            indexName: ix_customer_email
            columns:
              - column:
                  name: email
~~~

Ở đây hai nhánh không tạo index vật lý giống nhau: PostgreSQL có partial index, còn MySQL ví dụ dùng index thường. Reviewer cần xác nhận **hợp đồng hiệu năng**: truy vấn có được hỗ trợ đủ tốt trên cả hai DBMS không, index thường có chi phí lưu trữ và ghi chấp nhận được không, và tên index có nhất quán cần thiết không.

Không đặt cùng ID/author cho hai changeset dialect khác nhau trong cùng file với giả định DBMS sẽ làm chúng trở thành cùng một changeset. Changeset identity và lịch sử phải được thiết kế rõ ràng. Các nhánh riêng nên có ID riêng, tên mô tả DBMS và cùng được kiểm thử trong ma trận DBMS.

### 5.1. Mỗi DBMS phải đạt cùng hợp đồng

Một bảng có thể có tên index khác nhau trên PostgreSQL và SQL Server nhưng ứng dụng không quan tâm tên index. Tuy nhiên, các thuộc tính như uniqueness, cột được index, thứ tự cột và hiệu quả truy vấn có thể ảnh hưởng trực tiếp đến hành vi hệ thống.

Khi review, hãy ghi rõ:

- Điều gì phải giống nhau giữa các DBMS?
- Điều gì được phép khác nhau về implementation?
- Khác biệt có làm thay đổi semantics dữ liệu không?
- Có cần migration dữ liệu riêng để đồng bộ không?
- Cần truy vấn/kiểm tra nào chứng minh mỗi nhánh đạt cùng mục tiêu?

## 6. modifySql: chỉnh SQL Liquibase sinh ra theo DBMS

Liquibase có cơ chế **modifySql** để điều chỉnh SQL được sinh từ một change type. Đây là một lựa chọn khi cấu trúc thay đổi vẫn chung nhưng cần biến đổi một phần câu SQL cho dialect cụ thể.

Ví dụ minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-040-create-customer-index"
      author: "platform"
      changes:
        - createIndex:
            tableName: customer
            indexName: ix_customer_status
            columns:
              - column:
                  name: status
      modifySql:
        - dbms: postgresql
          append:
            value: " USING btree"
~~~

Đoạn này chỉ minh họa vị trí và ý tưởng của modifySql; **không nên sao chép nguyên văn để chạy** nếu chưa xác nhận SQL mà Liquibase sinh ra và vị trí phần append có hợp lệ trong cú pháp CREATE INDEX của phiên bản/DBMS cụ thể. Một số dialect đã mặc định dùng B-tree; thêm đoạn này có thể thừa hoặc sai cú pháp tùy SQL được sinh.

Các thao tác modifySql thường gặp gồm:

- **append**: thêm phần văn bản vào SQL.
- **prepend**: thêm phần văn bản vào đầu SQL.
- **replace**: thay chuỗi cụ thể.
- **regExpReplace**: thay thế theo biểu thức chính quy.
- **dbms**: giới hạn thao tác sửa SQL cho DBMS tương ứng.

Nên dùng modifySql khi thay đổi nhỏ, có thể kiểm tra rõ trên SQL được sinh. Nếu phải thay toàn bộ cú pháp hoặc logic khác nhau đáng kể, một changeset dbms-specific hoặc SQL riêng thường dễ review hơn.

**modifySql không phải một bộ dịch SQL tổng quát.** Nó biến đổi chuỗi SQL đã sinh; không tự hiểu đầy đủ ngữ nghĩa, constraint, transaction hay dependency. Thay đổi chuỗi không chính xác có thể tạo SQL hợp lệ về mặt văn bản nhưng sai logic hoặc sai vị trí.

## 7. SQL riêng và sqlFile theo DBMS

Một số tính năng không có change type portable phù hợp, ví dụ:

- Partial/filtered index.
- Function, procedure, trigger hoặc package.
- Partitioning và storage option.
- JSON expression index.
- DDL đặc thù engine.
- Hành vi khóa hoặc online DDL riêng.

Khi đó có thể dùng **sql** hoặc **sqlFile** trong changeset giới hạn bởi dbms.

Ví dụ dùng SQL riêng cho PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-050-create-customer-json-index-postgresql"
      author: "platform"
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX ix_customer_metadata_type
              ON customer ((metadata ->> 'type'));
      rollback:
        - sql:
            sql: |
              DROP INDEX IF EXISTS ix_customer_metadata_type;
~~~

Ví dụ này chỉ áp dụng PostgreSQL vì toán tử **->>** và expression index là cú pháp đặc thù. Nếu database khác cần một chỉ mục tương đương, phải thiết kế nhánh riêng với chức năng được hỗ trợ. Câu SQL rollback cũng cần kiểm tra quyền, schema và tính khả dụng của IF EXISTS trên phiên bản mục tiêu.

### 7.1. sqlFile

Có thể lưu SQL trong file riêng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-051-create-customer-function-postgresql"
      author: "platform"
      dbms: postgresql
      changes:
        - sqlFile:
            path: sql/postgresql/create_customer_function.sql
            relativeToChangelogFile: true
            splitStatements: false
            stripComments: false
      rollback:
        - sqlFile:
            path: sql/postgresql/drop_customer_function.sql
            relativeToChangelogFile: true
            splitStatements: false
            stripComments: false
~~~

Các tùy chọn **splitStatements**, **stripComments**, **endDelimiter** và cách thực thi phải phù hợp file SQL, đặc biệt với function/procedure chứa nhiều dấu chấm phẩy. Tùy chọn cụ thể và hành vi executor phụ thuộc loại DBMS, driver và phiên bản Liquibase. Kiểm tra file thực tế cùng SQL preview; không mặc định splitStatements=false hoặc true là đúng cho mọi script.

### 7.2. Không dùng một file SQL cho nhiều dialect nếu cú pháp khác nhau

Cách tổ chức rõ:

~~~text
db/changelog/
├── db.changelog-master.yaml
├── common/
│   └── customer-table.yaml
└── sql/
    ├── postgresql/
    │   ├── create_customer_function.sql
    │   └── drop_customer_function.sql
    ├── mssql/
    │   ├── create_customer_function.sql
    │   └── drop_customer_function.sql
    └── mysql/
        ├── create_customer_trigger.sql
        └── drop_customer_trigger.sql
~~~

Một file SQL được viết theo PostgreSQL không nên được tham chiếu bởi changeset chạy trên SQL Server. Cần gắn dbms cho changeset và lưu file theo dialect để tránh nhầm lẫn.

## 8. Precondition: bảo vệ điều kiện theo DBMS và schema

**dbms** ở cấp changeset giới hạn nền tảng được phép áp dụng. **Precondition dbms** là một cách kiểm tra điều kiện database trong cây precondition. Cả hai có vai trò khác nhau về mặt cấu hình và cần dùng đúng cú pháp.

Ví dụ precondition:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-060-add-postgresql-feature"
      author: "platform"
      preConditions:
        - onFail: HALT
        - dbms:
            type: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX ix_customer_status
              ON customer (status);
~~~

Precondition giúp dừng nếu DBMS không phù hợp theo điều kiện kiểm tra. Tuy nhiên, khi một changeset chỉ có thể chạy trên PostgreSQL, **dbms attribute** ở cấp changeset thường thể hiện ý định phạm vi trực tiếp và dễ review hơn. Không nên chỉ dùng precondition để che một changeset chứa SQL không portable mà không giải thích rõ.

Có thể kết hợp với precondition khác:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-061-add-customer-region-postgresql"
      author: "platform"
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
        - not:
            columnExists:
              tableName: customer
              columnName: region
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: region
                  type: VARCHAR(40)
~~~

Ví dụ kiểm tra bảng tồn tại và cột chưa có trước khi thêm. Precondition không thay thế việc kiểm tra schema giữa các DBMS; nó chỉ kiểm tra điều kiện cụ thể được khai báo. Nếu dùng **MARK_RAN**, cần chắc chắn trạng thái đích đã tồn tại và được xác minh; nếu không, lịch sử có thể ghi nhận changeset mà schema vẫn thiếu.

## 9. Tách changelog chung và changelog riêng theo DBMS

Khi dự án lớn, để mọi changeset trong một file duy nhất có thể khó review. Có thể tách theo trách nhiệm:

~~~text
db/changelog/
├── db.changelog-master.yaml
├── common/
│   ├── 001-create-customer.yaml
│   ├── 002-create-sales-order.yaml
│   └── 003-add-customer-status.yaml
└── dbms/
    ├── postgresql/
    │   ├── 101-customer-json-index.yaml
    │   └── 102-customer-function.yaml
    ├── mssql/
    │   ├── 201-customer-json-index.yaml
    │   └── 202-customer-function.yaml
    └── mysql/
        └── 301-customer-trigger.yaml
~~~

Master changelog có thể include các file chung và file dialect:

~~~yaml
databaseChangeLog:
  - include:
      file: common/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: common/002-create-sales-order.yaml
      relativeToChangelogFile: true
  - include:
      file: common/003-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: dbms/postgresql/101-customer-json-index.yaml
      relativeToChangelogFile: true
  - include:
      file: dbms/mssql/201-customer-json-index.yaml
      relativeToChangelogFile: true
  - include:
      file: dbms/mysql/301-customer-trigger.yaml
      relativeToChangelogFile: true
~~~

Trong ví dụ, từng file DBMS phải chứa changeset có **dbms** phù hợp. Việc include file không tự giới hạn DBMS; nếu không có điều kiện, changeset bên trong vẫn có thể được parser xem xét. Không nên nghĩ rằng thư mục tên **postgresql** tự khiến Liquibase chỉ chạy file đó trên PostgreSQL.

Một phương án khác là dùng includeAll theo thư mục dialect, nhưng thứ tự file và cách include cần được kiểm soát theo phiên bản, quy ước đặt tên và cấu hình. Với migration quan trọng, include tường minh thường dễ review thứ tự hơn.

### 9.1. Lưu ý định danh changeset khi tách file

Filename tham gia vào định danh changeset. Di chuyển file sau khi đã triển khai có thể khiến Liquibase nhận diện một changeset như một thay đổi khác nếu không quản lý **logicalFilePath** có chủ đích. Do đó:

- Chọn cấu trúc thư mục trước khi phát hành baseline.
- Giữ đường dẫn ổn định.
- Nếu cần di chuyển, lập kế hoạch bảo toàn logical path và kiểm tra trên bản sao database có lịch sử.
- Không đổi ID/author/filename tùy tiện để “làm sạch” repository sau khi đã triển khai.

## 10. Khác biệt ở khóa ngoại, index và constraint

Các change type constraint phổ biến có thể dùng chung, nhưng khả năng và hành vi DBMS vẫn cần kiểm chứng.

### 10.1. Foreign key

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-070-fk-sales-order-customer"
      author: "platform"
      changes:
        - addForeignKeyConstraint:
            baseTableName: sales_order
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_sales_order_customer
            onDelete: RESTRICT
~~~

Các DBMS có thể dùng từ khóa hoặc semantics khác nhau cho hành vi khi xóa/cập nhật. **RESTRICT**, **NO ACTION**, **CASCADE**, **SET NULL** không nên coi là các nhãn có thể hoán đổi trong mọi engine. Hãy xác nhận hành vi khi có transaction và dữ liệu thực tế.

### 10.2. Index

Index thông thường có thể dùng **createIndex**, nhưng những thuộc tính như partial/filtered index, included columns, expression index, operator class, clustering hoặc online/concurrent build có thể đặc thù DBMS.

Không nên tạo một index “có tên giống nhau” rồi kết luận tương đương. Hãy kiểm tra cột, thứ tự, uniqueness, predicate, expression và tác động lên truy vấn.

### 10.3. Constraint name

Một số DBMS tự sinh tên constraint nếu không chỉ định; quy tắc đặt tên và giới hạn độ dài khác nhau. Nên đặt tên rõ ràng, ổn định nếu change type hỗ trợ, đồng thời bảo đảm không vượt giới hạn của DBMS mục tiêu.

Tên constraint cũng quan trọng cho rollback: drop constraint thường cần đúng tên và bảng. Nếu snapshot từ database legacy có tên tự sinh khác nhau giữa môi trường, cần chuẩn hóa có kiểm soát hoặc mô tả sự khác biệt, không giả định tên giống nhau.

## 11. Dữ liệu và biểu thức default có thể khác theo DBMS

Schema đa DBMS không chỉ là DDL. Các biểu thức như **CURRENT_TIMESTAMP**, sequence, UUID generator, JSON extraction hoặc hàm chuỗi có thể có syntax/semantics khác nhau.

Ví dụ, default thời gian:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-080-event-created-at-postgresql"
      author: "platform"
      dbms: postgresql
      changes:
        - addDefaultValue:
            tableName: event_log
            columnName: created_at
            columnDataType: TIMESTAMP WITH TIME ZONE
            defaultValueComputed: CURRENT_TIMESTAMP
~~~

Đây là ví dụ cho PostgreSQL; kiểu timestamp và biểu thức phải được đối chiếu với hợp đồng dữ liệu của ứng dụng. DBMS khác có thể cần kiểu hoặc biểu thức riêng. Không giả định cùng một tên hàm có cùng timezone, precision và thời điểm đánh giá.

Với UUID, có thể dùng kiểu native và function generator riêng theo DBMS hoặc để ứng dụng sinh UUID. Chọn một chiến lược nhất quán: nếu database sinh khóa, tất cả DBMS mục tiêu cần có cơ chế tương đương; nếu ứng dụng sinh khóa, migration phải tạo kiểu cột phù hợp để lưu giá trị.

Dữ liệu reference cũng cần được xử lý theo quy tắc chung. Không nên để mỗi DBMS có bộ mã trạng thái khác nhau chỉ vì changeset seed data bị phân nhánh sai.

## 12. Transaction và DDL: không có giả định chung cho mọi engine

Một changeset thường được Liquibase thực thi trong transaction khi database hỗ trợ. Tuy nhiên, DDL transactional và implicit commit khác nhau giữa DBMS. Điều này ảnh hưởng:

- Nếu một changeset có nhiều DDL và lỗi giữa chừng, trạng thái có thể khác nhau.
- Rollback có thể không đảo được DDL đã commit ngầm.
- Lock của ALTER TABLE/CREATE INDEX có thể gây gián đoạn.
- Online/concurrent index build có thể có quy tắc riêng, không nằm trong transaction thông thường.
- Một SQL procedure hoặc trigger có thể yêu cầu delimiter/executor đặc biệt.

Không nên gom nhiều thay đổi rủi ro cao vào một changeset chỉ vì muốn chúng “nguyên tử”. Hãy tìm hiểu DBMS có hỗ trợ transaction cho loại DDL đó không. Nếu cần tách bước, tạo changeset có mục đích đơn nhất, precondition phù hợp và phương án phục hồi.

Thuộc tính **runInTransaction** có thể điều khiển việc Liquibase cố chạy changeset trong transaction theo khả năng hỗ trợ. Tắt transaction không phải giải pháp chung cho DDL đa DBMS; cần biết chính xác vì sao phải tắt và cách xử lý khi lệnh thất bại giữa chừng.

## 13. Rollback đa DBMS phải được kiểm tra theo từng nhánh

Cùng một mục tiêu schema có thể có cách rollback khác nhau. Ví dụ:

- PostgreSQL tạo partial index; rollback cần drop đúng index/schema.
- SQL Server tạo filtered index hoặc constraint với tên cụ thể.
- Oracle dùng sequence/default theo cách riêng.
- MySQL tạo trigger với body và delimiter riêng.

Nếu mỗi DBMS dùng changeset riêng, rollback tương ứng cũng phải nằm trong nhánh đó hoặc được khai báo theo change type có hỗ trợ.

Ví dụ SQL riêng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-090-create-pg-index"
      author: "platform"
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX ix_customer_active
              ON customer (email)
              WHERE status = 'ACTIVE';
      rollback:
        - sql:
            sql: DROP INDEX IF EXISTS ix_customer_active;

  - changeSet:
      id: "20261119-091-create-mysql-index"
      author: "platform"
      dbms: mysql
      changes:
        - createIndex:
            tableName: customer
            indexName: ix_customer_email
            columns:
              - column:
                  name: email
      rollback:
        - dropIndex:
            tableName: customer
            indexName: ix_customer_email
~~~

Ví dụ cho thấy rollback riêng theo DBMS. Tên object, schema qualification và cú pháp IF EXISTS cần kiểm tra theo phiên bản thực tế. Không thể suy ra rollback của một nhánh sẽ đúng cho nhánh kia.

**Rollback thành công về mặt DDL chưa chắc khôi phục dữ liệu**. Nếu changeset chuyển đổi dữ liệu, xóa cột hoặc thay đổi default, cần đánh giá khả năng phục hồi riêng. Với migration đa DBMS, kiểm thử rollback trên từng engine và version là bắt buộc nếu tổ chức cam kết hỗ trợ rollback.

## 14. Precondition và dbms không thay thế nhau

Hai cơ chế thường được dùng cùng lúc nhưng phục vụ mục đích khác:

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| **dbms trên changeset** | Chỉ định changeset áp dụng cho DBMS nào | SQL JSONB chỉ chạy trên PostgreSQL |
| **precondition dbms** | Kiểm tra database đang kết nối có DBMS mong muốn | HALT nếu môi trường không phải PostgreSQL |
| **tableExists/columnExists** | Kiểm tra đối tượng cần thiết tồn tại | Chặn addColumn nếu bảng không có |
| **sqlCheck** | Kiểm tra một điều kiện bằng SQL | Chỉ thêm NOT NULL khi không còn hàng NULL |

Nếu một changeset chứa SQL PostgreSQL, gắn dbms=postgresql để thể hiện rõ phạm vi. Precondition dbms có thể bổ sung kiểm tra bảo vệ, nhưng không nên chỉ dựa vào nó khi changeset có thể bị gọi ở runtime khác.

Cẩn trọng với **onFail: MARK_RAN**. Nếu DBMS không phù hợp hoặc object chưa đúng mà changeset bị đánh dấu ran, lịch sử có thể không phản ánh schema thực. Với điều kiện bắt buộc để migration an toàn, **HALT** thường phù hợp hơn.

## 15. Cấu hình CI/CD theo ma trận DBMS

Nếu ứng dụng hỗ trợ PostgreSQL, MySQL và SQL Server, pipeline nên chạy validation/test trên cả ba, thay vì chỉ một database đại diện.

Ví dụ ma trận khái niệm:

| Job | DBMS | Mục tiêu |
|---|---|---|
| liquibase-postgresql | PostgreSQL phiên bản mục tiêu | Validate, update-sql, update, rollback test |
| liquibase-mysql | MySQL phiên bản mục tiêu | Xác minh mapping type, DDL, FK và index |
| liquibase-mssql | SQL Server phiên bản mục tiêu | Kiểm tra identity, constraint, index và SQL riêng |
| schema-contract | Tất cả | So sánh các invariant schema và kiểm thử ứng dụng |

Một pipeline có thể thực hiện:

1. Lấy changelog từ cùng một commit/artifact.
2. Khởi tạo database thử nghiệm đúng DBMS/version.
3. Chạy **validate** bằng đúng Liquibase runtime.
4. Xem **update-sql** cho từng DBMS.
5. Chạy **update** trên database mới.
6. Kiểm tra schema/catalog, constraint, index và hành vi dữ liệu.
7. Chạy kiểm thử ứng dụng hoặc repository integration tests trên từng DBMS.
8. Thử rollback nếu đó là yêu cầu release.
9. Lưu log, SQL sinh ra, phiên bản Liquibase/driver/DBMS và kết quả.

Một ví dụ cấu hình pipeline giả định:

~~~text
matrix:
  database:
    - postgresql
    - mysql
    - mssql

for each database:
    provision database
    configure JDBC URL and driver
    liquibase validate
    liquibase update-sql
    liquibase update
    verify schema contract
    run integration tests
    test rollback on disposable database
~~~

Đây là sơ đồ quy trình, không phải cú pháp YAML hoàn chỉnh của một nền tảng CI cụ thể. Phải chuyển thành cấu hình phù hợp với GitHub Actions, GitLab CI, Jenkins hoặc hệ thống của tổ chức.

### 15.1. Dùng database container để kiểm thử

Có thể dùng container/test service tương ứng với DBMS, nhưng cần dùng **phiên bản gần môi trường triển khai**. H2 hoặc một database giả lập khác có thể tiện cho unit test nhưng không thay thế kiểm thử DDL thực tế trên PostgreSQL/MySQL/SQL Server.

Không cần chạy toàn bộ ma trận cho mọi commit nếu chi phí quá cao, nhưng các nhánh DBMS phải có cửa kiểm tra bắt buộc trước release. Có thể chạy smoke test nhanh theo commit và test đầy đủ theo lịch hoặc trước phát hành.

## 16. Tích hợp Spring Boot khi hỗ trợ nhiều DBMS

Spring Boot thường cấu hình Liquibase qua datasource và changelog:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Khi cùng một artifact ứng dụng được triển khai với các DBMS khác nhau, cần đảm bảo:

- JDBC driver đúng DBMS được đóng gói/cấp trong runtime.
- DataSource kết nối đúng database và schema.
- Liquibase version hỗ trợ change type và cú pháp changelog.
- Master changelog chứa các nhánh common và DBMS-specific cần thiết.
- Những thay đổi không tương thích được bảo vệ bằng dbms/precondition.
- Cấu hình context/label không vô tình làm khác tập changeset giữa môi trường.

Không nên dựa vào việc Spring profile tên **postgres** hoặc **mysql** để Liquibase tự động suy luận mọi nhánh nếu không có cấu hình rõ. Liquibase nhận diện DBMS từ database connection/runtime; profile của ứng dụng chỉ có tác dụng khi được ánh xạ vào cấu hình một cách chủ đích.

Nếu ứng dụng chạy nhiều instance cùng lúc, cơ chế lock của Liquibase hỗ trợ điều phối việc update, nhưng không giải quyết schema drift hoặc SQL không tương thích. Một migration job chuyên trách trong pipeline có thể giúp kiểm soát tốt hơn việc chạy một changelog trên từng DBMS.

## 17. Kiểm soát khác biệt phiên bản DBMS

Cùng một DBMS nhưng phiên bản khác nhau cũng có thể hỗ trợ tính năng khác nhau. Ví dụ một phiên bản mới có thể hỗ trợ JSON function, online DDL hoặc kiểu dữ liệu mà phiên bản cũ chưa có.

Không nên chỉ gắn **dbms: postgresql** rồi giả định mọi phiên bản PostgreSQL đều tương đương. Có thể cần:

- Quy định phiên bản DBMS tối thiểu được hỗ trợ.
- Kiểm tra phiên bản server trong pipeline/precondition hoặc hệ thống deployment.
- Tách nhánh changeset khi khác biệt thực sự cần thiết.
- Chọn cú pháp tương thích với phiên bản thấp nhất trong phạm vi hỗ trợ.
- Nâng cấp database theo kế hoạch riêng nếu feature mới là bắt buộc.

Một changelog có thể chạy trên DBMS A version mới nhưng thất bại ở version cũ. Hãy ghi nhận **ma trận hỗ trợ thực tế** thay vì dùng tên sản phẩm chung.

## 18. Checksum, lịch sử và thay đổi nhánh DBMS

Liquibase ghi nhận changeset trong **DATABASECHANGELOG** theo định danh ID, author và filename/logicalFilePath. Những changeset đã triển khai không nên bị chỉnh sửa tùy tiện.

Một số lỗi thường gặp trong changelog đa DBMS:

- Thêm nhánh DBMS vào trước changeset đã phát hành, làm thay đổi thứ tự hoặc định danh.
- Đổi tên file DBMS-specific khiến filename thay đổi.
- Sửa SQL của changeset đã chạy để hỗ trợ thêm một DBMS.
- Dùng cùng ID/author cho những thay đổi khác nhau trong các file khác nhau.
- Đổi dbms filter của changeset đã chạy và kỳ vọng lịch sử tự đồng bộ giữa môi trường.
- Dùng **clear-checksums** để bỏ qua sai khác mà chưa điều tra.

Cách xử lý thông thường là **giữ nguyên changeset đã triển khai và thêm changeset mới**. Nếu phát hiện một DBMS thiếu thay đổi vì nhánh cũ không được áp dụng, hãy thêm changeset bổ sung dành cho DBMS đó, có ID mới, điều kiện rõ ràng và kiểm chứng schema cuối. Không chỉnh lịch sử để giả vờ rằng mọi DBMS đã chạy cùng một migration.

Với các changeset dbms-specific, mỗi DBMS có thể có tập changeset đã áp dụng khác nhau nhưng vẫn phải đạt cùng hợp đồng schema. Vì vậy, không so sánh chỉ số lượng dòng DATABASECHANGELOG giữa các DBMS; hãy so sánh **đối tượng và invariant thực tế**.

## 19. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Changelog chạy trên PostgreSQL nhưng lỗi MySQL | Có SQL/kiểu dữ liệu đặc thù không được tách nhánh | Dùng change type portable hoặc dbms-specific changeset |
| Changeset không chạy trên một DBMS | dbms filter không khớp tên DBMS nhận diện | Xác minh runtime DBMS và giá trị dbms |
| Hai DBMS có schema khác nhau | Một nhánh thiếu change, precondition MARK_RAN hoặc logic dialect khác | So sánh schema contract và lịch sử từng môi trường |
| SQL preview khác kỳ vọng | Liquibase mapping/modifySql/dialect tạo câu lệnh khác | Review SQL sinh trên đúng DBMS/version |
| Chạy được trên H2 nhưng lỗi production | H2 không mô phỏng đầy đủ dialect/DDL production | Kiểm thử trên DBMS thật hoặc container đúng version |
| Index/constraint có tên khác | Quy tắc đặt tên hoặc giới hạn DBMS | Đặt tên tường minh và kiểm tra catalog |
| Default thời gian sai timezone | Semantics timestamp/function khác nhau | Chọn hợp đồng timezone và kiểm thử từng engine |
| SQL procedure bị tách sai | splitStatements/delimiter không phù hợp | Dùng sqlFile và cấu hình executor/delimiter đúng |
| Rollback thất bại trên một DBMS | SQL đảo hoặc transaction/DDL semantics khác | Viết rollback riêng và thử từng engine |
| Checksum mismatch sau khi thêm nhánh | Sửa changeset đã chạy hoặc đổi filename | Giữ nguyên lịch sử, thêm changeset mới |
| Changelog có quá nhiều điều kiện | Thiết kế phân nhánh không có quy ước | Tách common/dialect và ghi rõ invariant |
| Cùng artifact nhưng chạy sai DB | Sai JDBC URL/driver hoặc cấu hình profile | Log DBMS/version đã nhận diện, kiểm tra secret/config |

## 20. Bài thực hành: một schema chạy trên PostgreSQL và MySQL

**Bài toán:** Ứng dụng quản lý khách hàng hỗ trợ PostgreSQL và MySQL. Cần bảng customer với ID tự sinh, email, status, created_at và index phục vụ truy vấn khách hàng đang hoạt động.

### Bước 1 — Định nghĩa hợp đồng chung

Viết rõ:

- id là khóa chính, tự sinh, không NULL.
- email là chuỗi có giới hạn độ dài đã thống nhất.
- status là chuỗi trạng thái, không NULL, có giá trị mặc định nghiệp vụ nếu phù hợp.
- created_at biểu diễn thời điểm tạo, quy ước timezone rõ.
- Truy vấn lọc status phải có hiệu năng phù hợp.

### Bước 2 — Dùng change type chung cho bảng

Dùng **createTable** và kiểu dữ liệu trừu tượng phù hợp. Xem update-sql trên cả PostgreSQL và MySQL để so sánh identity, default, timestamp và kiểu cột.

### Bước 3 — Thiết kế index

Nếu PostgreSQL dùng partial index còn MySQL dùng index thường, tạo hai changeset dbms-specific riêng. Xác nhận truy vấn mục tiêu có kế hoạch thực thi phù hợp trên cả hai.

### Bước 4 — Thử migration

- Tạo database PostgreSQL đúng version mục tiêu.
- Tạo database MySQL đúng version mục tiêu.
- Chạy validate/update-sql/update cho từng DB.
- Kiểm tra schema, index, default, nullability và primary key.
- Chạy cùng integration test qua repository/service trên hai DBMS.

### Bước 5 — Kiểm tra dữ liệu và rollback

- Insert customer không truyền status nếu default được kỳ vọng.
- Thử status hợp lệ/không hợp lệ theo validation của ứng dụng.
- Kiểm tra timestamp và timezone.
- Thử rollback index và bảng trên database tạm.
- Đối chiếu kết quả schema sau rollback.

### Bước 6 — Ghi ma trận tương thích

Ghi lại phiên bản Liquibase, DBMS, driver, feature và kết quả. Nếu một DBMS cần nhánh riêng hoặc chưa hỗ trợ, ghi rõ giới hạn thay vì tuyên bố chung “changelog portable”.

## 21. Checklist review changelog đa DBMS

Trước khi merge hoặc phát hành:

- Đã xác định danh sách DBMS và phiên bản server thực sự được hỗ trợ?
- Đã định nghĩa hợp đồng schema chung, kiểu dữ liệu, timezone, identity và semantics default?
- Đã ưu tiên change type portable khi phù hợp?
- Những changeset chứa SQL đặc thù có dbms filter rõ ràng?
- DBMS identifier đúng với giá trị Liquibase nhận diện?
- Các nhánh riêng có ID riêng và cùng đạt invariant schema?
- modifySql chỉ dùng khi biến đổi nhỏ, có thể kiểm tra SQL trước/sau?
- sqlFile có delimiter/splitStatements/executor phù hợp?
- Precondition dùng đúng mục đích và không MARK_RAN để che schema thiếu?
- Master changelog include đúng file; thứ tự include ổn định?
- logicalFilePath/filename và định danh changeset được giữ ổn định?
- SQL preview đã được review trên từng DBMS/version?
- Migration và rollback đã được thử trên từng DBMS mục tiêu?
- Đã kiểm tra transaction, lock, index, constraint và DDL đặc thù?
- CI/CD có ma trận kiểm tra cho tất cả DBMS được hỗ trợ?
- Spring Boot runtime có driver, datasource và Liquibase version đúng?
- DATABASECHANGELOG và checksum được đối chiếu mà không sửa lịch sử cũ?
- Có tài liệu rõ về DBMS/version chưa hỗ trợ hoặc feature chỉ khả dụng trên một dialect?

**Kết luận:** Thiết kế changelog cho nhiều hệ quản trị bắt đầu từ **một hợp đồng schema chung**, sau đó lựa chọn đúng mức trừu tượng. Dùng change type portable cho phần phổ biến, giới hạn changeset bằng **dbms** khi cần dialect riêng, và chỉ dùng SQL/modifySql đặc thù khi có lý do rõ ràng. Mỗi nhánh phải được kiểm thử trên DBMS/version mục tiêu, đạt cùng invariant dữ liệu và có rollback phù hợp. Kết hợp cách tổ chức changelog ổn định với ma trận CI/CD, precondition, checksum và kiểm tra DATABASECHANGELOG sẽ giúp Liquibase quản lý nhiều hệ quản trị có thể truy nguyên mà vẫn giữ hành vi ứng dụng nhất quán.

