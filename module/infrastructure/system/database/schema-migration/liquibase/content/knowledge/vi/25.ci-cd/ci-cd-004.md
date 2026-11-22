# Rà soát, phê duyệt và lưu SQL dự kiến triển khai

Trong chương **CI/CD** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, SQL dự kiến triển khai là đầu vào quan trọng để reviewer hiểu chính xác database sẽ thay đổi thế nào trước khi migration được thực thi. Changelog mô tả ý định thay đổi; lệnh `update-sql` chuyển các changeset đang chờ thành SQL theo trạng thái database, DBMS, bộ lọc và cấu hình tại thời điểm sinh. Việc rà soát, phê duyệt và lưu bản SQL đó giúp nhóm phát hiện thao tác nguy hiểm, đối chiếu khác biệt giữa các môi trường và giữ bằng chứng gắn với release.

Phạm vi của dịch vụ **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài học tập trung vào việc rà soát, phê duyệt và lưu SQL dự kiến triển khai như một cổng kiểm soát trong quy trình phát hành.

Định hướng đầy đủ của dịch vụ: Nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Mục tiêu là reviewer có thể trả lời trước khi phê duyệt: SQL này được sinh từ artifact nào, dành cho database/DBMS nào, changeset nào sẽ chạy, có thao tác phá hủy hay lock dài không, điều kiện thực thi có đúng không, và bản SQL được duyệt có còn tương ứng với lần triển khai thực tế hay không.

## 1. Phân biệt changelog, SQL dự kiến và SQL đã thực thi

Ba loại nội dung có vai trò khác nhau:

| Thành phần | Ý nghĩa | Câu hỏi nó trả lời |
|---|---|---|
| Changelog | Mô tả changeset và ý định thay đổi có phiên bản | Dự án yêu cầu thay đổi gì? |
| SQL dự kiến (`update-sql`) | SQL Liquibase sinh ra cho trạng thái DB/config hiện tại | Nếu chạy update với đầu vào này, Liquibase dự kiến gửi SQL nào? |
| SQL thực thi và history | Câu lệnh thực tế cùng kết quả ghi nhận trong database/log | Điều gì đã xảy ra trên database? |

Changelog không phải SQL cuối cùng. Cùng một changeset có thể sinh SQL khác nhau theo DBMS. Cùng một DBMS cũng có thể tạo tập SQL khác nhau nếu database đã có changeset khác nhau, context/label khác nhau, parameter khác nhau hoặc precondition cho kết quả khác.

SQL dự kiến không chứng minh migration đã chạy. `update-sql` chỉ sinh script để xem xét; nó không áp dụng thay đổi. Sau khi chạy `update`, phải kiểm tra log, DATABASECHANGELOG, schema và dữ liệu thực tế.

Một bản SQL được phê duyệt cũng không tự động bảo đảm lần chạy sau vẫn giống hệt. Nếu artifact, cấu hình, filter hoặc trạng thái database thay đổi, SQL có thể khác. Vì vậy, cần ràng buộc phê duyệt với đúng artifact và điều kiện triển khai.

## 2. SQL preview nằm ở đâu trong pipeline?

Một pipeline có thể tổ chức theo trình tự:

~~~text
Pull request
    |
Review changelog và changeset
    |
Build artifact bất biến
    |
Validate + kiểm tra dependency
    |
Chọn DBMS / environment / filters
    |
Liquibase status
    |
Liquibase update-sql
    |
Lưu SQL preview + manifest
    |
Review SQL và đánh giá rủi ro
    |
Approval gắn với artifact/preview
    |
Kiểm tra freshness trước triển khai
    |
Liquibase update
    |
Đối chiếu history + schema + data
    |
Lưu deployment evidence
~~~

Các bước có thể được chia thành nhiều job, nhưng phải giữ được một định danh release xuyên suốt. Pipeline nên sinh preview cho đúng DBMS và cấu hình mục tiêu; một file SQL cho PostgreSQL không thể đại diện cho SQL của MySQL hoặc SQL Server.

Không nên chạy migration production ngay khi pull request được merge nếu quy trình yêu cầu review SQL và approval riêng. Preview cần được tạo, lưu và duyệt trước khi cấp quyền thực thi production.

## 3. Xác định đầy đủ đầu vào trước khi sinh SQL

SQL preview chỉ có ý nghĩa khi biết chính xác đầu vào. Một manifest tối thiểu nên xác định:

- Repository, commit SHA và artifact digest.
- Phiên bản changelog/master changelog.
- Phiên bản Liquibase, Java, JDBC driver và extension.
- DBMS và phiên bản engine.
- Database alias, schema đích và default schema.
- Context, label filter và dbms filter.
- Changelog parameters không nhạy cảm.
- Các tùy chọn liên quan transaction hoặc command.
- Thời điểm sinh preview.
- Trạng thái DATABASECHANGELOG tại thời điểm đó.
- Deployment ID và job attempt.

Ví dụ manifest minh họa:

~~~yaml
deployment:
  id: deploy-20261119-1842
  environment: staging
  release: customer-service-4.8.0
  commit: a1b2c3d
  artifactDigest: sha256:example-digest
database:
  target: customer-service-staging
  dbms: postgresql
  version: "16"
  defaultSchema: app
liquibase:
  version: "pinned-version"
  changeLog: db/changelog/db.changelog-master.yaml
  contexts: staging
  labels: release-4.8
  parameters:
    appSchema: app
preview:
  command: update-sql
  generatedAt: "2026-11-19T10:42:31Z"
~~~

