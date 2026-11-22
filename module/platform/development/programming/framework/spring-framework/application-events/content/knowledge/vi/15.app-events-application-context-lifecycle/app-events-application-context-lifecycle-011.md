# Listener phục vụ khởi tạo dữ liệu trong vòng đời ApplicationContext

## 1. Vấn đề và phạm vi

Khi ứng dụng Spring bắt đầu chạy, một số dữ liệu cần hiện diện trước khi các chức năng chính được sử dụng: danh mục trạng thái đơn hàng, nhóm quyền mặc định, mã cấu hình tham chiếu hoặc một bảng ánh xạ ổn định. Có thể viết một **listener khởi tạo dữ liệu (data initialization listener)** để thực hiện tác vụ này khi `ApplicationContext` hoàn tất giai đoạn khởi tạo.

Ví dụ: hệ thống phân quyền cần luôn có hai vai trò `ADMIN` và `VIEWER`. Tác vụ chuẩn bị phải bảo đảm:

- Khi ứng dụng chạy lần đầu, hai bản ghi được tạo với khóa nghiệp vụ xác định.
- Khi ứng dụng khởi động lại, dữ liệu không bị nhân đôi.
- Nếu một phần thao tác ghi dữ liệu thất bại, không để lại trạng thái nửa chừng.
- Nếu có context cha–con hoặc event được quan sát nhiều lần, listener không vô tình seed sai context.
- Khi seed là điều kiện bắt buộc để phục vụ request, lỗi phải được phát hiện trước khi ứng dụng được xem là sẵn sàng.

Đây là bài về **listener cho khởi tạo dữ liệu trong nhóm sự kiện vòng đời ApplicationContext**. Không nên nhầm nó với event nghiệp vụ như `OrderCreated` hay với thao tác cập nhật schema database bằng migration.

### Luồng tư duy

~~~text
ApplicationContext.refresh()
        |
        +-- đăng ký bean definitions, tạo singleton cần thiết
        +-- hoàn tất refresh context
        |
        +-- ContextRefreshedEvent
                 |
                 +-- @EventListener
                          |
                          +-- kiểm tra context nguồn
                          +-- chạy seed trong transaction
                          +-- ghi/đối chiếu dữ liệu theo khóa ổn định
                          +-- hoàn tất hoặc báo lỗi
~~~

`ContextRefreshedEvent` là điểm Spring Framework cung cấp để biết một context đã refresh xong. Listener thông thường chạy đồng bộ theo mặc định, nên nếu listener làm công việc nặng, nó kéo dài thời gian khởi động. Việc chọn nó phải dựa trên hợp đồng khởi động thật của ứng dụng.

## 2. Tại sao chọn ContextRefreshedEvent?

Spring Framework có bốn sự kiện vòng đời tiêu biểu kế thừa `ApplicationContextEvent`:

| Event | Khi phát | Có phù hợp để seed dữ liệu? |
| --- | --- | --- |
| `ContextRefreshedEvent` | Context hoàn tất refresh | Có thể phù hợp cho seed nhỏ cần bean đã khởi tạo |
| `ContextStartedEvent` | Gọi `context.start()` tường minh | Thường không phù hợp: không có ở mọi lần khởi động |
| `ContextStoppedEvent` | Gọi `context.stop()` | Không: dùng cho quan sát dừng |
| `ContextClosedEvent` | Trong quá trình `context.close()` | Không: đây là lúc shutdown, dependency đang kết thúc |

Một listener đơn giản:

~~~java
@Component
public class ReferenceDataListener {
    private final ReferenceDataService referenceDataService;

    public ReferenceDataListener(ReferenceDataService referenceDataService) {
        this.referenceDataService = referenceDataService;
    }

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        referenceDataService.ensureDefaults();
    }
}
~~~

Đây là mã **minh họa trong một dự án có sẵn** `ReferenceDataService` và cấu hình component scanning; cần import `Component`, `EventListener` và `ContextRefreshedEvent`. Spring suy ra event từ kiểu tham số. `ReferenceDataService.ensureDefaults()` nên có hợp đồng chạy lại an toàn.

