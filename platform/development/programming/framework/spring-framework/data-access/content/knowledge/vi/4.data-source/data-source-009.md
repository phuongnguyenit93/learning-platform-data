# Đóng nhóm kết nối theo vòng đời container trong Spring Framework

> **Chủ đề:** DataSource. Bài học giải thích khi nào và bằng cách nào phải **đóng connection pool** theo vòng đời của Spring IoC container, cách phân biệt đóng từng `Connection` với đóng cả `DataSource`, và ai chịu trách nhiệm dọn tài nguyên khi ứng dụng dừng. Các ví dụ chủ yếu dùng HikariCP, Spring Framework và Spring Boot; nguyên tắc sở hữu vòng đời còn áp dụng cho những pool khác nếu chúng hỗ trợ phương thức shutdown tương ứng.

## 1. Vì sao pool cần được đóng?

Một ứng dụng Java dùng JDBC thường phải lấy kết nối tới database liên tục. Tạo một kết nối vật lý có thể tốn thời gian và tài nguyên, nên một **connection pool** giữ một tập kết nối để nhiều thao tác mượn và trả lại. Spring thường cung cấp pool cho các Repository/DAO qua một bean `DataSource`.

Trong suốt thời gian ứng dụng hoạt động, pool quản lý:

- Kết nối vật lý đến DBMS, bao gồm socket và session có thể chiếm quota trên server.
- Các kết nối đang được mượn (active), kết nối nhàn rỗi (idle) và yêu cầu đang chờ được cấp kết nối.
- Các tác vụ nền và cấu trúc quản trị nội bộ của pool, ví dụ kiểm tra vòng đời kết nối và các bộ đếm.
- Cấu hình timeout, giới hạn số kết nối và các cơ chế kiểm tra kết nối.

Khi ứng dụng thật sự **dừng**, pool không còn được phục vụ request nào nữa; tài nguyên mà nó sở hữu phải được giải phóng. Nếu bỏ qua bước này, đặc biệt trong test tạo nhiều Spring context, chạy tác vụ nhiều lần trong một JVM hoặc hot redeploy, tài nguyên có thể tồn tại lâu hơn dự kiến. Ở một tiến trình JVM đã bị hệ điều hành kết thúc hoàn toàn, socket rồi sẽ được thu hồi ở cấp hệ điều hành; tuy nhiên không nên dựa vào kết thúc cưỡng bức để thay thế một quy trình shutdown có kiểm soát.

**Nguyên tắc chính:** **Thành phần sở hữu pool chịu trách nhiệm đóng pool khi vòng đời của nó kết thúc.** Nếu bean pool do Spring container tạo và quản lý, hãy đăng ký callback hủy bean để Spring gọi khi context đóng. Nếu DataSource do application server/JNDI quản lý, chính hệ thống sở hữu bên ngoài chịu trách nhiệm đóng nó.

## 2. Phân biệt ba hành động thường bị nhầm

| Hành động | Ví dụ | Thực chất | Khi nào? |
| --- | --- | --- | --- |
| Trả một kết nối đã mượn về pool | `connection.close()` đối với kết nối do HikariCP cấp | Thường đóng **logical handle**, đưa kết nối về pool để tái sử dụng; không tắt cả pool | Sau mỗi đơn vị làm việc; có thể qua `try-with-resources` hoặc Spring JDBC |
| Đóng toàn bộ pool | `hikariDataSource.close()` | Pool ngừng phục vụ, tiến hành dọn kết nối/tài nguyên nội bộ; những lần lấy Connection tiếp theo từ pool đã đóng sẽ thất bại | Khi **chủ sở hữu** pool kết thúc vòng đời |
| Đóng Spring container | `context.close()` | Spring chạy quy trình đóng context, stop các lifecycle beans và hủy singleton beans được quản lý; gọi destroy callback đã đăng ký của pool | Khi ứng dụng, test context hoặc subsystem cần kết thúc |

Ví dụ:

~~~java
// Minh họa một đoạn đang chạy; biến dataSource do Spring quản lý.
// Đóng Connection sau thao tác JDBC là bình thường.
try (java.sql.Connection connection = dataSource.getConnection()) {
    // Thực thi JDBC bằng connection.
}
// HikariDataSource vẫn hoạt động sau khi logical connection được trả về.

// Chỉ chủ sở hữu pool mới gọi hàm sau khi TOÀN BỘ ứng dụng đã hết dùng pool:
// hikariDataSource.close();
~~~

**Không đưa `dataSource.close()` vào DAO, Repository, Service hoặc `finally` của từng HTTP request.** Nếu một request tự đóng pool dùng chung, những request khác có thể không còn lấy được kết nối. Với `JdbcTemplate` hoặc JPA, framework thường quản lý việc mượn/trả kết nối theo ngữ cảnh truy cập dữ liệu/giao dịch; lập trình viên vẫn cần cấu hình vòng đời pool đúng, nhưng không phải tự gọi `Connection.close()` quanh mỗi `JdbcTemplate.update()`.

