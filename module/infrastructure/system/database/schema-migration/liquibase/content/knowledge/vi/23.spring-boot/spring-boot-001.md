# Thêm Liquibase vào ứng dụng Spring Boot

Trong chương **Spring Boot** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, tích hợp Liquibase giúp ứng dụng quản lý thay đổi schema và dữ liệu theo phiên bản ngay trong vòng đời phát hành. Khi có dependency và cấu hình phù hợp, Spring Boot tự khởi tạo Liquibase, đọc changelog, đối chiếu changeset với lịch sử trong database, thực thi những thay đổi đang chờ và ghi nhận kết quả. Nhờ vậy, nhóm có thể kiểm soát schema cùng mã nguồn, kiểm thử migration và phối hợp nhiều môi trường.

Phạm vi học tập của **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài học đi từ dependency, datasource, cấu hình application đến vận hành production, kiểm thử và xử lý sự cố.

Định hướng đầy đủ của module: Nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

**Mục tiêu:** sau khi hoàn thành, người học có thể thêm Liquibase vào ứng dụng Spring Boot, cấu hình changelog và kết nối đúng database, tạo migration đầu tiên, kiểm tra lịch sử, tích hợp JPA, viết test trên database thật và lựa chọn thời điểm chạy migration phù hợp với quy trình triển khai.

## 1. Liquibase tham gia vào vòng đời Spring Boot như thế nào?

Khi ứng dụng Spring Boot khởi động, framework xây dựng ApplicationContext, cấu hình datasource và các bean hạ tầng. Nếu Liquibase có trên classpath và được bật, Spring Boot auto-configuration tạo Liquibase bean sử dụng changelog đã cấu hình. Liquibase kết nối database, kiểm tra bảng lịch sử và khóa, xác định changeset cần xử lý rồi thực thi migration.

Luồng khái niệm:

~~~text
Spring Boot khởi động
        |
Đọc cấu hình và profile
        |
Tạo DataSource / kết nối migration
        |
Liquibase auto-configuration
        |
Đọc master changelog
        |
Đọc DATABASECHANGELOG và DATABASECHANGELOGLOCK
        |
Kiểm tra changeset, checksum, context/label, precondition
        |
Thực thi changeset đang chờ
        |
Ghi lịch sử triển khai
        |
Khởi tạo các thành phần ứng dụng phụ thuộc database
        |
Ứng dụng sẵn sàng phục vụ
~~~

Sơ đồ mô tả thứ tự phụ thuộc ở mức kiến trúc. Chi tiết bean lifecycle có thể khác theo phiên bản Spring Boot và cách ứng dụng tùy biến cấu hình.

Điều cần nhớ:

- Liquibase chạy trong quá trình khởi động nếu được bật và tích hợp tự động.
- Lỗi kết nối, changelog hoặc migration có thể làm quá trình khởi động thất bại.
- Spring Boot không tự tạo nội dung changelog từ entity JPA.
- Liquibase quản lý thay đổi theo changeset và lịch sử, không tự đồng bộ mọi khác biệt thủ công của schema.
- Việc migration chạy xong không chứng minh tất cả chức năng ứng dụng đã tương thích với schema mới; cần test ứng dụng riêng.

## 2. Thêm dependency vào dự án

Ứng dụng cần thư viện Liquibase và JDBC driver tương ứng với database. Nếu dùng JPA, dự án thường đã có Spring Data JPA; nếu dùng JDBC trực tiếp, có thể dùng starter JDBC.

Ví dụ Maven với PostgreSQL và Spring Data JPA:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.liquibase</groupId>
        <artifactId>liquibase-core</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Các dependency trên là ví dụ. Với MySQL, SQL Server, Oracle hoặc DBMS khác, thay JDBC driver bằng driver tương ứng và xác nhận phiên bản được hỗ trợ. Nếu dự án đã dùng Spring Boot dependency management/BOM, thường không cần tự đặt version cho từng thư viện được BOM quản lý.

Một số nguyên tắc:

- Chỉ có một dependency Liquibase phù hợp với phiên bản Spring Boot và Java đang dùng.
- Tránh khai báo đồng thời nhiều phiên bản liquibase-core qua dependency bắc cầu.
- Pin hoặc quản lý phiên bản driver và Liquibase trong quy trình build.
- Nếu dùng change type hoặc tính năng cần extension, thêm extension tương ứng và kiểm thử với đúng phiên bản.
- Không đưa JDBC driver của môi trường production vào test bằng cách dựa vào driver H2 tương thích giả lập.

Sau khi dependency được đưa vào classpath, Spring Boot có thể tự cấu hình Liquibase. Không cần viết một bean gọi Liquibase thủ công trong trường hợp tích hợp mặc định.

## 3. Tạo cấu trúc changelog

Một cấu trúc dễ quản lý:

~~~text
src/
  main/
    resources/
      db/
        changelog/
          db.changelog-master.yaml
          changes/
            001-create-customer.yaml
            002-add-customer-status.yaml
            003-create-customer-index.yaml
~~~

Tệp master là điểm vào duy nhất mà ứng dụng tham chiếu. Các tệp con được include theo thứ tự:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/changes/001-create-customer.yaml
  - include:
      file: db/changelog/changes/002-add-customer-status.yaml
  - include:
      file: db/changelog/changes/003-create-customer-index.yaml
