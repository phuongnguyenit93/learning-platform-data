# Quản lý DDL, PL/SQL và dữ liệu tham chiếu bằng version control

Schema Oracle là một phần của ứng dụng. Bảng, cột, index, constraint, sequence, view, package, procedure, trigger và dữ liệu tham chiếu đều ảnh hưởng đến cách ứng dụng hoạt động. Nếu các thay đổi này chỉ được thực hiện thủ công trên từng môi trường, sau một thời gian development, test và production có thể có cấu trúc khác nhau dù cùng chạy một phiên bản ứng dụng.

Version control cho database giúp lưu lịch sử thay đổi, review trước khi triển khai, dựng lại schema từ trạng thái ban đầu và xác định chính xác database đã nhận những thay đổi nào. Mục tiêu không chỉ là đưa file SQL vào Git, mà là xây dựng quy trình migration có thứ tự, có thể kiểm soát, có bằng chứng triển khai và có cách xử lý lỗi phù hợp với đặc tính Oracle.

Trong Oracle, cần đặc biệt lưu ý rằng nhiều câu lệnh DDL gây implicit commit. Vì vậy, migration chứa `CREATE`, `ALTER`, `DROP` hoặc `TRUNCATE` không thể được rollback như một transaction DML thông thường. Chiến lược thay đổi schema phải được thiết kế theo hướng triển khai tiến về phía trước, có bước kiểm tra trạng thái và có kế hoạch khôi phục dữ liệu/ứng dụng riêng.

## 1. Vì sao phải version control database?

Ứng dụng Java có source code trong Git, nhưng nếu schema Oracle không được quản lý cùng mức kỷ luật, source code không đủ để tái tạo môi trường chạy.

Ví dụ một release thêm chức năng lưu trạng thái thanh toán. Thay đổi có thể bao gồm:

- Thêm cột `PAYMENT_STATUS` vào bảng `ORDERS`.
- Thêm constraint kiểm soát giá trị trạng thái.
- Tạo index hỗ trợ truy vấn báo cáo.
- Sửa package `ORDER_API` để cập nhật trạng thái.
- Thêm các mã trạng thái chuẩn vào bảng `PAYMENT_STATUSES`.
- Cấp quyền cho runtime role đọc bảng mới.

Nếu chỉ commit Java code mà quên migration, ứng dụng mới có thể chạy trên máy developer nhưng lỗi khi deploy sang test hoặc production. Ngược lại, nếu DBA sửa trực tiếp production mà không có script trong repository, các môi trường sau không thể dựng lại đúng schema.

### 1.1. Lợi ích của database version control

| Lợi ích | Ý nghĩa thực tế |
|---|---|
| Lịch sử thay đổi | Biết ai thay đổi bảng, package hoặc dữ liệu tham chiếu, trong release nào |
| Tái lập môi trường | Có thể tạo schema mới bằng cùng chuỗi migration |
| Review | DBA và developer review DDL, quyền, index và data migration trước khi triển khai |
| Tính nhất quán | Development, test, staging và production nhận cùng thay đổi đã được phê duyệt |
| Audit | Có bằng chứng file migration, commit Git và lần chạy trên từng môi trường |
| Phát hiện drift | So sánh schema thực tế với trạng thái mong đợi trong repository |
| Roll forward | Khi migration đã áp dụng, có thể tạo migration tiếp theo để sửa lỗi có kiểm soát |
| CI/CD | Pipeline có thể tự dựng database test và kiểm tra migration trước khi release |

### 1.2. Database schema cũng là source code

DDL và PL/SQL là mã nguồn của database. Chúng cần có:

- Lịch sử phiên bản.
- Quy tắc đặt tên và tổ chức file.
- Review và phê duyệt.
- Kiểm thử.
- Quy trình triển khai.
- Quyền sở hữu và trách nhiệm bảo trì.

Một package PL/SQL được sửa bằng SQL Developer trực tiếp trên production nhưng không được lưu vào Git là một thay đổi ngoài quy trình. Dù ứng dụng vẫn chạy, lần dựng môi trường tiếp theo có thể mất thay đổi đó.

## 2. Phân loại thay đổi database

Không phải mọi file SQL đều có cùng vòng đời. Cần phân biệt các loại thay đổi để chọn cách version phù hợp.

| Loại | Ví dụ | Cách quản lý thường dùng |
|---|---|---|
| DDL cấu trúc | Tạo bảng, thêm cột, constraint, index, sequence | Versioned migration |
| PL/SQL | Package spec/body, procedure, function, trigger | Versioned hoặc repeatable migration tùy công cụ |
| View/synonym | Tạo hoặc thay đổi view, synonym | Versioned hoặc repeatable migration |
| Quyền | `GRANT`, `REVOKE`, role, directory | Migration có review và quản lý theo môi trường |
| Dữ liệu tham chiếu | Mã trạng thái, loại giao dịch, danh mục cố định | Seed/versioned data migration hoặc repeatable upsert |
| Dữ liệu nghiệp vụ | Khách hàng, đơn hàng, giao dịch | Không đóng gói như seed schema; xử lý bằng nghiệp vụ/import riêng |
| Data migration | Chuyển đổi giá trị/cấu trúc dữ liệu hiện có | Versioned data migration có kiểm soát và đối soát |
| Cấu hình môi trường | Endpoint, credential, đường dẫn, service name | Secret/config management, không hard-code vào migration chung |

### 2.1. Schema migration và data migration

Schema migration thay đổi cấu trúc database. Ví dụ thêm cột `SOURCE_SYSTEM` hoặc tạo index.

Data migration thay đổi dữ liệu đã tồn tại. Ví dụ chuyển mã trạng thái từ `P` sang `PAID`, điền giá trị mặc định cho cột mới hoặc tách một cột thành hai cột.

Hai loại thay đổi có thể liên quan nhưng nên được phân biệt trong thiết kế. DDL thường gây implicit commit và thay đổi metadata; DML có thể nằm trong transaction, nhưng một data migration lớn có thể tạo lượng undo/redo lớn, giữ lock lâu và ảnh hưởng workload.

### 2.2. Dữ liệu tham chiếu khác dữ liệu nghiệp vụ

Dữ liệu tham chiếu là tập giá trị nhỏ, ổn định, được code dùng như mã hoặc danh mục, ví dụ:

- `ORDER_STATUS`: NEW, PAID, CANCELLED.
- `PAYMENT_METHOD`: CARD, BANK_TRANSFER, CASH.
- `COUNTRY_CODE` hoặc loại tài liệu theo danh mục do hệ thống quản lý.
- Mã phân loại nội bộ mà nhiều module cùng sử dụng.

Dữ liệu nghiệp vụ như customer, order, payment transaction không nên được đưa vào migration seed dùng chung. Dữ liệu nghiệp vụ được tạo qua ứng dụng, import hoặc quy trình vận hành.

## 3. Git repository cho database

Một cấu trúc thư mục rõ ràng giúp tìm được migration và biết script nào thuộc loại nào. Ví dụ:

```text
database/
  oracle/
    migrations/
      V001__create_reference_tables.sql
      V002__create_customers.sql
      V003__create_orders.sql
      V004__add_payment_status.sql
      V005__create_order_indexes.sql
      V006__grant_runtime_privileges.sql
    repeatable/
      R__order_api_package.sql
      R__customer_search_view.sql
    seed/
      reference/
        V001__seed_order_statuses.sql
        V002__seed_payment_methods.sql
    rollback-notes/
      V004__rollback_notes.md
    test-data/
      integration/
        customers.sql
        orders.sql
    README.md
```

