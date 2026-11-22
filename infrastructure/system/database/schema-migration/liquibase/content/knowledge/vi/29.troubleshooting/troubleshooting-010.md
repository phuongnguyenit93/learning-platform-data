# Khác biệt kết quả giữa máy phát triển, CI và production

## 1. Nhận diện vấn đề

Trong module DATABASE_SCHEMA_MIGRATION_LIQUIBASE, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Nhóm còn phải kiểm chứng migration, chuẩn bị rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một tình huống phổ biến là cùng một thay đổi chạy đúng trên máy developer nhưng thất bại trong CI, hoặc CI báo thành công trong khi production sinh SQL khác, bỏ qua changeset hay tạo object ở schema ngoài dự kiến.

Hiện tượng này thường được mô tả là “môi trường không giống nhau”, nhưng nguyên nhân có thể nằm ở nhiều lớp độc lập:

- Source code, commit, artifact hoặc resource changelog khác nhau.
- Java, Spring Boot, Liquibase core, extension, JDBC driver hoặc build plugin khác version.
- Profile, biến môi trường, context, label, parameter, schema hoặc datasource có giá trị hiệu lực khác nhau.
- DBMS khác engine, edition, server version, compatibility mode hoặc cấu hình session.
- Database có dữ liệu, object, quyền, lịch sử Liquibase hoặc trạng thái lock khác nhau.
- Thời điểm chạy, thứ tự deploy, số runner đồng thời hoặc trạng thái transaction khác nhau.

Điểm quan trọng là phải xác định **khác biệt đầu tiên có thể làm thay đổi kết quả**, rồi tái hiện nó trong môi trường kiểm thử. Chạy lại lệnh nhiều lần trên cùng máy hoặc sửa changelog ngay khi thấy lỗi thường làm mất dấu nguyên nhân.

Sau bài học, bạn có thể lập dấu vân tay môi trường, so sánh cấu hình hiệu lực, tái hiện migration trong CI và production-like database, đọc lịch sử Liquibase, phân biệt lỗi nguồn với lỗi môi trường, và đưa kiểm tra nhất quán vào pipeline.

## 2. Phân loại khác biệt theo lớp

### 2.1. Source và artifact

Hai môi trường có thể không thực sự chạy cùng nội dung dù tên release giống nhau:

- Developer chạy file changelog chưa commit; CI checkout commit khác.
- CI build lại từ source mới nhất trong khi production triển khai artifact đã phát hành trước đó.
- File SQL được tham chiếu bằng sqlFile không được đóng gói vào JAR hoặc không có trong working directory.
- Master changelog include file bằng đường dẫn tương đối, nhưng working directory khác làm việc tìm file khác nhau.
- Một resource bị loại bởi cấu hình build, profile Maven/Gradle hoặc quy tắc packaging.
- Một container image được tag cố định nhưng nội dung image đã bị thay đổi hoặc registry trỏ tới digest khác.

Hãy đối chiếu commit SHA, artifact checksum/digest, danh sách resource changelog và version build. Đừng dùng riêng tên branch hoặc tag mutable làm bằng chứng hai nơi chạy cùng artifact.

### 2.2. Toolchain và dependency

Liquibase không chạy độc lập. Kết quả có thể bị ảnh hưởng bởi:

| Thành phần | Khác biệt có thể gây ra |
|---|---|
| Java runtime/JDK | Encoding, TLS, timezone, class loading, API và behavior runtime |
| Spring Boot | Auto-configuration, property binding, dependency management |
| Liquibase core/CLI | Parser, SQL generator, checksum, command và default behavior |
| Extension | Change type, precondition, service registration và API compatibility |
| JDBC driver | Metadata, authentication, transaction, datatype và exception |
| Maven/Gradle plugin | Dependency resolution, resource filtering, build lifecycle |
| OS/container image | Locale, timezone database, CA certificates, filesystem và line ending |

Máy developer có thể dùng Liquibase CLI cài toàn cục trong khi CI dùng Liquibase library được Spring Boot quản lý. Hai version đó có thể parse cùng changelog hoặc sinh SQL khác nhau. Cần ghi version thực tế của tiến trình thực thi, không chỉ version khai báo trong file build.

### 2.3. Cấu hình hiệu lực

Các giá trị có ảnh hưởng trực tiếp đến tập changeset hoặc SQL gồm:

- spring.profiles.active và các profile được kích hoạt cùng lúc.
- spring.liquibase.enabled và spring.liquibase.change-log.
- spring.liquibase.contexts và spring.liquibase.label-filter.
- spring.liquibase.default-schema, spring.liquibase.liquibase-schema, catalog và tablespace.
- Liquibase parameters được truyền qua Spring Boot, CLI hoặc file properties.
- JDBC URL, database/catalog, username, driver properties và session settings.
- Các biến môi trường, command-line arguments, ConfigMap, Secret và external configuration.

