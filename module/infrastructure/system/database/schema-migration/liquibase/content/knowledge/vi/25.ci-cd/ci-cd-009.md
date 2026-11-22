
# Tách bước migration khỏi bước khởi động ứng dụng khi phù hợp

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu thông qua changelog, changeset, precondition, checksum và lịch sử triển khai. Với Spring Boot, Liquibase có thể tự chạy migration khi ứng dụng khởi động. Cách này thuận tiện cho dự án nhỏ và môi trường đơn giản, nhưng ở hệ thống production có nhiều replica, database lớn, quy trình phê duyệt hoặc yêu cầu quyền hạn riêng, migration thường nên được chạy thành **một bước triển khai độc lập** trước khi khởi động hoặc rollout phiên bản ứng dụng mới.

Bài thuộc chương **CI/CD** này giải thích khi nào nên tách migration khỏi startup, cách thiết kế migration job riêng, cách phối hợp job với application deployment, cấu hình Spring Boot, kiểm soát thứ tự, quyền và secret, readiness gate, xử lý thất bại, rollback và quan sát sau triển khai. Mục tiêu là bảo đảm database đạt trạng thái tương thích trước khi ứng dụng mới nhận traffic, đồng thời giữ một chủ thể rõ ràng chịu trách nhiệm thay đổi schema.

Phạm vi bài học được xác định bởi **SERVICE_NAME=DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Theo **SERVICE_NAME_DESCRIBE**, module hướng dẫn quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Vì sao không phải lúc nào cũng chạy migration lúc startup?

Khi ứng dụng Spring Boot khởi động, auto-configuration có thể tạo Liquibase bean và thực thi changelog trước khi application context sẵn sàng. Với một service nhỏ, một instance và migration ngắn, đây là cách triển khai đơn giản.

Trong hệ thống lớn hơn, startup migration có thể gây ra các vấn đề:

- Nhiều replica cùng khởi động và cùng cố gắng kiểm tra/chạy migration.
- Ứng dụng mới chưa thể trở thành healthy cho đến khi migration hoàn tất.
- Một DDL hoặc backfill lâu khiến rollout bị kéo dài, readiness probe thất bại hoặc pod restart.
- Tài khoản runtime phải có quyền DDL/DML rộng hơn mức cần thiết cho xử lý request.
- Việc phê duyệt SQL preview và triển khai database bị gắn chặt với vòng đời ứng dụng.
- Lỗi migration làm application startup thất bại, dù code ứng dụng không có lỗi.
- Một lần scale-out hoặc restart ngoài lịch release cũng có thể kích hoạt quá trình migration.

Tách migration thành job riêng giúp pipeline **chủ động chọn thời điểm, target, credential, thứ tự và tiêu chí hoàn thành**. Ứng dụng chỉ được rollout sau khi database đã đạt điều kiện tương thích.

Tuy nhiên, tách job không phải quy tắc tuyệt đối. Một migration rất nhỏ, backward-compatible, được kiểm thử tốt và chạy trong hệ thống đơn giản có thể phù hợp với startup migration. Quyết định cần dựa trên thời gian, rủi ro, số instance, quyền và yêu cầu vận hành.

## 2. Hai mô hình triển khai

| Tiêu chí | Migration lúc startup | Migration job độc lập |
|---|---|---|
| Thời điểm chạy | Khi ứng dụng khởi động | Một bước riêng trong release pipeline |
| Chủ thể chạy | Một hoặc nhiều application instance | Job/runner được chỉ định |
| Quyền database | Runtime app có thể cần quyền migration | Tách tài khoản migration khỏi runtime |
| Phê duyệt SQL | Gắn với rollout app | Có thể preview/review trước rollout |
| Startup latency | Bao gồm thời gian migration | App chỉ khởi động sau gate |
| Điều phối | Liquibase lock điều phối các process dùng cùng bảng lock | Pipeline điều phối job và single-writer |
| Quan sát | Log lẫn trong log startup | Log, trạng thái và thời gian riêng |
| Phù hợp | Dự án nhỏ, migration ngắn, ít replica | Production, nhiều replica, migration dài hoặc cần approval |

