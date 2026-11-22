# Thứ tự khởi động và hành vi khi migration thất bại

## 1. Vì sao thứ tự khởi động có ý nghĩa?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi tích hợp Spring Boot, migration thường được chạy ngay trong quá trình khởi tạo application context. Vì vậy, **thứ tự tạo DataSource, chạy Liquibase và khởi tạo những bean cần database quyết định ứng dụng có khởi động đúng hay không**.

Giả sử phiên bản ứng dụng mới cần cột `customer_account.status_code`. Nếu một repository hoặc `EntityManagerFactory` sử dụng cột đó trước khi migration thêm cột hoàn tất, ứng dụng có thể lỗi ngay khi khởi động. Nếu migration thất bại nhưng ứng dụng vẫn nhận traffic, request có thể chạy trên schema chỉ được cập nhật một phần. Nếu nhiều replica cùng khởi động và tự chạy Liquibase, thời gian khởi động có thể kéo dài hoặc các instance phải chờ lock.

Khi cấu hình mặc định của Spring Boot được dùng và Liquibase được bật, bean tích hợp `SpringLiquibase` thực hiện migration trong giai đoạn khởi tạo context. Spring Boot cũng thiết lập các quan hệ phụ thuộc để những thành phần database phổ biến chờ quá trình khởi tạo database hoàn tất. Cách triển khai chi tiết phụ thuộc phiên bản Boot, Liquibase và cấu hình DataSource.

Bài học này giải thích vòng đời từ lúc Spring Boot tạo DataSource đến lúc Liquibase cập nhật database, thời điểm các bean JPA/JDBC và runner có thể sử dụng schema, hành vi khi precondition/checksum/SQL/kết nối thất bại, partial apply, lock, nhiều DataSource, nhiều replica và cách đưa migration thành bước triển khai có kiểm soát trong CI/CD.

## 2. Luồng khởi động điển hình

Trong ứng dụng Spring Boot có Liquibase trên classpath và auto-configuration phù hợp, luồng khái quát như sau:

```text
Khởi chạy SpringApplication
          |
          v
Đọc Environment / cấu hình profile
          |
          v
Tạo DataSource và cấu hình kết nối
          |
          v
Tạo bean SpringLiquibase
          |
          v
SpringLiquibase.afterPropertiesSet()
          |
          v
Kết nối database, lấy Liquibase lock
          |
          v
Đọc changelog và DATABASECHANGELOG
          |
          v
Kiểm tra precondition / checksum
          |
          v
Thực thi các changeset pending
          |
          v
Ghi lịch sử, giải phóng lock
          |
          v
Khởi tạo các bean phụ thuộc database
          |
          v
Hoàn tất ApplicationContext
          |
          v
ApplicationRunner / CommandLineRunner
          |
          v
Ứng dụng sẵn sàng nhận traffic
```

Đây là mô hình để hiểu thứ tự, không phải sơ đồ mọi callback nội bộ của tất cả phiên bản Spring Boot. Những điểm cần nhớ:

1. Liquibase cần một DataSource hợp lệ để kết nối database.
2. Migration được thực hiện trong quá trình khởi tạo bean `SpringLiquibase`.
3. Những bean được Spring Boot nhận diện là phụ thuộc database initialization sẽ chờ quá trình đó.
4. Runner chỉ được gọi sau khi application context đã khởi tạo thành công.
5. Nếu Liquibase ném lỗi trong lúc khởi tạo bean, quá trình refresh context thường thất bại và ứng dụng không đi đến trạng thái sẵn sàng.

### 2.1. Tại sao Liquibase chạy trước repository/JPA?

Ứng dụng thường có các bean như `JdbcTemplate`, repository, `EntityManagerFactory` hoặc service cần bảng/cột đã tồn tại. Spring Boot có cơ chế sắp xếp dependency giữa các database initializer và các bean tiêu thụ database, thay vì để tất cả khởi tạo theo thứ tự ngẫu nhiên.

Với cấu hình thông dụng, Liquibase được nhận diện là một database initializer. Các thành phần JPA/JDBC phổ biến được cấu hình để chờ initialization hoàn tất. Nếu dự án tự tạo bean tùy chỉnh, sử dụng thư viện khác hoặc khởi tạo database theo cách riêng, cần kiểm tra dependency thực tế; không mặc định mọi bean tự viết đều được Spring Boot nhận diện.

### 2.2. Migration hoàn tất trước khi runner chạy

`CommandLineRunner` và `ApplicationRunner` được gọi sau khi application context được refresh thành công. Vì thế, nếu runner truy vấn bảng vừa được Liquibase tạo, nó thường thấy schema sau migration.

Tuy nhiên, không nên dùng runner như một cách tùy tiện để chạy thêm DDL sau khi ứng dụng đã bắt đầu phục vụ. Nếu thay đổi là migration database, hãy quản lý nó bằng changelog và một quy trình sở hữu migration rõ ràng.

## 3. SpringLiquibase và auto-configuration của Spring Boot

