# `excludeName` khi cần loại trừ auto-configuration bằng tên lớp đầy đủ

## 1. Vấn đề cần giải quyết

Spring Boot tự động chọn các lớp **auto-configuration** từ những thư viện có trên classpath, dựa vào những điều kiện như class hiện diện, bean đã có và giá trị cấu hình. Điều này giảm cấu hình thủ công nhưng đôi khi ứng dụng **cần chủ động loại trừ một auto-configuration cụ thể**.

Ví dụ, một dịch vụ không muốn Spring Boot tự tạo `DataSource` mặc dù project có các thư viện JDBC/HikariCP, vì kết nối dữ liệu do một hạ tầng khác quản lý. Cách loại trừ theo kiểu Java thường thấy:

```java
@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
```

Cách trên yêu cầu chương trình **tham chiếu được kiểu `DataSourceAutoConfiguration`** khi biên dịch, tức phải có import và dependency phù hợp. Khi xây dựng một ứng dụng hoặc thư viện dùng module tùy chọn, bạn có thể cần khai báo loại trừ mà **không muốn tham chiếu trực tiếp đến lớp đích**. Khi ấy, dùng `excludeName`:

```java
@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
```

Giá trị trong `excludeName` là **tên lớp đầy đủ (fully qualified class name, FQCN)**, không phải tên bean, tên package, tên starter hay tên tệp JAR. Nó chỉ định một **auto-configuration candidate** cần được bỏ khỏi quá trình import tự động. Đối với Spring Boot 3.3, thuộc tính này có trên cả `@SpringBootApplication` và `@EnableAutoConfiguration`.

> Điểm mấu chốt: `excludeName` tắt đường **tự động import auto-configuration đã nêu**. Nó không xóa dependency, không chặn component scanning nói chung và không xóa bean do ứng dụng tự khai báo.

## 2. Cú pháp chính xác và một ứng dụng Java 17+ tối giản

Tạo file `src/main/java/demo/ExcludeNameApplication.java` trong một project Spring Boot 3.3.x:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class ExcludeNameApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExcludeNameApplication.class, args);
    }
}
```

Đây là **một class Java có thể biên dịch** khi dự án có Spring Boot starter/runtime. Không cần `import DataSourceAutoConfiguration`, vì chương trình chỉ dùng **chuỗi**. Lớp `DataSourceAutoConfiguration` thuộc Spring Boot, với FQCN chính xác:

```text
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Với `@SpringBootApplication`, Spring Boot đã bật auto-configuration theo mặc định; không cần thêm `@EnableAutoConfiguration` lên cùng class.

Nếu cần loại trừ nhiều lớp, truyền mảng tên:

```java
@SpringBootApplication(excludeName = {
    "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration",
    "org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration"
})
public class ExcludeNameApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExcludeNameApplication.class, args);
    }
}
```

Đây là **phiên bản thay thế** của class đầu, không đặt cả hai class trùng tên vào cùng source set. Tên thứ hai là auto-configuration của Spring Boot cho Redis trong hệ 3.3, không phải một `@Component` tự tạo.

**Trường hợp phù hợp để dùng chuỗi:** mã chung cần chạy với những tập dependency khác nhau; cấu hình dùng lại cho ứng dụng có hoặc không có starter tùy chọn; hoặc một meta-annotation muốn chỉ rõ tên auto-configuration mà không giữ tham chiếu `Class<?>` đến nó. Chuỗi giúp tránh phụ thuộc compile-time **cho chính thuộc tính loại trừ**, nhưng mọi nơi khác trong chương trình vẫn phải kiểm soát class loading riêng.

## 3. So sánh `exclude` và `excludeName`

Hai thuộc tính cùng mục đích loại trừ **auto-configuration**, khác nhau ở cách định danh:

| Tiêu chí | `exclude` | `excludeName` |
|---|---|---|
| Kiểu annotation attribute | `Class<?>[]` | `String[]` |
| Ví dụ | `DataSourceAutoConfiguration.class` | `"org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"` |
| Cần import lớp đích ở mã Java? | Thông thường có | Không |
| Trình biên dịch kiểm tra tên lớp? | Có, qua class literal | Không, tên có thể gõ sai |
| Dùng khi thư viện/lớp tùy chọn không có trên compile classpath? | Không tiện khi thiếu dependency compile | Phù hợp |
| Mục tiêu loại trừ | Auto-configuration | Auto-configuration |
| Ảnh hưởng đến `@Component` do ứng dụng scan? | Không trực tiếp | Không trực tiếp |

