# Flyway, Liquibase và quy trình kiểm tra migration PostgreSQL

Thay đổi lược đồ là một phần thường xuyên của phát triển ứng dụng: thêm bảng, đổi kiểu dữ liệu, tạo index, bổ sung constraint, chuyển đổi dữ liệu và loại bỏ cấu trúc cũ. Nếu các thay đổi này được chạy thủ công trên từng môi trường, source code và database dễ lệch phiên bản. Một máy chủ có thể đã thêm cột, máy khác chưa có; migration có thể chạy hai lần; hoặc ứng dụng mới được triển khai trước khi schema sẵn sàng.

Flyway và Liquibase giúp quản lý thay đổi database bằng các migration có phiên bản, lịch sử thực thi và cơ chế phát hiện thay đổi. Flyway thường tổ chức migration SQL theo tên file và version; Liquibase tổ chức thay đổi thành changesets trong changelog XML, YAML, JSON hoặc SQL. Cả hai đều có thể được tích hợp vào CI/CD để kiểm tra migration trên PostgreSQL trước khi triển khai.

Công cụ migration không thay thế thiết kế schema, kiểm tra lock impact hay kế hoạch rollback. Một migration chạy thành công trong database rỗng vẫn có thể thất bại khi nâng cấp dữ liệu production lớn. Quy trình tốt cần kiểm thử cả đường tạo mới và đường nâng cấp từ phiên bản đang chạy, đo thời gian/lock, xác minh dữ liệu và triển khai theo các bước tương thích với ứng dụng.

~~~text
       Developer changes schema / application
                       |
                       v
             Migration source files
                 /           \
                v             v
             Flyway        Liquibase
                \             /
                 \           /
                  v         v
              CI migration validation
                       |
              +--------+---------+
              |                  |
              v                  v
         Fresh database    Upgrade fixture
              |                  |
              +--------+---------+
                       |
                       v
               Schema/data tests
                       |
                       v
                Review & approval
                       |
                       v
                Deployment runner
                       |
                       v
               PostgreSQL target
                       |
             History / lock tables
                       |
                       v
              Observe and verify
~~~

Bài này thuộc chương **Thay đổi lược đồ** của module *Database Engine Relational PostgreSQL*, tập trung vào Flyway, Liquibase và quy trình kiểm tra migration có thể lặp lại, kiểm soát được và an toàn cho production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao cần quản lý schema changes bằng migration files.
2. Phân biệt Flyway versioned và repeatable migrations.
3. Hiểu naming convention và thứ tự chạy của Flyway.
4. Giải thích schema history, checksum, validate, info và repair.
5. Phân biệt Liquibase changelog, changeset, id, author và path.
6. Hiểu DATABASECHANGELOG và DATABASECHANGELOGLOCK.
7. Viết migration SQL cho PostgreSQL bằng cả hai công cụ.
8. Chọn giữa SQL-first và changelog formats.
9. Kiểm soát thứ tự migration và dependency giữa objects.
10. Xử lý migration đã chạy trên môi trường dùng chung.
11. Thiết kế rollback hoặc forward-fix phù hợp.
12. Hiểu DDL transaction behavior và các ngoại lệ PostgreSQL.
13. Quản lý index creation, constraints, enums và partition changes.
14. Dùng expand-contract để deploy schema tương thích nhiều phiên bản ứng dụng.
15. Backfill dữ liệu lớn theo batch.
16. Kiểm soát lock_timeout, statement_timeout và lock impact.
17. Kiểm thử migration trên database mới và database có dữ liệu cũ.
18. Kiểm tra schema, data invariants, indexes, permissions và query behavior.
19. Tích hợp migration validation vào CI/CD.
20. Triển khai migration với một runner duy nhất và quan sát kết quả.
21. Bảo vệ credentials và quyền thực thi migration.
22. Xử lý lỗi, migration drift và khác biệt giữa các môi trường.
23. Xây dựng quy trình review, release, rollback và incident response.

## 2. Vì sao cần migration management?

Database schema là một phần của ứng dụng được triển khai. Nếu code thay đổi nhưng schema không thay đổi đúng cách, ứng dụng có thể lỗi khi đọc/ghi hoặc tạo dữ liệu không nhất quán.

### 2.1. Lịch sử thay đổi

Migration files ghi lại database đã thay đổi như thế nào theo thời gian. Một developer mới có thể dựng schema từ đầu bằng cách áp dụng toàn bộ migration theo thứ tự.

### 2.2. Tính lặp lại

Cùng một bộ migration có thể chạy qua local, test, staging và production. Điều này giảm sai khác do thao tác thủ công.

### 2.3. Trạng thái đã áp dụng

Flyway và Liquibase lưu lịch sử changes đã chạy. Runner biết changes nào còn pending và tránh áp dụng lại changeset đã hoàn tất theo cơ chế của công cụ.

### 2.4. Kiểm tra tính toàn vẹn

Checksum giúp phát hiện file migration đã thay đổi sau khi chạy. Validate giúp phát hiện drift giữa artifact và lịch sử database.

### 2.5. Review trước deploy

Migration SQL nằm trong code review, có thể kiểm tra lock, data rewrite, index build, quyền và khả năng tương thích với application release.

### 2.6. Không có công cụ nào bảo đảm migration an toàn tự động

Một câu lệnh ALTER TABLE hợp lệ vẫn có thể chờ lock lâu, rewrite bảng lớn hoặc làm ứng dụng cũ lỗi. Công cụ quản lý thứ tự và lịch sử; con người vẫn phải đánh giá tác động.

## 3. Flyway và Liquibase: cách tiếp cận

| Tiêu chí | Flyway | Liquibase |
| --- | --- | --- |
| Đơn vị thay đổi | Migration file | Changeset |
| Cách định nghĩa | SQL hoặc Java migrations; repeatable SQL phổ biến | XML, YAML, JSON, formatted SQL và extensions |
| Versioning | V... migration names | Changelog order và changeset identity |
| Lịch sử | flyway_schema_history | DATABASECHANGELOG |
| Lock coordination | Cơ chế lock/history của Flyway | DATABASECHANGELOGLOCK |
| Checksum | Lưu checksum migration đã áp dụng | Lưu checksum của changeset |
| Rollback | Có thể dùng undo migrations ở cấu hình/edition hỗ trợ; thường dùng forward fix | Có rollback blocks hoặc rollback support cho change types |
| Phù hợp | SQL-first workflow đơn giản, rõ ràng | Changelog mô tả nhiều loại changes và preconditions |
| PostgreSQL-specific SQL | Dùng trực tiếp SQL migration | Dùng SQL changeset hoặc SQL file |

### 3.1. Flyway

Flyway thường dùng file có tên versioned theo pattern V1__description.sql, V2__description.sql. Công cụ ghi version, description, checksum và trạng thái trong schema history table.

### 3.2. Liquibase

Liquibase dùng changelog để mô tả changesets. Mỗi changeset có id, author và file/path định danh. Có thể dùng SQL trực tiếp hoặc change types có cấu trúc.

### 3.3. Không chạy hai tool trên cùng schema nếu không có thiết kế

Nếu Flyway và Liquibase cùng quản lý một schema mà không phân chia ownership rõ, lịch sử và thứ tự có thể không thống nhất. Chọn một migration authority cho mỗi database/schema hoặc định nghĩa ranh giới độc lập có kiểm soát.

### 3.4. SQL-first

PostgreSQL có nhiều tính năng đặc thù. SQL-first giúp dùng đầy đủ cú pháp PostgreSQL và review chính xác câu lệnh được chạy.

### 3.5. Declarative changelog

Liquibase change types có thể giúp mô tả intent và hỗ trợ nhiều database engines. Tuy nhiên, abstraction có thể không thể hiện đầy đủ PostgreSQL-specific behavior; dùng raw SQL khi cần kiểm soát chính xác.

### 3.6. Quyết định dựa trên workflow

Cân nhắc team familiarity, SQL review, multi-database support, rollback requirements, deployment integration và khả năng quản lý changesets dài hạn.

## 4. Nguyên tắc chung khi viết migration

Migration là artifact đã được triển khai. Khi một migration đã chạy trên môi trường dùng chung, nên coi nội dung của nó là immutable.

### 4.1. Một migration có mục tiêu rõ

Mỗi file/changeset nên thực hiện một thay đổi có ý nghĩa và có thể review. Tránh gộp nhiều thay đổi không liên quan khiến failure khó điều tra.

### 4.2. Thứ tự xác định

Dùng version hoặc changelog order rõ ràng. Không dựa vào thứ tự filesystem không được định nghĩa.

### 4.3. Không sửa migration đã chạy