`SpringLiquibase` là thành phần tích hợp Liquibase với vòng đời Spring. Khi bean được khởi tạo, phương thức khởi tạo của bean thực hiện quá trình update theo cấu hình. Trong Spring Boot, auto-configuration có thể tạo bean này khi:

- Liquibase có trên classpath.
- Có DataSource phù hợp.
- Auto-configuration Liquibase không bị loại trừ.
- `spring.liquibase.enabled` không bị tắt.
- Ứng dụng không khai báo bean tùy chỉnh làm auto-configuration lùi lại theo điều kiện của phiên bản.

Trong các phiên bản Spring Boot phổ biến, Liquibase auto-configuration được sắp xếp sau cấu hình DataSource để có thể sử dụng DataSource đã được tạo. Chi tiết điều kiện và dependency có thể thay đổi giữa các phiên bản; khi nâng cấp Boot, cần kiểm tra cấu hình thực tế và test khởi động.

### 3.1. Cấu hình cơ bản

Ví dụ `application.yaml`:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: app
    liquibase-schema: app_metadata
```

Ý nghĩa:

- `enabled` bật/tắt tích hợp Liquibase trong ứng dụng.
- `change-log` chỉ root changelog được nạp từ classpath.
- `default-schema` chỉ schema mặc định cho các đối tượng database theo cấu hình.
- `liquibase-schema` chỉ schema chứa bảng metadata Liquibase khi được cấu hình riêng.

Tên property và cách hỗ trợ schema phụ thuộc Boot version/DBMS. Nếu không có schema metadata riêng, Liquibase có thể dùng schema mặc định theo cấu hình kết nối. Cần xác nhận bảng `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK` thực tế nằm ở đâu.

Khi Liquibase được bật, giá trị mặc định của `enabled` trong cấu hình auto-configuration thường là true. Có thể đặt false có chủ đích trong môi trường mà migration được thực hiện bởi một job riêng, nhưng chỉ sau khi pipeline đã bảo đảm schema được cập nhật trước khi ứng dụng khởi động.

### 3.2. Không nhầm change-log với file migration cuối cùng

`spring.liquibase.change-log` trỏ đến **root changelog**. Root file có thể include nhiều YAML/XML/JSON hoặc SQL changeset. Ví dụ:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-status-code.yaml
      relativeToChangelogFile: true
```

Nếu root changelog sai đường dẫn, file con không được đóng gói vào artifact hoặc include sai relative path, ứng dụng có thể dừng trong startup trước khi service sẵn sàng. Vì vậy, cần kiểm tra cả cấu trúc resource trong artifact, không chỉ file trên máy developer.

## 4. Các giai đoạn khởi động và lỗi có thể xuất hiện

| Giai đoạn | Công việc | Ví dụ lỗi |
|---|---|---|
| Bind cấu hình | Đọc profile, URL, credentials và Liquibase properties | Thiếu biến môi trường, property sai kiểu |
| Tạo DataSource | Khởi tạo connection pool/driver | Sai URL, thiếu driver, database không truy cập được |
| Tạo SpringLiquibase | Nạp cấu hình changelog | Sai resource path, bean/DataSource không phù hợp |
| Đọc changelog | Parse file và include | YAML/XML sai cấu trúc, file include không tồn tại |
| Đọc metadata | Truy vấn history/lock | Thiếu quyền, sai schema metadata |
| Kiểm tra changeset | Checksum, precondition, filter | Checksum mismatch, precondition HALT |
| Thực thi SQL | Chạy DDL/DML | SQL không hợp lệ, constraint, lock timeout, quyền DDL |
| Hoàn tất context | Tạo bean phụ thuộc và runner | Bean truy cập schema sai, mapping không tương thích |

Một lỗi ở giai đoạn sớm thường khiến các giai đoạn sau không chạy. Ví dụ, nếu Liquibase thất bại trong lúc tạo bean, runner thường không được gọi. Đây là hành vi fail-fast có chủ đích: ứng dụng không nên tuyên bố sẵn sàng khi schema bắt buộc chưa đạt trạng thái mong muốn.

## 5. Hành vi khi migration thất bại

Khi `SpringLiquibase` thực hiện update và Liquibase ném exception, Spring coi quá trình tạo bean thất bại. Lỗi thường được bọc trong exception khởi tạo bean hoặc lỗi refresh application context. Kết quả phổ biến:

- Application context không khởi tạo thành công.
- `ApplicationRunner` và `CommandLineRunner` không được chạy.
- Ứng dụng không chuyển sang trạng thái ready bình thường.
- Tiến trình có thể kết thúc với lỗi khởi động; cách supervisor/container xử lý restart phụ thuộc nền tảng triển khai.
- Log cần được kiểm tra để tìm changeset và câu SQL gây lỗi thực tế.

Không nên cố bắt exception Liquibase rồi bỏ qua để ứng dụng tiếp tục khởi động nếu schema đó là điều kiện bắt buộc. Việc che lỗi có thể tạo một service “sống” về process nhưng không đáp ứng hợp đồng database.