Giá trị trên chỉ là ví dụ, không phải cấu hình mặc định. Không đưa password, token hoặc JDBC URL chứa credentials vào manifest. Nếu tên database/schema là thông tin nhạy cảm, dùng alias đã được phân loại theo chính sách tổ chức.

Không ghi một giá trị chung như "production" mà thiếu DBMS/version nếu hệ thống hỗ trợ nhiều engine. Reviewer phải biết bản SQL được sinh cho mục tiêu nào.

## 4. Kiểm tra changelog trước khi sinh SQL

Trước preview, cần kiểm tra:
- Master changelog đúng entry point.
- Các tệp include có trong artifact.
- Không có file draft/backup bị include ngoài ý muốn.
- ID/AUTHOR/FILENAME ổn định.
- Changeset đã triển khai không bị sửa.
- Checksum phù hợp với DATABASECHANGELOG.
- Context/label/dbms filter đúng.
- Parameter được allowlist và validate.
- Preconditions có ý nghĩa và không bị dùng để che lỗi.
- Rollback được khai báo hoặc giới hạn không thể đảo ngược được ghi rõ.

Có thể chạy:

~~~bash
liquibase validate
liquibase status --verbose
~~~

`validate` kiểm tra các vấn đề về changelog mà phiên bản Liquibase hỗ trợ phát hiện. `status --verbose` giúp xem changeset nào còn pending theo database và filter hiện tại. Kết quả phụ thuộc phiên bản, cấu hình và trạng thái DB.

Validate thành công không chứng minh SQL runtime chắc chắn thành công. Nó không thay thế review generated SQL, quyền database, test dữ liệu hoặc kiểm tra lock.

Nếu status không liệt kê changeset mong đợi, dừng quy trình preview để kiểm tra master include, context/label, dbms filter, logical path và database đích. Không phê duyệt một SQL file thiếu changeset chỉ vì command exit code bằng 0.

## 5. Sinh SQL bằng update-sql

Sau khi xác nhận đúng đầu vào, sinh SQL dự kiến:

~~~bash
liquibase update-sql
~~~

Trong CLI, changelog, URL, driver, credentials, context, label và parameter có thể được truyền qua properties hoặc command options. Dùng đúng cú pháp của phiên bản đã pin.

Ví dụ một lần chạy có cấu hình tường minh:

~~~bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --url=jdbc:postgresql://db.example.internal:5432/customer_service \
  --username=migration_user \
  --driver=org.postgresql.Driver \
  --context-filter=staging \
  update-sql
~~~

Đây là ví dụ CLI; cách truyền password nên lấy từ secret provider hoặc cơ chế an toàn của runner, không đặt secret vào command line nếu process list hoặc log có thể làm lộ. Tên option context/label có thể khác theo phiên bản Liquibase; kiểm tra `liquibase help` và tài liệu đúng phiên bản.

Có thể redirect output vào artifact file trong pipeline, ví dụ:

~~~bash
liquibase update-sql > update-preview.sql
~~~

Cần bảo đảm runner thu được cả stdout và stderr, giữ exit code của command và không làm mất thông báo lỗi khi redirect. Nếu command thất bại, không được coi file output một phần là preview hoàn chỉnh để phê duyệt.

SQL preview phải được sinh từ cùng artifact và cấu hình sẽ dùng khi update. Không sửa file SQL sau khi sinh để "làm đẹp" mà không giữ bản gốc; nếu cần annotation cho reviewer, đặt trong review record riêng.

## 6. Sinh preview riêng cho từng DBMS và môi trường

Cùng một changelog có thể được dùng trên PostgreSQL, MySQL, SQL Server hoặc Oracle. Tuy nhiên:
- Type mapping có thể khác.
- Identity/sequence có thể khác.
- Cách tạo index online/concurrently khác.
- Transaction DDL khác.
- Identifier quoting và giới hạn tên khác.
- SQL riêng được chọn qua dbms filter.
- Precondition metadata có thể trả kết quả khác.
- Default schema/search path khác.

Vì vậy, tạo một preview cho từng tổ hợp mục tiêu được hỗ trợ.

| Mục tiêu | Artifact preview | Reviewer cần xác nhận |
|---|---|---|
| PostgreSQL staging | SQL + manifest PostgreSQL | Schema, index, sequence, lock |
| PostgreSQL production | SQL + manifest production | Filter và database state đúng |
| MySQL staging | SQL + manifest MySQL | Type mapping, index, engine behavior |
| SQL Server production | SQL + manifest SQL Server | Schema, identity, transaction/lock |
| Oracle production | SQL + manifest Oracle | Sequence, identifier, DDL behavior |

Đây là mẫu ma trận; chỉ đưa DBMS/version thực sự nằm trong support policy.

Không tái sử dụng SQL preview từ staging cho production nếu trạng thái history, parameters hoặc DBMS target khác. Dù cùng engine, preview có thể khác nếu production đã có changeset hoặc object không giống staging.

## 7. Review cấu trúc và thứ tự SQL

Reviewer cần đọc toàn bộ SQL theo thứ tự thực thi, không chỉ tìm các câu CREATE TABLE.

Kiểm tra:
1. Có tạo schema hoặc object nền trước khi dùng không?
2. Bảng cha có trước FK không?
3. Cột có trước constraint/index không?
4. Seed data có trước bước tham chiếu không?
5. Backfill có trước khi thêm NOT NULL/UNIQUE không?
6. View/routine có được tạo sau dependency không?
7. Drop/rename có xuất hiện trước khi consumer chuyển đổi không?
8. SQL DBMS-specific có bị gửi nhầm engine không?
9. Có câu lệnh ngoài phạm vi release không?
10. Có thay đổi metadata hoặc quyền ngoài dự kiến không?

