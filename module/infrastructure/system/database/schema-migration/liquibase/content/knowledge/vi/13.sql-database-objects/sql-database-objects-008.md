# Khai báo quyền truy cập và đối tượng hỗ trợ bằng SQL

## 1. Mục tiêu và bối cảnh

Liquibase không chỉ dùng để tạo bảng, thêm cột hoặc thiết lập khóa ngoại. Một lần phát hành cơ sở dữ liệu còn có thể cần **cấp quyền cho tài khoản ứng dụng**, cập nhật quyền truy cập sau khi tạo bảng mới, khai báo **schema**, **sequence**, **view**, **function**, **extension**, **index** hay những đối tượng hỗ trợ khác. Nhiều thao tác trong số này phụ thuộc sâu vào cú pháp và mô hình bảo mật của từng hệ quản trị, nên **SQL trực tiếp** trong changelog Liquibase là một lựa chọn thực tế.

Tuy nhiên, câu lệnh **GRANT**, **REVOKE**, **CREATE OR REPLACE**, **ALTER DEFAULT PRIVILEGES** hoặc **DROP** không chỉ là những đoạn SQL kỹ thuật. Chúng quyết định ai có thể đọc dữ liệu, ai được chỉnh sửa cấu trúc, đối tượng nào có thể được gọi và cơ chế nào còn hoạt động sau khi rollback. Một migration sai có thể cấp quyền quá rộng hoặc làm gián đoạn hệ thống dù mọi changeset đều có trạng thái thành công.

Bài học thuộc chương **SQL và đối tượng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trọng tâm bài là **khai báo quyền truy cập và các đối tượng hỗ trợ bằng SQL có phiên bản hóa**, từ đó đưa các thay đổi bảo mật và hạ tầng database vào cùng quy trình triển khai có thể kiểm chứng.

Sau bài này, bạn cần:

1. Giải thích sự khác nhau giữa user, role, object owner, quyền truy cập và quyền sở hữu.
2. Viết changeset Liquibase để cấp hoặc thu hồi các quyền cần thiết trên schema, bảng, sequence, view và function.
3. Lựa chọn giữa **sql**, **sqlFile**, change type có cấu trúc và formatted SQL changelog.
4. Hiểu các điểm đặc thù của PostgreSQL như **PUBLIC**, quyền **USAGE** trên schema, quyền sequence và **ALTER DEFAULT PRIVILEGES**.
5. Định nghĩa và cập nhật đối tượng hỗ trợ theo thứ tự phụ thuộc, có rollback và kiểm tra sau triển khai.
6. Nhận diện rủi ro cấp quyền quá mức, quyền kế thừa, SQL động, chạy nhầm môi trường và thay đổi đối tượng dùng chung.
7. Tích hợp kiểm tra quyền và đối tượng vào quy trình dev/test/production và CI/CD.

Các ví dụ thực thi chủ yếu dùng **PostgreSQL**; không được sao chép nguyên lệnh GRANT hoặc cú pháp tạo function sang MySQL, SQL Server, Oracle mà không kiểm tra lại.

## 2. Tại sao nên quản lý GRANT và đối tượng hỗ trợ cùng migration?

Hãy hình dung ứng dụng vừa được bổ sung bảng **app.orders**. Liquibase tạo bảng thành công, nhưng tài khoản **app_runtime** không có quyền SELECT hoặc INSERT, khiến ứng dụng nhận lỗi permission denied ngay sau phát hành.

Một nhóm có thể sửa thủ công bằng cách đăng nhập database với tài khoản quản trị rồi GRANT quyền. Cách này giải quyết sự cố trước mắt nhưng tạo ra các vấn đề:

- Quyền đã được cấp không nằm trong changelog, nên dev/test khó tái tạo đúng production.
- Không có mã nguồn giải thích **vì sao** quyền được cấp và ai phê duyệt.
- Khó biết khi nào phải thu hồi quyền sau khi ứng dụng ngừng sử dụng đối tượng.
- Việc khôi phục hoặc dựng lại database dễ thiếu quyền cần thiết.
- Một người có thể cấp quyền quá rộng để xử lý lỗi nhanh, làm mất nguyên tắc tối thiểu quyền.
- Kiểm thử tự động có thể thành công nhờ quyền quản trị ở test nhưng thất bại với quyền hạn chế ở production.

Đưa thay đổi quyền vào Liquibase tạo ra một **kế hoạch triển khai phiên bản hóa**: tạo đối tượng, cấp quyền, kiểm tra quyền, triển khai ứng dụng và thu hồi quyền cũ khi đã an toàn. Tuy vậy, changelog không thay thế hệ thống quản lý danh tính, chính sách IAM, quản trị tài khoản hoặc quy trình cấp quyền DBA. Một số role và secret vẫn nên được cung cấp từ hạ tầng bên ngoài.

## 3. Hiểu đúng user, role, owner và privilege

Trong PostgreSQL, **role** là thực thể dùng để quản lý quyền và có thể có thuộc tính LOGIN để đóng vai trò tài khoản kết nối. Role có thể được cấp quyền trực tiếp hoặc kế thừa quyền qua membership của role khác, tùy cấu hình. Những hệ quản trị khác có mô hình user/role riêng.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Login role | Danh tính kết nối đến database | svc_orders |
| Group/privilege role | Tập hợp quyền được gán cho nhiều tài khoản | app_reader, app_writer |
| Object owner | Chủ sở hữu đối tượng, thường có khả năng ALTER/DROP và quản lý grant theo DBMS | migration_owner |
| Object privilege | Quyền cụ thể như SELECT, INSERT, UPDATE, DELETE, USAGE hoặc EXECUTE | SELECT ON app.orders |
| Role membership | Quan hệ một role là thành viên của role khác | svc_orders là thành viên app_writer |
| PUBLIC | Nhóm quyền đặc biệt bao gồm các role theo mô hình PostgreSQL | EXECUTE mặc định trên function mới |

Sự khác biệt cốt lõi: **có quyền SELECT không có nghĩa sở hữu bảng; là chủ sở hữu bảng không đồng nghĩa được đăng nhập từ mọi nơi; và đúng username không chứng minh kết nối trỏ đúng database**.

Một mô hình thực tế có thể tách:

- **migration_owner**: sở hữu schema và đối tượng, chạy các thao tác DDL hoặc ủy quyền DDL qua cơ chế phù hợp.
- **app_reader**: chỉ đọc các bảng hoặc view được phép.
- **app_writer**: được đọc/ghi những bảng nghiệp vụ cần thiết, không mặc nhiên được ALTER/DROP.
- **svc_orders**: tài khoản ứng dụng được cấp membership phù hợp thông qua quy trình quản trị role.

**Không dùng tài khoản superuser cho migration thường ngày** nếu một role quyền hạn chế là đủ. Bản thân việc cấp membership hoặc tạo login role có thể đòi hỏi quyền cao hơn; hãy giao đúng hệ thống quản lý danh tính/database hoặc job bootstrap riêng.

## 4. Các đối tượng hỗ trợ và quyền thường liên quan

