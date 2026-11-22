# NoneNestedConditions cho nhóm điều kiện phủ định

## 1. Khi nào cần NoneNestedConditions?

Một custom starter đôi khi chỉ nên tạo bean fallback khi **không có bất kỳ một lựa chọn thay thế nào được bật**.

Ví dụ, Acme cung cấp cache local mặc định. Cache local chỉ nên xuất hiện khi Redis chưa được bật và Hazelcast cũng chưa được bật. Nếu một trong hai integration remote được chọn, auto-configuration của cache local phải bị bỏ qua.

Biểu thức logic:

```text
LocalCacheEnabled = NOT (RedisEnabled OR HazelcastEnabled)
                 = NOT RedisEnabled AND NOT HazelcastEnabled
```

`NoneNestedConditions` biểu diễn chính xác phép phủ định của một nhóm điều kiện OR. Đây là lớp abstract trong `org.springframework.boot.autoconfigure.condition`, kế thừa `AbstractNestedCondition`. Nó match khi **không có nested class condition nào match**.

Mỗi nested class là một marker class, mang annotation condition riêng. Nhờ vậy mỗi nhánh loại trừ có tên và thông điệp chẩn đoán độc lập.

## 2. Phân biệt None, Any và All

| Lớp | Kết quả match | Logic |
| --- | --- | --- |
| `AnyNestedCondition` | Có ít nhất một nested condition match | `A OR B OR C` |
| `AllNestedConditions` | Tất cả nested condition đều match | `A AND B AND C` |
| `NoneNestedConditions` | Không nested condition nào match | `NOT (A OR B OR C)` |

Với hai điều kiện A và B:

| A | B | Any | All | None |
| --- | --- | --- | --- | --- |
| false | false | false | false | true |
| true | false | true | false | false |
| false | true | true | false | false |
| true | true | true | true | false |

Chỉ cần một member condition match thì `NoneNestedConditions` không match. Đây là điểm dễ nhầm nhất khi đọc chữ “none”.

Các ví dụ:

- `AnyNestedCondition`: bật integration nếu Redis **hoặc** Hazelcast được chọn.
- `AllNestedConditions`: bật tính năng khi property đã bật **và** class cần thiết có trên classpath.
- `NoneNestedConditions`: bật fallback local khi **không** có Redis **và không** có Hazelcast được chọn.

Nếu chỉ cần phủ định một điều kiện, annotation có sẵn như `@ConditionalOnMissingClass` hoặc `@ConditionalOnProperty` có thể đơn giản hơn. `NoneNestedConditions` hữu ích khi cần phủ định **một nhóm nhiều điều kiện khác nhau**.

## 3. Cấu trúc một custom NoneNestedConditions

Một condition tổng hợp có ba phần:

1. Lớp Java kế thừa `NoneNestedConditions`.
2. Constructor gọi `super(ConfigurationPhase...)` để chọn giai đoạn đánh giá.
3. Các nested marker class khai báo điều kiện thành viên bằng annotation.

Ví dụ:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.NoneNestedConditions;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;

static class OnNeitherRedisNorHazelcast extends NoneNestedConditions {

