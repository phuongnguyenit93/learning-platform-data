# Khai báo và sử dụng changelog properties trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase thông qua changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời triển khai migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một kỹ thuật quan trọng trong chương **Tham số hóa** là dùng **changelog properties** để tái sử dụng giá trị cấu hình trong nhiều changeset mà không phải chép cùng một chuỗi vào mọi chỗ.

Chẳng hạn, cùng một changelog có thể triển khai vào schema khác nhau theo môi trường, đặt tên bảng theo quy ước thống nhất hoặc tái sử dụng giá trị mặc định. Tuy nhiên, property substitution cũng làm kết quả migration phụ thuộc vào cấu hình tại thời điểm chạy. Vì vậy cần hiểu rõ **khai báo ở đâu, tham chiếu như thế nào, giá trị nào thực sự được dùng và điều gì xảy ra với lịch sử sau triển khai**.

## 1. Changelog property là gì?

Một changelog property là cặp **tên – giá trị** được Liquibase cung cấp để thay thế vào chỗ tham chiếu trong changelog. Cú pháp tham chiếu phổ biến là **dấu đô la, dấu ngoặc nhọn và tên thuộc tính**, ví dụ ${appSchema}, ${tablePrefix} hoặc ${initialStatus}.

Ví dụ, thay vì gõ tên schema ở hàng chục changeset:

~~~yaml
databaseChangeLog:
  - property:
      name: appSchema
      value: commerce

  - changeSet:
      id: 001-create-orders
      author: database-team
      changes:
        - createTable:
            schemaName: ${appSchema}
            tableName: orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Liquibase phân giải ${appSchema} thành giá trị được cấu hình, ở đây là commerce, khi xử lý changeset. Ví dụ trên mô tả ý định tạo bảng orders trong schema commerce. Để chạy thực tế, schema commerce cần tồn tại và tài khoản migration phải có quyền tương ứng.

Cần phân biệt ba tầng:

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| **Khai báo property** | name: appSchema, value: commerce | Cung cấp một giá trị để tham chiếu |
| **Tham chiếu property** | schemaName: ${appSchema} | Đặt chỗ để Liquibase thay giá trị |
| **Thay đổi database** | createTable, addColumn, sql | Thực hiện DDL/DML với giá trị đã phân giải |

**Property substitution là thay thế văn bản trong định nghĩa changelog.** Nó không giống SQL prepared-statement parameter binding; không tự kiểm tra giá trị có phải tên schema, tên bảng, kiểu dữ liệu hoặc biểu thức SQL an toàn hay không.

## 2. Vì sao nên dùng changelog properties?

Các tình huống phù hợp gồm:

- **Dùng lại cùng một tên schema hoặc đối tượng:** giảm việc viết lặp tên schema ở nhiều changeset.
- **Tách cấu hình giữa môi trường:** dev có thể dùng schema commerce_dev, staging dùng commerce_stage, production dùng commerce, trong phạm vi chiến lược triển khai đã thiết kế.
- **Quản lý một quy ước đặt tên:** ví dụ tiền tố bảng hoặc tên index cần nhất quán giữa các thay đổi.
- **Tham số hóa một giá trị mặc định có kiểm soát:** ví dụ default status ban đầu, khi thật sự có lý do cấu hình theo môi trường.
- **Tái sử dụng một changelog cho quá trình khởi tạo thử nghiệm:** cấu hình khác nhau cho database thử nghiệm và database tích hợp.
- **Giảm sự phụ thuộc vào cấu hình hard-code:** các pipeline có thể cung cấp tham số qua một giao diện nhất quán.

Changelog properties **không phù hợp** nếu nó khiến cùng một changeset tạo ra những mô hình dữ liệu khác nhau ngoài dự kiến, hoặc dùng để giấu mật khẩu và thông tin nhạy cảm trong SQL/changelog. Chỉ tham số hóa những giá trị có mục đích rõ ràng và có thể kiểm chứng.

## 3. Khai báo property trong YAML changelog

Trong changelog YAML, khai báo property là một phần tử trực thuộc databaseChangeLog:

~~~yaml
databaseChangeLog:
  - property:
      name: appSchema
      value: commerce

  - property:
      name: tablePrefix
      value: shop_

  - property:
      name: initialStatus
      value: PENDING

  - changeSet:
      id: 001-create-orders
      author: database-team
      changes:
        - createTable:
            schemaName: ${appSchema}
            tableName: ${tablePrefix}orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)
                  defaultValue: ${initialStatus}
~~~

Sau khi phân giải giá trị, bảng mục tiêu là commerce.shop_orders và giá trị default của cột status là PENDING. Đây là ví dụ minh họa; tên bảng và cách khai báo default phải tương thích với DBMS thực tế.

### 3.1. Đặt khai báo trước nơi sử dụng

Đặt những property dùng chung ở phần đầu changelog hoặc trong phần khai báo được nạp trước các changeset cần dùng đến chúng. Thứ tự include và includeAll có thể ảnh hưởng đến việc nguồn giá trị nào được đọc trước. Khi dự án có nhiều changelog con, nên thống nhất một vị trí rõ ràng cho property dùng chung, thay vì khai báo trùng lặp ở nhiều file.

### 3.2. Đặt tên property có ý nghĩa

Nên dùng tên thể hiện đúng mục đích:

| Tên nên dùng | Ý nghĩa |
|---|---|
| appSchema | Schema chứa đối tượng nghiệp vụ |
| tablePrefix | Tiền tố thống nhất cho bảng |
| auditIndexName | Tên index cụ thể |
| initialStatus | Giá trị trạng thái ban đầu |
| seedBatchSize | Tham số một tác vụ seed/backfill được thiết kế riêng |

Tránh tên quá chung như value, data hoặc name. Trong các changelog lớn, có thể đặt tiền tố nhóm như ordersSchema hoặc billingSchema để giảm nhầm lẫn giữa các ứng dụng.

### 3.3. Giá trị là văn bản, phải xét ngữ cảnh sử dụng

Liquibase thay property trong changelog theo chuỗi ký tự. Khi property dùng cho tên bảng hoặc schema, chuỗi phải hợp lệ theo quy tắc identifier của DBMS. Khi property tham gia câu SQL, cần xem xét dấu nháy, kiểu dữ liệu, ký tự đặc biệt và nguy cơ SQL injection.

Ví dụ: giá trị initialStatus là PENDING trong thuộc tính defaultValue của change type khác với việc chèn cùng chuỗi vào raw SQL mà không có dấu nháy. Với SQL tự viết, tác giả phải tạo câu lệnh đúng cú pháp DBMS, kiểm tra giá trị được cung cấp và review SQL sau khi thay thế.

## 4. Khai báo trong XML changelog

Với XML, có thể dùng thẻ property và tham chiếu cùng cú pháp:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <property name="appSchema" value="commerce"/>

    <changeSet id="001-create-customer" author="database-team">
        <createTable schemaName="${appSchema}" tableName="customer">
            <column name="id" type="BIGINT">
                <constraints primaryKey="true" nullable="false"/>
            </column>
        </createTable>
    </changeSet>
</databaseChangeLog>
~~~

Ý nghĩa tương đương với YAML: property được khai báo và giá trị được dùng tại vị trí schemaName. Khi chạy ở dự án thực tế, chọn schema XML/XSD tương thích phiên bản Liquibase đang sử dụng.

YAML và XML là hai cách biểu diễn cùng một mô hình changelog. Cần giữ quy ước đặt tên và phạm vi property nhất quán khi một dự án có nhiều định dạng file.

## 5. Sử dụng property trong SQL formatted changelog

Changelog dạng formatted SQL có thể tham chiếu giá trị do Liquibase cung cấp:

~~~sql
--liquibase formatted sql

--changeset database-team:001-create-orders
CREATE TABLE ${appSchema}.orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) DEFAULT 'PENDING'
);

--rollback DROP TABLE ${appSchema}.orders;
~~~

Với ví dụ này, appSchema phải có giá trị từ nguồn cấu hình phù hợp trước khi Liquibase xử lý. Nếu dùng schema commerce, SQL dự kiến chứa commerce.orders. Cần kiểm tra hỗ trợ DDL và rollback ở DBMS đích.

**Tham chiếu trong raw SQL đòi hỏi kiểm soát đầu vào chặt chẽ.** Property substitution không phải phép bind biến SQL an toàn; một giá trị schema không hợp lệ hoặc được đưa vào từ nguồn không tin cậy có thể làm câu SQL sai hoặc nguy hiểm.

