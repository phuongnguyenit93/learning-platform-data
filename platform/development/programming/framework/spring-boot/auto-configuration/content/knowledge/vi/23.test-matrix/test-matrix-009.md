# @ImportAutoConfiguration và giới hạn tập cấu hình trong kiểm thử Spring Boot

## 1. Bài toán: kiểm thử đúng phần auto-configuration cần thiết

Một ứng dụng Spring Boot có thể có hàng chục auto-configuration cho web, JSON, database, cache, messaging, metrics và nhiều tích hợp khác. Khi kiểm thử một tính năng nhỏ, nạp toàn bộ application context thường làm test chậm, phụ thuộc nhiều thư viện và khó xác định cấu hình nào tạo ra bean đang được kiểm tra.

Ví dụ, một repository JDBC chỉ cần:

- Một `DataSource` dùng cho test.
- Một `JdbcTemplate`.
- Auto-configuration riêng của thư viện tạo dịch vụ truy vấn.
- Có thể thêm một cấu hình hỗ trợ test cụ thể.

Nó không cần khởi động web server, cấu hình security, messaging hay mọi integration khác của ứng dụng.

Spring Boot cung cấp một số cách để giới hạn cấu hình được nạp:

- **Test slice** như `@JdbcTest`, `@DataJpaTest`, `@WebMvcTest`, `@JsonTest` tự chọn một tập cấu hình nhỏ phù hợp với tầng đang kiểm thử.
- **`@ImportAutoConfiguration`** thêm một tập auto-configuration được chỉ định vào test slice hoặc một test context.
- **`exclude` / `excludeAutoConfiguration`** loại bỏ cấu hình không muốn áp dụng.
- **`ApplicationContextRunner`** tạo context nhỏ và cho phép chọn chính xác tập auto-configuration trong các bài kiểm thử auto-configuration.
- **`@Import`** đăng ký cấu hình test hoặc component cụ thể; nó có vai trò khác với việc nhập auto-configuration.

Mục tiêu là tạo một context đủ để kiểm tra hành vi đang quan tâm, có thể giải thích được vì sao mỗi bean xuất hiện.

## 2. `@ImportAutoConfiguration` làm gì?

`@ImportAutoConfiguration` nằm trong package:

~~~java
org.springframework.boot.autoconfigure.ImportAutoConfiguration
~~~

Annotation này nhập và áp dụng các auto-configuration được chỉ định. Nó tuân theo cùng quy tắc sắp xếp `before` / `after` như `@EnableAutoConfiguration`, nhưng giới hạn vào tập lớp được chỉ định thay vì tự lấy toàn bộ candidate từ `ImportCandidates`.

Ví dụ:

