# Thay đổi cấu hình, thuộc tính và cơ chế tự cấu hình

Khi thực hiện **Java Advance Compatibility Migration**, nâng JDK thường đi cùng việc nâng Spring Boot, Spring Framework, Hibernate ORM, Jakarta EE runtime hoặc các nền tảng như Quarkus và Micronaut. Một ứng dụng có thể **biên dịch thành công** nhưng hành vi thay đổi vì property bị đổi tên, default value thay đổi, thứ tự nạp cấu hình khác trước hoặc một starter tự động đăng ký thêm/bớt bean.

Đây là nhóm lỗi khó phát hiện: không phải thay đổi nào cũng gây exception. Có thể dịch vụ vẫn trả HTTP 200 nhưng dùng sai database, timeout mặc định, không bật validation, thay provider gửi email hoặc expose endpoint quản trị ngoài dự kiến. Trong quá trình nâng Java, cần xem **cấu hình như một hợp đồng vận hành** giữa source code, framework, dependency, môi trường triển khai và người vận hành.

Bài học trình bày cách kiểm kê và chuyển đổi cấu hình, phân biệt thay đổi thuộc tính với thay đổi cơ chế auto-configuration, ví dụ trên Spring Boot và các framework khác, cách chẩn đoán bean graph/property binding, kiểm thử và tổ chức triển khai tương thích. Nội dung thuộc chương **Framework và nền tảng**; mục tiêu là giữ **hành vi quan sát được** sau migration, không chỉ làm cho ứng dụng khởi động được.

## 1. Cấu hình là một phần của runtime contract

Một ứng dụng Java có thể lấy cấu hình từ nhiều nguồn:

- File `application.properties`, `application.yml` hoặc file cấu hình theo profile.
- Biến môi trường do hệ điều hành/container cung cấp.
- JVM system properties như `-Duser.timezone=UTC`.
- Application command-line arguments.
- Kubernetes ConfigMap, Secret, Helm values và file mount.
- Config server, Vault, Consul hoặc cơ chế secret management.
- Feature flag service hoặc database configuration.
- Giá trị mặc định nằm trong framework/starter.
- Build-time configuration cho AOT/native-image.
- Test-only property sources, IDE run configurations và CI profiles.

**Một key có thể xuất hiện ở nhiều nguồn**, nên ứng dụng không nhất thiết dùng giá trị trong file của repository.

Ví dụ cấu hình:

~~~yaml
# application.yml
server:
  port: 8080

acme:
  connector:
    enabled: true
    timeout: 3s
~~~

Nếu deployment inject biến môi trường `ACME_CONNECTOR_TIMEOUT=10s` và framework bind tương ứng, effective timeout có thể là 10 giây. Nếu framework đổi cách giải key hoặc precedence, hành vi có thể thay dù YAML không đổi.

### 1.1. Các tầng thay đổi cần tách biệt

| Tầng | Câu hỏi | Rủi ro |
|---|---|---|
| Property name | Key cũ còn được nhận diện? | Cấu hình bị bỏ qua |
| Type và unit | Giá trị bind thành kiểu gì? | 5000 milliseconds bị hiểu thành 5000 seconds |
| Default | Khi không khai báo key, kết quả gì? | Tính năng bật/tắt khác trước |
| Property source | Nguồn nào có precedence cao nhất? | Production override không được áp dụng |
| Profile | File nào thực sự được kích hoạt? | Dùng nhầm môi trường |
| Auto-configuration | Bean nào được tạo từ classpath và conditions? | Thiếu hoặc thừa implementation |
| Lifecycle | Giá trị được đọc khi build, startup hay runtime? | Đổi env nhưng process không cập nhật |
| Security | Auth, TLS, endpoints quản trị giữ chính sách? | Lộ tài nguyên |
| Persistence | Datasource/ORM/transaction cấu hình đúng? | Kết nối sai DB hoặc khác SQL behavior |
| Observability | Health/metrics/tracing còn được tạo? | Không thấy regression |

Không thể thay thế kiểm tra các tầng này bằng việc chạy một lượt find-and-replace trong YAML.

## 2. Phân biệt thay đổi JDK với thay đổi framework

Nâng JDK có thể ảnh hưởng đến:
- Charset/encoding defaults, locale, timezone và dữ liệu tzdb.
- TLS protocols, truststore, crypto providers.
- JPMS strong encapsulation và reflective access.
- JVM flags, agent loading và Security Manager.
- Class-file format và các API Java SE.

Nâng framework có thể ảnh hưởng đến:
- Property key/deprecation/removal.
- Profile activation và config data loading.
- Điều kiện đăng ký bean và auto-configuration.
- Framework dependencies, starters, annotation processors.
- Jakarta namespace từ `javax.*` sang `jakarta.*`.
- Default serialization, validation, transaction và security.
- Web server, health, metrics, tracing và startup lifecycle.

Hai thay đổi thường kết hợp:

~~~text
JDK 11 -> JDK 17 hoặc 21
             |
             +-- Spring Boot 2.x -> 3.x
                        |
                        +-- Jakarta namespace
                        +-- Property renames
                        +-- New auto-configuration
                        +-- New ORM and web dependencies
                        +-- Different defaults
~~~

Không được kết luận “lỗi do Java 17” chỉ vì lỗi xuất hiện sau khi chuyển image JDK. Cần ghi **version JDK, framework, plugin, starter và dependency** của từng baseline.

## 3. Lập inventory cấu hình trước khi migration

Trước khi sửa code, lập bảng cho những property tác động vận hành: database, broker, HTTP clients, timeout, retry, bảo mật, metrics, feature flags và scheduled jobs.

| Property/điều kiện | Nguồn | Kiểu | Owner | Hành vi được mong đợi |
|---|---|---|---|---|
| `server.port` | Helm/env | Port | Platform | HTTP listener đúng cổng |
| `spring.datasource.url` | Config/Secret | JDBC URL | Data | Đúng database |
| `spring.profiles.active` | Launcher/env | Profile list | Release | Nạp prod configuration |
| `acme.connector.timeout` | YAML/env | Duration | Integration | Timeout 3s hoặc theo môi trường |
| `management.endpoints.web.exposure.include` | YAML | Endpoint list | SRE/Security | Chỉ expose endpoint được phép |
| `feature.billing-v2` | Feature flag | Boolean | Product | Bật/tắt code path có kiểm soát |
| `@ConditionalOnClass` | Runtime classpath | Presence | Framework | Chọn implementation phù hợp |

