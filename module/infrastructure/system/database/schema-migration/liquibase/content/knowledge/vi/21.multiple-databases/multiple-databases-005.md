# Quản lý nhiều schema và catalog trong một ứng dụng

## 1. Bài toán nhiều schema và catalog

Một ứng dụng doanh nghiệp có thể làm việc với nhiều schema trong cùng database, hoặc kết nối tới nhiều database/catalog khác nhau. Ví dụ, hệ thống bán hàng có schema sales chứa đơn hàng, schema crm chứa khách hàng, schema audit lưu lịch sử; một ứng dụng tích hợp có thể đồng thời kết nối tới catalog billing và catalog reporting. Ở môi trường multi-tenant, mỗi khách hàng còn có thể được cấp một schema riêng hoặc một database riêng.

Những mô hình này trông giống nhau ở góc nhìn ứng dụng, nhưng khác nhau về kết nối, quyền, lịch sử migration và khả năng giao dịch. Nếu chỉ thay tên schema trong changelog mà không xác định phạm vi của DATABASECHANGELOG, một changeset có thể chỉ chạy cho tenant đầu tiên rồi bị Liquibase bỏ qua ở các tenant còn lại. Nếu dùng nhầm datasource, migration có thể tác động lên database khác với database mà service đang phục vụ.

Bài học thuộc chương **Nhiều cơ sở dữ liệu** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng dẫn quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trọng tâm của bài là tổ chức nhiều schema/catalog trong một ứng dụng sao cho mỗi thay đổi có đúng đích, đúng lịch sử và đúng thứ tự phụ thuộc.

Sau bài học, người đọc có thể:

1. Phân biệt database/catalog với schema và hiểu sự khác nhau giữa các DBMS.
2. Chọn mô hình Liquibase cho nhiều schema trong một database hoặc nhiều catalog/database.
3. Cấu hình default schema/catalog và chỉ định schema/catalog ở từng change.
4. Thiết kế phạm vi DATABASECHANGELOG và DATABASECHANGELOGLOCK phù hợp với đơn vị triển khai.
5. Quản lý schema-per-tenant, datasource riêng và nhiều Liquibase instance.
6. Kiểm soát dependency, quyền, rollback, thứ tự triển khai và kiểm thử trên từng đích.

## 2. Phân biệt database, catalog và schema

Các thuật ngữ catalog và schema không có cùng ý nghĩa vật lý trên mọi hệ quản trị. Cần xác định mô hình của DBMS đang dùng thay vì suy luận từ tên tham số Liquibase.

| Khái niệm | Ý nghĩa tổng quát | Ví dụ |
|---|---|---|
| Database | Đơn vị database được kết nối hoặc quản trị độc lập theo DBMS | appdb, billingdb |
| Catalog | Không gian chứa/định danh các đối tượng database theo cách DBMS biểu diễn | Một số DBMS dùng catalog tương ứng database |
| Schema | Namespace nhóm bảng, view, sequence, function và các object khác | sales, crm, audit |
| Object | Thành phần cụ thể trong namespace | sales.orders, crm.customer |

### 2.1. Cách hiểu theo DBMS

| DBMS | Cách tổ chức thường gặp | Lưu ý khi triển khai |
|---|---|---|
| PostgreSQL | Một kết nối làm việc với một database; bên trong database có nhiều schema | Không thể chuyển sang database khác chỉ bằng schemaName; schema là namespace trong database |
| SQL Server | Một server có nhiều database; mỗi database có nhiều schema | Có thể có tên ba phần database.schema.object trong một số truy vấn, nhưng quyền và DDL cross-database có quy tắc riêng |
| MySQL | Thuật ngữ database và schema thường được dùng gần như đồng nghĩa | Tên database thường đóng vai trò namespace; không áp dụng nguyên mô hình PostgreSQL |
| Oracle | Schema gắn với user/owner trong database | Schema thường được quản lý như namespace của owner; quyền và synonym có vai trò quan trọng |

Trong Liquibase, các thuộc tính defaultCatalogName, defaultSchemaName, catalogName và schemaName giúp xác định nơi object được tạo hoặc tìm kiếm. Tuy nhiên, catalogName không phải cách portable để đổi JDBC connection sang một database độc lập. Nếu cần quản lý một database khác, thông thường phải dùng kết nối và Liquibase instance phù hợp với database đó.

### 2.2. Ba mô hình kiến trúc phổ biến

**Mô hình A — nhiều schema, một database:** một ứng dụng kết nối một database và quản lý các namespace như sales, crm, audit. Một Liquibase instance có thể quản lý nhiều schema nếu quyền và DBMS cho phép; từng change cần xác định đúng schema.

**Mô hình B — nhiều catalog/database:** một ứng dụng có nhiều datasource, mỗi datasource kết nối tới một database. Thường cần một Liquibase instance và lịch sử migration riêng cho từng database.

**Mô hình C — schema-per-tenant hoặc database-per-tenant:** ứng dụng dùng chung code nhưng triển khai cùng changelog cho nhiều tenant. Mỗi tenant cần một chiến lược lịch sử, khóa, tham số và tiến độ riêng để migration không bị bỏ qua hoặc chạy nhầm.

Không nên gộp ba mô hình thành một cấu hình duy nhất. Chúng khác nhau về ranh giới kết nối, khả năng transaction, quyền và đơn vị rollback.

## 3. Chọn một đơn vị quản lý migration

Trước khi viết changelog, hãy trả lời: một lần update Liquibase chịu trách nhiệm đưa trạng thái nào tới phiên bản mong muốn?

