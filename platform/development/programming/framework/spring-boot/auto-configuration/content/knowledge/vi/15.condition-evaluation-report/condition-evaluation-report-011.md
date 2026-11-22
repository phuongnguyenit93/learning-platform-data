# So sánh Condition Evaluation Report trước và sau khi thay dependency, thuộc tính hoặc bean

## 1. Condition Evaluation Report trả lời câu hỏi gì?

Spring Boot dùng các condition để quyết định một cấu hình hoặc bean có được áp dụng hay không. Những annotation thường gặp gồm:

- `@ConditionalOnClass`: class cần thiết có trên classpath hay không.
- `@ConditionalOnProperty`: thuộc tính có tồn tại và có giá trị phù hợp hay không.
- `@ConditionalOnBean`: bean phù hợp đã được đăng ký hay chưa.
- `@ConditionalOnMissingBean`: đã có bean để thay thế default hay chưa.
- `@ConditionalOnSingleCandidate`: có thể xác định một ứng viên duy nhất để inject theo kiểu hay không.
- `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication`: ApplicationContext có được nhận diện là web hay không.

**Condition Evaluation Report** ghi lại kết quả đánh giá các condition trên configuration và auto-configuration, kèm lý do match hoặc không match. Đây là công cụ giúp trả lời:

1. Vì sao một auto-configuration được áp dụng hoặc bị bỏ qua?
2. Vì sao một phương thức `@Bean` được đăng ký hoặc không được đăng ký?
3. Khi thay dependency, property hoặc bean, condition nào đổi trạng thái?
4. Một thay đổi có làm mất bean phụ thuộc hoặc kích hoạt fallback khác không?

Report là **ảnh chụp tại thời điểm khởi động** của một ApplicationContext. Nó không phải lịch sử thay đổi và không tự tạo bản diff giữa hai lần chạy. Muốn so sánh trước/sau, ta phải lưu hai report riêng rồi đối chiếu các entry liên quan.

## 2. Hai cách lấy báo cáo trong Spring Boot

### 2.1. Bật `--debug` khi khởi động

Với ứng dụng Spring Boot, thêm cờ `--debug`:

```bash
java -jar target/app.jar --debug
```

Spring Boot sẽ in **CONDITIONS EVALUATION REPORT** vào log khởi động. Báo cáo thường được chia thành:

- **Positive matches**: cấu hình hoặc bean có condition match.
- **Negative matches**: cấu hình hoặc bean có ít nhất một condition không match; phần chi tiết cho biết condition nào không match và condition nào đã match.
- **Exclusions**: các auto-configuration bị loại trừ.
- **Unconditional classes**: các cấu hình được áp dụng không cần condition.

`--debug` không có nghĩa bật debug remote JVM hay mở debugger; nó bật chế độ debug của Spring Boot để in thêm thông tin, trong đó có condition report.

Phù hợp khi cần chẩn đoán nhanh ở môi trường local, CI hoặc một tiến trình không có HTTP server. Nếu log quá dài, hãy tìm tên auto-configuration hoặc phương thức `@Bean` liên quan thay vì đọc toàn bộ report.

### 2.2. Dùng Actuator endpoint `/actuator/conditions`

Nếu ứng dụng có Spring Boot Actuator và chạy web, có thể lấy report dạng JSON bằng endpoint `conditions`.

Thêm dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Cấu hình expose endpoint trong `application.properties`:

```properties
management.endpoints.web.exposure.include=health,conditions
```

Khởi động ứng dụng web rồi gọi:

```bash
curl -s http://localhost:8080/actuator/conditions
```