Lưu ý: `javax.sql.DataSource` là **giao diện lấy kết nối**, không có phương thức `close()` chung. Việc đóng pool phụ thuộc vào loại implementation cụ thể, chẳng hạn `HikariDataSource.close()`, hoặc destroy callback do cấu hình Spring đăng ký. Không ép kiểu mọi `DataSource` thành HikariCP.

## 3. Pool sống cùng ApplicationContext như thế nào?

Vòng đời điển hình của một bean pool do Spring sở hữu:

~~~mermaid
flowchart TD
    A["Tạo ApplicationContext"] --> B["Tạo/configure DataSource bean"]
    B --> C["Khởi tạo pool khi cần hoặc khi tạo DataSource"]
    C --> D["Service/DAO dùng JDBC, mượn và trả Connection"]
    D --> E{"ApplicationContext được close?"}
    E -- "Chưa" --> D
    E -- "Có" --> F["Phát tín hiệu đóng, dừng các Lifecycle/SmartLifecycle beans"]
    F --> G["Hủy các singleton beans được quản lý"]
    G --> H["Gọi callback close/shutdown của pool"]
    H --> I["Pool đóng; giải phóng tài nguyên thuộc pool"]
~~~

Đây là **sơ đồ trách nhiệm**, không phải cam kết rằng mọi loại ứng dụng đều có cùng thứ tự vi mô cho mọi callback. Spring có các giai đoạn stop và destroy riêng; các bean còn có quan hệ phụ thuộc và phase. Điểm quan trọng là **pool phải còn khả dụng trong khi công việc cần database vẫn đang hoàn tất**, và phải bị đóng khi context thực sự hủy các tài nguyên mình sở hữu.

### Phân biệt `stop()` và `close()` trên context

- `ConfigurableApplicationContext.close()` đóng context và kích hoạt hủy các singleton beans được quản lý.
- `ConfigurableApplicationContext.stop()` gửi tín hiệu stop cho các thành phần Lifecycle thích hợp; **không đồng nghĩa** với việc hủy toàn bộ bean singleton hoặc đóng pool theo destroy method.
- `refresh()` không phải lệnh shutdown; việc hủy và tái tạo bean trong một số trường hợp được quyết định bởi implementation của context và các quy tắc quản lý scope.
- Spring Boot thường đăng ký **JVM shutdown hook** để đóng ApplicationContext khi JVM thoát bình thường. Việc gọi `context.close()` trực tiếp vẫn hữu ích trong chương trình console/test để xác định thời điểm đóng chính xác.

Nếu container không có cơ hội chạy shutdown callback (ví dụ tiến trình bị `SIGKILL`, crash/halt, mất điện), không thể bảo đảm một lệnh `close()` Java sẽ thực thi. Bởi vậy, ứng dụng vẫn cần cơ chế chịu lỗi khi connection rơi đột ngột ở tầng database và vận hành.

## 4. Ai sở hữu DataSource? Ba trường hợp quyết định cách đóng

| Trường hợp | Ai tạo và sở hữu pool? | Cách xử lý đúng |
| --- | --- | --- |
| Spring Boot tự cấu hình HikariCP từ `spring.datasource.*` | ApplicationContext của ứng dụng | Để Spring quản lý lifecycle; khi context đóng, DataSource bean được destroy và pool bị đóng |
| Tự khai báo `@Bean HikariDataSource` trong config Spring | ApplicationContext nếu bean đó sở hữu pool | Đăng ký `destroyMethod = "close"` hoặc dùng cơ chế destroy được Spring nhận diện; không gọi từ từng request |
| Lấy DataSource qua JNDI từ application server hoặc môi trường cấp ngoài | Container bên ngoài, ví dụ application server | **Không để Spring đóng pool của bên ngoài**; tắt automatic destroy inference nếu tạo `@Bean` proxy/lookup phù hợp |

Thêm hai trường hợp dễ quên:

- Nếu một thư viện hoặc code tự gọi `new HikariDataSource(...)` **ngoài Spring** và không chuyển quyền sở hữu lifecycle cho Spring, Spring không tự động biết object đó để gọi `close()`. Chính đoạn code tạo nó phải có quy trình đóng.
- Nếu tạo nhiều `ApplicationContext` hoặc nhiều pool cho nhiều database/tenant, mỗi pool phải có một **chủ sở hữu xác định**. Không dùng một bean destroy callback để vô tình đóng pool vẫn đang phục vụ một context/đơn vị khác.

Đôi khi cùng một object được expose bằng nhiều tên bean hoặc được tham chiếu từ nhiều context. Cần quyết định **một lifecycle owner** rõ ràng; tránh tình huống hai context độc lập đều cho rằng chúng có quyền đóng một tài nguyên chia sẻ.

## 5. Spring kích hoạt destroy callback cho bean bằng cách nào?

Spring có nhiều cách khai báo callback hủy tài nguyên. Mục đích giống nhau: đăng ký cách dọn tài nguyên với **container** để không phải gọi thủ công ở tầng nghiệp vụ.

### 5.1. Khai báo tường minh với `@Bean(destroyMethod = "close")`