Để tránh lỗi, ưu tiên khai báo property chỉ dành cho các giá trị nằm trong danh sách cho phép, dùng cùng quy ước identifier trên mọi môi trường, và review SQL được sinh bởi Liquibase trước khi thực thi.

## 6. Các nguồn cung cấp giá trị property

Property có thể được định nghĩa ngay trong changelog hoặc được truyền vào từ công cụ thực thi tùy cấu hình và phiên bản Liquibase. Các nguồn thường gặp:

| Nguồn | Ví dụ | Khi nào dùng |
|---|---|---|
| Changelog | property name/value trong YAML hoặc XML | Giá trị mặc định, cố định cho changelog |
| Liquibase CLI | Tham số định nghĩa dạng -Dname=value | Chạy migration thủ công hoặc job CI/CD |
| Cấu hình Liquibase/runner | Property hoặc cơ chế tham số được phiên bản đang dùng hỗ trợ | Pipeline và cấu hình môi trường |
| Spring Boot | spring.liquibase.parameters | Ứng dụng Spring Boot tự chạy Liquibase |
| Java API | ChangeLogParameters truyền vào Liquibase | Công cụ tích hợp Liquibase theo chương trình |

### 6.1. Ví dụ truyền từ Liquibase CLI

Giả sử changelog có tham chiếu ${appSchema} và ${tablePrefix}. Trong môi trường thử nghiệm, có thể truyền:

~~~bash
liquibase -DappSchema=commerce_test -DtablePrefix=shop_ --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

Sau khi xem SQL dự kiến và xác nhận đúng database, có thể sử dụng cùng bộ tham số trong lệnh update:

~~~bash
liquibase -DappSchema=commerce_test -DtablePrefix=shop_ --changelog-file=db/changelog/db.changelog-master.yaml update
~~~

Cú pháp và thứ tự tham số CLI nên được đối chiếu theo phiên bản Liquibase đang chạy. Quy trình triển khai phải dùng cùng nguồn giá trị cho validate, status, update-sql và update.

### 6.2. Lưu ý về thứ tự ưu tiên và phạm vi

Không nên dựa vào giả định mơ hồ rằng “property khai báo sau sẽ ghi đè property trước”. Trong một changelog, các property đã được định nghĩa thường được xử lý theo quy tắc giá trị được nhận trước và không được định nghĩa lại tùy tiện; nguồn ngoài changelog, context, DBMS và cách tích hợp có thể tạo ra trường hợp ưu tiên riêng.

Quy tắc thực hành an toàn:

1. Chọn **một nguồn có thẩm quyền** cho mỗi property ở mỗi môi trường.
2. Đặt giá trị mặc định trong changelog chỉ khi phù hợp và đã xác định cách nguồn ngoài override.
3. Tránh định nghĩa trùng tên với các giá trị khác nhau ở nhiều file include.
4. Tránh phụ thuộc vào thứ tự include không ổn định để thay đổi giá trị.
5. Review giá trị phân giải qua update-sql và kiểm tra hậu điều kiện.
6. Ghi lại phiên bản Liquibase, runner/framework, nguồn cấu hình và kết quả kiểm chứng.

Không đổi giá trị property “ngay giữa” các changeset với giả định nó hoạt động như biến có thể gán lại trong một chương trình. Changelog property được dùng để cấu hình việc xử lý changelog, không phải biến trạng thái có thể cập nhật tùy ý.

## 7. Phân biệt changelog properties với các cấu hình Liquibase khác

Dễ nhầm property do người viết định nghĩa với các tham số điều khiển chính Liquibase:

| Cơ chế | Ví dụ | Mục đích |
|---|---|---|
| Changelog property | appSchema=commerce | Giá trị thay thế trong changelog |
| defaultSchemaName | defaultSchemaName=commerce | Schema mặc định cho đối tượng do changelog quản lý |
| liquibaseSchemaName | liquibaseSchemaName=platform_meta | Vị trí bảng metadata DATABASECHANGELOG và DATABASECHANGELOGLOCK |
| Context | contextFilter=dev | Chọn changeset theo phạm vi môi trường hoặc công việc |
| Label | labels=seed-data | Nhóm changeset để lọc khi thực thi |
| Precondition | tableExists | Kiểm tra điều kiện trước khi chạy thay đổi |
| Checksum | MD5SUM trong DATABASECHANGELOG | Giúp kiểm tra nhất quán định nghĩa changeset đã chạy |