~~~java
@ImportAutoConfiguration({
        JacksonAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
class JsonSupportTest {
}
~~~

Trong ví dụ, test yêu cầu áp dụng hai auto-configuration đã chọn. Các auto-configuration vẫn phải thỏa điều kiện của chính chúng, chẳng hạn classpath, property hoặc bean condition. Việc liệt kê class không ép một auto-configuration tạo bean khi điều kiện của nó không match.

`@ImportAutoConfiguration` đặc biệt hữu ích khi viết test hoặc xây dựng annotation cho test slice. Trong ứng dụng thông thường, `@EnableAutoConfiguration` hoặc `@SpringBootApplication` thường là lựa chọn phù hợp hơn.

### 2.1. Các thuộc tính của annotation

| Thuộc tính | Kiểu | Ý nghĩa |
|---|---|---|
| `value` | `Class<?>[]` | Các auto-configuration cần nhập |
| `classes` | `Class<?>[]` | Alias của `value`, có cùng mục đích |
| `exclude` | `Class<?>[]` | Các auto-configuration phải loại khỏi lần nhập |

`value` và `classes` là hai tên thay thế cho cùng một thuộc tính. Chỉ cần dùng một cách viết:

~~~java
@ImportAutoConfiguration(
        classes = {JacksonAutoConfiguration.class}
)
class JsonSupportTest {
}
~~~

Hoặc dạng ngắn:

~~~java
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
class JsonSupportTest {
}
~~~

Có thể kết hợp lớp cần nhập và lớp cần loại:

~~~java
@ImportAutoConfiguration(
        classes = {
                JacksonAutoConfiguration.class,
                ValidationAutoConfiguration.class
        },
        exclude = {
                SomeOptionalMetricsAutoConfiguration.class
        }
)
class JsonSupportTest {
}
~~~

Lớp trong `exclude` không được áp dụng qua lần nhập này. Dùng `exclude` để diễn tả rõ tập cấu hình cần tránh, nhất là khi một annotation test hoặc annotation tổng hợp đã mang theo nhiều auto-configuration.

### 2.2. Khi không truyền `value` hoặc `classes`

Nếu danh sách lớp để trống, Spring Boot lấy các tên auto-configuration từ một file trong `META-INF/spring`. Tên file là tên đầy đủ của lớp được gắn `@ImportAutoConfiguration`, nối thêm hậu tố `.imports`.

Ví dụ, test class:

~~~java
package com.example.audit;

@ImportAutoConfiguration
class AuditSliceTest {
}
~~~

Có thể dùng resource:

~~~text
META-INF/spring/com.example.audit.AuditSliceTest.imports
~~~

Nội dung:

~~~text
com.example.audit.autoconfigure.AuditClientAutoConfiguration
com.example.audit.autoconfigure.AuditMetricsAutoConfiguration
~~~

Mỗi dòng là một FQCN. Có thể thêm comment bắt đầu bằng `#`. Một dòng có thể dùng tiền tố `optional:` để chỉ ra rằng lớp được nhập có thể vắng mặt trên classpath; khi đó Spring Boot bỏ qua lớp tùy chọn nếu không tìm thấy.

Cơ chế file này khác với file đăng ký auto-configuration chung:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File thứ nhất phục vụ tập import gắn với một annotation cụ thể; file thứ hai công bố auto-configuration của thư viện cho cơ chế khám phá auto-configuration thông thường của Spring Boot.

## 3. Giới hạn tập cấu hình trong test slice

Test slice tập trung vào một phần ứng dụng. Spring Boot cung cấp các annotation phổ biến:

| Annotation | Tập chức năng chính |
|---|---|
| `@WebMvcTest` | Spring MVC controller và hạ tầng web MVC liên quan |
| `@WebFluxTest` | Spring WebFlux controller và hạ tầng reactive web |
| `@JdbcTest` | `DataSource`, `JdbcTemplate` và hạ tầng JDBC |
| `@DataJpaTest` | JPA entity, repository và cấu hình persistence liên quan |
| `@JsonTest` | JSON serializer/deserializer và JSON test helpers |
| `@RestClientTest` | REST client và mock server cho client test |
| `@DataMongoTest` | MongoDB mapping và repository slice |
| `@JooqTest` | jOOQ `DSLContext` và cấu hình liên quan |

Các slice thường chỉ nạp một tập auto-configuration giới hạn và giới hạn component scan vào loại component phù hợp. Vì vậy, `@JdbcTest` không phải một ứng dụng đầy đủ có mọi `@Service`, `@Controller` và `@ConfigurationProperties` được quét như `@SpringBootApplication`.

Ví dụ, `@JdbcTest` mặc định cấu hình embedded database nếu có trên classpath và tạo `JdbcTemplate`. Nó không quét các component thông thường của ứng dụng. Có thể dùng `@EnableConfigurationProperties` để đưa các properties cần thiết vào context.

Điều này có hai hệ quả:

1. Test slice chạy tập trung và ít phụ thuộc hơn.
2. Nếu test cần một component ngoài phạm vi slice, phải nhập hoặc khai báo component đó một cách tường minh.

## 4. Thêm một auto-configuration vào test slice

Giả sử thư viện có `AuditQueryAutoConfiguration` tạo một dịch vụ truy vấn dựa trên `JdbcTemplate`. `@JdbcTest` đã cung cấp hạ tầng JDBC; test chỉ cần nhập thêm auto-configuration của thư viện.

~~~java
package com.example.audit;

import com.example.audit.autoconfigure.AuditQueryAutoConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@JdbcTest
@ImportAutoConfiguration(AuditQueryAutoConfiguration.class)
class AuditQuerySliceTest {

    @Autowired
    private AuditQueryService auditQueryService;

    @Test
    void usesJdbcTemplateProvidedByTheSlice() {
        assertEquals(1, auditQueryService.selectOne());
    }
}
~~~

`@JdbcTest` cung cấp JDBC slice. `@ImportAutoConfiguration` bổ sung auto-configuration riêng. Test không phải nhập lại `DataSourceAutoConfiguration` hay `JdbcTemplateAutoConfiguration` nếu slice đã cung cấp chúng.

Một auto-configuration minh họa:

~~~java
package com.example.audit.autoconfigure;

import com.example.audit.AuditQueryService;
import com.example.audit.JdbcAuditQueryService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@AutoConfiguration(after = JdbcTemplateAutoConfiguration.class)
@ConditionalOnClass(JdbcTemplate.class)
@ConditionalOnBean(JdbcTemplate.class)
public class AuditQueryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditQueryService.class)
    AuditQueryService auditQueryService(JdbcTemplate jdbcTemplate) {
        return new JdbcAuditQueryService(jdbcTemplate);
    }
}
~~~