~~~java
// Minh họa cấu hình: class này nằm trong ứng dụng có Spring và HikariCP.
@Configuration(proxyBeanMethods = false)
class DataSourceConfig {
    @Bean(destroyMethod = "close")
    HikariDataSource dataSource() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:h2:mem:demo");
        config.setUsername("sa");
        config.setMaximumPoolSize(5);
        return new HikariDataSource(config);
    }
}
~~~

Khi bean này là singleton do Spring quản lý và context đóng, Spring gọi `close()` như destroy method của bean. Đây là cách diễn đạt rõ ràng, dễ review rằng pool do context sở hữu. Với `@Bean`, Spring còn **tự suy luận destroy method** tên `close` hoặc `shutdown` công khai, không tham số khi sử dụng chế độ mặc định `(inferred)`. Vì vậy, với HikariDataSource được tạo đúng dưới dạng `@Bean`, việc viết `destroyMethod = "close"` thường là cách làm tường minh, không phải một bước bắt buộc để suy luận hoạt động.

### 5.2. Các cơ chế khác

- `@PreDestroy` (trong Spring hiện đại dùng `jakarta.annotation.PreDestroy`) trên phương thức dọn tài nguyên của bean.
- Interface `org.springframework.beans.factory.DisposableBean` với `destroy()`.
- Thuộc tính `@Bean(destroyMethod = "...")` để gọi một phương thức no-arg thích hợp.
- XML bean definition dùng `destroy-method`, nếu ứng dụng cấu hình bằng XML.

Nếu nhiều cơ chế destroy **khác phương thức** được khai báo trên cùng bean, thứ tự điển hình của Spring là `@PreDestroy` → `DisposableBean.destroy()` → custom destroy method. Không nên cố tình gọi đóng cùng pool nhiều lần từ những callback khác nhau; hãy để **một đường quản lý pool** rõ ràng. Dùng `@PreDestroy` của một Service để tự gọi `dataSource.close()` thường là sai quyền sở hữu, vì service không nhất thiết là bên cuối cùng cần database.

### 5.3. Vòng đời bean phụ thuộc scope

Destroy callback tự động đáng tin cậy nhất cho **singleton bean được Spring container quản lý**. Prototype bean được Spring tạo nhưng thường không nhận chu kỳ tự động destroy đầy đủ như singleton; bên sử dụng prototype phải lo việc dọn tài nguyên cần thiết. Do đó, một connection pool phổ biến nên được định nghĩa là **singleton có owner rõ ràng**, không tạo pool mới cho mỗi request/prototype bean.

## 6. Spring Boot auto-configured DataSource: phần lớn ứng dụng không cần viết code đóng pool

Với Spring Boot, nếu bổ sung `spring-boot-starter-jdbc` hoặc `spring-boot-starter-data-jpa`, dependency thường có HikariCP. Khi không có DataSource bean tùy chỉnh và cấu hình phù hợp, Spring Boot thường chọn HikariCP làm pool.

Ví dụ trong `application.properties`:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/lesson
spring.datasource.username=lesson_user
spring.datasource.password=replace-with-secret-from-environment
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=30000
~~~

Đây chỉ là ví dụ thuộc tính; thực tế nên nhận password từ biến môi trường/secret manager thay vì lưu bí mật vào repo. Khi Boot sở hữu pool, **đừng tạo thêm một `@PreDestroy` trong Controller/Service để gọi `HikariDataSource.close()`**. Spring container đã có cơ chế destroy bean khi đóng context.

### Cách ứng dụng Boot kết thúc

Trong ứng dụng Boot khởi động thông thường bằng `SpringApplication.run(...)`, Boot đăng ký shutdown hook của JVM để đóng context vào lúc JVM thoát bình thường. Trong job/CLI hoặc bài test cần kết thúc đúng lúc, có thể đóng context tường minh:

~~~java
// Minh họa trong một ứng dụng đã định nghĩa App.class là @SpringBootApplication.
try (org.springframework.context.ConfigurableApplicationContext context =
         org.springframework.boot.SpringApplication.run(App.class, args)) {
    // Làm việc khi context còn mở.
} // context.close() chạy khi thoát khỏi try.
~~~

Snippet này chỉ minh họa quản lý context; `App` và build Boot chưa được định nghĩa tại đây. Ví dụ **chạy độc lập** đầy đủ với Spring Framework được trình bày ở phần 8.

### Tắt ứng dụng web có request đang chạy

Khi dùng Spring Boot 3.3 với embedded web server hỗ trợ, có thể cấu hình graceful shutdown:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Trong giai đoạn shutdown, server ngừng tiếp nhận hoặc từ chối request mới theo cách phù hợp với implementation và cho request đang chạy thời gian kết thúc. Khi giai đoạn stop hoàn tất, Spring tiếp tục phá hủy singleton beans, bao gồm pool được quản lý. **Graceful shutdown không có nghĩa bảo đảm mọi request sẽ hoàn tất vô hạn thời gian**: timeout, thao tác JDBC đang treo và cách nền tảng gửi tín hiệu dừng vẫn quyết định kết quả thực tế. Cần thiết kế timeout cho JDBC, transaction và yêu cầu đầu vào hợp lý.

## 7. Cơ chế stop nền trước, đóng pool sau

