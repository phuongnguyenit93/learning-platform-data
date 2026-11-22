
# Lọc changeset theo hệ quản trị bằng dbms trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Dự án có thể chạy trên PostgreSQL, MySQL, MariaDB, Oracle, SQL Server hoặc nhiều hệ quản trị khác nhau. Một phần migration có thể dùng change type tương đối độc lập nền tảng, nhưng nhiều thao tác lại cần cú pháp SQL hoặc khả năng riêng của một DBMS. Thuộc tính **dbms** của changeset giúp chỉ định hệ quản trị nào được phép chạy thay đổi đó.

Bài thuộc chương **Bộ lọc thực thi** này tập trung vào việc lựa chọn changeset bằng dbms, kết hợp với các bộ lọc khác, đọc đúng trạng thái DATABASECHANGELOG và kiểm chứng migration trên từng loại cơ sở dữ liệu. Mục tiêu là viết được changelog có thể triển khai có kiểm soát trên nhiều DBMS mà không vô tình thực thi SQL sai hệ quản trị, bỏ qua phần schema bắt buộc hoặc tạo ra sự khác biệt khó phát hiện giữa các môi trường.

## 1. Bài toán: cùng ứng dụng nhưng SQL khác nhau theo DBMS

Xét một ứng dụng quản lý khách hàng. Bảng customer và cột email có thể được tạo qua change type chuẩn của Liquibase. Tuy nhiên, một thao tác tạo index với tùy chọn chuyên biệt có thể không dùng chung một câu SQL cho PostgreSQL và MySQL.

Ví dụ, PostgreSQL hỗ trợ cú pháp:

~~~sql
CREATE INDEX IF NOT EXISTS idx_customer_email
ON customer (email);
~~~

Một cách viết thường dùng trên MySQL là:

~~~sql
CREATE INDEX idx_customer_email
ON customer (email);
~~~

Cú pháp, điều kiện kiểm tra index tồn tại, hành vi lock và rollback không hoàn toàn giống nhau. Nếu gửi một câu lệnh chỉ được PostgreSQL hiểu tới MySQL, migration có thể thất bại khi chạy thật. Nếu thay vào đó bỏ hẳn migration ở MySQL mà ứng dụng vẫn cần index tương đương, hệ thống có thể bị lệch về hiệu năng hoặc tính năng.

Liquibase giải quyết bằng hai hướng:

1. **Ưu tiên change type chung** như createTable, addColumn, createIndex khi công cụ có thể chuyển đổi sang SQL thích hợp cho DBMS đích.
2. **Dùng dbms để tách changeset** khi thật sự cần SQL, tính năng hoặc cách triển khai riêng của mỗi hệ quản trị.

Điều quan trọng là dbms chỉ giúp **chọn changeset phù hợp**. Nó không tự chuyển đổi một câu lệnh PostgreSQL thành câu lệnh MySQL và không chứng minh hai nhánh thay đổi tạo ra schema tương đương.

## 2. dbms của changeset hoạt động như thế nào?

Thuộc tính **dbms** là một điều kiện lựa chọn changeset dựa trên loại database mà Liquibase xác định qua kết nối đang sử dụng.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-01-pg-only
      author: schema-team
      dbms: postgresql
      comment: Chạy thao tác chuyên biệt dành cho PostgreSQL
      changes:
        - sql:
            sql: SELECT 1
~~~

Ở ví dụ minh họa, changeset được xét để chạy khi kết nối hiện tại được Liquibase nhận diện là PostgreSQL. Nếu đang kết nối MySQL, changeset không được thực thi do không khớp bộ lọc dbms.

Có thể diễn giải logic:

~~~text
Đọc changeset
      |
      v
Xác định DBMS từ kết nối database hiện tại
      |
      v
Giá trị dbms có cho phép DBMS này?
      |                   |
     Có                 Không
      |                   |
      v                   v
Xét tiếp các điều     Bỏ qua changeset
kiện và lịch sử       ở lần chạy này
      |
      v
Nếu đủ điều kiện và đang pending:
thực thi thay đổi, ghi lịch sử
~~~

Sơ đồ là mô hình khái niệm để học, không mô tả chính xác thứ tự gọi từng thành phần bên trong Liquibase. Một changeset còn chịu ảnh hưởng của context, label, precondition, trạng thái đã chạy, checksum, runOnChange hoặc runAlways.

**Điểm mấu chốt:** thuộc tính dbms nằm trong changelog; hệ quản trị được Liquibase xác định từ **database thật mà tiến trình đang kết nối**. Tên profile của ứng dụng hoặc tên môi trường như dev, staging, prod không trực tiếp quyết định loại DBMS.

## 3. Các giá trị dbms thường dùng

Các tên DBMS phải khớp với tên mà phiên bản Liquibase và database extension của dự án hỗ trợ. Một số giá trị thường gặp:

| DBMS | Giá trị minh họa | Ghi chú |
|---|---|---|
| PostgreSQL | postgresql | Hữu ích cho SQL liên quan JSONB, partial index, tính năng PostgreSQL |
| MySQL | mysql | Phân biệt với MariaDB trong trường hợp Liquibase nhận diện riêng |
| MariaDB | mariadb | Kiểm tra khả năng và cú pháp cụ thể của phiên bản MariaDB |
| Oracle Database | oracle | Chú ý kiểu dữ liệu, sequence, DDL và đặc thù transaction |
| Microsoft SQL Server | mssql | Cú pháp T-SQL, chỉ mục và kiểu dữ liệu có điểm riêng |
| H2 | h2 | Thường xuất hiện trong kiểm thử, không đại diện cho mọi DBMS production |
| SQLite | sqlite | Nhiều thao tác ALTER TABLE và ràng buộc có giới hạn riêng |
| DB2 | db2 | Cần đối chiếu loại DB2 và khả năng được phiên bản Liquibase hỗ trợ |

