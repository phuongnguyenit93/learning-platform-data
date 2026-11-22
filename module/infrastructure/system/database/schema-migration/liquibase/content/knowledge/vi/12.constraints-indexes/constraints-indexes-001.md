# Tạo, thay đổi và xóa khóa chính

## 1. Mục tiêu và vị trí trong quản lý migration

**Khóa chính** (*primary key*, viết tắt **PK**) xác định duy nhất từng hàng của một bảng. Đây là một ràng buộc nền tảng trong thiết kế cơ sở dữ liệu quan hệ: một bảng có thể có nhiều ràng buộc UNIQUE nhưng chỉ có **một ràng buộc PRIMARY KEY**, gồm một hoặc nhiều cột. Các cột tham gia khóa chính không được chứa giá trị NULL và tổ hợp giá trị khóa phải là duy nhất.

Bài thuộc chương **Khóa và chỉ mục** trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trong phạm vi đó, bài này tập trung vào cách **tạo khóa chính khi tạo bảng, thêm khóa chính cho bảng đã tồn tại, thay đổi tập cột khóa chính và xóa khóa chính** bằng Liquibase.

Sau khi học, bạn cần có khả năng:

1. Hiểu ràng buộc PRIMARY KEY khác UNIQUE, NOT NULL và chỉ mục thường ở đâu.
2. Chọn khóa chính một cột hoặc khóa chính ghép phù hợp với mô hình dữ liệu.
3. Viết changeset Liquibase YAML dùng **createTable**, **addPrimaryKey** và **dropPrimaryKey**.
4. Kiểm tra dữ liệu hiện có trước khi thêm hoặc đổi PK: NULL, trùng khóa, quan hệ FK và phụ thuộc ứng dụng.
5. Thiết kế chuỗi migration đổi PK theo thứ tự an toàn, có phương án rollback hoặc khôi phục.
6. Xem xét khác biệt giữa PostgreSQL, MySQL, SQL Server, Oracle và ảnh hưởng tới chỉ mục, khóa bảng, hiệu năng.
7. Kiểm chứng migration trên dev/test trước khi triển khai production qua Spring Boot hoặc CI/CD.

**Nguyên tắc xuyên suốt:** khai báo thay đổi khóa chính là thao tác thay đổi hợp đồng dữ liệu của bảng, không chỉ là thay một dòng cấu hình. Nếu PK đã được tham chiếu bởi khóa ngoại hoặc được ứng dụng dùng làm định danh, cần kế hoạch tương thích và chuyển đổi dữ liệu.

## 2. Khóa chính thực chất bảo đảm điều gì?

Một ràng buộc PRIMARY KEY gồm hai tính chất logic:

- **Duy nhất:** không có hai hàng có cùng giá trị PK. Với PK ghép, tổ hợp tất cả cột mới phải duy nhất; từng cột riêng lẻ không nhất thiết duy nhất.
- **Không NULL:** mọi cột thuộc PK phải có giá trị ở mọi hàng.

Ví dụ bảng customers có khóa chính customer_id:

| customer_id | customer_name |
|---|---|
| 101 | Minh |
| 102 | Lan |
| 103 | Nam |

Giá trị customer_id = 102 không thể xuất hiện thêm ở một hàng khác, và customer_id không thể NULL.

Ví dụ khóa chính ghép của bảng order_items là **(order_id, line_no)**:

| order_id | line_no | product_code |
|---|---|---|
| 5001 | 1 | P001 |
| 5001 | 2 | P002 |
| 5002 | 1 | P005 |

order_id có thể lặp, line_no cũng có thể lặp, nhưng cặp (order_id, line_no) phải duy nhất. Cặp (5001, 2) không thể xuất hiện hai lần.

### 2.1. PRIMARY KEY khác UNIQUE, NOT NULL và INDEX

| Thành phần | Vai trò chính | Có thể thay thế PK không? |
|---|---|---|
| PRIMARY KEY | Định danh hàng, bảo đảm duy nhất và không NULL | Bản thân là ràng buộc khóa chính của bảng |
| UNIQUE | Ngăn giá trị hoặc tổ hợp trùng nhau | Không mặc nhiên là PK; chính sách NULL khác nhau theo DBMS |
| NOT NULL | Cấm giá trị NULL ở một cột | Không bảo đảm duy nhất |
| INDEX | Tăng tốc truy cập và có thể hỗ trợ ràng buộc | Chỉ mục thường không tự tạo ngữ nghĩa PRIMARY KEY |
| FOREIGN KEY | Bảo đảm quan hệ tham chiếu giữa các bảng | Phụ thuộc vào khóa được tham chiếu, không phải PK của bảng con |

Trong nhiều DBMS, tạo PRIMARY KEY đồng thời tạo hoặc sử dụng một cấu trúc chỉ mục duy nhất để thực thi ràng buộc. **Không nên hiểu “PK = một index thường”.** Dữ liệu, metadata, quy tắc cho khóa ngoại và hành vi khi xóa PK là những phần của ràng buộc, còn cách triển khai index cụ thể phụ thuộc hệ quản trị.

### 2.2. Khóa tự nhiên và khóa thay thế

**Khóa tự nhiên** (*natural key*) có ý nghĩa nghiệp vụ như mã quốc gia hoặc mã định danh có tính ổn định lâu dài. **Khóa thay thế** (*surrogate key*) là định danh kỹ thuật như BIGINT phát sinh từ sequence/identity hoặc UUID.

| Lựa chọn | Ưu điểm | Rủi ro/cân nhắc |
|---|---|---|
| BIGINT/identity | Kích thước gọn, index thường hiệu quả, dễ tham chiếu | Cần chiến lược sinh ID; phân tán và đồng bộ có thể phức tạp |
| UUID | Có thể tạo ID phân tán, ít phụ thuộc bộ cấp phát tập trung | Kích thước index lớn hơn; kiểu UUID và đặc điểm phân bố ảnh hưởng hiệu năng |
| Mã nghiệp vụ | Dễ hiểu, tránh một số phép ánh xạ ID | Dữ liệu nghiệp vụ có thể thay đổi; giá trị dài hoặc phụ thuộc quy tắc |
| Khóa ghép | Diễn tả tự nhiên quan hệ nhiều thành phần | FK tham chiếu rộng hơn, câu truy vấn và API có thể phức tạp |

Đừng thay đổi thiết kế PK chỉ vì muốn tối ưu một truy vấn đơn lẻ. Cần cân nhắc khóa ngoại, tính ổn định của định danh, dung lượng index và hợp đồng của ứng dụng.

## 3. Liquibase quản lý khóa chính như thế nào?

Liquibase diễn đạt thay đổi lược đồ bằng **changelog** chứa nhiều **changeset**. Mỗi changeset được nhận diện bởi **id**, **author** và đường dẫn changelog (hoặc danh tính logic được cấu hình). Công cụ đối chiếu các thay đổi với bảng lịch sử **DATABASECHANGELOG** và dùng checksum để phát hiện thay đổi nội dung của changeset đã áp dụng.

