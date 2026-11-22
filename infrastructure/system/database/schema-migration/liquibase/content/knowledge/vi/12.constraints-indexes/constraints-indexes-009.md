# Đặt tên ràng buộc, chỉ mục để hỗ trợ triển khai và hoàn tác

Trong chương **Khóa và chỉ mục** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, cách đặt tên ràng buộc (*constraint*) và chỉ mục (*index*) là một phần của thiết kế migration, không chỉ là quy tắc trình bày SQL. Khi một changeset thêm khóa chính, khóa ngoại, ràng buộc duy nhất hoặc chỉ mục, tên đối tượng sẽ được sử dụng trong lịch sử triển khai, câu lệnh gỡ bỏ, precondition, báo cáo lỗi, công cụ giám sát và quá trình xử lý schema drift.

Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và DATABASECHANGELOG. Một tên nhất quán giúp migration có thể kiểm chứng, dễ rollback và dễ triển khai qua development, staging, production, kể cả khi chạy bằng Spring Boot hoặc CI/CD. Ngược lại, để DBMS tự sinh tên ngẫu nhiên có thể khiến lệnh rollback hoặc bước sửa lỗi khó tái sử dụng giữa các database.

**Mục tiêu:** chọn tên ổn định, dễ hiểu, nằm trong giới hạn DBMS, ít va chạm và đủ chính xác để các change type Liquibase cùng thao tác trên một đối tượng qua nhiều lần triển khai.

## 1. Phân biệt ràng buộc và chỉ mục

Các khái niệm thường đi cùng nhau nhưng không đồng nhất:

| Đối tượng | Vai trò chính | Ví dụ tên có chủ đích |
|---|---|---|
| Primary key (PK) | Xác định duy nhất bản ghi, không cho phép NULL ở các cột khóa | pk_customer_account |
| Foreign key (FK) | Bảo vệ quan hệ tham chiếu tới bảng/khóa đích | fk_purchase_order_customer_account |
| Unique constraint (UQ) | Ngăn các giá trị vi phạm tính duy nhất của tập cột | uq_customer_account_email |
| Check constraint (CK) | Bảo vệ điều kiện dữ liệu, nếu DBMS hỗ trợ | ck_purchase_order_total_nonnegative |
| Default constraint | Cấp giá trị mặc định; có thể là đối tượng có tên riêng trên một số DBMS | df_purchase_order_status |
| Index (IX) | Cấu trúc truy cập phục vụ truy vấn, sắp xếp hoặc join | ix_customer_account_status_created_at |

PK và UNIQUE có thể được DBMS hỗ trợ bằng index nội bộ; FK cũng thường cần index phù hợp để tránh truy vấn/chặn khóa tốn kém. Tuy nhiên:

- **Unique constraint không luôn tương đương một unique index** về API metadata, cú pháp quản lý, điều kiện lọc hoặc cách DBMS biểu diễn.
- **Index không phải khóa ngoại**: thêm index trên customer_id không tự kiểm tra rằng customer_id tham chiếu đến một customer hợp lệ.
- **Một tên đối tượng không chứng minh định nghĩa của nó**: ix_customer_account_email có thể tồn tại nhưng lại không đánh index đúng cột email.

Các quy ước tên nên phản ánh **loại đối tượng và mục đích**, không dùng một tiền tố chung cho mọi thứ.

## 2. Vì sao tên quan trọng đối với Liquibase?

Một changeset có thể tạo khóa ngoại với tên tường minh:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-add-order-customer-fk"
      author: "team-db"
      changes:
        - addForeignKeyConstraint:
            baseTableName: purchase_order
            baseColumnNames: customer_id
            referencedTableName: customer_account
            referencedColumnNames: id
            constraintName: fk_purchase_order_customer_account
~~~

Sau này muốn gỡ ràng buộc, cần nhận diện chính xác đối tượng đã tạo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-001-drop-order-customer-fk"
      author: "team-db"
      changes:
        - dropForeignKeyConstraint:
            baseTableName: purchase_order
            constraintName: fk_purchase_order_customer_account
~~~

Nếu để DBMS tự đặt tên, mỗi môi trường có thể nhận một tên khác, đặc biệt khi schema được tạo bằng những phiên bản script khác nhau. Khi đó, một lệnh drop dựa trên tên đoán trước có thể thất bại hoặc nhắm sai đối tượng.

Tên dễ dự đoán còn giúp:

1. Đọc lỗi vi phạm FK/UNIQUE/PK trong log ứng dụng.
2. Viết precondition bằng tên xác định.
3. Kiểm tra metadata trên staging và production.
4. Viết rollback tường minh, có thể review trước khi chạy.
5. Xử lý xung đột do tạo trùng chỉ mục hoặc constraint.
6. Giữ nhất quán giữa changelog và mã ứng dụng hoặc tài liệu vận hành.

Cần phân biệt **tên object trong database** với **định danh changeset**. Liquibase nhận diện changeset bằng bộ ba ID, AUTHOR và FILENAME; tên constraint/index nằm trong nội dung thay đổi. Đổi tên index trong một changeset đã chạy vẫn có thể làm checksum khác, nhưng không đổi khóa định danh của changeset.

## 3. Quy ước đặt tên đề xuất

Một quy ước đơn giản, dễ áp dụng là:

~~~text
pk_<table>
fk_<child-table>_<parent-table>            hoặc fk_<child-table>_<fk-column>
uq_<table>_<column-list-or-business-key>
ck_<table>_<business-rule>
df_<table>_<column>                        nếu DBMS có default constraint có tên
ix_<table>_<column-list-or-purpose>
~~~