Ví dụ thứ tự hợp lý:

~~~text
CREATE SCHEMA (nếu cần và được cấp quyền)
CREATE TABLE reference
CREATE TABLE customer
ADD PRIMARY KEY / FOREIGN KEY
INSERT reference data
ADD nullable column
BACKFILL data
VALIDATE data
ADD NOT NULL / UNIQUE
CREATE INDEX
CREATE OR REPLACE VIEW
~~~

Đây là thứ tự minh họa; phụ thuộc thực tế có thể khác. Không phải mọi index đều nên tạo cuối cùng, và một số index có thể cần cách tạo online riêng.

Nếu SQL preview có câu lệnh không liên quan tới thay đổi trong pull request, dừng approval và tìm nguyên nhân: includeAll nạp file ngoài dự kiến, parameter sai, database history khác hoặc artifact không đúng commit.

## 8. Nhận diện câu lệnh phá hủy hoặc khó đảo ngược

Những câu lệnh cần chú ý đặc biệt:
- DROP TABLE, DROP COLUMN.
- TRUNCATE.
- DELETE không có điều kiện hoặc phạm vi quá rộng.
- UPDATE toàn bảng.
- ALTER COLUMN thay đổi kiểu/độ dài có nguy cơ mất dữ liệu.
- SET NOT NULL khi còn dữ liệu NULL.
- Thêm UNIQUE khi dữ liệu có duplicate.
- Thay đổi primary/foreign key.
- Đổi schema/owner/grant.
- Rebuild index hoặc thao tác khóa bảng.
- Thay đổi partition, sequence hoặc identity.

Với mỗi câu lệnh, reviewer cần hỏi:
- Phạm vi hàng/object nào bị ảnh hưởng?
- Có dữ liệu nào bị xóa hoặc chuyển đổi không thể đảo ngược?
- Có cần backup hoặc snapshot không?
- Có thể chạy theo batch không?
- Có lock lâu hoặc downtime không?
- Phiên bản ứng dụng cũ có còn tương thích không?
- Rollback thực sự khôi phục được dữ liệu hay chỉ khôi phục cấu trúc?
- Có phương án forward fix nếu rollback không an toàn?

Không phê duyệt DROP/DELETE chỉ dựa trên tên changeset hoặc comment. Cần hiểu điều kiện và dữ liệu thật.

## 9. Review lock, transaction và thời gian chạy

Một câu SQL hợp lệ vẫn có thể gây sự cố vận hành do lock hoặc thời gian thực thi.

Kiểm tra:
- DDL có khóa bảng không?
- Index có thể tạo online/concurrently không?
- Engine có hỗ trợ transactional DDL cho câu lệnh đó không?
- Một changeset có gom quá nhiều thao tác không?
- UPDATE/DELETE có quét toàn bảng không?
- Có index hỗ trợ điều kiện WHERE không?
- Batch size và thời gian transaction có phù hợp không?
- Replication lag, WAL/redo/transaction log có thể tăng đến mức nào?
- Timeout của pipeline, connection và database có đủ không?
- Có thể tạm dừng hoặc resume không?

Một migration chạy nhanh trên database test rỗng có thể kéo dài nhiều giờ trên production. Preview cho biết câu lệnh, nhưng execution plan và thời gian thực tế cần test với dữ liệu đại diện hoặc môi trường tương đương.

Nếu có thay đổi rủi ro cao, cần DBA hoặc database owner review và xác nhận maintenance window/online strategy trước approval.

## 10. Review dữ liệu và điều kiện precondition

SQL preview cần được đối chiếu với precondition trong changelog. Ví dụ:

~~~yaml
preConditions:
  - onFail: HALT
  - sqlCheck:
      expectedResult: "0"
      sql: |
        SELECT COUNT(*)
        FROM app.customer
        WHERE email IS NULL
~~~

Reviewer cần biết:
- Precondition được đánh giá trên database nào.
- Nó chạy ở cấp changelog hay changeset.
- onFail/onError là gì.
- Nếu không đạt, Liquibase dừng, cảnh báo hay đánh dấu changeset?
- Truy vấn có tốn kém không?
- Kết quả có thể thay đổi giữa preview và execution không?

Precondition không phải lúc nào cũng được biểu diễn đầy đủ trong SQL output. Một số điều kiện được Liquibase đánh giá trước khi thực thi change. Vì vậy, reviewer phải đọc cả changelog và SQL preview.

Không coi `update-sql` là bằng chứng mọi precondition chắc chắn đạt tại thời điểm update sau đó. Database có thể thay đổi giữa hai lần chạy. Với điều kiện quan trọng, kiểm tra lại gần thời điểm thực thi và bảo đảm không có writer làm thay đổi trạng thái giữa check và change.

Không dùng MARK_RAN để làm mất dấu một điều kiện chưa đạt.

## 11. Review parameter substitution và filter

Context, label, dbms và changelog parameters ảnh hưởng tập SQL được sinh.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-010-create-audit"
      author: "team-db"
      dbms: postgresql
      contextFilter: production
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

Reviewer cần xác nhận:
- DBMS filter có đúng target không?
- Context/label có chọn đúng changeset không?
- Parameter schema có nằm trong allowlist?
- Có parameter nào bị bỏ trống hoặc lấy từ nguồn không tin cậy?
- Preview có dùng cùng giá trị với execution không?
- Cấu hình profile có vô tình loại bỏ migration cần thiết không?