Những change type chính trong bài:

| Change type / thuộc tính | Mục đích | Khi sử dụng |
|---|---|---|
| createTable cùng column.constraints.primaryKey | Tạo bảng và khai báo PK ngay trong định nghĩa cột | Bảng mới |
| addPrimaryKey | Thêm PK vào một bảng đã tồn tại | Dữ liệu và cấu trúc đã đủ điều kiện |
| dropPrimaryKey | Gỡ PK hiện có khỏi bảng | Chuyển đổi mô hình khóa, xử lý phụ thuộc có kiểm soát |
| addNotNullConstraint | Bổ sung NOT NULL, khi cần chuẩn bị cột ngoài PK | Chuẩn hóa dữ liệu trước đổi khóa |
| addUniqueConstraint / createIndex | Chuẩn bị hoặc bảo vệ tính duy nhất theo thiết kế | Không mặc nhiên tương đương tạo PK |
| addForeignKeyConstraint / dropForeignKeyConstraint | Quản lý những quan hệ tham chiếu | Khi đổi PK ảnh hưởng tới FK |

**Tên khóa chính** nên theo quy ước nhất quán, ví dụ pk_customers, pk_orders, pk_order_items. Tên constraint rõ ràng giúp xem metadata, điều tra lỗi và xây dựng rollback dễ hơn so với phụ thuộc tên tự sinh của DBMS.

Các ví dụ sau dùng **YAML changelog của Liquibase** và ưu tiên PostgreSQL để mô tả SQL kiểm chứng. Tên/schema/version của DBMS chỉ là ví dụ; phải xác minh khả năng hỗ trợ change type của bản Liquibase cùng hệ quản trị thật trước khi dùng production.

## 4. Tạo khóa chính ngay khi tạo bảng

### 4.1. createTable với PK một cột

Một bảng mới thường nên khai báo PK ngay trong changeset createTable để không có giai đoạn bảng thiếu định danh.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customers
      author: platform-team
      changes:
        - createTable:
            schemaName: app
            tableName: customers
            columns:
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_customers
                    nullable: false
              - column:
                  name: customer_name
                  type: VARCHAR(150)
                  constraints:
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
      rollback:
        - dropTable:
            schemaName: app
            tableName: customers
~~~

**Điều kiện của ví dụ:** schema app đã tồn tại, tên bảng chưa bị sử dụng, tài khoản migration có quyền CREATE TABLE và các kiểu dữ liệu được DBMS hỗ trợ.

Giải thích:

- **primaryKey: true** khai báo cột customer_id là thành phần của PRIMARY KEY.
- **primaryKeyName** đặt tên constraint. Một số DBMS có quy tắc giới hạn chiều dài/tên khác nhau.
- **nullable: false** biểu đạt rõ ý định; bản thân PK đã yêu cầu không NULL.
- **rollback dropTable** chỉ thích hợp khi thực sự được phép xóa bảng mới tạo và dữ liệu bên trong. Sau khi ứng dụng đã có dữ liệu, rollback bằng dropTable có thể phá hủy dữ liệu, không phải phương án an toàn mặc định.

**PK không tự sinh ID.** Khai báo primaryKey: true cho BIGINT không làm cột tự tăng. Nếu cần identity/sequence/auto increment, phải cấu hình riêng theo khả năng hỗ trợ của DBMS và Liquibase, rồi kiểm thử cơ chế sinh giá trị.

### 4.2. Tạo khóa chính ghép khi tạo bảng

Khi mỗi dòng hàng được định danh bằng order_id và line_no:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-create-order-items
      author: platform-team
      changes:
        - createTable:
            schemaName: app
            tableName: order_items
            columns:
              - column:
                  name: order_id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_order_items
                    nullable: false
              - column:
                  name: line_no
                  type: INT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_order_items
                    nullable: false
              - column:
                  name: product_code
                  type: VARCHAR(50)
                  constraints:
                    nullable: false
              - column:
                  name: quantity
                  type: INT
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            schemaName: app
            tableName: order_items
~~~

Cùng hai cột được đánh dấu **primaryKey: true** để hình thành một PK ghép; đặt cùng một **primaryKeyName** thể hiện đây là một constraint logic duy nhất. Hãy kiểm tra SQL được Liquibase sinh ra cho đúng DBMS và bản Liquibase sử dụng. Nếu công cụ/DBMS không xử lý như kỳ vọng, có thể tổ chức thay đổi thành createTable rồi addPrimaryKey với **columnNames: order_id,line_no**.

**Khóa ghép không bảo đảm business invariant khác.** Ví dụ quantity phải lớn hơn 0 không được bảo đảm bởi PRIMARY KEY; đó là bài toán CHECK constraint và kiểm tra nghiệp vụ riêng.

## 5. Thêm PRIMARY KEY cho một bảng đã tồn tại

Bảng cũ có thể thiếu PK do di sản thiết kế hoặc do dữ liệu được import mà chưa có ràng buộc. Thêm PK cần một chuỗi bước:

1. Xác định cột/các cột dự kiến làm khóa.
2. Kiểm tra các giá trị NULL.
3. Kiểm tra trùng lặp theo toàn bộ khóa.
4. Kiểm tra bảng đã có PK khác chưa, và các FK đang tham chiếu.
5. Dự tính tác động index, thời gian khóa và lưu lượng ghi.
6. Chạy changeset addPrimaryKey trên môi trường test đại diện.
7. Chỉ triển khai production khi có phương án phục hồi và kiểm chứng hậu triển khai.

### 5.1. Thử kiểm tra NULL

Với bảng app.orders có cột order_id, truy vấn PostgreSQL:

~~~sql
SELECT COUNT(*) AS null_key_rows
FROM app.orders
WHERE order_id IS NULL;
~~~

Để thêm PK, giá trị phải là **0**. Nếu có giá trị NULL, cần làm sạch hoặc bổ sung định danh trước khi thêm constraint.

### 5.2. Thử kiểm tra trùng khóa

~~~sql
SELECT order_id, COUNT(*) AS occurrences
FROM app.orders
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Truy vấn này liệt kê những khóa trùng. Trên bảng lớn, GROUP BY có thể tốn I/O và bộ nhớ; cần đánh giá thời gian chạy, thống kê dữ liệu và chỉ mục sẵn có. Nếu chỉ muốn một con số cho precondition:

~~~sql
SELECT COUNT(*)
FROM (
    SELECT order_id
    FROM app.orders
    GROUP BY order_id
    HAVING COUNT(*) > 1
) AS duplicated_keys;
~~~

Để thêm PK, kết quả phải là **0**.