Bảng không phải danh sách đầy đủ. Đối với một database mới, database tương thích JDBC nhưng không phổ biến, hoặc extension bổ sung, phải xác nhận giá trị nhận diện được hỗ trợ ở phiên bản Liquibase đang dùng.

Không suy luận rằng MySQL, MariaDB và một hệ quản trị tương thích MySQL đều có cùng giá trị dbms. Hãy kiểm tra trên **đúng sản phẩm và phiên bản** mà môi trường sẽ chạy.

## 4. Cú pháp dbms trong YAML

### Chỉ một DBMS

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-02-pg-index
      author: schema-team
      dbms: postgresql
      comment: Dùng cú pháp index phù hợp PostgreSQL
      changes:
        - sql:
            sql: >-
              CREATE INDEX IF NOT EXISTS idx_customer_email
              ON customer (email)
      rollback:
        - sql:
            sql: DROP INDEX IF EXISTS idx_customer_email
~~~

Thuộc tính dbms ở cùng cấp với id, author, changes. Nó áp dụng cho **toàn bộ changeset**. Nếu chỉ một bước trong changeset là SQL chuyên biệt, nên cân nhắc tách bước đó thành changeset riêng thay vì buộc cả một nhóm thao tác chung chỉ chạy trên một DBMS.

### Nhiều DBMS trong một biểu thức

Nếu cùng một thao tác thích hợp cho PostgreSQL và MySQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-03-pg-or-mysql
      author: schema-team
      dbms: "postgresql,mysql"
      comment: Thao tác chỉ áp dụng cho PostgreSQL hoặc MySQL
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: external_code
                  type: varchar(64)
~~~

Danh sách cách nhau bằng dấu phẩy có nghĩa là changeset có thể được chọn khi DBMS khớp một trong các giá trị được liệt kê. Trong YAML, đặt chuỗi trong dấu nháy để bảo đảm cách diễn giải thống nhất.

**Lưu ý về thiết kế:** ví dụ chỉ minh họa cú pháp lọc. Nếu external_code là cột cốt lõi mà ứng dụng ở mọi DBMS đều cần, việc giới hạn thay đổi vào hai DBMS mà không có phương án cho các DBMS khác sẽ tạo ra schema không đồng nhất.

### Phủ định

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-04-except-oracle
      author: schema-team
      dbms: "!oracle"
      comment: Chạy trên các DBMS được hỗ trợ, trừ Oracle
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: source_system
                  type: varchar(40)
~~~

Tiền tố dấu chấm than thể hiện phủ định. Trong YAML, đặt giá trị như **"!oracle"** trong dấu nháy; dấu chấm than không được trích dẫn có thể bị YAML diễn giải như chỉ thị tag.

**Phủ định không phải danh sách cho phép an toàn:** khi viết !oracle, changeset có thể được chọn cả trên một DBMS mới mà nhóm chưa từng kiểm thử. Với SQL đặc thù sản phẩm, ưu tiên **danh sách cho phép tường minh** như postgresql,mysql khi nhóm có một tập DBMS được hỗ trợ rõ ràng.

### all và none

Hai giá trị đặc biệt thường gặp là:

- **all**: cho phép mọi loại DBMS mà Liquibase đang làm việc; trường hợp thông thường cũng có thể bỏ hẳn dbms.
- **none**: không chọn changeset để thực thi trên DBMS nào.

Không lạm dụng none để giấu migration chưa sẵn sàng trong changelog production. Một changeset bị vô hiệu hóa có thể gây hiểu nhầm về trạng thái phát hành. Nếu chưa sẵn sàng, nên giữ thay đổi ngoài nhánh phát hành hoặc quản lý kế hoạch đưa nó vào master changelog một cách rõ ràng.

## 5. Cú pháp dbms trong XML và formatted SQL

Nguyên tắc lựa chọn DBMS không phụ thuộc việc dự án dùng YAML, XML hay formatted SQL, nhưng vị trí thuộc tính sẽ khác nhau.

### XML changelog

~~~xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="20261119-05-pg" author="schema-team" dbms="postgresql">
        <comment>Tạo index bằng cú pháp phù hợp PostgreSQL.</comment>
        <sql>
            CREATE INDEX IF NOT EXISTS idx_customer_email
            ON customer (email);
        </sql>
        <rollback>
            <sql>DROP INDEX IF EXISTS idx_customer_email;</sql>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

Trong XML, dbms là attribute của phần tử changeSet. Cấu trúc phải được validate với phiên bản Liquibase và XSD đang dùng; ví dụ trên không thay thế việc kiểm tra tính tương thích DBMS thực tế.

### Formatted SQL

~~~sql
--liquibase formatted sql

--changeset schema-team:20261119-06-pg dbms:postgresql
--comment: Tạo index email khi triển khai trên PostgreSQL.
CREATE INDEX IF NOT EXISTS idx_customer_email
ON customer (email);

--rollback DROP INDEX IF EXISTS idx_customer_email;
~~~

Trong formatted SQL, điều kiện dbms được ghi cùng dòng **--changeset**. Khi sử dụng SQL theo dialect cụ thể, cần khai báo rollback phù hợp với DBMS đó và xác nhận cú pháp của các marker theo phiên bản Liquibase.