Ví dụ:

~~~text
pk_customer_account
pk_purchase_order

fk_purchase_order_customer_account
fk_order_item_purchase_order

uq_customer_account_email
uq_inventory_item_sku_warehouse

ck_purchase_order_total_nonnegative

ix_customer_account_status_created_at
ix_purchase_order_customer_id
ix_purchase_order_unpaid_created_at
~~~

Các tiền tố chỉ là **quy ước của dự án**, không phải cú pháp bắt buộc của Liquibase. Có tổ chức dùng idx_ thay cho ix_, uk_ thay cho uq_ hoặc bổ sung mã schema. Quan trọng nhất là chọn một quy ước, áp dụng nhất quán và ghi rõ ý nghĩa.

### Đặt tên theo quan hệ hay theo cột?

Với FK, fk_purchase_order_customer_account giúp nhìn ra bảng con và bảng cha. Nhưng nếu purchase_order có hai FK tới cùng customer_account, một cho buyer_id và một cho approver_id, hai ràng buộc sẽ va chạm tên. Khi đó, hãy mô tả vai trò hoặc cột:

~~~text
fk_purchase_order_buyer
fk_purchase_order_approver
~~~

Hoặc:

~~~text
fk_purchase_order_buyer_id_customer_account
fk_purchase_order_approver_id_customer_account
~~~

Tên ngắn gọn nhưng đủ phân biệt là tốt hơn một tên dài lặp nhiều từ mà vẫn mơ hồ.

### Chỉ mục theo cột hay mục đích?

Với index nhiều cột, thứ tự có ý nghĩa:

~~~text
ix_purchase_order_customer_id_created_at
ix_purchase_order_created_at_customer_id
~~~

Đây có thể là **hai cấu trúc khác nhau** và được DBMS tối ưu khác nhau. Không tự coi chúng tương đương. Với partial index, functional index hoặc index chuyên phục vụ một kiểu truy vấn, tên theo mục đích có thể dễ hiểu hơn, ví dụ ix_purchase_order_open_recent, kèm tài liệu xác định biểu thức và điều kiện WHERE.

## 4. Tiêu chí của một tên bền vững

Một tên tốt nên đạt những tiêu chí sau:

- **Ổn định:** không dựa vào timestamp deploy, môi trường, số build hoặc tên người vận hành.
- **Dễ tra cứu:** có tiền tố chỉ loại đối tượng và thông tin bảng/cột liên quan.
- **Phân biệt được:** không tạo hai tên giống nhau trong phạm vi tên của DBMS.
- **Ngắn vừa đủ:** không vượt giới hạn độ dài identifier và không bị DBMS cắt tên.
- **Ít phụ thuộc môi trường:** cùng artifact dùng tên logic nhất quán giữa dev, staging, production.
- **Không gây khó đọc:** tránh ký tự đặc biệt, khoảng trắng, emoji và tên bắt buộc phải quote khi không cần.
- **Không chứa bí mật:** không đưa mã khách hàng thật, token, password hoặc thông tin cá nhân vào tên đối tượng.
- **Phù hợp tổ chức:** thống nhất snake_case chữ thường hoặc một chuẩn tương đương.

Không đưa tên môi trường vào constraint nếu cùng một migration sẽ chạy trên nhiều database độc lập. Ví dụ fk_purchase_order_customer_account_prod không cần thiết khi chính database/schema đã thể hiện môi trường. Nếu nhiều tenant nằm chung schema, có thể cần một chiến lược đặt tên khác theo kiến trúc tenant và phạm vi namespace thực tế.

## 5. Giới hạn DBMS: độ dài, chữ hoa và phạm vi tên

Quy tắc đặt tên phải phù hợp với DBMS đích. Một số điểm thường gặp:

| Vấn đề | Rủi ro |
|---|---|
| Giới hạn độ dài | Tên bị từ chối, cắt ngắn hoặc mất phần phân biệt |
| Phân biệt chữ hoa/thường | Tên viết hoa, viết thường hoặc được quote có thể được hiểu khác |
| Phạm vi duy nhất | Tên index/constraint có thể phải duy nhất trong schema, table hoặc database tùy DBMS và loại đối tượng |
| Từ khóa SQL | Tên trùng từ khóa buộc quote hoặc gây lỗi |
| Tên do DBMS sinh | Tên có thể thay đổi theo môi trường/cách tạo object |
| Quy tắc Unicode/byte | Giới hạn có thể tính theo byte thay vì số ký tự |

Ví dụ, PostgreSQL thường giới hạn identifier ở **63 byte** với cấu hình mặc định. MySQL có nhiều giới hạn identifier tính bằng ký tự, và Oracle có các giới hạn khác nhau giữa thế hệ phiên bản và mức tương thích. Không thiết kế một quy ước dựa trên một giới hạn cố định rồi mặc định mọi DBMS đều giống nhau.

Để giảm nguy cơ tên quá dài:

1. Bỏ các từ không bổ sung ý nghĩa, ví dụ the hoặc table.
2. Dùng chữ viết tắt đã thống nhất cho những tên bảng rất dài.
3. Giữ thông tin phân biệt ở phần cuối khi còn chỗ.
4. Nếu cần hash rút gọn, dùng thuật toán tạo hash **ổn định** từ tên logic và ghi quy tắc rõ ràng.
5. Kiểm tra tên thực tế được lưu trên DBMS đích sau migration.

