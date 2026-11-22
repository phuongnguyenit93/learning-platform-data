# Cô lập thông tin kết nối, lịch sử và lỗi của từng đích

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi một hệ thống triển khai tới nhiều database, mỗi đích có thể khác nhau về host, database name, schema, DBMS version, tài khoản, quyền, lịch sử migration và trạng thái dữ liệu. Nếu pipeline dùng chung một cấu hình kết nối mơ hồ hoặc gộp log của mọi đích, nhóm rất dễ chạy nhầm database, đọc nhầm lịch sử hoặc xử lý sai một lỗi chỉ xảy ra ở một nơi.

Bài thuộc chương **Nhiều cơ sở dữ liệu** này hướng dẫn cô lập **thông tin kết nối, lịch sử và lỗi của từng đích**. Trọng tâm là định danh target rõ ràng; tách connection profile và secret; xác định schema, bảng DATABASECHANGELOG và DATABASECHANGELOGLOCK; ghi nhận kết quả riêng cho từng database; phân loại lỗi; và điều phối retry/resume mà không làm ảnh hưởng những đích đã hoàn thành.

Phạm vi được xác định bởi **SERVICE_NAME=DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Theo **SERVICE_NAME_DESCRIBE**, module hướng dẫn quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Vì sao phải cô lập từng đích?

Giả sử một release cần cập nhật bốn database:

- `customer_db` trên PostgreSQL cho Customer Service.
- `order_db` trên PostgreSQL cho Order Service.
- `billing_db` trên MySQL cho Billing Service.
- `analytics_db` trên một cụm database riêng cho báo cáo.

Mỗi đích có endpoint, credential, schema, bảng lịch sử, phiên bản DBMS và mức độ sẵn sàng khác nhau. Một job có thể kết nối thành công tới customer_db nhưng thất bại ở billing_db do credential hết hạn. Một changeset có thể đã chạy trên order_db nhưng còn pending trên analytics_db.

Cô lập theo đích giúp:

1. Xác định chính xác database nào đang được thay đổi.
2. Không dùng nhầm credential hoặc schema của service khác.
3. Biết changeset nào đã chạy trên từng database.
4. Khoanh vùng lỗi và người chịu trách nhiệm.
5. Retry database thất bại mà không chạy lại mù quáng những database đã thành công.
6. Giữ bằng chứng audit riêng cho từng target.
7. Hạn chế tác động khi một database chậm, mất kết nối hoặc bị khóa.

**Một release có thể có nhiều database, nhưng mỗi lần chạy Liquibase vẫn phải có một target kết nối xác định.** Không xem danh sách URL trong pipeline như một kết nối duy nhất có trạng thái lịch sử chung.

## 2. Định danh target độc lập với connection string

Mỗi database nên có một **target ID** ổn định, dễ nhận biết và không chứa secret. Ví dụ:

| Target ID | Environment | DBMS | Database | Owner |
|---|---|---|---|---|
| `customer-prod-a` | production | PostgreSQL | customer_db | customer-team |
| `order-prod-a` | production | PostgreSQL | order_db | order-team |
| `billing-prod-a` | production | MySQL | billing_db | billing-team |
| `analytics-prod-a` | production | PostgreSQL | analytics_db | data-platform |

Target ID là nhãn trong orchestration và log. Nó không nhất thiết là tên database hoặc JDBC URL. Cần giữ mapping giữa target ID và connection profile ở một nơi có kiểm soát.

Không đặt mật khẩu, token, chuỗi kết nối chứa credential hoặc thông tin nhạy cảm vào target ID, tên job, changelog hay log.

Trước khi update, pipeline cần hiển thị target ID, environment, DBMS, database/schema alias và revision changelog để người vận hành xác nhận. Thông tin hiển thị phải được lọc để không làm lộ password hoặc tham số kết nối bí mật.

## 3. Tách bốn khái niệm: target, connection, schema và history

Các khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Target** | Đích logic mà release cần quản lý | `order-prod-a` |
| **Connection profile** | Thông tin kết nối để mở session tới đích | JDBC URL, user, secret, TLS |
| **Schema** | Không gian chứa object ứng dụng và/hoặc bảng lịch sử | `orders` |
| **History location** | Vị trí bảng Liquibase ghi lịch sử và khóa | Schema chứa DATABASECHANGELOG và DATABASECHANGELOGLOCK |

Một target có thể kết nối tới một database rồi quản lý một schema cụ thể. Trong một số DBMS, database và schema là hai phạm vi riêng; ở DBMS khác, cách gọi và namespace khác nhau.

Nếu connection đúng nhưng default schema sai, Liquibase có thể tạo bảng lịch sử hoặc object ở vị trí ngoài dự kiến. Nếu schema ứng dụng đúng nhưng history table đặt sai, nhóm có thể đọc nhầm trạng thái hoặc tạo một lịch sử mới không mong muốn.

Vì vậy, mỗi target cần khai báo rõ database, schema ứng dụng, default schema và schema lịch sử theo khả năng DBMS/Liquibase version.

## 4. Một connection profile cho mỗi target