Theo tài liệu Spring Framework, listener theo `ContextRefreshedEvent` hoặc `SmartInitializingSingleton` là lựa chọn hữu ích cho những công việc cần thực hiện **sau giai đoạn khởi tạo singleton**, tránh đưa quá nhiều hoạt động phức tạp vào `@PostConstruct` khi bean còn đang trong quá trình khởi tạo. Dù vậy, `ContextRefreshedEvent` chỉ cho biết **container đã refresh**; không đồng nghĩa mọi dịch vụ ngoài hệ thống đã sẵn sàng hoặc Spring Boot đã phát `ApplicationReadyEvent`.

**Cảnh báo về một lần duy nhất:** một số context có thể hỗ trợ refresh lại; context cha có thể nhận event được phát từ context con. Do đó không xem `ContextRefreshedEvent` như cơ chế “chạy chính xác một lần trên toàn cluster”.

## 3. Phân biệt seed dữ liệu với schema migration và bean initialization

Ba nhu cầu thường bị trộn lẫn:

1. **Thay đổi cấu trúc bảng:** tạo bảng, cột, index, foreign key, phiên bản schema. Dùng công cụ migration chuyên dụng như Flyway hoặc Liquibase khi vận hành thực tế.
2. **Tạo dữ liệu tham chiếu ổn định:** thêm hoặc đồng bộ bản ghi có khóa nghiệp vụ xác định, ví dụ `ADMIN` và `VIEWER`. Có thể nằm trong migration có version, script triển khai, hoặc service seed idempotent.
3. **Khởi tạo trạng thái trong bộ nhớ của một bean:** dựng cache nội bộ, xác thực cấu hình, chuẩn bị cấu trúc dữ liệu. Cân nhắc constructor, `@PostConstruct`, init method hay `SmartInitializingSingleton` tùy phụ thuộc và thời điểm.

Với dữ liệu tham chiếu **bắt buộc và mang ý nghĩa phiên bản** (như một bộ mã dữ liệu chuẩn đi cùng schema), migration chứa cả dữ liệu có thể dễ kiểm soát hơn một listener chạy lặp. Listener phù hợp khi việc seed là một bước runtime có quy tắc rõ, có thể thực hiện nhiều lần và không phụ thuộc việc chạy script một lần duy nhất.

Một listener seed không nên tự giả định rằng các bảng cần thiết luôn được tạo xong chỉ vì đã nhận `ContextRefreshedEvent`. Trong Spring Boot, cơ chế thứ tự khởi tạo database, Flyway/Liquibase, SQL initializer, JPA và các bean phụ thuộc cần được cấu hình/kiểm chứng cụ thể. Nếu phải seed sau migration, hãy biểu đạt dependency thật hoặc đặt seed vào bước khởi tạo được điều phối rõ ràng.

## 4. Thiết kế listener đúng: idempotent, transaction, khóa nghiệp vụ

### 4.1. Idempotent nghĩa là gì?

Một phép seed `S` là **idempotent về trạng thái đích** khi áp dụng nhiều lần không tạo thêm tác động dữ liệu ngoài ý định:

~~~text
S(database) = database_có_đủ_dữ_liệu_chuẩn
S(S(database)) = S(database)
~~~

Ví dụ dữ liệu cần đảm bảo:

| code | label |
| --- | --- |
| `ADMIN` | Quản trị |
| `VIEWER` | Chỉ xem |

Nếu chạy lệnh `INSERT` vô điều kiện mỗi lần refresh, lần sau có thể lỗi vì duplicate key hoặc tăng số bản ghi. Để seed an toàn:

- Xác định **khóa tự nhiên hoặc khóa nghiệp vụ** ổn định, như `code`; tạo `UNIQUE`/`PRIMARY KEY` ở database.
- Sử dụng **upsert** theo dialect database (ví dụ `MERGE` trong H2 hoặc `ON CONFLICT` trong PostgreSQL) khi chính sách là “bảo đảm dữ liệu tồn tại/đúng giá trị”.
- Nếu dữ liệu do người dùng có thể chỉnh sửa, xác định rõ cột nào thuộc quyền sở hữu của hệ thống; không được vô tình ghi đè giá trị người dùng trong mỗi lần restart.
- Dùng transaction để các bản ghi cần nhất quán cùng commit/rollback.
- Kiểm thử lần chạy đầu, lần chạy lại, trường hợp thiếu một dòng và trường hợp có nhiều instance cùng khởi động.

Idempotent về trạng thái **không tự đảm bảo mọi side effect đều đúng một lần**. Nếu seed đồng thời gửi email, mỗi lần listener chạy có thể gửi email mới ngay cả khi database không thay đổi.

### 4.2. Tại sao phải có transaction?

Giả sử seed phải tạo hai role cùng lúc. Nếu insert role đầu xong nhưng insert role thứ hai lỗi, ta muốn một policy rõ: rollback cả hai hay cho phép bổ sung lần sau. Với seed bắt buộc và cần đồng bộ, thường tạo transaction chung.

Có thể dùng `@Transactional` trên một **service được Spring gọi qua proxy**, hoặc dùng `TransactionTemplate`. Đặt transaction ở service chứa nghiệp vụ seed sẽ dễ kiểm thử hơn phụ thuộc vào chi tiết proxy của listener.

~~~java
@Service
public class BootstrapService {
    @Transactional
    public void ensureDefaults() {
        roleRepository.upsert("ADMIN", "Quản trị");
        roleRepository.upsert("VIEWER", "Chỉ xem");
    }
}
~~~

Đoạn này là mã **minh họa** vì `roleRepository.upsert(...)` là API tự định nghĩa trong ứng dụng; không phải phương thức mặc định của Spring Data. Muốn transaction thực sự được áp dụng, phải có transaction manager, gọi method qua proxy phù hợp, và resource dữ liệu tham gia cùng transaction. Theo mặc định, Spring rollback khi `RuntimeException` hoặc `Error`; checked exception cần cấu hình rollback rule nếu muốn.

## 5. Ví dụ Java 17+ chạy được: seed an toàn khi nhận ContextRefreshedEvent

Ví dụ sử dụng Spring Framework 6.2.8, Spring JDBC và H2 in-memory, **không cần Spring Boot**. Nó minh họa:

- Đăng ký bean listener trước khi context refresh.
- Dùng `@EventListener` nhận `ContextRefreshedEvent`.
- Kiểm tra chính context phát event.
- Seed hai role trong một transaction JDBC.
- Sử dụng `MERGE` theo cú pháp **H2** để chạy lại vẫn giữ đúng hai bản ghi.
- Phát lại một event **mô phỏng** để kiểm thử idempotency; việc mô phỏng event **không phải** làm refresh context lần nữa.

### 5.1. Cấu trúc thư mục

~~~text
context-seed-demo/
├── pom.xml
└── src/main/java/ContextSeedDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>context-seed-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>ContextSeedDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. Mã nguồn đầy đủ

Tệp `src/main/java/ContextSeedDemo.java`:

~~~java
import javax.sql.DataSource;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class ContextSeedDemo {

    // Chuẩn bị schema riêng cho chương trình demo.
    // Ứng dụng thực nên quản lý schema bằng Flyway hoặc Liquibase.
    public static class DemoSchema {
        public DemoSchema(JdbcTemplate jdbc) {
            jdbc.execute(
                "CREATE TABLE role_catalog ("
                + "code VARCHAR(20) PRIMARY KEY, "
                + "label VARCHAR(100) NOT NULL)"
            );
        }
    }

    public static class SeedOnRefresh {
        private final ApplicationContext owner;
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transaction;

        public SeedOnRefresh(
                ApplicationContext owner,
                JdbcTemplate jdbc,
                TransactionTemplate transaction
        ) {
            this.owner = owner;
            this.jdbc = jdbc;
            this.transaction = transaction;
        }

        @EventListener
        public void onContextRefreshed(ContextRefreshedEvent event) {
            if (event.getApplicationContext() != owner) {
                return; // Bỏ qua event của một context khác.
            }

            transaction.executeWithoutResult(status -> {
                seedRole("ADMIN", "Quản trị");
                seedRole("VIEWER", "Chỉ xem");
            });

            int count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM role_catalog", Integer.class
            );
            System.out.println("SEED count=" + count);
        }

        private void seedRole(String code, String label) {
            // MERGE ... KEY là cú pháp H2 cho ví dụ.
            // Database khác cần câu lệnh upsert theo dialect tương ứng.
            jdbc.update(
                "MERGE INTO role_catalog (code, label) "
                + "KEY (code) VALUES (?, ?)",
                code, label
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:seed_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbc(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager
        ) {
            return new TransactionTemplate(manager);
        }

        @Bean
        DemoSchema demoSchema(JdbcTemplate jdbc) {
            return new DemoSchema(jdbc);
        }

        @Bean
        @DependsOn("demoSchema")
        SeedOnRefresh seedOnRefresh(
                ApplicationContext context,
                JdbcTemplate jdbc,
                TransactionTemplate transaction
        ) {
            return new SeedOnRefresh(context, jdbc, transaction);
        }
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM role_catalog", Integer.class
        );
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            context.setId("seed-demo");
            context.register(Config.class);
            context.refresh();

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            System.out.println(
                "AFTER_REFRESH count=" + count(jdbc)
            );

            // Chỉ mô phỏng việc giao lại event để kiểm tra idempotency.
            // Lệnh này KHÔNG thực hiện context.refresh() lần thứ hai.
            context.publishEvent(new ContextRefreshedEvent(context));

            System.out.println(
                "AFTER_REPLAY count=" + count(jdbc)
            );
        }
    }
}
~~~

Tại thư mục `context-seed-demo/`, sử dụng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do chương trình tự in ra theo thứ tự (không kể thông báo phụ thuộc môi trường của Maven):

~~~text
SEED count=2
AFTER_REFRESH count=2
SEED count=2
AFTER_REPLAY count=2
~~~

### 5.3. Giải thích theo từng mốc

**Khởi tạo context:** `context.register(Config.class)` đăng ký cấu hình, còn `context.refresh()` tạo các singleton. Bean `demoSchema` dựng bảng; `@DependsOn("demoSchema")` chỉ rõ listener phụ thuộc bước chuẩn bị bảng. Sau đó Spring phát `ContextRefreshedEvent` và listener đã được đăng ký nhận event.

**Seed lần đầu:** listener so sánh `event.getApplicationContext()` với bean context mà nó thuộc về. Nếu là đúng context, `TransactionTemplate` mở transaction, thực hiện hai câu `MERGE` rồi commit. `SEED count=2` cho thấy hai role hiện diện. `AFTER_REFRESH count=2` chứng minh dữ liệu đã có khi `refresh()` trả về.

**Phát lại event trong test:** `context.publishEvent(new ContextRefreshedEvent(context))` là một thao tác mô phỏng **được viết có chủ đích để kiểm thử**. Nó khiến listener nhận lại cùng loại event, nhưng không chạy pipeline refresh, không khởi tạo lại bean và không có ý nghĩa làm mới context. Hai lần `MERGE` tiếp tục bảo đảm cùng hai mã role, không tạo bản ghi thứ ba. `AFTER_REPLAY count=2` là bằng chứng về trạng thái dữ liệu cuối cùng.

**H2 và tính di động:** `MERGE INTO ... KEY (code)` là cú pháp H2; PostgreSQL có cú pháp `INSERT ... ON CONFLICT ... DO UPDATE`, một số database khác dùng chiến lược upsert khác. Cấu trúc JDBC transaction của ví dụ mang tính tổng quát, nhưng phải sửa SQL seed theo database thực tế.

