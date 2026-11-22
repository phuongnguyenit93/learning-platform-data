# Giới hạn tùy biến để giữ migration dễ kiểm tra và bảo trì

Trong chương **Mở rộng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, tùy biến giúp Liquibase đáp ứng khác biệt giữa các DBMS và nhu cầu riêng của dự án. Tuy nhiên, mỗi lớp tùy biến bổ sung thêm một nơi chứa logic, một tập phụ thuộc và một khả năng phát sinh lỗi. Nếu changelog dựa quá nhiều vào SQL động, custom change, precondition tự viết, extension không được quản lý hoặc quy tắc ngầm theo môi trường, người review khó dự đoán database sẽ thay đổi thế nào và nhóm vận hành khó tái lập kết quả.

Phạm vi của dịch vụ **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài học tập trung vào việc đặt giới hạn cho tùy biến để những nguyên tắc đó vẫn được duy trì khi dự án mở rộng.

Định hướng đầy đủ của dịch vụ: Nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Nguyên tắc xuyên suốt: **chọn cách biểu diễn đơn giản nhất vẫn đáp ứng đúng yêu cầu**, ưu tiên change type chuẩn có semantics rõ ràng, giới hạn SQL đặc thù trong phạm vi nhỏ, chỉ viết extension khi có nhu cầu thực sự và kiểm thử mọi hành vi tùy biến trên các DBMS/version được hỗ trợ.

## 1. Vì sao cần giới hạn tùy biến?

Một migration dễ bảo trì cần cho reviewer biết:
- Schema trước thay đổi là gì.
- Schema sau thay đổi mong đợi ra sao.
- Changeset nào tạo ra thay đổi.
- Điều kiện nào phải đạt trước khi chạy.
- SQL nào sẽ được thực thi trên từng DBMS.
- Cách khôi phục hoặc giới hạn của rollback.
- Công cụ và extension nào cần có để chạy migration.

Tùy biến quá mức làm các câu trả lời trên khó tìm hơn. Ví dụ, một custom change có thể đọc biến môi trường, gọi API ngoài, truy vấn nhiều bảng, tự sinh SQL và cập nhật dữ liệu. Khi đó, chỉ đọc changelog không đủ để hiểu kết quả; phải đọc thêm Java code, cấu hình, dependency, service ngoài và cách triển khai.

Các hệ quả thường gặp:
- Reviewer không nhìn thấy toàn bộ thay đổi trong một diff.
- Local, CI và production sinh SQL khác nhau.
- Một DBMS chạy thành công nhưng DBMS khác không có implementation tương đương.
- Nâng phiên bản Liquibase làm extension không tương thích.
- Rollback không thể tái tạo vì logic tùy biến phụ thuộc trạng thái bên ngoài.
- Khó xác định checksum/history đang đại diện cho nội dung nào.
- Người vận hành phải biết quá nhiều chi tiết nội bộ mới xử lý được sự cố.

Không phải mọi tùy biến đều xấu. SQL đặc thù DBMS hoặc extension có thể là lựa chọn đúng khi change type chuẩn không thể diễn đạt yêu cầu. Điều cần tránh là biến ngoại lệ thành cách làm mặc định.

## 2. Thứ tự ưu tiên khi lựa chọn cách triển khai

Có thể dùng thứ tự quyết định sau:

| Ưu tiên | Cách biểu diễn | Khi nên dùng |
|---|---|---|
| 1 | Change type chuẩn của Liquibase | Thay đổi phổ biến, được hỗ trợ trên DBMS mục tiêu |
| 2 | Thuộc tính chuẩn của change type | Cần cấu hình tên, schema, constraint, default hoặc rollback |
| 3 | Precondition/context/label/dbms | Giới hạn điều kiện hoặc phạm vi thực thi rõ ràng |
| 4 | SQL thuần trong changeset | Cần cú pháp mà change type không diễn đạt được |
| 5 | modifySql hoặc SQL theo DBMS | Cần điều chỉnh hẹp cho một engine cụ thể |
| 6 | Custom change/extension | Có logic tái sử dụng thực sự và được kiểm thử, đóng gói, vận hành |
| 7 | Công cụ migration riêng hoặc job ứng dụng | Logic dữ liệu phức tạp, dài hạn hoặc cần điều phối ngoài một changeset |

Đây là thứ tự ưu tiên để đánh giá, không phải luật cấm. Một câu SQL rõ ràng có thể dễ review hơn một custom extension quá tổng quát. Một job backfill riêng có thể an toàn hơn một changeset cố thực hiện xử lý hàng triệu bản ghi trong startup.

Trước khi chọn phương án phức tạp hơn, hãy ghi rõ change type chuẩn còn thiếu điều gì, vì sao SQL đơn giản không đủ và lợi ích của tùy biến có lớn hơn chi phí vận hành không.

## 3. Ưu tiên change type chuẩn

Change type chuẩn giúp changelog diễn đạt ý định thay vì gắn chặt với cú pháp một DBMS. Các ví dụ thường gặp:

- createTable, dropTable.
- addColumn, dropColumn, renameColumn.
- addPrimaryKey, addForeignKeyConstraint.
- addUniqueConstraint, addNotNullConstraint.
- createIndex, dropIndex.
- insert, update, delete.
- loadData hoặc loadUpdateData.
- createView hoặc thay đổi view theo khả năng hỗ trợ của phiên bản.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-001-add-customer-status"
      author: "team-db"
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: status_code
                  type: VARCHAR(24)
                  constraints:
                    nullable: true
~~~

Ý định thay đổi được thể hiện trực tiếp: thêm một cột nullable vào bảng customer. Liquibase chịu trách nhiệm sinh SQL phù hợp với database đang kết nối.

Change type chuẩn không tự bảo đảm mọi thuộc tính có cùng semantics trên mọi DBMS. Cần kiểm tra tài liệu và generated SQL theo phiên bản Liquibase, JDBC driver và DBMS cụ thể. Nếu một thuộc tính không được hỗ trợ hoặc có hành vi khác, hãy xử lý khác biệt đó có chủ đích.

## 4. Tránh bọc change type chuẩn trong custom change không cần thiết

Một anti-pattern là viết custom Java class chỉ để gọi một thao tác Liquibase vốn đã có change type chuẩn.

Ví dụ, nếu chỉ cần tạo bảng, custom extension không đem lại giá trị đáng kể so với createTable. Nó buộc mọi người:
- Hiểu Java implementation.
- Cài extension đúng phiên bản.
- Đóng gói class vào runtime.
- Kiểm tra classpath ở CLI và Spring Boot.
- Xử lý lỗi và rollback do code tự viết.
- Duy trì test cho một hành vi đã có sẵn.

Custom change chỉ nên được cân nhắc khi cần logic không thể diễn đạt rõ bằng change type, SQL hoặc job dữ liệu thông thường. Nếu custom code chỉ rút ngắn vài dòng YAML nhưng làm tăng dependency và khó kiểm tra, nên giữ cách chuẩn.

## 5. Giữ changeset nhỏ và thể hiện một mục đích

Changeset nên đại diện cho một bước thay đổi có thể review và xác minh. Không nên gom nhiều loại công việc không liên quan vào một changeset lớn.

Ví dụ khó bảo trì:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-100-everything"
      author: "team-db"
      changes:
        - createTable:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: status_code
                  type: VARCHAR(24)
        - sql:
            sql: UPDATE app.customer SET status_code = 'ACTIVE'
        - createIndex:
            schemaName: app
            tableName: customer
            indexName: ix_customer_status
            columns:
              - column:
                  name: status_code
~~~

Ví dụ này gộp tạo bảng, thêm cột, backfill và tạo index. Nếu một bước thất bại, reviewer phải xác định transaction/DDL behavior và trạng thái từng object.

Có thể tách thành:
1. Tạo bảng.
2. Thêm cột hoặc thay đổi schema.
3. Backfill dữ liệu nếu có.
4. Tạo constraint/index sau khi dữ liệu đạt điều kiện.

Không cần tạo một changeset cho mỗi dòng YAML. Ranh giới nên dựa vào mục đích, dependency, khả năng rollback và cách kiểm tra sau khi chạy.

## 6. Khi nào dùng SQL thuần?

SQL thuần là lựa chọn hợp lý khi:
- Change type chuẩn không hỗ trợ cú pháp cần thiết.
- Cần một expression hoặc tính năng DBMS đặc thù.
- Cần tối ưu một thao tác cụ thể sau khi đã đo.
- Cần gọi routine hoặc thực hiện thao tác mà change type không diễn đạt được.

Ví dụ PostgreSQL tạo expression index:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-010-customer-email-lower-index"
      author: "team-db"
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX ix_customer_email_lower
              ON app.customer (lower(email))
      rollback:
        - sql:
            sql: |
              DROP INDEX IF EXISTS app.ix_customer_email_lower
~~~

Đây là SQL đặc thù PostgreSQL. Nếu hệ thống hỗ trợ nhiều DBMS, cần có implementation tương ứng và kiểm tra rằng chúng đáp ứng cùng quy tắc nghiệp vụ. Không chỉ bỏ thuộc tính dbms rồi kỳ vọng các engine khác hiểu cú pháp.

Khi dùng SQL thuần:
- Ghi rõ DBMS và lý do.
- Giới hạn mỗi changeset vào một mục đích.
- Chỉ rõ schema/object.
- Xem xét delimiter, splitStatements và stripComments nếu có nhiều câu lệnh.
- Kiểm tra transaction DDL.
- Khai báo rollback hoặc ghi rõ vì sao không thể đảo ngược.
- Chạy update-sql và integration test trên engine thật.

## 7. Giới hạn SQL đặc thù bằng dbms

Nếu một changeset chỉ áp dụng cho một DBMS, khai báo dbms ở cấp changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-020-postgresql-extension"
      author: "team-db"
      dbms: postgresql
      changes:
        - sql:
            sql: CREATE EXTENSION IF NOT EXISTS pgcrypto
~~~

