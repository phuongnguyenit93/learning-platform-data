# Bảo vệ bảng lịch sử, khóa và bằng chứng triển khai

Trong chương **Bảo mật** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, hai bảng quản trị DATABASECHANGELOG và DATABASECHANGELOGLOCK là thành phần quan trọng của cơ chế triển khai. Bảng lịch sử cho biết Liquibase đã ghi nhận changeset nào; bảng khóa điều phối các tiến trình migration trên cùng database. Nếu các bảng này bị sửa, xóa hoặc truy cập trái phép, nhóm có thể mất khả năng xác định trạng thái migration, chạy lại DDL nguy hiểm hoặc che giấu thay đổi đã xảy ra.

Phạm vi của dịch vụ **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài học áp dụng những nguyên tắc đó để bảo vệ lịch sử, khóa và bằng chứng triển khai bằng phân quyền, tách danh tính, kiểm soát pipeline, audit độc lập, backup và quy trình ứng phó sự cố.

Định hướng đầy đủ của dịch vụ: Nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Mục tiêu là bảo đảm chỉ tiến trình migration được phê duyệt mới có quyền cập nhật schema và metadata Liquibase; người vận hành có thể kiểm tra lịch sử mà không sửa nó; và bằng chứng của từng release vẫn có thể truy xuất ngay cả khi database hoặc hệ thống triển khai gặp sự cố.

## 1. Phân biệt lịch sử Liquibase, khóa và audit trail

Ba loại thông tin thường bị nhầm lẫn:

| Thành phần | Vai trò | Không chứng minh được điều gì |
|---|---|---|
| DATABASECHANGELOG | Ghi nhận changeset Liquibase đã xử lý, định danh, thời điểm, thứ tự, loại thực thi và checksum | Không chứng minh toàn bộ schema hiện tại chưa bị thay đổi thủ công |
| DATABASECHANGELOGLOCK | Điều phối các Liquibase runner để tránh chạy migration đồng thời trên cùng database | Không phải khóa bảo vệ mọi DDL hoặc mọi ứng dụng khỏi sửa schema |
| Audit/deployment evidence | Ghi nhận ai phê duyệt, artifact nào được triển khai, lệnh nào chạy, kết quả và bằng chứng kiểm tra | Không tự thay thế trạng thái thực tế của database |

DATABASECHANGELOG là lịch sử thực thi do Liquibase quản lý. Nó thường chứa các trường như ID, AUTHOR, FILENAME, DATEEXECUTED, ORDEREXECUTED, EXECTYPE và MD5SUM; cấu trúc cụ thể phụ thuộc phiên bản.

DATABASECHANGELOGLOCK giữ trạng thái khóa của Liquibase. Một tiến trình migration lấy khóa trước khi thực hiện cập nhật và giải phóng khi hoàn tất theo quy trình. Bảng này thường có thông tin như ID, LOCKED, LOCKGRANTED và LOCKEDBY; không nên dựa vào một cấu trúc cột cố định nếu chưa xác minh phiên bản.

Audit trail cần lưu thông tin ngoài hai bảng trên: danh tính người/job, phê duyệt, commit hoặc digest artifact, môi trường, thời điểm, kết quả kiểm tra và log. Nếu một người có thể sửa cả schema lẫn DATABASECHANGELOG, chỉ dựa vào history trong cùng database sẽ không đủ để chứng minh thay đổi là hợp lệ.

## 2. Mô hình đe dọa cần bảo vệ

Các rủi ro thường gặp:

- Tài khoản runtime của ứng dụng có quyền UPDATE/DELETE trên DATABASECHANGELOG.
- Developer hoặc DBA sửa/xóa hàng lịch sử để bỏ qua validation hoặc làm migration chạy lại.
- Job CI/CD dùng chung credentials có quyền cao với ứng dụng.
- Một người có thể sửa changelog, phê duyệt và triển khai chính thay đổi đó mà không có kiểm soát độc lập.
- Migration artifact bị thay thế sau khi review.
- Kẻ tấn công thay đổi schema trực tiếp rồi sửa history để che dấu vết.
- Quyền giải phóng lock được cấp rộng, khiến một người có thể can thiệp migration đang chạy.
- Log chứa JDBC password, token, SQL literal hoặc dữ liệu cá nhân.
- Backup chứa history và dữ liệu nhạy cảm nhưng không được mã hóa hoặc kiểm soát truy cập.
- Quy trình khẩn cấp dùng clear-checksums, changelog-sync hoặc SQL trực tiếp mà không có phê duyệt và bằng chứng.

Cần xác định tài sản cần bảo vệ:
1. Changelog source và artifact đã phát hành.
2. Schema và dữ liệu nghiệp vụ.
3. DATABASECHANGELOG và DATABASECHANGELOGLOCK.
4. Credentials và quyền migration.
5. Pipeline, approval và deployment identity.
6. Log, SQL preview, audit record và backup.
7. Công cụ, driver và extension dùng để chạy migration.