| Đơn vị migration | Mô hình phù hợp | Câu hỏi quản trị |
|---|---|---|
| Toàn database | Nhiều schema có cùng vòng đời và phát hành đồng bộ | Một lịch sử có đại diện được tất cả object không? |
| Từng schema | Schema độc lập hoặc tenant có thể nâng cấp riêng | Lịch sử và lock table có tách theo schema không? |
| Từng catalog/database | Database có datasource, quyền và lịch phát hành riêng | Có Liquibase instance và artifact/config riêng cho mỗi database không? |
| Một nhóm schema liên kết | Một service quản lý vài schema có dependency chung | Thứ tự và tính nhất quán giữa các schema được điều phối ra sao? |

Một đơn vị migration cần có:

- Một đích kết nối được xác định rõ.
- Một phạm vi schema/catalog được quản lý.
- Một lịch sử changeset có thể giải thích.
- Một cơ chế khóa và điều phối phù hợp.
- Một tập tham số và quyền tối thiểu.
- Một quy trình rollback/forward fix được thử nghiệm.

Nếu không xác định đơn vị này, nhóm có thể tạo một changeset nhưng không biết nó đã chạy cho schema nào, hoặc một pipeline báo thành công trong khi một số tenant chưa được nâng cấp.

## 4. Quản lý nhiều schema trong cùng một database

Khi nhiều schema nằm trong cùng database và một Liquibase connection có quyền truy cập, có thể quản lý chúng trong cùng changelog. Cần dùng schemaName tường minh cho các object không thuộc schema mặc định.

Ví dụ YAML tạo hai bảng ở hai schema:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-sales-order
      author: platform
      changes:
        - createTable:
            schemaName: sales
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_id
                  type: bigint

  - changeSet:
      id: 002-create-crm-customer
      author: platform
      changes:
        - createTable:
            schemaName: crm
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: display_name
                  type: varchar(200)
~~~

Ví dụ giả định cả hai schema đã tồn tại, user migration có quyền tạo bảng và DBMS hỗ trợ mô hình này. Nếu schema chưa có, hãy tạo schema bằng change type phù hợp hoặc provisioning riêng trước khi tạo table.

### 4.1. Chỉ định schema cho mọi change cần thiết

Đừng chỉ thêm schemaName ở createTable rồi bỏ quên các changeset sau. Những change type như addColumn, createIndex, addForeignKeyConstraint, dropTable hoặc sql có thể cần schema tương ứng. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-add-order-index
      author: platform
      changes:
        - createIndex:
            schemaName: sales
            tableName: orders
            indexName: idx_orders_customer
            columns:
              - column:
                  name: customer_id
~~~

Đối với FK xuyên schema trong cùng database, có thể khai báo schema phía bảng con và schema phía bảng được tham chiếu nếu DBMS hỗ trợ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-add-sales-crm-foreign-key
      author: platform
      changes:
        - addForeignKeyConstraint:
            baseTableSchemaName: sales
            baseTableName: orders
            baseColumnNames: customer_id
            referencedTableSchemaName: crm
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_orders_customer
~~~

Đây là ví dụ cho hai schema cùng một database và có kiểu khóa tương thích. Khả năng tham chiếu xuyên schema, quyền và cú pháp phụ thuộc DBMS. Không suy rằng cùng khai báo schemaName thì FK có thể tham chiếu qua một database/catalog độc lập.

### 4.2. defaultSchemaName chỉ là mặc định

defaultSchemaName xác định schema mặc định mà Liquibase sử dụng khi change không chỉ rõ schema. Nó không có nghĩa mọi object trong changelog tự động thuộc schema đó nếu đã khai báo schema khác; cũng không thay thế việc xác minh schema thực tế của kết nối.

Ví dụ CLI minh họa:

~~~bash
liquibase \
  --url=jdbc:postgresql://db-host:5432/appdb \
  --default-schema-name=sales \
  --changelog-file=db/changelog/master.yaml \
  update
~~~

Tham số và cách viết tùy phiên bản CLI. Nếu một changeset cần tạo object ở crm, nên khai báo schemaName: crm rõ ràng. Điều này giúp tránh việc kết quả phụ thuộc search_path hoặc cấu hình mặc định vô tình thay đổi giữa các môi trường.

### 4.3. defaultCatalogName và catalogName

defaultCatalogName có vai trò tương tự mặc định catalog khi DBMS và Liquibase hỗ trợ khái niệm đó. catalogName ở change có thể định danh catalog của object. Tuy nhiên:

- Không phải DBMS nào cũng phân biệt catalog và schema như nhau.
- Không phải change type nào cũng hỗ trợ cùng thuộc tính catalog.
- Đặt catalogName không tự mở kết nối mới hoặc xác thực rằng database đích là đúng.
- Một số DBMS giới hạn DDL cross-database hoặc yêu cầu quyền đặc biệt.

Với PostgreSQL, một JDBC connection gắn với một database; muốn quản lý database khác thường phải tạo connection riêng. Với SQL Server, cross-database naming có thể xuất hiện trong truy vấn, nhưng không đồng nghĩa mọi DDL và transaction có thể triển khai portable. Với MySQL, database/schema có cách dùng thuật ngữ khác với PostgreSQL.

## 5. Quản lý DATABASECHANGELOG khi có nhiều schema

Đây là điểm thiết kế quan trọng nhất khi dùng một changelog cho nhiều schema.

Liquibase ghi changeset đã thực thi vào bảng DATABASECHANGELOG. Một bản ghi được nhận diện chủ yếu bằng tổ hợp id, author và đường dẫn changelog (filename hoặc logical file path theo cấu hình). Nếu cùng một bảng lịch sử được dùng chung cho nhiều schema, một changeset có cùng định danh sẽ được ghi nhận một lần.

### 5.1. Lịch sử chung cho nhiều schema liên kết

Giả sử một lần phát hành luôn cập nhật cả sales và crm như một đơn vị. Một DATABASECHANGELOG dùng chung có thể phù hợp:

- Một changeset tạo sales.orders.
- Một changeset tạo crm.customer.
- Một changeset thêm FK sales.orders tới crm.customer.