Cách giới hạn này giúp tránh gửi SQL PostgreSQL tới MySQL hoặc SQL Server. Tuy nhiên, changeset bị filter trên DBMS khác sẽ không tạo ra object tương đương. Nếu các changeset sau cần object đó, phải có nhánh tương ứng hoặc điều kiện phụ thuộc được thiết kế rõ.

Quy tắc:
- Mỗi nhánh DBMS có ID/AUTHOR/FILENAME ổn định.
- SQL riêng chỉ xuất hiện trong changeset giới hạn engine.
- Các nhánh tạo ra cùng hợp đồng schema/data nếu ứng dụng yêu cầu.
- Test xác nhận nhánh đúng được chọn và nhánh khác bị bỏ qua có chủ đích.
- Kiểm tra DATABASECHANGELOG trên từng DBMS.

Không dùng dbms filter để che một migration lỗi trên engine vẫn nằm trong support matrix. Nếu engine không còn được hỗ trợ, thay đổi support policy phải được thực hiện riêng.

## 8. Dùng context và label đúng mục đích

Context và label giúp chọn nhóm changeset theo môi trường hoặc phạm vi release. Chúng không phải công cụ tổng quát để ẩn lỗi hoặc thay thế dbms.

Ví dụ seed chỉ dành cho môi trường phát triển:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-030-dev-demo-customer"
      author: "team-db"
      contextFilter: dev
      changes:
        - insert:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 9001
              - column:
                  name: email
                  value: demo@example.invalid
~~~

Nguyên tắc:
- Context mô tả mục đích/môi trường thực thi.
- Label thường dùng để chọn nhóm release hoặc tính năng.
- dbms giới hạn hệ quản trị.
- Precondition kiểm tra trạng thái database trước khi chạy.

Không tạo nhiều context trùng lặp như dev-local, dev-ci, dev-test nếu chúng không đại diện cho khác biệt thực sự của migration. Cấu hình filter càng phức tạp, nguy cơ một môi trường bỏ sót changeset càng cao.

Mọi pipeline cần dùng filter có thể dự đoán và ghi nhận. Chạy validate/status/update-sql với đúng context/label trước khi update.

## 9. Precondition nên ngắn, rõ và có thể kiểm chứng

Precondition bảo vệ giả định của migration. Ví dụ kiểm tra bảng tồn tại trước khi thêm cột:

~~~yaml
preConditions:
  - onFail: HALT
  - tableExists:
      schemaName: app
      tableName: customer
~~~

Precondition tốt:
- Kiểm tra một giả định cần thiết.
- Dùng change/check có sẵn nếu đáp ứng yêu cầu.
- Trả kết quả dễ hiểu.
- Có hành vi onFail/onError phù hợp.
- Không thực hiện thay đổi dữ liệu.
- Không phụ thuộc dịch vụ ngoài.
- Chạy nhanh và có thể lặp lại.

Tránh precondition:
- Chạy truy vấn toàn bảng lớn trong mỗi lần startup.
- Gọi HTTP/API hoặc filesystem.
- Đọc thời gian hiện tại để quyết định nội dung migration.
- Phụ thuộc biến môi trường không được kiểm soát.
- Có side effect hoặc sửa schema.
- Bắt lỗi rộng rồi coi như điều kiện đạt.

Nếu cần kiểm tra dữ liệu lớn trước khi thêm constraint, có thể chạy bước validation riêng trong pipeline/job dữ liệu. Sau khi kết quả đạt, precondition nhỏ có thể xác nhận điều kiện cuối cùng ngay trước migration.

## 10. Tránh dùng MARK_RAN để che trạng thái không rõ

onFail: MARK_RAN có thể đánh dấu changeset là đã xử lý dù các change không được thực thi. Điều này có thể hữu ích trong một số quy trình baseline được thiết kế rõ, nhưng nguy hiểm nếu dùng để bỏ qua trạng thái database bất ngờ.

Ví dụ không nên dùng MARK_RAN chỉ vì bảng đã tồn tại. Bảng có thể có:
- Kiểu cột khác.
- Constraint thiếu.
- Index không đúng.
- Dữ liệu chưa được backfill.
- Owner/grant khác.
- Schema sai.

Nếu object tồn tại do thao tác ngoài Liquibase, cần đối chiếu cấu trúc thực tế và xác định quy trình baseline/reconcile có phê duyệt. Không dùng MARK_RAN như một cách làm cho pipeline xanh.

## 11. Giới hạn modifySql

modifySql có thể điều chỉnh SQL được sinh ra cho một DBMS hoặc điều kiện cụ thể. Nó hữu ích khi chỉ cần thay đổi nhỏ trong câu SQL mà change type tạo ra.

Ví dụ minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-040-create-audit-table"
      author: "team-db"
      dbms: postgresql
      changes:
        - createTable:
            schemaName: app
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
      modifySql:
        - append:
            value: " TABLESPACE fast_storage"
~~~

Ví dụ chỉ có ý nghĩa nếu cú pháp được sinh ra và vị trí append phù hợp với DBMS/DDL cụ thể. Cần kiểm tra generated SQL; không áp dụng mù quáng.