Đây là một cách tổ chức minh họa. Nếu dùng Flyway, tên file và vị trí cần theo cấu hình của Flyway. Nếu dùng Liquibase, có thể tổ chức changelog XML/YAML/JSON/SQL và include các file con. Không nên trộn nhiều convention trong cùng một thư mục khiến tool không xác định được migration nào cần chạy.

### 3.1. Migration phải có thứ tự xác định

Một versioned migration nên có version duy nhất và tăng theo quy tắc của nhóm. Ví dụ:

```text
V001__create_customers.sql
V002__create_products.sql
V003__create_orders.sql
V004__create_order_items.sql
```

Migration tool sắp xếp theo version hoặc thứ tự changelog đã khai báo. Không nên dựa vào thứ tự file trong Windows Explorer, thứ tự Git commit hoặc thời gian file được sửa.

### 3.2. Migration đã chạy phải được xem là bất biến

Sau khi migration `V004` đã chạy ở một môi trường dùng chung, không sửa nội dung `V004` để “sửa lại lịch sử”. Tool thường lưu checksum hoặc thông tin tương đương; thay đổi file đã chạy có thể khiến validation thất bại hoặc làm môi trường khác nhau.

Nếu cần sửa, tạo migration mới, ví dụ `V007__correct_payment_status_constraint.sql`. Migration mới mô tả trạng thái chuyển tiếp từ schema hiện tại sang trạng thái mong muốn.

Trong quá trình phát triển cục bộ trước khi migration được chia sẻ hoặc chạy ở môi trường dùng chung, nhóm có thể gộp/sắp xếp lại migration theo quy ước nội bộ. Sau khi migration được phát hành, phải giữ lịch sử ổn định.

### 3.3. Review migration như review code

Pull request database nên cho reviewer biết:

- Object nào được thêm/sửa/xóa.
- Có thay đổi dữ liệu hiện có không.
- Có lock hoặc table rewrite không.
- Index tạo online hay offline và có cần thời gian dài không.
- Có ảnh hưởng đến package/view/trigger phụ thuộc không.
- Có cần grant/revoke quyền không.
- Kịch bản ứng dụng cũ và mới có tương thích trong giai đoạn rollout không.
- Nếu thất bại thì trạng thái database sẽ như thế nào.

Không nên chỉ đính kèm ảnh chụp màn hình SQL Developer. Migration cần được lưu thành file có thể review, chạy lại trên môi trường mới và truy vết trong Git.

## 4. Công cụ migration: Flyway và Liquibase

Hai công cụ thường gặp trong hệ sinh thái Java là Flyway và Liquibase. Cả hai quản lý lịch sử thay đổi database, nhưng mô hình cấu hình và changelog khác nhau.

### 4.1. Flyway

Flyway thường dùng versioned migration với quy ước tên file như:

```text
V1__create_customer_table.sql
V2__create_order_table.sql
V3__add_order_status.sql
```

Flyway lưu lịch sử migration trong schema history table (mặc định thường là `flyway_schema_history`). Khi chạy, nó xác định migration nào đã áp dụng, migration nào còn thiếu và kiểm tra checksum theo cấu hình.

Repeatable migration thường có dạng:

```text
R__order_api_package.sql
R__reporting_views.sql
```

Repeatable migration được chạy lại khi checksum thay đổi, thường dùng cho object mà toàn bộ định nghĩa có thể thay thế bằng `CREATE OR REPLACE`, như view hoặc package. Versioned migration và repeatable migration có vai trò khác nhau; không nên dùng repeatable để thay thế migration cấu trúc có trạng thái chuyển tiếp.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  flyway:
    enabled: true
    locations: classpath:db/migration/oracle
    schemas: APP_OWNER
    default-schema: APP_OWNER
    validate-on-migrate: true
```

Tên property và khả năng cụ thể phụ thuộc phiên bản Spring Boot/Flyway. Cần dùng cấu hình phù hợp với dependency đang triển khai.

### 4.2. Liquibase

Liquibase quản lý thay đổi qua changelog. Changelog có thể viết bằng XML, YAML, JSON hoặc SQL format. Mỗi changeSet có id, author và nội dung thay đổi.

Ví dụ YAML đơn giản:

```yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customers
      author: database-team
      changes:
        - createTable:
            tableName: customers
            columns:
              - column:
                  name: customer_id
                  type: NUMBER(12)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_name
                  type: VARCHAR2(200)
                  constraints:
                    nullable: false
```

Liquibase lưu trạng thái trong các bảng như `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`. Với SQL/PLSQL đặc thù Oracle, có thể dùng SQL changeset hoặc `sqlFile` để giữ cú pháp nguyên bản.

### 4.3. So sánh khái quát

| Tiêu chí | Flyway | Liquibase |
|---|---|---|
| Mô hình chính | Migration file theo version và repeatable | Changelog gồm changeSet |
| Cách mô tả | SQL là cách dùng phổ biến | SQL hoặc XML/YAML/JSON |
| Lịch sử | Schema history table | DATABASECHANGELOG và DATABASECHANGELOGLOCK |
| Rollback | Phụ thuộc edition/tính năng và script/chiến lược | Có thể khai báo rollback cho changeSet, nhưng không phải mọi thao tác Oracle đều rollback được |
| Phù hợp với SQL Oracle đặc thù | Tự nhiên khi dùng SQL migration | Có thể dùng SQL changeset/sqlFile |
| Khả năng mô tả độc lập database | Tập trung migration SQL hoặc Java | Có abstraction changeset đa database |

Việc chọn tool phụ thuộc đội ngũ, quy trình release, mức độ dùng SQL Oracle đặc thù và hệ thống hiện tại. Không nên chạy đồng thời hai migration tool trên cùng schema nếu không có thiết kế ownership rõ ràng.

## 5. Đặc tính Oracle DDL và hệ quả cho migration

Oracle tự commit trước khi thực hiện nhiều DDL statement và commit sau khi DDL thành công. Do đó, một migration có DDL và DML không nhất thiết là một transaction có thể rollback toàn bộ.

Ví dụ:

```sql
UPDATE app.orders
SET order_status = 'PAID'
WHERE order_status = 'P';

ALTER TABLE app.orders ADD payment_reference VARCHAR2(100);

