# Bổ sung mô tả bảng, cột và kiểm tra SQL được sinh trong Liquibase

Trong cơ sở dữ liệu, tên bảng và tên cột hiếm khi truyền tải toàn bộ ý nghĩa nghiệp vụ. Cột **status** có thể biểu thị trạng thái thanh toán, vòng đời khách hàng hoặc một cờ xử lý nội bộ. Nếu không có tài liệu đi kèm, người bảo trì dễ suy diễn sai, trong khi người review migration khó phát hiện thay đổi định nghĩa dữ liệu.

Liquibase cho phép quản lý **mô tả bảng và cột (remarks/comments)** bằng changelog, tương tự cách quản lý CREATE TABLE, ADD COLUMN, index và constraint. Quan trọng hơn, trước khi cập nhật database, ta có thể **kiểm tra SQL được Liquibase sinh ra** để xác nhận mô tả sẽ được áp dụng bằng cú pháp đúng với hệ quản trị đích.

Bài học thuộc chương **Thay đổi bảng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Sau khi hoàn thành, bạn có thể:

1. Giải thích vai trò của mô tả bảng/cột trong database schema.
2. Khai báo remarks khi tạo bảng/cột và bổ sung hoặc chỉnh sửa remarks trên đối tượng đã tồn tại.
3. Sử dụng **setTableRemarks** và **setColumnRemarks** trong changelog YAML/XML/JSON theo khả năng hỗ trợ của DBMS.
4. Phân biệt **remarks** của Liquibase với **COMMENT ON** hoặc cú pháp riêng của DBMS.
5. Chạy **validate**, **status --verbose**, **update-sql** và đối chiếu SQL dự kiến trước **update**.
6. Kiểm tra mô tả thật trong metadata database, lập kế hoạch rollback và kiểm soát nhiều môi trường.

## 1. Mô tả bảng và cột là gì?

**Mô tả bảng** giải thích mục đích hoặc ý nghĩa của một bảng; **mô tả cột** làm rõ dữ liệu trong cột, đơn vị tính, miền giá trị hay những lưu ý nghiệp vụ.

Ví dụ, bảng **customer** có thể được mô tả là:

> Thông tin khách hàng được sử dụng trong quản lý đơn hàng; không lưu dữ liệu xác thực.

Cột **customer.status** có thể được mô tả là:

> Trạng thái vòng đời: ACTIVE, SUSPENDED hoặc CLOSED.

Một số DBMS lưu các mô tả này trong **system catalog** hoặc **information_schema**. Công cụ quản trị database, IDE hay phần mềm quản trị metadata có thể hiển thị chúng, tùy khả năng hỗ trợ.

Điểm quan trọng: **remarks là metadata có cấu trúc**, không phải constraint. Một mô tả ghi “status chỉ nhận ACTIVE/SUSPENDED/CLOSED” không tự khiến DBMS từ chối giá trị khác. Muốn thực thi quy tắc, cần thêm CHECK constraint, foreign key, kiểu dữ liệu phù hợp hoặc cơ chế kiểm soát tương ứng.

### 1.1. Mô tả tốt nên chứa gì?

| Nội dung | Ví dụ | Lợi ích |
|---|---|---|
| Ý nghĩa nghiệp vụ | “Thời điểm đơn hàng được xác nhận” | Tránh nhầm với thời điểm tạo |
| Đơn vị hoặc chuẩn | “Khối lượng tính bằng gram” | Tránh lỗi đổi đơn vị |
| Miền giá trị | “PENDING, PAID hoặc CANCELLED” | Hỗ trợ đọc hiểu và kiểm thử |
| Quy tắc giá trị rỗng | “NULL khi chưa có người xử lý” | Phân biệt không biết với không áp dụng |
| Nguồn dữ liệu | “Được đồng bộ từ hệ thống hóa đơn” | Giúp truy vết lineage |
| Cảnh báo bảo mật phù hợp | “Có thể chứa dữ liệu liên hệ” | Nhắc nhóm quản lý dữ liệu đúng cách |

Mô tả nên ngắn, chính xác và bền theo thời gian. Không ghi secret, mật khẩu, mã truy cập, thông tin cá nhân cụ thể hay SQL chứa dữ liệu nhạy cảm trong remarks. Metadata này có thể được người dùng có quyền đọc catalog hoặc các công cụ khám phá dữ liệu nhìn thấy.

## 2. Remarks nằm ở đâu trong vòng đời một migration?

Hãy xem comments như một phần của **hợp đồng schema** mà các nhóm phát triển và vận hành có thể kiểm tra.

~~~mermaid
flowchart TD
    A[Changelog mô tả bảng/cột] --> B[Liquibase parse changeset]
    B --> C[validate / status / update-sql]
    C --> D{SQL đúng DBMS và đúng phạm vi?}
    D -->|Chưa| E[Sửa migration trước phát hành]
    D -->|Rồi| F[Liquibase update]
    F --> G[Metadata bảng/cột trong database]
    F --> H[DATABASECHANGELOG]
    G --> I[Truy vấn catalog xác minh remarks]
    H --> J[Đối chiếu ID, author, FILENAME, checksum]
~~~

Một thay đổi về mô tả có thể có **changeset ID và lịch sử triển khai riêng**, dù không làm thay đổi dữ liệu hàng trong bảng. Việc thêm mô tả không nên được xem là thao tác bên ngoài quy trình migration nếu dự án đã chọn Liquibase làm nguồn quản lý schema.

Ví dụ luồng thay đổi:

1. Tạo bảng **customer**.
2. Thêm cột **status**.
3. Bổ sung mô tả cho bảng và cho cột **status**.
4. Kiểm tra SQL được sinh, chạy trên development.
5. Đọc metadata để xác nhận comment thực tế.
6. Đưa cùng artifact đã kiểm chứng qua các môi trường.

## 3. Các cách khai báo mô tả trong Liquibase

Có ba cách thường gặp, mỗi cách phục vụ một thời điểm khác nhau.

| Cách | Dùng khi nào? | Ý tưởng |
|---|---|---|
| Thuộc tính **remarks** khi **createTable** | Tạo bảng mới và muốn ghi mô tả ngay | Khai báo metadata cùng cấu trúc bảng |
| Thuộc tính **remarks** trên **column** | Tạo/thêm cột và mô tả cột ngay | Đặt mô tả cạnh định nghĩa cột |
| **setTableRemarks / setColumnRemarks** | Bảng/cột đã tồn tại hoặc cần sửa mô tả | Migration riêng cập nhật metadata |
| SQL gốc theo DBMS | Liquibase hoặc change type chưa hỗ trợ trường hợp cụ thể | Ví dụ PostgreSQL dùng COMMENT ON |