Một câu hỏi khó thường gặp: nếu có scheduled job, message listener hoặc worker thread đang dùng database thì sao?

Mô hình an toàn về mặt thiết kế:

1. Nhận tín hiệu ngừng phục vụ, ngăn công việc mới bắt đầu hoặc điều chỉnh readiness/routing.
2. Yêu cầu những worker/listener đang thực hiện tác vụ hoàn tất hoặc hủy có kiểm soát trong thời hạn rõ.
3. Đợi các transaction/Connection đang sử dụng kết thúc theo chính sách thích hợp.
4. Cho Spring thực hiện destroy bean của pool, đóng kết nối và tài nguyên thuộc pool.
5. Kết thúc process hoặc hoàn thành quá trình ngừng subsystem.

Trong Spring, `Lifecycle`/`SmartLifecycle` cho phép một component tham gia giai đoạn start/stop của context. Với `SmartLifecycle`, `getPhase()` và callback `stop(Runnable callback)` cho phép phối hợp thứ tự/hoàn tất stop theo quy định. **Phase cao dừng trước phase thấp** trong nhóm lifecycle được điều phối; quan hệ phụ thuộc tường minh cũng ảnh hưởng thứ tự. Giai đoạn stop thông thường diễn ra **trước** destroy callbacks của singleton beans. Không cần biến mọi Repository thành `SmartLifecycle`; cơ chế này chủ yếu hữu ích với bean tự quản lý công việc chạy nền.

~~~java
// Fragment minh họa, KHÔNG phải chương trình chạy độc lập.
@Override
public void stop(Runnable callback) {
    consumer.pauseAcceptingNewWork();
    consumer.finishOrCancelCurrentWork();
    callback.run(); // Báo đã hoàn tất stop cho LifecycleProcessor.
}
~~~

Không gọi `callback.run()` sớm nếu worker còn thực sự sử dụng database; cũng không chặn vô hạn khi shutdown. Việc kết thúc các tác vụ bất đồng bộ cần cơ chế phối hợp thực tế, timeout và xử lý lỗi. Nếu chỉ dùng Spring MVC thông thường và không tự tạo thread nền, có thể dựa vào vòng đời tích hợp của server và pool.

### Điều cần tránh khi có các callback shutdown

- `ContextClosedEvent` báo context bắt đầu đóng; listener không nên giả định nó được phép chạy giao dịch dài hoặc luôn chạy theo đúng thứ tự so với mọi bean khác.
- Không thực hiện một giao dịch JDBC phức tạp trong `@PreDestroy` nếu nó còn phụ thuộc vào nhiều bean đã/đang bị hủy; ưu tiên hoàn tất công việc trong giai đoạn stop có thứ tự.
- Không xem `HikariDataSource.close()` là cơ chế “đợi mọi request hoàn tất” thay cho phối hợp shutdown; pool shutdown không thay thế việc ngừng request/worker theo thứ tự hợp lý.
- Không dùng shutdown callback để sửa dữ liệu sau một lần `SIGKILL`; callback có thể không bao giờ được gọi trong trường hợp đó.

## 8. Ví dụ chạy được: đóng HikariCP khi đóng Spring container

Ví dụ chạy bằng **Java 21**, **Gradle**, **Spring Framework 6.1.14**, **HikariCP 5.1.0** và **H2 2.3.232**. Đây là ứng dụng console Spring Framework thuần để nhìn thấy chính xác chủ sở hữu pool; không cần web server hoặc Spring Boot.

Cấu trúc project:

~~~text
pool-lifecycle-demo/
├── build.gradle
└── src/main/java/demo/PoolLifecycleLesson.java
~~~

### 8.1. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'demo.PoolLifecycleLesson'
}

dependencies {
    implementation platform('org.springframework:spring-framework-bom:6.1.14')
    implementation 'org.springframework:spring-context'
    implementation 'org.springframework:spring-jdbc'
    implementation 'com.zaxxer:HikariCP:5.1.0'
    runtimeOnly 'com.h2database:h2:2.3.232'
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.16'
}
~~~

### 8.2. `src/main/java/demo/PoolLifecycleLesson.java`

~~~java
package demo;

import java.sql.Connection;
import javax.sql.DataSource;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

public final class PoolLifecycleLesson {

    public static void main(String[] args) throws Exception {
        HikariDataSource pool;

        // Context là chủ sở hữu bean pool trong phạm vi này.
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(PoolConfiguration.class)) {

            pool = context.getBean(HikariDataSource.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("CREATE TABLE lesson_item (id INTEGER PRIMARY KEY)");
            jdbc.update("INSERT INTO lesson_item (id) VALUES (?)", 7);

            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM lesson_item", Integer.class
            );
            System.out.println("Rows = " + count);

            // Mượn một logical Connection rồi trả về pool.
            try (Connection connection = pool.getConnection()) {
                System.out.println(
                    "Borrowed connection open = " + !connection.isClosed()
                );
            }

            // Connection.close() ở trên không tắt cả pool.
            System.out.println(
                "Pool open after Connection.close = " + !pool.isClosed()
            );

        } // AnnotationConfigApplicationContext.close() được gọi tại đây.