### 5.1. Ví dụ lỗi precondition

Giả sử migration yêu cầu mọi khách hàng có trạng thái hợp lệ trước khi thêm constraint:

```yaml
databaseChangeLog:
  - changeSet:
      id: 030-require-account-status
      author: migration-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer_account
              WHERE status_code IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer_account
            columnName: status_code
            columnDataType: varchar(20)
```

Nếu còn bản ghi NULL, precondition không đạt và Liquibase dừng. Trong Spring Boot, exception này làm bean Liquibase không khởi tạo thành công, kéo theo application context thất bại.

Đây là kết quả đúng nếu ứng dụng yêu cầu cột không NULL. Cần xử lý dữ liệu hoặc quy trình backfill rồi chạy lại theo kế hoạch, không thay `HALT` thành `MARK_RAN` chỉ để service khởi động.

### 5.2. Checksum mismatch cũng có thể chặn startup

Nếu một changeset đã chạy bị sửa, Liquibase có thể báo checksum mismatch trong lúc khởi động. Ứng dụng vì vậy không hoàn tất startup. Cách xử lý là xác định file/commit/artifact đã triển khai, khôi phục changeset lịch sử hoặc tạo changeset mới. Không sửa trực tiếp `MD5SUM` trong `DATABASECHANGELOG` và không mặc định dùng `clear-checksums` để dập lỗi.

## 6. Một lần startup lỗi có thể đã áp dụng một phần migration

Một điểm quan trọng: **thất bại khi khởi động không đồng nghĩa database hoàn toàn không thay đổi**.

Liquibase thường quản lý transaction theo changeset khi DBMS hỗ trợ và changeset được chạy theo cấu hình giao dịch phù hợp. Nhưng:

- Các changeset trước đó đã thành công có thể đã commit và được ghi vào `DATABASECHANGELOG`.
- Changeset gây lỗi có thể được rollback transaction nếu DBMS hỗ trợ và toàn bộ thao tác nằm trong transaction đó.
- Một số DDL của DBMS có implicit commit hoặc không thể rollback như DML thông thường.
- Changeset cấu hình `runInTransaction: false` có thể có hành vi một phần nếu câu SQL giữa chừng lỗi.
- External procedure, script hoặc thao tác ngoài database có thể đã tạo hiệu ứng mà transaction không hoàn tác.

Do đó, sau lỗi phải xác minh **cả schema thực tế và history**, không chỉ đọc dòng cuối log.

### 6.1. Ví dụ chuỗi ba changeset

```text
001 create customer_status       -> thành công, commit
002 add customer.status_code     -> thành công, commit
003 backfill invalid data        -> thất bại
004 add NOT NULL                 -> chưa được chạy
```

Sau lần startup thất bại, database có thể vẫn giữ changeset 001 và 002. Liquibase không nhất thiết tự quay lại trạng thái trước cả chuỗi. Ở lần khởi động sau, nó đối chiếu lịch sử và tiếp tục những changeset còn pending theo cấu hình.

Nếu changeset 003 có tác động một phần hoặc DDL đã commit ngầm, phải điều tra trạng thái thực trước khi retry. Không xóa record 001/002 để cố chạy lại toàn bộ migration.

### 6.2. runInTransaction không phải transaction toàn bộ changelog

`runInTransaction` điều khiển hành vi transaction của changeset theo hỗ trợ của Liquibase/DBMS; mặc định thường là true. Nó không biến toàn bộ changelog thành một transaction lớn. Một thay đổi gồm nhiều changeset có thể đã áp dụng một phần trước khi một changeset sau lỗi.

Với những thao tác không thể chạy an toàn trong transaction (một số loại DDL hoặc lệnh đặc thù), phải hiểu rõ hành vi DBMS, chia changeset hợp lý và thiết kế cách phục hồi. Đừng đặt `runInTransaction: false` chỉ để né lỗi transaction mà không kiểm tra khả năng partial apply.

## 7. Thứ tự phụ thuộc giữa Liquibase, JPA và bean ứng dụng

Ứng dụng có thể dùng đồng thời Liquibase, Hibernate/JPA, Spring Data repository, `JdbcTemplate` hoặc `JdbcClient`, service có truy vấn database trong constructor/`@PostConstruct` và `ApplicationRunner`.

Những thành phần này phải nhìn thấy schema ở trạng thái đúng. Spring Boot có cơ chế database initialization dependency cho nhiều loại bean phổ biến. Với bean tự viết hoặc thư viện không được nhận diện, cần khai báo phụ thuộc rõ ràng nếu nó yêu cầu schema đã khởi tạo.

Ví dụ bean tự tạo cần database:

```java
import org.springframework.boot.sql.init.dependency.DependsOnDatabaseInitialization;
import org.springframework.stereotype.Component;

@Component
@DependsOnDatabaseInitialization
public class CustomerSchemaInspector {

    public CustomerSchemaInspector(CustomerRepository repository) {
        // Bean này chỉ nên khởi tạo sau database initialization.
        // Tránh chạy truy vấn phức tạp trong constructor nếu có thể.
    }
}
```