Liquibase ghi nhận các changeset theo thứ tự trong một lịch sử chung. Khi update tiếp theo, những changeset đó không tự chạy lại chỉ vì chúng đã được áp dụng ở một schema khác. Đây là hành vi đúng nếu đơn vị triển khai là cả nhóm schema.

Điều kiện là pipeline phải xác minh tất cả object thuộc phạm vi phát hành đã đạt trạng thái mong muốn. Nếu một changeset chạy một phần do lỗi DBMS không rollback đầy đủ, lịch sử và object vật lý có thể lệch nhau; phải điều tra trước khi retry.

### 5.2. Lịch sử riêng cho từng schema hoặc tenant

Nếu mỗi tenant có schema riêng và phải được nâng cấp độc lập, một DATABASECHANGELOG chung có thể gây lỗi logic:

1. Chạy changelog với tenant A, changeset 001 tạo bảng orders trong schema A và được ghi vào lịch sử chung.
2. Chạy cùng changelog với tenant B nhưng vẫn dùng lịch sử đó.
3. Liquibase thấy changeset 001 đã chạy nên bỏ qua; bảng orders trong schema B chưa được tạo.

Giải pháp là tách lịch sử theo đơn vị triển khai độc lập, ví dụ đặt bảng DATABASECHANGELOG và DATABASECHANGELOGLOCK trong schema của từng tenant, hoặc dùng bảng lịch sử riêng biệt trong schema quản trị. Mỗi lần chạy phải trỏ đúng lịch sử tương ứng tenant.

Các tham số cấu hình lịch sử thường bao gồm tên/schema của Liquibase metadata tables, chẳng hạn liquibaseSchemaName và các tên bảng changelog/lock. Tên tham số chính xác có thể khác theo phiên bản CLI, API hoặc Spring Boot integration; phải kiểm tra tài liệu của phiên bản dự án.

### 5.3. Không nhầm schema object với schema của bảng lịch sử

defaultSchemaName điều khiển schema mặc định cho object database. liquibaseSchemaName điều khiển nơi đặt các bảng metadata Liquibase trong những DBMS/tích hợp hỗ trợ. Hai mục đích khác nhau.

Ví dụ một tenant có schema tenant_a, trong khi lịch sử được lưu ở schema quản trị migration_control. Nếu tất cả tenant cùng dùng đúng một bảng DATABASECHANGELOG tại migration_control, changeset định danh giống nhau vẫn chỉ được ghi một lần. Chỉ đổi defaultSchemaName thành tenant_a không tạo lịch sử độc lập.

Nếu muốn mỗi tenant có tiến độ riêng, cần tách history identity/scope rõ ràng: dùng schema metadata riêng theo tenant hoặc tên bảng history riêng theo quy tắc được kiểm soát. Không chỉnh sửa nội dung changeset tùy tiện chỉ để tạo định danh khác nhau.

### 5.4. DATABASECHANGELOGLOCK cũng cần đúng phạm vi

DATABASECHANGELOGLOCK phối hợp các tiến trình Liquibase dùng cùng lock table. Nếu nhiều tenant có lịch sử độc lập, cần quyết định lock table có tách theo tenant hay dùng chung để tuần tự hóa. Lock riêng cho phép chạy song song nhưng có thể tăng tải DBMS; lock chung hạn chế cạnh tranh nhưng có thể làm các tenant chờ nhau.

Không coi lock của Liquibase là khóa nghiệp vụ. Nó không ngăn ứng dụng hoặc DBA thay đổi schema/data ngoài luồng migration.

## 6. Schema-per-tenant: triển khai cùng một changelog cho nhiều tenant

Trong mô hình schema-per-tenant, mỗi tenant có schema riêng nhưng thường dùng chung một cấu trúc. Ví dụ:

~~~text
appdb
  ├── tenant_001
  │     ├── customer
  │     └── orders
  ├── tenant_002
  │     ├── customer
  │     └── orders
  └── tenant_003
        ├── customer
        └── orders
~~~

Ứng dụng có thể chọn schema theo tenant hiện tại, nhưng migration cần chạy qua tất cả schema. Một cách tổ chức là chạy cùng changelog nhiều lần, mỗi lần với:

- defaultSchemaName tương ứng tenant.
- liquibaseSchemaName tương ứng tenant hoặc metadata scope riêng.
- Một datasource/database connection đúng.
- Một context/label/filter được xác định.
- Một lịch sử changeset độc lập để biết tenant nào đã nâng cấp.

### 6.1. Changelog có tham số schema

Ví dụ YAML dùng property:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-orders
      author: platform
      changes:
        - createTable:
            schemaName: ${tenant.schema}
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: created_at
                  type: timestamp
~~~

Pipeline cung cấp giá trị tenant.schema theo từng tenant, ví dụ tenant_001. Cần xác minh cơ chế ưu tiên property của phiên bản Liquibase và nguồn cấu hình; giá trị truyền từ CLI hoặc integration có thể được ưu tiên hơn property mặc định trong changelog.

Chỉ nhận tên schema từ registry/cấu hình triển khai được kiểm soát. Không đưa input tùy ý từ request người dùng vào identifier trong changelog. Kiểm tra tên schema hợp lệ, đúng tenant và không chứa cú pháp quote/SQL ngoài dự kiến.

### 6.2. Một vòng chạy cho từng tenant

Quy trình có thể biểu diễn:

~~~text
Lấy danh sách tenant được phê duyệt
             |
             v
Xác định schema + history table của tenant
             |
             v
Kiểm tra kết nối, quyền và preconditions
             |
             v
Validate + status + SQL preview
             |
             v
Chạy Liquibase update cho tenant
             |
             v
Xác minh object + DATABASECHANGELOG
             |
             v
Ghi checkpoint thành công/thất bại
             |
             v
Chuyển sang tenant tiếp theo
~~~