Ưu tiên các **change type** của Liquibase khi chúng được hỗ trợ trên DBMS và phiên bản dự án. Với trường hợp đặc thù, SQL gốc giúp kiểm soát cú pháp nhưng làm tăng trách nhiệm bảo trì đa DBMS.

Không phải mọi DBMS đều hỗ trợ comments trên bảng và cột theo cùng cách. Không nên kết luận rằng changelog đã validate thành công thì SQL sinh ra chắc chắn tương thích với mọi database.

## 4. Khai báo remarks ngay khi tạo bảng

Giả sử cần tạo bảng **customer** có ý nghĩa rõ ràng và lưu thông tin liên hệ.

Ví dụ YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "customer-team"
      changes:
        - createTable:
            tableName: customer
            remarks: "Hồ sơ khách hàng dùng trong quy trình đặt hàng"
            columns:
              - column:
                  name: id
                  type: bigint
                  remarks: "Định danh kỹ thuật của khách hàng"
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  remarks: "Địa chỉ email liên hệ của khách hàng"
              - column:
                  name: status
                  type: varchar(24)
                  remarks: "Trạng thái vòng đời tài khoản khách hàng"
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: customer
~~~

Ý nghĩa:

- **createTable.remarks** mô tả bảng.
- **column.remarks** mô tả từng cột trong quá trình tạo.
- **constraints** vẫn là nguồn thể hiện ràng buộc thực thi.
- **rollback dropTable** xóa cả bảng, vì thế có thể làm mất dữ liệu nếu bảng đã có dữ liệu thực tế.

**Lưu ý tương thích:** Khả năng chuyển thuộc tính remarks thành SQL khi tạo bảng/cột phụ thuộc change type, driver và DBMS. Nếu mục tiêu là quản lý remarks độc lập, hoặc cần sửa mô tả trên đối tượng đã tồn tại, hãy dùng **setTableRemarks** và **setColumnRemarks** rồi kiểm tra **update-sql**.

### 4.1. Khi thêm cột mới bằng addColumn

Có thể đặt remarks cùng định nghĩa cột nếu Liquibase/DBMS đích hỗ trợ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002-add-customer-timezone"
      author: "customer-team"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: timezone
                  type: varchar(64)
                  remarks: "Tên múi giờ theo định dạng IANA, ví dụ Asia/Ho_Chi_Minh"
      rollback:
        - dropColumn:
            tableName: customer
            columnName: timezone
~~~

Đây là một migration minh họa độc lập, giả định bảng **customer** đã tồn tại. Không thể chỉ thêm dòng **remarks** vào một changeset tạo cột đã chạy rồi mong Liquibase âm thầm cập nhật comment: sửa changeset cũ có thể phát sinh vấn đề checksum và làm lệch lịch sử. Với schema đã phát hành, hãy tạo changeset mới để bổ sung mô tả.

## 5. Bổ sung mô tả bảng đã tồn tại: setTableRemarks

**setTableRemarks** là change type cho phép đặt hoặc thay đổi comment của một bảng mà không cần tái tạo bảng.

Ví dụ YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-customer-table-remarks"
      author: "schema-team"
      changes:
        - setTableRemarks:
            schemaName: public
            tableName: customer
            remarks: "Hồ sơ khách hàng phục vụ đơn hàng; không chứa thông tin đăng nhập"
~~~

Các trường chính:

| Thuộc tính | Công dụng |
|---|---|
| **tableName** | Tên bảng cần mô tả |
| **remarks** | Nội dung mô tả sẽ ghi vào metadata của bảng |
| **schemaName** | Schema chứa bảng nếu DBMS hỗ trợ hoặc cấu hình cần chỉ định |
| **catalogName** | Catalog, khi cần và được DBMS/driver hỗ trợ |

Tên change type phải viết đúng **setTableRemarks**, không nhầm với SQL statement hay thuộc tính comment của từng cột. Một số công cụ sinh SQL đích có thể sử dụng COMMENT ON, ALTER TABLE hoặc cú pháp khác để áp dụng yêu cầu.

### 5.1. Tại sao nên tách thành changeset mới?

Ví dụ bảng **customer** đã chạy trên development, staging và production. Sau đó đội phát triển muốn làm rõ ý nghĩa bảng.

Cách đúng về lịch sử thường là **thêm changeset mới** chỉ chứa setTableRemarks:

- Không sửa changeset **createTable** đã triển khai.
- Dễ review phần thay đổi: chỉ cập nhật metadata, không thay đổi cột hoặc dữ liệu.
- Có ID riêng để truy vết trong DATABASECHANGELOG.
- Dễ xác minh SQL dự kiến có phải chỉ là lệnh cập nhật comment hay không.

Độ rủi ro thường thấp hơn thao tác thay đổi dữ liệu hoặc kiểu cột, nhưng không bằng không: SQL cập nhật metadata vẫn cần quyền phù hợp và có thể bị DBMS từ chối.

## 6. Bổ sung mô tả cột đã tồn tại: setColumnRemarks

**setColumnRemarks** đặt hoặc thay đổi mô tả cho một cột cụ thể của bảng.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-004-customer-status-remarks"
      author: "schema-team"
      changes:
        - setColumnRemarks:
            schemaName: public
            tableName: customer
            columnName: status
            remarks: "ACTIVE: hoạt động; SUSPENDED: tạm khóa; CLOSED: đã đóng"
~~~

Các trường chính:

| Thuộc tính | Vai trò |
|---|---|
| **tableName** | Xác định bảng sở hữu cột |
| **columnName** | Xác định cột cần cập nhật mô tả |
| **remarks** | Nội dung mô tả mới |
| **schemaName** | Chỉ định schema khi phù hợp |
| **catalogName** | Chỉ định catalog nếu DBMS hỗ trợ |
| **columnDataType** | Có thể được yêu cầu hoặc hữu ích với một số DBMS/phiên bản để dựng SQL |

Đối với một số hệ quản trị, thay đổi comment của cột phải thực hiện thông qua câu lệnh ALTER/ MODIFY chứa cả kiểu dữ liệu hoặc đặc điểm cột. Vì vậy, dù **setColumnRemarks** chỉ có mục tiêu metadata, hãy kiểm tra SQL được sinh ra để chắc chắn Liquibase không vô tình thay đổi kiểu dữ liệu, nullable, default hoặc các thuộc tính khác.

### 6.1. Nhận diện chính xác bảng và schema

Giả sử có hai bảng trùng tên:

~~~text
public.customer
archive.customer
~~~

Một changeset không chỉ rõ schema có thể tác động đối tượng trong **default schema** của kết nối, không nhất thiết đúng bảng mà người viết dự định. Do đó:

- Sử dụng schemaName khi nhiều schema cùng tồn tại.
- Kiểm tra cấu hình defaultSchemaName và URL của Liquibase.
- Không suy ra schema từ tên service, nhãn changeset hoặc thư mục mã nguồn.
- Kiểm tra SQL được sinh có chỉ đúng đối tượng không.