| Đối tượng | Vai trò | Thay đổi SQL thường gặp | Điểm cần chú ý |
|---|---|---|---|
| Schema | Không gian tên tổ chức các đối tượng | CREATE SCHEMA, GRANT USAGE | Quyền truy cập schema khác quyền trên từng bảng |
| Table | Lưu dữ liệu nghiệp vụ | GRANT SELECT/INSERT/UPDATE/DELETE | Không cấp ALL PRIVILEGES chỉ để xử lý lỗi một truy vấn |
| Sequence | Cấp phát giá trị tăng dần, có thể dùng với serial/nextval | CREATE SEQUENCE, GRANT USAGE | Quyền sequence tách khỏi quyền trên bảng |
| View | Cung cấp truy vấn được đặt tên | CREATE OR REPLACE VIEW, GRANT SELECT | Quyền trên view và quyền trên bảng nguồn có quy tắc riêng |
| Function | Đóng gói phép tính hoặc thao tác database | CREATE OR REPLACE FUNCTION, GRANT EXECUTE | Tránh cấp EXECUTE rộng; xem xét SECURITY DEFINER |
| Procedure | Chương trình có thể CALL | CREATE PROCEDURE, GRANT EXECUTE | Cú pháp và giao dịch tùy DBMS |
| Index | Hỗ trợ hiệu năng và một số ràng buộc | CREATE INDEX, DROP INDEX | Có thể khóa bảng, chiếm dung lượng; không phải role privilege độc lập như bảng |
| Trigger | Thực thi logic khi có sự kiện DML/DDL | CREATE TRIGGER, DROP TRIGGER | Phụ thuộc function, bảng và quyền của creator |
| Extension | Bổ sung kiểu dữ liệu, function hoặc khả năng DBMS | CREATE EXTENSION | Có thể cần quyền đặc biệt và tác động toàn database |
| Type/synonym | Định nghĩa kiểu, alias hoặc hợp đồng SQL đặc thù | CREATE TYPE, CREATE SYNONYM | Không phải DBMS nào cũng hỗ trợ cùng cú pháp |

Khái niệm “đối tượng hỗ trợ” không có nghĩa luôn phải tạo tất cả bằng SQL thô. Nếu Liquibase có change type phù hợp như createTable, createIndex hoặc createView, change type có cấu trúc thường tăng tính khả chuyển và giúp nhìn rõ ý định. **Dùng SQL trực tiếp** khi cần đặc tính DBMS, câu lệnh GRANT/REVOKE hoặc khả năng mà change type được chọn không diễn đạt đầy đủ.

## 5. Nguyên tắc thiết kế quyền: tối thiểu, có phạm vi và có chủ sở hữu

Trước khi viết GRANT, hãy trả lời:

1. **Ai cần quyền?** Một role nghiệp vụ ổn định hay một user riêng lẻ?
2. **Cần thao tác gì?** Chỉ SELECT, hay cần INSERT/UPDATE/DELETE, EXECUTE, USAGE?
3. **Trên đối tượng nào?** Một bảng, một view, một schema hay cả database?
4. **Ai cấp quyền?** Owner hoặc role có GRANT OPTION, không phải mọi tài khoản kết nối.
5. **Quyền có nên áp dụng cho đối tượng tương lai không?** Nếu có, phải quản lý default privileges theo DBMS.
6. **Khi nào thu hồi?** Xác định thời điểm ứng dụng ngừng cần quyền, tránh xóa quyền đang phục vụ production.
7. **Làm sao kiểm chứng?** Truy vấn metadata/quyền hiệu lực và kiểm thử bằng role runtime thật.

Ví dụ, ứng dụng chỉ cần đọc báo cáo không nên được cấp **CREATE ON SCHEMA app** hoặc **DELETE ON ALL TABLES IN SCHEMA app**. Một dashboard chỉ đọc view nên được cấp SELECT trên view phù hợp thay vì SELECT trên mọi bảng chứa dữ liệu cá nhân.

Cũng cần phân biệt **quyền trực tiếp** với **quyền hiệu lực**. Một REVOKE trực tiếp có thể không chặn truy cập nếu role vẫn nhận quyền qua membership hoặc PUBLIC. Kiểm tra bảo mật phải xem toàn bộ đường cấp quyền.

## 6. Bối cảnh ví dụ PostgreSQL thống nhất

Giả sử nhóm vận hành có:

- Database học tập **shop_lab**.
- Schema **app**, đã tồn tại.
- Bảng **app.orders** có các cột order_id, status, total_amount, created_at.
- Hai role **app_reader** và **app_writer**, được hạ tầng hoặc DBA tạo trước.
- Tài khoản chạy Liquibase có quyền cần thiết để cấp quyền trên đối tượng, thông thường là owner hoặc role có GRANT OPTION phù hợp.
- Tài khoản ứng dụng được quản lý ở bước riêng, không đặt mật khẩu hoặc thông tin login trong changelog.

Mục tiêu là:

- app_reader được USAGE trên schema app và SELECT trên bảng orders.
- app_writer được USAGE trên schema app và SELECT, INSERT, UPDATE, DELETE trên bảng orders.
- Không trao quyền CREATE/DROP cho hai role runtime chỉ vì chúng cần đọc/ghi dữ liệu.
- Khi thêm view hoặc sequence sau này, cấp thêm quyền phù hợp, không giả định quyền trên bảng tự lan sang mọi đối tượng.

**Các giả định phải được xác minh trong database thật.** Câu lệnh GRANT chạy được trên shop_lab không chứng minh role tương ứng đã tồn tại ở production hoặc mọi tài khoản đã được phép sử dụng chúng.

## 7. Khai báo GRANT bằng changeset Liquibase YAML

Ví dụ một changeset dùng **sql** để cấp quyền:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 101-grant-orders-access
      author: platform-team
      comment: Cấp quyền tối thiểu trên bảng orders
      preConditions:
        - onFail: HALT
        - onError: HALT
        - dbms:
            type: postgresql
        - tableExists:
            schemaName: app
            tableName: orders
        - sqlCheck:
            expectedResult: "2"
            sql: |
              SELECT COUNT(*)
              FROM pg_roles
              WHERE rolname IN ('app_reader', 'app_writer')
      changes:
        - sql:
            sql: GRANT USAGE ON SCHEMA app TO app_reader, app_writer;
        - sql:
            sql: GRANT SELECT ON TABLE app.orders TO app_reader;
        - sql:
            sql: |
              GRANT SELECT, INSERT, UPDATE, DELETE
              ON TABLE app.orders TO app_writer;
      rollback:
        - sql:
            sql: |
              REVOKE SELECT, INSERT, UPDATE, DELETE
              ON TABLE app.orders FROM app_writer;
        - sql:
            sql: REVOKE SELECT ON TABLE app.orders FROM app_reader;
        - sql:
            sql: REVOKE USAGE ON SCHEMA app FROM app_reader, app_writer;
~~~

### 7.1. Giải thích

- **id** và **author** giúp Liquibase định danh changeset; không sửa định danh sau khi triển khai.
- **dbms** yêu cầu PostgreSQL; SQL GRANT không được giả định tương thích mọi DBMS.
- **tableExists** phát hiện việc chạy trước khi tạo bảng.
- **sqlCheck** xác nhận có đúng hai role theo tên mong muốn. Kết quả 2 không chứng minh chúng có quyền đúng; bước GRANT và hậu kiểm vẫn cần thiết.
- Mỗi mục **sql** chứa một câu lệnh, giúp dễ đọc và kiểm soát lỗi hơn một khối quá dài.
- **rollback** mô tả REVOKE; đây là ví dụ học tập cần được đánh giá kỹ trước khi dùng trên môi trường có nhiều dịch vụ.

