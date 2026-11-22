# Giới hạn thay đổi thuộc tính ảnh hưởng đến sự hiện diện của bean sau AOT

## 1. Vấn đề: vì sao đổi property lúc chạy mà bean không xuất hiện hoặc không biến mất?

Trong ứng dụng Spring Boot thông thường, container đọc classpath và Environment khi khởi động. Các điều kiện như `@ConditionalOnProperty`, `@Profile`, `@ConditionalOnClass` và `@ConditionalOnBean` được đánh giá trong quá trình tạo ApplicationContext. Vì vậy, hai lần khởi động với property khác nhau có thể tạo ra hai tập bean khác nhau.

Spring AOT thay đổi thời điểm của quyết định này. Trong giai đoạn build, Spring phân tích ApplicationContext, xử lý configuration và đánh giá các điều kiện để sinh mã khởi tạo bean definitions. Khi chạy ứng dụng đã AOT, mã được sinh sẽ khôi phục cấu trúc bean đã quyết định ở build time.

**Hệ quả:** property ảnh hưởng đến việc một bean có được đăng ký hay không phải có giá trị phù hợp ngay khi chạy AOT. Nếu bean được đưa vào bean graph lúc build, đổi property sang false khi chạy không tự xóa bean. Nếu bean bị loại lúc build, đổi property sang true khi chạy cũng không tự tạo bean mới.

Điều này áp dụng cho native image và cả ứng dụng JVM sử dụng mã AOT đã sinh. Nó không có nghĩa mọi property đều bị cố định. Các property chỉ cấu hình một bean đã được đăng ký vẫn có thể nhận giá trị từ Environment lúc ứng dụng chạy.

Bài này dùng Spring Boot 3.3.x, Spring Framework 6.1 và Java 17+ để phân biệt hai nhóm property, cấu hình Maven/Gradle AOT, kiểm thử hành vi trên JVM thường và chứng minh giới hạn bằng hai lần build AOT.

## 2. AOT quyết định điều gì ở build time?

AOT (Ahead-of-Time) phân tích ApplicationContext trong quá trình build và sinh các tài nguyên giúp khởi động ứng dụng với ít công việc động hơn. Spring Boot dùng bước này bắt buộc khi chuyển Spring ApplicationContext thành GraalVM Native Image; cũng có thể chạy mã AOT đã sinh trên JVM để kiểm tra trước khi tạo native executable.

Trong AOT processing, Spring xử lý cấu hình và tạo bean definitions cần thiết. Các condition được đánh giá trong môi trường build. Những bean definitions không thỏa điều kiện bị loại khỏi cấu trúc được sinh.

Có thể hình dung:

```text
Build classpath + build Environment
              |
              v
       Parse configuration
              |
              v
    Evaluate @Conditional rules
              |
       +------+------+
       |             |
    condition      condition
      match        no-match
       |             |
       v             v
 keep bean       discard bean
 definition      definition
       |             |
       +------+------+
              |
              v
     Generate AOT code
              |
              v
      Package application
              |
              v
       Run AOT artifact
              |
              v
   Restore the build-time bean graph
```

Spring Framework mô tả classpath là cố định tại build time và các bean definitions không thể thay đổi tùy ý lúc runtime. Những property của Environment ảnh hưởng đến sự hiện diện của bean qua condition chỉ được xét ở build time. Các profile cũng chịu giới hạn này vì `@Profile` được triển khai bằng condition.

### 2.1. Các quyết định thường bị cố định

| Cơ chế | Ví dụ | Ảnh hưởng trong AOT |
| --- | --- | --- |
| `@ConditionalOnProperty` | `feature.enabled=true` | Quyết định bean/configuration có được đưa vào bean graph |
| `@Profile` | `@Profile("production")` | Profile cần được chọn khi chạy AOT |
| `@ConditionalOnClass` | Một SDK class có trên classpath | Classpath phải được xác định khi build |
| `@ConditionalOnBean` | Có bean prerequisite | Quyết định dựa trên bean definitions lúc AOT |
| `@ConditionalOnMissingBean` | Chưa có bean do ứng dụng cung cấp | Back-off được quyết định khi AOT |
| Custom `Condition` đọc Environment | Kiểm tra property hoặc profile | Kết quả condition được tính ở build time |

