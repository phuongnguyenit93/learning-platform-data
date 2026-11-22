# Viết changelog XML và khai báo namespace, schema

Trong Liquibase, **changelog XML** mô tả các thay đổi cần triển khai lên cơ sở dữ liệu dưới dạng các phần tử có cấu trúc. Mỗi changeset mang định danh và khai báo thao tác như tạo bảng, thêm cột, tạo index, cập nhật dữ liệu hoặc thực thi SQL. XML hỗ trợ kiểm tra cấu trúc dựa trên XSD, phù hợp với nhóm muốn quy tắc rõ ràng và công cụ IDE kiểm tra được phần tử, thuộc tính.

Đây là bài học thuộc chương **Định dạng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung cách viết XML đúng, hiểu namespace và schema, tổ chức changeset, kiểm tra trước khi chạy và tránh nhầm lẫn giữa **XML schema (XSD)** với **schema của database**.

## 1. XML changelog khác gì SQL migration?

Liquibase có thể mô tả thay đổi theo nhiều định dạng như XML, YAML, JSON hoặc formatted SQL. Dù dùng định dạng nào, công cụ vẫn quản lý danh tính changeset và lịch sử triển khai trong database.

XML có ba lợi thế chính:

- **Cấu trúc tường minh:** mỗi thao tác sử dụng một phần tử xác định như createTable, addColumn, addForeignKeyConstraint, createIndex hoặc insert.
- **Kiểm tra cú pháp theo XSD:** phát hiện sớm việc viết sai phần tử, thiếu thuộc tính cần thiết hoặc đặt thẻ sai cấu trúc.
- **Hỗ trợ tooling:** IDE thường gợi ý tên phần tử/thuộc tính và hỗ trợ định dạng, điều hướng, kiểm tra XML.

Đổi lại, XML thường dài hơn SQL/YAML và cần xử lý ký tự đặc biệt. Nó cũng không loại bỏ khác biệt giữa PostgreSQL, MySQL, Oracle hoặc các DBMS khác: một thay đổi hợp lệ theo XSD vẫn có thể không chạy được trên database đích do kiểu dữ liệu, quyền, constraint hoặc hành vi transaction.

## 2. Cấu trúc tối thiểu của changelog XML

Ví dụ sau là một changelog hoàn chỉnh, tạo bảng customer:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        http://www.liquibase.org/xml/ns/dbchangelog
        http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="001-create-customer" author="database-team">
        <createTable tableName="customer">
            <column name="id" type="BIGINT" autoIncrement="true">
                <constraints
                    primaryKey="true"
                    primaryKeyName="pk_customer"
                    nullable="false"/>
            </column>
            <column name="email" type="VARCHAR(255)">
                <constraints nullable="false"/>
            </column>
        </createTable>
    </changeSet>

</databaseChangeLog>
~~~

Các phần chính gồm:

1. **XML declaration:** dòng đầu khai báo XML 1.0 và encoding UTF-8.
2. **databaseChangeLog:** phần tử gốc chứa các changeset hoặc các chỉ thị include.
3. **xmlns:** đưa các phần tử không có tiền tố vào namespace Liquibase.
4. **xmlns:xsi:** khai báo tiền tố xsi của XML Schema instance.
5. **xsi:schemaLocation:** liên kết URI namespace với định nghĩa XSD.
6. **changeSet:** đơn vị thay đổi có id và author.
7. **createTable, column, constraints:** các change type/phần tử con thể hiện thao tác lên database.

Một XML document phải có phần tử gốc duy nhất, cặp thẻ mở/đóng phù hợp và mọi thuộc tính được đặt trong dấu nháy. XML phân biệt chữ hoa/chữ thường: changeSet không đồng nghĩa với changeset hay ChangeSet.

Không chạy một changelog chỉ vì IDE tô màu đúng; cần tiếp tục kiểm tra bằng Liquibase runtime và database mục tiêu.

## 3. Khai báo namespace mặc định

Dòng sau khai báo **default namespace**:

~~~xml
xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
~~~

URI namespace là định danh của bộ từ vựng XML Liquibase. Nhờ khai báo này, các phần tử như databaseChangeLog, changeSet và createTable (khi không có tiền tố) đều thuộc namespace Liquibase.

Ví dụ:

~~~xml
<databaseChangeLog xmlns="http://www.liquibase.org/xml/ns/dbchangelog">
    <changeSet id="002-example" author="team">
        <sql>CREATE TABLE example_table (id BIGINT PRIMARY KEY);</sql>
    </changeSet>