Đừng ghi giá trị secret vào inventory; chỉ ghi tên, nguồn cung cấp, kiểu, owner và test xác minh.

### 3.1. Tìm trong source và deployment artifacts

Ví dụ tìm kiếm trong repository thực tế:

~~~bash
rg -n --hidden -g '!**/.git/**' \
  'spring\.|quarkus\.|micronaut\.|management\.|server\.|datasource' .

rg -n --hidden -g '!**/.git/**' \
  'SPRING_PROFILES_ACTIVE|SPRING_CONFIG|JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS|--spring\.' .
~~~

File cần khảo sát có thể nằm ở:
- `src/main/resources/application.yml` và các file profile.
- `src/test/resources`.
- `pom.xml` hoặc `build.gradle(.kts)`.
- Dockerfile, entrypoint shell scripts, Windows service config.
- Helm chart, Kubernetes manifests, Kustomize.
- CI variables, pipeline templates.
- Remote config service và secret store.

Tìm text **không nhìn thấy giá trị đã render ở production**. Có thể phải kiểm tra manifest và effective environment thông qua quy trình quản trị hạ tầng, với dữ liệu nhạy cảm được che.

### 3.2. Cần ghi cả config không xuất hiện trong file

Một dependency starter có thể tự đăng ký:
- DataSource từ JDBC driver trên classpath.
- Web server theo web framework dependencies.
- JSON serializer hoặc validation provider.
- Metrics registry và health indicator.
- Security filter chain hoặc các component mặc định.
- HTTP client và connection pool.

Vì vậy inventory cần có **classpath/dependency graph và auto-configuration report**, không chỉ liệt kê key YAML.

## 4. Property rename, removal và semantic change

Những dạng thay đổi phổ biến:

| Loại | Đặc điểm | Cách xử lý |
|---|---|---|
| Rename | Key đổi tên, ý nghĩa gần tương đương | Sửa mọi nguồn và test binding |
| Removed | Key không còn chức năng | Bỏ và thay cơ chế nếu cần |
| Split | Một key chia thành nhiều key | Chốt semantics riêng |
| Merge | Nhiều key thành một cấu hình | Giải quyết conflict |
| Type change | Integer -> Duration, string -> enum | Ghi rõ unit và input validation |
| Default change | Không khai báo mà behavior khác | Cấu hình explicit |
| Scope change | Global -> per-client/per-profile | Chuyển đúng vị trí |
| Conditional change | Bean chỉ tạo khi dependency/property khác | Test conditions |
| Behavior change | Cùng key nhưng semantics mới | Test nghiệp vụ/integration |
| Deprecation | Key còn alias tạm | Lập kế hoạch loại bỏ |

### 4.1. Một ví dụ Spring Boot 2.x -> 3.x

Một số đổi tên được ghi nhận trong migration từ Spring Boot 2 sang 3, chẳng hạn:

| Trước | Sau ở stack Boot 3 tương ứng | Lưu ý |
|---|---|---|
| `spring.redis.host` | `spring.data.redis.host` | Kiểm tra Redis auto-config đang dùng |
| `spring.redis.port` | `spring.data.redis.port` | Xác minh env override |
| `server.max-http-header-size` | `server.max-http-request-header-size` | Header request/response có phạm vi khác nhau |

Ví dụ cũ:

~~~yaml
spring:
  redis:
    host: redis.internal
    port: 6379

server:
  max-http-header-size: 16KB
~~~

Ví dụ hướng chuyển trên một release Boot 3 phù hợp:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379

server:
  max-http-request-header-size: 16KB
~~~

Bảng là minh họa cho **một migration cụ thể**, không phải danh sách đầy đủ hoặc công thức áp dụng cho mọi Spring Boot minor/major version. Phải dùng **configuration properties appendix và migration guide của release đích** để xác nhận key, default và behavior.

### 4.2. Key bị bỏ qua có thể nguy hiểm hơn lỗi startup

Khi framework không fail nếu gặp unknown property:
- Connection timeout có thể về default dài hơn.
- Circuit breaker/feature flag có thể không được kích hoạt.
- HTTP header limit có thể sai.
- Connection pool size có thể khác.
- Security/management endpoint configuration có thể không được áp dụng.

Startup thành công không chứng minh property đã được đọc. Cần **xác nhận effective value và kết quả chức năng**.

### 4.3. Spring Boot Properties Migrator là công cụ tạm

Trong các release hỗ trợ, `spring-boot-properties-migrator` có thể hỗ trợ phát hiện một số key đã đổi khi nâng Spring Boot, và có thể dùng alias tạm theo phạm vi công cụ.

Maven minh họa:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-properties-migrator</artifactId>
  <scope>runtime</scope>
</dependency>
~~~

Gradle minh họa:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
}
~~~

Hãy xác minh công cụ có hỗ trợ **đúng release** đang nâng. Dùng để chẩn đoán, sửa các nguồn config thực, rồi **bỏ dependency migrator**. Công cụ không tự xử lý mọi key, defaults, semantics hoặc cấu hình ở secret/config service.

## 5. Property sources và thứ tự ưu tiên

Spring Boot có nhiều property sources: config data, profile-specific config, environment variables, Java system properties, command-line arguments, JSON application properties và test-specific overrides. **Thứ tự precedence đầy đủ phụ thuộc framework version và nguồn**, nên dùng tài liệu chính thức của đúng release thay vì một danh sách rút gọn.

Ví dụ:

~~~yaml
# application.yml
acme:
  connector:
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
acme:
  connector:
    timeout: 5s
~~~

Biến môi trường trong container:

~~~text
ACME_CONNECTOR_TIMEOUT=10s
~~~

Giá trị effective có thể là 10s. Nếu launcher truyền thêm một argument có precedence cao hơn, giá trị lại khác. Cần biết **tất cả source đang được nạp**, không chỉ đoạn YAML ở repository.

### 5.1. Relaxed binding không phải phép thay ký tự tùy ý