Annotation và package phụ thuộc phiên bản Spring Boot. Nếu phiên bản đang dùng không cung cấp annotation này, có thể dùng cơ chế dependency bean phù hợp của phiên bản hoặc thiết kế bean không truy vấn database trong constructor.

### 7.1. Tránh query database trong constructor

Constructor nên chủ yếu gán dependency và kiểm tra cấu hình đơn giản. Truy vấn database trong constructor có thể làm thứ tự khởi tạo khó hiểu, gây lỗi khó chẩn đoán và tạo side effect trong lúc context đang được tạo.

Nếu cần kiểm tra dữ liệu khi ứng dụng đã sẵn sàng, hãy dùng một bước startup rõ ràng như runner hoặc application event, đồng thời xác nhận database initialization đã hoàn tất.

### 7.2. Runner không phải công cụ migration

`ApplicationRunner` chạy sau khi context được refresh. Nếu cần tạo bảng/cột, hãy viết changeset Liquibase. Runner phù hợp hơn cho tác vụ ứng dụng sau khi schema sẵn sàng, như kiểm tra trạng thái, warm cache hoặc nạp dữ liệu không thuộc schema migration theo thiết kế riêng.

## 8. Phối hợp Hibernate DDL với Liquibase

Nếu Liquibase là chủ sở hữu schema, không nên để Hibernate đồng thời tự tạo/sửa cấu trúc trong production mà không có chiến lược rõ ràng.

Ví dụ cấu hình thường dùng để yêu cầu Hibernate xác minh mapping với schema hiện có:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Các lựa chọn `ddl-auto` thường gồm `none`, `validate`, `update`, `create` và `create-drop`; hành vi mặc định còn phụ thuộc loại database và cấu hình Boot. Với production, cần chủ động cấu hình thay vì dựa vào default.

Nếu đặt Hibernate `update` và Liquibase cùng thay đổi schema, thứ tự và quyền sở hữu trở nên khó dự đoán. Có thể xuất hiện race condition hoặc schema drift. Nên để một công cụ chịu trách nhiệm migration; Hibernate validate mapping sau khi Liquibase đã hoàn tất.

## 9. Cấu hình nhiều profile và bí mật kết nối

Một ứng dụng có thể dùng các profile khác nhau:

```yaml
# application.yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

```yaml
# application-test.yaml
spring:
  liquibase:
    enabled: true
    contexts: test
```

```yaml
# application-prod.yaml
spring:
  liquibase:
    enabled: true
    contexts: production
```

Tên context phải khớp cách gắn context trong changeset. Nếu không có filter phù hợp, một số changeset có thể được xét theo hành vi mặc định của Liquibase; đừng dùng context như cơ chế duy nhất để bảo vệ dữ liệu production.

Không đặt credentials trong changelog hoặc source code. URL và secret nên lấy từ biến môi trường/secret manager, ví dụ các thuộc tính datasource được bind từ environment:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/app
    username: app_user
    password: external-secret
```

Giá trị trên chỉ minh họa cấu trúc cấu hình; production phải lấy secret từ secret store hoặc biến môi trường. Không in giá trị bí mật trong log startup, lỗi cấu hình hoặc artifact CI/CD.

### 9.1. Tham số Liquibase

Spring Boot hỗ trợ nhiều thuộc tính `spring.liquibase.*` như change-log, enabled, contexts, default-schema, liquibase-schema và parameters; tên và phạm vi chính xác cần đối chiếu với phiên bản Boot. Các tham số có thể được dùng làm property substitution trong changelog. Hãy quản lý chúng theo profile nhưng bảo đảm preview và migration thật dùng cùng giá trị.

## 10. Nhiều DataSource: Liquibase phải dùng đúng database

Ứng dụng có thể có một DataSource cho nghiệp vụ và một DataSource khác cho database metadata hoặc một database riêng. Nếu Liquibase kết nối nhầm, nó có thể chạy migration vào sai database hoặc đọc lịch sử không liên quan.

Spring Boot cung cấp qualifier `@LiquibaseDataSource` cho trường hợp cần chỉ định DataSource riêng dành cho Liquibase. Ví dụ khung cấu hình:

```java
@Bean
@LiquibaseDataSource
DataSource liquibaseDataSource(DataSourceProperties properties) {
    return properties.initializeDataSourceBuilder().build();
}
```

Đây là ví dụ cấu trúc; trong ứng dụng thật, cần cấu hình properties riêng cho DataSource migration và kiểm tra bean nào là `@Primary`, bean nào được Liquibase chọn. Không tạo hai DataSource cùng trỏ một database nhưng khác schema mà không xác định rõ mục đích.

Trước khi startup production, xác minh JDBC URL thực tế của Liquibase, database/catalog/schema, tài khoản và quyền DDL/DML, vị trí bảng `DATABASECHANGELOG`/`DATABASECHANGELOGLOCK`, root changelog và DataSource mà repository/JPA đang sử dụng.

