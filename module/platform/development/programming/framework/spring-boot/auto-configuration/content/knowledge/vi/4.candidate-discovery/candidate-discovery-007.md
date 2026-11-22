# Vai trò của AutoConfigurationImportFilter và metadata hỗ trợ lọc

## 1. Vị trí của bộ lọc trong quá trình khám phá auto-configuration

Trong Spring Boot, chỉ vì một lớp được liệt kê là ứng viên auto-configuration không có nghĩa nó chắc chắn được import hoặc tạo bean. Trước khi Spring phân tích đầy đủ bytecode và các phương thức `@Bean` của ứng viên, Boot có thể **loại sớm những ứng viên chắc chắn không phù hợp**.

Hai thành phần quan trọng trong bước này:

- **`AutoConfigurationImportFilter`**: hợp đồng để một bộ lọc quyết định ứng viên auto-configuration nào được tiếp tục xem xét.
- **`AutoConfigurationMetadata`**: API đọc metadata được tạo trước lúc biên dịch từ annotation trên các lớp auto-configuration; nhờ đó bộ lọc có thể quyết định nhanh mà không cần nạp đầy đủ class.

Trong Spring Boot 3.3.x, quá trình có thể hình dung:

```text
@SpringBootApplication
  -> @EnableAutoConfiguration
      -> AutoConfigurationImportSelector (DeferredImportSelector)
          -> tìm tên ứng viên từ *.imports
          -> loại trùng và áp dụng exclusions
          -> nạp các AutoConfigurationImportFilter
          -> đọc AutoConfigurationMetadata nếu có
          -> gọi filter.match(candidateNames, metadata)
          -> bỏ ứng viên bị kết luận false
          -> sắp thứ tự và import các ứng viên còn lại
              -> Spring phân tích @Configuration và @Conditional
              -> đăng ký những BeanDefinition phù hợp
              -> BeanFactory tạo bean khi cần
```

Sơ đồ này rút gọn một số xử lý nhóm, thứ tự và các vòng đánh giá của `DeferredImportSelector`. Cần phân biệt **lọc danh sách tên lớp trước import** với **đánh giá `@Conditional` khi Spring xử lý cấu hình**. Chúng bổ sung cho nhau.

Một bộ lọc giữ lại ứng viên chỉ có nghĩa ứng viên **có thể tiếp tục** vào pha xử lý cấu hình; không bảo đảm mọi bean trong đó sẽ được đăng ký. Ngược lại, khi bộ lọc loại hẳn ứng viên, lớp auto-configuration đó không được import qua danh sách ứng viên đang xét.

## 2. Phân biệt ba loại tệp metadata thường gặp

Đây là lỗi nhầm lẫn rất phổ biến trong quá trình học auto-configuration.

| Tệp | Vai trò | Ai đọc hoặc tạo |
| --- | --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | **Danh sách tên lớp ứng viên** auto-configuration, mỗi dòng một tên class | Do tác giả thư viện cung cấp; Boot đọc để khám phá ứng viên |
| `META-INF/spring-autoconfigure-metadata.properties` | **Metadata hỗ trợ lọc sớm** dựa trên annotation/điều kiện và thông tin cấu hình | Được `spring-boot-autoconfigure-processor` tạo lúc compile; Boot đọc để tối ưu |
| `META-INF/spring-configuration-metadata.json` | Mô tả **các key cấu hình**, type, description, default/hint cho IDE/tooling | Thường do `spring-boot-configuration-processor` tạo; không phải danh sách auto-configuration và không phải dữ liệu chính cho import filter |

Ví dụ tệp `AutoConfiguration.imports` trong thư viện:

```text
com.acme.boot.autoconfigure.AcmeClientAutoConfiguration
com.acme.boot.autoconfigure.AcmeHealthAutoConfiguration
```

Đây chỉ là **tên của ứng viên**. Boot vẫn xét exclusions, filter và các điều kiện của những lớp đó.

Ví dụ minh họa hình dạng của metadata được tạo:

```properties
com.acme.boot.autoconfigure.AcmeClientAutoConfiguration.ConditionalOnClass=com.acme.client.Client
```

Tên key/giá trị ở trên chỉ minh họa cho một điều kiện class đơn giản, không phải kết quả thực tế được bảo đảm từ một phiên bản processor cụ thể. Hãy xem file được sinh trong bản build của chính thư viện để biết dữ liệu thật.