Cả hai mô hình đều dùng Liquibase và DATABASECHANGELOG. Khác biệt chính là **ai chạy migration, chạy khi nào và pipeline xác nhận kết quả ra sao**.

## 3. Vòng đời release khi tách migration

Một release có thể được tổ chức theo trình tự:

~~~text
Build application artifact
          |
          v
Package changelog + migration runtime
          |
          v
Validate changelog / kiểm tra target
          |
          v
Generate và review SQL dự kiến
          |
          v
Migration job chạy Liquibase update
          |
          v
Kiểm tra DATABASECHANGELOG + schema/data
          |
          v
Readiness gate PASS?
       /       \
     No         Yes
     |           |
     v           v
Dừng release   Deploy/rollout application
                 |
                 v
           Health + smoke tests
                 |
                 v
           Theo dõi và hoàn tất release
~~~

Migration job là một bước có trạng thái riêng. Nếu job thất bại, pipeline không nên tiếp tục rollout application phiên bản đòi hỏi schema mới.

Trong hệ thống nhiều database, mỗi target có thể có một migration job riêng; pipeline điều phối prerequisite và readiness theo dependency. Không giả định một job thành công ở database A chứng minh database B đã được cập nhật.

## 4. Khi nào nên tách migration khỏi startup?

Các dấu hiệu sau thường ủng hộ migration job độc lập:

1. Ứng dụng chạy nhiều replica hoặc auto-scaling.
2. Migration có thể kéo dài đáng kể, cần maintenance window hoặc giám sát.
3. Có DDL yêu cầu lock mạnh, index build hoặc backfill dữ liệu lớn.
4. Production yêu cầu phê duyệt trước khi thay đổi database.
5. Runtime application không nên có quyền CREATE/ALTER/DROP.
6. Nhiều service hoặc nhiều database có dependency và thứ tự triển khai.
7. Database do DBA/platform team quản lý riêng với lịch rollout ứng dụng.
8. Có yêu cầu audit riêng cho migration, target, operator và release revision.
9. Cần chạy migration trước khi deploy app mới nhưng vẫn giữ app cũ phục vụ traffic.
10. Muốn retry/recover migration mà không phải restart application.

Ngược lại, startup migration có thể phù hợp nếu database thử nghiệm hoặc service nhỏ, chỉ có một instance, migration rất ngắn, có thể chạy lặp theo lịch sử Liquibase và không yêu cầu approval riêng. Dù vậy, vẫn phải hiểu quyền và cơ chế lock.

## 5. Không nhầm migration job với init container chạy theo từng pod

Trong Kubernetes, một **Job** được tạo riêng cho một lần release có thể chạy migration trước khi Deployment được rollout. Một **init container** lại chạy trong vòng đời của từng Pod.

Nếu mỗi application Pod có init container chạy Liquibase, khi scale từ 2 lên 10 replica, nhiều init container có thể cùng khởi động migration. Liquibase lock có thể tuần tự hóa những tiến trình dùng chung bảng lock, nhưng các pod vẫn phải chờ và tạo thêm kết nối/log/retry. Việc scale ứng dụng khi đó vô tình kích hoạt nhiều migration process.

Mô hình thường dễ kiểm soát hơn:

- Một Kubernetes Job riêng, có target và revision rõ.
- Job chạy xong và hậu kiểm PASS.
- Deployment application mới được mở rollout.
- Application container không tự chạy migration nếu pipeline đã là migration owner.

Init container vẫn hữu ích cho các tác vụ chuẩn bị riêng của từng pod, nhưng migration dùng chung database thường không nên nhân bản theo số replica.

## 6. Cấu hình Spring Boot cho startup migration