Không chỉ `@ConditionalOnProperty` bị ảnh hưởng. Bất kỳ condition nào quyết định sự hiện diện của bean đều cần được xem xét. Nếu custom condition đọc `Environment` rồi trả về true/false, giá trị nó đọc cũng thuộc môi trường AOT.

### 2.2. Ví dụ với @ConditionalOnProperty

```java
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.feature",
            name = "enabled",
            havingValue = "true")
    FeatureClient featureClient() {
        return new FeatureClient();
    }
}
```

Nếu `acme.feature.enabled=true` trong lúc AOT, `FeatureClient` được giữ lại. Khi ứng dụng AOT chạy với:

```bash
java -Dspring.aot.enabled=true -jar app.jar --acme.feature.enabled=false
```

bean vẫn hiện diện vì quyết định đăng ký đã được tạo ở build time.

Nếu AOT chạy với `acme.feature.enabled=false`, bean bị loại. Đổi thành true ở runtime cũng không thêm được bean definition mà mã AOT đã không sinh.

### 2.3. Profile cũng là condition

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@Profile("production")
class ProductionFeatureConfiguration {

    @Bean
    ProductionFeature productionFeature() {
        return new ProductionFeature();
    }
}
```

Nếu profile `production` được bật trong quá trình AOT, cấu hình production được đưa vào bean graph. Khi chạy AOT, profile này được giữ theo quyết định đã tạo. Nếu cần các biến thể profile có bean graph khác nhau, hãy tạo artifact AOT riêng cho từng biến thể.

Không nhầm việc chọn profile với việc đọc property thông thường. Một profile có thể chứa cả property cấu hình bean và property chỉ thay đổi giá trị của bean đã tồn tại. Phần property thứ hai vẫn có thể khác giữa các môi trường runtime.

## 3. Phân biệt property quyết định bean presence và property cấu hình bean

Đây là phân biệt quan trọng nhất khi thiết kế ứng dụng AOT.

### 3.1. Property ảnh hưởng đến sự hiện diện của bean

Ví dụ:

```properties
acme.feature.enabled=true
```

Property này được dùng trong `@ConditionalOnProperty`. Nó quyết định có đăng ký `FeatureClient` hay không. Vì vậy giá trị cần được đặt trong môi trường dùng để AOT processing.

Các dạng tương tự:

- `acme.kafka.enabled` quyết định có tạo Kafka integration beans không.
- `acme.storage.type` quyết định chọn một configuration theo điều kiện.
- `spring.profiles.active` quyết định những cấu hình `@Profile` nào được xét.
- Property do custom `Condition` đọc để đăng ký một bean tùy chọn.

Các giá trị này phải phù hợp với deployment variant mà artifact được build để phục vụ.

### 3.2. Property chỉ cấu hình một bean đã tồn tại

Ví dụ:

```properties
acme.feature.endpoint=https://api.example.test
acme.feature.timeout=3s
acme.feature.max-connections=20
```

Nếu `FeatureClient` luôn được đăng ký và các property trên chỉ được bind vào `@ConfigurationProperties` để cấu hình endpoint, timeout và connection pool, các giá trị có thể được cung cấp bởi Environment khi ứng dụng chạy.

Ví dụ:

```java
@ConfigurationProperties("acme.feature")
public record FeatureProperties(
        URI endpoint,
        Duration timeout,
        int maxConnections) {
}
```

`@ConfigurationProperties` mô tả dữ liệu cấu hình cho bean. Nếu các trường này không tham gia condition quyết định bean presence, chúng không bị cố định theo cách của `@ConditionalOnProperty`.

Cần phân biệt “runtime configuration” với “hot reload”. Giá trị có thể khác giữa các lần triển khai/khởi động. Việc sửa Environment sau khi ứng dụng đã chạy không tự động làm mọi `@ConfigurationProperties` bean bind lại; muốn refresh nóng cần cơ chế refresh/rebinding riêng.

### 3.3. Bảng quyết định

| Cách dùng property | Ví dụ | Có thể thay đổi giữa các lần chạy AOT? |
| --- | --- | :---: |
| Làm đầu vào cho `@ConditionalOnProperty` | `feature.enabled` | Không làm đổi bean presence của artifact đã AOT |
| Được đọc bởi custom `Condition` | `feature.mode` trong condition | Không làm đổi bean presence |
| Chọn `@Profile` có configuration beans khác nhau | `production` / `development` | Profile ảnh hưởng bean graph phải chọn lúc build |
| Bind vào field của bean đã có | `feature.timeout` | Có |
| Truyền vào constructor để cấu hình bean đã được giữ lại | `feature.endpoint` | Có |
| Đọc trong method để chọn hành vi của bean luôn tồn tại | `feature.strategy` | Có, theo giá trị Environment được bind/đọc lúc runtime |
| Thêm class/dependency vào classpath sau build | SDK mới chỉ có ở deployment | Không; classpath đã được cố định |

Một property có thể vừa được bind vào `@ConfigurationProperties` vừa được dùng trong condition. Khi đó **quyết định bean presence** của property bị cố định, dù giá trị property vẫn có thể tồn tại trong Environment lúc chạy. Không được suy ra rằng mọi nơi đọc property đều bị thay thế bằng giá trị build time; điều bị cố định là kết quả quyết định cấu trúc bean.

## 4. Vì sao AOT cần bean graph ổn định?

Trong khởi động Spring thông thường, framework có thể đọc classpath, parse configuration, đánh giá condition và đăng ký bean definitions theo Environment hiện tại.

AOT làm phần lớn công việc cấu trúc này sớm hơn. Mã được sinh sẽ khôi phục trạng thái bean factory đã chuẩn bị. Nếu ứng dụng có thể thêm/xóa tùy ý bean theo property runtime, mã khởi tạo được sinh sẽ không còn mô tả đúng cấu trúc đã phân tích.

Vì vậy:

- Classpath phải đầy đủ và cố định khi build.
- Các configuration có điều kiện phải được đánh giá trong đúng build Environment.
- Bean definitions không thể tùy ý thay đổi theo profile/property runtime.
- Không dựa vào việc thêm dependency hoặc class mới sau khi native image đã được tạo.
- Custom registration cần dùng các cơ chế đăng ký bean definitions mà AOT có thể xử lý.

Spring Framework cũng lưu ý một số dạng đăng ký không thể chuyển đổi trực tiếp sang AOT, chẳng hạn bean definition dùng instance supplier là lambda/method reference hoặc singleton được đăng ký bằng `registerSingleton`. Nếu cần đăng ký bean theo cách lập trình, hãy cân nhắc `BeanDefinitionRegistry`, `BeanDefinitionRegistryPostProcessor` hoặc `ImportBeanDefinitionRegistrar` phù hợp với vòng đời AOT.

## 5. Thiết kế feature toggle phù hợp với AOT

Nếu một tính năng cần bật/tắt theo từng deployment mà không đổi bean graph, hãy để bean luôn tồn tại và đưa cờ vào logic của bean. Không dùng condition để tạo/xóa bean nếu giá trị phải linh hoạt sau build.

### 5.1. Thiết kế không phù hợp khi cần toggle runtime

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true")
AuditPublisher auditPublisher() {
    return new AuditPublisher();
}
```