## 3. Tách danh tính ứng dụng, migration và kiểm toán

Không nên dùng một tài khoản database cho mọi hoạt động. Một mô hình cơ bản:

| Danh tính | Quyền cần có | Quyền nên tránh |
|---|---|---|
| Runtime application | Quyền đọc/ghi dữ liệu nghiệp vụ theo chức năng | DDL, sửa/xóa history Liquibase, thao tác lock |
| Liquibase migration | Quyền DDL/DML cần thiết cho changeset và quyền quản lý history/lock | Quyền quản trị server không liên quan |
| Read-only auditor | Đọc metadata, DATABASECHANGELOG và log được phép | UPDATE/DELETE/DDL |
| DBA break-glass | Quyền quản trị theo quy trình khẩn cấp | Sử dụng thường xuyên hoặc không ghi audit |
| CI/CD orchestrator | Lấy secret, khởi chạy job và lưu artifact theo vai trò | Truy cập trực tiếp rộng hơn nhu cầu |

Runtime user chỉ cần quyền trên các bảng/view mà ứng dụng sử dụng. Nó không cần quyền thay đổi schema hoặc sửa metadata Liquibase.

Migration user cần đủ quyền để thực hiện các changeset được phê duyệt. Tùy DBMS, quyền DDL có thể gắn với schema owner hoặc role đặc biệt. Không cấp quyền quản trị toàn server nếu chỉ cần thay đổi một schema ứng dụng.

Read-only auditor có thể truy vấn history để đối chiếu release nhưng không được sửa lịch sử. Quyền này cũng cần giới hạn theo phân loại dữ liệu và chính sách bảo mật.

Tách danh tính giúp log và audit trả lời được **ai đã thực hiện hành động**. Nếu mọi tiến trình dùng cùng một admin account, khó phân biệt hành động của ứng dụng, pipeline và người vận hành.

## 4. Đặt bảng metadata Liquibase trong schema được bảo vệ

Có thể tách bảng lịch sử/khóa khỏi schema nghiệp vụ để quản lý quyền rõ ràng hơn. Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    default-schema: app
    liquibase-schema: migration_meta
~~~

default-schema là schema mặc định cho các change không chỉ rõ schema; liquibase-schema chỉ định nơi lưu bảng quản trị Liquibase. Tên property và hành vi cụ thể cần kiểm tra theo phiên bản Spring Boot/Liquibase.

Lợi ích:
- Phân biệt metadata migration với dữ liệu nghiệp vụ.
- Có thể cấp quyền đọc history riêng cho auditor.
- Hạn chế runtime application truy cập bảng quản trị.
- Dễ áp dụng audit và retention theo phạm vi.
- Giảm nguy cơ ứng dụng vô tình đọc/ghi bảng metadata.

Schema migration_meta cần được provisioning và phân quyền trước hoặc trong bước bootstrap được phê duyệt. Không giả định Liquibase có quyền tự tạo schema nếu tài khoản chỉ được cấp quyền trên schema đã tồn tại.

Nếu đổi schema hoặc tên bảng history sau khi đã triển khai, phải lập kế hoạch chuyển đổi có kiểm chứng. Cấu hình sai có thể khiến Liquibase tìm một bảng DATABASECHANGELOG mới và hiểu nhầm các changeset cũ chưa được chạy.

## 5. Bảo vệ DATABASECHANGELOG khỏi sửa trái phép

Các biện pháp chính:

- Runtime application không có quyền UPDATE, DELETE, TRUNCATE hoặc DROP trên bảng history.
- Developer không dùng tài khoản runtime để thao tác metadata.
- Migration user chỉ được sử dụng trong job hoặc tiến trình được phê duyệt.
- Read-only auditor chỉ có SELECT.
- Quyền owner/schema được quản lý riêng; không để mọi developer là owner.
- Hành động DDL/DML trực tiếp trên bảng history được audit nếu DBMS hỗ trợ.
- Có backup/PITR để phục hồi nếu history bị hỏng.
- So sánh history với artifact và bằng chứng deployment bên ngoài.

Ví dụ nguyên tắc quyền theo PostgreSQL (chỉ minh họa, phải điều chỉnh owner/schema/role thực tế):

~~~sql
REVOKE ALL ON TABLE migration_meta.databasechangelog
FROM app_runtime;

REVOKE ALL ON TABLE migration_meta.databasechangeloglock
FROM app_runtime;

GRANT SELECT ON TABLE migration_meta.databasechangelog
TO migration_auditor;

GRANT SELECT ON TABLE migration_meta.databasechangeloglock
TO migration_auditor;
~~~

Cú pháp, tên bảng thực tế và quyền kế thừa phụ thuộc DBMS. Trong PostgreSQL, quyền của owner và superuser có thể vượt qua grant/revoke thông thường; cần kiểm soát owner role và membership. Với MySQL, SQL Server, Oracle hoặc engine khác, dùng mô hình grant tương ứng.