Không nên tự viết tay tệp metadata này như một nguồn sự thật riêng rồi bỏ qua annotation. Trong module auto-configuration, nên dùng annotation processor đúng phiên bản để giữ metadata nhất quán với source. File metadata có thể thiếu hoặc không bao phủ hết điều kiện; ứng dụng vẫn phải dựa vào quá trình đánh giá điều kiện chính thức của Spring.

## 3. AutoConfigurationImportFilter là API nào?

Trong Spring Boot 3.3.13, giao diện thuộc package:

```java
org.springframework.boot.autoconfigure.AutoConfigurationImportFilter
```

Hợp đồng cốt lõi:

```java
boolean[] match(
    String[] autoConfigurationClasses,
    AutoConfigurationMetadata autoConfigurationMetadata
);
```

**Đây là chữ ký API để giải thích**, không phải file Java tự biên dịch độc lập.

- `autoConfigurationClasses`: mảng các **tên lớp đầy đủ** của ứng viên hiện đang được xét, không phải mảng các `Class<?>` đã nạp. Mảng có thể chứa phần tử `null` do các bước lọc trước.
- `autoConfigurationMetadata`: cung cấp metadata tạo trước bằng annotation processor, giúp tránh phân tích không cần thiết.
- Kết quả `boolean[]` **phải có cùng độ dài** với mảng ứng viên. Phần tử `true` cho phép ứng viên ở vị trí tương ứng tiếp tục; `false` loại ứng viên đó khỏi lần import này.
- Bộ lọc **không được sửa** các phần tử của mảng `autoConfigurationClasses`.
- Có thể có nhiều filter; ứng viên bị một filter loại sẽ không được khôi phục chỉ vì filter khác trả `true`. Cần viết filter chịu được phần tử `null`.
- Đây là API mở rộng infrastructure; phần lớn ứng dụng bình thường không phải tự triển khai nó.

Ví dụ logic đơn giản:

```text
candidates = [A, B, C]
filter F1 = [true, false, true]
filter F2 = [true, true, false]
kết quả còn lại = [A]
```

`false` là quyết định loại. Không nên nhầm `true` với “chắc chắn bean sẽ tồn tại”: ứng viên A vẫn có thể bị `@ConditionalOnProperty` hay `@ConditionalOnMissingBean` đánh giá tiếp khi Spring phân tích.

### Cơ chế đăng ký filter

Trong Spring Boot 3.3.x, `AutoConfigurationImportFilter` được đăng ký bằng `META-INF/spring.factories`, chẳng hạn:

```properties
org.springframework.boot.autoconfigure.AutoConfigurationImportFilter=\
com.acme.boot.filter.AcmeImportFilter
```

**Lưu ý khác nhau về tệp:** lớp auto-configuration được liệt kê trong `AutoConfiguration.imports`, còn triển khai **filter** được khai báo qua key `AutoConfigurationImportFilter` trong `spring.factories`. Di chuyển dòng filter sang `.imports` không tạo ra filter. Không cần đánh dấu filter bằng `@Component` để đăng ký theo cách này.

Boot có thể gọi các phương thức thuộc các giao diện `Aware` sau trước khi gọi `match(...)` nếu filter triển khai chúng:

- `EnvironmentAware`: lấy `Environment` để đọc property.
- `BeanFactoryAware`: nhận `BeanFactory`.
- `BeanClassLoaderAware`: nhận classloader dùng bởi container.
- `ResourceLoaderAware`: nhận bộ nạp tài nguyên.

Filter nên nhanh, không có side effect và không tạo bean nghiệp vụ trong lúc lọc. Nó chạy ở giai đoạn container còn đang dựng cấu hình; cố sử dụng mọi bean như khi ứng dụng đã sẵn sàng có thể làm lệch lifecycle hoặc gây lỗi khởi tạo sớm.

## 4. AutoConfigurationMetadata giúp giảm công việc như thế nào?

`AutoConfigurationMetadata` là interface cho phép đọc metadata đã được thu thập lúc build, thay vì bắt đầu bằng việc nạp và phân tích toàn bộ ứng viên runtime.

Một số phương thức quan trọng:

```java
boolean wasProcessed(String className);
String get(String className, String key);
Integer getInteger(String className, String key);
Set<String> getSet(String className, String key);
```

Đây là chữ ký rút gọn để đọc hiểu API; những overload có `defaultValue` cũng tồn tại. Khi dùng `getSet`, cần import `java.util.Set`. Những lời gọi `get...` có thể trả `null` nếu không tìm thấy metadata tương ứng; không nên coi việc thiếu metadata là bằng chứng điều kiện chắc chắn sai.