Connection profile nên gồm tối thiểu:

- Target ID và environment.
- JDBC URL hoặc endpoint tương ứng.
- Database/catalog và schema mặc định.
- Username/service account.
- Tham chiếu secret (không phải giá trị secret trong repository).
- TLS/SSL mode, certificate hoặc truststore nếu cần.
- DBMS/driver version dự kiến.
- Liquibase changelog master.
- History table/schema và lock table/schema.
- Timeout và chính sách kết nối phù hợp.

Ví dụ manifest **mang tính khái niệm**:

~~~yaml
targets:
  customer-prod-a:
    dbms: postgresql
    connectionProfile: secret://prod/customer-db-migrator
    database: customer_db
    defaultSchema: customer
    changelog: db/changelog/customer/master.yaml
    historySchema: customer
    owner: customer-team

  billing-prod-a:
    dbms: mysql
    connectionProfile: secret://prod/billing-db-migrator
    database: billing_db
    defaultSchema: billing
    changelog: db/changelog/billing/master.yaml
    historySchema: billing
    owner: billing-team
~~~

Đây là manifest do pipeline hoặc deployment controller diễn giải, **không phải file cấu hình built-in mà Liquibase tự đọc**. Trường `connectionProfile` chỉ là tham chiếu tới secret manager. Không ghi password hoặc token thật vào YAML, Git hay artifact.

## 5. Không dùng một URL mặc định cho mọi target

Một lỗi nguy hiểm là pipeline nhận target ID nhưng vẫn dùng URL mặc định chung. Ví dụ job có tên `liquibase-order-prod` nhưng biến DB_URL còn trỏ tới customer_db.

Để tránh:

1. Mỗi target ID ánh xạ tới đúng một connection profile.
2. Job nhận target như tham số bắt buộc, không có fallback production ngầm.
3. Trước khi chạy, kiểm tra host/database/schema thực tế bằng truy vấn chỉ đọc.
4. So sánh thông tin database trả về với metadata target được phê duyệt.
5. Dừng nếu target alias, DBMS hoặc schema không khớp.
6. Ghi target ID và fingerprint không nhạy cảm vào log release.

Không chỉ kiểm tra hostname. Một cluster có thể chứa nhiều database hoặc schema. Hãy xác minh cả database/catalog, schema và danh tính service account theo cách DBMS hỗ trợ.

## 6. Cô lập credentials và quyền truy cập

Mỗi target nên có service account migration riêng hoặc ít nhất một phạm vi quyền rõ ràng. Tài khoản migration thường cần quyền:

- Kết nối tới database đích.
- Đọc metadata/schema cần thiết.
- Tạo và cập nhật DATABASECHANGELOG, DATABASECHANGELOGLOCK.
- Thực hiện DDL/DML trong phạm vi schema được quản lý.
- Tạo index, constraint, sequence hoặc routine nếu changeset cần.
- Truy cập các object phụ trợ được thiết kế rõ ràng.

Không cấp quyền DBA hoặc superuser cho mọi job nếu không cần. Một migration tạo extension, user, role hoặc grant có thể cần quyền đặc biệt; hãy tách bước đó thành tác vụ DBA được kiểm soát thay vì mở rộng quyền thường trực cho toàn bộ pipeline.

Credential của customer_db không nên được cấp cho job billing_db. Nếu pipeline có quyền truy cập nhiều secret, cần giới hạn quyền theo job/target để một lỗi cấu hình không làm lộ toàn bộ thông tin kết nối.

## 7. Quản lý secret an toàn

Các nguyên tắc thực hành:

- Lưu password, token và certificate private key trong secret manager hoặc kho secret của CI/CD.
- Chỉ inject secret vào job cần target đó.
- Ưu tiên cơ chế credential ngắn hạn/rotation khi nền tảng hỗ trợ.
- Không commit file properties có password thật.
- Không in toàn bộ environment variables khi debug.
- Không bật log JDBC/HTTP ở mức có thể in credential hoặc dữ liệu nhạy cảm.
- Không đưa password vào tên process, artifact, command log hoặc ticket.
- Thu hồi credential của công cụ cũ sau khi cutover được xác nhận.
- Tách tài khoản migration khỏi tài khoản runtime khi phù hợp.

Nếu dùng file `liquibase.properties`, hãy quản lý file không bí mật trong repository và cấp giá trị nhạy cảm từ runtime. Cú pháp tham chiếu biến môi trường/property có thể phụ thuộc cách chạy và phiên bản; kiểm tra đúng cơ chế Liquibase/CLI/plugin trước khi dùng. Không giả định một placeholder bất kỳ sẽ tự được mở rộng.

## 8. Xác minh target trước khi mở migration

Trước khi gọi `update`, chạy các bước kiểm tra chỉ đọc:

1. Mở kết nối bằng profile được chọn.
2. Lấy thông tin DBMS và phiên bản.
3. Lấy database/catalog hiện tại.
4. Lấy schema hiện tại và user/session đang dùng.
5. Kiểm tra quyền đọc metadata và bảng lịch sử.
6. Xác nhận target alias khớp manifest.
7. Kiểm tra changelog master có trong artifact.
8. Kiểm tra không có job khác đang sở hữu cùng database migration.