### 5.3. Viết changeset addPrimaryKey có kiểm tra dữ liệu

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-add-orders-primary-key
      author: platform-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: app
            tableName: orders
        - not:
            - primaryKeyExists:
                schemaName: app
                tableName: orders
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.orders
              WHERE order_id IS NULL
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM (
                  SELECT order_id
                  FROM app.orders
                  GROUP BY order_id
                  HAVING COUNT(*) > 1
              ) AS duplicated_keys
      changes:
        - addPrimaryKey:
            schemaName: app
            tableName: orders
            columnNames: order_id
            constraintName: pk_orders
      rollback:
        - dropPrimaryKey:
            schemaName: app
            tableName: orders
            constraintName: pk_orders
~~~

**Những điểm cần hiểu:**

- **primaryKeyExists** xác nhận bảng chưa có PK; nếu đã có, chính sách HALT yêu cầu điều tra, không tự động xóa hoặc thay PK cũ.
- Hai **sqlCheck** xác nhận dữ liệu không NULL và không trùng.
- **addPrimaryKey** thêm ràng buộc với tên rõ ràng.
- **rollback dropPrimaryKey** có thể gỡ ràng buộc nếu thực sự cần, nhưng không tự khôi phục mọi ảnh hưởng đến quan hệ và ứng dụng.

Ví dụ giả định PostgreSQL có bảng app.orders, các cột/thông số đúng như mô tả và tài khoản có quyền DDL. Liquibase sẽ dùng SQL phù hợp DBMS được hỗ trợ; cần đối chiếu kết quả update-sql và kiểm thử thực tế.

**Lưu ý quan trọng:** việc precondition trả 0 không bảo vệ tuyệt đối khỏi một phiên giao dịch khác chèn hàng trùng/null giữa thời điểm kiểm tra và lúc DBMS áp đặt constraint. Quy tắc cuối cùng vẫn được DBMS thực thi khi addPrimaryKey. Với hệ thống đang ghi liên tục, cần chiến lược triển khai để kiểm soát ghi đồng thời hoặc tính tới khả năng lệnh thất bại.

### 5.4. Khi nào cần thêm NOT NULL riêng?

Một số DBMS/loại thao tác tạo PK sẽ đồng thời áp đặt NOT NULL cho cột khóa. Tuy nhiên, nếu chuyển đổi dữ liệu phức tạp hoặc cần thay đổi trạng thái nullable có kiểm soát trước khi tạo PK, có thể dùng **addNotNullConstraint** ở changeset riêng.

Đừng tự áp dụng NOT NULL trước khi làm sạch dữ liệu cũ. Việc thêm NOT NULL, tạo PK và triển khai code ứng dụng cùng lúc phải được kiểm thử theo đúng thứ tự để tránh ứng dụng cũ còn tạo hàng thiếu định danh.

## 6. Thêm khóa chính ghép vào bảng hiện hữu

Giả sử bảng app.order_items có hai cột order_id và line_no nhưng chưa có PK. Bộ kiểm tra phải đánh giá **cặp khóa**, không phải từng cột riêng lẻ.

### 6.1. Kiểm tra NULL của bất kỳ thành phần nào

~~~sql
SELECT COUNT(*) AS null_component_rows
FROM app.order_items
WHERE order_id IS NULL
   OR line_no IS NULL;
~~~

Chỉ một cột của PK ghép bị NULL cũng không hợp lệ.

### 6.2. Kiểm tra tổ hợp trùng

~~~sql
SELECT order_id, line_no, COUNT(*) AS occurrences
FROM app.order_items
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

Đôi khi order_id lặp nhiều lần là đúng nghiệp vụ; điểm cần loại trừ chỉ là **cặp trùng**.

### 6.3. addPrimaryKey cho nhiều cột

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-add-order-items-pk
      author: platform-team
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: order_items
        - not:
            - primaryKeyExists:
                schemaName: app
                tableName: order_items
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.order_items
              WHERE order_id IS NULL OR line_no IS NULL
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM (
                  SELECT order_id, line_no
                  FROM app.order_items
                  GROUP BY order_id, line_no
                  HAVING COUNT(*) > 1
              ) AS duplicated_pairs
      changes:
        - addPrimaryKey:
            schemaName: app
            tableName: order_items
            columnNames: order_id,line_no
            constraintName: pk_order_items
      rollback:
        - dropPrimaryKey:
            schemaName: app
            tableName: order_items
            constraintName: pk_order_items
~~~

Thứ tự cột **order_id,line_no** là một phần của thiết kế PK ghép: tuy tính duy nhất của (A,B) và (B,A) là tương đương về mặt logic, thứ tự cột có thể ảnh hưởng cách index được tạo và hiệu quả truy vấn. Chọn thứ tự dựa trên truy vấn thực tế và các quan hệ tham chiếu, không chỉ theo thứ tự xuất hiện trong bảng.

## 7. Xóa khóa chính bằng dropPrimaryKey

Đôi khi cần bỏ PK vì thay đổi mô hình định danh. Liquibase cung cấp change type **dropPrimaryKey**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 005-drop-legacy-primary-key
      author: platform-team
      preConditions:
        - onFail: HALT
        - primaryKeyExists:
            schemaName: app
            tableName: legacy_codes
      changes:
        - dropPrimaryKey:
            schemaName: app
            tableName: legacy_codes
            constraintName: pk_legacy_codes
      rollback:
        - addPrimaryKey:
            schemaName: app
            tableName: legacy_codes
            columnNames: legacy_code
            constraintName: pk_legacy_codes
~~~

Đây là **ví dụ độc lập** dành cho bảng app.legacy_codes, giả định bảng có PK pk_legacy_codes trên legacy_code và không có khóa ngoại hoặc đối tượng phụ thuộc cản trở việc xóa. Khi thực hành trên DBMS cụ thể, cần xác nhận thuộc tính constraintName được hỗ trợ đúng như dự kiến.

**Đừng xem dropPrimaryKey là bước dọn dẹp vô hại.** Gỡ PK có thể:

- Làm mất cơ chế bảo đảm định danh duy nhất nếu không có UNIQUE khác.
- Ảnh hưởng những FK đang tham chiếu.
- Làm thay đổi hoặc loại bỏ chỉ mục dùng để thực thi PK, tùy DBMS.
- Ảnh hưởng kế hoạch truy vấn, join, ORM và hành vi UPDATE/DELETE theo ID.
- Đặt bảng vào trạng thái không còn khóa chính, nếu không tạo khóa thay thế trong quy trình an toàn.

Rollback trong ví dụ **chỉ có thể thêm lại PK cũ nếu dữ liệu vẫn không NULL/không trùng và các phụ thuộc không xung đột**. Nếu ứng dụng đã cho phép dữ liệu mới vi phạm điều kiện, rollback có thể thất bại.

### 7.1. PK bị FK tham chiếu thì sao?

Một FK thường tham chiếu tới PK hoặc một khóa duy nhất được DBMS cho phép. Nếu một FK đang phụ thuộc PK bị xóa, nhiều DBMS sẽ từ chối lệnh DROP CONSTRAINT nếu không xử lý quan hệ tham chiếu trước.