Ví dụ tương đương về ý định khi class đích sẵn có:

```java
// Cách tham chiếu kiểu, yêu cầu import phù hợp
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)

// Cách tham chiếu tên, không cần import lớp đích
@SpringBootApplication(excludeName =
    "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
```

Hai đoạn ở trên là **các dòng annotation minh họa riêng biệt**, phải gắn từng annotation lên class tương ứng.

Chọn `exclude` khi code đã phụ thuộc lớp đích và muốn IDE hỗ trợ điều hướng/đổi tên. Chọn `excludeName` khi cần viết loại trừ **bằng chuỗi FQCN**, đặc biệt lúc lớp có thể vắng mặt ở một biến thể dependency.

**Một điểm tinh tế của meta-annotation:** tài liệu Javadoc Spring Boot cảnh báo khi tạo annotation tổng hợp bao ngoài `@EnableAutoConfiguration` hoặc `@SpringBootApplication`, nên ưu tiên `excludeName` để tránh các vấn đề đọc class literal ở metadata của meta-annotation. Đừng khái quát rằng mọi `Class<?>` ở annotation trực tiếp sẽ luôn gây lỗi khi runtime thiếu class; Spring có cách đọc metadata, và Javadoc phân biệt annotation trực tiếp với annotation tổng hợp.

## 4. Phạm vi thực tế của thao tác loại trừ

Quá trình auto-configuration Spring Boot 3.3 có thể hiểu ở mức khái quát:

1. Spring Boot phát hiện danh sách **ứng viên auto-configuration** từ tài nguyên `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` trong các JAR.
2. Framework tập hợp các ngoại lệ được khai báo qua `exclude`, `excludeName` và thuộc tính môi trường `spring.autoconfigure.exclude`.
3. Các tên auto-configuration bị loại trừ được bỏ khỏi danh sách nhập tự động.
4. Những ứng viên còn lại tiếp tục được xét theo các điều kiện của riêng chúng, chẳng hạn `@ConditionalOnClass` hoặc `@ConditionalOnMissingBean`.
5. Application context được xây dựng từ cấu hình người dùng và các auto-configuration được phép áp dụng.

Vì vậy, sau khi loại trừ `DataSourceAutoConfiguration`:

- Starter JDBC/HikariCP **vẫn có thể có mặt trên classpath**; `excludeName` không sửa Gradle hay Maven dependency graph.
- Một `DataSource` do người dùng khai báo với `@Bean` **vẫn có thể tồn tại**.
- Một cấu hình khác được import trực tiếp hoặc một auto-configuration khác **vẫn có thể tạo bean liên quan** nếu điều kiện của nó cho phép.
- Đường đăng ký bean của **auto-configuration đã bị loại trừ** sẽ không chạy như một ứng viên import tự động; những side effect khác do code người dùng thực hiện không được tắt theo.
- Khi một auto-configuration khác phụ thuộc các bean từ cấu hình đã loại trừ, nó có thể không match điều kiện hoặc có thể thất bại khi chạy nếu được viết không đúng; phải kiểm thử cả context sau loại trừ.

Không nhầm `excludeName` với “disable toàn bộ tính năng” trong mọi trường hợp. Nên kiểm tra **bean cuối cùng** thay vì chỉ nhìn thấy tên auto-configuration trong danh sách excludes.

### Vì sao phải là auto-configuration class?

Đúng:

```java
@SpringBootApplication(excludeName =
    "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
```

Sai mục tiêu:

```java
// Không dùng tên implementation bean hay lớp @Service thường
@SpringBootApplication(excludeName = "demo.service.PaymentService")
```

Một class `@Service` thông thường không được Spring Boot nhập dưới dạng auto-configuration candidate, nên `excludeName` không phải công cụ để tắt nó. Với một lớp **tồn tại trên classpath** nhưng không thuộc danh sách auto-configuration hợp lệ, Spring Boot có thể báo lỗi dạng “classes could not be excluded because they are not auto-configuration classes”. Nếu class **không tồn tại** thì chuỗi không bắt JVM tham chiếu đến class đó; tuy nhiên loại trừ một cái tên vốn không có ứng viên tương ứng cũng **không mang lại thay đổi có ý nghĩa**.

Để loại trừ component do `@ComponentScan` phát hiện, dùng bộ lọc scan hoặc điều chỉnh thiết kế đăng ký component phù hợp. Để ngăn một bean tự tạo, dùng chính điều kiện/định nghĩa bean hoặc thay đổi cấu hình của ứng dụng. Không tráo đổi các cơ chế này với auto-configuration exclusion.