### 7.2. Hai giới hạn quan trọng của rollback GRANT

**Thứ nhất:** nếu app_reader/app_writer đã có quyền tương tự từ một nguồn khác, lệnh REVOKE của rollback có thể thay đổi trạng thái ngoài mong muốn. Một changeset không tự ghi lại chính xác mọi đường cấp quyền đã tồn tại trước khi nó chạy.

**Thứ hai:** thu hồi USAGE trên schema có thể làm ứng dụng lỗi dù quyền trên bảng vẫn còn. Đừng rollback một changeset cấp quyền trên production khi chưa đánh giá dịch vụ nào đang phụ thuộc vào quyền đó. Trên hệ thống lớn, nên tách quyền theo đối tượng và thời điểm thu hồi, đồng thời chỉ rollback khi đã xác nhận baseline ban đầu.

Nếu người dùng chỉ có quyền SELECT qua một role cha, REVOKE SELECT trực tiếp từ role con chưa chắc loại bỏ quyền hiệu lực. Cần kiểm tra role membership và PUBLIC để đạt kết quả bảo mật mong muốn.

## 8. Kiểm chứng GRANT/REVOKE trên PostgreSQL

Các hàm kiểm tra quyền hiệu lực của PostgreSQL hữu ích hơn việc chỉ nhìn vào câu SQL đã chạy.

~~~sql
SELECT
    has_schema_privilege('app_reader', 'app', 'USAGE') AS reader_schema_usage,
    has_table_privilege('app_reader', 'app.orders', 'SELECT') AS reader_can_select,
    has_table_privilege('app_reader', 'app.orders', 'INSERT') AS reader_can_insert,
    has_table_privilege('app_writer', 'app.orders', 'INSERT') AS writer_can_insert,
    has_table_privilege('app_writer', 'app.orders', 'DELETE') AS writer_can_delete;
~~~

Kết quả mong đợi theo thiết kế trong môi trường học tập là reader có USAGE/SELECT, reader không có INSERT, writer có INSERT/DELETE. Tuy nhiên:

- Một role có thể nhận thêm quyền qua membership hoặc PUBLIC, nên phải kiểm tra **quyền hiệu lực** chứ không chỉ câu GRANT của một changeset.
- Quyền của một role không có nghĩa người dùng cuối cùng đã đăng nhập hoặc được cấp role đúng cách.
- Có quyền trên bảng không bảo đảm truy vấn thành công nếu schema không được phép USAGE.
- **Row-Level Security (RLS)**, chính sách view, quyền cột và logic của function có thể tiếp tục hạn chế hoặc mở rộng hành vi thực tế.

Có thể xem danh sách grant qua information_schema tùy quyền và DBMS:

~~~sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'app'
  AND table_name = 'orders'
ORDER BY grantee, privilege_type;
~~~

Thông tin trong information_schema có thể bị giới hạn theo quyền của user đang truy vấn. Một truy vấn trả ít dòng không chứng minh database không có quyền khác. Với kiểm toán production, kết hợp metadata, role membership và kiểm thử bằng chính danh tính runtime.

## 9. Quyền trên schema không thay thế quyền trên bảng

Trong PostgreSQL, **USAGE ON SCHEMA app** cho phép phân giải/tìm đối tượng trong schema nhưng không tự cấp SELECT cho mọi bảng bên trong. Ngược lại, chỉ GRANT SELECT trên bảng mà thiếu USAGE trên schema có thể khiến ứng dụng vẫn không truy cập được bảng qua tên có schema.

Ví dụ:

~~~sql
GRANT USAGE ON SCHEMA app TO app_reader;
GRANT SELECT ON TABLE app.orders TO app_reader;
~~~

Nếu một role được cấp **CREATE ON SCHEMA app**, role đó có khả năng tạo đối tượng trong schema. Đây là quyền mạnh hơn nhiều so với USAGE và không nên cấp đại trà cho runtime role.

Khi ứng dụng cần đọc một tập bảng cụ thể, hãy ưu tiên **cấp quyền theo danh sách đối tượng** thay vì:

~~~sql
-- Ví dụ cần thận trọng; KHÔNG coi là mặc định an toàn.
GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_reader;
~~~

Lệnh theo toàn schema có thể mở quyền với các bảng nhạy cảm hoặc mới phát hiện chưa được review. Trên PostgreSQL, **GRANT ON ALL TABLES** áp dụng cho các đối tượng hiện có theo phạm vi phù hợp, **không mặc nhiên định nghĩa quyền cho những bảng được tạo trong tương lai**.

## 10. Quyền trên sequence: ví dụ dễ bị bỏ sót

Trong PostgreSQL, một cột dùng sequence theo kiểu serial hoặc gọi **nextval** có thể cần quyền riêng trên sequence, ngay cả khi role đã có INSERT trên bảng.

Ví dụ:

~~~sql
GRANT USAGE ON SEQUENCE app.orders_order_id_seq TO app_writer;
~~~

Với nhu cầu cụ thể, một số thao tác sequence có thể liên quan đến SELECT hoặc UPDATE thay vì chỉ USAGE. Cần xác định cơ chế sinh ID đang dùng và quyền cần thiết cho nó. **Identity column** và **serial/nextval** có khác biệt về cơ chế quyền; không tự giả định mọi lệnh INSERT đều phải được cấp thêm cùng một privilege trên sequence.

Một changeset minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 102-grant-order-sequence
      author: platform-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - dbms:
            type: postgresql
        - sequenceExists:
            schemaName: app
            sequenceName: orders_order_id_seq
      changes:
        - sql:
            sql: |
              GRANT USAGE
              ON SEQUENCE app.orders_order_id_seq
              TO app_writer;
      rollback:
        - sql:
            sql: |
              REVOKE USAGE
              ON SEQUENCE app.orders_order_id_seq
              FROM app_writer;
~~~

Ví dụ giả định sequence tồn tại, thuộc quyền quản lý của nhóm và không được role khác sử dụng ngoài chính sách. Không nên suy ra mọi sequence mang tên tương tự đều phục vụ cột order_id: cần kiểm tra metadata của database.

Xác minh:

~~~sql
SELECT has_sequence_privilege(
    'app_writer',
    'app.orders_order_id_seq',
    'USAGE'
) AS writer_sequence_usage;
~~~

Nếu ứng dụng vẫn báo permission denied dù đã cấp INSERT, hãy xác định đối tượng cụ thể bị từ chối từ thông báo lỗi và metadata, không giải quyết bằng cách cấp ALL PRIVILEGES hàng loạt.

## 11. Đối tượng được tạo sau: ALTER DEFAULT PRIVILEGES

GRANT trên bảng hiện có **không phải quy tắc mặc định cho mọi bảng mới**. Nếu ứng dụng cần quyền nhất quán với các bảng sẽ được tạo trong tương lai, PostgreSQL hỗ trợ **ALTER DEFAULT PRIVILEGES**.

Giả sử các bảng mới trong schema app được tạo bởi role **migration_owner**. Một thay đổi có thể khai báo:

~~~sql
ALTER DEFAULT PRIVILEGES
FOR ROLE migration_owner
IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
~~~

Điểm cần hiểu:

1. Default privileges áp dụng cho những đối tượng **được tạo về sau**, không cấp lại quyền cho bảng đã tồn tại.
2. Chúng phụ thuộc vào **role thực sự tạo đối tượng**. Nếu job tạo bảng dưới role khác, quy tắc của migration_owner có thể không áp dụng.
3. Việc thay default privileges có yêu cầu quyền quản trị phù hợp với role tạo đối tượng.
4. Default privileges cho tables, sequences và functions là các nhóm đối tượng riêng.
5. Default privileges không thay thế bước review quyền trên từng bảng có dữ liệu nhạy cảm.

Rollback đối ứng:

~~~sql
ALTER DEFAULT PRIVILEGES
FOR ROLE migration_owner
IN SCHEMA app
REVOKE SELECT ON TABLES FROM app_reader;
~~~

Rollback này chỉ thay đổi chính sách cấp quyền **cho đối tượng mới trong tương lai** theo phạm vi tương ứng; không tự thu hồi mọi quyền đã được cấp cho các bảng hình thành trong thời gian chính sách có hiệu lực.

**Lưu ý về PUBLIC:** PostgreSQL có các quyền mặc định ở cấp toàn role và cấp schema. Một REVOKE ở cấp schema không phải lúc nào cũng có thể đảo ngược một quyền mặc định rộng được thiết lập toàn cục. Đặc biệt với function, cần kiểm tra đúng quy tắc về EXECUTE mặc định cho PUBLIC và thời điểm cấu hình, không nghĩ rằng một lệnh REVOKE cục bộ luôn đóng được mọi đường truy cập.

## 12. Định nghĩa và cấp quyền trên view

Một view có thể đóng vai trò giao diện SQL ổn định để ứng dụng hoặc báo cáo truy vấn. Ví dụ chỉ lộ số đơn đang hoạt động:

~~~sql
CREATE OR REPLACE VIEW app.active_order_summary AS
SELECT
    status,
    COUNT(*) AS order_count,
    COALESCE(SUM(total_amount), 0) AS total_amount
FROM app.orders
WHERE status = 'ACTIVE'
GROUP BY status;
~~~

Nếu nhóm muốn tài khoản báo cáo **report_reader** chỉ đọc view:

~~~sql
GRANT USAGE ON SCHEMA app TO report_reader;
GRANT SELECT ON TABLE app.active_order_summary TO report_reader;
~~~

**Giả định:** report_reader đã tồn tại; app.orders và các cột được tham chiếu đã tồn tại; owner view có quyền đọc bảng nguồn. Đừng cấp SELECT trên app.orders cho report_reader nếu mục tiêu thực sự là hạn chế người đọc chỉ thông qua view.

### 12.1. View không tự động là ranh giới bảo mật hoàn chỉnh

Quy tắc quyền và row-level security của view khác nhau giữa DBMS, và với PostgreSQL có thể phụ thuộc vào cách view được tạo, quyền của owner và tùy chọn **security_invoker** trên các phiên bản hỗ trợ. Việc grant SELECT trên view **có thể** cho phép đọc thông tin từ bảng nền dù người đọc không có SELECT trực tiếp trên bảng; cần review dữ liệu mà view trả về và các điều kiện RLS.

Khi thay định nghĩa view, cần kiểm thử dữ liệu đầu ra, tên/kiểu cột, quyền hiện có và mọi view/function phụ thuộc. CREATE OR REPLACE VIEW không thể thay đổi tùy ý hợp đồng cột trên PostgreSQL; những thay đổi phá vỡ tương thích có thể cần một changeset chuyển đổi riêng.

### 12.2. Chọn runOnChange khi nào?

Một view có định nghĩa đầy đủ có thể được khai báo trong changeset **runOnChange: true** nếu nhóm muốn chạy lại khi checksum của changeset thay đổi. Cách này phù hợp với đối tượng có thể thay thế mà không mất dữ liệu nghiệp vụ.

Ngược lại, **không dùng runOnChange theo mặc định cho GRANT/REVOKE hoặc ALTER TABLE phá hủy**. Thay đổi quyền là quyết định bảo mật theo thời điểm; khi chính sách đổi, một changeset mới thể hiện ý định thu hồi hoặc bổ sung quyền thường dễ truy vết hơn việc sửa âm thầm changeset đã triển khai.

Một release cũ có định nghĩa view cũ cũng có thể ghi đè release mới nếu được chạy muộn với runOnChange. Pipeline production phải kiểm soát thứ tự artifact.

## 13. Function: quyền EXECUTE và tác động của PUBLIC

PostgreSQL cho phép định nghĩa function bằng SQL. Ví dụ function xử lý chuỗi không có tác dụng phụ:

~~~sql
CREATE OR REPLACE FUNCTION app.normalize_code(input_text text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $body$
    SELECT UPPER(BTRIM(input_text));
$body$;
~~~

Sau khi tạo function, nếu chính sách chỉ cho role app_writer gọi:

~~~sql
REVOKE ALL ON FUNCTION app.normalize_code(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.normalize_code(text) TO app_writer;
~~~

**Vì sao cần quan tâm PUBLIC?** Trên PostgreSQL, quyền EXECUTE trên function mới thường được cấp cho PUBLIC theo mặc định. Nếu chỉ GRANT EXECUTE cho app_writer mà không xử lý quyền mặc định rộng hơn, các role khác vẫn có thể thực thi function.

Việc REVOKE và GRANT nên được thực hiện với thứ tự và phạm vi thích hợp để tránh cửa sổ cấp quyền ngoài ý muốn. Có thể nhóm chúng trong một changeset giao dịch trên PostgreSQL khi các câu lệnh và cách thực thi Liquibase hỗ trợ, sau khi kiểm chứng thực tế.

Các function có **SECURITY DEFINER** đặc biệt nhạy cảm vì có thể chạy với quyền của owner thay vì người gọi. Cần kiểm tra search_path, định danh schema đầy đủ, quyền EXECUTE và tính an toàn của SQL bên trong. Một function SECURITY DEFINER không được review có thể trở thành đường nâng quyền dù người gọi chỉ được cấp EXECUTE.

### 13.1. Tại sao splitStatements có thể quan trọng?

Function hoặc procedure thường có nhiều dấu chấm phẩy trong phần thân. Nếu Liquibase tự tách câu lệnh tại delimiter không phù hợp, SQL có thể bị gửi thành nhiều phần không hợp lệ.

Một changeset YAML có thể dùng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 103-create-normalize-function
      author: platform-team
      runOnChange: true
      preConditions:
        - onFail: HALT
        - dbms:
            type: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE OR REPLACE FUNCTION app.normalize_code(input_text text)
              RETURNS text
              LANGUAGE sql
              IMMUTABLE
              AS $body$
                  SELECT UPPER(BTRIM(input_text));
              $body$;
      rollback:
        - sql:
            sql: |
              DROP FUNCTION IF EXISTS app.normalize_code(text);
~~~

Hàm có thể chạy lặp khi định nghĩa thay đổi. Tuy nhiên, **rollback DROP FUNCTION xóa đối tượng**, không phục hồi tự động định nghĩa cũ. Nó có thể làm hỏng hệ thống đang gọi function; cần xem xét forward fix hoặc khôi phục định nghĩa trước đó từ bản phát hành đã kiểm thử.

Một function có chữ ký thay đổi có thể tạo overload mới chứ không thay thế function cũ; đừng giả định CREATE OR REPLACE luôn thay thế bất kỳ thay đổi nào.

## 14. Quản lý schema và sequence bằng SQL có kiểm soát

Với một dự án mới, đôi khi cần tạo schema trước khi tạo bảng và cấp quyền:

~~~sql
CREATE SCHEMA app;
~~~

Việc sử dụng **CREATE SCHEMA IF NOT EXISTS** có thể thuận tiện trong môi trường học tập nhưng không xác minh được schema đang tồn tại có owner và quyền như mong muốn. Trên production, tốt hơn nên kiểm tra trạng thái thật trước khi coi schema đã sẵn sàng.

Sequence là một đối tượng hỗ trợ khác:

~~~sql
CREATE SEQUENCE app.invoice_number_seq
START WITH 1000
INCREMENT BY 1;
~~~

Cần phân biệt:

- Sequence **không tự liên kết** tới cột của bảng chỉ vì cùng tên.
- Nếu ứng dụng gọi nextval, phải kiểm tra quyền trên sequence.
- Xóa rồi tạo lại sequence có thể làm thay đổi trạng thái cấp phát giá trị hoặc gây trùng ID nếu không có kế hoạch.
- Nếu sequence gắn với cột qua dependency hoặc ownership, phải kiểm tra ảnh hưởng của thao tác DROP/ALTER.

Trong Liquibase, nếu có change type phù hợp như createSequence, nên cân nhắc dùng change type đó thay SQL thô để biểu đạt mục tiêu rõ hơn. Chỉ dùng SQL trực tiếp khi thật sự cần cú pháp/thuộc tính đặc thù.

Một số tổ chức quản lý schema, extension hoặc owner tại bước bootstrap do DBA thực hiện. **Không được tự tạo hoặc đổi ownership của đối tượng dùng chung chỉ vì changelog có quyền thực thi.** Phải xác định hệ thống nào sở hữu vòng đời của đối tượng.

## 15. Index, trigger, extension: không phải đối tượng nào cũng nên xử lý giống nhau

### 15.1. Index và vấn đề transaction

Giả sử PostgreSQL có bảng app.orders rất lớn. Một index hỗ trợ truy vấn theo created_at có thể được tạo bằng:

~~~sql
CREATE INDEX ix_orders_created_at
ON app.orders (created_at);
~~~

Nếu cần giảm việc chặn ghi, PostgreSQL hỗ trợ **CREATE INDEX CONCURRENTLY** với những điều kiện đặc thù; câu lệnh này không thể chạy bên trong transaction block thông thường. Một changeset Liquibase minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 104-create-orders-index-concurrently
      author: platform-team
      runInTransaction: false
      preConditions:
        - onFail: HALT
        - dbms:
            type: postgresql
        - tableExists:
            schemaName: app
            tableName: orders
      changes:
        - sql:
            sql: |
              CREATE INDEX CONCURRENTLY ix_orders_created_at
              ON app.orders (created_at);
      rollback:
        - sql:
            sql: |
              DROP INDEX CONCURRENTLY IF EXISTS app.ix_orders_created_at;
~~~

**Chỉ nên áp dụng khi đã kiểm tra Liquibase và PostgreSQL version cụ thể.** Đặt runInTransaction: false tạo rủi ro trạng thái dở dang nếu có nhiều lệnh hoặc công cụ thất bại giữa chừng. CREATE INDEX CONCURRENTLY thất bại có thể để lại một index không hợp lệ cần xử lý có chủ đích. Không sử dụng runInTransaction: false như cách chung để né lỗi DDL hay transaction.

### 15.2. Trigger có phụ thuộc function và bảng

Một trigger phụ thuộc vào function được gọi và bảng nhận trigger. Thứ tự migration thường là:

1. Tạo function trigger phù hợp.
2. Tạo hoặc kiểm tra bảng đích.
3. Khai báo trigger trên bảng.
4. Kiểm thử thao tác INSERT/UPDATE/DELETE có kích hoạt đúng.
5. Kiểm tra quyền của user và tác dụng phụ của trigger.

Khi gỡ trigger/function, phải đảo thứ tự phù hợp và bảo vệ các chức năng đang sử dụng chúng. Với PostgreSQL, function chạy dưới các quy tắc bảo mật riêng; các function trigger không nên được coi như đường cấp quyền tùy ý cho người gọi.

### 15.3. Extension cần quyền và review độc lập

Cú pháp PostgreSQL ví dụ:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

Câu lệnh chỉ để minh họa; **không nên tự chạy trên production** nếu chưa được phê duyệt. Extension có thể tạo nhiều đối tượng, ảnh hưởng schema, quyền, khả năng nâng cấp và yêu cầu đặc biệt của tài khoản triển khai. Một số extension có chính sách trusted và yêu cầu cài đặt khác nhau theo PostgreSQL version.

Rollback **DROP EXTENSION** có thể xóa nhiều đối tượng phụ thuộc hoặc làm ứng dụng khác mất tính năng. Nếu extension được quản lý chung bởi hạ tầng, changelog ứng dụng nên kiểm tra sự hiện diện và yêu cầu quản trị riêng thay vì tự sở hữu toàn bộ vòng đời extension.

## 16. Chọn sql, sqlFile hay formatted SQL changelog

Liquibase hỗ trợ nhiều cách chứa SQL. Quyết định dựa trên kích thước, tính đặc thù DBMS và quy trình review.

### 16.1. sql: đặt SQL trực tiếp trong YAML

Phù hợp khi câu lệnh ngắn, gắn sát một thay đổi và dễ review:

~~~yaml
changes:
  - sql:
      sql: GRANT SELECT ON TABLE app.orders TO app_reader;
~~~

Ưu điểm: SQL và metadata changeset ở gần nhau. Hạn chế: nếu function/procedure dài, YAML nhiều dòng và các quy tắc dấu chấm phẩy có thể khó bảo trì.

### 16.2. sqlFile: lưu SQL ở tệp riêng có phiên bản hóa

Một ví dụ khai báo tham chiếu SQL trong changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 105-grant-report-access
      author: platform-team
      preConditions:
        - onFail: HALT
        - dbms:
            type: postgresql
      changes:
        - sqlFile:
            path: sql/grants/report-access.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
            endDelimiter: ";"
      rollback:
        - sql:
            sql: REVOKE SELECT ON TABLE app.active_order_summary FROM report_reader;
~~~

**Đây là ví dụ mô tả cấu trúc, không phải yêu cầu tạo tệp trong bài học này.** Khi triển khai thực tế, đường dẫn phải trỏ tới một SQL file tồn tại và được quản lý trong cùng repository, chẳng hạn nội dung:

~~~sql
GRANT USAGE ON SCHEMA app TO report_reader;
GRANT SELECT ON TABLE app.active_order_summary TO report_reader;
~~~

**Cảnh báo:** rollback minh họa chỉ REVOKE SELECT trên view, **chưa thu hồi USAGE trên schema**. Đó có thể là chủ đích vì quyền USAGE được chia sẻ với đối tượng khác, hoặc có thể là thiếu sót nếu role không còn cần schema. Từng quyền phải có người sở hữu và một kế hoạch thu hồi rõ ràng.

**relativeToChangelogFile: true** giúp đường dẫn được phân giải tương đối với changelog đang chứa thay đổi, hạn chế phụ thuộc thư mục làm việc của CLI. **splitStatements** và **endDelimiter** cần được cân nhắc khi SQL chứa function, block hoặc delimiter đặc biệt; không nên bật mặc định nếu nó làm vỡ câu lệnh.

### 16.3. Formatted SQL changelog

Một số nhóm chọn lưu metadata và SQL trong cùng tệp **Liquibase formatted SQL**:

~~~sql
--liquibase formatted sql

--changeset platform-team:106-grant-reader dbms:postgresql
GRANT USAGE ON SCHEMA app TO app_reader;
GRANT SELECT ON TABLE app.orders TO app_reader;
--rollback REVOKE SELECT ON TABLE app.orders FROM app_reader;
--rollback REVOKE USAGE ON SCHEMA app FROM app_reader;
~~~

Phương án này thuận tiện với nhóm SQL chuyên sâu, nhưng cần hiểu cách Liquibase phân tách changeset, nhận diện rollback, comment và delimiter của đúng phiên bản công cụ. Không phải mọi cú pháp SQL thuần đều tự trở thành Liquibase formatted SQL khi đặt vào một tệp .sql.

### 16.4. SQL thô có giới hạn về tính khả chuyển

Một change type có cấu trúc có thể cho Liquibase ánh xạ sang SQL tương ứng với từng DBMS. SQL thô được phát đi với ngữ nghĩa mà DBMS cụ thể hiểu. Vì vậy, changelog chứa GRANT, CREATE EXTENSION hoặc SQL function thường nên có điều kiện **dbms**, kiểm thử trên DBMS được hỗ trợ và chính sách lỗi rõ ràng.

## 17. Tiền điều kiện và khả năng chạy lặp

GRANT/REVOKE thường có thể được gọi nhiều lần ở mức SQL mà không báo lỗi chỉ vì quyền đã được cấp/thu hồi, nhưng **không có nghĩa changeset phải chạy lại**.

Liquibase quản lý mỗi changeset thông qua **DATABASECHANGELOG**. Với changeset thông thường:

- Lần đầu chưa có lịch sử: đánh giá điều kiện rồi thực thi.
- Lần tiếp theo, nếu changeset đã chạy hợp lệ: thường bỏ qua.
- Nếu sửa nội dung changeset đã triển khai: có thể phát sinh lỗi checksum.
- Nếu cần thay đổi chính sách quyền: tạo changeset mới với id mới, thể hiện rõ quyền được cấp hoặc thu hồi.

Ví dụ kiểm tra quyền trước khi cấp:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - dbms:
      type: postgresql
  - sqlCheck:
      expectedResult: "1"
      sql: |
        SELECT COUNT(*)
        FROM pg_roles
        WHERE rolname = 'app_reader'
~~~

Điều kiện này xác nhận role tồn tại, không ngăn quyền bị thay đổi về sau bởi quy trình khác. **Precondition không phải công cụ kiểm toán drift liên tục**. Nếu có yêu cầu phát hiện drift, cần kiểm tra metadata/quyền ngoài lịch sử changeset và có quy trình hòa giải được phê duyệt.

Đừng dùng **MARK_RAN** chỉ để cho pipeline tiếp tục khi role hoặc object bắt buộc chưa tồn tại; điều đó có thể ghi rằng changeset hoàn tất dù quyền chưa được cấp. **HALT** là lựa chọn an toàn cho những điều kiện bảo mật bắt buộc.

## 18. An toàn khi tham số hóa GRANT và đối tượng

Đôi khi nhóm muốn dùng cùng changelog cho schema dev, test và production, với tên schema hoặc role khác nhau. Liquibase hỗ trợ changelog parameters, nhưng thay thế thuộc tính là cơ chế thay thế giá trị/chuỗi khi xử lý changelog, **không tương đương prepared statement** hay việc bind an toàn của JDBC.

Tên schema, role và đối tượng là **SQL identifier**. Nếu chúng được lắp vào SQL thô từ đầu vào thiếu tin cậy, có thể gây lỗi cú pháp, cấp quyền sai hoặc rủi ro SQL injection. Không cho một request người dùng hoặc dữ liệu không đáng tin tùy ý quyết định tên role được GRANT.

Hãy dùng bảng ánh xạ được kiểm soát:

| Môi trường | Schema được phép | Role runtime |
|---|---|---|
| Dev | dev_app | dev_app_reader |
| Test | test_app | test_app_reader |
| Production | app | app_reader |

Trong CI/CD, xác nhận các giá trị nằm trong **allowlist** của môi trường; review SQL sau khi resolve; không dùng tên job làm bằng chứng duy nhất về database đang kết nối. Nếu role không tồn tại, cần dừng và điều tra thay vì mặc nhiên tạo user/role với password trong changelog.

**Không chứa mật khẩu, token, private key hoặc chuỗi kết nối có secret trong SQL GRANT, changelog hoặc output update-sql.** Secret thuộc về hệ thống quản lý bí mật và được cấp cho tiến trình triển khai theo chính sách.

## 19. Quyền sở hữu và khác biệt giữa các DBMS

Những câu lệnh SQL trong bài mang tính PostgreSQL. Một số khác biệt quan trọng:

| Chủ đề | PostgreSQL | Những khác biệt cần kiểm tra ở DBMS khác |
|---|---|---|
| Role/user | Role có thể có LOGIN, membership và quyền đối tượng | MySQL, Oracle, SQL Server tổ chức principal, user, role theo mô hình riêng |
| Schema USAGE | USAGE ON SCHEMA cần để phân giải đối tượng | SQL Server có mô hình schema permission khác; MySQL dùng database-level privilege |
| Sequence | Privilege USAGE/SELECT/UPDATE trên sequence | Hệ quản trị khác có cú pháp và mô hình sequence/identity khác |
| Default privileges | ALTER DEFAULT PRIVILEGES theo role tạo đối tượng | Không thể dịch nguyên cú pháp sang mọi DBMS |
| Function EXECUTE | EXECUTE và quyền PUBLIC mặc định đáng lưu ý | Quyền procedure/function, definer/invoker có quy tắc riêng |
| Extension | CREATE EXTENSION và chính sách trusted/privilege | DBMS khác có package, plugin hay capability tương ứng khác |
| DDL giao dịch | Nhiều DDL hỗ trợ transaction, có ngoại lệ như CREATE INDEX CONCURRENTLY | MySQL và DBMS khác có implicit commit và hạn chế DDL khác nhau |

Với hệ thống đa DBMS, nên chia changeset theo **dbms**, dùng change type chung ở nơi có thể và kiểm thử từng nhánh trên DBMS mục tiêu. Không tạo một changelog SQL “đẹp về cú pháp” rồi mặc định nó có thể chạy ở mọi hệ quản trị.

### 19.1. GRANT và ownership không phải cùng thao tác

Một GRANT không thay đổi owner của bảng. Muốn chuyển owner có thể cần câu lệnh khác, với quyền và hệ quả riêng. Đổi owner có thể thay đổi khả năng ALTER/DROP và chính sách cấp quyền về sau, đặc biệt khi có default privileges hoặc function chạy theo owner.

Không chuyển owner của đối tượng sang tài khoản ứng dụng chỉ để giải quyết lỗi runtime. Nên giữ một mô hình owner ổn định cho schema và đối tượng được quản lý bởi Liquibase.

## 20. Rollback quyền và đối tượng hỗ trợ

Rollback có thể được chia thành ba nhóm:

**Nhóm A — quyền truy cập:** ví dụ GRANT SELECT được đảo bằng REVOKE SELECT. Tuy nhiên, cần biết quyền đó có tồn tại từ trước hay không và liệu role vẫn có quyền hiệu lực qua membership/PUBLIC hay không.

**Nhóm B — đối tượng hỗ trợ mới:** ví dụ CREATE VIEW được đảo bằng DROP VIEW. Nếu view đã được ứng dụng sử dụng hoặc có phụ thuộc, DROP có thể làm gián đoạn dịch vụ; đôi khi phương án tốt hơn là tạo định nghĩa sửa lỗi hoặc một changeset riêng.

**Nhóm C — đối tượng quản trị chung:** extension, schema, role hoặc default privileges có thể đang phục vụ nhiều dịch vụ. Rollback tự động bằng DROP/REVOKE có thể không phù hợp; đôi khi cần quy trình khôi phục được điều phối bởi DBA hoặc infrastructure.

| Thay đổi | Rollback có thể mô tả | Câu hỏi cần xác nhận |
|---|---|---|
| GRANT SELECT trên bảng | REVOKE SELECT | Quyền đã tồn tại trước đó? Có dịch vụ khác dùng? |
| GRANT EXECUTE function | REVOKE EXECUTE | PUBLIC hoặc role cha còn quyền không? |
| ALTER DEFAULT PRIVILEGES | REVOKE default privilege tương ứng | Các đối tượng đã được tạo trong thời gian đó xử lý ra sao? |
| CREATE VIEW | DROP VIEW hoặc phục hồi định nghĩa trước | Có ứng dụng/đối tượng phụ thuộc? |
| CREATE FUNCTION | DROP FUNCTION hoặc định nghĩa sửa lỗi | Chữ ký, overload và quyền EXECUTE ra sao? |
| CREATE SEQUENCE | DROP SEQUENCE | Giá trị đã cấp và quan hệ sở hữu có bị mất? |
| CREATE INDEX | DROP INDEX | Query plan, tính duy nhất và khả năng online DDL? |
| CREATE EXTENSION | Có thể không nên tự động DROP | Có đối tượng phụ thuộc hoặc dịch vụ dùng chung? |

**Không xem rollback SQL là bản sao ngược hoàn toàn của một hành động bảo mật.** Quyền hiệu lực có thể đến từ nhiều nguồn và dữ liệu/vòng đời đối tượng thay đổi sau lần GRANT. Mỗi rollback cần giới hạn phạm vi, tiền điều kiện hoặc ít nhất chứng cứ vận hành rõ ràng.

## 21. Quy trình CI/CD an toàn cho SQL quyền và đối tượng

Một pipeline có thể triển khai theo các bước:

1. **Khóa phiên bản:** dùng cùng revision changelog, phiên bản Liquibase, Java và JDBC driver đã được kiểm thử.
2. **Xác định owner:** role nào tạo đối tượng, role nào có thể GRANT, ai chịu trách nhiệm login role và secret.
3. **Kiểm tra đích:** host, database, schema và account thực tế khớp môi trường mong muốn.
4. **Kiểm tra phụ thuộc:** role, schema, bảng, sequence, view/function phải tồn tại theo đúng thứ tự.
5. **Validate changelog:** chạy Liquibase validate.
6. **Xem trước SQL:** sinh update-sql, kiểm tra GRANT/REVOKE, role, schema và những thao tác DROP/CREATE có rủi ro.
7. **Kiểm thử trên test/staging:** chạy migration bằng quyền gần production, không chỉ bằng superuser.
8. **Kiểm tra quyền hiệu lực:** dùng has_*_privilege hoặc công cụ tương đương, thử đọc/ghi bằng runtime role.
9. **Production gate:** xét phê duyệt, backup/khôi phục khi đối tượng có dữ liệu hoặc nhiều phụ thuộc, và thời gian triển khai.
10. **Triển khai có giám sát:** chỉ một job có chủ sở hữu rõ ràng, giữ log không chứa secret, đối chiếu DATABASECHANGELOG.
11. **Hậu kiểm:** quyền đúng tập cho phép, chức năng ứng dụng hoạt động, không còn quyền thừa hoặc đối tượng mồ côi ngoài kế hoạch.

Ví dụ lệnh:

~~~bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status --verbose
liquibase --defaults-file=liquibase.properties update-sql
~~~

Sau review và phê duyệt:

~~~bash
liquibase --defaults-file=liquibase.properties update
~~~

Tên lệnh có thể thay đổi theo phiên bản CLI; ví dụ tài liệu cũ có thể gọi updateSQL. **validate không chứng minh GRANT sẽ thành công trên production**, còn **update-sql không chứng minh các role và quyền hiệu lực đã chính xác**. Cần kiểm tra bằng database đích hoặc môi trường đại diện.

Khi Spring Boot tự chạy Liquibase lúc khởi động và CI/CD cũng có job migration, phải chọn một chủ sở hữu cho mỗi lượt phát hành. DATABASECHANGELOGLOCK giúp điều phối tiến trình nhưng không phải cơ chế phân quyền và không giải quyết việc hai phiên bản ứng dụng khác nhau muốn cấp/thu hồi quyền trái ngược.

## 22. Kịch bản thực hành: cấp quyền đọc cho báo cáo

**Bối cảnh:** ứng dụng bán hàng có bảng app.orders. Một dịch vụ báo cáo cần xem số đơn ACTIVE nhưng không được đọc toàn bộ bảng orders và không có quyền ghi dữ liệu.

### Bước 1. Chuẩn bị database và role

Trong database học tập **shop_lab**, kiểm tra schema app và bảng orders. Role **report_reader** được hạ tầng hoặc DBA tạo trước, không commit password hoặc thao tác tạo login role vào bài học.

### Bước 2. Tạo view

Viết changeset tạo **app.active_order_summary** theo định nghĩa ở mục 12. Tài khoản migration có quyền sở hữu và tạo view phù hợp; review dữ liệu mà view có thể tiết lộ.

### Bước 3. Cấp quyền

Viết một changeset GRANT USAGE ON SCHEMA app và GRANT SELECT ON app.active_order_summary TO report_reader. Không GRANT SELECT trên app.orders cho report_reader nếu yêu cầu chỉ được truy vấn view.

### Bước 4. Kiểm tra trước thực thi

Chạy validate và update-sql trên shop_lab. Xác nhận SQL không chứa GRANT ALL, không cấp quyền cho PUBLIC và không đụng database/schema khác.

### Bước 5. Thực thi

Chạy update bằng tài khoản migration có quyền cần thiết. Kiểm tra dòng changeset trong DATABASECHANGELOG.

### Bước 6. Kiểm chứng quyền

~~~sql
SELECT
    has_schema_privilege('report_reader', 'app', 'USAGE') AS schema_access,
    has_table_privilege(
        'report_reader', 'app.active_order_summary', 'SELECT'
    ) AS view_select,
    has_table_privilege(
        'report_reader', 'app.orders', 'SELECT'
    ) AS base_table_select;
~~~

Trong mô hình tối thiểu quyền, mong đợi schema_access = true, view_select = true và base_table_select = false. Nếu base_table_select = true, phải điều tra nguồn quyền: membership, PUBLIC hoặc GRANT trực tiếp trước đó.

### Bước 7. Thử truy vấn bằng role thực tế

Sau khi có cơ chế đăng nhập/đổi role được phép, thử SELECT trên view và thử SELECT trực tiếp trên bảng orders bằng chính danh tính runtime, không phải owner/superuser. Quan sát thêm RLS, phạm vi dữ liệu và khả năng truy vấn từ ứng dụng.

### Bước 8. Kiểm chứng rollback trên lab

Chỉ khi không còn ứng dụng phụ thuộc, thử REVOKE SELECT trên view rồi xác nhận role không còn đọc được. Không xóa schema hoặc view dùng chung chỉ để minh họa rollback nếu còn dịch vụ khác sử dụng.

**Kết quả kỳ vọng:** người học có thể giải thích tại sao SELECT trên view chưa đồng nghĩa SELECT trên bảng, tại sao phải có USAGE trên schema và vì sao rollback GRANT phải xét quyền hiệu lực trước/sau.

## 23. Tình huống lỗi và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| GRANT báo role không tồn tại | Chưa bootstrap role hoặc sai tên | Kiểm tra pg_roles và quy trình tạo role, dừng migration có điều kiện |
| permission denied khi GRANT | Role triển khai không phải owner/không có GRANT OPTION phù hợp | Xác định owner và chính sách phân quyền, không nâng lên superuser tùy tiện |
| App vẫn không SELECT được | Thiếu USAGE schema, quyền bảng hoặc role membership | Kiểm tra has_schema_privilege, has_table_privilege, kết nối runtime |
| App INSERT được nhưng không sinh ID | Thiếu quyền sequence với cơ chế nextval hoặc cấu hình ID sai | Kiểm tra loại cột, sequence và quyền cần thiết |
| Đã REVOKE nhưng role vẫn đọc được | Quyền kế thừa qua membership, PUBLIC hoặc nguồn grant khác | Kiểm toán quyền hiệu lực và các đường cấp quyền |
| Function callable bởi nhiều role ngoài ý muốn | PUBLIC còn EXECUTE hoặc GRANT quá rộng | Kiểm tra default privileges và quyền EXECUTE hiệu lực |
| Đổi view làm ứng dụng lỗi | Hợp đồng cột thay đổi, phụ thuộc khác chưa được xét | Review CREATE OR REPLACE và các consumer, chuyển đổi nhiều pha |
| SQL function bị tách sai | splitStatements/endDelimiter chưa phù hợp | Điều chỉnh xử lý SQL và kiểm thử trên DBMS |
| CREATE INDEX CONCURRENTLY lỗi | Dùng transaction hoặc gặp tranh chấp, dữ liệu sai | Kiểm tra runInTransaction, trạng thái index, kế hoạch phục hồi |
| SQL-file không tìm thấy | path hoặc relativeToChangelogFile sai | Kiểm tra cấu trúc dự án và đường dẫn trong artifact |
| Chạy đúng changelog nhưng sai schema | JDBC URL, default schema, placeholder sai | Xác minh database/schema đích và SQL sau resolve |
| Rollback xóa quyền cần thiết | REVOKE ảnh hưởng role dùng chung | Kiểm tra baseline và các phụ thuộc trước rollback |
| Checksum mismatch | Đã sửa changeset quyền/đối tượng từng chạy | Giữ nguyên lịch sử, tạo changeset mới hoặc xử lý theo quy trình thay đổi có kiểm soát |
| Role đúng nhưng vẫn bị từ chối trên hàng dữ liệu | RLS hoặc chính sách bảo mật ứng dụng | Phân biệt table privilege và row-level policy |

Không sửa trực tiếp DATABASECHANGELOG, không dùng clear-checksums hoặc MARK_RAN chỉ để che lỗi quyền hoặc bỏ qua đối tượng bắt buộc chưa tồn tại. Nếu cấp quyền lỡ quá rộng, cần đánh giá tác động ngay, tạo thao tác thu hồi phù hợp và kiểm tra lại quyền hiệu lực.

## 24. Checklist trước khi đưa changeset SQL vào production

- [ ] Tôi đã xác định rõ quyền được cấp cho role nào, trên đối tượng nào và vì mục đích gì.
- [ ] Tôi không cấp ALL PRIVILEGES hoặc CREATE/ALTER/DROP cho runtime role nếu không thật sự cần.
- [ ] Role và schema đã tồn tại đúng chủ sở hữu; việc tạo login/secret được quản lý ngoài changelog ứng dụng.
- [ ] Tôi hiểu sự khác nhau giữa USAGE trên schema và quyền trên bảng/sequence/function.
- [ ] Tôi đã kiểm tra role membership, PUBLIC, RLS và quyền hiệu lực khi thích hợp.
- [ ] Tôi hiểu GRANT trên bảng hiện có không tự mở rộng sang bảng tương lai.
- [ ] Nếu dùng ALTER DEFAULT PRIVILEGES, role tạo object và phạm vi tương lai đã rõ ràng.
- [ ] Mọi SQL đặc thù DBMS có precondition/giới hạn DBMS và được kiểm thử đúng hệ quản trị.
- [ ] Thứ tự tạo đối tượng trước khi GRANT và thứ tự thu hồi trước khi DROP được thiết kế hợp lý.
- [ ] Đường dẫn sqlFile, encoding, delimiter và splitStatements đã được xác minh trên công cụ thật.
- [ ] Tôi đã review SQL sau khi thay thế tham số; schema/role chỉ nhận giá trị từ allowlist.
- [ ] Không có password, token hoặc dữ liệu nhạy cảm trong changelog, update-sql, log hay artifact CI.
- [ ] Tôi hiểu rollback có thể phá quyền dịch vụ khác hoặc mất đối tượng, và có phương án khôi phục.
- [ ] Tôi đã thử migration bằng role có quyền gần production, không chỉ tài khoản superuser.
- [ ] Tôi đã kiểm tra DATABASECHANGELOG, metadata và quyền bằng chính role runtime sau deploy.
- [ ] Changelog đã được review, ghi nhận phiên bản và chuyển qua dev/test trước production.

## 25. Kết luận

**Khai báo quyền truy cập và đối tượng hỗ trợ bằng SQL** giúp Liquibase quản lý trọn vẹn hơn các thay đổi phục vụ một bản phát hành database, không chỉ schema và dữ liệu. Những câu lệnh **GRANT/REVOKE**, tạo schema, sequence, view, function, index hoặc extension có thể được đặt trong changeset có **id/author**, **precondition**, **rollback**, **checksum** và lịch sử trong **DATABASECHANGELOG**.

Nhưng một migration quyền chỉ đáng tin khi nó tuân thủ **nguyên tắc tối thiểu quyền**, kiểm tra **đúng role và database đích**, hiểu **quyền hiệu lực qua membership/PUBLIC**, quản lý **phụ thuộc đối tượng**, review SQL thực tế và có phương án xử lý rollback phù hợp. Trong module DATABASE_SCHEMA_MIGRATION_LIQUIBASE, cách tiếp cận này kết nối SQL đặc thù DBMS với quy trình Liquibase có kiểm chứng trên dev, test, production và các luồng triển khai Spring Boot/CI/CD, giúp giảm thao tác cấp quyền thủ công và tăng khả năng truy vết thay đổi.