Endpoint trả về report của các ApplicationContext. Cấu trúc chính:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "SomeAutoConfiguration#someBean": [
          {
            "condition": "OnPropertyCondition",
            "message": "@ConditionalOnProperty ... matched"
          }
        ]
      },
      "negativeMatches": {
        "AnotherAutoConfiguration#anotherBean": {
          "notMatched": [
            {
              "condition": "OnBeanCondition",
              "message": "@ConditionalOnBean ... did not find any beans"
            }
          ],
          "matched": []
        }
      },
      "unconditionalClasses": []
    }
  }
}
```

Đây là **hình dạng minh họa rút gọn**, không phải JSON nguyên văn của một ứng dụng cụ thể. Report thực tế có nhiều class, nhiều condition và thông điệp phụ thuộc môi trường.

Các trường đáng chú ý:

| Trường | Ý nghĩa |
| --- | --- |
| `contexts` | Các ApplicationContext được báo cáo, theo id |
| `positiveMatches` | Các source có condition match |
| `negativeMatches` | Các source có condition không match |
| `notMatched` | Những condition không thỏa trong source đó |
| `matched` | Những condition khác vẫn thỏa trong cùng source |
| `unconditionalClasses` | Các lớp cấu hình không cần điều kiện |
| `parentId` | Id của parent context, nếu có |

Key trong `positiveMatches`/`negativeMatches` thường là tên class cấu hình hoặc dạng `ClassName#beanMethod`. Đây là cách tìm chính xác bean method cần so sánh.

**Lưu ý:** endpoint phải được bật, được expose và được phép truy cập. Chỉ expose `conditions` trên môi trường phù hợp, bảo vệ endpoint bằng Spring Security hoặc giới hạn management network theo chính sách vận hành; report có thể tiết lộ tên class, bean, dependency và các điều kiện cấu hình. Nếu không muốn expose HTTP endpoint, dùng `--debug`.

## 3. Đọc report theo loại condition

### 3.1. Thay dependency: `OnClassCondition`

`@ConditionalOnClass` kiểm tra một hoặc nhiều class có thể được load từ classpath hay không. Khi thêm hoặc bỏ một dependency, condition liên quan có thể đổi:

- Dependency có class cần thiết: class-level condition có thể match.
- Dependency bị bỏ khỏi runtime classpath: condition không match, cấu hình được bảo vệ bởi annotation có thể không được áp dụng.
- Những bean nằm trong cấu hình đó có thể biến mất; các condition khác phụ thuộc những bean này cũng có thể đổi theo.

Trong report, tìm `OnClassCondition` và message cho biết class nào được tìm thấy hoặc còn thiếu. Phân biệt **dependency có trong compile classpath** và **dependency có trong runtime classpath**: ứng dụng chạy cần class có mặt trong runtime classpath của process.