Service:

~~~java
package com.example.audit;

public interface AuditQueryService {
    Integer selectOne();
}
~~~

Implementation:

~~~java
package com.example.audit;

import org.springframework.jdbc.core.JdbcTemplate;

public class JdbcAuditQueryService implements AuditQueryService {

    private final JdbcTemplate jdbcTemplate;

    public JdbcAuditQueryService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public Integer selectOne() {
        return jdbcTemplate.queryForObject("SELECT 1", Integer.class);
    }
}
~~~

Thứ tự `after = JdbcTemplateAutoConfiguration.class` giúp điều kiện bean được đánh giá sau cấu hình tạo `JdbcTemplate`. Tham số `JdbcTemplate` trong phương thức `@Bean` thể hiện dependency thực tế khi Spring tạo service.

Test cần có JDBC starter và H2 trong test runtime, ví dụ với Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}
~~~

Với Spring Boot 3.3 và JUnit 5, chạy test bằng:

~~~bash
./gradlew test --tests com.example.audit.AuditQuerySliceTest
~~~

Kết quả kỳ vọng là test khởi động context JDBC slice, tạo service và thực thi `SELECT 1` trên embedded database. Đây là ví dụ kiểm thử; cần chạy trong project thực tế để xác nhận dependency, package và auto-configuration imports của dự án.

## 5. Loại trừ auto-configuration không cần thiết

Có hai vị trí thường dùng để loại cấu hình.

### 5.1. Dùng thuộc tính `exclude` của `@ImportAutoConfiguration`

~~~java
@ImportAutoConfiguration(
        classes = {
                AuditQueryAutoConfiguration.class,
                AuditMetricsAutoConfiguration.class
        },
        exclude = {
                SomeOptionalMetricsAutoConfiguration.class
        }
)
class AuditQuerySliceTest {
}
~~~

Cách này phù hợp khi test hoặc annotation tổng hợp tự khai báo tập import.

### 5.2. Dùng `excludeAutoConfiguration` của test slice

Nhiều slice có thuộc tính `excludeAutoConfiguration`. Ví dụ:

~~~java
@JdbcTest(
        excludeAutoConfiguration = {
                FlywayAutoConfiguration.class
        }
)
@ImportAutoConfiguration(AuditQueryAutoConfiguration.class)
class AuditQueryWithoutFlywayTest {
}
~~~

Đây là ví dụ dành cho project có Flyway trên classpath và muốn tắt Flyway trong test. Nếu Flyway không phải dependency của project, không cần thêm class này vào code test.