Trên PostgreSQL, **không nên tự động thêm CASCADE** để “cho chạy được”, vì CASCADE có thể xóa các constraint phụ thuộc ngoài phạm vi dự định. Đúng hơn là phải liệt kê FK, lập trình tự thay đổi/chuyển FK và kiểm chứng toàn bộ đường quan hệ.

Một thiết kế đổi khóa chính thực tế thường yêu cầu **dropForeignKeyConstraint**, **addForeignKeyConstraint** và có thể cần backfill cột FK ở bảng con. Đây là vấn đề chuyển đổi dữ liệu và hợp đồng ứng dụng, không chỉ là đổi PK của một bảng.

## 8. Thay đổi khóa chính có những loại nào?

Cụm từ “thay đổi khóa chính” có thể mang nhiều ý nghĩa. Không nên dùng một phương án cho tất cả:

| Yêu cầu | Ví dụ | Hướng xử lý |
|---|---|---|
| Đổi tên constraint, giữ cột khóa | pk_old → pk_orders | Sử dụng thao tác đổi tên constraint được DBMS hỗ trợ, hoặc migration có review; tránh drop/add không cần thiết |
| Đổi kiểu dữ liệu cột khóa | INT → BIGINT | Xem FK cùng kiểu, mức khóa và khả năng chuyển kiểu; PK logic có thể giữ nguyên |
| Đổi từ khóa đơn sang khóa ghép | id → (order_id, line_no) | Chuẩn bị dữ liệu, FK, chỉ mục, code ứng dụng; thay constraint theo thứ tự |
| Đổi khóa tự nhiên sang surrogate | customer_code → customer_id | Thêm ID, backfill, chuyển FK, đổi quan hệ, tạo PK mới theo giai đoạn |
| Đổi thứ tự cột trong PK ghép | (a,b) → (b,a) | Kiểm tra query plan và index; đánh giá xem cần đổi PK hay chỉ thêm index khác |
| Chuyển khóa giữa schema/database | orders.id sang định danh mới ở hệ khác | Bài toán chuyển dữ liệu và đồng bộ liên dịch vụ, không chỉ một changeset |

**Liquibase không có một thao tác phổ quát “modifyPrimaryKey” bảo đảm đổi mọi loại PK an toàn.** Thay đổi tập cột PK thường phải tổ chức các bước chuẩn bị, bỏ ràng buộc cũ và tạo ràng buộc mới, đồng thời xử lý FK và dữ liệu liên quan. Nếu chỉ cần tối ưu truy vấn, có khi tạo một index phụ là hợp lý hơn việc thay PK.

## 9. Ví dụ chiến lược đổi từ PK đơn sang PK ghép

Giả sử bảng app.order_items hiện dùng PK **order_item_id**, nhưng yêu cầu nghiệp vụ mới muốn dùng **(order_id, line_no)**. Đừng lập tức xóa PK cũ và thêm PK mới trên production.

### 9.1. Xác nhận các giả định

Trước hết xác nhận:

1. Mỗi hàng có order_id và line_no không NULL.
2. Cặp (order_id, line_no) không trùng trên dữ liệu hiện tại.
3. Mọi code đang đọc/ghi order_item_id đã được xác định.
4. Các bảng con đang dùng order_item_id làm FK đã được liệt kê.
5. Có phương án chuyển tham chiếu hoặc duy trì định danh cũ trong giai đoạn tương thích.
6. Dữ liệu mới trong thời gian triển khai vẫn tuân theo ràng buộc của khóa mới.

### 9.2. Giai đoạn expand

Không phá PK cũ ngay. Đầu tiên:

- Bổ sung cột line_no nếu chưa có, ban đầu theo chiến lược phù hợp với dữ liệu cũ.
- Backfill các giá trị thiếu từ dữ liệu nguồn có kiểm chứng.
- Bổ sung NOT NULL khi mọi hàng đã hợp lệ.
- Thêm **UNIQUE(order_id, line_no)** để bảo vệ bất biến của khóa mới trong giai đoạn song song.
- Phát hành ứng dụng có thể đọc/ghi cả định danh cũ và khóa mới, nếu kiến trúc yêu cầu.

Unique constraint không biến cặp đó thành PK, nhưng giúp kiểm tra tính duy nhất trước khi thay đổi ràng buộc chính. Cần đảm bảo cách DBMS xử lý NULL phù hợp; nếu chưa áp NOT NULL, UNIQUE một mình có thể không ngăn mọi trường hợp cần ngăn.

### 9.3. Giai đoạn migrate

Cập nhật mọi bảng tham chiếu và code ứng dụng. Nếu bảng shipment_items đang FK tới order_items(order_item_id), không thể chỉ đổi PK ở order_items mà bỏ qua shipment_items. Có thể cần thêm order_id/line_no ở bảng con, backfill từ quan hệ cũ, kiểm chứng tính đầy đủ và bổ sung FK mới.

Thử toàn bộ luồng đọc/ghi, chạy đồng thời phiên bản ứng dụng cũ và mới nếu production deploy rolling. Chỉ khi không còn thành phần nào phụ thuộc vào PK cũ mới thực hiện bước cuối.

### 9.4. Giai đoạn contract

Sau khi kiểm chứng:

1. Xác nhận các FK cũ đã được chuyển/gỡ theo kế hoạch.
2. Xác nhận dữ liệu không NULL và không trùng ở khóa mới.
3. Thực hiện dropPrimaryKey cho constraint cũ.
4. Thực hiện addPrimaryKey cho (order_id,line_no).
5. Tạo/kiểm tra lại FK mới và các index bổ trợ.
6. Kiểm tra hiệu năng, ORM mapping, API và hệ thống tích hợp.
7. Chỉ loại bỏ cột order_item_id nếu chắc chắn không còn được sử dụng và đã có kế hoạch dữ liệu.

Việc drop/add cuối cùng có thể được tổ chức thành một changeset transaction trên DBMS hỗ trợ DDL giao dịch, **nhưng không được giả định mọi DBMS đảm bảo atomic DDL như nhau**. Với PostgreSQL, nhiều DDL có thể nằm trong giao dịch, song khóa bảng và phụ thuộc vẫn có thể cản trở. Với MySQL, hành vi implicit commit/DDL khác biệt cần xem xét riêng.

### 9.5. Ví dụ bước contract tối giản

