# Phối hợp Liquibase với Hibernate và thiết lập ddl-auto

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Spring Boot**, ứng dụng thường dùng Hibernate thông qua Spring Data JPA để ánh xạ entity sang bảng, cột và quan hệ. Đồng thời, Liquibase quản lý thay đổi schema bằng changelog và changeset. Nếu cả hai công cụ cùng tự ý tạo hoặc sửa schema, database có thể lệch khỏi lịch sử migration, khó kiểm soát khi triển khai nhiều môi trường và khó rollback.

Cách phối hợp rõ ràng là **Liquibase sở hữu việc thay đổi schema**, còn **Hibernate kiểm tra khả năng tương thích giữa mapping entity và schema hiện có**. Trong Spring Boot, cấu hình thường dùng **spring.jpa.hibernate.ddl-auto=validate** để Hibernate xác minh schema khi khởi động mà không tự tạo hoặc sửa bảng. Nếu không cần kiểm tra bằng Hibernate, có thể dùng **none**. Những chế độ như **update**, **create** hoặc **create-drop** có mục đích khác và cần được giới hạn cẩn thận.

Bài học này giải thích quan hệ giữa Liquibase, Hibernate và JPA; ý nghĩa từng giá trị ddl-auto; cấu hình Spring Boot; cách xử lý thứ tự khởi tạo; các khác biệt giữa entity mapping và DDL; cách kiểm thử migration; cùng quy trình triển khai và chẩn đoán lỗi. Mục tiêu của module là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai, có kiểm chứng, rollback và phối hợp nhiều môi trường. Cấu hình đúng giúp quy trình đó nhất quán với ORM.

## 1. Hai công cụ có hai trách nhiệm khác nhau

**Liquibase** quản lý lịch sử thay đổi database. Một changelog chứa changeset mô tả những bước như tạo bảng, thêm cột, tạo index, thêm constraint, chuyển đổi dữ liệu hoặc thay đổi default. Khi triển khai, Liquibase kiểm tra DATABASECHANGELOG, checksum và điều kiện chạy để quyết định changeset nào cần áp dụng.

**Hibernate** là ORM. Nó ánh xạ entity Java sang cấu trúc relational, tạo SQL cho truy vấn và thao tác dữ liệu. Hibernate cần biết bảng, cột, kiểu dữ liệu và quan hệ để thực hiện công việc. Hibernate cũng có khả năng kiểm tra hoặc sinh DDL từ mapping tùy cấu hình.

Nếu không phân định trách nhiệm, hai công cụ có thể cùng tác động schema:

~~~text
Spring Boot starts
       |
       +--> Liquibase reads changelog
       |        |
       |        +--> creates/alters schema
       |
       +--> Hibernate reads entity mapping
                |
                +--> ddl-auto may validate or alter schema
~~~

Khi **ddl-auto=update**, Hibernate có thể tự điều chỉnh schema dựa trên entity, trong khi Liquibase không ghi nhận những thay đổi đó trong lịch sử changeset. Kết quả là database có cột hoặc constraint mà changelog không mô tả; database ở development khác staging/production dù cùng commit; rollback Liquibase không biết phải đảo thay đổi do Hibernate tạo; và review không thấy rõ DDL nào sẽ chạy trước khi ứng dụng khởi động.

| Thành phần | Trách nhiệm |
|---|---|
| **Liquibase changelog** | Tạo, sửa, xóa schema; quản lý changeset, precondition, checksum và lịch sử |
| **Hibernate mapping** | Mô tả cách entity ánh xạ vào schema |
| **Hibernate ddl-auto=validate** | Kiểm tra một phần tương thích schema/entity khi khởi động |
| **Ứng dụng/JPA** | Đọc và ghi dữ liệu theo mapping |
| **CI/CD** | Kiểm thử changelog, triển khai theo thứ tự, xác minh schema và ứng dụng |

Hibernate validation không thay thế kiểm tra toàn diện của Liquibase hoặc DBMS. Nó chỉ xác minh những khía cạnh mapping mà Hibernate hỗ trợ trong phiên bản đang dùng.

## 2. ddl-auto là gì?

Trong Spring Boot, thuộc tính:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

điều khiển hành động schema generation của Hibernate khi ứng dụng khởi động.

| Giá trị | Hành vi khái quát | Tình huống |
|---|---|---|
| **none** | Không yêu cầu Hibernate tạo, cập nhật hoặc validate schema | Khi schema được kiểm tra bằng cơ chế khác |
| **validate** | Kiểm tra schema hiện có có tương thích với mapping Hibernate hay không | Phù hợp khi Liquibase quản lý schema |
| **update** | Cố gắng điều chỉnh schema để phù hợp mapping | Có thể hữu ích trong thử nghiệm, không nên là cơ chế migration production |
| **create** | Tạo schema theo mapping khi khởi động; có thể xóa đối tượng schema hiện có trước khi tạo tùy cơ chế Hibernate | Database thử nghiệm có thể hủy được |
| **create-drop** | Tạo schema khi khởi động và xóa schema do Hibernate quản lý khi SessionFactory/EntityManagerFactory đóng | Một số thử nghiệm hoặc môi trường tạm thời |