Không cấp SELECT rộng cho toàn bộ nhân sự nếu history có thể tiết lộ tên schema, đường dẫn source, người thực hiện hoặc metadata nội bộ. Auditor cần quyền vừa đủ.

## 6. Bảo vệ DATABASECHANGELOGLOCK

Bảng lock có tính vận hành đặc biệt. Liquibase cần đọc và cập nhật trạng thái khóa; người khác không nên tùy tiện thay đổi.

Quy tắc:
- Chỉ Liquibase migration principal và DBA theo runbook mới được quyền cập nhật lock.
- Runtime application không có quyền sửa hoặc xóa lock.
- Auditor chỉ đọc trạng thái khi được phép.
- Không xóa bảng DATABASECHANGELOGLOCK để xử lý timeout.
- Không cập nhật LOCKED=false thủ công khi chưa xác minh process/session giữ khóa đã dừng.
- Không cho nhiều pipeline cùng triển khai một database nếu không có điều phối.
- Ghi lại mọi thao tác break-glass liên quan lock.

Kiểm tra trạng thái bằng truy vấn phù hợp DBMS:

~~~sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM migration_meta.databasechangeloglock;
~~~

Tên schema/table có thể khác theo cấu hình. Một lock đang bật không tự động có nghĩa là stale lock. Tiến trình có thể vẫn đang chạy DDL, chờ lock bảng nghiệp vụ hoặc đang chờ phản hồi từ database.

Trước khi can thiệp:
1. Xác định job/pod/host được ghi trong LOCKEDBY nếu có.
2. Kiểm tra trạng thái process trong orchestrator.
3. Kiểm tra session và câu lệnh đang chạy trên database.
4. Xác nhận migration không còn hoạt động.
5. Bảo toàn log và history.
6. Thực hiện thao tác giải phóng theo runbook có phê duyệt.
7. Xác minh lock và schema sau đó.

## 7. Checksum giúp phát hiện thay đổi, nhưng không phải bằng chứng chống giả mạo

Liquibase lưu checksum của changeset trong DATABASECHANGELOG để phát hiện nội dung đã triển khai bị thay đổi so với nội dung hiện tại. Khi checksum không khớp, validation có thể báo lỗi.

Tuy nhiên:
- Checksum không chứng minh ai đã tạo artifact.
- Checksum không chứng minh database chưa bị sửa thủ công.
- Người có quyền sửa cả changelog và bảng history có thể tìm cách che giấu sai lệch.
- MD5SUM không nên được xem là chữ ký số hoặc cơ chế xác thực nguồn gốc artifact.
- Checksum không thay thế chữ ký artifact, commit protection hoặc audit độc lập.

Bảo vệ nguồn gốc cần kết hợp:
- Review thay đổi trong pull request.
- Branch protection và approval độc lập.
- Artifact bất biến gắn commit SHA/digest.
- Quyền triển khai tách khỏi quyền sửa source.
- Lưu generated SQL và log theo deployment ID.
- Đối chiếu DATABASECHANGELOG với artifact đã phê duyệt.
- Audit DDL trực tiếp ngoài Liquibase.

Không sửa changeset đã chạy chỉ để làm validation xanh. Nếu nội dung cần thay đổi, thêm changeset mới. clear-checksums và validCheckSum là cơ chế có tác động đến validation; chỉ dùng trong trường hợp được hiểu rõ, có phê duyệt và có bằng chứng về lý do.

## 8. Không sửa lịch sử bằng SQL thủ công

Không xóa hoặc chỉnh sửa hàng DATABASECHANGELOG để:
- Buộc changeset cũ chạy lại.
- Bỏ qua checksum mismatch.
- Che một lần triển khai thất bại.
- Đánh dấu một migration đã chạy dù chưa kiểm chứng schema.
- Làm cho các môi trường có history giống nhau một cách giả tạo.

Việc chỉnh history có thể dẫn đến:
- DDL chạy lại trên object đã tồn tại.
- Changeset bị bỏ qua dù database thiếu object.
- Không còn khả năng giải thích thứ tự triển khai.
- Sai lệch giữa staging và production.
- Mất bằng chứng phục vụ audit hoặc sự cố.

Các lệnh changelog-sync, changelog-sync-sql, clear-checksums, mark-next-changeset-ran hoặc thao tác history tương tự cần được xem là hành động quản trị đặc biệt. Chỉ dùng đúng mục đích, đúng phạm vi, trên database đã đối chiếu và có phê duyệt. Cú pháp/tên lệnh phụ thuộc phiên bản Liquibase.

Nếu history bị sai:
1. Dừng deployment tiếp theo.
2. Bảo toàn bản chụp history và log.
3. So sánh schema vật lý với canonical/changelog.
4. Xác định changeset đã thực thi thật, được đánh dấu hay chưa bắt đầu.
5. Lập phương án reconcile cùng DBA và owner ứng dụng.
6. Ghi lại thay đổi lịch sử như một sự kiện đặc biệt.
7. Kiểm tra lại status, schema, data và artifact trước khi tiếp tục.