Giới hạn nên đặt:
- Chỉ dùng khi sửa đổi nhỏ và có thể dự đoán.
- Chỉ rõ DBMS nếu cú pháp phụ thuộc engine.
- Không dùng regex thay thế rộng có thể ảnh hưởng câu SQL ngoài dự kiến.
- Không sửa SQL theo môi trường bằng chuỗi tùy ý.
- Có test so sánh SQL trước/sau.
- Nếu logic modifySql trở nên phức tạp, cân nhắc SQL riêng dễ đọc hơn.

Không dùng modifySql để biến một changeset portable thành một hệ thống template SQL khó hiểu.

## 12. Dùng include tường minh cho changelog quan trọng

Master changelog với include tường minh giúp reviewer thấy thứ tự:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-create-customer-index.yaml
      relativeToChangelogFile: true
~~~

includeAll có thể hữu ích khi thư mục chứa nhiều changelog được quản lý theo quy ước. Tuy nhiên, nó làm thứ tự và tập file được nạp phụ thuộc vào quy tắc quét thư mục, filter và naming. Cần xác minh cách sắp xếp của phiên bản Liquibase đang dùng và không dựa vào thứ tự ngẫu nhiên của filesystem.

Giới hạn includeAll:
- Chỉ dùng trong thư mục có quy ước tên rõ.
- Không trộn changelog release, demo và thử nghiệm.
- Không để file tạm hoặc backup trong thư mục được quét.
- Kiểm tra thứ tự thực tế bằng validate/status/update-sql.
- Có test rằng artifact chỉ chứa đúng changelog mong muốn.

Với migration quan trọng hoặc phụ thuộc thứ tự chặt, include tường minh thường dễ review hơn.

## 13. Parameter substitution phải được kiểm soát

Parameter giúp tái sử dụng changelog, ví dụ schema name:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-050-create-audit"
      author: "team-db"
      changes:
        - createTable:
            schemaName: "${appSchema}"
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Cấu hình cấp parameter phải được quản lý ngoài source theo môi trường. Nhưng parameter cũng có thể làm thay đổi mục tiêu migration.

Quy tắc:
- Chỉ dùng parameter cho giá trị cấu hình thực sự cần thay đổi.
- Tên schema/identifier phải nằm trong allowlist.
- Không dùng parameter cho password/token.
- Không nhận giá trị trực tiếp từ request hoặc người dùng cuối.
- Không ghép SQL động từ input không tin cậy.
- Ghi lại parameter không nhạy cảm trong deployment record.
- Review update-sql sau substitution.
- Test tất cả giá trị hợp lệ được hỗ trợ.

Nếu mọi môi trường đều dùng cùng một schema, đừng tạo parameter chỉ để “linh hoạt”. Mỗi biến cấu hình làm tăng số tổ hợp cần kiểm thử.

## 14. Hạn chế logic phụ thuộc môi trường

Một changelog có thể được triển khai trên development, staging và production. Nội dung changeset nên mô tả thay đổi schema/data có thể tái lập, không tự quyết định hành vi theo trạng thái máy chạy.

Tránh:
- Đọc hostname để chọn schema.
- Dùng thời điểm chạy để tạo tên object.
- Gọi dịch vụ ngoài để quyết định DDL.
- Dùng dữ liệu local chưa được đóng gói.
- Sinh ID changeset hoặc tên bảng ngẫu nhiên.
- Tự phát hiện môi trường bằng cách dò URL tùy tiện.
- Có nhánh logic ẩn mà reviewer không nhìn thấy trong changelog.

Hãy đưa khác biệt môi trường vào cấu hình đã khai báo, context/label được review hoặc deployment orchestration. Mỗi tổ hợp cấu hình phải được kiểm thử và ghi nhận.

## 15. Khi nào custom extension thực sự cần thiết?

Custom extension có thể hợp lý khi:
- Có một change type nghiệp vụ lặp lại nhiều lần.
- Có logic phức tạp mà SQL hoặc change type chuẩn không thể diễn đạt an toàn.
- Cần tích hợp với API Liquibase được hỗ trợ để bổ sung hành vi nhất quán.
- Tổ chức có nhiều dự án dùng chung extension và có owner duy trì.
- Có thể kiểm thử trên toàn bộ DBMS/version mục tiêu.

Ví dụ nhu cầu có thể cân nhắc extension:
- Một change type nội bộ chuẩn hóa cách tạo một loại object đặc thù của sản phẩm.
- Một precondition chuyên biệt kiểm tra metadata mà change type chuẩn không hỗ trợ.
- Một custom generator cho SQL có quy tắc lặp lại, được review và test rộng.

Không nên viết extension chỉ để:
- Bọc một câu CREATE TABLE.
- Thay thế một câu UPDATE đơn giản.
- Đọc một biến môi trường.
- Rút ngắn vài dòng YAML.
- Bỏ qua precondition hoặc checksum.
- Thực hiện một thao tác chỉ dùng đúng một lần.

Trước khi phát triển, so sánh tổng chi phí sở hữu: code, test, release, compatibility, tài liệu, support và cách vận hành.

## 16. Thiết kế ranh giới cho custom change