ROLLBACK;
```

Trước khi chạy DDL `ALTER TABLE`, Oracle có thể commit DML `UPDATE`. `ROLLBACK` cuối không khôi phục các dòng đã cập nhật. Đây là khác biệt lớn so với một số database nơi người phát triển quen kỳ vọng DDL nằm trong transaction.

### 5.1. Không thiết kế migration dựa trên rollback DDL

Đối với Oracle, hãy giả định DDL đã thực hiện thành công là thay đổi đã commit. Nếu migration thất bại sau một số DDL, schema có thể ở trạng thái một phần. Quy trình triển khai cần:

- Xác định statement nào đã thành công.
- Kiểm tra object hiện tại và migration history.
- Không chạy lại mù quáng script có DDL không idempotent.
- Tạo migration sửa tiếp hoặc thực hiện thao tác phục hồi được phê duyệt.
- Ghi nhận trạng thái để môi trường khác không bị lệch.

### 5.2. DDL có thể làm invalid object phụ thuộc

Thay đổi bảng có thể làm view, package, trigger hoặc function phụ thuộc chuyển sang trạng thái `INVALID`. Oracle có thể tự động compile lại một số object khi được sử dụng, nhưng compile có thể thất bại nếu source PL/SQL không còn tương thích.

Sau migration ảnh hưởng đến object phụ thuộc, cần kiểm tra `USER_OBJECTS`/`DBA_OBJECTS`, xem compile errors và compile lại theo dependency order khi cần.

### 5.3. DDL lock và thời gian triển khai

Một số DDL cần lock metadata hoặc có thể scan/rewrite dữ liệu. Ví dụ thêm constraint, thay đổi datatype, tạo index hoặc move table có thể ảnh hưởng session đang truy cập object. Cần đánh giá thời gian chạy trên dữ liệu có kích thước gần production.

Các tùy chọn online như `CREATE INDEX ONLINE` hoặc `ALTER TABLE ...` với khả năng online phụ thuộc edition, version, loại object và thao tác. Không nên thêm `ONLINE` theo thói quen mà chưa xác nhận hỗ trợ.

## 6. Tổ chức migration DDL theo dependency

Object Oracle có quan hệ phụ thuộc. Bảng cần tồn tại trước foreign key; package body cần package spec; view cần bảng hoặc view nguồn; trigger cần bảng; synonym cần object đích hoặc có thể được tạo trước nhưng việc phân giải sẽ phụ thuộc object.

Một thứ tự thường gặp:

1. User/schema, tablespace/quota và grant cần thiết.
2. Sequence hoặc identity strategy.
3. Bảng nền và cột.
4. Primary key, unique constraint và check constraint.
5. Foreign key theo quan hệ parent-child.
6. Index bổ sung.
7. View và materialized view.
8. Type, package specification và package body.
9. Procedure/function độc lập.
10. Trigger, synonym và grant cho runtime role.
11. Dữ liệu tham chiếu cần thiết cho ứng dụng.

Thứ tự cụ thể phụ thuộc dependency. Ví dụ package spec có thể tham chiếu type; package body có thể tham chiếu package khác. Hãy tạo dependency graph khi schema phức tạp.

### 6.1. Tạo bảng trước constraint tham chiếu

Nếu `ORDERS` tham chiếu `CUSTOMERS`, phải tạo bảng `CUSTOMERS` trước khi tạo foreign key trên `ORDERS`.

```sql
CREATE TABLE customers (
    customer_id NUMBER(12) CONSTRAINT pk_customers PRIMARY KEY,
    customer_name VARCHAR2(200) NOT NULL
);
```

```sql
CREATE TABLE orders (
    order_id NUMBER(12) CONSTRAINT pk_orders PRIMARY KEY,
    customer_id NUMBER(12) NOT NULL,
    order_date DATE NOT NULL
);
```

```sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id);
```

Tách constraint thành migration riêng có thể hữu ích khi migration cần tạo dữ liệu nền, validate hoặc kiểm soát lock. Với schema mới, cũng có thể khai báo constraint ngay trong `CREATE TABLE` nếu dependency đã sẵn sàng.

### 6.2. Package specification trước package body

Package spec công bố API; package body chứa implementation. Khi tạo mới, spec phải tồn tại trước body:

```sql
CREATE OR REPLACE PACKAGE app.order_api AS
    PROCEDURE mark_paid(p_order_id IN NUMBER);
END order_api;
/
```

```sql
CREATE OR REPLACE PACKAGE BODY app.order_api AS
    PROCEDURE mark_paid(p_order_id IN NUMBER) IS
    BEGIN
        UPDATE app.orders
        SET order_status = 'PAID'
        WHERE order_id = p_order_id;
    END mark_paid;
END order_api;
/
```

Trong script chạy bằng SQL*Plus/SQLcl, dấu `/` trên dòng riêng gửi PL/SQL block đã buffer để thực thi. Khi chạy bằng JDBC hoặc migration tool, delimiter handling có thể khác. Cần cấu hình tool để không gửi dấu `/` như một phần SQL text và không cắt package body tại dấu chấm phẩy bên trong.

### 6.3. Compile và kiểm tra PL/SQL

`CREATE OR REPLACE` có thể tạo object ở trạng thái `INVALID` nếu compile errors. Script không nên chỉ dựa vào việc DDL không ném exception để kết luận package hoạt động.

Kiểm tra object:

```sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE object_type IN ('PACKAGE', 'PACKAGE BODY', 'PROCEDURE', 'FUNCTION', 'TRIGGER')
ORDER BY object_name, object_type;
```

Xem lỗi compile:

```sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
ORDER BY name, type, sequence;
```

Có thể compile lại package:

```sql
ALTER PACKAGE app.order_api COMPILE SPECIFICATION;
ALTER PACKAGE app.order_api COMPILE BODY;
```

Nếu compile lỗi do direct privilege hoặc dependency chưa có, phải sửa nguyên nhân. Không cấp quyền rộng như `SELECT ANY TABLE` chỉ để làm package compile được.

## 7. Version control cho PL/SQL

PL/SQL source nên được lưu thành file riêng, có tên phản ánh schema và object. Ví dụ:

```text
database/oracle/plsql/
  packages/
    order_api.pks.sql
    order_api.pkb.sql
    customer_api.pks.sql
    customer_api.pkb.sql
  procedures/
    reconcile_orders.sql
  functions/
    calculate_tax.sql
  triggers/
    orders_biu.sql