## 7. Ví dụ hoàn chỉnh: mô tả bảng và hai cột PostgreSQL

Giả sử bảng **public.customer** đã tồn tại, có các cột **email** và **status**, và **chưa có mô tả cũ**. Mục tiêu là bổ sung ba comments có thể kiểm chứng.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-005-document-customer"
      author: "schema-team"
      dbms: postgresql
      comment: "Add database remarks for customer table and columns"

      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: customer
        - columnExists:
            schemaName: public
            tableName: customer
            columnName: email
        - columnExists:
            schemaName: public
            tableName: customer
            columnName: status

      changes:
        - setTableRemarks:
            schemaName: public
            tableName: customer
            remarks: "Hồ sơ khách hàng phục vụ xử lý đơn hàng"

        - setColumnRemarks:
            schemaName: public
            tableName: customer
            columnName: email
            remarks: "Email liên hệ; có thể khác email đăng nhập"

        - setColumnRemarks:
            schemaName: public
            tableName: customer
            columnName: status
            remarks: "Trạng thái vòng đời: ACTIVE, SUSPENDED hoặc CLOSED"

      rollback:
        - sql:
            sql: |
              COMMENT ON COLUMN public.customer.status IS NULL;
              COMMENT ON COLUMN public.customer.email IS NULL;
              COMMENT ON TABLE public.customer IS NULL;
~~~

**Cách đọc ví dụ:**

1. **dbms: postgresql** giới hạn changeset vào PostgreSQL; các ví dụ SQL rollback cũng dùng cú pháp PostgreSQL.
2. Các precondition kiểm tra rằng đối tượng tồn tại; **HALT** nếu giả định không thỏa.
3. Hai change type riêng biệt mô tả bảng và mô tả cột.
4. SQL rollback dùng **COMMENT ... IS NULL** để xóa comment, dựa trên giả định ban đầu chưa có comment.
5. Nếu trước migration đã có mô tả, rollback phải **khôi phục đúng nội dung trước đó**, không mặc định xóa comment.

Đây là bài tập trên database thử nghiệm. Khi chạy thật, cần xác minh quyền, default schema, độ dài comment và khả năng hỗ trợ của phiên bản Liquibase/DBMS.

### 7.1. Vì sao rollback cần biết trạng thái cũ?

Giả sử trước migration có mô tả:

~~~text
customer.email = "Email chính của khách hàng"
~~~

Sau changeset, mô tả đổi thành:

~~~text
customer.email = "Email liên hệ; có thể khác email đăng nhập"
~~~

Nếu rollback bằng **COMMENT ... IS NULL**, bạn đã **xóa** comment cũ, không khôi phục nó. Một rollback đúng cần có nội dung cũ làm baseline, ví dụ trong PostgreSQL:

~~~sql
COMMENT ON COLUMN public.customer.email
IS 'Email chính của khách hàng';
~~~

Với metadata cũ không được quản lý bằng Liquibase, hãy đọc catalog và ghi nhận baseline trước khi thay đổi. Rollback remarks là bài toán **khôi phục metadata**, không phải chỉ đảo một lệnh DDL.

## 8. SQL PostgreSQL được sinh ra trông như thế nào?

Với change type cập nhật remarks trên PostgreSQL, SQL dự kiến có thể tương đương:

~~~sql
COMMENT ON TABLE public.customer
IS 'Hồ sơ khách hàng phục vụ xử lý đơn hàng';

COMMENT ON COLUMN public.customer.email
IS 'Email liên hệ; có thể khác email đăng nhập';

COMMENT ON COLUMN public.customer.status
IS 'Trạng thái vòng đời: ACTIVE, SUSPENDED hoặc CLOSED';
~~~

Đây là **minh họa dạng SQL**, không phải bản chép nguyên văn từ một lần chạy Liquibase. SQL thực tế có thể khác về cách quote định danh, số lệnh, schema qualifier, dấu chấm phẩy và câu lệnh quản lý lịch sử tùy phiên bản, driver và cấu hình.

PostgreSQL dùng **COMMENT ON** cho bảng và cột. Một số ví dụ:

~~~sql
-- Đặt hoặc thay mô tả bảng
COMMENT ON TABLE public.customer IS 'Hồ sơ khách hàng';

-- Đặt hoặc thay mô tả cột
COMMENT ON COLUMN public.customer.email IS 'Địa chỉ liên hệ';

-- Gỡ mô tả
COMMENT ON COLUMN public.customer.email IS NULL;
~~~

Lưu ý **NULL** không tương đương chuỗi rỗng trong mọi cơ chế hiển thị. Khi muốn xóa comment, phải kiểm tra cú pháp của DBMS và kết quả catalog.

### 8.1. Những yếu tố cần quan sát trong SQL được sinh

- Có đúng lệnh cập nhật **comment**, không có DROP TABLE/ DROP COLUMN ngoài dự kiến.
- Tên bảng và cột có đúng, bao gồm schema.
- Chuỗi Unicode tiếng Việt được giữ nguyên.
- Dấu nháy đơn trong nội dung mô tả được escape đúng.
- Không có statement khiến kiểu dữ liệu hoặc constraint thay đổi trái ý định.
- Nếu cần transaction, SQL và DBMS hỗ trợ đúng hành vi mong đợi.
- Khi đổi remarks cũ, SQL là thao tác **ghi đè mô tả**, không phải thêm dòng ghi chú độc lập.

## 9. Khác biệt giữa các hệ quản trị dữ liệu

Liquibase nhằm cung cấp ngôn ngữ changelog thống nhất, nhưng SQL cuối cùng do **SQL generator cho DBMS đích** quyết định.

| DBMS | Cách quản lý comment thường thấy | Điểm cần kiểm tra |
|---|---|---|
| PostgreSQL | COMMENT ON TABLE / COLUMN | Schema, quyền sở hữu đối tượng, Unicode |
| Oracle | COMMENT ON TABLE / COLUMN | Tên schema, quyền và giới hạn metadata |
| MySQL | COMMENT trong định nghĩa TABLE/COLUMN hoặc ALTER TABLE | Kiểu dữ liệu cột, charset/collation, thuộc tính giữ nguyên |
| MariaDB | COMMENT trên table/column qua DDL tương ứng | Hành vi ALTER/ MODIFY và phiên bản |
| SQL Server | Extended properties như MS_Description hoặc cơ chế metadata tương ứng | SQL generator hỗ trợ hay không, schema/object hierarchy |
| DB2, H2 và DBMS khác | Có cú pháp hoặc mức hỗ trợ khác nhau | Kiểm tra support matrix của đúng phiên bản |