**Vì sao dùng @DependsOn?** Nó xác nhận thứ tự tạo bean trong ví dụ. Trong ứng dụng thực, không dùng `@DependsOn` thay cho công cụ migration ở môi trường nhiều instance. Ở đây `DemoSchema` chỉ phục vụ ví dụ độc lập, không phải kiến trúc migration để dùng trong production.

## 6. Khi nào listener seed phải làm startup thất bại?

Nếu dữ liệu khởi tạo là **bắt buộc** để ứng dụng hoạt động đúng, lựa chọn an toàn thường là thất bại có thể quan sát, thay vì bỏ qua lỗi và vẫn báo sẵn sàng. Với `SimpleApplicationEventMulticaster` mặc định (không có executor async hay `ErrorHandler` nuốt lỗi), phương thức `@EventListener` chạy đồng bộ; exception chưa được xử lý có thể truyền ra từ bước phát `ContextRefreshedEvent`, làm quá trình `refresh()` thất bại.

Ví dụ trong service (mã minh họa):

~~~java
public void ensureDefaults() {
    if (!catalogStorage.isAvailable()) {
        throw new IllegalStateException(
            "Cannot initialize required catalog"
        );
    }
    catalogStorage.upsertRequiredEntries();
}
~~~

Nếu application cần dữ liệu này **trước khi nhận traffic**, cần kết nối thất bại khởi tạo với trạng thái startup/readiness thực tế. Đừng chỉ log lỗi rồi tiếp tục. Với Spring Boot, có thể lựa chọn `ApplicationRunner` hoặc `CommandLineRunner` chạy trước khi ứng dụng được xem là sẵn sàng theo chuỗi lifecycle Boot, phù hợp với công việc cuối giai đoạn khởi động.

Ngược lại, nếu seed một cache phụ trợ có thể phục hồi hoặc một projection không bắt buộc, không nhất thiết phải làm toàn bộ startup thất bại. Nhưng cần báo trạng thái degraded, có retry/giám sát và tránh trả “ready” sai khi endpoint thực sự cần cache ấy.

### Listener đồng bộ không phải giải pháp cho mọi loại khởi tạo

Mặc định `@EventListener` xử lý đồng bộ; một seed lớn có thể làm `refresh()` kéo dài, gây timeout hoặc tăng thời gian rolling deployment. Tránh tải hàng triệu dòng hoặc gọi nhiều API mạng trong listener chỉ vì đây là điểm dễ gắn mã. Tách batch job/migration hoặc công việc hậu khởi động phù hợp khi thời gian thực thi và độ tin cậy đòi hỏi.

`@Async` có thể làm listener trả về nhanh, nhưng lại khiến ứng dụng có thể nhận request trước khi seed hoàn tất; exception từ task async không tự truyền về publisher như listener đồng bộ. Nếu seed là điều kiện bắt buộc, cần cơ chế readiness/blocking được thiết kế riêng trước khi cho nhận traffic.

## 7. Context cha–con và nhiều instance

### 7.1. Context hierarchy: event có thể lan lên context cha

Trong Spring, event phát từ context con có thể lan lên context cha. Một listener đặt trong parent context vì thế có thể nhận `ContextRefreshedEvent` do child context phát ra. Nếu không lọc nguồn, cùng một logic seed có thể chạy lại tại thời điểm không mong muốn.

Một cách rõ ràng là inject context sở hữu listener rồi kiểm tra:

~~~java
@EventListener
public void seed(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != owningContext) {
        return;
    }
    seedService.ensureDefaults();
}
~~~

`owningContext` là bean `ApplicationContext` được inject vào listener; `seedService` là service của ứng dụng. Đoạn mã là minh họa và chỉ chạy khi đặt trong bean listener. So sánh **đối tượng context** tránh nhầm nếu ID bị cấu hình giống nhau. Trong ví dụ đầy đủ, phép so sánh này đã xuất hiện trực tiếp trong `SeedOnRefresh`.