```

`.pks.sql` thường dùng cho package specification; `.pkb.sql` cho package body. Đây là convention của repository, không phải phần mở rộng bắt buộc của Oracle.

### 7.1. Một object, một nguồn sự thật

Tránh lưu nhiều bản package giống nhau trong nhiều thư mục release mà không xác định bản nào là canonical. Nếu cùng một package được tạo từ nhiều script khác nhau, deployment có thể vô tình ghi đè implementation mới bằng bản cũ.

Nên có một nguồn định nghĩa chính cho mỗi object và quy định rõ cách migration tool sử dụng nó:

- Versioned migration chứa nội dung thay đổi một lần.
- Repeatable migration chứa định nghĩa đầy đủ của object có thể replace.
- Changelog include file PL/SQL theo thứ tự dependency.

Không nên vừa tạo package body trong versioned migration, vừa có repeatable file cùng object mà không có thứ tự rõ. Nếu cả hai cùng chạy, kết quả cuối phụ thuộc thứ tự execution.

### 7.2. Versioned hay repeatable cho PL/SQL?

Có hai cách phổ biến:

**Versioned migration:** mỗi thay đổi package có version riêng. Lịch sử cho biết package được sửa ở release nào. Cách này phù hợp khi muốn mọi thay đổi là bước chuyển trạng thái bất biến.

**Repeatable migration:** file chứa toàn bộ định nghĩa package/view. Khi checksum thay đổi, tool chạy lại `CREATE OR REPLACE`. Cách này thuận tiện với object có định nghĩa thay thế toàn bộ.

Lựa chọn phụ thuộc tool và chính sách release. Với repeatable migration, cần bảo đảm file luôn chứa định nghĩa đầy đủ và chạy sau versioned migration cần thiết. Với versioned migration, không sửa file đã chạy.

### 7.3. Tách spec và body

Tách package spec và body giúp review API thay đổi riêng với implementation. Thay đổi spec có thể invalid các caller phụ thuộc và làm tăng phạm vi recompile; thay đổi body thường ít ảnh hưởng compile dependency hơn, dù vẫn có thể tạo invalidation/compile behavior theo object dependency.

Nếu chỉ thay implementation, không cần thay package spec. Điều này giúp hạn chế compile cascade và giữ API ổn định.

### 7.4. PL/SQL compile settings

Một số package phụ thuộc compiler settings, conditional compilation hoặc session/environment settings. Nếu repository cần kiểm soát, hãy lưu cấu hình compile cần thiết và đảm bảo pipeline dùng cùng database version/setting.

Không hard-code path hoặc credential môi trường vào PL/SQL. Dùng configuration table, secure application context hoặc cơ chế secret/config phù hợp, có kiểm soát quyền truy cập.

## 8. Quản lý dữ liệu tham chiếu bằng migration

Dữ liệu tham chiếu thường được ứng dụng dùng như một phần của contract. Nếu Java code bắt đầu gửi status `REFUNDED` nhưng bảng `ORDER_STATUSES` chưa có giá trị đó ở production, thao tác có thể lỗi foreign key hoặc validation.

Vì vậy, thay đổi code và reference data phải được triển khai đồng bộ theo thứ tự an toàn.

### 8.1. Seed reference data bằng INSERT

Ví dụ bảng:

```sql
CREATE TABLE order_statuses (
    status_code VARCHAR2(20) CONSTRAINT pk_order_statuses PRIMARY KEY,
    status_name VARCHAR2(100) NOT NULL,
    is_terminal CHAR(1) DEFAULT 'N' NOT NULL,
    CONSTRAINT ck_order_status_terminal CHECK (is_terminal IN ('Y', 'N'))
);
```

Seed:

```sql
INSERT INTO order_statuses(status_code, status_name, is_terminal)
VALUES ('NEW', 'New order', 'N');

INSERT INTO order_statuses(status_code, status_name, is_terminal)
VALUES ('PAID', 'Paid', 'N');

INSERT INTO order_statuses(status_code, status_name, is_terminal)
VALUES ('CANCELLED', 'Cancelled', 'Y');
```

Đây là migration dữ liệu một lần. Khi chạy ở schema mới, nó tạo các dòng ban đầu. Khi chạy lại trên schema đã có dữ liệu, primary key sẽ ngăn insert trùng. Đó có thể là điều mong muốn nếu versioned migration phải chạy đúng một lần.

### 8.2. MERGE cho dữ liệu tham chiếu cần đồng bộ

Nếu dữ liệu tham chiếu được cập nhật lặp lại theo trạng thái chuẩn, `MERGE` có thể đồng bộ:

```sql
MERGE INTO order_statuses t
USING (
    SELECT 'NEW' AS status_code, 'New order' AS status_name, 'N' AS is_terminal FROM dual
    UNION ALL
    SELECT 'PAID', 'Paid', 'N' FROM dual
    UNION ALL
    SELECT 'CANCELLED', 'Cancelled', 'Y' FROM dual
) s
ON (t.status_code = s.status_code)
WHEN MATCHED THEN
    UPDATE SET
        t.status_name = s.status_name,
        t.is_terminal = s.is_terminal
WHEN NOT MATCHED THEN
    INSERT (status_code, status_name, is_terminal)
    VALUES (s.status_code, s.status_name, s.is_terminal);
```

`MERGE` phù hợp khi định nghĩa dữ liệu chuẩn cần được áp lại. Tuy nhiên, nếu production cho phép người quản trị sửa mô tả hoặc thuộc tính tham chiếu, `MERGE` có thể ghi đè thay đổi đó. Cần xác định rõ cột nào do code sở hữu và cột nào do vận hành quản lý.

### 8.3. Dữ liệu tham chiếu immutable và dữ liệu cấu hình

Không phải mọi bảng lookup đều nên bị migration ghi đè. Có thể phân loại:

- **Immutable reference:** mã trạng thái hoặc loại dữ liệu do sản phẩm định nghĩa; thay đổi thông qua migration.
- **Operational configuration:** ngưỡng, endpoint, feature flag hoặc tham số được vận hành thay đổi; quản lý qua công cụ cấu hình riêng.
- **Business-maintained catalog:** danh mục do người dùng/quản trị nghiệp vụ duy trì; không seed lại bằng migration mỗi lần deploy.

Phân loại này tránh tình huống migration mới vô tình ghi đè cấu hình production hợp lệ.

### 8.4. Không xóa mã tham chiếu đang được sử dụng

Nếu status `CANCELLED` đã được dùng trong hàng triệu dòng đơn hàng, xóa status khỏi bảng lookup có thể vi phạm foreign key hoặc làm mất ý nghĩa lịch sử. Thông thường nên đánh dấu không còn sử dụng (`ACTIVE = 'N'`) thay vì delete.

Nếu thật sự cần xóa, phải kiểm tra toàn bộ foreign key, dữ liệu lịch sử, báo cáo, package và code downstream. Thay đổi mã tham chiếu là thay đổi contract, không chỉ là xóa một dòng seed.

## 9. Data migration cho dữ liệu hiện có

Khi schema thay đổi, dữ liệu cũ có thể cần chuyển đổi. Ví dụ đổi `ORDER_STATUS` từ mã một ký tự sang mã đầy đủ.

### 9.1. Migration đơn giản

```sql
UPDATE orders
SET order_status = CASE order_status
    WHEN 'N' THEN 'NEW'
    WHEN 'P' THEN 'PAID'
    WHEN 'C' THEN 'CANCELLED'
    ELSE order_status
END
WHERE order_status IN ('N', 'P', 'C');

COMMIT;
```

Với data migration lớn, cần ước lượng số dòng, undo/redo, thời gian lock và khả năng chạy lại. Nếu migration có thể chạy lại, điều kiện phải giới hạn chính xác các dòng chưa chuyển đổi.

### 9.2. Migration theo nhiều giai đoạn

Thay đổi lớn nên chia thành các bước tương thích:

1. Thêm cột mới nullable.
2. Deploy code có thể đọc cột cũ và mới, nhưng vẫn ghi theo cách tương thích.
3. Backfill dữ liệu cũ theo batch.
4. Chuyển code sang ghi/đọc cột mới.
5. Xác nhận không còn consumer dùng cột cũ.
6. Thêm constraint/NOT NULL nếu cần.
7. Xóa cột cũ ở release sau.

Cách này thường được gọi là expand-and-contract. Nó giảm rủi ro khi ứng dụng có nhiều instance và không thể dừng toàn bộ để deploy schema và code cùng một thời điểm.

### 9.3. Backfill theo batch

Không nên luôn chạy một `UPDATE` khổng lồ trên bảng rất lớn trong giờ cao điểm. Có thể chia thành chunk theo primary key hoặc partition:

```sql
UPDATE orders
SET normalized_status = order_status
WHERE order_id >= :from_id
  AND order_id < :to_id
  AND normalized_status IS NULL;