## 9. Bảo vệ changelog source và artifact

Lịch sử database chỉ có ý nghĩa khi có thể đối chiếu với source đã được phê duyệt.

Các kiểm soát nên có:
- Changelog nằm trong repository có branch protection.
- Pull request bắt buộc review bởi người khác tác giả khi thay đổi ảnh hưởng production.
- CODEOWNERS hoặc cơ chế ownership tương đương cho thư mục migration.
- Không cho pipeline production lấy changelog từ branch tùy ý.
- Build artifact một lần và promote cùng artifact qua môi trường.
- Ghi commit SHA, artifact digest và Liquibase version.
- Pin JDBC driver, Liquibase core và extension.
- Quét dependency và quản lý nguồn tải package.
- Không chạy changelog lấy từ người dùng hoặc nguồn không tin cậy.
- Bảo vệ file SQL, CSV, include path và changelog parameter khỏi thay thế ngoài ý muốn.

Một artifact được review nhưng bị build lại từ source đã thay đổi không còn chắc chắn là artifact đã được phê duyệt. Dùng digest để liên kết artifact được review với artifact được triển khai.

## 10. Tách quyền phê duyệt và quyền thực thi

Một quy trình an toàn nên phân biệt:
- Người đề xuất changeset.
- Người review nội dung và generated SQL.
- Người phê duyệt triển khai production.
- Identity thực thi migration job.
- Người kiểm tra kết quả sau triển khai.

Không nhất thiết mỗi vai trò là một cá nhân khác nhau trong mọi tổ chức, nhưng các thay đổi rủi ro cao nên có kiểm soát độc lập. Người có thể sửa changelog không nên tự cấp cho mình quyền vượt qua tất cả cổng phê duyệt production.

Pipeline nên:
1. Validate changelog trong pull request.
2. Chạy test trên database cô lập.
3. Sinh update-sql với đúng DBMS/filter.
4. Review và phê duyệt.
5. Cấp credentials ngắn hạn cho migration job.
6. Thực thi artifact bất biến.
7. Thu thập log và history.
8. Chạy post-deployment checks.
9. Ghi deployment record.

Approval cần gắn với commit/artifact cụ thể, môi trường và thời điểm. Approval chung không gắn digest có thể bị tái sử dụng cho một artifact khác.

## 11. Credentials và secret cho migration

Migration user có quyền cao hơn runtime user, vì vậy credentials phải được bảo vệ nghiêm ngặt.

Nguyên tắc:
- Lấy secret từ secret manager hoặc cơ chế cấp phát của nền tảng.
- Ưu tiên credentials ngắn hạn/rotatable nếu DBMS và hạ tầng hỗ trợ.
- Không commit password trong liquibase.properties hoặc application.yaml.
- Không ghi secret vào command line nếu process list có thể lộ.
- Không in toàn bộ environment khi debug pipeline.
- Không đưa secret vào changelog parameter.
- Không chia sẻ cùng một credential giữa nhiều môi trường.
- Thu hồi hoặc rotate credentials sau sự cố nghi ngờ lộ.
- Audit việc đọc secret và sử dụng migration identity.

Ví dụ cấu hình không chứa giá trị bí mật:

~~~yaml
spring:
  liquibase:
    url: ${MIGRATION_DB_URL}
    user: ${MIGRATION_DB_USERNAME}
    password: ${MIGRATION_DB_PASSWORD}
~~~

Cách inject biến môi trường cần được bảo vệ bởi CI runner, container runtime hoặc secret provider. Biến môi trường không tự động an toàn nếu ứng dụng log toàn bộ environment hoặc process có quyền đọc process metadata.

## 12. Bảo vệ changelog parameters và SQL động

Liquibase hỗ trợ parameter substitution để dùng giá trị theo môi trường. Parameter có thể ảnh hưởng schema, tên object hoặc nội dung SQL; do đó phải kiểm soát đầu vào.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-001-create-tenant-audit"
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

appSchema phải được lấy từ cấu hình đã kiểm soát và chỉ nhận giá trị trong allowlist. Không dùng input HTTP, tên tenant tùy ý hoặc giá trị do người dùng cuối cung cấp để xây dựng identifier/SQL.

Các biện pháp:
- Validate parameter trước khi migration chạy.
- Giới hạn giá trị theo allowlist.
- Không dùng parameter cho password/token.
- Không nối chuỗi tùy tiện vào SQL.
- Review generated SQL sau khi substitution.
- Dùng identifier cố định nếu không thật sự cần parameter.
- Có test cho từng profile/database.

SQL động có thể mở rộng phạm vi tác động ngoài dự kiến nếu parameter bị thay đổi. Quyền migration cao làm rủi ro này lớn hơn quyền ứng dụng thông thường.