Bảng chỉ minh họa **hướng tiếp cận**, không cam kết tất cả phiên bản Liquibase hỗ trợ setTableRemarks/setColumnRemarks trên mọi DBMS kể trên. Một loại change có thể được hỗ trợ cho một DBMS nhưng không hỗ trợ auto rollback hoặc một đặc tính riêng.

**Nguyên tắc:** Dùng đúng Liquibase và driver của pipeline thật để kiểm tra, thay vì suy luận SQL từ bản YAML.

### 9.1. Cẩn thận khi DBMS phải định nghĩa lại cột

Trên một số DBMS, muốn sửa comment cột cần dùng câu lệnh tái định nghĩa cột (ví dụ một biến thể ALTER TABLE ... MODIFY COLUMN). Nếu thay đổi này làm mất một thuộc tính cột như DEFAULT, NOT NULL hoặc charset, migration có thể gây regression dù người viết chỉ muốn sửa mô tả.

Vì vậy, với MySQL/MariaDB, hãy kiểm tra kỹ **toàn bộ câu SQL** được Liquibase sinh, không chỉ tìm từ **COMMENT** trong output. Nếu cần, thử trên bản sao schema thật và kiểm tra lại kiểu cột/constraint sau update.

## 10. Dùng XML để khai báo setTableRemarks/setColumnRemarks

Ngoài YAML, XML cho phép mô tả cùng thay đổi theo cấu trúc tường minh.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="20261119-006" author="schema-team">
        <setTableRemarks
            schemaName="public"
            tableName="customer"
            remarks="Hồ sơ khách hàng dùng cho quy trình đơn hàng"/>

        <setColumnRemarks
            schemaName="public"
            tableName="customer"
            columnName="email"
            remarks="Email liên hệ của khách hàng"/>
    </changeSet>
</databaseChangeLog>
~~~

XML hữu ích khi dự án muốn validation dựa trên XSD và tổ chức changelog theo cấu trúc rõ ràng. Tuy nhiên, XSD hợp lệ không có nghĩa hai thao tác được hỗ trợ trên mọi DBMS đích.

Nếu dự án dùng JSON, các change type tương ứng cũng có thể được mô tả trong phần **changes**; quy tắc kiểm chứng SQL không thay đổi.

## 11. Dùng SQL gốc khi change type không phù hợp

Một số nhóm lựa chọn viết formatted SQL hoặc change SQL thủ công cho remarks, đặc biệt khi DBMS có tính năng metadata riêng.

Ví dụ **formatted SQL** riêng cho PostgreSQL:

~~~sql
--liquibase formatted sql

--changeset schema-team:20261119-007 dbms:postgresql
--comment: Document customer table and contact email
COMMENT ON TABLE public.customer
IS 'Hồ sơ khách hàng phục vụ xử lý đơn hàng';

COMMENT ON COLUMN public.customer.email
IS 'Email liên hệ của khách hàng';

--rollback COMMENT ON COLUMN public.customer.email IS NULL;
--rollback COMMENT ON TABLE public.customer IS NULL;
~~~

Ví dụ này phù hợp khi trước đó chưa có comment hoặc chính sách rollback chấp nhận gỡ comment. Nếu đã có comment, rollback cần khôi phục đúng giá trị cũ.

### Khi nào nên ưu tiên change type thay vì SQL thủ công?

Ưu tiên **setTableRemarks/setColumnRemarks** khi:

- DBMS đích được Liquibase hỗ trợ cho change type đó.
- Dự án có thể dùng cùng changelog cho nhiều DBMS.
- Người review muốn nắm **ý định** thay vì phải đọc mọi biến thể SQL vendor.
- Nhóm có khả năng xác minh SQL output và kiểm thử DBMS thật.

Ưu tiên SQL gốc khi:

- Cần cú pháp metadata chuyên biệt.
- SQL generator không hỗ trợ trường hợp cụ thể.
- Có yêu cầu kiểm soát chính xác DDL do database team quy định.
- Có test và rollback rõ ràng cho cú pháp vendor-specific.

Tránh dùng SQL thủ công chỉ vì change type sinh SQL khác phong cách mong muốn nhưng vẫn đúng; việc viết tay tăng chi phí bảo trì và rủi ro đa môi trường.

## 12. Tại sao phải xem SQL được sinh trước khi update?

Việc khai báo changelog đúng cấu trúc mới cho biết **ý định**. Còn thay đổi thực tế lên database sẽ được thực thi bằng **SQL do Liquibase tạo ra hoặc SQL bạn khai báo**.

Việc review SQL giúp phát hiện:

1. **Sai object:** tableName/columnName đúng về tên nhưng nằm ở schema khác.
2. **Sai DBMS:** changelog được sinh cho hệ quản trị không hỗ trợ comments theo cách dự kiến.
3. **Thay đổi ngoài phạm vi:** thay vì chỉ thêm remarks, SQL còn ALTER kiểu hoặc NOT NULL.
4. **Thiếu escape:** mô tả chứa dấu nháy hoặc ký tự đa byte không được truyền như mong muốn.
5. **Migration chưa đủ tiền đề:** object chưa tồn tại hoặc schema có trạng thái khác dự kiến.
6. **Mâu thuẫn lịch sử:** changeset bị coi là đã chạy hoặc chạy lại ngoài ý muốn.
7. **Rủi ro rollback:** comment mới ghi đè comment cũ nhưng rollback không khôi phục giá trị ban đầu.

**update-sql** là lệnh hữu ích để xem SQL mà Liquibase dự kiến dùng cho những changeset cần xử lý. Output không thay thế việc thực thi thử trên database đại diện, vì khả năng sinh SQL đúng và khả năng thực thi thành công là hai vấn đề khác nhau.

## 13. Quy trình kiểm tra bằng Liquibase CLI

Giả sử changelog gốc được nạp qua file **db/changelog/db.changelog-master.yaml** và kết nối JDBC đã được cấu hình bằng phương pháp an toàn.

### Bước 1: Xác định phiên bản và database đích

~~~bash
liquibase --version
~~~

Kiểm tra Liquibase version, JDBC driver, URL, database, schema và user. Đừng chạy một lệnh migration chỉ vì terminal đang đứng trong repository đúng: **working directory không xác định database đích**.

### Bước 2: Validate changelog

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate
~~~

Validation giúp tìm lỗi về cấu trúc changelog, tên change type và khai báo không hợp lệ theo khả năng parser. Tuy nhiên, **validate không chứng minh toàn bộ SQL tương thích DBMS, tất cả quyền đầy đủ hoặc mọi câu lệnh sẽ chạy thành công**.

### Bước 3: Xem changeset còn pending

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
~~~

Kết quả phụ thuộc **DATABASECHANGELOG của chính database đang kết nối**. Nếu changeset remarks chưa được nạp qua include hoặc đã ghi nhận từ trước, output có thể không giống mong đợi.

### Bước 4: Sinh SQL dự kiến

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