Không nhất thiết phải nâng cấp tất cả tenant cùng lúc. Với số lượng lớn, có thể triển khai theo batch/canary, theo dõi lock, CPU, I/O, replication lag và lỗi ứng dụng. Mỗi tenant cần trạng thái tiến độ rõ ràng để có thể tiếp tục sau khi một tenant thất bại.

### 6.3. Giới hạn concurrency

Chạy 100 tenant song song không có nghĩa migration hoàn tất nhanh hơn 100 lần. Các schema vẫn dùng chung CPU, I/O, buffer pool, WAL/redo, storage và connection pool của một database server. Nhiều DDL cùng lúc có thể tranh chấp metadata lock, tài nguyên và làm dịch vụ chính chậm.

Hãy chọn concurrency dựa trên thử nghiệm tải và giới hạn vận hành. Có thể bắt đầu tuần tự hoặc một số worker nhỏ, sau đó tăng dần khi có bằng chứng. Không dùng cùng một Liquibase instance/connection để thực thi song song nhiều changelog mà không hiểu giới hạn API và lock.

## 7. Nhiều catalog/database: một datasource cho mỗi đích độc lập

Khi một ứng dụng kết nối tới nhiều database độc lập, mỗi database cần một cấu hình kết nối và phạm vi lịch sử riêng. Ví dụ:

~~~text
Orders Service
   ├── ordersDataSource  → orders_db
   │       └── Liquibase orders
   │             ├── DATABASECHANGELOG
   │             └── DATABASECHANGELOGLOCK
   |
   └── billingDataSource → billing_db
           └── Liquibase billing
                 ├── DATABASECHANGELOG
                 └── DATABASECHANGELOGLOCK
~~~

Trong kiến trúc này:

- Changelog orders chỉ chạy qua ordersDataSource.
- Changelog billing chỉ chạy qua billingDataSource.
- Mỗi database có lịch sử riêng.
- Credential và quyền được cấp riêng theo nguyên tắc least privilege.
- Pipeline ghi nhận kết quả của từng đích; không giả định hai database cập nhật nguyên tử cùng nhau.

### 7.1. Một Liquibase instance không phải bộ điều phối giao dịch phân tán

Hai database độc lập thường không thể được cập nhật trong cùng một transaction đơn giản chỉ vì chúng thuộc cùng một ứng dụng. Liquibase chạy update trên orders_db thành công nhưng billing_db thất bại thì trạng thái thực tế là:

- Orders đã ở phiên bản mới.
- Billing vẫn ở phiên bản cũ.
- Ứng dụng có thể cần chạy ở chế độ tương thích trong lúc khắc phục.

Không giả định Liquibase sẽ tự rollback database thứ nhất khi database thứ hai thất bại. Phải thiết kế dependency và trình tự triển khai, hoặc sử dụng mô hình tương thích/forward fix.

### 7.2. Cấu hình Spring Boot với nhiều Liquibase

Trong Spring Boot, một datasource thường được gắn với một cấu hình Liquibase. Khi có nhiều datasource, cần tạo các bean SpringLiquibase riêng hoặc cách tích hợp tương đương theo phiên bản:

~~~java
@Bean
SpringLiquibase ordersLiquibase(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    SpringLiquibase liquibase = new SpringLiquibase();
    liquibase.setDataSource(dataSource);
    liquibase.setChangeLog("classpath:/db/changelog/orders-master.yaml");
    liquibase.setDefaultSchema("orders");
    liquibase.setLiquibaseSchema("orders");
    return liquibase;
}

@Bean
SpringLiquibase billingLiquibase(
        @Qualifier("billingDataSource") DataSource dataSource) {
    SpringLiquibase liquibase = new SpringLiquibase();
    liquibase.setDataSource(dataSource);
    liquibase.setChangeLog("classpath:/db/changelog/billing-master.yaml");
    liquibase.setDefaultSchema("billing");
    liquibase.setLiquibaseSchema("billing");
    return liquibase;
}
~~~

Đây là ví dụ minh họa API SpringLiquibase và cách gắn datasource/changelog riêng. Constructor, setter, bean lifecycle và cách bind LiquibaseProperties có thể thay đổi theo phiên bản Spring Boot/Liquibase. Phải kiểm tra API đúng dependency đang dùng, đánh dấu @Qualifier rõ ràng và tránh để auto-configuration tạo thêm một Liquibase bean ngoài dự kiến.

Nếu hai Liquibase bean có dependency triển khai, cần điều phối thứ tự rõ ràng, ví dụ job migration riêng hoặc dependency trong application context. Không dựa vào thứ tự khởi tạo bean ngẫu nhiên.

### 7.3. Cấu hình quyền riêng

Orders migration user không nhất thiết cần quyền DDL trên billing_db. Billing migration user cũng không nên có quyền sửa schema orders nếu không cần thiết. Tách credentials giúp:

- Giảm phạm vi sự cố khi cấu hình sai datasource.
- Dễ audit changeset theo owner.
- Giảm quyền vượt quá nhu cầu.
- Xác định rõ service nào chịu trách nhiệm object nào.

Không ghi password hoặc secret trực tiếp vào changelog, source code hay log. Sử dụng secret manager hoặc cơ chế cấu hình bảo mật của nền tảng.

## 8. Cross-schema và cross-catalog dependency

Dependency giữa hai schema cùng database thường có thể biểu diễn bằng schema-qualified object và FK/view tùy DBMS. Dependency giữa hai catalog/database độc lập phức tạp hơn:

- Một DBMS có thể cho phép truy vấn cross-database nhưng không hỗ trợ FK xuyên database.
- Một DBMS có database link, synonym hoặc linked server với quyền và cú pháp riêng.
- Một thay đổi ở database A có thể cần database B đã sẵn sàng trước.
- Không có bảo đảm transaction nguyên tử giữa hai Liquibase instance nếu không có cơ chế phân tán riêng.

### 8.1. Tổ chức thứ tự triển khai

Ví dụ billing cần đọc customer_id do orders quản lý:

1. Đảm bảo contract/schema ở orders đã sẵn sàng.
2. Triển khai billing để có thể đọc định dạng mới hoặc chấp nhận trạng thái chuyển tiếp.
3. Chạy migration billing sau khi dependency đã đạt.
4. Xác minh tích hợp giữa hai database bằng kiểm thử ứng dụng.
5. Chỉ loại bỏ cấu trúc cũ sau khi cả hai phía không còn phụ thuộc.

Không dùng precondition SQL trên datasource billing để giả định nó có thể truy vấn catalog orders nếu hai database không nằm trong cùng connection hoặc DBMS không hỗ trợ cross-catalog access. Trong trường hợp đó, pipeline cần một gate ngoài database hoặc bước kiểm tra qua kết nối riêng.

### 8.2. Chọn một nguồn chuẩn cho object dùng chung

Nếu nhiều service cùng dùng schema crm, cần có owner rõ ràng cho changelog của schema đó. Không để orders service và billing service cùng tạo changeset quản lý một object crm.customer với lịch sử riêng mà không có quy ước, vì có thể dẫn đến:

- Hai DATABASECHANGELOG không phản ánh cùng trạng thái.
- Một service drop/modify object mà service khác đang dùng.
- Hai pipeline chạy đồng thời DDL trên cùng object.
- Rollback của một service làm hỏng service còn lại.

Một schema dùng chung nên có một luồng migration có thẩm quyền hoặc một cơ chế phối hợp release được thống nhất.

## 9. Phân biệt schema-per-tenant và shared-schema multi-tenancy

Không phải ứng dụng nhiều tenant nào cũng cần nhiều schema.

| Mô hình | Cách lưu dữ liệu | Đặc điểm migration |
|---|---|---|
| Shared schema | Mọi tenant dùng chung table, phân biệt bằng tenant_id | Một cấu trúc chung; cần kiểm soát dữ liệu theo tenant và index theo tenant |
| Schema-per-tenant | Mỗi tenant có các bảng trong schema riêng | Cùng changelog có thể chạy nhiều lần với tham số schema và history riêng |
| Database-per-tenant | Mỗi tenant có database riêng | Datasource/Liquibase instance hoặc connection theo tenant; lịch sử độc lập |

Shared schema không cần chạy cùng changeset tạo table cho từng tenant; bảng đã tồn tại dùng chung. Còn schema-per-tenant cần đảm bảo mỗi schema đã nhận đúng changeset. Database-per-tenant cần xử lý kết nối, credential, lịch sử và concurrency theo từng database.

Lựa chọn mô hình là quyết định kiến trúc có tác động đến backup, restore, security, vận hành và chi phí. Không chuyển từ shared schema sang schema-per-tenant chỉ bằng cách đổi defaultSchemaName.

## 10. Kiểm soát search_path, default schema và identifier

Nhiều ứng dụng dựa vào schema mặc định hoặc session search path. Điều này tiện nhưng dễ tạo sai đích nếu connection pool tái sử dụng session hoặc cấu hình khác nhau giữa môi trường.

Ví dụ trên PostgreSQL:

~~~sql
SHOW search_path;
SELECT current_database(), current_schema();
~~~

Các câu lệnh giúp kiểm tra database và schema hiện hành của session. Nếu SQL trong changelog viết:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY
);
~~~

thì schema đích phụ thuộc search_path/default schema của session và cấu hình Liquibase. Nếu cần tạo ở schema cụ thể, nên dùng schemaName trong change hoặc SQL fully-qualified phù hợp DBMS:

~~~sql
CREATE TABLE sales.orders (
    id BIGINT PRIMARY KEY
);
~~~

Tên schema và quoting phải phù hợp DBMS; ví dụ trên là cú pháp PostgreSQL thông thường với tên chữ thường. Không hardcode schema khác môi trường nếu có thể dùng property được kiểm soát.

### 10.1. Identifier có chữ hoa/thường

PostgreSQL gập identifier không trích dẫn về chữ thường; Oracle thường gập về chữ hoa; MySQL có quy tắc tên bảng phụ thuộc cấu hình và filesystem; SQL Server chịu ảnh hưởng collation. Vì vậy, cùng một tên schema có thể được hiển thị hoặc tra cứu khác nhau.

Khi dùng nhiều schema:

- Chọn convention tên ổn định, thường là chữ thường snake_case nếu phù hợp.
- Tránh schema chỉ khác nhau bởi chữ hoa/thường.
- Không tự ghép dấu quote vào schemaName/catalogName trong changelog.
- Kiểm tra SQL preview và catalog thật sau triển khai.
- Dùng objectQuotingStrategy có chủ đích nếu dự án cần quoted identifiers.

### 10.2. Connection pool và session state

Không giả định mỗi request được cấp một session mới. Connection pool có thể tái sử dụng session và một số setting như search_path hoặc role có thể tồn tại qua lần mượn kết nối nếu không được reset đúng cách.

Với ứng dụng chọn schema theo tenant, cần một cơ chế an toàn để đặt và khôi phục schema/session context; đồng thời kiểm thử khi nhiều request tenant khác nhau dùng chung pool. Liquibase migration nên chạy bằng connection và schema target được xác định rõ, không dựa vào trạng thái session còn sót từ một request ứng dụng.

## 11. Changelog parameters và cấu hình theo môi trường

Một changelog có thể dùng property để tái sử dụng cho nhiều schema:

~~~yaml
databaseChangeLog:
  - property:
      name: app.schema
      value: sales

  - changeSet:
      id: 020-create-audit-event
      author: platform
      changes:
        - createTable:
            schemaName: ${tenant.schema}
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Giá trị sales là mặc định minh họa. Pipeline có thể cung cấp app.schema theo tenant hoặc môi trường. Cần xác minh precedence giữa property trong changelog, file cấu hình, environment variable, CLI và Spring Boot integration theo phiên bản.