~~~

Đường dẫn include được phân giải theo cấu hình và vị trí changelog. Với dự án có cấu trúc nhiều thư mục, có thể dùng relativeToChangelogFile để đường dẫn tương đối theo tệp chứa include. Cần giữ đường dẫn ổn định sau khi changeset đã triển khai vì FILENAME có thể tham gia định danh changeset trong DATABASECHANGELOG.

Ví dụ tệp tạo bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "team-db"
      comment: "Tạo bảng khách hàng"
      changes:
        - createTable:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_customer
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            schemaName: app
            tableName: customer
~~~

Ví dụ giả định schema app đã tồn tại và kiểu TIMESTAMP phù hợp với DBMS mục tiêu. Nếu cần tạo schema, sequence hoặc default đặc thù, hãy mô tả rõ bằng changeset riêng hoặc SQL được giới hạn DBMS.

Mỗi changeset cần có:
- ID ổn định, duy nhất trong phạm vi định danh dự án.
- Author theo quy ước nhóm.
- Change mô tả một bước thay đổi có thể review.
- Precondition khi có giả định về trạng thái database.
- Rollback phù hợp nếu thao tác có thể hoàn tác.
- Comment hoặc tài liệu ngắn giúp người review hiểu mục đích.

Sau khi changeset đã chạy ở môi trường dùng chung, coi nội dung lịch sử là bất biến. Thay đổi tiếp theo được mô tả bằng changeset mới, không sửa migration cũ để thể hiện trạng thái mới.

## 4. Cấu hình Spring Boot để bật Liquibase

Spring Boot hỗ trợ các thuộc tính cấu hình dưới tiền tố spring.liquibase. Ví dụ application.yaml:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

Trong ví dụ:
- enabled bật hoặc tắt tích hợp Liquibase.
- change-log chỉ định changelog gốc trên classpath.
- datasource cung cấp kết nối mặc định để Liquibase sử dụng nếu không cấu hình datasource riêng cho Liquibase.
- DB_URL, DB_USERNAME và DB_PASSWORD được cấp từ môi trường triển khai hoặc secret manager.

Khi liquibase-core có trên classpath và datasource được cấu hình, Spring Boot thường tự chạy Liquibase trong quá trình khởi động. Nếu muốn dùng đường dẫn mặc định của Spring Boot, hãy kiểm tra default changelog path theo phiên bản framework đang dùng; khai báo tường minh thường giúp người đọc biết chính xác tệp nào là entry point.

Không commit password, token hoặc JDBC URL chứa credentials vào repository. Không in biến môi trường nhạy cảm ra log pipeline.

## 5. Phân biệt datasource ứng dụng và datasource Liquibase

Mặc định, Liquibase có thể sử dụng datasource chính của ứng dụng. Điều này đơn giản với hệ thống nhỏ, nhưng tài khoản runtime và tài khoản migration thường có quyền khác nhau:

- Ứng dụng thường chỉ cần SELECT/INSERT/UPDATE/DELETE trên bảng nghiệp vụ.
- Liquibase cần quyền DDL/DML phù hợp để tạo bảng, thêm cột, constraint, index và ghi lịch sử.
- Tài khoản migration thường có quyền cao hơn, vì vậy cần giới hạn thời điểm và nơi sử dụng.

Spring Boot cho phép cấu hình kết nối riêng cho Liquibase bằng các thuộc tính như spring.liquibase.url, spring.liquibase.user, spring.liquibase.password và spring.liquibase.driver-class-name.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: ${APP_DB_URL}
    username: ${APP_DB_USERNAME}
    password: ${APP_DB_PASSWORD}

  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    url: ${MIGRATION_DB_URL}
    user: ${MIGRATION_DB_USERNAME}
    password: ${MIGRATION_DB_PASSWORD}
~~~

Ở đây, ứng dụng kết nối bằng APP_DB_USERNAME, còn Liquibase kết nối bằng MIGRATION_DB_USERNAME. Hai URL có thể trỏ cùng database nhưng dùng principal khác nhau; cũng có thể tách endpoint theo kiến trúc vận hành.

Lưu ý:
- Tài khoản migration phải được cấp quyền trên đúng database/schema và các bảng lịch sử Liquibase.
- Tài khoản runtime không nên nhận quyền DDL nếu không cần thiết.
- Nếu migration datasource trỏ nhầm database, Liquibase có thể cập nhật một nơi còn ứng dụng đọc/ghi nơi khác.
- Phải kiểm tra cả cấu hình kết nối của datasource chính và Liquibase trong từng profile.
- Datasource riêng không tự tạo quy trình phê duyệt; quyền cao hơn vẫn cần được bảo vệ bởi secret manager và pipeline.

## 6. Các thuộc tính Spring Liquibase thường dùng

Những thuộc tính phổ biến:

| Thuộc tính | Mục đích |
|---|---|
| spring.liquibase.enabled | Bật/tắt tích hợp |
| spring.liquibase.change-log | Changelog gốc |
| spring.liquibase.url | JDBC URL riêng cho Liquibase |
| spring.liquibase.user | User riêng cho Liquibase |
| spring.liquibase.password | Password riêng cho Liquibase |
| spring.liquibase.driver-class-name | JDBC driver riêng |
| spring.liquibase.default-schema | Schema mặc định cho các change không chỉ rõ schema |
| spring.liquibase.liquibase-schema | Schema lưu bảng quản lý của Liquibase |
| spring.liquibase.database-change-log-table | Tên bảng lịch sử |
| spring.liquibase.database-change-log-lock-table | Tên bảng khóa |
| spring.liquibase.contexts | Context được áp dụng |
| spring.liquibase.label-filter | Bộ lọc label |
| spring.liquibase.parameters | Các giá trị thay thế parameter trong changelog |

Tên property và khả năng hỗ trợ cần đối chiếu với phiên bản Spring Boot cụ thể. Không sao chép toàn bộ thuộc tính vào mọi ứng dụng nếu không có nhu cầu.

### default-schema và liquibase-schema khác nhau

- **default-schema** ảnh hưởng schema mặc định cho các change không chỉ rõ schema.
- **liquibase-schema** chỉ định nơi lưu bảng quản lý như DATABASECHANGELOG và DATABASECHANGELOGLOCK.

Ví dụ:

~~~yaml
spring:
  liquibase:
    default-schema: app
    liquibase-schema: migration_meta
~~~

Cấu hình này giả định hai schema đã tồn tại và tài khoản migration có quyền cần thiết. Nếu không chỉ rõ schema cho bảng nghiệp vụ, change có thể được tạo trong app; bảng lịch sử Liquibase nằm ở migration_meta. Việc tách schema metadata giúp phân quyền và quan sát rõ hơn, nhưng phải bảo đảm truy vấn kiểm tra lịch sử sử dụng đúng schema.

## 7. Quản lý profile và môi trường

Spring Boot hỗ trợ externalized configuration và profile để nạp cấu hình khác nhau theo môi trường. Ví dụ:

~~~yaml
# application.yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

~~~yaml
# application-dev.yaml
spring:
  liquibase:
    contexts: dev
~~~

~~~yaml
# application-prod.yaml
spring:
  liquibase:
    contexts: prod
~~~

Đây là ví dụ khi changelog có changeset gắn context phù hợp. Không gắn context vào changeset chỉ để tránh chạy một thay đổi nguy hiểm trong production; phải kiểm tra filter và chính sách lựa chọn changeset theo đúng phiên bản Liquibase.

Một số nguyên tắc:
- Giữ cùng master changelog giữa các môi trường.
- Chỉ thay đổi kết nối, secret, schema parameters và filter có chủ đích.
- Không sửa changeset cũ theo profile.
- Không để dữ liệu demo được chọn nhầm ở production.
- Không dựa vào tên profile để suy ra database URL; kiểm tra giá trị cấu hình hiệu lực.
- Dùng cùng artifact/changelog đã kiểm thử để promote qua staging và production.

Nếu production không cần chạy một số seed demo, tốt hơn là tách rõ dữ liệu thử nghiệm khỏi changelog nghiệp vụ hoặc đặt filter được review và kiểm tra trong pipeline.

## 8. Tạo changeset đầu tiên và kiểm chứng

Sau khi cấu hình dependency, datasource và master changelog, chạy ứng dụng trên database phát triển có thể khôi phục. Spring Boot sẽ khởi tạo Liquibase theo cấu hình.

Kết quả mong đợi:
1. Kết nối tới đúng database.
2. Liquibase tạo bảng lịch sử/khóa nếu chưa tồn tại và được cấp quyền.
3. Đọc master changelog cùng các tệp include.
4. Xác định changeset chưa chạy.
5. Thực thi DDL/DML.
6. Ghi lịch sử vào DATABASECHANGELOG.
7. Hoàn tất khởi tạo các thành phần phụ thuộc và ứng dụng tiếp tục startup.

Có thể kiểm tra trực tiếp trong database:

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

Nếu bảng lịch sử được lưu trong schema riêng, dùng tên schema đầy đủ hoặc search path phù hợp. Không giả định bảng nằm trong public.

Kiểm tra cấu trúc bảng:

~~~sql
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'customer'
ORDER BY ordinal_position;
~~~

Đây là truy vấn theo information_schema; metadata chi tiết và quyền đọc có thể khác theo DBMS. Với engine khác, dùng catalog tương ứng.

**Chỉ thấy log “Liquibase update successful” chưa đủ.** Cần xác minh changeset, object vật lý và dữ liệu thực tế.

## 9. Không để Hibernate và Liquibase cùng tự thay đổi schema

Nếu ứng dụng dùng Spring Data JPA/Hibernate, cấu hình production thường nên để Liquibase quản lý DDL và Hibernate kiểm tra mapping:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Các chế độ Hibernate thường gặp:
- validate: kiểm tra mapping với schema hiện có.
- none: không tự quản lý schema.
- update: cố điều chỉnh schema theo entity.
- create/create-drop: tạo hoặc tạo rồi xóa schema theo vòng đời.

Dùng Liquibase cùng ddl-auto: update trong production tạo ra hai nguồn thay đổi schema. Hibernate có thể thay đổi cấu trúc mà không tạo changeset, checksum hoặc lịch sử Liquibase tương ứng. Điều này làm môi trường khó tái lập và khó review.

Có thể dùng create-drop trong test cô lập nếu đó là lựa chọn có chủ đích, nhưng test migration cần xác minh chính Liquibase tạo schema theo changelog. Không dùng Hibernate auto-DDL để “bù” cho một changelog thiếu bảng/cột.