Giá trị trong application.yml chưa chắc là giá trị cuối cùng. Biến môi trường, command-line argument, profile bổ sung hoặc property source do nền tảng cung cấp có thể ghi đè. Vì vậy phải kiểm tra **giá trị đã bind tại runtime**, sau khi đã loại bỏ password và token.

### 2.4. DBMS và trạng thái database

Ngay cả khi kết nối tới cùng loại DBMS, các database vẫn có thể khác:

- Server version, edition, compatibility level hoặc extension được cài.
- Collation, character set, case sensitivity, SQL mode và timezone.
- Default schema, search path, current catalog, owner và quyền.
- Object đã được DBA tạo thủ công hoặc đã bị chỉnh sửa ngoài Liquibase.
- Dữ liệu hiện có làm precondition hoặc constraint cho kết quả khác nhau.
- DATABASECHANGELOG có lịch sử khác, changeset đã chạy ở môi trường này nhưng chưa chạy ở môi trường khác.
- DATABASECHANGELOGLOCK còn lock do runner trước bị dừng.

“Cùng PostgreSQL” hay “cùng SQL Server” chưa đủ để kết luận môi trường tương đương. Cần so sánh server version, cấu hình session, schema, quyền và trạng thái dữ liệu liên quan.

## 3. Lập dấu vân tay môi trường

Trước khi điều tra, tạo một bản ghi ngắn cho từng lần chạy. Dấu vân tay không chứa bí mật nhưng đủ để xác định tiến trình và database đích.

| Nhóm | Thông tin nên ghi |
|---|---|
| Release | Commit SHA, build number, artifact version và checksum |
| Runtime | Java vendor/version, OS/container image digest |
| Framework | Spring Boot version và active profiles |
| Migration engine | Liquibase core/CLI version, extension versions |
| Driver | JDBC driver name/version |
| Database | DBMS product/version, database/catalog và schema đích |
| Filters | Contexts, label filter, DBMS filter và parameters không nhạy cảm |
| Changelog | Master changelog, logical file path và resource list |
| Security | Principal/role đã dùng và schema grants liên quan |
| Execution | Thời điểm, pipeline/job ID, runner identity, duration và exit code |

Ví dụ bản ghi đã làm sạch:

~~~text
release.commit=8f3a1c2...
release.artifact=orders-service:2026.11.19
runtime.java=21
spring.boot=3.x.y
liquibase.core=4.x.y
liquibase.extension.custom=1.x.y
jdbc.driver=PostgreSQL JDBC 42.x
database.product=PostgreSQL
database.serverVersion=16.x
database.name=orders_test
database.schema=app_test
liquibase.schema=liquibase_meta
spring.profiles.active=test
liquibase.contexts=common,test
liquibase.labelFilter=baseline,release-2026-11
liquibase.changeLog=classpath:/db/changelog/db.changelog-master.yaml
~~~

Các version trong ví dụ chỉ minh họa cách ghi nhận, không phải ma trận tương thích được khuyến nghị. Ghi version chính xác từ runtime và database thật.

### 3.1. Không log thông tin xác thực

Không ghi password, access token, private key hoặc JDBC URL chứa user/password. Có thể ghi host đã rút gọn, database name, driver properties không nhạy cảm và principal name. Nếu hostname hoặc tên database là thông tin nhạy cảm, dùng mã định danh nội bộ ổn định để đối chiếu.

Không in toàn bộ Spring Environment, toàn bộ system properties hoặc nội dung Secret chỉ để tìm giá trị cấu hình. Hãy chọn allowlist các thuộc tính cần kiểm tra và mask các trường nhạy cảm.

### 3.2. Lưu cùng kết quả migration

Dấu vân tay nên được gắn với:

- SQL preview hoặc update-sql đã review.
- Output validate và status --verbose.
- Log migration và danh sách changeset được thực thi.
- Báo cáo test database trống và database có lịch sử.
- Kết quả smoke test sau migration.

Nhờ vậy, khi production khác CI, nhóm có thể so sánh hai lần chạy theo từng trường thay vì dựa vào trí nhớ.

## 4. Xác minh source, changelog và artifact

### 4.1. Đảm bảo cùng commit và cùng artifact

Kiểm tra:

1. Commit SHA mà developer, CI và production đang sử dụng.
2. Artifact được tạo từ commit đó có cùng checksum/digest ở các bước deploy.
3. JAR/container có chứa master changelog và tất cả file được include.
4. Các sqlFile, include và includeAll resolve tới đúng resource.
5. Không có file changelog được tạo hoặc sửa ngoài quy trình build.