Hành vi chi tiết, đặc biệt với create và create-drop, có thể phụ thuộc phiên bản Hibernate, cấu hình schema generation và database. Không dùng chúng trên database chứa dữ liệu cần bảo toàn.

### 2.1. Vì sao chọn validate khi dùng Liquibase?

Với **validate**, Hibernate không tự sửa schema để khớp entity. Nếu entity yêu cầu cột nhưng database chưa có, ứng dụng có thể thất bại khi khởi động và báo lỗi mapping/schema. Đây là tín hiệu hữu ích: changelog có thể chưa được triển khai, hoặc entity và migration không cùng phiên bản.

Ví dụ, entity có thuộc tính **customer.region** nhưng database chưa có cột region. Hibernate validate phát hiện cột không tồn tại và báo lỗi. Nhóm kiểm tra changeset thêm cột đã có trong artifact chưa, migration đã chạy trên đúng database chưa, và thứ tự deploy có đúng không. Sau khi Liquibase áp dụng changeset hợp lệ, ứng dụng khởi động lại và validation có thể thành công.

**validate không tạo cột region giúp ứng dụng.** Nó báo trạng thái không tương thích để nhóm sửa đúng migration hoặc triển khai.

### 2.2. Khi nào dùng none?

**none** phù hợp khi nhóm không muốn Hibernate kiểm tra schema lúc khởi động, chẳng hạn validation được thực hiện bằng một công cụ khác hoặc có mapping đặc thù không thể kiểm tra đầy đủ bằng Hibernate. Tuy vậy, bỏ validate không có nghĩa schema chắc chắn đúng. Cần có kiểm tra thay thế trong CI/CD hoặc startup health check phù hợp.

Nếu không có cơ chế kiểm tra nào, ứng dụng có thể chỉ phát hiện schema sai khi một truy vấn thực sự được thực thi.

### 2.3. Vì sao không dùng update làm migration chính?

**update** suy ra DDL từ entity mapping và cố điều chỉnh schema. Đây không phải một lịch sử migration có version rõ ràng:

- Không có changeset nghiệp vụ tương ứng trong changelog.
- Không thể review chuỗi migration có ID, author và rollback rõ ràng như Liquibase.
- Các thay đổi rename, data backfill, chuyển đổi dữ liệu và constraint phức tạp không thể được suy ra an toàn chỉ từ mapping.
- Kết quả có thể phụ thuộc Hibernate version và dialect.
- Nhiều instance khởi động có thể tạo ra hành vi triển khai khó kiểm soát.
- Rollback không có lịch sử tương đương DATABASECHANGELOG.

Dùng update làm nguồn thay đổi schema song song với Liquibase sẽ tạo **hai chủ sở hữu schema**. Nếu mục tiêu là quản lý migration có thể review, kiểm chứng và rollback, hãy đưa thay đổi vào changeset.

## 3. Cấu hình Spring Boot cơ bản

Một cấu hình điển hình khi Liquibase quản lý schema và Hibernate chỉ validate:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/appdb
    username: app_user
    password: $DB_PASSWORD
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Ý nghĩa:

- **spring.datasource** cung cấp kết nối database cho ứng dụng và các thành phần tích hợp mặc định.
- **spring.liquibase.enabled=true** bật Liquibase auto-configuration.
- **spring.liquibase.change-log** chỉ định master changelog trên classpath.
- **spring.jpa.hibernate.ddl-auto=validate** yêu cầu Hibernate kiểm tra mapping với schema đã được khởi tạo.

Password được lấy từ biến môi trường trong ví dụ. Trong production nên dùng secret manager hoặc cơ chế quản lý bí mật của nền tảng, không commit credential vào YAML.

Tên property và hành vi auto-configuration cần được đối chiếu với phiên bản Spring Boot, Liquibase và Hibernate mà dự án sử dụng. Nếu dùng nhiều datasource hoặc cấu hình tùy chỉnh, phải xác định rõ datasource nào được Liquibase sử dụng và datasource nào được JPA sử dụng.

### 3.1. Chọn ddl-auto theo môi trường

Không nên để một giá trị khác nhau tùy tiện giữa môi trường. Ví dụ, nếu development dùng update còn production dùng validate, schema ở development có thể phát triển theo entity mà không có changeset. Khi merge code, changelog không tái tạo được schema mà developer đang chạy.

Một cấu hình rõ ràng:

~~~yaml
# application.yml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Có thể dùng profile để ghi đè thông số kết nối hoặc bật/tắt migration trong một số kịch bản kiểm thử đặc biệt, nhưng nên giữ nguyên nguyên tắc **Liquibase là chủ sở hữu schema** ở các môi trường tích hợp và triển khai.

