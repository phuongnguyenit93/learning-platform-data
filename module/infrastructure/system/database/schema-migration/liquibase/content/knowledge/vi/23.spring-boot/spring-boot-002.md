# Cấu trúc tài nguyên và cấu hình spring.liquibase.change-log

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring Boot, Liquibase cần một điểm vào để biết phải đọc changelog nào, cùng quy tắc tìm các file migration được tham chiếu từ đó. Vị trí file, cách phân giải đường dẫn, thứ tự include và cấu hình kết nối đều ảnh hưởng trực tiếp tới việc migration có chạy đúng khi ứng dụng khởi động hay không.

Một cấu hình có thể hoạt động trong IDE nhưng thất bại sau khi đóng gói JAR hoặc chạy trong container. Master changelog có thể được tìm thấy nhưng file con hoặc SQL file lại thiếu. Liquibase cũng có thể chạy trên một database khác với database mà ứng dụng sử dụng nếu cấu hình datasource không thống nhất. Vì vậy, cấu trúc resources và thuộc tính **spring.liquibase.change-log** cần được thiết kế, kiểm thử cùng artifact triển khai.

Bài thuộc chương **Spring Boot** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào **cấu trúc tài nguyên và cấu hình spring.liquibase.change-log**.

Sau bài học, bạn cần có thể:

1. Tổ chức changelog trong resources theo cấu trúc rõ ràng và ổn định.
2. Phân biệt đường dẫn classpath, file system và đường dẫn tương đối.
3. Cấu hình spring.liquibase.change-log trong application.yml hoặc application.properties.
4. Tạo master changelog và quản lý file con bằng include/includeAll.
5. Phân biệt datasource ứng dụng với kết nối riêng dành cho Liquibase.
6. Quản lý profile, context, label và parameter theo môi trường.
7. Đảm bảo changelog và SQL file được đóng gói vào JAR/container.
8. Kiểm thử việc nạp changelog và migration trên đúng DBMS.

## 2. Spring Boot tìm changelog từ đâu?

Thuộc tính **spring.liquibase.change-log** xác định changelog gốc mà Spring Boot cấu hình cho Liquibase. Một đường dẫn classpath thường dùng là:

~~~text
classpath:/db/changelog/db.changelog-master.yaml
~~~

Tài nguyên này thường nằm dưới:

~~~text
src/main/resources/db/changelog/db.changelog-master.yaml
~~~

Một cấu trúc project minh họa:

~~~text
src/
  main/
    resources/
      application.yml
      application-dev.yml
      application-prod.yml
      db/
        changelog/
          db.changelog-master.yaml
          changes/
            001-create-customer.yaml
            002-create-order.yaml
            003-add-order-status.yaml
          reference-data/
            001-order-status.yaml
          sql/
            postgresql/
              create-order-summary.sql
~~~

Khi build ứng dụng, tài nguyên trong src/main/resources thường được đưa vào classpath. Trong JAR, chúng nằm bên trong archive; không nhất thiết tồn tại dưới dạng file vật lý trong thư mục làm việc.

**Không ghi src/main/resources vào đường dẫn classpath.** Ví dụ đúng là classpath:/db/changelog/db.changelog-master.yaml, vì đường dẫn bắt đầu từ gốc tài nguyên đã được đóng gói.

## 3. Classpath và file system

| Kiểu đường dẫn | Ví dụ | Khi phù hợp |
|---|---|---|
| Classpath | classpath:/db/changelog/db.changelog-master.yaml | Changelog đi cùng artifact ứng dụng |
| File system | file:/opt/orders/migrations/db.changelog-master.yaml | Changelog được mount/cung cấp bên ngoài JAR |
| Tương đối | db/changelog/db.changelog-master.yaml | Chỉ khi cơ chế phân giải và working directory đã rõ |

### 3.1. Classpath

~~~yaml
spring:
  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Ưu điểm:

- Changelog đi cùng phiên bản ứng dụng.
- Local, test và production có thể dùng cùng artifact.
- Không phụ thuộc thư mục làm việc của tiến trình.
- Dễ kiểm tra nội dung migration đã đóng gói.

