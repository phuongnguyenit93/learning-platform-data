
# Khai báo rollback tự động và rollback tường minh trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý sự tiến hóa schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi một bản phát hành gặp sự cố, nhóm thường đặt câu hỏi: **Có thể đưa database quay lại trạng thái trước migration hay không?** Liquibase cung cấp hai cách khai báo thao tác hoàn tác: **rollback tự động (automatic rollback)** khi change type có thể sinh bước đảo ngược phù hợp; và **rollback tường minh (explicit/custom rollback)** do người viết changelog chủ động định nghĩa.

Bài thuộc chương **Hoàn tác** này đi sâu vào điều kiện sử dụng hai hình thức rollback, cú pháp YAML/XML/formatted SQL, mối quan hệ với DATABASECHANGELOG, thứ tự hoàn tác, giới hạn của DDL và dữ liệu, cũng như kiểm chứng trên PostgreSQL, MySQL, SQL Server, Oracle hoặc DBMS khác. Nội dung liên hệ trực tiếp với thực hành migration có kiểm chứng, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Mục tiêu sau bài học: phân biệt rollback tự động với tường minh; biết khi nào Liquibase không thể tự khôi phục dữ liệu; viết và thử rollback theo changeset; hiểu tag, count, date và bản SQL preview; xây dựng kế hoạch giảm rủi ro khi rollback production.

## 1. Rollback là gì, và không phải là gì?

**Rollback Liquibase** là một hoạt động chủ động đưa lịch sử migration lùi về một mốc bằng cách thực hiện các thay đổi đảo ngược tương ứng, trong phạm vi công cụ và database hỗ trợ. Mốc đó có thể được chỉ định bằng tag, số lượng changeset hoặc thời điểm.

Rollback **không đồng nghĩa** với ba khái niệm khác:

- **Transaction rollback của DBMS:** hoàn tác các thay đổi thuộc một transaction chưa commit hoặc bị lỗi, tùy khả năng DBMS. Nó diễn ra ở mức giao dịch.
- **Restore từ backup/PITR:** khôi phục toàn bộ hoặc một phần dữ liệu từ snapshot, backup hay transaction log; có thể khôi phục dữ liệu mà một lệnh rollback DDL không biết.
- **Đưa ứng dụng về phiên bản cũ:** thay đổi mã ứng dụng hoặc artifact, không tự động thay đổi database. Code cũ phải tương thích với schema còn tồn tại.

Ví dụ, migration tạo thêm cột optional có thể hỗ trợ phiên bản ứng dụng cũ lẫn mới. Nếu cần quay lại code cũ, **không nhất thiết** phải xóa ngay cột đó. Ngược lại, migration đã xóa cột chứa dữ liệu có thể không thể khôi phục nội dung chỉ bằng cách tạo lại cột.

**Nguyên tắc nền tảng:** rollback thành công về mặt công cụ chưa đủ để chứng minh dữ liệu, ràng buộc và ứng dụng đã trở về trạng thái nghiệp vụ đúng.

## 2. Một changeset và hai loại khai báo hoàn tác

Changelog thường chứa các changeset theo trình tự phụ thuộc:

~~~text
001 — Tạo bảng customer
002 — Thêm cột customer.status
003 — Backfill status từ dữ liệu cũ
004 — Thêm constraint NOT NULL
~~~

Khi update, Liquibase xét và thực thi changeset theo thứ tự changelog, bỏ qua những changeset đã được ghi nhận theo quy tắc thông thường.

Khi rollback về một mốc cũ hơn, Liquibase thường xử lý các changeset thuộc phạm vi cần hoàn tác theo **thứ tự ngược lại** để xử lý phụ thuộc: 004 → 003 → 002 → 001, nếu cả bốn đều nằm trong phạm vi và có cách hoàn tác khả dụng.

Có hai nguồn tạo thao tác đảo ngược:

1. **Rollback tự động:** Liquibase biết cách sinh thay đổi ngược cho một change type và DBMS được hỗ trợ. Ví dụ, createTable có thể có thao tác đảo ngược tương ứng là dropTable.
2. **Rollback tường minh:** người viết khai báo block rollback hoặc câu SQL rollback để công cụ sử dụng. Đây là yêu cầu quan trọng với SQL tùy chỉnh và nhiều data migration.

Một changeset có thể chứa nhiều change. Nếu một phần cần rollback riêng, phải kiểm tra toàn bộ phạm vi của changeset, không suy luận rằng Liquibase sẽ tự phục hồi phần còn lại theo ý nghĩa nghiệp vụ.

## 3. Rollback tự động: Liquibase sinh thao tác đảo ngược

**Automatic rollback** dựa trên khả năng mà Liquibase hỗ trợ cho từng change type và DBMS. Một ví dụ đơn giản:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: schema-team
      comment: Tạo bảng khách hàng phục vụ ứng dụng.
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

Changeset không khai báo block rollback. Đối với các DBMS hỗ trợ, Liquibase có thể tạo thao tác **dropTable** như một cách hoàn tác createTable.

Nhưng đây không phải bảo đảm an toàn dữ liệu: nếu bảng customer được ứng dụng ghi dữ liệu sau migration, dropTable sẽ xóa dữ liệu đó. **Có khả năng sinh SQL đảo ngược không có nghĩa có khả năng lấy lại dữ liệu nghiệp vụ.**

Vì vậy, trước khi sử dụng automatic rollback, cần trả lời:

- Change type này có được Liquibase hỗ trợ tự rollback trên DBMS/phiên bản đang chạy không?
- SQL đảo ngược được sinh ra là gì?
- Nó có xóa dữ liệu hoặc đối tượng được tạo sau migration không?
- Các changeset sau có thêm khóa ngoại, index hoặc phụ thuộc khác vào đối tượng này không?
- Có kế hoạch khôi phục dữ liệu hoặc rollback ứng dụng tương ứng không?

## 4. Ma trận change type: khi nào có thể tự rollback?