Nếu CI tạo một artifact cho test rồi production build lại từ branch, hai môi trường có thể không còn cùng nội dung. Nên promote chính artifact đã qua kiểm thử tới staging/production, thay vì build lại không kiểm soát.

### 4.2. Kiểm tra include path

Với changelog có cấu trúc:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-order-index.yaml
      relativeToChangelogFile: true
~~~

relativeToChangelogFile: true giúp đường dẫn được resolve tương đối với changelog chứa khai báo include. Nếu dùng đường dẫn phụ thuộc working directory, kết quả có thể khác giữa IDE, CLI, JAR và container. Kiểm tra resource thực tế bên trong artifact đã đóng gói.

### 4.3. Giữ ổn định định danh changeset

Liquibase nhận diện changeset dựa trên các thành phần định danh như id, author và file path/logical file path. Khi di chuyển hoặc đổi tên file, hãy xem xét logicalFilePath và hành vi nhận diện theo version Liquibase đang dùng. Nếu cùng một changeset bị nhận diện như một file path mới, Liquibase có thể coi nó là changeset chưa chạy.

Không đổi id, author hoặc logical path tùy tiện để “làm sạch” changelog đã triển khai. Nếu cần tổ chức lại file, phải thử trên bản sao database có lịch sử và xác minh Liquibase vẫn nhận diện đúng các changeset cũ.

## 5. So sánh toolchain và dependency

### 5.1. Xác minh version thực tế

Ghi nhận version Java và Liquibase từ chính tiến trình CI hoặc migration job. Với CLI, lệnh:

~~~bash
liquibase --version
java -version
~~~

Với Maven:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies
~~~

Các lệnh build chỉ dùng khi dự án có cấu hình tương ứng; so sánh output giữa môi trường local và CI. Không chỉ xem version trong pom.xml hoặc build.gradle: BOM, plugin, dependency constraint và dependency bắc cầu có thể quyết định version thực tế.

### 5.2. CLI và Spring Boot có thể dùng hai Liquibase khác nhau

Một pipeline có thể chạy Liquibase CLI để tạo SQL preview, trong khi ứng dụng Spring Boot dùng Liquibase core trên classpath lúc startup. Nếu hai version hoặc extension khác nhau:

- Parser có thể diễn giải changelog khác nhau.
- SQL generator có thể sinh cú pháp khác nhau.
- Precondition hoặc custom change type có thể không được đăng ký giống nhau.
- Checksum/history có thể được xử lý khác theo version.

Đồng bộ version core, extension và JDBC driver nếu kiến trúc cho phép. Nếu phải dùng version khác, ghi rõ lý do và chạy test với cả hai đường thực thi.

### 5.3. Kiểm tra classpath của extension

Nếu CI nhận diện custom change type nhưng production không nhận diện:

- So sánh dependency tree và scope của extension.
- Kiểm tra extension có trong runtime classpath hay chỉ có trong build/test classpath.
- Kiểm tra service descriptor/SPI sau khi đóng gói.
- Kiểm tra class loader và dependency bắc cầu.
- Chạy test trên artifact cuối cùng, không chỉ từ IDE.

Lỗi ClassNotFoundException, NoSuchMethodError hoặc “unknown change type” thường chỉ ra vấn đề dependency/API/classpath trước khi cần xem SQL.

## 6. So sánh cấu hình hiệu lực của Spring Boot và Liquibase

### 6.1. Profile active

Ghi nhận tất cả profile đang active, không chỉ profile dự định. Ví dụ dev,metrics có thể kết hợp nhiều file profile; một property trong profile bổ sung hoặc biến môi trường có thể ghi đè cấu hình Liquibase.

Kiểm tra các giá trị:

| Thuộc tính | Điều cần xác nhận |
|---|---|
| spring.profiles.active | Danh sách profile thực tế |
| spring.liquibase.enabled | Liquibase có thực sự chạy trong tiến trình này không |
| spring.liquibase.change-log | Master changelog đã resolve |
| spring.liquibase.contexts | Tập context được truyền |
| spring.liquibase.label-filter | Biểu thức label hiệu lực |
| spring.liquibase.default-schema | Schema mặc định cho object |
| spring.liquibase.liquibase-schema | Schema metadata |
| spring.liquibase.parameters.* | Giá trị parameter sau khi bind |

Property name và khả năng binding có thể khác theo phiên bản Spring Boot. Hãy kiểm tra metadata/tài liệu đúng version đang chạy, đặc biệt khi nâng Spring Boot hoặc Liquibase.

### 6.2. Context và label làm thay đổi tập changeset

Ví dụ:

~~~yaml
spring:
  liquibase:
    contexts: common,prod
    label-filter: baseline,release-2026-11
~~~