</databaseChangeLog>
~~~

Ở đây, default namespace được kế thừa xuống các phần tử con. Nếu bỏ xmlns hoặc khai báo sai URI, tệp có thể vẫn đúng ngữ pháp XML nhưng Liquibase hoặc XML Schema validator không nhận ra phần tử cần thiết.

Namespace URI **không phải JDBC URL** và không trỏ tới cơ sở dữ liệu. Nó cũng không chỉ định các bảng sẽ nằm trong PostgreSQL schema public, app hay tên schema nào khác.

## 4. Khai báo xmlns:xsi và xsi:schemaLocation

Phần khai báo chuẩn:

~~~xml
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"

xsi:schemaLocation="
    http://www.liquibase.org/xml/ns/dbchangelog
    http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd"
~~~

**xmlns:xsi** khai báo tiền tố xsi. Tiền tố này được dùng trong thuộc tính schemaLocation, vốn thuộc namespace XML Schema instance chứ không phải namespace Liquibase.

**xsi:schemaLocation** chứa một hoặc nhiều **cặp** giá trị:

~~~text
<namespace URI> <đường dẫn XSD>
~~~

Trong trường hợp này, giá trị thứ nhất là URI namespace Liquibase; giá trị thứ hai là địa chỉ tệp XSD mô tả cấu trúc của namespace đó. Dấu cách hoặc xuống dòng phân tách các giá trị. Nếu có thêm namespace của extension, cần ánh xạ thêm cặp namespace/XSD phù hợp với extension ấy.

Lỗi thường gặp:

- Có xsi:schemaLocation nhưng thiếu xmlns:xsi: XML parser báo tiền tố xsi chưa được khai báo.
- Viết nhầm namespace URI: XSD không khớp với các phần tử XML.
- Đặt một đường dẫn changelog vào vị trí XSD: bộ kiểm tra không tìm được schema định nghĩa cấu trúc.
- Khai báo XSD của phiên bản không phù hợp: một phần tử/thuộc tính mới có thể bị validator từ chối.
- Dùng URI namespace đúng nhưng đặt phần tử ở sai cấp: XSD vẫn báo lỗi.

### latest.xsd hay XSD theo phiên bản?

dbchangelog-latest.xsd là cách khai báo quen thuộc trong tài liệu mẫu và hữu ích khi học. Đối với repository cần kiểm soát phiên bản, nhóm có thể lựa chọn XSD có phiên bản cụ thể tương ứng với bản Liquibase runtime và các tính năng được dùng. Cần đối chiếu chính xác danh sách XSD đã phát hành; không tự suy ra tên phiên bản XSD tùy ý.

Một XSD mới không khiến Liquibase runtime cũ tự hỗ trợ tính năng mới, và một XSD cũ có thể không biết các thuộc tính được phiên bản mới bổ sung. Vì vậy hãy quản lý cùng nhau phiên bản **Liquibase CLI/library, XSD, JDBC driver, DBMS và extension**. Khi chạy offline, cách IDE/runtime phân giải XSD cũng cần được kiểm tra; một công cụ có thể dùng tài nguyên đi kèm, công cụ khác có thể cần tải schema từ ngoài.

## 5. Phân biệt XML schema với database schema

Tên **schema** xuất hiện ở hai lớp độc lập:

| Khái niệm | Ví dụ | Tác dụng |
|---|---|---|
| XML namespace | http://www.liquibase.org/xml/ns/dbchangelog | Xác định loại phần tử trong tệp XML |
| XML Schema Definition (XSD) | dbchangelog-latest.xsd | Kiểm tra cấu trúc tệp XML |
| Database schema | public hoặc app trong PostgreSQL | Không gian tên chứa bảng, view, index và đối tượng database |
| Liquibase schema | Schema chứa DATABASECHANGELOG và DATABASECHANGELOGLOCK, nếu cấu hình riêng | Lưu metadata lịch sử và khóa triển khai |

Ví dụ, để tạo bảng app_setting trong **database schema app**, dùng schemaName trên change type:

~~~xml
<changeSet id="003-create-app-setting" author="team">
    <createTable schemaName="app" tableName="app_setting">
        <column name="setting_key" type="VARCHAR(100)">
            <constraints primaryKey="true" nullable="false"/>
        </column>
    </createTable>