    OnNeitherRedisNorHazelcast() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
            prefix = "acme.cache.redis",
            name = "enabled",
            havingValue = "true")
    static class RedisEnabled {
    }

    @ConditionalOnProperty(
            prefix = "acme.cache.hazelcast",
            name = "enabled",
            havingValue = "true")
    static class HazelcastEnabled {
    }
}
```

`RedisEnabled` match khi `acme.cache.redis.enabled=true`. `HazelcastEnabled` match khi `acme.cache.hazelcast.enabled=true`. Condition tổng hợp chỉ match khi cả hai nested condition đều không match.

Các nested class là marker class: không cần bean method hoặc logic Java riêng. Annotation trên từng class cung cấp tiêu chí để Spring Boot đánh giá.

## 4. Chọn đúng ConfigurationPhase

Constructor của `NoneNestedConditions` bắt buộc nhận `ConfigurationPhase`. Giá trị này quyết định thời điểm nhóm nested conditions được đánh giá.

### 4.1. PARSE_CONFIGURATION

Dùng khi các nested conditions có thể được đánh giá trong lúc parse cấu hình, chẳng hạn:

- `@ConditionalOnClass` / `@ConditionalOnMissingClass`.
- `@ConditionalOnProperty`.
- Các điều kiện kiểm tra resource, JNDI hoặc môi trường mà không cần đọc bean registry.

Ví dụ cache bên dưới dùng property conditions, nên chọn:

```java
NoRemoteCacheEnabledCondition() {
    super(ConfigurationPhase.PARSE_CONFIGURATION);
}
```

`PARSE_CONFIGURATION` có nghĩa condition được đánh giá khi một lớp cấu hình đang được parse. Nếu condition không match, lớp cấu hình có thể bị bỏ qua trước khi các bean method của nó được xử lý.

### 4.2. REGISTER_BEAN

Dùng khi các nested conditions cần xem bean definitions đã được đăng ký, ví dụ `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`.

Một mẫu khác: chỉ tạo `Clock` fallback khi context chưa có `DataSource` và cũng chưa có `Clock`:

```java
import java.time.Clock;
import javax.sql.DataSource;

import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.NoneNestedConditions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;

class OnNeitherDataSourceNorClock extends NoneNestedConditions {

    OnNeitherDataSourceNorClock() {
        super(ConfigurationPhase.REGISTER_BEAN);
    }

    @ConditionalOnBean(DataSource.class)
    static class DataSourceExists {
    }

    @ConditionalOnBean(Clock.class)
    static class ClockExists {
    }
}

@Configuration(proxyBeanMethods = false)
class FallbackClockConfiguration {

    @Bean
    @Conditional(OnNeitherDataSourceNorClock.class)
    Clock fallbackClock() {
        return Clock.systemUTC();
    }
}
```

Condition được đặt trên **phương thức `@Bean`**, để được đánh giá ở giai đoạn đăng ký bean. Nếu một bean `DataSource` hoặc `Clock` đã được xử lý, một nested condition match và condition tổng hợp không match; fallback không được đăng ký.

`REGISTER_BEAN` không có nghĩa là đợi mọi object được khởi tạo xong. Đây là phase đăng ký bean definition; bean conditions kiểm tra những definition mà container đã biết tại thời điểm đó.

### 4.3. Không trộn lẫn hai phase

Các nested conditions trong một nhóm phải tương thích với phase của condition tổng hợp.

- Nhóm chỉ chứa property/classpath checks: chọn `PARSE_CONFIGURATION`.
- Nhóm chứa bean checks: chọn `REGISTER_BEAN`.
- Nếu cần cả property check và bean check, cân nhắc tách thành hai lớp condition hoặc hai lớp cấu hình có phase riêng, thay vì ép các member khác phase vào cùng một nhóm.

Đặc biệt, condition phase `REGISTER_BEAN` không dùng để ngăn một `@Configuration` class được parse. Nếu mục tiêu là điều kiện theo bean, thường đặt condition tổng hợp trên `@Bean` method như ví dụ `FallbackClockConfiguration`.

## 5. Ví dụ thực tế: chỉ tạo cache local khi không chọn cache remote

Ta xây một auto-configuration tạo `CacheStore` local mặc định. Nếu Redis hoặc Hazelcast được bật, cấu hình local sẽ không được áp dụng. Ví dụ dùng Spring Boot 3.3.5 và Java 17+.

### 5.1. Cấu trúc project

```text
none-nested-conditions-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/cache/CacheStore.java
    │   ├── java/demo/autoconfigure/
    │   │   ├── NoRemoteCacheEnabledCondition.java
    │   │   └── LocalCacheAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/autoconfigure/
        └── LocalCacheAutoConfigurationTests.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>none-nested-conditions-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-autoconfigure` cung cấp `NoneNestedConditions`, `@AutoConfiguration` và các condition annotation. `spring-boot-starter-test` chỉ phục vụ test, cung cấp JUnit, AssertJ và `ApplicationContextRunner`.

### 5.3. Contract cache: `CacheStore.java`

Tệp `src/main/java/demo/cache/CacheStore.java`:

```java
package demo.cache;