```

Job điều phối chọn các khoảng khóa, commit từng batch và ghi checkpoint. Cần xác định:

- Batch size.
- Thời gian nghỉ giữa batch.
- Cách tiếp tục sau lỗi.
- Số dòng đã xử lý và số dòng còn lại.
- Tác động đến index, undo, redo và replication.

Nếu backfill cần chạy đồng thời với ứng dụng, phải bảo đảm code mới không ghi giá trị không tương thích và không bỏ sót dòng được tạo/cập nhật trong lúc backfill.

### 9.4. Đối soát sau data migration

Sau chuyển đổi, so sánh số dòng theo từng trạng thái, kiểm tra NULL, key và aggregate. Ví dụ:

```sql
SELECT order_status, COUNT(*)
FROM orders
GROUP BY order_status
ORDER BY order_status;
```

Có thể lưu count trước/sau và kết quả validation trong deployment log. Chỉ đánh dấu migration hoàn tất khi các điều kiện dữ liệu mong đợi đã đạt.

## 10. Versioning GRANT, role và quyền database

Quyền cũng là một phần của schema contract. Nếu package mới cần đọc bảng khác schema, migration cần cấp direct object privilege phù hợp cho owner của package. Nếu runtime user cần gọi package, cần grant `EXECUTE` hoặc role tương ứng.

Ví dụ:

```sql
GRANT SELECT, INSERT, UPDATE
ON data_owner.orders
TO app_owner;

GRANT EXECUTE
ON app_owner.order_api
TO app_runtime_role;
```

Không nên cấp quyền quản trị rộng như `DBA`, `SELECT ANY TABLE` hoặc `CREATE ANY PROCEDURE` chỉ để tránh lỗi triển khai. Hãy cấp đúng privilege theo object và ngữ cảnh thực thi.

### 10.1. Direct grant cho stored PL/SQL

Với definer-rights PL/SQL, role của session bị vô hiệu hóa trong lúc thực thi unit. Nếu package owner cần truy cập object ở schema khác, hãy grant trực tiếp cho owner theo yêu cầu. Vì vậy, migration GRANT cần nằm trước migration compile package hoặc trước khi package được gọi.

### 10.2. GRANT và REVOKE phải được review

Thay đổi quyền có thể làm mở rộng hoặc thu hẹp bề mặt truy cập. Review cần hỏi:

- Grantee là user, role hay `PUBLIC`?
- Object nào được truy cập?
- Privilege có cấp theo cột được không?
- Có cần `WITH GRANT OPTION` hoặc `WITH ADMIN OPTION` không?
- Runtime user có thực sự cần quyền DDL không?
- Có quyền cũ cần revoke không và ảnh hưởng chuỗi grant thế nào?

### 10.3. Quản lý quyền theo môi trường

Một số grant giống nhau ở mọi môi trường; một số quyền hoặc directory path khác nhau theo môi trường. Không nên tạo một migration chung chứa password, host, path hoặc user quản trị khác nhau theo từng nơi. Dùng placeholder/configuration được quản lý hoặc script bootstrap riêng có review.

## 11. Repeatable migration và CREATE OR REPLACE

Các object như view, package, procedure và function thường có thể được thay bằng `CREATE OR REPLACE`. Đây là lý do chúng phù hợp với repeatable migration trong một số công cụ.

Ví dụ view:

```sql
CREATE OR REPLACE VIEW app.v_paid_orders AS
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM app.orders
WHERE order_status = 'PAID';
```

Ví dụ package body:

```sql
CREATE OR REPLACE PACKAGE BODY app.order_api AS
    PROCEDURE mark_paid(p_order_id IN NUMBER) IS
    BEGIN
        UPDATE app.orders
        SET order_status = 'PAID'
        WHERE order_id = p_order_id;
    END mark_paid;
END order_api;
/
```

### 11.1. Cẩn trọng với replace

`CREATE OR REPLACE` không phải lúc nào cũng hoàn toàn không tác động. Thay package spec có thể invalid các dependent object. Thay view có thể làm thay đổi contract của client nếu số cột hoặc kiểu dữ liệu đổi. Thay trigger có thể làm thay đổi side effect của DML.

Vì vậy, repeatable migration không có nghĩa có thể thay bất kỳ định nghĩa nào mà không cần versioning/review. Thay đổi API public cần được xem như thay đổi tương thích ứng dụng.

### 11.2. Compile errors và warning

Sau khi deploy PL/SQL, kiểm tra object status và `USER_ERRORS`/`DBA_ERRORS`. Một số lỗi compile có thể chỉ xuất hiện khi dependency hoặc privilege chưa sẵn sàng. Pipeline nên fail nếu object bắt buộc còn `INVALID` hoặc có lỗi compile.

## 12. SQL*Plus, SQLcl và delimiter PL/SQL

Oracle SQL script có một số đặc điểm khi chạy qua command-line client:

- DML kết thúc bằng dấu `;`.
- PL/SQL block thường kết thúc bằng `END;` rồi dùng `/` trên dòng riêng để gửi block.
- `/` là lệnh của SQL*Plus/SQLcl, không phải token SQL gửi tới database.
- Migration tool có thể có quy tắc riêng để nhận biết statement delimiter.

Ví dụ script:

```sql
CREATE OR REPLACE PROCEDURE app.rebuild_summary AS
BEGIN
    NULL;
END;
/
```

Nếu migration tool không nhận biết slash delimiter, nó có thể gửi cả `/` vào JDBC statement và gây lỗi cú pháp. Nếu tool cắt tại mọi dấu `;`, package body sẽ bị chia thành nhiều statement sai. Cần cấu hình delimiter hoặc statement splitting theo hướng dẫn của tool và dùng integration test để chạy script thực tế.

### 12.1. Không trộn SQL*Plus command vào JDBC SQL

Các lệnh như `SET SERVEROUTPUT ON`, `PROMPT`, `WHENEVER SQLERROR`, `SPOOL` là lệnh client, không phải SQL gửi qua JDBC. Một file chạy được bằng SQLcl chưa chắc chạy nguyên văn qua Flyway/Liquibase JDBC.

Nếu cần chạy script bằng SQL*Plus/SQLcl, ghi rõ tool trong deployment pipeline. Nếu cần chạy bằng migration tool JDBC, giữ file theo cú pháp mà tool hỗ trợ.

## 13. Kiểm tra schema sau migration

Migration history cho biết tool đã chạy file nào, nhưng không luôn chứng minh mọi object ở database còn đúng định nghĩa. Một DBA có thể sửa thủ công sau migration hoặc deployment có thể bị gián đoạn.

### 13.1. Kiểm tra object status

```sql
SELECT object_type,
       status,
       COUNT(*) AS object_count
FROM user_objects
GROUP BY object_type, status
ORDER BY object_type, status;
```

Tìm object invalid:

```sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
```

### 13.2. Kiểm tra constraint

```sql
SELECT table_name,
       constraint_name,
       constraint_type,
       status,
       validated
FROM user_constraints
ORDER BY table_name, constraint_type, constraint_name;
```

### 13.3. Kiểm tra index

```sql
SELECT index_name,
       table_name,
       status,
       uniqueness