Chỉ dùng minh họa khi **mọi phụ thuộc đã được xử lý**, bảng có dữ liệu hợp lệ và việc đổi PK đã được tập dượt:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 006-switch-order-items-primary-key
      author: platform-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - primaryKeyExists:
            schemaName: app
            tableName: order_items
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.order_items
              WHERE order_id IS NULL OR line_no IS NULL
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM (
                  SELECT order_id, line_no
                  FROM app.order_items
                  GROUP BY order_id, line_no
                  HAVING COUNT(*) > 1
              ) AS duplicated_pairs
      changes:
        - dropPrimaryKey:
            schemaName: app
            tableName: order_items
            constraintName: pk_order_items_id
        - addPrimaryKey:
            schemaName: app
            tableName: order_items
            columnNames: order_id,line_no
            constraintName: pk_order_items
      rollback:
        - dropPrimaryKey:
            schemaName: app
            tableName: order_items
            constraintName: pk_order_items
        - addPrimaryKey:
            schemaName: app
            tableName: order_items
            columnNames: order_item_id
            constraintName: pk_order_items_id
~~~

Điều kiện primaryKeyExists ở đây chỉ kiểm tra **có** PK; chưa xác minh đầy đủ PK hiện hữu đúng là pk_order_items_id. Với một quy trình production, cần kiểm tra tên và tập cột PK hiện tại bằng metadata DBMS hoặc preflight riêng trước khi drop. Rollback chỉ phản ánh việc đổi constraint, không tự phục hồi những FK, mã ứng dụng hoặc dữ liệu đã chuyển đổi ngoài changeset này.

## 10. Kiểm tra khóa chính và khóa ngoại bằng SQL PostgreSQL

### 10.1. Liệt kê PK của bảng

~~~sql
SELECT
    c.conname AS constraint_name,
    pg_get_constraintdef(c.oid) AS constraint_definition
FROM pg_constraint AS c
JOIN pg_class AS t ON t.oid = c.conrelid
JOIN pg_namespace AS n ON n.oid = t.relnamespace
WHERE n.nspname = 'app'
  AND t.relname = 'order_items'
  AND c.contype = 'p';
~~~

Kết quả sẽ cho biết tên constraint và các cột PK đang được định nghĩa. Nếu không có dòng, bảng hiện không có PK theo dữ liệu metadata được truy vấn. Câu SQL dành riêng PostgreSQL.

### 10.2. Tìm FK tham chiếu tới bảng

~~~sql
SELECT
    c.conname AS foreign_key_name,
    c.conrelid::regclass AS referencing_table,
    pg_get_constraintdef(c.oid) AS foreign_key_definition
FROM pg_constraint AS c
WHERE c.contype = 'f'
  AND c.confrelid = 'app.order_items'::regclass
ORDER BY c.conrelid, c.conname;
~~~

Đây là ví dụ truy vấn **chỉ đọc** để xem phụ thuộc. Với một hệ thống nhiều schema, cần có quyền xem metadata phù hợp và kiểm tra thêm những phụ thuộc như view, trigger, job hoặc ORM. Không có FK trực tiếp không có nghĩa chắc chắn không còn ứng dụng sử dụng cột khóa cũ.

### 10.3. Kiểm tra PK hiện tại từ Liquibase

Liquibase có precondition **primaryKeyExists**, thường dùng với tableName và schemaName; tùy phiên bản và DBMS, có thể chỉ định thêm tên PK. Tuy nhiên, với migration đổi PK phức tạp, nên bổ sung truy vấn metadata đọc riêng để xác nhận **đúng constraint và đúng tập cột** chứ không chỉ kết luận “bảng có PK”.

Precondition có thể gặp chi phí snapshot metadata; cần thử hiệu năng của nó ở cơ sở dữ liệu thực và phân biệt kết quả *không đạt* với *lỗi khi đánh giá*.

## 11. PK và INDEX: cơ chế nội bộ tùy DBMS

Tạo PRIMARY KEY thường có tác động lên cấu trúc index:

- **PostgreSQL:** PK được thực thi bằng unique B-tree index. Thêm PK có thể phải quét bảng, tạo index và lấy khóa ở mức phù hợp; khi xóa ràng buộc, index gắn với ràng buộc cũng có thể bị loại bỏ.
- **MySQL/InnoDB:** PK liên quan trực tiếp tới cấu trúc clustered index và cách hàng được tổ chức. Thay PK trên bảng lớn có thể rất tốn kém, thậm chí yêu cầu xây dựng lại bảng hoặc sao chép dữ liệu tùy phiên bản và thuật toán DDL.
- **SQL Server:** PRIMARY KEY có thể dùng chỉ mục clustered hoặc nonclustered theo cấu hình; không nên mặc định mọi PK đều clustered.
- **Oracle:** PK có thể được thực thi bằng index được tạo hoặc sử dụng theo chính sách và cú pháp tương ứng.

Các mô tả này nêu định hướng; điều kiện khóa, thời gian chạy và khả năng online DDL phụ thuộc phiên bản DBMS, kích thước bảng, số index/FK, workload và tham số cụ thể. Liquibase không khiến một thao tác DDL trở nên “online” hay không khóa bảng chỉ vì được khai báo bằng YAML.

### 11.1. Những câu hỏi phải hỏi với bảng lớn

1. Bảng có bao nhiêu hàng, tổng kích thước và tốc độ ghi hiện tại?
2. Có index hoặc unique constraint sẵn đủ điều kiện hỗ trợ PK mới không?
3. DBMS có cơ chế tạo index theo cách giảm gián đoạn hay không?
4. Việc đổi PK có làm xây dựng lại clustered index hoặc toàn bảng không?
5. Bao nhiêu FK, trigger hoặc ứng dụng phụ thuộc khóa?
6. Có đủ dung lượng trống, I/O và thời gian triển khai không?
7. Có thể rollback DDL trong transaction không, hay cần kế hoạch restore?
8. Cần thời gian bảo trì, giới hạn lock timeout hoặc phương án deploy nhiều pha không?

Với PostgreSQL, một số chiến lược giảm gián đoạn xây dựng unique index trước rồi gắn vào PK có thể yêu cầu SQL đặc thù và điều kiện riêng; **CREATE INDEX CONCURRENTLY** không thể được xử lý như mọi DDL giao dịch thông thường. Đừng dùng mẹo tối ưu này khi chưa thử trên phiên bản PostgreSQL và Liquibase cụ thể. Với những hệ quản trị khác, hãy kiểm tra tài liệu DDL online riêng.

## 12. Precondition bảo vệ trước và sau khi đổi khóa

**Precondition** giúp diễn đạt giả định bắt buộc; kết quả không đạt hoặc lỗi đánh giá nên được xử lý rõ ràng.

Ví dụ trước khi thêm PK:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - tableExists:
      schemaName: app
      tableName: orders
  - not:
      - primaryKeyExists:
          schemaName: app
          tableName: orders
  - sqlCheck:
      expectedResult: "0"
      sql: |
        SELECT COUNT(*) FROM app.orders WHERE order_id IS NULL
~~~

Nhưng precondition **không thay thế** việc DBMS thực thi constraint và không phải hàng rào chống thay đổi đồng thời bên ngoài Liquibase. Chẳng hạn một tiến trình không dùng Liquibase vẫn có thể thay đổi bảng. Cần xác minh lại kết quả thực tế sau update.