Nếu cần **none** cho một môi trường, hãy ghi rõ cơ chế kiểm tra schema thay thế. Không dùng profile test để che một migration sai khiến integration test không còn phát hiện schema mismatch.

## 4. Thứ tự Liquibase và Hibernate khi Spring Boot khởi động

Khi ứng dụng cần cả Liquibase và Hibernate, schema phải sẵn sàng trước khi Hibernate tạo EntityManagerFactory và validate mapping.

~~~text
Spring Boot application startup
          |
          v
Create/configure DataSource
          |
          v
Liquibase initialization
          |
          +--> acquire DATABASECHANGELOGLOCK
          +--> read DATABASECHANGELOG
          +--> apply pending changesets
          +--> release lock
          |
          v
Hibernate builds EntityManagerFactory
          |
          v
ddl-auto=validate checks mapping
          |
          v
Application becomes ready
~~~

Spring Boot có cơ chế sắp xếp các thành phần khởi tạo database và các bean phụ thuộc vào database trong cấu hình auto-configuration thông thường. Tuy nhiên, custom bean, nhiều datasource, lazy initialization hoặc cấu hình tự viết có thể thay đổi thứ tự. Hãy kiểm tra thực tế bằng startup log và integration test.

Nếu Hibernate validate chạy trước migration, ứng dụng có thể báo thiếu bảng/cột dù changelog có thể tạo chúng. Khi gặp tình huống này, cần kiểm tra thứ tự khởi tạo và datasource, không vội chuyển ddl-auto sang update.

Một số nguyên tắc startup:

- Dùng cùng database/schema cho Liquibase và JPA nếu đó là kiến trúc dự kiến.
- Đảm bảo Liquibase được bật và master changelog được tìm thấy.
- Không tạo EntityManagerFactory từ datasource khác chưa được migration.
- Không để một bean khởi động truy vấn database trước khi initializer hoàn tất nếu cấu hình tùy chỉnh phá dependency ordering.
- Xem log Liquibase và Hibernate theo thứ tự thời gian.
- Với migration job độc lập, triển khai schema trước khi rollout application cần schema mới.

Trong ứng dụng phức tạp, có thể cần khai báo dependency khởi tạo rõ ràng theo cơ chế Spring Boot phù hợp phiên bản. Trước khi thêm annotation hoặc bean dependency tùy chỉnh, hãy xác định bean nào thực sự được khởi tạo quá sớm.

## 5. Entity mapping phải khớp với schema Liquibase

Hibernate đọc mapping từ entity và metadata JPA. Liquibase tạo schema. Hai phần phải thống nhất về tên bảng/schema, tên cột, kiểu dữ liệu, độ dài, precision/scale, nullability, primary key, chiến lược sinh khóa, quan hệ, enum, temporal mapping/timezone và naming strategy.

Ví dụ entity:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 200)
    private String fullName;

    @Column(name = "email", length = 320)
    private String email;

    @Column(name = "status", nullable = false, length = 24)
    private String status;

    protected Customer() {
    }
}
~~~

Changelog tương ứng có thể khai báo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "platform"
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: full_name
                  type: VARCHAR(200)
                  constraints:
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
              - column:
                  name: status
                  type: VARCHAR(24)
                  defaultValue: NEW
                  constraints:
                    nullable: false
~~~

Đây là ví dụ cho một DBMS/kiểu sinh khóa tương thích với cấu hình minh họa. Cần kiểm tra DDL được sinh trên DBMS thực tế. **GenerationType.IDENTITY** phải tương thích với identity/auto-increment mà migration tạo; nếu dùng sequence hoặc table generator thì schema và mapping cần được thiết kế tương ứng.

### 5.1. Naming strategy

JPA/Hibernate có thể áp dụng **physical naming strategy** để chuyển tên thuộc tính Java sang tên cột vật lý. Ví dụ **fullName** có thể trở thành **full_name** theo naming strategy. Nếu changelog tạo fullName nhưng Hibernate tìm full_name, validate hoặc truy vấn sẽ thất bại.

Có hai cách rõ ràng:

- Khai báo tên vật lý bằng **@Column(name = "full_name")** và tên bảng bằng **@Table**.
- Thống nhất naming strategy của ứng dụng và đặt tên trong changelog theo kết quả thực tế.

Không nên đổi naming strategy giữa các môi trường mà không có migration tương ứng. Cùng entity source nhưng profile khác naming strategy có thể tìm những bảng/cột khác nhau.

### 5.2. Nullability và validation nghiệp vụ

**@Column(nullable = false)** mô tả nullability trong mapping và có thể tham gia schema generation/validation tùy Hibernate. Nhưng nó không thay thế DDL constraint được quản lý trong Liquibase.

**@NotNull** từ Bean Validation là một cơ chế validation ở tầng ứng dụng. Nó có thể từ chối entity trước khi gửi SQL nếu validation được kích hoạt. Tuy nhiên, nó không bảo vệ các luồng ghi ngoài ứng dụng như SQL trực tiếp, batch job hoặc service khác. Để bảo vệ dữ liệu ở mọi writer, database cần constraint phù hợp do migration tạo.