Bảng dưới mô tả những trường hợp **điển hình**, không phải cam kết trên mọi DBMS/phiên bản. Cần xác minh bằng tài liệu change type của phiên bản đang dùng và sinh SQL rollback trên đúng database.

| Change type | Khả năng rollback tự động điển hình | Điều cần lưu ý |
|---|---|---|
| **createTable** | Thường có, đảo ngược bằng dropTable | Xóa bảng có thể làm mất mọi dữ liệu được tạo sau đó |
| **addColumn** | Thường có, đảo ngược bằng dropColumn | Xóa cột làm mất dữ liệu đã ghi vào cột |
| **createIndex** | Thường có, đảo ngược bằng dropIndex | Ảnh hưởng hiệu năng và các truy vấn đang chạy |
| **renameTable / renameColumn** | Có thể được hỗ trợ | Phải kiểm tra tên, phụ thuộc và trạng thái ứng dụng |
| **dropTable / dropColumn** | Thường không thể tự khôi phục đầy đủ | Dữ liệu và đặc tính đối tượng cũ không còn sẵn |
| **insert** | Không nên kỳ vọng tự rollback | Cần xác định chính xác hàng mới, khóa và dữ liệu phụ thuộc |
| **update** | Không tự biết giá trị trước của mỗi hàng | Cần snapshot hoặc biến đổi ngược có chứng cứ |
| **delete** | Không tự biết dữ liệu đã bị xóa | Phải có backup/snapshot hoặc SQL phục hồi dữ liệu gốc |
| **sql / sqlFile** | Không tự suy ra SQL đảo ngược an toàn | Thường cần rollback tường minh |
| **createProcedure / createView** | Phụ thuộc change type và DBMS | Cần kiểm tra hỗ trợ replace và định nghĩa trước đó |

Đừng kết luận từ tên change type rằng rollback chắc chắn khả dụng. Liquibase hỗ trợ nhiều phiên bản, edition, database extension và biến thể change; hành vi cần được **kiểm chứng trên môi trường mục tiêu**.

Đặc biệt, tự sinh dropTable/dropColumn đúng cú pháp nhưng vẫn có thể là **rollback phá hủy**. Đây là lý do automatic rollback phù hợp nhất khi cấu trúc còn ở giai đoạn thử nghiệm hoặc đã có chính sách dữ liệu tương ứng.

## 5. Cú pháp rollback tường minh trong YAML

Một changeset tạo bảng có thể chủ động khai báo rollback bằng change type:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-create-order-note
      author: order-team
      comment: Thêm bảng ghi chú đơn hàng.
      changes:
        - createTable:
            tableName: order_note
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: note
                  type: varchar(500)
      rollback:
        - dropTable:
            tableName: order_note
~~~

Trong ví dụ, rollback được khai báo rõ thay vì để Liquibase tự suy ra. Lợi ích là reviewer dễ nhìn thấy hành động hoàn tác và thảo luận tác động. Tuy nhiên, block rollback ở đây vẫn **drop bảng**, tức mất dữ liệu nếu bảng đã chứa ghi chú.

Rollback tường minh có thể chứa nhiều change type, ví dụ xóa index trước rồi xóa bảng. Thứ tự bên trong block rollback cần được thiết kế để đáp ứng các ràng buộc đối tượng tại thời điểm thực hiện.

Một block rollback không được thiết kế chính xác có thể còn nguy hiểm hơn automatic rollback. Việc “có block rollback” chỉ cho biết đã khai báo một cách xử lý, không chứng minh nó tương đương trạng thái trước migration.

## 6. YAML: rollback đảo ngược addColumn

Giả sử cột status mới được thêm để hỗ trợ phiên bản ứng dụng kế tiếp:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-add-customer-status
      author: customer-team
      comment: Mở rộng bảng customer với trạng thái tạm thời nullable.
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(20)
                  constraints:
                    nullable: true
      rollback:
        - dropColumn:
            tableName: customer
            columnName: status
~~~

Rollback tường minh mô tả rõ thao tác **dropColumn**. Khi dùng automatic rollback cho addColumn trên một DBMS được hỗ trợ, Liquibase cũng có thể sinh thao tác tương tự. Nhưng hai cách đều làm mất giá trị status được ghi sau khi thêm cột.

Một kế hoạch production có thể an toàn hơn là **giữ cột mới khi rollback ứng dụng**, miễn phiên bản cũ tương thích và không phụ thuộc ràng buộc đã bị thay đổi. Nếu thật sự cần xóa cột, phải đánh giá dữ liệu, backup và các service đang dùng cột đó trước khi thực hiện.

## 7. Rollback tường minh cho update: phải biết dữ liệu cũ

Ví dụ migration chuẩn hóa dữ liệu:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-normalize-customer-status
      author: customer-team
      comment: Chuyển trạng thái PENDING_OLD thành PENDING.
      changes:
        - update:
            tableName: customer
            columns:
              - column:
                  name: status
                  value: PENDING
            where: "status = 'PENDING_OLD'"
      rollback:
        - update:
            tableName: customer
            columns:
              - column:
                  name: status
                  value: PENDING_OLD
            where: "status = 'PENDING'"
~~~

**Chú ý: đây là ví dụ minh họa cách khai báo, không phải rollback an toàn để dùng nguyên xi.** Nếu bảng đã có khách hàng status=PENDING hợp lệ từ trước, hoặc ứng dụng ghi PENDING sau khi migration, rollback sẽ vô tình đổi những hàng không thuộc tập dữ liệu đã chuyển.

Để rollback dữ liệu chính xác, cần một cơ chế xác định **những hàng đã bị migration thay đổi** và **giá trị ban đầu**. Các lựa chọn có thể gồm:

1. Lưu bản sao các cột cần khôi phục cùng khóa định danh trước khi update.
2. Dùng bảng hỗ trợ migration chứa change-id, primary key và giá trị trước.
3. Tạm giữ cột hoặc trạng thái cũ trong giai đoạn chuyển tiếp.
4. Có backup/PITR để phục hồi một cách có kiểm soát.
5. Nếu không thể khôi phục an toàn, ưu tiên **forward fix** bằng changeset mới.