Không chỉ xem file `pom.xml`. Kiểm tra dependency graph thực tế và phạm vi dependency:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.example:optional-library
```

Nếu dùng Gradle, xem `runtimeClasspath`, chẳng hạn:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Một dependency được khai báo `test` hoặc `provided` có thể không có trong runtime theo cách ứng dụng cần. Version conflict hoặc exclusion bắc cầu cũng có thể làm class biến mất dù một dependency khác vẫn được khai báo.

### 3.2. Thay property: `OnPropertyCondition`

`@ConditionalOnProperty` kiểm tra property trong `Environment`. Khi đổi file cấu hình, profile, biến môi trường hoặc command-line argument, condition có thể chuyển từ positive sang negative và ngược lại.

Ví dụ:

```java
@Bean
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
public FeatureService featureService() {
    return new FeatureService("enabled");
}
```

Với cấu hình này:

```properties
demo.feature.enabled=true
```

condition match; còn `false` hoặc property không tồn tại thì method không được đăng ký. Vì `matchIfMissing=false`, việc thiếu property không được hiểu là bật tính năng.

Khi so sánh, ghi lại **giá trị thực tế mà ứng dụng nhận được**, không chỉ nội dung một file `application.properties`. Property có thể bị override bởi profile, environment variable, command-line argument, config import hoặc nguồn cấu hình có độ ưu tiên cao hơn.

Trong report, tìm `OnPropertyCondition` và đọc cả tên property, giá trị kỳ vọng, giá trị nhận được hoặc lý do property không tồn tại. Nếu message cho biết property không tìm thấy, hãy kiểm tra tên chính xác, prefix, profile active và thứ tự nguồn cấu hình.

### 3.3. Thay bean: `OnBeanCondition`

`@ConditionalOnBean`, `@ConditionalOnMissingBean` và `@ConditionalOnSingleCandidate` thuộc nhóm điều kiện theo bean. Khi thêm hoặc thay bean trong ứng dụng, nhiều entry có thể đổi:

- `@ConditionalOnBean`: từ không match sang match khi bean phù hợp được đăng ký.
- `@ConditionalOnMissingBean`: default có thể từ match sang không match khi ứng dụng cung cấp bean custom.
- `@ConditionalOnSingleCandidate`: có thể match với một bean hoặc nhiều bean có một primary duy nhất; có thể không match nếu nhiều bean không có primary duy nhất.

Ví dụ default:

```java
@Bean
@ConditionalOnMissingBean(FoundationClient.class)
public FoundationClient foundationClient() {
    return () -> "default";
}
```

Nếu người dùng thêm `FoundationClient` custom, condition của default không còn match. Consumer khác có `@ConditionalOnBean(FoundationClient.class)` vẫn có thể match và sử dụng bean custom.

Khi so sánh report, đừng kết luận “feature mất” chỉ vì default provider không còn được đăng ký. Hãy kiểm tra **bean custom có thay thế đúng contract hay không** và các consumer cuối cùng có xuất hiện không.

Condition theo bean được đánh giá dựa trên bean definitions đã được xử lý đến thời điểm đó. Nếu provider là auto-configuration khác, thứ tự xử lý có thể cần metadata `@AutoConfiguration(after = ...)`. Report giúp nhận ra consumer không thấy bean vì provider chưa được đăng ký, provider bị exclude, hoặc một condition khác không match.

## 4. Quy trình so sánh trước và sau thay đổi

Một bản so sánh đáng tin cậy cần giữ các yếu tố khác giống nhau. Không thay dependency, property và bean cùng lúc rồi cố suy ra yếu tố nào gây ra kết quả.

### Bước 1 — chốt baseline

Trước thay đổi, ghi lại:

- Commit hoặc phiên bản source đang chạy.
- Spring Boot version, JDK version và profile active.
- Runtime dependency graph hoặc file artifact.
- Command-line arguments và các property liên quan.
- Bean custom nào được đăng ký.
- Condition report gốc.

Đặt tên file theo thay đổi và thời điểm, ví dụ `conditions-baseline.json`. Nếu dùng `--debug`, lưu log khởi động đầy đủ để có thể truy lại source và thông điệp.

### Bước 2 — chỉ thay một yếu tố

Chọn đúng một nhóm thay đổi:

- **Dependency:** thêm/bỏ/nâng version một thư viện, giữ property và bean như cũ.
- **Property:** đổi một property, giữ dependency và bean như cũ.
- **Bean:** thêm bean custom, bỏ bean custom hoặc thay implementation, giữ dependency và property như cũ.

Với thay đổi dependency, build lại artifact sau khi cập nhật dependency graph. Với property hoặc bean, dùng cùng artifact nếu source không thay đổi.

### Bước 3 — khởi động lại và lấy report sau thay đổi

Condition được đánh giá trong quá trình khởi động context. Vì vậy phải khởi động **một ApplicationContext mới** sau khi thay đổi. Lưu report thứ hai, chẳng hạn `conditions-after-property.json`.

Không coi việc thay property trong một file đang mở hoặc đăng ký bean sau khi context đã refresh là tương đương với một lần đánh giá condition mới. Để so sánh chuẩn, dừng process cũ và khởi động lại với cấu hình mới.

### Bước 4 — so sánh đúng source

Tập trung vào các entry liên quan:

1. Auto-configuration provider.
2. Bean method tạo foundation bean.
3. Auto-configuration consumer.
4. Bean method của feature phụ thuộc.
5. Các downstream consumer khác dùng foundation/feature bean.

Với mỗi source, đối chiếu:

- Nằm trong positive hay negative matches?
- Condition nào match hoặc không match?
- Message thay đổi như thế nào?
- Bean thực tế có tồn tại sau startup không?
- Có fallback hoặc consumer nào biến mất theo không?

Không chỉ đếm số lượng positive/negative match của toàn ứng dụng. Một dependency mới có thể khiến nhiều auto-configuration khác đổi trạng thái; phần lớn thay đổi đó không liên quan đến chức năng đang điều tra.

### Bước 5 — xác minh bằng bean registry và hành vi

Report cho biết **vì sao condition được đánh giá như vậy**. Nó không chứng minh đầy đủ rằng chức năng nghiệp vụ chạy đúng.

Sau khi xác định condition thay đổi, kiểm tra bean thực tế bằng `ApplicationContext.getBeansOfType(...)`, `ApplicationContextRunner` hoặc Actuator `/actuator/beans` nếu đã bật endpoint phù hợp. Cuối cùng chạy test/integration test cho request, job hoặc luồng nghiệp vụ phụ thuộc.

## 5. Ví dụ Spring Boot 3.3.5 / Java 17+ để tạo ba loại thay đổi

Ví dụ này có ba trục độc lập:

1. **Dependency:** auto-configuration feature chỉ có mặt khi class `org.h2.Driver` nằm trên runtime classpath.
2. **Property:** bean feature chỉ được tạo khi `demo.feature.enabled=true`.
3. **Bean:** ứng dụng có thể cung cấp `FoundationClient` custom; khi đó default client nhường chỗ và feature dùng client custom.

Ta sử dụng Actuator endpoint để lưu JSON report trước/sau. Cùng một cấu trúc source giúp quan sát từng condition thay đổi.

### 5.1. Cấu trúc thư mục

```text
condition-report-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── api/
    │   │   │   ├── FoundationClient.java
    │   │   │   └── FeatureService.java
    │   │   ├── app/
    │   │   │   └── DemoApplication.java
    │   │   └── autoconfigure/
    │   │       ├── FoundationClientAutoConfiguration.java
    │   │       └── FeatureAutoConfiguration.java
    │   └── resources/
    │       ├── application.properties
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/app/
        └── ConditionChangeTests.java
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
    <artifactId>condition-report-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` cung cấp web server để gọi Actuator bằng HTTP. H2 chỉ đóng vai trò **dependency marker** cho ví dụ classpath condition; chương trình không kết nối database. Khi bỏ dependency H2 và build lại, feature auto-configuration sẽ không match điều kiện classpath.

### 5.3. `src/main/resources/application.properties`

```properties
management.endpoints.web.exposure.include=health,conditions
server.port=8080
```

Trong ví dụ local, endpoint `conditions` được expose để dễ quan sát. Khi triển khai thật, chỉ mở endpoint cho nhóm vận hành được phép truy cập.

### 5.4. `src/main/java/demo/api/FoundationClient.java`

```java
package demo.api;