Không nên giải quyết trùng event chỉ bằng `AtomicBoolean seeded` trong một JVM. Cờ bộ nhớ có thể giúp bỏ qua tác vụ không cần thiết trong một instance, nhưng không bảo vệ database khi có **hai instance, hai process, rolling deployment hoặc test tạo nhiều context**.

### 7.2. Nhiều instance: unique constraint và concurrency

Khi hai pod khởi động đồng thời, cả hai có thể nhận event refresh và thực hiện seed trên cùng database. Mẫu “`SELECT COUNT(*)`; nếu 0 thì `INSERT`” bị **race condition**:

~~~text
Instance A: SELECT, chưa có ADMIN
Instance B: SELECT, chưa có ADMIN
Instance A: INSERT ADMIN
Instance B: INSERT ADMIN  -> duplicate key hoặc dữ liệu bị trùng
~~~

Giải pháp đáng tin phải nằm ở tầng dữ liệu và điều phối:

- Ràng buộc `UNIQUE`/`PRIMARY KEY` bắt buộc cho khóa nghiệp vụ.
- Upsert nguyên tử theo database và xử lý xung đột đúng cách.
- Transaction phù hợp để seed nhiều bản ghi nhất quán.
- Khi phải thực hiện một bước duy nhất trên toàn cluster (ví dụ chuyển đổi dữ liệu không idempotent), dùng migration coordinator, database lock/distributed lock hoặc job triển khai riêng; chỉ một flag trong singleton không đủ.

`@Order` giữa listener chỉ ảnh hưởng thứ tự xử lý trong một event/context theo cơ chế Spring tương ứng; nó **không điều phối nhiều JVM**, không thay thế transaction hay unique constraint.

## 8. Chọn phương án khởi tạo phù hợp

| Nhu cầu | Điểm xuất phát | Điểm cần lưu ý |
| --- | --- | --- |
| Chuẩn bị trường nội bộ của một bean | Constructor hoặc `@PostConstruct` | Không đặt công việc nặng phụ thuộc nhiều bean khác trong creation lock |
| Chạy một bước sau khi các singleton thông thường đã được tạo | `SmartInitializingSingleton` | Gắn với giai đoạn khởi tạo singleton; không phải event nghiệp vụ |
| Seed nhỏ cần Spring bean và mốc context refresh | `@EventListener(ContextRefreshedEvent.class)` | Idempotent, transaction, kiểm tra context nguồn |
| Công việc sau Spring Boot startup nhưng trước khi app được xem là ready | `ApplicationRunner`/`CommandLineRunner` | Thuộc Spring Boot; mốc khác `ContextRefreshedEvent` |
| Cần phản ứng sau Spring Boot hoàn tất runners | `ApplicationReadyEvent` | Thời điểm muộn hơn; nếu tác vụ là điều kiện readiness phải cân nhắc lifecycle |
| Schema hoặc dữ liệu tham chiếu có version | Flyway/Liquibase/migration | Theo dõi version, rollback và thứ tự triển khai |
| Khởi chạy/dừng một consumer theo phase | `SmartLifecycle` | Có start/stop và điều phối shutdown |
| Nạp dữ liệu lớn hoặc chuyển đổi phức tạp | Batch job/migration riêng | Có checkpoint, resume, giới hạn tải, quan sát tiến độ |
| Bổ sung cache có thể phục hồi sau startup | Worker nền có giám sát | Readiness và hành vi trước khi cache nóng phải rõ |

### Tránh nhầm các mốc của Spring Boot

Spring Boot phát `ApplicationStartedEvent` sau khi context refresh nhưng **trước** `ApplicationRunner`/`CommandLineRunner`, còn `ApplicationReadyEvent` xuất hiện sau khi các runner hoàn tất. `ContextRefreshedEvent` thuộc Spring Framework và có mốc sớm hơn readiness của Boot. Vì vậy cùng một tên “startup” có thể dẫn đến lựa chọn sai về lúc dữ liệu phải sẵn sàng.