Đặc biệt với dữ liệu nghiệp vụ, không nên tuyên bố rollback đơn giản như gán mọi hàng PENDING về giá trị cũ. Sự thay đổi dữ liệu sau thời điểm migration khiến “SQL đảo ngược” không còn đồng nghĩa “khôi phục lịch sử”.

## 8. Rollback cho insert: tránh xóa dữ liệu phát sinh sau migration

Một insert tham chiếu có thể có rollback tường minh:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 005-insert-vip-type
      author: customer-team
      changes:
        - insert:
            tableName: customer_type
            columns:
              - column:
                  name: code
                  value: VIP
              - column:
                  name: display_name
                  value: Khách hàng ưu tiên
      rollback:
        - delete:
            tableName: customer_type
            where: "code = 'VIP'"
~~~

Rollback này chỉ tương đối đơn giản nếu code VIP **chưa tồn tại trước migration**, là khóa duy nhất và chưa có bảng nào tham chiếu tới nó sau đó. Nếu khách hàng đã được gán loại VIP, thao tác delete có thể:

- Bị từ chối do foreign key.
- Kích hoạt cascade và gây xóa ngoài mong muốn.
- Để lại dữ liệu tham chiếu không hợp lệ nếu ràng buộc thiếu.
- Gây lỗi cho phiên bản ứng dụng còn dùng mã VIP.

Vì vậy, với master/reference data, rollback có thể cần một **kế hoạch deprecate/disable** thay vì hard delete. Việc giữ lại một bản ghi danh mục không được ứng dụng cũ sử dụng thường ít nguy hiểm hơn xóa dữ liệu đã trở thành một phần nghiệp vụ.

## 9. Rollback cho delete: không thể tự sinh lại hàng đã mất

Giả sử changeset xóa những bản ghi khách hàng không hợp lệ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 006-delete-obsolete-entries
      author: customer-team
      changes:
        - delete:
            tableName: customer_type
            where: "code = 'LEGACY_UNUSED'"
~~~

Sau khi delete, Liquibase không thể tự biết những bản ghi đã xóa có description, created_at, owner hoặc cột khác là gì. Nếu xóa liên quan khóa ngoại, trigger hay cascade, tập dữ liệu mất có thể còn lớn hơn dự kiến.

Một rollback tường minh chỉ có thể tái tạo chính xác khi **dữ liệu gốc đã được lưu** hoặc thao tác có các giá trị cố định đã biết và được xác minh. Nếu không, cần backup hoặc một quy trình khôi phục chuyên dụng.

**Không dùng insert cứng một hàng mặc định làm rollback cho delete nhiều hàng**. Nó có thể tạo dữ liệu mới giống bề ngoài nhưng không phục hồi khóa, thông tin audit hoặc mối quan hệ nghiệp vụ.

## 10. Rollback của SQL viết tay

Nếu một changeset dùng change type **sql**, Liquibase không thể tự suy ra ý định của mã SQL tùy ý.

Ví dụ PostgreSQL tạo một view tùy chỉnh:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 007-create-active-customer-view
      author: reporting-team
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE VIEW v_active_customer AS
              SELECT id, email
              FROM customer
              WHERE status = 'ACTIVE';
      rollback:
        - sql:
            sql: DROP VIEW IF EXISTS v_active_customer;
~~~

Ở đây rollback tường minh là một đoạn SQL. Cần kiểm tra cú pháp theo DBMS, quyền thực thi và các đối tượng phụ thuộc.

Nếu view **đã tồn tại trước migration** và changeset thay thế định nghĩa của nó, dropView không khôi phục được định nghĩa trước. Muốn rollback chính xác, phải giữ lại nội dung định nghĩa cũ để tạo lại.

Với function, procedure, trigger hoặc SQL nhiều statement, cần lưu ý **splitStatements, endDelimiter, executor JDBC/native và runInTransaction**. Cấu hình phù hợp cho forward SQL không nhất thiết phù hợp với rollback SQL; phải kiểm thử cả hai chiều.

## 11. Rollback bằng sqlFile: quản lý script riêng

Khi rollback dài hoặc chứa SQL đặc thù DBMS, có thể lưu kịch bản đảo ngược trong tệp SQL và tham chiếu bằng **sqlFile** trong rollback.

Giả sử cấu trúc:

~~~text
db/changelog/
  db.changelog-master.yaml
  changes/
    008-create-reporting-view.yaml
  scripts/
    008-create-reporting-view.sql
    008-drop-reporting-view.sql
~~~

Changeset trong changes/008-create-reporting-view.yaml:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 008-reporting-view
      author: reporting-team
      dbms: postgresql
      changes:
        - sqlFile:
            path: ../scripts/008-create-reporting-view.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
      rollback:
        - sqlFile:
            path: ../scripts/008-drop-reporting-view.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
~~~

Nội dung script forward có thể tạo view, còn script rollback có thể drop view. Mọi tệp được tham chiếu phải được **đóng gói trong artifact** và có thể được Liquibase tìm thấy khi chạy từ CLI, Maven/Gradle plugin hoặc classpath Spring Boot.

Lưu ý: hai script cần **được review như một cặp**, giữ nguyên sau khi changeset đã triển khai, và cùng tương thích DBMS/phiên bản đang dùng. Việc đổi path hoặc thay script có thể tác động định danh, checksum và tính tái lập lịch sử.

## 12. Rollback tường minh trong XML

Đối với XML changelog, phần rollback nằm bên trong changeSet:

~~~xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="009-add-customer-note" author="customer-team">
        <comment>Thêm cột ghi chú tạm cho khách hàng.</comment>
        <addColumn tableName="customer">
            <column name="note" type="varchar(500)"/>
        </addColumn>
        <rollback>
            <dropColumn tableName="customer" columnName="note"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