Sự khác nhau về ý nghĩa:

- `@ImportAutoConfiguration(exclude = ...)` loại class khỏi lần nhập auto-configuration đó.
- `excludeAutoConfiguration` là thuộc tính của slice annotation để loại auto-configuration khỏi cấu hình slice.
- `@SpringBootApplication(exclude = ...)` và property `spring.autoconfigure.exclude` là cách loại cấu hình khỏi lần khởi động ứng dụng rộng hơn; không nên sửa cấu hình production chỉ để làm một test slice nhỏ hơn.

### 5.3. Chọn đúng lớp cần loại

Trước khi exclude, xác định auto-configuration nào thực sự gây ra bean hoặc side effect không mong muốn. Có thể dùng Condition Evaluation Report để xem:

- Cấu hình nào match.
- Cấu hình nào không match và lý do.
- Bean nào được tạo bởi auto-configuration.
- Condition nào phụ thuộc classpath, property hoặc bean hiện diện.

Không exclude một nhóm cấu hình rộng nếu chỉ một auto-configuration cụ thể gây nhiễu. Việc loại quá nhiều có thể làm test không còn mô phỏng đúng hạ tầng cần kiểm tra.

## 6. `@ImportAutoConfiguration` khác `@Import` như thế nào?

Hai annotation đều có thể khiến cấu hình được đưa vào context, nhưng ý nghĩa và cơ chế xử lý khác nhau.

| Tiêu chí | `@ImportAutoConfiguration` | `@Import` |
|---|---|---|
| Mục tiêu | Các lớp auto-configuration của Spring Boot | Cấu hình hoặc component cụ thể |
| Thứ tự | Tuân theo ordering của auto-configuration | Theo cơ chế import cấu hình thông thường của Spring |
| Danh sách | Có `value`/`classes` và `exclude` | Nhập trực tiếp các class được chỉ định |
| File imports | Có thể dùng file `.imports` theo FQCN lớp được gắn annotation | Không dùng cơ chế file imports của annotation này |
| Trường hợp thường gặp | Thêm cấu hình vào test slice hoặc test auto-configuration | Đưa test config, mock bean config hoặc cấu hình hỗ trợ vào context |

Spring Boot xử lý auto-configuration theo cơ chế riêng, bao gồm ordering và các điều kiện. Vì vậy, khi nhập một auto-configuration vào test slice, hãy dùng `@ImportAutoConfiguration`. Không dùng `@Import` thông thường để thay thế.

Ngược lại, nếu muốn đưa một lớp `@TestConfiguration` chứa mock bean hoặc một cấu hình kiểm thử cụ thể vào context, `@Import` là lựa chọn thích hợp:

~~~java
@JdbcTest
@Import(AuditTestBeans.class)
@ImportAutoConfiguration(AuditQueryAutoConfiguration.class)
class AuditQuerySliceTest {
}
~~~

Trong ví dụ, `AuditTestBeans` là cấu hình do test sở hữu; `AuditQueryAutoConfiguration` là auto-configuration của thư viện. Mỗi annotation có một trách nhiệm rõ ràng.

## 7. Tạo annotation riêng để tái sử dụng test slice

Nếu nhiều test cùng cần một slice và một tập auto-configuration bổ sung, có thể tạo annotation tổng hợp.

~~~java
package com.example.audit.test;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@JdbcTest
@ImportAutoConfiguration(AuditQueryAutoConfiguration.class)
public @interface AuditJdbcTest {
}
~~~

Dùng annotation đó trong test:

~~~java
@AuditJdbcTest
class AuditRepositoryTests {

    @Autowired
    AuditQueryService auditQueryService;

    @Test
    void canRunJdbcQuery() {
        assertEquals(1, auditQueryService.selectOne());
    }
}
~~~

Cách này gom quy ước test vào một tên có ý nghĩa. Khi cần thay đổi hạ tầng slice hoặc auto-configuration dùng chung, cập nhật annotation tổng hợp một lần thay vì sửa từng test class.