public record CacheStore(String provider) {
}
```

Trong starter thật, contract có thể là interface với các thao tác get/put/evict. Ví dụ dùng record để tập trung vào kết quả condition và dễ assertion.

### 5.4. Nhóm điều kiện phủ định: `NoRemoteCacheEnabledCondition.java`

Tệp `src/main/java/demo/autoconfigure/NoRemoteCacheEnabledCondition.java`:

```java
package demo.autoconfigure;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.NoneNestedConditions;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;

class NoRemoteCacheEnabledCondition extends NoneNestedConditions {

    NoRemoteCacheEnabledCondition() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
            prefix = "acme.cache.redis",
            name = "enabled",
            havingValue = "true")
    static class RedisEnabled {
    }

    @ConditionalOnProperty(
            prefix = "acme.cache.hazelcast",
            name = "enabled",
            havingValue = "true")
    static class HazelcastEnabled {
    }
}
```

Mỗi property có `matchIfMissing=false` theo mặc định. Vì vậy, khi property vắng mặt hoặc không có giá trị `true`, nested condition tương ứng không match.

| Redis enabled | Hazelcast enabled | Condition tổng hợp | Local fallback |
| --- | --- | --- | --- |
| thiếu/false | thiếu/false | Match | Được phép |
| true | thiếu/false | Không match | Bị bỏ qua |
| thiếu/false | true | Không match | Bị bỏ qua |
| true | true | Không match | Bị bỏ qua |

### 5.5. Auto-configuration local: `LocalCacheAutoConfiguration.java`

Tệp `src/main/java/demo/autoconfigure/LocalCacheAutoConfiguration.java`:

```java
package demo.autoconfigure;

import demo.cache.CacheStore;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration
@Conditional(NoRemoteCacheEnabledCondition.class)
public class LocalCacheAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CacheStore.class)
    public CacheStore localCacheStore() {
        return new CacheStore("local");
    }
}
```

Có hai lớp quyết định độc lập:

1. `@Conditional(NoRemoteCacheEnabledCondition.class)` quyết định toàn bộ local auto-configuration có được áp dụng hay không.
2. `@ConditionalOnMissingBean(CacheStore.class)` cho phép ứng dụng cung cấp `CacheStore` custom để thay thế bean mặc định.

Nếu Redis hoặc Hazelcast được bật, lớp local auto-configuration bị bỏ qua. Nếu không có remote provider nào được chọn, lớp được áp dụng; bean local chỉ được tạo nếu chưa có `CacheStore` khác.

Trong hệ thống thật, Redis/Hazelcast integration phải có auto-configuration riêng để đăng ký provider tương ứng. Ví dụ này chỉ nạp local auto-configuration để kiểm tra chính xác điều kiện loại trừ.

### 5.6. Đăng ký auto-configuration

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
demo.autoconfigure.LocalCacheAutoConfiguration
```

Spring Boot 3.x dùng file `AutoConfiguration.imports` để phát hiện auto-configuration trong JAR. Nếu không đăng ký lớp này, việc viết đúng `@AutoConfiguration` và condition vẫn chưa đủ để ứng dụng tự động nạp nó.

## 6. Kiểm thử các nhánh logic bằng ApplicationContextRunner

Tạo tệp `src/test/java/demo/autoconfigure/LocalCacheAutoConfigurationTests.java`:

```java
package demo.autoconfigure;

import demo.cache.CacheStore;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class LocalCacheAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            LocalCacheAutoConfiguration.class));

    @Test
    void createsLocalCacheWhenNoRemoteProviderIsEnabled() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(CacheStore.class);
            assertThat(context.getBean(CacheStore.class).provider())
                    .isEqualTo("local");
        });
    }

    @Test
    void skipsLocalCacheWhenRedisIsEnabled() {
        this.runner
                .withPropertyValues("acme.cache.redis.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CacheStore.class);
                });
    }

    @Test
    void skipsLocalCacheWhenHazelcastIsEnabled() {
        this.runner
                .withPropertyValues("acme.cache.hazelcast.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CacheStore.class);
                });
    }

    @Test
    void skipsLocalCacheWhenBothRemoteProvidersAreEnabled() {
        this.runner
                .withPropertyValues(
                        "acme.cache.redis.enabled=true",
                        "acme.cache.hazelcast.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CacheStore.class);
                });
    }

    @Test
    void userDefinedCacheStoreReplacesLocalDefault() {
        this.runner
                .withBean(CacheStore.class, () -> new CacheStore("custom"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CacheStore.class);
                    assertThat(context).doesNotHaveBean("localCacheStore");
                    assertThat(context.getBean(CacheStore.class).provider())
                            .isEqualTo("custom");
                });
    }
}
```