Cách này phù hợp khi muốn tạo các artifact AOT khác nhau cho các deployment variant. Nó không phù hợp nếu cùng một AOT artifact cần bật/tắt bean bằng property runtime.

### 5.2. Giữ bean luôn tồn tại, thay đổi hành vi

```java
@ConfigurationProperties("acme.audit")
public record AuditProperties(
        boolean enabled,
        URI endpoint) {
}

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AuditProperties.class)
class AuditConfiguration {

    @Bean
    AuditPublisher auditPublisher(AuditProperties properties) {
        return new AuditPublisher(properties);
    }
}

final class AuditPublisher {

    private final AuditProperties properties;

    AuditPublisher(AuditProperties properties) {
        this.properties = properties;
    }

    void publish(AuditEvent event) {
        if (!this.properties.enabled()) {
            return;
        }

        // Gửi event đến endpoint đã cấu hình.
    }
}
```

Trong thiết kế này, `AuditPublisher` luôn có trong bean graph. Giá trị `enabled` được bind lúc ứng dụng chạy và quyết định hành vi của method. Khi đổi property giữa hai deployment, bean vẫn tồn tại nhưng có thể hoạt động hoặc no-op theo cấu hình.

Đây là một feature toggle ở tầng hành vi. Nếu cần loại bỏ dependency, endpoint, security integration hoặc toàn bộ bean khỏi artifact để giảm footprint, hãy tạo artifact AOT riêng thay vì mong một runtime property thay đổi bean graph.