| Cơ chế | Phạm vi |
|---|---|
| **@NotNull** | Validation object/entity ở tầng ứng dụng khi được kích hoạt |
| **@Column(nullable=false)** | Metadata mapping và schema generation/validation của ORM |
| **NOT NULL trong database** | Ràng buộc dữ liệu được DBMS thực thi |
| **Precondition Liquibase** | Điều kiện kiểm tra trước khi changeset chạy |

## 6. Tách trách nhiệm: migration trong changelog, mapping trong entity

Khi thêm một thuộc tính mới, quy trình nên là:

1. Thiết kế thay đổi schema và dữ liệu.
2. Viết changeset Liquibase có ID, author và rollback phù hợp.
3. Kiểm tra SQL và precondition.
4. Thử migration trên database đại diện.
5. Cập nhật entity mapping để phản ánh schema đích.
6. Chạy Hibernate validate trong integration test.
7. Triển khai migration và ứng dụng theo thứ tự tương thích.

Không nên dựa vào việc sửa entity rồi để Hibernate update database. Ví dụ đổi:

~~~java
@Column(name = "email", length = 320)
private String email;
~~~

thành:

~~~java
@Column(name = "email", length = 500)
private String email;
~~~

thì migration cần thay đổi độ dài cột trong changelog. Việc mapping Java đã khai báo length 500 không tự là một migration có lịch sử.

Tương tự, đổi tên field Java không nhất thiết là đổi tên cột database nếu có annotation **@Column(name=...)** giữ tên cũ. Hãy phân biệt refactor code với thay đổi schema.

## 7. Hibernate validate kiểm tra được gì và giới hạn ở đâu?

**ddl-auto=validate** là một hàng rào hữu ích để phát hiện một số sai lệch giữa entity mapping và database. Ví dụ bảng hoặc cột được mapping không tồn tại, kiểu cột không tương thích với kiểu Hibernate mong đợi, hoặc một số khác biệt về cấu trúc được Hibernate schema validator nhận diện.

Nhưng không nên xem validate là một công cụ diff schema đầy đủ. Mức độ kiểm tra phụ thuộc Hibernate version, dialect và metadata database. Nó không thay thế việc xác minh tất cả index, check constraint, default expression, trigger, procedure, view, partition, cascade/deferrable của foreign key, invariant nghiệp vụ của dữ liệu hoặc những object không được ánh xạ trong entity.

Ví dụ entity không khai báo một index phụ trợ thì Hibernate validate có thể không báo thiếu index đó. Liquibase vẫn phải quản lý index và CI cần có kiểm tra phù hợp.

**Kết hợp hai lớp kiểm tra**:

1. Liquibase và kiểm tra schema/database đảm bảo migration tạo đúng đối tượng.
2. Hibernate validate đảm bảo mapping entity có thể làm việc với schema ở những khía cạnh Hibernate hỗ trợ.

## 8. Vì sao ddl-auto=update tạo rủi ro khi dùng Liquibase?

Một tình huống:

- Nhánh A thêm cột **customer.region** trong entity.
- Developer bật **ddl-auto=update**.
- Hibernate tự thêm cột trên database local.
- Changeset Liquibase chưa được tạo.
- Developer commit code và deploy sang staging.
- Staging chỉ chạy Liquibase, nên cột region không có.
- Hibernate validate hoặc truy vấn ứng dụng báo lỗi.

Ở local, mọi thứ có vẻ hoạt động; ở staging, schema khác vì lịch sử migration thiếu bước thay đổi.

Một tình huống khác: Hibernate update tạo constraint/index theo naming hoặc dialect khác với convention của Liquibase. Sau đó changeset Liquibase cố tạo cùng object, dẫn đến duplicate object hoặc trạng thái không đồng nhất.

Nếu đã dùng update trên một database, không nên đơn giản chạy changelog mới lên đó mà chưa kiểm tra. Hãy so sánh schema thực tế, xác định object nào do Hibernate tạo, rồi tạo changeset tương ứng hoặc đồng bộ lịch sử theo kế hoạch đã review. Không chỉnh DATABASECHANGELOG thủ công để che sự khác biệt.

## 9. Cấu hình riêng datasource cho Liquibase

Trong một số hệ thống, tài khoản ứng dụng chỉ có quyền DML, còn tài khoản migration có quyền DDL. Spring Boot có thể cấu hình thông tin kết nối riêng cho Liquibase:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/appdb
    username: app_runtime
    password: $APP_DB_PASSWORD
  liquibase:
    url: jdbc:postgresql://db-host:5432/appdb
    user: liquibase_migrator
    password: $LIQUIBASE_DB_PASSWORD
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Property cụ thể cho datasource Liquibase có thể khác theo phiên bản Spring Boot; kiểm tra configuration metadata và tài liệu phiên bản của dự án. Với cấu hình Java tùy chỉnh, có thể khai báo datasource riêng và đánh dấu datasource dành cho Liquibase bằng cơ chế như **@LiquibaseDataSource** nếu phiên bản hỗ trợ.