Một người viết `@EventListener(ContextStartedEvent.class)` thay vì `ContextRefreshedEvent` có thể không thấy listener chạy ở lúc khởi động mặc định vì `ContextStartedEvent` gắn với lời gọi `context.start()` tường minh, không đồng nghĩa khởi tạo context lần đầu.

## 9. Kiểm thử listener khởi tạo dữ liệu

Đối với seed có yêu cầu ổn định, kiểm thử cả **kết quả dữ liệu sau mốc lifecycle** và hành vi khi lỗi.

| Ca kiểm thử | Điều cần chứng minh |
| --- | --- |
| Tạo context mới với DB trống | Dữ liệu bắt buộc xuất hiện khi refresh hoàn tất |
| Phát lại event cùng context | Không tăng số bản ghi, không sinh side effect không mong muốn |
| Database đã có đầy đủ dữ liệu | Chạy lại không làm hỏng dữ liệu hợp lệ |
| Database chỉ thiếu một bản ghi | Chỉ bổ sung/sửa đúng bản ghi theo policy |
| Một lệnh seed phát sinh exception | Transaction rollback các thay đổi thuộc cùng transaction |
| Context cha–con | Listener chỉ xử lý đúng context mong muốn |
| Hai instance cùng khởi động | Không có duplicate nhờ unique/upsert hoặc cơ chế điều phối |
| Bean listener chưa đăng ký hoặc lazy | Test phát hiện listener không nhận event cần thiết |
| Sai thứ tự migration/schema | Startup báo lỗi rõ; không để app ready với schema thiếu |
| Executor async/exception handler được cấu hình | Kiểm tra lại hợp đồng blocking và lỗi; không mặc định giống xử lý đồng bộ |

Không nên chỉ xác nhận log `SEED count=2` rồi kết luận giao dịch thật đã commit. Với integration test, query dữ liệu **sau khi bước startup/transaction đã kết thúc**, và cần tránh để toàn bộ bài test bị một transaction test bao ngoài khiến dữ liệu nhìn thấy khác thực tế triển khai.

Đối với lỗi, hãy thử làm một câu `MERGE` cố ý vi phạm constraint để xác nhận cả transaction rollback; không chỉ kiểm tra exception text. Khi test một context bằng `AnnotationConfigApplicationContext`, **không gọi lại `refresh()` lần thứ hai** vì loại context này không hỗ trợ hot refresh lặp như một số context khác. Trong ví dụ, một `ContextRefreshedEvent` được publish thủ công chỉ nhằm thử idempotency, không thực hiện refresh thứ hai.

### Quan sát trong production

Nên có log và metrics cho: thời gian seed, số dòng thêm/cập nhật, số lần thử, lỗi SQL/constraint, trạng thái startup và phiên bản seed. Tránh log mật khẩu, token hoặc dữ liệu nhạy cảm. Khi có nhiều node, gắn instance ID và context ID để phân biệt các lần chạy.

Nếu seed cần dùng feature flag hoặc profile, kiểm tra `Environment` trước khi thực thi. Nhưng đừng biến data bắt buộc thành logic “âm thầm bỏ qua” chỉ vì property thiếu. Chính sách khi flag tắt cần được đặc tả rõ.

## 10. Những lỗi phổ biến