public interface FoundationClient {
    String id();
}
```

### 5.5. `src/main/java/demo/api/FeatureService.java`

```java
package demo.api;

public record FeatureService(String description) {
}
```

### 5.6. Provider: `FoundationClientAutoConfiguration`

Tệp `src/main/java/demo/autoconfigure/FoundationClientAutoConfiguration.java`:

```java
package demo.autoconfigure;

import demo.api.FoundationClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FoundationClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationClient.class)
    public FoundationClient foundationClient() {
        return () -> "default";
    }
}
```

Report sẽ cho biết default bean được đăng ký vì chưa tìm thấy `FoundationClient` nào, hoặc không được đăng ký vì ứng dụng đã cung cấp bean custom.

### 5.7. Consumer: `FeatureAutoConfiguration`

Tệp `src/main/java/demo/autoconfigure/FeatureAutoConfiguration.java`:

```java
package demo.autoconfigure;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = FoundationClientAutoConfiguration.class)
@ConditionalOnClass(name = "org.h2.Driver")
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @ConditionalOnBean(FoundationClient.class)
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService("enabled:" + client.id());
    }
}
```

Có ba lớp quyết định:

- `@ConditionalOnClass` ở cấp class: chỉ xử lý feature configuration nếu H2 có mặt.
- `@ConditionalOnProperty` ở cấp bean: chỉ đăng ký feature khi property bật.
- `@ConditionalOnBean` ở cấp bean: cần có foundation client phù hợp.

`after` giúp provider auto-configuration được xử lý trước consumer để condition theo bean thấy bean definition do provider tạo. Nó không thể tạo lại provider nếu provider bị exclude hoặc không match.

### 5.8. Ứng dụng chính: `DemoApplication`

Tệp `src/main/java/demo/app/DemoApplication.java`:

```java
package demo.app;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "client",
            havingValue = "custom")
    public FoundationClient customFoundationClient() {
        return () -> "custom";
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {

            FoundationClient client =
                    context.getBeanProvider(FoundationClient.class)
                            .getIfAvailable();

            FeatureService feature =
                    context.getBeanProvider(FeatureService.class)
                            .getIfAvailable();

            System.out.println("client=" +
                    (client == null ? "none" : client.id()));

            System.out.println("feature=" +
                    (feature == null ? "disabled" : feature.description()));
        }
    }
}
```

Bean custom chỉ xuất hiện khi `demo.client=custom`. Khi đó `@ConditionalOnMissingBean` của provider nhường chỗ cho bean do ứng dụng cung cấp.

### 5.9. Khai báo auto-configuration

Tệp `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
demo.autoconfigure.FeatureAutoConfiguration
demo.autoconfigure.FoundationClientAutoConfiguration
```

Đặt consumer trước provider trong file để minh họa metadata `after` điều khiển thứ tự áp dụng auto-configuration. Trong dự án thực tế, tên lớp phải đúng hoàn toàn.

## 6. Chụp report và so sánh bốn trạng thái

Build:

```bash
mvn -q test
mvn -q -DskipTests package
```

Khởi động ứng dụng ở một terminal; dùng terminal khác gọi endpoint và lưu JSON. Sau mỗi lần chụp, dừng process bằng Ctrl+C rồi chạy lại với một bộ tham số mới.

### Trạng thái A — baseline: dependency có, property bật, dùng default bean

Khởi động:

```bash
java -jar target/condition-report-demo-0.0.1-SNAPSHOT.jar --demo.feature.enabled=true
```

Lưu report:

```bash
curl -s http://localhost:8080/actuator/conditions -o conditions-baseline.json
```

Hai dòng do chương trình in ra:

```text
client=default
feature=enabled:default
```

Kết quả cần tìm trong report:

- `FeatureAutoConfiguration` có positive match cho `OnClassCondition` vì `org.h2.Driver` có trên runtime classpath.
- `FeatureAutoConfiguration#featureService` có positive match cho `OnPropertyCondition` vì property bật.
- `FeatureAutoConfiguration#featureService` có positive match cho `OnBeanCondition` vì `FoundationClient` đã được đăng ký.
- `FoundationClientAutoConfiguration#foundationClient` có positive match cho `OnBeanCondition` của `@ConditionalOnMissingBean` vì chưa có client custom.