Ví dụ truy vấn có tính minh họa, cú pháp tùy DBMS:

~~~sql
SELECT CURRENT_USER;
~~~

Trên PostgreSQL có thể kiểm tra:

~~~sql
SELECT current_database(), current_schema(), current_user;
~~~

Trên MySQL có thể kiểm tra:

~~~sql
SELECT DATABASE(), CURRENT_USER();
~~~

Không dùng một câu SQL chung cho mọi DBMS. Pipeline có thể dùng adapter hoặc bước kiểm tra theo từng dialect. Nếu không xác minh được đích, dừng trước khi update.

## 9. DATABASECHANGELOG được cô lập theo database đích

Liquibase dùng **DATABASECHANGELOG** để ghi nhận changeset đã được xử lý. Trong cấu hình thông thường, bảng này tồn tại trong database/schema đích của lần chạy.

Điều đó có nghĩa:

- customer_db có history riêng.
- order_db có history riêng.
- billing_db có history riêng.
- Một changeset có thể đã EXECUTED ở customer_db nhưng chưa tồn tại trong history của order_db.
- Checksum/lịch sử của từng target phải được kiểm tra tại chính target đó.

Một truy vấn tham khảo:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    MD5SUM,
    EXECTYPE,
    DATEEXECUTED,
    ORDEREXECUTED
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Tên bảng, schema và tập cột có thể thay đổi theo cấu hình và phiên bản. Luôn truy vấn đúng database/schema history của target; không lấy history ở một database rồi suy ra database khác đã cập nhật.

**DATABASECHANGELOG là lịch sử cục bộ của đích**, không phải một registry trung tâm tự đồng bộ trạng thái tất cả database.

## 10. DATABASECHANGELOGLOCK cũng thuộc phạm vi cấu hình đích

Liquibase dùng **DATABASECHANGELOGLOCK** để điều phối các tiến trình Liquibase cùng sử dụng bảng lock. Một target thông thường có lock table tương ứng với history table.

Bảng này giúp tránh hai tiến trình Liquibase cùng thực hiện migration không được điều phối trên cùng lịch sử. Tuy nhiên:

- Lock ở customer_db không khóa order_db.
- Lock Liquibase không chặn Flyway hoặc DBA chạy SQL thủ công.
- Lock không thay thế lock row/table/metadata của DBMS.
- Nếu hai changelog độc lập dùng hai bảng lock khác nhau nhưng cùng sửa một object, chúng không tự điều phối với nhau.

Nếu nhiều ứng dụng/changelog cùng chia sẻ một database, quyết định dùng chung hay tách bảng history/lock phải được thiết kế có chủ đích. Dùng chung có thể tạo một lịch sử và cơ chế serialize chung; tách riêng giúp độc lập lịch sử nhưng tăng trách nhiệm điều phối xung đột object.

## 11. Cấu hình tên bảng history và schema

Liquibase cho phép cấu hình tên bảng lịch sử và bảng lock, cùng schema/catalog chứa chúng, theo thuộc tính và cách gọi của phiên bản/DBMS.

Các thuộc tính thường gặp gồm:

- `databaseChangeLogTableName`
- `databaseChangeLogLockTableName`
- `liquibaseSchemaName`
- `defaultSchemaName`
- `liquibaseCatalogName` hoặc thuộc tính catalog tương ứng theo DBMS/version.

Tên property, vị trí cấu hình và cách truyền có thể khác giữa CLI, Maven/Gradle plugin và Spring Boot. Xác nhận theo phiên bản thực tế.

Ví dụ một target có history schema riêng:

~~~text
Application objects: customer.*
Liquibase history:   migration_meta.DATABASECHANGELOG
Liquibase lock:      migration_meta.DATABASECHANGELOGLOCK
~~~

Nếu hai database khác nhau, cùng tên bảng DATABASECHANGELOG không gây xung đột vì chúng nằm trong database riêng. Nếu nhiều logical target thực chất cùng một physical database/schema, cần cân nhắc tên bảng hoặc schema history riêng và hiểu tác động điều phối.

Không đổi tên bảng history/lock tùy tiện sau khi đã triển khai. Nếu thay đổi vị trí, Liquibase có thể không tìm thấy lịch sử cũ và tạo một history mới, khiến changeset cũ xuất hiện pending.

## 12. Một database vật lý, nhiều schema hoặc nhiều logical target

Có trường hợp một PostgreSQL database chứa nhiều schema ứng dụng: `customer`, `orders`, `billing`. Chúng có thể được xem là các logical target, nhưng vẫn chia sẻ tài nguyên và transaction engine của cùng database.

Cần quyết định:

- Mỗi schema có master changelog riêng hay một master chung?
- Các schema dùng chung một DATABASECHANGELOG hay history riêng?
- Nếu history riêng, lock table cũng riêng hay có một cơ chế serialize cấp database?
- Những changeset nào sửa object cross-schema?
- Ai sở hữu migration của schema dùng chung?
- Pipeline có ngăn hai job cùng sửa object phụ thuộc không?