### 11.1. Không trộn parameter schema với database URL

app.schema chỉ thay thế tên schema trong changelog. Nó không thay đổi database mà JDBC URL kết nối tới. Nếu cần chuyển từ orders_db sang billing_db, phải chọn datasource/URL tương ứng.

Đây là nguyên tắc quan trọng khi ứng dụng có nhiều catalog: đổi schema parameter không thể biến một connection đang gắn orders_db thành connection tới billing_db.

### 11.2. Không dùng context/label thay cho schema isolation

Context và label giúp chọn nhóm changeset theo mục đích hoặc giai đoạn phát hành. Chúng không tự tạo lịch sử riêng cho từng tenant. Nếu chạy cùng changeset với cùng history table trên nhiều schema, context/label không giải quyết việc changeset đã được ghi nhận một lần.

Hãy tách rõ:

- Property/default schema: object được tạo ở đâu.
- Datasource/catalog: kết nối tới database nào.
- Context/label: changeset nào được chọn.
- DATABASECHANGELOG: changeset nào đã được ghi nhận trong đơn vị lịch sử đó.
- DATABASECHANGELOGLOCK: tiến trình nào đang giữ khóa điều phối lịch sử.

## 12. Preconditions để bảo vệ đúng đích

Khi changelog chạy cho nhiều schema, precondition cần kiểm tra đúng schema thay vì dựa vào schema mặc định không rõ ràng.

Ví dụ kiểm tra schema và bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 030-add-audit-column
      author: platform
      preConditions:
        - onFail: HALT
        - onError: HALT
        - schemaExists:
            schemaName: ${tenant.schema}
        - tableExists:
            schemaName: ${tenant.schema}
            tableName: audit_event
      changes:
        - addColumn:
            schemaName: ${tenant.schema}
            tableName: audit_event
            columns:
              - column:
                  name: actor_id
                  type: varchar(80)
~~~

Ví dụ giả định precondition schemaExists và tableExists được hỗ trợ trong phiên bản Liquibase/DBMS đang dùng. Nếu schema không tồn tại, HALT dừng changeset; nếu không đọc được metadata, onError cũng dừng.

Một precondition chỉ xác nhận điều kiện tại thời điểm đánh giá. Nó không ngăn một tiến trình khác đổi object ngay sau đó, không chứng minh quyền tạo object và không bảo đảm mọi schema tenant đều đã chạy. Pipeline phải lặp kiểm tra theo từng tenant và lưu kết quả.

### 12.1. Kiểm tra đúng catalog/database

Precondition dbms có thể xác nhận engine, nhưng không đủ để xác nhận đúng database/catalog. Có thể cần kiểm tra tên database bằng SQL đặc thù DBMS hoặc kiểm tra connection metadata trong pipeline. Ví dụ PostgreSQL:

~~~sql
SELECT current_database();
~~~

Không dùng một câu SQL chung cho mọi DBMS để kiểm tra catalog. Nếu một pipeline dùng nhiều datasource, tên datasource và URL phải được xác minh trước khi khởi chạy Liquibase.

## 13. Rollback trong môi trường nhiều schema/catalog

Rollback phải dùng cùng đơn vị quản lý đã chọn:

- Nhiều schema có lịch sử chung: rollback có thể đảo nhiều changeset ảnh hưởng các schema cùng đơn vị.
- Mỗi tenant có history riêng: rollback tenant A không tự rollback tenant B.
- Nhiều catalog với Liquibase riêng: rollback từng database là các thao tác độc lập, cần điều phối thứ tự.

### 13.1. Tránh rollback một schema nhưng làm hỏng schema phụ thuộc

Nếu sales.orders có FK tới crm.customer, rollback thay đổi ở crm có thể làm sales mất dependency. Trước khi rollback cần xác định dependency graph và thứ tự:

1. Ngừng hoặc chuyển ứng dụng khỏi các luồng phụ thuộc object sắp gỡ.
2. Gỡ FK/view/trigger phụ thuộc ở schema con nếu kế hoạch yêu cầu.
3. Rollback object ở schema cha.
4. Xác minh dữ liệu, catalog và ứng dụng.

Không mặc định thứ tự rollback đơn giản là đảo thứ tự file; cần xem changeset thực sự đã chạy và các phụ thuộc được tạo sau đó.

### 13.2. Nhiều database không có rollback nguyên tử chung

Giả sử orders_db rollback thành công nhưng billing_db rollback thất bại. Hai database ở hai trạng thái khác nhau. Ứng dụng phải có khả năng hoạt động an toàn trong trạng thái trung gian hoặc hệ thống phải tạm ngừng chức năng liên quan để khắc phục.

Với dữ liệu đã biến đổi, rollback DDL không phục hồi dữ liệu. Cần backup, mapping, forward fix hoặc restore theo kế hoạch. Không dùng một tag Liquibase như thể nó là snapshot đồng thời của mọi database.

## 14. Kiểm thử và xác minh theo từng đích

Một changelog dùng cho nhiều schema/catalog cần được kiểm tra theo từng cấu hình thực thi:

| Kiểm tra | Một database, nhiều schema | Nhiều database/catalog |
|---|---|---|
| Kết nối | Đúng database, có quyền trên các schema | Đúng datasource/URL của từng database |
| Default schema/catalog | Không gây ghi nhầm namespace | Được cấu hình riêng theo connection |
| Object changes | SchemaName/catalogName chính xác | Changelog đúng với DBMS và database |
| History | Chung hay riêng theo đơn vị phát hành | Thường độc lập cho từng database |
| Lock | Lock chung có thể tuần tự hóa nhóm schema | Lock riêng theo database/instance |
| Dependency | Kiểm tra giữa schema trong cùng database | Điều phối giữa database qua pipeline |
| Rollback | Đánh giá ảnh hưởng mọi schema trong lịch sử chung | Rollback độc lập và xử lý trạng thái lệch |