Ví dụ: ${appSchema} trong schemaName giúp chọn schema cho đối tượng cụ thể, trong khi defaultSchemaName được dùng khi change type không chỉ rõ schema. Còn liquibaseSchemaName quản lý nơi Liquibase lưu bảng lịch sử và lock; không nên tự động coi nó giống appSchema.

**Context và label quyết định changeset nào được chọn; property quyết định giá trị được thay vào changelog.** Hai cơ chế có thể phối hợp, nhưng không thay thế cho nhau.

### 7.1. Ví dụ dùng property cùng precondition

Một changeset thêm index trên bảng đã có có thể tham chiếu schema thống nhất trong cả precondition lẫn thay đổi:

~~~yaml
databaseChangeLog:
  - property:
      name: appSchema
      value: commerce

  - changeSet:
      id: 002-add-orders-index
      author: database-team
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: ${appSchema}
            tableName: orders
      changes:
        - createIndex:
            schemaName: ${appSchema}
            tableName: orders
            indexName: idx_orders_status
            columns:
              - column:
                  name: status
~~~

Precondition giúp dừng khi bảng chưa tồn tại; nó không tự kiểm tra mọi rủi ro của index, chẳng hạn index đã có hoặc tên trùng. Đối với một migration sản xuất cần bổ sung những kiểm tra thích hợp và review SQL trên DBMS cụ thể.

## 8. Tham số hóa theo DBMS hoặc môi trường

Liquibase có khả năng khai báo property theo những điều kiện nhất định, chẳng hạn dbms hoặc context trong các định dạng và phiên bản hỗ trợ. Tuy nhiên, khi mục tiêu là làm rõ sự khác nhau giữa môi trường, thường dễ kiểm soát hơn nếu cấu hình giá trị ngay tại runner hoặc pipeline và giữ changelog cùng một nguồn.

Ví dụ một changelog dùng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-create-audit
      author: database-team
      changes:
        - createTable:
            schemaName: ${appSchema}
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Các môi trường triển khai có thể dùng:

| Môi trường | Giá trị appSchema | SQL dự kiến |
|---|---|---|
| Local | commerce_local | CREATE TABLE commerce_local.audit_event ... |
| Test | commerce_test | CREATE TABLE commerce_test.audit_event ... |
| Production | commerce | CREATE TABLE commerce.audit_event ... |

Cần xác định schema đã tồn tại, tài khoản có quyền và migrations khác có dựa vào cùng schema hay không. Không dùng tên schema ngẫu nhiên để “test nhanh” trên database đang chứa dữ liệu production.

### 8.1. Context và giá trị thuộc tính

Nếu ứng dụng có context như dev hoặc prod, có thể tổ chức changeset theo context cho dữ liệu seed, tính năng phụ trợ hoặc các thay đổi được phép chọn lọc. Song song, appSchema và giá trị cấu hình vẫn phải được truyền rõ cho từng environment.

**Tránh kỳ vọng context tự tạo ra giá trị property.** Một property chỉ được thay thế nếu có khai báo hoặc nguồn tham số phù hợp. Khi có những khai báo property gắn điều kiện context/dbms, phải kiểm tra khả năng hỗ trợ và thứ tự chọn giá trị của phiên bản Liquibase, nhất là trong changelog gồm nhiều file include.

### 8.2. Hạn chế tham số hóa logic schema

Changelog properties không phải công cụ biến một changelog thành chương trình tùy ý. Nếu cùng id/author/file path nhưng môi trường A tạo bảng có cột customer_id, môi trường B lại tạo bảng không có cột đó do giá trị property hoặc SQL điều kiện, việc so sánh lịch sử sẽ rất khó.

Dùng property cho những tham số **đã được thiết kế để khác nhau** như vị trí schema hoặc prefix có kiểm soát; dùng changeset có điều kiện và nhánh migration rõ ràng khi thực sự có khác biệt về cấu trúc.

## 9. Tích hợp Spring Boot