</changeSet>
~~~

Schema app phải đã tồn tại và user triển khai phải có quyền tương ứng. Nó có thể được tạo ở một changeset trước hoặc bằng bước bootstrap có kiểm soát.

Thay đổi giá trị xsi:schemaLocation **không** chuyển bảng sang schema app. Tương tự, cấu hình JDBC URL, default schema và Liquibase schema là trách nhiệm của cấu hình kết nối/ứng dụng, không phải của XSD.

## 6. Changeset: ID, author, đường dẫn và lịch sử

Mỗi changeset có ít nhất hai thuộc tính quan trọng là id và author:

~~~xml
<changeSet id="20261119-001-create-account" author="team">
    <createTable tableName="account">
        <column name="id" type="BIGINT">
            <constraints primaryKey="true" nullable="false"/>
        </column>
    </createTable>
</changeSet>
~~~

Liquibase thường định danh changeset bằng tổ hợp **id, author và đường dẫn changelog** (hoặc logicalFilePath nếu được cấu hình). Bảng DATABASECHANGELOG ghi nhận lịch sử đã chạy, thời gian và checksum. Vì vậy:

- ID và author nên theo quy ước thống nhất, có ý nghĩa và giữ ổn định.
- Sau khi đã triển khai, không tùy tiện đổi tên/di chuyển changelog vì có thể thay đổi danh tính changeset.
- Không sửa logic của changeset đã chạy ở các môi trường dùng chung; thường nên tạo changeset mới để điều chỉnh trạng thái.
- Nếu có checksum mismatch, cần điều tra nội dung nào đã thay đổi; không tự làm mới checksum để che giấu sai lệch.
- Nếu bắt buộc di chuyển tệp cũ, nghiên cứu logicalFilePath và kiểm thử trên database đã có lịch sử trước khi thực hiện.

Một tệp có thể có nhiều changeset, nhưng nên giữ mỗi changeset nhỏ, có mục đích rõ và có thể xác minh riêng. Đừng gộp các thao tác không liên quan chỉ vì XML cho phép.

## 7. Ví dụ hoàn chỉnh với precondition và rollback

Ví dụ sau tạo bảng customer_account, sau đó tạo index trên email. Các precondition kiểm tra trạng thái trước khi chạy và rollback được khai báo tường minh.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        http://www.liquibase.org/xml/ns/dbchangelog
        http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="001-create-customer-account" author="team">
        <comment>Tạo bảng tài khoản khách hàng</comment>

        <preConditions onFail="HALT" onError="HALT">
            <not>
                <tableExists tableName="customer_account"/>
            </not>
        </preConditions>

        <createTable tableName="customer_account">
            <column name="id" type="BIGINT" autoIncrement="true">
                <constraints
                    primaryKey="true"
                    primaryKeyName="pk_customer_account"
                    nullable="false"/>
            </column>
            <column name="email" type="VARCHAR(255)">
                <constraints nullable="false"/>
            </column>
            <column
                name="created_at"
                type="TIMESTAMP"
                defaultValueComputed="CURRENT_TIMESTAMP">
                <constraints nullable="false"/>
            </column>
        </createTable>

        <rollback>
            <dropTable tableName="customer_account"/>
        </rollback>
    </changeSet>

    <changeSet id="002-index-customer-email" author="team">
        <preConditions onFail="HALT" onError="HALT">
            <tableExists tableName="customer_account"/>
            <not>
                <indexExists
                    tableName="customer_account"
                    indexName="idx_customer_account_email"/>
            </not>
        </preConditions>

        <createIndex
            indexName="idx_customer_account_email"
            tableName="customer_account">
            <column name="email"/>
        </createIndex>

        <rollback>
            <dropIndex
                tableName="customer_account"
                indexName="idx_customer_account_email"/>
        </rollback>
    </changeSet>

</databaseChangeLog>
~~~

Đọc ví dụ theo thứ tự:

1. Liquibase đọc changeset 001, xác định nó chưa chạy và kiểm tra bảng customer_account chưa tồn tại.
2. Nếu điều kiện đúng, createTable chạy; lịch sử được ghi nhận. Nếu bảng đã tồn tại ngoài lịch sử Liquibase, HALT dừng migration để kiểm tra sai lệch.
3. Changeset 002 chỉ chạy khi bảng tồn tại và index chưa tồn tại.
4. Khi rollback được yêu cầu, Liquibase sử dụng nội dung rollback đã khai báo theo thứ tự rollback áp dụng cho lịch sử thực thi.