## 11. Nhiều replica cùng khởi động và vai trò của Liquibase lock

Trong Kubernetes hoặc môi trường scale-out, nhiều replica có thể khởi động gần như đồng thời. Nếu mỗi instance đều bật Liquibase, chúng có thể cùng cố chạy migration.

`DATABASECHANGELOGLOCK` giúp điều phối: một tiến trình giữ lock để thực hiện migration, tiến trình khác phải chờ hoặc xử lý theo cơ chế lock của Liquibase. Cơ chế này giảm nguy cơ hai tiến trình Liquibase cùng áp dụng changeset, nhưng không biến việc tất cả replica cùng chạy migration thành kiến trúc triển khai tối ưu.

Các vấn đề có thể gặp:

- Nhiều replica cùng chờ lock, kéo dài thời gian startup.
- Timeout hoặc lỗi kết nối khiến replica khởi động thất bại.
- Một job bị kill có thể để lại lock cần điều tra.
- Các phiên bản ứng dụng cũ và mới chạy đồng thời trong rolling deployment, nên migration phải tương thích với cả hai.
- Một process khác ngoài Liquibase vẫn có thể thay đổi schema; Liquibase lock không điều phối DBA/script không dùng cùng cơ chế.

### 11.1. Một migration job riêng

Ở hệ thống nhiều replica, một lựa chọn là chạy Liquibase trong job riêng trước khi cập nhật ứng dụng:

```text
Deploy pipeline
      |
      v
Migration Job (Liquibase update)
      |
      v
Kiểm tra schema / DATABASECHANGELOG
      |
      v
Cho phép rollout ứng dụng
      |
      v
Các replica khởi động với migration auto-run đã tắt
```

Khi dùng mô hình này, cấu hình ứng dụng có thể đặt `spring.liquibase.enabled: false` ở profile runtime; job migration sử dụng profile hoặc entry point riêng bật Liquibase. **Chỉ tắt Liquibase trong ứng dụng sau khi đã bảo đảm job migration chạy thành công trước rollout.**

### 11.2. Khi nào để ứng dụng tự chạy Liquibase?

Với ứng dụng nhỏ, một instance hoặc môi trường development, auto-run khi startup có thể đơn giản và phù hợp. Nhưng vẫn cần quyền kết nối và quyền migration, kiểm soát thời gian startup, chọn chiến lược nhất quán khi scale nhiều instance, kiểm tra compatibility khi rolling deploy và tránh nhiều pipeline/ứng dụng cùng sở hữu migration.

## 12. Phân loại lỗi và cách xử lý

| Nhóm lỗi | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Cấu hình | Không bind được URL/profile/parameter | Xác nhận active profile và biến môi trường |
| Kết nối | Connection refused, timeout, authentication failed | Kiểm tra network, secret, JDBC URL và quyền |
| Resource | Không tìm thấy root/include changelog | Kiểm tra classpath và nội dung artifact |
| Parse | YAML/XML/SQL format không hợp lệ | Đọc lỗi parser, kiểm tra changelog |
| History | Checksum mismatch, identity khác | Đối chiếu commit, ID/author/path và DATABASECHANGELOG |
| Precondition | HALT do dữ liệu/schema không đạt | Chạy truy vấn kiểm tra và xử lý nguồn dữ liệu |
| SQL/DDL | Syntax error, unsupported change, thiếu quyền | Xem SQL sinh ra, DBMS version và grant |
| Constraint | Duplicate, NULL, orphan hoặc FK fail | Đối soát dữ liệu trước khi thêm constraint |
| Lock | Liquibase chờ lock hoặc báo lock đang giữ | Xác minh tiến trình/session rồi mới release |
| Bean startup | Repository/JPA/service không khởi tạo | Kiểm tra dependency database initialization và schema thực |

Đọc exception gốc và log changeset, không chỉ dòng cuối “Application run failed”. Log cần cho biết database nào, changelog nào, changeset nào và SQL/condition nào gây lỗi, nhưng phải tránh để lộ password hoặc thông tin nhạy cảm.

## 13. Quy trình xử lý sau khi startup migration thất bại

Khi ứng dụng không khởi động được do Liquibase, làm theo thứ tự:

1. **Giữ ứng dụng ở trạng thái không nhận traffic.** Nếu schema chưa đạt, không bỏ qua lỗi để mở readiness.
2. **Xác định đúng database.** Đối chiếu URL, catalog/schema và profile mà tiến trình đã dùng.
3. **Tìm changeset lỗi.** Đọc exception gốc, log Liquibase và SQL liên quan.
4. **Đọc history.** Kiểm tra `DATABASECHANGELOG` xem changeset nào đã được ghi nhận; xác nhận đúng metadata schema/table.
5. **Kiểm tra schema thực tế.** Đối chiếu bảng, cột, index, constraint và dữ liệu; không chỉ dựa vào history.
6. **Xác định mức độ partial apply.** Kiểm tra changeset lỗi có transaction không, DBMS có implicit commit không và có external side effect không.
7. **Sửa nguyên nhân.** Ví dụ bổ sung mapping dữ liệu, cấp đúng quyền, sửa resource path hoặc tạo changeset mới.
8. **Đánh giá retry/repair.** Nếu changeset lỗi chưa được ghi nhận và không có tác động một phần, có thể chạy lại sau khi xác minh. Nếu đã có partial DDL/DML, cần migration bù hoặc phục hồi có kiểm soát.
9. **Kiểm tra lock.** Chỉ dùng release-locks khi xác nhận không còn process migration hợp lệ.
10. **Thử trên database đại diện.** Xác nhận startup thành công và hậu kiểm dữ liệu/schema.
11. **Khởi động lại ứng dụng.** Chỉ mở traffic khi migration và các bean phụ thuộc đều sẵn sàng.