Giả sử một lớp auto-configuration mang:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.client.Client")
public class AcmeClientAutoConfiguration {
}
```

Annotation processor có thể thu thập điều kiện class này vào tệp `spring-autoconfigure-metadata.properties`. Một filter tối ưu có thể tra điều kiện đã biết để phát hiện sự thiếu mặt của `com.acme.client.Client` trên classpath **trước khi phải đọc toàn bộ cấu hình ứng viên**.

Lợi ích:

1. **Giảm I/O/metadata parsing** không cần thiết khi có nhiều auto-configuration trên classpath.
2. **Giảm cơ hội phải đọc bytecode** của những cấu hình chắc chắn không phù hợp.
3. Giúp khởi động tốt hơn khi dùng nhiều starter/thư viện có tính năng tùy chọn.
4. Giữ quyết định dựa trên thông tin định nghĩa tại build thay vì phải khởi tạo bean để “thử xem” có chạy được không.

Tuy nhiên, tối ưu này có giới hạn:

- Metadata chỉ phản ánh những điều kiện/thông tin mà processor hỗ trợ và có thể sinh tại compile time; không diễn đạt được mọi logic tùy chỉnh.
- Các điều kiện phụ thuộc bean hiện có, property động, profile hoặc ngữ cảnh thường vẫn cần đánh giá đúng giai đoạn tương ứng.
- Metadata không phải danh sách bean definition và không phải cache các instance.
- **Không có metadata không có nghĩa auto-configuration phải bị loại**; cần để Spring kiểm tra điều kiện thật nếu chưa có đủ thông tin.
- Hành vi lọc nhanh chỉ tối ưu quá trình quyết định ứng viên; không thay thế vòng đời bean, dependency injection hay logic `@Conditional` của framework.

## 5. Một ví dụ về OnClassCondition và các mức kiểm tra

Trong các bộ lọc tích hợp, điều kiện dựa trên classpath là trường hợp thích hợp để quyết định sớm: tên class cần có/không được có thường là thông tin mà processor có thể lưu trước.

Ví dụ minh họa lớp cấu hình:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.VendorClient")
class VendorClientAutoConfiguration {
    // Các @Bean liên quan đến VendorClient
}
```

Khi `com.vendor.sdk.VendorClient` không có trong classpath runtime, Boot có cơ sở loại hoặc bỏ qua cấu hình này theo điều kiện class. Metadata được tạo giúp quá trình lọc nhanh hơn khi có sẵn; việc xử lý điều kiện vẫn phải đúng dù metadata không được sinh.

Không phải mọi `@ConditionalOnClass` đều được quyết định tại một “filter chung” bất kể vị trí annotation. Một điều kiện đặt trực tiếp trên class auto-configuration có thể được xử lý sớm; điều kiện đặt trên một `@Bean` method trong nested configuration có thể cần phân tích cấu hình chi tiết hơn. Không nên diễn dịch rằng `AutoConfigurationImportFilter` thay toàn bộ hệ thống `Condition`.

Có ba lớp quyết định hữu ích để nhớ:

```text
1. Candidate discovery: tên lớp có trong .imports?
2. Import filtering: có bằng chứng loại sớm candidate?
3. Condition evaluation / bean registration:
   lớp cấu hình và phương thức @Bean có khớp điều kiện không?
```

Lớp 1 không chứng minh lớp 3 sẽ tạo bean. Lớp 2 hoạt động để tránh công việc không cần thiết trước lớp 3.

## 6. Ví dụ runnable: viết một AutoConfigurationImportFilter tùy chỉnh

Ví dụ này dùng **Java 17**, **Spring Boot 3.3.13** và **Maven**. Mục đích là so sánh hai lần chạy có và không có một auto-configuration được import bằng cách dùng filter đọc property `sample.greeting.enabled`.

Để kiểm soát rõ nghĩa, ví dụ có:

- Ứng dụng `demo.app.FilterDemoApplication` dùng `@SpringBootApplication`.
- API `demo.api.GreetingApi` là class thường, không phải component.
- Auto-configuration `demo.autoconfigure.GreetingAutoConfiguration`, nằm **ngoài vùng component scan** của lớp main.
- Filter `demo.filter.GreetingImportFilter`, được đăng ký trong `spring.factories`.
- Tệp `.imports` liệt kê lớp auto-configuration.
- Annotation processor cho phép build tạo metadata hỗ trợ lọc.

Ứng dụng vẫn có `ApplicationRunner`, nhưng nó nhận `ObjectProvider<GreetingApi>` để không làm startup thất bại khi filter loại bean mặc định. Ví dụ được tổ chức trong **một Maven module cho dễ chạy**; thư viện/starter thật thường đóng gói auto-configuration riêng.

