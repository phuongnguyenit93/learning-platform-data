# Thiết lập mức log và thu thập nhật ký phục vụ điều tra

Trong chương **Vận hành** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, log là bằng chứng để hiểu Liquibase đã kết nối tới database nào, nạp changelog nào, chọn changeset nào, thực thi câu lệnh gì và dừng ở bước nào. Khi migration lỗi, một thông báo ngắn như “Migration failed” không đủ để xác định nguyên nhân. Cần có mức log phù hợp, định danh release, thông tin database không nhạy cảm, changeset đang chạy và trạng thái lịch sử để tái dựng diễn biến.

Phạm vi của dịch vụ **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài học áp dụng phạm vi đó vào việc thiết lập logging và thu thập nhật ký phục vụ điều tra, giúp nhóm phân biệt lỗi cấu hình, kết nối, validation, checksum, precondition, SQL, transaction và lock.

Định hướng đầy đủ của dịch vụ: Nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Mục tiêu không phải bật DEBUG cho mọi thành phần trong mọi môi trường. Mục tiêu là **thu được đủ bằng chứng để trả lời câu hỏi vận hành, trong thời gian cần thiết, với phạm vi và quyền truy cập được kiểm soát**.

## 1. Log cần trả lời những câu hỏi nào?

Một bộ log phục vụ điều tra migration cần giúp trả lời:

1. Ai hoặc job nào khởi chạy migration?
2. Release, commit và artifact changelog nào đang được triển khai?
3. Thời điểm bắt đầu/kết thúc là khi nào, mất bao lâu?
4. Liquibase kết nối đúng DBMS, database và schema không?
5. Master changelog và các tệp include nào được nạp?
6. Context, label, dbms filter và parameter nào có hiệu lực?
7. Changeset nào được chọn, bỏ qua, đã chạy hoặc thất bại?
8. Precondition đạt, không đạt hay phát sinh lỗi khi đánh giá?
9. Có lỗi checksum hoặc định danh ID/AUTHOR/FILENAME không?
10. SQL nào được sinh/thực thi và lỗi đến từ DBMS nào?
11. DATABASECHANGELOG và DATABASECHANGELOGLOCK đang ở trạng thái nào?
12. Sau sự cố, database đã thay đổi một phần hay chưa?
13. Có thể retry, rollback hay cần forward fix/restore?

Không phải tất cả câu trả lời đều nằm trong một file log. Cần kết hợp log ứng dụng, log Liquibase, log database, output pipeline, metadata DATABASECHANGELOG và trạng thái schema thực tế.

## 2. Phân biệt các nguồn log

| Nguồn | Nội dung thường có | Dùng để điều tra |
|---|---|---|
| Spring Boot application log | Startup, bean, datasource, exception, readiness | Vì sao ứng dụng không khởi động hoặc không sẵn sàng |
| Liquibase log | Changelog, changeset, validation, lock, update | Liquibase đã làm gì và dừng ở đâu |
| Migration job/CI log | Command, release, artifact, environment, exit code | Job nào chạy, dùng cấu hình nào, kết quả ra sao |
| Database server log | SQL error, deadlock, lock timeout, connection, permission | Engine từ chối câu lệnh hoặc gặp vấn đề runtime |
| Audit/security log | Đăng nhập, quyền, principal, thay đổi được audit | Ai đã truy cập hoặc thực thi hành động được ghi nhận |
| Deployment/orchestrator log | Pod/container restart, rollout, readiness, kill signal | Migration bị dừng do hạ tầng hoặc thứ tự rollout |
| DATABASECHANGELOG | Định danh, thời điểm, thứ tự, EXECTYPE, checksum | Changeset nào đã được Liquibase ghi nhận |
| DATABASECHANGELOGLOCK | Trạng thái khóa và thông tin lock | Có migration runner đang giữ lock hay không |

Mỗi nguồn có vòng đời và định dạng riêng. Không giả định log Liquibase chứa đầy đủ SQL từ database server, hoặc database server log biết release artifact nào đã gửi câu lệnh.

Khi có sự cố, hãy ghi lại mốc thời gian và định danh chung để ghép các nguồn. Đồng hồ máy chạy ứng dụng, pipeline và database cần đồng bộ theo NTP hoặc cơ chế tương đương; nếu lệch giờ, thứ tự sự kiện có thể bị hiểu sai.

## 3. Chọn mức log phù hợp

Mức log quyết định độ chi tiết được ghi. Tên level và cách ánh xạ có thể khác giữa logging framework, phiên bản Spring Boot, Liquibase và adapter logging.

| Mức thường gặp | Nội dung | Cách sử dụng |
|---|---|---|
| ERROR | Lỗi khiến một thao tác thất bại | Luôn thu thập |
| WARN | Điều kiện bất thường hoặc có rủi ro | Thu thập trong vận hành thường ngày |
| INFO | Mốc khởi động, triển khai và kết quả chính | Mức nền phù hợp cho nhiều môi trường |
| DEBUG | Chi tiết xử lý nội bộ và cấu hình đã được log | Bật có thời hạn khi điều tra |
| TRACE | Thông tin rất chi tiết, có thể tạo lượng log lớn | Chỉ bật trong môi trường/phạm vi hẹp nếu cần |