Trong Spring Boot, `@ConfigurationProperties` thường hỗ trợ những biến thể đặt tên phù hợp với relaxed binding, ví dụ từ key dạng kebab-case sang Java camelCase. Nhưng quy tắc cho environment variables, list indices và map keys có chi tiết riêng.

Ví dụ key canonical:

~~~text
acme.connector.read-timeout
~~~

Có thể được ánh xạ theo quy tắc environment binding tương ứng. Tuy nhiên không tự suy luận mọi biến thể underscore/camelCase đều hợp lệ. **Ghi đúng tên biến môi trường thực** sẽ được inject vào container/CI và test trên framework version đích.

### 5.2. Placeholder và default tạo dependency ẩn

~~~yaml
acme:
  connector:
    base-url: "${ACME_CONNECTOR_URL}"
    timeout: "${ACME_TIMEOUT:3s}"
~~~

Trong ví dụ, nếu `ACME_TIMEOUT` vắng mặt, ứng dụng có thể dùng 3s. Đó là default có thể chấp nhận được nếu nghiệp vụ đã phê duyệt; nhưng với DB URL, encryption key hoặc authentication secret, một fallback tùy tiện có thể nguy hiểm.

Phân biệt:
- **Required config**: fail-fast khi thiếu.
- **Optional config**: default có tài liệu và test.
- **Secret**: lấy từ source bảo mật, không log raw value.
- **Feature flag**: default và rollout semantics rõ.

## 6. Profiles và Config Data API

Profile quyết định những config source nào được activate. Một ứng dụng có thể chạy đúng local nhưng sai production vì profile config không còn được nạp theo cách cũ.

Ví dụ:

~~~yaml
# application.yml
acme:
  connector:
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
acme:
  connector:
    timeout: 10s
~~~

Spring Boot 2.4 đã thay đáng kể cách xử lý **config data**, bao gồm `spring.config.import` và một số quy tắc profile activation. Khi nâng từ những version cũ, cần kiểm tra:
- `spring.config.location` so với `spring.config.additional-location`.
- `spring.config.import` và nguồn remote.
- `spring.config.activate.on-profile` trong multi-document YAML.
- Các hạn chế về active/include profiles.
- Profile groups và thứ tự config data.
- Spring Cloud Config integration nếu dùng.

Ví dụ multi-document YAML:

~~~yaml
acme:
  connector:
    timeout: 3s
---
spring:
  config:
    activate:
      on-profile: prod
acme:
  connector:
    timeout: 10s
~~~

Không phải mọi cú pháp profile cũ có thể được đổi bằng một regex. Kiểm tra behavior bằng **effective configuration** của đúng process.

### 6.1. Profile không là ranh giới bảo mật

`spring.profiles.active=prod` không tự đảm bảo:
- Đúng database/Secret.
- TLS validation bật.
- Endpoint quản trị đã bảo vệ.
- Debug logging tắt.
- Cấu hình không bị environment ghi đè.

Security phải được kiểm chứng qua chính sách và negative tests, không chỉ tên profile.

## 7. @ConfigurationProperties: binding và validation

Spring Boot cung cấp `@ConfigurationProperties` để bind cấu hình sang Java type. Khi nâng framework hoặc JDK, cần xem constructor binding, property registration, type converters và validation behavior.

### 7.1. Ví dụ record trên Java 17 và Spring Boot 3

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.connector")
public record ConnectorProperties(
        boolean enabled,
        Duration timeout,
        String baseUrl
) {
    public ConnectorProperties {
        if (timeout == null) {
            timeout = Duration.ofSeconds(3);
        }
    }
}
~~~

Config:

~~~yaml
acme:
  connector:
    enabled: true
    timeout: 5s
    base-url: "https://gateway.internal"
~~~

Đăng ký bằng config class:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ConnectorProperties.class)
public class ConnectorConfig {
}
~~~

Một record có canonical constructor tương ứng có thể dùng constructor binding trong Spring Boot 3 khi được đăng ký đúng. **Không áp nguyên ví dụ sang Spring Boot 2/JDK 8**: record là Java feature mới và binding annotations/rules đã thay đổi qua release.

### 7.2. Đơn vị thời gian và dung lượng

Trước migration, code có thể đọc timeout theo milliseconds từ một số nguyên. Sau migration, property kiểu `Duration` có thể nhận `500ms`, `3s` hoặc `2m` theo converter tương ứng.

Nên ghi rõ:

~~~yaml
acme:
  connector:
    timeout: 3s
    max-payload: 10MB
~~~

Nếu dùng `max-payload`, class binding cũng phải khai báo field/record component tương ứng, chẳng hạn `DataSize maxPayload`. Ví dụ này minh họa tính rõ ràng về đơn vị, không phải framework built-in keys.

Tránh một config như `timeout: 3000` nếu framework version mới có thể hiểu đơn vị khác trước. Cần characterization test đối chiếu giá trị đã bind.

### 7.3. Jakarta Validation và @Validated

Nếu nâng từ Spring Boot 2/Java EE stack sang Spring Boot 3/Jakarta, validation annotations cũng đổi namespace:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.connector")
public record ConnectorProperties(
        @NotNull Duration timeout,
        @NotBlank String baseUrl
) {}
~~~

Để validation thực thi, project cần Jakarta Validation API và provider tương thích cùng cách đăng ký properties bean phù hợp. **Compile pass không bảo đảm validation có chạy**. Cần test property thiếu/blank và quan sát startup failure.

### 7.4. Unknown property

Nếu cấu hình viết sai `timeuot` thay vì `timeout`, một binder có thể bỏ qua key chưa biết rồi dùng default. Với các config quan trọng, cân nhắc strict binding/validation theo khả năng của framework.

Tuy nhiên, strict binding không nhìn thấy mọi property ở mọi source; nếu key nằm trong profile không active, hoặc một config service không được truy cập, cần kiểm tra inventory và startup config tương ứng.

### 7.5. @Value và @ConfigurationProperties khác nhau

Ví dụ:

~~~java
@Value("${acme.connector.timeout:3s}")
private Duration timeout;
~~~