FROM user_indexes
ORDER BY table_name, index_name;
```

### 13.4. Kiểm tra migration history

Với Flyway, xem schema history table theo schema/cấu hình của dự án. Với Liquibase, xem `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`. Các bảng này là metadata của tool; không sửa thủ công để ép migration pass nếu chưa hiểu trạng thái thực tế.

### 13.5. Schema drift

Schema drift là khác biệt giữa database thực tế và định nghĩa mong đợi trong repository. Drift có thể phát sinh từ:

- Hotfix thủ công trên production không được commit lại.
- Script chạy ngoài migration tool.
- Migration chạy ở môi trường này nhưng không chạy ở môi trường khác.
- Người vận hành thay đổi grant, index hoặc package.
- Tool history bị chỉnh sửa hoặc database được restore từ snapshot khác thời điểm.

Để kiểm soát drift, cần hạn chế DDL trực tiếp, audit thay đổi, định kỳ so sánh metadata/DDL và đưa hotfix vào Git bằng migration tương ứng. Không nên tự động ghi đè production chỉ vì schema diff báo khác; trước tiên phải hiểu vì sao khác và đánh giá tác động.

## 14. Rollback, roll forward và khôi phục sau lỗi

Rollback database thường phức tạp hơn rollback ứng dụng vì schema/data có thể đã được thay đổi và có transaction mới sử dụng cấu trúc đó.

### 14.1. Rollback script không phải lúc nào cũng an toàn

Ví dụ migration thêm cột:

```sql
ALTER TABLE orders ADD payment_reference VARCHAR2(100);
```

Rollback có thể là:

```sql
ALTER TABLE orders DROP COLUMN payment_reference;
```

Nhưng nếu ứng dụng mới đã ghi dữ liệu vào cột đó, rollback sẽ làm mất dữ liệu. Vì vậy, việc có thể viết câu DDL ngược không có nghĩa rollback an toàn về mặt nghiệp vụ.

### 14.2. Roll forward

Với Oracle production, chiến lược thường an toàn hơn là tạo migration mới để sửa trạng thái hiện tại:

```sql
-- V008__correct_payment_reference_length.sql
ALTER TABLE orders MODIFY payment_reference VARCHAR2(200);
```

Migration mới ghi lại thay đổi và giữ lịch sử. Nếu migration trước đã chạy ở một số môi trường, không sửa file cũ để chúng có lịch sử khác nhau.

### 14.3. Phân biệt rollback ứng dụng và rollback database

Có thể rollback phiên bản Java trong khi schema vẫn giữ cột mới nếu schema thay đổi theo hướng backward compatible. Đây là lợi ích của expand-and-contract.

Ví dụ:

1. Thêm cột nullable `PAYMENT_REFERENCE`.
2. Deploy code mới có thể ghi cột mới nhưng code cũ vẫn bỏ qua được.
3. Chuyển traffic và xác nhận.
4. Chỉ ở release sau mới xóa cột cũ hoặc siết constraint.

Nếu schema thay đổi phá vỡ code cũ ngay lập tức, rollback ứng dụng có thể không chạy được. Do đó cần đánh giá tương thích giữa phiên bản ứng dụng N và N-1.

### 14.4. DDL thất bại giữa chừng

Nếu migration có nhiều DDL và thất bại ở statement thứ ba, hai statement trước có thể đã commit. Quy trình xử lý:

1. Dừng deploy để tránh môi trường tiếp tục nhận migration phụ thuộc.
2. Xem log tool và xác định statement cuối cùng thành công.
3. Kiểm tra object/constraint/index thực tế trong Oracle.
4. Xác định migration history có ghi nhận failed hay chưa.
5. Tạo kế hoạch repair/forward-fix phù hợp.
6. Chỉ chạy lại sau khi trạng thái schema đã được đưa về trạng thái dự kiến.
7. Ghi nhận incident và cập nhật migration/test nếu cần.

Không xóa row trong migration history table hoặc chạy lại script nhiều lần theo kiểu thử-sai trên production.

## 15. Expand-and-contract cho deploy không downtime

Khi ứng dụng có nhiều instance hoặc cần rolling deployment, database và application code có thể tồn tại song song ở nhiều version. Migration nên bảo đảm code cũ và code mới cùng hoạt động trong giai đoạn chuyển tiếp.

### 15.1. Thêm cột mới

Giả sử đổi từ `CUSTOMER_NAME` sang `DISPLAY_NAME`:

**Expand:**

```sql
ALTER TABLE customers ADD display_name VARCHAR2(200);
```

Deploy code có thể đọc `DISPLAY_NAME` nếu có, nếu chưa có thì fallback `CUSTOMER_NAME`; khi ghi, có thể ghi cả hai cột trong thời gian chuyển tiếp.

Backfill dữ liệu:

```sql
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL;

COMMIT;
```

Sau khi tất cả instance code mới đã chạy và dữ liệu được đối soát, chuyển read/write hoàn toàn sang `DISPLAY_NAME`.

**Contract:** ở release sau, xác nhận không còn consumer sử dụng `CUSTOMER_NAME`, rồi mới drop cột cũ.

### 15.2. Thêm NOT NULL an toàn

Thêm cột `NOT NULL` vào bảng lớn có thể cần default/backfill và có tác động tùy phiên bản. Một cách triển khai theo giai đoạn:

1. Thêm cột nullable.
2. Deploy code luôn ghi giá trị mới.
3. Backfill các dòng cũ theo batch.
4. Kiểm tra không còn NULL.
5. Thêm constraint hoặc sửa cột thành NOT NULL theo cách phù hợp version/workload.

Điều này giúp tránh một lần thay đổi lớn bất ngờ trong giờ cao điểm.

### 15.3. Thay đổi enum/reference data

Nếu Java code cần status mới `REFUNDED`, hãy thêm mã vào bảng tham chiếu trước khi deploy code bắt đầu ghi status đó. Nếu code mới chạy trước khi seed, foreign key hoặc validation có thể từ chối dữ liệu.

Khi xóa status cũ, cần chờ mọi instance và consumer ngừng sử dụng nó. Đây cũng là expand-and-contract ở mức reference data.

## 16. Quản lý dữ liệu tham chiếu theo môi trường

Reference data có thể khác nhau giữa môi trường. Ví dụ một số mã test chỉ có ở development/test, trong khi production có mã nghiệp vụ được cấu hình bởi bộ phận vận hành.

Nên chia:

- **Seed chung:** mã bắt buộc để ứng dụng hoạt động giống nhau ở mọi môi trường.
- **Seed test-only:** dữ liệu fixture không được triển khai production.
- **Environment-specific configuration:** giá trị khác nhau theo environment, được inject từ config/secret hoặc migration parameter được kiểm soát.
- **Operationally managed data:** dữ liệu do admin/nghiệp vụ quản lý, không bị migration ghi đè.

Không đưa mật khẩu, endpoint production, API key hoặc dữ liệu cá nhân thật vào seed script. Dùng dữ liệu giả và domain dành riêng cho test.

### 16.1. Dữ liệu seed phải có ownership

Mỗi bảng reference nên xác định ai là owner của dữ liệu:

| Dữ liệu | Owner | Cách thay đổi |
|---|---|---|
| Order status do code quy định | Development/database team | Migration có version |
| Feature flag vận hành | Operations/product | Config management hoặc admin UI |
| Country list theo nguồn chuẩn | Data governance | Import/versioned reference process |
| Test customer/order | Test suite | Fixture riêng, cleanup sau test |

Nếu không có ownership, migration và thao tác admin có thể ghi đè lẫn nhau.

### 16.2. Không hard-code ID tự tăng cho mọi reference

Với reference code có ý nghĩa ổn định, dùng natural code như `PAID`, `CANCELLED` thường dễ triển khai hơn ID sequence thay đổi theo môi trường. Nếu schema dùng surrogate key, hãy bảo đảm mapping code-to-ID được tạo đồng nhất và ứng dụng không giả định ID cụ thể giữa các môi trường trừ khi đó là contract được quản lý.

## 17. Quy trình CI/CD cho database migration

Một pipeline cơ bản có thể gồm:

```text
Developer tạo migration trong Git
              |
              v
       Pull request review
              |
              v
   Static checks / SQL linting
              |
              v
 Provision Oracle test database
              |
              v
   Run all migrations from zero
              |
              v
    Run upgrade from prior version
              |
              v
     Compile PL/SQL and validate
              |
              v
       Seed and integration tests
              |
              v
     Build deployment artifact
              |
              v
   Deploy to staging / approval
              |
              v
       Deploy to production
              |
              v
   Verify history, objects and app
