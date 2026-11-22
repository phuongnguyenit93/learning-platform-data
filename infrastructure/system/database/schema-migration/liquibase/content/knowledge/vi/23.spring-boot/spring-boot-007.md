# Quản lý migration khi ứng dụng có nhiều DataSource

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Với ứng dụng có nhiều **DataSource**, cần xác định rõ Liquibase kết nối tới database nào, dùng root changelog nào, lưu lịch sử ở đâu và chạy migration theo thứ tự nào.

Một ứng dụng có thể truy cập nhiều database hoặc nhiều vùng dữ liệu: đơn hàng, thanh toán, báo cáo, tenant, dữ liệu lịch sử hay một hệ thống bên ngoài. Việc khai báo nhiều bean DataSource chỉ giải quyết kết nối của ứng dụng. Nó **không tự bảo đảm Liquibase sẽ cập nhật đúng tất cả database**. Nếu Liquibase lấy nhầm DataSource, dùng chung bảng metadata ngoài ý muốn hoặc chỉ chạy một root changelog, một database có thể được cập nhật trong khi database còn lại vẫn ở schema cũ.

Bài học tập trung vào cách tổ chức migration cho từng đích dữ liệu, lựa chọn DataSource cho Liquibase, cấu hình SpringLiquibase tường minh khi có nhiều đích, tách lịch sử triển khai, điều phối thứ tự khởi động và kiểm chứng qua Spring Boot/CI/CD.

## 1. DataSource và Liquibase làm hai nhiệm vụ khác nhau

Trong Spring Boot, **DataSource** cung cấp kết nối JDBC. Repository, JDBC template, JPA/Hibernate hoặc service có thể dùng DataSource để đọc/ghi dữ liệu ứng dụng.

Liquibase cần một DataSource để:

- Kết nối tới database đích.
- Đọc trạng thái lịch sử trong DATABASECHANGELOG.
- Lấy lock qua DATABASECHANGELOGLOCK.
- Kiểm tra changeset đã chạy hay còn pending.
- Thực thi DDL/DML từ changelog.
- Ghi lại kết quả và checksum của changeset.

Nếu ứng dụng có ordersDataSource và billingDataSource, Liquibase không tự suy ra rằng phải chạy changelog orders trên DataSource thứ nhất và changelog billing trên DataSource thứ hai. Cần cấu hình quan hệ đó một cách rõ ràng.

### 1.1. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa |
|---|---|
| DataSource | Cấu hình nguồn kết nối JDBC tới một database hoặc pool kết nối |
| Runtime DataSource | DataSource mà ứng dụng dùng để phục vụ request và tác vụ nghiệp vụ |
| Migration DataSource | DataSource mà Liquibase dùng để thay đổi schema và dữ liệu |
| SpringLiquibase | Bean tích hợp Liquibase với Spring; khi khởi tạo, bean thực hiện migration nếu được bật |
| Root changelog | File changelog gốc nạp các changeset và file con cho một phạm vi migration |
| DATABASECHANGELOG | Bảng ghi lịch sử changeset đã được Liquibase xử lý |
| DATABASECHANGELOGLOCK | Bảng điều phối lock cho quá trình cập nhật cùng bộ metadata |
| Migration target | Một database/schema hoặc phạm vi được quản lý bởi một quy trình Liquibase cụ thể |

Một migration DataSource có thể trùng với runtime DataSource, hoặc là một DataSource riêng có quyền DDL cao hơn. Tách hai loại kết nối thường hữu ích khi ứng dụng runtime chỉ cần quyền SELECT/INSERT/UPDATE/DELETE còn migration cần tạo bảng, index, constraint hoặc thay đổi cấu trúc.

### 1.2. Ví dụ kiến trúc hai database

~~~text
Spring Boot application
    |
    +-- ordersDataSource
    |       |
    |       +-- Orders repositories / JPA
    |       |
    |       +-- ordersLiquibase
    |               |
    |               +-- db/changelog/orders/master.yaml
    |               +-- Orders DATABASECHANGELOG / LOCK
    |
    +-- billingDataSource
            |
            +-- Billing repositories / JDBC
            |
            +-- billingLiquibase
                    |
                    +-- db/changelog/billing/master.yaml
                    +-- Billing DATABASECHANGELOG / LOCK
~~~

Mỗi đích có root changelog, DataSource và lịch sử riêng. Nếu hai DataSource trỏ tới hai database vật lý khác nhau, metadata mặc định của Liquibase thường nằm riêng theo database. Nếu chúng trỏ vào cùng một database vật lý, cần thiết kế schema hoặc tên bảng metadata để hai quy trình không vô tình dùng chung lịch sử/lock.

## 2. Chọn mô hình migration theo số lượng đích

Không phải ứng dụng nào có nhiều DataSource cũng cần nhiều Liquibase bean. Trước tiên hãy xác định **có bao nhiêu database/schema thực sự cần được quản lý độc lập**.

| Kiến trúc | Cách tổ chức Liquibase thường phù hợp |
|---|---|
| Một database, nhiều repository | Một DataSource và một Liquibase root changelog |
| Một database, nhiều schema nhưng một lịch sử chung | Một Liquibase bean nếu các schema thuộc cùng một migration lifecycle |
| Một database, nhiều schema được phát hành độc lập | Có thể dùng nhiều SpringLiquibase bean với metadata riêng |
| Nhiều database vật lý | Một Liquibase bean/runner cho từng database cần migration |
| Một database chính và một database chỉ đọc bên ngoài | Chỉ quản lý migration cho database thuộc quyền sở hữu; không tự chạy DDL trên nguồn ngoài |
| Nhiều tenant database | Điều phối migration theo danh sách tenant/database, có giới hạn concurrency và theo dõi từng kết quả |

### 2.1. Một Liquibase bean cho một migration lifecycle