và `@ConfigurationProperties` có thể cùng đạt mục đích đọc giá trị, nhưng khác về metadata, constructor/type binding, validation và khả năng test. Khi chuyển từ `@Value`, đừng quên giữ hoặc điều chỉnh **default 3s**. Xóa placeholder rồi dùng record constructor có thể đổi behavior với property vắng mặt.

## 8. Auto-configuration: điều kiện tạo bean

Spring Boot auto-configuration dựa vào classpath, môi trường, property values và bean definitions để tạo các component mặc định.

Một số điều kiện thường gặp:
- `@ConditionalOnClass`: dependency class có tồn tại không?
- `@ConditionalOnMissingClass`: dependency class vắng mặt?
- `@ConditionalOnBean`: đã có một bean cụ thể?
- `@ConditionalOnMissingBean`: chưa có bean cụ thể?
- `@ConditionalOnProperty`: property thỏa điều kiện?
- `@ConditionalOnWebApplication`: web environment phù hợp?
- `@ConditionalOnResource`: có resource?
- Custom conditions do framework/starter định nghĩa.

~~~text
                Runtime classpath
                       |
                Configuration sources
                       |
                  Bean definitions
                       |
                Evaluate conditions
                 /            \
              match          no match
                |               |
           Register bean      Skip bean
                |
          Initialize component
                |
             Behavior
~~~

**Cùng một YAML nhưng dependency graph khác có thể tạo bean graph khác.** Nâng framework/starter đôi khi làm một bean xuất hiện hoặc biến mất mà không có thay đổi trong application source.

### 8.1. @ConditionalOnProperty

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfig {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.metrics",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    MetricsExporter metricsExporter() {
        return new MetricsExporter();
    }
}
~~~

`MetricsExporter` là class minh họa của ứng dụng. Nếu property được đổi từ `acme.metrics.enabled` sang `acme.observability.enabled` nhưng annotation hoặc config chưa được sửa đồng bộ, bean có thể không được tạo.

Điều này có thể gây **silent behavior change** hơn là startup error nếu component optional.

### 8.2. @ConditionalOnMissingBean

~~~java
@Bean
@ConditionalOnMissingBean(OutboundClient.class)
OutboundClient outboundClient() {
    return new DefaultOutboundClient();
}
~~~

Ở đây, bean mặc định chỉ được tạo khi chưa có bean phù hợp. Sau migration:
- Starter khác có thể đã tạo một `OutboundClient`, khiến default không được tạo.
- Dependency bị loại bỏ có thể làm default bất ngờ xuất hiện.
- Bean type/qualifier hoặc search scope thay đổi có thể làm condition cho kết quả khác.

Cần quan sát condition evaluation report và bean graph, không suy đoán bằng thứ tự source files.

## 9. Auto-configuration registration của Spring Boot 2 và 3

Những thư viện/starter nội bộ cần đặc biệt chú ý đến cơ chế đăng ký auto-configuration.

### 9.1. Cơ chế cũ qua spring.factories

Một số starter Spring Boot 2.x đăng ký auto-configuration qua:

~~~text
META-INF/spring.factories
~~~

Nội dung kiểu:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.autoconfigure.OutboundAutoConfiguration
~~~

Đây là một **cách đăng ký auto-configuration cũ**. Không được suy rằng mọi công dụng khác của `spring.factories` trong Spring ecosystem đều bị loại bỏ.

### 9.2. AutoConfiguration.imports

Spring Boot 2.7 hỗ trợ cơ chế đăng ký mới; trong Spring Boot 3, auto-config registration sử dụng file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.example.autoconfigure.OutboundAutoConfiguration
~~~

Class minh họa:

~~~java
package com.example.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(OutboundClient.class)
@EnableConfigurationProperties(ConnectorProperties.class)
public class OutboundAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(OutboundClient.class)
    @ConditionalOnProperty(
            prefix = "acme.connector",
            name = "enabled",
            havingValue = "true"
    )
    OutboundClient outboundClient(ConnectorProperties properties) {
        return new DefaultOutboundClient(properties.timeout());
    }
}
~~~

Các type `OutboundClient`, `DefaultOutboundClient` và `ConnectorProperties` ở ví dụ phải có implementation của thư viện. Đoạn này minh họa quan hệ giữa **metadata registration, conditional properties và bean creation**, không phải một project Java hoàn chỉnh.

Một starter chỉ có `EnableAutoConfiguration` entry cũ trong `spring.factories` có thể không còn được Spring Boot 3 phát hiện theo đường cũ. Dù class vẫn nằm trong JAR, auto-config có thể không được import. Nâng dependency trên ứng dụng không tự cập nhật file metadata **bên trong JAR starter**.

### 9.3. Metadata không tự sửa mọi thứ

Starter cũ còn có thể:
- Import `javax.servlet` hoặc `javax.validation` thay vì `jakarta.*`.
- Dùng Spring APIs đã đổi signature/behavior.
- Dùng property prefix hoặc type binding cũ.
- Có conditional class names không còn tồn tại.
- Tạo bean conflict với framework mới.
- Yêu cầu JDK baseline hoặc transitive dependency khác.

Cần nâng và test **toàn bộ starter**, không chỉ file `AutoConfiguration.imports`.

## 10. Bean override, ambiguity và dependency injection

Các lỗi thường gặp sau migration:

~~~text
NoSuchBeanDefinitionException
NoUniqueBeanDefinitionException
BeanDefinitionOverrideException
UnsatisfiedDependencyException
BeanCreationException
~~~

Có thể do bean biến mất, thêm implementation trùng type, đổi bean name, một condition không match hoặc dependency cycle xuất hiện.

Ví dụ, `spring.main.allow-bean-definition-overriding=true` ở một Spring Boot release phù hợp có thể cho phép một số bean definition cùng tên bị ghi đè. **Không nên bật flag đó như cách chữa chung**: kết quả có thể khiến implementation quan trọng bị thay thế mà test không phát hiện.

Thay vào đó:
1. Xác định bean name/type và stack trace root cause.
2. Xem configuration class nào đăng ký bean.
3. Kiểm tra auto-config report matched/unmatched.
4. Kiểm tra dependency starter và version.
5. Kiểm tra `@Primary`, `@Qualifier` và custom bean definition.
6. Chốt implementation mong muốn, rồi viết test bean graph.

