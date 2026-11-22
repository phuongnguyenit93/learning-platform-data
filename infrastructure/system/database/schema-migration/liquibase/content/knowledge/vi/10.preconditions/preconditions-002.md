# Tiền điều kiện ở cấp changelog và cấp changeset

Khi một migration Liquibase được triển khai, câu hỏi quan trọng không chỉ là “SQL có đúng cú pháp không?” mà còn là **“database đang ở trạng thái phù hợp để chạy thay đổi này hay chưa?”**. Thêm khóa ngoại trước khi bảng tham chiếu tồn tại, đặt NOT NULL khi vẫn còn dữ liệu NULL, hoặc chạy cú pháp PostgreSQL lên MySQL đều có thể khiến quy trình phát hành thất bại. Liquibase cung cấp **precondition (tiền điều kiện)** để kiểm tra những giả định đó trước khi thực thi thay đổi.

Precondition có thể được khai báo ở **cấp changelog** để bảo vệ những giả định chung cho một tập migration, hoặc ở **cấp changeset** để bảo vệ một thao tác cụ thể. Khác biệt này ảnh hưởng trực tiếp đến phạm vi bị chặn khi điều kiện không đạt và cách changeset được ghi vào lịch sử.

Bài thuộc chương **Tiền điều kiện** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung thiết kế đúng hai cấp precondition, lựa chọn phản ứng khi điều kiện sai, tổ chức ví dụ thực tế và kiểm chứng trong pipeline.

## 1. Precondition là gì và kiểm tra được những gì?

Precondition là phép kiểm tra điều kiện trước khi Liquibase áp dụng changeset hoặc xử lý changelog theo phạm vi được cấu hình. Nó không phải lệnh migration và không tự sửa database.

Những câu hỏi thường được biểu diễn bằng precondition:

- Kết nối hiện tại có đúng hệ quản trị PostgreSQL không?
- Bảng customer đã tồn tại trước khi thêm cột email chưa?
- Bảng customer **chưa tồn tại** trước khi createTable phải không?
- Index hoặc constraint đang cần tạo đã tồn tại chưa?
- Một changeset tiền đề đã được ghi nhận trong lịch sử chưa?
- Số bản ghi vi phạm một quy tắc dữ liệu có bằng 0 không?
- Tài khoản đang chạy có phải tài khoản migration được phép không?

Ví dụ, trước khi thêm constraint NOT NULL cho customer.email, có thể kiểm tra dữ liệu:

~~~sql
SELECT COUNT(*)
FROM customer
WHERE email IS NULL;
~~~

Nếu kết quả là 0, giả định “không còn email NULL” đang đúng tại thời điểm kiểm tra. Nếu kết quả khác 0, migration cần dừng hoặc được xử lý theo chính sách. Nếu SQL không chạy được vì thiếu bảng hoặc quyền, đó là **lỗi đánh giá điều kiện**, khác với điều kiện được đánh giá thành công nhưng trả về false.

Precondition không chứng minh toàn bộ quá trình sẽ thành công. Sau khi kiểm tra, database vẫn có thể thay đổi do ứng dụng khác ghi dữ liệu; một câu DDL vẫn có thể lỗi vì khóa bảng, quyền, kiểu dữ liệu hay hành vi transaction. Vì vậy precondition phải đi cùng kiểm thử thực thi và kế hoạch phục hồi.

## 2. Phân biệt cấp changelog và cấp changeset

| Khía cạnh | Precondition cấp changelog | Precondition cấp changeset |
|---|---|---|
| Vị trí | Trực tiếp dưới phần tử gốc databaseChangeLog | Bên trong một changeSet |
| Mục đích | Ràng buộc giả định chung khi xử lý changelog | Kiểm tra trạng thái cần thiết cho đúng một bước thay đổi |
| Phạm vi tác động | Có thể ngăn quá trình xử lý tập changelog tương ứng | Tác động tới changeset chứa điều kiện |
| Ví dụ | Changelog chỉ chạy trên PostgreSQL | Bảng customer chưa tồn tại trước khi tạo |
| Lựa chọn khi không đạt | Thông thường HALT hoặc WARN | HALT, WARN, CONTINUE, MARK_RAN theo ngữ nghĩa được hỗ trợ |
| Rủi ro khi đặt sai | Một điều kiện chỉ đúng lúc cài mới có thể chặn cả các lần nâng cấp sau | Điều kiện chung bị lặp lại và dễ thiếu ở một changeset |

Sơ đồ luồng khái quát:

~~~mermaid
flowchart TD
  A["Đọc changelog"] --> B{"Precondition cấp changelog đạt?"}
  B -->|Đạt| C["Xác định changeset cần chạy"]
  B -->|Không đạt| D["Xử lý onFail hoặc onError ở cấp changelog"]
  C --> E{"Precondition của changeset đạt?"}
  E -->|Đạt| F["Thực hiện thay đổi và ghi lịch sử"]
  E -->|Không đạt| G["Xử lý onFail hoặc onError của changeset"]
  F --> H["Changeset tiếp theo"]
~~~

Đây là luồng minh họa, không có nghĩa mọi nhánh đều được phép tiếp tục. Ví dụ HALT dừng tiến trình; MARK_RAN ghi lịch sử mà không thực thi; CONTINUE cho phép bỏ qua changeset trong lần chạy đó.

### 2.1. Khi nên đặt ở cấp changelog

Cấp changelog phù hợp với những giả định chung **phải đúng cho toàn bộ tài liệu hoặc phạm vi được nạp**, chẳng hạn một changelog dành riêng cho PostgreSQL. Nếu changelog con dùng một extension đặc thù, có thể cân nhắc precondition tại phạm vi changelog con hoặc tại changeset sử dụng extension.

Không nên đặt điều kiện “bảng customer chưa tồn tại” ở cấp changelog gốc nếu cùng changelog ấy sẽ được dùng để nâng cấp database trong tương lai. Khi bảng đã được tạo ở lần triển khai đầu tiên, điều kiện đó sẽ trở thành sai và có thể chặn việc xử lý các changeset mới không liên quan.

### 2.2. Khi nên đặt ở cấp changeset

Cấp changeset dành cho điều kiện **sát thao tác sắp chạy**, chẳng hạn:

- Trước createTable: bảng mục tiêu chưa có.
- Trước addColumn: bảng đã có và cột chưa có.
- Trước addForeignKeyConstraint: hai bảng và các cột cần thiết đã có.
- Trước addNotNullConstraint: không còn bản ghi NULL.
- Trước insert dữ liệu bắt buộc: bản ghi tham chiếu phù hợp đã tồn tại.

Đặt điều kiện cạnh thay đổi giúp reviewer hiểu ý định và giúp lỗi khi triển khai chỉ ra đúng bước cần điều tra.

## 3. Ví dụ YAML: precondition ở cấp changelog

Changelog sau chỉ được thiết kế cho PostgreSQL:

~~~yaml
databaseChangeLog:
  - preConditions:
      - onFail: HALT
      - onError: HALT
      - dbms:
          type: postgresql

  - changeSet:
      id: 001-create-customer
      author: team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Precondition cấp changelog được đặt thành một mục của danh sách databaseChangeLog, cùng cấp với changeSet, không nằm trong changeSet. Nếu kết nối tới DBMS khác, điều kiện dbms không thỏa và HALT dừng triển khai.

Trong dự án thực tế, cũng có thể kiểm tra tài khoản bằng runningAs hoặc kết hợp nhiều điều kiện chung, nhưng đừng đặt ràng buộc tài khoản quá hẹp nếu các môi trường dùng những user migration hợp lệ khác nhau.

## 4. Ví dụ YAML: precondition ở cấp changeset

Changelog sau kiểm tra bảng customer chưa tồn tại trước khi tạo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - not:
            - tableExists:
                tableName: customer
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Ở đây preConditions là một thuộc tính trong changeSet. Nếu bảng đã tồn tại nhưng changeset chưa được ghi nhận trong DATABASECHANGELOG, migration dừng để người vận hành xác minh nguồn gốc của bảng. Không nên tự giả định bảng tồn tại đồng nghĩa với việc tất cả cột, khóa và dữ liệu đều đúng như mong đợi.

Ví dụ bổ sung cột email:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-email
      author: team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
        - not:
            - columnExists:
                tableName: customer
                columnName: email
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: email
                  type: VARCHAR(255)
~~~

Hai điều kiện có ý nghĩa: bảng phải có và cột email chưa có. Đặt chúng ở cấp changeset giúp các thay đổi khác trong changelog không bị phụ thuộc một cách không cần thiết vào trạng thái riêng của cột email.

## 5. Ví dụ XML: cách đặt chính xác trong tài liệu

Trong changelog XML, preConditions cấp changelog là phần tử con trực tiếp của databaseChangeLog:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <preConditions onFail="HALT" onError="HALT">
        <dbms type="postgresql"/>
    </preConditions>

    <changeSet id="001-create-customer" author="team">
        <preConditions onFail="HALT" onError="HALT">
            <not>
                <tableExists tableName="customer"/>
            </not>
        </preConditions>

        <createTable tableName="customer">
            <column name="id" type="BIGINT">
                <constraints primaryKey="true" nullable="false"/>
            </column>
        </createTable>
    </changeSet>
</databaseChangeLog>
~~~

Ví dụ này chứa **cả hai cấp**:

1. Precondition bên ngoài changeSet kiểm tra PostgreSQL.
2. Precondition bên trong changeSet kiểm tra bảng customer chưa có.
3. Nếu cả hai điều kiện phù hợp và changeset chưa áp dụng, Liquibase có thể thực thi createTable.

Hãy tuân thủ đúng vị trí phần tử theo XSD được dùng. Một XML document có thể well-formed nhưng vẫn sai schema Liquibase nếu preConditions hoặc các phần tử con được đặt sai cấp. Đối với YAML, tương đương là kiểm soát chính xác mức thụt lề.

## 6. Phân biệt onFail và onError

**onFail** là cách xử lý khi Liquibase đánh giá precondition thành công nhưng kết quả không đúng như yêu cầu. Ví dụ tableExists trả về false, hoặc sqlCheck trả 5 trong khi expectedResult là 0.

**onError** là cách xử lý khi không thể đánh giá precondition như dự kiến, chẳng hạn truy vấn kiểm tra bị sai cú pháp, thiếu quyền đọc metadata hoặc lỗi kết nối.

| Hành vi | Ý nghĩa | Dùng khi nào |
|---|---|---|
| HALT | Dừng triển khai và báo lỗi | Mặc định nên ưu tiên với điều kiện bắt buộc |
| WARN | Cảnh báo nhưng tiếp tục xử lý | Khi kết quả chỉ mang tính thông tin và việc chạy tiếp được chấp nhận |
| CONTINUE | Bỏ qua changeset hiện tại trong lần chạy; có thể xét lại trong lần tiếp theo | Chỉ dùng tại cấp changeset và phải kiểm tra phụ thuộc |
| MARK_RAN | Không chạy nội dung thay đổi nhưng ghi nhận changeset như đã chạy | Chỉ dùng tại cấp changeset trong tình huống baseline/đồng bộ đã được xác minh |

Ở **cấp changelog**, Liquibase thường chỉ chấp nhận HALT và WARN; **CONTINUE và MARK_RAN chỉ áp dụng ở cấp changeset**. Tùy chọn onFail và onError phải được hiểu riêng; một truy vấn kiểm tra thất bại khi thực thi có thể đi vào nhánh onError thay vì onFail.

### 6.1. HALT cho trạng thái bắt buộc

Nếu bảng cần sửa chưa tồn tại hoặc còn dữ liệu vi phạm constraint, HALT làm lỗi lộ rõ trước khi thay đổi tiếp. Đây là lựa chọn phù hợp cho migration production có tính bắt buộc.

### 6.2. WARN có thể cho phép thay đổi chạy tiếp