## 13. Ghi nhận bằng chứng cho mỗi lần triển khai

Một deployment record nên có các thông tin đủ để truy vết:

| Nhóm | Bằng chứng |
|---|---|
| Danh tính | Người đề xuất, reviewer, approver, job/service identity |
| Artifact | Repository, commit SHA, artifact digest, changelog revision |
| Công cụ | Liquibase version, JDBC driver, extension, Java runtime |
| Đích | Environment, DBMS/version, database alias, schema |
| Phạm vi | Master changelog, context, label, parameters |
| Preview | validate output, status, generated update-sql |
| Thực thi | Job ID, start/end time, exit code, migration log |
| History | DATABASECHANGELOG snapshot/đối chiếu cần thiết |
| Kết quả | Schema/data assertions, smoke test, health status |
| Phê duyệt | Approval ID, thời điểm và phạm vi được duyệt |

Không cần lưu password, token hoặc dữ liệu nghiệp vụ nguyên bản trong deployment record. Chỉ lưu metadata đủ để xác định môi trường và artifact.

Có thể lưu bằng chứng trong hệ thống CI/CD, kho artifact hoặc nền tảng audit độc lập với database đích. Nếu database bị xâm phạm hoặc history bị sửa, bằng chứng ngoài database giúp đối chiếu.

## 14. Làm cho bằng chứng khó bị sửa hoặc xóa

Đối với môi trường quan trọng, log và deployment artifact nên được gửi tới hệ thống tập trung có kiểm soát quyền và retention.

Có thể áp dụng:
- Append-only log ingestion.
- Object storage có retention lock/object lock nếu chính sách yêu cầu.
- Quyền xóa log tách khỏi quyền ghi log.
- Mã hóa khi truyền và lưu.
- Audit mọi lần đọc/export/xóa.
- Backup riêng cho deployment evidence.
- Digest hoặc chữ ký số cho artifact và manifest.
- Đồng bộ timestamp.
- Lưu log ở account/project độc lập với database production.

Không cần biến mọi log debug thành dữ liệu lưu vĩnh viễn. Phân loại:
- Deployment summary và approval record: retention theo yêu cầu audit.
- Migration log: retention đủ thời gian hỗ trợ điều tra và chính sách.
- DEBUG/TRACE tạm thời: thời hạn ngắn hơn.
- Database audit: theo chính sách bảo mật/tuân thủ.
- Backup: theo RPO/RTO và quy định dữ liệu.

Nếu chỉ lưu log trong cùng pod hoặc database mà migration quản lý, một sự cố xóa pod/database có thể làm mất cả ứng dụng lẫn bằng chứng.

## 15. Audit thay đổi schema ngoài Liquibase

DATABASECHANGELOG chỉ phản ánh các changeset Liquibase ghi nhận. Một DBA hoặc công cụ khác có thể chạy DDL trực tiếp mà không tạo changeset tương ứng.

Để phát hiện:
- Bật database auditing cho DDL quan trọng nếu DBMS hỗ trợ.
- Thu log đăng nhập và principal thực thi.
- So sánh snapshot/schema diff theo lịch.
- Cảnh báo khi runtime principal thực hiện DDL.
- Kiểm tra grant và ownership định kỳ.
- Ghi ticket/change request cho thao tác break-glass.
- Đối chiếu audit event với deployment record.

Không phải DBMS nào cũng cung cấp audit cùng mức chi tiết hoặc cùng chi phí. Cấu hình audit cần được kiểm thử về hiệu năng, dung lượng và khả năng truy vấn.

Một thay đổi ngoài Liquibase cần được điều tra:
1. Ai thực hiện và bằng principal nào?
2. Thời điểm và session nào?
3. Object nào thay đổi?
4. Có approval/ticket không?
5. Có ảnh hưởng dữ liệu hoặc ứng dụng không?
6. Có cần changeset mới để đưa thay đổi vào lịch sử chuẩn không?

Không sửa DATABASECHANGELOG để làm cho một DDL thủ công trông như changeset đã được chạy. Cần tạo bằng chứng và kế hoạch reconcile riêng.

## 16. Bảo vệ backup và bản sao lịch sử

Backup database thường chứa cả dữ liệu nghiệp vụ lẫn DATABASECHANGELOG. Vì vậy, backup cần cùng mức bảo vệ với dữ liệu nguồn.

Kiểm soát:
- Mã hóa backup và bản sao.
- Hạn chế ai có quyền tạo, tải xuống, restore hoặc xóa.
- Tách quyền quản trị backup khỏi quyền migration.
- Có retention và lifecycle policy.
- Kiểm tra tính toàn vẹn backup.
- Thử restore định kỳ.
- Ghi lại thời điểm, database version và artifact liên quan.
- Không dùng backup production cho môi trường không được phép nếu chưa mask dữ liệu.
- Bảo đảm history sau restore khớp với trạng thái schema được restore.