Các bước kiểm chứng trước update:

1. Ghi lại database/catalog, schema, DBMS/version và datasource.
2. Xác minh user migration có quyền tối thiểu cần thiết.
3. Chạy validate và status với đúng changelog, property, context/label.
4. Sinh SQL preview và kiểm tra fully-qualified object.
5. Kiểm tra DATABASECHANGELOG và DATABASECHANGELOGLOCK trong đúng history scope.
6. Chạy thử trên một schema/tenant đại diện.
7. Đối chiếu object và dữ liệu sau update.
8. Thử rollback hoặc forward fix trong môi trường cô lập.
9. Mở rộng theo batch có giới hạn concurrency.

### 14.1. Lệnh CLI minh họa

~~~bash
liquibase --defaults-file=./config/tenant-001.properties validate
liquibase --defaults-file=./config/tenant-001.properties status --verbose
liquibase --defaults-file=./config/tenant-001.properties update-sql
liquibase --defaults-file=./config/tenant-001.properties update
~~~

Tên lệnh và tham số có thể khác theo phiên bản Liquibase; một số phiên bản hiển thị lệnh sinh SQL dưới tên updateSQL. Phải dùng đúng cú pháp và cùng artifact/property đã review. Không ghi mật khẩu trực tiếp vào shell history hoặc log.

### 14.2. Xác minh sau triển khai

Không chỉ kiểm tra exit code. Với mỗi schema/catalog:

- Xác nhận bảng, cột, index, constraint và view đã tồn tại đúng schema.
- Kiểm tra dữ liệu và các điều kiện nghiệp vụ.
- Đọc DATABASECHANGELOG để biết changeset đã được ghi nhận ở history nào.
- Xác minh trạng thái lock đã được giải phóng.
- Kiểm tra quyền runtime của ứng dụng.
- Chạy smoke test trên datasource/schema đích.
- Ghi checkpoint tenant/database thành công hoặc lỗi.

Một pipeline hoàn tất một phần phải báo rõ đích nào thành công, đích nào thất bại; không gộp thành một trạng thái “migration thành công” chung.

## 15. Tổ chức CI/CD cho nhiều schema và catalog

### 15.1. Pipeline cho nhiều schema trong một database

Một pipeline có thể:

1. Lấy danh sách schema được phép nâng cấp từ registry.
2. Xác minh schema tồn tại, owner và quyền migration.
3. Với từng schema, chọn property và history scope tương ứng.
4. Chạy validate/status/preview.
5. Triển khai theo batch có concurrency giới hạn.
6. Lưu kết quả, checkpoint và metrics từng schema.
7. Dừng hoặc pause khi có lỗi vượt ngưỡng.

Nếu các schema thuộc cùng một release và có dependency chặt, có thể triển khai theo một changelog/history chung, nhưng cần bảo đảm các bước thành công theo thứ tự và có phương án xử lý partial failure.

### 15.2. Pipeline cho nhiều database

Mỗi database cần:

- Datasource/secret riêng.
- Changelog root và parameters đúng đích.
- Liquibase history/lock riêng.
- DBMS/version compatibility được kiểm tra.
- Thứ tự triển khai và dependency được khai báo.
- Báo cáo độc lập cùng một release manifest tổng hợp.

Nếu database B phụ thuộc schema mới từ database A, pipeline phải chạy gate kiểm tra A trước khi cập nhật B. Không dựa vào một transaction xuyên database không được hỗ trợ.

### 15.3. Chạy song song hay tuần tự?

Chạy song song có thể rút ngắn thời gian khi các database độc lập, nhưng tăng số kết nối, tải I/O và áp lực lên hạ tầng dùng chung. Chạy tuần tự dễ kiểm soát nhưng có thể kéo dài cửa sổ phát hành. Quyết định dựa trên:

- Mức độc lập của database/schema.
- Mức tải và khả năng chịu DDL của DBMS.
- Tính chất lock và transaction của từng thao tác.
- SLO ứng dụng và giới hạn cửa sổ bảo trì.
- Khả năng resume sau lỗi và độ tin cậy của checkpoint.

Không chạy đồng thời hai pipeline trên cùng object chỉ vì mỗi pipeline dùng DATABASECHANGELOG khác nhau. History lock tách biệt không loại bỏ lock DDL của DBMS.

## 16. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Đổi defaultSchemaName nhưng dùng chung history cho tenant | Changeset chỉ chạy lần đầu, tenant sau bị bỏ qua | Tách history theo đơn vị tenant hoặc thiết kế một lần triển khai cho cả nhóm schema |
| Nhầm schemaName với database/catalog | SQL chạy sai namespace hoặc không kết nối được database đích | Phân biệt JDBC URL, catalog và schema |
| Không chỉ rõ schema trong changeset | Phụ thuộc default schema/search_path khác nhau | Dùng schemaName tường minh cho object quan trọng |
| Một Liquibase bean dùng nhầm datasource | Migration tác động database sai | Dùng @Qualifier và xác minh connection identity |
| Nhiều Liquibase bean không có thứ tự | Database phụ thuộc được migrate trước database nền | Điều phối thứ tự trong application context hoặc CI/CD |
| Cùng một DATABASECHANGELOG cho nhiều tenant độc lập | Tenant sau không chạy changeset đã ghi nhận | History riêng hoặc logical unit riêng được thiết kế đúng |
| History riêng nhưng object dùng chung | Nhiều pipeline cùng sửa một object | Chỉ định một owner và một migration authority |
| Dùng context/label để giả lập history riêng | Changeset vẫn bị coi là đã chạy trong history chung | Tách lịch sử, không nhầm filter với identity |
| Chạy mọi tenant song song không giới hạn | Lock contention, CPU/I/O cao, replication lag | Giới hạn concurrency và theo dõi tải |
| Chỉ kiểm tra exit code tổng | Một số tenant/database có thể chưa migrate | Báo trạng thái riêng từng đích và đối soát sau chạy |
| Rollback một database mà không xét database phụ thuộc | Ứng dụng rơi vào trạng thái không tương thích | Dependency graph và orchestration rollback |
| Dùng catalogName để đổi JDBC database | Kết nối vẫn ở database ban đầu | Tạo datasource/connection đúng database |
| Chỉ kiểm tra object tồn tại, không kiểm tra history | Object thủ công có thể bị hiểu là changeset đã chạy | Đối chiếu catalog với DATABASECHANGELOG |
| Tài khoản migration dùng quyền quá rộng | Sai cấu hình có thể ảnh hưởng nhiều database | Tách credentials và cấp quyền tối thiểu |
| Search path còn sót từ connection pool | Truy vấn tenant có thể nhắm nhầm schema | Reset session context và dùng schema qualification |