Nếu Hibernate validate thất bại sau khi Liquibase chạy:
1. Kiểm tra đúng database/schema.
2. Đọc DATABASECHANGELOG.
3. Kiểm tra kiểu dữ liệu, nullability, tên cột và sequence.
4. So sánh entity mapping với changelog.
5. Tạo changeset mới nếu schema cần thay đổi.
6. Không sửa changeset đã chạy chỉ để làm validate xanh.

## 10. Chọn cách chạy Liquibase: startup hay migration job riêng

Có hai mô hình vận hành chính.

### Mô hình A: chạy khi Spring Boot khởi động

Ưu điểm:
- Ít thành phần triển khai.
- Changelog đi cùng artifact ứng dụng.
- Môi trường phát triển dễ thiết lập.
- Ứng dụng không tiếp tục startup khi migration bắt buộc thất bại.

Nhược điểm:
- Thời gian startup phụ thuộc database và migration.
- Nhiều instance có thể cùng cố khởi chạy Liquibase.
- Tài khoản ứng dụng hoặc runtime phải có quyền migration nếu dùng datasource chính.
- Khó tạo cổng phê duyệt riêng cho migration nguy cơ cao.
- Nếu migration dài, readiness và autoscaling có thể bị ảnh hưởng.

Phù hợp với hệ thống nhỏ hoặc migration ngắn, có quy trình startup được kiểm soát.

### Mô hình B: migration job riêng trong CI/CD

Pipeline chạy Liquibase bằng một job chuyên trách trước khi triển khai ứng dụng mới. Ứng dụng runtime chỉ kết nối database sau khi schema đã ở trạng thái tương thích.

Ưu điểm:
- Tách quyền migration khỏi quyền runtime.
- Có bước review SQL và phê duyệt.
- Dễ kiểm soát thứ tự release.
- Dễ lưu log, artifact và kết quả migration.
- Tránh mỗi replica ứng dụng đều tự khởi chạy migration.

Nhược điểm:
- Cần quản lý thêm job, cấu hình và credentials.
- Phải bảo đảm job migration dùng đúng artifact/changelog với ứng dụng.
- Nếu job thành công nhưng ứng dụng deploy thất bại, database có thể đi trước code; migration cần tương thích ngược.

Với production nhiều instance hoặc thay đổi có rủi ro cao, migration job riêng thường dễ kiểm soát hơn. Có thể vẫn giữ Liquibase trên classpath nhưng tắt auto-run ở ứng dụng runtime và chạy một tiến trình migration được ủy quyền; phải bảo đảm không có đường chạy thứ hai vô tình thực thi cùng changelog.

## 11. Nhiều instance Spring Boot và DATABASECHANGELOGLOCK

Trong môi trường có nhiều replica, ví dụ:

~~~text
Application instance A ──┐
Application instance B ──┼──> Database
Application instance C ──┘
~~~

Nếu mỗi instance cùng bật Liquibase startup, nhiều tiến trình có thể đồng thời thử migration. Liquibase dùng DATABASECHANGELOGLOCK để điều phối các tiến trình Liquibase trên cùng database. Cơ chế này giúp tránh việc hai Liquibase runner đồng thời thực thi cùng tập migration theo cách không được điều phối.

Tuy nhiên, lock không:
- Ngăn DBA hoặc công cụ khác chạy DDL ngoài Liquibase.
- Khóa toàn bộ truy vấn ứng dụng.
- Bảo đảm DDL không khóa bảng.
- Bảo đảm ứng dụng phiên bản cũ tương thích với schema mới.
- Thay thế kế hoạch migration job, readiness hoặc rolling deployment.

Khi nhiều instance cùng khởi động:
- Có thể có instance phải chờ lock.
- Một instance có thể gặp timeout hoặc thất bại khi chờ.
- Migration dài có thể kéo dài thời gian startup.
- Nếu job bị dừng bất thường, phải điều tra tiến trình và lock state trước khi giải phóng khóa.

Không xóa hoặc giải phóng DATABASECHANGELOGLOCK bằng SQL tùy tiện khi chưa xác minh không còn migration đang chạy. Nếu có job migration riêng, các replica ứng dụng nên khởi động sau khi job hoàn tất.

## 12. Tích hợp với JPA repository và entity

Giả sử changelog tạo bảng customer:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010-create-customer"
      author: "team-db"
      changes:
        - createTable:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
                  constraints:
                    nullable: false
~~~

Entity JPA có thể ánh xạ:

~~~java
@Entity
@Table(name = "customer", schema = "app")
public class Customer {
    @Id
    private Long id;

    @Column(name = "email", nullable = false, length = 320)
    private String email;
}
~~~

Các điểm cần đồng bộ:
- Tên schema/table/column.
- Kiểu dữ liệu và độ dài.
- Nullability.
- Primary key và generation strategy.
- Sequence/identity nếu dùng ID tự sinh.
- Unique/FK/index có thể được ORM sử dụng hoặc ứng dụng phụ thuộc.

JPA annotation không phải migration. Thay đổi length từ 320 lên 500 trong entity không tự tạo changeset. Phải cập nhật changelog bằng changeset mới, kiểm tra dữ liệu hiện tại và chạy migration trước khi phát hành code phụ thuộc vào cột mới.