Nếu custom change là cần thiết, giữ hợp đồng hẹp:
- Input khai báo rõ trong changelog.
- Không đọc cấu hình ẩn ngoài những tham số được khai báo.
- Không gọi mạng hoặc phụ thuộc dịch vụ ngoài khi chạy migration.
- Không tự tạo transaction ngoài cơ chế đã được thiết kế.
- Không sửa DATABASECHANGELOG trực tiếp.
- Không tự quản lý lock.
- Không tự sinh changeset ID.
- Có lỗi rõ ràng khi input không hợp lệ.
- Có rollback hoặc tuyên bố giới hạn không thể rollback.
- Có test cho cả thành công, thất bại và chạy lại.

Một custom change không nên âm thầm thay đổi nhiều object ngoài phạm vi mô tả. Nếu cần thay đổi nhiều bước, cân nhắc chia thành các changeset chuẩn hoặc một job riêng có trạng thái quan sát được.

## 17. Đóng gói và quản lý phiên bản extension

Extension chạy trong môi trường thực thi Liquibase. Nếu extension có trong Spring Boot runtime nhưng thiếu trong CLI migration job, cùng changelog có thể chạy ở ứng dụng nhưng thất bại trong pipeline.

Cần quản lý:
- Artifact extension và version.
- Phiên bản Liquibase API mà extension phụ thuộc.
- Java runtime.
- JDBC driver và DBMS.
- Cấu hình service discovery/extension loading nếu API yêu cầu.
- Dependency transitive.
- Cách extension được đưa vào classpath CLI và Spring Boot.
- Compatibility matrix.
- Quy trình nâng cấp và rollback extension.

Pin phiên bản extension và Liquibase. Không dùng một extension build với API mới trên runner có Liquibase cũ mà không test. Trước khi nâng cấp, chạy test changelog đại diện trên toàn bộ DBMS được hỗ trợ.

Không tải extension từ URL động trong lúc production migration. Artifact cần được kiểm tra, lưu trữ và promote giống application dependency.

## 18. Kiểm thử extension và tùy biến

Một custom extension cần nhiều lớp test:

| Lớp | Kiểm tra |
|---|---|
| Unit test | Validate input, logic chuyển đổi, error handling |
| Serialization/parsing | Changelog khai báo custom property được đọc đúng |
| Generated SQL | SQL sinh ra đúng theo DBMS |
| Integration test | Thực thi trên database thật |
| Rollback test | Hoàn tác hoặc ghi nhận giới hạn |
| Repeatability | Chạy lại không gây side effect ngoài dự kiến |
| Compatibility | Hoạt động với Liquibase/Java/driver version được hỗ trợ |
| Packaging | CLI và Spring Boot đều nạp đúng extension |
| Failure test | Lỗi giữa chừng không để trạng thái mơ hồ |

Test trên H2 không thay thế kiểm thử trên DBMS thật. Nếu extension tạo SQL cho PostgreSQL, MySQL hoặc SQL Server, mỗi engine cần integration test riêng.

Đối với custom precondition, kiểm tra cả true, false và exception khi truy vấn metadata. Đối với custom change, kiểm tra input rỗng, dữ liệu biên, quyền thiếu, timeout và rollback.

## 19. Không đưa logic backfill lớn vào extension tổng quát

Một custom change có thể hấp dẫn vì cho phép đóng gói một vòng lặp dữ liệu. Nhưng backfill lớn cần:
- Batch size.
- Checkpoint/resume.
- Retry và idempotency.
- Throttle.
- Lock và transaction duration.
- Progress metrics.
- Error reporting theo hàng.
- Khả năng dừng và tiếp tục.
- Kiểm tra dữ liệu sau chuyển đổi.

Nếu extension không cung cấp những khả năng này, nó có thể tạo một khối logic khó quan sát trong quá trình migration. Với dữ liệu lớn hoặc logic nghiệp vụ phức tạp, job riêng thường dễ vận hành hơn.

Liquibase vẫn có thể quản lý các mốc schema trước/sau job, ví dụ thêm cột, xác minh điều kiện và thêm constraint sau khi backfill hoàn tất. Trạng thái job cần được ghi nhận bên ngoài theo quy trình có kiểm toán.

## 20. Không dùng precondition để thay thế validation nghiệp vụ phức tạp

Precondition nên kiểm tra điều kiện nhỏ ngay trước migration. Không biến nó thành một chương trình xác minh toàn bộ dữ liệu.

Ví dụ kiểm tra nhanh số hàng còn NULL:

~~~yaml
preConditions:
  - onFail: HALT
  - sqlCheck:
      expectedResult: "0"
      sql: |
        SELECT COUNT(*)
        FROM app.customer
        WHERE status_code IS NULL
~~~

Với bảng lớn, COUNT toàn bảng có thể tốn tài nguyên hoặc giữ thời gian thực thi lâu. Có thể chạy validation job trước và dùng kiểm tra hẹp hơn trong changeset, tùy yêu cầu nhất quán. Cần bảo đảm không có writer tạo dữ liệu sai giữa bước validation và migration.

Không viết custom precondition gọi REST service, đọc file local hoặc kiểm tra trạng thái con người. Những điều kiện đó thuộc pipeline/release gate, không thuộc trạng thái database mà Liquibase nên kiểm tra.