Một số API hoặc adapter dùng FINE/FINER/FINEST thay cho DEBUG/TRACE. Không chuyển đổi tên level một cách máy móc. Hãy kiểm tra logging backend và phiên bản thực tế.

Khuyến nghị:
- Production giữ INFO hoặc mức tương đương làm nền.
- ERROR/WARN luôn được thu thập và cảnh báo theo quy tắc vận hành.
- Tăng chi tiết cho package Liquibase hoặc migration job khi có sự cố.
- Đặt thời hạn bật DEBUG/TRACE và người chịu trách nhiệm tắt.
- Tránh bật TRACE toàn bộ ứng dụng trong giờ cao điểm.
- Không dùng log level thay cho audit trail hoặc database history.

Log quá ít khiến điều tra thiếu bằng chứng. Log quá nhiều làm tăng chi phí lưu trữ, nhiễu thông tin và nguy cơ lộ dữ liệu. Cần chọn level theo câu hỏi cần trả lời.

## 4. Cấu hình logging trong Spring Boot

Spring Boot cho phép cấu hình mức log theo logger/package. Ví dụ application.yaml:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework: INFO
    liquibase: INFO
    liquibase.changelog: DEBUG
    liquibase.executor: DEBUG
~~~

Các logger con ở ví dụ minh họa phạm vi có thể cần điều tra. Tên logger cụ thể và mức thông tin được phát ra phụ thuộc phiên bản Liquibase, logging bridge và backend. Nếu không thấy thông tin mong đợi, kiểm tra tên logger thực tế trong output hoặc tài liệu của phiên bản đang dùng.

Có thể đặt file log:

~~~yaml
logging:
  file:
    name: logs/application.log
~~~

Đường dẫn này chỉ phù hợp khi tiến trình có quyền ghi và môi trường có cơ chế thu gom file. Trong container, thường nên ghi ra stdout/stderr để runtime agent hoặc platform log collector thu thập; nếu ghi file, cần volume, rotation và retention rõ ràng.

Không đặt root=DEBUG trong production chỉ để xem Liquibase. Hãy tăng logger hẹp nhất có thể, ví dụ package Liquibase, và chỉ trong thời gian điều tra.

### Cấu hình theo profile

Có thể giữ mức mặc định ở application.yaml và tăng chi tiết ở profile điều tra:

~~~yaml
# application.yaml
logging:
  level:
    root: INFO
    liquibase: INFO
~~~

~~~yaml
# application-diagnostics.yaml
logging:
  level:
    liquibase: DEBUG
    liquibase.changelog: DEBUG
    liquibase.executor: DEBUG
~~~

Chỉ kích hoạt profile diagnostics qua quy trình được phê duyệt. Profile không phải cơ chế bảo mật; người vận hành vẫn phải kiểm tra log có thể chứa SQL, giá trị dữ liệu hoặc thông tin kết nối.

Nếu thay đổi cấu hình logging động bằng actuator hoặc nền tảng quản trị, giới hạn quyền truy cập endpoint và ghi nhận ai thay đổi mức log, khi nào và trong bao lâu.

## 5. Cấu hình log cho Liquibase CLI

Khi chạy Liquibase độc lập trong CI/CD hoặc migration job, có thể truyền mức log và file output qua tham số CLI được phiên bản hỗ trợ.

Ví dụ:

~~~bash
liquibase   --log-level=INFO   --log-file=liquibase-migration.log   validate
~~~

Khi cần điều tra chi tiết hơn, có thể tăng mức log theo cú pháp của bản CLI, ví dụ:

~~~bash
liquibase   --log-level=FINE   --log-file=liquibase-diagnostics.log   update
~~~

Liquibase có thể sử dụng các mức FINE/FINER/FINEST trong một số phiên bản hoặc adapter; cách đặt mức và tên option cần xác minh bằng help/tài liệu đúng phiên bản. Không giả định mọi bản CLI chấp nhận DEBUG như logging framework của Spring Boot.

Tách log theo command hoặc job giúp tránh trộn validate, update-sql và update vào một file khó đọc. Tuy nhiên, cần giữ chung một deployment/run ID để ghép các phần.

Trong pipeline, lưu stdout/stderr cùng exit code. Nếu CLI hỗ trợ log file riêng, thu thập cả file đó và bảo đảm log collector không bỏ sót output khi job bị kill.

## 6. Ghi lại định danh release và changeset

Một log hữu ích phải gắn được với đúng artifact. Nên ghi các trường:

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| deployment_id | deploy-20261119-1842 | Định danh một lần triển khai |
| release_version | 4.8.0 | Phiên bản phát hành |
| commit_sha | a1b2c3d | Commit chứa changelog |
| artifact_digest | sha256:... | Xác định artifact bất biến |
| environment | staging | Môi trường |
| dbms | PostgreSQL | Engine |
| database_name | customer_service | Database đích, nếu không nhạy cảm |
| liquibase_version | phiên bản đã pin | Công cụ thực thi |
| jdbc_driver_version | phiên bản đã pin | Driver |
| changelog_file | db/changelog/db.changelog-master.yaml | Entry point |
| changeset_id/author | 20261119-001/team-db | Định danh changeset |
| execution_result | success/failure | Kết quả |