Trong ứng dụng Spring Boot, có thể truyền changelog properties qua spring.liquibase.parameters:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    default-schema: commerce
    parameters:
      appSchema: ${APP_SCHEMA:commerce}
      tablePrefix: shop_
      initialStatus: PENDING
~~~

Giải thích:

- spring.liquibase.change-log trỏ đến changelog gốc.
- spring.liquibase.parameters là tập giá trị được truyền vào Liquibase để thay thế trong changelog.
- Cú pháp ${APP_SCHEMA:commerce} ở đây là **placeholder của Spring**, lấy biến môi trường APP_SCHEMA và dùng commerce làm giá trị mặc định. Nó được Spring xử lý ở bước cấu hình ứng dụng.
- Cú pháp ${appSchema} xuất hiện **trong changelog** là placeholder của Liquibase. Hai tầng cú pháp có thể nhìn giống nhau nhưng được xử lý tại thời điểm khác nhau.
- spring.liquibase.default-schema là tham số cấu hình Liquibase, có vai trò riêng so với property appSchema.

Khi sử dụng profile khác nhau, hãy kiểm tra cấu hình Spring cuối cùng sau khi tổng hợp application.yml, application-{profile}.yml, biến môi trường và nguồn cấu hình ngoài. Không chỉ đọc một file và giả định đó là giá trị thực khi ứng dụng khởi động.

### 9.1. Khi migration chạy ở pipeline riêng

Một số hệ thống để Spring Boot tự chạy Liquibase trên mỗi instance; hệ thống khác dùng job chuyên trách trong CI/CD và tắt migration tự động khi chạy ứng dụng.

Nếu pipeline và ứng dụng đều có thể chạy migration, chúng phải sử dụng cùng URL, schema metadata, changelog, context, label và property values cần thiết. Cấu hình sai có thể khiến một job triển khai sang schema A, còn instance ứng dụng lại dùng schema B.

Với nhiều instance, Liquibase lock giúp điều phối tiến trình trên cùng bộ bảng metadata. Tuy nhiên, lock không sửa lỗi cấu hình khác nhau giữa các tiến trình. Một migration job chuyên trách giúp dễ quản trị cấu hình, quyền và thứ tự triển khai hơn.

## 10. Tích hợp CI/CD: cố định và kiểm chứng giá trị

Pipeline nên có một bước giải quyết property trước khi thực thi SQL. Một quy trình khả thi:

~~~text
Commit changelog bất biến
           |
           v
Nạp cấu hình của môi trường đích
           |
           v
Xác nhận appSchema, tablePrefix và database URL
           |
           v
liquibase validate
           |
           v
liquibase status --verbose
           |
           v
liquibase update-sql + review
           |
           v
liquibase update
           |
           v
Kiểm tra DATABASECHANGELOG + schema + dữ liệu
~~~

Trước khi thực thi, kiểm tra không còn placeholder chưa được phân giải trong SQL dự kiến, tên schema/bảng nằm trong danh sách cho phép, quyền DDL phù hợp và migration không nhắm vào database sai. Sau khi chạy, lưu phiên bản changelog, tập property không nhạy cảm, cấu hình kết nối đã được che thông tin bí mật và kết quả hậu kiểm.

### 10.1. Không sửa property sau khi changeset đã chạy một cách tùy tiện

Một changeset dùng ${initialStatus} để tạo giá trị default có thể đã chạy với PENDING. Sau khi triển khai, nếu thay initialStatus thành NEW, Liquibase không nhất thiết tự biến default trong database thành NEW. Ngược lại, thay thế property có thể ảnh hưởng đến cách checksum được kiểm tra hoặc cách một changeset chạy lại tạo SQL.

Vì thế, **thay đổi giá trị property không phải một migration mới**. Nếu yêu cầu nghiệp vụ thay đổi default của cột, hãy tạo changeset mới như addDefaultValue hoặc raw SQL được review theo DBMS và lưu lịch sử rõ ràng.

### 10.2. Quản trị property khi rollback

Nếu migration sử dụng ${appSchema} và rollback cũng tham chiếu ${appSchema}, lần rollback về sau phải trỏ đúng schema đã được cập nhật ban đầu. Thay đổi appSchema giữa update và rollback có thể làm rollback tác động lên schema khác hoặc thất bại.