**Cảnh báo về rollback:** dropIndex thường chỉ xóa index, nhưng dropTable xóa bảng và dữ liệu. Không coi rollback trong XML là bằng chứng có thể phục hồi toàn bộ thông tin. Với production, cần backup/restore hoặc forward-fix được diễn tập.

Precondition giúp phát hiện trạng thái không phù hợp; nó không thay thế thứ tự changeset đúng, kế hoạch migration dữ liệu hay kiểm tra sau triển khai. Hành vi MARK_RAN có thể đánh dấu changeset đã chạy mà không áp dụng thay đổi, nên không dùng để che giấu lỗi cấu trúc.

## 8. Xử lý ký tự đặc biệt khi nhúng SQL vào XML

XML dùng một số ký tự để tạo cấu trúc. Đặt trực tiếp dấu nhỏ hơn hoặc ký tự ampersand trong nội dung XML có thể làm parser báo lỗi.

Bảng quy đổi ký tự nguồn:

~~~text
Ký tự gốc    Cách viết trong XML
&            &amp;
<            &lt;
>            &gt;
"            &quot;   (khi cần escape trong thuộc tính)
'            &apos;   (khi cần escape trong thuộc tính)
~~~

Ví dụ SQL gốc:

~~~sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE total_amount < 100
  AND status = 'PENDING';
~~~

Trong phần tử sql, dấu nhỏ hơn cần được escape:

~~~xml
<changeSet id="004-archive-small-orders" author="team">
    <sql>
        UPDATE orders
        SET status = 'ARCHIVED'
        WHERE total_amount &lt; 100
          AND status = 'PENDING';
    </sql>
</changeSet>
~~~

Dấu & trong XML cần viết thành &amp; khi nó thuộc dữ liệu văn bản. Nếu SQL chứa nhiều ký tự đặc biệt hoặc nhiều dòng, có thể dùng CDATA:

~~~xml
<changeSet id="005-normalize-email" author="team">
    <sql><![CDATA[
        UPDATE customer_account
        SET email = LOWER(email)
        WHERE email IS NOT NULL
          AND email <> LOWER(email);
    ]]></sql>
</changeSet>
~~~

CDATA giúp XML parser coi nội dung bên trong là văn bản thay vì markup. Tuy nhiên, không thể đặt nguyên chuỗi kết thúc CDATA vào chính vùng CDATA mà không xử lý tách chuỗi. CDATA cũng không làm SQL an toàn hay độc lập DBMS; vẫn phải review câu lệnh, dữ liệu bị ảnh hưởng và khả năng rollback.

XML còn có quy tắc riêng cho comment: không được chứa hai dấu gạch ngang liên tiếp bên trong một XML comment. Nếu cần ghi lý do thay đổi, nên dùng phần tử comment trong changeset để dễ đọc và tránh vi phạm cú pháp XML.

## 9. Change type có cấu trúc hay SQL trực tiếp?

Với XML, có thể kết hợp change type và SQL trực tiếp.

Change type:

~~~xml
<addColumn tableName="customer_account">
    <column name="phone_number" type="VARCHAR(30)"/>
</addColumn>
~~~

SQL trực tiếp:

~~~xml
<sql><![CDATA[
    CREATE INDEX idx_customer_created_at
    ON customer_account (created_at);
]]></sql>
~~~

| Tiêu chí | Change type có cấu trúc | SQL nhúng |
|---|---|---|
| Ý định thay đổi | Rõ thông qua tên phần tử | Phụ thuộc câu SQL và comment |
| Khả năng tương thích DBMS | Liquibase hỗ trợ biên dịch ở mức có thể | Thường đặc thù SQL dialect |
| Tính năng nâng cao của database | Có thể thiếu một số tùy chọn native | Kiểm soát câu lệnh trực tiếp |
| Rollback | Một số loại được hỗ trợ tự sinh | Thường cần rollback tường minh |
| Xác minh | Xem SQL thực tế được Liquibase tạo | Kiểm tra SQL do tác giả viết |

Không phải change type nào cũng hỗ trợ rollback tự động, và không phải SQL nào cũng chạy trong transaction. Khả năng transactional DDL phụ thuộc DBMS, phiên bản và cấu hình. Với migration có cập nhật nhiều dữ liệu, cần tính đến thời gian, khóa bảng, replication lag và phương án backfill theo lô.