Ý nghĩa không đổi so với YAML: changes xác định thao tác tiến, rollback mô tả thao tác đảo ngược. Phải validate XML bằng XSD phù hợp với phiên bản Liquibase và extension đang dùng.

Không nên copy một rollback XML đã kiểm tra trên DBMS A sang DBMS B rồi mặc định kết quả giống nhau. Các thay đổi liên quan index, schema, kiểu dữ liệu hoặc constraint có thể có khả năng rollback khác nhau.

## 13. Rollback trong formatted SQL changelog

Formatted SQL dùng các marker đặc biệt:

~~~sql
--liquibase formatted sql

--changeset reporting-team:010-create-customer-email-index dbms:postgresql
--comment: Tạo index phục vụ tra cứu email.
CREATE INDEX idx_customer_email
ON customer (email);

--rollback DROP INDEX IF EXISTS idx_customer_email;
~~~

**--rollback** là chỉ thị trong formatted SQL. Nó không phải là SQL được thực thi trong lần update thông thường; Liquibase dùng nội dung đó khi rollback changeset thuộc phạm vi được chọn.

Với rollback có nhiều câu lệnh hoặc định nghĩa procedure/function, cần kiểm tra cú pháp khai báo nhiều dòng, delimiter và việc tách SQL theo phiên bản đang dùng. Không mặc định hai dấu chấm phẩy hay các lệnh client như GO, DELIMITER, slash sẽ được hiểu giống nhau giữa JDBC và native executor.

**Không trộn formatted SQL của Liquibase với tệp SQL thường** rồi cho rằng các dòng --rollback sẽ tự động được công cụ nhận diện nếu tệp không được parse ở định dạng formatted SQL.

## 14. Trường hợp không nên cố viết rollback phá hủy

Không phải migration nào cũng có một thao tác đảo ngược an toàn. Ví dụ:

- Xóa một cột đã chứa dữ liệu nhiều năm.
- Hợp nhất hai tài khoản thành một bản ghi duy nhất mà không lưu mapping.
- Chuẩn hóa email thành chữ thường trong hệ thống có yêu cầu giữ nguyên ký tự gốc.
- Xóa hàng theo chính sách bảo mật hoặc thời hạn lưu trữ.
- Thay đổi khóa chính hoặc định danh được hệ thống khác tham chiếu.
- Sửa dữ liệu đồng thời với ứng dụng đang ghi vào cùng bảng.

Khi **không thể** tạo rollback đáng tin cậy, tài liệu migration cần nêu rõ:

1. Vì sao rollback tự động không phù hợp.
2. Những thông tin nào sẽ mất nếu thực hiện SQL đảo ngược đơn giản.
3. Phương án **forward fix** hoặc phục hồi từ backup/PITR.
4. Mốc trước migration cần kiểm tra và lưu lại.
5. Quy trình phê duyệt và điều kiện dừng triển khai.
6. Cách chuyển ứng dụng về phiên bản tương thích nếu một phần migration đã commit.

Không nên bịa một rollback tường minh chỉ để pipeline có “lệnh rollback”. Một rollback sai còn có thể gây thiệt hại lớn hơn việc giữ schema ở trạng thái mở rộng và triển khai bản sửa tiếp.

## 15. Preview rollback SQL trước khi thực thi

Liquibase hỗ trợ các lệnh xem SQL dự kiến tương ứng với chiến lược rollback, tùy phiên bản CLI hoặc build plugin. Những tên thường gặp:

~~~text
liquibase rollback-sql --tag=before-release
liquibase rollback-count-sql --count=2
liquibase rollback-to-date-sql --date="2026-11-19 12:00:00"
~~~

Các lệnh trên chỉ **minh họa tên lệnh và dạng tham số**; cần kiểm tra format ngày, timezone, thứ tự option và quy tắc tag của phiên bản đang dùng. Chúng phải chạy trên đúng database/schema, cùng changelog revision và bộ lọc cần thiết để kết quả có ý nghĩa.

Preview SQL giúp phát hiện:

- DROP TABLE/DROP COLUMN ngoài phạm vi dự định.
- Câu DELETE hoặc UPDATE có WHERE quá rộng.
- Rollback thiếu cho changeset có SQL tùy chỉnh.
- Thứ tự xóa index/constraint trước bảng liên quan.
- SQL không phù hợp DBMS hoặc cấu hình executor.
- Những thay đổi không thể khôi phục dữ liệu chỉ bằng DDL.

**Preview không thay thế chạy thử.** Một câu SQL có cú pháp hợp lệ vẫn có thể thất bại do khóa ngoại, lock, quyền, dữ liệu production hoặc transaction.

## 16. Rollback theo tag, count và date

Ba cách chọn mốc thường gặp:

| Cơ chế | Ý nghĩa | Nguy cơ thường gặp |
|---|---|---|
| **rollback tới tag** | Đưa database về mốc được gắn tag trong lịch sử | Tag đặt sai database/release hoặc phạm vi changeset khác kỳ vọng |
| **rollback-count** | Hoàn tác số lượng changeset được chỉ định theo lịch sử | Đếm changeset, không đếm file, SQL statement hoặc phút triển khai |
| **rollback-to-date** | Hoàn tác các changeset nằm sau mốc thời gian theo quy tắc của Liquibase | Khác timezone, clock hoặc chọn nhầm thời điểm |

Ví dụ minh họa lệnh **thực thi** — không chạy trên production chỉ để thử:

~~~text
liquibase rollback --tag=before-release
liquibase rollback-count --count=2
liquibase rollback-to-date --date="2026-11-19 12:00:00"
~~~

Dù chọn cách nào, hãy lấy thông tin từ **DATABASECHANGELOG của đúng database**, không chỉ suy ra từ tên release. Một release có thể gồm nhiều changeset, và một changeset có thể chứa nhiều SQL statement.