Ở bước này, kiểm tra SQL tương ứng với setTableRemarks/setColumnRemarks và các SQL metadata do Liquibase quản lý. Một bản update-sql có thể chứa các lệnh quản lý transaction, lock, DATABASECHANGELOG hoặc các thay đổi pending khác; không mặc định mọi câu trong output đều là nội dung của changeset remarks.

### Bước 5: Chỉ thực thi sau khi review

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
~~~

Nên chạy lần đầu trên development hoặc database thử nghiệm có schema tương đương mục tiêu. Khi production yêu cầu phê duyệt, output SQL và danh sách pending phải được xem xét trước update.

**Lưu ý phiên bản:** Cú pháp option CLI của Liquibase có thể thay đổi giữa các thế hệ. Ví dụ dùng cách đặt tham số thường gặp; cần đối chiếu **--help** của phiên bản thực tế. Không ghi password trong lệnh khi có nguy cơ bị lưu vào shell history, process list hoặc CI log.

## 14. Cách review output update-sql có hệ thống

Thay vì chỉ tìm xem output có chứa từ **COMMENT**, hãy dùng checklist:

| Câu hỏi | Kỳ vọng với migration chỉ cập nhật remarks |
|---|---|
| Changeset nào đang pending? | Đúng ID, author và changelog file đã review |
| SQL nhắm tới đối tượng nào? | Đúng schema, bảng và cột |
| Có bao nhiêu thao tác cập nhật comment? | Khớp số đối tượng dự kiến |
| SQL có thay đổi cấu trúc ngoài metadata? | Không, trừ khi DBMS yêu cầu DDL kèm thuộc tính được giữ nguyên chính xác |
| Nội dung comments có nguyên vẹn? | Không mất dấu tiếng Việt, không sai dấu nháy |
| Có SQL bất ngờ từ changeset khác? | Phải được review riêng trước khi chạy |
| Preconditions có được xử lý đúng? | Phù hợp onFail/onError và onSqlOutput nếu dùng |
| Hành vi rollback có rõ không? | Khôi phục metadata cũ khi có baseline |
| Có khác biệt so với staging không? | Phải giải thích được dựa trên lịch sử, DBMS và cấu hình |

### 14.1. Đừng bỏ qua filter và precondition

Nếu changelog có **contexts**, **labels** hoặc **dbms**, chúng có thể khiến một changeset remarks được hoặc không được xét tại runtime. Một changeset không có trong update-sql có thể đã được ghi nhận, bị filter loại, không được include hoặc không tương thích DBMS.

Nếu có precondition, chế độ **update-sql** có thể đánh giá hay bỏ qua một số điều kiện tùy cấu hình **onSqlOutput** và phiên bản. Vì vậy, SQL preview phải được kiểm tra cùng thông tin database, log và precondition.

### 14.2. Lưu bằng chứng review phù hợp

Trong CI/CD, có thể lưu artifact chứa SQL dự kiến và danh sách changeset pending theo quy định tổ chức. Trước khi lưu, cần kiểm tra log có thể chứa thông tin nhạy cảm như URL, schema nội bộ hoặc literal nghiệp vụ hay không.

Dùng cùng một version Liquibase, cùng artifact changelog và cấu hình filter khi so sánh **preview** với **update thật**. Nếu đối tượng schema thay đổi giữa hai thời điểm, preview có thể không còn đại diện chính xác.

## 15. Xác minh remarks trực tiếp trong PostgreSQL

Sau update, cách kiểm chứng mạnh nhất là **đọc metadata thật** của database, không chỉ xem rằng Liquibase trả về exit code thành công.

### 15.1. Mô tả bảng

PostgreSQL có hàm **obj_description**. Ví dụ:

~~~sql
SELECT
    obj_description('public.customer'::regclass, 'pg_class')
        AS table_remarks;
~~~

Kết quả mong đợi trong ví dụ:

~~~text
Hồ sơ khách hàng phục vụ xử lý đơn hàng
~~~

Giá trị trả về có thể là NULL nếu bảng chưa có comment. Nếu không có bảng hoặc thiếu quyền, truy vấn có thể báo lỗi. Hãy xác nhận đang kết nối tới đúng database và schema.

### 15.2. Mô tả từng cột

PostgreSQL có hàm **col_description**; một truy vấn dùng catalog:

~~~sql
SELECT
    a.attname AS column_name,
    col_description(a.attrelid, a.attnum) AS column_remarks
FROM pg_catalog.pg_attribute a
WHERE a.attrelid = 'public.customer'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND a.attname IN ('email', 'status')
ORDER BY a.attnum;
~~~

Truy vấn này hiển thị mô tả hiện tại của hai cột, giúp đối chiếu với changelog. Nếu kết quả không giống nội dung vừa deploy, kiểm tra:

- Changelog có được include đúng không?
- Changeset còn pending hay đã ghi nhận?
- Có một changeset khác thay đổi comment sau đó không?
- SQL đã chạy trên schema nào?
- Có lỗi encoding, truncation hoặc giới hạn của DBMS không?

### 15.3. Không coi công cụ quản trị là nguồn chân lý duy nhất

Một IDE có thể cache metadata, chỉ hiển thị phần comment hoặc yêu cầu refresh. Khi không thấy mô tả trong UI, hãy kiểm tra catalog trực tiếp trước khi kết luận Liquibase không cập nhật.

## 16. Xác minh remarks trên MySQL/MariaDB

Với MySQL và một số phiên bản MariaDB, metadata comment thường được truy cập qua **information_schema**. Ví dụ:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer';
~~~

Với cột:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer'
  AND COLUMN_NAME IN ('email', 'status')
ORDER BY ORDINAL_POSITION;
~~~

Ngoài **COLUMN_COMMENT**, cần quan sát **COLUMN_TYPE**, **IS_NULLABLE** và **COLUMN_DEFAULT** để bảo đảm DDL không vô tình biến đổi thuộc tính cột.

Không copy nguyên SQL PostgreSQL **COMMENT ON** sang MySQL: mỗi DBMS có cách cập nhật metadata khác nhau. Nếu remarks không được hỗ trợ đầy đủ bởi Liquibase/DBMS phiên bản đang dùng, hãy lựa chọn cách triển khai và kiểm chứng khác theo tài liệu chính thức của phiên bản đó.

## 17. Kiểm tra lịch sử DATABASECHANGELOG

Sau khi Liquibase xử lý changeset, thông tin về lần chạy thường được ghi trong **DATABASECHANGELOG**. Có thể đối chiếu:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Một số điểm cần nhớ:

- **ID + AUTHOR + FILENAME/logicalFilePath** xác định changeset theo cách Liquibase quản lý lịch sử.
- **EXECTYPE** thể hiện cách changeset được xử lý, có thể bao gồm EXECUTED, MARK_RAN hoặc RERAN.
- **MD5SUM** là checksum dùng trong quá trình kiểm soát thay đổi đã ghi nhận.
- Một dòng lịch sử không chứng minh comment vẫn còn đúng sau đó: người có quyền có thể sửa metadata thủ công.
- Không xóa hoặc sửa hàng DATABASECHANGELOG chỉ để “chạy lại” migration comments.

Nên kết hợp **đối chiếu lịch sử** với **truy vấn metadata thật**.

## 18. Mối quan hệ với checksum và việc sửa mô tả

Giả sử một changeset đã chạy trên production:

~~~yaml
- setColumnRemarks:
    tableName: customer
    columnName: status
    remarks: "Trạng thái khách hàng"
~~~

Sau đó, người phát triển sửa thành:

~~~yaml
- setColumnRemarks:
    tableName: customer
    columnName: status
    remarks: "Trạng thái vòng đời của khách hàng"
~~~

Nếu sửa ngay trong changeset cũ đã triển khai, Liquibase có thể phát hiện **checksum mismatch** theo cơ chế checksum của nó. Dù chỉ thay metadata mô tả, thay đổi trong nội dung changeset vẫn có thể được xem là thay đổi lịch sử.

Cách phù hợp trong đa số quy trình:

1. Giữ nguyên changeset đã phát hành.
2. Tạo một changeset mới cập nhật remarks.
3. Mô tả rõ lý do thay đổi ngữ nghĩa.
4. Kiểm tra SQL dự kiến từ changeset mới.
5. Triển khai và xác minh catalog.

Không dùng **clear-checksums**, **runAlways**, **runOnChange** hoặc thay đổi ID/đường dẫn như cách mặc định để né quy trình tạo changeset mới. Những cơ chế này có mục đích riêng và có thể gây hành vi không mong muốn nếu áp dụng tùy tiện.

## 19. Preconditions cho migration chỉ cập nhật remarks

Mặc dù chỉ thay comment, migration vẫn nên xác nhận đối tượng tồn tại. Nếu bảng hoặc cột chưa có, SQL metadata có thể thất bại.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-008-document-order-status"
      author: "orders-team"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: order_status
      changes:
        - setColumnRemarks:
            tableName: orders
            columnName: order_status
            remarks: "Trạng thái đơn hàng theo vòng đời xử lý"
~~~

Trong ví dụ, **HALT** làm lộ sai lệch schema thay vì đánh dấu changeset đã xử lý mà không cập nhật mô tả.

### 19.1. Có nên dùng MARK_RAN không?

**MARK_RAN** ở local precondition có thể khiến Liquibase ghi nhận changeset là đã xử lý dù phần SQL không chạy. Điều này có thể phù hợp với một số kế hoạch baseline có kiểm chứng, nhưng **không nên dùng chỉ để bỏ qua lỗi thiếu bảng**. Nó tạo ra lịch sử cho một thay đổi chưa thực sự có trong database.

### 19.2. Khi điều kiện phải phù hợp toàn changelog

Nếu toàn bộ changelog chỉ dành cho PostgreSQL, có thể dùng **preConditions cấp changelog** kiểm tra DBMS. Nhưng điều kiện “bảng orders đã tồn tại” thường chỉ là tiền đề của một changeset và phù hợp hơn khi đặt **ở cấp changeset**.

### 19.3. Cần đọc đầy đủ precondition và SQL preview

Ngay cả khi precondition kiểm tra tableExists đạt, nó không chứng minh cột có đúng datatype hoặc SQL generator sẽ không tác động thuộc tính khác trên DBMS như MySQL. Nếu cần an toàn cao, bổ sung kiểm chứng schema trực tiếp trước/sau migration.

## 20. Cách đặt nội dung remarks có thể duy trì lâu dài

Mô tả cần thống nhất giữa nghiệp vụ, schema và tài liệu ứng dụng.

### 20.1. Tránh mô tả quá chung

Không nên:

~~~text
customer.status: "Trạng thái"
payment.amount: "Số tiền"
orders.created_at: "Ngày tạo"
~~~

Nên:

~~~text
customer.status:
  "Trạng thái vòng đời hồ sơ: ACTIVE, SUSPENDED, CLOSED"

payment.amount:
  "Giá trị thanh toán tính theo đơn vị nhỏ nhất của currency"

orders.created_at:
  "Thời điểm hệ thống ghi nhận đơn hàng, lưu theo UTC"
~~~

Ví dụ về tiền tệ chỉ phù hợp nếu chính ứng dụng thật sự lưu theo đơn vị nhỏ nhất. Không áp dụng một mô tả nghe hợp lý nhưng trái với thiết kế dữ liệu hiện có.

### 20.2. Không gắn nghĩa nghiệp vụ chưa được xác nhận

Nếu cột **customer.status** đang chứa nhiều giá trị khác nhau, không tự viết mô tả giới hạn chỉ ba giá trị mà chưa kiểm tra domain và dữ liệu hiện hữu. Comment sai có thể nguy hiểm vì người phát triển tin vào metadata để viết logic.

Trước khi đổi mô tả:

- Đối chiếu tài liệu nghiệp vụ đã duyệt.
- Kiểm tra schema, constraint và enum tương ứng.
- Kiểm tra dữ liệu thực tế khi được phép.
- Review với chủ sở hữu miền dữ liệu.

### 20.3. Tránh chứa dữ liệu dễ lỗi thời

Mô tả cột không nên chứa số liệu vận hành động như “có 1,2 triệu dòng” hoặc tên nhân sự trực vận hành. Comments có vòng đời tương đối dài; nội dung thay đổi liên tục nên đặt trong tài liệu vận hành khác.

## 21. Kiểm soát ảnh hưởng tới schema và hiệu năng

Phần lớn thay đổi comment không chỉnh dữ liệu hàng, nhưng tác động vận hành khác nhau tùy DBMS và SQL được sinh.

Cần cân nhắc:

- **Quyền:** user migration có thể cần quyền sở hữu bảng hoặc quyền ALTER/COMMENT phù hợp.
- **Lock:** một số DDL/metadata operation có thể cần lock trên đối tượng, ảnh hưởng truy cập đồng thời.
- **Transaction:** DBMS khác nhau có quy tắc commit/rollback DDL khác nhau.
- **Metadata cache:** công cụ quản trị có thể hiển thị chậm sau thay đổi.
- **Giới hạn độ dài:** comment của bảng/cột có thể bị giới hạn và xử lý khác nhau theo DBMS.
- **Charset/Unicode:** đảm bảo pipeline và database bảo toàn tiếng Việt, ký tự đặc biệt và escape.
- **Drift:** một admin sửa comment trực tiếp có thể khiến catalog khác changelog dù lịch sử Liquibase không đổi.