## 21. Giữ rollback dễ hiểu và trung thực

Tùy biến thường làm rollback phức tạp. Một changeset có custom code phải trả lời:
- Rollback có thể tái tạo dữ liệu cũ không?
- Thứ tự hoàn tác có đúng dependency không?
- Có side effect ngoài database không?
- Nếu custom code chạy một phần rồi lỗi thì sao?
- Extension version cũ có thể rollback artifact mới không?
- Có cần chạy job khôi phục riêng?

Không khai báo rollback giả chỉ để đáp ứng hình thức. Nếu thay đổi không thể đảo ngược, ghi rõ giới hạn và phương án forward fix/restore.

Ví dụ addColumn có rollback dropColumn:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-060-add-customer-note"
      author: "team-db"
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: note
                  type: VARCHAR(500)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: customer
            columnName: note
~~~

Rollback này sẽ xóa dữ liệu đã được ghi vào note. Nó chỉ an toàn nếu nghiệp vụ chấp nhận mất dữ liệu hoặc có backup/forward recovery. Độ ngắn của rollback không đồng nghĩa độ an toàn.

## 22. Giữ changeset bất biến và quản lý checksum

Sau khi changeset đã chạy ở bất kỳ môi trường dùng chung nào, không sửa nội dung để thay đổi hành vi. Liquibase lưu checksum trong DATABASECHANGELOG; thay đổi nội dung có thể làm validation báo mismatch.

Tùy biến không được dùng để né quy tắc bất biến:
- Không thay đổi custom extension implementation rồi giả định changeset cũ vẫn mang cùng semantics.
- Không thay đổi parameter mặc định khiến cùng artifact tạo schema khác mà không ghi nhận.
- Không đổi logical path/ID/AUTHOR tùy tiện.
- Không dùng clear-checksums để che source drift.
- Không dùng validCheckSum thay cho review migration.

Nếu logic cần thay đổi, tạo changeset mới hoặc version extension mới với migration/release được kiểm thử. Artifact và dependency cần được pin để lịch sử có thể giải thích.

## 23. Kiểm soát includeAll, naming và discovery

includeAll có thể làm việc thêm file vào thư mục tự động trở thành một phần changelog. Đây là tiện ích nhưng cũng là một nguồn thay đổi ẩn.

Giới hạn:
- Thư mục chỉ chứa changelog đã sẵn sàng triển khai.
- Quy tắc tên và thứ tự được tài liệu hóa.
- Không chứa file backup, draft hoặc thử nghiệm.
- Có review khi thêm/xóa file.
- CI xác nhận danh sách changeset được nạp.
- Không dựa vào thứ tự filesystem không được bảo đảm.
- Có thể dùng include tường minh cho các bước phụ thuộc chặt.

Không di chuyển changelog đã triển khai nếu chưa hiểu tác động tới FILENAME và identity. Nếu cần thay đổi logical path, phải dùng cơ chế phù hợp phiên bản và kiểm tra history trước/sau.

## 24. Tránh SQL động và identifier không được kiểm soát

SQL động có thể tạo ra nhiều câu lệnh khác nhau từ cùng một changelog. Điều này làm review khó và tăng nguy cơ injection hoặc tác động sai schema.

Không:
- Ghép tên bảng từ input người dùng.
- Đưa giá trị request vào parameter substitution.
- Dùng biến môi trường tự do để tạo câu SQL.
- Tự động quét toàn bộ schema rồi sửa mọi object tìm thấy.
- Chạy SQL từ file tải xuống không được xác minh.
- Sinh tên changeset/object ngẫu nhiên.

Nếu cần identifier thay đổi theo môi trường, dùng allowlist và kiểm tra generated SQL. Nếu cần xử lý nhiều tenant/schema, cân nhắc một cơ chế provisioning có hợp đồng rõ và audit riêng thay vì làm changelog tùy biến khó kiểm soát.

## 25. Tiêu chí đánh giá một tùy biến

Trước khi chấp nhận, trả lời các câu hỏi:

| Câu hỏi | Dấu hiệu có thể chấp nhận |
|---|---|
| Change type chuẩn có đáp ứng không? | Đã thử và ghi rõ giới hạn |
| SQL thuần có đủ không? | SQL ngắn, giới hạn DBMS và dễ review |
| Tùy biến có tái sử dụng không? | Có nhiều use case thật, không phải abstraction sớm |
| Có deterministic không? | Cùng artifact/config tạo cùng ý định thay đổi |
| Có kiểm thử không? | Unit, generated SQL và integration test |
| Có rollback/recovery không? | Hành vi được chứng minh hoặc giới hạn được ghi rõ |
| Có owner không? | Có nhóm chịu trách nhiệm và thời gian hỗ trợ |
| Có version compatibility không? | Liquibase/Java/DBMS matrix rõ |
| Có observability không? | Log, metric, error và progress có thể truy xuất |
| Có làm reviewer hiểu khó hơn không? | Lợi ích lớn hơn chi phí đọc và vận hành |

Nếu không có owner, test hoặc quy trình nâng cấp, custom extension trở thành dependency không được quản lý. Không nên đưa nó vào production chỉ vì chạy được trên máy phát triển.