        // Giữ tham chiếu chỉ để kiểm tra trạng thái; không dùng pool để query nữa.
        System.out.println(
            "Pool closed after context.close = " + pool.isClosed()
        );
    }

    @Configuration(proxyBeanMethods = false)
    public static class PoolConfiguration {

        @Bean(destroyMethod = "close")
        public HikariDataSource dataSource() {
            HikariConfig config = new HikariConfig();
            config.setJdbcUrl("jdbc:h2:mem:pool_lifecycle;DB_CLOSE_DELAY=-1");
            config.setUsername("sa");
            config.setPassword("");
            config.setPoolName("lesson-pool");
            config.setMaximumPoolSize(2);
            return new HikariDataSource(config);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }
    }
}
~~~

Giải thích mối quan hệ:

1. `AnnotationConfigApplicationContext` tạo bean `HikariDataSource` theo `PoolConfiguration`, sở hữu vòng đời singleton này.
2. `JdbcTemplate` nhận `DataSource` qua dependency injection. Thực thi SQL bằng `jdbc.execute` và `jdbc.update` không yêu cầu người gọi tự quản lý vòng đời pool.
3. `try (Connection connection = pool.getConnection())` mô phỏng một công việc JDBC mức thấp: khi ra khỏi block, connection được trả về pool; `isClosed()` của cả pool vẫn `false`.
4. Khi ra khỏi outer `try`, `context.close()` kích hoạt Spring destruction callback của bean, gọi `HikariDataSource.close()`.
5. Sau khi context đóng, `pool.isClosed()` phải là `true`. Ta không dùng đối tượng đã đóng để thực thi SQL hoặc mượn connection mới.

Nếu thư mục có Gradle wrapper, chạy `./gradlew run` trên Linux/macOS hoặc `.\gradlew.bat run` trên Windows PowerShell. Nếu chưa có wrapper nhưng đã cài Gradle tương thích: `gradle run`. Java toolchain 21 phải có sẵn hoặc được Gradle cấu hình để cung cấp.

Các dòng **do chính code demo in**, bỏ qua log thông tin/khởi tạo/đóng của Spring, HikariCP và Gradle, là:

~~~text
Rows = 1
Borrowed connection open = true
Pool open after Connection.close = true
Pool closed after context.close = true
~~~

Đây là một ví dụ **khép kín với hai file**; nó không dùng Spring Boot autoconfiguration. Nếu bỏ dòng `@Bean(destroyMethod = "close")` và chỉ dùng `@Bean`, Spring vẫn có thể tự nhận diện `close()` công khai của HikariDataSource theo quy tắc destroy-method inference. Nếu thay bằng `@Bean(destroyMethod = "")`, ta đã tắt suy luận callback; không nên làm vậy cho pool do context thật sự sở hữu.

**Chú ý về H2:** `DB_CLOSE_DELAY=-1` yêu cầu database H2 trong bộ nhớ tiếp tục tồn tại đến khi JVM kết thúc, nhưng điều này **không làm HikariCP tiếp tục mở** sau khi context đóng. Trạng thái `pool.isClosed()` chứng minh lifecycle pool, chứ không phải thông tin về việc database engine đã kết thúc hay dữ liệu H2 còn được giữ bao lâu.

## 9. Thí dụ tương đương với Spring Boot: cấu hình pool tự động hoặc bean tự tạo

### 9.1. Khi để Spring Boot tự cấu hình

Một dự án Spring Boot đã có starter JDBC, driver PostgreSQL và thuộc tính database thường không cần class cấu hình DataSource. Boot tạo bean pool thích hợp và gắn nó với ApplicationContext. Để DB transaction chạy trong request, Service/Repository tiếp tục dùng JdbcTemplate hoặc JPA như bình thường. Khi ứng dụng dừng đúng quy trình, Spring dọn bean pool.

Đối với ứng dụng Boot chạy trong JVM bình thường, Spring Boot đăng ký shutdown hook để đóng context; trong ứng dụng console/test có lifecycle ngắn, có thể đóng context tường minh. **Không tạo thêm HikariCP thứ hai** chỉ để kiểm soát thao tác close khi Boot đã có một DataSource bean.

### 9.2. Khi tự khai báo `@Bean DataSource`

Có thể định nghĩa DataSource tùy chỉnh, khi đó cơ chế auto-config DataSource mặc định của Boot thường sẽ lùi lại. Hãy làm rõ ownership và destroy method:

~~~java
// Ví dụ cấu hình riêng, chỉ minh họa; phần 8 là ví dụ chạy độc lập.
@Bean(destroyMethod = "close")
public HikariDataSource reportsDataSource() {
    HikariDataSource pool = new HikariDataSource();
    pool.setJdbcUrl("jdbc:postgresql://db:5432/reports");
    pool.setUsername("reports_user");
    pool.setPassword("configured-at-runtime");
    pool.setMaximumPoolSize(5);
    return pool;
}
~~~

Trong thực tế, truyền credentials qua hệ thống secret/environment và cân nhắc cách cấu hình `@ConfigurationProperties` thay vì hardcode. Khi có **nhiều** DataSource, cần thiết kế cách chọn bean (`@Qualifier`/`@Primary`), JdbcTemplate/EntityManagerFactory tương ứng và transaction manager phù hợp. Mỗi pool do Spring sở hữu đều cần được destroy đúng.