### 13.1. Không xóa record history để retry

Nếu changeset 001 và 002 đã thành công, còn 003 thất bại, không xóa hai record đầu để buộc Liquibase chạy lại toàn bộ. Việc đó có thể gây create table/column trùng và làm metadata sai lệch. Hãy xác định đúng changeset pending và trạng thái thực tế.

### 13.2. Không tự đánh dấu changeset đã chạy

Nếu SQL lỗi, không thêm dòng `DATABASECHANGELOG` hoặc dùng `MARK_RAN` chỉ để Spring Boot qua startup. Chỉ dùng cơ chế đánh dấu/sync khi thay đổi tương ứng đã được áp dụng bên ngoài và đã được đối chiếu đầy đủ với schema/data thực tế, có review và phê duyệt.

### 13.3. Lock không được giải phóng bằng phỏng đoán

Nếu log cho thấy lock đang giữ, xác minh process, session và thời điểm lock trước. Dùng `list-locks`/`release-locks` theo phiên bản hỗ trợ sau khi chắc chắn lock bị bỏ lại. Không cập nhật trực tiếp cột `LOCKED` bằng SQL khi chưa điều tra.

## 14. Thiết kế changeset để startup dễ phục hồi

Một changeset tốt cần có phạm vi rõ, precondition đúng và cách phục hồi được đánh giá.

### 14.1. Tách thay đổi theo giai đoạn

Thay vì một changeset lớn vừa tạo bảng, backfill hàng triệu dòng, thêm FK và xóa cột cũ, có thể tách:

```text
001 EXPAND: thêm cột nullable
002 REFERENCE: tạo/nạp bảng danh mục
003 BACKFILL: điền dữ liệu theo quy tắc
004 VERIFY: kiểm tra số NULL/orphan/invalid
005 CONSTRAIN: thêm NOT NULL/FK
006 CONTRACT: xóa cấu trúc cũ khi đã an toàn
```

Cách chia này giúp biết bước nào thành công và bước nào thất bại. Nó cũng cho phép triển khai ứng dụng chuyển tiếp giữa các giai đoạn.

### 14.2. Precondition để dừng an toàn

Ví dụ kiểm tra dữ liệu trước khi thêm FK:

```yaml
databaseChangeLog:
  - changeSet:
      id: 050-add-customer-status-fk
      author: migration-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer_account c
              WHERE c.status_code IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1
                    FROM account_status s
                    WHERE s.code = c.status_code
                )
      changes:
        - addForeignKeyConstraint:
            constraintName: fk_customer_account_status
            baseTableName: customer_account
            baseColumnNames: status_code
            referencedTableName: account_status
            referencedColumnNames: code
```

Nếu dữ liệu còn mã mồ côi, startup sẽ fail-fast. Đây là cách bảo vệ tính toàn vẹn, miễn là nhóm có quy trình sửa dữ liệu và triển khai lại rõ ràng.

### 14.3. Hạn chế thay đổi không đảo ngược trong startup

Các changeset phá hủy như `dropTable` hoặc `dropColumn` cần được cân nhắc thời điểm. Nếu ứng dụng mới khởi động nhưng một consumer cũ vẫn đang chạy, contract migration có thể làm consumer lỗi. Không gom bước expand và contract vào cùng startup khi hệ thống cần rolling deployment.

## 15. Kiểm thử thứ tự khởi động và lỗi migration

Kiểm thử tích hợp cần dùng DBMS tương ứng với production khi có change phụ thuộc tính năng riêng. H2 không luôn mô phỏng đúng PostgreSQL, MySQL, Oracle hoặc SQL Server.

Một chiến lược kiểm thử:

1. Khởi động application context với database trống và Liquibase bật.
2. Xác nhận các changeset được áp dụng và bảng/cột cần thiết tồn tại.
3. Xác nhận JPA mapping và repository có thể sử dụng schema sau migration.
4. Cố ý tạo dữ liệu làm precondition thất bại trên database test riêng.
5. Khởi động context và xác nhận lỗi migration làm context không sẵn sàng.
6. Kiểm tra changeset trước lỗi đã commit hay chưa và schema thực tế ra sao.
7. Sửa dữ liệu test, chạy lại startup theo quy trình và xác nhận thành công.
8. Kiểm tra cấu hình runtime khi Liquibase bị tắt chỉ dùng trong mô hình migration job riêng.