Annotation tổng hợp vẫn phải giữ phạm vi nhỏ. Không thêm các cấu hình không liên quan chỉ vì một test đơn lẻ cần chúng.

## 8. Dùng file imports để mở rộng mọi test của một slice

Nếu thư viện test support muốn thêm một auto-configuration vào **mọi** test dùng một slice cụ thể, Spring Boot cho phép đăng ký theo tên slice annotation bằng resource trong `META-INF/spring`.

Ví dụ, để thêm `com.example.IntegrationAutoConfiguration` vào mọi test có `@JdbcTest`, tạo file:

~~~text
META-INF/spring/org.springframework.boot.test.autoconfigure.jdbc.JdbcTest.imports
~~~

Nội dung:

~~~text
com.example.IntegrationAutoConfiguration
~~~

Có thể thêm comment bằng `#`. File này được dùng bởi slice annotation có cơ chế `@ImportAutoConfiguration`; do đó, nó áp dụng cho mọi `@JdbcTest` trong phạm vi classpath có chứa resource.

Đây là quyết định ở cấp module test support, không phải lựa chọn của một test class đơn lẻ. Nếu chỉ một test cần cấu hình bổ sung, dùng `@ImportAutoConfiguration` trực tiếp trên test hoặc annotation tổng hợp sẽ dễ hiểu và ít gây tác động phụ hơn.

### 8.1. Phân biệt ba file imports

| Tên file | Ai sử dụng | Mục đích |
|---|---|---|
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Cơ chế auto-configuration chung | Công bố auto-configuration của thư viện |
| `META-INF/spring/<FQCN-của-test-hoặc-annotation>.imports` | `@ImportAutoConfiguration` | Chỉ định auto-configuration cho annotation/test cụ thể |
| `META-INF/spring/org.springframework.boot.test.autoconfigure.jdbc.JdbcTest.imports` | `@JdbcTest` | Thêm cấu hình vào mọi JDBC slice test |

Đừng ghi auto-configuration của thư viện vào file dành cho slice test với kỳ vọng ứng dụng production sẽ tự phát hiện nó. Ngược lại, file `AutoConfiguration.imports` toàn cục không phải cách giới hạn cấu hình của riêng một test.

## 9. `@SpringBootTest` có tự giới hạn theo danh sách import không?

`@SpringBootTest` thường tìm cấu hình ứng dụng chính, chẳng hạn class có `@SpringBootApplication`. Cấu hình đó thường bật `@EnableAutoConfiguration`, do đó context có thể nạp toàn bộ auto-configuration phù hợp với classpath và property.

Gắn thêm:

~~~java
@SpringBootTest
@ImportAutoConfiguration(AuditQueryAutoConfiguration.class)
class AuditIntegrationTest {
}
~~~

không có nghĩa là toàn bộ auto-configuration của ứng dụng chính bị thay thế bằng một danh sách chỉ có `AuditQueryAutoConfiguration`. Annotation này nhập thêm cấu hình đã chỉ định; auto-configuration do ứng dụng chính bật vẫn có thể được áp dụng.

Nếu muốn kiểm thử tích hợp gần với ứng dụng thật, `@SpringBootTest` là lựa chọn đúng. Nếu mục tiêu là cô lập một nhóm auto-configuration, hãy dùng test slice hoặc một test context tối giản được khai báo tường minh.

Không cố biến một `@SpringBootTest` đầy đủ thành slice bằng cách thêm `@ImportAutoConfiguration`. Chọn annotation theo phạm vi cần kiểm tra ngay từ đầu.

## 10. Kiểm thử một tập auto-configuration chính xác bằng `ApplicationContextRunner`

Khi phát triển auto-configuration của thư viện, `ApplicationContextRunner` thường là cách gọn và rõ nhất để kiểm thử từng tổ hợp:

- Auto-configuration nào được bật.
- Property nào có mặt.
- User bean nào đã được khai báo.
- Class nào bị loại khỏi classpath.
- Bean nào được tạo hoặc bị bỏ qua.