## 10. DataSource từ JNDI hoặc pool do application server sở hữu: không đóng từ Spring

Trường hợp ứng dụng WAR hoặc ứng dụng trong Jakarta EE application server: pool có thể được quản trị ở Tomcat/JBoss/WebLogic hoặc môi trường cấp ngoài, và ứng dụng chỉ **lookup** một `DataSource` qua JNDI.

Ví dụ minh họa:

~~~java
// Fragment cho ứng dụng có Spring bean config và JNDI phù hợp.
// Không phải chương trình độc lập; các import và server JNDI tùy môi trường.
@Bean(destroyMethod = "")
public javax.sql.DataSource externalDataSource() throws javax.naming.NamingException {
    return (javax.sql.DataSource) new javax.naming.InitialContext()
        .lookup("java:comp/env/jdbc/AppDb");
}
~~~

`destroyMethod = ""` ở đây có mục đích: **Spring không tự suy luận và gọi close/shutdown trên object lấy từ nguồn bên ngoài**, vì chủ sở hữu thật là application server. Đây là ngoại lệ về ownership, không phải mẹo nên áp dụng mặc định cho mọi DataSource. Theo cơ chế Spring, tắt inferred destroy method không nhất thiết vô hiệu hóa các callback do bean tự triển khai qua các giao diện lifecycle khác; cần kiểm tra đối tượng thực tế và chính sách của external container.

Nếu triển khai Spring Boot trên application server và cấu hình `spring.datasource.jndi-name`, cũng cần hiểu pool thực sự thuộc server. Tránh viết custom shutdown hook của ứng dụng để đóng pool toàn server trong khi các deployment khác vẫn có thể dùng nó.

## 11. Đóng context trong ứng dụng web, CLI và integration test

| Môi trường | Sự kiện kết thúc thông thường | Việc cần làm |
| --- | --- | --- |
| Spring Boot chạy như tiến trình server | Tín hiệu dừng bình thường/JVM exit, Spring shutdown hook | Bảo đảm shutdown được phép chạy; graceful server stop và bean destroy sẽ dọn pool |
| Spring Framework chạy bằng `AnnotationConfigApplicationContext` | Kết thúc một đơn vị sử dụng context | Dùng `try-with-resources` hoặc gọi `close()`; nếu để context chạy lâu, cân nhắc `registerShutdownHook()` |
| Công cụ CLI/tác vụ batch | Hoàn tất job hoặc lỗi phải kết thúc context | Đóng context ngay cả ở nhánh exception; đừng chỉ thoát mà giữ pool sống trong JVM |
| Spring test dùng context caching | Kết thúc test đơn lẻ chưa chắc đóng context | TestContext có thể cache context giữa các test; đừng tự đóng pool sau mỗi test method |
| Test tự tạo context | Kết thúc block/test | Đóng context trong cleanup; kiểm tra `isClosed()` khi cần |
| Ứng dụng WAR trên external app server | Redeploy/undeploy hoặc stop deployment | Xác định pool là app-owned hay server-owned trước khi quyết định destroy method |

Trong Spring TestContext, context caching giúp tái sử dụng ApplicationContext giữa các bài test. Vì vậy **“test method kết thúc” không phải lúc nào cũng là “context bị đóng”**. Nếu test cần xác minh destroy lifecycle, hãy tạo một context độc lập như ví dụ phần 8 hoặc thiết kế test có quyền đóng context, tránh phá shared cached context làm hỏng các test khác.

### `registerShutdownHook()` và đóng thủ công

Với Spring Framework thuần, context có thể đăng ký hook tùy nhu cầu:

~~~java
// Fragment, không độc lập.
AnnotationConfigApplicationContext context =
    new AnnotationConfigApplicationContext(MyConfiguration.class);
context.registerShutdownHook();
// Đối với chương trình dùng context trong một phạm vi rõ ràng,
// vẫn có thể gọi context.close() tường minh khi hoàn tất.
~~~

Hook nhằm xử lý đường JVM shutdown bình thường. Không đăng ký hook mới cho mỗi bean/DAO hoặc mỗi lần mượn Connection. Spring Boot tự có cơ chế shutdown hook của nó trong cách bootstrap thông dụng.

## 12. Quan sát và kiểm tra pool đã đóng thật chưa

**Phép kiểm tra trực tiếp trong bài học:** giữ tham chiếu đến `HikariDataSource` trước khi context đóng, sau đó gọi `pool.isClosed()` sau `context.close()`. Đây là bằng chứng rõ và định lượng cho lifecycle của pool trong demo. Sau khi pool đóng, không thực hiện thao tác nghiệp vụ thông qua tham chiếu cũ.

Trong ứng dụng thật, còn có thể dùng:

- **Log lifecycle** của implementation pool, chẳng hạn log HikariCP khi pool shutdown. Không phụ thuộc tuyệt đối vào chuỗi log cụ thể của từng phiên bản.
- **Metrics**: active, idle, total, pending connections trong thời gian chạy; quan sát xu hướng giảm và không còn borrower khi shutdown (tùy cách metrics được đăng ký và hủy).
- **Database session view**: xem các session từ ứng dụng giảm sau khi hệ thống đóng pool; cần tính đến connection của các ứng dụng khác và các kết nối tồn tại do server-side timeout.
- **Integration test**: tạo context với DataSource thật, thực thi truy vấn, đóng context, kiểm tra trạng thái pool; sau đó khởi tạo context mới và xác minh tài nguyên cũ không còn bị dùng.

Đừng xem chỉ số `idle=0` là bằng chứng pool đã đóng. Một pool đang mở có thể tạm không có kết nối idle; tương tự, DBMS có thể còn session của thành phần khác. Nếu hệ thống có nhiều pool, hãy gắn tên pool hoặc thông tin kết nối để đối chiếu đúng đối tượng.

### Kiểm thử JUnit gợi ý

~~~java
// Fragment JUnit 5, phụ thuộc vào PoolLifecycleLesson của phần 8.
// Chỉ minh họa test logic; cần thêm dependency JUnit khi đưa vào dự án.
@Test
void contextCloseShutsDownOwnedPool() {
    HikariDataSource owned;
    try (var context = new AnnotationConfigApplicationContext(
            PoolLifecycleLesson.PoolConfiguration.class)) {
        owned = context.getBean(HikariDataSource.class);
        assertFalse(owned.isClosed());
    }
    assertTrue(owned.isClosed());
}
~~~

Hãy giữ ranh giới: test chứng minh **managed Hikari bean đóng theo context**; nó không chứng minh request đã được graceful stop trong ứng dụng web thực tế. Kiểm thử graceful shutdown cần tình huống có request đang chạy và timeout thực tế.

## 13. Những lỗi phổ biến và hệ quả

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `hikariDataSource.close()` sau mỗi query hoặc request | Một request làm các request khác mất pool | Trả `Connection` sau mỗi thao tác; đóng pool một lần ở owner lifecycle |
| Tạo `new HikariDataSource` trong DAO nhưng không đăng ký bean hoặc cleanup | Pool có thể sống ngoài vòng đời Spring context | Dùng một singleton bean được quản lý hoặc quản lý ownership rõ khi tự tạo |
| Dùng `@Bean(destroyMethod = "")` cho pool do Spring sở hữu | Mất inferred close callback; có nguy cơ không dọn pool | Để mặc định hoặc khai báo `destroyMethod = "close"` |
| Gắn `@PreDestroy` trong Service rồi gọi `dataSource.close()` | Quyền sở hữu sai; phụ thuộc khác có thể đang cần pool | Đăng ký callback trên chính bean pool; phối hợp worker stop trước |
| Đóng DataSource do server JNDI sở hữu | Có thể làm hỏng dịch vụ khác đang dùng tài nguyên ngoài | Đặt `destroyMethod = ""` cho lookup phù hợp; để owner ngoài quản lý |
| Cho rằng `context.stop()` đã destroy pool | Pool có thể vẫn còn vì bean chưa bị hủy | Dùng `context.close()` khi thật sự kết thúc vòng đời |
| Đóng context khi có worker vẫn đang query | Lỗi truy vấn, timeout, job bị dở dang | Dừng nhận việc, cho in-flight work kết thúc trong hạn rồi destroy pool |
| Chỉ tin vào shutdown hook khi tiến trình bị kill cưỡng bức | Callback có thể không chạy | Thiết kế graceful termination, readiness, timeout và recovery sau crash |
| Tạo pool mới mỗi lần mở Spring context trong test mà không đóng context | Chồng nhiều pool, tăng số kết nối | Dùng test context lifecycle/caching có kiểm soát; đóng context tự tạo |
| Thấy không còn idle connections rồi tuyên bố pool đã đóng | Nhầm trạng thái số kết nối với trạng thái lifecycle | Kiểm tra `HikariDataSource.isClosed()`/log/owner context |

## 14. Tình huống nâng cao: nhiều context và nhiều nhóm kết nối

**Hai DataSource do cùng một Spring context sở hữu:** Nếu ứng dụng dùng `ordersDataSource` và `analyticsDataSource`, mỗi bean pool cần destroy đúng khi context đóng. Không để custom cleanup đóng một pool mà vẫn có worker đang dùng. Tên bean và `@Qualifier` quyết định lời gọi DAO đi tới pool nào; tên pool và metrics hỗ trợ quan sát.

**Parent/child ApplicationContext:** Một bean DataSource do parent context sở hữu không nên bị child context chủ động đóng khi chỉ child kết thúc. Việc đóng parent cuối cùng mới là lúc pool parent-owned được destroy. Đừng tái đăng ký cùng một object pool vào nhiều context dưới các bean có destroy callback độc lập nếu không có chính sách một owner.

**Pool được mượn từ framework bên ngoài:** Ví dụ library hỗ trợ JNDI, proxy DataSource hay multi-tenant routing có thể đưa ra interface `DataSource` không sở hữu socket. Cần xác định **đối tượng nào thật sự sở hữu pool** rồi mới gắn destroy callback. Không giả định cứ có `getConnection()` là đối tượng đó có quyền shutdown.