### 5.3. Chọn giữa một artifact và nhiều artifact

| Nhu cầu | Thiết kế |
| --- | --- |
| Cùng một bean luôn tồn tại, chỉ thay endpoint/timeout/strategy | Một artifact AOT; property cấu hình đọc lúc runtime |
| Một feature luôn có bean nhưng có thể no-op theo cờ runtime | Một artifact AOT; toggle nằm trong logic bean |
| Feature cần có hoặc không có bean thực sự | Build artifact AOT riêng cho từng biến thể |
| Profile làm thay đổi tập configuration/bean | Chọn profile trong AOT build; tạo build riêng khi cần profile khác |
| Dependency/classpath thay đổi giữa deployment | Build artifact riêng với classpath tương ứng |
| Muốn ứng dụng thay đổi bean graph tự do lúc runtime | Dùng chế độ khởi động Spring thông thường, không dựa vào AOT bean graph đã sinh |

## 6. Chọn đúng Environment cho quá trình AOT

Điều kiện phải được đánh giá trong môi trường build đại diện cho deployment mà artifact sẽ phục vụ. Hãy xác định trước:

- Profile nào cần bật?
- Property nào quyết định auto-configuration có được áp dụng?
- Optional dependency nào phải có trên classpath?
- Bean nào do ứng dụng cung cấp khiến auto-configuration back-off?
- Có property nào bị đọc bởi custom `Condition` không?
- Các deployment variant có cùng bean graph hay cần artifact riêng?

Nếu build AOT trong môi trường local với property mặc định, nhưng production cần một condition khác, artifact có thể chứa bean graph sai cho production. Đừng trông đợi environment variables hoặc config server lúc runtime có thể bổ sung những bean đã bị loại ở build time.

### 6.1. Maven: cấu hình process-aot

Spring Boot Maven Plugin cung cấp goal `process-aot`. Ví dụ POM dưới đây truyền property feature vào ApplicationContext được tạo trong AOT processing:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>process-aot</id>
                    <phase>process-classes</phase>
                    <goals>
                        <goal>process-aot</goal>
                    </goals>
                    <configuration>
                        <arguments>
                            <argument>--acme.feature.enabled=true</argument>
                        </arguments>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

`arguments` là application arguments được dùng khi AOT processing. Có thể truyền thêm các property build-time khác theo contract của ứng dụng.

Maven plugin cũng hỗ trợ `profiles` để chọn Spring profiles cho AOT processing. Ví dụ cấu hình profile:

```xml
<configuration>
    <profiles>production,cloud</profiles>
</configuration>
```

Khi dùng `spring-boot-starter-parent`, Spring Boot cung cấp Maven profile `native` để tự động cấu hình execution `process-aot` khi plugin được áp dụng. Profile đó còn cấu hình các bước native build tương ứng. Nếu chỉ muốn minh họa AOT-generated initialization trên JVM, có thể cấu hình goal `process-aot` như ví dụ đầu và đóng gói JAR, không cần chạy native-image compiler.

### 6.2. Gradle: cấu hình ProcessAot

Với Gradle, truyền application arguments cho task `ProcessAot`:

```groovy
tasks.withType(
    org.springframework.boot.gradle.tasks.aot.ProcessAot
).configureEach {
    args('--acme.feature.enabled=true')
    args('--spring.profiles.active=production,cloud')
}
```

Chỉ truyền các property/profile thực sự cần cho bean graph. Các giá trị này sẽ được dùng khi condition được đánh giá trong quá trình build.

### 6.3. Tách biến thể build

Nếu ứng dụng cần một artifact có feature và một artifact không có feature, hãy tạo hai build với đầu vào AOT khác nhau:

```text
AOT build: acme.feature.enabled=true
              |
              v
      FeatureClient included
              |
              v
       Artifact variant ON

AOT build: acme.feature.enabled=false
              |
              v
      FeatureClient excluded
              |
              v
       Artifact variant OFF
```

Đặt tên/tag artifact hoặc image rõ ràng theo variant để tránh deploy nhầm. Không ghi đè hai biến thể vào cùng một đường dẫn artifact trong pipeline.