**Tag không phải backup.** Nó là một mốc logic trong lịch sử Liquibase. Khi cần phục hồi giá trị dữ liệu bị xóa, việc tồn tại tag không tự tạo ra một bản dữ liệu cũ để khôi phục.

## 17. Tag trong changelog và tag bằng lệnh

Có thể gắn mốc thông qua cơ chế tag của Liquibase hoặc một change type trong changelog như **tagDatabase**, tùy thiết kế phát hành.

Ví dụ changeset đánh dấu mốc:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 011-tag-release-2026-11
      author: release-team
      changes:
        - tagDatabase:
            tag: release-2026-11-before-upgrade
~~~

Ngoài ra, có các lệnh CLI để gắn tag cho trạng thái lịch sử đang có. Hai cách có cơ chế ghi nhận khác nhau theo phiên bản và cách sử dụng; cần kiểm chứng mốc nào Liquibase chọn khi rollback.

Điểm cần xác nhận trước production:

- Tag có thật ở **database đích** hay chỉ tồn tại trong một tệp?
- Tag có tên duy nhất, đúng release và được ghi trong hồ sơ triển khai?
- Những changeset nào được rollback khi chọn tag đó?
- Tag changeset có nằm trong phạm vi rollback theo quy tắc phiên bản không?
- Có người xác nhận danh sách changeset và SQL preview không?

Dùng cùng một tên tag ở hai database không chứng minh hai database đang ở cùng trạng thái dữ liệu. Mỗi môi trường có lịch sử và dữ liệu độc lập.

## 18. DATABASECHANGELOG thay đổi thế nào khi rollback?

Trong lần update, Liquibase ghi nhận changeset đã thực thi hoặc được đánh dấu theo một cơ chế nhất định vào **DATABASECHANGELOG**. Khi rollback thành công một changeset thuộc phạm vi chọn, Liquibase thường điều chỉnh lịch sử để changeset đó **không còn được xem là đã áp dụng** theo cơ chế rollback thông thường.

Có thể kiểm tra:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Những điểm cần hiểu:

- Lịch sử không đồng nghĩa với snapshot schema. Row đã bị loại khỏi lịch sử không tự chứng minh dữ liệu được khôi phục.
- Rollback có thể **thất bại một phần** tùy DBMS, transaction và cấu hình; phải kiểm tra schema/data thật.
- Nếu đã rollback thành công và chạy update lại với cùng changelog, changeset có thể được xem là pending và được thực thi lại, theo điều kiện của lần chạy.
- Những changeset dùng runAlways, runOnChange hoặc được MARK_RAN cần đánh giá riêng; không suy luận mọi row có cùng hành vi.
- Không sửa thẳng DATABASECHANGELOG để giả lập rollback vì điều đó không thực thi thay đổi schema/dữ liệu.

Có thể dùng log migration, bảng history và kiểm tra database để xây dựng bằng chứng hậu rollback. **Chỉ nhìn exit code hoặc số row trong lịch sử là chưa đủ.**

## 19. MARK_RAN và rollback: rủi ro xóa đối tượng có sẵn

Một trường hợp nguy hiểm là changeset dùng precondition **onFail: MARK_RAN** để ghi nhận bảng đã tồn tại từ trước:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 012-customer-baseline
      author: schema-team
      preConditions:
        - onFail: MARK_RAN
        - not:
            - tableExists:
                tableName: customer
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
      rollback:
        - dropTable:
            tableName: customer
~~~

Nếu bảng customer đã tồn tại, Liquibase có thể ghi MARK_RAN **mà không thực thi createTable**. Nhưng rollback được khai báo lại là dropTable. Nếu thao tác rollback đó được áp dụng, nó có thể xóa **bảng có sẵn** thuộc hệ thống trước khi Liquibase quản lý.

Vì vậy, trước khi rollback một phạm vi có changeset MARK_RAN:

1. Tìm những row EXECTYPE=MARK_RAN liên quan.
2. Xác định trạng thái/schema đã tồn tại trước migration.
3. Kiểm tra chính xác SQL rollback dự kiến theo phiên bản đang dùng.
4. Xác định đối tượng rollback có thực sự do changeset tạo không.
5. Nếu là đối tượng legacy, **không tự động chạy dropTable/dropColumn**.
6. Chọn chiến lược baseline, forward fix hoặc phục hồi phù hợp.

**Precondition dùng cho update không phải điều kiện bảo vệ tự động cho mọi thao tác rollback.** Phải thiết kế rollback riêng và thử trên database có lịch sử thực tế.

## 20. runInTransaction, autocommit và rollback một phần

Liquibase có thuộc tính changeset **runInTransaction** nhằm điều khiển việc cố gắng thực thi trong transaction khi DBMS hỗ trợ. Khả năng rollback thực tế vẫn phụ thuộc DBMS và tính chất câu SQL.

| Trường hợp | Điều có thể xảy ra |
|---|---|
| DML trong transaction được DBMS hỗ trợ | Một lỗi có thể khiến toàn bộ transaction bị rollback |
| DDL có implicit commit | Đối tượng có thể đã thay đổi dù transaction được dự tính |
| runInTransaction: false | Các lệnh có thể tạo tác động từng phần nếu lỗi giữa chừng |
| Một changeset chứa nhiều change | Phần thành công và phần lỗi cần kiểm tra lại theo transaction thật |
| Rollback chạy nhiều DDL/DML | Chính rollback cũng có thể thất bại giữa chừng |
| SQL đặc thù DBMS như concurrent index | Cần chính sách transaction và phục hồi riêng |

Do đó, rollback Liquibase **không phải một giao dịch toàn năng** có thể đưa mọi DBMS về đúng trạng thái trước release bằng một lệnh.

Trước một lệnh rollback phá hủy, cần có backup hoặc cách phục hồi dữ liệu, hạn chế các session ứng dụng ghi đồng thời và hiểu lock/timeout. Với hệ thống production, thử rollback trên bản sao có kích thước và dữ liệu đại diện thường quan trọng hơn một bài test trên database trống.