## 26. Ví dụ cấu trúc changelog dễ bảo trì

Một cách tổ chức có thể dùng:

~~~text
db/changelog/
  db.changelog-master.yaml
  schema/
    001-create-reference-tables.yaml
    002-create-customer.yaml
  changes/
    20261120-add-customer-status.yaml
    20261121-create-customer-index.yaml
  dbms/
    postgresql/
      20261122-customer-expression-index.yaml
    mysql/
      20261122-customer-normalized-index.yaml
  data/
    payment-status.csv
~~~

Master changelog include rõ thứ tự:

~~~yaml
databaseChangeLog:
  - include:
      file: schema/001-create-reference-tables.yaml
      relativeToChangelogFile: true
  - include:
      file: schema/002-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/20261120-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/20261121-create-customer-index.yaml
      relativeToChangelogFile: true
  - include:
      file: dbms/postgresql/20261122-customer-expression-index.yaml
      relativeToChangelogFile: true
  - include:
      file: dbms/mysql/20261122-customer-normalized-index.yaml
      relativeToChangelogFile: true
~~~

Trong thực tế, mỗi changeset DBMS-specific cần dbms filter hoặc cách giới hạn phù hợp để chỉ engine đúng thực thi. Cấu trúc thư mục chỉ là cách tổ chức, không tự động giới hạn DBMS.

Không chia thư mục quá sâu đến mức khó tìm changeset. Tổ chức theo mục đích và dependency, giữ master changelog dễ đọc.

## 27. Quy trình review tùy biến trong CI/CD

Một pipeline có thể áp dụng các cổng:

1. Kiểm tra YAML/XML/JSON changelog parse được.
2. Chạy liquibase validate.
3. Kiểm tra include và dependency.
4. Chạy test trên DBMS/version hỗ trợ.
5. Sinh update-sql cho từng engine và filter.
6. Review SQL đặc thù và modifySql.
7. Kiểm tra extension/dependency version.
8. Chạy integration migration trên database cô lập.
9. Kiểm tra rollback hoặc forward recovery.
10. Lưu artifact digest, SQL preview và kết quả test.
11. Chỉ promote artifact đã được phê duyệt.

Ví dụ command minh họa:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Các command phải chạy với changelog, URL, driver, context/label và parameters đúng môi trường. Không dùng output PostgreSQL thay cho SQL của SQL Server hoặc MySQL.

Pipeline nên fail nếu extension thiếu, version không tương thích, custom change không được nạp hoặc một DBMS trong support matrix không chạy được.

## 28. Chẩn đoán tùy biến quá mức

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| CLI chạy, Spring Boot không chạy | Extension có trong classpath một môi trường nhưng thiếu ở môi trường kia | So sánh dependency/runtime classpath |
| Một DBMS lỗi khi parse | SQL hoặc extension không hỗ trợ engine | Kiểm tra dbms filter và compatibility matrix |
| SQL khác giữa local và CI | Parameter/profile/filter không giống | Ghi cấu hình hiệu lực và review update-sql |
| includeAll nạp thêm file lạ | Thư mục discovery chứa draft/backup | Tách thư mục và kiểm soát file |
| Checksum mismatch sau sửa extension | Source changeset hoặc semantics đã đổi | Giữ changeset bất biến, thêm version/migration mới |
| Precondition chạy lâu | Truy vấn nặng hoặc gọi logic ngoài | Chuyển validation sang job riêng |
| Rollback không khôi phục dữ liệu | Custom change có side effect hoặc thiếu inverse | Thiết kế forward fix/backup và ghi giới hạn |
| Không biết SQL nào đã chạy | Log tùy biến thiếu changeset identity | Gắn deployment ID và đối chiếu DB history |
| Extension lỗi sau nâng Liquibase | API/Java compatibility thay đổi | Pin version, chạy compatibility test trước nâng cấp |
| Tùy biến chỉ hoạt động ở local | Phụ thuộc file, biến môi trường hoặc package local | Kiểm thử từ artifact đóng gói |
| Nhiều thay đổi ngầm trong một changeset | Custom code thực hiện quá nhiều công việc | Chia nhỏ changeset/job và làm rõ mục đích |
| Một môi trường bỏ sót object | Filter dbms/context/label sai | Kiểm tra status và schema trên từng môi trường |

Khi điều tra, luôn thu thập changelog artifact, extension version, generated SQL, log và DATABASECHANGELOG. Không sửa history hoặc tắt precondition trước khi xác định nguyên nhân.

## 29. Bài thực hành: đơn giản hóa một migration tùy biến

**Bối cảnh:** dự án có custom change tên CreateCustomerTableHelper. Extension này chỉ tạo bảng customer, thêm primary key và cột email. Changelog còn có modifySql theo môi trường và một precondition gọi truy vấn toàn bảng.

### Phần A — Đánh giá

1. Đọc hợp đồng custom change và xác định mọi side effect.
2. Kiểm tra change type chuẩn có thể thay thế không.
3. Kiểm tra SQL sinh ra theo từng DBMS.
4. Xác định precondition có thật sự cần truy vấn dữ liệu lớn không.
5. Kiểm tra modifySql có thể bỏ hoặc giới hạn hẹp hơn không.
6. Xác định extension đang được đóng gói ở CLI và Spring Boot ra sao.