Đây thường là lựa chọn phù hợp cho ứng dụng Spring Boot. Nếu database migration được phát hành độc lập với ứng dụng, nhóm có thể tạo artifact migration riêng nhưng vẫn cần quản lý phiên bản và nguồn gốc changelog.

### 3.2. File system

~~~yaml
spring:
  liquibase:
    change-log: file:/opt/orders/migrations/db.changelog-master.yaml
~~~

Cách này phù hợp khi hạ tầng chủ động mount changelog từ volume hoặc cung cấp bundle migration bên ngoài ứng dụng. Cần xác nhận file tồn tại trên đúng máy/container, tiến trình có quyền đọc, file con và SQL file đều có mặt, và nội dung không thể bị chỉnh sửa ngoài quy trình release.

Nếu file system thay đổi độc lập với image ứng dụng, hai lần chạy cùng một image có thể nạp nội dung migration khác nhau. Khi đó, changelog bên ngoài cũng phải có version/artifact và dấu vết review riêng.

### 3.3. Đường dẫn master và file con là hai việc khác nhau

spring.liquibase.change-log trỏ tới **master changelog**. Các file con được master nạp bằng include hoặc includeAll. Đường dẫn file con được phân giải theo cấu hình của include, vì vậy hãy đặt relativeToChangelogFile rõ ràng khi muốn tính đường dẫn từ thư mục chứa changelog hiện tại.

## 4. Master changelog là điểm vào ổn định

Một master changelog giúp xác định chính xác những file nào thuộc lịch sử migration của ứng dụng.

Ví dụ cấu trúc:

~~~text
db/changelog/
  db.changelog-master.yaml
  001-initial-schema.yaml
  002-reference-data.yaml
  changes/
    003-add-customer-email.yaml
    004-create-order-index.yaml
  reporting/
    005-create-order-summary.yaml
  sql/
    postgresql/
      refresh-reporting-view.sql
~~~

Nội dung master:

~~~yaml
databaseChangeLog:
  - include:
      file: 001-initial-schema.yaml
      relativeToChangelogFile: true
  - include:
      file: 002-reference-data.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-add-customer-email.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/004-create-order-index.yaml
      relativeToChangelogFile: true
  - include:
      file: reporting/005-create-order-summary.yaml
      relativeToChangelogFile: true
~~~

Master giữ cấu hình Spring Boot ổn định khi nhóm thêm migration. File mới được đưa vào lịch sử bằng cách thêm include hoặc đặt trong thư mục được includeAll có kiểm soát.

Lợi ích của master changelog:

- Kiểm soát thứ tự include và phụ thuộc.
- Review được chính xác file nào tham gia release.
- Tách migration theo chủ đề mà vẫn có một điểm vào.
- Giảm nguy cơ nạp nhầm file nháp.
- Giữ cấu hình Spring Boot ngắn gọn.

Không tạo nhiều master khác nhau cho dev/test/production chỉ vì URL hoặc database name khác nhau. Nếu các môi trường thuộc cùng một ứng dụng và cần chung lịch sử schema, nên dùng cùng master và thay đổi cấu hình kết nối theo môi trường.

## 5. include và includeAll

### 5.1. include: liệt kê file tường minh

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-order.yaml
      relativeToChangelogFile: true
~~~

include phù hợp khi nhóm muốn danh sách migration và thứ tự được review ngay trong master. Mỗi file mới cần được thêm vào master, nhưng chính bước đó giúp reviewer thấy rõ một changeset mới tham gia release.

### 5.2. includeAll: nạp thư mục

~~~yaml
databaseChangeLog:
  - includeAll:
      path: changes
      relativeToChangelogFile: true
~~~

includeAll tự động nạp các changelog trong thư mục theo quy tắc sắp xếp và lọc của Liquibase. Nó hữu ích khi nhóm có quy ước đặt tên và bảo đảm mọi file trong thư mục đều được phép triển khai.

Cần lưu ý:

- Không đặt file nháp, backup hoặc tài liệu trong thư mục includeAll.
- Đặt tên có thứ tự ổn định, ví dụ 001, 002, 003.
- Kiểm tra resource comparator và filter nếu dự án tùy chỉnh.
- Tránh để một file vừa được include tường minh vừa nằm trong thư mục includeAll.
- Mỗi file được thêm vào thư mục có thể tham gia migration kế tiếp, nên review thay đổi thư mục rất quan trọng.