### 15.1. Ví dụ kiểm tra schema sau startup

Trong integration test, sau khi context đã khởi tạo, có thể dùng JDBC để kiểm tra cột:

```java
@SpringBootTest
class LiquibaseStartupIntegrationTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void migrationCreatesStatusColumn() {
        Integer count = jdbcTemplate.queryForObject(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_name = 'customer_account'
              AND column_name = 'status_code'
            """,
            Integer.class
        );

        assertThat(count).isEqualTo(1);
    }
}
```

Ví dụ dùng cú pháp text block và `information_schema` phù hợp với DBMS hỗ trợ; nếu database có nhiều schema cùng tên bảng, cần thêm điều kiện schema/catalog. Không dùng truy vấn này như test portable cho mọi hệ quản trị.

### 15.2. Kiểm tra fail-fast

Để kiểm thử lỗi startup, có thể tạo một test context với changelog/DB riêng chứa precondition chắc chắn không đạt. Xác nhận context không refresh thành công và runner không được gọi. Không cố tình làm hỏng database dùng chung để kiểm thử.

### 15.3. Kiểm thử lock và thời gian khởi động

Trong môi trường lab, có thể khởi động hai process với cùng database để quan sát lock và thời gian chờ. Không dùng test concurrency này trên production. Ghi lại startup duration, log lock và trạng thái `DATABASECHANGELOGLOCK`.

## 16. CI/CD: chạy migration trước khi rollout ứng dụng

Một pipeline nhiều replica có thể chọn mô hình job migration riêng:

```text
Build application + changelog artifact
                 |
                 v
Validate changelog / update-sql / tests
                 |
                 v
Backup & migration pre-check
                 |
                 v
Run one Liquibase migration job
                 |
                 v
Verify DATABASECHANGELOG + schema + data
                 |
                 v
Deploy application replicas
                 |
                 v
Readiness / smoke tests
                 |
                 v
Complete release
```

Các nguyên tắc:

- Dùng đúng artifact changelog đã được review.
- Migration job và application phải cùng hiểu phiên bản schema dự kiến.
- Job phải có timeout, log và quyền migration riêng.
- Chỉ rollout app sau khi job thành công và hậu kiểm đạt.
- Nếu job thất bại, dừng rollout; điều tra trạng thái database trước khi retry.
- Với rolling deployment, changeset phải tương thích cả phiên bản app đang chạy và phiên bản sắp triển khai.
- Không để mỗi replica tự chạy cùng một chuỗi migration nếu kiến trúc đã chọn job tập trung.

Trong mô hình job riêng, ứng dụng có thể dùng `spring.liquibase.enabled=false` ở profile runtime. Nhưng cần kiểm tra deployment dependency để không có tình huống application rollout chạy trước migration job.

### 16.1. Khi nào dùng auto-run khi startup?

Auto-run phù hợp khi quy mô đơn giản, một instance hoặc nhóm chấp nhận startup chịu trách nhiệm migration. Job riêng thường phù hợp hơn khi có nhiều replica, migration dài hoặc cần phê duyệt, cần kiểm tra dữ liệu giữa các giai đoạn, dùng nhiều service cùng chia sẻ database, cần tách quyền DDL khỏi tài khoản runtime hoặc cần kiểm soát thứ tự giữa nhiều deployment.

Không có một lựa chọn đúng cho mọi kiến trúc. Điều quan trọng là một database phải có **một quy trình sở hữu migration rõ ràng**, cùng một bộ artifact và history có thể truy vết.

## 17. Những tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| App không khởi động sau deploy | Liquibase changeset lỗi hoặc precondition HALT | Tìm changeset lỗi, kiểm tra history/schema và sửa nguyên nhân |
| Repository báo thiếu bảng/cột | Bean truy vấn trước initialization hoặc migration không chạy đúng DB | Kiểm tra DataSource, bean dependency và changelog |
| Startup kéo dài ở nhiều replica | Nhiều instance cùng chạy Liquibase và chờ lock | Dùng migration job tập trung hoặc điều phối startup |
| Checksum mismatch sau release | Changeset đã chạy bị sửa hoặc artifact không nhất quán | Đối chiếu commit/artifact, giữ changeset lịch sử và tạo migration mới |
| Bảng metadata không tồn tại | Sai database/schema hoặc thiếu quyền tạo metadata | Xác minh URL, schema và quyền Liquibase |
| Migration dừng vì NULL/duplicate | Dữ liệu cũ không đạt constraint mới | Backfill, xử lý duplicate và đối soát trước khi thêm constraint |
| Retry startup vẫn thất bại | Changeset trước đã commit hoặc changeset lỗi để lại partial effect | Kiểm tra DB thật và thiết kế repair/migration bù |
| Lock còn sau process crash | Tiến trình bị kill hoặc lock bị bỏ lại | Kiểm tra process/session rồi dùng release-locks khi an toàn |
| Hibernate tự thay đổi schema | ddl-auto không phù hợp với Liquibase | Chọn một chủ thể migration, thường để Hibernate validate |
| Ứng dụng khởi động dù migration chưa chạy | Liquibase bị tắt nhưng pipeline không chạy job trước | Sửa thứ tự deployment và readiness gate |