## 10. Context, label và DBMS trong XML

Có thể dùng thuộc tính của changeset để giới hạn phạm vi triển khai hoặc mô tả chính sách chạy lại, chẳng hạn dbms, contextFilter, labels, runAlways và runOnChange khi được XSD/runtime hỗ trợ.

Ví dụ chỉ dành cho PostgreSQL:

~~~xml
<changeSet id="006-postgres-index" author="team" dbms="postgresql">
    <preConditions onFail="HALT">
        <tableExists tableName="customer_account"/>
    </preConditions>

    <sql><![CDATA[
        CREATE INDEX idx_customer_email_lower
        ON customer_account (LOWER(email));
    ]]></sql>

    <rollback>
        <sql>DROP INDEX idx_customer_email_lower;</sql>
    </rollback>
</changeSet>
~~~

dbms giúp lọc changeset theo database engine; precondition kiểm tra điều kiện trước khi áp dụng. Context và label hỗ trợ chọn changeset theo môi trường, mục đích, hoặc giai đoạn. Chúng **không** là cơ chế phân quyền, và cũng không tự bảo đảm các changeset có quan hệ phụ thuộc đều được chọn. Ví dụ nếu một changeset tạo bảng chỉ chạy ở dev mà changeset tạo khóa ngoại lại chạy ở production, migration production có thể lỗi.

Các thuộc tính runAlways hoặc runOnChange cần được sử dụng khi có lý do rõ ràng và hiểu chính xác cơ chế checksum. Không bật chúng đơn thuần để tránh một lỗi checksum mismatch do chỉnh sửa lịch sử.

## 11. Tổ chức nhiều changelog XML bằng include và includeAll

Khi số lượng changeset tăng, nên chia thành các tệp nhỏ:

~~~text
src/main/resources/db/changelog/
├── db.changelog-master.xml
└── changes/
    ├── 0001-create-customer.xml
    ├── 0002-create-orders.xml
    └── 0003-add-foreign-key.xml
~~~

Trong changelog master, dùng include để khai báo rõ thứ tự:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        http://www.liquibase.org/xml/ns/dbchangelog
        http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <include file="changes/0001-create-customer.xml"
             relativeToChangelogFile="true"/>
    <include file="changes/0002-create-orders.xml"
             relativeToChangelogFile="true"/>
    <include file="changes/0003-add-foreign-key.xml"
             relativeToChangelogFile="true"/>

</databaseChangeLog>
~~~

Hoặc dùng includeAll khi muốn nạp các tệp từ một thư mục:

~~~xml
<includeAll path="changes/" relativeToChangelogFile="true"/>
~~~

includeAll thường xử lý các tài nguyên theo thứ tự chữ cái/đường dẫn; nhóm nên dùng tiền tố số cùng độ rộng như 0001, 0002, 0003. Nhưng Liquibase không tự suy luận đồ thị phụ thuộc giữa bảng, khóa ngoại và dữ liệu. Nếu thứ tự phải được kiểm soát nghiêm ngặt, include tường minh có thể dễ review hơn.

Mỗi changelog XML con cần khai báo namespace/XSD hợp lệ như changelog gốc nếu nó là một tài liệu XML độc lập. Hãy bảo đảm các tệp con thực sự được đóng gói vào JAR/image. Đổi tên hoặc di chuyển một changelog đã triển khai cần quy trình đặc biệt vì đường dẫn ảnh hưởng định danh changeset.

## 12. Namespace có tiền tố và extension

Ngoài default namespace, XML cho phép đặt tiền tố:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<lb:databaseChangeLog
    xmlns:lb="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        http://www.liquibase.org/xml/ns/dbchangelog
        http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <lb:changeSet id="007-prefixed-xml" author="team">
        <lb:sql>CREATE TABLE prefix_demo (id BIGINT PRIMARY KEY);</lb:sql>
    </lb:changeSet>

</lb:databaseChangeLog>
~~~

Tiền tố lb có thể đổi thành tên khác, miễn là được khai báo đúng URI. Nếu không có default namespace thì phần tử thuộc namespace Liquibase phải dùng đúng tiền tố.

Một số extension có thể cung cấp namespace và XSD riêng. Chỉ khai báo các namespace bổ sung theo tài liệu của extension tương thích với phiên bản Liquibase đang dùng. Khai báo namespace không tự cài extension hoặc cấp quyền sử dụng tính năng; runtime vẫn cần thư viện và entitlement tương ứng. Đối với changelog core, default namespace đơn giản thường là lựa chọn dễ đọc nhất.