### Trạng thái B — chỉ tắt property

Dừng ứng dụng, khởi động lại cùng JAR và cùng dependency:

```bash
java -jar target/condition-report-demo-0.0.1-SNAPSHOT.jar --demo.feature.enabled=false
```

Lưu report:

```bash
curl -s http://localhost:8080/actuator/conditions -o conditions-property-off.json
```

Output ứng dụng:

```text
client=default
feature=disabled
```

Khi so sánh với baseline:

- Class-level `OnClassCondition` vẫn match vì H2 không đổi.
- Provider default vẫn có mặt.
- `FeatureAutoConfiguration#featureService` chuyển sang negative match do `OnPropertyCondition` không thỏa.
- Consumer không được đăng ký; đây là **feature bị tắt có chủ đích**, không phải lỗi khởi tạo bean.

### Trạng thái C — chỉ thêm bean custom

Dừng ứng dụng, bật lại feature và thêm property cho client custom:

```bash
java -jar target/condition-report-demo-0.0.1-SNAPSHOT.jar --demo.feature.enabled=true --demo.client=custom
```

Lưu report:

```bash
curl -s http://localhost:8080/actuator/conditions -o conditions-custom-bean.json
```

Output ứng dụng:

```text
client=custom
feature=enabled:custom
```

Khi so sánh với baseline:

- `OnClassCondition` vẫn match.
- `OnPropertyCondition` vẫn match.
- `FoundationClientAutoConfiguration#foundationClient` không còn tạo default vì `@ConditionalOnMissingBean` tìm thấy bean custom.
- `FeatureAutoConfiguration#featureService` vẫn match `@ConditionalOnBean` và sử dụng client custom.

Đây là ví dụ quan trọng: **default provider chuyển từ positive sang negative match nhưng consumer vẫn positive**. Không nên coi mọi negative match là lỗi; default nhường chỗ là hành vi mong muốn.

### Trạng thái D — chỉ bỏ dependency H2

Trở về property baseline (`demo.feature.enabled=true`, không khai báo `demo.client=custom`). Xóa dependency H2 khỏi `pom.xml`:

```xml
<!-- Bỏ dependency này khỏi pom.xml -->
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>runtime</scope>
</dependency>
```

Build lại artifact:

```bash
mvn -q -DskipTests clean package
mvn dependency:tree -Dincludes=com.h2database:h2
```

Xác nhận dependency không còn trong runtime dependency graph. Khởi động lại với cùng property baseline:

```bash
java -jar target/condition-report-demo-0.0.1-SNAPSHOT.jar --demo.feature.enabled=true
```

Lưu report:

```bash
curl -s http://localhost:8080/actuator/conditions -o conditions-no-h2.json
```

Output:

```text
client=default
feature=disabled
```

Khi so sánh:

- `FeatureAutoConfiguration` chuyển sang negative match vì `OnClassCondition` không tìm thấy `org.h2.Driver`.
- Các method condition bên trong class không được xử lý như khi class-level condition match; đừng kỳ vọng luôn thấy một negative entry riêng cho `featureService`.
- `FoundationClientAutoConfiguration` không phụ thuộc H2, nên default client vẫn có mặt.
- Consumer feature không được đăng ký vì toàn bộ feature auto-configuration bị bỏ qua.

Lưu ý: H2 trong ví dụ chỉ là dependency marker, không phải database đang được kết nối. Bỏ H2 không làm provider client biến mất; nó chỉ loại nhánh feature được bảo vệ bởi classpath condition.

### 6.1. Ma trận so sánh

| Trạng thái | H2 trên classpath | `demo.feature.enabled` | Client được chọn | Feature |
| --- | --- | --- | --- | --- |
| A. Baseline | Có | true | default | enabled:default |
| B. Property off | Có | false | default | disabled |
| C. Custom bean | Có | true | custom | enabled:custom |
| D. Dependency off | Không | true | default | disabled |

Ma trận cho thấy mỗi thay đổi ảnh hưởng một condition khác nhau. Trong ứng dụng thực tế, một thay đổi dependency cũng có thể tác động đến nhiều auto-configuration khác; cần xem các source liên quan chứ không chỉ nhìn một dòng tổng kết.

## 7. So sánh hai JSON report bằng PowerShell

Report Actuator có các object JSON động theo tên source. Dùng PowerShell để lấy entry của một source cụ thể mà không cần đọc toàn bộ report:

```powershell
$before = Get-Content .\conditions-baseline.json -Raw | ConvertFrom-Json
$after = Get-Content .\conditions-property-off.json -Raw | ConvertFrom-Json

$source = 'FeatureAutoConfiguration#featureService'

'--- BEFORE: positive ---'
$before.contexts.application.positiveMatches.PSObject.Properties[$source].Value |
    ConvertTo-Json -Depth 20

'--- BEFORE: negative ---'
$before.contexts.application.negativeMatches.PSObject.Properties[$source].Value |
    ConvertTo-Json -Depth 20

'--- AFTER: positive ---'
$after.contexts.application.positiveMatches.PSObject.Properties[$source].Value |
    ConvertTo-Json -Depth 20

'--- AFTER: negative ---'
$after.contexts.application.negativeMatches.PSObject.Properties[$source].Value |
    ConvertTo-Json -Depth 20
```

Đổi tên file đầu vào và `$source` để so sánh `conditions-custom-bean.json` hoặc `conditions-no-h2.json`. Nếu một source không có trong positive/negative của report, có thể class configuration chưa được xử lý do condition cấp lớp không match; hãy kiểm tra entry class-level `FeatureAutoConfiguration`.

Một cách đọc kết quả hiệu quả là lập bảng nhỏ:

| Source | Trước | Sau | Diễn giải |
| --- | --- | --- | --- |
| `FeatureAutoConfiguration` | Positive OnClass | Negative OnClass | Dependency marker đã biến mất |
| `FeatureAutoConfiguration#featureService` | Positive property + bean | Negative property | Feature bị tắt bằng property |
| `FoundationClientAutoConfiguration#foundationClient` | Positive missing-bean | Negative missing-bean | Default nhường chỗ cho custom bean |

Đây là **các ví dụ đối chiếu theo từng kịch bản**. Entry thực tế phụ thuộc đúng source, version và môi trường chạy. Đừng chép message từ một phiên bản report khác rồi coi là output cố định.

## 8. Kiểm thử hành vi condition bằng `ApplicationContextRunner`

Report giúp giải thích, còn test bảo vệ hợp đồng của auto-configuration. Tạo `src/test/java/demo/app/ConditionChangeTests.java`:

```java
package demo.app;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import demo.autoconfigure.FeatureAutoConfiguration;
import demo.autoconfigure.FoundationClientAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionChangeTests {

    private ApplicationContextRunner runner(String... properties) {
        return new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        FoundationClientAutoConfiguration.class,
                        FeatureAutoConfiguration.class))
                .withPropertyValues(properties);
    }

    @Test
    void enabledFeatureUsesDefaultClient() {
        runner("demo.feature.enabled=true").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(FoundationClient.class);
            assertThat(context).hasSingleBean(FeatureService.class);
            assertThat(context.getBean(FeatureService.class).description())
                    .isEqualTo("enabled:default");
        });
    }

    @Test
    void disabledPropertyRemovesOnlyFeature() {
        runner("demo.feature.enabled=false").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(FoundationClient.class);
            assertThat(context).doesNotHaveBean(FeatureService.class);
        });
    }

    @Test
    void customClientReplacesDefaultAndFeatureStillWorks() {
        runner("demo.feature.enabled=true")
                .withBean(FoundationClient.class, () -> () -> "custom")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(FoundationClient.class);
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getBean(FeatureService.class)
                            .description())
                            .isEqualTo("enabled:custom");
                });
    }

    @Test
    void missingFoundationPreventsFeatureRegistration() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        FeatureAutoConfiguration.class))
                .withPropertyValues("demo.feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(FoundationClient.class);
                    assertThat(context).doesNotHaveBean(FeatureService.class);
                });
    }
}
```

Chạy test:

```bash
mvn -q test
```

Bốn test xác minh hành vi khi property bật/tắt, bean custom thay thế default và provider vắng mặt. H2 có trên test runtime classpath do dependency trong `pom.xml`; nếu muốn test classpath condition âm, có thể bổ sung test với `FilteredClassLoader` của Spring Boot Test để ẩn `org.h2.Driver`. Các lệnh build/run ở kịch bản D xác minh thêm việc bỏ dependency khỏi artifact thật.