1. **INSERT vô điều kiện sau mỗi refresh:** trùng dữ liệu hoặc gây duplicate key. Dùng khóa nghiệp vụ và idempotent upsert.
2. **Dùng ContextStartedEvent để chờ ứng dụng khởi tạo lần đầu:** event này yêu cầu thao tác `start()` tường minh; thường nên xét `ContextRefreshedEvent`.
3. **Coi ContextRefreshedEvent đồng nghĩa Spring Boot ready:** Boot còn các bước runners/readiness sau refresh.
4. **Nhét seed nặng vào @PostConstruct:** có thể xảy ra trong singleton creation lock, khi các phụ thuộc khác chưa hoàn tất.
5. **Seed trước khi bảng/schema sẵn sàng:** mô tả rõ thứ tự migration và dependencies; không dựa vào may rủi.
6. **Không dùng transaction cho nhiều bản ghi phải cùng thành công:** để lại dữ liệu khởi tạo nửa chừng.
7. **Dựa vào biến boolean trong singleton để ngăn hai pod seed:** không giải quyết concurrency liên tiến trình.
8. **Chỉ kiểm tra COUNT trước INSERT:** vẫn có race condition; dùng unique/upsert/lock phù hợp.
9. **Không lọc context cha–con:** listener của cha có thể xử lý event do con phát.
10. **Nuốt lỗi seed bắt buộc:** ứng dụng vẫn ready dù thiếu dữ liệu quan trọng.
11. **Đặt async cho seed bắt buộc:** request có thể đến trước khi dữ liệu sẵn sàng, lỗi async không tự làm startup thất bại.
12. **Đưa schema migration vào mỗi event refresh:** thay đổi DDL không có hợp đồng migration/version an toàn.
13. **Ghi đè dữ liệu người dùng mỗi lần restart:** cần chính sách ownership và cơ chế bảo toàn các chỉnh sửa hợp lệ.
14. **Tạo tài khoản quản trị với mật khẩu mặc định trong seed:** gây rủi ro nghiêm trọng; dùng quy trình provisioning bí mật và đổi mật khẩu an toàn.
15. **Tự publish ContextRefreshedEvent để “khởi động lại” ứng dụng:** publish object event không chạy lại pipeline refresh hoặc tạo bean.

## 11. Bài tập tự kiểm tra

1. Vì sao listener khởi tạo role nên nhận `ContextRefreshedEvent` thay vì `ContextStartedEvent`?
2. Tại sao `@PostConstruct` không phải lúc nào cũng thích hợp để gọi nhiều service/DB khi bootstrap?
3. Trong ví dụ H2, chạy lại event hai lần có làm bảng có bốn role không? Vì sao?
4. Nếu hai pod cùng chạy seed, một `AtomicBoolean` trong bean có đủ ngăn dữ liệu trùng không?
5. Nếu một trong hai lệnh `MERGE` lỗi, `TransactionTemplate` giúp đảm bảo điều gì đối với cùng transaction?
6. Nếu cần version hoá hàng trăm bản ghi tham chiếu theo release, có nhất thiết nên đặt trong listener không?
7. Vì sao `getApplicationContext() != owner` giúp tránh nhận nhầm event trong context hierarchy?
8. Nếu seed là bước bắt buộc nhưng được đưa sang `@Async`, readiness có thể sai theo cách nào?
9. Phát thủ công `new ContextRefreshedEvent(context)` có gọi lại lifecycle `refresh()` không?
10. Khi dữ liệu được người dùng chỉnh sửa, tại sao một seed “upsert mọi cột” có thể phá dữ liệu?

**Định hướng trả lời:** (1) refresh là mốc container khởi tạo, start là thao tác tường minh; (2) bean còn trong quá trình khởi tạo và có rủi ro về phụ thuộc/creation lock; (3) không, `MERGE` theo khóa `code` giữ hai bản ghi; (4) không, mỗi pod có bộ nhớ riêng; (5) rollback các thay đổi thuộc transaction khi exception phù hợp; (6) cân nhắc migration có version; (7) lọc đúng đối tượng context; (8) app nhận request trước khi seed hoàn tất; (9) không, chỉ phát một object event; (10) ghi đè trạng thái do người dùng sở hữu.

## Tài liệu tham khảo

- Spring Framework Reference — *Application Events / Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference — *Lifecycle Callbacks and Initialization*: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework Reference — *Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2.8 Javadoc — *ContextRefreshedEvent*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html
- Spring Framework 6.2.8 Javadoc — *TransactionTemplate*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Boot Reference — *Application Events and ApplicationRunner*: https://docs.spring.io/spring-boot/reference/features/spring-application.html