## 13. Các tầng kiểm chứng XML và migration

| Tầng | Bắt được lỗi gì? | Giới hạn |
|---|---|---|
| XML parser | Thẻ không cân bằng, dấu nháy sai, entity không hợp lệ | Không biết thay đổi database có đúng không |
| XSD validation | Phần tử/thuộc tính sai hoặc đặt sai vị trí theo schema | Không biết SQL sẽ chạy được trên database |
| Liquibase validate | Các lỗi changelog mà phiên bản Liquibase có thể phát hiện | Không thay thế chạy thử với dữ liệu thật |
| Preview SQL | SQL dự kiến sẽ thực thi | Không đo chính xác tải/khóa/hiệu năng production |
| Database test | Khả năng áp dụng trên trạng thái database đại diện | Không bảo đảm mọi môi trường có cùng dữ liệu và quyền |
| Kiểm tra sau chạy | Schema, dữ liệu và lịch sử thay đổi như mong đợi | Vẫn cần giám sát vận hành |

Ví dụ phần tử createTables (thừa chữ s) có thể là XML well-formed nhưng không phải change type hợp lệ theo XSD. Ngược lại, createTable hợp lệ theo XSD vẫn có thể lỗi vì bảng đã tồn tại, thiếu quyền tạo bảng hoặc sử dụng kiểu dữ liệu không phù hợp.

Với CLI đã cấu hình URL, user, driver và changelog, có thể dùng:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.xml validate
liquibase --changelog-file=db/changelog/db.changelog-master.xml status --verbose
liquibase --changelog-file=db/changelog/db.changelog-master.xml update-sql
~~~

Tên tùy chọn và lệnh có thể khác tùy phiên bản; cần đối chiếu Liquibase đang dùng. Validate kiểm tra changelog, status cho biết changeset chờ chạy, còn update-sql giúp review SQL trước khi update.

Sau khi thử trên PostgreSQL, có thể xem lịch sử:

~~~sql
SELECT id, author, filename, dateexecuted, orderexecuted, exectype
FROM databasechangelog
ORDER BY orderexecuted;
~~~

DATABASECHANGELOG ghi nhận lịch sử và checksum. Không chỉnh sửa trực tiếp bảng lịch sử hoặc xóa checksum để che giấu lỗi XML. Nếu có sai lệch, xác định nguyên nhân từ tệp changelog, cấu hình database và nội dung đã triển khai.

## 14. Kết nối changelog XML với Spring Boot và CI/CD

Với Spring Boot, thường đặt tệp XML trong thư mục resources và khai báo:

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.xml
~~~

Ứng dụng cần dependency Liquibase, JDBC driver tương ứng và datasource hoặc cấu hình Liquibase riêng. Khi đóng gói, phải kiểm tra tất cả changelog con có trong artifact. Một cấu hình chạy được từ IDE nhưng thiếu tệp trong JAR vẫn có thể thất bại khi triển khai.

Pipeline CI/CD nên kiểm tra:

1. Changelog XML parse được và namespace/XSD phù hợp với runtime.
2. Liquibase validate thành công trên cấu hình sẽ triển khai.
3. Danh sách changeset và SQL dự kiến được review.
4. Migration áp dụng thành công từ database trống.
5. Nâng cấp từ database đã chạy phiên bản trước thành công.
6. Schema, constraint, dữ liệu và ứng dụng vẫn tương thích.
7. Rollback, backup/restore hoặc forward-fix đã được thử khi cần.
8. Kết quả triển khai được xác minh qua lịch sử và log.

Với nhiều replica Spring Boot, cần xác định tiến trình nào chạy migration và thứ tự ứng dụng nhận traffic. Liquibase có bảng khóa triển khai nhưng không thay thế thiết kế phát hành có điều phối.

## 15. Lỗi thường gặp khi viết XML changelog