### 6.1. Chạy test

Từ thư mục project:

```bash
mvn -q test
```

Năm test xác nhận:

- Không chọn remote: local cache được tạo.
- Chọn Redis: local cache bị bỏ qua.
- Chọn Hazelcast: local cache bị bỏ qua.
- Chọn cả hai: local cache bị bỏ qua.
- Có cache custom: local default nhường chỗ.

`ApplicationContextRunner` tạo context nhỏ cho từng kịch bản rồi đóng context sau khi assertion chạy. Nó phù hợp để kiểm tra condition mà không cần khởi động web server hoặc ứng dụng đầy đủ.

## 7. Đọc Condition Evaluation Report khi nhóm phủ định không match

Mỗi nested condition có kết quả riêng. Khi bật `--debug` trên ứng dụng thật, Spring Boot in Condition Evaluation Report. Nếu đã expose Actuator endpoint `conditions`, có thể đọc report dưới dạng JSON.

Khi không chọn remote cache:

- `RedisEnabled` không match.
- `HazelcastEnabled` không match.
- `NoRemoteCacheEnabledCondition` match vì không có member condition nào match.
- `LocalCacheAutoConfiguration` được áp dụng.
- `localCacheStore` được đăng ký nếu `CacheStore` chưa có bean custom.

Khi Redis được bật:

- `RedisEnabled` match.
- `HazelcastEnabled` không match.
- `NoRemoteCacheEnabledCondition` không match.
- `LocalCacheAutoConfiguration` bị bỏ qua.
- Bean local không được tạo từ auto-configuration này.

Không hard-code nguyên văn message report vào test. Message có thể thay đổi theo phiên bản Boot và nested member; hãy kiểm tra source, trạng thái match/no-match và bean registry.

Nếu cần expose Actuator endpoint để chẩn đoán:

```properties
management.endpoints.web.exposure.include=health,conditions
```

Endpoint conditions có thể tiết lộ tên configuration, bean và thông tin môi trường. Chỉ expose trên môi trường phù hợp và giới hạn truy cập cho người có quyền vận hành.

## 8. Khi nào nên dùng NoneNestedConditions?

Dùng `NoneNestedConditions` khi:

- Một fallback chỉ được tạo nếu không có integration hoặc mode nào trong một nhóm được bật.
- Nhiều nhánh loại trừ dùng annotation khác nhau, chẳng hạn property, classpath và JNDI.
- Muốn Condition Evaluation Report thể hiện rõ từng lý do khiến fallback bị loại.
- Cần đặt tên một quy tắc phủ định có ý nghĩa thay vì lặp lại logic condition ở nhiều configuration class.

| Fallback | Các điều kiện loại trừ |
| --- | --- |
| Local cache | Redis được bật hoặc Hazelcast được bật |
| Embedded database | PostgreSQL driver có mặt hoặc external database URL được khai báo |
| Default HTTP client | Reactor Netty có mặt hoặc client custom đã được cấu hình |
| Local scheduler | Quartz được bật hoặc scheduler cluster đã được chọn |
| Default metrics exporter | Prometheus exporter hoặc OTLP exporter được bật |

Các ví dụ này cần chọn đúng condition theo yêu cầu thực tế. Nếu chỉ muốn fallback nhường chỗ khi **đã có bean custom**, dùng `@ConditionalOnMissingBean` riêng cho bean method thường rõ hơn việc gộp nó vào một condition parse-phase.

## 9. Các bẫy thường gặp