Nếu chọn startup migration, Spring Boot có thể bật Liquibase thông qua cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/customer_db
    username: customer_app
    password: \${CUSTOMER_DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Ví dụ trên minh họa cách cấu hình; credentials phải được cấp từ secret store của môi trường, không lưu password thật trong repository.

Khi ứng dụng khởi động, Liquibase auto-configuration dùng datasource được chọn và changelog được chỉ định. Hãy xác minh:

- Driver và DBMS version phù hợp.
- Changelog master và các file include có trong artifact.
- Default schema, schema history và quyền tạo bảng lịch sử đúng.
- Runtime account có quyền phù hợp với toàn bộ changeset được chạy.
- Không có migration runner khác cạnh tranh cùng target.
- Startup/readiness timeout đủ cho migration được dự kiến.

Nếu ứng dụng có nhiều DataSource, không mặc định Liquibase tự chạy trên tất cả database theo đúng thứ tự. Cần cấu hình rõ datasource/changelog cho từng đích hoặc dùng migration job riêng.

## 7. Tắt auto-run khi pipeline là migration owner

Khi pipeline chạy Liquibase độc lập, application runtime thường cần tắt auto-run để tránh mỗi replica khởi động lại thực hiện migration.

Trong Spring Boot:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Có thể đặt giá trị này trong profile runtime của môi trường dùng migration job riêng. Cần bảo đảm profile và biến môi trường được áp dụng đúng trong deployment thực tế; không chỉ tắt ở file local trong khi production vẫn bật.

Một mô hình cấu hình:

~~~text
Migration job:
  Liquibase enabled
  Migration datasource/credentials
  Changelog master
  Run validate + update + post-check

Application runtime:
  Liquibase disabled
  Runtime datasource/credentials
  Không có quyền DDL nếu không cần
~~~

Nếu một ứng dụng có nhiều deployment profile hoặc nhiều DataSource, kiểm tra từng bean/cấu hình Liquibase tùy chỉnh. Tắt property auto-configuration không nhất thiết vô hiệu hóa một Liquibase bean do ứng dụng tự khai báo theo cách riêng.

## 8. Tách tài khoản migration khỏi tài khoản runtime

Đây là một lợi ích quan trọng của migration job riêng.

**Migration account** có thể cần quyền:

- Tạo/cập nhật DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- Tạo bảng/cột/index/constraint trong schema được quản lý.
- Thực hiện data migration được phê duyệt.
- Đọc metadata và chạy precondition.
- Tạo procedure/view/sequence nếu changelog yêu cầu.

**Runtime account** thường chỉ cần quyền:

- SELECT/INSERT/UPDATE/DELETE theo nghiệp vụ.
- Execute procedure hoặc truy cập object được ứng dụng sử dụng.
- Không cần quyền CREATE/ALTER/DROP nếu không có yêu cầu cụ thể.

Không dùng một tài khoản DBA toàn quyền cho cả migration job và application runtime. Tách quyền giảm phạm vi tác động khi credential runtime bị lộ hoặc ứng dụng có lỗi.

Một số DBMS yêu cầu quyền bổ sung cho extension, schema, grant hoặc object đặc biệt. Hãy thử bằng đúng migration account trên database tương đương, không dựa vào việc chạy thành công bằng tài khoản DBA trong môi trường phát triển.

## 9. Dùng cùng artifact để tránh lệch revision

Migration job và application deployment nên gắn với cùng một release revision. Nếu job dùng changelog ở commit X nhưng application được build từ commit Y, schema có thể không tương thích với code được rollout.

Nên lưu:

- Git commit SHA.
- Application artifact/image digest.
- Liquibase changelog revision.
- Liquibase version và JDBC driver version.
- Target ID, DBMS/version và schema.
- Release ID và kết quả migration.

Một lựa chọn là đóng gói changelog cùng application artifact và chạy migration command từ chính image đó. Một lựa chọn khác là tạo migration image riêng từ cùng commit, chứa cùng changelog và dependency tương thích. Dù chọn cách nào, pipeline cần xác minh hai artifact thuộc cùng release.

Không tải changelog từ nhánh Git thay đổi liên tục trong lúc production deployment đang chạy. Hãy dùng revision bất biến đã được review.

## 10. Pipeline stages: validate, preview, update, verify

Một pipeline điển hình:

| Giai đoạn | Mục tiêu | Điều kiện qua bước |
|---|---|---|
| Build | Tạo artifact và đóng gói changelog | Build thành công, revision cố định |
| Validate | Kiểm tra cấu trúc changelog/resource | Không có lỗi parse/reference |
| Target check | Xác minh DB, schema, DBMS và credential | Target fingerprint khớp |
| Status | Xem changeset pending | Danh sách pending đúng dự kiến |
| SQL preview | Sinh SQL dự kiến | Reviewer chấp thuận DDL/DML |
| Update | Thực thi migration | Job kết thúc thành công |
| Post-check | Kiểm tra history/schema/data | Invariant đạt |
| Application rollout | Deploy code tương thích | Migration gate PASS |
| Smoke/health | Xác nhận app hoạt động | Readiness và test PASS |

Các lệnh CLI thường gặp:

~~~text
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
~~~

Tên lệnh, option và cách gọi có thể khác theo Liquibase version hoặc Maven/Gradle plugin. Dùng đúng wrapper/configuration của dự án. Validate không chứng minh SQL chắc chắn chạy được trên DBMS; update-sql không thực thi migration; cả hai đều không thay thế post-check dữ liệu thật.

## 11. SQL preview và approval cho production

SQL preview giúp reviewer thấy những thay đổi dự kiến trước khi job ghi vào database:

- CREATE/ALTER/DROP TABLE hoặc COLUMN.
- CREATE/DROP INDEX.
- ADD/DROP constraint.
- UPDATE/DELETE/INSERT.
- SQL tùy chỉnh từ sql/sqlFile.
- Các thay đổi theo DBMS filter, context và label.

Reviewer cần chú ý phạm vi WHERE, thao tác phá hủy, thời gian lock, DDL có implicit commit, transaction, data volume và rollback.

Có thể thiết kế approval gate riêng:

~~~text
Generate update SQL
       |
       v
Store artifact + checksum
       |
       v
Human/automated review
       |
       v
Approval for target/environment
       |
       v
Run Liquibase update using same revision
~~~

SQL preview và SQL thực thi phải dùng cùng changelog, properties, DBMS, context/label và target. Nếu pipeline thay đổi tham số giữa preview và update, reviewer có thể đã duyệt một tập changeset khác.

Không gửi SQL preview có thông tin nhạy cảm ra hệ thống log hoặc artifact công khai.

## 12. Migration job trong CI/CD

Một job migration độc lập cần nhận các đầu vào rõ:

- Target ID hoặc environment/database alias.
- Connection profile và secret được cấp đúng phạm vi.
- Master changelog.
- Release revision.
- Liquibase version và driver.
- Context/label/dbms filters nếu sử dụng.
- Timeout, retry policy và approval.
- Readiness/post-check.

Pseudo workflow:

~~~text
migration:
  image: application-release-image
  environment: production
  script:
    - verify-target
    - liquibase validate
    - liquibase status --verbose
    - liquibase update-sql
    - require-approval
    - liquibase update
    - verify-schema-and-data
  artifacts:
    - migration-log
    - update-sql-review
    - release-metadata
~~~

Đây là sơ đồ logic, không phải cú pháp chạy trực tiếp cho mọi CI platform. Các trường \`script\`, \`artifacts\`, approval và environment cần chuyển thành cấu hình phù hợp với hệ thống CI/CD đang dùng.

Quan trọng là application deployment **phụ thuộc vào kết quả migration job**. Nếu migration thất bại hoặc post-check không đạt, pipeline phải chặn rollout code yêu cầu schema mới.

## 13. Kubernetes Job: chạy migration một lần theo release

Một Kubernetes Job có thể dùng image đã build để thực thi Liquibase:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: customer-db-migration-release-2026-11
spec:
  completions: 1
  parallelism: 1
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: liquibase
          image: registry.example.invalid/customer-service:release-2026-11
          command:
            - /app/bin/run-migration
          envFrom:
            - secretRef:
                name: customer-db-migration-secret
~~~

Đây là cấu hình minh họa. Image phải chứa đúng Liquibase runtime, driver, changelog và wrapper command. Secret phải có quyền đúng target. Cần cân nhắc Job TTL, activeDeadlineSeconds, service account, network policy, resource limits, log retention và cleanup theo nền tảng.

Pipeline nên đợi Job hoàn tất, thu thập log và chạy post-check trước khi rollout Deployment. Không tạo một Job mới cho mỗi pod; một release migration job cần có danh tính riêng và được orchestration kiểm soát.

## 14. Vì sao không nên dựa vào init container cho migration dùng chung?

Init container được chạy cho từng Pod trước container ứng dụng của Pod đó. Nếu mỗi Pod gọi Liquibase:

- Nhiều process có thể cùng kiểm tra/update.
- Các process có thể xếp hàng chờ DATABASECHANGELOGLOCK.
- Pod startup phụ thuộc thời gian migration.
- Scale-out có thể tạo migration process mới.
- Lỗi kết nối hoặc lock wait có thể làm Pod không bao giờ Ready.
- Việc restart pod có thể tạo thêm lần thử migration ngoài lịch release.

Liquibase lock có thể giảm nguy cơ hai Liquibase process cùng ghi history trên cùng bảng lock, nhưng nó không biến các init container thành một release coordinator. Nó cũng không quản lý Flyway, SQL thủ công hoặc migration tới database khác.

Nếu cần một bước chuẩn bị database, dùng Job/runner độc lập có owner rõ ràng và để Deployment phụ thuộc kết quả của Job.

## 15. Kiểm soát single-writer cho mỗi database

Trong một thời điểm, nên có một migration owner được xác định cho mỗi database/schema có lịch sử chung.

Các nguồn chạy migration có thể gồm:

- CI/CD job.
- Spring Boot startup auto-run.
- Kubernetes Job.
- DBA chạy CLI.
- Maven/Gradle plugin.
- Một service quản trị riêng.

Nếu nhiều nguồn cùng chạy, cần quy định nguồn nào được phép hoạt động trong từng release. DATABASECHANGELOGLOCK điều phối các Liquibase process cùng sử dụng bảng lock tương ứng, nhưng không thay thế policy single-writer.

Một pipeline tốt:

1. Serialize migration job theo target database.
2. Chặn job mới nếu job trước còn running.
3. Xác minh database và schema trước khi lấy lock.
4. Không auto-release lock khi job timeout mà chưa xác minh owner.
5. Kiểm tra DATABASECHANGELOG và schema sau khi job lỗi.
6. Chỉ retry khi trạng thái thực tế đã rõ.

Không xóa hoặc sửa DATABASECHANGELOGLOCK bằng SQL chỉ để cho pipeline chạy tiếp. Nếu nghi stale lock, xác minh process/session và dùng quy trình Liquibase được hỗ trợ.

## 16. Readiness gate giữa migration và application rollout

Migration job thành công là điều kiện cần, nhưng không phải lúc nào cũng đủ. Một readiness gate có thể kiểm tra:

- Database đúng target và schema.
- Changeset mong đợi đã được ghi nhận trong DATABASECHANGELOG.
- Cột, bảng, index và constraint tồn tại đúng định nghĩa.
- Backfill đạt invariant và row count mong đợi.
- Reference data đã có.
- Không còn migration job khác đang chạy.
- Ứng dụng phiên bản sắp deploy có thể sử dụng schema mới.
- CDC/ETL hoặc consumer liên quan đã sẵn sàng nếu có.

Ví dụ kiểm tra chỉ đọc:

~~~sql
SELECT COUNT(*)
FROM customer
WHERE status IS NULL;
~~~

Nếu migration vừa backfill status và release yêu cầu không còn NULL, gate có thể yêu cầu kết quả bằng 0. Query thực tế phải phù hợp schema, quy mô và chính sách dữ liệu; không log các hàng chứa PII.

Không chỉ kiểm tra process exit code. Changeset có thể dùng MARK_RAN, hoặc SQL chạy thành công nhưng không tác động hàng nào; hậu điều kiện nghiệp vụ mới chứng minh kết quả mong muốn.

## 17. Expand–migrate–contract: tránh yêu cầu app và schema đổi cùng lúc

Khi application và database được triển khai ở hai bước riêng, phải giữ tương thích trong khoảng chuyển tiếp.

**Expand:**

- Thêm cột/bảng mới ở trạng thái tương thích.
- Giữ trường cũ và logic cũ.
- Không đặt constraint phá vỡ phiên bản ứng dụng đang chạy.
- Deploy code có thể đọc/ghi cả hai cấu trúc khi cần.

**Migrate:**

- Chuyển dữ liệu theo batch hoặc changeset phù hợp.
- Xác minh invariant.
- Chuyển dần traffic hoặc logic đọc sang cấu trúc mới.
- Theo dõi lỗi và hiệu năng.

**Contract:**

- Xác nhận không còn application instance cũ.
- Dừng ghi/đọc cấu trúc cũ.
- Xóa cột/bảng/index cũ theo kế hoạch.
- Chỉ contract khi rollback/restore và phụ thuộc đã được đánh giá.

Ví dụ release:

~~~text
Release 1: database expand
Release 2: application hỗ trợ schema cũ + mới
Release 3: backfill và chuyển đọc/ghi
Release 4: database contract sau thời gian ổn định
~~~

Tách migration khỏi startup giúp tổ chức những giai đoạn này rõ ràng, nhưng không tự bảo đảm backward compatibility. Changelog và application code vẫn cần được thiết kế cùng nhau.

## 18. Migration thất bại: chặn rollout và điều tra trước retry

Nếu migration job thất bại:

1. Chặn application rollout phụ thuộc schema mới.
2. Xác định target, release revision và changeset gây lỗi.
3. Đọc log Liquibase, SQLState/vendor code và trạng thái connection.
4. Kiểm tra DATABASECHANGELOG và DATABASECHANGELOGLOCK.
5. Kiểm tra schema/data thực tế để phát hiện thay đổi một phần.
6. Xác định DBMS có rollback DDL trong transaction hay không.
7. Kiểm tra session còn hoạt động hoặc đang chờ DBMS lock.
8. Quyết định sửa cấu hình, cấp quyền, forward fix hay rollback.
9. Chạy lại cùng revision chỉ khi trạng thái đã được xác minh.
10. Hậu kiểm trước khi mở rollout.

Không mặc định job exit non-zero có nghĩa database không thay đổi gì. DDL có thể autocommit; changeset dùng runInTransaction=false có thể để lại tác động từng phần; kết nối có thể mất sau khi SQL thành công nhưng trước khi lịch sử được ghi nhận.

Không xóa row DATABASECHANGELOG hoặc gọi clearCheckSums để ép chạy lại khi chưa biết trạng thái thực tế.

## 19. Rollback application không nhất thiết rollback database

Một lỗi ở phiên bản ứng dụng mới không có nghĩa phải rollback schema ngay lập tức.

Nếu database đã được expand theo cách backward-compatible, có thể:

- Dừng rollout application mới.
- Đưa traffic về phiên bản ứng dụng cũ.
- Giữ schema mở rộng.
- Điều tra lỗi code.
- Sửa application và deploy lại.

Đây thường là lựa chọn ít phá hủy hơn việc drop cột/bảng vừa được thêm, đặc biệt nếu ứng dụng mới đã ghi dữ liệu vào đó.

Rollback database chỉ nên thực hiện khi có phạm vi rõ, SQL preview, bằng chứng dữ liệu an toàn và kế hoạch phục hồi. Liquibase rollback không phải backup; rollback DDL không tự khôi phục giá trị đã mất.

Với migration không thể đảo ngược, ưu tiên forward fix hoặc restore/PITR theo runbook đã được kiểm chứng.

## 20. Tách quyền và trách nhiệm giữa pipeline và ứng dụng

| Trách nhiệm | Migration job | Application runtime |
|---|---|---|
| Đọc changelog | Có | Không cần nếu đã tắt auto-run |
| DDL | Theo phạm vi được duyệt | Thường không |
| DML migration | Có khi cần | DML nghiệp vụ bình thường |
| DATABASECHANGELOG | Có quyền quản lý | Không cần ghi |
| Secret migration | Có | Không cần |
| Runtime datasource | Có thể dùng profile riêng | Có |
| Readiness/health | Post-migration gate | Application health |
| Audit release | Lưu migration record | Lưu application deployment record |

Tách quyền giúp nguyên tắc least privilege dễ thực hiện hơn. Nếu ứng dụng runtime cần quyền đặc biệt, phải có lý do và giới hạn rõ, không dùng migration account làm datasource mặc định cho mọi request.

## 21. Nhiều database và nhiều DataSource

Nếu một ứng dụng có nhiều database, một migration job có thể được tạo cho từng target, hoặc một orchestrator gọi lần lượt theo dependency.

Ví dụ:

~~~text
customer-migration-job
          |
          v
customer-ready gate
          |
          v
order-migration-job
          |
          v
order-ready gate
          |
          v
application rollout
~~~

Mỗi job có connection profile, master changelog, DATABASECHANGELOG và DATABASECHANGELOGLOCK theo target. Liquibase lock ở database A không khóa database B; thứ tự giữa chúng phải do pipeline điều phối.

Trong Spring Boot, nhiều DataSource cần cấu hình Liquibase rõ cho từng datasource nếu chọn startup migration. Không giả định auto-configuration mặc định tự xử lý tất cả. Với production, migration job riêng thường giúp phân tách target, secret, quyền và lỗi rõ hơn.

## 22. Quan sát migration job

Một migration job cần log và metric riêng, tối thiểu gồm:

- Release ID, target ID và environment.
- Commit SHA/artifact digest.
- Liquibase version, JDBC driver và DBMS version.
- Changelog master và context/label/dbms filter.
- Thời điểm bắt đầu/kết thúc.
- Changeset đang chạy và kết quả.
- Thời gian chờ DATABASECHANGELOGLOCK.
- Thời gian SQL thực thi hoặc chờ DBMS lock nếu quan sát được.
- Error class, SQLState/vendor code.
- Kết quả post-check.
- Người/job owner và approval record.

Không log password, token, full secret URI, private key hoặc nội dung dữ liệu nhạy cảm. Nếu cần lưu SQL preview, áp dụng quyền truy cập và retention tương ứng với thông tin schema của tổ chức.

Dashboard nên phân biệt các trạng thái: PENDING, RUNNING, SUCCESS, FAILED, BLOCKED và NEEDS_RECOVERY. Đây là trạng thái orchestration, không phải EXECTYPE của Liquibase.

## 23. Lỗi thường gặp khi tách migration khỏi startup

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| App khởi động nhưng schema chưa được cập nhật | Pipeline tắt auto-run nhưng migration job chưa chạy | Thêm dependency/gate giữa job và rollout |
| Migration job thành công nhưng app lỗi schema | Job dùng revision/target khác application | Ghim cùng artifact/revision và xác minh target |
| Pod chờ lâu ở startup | App vẫn bật Liquibase auto-run hoặc init container chạy migration | Kiểm tra profile, bean và workload |
| Nhiều job cùng chạy một database | Pipeline thiếu serialization hoặc nhiều nguồn auto-run | Thiết lập single-writer và lock policy |
| Job không tìm thấy changelog | Resource không đóng gói trong image/JAR | Kiểm tra classpath, working directory và artifact |
| Job không tạo được history table | Sai schema hoặc thiếu quyền | Xác minh history schema và migration account |
| Runtime app có quyền DDL rộng | Dùng chung migration credential | Tách datasource/account và thu hẹp quyền |
| SQL preview khác SQL thực thi | Khác revision, properties, filter hoặc DBMS | Dùng cùng artifact/configuration cho hai bước |
| Job timeout nhưng DB đã đổi một phần | DDL autocommit hoặc mất kết nối giữa chừng | Kiểm tra history và schema trước retry |
| Spring Boot nhiều DataSource chỉ migrate một DB | Auto-configuration chỉ gắn datasource được chọn | Cấu hình riêng hoặc dùng job cho từng target |
| Rollback làm mất dữ liệu mới | DDL rollback phá hủy sau khi app đã ghi dữ liệu | Giữ schema mở rộng, forward fix hoặc phục hồi |
| Pipeline tiếp tục dù post-check fail | Gate chỉ kiểm tra exit code | Thêm hậu điều kiện schema/data và chặn rollout |

## 24. Bài thực hành: chuyển từ startup migration sang migration job

Thực hiện trên database disposable, không dùng production.

### Bước 1 — Bắt đầu với startup migration

Tạo một Spring Boot application có Liquibase dependency và master changelog. Bật:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Chạy ứng dụng trên môi trường thử nghiệm, xác nhận changeset được ghi trong DATABASECHANGELOG và schema đạt kết quả mong đợi.

### Bước 2 — Chuẩn bị migration job riêng

Đóng gói cùng changelog và driver trong một image/runner riêng hoặc dùng cùng application artifact với command migration. Cấp migration credential từ secret của môi trường thử nghiệm.

Chạy validate, status và updateSQL trên target thử nghiệm. Review SQL trước khi thực thi.

### Bước 3 — Chạy migration trước application

Thực thi Liquibase update từ job. Kiểm tra DATABASECHANGELOG, schema và dữ liệu. Chỉ đánh dấu job thành công sau post-check.

### Bước 4 — Tắt auto-run trong application runtime

Đặt:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Khởi động ứng dụng bằng runtime credential không có quyền DDL nếu mô hình bảo mật cho phép. Xác nhận ứng dụng vẫn kết nối và thao tác nghiệp vụ bình thường.

### Bước 5 — Kiểm tra gate

Tạo một điều kiện hậu kiểm, ví dụ bảng/cột mới tồn tại và dữ liệu backfill đạt invariant. Cho application deployment phụ thuộc kết quả gate. Cố ý làm gate fail trên môi trường thử để xác nhận application không được rollout.

### Bước 6 — Mô phỏng migration thất bại

Dùng changeset thử nghiệm yêu cầu quyền mà migration account không có. Quan sát pipeline dừng rollout, ghi đúng target/changeset/error. Sau khi điều chỉnh quyền, kiểm tra schema/history rồi mới retry.

### Bước 7 — So sánh hai mô hình

Ghi nhận thời gian startup, thời gian migration, quyền của hai tài khoản, log, khả năng approval và cách phục hồi. Chọn mô hình phù hợp với thời gian migration, số replica và yêu cầu vận hành.

## 25. Checklist thiết kế migration job riêng

- [ ] Đã quyết định startup migration hay migration job dựa trên số replica, thời gian và rủi ro.
- [ ] Chỉ có một migration owner cho mỗi database/schema tại một thời điểm.
- [ ] Migration job và application dùng cùng release revision/artifact đã được review.
- [ ] Changelog master, include và sqlFile có trong artifact.
- [ ] DBMS/version, target database, schema và history location được xác minh.
- [ ] Migration credentials tách khỏi runtime credentials khi phù hợp.
- [ ] Secret được cấp qua secret manager, không commit hoặc log.
- [ ] Pipeline chạy validate, status và SQL preview trước update theo policy.
- [ ] Production có approval gate cho thay đổi cần phê duyệt.
- [ ] Application rollout phụ thuộc migration job và post-check.
- [ ] Spring Boot auto-run được tắt đúng profile khi job riêng là owner.
- [ ] Hibernate ddl-auto và SQL initialization không tự thay đổi schema ngoài kế hoạch.
- [ ] Không dùng init container theo từng Pod để nhân migration process.
- [ ] Timeout/retry được phân biệt theo connection, Liquibase lock, DBMS lock, statement và job.
- [ ] Có kiểm tra DATABASECHANGELOG và schema/data sau migration.
- [ ] Partial failure có runbook; không retry mù quáng hoặc xóa history.
- [ ] Rollback application và rollback database được đánh giá riêng.
- [ ] Schema changes dùng expand–migrate–contract khi cần backward compatibility.
- [ ] Log/metric có target, revision, changeset và error correlation nhưng không lộ secret/PII.
- [ ] Đã thử trên database clone có dữ liệu đại diện và diễn tập migration failure.
- [ ] Có release record, owner, approval và hậu kiểm.

**Ghi nhớ:** Tách migration khỏi bước khởi động ứng dụng khi cần kiểm soát riêng thời điểm, quyền, approval, thời gian và thứ tự triển khai. Một migration job dùng cùng revision changelog với application, chạy trước rollout, có single-writer, SQL preview và post-check rõ ràng sẽ giúp khoanh vùng lỗi và ngăn code mới chạy trên schema chưa sẵn sàng. Startup migration vẫn có thể phù hợp với hệ thống nhỏ và thay đổi ngắn, nhưng trong production nhiều replica hoặc migration phức tạp, job độc lập thường đem lại khả năng điều phối, audit và phục hồi tốt hơn.