Không dùng tên profile làm bằng chứng duy nhất cho target database. Kiểm tra URL/alias, DBMS metadata và effective filters. Không đưa secret vào parameter hoặc manifest.

## 12. Review rollback SQL riêng biệt

Nếu changeset có rollback, sinh SQL rollback để xem xét khi quy trình cần đánh giá khả năng phục hồi:

~~~bash
liquibase rollback-sql --tag=release-before-change
~~~

Tên option và cách chọn rollback target phụ thuộc phiên bản Liquibase. Cần xác minh tag tồn tại, tag được đặt ở đúng mốc và rollback scope đúng dự định.

Rollback SQL cần được review riêng:
- Có drop dữ liệu không?
- Có mất dữ liệu được ghi sau migration không?
- Có khôi phục chính xác giá trị trước đó không?
- Có dependency được tạo sau changeset không?
- Có thể rollback trong khi ứng dụng mới vẫn chạy không?
- Có DDL không transactional không?
- Có cần backup/restore thay vì rollback logic không?

Rollback SQL chỉ là kế hoạch hoàn tác được sinh ra; không chứng minh thao tác rollback an toàn trong production. Một changeset có rollback dropColumn có thể xóa toàn bộ dữ liệu đã ghi vào cột mới.

Với thay đổi không thể đảo ngược, ghi rõ forward fix/restore plan. Không khai báo rollback giả chỉ để pipeline có một file SQL.

## 13. Checklist review SQL theo nhóm thay đổi

| Nhóm | Điểm cần kiểm tra |
|---|---|
| CREATE TABLE | Schema, type, nullability, PK, default, owner |
| ADD COLUMN | Nullable/default, backfill, compatibility |
| DROP/RENAME | Consumer cũ, dữ liệu mất, rollout nhiều giai đoạn |
| ALTER TYPE | Cast, truncation, precision, lock |
| FOREIGN KEY | Dữ liệu mồ côi, validation, index hỗ trợ |
| UNIQUE | Duplicate, collation, NULL semantics |
| INDEX | Kích thước, online strategy, lock, query benefit |
| UPDATE/DELETE | Điều kiện WHERE, số hàng, batch, transaction |
| SEED | Idempotency, unique key, môi trường, dữ liệu nhạy cảm |
| VIEW/ROUTINE | Dependency, quyền, cú pháp DBMS |
| GRANT/REVOKE | Principal, phạm vi và least privilege |
| DROP/TRUNCATE | Backup, phê duyệt đặc biệt, recovery |

Reviewer không chỉ xác nhận SQL parse được. Cần xác nhận thay đổi đúng nghiệp vụ, đúng môi trường và phù hợp với chiến lược triển khai.

## 14. Quy trình approval và phân tách trách nhiệm

Một quy trình approval nên phân biệt:
- Người tạo changeset.
- Reviewer kỹ thuật.
- DBA/database owner đối với thay đổi rủi ro cao.
- Người phê duyệt production.
- Service identity thực thi migration.
- Người xác minh kết quả sau triển khai.

Approval nên gắn với:
- Deployment ID.
- Commit SHA.
- Artifact digest.
- SQL preview digest.
- DBMS/version và target alias.
- Context/label/parameters.
- Người phê duyệt và thời điểm.
- Phạm vi được phép thực thi.

Không dùng một approval chung cho mọi database hoặc mọi bản SQL. Preview PostgreSQL staging không phê duyệt SQL Oracle production. Nếu SQL hoặc manifest thay đổi sau approval, approval cũ phải hết hiệu lực và quy trình review cần chạy lại.

Với thao tác phá hủy, thay đổi quyền hoặc migration có nguy cơ downtime, yêu cầu reviewer/approver có chuyên môn và quyền hạn phù hợp. Không để tác giả tự phê duyệt mọi bước nếu chính sách yêu cầu kiểm soát độc lập.

## 15. Gắn approval với artifact bất biến

SQL preview cần được liên kết với artifact changelog đã build. Một cách làm:
1. Build changelog artifact từ commit đã review.
2. Tính digest artifact.
3. Sinh SQL preview từ artifact đó.
4. Tính digest file SQL và manifest.
5. Lưu ba thành phần cùng nhau.
6. Approval tham chiếu các digest.
7. Deployment job kiểm tra lại digest trước khi chạy.

Ví dụ manifest:

~~~yaml
approval:
  deploymentId: deploy-20261119-1842
  artifactDigest: sha256:artifact-digest
  sqlDigest: sha256:sql-preview-digest
  manifestDigest: sha256:manifest-digest
  target: customer-service-prod
  dbms: postgresql
  reviewer: database-reviewer
  approvedAt: "2026-11-19T11:00:00Z"
  decision: approved
~~~

Digest minh họa không phải giá trị thực. Có thể dùng SHA-256 hoặc cơ chế integrity/signature theo chuẩn tổ chức. Không tự tạo checksum từ một file khác sau approval mà không cập nhật approval record.

Artifact bất biến giúp chứng minh reviewer đã xem đúng nội dung được triển khai. Nếu pipeline build lại changelog từ branch đã thay đổi, cần tạo preview và approval mới.

## 16. Lưu SQL preview ở đâu và theo cấu trúc nào?

SQL preview là deployment artifact. Nên lưu trong artifact repository hoặc hệ thống lưu trữ CI/CD có:
- Phân quyền đọc/ghi/xóa rõ ràng.
- Versioning hoặc immutable retention nếu cần.
- Mã hóa khi truyền và lưu.
- Audit truy cập.
- Retention theo môi trường và chính sách.
- Liên kết với job, commit, approval và deployment record.