Các nguyên tắc bảo mật:

- Tài khoản migration chỉ được cấp quyền DDL cần thiết trong phạm vi schema.
- Tài khoản ứng dụng chỉ có quyền đọc/ghi nghiệp vụ cần thiết.
- Không dùng tài khoản DBA toàn quyền cho ứng dụng thường xuyên.
- Credential được lưu ở secret manager, không commit vào source.
- Log không in password hoặc URL chứa thông tin nhạy cảm.

Nếu Liquibase và Hibernate dùng hai datasource khác nhau, phải bảo đảm chúng trỏ tới **cùng database/schema đích** hoặc kiến trúc đã định nghĩa. Một trường hợp nguy hiểm là Liquibase cập nhật database A trong khi Hibernate kết nối database B; migration log báo thành công nhưng ứng dụng vẫn thiếu bảng.

## 10. Profile và cấu hình môi trường

Một ví dụ cấu hình theo profile:

~~~yaml
# application.yml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

~~~yaml
# application-test.yml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/app_test
  liquibase:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
~~~

~~~yaml
# application-prod.yml
spring:
  datasource:
    url: $DB_URL
    username: $DB_USER
    password: $DB_PASSWORD
  liquibase:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Mục tiêu là giữ hành vi migration và validation nhất quán. Khác biệt profile chủ yếu là kết nối, secret, context/label hoặc các tham số môi trường được phê duyệt.

Nếu tắt Liquibase trong test hoặc một profile nào đó, phải biết database được tạo bằng cách nào. Một embedded database được Hibernate create-drop có thể làm test qua nhưng không phản ánh schema thật do Liquibase quản lý.

Không để production dùng **ddl-auto=update** trong khi staging dùng validate. Cấu hình như vậy khiến production có thể tự sửa schema ngoài release artifact và làm mất tính truy nguyên.

## 11. Tích hợp Liquibase với Spring Boot: changelog và migration

Một master changelog có thể tổ chức theo module:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/001-create-customer.yaml
      relativeToChangelogFile: false
  - include:
      file: db/changelog/002-create-sales-order.yaml
      relativeToChangelogFile: false
  - include:
      file: db/changelog/003-add-customer-region.yaml
      relativeToChangelogFile: false
~~~

Trong dự án thực tế, cấu trúc classpath và relative path phải khớp với artifact được đóng gói. Changelog cần được version-control và có thứ tự dependency rõ.

Một changeset thêm cột:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010-add-customer-region"
      author: "platform"
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
        - not:
            columnExists:
              tableName: customer
              columnName: region
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: region
                  type: VARCHAR(40)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: region
~~~

Ví dụ minh họa cách bảo vệ điều kiện; trong hệ thống thật, cần xem xét cột đã tồn tại do drift hay do migration khác, và không dùng **MARK_RAN** nếu chưa chứng minh trạng thái đích. Rollback dropColumn sẽ làm mất dữ liệu trong cột region nếu ứng dụng đã ghi; cần đánh giá trước khi dùng trên production.

Khi ứng dụng khởi động, Liquibase đọc changelog, so sánh DATABASECHANGELOG, chạy changeset pending rồi Hibernate validate mapping. Cấu hình này hoạt động tốt khi cùng artifact và database được chọn đúng.

## 12. Thứ tự phát hành entity và schema

Một thay đổi entity/schema có thể gây lỗi nếu phát hành không đúng thứ tự, đặc biệt khi rolling deployment có nhiều phiên bản ứng dụng cùng chạy.

~~~text
Release A: Liquibase addColumn region nullable
       |
       v
Release B: deploy app biết đọc/ghi region
       |
       v
Backfill dữ liệu cũ nếu cần
       |
       v
Verify dữ liệu và writer
       |
       v
Release C: add NOT NULL hoặc constraint mới nếu yêu cầu
~~~

Không nên triển khai entity mới yêu cầu cột region trước khi migration tạo cột trên database. Với **ddl-auto=validate**, ứng dụng mới có thể dừng startup ngay nếu schema chưa sẵn sàng. Đây là hành vi bảo vệ tốt nếu pipeline đã triển khai migration trước.

Với thay đổi phá tương thích như drop/rename column, cần dùng **expand-contract**:

1. Thêm cấu trúc mới nhưng giữ cấu trúc cũ.
2. Triển khai code tương thích cả hai.
3. Chuyển dữ liệu và xác minh.
4. Chuyển toàn bộ writer/reader sang cấu trúc mới.
5. Gỡ cấu trúc cũ trong một release sau.

Hibernate validate chỉ kiểm tra mapping của phiên bản ứng dụng đang khởi động; nó không bảo đảm các instance cũ còn chạy sẽ tương thích với schema mới. Cần xét toàn bộ phiên bản app trong quá trình rollout.