Chỉ gắn comment SQL thông thường như **-- PostgreSQL only** không tạo ra bộ lọc. Liquibase phải nhận được thuộc tính dbms hợp lệ trong định nghĩa changeset.

## 6. Chọn change type chung trước khi dùng dbms

Nếu migration có thể biểu diễn bằng change type trừu tượng của Liquibase, cách đó thường dễ bảo trì hơn việc duy trì hai đoạn SQL tương tự.

Ví dụ, tạo index đơn giản:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-07-customer-email-index
      author: schema-team
      comment: Tăng tốc truy vấn tìm khách hàng theo email
      changes:
        - createIndex:
            tableName: customer
            indexName: idx_customer_email
            columns:
              - column:
                  name: email
      rollback:
        - dropIndex:
            tableName: customer
            indexName: idx_customer_email
~~~

Ở ví dụ này không có dbms. Liquibase có thể sinh DDL phù hợp với DBMS được hỗ trợ cho change type createIndex. Tuy vậy, tương thích change type không đồng nghĩa hiệu năng, lock hoặc khả năng rollback giống nhau giữa các hệ quản trị. Vẫn phải kiểm tra SQL sinh ra.

Khi nào cần dùng dbms? Một số tình huống hợp lý:

- Tạo một loại index đặc biệt như partial index hoặc dùng tùy chọn online/concurrent phụ thuộc DBMS.
- Sử dụng kiểu dữ liệu hay tính năng riêng như JSONB, function hoặc stored procedure đặc thù.
- Chạy bước dữ liệu dùng SQL dialect riêng để tối ưu trên một DBMS.
- Cài đặt các lựa chọn DDL khác nhau để đạt cùng một mục tiêu schema.
- Bỏ qua một thao tác mà một DBMS không hỗ trợ, **sau khi** xác định giải pháp thay thế và kiểm chứng tính tương đương.

Nếu tác vụ làm thay đổi ý nghĩa dữ liệu hoặc ràng buộc cốt lõi, không nên chỉ bỏ qua ở một DBMS và coi như kết quả giống nhau.

## 7. Thiết kế nhánh PostgreSQL và MySQL cho cùng một mục tiêu

Giả sử bảng customer đã có cột email và nhóm muốn bổ sung index cùng tên trên PostgreSQL và MySQL. Hai câu SQL khác nhau một chút, nên có thể tách thành hai changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-08-create-email-index-pg
      author: schema-team
      dbms: postgresql
      comment: Tạo index email trên PostgreSQL, dùng IF NOT EXISTS
      changes:
        - sql:
            sql: >-
              CREATE INDEX IF NOT EXISTS idx_customer_email
              ON customer (email)
      rollback:
        - sql:
            sql: DROP INDEX IF EXISTS idx_customer_email

  - changeSet:
      id: 20261119-09-create-email-index-mysql
      author: schema-team
      dbms: mysql
      comment: Tạo index email bằng cú pháp MySQL
      changes:
        - sql:
            sql: >-
              CREATE INDEX idx_customer_email
              ON customer (email)
      rollback:
        - sql:
            sql: DROP INDEX idx_customer_email ON customer
~~~

Trên PostgreSQL, chỉ changeset có dbms: postgresql được chọn. Trên MySQL, chỉ changeset có dbms: mysql được chọn. Mặc dù hai changeset có id khác nhau, chúng thể hiện một **mục tiêu thiết kế** giống nhau: tạo index idx_customer_email.

| DBMS | Changeset được xét chạy | Changeset bị lọc |
|---|---|---|
| PostgreSQL | 20261119-08-create-email-index-pg | 20261119-09-create-email-index-mysql |
| MySQL | 20261119-09-create-email-index-mysql | 20261119-08-create-email-index-pg |
| MariaDB | Cần khai báo và kiểm chứng nhánh được hỗ trợ | Không giả định MySQL branch tự được chọn |
| Oracle | Không có nhánh tương ứng trong ví dụ | Cả hai đều không đủ cho mục tiêu index |

Cách viết này giúp tách SQL, precondition và rollback cho từng DBMS. Tuy nhiên, nó cũng có **chi phí bảo trì**: một mục tiêu logic có nhiều changeset và mỗi nhánh phải được test. Nếu createIndex chung đã đáp ứng yêu cầu, nên ưu tiên phiên bản chung ở mục trước.

Ví dụ dùng PostgreSQL **IF NOT EXISTS** không bảo đảm index hiện tại có đúng các cột hoặc tùy chọn mong muốn: nếu cùng tên đã tồn tại nhưng định nghĩa khác, migration có thể không sửa cấu trúc đó. Cần kiểm tra schema thực tế sau khi chạy.

## 8. Bộ lọc dbms khác precondition dbms như thế nào?

Liquibase có thể xác định DBMS bằng **thuộc tính dbms của changeset** hoặc thông qua **precondition dbms**. Hai cơ chế này không hoàn toàn tương đương.

### Cách A: Thuộc tính dbms của changeset

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-10-pg-only
      author: schema-team
      dbms: postgresql
      changes:
        - sql:
            sql: SELECT 1
~~~

Khi DBMS không khớp, changeset bị loại khỏi tập được thực thi trong lần update. Thông thường, nó **không được ghi như một changeset đã chạy** trong DATABASECHANGELOG của DBMS bị loại chỉ vì thuộc tính dbms không khớp.

### Cách B: Precondition kiểm tra DBMS

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-11-require-pg
      author: schema-team
      preConditions:
        - onFail: HALT
        - dbms:
            type: postgresql
      changes:
        - sql:
            sql: SELECT 1