Nếu khôi phục schema từ backup cũ nhưng dùng changelog hiện tại, Liquibase có thể thấy history ở một mốc cũ và đề xuất chạy các changeset tiếp theo. Phải xác định chính xác backup được tạo sau changeset nào, artifact nào tương ứng và có thay đổi ngoài Liquibase nào xảy ra sau đó.

Backup chỉ hữu ích khi có thể restore và xác minh. Một file backup chưa từng thử phục hồi không phải bằng chứng recovery đã sẵn sàng.

## 17. Quy trình xử lý khi phát hiện history bị sửa

Nếu nghi ngờ DATABASECHANGELOG bị xóa hoặc sửa trái phép:

1. Dừng các migration job tiếp theo trên database liên quan.
2. Không tự ý chỉnh thêm history để khớp với mong đợi.
3. Bảo toàn log, database audit, CI job và deployment artifact.
4. Chụp trạng thái DATABASECHANGELOG/LOCK và schema hiện tại theo quy trình được phép.
5. Xác định principal và thời điểm có hành động bất thường.
6. So sánh với bản history backup và deployment evidence bên ngoài.
7. Xác định schema có thay đổi thật hay chỉ metadata bị sửa.
8. Đánh giá dữ liệu, constraint và ứng dụng có bị ảnh hưởng không.
9. Lập kế hoạch reconcile cùng DBA/security/application owner.
10. Chỉ tiếp tục triển khai sau khi history và schema có trạng thái được hiểu, phê duyệt và ghi nhận.

Không chạy update ngay để “xem Liquibase sửa được không”. Nếu history bị thiếu, Liquibase có thể cố thực thi lại changeset và gây lỗi hoặc thay đổi dữ liệu.

## 18. Quy trình xử lý lock bất thường

Nếu DATABASECHANGELOGLOCK có LOCKED=true trong thời gian dài:

1. Ghi thời điểm quan sát, database alias và deployment ID.
2. Xác định LOCKEDBY/LOCKGRANTED nếu có.
3. Kiểm tra migration job có còn active không.
4. Kiểm tra session DB và câu SQL đang chạy.
5. Kiểm tra lock wait/deadlock/transaction trong DBMS.
6. Đối chiếu log của runner và orchestrator.
7. Xác nhận process đã dừng và không còn câu lệnh migration đang thực thi.
8. Xin phê duyệt theo runbook nếu phải release lock.
9. Thực hiện bằng principal được cấp quyền.
10. Kiểm tra lock, history và schema sau thao tác.

Không xóa hàng lock, drop bảng lock hoặc cập nhật LOCKED=false tùy tiện. Một tiến trình có thể vẫn đang thực hiện DDL ngoài transaction hoặc đang chờ tài nguyên database.

Sau khi giải phóng lock, không tự động retry nếu chưa xác định changeset trước đó đã thay đổi một phần schema hay chưa.

## 19. Kiểm soát thao tác quản trị đặc biệt

Một số lệnh và thao tác có thể ảnh hưởng lịch sử hoặc trạng thái migration:

| Hành động | Rủi ro | Kiểm soát |
|---|---|---|
| changelog-sync | Đánh dấu changeset là đã xử lý mà không chạy change | Chỉ dùng cho baseline đã đối chiếu, giới hạn đúng changelog |
| clear-checksums | Xóa checksum đã lưu để Liquibase tính lại | Phải có lý do, backup và approval |
| validCheckSum | Chấp nhận checksum cụ thể | Review checksum cũ/mới và phạm vi changeset |
| mark-next-changeset-ran | Ghi nhận changeset mà không chạy theo cách thông thường | Xác minh schema trước và sau |
| Sửa DATABASECHANGELOG | Làm sai lệch lịch sử | Không dùng như thao tác sửa lỗi thông thường |
| Giải phóng lock thủ công | Có thể gây hai migration runner đồng thời | Xác minh process/session và runbook |
| Chạy SQL trực tiếp | Thay đổi không được history Liquibase ghi nhận | Break-glass, audit và reconcile bằng changeset mới |

Tên lệnh và hành vi chi tiết phụ thuộc phiên bản Liquibase. Bảng trên là phân loại rủi ro, không phải hướng dẫn chạy các lệnh trong mọi tình huống.

Mọi thao tác đặc biệt cần có:
- Người yêu cầu và người phê duyệt.
- Database/schema đích.
- Lý do và sự cố/ticket liên quan.
- Artifact/changelog revision.
- Backup hoặc bằng chứng trước thao tác.
- Command/SQL đã review.
- Thời điểm và principal thực hiện.
- Kết quả và kiểm tra sau thao tác.

## 20. Kiểm soát Spring Boot và runtime application

Nếu Spring Boot chạy Liquibase lúc startup, ứng dụng có thể cần quyền migration. Trong production, cân nhắc tách migration job khỏi runtime để giảm quyền:

~~~yaml
spring:
  liquibase:
    enabled: false
  datasource:
    url: ${APP_DB_URL}
    username: ${APP_DB_USERNAME}
    password: ${APP_DB_PASSWORD}