Ví dụ, rút gọn:

~~~text
fk_purchase_order_customer_account_approver_id
→ fk_purchase_order_approver
~~~

Tránh việc hai tên dài khác nhau bị DBMS cắt thành cùng một chuỗi tiền tố. Ngoài giới hạn chiều dài, nên kiểm tra tên constraint/index hiện có để tránh va chạm trong namespace mà DBMS sử dụng.

## 6. Đặt tên primary key khi tạo bảng

Trong YAML changelog, có thể đặt tên PK bằng primaryKeyName trong constraints của cột:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer-account"
      author: "team-db"
      comment: "Tạo bảng và định danh khóa chính"
      changes:
        - createTable:
            schemaName: app
            tableName: customer_account
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_customer_account
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
                  constraints:
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            schemaName: app
            tableName: customer_account
~~~

**Lưu ý quan trọng:** rollback dropTable chỉ phù hợp để minh họa khi bảng mới tạo và chưa có dữ liệu cần giữ. Nếu bảng đã phát sinh dữ liệu, việc xóa bảng sẽ gây mất dữ liệu và có thể thất bại do phụ thuộc FK. Với production, cần đánh giá phương án khôi phục hoặc sửa tiến.

Nếu PK được thêm vào một bảng có sẵn, có thể dùng addPrimaryKey và đặt constraintName:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002-add-legacy-customer-pk"
      author: "team-db"
      changes:
        - addPrimaryKey:
            schemaName: app
            tableName: legacy_customer
            columnNames: id
            constraintName: pk_legacy_customer
      rollback:
        - dropPrimaryKey:
            schemaName: app
            tableName: legacy_customer
            constraintName: pk_legacy_customer
~~~

Hai changeset trên chỉ minh họa **hai ngữ cảnh khác nhau**: tạo bảng có PK, hoặc thêm PK cho bảng tồn tại. Không áp dụng cả hai cho cùng một bảng theo cách tạo khóa chính hai lần.

Trước addPrimaryKey, cần xác minh dữ liệu cột khóa không NULL và không trùng; có tên đúng không thay thế được điều kiện dữ liệu hợp lệ.

## 7. Đặt tên unique constraint và phân biệt unique index

Ví dụ yêu cầu mỗi email chỉ xuất hiện một lần trong bảng customer_account:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-unique-customer-email"
      author: "team-db"
      changes:
        - addUniqueConstraint:
            schemaName: app
            tableName: customer_account
            columnNames: email
            constraintName: uq_customer_account_email
      rollback:
        - dropUniqueConstraint:
            schemaName: app
            tableName: customer_account
            constraintName: uq_customer_account_email
~~~

Một unique constraint là quy tắc dữ liệu. Trên nhiều DBMS, nó được triển khai nhờ một index nhưng việc quản lý bằng **dropUniqueConstraint** khác với **dropIndex**; không tùy tiện thay hai change type cho nhau.

Nếu email có thể NULL, cách UNIQUE xử lý nhiều giá trị NULL phụ thuộc DBMS và một số tính năng/cấu hình cụ thể. Nếu nghiệp vụ yêu cầu tính duy nhất theo email chuẩn hóa (lowercase, trim), ràng buộc trên cột email thô chưa chắc đủ. Có thể cần quy tắc dữ liệu hoặc index biểu thức đặc thù DBMS, và phải đặt tên phản ánh chính xác mục tiêu.

Trước khi thêm ràng buộc, kiểm tra dữ liệu trùng:

~~~sql
SELECT email, COUNT(*) AS occurrences
FROM app.customer_account
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Truy vấn trên minh họa cách tìm giá trị trùng; nếu chuẩn hóa email là yêu cầu nghiệp vụ, phải áp dụng cùng phép chuẩn hóa trong bước kiểm tra. Không giải quyết lỗi addUniqueConstraint bằng cách xóa dữ liệu trùng mà chưa có quyết định nghiệp vụ.

## 8. Đặt tên foreign key rõ quan hệ và vai trò

Giả sử bảng purchase_order có customer_id tham chiếu customer_account.id:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-004-add-order-customer-fk"
      author: "team-db"
      changes:
        - addForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: purchase_order
            baseColumnNames: customer_id
            referencedTableSchemaName: app
            referencedTableName: customer_account
            referencedColumnNames: id
            constraintName: fk_purchase_order_customer_account
      rollback:
        - dropForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: purchase_order
            constraintName: fk_purchase_order_customer_account
~~~

Trong change type này:

- **baseTableName** là bảng chứa cột khóa ngoại, tức bảng con.
- **baseColumnNames** là cột FK của bảng con.
- **referencedTableName** là bảng được tham chiếu.
- **referencedColumnNames** là cột đích được tham chiếu.
- **constraintName** định danh ràng buộc để Liquibase có thể quản lý và gỡ bỏ.

Không đặt tên FK bằng một chuỗi chung như fk_customer nếu database có nhiều FK liên quan tới customer. Khi bảng có buyer_id và approver_id cùng trỏ customer_account, hãy đặt tên theo vai trò của từng khóa.

Trước khi áp FK, phải kiểm tra dữ liệu đang có. Nếu purchase_order.customer_id chứa một giá trị không tồn tại trong customer_account.id, lệnh thêm FK có thể thất bại dù tên FK hợp lệ và metadata không trùng. Tên cũng không thay thế quyết định về ON DELETE và ON UPDATE; phải xác định hành vi quan hệ đúng nghiệp vụ và hỗ trợ của DBMS.