~~~

Nếu precondition không đạt, **onFail** quy định phản ứng. Với HALT, Liquibase dừng cập nhật thay vì im lặng bỏ qua changeset. Những lựa chọn khác như WARN, CONTINUE hoặc MARK_RAN mang ý nghĩa vận hành khác và cần được xem xét kỹ theo phạm vi precondition và phiên bản Liquibase.

| Tiêu chí | changeset dbms | preConditions dbms |
|---|---|---|
| Câu hỏi | Changeset này dành cho DBMS nào? | Trạng thái DBMS có đáp ứng điều kiện bắt buộc không? |
| DBMS không khớp | Changeset không được chọn để chạy | Thực hiện hành vi theo onFail |
| Có thể chủ động dừng migration? | Không phải cơ chế báo lỗi bắt buộc khi mismatch | Có, ví dụ onFail: HALT |
| Dùng khi nào? | Chọn nhánh thay đổi cho từng DBMS | Chứng minh điều kiện an toàn hoặc dừng nếu môi trường không phù hợp |
| Lịch sử | Mismatch không tương đương một lần thực thi | MARK_RAN có thể ghi nhận trạng thái theo lựa chọn rõ ràng |

Nếu ứng dụng **bắt buộc** chạy trên PostgreSQL và không có phương án cho DBMS khác, dùng riêng dbms: postgresql có thể khiến toàn bộ thao tác bị bỏ qua trên một database MySQL được cấu hình nhầm. Khi tình huống đó phải là lỗi triển khai, precondition ở phạm vi phù hợp với HALT hoặc một guard của pipeline là lựa chọn cần cân nhắc.

Không dùng MARK_RAN chỉ để làm cho trạng thái hiển thị như đã triển khai khi thực tế database không có schema mong muốn.

## 9. Phân biệt dbms với context và label

Một changeset có thể có nhiều cơ chế lựa chọn:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-12-pg-reporting
      author: reporting-team
      dbms: postgresql
      context: "@reporting"
      labels: report-index
      comment: Tối ưu truy vấn báo cáo chỉ khi chạy trên PostgreSQL với context phù hợp
      changes:
        - sql:
            sql: >-
              CREATE INDEX IF NOT EXISTS idx_customer_email_report
              ON customer (email)
~~~

Mỗi thuộc tính có trách nhiệm khác nhau:

| Thuộc tính | Câu hỏi nó giải quyết |
|---|---|
| dbms | Kết nối hiện tại là loại cơ sở dữ liệu nào? |
| context hoặc contextFilter | Thay đổi thuộc ngữ cảnh thực thi nào được phép chọn? |
| labels | Changeset thuộc nhãn nào để bộ lọc label lựa chọn? |
| preConditions | Database thực tế có đáp ứng điều kiện an toàn hay không? |
| runOnChange/runAlways | Sau khi đã ghi nhận, changeset có thể/chủ động chạy lại theo quy tắc nào? |

Các điều kiện lựa chọn phải **cùng thỏa mãn** để changeset được thực thi theo cấu hình của lần chạy. Chúng không được dùng thay cho nhau: dbms không thể thay thế context môi trường, context không chứng minh DBMS đúng, còn precondition không thay thế thiết kế migration có phụ thuộc hợp lệ.

Đặc biệt, context thông thường **không tự bảo đảm bị bỏ qua khi không có context filter**; trong một số cách chạy Liquibase, nếu không truyền filter thì changeset có context vẫn được xét. Cú pháp context bắt buộc có tiền tố @ là một cách tổ chức cần kiểm tra theo phiên bản Liquibase. Với production, pipeline phải truyền bộ lọc rõ ràng và review tập SQL dự kiến.

## 10. dbms không thay thế kiểm soát phiên bản database

Bộ lọc postgresql cho phép nhận diện **họ DBMS PostgreSQL**, nhưng không có nghĩa mọi phiên bản PostgreSQL đều hỗ trợ chính xác cùng một cú pháp hoặc tùy chọn.

Ví dụ, câu lệnh có thể dùng một tính năng chỉ xuất hiện từ phiên bản PostgreSQL nhất định. Gắn dbms: postgresql chỉ giải quyết phần loại hệ quản trị; nó **không tự kiểm tra phiên bản tối thiểu**.

Khi cần một tính năng phụ thuộc phiên bản:

1. Xác định phiên bản DBMS tối thiểu được hỗ trợ trong tài liệu sản phẩm.
2. Tạo môi trường kiểm thử với phiên bản thấp nhất và phiên bản đích.
3. Sinh SQL dự kiến, sau đó chạy thử migration trên DBMS thực.
4. Nếu cần, thêm precondition hoặc kiểm tra version của database trong bước chuẩn bị phát hành, dựa trên cơ chế được phiên bản Liquibase và DBMS hỗ trợ.
5. Có phương án SQL thay thế hoặc đặt ràng buộc yêu cầu nâng cấp database trước khi triển khai.
6. Ghi rõ điều kiện tương thích trong release record.

Điều này cũng áp dụng cho MariaDB so với MySQL, các phiên bản Oracle, SQL Server và extension hỗ trợ từng database. Không nên hiểu dbms như một ma trận kiểm thử tương thích hoàn chỉnh.

## 11. SQL theo DBMS và transaction/rollback

Một DBMS có thể cung cấp tính năng quản lý lock hoặc DDL trong transaction khác DBMS khác. Khi dùng SQL riêng, changeset cần được thiết kế theo tính chất của hệ quản trị đích.