WARN không biến điều kiện không đạt thành trạng thái an toàn. Nếu precondition yêu cầu bảng tồn tại nhưng báo WARN khi bảng thiếu, changeset vẫn có thể được thực thi rồi thất bại ở câu SQL. Chỉ dùng WARN khi điều kiện thực sự là cảnh báo được phép bỏ qua.

### 6.3. CONTINUE và phụ thuộc chuỗi migration

CONTINUE có thể hợp lý cho một changeset tùy chọn độc lập, nhưng không nên dùng cho bước tạo bảng mà mọi changeset kế tiếp cần. Nếu bỏ qua bước đầu rồi chạy bước sau, database có thể rơi vào trạng thái lệch kỳ vọng giữa các môi trường.

### 6.4. MARK_RAN cần kiểm chứng độc lập

MARK_RAN ghi nhận changeset như đã chạy dù thay đổi không được thực hiện. Chỉ nên dùng khi nhóm đã kiểm tra độc lập rằng kết quả mong muốn **thực sự hiện diện**, chẳng hạn trong một quy trình baseline có kiểm toán.

Nếu bảng customer đã tồn tại nhưng thiếu constraint, việc dùng MARK_RAN cho changeset tạo bảng có thể làm lịch sử trông hoàn chỉnh trong khi schema thực tế sai. Không dùng MARK_RAN như cách phổ biến để “bỏ qua lỗi và deploy tiếp”.

## 7. Kết hợp điều kiện bằng AND, OR và NOT

Liquibase hỗ trợ logic kiểm tra phức hợp:

- AND yêu cầu tất cả điều kiện con đúng.
- OR yêu cầu ít nhất một điều kiện con đúng.
- NOT đảo kết quả điều kiện con.

Ví dụ XML yêu cầu có bảng và cột:

~~~xml
<preConditions onFail="HALT">
    <and>
        <tableExists tableName="customer"/>
        <columnExists tableName="customer" columnName="email"/>
    </and>
</preConditions>
~~~

Ví dụ chỉ cho phép PostgreSQL hoặc MySQL:

~~~xml
<preConditions onFail="HALT">
    <or>
        <dbms type="postgresql"/>
        <dbms type="mysql"/>
    </or>
</preConditions>
~~~

Ví dụ yêu cầu index chưa tồn tại:

~~~xml
<preConditions onFail="HALT">
    <not>
        <indexExists
            tableName="customer"
            indexName="idx_customer_email"/>
    </not>
</preConditions>
~~~

Trong YAML có thể viết:

~~~yaml
preConditions:
  - onFail: HALT
  - and:
      - tableExists:
          tableName: customer
      - columnExists:
          tableName: customer
          columnName: email
~~~

Nhiều điều kiện trực tiếp thường được kết hợp với ý nghĩa AND. Với logic có nhiều nhóm và phủ định, khai báo and/or/not tường minh giúp tránh hiểu sai. Liquibase có thể đánh giá nhóm logic theo cơ chế dừng sớm, vì vậy các precondition phải được thiết kế là phép kiểm tra chỉ đọc, không phụ thuộc side effect.

## 8. Các loại precondition thường dùng

| Loại | Nội dung kiểm tra | Ví dụ sử dụng |
|---|---|---|
| dbms | Loại DBMS hiện tại | Giới hạn changelog theo PostgreSQL |
| runningAs | User đang kết nối | Áp chính sách tài khoản migration |
| tableExists | Bảng có tồn tại | Kiểm tra tiền đề trước addColumn |
| columnExists | Cột có tồn tại | Thay đổi cột hoặc tránh thêm trùng |
| indexExists | Index có tồn tại | Tạo index mới hoặc kiểm tra index tiền đề |
| primaryKeyExists | Khóa chính có tồn tại | Thêm hoặc sửa primary key |
| foreignKeyConstraintExists | Khóa ngoại có tồn tại | Tránh thêm constraint trùng |
| changeSetExecuted | Changeset đã được ghi nhận trong lịch sử | Ràng buộc mốc migration khi thật cần |
| sqlCheck | Giá trị từ câu SQL có bằng expectedResult | Kiểm tra dữ liệu legacy |
| customPrecondition | Điều kiện do nhóm tự triển khai | Tình huống đặc thù chưa được core hỗ trợ |

Các kiểm tra metadata đôi khi cần đọc snapshot database và có thể tốn tài nguyên trên schema lớn. Khi có nhiều schema và đối tượng trùng tên, khai báo schemaName ở những precondition hỗ trợ để tránh kết luận từ sai đối tượng.

Không phải DBMS nào cũng có cùng danh mục đối tượng, quyền metadata hoặc khả năng transaction. Kiểm tra DBMS/phiên bản thực tế nếu precondition dùng cú pháp hoặc đối tượng đặc thù.

## 9. Kiểm tra dữ liệu bằng sqlCheck

sqlCheck phù hợp cho những điều kiện mà chỉ kiểm tra tên bảng/cột là chưa đủ. Ví dụ, trước khi đặt customer.email thành NOT NULL:

~~~xml
<changeSet id="003-require-email" author="team">
    <preConditions onFail="HALT" onError="HALT">
        <tableExists tableName="customer"/>
        <columnExists tableName="customer" columnName="email"/>
        <sqlCheck expectedResult="0">
            SELECT COUNT(*) FROM customer WHERE email IS NULL
        </sqlCheck>
    </preConditions>

    <addNotNullConstraint
        tableName="customer"
        columnName="email"
        columnDataType="VARCHAR(255)"/>

    <rollback>
        <dropNotNullConstraint
            tableName="customer"
            columnName="email"
            columnDataType="VARCHAR(255)"/>
    </rollback>
</changeSet>
~~~

Nếu truy vấn chạy được và trả 0, điều kiện dữ liệu đúng. Nếu trả một số khác, onFail được áp dụng. Nếu SQL lỗi vì thiếu quyền hoặc bảng, onError được áp dụng.

Có thể viết tương tự trong YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-require-email
      author: team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer
        - columnExists:
            tableName: customer
            columnName: email
        - sqlCheck:
            expectedResult: "0"
            sql: SELECT COUNT(*) FROM customer WHERE email IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: email
            columnDataType: VARCHAR(255)
      rollback:
        - dropNotNullConstraint:
            tableName: customer
            columnName: email
            columnDataType: VARCHAR(255)
~~~

sqlCheck thường cần trả một kết quả vô hướng, phổ biến là một hàng và một cột, để Liquibase so sánh với expectedResult. Nên chọn một biểu diễn ổn định, ví dụ số lượng bản ghi hoặc giá trị 0/1.

**Giới hạn vận hành:** COUNT(*) có thể quét nhiều dòng và gây tải trên bảng lớn. Nếu chỉ cần biết có ít nhất một bản ghi vi phạm, có thể tối ưu bằng EXISTS hoặc giới hạn kết quả theo DBMS và trả 0/1. Tránh câu SQL có side effect trong precondition. Mọi kết quả đúng chỉ đúng tại thời điểm kiểm tra; nếu ứng dụng đang ghi dữ liệu đồng thời, vẫn có thể phát sinh dòng vi phạm trước khi constraint được áp dụng.

## 10. Ví dụ trọn vẹn: một changelog có cả hai cấp

Giả sử cần tạo bảng customer trên PostgreSQL rồi yêu cầu cột email không được NULL:

~~~yaml
databaseChangeLog:
  - preConditions:
      - onFail: HALT
      - onError: HALT
      - dbms:
          type: postgresql

  - changeSet:
      id: 001-create-customer
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - not:
            - tableExists:
                tableName: customer
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
                  type: VARCHAR(255)
      rollback:
        - dropTable:
            tableName: customer

  - changeSet:
      id: 002-require-customer-email
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer
        - columnExists:
            tableName: customer
            columnName: email
        - sqlCheck:
            expectedResult: "0"
            sql: SELECT COUNT(*) FROM customer WHERE email IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: email
            columnDataType: VARCHAR(255)
      rollback:
        - dropNotNullConstraint:
            tableName: customer
            columnName: email
            columnDataType: VARCHAR(255)
~~~

**Diễn tiến mong đợi:**

1. Khi xử lý changelog, Liquibase kiểm tra kết nối đúng PostgreSQL.
2. Changeset 001 chưa chạy: kiểm tra bảng customer chưa tồn tại; nếu đạt, tạo bảng.
3. Changeset 002 chưa chạy: kiểm tra bảng/cột đã có và không có email NULL; nếu đạt, thêm NOT NULL.
4. Liquibase ghi lịch sử cho các changeset được áp dụng thành công. Khi chạy update lần sau trên cùng database, các changeset đã chạy thường không được thực hiện lại.
5. Nếu sau đó thêm changeset 003, precondition cấp changelog vẫn có ý nghĩa chung trong khi tiền điều kiện “bảng chưa tồn tại” nằm riêng trong changeset 001.

Changelog minh họa thao tác rollback có thể xóa bảng customer. Với database chứa dữ liệu thật, dropTable không phải cách khôi phục an toàn nếu chưa có backup hoặc kế hoạch thay thế.

## 11. Precondition tương tác với DATABASECHANGELOG như thế nào?

Liquibase dùng ID, author và đường dẫn changelog (hoặc logicalFilePath đã cấu hình) để nhận diện changeset. Bảng DATABASECHANGELOG ghi lịch sử, kết quả thực thi và checksum theo cơ chế của Liquibase.

Trên PostgreSQL có thể xem:

~~~sql
SELECT id, author, filename, exectype, dateexecuted, orderexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

| Tình trạng | Vai trò của precondition |
|---|---|
| Changeset chưa áp dụng | Precondition cục bộ có thể được kiểm tra trước khi thực thi |
| Changeset đã áp dụng, chạy update thông thường | Liquibase thường bỏ qua changeset; precondition không phải cơ chế giám sát drift liên tục |
| Changeset dùng runAlways hoặc runOnChange | Cần đánh giá lại tương tác giữa điều kiện và cơ chế chạy lại |
| onFail=MARK_RAN ở cấp changeset | Ghi nhận changeset đã chạy mặc dù không thực thi thay đổi |
| onFail=CONTINUE ở cấp changeset | Changeset bị bỏ qua trong lần này, có thể được xét lại về sau |

Precondition và checksum có nhiệm vụ khác nhau. Checksum phát hiện những thay đổi liên quan đến nội dung changeset đã được ghi nhận; precondition kiểm tra điều kiện database khi nó được đánh giá. Precondition đạt không chứng minh checksum sẽ đúng, và checksum đúng không chứng minh schema/dữ liệu hiện hữu không bị thay đổi thủ công.

Không sửa trực tiếp DATABASECHANGELOG, xóa checksum hay thay đổi ID/author/đường dẫn chỉ để ép lịch sử đi theo ý muốn. Khi phát hiện sai lệch, xác định nguyên nhân rồi bổ sung migration sửa chữa hoặc thực hiện baseline theo quy trình có kiểm chứng.

## 12. Đặt precondition khi changelog có include và includeAll

Một hệ thống có thể dùng changelog gốc và các changelog con:

~~~text
db/changelog/
├── master.yaml
└── modules/
    ├── customer.yaml
    ├── orders.yaml
    └── reference-data.yaml
~~~

Nếu mọi module dùng PostgreSQL, có thể đặt điều kiện DBMS chung ở master. Nếu một thao tác cụ thể trong orders.yaml yêu cầu index hoặc extension đặc thù, điều kiện nên nằm ngay trong changeset đó hoặc trong phạm vi changelog con phù hợp.

Tránh đặt điều kiện “chưa có bảng orders” ở master khi hệ thống cần dùng cùng changelog cho việc nâng cấp ở các phiên bản sau. Trên production đã tồn tại orders, điều kiện chung có thể chặn changeset mới không liên quan.

Quy tắc thiết kế:

- Cấp càng chung thì giả định càng phải ổn định qua mọi lần chạy phù hợp.
- Cấp càng cụ thể thì điều kiện càng sát thao tác và dễ chẩn đoán.
- Không dùng precondition thay thế thứ tự dependency của include/includeAll.
- Không dùng các bộ lọc context/label để âm thầm bỏ qua một changeset tiền đề của các changeset khác.

## 13. Nhiều môi trường, context/label và vấn đề dữ liệu

Local, test, staging và production có thể khác về dữ liệu, quyền và thời điểm triển khai. Precondition phải diễn đạt điều kiện **đúng về mặt nghiệp vụ**, không vô tình phụ thuộc trạng thái ngẫu nhiên ở local.

Những tình huống cần tránh:

- sqlCheck giả định ID tự tăng của bản ghi tham chiếu luôn bằng 1 trên mọi môi trường.
- Changelog gốc dùng runningAs với đúng user local, trong khi pipeline production dùng user migration khác theo thiết kế.
- Dev đã backfill xong, production còn bản ghi legacy bị NULL.
- Một bảng được tạo thủ công ở staging nhưng chưa có trong DATABASECHANGELOG.
- Changeset tạo bảng chỉ có context dev trong khi changeset thêm khóa ngoại lại chạy ở production.
- Chỉ kiểm thử trên database trống, bỏ qua đường nâng cấp từ dữ liệu đã có.

Hãy kiểm thử cả **fresh install** và **upgrade từ trạng thái database của phiên bản trước**. Nếu dùng nhiều DBMS hoặc nhiều phiên bản database, cần thử trên các đích được hỗ trợ.

Context và label là bộ lọc lựa chọn changeset, không phải hệ thống phân quyền. Quyền DDL, bí mật kết nối và quyền phát hành production phải do database/pipeline kiểm soát.

## 14. Transaction, concurrency và giới hạn của tiền điều kiện

Precondition là phép kiểm tra tại một thời điểm. Giữa lúc kiểm tra và áp dụng migration, ứng dụng vẫn có thể ghi dữ liệu.

Ví dụ sqlCheck thấy không còn email NULL, nhưng một tiến trình ứng dụng ghi bản ghi có email NULL ngay trước khi addNotNullConstraint. Lệnh tạo constraint có thể lỗi. Bảng DATABASECHANGELOGLOCK giúp điều phối những tiến trình Liquibase cùng chạy migration, nhưng không tự ngăn toàn bộ transaction nghiệp vụ của ứng dụng.

Cần thiết kế quy trình phù hợp với database:

1. Mở rộng schema có tương thích ngược khi cần.
2. Cập nhật cách ứng dụng ghi dữ liệu.
3. Backfill dữ liệu cũ theo lô nếu bảng lớn.
4. Kiểm tra lại dữ liệu với precondition đủ hiệu quả.
5. Áp dụng constraint khi có kế hoạch kiểm soát thời điểm, khóa và lưu lượng.
6. Quan sát ứng dụng và database sau triển khai.

Một số DBMS có DDL không rollback được trong transaction hoặc tự commit. Nếu changeset gồm nhiều thao tác và gặp lỗi giữa chừng, database có thể ở trạng thái thực thi một phần. Precondition không tự hoàn tác trạng thái đó. Hãy giữ changeset nhỏ, rõ và chuẩn bị forward-fix hoặc restore khi cần.

## 15. Precondition có thay thế kiểm thử rollback không?

Một changeset có thể có precondition đúng lúc áp dụng nhưng khi rollback lại có điều kiện khác:

- Khi tạo index cần index chưa tồn tại; khi gỡ index cần index tồn tại.
- Khi tạo bảng chưa có dữ liệu; khi rollback dropTable bảng có thể chứa dữ liệu kinh doanh.
- Khi thêm constraint cần dữ liệu phù hợp; khi gỡ constraint cần đánh giá khả năng tương thích với nhiều phiên bản ứng dụng.

Không coi precondition ở chiều triển khai tiến là bằng chứng rollback an toàn. Phải kiểm thử rollback trên bản sao dữ liệu và kiểm tra SQL, khóa, dependency. Nếu thay đổi dữ liệu một chiều, kế hoạch có thể phải là backup/restore hoặc forward-fix thay cho rollback thông thường.

## 16. Quy trình xác minh trong CLI, Spring Boot và CI/CD

Một quy trình kiểm chứng gợi ý:

1. Review changelog: precondition cấp chung có thực sự là bất biến chung không?
2. Validate để phát hiện lỗi khai báo được phiên bản Liquibase hỗ trợ.
3. Xem danh sách changeset chưa chạy và SQL dự kiến.
4. Chạy migration trên database mới.
5. Chạy migration trên database nâng cấp có dữ liệu gần thực tế.
6. Thử riêng trường hợp điều kiện không đạt và trường hợp điều kiện bị lỗi.
7. Kiểm tra bảng, constraint, dữ liệu và DATABASECHANGELOG sau chạy.
8. Đánh giá rollback, backup, quyền và trình tự triển khai production.

Lệnh CLI minh họa, khi kết nối và changelog đã được cấu hình:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
~~~

Các lệnh và tham số cần được đối chiếu với phiên bản Liquibase của dự án. update thực hiện thay đổi thật; chỉ chạy sau khi xác nhận đúng database đích. Với chế độ tạo trước SQL, một số precondition có hành vi kiểm tra riêng theo phiên bản/cấu hình, nên không dựa vào update-sql như phép thử duy nhất.

Spring Boot có thể tự chạy Liquibase lúc khởi động nếu dependency và cấu hình cho phép. Trong môi trường có nhiều replica, nên quy định rõ tiến trình nào được chạy migration, khi nào ứng dụng nhận traffic và cách giám sát khi precondition HALT làm startup thất bại. Điều này giúp tránh triển khai ứng dụng lên schema chưa đáp ứng yêu cầu.

## 17. Xử lý lỗi precondition có hệ thống

Nếu Liquibase báo precondition failed hoặc error:

1. **Xác định cấp khai báo:** lỗi của master/changelog con hay changeset nào?
2. **Kiểm tra môi trường:** JDBC URL, DBMS, schema, user, context/label có đúng không?
3. **Phân biệt fail/error:** kết quả kiểm tra sai hay bản thân phép kiểm tra không chạy được?
4. **Kiểm tra trạng thái thực:** bảng, cột, index, constraint, dữ liệu bằng truy vấn độc lập.
5. **Đối chiếu lịch sử:** ID, author, filename, exectype trong DATABASECHANGELOG.
6. **Sửa nguyên nhân:** backfill dữ liệu, bổ sung migration, điều chỉnh điều kiện đặt sai cấp hoặc sửa quyền.
7. **Thử lại trên bản sao:** xác minh đường nâng cấp trước khi áp dụng thật.

Ví dụ bảng customer tồn tại nhưng changeset tạo bảng chưa từng được Liquibase ghi nhận: hãy điều tra cấu trúc bảng và đường dẫn changelog. Không đổi ngay onFail thành MARK_RAN chỉ để pipeline tiếp tục.

Nếu lỗi đến từ quyền metadata hoặc SQL sai, cũng không nên chuyển tùy tiện onError sang WARN. Hãy giải quyết đúng quyền và cú pháp.

## 18. Bài thực hành và checklist

Dựng một PostgreSQL lab riêng, rồi thực hiện các tình huống sau:

1. Tạo changelog với dbms cấp changelog và not tableExists cấp changeset; chạy trên database trống.
2. Tạo bảng customer thủ công trên một database lab khác, chạy lại changeset tạo bảng và quan sát onFail=HALT.
3. Chuẩn bị dữ liệu có email NULL trước changeset addNotNullConstraint; kiểm tra sqlCheck không đạt.
4. Sửa dữ liệu, chạy lại và xác nhận constraint được tạo.
5. Cố tình dùng SQL sai trong sqlCheck trên một bản sao để quan sát onError, phân biệt với onFail.
6. Thử nhóm and/or/not trên các trạng thái bảng/cột khác nhau.
7. Trên changeset **tùy chọn và độc lập**, thử CONTINUE rồi MARK_RAN trong database có thể xóa; so sánh DATABASECHANGELOG và lần chạy tiếp theo.
8. Xác minh rollback của constraint, đồng thời phân tích lý do không được dùng dropTable bừa bãi khi có dữ liệu.
9. Chạy thử cả từ database mới và database đã áp dụng phiên bản trước.

| Câu hỏi trước khi merge | Bằng chứng cần có |
|---|---|
| Precondition đặt đúng cấp? | Phạm vi ảnh hưởng khi fail được mô tả rõ |
| Changelog-level condition đúng cho mọi lần nâng cấp? | Đã thử trên database cũ và mới |
| onFail và onError có chính sách phù hợp? | Test trường hợp trả false và trường hợp lỗi |
| Dùng WARN, CONTINUE, MARK_RAN có chủ đích? | Review hậu quả với các changeset phụ thuộc |
| AND/OR/NOT diễn đạt đúng logic? | Đã thử các tổ hợp đạt/không đạt |
| sqlCheck trả kết quả ổn định và đủ nhẹ? | SQL được thử trên dữ liệu đại diện |
| Metadata check đúng schema? | URL, schema, quyền được xác minh |
| Context/label không bỏ qua bước tiền đề? | Thử đúng filter của các môi trường |
| Rollback hoặc forward-fix an toàn? | Đã thử và có backup khi cần |
| Có thể truy vết sau triển khai? | Bảng, dữ liệu và DATABASECHANGELOG được đối chiếu |

**Nguyên tắc lựa chọn:** đặt precondition **cấp changelog** cho những giả định chung, bền vững trong toàn bộ phạm vi changelog; đặt precondition **cấp changeset** cho trạng thái cần thiết ngay trước một thay đổi cụ thể. Ưu tiên HALT với điều kiện bắt buộc, chỉ dùng CONTINUE/MARK_RAN khi hiểu chính xác tác động lịch sử, và kiểm thử cả lúc điều kiện đạt lẫn không đạt. Precondition giúp giảm rủi ro khi triển khai Liquibase, nhưng vẫn phải được kết hợp với checksum, lịch sử migration, kiểm thử dữ liệu, rollback và điều phối phát hành.

# Tiền điều kiện ở cấp changelog và cấp changeset trong Liquibase

Trong migration database, câu hỏi quan trọng không chỉ là **“cần chạy câu SQL nào?”**, mà còn là **“database hiện tại có đáp ứng điều kiện để chạy thay đổi này hay không?”**. Một changeset có thể hợp lệ về cú pháp nhưng vẫn không phù hợp với hệ quản trị, thiếu bảng nền, dùng sai tài khoản hoặc gặp dữ liệu chưa sẵn sàng để áp dụng ràng buộc. **Preconditions (tiền điều kiện)** là cơ chế Liquibase cho phép kiểm tra các giả định trước khi tiến hành thay đổi.

Bài học thuộc chương **Tiền điều kiện** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Trọng tâm của bài là **hai phạm vi khai báo precondition: cấp changelog và cấp changeset**. Hai phạm vi có mục đích, điểm đánh giá và khả năng xử lý khi điều kiện không thỏa khác nhau. Dùng nhầm phạm vi có thể khiến cả một đợt triển khai dừng không cần thiết, hoặc nguy hiểm hơn, một changeset bị đánh dấu đã chạy dù chưa thực sự tạo đối tượng mong muốn.

Sau bài học, bạn sẽ có thể:

- Phân biệt tiền điều kiện toàn cục ở cấp changelog và tiền điều kiện cục bộ ở cấp changeset.
- Lựa chọn điều kiện kiểm tra schema, DBMS, tài khoản, dữ liệu và lịch sử phù hợp.
- Kết hợp điều kiện bằng AND, OR, NOT với logic rõ ràng.
- Giải thích hành vi onFail, onError, HALT, WARN, CONTINUE và MARK_RAN.
- Hiểu tương tác với DATABASECHANGELOG, checksum, rollback và chế độ sinh SQL.
- Xây dựng quy trình kiểm chứng trước khi chạy Liquibase update ở nhiều môi trường.