## 13. Kiểm thử tích hợp: database thật và migration thật

Một test chỉ khởi tạo entity trên H2 có thể không phát hiện lỗi DDL PostgreSQL hoặc MySQL. Khi production dùng DBMS cụ thể, integration test quan trọng nên chạy trên cùng loại database hoặc container tương ứng.

| Loại test | Kiểm tra |
|---|---|
| **Changelog validate** | Changelog parse được, include hợp lệ |
| **Fresh database migration** | Liquibase dựng schema từ database trống |
| **Upgrade migration** | Changeset mới chạy trên schema ở version trước |
| **Hibernate validate** | Entity mapping tương thích schema sau migration |
| **Repository integration** | Truy vấn, insert/update và quan hệ hoạt động |
| **Constraint behavior** | NOT NULL, FK, unique/check thực thi như kỳ vọng |
| **Rollback test** | SQL rollback và trạng thái sau hoàn tác |
| **Application startup test** | Spring context khởi động theo đúng thứ tự |

Với Testcontainers, có thể provision DBMS thật cho test:

~~~java
@Testcontainers
@SpringBootTest
class CustomerRepositoryIntegrationTest {

    @Container
    static PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void savesCustomerUsingLiquibaseManagedSchema() {
        Customer customer = new Customer();
        // Set required fields and persist through the repository.
    }
}
~~~

Đây là skeleton minh họa; cần thêm dependency Testcontainers, driver và dữ liệu bắt buộc của entity. Spring Boot test context sẽ cần bật Liquibase theo cấu hình test và dùng **ddl-auto=validate** để kiểm tra schema. Với **@DataJpaTest**, kiểm tra cấu hình thay thế datasource mặc định; nếu muốn giữ database Testcontainers, có thể cần cấu hình tương ứng như **@AutoConfigureTestDatabase(replace = NONE)** tùy phiên bản Spring Boot.

### 13.1. Test database trống và database nâng cấp

Cả hai đường đều cần thiết:

- **Fresh database**: chứng minh baseline và toàn bộ changelog dựng được schema mới.
- **Upgrade database**: chứng minh changeset mới hoạt động trên schema/dữ liệu đã tồn tại, không chỉ trên trạng thái sạch.

Một changelog có thể tạo được schema từ đầu nhưng lỗi khi nâng cấp vì precondition, dữ liệu NULL, index trùng hoặc thay đổi tên cột. Hibernate validate sau migration giúp phát hiện mapping mismatch trong cả hai kịch bản.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Hibernate báo thiếu bảng/cột | Liquibase chưa chạy, changelog thiếu changeset hoặc dùng sai datasource/schema | Kiểm tra startup log, DATABASECHANGELOG, URL/schema |
| Liquibase thành công nhưng Hibernate validate lỗi | Mapping không khớp tên/kiểu/cột, datasource khác nhau | So sánh entity, naming strategy và catalog DB |
| Ứng dụng khởi động trước migration | Custom initialization/dependency ordering | Kiểm tra bean initialization và cấu hình Spring Boot |
| Local chạy được, staging lỗi | Local dùng ddl-auto=update hoặc schema drift | Đưa thay đổi vào changelog, tái tạo database từ artifact |
| Duplicate table/column | Liquibase chưa sync baseline hoặc Hibernate đã tự tạo object | Xác minh schema và lịch sử, lập kế hoạch baseline |
| Không tương thích kiểu dữ liệu | Type mapping/dialect/precision khác DBMS | Xem DDL và metadata, sửa changeset hoặc mapping |
| Entity nullable nhưng DB NOT NULL | Mapping và constraint không thống nhất | Thống nhất contract; cập nhật entity hoặc migration theo nghiệp vụ |
| @NotNull không ngăn SQL trực tiếp | Bean Validation chỉ chạy trong tầng ứng dụng | Tạo database constraint bằng Liquibase |
| Test H2 pass, production fail | Dialect và DDL semantics khác nhau | Test bằng DBMS production hoặc container tương ứng |
| Liquibase lock đang giữ | Migration khác đang chạy hoặc process bị dừng | Kiểm tra tiến trình/log trước khi release lock |
| Startup rất lâu | Changeset DDL/DML lớn hoặc precondition quét bảng | Tách migration job, đo thời gian và tối ưu |
| Rollback xong app không chạy | Schema đã lùi nhưng app version không tương thích | Phối hợp rollback app/schema hoặc roll-forward |

### 14.1. Trình tự điều tra

Khi startup lỗi, nên thu thập theo thứ tự:

1. **Database URL/schema**: ứng dụng và Liquibase có thực sự cùng database?
2. **Liquibase log**: changelog có được tìm thấy, lock có được lấy, changeset nào đã chạy?
3. **DATABASECHANGELOG**: changeset mong đợi đã được ghi nhận chưa?
4. **Schema thực tế**: bảng/cột/constraint có tồn tại và đúng kiểu không?
5. **Hibernate mapping**: tên bảng/cột, naming strategy, ID generation, type và nullability.
6. **DDL preview**: SQL dự kiến có đúng dialect?
7. **Phiên bản runtime**: Spring Boot, Hibernate, Liquibase, JDBC driver và DBMS có tương thích không?