## 17. Bài thực hành

### Bài A — Hai schema trong một database

Tạo database thử có schema sales và crm. Dùng một changelog tạo sales.orders và crm.customer, sau đó thêm index và FK phù hợp.

Thực hiện:

1. Chạy validate và update-sql.
2. Xác minh SQL tạo đúng schema.
3. Chạy update và kiểm tra object trong catalog.
4. Đọc DATABASECHANGELOG và xác nhận mỗi changeset được ghi nhận một lần.
5. Thử rollback trong database cô lập và xác minh dependency.

Mục tiêu: hiểu lịch sử chung phù hợp khi cả hai schema là một đơn vị phát hành.

### Bài B — Hai tenant schema độc lập

Tạo tenant_001 và tenant_002. Dùng cùng changelog với property tenant.schema nhưng history độc lập cho mỗi tenant.

Thực hiện:

1. Chạy update cho tenant_001.
2. Chạy update cho tenant_002.
3. Xác minh cả hai schema đều có object.
4. Xác minh mỗi history ghi nhận changeset riêng.
5. Chạy lại update tenant_001 và xác nhận không tạo object trùng.
6. Mô phỏng tenant_002 thất bại, rồi resume mà không chạy nhầm tenant_001.

Mục tiêu: chứng minh việc thay property schema không tự tạo history độc lập; cấu hình lịch sử phải được tách rõ.

### Bài C — Hai catalog/database

Tạo orders_db và billing_db trong môi trường thử nghiệm. Cấu hình hai datasource và hai Liquibase instance với changelog/history riêng.

Thực hiện:

1. Xác minh mỗi Liquibase dùng đúng datasource.
2. Chạy migration orders và billing.
3. Mô phỏng billing thất bại sau khi orders thành công.
4. Xác minh trạng thái trung gian và khả năng ứng dụng tiếp tục hoạt động an toàn.
5. Thử forward fix hoặc rollback riêng từng database.

Mục tiêu: hiểu hai database không được cập nhật nguyên tử chỉ vì cùng thuộc một ứng dụng.

## 18. Checklist trước khi vận hành

- [ ] Đã phân biệt database/catalog/schema theo đúng DBMS.
- [ ] Đơn vị migration được xác định: toàn database, từng schema, từng tenant hay từng catalog.
- [ ] Mỗi datasource/connection có tên, URL, owner và quyền rõ ràng.
- [ ] defaultSchemaName/defaultCatalogName không được dùng thay cho việc xác định đích kết nối.
- [ ] Changeset chỉ rõ schema/catalog khi cần; không phụ thuộc search_path không kiểm soát.
- [ ] DATABASECHANGELOG và DATABASECHANGELOGLOCK nằm đúng phạm vi lịch sử đã chọn.
- [ ] Tenant độc lập có history độc lập; nhóm schema phát hành cùng nhau có thể dùng history chung có chủ đích.
- [ ] Không dùng context/label để thay thế history isolation.
- [ ] Nhiều Liquibase instance có datasource, changelog và cấu hình riêng.
- [ ] Dependency giữa schema/database có thứ tự và gate kiểm chứng.
- [ ] Cross-catalog DDL/query được xác nhận hỗ trợ trên DBMS cụ thể.
- [ ] Concurrency được giới hạn và giám sát tải, lock, replication lag.
- [ ] Preconditions xác nhận đúng schema và trạng thái, không thay thế việc kiểm tra kết nối.
- [ ] Rollback đã được review theo phạm vi ảnh hưởng và khả năng phục hồi dữ liệu.
- [ ] Pipeline báo cáo riêng từng schema/database, có checkpoint và khả năng resume.
- [ ] Sau deploy đã xác minh object, dữ liệu, history, quyền và chức năng ứng dụng.

## 19. Ghi nhớ

Quản lý nhiều schema và catalog trong một ứng dụng đòi hỏi tách bạch **nơi kết nối**, **namespace của object** và **đơn vị lịch sử migration**. defaultSchemaName/schemaName giúp xác định schema; defaultCatalogName/catalogName có ý nghĩa tùy DBMS; datasource/JDBC URL quyết định database thực sự được kết nối. DATABASECHANGELOG ghi nhận changeset theo định danh trong một history scope, nên dùng chung history cho nhiều tenant độc lập có thể khiến changeset chỉ chạy ở tenant đầu tiên.

Với nhiều schema liên kết trong cùng database, một changelog và lịch sử chung có thể phù hợp nếu triển khai như một đơn vị. Với schema-per-tenant hoặc nhiều database độc lập, cần history/lock scope và Liquibase instance phù hợp từng đơn vị, cùng pipeline điều phối thứ tự, concurrency và partial failure. Quy trình đáng tin cậy là **xác định mô hình → chọn datasource/schema/history → kiểm tra dependency và quyền → preview → triển khai theo đích → xác minh từng lịch sử và object → quản lý rollback/forward fix**. Cách tổ chức này giúp ứng dụng Spring Boot hoặc CI/CD quản lý nhiều database có thể dự đoán, truy vết và vận hành an toàn.