Nếu orders và billing chỉ là hai schema trong cùng một database, được triển khai cùng một lần và có chung dependency, có thể tổ chức một root changelog với các changeset tạo đối tượng ở từng schema. Khi đó một bảng lịch sử và một lock có thể là lựa chọn phù hợp.

Ngược lại, nếu hai schema được phát hành độc lập, có chủ sở hữu khác nhau hoặc có thời điểm triển khai khác nhau, nên tách migration lifecycle để mỗi phạm vi có lịch sử và lock riêng.

Không tạo nhiều Liquibase bean chỉ vì có nhiều repository. Số bean nên phản ánh số **migration target độc lập**, không phản ánh số package hoặc số nhóm code.

### 2.2. Một DataSource không đồng nghĩa một schema

Một JDBC connection có thể truy cập nhiều schema nếu tài khoản được cấp quyền. Liquibase có thể tạo đối tượng ở schema cụ thể qua schemaName, hoặc dùng defaultSchemaName khi change type không chỉ định rõ.

Cần phân biệt:

- Database/catalog mà connection đang kết nối.
- Schema mặc định của session.
- Schema chứa đối tượng nghiệp vụ.
- Schema chứa DATABASECHANGELOG và DATABASECHANGELOGLOCK.

Đừng dùng tên schema để che giấu việc hai database vật lý khác nhau. Một DataSource vẫn kết nối tới một đích JDBC cụ thể.

## 3. Spring Boot tự chọn DataSource nào cho Liquibase?

Khi dùng auto-configuration mặc định, Spring Boot có thể cấu hình Liquibase dựa trên DataSource của ứng dụng. Nếu có một bean DataSource chính, Liquibase thường dùng bean phù hợp theo quy tắc auto-configuration.

Spring Boot hỗ trợ một DataSource riêng cho Liquibase thông qua qualifier **@LiquibaseDataSource**. Ngoài ra, cấu hình Liquibase có thể được cấp thông tin kết nối riêng bằng các thuộc tính spring.liquibase.* tương ứng với phiên bản Spring Boot đang dùng.

Điều này phù hợp khi ứng dụng có nhiều DataSource nhưng chỉ có **một migration target được auto-configure**.

### 3.1. Dùng @LiquibaseDataSource cho một migration target

Ví dụ:

~~~java
@Configuration
public class DataSourceConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders")
    public DataSourceProperties ordersDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.orders-migration")
    public DataSourceProperties ordersMigrationDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders.configuration")
    public HikariDataSource ordersDataSource(
            @Qualifier("ordersDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean
    @LiquibaseDataSource
    @ConfigurationProperties("app.datasource.orders-migration.configuration")
    public HikariDataSource ordersMigrationDataSource(
            @Qualifier("ordersMigrationDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
~~~

Đây là ví dụ minh họa cách khai báo bean; khi triển khai thật, hãy cấu hình URL, username, password và pool cho migration DataSource từ nguồn phù hợp. Không sao chép nguyên cấu hình runtime rồi vô tình dùng chung credentials nếu mục tiêu là tách quyền.

Khi có @LiquibaseDataSource, auto-configuration có thể chọn bean đó cho Liquibase thay vì DataSource chính. @Primary vẫn có vai trò khi Spring cần một DataSource mặc định cho những injection không dùng qualifier.

### 3.2. Dùng cấu hình kết nối Liquibase riêng

Trong trường hợp chỉ có một Liquibase target, có thể cấu hình URL và thông tin xác thực riêng qua spring.liquibase.url, spring.liquibase.user và các thuộc tính liên quan được phiên bản Spring Boot hỗ trợ. Điều này cho phép migration dùng tài khoản khác runtime.

Không đưa password thật vào application.yml đã commit. Dùng biến môi trường/secret manager hoặc cấu hình ngoài được bảo vệ.

### 3.3. Giới hạn của auto-configuration khi có nhiều target

Các thuộc tính spring.liquibase.* mô tả **một cấu hình Liquibase auto-configured**. Chúng không tự tạo một root changelog độc lập cho từng DataSource tùy theo tên bean.

Nếu ứng dụng cần chạy hai root changelog lên hai database khác nhau, cấu hình auto-configuration đơn lẻ không đủ để biểu diễn cả hai quy trình. Khi đó, cách rõ ràng hơn là khai báo các bean SpringLiquibase riêng, mỗi bean nhận DataSource và root changelog tương ứng.

## 4. Khai báo nhiều SpringLiquibase bean tường minh

Giả sử ứng dụng quản lý hai database:

- Orders DB: lưu khách hàng và đơn hàng.
- Billing DB: lưu hóa đơn và thanh toán.

Cấu hình Java có thể khai báo hai bean:

~~~java
@Configuration
public class LiquibaseConfiguration {

    @Bean
    public SpringLiquibase ordersLiquibase(
            @Qualifier("ordersMigrationDataSource") DataSource dataSource) {

        SpringLiquibase liquibase = new SpringLiquibase();
        liquibase.setDataSource(dataSource);
        liquibase.setChangeLog(
                "classpath:db/changelog/orders/db.changelog-master.yaml");
        liquibase.setDefaultSchema("orders");
        liquibase.setLiquibaseSchema("orders_meta");
        liquibase.setContexts("prod");
        return liquibase;
    }

    @Bean
    public SpringLiquibase billingLiquibase(
            @Qualifier("billingMigrationDataSource") DataSource dataSource) {

        SpringLiquibase liquibase = new SpringLiquibase();
        liquibase.setDataSource(dataSource);
        liquibase.setChangeLog(
                "classpath:db/changelog/billing/db.changelog-master.yaml");
        liquibase.setDefaultSchema("billing");
        liquibase.setLiquibaseSchema("billing_meta");
        liquibase.setContexts("prod");
        return liquibase;
    }
}
~~~

Đoạn mã thể hiện cách ánh xạ từng bean tới một DataSource và root changelog. Các schema orders_meta và billing_meta phải được provisioning hoặc tạo theo cách được cấp quyền; không giả định Liquibase có thể tạo schema metadata nếu schema chưa tồn tại và tài khoản không có quyền.

Tên setter và khả năng cấu hình có thể khác theo phiên bản thư viện SpringLiquibase/Liquibase được dự án sử dụng. Hãy đối chiếu API của version đã pin. Với cấu hình nhiều target, kiểm tra startup test để xác nhận cả hai bean thực sự chạy đúng.

### 4.1. Tại sao phải dùng @Qualifier?

Nếu có nhiều DataSource, injection chỉ khai báo kiểu DataSource có thể trở nên mơ hồ. @Qualifier("ordersMigrationDataSource") nói rõ bean nào được dùng cho ordersLiquibase.

Không dựa vào thứ tự khai báo bean hoặc tên biến Java để Spring tự chọn đúng database. Đặt tên bean ổn định và dùng qualifier ở mọi nơi cần lựa chọn một target cụ thể.

### 4.2. Khi tự khai báo SpringLiquibase, cần hiểu auto-configuration

Spring Boot auto-configuration thường chỉ tạo Liquibase bean khi chưa có bean tương ứng do ứng dụng khai báo. Khi tự khai báo nhiều SpringLiquibase bean, cần kiểm tra cấu hình auto-configuration để tránh một bean mặc định ngoài ý muốn hoặc cấu hình Liquibase chạy thêm lần nữa.

Không kết hợp tùy tiện một @LiquibaseDataSource, một root auto-configured và hai bean tự khai báo mà không kiểm tra bean nào thực sự tồn tại trong ApplicationContext.

## 5. Tách root changelog cho từng database

Một cấu trúc tài nguyên có thể tổ chức:

~~~text
src/main/resources/
  db/changelog/
    orders/
      db.changelog-master.yaml
      schema/
        001-create-customers.yaml
        002-create-orders.yaml
      data/
        010-seed-order-status.yaml
    billing/
      db.changelog-master.yaml
      schema/
        001-create-invoices.yaml
        002-create-payments.yaml
      data/
        010-seed-payment-methods.yaml
~~~

Root orders:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/orders/schema/001-create-customers.yaml
  - include:
      file: db/changelog/orders/schema/002-create-orders.yaml
  - include:
      file: db/changelog/orders/data/010-seed-order-status.yaml
~~~

Root billing:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/billing/schema/001-create-invoices.yaml
  - include:
      file: db/changelog/billing/schema/002-create-payments.yaml
  - include:
      file: db/changelog/billing/data/010-seed-payment-methods.yaml
~~~

Các file là ví dụ về tổ chức tài nguyên. Hãy bảo đảm đường dẫn include được resolve đúng theo root/resource accessor và cấu trúc JAR thực tế. Một file con có thể include tiếp file khác; toàn bộ cây dependency phải được đóng gói.

### 5.1. Không dùng nhầm root changelog

Nếu ordersLiquibase trỏ tới root billing, Liquibase có thể tạo bảng billing trong database orders hoặc thất bại vì schema/permission không phù hợp. Cấu hình đúng kiểu DataSource chưa đủ; root changelog cũng phải đúng phạm vi.

Nên đặt tên bean và đường dẫn root có quan hệ dễ nhận diện:

| Bean | DataSource | Root changelog | Default schema |
|---|---|---|---|
| ordersLiquibase | ordersMigrationDataSource | db/changelog/orders/db.changelog-master.yaml | orders |
| billingLiquibase | billingMigrationDataSource | db/changelog/billing/db.changelog-master.yaml | billing |

Review mapping này trong pull request và kiểm tra nó trong test cấu hình Spring.

### 5.2. Không include chéo tùy tiện

Có thể chia sẻ changelog chung giữa nhiều database nếu change type và SQL tương thích, nhưng không nên để root orders vô tình include một file chỉ dành cho billing. Nếu dùng một thư viện changelog chung, hãy xác định rõ phần dùng chung, phần theo DBMS và dependency của từng target.

Khi hai database có lifecycle độc lập, mỗi root nên thể hiện rõ tập changeset mà database đó sở hữu.

## 6. Tách DATABASECHANGELOG và DATABASECHANGELOGLOCK

Mỗi Liquibase execution cần đọc/ghi lịch sử và lock trong đúng phạm vi. Nếu nhiều migration target cùng trỏ vào một database vật lý và cùng dùng một bộ bảng metadata, chúng có thể chia sẻ lịch sử và lock ngoài ý muốn.

### 6.1. Trường hợp hai database vật lý khác nhau

Nếu ordersDataSource và billingDataSource kết nối hai database khác nhau, mỗi database có bộ metadata riêng. Cùng tên bảng DATABASECHANGELOG không gây xung đột vì chúng nằm trong hai database khác nhau.

Vẫn cần bảo đảm mỗi root changelog chỉ chạy trên database mà nó sở hữu.

### 6.2. Trường hợp hai schema trên cùng một database

Nếu hai DataSource kết nối cùng database/catalog nhưng quản lý hai schema độc lập, cần quyết định cách tách metadata. Có thể đặt metadata trong schema riêng:

- ordersLiquibase lưu bảng lịch sử trong orders_meta.
- billingLiquibase lưu bảng lịch sử trong billing_meta.

Hoặc dùng tên bảng metadata khác nhau trong cùng schema metadata nếu DBMS/cấu hình cho phép. Cần tách cả bảng lock tương ứng để hai quy trình có lifecycle riêng.

Không để hai root độc lập dùng chung DATABASECHANGELOG chỉ vì tên bảng mặc định giống nhau. Khi dùng chung, định danh changeset và thứ tự triển khai có thể bị trộn; một root có thể nhìn thấy changeset của root còn lại nếu định danh trùng hoặc phạm vi metadata không được thiết kế.

### 6.3. Khi nào dùng chung metadata có thể hợp lý?

Nếu có một root changelog duy nhất quản lý nhiều schema trong cùng database, một bộ DATABASECHANGELOG/LOCK chung thường là lựa chọn tự nhiên. Khi đó, các changeset thuộc cùng một lịch sử và một quá trình triển khai được điều phối thống nhất.

Quy tắc là **một bộ metadata cho một migration lifecycle đã được xác định**, không phải một bộ metadata cho mỗi repository hoặc một bảng metadata dùng chung cho mọi database bất kể ownership.

### 6.4. Quyền đối với schema metadata

Tài khoản migration cần:

- Quyền đọc/ghi DATABASECHANGELOG.
- Quyền đọc/ghi DATABASECHANGELOGLOCK.
- Quyền tạo các bảng metadata lần đầu nếu chưa có.
- Quyền truy cập schema nghiệp vụ tương ứng.
- Quyền tạo DDL/DML theo changeset.

Nếu schema metadata do DBA provisioning, hãy ghi rõ owner và grant. Không cấp quyền DBA toàn cục chỉ để tránh lỗi thiếu quyền.

## 7. Phân biệt migration DataSource và runtime DataSource

Tách kết nối migration khỏi kết nối ứng dụng giúp giới hạn quyền và kiểm soát thời điểm thay đổi schema.

| Thuộc tính | Migration DataSource | Runtime DataSource |
|---|---|---|
| Mục đích | DDL/DML migration và metadata Liquibase | Phục vụ nghiệp vụ |
| Quyền | Có quyền thay đổi schema theo phạm vi | Tối thiểu theo thao tác ứng dụng |
| Thời điểm | Startup hoặc migration job | Suốt vòng đời ứng dụng |
| Số connection | Thường ít, phục vụ tác vụ migration | Pool theo tải ứng dụng |
| Credential | Secret riêng | Secret runtime riêng |
| Giám sát | Log migration, lock, thời gian DDL | Pool usage, query latency, error rate |

### 7.1. Một migration connection riêng cho mỗi target

Nếu orders và billing là hai database, có thể có:

- ordersMigrationDataSource → orders DB với user orders_migrator.
- billingMigrationDataSource → billing DB với user billing_migrator.
- ordersDataSource → orders DB với user orders_runtime.
- billingDataSource → billing DB với user billing_runtime.

Mỗi SpringLiquibase bean nhận migration DataSource tương ứng. Repository chỉ inject runtime DataSource.

### 7.2. Không để JPA/Hibernate tự sửa schema song song

Nếu Liquibase là nguồn quản lý schema, cấu hình Hibernate nên ở chế độ kiểm tra phù hợp (thường là validate hoặc không tự thay đổi schema theo chính sách dự án), thay vì cùng Liquibase thực hiện DDL qua update/create.

Hai công cụ cùng thay đổi schema có thể tạo race, khác biệt không có trong changelog và khó truy vết. Mỗi persistence unit cần gắn đúng DataSource và schema; Hibernate validate trên database orders không thể chứng minh database billing đã được migration.

## 8. Cấu hình nhiều DataSource bằng Spring Boot

Ví dụ cấu hình properties cho hai target:

~~~yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://orders-db:5432/orders
      username: orders_runtime
      password: <ORDERS_DB_PASSWORD>
      configuration:
        maximum-pool-size: 12
    orders-migration:
      url: jdbc:postgresql://orders-db:5432/orders
      username: orders_migrator
      password: <ORDERS_MIGRATION_PASSWORD>
      configuration:
        maximum-pool-size: 2
    billing:
      url: jdbc:postgresql://billing-db:5432/billing
      username: billing_runtime
      password: <BILLING_DB_PASSWORD>
      configuration:
        maximum-pool-size: 8
    billing-migration:
      url: jdbc:postgresql://billing-db:5432/billing
      username: billing_migrator
      password: <BILLING_MIGRATION_PASSWORD>
      configuration:
        maximum-pool-size: 2
~~~

Đây là cấu hình minh họa. Trong môi trường thật, URL và secret đến từ cấu hình theo môi trường/secret manager; không commit password.

Có thể tạo hai DataSourceProperties và hai DataSource với prefix riêng. Một DataSource có thể được đánh dấu @Primary để làm mặc định cho các injection không có qualifier, nhưng các bean Liquibase và repository cần chỉ rõ qualifier tương ứng.

### 8.1. Mỗi persistence unit cần đúng DataSource

Nếu dùng JPA cho cả orders và billing, có thể cần hai EntityManagerFactory và hai PlatformTransactionManager, mỗi bộ gắn với package entity/repository và DataSource tương ứng.

Điều này thuộc cấu hình persistence của ứng dụng. Liquibase không tự cấu hình repository, entity manager hay transaction manager. Cần bảo đảm:

- Orders repositories dùng ordersDataSource/EntityManagerFactory.
- Billing repositories dùng billingDataSource/EntityManagerFactory.
- Orders Liquibase dùng orders migration target.
- Billing Liquibase dùng billing migration target.
- Transaction của service chỉ dùng manager phù hợp với database mà nó thao tác.

Một transaction manager JDBC/JPA thông thường không tạo distributed transaction xuyên hai database. Nếu nghiệp vụ ghi cả orders và billing, cần thiết kế consistency riêng (outbox/saga/transaction coordinator) thay vì kỳ vọng hai Liquibase bean hoặc hai DataSource làm thao tác dữ liệu nguyên tử.

## 9. Thứ tự khởi động: migration phải hoàn tất trước consumer

Một ứng dụng có thể tạo Liquibase bean nhưng service hoặc JPA khởi tạo trước khi schema tương ứng sẵn sàng nếu dependency initialization không được thiết kế rõ.

Với SpringLiquibase, migration thường chạy trong quá trình khởi tạo bean. Tuy nhiên, khi tự khai báo nhiều bean, phải kiểm tra thứ tự giữa:

- SpringLiquibase bean cho orders.
- SpringLiquibase bean cho billing.
- EntityManagerFactory hoặc JDBC client của từng database.
- Repository/service thực hiện query trong quá trình khởi tạo.
- Scheduler, listener, message consumer hoặc background job.

### 9.1. Khai báo dependency khởi tạo

Nếu một bean cần schema orders ngay khi khởi tạo, có thể khai báo phụ thuộc rõ ràng:

~~~java
@Bean
@DependsOn("ordersLiquibase")
public OrdersStartupVerifier ordersStartupVerifier(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new OrdersStartupVerifier(dataSource);
}
~~~

Với các bean JPA hoặc database initializer, cách tích hợp dependency có thể khác theo phiên bản Spring Boot và cách khai báo EntityManagerFactory. Có thể dùng cơ chế dependency initialization được Spring Boot hỗ trợ hoặc @DependsOn trên bean phù hợp. Không giả định chỉ vì Liquibase bean được khai báo trong cùng class thì mọi consumer sẽ tự có thứ tự mong muốn.

### 9.2. Không khởi động consumer khi migration bắt buộc thất bại

Nếu orders migration thất bại, ứng dụng không nên tiếp tục nhận request phụ thuộc schema orders như thể mọi thứ bình thường. Nếu billing migration thành công nhưng orders thất bại, trạng thái ứng dụng là một trạng thái triển khai không đồng nhất; cần dừng startup/rollout hoặc áp dụng chính sách degraded mode được thiết kế và giám sát rõ ràng.

Không nuốt exception từ một SpringLiquibase bean chỉ để ứng dụng khởi động. Nếu một database không bắt buộc trong một profile, hãy cấu hình shouldRun/điều kiện bean theo profile có chủ đích và kiểm tra rõ target đó không nằm trong phạm vi release.

## 10. Nhiều database vật lý: kiểm soát partial success

Khi orders và billing là hai database độc lập, hai Liquibase bean thực hiện hai migration độc lập. Nếu orders thành công nhưng billing thất bại, không có transaction JDBC thông thường nào tự động rollback cả hai database như một đơn vị.

Ví dụ:

~~~text
Release 2.4.0
   |
   +--> Orders migration: SUCCESS
   |
   +--> Billing migration: FAILED
             |
             v
       Release ở trạng thái không đồng nhất
~~~

Các bước xử lý:

1. Dừng rollout ứng dụng phụ thuộc đồng thời vào schema mới của cả hai.
2. Xác minh orders changeset và schema đã được áp dụng.
3. Điều tra billing migration; xác định có DDL/DML commit một phần không.
4. Quyết định sửa billing bằng retry có kiểm soát, forward-fix hoặc rollback.
5. Kiểm tra tương thích của ứng dụng với trạng thái hiện tại.
6. Ghi lại trạng thái từng database trong deployment manifest.
7. Chỉ tiếp tục rollout khi các target bắt buộc đạt trạng thái tương thích.

Không coi hai bean trong cùng ApplicationContext là một giao dịch phân tán. SpringLiquibase không tự điều phối rollback xuyên nhiều database.

### 10.1. Lập bảng trạng thái theo target

| Target | Liquibase bean | Release | Kết quả | Hành động tiếp |
|---|---|---|---|---|
| Orders DB | ordersLiquibase | 2.4.0 | SUCCESS | Hậu kiểm và giữ schema tương thích |
| Billing DB | billingLiquibase | 2.4.0 | FAILED | Điều tra partial state, sửa chữa |
| Reporting DB | reportingLiquibase | 2.4.0 | NOT STARTED | Chờ target bắt buộc sẵn sàng |

Không chỉ ghi một trạng thái chung migration=success ở cấp ứng dụng nếu có nhiều target.

## 11. Thứ tự giữa nhiều migration target

Nếu các database độc lập hoàn toàn, có thể chạy migration song song để rút ngắn thời gian. Nhưng chỉ làm vậy khi:

- Không có dependency dữ liệu/schema xuyên database.
- Không có một target cần hoàn tất trước target kia.
- Hạ tầng có đủ connection và tài nguyên.
- Pipeline có thể theo dõi kết quả riêng.
- Partial success đã có phương án xử lý.

Nếu release yêu cầu thứ tự, điều phối rõ ràng:

~~~text
1. Orders schema expand
        |
        v
2. Billing schema expand
        |
        v
3. Backfill / reconciliation
        |
        v
4. Deploy application compatible
        |
        v
5. Contract / cleanup theo release sau
~~~

Đây chỉ là ví dụ. Thứ tự thật phải xuất phát từ hợp đồng nghiệp vụ giữa các service/database. Nếu không có dependency, không cần tạo thứ tự giả tạo.

### 11.1. Không dùng một lock Liquibase để đồng bộ nhiều database

DATABASECHANGELOGLOCK chỉ điều phối những runner chia sẻ cùng bộ metadata của một database/target. Nó không khóa orders và billing như một giao dịch chung, cũng không bảo đảm hai migration chạy theo cùng một release.

Việc điều phối nhiều target thuộc trách nhiệm của CI/CD/orchestrator hoặc một quy trình migration cấp cao hơn.

## 12. Context, label, dbms và properties theo từng DataSource

Mỗi target có thể có cấu hình khác:

| Target | Context ví dụ | DBMS | Root |
|---|---|---|---|
| Orders | prod | PostgreSQL | orders/master.yaml |
| Billing | prod | PostgreSQL | billing/master.yaml |
| Reporting | reporting | PostgreSQL | reporting/master.yaml |
| Legacy Oracle | legacy | Oracle | legacy/master.yaml |

Cấu hình filter phải được gắn vào đúng SpringLiquibase bean. Không truyền context billing cho orders chỉ vì cả hai cùng khởi động trong một profile.

### 12.1. Context không phải ranh giới bảo mật

Context/label điều khiển changeset nào được chọn; chúng không thay thế database URL, credential, quyền và network boundary. Một root changelog sai vẫn có thể chạy SQL sai database nếu user có quyền.

Đối với fixture test hoặc dữ liệu demo, cần tách root changelog và database; không chỉ dựa vào context để ngăn production.

### 12.2. Property substitution phải được kiểm chứng theo target

Nếu orders và billing có schema/property khác nhau, mỗi Liquibase bean cần nhận giá trị tương ứng. Không để hai bean cùng đọc một tập properties mặc định rồi vô tình tạo đối tượng vào schema giống nhau.

Kiểm tra SQL preview hoặc test integration với cấu hình cuối cùng. Không đưa secret vào property của changelog hoặc log.

## 13. Nhiều DBMS và cấu hình migration riêng

Một ứng dụng có thể kết nối nhiều DBMS, chẳng hạn PostgreSQL cho orders và Oracle cho reporting. Không thể giả định cùng SQL chạy trên mọi database.

Cách tổ chức thường là:

- Root changelog riêng cho mỗi DBMS/target khi schema và logic khác nhau đáng kể.
- Changeset dbms để giới hạn thay đổi đặc thù khi một root chung thật sự phù hợp.
- Change type trừu tượng cho thay đổi portable nếu sinh SQL đúng trên mọi engine được hỗ trợ.
- SQL riêng theo engine cho function, index, partition, sequence hoặc DDL đặc thù.
- Kiểm thử trên DBMS/version thực tế, không chỉ H2.

Ví dụ changeset giới hạn PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-050-create-partial-index
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX idx_orders_open
              ON orders (created_at)
              WHERE status = 'OPEN';
~~~

Nếu target billing dùng Oracle, không được giả định changeset PostgreSQL này cung cấp cùng chức năng cho billing. Cần root/changelog và implementation phù hợp cho từng engine.

## 14. Transaction, rollback và trạng thái từng target

Mỗi database có transaction semantics, lock và DDL behavior riêng. Một lần chạy nhiều SpringLiquibase bean không làm các changeset của các target trở thành transaction phân tán.

Cần kiểm tra:

- DDL có transactional trên DBMS đó không?
- Changeset có runInTransaction=false không?
- SQL có thao tác auto-commit hoặc cấm transaction không?
- Lock/timeout có ảnh hưởng target khác không?
- Rollback có thể phục hồi dữ liệu thật không?
- Khi một target thành công và target khác thất bại, ứng dụng có tương thích không?

### 14.1. Rollback từng target

Rollback orders không tự rollback billing. Mỗi target có lịch sử, tag và phạm vi changeset riêng. Trước khi rollback, xác định chính xác database và migration bean/runner sẽ thao tác.

Không chạy một lệnh rollback chung lên nhiều database chỉ dựa vào cùng tên tag nếu chưa xác nhận tag tồn tại và ý nghĩa giống nhau ở từng target.

### 14.2. Forward-fix có thể phù hợp hơn

Nếu orders migration đã tạo cột mới và ứng dụng bắt đầu ghi dữ liệu, rollback xóa cột có thể làm mất dữ liệu. Nếu billing migration thất bại, có thể cần forward-fix billing để đạt trạng thái tương thích thay vì rollback orders.

Quyết định phải dựa trên trạng thái thực tế và yêu cầu nghiệp vụ, không phải cố ép tất cả target về cùng một điểm lịch sử bằng mọi giá.

## 15. Kiểm tra startup và các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| NoUniqueBeanDefinitionException cho DataSource | Injection không có qualifier và có nhiều bean | Dùng @Qualifier, xác định @Primary hợp lý |
| Liquibase chạy vào database sai | DataSource auto-config được chọn không đúng | Kiểm tra @LiquibaseDataSource, URL và bean mapping |
| Chỉ một database được migration | Chỉ có một Liquibase auto-configured bean | Khai báo SpringLiquibase riêng cho từng target |
| Hai target cùng thấy changeset của nhau | Dùng chung metadata table không chủ đích | Tách liquibaseSchema hoặc tên bảng history/lock |
| Bảng metadata không tạo được | Thiếu schema hoặc quyền DDL | Provision metadata schema và grant migration user |
| Migration chạy trước khi consumer sẵn sàng | Bean dependency chưa rõ | Khai báo dependency khởi tạo và test ApplicationContext |
| JPA báo thiếu bảng khi startup | EntityManagerFactory dùng DataSource khác hoặc khởi tạo sớm | Kiểm tra persistence unit và thứ tự Liquibase |
| Một database thành công, database kia lỗi | Partial success giữa các target | Kiểm tra history/schema từng DB, dừng rollout |
| Migration chạy hai lần | Có nhiều runner hoặc auto-config + custom bean | Kiểm tra ApplicationContext, job và startup config |
| Chạy được dev nhưng lỗi prod | Khác context, DBMS, schema, quyền hoặc artifact | So cấu hình cuối cùng và SQL preview từng target |
| Lock chờ lâu | Runner khác đang chạy hoặc lock còn sót | Xác minh session/job trước khi giải phóng lock |
| Rollback làm mất dữ liệu | Đảo DDL/DML không khôi phục giá trị cũ | Backup/forward-fix và hậu kiểm dữ liệu |

### 15.1. Quan sát bean mapping trong ApplicationContext

Khi có nhiều DataSource và Liquibase bean, hãy kiểm tra tên bean thực tế và dependency graph. Không chỉ nhìn class cấu hình mà kết luận auto-configuration đã tạo đúng bean.

Có thể bật logging có kiểm soát cho quá trình khởi tạo Spring/Liquibase trên môi trường test. Không bật debug quá chi tiết trên production nếu log có thể chứa SQL literal, URL hoặc thông tin nhạy cảm.

### 15.2. Không giải phóng lock bằng thao tác thủ công vội vàng

Nếu ordersLiquibase đang chờ DATABASECHANGELOGLOCK, xác định runner nào giữ lock và database nào được kết nối. Không sửa bảng lock của billing khi lỗi xảy ra ở orders, và không xóa lock khi tiến trình gốc còn chạy.

## 16. Kiểm chứng bằng lệnh cho từng DataSource

Khi dùng CLI, mỗi target cần cấu hình URL, changelog và metadata tương ứng. Có thể dùng một defaults/properties file được quản lý riêng cho mỗi target, hoặc cung cấp tham số qua runner/secret source.

Ví dụ luồng kiểm tra cho orders:

~~~bash
liquibase --defaults-file=liquibase-orders.properties validate
liquibase --defaults-file=liquibase-orders.properties status --verbose
liquibase --defaults-file=liquibase-orders.properties update-sql
liquibase --defaults-file=liquibase-orders.properties update
liquibase --defaults-file=liquibase-orders.properties history
~~~

Tương tự, billing dùng cấu hình và root changelog riêng:

~~~bash
liquibase --defaults-file=liquibase-billing.properties validate
liquibase --defaults-file=liquibase-billing.properties status --verbose
liquibase --defaults-file=liquibase-billing.properties update-sql
liquibase --defaults-file=liquibase-billing.properties update
liquibase --defaults-file=liquibase-billing.properties history
~~~

Tên file chỉ minh họa. Không lưu password trong defaults file đã commit; dùng biến môi trường, secret manager hoặc cơ chế bảo mật của pipeline. Nếu cùng một runner dùng nhiều defaults file, xác minh mỗi lần gọi thật sự chọn đúng target.

### 16.1. Kiểm tra DATABASECHANGELOG riêng

Trên mỗi database/schema metadata, kiểm tra:

- Changeset id, author, filename.
- Checksum.
- EXECTYPE như EXECUTED, RERAN hoặc MARK_RAN.
- Thời điểm và deployment ID.
- Changeset pending theo đúng root/filter.

Không chỉ đếm số dòng history. Hai target có thể có số changeset khác nhau; điều quan trọng là danh sách và trạng thái đúng với release của từng target.

### 16.2. Kiểm tra schema thật sau migration

Dùng catalog của DBMS để xác nhận bảng/cột/constraint/index trong đúng schema. Kiểm tra dữ liệu tham chiếu, foreign key, view/function và quyền runtime. Nếu hai DataSource cùng database vật lý nhưng default schema khác, hãy xác nhận đối tượng được tạo đúng schema chứ không chỉ đúng database.

## 17. Bài thực hành: hai DataSource, hai Liquibase target

**Mục tiêu:** cấu hình Spring Boot có hai DataSource và hai root changelog, mỗi Liquibase bean cập nhật đúng database và có metadata độc lập. Dùng database thử nghiệm, không dùng production.

### Bước 1. Xác định hai target

| Thuộc tính | Orders | Billing |
|---|---|---|
| DataSource bean | ordersDataSource | billingDataSource |
| Migration bean | ordersLiquibase | billingLiquibase |
| Database | orders_test | billing_test |
| Root changelog | db/changelog/orders/master.yaml | db/changelog/billing/master.yaml |
| Default schema | orders | billing |
| Metadata schema | orders_meta | billing_meta |

Các tên là minh họa. Có thể dùng cùng một database vật lý với schema tách riêng, nhưng khi đó phải bảo đảm metadata tách như thiết kế.

### Bước 2. Khai báo hai DataSource

Tạo hai bean DataSource với prefix cấu hình riêng. Đánh dấu một bean @Primary nếu ứng dụng cần DataSource mặc định, nhưng tất cả bean Liquibase phải inject đúng qualifier.

Không dùng chung credentials nếu hai database cần quyền khác nhau.

### Bước 3. Khai báo hai SpringLiquibase bean

Dùng mẫu ở mục 4 hoặc 10. Xác nhận:

- ordersLiquibase nhận ordersDataSource.
- billingLiquibase nhận billingDataSource.
- Root changelog không bị hoán đổi.
- Default schema và metadata schema đúng.
- Context/label đúng profile.
- Không có Liquibase bean auto-config thứ ba ngoài ý muốn.

### Bước 4. Chuẩn bị root changelog riêng

Orders tạo bảng customers và orders. Billing tạo bảng invoices và payments. Không include file chéo. Đóng gói tất cả resource trong classpath/JAR hoặc migration bundle.

### Bước 5. Chạy kiểm thử database mới

Với từng database:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Các lệnh phải chạy với cấu hình target tương ứng. Xác minh bảng nghiệp vụ chỉ xuất hiện ở database/schema đúng, metadata không bị chia sẻ ngoài ý muốn.

### Bước 6. Kiểm tra lần update thứ hai

Chạy validate/status/update lần nữa cho cả hai target. Changeset thông thường không được chạy lại; không có seed duplicate; schema và dữ liệu không đổi ngoài chủ đích.

### Bước 7. Thử partial failure trong lab

Trên database test có thể tạo lại, cố ý làm một changeset của billing thất bại sau khi orders migration đã thành công. Quan sát:

- Orders DATABASECHANGELOG ghi gì?
- Billing DATABASECHANGELOG ghi gì?
- Có DDL nào đã commit một phần?
- Application startup/rollout có bị dừng không?
- Pipeline báo target nào failed?
- Có thể forward-fix billing mà giữ orders tương thích không?

Không xóa bảng history hoặc lock bằng tay để làm bài test chạy lại được. Nếu cần reset, tạo lại database lab theo lifecycle an toàn.

### Bước 8. Kiểm tra application

Khởi động Spring Boot từ artifact đã build. Kiểm tra từng repository/service dùng đúng DataSource, JPA mapping đúng schema, migration hoàn tất trước consumer và runtime user không có quyền DDL ngoài thiết kế.

Ghi lại version Liquibase, root changelog, bean mapping, exit code, history và hậu điều kiện cho từng target.

## 18. CI/CD cho ứng dụng nhiều database

Một pipeline nên biểu diễn migration target thành các bước riêng có kết quả độc lập:

~~~text
Build artifact + changelog
        |
        v
Validate resource dependencies
        |
        v
Orders target
  validate -> status -> update-sql -> approval -> update -> postcheck
        |
        v
Billing target
  validate -> status -> update-sql -> approval -> update -> postcheck
        |
        v
Cross-target compatibility checks
        |
        v
Rollout application
        |
        v
Smoke tests + release record
~~~

Nếu không có dependency giữa hai database, một số bước có thể chạy song song. Nếu có dependency, phải điều phối thứ tự và dừng khi target bắt buộc thất bại.

### 18.1. Ghi trạng thái từng target

Release manifest hoặc deployment report nên ghi:

- Application version và migration artifact version/digest.
- Liquibase version và JDBC driver.
- Database target đã redacted.
- Root changelog và metadata schema.
- Context/label.
- Changeset pending/đã chạy.
- Exit code từng lệnh.
- Kết quả hậu kiểm.
- Trạng thái partial success nếu có.
- Người phê duyệt và recovery plan.

Không chỉ ghi migration=success ở cấp ứng dụng nếu có nhiều target.

### 18.2. Retry có kiểm soát

Khi billing thất bại, không chạy lại toàn bộ job và giả định orders sẽ không thay đổi. Liquibase history có thể giúp bỏ qua changeset đã chạy ở orders, nhưng cần xác minh artifact, database và trạng thái vật lý trước retry.

Đặc biệt, DDL ngoài transaction hoặc changeset runInTransaction=false có thể để lại thay đổi một phần. Retry chỉ sau khi xác định database đang ở trạng thái nào và câu lệnh có an toàn khi chạy lại không.

### 18.3. Phân quyền theo target

CI runner của orders không cần quyền DDL trên billing nếu không triển khai billing. Có thể dùng secret scope và service account riêng theo target, giới hạn network route và ghi audit. Điều này giảm hậu quả nếu cấu hình nhầm hoặc job bị lạm dụng.

## 19. Những quyết định kiến trúc cần ghi lại

Khi đưa multi-DataSource vào vận hành, tài liệu kiến trúc nên trả lời:

1. Những database/schema nào thuộc quyền sở hữu của ứng dụng?
2. Target nào có Liquibase migration và target nào chỉ đọc/được quản lý bên ngoài?
3. Mỗi target dùng root changelog nào?
4. DataSource nào là runtime, DataSource nào là migration?
5. Có bao nhiêu SpringLiquibase bean và bean nào phụ thuộc bean nào?
6. Metadata schema/table/lock được đặt ở đâu?
7. Các target có thể migrate song song hay cần thứ tự?
8. Khi một target thành công, target khác thất bại thì release xử lý ra sao?
9. Migration chạy trong startup hay CI/CD job riêng?
10. Version ứng dụng nào tương thích với schema sau từng giai đoạn?
11. Rollback/forward-fix và backup/restore được kiểm chứng như thế nào?
12. Ai sở hữu từng database và ai phê duyệt thay đổi?

Không để những quyết định này chỉ nằm trong tên bean hoặc cấu hình không có review. Khi có nhiều nhóm phát triển, ownership và quy trình phát hành cần rõ ràng.

## 20. Checklist nghiệm thu multi-DataSource Liquibase

- [ ] Đã phân loại DataSource runtime và migration cho từng target.
- [ ] Đã xác định số migration lifecycle thực sự, không tạo bean chỉ theo số repository.
- [ ] Mỗi SpringLiquibase bean dùng đúng DataSource qua @Qualifier.
- [ ] Auto-configuration và custom beans không tạo runner trùng.
- [ ] Root changelog riêng đúng database/schema; không include nhầm.
- [ ] Toàn bộ include, sqlFile, CSV và resource có trong artifact.
- [ ] defaultSchema và liquibaseSchema được phân biệt rõ.
- [ ] DATABASECHANGELOG và DATABASECHANGELOGLOCK được tách theo lifecycle khi cần.
- [ ] Schema metadata được provisioning và migration user có quyền phù hợp.
- [ ] Context, label, dbms và properties đúng từng target.
- [ ] Liquibase, JDBC driver và extension được khóa version.
- [ ] Migration hoàn tất trước consumer cần schema.
- [ ] JPA/Hibernate không tự sửa schema song song với Liquibase.
- [ ] Mỗi target có validate, status, update-sql và hậu kiểm riêng.
- [ ] Đã kiểm thử fresh install và upgrade path cho từng target.
- [ ] Đã kiểm tra partial success và retry/forward-fix trong lab.
- [ ] Không giả định nhiều database được rollback như một transaction.
- [ ] Rollback được review riêng theo từng database và dữ liệu.
- [ ] CI/CD lưu kết quả/exit code theo target và dừng rollout khi target bắt buộc thất bại.
- [ ] Runtime credentials có quyền tối thiểu; migration credentials được bảo vệ.
- [ ] Application smoke test xác nhận repository/service dùng đúng database.

## 21. Kết luận

Quản lý Liquibase trong ứng dụng nhiều DataSource bắt đầu từ việc xác định **mỗi migration target thuộc database/schema nào**, sau đó ánh xạ tường minh DataSource, root changelog, metadata và cấu hình cho từng target. Với một target, @LiquibaseDataSource hoặc cấu hình Liquibase riêng có thể đủ; với nhiều target độc lập, các SpringLiquibase bean riêng giúp kiểm soát rõ ràng DataSource, changelog và lịch sử.

Cần tách migration DataSource khỏi runtime DataSource khi quyền và vòng đời khác nhau, tách DATABASECHANGELOG/LOCK khi các migration lifecycle độc lập cùng một database vật lý, và bảo đảm migration chạy trước consumer. Quan trọng nhất, nhiều Liquibase bean không tạo ra một transaction phân tán: nếu một database thành công còn database khác thất bại, phải theo dõi partial success, kiểm tra trạng thái từng nơi và chọn retry, rollback hoặc forward-fix có kiểm chứng. Kết hợp cấu hình Spring Boot rõ ràng, artifact bất biến, CI/CD theo từng target và hậu kiểm schema/data sẽ giúp migration nhất quán và có thể kiểm toán trên toàn bộ hệ thống.