Không chuyển ddl-auto sang update chỉ để ứng dụng khởi động qua lỗi. Cần xác định migration hoặc mapping nào sai và sửa tại đúng nguồn sở hữu.

## 15. Quản lý checksum và lịch sử khi entity thay đổi

Khi entity thay đổi, không sửa trực tiếp changeset đã triển khai để làm database khớp entity mới. Hãy tạo changeset mới.

Ví dụ:
- Changeset cũ tạo **customer.email VARCHAR(320)**.
- Entity mới cần độ dài 500.
- Tạo changeset mới dùng modifyDataType hoặc SQL phù hợp để mở rộng cột.
- Cập nhật entity mapping thành length 500 trong cùng release.
- Kiểm thử migration từ schema cũ và Hibernate validate trên schema mới.

Liquibase ghi checksum của changeset trong DATABASECHANGELOG. Nếu sửa nội dung changeset cũ sau khi đã chạy, checksum validation có thể báo lỗi. **Hibernate validate không sửa hoặc bỏ qua checksum**; hai cơ chế kiểm soát khác nhau.

Không dùng **clear-checksums** để che một thay đổi lịch sử chưa được điều tra. Nếu changeset cũ có lỗi, thường nên giữ nguyên lịch sử và thêm changeset sửa chữa mới. Chỉ dùng cơ chế checksum đặc biệt theo quy trình có chủ đích, có review và hiểu ảnh hưởng trên mọi môi trường.

## 16. Hibernate dialect và khác biệt DBMS

Hibernate dùng dialect để tạo SQL cho database. Liquibase cũng nhận diện DBMS và sinh SQL theo change type hoặc SQL riêng. Hai cơ chế cần tương thích với cùng database nhưng không nhất thiết dùng cùng một cách khai báo.

Các vấn đề cần kiểm tra:

- Kiểu dữ liệu vật lý mà Liquibase tạo có tương thích mapping Hibernate không?
- IDENTITY/SEQUENCE trong entity có khớp cấu trúc database không?
- Timestamp có timezone được ánh xạ đúng không?
- Enum được lưu dạng STRING hay ORDINAL, changelog tạo kiểu phù hợp chưa?
- JSON/UUID/array type có phụ thuộc dialect cụ thể không?
- Naming strategy có giống giữa môi trường không?
- Hibernate version có thay đổi cách validate type hoặc sequence không?

Không nên ép một dialect cụ thể vào cấu hình nếu Hibernate có thể nhận diện đúng từ JDBC metadata, trừ khi có lý do tương thích rõ. Nếu khai báo dialect thủ công, phải bảo đảm phù hợp DBMS và version.

Với hệ thống hỗ trợ nhiều DBMS, kiểm thử ma trận trên từng engine. Một mapping validate thành công trên PostgreSQL không chứng minh schema và entity hoạt động tương đương trên SQL Server hoặc MySQL.

## 17. Khi nào nên tắt Liquibase trong Spring Boot?

Có một số trường hợp đặc biệt:

- Một ứng dụng chỉ đọc database do một service khác sở hữu schema.
- Migration được chạy bởi pipeline/job độc lập trước khi ứng dụng khởi động.
- Test cần dùng schema fixture được dựng sẵn và có chủ đích không chạy changelog.
- Một module chỉ dùng datasource phụ không quản lý schema.

Có thể dùng:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Nhưng khi tắt, phải bảo đảm database đã được migration bằng quy trình khác. Nếu ứng dụng có **ddl-auto=validate**, Hibernate vẫn kiểm tra schema khi startup; nếu schema chưa sẵn sàng, ứng dụng có thể không khởi động. Nếu đặt **ddl-auto=none**, cần có cơ chế xác minh thay thế.

Không tắt Liquibase chỉ để bỏ qua một changeset lỗi trên môi trường thật. Hãy sửa precondition, dữ liệu hoặc migration theo kế hoạch; nếu không, các môi trường sẽ mất tính nhất quán.

## 18. CI/CD: một nguồn thay đổi schema

Một pipeline triển khai tốt nên tách migration và application rollout khi cần:

~~~text
Build immutable application artifact
            |
            v
Validate changelog
            |
            v
Provision/identify target database
            |
            v
Liquibase update (migration job)
            |
            v
Verify schema and data invariants
            |
            v
Start/roll out Spring Boot application
            |
            v
Hibernate ddl-auto=validate
            |
            v
Smoke test and readiness check
~~~

Các gate quan trọng:

- Changelog được validate và review.
- SQL được preview theo đúng DBMS.
- Migration chạy trên database đại diện trước production.
- Dữ liệu được backfill và kiểm chứng trước constraint mới.
- Application artifact dùng cùng phiên bản entity mapping với schema release.
- Hibernate validate chạy thành công sau migration.
- Log, commit, Liquibase version, DBMS version và changeset history được lưu.