Không cần đưa mọi trường vào từng dòng log nếu platform đã có metadata chung. Điều quan trọng là có thể truy vấn hoặc liên kết chúng.

Không ghi:
- Password, token, private key hoặc secret.
- JDBC URL có user/password nhúng trong chuỗi.
- Giá trị cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm.
- Toàn bộ nội dung request nếu không cần.
- SQL literal chứa thông tin nhạy cảm mà không có chính sách bảo vệ.

Tên database/schema cũng có thể là thông tin nhạy cảm trong một số tổ chức; chỉ ghi theo chính sách phân loại dữ liệu nội bộ.

## 7. Structured logging và correlation ID

Log dạng text tự do thuận tiện đọc bằng mắt nhưng khó truy vấn khi số lượng lớn. Structured logging lưu các trường riêng như timestamp, level, logger, message, deployment ID, environment và changeset ID.

Ví dụ JSON minh họa:

~~~json
{
  "timestamp": "2026-11-19T10:42:31.412Z",
  "level": "INFO",
  "service": "customer-service",
  "environment": "staging",
  "deployment_id": "deploy-20261119-1842",
  "release_version": "4.8.0",
  "component": "liquibase",
  "changeset_id": "20261119-001",
  "changeset_author": "team-db",
  "event": "changeset_completed",
  "duration_ms": 824,
  "result": "success"
}
~~~

Đây là schema ví dụ cho hệ thống log; không khẳng định Liquibase tự phát ra đúng JSON với toàn bộ trường trên. Có thể cần logging encoder, MDC hoặc lớp điều phối migration bổ sung để gắn metadata.

**Correlation ID** giúp liên kết các log thuộc cùng một lần triển khai. Có thể dùng deployment_id/run_id từ CI/CD và trace ID cho request ứng dụng.

Đối với migration không gắn với HTTP request, không tạo trace ID giả cho từng changeset nếu không có trace system. Một deployment ID ổn định thường đủ để nối log của CLI, database job và deployment orchestrator.

Nếu dùng MDC:
- Đặt deployment ID trước khi gọi migration.
- Bổ sung changeset ID nếu có hook/observer phù hợp.
- Xóa MDC trong finally để không rò giá trị sang thread/task khác.
- Không đưa secret vào MDC.
- Kiểm tra async executor và thread reuse.

## 8. Những sự kiện Liquibase nên thu thập

Một bộ log vận hành nên nhận diện được các mốc:

1. Migration process bắt đầu.
2. Phiên bản Liquibase và DBMS được xác định.
3. Kết nối database thành công hoặc thất bại.
4. Master changelog được nạp.
5. Changelog con được include.
6. Validation bắt đầu/kết thúc.
7. Changeset được chọn hoặc bị filter.
8. Precondition được đánh giá.
9. Lock được lấy hoặc phải chờ.
10. SQL được sinh/thực thi.
11. Changeset hoàn thành hoặc thất bại.
12. DATABASECHANGELOG được cập nhật.
13. Migration kết thúc và lock được giải phóng.

Không phải mọi phiên bản hoặc logger đều phát ra từng sự kiện với cùng tên. Hãy xác định các event thực tế bằng một lần chạy thử có kiểm soát và tài liệu tương ứng.

Nếu cần số liệu ổn định hơn log text, có thể bổ sung metric:
- Thời gian migration tổng.
- Thời gian từng changeset.
- Số changeset thành công/thất bại.
- Số lần chờ lock.
- Số lần retry.
- Tỷ lệ migration thành công theo DBMS/version.

Không dùng metric có label là giá trị tự do như SQL hoặc tên changeset không giới hạn nếu có thể tạo cardinality rất lớn. Dùng log/tracing cho chi tiết, metric cho tổng hợp.

## 9. Thu thập SQL và update-sql phục vụ review

Trước khi update, có thể tạo SQL dự kiến:

~~~bash
liquibase update-sql
~~~

Output update-sql là bằng chứng về những thay đổi Liquibase dự kiến thực hiện với:
- Database đích hiện tại.
- Changelog artifact hiện tại.
- Context/label/dbms filter.
- Changelog parameters.
- Phiên bản Liquibase và driver.
- Lịch sử DATABASECHANGELOG tại thời điểm sinh.

Lưu output này như artifact của deployment nếu chính sách cho phép. Gắn deployment ID, commit SHA, DBMS và thời điểm sinh để biết SQL thuộc release nào.

Cần phân biệt:
- **update-sql:** SQL dự kiến được sinh ra.
- **Log khi update:** diễn biến lúc Liquibase thực thi.
- **Database server log:** câu lệnh engine nhận được và lỗi runtime.
- **DATABASECHANGELOG:** lịch sử changeset Liquibase ghi nhận.

Update-sql không chứng minh câu lệnh đã chạy thành công. Log update cũng không thay thế bằng chứng schema cuối cùng. Nếu câu SQL có literal nhạy cảm hoặc tên object nhạy cảm, phải áp dụng chính sách lưu trữ và truy cập phù hợp.

## 10. Không nhầm log với DATABASECHANGELOG