Không loại một auto-configuration rộng nếu chưa hiểu nó còn tạo transaction, health, metrics hoặc converter beans nào.

## 11. Chẩn đoán với condition evaluation report và Actuator

Spring Boot có thể cung cấp **condition evaluation report**. Một cách xem khi chạy thử:

~~~bash
java -jar app.jar --debug
~~~

Không bật debug lâu dài ở production nếu có nguy cơ làm tăng log hoặc lộ thông tin vận hành.

Các endpoint Actuator, khi dependency có mặt và được expose an toàn, có thể hỗ trợ:

| Endpoint | Mục đích | Rủi ro |
|---|---|---|
| `conditions` | Xem auto-config match/miss | Lộ class/bean graph |
| `beans` | Danh sách bean hiện có | Lộ cấu trúc ứng dụng |
| `configprops` | Thông tin binding config properties | Có thể lộ values nhạy cảm |
| `env` | Property sources và values | Cần bảo vệ/sanitize nghiêm ngặt |
| `health` | Readiness/liveness/health | UP chưa chứng minh business config đúng |
| `metrics` | Theo dõi behavior/latency | Cần kiểm soát labels và access |

Ví dụ URL `/actuator/conditions` chỉ có hiệu lực khi Actuator được cài và endpoint được bật/expose theo đúng framework version.

### 11.1. Phân biệt ba loại lỗi

**Property không bind:** kiểm tra tên/kiểu/source/constructor/validation.

**Auto-config không match:** kiểm tra `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` và metadata registration.

**Bean được tạo nhưng behavior sai:** kiểm tra default, client/provider config, runtime/JDK, network, database và logic nghiệp vụ.

Báo cáo conditions không thể thay thế integration tests; nó chỉ giúp giải thích một tầng của việc dựng application context.

## 12. Kiểm thử configuration binding

Spring Boot hỗ trợ `ApplicationContextRunner` để kiểm tra context nhỏ trong starter và configuration tests.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class ConnectorPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfig.class);

    @Test
    void bindsTimeoutAndUrl() {
        runner.withPropertyValues(
                "acme.connector.enabled=true",
                "acme.connector.timeout=5s",
                "acme.connector.base-url=https://api.internal"
        ).run(context -> {
            ConnectorProperties props =
                    context.getBean(ConnectorProperties.class);

            assertThat(props.enabled()).isTrue();
            assertThat(props.timeout()).hasSeconds(5);
            assertThat(props.baseUrl())
                    .isEqualTo("https://api.internal");
        });
    }

    @EnableConfigurationProperties(ConnectorProperties.class)
    static class TestConfig {}
}
~~~

Test này dùng `ConnectorProperties` record ở mục trước. Cần JUnit, AssertJ và Spring Boot Test dependencies tương thích. Nó minh họa **xác nhận giá trị thực đã bind**, không chỉ đọc YAML.

### 12.1. Kiểm thử điều kiện có/không có bean

Ví dụ cho `OutboundAutoConfiguration`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class OutboundAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withConfiguration(
                    AutoConfigurations.of(OutboundAutoConfiguration.class)
                );

    @Test
    void doesNotCreateClientWhenDisabled() {
        runner.withPropertyValues("acme.connector.enabled=false")
              .run(ctx ->
                  assertThat(ctx).doesNotHaveBean(OutboundClient.class)
              );
    }

    @Test
    void createsClientWhenEnabled() {
        runner.withPropertyValues(
                    "acme.connector.enabled=true",
                    "acme.connector.timeout=500ms"
              )
              .run(ctx ->
                  assertThat(ctx).hasSingleBean(OutboundClient.class)
              );
    }
}
~~~

Đây là **test outline cho starter minh họa**; cần implementation và dependencies thật để chạy. Ngoài test isolated context, phải có integration tests kiểm tra client kết nối đúng endpoint, timeout thật và error/retry behavior.

### 12.2. Test missing/invalid values

Bổ sung các case:
- Thiếu required URL/credential.
- Duration âm hoặc zero khi không được phép.
- Giá trị enum không hợp lệ.
- Cấu hình timeout chỉ có đơn vị số.
- Property key bị gõ sai.
- Key cũ và key mới cùng tồn tại với giá trị khác.
- Environment variable ghi đè profile YAML.
- Feature disabled không khởi tạo network client.

Với config quan trọng, test nên chứng minh **fail-fast hoặc fallback được phê duyệt**, không chỉ “context loads”.

## 13. Cấu hình bảo mật có thể thay đổi cùng framework

Spring Security hoặc security integration của framework có thể thay API và default khi nâng major version. Ví dụ:
- Cách khai báo `SecurityFilterChain` và matcher APIs.
- Servlet filter chuyển từ `javax.servlet` sang `jakarta.servlet` ở stack Jakarta.
- OAuth2 resource server/JWT validation.
- CSRF, CORS, session/cookie policy.
- Actuator security defaults và management port.
- Role mapping/authorization annotations.

Không được coi một cấu hình mới là an toàn chỉ vì startup thành công. Lập contract cụ thể, ví dụ:
- `GET /public/health` được anonymous truy cập.
- `GET /orders/{id}` yêu cầu authentication và kiểm quyền trên order.
- `POST /admin/reindex` chỉ cho admin.
- `/actuator/env` và `/actuator/configprops` không public ra Internet.

Chạy cả **positive và negative tests** trên framework/JDK đích. Không dùng workaround như disable security filter, allow-all CORS, ignore certificate validation hoặc expose all Actuator endpoints trong production để “làm migration pass”.

## 14. Web server, HTTP defaults và proxy

Nâng embedded Tomcat/Jetty/Undertow/Netty có thể làm thay:
- Connection/read/write timeouts.
- Max request headers/body size.
- HTTP/2, keep-alive và compression.
- Forwarded headers/reverse proxy handling.
- Context path, route matching, error mapping.
- TLS default cipher/protocols.
- Session cookie, SameSite và servlet lifecycle.

Một property đã đổi tên không chỉ tác động ứng dụng mà còn có thể tương tác với gateway:

~~~text
Client
  |
  v
Ingress / API gateway
  |   TLS, header/body limit, timeout
  v
Load balancer
  |   keep-alive, connection pooling
  v
Tomcat / Netty
  |   header limit, request decoding
  v