## 21. Rollback nhiều changeset phải tôn trọng phụ thuộc

Ví dụ migration theo thứ tự:

~~~text
001 — createTable customer
002 — createTable purchase_order
003 — addForeignKey purchase_order.customer_id -> customer.id
004 — insert customer reference data
005 — addColumn purchase_order.status
~~~

Nếu rollback toàn bộ, thứ tự ngược về mặt phụ thuộc thường yêu cầu:

~~~text
005 — remove status
004 — remove data nếu an toàn
003 — drop foreign key
002 — drop purchase_order
001 — drop customer
~~~

Nếu rollback chỉ một changeset ở giữa trong khi các changeset mới hơn vẫn còn phụ thuộc vào nó, có thể tạo schema không nhất quán. Những lệnh rollback thông thường theo mốc của Liquibase xử lý **một đoạn lịch sử** thay vì chọn ngẫu nhiên một change tùy ý; cần hiểu phạm vi mốc trước khi dùng.

Với dữ liệu tham chiếu, nếu các bảng giao dịch đã sử dụng mã dữ liệu từ changeset 004, rollback data bằng DELETE có thể bị chặn hoặc gây mất mát. Khi đó nên giữ lại dữ liệu và chỉ rollback ứng dụng, hoặc chọn forward fix. Không ép SQL bằng cách tắt foreign key tùy tiện.

## 22. Rollback ứng dụng và rollback database: phối hợp thế nào?

Giả sử release R2 thêm một cột mới và code mới đã ghi vào cột đó. Phát hiện lỗi logic ở R2, nhóm muốn trở lại R1.

Hai hướng:

**Hướng A — Chỉ rollback code:** triển khai lại R1, giữ schema mở rộng nếu R1 vẫn hoạt động. Ưu điểm là không mất dữ liệu mới; nhược điểm là phải xác nhận code R1 tương thích với schema và ràng buộc hiện hành.

**Hướng B — Rollback code và database:** hoàn tác các changeset thuộc R2. Chỉ phù hợp khi đã xác minh dữ liệu, constraint, mốc release và SQL rollback an toàn; nếu R2 đã ghi dữ liệu mới, rollback schema có thể gây mất dữ liệu.

Đó là lý do chiến lược **expand–migrate–contract** thường an toàn hơn thay đổi phá vỡ trong một lần phát hành:

1. Expand: thêm cấu trúc mới còn tương thích.
2. Migrate: chuyển dữ liệu và triển khai code theo giai đoạn.
3. Contract: chỉ xóa cấu trúc cũ sau khi hết nhu cầu tương thích.

Với mô hình này, một lỗi code có thể được xử lý bằng rolling back ứng dụng hoặc forward fix, không bắt buộc rollback DDL phá hủy.

## 23. Spring Boot và pipeline: chọn một chủ thể rollback

Một ứng dụng Spring Boot có thể tự chạy migration khi khởi động:

~~~yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Auto-configuration Spring Boot thường phục vụ **update** changelog, không có nghĩa ứng dụng tự rollback database khi code deploy lỗi. Rollback cần một tác vụ vận hành có kế hoạch và được phê duyệt riêng.

Trong CI/CD có thể dùng Liquibase CLI, Maven hoặc Gradle plugin tùy dự án. Khi migration/rollback là một job độc lập, có thể tắt Liquibase auto-run ở runtime theo mô hình triển khai của tổ chức. Cần xác định **một migration owner** cho từng database và mỗi lần phát hành.

Trước lệnh rollback cần xác minh:

- Chính xác database và schema đích, thông tin kết nối được bảo mật.
- Revision changelog có đầy đủ rollback cần thiết.
- Phiên bản Liquibase/driver, DBMS và executor tương ứng.
- Mốc tag/count/date đã được review.
- Không có migration job hoặc replica khác đang cố update cùng lúc.
- Có kế hoạch khóa, timeout và tác động ứng dụng.
- Đã preview SQL và có người duyệt.
- Có backup/restore nếu thao tác đảo ngược không thể khôi phục dữ liệu.

**DATABASECHANGELOGLOCK** giúp điều phối các tiến trình Liquibase dùng chung bảng khóa, nhưng không loại trừ mọi DDL thủ công, lock DBMS hay vấn đề ứng dụng ghi đồng thời.

## 24. Quy trình kiểm chứng rollback trước production

Một workflow an toàn:

**Bước 1 — Xác định điểm xuất phát:** ghi revision ứng dụng, phiên bản Liquibase, DBMS, schema, snapshot cấu trúc và số lượng/tình trạng dữ liệu quan trọng.

**Bước 2 — Xác nhận phạm vi:** dùng DATABASECHANGELOG để biết changeset nào đã chạy; xác định tag/count/date; liệt kê chính xác các changeset nằm trong phạm vi rollback.

**Bước 3 — Kiểm tra khả năng rollback:** đánh giá change type nào tự sinh rollback, change nào có block rollback và change nào chưa có kịch bản an toàn.

**Bước 4 — Sinh SQL preview:** dùng lệnh rollback-*sql tương ứng. Review DROP, UPDATE, DELETE, schema, tên đối tượng, điều kiện WHERE và thứ tự phụ thuộc.

**Bước 5 — Tạo bản sao có lịch sử thật:** ưu tiên clone/snapshot database đã có dữ liệu đại diện, cùng DBMS/phiên bản/cấu hình. Bảo vệ PII trong môi trường test.

**Bước 6 — Thử rollback:** thực thi trên bản sao, kiểm tra exit code, log, schema, khóa, dữ liệu và lịch sử sau rollback.

**Bước 7 — Thử update trở lại:** nếu quy trình rollback rồi reapply là kịch bản dự kiến, chạy lại migration trên bản sao và xem có duplicate key, checksum, dữ liệu lệch hay không.

**Bước 8 — Kiểm tra ứng dụng:** test phiên bản ứng dụng sẽ chạy sau rollback; xác nhận các query và constraint tương thích.