## 5. `@EnableAutoConfiguration(excludeName=...)` và cách cấu hình bằng properties

`@SpringBootApplication` kết hợp `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. Vì vậy annotation `@SpringBootApplication(excludeName=...)` là alias của thuộc tính loại trừ trên `@EnableAutoConfiguration`.

Nếu bạn viết cấu hình không dùng `@SpringBootApplication`, vẫn có thể khai báo:

```java
package demo;

import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class ExcludeJdbcAutoConfiguration {
}
```

Đây là class Java **có thể biên dịch riêng** trong project Spring Boot có các dependency thích hợp, nhưng chỉ khai báo cấu hình, không phải chương trình chạy độc lập có phương thức `main`.

Ngoài annotation, Spring Boot cũng hỗ trợ property:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Trong `application.yml` có thể khai báo:

```yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Khi cần nhiều tên trong `.properties`, sử dụng danh sách phân cách bằng dấu phẩy:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration
```

**Sự khác biệt về quản trị:**

- `excludeName` trong annotation đặt quyết định loại trừ ở mã nguồn và gắn với cấu hình khởi động.
- `spring.autoconfigure.exclude` cho phép thay đổi danh sách thông qua property sources theo môi trường, profile hoặc tham số khởi động; dễ áp dụng khi bạn không muốn sửa Java.
- Các nguồn loại trừ từ annotation và property **có thể cùng được áp dụng**. Đặt property không có nghĩa xóa các excludes đã hard-code ở annotation; cũng không nên dựa vào property để “bật lại” một tên bị loại trừ ngay trên annotation.
- Cần đọc giá trị property cuối cùng theo **thứ tự ưu tiên property source**. Nếu một file cấu hình riêng định nghĩa lại danh sách, hãy kiểm tra hiệu quả thực tế khi khởi động.

Trong Spring Boot 3.3, tên đầy đủ của property là `spring.autoconfigure.exclude`; không nhầm với `spring.main.*` hay `spring.boot.*`.

## 6. Ví dụ kiểm chứng bằng JUnit 5 và `ApplicationContextRunner`

Để xác nhận hiệu quả thực tế, tạo **một tệp test hoàn chỉnh** tại `src/test/java/demo/ExcludeNameTest.java` trong dự án **Spring Boot 3.3.x, Java 17+**. Test dùng H2 và Spring JDBC để tạo tình huống có thể quan sát: không loại trừ thì auto-configuration tạo `DataSource`; khai báo `excludeName` hoặc property loại trừ thì không tạo `DataSource` tự động.

```java
package demo;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ExcludeNameTest {

    private static final String DATA_SOURCE_AUTO_CONFIGURATION =
            "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration";

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class AutoConfigurationEnabled {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(
            excludeName = DATA_SOURCE_AUTO_CONFIGURATION
    )
    static class AutoConfigurationWithExcludeName {
    }

    private ApplicationContextRunner jdbcRunner() {
        return new ApplicationContextRunner().withPropertyValues(
                "spring.datasource.url=jdbc:h2:mem:exclude_name_test",
                "spring.datasource.username=sa",
                "spring.datasource.password="
        );
    }

    @Test
    void baselineCreatesDataSourceAutomatically() {
        jdbcRunner()
                .withUserConfiguration(AutoConfigurationEnabled.class)
                .run(context -> assertEquals(
                        1,
                        context.getBeansOfType(DataSource.class).size()
                ));
    }

    @Test
    void excludeNamePreventsDataSourceAutoConfiguration() {
        jdbcRunner()
                .withUserConfiguration(AutoConfigurationWithExcludeName.class)
                .run(context -> assertTrue(
                        context.getBeansOfType(DataSource.class).isEmpty()
                ));
    }

    @Test
    void propertyAlsoPreventsDataSourceAutoConfiguration() {
        jdbcRunner()
                .withUserConfiguration(AutoConfigurationEnabled.class)
                .withPropertyValues(
                        "spring.autoconfigure.exclude="
                                + DATA_SOURCE_AUTO_CONFIGURATION
                )
                .run(context -> assertTrue(
                        context.getBeansOfType(DataSource.class).isEmpty()
                ));
    }
}
```

Điểm cần lưu ý khi đọc test:

1. `AutoConfigurationEnabled` là baseline, có `@EnableAutoConfiguration` và không loại trừ.
2. `AutoConfigurationWithExcludeName` dùng **chuỗi compile-time constant** với `@EnableAutoConfiguration(excludeName = ...)`; không cần import lớp auto-configuration đích.
3. `jdbcRunner()` cung cấp cấu hình JDBC/H2, không khai báo bất kỳ `@Bean DataSource` nào. Khi thư viện HikariCP và driver H2 hiện diện theo dependency bên dưới, nhánh mặc định có thể tạo datasource tự động.
4. Test thứ nhất xác nhận đúng **một bean `DataSource`** trong baseline; hai test sau xác nhận không có bean kiểu đó vì đường auto-configuration tạo nó đã bị loại trừ.
5. Mỗi `ApplicationContextRunner` chạy một application context độc lập. Test **không gọi database nghiệp vụ**, không yêu cầu server HTTP và không cần kết nối database bên ngoài.

Với một dự án Gradle Spring Boot 3.3.x **đã cấu hình plugin Spring Boot và dependency management**, thêm các dependency sau nếu chưa có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu dependency quản lý phiên bản theo Spring Boot BOM đúng, không cần ghi phiên bản riêng cho H2. Dòng `spring-boot-starter-jdbc` cung cấp đường tạo datasource và connection pool cho bài test, còn H2 là database in-memory. Các dependency này phục vụ **kịch bản test**; một ứng dụng chỉ dùng `excludeName` ở mức annotation không bắt buộc phải thêm JDBC/H2.

Chạy kiểm thử từ root dự án Gradle:

```bash
./gradlew test --tests demo.ExcludeNameTest
```

Với Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.ExcludeNameTest
```

**Kết quả mong đợi:** **3 test pass**. Test baseline có một `DataSource`; hai test loại trừ không có `DataSource`. Đây là kỳ vọng dựa trên Spring Boot 3.3.x và bộ dependency mô tả, **không phải stdout của lần chạy thực tế**. Nếu project đã có cấu hình bổ sung tạo `DataSource` thủ công hoặc một starter khác can thiệp, cần cô lập test runner hoặc điều chỉnh assertion theo mục tiêu cần chứng minh.

### Trường hợp có bean tự đăng ký: điều gì xảy ra?

Giả sử ứng dụng bổ sung:

```java
@Bean
DataSource applicationDataSource() {
    // Trả về DataSource được ứng dụng quản lý.
}
```

Đây là đoạn **minh họa, không chạy độc lập**. Loại trừ `DataSourceAutoConfiguration` **không ngăn** ứng dụng đăng ký bean `applicationDataSource`. Chính vì vậy phép kiểm tra “context có `DataSource` hay không” trong test chỉ chứng minh được tác dụng loại trừ khi **không có một nguồn tạo `DataSource` khác**.

## 7. Vì sao tên class phải chính xác?

Với `excludeName`, Spring Boot xử lý một chuỗi. Trình biên dịch không thể phát hiện lỗi chính tả hoặc thay đổi package của tên auto-configuration.

Ví dụ:

```java
// ĐÚNG: tên đầy đủ của auto-configuration
@SpringBootApplication(excludeName =
    "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")

// SAI: thiếu package, không phải FQCN
@SpringBootApplication(excludeName = "DataSourceAutoConfiguration")

// SAI MỤC TIÊU: tên bean/implementation trong ứng dụng
@SpringBootApplication(excludeName = "demo.service.PaymentService")
```

Đây là các annotation minh họa độc lập, không gắn đồng thời lên một class.

Để tìm tên cần loại trừ đáng tin cậy:

1. Chạy ứng dụng với `--debug` để xem **Condition Evaluation Report**. Tìm auto-configuration liên quan tới bean/feature muốn vô hiệu hóa.
2. Đối chiếu lớp trong **Javadoc chính thức**, mã nguồn thư viện, hoặc file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` của dependency đang dùng.
3. Sao chép **FQCN chính xác**, bao gồm package và viết hoa/chữ thường. Không dùng `*`, tên bean hoặc pattern package.
4. Viết test xác nhận auto-configuration mong muốn đã bị bỏ, **không chỉ** kiểm tra app khởi động thành công.
5. Khi nâng phiên bản Spring Boot/starter, rà lại các tên đã hard-code và kiểm tra trường hợp tên lớp đã bị thay thế hoặc đổi vị trí.

Theo tài liệu Spring Boot, dù auto-configuration class được công khai, **tên lớp để loại trừ** mới là phần API được coi là công khai. Không nên phụ thuộc vào bean method, nested configuration class hay cấu trúc nội bộ của auto-configuration vì các chi tiết đó có thể thay đổi.

## 8. Các tình huống `excludeName` có giá trị

### 8.1. Module tùy chọn không có ở mọi runtime

Một ứng dụng triển khai nhiều biến thể: bản A có starter liên quan, bản B không cài. Cấu hình Java chung muốn loại trừ một auto-configuration của module A nhưng không muốn khai báo class literal phụ thuộc vào module đó.

```java
@SpringBootApplication(excludeName =
    "com.vendor.platform.autoconfigure.OptionalFeatureAutoConfiguration")
```

Ở đây tên `com.vendor.platform.autoconfigure.OptionalFeatureAutoConfiguration` là **giả định**; trước khi áp dụng, phải tìm đúng tên auto-configuration thực tế của thư viện. Dùng chuỗi giúp Java compile ngay cả khi lớp của vendor không có ở compile classpath. Trong biến thể không cài module, không có ứng viên tương ứng để loại trừ; trong biến thể có module, exclusion chỉ có ý nghĩa nếu nó thực sự tham gia cơ chế auto-configuration.

### 8.2. Meta-annotation dùng chung

Nếu đội phát triển xây dựng một annotation tập hợp chính sách cấu hình, nó có thể gắn `@EnableAutoConfiguration` làm meta-annotation với `excludeName`, ví dụ:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Configuration;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Configuration
@EnableAutoConfiguration(excludeName =
    "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
public @interface WithoutJdbcAutoConfiguration {
}
```

Đây là tệp Java **có thể biên dịch** khi dependency Spring Boot tồn tại; để sử dụng, gắn `@WithoutJdbcAutoConfiguration` lên một configuration class của ứng dụng. `excludeName` đặc biệt phù hợp ở vị trí meta-annotation vì tránh khai báo class literal trên annotation lồng nhau, đúng với khuyến nghị Javadoc.

Đừng tự tạo meta-annotation chỉ để tiết kiệm một dòng code nếu một `@SpringBootApplication(excludeName = ...)` trực tiếp đã đủ rõ ràng.

### 8.3. Cấu hình theo môi trường triển khai

Nếu chỉ một số deployment cần loại trừ, khai báo `spring.autoconfigure.exclude` ở property source có thể phù hợp hơn hard-code `excludeName`. Cả hai cùng loại trừ auto-configuration; lựa chọn chủ yếu liên quan việc **ai sở hữu quyết định**: code chung hay môi trường triển khai.

## 9. Sai lầm phổ biến và cách xử lý

**Sai lầm 1 — Cho `excludeName` một tên bean.** `"dataSource"` hoặc `"paymentService"` là tên bean, không phải FQCN của auto-configuration. Hãy tìm lớp auto-configuration thực sự hoặc dùng cơ chế dành cho bean/component.

**Sai lầm 2 — Cung cấp package thay vì class.** `"org.springframework.boot.autoconfigure.jdbc"` không loại trừ cả package. Giá trị phải là tên **một lớp**; dùng mảng `String[]` khi có nhiều lớp.

**Sai lầm 3 — Cho rằng loại trừ dependency.** Dù loại trừ auto-configuration, JDBC driver, HikariCP, Redis client... vẫn có thể có trên classpath. Nếu mục tiêu là giảm kích thước hoặc lỗ hổng dependency, cần sửa dependency graph bằng Gradle/Maven.

**Sai lầm 4 — Nghĩ rằng mọi bean liên quan đều biến mất.** Một `@Bean` tự khai báo, một `@Import` trực tiếp hoặc một auto-configuration khác vẫn có thể tạo bean cùng chức năng. Luôn kiểm chứng bean graph sau khởi động.

**Sai lầm 5 — Nhầm với `@ComponentScan(excludeFilters=...)`.** Bộ lọc component scan chủ yếu tác động component được quét; `excludeName` tác động danh sách **auto-configuration imports**. Nếu một `@Component` của ứng dụng đang bị quét, xử lý ở component scan hoặc cấu hình bean.

**Sai lầm 6 — Dùng một class không phải auto-configuration.** Spring Boot có thể từ chối exclusions trỏ tới class có mặt trên classpath nhưng không phải auto-configuration candidate. Không nên cố “loại mọi `@Configuration`” bằng `excludeName`.

**Sai lầm 7 — Gõ sai FQCN và kết luận exclusion đã có tác dụng.** Chuỗi không được Java compiler kiểm tra. Đặc biệt khi tên không có trên classpath, ứng dụng có thể vẫn chạy vì không có gì cần loại trừ. Kiểm tra báo cáo condition cùng các bean thực tế.

**Sai lầm 8 — Bỏ qua hệ quả gián tiếp.** Loại trừ một auto-configuration có thể khiến một auto-configuration khác không tìm được bean mong muốn; hoặc một fallback bean khác được kích hoạt. Test cả startup và các bean phụ thuộc, không chỉ bean chính.

**Sai lầm 9 — Dùng `excludeName` để thay `@ConditionalOnProperty`.** Nếu bạn làm chủ auto-configuration và muốn người dùng bật/tắt một chức năng theo cờ, hãy đặt condition cho chức năng đó. `excludeName` phù hợp khi ứng dụng **chủ động vô hiệu hóa cả auto-configuration** đã biết, thường là từ thư viện.

**Sai lầm 10 — Nhầm thời điểm tác dụng.** Auto-configuration exclusions được xử lý khi dựng context. Thay đổi property hay annotation sau khi ứng dụng đã chạy **không tự động** gỡ bean khỏi context đã khởi động.

## 10. Quy trình chẩn đoán thực tế

Khi một auto-configuration vẫn hoạt động sau khi bạn khai báo `excludeName`:

1. Kiểm tra annotation đang nằm trên **class khởi động thực sự**, hoặc kiểm tra `spring.autoconfigure.exclude` trong `Environment` cuối cùng.
2. Xác minh **tên class hoàn chỉnh** từ đúng phiên bản dependency đang chạy; không sao chép tên từ tài liệu của phiên bản khác mà không đối chiếu.
3. Xác minh target là **auto-configuration candidate** được Boot chọn thông qua imports, chứ không phải một user `@Configuration` hoặc bean thường.
4. Chạy với `--debug` để xem các điều kiện được match/không match và mục exclusions; nếu đã dùng Actuator, có thể xem `/actuator/conditions` theo cấu hình quyền truy cập của ứng dụng.
5. Kiểm tra bean sau startup, ví dụ `context.getBeansOfType(DataSource.class)` hoặc test `ApplicationContextRunner`; chỉ có log “excluded” chưa chắc giải thích tất cả bean đã có.
6. Nếu bean vẫn tồn tại, truy ra **nguồn định nghĩa bean**: code `@Bean`, component scan, import thủ công hay auto-configuration khác.
7. Test ít nhất hai bối cảnh: **không loại trừ** và **có loại trừ**, cùng một dependency/runtime set, để chứng minh chênh lệch thật.

Cách đọc thông báo lỗi cần chính xác: `ClassNotFoundException`/`NoClassDefFoundError` từ một phần code khác không nhất thiết do `excludeName` gây ra; thuộc tính chuỗi không tự bảo vệ mọi tham chiếu class tùy chọn trong toàn ứng dụng. Ngược lại, lỗi “not auto-configuration classes” cho biết bạn đã nhắm sai loại class hoặc candidate không đúng.

## 11. Ghi nhớ

- `excludeName` nhận **`String[]` gồm FQCN của auto-configuration**: ví dụ `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`.
- Có thể dùng trong **`@SpringBootApplication` hoặc `@EnableAutoConfiguration`**. Nếu đã có class literal phù hợp, `exclude` là cách có kiểm tra kiểu tại compile time.
- `excludeName` rất hữu ích khi **class tùy chọn không thể tham chiếu trực tiếp**; đặc biệt chú ý với composed/meta-annotations.
- Exclusion **chỉ chặn tự động nhập auto-configuration tương ứng**; nó không gỡ JAR, không chặn toàn bộ component scan và không xóa bean tự đăng ký.
- `spring.autoconfigure.exclude` là lựa chọn tương đương về cơ chế khi muốn điều khiển qua cấu hình môi trường.
- Tên chuỗi phải chính xác; kiểm tra Condition Evaluation Report và **test các bean sau khởi động**, nhất là khi nâng cấp dependency.

### Tài liệu chính thức để đối chiếu

- Spring Boot 3.3 Javadoc — `SpringBootApplication`, `exclude` và `excludeName`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html
- Spring Boot 3.3 Javadoc — `EnableAutoConfiguration`, exclusions và property `spring.autoconfigure.exclude`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
- Spring Boot Reference — *Auto-configuration*, phần disabling specific auto-configuration classes: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot 3.3 Reference — *Creating Your Own Auto-configuration*, imports của auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