## 18. Bài thực hành: mô phỏng startup thành công và thất bại

**Bối cảnh:** ứng dụng Spring Boot dùng PostgreSQL, Liquibase tạo bảng `customer_account` và thêm cột `status_code`. Repository cần cột này ngay khi ứng dụng hoạt động.

### Bước 1. Cấu hình startup

- Thêm Liquibase dependency.
- Khai báo `spring.liquibase.change-log` tới root changelog.
- Cấu hình DataSource qua biến môi trường.
- Để Hibernate ở chế độ validate hoặc none theo chính sách dự án.
- Chuẩn bị database lab trống.

### Bước 2. Khởi động thành công

Chạy ứng dụng và quan sát log: DataSource được tạo; Liquibase nạp changelog và lấy lock; changeset pending được thực thi; `DATABASECHANGELOG` được cập nhật; context hoàn tất, runner được gọi và ứng dụng ready.

Kiểm tra cột `status_code` trong database và thử repository.

### Bước 3. Tạo lỗi có kiểm soát

Trên database test riêng, thêm dữ liệu làm precondition fail (ví dụ `status_code IS NULL` trước khi yêu cầu NOT NULL). Khởi động lại với changeset siết ràng buộc.

Kỳ vọng Liquibase dừng tại precondition, bean Liquibase không khởi tạo thành công, application context không refresh thành công, runner không chạy và ứng dụng không báo ready. Các changeset trước đó có thể vẫn được giữ nếu đã commit.

### Bước 4. Điều tra trạng thái

Đọc log, `DATABASECHANGELOG`, schema và dữ liệu. Xác định changeset nào đã áp dụng, changeset nào pending và có partial effect hay không. Không xóa lịch sử để retry.

### Bước 5. Sửa và khởi động lại

Sửa dữ liệu test theo mapping đã duyệt, chạy lại startup. Xác nhận migration hoàn tất, repository hoạt động và application ready.

### Bước 6. Mô phỏng nhiều replica

Khởi chạy hai process lab cùng database. Quan sát `DATABASECHANGELOGLOCK`, thời gian chờ và hành vi khi một process đang chạy migration. Sau đó thiết kế job migration riêng và so sánh.

**Tiêu chí hoàn thành:** giải thích được thứ tự DataSource → Liquibase → bean phụ thuộc → runner; chứng minh migration lỗi làm startup fail-fast; biết kiểm tra partial apply và triển khai lại an toàn.

## 19. Checklist vận hành Spring Boot + Liquibase

- [ ] Đã xác nhận phiên bản Spring Boot, Liquibase, JDBC driver và DBMS.
- [ ] `spring.liquibase.change-log` trỏ đúng root changelog có trong artifact.
- [ ] DataSource Liquibase trỏ đúng database/catalog/schema và có quyền phù hợp.
- [ ] Bảng `DATABASECHANGELOG`/`DATABASECHANGELOGLOCK` nằm đúng schema metadata.
- [ ] Bean cần database được sắp xếp sau initialization; bean tùy chỉnh có dependency rõ ràng.
- [ ] Không query database trong constructor nếu có thể tránh.
- [ ] Hibernate không đồng thời tự quản lý schema ngoài chiến lược đã thống nhất.
- [ ] Precondition và checksum được kiểm tra; lỗi migration không bị nuốt để app tiếp tục ready.
- [ ] Có quy trình xác minh partial apply sau startup failure.
- [ ] Không xóa/sửa history thủ công để retry.
- [ ] Lock chỉ được release sau khi xác nhận không còn process migration hợp lệ.
- [ ] Nhiều replica có một chiến lược sở hữu migration rõ ràng.
- [ ] Nếu tắt Liquibase ở app runtime, migration job chạy thành công trước rollout.
- [ ] Test startup thành công và fail-fast trên DBMS đại diện.
- [ ] Readiness chỉ đạt sau khi schema và bean ứng dụng đã sẵn sàng.
- [ ] Log có đủ thông tin chẩn đoán nhưng không lộ credentials/secret.
- [ ] Có backup, migration bù hoặc phương án phục hồi phù hợp với thay đổi không đảo ngược.

**Kết luận:** Spring Boot thường thực hiện Liquibase trong giai đoạn khởi tạo application context thông qua bean `SpringLiquibase`. Vì vậy, migration hoàn tất trước khi các bean phụ thuộc database và runner sử dụng schema. Nếu migration thất bại, startup thường dừng; tuy nhiên những changeset trước đó có thể đã commit, nên phải kiểm tra history và schema thực tế trước khi retry. Với hệ thống nhiều replica, hãy thống nhất một chủ thể sở hữu migration, kiểm soát lock và chỉ cho ứng dụng nhận traffic sau khi database đã đạt trạng thái yêu cầu.