Ví dụ PostgreSQL cho phép tạo index **CONCURRENTLY** trong nhiều trường hợp để giảm một số loại blocking, nhưng câu lệnh này **không chạy được trong một transaction block**. Với changeset chuyên biệt, một cấu hình minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-13-pg-concurrent-index
      author: schema-team
      dbms: postgresql
      runInTransaction: false
      comment: >-
        Tạo index đồng thời để giảm ảnh hưởng lên bảng đang có truy cập.
        Chỉ chạy trên PostgreSQL, ngoài transaction.
      changes:
        - sql:
            sql: >-
              CREATE INDEX CONCURRENTLY IF NOT EXISTS
              idx_customer_email_online ON customer (email)
      rollback:
        - sql:
            sql: >-
              DROP INDEX CONCURRENTLY IF EXISTS
              idx_customer_email_online
~~~

Ví dụ yêu cầu được thử trên phiên bản PostgreSQL phù hợp và phải kiểm tra khả năng hỗ trợ cú pháp của Liquibase/driver. **runInTransaction: false** làm thay đổi tính nguyên tử: nếu changeset chứa nhiều câu lệnh và chỉ một phần thành công, database có thể ở trạng thái dở dang. Với thao tác dạng này, nên giữ changeset nhỏ, có phương án phát hiện đối tượng index chưa hợp lệ và có runbook phục hồi.

Rollback không chỉ là có dòng rollback trong YAML; nó phải thực sự được test theo DBMS và dữ liệu. Một số DDL có thể tự commit hoặc không rollback như mong muốn. Không đánh đồng khả năng Liquibase phát sinh câu lệnh rollback với khả năng khôi phục toàn bộ dữ liệu sau triển khai.

Khi có hai nhánh SQL phục vụ cùng mục tiêu trên các DBMS khác nhau, hãy viết rollback riêng phù hợp với từng nhánh. Một câu SQL rollback của PostgreSQL có thể vô nghĩa trên MySQL hoặc ngược lại.

## 12. DBMS filter và lịch sử DATABASECHANGELOG

Mỗi database có bảng lịch sử Liquibase riêng, mặc định là **DATABASECHANGELOG**, ghi nhận các changeset đã chạy hoặc được ghi nhận theo những cơ chế đặc biệt. Changelog hiện tại được so với lịch sử tại đúng database kết nối.

Ví dụ một master changelog có ba changeset:

| ID | Điều kiện dbms | Vai trò |
|---|---|---|
| 001-create-customer | Không khai báo dbms | Tạo bảng chung |
| 002-pg-index | postgresql | Tối ưu index PostgreSQL |
| 003-mysql-index | mysql | Tối ưu index MySQL |

Sau khi chạy trên PostgreSQL, lịch sử có thể chứa 001 và 002. Changeset 003 bị lọc do DBMS không khớp nên **không nhất thiết có bản ghi trong DATABASECHANGELOG**. Trên MySQL, lịch sử có thể chứa 001 và 003.

Điều này có nghĩa:

- Không được yêu cầu mọi database phải có **danh sách ID trong DATABASECHANGELOG giống hệt nhau** khi changelog cố ý tách nhánh theo DBMS.
- Phải đối chiếu các changeset **được kỳ vọng trên từng DBMS** với lịch sử và schema thực tế.
- Bộ lọc không khớp không phải là tương đương rollback, cũng không phải là đã chạy thành công.
- Nếu sau này đổi DBMS của một hệ thống, không thể dựa vào lịch sử cũ để tự kết luận những changeset dành riêng cho DBMS mới đã được áp dụng.
- Database thật có thể bị thay đổi ngoài Liquibase, vì vậy lịch sử không chứng minh schema hoàn toàn không có drift.

Các cột thường thấy như ID, AUTHOR, FILENAME, MD5SUM, DATEEXECUTED và EXECTYPE giúp truy vết nội dung đã ghi nhận. Tuy nhiên, lịch sử còn phụ thuộc định danh **id + author + filename/logicalFilePath**. Không sửa id, author hoặc di chuyển file changelog đã triển khai mà không bảo toàn định danh logic và kiểm chứng trên database có lịch sử.

## 13. dbms filter có giúp tránh checksum mismatch không?

Không nên dùng dbms như một cách né tránh quy tắc bất biến của changeset. Liquibase tính checksum từ nội dung changeset theo phiên bản công cụ và so với lịch sử đã ghi nhận.

Giả sử 002-pg-index đã chạy trên PostgreSQL. Sau khi production đã ghi nhận changeset, việc sửa SQL trong 002 rồi chạy lại có thể gây checksum mismatch, dù dbms: postgresql vẫn đúng. Giải pháp thông thường là tạo changeset mới để điều chỉnh index hoặc sửa lỗi.

Tương tự, nếu một changeset đã chạy trên PostgreSQL, sau đó developer bổ sung dbms: mysql vào changeset cũ, có thể dẫn đến lịch sử và hành vi bất ngờ. Thay đổi phạm vi chạy của migration đã phát hành cần được đánh giá riêng thay vì mặc nhiên coi là sửa metadata vô hại.

Các thuộc tính runOnChange và runAlways cho phép một số changeset được thiết kế chạy lại theo quy tắc Liquibase. Chúng phục vụ những tình huống như định nghĩa view hoặc stored procedure, **không** phải cơ chế chung để âm thầm sửa migration tạo bảng hay chuyển dữ liệu đã chạy.

Quy ước an toàn: **một khi changeset đã được áp dụng trong môi trường chia sẻ, hãy coi nó là bất biến; tạo changeset bổ sung cho mọi thay đổi chức năng hoặc schema mới**.