Ví dụ cấu trúc thư mục artifact:

~~~text
migration-review/
  customer-service/
    4.8.0/
      deploy-20261119-1842/
        manifest.yaml
        update-preview.sql
        rollback-preview.sql
        validate.log
        status.log
        review-record.md
        checksums.txt
~~~

Đây là cấu trúc minh họa. Không nên lưu artifact chỉ trong workspace tạm hoặc filesystem ephemeral của runner. Nếu job/pod bị xóa, bằng chứng phải còn trong kho đã cấu hình.

Tên file nên chứa target/DBMS hoặc manifest phải ghi rõ target. Tránh tên chung như update.sql nếu nhiều môi trường cùng dùng một bucket.

Không lưu credentials trong SQL preview hoặc manifest. Giới hạn quyền xem SQL vì nội dung có thể tiết lộ tên bảng, cột, logic nghiệp vụ và cấu trúc nội bộ.

## 17. Bảo vệ SQL preview và manifest

SQL preview có thể chứa:
- Tên schema/table/column nội bộ.
- Literal trong INSERT/UPDATE.
- Dữ liệu seed.
- Logic nghiệp vụ trong view/routine.
- Tên user/role và quyền.
- Đường dẫn hoặc thông tin môi trường.

Biện pháp:
- Không công khai artifact.
- Redact secret và dữ liệu cá nhân nếu xuất hiện.
- Giới hạn người xem theo môi trường.
- Không gửi file nguyên bản qua kênh chat/ticket không được phép.
- Ghi audit khi tải xuống/xóa.
- Không đưa password vào command option được lưu trong log.
- Dùng secret store khi kết nối database.
- Có retention riêng cho preview và debug output.

Redaction cần thận trọng: sửa SQL preview sau khi sinh có thể làm file không còn là bản SQL nguyên gốc được Liquibase tạo. Nếu cần chia sẻ bản đã che dữ liệu, giữ bản gốc trong kho có kiểm soát và lưu một bản redacted riêng với quan hệ rõ ràng; không dùng bản redacted làm SQL thực thi.

## 18. Freshness: khi nào preview không còn hợp lệ?

SQL preview phản ánh trạng thái database và cấu hình tại thời điểm sinh. Nó có thể lỗi thời khi:
- Một migration khác chạy sau preview.
- Một DBA thay đổi schema trực tiếp.
- DATABASECHANGELOG thay đổi.
- Một job khác tạo hoặc xóa object.
- Context/label/parameter thay đổi.
- Artifact hoặc extension được cập nhật.
- DBMS được nâng phiên bản.
- Một precondition đổi kết quả do dữ liệu thay đổi.

Trước khi triển khai:
1. Xác minh artifact digest vẫn giống bản được duyệt.
2. Xác minh target alias và DBMS/version.
3. Xác minh context/label/parameter.
4. Chạy status lại để xem changeset pending.
5. Kiểm tra không có migration job khác đang cập nhật database.
6. Xem lại thay đổi schema/history kể từ preview.
7. Nếu trạng thái thay đổi, sinh preview mới và review lại.

Đối với môi trường có thay đổi liên tục, thời hạn hiệu lực preview nên ngắn và được quy định. Không phê duyệt một file SQL cũ rồi chạy update nhiều ngày sau mà không kiểm tra trạng thái database.

## 19. Không thực thi SQL preview thủ công một cách tùy tiện

Mặc định, sau khi review SQL preview, pipeline nên thực thi migration bằng Liquibase `update` với cùng artifact và cấu hình đã được phê duyệt. Liquibase chịu trách nhiệm quản lý changeset và ghi lịch sử tương ứng.

Nếu lấy file update-sql rồi chạy bằng một công cụ SQL bên ngoài:
- Database có thể thay đổi nhưng DATABASECHANGELOG không được cập nhật như Liquibase mong đợi.
- Lần Liquibase update sau có thể cố chạy lại changeset.
- Checksum/history có thể không phản ánh hành động thực tế.
- Cách xử lý transaction và lock có thể khác.
- Các statement phụ trợ của Liquibase có thể không được quản lý đúng.

Chỉ dùng quy trình thực thi SQL bên ngoài nếu tổ chức có thiết kế rõ để đồng bộ history và lock, có kiểm thử trên DBMS mục tiêu, có approval đặc biệt và có runbook reconcile. Không coi việc chạy file SQL bằng psql/sqlcmd/SQL client là tương đương tự động với Liquibase update.

Review SQL preview không đồng nghĩa bắt buộc phải chạy file preview bằng tay. Preview là bằng chứng để phê duyệt; execution path cần được xác định riêng.

## 20. Bảo đảm preview và execution dùng cùng cấu hình

Một nguyên nhân sai lệch phổ biến là preview chạy với cấu hình khác execution:

| Thành phần | Preview | Execution cần khớp |
|---|---|---|
| Changelog artifact | Digest A | Digest A |
| Liquibase version | Version X | Version X |
| JDBC driver | Version Y | Version Y |
| DBMS/target | PostgreSQL staging | Cùng target đã duyệt |
| Context | staging | Cùng filter |
| Label | release-4.8 | Cùng filter |
| Parameters | appSchema=app | Cùng giá trị |
| Changelog path | Master A | Master A |
| Extension | Version E | Version E |

Nếu tổ chức cố ý dùng cùng changelog artifact nhưng thay target environment, cần sinh preview riêng cho từng target. Không thể dùng một preview staging làm approval cho production khi dữ liệu/history production khác.