Nếu local dùng common,dev còn production dùng common,prod, các changeset được gắn context riêng có thể được chọn khác nhau. Label filter cũng có thể loại changeset dù context phù hợp. Một changeset không khai báo context/label có quy tắc chọn riêng; không xem field bỏ trống là cơ chế bảo vệ production.

Để chẩn đoán:

1. Đọc context/label trên changeset đang được nhắc tới.
2. Ghi bộ lọc hiệu lực ở mỗi môi trường.
3. Chạy status --verbose với đúng bộ lọc.
4. Chạy update-sql với cùng changelog, DBMS, parameters và schema.
5. So sánh danh sách changeset pending và SQL preview.

Không thay đổi context/label để làm CI và production có cùng output trước khi xác định môi trường nào đang dùng đúng chính sách release.

### 6.3. Parameter và schema

Một parameter như ${appSchema}` có thể được truyền từ profile hoặc CLI. Nếu local thay bằng app_dev, CI thay bằng app_ci và production thay bằng app, cùng changeset có thể tác động lên các schema khác nhau. Điều này là chủ đích nếu được kiểm soát, nhưng nguy hiểm nếu giá trị bị thiếu hoặc ghi đè.

Đối chiếu:

- default-schema với schemaName khai báo trực tiếp.
- liquibase-schema với schema chứa DATABASECHANGELOG/DATABASECHANGELOGLOCK.
- Parameter trong Spring Boot với parameter của CLI.
- Catalog/database trong JDBC URL với schema được truyền vào changelog.

Không giả định default-schema tự tạo schema hoặc parameter được thay đúng chỉ vì ứng dụng khởi động thành công. Hãy kiểm tra SQL preview và object thực tế.

## 7. So sánh DBMS, driver và session

### 7.1. Xác nhận database đích

Một lỗi nghiêm trọng là Liquibase chạy vào database khác với database mà nhóm đang kiểm tra. Trước update, xác minh:

- DBMS product name và server version.
- Host/endpoint và port (theo cách đã che thông tin nhạy cảm).
- Database/catalog/service name.
- Current user, current schema và default schema.
- JDBC driver name/version.
- TLS/authentication mode.

Không dựa vào tên biến PROD_DB_URL hoặc tên profile prod làm bằng chứng target đúng. Kiểm tra giá trị connection thực tế và identity mà database trả về.

### 7.2. Kiểm tra cấu hình session

Session có thể ảnh hưởng cách DBMS phân giải tên và thực thi SQL:

- PostgreSQL: search_path, role, timezone, collation và session settings.
- MySQL: sql_mode, default database, character set, collation và timezone.
- SQL Server: database context, default schema, compatibility level, collation và SET options.
- Oracle: current schema, NLS settings, session timezone, edition và quyền.

Nếu SQL không qualify schema, cùng câu lệnh có thể tạo object ở nơi khác tùy session. Ưu tiên schema qualification rõ ràng trong changelog khi phù hợp và kiểm tra session state trong mỗi môi trường.

### 7.3. JDBC metadata và SQL generation

Liquibase dùng JDBC metadata để snapshot database và thực hiện một số kiểm tra. Driver khác version hoặc server metadata khác có thể làm:

- Object không xuất hiện trong snapshot.
- Schema/catalog bị phân loại khác.
- Datatype/default expression được nhận diện khác.
- Diff báo sai khác ngoài dự kiến.
- Precondition hoặc change type chọn nhánh khác.

So sánh driver và kết quả metadata trước khi kết luận changelog sai. Nếu có nhiều DBMS, sinh update-sql riêng cho từng engine/version được hỗ trợ.

## 8. So sánh dữ liệu và lịch sử Liquibase

### 8.1. Dữ liệu ban đầu ảnh hưởng precondition

Một changeset có thể chỉ chạy khi bảng, cột, dữ liệu hoặc constraint thỏa precondition. Local database ít dữ liệu có thể đạt điều kiện, trong khi production có dữ liệu trùng hoặc NULL làm migration thất bại.

Ví dụ precondition kiểm tra dữ liệu trùng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: add-unique-email
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM (
                SELECT email
                FROM app.customer
                GROUP BY email
                HAVING COUNT(*) > 1
              ) duplicates
      changes:
        - addUniqueConstraint:
            schemaName: app
            tableName: customer
            columnNames: email
            constraintName: uq_customer_email
~~~

Ví dụ cần được điều chỉnh theo cú pháp SQL và DBMS thực tế. Mục tiêu là kiểm tra điều kiện dữ liệu trước khi tạo unique constraint; production có dữ liệu lịch sử nên có thể phát hiện duplicate mà local không có.

Không đổi onFail: HALT thành MARK_RAN chỉ để pipeline xanh. MARK_RAN có thể ghi nhận changeset mà không thực thi thay đổi, khiến schema thực tế không có constraint mong đợi. Chỉ dùng khi semantics đã được thiết kế, có kiểm tra hậu điều kiện và được review.

### 8.2. Đối chiếu DATABASECHANGELOG

Mỗi database có lịch sử triển khai riêng. So sánh:

- ID, AUTHOR, FILENAME hoặc logical path.
- MD5SUM/checksum.
- DATEEXECUTED, ORDEREXECUTED và DEPLOYMENT_ID nếu có.
- EXECTYPE như EXECUTED, RERAN, MARK_RAN hoặc trạng thái theo version.
- Changeset nào pending, đã chạy hoặc bị đánh dấu chạy.

Đừng chỉ đếm số dòng. Hai database có cùng số changeset vẫn có thể có lịch sử khác nhau. Đối chiếu tập định danh changeset và trạng thái, sau đó xác minh object/data thật.

### 8.3. Checksum mismatch

Nếu một môi trường báo checksum mismatch còn môi trường khác không:

1. Xác định changeset, file path và checksum đang lưu.
2. So sánh source changelog đã phát hành với source hiện tại.
3. Kiểm tra Liquibase version và checksum version.
4. Xác định changeset có bị sửa sau khi đã chạy ở môi trường đó không.
5. Thử trên bản sao database có cùng history trước khi thay đổi.

Không dùng clearCheckSums như cách sửa mặc định. Lệnh này buộc tính lại checksum; nó không chứng minh nội dung changeset hợp lệ và không khôi phục schema. Không xóa row DATABASECHANGELOG hoặc sửa checksum thủ công để che khác biệt.

### 8.4. Phân biệt schema drift với lịch sử migration

Một DBA có thể sửa object trực tiếp ở production mà không cập nhật changelog. Khi đó:

- DATABASECHANGELOG có thể cho biết changeset đã chạy.
- Schema thực tế có thể khác với kết quả mà changeset dự kiến tạo.
- Lần migration sau có thể lỗi do object đã tồn tại hoặc definition không giống mong đợi.

Đối chiếu schema thực tế bằng snapshot/diff hoặc truy vấn metadata phù hợp. Nếu phát hiện drift, xác định nguồn thay đổi và thống nhất cách sửa bằng changeset có kiểm soát. Không sửa lịch sử để giả vờ object chưa từng được triển khai.

## 9. Khác biệt do quyền, lock và thứ tự chạy

### 9.1. Quyền database khác nhau

Local developer thường kết nối bằng user có quyền rộng, trong khi CI hoặc production dùng migration account bị giới hạn. Một changeset có thể chạy ở local nhưng thất bại do:

- Thiếu quyền CREATE, ALTER, DROP, INDEX hoặc REFERENCES.
- Thiếu quyền tạo sequence, view, routine hoặc trigger.
- Thiếu quyền ghi DATABASECHANGELOG/DATABASECHANGELOGLOCK.
- Thiếu quyền đọc catalog hoặc dữ liệu mà precondition truy vấn.
- Object thuộc owner khác hoặc schema không cho phép tạo object.

So sánh principal và grants thực tế. Không giải quyết bằng cách cấp DBA/superuser cho toàn bộ môi trường. Cấp quyền đúng object/schema và thử lại bằng đúng principal migration của pipeline.

### 9.2. Lock và nhiều runner đồng thời

CI job và ứng dụng Spring Boot có thể cùng chạy Liquibase; hoặc hai pipeline release cùng cập nhật một database. DATABASECHANGELOGLOCK điều phối các Liquibase runner dùng chung metadata, nhưng không bảo vệ trước mọi thay đổi thủ công hoặc DDL ngoài Liquibase.

Khi gặp lock wait:

1. Xác định job/instance nào đang chạy migration.
2. Kiểm tra log và thời gian bắt đầu của runner.
3. Xác minh process có còn hoạt động hay đã chết.
4. Kiểm tra changeset cuối cùng, object đã tạo và lịch sử.
5. Chỉ giải phóng lock theo runbook sau khi chắc chắn không còn runner sở hữu lock.

Không xóa lock row ngay khi thấy timeout. DDL có thể đã thực thi một phần, nhất là trên DBMS có DDL auto-commit hoặc không hỗ trợ transaction DDL cho thao tác đó.

### 9.3. Thứ tự deploy và phiên bản ứng dụng

Production có thể chạy migration trước khi rollout ứng dụng, còn local startup migration chạy sau khi ứng dụng đã khởi tạo datasource. Nếu thay đổi schema phá vỡ tương thích ngược, ứng dụng cũ hoặc mới có thể thất bại tùy thứ tự.

Ưu tiên chiến lược expand-contract:

1. Thêm cấu trúc mới tương thích với ứng dụng cũ.
2. Deploy ứng dụng có thể làm việc với cả cấu trúc cũ và mới.
3. Backfill, xác minh dữ liệu và chuyển traffic.
4. Chỉ xóa cấu trúc cũ ở release sau khi không còn consumer.

Ghi lại thứ tự migration, deploy và rollout cho mỗi môi trường.

## 10. Quy trình chẩn đoán có thứ tự

Khi local, CI và production cho kết quả khác nhau, thực hiện theo thứ tự sau:

### Bước 1: Đóng băng bằng chứng

Lưu commit, artifact digest, version toolchain, log, SQL preview, bộ lọc và thời điểm chạy. Tránh sửa changelog hoặc cấu hình trước khi có bản ghi ban đầu.

### Bước 2: Xác minh target

Xác nhận DBMS, server version, database/catalog, schema, principal và JDBC driver. Loại trừ khả năng chạy nhầm database hoặc schema.

### Bước 3: So sánh source và classpath

Đối chiếu commit, artifact, changelog resource, include path, Liquibase core, extension và driver. Kiểm tra JAR/container thực tế.

### Bước 4: So sánh cấu hình hiệu lực

Đối chiếu profile, contexts, labels, parameters, default schema, Liquibase schema, JDBC properties và session settings. Kiểm tra property source ghi đè.

### Bước 5: So sánh tập changeset

Chạy validate, status --verbose và update-sql bằng đúng version/configuration. So sánh changeset pending, SQL và thứ tự.

### Bước 6: So sánh lịch sử và schema

Đối chiếu DATABASECHANGELOG, checksum, execution type, lock và object thực tế. Kiểm tra dữ liệu liên quan precondition/constraint.

### Bước 7: Kiểm tra quyền và concurrency

Chạy bằng đúng migration principal; xác định runner khác, lock wait, transaction boundary và quyền catalog/object.

### Bước 8: Tái hiện trong môi trường gần production

Khôi phục snapshot đã làm sạch dữ liệu nhạy cảm hoặc tạo dataset tổng hợp đại diện. Dùng cùng artifact, DBMS version, driver, parameters và principal. Chỉ thay một biến trong mỗi lượt thử để xác định yếu tố gây khác biệt.

### Bước 9: Sửa nguyên nhân và thêm regression check

Sửa cấu hình, dependency, quyền, changelog hoặc quy trình deploy tại đúng lớp gây lỗi. Thêm kiểm tra vào pipeline để lỗi không tái xuất hiện.

## 11. Các lệnh kiểm tra hữu ích

Chạy lệnh với cùng changelog, version, JDBC driver, contexts, labels, parameters và schema mà môi trường thực tế sử dụng. Cách truyền option có thể khác theo Liquibase version và cách quản lý cấu hình.

~~~bash
liquibase --version
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Ý nghĩa:

- --version: xác nhận Liquibase CLI thực tế.
- validate: kiểm tra changelog và các tham chiếu có thể xác minh mà không thực thi migration.
- status --verbose: liệt kê changeset chưa được triển khai theo filter hiện tại.
- update-sql: sinh SQL dự kiến để review; không thay thế update trên database thử nghiệm.

Nếu dùng diff/diff-changelog, phải cấu hình reference database và target database đúng cách, đồng thời hiểu snapshot/metadata của từng DBMS. Diff phát hiện khác biệt cấu trúc nhưng không tự xác định nguồn gốc hay cách sửa an toàn.

Trong Spring Boot, các lệnh CLI chỉ có giá trị so sánh nếu chúng dùng cùng cấu hình hiệu lực với ứng dụng. Một file liquibase.properties khác contexts hoặc parameters không phải phép tái hiện tương đương.

## 12. Tái hiện và kiểm thử trong CI

### 12.1. Dùng DBMS đại diện

Nếu production dùng PostgreSQL, test migration trên PostgreSQL cùng major version hoặc phiên bản tương đương được phê duyệt. H2 có thể hữu ích cho kiểm thử logic ứng dụng, nhưng không chứng minh SQL generator, DDL, metadata, collation, lock và transaction của PostgreSQL/MySQL/SQL Server/Oracle.

### 12.2. Kiểm tra cả database trống và database có lịch sử

Hai kịch bản phát hiện lỗi khác nhau:

| Trạng thái | Lỗi thường phát hiện |
|---|---|
| Database trống | Thiếu include, sai thứ tự tạo object, thiếu bootstrap/schema, fresh install lỗi |
| Database có lịch sử | Checksum mismatch, changeset pending sai, precondition phụ thuộc dữ liệu, schema drift |
| Database có dữ liệu đại diện | Duplicate, NULL, FK violation, backfill chậm, constraint không tạo được |

Không chỉ chạy update trên database mới rồi kết luận production an toàn.

### 12.3. Một pipeline migration tham khảo

~~~text
Checkout exact commit
        |
        v
Build one immutable artifact
        |
        v
Record Java / Liquibase / JDBC / extension versions
        |
        v
Resolve effective profile, contexts, labels and schemas
        |
        v
Validate changelog
        |
        v
Run status and generate update-sql
        |
        v
Test fresh DB and upgraded DB on target DBMS
        |
        v
Review SQL, data checks, permissions and rollback plan
        |
        v
Approve target and promote the same artifact
        |
        v
Run production migration once
        |
        v
Verify history, schema, data and application health
~~~

Pipeline nên dừng nếu target không đúng allowlist, artifact digest không khớp, changeset pending ngoài dự kiến, SQL preview thay đổi chưa review, extension thiếu hoặc test migration thất bại.

### 12.4. Giữ cấu hình CI và production có thể so sánh

Không nhất thiết mọi môi trường có cùng context, schema hay credential; chúng có thể khác có chủ đích. Điều cần thiết là khác biệt được khai báo và review. Dùng cùng artifact và version công cụ, đồng thời lưu riêng cấu hình từng môi trường để có thể tái hiện.

## 13. Bảng triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra đầu tiên |
|---|---|---|
| Local chạy, CI báo unknown change type | Extension thiếu hoặc khác version/classpath | Dependency tree, runtime classpath, SPI |
| CI chạy, production không thấy changeset | Context/label/profile khác | Filter hiệu lực và status --verbose |
| Production tạo object vào schema lạ | Parameter, default schema hoặc session search path | SQL preview, schemaName và current schema |
| Local pass, production unique constraint thất bại | Dữ liệu production có duplicate/NULL | Query precondition trên dataset đại diện |
| Một môi trường báo checksum mismatch | Changeset đã bị sửa hoặc version/history khác | Source đã phát hành, checksum và Liquibase version |
| SQL preview khác nhau | DBMS, driver, version, parameter hoặc extension | Dấu vân tay DBMS và toolchain |
| CI pass nhưng ứng dụng startup fail | CLI và Spring Boot dùng config/version khác | Auto-configuration, datasource, classpath |
| Migration timeout ở production | Dữ liệu lớn, lock, index build, transaction | Execution plan, lock wait, duration và DB size |
| Liquibase lock không được giải phóng | Runner cũ, job bị kill hoặc lỗi giữa DDL | Process đang chạy và trạng thái object |
| Một changeset bị bỏ qua | Precondition, context/label hoặc MARK_RAN | Log precondition, history và filter |
| Local chạy bằng admin, CI bị permission denied | Quyền local quá rộng | Grants của migration principal |
| Chạy lại cho kết quả khác | Dữ liệu thay đổi, nondeterministic SQL hoặc nhiều runner | Idempotency, dữ liệu đầu vào và execution order |
| CI có resource nhưng production JAR thiếu | Build resource filtering/packaging khác | Nội dung JAR/image và include path |
| Thời gian/ngày khác giữa môi trường | Timezone/session/clock khác | UTC, DB session timezone và expression |

## 14. Những cách xử lý dễ làm vấn đề nghiêm trọng hơn

- **Không sửa changeset đã chạy để làm các môi trường giống nhau.** Hãy tạo changeset mới hoặc khôi phục nội dung đã phát hành sau khi xác minh checksum.
- **Không chạy clearCheckSums hàng loạt.** Chỉ dùng khi đã xác định nguyên nhân và hiểu ảnh hưởng tới lịch sử.
- **Không xóa DATABASECHANGELOG hoặc lock row tùy tiện.** Có thể khiến Liquibase chạy lại DDL hoặc che giấu trạng thái chưa hoàn tất.
- **Không đổi precondition thành MARK_RAN để pipeline xanh.** Cần chứng minh object/data mong đợi đã tồn tại và có hậu kiểm.
- **Không cấp quyền DBA cho CI hoặc ứng dụng chỉ để vượt lỗi permission.** Xác định quyền cụ thể của changeset.
- **Không chạy update trực tiếp trên production để “thử xem sao”.** Sinh SQL, review, thử trên DBMS đại diện và phê duyệt trước.
- **Không build lại artifact khác cho production mà bỏ qua kiểm thử.** Promote đúng artifact đã qua kiểm tra.
- **Không retry mù sau timeout.** DDL có thể đã thực thi dù client không nhận được phản hồi.

## 15. Ví dụ điều tra: CI có changeset pending, production không có

Giả sử một changeset add-customer-status có context common, label release-2026-11. CI báo changeset pending và SQL preview có câu ALTER TABLE; production báo không còn changeset cần chạy.

Thực hiện:

1. Xác nhận cả hai đang dùng cùng commit, artifact, Liquibase core và extension.
2. So sánh master changelog, include path và logical file path.
3. Ghi context và label filter hiệu lực. Nếu production dùng label filter không chứa release-2026-11, changeset có thể bị loại khỏi tập được chọn.
4. Đối chiếu row tương ứng trong DATABASECHANGELOG của production theo ID, AUTHOR và FILENAME.
5. Nếu row đã tồn tại, kiểm tra EXECTYPE, checksum và object thực tế.
6. Nếu row chưa tồn tại nhưng status không liệt kê, kiểm tra filter, precondition và DBMS applicability.
7. Chạy update-sql với cấu hình production đã làm sạch secrets trên database bản sao.
8. Xác định production đã có object do thao tác thủ công hay không trước khi quyết định changeset sửa chữa.

Không kết luận production đã an toàn chỉ vì status báo không có pending. Cần xác minh changeset được chọn đúng, history đúng và object thực tế đúng.

## 16. Ví dụ điều tra: local pass nhưng production thất bại khi thêm unique constraint

Developer thử trên database mới với vài bản ghi mẫu nên email không trùng. Production có dữ liệu lịch sử chứa nhiều bản ghi cùng email sau khi chuẩn hóa chữ hoa/thường.

Quy trình xử lý:

1. Lấy bản sao dữ liệu production đã làm sạch hoặc tạo dataset tổng hợp bảo toàn phân bố duplicate.
2. Chạy query kiểm tra duplicate theo đúng collation/case sensitivity của DBMS production.
3. Xác định quy tắc nghiệp vụ: email có phân biệt hoa/thường không, NULL có được phép không, bản ghi nào được giữ.
4. Viết data migration/backfill hoặc quy trình xử lý duplicate có kiểm soát.
5. Chạy precondition để migration dừng nếu dữ liệu vẫn vi phạm.
6. Tạo unique constraint sau khi dữ liệu đã đạt điều kiện.
7. Thử toàn bộ upgrade path trên DB có history và dữ liệu đại diện.
8. Đo thời gian, lock và ảnh hưởng tới traffic trước production.

Kết quả khác nhau không nhất thiết do Liquibase hoặc CI. Nó có thể phản ánh dữ liệu và semantics của DBMS thật. Phải xử lý dữ liệu theo quy tắc nghiệp vụ trước khi tạo constraint.

## 17. Checklist phòng ngừa khác biệt môi trường

- [ ] Developer, CI và production triển khai cùng commit/artifact đã được xác định.
- [ ] Artifact có checksum/digest và không bị build lại ngoài quy trình promote.
- [ ] Java, Spring Boot, Liquibase core/CLI, extension và JDBC driver được pin và ghi version.
- [ ] Dependency graph không có version xung đột hoặc extension thiếu runtime classpath.
- [ ] Master changelog, include và SQL resource có trong artifact cuối.
- [ ] Active profiles và cấu hình Liquibase hiệu lực được ghi nhận, đã mask secrets.
- [ ] Contexts, label filter, DBMS filter và parameters được review theo môi trường.
- [ ] JDBC URL trỏ đúng database/catalog; default schema và metadata schema đúng.
- [ ] DBMS engine/version, collation, timezone, SQL mode và session settings được ghi nhận.
- [ ] Migration principal có quyền cần thiết; runtime principal không được dùng thay cho migration.
- [ ] Database trống và database có history đều được kiểm thử.
- [ ] Dataset test có duplicate/NULL/biên dữ liệu phù hợp với precondition và constraint.
- [ ] validate, status --verbose và update-sql chạy bằng đúng cấu hình mục tiêu.
- [ ] Đã đối chiếu DATABASECHANGELOG, checksum, execution type, lock và schema thực tế.
- [ ] Chỉ có một quy trình migration được phép chạy trên target trong một đợt deploy.
- [ ] Có kế hoạch rollback/forward-fix và cách xử lý DDL đã thực thi một phần.
- [ ] Có smoke test sau migration và log đủ để truy vết release mà không lộ secret.

**Kết luận:** khác biệt giữa máy phát triển, CI và production thường xuất phát từ source/artifact, toolchain, cấu hình hiệu lực, DBMS/driver, dữ liệu, lịch sử Liquibase, quyền hoặc thứ tự chạy. Hãy lập dấu vân tay cho từng lần migration, so sánh theo từng lớp, tái hiện bằng đúng artifact và DBMS đại diện, rồi kiểm tra tập changeset, SQL preview, history và object thực tế. Khi CI kiểm thử cả database trống lẫn database có lịch sử, production nhận đúng artifact đã review và chỉ một runner thực hiện migration theo quy trình, DATABASE_SCHEMA_MIGRATION_LIQUIBASE sẽ có kết quả nhất quán và dễ điều tra hơn qua các môi trường.