## 9. Đặt tên index theo thứ tự cột và mục đích truy vấn

Một index phục vụ truy vấn theo trạng thái và thời điểm tạo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-005-index-customer-status-created"
      author: "team-db"
      changes:
        - createIndex:
            schemaName: app
            tableName: customer_account
            indexName: ix_customer_account_status_created_at
            columns:
              - column:
                  name: status
              - column:
                  name: created_at
      rollback:
        - dropIndex:
            schemaName: app
            tableName: customer_account
            indexName: ix_customer_account_status_created_at
~~~

Ví dụ giả định cột created_at đã tồn tại. Nếu chưa, changeset phải được đặt sau migration tạo cột và phải kiểm chứng trong changelog.

Thứ tự các cột trong index là một phần thiết kế vật lý: index trên (status, created_at) không tự động thay thế mọi tình huống của index trên (created_at, status). Tên nên thể hiện thứ tự để người đọc hiểu đúng ý định.

Với index chức năng, partial index, covering index hoặc index chuyên biệt phục vụ một workload, một tên theo mục đích có thể hữu ích, ví dụ ix_purchase_order_open_recent. Khi đó, phần comment trong changelog hoặc tài liệu thiết kế cần mô tả định nghĩa thực sự: biểu thức, điều kiện lọc, hướng sort hoặc cột INCLUDE.

Không tạo index chỉ vì có một FK hoặc một cột thường được lọc. Cần xem dữ liệu, truy vấn thực tế, EXPLAIN/plan, selectivity và chi phí write/maintenance. Index trùng chức năng gây tốn dung lượng và làm chậm INSERT/UPDATE/DELETE.

## 10. Các ràng buộc khác: CHECK và DEFAULT

Tên rõ ràng cũng có ích cho ràng buộc kiểm tra nghiệp vụ:

~~~text
ck_purchase_order_total_nonnegative
ck_customer_account_status_allowed
~~~

Ví dụ ý tưởng SQL trên một DBMS hỗ trợ CHECK:

~~~sql
ALTER TABLE app.purchase_order
ADD CONSTRAINT ck_purchase_order_total_nonnegative
CHECK (total_amount >= 0);
~~~

Các change type hỗ trợ CHECK trong Liquibase và tính năng đi kèm có thể phụ thuộc phiên bản/edition; một số nhóm dùng SQL có kiểm soát để tạo CHECK. Nếu cần SQL riêng, hãy dùng changeset với điều kiện DBMS và rollback tường minh, chẳng hạn DROP CONSTRAINT theo cú pháp đúng của DBMS.

Một số DBMS, đặc biệt SQL Server, biểu diễn DEFAULT bằng ràng buộc có tên riêng. Khi đó, nếu migration cần gỡ default, tên rõ ràng là lợi thế lớn. Nhưng không mặc định mọi DBMS đều tạo một default constraint theo cùng mô hình. Hãy kiểm tra metadata và tài liệu phiên bản trước khi đưa một tiền tố df_ vào quy ước chung.

Không đặt tên CHECK theo câu SQL quá dài. Ví dụ ck_purchase_order_total_nonnegative dễ đọc hơn ck_purchase_order_total_amount_greater_than_or_equal_to_zero, đồng thời ít vượt giới hạn độ dài.

## 11. Một chuỗi migration đầy đủ và thứ tự rollback

Giả sử hai bảng customer_account và purchase_order đã tồn tại, với các cột phù hợp. Thứ tự thay đổi có thể là:

~~~text
01. Tạo/kiểm tra primary key của bảng được tham chiếu
02. Làm sạch dữ liệu và thêm unique constraint
03. Tạo index phục vụ truy vấn
04. Xác minh dữ liệu tham chiếu rồi thêm foreign key
~~~

Nếu thực hiện rollback các changeset này, thứ tự logic thường cần đảo ngược:

~~~text
04. Gỡ foreign key trước
03. Gỡ index do changeset tạo
02. Gỡ unique constraint
01. Chỉ gỡ primary key nếu đã xác nhận không còn phụ thuộc
~~~

Lý do: DBMS thường không cho phép xóa một khóa được FK khác tham chiếu. Khi một thao tác cần thay đổi cấu trúc khóa, phải giải quyết phụ thuộc theo thứ tự thích hợp trước.

Tên giúp rollback chính xác nhưng **không tự giải quyết phụ thuộc**. Ví dụ dropForeignKeyConstraint cần tên FK đúng; nếu rollback một migration createTable đang chứa dữ liệu thật, việc dropTable vẫn không an toàn dù tên FK/PK rất chuẩn.

Với một changeset gồm nhiều change, rollback tường minh nên đảo ngược theo thứ tự phù hợp và được thử trên DBMS đích. Không giả định mọi thay đổi cấu trúc đều có rollback tự động hoặc DDL transaction đầy đủ. Nếu thay đổi SQL tạo index concurrently trên PostgreSQL, giao dịch và rollback cần được xem xét riêng.

## 12. Precondition xác minh tên đối tượng trước khi tạo

Liquibase hỗ trợ các precondition như primaryKeyExists, foreignKeyConstraintExists, uniqueConstraintExists và indexExists. Có thể dùng để phát hiện tình trạng không khớp trước khi chạy.