Hai logical target cùng physical database không độc lập như hai database instance. Chúng có thể cạnh tranh lock và tài nguyên, và DDL cross-schema có thể tạo phụ thuộc. Tách history table không tự tạo cách ly transaction hoặc khóa đối tượng.

Nếu dùng một history chung, các changeset từ nhiều domain phải có identity ổn định và thứ tự include được review. Nếu dùng history riêng, cần orchestration để tránh xung đột giữa các job.

## 13. Dùng cùng changelog cho nhiều đích hay tách changelog?

Hai mô hình đều có thể phù hợp:

| Tiêu chí | Changelog dùng chung | Changelog riêng theo target |
|---|---|---|
| Schema giống nhau | Phù hợp | Có thể trùng lặp |
| Schema khác nhau | Cần DBMS filter/nhánh rõ | Dễ biểu đạt khác biệt |
| Identity changeset | Cùng bộ id/author/filename được ghi riêng trong từng history | Có thể tách phạm vi và owner |
| Lịch sử | Mỗi target vẫn có DATABASECHANGELOG riêng | Mỗi target có history riêng |
| Rủi ro | Changeset không phù hợp một target nếu filter sai | Drift giữa các changelog nếu copy thủ công |
| Review | Một thay đổi có thể được review một lần | Mỗi target cần review phạm vi riêng |

Changelog dùng chung không có nghĩa chỉ cần update một lần là mọi target đã xong. Mỗi target phải chạy riêng với connection profile và history riêng.

Changelog riêng không có nghĩa được phép copy changeset cũ rồi sửa identity tùy tiện. Hãy giữ ownership và lịch sử ổn định, dùng include/shared changelog hoặc convention phù hợp khi cấu trúc có thể tái sử dụng.

## 14. Cấu hình Liquibase CLI theo target

Một lần chạy CLI thường cần URL, credentials, changelog và các thuộc tính schema phù hợp. Ví dụ dạng lệnh minh họa:

~~~text
liquibase
  --url=jdbc:postgresql://db-host:5432/customer_db
  --username=customer_migrator
  --changelog-file=db/changelog/customer/master.yaml
  update
~~~

Giá trị password không được viết trực tiếp trong ví dụ/repository; inject qua secret mechanism phù hợp với nền tảng. Cú pháp chính xác và cách nạp properties phụ thuộc phiên bản Liquibase CLI.

Một job khác phải nhận connection profile của order_db và master changelog tương ứng. Không tái sử dụng URL customer_db rồi chỉ đổi tên job.

Trước lệnh update, có thể chạy validate/status/updateSQL theo phiên bản. Sau update, kiểm tra DATABASECHANGELOG và kết quả schema/data tại đúng target. Lưu target ID và revision vào release record.

## 15. Cấu hình Spring Boot: một datasource và nhiều datasource

Với một datasource, Spring Boot có thể cấu hình Liquibase qua:

~~~yaml
spring:
  datasource:
    url: ${APP_DB_URL}
    username: ${APP_DB_USER}
    password: ${APP_DB_PASSWORD}
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Placeholder chỉ minh họa việc lấy cấu hình từ môi trường; cách bind và nguồn secret phải theo cấu hình Spring Boot/deployment thực tế.

Khi ứng dụng có nhiều DataSource, không mặc định Spring Boot sẽ tự chạy một Liquibase migration độc lập trên mọi datasource theo đúng thứ tự mong muốn. Cần xác định Liquibase gắn với datasource nào, hoặc cấu hình các Liquibase bean/job riêng theo Spring Boot version.

Một lựa chọn vận hành thường dễ kiểm soát là **migration job riêng cho từng target**, còn ứng dụng runtime không tự chạy migration trên tất cả database. Nếu dùng nhiều Liquibase bean trong một ứng dụng, khai báo rõ URL/DataSource, changelog, history schema và thứ tự khởi tạo; không dựa vào thứ tự bean ngầm.

## 16. Cô lập cấu hình không có nghĩa nhân bản mọi file changelog

Không cần tạo bản sao changelog chỉ vì database có URL khác nhau. Nếu schema và thay đổi giống nhau, có thể chạy cùng một artifact/changelog trên nhiều target. Phần cần tách là **connection, target metadata, history và execution result**.

Tách changelog khi:

- Schema thuộc các domain khác nhau.
- DBMS hoặc cú pháp thay đổi khác nhau.
- Thứ tự release và owner khác nhau.
- Một target không được phép nhận một thay đổi.
- Context/label/dbms filter không đủ rõ để bảo đảm phạm vi.

Tránh copy-paste cùng một thay đổi vào nhiều thư mục rồi để nội dung lệch dần. Nếu cần shared changelog, sử dụng cơ chế include và kiểm thử mỗi target bằng đúng DBMS/configuration.

## 17. Tách trạng thái và log của từng lần chạy

Mỗi job nên phát hành một execution record có các trường:

| Trường | Mục đích |
|---|---|
| release_id | Liên kết các job thuộc cùng một đợt phát hành |
| target_id | Database đích logic |
| environment | Dev/test/staging/production |
| database_alias | Tên database/schema không nhạy cảm |
| dbms/version | Dialect và phiên bản |
| changelog_revision | Commit SHA/artifact digest |
| changelog_file | Master changelog |
| started_at / finished_at | Thời gian thực thi |
| status | Pending/running/success/failed/blocked |
| failed_changeset | id/author/filename nếu có |
| error_class | Nhóm lỗi đã phân loại |
| retryable | Có thể retry sau khi kiểm tra hay không |
| operator/job_id | Người hoặc pipeline thực thi |

Không gộp trạng thái thành một cờ duy nhất `release_success=true` khi một target thành công còn target khác thất bại. Cần có trạng thái tổng hợp và trạng thái từng target.

## 18. Tương quan log và che giấu thông tin nhạy cảm

Log tốt giúp trả lời: job nào, target nào, revision nào, changeset nào và lỗi xảy ra ở giai đoạn nào.

Nên ghi:

- Release ID, target ID, environment.
- DBMS/version và database/schema alias.
- Changelog revision và changeset identity.
- Pha chạy: resolve config, connect, validate, acquire lock, execute, record history.
- Thời gian kết nối, thời gian chờ lock và thời gian statement nếu có.
- SQLState/vendor error code khi driver cung cấp.
- Kết quả readiness và kiểm tra sau migration.
- Job ID, correlation ID và operator.

Không ghi:

- Password, token, private key hoặc full secret URI.
- JDBC URL nếu URL chứa thông tin nhạy cảm.
- Nội dung hàng dữ liệu có PII hoặc dữ liệu thanh toán.
- Toàn bộ biến môi trường.
- SQL parameter nhạy cảm ở dạng plaintext.

Nếu cần chẩn đoán SQL, log statement đã lọc hoặc template an toàn; hạn chế bật debug JDBC trên production và kiểm soát quyền truy cập log.

## 19. Phân loại lỗi theo từng target

Một lỗi cần được phân loại trước khi quyết định retry:

| Nhóm lỗi | Ví dụ | Hướng xử lý đầu tiên |
|---|---|---|
| Connection | Host không tới được, DNS, connection refused | Kiểm tra network, endpoint và trạng thái DB |
| Authentication | Password hết hạn, user bị khóa | Xác minh secret/rotation và account |
| Authorization | Không có quyền CREATE/ALTER/INSERT | Kiểm tra quyền tối thiểu và object owner |
| Target mismatch | Job order_db lại trỏ customer_db | Dừng ngay, xác minh target fingerprint |
| Changelog/resource | Không tìm thấy master/include/sqlFile | Kiểm tra artifact và resource path |
| Validation/checksum | Changelog lỗi hoặc checksum mismatch | Dừng, so sánh revision và identity |
| Liquibase lock | DATABASECHANGELOGLOCK đang bị giữ | Xác minh job owner trước khi xử lý |
| DBMS lock/deadlock | DDL/DML bị block hoặc deadlock | Quan sát session, blocker, transaction |
| SQL/dialect | Cú pháp không hợp DBMS/version | Review SQL và DBMS filter |
| Data/precondition | Điều kiện dữ liệu không đạt | Kiểm tra invariant và trạng thái đầu vào |
| Resource exhaustion | Timeout, connection pool, disk/log đầy | Đánh giá tài nguyên và tác động trước retry |

Không dùng một retry policy cho mọi nhóm. Connection timeout tạm thời có thể retry có giới hạn; checksum mismatch hoặc target mismatch phải dừng để điều tra. Deadlock có thể retry trong một số tình huống nếu transaction và changeset được thiết kế phù hợp, nhưng phải kiểm tra tác động một phần.

## 20. Không để lỗi một target làm sai lịch sử target khác

Giả sử một release có ba database:

| Target | Kết quả | Lịch sử |
|---|---|---|
| customer-prod-a | Thành công | Changeset mới được ghi |
| order-prod-a | Thành công | Changeset mới được ghi |
| billing-prod-a | Thất bại do quyền | Changeset còn pending hoặc trạng thái cần điều tra |

Lịch sử của customer_db và order_db không bị xóa chỉ vì billing_db thất bại. Khi sửa quyền, job có thể tiếp tục riêng billing_db, với điều kiện đã xác minh không có thay đổi một phần cần phục hồi.

Không chạy một script cleanup xóa history của các target đã thành công để đưa release về trạng thái “tất cả chưa chạy”. Điều đó phá bằng chứng thực thi và có thể khiến DDL/DML chạy lại.

Trạng thái release tổng hợp có thể là **PARTIAL_SUCCESS** hoặc **NEEDS_RECOVERY** trong orchestration, trong khi mỗi database vẫn giữ lịch sử Liquibase của chính nó.

## 21. Retry và resume theo target

Một retry an toàn cần theo thứ tự:

1. Chọn đúng target ID đã thất bại.
2. Xác minh connection profile hiện tại và target fingerprint.
3. Kiểm tra job cũ đã kết thúc, không còn session migration hoạt động.
4. Đọc DATABASECHANGELOG và DATABASECHANGELOGLOCK của target đó.
5. Kiểm tra schema/data thực tế để phát hiện thay đổi một phần.
6. Xác định changeset đã EXECUTED, MARK_RAN, RERAN hay chưa được ghi nhận.
7. Nếu không có thay đổi một phần và nguyên nhân tạm thời đã hết, chạy lại cùng revision.
8. Nếu có drift hoặc DDL autocommit, tạo kế hoạch recovery/forward fix trước retry.
9. Chạy validate/status/updateSQL nếu phù hợp.
10. Thực thi và hậu kiểm target đó, sau đó cập nhật release record.

Liquibase thường bỏ qua changeset đã được ghi nhận theo identity trong DATABASECHANGELOG. Nhưng điều đó không bảo đảm một changeset bị lỗi giữa chừng không để lại object/data nếu DBMS không rollback DDL hoặc changeset dùng runInTransaction=false.

**Không xóa row history để ép chạy lại.** Trước khi retry, phải biết trạng thái thực tế.

## 22. Partial failure và trạng thái release

Khi nhiều database được cập nhật độc lập, cần mô hình trạng thái rõ:

~~~text
PENDING
   |
   v
RUNNING
   |
   +------> SUCCESS
   |
   +------> FAILED
   |
   +------> BLOCKED
                |
                v
          NEEDS_RECOVERY
                |
         +------+------+
         |             |
      RESUMABLE     FORWARD_FIX
         |             |
         v             v
      RUNNING        VERIFIED
~~~

Đây là state model khái niệm của orchestrator, không phải EXECTYPE hay trạng thái built-in của Liquibase.

- **SUCCESS:** update và hậu kiểm target hoàn tất.
- **FAILED:** job lỗi; chưa kết luận có hay không thay đổi một phần.
- **BLOCKED:** không chạy vì prerequisite hoặc target khác chưa sẵn sàng.
- **NEEDS_RECOVERY:** cần đối chiếu schema/history trước khi tiếp tục.
- **RESUMABLE:** đã xác minh trạng thái cho phép chạy lại cùng revision.

Giữ riêng status của từng target và trạng thái tổng release. Nếu một provider thất bại, consumer phụ thuộc phải ở BLOCKED thay vì tự chạy và tạo schema không nhất quán.

## 23. Bảng history chung hay riêng khi có nhiều ứng dụng cùng database?

Nếu hai ứng dụng cùng dùng một physical database, cần quyết định phạm vi history:

**Dùng chung DATABASECHANGELOG/DATABASECHANGELOGLOCK:**

- Có một lịch sử điều phối chung.
- Changeset identity cần không xung đột.
- Các nhóm phải phối hợp thứ tự và quyền.
- Một migration có thể chờ migration khác vì cùng lock table.

**Tách history/lock theo logical owner:**

- Lịch sử và trạng thái từng owner dễ phân biệt.
- Một nhóm có thể quản lý changelog riêng.
- Các job có thể chạy đồng thời nếu không có cơ chế lock chung.
- Cần orchestration tránh cùng sửa một object hoặc tạo phụ thuộc chéo.

Không có lựa chọn mặc định tốt cho mọi hệ thống. Nếu hai owner thay đổi các schema độc lập, history riêng có thể phù hợp. Nếu họ thay đổi object phụ thuộc trong cùng schema, history riêng không đủ để bảo đảm an toàn; cần một release coordinator hoặc lock cấp cao hơn.

## 24. Tách lỗi kết nối khỏi lỗi migration

Một thông báo “Liquibase update failed” quá chung để vận hành. Phân biệt:

- **Không mở được kết nối:** chưa gửi changeset SQL.
- **Kết nối thành công nhưng không lấy được Liquibase lock:** có job khác giữ history lock hoặc lock table không truy cập được.
- **Lấy được Liquibase lock nhưng SQL chờ DBMS:** session đang chờ row/table/metadata lock.
- **SQL bị từ chối:** syntax, permission, constraint hoặc dữ liệu không đạt.
- **SQL thành công nhưng ghi history lỗi:** cần kiểm tra transaction và lịch sử thực tế; không giả định changeset chưa tác động.
- **Mất kết nối trong lúc chạy:** kết quả có thể chưa rõ, đặc biệt với DDL/autocommit.

Error record nên chứa phase và SQLState/vendor code, không chỉ message. Khi connection bị mất giữa chừng, hãy kiểm tra session DBMS và DATABASECHANGELOG trước khi retry.

## 25. Timeout và retry policy riêng cho từng đích

Mỗi DBMS/target có latency, mạng và workload khác nhau. Không nhất thiết mọi target dùng cùng timeout.

Cần phân biệt:

| Timeout | Ý nghĩa |
|---|---|
| Connection timeout | Thời gian thiết lập kết nối |
| Socket/read timeout | Thời gian chờ phản hồi qua kết nối |
| Liquibase lock wait | Thời gian chờ quyền migration theo cấu hình |
| DBMS lock timeout | Thời gian chờ khóa đối tượng |
| Statement/query timeout | Thời gian thực thi câu SQL |
| Job timeout | Giới hạn tổng thời gian pipeline |

Tên thuộc tính và cách truyền timeout khác theo JDBC driver, Liquibase version, DBMS và CI system. Kiểm tra từng tầng, không tăng tất cả lên một giá trị lớn khi gặp lỗi.

Retry nên có giới hạn, backoff và phân loại lỗi. Không retry vô hạn đối với checksum mismatch, target mismatch, permission hoặc SQL syntax. Với timeout do lock, phải xác định blocker và trạng thái transaction trước khi retry.

## 26. Connection pool và vòng đời kết nối

Migration job thường có nhu cầu kết nối khác với request traffic của ứng dụng:

- Job có thể cần một kết nối ổn định trong suốt quá trình migration.
- Nhiều target đồng thời tạo tổng số connection tăng nhanh.
- Pool dùng chung với traffic ứng dụng có thể làm cạn connection.
- Timeout/idle connection của proxy hoặc firewall có thể ngắt migration dài.
- Multi-DataSource cần xác định rõ Liquibase dùng pool/connection nào.

Với job riêng, có thể dùng cấu hình pool nhỏ, giới hạn concurrency và lifecycle rõ ràng. Không tăng pool size chỉ để chạy nhiều database song song; hãy xem năng lực DBMS, I/O, lock và giới hạn connection trước.

Nếu Liquibase chạy lúc Spring Boot startup, kiểm tra pool và readiness/liveness probe để migration dài không tạo vòng restart. Một migration job độc lập thường dễ cô lập tài nguyên và quan sát hơn.

## 27. Cấu hình khác nhau theo environment nhưng giữ cùng changelog revision

Cùng một changelog revision nên được promote qua dev, test, staging và production. Thông tin kết nối, credentials và một số tham số triển khai thay đổi theo environment; nội dung migration không nên bị sửa thủ công giữa các môi trường.

Một ma trận cấu hình:

| Thuộc tính | Development | Staging | Production |
|---|---|---|---|
| Target ID | customer-dev | customer-stg | customer-prod-a |
| Connection profile | secret dev | secret staging | secret prod |
| Changelog revision | commit X | commit X | commit X |
| History schema | migration_meta | migration_meta | migration_meta |
| Migration user | dev migrator | staging migrator | prod migrator |
| Approval | tự động theo policy | review | phê duyệt release |
| Logging | chi tiết hơn | tiêu chuẩn | lọc secret/PII |

Không build ba artifact có nội dung changelog khác nhau cho cùng release. Nếu DBMS hoặc schema thực sự khác, dùng changeset filter hoặc changelog tách biệt có chủ đích, và kiểm tra mỗi nhánh tương thích.

## 28. Kiểm tra drift và target nhầm

Một target có thể kết nối thành công nhưng schema không còn khớp lịch sử do DBA hotfix hoặc công cụ ngoài Liquibase.

Trước khi chạy migration quan trọng:

1. Xác nhận target fingerprint.
2. Kiểm tra changeset history và checksum.
3. Kiểm tra các object prerequisite.
4. So sánh schema với baseline/reference khi cần.
5. Xác minh dữ liệu thỏa precondition/invariant.
6. Xác định object do công cụ khác sở hữu.
7. Dừng nếu phát hiện drift chưa được giải thích.

Đừng dùng changelog-sync hoặc MARK_RAN để làm sạch status khi chưa xác minh. Nếu target nhầm, dừng ngay cả khi credentials hợp lệ và SQL preview trông đúng.

## 29. Kiểm thử và quan sát trước/sau migration

Mỗi target cần có kết quả kiểm chứng riêng:

**Trước migration:**

- Target/database/schema đúng.
- DBMS/version được hỗ trợ.
- Changelog và artifact đúng revision.
- History/lock table truy cập được.
- Changeset pending đúng dự kiến.
- Precondition và dữ liệu đầu vào đạt.
- Không có job cạnh tranh.

**Sau migration:**

- Job exit thành công.
- DATABASECHANGELOG ghi nhận đúng changeset và EXECTYPE.
- Schema object tồn tại với kiểu, constraint và index đúng.
- Data invariant/row count đạt.
- Ứng dụng hoặc consumer có thể sử dụng contract.
- Không còn lock bất thường hoặc session migration treo.
- Release record được cập nhật theo target.

Không chỉ dựa vào “Liquibase update succeeded”. Một changeset có thể MARK_RAN hoặc không tác động hàng nào mà job vẫn thành công. Kiểm tra hậu điều kiện nghiệp vụ mới chứng minh kết quả mong muốn.

## 30. Bài thực hành: cô lập hai target và xử lý một target thất bại

Thực hành trên database disposable, không dùng production.

### Bối cảnh

Có hai database độc lập:

- `customer_lab` dùng PostgreSQL.
- `billing_lab` dùng DBMS thử nghiệm thứ hai hoặc một database riêng cùng loại.