Spring filters/controllers
~~~

Nếu gateway từ chối request vì header quá lớn, tăng limit ở Tomcat không sửa được. Nếu framework không còn bind key limit cũ, Tomcat có thể lấy default khác dù gateway cho qua. Vì vậy test cần kiểm tra **đúng lớp đang từ chối** và so sánh status/body/log ở mỗi hop.

## 15. Persistence, connection pool và ORM

Framework migration có thể kéo theo nâng Hibernate ORM, Jakarta Persistence, JDBC drivers và connection pool. Property names và behavior có thể thay:
- DataSource discovery và bean selection.
- HikariCP maximum/minimum pool, timeout/idle.
- Transaction manager, propagation và exception translation.
- ORM dialect, naming strategy và SQL generated.
- Schema generation/validation.
- Entity scanning, converters, listeners, bytecode enhancement.
- `javax.persistence.*` -> `jakarta.persistence.*` trong Jakarta stack.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://db.internal:5432/orders"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 20
      connection-timeout: 5s
~~~

Đây là cấu hình minh họa trong Spring Boot stack dùng HikariCP; phải xác minh key/value support theo version thực tế. Đừng log password hoặc đưa secret thật vào repository.

### 15.1. DB health không chứng minh migration đúng

Ứng dụng có thể health UP nhưng:
- Đang kết nối database test do env override.
- Dùng pool/default khác.
- Thay SQL dialect khiến câu truy vấn hiếm bị lỗi.
- Dùng schema auto-generation ngoài dự kiến.
- Thay transaction boundaries gây data inconsistency.

Cần test transaction, integration, DB identity và query semantics. Không lấy `hibernate.hbm2ddl.auto=update` làm kế hoạch schema migration production nếu chưa có quy trình thay đổi dữ liệu được review.

## 16. Observability và management configuration

Nâng framework có thể thay:
- Actuator endpoints và exposure.
- Micrometer metrics names/tags.
- Tracing bridge, propagation và sampling.
- Health/readiness probe behavior.
- Exporter credentials, batching, buffering.
- Logging format/correlation IDs.

Ví dụ migration Spring Boot 2 sang 3 thường kéo theo cập nhật observability integration; **không chỉ đổi tên một key tracing** mà phải kiểm tra end-to-end spans và dashboards.

Một hệ thống v2 có thể chạy đúng nhưng metrics không còn được thu, gây khó phát hiện regression. Kiểm tra metric names, latency histograms, service/operation labels, trace context và masking PII/secret.

## 17. Quarkus, Micronaut và Jakarta application servers

Nguyên tắc “kiểm kê property → xác minh bean graph → test runtime” áp dụng rộng, nhưng từng framework có cơ chế khác nhau.

### 17.1. Quarkus: build-time và runtime configuration

Quarkus phân loại một số cấu hình thành build-time hoặc runtime theo extension và release. Với native image/AOT, một phần cấu hình có thể được cố định khi build.

Khi migration:
- Đọc config guide của Quarkus version đích.
- Phân biệt key build-time và runtime.
- Không giả định thay env lúc startup sẽ cập nhật mọi thuộc tính.
- Rebuild image khi những key build-time thay đổi.
- Kiểm tra extension version, profile và config precedence.
- Test riêng JVM mode và native mode nếu dùng.

Không áp nguyên `@ConditionalOnClass` hoặc `AutoConfiguration.imports` của Spring Boot sang Quarkus.

### 17.2. Micronaut: compile-time bean metadata

Micronaut sử dụng annotation processing/compile-time metadata cho nhiều hoạt động dependency injection. Nâng JDK/framework có thể yêu cầu nâng annotation processor hoặc tái tạo metadata.

Kiểm tra:
- Micronaut runtime/processor/plugin versions.
- Config prefix, conversion và validation.
- `@Requires` conditions và environments.
- Generated bean definitions sau clean build.
- Runtime/JDK target và native/AOT mode.
- Behavior của HTTP clients, security, DB và metrics.

### 17.3. Jakarta EE application server

Với Tomcat, Jetty, WildFly, Payara, Open Liberty và những runtime tương tự:
- Đối chiếu Java EE/Jakarta EE namespace.
- Kiểm tra `web.xml`, `persistence.xml` và deployment descriptors.
- Xem JNDI DataSource/JMS bindings.
- Kiểm tra CDI bean discovery và provider integration.
- Xem class loader/module isolation, security realms và TLS.
- Rà config server do operator quản lý ngoài WAR/EAR.

Chuyển source sang `jakarta.*` không tự thay resource mapping và app server configuration ở production.

## 18. Container, Kubernetes và cấu hình vận hành

Một YAML trong repository có thể bị ghi đè bởi deployment template hoặc environment.

Ví dụ Deployment minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: orders
          image: registry.example/orders:PINNED_VERSION
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: ACME_CONNECTOR_TIMEOUT
              value: "5s"
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-db
                  key: password
~~~

Đây không phải manifest production hoàn chỉnh; cần resources, probes, securityContext, service account, image digest/policy và network controls theo tiêu chuẩn triển khai.

### 18.1. Cấu hình và binary phải rollout đồng bộ

Trong rolling deployment, v1 và v2 có thể đọc hai key khác nhau. Nếu ConfigMap/Secret được cập nhật trước binary:
- v1 có thể không hiểu key mới.
- v2 có thể không còn đọc key cũ.
- Process đã chạy có thể không cập nhật biến môi trường.
- Rollback về v1 có thể dùng config không còn phù hợp.

Một hướng an toàn:
1. Thêm key mới trong giai đoạn tương thích.
2. Cho v2 tạm đọc cả old/new key khi thật sự cần, với priority rõ.
3. Chuyển Helm/CI/Secret/config service sang key mới.
4. Canary và kiểm tra effective config.
5. Chỉ xóa key cũ sau khi không còn v1 trong support window.

Không để một key giữ **hai semantics khác nhau** giữa v1 và v2; khi đó phải dùng key/version riêng.

### 18.2. Ma trận môi trường