Nếu dùng @GeneratedValue, strategy phải tương thích với cách Liquibase tạo identity/sequence trên từng DBMS. Kiểm thử generated key qua JDBC/ORM trên engine thật.

## 13. Precondition để bảo vệ migration khi Spring Boot startup

Precondition mô tả điều kiện database phải đạt trước khi changeset chạy. Ví dụ thêm cột phone khi bảng customer tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-011-add-customer-phone"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: customer
        - not:
            - columnExists:
                schemaName: app
                tableName: customer
                columnName: phone
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: VARCHAR(30)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: customer
            columnName: phone
~~~

Nếu bảng thiếu hoặc cột đã tồn tại, precondition có thể dừng startup theo chính sách. Điều này tốt hơn để ứng dụng tiếp tục với schema không rõ trạng thái.

Tuy nhiên:
- columnExists chỉ kiểm tra tồn tại, không chứng minh kiểu dữ liệu hoặc constraint đúng.
- onFail: MARK_RAN có thể ghi nhận changeset mà không chạy change; không dùng để che schema drift.
- Precondition được kiểm tra tại thời điểm chạy, không thay thế constraint database.
- Nếu precondition dùng SQL riêng, phải kiểm tra câu SQL trên mọi DBMS mục tiêu.
- Precondition cấp changelog và cấp changeset có phạm vi hành vi khác nhau; chọn đúng nơi khai báo.

Trong startup, HALT thường khiến ứng dụng không khởi động tiếp. Hãy xem đây là tín hiệu cần điều tra, không tìm cách tự động bỏ qua mọi lỗi để giữ app chạy.

## 14. Quản lý context, label và dữ liệu theo môi trường

Changelog có thể chứa seed data hoặc changeset chỉ chạy trong một số phạm vi. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-020-seed-demo-customer"
      author: "team-db"
      contextFilter: dev
      changes:
        - insert:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 9001
              - column:
                  name: email
                  value: demo@example.invalid
~~~

Spring Boot có thể truyền context qua spring.liquibase.contexts và label filter qua thuộc tính tương ứng được phiên bản hỗ trợ. Cần kiểm tra cú pháp và hành vi filter của phiên bản Liquibase đang dùng.

Không coi contextFilter: dev là lớp bảo vệ duy nhất để ngăn seed demo vào production. Cần:
- Xác nhận profile thực tế và cấu hình đã được nạp.
- Kiểm tra generated SQL hoặc status với đúng filter.
- Tách dữ liệu demo khỏi migration production nếu có thể.
- Không dùng dữ liệu giả trong changelog dùng chung nếu chưa kiểm soát được phạm vi.
- Không đặt password hoặc dữ liệu nhạy cảm trong seed.

Dữ liệu tham chiếu chuẩn như mã trạng thái có thể được quản lý bằng changeset; dữ liệu giao dịch và dữ liệu riêng của khách hàng không nên được đóng gói thành seed migration thông thường.

## 15. Truyền changelog parameters qua cấu hình Spring Boot

Khi cùng changelog được triển khai trên nhiều schema hoặc cần một giá trị không nhạy cảm theo môi trường, có thể dùng parameter substitution.

Ví dụ changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-030-create-audit-table"
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

Cấu hình Spring Boot:

~~~yaml
spring:
  liquibase:
    parameters:
      appSchema: ${APP_SCHEMA}
~~~

Parameter phải được truyền nhất quán trong update và rollback. Nếu rollback sử dụng schema khác, Liquibase có thể tìm nhầm object.

Không dùng parameter substitution để đưa secret vào nội dung changelog hoặc SQL được lưu trong log. Tên schema, mã môi trường và một số giá trị cấu hình có thể là parameter; credentials phải được cấp qua cơ chế kết nối an toàn.

Không xây dựng tên bảng/cột tùy ý từ input người dùng. Changelog là mã triển khai có quyền DDL; parameter phải được kiểm soát và validate.

## 16. Kiểm thử Liquibase bằng Spring Boot Test

Một kiểm thử tích hợp nên khởi động database thật hoặc container tương ứng, sau đó để Spring Boot chạy Liquibase. Với Testcontainers, ví dụ PostgreSQL:

~~~java
@Testcontainers
@SpringBootTest
class LiquibaseMigrationIT {

    @Container
    static PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }

    @Test
    void migrationCreatesCustomerTable() {
        // Truy vấn metadata hoặc dùng repository để xác minh schema.
    }
}
~~~

Đây là mẫu minh họa; phiên bản image, Testcontainers, JUnit và Spring Boot phải được pin theo ma trận hỗ trợ của dự án.

Test cần xác minh:
1. ApplicationContext khởi động thành công.
2. Liquibase đọc đúng changelog.
3. DATABASECHANGELOG có changeset dự kiến.
4. Bảng/cột/constraint/index cần thiết tồn tại.
5. Dữ liệu tham chiếu có đúng code và giá trị.
6. Hibernate validate không báo mapping mismatch.
7. Repository/JDBC đọc và ghi được.
8. Migration chạy lại không nhân đôi dữ liệu hoặc tạo object.
9. Precondition fail trong fixture tương ứng sẽ dừng theo chính sách.
10. Rollback hoặc forward fix đã được kiểm tra riêng trên database có thể khôi phục.