Cấu hình nên được lấy từ một manifest bất biến hoặc deployment definition có version. Không để job preview và job execution tự đọc hai bộ biến môi trường không được đối chiếu.

## 21. Kiểm tra thay đổi giữa preview và execution

Trước update, pipeline có thể chạy lại:
- `validate`.
- `status --verbose`.
- Kiểm tra artifact digest.
- Kiểm tra DBMS metadata.
- Kiểm tra migration lock/runner ownership.
- Kiểm tra các precondition quan trọng theo cơ chế phù hợp.

Nếu tập changeset pending khác với preview đã duyệt, dừng deployment. Sinh SQL mới và yêu cầu review lại nếu thay đổi có ảnh hưởng đến nội dung được phê duyệt.

Không nên cố so sánh toàn bộ file SQL bằng chuỗi nếu output có timestamp/comment không ổn định; hãy xác định cách canonicalize hoặc so sánh digest theo đúng artifact được lưu. Không bỏ qua khác biệt câu lệnh thực thi chỉ vì metadata khác.

Approval phải hết hiệu lực khi nội dung SQL, artifact hoặc cấu hình quan trọng thay đổi.

## 22. Kiểm tra nhiều lần sinh preview

Một cách kiểm tra tính ổn định là sinh preview hai lần trên cùng trạng thái database và cùng cấu hình trong môi trường test cô lập.

Mục tiêu:
- Cùng artifact và DB state cho tập SQL tương đương.
- Không có timestamp hoặc giá trị ngẫu nhiên ảnh hưởng semantics.
- Context/label chọn cùng changeset.
- Parameter substitution giống nhau.
- Không phụ thuộc file local hoặc hostname.
- Extension sinh kết quả xác định.

Không phải mọi dòng output nhất thiết giống byte-for-byte; có thể có comment, header hoặc metadata thời gian. Điều cần so sánh là nội dung SQL và phạm vi changeset. Nếu khác biệt có ý nghĩa, điều tra trước khi đưa vào approval.

Tính xác định đặc biệt quan trọng khi changelog dùng custom extension, SQL động hoặc includeAll.

## 23. Review generated SQL trong pull request

Một cách làm hữu ích là đính kèm preview vào pull request hoặc trang review nội bộ, kèm:
- Tóm tắt changeset mới.
- SQL preview theo DBMS mục tiêu.
- Link changelog source.
- Kết quả test fresh install và upgrade.
- Kết quả rollback test hoặc giải thích giới hạn.
- Rủi ro lock/downtime.
- Số lượng dữ liệu dự kiến ảnh hưởng nếu có.
- Approver cần thiết.

Reviewer nên xem cả changelog và SQL. Changelog giải thích ý định; SQL giúp thấy câu lệnh cụ thể được sinh. Nếu SQL không phản ánh ý định, không sửa file SQL preview để che khác biệt; sửa changelog/config và sinh lại.

Với thay đổi đơn giản, review có thể nằm trong pull request. Với production/high-risk, nên có approval deployment riêng sau khi preview được sinh cho đúng target.

## 24. Tự động hóa policy checks trước approval

Pipeline có thể kiểm tra các mẫu rủi ro:
- DROP TABLE/DROP COLUMN.
- TRUNCATE.
- DELETE/UPDATE không có WHERE.
- ALTER COLUMN có thể truncate dữ liệu.
- GRANT quyền rộng.
- SQL không có dbms filter dù chứa cú pháp đặc thù.
- Changeset không có rollback trong khi policy yêu cầu.
- includeAll trỏ vào thư mục có file ngoài quy ước.
- Parameter chưa được allowlist.
- Extension không nằm trong allowlist version.
- Preview target không khớp environment.

Policy check tự động chỉ là bộ lọc. Nó có thể tạo false positive hoặc bỏ sót SQL động, stored procedure và cú pháp đặc thù. Không thay thế review chuyên môn.

Ví dụ pipeline logic:

~~~text
if validate failed:
    stop
if artifact digest differs from reviewed build:
    stop
if target DBMS is unsupported:
    stop
if generated SQL contains destructive change:
    require elevated approval
if preview or manifest changed after approval:
    invalidate approval
if status differs from reviewed pending set:
    regenerate preview and review
otherwise:
    allow migration job
~~~

Điều kiện phải được thực thi bằng dữ liệu pipeline thực tế. Không chỉ hiển thị warning mà vẫn cho production deploy nếu policy yêu cầu block.

## 25. Lưu rollback preview và kế hoạch phục hồi

Ngoài SQL tiến lên, nên đánh giá kế hoạch rollback hoặc forward fix:

- Có thể sinh rollback SQL cho tag/count/date được chọn không?
- Changeset có rollback khai báo không?
- Rollback có xóa dữ liệu mới không?
- Có DDL không transactional không?
- Ứng dụng cũ có tương thích với schema sau rollback không?
- Có cần restore backup?
- Có thể forward fix an toàn hơn không?

Lưu rollback preview nếu chính sách yêu cầu, nhưng gắn rõ target, tag/rollback scope và thời điểm sinh. Một file rollback-sql cho tag khác không thể được dùng làm kế hoạch cho release hiện tại.

Không thực thi rollback preview trong production chỉ vì file đã được duyệt. Trạng thái database sau sự cố có thể khác với lúc sinh preview; phải kiểm tra history/schema và tạo kế hoạch phù hợp.

## 26. Approval sau khi SQL được lưu