### 6.1. Cây thư mục

```text
filter-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── app/FilterDemoApplication.java
    │   ├── api/GreetingApi.java
    │   ├── autoconfigure/GreetingAutoConfiguration.java
    │   └── filter/GreetingImportFilter.java
    └── resources/META-INF/
        ├── spring.factories
        └── spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Đặt `FilterDemoApplication` trong `demo.app`; các package `demo.api`, `demo.autoconfigure`, `demo.filter` là **package anh em**, nên component scan mặc định không tự đăng ký `GreetingAutoConfiguration`. Lớp đó chỉ có đường vào từ `.imports`.

### 6.2. Cấu hình Maven

**`pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>filter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter` mang các phụ thuộc Spring/Boot cơ bản. `spring-boot-autoconfigure-processor` chỉ nằm trên annotation processor path trong pha biên dịch, phục vụ tạo metadata; nó không phải dependency cần thiết để tạo bean runtime.

### 6.3. Class API

**`src/main/java/demo/api/GreetingApi.java`:**

```java
package demo.api;

public record GreetingApi(String message) {
}
```

Record Java này không có stereotype như `@Component`. Nếu không được đăng ký qua auto-configuration hoặc cấu hình ứng dụng, Spring không tự có bean `GreetingApi`.

### 6.4. Lớp auto-configuration

**`src/main/java/demo/autoconfigure/GreetingAutoConfiguration.java`:**

```java
package demo.autoconfigure;

import demo.api.GreetingApi;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingApi.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingApi.class)
    GreetingApi greetingApi() {
        return new GreetingApi("hello from auto-configuration");
    }
}
```

`@ConditionalOnClass(GreetingApi.class)` cho thấy một điều kiện class có thể được annotation processor thu thập để tối ưu sớm. Trong ví dụ, `GreetingApi` luôn có mặt vì là class của cùng project; điều kiện này thỏa. `@ConditionalOnMissingBean` giúp bean mặc định nhường chỗ nếu ứng dụng chủ động tạo bean cùng type.

Đừng nhầm hai điều kiện: thiếu class là một vấn đề về classpath; có bean hay chưa là tình trạng của registry ở thời điểm xử lý configuration.

### 6.5. Tệp liệt kê ứng viên

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:**

```text
demo.autoconfigure.GreetingAutoConfiguration
```

Nếu thiếu tệp hoặc sai tên class, Boot không khám phá được ứng viên auto-configuration này theo cơ chế thường dùng trong Spring Boot 3.3.x. Tệp này **không** đăng ký filter.

### 6.6. Filter quyết định có import ứng viên không

**`src/main/java/demo/filter/GreetingImportFilter.java`:**

```java
package demo.filter;

import org.springframework.boot.autoconfigure.AutoConfigurationImportFilter;
import org.springframework.boot.autoconfigure.AutoConfigurationMetadata;
import org.springframework.context.EnvironmentAware;
import org.springframework.core.env.Environment;

public final class GreetingImportFilter
        implements AutoConfigurationImportFilter, EnvironmentAware {

    private static final String TARGET =
        "demo.autoconfigure.GreetingAutoConfiguration";

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public boolean[] match(
            String[] autoConfigurationClasses,
            AutoConfigurationMetadata autoConfigurationMetadata) {

        boolean enabled = environment.getProperty(
            "sample.greeting.enabled", Boolean.class, true);

        boolean[] result = new boolean[autoConfigurationClasses.length];
        for (int i = 0; i < autoConfigurationClasses.length; i++) {
            String candidate = autoConfigurationClasses[i];

            // null có thể xuất hiện do filter chạy trước đó.
            // Cho qua những ứng viên khác và chỉ quyết định TARGET.
            result[i] = !TARGET.equals(candidate) || enabled;
        }
        return result;
    }
}
```

Phân tích:

- `EnvironmentAware` làm cho filter nhận được `Environment` trước lúc gọi `match(...)`.
- Property `sample.greeting.enabled` **do ví dụ tự đặt**, không phải property có sẵn của Spring Boot.
- Nếu property vắng mặt, default `true`; filter giữ lại `GreetingAutoConfiguration`.
- Nếu property bằng `false`, phần tử tương ứng trả về `false`, Boot loại ứng viên khỏi danh sách import.
- Mảng kết quả có chính xác độ dài mảng đầu vào.
- `TARGET.equals(candidate)` an toàn cả khi `candidate` là `null`; filter không sửa mảng đầu vào và không tạo bean.
- Tham số `autoConfigurationMetadata` sẵn để filter tra metadata đã được sinh; ví dụ cố ý không dùng nó vì quyết định riêng dựa trên property. Phần sau minh họa API đọc metadata và lý do cần fallback.

### 6.7. Đăng ký filter trong spring.factories

**`src/main/resources/META-INF/spring.factories`:**

```properties
org.springframework.boot.autoconfigure.AutoConfigurationImportFilter=\
demo.filter.GreetingImportFilter
```

Điểm này rất quan trọng: **filter** được Boot nạp qua `spring.factories`, còn **ứng viên auto-configuration** được lấy từ `.imports`. Dùng sai tệp khiến thí nghiệm không phản ánh ý định.

Đây là file properties hợp lệ: dấu `\` cuối dòng nối giá trị sang dòng tiếp theo. Cũng có thể ghi toàn bộ cặp key/value trên một dòng.

### 6.8. Lớp ứng dụng và đầu ra quan sát

**`src/main/java/demo/app/FilterDemoApplication.java`:**

```java
package demo.app;