Với thay đổi phức tạp, nên lưu cấu hình triển khai theo phiên bản, review rollback-sql trong đúng môi trường và thử quy trình phục hồi trước khi đưa vào production. Rollback không tự bảo đảm khôi phục dữ liệu đã bị xóa hoặc chuyển đổi không đảo ngược.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SQL còn ${appSchema} | Property chưa được cung cấp hoặc sai tên | Kiểm tra khai báo, CLI/Spring parameters và update-sql |
| Bảng được tạo trong schema không mong muốn | Giá trị appSchema sai hoặc defaultSchemaName khác dự kiến | Kiểm tra config cuối cùng, kết nối và catalog của DBMS |
| Giá trị trên staging khác production | Nguồn cấu hình khác hoặc không được quản lý | Ghi nhận property values và review theo môi trường |
| Tên bảng/index không hợp lệ | Ký tự đặc biệt, quá độ dài hoặc sai identifier case | Dùng quy ước identifier theo DBMS và danh sách cho phép |
| Changelog include trùng property | Nhiều nguồn định nghĩa cùng một tên | Đặt một nguồn có thẩm quyền; kiểm tra thứ tự include |
| Thay property làm mismatch checksum | Property ảnh hưởng định nghĩa changeset đã chạy hoặc thay đổi parser/phiên bản | Điều tra lịch sử, khôi phục định nghĩa và tạo changeset sửa chữa |
| Rollback lỗi vì không tìm thấy đối tượng | Dùng giá trị schema khác lần update | Phục hồi cấu hình đúng, review rollback SQL |
| Pipeline lộ thông tin bí mật | Đưa password/token vào changelog property hoặc log | Dùng secret manager, loại bỏ bí mật khỏi changelog và log |
| Precondition không kiểm tra đúng bảng | Property phân giải sai schema hoặc tên bảng | Kiểm tra SQL, catalog và kết quả precondition trên database thử nghiệm |

Cần xử lý lỗi theo đúng lớp: cú pháp/định nghĩa changelog, nguồn giá trị, đường dẫn include, cấu hình connection, quyền hoặc trạng thái schema. Đừng dùng clear-checksums để bỏ qua những sai lệch chưa được hiểu rõ.

## 12. Bài thực hành có kiểm chứng

Mục tiêu: triển khai một changelog với property appSchema và tablePrefix, kiểm tra giá trị phân giải và hiểu giới hạn khi đổi property sau triển khai.

**Điều kiện:** PostgreSQL thử nghiệm hoặc DBMS có cơ chế schema tương đương; có quyền tạo schema/bảng; không kết nối production. Tạo sẵn schema practice_a và practice_b bằng công cụ quản trị tương ứng trước khi chạy.

### Bước 1. Viết changelog dùng property

~~~yaml
databaseChangeLog:
  - property:
      name: tablePrefix
      value: lab_

  - changeSet:
      id: practice-001-create-order
      author: learner
      changes:
        - createTable:
            schemaName: ${appSchema}
            tableName: ${tablePrefix}orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)
                  defaultValue: PENDING
      rollback:
        - dropTable:
            schemaName: ${appSchema}
            tableName: ${tablePrefix}orders
~~~

Ở đây tablePrefix có giá trị mặc định từ changelog; appSchema do môi trường chạy cung cấp. Ví dụ có rollback để minh họa việc sử dụng lại property, nhưng rollback của dropTable làm mất dữ liệu trong bảng nếu đã có dữ liệu; chỉ dùng trong môi trường lab rỗng.

### Bước 2. Xem SQL dự kiến

Cung cấp appSchema bằng CLI của phiên bản đang dùng:

~~~bash
liquibase -DappSchema=practice_a --changelog-file=db/changelog/practice.yaml validate
liquibase -DappSchema=practice_a --changelog-file=db/changelog/practice.yaml update-sql
~~~

Kiểm tra câu lệnh tạo bảng practice_a.lab_orders; không còn chuỗi ${appSchema} hoặc ${tablePrefix} chưa được phân giải. Nếu SQL không đúng, kiểm tra nguồn giá trị và định danh property trước khi chạy.

### Bước 3. Triển khai và đối chiếu

~~~bash
liquibase -DappSchema=practice_a --changelog-file=db/changelog/practice.yaml update
liquibase -DappSchema=practice_a --changelog-file=db/changelog/practice.yaml history
~~~