## 14. Chiến lược quản lý một changelog cho nhiều DBMS

Nhóm có thể chọn một trong ba cách tổ chức phổ biến.

### Chiến lược A: Changelog chung với change type độc lập nền tảng

Chỉ sử dụng change type được Liquibase hỗ trợ trên toàn bộ DBMS của dự án, không dùng dbms trừ khi thật cần thiết. Đây là cách ưu tiên khi schema logic giống nhau.

~~~text
master changelog
  - create-customer.yaml
  - add-customer-status.yaml
  - create-customer-index.yaml
~~~

Ưu điểm: ít nhánh, review đơn giản, dễ kiểm tra tương đương schema. Hạn chế: một số tính năng đặc thù DBMS không thể biểu diễn đủ.

### Chiến lược B: Một changelog, thay đổi chung và các nhánh dbms rõ ràng

~~~text
master changelog
  - 001-common-create-customer.yaml
  - 002-postgresql-create-special-index.yaml  (dbms: postgresql)
  - 003-mysql-create-index.yaml               (dbms: mysql)
  - 004-common-add-status.yaml
~~~

Ưu điểm: chung lịch sử mã nguồn, nhánh chuyên biệt có mục tiêu rõ. Hạn chế: số changeset tăng, cần ma trận kiểm thử và kiểm tra schema logic tương đương theo DBMS.

### Chiến lược C: Changelog phân tách theo DBMS, điều phối điểm vào

Có thể có nhóm changelog riêng cho PostgreSQL và nhóm khác cho MySQL, rồi tổ chức master hoặc pipeline lựa chọn theo thiết kế đã review. Cách này cần hợp đồng rất rõ về nguồn sự thật, thứ tự thực thi và mục tiêu schema, tránh tách thành hai hệ thống migration không còn đồng nhất.

Không chọn chiến lược chỉ vì viết file ngắn hơn. Hãy cân nhắc số DBMS được hỗ trợ, lượng SQL đặc thù, độ phức tạp rollback, chi phí bảo trì và khả năng kiểm thử tự động.

## 15. Kiểm chứng dbms trong Spring Boot và CI/CD

Một ứng dụng Spring Boot có thể cấu hình Liquibase:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
~~~

URL kết nối chọn database đích, còn Liquibase nhận diện loại DBMS qua kết nối đó. Nếu staging dùng PostgreSQL nhưng production bị cấu hình nhầm trỏ MySQL, bộ lọc dbms có thể chọn nhánh hoàn toàn khác. Do đó, không chỉ kiểm tra tên môi trường; cần xác minh cả loại DBMS, host, database/schema và phiên bản thực tế.

Có thể tách migration thành job riêng bằng CLI, Maven plugin hoặc Gradle plugin trong pipeline. Dù chạy bằng cách nào, CI/CD nên:

1. Ghim phiên bản Liquibase, JDBC driver và JDK phù hợp.
2. Dùng cùng master changelog từ artifact/revision đã được review.
3. Lấy URL và thông tin xác thực từ secret store; không ghi mật khẩu vào changelog/log.
4. Kiểm tra DBMS hiện tại khớp DBMS được khai báo trong cấu hình môi trường.
5. Chạy validate, kiểm tra status và sinh updateSQL bằng đúng cấu hình DBMS mục tiêu.
6. Kiểm tra sự hiện diện của các changeset bắt buộc và vắng mặt của SQL nhánh khác.
7. Chạy update trên database thử nghiệm cùng DBMS và phiên bản tương ứng.
8. Xác minh schema, dữ liệu và DATABASECHANGELOG sau chạy.
9. Chỉ promote artifact đã kiểm chứng sang môi trường tiếp theo.

**H2 không thay thế kiểm thử PostgreSQL/MySQL.** Một bộ integration test sử dụng H2 có thể không thực thi các changeset dbms: postgresql và không phát hiện lỗi cú pháp SQL PostgreSQL. Nếu hệ thống hỗ trợ nhiều DBMS, cần có test database thật cho mỗi nhánh quan trọng.

## 16. Quy trình xác nhận changeset nào sẽ chạy

Để phát hiện filter sai trước khi thực thi, có thể dùng các lệnh Liquibase tương ứng với phiên bản dự án:

~~~text
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
~~~

Các tên lệnh và cách truyền option kết nối có thể khác giữa phiên bản CLI hoặc plugin; điều quan trọng là **validate/status/update-sql phải chạy trên cùng connection, changelog và bộ lọc** với update dự kiến.

Một quy trình review:

**Bước 1 — Kiểm tra kết nối.** Xác nhận loại DBMS, database và schema. Tránh log credential.

**Bước 2 — Đọc changelog.** Liệt kê changeset không có dbms và changeset chỉ dành cho từng DBMS. Xác định changeset bắt buộc cho schema logic của ứng dụng.

**Bước 3 — Validate.** Kiểm tra cấu trúc và cách Liquibase parse changelog; đây chưa phải bằng chứng SQL chạy được.

**Bước 4 — Status.** Quan sát changeset pending theo connection và bộ lọc. Không mặc định tất cả changeset không xuất hiện trong status đều đã chạy; chúng cũng có thể bị loại bởi filter.

**Bước 5 — update-sql.** Sinh SQL dự kiến. Ví dụ trên PostgreSQL không được có DDL chỉ dành cho MySQL. Kiểm tra cả tên index, kiểu dữ liệu và thứ tự thay đổi.