**Bước 9 — Chuẩn bị khôi phục:** backup/PITR, ngưỡng dừng, người phê duyệt, chủ thể vận hành và thời gian bảo trì phù hợp.

**Bước 10 — Triển khai và hậu kiểm:** thực thi có giám sát, xác minh DATABASECHANGELOG/schema/dữ liệu, lưu release record và báo cáo sự cố.

Một lần validate thành công hoặc preview rollback SQL không chứng minh rằng dữ liệu production sẽ phục hồi đúng. **Thử trên database có lịch sử và dữ liệu thật được ẩn danh hoặc mô phỏng** là bước không thể bỏ qua đối với rollback quan trọng.

## 25. Phân biệt rollback test, rollback production và forward fix

| Phương án | Mục tiêu | Khi thích hợp | Rủi ro |
|---|---|---|---|
| **Rollback test** | Kiểm chứng định nghĩa rollback trước phát hành | Trong CI/test database disposable | Nếu test quá đơn giản sẽ bỏ qua lỗi trên dữ liệu thật |
| **Rollback production** | Hoàn tác một nhóm migration trên database thật | Có phạm vi/mốc rõ, backup và bằng chứng dữ liệu an toàn | Có thể xóa dữ liệu, giữ lock lâu, làm code và schema lệch |
| **Forward fix** | Tạo changeset mới để sửa trạng thái hiện tại | Dữ liệu đã phát sinh, thao tác phá hủy không đảo ngược được | Cần thiết kế thêm migration và kiểm tra tác động |
| **Restore/PITR** | Khôi phục dữ liệu từ bản sao hoặc transaction log | Dữ liệu bị phá hủy, không thể tái tạo bằng SQL | Có thể mất những giao dịch hợp lệ sau điểm khôi phục |
| **Rollback ứng dụng không rollback DB** | Giảm tác động lỗi code khi schema vẫn tương thích | Với schema mở rộng, backward compatibility tốt | Phải test code cũ với schema mới |

Không có quy tắc “rollback luôn tốt hơn forward fix”. Với schema production có nhiều dữ liệu mới và nhiều service dùng chung, **forward fix** có thể ít phá hủy hơn. Với migration vừa chạy trên database chưa được ứng dụng sử dụng, rollback DDL tự động có thể phù hợp hơn.

Quyết định phụ thuộc thời điểm, độ rộng tác động, khả năng tái tạo dữ liệu, DBMS và mức độ tương thích các phiên bản ứng dụng.

## 26. Lỗi thường gặp khi khai báo rollback

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Lệnh rollback báo không thể tự rollback change | Change type/DBMS không hỗ trợ automatic rollback | Khai báo rollback tường minh hoặc thiết kế forward fix/restore |
| DROP COLUMN thành công nhưng mất dữ liệu mới | Auto rollback chỉ đảo ngược schema, không phục hồi giá trị | Không dùng dropColumn nếu dữ liệu chưa được lưu; chuẩn bị backup |
| Rollback UPDATE đổi sai tập hàng | WHERE không phân biệt dữ liệu cũ và dữ liệu được ghi sau migration | Lưu snapshot/tập khóa thay đổi hoặc dùng forward fix |
| Rollback insert xóa bản ghi đã được tham chiếu | Mã tham chiếu bắt đầu được ứng dụng sử dụng | Chọn disable/deprecate, kiểm tra foreign key và dữ liệu |
| Rollback delete không phục hồi bản ghi | Không lưu dữ liệu trước delete | Restore từ bản sao/snapshot đã kiểm chứng |
| Rollback sai mốc | Tag/count/date không khớp release thật | Kiểm tra DATABASECHANGELOG và preview danh sách changeset |
| Rollback SQL khác giữa local và production | DBMS/driver/executor hoặc revision khác nhau | Ghim version và kiểm thử trên DBMS đích |
| Rollback vướng lock/timeout | DDL/DML cần khóa đối tượng đang được ứng dụng sử dụng | Quan sát DBMS sessions, bố trí maintenance hoặc chuyển chiến lược |
| Chạy rollback xong update lại lỗi | SQL đảo ngược để lại trạng thái khác baseline hoặc dữ liệu mới xung đột | Thử vòng rollback–reapply và sửa thiết kế |
| Có rollback block nhưng schema vẫn sai | Block chỉ hoàn tác một phần hoặc thiếu phụ thuộc | Review toàn changeset và trạng thái thực sau rollback |
| MARK_RAN baseline rồi rollback đòi xóa bảng cũ | Changeset được đánh dấu nhưng không tạo bảng | Kiểm tra EXECTYPE và loại bỏ kế hoạch rollback phá hủy không hợp lệ |
| Chỉnh changeset cũ làm checksum mismatch | Đã sửa nội dung triển khai | Tạo changeset mới; không sửa lịch sử để né lỗi |
| Pipeline rollback thất bại giữa chừng | DDL autocommit/runInTransaction false hoặc quyền không đủ | Điều tra những gì đã áp dụng; dùng recovery runbook |
| Spring Boot phiên bản cũ không chạy sau rollback | Schema/data không tương thích với code cũ | Kiểm thử cặp version ứng dụng–database trước khi thao tác |

Các lỗi trên cần được phân loại theo **rollback SQL**, **trạng thái database**, **lịch sử Liquibase** và **khả năng tương thích ứng dụng**. Đừng dùng việc xóa row DATABASECHANGELOG hoặc clearCheckSums để thay thế phục hồi dữ liệu.

## 27. Bài thực hành: automatic rollback và explicit rollback

Thực hành trên **database disposable**, không dùng production.

### Bước 1 — Tạo bảng bằng change type có thể tự rollback

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-001-create-category
      author: lab-team
      changes:
        - createTable:
            tableName: demo_category
            columns:
              - column:
                  name: code
                  type: varchar(30)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: label
                  type: varchar(100)
                  constraints:
                    nullable: false