Nếu V12 đã chạy ở staging/production, không sửa V12 để thay đổi logic. Tạo migration mới V13 để sửa trạng thái.

### 4.4. Migration phải review được

Đọc được SQL, hiểu tác động với data volume, locks, constraints, defaults, indexes và application versions.

### 4.5. Idempotency không phải mục tiêu duy nhất

Một migration versioned thường chỉ chạy một lần. Không cần bọc mọi câu lệnh bằng IF NOT EXISTS để che giấu drift. Nếu object đã tồn tại ngoài dự kiến, dừng và xác định nguyên nhân.

### 4.6. Fail fast

Dùng psql ON_ERROR_STOP trong script, transaction khi phù hợp và preconditions để tránh tiếp tục sau lỗi.

### 4.7. Không chứa secrets

Không ghi passwords, API tokens, private keys hoặc production credentials trong migration source.

### 4.8. Data migration cần giới hạn

Backfill bảng lớn phải chia batch, có tiến độ, khả năng resume và kiểm soát lock/replication load.

## 5. Flyway: cấu trúc dự án

Một dự án đơn giản có thể tổ chức như sau:

~~~text
project/
  src/
    main/
      resources/
        db/
          migration/
            V1__create_customer.sql
            V2__create_orders.sql
            V3__add_order_status.sql
            R__customer_summary_view.sql
  flyway.conf
~~~

### 5.1. Migration locations

Flyway tìm migration files trong configured locations. Với Java application, thư mục classpath migration phổ biến là db/migration; CLI có thể dùng filesystem locations.

### 5.2. Versioned migrations

File V1, V2, V3... được chạy theo version ordering. Version có thể có nhiều phần, ví dụ V2.1 hoặc V2026.11.14.1, tùy convention của dự án.

### 5.3. Description

Phần sau hai dấu gạch dưới mô tả mục đích. Dùng tên ngắn, rõ và nhất quán.

### 5.4. Repeatable migrations

File bắt đầu bằng R__ thường được dùng cho objects có thể cập nhật lại khi nội dung thay đổi, như views hoặc functions. Flyway chạy repeatable migrations khi checksum thay đổi, sau các pending versioned migrations theo thứ tự repeatable.

### 5.5. Java migrations

Có thể dùng Java migrations khi logic không thuận tiện biểu diễn bằng SQL. Tuy nhiên, SQL thường dễ audit và review hơn cho schema changes PostgreSQL.

### 5.6. Naming consistency

Không đổi version hoặc description tùy tiện sau khi migration đã chạy. Giữ quy ước nhất quán giữa modules và teams.

## 6. Flyway: viết versioned migration

Ví dụ tạo bảng customers:

~~~sql
-- V1__create_customer.sql
CREATE TABLE app.customer (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    display_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX customer_email_uq
    ON app.customer (email);
~~~

### 6.1. Schema tồn tại trước

Nếu schema app chưa có, tạo trong migration trước hoặc dùng schema bootstrap đã được quản lý. Không giả định schema tồn tại ở mọi môi trường.

### 6.2. Naming

Tên file phải đúng pattern Flyway đã cấu hình. Một lỗi tên file có thể khiến migration không được nhận diện.

### 6.3. SQL order

Tạo schema trước bảng, bảng trước index/constraint phụ thuộc, function trước trigger gọi function.

### 6.4. Transaction

Flyway thường chạy SQL migration trong transaction nếu database và migration cho phép. Một số câu lệnh PostgreSQL không thể chạy trong transaction block; cần cấu hình migration execution phù hợp.

### 6.5. Thay đổi tiếp theo

Nếu cần thêm column, tạo V2__add_customer_phone.sql. Không quay lại sửa V1 sau khi đã chạy.

~~~sql
-- V2__add_customer_phone.sql
ALTER TABLE app.customer
    ADD COLUMN phone_number text;
~~~

## 7. Flyway: schema history, checksum và lệnh thường dùng

Flyway lưu lịch sử trong bảng flyway_schema_history theo schema/configuration đã chọn.

### 7.1. Schema history

Bảng này ghi version, description, type, script, checksum, installed_by, installed_on, execution_time và success cùng các trường liên quan.

### 7.2. migrate

~~~bash
flyway migrate
~~~

Áp dụng các versioned migrations chưa chạy và repeatable migrations cần cập nhật.

### 7.3. info

~~~bash
flyway info
~~~

Hiển thị migration đã chạy, pending, failed/resolved state và thông tin liên quan.

### 7.4. validate

~~~bash
flyway validate
~~~

So sánh migration files hiện tại với lịch sử đã lưu, bao gồm checksum và metadata theo cấu hình. Validate không chứng minh schema/data runtime hoàn toàn đúng.

### 7.5. repair

~~~bash
flyway repair
~~~

Repair điều chỉnh metadata history theo quy tắc của Flyway, chẳng hạn loại bỏ failed migration records hoặc đồng bộ checksum. Đây không phải lệnh sửa schema hay chạy lại SQL bị lỗi. Chỉ dùng sau khi xác định chính xác trạng thái database và nguyên nhân.

### 7.6. baseline

Baseline đánh dấu database hiện hữu như một điểm bắt đầu để Flyway quản lý các migrations tiếp theo. Dùng khi tiếp nhận schema đã tồn tại; không coi baseline là quá trình kiểm tra toàn bộ schema.

### 7.7. clean

Clean xóa objects trong schemas được quản lý theo cấu hình. Đây là lệnh phá hủy dữ liệu/schema; không bật hoặc chạy trên production. Dùng riêng trong test database có thể tái tạo.

### 7.8. undo

Một số Flyway versions/editions hỗ trợ undo migrations. Kiểm tra license/version và định nghĩa undo script nếu workflow yêu cầu. Không giả định mọi SQL migration đều tự động rollback được.

## 8. Flyway: repeatable migrations

Repeatable migrations hữu ích cho definitions được thay thế toàn bộ khi source thay đổi.

### 8.1. View

~~~sql
-- R__customer_summary_view.sql
CREATE OR REPLACE VIEW app.customer_summary AS
SELECT
    c.customer_id,
    c.email,
    count(o.order_id) AS order_count
FROM app.customer AS c
LEFT JOIN app.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.email;
~~~

### 8.2. Function

~~~sql
-- R__normalize_email.sql
CREATE OR REPLACE FUNCTION app.normalize_email(value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT lower(btrim(value));
$$;
~~~

### 8.3. Khi nào dùng

Repeatable phù hợp với view, function, procedure hoặc reference data scripts được thiết kế để chạy lại khi checksum thay đổi.

### 8.4. Không dùng cho data backfill tùy tiện

Một repeatable migration chạy lại khi nội dung đổi. Nếu script thực hiện UPDATE lớn không idempotent hoặc side effects, có thể lặp lại thay đổi ngoài ý muốn.

### 8.5. Versioned hay repeatable?

Dùng versioned cho thay đổi một lần có thứ tự lịch sử. Dùng repeatable cho object definition được tái áp dụng toàn bộ khi source thay đổi.

## 9. Flyway: cấu hình và môi trường

Cấu hình có thể đến từ file, command line, environment variables hoặc application integration.

### 9.1. Cấu hình mẫu

~~~properties
flyway.url=jdbc:postgresql://localhost:5432/appdb
flyway.user=migration_runner
flyway.locations=filesystem:./sql/migrations
flyway.schemas=app
flyway.defaultSchema=app
flyway.validateOnMigrate=true
~~~

Cú pháp prefix/property names có thể khác giữa Flyway CLI, Maven/Gradle plugin và API version. Kiểm tra tài liệu của phiên bản đang dùng.

### 9.2. Tách credentials

Không commit flyway.password vào repository. Inject qua secret store hoặc CI protected variables.

### 9.3. Per-environment config

URL, username, schemas và connection settings có thể khác theo environment; migration source nên giống nhau.

### 9.4. Placeholders

Flyway có hỗ trợ placeholders theo cấu hình. Dùng cho identifier/config có kiểm soát, không dùng để đưa secrets vào SQL history hoặc logs.

### 9.5. Schema history table

Đặt schema/table history rõ ràng để tránh nhiều ứng dụng cùng quản lý một history table ngoài ý muốn.

### 9.6. Migration runner

Trong production, chọn một deployment job/runner làm owner chạy migration. Tránh mọi application replica cùng khởi động và tự migrate nếu không có chiến lược lock/coordination được kiểm chứng.

## 10. Liquibase: changelog và changeset

Liquibase mô tả database changes trong một changelog. Changelog có thể include các file con để chia theo module hoặc release.

### 10.1. Changeset identity

Một changeset được định danh bởi id, author và changelog path. Không tái sử dụng identity cho thay đổi khác.

### 10.2. XML example

~~~xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="001-create-customer" author="platform">
        <sql>
            CREATE TABLE app.customer (
                customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                email text NOT NULL,
                display_name text NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now()
            );
        </sql>
    </changeSet>
</databaseChangeLog>
~~~

Trong dự án thực tế, dùng schemaLocation/version được khuyến nghị bởi Liquibase release đang pin; không phụ thuộc tài liệu "latest" không kiểm soát.

### 10.3. YAML example

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-phone
      author: platform
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: phone_number
                  type: varchar(40)
~~~

### 10.4. Formatted SQL

Liquibase cũng hỗ trợ formatted SQL changelog với header và changeset markers. Cách này giữ SQL PostgreSQL gần nguyên bản.

### 10.5. Include

Root changelog có thể include changelogs theo module/release. Giữ thứ tự include rõ ràng và tránh include cùng changeset nhiều lần ngoài ý muốn.

### 10.6. Một changeset, một mục đích

Chia changesets sao cho failure và rollback dễ hiểu. Tránh tạo một changeset khổng lồ với hàng chục thao tác không liên quan.

## 11. Liquibase: DATABASECHANGELOG và lock

Liquibase lưu metadata trong các bảng quản lý riêng.

### 11.1. DATABASECHANGELOG

Bảng này ghi các changesets đã được thực thi, bao gồm id, author, filename, execution order/date, checksum, description, contexts/labels và deployment metadata tùy version.

### 11.2. DATABASECHANGELOGLOCK

Bảng lock đảm bảo một Liquibase process giữ quyền thực hiện changeset sequence tại một thời điểm cho database tương ứng.

### 11.3. Lock wait

Nếu một deployment khác đang chạy, process mới có thể chờ lock. Điều tra process owner trước khi clear lock.

### 11.4. Clear checksums

Liquibase có lệnh clearCheckSums để yêu cầu tính lại checksums. Không dùng như cách che việc changeset đã sửa sau khi chạy. Xác định vì sao checksum khác và tuân theo change-management policy.

### 11.5. Lock cleanup

Không xóa bảng lock hoặc sửa LOCKED=0 thủ công khi chưa xác định process cũ đã kết thúc. Có thể tạo hai migration runners cùng chạy nếu giải phóng lock sai.

### 11.6. History không phải schema diff

DATABASECHANGELOG cho biết changeset đã chạy. Nó không chứng minh không có DBA hoặc tool khác sửa schema ngoài Liquibase.

## 12. Liquibase: lệnh vận hành

### 12.1. validate

~~~bash
liquibase validate
~~~

Kiểm tra changelog structure và một số metadata/validation rules. Không thay thế chạy migration trên PostgreSQL thật.

### 12.2. status

~~~bash
liquibase status
~~~

Cho biết changesets chưa được áp dụng theo database/changelog configuration.

### 12.3. update

~~~bash
liquibase update
~~~

Áp dụng pending changesets.

### 12.4. updateSQL

~~~bash
liquibase updateSQL
~~~

Sinh SQL mà Liquibase dự kiến chạy mà không thực thi các thay đổi đó. Review SQL output và chạy trên PostgreSQL staging để xác nhận behavior.

### 12.5. rollback

Liquibase hỗ trợ rollback theo tag/count/date tùy version và cấu hình. Rollback chỉ khả thi khi changeset có rollback logic hoặc change type có rollback implementation.

### 12.6. rollbackSQL

Sinh SQL rollback dự kiến để review trước khi thực hiện rollback thật.

### 12.7. diff

Một số workflows dùng diff/diff-changelog để so sánh schema giữa databases. Diff không tự xác định business intent và có thể tạo SQL cần review thủ công.

### 12.8. Tag

Có thể tag database tại release boundary để hỗ trợ rollback theo mốc. Tag không thay thế backup hoặc kiểm tra khả năng phục hồi.

## 13. Liquibase: preconditions, contexts và labels

Các metadata này giúp điều khiển changeset được chạy ở đâu và trong điều kiện nào.

### 13.1. Preconditions

Preconditions kiểm tra trạng thái database trước khi chạy changeset, ví dụ schema/table/column tồn tại hoặc database type/version phù hợp.

~~~xml
<changeSet id="003-add-status" author="platform">
    <preConditions onFail="HALT">
        <tableExists schemaName="app" tableName="orders"/>
        <not>
            <columnExists schemaName="app" tableName="orders" columnName="status"/>
        </not>
    </preConditions>
    <addColumn schemaName="app" tableName="orders">
        <column name="status" type="text"/>
    </addColumn>
</changeSet>
~~~

### 13.2. onFail

Các lựa chọn như HALT, WARN, MARK_RAN hoặc CONTINUE có semantics khác nhau. Dùng HALT khi trạng thái không đúng phải dừng deployment. MARK_RAN chỉ dùng khi đã chứng minh database ở trạng thái tương đương và policy cho phép.

### 13.3. Contexts

Contexts có thể phân loại changesets cho môi trường hoặc mục đích khác nhau. Không dùng contexts để bỏ qua schema cần thiết ở production.

### 13.4. Labels

Labels cung cấp cách lọc changesets theo release/component/team. Giữ policy labels rõ ràng để không bỏ sót changeset.

### 13.5. dbms

Có thể giới hạn changeset cho database engine cụ thể. Dùng khi changelog dùng chung nhiều engines nhưng SQL có khác biệt.

### 13.6. Preconditions không thay test

Một tableExists precondition chỉ chứng minh bảng tồn tại, không chứng minh cấu trúc, dữ liệu và semantics đúng.

## 14. Liquibase rollback và giới hạn

Rollback là khả năng hữu ích, nhưng không phải mọi thay đổi đều có inverse operation an toàn.

### 14.1. Explicit rollback

Ví dụ changeset tạo index có thể định nghĩa rollback drop index tương ứng:

~~~xml
<changeSet id="004-customer-created-index" author="platform">
    <sql>
        CREATE INDEX customer_created_at_idx
        ON app.customer (created_at);
    </sql>
    <rollback>
        <sql>
            DROP INDEX IF EXISTS app.customer_created_at_idx;
        </sql>
    </rollback>
</changeSet>
~~~

### 14.2. Data loss

Rollback DROP COLUMN không thể phục hồi giá trị đã mất nếu không có backup hoặc data copy riêng. Rollback destructive DDL thường không đối xứng.

### 14.3. Data transformations

Nếu changeset chuyển đổi dữ liệu, rollback cần giữ old values hoặc định nghĩa transform ngược có thể chứng minh. Không giả định đổi type có thể tự đổi lại mà không mất dữ liệu.

### 14.4. SQL changesets

Raw SQL changeset có thể cần rollback block tường minh. Kiểm tra generated rollback SQL trước khi tin rằng rollback command sẽ hoạt động.

### 14.5. Forward fix

Trong production, tạo migration mới sửa lỗi thường an toàn và audit được hơn sửa lịch sử hoặc cố đảo ngược một migration đã tạo side effects.

### 14.6. Rollback plan và restore plan

Rollback application/schema khác restore database backup. Khi dữ liệu mới đã được ghi, restore backup có thể làm mất writes sau backup. Thiết kế recovery theo RPO/RTO.

## 15. PostgreSQL DDL và transaction behavior

PostgreSQL hỗ trợ transactional DDL cho nhiều thao tác: nếu transaction rollback, các thay đổi schema thuộc transaction đó thường rollback cùng. Tuy nhiên, có những câu lệnh không thể chạy trong transaction block và một số operation có lock/side effects đặc biệt.

### 15.1. Transactional DDL

Ví dụ:

~~~sql
BEGIN;

ALTER TABLE app.customer
    ADD COLUMN preferred_name text;

CREATE INDEX customer_preferred_name_idx
    ON app.customer (preferred_name);

COMMIT;
~~~

Nếu transaction thất bại trước COMMIT, cả hai thay đổi có thể rollback.

### 15.2. CREATE INDEX CONCURRENTLY

CREATE INDEX CONCURRENTLY không được chạy bên trong transaction block:

~~~sql
CREATE INDEX CONCURRENTLY customer_email_idx
ON app.customer (email);
~~~

Migration runner phải cho phép câu lệnh này chạy ngoài transaction. Cấu hình cụ thể khác giữa Flyway/Liquibase versions và integration; kiểm tra đúng tài liệu và thử trong CI.

### 15.3. REINDEX CONCURRENTLY

Một số dạng REINDEX CONCURRENTLY cũng không chạy trong transaction block. Xác nhận cú pháp và giới hạn theo PostgreSQL version.

### 15.4. VACUUM

VACUUM không thể chạy trong transaction block thông thường. Không gộp VACUUM vào một changeset/migration được runner tự động bao transaction.

### 15.5. CREATE DATABASE

CREATE DATABASE không thể chạy trong transaction block. Thường database provisioning được tách khỏi schema migrations.

### 15.6. ALTER SYSTEM

ALTER SYSTEM thay đổi cấu hình server và không phải schema migration thông thường. Quản lý qua infrastructure/configuration management riêng.

### 15.7. Enum changes

ALTER TYPE ... ADD VALUE có các quy tắc transaction theo PostgreSQL version; trên các version cho phép chạy trong transaction, giá trị enum mới không thể được dùng cho tới khi transaction commit. Tách việc thêm value và migration data cần dùng value đó thành các bước rõ ràng.

### 15.8. Transaction policy

Đừng tắt transaction cho cả migration chỉ vì một câu lệnh không hỗ trợ transaction. Tách non-transactional operation thành migration riêng và giữ các thay đổi khác có transaction khi phù hợp.

## 16. Lock impact và migration an toàn

DDL có thể cần lock mạnh trên table. Một câu lệnh nhanh trên bảng nhỏ có thể chờ rất lâu trên production nếu có long transaction.

### 16.1. Lock acquisition

ALTER TABLE thường cần lock tương đối mạnh; mức lock phụ thuộc loại operation. Khi không lấy được lock, câu lệnh có thể chờ và tạo queue cho các truy vấn khác.

### 16.2. lock_timeout

Đặt giới hạn chờ lock để migration fail nhanh thay vì chờ vô hạn:

~~~sql
SET lock_timeout = '3s';
SET statement_timeout = '15min';

ALTER TABLE app.orders
    ADD COLUMN source_code text;

RESET lock_timeout;
RESET statement_timeout;
~~~

Nếu runner tự bao migration trong transaction, SET/RESET trong cùng transaction cần được đặt có chủ đích. Có thể dùng SET LOCAL khi chạy trong transaction.

### 16.3. statement_timeout

statement_timeout giới hạn thời gian statement chạy, bao gồm thời gian chờ lock. Chọn giá trị phù hợp với operation và deployment window.

### 16.4. Long transactions

Một transaction mở lâu có thể giữ lock hoặc snapshot và chặn DDL. Trước migration, quan sát pg_stat_activity, transaction age và prepared transactions.

### 16.5. Lock queue

Một DDL đang chờ lock có thể khiến các truy vấn mới xếp hàng phía sau tùy lock conflicts. Dừng migration khi thấy blocking lan rộng.

### 16.6. NOWAIT

Một số operations hỗ trợ NOWAIT hoặc lock_timeout để fail sớm. Dùng khi muốn migration thử lấy lock trong cửa sổ ngắn và retry ở thời điểm khác.

### 16.7. Online index build

CREATE INDEX CONCURRENTLY giảm blocking writes so với build thường, nhưng mất nhiều thời gian hơn, dùng thêm I/O và có thể thất bại để lại invalid index cần cleanup.

### 16.8. Review lock level

Đọc PostgreSQL documentation cho operation/version cụ thể. Không suy ra lock chỉ từ tên ALTER TABLE.

## 17. Expand-contract deployment

Expand-contract giúp schema và application versions cùng hoạt động trong thời gian rollout.

### 17.1. Expand

Thêm cấu trúc mới theo cách tương thích ngược, ví dụ thêm nullable column hoặc bảng mới, chưa xóa cột cũ.

### 17.2. Deploy compatible application

Triển khai code có thể đọc/ghi cấu trúc mới mà vẫn hoạt động khi một số application instances còn chạy version cũ.

### 17.3. Backfill

Chuyển dữ liệu cũ sang cấu trúc mới theo batch, theo dõi tiến độ và tính nhất quán.

### 17.4. Switch reads

Sau khi backfill và validation hoàn tất, chuyển application reads sang column/table mới.

### 17.5. Stop old writes

Đợi tất cả app instances cũ đã được thay thế và không còn job/consumer ghi vào cấu trúc cũ.

### 17.6. Contract

Trong một release riêng, xóa cột/bảng/index cũ sau khi xác nhận không còn code hoặc report phụ thuộc.

### 17.7. Vì sao tách release?

Nếu add và drop cùng một deploy, application instances cũ có thể lỗi trong rollout. Expand-contract tạo khoảng tương thích để rolling deployment an toàn hơn.

### 17.8. Ví dụ đổi tên column

Không rename column ngay khi application cũ vẫn dùng tên cũ. Thêm column mới, dual-write có kiểm soát hoặc dùng trigger tạm thời, backfill, chuyển reads, ngừng old writes rồi drop cột cũ.

## 18. Backfill dữ liệu lớn

Backfill có thể tốn nhiều giờ và tạo WAL, bloat, replication lag hoặc lock contention.

### 18.1. Chia batch

Dùng primary key ranges hoặc keyset pagination thay vì một UPDATE toàn bảng kéo dài.

~~~sql
UPDATE app.customer
SET normalized_email = lower(btrim(email))
WHERE customer_id > 100000
  AND customer_id <= 110000
  AND normalized_email IS NULL;
~~~

Lặp lại theo batches với commit riêng, ghi nhận last processed key và số rows cập nhật.

### 18.2. Resume

Backfill nên có checkpoint hoặc điều kiện WHERE để có thể chạy lại mà không cập nhật lại rows đã hoàn tất.

### 18.3. Throttling

Điều chỉnh batch size, pause interval và concurrency dựa trên replication lag, WAL generation, CPU, I/O và application latency.

### 18.4. Idempotent update

Dùng predicate chỉ chọn rows chưa được xử lý. Đảm bảo logic transform có thể chạy lại mà không làm sai dữ liệu.

### 18.5. Concurrent writes

Nếu ứng dụng tiếp tục ghi trong backfill, cần dual-write hoặc cơ chế catch-up để không bỏ sót rows mới. Expand-contract cần định nghĩa rõ write ownership.

### 18.6. Không chạy backfill khổng lồ trong schema migration

Tách schema DDL khỏi data backfill job khi dataset lớn. Điều này giúp deployment ngắn hơn và dễ quan sát/kiểm soát hơn.

### 18.7. Validation

Đếm rows còn NULL, so sánh transformation samples và aggregate checks trước khi chuyển reads.

## 19. Thêm constraint an toàn cho bảng lớn

Một số PostgreSQL operations cho phép tách enforcement và validation.

### 19.1. CHECK NOT VALID

~~~sql
ALTER TABLE app.orders
ADD CONSTRAINT orders_amount_nonnegative
CHECK (amount >= 0) NOT VALID;
~~~

Constraint mới được áp dụng với các row mới/được cập nhật theo semantics PostgreSQL, nhưng dữ liệu cũ chưa được scan để xác minh.

### 19.2. Validate riêng

~~~sql
ALTER TABLE app.orders
VALIDATE CONSTRAINT orders_amount_nonnegative;
~~~

Validation có lock behavior nhẹ hơn một số thao tác tạo constraint trực tiếp, nhưng vẫn tiêu thụ I/O và cần được lên lịch.

### 19.3. Foreign key NOT VALID

Có thể thêm foreign key NOT VALID rồi VALIDATE CONSTRAINT sau khi kiểm tra dữ liệu cũ. Test lock behavior và dependency thực tế.

### 19.4. Unique constraint

Một chiến lược phổ biến là tạo unique index concurrently, kiểm tra index valid, sau đó gắn thành constraint bằng operation phù hợp. Cần kiểm tra PostgreSQL version và giới hạn transaction.

### 19.5. Data cleanup trước

Nếu dữ liệu cũ vi phạm constraint, tìm và xử lý rows trước validation. Không dùng NOT VALID để che vi phạm vĩnh viễn.

## 20. Index migration trên PostgreSQL

Index creation có thể ảnh hưởng mạnh tới availability và I/O.

### 20.1. CREATE INDEX thường

~~~sql
CREATE INDEX orders_created_at_idx
ON app.orders (created_at);
~~~

Operation có thể chặn writes trong thời gian build tùy lock mode. Phù hợp hơn với bảng nhỏ hoặc maintenance window được kiểm soát.

### 20.2. CREATE INDEX CONCURRENTLY

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
ON app.orders (created_at);
~~~

Cho phép INSERT/UPDATE/DELETE tiếp tục trong phần lớn quá trình build nhưng cần nhiều scans và có overhead.

### 20.3. Không trong transaction block

Tách câu lệnh concurrently khỏi migration transaction. Cấu hình Flyway/Liquibase theo phiên bản để chạy changeset ngoài transaction khi cần.

### 20.4. Failed concurrent index

Nếu concurrent build thất bại, có thể để lại index invalid. Kiểm tra pg_index.indisvalid/indisready và cleanup có kiểm soát trước khi retry.

### 20.5. IF NOT EXISTS không bảo đảm index đúng

Một index cùng tên nhưng definition khác có thể khiến migration không đạt trạng thái mong muốn. So sánh pg_get_indexdef và catalog metadata.

### 20.6. Index size và disk

Tính dung lượng tạm/đích và theo dõi disk free. Build concurrent có thể cần thêm storage trong lúc index cũ vẫn tồn tại.

## 21. Data types, enums và object dependencies

### 21.1. Enum

Thêm enum value là thay đổi schema cần phối hợp với application release. Không để application gửi enum label mới trước khi mọi database instance có type tương thích.

### 21.2. Domain và composite types

Tạo type trước function/table dùng type đó. Thay đổi type có thể ảnh hưởng dependencies rộng.

### 21.3. Functions và procedures

Định nghĩa function/procedure nên có migration hoặc repeatable object definition rõ. Kiểm tra search_path và ownership.

### 21.4. Views và materialized views

View phụ thuộc tables/columns. Khi đổi schema, cập nhật view tương thích. Materialized views có thể cần refresh và thời gian refresh cần được tính vào rollout.

### 21.5. Triggers

Tạo function trước trigger. Khi trigger thay đổi data, xem xét side effects, recursion, replication behavior và lock impact.

### 21.6. Extensions

Cài extension package trên server trước CREATE EXTENSION/ALTER EXTENSION UPDATE. Binary library phải có trên mọi host có thể chạy database.

### 21.7. Ownership và grants

Schema migration cần giữ ownership/grants đúng. Migration runner có thể chạy dưới owner role hoặc dùng SET ROLE; tránh để object production thuộc role không còn tồn tại.

## 22. Flyway và Liquibase trong CI

CI nên chạy migration trên database PostgreSQL tạm thời, không chỉ parse SQL.

### 22.1. Fresh database test

Tạo database rỗng với đúng major version/extension dependencies rồi chạy toàn bộ migrations.

### 22.2. Upgrade-path test

Tạo database ở schema/data version gần production, nạp fixture đại diện rồi chạy pending migrations. Đây là kiểm tra quan trọng vì migration có thể chạy tốt trên database rỗng nhưng lỗi khi data đã có.

### 22.3. PostgreSQL version parity

Dùng cùng major version với production target. Với cross-major upgrade, test cả source và target version theo đúng pair.

### 22.4. Extension parity

Cài đúng extension versions, locale/collation và server settings cần thiết.

### 22.5. Validate migration artifact

Flyway validate hoặc Liquibase validate kiểm tra metadata/changelog. Sau đó chạy migrate/update trên DB thực để phát hiện lỗi SQL và runtime.

### 22.6. SQL preview

Dùng Liquibase updateSQL hoặc cơ chế dry-run/preview tương ứng của tool để review SQL dự kiến. Preview không thay thế execution test.

### 22.7. Schema assertions

Kiểm tra columns, types, nullability, indexes, constraints, defaults, functions, triggers, grants và ownership.

### 22.8. Data assertions

Kiểm tra row counts, aggregates, no-duplicate conditions, no-orphan conditions và business invariants.

### 22.9. App compatibility

Chạy integration tests của application trên schema sau migration và nếu có thể, kiểm tra rolling compatibility giữa app version cũ/mới.

### 22.10. Artifact immutability

CI/CD triển khai đúng migration artifact đã được review/build. Không tạo nội dung migration khác nhau tùy environment ngoài placeholders/config được kiểm soát.

## 23. Ví dụ CI workflow tổng quát

~~~text
Pull request
    |
    v
Static review / lint SQL
    |
    v
Start PostgreSQL test service
    |
    v
Install required extensions
    |
    +-------------------------+
    |                         |
    v                         v
Fresh DB test            Upgrade fixture
    |                         |
    v                         v
Flyway migrate /         Restore prior schema
Liquibase update         and representative data
    |                         |
    v                         v
Schema + data tests      Apply pending migrations
    |                         |
    +------------+------------+
                 |
                 v
          Application tests
                 |
                 v
          Review SQL/lock plan
                 |
                 v
             Approve
                 |
                 v
          Staging migration
                 |
                 v
          Production runner
~~~

### 23.1. Pull request gate

Không merge migration nếu fresh install hoặc upgrade-path test thất bại.

### 23.2. Parallel tests

Mỗi CI job cần database riêng hoặc schema/database isolation. Không để hai test runners cùng sửa một database.

### 23.3. Test data

Fixture cần đại diện edge cases: NULLs, duplicate values, large tables, long text, timezone, boundary dates và existing constraints.

### 23.4. Performance test

Đối với migration lớn, đo thời gian, lock duration, WAL, disk growth và replication lag trên staging với data volume gần thực tế.

### 23.5. Approval gate

Production migration cần review SQL và deployment window theo mức rủi ro. Không cho phép auto-apply destructive migration chỉ vì CI pass.

## 24. Kiểm thử migration trên PostgreSQL

Một bộ test tốt gồm nhiều lớp.

### 24.1. Syntax/parse

Kiểm tra file naming, changelog schema, SQL syntax và tool validation.

### 24.2. Execution

Chạy migrations trên PostgreSQL thực tế để kiểm tra permissions, transaction behavior và server-specific features.

### 24.3. Repeatability

Tạo mới database rồi chạy tất cả migrations. Chạy validate/status sau đó để xác nhận history nhất quán.

### 24.4. Upgrade path

Nâng từ các version đang được hỗ trợ. Nếu production có nhiều version nền, test từng đường nâng cấp quan trọng.

### 24.5. Data correctness

Kiểm tra transformation results bằng SQL assertions. Không chỉ kiểm tra migration exit code.

### 24.6. Rollback/forward fix

Nếu dùng rollback, test rollback SQL trên database disposable. Nếu dùng forward fix, kiểm tra recovery migration có thể chạy sau partial failure theo trạng thái thực tế.

### 24.7. Lock behavior

Dùng session thứ hai giữ transaction/lock để kiểm tra migration phản ứng với lock_timeout. Đo lock duration và blocking impact.

### 24.8. Concurrency

Kiểm tra ứng dụng đọc/ghi trong khi migration chạy nếu rollout design yêu cầu online compatibility.

### 24.9. Failure injection

Trong lab, tạo lỗi có kiểm soát giữa migration để xác nhận transaction rollback, history status và recovery procedure. Không cố tình làm điều này trên production.

### 24.10. Restore test

Backup và restore là một phần của migration risk management. Kiểm tra khả năng restore nếu migration có destructive operations.

## 25. Kiểm tra schema và data sau migration

### 25.1. Catalog inspection

Dùng information_schema và PostgreSQL catalogs để kiểm tra schema.

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'app'
ORDER BY table_name, ordinal_position;
~~~

### 25.2. Index definitions

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'app'
ORDER BY tablename, indexname;
~~~

### 25.3. Constraints

~~~sql
SELECT
    conrelid::regclass AS relation,
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'app'::regnamespace
ORDER BY relation::text, conname;
~~~

### 25.4. Invalid indexes

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready
FROM pg_index
WHERE NOT indisvalid OR NOT indisready;
~~~

### 25.5. Data invariants

Ví dụ kiểm tra không còn normalized_email NULL sau backfill:

~~~sql
SELECT count(*)
FROM app.customer
WHERE normalized_email IS NULL;
~~~

### 25.6. Duplicate detection

~~~sql
SELECT email, count(*)
FROM app.customer
GROUP BY email
HAVING count(*) > 1;
~~~

### 25.7. Referential integrity

Kiểm tra orphan rows hoặc constraint validation state. Một constraint tồn tại nhưng NOT VALID chưa chứng minh dữ liệu cũ đã thỏa điều kiện.

### 25.8. Permissions

Xác nhận application role có quyền cần thiết và không có quyền thừa sau migration.

## 26. Migration history và schema drift

History table là nguồn quan trọng nhưng không phải bằng chứng duy nhất về trạng thái schema.

### 26.1. Drift

Schema drift xảy ra khi database bị sửa ngoài migration tool, hoặc migrations khác nhau được chạy giữa môi trường.

### 26.2. Manual hotfix

Nếu DBA thực hiện hotfix trực tiếp production, phải ghi lại và đưa thay đổi tương đương vào migration source. Nếu không, staging/fresh database sẽ không tái tạo được production.

### 26.3. Flyway checksum mismatch

Checksum mismatch thường có nghĩa file migration đã thay đổi sau khi được áp dụng hoặc artifact khác với artifact ban đầu. Xác định nội dung đã chạy và tạo corrective migration thay vì sửa checksum tùy tiện.

### 26.4. Liquibase checksum mismatch

Changeset checksum mismatch cũng cần điều tra. Không dùng clearCheckSums để hợp thức hóa chỉnh sửa không được review.

### 26.5. Baseline hiện hữu

Khi đưa database cũ vào quản lý, so sánh schema thực tế với baseline artifact. Baseline chỉ ghi điểm bắt đầu, không tự đồng bộ object.

### 26.6. Drift detection

Có thể dùng schema diff/catalog snapshots trong CI hoặc định kỳ. Review mọi khác biệt trước khi tạo migration corrective.

## 27. Thực thi migration trong production

Migration production cần một runner có quyền và trách nhiệm rõ ràng.

### 27.1. Một runner

Dùng deployment job hoặc release task chạy migration một lần. Không để từng application pod tự thực thi đồng thời trừ khi cơ chế orchestration đã được thiết kế và kiểm chứng.

### 27.2. Locking

Flyway/Liquibase có cơ chế phối hợp để ngăn migration concurrency. Tuy vậy, vẫn cần pipeline-level serialization để tránh nhiều release cạnh tranh.

### 27.3. Credentials

Migration role thường cần quyền DDL rộng hơn application role. Tách hai credentials và không cấp quyền DDL cho runtime application.

### 27.4. Deployment ordering

Với expand-contract:
1. Deploy expand migration.
2. Deploy app version tương thích.
3. Backfill.
4. Switch reads/writes.
5. Deploy contract migration ở release sau.

### 27.5. Time window

Chạy migration có lock/I/O impact trong window phù hợp. Migration online không đồng nghĩa không cần thông báo/monitoring.

### 27.6. Observe

Theo dõi migration process, PostgreSQL logs, pg_stat_activity, pg_locks, disk, WAL, replication lag và application latency.

### 27.7. Stop conditions

Dừng hoặc abort theo runbook nếu lock wait vượt ngưỡng, disk headroom thấp, replication lag tăng nhanh hoặc application errors vượt giới hạn.

### 27.8. Completion

Chỉ đánh dấu release thành công sau khi tool history, schema assertions, application smoke tests và monitoring đạt yêu cầu.

## 28. Security và separation of duties

### 28.1. Migration role

Tạo role riêng cho deployment runner. Quyền có thể bao gồm ownership/DDL trong schema được quản lý, nhưng không nên là superuser mặc định.

### 28.2. Runtime role

Application runtime chỉ nhận DML/EXECUTE cần thiết. Không cho ứng dụng tự tạo/drop schema trong vận hành thường ngày.

### 28.3. Secret management

Credentials được inject lúc chạy và rotate theo policy. Không ghi password trong changelog, SQL comments, CI artifacts hoặc command logs.

### 28.4. Approval

Destructive DDL như DROP TABLE/COLUMN, data rewrite lớn hoặc truncate cần review/approval phù hợp.

### 28.5. Audit

Ghi người chạy, release ID, commit SHA, target database, thời điểm, migration versions và kết quả.

### 28.6. Least privilege

Nếu migration cần quyền đặc biệt, dùng role tạm thời hoặc elevated job có kiểm soát, sau đó thu hồi quyền không còn cần.

## 29. Những anti-pattern phổ biến

### 29.1. Sửa migration đã chạy

Làm checksum khác và khiến môi trường không đồng nhất. Tạo migration mới.

### 29.2. Chạy DDL thủ công không ghi nhận

Tạo schema drift. Đưa hotfix vào migration history theo cách được review.

### 29.3. Gộp backfill lớn vào migration ngắn

Giữ transaction/lock lâu, tạo WAL và khó theo dõi. Tách job dữ liệu riêng.

### 29.4. DROP ngay trong cùng release

Application instances cũ có thể vẫn truy cập column/table. Dùng expand-contract.

### 29.5. Dùng IF NOT EXISTS để che drift

Object có thể tồn tại nhưng definition sai. Kiểm tra trạng thái và fail nếu không đúng kỳ vọng.

### 29.6. Dựa vào rollback tự động

Không phải DDL/data change nào cũng có inverse. Thiết kế forward fix, backup/restore và data preservation.

### 29.7. Chạy nhiều migration runners

Có thể tạo lock contention và release ordering không rõ. Serialize deployment.

### 29.8. Chỉ test database rỗng

Không phát hiện vấn đề dữ liệu hiện có, duplicates, NULLs, long locks và table rewrite. Test upgrade fixture.

### 29.9. Không review SQL generated

Liquibase abstraction có thể tạo SQL khác dự kiến. Review updateSQL và thực thi trên PostgreSQL staging.

### 29.10. Không đo lock

Một migration "nhỏ" vẫn có thể đợi ACCESS EXCLUSIVE lock. Đo và dùng lock_timeout.

## 30. Troubleshooting

### Lỗi 1. Flyway không tìm thấy migration

Kiểm tra locations, filename pattern, classpath/filesystem path và quyền đọc artifact.

### Lỗi 2. Flyway validate checksum mismatch

So sánh file hiện tại với artifact đã deploy, history row và commit SHA. Không sửa checksum trước khi hiểu drift.

### Lỗi 3. Flyway migration failed

Kiểm tra error và transaction behavior. Xác định DDL đã rollback hoàn toàn hay có non-transactional operation đã thực hiện một phần trước khi chạy repair/retry.

### Lỗi 4. Flyway repair bị dùng sai

Repair chỉ sửa metadata history theo tool semantics, không sửa schema/data. Xác nhận trạng thái database trước khi chạy.

### Lỗi 5. Liquibase changeset checksum changed

Xác định changeset đã áp dụng ở đâu và nội dung có bị sửa không. Tạo changeset mới nếu cần thay đổi.

### Lỗi 6. Liquibase lock không được giải phóng

Xác nhận runner cũ đã dừng và không còn process đang chạy. Chỉ clear lock theo procedure chính thức sau khi xác minh.

### Lỗi 7. Liquibase updateSQL khác dự kiến

Review DBMS/version, changelog parameters, contexts/labels và generated SQL. Chạy trên PostgreSQL staging.

### Lỗi 8. CREATE INDEX CONCURRENTLY báo transaction block

Tách migration non-transactional và cấu hình runner phù hợp. Không bỏ concurrent chỉ để tránh lỗi nếu production cần writes tiếp tục.

### Lỗi 9. ALTER TABLE chờ lock

Xem pg_stat_activity/pg_locks, tìm blocker, dùng lock_timeout và thử lại trong window thích hợp.

### Lỗi 10. Migration chạy lâu

Xác định đang chờ lock, scan/rewrite table, build index, backfill hay I/O. Không chỉ tăng timeout.

### Lỗi 11. Unique constraint thất bại

Tìm duplicate values, xử lý data trước, tạo unique index theo chiến lược online nếu phù hợp rồi attach constraint.

### Lỗi 12. NOT NULL thất bại

Tìm NULL rows, backfill theo batch, validate trước khi đặt NOT NULL.

### Lỗi 13. Subscriber/replica lag tăng sau DDL/backfill

Theo dõi WAL volume, index build, backfill rate và downstream capacity. Throttle job.

### Lỗi 14. App version cũ lỗi sau migration

Schema change không backward-compatible. Dùng expand-contract và rollback app/schema plan.

### Lỗi 15. Fresh install pass nhưng upgrade fails

Fixture cũ có data shape khác hoặc drift. Thêm upgrade-path tests từ các production baseline versions.

### Lỗi 16. Rollback mất dữ liệu

Rollback DDL/data không inverse. Dừng writes, restore/reconcile từ backup hoặc tạo forward fix theo incident plan.

### Lỗi 17. Role thiếu quyền

Xác định object ownership và quyền cần thiết; cấp đúng schema/table privileges hoặc chạy dưới migration owner phù hợp.

### Lỗi 18. Extension không tồn tại

Cài OS package/shared library trước khi CREATE EXTENSION hoặc chạy extension upgrade.

### Lỗi 19. Search_path khác nhau

Dùng schema-qualified object names trong migrations để tránh tạo object vào schema sai.

### Lỗi 20. Migration chạy hai lần

Kiểm tra history/lock table, deployment concurrency và app auto-migration behavior. Serialize runner và khôi phục state đúng theo tool.

## 31. Quy trình kiểm tra migration hoàn chỉnh

~~~text
1. Author migration
       |
       v
2. Review SQL / changelog
       |
       v
3. Validate tool metadata
       |
       v
4. Fresh PostgreSQL database test
       |
       v
5. Upgrade from prior schema fixture
       |
       v
6. Assert schema and data
       |
       v
7. Test app compatibility
       |
       v
8. Measure locks / runtime / WAL
       |
       v
9. Stage deployment
       |
       v
10. Production migration runner
       |
       v
11. Smoke tests and monitoring
       |
       v
12. Record release evidence
~~~

### 31.1. Source review

Review migration file, naming, ordering, DDL semantics, permissions, data transformations và rollback/forward-fix.

### 31.2. Tool validation

Flyway validate hoặc Liquibase validate để kiểm tra metadata/changelog. Kiểm tra version/tool config đã pin.

### 31.3. Fresh install

Tạo DB rỗng, cài extensions và chạy toàn bộ migrations. Xác nhận schema cuối.

### 31.4. Upgrade fixture

Restore schema/data từ release trước rồi chạy pending migrations. Include data edge cases và object dependencies.

### 31.5. Assertions

Kiểm tra catalogs, counts, aggregates, constraints, indexes, permissions và application tests.

### 31.6. Operational test

Đo lock wait, execution duration, WAL, disk và replication lag. Xác nhận migration runner không chạy song song.

### 31.7. Production release

Dùng artifact đã được kiểm thử, một runner, maintenance/rollout window và stop conditions.

### 31.8. Evidence

Lưu migration versions, commit SHA, execution time, logs, validation outputs và approval record.

## 32. Ví dụ quy trình Flyway

Một workflow SQL-first:

~~~text
db/migration/
  V1__create_schema.sql
  V2__create_customer.sql
  V3__add_customer_phone.sql
  V4__add_order_status.sql
  R__customer_summary_view.sql
~~~

### 32.1. V1

~~~sql
CREATE SCHEMA IF NOT EXISTS app;
~~~

### 32.2. V2

~~~sql
CREATE TABLE app.customer (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

### 32.3. V3

~~~sql
ALTER TABLE app.customer
ADD COLUMN phone_number text;
~~~

### 32.4. V4

~~~sql
ALTER TABLE app.orders
ADD COLUMN status text;
~~~

### 32.5. Repeatable view

~~~sql
CREATE OR REPLACE VIEW app.customer_summary AS
SELECT customer_id, email
FROM app.customer;
~~~

### 32.6. CI

~~~bash
flyway validate
flyway info
flyway migrate
flyway validate
~~~

Chạy trong test database disposable. Production runner dùng cùng artifact/config được review, với target credentials và deployment gate phù hợp.

## 33. Ví dụ quy trình Liquibase

Một root changelog có thể include changesets theo release:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/001-create-schema.yaml
  - include:
      file: db/changelog/002-create-customer.yaml
  - include:
      file: db/changelog/003-add-customer-phone.yaml
~~~

### 33.1. Changeset

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: platform
      changes:
        - createTable:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: customer_id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: text
                  constraints:
                    nullable: false
~~~

### 33.2. PostgreSQL-specific SQL

Với cú pháp/feature đặc thù, dùng sql/sqlFile changeset để kiểm soát câu lệnh chính xác.

### 33.3. Preview

~~~bash
liquibase validate
liquibase status
liquibase updateSQL
~~~

Review SQL output trước khi thực hiện update trên PostgreSQL.

### 33.4. Apply test

~~~bash
liquibase update
liquibase status
~~~

### 33.5. Rollback review

~~~bash
liquibase rollbackSQL <tag-or-count>
~~~

Cú pháp command/arguments tùy Liquibase version. Xác nhận rollback block và SQL generated trên database test.

## 34. Bảng so sánh lựa chọn công cụ

| Tình huống | Cân nhắc |
| --- | --- |
| Team dùng SQL-first và PostgreSQL-only | Flyway hoặc Liquibase formatted SQL |
| Cần changeset metadata phong phú | Liquibase |
| Cần repeatable view/function scripts | Flyway repeatable migrations hoặc Liquibase changesets được thiết kế tương đương |
| Cần SQL PostgreSQL-specific | Cả hai đều có thể chạy raw SQL |
| Cần rollback khai báo | Liquibase rollback blocks hoặc Flyway undo khi edition/version hỗ trợ |
| Nhiều database engines | Liquibase abstraction có thể hữu ích, nhưng phải review generated SQL |
| CI đơn giản, versioned SQL | Flyway thường dễ tổ chức |
| Schema drift giữa môi trường | Cả hai cần validate/history plus schema inspection |
| Data backfill rất lớn | Tách job riêng, không phụ thuộc tool |
| Online index creation | Cả hai cần xử lý non-transactional migration đúng cách |

## 35. Bài tập thực hành

Các bài tập thực hiện trên PostgreSQL test database riêng. Không chạy clean, drop schema hoặc thử rollback destructive trên production.

### Bài 1. Migration

Vì sao schema changes nên được lưu thành migration files?

### Bài 2. Flyway

Flyway versioned migration có naming convention cơ bản nào?

### Bài 3. Repeatable

Repeatable migration phù hợp với loại database objects nào?

### Bài 4. Checksum

Checksum giúp phát hiện vấn đề gì?

### Bài 5. History

Flyway lưu lịch sử migration trong bảng nào theo mặc định?

### Bài 6. Validate

flyway validate làm gì và không chứng minh điều gì?

### Bài 7. Repair

Vì sao flyway repair không phải lệnh sửa schema?

### Bài 8. Baseline

Baseline dùng khi nào?

### Bài 9. Clean

Vì sao không chạy flyway clean trên production?

### Bài 10. Liquibase

Một changeset được định danh bởi các trường nào?

### Bài 11. DATABASECHANGELOG

Bảng này lưu thông tin gì?

### Bài 12. DATABASECHANGELOGLOCK

Bảng lock có vai trò gì?

### Bài 13. Preconditions

Preconditions dùng để làm gì?

### Bài 14. Contexts

Contexts/labels ảnh hưởng cách chọn changesets ra sao?

### Bài 15. Rollback

Vì sao không phải mọi changeset đều rollback tự động an toàn?

### Bài 16. Transactional DDL

PostgreSQL hỗ trợ transactional DDL có nghĩa gì?

### Bài 17. Concurrent index

Vì sao CREATE INDEX CONCURRENTLY cần migration ngoài transaction?

### Bài 18. VACUUM

Có thể chạy VACUUM trong transaction block thông thường không?

### Bài 19. Lock timeout

Viết SQL đặt lock_timeout bằng 3 giây.

### Bài 20. Statement timeout

statement_timeout khác lock_timeout như thế nào?

### Bài 21. Expand-contract

Nêu các giai đoạn của expand-contract deployment.

### Bài 22. Rename column

Vì sao không nên rename/drop column ngay trong release đầu tiên?

### Bài 23. Backfill

Vì sao nên chia backfill lớn thành batches?

### Bài 24. Resume

Một backfill có thể resume cần đặc điểm gì?

### Bài 25. NOT VALID

CHECK NOT VALID cho phép tách hai bước nào?

### Bài 26. Index failure

Sau CREATE INDEX CONCURRENTLY thất bại, cần kiểm tra gì?

### Bài 27. Fresh test

Fresh database test phát hiện loại lỗi nào?

### Bài 28. Upgrade test

Vì sao phải test từ schema/data version cũ?

### Bài 29. Data assertion

Kể bốn loại data invariants có thể kiểm tra.

### Bài 30. Migration runner

Vì sao production thường nên có một migration runner được serialize?

### Bài 31. Schema drift

Schema drift xảy ra khi nào?

### Bài 32. Manual hotfix

DBA hotfix trực tiếp production cần làm gì để giữ migration history nhất quán?

### Bài 33. Role separation

Vì sao tách migration role và application runtime role?

### Bài 34. Search path

Vì sao nên schema-qualify object names?

### Bài 35. Liquibase preview

Lệnh nào sinh SQL dự kiến mà không thực thi changesets?

### Bài 36. Flyway repeatable

Khi nào repeatable migration được chạy lại?

### Bài 37. Enum

Vì sao thêm enum value và dùng value đó cần được tách bước/commit phù hợp?

### Bài 38. Rollback boundary

Khi nào forward fix thường phù hợp hơn rollback?

### Bài 39. Production monitoring

Kể năm signals cần theo dõi trong lúc migration chạy.

### Bài 40. Quy trình

Đề xuất pipeline CI/CD kiểm tra và triển khai migration PostgreSQL.

## 36. Lời giải tham khảo

### Bài 1–9. Flyway

Migration files giúp version hóa, review, tái tạo schema và áp dụng nhất quán. Flyway versioned file thường có dạng V1__description.sql. Repeatable phù hợp view/function/procedure definitions được chạy lại khi nội dung thay đổi. Checksum phát hiện migration file đã bị sửa sau khi áp dụng. History table mặc định là flyway_schema_history. validate so sánh artifact với metadata history nhưng không chứng minh mọi schema objects/data đúng. repair sửa metadata history theo tool semantics chứ không chạy SQL để sửa schema. Baseline đánh dấu điểm bắt đầu quản lý database hiện hữu. clean phá hủy schemas/objects theo cấu hình nên không dùng production.

### Bài 10–15. Liquibase

Changeset identity gồm id, author và changelog path. DATABASECHANGELOG lưu changesets đã thực thi và metadata/checksum. DATABASECHANGELOGLOCK phối hợp chỉ một process update tại một thời điểm. Preconditions kiểm tra database state trước changeset. Contexts/labels lọc changesets theo môi trường/component/release. Rollback có thể không đảo ngược được data loss, external side effects hoặc raw SQL không có rollback definition.

### Bài 16–20. PostgreSQL transactions và locks

Transactional DDL cho phép rollback nhiều schema changes cùng transaction. CREATE INDEX CONCURRENTLY không chạy trong transaction block và cần migration execution mode phù hợp. VACUUM không chạy trong transaction block thông thường.

~~~sql
SET lock_timeout = '3s';
~~~

lock_timeout giới hạn thời gian chờ lock; statement_timeout giới hạn tổng thời gian statement.

### Bài 21–26. Deployment và backfill

Expand-contract gồm expand schema, deploy app tương thích, backfill, switch reads/writes, stop old usage rồi contract/drop object cũ. Rename/drop ngay có thể làm app instances cũ lỗi. Batch backfill giảm transaction duration, lock/WAL bursts và cho phép throttling. Resume cần checkpoint hoặc predicate để chỉ xử lý rows chưa hoàn tất. NOT VALID tách add constraint và validate dữ liệu cũ. Sau concurrent index failure, kiểm tra pg_index.indisvalid/indisready và cleanup invalid index có kiểm soát.

### Bài 27–34. Kiểm thử và quản trị

Fresh test phát hiện migration chain không dựng được schema. Upgrade test phát hiện dữ liệu cũ, duplicates, NULLs và dependencies. Data invariants gồm counts, sums, uniqueness, referential integrity, non-NULL và domain-specific rules. Một runner giúp serialize và audit. Schema drift do thay đổi ngoài migration history hoặc artifact khác nhau. Hotfix phải được ghi nhận bằng corrective migration. Tách roles để application không có DDL quyền rộng. Schema-qualify để tránh search_path tạo object sai schema.

### Bài 35–40. Pipeline và vận hành

liquibase updateSQL sinh SQL preview. Flyway repeatable chạy lại khi checksum thay đổi. Enum value mới chỉ được dùng sau khi transaction thêm value đã commit theo PostgreSQL semantics. Forward fix phù hợp khi rollback không thể đảo ngược data hoặc có side effects. Theo dõi migration duration, lock waits, active blockers, CPU/I/O, WAL/replication lag, disk và application errors.

Pipeline: review SQL/changelog; validate tool metadata; chạy fresh database; chạy upgrade fixture; assert schema/data; test app compatibility; đo lock/runtime/WAL; deploy staging; approve; chạy một production migration runner; smoke test và monitor; lưu evidence/release ID.

## 37. Bảng tra cứu nhanh

| Nhu cầu | Flyway | Liquibase / PostgreSQL |
| --- | --- | --- |
| Versioned change | V1__name.sql | Changeset id/author |
| Repeatable definition | R__name.sql | Changelog changeset được thiết kế phù hợp |
| History | flyway_schema_history | DATABASECHANGELOG |
| Migration lock | Flyway coordination | DATABASECHANGELOGLOCK |
| Pending changes | info | status |
| Metadata validation | validate | validate |
| Apply changes | migrate | update |
| SQL preview | Cơ chế preview/version-specific | updateSQL |
| Repair metadata | repair | clearCheckSums chỉ theo policy |
| Baseline existing DB | baseline | Changelog baseline/tag/mark-ran workflow |
| Rollback | Undo nếu hỗ trợ; thường forward fix | rollback block/commands |
| Non-transactional SQL | Per-migration transaction config | runInTransaction=false |
| PostgreSQL index online | CREATE INDEX CONCURRENTLY | Raw SQL changeset ngoài transaction |
| Lock safety | lock_timeout trong SQL | lock_timeout trong SQL |
| Schema inspect | Catalog/pg_dump | Catalog/diff |
| Data backfill | Job riêng | Job riêng |
| CI validation | Fresh + upgrade tests | validate + updateSQL + execution tests |

## 38. Checklist kiểm tra và triển khai migration

1. Mỗi migration có mục đích và owner rõ ràng.
2. Version/changeset identity không bị tái sử dụng.
3. Không sửa file đã áp dụng trên môi trường dùng chung.
4. Schema-qualified names được dùng nhất quán.
5. Dependencies giữa schemas, tables, types, functions và triggers đã rõ.
6. PostgreSQL version/extension compatibility được xác nhận.
7. Transaction behavior của từng statement được kiểm tra.
8. Non-transactional operations được tách riêng.
9. CREATE INDEX CONCURRENTLY không nằm trong transaction block.
10. Lock impact và lock_timeout được đánh giá.
11. statement_timeout phù hợp operation.
12. Large table rewrites/backfills được tách và ước lượng.
13. DDL tương thích với app versions trong rolling deployment.
14. Expand-contract được dùng khi cần compatibility window.
15. Backfill có batch, checkpoint, throttling và validation.
16. Constraints được validate theo kế hoạch.
17. Fresh database test pass.
18. Upgrade-path test từ schema/data cũ pass.
19. Schema assertions pass.
20. Data invariants pass.
21. Indexes/constraints/permissions/ownership được kiểm tra.
22. Application integration tests pass.
23. Liquibase generated SQL hoặc Flyway artifact được review.
24. Checksum/history state hợp lệ.
25. Không có schema drift chưa giải thích.
26. Một production migration runner được serialize.
27. Migration credentials được bảo vệ và tách khỏi runtime role.
28. Backup/restore và recovery options được đánh giá.
29. Stop conditions và rollback/forward-fix plan được ghi.
30. Theo dõi locks, blockers, runtime, CPU, I/O, WAL và disk.
31. Theo dõi replication lag nếu có standbys.
32. Smoke tests sau migration pass.
33. Release ID, commit SHA và history state được lưu.
34. Destructive contract changes chỉ chạy khi old application usage đã hết.
35. Cleanup/retire artifacts chỉ sau khi migration ổn định.

## 39. Tổng kết

Flyway và Liquibase cung cấp cơ chế quản lý lịch sử schema changes, checksum, thứ tự thực thi và phối hợp migration runners. Flyway thường tổ chức SQL files thành versioned và repeatable migrations; Liquibase tổ chức changelog thành changesets có id/author, preconditions, contexts/labels và rollback metadata. Cả hai đều có thể chạy SQL PostgreSQL-specific khi cần.

Công cụ không thể tự quyết định một DDL an toàn cho production. PostgreSQL có transactional DDL cho nhiều operations nhưng một số lệnh như CREATE INDEX CONCURRENTLY, VACUUM và CREATE DATABASE không chạy trong transaction block thông thường. ALTER TABLE có thể chờ lock hoặc làm thay đổi lớn trên bảng. Dùng lock_timeout, statement_timeout, online index strategies, NOT VALID/VALIDATE CONSTRAINT và staging measurements để giảm rủi ro.

Với ứng dụng rolling deployment, expand-contract giữ schema tương thích qua nhiều phiên bản: mở rộng schema, deploy code mới, backfill, chuyển reads/writes rồi mới loại bỏ cấu trúc cũ. Backfill lớn cần batch, checkpoint và throttling. Migration test phải bao gồm cả database rỗng và upgrade từ schema/data cũ, sau đó kiểm tra catalog, data invariants, permissions, application behavior và lock impact.

Trong production, serialize migration runner, bảo vệ credentials, review SQL generated và theo dõi blockers, WAL, replication lag, disk cùng application errors. Nếu migration đã chạy, tạo migration mới để sửa thay vì viết lại lịch sử. Khi rollback không thể khôi phục dữ liệu hoặc side effects, dùng forward fix và recovery plan đã chuẩn bị. Một pipeline có kiểm tra lặp lại và release evidence sẽ giúp schema changes trở thành một phần có thể kiểm soát của vòng đời ứng dụng.