| Môi trường | JDK | Framework | Nguồn config | Cần xác minh |
|---|---|---|---|---|
| Local | Developer JDK | Target | YAML/env | Binding, unit tests |
| CI | Pinned test JDK | Target | Test properties | Conditions, validation |
| Integration | Runtime target | Target | Containers/secrets test | DB, HTTP, broker |
| Staging | Prod-like image | Target | Helm/config service | Canary, probes, auth |
| Production v1 | Old JDK | Old framework | Old config | Baseline |
| Production v2 | New JDK | New framework | New config | Compatibility, rollback |

Tránh chỉ chạy các test với `application-test.yml` nếu production còn có properties từ sources khác.

## 19. Migration thực hành: cấu hình client cũ sang mới

Giả sử code cũ đọc:

~~~yaml
acme:
  connector:
    enabled: true
    timeoutMillis: 5000
    endpoint: "https://legacy.internal"
~~~

Code cũ:

~~~java
@Value("${acme.connector.timeoutMillis:5000}")
private int timeoutMillis;
~~~

Phiên bản mới muốn dùng `Duration` và tên key rõ ràng:

~~~yaml
acme:
  connector:
    enabled: true
    timeout: 5s
    base-url: "https://legacy.internal"
~~~

Checklist hành vi của thay đổi này:
- 5000 milliseconds có đúng bằng 5 giây với client library mới không?
- Default khi property thiếu có còn giống trước không?
- Source env/Helm nào vẫn set `timeoutMillis`?
- Nếu cả hai key xuất hiện, key nào được ưu tiên?
- `enabled=false` có ngăn client bean và side effects không?
- Khi quay về v1, cấu hình cũ còn có hiệu lực không?

**Đừng giữ alias cũ vô thời hạn.** Một bridge config có thể hữu ích trong coexistence window, nhưng phải có owner, priority rule, warning và điều kiện loại bỏ.

## 20. Bảng chẩn đoán lỗi

| Triệu chứng | Tầng nghi ngờ | Điều cần kiểm tra |
|---|---|---|
| Failed to bind properties | Key/type/constructor/validation | Root cause và effective values |
| Không có lỗi nhưng property không hiệu lực | Renamed/removed key hoặc precedence | Runtime config report, release notes |
| NoSuchBeanDefinitionException | Auto-config không match/register | Conditions, starter, imports metadata |
| NoUniqueBeanDefinitionException | Nhiều bean cùng type | Qualifier, Primary, dependencies |
| BeanDefinitionOverrideException | Bean name trùng | Owner và bean graph; không bật override mù |
| Server kết nối DB sai | Profile/env/secret precedence | JDBC URL source và DB identity |
| Actuator endpoint mất | Exposure/security/management config | Dependency và access policy |
| Metrics/tracing biến mất | Observability plugin/properties | Exporter, registry và log |
| Local pass, Kubernetes fail | Env naming, mounts, image, profiles | Rendered deployment manifest |
| HTTP 431 sau upgrade | Header limit gateway/container | Từng lớp proxy và app server |
| Bean validation không chạy | Jakarta provider/annotation mismatch | Invalid input integration test |
| Quarkus native không nhận env mới | Build-time config fixed | Build-time/runtime classification |
| JDK mới TLS fail | Truststore/provider/cipher changes | TLS handshake và JDK release |
| Test xanh, prod sai default | Test property source override | Prod-like integration tests |
| Startup UP nhưng chức năng tắt | Optional bean không được tạo | Bean graph và business-level tests |

Giải lỗi đúng tầng. `--add-opens` không sửa property key sai; bean overriding không sửa missing dependency; tăng JVM memory không sửa timeout/condition binding.

## 21. Chiến lược kiểm thử hồi quy

Một migration cấu hình cần nhiều lớp bằng chứng:

**Static inventory**
- Danh sách key deprecated/removed/renamed.
- Dependency starter versions.
- JVM args, Docker/Helm/CI overrides.
- Cấu hình Jakarta/XML/provider.

**Binding tests**
- Missing/invalid/valid value.
- Duration/DataSize conversion.
- Environment precedence.
- Profile activation.
- Unknown key/alias behavior.

**Auto-configuration tests**
- Bean được tạo khi property bật.
- Bean không được tạo khi property tắt.
- Khi dependency vắng mặt, điều kiện tương ứng không match.
- Custom bean được ưu tiên theo đúng chính sách.
- Không có duplicate/ambiguous beans.

**Integration tests**
- HTTP routes/status/headers.
- TLS/authz, DB transactions.
- Messaging retries và broker integration.
- Health/readiness/metrics/tracing.
- Application startup/shutdown dưới JDK/image đích.

**Rollout tests**
- V1/v2 cùng chạy với config chuyển tiếp.
- Canary và ngưỡng rollback.
- V1 đọc được dữ liệu do v2 ghi trong support window nếu đó là yêu cầu.
- Xóa alias/property cũ chỉ sau khi toàn bộ consumer chuyển đổi.

### 21.1. Một test matrix nhỏ

| Trường hợp | Input | Expected |
|---|---|---|
| Thiếu key optional | No `timeout` | Default được phê duyệt |
| Value hợp lệ | `5s` | 5 giây |
| Giá trị cùng nghĩa | `5000ms` | 5 giây |
| Value invalid | `abc` | Fail fast |
| Env override | `ACME_CONNECTOR_TIMEOUT=10s` | Source được áp dụng đúng |
| Feature disabled | `enabled=false` | Không tạo client hoặc side effect |
| Key cũ | `timeoutMillis` | Warning/alias/fail theo policy |
| Old/new conflict | Hai values khác | Xử lý conflict theo contract |
| Missing class | Không có client library | Auto-config không tạo bean |
| Prod profile | Profile `prod` active | Chỉ đúng config sources được nạp |

Với config liên quan bảo mật, nên có **negative tests**: request trái quyền phải bị từ chối, admin endpoint không public và invalid secret/config không bị fallback vào chế độ không bảo vệ.

## 22. Lộ trình triển khai từng bước

### Bước 1: Chốt phiên bản mục tiêu

Ghi rõ JDK vendor/build, framework version, starter, ORM, web server, validation/security providers, container image và support window. Đọc migration guide **đúng release**.

### Bước 2: Chụp baseline

Ghi cấu hình hiệu lực (đã che secrets), active profiles, matched/unmatched conditions, bean graph, startup warnings, behavior/timeouts/health và application artifact hash của phiên bản cũ.