## 7. Ví dụ chạy được: chứng minh bean presence đã được cố định

Ví dụ này dùng Spring Boot 3.3.13, Java 17 và Maven. Ta tạo một bean có điều kiện, sau đó:

1. Kiểm tra behavior thông thường bằng `ApplicationContextRunner`.
2. Build AOT với property true, chạy trên JVM với property false.
3. Build AOT với property false, chạy trên JVM với property true.
4. So sánh bean presence để thấy runtime property không đảo ngược quyết định build.

### 7.1. Cấu trúc project

```text
aot-condition-lab/
├── pom.xml
└── src/
    ├── main/java/demo/aot/
    │   ├── AotConditionLabApplication.java
    │   ├── FeatureConfiguration.java
    │   └── FeatureMarker.java
    └── test/java/demo/aot/
        └── RuntimeConditionTest.java
```

### 7.2. POM

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>aot-condition-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <id>process-aot</id>
                        <phase>process-classes</phase>
                        <goals>
                            <goal>process-aot</goal>
                        </goals>
                        <configuration>
                            <arguments>
                                <argument>--acme.feature.enabled=true</argument>
                            </arguments>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Ở build đầu, AOT nhận `acme.feature.enabled=true`. Để kiểm tra biến thể OFF, thay đúng argument đó thành false, chạy lại `clean package` và dùng JAR mới.

### 7.3. Bean được đăng ký có điều kiện

File `FeatureMarker.java`:

```java
package demo.aot;

public record FeatureMarker(String source) {
}
```

File `FeatureConfiguration.java`:

```java
package demo.aot;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.feature",
            name = "enabled",
            havingValue = "true")
    FeatureMarker featureMarker() {
        return new FeatureMarker("conditional-bean");
    }
}
```

File `AotConditionLabApplication.java`:

```java
package demo.aot;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.beans.factory.ObjectProvider;

@SpringBootApplication
@Import(FeatureConfiguration.class)
public class AotConditionLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(AotConditionLabApplication.class, args);
    }

    @Bean
    CommandLineRunner reportFeaturePresence(
            ObjectProvider<FeatureMarker> featureProvider) {

        return args -> System.out.println(
                "featurePresent=" + (featureProvider.getIfAvailable() != null));
    }
}
```

`ObjectProvider` cho phép kiểm tra bean có tồn tại mà không yêu cầu bean phải có mặt. Khi feature bị loại ở build time, ứng dụng vẫn khởi động và in `featurePresent=false`.

### 7.4. Test behavior thông thường trước AOT

File `RuntimeConditionTest.java`:

```java
package demo.aot;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

class RuntimeConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(FeatureConfiguration.class);

    @Test
    void propertyTrueRegistersFeatureBean() {
        runner.withPropertyValues("acme.feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(FeatureMarker.class);
                });
    }

    @Test
    void propertyFalseDoesNotRegisterFeatureBean() {
        runner.withPropertyValues("acme.feature.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(FeatureMarker.class);
                });
    }
}
```

Hai test chứng minh trong context thông thường, cùng một configuration có thể cho kết quả khác nhau theo property của lần khởi động. Đây là behavior mong đợi trước khi AOT cố định bean graph.

Import `org.springframework.context.annotation.Import` không cần thiết trong test trên; có thể bỏ import đó nếu IDE báo unused import.

### 7.5. Chạy test JVM thông thường

Từ thư mục project:

```bash
mvn clean test
```

Kết quả mong đợi:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Dòng thống kê chi tiết có thể khác theo phiên bản Surefire, nhưng cả hai test phải pass.

### 7.6. Build AOT với feature ON

Giữ POM argument:

```xml
<argument>--acme.feature.enabled=true</argument>
```

Build JAR:

```bash
mvn clean package
```

Chạy JAR trên JVM nhưng yêu cầu dùng AOT-generated initialization:

```bash
java -Dspring.aot.enabled=true -jar target/aot-condition-lab-1.0.0.jar --acme.feature.enabled=false
```

Output kỳ vọng:

```text
featurePresent=true
```

Giá trị runtime là false, nhưng bean đã được giữ lại khi AOT processing chạy với true.

### 7.7. Build AOT với feature OFF

Sửa argument trong POM thành:

```xml
<argument>--acme.feature.enabled=false</argument>
```