```

### 17.1. Kiểm tra từ database rỗng

Tạo database/schema mới và chạy toàn bộ migration từ đầu giúp phát hiện:

- Migration bị thiếu dependency.
- File PL/SQL không chạy đúng delimiter.
- Seed reference bị thiếu.
- Grant không đủ.
- Script phụ thuộc object tồn tại từ trước nhưng không được tạo trong repository.

### 17.2. Kiểm tra upgrade từ version cũ

Chỉ dựng mới từ zero là chưa đủ. Production thường chứa dữ liệu và schema ở version cũ. Pipeline nên restore/cloning một database có cấu trúc và lượng dữ liệu đại diện, sau đó chạy migration từ version cũ lên version mới.

Điều này phát hiện lock lâu, data conversion lỗi, constraint không thể validate và thời gian backfill không phù hợp.

### 17.3. Kiểm tra PL/SQL sau migration

Pipeline có thể truy vấn `USER_OBJECTS` và `USER_ERRORS` để fail nếu package/view/procedure quan trọng còn invalid hoặc compile errors. Sau đó chạy smoke test gọi các API database quan trọng.

### 17.4. Không để mọi application instance tự chạy migration

Nếu mỗi instance Spring Boot cùng khởi động và tự chạy migration, cần bảo đảm migration tool có locking và chỉ một tiến trình thực hiện thay đổi tại một thời điểm. Trong production, nhiều tổ chức chọn một deployment job riêng để chạy migration trước khi rollout application. Cách này tách quyền DDL khỏi runtime account và dễ kiểm soát thời điểm triển khai.

Runtime user thường không cần quyền `CREATE TABLE`, `ALTER TABLE` hoặc `DROP TABLE`. Tách migration user và runtime user giúp giảm quyền ứng dụng.

## 18. Deployment an toàn theo nhiều môi trường

Development, test, staging và production cần nhận cùng migration artifact nhưng có cấu hình kết nối/quyền riêng.

| Môi trường | Mục đích | Kiểm soát |
|---|---|---|
| Local development | Developer thử thay đổi | Schema riêng, reset nhanh, dữ liệu giả |
| CI database | Kiểm tra tự động | Dựng mới và upgrade test, tự hủy sau run |
| Integration/test | Kiểm thử nhiều service | Migration đồng nhất, seed có kiểm soát |
| Staging | Mô phỏng production | Data volume/structure gần production, deployment rehearsal |
| Production | Dữ liệu thật | Change approval, backup/restore plan, monitoring và runbook |

### 18.1. Cùng artifact, cấu hình khác nhau

Migration nên mô tả thay đổi schema giống nhau trên các môi trường. Những giá trị như host, password, directory path hoặc tablespace đặc thù cần được quản lý bằng configuration/placeholder theo chính sách của tool.

Tránh sửa file migration thủ công cho riêng production. Nếu cần hành vi khác nhau, dùng cấu hình có kiểm soát hoặc tách migration theo điều kiện được tài liệu hóa rõ ràng.

### 18.2. Quyền triển khai

Có thể dùng:

- Migration account có quyền DDL cần thiết.
- Runtime account chỉ có quyền DML/EXECUTE cần thiết.
- DBA/operator account cho thao tác quản trị đặc biệt.

Không lưu credential migration trong repository. CI lấy secret tại thời điểm chạy từ secret manager và không in ra log.

### 18.3. Audit và change record

Mỗi lần triển khai nên lưu:

- Git commit/tag hoặc artifact version.
- Danh sách migration đã chạy.
- Database/service/PDB target.
- Thời gian bắt đầu/kết thúc.
- Kết quả và lỗi.
- Người hoặc pipeline phê duyệt.
- Kết quả kiểm tra object, constraint và PL/SQL.

Điều này giúp liên kết thay đổi source code với thay đổi database khi điều tra incident.

## 19. Xử lý hotfix trên production

Đôi khi phải sửa lỗi khẩn cấp trực tiếp trên production theo quy trình change management. Nếu có hotfix, không để nó tồn tại ngoài Git.

Quy trình nên là:

1. Ghi nhận chính xác DDL/PLSQL đã thực hiện và người phê duyệt.
2. Lưu script hotfix vào repository ngay sau khi xử lý.
3. Tạo migration version mới mô tả trạng thái cần có ở các môi trường khác.
4. Kiểm thử migration trên bản clone hoặc staging có schema gần production.
5. Đánh dấu môi trường production đã nhận thay đổi tương ứng theo quy trình migration tool phù hợp.
6. So sánh schema để phát hiện phần khác còn sót.

Không sửa migration cũ để giả vờ rằng production đã chạy cùng lịch sử với môi trường khác. Nếu production được hotfix thủ công, cần reconciliation rõ ràng để tool history và schema state không mâu thuẫn.

## 20. Schema drift và so sánh DDL

Version control không tự ngăn drift nếu người dùng vẫn có thể chạy DDL ngoài quy trình. Cần kết hợp:

- Hạn chế quyền DDL trên production.
- Audit DDL hoặc sử dụng cơ chế change tracking phù hợp.
- So sánh DDL giữa repository và database định kỳ.
- Kiểm tra invalid object, constraint status và grants.
- Đưa mọi hotfix trở lại migration history.

Oracle cung cấp `DBMS_METADATA` để lấy DDL của object. Ví dụ:

```sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')
FROM dual;
```

Có thể dùng `DBMS_METADATA.GET_DDL` cho package, view, index và các object khác theo object type. Output cần được chuẩn hóa trước khi diff vì storage clause, tablespace, segment attributes và metadata có thể khác giữa môi trường dù logic schema tương đương.

Không nên lấy DDL production rồi ghi đè repository mà không review. Diff là bằng chứng để điều tra, không phải lệnh tự động đồng bộ an toàn.

## 21. Oracle Edition-Based Redefinition và thay đổi online

Với hệ thống yêu cầu availability cao, Oracle Edition-Based Redefinition (EBR) có thể hỗ trợ triển khai thay đổi ứng dụng/database theo edition, giảm thời gian cần dừng ứng dụng. EBR dùng edition để duy trì nhiều phiên bản PL/SQL object và editioning view theo cơ chế Oracle hỗ trợ.

EBR không phải tính năng migration tool và không phù hợp với mọi schema. Nó yêu cầu thiết kế editionable object, editioning view, cross-edition trigger hoặc cơ chế đồng bộ tương ứng tùy loại thay đổi.

Các nguyên tắc:

- Thiết kế schema có thể edition hóa từ trước.
- Xác định object nào editionable và object nào noneditionable.
- Quản lý edition và deployment order bằng script version control.
- Kiểm thử session ở edition cũ và edition mới.
- Có kế hoạch chuyển service/session sang edition mới và dọn edition cũ.

Nếu không dùng EBR, expand-and-contract vẫn là cách phổ biến để triển khai schema tương thích trong giai đoạn rolling deployment.

## 22. Quản lý index và constraint trong release

Index và constraint có thể làm thay đổi đáng kể thời gian triển khai. Một migration thêm index trên bảng lớn có thể tiêu tốn I/O, CPU và gây cạnh tranh với workload ứng dụng.

### 22.1. Tạo index

```sql
CREATE INDEX ix_orders_customer_date
    ON app.orders(customer_id, order_date);