### Bước 3: Phân loại thay đổi

Tách thành:
- Renamed/removed config.
- Type/default/semantic changes.
- Profile/property source precedence.
- Auto-config condition/registration changes.
- Starter/dependency/Jakarta changes.
- JDK behavior changes.

### Bước 4: Chuyển nguồn cấu hình và code

Sửa YAML/properties/Helm/CI/config service, `@ConfigurationProperties`, validation và custom starters. Nếu dùng migrator/OpenRewrite/IDE, ghi rõ phạm vi và sửa các case không được hỗ trợ.

### Bước 5: Xác minh bean graph và effective config

Dùng context tests, condition evaluation report và debugging an toàn. Khi có bean thiếu/trùng, tìm đúng configuration class/condition thay vì tắt auto-config hàng loạt.

### Bước 6: Integration test trên runtime đích

Test database, HTTP, TLS, authz, validation, messaging, metrics, scheduling và operations bằng JDK/framework/container image dự kiến triển khai.

### Bước 7: Canary và rollback

Triển khai một phần traffic, quan sát business metrics và error rates, bảo đảm v1/v2 có config compatibility. Nếu config mới làm thay data state mà v1 không hiểu, phải có kế hoạch rollback dữ liệu hoặc đặt feature gate trước khi mở chức năng.

### Bước 8: Loại cấu hình cũ

Khi không còn consumer dùng config cũ, xóa alias/migrator, starter version legacy, flags workaround và tài liệu lỗi thời. Duy trì regression test và config inventory cho các đợt nâng tiếp theo.

## 23. Những sai lầm thường gặp

- **Build xanh nghĩa là cấu hình đúng:** property cũ có thể bị bỏ qua.
- **Cùng YAML nghĩa là cùng behavior:** precedence, profile và defaults có thể đổi.
- **Không khai báo property nghĩa là feature tắt:** auto-config có thể bật theo classpath.
- **Đổi key ở một file là xong:** Helm, Secret, CI và config service có thể giữ key cũ.
- **Relaxed binding nhận mọi biến thể:** environment mapping có quy tắc cụ thể.
- **Migrator sửa mọi vấn đề:** chỉ hỗ trợ các thay đổi đã được định nghĩa.
- **Binding đúng thì bean tồn tại:** auto-config còn phụ thuộc conditions.
- **Thêm starter chỉ thêm JAR:** starter có thể kích hoạt bean và side effects.
- **Bật bean overriding chữa mọi lỗi:** có thể che implementation conflict.
- **Actuator env/beans có thể public để debug:** cần access control và sanitization.
- **Profile prod là security boundary:** profile không thay authentication/authorization.
- **Nâng JDK đồng nghĩa đổi javax thành jakarta:** đó là một migration framework/API riêng.
- **Quarkus/Micronaut config như Spring Boot:** build-time/compile-time mechanisms khác.
- **Native image đọc mọi env mới ở runtime:** có thể có config cố định khi build.
- **Health UP chứng minh application đúng:** không kiểm tra mọi business capability.
- **Rollback binary đủ để rollback:** DB, config và event state có thể đã thay.

## 24. Checklist hoàn tất migration cấu hình

- [ ] Đã xác định JDK/framework/starter/provider/container versions thực tế.
- [ ] Đã đọc migration guide và property appendix của đúng release.
- [ ] Đã liệt kê config sources: files, env, JVM args, remote config, Helm và Secrets.
- [ ] Đã phân loại renamed/removed/split/type/default/semantic changes.
- [ ] Đã biết effective values, profile activation và precedence.
- [ ] Required config có fail-fast/validation và default được phê duyệt.
- [ ] `@ConfigurationProperties` bind đúng type/unit và bean registration.
- [ ] Jakarta Validation annotations/provider phù hợp nếu có.
- [ ] Auto-configuration metadata và conditional beans được test.
- [ ] Không có missing/duplicate bean hoặc override ngoài dự kiến.
- [ ] Security/Actuator/TLS/authz được xác minh bằng negative tests.
- [ ] DB/ORM/transactions/pool settings giữ behavior mong muốn.
- [ ] HTTP limits, proxy interaction và session behavior đã test.
- [ ] Health/metrics/traces không biến mất hoặc expose sai.
- [ ] Các môi trường local/CI/staging/production-like đã được đối chiếu.
- [ ] Có canary, compatibility window và rollback plan khi v1/v2 cùng chạy.
- [ ] Không log secret hoặc public endpoint `env`/`configprops`.
- [ ] Migrator, aliases và workaround có owner/điều kiện loại bỏ.

## 25. Tài liệu để đối chiếu

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html).
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html).
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html).
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide).
- [Quarkus Configuration Reference](https://quarkus.io/guides/config-reference).
- [Micronaut Documentation](https://docs.micronaut.io/latest/guide/).
- [Jakarta EE Specifications](https://jakarta.ee/specifications/).

Tài liệu “current/latest” thay đổi theo thời gian. Khi migration, ưu tiên tài liệu **theo đúng version đã pin**, cùng kết quả kiểm thử trên artifact và runtime của dự án, thay vì suy từ ví dụ cho một phiên bản khác.

## 26. Kết luận

**Thay đổi cấu hình và cơ chế tự cấu hình là migration hợp đồng vận hành, không chỉ là thay tên YAML key.** Một ứng dụng Java có thể khởi động và biên dịch bình thường nhưng thay đổi timeout, database, security behavior, bean graph hoặc observability do framework, starter, JDK và deployment sources khác trước.

Lộ trình an toàn là **chụp baseline → kiểm kê config sources và dependency → phân loại property/default/conditional changes → chuyển config và starter metadata → kiểm chứng binding/bean graph → integration test trên JDK/framework đích → canary/rollback có kiểm soát**. Mỗi cấu hình quan trọng cần trả lời được: **ai cung cấp giá trị, thành phần nào đọc nó, điều kiện nào kích hoạt và hành vi nào phải được giữ**. Khi những hợp đồng đó được kiểm thử và tài liệu hóa, hệ thống có thể nâng Java và framework từng bước mà không để các mặc định hoặc auto-configuration trở thành rủi ro ẩn.