import demo.api.GreetingApi;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class FilterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ObjectProvider<GreetingApi> provider) {
        return args -> {
            GreetingApi greeting = provider.getIfAvailable();
            System.out.println("GREETING_PRESENT: " + (greeting != null));
            if (greeting != null) {
                System.out.println("GREETING: " + greeting.message());
            }
        };
    }
}
```

Với `ObjectProvider`, runner có thể kiểm tra sự hiện diện của bean mà không thất bại khi filter loại auto-configuration. Nếu ta inject bắt buộc `GreetingApi` vào constructor, lần chạy disabled có thể lỗi startup vì thiếu dependency; khi đó không quan sát được thông báo được thiết kế ở đây.

### 6.9. Build và chạy hai trường hợp

Yêu cầu: Java 17+, Maven và quyền truy cập dependency Maven. Trong thư mục `filter-demo`:

```bash
mvn -q -DskipTests package
java -jar target/filter-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Bỏ qua log và banner, các dòng do ứng dụng in:

```text
GREETING_PRESENT: true
GREETING: hello from auto-configuration
```

Lý do: mặc định `sample.greeting.enabled=true`; filter giữ ứng viên, `@ConditionalOnClass` khớp, không có bean `GreetingApi` do ứng dụng khai báo, nên `@Bean greetingApi()` được đăng ký và được lấy qua `ObjectProvider`.

Lần thứ hai:

```bash
java -jar target/filter-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --sample.greeting.enabled=false
```

Dòng do ứng dụng in:

```text
GREETING_PRESENT: false
```

Lý do: filter trả `false` cho ứng viên `demo.autoconfigure.GreetingAutoConfiguration`, nên cấu hình này không được import để đăng ký bean `greetingApi`. `ObjectProvider#getIfAvailable()` trả `null`, runner vẫn chạy được.

**Ý nghĩa của thí nghiệm:** filter quyết định **danh sách ứng viên cần import**. Các điều kiện `@ConditionalOnClass` và `@ConditionalOnMissingBean` là các kiểm tra khác. Trong ứng dụng bình thường, nếu chỉ muốn bật/tắt bean theo property, thường dùng `@ConditionalOnProperty` dễ bảo trì hơn; viết `AutoConfigurationImportFilter` là kỹ thuật cho thư viện/infrastructure khi thật sự cần lọc sớm.

## 7. Xem metadata sinh ra từ annotation processor

Sau khi biên dịch, trong Maven project, metadata được đặt trong output resources của build và được đưa vào JAR nếu được sinh thành công:

```text
target/classes/META-INF/spring-autoconfigure-metadata.properties
```

Có thể kiểm tra bằng lệnh:

```bash
jar tf target/filter-demo-0.0.1-SNAPSHOT.jar
```

Tìm đường dẫn metadata trong kết quả `jar tf`. Với Spring Boot executable JAR, các ứng dụng đóng gói lại có thể đặt tài nguyên ứng dụng dưới `BOOT-INF/classes/`; đó là vị trí trong archive, không có nghĩa đường dẫn resource mà Boot đọc thay đổi.

Trên hệ thống có công cụ unzip, có thể xem nội dung class output:

```bash
cat target/classes/META-INF/spring-autoconfigure-metadata.properties
```

Lệnh `cat` phù hợp với shell Unix/macOS/Git Bash; trên Windows PowerShell có thể dùng `Get-Content` thay thế.