Khi một precondition phát hiện bảng đã có PK khác hoặc dữ liệu trùng, lựa chọn an toàn là **HALT** và điều tra. Không dùng **MARK_RAN** để ghi changeset như đã chạy nếu PK mới chưa tồn tại; làm thế khiến lịch sử DATABASECHANGELOG không phản ánh schema thực tế.

## 13. Chú ý đến checksum và lịch sử thay đổi

Mỗi changeset của Liquibase được lưu trong **DATABASECHANGELOG** sau khi áp dụng. Nhóm không nên chỉnh sửa nội dung changeset addPrimaryKey hoặc dropPrimaryKey đã chạy ở một môi trường rồi dùng cùng id/author để thực hiện một thay đổi khác.

Ví dụ: đã triển khai changeset 003-add-orders-primary-key cho order_id trên dev, sau đó muốn đổi thành (order_id,store_id). Không nên sửa lại columnNames trong chính changeset lịch sử; checksum có thể không khớp và quan trọng hơn, dev đã có một trạng thái schema khác với database chưa chạy.

Cách phù hợp hơn là:

1. Giữ nguyên changeset lịch sử.
2. Viết changeset mới để chuẩn bị cột và dữ liệu.
3. Viết migration mới để xử lý FK/index liên quan.
4. Viết changeset thay PK theo trình tự được kiểm chứng.
5. Thử trên database có lịch sử thật, không chỉ một database hoàn toàn trống.

**runOnChange** phù hợp hơn với định nghĩa có thể thay thế như view/function, không phải công cụ mặc định để làm mới DDL phá vỡ ràng buộc. **runAlways** càng không nên dùng để lặp lại add/drop PK ở mỗi lần update.

Việc xóa hoặc sửa thủ công DATABASECHANGELOG để “cho Liquibase chạy lại” có thể gây lỗi trùng constraint, mất ràng buộc hoặc chạy thao tác phá hủy ngoài dự kiến. Nếu thấy schema drift, phải điều tra nguyên nhân và chọn migration hòa giải có kiểm soát.

## 14. Rollback: điều gì có thể khôi phục và điều gì không?

Viết rollback cho thay đổi PK không đơn giản là đổi thứ tự add/drop.

| Thay đổi tiến lên | Rollback cấu trúc có thể mô tả | Điều kiện/rủi ro |
|---|---|---|
| Tạo bảng cùng PK | dropTable | Xóa bảng và dữ liệu; thường không an toàn sau khi đã sử dụng |
| addPrimaryKey | dropPrimaryKey | Có thể ảnh hưởng FK và index; ứng dụng có thể kỳ vọng PK tồn tại |
| dropPrimaryKey | addPrimaryKey với cột cũ | Dữ liệu phải còn duy nhất và không NULL; FK/ứng dụng cần tương thích |
| Đổi PK A sang B | Bỏ PK B rồi thêm PK A | Chưa xử lý FK, dữ liệu và code ứng dụng; có thể không khả thi |
| Đổi kiểu cột khóa | Đổi kiểu về cũ | Có thể tràn/mất dữ liệu hoặc không tương thích với khóa ngoại |

**Rollback cấu trúc** khác **khôi phục dữ liệu**. Nếu trong thời gian PK cũ bị gỡ, ứng dụng ghi những hàng có định danh trùng hoặc NULL, lệnh thêm lại PK cũ có thể thất bại. Nếu đã xóa cột khóa cũ, rollback chỉ đổi constraint không thể phục hồi giá trị của cột.

Với production, cần một **kế hoạch phục hồi** gồm điểm backup hợp lệ, khả năng restore theo DBMS và chiến lược forward fix. Một số migration đổi PK nên được xem là bước tiến không đảo ngược về mặt dữ liệu sau một mốc triển khai nhất định.

### 14.1. Một rollback tốt cần ghi rõ

- Trạng thái schema/dữ liệu mà rollback chấp nhận.
- Dữ liệu có thể mất hay cần restore.
- FK và index nào phải được phục hồi.
- Phiên bản ứng dụng có thể chạy sau rollback.
- Thời điểm “không còn có thể quay lại” nếu dữ liệu mới không tương thích.
- Cách xác minh trước và sau rollback.

Nếu không thể tạo rollback tự động an toàn, hãy nói rõ lý do trong tài liệu phát hành và chuẩn bị phương án khôi phục/forward fix thay vì viết một lệnh drop nguy hiểm chỉ để có đủ trường rollback.

## 15. Tích hợp với Java, Spring Boot và ORM

Trong hệ sinh thái Java, lớp entity thường sử dụng trường định danh, ví dụ JPA **@Id** hoặc **@EmbeddedId/@IdClass** cho khóa ghép. Thay đổi khóa chính ở database có thể đòi hỏi sửa mapping và logic repository:

- Đổi BIGINT sang UUID ảnh hưởng kiểu dữ liệu của ID ở Java và request/response.
- Chuyển từ PK đơn sang PK ghép ảnh hưởng equals/hashCode, URL API, cache và các khóa tham chiếu.
- Một số logic update/delete có thể dùng ID cũ trực tiếp; đổi PK trước khi ứng dụng thích nghi gây lỗi.
- Khóa ngoại của các bảng khác và cơ chế lazy loading có thể cần cập nhật.
- Migration cần đi trước hoặc đi cùng triển khai ứng dụng theo thứ tự tương thích.

Nếu Spring Boot khởi động Liquibase tự động và nhiều replica cùng khởi động, cơ chế khóa DATABASECHANGELOGLOCK có thể điều phối những lần update, nhưng không thay thế kế hoạch release. Với thay đổi PK rủi ro cao, việc chạy Liquibase qua **job CI/CD riêng** thường giúp kiểm soát và quan sát tốt hơn, tùy kiến trúc tổ chức.

**Tránh dùng hai nguồn tự động quản lý schema mâu thuẫn.** Chẳng hạn không để cơ chế auto DDL từ ORM đồng thời tự đổi bảng theo một logic khác trong khi Liquibase là nguồn quản lý schema chính. Cần thống nhất quy trình schema migrations cho môi trường production.

## 16. Quy trình CI/CD cho thay đổi PK

Một quy trình triển khai có kiểm chứng có thể đi theo các bước:

1. **Thiết kế:** quyết định khóa mới, kiểu dữ liệu, thứ tự cột, ảnh hưởng business key, FK và ORM.
2. **Preflight dữ liệu:** kiểm tra NULL, duplicate, FK và metadata của PK hiện tại.
3. **Review changelog:** changeset id/author, SQL sinh ra, rollback, nhận xét về DBMS cụ thể.
4. **Validate:** dùng Liquibase kiểm tra cấu trúc changelog.
5. **Preview:** sinh SQL bằng update-sql và xem các lệnh ALTER TABLE, CREATE INDEX, DROP CONSTRAINT tương ứng.
6. **Dev/test:** chạy trên database có dữ liệu và lịch sử gần giống production, không chỉ database rỗng.
7. **Đánh giá vận hành:** đo thời gian, tác động lock, disk/I/O, transaction log và khả năng rollback.
8. **Xác nhận trước production:** đúng JDBC URL, schema, user migration, quyền, backup, mốc phê duyệt.
9. **Triển khai:** chạy một job có chủ sở hữu rõ ràng; theo dõi log và lỗi DBMS.
10. **Hậu kiểm:** xác nhận constraint thực tế, số hàng, tính toàn vẹn FK, khả năng đọc/ghi và bảng DATABASECHANGELOG.

Ví dụ lệnh:

~~~bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status --verbose
liquibase --defaults-file=liquibase.properties update-sql
~~~

Sau khi kiểm tra và được phép triển khai:

~~~bash
liquibase --defaults-file=liquibase.properties update
~~~

Tên lệnh hoặc tùy chọn có thể khác giữa các phiên bản Liquibase; trong tài liệu cũ update-sql có thể được viết updateSQL. **validate không chứng minh dữ liệu đã đủ điều kiện**, còn **update-sql không chứng minh thao tác có thể thực thi nhanh và an toàn trên production**. Cần kiểm thử trực tiếp trên DBMS và dữ liệu đại diện.

Không đưa password vào changelog, script SQL được commit hoặc log. Đích kết nối và secret của dev/test/production phải được quản lý riêng. Có thể giữ cùng changelog nhưng cấp thông số môi trường qua cấu hình runtime có kiểm soát.

## 17. Kiểm chứng sau migration bằng SQL

Sau khi chạy Liquibase, cần kiểm chứng metadata thực tế của PK, không chỉ dựa vào exit code.

### 17.1. Xem constraint PostgreSQL

~~~sql
SELECT
    c.conname,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint AS c
JOIN pg_class AS t ON t.oid = c.conrelid
JOIN pg_namespace AS n ON n.oid = t.relnamespace
WHERE n.nspname = 'app'
  AND t.relname = 'orders'
  AND c.contype = 'p';
~~~

Kết quả phải có tên và tập cột đúng dự kiến. Nếu không có dòng, bảng không có PK theo metadata được truy vấn hoặc bạn đang kết nối nhầm schema/database.

### 17.2. Kiểm tra dữ liệu và quan hệ

Khi PK đã được áp đặt, DBMS bảo đảm tính duy nhất và không NULL của các cột PK đối với thao tác ghi được chấp nhận. Nhưng vẫn nên chạy các kiểm tra nghiệp vụ liên quan: tổng số hàng có thay đổi ngoài ý muốn không, các FK có hợp lệ không, các truy vấn ứng dụng có còn dùng cột khóa đúng không.

Ví dụ với PK order_id:

~~~sql
SELECT COUNT(*) AS total_rows
FROM app.orders;
~~~

Và thử câu truy vấn đọc bằng đúng ID của bộ dữ liệu kiểm thử. Nếu có migration backfill/loại trùng trước đó, cần đối chiếu số hàng trước/sau với kế hoạch đã được phê duyệt. Không xem việc addPrimaryKey thành công là bằng chứng một bước làm sạch dữ liệu trước đó không gây mất dữ liệu.

### 17.3. Kiểm tra lịch sử Liquibase

Tùy schema lưu metadata và cách DBMS xử lý định danh bảng, có thể xem dòng trong DATABASECHANGELOG tương ứng với id/author của changeset:

~~~sql
SELECT id, author, filename, exectype, dateexecuted, md5sum
FROM databasechangelog
WHERE id = '003-add-orders-primary-key'
  AND author = 'platform-team';
~~~

Ví dụ này theo PostgreSQL với cách tên bảng mặc định thường được lưu/nhận diện không phân biệt chữ hoa khi không đặt dấu nháy. Nếu Liquibase đặt bảng lịch sử ở schema khác, phải truy vấn đúng schema. Không sửa trực tiếp bảng lịch sử để che lấp lỗi thiếu PK.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| addPrimaryKey báo có dữ liệu trùng | Giá trị định danh chưa duy nhất | Kiểm tra duplicate và xử lý dữ liệu có phê duyệt |
| addPrimaryKey báo không cho phép NULL | Có hàng NULL trong một hoặc nhiều cột PK | Backfill hợp lệ rồi kiểm tra lại trước khi áp constraint |
| Bảng đã có PRIMARY KEY | Chọn nhầm bảng hoặc chưa lên kế hoạch thay PK | Kiểm tra metadata; không xóa PK cũ theo phản xạ |
| dropPrimaryKey bị từ chối | FK hoặc phụ thuộc khác dùng PK | Liệt kê FK, lên kế hoạch chuyển quan hệ, tránh CASCADE tùy tiện |
| Liquibase báo checksum mismatch | Đã sửa changeset PK từng triển khai | Khôi phục changeset lịch sử, tạo changeset mới cho thay đổi kế tiếp |
| Rollback addPrimaryKey cũ thất bại | Dữ liệu mới không còn duy nhất/không NULL hoặc FK chưa được phục hồi | Đánh giá phương án restore hoặc forward fix |
| Thay PK mất nhiều thời gian | Bảng lớn, xây lại index/table, khóa ghi | Đo trên test đại diện, đánh giá online DDL và maintenance window |
| Thêm PK thành công nhưng ứng dụng lỗi | ORM/API/FK vẫn tham chiếu khóa cũ | Triển khai expand–migrate–contract và kiểm thử version tương thích |
| Index bất ngờ biến mất sau drop PK | Index gắn với ràng buộc bị DBMS loại bỏ | Xem metadata/index và kế hoạch tái tạo index cần thiết |
| PK trỏ nhầm schema | defaultSchemaName/schemaName hoặc JDBC URL sai | Xác minh DB đích, current schema, SQL preview và metadata |
| Khóa ghép không dùng đúng thứ tự cột | Thiết kế columnNames sai thứ tự hoặc kỳ vọng index khác | Kiểm tra định nghĩa PK và hiệu năng truy vấn |
| Việc migrate hai bước để bảng không có PK quá lâu | Drop/add tách thành các đợt không kiểm soát | Tổ chức chuyển đổi ngắn có kiểm tra, giao dịch khi DBMS hỗ trợ |

Lỗi không phải lúc nào cũng sửa được bằng cách xóa constraint, thay metadata hay MARK_RAN. Cần phân biệt vấn đề ở **schema**, **dữ liệu**, **phụ thuộc**, **quyền**, **phiên bản DBMS** và **lịch sử Liquibase**.

## 19. Bài tập thực hành: từ bảng không có PK đến PK ghép

**Bối cảnh:** một bảng lab.order_items có dữ liệu được import, chứa order_id, line_no, product_code và quantity nhưng chưa có khóa chính.