DATABASECHANGELOG là bảng lịch sử, không phải log file. Nó thường ghi ID, AUTHOR, FILENAME, DATEEXECUTED, ORDEREXECUTED, EXECTYPE, MD5SUM và các metadata khác tùy phiên bản.

Truy vấn điều tra minh họa:

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
ORDER BY ORDEREXECUTED;
~~~

Nếu bảng history nằm trong schema riêng, cần truy vấn đúng schema đã cấu hình.

Các câu hỏi:
- Changeset thất bại có được ghi nhận hay không?
- Changeset được đánh dấu MARK_RAN hay thực thi thật?
- Checksum có khớp với artifact?
- FILENAME có thay đổi do di chuyển changelog?
- Thứ tự thực thi có đúng release?
- Có changeset nào xuất hiện ngoài dự kiến?

Không kết luận chỉ từ log “Starting changeset”. Hãy đối chiếu hàng history sau sự cố và schema vật lý.

## 11. Thu thập trạng thái DATABASECHANGELOGLOCK

Liquibase sử dụng DATABASECHANGELOGLOCK để điều phối các migration runner trên cùng database. Khi update bị chờ hoặc timeout, cần xác minh lock.

Truy vấn minh họa:

~~~sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

Tên schema và cấu trúc bảng phụ thuộc cấu hình/phiên bản. Kiểm tra đúng bảng được Liquibase sử dụng.

Thu thập:
- LOCKED hiện tại.
- LOCKGRANTED.
- LOCKEDBY.
- Thời điểm migration job bắt đầu.
- Host/pod/process tương ứng.
- Log của tiến trình đang giữ lock.
- Trạng thái process trong orchestrator.

Một lock đang bật không tự chứng minh bị treo. Migration có thể vẫn đang chạy hoặc chờ DDL. Không force release lock khi chưa xác định tiến trình giữ lock đã dừng và database không còn câu lệnh migration đang thực thi.

Nếu cần giải phóng lock sau sự cố, thực hiện theo runbook DBA/Liquibase đã phê duyệt và ghi lại bằng chứng trước/sau.

## 12. Log khi validate hoặc precondition thất bại

Nếu validate hoặc precondition không đạt, cần thu thập:

- Command và tham số đã chạy.
- Changelog file và include chain.
- ID/AUTHOR/FILENAME của changeset liên quan.
- DBMS/version và schema mặc định.
- Context, label, dbms filter.
- Kết quả precondition và onFail/onError.
- Exception đầy đủ cùng root cause.
- Metadata object được kiểm tra.
- DATABASECHANGELOG trước/sau.

Ví dụ precondition:

~~~yaml
preConditions:
  - onFail: HALT
  - tableExists:
      schemaName: app
      tableName: customer
  - not:
      - columnExists:
          schemaName: app
          tableName: customer
          columnName: display_name
~~~

Nếu điều kiện không đạt, log cần giúp phân biệt:
- Bảng không tồn tại.
- Bảng tồn tại ở schema khác.
- Cột đã tồn tại do thao tác ngoài Liquibase.
- Tài khoản không đọc được metadata.
- Precondition SQL bị lỗi.
- Database đang ở release không đúng.

Không đổi onFail sang MARK_RAN chỉ để bỏ qua lỗi. Cần hiểu trạng thái thực tế trước khi quyết định sửa schema hoặc history.

## 13. Log checksum mismatch và điều tra lịch sử

Khi gặp checksum mismatch, thu thập:
1. Thông báo đầy đủ và changeset ID/AUTHOR/FILENAME.
2. MD5SUM hiện lưu trong DATABASECHANGELOG.
3. Commit/artifact changelog đã triển khai trước đó.
4. Commit/artifact hiện tại.
5. Phiên bản Liquibase trước và hiện tại.
6. Thay đổi nội dung changeset trong Git diff.
7. Khả năng FILENAME hoặc logicalFilePath đã đổi.
8. runOnChange/runAlways/validCheckSum nếu có.
9. Lịch sử ở development, staging và production.

Không ghi đè checksum hoặc xóa history trước khi bảo toàn bằng chứng. Một checksum khác có thể do sửa changeset đã chạy, thay đổi đường dẫn, nâng phiên bản thuật toán hoặc khác artifact. Cần phân loại đúng nguyên nhân.

Thông thường, changeset đã triển khai nên được giữ bất biến; thay đổi mới được thêm bằng changeset mới. clear-checksums không phải công cụ để sửa schema drift hoặc làm cho một thay đổi cũ tự chạy lại.

## 14. Log khi SQL thực thi thất bại

Khi một changeset lỗi trong lúc chạy SQL, thu thập:

- SQL dự kiến từ update-sql.
- Log Liquibase quanh thời điểm lỗi.
- SQLState/vendor error code nếu có.
- Exception chain và root cause.
- DBMS server log cùng timestamp.
- Transaction state và loại DDL.
- Lock wait/deadlock/timeout.
- DATABASECHANGELOG và schema thực tế sau lỗi.
- Số hàng/giá trị dữ liệu liên quan, ở dạng đã che hoặc tổng hợp.

Không chỉ copy dòng cuối cùng của stack trace. Root cause có thể nằm sâu hơn, chẳng hạn permission denied, duplicate key, deadlock, invalid identifier hoặc timeout.