Trong ví dụ, processor có thể ghi metadata cho điều kiện `@ConditionalOnClass` của `GreetingAutoConfiguration`. Đừng kỳ vọng phải thấy một nội dung key/value giống hệt ví dụ minh họa ở mục 2; định dạng và tập điều kiện được xử lý phụ thuộc phiên bản processor.

Một filter muốn đọc metadata có thể dùng các API sau (đoạn minh họa, **không phải tệp Java độc lập**):

```java
String configClass = "demo.autoconfigure.GreetingAutoConfiguration";
boolean processed = autoConfigurationMetadata.wasProcessed(configClass);
Set<String> requiredClasses =
    autoConfigurationMetadata.getSet(configClass, "ConditionalOnClass");

// processed có thể false và requiredClasses có thể null.
// Không được suy ra "không có metadata" = "không khớp condition".
```

Đây là ví dụ cách đọc API, không phải yêu cầu sửa filter đang chạy trong mục 6. Việc xử lý `ConditionalOnClass` tối ưu có sẵn trong Boot; không nên tự cài một bản kiểm tra classpath thứ hai chỉ để minh họa. Trường hợp cần điều kiện khác, hãy định nghĩa contract rõ ràng, kiểm thử với metadata có/không có và classloader phù hợp.

## 8. Khi metadata không có hoặc lỗi thời thì sao?

Một auto-configuration có thể chạy dù thư viện không tạo `spring-autoconfigure-metadata.properties`, miễn là danh sách ứng viên và điều kiện Spring được đăng ký hợp lệ. Metadata là **công cụ tăng tốc**.

Các tình huống:

| Tình huống | Hành vi an toàn |
| --- | --- |
| Có metadata đầy đủ cho một điều kiện được hỗ trợ | Có thể dùng nó để loại sớm ứng viên chắc chắn không phù hợp |
| Không có metadata cho một class | Để bộ xử lý condition chính thức đánh giá; không tự kết luận `false` |
| Metadata chứa key không có giá trị | Kiểm tra `null`/default trước khi dùng |
| Metadata được build từ source/phiên bản không khớp | Build lại đúng processor; không dựa vào metadata thủ công lỗi thời |
| Có nhiều JAR cung cấp metadata | Để cơ chế nạp tài nguyên của Boot xử lý; không giả định chỉ một file toàn ứng dụng |
| Điều kiện phụ thuộc environment hoặc bean runtime | Kiểm tra trong giai đoạn mà thông tin ấy đáng tin cậy |

Nội dung “loại sớm” phải bảo toàn hành vi đúng. Nếu filter loại nhầm một ứng viên, các điều kiện chạy sau sẽ **không có cơ hội khôi phục ứng viên đó**. Vì vậy một filter tùy chỉnh không nên đoán từ những thông tin mơ hồ.

Trong thực tế, nếu chỉ cần bật/tắt một feature bằng property:

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "acme.feature",
    name = "enabled",
    havingValue = "true"
)
class AcmeFeatureAutoConfiguration {
}
```

Đoạn này minh họa annotation và yêu cầu các import phù hợp. Boot đã có cơ chế condition; thường không cần filter tự viết để đọc lại cùng property.

## 9. Phân biệt filter với các cơ chế khác

### 9.1. Filter so với @ConditionalOnClass

`@ConditionalOnClass` biểu diễn điều kiện nghiệp vụ/kỹ thuật của cấu hình: “chỉ áp dụng khi class này tồn tại”. Bộ lọc sớm có thể khai thác metadata của điều kiện này để giảm công việc, nhưng **điều kiện vẫn là nguồn sự thật**. Nếu metadata không có, kiểm tra class trong quá trình xử lý cấu hình vẫn phải đúng.

### 9.2. Filter so với @ConditionalOnMissingBean

`@ConditionalOnMissingBean` dựa vào bean definitions đã được xử lý tại thời điểm đánh giá. Nó thường được dùng để mặc định nhường quyền cho bean do ứng dụng cung cấp. Một bộ lọc import làm việc sớm hơn và không nên tự giả định bean registry đã ở trạng thái hoàn chỉnh.

### 9.3. Filter so với excludes

Có thể loại trừ một auto-configuration cụ thể bằng:

```java
@SpringBootApplication(
    excludeName = "demo.autoconfigure.GreetingAutoConfiguration"
)
```

Hoặc:

```properties
spring.autoconfigure.exclude=demo.autoconfigure.GreetingAutoConfiguration
```

Đây là cách yêu cầu Boot loại hẳn một auto-configuration khỏi lần khởi động; nó **khác** với việc viết một filter custom. Các snippet này là minh họa, không dùng đồng thời với ví dụ chạy ở mục 6 nếu muốn quan sát filter.

Dùng exclude khi ứng dụng biết rõ lớp cấu hình không mong muốn. Dùng condition khi cấu hình phụ thuộc class/property/bean. Dùng filter tùy chỉnh khi đang phát triển infrastructure có nhu cầu lựa chọn ứng viên trước giai đoạn đọc/đăng ký cấu hình.

### 9.4. Filter so với @Primary và bean overriding

- `@Primary` chỉ giúp chọn ưu tiên trong autowiring giữa nhiều bean cùng type.
- Bean overriding cho phép một bean definition thay định nghĩa trùng tên nếu được phép.
- `@ConditionalOnMissingBean` có thể khiến default definition không được đăng ký.
- `AutoConfigurationImportFilter` có thể loại hẳn một **auto-configuration candidate** trước khi Spring xử lý các bean definitions bên trong.

Bốn cơ chế ở bốn lớp quyết định khác nhau; không thể thay thế tùy ý cho nhau.

## 10. Chẩn đoán filter và condition khi khởi động

Có thể dùng:

```bash
java -jar target/filter-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --sample.greeting.enabled=false \
  --debug