**Yêu cầu:** đặt PK ghép (order_id,line_no), xác minh không mất dữ liệu và có thể kiểm tra rollback ở môi trường học tập.

Các bước:

1. Tạo database/schema **lab** riêng, không sử dụng production.
2. Nhập dữ liệu mẫu hợp lệ và cố ý thêm một số dòng thiếu order_id hoặc cặp khóa trùng để quan sát lỗi.
3. Chạy hai truy vấn kiểm tra NULL và duplicate theo mục 6; ghi kết quả.
4. Xử lý dữ liệu test vi phạm để các truy vấn trở về 0. Không áp cách xóa tự động lên dữ liệu thật.
5. Viết changeset addPrimaryKey với precondition HALT và tên pk_order_items.
6. Chạy validate, status và update-sql trên database lab; đối chiếu columnNames.
7. Chạy update và kiểm tra metadata PostgreSQL của PK.
8. Thử INSERT thêm cặp khóa trùng hoặc giá trị NULL; DBMS phải từ chối.
9. Thử rollback trên bản sao lab chỉ khi không có FK phụ thuộc; kiểm tra chính xác constraint được gỡ.
10. Thử thêm lại PK khi dữ liệu hợp lệ; sau đó cố ý tạo một bản ghi vi phạm để thấy lệnh thêm PK thất bại.

**Kết quả mong đợi:** người học chứng minh được tính duy nhất và NOT NULL của khóa ghép, hiểu vì sao dữ liệu hiện có cần chuẩn hóa trước và không nhầm việc Liquibase chạy “thành công” với khả năng rollback dữ liệu production.

## 20. Tình huống suy luận

### Tình huống A — Bảng có một triệu hàng, nhiều hàng thiếu khóa

Nhóm muốn thêm PK ngay bằng một changeset. Truy vấn kiểm tra cho thấy 15.000 hàng có order_id NULL.

**Phân tích:** không nên dùng MARK_RAN hoặc thêm PK rồi chờ DBMS tự xử lý. Cần xác định quy tắc cấp phát ID, backfill không gây trùng, đo chi phí cập nhật và thử lại trên tập dữ liệu đại diện. Chỉ thêm PK khi bất biến dữ liệu đã đáp ứng.

### Tình huống B — Muốn đổi khóa chính để tối ưu một truy vấn

Ứng dụng có PK customers.customer_id nhưng thường tìm theo email. Một người đề xuất đổi PK thành email.

**Phân tích:** thường nên xem xét UNIQUE(email) và một index phù hợp trước, thay vì đổi PK. Email có thể thay đổi, có thể có vấn đề chuẩn hóa chữ hoa/thường và đang được nhiều thành phần sử dụng. Đổi PK có thể làm hỏng FK và hợp đồng ứng dụng chỉ để tối ưu một truy vấn.

### Tình huống C — PostgreSQL từ chối xóa PK vì FK

Bảng payments.order_id tham chiếu orders(order_id), một changeset muốn drop PK ở orders.

**Phân tích:** phải đánh giá quan hệ tham chiếu và thiết kế FK mới trước. Không tự thêm CASCADE mà chưa biết những constraint sẽ bị xóa. Dùng migration nhiều giai đoạn hoặc chuyển FK theo kế hoạch.

### Tình huống D — Rollback sau khi ứng dụng đã ghi khóa mới

Đã đổi PK order_items từ order_item_id sang (order_id,line_no). Ứng dụng mới tiếp tục tạo dữ liệu bằng định danh mới và ngừng cấp order_item_id.

**Phân tích:** rollback đơn giản bằng drop PK mới rồi add lại PK cũ có thể thất bại vì order_item_id bị NULL/trùng. Cần xác định thời điểm không còn rollback đơn giản, chuẩn bị backfill ID cũ hoặc dùng forward fix/restore, và phối hợp phiên bản ứng dụng.

## 21. Checklist trước production

- [ ] Tôi có lý do rõ ràng để dùng PK một cột hoặc ghép, không chỉ vì một truy vấn đơn lẻ.
- [ ] Tất cả cột PK đều không NULL và tổ hợp khóa không trùng trên dữ liệu thực tế.
- [ ] Tôi đã kiểm tra PK hiện hữu, tên constraint và các FK đang phụ thuộc.
- [ ] Tên và thứ tự cột trong columnNames là có chủ đích.
- [ ] Tôi biết DBMS sẽ tạo/sử dụng index gì, tác động khóa bảng và thời gian ước lượng theo kết quả đo.
- [ ] Changelog có id/author ổn định, không sửa changeset đã triển khai.
- [ ] Các precondition dùng HALT cho trạng thái không đáp ứng hoặc không xác định.
- [ ] Tôi đã kiểm thử migration trên dữ liệu có lịch sử và quy mô đủ đại diện.
- [ ] Tôi đã xem SQL do Liquibase sinh ra và xác minh đúng database/schema.
- [ ] Mọi FK, ORM mapping và API phụ thuộc ID cũ đã có kế hoạch chuyển đổi.
- [ ] Tôi hiểu rollback sẽ làm gì với dữ liệu, FK và index; có kế hoạch restore/forward fix nếu cần.
- [ ] Có backup hợp lệ, thời gian triển khai, quyền migration và chủ sở hữu job rõ ràng.
- [ ] Sau update, metadata PK, dữ liệu và DATABASECHANGELOG được kiểm tra.
- [ ] Không dùng runAlways/runOnChange hoặc sửa trực tiếp lịch sử để ép chạy lại DDL PK.

## 22. Kết luận

Tạo, thay đổi và xóa khóa chính bằng Liquibase đòi hỏi phối hợp **ràng buộc dữ liệu**, **thiết kế định danh**, **chỉ mục**, **khóa ngoại**, **lịch sử migration** và **vận hành database**. Với bảng mới, khai báo PK ngay trong createTable thường là lựa chọn rõ ràng. Với bảng đang có dữ liệu, addPrimaryKey chỉ nên chạy sau khi kiểm tra NULL, trùng khóa và phụ thuộc. Với yêu cầu đổi PK, chiến lược **expand–migrate–contract** giúp hạn chế việc phá vỡ ứng dụng hoặc quan hệ tham chiếu. DropPrimaryKey luôn cần được xem xét tác động đến FK và index.

Trong module DATABASE_SCHEMA_MIGRATION_LIQUIBASE, các change type createTable, addPrimaryKey và dropPrimaryKey cần đi cùng **precondition phù hợp**, **changelog và checksum bất biến theo lịch sử**, **rollback có giới hạn rõ ràng**, cùng quy trình **kiểm chứng dev/test và phê duyệt production** qua Spring Boot hoặc CI/CD. Một migration PK được coi là đáng tin khi không chỉ chạy được, mà còn bảo vệ định danh dữ liệu, giữ tương thích ứng dụng và có đường xử lý sự cố được chuẩn bị trước.