Ví dụ tạo index khi bảng đã có nhưng index cùng tên chưa tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-006-index-order-customer-id"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
            - tableExists:
                schemaName: app
                tableName: purchase_order
            - columnExists:
                schemaName: app
                tableName: purchase_order
                columnName: customer_id
            - not:
                - indexExists:
                    schemaName: app
                    tableName: purchase_order
                    indexName: ix_purchase_order_customer_id
      changes:
        - createIndex:
            schemaName: app
            tableName: purchase_order
            indexName: ix_purchase_order_customer_id
            columns:
              - column:
                  name: customer_id
      rollback:
        - dropIndex:
            schemaName: app
            tableName: purchase_order
            indexName: ix_purchase_order_customer_id
~~~

Precondition trên chỉ kiểm tra **sự tồn tại theo tên**. Nó không xác nhận rằng một index cùng tên đang có đúng cột hoặc đúng định nghĩa. Nếu phát hiện index đã tồn tại, chọn onFail: HALT sẽ buộc người vận hành xác minh khác biệt thay vì bỏ qua.

Cách dùng onFail: MARK_RAN có thể khiến Liquibase ghi EXECTYPE=MARK_RAN mà không chạy createIndex. Chỉ dùng sau khi có bằng chứng index đã tồn tại và **thực sự tương đương** với điều changeset cần tạo. Không dùng MARK_RAN như cách né lỗi tên trùng chưa được điều tra.

Với primaryKeyExists và foreignKeyConstraintExists, tùy change type và DBMS, tham số như primaryKeyName, foreignKeyName, foreignKeyTableName và schemaName cần được khai báo đúng. Ngoài tên, nên kiểm tra định nghĩa khóa và dữ liệu bằng metadata hoặc SQL riêng khi rủi ro cao.

## 13. Đổi tên constraint hoặc index đã triển khai

Đổi tên một index/constraint **không đồng nghĩa đổi tên changeset**. Khi đã ghi vào DATABASECHANGELOG, không sửa lại id, author hoặc nội dung changeset cũ để đổi ix_customer_status thành ix_customer_account_status.

Quy trình thích hợp là **changeset mới**, chẳng hạn:

1. Xác nhận đối tượng cũ đang tồn tại ở đúng schema/table.
2. Kiểm tra DBMS hỗ trợ rename trực tiếp hay phải drop/recreate.
3. Đánh giá tác động lock, khối lượng dữ liệu và giao dịch.
4. Tạo changeset mới mô tả chuyển đổi tên, có rollback tương ứng.
5. Xác nhận ứng dụng/job không sử dụng tên cũ trong câu lệnh DDL hoặc metadata.

Một số DBMS có SQL đổi tên index hoặc constraint, nhưng cú pháp và mức hỗ trợ không thống nhất. Nếu dùng SQL đặc thù:

~~~sql
-- Minh họa PostgreSQL, không dùng nguyên văn cho DBMS khác.
ALTER INDEX app.ix_customer_status
RENAME TO ix_customer_account_status;
~~~

Trong ví dụ, cần bảo đảm đối tượng thực tế là một index độc lập có thể đổi tên theo cú pháp phù hợp. Với index đang hỗ trợ một constraint, đổi tên index có thể tác động khác với đổi tên constraint. Hãy kiểm tra metadata trước khi thực hiện.

Nếu buộc phải drop và tạo lại index, không xem thao tác đó là rename thuần túy. Nó có thể cần quét bảng lớn, giữ lock hoặc tạo chi phí tài nguyên đáng kể. Với unique constraint và FK, việc drop/recreate còn có khoảng thời gian không có ràng buộc, có nguy cơ dữ liệu vi phạm nếu ứng dụng vẫn ghi.

**Rollback đổi tên** phải dùng đúng tên trước/sau và điều kiện tồn tại. Không đổi trực tiếp tên trong DATABASECHANGELOG: bảng đó quản lý định danh changeset, không phải danh mục tên index/constraint cần sửa tay.

## 14. Hành vi khi đổi tên bảng hoặc cột

Giả sử bảng customer được đổi thành customer_account. Ràng buộc ban đầu có tên pk_customer và uq_customer_email.

DBMS có thể giữ nguyên các tên ràng buộc, tự cập nhật phụ thuộc nội bộ hoặc có một số quy tắc đổi tên kèm theo. Không giả định tất cả PK, FK, index sẽ tự chuyển tên theo quy ước mới.

Có hai lựa chọn hợp lệ:

- **Giữ tên kỹ thuật cũ** nếu không ảnh hưởng triển khai, vận hành hoặc tuân thủ quy ước. Tên có thể phản ánh lịch sử, không nhất thiết phải đổi chỉ vì tên bảng đã đổi.
- **Tạo các changeset đổi tên riêng** sau khi đánh giá phụ thuộc và cú pháp DBMS. Khi làm vậy, phải phân biệt tên constraint và tên index backing.

Không tạo nhiều migration rủi ro chỉ để có tên “đẹp”. Mục tiêu đặt tên là hỗ trợ **vận hành, kiểm chứng và hoàn tác**, không phải buộc mọi object luôn trùng hoàn toàn với tên bảng hiện hành.

Khi đổi tên cột email thành primary_email, ràng buộc uq_customer_account_email có thể vẫn hợp lệ về logic. Hãy xem xét đặt tên mới nếu tên cũ thực sự gây nhầm lẫn hoặc cần chuẩn hóa, và phải đánh giá đầy đủ tác động tới SQL/script ngoài Liquibase.

## 15. Cách truy vấn metadata để đối chiếu tên