Nếu dự án hỗ trợ nhiều DBMS, chạy integration test trên từng engine thật. H2 có thể dùng cho một số unit test nhanh nhưng không thay thế kiểm thử PostgreSQL, MySQL, SQL Server hoặc Oracle.

## 17. Kiểm thử nâng cấp từ schema cũ

Test từ database rỗng chỉ chứng minh fresh install. Ứng dụng production thường có dữ liệu và schema từ release trước.

Một upgrade test nên:
- Dựng schema bằng changelog của release cũ.
- Nạp dữ liệu đại diện và edge case.
- Chạy application hoặc migration job với changelog mới.
- Kiểm tra backfill và dữ liệu lịch sử.
- Xác minh FK, UNIQUE, NOT NULL và index mới.
- Khởi động code mới và chạy test repository/API.
- Kiểm tra rollback/forward fix trên bản sao.

Ví dụ thêm cột bắt buộc:
1. Thêm cột nullable.
2. Triển khai ứng dụng có thể đọc/ghi cả trạng thái cũ và mới.
3. Backfill dữ liệu theo lô.
4. Kiểm tra không còn NULL.
5. Thêm NOT NULL trong changeset riêng.
6. Sau khi không còn code cũ phụ thuộc, mới loại bỏ cột cũ nếu cần.

Không thêm cột NOT NULL vào bảng có dữ liệu lớn mà không xác định default/backfill và tác động lock của DBMS. Một migration chạy nhanh trên database test rỗng có thể gây lock lâu trong production.

## 18. Chạy Liquibase bằng CI/CD thay vì startup

Với production, có thể tách migration thành job riêng:

~~~text
Build application + changelog artifact
             |
Validate changelog
             |
Connect to target database
             |
Status + update-sql
             |
Review / approval
             |
Liquibase update job
             |
Verify DATABASECHANGELOG + schema/data
             |
Deploy application instances
             |
Smoke test and observe
~~~

Một job CLI có thể thực hiện:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql

# Sau review và phê duyệt trên đúng database:
liquibase update
liquibase history
~~~

Pipeline phải đảm bảo:
- Chạy cùng commit/artifact changelog với bản ứng dụng sắp triển khai.
- JDBC URL và schema là đúng môi trường.
- Tài khoản migration lấy từ secret store.
- Chỉ một migration job có trách nhiệm cập nhật database tại một thời điểm.
- SQL được review với đúng DBMS và filter.
- Log và kết quả được lưu nhưng không chứa secret.
- Ứng dụng mới chỉ được mở traffic khi schema đã đạt điều kiện tương thích.
- Nếu migration thành công nhưng deploy app thất bại, schema vẫn phải tương thích với phiên bản ứng dụng đang chạy.

Nếu ứng dụng runtime vẫn bật Liquibase auto-run trong khi pipeline cũng chạy Liquibase, cần xác định một cơ chế ownership duy nhất. Nếu không, hai đường triển khai có thể cạnh tranh lock, sử dụng credentials khác nhau hoặc chạy với artifact không giống nhau.

## 19. Rolling deployment và tương thích phiên bản ứng dụng

Liquibase có thể triển khai schema trước hoặc trong lúc ứng dụng khởi động, nhưng không tự đảm bảo phiên bản cũ và mới cùng tương thích.

Ví dụ đổi tên cột:
- Ứng dụng cũ đọc customer.full_name.
- Migration đổi thành customer.display_name.
- Ứng dụng mới chỉ đọc customer.display_name.

Nếu migration chạy trước khi mọi instance cũ dừng, request trên instance cũ có thể lỗi.

Chiến lược expand–migrate–contract:
1. Thêm cột mới mà vẫn giữ cột cũ.
2. Triển khai code đọc/ghi tương thích với cả hai.
3. Backfill dữ liệu từ cột cũ sang cột mới.
4. Chuyển toàn bộ reader/writer.
5. Xác nhận không còn phiên bản ứng dụng phụ thuộc cột cũ.
6. Xóa cột cũ bằng changeset riêng trong release sau.

Các thay đổi phá tương thích nên được chia thành nhiều release khi cần. Không sửa changeset cũ để gộp toàn bộ quá trình thành một DDL tức thời.

## 20. Rollback khi Liquibase chạy cùng ứng dụng

Rollback là một quyết định triển khai, không phải nút tự động khôi phục mọi thứ khi Spring Boot không khởi động.

Có ba tình huống:

**Migration thất bại trước khi hoàn thành:** tùy DBMS, loại DDL và transaction, có thể không có thay đổi nào được áp dụng hoặc có một phần thay đổi đã tồn tại. Cần đọc log, DATABASECHANGELOG và schema thực tế trước khi retry.

**Migration thành công nhưng ứng dụng mới lỗi:** database có thể đã tiến lên. Rollback ứng dụng về bản cũ chỉ an toàn nếu schema mới tương thích ngược. Nếu migration đã xóa/đổi cột, app cũ có thể không chạy.

**Cần rollback schema:** phải có rollback changeset phù hợp, kiểm tra dữ liệu đã phát sinh và dependency. Drop column có thể xóa dữ liệu; rollback thay đổi dữ liệu có thể không đảo ngược nếu không lưu giá trị nguồn.