Approval record nên chứa:
- Người review SQL.
- Người phê duyệt.
- Thời điểm.
- Deployment ID.
- Artifact digest.
- SQL preview digest.
- Manifest digest.
- Target DBMS/version/database alias.
- Context/label/parameters.
- Rủi ro đã đánh giá.
- Điều kiện triển khai và maintenance window.
- Rollback/forward recovery decision.

Nếu một reviewer chỉ bấm approve changelog trong pull request mà chưa thấy SQL preview cho target, không nên ghi nhận đó là approval SQL production nếu quy trình yêu cầu xem SQL.

Approval không nên được chuyển sang deployment khác bằng cách copy trạng thái. Nó có phạm vi artifact và target cụ thể.

## 27. Lưu trữ và truy xuất bằng chứng

Một deployment evidence bundle có thể gồm:

~~~text
deployment-id/
  manifest.yaml
  artifact-digest.txt
  update-preview.sql
  rollback-preview.sql
  validate.log
  status.log
  review-record.json
  approval-record.json
  test-results/
  execution.log
  post-deployment-checks.json
~~~

Không phải mọi deployment đều cần đủ file trên. Chọn tập bằng chứng phù hợp với rủi ro và yêu cầu audit.

Nên lưu tại artifact store hoặc CI/CD system có:
- Versioning.
- Quyền đọc/ghi/xóa tách biệt.
- Encryption.
- Audit download/delete.
- Retention policy.
- Khả năng liên kết commit và deployment.
- Bản sao độc lập với database đích.

Không chỉ lưu file SQL trong workspace runner hoặc thư mục build tạm. Nếu runner bị xóa, bằng chứng phải còn ở kho lưu trữ được quản lý.

## 28. Bảo mật SQL preview

SQL có thể tiết lộ cấu trúc dữ liệu và thông tin nội bộ. Nếu chứa literal, có thể làm lộ dữ liệu seed hoặc dữ liệu nghiệp vụ.

Thực hành:
- Không ghi credentials vào SQL hoặc command line.
- Không dùng dữ liệu cá nhân thật trong seed preview nếu không cần.
- Redact secret trước khi chia sẻ.
- Giới hạn quyền đọc artifact production.
- Không đưa SQL preview vào repository public.
- Mã hóa khi lưu/truyền.
- Ghi audit truy cập.
- Đặt retention theo chính sách.
- Giữ bản gốc bất biến nếu có bản redacted cho review rộng hơn.

Nếu redaction làm thay đổi SQL, bản redacted chỉ là bản xem xét; không được dùng để thực thi. Lưu mối liên hệ tới bản gốc có quyền truy cập hạn chế.

## 29. Điều tra khi SQL thực tế khác preview

Nếu deployment thực tế có SQL hoặc changeset khác với bản duyệt:
1. Dừng job nếu chưa hoàn tất và nếu có thể dừng an toàn.
2. Ghi deployment ID, command, artifact digest và target.
3. Bảo toàn stdout/stderr và database log.
4. So sánh manifest với preview được duyệt.
5. Kiểm tra Liquibase version, driver và extension.
6. Kiểm tra context, label, dbms filter và parameter.
7. Kiểm tra DATABASECHANGELOG và trạng thái database tại thời điểm chạy.
8. Xác định có migration khác chạy xen giữa không.
9. Xác minh schema/data đã thay đổi đến đâu.
10. Chỉ tiếp tục sau khi owner quyết định reconcile, rollback hoặc forward fix.

Không chỉnh sửa SQL preview cũ để làm nó trông giống SQL thực thi. Giữ cả hai bản và ghi nhận sai lệch.

## 30. Xử lý các tình huống review thường gặp

| Tình huống | Hành động |
|---|---|
| SQL preview có DROP COLUMN | Yêu cầu phân tích consumer, dữ liệu, backup và approval nâng cao |
| Preview thiếu changeset mong đợi | Kiểm tra include, filter, history và target |
| Preview chứa SQL DBMS khác | Dừng, kiểm tra dbms filter và cấu hình |
| Update-sql thất bại | Không phê duyệt output một phần; điều tra root cause |
| SQL thay đổi sau approval | Hủy approval cũ, sinh và review lại |
| DB history thay đổi sau preview | Chạy status và sinh preview mới |
| Artifact digest khác | Không triển khai artifact chưa được duyệt |
| Parameter thay đổi | Sinh lại SQL, manifest và approval |
| SQL có secret/PII | Cách ly artifact, redaction và xử lý theo incident policy |
| Không có rollback SQL | Đánh giá forward fix/restore, ghi rõ giới hạn |
| Preview giống nhưng execution fail | Xem DB lock, quyền, dữ liệu, transaction và server log |
| Một DBMS không có preview | Chưa đủ điều kiện phát hành cho engine đó |

## 31. Bài thực hành: review và phê duyệt SQL dự kiến triển khai

**Bối cảnh:** một release thêm cột status_code vào customer, backfill dữ liệu hiện có và tạo index. Hệ thống hỗ trợ PostgreSQL và MySQL; production cần approval trước khi migration.

### Phần A — Chuẩn bị artifact

1. Tạo changeset trong branch đã review.
2. Build changelog artifact bất biến.
3. Ghi commit SHA và artifact digest.
4. Pin Liquibase, driver và extension.
5. Xác định target DBMS/version, schema, context/label và parameter.

### Phần B — Sinh preview

1. Chạy validate.
2. Chạy status --verbose.
3. Xác nhận tập changeset pending.
4. Chạy update-sql trên PostgreSQL staging.
5. Lưu update-preview-postgresql.sql và manifest.
6. Chạy lại trên MySQL staging.
7. Lưu update-preview-mysql.sql và manifest riêng.
8. Kiểm tra exit code và không phê duyệt file output một phần.