Ví dụ dưới đây dành cho **PostgreSQL** và chỉ dùng truy vấn đọc. Chúng không phải SQL chuẩn dùng nguyên vẹn trên mọi DBMS.

### Liệt kê ràng buộc

~~~sql
SELECT
    tc.table_schema,
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type
FROM information_schema.table_constraints AS tc
WHERE tc.table_schema = 'app'
  AND tc.table_name IN ('customer_account', 'purchase_order')
ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;
~~~

### Xem index và định nghĩa

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND tablename IN ('customer_account', 'purchase_order')
ORDER BY tablename, indexname;
~~~

### Kiểm tra một foreign key theo tên

~~~sql
SELECT
    con.conname AS constraint_name,
    con.conrelid::regclass AS table_name,
    con.confrelid::regclass AS referenced_table,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
WHERE con.contype = 'f'
  AND con.conname = 'fk_purchase_order_customer_account';
~~~

Từ thông tin này, cần kiểm tra cả **tên, bảng gốc, bảng tham chiếu, cột, định nghĩa**. Chỉ thấy constraint_name trong kết quả không đủ chứng minh mối quan hệ đúng như mong muốn.

Với MySQL, SQL Server hoặc Oracle, dùng catalog hoặc information_schema/metadata view mà DBMS đó hỗ trợ. Các mức quyền của tài khoản migration có thể ảnh hưởng khả năng đọc metadata; nếu không thấy đối tượng, cần phân biệt đối tượng thật sự không tồn tại với việc truy vấn không có quyền phù hợp.

## 16. Kiểm soát tên theo schema, tenant và môi trường

Một changelog được triển khai qua nhiều môi trường thường dùng cùng một tên logic:

~~~text
development: app_dev.ix_customer_account_status_created_at
staging:     app_stage.ix_customer_account_status_created_at
production:  app.ix_customer_account_status_created_at
~~~

Mỗi database/schema là phạm vi độc lập theo kiến trúc thực tế. Có thể giữ tên index nhất quán, còn schemaName hoặc JDBC URL được truyền qua cấu hình Liquibase/Spring Boot/CI/CD.

Ví dụ dùng changelog parameter cho schema:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-007-index-status-by-environment"
      author: "team-db"
      changes:
        - createIndex:
            schemaName: "${appSchema}"
            tableName: customer_account
            indexName: ix_customer_account_status
            columns:
              - column:
                  name: status
      rollback:
        - dropIndex:
            schemaName: "${appSchema}"
            tableName: customer_account
            indexName: ix_customer_account_status
~~~

Trong cả update và rollback, cần truyền **cùng giá trị appSchema** tương ứng với môi trường đã triển khai. Nếu rollback dùng appSchema khác, Liquibase có thể tìm đối tượng ở nhầm schema. Hãy lưu giá trị không nhạy cảm đã dùng trong log phát hành.

Việc chọn schema khác nhau không làm thay đổi quy tắc định danh changeset; mỗi database đích có DATABASECHANGELOG riêng. Không sửa id, author hoặc tên constraint tùy tiện trên một môi trường chỉ để “phân biệt” production.

Với mô hình multi-tenant cùng schema, tên index hoặc constraint có thể cần bao gồm phạm vi tenant nếu tạo nhiều đối tượng vật lý. Nhưng nếu tenant chỉ là giá trị dữ liệu trong một bảng chung, thường không nên tạo ràng buộc/index mới cho mỗi tenant; quy tắc nghiệp vụ và chiến lược phân vùng/index phải được thiết kế riêng.

## 17. Tác động lên ứng dụng, ORM và vận hành

Không phải mọi tên constraint đều xuất hiện trong mã Java, nhưng tên vẫn có thể tạo ra phụ thuộc:

- Hibernate/JPA có thể sinh DDL dựa trên annotation; cần tránh để auto-DDL cạnh tranh với Liquibase trong production.
- Một số ứng dụng phân loại lỗi theo constraintName, ví dụ biến lỗi uq_customer_account_email thành thông báo “Email đã được sử dụng”.
- Native SQL, stored procedure hoặc job DBA có thể tham chiếu tên constraint/index trong câu lệnh bảo trì.
- APM/log alert có thể tìm tên index hoặc constraint cụ thể.
- Công cụ migration/schema diff có thể báo drift nếu tên đối tượng khác dù định nghĩa gần giống.
- Báo cáo hiệu năng có thể tham chiếu tên index từ EXPLAIN hoặc system catalog.

Ví dụ JPA có thể khai báo unique constraint như sau:

~~~java
@Entity
@Table(
    name = "customer_account",
    schema = "app",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_customer_account_email",
        columnNames = {"email"}
    )
)
public class CustomerAccount {
    @Id
    private Long id;

    @Column(nullable = false)
    private String email;
}
~~~

Annotation minh họa tính nhất quán tên ở lớp mapping; nguồn quản lý schema cho production vẫn nên được quy định rõ. Nếu Liquibase là nguồn migration chính, đừng để Hibernate tạo một unique constraint tên khác ngoài ý muốn.

Khi đổi tên constraint, kiểm tra cả cách driver và framework báo lỗi. Một số DBMS trả tên ràng buộc trong lỗi, số khác trả mã lỗi hoặc thông điệp không đồng nhất. Không xây dựng logic nghiệp vụ chỉ dựa vào chuỗi thông báo có thể thay đổi giữa phiên bản.