| Hiện tượng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| XML báo tiền tố xsi chưa khai báo | Thiếu xmlns:xsi | Thêm namespace XML Schema instance đúng |
| Không nhận databaseChangeLog | Thiếu/sai default namespace hoặc tiền tố | Đối chiếu URI dbchangelog |
| Phần tử không được cho phép | Sai tên/thứ tự phần tử hoặc XSD không phù hợp | Sửa cú pháp, đồng bộ XSD và Liquibase runtime |
| SQL có dấu nhỏ hơn gây lỗi parse | Chưa escape hoặc dùng CDATA | Dùng &lt; hay vùng CDATA phù hợp |
| Không tìm được XSD | Đường dẫn sai hoặc môi trường offline chưa có tài nguyên | Kiểm tra URI, bản phân phối và cơ chế phân giải |
| Không thấy changelog con | Sai include path, relativeToChangelogFile hoặc thiếu file trong artifact | Kiểm tra đường dẫn/classpath và bản đóng gói |
| Đổi tên file làm changeset chạy lại | Đường dẫn là một phần định danh | Kiểm tra DATABASECHANGELOG, logicalFilePath và lịch sử triển khai |
| Checksum mismatch | Nội dung changeset đã chạy bị sửa | Điều tra thay đổi, thường viết changeset sửa chữa mới |
| XML validate thành công nhưng update lỗi | DBMS, quyền, kiểu dữ liệu hoặc trạng thái bảng không phù hợp | Kiểm thử trên database và dữ liệu đại diện |
| Rollback làm mất dữ liệu | Drop table/column hoặc dữ liệu bị biến đổi một chiều | Có backup và kế hoạch phục hồi được thử nghiệm |

Cách xử lý có hệ thống là kiểm tra lần lượt **XML well-formed → namespace/XSD → Liquibase validate → SQL dự kiến → trạng thái database thực tế**. Điều đó phân biệt được lỗi cú pháp tài liệu, lỗi metadata Liquibase và lỗi thực thi trên database.

## 16. Bài thực hành và checklist hoàn thành

Trên database lab của module, thực hiện các bước sau:

1. Tạo một changelog XML với khai báo UTF-8, default namespace, xmlns:xsi và xsi:schemaLocation.
2. Viết changeset tạo bảng với id/author rõ ràng; kiểm tra bằng validate trước khi chạy.
3. Viết precondition để dừng khi bảng đã tồn tại; thử điều kiện đạt và không đạt trên database lab có thể xóa.
4. Thêm changeset tạo index và rollback gỡ index; giải thích vì sao rollback dropTable nguy hiểm với dữ liệu.
5. Nhúng một lệnh SQL chứa toán tử nhỏ hơn, dùng escaping hoặc CDATA.
6. Chia master changelog và changelog con, kiểm tra thứ tự include.
7. Cấu hình Spring Boot hoặc Liquibase CLI trỏ đúng master XML.
8. Thực thi trên database trống, đối chiếu bảng/index và xem DATABASECHANGELOG.
9. Thử một lỗi namespace hoặc XML element trên bản sao riêng và xác định tầng kiểm tra phát hiện lỗi.
10. Thử nâng cấp database đã chạy migration cũ, xác nhận changeset đã ghi nhận không chạy lại bất ngờ.

| Câu hỏi trước khi merge | Bằng chứng cần có |
|---|---|
| XML có declaration, root và UTF-8 đúng không? | XML parser đọc thành công |
| xmlns, xmlns:xsi và schemaLocation có đúng không? | XSD validation phù hợp phiên bản |
| ID, author và đường dẫn changelog ổn định không? | Không sửa lịch sử đã triển khai |
| SQL có escape/CDATA hợp lệ không? | XML parser và preview SQL đạt |
| Database schema và quyền có đúng môi trường không? | Kiểm tra URL, user và default schema |
| Precondition và rollback có được thử chưa? | Kết quả thử đạt/không đạt và phục hồi |
| Fresh install và upgrade đều chạy được không? | Hai kịch bản kiểm thử thành công |
| Tệp XML con có được đóng gói không? | Kiểm tra JAR hoặc image thực tế |
| Có thể theo dõi sau triển khai không? | Lịch sử DATABASECHANGELOG và log được xác minh |

Một changelog XML tốt cho phép người khác hiểu **thay đổi nào sẽ chạy, điều kiện thực thi, nơi tạo đối tượng và cách xử lý khi lỗi xảy ra**. Namespace/XSD giúp bảo đảm tài liệu có cấu trúc đúng; còn an toàn migration phụ thuộc vào precondition, thiết kế changeset, kiểm tra SQL, rollback và kỷ luật triển khai qua các môi trường. Sử dụng đúng các lớp này giúp XML trở thành định dạng tin cậy để quản lý thay đổi database với Liquibase.

