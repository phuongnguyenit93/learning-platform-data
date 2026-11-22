# Dùng DataSource ứng dụng hoặc kết nối migration riêng

Khi tích hợp Liquibase vào Spring Boot, một quyết định quan trọng là **Liquibase sẽ dùng chính DataSource của ứng dụng hay một kết nối database riêng dành cho migration?** Cả hai cách đều hợp lệ, nhưng tạo ra ranh giới quyền hạn và vận hành khác nhau. Dùng chung giúp cấu hình đơn giản; kết nối riêng giúp tách quyền DDL khỏi tài khoản runtime, kiểm soát credential và điều phối triển khai rõ ràng hơn.

Bài học thuộc chương **Spring Boot** của module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`. Module hướng tới quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào cách Spring Boot cung cấp DataSource cho Liquibase, cách cấu hình kết nối migration riêng, cách chọn bean khi có nhiều DataSource và cách tránh chạy migration bằng nhầm tài khoản hoặc nhầm database.

## 1. Hai mô hình kết nối

Spring Boot có thể tự cấu hình Liquibase khi dependency phù hợp có mặt, Liquibase được bật và có một DataSource hợp lệ. Nếu không khai báo kết nối riêng, Liquibase thường sử dụng DataSource chính của ứng dụng. Nếu khai báo kết nối migration riêng hoặc cung cấp bean được đánh dấu dành cho Liquibase, Liquibase có thể sử dụng kết nối đó.

### 1.1. Dùng chung DataSource ứng dụng

~~~text
Spring Boot
    |
    v
Application DataSource
    |----------------------|
    v                      v
Liquibase               JDBC/JPA application
    |                      |
    v                      v
DATABASECHANGELOG       SELECT / INSERT / UPDATE
DDL migration           business queries
~~~

Một DataSource và một bộ credential được dùng cho cả migration lẫn truy cập nghiệp vụ. Tài khoản này cần có đủ quyền DDL mà changelog yêu cầu, đồng thời có quyền DML cần cho ứng dụng.

Ưu điểm:

- Ít cấu hình và ít bean hơn.
- Không cần quản lý hai bộ credential hoặc hai pool kết nối.
- Phù hợp môi trường phát triển, test hoặc ứng dụng nhỏ có mô hình quyền đơn giản.
- Giảm nguy cơ hai URL trỏ nhầm database khi chỉ có một cấu hình kết nối.

Đánh đổi:

- Tài khoản runtime có thể phải giữ quyền CREATE, ALTER, DROP hoặc quyền quản trị schema rộng.
- Nếu credential ứng dụng bị lộ, phạm vi tác động có thể bao gồm cả schema.
- Khó phân biệt thao tác nghiệp vụ và thao tác migration trong audit theo database user.
- Khó áp dụng nguyên tắc least privilege cho service runtime.

### 1.2. Dùng DataSource riêng cho Liquibase

~~~text
Spring Boot
    |-----------------------------|
    v                             v
Application DataSource       Liquibase DataSource
    |                             |
    v                             v
Runtime DB role              Migration DB role
    |                             |
    v                             v
JDBC/JPA business             DATABASECHANGELOG
SELECT / INSERT / UPDATE      DDL / migration
~~~

Hai DataSource có thể trỏ đến **cùng một database và schema**, nhưng dùng user/role khác nhau:

- DataSource ứng dụng dùng tài khoản runtime với quyền cần thiết cho truy vấn và ghi dữ liệu nghiệp vụ.
- DataSource Liquibase dùng tài khoản migration có quyền DDL và quyền đọc/ghi các bảng metadata Liquibase.

Ưu điểm:

- Tách quyền triển khai schema khỏi quyền chạy ứng dụng.
- Có thể dùng credential migration chỉ được cấp trong giai đoạn khởi động hoặc deploy.
- Audit database dễ nhận diện thao tác từ role migration.
- Có thể áp dụng chính sách mạng, secret, pool và timeout khác nhau.

Đánh đổi:

- Cần quản lý hai URL, hai bộ credential và hai cấu hình.
- Phải bảo đảm cả hai kết nối trỏ tới đúng database/schema mục tiêu.
- Tăng số thành phần cần kiểm tra khi khởi động và xử lý sự cố.
- Nếu dùng nhiều DataSource bean tự cấu hình, cần xác định rõ bean nào dành cho Liquibase, bean nào là primary cho JDBC/JPA.

## 2. Cách Spring Boot chọn DataSource cho Liquibase

Trong cấu hình Spring Boot thông dụng, có ba trường hợp:

1. **Có bean `@LiquibaseDataSource`:** bean được đánh dấu rõ ràng dành cho Liquibase.
2. **Có cấu hình kết nối riêng `spring.liquibase.url` cùng thông tin đăng nhập cần thiết:** Boot có thể tạo DataSource riêng cho Liquibase.
3. **Không có cấu hình/bean riêng:** Liquibase thường dùng DataSource chính của ứng dụng.

Chi tiết điều kiện và thứ tự ưu tiên có thể thay đổi theo phiên bản Spring Boot và cấu hình bean tùy chỉnh. Khi ứng dụng khai báo nhiều DataSource, cần kiểm tra auto-configuration report hoặc log startup của đúng phiên bản, và xác minh database/user thực tế mà Liquibase kết nối.

**Không nên cấu hình nhiều cơ chế cùng lúc mà không có chủ đích.** Hãy chọn một cách cấp DataSource riêng: dùng `spring.liquibase.url` để Boot tạo kết nối, hoặc cung cấp bean `@LiquibaseDataSource` khi cần cấu hình Java/pool chuyên biệt.

## 3. Cấu hình đơn giản: dùng chung DataSource

Ví dụ `application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/customer_db
    username: customer_app
    password: ${CUSTOMER_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Trong cấu hình này:

- Liquibase không có URL/user/password riêng.
- Spring Boot dùng DataSource chính đã cấu hình ở `spring.datasource` theo cơ chế auto-configuration.
- Tài khoản `customer_app` phải có quyền thực thi mọi changeset cần chạy và cập nhật history/lock table.
- JDBC/JPA cũng dùng DataSource ứng dụng.

Ví dụ phù hợp cho môi trường local hoặc integration test. Nếu dùng trên production, hãy đánh giá kỹ việc cấp quyền DDL cho tài khoản runtime. Không cấp quyền quản trị database chỉ để migration chạy qua một lỗi permission.

### 3.1. Phân biệt tên property

| Property | Ý nghĩa |
|---|---|
| `spring.datasource.url` | URL của DataSource ứng dụng. |
| `spring.datasource.username` / `password` | Credential của DataSource ứng dụng. |
| `spring.liquibase.change-log` | Changelog gốc Liquibase cần nạp. |
| `spring.liquibase.enabled` | Bật/tắt Liquibase auto-configuration. |
| `spring.liquibase.url` | URL kết nối riêng cho Liquibase khi cấu hình theo cách này. |
| `spring.liquibase.user` / `password` | Credential riêng của Liquibase. |

Tên property và binding có thể khác nếu dự án dùng phiên bản Spring Boot rất cũ hoặc tự viết cấu hình. Hãy đối chiếu metadata/configuration reference của phiên bản đang dùng.

## 4. Cấu hình kết nối migration riêng bằng properties

Đây là cách trực tiếp khi muốn dùng hai bộ credential mà không cần tự khai báo DataSource bean.

Ví dụ `application.yml`:

~~~yaml
spring:
  datasource:
    url: ${APP_DB_URL}
    username: ${APP_DB_USERNAME}
    password: ${APP_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    url: ${MIGRATION_DB_URL}
    user: ${MIGRATION_DB_USERNAME}
    password: ${MIGRATION_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
~~~

Trong đó:

- `APP_DB_URL` và credential ứng dụng được dùng cho JDBC/JPA.
- `MIGRATION_DB_URL` và credential migration được dùng để Liquibase thực hiện changeset.
- Hai URL thường cùng trỏ đến database cần quản lý; nếu khác database, đó phải là quyết định kiến trúc rõ ràng và cần xác minh rất kỹ.
- Driver phải có mặt trên classpath và tương thích với database đích.

Ví dụ giá trị biến môi trường không được hard-code trong repository. Mỗi môi trường nên lấy secret từ secret manager hoặc cơ chế quản lý bí mật của nền tảng triển khai.

### 4.1. Hai URL cần cùng mục tiêu nghiệp vụ

Một lỗi nguy hiểm là ứng dụng đọc/ghi database A nhưng Liquibase chạy migration trên database B. Ứng dụng có thể khởi động thành công nếu database A đã có schema, trong khi changeset lại được ghi vào history của B.

Hãy kiểm tra:

- Host, port, database/catalog và schema của cả hai URL.
- Có proxy, read replica hoặc endpoint chỉ đọc trong một URL không.
- Default schema của mỗi user có giống nhau không.
- Liquibase metadata table được đặt ở schema nào.
- Môi trường/profile có override URL hay credential không.

Có thể dùng tên database và user trong log startup đã được làm sạch bí mật, hoặc một health/diagnostic check nội bộ để xác nhận đích kết nối. Không log password hoặc toàn bộ JDBC URL nếu URL chứa thông tin nhạy cảm.

## 5. Cấp bean `@LiquibaseDataSource` khi cần kiểm soát sâu hơn

Khi cần cấu hình DataSource bằng Java, pool riêng, secret binding hoặc lựa chọn datasource theo logic ứng dụng, có thể cung cấp một bean được đánh dấu `@LiquibaseDataSource`.

Ví dụ cấu hình dùng `DataSourceProperties` và HikariCP:

~~~java
package com.example.config;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.autoconfigure.liquibase.LiquibaseDataSource;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LiquibaseDataSourceConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource.liquibase")
    DataSourceProperties liquibaseDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @LiquibaseDataSource
    @ConfigurationProperties("app.datasource.liquibase.configuration")
    HikariDataSource liquibaseDataSource(
            @Qualifier("liquibaseDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
~~~

Ví dụ `application.yml` tương ứng:

~~~yaml
app:
  datasource:
    liquibase:
      url: ${MIGRATION_DB_URL}
      username: ${MIGRATION_DB_USERNAME}
      password: ${MIGRATION_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        pool-name: liquibase-pool
        maximum-pool-size: 1
        minimum-idle: 0
        connection-timeout: 10000
~~~

`DataSourceProperties` giúp chuyển property `url` sang thuộc tính kết nối phù hợp khi khởi tạo Hikari. Phần `configuration` được bind vào HikariCP. Nếu dự án dùng pool khác, cần thay type và property tương ứng.

Lưu ý:

- Cần có dependency HikariCP và driver phù hợp.
- Bean `@LiquibaseDataSource` phải được Spring tạo trước khi Liquibase auto-configuration cần dùng nó.
- Khi có nhiều DataSource, DataSource ứng dụng thường cần được đánh dấu `@Primary` hoặc được cấu hình rõ để JDBC/JPA chọn đúng.
- Không đánh dấu DataSource runtime là `@LiquibaseDataSource` nếu mục tiêu là tách quyền.
- Tránh vừa khai báo bean chuyên biệt vừa đặt `spring.liquibase.url` theo một cách gây mơ hồ; chọn một nguồn cấu hình và xác minh bean thực tế.

Đây là ví dụ cho Spring Boot có annotation `@LiquibaseDataSource`; import/package và điều kiện auto-configuration cần được kiểm tra theo phiên bản Spring Boot của dự án.

## 6. DataSource ứng dụng phải được chọn đúng khi có nhiều bean

Khi tự cấu hình nhiều DataSource, Spring Boot không thể luôn suy ra bean nào là nguồn mặc định cho mọi tích hợp. JPA, `JdbcTemplate`, repository và Liquibase có thể có yêu cầu qualifier khác nhau.

Một cấu hình nhiều DataSource nên thể hiện rõ:

| Bean | Vai trò | Cách đánh dấu thường gặp |
|---|---|---|
| Application DataSource | Kết nối runtime cho JDBC/JPA. | `@Primary` nếu là datasource chính. |
| Liquibase DataSource | Kết nối migration. | `@LiquibaseDataSource`. |
| Reporting/readonly DataSource | Kết nối đọc hoặc tác vụ riêng. | `@Qualifier` riêng, không dùng làm primary nếu không chủ ý. |

Không nên đặt tên bean chung chung rồi hy vọng auto-configuration chọn đúng. Tên bean, qualifier và cấu hình transaction manager cần được kiểm tra trong application context.

### 6.1. Không dùng nhầm transaction manager

Ứng dụng có thể có nhiều DataSource và nhiều transaction manager. Một transaction manager gắn với DataSource runtime không tự quản lý transaction trên DataSource migration riêng.

Liquibase có cơ chế thực thi migration và quản lý transaction riêng theo changeset/DBMS. Annotation `@Transactional` của service không bao bọc toàn bộ Liquibase startup migration. Tương tự, không nên giả định một transaction nghiệp vụ sẽ rollback được DDL Liquibase đã commit.

Khi cấu hình transaction manager tùy chỉnh, hãy chỉ định rõ DataSource mà nó quản lý. Tránh gắn nhầm `JdbcTemplate`, JPA EntityManagerFactory hoặc transaction manager sang migration DataSource.

## 7. Phân quyền cho hai kết nối

Tách DataSource chỉ có ý nghĩa khi database role cũng được cấp quyền khác nhau.

| Quyền | Runtime role | Migration role |
|---|---|---|
| SELECT dữ liệu ứng dụng | Có theo nhu cầu. | Chỉ khi changeset cần đọc dữ liệu. |
| INSERT/UPDATE/DELETE nghiệp vụ | Có theo nhu cầu. | Chỉ khi migration cần backfill hoặc seed. |
| CREATE/ALTER/DROP object | Không nên có mặc định. | Có trong phạm vi schema cần quản lý. |
| Đọc/ghi `DATABASECHANGELOG` | Thường không cần. | Cần. |
| Đọc/ghi `DATABASECHANGELOGLOCK` | Thường không cần. | Cần theo cơ chế Liquibase. |
| Tạo role/user hoặc quản trị server | Không. | Không nên có nếu migration không cần. |

Ví dụ tư duy phân quyền:

~~~text
customer_runtime
  - SELECT / INSERT / UPDATE / DELETE trên object nghiệp vụ cần dùng
  - Không có quyền ALTER/DROP schema

customer_migrator
  - Quyền DDL trong schema customer
  - Quyền đọc/ghi bảng Liquibase history và lock
  - Không có quyền quản trị server nếu không cần
~~~

Tên role và quyền cụ thể tùy DBMS. PostgreSQL, MySQL, Oracle và SQL Server có mô hình schema, owner và grant khác nhau. Tài khoản migration cần quyền cho **mọi change thực tế** và cho metadata Liquibase; chỉ cấp `CREATE TABLE` có thể chưa đủ nếu changelog tạo sequence, index, trigger, function hoặc constraint.

### 7.1. Không dùng tài khoản superuser làm giải pháp mặc định

Nếu migration thất bại do thiếu quyền, hãy xác định object và quyền cụ thể bị thiếu. Cấp superuser hoặc DBA toàn database cho ứng dụng chỉ để tránh lỗi tạm thời làm tăng phạm vi thiệt hại khi credential bị lộ hoặc ứng dụng có lỗ hổng.

## 8. Schema của object nghiệp vụ và schema metadata Liquibase

Khi dùng kết nối riêng, cần phân biệt:

- **Default schema:** schema mặc định cho các object mà changeset tạo nếu không chỉ định schema riêng.
- **Liquibase schema:** schema chứa bảng quản lý như `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`, nếu được cấu hình tách.

Spring Boot có các property Liquibase liên quan như `spring.liquibase.default-schema` và `spring.liquibase.liquibase-schema` trong những phiên bản hỗ trợ. Hãy xác minh đúng property và hành vi theo version đang dùng.

Ví dụ minh họa:

~~~yaml
spring:
  liquibase:
    default-schema: customer
    liquibase-schema: database_admin
~~~

Trong cấu hình này, changeset có thể tạo object mặc định trong schema `customer`, trong khi metadata Liquibase nằm ở `database_admin`, tùy cấu hình DBMS và phiên bản. Migration role phải có quyền tương ứng trên cả hai schema. Không đặt `liquibase-schema` sang một schema mà user migration không thể tạo/đọc/ghi history.

Nếu hai DataSource trỏ cùng database nhưng có default schema khác nhau, câu SQL không chỉ rõ schema có thể tác động nhầm object. Ưu tiên chỉ định `schemaName`/catalog phù hợp trong changeset khi cần và kiểm tra SQL preview trên đúng kết nối.

## 9. Vòng đời startup của Spring Boot

Khi Liquibase auto-configuration được bật, Spring Boot tạo và chạy Liquibase trong quá trình khởi động ứng dụng. Migration thường được hoàn tất trước khi những bean phụ thuộc vào schema được khởi tạo hoặc ứng dụng sẵn sàng phục vụ traffic; thứ tự chi tiết phụ thuộc auto-configuration và dependency bean.

~~~mermaid
flowchart TD
    A[Spring Boot bắt đầu khởi động] --> B[Tạo application DataSource]
    B --> C{Có Liquibase DataSource riêng?}
    C -->|Có| D[Tạo/chọn migration DataSource]
    C -->|Không| E[Dùng primary application DataSource]
    D --> F[Liquibase đọc changelog và history]
    E --> F
    F --> G[Kiểm tra lock, filter và changeset]
    G --> H[Thực thi migration cần thiết]
    H --> I[Hoàn tất Liquibase initialization]
    I --> J[Khởi tạo các bean ứng dụng phụ thuộc schema]
    J --> K[Ứng dụng sẵn sàng]
~~~

Nếu migration thất bại, startup thường thất bại theo mặc định vì schema chưa được bảo đảm ở trạng thái mà ứng dụng mong đợi. Không tắt Liquibase để làm ứng dụng khởi động qua lỗi nếu chưa có kế hoạch xác minh schema và triển khai riêng.

### 9.1. Migration khi nhiều instance khởi động

Nếu nhiều instance Spring Boot khởi động cùng lúc, mỗi instance có thể khởi tạo Liquibase. Bảng `DATABASECHANGELOGLOCK` giúp điều phối việc cập nhật changelog trên cùng database. Tuy nhiên:

- Lock không thay thế kế hoạch phát hành hoặc dependency giữa service.
- Lock không chặn mọi truy vấn ghi nghiệp vụ.
- Instance chờ có thể timeout nếu migration khác giữ lock lâu.
- Nếu migration lỗi sau DDL tự commit, lần thử sau có thể gặp object đã tồn tại nhưng history chưa ghi thành công.

Với production, nhiều hệ thống chọn chạy migration ở một bước pipeline riêng rồi khởi động nhiều instance ứng dụng sau khi schema đạt trạng thái yêu cầu. Nếu vẫn bật Liquibase khi startup, cần hiểu và kiểm thử hành vi cạnh tranh/lock của phiên bản đang dùng.

## 10. Chọn chạy Liquibase lúc startup hay từ pipeline?

Tách DataSource không tự quyết định thời điểm migration. Có thể dùng connection riêng nhưng vẫn chạy Liquibase trong Spring Boot startup; cũng có thể dùng CLI/pipeline với credential migration.

| Mô hình | Ưu điểm | Điều cần quản lý |
|---|---|---|
| Startup với cùng DataSource | Đơn giản, ít cấu hình. | Runtime credential cần DDL; nhiều instance có thể cùng khởi tạo Liquibase. |
| Startup với DataSource riêng | Tách quyền runtime/migration mà vẫn giữ migration gắn với app startup. | Secret migration phải có khi ứng dụng khởi động; kiểm soát pool/lock và lỗi startup. |
| Pipeline/CLI trước khi khởi động app | Tách rõ deploy schema và deploy binary; dễ phê duyệt SQL. | Phải khóa version/artifact, URL, filter và trình tự giữa migration với ứng dụng. |

Một quy trình production có thể:

1. Build artifact ứng dụng và changelog bất biến.
2. Pipeline migration dùng credential riêng để chạy `validate`, `status`, SQL preview và `update`.
3. Kiểm tra history/schema sau update.
4. Triển khai ứng dụng với runtime credential không có DDL.
5. Smoke test và giám sát.

Nếu pipeline đã chạy migration, có thể cấu hình `spring.liquibase.enabled=false` cho bước chạy ứng dụng **chỉ khi** quy trình deploy bảo đảm migration đã hoàn tất trước và có kiểm tra trạng thái. Không tắt tùy tiện ở mọi profile vì database mới hoặc môi trường test có thể dựa vào Liquibase startup để dựng schema.

## 11. Cấu hình theo profile và quản lý secret

Local có thể dùng chung DataSource để đơn giản; production nên dùng role tách biệt. Có thể đặt cấu hình nền trong `application.yml`, sau đó override kết nối theo profile hoặc biến môi trường.

Ví dụ cấu hình khái quát:

~~~yaml
spring:
  datasource:
    url: ${APP_DB_URL}
    username: ${APP_DB_USERNAME}
    password: ${APP_DB_PASSWORD}

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    url: ${MIGRATION_DB_URL:${APP_DB_URL}}
    user: ${MIGRATION_DB_USERNAME:${APP_DB_USERNAME}}
    password: ${MIGRATION_DB_PASSWORD:${APP_DB_PASSWORD}}
~~~

Ví dụ cho phép local fallback về credential ứng dụng nếu biến migration chưa đặt; production nên **bắt buộc** biến migration riêng bằng secret policy hoặc cấu hình profile rõ ràng, tránh vô tình fallback sang tài khoản runtime có quyền không phù hợp hoặc ngược lại.

Không commit `.env` chứa password thật. Không in resolved configuration trong log. Cần có quy trình xoay vòng secret và thu hồi credential migration sau khi không còn cần thiết.

### 11.1. Tránh cấu hình sai giữa profile

Một số lỗi thường gặp:

- `application-prod.yml` override `spring.datasource.url` nhưng quên override `spring.liquibase.url`.
- Liquibase dùng secret staging trong khi ứng dụng dùng database production.
- Migration user có quyền trên schema A nhưng `default-schema` lại là B.
- Test profile tắt Liquibase nhưng không có bước tạo schema khác.
- Production dùng `spring.liquibase.enabled=false` trong khi pipeline migration chưa chạy.

Nên kiểm tra cấu hình đã resolve bằng cách log **chỉ thông tin không nhạy cảm** như environment, database name, schema và user name đã được làm sạch; không log password/token.

## 12. Kiểm thử hai DataSource trong Spring Boot

Một integration test có hai mục tiêu độc lập:

1. Xác minh Liquibase thực sự dùng migration DataSource.
2. Xác minh ứng dụng runtime vẫn dùng application DataSource với quyền giới hạn.

### 12.1. Kiểm thử lựa chọn DataSource

Trong test context:

- Cung cấp hai database/user riêng hoặc hai datasource có thể nhận diện được.
- Đảm bảo application DataSource được inject vào `JdbcTemplate`/JPA.
- Đảm bảo Liquibase nhận bean `@LiquibaseDataSource` hoặc cấu hình `spring.liquibase.url` đúng.
- Kiểm tra `DATABASECHANGELOG` được tạo/ghi trong database đích dự kiến.
- Kiểm tra một truy vấn ứng dụng đi qua runtime datasource.

Không chỉ assert application context khởi động thành công. Nếu cả hai URL vô tình trỏ cùng database và cùng user, test có thể không phát hiện nhầm bean.

### 12.2. Kiểm thử quyền

Có thể dùng hai role test:

- Runtime role đọc/ghi bảng nghiệp vụ nhưng thử `CREATE TABLE` phải bị từ chối.
- Migration role có quyền chạy một changeset thử và cập nhật history.

Kiểm tra quyền thực tế trên DBMS, không chỉ dựa vào tên role hoặc cấu hình Spring. Một số quyền được kế thừa qua role group hoặc default grant.

### 12.3. Test với database thật qua Testcontainers

Testcontainers có thể khởi chạy PostgreSQL/MySQL/DBMS phù hợp để kiểm tra SQL và quyền gần thực tế. Khi dùng container:

- Tạo database và role test tương ứng.
- Chạy Liquibase trên migration DataSource.
- Khởi tạo application DataSource bằng runtime role.
- Xác minh schema/history, sau đó thực hiện thao tác CRUD qua ứng dụng.
- Tạo test migration thất bại để xác nhận ứng dụng không coi schema chưa hoàn tất là sẵn sàng.

H2 hoặc database giả lập có thể hữu ích cho logic đơn giản nhưng không thay thế kiểm thử trên DBMS production, đặc biệt với DDL native, lock, sequence, trigger và transaction.

## 13. Những lỗi thường gặp khi dùng DataSource riêng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Liquibase báo thiếu quyền CREATE/ALTER | Migration URL đang dùng runtime credential hoặc role thiếu grant. | Kiểm tra user thực tế và cấp quyền đúng schema/object. |
| Ứng dụng chạy query nhưng migration báo table not found | Liquibase và ứng dụng trỏ khác database/schema. | So sánh URL, catalog, default schema và profile. |
| `DATABASECHANGELOG` nằm ở schema lạ | `liquibase-schema` hoặc default schema không đúng. | Kiểm tra property và grant cho migration role. |
| Có hai DataSource nhưng JPA chọn nhầm | Thiếu `@Primary`, `@Qualifier` hoặc cấu hình EntityManagerFactory. | Gắn bean và transaction manager rõ ràng. |
| Liquibase không dùng bean tùy chỉnh | Bean thiếu `@LiquibaseDataSource`, sai package/import hoặc auto-config khác. | Kiểm tra bean context và auto-configuration report. |
| Startup chờ lâu hoặc timeout lock | Instance khác đang giữ `DATABASECHANGELOGLOCK`, migration lâu. | Kiểm tra tiến trình, lock và timeout; không tự giải phóng khi chưa điều tra. |
| Migration chạy vào DB khác | `spring.liquibase.url` bị override sai profile. | Kiểm tra cấu hình đã resolve và database identity. |
| Migration thành công nhưng runtime không đọc được bảng | Runtime role thiếu USAGE/SELECT hoặc grant cho object mới chưa có. | Cấp quyền runtime/default privileges theo policy. |
| Runtime có thể ALTER TABLE dù muốn tách quyền | Cả hai DataSource dùng chung user hoặc role runtime kế thừa quyền DDL. | Kiểm tra grants và credential thực tế. |
| Test pass nhưng production lỗi | H2/DBMS khác, quyền test quá rộng hoặc profile không giống. | Test trên DBMS tương ứng và role có quyền giống production. |

## 14. Bài thực hành có kiểm chứng

**Bối cảnh:** một ứng dụng Spring Boot dùng PostgreSQL. Runtime chỉ được đọc/ghi dữ liệu khách hàng; Liquibase cần tạo bảng và index.

### Giai đoạn A — Dùng chung DataSource

1. Cấu hình `spring.datasource` với một user test có cả DML và quyền DDL trong schema thử.
2. Bật `spring.liquibase.enabled` và chỉ định changelog.
3. Khởi động ứng dụng, xác minh bảng nghiệp vụ và `DATABASECHANGELOG` được tạo.
4. Thực hiện một truy vấn CRUD qua JDBC/JPA.
5. Ghi nhận quyền của user đang được dùng cho cả hai thao tác.

### Giai đoạn B — Tách kết nối migration

1. Tạo runtime role chỉ có quyền DML cần thiết.
2. Tạo migration role có quyền DDL trong schema và quyền history/lock.
3. Cấu hình `spring.datasource` bằng runtime credential.
4. Cấu hình `spring.liquibase.url`, `user`, `password` bằng migration credential.
5. Khởi động ứng dụng và xác minh changeset được ghi trong database đích.
6. Thử tạo bảng bằng runtime role; thao tác DDL phải bị từ chối.
7. Thử CRUD qua ứng dụng; runtime vẫn hoạt động theo quyền được cấp.

### Giai đoạn C — Kiểm tra sai cấu hình

Trên database thử nghiệm:

1. Cố tình đặt `spring.liquibase.url` sang database khác và quan sát history được ghi ở đâu.
2. Đặt default schema không phù hợp rồi kiểm tra object/history.
3. Thu hồi một quyền DDL cần thiết khỏi migration role và xem lỗi startup.
4. Khôi phục cấu hình đúng, chạy lại trên database có trạng thái đã điều tra.

Không thực hiện thử nghiệm sai URL hoặc thu hồi quyền trên production.

### Giai đoạn D — Tách migration khỏi startup

1. Chạy Liquibase CLI trong bước pipeline thử nghiệm bằng migration credential.
2. Kiểm tra `validate`, `status --verbose`, SQL preview và `update`.
3. Xác minh `DATABASECHANGELOG` và schema.
4. Khởi động ứng dụng với runtime credential và `spring.liquibase.enabled=false` chỉ trong profile của quy trình này.
5. Chạy smoke test để xác nhận ứng dụng dùng schema đã được cập nhật.

**Tiêu chí đạt:** giải thích được DataSource được chọn cho Liquibase; cấu hình được hai credential riêng; runtime không có quyền DDL; migration role có quyền đủ nhưng giới hạn; xác minh đúng database/schema; kiểm thử được cả startup migration và pipeline migration.

## 15. Checklist thiết kế kết nối Liquibase trong Spring Boot

- [ ] Đã quyết định dùng chung DataSource hay DataSource migration riêng.
- [ ] Nếu dùng riêng, đã chọn rõ `spring.liquibase.url` hoặc bean `@LiquibaseDataSource`.
- [ ] Application DataSource được chọn đúng cho JDBC/JPA; có `@Primary` khi cần.
- [ ] Hai kết nối trỏ đúng database/catalog/schema theo thiết kế.
- [ ] Migration role có DDL và quyền history/lock cần thiết.
- [ ] Runtime role không có quyền DDL rộng nếu không cần.
- [ ] Default schema và Liquibase metadata schema được cấu hình đúng.
- [ ] Credential được lấy từ secret manager/biến môi trường, không commit.
- [ ] Pool, timeout và lifecycle của migration DataSource phù hợp.
- [ ] Đã xác định migration chạy lúc startup hay từ pipeline.
- [ ] Nếu nhiều instance startup, đã hiểu hành vi lock và timeout.
- [ ] Test dùng DBMS/role đại diện, không chỉ dựa vào H2.
- [ ] Đã kiểm tra lỗi sai URL, sai schema, thiếu quyền và migration failure.
- [ ] Sau migration đã kiểm tra history, schema và CRUD bằng runtime role.

## 16. Câu hỏi tự kiểm tra

1. Khi không khai báo Liquibase DataSource riêng, Spring Boot thường dùng DataSource nào?
2. `@LiquibaseDataSource` biểu thị vai trò gì?
3. `spring.datasource.url` và `spring.liquibase.url` khác nhau như thế nào?
4. Vì sao tách credential migration khỏi runtime giúp thực hiện least privilege?
5. Nếu hai DataSource trỏ tới hai database khác nhau, rủi ro nào có thể xảy ra?
6. Khi có nhiều DataSource, vì sao application DataSource thường cần `@Primary`?
7. Liquibase DataSource có dùng chung transaction với `@Transactional` của service không?
8. Migration role cần quyền gì ngoài quyền tạo bảng?
9. `default-schema` và `liquibase-schema` khác nhau thế nào?
10. Vì sao `DATABASECHANGELOGLOCK` không thay thế kế hoạch điều phối release?
11. Khi nào nên chạy migration trong pipeline thay vì startup của từng instance?
12. Làm sao kiểm thử rằng JDBC/JPA dùng runtime DataSource còn Liquibase dùng migration DataSource?
13. Vì sao test H2 có thể không phát hiện vấn đề DDL hoặc quyền trên production DBMS?
14. Khi migration thất bại do thiếu quyền, vì sao không nên cấp superuser cho ứng dụng để xử lý nhanh?

## Kết luận

Spring Boot cho phép Liquibase dùng **DataSource chính của ứng dụng** hoặc **kết nối migration riêng**. Dùng chung đơn giản nhưng thường buộc runtime role có quyền DDL; tách riêng giúp giới hạn quyền, audit và điều phối credential rõ hơn, đổi lại cần quản lý hai kết nối và xác minh chúng trỏ cùng mục tiêu đã định. Chọn `spring.liquibase.url` hoặc bean `@LiquibaseDataSource` theo nhu cầu, cấu hình rõ primary/qualifier khi có nhiều DataSource, và kiểm thử quyền thực tế trên DBMS đích. Khi kết nối, schema metadata, thời điểm migration và quyền runtime được xác định rõ, `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` có thể vận hành an toàn cùng Spring Boot và CI/CD.