## 1. Precondition là gì?

Precondition là phép kiểm tra trạng thái hoặc đặc điểm của database trước khi Liquibase thực thi phần thay đổi liên quan. Kết quả có thể là:

1. **Thỏa điều kiện:** Liquibase có thể tiếp tục xử lý theo quy tắc chung của changeset.
2. **Không thỏa điều kiện (failure):** Phép kiểm tra thực hiện được nhưng kết quả không đúng kỳ vọng.
3. **Lỗi khi kiểm tra (error):** Không thể đánh giá điều kiện do SQL sai, thiếu quyền, lỗi kết nối, thiếu đối tượng hoặc lỗi thực thi khác.

Ví dụ:

- Chỉ chạy migration PostgreSQL khi DBMS của kết nối là PostgreSQL.
- Xác minh user kết nối là tài khoản migration được cấp phép.
- Chỉ thêm cột mới khi bảng nền đã tồn tại và cột chưa tồn tại.
- Chỉ thêm ràng buộc NOT NULL sau khi không còn dòng chứa NULL.
- Xác minh một changeset tiên quyết đã được Liquibase ghi nhận.

**Precondition không phải changeset.** Nó không mô tả một thao tác thay đổi schema/dữ liệu cần được lưu thành migration riêng, mà quyết định liệu chương trình có tiếp tục, dừng hoặc xử lý changeset theo chính sách đã cấu hình.

Sơ đồ tư duy đơn giản:

~~~mermaid
flowchart TD
    A[Liquibase đọc changelog] --> B{Precondition cấp changelog}
    B -->|Đạt| C[Đối chiếu các changeset với lịch sử]
    B -->|Fail/Error| X[Áp dụng onFail hoặc onError của changelog]
    C --> D{Changeset còn cần xử lý và đủ filter?}
    D -->|Không| N[Không thực thi changeset trong lần này]
    D -->|Có| E{Precondition cấp changeset}
    E -->|Đạt| F[Thực thi migration]
    E -->|Fail/Error| Y[Áp dụng onFail hoặc onError của changeset]
    F --> G[Ghi kết quả vào DATABASECHANGELOG]
~~~

Sơ đồ chỉ mô tả luồng chính. Liquibase còn xét filter context/label, dbms, runOnChange, runAlways, precondition outcome, transaction và lock.

## 2. Hai phạm vi: changelog và changeset

Precondition có thể được đặt tại **cấp changelog** hoặc **bên trong một changeset**.

| Tiêu chí | Cấp changelog (global) | Cấp changeset (local) |
|---|---|---|
| Vị trí | Phần preConditions trực tiếp dưới databaseChangeLog | Phần preConditions bên trong changeSet |
| Phạm vi ý nghĩa | Điều kiện nền cho toàn bộ luồng changelog | Điều kiện cần cho một changeset cụ thể |
| Ví dụ | Kết nối phải là PostgreSQL hoặc đúng user migration | Bảng tồn tại, cột chưa tồn tại, dữ liệu hợp lệ |
| Ảnh hưởng | Có thể dừng hoặc cảnh báo trước khi tiếp tục với changelog | Có thể dừng, cảnh báo, bỏ qua hoặc đánh dấu một changeset theo chính sách |
| onFail/onError | Chỉ hỗ trợ HALT và WARN theo quy tắc phạm vi global | Có thể dùng HALT, WARN, CONTINUE, MARK_RAN theo phạm vi local |
| Khả năng tái sử dụng | Áp dụng chung cho nhiều changeset | Nằm sát migration cần kiểm tra |
| Rủi ro nếu dùng sai | Một điều kiện cục bộ có thể chặn toàn bộ tập migration | Có thể bỏ sót điều kiện nền chung hoặc đánh dấu sai lịch sử |

**Quy tắc chọn phạm vi:** hỏi **“Điều kiện này phải đúng cho tất cả migration trong changelog, hay chỉ cần đúng để chạy một thay đổi cụ thể?”**.

Nếu là yêu cầu về toàn bộ môi trường, cân nhắc global. Nếu là giả định của một phép thay đổi, dùng local.

### 2.1. Khi nào dùng cấp changelog?

Hợp lý khi tất cả changeset trong changelog được thiết kế cho cùng loại DBMS hoặc khi cần một điều kiện vận hành áp dụng cho cả luồng, ví dụ một tài khoản được quản lý tập trung.

Ví dụ:

- Toàn bộ changelog chỉ hỗ trợ PostgreSQL.
- Luồng migration cần một tài khoản có danh tính rõ ràng.
- Một thuộc tính changelog bắt buộc phải được khai báo trước khi cập nhật.

Không nên áp đặt điều kiện global chỉ vì một changeset cần nó. Chẳng hạn, nếu một changelog gồm nhiều loại thay đổi nhưng chỉ một bước yêu cầu bảng legacy còn tồn tại, đặt tableExists ở cấp changelog có thể chặn cả các thay đổi độc lập.

### 2.2. Khi nào dùng cấp changeset?

Hợp lý khi một thay đổi cần tiền đề riêng:

- Thêm index khi cột đích đã tồn tại.
- Xóa bảng cũ khi ứng dụng đã ngừng sử dụng nó.
- Backfill sau khi đã thêm cột mới.
- Thêm unique constraint khi dữ liệu không còn trùng.
- Dừng thay đổi nếu một thay đổi tiên quyết chưa được ghi nhận.

Đặt điều kiện ngay cạnh changeset giúp người review hiểu lý do, hiệu lực và rủi ro của thay đổi.

## 3. Ví dụ XML so sánh hai phạm vi trong cùng changelog

XML biểu diễn rõ nhất cấu trúc lồng nhau giữa global và local.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        http://www.liquibase.org/xml/ns/dbchangelog
        https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <!-- Tiền điều kiện toàn cục: toàn bộ changelog này dành cho PostgreSQL -->
    <preConditions onFail="HALT" onError="HALT">
        <dbms type="postgresql"/>
    </preConditions>

    <changeSet id="20261119-001" author="orders-team">
        <!-- Tiền điều kiện cục bộ: chưa có bảng order_note -->
        <preConditions onFail="HALT" onError="HALT">
            <not>
                <tableExists tableName="order_note" schemaName="public"/>
            </not>
        </preConditions>

        <createTable tableName="order_note" schemaName="public">
            <column name="id" type="bigint">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="note_text" type="varchar(1000)">
                <constraints nullable="false"/>
            </column>
        </createTable>

        <rollback>
            <dropTable tableName="order_note" schemaName="public"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

Trong ví dụ:

1. Global **dbms** kiểm tra kết nối có phải PostgreSQL không. Nếu không đúng, **HALT** chặn luồng.
2. Khi Liquibase xác định changeset chưa được xử lý hoặc cần xử lý lại theo cơ chế của nó, precondition local kiểm tra **order_note** chưa tồn tại.
3. Nếu bảng đã tồn tại nhưng changeset chưa được ghi nhận, **HALT** làm lộ trạng thái bất thường để điều tra thay vì lặng lẽ xem migration thành công.
4. Nếu điều kiện đạt, Liquibase thực thi createTable, rồi ghi nhận trạng thái theo cơ chế của nó.
5. Rollback là phần đảo ngược riêng, không phải precondition; xóa bảng có thể làm mất dữ liệu thật.

**Lưu ý:** Đây là ví dụ dành cho một database PostgreSQL mới, với schema **public** có sẵn và user đủ quyền. Không nên copy vào một database có bảng order_note đã được quản lý bởi migration khác.

## 4. Ví dụ tương đương với changelog YAML

Trong YAML, tiền điều kiện là nhánh **preConditions**, còn changeSet có nhánh preConditions riêng.

~~~yaml
databaseChangeLog:
  - preConditions:
      - onFail: HALT
      - onError: HALT
      - dbms:
          type: postgresql

  - changeSet:
      id: "20261119-002"
      author: "orders-team"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: order_note
        - not:
            - columnExists:
                schemaName: public
                tableName: order_note
                columnName: created_at
      changes:
        - addColumn:
            schemaName: public
            tableName: order_note
            columns:
              - column:
                  name: created_at
                  type: timestamp
      rollback:
        - dropColumn:
            schemaName: public
            tableName: order_note
            columnName: created_at
~~~

Ví dụ giả định bảng **order_note** đã tồn tại nhờ một changeset trước đó. Global DBMS guard áp dụng cho cả changelog; local preConditions yêu cầu bảng tồn tại và cột **created_at** chưa tồn tại.

Cần chú ý cú pháp YAML của Liquibase: preConditions thường được biểu diễn bằng **danh sách các phần tử** gồm thuộc tính xử lý và các điều kiện. Cách parser hỗ trợ các thuộc tính và condition cụ thể phụ thuộc phiên bản, vì vậy nên chạy **validate** với chính phiên bản Liquibase của dự án.

### 4.1. Vì sao không dùng global để kiểm tra cột created_at?

Nếu đặt **not columnExists** ở cấp changelog, đến khi cột đã được thêm, lần update tiếp theo có thể không qua được global precondition, kể cả khi changeset thêm cột đã chạy thành công. Điều này đặc biệt không phù hợp với mong muốn update lặp lại mà không gây lỗi.

Trong khi đó, precondition local của một changeset thông thường **không được đánh giá lại** nếu changeset đó đã được ghi nhận và không cần chạy lại. Nó bảo vệ thời điểm áp dụng thay đổi chứ không bắt toàn bộ changelog luôn thỏa một trạng thái tạm thời.

## 5. Các precondition thường gặp

Liquibase cung cấp nhiều điều kiện dựng sẵn. Tên và tính khả dụng của mỗi loại có thể khác giữa DBMS, định dạng và phiên bản.

| Loại | Kiểm tra | Phạm vi phù hợp |
|---|---|---|
| **dbms** | Loại DBMS của kết nối | Global nếu toàn changelog phụ thuộc DBMS; local nếu chỉ một changeset |
| **runningAs** | Username dùng trong kết nối | Global khi cần tài khoản migration chuẩn; local nếu chỉ một thao tác |
| **tableExists** | Bảng có tồn tại không | Local khi thao tác liên quan bảng |
| **columnExists** | Cột có tồn tại trong bảng không | Local khi thêm/đổi cột hoặc xác nhận tiền đề |
| **indexExists** | Index có tồn tại không | Local khi tạo/xóa index |
| **viewExists** | View có tồn tại không | Local cho thay đổi view |
| **foreignKeyConstraintExists** | Ràng buộc khóa ngoại có tồn tại không | Local với thay đổi constraint |
| **primaryKeyExists** | Khóa chính có tồn tại không | Local trước các thay đổi PK |
| **sequenceExists** | Sequence có tồn tại không | Local, tùy hỗ trợ DBMS |
| **changeSetExecuted** | Một changeset nhất định đã được Liquibase ghi nhận | Local để thể hiện quan hệ phụ thuộc đã có trong lịch sử |
| **changeLogPropertyDefined** | Thuộc tính changelog đã được định nghĩa, có thể kiểm tra giá trị | Global hoặc local tùy mục đích |
| **sqlCheck** | Kết quả scalar của SQL khớp giá trị kỳ vọng | Local để kiểm tra điều kiện nghiệp vụ/dữ liệu |
| **customPrecondition** | Kiểm tra bằng mã tùy biến | Trường hợp thực sự cần và được kiểm soát về classpath/version |

**Không phải mọi precondition đều chỉ là phép truy vấn nhẹ.** Một số phép kiểm tra metadata có thể dùng cơ chế snapshot trên DBMS hoặc tình huống nhất định. Trên hệ thống lớn, cần tính đến chi phí metadata và tốc độ chạy nếu một changelog có hàng trăm precondition.

## 6. Phối hợp AND, OR và NOT