Với migration không thể đảo ngược, forward fix hoặc restore có thể là phương án phù hợp hơn. Không tự động chạy rollback khi startup fail mà chưa xác định trạng thái database và traffic.

## 21. Bảo mật và phân quyền

Liquibase có thể thực thi DDL và DML, vì vậy quyền truy cập cần được quản lý:

- Secret database chỉ được cấp cho đúng ứng dụng/job.
- Runtime user không cần quyền ALTER/DROP nếu migration chạy riêng.
- Migration user chỉ được cấp quyền trên database/schema thuộc phạm vi.
- Không ghi password vào changelog, Git, log hoặc thông báo lỗi.
- Giới hạn quyền đọc metadata và quyền tạo object theo DBMS.
- Audit người/job thực thi migration và artifact changelog.
- Phân biệt môi trường test với production.
- Không cho người dùng cuối cung cấp parameter trực tiếp vào changelog.

Nếu sử dụng datasource riêng cho Liquibase, phải kiểm tra cả quyền của migration user và runtime user. Việc tách credentials giúp giảm quyền ứng dụng, nhưng không làm giảm trách nhiệm bảo vệ secret migration.

## 22. Chẩn đoán lỗi thường gặp khi tích hợp Spring Boot

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| ApplicationContext không khởi động | Liquibase migration thất bại | Đọc root cause trong log trước lỗi bean |
| Không tìm thấy changelog | Sai classpath hoặc change-log path | Kiểm tra file trong resources và cấu hình hiệu lực |
| Connection refused | URL, host, port hoặc database chưa sẵn sàng | Kiểm tra datasource và readiness của DB |
| Permission denied | Runtime/migration user thiếu quyền | Xác minh grants trên schema và bảng history |
| Checksum validation failed | Changeset đã chạy bị sửa | Đối chiếu ID/AUTHOR/FILENAME, Git revision và MD5SUM |
| Table already exists | DDL ngoài Liquibase hoặc định danh thay đổi | Kiểm tra schema thực tế và DATABASECHANGELOG |
| Có bảng nhưng JPA validate fail | Mapping/type/schema/sequence không khớp | So sánh entity và metadata |
| Liquibase chạy sai database | Cấu hình datasource hoặc profile sai | Xác minh URL hiệu lực của cả datasource và Liquibase |
| Ứng dụng khởi động chậm | Migration dài, lock hoặc DB chậm | Đo thời gian từng changeset và kiểm tra lock |
| Nhiều instance cùng chờ | Cạnh tranh DATABASECHANGELOGLOCK | Kiểm tra migration runner và chiến lược rollout |
| Seed demo vào production | Context/label/profile chọn sai | Kiểm tra filter thực tế và generated SQL |
| Startup thành công nhưng API lỗi | Schema mới chưa tương thích ứng dụng | Kiểm tra contract, query, data và version rollout |
| Rollback thất bại | Dữ liệu/dependency hoặc DDL không hỗ trợ rollback | Đối chiếu schema và dữ liệu trước khi retry |

Khi chẩn đoán, tách các lớp lỗi:
1. Dependency/autoconfiguration.
2. Cấu hình datasource/profile.
3. Parse changelog và include.
4. Changeset identity/checksum/precondition.
5. SQL/DBMS/permission/transaction.
6. Schema và dữ liệu.
7. Mapping ứng dụng và thứ tự rollout.

Không xử lý lỗi checksum bằng cách xóa hàng DATABASECHANGELOG hoặc clear-checksums tùy tiện. Không giải phóng lock khi chưa xác minh tiến trình migration đã dừng.

## 23. Bài thực hành: tích hợp Liquibase vào ứng dụng Spring Boot

**Bối cảnh:** ứng dụng quản lý khách hàng dùng Spring Boot, JPA và PostgreSQL. Yêu cầu tạo bảng customer, thêm cột status và index theo email.

### Phần A — Cấu hình

1. Thêm liquibase-core và PostgreSQL JDBC driver.
2. Tạo master changelog trong src/main/resources/db/changelog.
3. Cấu hình spring.liquibase.change-log.
4. Cấp JDBC URL, username và password từ môi trường.
5. Cấu hình Hibernate ddl-auto: validate.
6. Xác nhận Liquibase dùng đúng datasource và schema.

### Phần B — Viết migration

1. Tạo changeset tạo bảng customer với PK và email.
2. Tạo changeset thêm status nullable.
3. Tạo changeset tạo index trên email.
4. Khai báo ID, author, comment và rollback phù hợp.
5. Thêm precondition cho những giả định quan trọng.
6. Không sửa changeset sau khi đã triển khai.

### Phần C — Khởi động và xác minh

1. Khởi động database test.
2. Chạy ứng dụng Spring Boot.
3. Kiểm tra log Liquibase.
4. Đọc DATABASECHANGELOG.
5. Truy vấn metadata để xác minh bảng, cột và index.
6. Khởi động lại ứng dụng; xác minh changeset thông thường không chạy lại.
7. Chạy repository test và kiểm tra Hibernate validate.

### Phần D — Kiểm thử upgrade