Nếu log SQL có literal chứa dữ liệu nhạy cảm, không gửi nguyên văn ra hệ thống ticket/chat không được phép. Hãy redaction hoặc thay bằng placeholder và giữ bản gốc trong kho log có quyền truy cập kiểm soát.

## 15. Correlate log ứng dụng và log migration

Nếu Liquibase chạy khi Spring Boot startup, có thể liên kết log theo:
- Application instance/pod.
- Deployment ID.
- Release version.
- Environment.
- DBMS/database alias.
- Startup attempt.
- Changeset identity.

Nếu migration chạy trong job riêng:
- Gắn cùng release ID với application deployment.
- Ghi artifact digest và commit SHA.
- Ghi job ID, runner/host và thời điểm.
- Ghi DB target alias.
- Đưa output migration vào cùng deployment record.
- Liên kết với rollout application sau migration.

Một timeline mẫu:

~~~text
10:00:00  deploy job started       deploy-1842
10:00:04  liquibase validate PASS  deploy-1842
10:00:07  liquibase update-sql     deploy-1842
10:00:12  approval granted         deploy-1842
10:00:15  liquibase update started deploy-1842
10:00:16  changeset 001 completed  deploy-1842
10:00:18  changeset 002 failed     deploy-1842
10:00:19  database error captured deploy-1842
10:00:23  job marked failed        deploy-1842
10:03:00  investigation opened     deploy-1842
~~~

Timeline này chỉ minh họa cách nối sự kiện; không đại diện cho thời gian thực tế. Mỗi hệ thống cần dùng timestamp có timezone và một deployment ID thống nhất.

## 16. Thu thập log trong Spring Boot

Khi Liquibase tích hợp qua auto-configuration, log có thể xuất hiện trong log startup cùng các bean khác. Để điều tra:

1. Lưu toàn bộ startup log từ đầu tiến trình, không chỉ phần exception cuối.
2. Ghi phiên bản Spring Boot, Liquibase, JDBC driver và Java.
3. Ghi profile và tên cấu hình không nhạy cảm.
4. Ghi DB target alias và schema.
5. Thu thập logger Liquibase ở mức phù hợp.
6. Ghi root cause và stack trace.
7. Đọc DATABASECHANGELOG/LOCK.
8. Xác minh datasource Liquibase và datasource ứng dụng có trỏ đúng mục tiêu.
9. Kiểm tra readiness, restart count và termination signal.
10. Gắn log với deployment ID.

Nếu ứng dụng bị restart liên tục, log collector phải giữ được log của các container/pod trước đó. Chỉ đọc log container hiện tại có thể bỏ mất lần migration thất bại đầu tiên.

Không bật endpoint quản trị logging công khai. Nếu dùng actuator để thay đổi level, giới hạn network, authentication và audit.

## 17. Thu thập log từ CI/CD hoặc migration job

Một job migration nên lưu các artifact vận hành sau:

| Artifact | Nội dung |
|---|---|
| command-summary | Command đã chạy và option không nhạy cảm |
| changelog-revision | Commit SHA hoặc artifact digest |
| validate-output | Kết quả validation |
| status-output | Danh sách changeset pending |
| update-sql | SQL dự kiến được review |
| migration-log | Log thực thi |
| exit-status | Exit code của tiến trình |
| dbms-metadata | DBMS/version/driver |
| history-snapshot | Trạng thái DATABASECHANGELOG trước/sau theo chính sách |
| post-check | Kết quả kiểm tra schema/data sau migration |

Không nhất thiết mọi hệ thống phải lưu bản dump đầy đủ DATABASECHANGELOG nếu dữ liệu đó đã có thể truy vấn an toàn. Hãy chọn artifact đủ để audit mà không sao chép dữ liệu không cần thiết.

Log pipeline cần giữ:
- Job ID và attempt number.
- Người/identity khởi chạy hoặc phê duyệt.
- Environment và target alias.
- Thời gian bắt đầu/kết thúc.
- Artifact version.
- Exit code và trạng thái.
- Link tới log database nếu được phép.

Nếu job retry, mỗi attempt phải có định danh riêng nhưng cùng deployment ID cha. Điều này giúp phân biệt lần chạy đầu đã tạo một phần schema với lần retry sau.

## 18. Thu thập log database server

Database server log thường là nơi duy nhất thể hiện rõ một số lỗi engine:
- SQL syntax/vendor error.
- Permission denied.
- Deadlock.
- Lock timeout.
- Connection limit.
- Transaction abort.
- Disk/temp/WAL/transaction log exhaustion.
- Replication lag hoặc failover.
- DDL lock kéo dài.

Khi yêu cầu DBA hỗ trợ, cung cấp:
- DBMS và version.
- Database/schema alias.
- Timestamp có timezone.
- Deployment ID.
- SQLState/vendor error code.
- Changeset ID.
- Session ID/process ID nếu có và được phép.
- SQL đã redaction.
- Thời gian chờ/timeout.
- Bằng chứng lock và transaction state.

Không yêu cầu DBA bật log toàn bộ statement hoặc bind parameter trong production một cách vô thời hạn. Việc tăng database logging có thể ảnh hưởng hiệu năng, dung lượng và quyền riêng tư. Hãy dùng phạm vi, thời gian và chính sách audit được phê duyệt.