### Phần B — Thiết kế lại

1. Dùng createTable cho bảng và cột.
2. Khai báo primary key bằng thuộc tính chuẩn.
3. Dùng precondition tableExists/columnExists nếu cần bảo vệ giả định.
4. Tách SQL DBMS-specific thành changeset có dbms filter.
5. Chuyển validation dữ liệu nặng sang job trước migration.
6. Giữ changeset cũ bất biến; dùng changeset mới nếu đã triển khai.

### Phần C — Kiểm thử

1. Chạy validate.
2. Sinh update-sql cho từng DBMS.
3. Chạy fresh install trên database cô lập.
4. Chạy upgrade từ release trước.
5. Xác minh schema/data.
6. Chạy test rollback hoặc forward recovery.
7. Chạy từ artifact đóng gói, không chỉ từ IDE.
8. So sánh log và DATABASECHANGELOG.

### Phần D — Quyết định giữ extension hay loại bỏ

Chỉ giữ extension nếu logic còn lại thật sự không thể diễn đạt rõ bằng change type, SQL hoặc job riêng; có owner; có test; có version compatibility và có hướng dẫn vận hành. Nếu không, loại bỏ bằng một thay đổi có kiểm soát ở release mới.

### Câu hỏi tự kiểm tra

- Vì sao change type chuẩn thường dễ bảo trì hơn custom change? **Vì semantics được chuẩn hóa, ít code riêng và dễ review hơn.**
- SQL thuần có luôn là lựa chọn xấu không? **Không.** SQL ngắn, giới hạn DBMS và được test có thể rõ hơn extension.
- Khi nào dùng dbms filter? **Khi toàn bộ changeset chỉ dành cho một DBMS cụ thể.**
- Context có thay thế dbms không? **Không.** Context mô tả mục đích/phạm vi, còn dbms nhận diện engine.
- Có nên dùng precondition để quét dữ liệu lớn? **Không mặc định.** Dùng validation/job riêng khi kiểm tra tốn kém.
- Vì sao includeAll cần quy ước chặt? **Vì thêm file vào thư mục có thể thay đổi tập changeset được nạp.**
- Custom extension cần kiểm thử gì? **Parsing, generated SQL, integration, rollback, failure, packaging và compatibility.**
- Có thể sửa changeset cũ khi thay implementation extension không? **Không nên.** Giữ lịch sử bất biến và thêm migration mới khi cần.

## 30. Checklist giới hạn tùy biến

**Thiết kế**
- [ ] Đã xem xét change type chuẩn trước khi viết SQL/custom code.
- [ ] Mỗi changeset có một mục đích rõ và phạm vi thay đổi hẹp.
- [ ] SQL riêng có dbms filter và lý do được ghi nhận.
- [ ] Context, label và precondition dùng đúng mục đích.
- [ ] includeAll có thư mục và naming convention được kiểm soát.
- [ ] Parameter chỉ dùng cho cấu hình cần thiết, có allowlist.
- [ ] Không phụ thuộc thời gian, hostname, input người dùng hoặc dịch vụ ngoài.

**Custom extension**
- [ ] Có use case tái sử dụng thực sự.
- [ ] Có owner chịu trách nhiệm.
- [ ] Input/side effect được mô tả rõ.
- [ ] Không sửa DATABASECHANGELOG hoặc tự quản lý lock.
- [ ] Có error handling và rollback/recovery.
- [ ] Có test unit, parsing, generated SQL và DBMS thật.
- [ ] Có compatibility matrix Liquibase/Java/DBMS.
- [ ] Extension được pin, đóng gói và promote cùng artifact.
- [ ] CLI và Spring Boot đều nạp đúng phiên bản.

**Kiểm thử và vận hành**
- [ ] validate/status/update-sql chạy với đúng cấu hình.
- [ ] Có fresh install và upgrade test.
- [ ] Có rollback/forward fix test.
- [ ] Log có deployment ID và changeset identity.
- [ ] Không log secret hoặc dữ liệu nhạy cảm.
- [ ] Có hướng dẫn khi extension thiếu hoặc không tương thích.
- [ ] Có kế hoạch nâng cấp và loại bỏ tùy biến không còn cần.
- [ ] Changeset đã triển khai được giữ bất biến.

**Kết luận:** giới hạn tùy biến giúp changelog vẫn là tài liệu có thể đọc, review và tái lập. Hãy ưu tiên change type chuẩn; dùng SQL hoặc modifySql cho khác biệt hẹp và có kiểm thử; giới hạn precondition, context, label, include và parameter; chỉ xây custom extension khi có lợi ích tái sử dụng rõ, owner và compatibility matrix. Khi mỗi thay đổi có phạm vi nhỏ, SQL dự kiến kiểm tra được, rollback trung thực và artifact được pin, Liquibase có thể mở rộng theo nhu cầu dự án mà không biến migration thành một hệ thống khó hiểu và khó vận hành.