1. **Nhầm None với All.** None match khi không có member nào match; All cần mọi member đều match.
2. **Đọc “none” như “ít nhất một điều kiện false”.** Với hai điều kiện, chỉ cần một member match là None không match. Hãy dùng bảng chân trị.
3. **Chọn sai phase.** Condition theo bean registry cần `REGISTER_BEAN`; property/classpath checks thường phù hợp `PARSE_CONFIGURATION`.
4. **Đặt condition REGISTER_BEAN trên configuration class.** Phase này dành cho việc đăng ký bean; nó không chặn parse configuration class như phase parse. Đặt trên `@Bean` method nếu cần.
5. **Trộn member condition khác phase.** Nhóm nested condition phải dùng phase tương thích; tách nhóm nếu cần kiểm tra cả parse-time và bean-time.
6. **Quên `matchIfMissing`.** Property không tồn tại thường khiến nested `@ConditionalOnProperty` không match. Trong nhóm None, điều đó có thể làm fallback được bật. Ghi rõ default property trong tài liệu.
7. **Cho phép giá trị property không hợp lệ.** Nếu người dùng gõ sai tên hoặc giá trị provider, không nested condition nào match và fallback có thể được tạo. Hãy validate cấu hình được phép thay vì dùng None làm bộ kiểm tra enum.
8. **Bật đồng thời nhiều remote provider.** None chỉ loại fallback local; nó không chọn Redis hay Hazelcast và cũng không bảo đảm hai integration không cùng tạo bean. Cần validation hoặc policy riêng nếu chỉ được chọn một provider.
9. **Bỏ qua user bean.** Condition nhóm có thể match và configuration class được áp dụng, nhưng `@ConditionalOnMissingBean` vẫn phải cho custom bean nhường chỗ.
10. **Dùng condition tổng hợp cho logic quá đơn giản.** Nếu chỉ phủ định một class, dùng `@ConditionalOnMissingClass`. Nếu chỉ kiểm tra một property, dùng `@ConditionalOnProperty`.
11. **Không đăng ký auto-configuration.** Quên file `AutoConfiguration.imports` khiến ứng dụng không phát hiện cấu hình, dù condition đã viết đúng.
12. **Chỉ kiểm tra Condition Report.** Hãy assertion bean type/name và giá trị implementation để xác nhận kết quả cuối cùng.

## 10. Checklist review một nhóm điều kiện phủ định

- [ ] Đã viết rõ từng member condition bằng tên có ý nghĩa.
- [ ] Đã xác định biểu thức tổng hợp là NOT(A OR B OR ...).
- [ ] Đã lập bảng chân trị cho các tổ hợp quan trọng.
- [ ] Đã chọn ConfigurationPhase phù hợp với member conditions.
- [ ] Nếu dùng REGISTER_BEAN, condition được đặt trên bean method hoặc điểm đăng ký bean phù hợp.
- [ ] Đã kiểm tra property thiếu, false, true và giá trị không hợp lệ.
- [ ] Đã kiểm tra trường hợp nhiều member cùng match.
- [ ] Đã kiểm tra bean custom và back-off của fallback.
- [ ] Đã đăng ký auto-configuration trong `AutoConfiguration.imports`.
- [ ] Đã test bằng `ApplicationContextRunner` trên đúng Spring Boot version.
- [ ] Đã đọc report để hiểu từng nested condition.
- [ ] Đã kiểm tra bean registry để xác nhận fallback thực tế.

## Tài liệu chính thức

- [Spring Boot 3.3 — `NoneNestedConditions` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/NoneNestedConditions.html): định nghĩa “match khi không nested class condition nào match” và constructor nhận `ConfigurationPhase`.
- [Spring Boot 3.3 — `AnyNestedCondition` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AnyNestedCondition.html): nhóm condition theo phép OR.
- [Spring Boot 3.3 — `AllNestedConditions` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AllNestedConditions.html): nhóm condition theo phép AND.
- [Spring Framework 6.1 — `ConfigurationCondition.ConfigurationPhase` API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html): khác biệt giữa `PARSE_CONFIGURATION` và `REGISTER_BEAN`.
- [Spring Boot 3.3 — Developing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): đăng ký auto-configuration và kiểm thử với `ApplicationContextRunner`.
- [Spring Boot 3.3 — Conditions Actuator API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): đọc Condition Evaluation Report qua endpoint conditions.