### Phần C — Review

1. Đối chiếu từng câu SQL với changelog.
2. Kiểm tra schema và thứ tự dependency.
3. Kiểm tra UPDATE backfill và điều kiện WHERE.
4. Kiểm tra lock/time estimate và index strategy.
5. Kiểm tra precondition, context, label và dbms filter.
6. Review rollback/forward recovery.
7. Chạy test trên database có dữ liệu đại diện.
8. Ghi nhận rủi ro và yêu cầu approval phù hợp.

### Phần D — Approval và execution

1. Tính digest SQL preview và manifest.
2. Gắn approval với artifact/preview/target cụ thể.
3. Trước deployment, kiểm tra lại artifact digest và database status.
4. Nếu trạng thái hoặc preview thay đổi, dừng và review lại.
5. Chạy Liquibase update bằng cùng artifact/config đã duyệt.
6. Lưu execution log và exit code.
7. Đối chiếu DATABASECHANGELOG, schema và dữ liệu.
8. Lưu deployment evidence bundle.

### Câu hỏi tự kiểm tra

- `update-sql` có thực thi migration không? **Không.** Nó sinh SQL dự kiến.
- Có thể dùng preview staging cho production không? **Không nếu target state/config khác.** Cần preview riêng cho production.
- Vì sao approval phải gắn digest? **Để bảo đảm reviewer duyệt đúng artifact và SQL được triển khai.**
- SQL preview có thay thế changelog không? **Không.** Changelog là nguồn mô tả thay đổi có phiên bản; preview là SQL được sinh từ trạng thái cụ thể.
- Nếu database thay đổi sau preview thì sao? **Kiểm tra status và sinh preview mới; approval cũ có thể hết hiệu lực.**
- Có nên chạy file SQL bằng client thủ công sau khi review? **Không mặc định.** Nên để Liquibase update quản lý execution và history.
- Vì sao cần review rollback riêng? **Vì rollback có thể xóa dữ liệu hoặc không thể đảo ngược hoàn toàn.**
- Nếu update-sql thất bại nhưng file vẫn có nội dung thì có được duyệt không? **Không.** Output một phần không phải preview hoàn chỉnh.

## 32. Checklist rà soát, phê duyệt và lưu SQL

**Đầu vào và khả năng tái lập**
- [ ] Artifact changelog được build và có digest.
- [ ] Commit SHA, Liquibase, Java, JDBC driver và extension được ghi nhận.
- [ ] DBMS/version, target alias và schema rõ ràng.
- [ ] Context, label, dbms filter và parameter được ghi nhận.
- [ ] Master changelog và toàn bộ include có trong artifact.
- [ ] Changeset cũ bất biến và checksum được kiểm tra.

**Sinh SQL**
- [ ] validate đạt.
- [ ] status --verbose đúng tập changeset pending.
- [ ] update-sql chạy thành công với đúng target/config.
- [ ] SQL preview riêng cho từng DBMS/môi trường cần thiết.
- [ ] Exit code được lưu; output một phần không bị coi là thành công.
- [ ] Preview có timestamp và deployment ID.

**Review kỹ thuật**
- [ ] SQL khớp changelog và ý định nghiệp vụ.
- [ ] Thứ tự dependency đúng.
- [ ] DROP/DELETE/TRUNCATE/ALTER rủi ro đã được đánh giá.
- [ ] Precondition, filter và parameter đúng.
- [ ] Lock, transaction, thời gian chạy và online strategy được xem xét.
- [ ] Dữ liệu/backfill/constraint được kiểm tra.
- [ ] Rollback hoặc forward recovery được review riêng.
- [ ] SQL không chứa secret hoặc dữ liệu nhạy cảm ngoài phạm vi.

**Approval và freshness**
- [ ] Approval gắn với artifact digest, SQL digest và manifest digest.
- [ ] Reviewer/approver đúng vai trò.
- [ ] Target DBMS/environment khớp approval.
- [ ] Trước execution đã kiểm tra lại artifact và database status.
- [ ] Nếu SQL/config/state thay đổi, approval cũ bị vô hiệu và review lại.

**Lưu trữ và thực thi**
- [ ] SQL preview và manifest được lưu trong artifact store có kiểm soát.
- [ ] Có encryption, access audit và retention.
- [ ] Không chỉ lưu trong workspace tạm.
- [ ] Execution dùng cùng artifact/config đã duyệt.
- [ ] Liquibase update quản lý execution/history theo quy trình.
- [ ] Có log, exit code và post-deployment checks.
- [ ] DATABASECHANGELOG, schema và dữ liệu được đối chiếu.
- [ ] Deployment evidence bundle truy xuất được sau khi job kết thúc.

**Kết luận:** rà soát và phê duyệt SQL dự kiến triển khai là cổng kiểm soát nối changelog với hành động thực tế trên database. `update-sql` cho reviewer thấy câu lệnh được sinh theo DBMS, history và filter hiện tại; manifest và digest xác định chính xác artifact/target; approval ghi nhận quyết định; còn freshness check bảo đảm trạng thái database chưa làm preview lỗi thời. Lưu SQL cùng log, history và kết quả kiểm tra trong kho artifact có kiểm soát giúp tổ chức truy vết được mỗi lần migration. Khi execution tiếp tục do Liquibase quản lý bằng cùng artifact và cấu hình đã duyệt, quy trình vừa giữ được lịch sử changeset vừa có bằng chứng đủ để review, audit và điều tra.