Một tiền điều kiện thường không chỉ có một phép kiểm tra. Liquibase hỗ trợ những tổ hợp logic để diễn đạt điều kiện phức tạp.

- **AND**: mọi điều kiện bên trong phải đạt.
- **OR**: ít nhất một điều kiện bên trong đạt.
- **NOT**: đảo ngược kết quả điều kiện con.

Ví dụ XML: chỉ thêm index khi bảng và cột đều có, đồng thời index chưa tồn tại.

~~~xml
<changeSet id="20261119-003" author="orders-team">
    <preConditions onFail="HALT" onError="HALT">
        <and>
            <tableExists tableName="order_note" schemaName="public"/>
            <columnExists tableName="order_note"
                          columnName="created_at" schemaName="public"/>
            <not>
                <indexExists tableName="order_note"
                             indexName="idx_order_note_created_at"
                             schemaName="public"/>
            </not>
        </and>
    </preConditions>

    <createIndex tableName="order_note"
                 schemaName="public"
                 indexName="idx_order_note_created_at">
        <column name="created_at"/>
    </createIndex>

    <rollback>
        <dropIndex indexName="idx_order_note_created_at"
                   tableName="order_note"
                   schemaName="public"/>
    </rollback>
</changeSet>
~~~

Điều kiện này giúp tránh tạo index trùng, nhưng **không thay thế yêu cầu khớp trạng thái lịch sử**. Nếu index đã tồn tại do thao tác ngoài Liquibase, cần điều tra xem nó có đúng cấu trúc, cột và mục đích hay không trước khi quyết định HALT, MARK_RAN hoặc sửa chữa.

### 6.1. Đánh giá lười (lazy evaluation)

Với tổ hợp logic, Liquibase thường sử dụng đánh giá ngắn mạch: trong AND, khi một điều kiện đã fail, những điều kiện còn lại có thể không cần đánh giá; trong OR, nếu điều kiện đã đạt, những điều kiện còn lại có thể được bỏ qua.

Điều này có hai hệ quả:

1. Đặt điều kiện rẻ và dễ kiểm tra trước có thể giảm công việc không cần thiết.
2. Không nên xem mọi điều kiện con là cơ chế bắt buộc để thu thập toàn bộ thông tin lỗi.

Nếu cần bản ghi chẩn đoán chi tiết cho mọi tiền đề, có thể bổ sung kiểm tra riêng trong pipeline thay vì phụ thuộc vào thứ tự evaluation của precondition.

### 6.2. OR để hỗ trợ nhiều môi trường

Giả sử một changelog có thể chạy trên PostgreSQL hoặc MySQL. Có thể mô tả lựa chọn:

~~~xml
<preConditions onFail="HALT" onError="HALT">
    <or>
        <dbms type="postgresql"/>
        <dbms type="mysql"/>
    </or>
</preConditions>
~~~

Điều kiện cho phép hai DBMS đó. Tuy nhiên, **việc cho phép kết nối không có nghĩa SQL bên trong tự động tương thích với cả hai**. Nếu dùng SQL đặc thù DBMS, hãy chia changeset theo DBMS hoặc sử dụng change type trừu tượng phù hợp và kiểm tra thực tế trên cả hai hệ.

## 7. Phân biệt onFail và onError

Đây là sự khác nhau quan trọng nhất khi chọn chính sách xử lý.

**onFail** áp dụng khi phép kiểm tra thực hiện bình thường nhưng trả về kết quả **không thỏa**. Ví dụ sqlCheck yêu cầu 0 dòng không hợp lệ nhưng thực tế có 12 dòng.

**onError** áp dụng khi hệ thống **không thể thực hiện/đánh giá** precondition. Ví dụ SQL trong sqlCheck tham chiếu một cột không tồn tại khiến database báo lỗi.

| Tình huống | Phân loại điển hình | Ví dụ |
|---|---|---|
| Bảng đang tồn tại nhưng điều kiện yêu cầu không tồn tại | Failure | NOT tableExists trả về false |
| Dữ liệu có 3 bản ghi NULL khi yêu cầu 0 | Failure | sqlCheck trả về 3 thay vì 0 |
| Câu SQL kiểm tra sai tên cột và bị database từ chối | Error | SQL exception trong sqlCheck |
| Không đọc được metadata do lỗi quyền hoặc lỗi driver | Error | Lỗi trong quá trình kiểm tra |
| User đang kết nối khác user được yêu cầu | Failure | runningAs không khớp |

Không phải mọi lỗi SQL đều cho cùng loại ngoại lệ trên mọi phiên bản/DBMS; bảng là mô hình tư duy để chọn chính sách.

**Khuyến nghị khi dữ liệu và schema quan trọng:** đặt cả **onFail="HALT"** và **onError="HALT"** trừ khi có lý do được đánh giá rõ ràng cho chính sách khác. Thiếu quyền đọc dữ liệu không nên bị hiểu nhầm là “điều kiện không thỏa nên bỏ qua”.

## 8. Các lựa chọn HALT, WARN, CONTINUE và MARK_RAN

Liquibase hỗ trợ các kết quả xử lý khác nhau cho precondition, nhưng **phạm vi được phép dùng không giống nhau**.

| Chính sách | Hành vi khái quát | Phạm vi thường hỗ trợ | Rủi ro |
|---|---|---|---|
| **HALT** | Dừng luồng update khi điều kiện fail/error | Global và local | Dừng cả đợt triển khai; phù hợp với ràng buộc bắt buộc |
| **WARN** | Ghi cảnh báo rồi tiếp tục theo quy tắc | Global và local | Có thể vẫn chạy SQL dù điều kiện cảnh báo chưa đạt |
| **CONTINUE** | Bỏ qua changeset hiện tại, để nó có thể được xét lại trong lần update sau | Local | Migration bị trì hoãn; phụ thuộc có thể thất bại |
| **MARK_RAN** | Không chạy phần thay đổi nhưng đánh dấu changeset là đã xử lý | Local | Dễ che khuất trạng thái thiếu schema/dữ liệu |

**Trong precondition cấp changelog, chỉ dùng HALT hoặc WARN.** CONTINUE và MARK_RAN là lựa chọn xử lý một changeset cục bộ; chúng không có ý nghĩa phù hợp để áp dụng cho cả changelog.

### 8.1. Ví dụ HALT: xử lý sai trạng thái

~~~xml
<preConditions onFail="HALT" onError="HALT">
    <tableExists tableName="order_note" schemaName="public"/>
</preConditions>
~~~

Nếu bảng không có, migration nên dừng để nhóm xác minh changeset tạo bảng đã được áp dụng hay chưa. Đây là tình huống thường phù hợp với HALT.

### 8.2. Ví dụ CONTINUE: trì hoãn một changeset

~~~xml
<changeSet id="20261119-004" author="orders-team">
    <preConditions onFail="CONTINUE" onError="HALT">
        <tableExists tableName="optional_legacy_source" schemaName="public"/>
    </preConditions>

    <sql>
        INSERT INTO order_note (id, note_text)
        SELECT id, note_text
        FROM optional_legacy_source;
    </sql>
</changeSet>
~~~

Khi bảng nguồn không có, Liquibase bỏ qua changeset hiện tại thay vì đánh dấu là đã thực thi. Ở lần update khác, changeset có thể được xét lại. **Điều này có thể phù hợp cho một migration phụ thuộc dữ liệu tùy chọn**, nhưng không thích hợp nếu những changeset sau buộc phải có dữ liệu đã được nhập.

Ví dụ không viết rollback vì dữ liệu chèn có thể trùng lặp hoặc cần khóa định danh nguồn; khi triển khai thật phải thiết kế khả năng lặp lại và phục hồi.

### 8.3. Ví dụ MARK_RAN: chỉ dùng khi trạng thái tương đương đã được xác minh

~~~xml
<changeSet id="20261119-005" author="orders-team">
    <preConditions onFail="MARK_RAN" onError="HALT">
        <not>
            <tableExists tableName="legacy_migration_marker"
                         schemaName="public"/>
        </not>
    </preConditions>

    <createTable tableName="legacy_migration_marker"
                 schemaName="public">
        <column name="id" type="bigint"/>
    </createTable>
</changeSet>
~~~

Nếu bảng đã tồn tại, changeset được đánh dấu **MARK_RAN** mà không thực thi createTable. Nhưng precondition chỉ kiểm tra **sự tồn tại**, không khẳng định bảng có cấu trúc, constraint hoặc dữ liệu đúng. Nếu bảng do một migration ngoài Liquibase tạo ra với schema không tương thích, đánh dấu đã chạy có thể tạo ra lịch sử giả định sai.

Vì vậy, chỉ chọn MARK_RAN khi tổ chức có cơ sở đáng tin cậy để xác nhận trạng thái đã đạt tương đương với kết quả mong muốn, và khi việc ghi nhận này là một phần của kế hoạch chuyển giao/baseline có kiểm chứng.

### 8.4. Ví dụ WARN: cảnh báo không phải ràng buộc an toàn

~~~xml
<preConditions onFail="WARN" onError="HALT">
    <runningAs username="orders_migrator"/>
</preConditions>
~~~

Cấu hình này có thể hữu ích trong môi trường thử nghiệm để cảnh báo khi user khác dự kiến, nhưng với production, việc chạy bằng tài khoản không được phê duyệt thường cần **HALT** thay vì WARN.

## 9. onFailMessage và onErrorMessage: thông báo dễ điều tra

Có thể bổ sung thông báo riêng để đội vận hành hiểu lý do dừng.

~~~xml
<preConditions
    onFail="HALT"
    onError="HALT"
    onFailMessage="Database is not PostgreSQL"
    onErrorMessage="Cannot verify database type">
    <dbms type="postgresql"/>
</preConditions>
~~~

Thông báo cần mô tả **giả định nào đang bị vi phạm**, không phải chỉ lặp lại “migration failed”.

Đối với local:

~~~xml
<preConditions
    onFail="HALT"
    onError="HALT"
    onFailMessage="Column status must already exist on invoice">
    <columnExists schemaName="public"
                  tableName="invoice"
                  columnName="status"/>
</preConditions>
~~~

Không đưa mật khẩu, token, thông tin cá nhân hoặc dữ liệu nhạy cảm vào message. Thông báo precondition có thể xuất hiện trong log ứng dụng hoặc CI/CD.

## 10. Precondition sqlCheck cho điều kiện dữ liệu

Các built-in condition như **tableExists** hoặc **columnExists** phù hợp với cấu trúc. Khi cần xác minh dữ liệu, **sqlCheck** thường cho phép chạy một truy vấn trả về **một giá trị scalar** và so sánh với **expectedResult**.

Giả sử chuẩn bị thêm NOT NULL cho cột status của bảng invoice. Trước đó, các dòng status NULL phải được xử lý.

Ví dụ XML:

~~~xml
<changeSet id="20261119-006" author="billing-team">
    <preConditions onFail="HALT" onError="HALT"
                   onFailMessage="invoice.status still contains NULL">
        <sqlCheck expectedResult="0">
            SELECT COUNT(*) FROM public.invoice WHERE status IS NULL
        </sqlCheck>
    </preConditions>

    <addNotNullConstraint
        schemaName="public"
        tableName="invoice"
        columnName="status"
        columnDataType="varchar(24)"/>
</changeSet>
~~~

Đây là bước **contract** sau một migration backfill. Nếu truy vấn trả về 5, precondition fail và Liquibase không áp dụng ràng buộc.

### 10.1. Vì sao dùng COUNT thay vì SELECT dữ liệu?

sqlCheck thường so sánh một giá trị trả về với expectedResult. Câu SQL:

~~~sql
SELECT COUNT(*)
FROM public.invoice
WHERE status IS NULL;
~~~

có dạng scalar rõ ràng, dễ review. Trong một số DBMS, kiểu trả về, định dạng boolean hoặc cách chuyển chuỗi có thể khác. Nên ưu tiên số nguyên hoặc giá trị đơn giản, kiểm tra hành vi của phiên bản Liquibase và driver.