Với thay đổi remarks số lượng lớn, tránh gộp vô hạn các thay đổi metadata vào một changeset nếu cần rollback, review hoặc điều tra độc lập. Nhóm theo bảng hoặc phạm vi nghiệp vụ thường dễ kiểm soát hơn.

## 22. Tổ chức changeset remarks và review nhiều người

Một cấu trúc hợp lý:

~~~text
db/changelog/
  db.changelog-master.yaml
  releases/
    2026/
      11/
        001-create-customer.yaml
        002-add-customer-status.yaml
        003-document-customer-columns.yaml
~~~

Trong changelog gốc:

~~~yaml
databaseChangeLog:
  - include:
      file: releases/2026/11/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2026/11/002-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2026/11/003-document-customer-columns.yaml
      relativeToChangelogFile: true
~~~

Việc đặt migration mô tả sau migration tạo bảng/cột thể hiện đúng quan hệ phụ thuộc. Khi review PR, người review cần xem:

1. Tên tệp mới và thứ tự include.
2. Các bảng/cột thực sự tồn tại ở thời điểm changeset chạy.
3. Comments mới có được phê duyệt về nghiệp vụ không.
4. Có sửa changeset cũ hoặc di chuyển tệp đã triển khai không.
5. SQL generator có tạo câu lệnh ngoài dự kiến không.
6. Rollback khôi phục comment trước đó như thế nào.

Không đổi đường dẫn tệp đã triển khai chỉ để đưa nó vào một thư mục đặt tên đẹp hơn; **FILENAME** là một phần định danh changeset nếu không có logicalFilePath ổn định.

## 23. Tích hợp với Spring Boot và CI/CD

Trong ứng dụng Spring Boot, Liquibase có thể chạy lúc khởi động hoặc được tách ra thành một bước migration của pipeline.

Ví dụ cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-staging.internal:5432/orders
    username: orders_migrator
    password: "<inject-at-runtime>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: public
~~~

Đây là dữ liệu ví dụ, không chứa credential thật. Trong dự án thực tế, secret cần được inject qua cơ chế bảo mật tương ứng, và tài khoản runtime ứng dụng có thể tách khỏi tài khoản DDL của Liquibase.

Một pipeline có kiểm soát nên:

- Sử dụng artifact changelog bất biến.
- Xác nhận URL, schema, user, context/label filter của từng môi trường.
- Chạy validate và status.
- Sinh và review SQL dự kiến bằng đúng Liquibase/DBMS mục tiêu.
- Áp dụng update trên môi trường thử nghiệm trước.
- Kiểm tra metadata thực tế và DATABASECHANGELOG.
- Giữ lại bằng chứng review và deployment ID.
- Chỉ triển khai production sau khi xác nhận không có SQL ngoài phạm vi mô tả.

**Quan trọng:** Các lệnh sinh SQL trên hai database có lịch sử pending khác nhau có thể cho output khác nhau ngay cả khi changelog giống nhau. Cần đối chiếu cả **trạng thái DATABASECHANGELOG** chứ không chỉ so sánh text SQL giữa staging và production.

## 24. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Changelog validate nhưng update báo không hỗ trợ change type | SQL generator/DBMS đích chưa hỗ trợ | Kiểm tra phiên bản và support matrix |
| SQL sinh ra không có lệnh comment | Changeset đã chạy, không được include hoặc bị filter | Xem status --verbose, changelog và lịch sử |
| Comment được cập nhật vào bảng khác | Chưa chỉ định schema hoặc default schema sai | Kiểm tra schemaName và SQL được sinh |
| Mô tả cột không đổi sau update | Sai columnName, schema hoặc có changeset khác ghi đè | Đối chiếu catalog và lịch sử |
| SQL chỉ định sai tên có chữ hoa/ký tự đặc biệt | Vấn đề quoting và case sensitivity | Kiểm tra cách DBMS xử lý tên định danh |
| Ghi comment tiếng Việt bị lỗi dấu | Encoding file, JDBC hoặc database charset không đồng nhất | Kiểm tra UTF-8 và thông số kết nối |
| Mô tả chứa dấu nháy đơn gây lỗi SQL thủ công | SQL literal không được escape đúng | Dùng change type hoặc escape theo DBMS |
| MySQL ALTER cột làm thay đổi thuộc tính khác | Cách sửa comment yêu cầu định nghĩa lại cột | Review toàn SQL và compare schema trước/sau |
| Rollback xóa mô tả cũ | Đã dùng COMMENT ... IS NULL thay vì khôi phục baseline | Lưu và restore mô tả trước migration |
| Chỉnh remarks trong changeset cũ bị checksum mismatch | Đã sửa nội dung đã triển khai | Giữ changelog cũ, tạo changeset mới |
| SQL preview đúng nhưng update lỗi | Lệch thời điểm/schema, thiếu quyền, lock, DBMS khác | Chạy test cùng môi trường và kiểm tra log |
| IDE chưa hiện comment mới | Cache metadata hoặc quyền xem catalog | Refresh IDE, query catalog trực tiếp |
| DATABASECHANGELOG có EXECUTED nhưng comment không đúng | Drift hoặc thay đổi thủ công sau migration | So sánh catalog, audit và artifact triển khai |
| Pipeline update ở sai database | JDBC URL/profile/secret sai | Xác minh endpoint, database, schema và user |

Khi điều tra, không “sửa” lịch sử bằng cách xóa hoặc cập nhật hàng trong DATABASECHANGELOG. Hãy xác định changeset nào đã chạy, SQL nào được sinh và metadata thực tế hiện ở trạng thái nào.

## 25. Bài thực hành: bổ sung và kiểm chứng remarks

**Bối cảnh:** Dịch vụ đặt hàng dùng PostgreSQL, Spring Boot và Liquibase. Bảng **public.orders** tồn tại với các cột **order_id**, **order_status** và **created_at**. Hiện các đối tượng chưa có mô tả. Yêu cầu bổ sung comment rõ ràng rồi kiểm tra SQL sẽ chạy.

### 25.1. Changelog thực hành

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "practice-document-orders-001"
      author: "training-team"
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: orders
        - columnExists:
            schemaName: public
            tableName: orders
            columnName: order_status
        - columnExists:
            schemaName: public
            tableName: orders
            columnName: created_at

      changes:
        - setTableRemarks:
            schemaName: public
            tableName: orders
            remarks: "Đơn hàng được ghi nhận bởi hệ thống giao dịch"

        - setColumnRemarks:
            schemaName: public
            tableName: orders
            columnName: order_status
            remarks: "Trạng thái xử lý đơn hàng theo quy trình nghiệp vụ"

        - setColumnRemarks:
            schemaName: public
            tableName: orders
            columnName: created_at
            remarks: "Thời điểm hệ thống tạo đơn hàng, lưu theo UTC"

      rollback:
        - sql:
            sql: |
              COMMENT ON COLUMN public.orders.created_at IS NULL;
              COMMENT ON COLUMN public.orders.order_status IS NULL;
              COMMENT ON TABLE public.orders IS NULL;