Nếu Spring Boot tự chạy Liquibase khi khởi động, vẫn cần bảo đảm artifact có đúng changelog và các instance không dùng phiên bản khác nhau. Với nhiều instance, Liquibase lock hỗ trợ tránh các tiến trình update đồng thời trên cùng database, nhưng không giải quyết compatibility giữa application version cũ và schema mới. Chiến lược expand-contract vẫn cần thiết.

## 19. Bài thực hành: Liquibase tạo schema, Hibernate validate

**Bài toán:** Ứng dụng Spring Boot có entity Customer với id, fullName, email và status. Database được quản lý bằng Liquibase. Hibernate phải xác minh mapping khi startup.

### Bước 1 — Tạo changelog

- Viết changeset createTable customer.
- Chỉ định primary key, nullability, độ dài cột và default theo yêu cầu.
- Xác định chiến lược sinh khóa tương thích với DBMS.
- Viết rollback có xem xét dữ liệu.

### Bước 2 — Viết entity

- Dùng **@Entity** và **@Table(name = "customer")**.
- Dùng **@Column(name = "full_name")** cho tên cột vật lý.
- Đồng bộ length/nullability và ID generation với schema.
- Không yêu cầu Hibernate tự sửa schema.

### Bước 3 — Cấu hình Spring Boot

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

### Bước 4 — Khởi động trên database trống

- Xác nhận Liquibase tạo bảng trước khi Hibernate validate.
- Kiểm tra DATABASECHANGELOG có changeset createTable.
- Kiểm tra catalog database và entity mapping.
- Xác nhận ứng dụng khởi động thành công.

### Bước 5 — Tạo lỗi có chủ đích trên database thử nghiệm

- Đổi tên cột trong entity mà không sửa changelog.
- Chạy lại ứng dụng và quan sát lỗi validate.
- Khôi phục mapping hoặc thêm changeset renameColumn đúng cách.
- Không bật ddl-auto=update để che lỗi.

### Bước 6 — Kiểm thử database nâng cấp

- Dựng schema từ baseline cũ.
- Chạy changeset thêm cột mới.
- Cập nhật entity.
- Chạy Hibernate validate và repository test.
- Thử rollback trên database tạm, kiểm tra dữ liệu có bị mất không.

### Bước 7 — Ghi bằng chứng

Lưu kết quả Liquibase validate/update, DATABASECHANGELOG, schema metadata, Hibernate startup log và integration test. Giải thích rõ vì sao **validate** phù hợp khi Liquibase là chủ sở hữu schema.

## 20. Checklist review trước khi triển khai

- Liquibase có phải nguồn duy nhất quản lý DDL/schema?
- ddl-auto được đặt tường minh, thường là validate hoặc none theo chính sách?
- Không có môi trường production dùng update, create hoặc create-drop ngoài ý định thử nghiệm được kiểm soát?
- Master changelog, đường dẫn và changeset identity ổn định?
- Migration được áp dụng trước khi Hibernate validate mapping mới?
- Liquibase và JPA có dùng đúng database/schema dự kiến?
- Entity table/column names khớp physical naming strategy?
- Kiểu dữ liệu, precision/scale, timezone, enum và ID generation tương thích?
- @NotNull, @Column(nullable=false) và database NOT NULL được hiểu đúng tầng trách nhiệm?
- Hibernate validate được xem là kiểm tra mapping, không phải schema diff đầy đủ?
- Precondition và rollback được review theo dữ liệu thực tế?
- Integration test chạy trên DBMS/version phù hợp?
- Có test cả database trống và database nâng cấp?
- Với Testcontainers hoặc @DataJpaTest, datasource thay thế có được cấu hình đúng?
- Spring Boot startup ordering đã được xác minh qua log/test?
- Nếu dùng datasource riêng cho Liquibase, tài khoản và database đích đã đúng?
- Checksum mismatch được điều tra, không bị clear-checksums để che lỗi?
- CI/CD triển khai schema trước application và có smoke test sau startup?
- Có phương án rollback/roll-forward tương thích với phiên bản ứng dụng đang chạy?

**Kết luận:** Khi phối hợp Spring Boot, Liquibase và Hibernate, hãy để **Liquibase quản lý mọi thay đổi schema** qua changelog và changeset; Hibernate tập trung ánh xạ entity và thường dùng **ddl-auto=validate** để phát hiện mapping không khớp khi khởi động. **none** có thể phù hợp nếu có cơ chế kiểm tra thay thế; **update**, **create** và **create-drop** không nên trở thành nguồn migration song song trong môi trường cần bảo toàn dữ liệu. Đồng bộ entity mapping, thứ tự khởi tạo, datasource, DBMS và kiểm thử CI/CD sẽ giúp ứng dụng khởi động trên schema đúng, giữ lịch sử thay đổi có thể truy nguyên và giảm rủi ro lệch môi trường.