Mỗi database có connection profile, user migration và master changelog riêng.

### Bước 1 — Khai báo target manifest

~~~yaml
targets:
  customer-lab:
    connectionProfile: secret://lab/customer
    changelog: db/changelog/customer/master.yaml
    historySchema: migration_meta
  billing-lab:
    connectionProfile: secret://lab/billing
    changelog: db/changelog/billing/master.yaml
    historySchema: migration_meta
~~~

Các secret URI chỉ là placeholder minh họa. Cung cấp credential qua secret manager của môi trường thử nghiệm.

### Bước 2 — Xác minh connection

Kết nối từng target riêng. Ghi target ID, DBMS, database/schema, user và phiên bản. Cố ý trỏ một profile tới database sai trên bản lab để kiểm tra guard target fingerprint; pipeline phải dừng trước update.

### Bước 3 — Chạy migration

Chạy validate/status/updateSQL cho từng target. Sau khi review, chạy update riêng. Truy vấn DATABASECHANGELOG trên từng database và xác nhận history không bị trộn.

### Bước 4 — Tạo lỗi chỉ ở billing_lab

Trên môi trường lab, dùng user billing không có quyền tạo một object mà changeset yêu cầu. Chạy job billing và ghi nhận lỗi authorization. Customer job không bị ảnh hưởng và lịch sử customer không bị xóa.

### Bước 5 — Phân loại và phục hồi

Kiểm tra billing_lab đã thực thi một phần hay chưa. Cấp quyền đúng cho user lab, giữ nguyên revision changelog, xác minh history/schema/data, rồi retry riêng billing_lab. Không chạy lại customer_lab nếu nó đã hoàn tất và hậu kiểm đạt.

### Bước 6 — So sánh execution record

| Trường | customer-lab | billing-lab lần đầu | billing-lab retry |
|---|---|---|---|
| Target | customer-lab | billing-lab | billing-lab |
| Connection | Đúng | Đúng | Đúng |
| Result | Success | Failed | Success |
| History | Changeset ghi nhận | Pending/điều tra | Ghi nhận sau thành công |
| Recovery | Không cần | Sửa quyền, kiểm tra | Hậu kiểm |

Kết quả mong đợi là lỗi của một target được khoanh vùng, có thể điều tra và retry độc lập sau khi xác nhận trạng thái thật.

## 31. Checklist trước khi triển khai nhiều database

- [ ] Mỗi database có target ID ổn định, không chứa secret.
- [ ] Connection profile ánh xạ chính xác target ID tới endpoint/database/schema.
- [ ] Job không có fallback URL production mặc định.
- [ ] Có bước xác minh target fingerprint trước update.
- [ ] Credentials được lưu trong secret manager và cấp theo least privilege.
- [ ] Không ghi password, token, PII hoặc full secret URL vào log.
- [ ] DBMS/version, schema ứng dụng và schema history được xác định rõ.
- [ ] DATABASECHANGELOG và DATABASECHANGELOGLOCK được truy vấn tại đúng target.
- [ ] Tên bảng/schema history không bị thay đổi ngoài kế hoạch.
- [ ] Chọn dùng chung hay tách history khi nhiều logical owner cùng physical database.
- [ ] Mỗi target có changelog/master phù hợp và cùng revision release đã phê duyệt.
- [ ] Liquibase CLI/plugin/Spring Boot dùng đúng connection profile.
- [ ] Mỗi target có execution record và status riêng.
- [ ] Log có release ID, target ID, changeset identity, phase và error code.
- [ ] Retry policy phân biệt lỗi tạm thời với lỗi cấu hình, checksum, SQL và target mismatch.
- [ ] Trước retry đã xác minh job cũ dừng và schema/data không ở trạng thái một phần.
- [ ] Lỗi một target không xóa history của target khác.
- [ ] Có trạng thái partial success, blocked, needs recovery và resume trong orchestrator.
- [ ] Có timeout riêng cho connection, lock, statement và job.
- [ ] Concurrency phù hợp giới hạn connection và tài nguyên DBMS.
- [ ] Spring Boot nhiều DataSource có Liquibase owner/configuration rõ ràng.
- [ ] Đã thử trên database clone và cố ý mô phỏng lỗi một target.
- [ ] Hậu kiểm schema, data invariant và DATABASECHANGELOG cho từng target.

**Ghi nhớ:** Cô lập nhiều database bằng cách tách rõ **target ID, connection profile, schema/history location và execution record**. DATABASECHANGELOG và DATABASECHANGELOGLOCK thuộc phạm vi database hoặc cấu hình lịch sử tương ứng; trạng thái của một target không chứng minh target khác đã chạy. Khi một job thất bại, phân loại lỗi, kiểm tra trạng thái schema/history tại đúng đích rồi mới retry riêng. Secret phải được cấp theo least privilege, log phải có correlation nhưng không lộ dữ liệu nhạy cảm, và pipeline cần lưu kết quả từng target để migration có thể tiếp tục an toàn qua nhiều môi trường với Spring Boot hoặc CI/CD.