```

Trước khi tạo, cần xem query workload, cardinality, thứ tự cột và index đã tồn tại. Không tạo index trùng hoặc gần giống mà chưa đánh giá.

Tùy phiên bản/edition và điều kiện, có thể dùng online index creation:

```sql
CREATE INDEX ix_orders_customer_date
    ON app.orders(customer_id, order_date)
    ONLINE;
```

`ONLINE` không loại bỏ mọi lock hoặc chi phí. Cần xác nhận cú pháp, giới hạn và license/edition của môi trường.

### 22.2. Thêm foreign key vào bảng đã có dữ liệu

Nếu bảng lớn đã có dữ liệu, thêm FK với validate có thể phải kiểm tra dữ liệu hiện tại. Nếu có dòng mồ côi, lệnh thất bại. Trước migration, có thể chạy truy vấn kiểm tra orphan rows và lập kế hoạch sửa dữ liệu.

Oracle hỗ trợ `ENABLE NOVALIDATE` trong một số chiến lược để enforce với DML mới mà chưa validate toàn bộ dữ liệu cũ; sau đó có thể validate riêng. Nhưng đây là trạng thái tạm và cần được theo dõi, không nên để test/production quên validate.

### 22.3. Constraint và index

Primary key/unique constraint thường dựa trên index để enforce uniqueness. Khi migration tạo constraint, Oracle có thể tạo index hoặc sử dụng index sẵn có phù hợp. Tránh tạo index trùng với index phục vụ constraint.

## 23. Các lỗi thường gặp khi version control database

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Flyway checksum mismatch | File migration đã chạy bị sửa | Khôi phục file lịch sử; tạo migration mới; chỉ repair theo quy trình có kiểm soát |
| Migration báo object already exists | Script chạy một phần hoặc môi trường drift | Kiểm tra object và history; không thêm `IF EXISTS` giả định cú pháp không hỗ trợ |
| PL/SQL object INVALID | Dependency thiếu, compile error hoặc direct privilege thiếu | Xem `USER_ERRORS`, dependency và grants |
| Package body compile lỗi sau deploy | Package spec hoặc type thay đổi không tương thích | Deploy theo dependency order và compile lại |
| FK migration thất bại | Dữ liệu cũ có orphan hoặc parent chưa được tạo | Kiểm tra dữ liệu và dependency trước khi enable validate |
| Seed duplicate key | Migration chạy lại hoặc dữ liệu đã được tạo thủ công | Xác định ownership; dùng versioned one-time insert hoặc upsert có chủ đích |
| Migration chạy ở dev nhưng lỗi production | Data volume, privilege, edition/version hoặc object state khác | Test upgrade trên bản clone có dữ liệu gần production |
| DDL chạy một phần rồi lỗi | Oracle implicit commit | Kiểm tra trạng thái từng object và tạo repair/forward migration |
| Runtime app lỗi sau khi deploy schema | Code và schema không tương thích trong rolling deployment | Dùng expand-and-contract và kiểm tra N/N-1 compatibility |
| Drift giữa môi trường | Hotfix hoặc thay đổi thủ công ngoài Git | Audit, schema diff và đưa hotfix vào migration |
| PL/SQL script bị tách sai | Migration tool không hiểu slash delimiter | Cấu hình statement splitting đúng với Oracle PL/SQL |
| Migration chạy đồng thời | Nhiều app instance cùng khởi động migration | Dùng lock của tool hoặc deployment job riêng |

## 24. Quy trình làm việc từ yêu cầu đến production

Một thay đổi database có thể đi qua các bước:

1. **Phân tích yêu cầu:** xác định object, dữ liệu, API và compatibility cần thay đổi.
2. **Thiết kế migration:** chọn DDL, data migration, PL/SQL và grants; xác định dependency.
3. **Tạo file trong Git:** đặt version, tên và thư mục theo convention.
4. **Review:** DBA/developer đánh giá lock, storage, data loss, privilege và rollback/forward strategy.
5. **Test từ zero:** dựng schema mới, chạy toàn bộ migration và seed.
6. **Test upgrade:** chạy từ version cũ với dữ liệu đại diện.
7. **Compile/validate:** kiểm tra object status, constraint và reference data.
8. **Integration test:** chạy ứng dụng với runtime account và service tương ứng.
9. **Deploy staging:** đo thời gian và kiểm tra runbook.
10. **Deploy production:** dùng migration job, credential riêng và change window phù hợp.
11. **Verify:** xem history, object status, invalid PL/SQL, data checks và ứng dụng.
12. **Reconcile:** đưa mọi hotfix hoặc thao tác vận hành phát sinh trở lại version control.

## 25. Checklist cho một pull request database

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Scope | Object nào được tạo, sửa hoặc xóa? |
| Version | Migration version có duy nhất và theo đúng convention không? |
| Immutability | File đã chạy ở môi trường dùng chung có bị sửa không? |
| Dependency | Bảng, type, package spec/body, view và grant có đúng thứ tự không? |
| DDL behavior | Có implicit commit, lock hoặc table rewrite không? |
| Data migration | Có giới hạn phạm vi, batch size, undo/redo và retry strategy không? |
| Reference data | Dữ liệu do code hay operations sở hữu; có ghi đè dữ liệu môi trường không? |
| PL/SQL | Script delimiter đúng; compile errors được kiểm tra chưa? |
| Privileges | Direct grants, roles và runtime access có tối thiểu không? |
| Compatibility | Code cũ và mới có cùng chạy được trong giai đoạn rollout không? |
| Recovery | Nếu thất bại giữa chừng, trạng thái schema được xác định và sửa thế nào? |
| Testing | Đã test từ schema mới và upgrade từ version cũ chưa? |
| Evidence | Có migration log, schema history và kết quả verify không? |
| Environment | Không chứa credential/host/path nhạy cảm trong Git chứ? |

Quản lý DDL, PL/SQL và dữ liệu tham chiếu bằng version control biến database thành một phần có thể review, kiểm thử và tái lập của sản phẩm. Với Oracle, cần thiết kế migration theo dependency, hiểu implicit commit của DDL, giữ migration đã chạy bất biến và dùng migration mới để sửa trạng thái. PL/SQL phải được triển khai đúng delimiter và compile dependency; reference data cần có ownership và thứ tự tương thích với code; data migration lớn cần batch và đối soát. Khi kết hợp Git, migration tool, CI database và quy trình deploy expand-and-contract, các môi trường sẽ nhất quán hơn và thay đổi database có thể được truy vết như thay đổi ứng dụng.