**Bước 6 — Thực thi trên bản thử nghiệm.** Chạy update với DBMS tương ứng, xác nhận schema sau cùng và thử hành vi ứng dụng.

**Bước 7 — Đối chiếu lịch sử.** Truy vấn DATABASECHANGELOG để xác nhận những changeset đúng DBMS đã được ghi nhận.

**Bước 8 — Thử nâng cấp.** Ngoài database mới, dùng database có lịch sử migration cũ để bảo đảm không có vấn đề do changeset đã chạy và thay đổi bổ sung.

Không thực hiện lệnh update trên production chỉ để thử xem bộ lọc dbms có hoạt động hay không.

## 17. Ví dụ truy vấn lịch sử theo nhánh DBMS

Giả sử changelog có hai changeset tạo index cho PostgreSQL/MySQL. Sau khi update trên PostgreSQL, có thể truy vấn:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    EXECTYPE,
    MD5SUM
FROM DATABASECHANGELOG
WHERE ID IN (
    '20261119-08-create-email-index-pg',
    '20261119-09-create-email-index-mysql'
)
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Kết quả kỳ vọng trên PostgreSQL là changeset PostgreSQL được ghi nhận nếu nó thực sự chạy hoặc được ghi nhận theo một cơ chế có chủ đích; changeset MySQL không có bản ghi do DBMS filter. Trên MySQL thì kỳ vọng ngược lại.

Một bản ghi thiếu trong DATABASECHANGELOG chưa đủ chứng minh changeset bị loại bởi dbms. Nó cũng có thể chưa được include, bị lọc bởi context/label, có precondition, hoặc update chưa diễn ra. Cần đối chiếu log Liquibase, changelog revision và SQL dự kiến.

Nếu tổ chức có nhiều database và schema, phải kết nối đúng DB chứa bảng lịch sử; Liquibase có thể cấu hình tên hoặc schema khác với giá trị mặc định.

## 18. Những lỗi thường gặp với dbms

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra, xử lý |
|---|---|---|
| Changeset PostgreSQL không chạy | Kết nối không thực sự là PostgreSQL hoặc giá trị dbms không khớp | Kiểm tra URL, sản phẩm DBMS thực tế, log và bộ lọc |
| Changelog vẫn validate nhưng schema thiếu cột | Cột cốt lõi bị đặt trong changeset chỉ dành cho một DBMS | Đưa thao tác chung ra changeset chung hoặc tạo nhánh tương đương cho DBMS còn lại |
| Chạy trên MariaDB nhưng nhánh mysql không chạy | DBMS được nhận diện khác hoặc phiên bản không tương thích | Xác minh cách Liquibase nhận diện MariaDB và khai báo nhánh đúng |
| Chạy sai câu SQL dialect | Changeset không gắn dbms, dùng danh sách DBMS quá rộng hoặc dùng phủ định thiếu kiểm soát | Giới hạn rõ các DBMS được hỗ trợ và thử update-sql trên từng loại |
| PostgreSQL lỗi CREATE INDEX CONCURRENTLY | Chạy trong transaction block | Kiểm tra runInTransaction, số câu lệnh và cơ chế phục hồi |
| Index tồn tại nhưng định nghĩa sai | SQL IF NOT EXISTS chỉ kiểm tra tên đối tượng tồn tại | Kiểm tra schema thực tế, tạo migration sửa có chủ đích |
| Mismatch dbms bị hiểu là đã chạy | Nhầm bộ lọc với MARK_RAN | Đối chiếu DATABASECHANGELOG và hành vi filter |
| Chạy được H2 nhưng lỗi production | SQL riêng cho PostgreSQL/MySQL không được H2 thực thi | Test trên đúng loại DBMS đích |
| Checksum mismatch sau khi sửa SQL | Sửa changeset đã triển khai | Tạo changeset mới và giữ định danh lịch sử |
| Staging và production thực thi nhánh khác nhau | Hai môi trường dùng loại DBMS khác hoặc cấu hình kết nối sai | Xác minh cấu hình, ma trận hỗ trợ và artifact |
| Đổi database từ MySQL sang PostgreSQL rồi thấy migration pending khác | Changelog có nhánh riêng và lịch sử không tương ứng | Lập kế hoạch migration dữ liệu/đổi DBMS riêng, kiểm chứng toàn bộ schema |
| Rollback không chạy đúng | SQL rollback không tương thích DBMS hoặc DDL không thể đảo ngược | Thiết kế rollback theo từng nhánh và thử trên DBMS thật |

Tình huống khó nhất thường không phải lỗi cú pháp, mà là **migration bị bỏ qua hợp lệ theo filter nhưng lại là thay đổi ứng dụng bắt buộc phải có**. Vì vậy, kiểm tra tích hợp phải chứng minh ứng dụng có schema cần thiết, không chỉ chứng minh Liquibase update trả exit code 0.

## 19. Bài thực hành: hỗ trợ PostgreSQL và MySQL

Giả sử ứng dụng cần bảng customer dùng chung và index email trên hai DBMS. Hãy thực hành trên **hai database thử nghiệm độc lập**, một PostgreSQL và một MySQL.

### Bước 1 — Tạo migration chung

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: schema-team
      comment: Tạo bảng khách hàng dùng chung cho các DBMS được hỗ trợ
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  constraints:
                    nullable: false
~~~

Trong bài thực hành, id được cấp từ ứng dụng hoặc cơ chế ngoài, chưa khai báo autoIncrement. Với sản phẩm thật cần thiết kế chiến lược sinh khóa, unique constraint, index và kiểu dữ liệu phù hợp; những thành phần đó không tự được xác định bởi ví dụ tối giản này.