Sau đó build sạch:

```bash
mvn clean package
```

Chạy với property runtime true:

```bash
java -Dspring.aot.enabled=true -jar target/aot-condition-lab-1.0.0.jar --acme.feature.enabled=true
```

Output kỳ vọng:

```text
featurePresent=false
```

Bean không được tạo dù runtime property là true, vì AOT build đã loại bean khỏi bean graph.

### 7.8. Kết quả của hai biến thể

| Giá trị lúc AOT | Giá trị lúc runtime | Bean có mặt? | Lý do |
| --- | --- | :---: | --- |
| true | true | Có | Bean được giữ ở build time |
| true | false | Có | Runtime không xóa bean đã sinh |
| false | false | Không | Bean bị loại ở build time |
| false | true | Không | Runtime không thêm bean definition đã bị loại |

Đây là phép thử quan trọng nhất của bài. Nó chạy mã AOT đã sinh trên JVM, không cần đợi native-image compiler. Khi đóng gói native image, AOT là bước bắt buộc và giới hạn bean presence tương tự vẫn áp dụng.

## 8. Kiểm thử AOT trên JVM và kiểm thử native image

Không nhất thiết phải build native image cho mọi lần kiểm thử. Nên dùng nhiều lớp:

### 8.1. Unit test thông thường

Dùng `ApplicationContextRunner` để kiểm tra condition ở chế độ runtime tiêu chuẩn. Các test này nhanh, dễ chạy trong IDE và xác minh feature ON/OFF theo property.

### 8.2. AOT processing test

Chạy Maven goal `process-aot` hoặc Gradle task `ProcessAot`. Bước này xác nhận ứng dụng có thể được phân tích và mã khởi tạo được sinh với build Environment dự kiến.

### 8.3. Chạy mã AOT trên JVM

Sau khi JAR chứa mã AOT, chạy:

```bash
java -Dspring.aot.enabled=true -jar target/aot-condition-lab-1.0.0.jar
```

Đây là cách kiểm tra generated initialization mà không phải chờ compile native image. Đảm bảo artifact thật sự đã được build với AOT; nếu không, JVM thông thường sẽ dùng luồng khởi tạo runtime.

### 8.4. Native image smoke test

Khi cần xác nhận GraalVM, build native image và chạy executable. Native image tự dùng mã AOT. Nên giữ unit/integration tests trên JVM cho phần lớn logic để giảm thời gian feedback; dành native smoke tests cho các điểm có khác biệt như reflection, resources, serialization, dynamic proxies và runtime hints.

AOT thành công chưa đồng nghĩa native image chắc chắn build được. Runtime hints cho reflection/resource/proxy và các giới hạn của native compiler là một lớp kiểm tra khác với condition property.

## 9. Những lỗi thiết kế và chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Đổi `feature.enabled=false` nhưng bean vẫn tồn tại | Bean được giữ khi AOT chạy với true | Build lại với property false |
| Đổi `feature.enabled=true` nhưng bean không xuất hiện | Bean đã bị loại khi AOT chạy với false | Build lại với property true |
| Profile runtime không nạp configuration có bean mới | Profile ảnh hưởng condition nhưng chưa được chọn lúc AOT | Đặt profile trong process-aot hoặc tạo artifact riêng |
| Local AOT chạy được nhưng production thiếu bean | Build Environment không đại diện production | Đồng bộ build-time properties/profile với deployment |
| Thêm SDK ở runtime nhưng auto-configuration không xuất hiện | Classpath đã cố định lúc build | Thêm dependency trước AOT và build lại |
| Bean luôn tồn tại dù feature tắt | Bean không được condition loại; cờ chỉ cấu hình hành vi | Xác định đây là toggle hành vi hay cần bean presence thật |
| Unit test pass nhưng AOT app khác | Unit test chạy context thông thường | Thêm AOT build/run smoke test |
| AOT build lỗi với đăng ký bean động | Registration path không được AOT hỗ trợ | Dùng BeanDefinitionRegistry/ImportBeanDefinitionRegistrar phù hợp |
| Native image thiếu class/resource | Thiếu runtime hints hoặc resource không được nhận diện | Thêm RuntimeHints và native integration test |
| Kết quả test thay đổi sau khi sửa property nhưng JAR cũ vẫn được chạy | Artifact chưa được clean/rebuild | Chạy clean package và xác nhận đúng JAR |