## 18. Index trên bảng lớn và triển khai ít gián đoạn

Tên index giúp gỡ bỏ/khôi phục dễ hơn, nhưng **không quyết định** việc tạo index có khóa bảng lâu hay không. Trên database lớn, cần đánh giá:

1. Số lượng hàng và kích thước dữ liệu.
2. Tần suất ghi và thời gian lock.
3. Khả năng tạo index online/concurrently của DBMS.
4. Dung lượng đĩa tạm và replication lag.
5. Timeout và giới hạn transaction.
6. Cách dừng hoặc tiếp tục khi tạo index không hoàn thành.

Một số DBMS hỗ trợ tạo index đồng thời/online với cú pháp đặc thù. Ví dụ PostgreSQL có CREATE INDEX CONCURRENTLY nhưng lệnh này có yêu cầu riêng về transaction; không thể chỉ đặt tên ix_ rồi xem như tự động an toàn.

Nếu dùng SQL đặc thù thay vì createIndex chung của Liquibase, cần changeset tường minh với dbms phù hợp, xử lý runInTransaction một cách có chủ đích và kiểm tra trạng thái index bị tạo dở theo DBMS. Rollback cũng phải dùng cú pháp phù hợp và xác minh index có tồn tại, hợp lệ trước khi gỡ.

Không khẳng định rollback index là không có rủi ro: dropIndex có thể làm hiệu năng truy vấn suy giảm đột ngột, nhất là khi ứng dụng đã bắt đầu phụ thuộc vào kế hoạch truy vấn mới.

## 19. Rollback và phục hồi khi có lỗi giữa chừng

Một tình huống phát hành:

1. addUniqueConstraint thành công.
2. createIndex thất bại do thiếu dung lượng.
3. addForeignKeyConstraint chưa được chạy.

Tùy DBMS và cơ chế transaction DDL, database có thể đã ghi nhận một phần thay đổi. Cần đọc DATABASECHANGELOG và trạng thái schema thực tế để biết cái gì đã được áp dụng, không chỉ dựa trên exit code của pipeline.

Nếu các thao tác nằm trong changeset riêng:

- Chúng có các mốc lịch sử độc lập.
- Có thể xác định rõ changeset nào đã ghi EXECTYPE=EXECUTED hoặc trạng thái khác.
- Dễ sửa tiến bằng một changeset mới sau khi xử lý nguyên nhân lỗi.
- Rollback có thể được nhắm theo phạm vi phù hợp, nhưng vẫn phải đánh giá phụ thuộc.

Nếu nhiều thao tác nằm trong một changeset và DDL không thể rollback nguyên tử, tình trạng có thể phức tạp hơn. Khi đó, cần kiểm kê đối tượng thực tế theo **tên đã quy ước** trước khi chạy lại hoặc sửa tiến.

Không chỉnh trực tiếp DATABASECHANGELOG để làm hệ thống “trông như đã chạy”. Không dùng clear-checksums hoặc MARK_RAN làm phương án mặc định khi gặp lỗi; phải xác minh đúng định nghĩa đối tượng và thiết kế lại migration nếu cần.

## 20. Quy trình CI/CD có kiểm chứng

Một quy trình phát hành tốt sẽ:

1. Đọc changelog và xác nhận tên PK/FK/UQ/IX theo quy ước.
2. Chạy validate để kiểm tra cú pháp và tính hợp lệ ở mức Liquibase có thể hỗ trợ.
3. Chạy status --verbose để biết changeset nào đang chờ trên database đích.
4. Tạo update-sql và review **tên object**, schema, bảng/cột, hành vi dữ liệu và khóa.
5. Chạy truy vấn metadata để so sánh đối tượng hiện có trước khi áp dụng.
6. Xác nhận dữ liệu đủ điều kiện để thêm PK/UQ/FK.
7. Chạy update trong job migration có quyền phù hợp, theo cửa sổ phát hành.
8. Đối chiếu DATABASECHANGELOG, metadata và kiểm thử ứng dụng sau triển khai.
9. Lưu chứng cứ SQL đã review và quyết định phê duyệt, không ghi secret vào log.
10. Giữ nguyên changelog đã kiểm thử khi promote giữa staging và production.

Ví dụ lệnh CLI khi đã cấu hình kết nối và changelog:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
# Sau khi review SQL và phê duyệt:
liquibase update
liquibase history
~~~

Bảng DATABASECHANGELOG quản lý lịch sử changeset theo ID, AUTHOR, FILENAME, EXECTYPE, MD5SUM và các trường khác; nó **không thay thế** bảng metadata index/constraint của DBMS. Sau update, phải kiểm tra cả lịch sử Liquibase và định nghĩa vật lý của ràng buộc/chỉ mục.

Trong Spring Boot, cấu hình spring.liquibase.change-log chỉ định changelog gốc. Nếu cùng ứng dụng chạy ở nhiều instance, DATABASECHANGELOGLOCK hỗ trợ điều phối tiến trình Liquibase, nhưng không thay thế việc quản lý schema DDL, lock và traffic tại tầng database.

## 21. Tình huống thực hành: chuẩn hóa tên và rollback

**Đề bài:** database thử nghiệm PostgreSQL có bảng app.customer_account(id, email, status, created_at) và app.purchase_order(id, customer_id). Yêu cầu:

- Customer_account có PK tên pk_customer_account.
- Email có UNIQUE tên uq_customer_account_email.
- Chỉ mục theo status và created_at tên ix_customer_account_status_created_at.
- FK từ purchase_order.customer_id đến customer_account.id tên fk_purchase_order_customer_account.