~~~

Ứng dụng runtime không bật auto-run. Pipeline chạy Liquibase bằng migration principal riêng trước khi deploy application.

Nếu vẫn chọn startup migration:
- Dùng datasource/credentials riêng cho Liquibase nếu phù hợp phiên bản Spring Boot.
- Không cấp DDL cho runtime user.
- Đảm bảo chỉ một quy trình được quyền migration.
- Kiểm soát DATABASECHANGELOGLOCK.
- Ghi nhận instance/deployment identity.
- Có readiness và timeout phù hợp.
- Không để mọi replica có quyền DDL rộng nếu không cần.

Hibernate nên dùng validate hoặc chế độ không tự thay đổi schema trong production khi Liquibase là nguồn quản lý chính. Không để ddl-auto: update tạo thay đổi ngoài history.

## 21. Bảo vệ log và SQL preview

Log, update-sql và history snapshot có thể chứa thông tin nhạy cảm hoặc cấu trúc nội bộ.

Cần:
- Redact JDBC URL, password, token và bind value nhạy cảm.
- Không bật log bind parameter rộng trong production nếu chưa đánh giá.
- Giới hạn quyền xem generated SQL.
- Không lưu SQL artifact vào repository công khai.
- Không gửi log nguyên bản vào ticket/chat không được phép.
- Mã hóa log và artifact.
- Có retention và audit truy cập.
- Tách log debug ngắn hạn khỏi deployment evidence dài hạn.

Một bản SQL preview có thể tiết lộ tên bảng, cột, index và logic dữ liệu. Xem nó là artifact triển khai có phân loại, không phải file vô hại.

## 22. Checklist kiểm soát quyền

| Kiểm tra | Runtime | Migration | Auditor |
|---|---:|---:|---:|
| Đọc bảng nghiệp vụ cần thiết | Có | Theo nhu cầu | Không mặc định |
| Ghi dữ liệu nghiệp vụ | Theo chức năng | Theo changeset | Không |
| Tạo/sửa/xóa schema | Không | Có trong phạm vi | Không |
| SELECT DATABASECHANGELOG | Không mặc định | Có | Có |
| UPDATE/INSERT/DELETE DATABASECHANGELOG | Không | Theo quyền Liquibase cần thiết | Không |
| UPDATE DATABASECHANGELOGLOCK | Không | Theo quyền Liquibase cần thiết | Không |
| DDL ngoài schema sở hữu | Không | Không mặc định | Không |
| Quản trị database/server | Không | Không mặc định | Không |

Bảng là mô hình quyền logic. Cách cấp quyền thực tế khác nhau theo DBMS và cần kiểm tra cả role membership, ownership, default privileges và quyền kế thừa.

## 23. Checklist bằng chứng triển khai

Mỗi lần phát hành cần có thể truy xuất:

- [ ] Deployment ID/run ID.
- [ ] Người hoặc service identity khởi chạy.
- [ ] Người review và phê duyệt.
- [ ] Commit SHA và artifact digest.
- [ ] Master changelog và revision.
- [ ] Liquibase/driver/extension version.
- [ ] DBMS/version và database alias.
- [ ] Context, label và parameters hiệu lực.
- [ ] validate/status/update-sql output.
- [ ] Migration log và exit code.
- [ ] Changeset identity và trạng thái history.
- [ ] Schema/data post-check.
- [ ] Thời điểm bắt đầu/kết thúc.
- [ ] Sự cố, retry hoặc thao tác break-glass nếu có.

Không lưu secret hoặc dữ liệu cá nhân vào manifest. Artifact digest và log cần được bảo vệ khỏi sửa/xóa trái phép.

## 24. Bài thực hành: bảo vệ history và lock trong một release

**Bối cảnh:** ứng dụng Spring Boot dùng PostgreSQL. Liquibase chạy trong CI/CD job riêng. Runtime user chỉ được truy cập dữ liệu nghiệp vụ; migration user có quyền DDL trên schema app và quản lý metadata trong migration_meta.

### Phần A — Phân quyền

1. Tạo hoặc xác định role runtime, migration và auditor.
2. Đặt DATABASECHANGELOG/LOCK trong schema metadata.
3. Cấp runtime quyền cần thiết trên bảng nghiệp vụ.
4. Thu hồi quyền runtime trên hai bảng Liquibase.
5. Cấp auditor SELECT theo phạm vi.
6. Xác minh runtime không thể UPDATE/DELETE history hoặc sửa lock.
7. Xác minh migration job vẫn chạy được với principal riêng.

### Phần B — Bảo vệ source và artifact

1. Đưa changelog vào branch có protection.
2. Yêu cầu review độc lập cho migration production.
3. Build artifact và ghi digest.
4. Chạy validate, status và update-sql.
5. Lưu SQL preview và approval record.
6. Chỉ cấp migration credentials cho job được phê duyệt.
7. Gắn deployment ID vào log và artifact.