### 5.3. Chọn cách nào?

| Tiêu chí | include | includeAll |
|---|---|---|
| Danh sách file | Tường minh | Dựa vào thư mục |
| Thứ tự | Khai báo trong master | Theo quy tắc sắp xếp |
| Nạp nhầm file | Dễ kiểm soát hơn | Cần quản lý folder chặt |
| Thêm file | Cập nhật master | Thêm vào thư mục |
| Phù hợp | Release cần review chặt | Folder có quy ước rõ và ổn định |

Có thể kết hợp hai cách, miễn là không nạp trùng và reviewer hiểu chính xác tập changeset sẽ chạy.

## 6. Tổ chức file theo vòng đời và trách nhiệm

Một cấu trúc khác có thể chia theo loại đối tượng:

~~~text
db/changelog/
  db.changelog-master.yaml
  schema/
    001-create-customer.yaml
    002-create-order.yaml
  data/
    101-insert-reference-status.yaml
  indexes/
    201-create-order-index.yaml
  views/
    301-create-order-summary.yaml
  sql/
    postgresql/
      create-order-summary.sql
    oracle/
      create-order-summary.sql
~~~

Có thể chia theo domain nghiệp vụ thay vì loại đối tượng; điều quan trọng là người review tìm được thay đổi và phụ thuộc.

Nguyên tắc:

- Tên file duy nhất, mô tả mục đích.
- Mỗi changeset có id/author ổn định.
- Không sửa changeset đã triển khai để thêm thay đổi mới.
- SQL file được tham chiếu phải được commit và đóng gói.
- SQL đặc thù DBMS nằm trong nhánh rõ ràng.
- Master changelog là điểm vào được cấu hình cho ứng dụng.

Đường dẫn file có liên quan tới định danh changeset trong lịch sử Liquibase. Di chuyển/đổi tên file sau triển khai có thể làm thay đổi cách công cụ nhận diện FILENAME; cần xem xét logicalFilePath và thử trên database có lịch sử trước khi thay đổi cấu trúc.

## 7. Cấu hình spring.liquibase.change-log trong application.yml

Cấu hình tối thiểu:

~~~yaml
spring:
  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Cấu hình có thêm schema metadata:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: app
    liquibase-schema: platform
    database-change-log-table: DATABASECHANGELOG
    database-change-log-lock-table: DATABASECHANGELOGLOCK
~~~

Ý nghĩa:

- **enabled**: bật/tắt Liquibase auto-configuration của Spring Boot.
- **change-log**: đường dẫn master changelog.
- **default-schema**: schema mặc định cho các đối tượng trong changeset khi không chỉ rõ schema, tùy DBMS.
- **liquibase-schema**: schema lưu bảng metadata Liquibase nếu được cấu hình và DBMS hỗ trợ.
- **database-change-log-table**: tên bảng lịch sử changeset.
- **database-change-log-lock-table**: tên bảng điều phối khóa changelog.

Các thuộc tính và giá trị mặc định có thể thay đổi theo phiên bản Spring Boot/Liquibase. Cần xác minh schema metadata tồn tại, tài khoản có quyền phù hợp và DBMS hỗ trợ cấu hình đã chọn.

### 7.1. Cấu hình application.properties

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.yaml
spring.liquibase.default-schema=app
spring.liquibase.liquibase-schema=platform
spring.liquibase.database-change-log-table=DATABASECHANGELOG
spring.liquibase.database-change-log-lock-table=DATABASECHANGELOGLOCK
~~~

Không khai báo cùng một thuộc tính ở nhiều nguồn cấu hình mà không hiểu precedence của Spring Boot. Profile, environment variable, command line hoặc config server có thể ghi đè giá trị trong application.yml.

## 8. Tên master có thể thay đổi, điểm vào phải ổn định

Tên file không bắt buộc là db.changelog-master.yaml. Ví dụ:

~~~yaml
spring:
  liquibase:
    change-log: classpath:/db/changelog/master.yaml
~~~