## 19. Redact secret và dữ liệu nhạy cảm

Log có thể vô tình chứa:
- JDBC URL kèm username/password.
- Access token, API key hoặc certificate path.
- SQL literal có email, số điện thoại hoặc thông tin khách hàng.
- Giá trị bind parameter.
- Dữ liệu seed hoặc dữ liệu backfill.
- File path hoặc tên host nội bộ.
- Stack trace có giá trị cấu hình.

Nguyên tắc:
1. Không log secret ngay từ đầu.
2. Dùng biến môi trường/secret manager và tránh nối secret vào message.
3. Redact URL trước khi ghi.
4. Không bật bind-parameter logging rộng trong production.
5. Che dữ liệu cá nhân trong SQL/error context.
6. Giới hạn quyền đọc log theo vai trò.
7. Mã hóa khi truyền và lưu.
8. Có retention và quy trình xóa theo chính sách.
9. Ghi audit khi truy cập log nhạy cảm.
10. Kiểm tra redaction trước khi đính kèm log vào ticket.

Ví dụ một URL không nên xuất hiện trong log:

~~~text
jdbc:postgresql://db.internal:5432/customer?user=admin&password=secret
~~~

Thay bằng thông tin không nhạy cảm:

~~~text
db_target=customer-service-prod
dbms=PostgreSQL
connection_result=failed
error_code=08001
~~~

Không giả định log platform tự động che mọi secret. Hãy thử redaction với dữ liệu giả và kiểm tra đầu ra trước khi triển khai.

## 20. Lưu trữ, rotation và retention

Log migration có giá trị điều tra và audit, nhưng không nên lưu vô thời hạn hoặc để file tăng không giới hạn.

Cần quy định:
- Nơi lưu stdout/stderr và file log.
- Rotation theo dung lượng/thời gian.
- Retention theo môi trường và yêu cầu audit.
- Quyền truy cập và mã hóa.
- Cách tìm theo deployment ID/changeset.
- Cách export log cho điều tra.
- Cách giữ log khi pod/container bị xóa.
- Cách xử lý log có dữ liệu nhạy cảm.
- Đồng bộ thời gian và timezone.

Nếu chạy container, ghi log ra stdout/stderr thường giúp platform thu thập tập trung. Nếu dùng file, cấu hình rotation và volume rõ ràng. Không ghi log vào filesystem ephemeral rồi kỳ vọng có thể điều tra sau khi container bị xóa.

Log debug có thể được giữ ngắn hơn log audit hoặc deployment summary. Phân loại theo mục đích thay vì một thời hạn chung.

## 21. Runbook điều tra một lần Liquibase update thất bại

Khi nhận cảnh báo migration fail:

### Bước 1 — Xác định lần chạy

Ghi deployment ID, release, commit, artifact, environment, DB target alias, DBMS/version và thời gian.

### Bước 2 — Bảo toàn bằng chứng

Thu thập stdout/stderr, Liquibase log, CI job log, application startup log và database server log. Không xóa log hoặc chạy lại ngay.

### Bước 3 — Xác định changeset

Tìm ID/AUTHOR/FILENAME và thông báo lỗi đầu tiên. Đọc các dòng log trước exception để biết Liquibase đang validate, lấy lock, chạy precondition hay thực thi SQL.

### Bước 4 — Kiểm tra lịch sử

Đọc DATABASECHANGELOG và DATABASECHANGELOGLOCK. So sánh trạng thái trước/sau nếu có snapshot. Xác định changeset đã được ghi nhận, MARK_RAN, thất bại hay chưa bắt đầu.

### Bước 5 — Kiểm tra database thực tế

Kiểm tra bảng/cột/constraint/index liên quan, dữ liệu và transaction state. DDL có thể không rollback nguyên tử trên một số DBMS; không suy luận schema vẫn nguyên trạng chỉ vì changeset không được ghi vào history.

### Bước 6 — Phân loại nguyên nhân

- Kết nối/credentials.
- Permission/schema.
- Changelog parse/include.
- Context/label/dbms filter.
- Precondition.
- Checksum/identity.
- SQL syntax/capability.
- Constraint/data.
- Lock/deadlock/timeout.
- Hạ tầng/job termination.

### Bước 7 — Chọn hành động

Chỉ retry khi trạng thái database đã rõ và changeset có thể chạy an toàn. Nếu có object được tạo một phần, lập kế hoạch reconcile hoặc forward fix. Nếu cần rollback, kiểm tra dữ liệu và rollback SQL trước khi thực hiện.

### Bước 8 — Xác minh sau khắc phục

Chạy validate/status/update-sql, review output, thực hiện theo phê duyệt và kiểm tra history/schema/data. Ghi lại nguyên nhân gốc và hành động phòng ngừa.

Không dùng clear-checksums, xóa DATABASECHANGELOG hoặc release lock cưỡng bức làm bước đầu tiên của runbook.

## 22. Ví dụ truy vấn điều tra lịch sử

### Changeset đã được ghi nhận

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
WHERE ID = '20261119-001'
ORDER BY DATEEXECUTED;
~~~