Không nên dùng truy vấn trả về nhiều hàng/nhiều cột rồi giả định Liquibase tự hiểu “không có lỗi”. Với precondition phức tạp, hãy biến yêu cầu thành phép kiểm tra rõ ràng, chẳng hạn số lượng vi phạm phải bằng 0.

### 10.2. Ví dụ kiểm tra dữ liệu trùng trước unique constraint

~~~sql
SELECT COUNT(*)
FROM (
    SELECT invoice_code
    FROM public.invoice
    GROUP BY invoice_code
    HAVING COUNT(*) > 1
) duplicate_codes;
~~~

Nếu kết quả lớn hơn 0, không nên tạo unique constraint cho invoice_code trước khi có kế hoạch sửa dữ liệu. Đối với bảng rất lớn, truy vấn GROUP BY có thể tốn CPU, bộ nhớ hoặc I/O; cần cân nhắc hiệu năng khi precondition chạy trong khung triển khai production.

### 10.3. Những điều sqlCheck không bảo đảm

- Truy vấn chỉ là **ảnh chụp logic tại thời điểm kiểm tra**. Nếu ứng dụng tiếp tục ghi dữ liệu song song, trạng thái có thể thay đổi trước khi constraint được áp dụng.
- sqlCheck không tự đảm bảo transaction bao phủ cả kiểm tra và DDL với cùng mức cô lập trên mọi DBMS.
- Nếu user không có quyền đọc bảng, điều kiện có thể error chứ không phải fail.
- Kết quả COUNT=0 không đảm bảo toàn bộ invariant khác của ứng dụng đã được thỏa.

Với thay đổi có rủi ro cao, dùng thêm kiểm soát ghi dữ liệu, khóa phù hợp hoặc cơ chế DBMS bảo vệ invariant ngay trong DDL.

## 11. Precondition changeSetExecuted và phụ thuộc lịch sử

Một changeset có thể yêu cầu changeset khác đã được Liquibase ghi nhận trước đó.

Ví dụ XML:

~~~xml
<changeSet id="20261119-007" author="billing-team">
    <preConditions onFail="HALT" onError="HALT">
        <changeSetExecuted
            id="20261119-001"
            author="billing-team"
            changeLogFile="db/changelog/releases/2026/11/001-invoice.xml"/>
    </preConditions>

    <createIndex tableName="invoice"
                 schemaName="public"
                 indexName="idx_invoice_status">
        <column name="status"/>
    </createIndex>
</changeSet>
~~~

**changeLogFile** phải khớp định danh changelog mà Liquibase ghi nhận cho changeset tiên quyết. Nếu tệp đã được di chuyển hoặc logicalFilePath khác, có thể không khớp dù schema thật đã chứa đối tượng tương ứng.

Không nên dùng changeSetExecuted thay thế việc kiểm tra **đối tượng thực tế** khi thay đổi phụ thuộc schema quan trọng. Một changeset được ghi nhận MARK_RAN có thể không thực sự thực thi phần SQL; hoặc schema có thể đã bị sửa thủ công sau đó.

Để kiểm tra đầy đủ, có thể kết hợp:

- changeSetExecuted, nếu cần xác minh luồng lịch sử.
- tableExists/columnExists, nếu cần xác minh đối tượng.
- sqlCheck, nếu cần xác minh dữ liệu.

## 12. Precondition ở cấp changelog: các tình huống áp dụng và giới hạn

Global precondition nên bảo vệ **giả định chung** của changelog, không phải chi tiết nhất thời của một changeset.

### 12.1. Ví dụ: changelog dành riêng cho PostgreSQL

~~~xml
<preConditions onFail="HALT" onError="HALT">
    <dbms type="postgresql"/>
</preConditions>
~~~

Hợp lý nếu toàn bộ changelog chỉ có SQL PostgreSQL, hoặc hệ thống cam kết một DBMS. Nếu sau này muốn tái sử dụng changelog trên MySQL, cần tái thiết kế các điều kiện/changelog, không chỉ đổi một dòng dbms.

### 12.2. Ví dụ: yêu cầu tài khoản migration chuẩn

~~~xml
<preConditions onFail="HALT" onError="HALT">
    <runningAs username="orders_migrator"/>
</preConditions>
~~~

Giúp phát hiện cấu hình sai principal. Nhưng username chỉ là một tín hiệu; cần xác nhận **host, port, database/service, schema và quyền thật**. Hai hệ thống riêng có thể có user trùng tên, vì vậy runningAs không phải bằng chứng chắc chắn đang ở đúng database.

### 12.3. Tình huống không nên dùng global

Giả sử changelog có ba bước:

1. Tạo bảng invoice.
2. Backfill invoice.status.
3. Bổ sung NOT NULL cho invoice.status.

Nếu đặt precondition global **invoice.status phải không còn NULL**, lần chạy đầu trên database mới sẽ fail trước cả bước tạo/bổ sung cột. Điều kiện đó chỉ đúng cho **bước 3**, không phải cho mọi bước.

Hãy đặt sqlCheck vào changeset bổ sung NOT NULL. Global guard có thể chỉ kiểm tra DBMS hoặc cấu hình môi trường.

### 12.4. Vị trí so với thay đổi khác

Trong XML, preConditions cấp changelog là phần tử trực tiếp của databaseChangeLog, không nằm trong changeSet. Với YAML, phần tử preConditions là một entry của danh sách databaseChangeLog, cùng cấp với các entry changeSet. Nên để global guard ở phần đầu changelog để rõ ràng và dễ review.

Khi dùng nhiều changelog lồng nhau qua include, cần kiểm tra phạm vi thực tế của từng global precondition đối với tệp chứa nó và luồng include. Không mặc định global guard trong một tệp con có thể bảo vệ toàn bộ root changelog độc lập.

## 13. Precondition ở cấp changeset: gắn sát thay đổi cần bảo vệ

Local precondition có ưu điểm là **phản ánh điều kiện của một bước cụ thể** và chỉ được xử lý khi Liquibase xét changeset đó để thực thi.

Ví dụ: tạo index nếu bảng và cột đã tồn tại, đồng thời index chưa tồn tại.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-008"
      author: "billing-team"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: invoice
        - columnExists:
            schemaName: public
            tableName: invoice
            columnName: status
        - not:
            - indexExists:
                schemaName: public
                tableName: invoice
                indexName: idx_invoice_status
      changes:
        - createIndex:
            schemaName: public
            tableName: invoice
            indexName: idx_invoice_status
            columns:
              - column:
                  name: status
      rollback:
        - dropIndex:
            schemaName: public
            tableName: invoice
            indexName: idx_invoice_status
~~~

Nếu index đã tồn tại trong một database nhưng changeset chưa được ghi nhận, HALT buộc nhóm xác định nguyên nhân. Không tự dùng MARK_RAN khi chưa xác nhận index hiện hữu có đúng cột, kiểu index và đặc điểm cần thiết.

### 13.1. Liên hệ với tính lặp lại

Một changeset đã được đánh dấu EXECUTED thường không chạy lại trên những lần update sau. Vì vậy, local guard kiểu **NOT tableExists** không cần “luôn đúng mãi mãi”. Nó chỉ cần đúng khi changeset thực sự sắp chạy.

Đây là lý do local guard thích hợp cho một điều kiện sẽ **thay đổi từ true sang false sau khi migration thành công**, chẳng hạn “bảng chưa tồn tại” trước CREATE TABLE.

### 13.2. Local guard không phải phép thay thế giao dịch

Một precondition kiểm tra “bảng chưa tồn tại” có thể đạt tại thời điểm T1 nhưng một tiến trình khác tạo bảng ở T2. Liquibase có cơ chế khóa khi chạy migration nhưng khóa của Liquibase không tự ngăn mọi thao tác ngoài Liquibase. Quyền database, transaction và phối hợp triển khai vẫn quan trọng.

## 14. Precondition khi sinh SQL: onSqlOutput

Liquibase hỗ trợ việc **sinh SQL dự kiến** thay vì thực thi ngay, ví dụ với lệnh **update-sql**. Điều này đặt ra câu hỏi: precondition có được đánh giá trên database khi chỉ sinh SQL hay không?

Trong cấu hình precondition XML có thuộc tính **onSqlOutput**; các giá trị điển hình:

| Giá trị | Ý nghĩa khái quát |
|---|---|
| **TEST** | Đánh giá precondition trong quá trình sinh SQL |
| **IGNORE** | Không đánh giá precondition khi sinh SQL |
| **FAIL** | Báo lỗi thay vì tiến hành sinh SQL nếu không thể chấp nhận cơ chế này |

Ví dụ:

~~~xml
<preConditions onFail="HALT"
               onError="HALT"
               onSqlOutput="TEST">
    <dbms type="postgresql"/>
</preConditions>
~~~

Cần kiểm tra phiên bản Liquibase và kiểu changelog đang sử dụng vì cách biểu diễn và mặc định của onSqlOutput có thể thay đổi. Một bản SQL sinh ra khi bỏ qua điều kiện không chứng minh tất cả precondition sẽ đạt lúc update thật.

**Quy trình an toàn:** chạy validate, status và update-sql trên một database đại diện, sau đó chạy kiểm tra trực tiếp những invariant quan trọng (schema, số lượng dữ liệu vi phạm, quyền). Sinh SQL là lớp review, không thay thế migration thử nghiệm.

## 15. Formatted SQL và phạm vi hỗ trợ precondition

Với **Liquibase formatted SQL**, chỉ thị thường có dạng comment:

~~~sql
--liquibase formatted sql

--changeset billing-team:20261119-009 dbms:postgresql
--preconditions onFail:HALT onError:HALT
--precondition-sql-check expectedResult:0 SELECT COUNT(*) FROM public.invoice WHERE status IS NULL;
ALTER TABLE public.invoice ALTER COLUMN status SET NOT NULL;

--rollback ALTER TABLE public.invoice ALTER COLUMN status DROP NOT NULL;
~~~

Trong ví dụ, sqlCheck yêu cầu không có invoice.status NULL trước khi bổ sung NOT NULL.

**Lưu ý phạm vi và phiên bản:**

- Các chỉ thị precondition trong formatted SQL có khả năng hỗ trợ khác nhau giữa những phiên bản Liquibase.
- **sqlCheck** là dạng thường dùng trong formatted SQL; không nên giả định toàn bộ loại precondition YAML/XML đều có cùng cú pháp SQL comment.
- Các dạng precondition bổ sung trong formatted SQL được hỗ trợ ở những phiên bản mới có thể không chạy trên công cụ cũ của pipeline.
- Nếu cần logic lồng nhau phức tạp hoặc yêu cầu portable nhiều DBMS, YAML/XML/JSON có thể dễ biểu diễn và validate hơn.

Không nên dán nguyên các precondition XML vào đầu tệp SQL và giả định Liquibase sẽ đọc được. Hãy chọn một cú pháp đúng với định dạng changelog.

## 16. Phối hợp precondition với context, label và dbms

Precondition là **kiểm tra**, còn context và label chủ yếu là **bộ lọc lựa chọn changeset**. Chúng có thể xuất hiện trong cùng changeset.

Ví dụ YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010"
      author: "reporting-team"
      dbms: postgresql
      labels: "reporting"
      contextFilter: "staging"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: invoice
            schemaName: public
      changes:
        - createView:
            viewName: invoice_count
            schemaName: public
            selectQuery: "SELECT COUNT(*) AS total FROM public.invoice"
      rollback:
        - dropView:
            viewName: invoice_count
            schemaName: public
~~~

Phân vai:

- **dbms** lọc theo loại hệ quản trị.
- **contextFilter** cho phép chọn theo context mà runtime cung cấp.
- **labels** phân loại và cho phép lọc theo nhóm thay đổi.
- **preConditions** kiểm tra bảng invoice thực sự có tồn tại.