Xác minh bảng practice_a.lab_orders đã tồn tại và bảng DATABASECHANGELOG của database ghi nhận practice-001-create-order. Kiểm tra cột id, status và default của status thông qua metadata DBMS.

### Bước 4. Quan sát hậu quả khi đổi property

Trên **cùng database thử nghiệm**, thay appSchema bằng practice_b trong lệnh xem SQL:

~~~bash
liquibase -DappSchema=practice_b --changelog-file=db/changelog/practice.yaml update-sql
~~~

Không chạy update khi chưa hiểu kết quả. Liquibase có thể tiếp tục xem changeset đã chạy theo lịch sử, hoặc gặp khác biệt về checksum/hành vi tùy phiên bản và cách property tham gia định nghĩa; thay appSchema không tự động tạo bảng tương ứng ở practice_b. Đây là lý do không nên dùng cùng bộ lịch sử để kỳ vọng một changeset duy nhất sẽ tự thực thi lại cho nhiều schema chỉ vì property thay đổi.

Muốn thử triển khai độc lập vào schema khác, nên dùng một database lab khác hoặc bộ lịch sử Liquibase được tách có chủ đích, sau đó so sánh hai môi trường. Không sao chép, xóa hoặc chỉnh trực tiếp DATABASECHANGELOG để ép changeset chạy lại.

### Bước 5. Tổng hợp kết quả

Ghi lại: tập property đã dùng, SQL sau phân giải, bảng nào thực sự được tạo, lịch sử được ghi nhận và hành vi khi thay giá trị property. Giải thích vì sao việc đổi property không thay thế được changeset migration khi mô hình dữ liệu cần thay đổi.

## 13. Checklist khi thiết kế changelog properties

- [ ] Mỗi property có tên rõ ràng, mục đích và nguồn giá trị xác định.
- [ ] Giá trị mặc định phù hợp; không phụ thuộc vào thứ tự include ngẫu nhiên.
- [ ] Không trùng tên property với các giá trị khác nhau nếu chưa thiết kế rõ phạm vi.
- [ ] Đã phân biệt changelog property với defaultSchemaName và liquibaseSchemaName.
- [ ] Không trộn lẫn property substitution với SQL bind parameter.
- [ ] Mọi tên schema/bảng/index và chuỗi đưa vào SQL đều được kiểm tra hợp lệ.
- [ ] Không đặt password/token hoặc dữ liệu bí mật vào changelog property sẽ bị log hoặc sinh SQL.
- [ ] Cấu hình CLI, Spring Boot và CI/CD nhất quán cho cùng môi trường.
- [ ] Đã review update-sql và không còn placeholder chưa phân giải.
- [ ] Đã kiểm tra checksum và lịch sử trên database đã từng triển khai.
- [ ] Có kế hoạch thay đổi schema bằng changeset mới khi property về sau đổi ý nghĩa nghiệp vụ.
- [ ] Rollback dùng đúng giá trị đã áp dụng và có kế hoạch bảo vệ dữ liệu.
- [ ] Đã thử cả đường nâng cấp từ database cũ và đường triển khai trên database thử nghiệm mới.
- [ ] Đã lưu bằng chứng cấu hình không nhạy cảm cùng phiên bản changelog.

## 14. Kết luận

**Changelog properties** giúp thay thế những giá trị cấu hình lặp lại trong Liquibase bằng các tham chiếu có tên, ví dụ ${appSchema} và ${tablePrefix}. Chúng hỗ trợ dùng chung một cấu trúc changelog trong phạm vi môi trường đã thiết kế, nhưng vẫn cần hiểu rõ giá trị đến từ đâu, được phân giải khi nào và ảnh hưởng thế nào đến changeset đã triển khai.

Trong thực hành quản lý schema và dữ liệu, hãy dùng property một cách có kiểm soát, kiểm tra SQL trước khi chạy, giữ nguyên lịch sử changeset và tạo changeset mới khi yêu cầu cấu trúc thay đổi. Kết hợp cùng precondition, checksum, rollback có kế hoạch và CI/CD quản lý cấu hình, cách làm này giúp các lần migration có thể kiểm chứng và tái tạo qua nhiều môi trường.