### 9.1. Đừng dùng condition cho một feature toggle cần đổi ở runtime

Nếu muốn cùng một artifact được triển khai ở nhiều môi trường và chỉ thay đổi việc gửi audit, gửi metrics hoặc bật một integration, cân nhắc đăng ký bean luôn tồn tại và để bean tự quyết định hành vi theo property runtime.

Chỉ dùng condition khi bean presence thực sự là quyết định kiến trúc cần cố định cho artifact, ví dụ loại adapter, loại server hoặc integration có dependency riêng.

### 9.2. Đừng coi mọi property là build-time constant

AOT không đóng băng toàn bộ `application.properties`. Property chỉ cấu hình endpoint, timeout, pool size, logging level hoặc giá trị nghiệp vụ của bean đã tồn tại vẫn có thể được bind lúc runtime.

Hãy lần theo nơi property được dùng:

- Nếu nó đi vào condition, kết quả bean presence được chốt ở build.
- Nếu nó chỉ đi vào constructor/method của bean đã có, giá trị có thể đến từ runtime Environment.
- Nếu custom code tự đọc Environment để đăng ký bean definitions, phải bảo đảm registration đó được thực hiện trong pha AOT và dùng API registry phù hợp.

## 10. Checklist trước khi phát hành ứng dụng AOT

**Bean graph và condition**

- [ ] Đã liệt kê tất cả `@ConditionalOnProperty`, `@Profile` và custom `Condition`.
- [ ] Đã tìm các condition dựa trên classpath, bean presence và property.
- [ ] Đã xác định giá trị build-time cho mọi property ảnh hưởng bean presence.
- [ ] Đã chọn profile cần thiết khi chạy `process-aot`.
- [ ] Đã kiểm tra `@ConditionalOnMissingBean` không back-off ngoài dự kiến.
- [ ] Đã tránh kỳ vọng runtime property thêm/xóa bean sau AOT.

**Runtime configuration**

- [ ] Property chỉ cấu hình bean hiện hữu vẫn được bind từ runtime Environment.
- [ ] Không nhầm property binding với hot reload.
- [ ] Feature toggle cần linh hoạt được đặt trong logic của bean luôn tồn tại.
- [ ] Nếu bean graph khác nhau, pipeline tạo artifact AOT riêng.

**Build và verification**

- [ ] Maven/Gradle đã chạy đúng AOT task.
- [ ] Build input (arguments, profiles, system properties) được ghi lại trong pipeline.
- [ ] Đã chạy unit tests cho context runtime thông thường.
- [ ] Đã chạy AOT-generated JAR trên JVM với `spring.aot.enabled=true`.
- [ ] Đã thử ít nhất một property runtime trái ngược với giá trị AOT để xác nhận bean presence cố định.
- [ ] Đã clean trước khi build biến thể AOT khác.
- [ ] Đã chạy native smoke test khi phát hành GraalVM image.
- [ ] Runtime hints cho reflection/resource/proxy đã được kiểm tra riêng.

**Ghi nhớ:** AOT cố định cấu trúc bean theo classpath và Environment lúc build. Property điều khiển `@Conditional` và profile quyết định bean presence không thể dùng để thêm/xóa bean trong cùng artifact sau khi build. Property chỉ cấu hình bean đã tồn tại vẫn có thể thay đổi theo runtime Environment. Nếu cần thay đổi hành vi, giữ bean và dùng runtime feature flag; nếu cần thay đổi bean graph, tạo artifact AOT riêng cho từng biến thể.

## Tài liệu chính thức

- Spring Boot 3.3.13 — Ahead-of-Time Processing và goal `process-aot`, các tham số `arguments`/`profiles`: https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html
- Spring Boot 3.3 — Ahead-of-Time Processing With the JVM: https://docs.spring.io/spring-boot/3.3/reference/packaging/aot.html
- Spring Boot 3.3 — Testing GraalVM Native Images và chạy mã AOT trên JVM: https://docs.spring.io/spring-boot/3.3/how-to/native-image/testing-native-applications.html
- Spring Framework — Ahead of Time Optimizations, classpath cố định và condition/property constraints: https://docs.spring.io/spring-framework/reference/core/aot.html