Ví dụ:

~~~java
package com.example.audit.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AuditQueryAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            DataSourceAutoConfiguration.class,
                            JdbcTemplateAutoConfiguration.class,
                            AuditQueryAutoConfiguration.class
                    ))
                    .withPropertyValues(
                            "spring.datasource.url=jdbc:h2:mem:audit_test",
                            "spring.datasource.username=sa",
                            "spring.datasource.password="
                    );

    @Test
    void importsOnlyTheAutoConfigurationsUnderTest() {
        runner.run(context -> {
            assertTrue(context.containsBean("dataSource"));
            assertTrue(context.containsBean("jdbcTemplate"));
            assertEquals(
                    1,
                    context.getBean(AuditQueryService.class).selectOne()
            );
        });
    }
}
~~~

`AutoConfigurations.of(...)` biểu diễn tập auto-configuration mà runner cần áp dụng. Spring Boot vẫn sắp xếp các class theo metadata ordering; không nên dựa vào thứ tự chúng xuất hiện trong mảng.

Đoạn test trên cần JDBC starter và H2 ở test runtime. Nó không khởi động toàn bộ ứng dụng, không cần `@SpringBootApplication`, và chỉ đưa các auto-configuration liên quan tới JDBC và service đang kiểm thử vào runner.

### 10.1. Kiểm tra điều kiện khi classpath thiếu thư viện

Có thể dùng `FilteredClassLoader` để mô phỏng class hoặc package không có trên runtime classpath:

~~~java
@Test
void backsOffWhenJdbcTemplateIsNotOnTheClasspath() {
    runner.withClassLoader(
            new FilteredClassLoader(JdbcTemplate.class)
    ).run(context ->
            assertTrue(context.getBeansOfType(AuditQueryService.class).isEmpty())
    );
}
~~~

Test này hữu ích khi auto-configuration có `@ConditionalOnClass`. Nó kiểm tra hành vi khi dependency vắng mặt, thay vì chỉ kiểm tra trường hợp mọi thư viện đều có trong classpath.

Lưu ý: ví dụ `FilteredClassLoader` phải được biên dịch trong test có `spring-boot-test` và các kiểu được tham chiếu cần có trong compile classpath. Bộ lọc tác động tới classloader của context test, không gỡ dependency khỏi build.

### 10.2. Kiểm tra back-off khi ứng dụng có bean riêng

Một auto-configuration tốt thường nhường chỗ cho bean do ứng dụng cung cấp:

~~~java
@Configuration(proxyBeanMethods = false)
static class CustomAuditConfiguration {

    @Bean
    AuditQueryService customAuditQueryService() {
        return () -> 42;
    }
}
~~~

Đưa cấu hình người dùng vào runner:

~~~java
runner.withUserConfiguration(CustomAuditConfiguration.class)
        .run(context -> {
            assertEquals(
                    42,
                    context.getBean(AuditQueryService.class).selectOne()
            );
        });
~~~

Cách kiểm thử này xác nhận `@ConditionalOnMissingBean` hoạt động như dự kiến. Trong test thật, bảo đảm interface và kiểu trả về của bean tùy chỉnh phù hợp với API mà auto-configuration đang kiểm tra.

## 11. Chọn công cụ theo phạm vi test

| Mục tiêu | Công cụ nên dùng | Lý do |
|---|---|---|
| Kiểm thử controller MVC | `@WebMvcTest` + `@Import` cho collaborator test + `@ImportAutoConfiguration` khi cần auto-config bổ sung | Tập trung vào web MVC |
| Kiểm thử JDBC repository/service | `@JdbcTest` + `@ImportAutoConfiguration` | Dùng JDBC slice có sẵn |
| Kiểm thử JSON | `@JsonTest` và cấu hình JSON cần thiết | Không cần database hoặc web layer |
| Kiểm thử auto-configuration của thư viện | `ApplicationContextRunner` + `AutoConfigurations.of(...)` | Chọn chính xác class, property và user bean |
| Kiểm thử tích hợp toàn ứng dụng | `@SpringBootTest` | Xác minh cấu hình thực tế gần ứng dụng |
| Nhiều test dùng cùng slice và auto-config | Annotation tổng hợp hoặc slice-specific `.imports` | Chia sẻ quy ước một cách có chủ đích |