Nếu filter loại bỏ changeset thì precondition của changeset thông thường không cần đánh giá. Nếu filter chọn changeset nhưng bảng thiếu, precondition mới có vai trò dừng migration.

Không nên suy ra context **staging** đồng nghĩa JDBC URL chắc chắn kết nối tới staging. Filter không thay thế cấu hình endpoint, database, schema hoặc tài khoản.

## 17. Mối liên hệ với DATABASECHANGELOG và checksum

Liquibase theo dõi changeset trong **DATABASECHANGELOG**. Một số cột thường dùng:

| Cột | Ý nghĩa |
|---|---|
| ID | ID changeset |
| AUTHOR | Tác giả |
| FILENAME | Đường dẫn changelog định danh |
| EXECTYPE | Kiểu xử lý (ví dụ EXECUTED, MARK_RAN, RERAN) |
| DATEEXECUTED | Thời điểm ghi nhận |
| MD5SUM | Checksum được lưu |
| CONTEXTS, LABELS | Metadata phục vụ truy vết |
| ORDEREXECUTED | Thứ tự ghi nhận |

Khi **onFail=MARK_RAN**, changeset có thể được lưu với **EXECTYPE=MARK_RAN** dù phần migration không thực thi. Điều này cần được phân biệt rõ với **EXECTYPE=EXECUTED**. Tuy nhiên, cả hai đều tác động tới việc Liquibase xem xét changeset ở những lần update sau theo quy tắc của nó.

Khi **onFail=CONTINUE**, changeset thường không được ghi nhận là đã thực thi, do đó có thể còn pending trong lần chạy sau.

Khi **HALT**, phần thay đổi liên quan không nên được đánh dấu thành công chỉ vì tiến trình đã bắt đầu; đội vận hành cần kiểm tra tình trạng thực tế và lịch sử sau lỗi, nhất là nếu có thay đổi không hỗ trợ transaction hoặc lỗi xảy ra sau các changeset khác trong cùng đợt.

### 17.1. Precondition có bảo vệ khỏi checksum mismatch không?

Không. Precondition không phải cách bỏ qua kiểm tra checksum. Nếu nội dung của một changeset đã triển khai bị sửa, Liquibase có thể phát hiện checksum không khớp. Không dùng thay đổi precondition, clear-checksums hoặc chỉnh DATABASECHANGELOG thủ công để che vấn đề lịch sử.

Khi cần sửa cấu trúc hoặc dữ liệu tiếp sau migration đã chạy, cách phổ biến là **thêm changeset mới**.

### 17.2. Precondition changeSetExecuted có bảo đảm dữ liệu tồn tại không?

Không hoàn toàn. Một changeset có thể đã được đánh dấu MARK_RAN hoặc các thao tác bên ngoài Liquibase đã làm trạng thái schema khác với kỳ vọng. Nếu tính đúng đắn phụ thuộc đối tượng hoặc dữ liệu, hãy kiểm tra trạng thái thật thay vì chỉ đọc cột lịch sử.

## 18. Precondition và rollback: phạm vi không giống nhau

Precondition chủ yếu kiểm soát **điều kiện trước khi thực thi thay đổi**. Rollback mô tả **cách đảo ngược** changeset, là quy trình khác. Một changeset có rollback không đồng nghĩa precondition giúp rollback dữ liệu an toàn.

Ví dụ:

- Trước CREATE TABLE, điều kiện NOT tableExists có thể phù hợp.
- Khi rollback DROP TABLE, điều kiện này không còn là điều kiện có ý nghĩa cho việc xóa bảng.
- Nếu đã có dữ liệu thật, DROP TABLE có thể làm mất dữ liệu dù changeset ban đầu hợp lệ.

Với migration dữ liệu:

~~~sql
UPDATE invoice
SET status = 'PAID'
WHERE paid_at IS NOT NULL
  AND status IS NULL;
~~~

Precondition có thể kiểm tra cột **paid_at** tồn tại và số dòng vi phạm điều kiện nào đó. Nhưng để đảo ngược update, cần biết những dòng nào bị thay đổi bởi chính migration; chỉ đặt status về NULL có thể làm mất thông tin hợp lệ.

Vì vậy, trong thiết kế migration thực tế cần phân biệt:

1. **Precondition:** có được phép chạy không?
2. **Changeset:** thực hiện thay đổi gì?
3. **Rollback/forward fix:** khôi phục thế nào nếu cần?
4. **Post-migration verification:** làm sao biết kết quả đúng?

## 19. Tình huống điển hình: chạy lần đầu và chạy lại

Giả sử cần tạo bảng **audit_event**, với local precondition NOT tableExists.

### Tình huống A: database mới và lịch sử rỗng

- Bảng audit_event chưa tồn tại.
- Changeset chưa có trong DATABASECHANGELOG.
- Precondition đạt; CREATE TABLE chạy.
- Liquibase ghi nhận changeset.

Đây là luồng bình thường.

### Tình huống B: chạy update lần thứ hai

- Bảng audit_event đã tồn tại do lần đầu tạo thành công.
- Changeset đã được ghi nhận.
- Liquibase thông thường không chạy lại changeset.
- Precondition local không phải liên tục yêu cầu bảng vắng mặt sau lần chạy đầu.

Đây chính là lý do local precondition phù hợp với điều kiện có tính tạm thời.

### Tình huống C: bảng tồn tại nhưng changeset chưa có lịch sử

- Có người đã tạo bảng thủ công, hoặc database được import một phần.
- Precondition NOT tableExists fail.
- Với HALT, Liquibase dừng để điều tra.
- Với MARK_RAN, Liquibase có thể đánh dấu đã xử lý mà không tạo bảng.

**Không mặc định chọn MARK_RAN** nếu chưa xác minh bảng đã có đúng schema, constraint, index và quyền mong muốn.

### Tình huống D: có lỗi quyền hoặc metadata

- User không có quyền đọc metadata hoặc không có quyền truy vấn bảng.
- Precondition có thể error.
- Với onError=HALT, dừng và điều tra quyền, connection hoặc driver.

Trường hợp này không nên coi là “bảng không tồn tại”.

## 20. Tình huống case study: thay đổi ràng buộc dữ liệu trong production

Một ứng dụng hóa đơn có bảng **invoice**, cột **status** hiện cho phép NULL. Mục tiêu là chuyển sang NOT NULL để bảo đảm chất lượng dữ liệu.

### Kế hoạch đúng thứ tự

**Bước 1 — Expand.** Tạo cột status nếu cột chưa tồn tại, hoặc bảo đảm ứng dụng có thể ghi trạng thái mới. Precondition local kiểm tra schema tiên quyết.

**Bước 2 — Migrate.** Backfill các dòng có status NULL theo quy tắc nghiệp vụ. Cần đánh giá chi phí cập nhật, chia batch khi cần và thiết kế khôi phục dữ liệu.

**Bước 3 — Verify.** Chạy truy vấn:

~~~sql
SELECT COUNT(*)
FROM public.invoice
WHERE status IS NULL;
~~~

Kỳ vọng **0**.

**Bước 4 — Contract.** Thêm NOT NULL, với local sqlCheck yêu cầu expectedResult=0. Nếu vẫn còn NULL, HALT để xử lý tiếp thay vì MARK_RAN.

**Bước 5 — Deploy application.** Ứng dụng phải tương thích với ràng buộc mới; kiểm tra dữ liệu sau triển khai.

### Vì sao không đặt điều kiện “status không NULL” ở cấp changelog?

Vì ở giai đoạn đầu, dữ liệu chưa được backfill. Global guard sẽ chặn ngay bước cần thiết để sửa dữ liệu. Điều kiện này là tiền đề cho **bước contract**, nên đặt ở changeset tương ứng.

### Vì sao không dùng MARK_RAN khi còn NULL?

Vì MARK_RAN có thể ghi nhận rằng bước thêm NOT NULL đã được xử lý trong khi constraint chưa thực sự có trong database. Những changeset hoặc ứng dụng về sau có thể dựa vào invariant sai.

### Vì sao vẫn cần khóa và kiểm soát ghi đồng thời?

Một truy vấn COUNT=0 chỉ kiểm tra tại một thời điểm. Nếu ứng dụng cũ vẫn ghi NULL ngay sau kiểm tra, thao tác thêm NOT NULL có thể thất bại hoặc gây tranh chấp. Cần phối hợp phiên bản ứng dụng, transaction, khóa và phương thức áp ràng buộc phù hợp DBMS.

## 21. Kiểm chứng precondition trước khi update

Một pipeline migration an toàn nên kết hợp **kiểm tra cấu hình**, **kiểm tra changelog** và **kiểm tra dữ liệu**.

Quy trình:

1. Xác nhận JDBC URL, DBMS, database, schema và tài khoản migration.
2. Xác nhận changelog artifact và Liquibase version.
3. Chạy **validate** để kiểm tra cấu trúc changelog.
4. Chạy **status --verbose** để xem các changeset đang pending.
5. Chạy **update-sql** để review SQL dự kiến, đồng thời hiểu thiết lập onSqlOutput.
6. Thực hiện các truy vấn kiểm chứng invariant quan trọng bằng tài khoản phù hợp.
7. Thử migration trên database development hoặc bản sao chứa dữ liệu đại diện.
8. Đọc log khi precondition fail/error để phân biệt lỗi điều kiện và lỗi thực thi.
9. Chỉ sau khi kết quả khớp kế hoạch mới chạy **update** trên môi trường đích.
10. Xác minh schema, dữ liệu và DATABASECHANGELOG sau triển khai.

Lệnh CLI minh họa (giả sử JDBC connection được cấu hình qua nguồn an toàn):

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate
liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
~~~

Tên cờ và cách lấy kết nối phụ thuộc phiên bản Liquibase. Không ghi password thật vào lệnh nếu shell history hoặc CI log có thể lưu lại.

### 21.1. Thử nghiệm cả đường fail và error

Chỉ kiểm tra rằng precondition **pass** là chưa đủ. Nên có ba tình huống thử:

| Trạng thái test | Kỳ vọng |
|---|---|
| Đúng tiền đề | Migration được phép thực thi |
| Điều kiện sai nhưng truy vấn chạy được | onFail xử lý như dự kiến |
| Lỗi khi đánh giá (sai quyền, sai đối tượng trong sqlCheck trên DB test) | onError xử lý như dự kiến |

Đặc biệt kiểm tra việc MARK_RAN/CONTINUE có khiến các bước tiếp theo thất bại hoặc bỏ qua mà pipeline không phát hiện không.

## 22. Tích hợp Spring Boot và CI/CD

Spring Boot có thể chạy Liquibase khi ứng dụng khởi động hoặc hệ thống có thể dùng một bước migration riêng trong pipeline. Với cả hai cách, precondition vẫn được khai báo trong changelog.

Ví dụ cấu hình kết nối minh họa:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-staging.internal:5432/orders
    username: orders_migrator
    password: "<inject-from-secret-manager>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: public
~~~

**Lưu ý:** Đây là cấu hình ví dụ, không chứa secret thật. Trên production, nên đánh giá việc dùng DataSource riêng cho Liquibase nếu user ứng dụng không được phép có quyền DDL.

### Chính sách triển khai đề xuất

- Giữ cùng một artifact changelog qua development, test, staging và production.
- Không sửa changeset đã triển khai chỉ để làm precondition pass ở môi trường khác.
- Cấu hình endpoint và quyền riêng cho từng môi trường.
- Dùng precondition global cho các giả định chung và local cho các bước cụ thể.
- Ưu tiên HALT đối với lỗi có thể gây lệch schema/dữ liệu.
- Ghi nhận kết quả precondition fail/error trong log, cùng deployment ID nhưng không ghi secret.
- Thử rollback hoặc forward fix trên dữ liệu đại diện.
- Đánh giá khả năng chạy đồng thời, đặc biệt khi nhiều instance cùng khởi động.