### Bước 2 — Thêm hai migration riêng

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-create-email-index-postgresql
      author: schema-team
      dbms: postgresql
      comment: Tạo index email với cú pháp PostgreSQL
      changes:
        - sql:
            sql: CREATE INDEX IF NOT EXISTS idx_customer_email ON customer (email)
      rollback:
        - sql:
            sql: DROP INDEX IF EXISTS idx_customer_email

  - changeSet:
      id: 003-create-email-index-mysql
      author: schema-team
      dbms: mysql
      comment: Tạo index email với cú pháp MySQL
      changes:
        - sql:
            sql: CREATE INDEX idx_customer_email ON customer (email)
      rollback:
        - sql:
            sql: DROP INDEX idx_customer_email ON customer
~~~

Kết nối các file changeset vào master changelog theo đúng thứ tự: tạo bảng trước, sau đó mới tạo index. Đây là bài mô phỏng hai cách dùng dialect, trong một dự án đơn giản createIndex chung vẫn là cách ưu tiên.

### Bước 3 — Kiểm tra trên PostgreSQL

Chạy validate, status, update-sql và chỉ update trên DB PostgreSQL thử nghiệm sau khi review SQL. Kỳ vọng:

- Changeset 001 được chạy.
- Changeset 002 được chọn và được chạy.
- Changeset 003 bị lọc vì dbms không khớp.
- Bảng customer và index idx_customer_email tồn tại với cấu trúc dự kiến.
- DATABASECHANGELOG ghi nhận 001 và 002, sau khi chúng được thực thi.

### Bước 4 — Kiểm tra trên MySQL

Lặp lại trên một database MySQL mới. Kỳ vọng:

- Changeset 001 được chạy.
- Changeset 002 bị lọc.
- Changeset 003 được chọn và được chạy.
- Schema logic có bảng và index phục vụ ứng dụng giống mục tiêu trên PostgreSQL.
- DATABASECHANGELOG ghi nhận 001 và 003.

### Bước 5 — Thử trường hợp khai báo sai dbms

Trên một database thử nghiệm mới, cố ý đặt dbms: oracle cho changeset 002 nhưng kết nối PostgreSQL. Chạy status và update-sql, quan sát rằng SQL tạo index PostgreSQL không xuất hiện từ changeset 002. Đối chiếu với schema cần thiết và nhận xét: **Liquibase không báo lỗi chỉ vì một changeset được chủ động lọc khỏi DBMS hiện tại**. Một bộ kiểm tra schema hoặc danh sách thay đổi bắt buộc là cách nhận ra sự thiếu sót.

Sau đó khôi phục khai báo đúng trước khi hoàn thành bài thực hành. Không sửa file đã triển khai trên database chung; các thử nghiệm này chỉ thực hiện trên database và changelog chưa phát hành.

### Bước 6 — Thử nâng cấp từ trạng thái đã có

Tạo database ở phiên bản trước, chạy changeset chung, rồi bổ sung changeset index và chạy update. So sánh trạng thái cuối với database được dựng từ đầu. Cách kiểm tra này phát hiện khác biệt thứ tự hoặc dữ liệu mà chỉ chạy database sạch có thể không thấy.

## 20. Checklist khi sử dụng dbms trong release

- [ ] Đã xác định chính xác tập DBMS và phiên bản được sản phẩm hỗ trợ.
- [ ] Các thay đổi schema chung được biểu diễn bằng change type chung khi thích hợp.
- [ ] Mỗi SQL chuyên biệt được giới hạn bằng dbms đúng loại DBMS.
- [ ] Mọi mục tiêu schema bắt buộc đều có phương án trên từng DBMS được hỗ trợ.
- [ ] Không dùng phủ định DBMS quá rộng cho một cú pháp chỉ được kiểm thử trên vài sản phẩm.
- [ ] Cú pháp YAML/XML/formatted SQL của dbms đã được validate.
- [ ] Không hiểu sai dbms filter thành precondition, context hoặc label.
- [ ] Đã đánh giá tương thích phiên bản DBMS và dependency/extension.
- [ ] Các changeset DDL đặc biệt có kế hoạch transaction/lock và rollback phù hợp.
- [ ] Changelog cũ đã triển khai không bị sửa nội dung hoặc định danh.
- [ ] CI/CD kiểm tra DBMS thực tế, đúng URL/schema, đúng artifact và secrets.
- [ ] Đã sinh SQL dự kiến trên từng DBMS mục tiêu và review nhánh thực thi.
- [ ] Đã thử database rỗng và database nâng cấp từ release trước.
- [ ] Đã kiểm tra cấu trúc, dữ liệu và hành vi ứng dụng sau migration.
- [ ] Đã đối chiếu DATABASECHANGELOG và biết những changeset bị lọc có chủ đích.
- [ ] Có kế hoạch rollback hoặc forward fix riêng cho từng DBMS khi cần.

**Ghi nhớ:** dbms giúp Liquibase lựa chọn changeset theo loại hệ quản trị mà kết nối hiện tại được nhận diện. Nó hữu ích khi cần SQL hoặc tính năng riêng, nhưng không tự kiểm tra phiên bản DBMS, không tự bảo đảm schema tương đương và không thay thế phép thử migration trên cơ sở dữ liệu thật. Một thiết kế đáng tin cậy kết hợp change type dùng chung khi có thể, nhánh dbms rõ ràng khi cần, lịch sử DATABASECHANGELOG riêng của mỗi môi trường và quy trình kiểm chứng qua Spring Boot hoặc CI/CD.