1. Dựng database bằng phiên bản changelog trước.
2. Nạp dữ liệu customer đại diện.
3. Chạy ứng dụng với changelog mới.
4. Kiểm tra dữ liệu được giữ nguyên.
5. Xác minh cột status và index được tạo.
6. Chạy test API đọc/ghi.
7. Thử rollback trên database bản sao và ghi nhận dữ liệu bị ảnh hưởng.

### Phần E — Chuyển sang CI/CD

1. Tách migration job nếu production yêu cầu cổng phê duyệt.
2. Chạy validate, status và update-sql.
3. Review SQL với đúng DBMS.
4. Chạy update bằng tài khoản migration.
5. Kiểm tra history và schema.
6. Triển khai ứng dụng bằng cùng artifact đã kiểm thử.
7. Chạy smoke test và theo dõi log/metrics.

### Câu hỏi tự kiểm tra

- Chỉ thêm liquibase-core vào classpath có đủ để Spring Boot tự cấu hình không? **Trong cấu hình mặc định, cần thêm datasource và changelog hợp lệ; auto-configuration sẽ được kích hoạt khi điều kiện phù hợp.**
- Nếu spring.liquibase.enabled=false thì điều gì xảy ra? **Tích hợp Liquibase startup bị tắt; phải có một quy trình migration khác nếu ứng dụng cần schema mới.**
- Có nên để Hibernate ddl-auto:update cùng Liquibase trong production? **Không nên**, vì tạo hai nguồn quản lý schema và làm lịch sử không nhất quán.
- Vì sao cần datasource riêng cho Liquibase? **Để tách quyền DDL của migration khỏi quyền runtime khi kiến trúc yêu cầu.**
- DATABASECHANGELOGLOCK có thay thế migration job riêng không? **Không.** Nó điều phối Liquibase runner, không quản lý toàn bộ release.
- Vì sao cần upgrade test với dữ liệu cũ? **Vì migration có thể thất bại do NULL, dữ liệu trùng, FK hoặc chuyển đổi kiểu dù fresh install thành công.**
- Rollback ứng dụng có đồng nghĩa rollback database không? **Không.** Hai hành động cần được thiết kế và thực hiện riêng.
- Nếu đổi tên cột, tại sao cần expand–migrate–contract? **Để các phiên bản ứng dụng cũ/mới có thời gian tương thích trong rolling deployment.**

## 24. Checklist triển khai Liquibase trong Spring Boot

**Dependency và cấu hình**
- [ ] Đã thêm liquibase-core và JDBC driver phù hợp.
- [ ] Phiên bản Liquibase, Spring Boot, Java và driver được quản lý rõ.
- [ ] Master changelog tồn tại trên classpath.
- [ ] spring.liquibase.change-log trỏ đúng entry point.
- [ ] Datasource và profile trỏ đúng database/schema.
- [ ] Secret được cấp từ nguồn an toàn.
- [ ] default-schema và liquibase-schema được phân biệt đúng.
- [ ] Context, label và parameters được cấu hình có chủ đích.

**Changelog và lịch sử**
- [ ] Changeset có ID/AUTHOR/FILENAME ổn định.
- [ ] Có precondition khi cần kiểm tra giả định.
- [ ] Có rollback hoặc ghi rõ giới hạn không thể đảo ngược.
- [ ] Không sửa changeset đã chạy.
- [ ] DATABASECHANGELOG và DATABASECHANGELOGLOCK nằm đúng nơi.
- [ ] Đã kiểm tra status, update-sql và history.

**Ứng dụng và kiểm thử**
- [ ] Hibernate không tự update schema production.
- [ ] Entity mapping phù hợp với changelog.
- [ ] Có fresh install test trên DBMS được hỗ trợ.
- [ ] Có upgrade test với dữ liệu đại diện.
- [ ] Có test precondition, checksum và lỗi migration.
- [ ] Có test repository/API sau migration.
- [ ] Có test rollback hoặc forward fix trên bản sao.
- [ ] Đã kiểm tra thời gian startup, lock và readiness.

**Vận hành production**
- [ ] Đã chọn startup migration hay job riêng.
- [ ] Chỉ một quy trình được quyền thực thi migration cho database tại một thời điểm.
- [ ] Runtime user và migration user được phân quyền phù hợp.
- [ ] Có review SQL và phê duyệt cho thay đổi nguy cơ cao.
- [ ] Cùng artifact/changelog được promote qua các môi trường.
- [ ] Có kế hoạch tương thích rolling deployment.
- [ ] Có backup/restore hoặc forward fix khi rollback không khả thi.
- [ ] Đã kiểm tra DATABASECHANGELOG, schema, dữ liệu và smoke test sau triển khai.

**Kết luận:** tích hợp Liquibase vào Spring Boot giúp migration trở thành một phần có kiểm soát của vòng đời ứng dụng. Dependency kích hoạt auto-configuration, datasource xác định database đích, master changelog mô tả thay đổi, còn DATABASECHANGELOG lưu lịch sử để Liquibase biết changeset nào cần xử lý. Để vận hành an toàn, hãy giữ changeset đã phát hành bất biến, tách quyền migration khi cần, để Hibernate validate mapping, kiểm thử trên database thật và lựa chọn rõ giữa startup migration với CI/CD job riêng. Khi kết hợp precondition, checksum, rollback, test upgrade và chiến lược tương thích phiên bản, nhóm có thể triển khai schema và dữ liệu nhất quán qua nhiều môi trường.