~~~

Đây là ví dụ dành cho database thử nghiệm, **giả định không có comments trước đó**. Nếu bảng thật đã có mô tả, phải đọc baseline và thiết kế rollback khôi phục đúng giá trị cũ.

### 25.2. Quy trình thực hiện

1. Tạo một database PostgreSQL thử nghiệm hoặc dùng môi trường thực hành được cấp phép.
2. Xác nhận bảng **public.orders** và các cột được yêu cầu tồn tại.
3. Đăng ký changelog thực hành vào luồng Liquibase của bài học.
4. Chạy **validate** với kết nối thử nghiệm.
5. Chạy **status --verbose** và xác nhận changeset thực hành còn pending.
6. Chạy **update-sql**, kiểm tra các câu COMMENT ON TABLE / COLUMN, tên đối tượng và ký tự tiếng Việt.
7. Xác nhận output không chứa thay đổi kiểu dữ liệu hoặc constraint ngoài phạm vi.
8. Chạy **update** trên database thử nghiệm.
9. Truy vấn **obj_description** và **col_description** để xác nhận comments.
10. Đối chiếu ID, AUTHOR, FILENAME và EXECTYPE trong DATABASECHANGELOG.
11. Thử rollback trên bản sao database dùng cho thực hành, kiểm tra comments được gỡ đúng giả định.
12. Chạy lại update và đối chiếu kết quả, tránh thử trên production.

### 25.3. Những điều cần giải thích sau khi chạy

- Vì sao một migration chỉ đổi remarks vẫn cần ID changeset riêng?
- Vì sao sql preview không phải bằng chứng duy nhất?
- Nếu output có ALTER COLUMN ngoài dự kiến, cần điều tra gì?
- Nếu comment cũ đã tồn tại, rollback phải thay đổi ra sao?
- Nếu staging hiện comment đúng nhưng production còn comment cũ, nên kiểm tra lịch sử nào trước?

## 26. Câu hỏi tự kiểm tra

**1. Khác biệt giữa remarks và constraint là gì?**

Remarks là metadata diễn giải cho người đọc; constraint là quy tắc dữ liệu được DBMS kiểm soát. Một comment nói cột “bắt buộc” không tự tạo NOT NULL.

**2. Khi nào dùng setTableRemarks thay vì createTable.remarks?**

Khi bảng đã tồn tại hoặc cần cập nhật mô tả mà không sửa changeset tạo bảng đã phát hành.

**3. Tại sao phải xem update-sql nếu chỉ thay comment?**

Để kiểm tra đúng đối tượng, schema, SQL dialect, encoding và phát hiện DDL phát sinh ngoài ý định.

**4. Vì sao không thể copy COMMENT ON của PostgreSQL sang mọi DBMS?**

Vì cú pháp và cơ chế lưu metadata khác nhau; Liquibase phải sinh SQL theo target DBMS hoặc nhóm phát triển phải viết SQL riêng.

**5. Vì sao không nên sửa remarks trong một changeset cũ đã chạy?**

Vì có thể thay đổi checksum và làm lịch sử triển khai không nhất quán; nên tạo changeset mới.

**6. Một changeset trong DATABASECHANGELOG có đảm bảo comment còn tồn tại không?**

Không. Database có thể bị sửa thủ công sau update, hoặc một changeset khác đã ghi đè comment. Cần truy vấn catalog thực tế.

**7. Muốn rollback đúng một comment trước đây đã có nội dung, làm gì?**

Ghi nhận mô tả trước khi migration và phục hồi đúng chuỗi cũ, không mặc định đặt comment thành NULL.

**8. Làm sao biết setColumnRemarks không làm đổi kiểu cột trên MySQL?**

Review SQL được sinh và kiểm tra metadata kiểu cột, nullable và default trước/sau migration trên DBMS đích.

**9. Changelog YAML hợp lệ có bảo đảm SQL comments chạy được ở mọi DBMS không?**

Không. Phụ thuộc khả năng hỗ trợ change type và SQL generator theo phiên bản Liquibase/DBMS.

**10. Vì sao cần schemaName trong hệ thống nhiều schema?**

Để tránh Liquibase tác động bảng trùng tên ở schema khác hoặc default schema không như dự kiến.

## 27. Checklist trước khi hoàn tất migration remarks

- [ ] Mục đích của từng bảng/cột đã được chủ sở hữu dữ liệu xác nhận.
- [ ] Mô tả không nhầm với constraint hoặc quy tắc đảm bảo dữ liệu.
- [ ] Không chứa secret, dữ liệu cá nhân cụ thể hoặc thông tin nhạy cảm không cần thiết.
- [ ] Đã chọn đúng cách khai báo: createTable/column remarks hay setTableRemarks/setColumnRemarks.
- [ ] Những changeset đã triển khai được giữ nguyên; thay đổi metadata mới có changeset ID mới.
- [ ] Có schemaName/catalogName phù hợp với database đích.
- [ ] Liquibase version, driver và DBMS hỗ trợ change type đã chọn.
- [ ] Chạy validate và status --verbose với đúng kết nối.
- [ ] Review update-sql, xác nhận đối tượng, comment, encoding và mọi SQL đi kèm.
- [ ] Không có thay đổi kiểu dữ liệu, default, nullable hoặc constraint ngoài dự kiến.
- [ ] Precondition phù hợp và không che lỗi bằng MARK_RAN thiếu căn cứ.
- [ ] Rollback khôi phục metadata cũ, hoặc nêu rõ giả định trước khi gỡ comment.
- [ ] Đã thử trên database có cấu trúc đại diện cho môi trường triển khai.
- [ ] Đã truy vấn catalog để xác nhận comment sau update.
- [ ] Đã đối chiếu DATABASECHANGELOG và lưu bằng chứng deploy.
- [ ] Đã kiểm tra context/label filter, endpoint và quyền khi qua nhiều môi trường.
- [ ] Có kế hoạch xử lý drift nếu catalog bị sửa ngoài Liquibase.

**Kết luận:** Bổ sung remarks cho bảng và cột giúp biến schema thành tài liệu kỹ thuật có thể tra cứu ngay tại database. Liquibase cho phép quản lý những mô tả này bằng changeset có lịch sử rõ ràng, nhưng tính đúng đắn chỉ được khẳng định khi **SQL dự kiến phù hợp DBMS và đúng đối tượng**, migration được kiểm chứng trên môi trường phù hợp, và metadata thực tế sau update khớp với mô tả đã được review. Kết hợp setTableRemarks, setColumnRemarks, update-sql, kiểm tra catalog và quản lý rollback là cách duy trì schema dễ hiểu mà vẫn bảo toàn quy trình triển khai an toàn.