Thay ID bằng định danh thực tế. Nếu có thể trùng ID giữa author/file khác nhau, phải lọc cả AUTHOR và FILENAME.

### Kiểm tra lock

~~~sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

### Kiểm tra cột sau migration

~~~sql
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'customer'
ORDER BY ordinal_position;
~~~

Các truy vấn metadata cần điều chỉnh theo DBMS và quyền. Với Oracle, SQL Server hoặc các engine khác, catalog có thể có cấu trúc khác.

Khi chia sẻ kết quả, loại bỏ dữ liệu cá nhân hoặc tên object nhạy cảm theo chính sách. Lưu lại thời điểm truy vấn và database alias để kết quả có thể truy vết.

## 23. Phân biệt lỗi migration với lỗi ứng dụng sau migration

Có thể migration đã hoàn tất nhưng ứng dụng mới lỗi do mapping hoặc query. Cũng có thể ứng dụng startup thất bại trước khi Liquibase bắt đầu vì datasource chưa kết nối.

| Dấu hiệu | Khả năng | Bằng chứng cần xem |
|---|---|---|
| Không tạo được datasource | URL/driver/credentials/network | Spring Boot root cause, DB connection log |
| Liquibase không tìm thấy changelog | Resource/classpath/config | Log include, artifact content |
| Validation thất bại | Changelog/ID/checksum/precondition | Liquibase log và DATABASECHANGELOG |
| SQL bị DBMS từ chối | Syntax/permission/data/lock | Liquibase exception và DB server log |
| Liquibase thành công, Hibernate validate fail | Mapping/schema mismatch | Entity, metadata schema, release artifact |
| Startup thành công, API lỗi | Query/data/contract | Application trace, SQL log được bảo vệ, data assertion |
| Pod restart trong migration | OOM/termination/probe/timeout | Orchestrator event, process exit, DB lock/history |

Phân loại đúng giúp tránh thay đổi changelog khi nguyên nhân thật là datasource, quyền hoặc ứng dụng. Log migration chỉ là một phần của bằng chứng.

## 24. Ví dụ cấu hình logging theo hai môi trường

Development có thể cần chi tiết hơn:

~~~yaml
# application-dev.yaml
logging:
  level:
    root: INFO
    liquibase: DEBUG
    liquibase.changelog: DEBUG
~~~

Production giữ mức nền:

~~~yaml
# application-prod.yaml
logging:
  level:
    root: INFO
    liquibase: INFO
~~~

Khi có sự cố production, có thể bật logger Liquibase chi tiết hơn qua cơ chế quản trị được bảo vệ và có thời hạn. Sau điều tra, trả về mức bình thường.

Đối với migration job riêng, đặt mức log ở command hoặc cấu hình runtime của CLI. Đừng cho rằng application.yaml của Spring Boot tự động ảnh hưởng đến một tiến trình Liquibase CLI độc lập.

Mỗi lần thay đổi log level nên có:
- Người yêu cầu và người phê duyệt.
- Lý do.
- Logger/package cụ thể.
- Mức cũ và mức mới.
- Thời gian bắt đầu/kết thúc.
- Nơi lưu log.
- Người chịu trách nhiệm tắt.
- Kiểm tra secret/data redaction.

## 25. Chẩn đoán vấn đề logging

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không thấy log Liquibase | Logger level, backend hoặc auto-configuration không hoạt động | Kiểm tra classpath, logger name và startup |
| DEBUG không tạo thêm thông tin | Đặt sai package hoặc adapter level khác | Xác minh logger thực tế và phiên bản |
| Có log nhưng thiếu changeset ID | Format/observer không đưa metadata | Liên kết bằng deployment ID và history |
| Log mất sau pod restart | Chỉ ghi file trong filesystem ephemeral | Thu thập stdout/stderr hoặc persistent volume |
| Không ghép được CI và DB log | Timestamp lệch hoặc thiếu run ID | Đồng bộ clock và dùng deployment ID |
| File log tăng không giới hạn | Chưa cấu hình rotation/retention | Cấu hình rotation và collector |
| Log lộ JDBC password | URL bị ghi nguyên văn | Redact, rotate secret nếu cần, sửa nguồn phát log |
| Log quá lớn | DEBUG/TRACE toàn hệ thống | Thu hẹp package và thời gian |
| SQL không có trong log | Mức log/adapter không ghi SQL hoặc command khác | Thu update-sql và DB server log có kiểm soát |
| Không biết changeset đã chạy chưa | Chỉ đọc exception | Đối chiếu DATABASECHANGELOG và schema thực tế |
| Lock báo đang giữ lâu | Migration vẫn chạy hoặc process bị dừng | Kiểm tra process, DB session và orchestrator |
| Log không khớp release | Artifact/commit không được ghi nhận | Gắn commit SHA và artifact digest vào job |

## 26. Bài thực hành: thu thập log cho một migration thất bại

**Bối cảnh:** Spring Boot tích hợp Liquibase. Một changeset thêm unique constraint vào bảng customer nhưng update thất bại vì dữ liệu email bị trùng ở staging.

### Phần A — Chuẩn bị logging