~~~

Không có block rollback. Trên DBMS được Liquibase hỗ trợ, kiểm tra preview rollback xem công cụ dự kiến sinh dropTable nào. **Chưa tạo dữ liệu cần giữ** trong bảng ở bài thử này.

### Bước 2 — Thêm dữ liệu với rollback tường minh

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-002-insert-category
      author: lab-team
      changes:
        - insert:
            tableName: demo_category
            columns:
              - column:
                  name: code
                  value: NORMAL
              - column:
                  name: label
                  value: Bình thường
      rollback:
        - delete:
            tableName: demo_category
            where: "code = 'NORMAL'"
~~~

Ở bước này, rollback tường minh chỉ phù hợp vì dữ liệu NORMAL là dữ liệu giả được tạo trong database thử và chưa có bảng phụ thuộc.

### Bước 3 — Đặt một mốc rollback

Sau khi 001 và 002 chạy thành công trên database thử nghiệm, gắn một tag test đã được ghi nhận vào lịch sử hoặc dùng mốc count có thể kiểm tra. Nếu dự định kiểm thử rollback-count, ghi rõ rằng mỗi **changeset** được đếm một lần, không tính từng column hay từng SQL statement.

### Bước 4 — Thêm một changeset mới

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-003-add-category-active
      author: lab-team
      changes:
        - addColumn:
            tableName: demo_category
            columns:
              - column:
                  name: active
                  type: boolean
~~~

Trên DBMS hỗ trợ, addColumn có thể được tự rollback bằng dropColumn.

### Bước 5 — Preview và thử rollback changeset mới nhất

Chạy validate, xem status, tạo SQL preview và thực thi update cho database thử nghiệm. Sau đó sinh rollback-count-sql với count=1, kiểm tra SQL dự kiến chỉ xử lý changeset 003. Nếu phù hợp, chạy rollback-count 1 trên database disposable rồi xác nhận cột active không còn tồn tại.

### Bước 6 — Thử rollback thêm changeset dữ liệu

Nếu muốn hoàn tác tiếp changeset 002, xác nhận rollback tường minh sẽ xóa đúng code NORMAL và không có dữ liệu phụ thuộc. Thử trên database mới hoặc snapshot đã lưu, sau đó đối chiếu DATABASECHANGELOG và tập bản ghi.

### Bước 7 — Kiểm tra rollback–reapply

Chạy update lại với changelog ban đầu. Xác nhận changeset đã bị rollback được xem xét chạy lại, bảng và dữ liệu được tạo đúng dự kiến. Ghi nhận sự khác biệt giữa **thao tác tạo DDL được tự rollback** và **dữ liệu cần rollback tường minh**.

### Bước 8 — Thử tình huống không an toàn

Trên database thử riêng, sau khi chạy 002, tạo bản ghi khác phụ thuộc vào code NORMAL hoặc sửa label bằng ứng dụng giả lập. Quan sát rằng rollback delete có thể bị chặn hoặc làm mất thay đổi phát sinh sau migration. Kết luận: rollback được khai báo đúng cú pháp chưa chắc đúng về nghiệp vụ.

## 28. Checklist trước khi phát hành changeset có rollback

- [ ] Đã biết change type nào có automatic rollback trên **đúng DBMS/phiên bản**.
- [ ] Các change type không tự rollback được có kịch bản tường minh hoặc kế hoạch phục hồi khác.
- [ ] Rollback đã được review cùng forward change, không để đến lúc sự cố mới viết.
- [ ] Có phân biệt transaction rollback, Liquibase rollback, restore và rollback ứng dụng.
- [ ] Tất cả DROP TABLE/COLUMN và DELETE đã được đánh giá tác động dữ liệu.
- [ ] Rollback UPDATE có chứng cứ xác định đúng hàng và giá trị trước thay đổi.
- [ ] Rollback INSERT không xóa dữ liệu đã được ứng dụng khác tham chiếu.
- [ ] SQL/script rollback được đóng gói trong artifact và dùng đường dẫn ổn định.
- [ ] DBMS, dialect, quyền, delimiter và executor phù hợp với môi trường thật.
- [ ] Đã xác minh scope rollback theo tag/count/date và số changeset dự kiến.
- [ ] Đã sinh và review rollback SQL, không chỉ review forward SQL.
- [ ] Đã thử rollback trên DBMS thật, bản sao có schema/dữ liệu đại diện.
- [ ] Đã thử rollback–reapply khi đó là kịch bản vận hành có thể xảy ra.
- [ ] Đã đối chiếu DATABASECHANGELOG, EXECTYPE và trạng thái đối tượng sau rollback.
- [ ] Đã xem xét changeset MARK_RAN hoặc baseline trước khi xóa đối tượng.
- [ ] Đã đánh giá transaction, DDL autocommit, lock và thời gian thực thi.
- [ ] Không chỉnh sửa changeset đã phát hành để né checksum.
- [ ] Có backup/PITR hoặc phương án forward fix khi đảo ngược không an toàn.
- [ ] CI/CD có người phê duyệt, một migration owner và cơ chế dừng rollout.
- [ ] Phiên bản ứng dụng sau rollback đã được kiểm tra với schema/data tương ứng.
- [ ] Có hậu kiểm và release record nêu mốc, revision, kết quả và rủi ro còn lại.

**Ghi nhớ:** **rollback tự động** giúp Liquibase sinh thao tác đảo ngược cho một số change type và DBMS; **rollback tường minh** cho phép người phát triển khai báo cụ thể thay đổi cần hoàn tác, nhất là với SQL viết tay hoặc dữ liệu. Cả hai đều không phải là backup và không tự bảo đảm khôi phục giá trị đã mất. Rollback đáng tin cậy phải có phạm vi rõ ràng, preview SQL, kiểm thử trên database có lịch sử thực, hiểu transaction/lock, có phương án phục hồi dữ liệu và được điều phối thống nhất với Spring Boot hoặc CI/CD.