Pipeline không nên coi trạng thái “Liquibase command exit code 0” là bằng chứng tất cả changeset đã thực sự chạy. Nếu có MARK_RAN, WARN hoặc CONTINUE, cần kiểm tra lịch sử và kết quả thực tế để hiểu điều gì đã xảy ra.

## 23. Lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| Cả changelog bị chặn vì một bảng chưa có | Đặt tableExists cục bộ ở cấp global | Chuyển điều kiện vào changeset cần nó nếu phù hợp |
| Lần đầu update chạy tốt, lần sau global guard fail | Global guard kiểm tra trạng thái tạm thời trước CREATE/ALTER | Chọn precondition local hoặc điều chỉnh thiết kế |
| Changeset MARK_RAN nhưng không có bảng mới | onFail=MARK_RAN đã đánh dấu mà không chạy SQL | Đối chiếu EXECTYPE, schema thực tế và lý do precondition fail |
| Changeset luôn pending | onFail=CONTINUE hoặc filter/ngữ cảnh chưa thỏa | Xem status, log và tiền đề hiện tại |
| sqlCheck báo error thay vì fail | SQL sai, cột thiếu, lỗi quyền hoặc kết nối | Chạy SQL kiểm tra có kiểm soát, xem onError |
| sqlCheck báo fail khi DBMS trả về kiểu khác | expectedResult không khớp biểu diễn scalar | Dùng giá trị đơn giản, xác minh kiểu và kết quả trả về |
| Global dbms guard fail trên một DBMS khác | Changelog chỉ thiết kế cho một DBMS | Tách luồng DBMS hoặc dùng change type portable |
| RunningAs đạt nhưng vẫn ở sai môi trường | User trùng tên ở nhiều database | Xác minh URL, database/schema, không dựa vào username |
| Precondition pass nhưng migration thất bại | Thiếu quyền DDL, race condition hoặc SQL không tương thích | Phân tích lỗi DBMS/transaction, kiểm tra trực tiếp schema |
| update-sql khác với update thật | onSqlOutput và trạng thái DB khác nhau | Kiểm tra cơ chế sinh SQL/precondition trên đúng phiên bản |
| changeSetExecuted không tìm thấy history | Sai author, id hoặc FILENAME/logicalFilePath | Đối chiếu chính xác DATABASECHANGELOG |
| Chạy lại migration ngoài dự kiến | runAlways/runOnChange hoặc định danh đường dẫn thay đổi | So sánh changeset ID, AUTHOR, FILENAME, checksum |
| Rollback làm mất dữ liệu | Chỉ có DROP TABLE/DROP COLUMN mà không kế hoạch dữ liệu | Thử trên bản sao và xây dựng kế hoạch khôi phục |

Khi điều tra, nên ghi lại: **database nào**, **changeset nào**, **precondition nào**, **kết quả fail/error**, **onFail/onError đặt giá trị gì**, và **trạng thái thực tế của schema/data**. Không xóa hàng trong DATABASECHANGELOG để “chạy lại cho nhanh”.

## 24. Bài thực hành: global guard và local guard

**Bối cảnh:** Dịch vụ đơn hàng dùng PostgreSQL. Cần tạo bảng **shipping_event** nếu chưa tồn tại và bổ sung index trên cột **order_id**.

Giả sử schema public đã có, user migration có quyền tương ứng và database thử nghiệm chưa có bảng shipping_event.

### 24.1. Changelog XML đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        http://www.liquibase.org/xml/ns/dbchangelog
        https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <preConditions onFail="HALT" onError="HALT">
        <dbms type="postgresql"/>
    </preConditions>

    <changeSet id="practice-001" author="training-team">
        <preConditions onFail="HALT" onError="HALT">
            <not>
                <tableExists tableName="shipping_event"
                             schemaName="public"/>
            </not>
        </preConditions>
        <createTable tableName="shipping_event" schemaName="public">
            <column name="id" type="bigint">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="order_id" type="bigint">
                <constraints nullable="false"/>
            </column>
            <column name="event_type" type="varchar(64)">
                <constraints nullable="false"/>
            </column>
        </createTable>
        <rollback>
            <dropTable tableName="shipping_event" schemaName="public"/>
        </rollback>
    </changeSet>

    <changeSet id="practice-002" author="training-team">
        <preConditions onFail="HALT" onError="HALT">
            <and>
                <tableExists tableName="shipping_event"
                             schemaName="public"/>
                <columnExists tableName="shipping_event"
                              columnName="order_id"
                              schemaName="public"/>
                <not>
                    <indexExists tableName="shipping_event"
                                 indexName="idx_shipping_event_order"
                                 schemaName="public"/>
                </not>
            </and>
        </preConditions>
        <createIndex tableName="shipping_event"
                     schemaName="public"
                     indexName="idx_shipping_event_order">
            <column name="order_id"/>
        </createIndex>
        <rollback>
            <dropIndex tableName="shipping_event"
                       schemaName="public"
                       indexName="idx_shipping_event_order"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

### 24.2. Thử nghiệm có kiểm soát

1. Chạy validate để kiểm tra changelog.
2. Chạy status --verbose và xác nhận cả hai changeset đang pending.
3. Chạy update-sql và kiểm tra SQL tạo bảng trước tạo index.
4. Chạy update trên database thử nghiệm.
5. Xác minh bảng shipping_event và index đã được tạo.
6. Xem DATABASECHANGELOG và đảm bảo hai changeset được ghi nhận đúng.
7. Chạy update lần nữa để xác nhận không chạy lại hai changeset theo mặc định.

### 24.3. Thử đường fail của local precondition

Trên một **database thử nghiệm khác**, tạo sẵn bảng shipping_event bằng phương thức phù hợp, nhưng để DATABASECHANGELOG chưa ghi changeset practice-001. Chạy lại với precondition HALT. Dự kiến precondition local của practice-001 fail vì bảng đã tồn tại.

Đây là tình huống có thể xảy ra khi tiếp nhận database đã có schema thủ công. Trước khi chọn MARK_RAN hay phương án baseline, phải xác minh cấu trúc hiện hữu có thực sự tương đương với kết quả migration.

### 24.4. Thử đường fail của global precondition

Chạy changelog trong một database thử nghiệm dùng DBMS khác được hỗ trợ. Global dbms guard phải chặn, do đó không đi vào các thay đổi thiết kế riêng cho PostgreSQL.

Không thực hiện các bài thử phá hoại trên production.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Điều kiện “kết nối phải là PostgreSQL” nên ở cấp nào?

Nếu toàn bộ changelog chỉ thiết kế cho PostgreSQL, đặt global là hợp lý. Nếu chỉ một changeset chứa SQL PostgreSQL còn các changeset khác portable, nên gắn điều kiện ở mức cục bộ hoặc dùng thuộc tính dbms của changeset tương ứng.

**Câu 2.** Điều kiện “bảng chưa tồn tại trước CREATE TABLE” nên ở đâu?

Thông thường ở local precondition của changeset CREATE TABLE. Đặt global dễ khiến lần update sau bị chặn vì bảng đã được tạo thành công.

**Câu 3.** Khác nhau giữa onFail và onError là gì?

onFail xử lý kết quả kiểm tra không đạt. onError xử lý lỗi trong quá trình đánh giá điều kiện, ví dụ truy vấn sai hoặc thiếu quyền.

**Câu 4.** Có dùng MARK_RAN trong precondition cấp changelog được không?

Không theo quy tắc thông dụng của Liquibase: ở cấp changelog chỉ dùng HALT hoặc WARN. MARK_RAN và CONTINUE là chính sách dành cho changeset cục bộ.

**Câu 5.** Vì sao không nên dùng MARK_RAN mặc định khi bảng đã tồn tại?

Vì chỉ có bảng cùng tên không chứng minh cấu trúc, constraint hay dữ liệu giống migration dự kiến. MARK_RAN có thể làm lịch sử ghi nhận trạng thái không tương đương.

**Câu 6.** sqlCheck mong đợi COUNT=0 nhưng trả về 7 là fail hay error?

Đó thường là **fail** vì truy vấn thực thi thành công nhưng kết quả khác expectedResult. Nếu truy vấn lỗi do cột không tồn tại thì là **error**.

**Câu 7.** local precondition có tự chạy lại trên mọi lần update sau khi changeset đã EXECUTED không?

Thông thường không, vì Liquibase không thực thi lại changeset đã ghi nhận trừ khi có cơ chế rerun phù hợp như runAlways/runOnChange. Đó là lý do điều kiện “chưa tồn tại” có thể đặt ở local.

**Câu 8.** Precondition có bảo đảm rollback an toàn không?

Không. Nó kiểm tra điều kiện cho migration, còn rollback cần thiết kế để không phá hủy dữ liệu hoặc quan hệ phụ thuộc ngoài dự kiến.

**Câu 9.** Tại sao vẫn cần xem update-sql và trạng thái DB nếu đã viết precondition?

Vì precondition chỉ kiểm tra những giả định được khai báo, không kiểm thử toàn bộ SQL, tải hệ thống hoặc khả năng tương thích ứng dụng; thêm nữa onSqlOutput có thể ảnh hưởng việc đánh giá trong chế độ sinh SQL.

**Câu 10.** Nếu một changeset đã đánh dấu MARK_RAN, changeSetExecuted có khẳng định SQL của nó từng chạy không?

Không. MARK_RAN có nghĩa Liquibase ghi nhận đã xử lý nhưng phần thay đổi có thể chưa được thực thi.

## 26. Checklist review trước khi triển khai

- [ ] Đã phân biệt rõ global guard và local guard.
- [ ] Không đặt điều kiện tạm thời của một changeset ở cấp changelog.
- [ ] Global guard chỉ dùng HALT/WARN theo quy tắc phạm vi.
- [ ] Local guard dùng CONTINUE/MARK_RAN chỉ khi có lý do và kế hoạch xử lý phụ thuộc.
- [ ] onFail và onError được chọn riêng, không nhầm failure với error.
- [ ] Các sqlCheck trả về scalar và có expectedResult rõ ràng.
- [ ] Điều kiện liên quan dữ liệu được thử với dữ liệu đại diện, gồm trường hợp lỗi.
- [ ] Điều kiện AND/OR/NOT có thứ tự và ý nghĩa dễ review.
- [ ] Không dùng precondition thay thế kiểm tra quyền hoặc chọn đúng JDBC endpoint.
- [ ] Không dựa hoàn toàn vào changeSetExecuted khi cần chứng minh schema/data thực tế.
- [ ] Đã cân nhắc chi phí snapshot/metadata và query dữ liệu trên database lớn.
- [ ] Đã đánh giá giao dịch, race condition và khả năng ghi đồng thời.
- [ ] Changelog được validate và status/update-sql được kiểm tra trên database phù hợp.
- [ ] Kết quả MARK_RAN, CONTINUE, WARN được kiểm tra sau triển khai.
- [ ] Đã thiết kế rollback hoặc forward fix cho migration rủi ro.
- [ ] Không sửa changeset cũ hoặc DATABASECHANGELOG tùy tiện để vượt qua precondition.
- [ ] Artifact changelog, phiên bản Liquibase và metadata môi trường được lưu để truy vết.

**Kết luận:** Precondition cấp changelog phù hợp để kiểm soát những giả định chung của một luồng migration; precondition cấp changeset phù hợp để bảo vệ thay đổi cụ thể tại thời điểm thực thi. Lựa chọn đúng phạm vi và chính sách onFail/onError giúp nhóm phát triển phát hiện trạng thái schema/dữ liệu không mong đợi thay vì tiếp tục mù quáng hoặc ghi nhận lịch sử sai. Kết hợp precondition với changelog ổn định, DATABASECHANGELOG, kiểm chứng SQL và quy trình CI/CD là nền tảng của migration Liquibase an toàn, giải thích được và có thể vận hành qua nhiều môi trường.