Spring Boot không hỗ trợ ghép nhiều slice annotation khác nhau trên cùng test class, ví dụ đặt đồng thời `@JdbcTest` và `@JsonTest` để tạo một slice kết hợp. Nếu cần nhiều khả năng, chọn một slice chính rồi thêm các `@AutoConfigure...` annotation hoặc `@ImportAutoConfiguration` phù hợp.

## 12. Chẩn đoán khi bean không xuất hiện trong test

Khi test không tìm thấy bean mong đợi, kiểm tra theo trình tự:

1. **Test có nạp đúng slice không?** Xác nhận annotation test và cấu hình chính được phát hiện.
2. **Auto-configuration có nằm trong tập import không?** Kiểm tra class đã được chỉ định trong `@ImportAutoConfiguration`, runner `AutoConfigurations.of(...)` hoặc file `.imports`.
3. **Có classpath condition nào không đạt không?** Xác nhận dependency thực sự nằm trong test runtime.
4. **Có property condition nào không đạt không?** Đọc đúng prefix, tên property và giá trị yêu cầu.
5. **Có bean condition nào không đạt không?** Một bean khác có thể khiến `@ConditionalOnMissingBean` back off; hoặc dependency cần thiết chưa được đăng ký.
6. **Ordering có đúng không?** Nếu condition phụ thuộc bean từ auto-configuration khác, khai báo `after` / `before` phù hợp trên class auto-configuration.
7. **Bean nằm ngoài component scan của slice không?** Dùng `@Import` hoặc `@EnableConfigurationProperties` để đăng ký thành phần test cần.
8. **Có exclusion nào tác động không?** Kiểm tra `exclude`, `excludeAutoConfiguration` và property `spring.autoconfigure.exclude`.
9. **Đang dùng nhầm `@Import` không?** Đổi sang `@ImportAutoConfiguration` khi lớp cần nhập là auto-configuration.
10. **Đang mong `@ImportAutoConfiguration` giới hạn một `@SpringBootTest` đầy đủ?** Dùng test slice hoặc `ApplicationContextRunner` nếu cần tập cấu hình hẹp.

Bật debug condition report khi cần tìm lý do auto-configuration match hoặc không match. Không nên thêm hàng loạt cấu hình cho tới khi test xanh; hãy tìm điều kiện đầu tiên không đạt và sửa đúng nguyên nhân.

## 13. Các lỗi thường gặp

1. **Dùng `@Import` để nhập auto-configuration.** Dùng `@ImportAutoConfiguration` để Spring Boot áp dụng ordering và cơ chế import chuyên biệt.
2. **Tưởng `@ImportAutoConfiguration` tự tạo bean bất chấp condition.** Nó chỉ đưa auto-configuration vào quá trình xử lý; điều kiện của class và bean vẫn có hiệu lực.
3. **Đặt `@ImportAutoConfiguration` lên `@SpringBootTest` rồi mong toàn bộ auto-config khác biến mất.** Nó không thay thế `@EnableAutoConfiguration` từ ứng dụng chính.
4. **Dùng `@JdbcTest` nhưng mong mọi `@Service` được scan.** Slice giới hạn component scan; nhập component cần thiết một cách tường minh.
5. **Quên file `.imports` theo FQCN của annotation.** Khi không truyền danh sách class, tên file phải khớp lớp được gắn `@ImportAutoConfiguration`.
6. **Nhầm file imports của test slice với file auto-configuration toàn cục.** Hai file có tên và phạm vi áp dụng khác nhau.
7. **Dựa vào thứ tự class trong mảng `classes`.** Dùng `@AutoConfiguration(after=...)` hoặc `before=...` để diễn tả quan hệ thứ tự.
8. **Exclude quá nhiều cấu hình.** Test có thể không còn hạ tầng cần thiết hoặc không mô phỏng đúng ứng dụng.
9. **Kết hợp nhiều slice annotation.** Chọn một slice chính và bổ sung cấu hình còn thiếu bằng các annotation hỗ trợ.
10. **Không kiểm thử classpath thiếu dependency.** Dùng `FilteredClassLoader` để xác minh auto-configuration tùy chọn tự back off.
11. **Chỉ test auto-configuration bằng runner rồi kết luận starter đã đóng gói đúng.** Runner đăng ký class trực tiếp không chứng minh resource `.imports` có trong JAR; cần consumer test nếu muốn kiểm tra discovery qua artifact.
12. **Đặt cấu hình chỉ dành cho một test vào file imports dùng chung của slice.** Mọi test dùng slice sẽ nhận cấu hình đó; chỉ dùng file chung khi đây là quy ước có chủ đích của module test support.