Hãy thực hiện theo các bước:

1. **Đọc metadata hiện có.** Kiểm tra PK, UNIQUE, index và FK trên hai bảng; xác định tên có đang khác quy ước không.
2. **Kiểm tra dữ liệu.** Xác nhận id không NULL/trùng, email phù hợp quy tắc UNIQUE, và mọi customer_id có tham chiếu hợp lệ.
3. **Viết changeset độc lập** cho những đối tượng chưa tồn tại; đặt constraintName/indexName tường minh.
4. **Đặt precondition phù hợp**, ưu tiên HALT khi tên đã tồn tại nhưng chưa rõ định nghĩa.
5. **Khai báo rollback đúng change type**: dropPrimaryKey, dropUniqueConstraint, dropIndex, dropForeignKeyConstraint. Chỉ thử rollback những object được chính migration tạo ra và không còn phụ thuộc.
6. **Chạy validate và update-sql**; review đúng tên object/schema trước khi update.
7. **Thử update** trên database thử nghiệm có thể khôi phục.
8. **So sánh metadata** sau chạy: tên, bảng, cột, định nghĩa và trạng thái dữ liệu.
9. **Đọc DATABASECHANGELOG**, ghi nhận các changeset đã chạy.
10. **Thử rollback** trên bản sao thử nghiệm, đánh giá thứ tự gỡ FK trước khi gỡ khóa được tham chiếu.
11. **Triển khai qua staging** với cùng changelog và xác nhận tên object không bị thay đổi ngoài dự kiến.

### Câu hỏi tự kiểm tra

- Nếu tạo FK nhưng không đặt constraintName, có thể gỡ bằng tên fk_purchase_order_customer_account theo suy đoán không? **Không.** Cần biết tên thực tế DBMS đã tạo.
- Nếu index trùng tên đã tồn tại, có chắc nó có đúng cột và thứ tự không? **Không.** Phải kiểm tra định nghĩa.
- Có nên sửa changeset đã chạy để đổi tên uq_customer_email thành uq_customer_account_email không? **Không.** Viết changeset mới, xử lý theo DBMS và lịch sử.
- Unique constraint và unique index có phải cùng đối tượng trong mọi DBMS không? **Không.** Chúng có thể liên quan về cách thực thi nhưng khác mô hình và API quản lý.
- Rollback FK có bảo đảm dữ liệu luôn khôi phục an toàn không? **Không.** Gỡ FK có thể làm mất cơ chế bảo vệ tham chiếu, còn tái tạo FK có thể thất bại nếu dữ liệu thay đổi.
- Đặt tên chuẩn có thay thế việc kiểm tra production bằng update-sql không? **Không.** Tên chỉ là một phần của migration cần review.

## 22. Checklist review tên ràng buộc và chỉ mục

- [ ] Đã phân biệt PK, FK, UNIQUE, CHECK, DEFAULT và index.
- [ ] Mỗi loại có tiền tố theo quy ước của dự án.
- [ ] Tên đủ thông tin bảng, cột hoặc vai trò quan hệ.
- [ ] FK nhiều vai trò tới cùng bảng cha được đặt tên khác nhau.
- [ ] Tên nằm trong giới hạn độ dài và namespace của DBMS đích.
- [ ] Không có tên sinh ngẫu nhiên ngoài ý muốn trong migration mới.
- [ ] Đã khai báo primaryKeyName, constraintName hoặc indexName đúng change type.
- [ ] Rollback dùng đúng tên object và đúng change type.
- [ ] Đã kiểm tra thứ tự phụ thuộc khi thêm/gỡ FK, PK và UNIQUE.
- [ ] Đã xác nhận dữ liệu không vi phạm ràng buộc sắp thêm.
- [ ] Index không trùng chức năng và đúng thứ tự cột/biểu thức/predicate.
- [ ] Precondition được dùng đúng mục đích, không MARK_RAN khi chưa kiểm chứng định nghĩa.
- [ ] Không sửa changeset đã chạy để đổi tên object.
- [ ] Rename constraint/index được viết thành migration mới khi thật sự cần.
- [ ] Đã rà soát các phụ thuộc trong ORM, native SQL, log/error mapping và job vận hành.
- [ ] Đã đánh giá lock DDL, chi phí tạo index và phương án rollback.
- [ ] Đã chạy validate, status, update-sql và kiểm tra metadata DBMS.
- [ ] Đã đọc DATABASECHANGELOG và kiểm chứng object thật sau triển khai.
- [ ] Cùng artifact/changelog được promote qua các môi trường, giá trị schema được quản lý rõ ràng.

**Kết luận:** tên ràng buộc và chỉ mục ổn định giúp Liquibase thao tác chính xác trên đối tượng, viết rollback dễ kiểm chứng và điều tra sự cố nhanh hơn. Một quy ước hiệu quả kết hợp tiền tố loại đối tượng, vai trò nghiệp vụ, phạm vi tên và giới hạn DBMS. Nhưng tên đúng chưa đủ: vẫn phải kiểm tra dữ liệu, thứ tự phụ thuộc, định nghĩa thực tế, khả năng khóa bảng và trạng thái DATABASECHANGELOG. Khi áp dụng đồng bộ trong changelog và quy trình Spring Boot/CI/CD, nhóm giảm rủi ro triển khai và tăng khả năng hoàn tác một cách có kiểm soát.