Điều kiện là file tồn tại, hợp lệ, các file con phân giải được, changeset có danh tính ổn định và artifact chứa đủ tài nguyên.

Đừng đổi property mỗi lần thêm một file migration. File mới nên được nối vào master bằng include/includeAll. Nếu thực sự có nhiều sản phẩm hoặc schema độc lập, mỗi master phải có phạm vi, chủ sở hữu và lịch sử riêng được xác định rõ.

## 9. Datasource ứng dụng và kết nối Liquibase

Spring Boot có thể dùng datasource ứng dụng để chạy Liquibase nếu không cấu hình kết nối riêng. Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_runtime
    password: ${APP_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Cấu hình này dùng datasource chính theo cơ chế auto-configuration. Tuy nhiên, runtime role thường chỉ cần quyền nghiệp vụ, trong khi migration có thể cần quyền DDL. Nhiều hệ thống tách tài khoản migration khỏi tài khoản runtime.

### 9.1. Kết nối riêng cho Liquibase

Spring Boot hỗ trợ các thuộc tính riêng như url, user và password dưới prefix spring.liquibase:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_runtime
    password: ${APP_DB_PASSWORD}

  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    url: jdbc:postgresql://localhost:5432/orders
    user: migration_owner
    password: ${MIGRATION_DB_PASSWORD}
~~~

Khi dùng kết nối riêng, xác minh:

- Liquibase và ứng dụng trỏ đúng database/cluster.
- Schema mặc định và schema metadata phù hợp.
- Migration role có quyền cần thiết, không dùng superuser nếu không bắt buộc.
- Runtime role không thừa hưởng quyền DDL ngoài ý muốn.
- Secret được cấp qua nguồn cấu hình an toàn.
- CI/CD và ứng dụng không cùng chạy migration mà thiếu điều phối.

Nếu Liquibase migrate database A trong khi ứng dụng đọc database B, ứng dụng có thể khởi động nhưng lỗi vì thiếu bảng/cột. Kiểm tra database identity trên cả hai kết nối.

### 9.2. DataSource bean tùy chỉnh

Nếu dự án định nghĩa nhiều DataSource bean, cần xác định rõ bean nào dành cho Liquibase bằng cơ chế qualifier/annotation được Spring Boot hỗ trợ ở phiên bản đang dùng. Không giả định chỉ đặt tên bean là liquibaseDataSource thì mọi cấu hình đều tự chọn đúng.

Kiểm tra bean được tạo trước khi Liquibase chạy, không có vòng phụ thuộc tới bảng chưa được tạo, và integration test sử dụng đúng datasource.

## 10. Profile theo môi trường

Spring Boot có thể dùng:

~~~text
application.yml
application-dev.yml
application-test.yml
application-staging.yml
application-prod.yml
~~~

Ví dụ:

~~~yaml
# application.yml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

~~~yaml
# application-dev.yml
spring:
  liquibase:
    contexts: dev
~~~

~~~yaml
# application-prod.yml
spring:
  liquibase:
    contexts: prod
~~~

Ví dụ chỉ minh họa context. Nếu changelog không có changeset gắn context tương ứng, cấu hình này không tự tạo ra thay đổi.

Thông thường các môi trường cùng ứng dụng nên dùng chung master changelog, cùng lịch sử migration; URL, user, password và parameter được cấp theo môi trường. Chỉ tạo master riêng khi database/schema thực sự thuộc phạm vi sản phẩm độc lập.

## 11. Context và label

Spring Boot có thể truyền contexts và labels cho Liquibase. Chúng lọc changeset theo mục đích hoặc nhóm chức năng, không thay thế profile và không phải cách che giấu drift.

Ví dụ changeset dữ liệu demo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 101-insert-demo-customer
      author: platform-team
      context: dev
      changes:
        - insert:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: display_name
                  value: Demo Customer
~~~

Cấu hình:

~~~yaml
spring:
  liquibase:
    contexts: dev
~~~

Changeset demo chỉ nên chạy trong môi trường được chọn. Cần kiểm tra cách kết hợp context/label và mặc định của phiên bản Liquibase. Không dùng context để loại bỏ một thay đổi schema bắt buộc khỏi production.

Label có thể nhóm migration theo chức năng hoặc phạm vi release, ví dụ reporting. Pipeline cần kiểm tra tập changeset được chọn sau khi áp dụng label.

## 12. Liquibase parameters

Changelog có thể tham chiếu parameter được cấu hình từ Spring Boot:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 110-create-app-table
      author: platform-team
      changes:
        - createTable:
            schemaName: ${appSchema}
            tableName: customer_note
            columns:
              - column:
                  name: note_id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Cấu hình:

~~~yaml
spring:
  liquibase:
    parameters:
      appSchema: app
~~~

Parameter được thay thế theo cơ chế Liquibase. Kiểm tra changelog sau khi resolve và tránh xung đột với placeholder của Spring hoặc resource filtering của build tool.

### 12.1. Thay thế chuỗi không phải prepared statement

Thay thế placeholder không tương đương bind parameter của JDBC. Đặc biệt schema, table và role là SQL identifier.

- Chỉ lấy identifier từ allowlist.
- Không lấy tên schema/role từ request.
- Không ghép SQL tùy ý từ đầu vào không tin cậy.
- Dùng change type có cấu trúc khi phù hợp.
- Review update-sql sau khi parameter được resolve.

### 12.2. Secret phải nằm ngoài changelog

Không lưu password, token, private key hoặc chuỗi kết nối trong file migration. Cấp secret qua environment, secret manager hoặc hệ thống cấu hình bảo mật.

~~~yaml
spring:
  datasource:
    password: ${APP_DB_PASSWORD}
  liquibase:
    password: ${MIGRATION_DB_PASSWORD}
~~~

Không in secret ra log hoặc đưa chúng vào artifact công khai.

## 13. Phân giải đường dẫn file con

Giả sử master nằm tại:

~~~text
db/changelog/db.changelog-master.yaml
~~~

và file con tại:

~~~text
db/changelog/changes/001-create-customer.yaml
~~~

Có thể khai báo:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
~~~

Khi relativeToChangelogFile là true, đường dẫn file con được tính tương đối với changelog chứa include. Nếu bỏ thuộc tính hoặc đặt false, cách phân giải có thể dựa vào resource accessor/classpath root và cấu hình khác.

Lỗi thường gặp là master nằm ở db/changelog nhưng include lại viết db/changelog/changes/... đồng thời relativeToChangelogFile là true. Đường dẫn có thể bị ghép lặp thành db/changelog/db/changelog/changes. Luôn kiểm tra đường dẫn từ chính file chứa include.

## 14. includeAll và thứ tự file

Ví dụ folder:

~~~text
changes/
  001-create-customer.yaml
  002-create-order.yaml
  003-add-order-status.yaml
  010-create-reporting-view.yaml
~~~

Tên có tiền tố số giúp người đọc nhận biết thứ tự. Tuy nhiên, cần dựa trên cơ chế sắp xếp/resource comparator của Liquibase, không dựa vào thứ tự hiển thị trong file explorer.

Không đặt file backup, draft, tài liệu, SQL không được tham chiếu hoặc changelog của module khác trong thư mục includeAll. Nếu cần filter, kiểm tra cấu hình và cách xử lý phần mở rộng/đường dẫn của đúng phiên bản công cụ.

Với migration production có phụ thuộc nhạy cảm, include tường minh thường dễ review hơn. Nếu dùng includeAll, hãy coi mọi file mới trong folder như một thay đổi có thể tham gia release.

## 15. Đóng gói resources vào JAR

Classpath chỉ hoạt động nếu file được đóng gói vào artifact. IDE có thể đọc file từ src/main/resources dù JAR thiếu file do cấu hình resources sai.

Kiểm tra khi dự án:

- Thay đổi sourceSets/resources.
- Dùng resource filtering.
- Chia ứng dụng thành nhiều module.
- Đóng gói executable JAR hoặc layered container.
- Đưa changelog vào dependency JAR riêng.
- Loại trừ một số phần mở rộng file khỏi artifact.

Có thể liệt kê nội dung JAR:

~~~bash
jar tf build/libs/orders-service.jar
~~~

Với Maven, artifact có thể nằm trong target thay vì build/libs. Xác nhận JAR có master, các file con và SQL file được tham chiếu. Master tồn tại nhưng file con thiếu vẫn khiến Liquibase thất bại.

### 15.1. Resource filtering và placeholder

Một số build tool có thể thay thế placeholder trong resources lúc đóng gói; Liquibase cũng có cú pháp placeholder riêng. Nếu Maven filtering hoặc plugin resource thay đổi chuỗi ${...}, nội dung trong JAR có thể khác file nguồn.

Xác định rõ:

- Changelog có được filter lúc build không?
- Placeholder thuộc Spring hay Liquibase?
- Giá trị được resolve lúc build hay runtime?
- Có cần escape placeholder trong build không?
- Artifact có chứa secret sau filtering không?

Thường nên tránh build-time filtering không cần thiết và cấp parameter theo runtime có kiểm soát.

## 16. spring.liquibase.enabled và chủ sở hữu migration

~~~yaml
spring:
  liquibase:
    enabled: true
~~~

Khi bật, Spring Boot auto-configure Liquibase theo vòng đời khởi động. Nếu đặt false, auto-configuration Liquibase bị tắt.

### 16.1. Ứng dụng tự chạy migration

Phù hợp với hệ thống nhỏ hoặc triển khai đơn giản. Cần bảo đảm nhiều replica không gây cạnh tranh không cần thiết, DATABASECHANGELOGLOCK được theo dõi, migration tương thích với phiên bản ứng dụng và tài khoản có quyền cần thiết.

Khi nhiều replica khởi động cùng lúc, Liquibase có cơ chế lock điều phối, nhưng các replica khác có thể phải chờ và bị ảnh hưởng bởi startup/readiness timeout.

### 16.2. Job CI/CD chạy migration riêng

Phù hợp khi migration dài, cần phê duyệt hoặc quyền DDL được tách khỏi runtime. Pipeline chạy Liquibase một lần, kiểm tra kết quả rồi mới khởi động ứng dụng.

Ví dụ profile production:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Chỉ dùng khi pipeline hoặc một thành phần khác thực sự sở hữu migration. Nếu tắt auto migration mà không có job thay thế, database có thể chưa được cập nhật khi ứng dụng chạy.

Không để job CI/CD và mọi replica cùng là chủ sở hữu migration mà thiếu quy tắc điều phối.

## 17. Các thuộc tính thường gặp

| Thuộc tính | Mục đích | Lưu ý |
|---|---|---|
| spring.liquibase.enabled | Bật/tắt auto-configuration | Không thay thế việc kiểm soát job riêng |
| spring.liquibase.change-log | Đường dẫn master changelog | Nên dùng classpath ổn định cho resource đóng gói |
| spring.liquibase.url | URL riêng cho Liquibase | Xác minh cùng database/cluster mong muốn |
| spring.liquibase.user | Tài khoản migration | Có thể tách khỏi runtime |
| spring.liquibase.password | Mật khẩu migration | Lấy từ secret manager/environment |
| spring.liquibase.default-schema | Schema mặc định cho changeset | Khác schema metadata |
| spring.liquibase.liquibase-schema | Schema lưu bảng metadata | Cần quyền và schema phù hợp |
| spring.liquibase.contexts | Chọn changeset theo context | Không loại bỏ schema bắt buộc |
| spring.liquibase.labels | Chọn changeset theo label | Kiểm tra tập changeset được chọn |
| spring.liquibase.parameters | Parameter cho changelog | Không ghép identifier từ input không tin cậy |
| spring.liquibase.drop-first | Drop object trước migration | Rất nguy hiểm nếu bật nhầm môi trường |
| spring.liquibase.clear-checksums | Xóa checksum đã lưu | Không phải bước mặc định của pipeline |

Danh sách và cách bind có thể thay đổi theo phiên bản Spring Boot. Hãy kiểm tra metadata cấu hình của phiên bản dự án.

Đặc biệt, drop-first không phải cách reset production an toàn; clear-checksums không sửa schema drift. Các thuộc tính quản trị cần được kiểm soát chặt.

## 18. Ví dụ cấu hình theo profile

Cấu hình chung:

~~~yaml
# application.yml
spring:
  datasource:
    url: ${APP_DB_URL}
    username: ${APP_DB_USER}
    password: ${APP_DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: app
    liquibase-schema: platform
    user: ${MIGRATION_DB_USER}
    password: ${MIGRATION_DB_PASSWORD}
~~~

Cấu hình dev:

~~~yaml
# application-dev.yml
spring:
  liquibase:
    contexts: dev
~~~

Cấu hình production khi CI/CD sở hữu migration:

~~~yaml
# application-prod.yml
spring:
  liquibase:
    enabled: false
~~~

Các placeholder phải được cung cấp từ nguồn cấu hình hoặc secret store. Nếu Liquibase dùng URL riêng, xác minh nó trỏ đúng database mà ứng dụng sẽ sử dụng.

## 19. Chẩn đoán lúc khởi động

Khi Liquibase không chạy như mong đợi, kiểm tra theo thứ tự:

1. Profile nào đang active?
2. spring.liquibase.enabled có bật không?
3. spring.liquibase.change-log sau khi resolve có đúng đường dẫn không?
4. Master có trong classpath/file system không?
5. File include/includeAll và SQL file có được đóng gói không?
6. JDBC URL, database, schema và user của Liquibase có đúng không?
7. Tài khoản có quyền đọc/ghi DATABASECHANGELOG và DATABASECHANGELOGLOCK không?
8. Changelog có hợp lệ và changeset có được chọn theo context/label không?
9. Có checksum mismatch hoặc precondition thất bại không?
10. Có job khác giữ khóa changelog hoặc DBMS đang chờ khóa không?

Đọc log để xác định lỗi ở giai đoạn cấu hình, tìm resource, kết nối, lấy lock, validate hay thực thi changeset. Không chỉ tăng startup timeout khi chưa biết nguyên nhân.

## 20. Kiểm thử integration với database thật

Một test khởi động Spring Boot có thể kiểm tra Liquibase chạy trên database test. Nên dùng cùng loại DBMS với production nếu ứng dụng phụ thuộc SQL hoặc tính năng riêng.

Ví dụ Testcontainers PostgreSQL:

~~~java
@SpringBootTest
@Testcontainers
class LiquibaseStartupTest {

    @Container
    static PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void configureDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
        registry.add(
            "spring.liquibase.change-log",
            () -> "classpath:/db/changelog/db.changelog-master.yaml"
        );
    }

    @Test
    void applicationStartsAfterLiquibaseMigration() {
        // Spring context khởi động thành công sau migration.
    }
}
~~~

Đây là ví dụ minh họa; cần dependency Testcontainers/JUnit tương ứng với phiên bản dự án. Một bài test chỉ xác nhận context khởi động chưa đủ. Nên kiểm tra bảng/cột/index/constraint, dữ liệu tham chiếu, DATABASECHANGELOG, quyền runtime, update lần hai và phương án rollback/forward fix.

### 20.1. Không chỉ dùng H2 khi production dùng DBMS khác

H2 tiện cho test nhanh nhưng không chứng minh PostgreSQL, MySQL, SQL Server hoặc Oracle tương thích. Khác biệt về kiểu dữ liệu, function, transaction DDL, lock và SQL đặc thù có thể chỉ xuất hiện trên DBMS thật.

Có kiểm thử migration cho từng DBMS/version trong ma trận hỗ trợ sản phẩm.

## 21. Kiểm tra artifact container

Một cấu hình classpath chạy trong IDE nhưng lỗi trong container có thể do:

- Resource không được đóng gói.
- Changelog nằm ở module khác nhưng dependency không chứa resource.
- SQL file tham chiếu không được copy.
- Chữ hoa/thường của tên file khác nhau; filesystem Linux phân biệt chữ hoa/thường.
- Đường dẫn include tương đối được tính khác kỳ vọng.
- Resource filtering làm thay đổi placeholder.
- Volume mount che khuất thư mục resource trong container.

Kiểm tra nội dung JAR bên trong image hoặc chạy bước xác minh artifact trước deploy. Không dựa vào việc file tồn tại trên máy phát triển.

Nếu dùng file system bên ngoài, ghi rõ volume mount và version migration bundle. Không mount thư mục có thể bị chỉnh sửa tùy ý sau khi artifact được phê duyệt.

## 22. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy changelog | Sai classpath hoặc tên file | Kiểm tra resources và change-log |
| IDE chạy được nhưng JAR lỗi | File không đóng gói hoặc filtering thay đổi | Kiểm tra JAR/container |
| Master tìm thấy nhưng include lỗi | Path hoặc relativeToChangelogFile sai | Xác minh đường dẫn từ file chứa include |
| Changeset chạy sai thứ tự | includeAll/naming không rõ | Dùng tên có thứ tự hoặc include tường minh |
| SQL file không tìm thấy | File không nằm trong artifact | Kiểm tra sqlFile path và packaging |
| Migration chạy nhầm database | Liquibase URL khác datasource hoặc profile sai | Xác minh database identity cả hai kết nối |
| App lỗi quyền lúc khởi động | Runtime user được dùng cho DDL nhưng thiếu quyền | Tách migration user hoặc cấp quyền đúng |
| App thiếu bảng sau deploy | Liquibase bị disable hoặc chạy trên DB khác | Kiểm tra enabled, URL và thứ tự deploy |
| File được nạp hai lần | include và includeAll chồng lặp | Chọn một cách nạp cho mỗi file |
| Changeset không chạy | Context/label không khớp | Kiểm tra contexts/labels và status |
| Checksum mismatch sau build | Filtering hoặc changeset lịch sử bị sửa | So sánh source, artifact và Git |
| Nhiều replica cùng migrate | Thiếu chủ sở hữu migration rõ ràng | Dùng job riêng hoặc điều phối startup |
| Secret xuất hiện trong log | Credential nằm trong changelog/command | Dùng secret store và masking |

Không sửa DATABASECHANGELOG thủ công hoặc clear-checksums chỉ vì ứng dụng không tìm thấy changelog. Trước tiên xác định lỗi ở resource, cấu hình, kết nối hay lịch sử.

## 23. Checklist trước khi phát hành

- [ ] spring.liquibase.change-log trỏ đúng master changelog.
- [ ] Master và file con nằm trong resources hoặc file system được quản lý.
- [ ] Đường dẫn classpath không chứa tiền tố src/main/resources.
- [ ] include/includeAll có thứ tự, phạm vi rõ và không nạp trùng.
- [ ] SQL file tham chiếu đã được đóng gói.
- [ ] JAR/container thực tế chứa đầy đủ changelog.
- [ ] Resource filtering không thay đổi placeholder ngoài dự kiến.
- [ ] Profile, contexts, labels và parameters được xác định rõ.
- [ ] Liquibase và ứng dụng trỏ tới đúng database/cluster.
- [ ] Migration role tách khỏi runtime role khi cần.
- [ ] Không có secret trong changelog, artifact hoặc log.
- [ ] Không bật drop-first/clear-checksums tùy tiện ở production.
- [ ] Đã chạy validate, status và update-sql.
- [ ] Đã thử migration trên DBMS thực tế và dữ liệu đại diện.
- [ ] Có một chủ sở hữu migration rõ ràng: Spring Boot startup hoặc job CI/CD.
- [ ] Có hậu kiểm schema, DATABASECHANGELOG và chức năng ứng dụng.

## 24. Kết luận

**spring.liquibase.change-log** là điểm cấu hình để Spring Boot tìm master changelog. Cấu trúc tài nguyên tốt bắt đầu từ một vị trí ổn định trong resources, một master rõ ràng, các file con được nạp có kiểm soát bằng include/includeAll và SQL file được đóng gói cùng artifact.

Cấu hình cần phân biệt classpath với file system, datasource ứng dụng với kết nối migration, default schema với schema lưu metadata, và profile với context/label. Dùng cùng changelog đã review qua các môi trường giúp giữ lịch sử nhất quán; URL, tài khoản và secret được cấp riêng theo môi trường.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, quy trình đáng tin cậy còn phải kiểm tra SQL, precondition, checksum, DATABASECHANGELOG, quyền migration, khả năng đóng gói JAR/container và kết quả trên DBMS thật. Khi đường dẫn, cấu hình và chủ sở hữu migration được xác định rõ, việc triển khai schema trở nên có thể tái lập và truy vết qua dev, test, staging và production.