## 14. Quy trình thiết kế test có tập cấu hình rõ ràng

1. Xác định tầng đang kiểm thử: MVC, JDBC, JPA, JSON, client hay auto-configuration riêng.
2. Chọn test slice tương ứng nếu nó cung cấp đúng hạ tầng cần thiết.
3. Liệt kê bean và auto-configuration tối thiểu mà test cần.
4. Dùng `@ImportAutoConfiguration` để thêm auto-configuration còn thiếu.
5. Dùng `exclude` hoặc `excludeAutoConfiguration` khi một cấu hình cụ thể gây side effect hoặc không thuộc phạm vi test.
6. Dùng `@Import` cho test configuration, mock bean hoặc component cụ thể.
7. Nếu kiểm thử thư viện auto-configuration, dùng `ApplicationContextRunner` và `AutoConfigurations.of(...)` để cô lập từng tổ hợp.
8. Kiểm thử thêm trường hợp classpath thiếu dependency, property tắt và user bean override.
9. Nếu test phụ thuộc vào resource discovery, kiểm tra JAR và chạy consumer smoke test; không chỉ đăng ký class trực tiếp trong runner.
10. Khi cần nhiều test chia sẻ cùng cấu hình, tạo annotation tổng hợp hoặc file slice-specific `.imports` với phạm vi rõ ràng.

## 15. Ghi nhớ

- `@ImportAutoConfiguration` nhập một tập auto-configuration cụ thể và tuân theo ordering như `@EnableAutoConfiguration`.
- `value` và `classes` là alias; `exclude` loại class khỏi lần nhập.
- Khi danh sách class trống, Spring Boot đọc file `.imports` trong `META-INF/spring` có tên dựa trên FQCN của lớp được gắn annotation.
- Test slice đã có tập auto-configuration giới hạn; `@ImportAutoConfiguration` bổ sung cấu hình còn thiếu.
- Dùng `@Import` cho test config hoặc component cụ thể; dùng `@ImportAutoConfiguration` cho auto-configuration.
- `@SpringBootTest` với ứng dụng chính thường vẫn nạp toàn bộ auto-configuration phù hợp; thêm `@ImportAutoConfiguration` không biến nó thành slice.
- `ApplicationContextRunner` cùng `AutoConfigurations.of(...)` là cách kiểm thử một tập auto-configuration chính xác.
- Thứ tự trong danh sách class không thay thế ordering metadata `before` / `after`.
- Một test slice tập trung nên kiểm tra đúng một tầng; nếu cần thêm chức năng, nhập cấu hình có chủ đích.
- Consumer smoke test cần thiết khi muốn xác nhận resource imports và dependency của artifact đã publish.

### Tài liệu Spring Boot 3.3 chính thức

- Javadoc `@ImportAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html
- Testing Spring Boot Applications — test slices, auto-configured tests và mở rộng slice: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Testing — test modules và các tiện ích kiểm thử: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
- Creating Your Own Auto-configuration — kiểm thử auto-configuration với `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