```

`--debug` giúp Boot xuất **Conditions Evaluation Report** để quan sát các positive/negative matches và exclusions. Tuy vậy, một candidate bị filter loại sớm có thể không xuất hiện như một negative match tương đương với một `@Conditional` được xét sau import. Report không phải log đầy đủ của **mọi** quyết định ở mọi filter.

Để kiểm tra filter custom:

1. Xác nhận lớp filter có trong JAR.
2. Xác nhận `META-INF/spring.factories` có key `org.springframework.boot.autoconfigure.AutoConfigurationImportFilter` và tên lớp filter đúng.
3. Xác nhận auto-configuration nằm trong `.imports` và không bị component scan vô tình nhặt vào.
4. Xác nhận `Environment` nhận giá trị property mong muốn.
5. Với một bản chạy kiểm thử, quan sát mảng kết quả `match(...)` cho candidate mục tiêu (có thể dùng logging chọn lọc, không ghi log toàn bộ candidate ở production).
6. Đối chiếu bean thực tế bằng `ApplicationContext`, `ObjectProvider` hoặc test context sau startup.

Không nên dùng `System.out.println` trong filter production: nó có thể chạy nhiều lần, làm nhiễu startup log và tăng I/O. Nếu cần quan sát, dùng logger có mức TRACE/DEBUG và tránh in dữ liệu cấu hình nhạy cảm.

### Những triệu chứng dễ gây hiểu sai

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Filter không chạy | Sai key/file `spring.factories`, class không vào JAR | Kiểm tra resources sau build |
| Auto-configuration vẫn được áp dụng dù đã filter | Auto-configuration bị scan/import bằng đường khác, sai tên TARGET | Kiểm tra package và `.imports` |
| Bean không xuất hiện dù filter trả `true` | Một condition sau đó không khớp hoặc bean đã được thay bằng cấu hình khác | Xem Conditions Evaluation Report |
| Build không có `spring-autoconfigure-metadata.properties` | Chưa bật `spring-boot-autoconfigure-processor` hoặc processor không chạy | Kiểm tra Maven plugin/Gradle annotationProcessor |
| Nhiều ứng viên bị loại ngoài dự tính | Mảng boolean sai index/chiều dài, xử lý `null` hoặc logic quá rộng | Kiểm thử độc lập `match(...)` trên nhiều candidate |
| Sau khi thêm metadata, hành vi thay đổi bất thường | Metadata cũ hoặc custom filter phụ thuộc dữ liệu không chắc chắn | Clean build và so sánh các lần chạy có/không metadata |

Khi điều tra hiệu năng, nên đo thời gian startup của ứng dụng thật thay vì giả định filter tùy chỉnh luôn nhanh hơn. Spring Boot đã có các bộ lọc và cơ chế điều kiện tối ưu cho nhiều trường hợp phổ biến.

## 11. Hướng dẫn thiết kế filter an toàn cho thư viện

Nếu đang viết thư viện tích hợp với Spring Boot:

1. **Định nghĩa auto-configuration theo điều kiện chính thức.** Dùng `@AutoConfiguration`, `@ConditionalOnClass`, `@ConditionalOnMissingBean` và property phù hợp. Không biến filter custom thành nguồn quy tắc duy nhất trong khi bỏ qua condition có ý nghĩa tương ứng.
2. **Khai báo auto-configuration trong `.imports`.** Tên lớp cần chính xác, nằm ngoài package component scan của ứng dụng.
3. **Thêm annotation processor cho metadata.** Đảm bảo build tạo resource; không tự sửa tệp generated hoặc nhầm với JSON metadata cho IDE.
4. **Chỉ viết filter nếu có lợi ích rõ ràng.** Chẳng hạn có nhiều ứng viên với thông tin tĩnh có thể loại chắc chắn trước pha parse. Đối với bật/tắt bằng property đơn giản, dùng `@ConditionalOnProperty` thường đủ.
5. **Xử lý mọi phần tử an toàn.** Duy trì mảng boolean cùng kích thước, không thay đổi input, chịu được `null`, không phụ thuộc thứ tự ngẫu nhiên và không tạo bean sớm.
6. **Có chiến lược khi metadata thiếu.** Nếu không thể biết chắc ứng viên không phù hợp, giữ ứng viên để các `Condition` kiểm tra sau.
7. **Kiểm thử cả hai hướng.** Với classpath đầy đủ/thiếu, properties bật/tắt, user-defined bean, exclusions và nhiều filter cùng hoạt động.
8. **Quan sát thực tế.** Có thể dùng `ApplicationContextRunner` trong module auto-configuration để kiểm tra các cấu hình có/không được đăng ký; dùng log có kiểm soát khi cần khảo sát chi tiết bước import.

Một filter có tác động rộng vì nó đứng trước nhiều bước Spring có thể xử lý bình thường. Một quyết định `false` sai không chỉ làm chậm startup mà còn làm thiếu tính năng thực sự cần thiết. Vì thế điều kiện loại sớm phải **đơn giản, kiểm chứng được, ít phụ thuộc trạng thái runtime**.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** File `.imports` có vai trò gì và vì sao nó chưa đủ để nói bean tồn tại?

**Đáp án:** Nó chỉ liệt kê ứng viên auto-configuration. Exclusion, import filters và điều kiện trong configuration/`@Bean` còn có thể ngăn đăng ký bean.

**Câu 2.** `AutoConfigurationImportFilter.match(...)` nhận gì và phải trả gì?

**Đáp án:** Nhận mảng tên lớp ứng viên và `AutoConfigurationMetadata`, trả `boolean[]` cùng độ dài; `false` loại ứng viên tương ứng. Mảng đầu vào có thể chứa `null` và không được sửa.

**Câu 3.** Bộ lọc đăng ký ở `.imports` hay `spring.factories`?

**Đáp án:** Trong Spring Boot 3.3.x, triển khai `AutoConfigurationImportFilter` được đăng ký bằng key của interface trong `META-INF/spring.factories`. Các lớp auto-configuration được liệt kê riêng trong `AutoConfiguration.imports`.

**Câu 4.** `spring-autoconfigure-metadata.properties` khác `spring-configuration-metadata.json` như thế nào?

**Đáp án:** File properties hỗ trợ lọc sớm auto-configuration; file JSON mô tả các cấu hình/property để IDE và tooling hỗ trợ người dùng. Chúng được tạo cho các mục đích khác nhau.

**Câu 5.** Không tìm thấy metadata của một ứng viên có đồng nghĩa phải lọc ứng viên đó không?

**Đáp án:** Không. Thiếu metadata là thiếu dữ liệu để tối ưu; phải giữ con đường đánh giá điều kiện đầy đủ của Spring.

**Câu 6.** Vì sao lần chạy `--sample.greeting.enabled=false` không có `GreetingApi` trong ví dụ?

**Đáp án:** Filter loại `GreetingAutoConfiguration` trước import; không còn cấu hình nào khác đăng ký bean đó trong project ví dụ.

**Câu 7.** Nếu filter trả `true` nhưng bean vẫn không có, bước nào cần kiểm tra?

**Đáp án:** Các condition trên configuration và phương thức `@Bean`, dependency, context type, properties, exclusions và lỗi khởi tạo. `true` ở import filter không buộc một bean phải được tạo.

**Câu 8.** Có nên dùng filter để giải quyết mọi điều kiện theo bean runtime?

**Đáp án:** Không. Registry có thể chưa đầy đủ ở thời điểm filter; các điều kiện như `@ConditionalOnMissingBean` thuộc giai đoạn xử lý cấu hình thích hợp hơn.

## Tài liệu tham khảo

- Spring Boot 3.3.13, `AutoConfigurationImportFilter` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html
- Spring Boot 3.3.13, `AutoConfigurationImportSelector` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot 3.3, Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3, Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot 3.3, `AutoConfigurationMetadata` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationMetadata.html