## 9. Những sai lầm khi đọc và so sánh report

1. **Coi report là diff tự động.** Không phải: mỗi report chỉ mô tả một lần khởi động. Phải lưu snapshot trước/sau và so sánh cùng source.
2. **Thay nhiều yếu tố cùng lúc.** Khi vừa đổi dependency, property và bean, không thể biết condition nào gây thay đổi. Mỗi lần chỉ đổi một yếu tố.
3. **Chỉ tìm một condition và bỏ qua condition khác trên cùng source.** Một bean có thể cần cả property lẫn bean condition; tất cả điều kiện áp dụng phải thỏa.
4. **Nhầm class-level negative match với method-level negative match.** Nếu class-level condition không match, cấu hình có thể bị loại trước khi method conditions được đánh giá.
5. **Coi negative match là lỗi.** `@ConditionalOnMissingBean` không match vì có bean custom thường là back-off đúng ý đồ.
6. **Chỉ đọc file properties mà không xem giá trị runtime.** Profile, environment variable, command-line và config import có thể override giá trị.
7. **Nhìn dependency khai báo mà không kiểm tra runtime graph.** Scope, exclusion, version conflict và dependency bắc cầu có thể khiến class không có trên runtime classpath.
8. **Cho rằng condition theo bean đếm object sau khởi tạo.** Conditions được đánh giá trong giai đoạn xử lý cấu hình dựa trên bean definitions đã biết, không phải sau mỗi request.
9. **Chỉ kiểm tra report, không kiểm tra bean thực tế.** Một condition match chưa chứng minh chức năng nghiệp vụ hoạt động; cần test bean registry và luồng thực thi.
10. **So sánh report từ môi trường khác nhau.** Profile, JDK, Boot version, OS, environment, classpath và command line có thể làm nhiều condition đổi. Chuẩn hóa môi trường trước khi kết luận.

## 10. Checklist điều tra một thay đổi

Khi review một PR thay dependency, property hoặc bean, thực hiện theo thứ tự:

- [ ] Chụp Condition Evaluation Report trước thay đổi.
- [ ] Ghi lại Boot/JDK version, profile, command line và runtime dependency graph.
- [ ] Chỉ thay một yếu tố trong lần so sánh.
- [ ] Khởi động context mới và lưu report sau thay đổi.
- [ ] So sánh source provider, consumer và downstream bean liên quan.
- [ ] Ghi rõ condition nào chuyển positive ↔ negative và message giải thích.
- [ ] Kiểm tra bean thực tế theo type/name/qualifier và số lượng ứng viên.
- [ ] Kiểm tra fallback/back-off có đúng ý đồ không.
- [ ] Chạy test auto-configuration và integration test cho chức năng bị ảnh hưởng.
- [ ] Lưu lại nguyên nhân, thay đổi dự kiến và bằng chứng xác minh trong PR/review.

**Cách kết luận nên cụ thể:** “Sau khi bỏ H2 khỏi runtime classpath, `FeatureAutoConfiguration` chuyển sang negative match ở `OnClassCondition`; provider `FoundationClient` vẫn tồn tại; `FeatureService` không được đăng ký. Đây là kết quả đúng theo thiết kế feature chỉ hỗ trợ khi H2 có mặt.” Một kết luận như vậy chỉ rõ nguyên nhân, phạm vi tác động và bean còn/mất.

## Tài liệu chính thức

- [Spring Boot 3.3 — Conditions Evaluation Report Actuator API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): cách lấy report và cấu trúc `contexts`, `positiveMatches`, `negativeMatches`, `unconditionalClasses`.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): cách bật, expose và kiểm soát truy cập endpoint.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): class, property, bean conditions, thứ tự auto-configuration và kiểm thử.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): `ApplicationContextRunner` và cách kiểm thử các nhánh condition.