### Phần C — Kiểm tra audit

1. Chạy một migration thành công trên database test.
2. Đối chiếu changeset với DATABASECHANGELOG.
3. Kiểm tra log CI và DB server theo deployment ID.
4. Thử thao tác UPDATE history bằng runtime user; xác nhận bị từ chối.
5. Thử đọc history bằng auditor; xác nhận chỉ đọc.
6. Kiểm tra lock sau khi migration hoàn tất.
7. Xác minh backup và quy trình restore metadata.

### Phần D — Diễn tập sự cố

1. Trên database test riêng, mô phỏng job bị dừng trong migration.
2. Thu thập log, history, lock và trạng thái schema.
3. Xác định process/session còn hoạt động hay không.
4. Thực hiện runbook giải phóng lock chỉ sau khi xác minh và phê duyệt.
5. Kiểm tra changeset đã thay đổi một phần hay chưa.
6. Reconcile và chạy lại theo kế hoạch.
7. Lưu incident record cùng artifact và kết quả sau khắc phục.

### Câu hỏi tự kiểm tra

- DATABASECHANGELOG có phải audit trail bất biến không? **Không.** Đây là lịch sử Liquibase trong database và vẫn có thể bị sửa bởi principal đủ quyền.
- Checksum có chứng minh artifact do người được phê duyệt tạo không? **Không.** Cần commit protection, artifact digest/chữ ký và approval record.
- Runtime user có cần quyền UPDATE history không? **Không.**
- DATABASECHANGELOGLOCK có khóa mọi DDL trong database không? **Không.** Nó điều phối Liquibase runner.
- Thấy LOCKED=true có thể giải phóng ngay không? **Không.** Phải xác minh process/session và trạng thái migration.
- Có nên xóa history khi checksum mismatch không? **Không.** Bảo toàn bằng chứng và điều tra nguyên nhân.
- Vì sao cần lưu log ngoài database? **Để có bằng chứng độc lập khi database/history gặp sự cố hoặc bị sửa.**
- Tách migration job giúp ích gì? **Giảm quyền runtime và tạo cổng review/phê duyệt riêng cho DDL.**

## 25. Checklist bảo vệ bảng lịch sử, khóa và bằng chứng

**Danh tính và quyền**
- [ ] Runtime, migration, auditor và DBA có danh tính riêng.
- [ ] Runtime không có quyền DDL hoặc sửa DATABASECHANGELOG/LOCK.
- [ ] Migration user chỉ có quyền trong phạm vi cần thiết.
- [ ] Auditor chỉ đọc metadata được phép.
- [ ] Owner/schema role và quyền kế thừa được kiểm tra.
- [ ] Break-glass có phê duyệt và audit.

**Lịch sử và khóa**
- [ ] DATABASECHANGELOG và DATABASECHANGELOGLOCK nằm trong schema được bảo vệ.
- [ ] Không sửa/xóa history bằng SQL như cách xử lý thông thường.
- [ ] Không dùng clear-checksums/validCheckSum/changelog-sync tùy tiện.
- [ ] Lock được điều tra qua process, session và database log.
- [ ] Không giải phóng lock khi migration còn hoạt động.
- [ ] Có backup và phương án reconcile history.

**Source và artifact**
- [ ] Changelog được bảo vệ bằng branch protection/review.
- [ ] Approval gắn với commit/artifact digest.
- [ ] Artifact được build một lần và promote bất biến.
- [ ] Liquibase, JDBC driver và extension được pin.
- [ ] Migration job dùng credentials riêng, thời hạn phù hợp.
- [ ] Parameter và SQL động được allowlist/validate.

**Bằng chứng và audit**
- [ ] Có deployment ID, release, commit, artifact và approver.
- [ ] Có validate/status/update-sql, migration log và exit code.
- [ ] Có history/schema/data post-check.
- [ ] Có database audit cho DDL quan trọng nếu khả thi.
- [ ] Log được gửi tới hệ thống độc lập, có quyền và retention.
- [ ] Secret/PII được redaction.
- [ ] Backup được mã hóa và restore định kỳ.
- [ ] Có runbook cho history tampering, stale lock và migration failure.

**Kết luận:** bảo vệ DATABASECHANGELOG và DATABASECHANGELOGLOCK cần kết hợp phân quyền database, tách runtime khỏi migration identity, kiểm soát source/artifact, giới hạn thao tác quản trị đặc biệt và lưu bằng chứng triển khai độc lập. History và checksum giúp Liquibase phát hiện trạng thái changeset, còn lock điều phối migration runner; cả hai không thay thế audit bảo mật hoặc xác minh schema thực tế. Khi mỗi release có artifact bất biến, approval, log, history đối chiếu được và quy trình xử lý sự cố rõ ràng, nhóm có thể bảo vệ tính toàn vẹn của quá trình migration qua Spring Boot và CI/CD.