1. Cấu hình root ở INFO.
2. Tăng logger Liquibase ở mức DEBUG trong môi trường test.
3. Gắn deployment ID và release version vào log pipeline.
4. Bảo đảm không log password hoặc giá trị khách hàng.
5. Lưu stdout/stderr và log database server.

### Phần B — Tạo lỗi có kiểm soát

1. Tạo database test từ changelog trước đó.
2. Chèn hai customer có email trùng theo quy tắc unique.
3. Chạy validate, status và update-sql.
4. Chạy update trên database test.
5. Thu thập exception, SQLState/vendor code và changeset ID.
6. Ghi nhận timestamp, DBMS/version và job ID.

### Phần C — Điều tra

1. Xác định changeset thất bại.
2. Đọc DATABASECHANGELOG để biết changeset đã được ghi nhận hay chưa.
3. Kiểm tra schema và dữ liệu thực tế.
4. Kiểm tra DB server log để xác nhận unique violation.
5. Xác định transaction có rollback hay không.
6. Đếm và phân loại các giá trị email trùng.
7. Không xóa history hoặc retry trước khi dữ liệu được xử lý.

### Phần D — Khắc phục và xác minh

1. Thiết kế quy trình xử lý duplicate theo nghiệp vụ.
2. Chạy audit dữ liệu trước khi thêm constraint.
3. Thêm precondition/sqlCheck phù hợp nếu cần.
4. Chạy validate và update-sql lại.
5. Review và chạy update.
6. Kiểm tra constraint, DATABASECHANGELOG và log.
7. Hạ log level về mức vận hành bình thường.
8. Lưu báo cáo nguyên nhân và biện pháp phòng ngừa.

### Câu hỏi tự kiểm tra

- Log INFO có đủ để điều tra mọi lỗi SQL không? **Không.** Có thể cần log chi tiết tạm thời và database server log.
- Bật DEBUG root trong production có phải cách tốt nhất không? **Không.** Nên tăng logger Liquibase có phạm vi và thời hạn.
- Log “changeset failed” có chứng minh schema không đổi không? **Không.** Cần kiểm tra transaction và schema thực tế.
- DATABASECHANGELOG có phải log file không? **Không.** Đây là lịch sử changeset do Liquibase quản lý.
- Có thể giải phóng DATABASECHANGELOGLOCK ngay khi thấy LOCKED=true không? **Không.** Phải xác minh tiến trình giữ lock và DB session.
- Update-sql có chứng minh SQL đã chạy không? **Không.** Nó chỉ sinh SQL dự kiến.
- Có nên log toàn bộ bind parameter trong production không? **Không mặc định.** Có thể làm lộ dữ liệu và tăng chi phí.
- Làm sao nối log CI với DB server log? **Dùng deployment ID, timestamp có timezone, DB target alias và session/process ID khi được phép.**

## 27. Checklist logging và điều tra migration

**Cấu hình**
- [ ] Root logging level phù hợp với môi trường.
- [ ] Logger Liquibase được cấu hình theo package/phạm vi cần thiết.
- [ ] CLI và Spring Boot được cấu hình độc lập đúng cách.
- [ ] DEBUG/TRACE có thời hạn và người chịu trách nhiệm.
- [ ] File log có rotation hoặc stdout/stderr được collector thu thập.

**Định danh và liên kết**
- [ ] Có deployment ID, release version, commit SHA hoặc artifact digest.
- [ ] Có DBMS/version, DB target alias và Liquibase version.
- [ ] Có changeset ID/AUTHOR/FILENAME khi điều tra một change.
- [ ] Timestamp có timezone và đồng hồ được đồng bộ.
- [ ] Log pipeline, application và database có thể được liên kết.

**Bằng chứng**
- [ ] Thu stdout/stderr và Liquibase log.
- [ ] Lưu validate/status/update-sql và exit code khi phù hợp.
- [ ] Đọc DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- [ ] Thu database server log khi có SQL error/lock/deadlock.
- [ ] Kiểm tra schema và dữ liệu thực tế sau lỗi.
- [ ] Bảo toàn log trước retry hoặc recovery.

**Bảo mật và vận hành**
- [ ] Không ghi password, token hoặc secret.
- [ ] SQL literal và dữ liệu cá nhân được redaction.
- [ ] Quyền đọc log được giới hạn.
- [ ] Có mã hóa, retention và audit truy cập.
- [ ] Không bật log toàn hệ thống quá lâu.
- [ ] Không xóa history hoặc release lock khi chưa điều tra.
- [ ] Có runbook phân loại lỗi và quy trình escalations.
- [ ] Có báo cáo nguyên nhân gốc và bước phòng ngừa sau sự cố.

**Kết luận:** logging tốt giúp biến một lần migration thất bại thành chuỗi sự kiện có thể tái dựng: release nào chạy, database nào được kết nối, changeset nào được chọn, SQL hoặc precondition nào thất bại và lịch sử đã được ghi đến đâu. Kết hợp mức log phù hợp, deployment ID, log Liquibase, database server log, DATABASECHANGELOG và trạng thái schema thực tế sẽ giúp điều tra chính xác hơn. Thu thập vừa đủ, bảo vệ secret, giới hạn thời gian DEBUG/TRACE và giữ runbook rõ ràng là nền tảng để vận hành Liquibase an toàn qua Spring Boot và CI/CD.