**Khi deploy lại:** Nếu cùng một JVM/container tạo Spring context mới mà context cũ không được dọn đúng, có thể giữ classloader, thread và connection của phiên bản cũ. Đảm bảo hoàn tất stop/destroy của context cũ trước khi chuyển tài nguyên sang phiên bản mới, theo lifecycle của môi trường deploy.

## 15. Tự kiểm tra

**Câu 1.** DAO đã trả Connection sau một query. Pool có phải đóng ngay không?  
**Đáp:** Không. `Connection.close()` trên kết nối pooled chủ yếu trả logical Connection về pool; pool vẫn phục vụ công việc khác.

**Câu 2.** Bean `@Bean HikariDataSource` có public `close()`, không khai báo `destroyMethod`. Spring có thể tự gọi close lúc context đóng không?  
**Đáp:** Có. Spring có cơ chế suy luận destroy method `close/shutdown` đối với `@Bean`, miễn bean thuộc scope/vòng đời do container quản lý đúng cách.

**Câu 3.** Ứng dụng chạy trên server có pool JNDI dùng chung. Ai đóng pool?  
**Đáp:** Chủ sở hữu pool là application server; Spring application chỉ mượn DataSource và không nên tự đóng tài nguyên bên ngoài.

**Câu 4.** Khác biệt giữa `context.stop()` và `context.close()` đối với bean pool?  
**Đáp:** Stop hướng tới Lifecycle stop phase; close khởi động quy trình hủy context và destroy singleton beans, gồm destroy method của pool.

**Câu 5.** Tắt web server có một query kéo dài: gọi `pool.close()` lập tức có bảo đảm query được hoàn tất không?  
**Đáp:** Không. Cần graceful shutdown phối hợp nhận request mới, in-flight request/transaction, timeout và giai đoạn stop trước khi hủy pool.

**Câu 6.** `HikariDataSource.isClosed() == false` nhưng hiện có 0 idle connection thì sao?  
**Đáp:** Pool vẫn đang mở; số idle không xác định lifecycle status.

**Câu 7.** Test tạo context mới cho mỗi test case mà không close, có vấn đề gì?  
**Đáp:** Có thể tích lũy pool/connection và tài nguyên nền. Hãy để TestContext quản lý caching/cleanup, hoặc chủ động đóng những context do test tạo riêng.

## 16. Checklist triển khai thực tế

1. **Xác nhận owner:** DataSource pool do Spring Boot/Spring config tạo hay do external server cấp?
2. **Đúng scope:** Một pool thường là singleton lâu sống; tránh khởi tạo theo request.
3. **Đúng destroy callback:** Pool owned-by-Spring dùng suy luận `close` hoặc khai báo `destroyMethod="close"`; pool external thì không tự destroy.
4. **Đúng ranh giới JDBC:** Borrow/return Connection mỗi thao tác hoặc để Spring JDBC/JPA quản lý; không đóng pool tại tầng truy vấn.
5. **Đúng shutdown order:** Ngừng nhận việc và dừng workers trước khi phá hủy pool; cấu hình timeout phù hợp với web/background job.
6. **Đúng môi trường:** CLI/test tự tạo context phải đóng context; web Boot phải cho shutdown hook/graceful path hoạt động.
7. **Đúng bằng chứng:** Verify `isClosed()` trong test, log/metrics/session trên hệ thống thực, và thử stop có request đang chạy.
8. **Đúng phạm vi sửa lỗi:** Nếu leak là do Connection không được trả, sửa borrower; nếu leak là do context/pool không bị destroy, sửa lifecycle owner. Hai lỗi có cùng triệu chứng cạn connection nhưng nguyên nhân khác nhau.

## 17. Tài liệu chính thức nên đọc thêm

- [Spring Framework — Bean lifecycle và destruction callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): cơ chế `@PreDestroy`, `DisposableBean`, destroy method, `Lifecycle` và `SmartLifecycle`.
- [Spring Framework — `@Bean` và suy luận close/shutdown](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): inference và trường hợp DataSource lấy từ JNDI.
- [Spring Boot — SQL Databases / Supported Connection Pools](https://docs.spring.io/spring-boot/reference/data/sql.html): lựa chọn HikariCP, cấu hình DataSource và JNDI.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): stop web server theo giai đoạn và timeout.
- [Spring Boot — SpringApplication / Application Exit](https://docs.spring.io/spring-boot/reference/features/spring-application.html): shutdown hook và ApplicationContext lifecycle.

**Ghi nhớ cuối bài:** Trả một `Connection` khác hoàn toàn với đóng một **pool**. Spring container nên chịu trách nhiệm đóng pool **mà nó thật sự sở hữu** khi `ApplicationContext.close()`. Các tác vụ còn dùng database cần được dừng hoặc hoàn tất trước giai đoạn destroy; còn pool do server bên ngoài cấp phải được chính server đó quản lý. Bài toán không chỉ là gọi một phương thức `close()`, mà là **đặt lệnh close ở đúng chủ sở hữu và đúng thời điểm**.
