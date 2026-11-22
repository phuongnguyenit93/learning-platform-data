# Tránh suy diễn rằng spring.factories đã bị loại bỏ với mọi cơ chế mở rộng

## 1. Kết luận cần nhớ trước tiên

Spring Boot đã thay đổi **cách đăng ký auto-configuration**: từ key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `META-INF/spring.factories` sang file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

Thay đổi đó **không có nghĩa file `spring.factories` bị xóa khỏi toàn bộ hệ sinh thái Spring**.

Trong Spring Boot 3.3:

- Không dùng key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `spring.factories` để đăng ký auto-configuration nữa.
- Vẫn dùng `spring.factories` cho một số extension point khác, ví dụ `EnvironmentPostProcessor` và `ApplicationListener`.
- Spring Framework vẫn cung cấp `SpringFactoriesLoader` để đọc các implementation được khai báo trong `META-INF/spring.factories`.
- Những cơ chế khác như `@Import`, component scanning, `ServiceLoader` hoặc `AutoConfiguration.imports` có quy tắc đăng ký riêng.

Vì vậy, khi nâng cấp một thư viện lên Spring Boot 3, hãy xem **từng key và extension point** trong file `spring.factories`. Chuyển key auto-configuration sang imports; giữ các key khác nếu extension point tương ứng vẫn yêu cầu chúng.

Bài này tập trung vào phạm vi thay đổi từ Spring Boot 2.6 trở về trước, Boot 2.7 và Boot 3.x. Ví dụ code dùng Java 17+ và Spring Boot 3.3.13.

## 2. Lịch sử thay đổi theo phiên bản

| Phiên bản | Đăng ký auto-configuration | Trạng thái key EnableAutoConfiguration trong spring.factories |
|---|---|---|
| Spring Boot 2.6 và cũ hơn | `META-INF/spring.factories` | Cơ chế đăng ký được hỗ trợ |
| Spring Boot 2.7 | `AutoConfiguration.imports` được giới thiệu | Vẫn được đọc để tương thích ngược, nhưng đã deprecated |
| Spring Boot 3.0 trở lên | `AutoConfiguration.imports` | Hỗ trợ key này đã bị loại bỏ |
| Spring Boot 3.3 | `AutoConfiguration.imports` | Không đăng ký auto-configuration bằng key cũ; các key spring.factories khác vẫn có thể được dùng |

### 2.1. Trước Spring Boot 2.7

Một thư viện công bố auto-configuration bằng file:

`src/main/resources/META-INF/spring.factories`

Ví dụ:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.catalog.autoconfigure.CatalogAutoConfiguration,\
com.acme.catalog.autoconfigure.CatalogWebAutoConfiguration
```

Spring Boot đọc danh sách class ở key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` để tìm các auto-configuration candidate.

Đây là cách đăng ký được mô tả trong tài liệu Spring Boot 2.5.

### 2.2. Spring Boot 2.7: giai đoạn chuyển tiếp

Spring Boot 2.7 giới thiệu file:

`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Mỗi dòng chứa tên đầy đủ của một auto-configuration class:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
com.acme.catalog.autoconfigure.CatalogWebAutoConfiguration
```

Boot 2.7 vẫn đọc các entry auto-configuration cũ trong `spring.factories` để tương thích ngược. Nếu cùng một class xuất hiện trong cả hai file, Boot 2.7 khử trùng lặp entry.

Đây là giai đoạn phù hợp để thư viện hỗ trợ đồng thời ứng dụng Boot cũ và mới: công bố candidate trong cả hai vị trí, sau đó kiểm thử trên các phiên bản mục tiêu.

Tuy nhiên, tài liệu Boot 2.7 đánh dấu việc nạp auto-configuration từ `spring.factories` là deprecated. Không nên hiểu khả năng tương thích ngược này là lời khuyên tiếp tục dùng key cũ cho các dự án mới.

### 2.3. Spring Boot 3.0: loại bỏ đúng một cơ chế đăng ký

Migration Guide của Boot 3 nói rõ: hỗ trợ đăng ký auto-configuration trong `spring.factories` bằng key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` đã bị loại bỏ để chuyển sang file imports.

Điểm quan trọng nằm ở vế tiếp theo của hướng dẫn: **các entry `spring.factories` dưới những key khác không bị ảnh hưởng bởi thay đổi này**.

Do đó, nếu một thư viện có cả hai nội dung:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.catalog.autoconfigure.CatalogAutoConfiguration

org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.catalog.CatalogEnvironmentPostProcessor
```

thì khi nâng cấp lên Boot 3:

- Chuyển `CatalogAutoConfiguration` sang `AutoConfiguration.imports`.
- Giữ entry `EnvironmentPostProcessor` nếu thư viện vẫn cung cấp processor này.

Không xóa toàn bộ file `spring.factories` chỉ vì key auto-configuration đã chuyển vị trí.

## 3. Ba cơ chế cần phân biệt

| Cơ chế | Tệp hoặc cách đăng ký | Ai xử lý? | Dùng cho việc gì? |
|---|---|---|---|
| Auto-configuration candidates | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Spring Boot auto-configuration import mechanism | Liệt kê các class cấu hình tự động |
| Factory/SPI registry | `META-INF/spring.factories` | Spring Framework `SpringFactoriesLoader` hoặc extension point của Spring Boot | Tìm implementation theo key là tên interface/loại factory |
| Các cơ chế Spring/Java khác | `@Import`, component scan, `ServiceLoader`, đăng ký trực tiếp... | Cơ chế tương ứng | Nạp cấu hình, component hoặc implementation theo hợp đồng riêng |

Không có một file duy nhất đăng ký tất cả mọi loại mở rộng.

### 3.1. AutoConfiguration.imports là danh sách candidate chuyên biệt

File imports không phải file properties. Mỗi dòng là một class name:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
com.acme.catalog.autoconfigure.CatalogMetricsAutoConfiguration
```

Spring Boot tìm file này trong các JAR trên classpath khi xử lý `@EnableAutoConfiguration`, thường được kích hoạt thông qua `@SpringBootApplication`.

Sau khi tìm thấy candidate, Boot tiếp tục đánh giá các condition như `@ConditionalOnClass`, `@ConditionalOnProperty` và `@ConditionalOnMissingBean`. Có tên trong imports không có nghĩa mọi bean của class chắc chắn được tạo; các condition vẫn quyết định cấu hình có áp dụng hay không.

Tác giả thư viện duy trì danh sách imports. Không dùng file này để đăng ký `EnvironmentPostProcessor`, `ApplicationListener` hoặc một SPI tùy chỉnh.

### 3.2. spring.factories là registry theo key

`spring.factories` dùng định dạng Java Properties. Key thường là tên đầy đủ của interface hoặc abstract class; value là danh sách tên implementation, phân tách bằng dấu phẩy.

Ví dụ:

```properties
com.acme.catalog.CatalogPlugin=\
com.acme.catalog.plugin.FastCatalogPlugin,\
com.acme.catalog.plugin.CachedCatalogPlugin
```

Đây là khai báo cho một SPI tên `CatalogPlugin`. Một đoạn code phải gọi factory loader cho loại SPI đó thì các implementation mới được tải.

File `spring.factories` **không tự động kích hoạt mọi key tùy ý**. Một extension point phải có code đọc key tương ứng, thường thông qua `SpringFactoriesLoader` hoặc cơ chế loader riêng của Spring Boot.

### 3.3. SpringFactoriesLoader vẫn đọc spring.factories

Spring Framework cung cấp:

`org.springframework.core.io.support.SpringFactoriesLoader`

Loader này tìm các file `META-INF/spring.factories` trong classpath, đọc entry theo key là factory type và khởi tạo implementation được khai báo.

Ví dụ với Spring Framework 6.1, có thể dùng API:

```java
SpringFactoriesLoader loader =
        SpringFactoriesLoader.forDefaultResourceLocation();

List<CatalogPlugin> plugins =
        loader.load(CatalogPlugin.class);
```

Các file factories từ nhiều JAR có thể cùng đóng góp implementation cho một factory type. Loader tổng hợp danh sách theo key và sắp xếp kết quả bằng `AnnotationAwareOrderComparator`; implementation trùng lặp được khử trùng lặp theo quy tắc của loader.

Đây là cơ chế tổng quát của Spring Framework. Việc Boot 3 bỏ một key auto-configuration không làm API `SpringFactoriesLoader` biến mất.

## 4. Những extension point vẫn dùng spring.factories trong Spring Boot 3.3

Một số ví dụ có tài liệu/API chính thức:

| Extension point | Key trong spring.factories | Vai trò |
|---|---|---|
| `EnvironmentPostProcessor` | `org.springframework.boot.env.EnvironmentPostProcessor` | Chỉnh sửa `Environment` trước khi ApplicationContext được refresh |
| `ApplicationListener` | `org.springframework.context.ApplicationListener` | Đăng ký listener tự động cho các application event, kể cả event xảy ra trước khi context được tạo |
| `FailureAnalyzer` | `org.springframework.boot.diagnostics.FailureAnalyzer` | Phân tích startup failure và đưa ra thông báo/hướng khắc phục |
| `ApplicationContextInitializer` | `org.springframework.context.ApplicationContextInitializer` | Khởi tạo hoặc tùy chỉnh ApplicationContext trước refresh |
| SPI do thư viện tự định nghĩa | Tên interface/abstract class của SPI | Nạp implementation khi code gọi `SpringFactoriesLoader` với đúng type |

Danh sách trên là các ví dụ, không phải danh sách đầy đủ mọi extension point. Khi làm việc với một loại cụ thể, kiểm tra API/tài liệu của đúng phiên bản để xác định loader và key được yêu cầu.

### 4.1. EnvironmentPostProcessor

`EnvironmentPostProcessor` cho phép thay đổi Environment trước khi ApplicationContext được refresh. API Spring Boot 3.3.13 nêu rõ implementation phải được đăng ký trong `META-INF/spring.factories` bằng tên đầy đủ của interface làm key.

Ví dụ:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.catalog.CatalogEnvironmentPostProcessor
```

Nội dung này vẫn có ý nghĩa trong Boot 3.3. Không chuyển entry đó sang `AutoConfiguration.imports`, vì imports dành cho auto-configuration candidates.

### 4.2. ApplicationListener

Nếu muốn listener được đăng ký tự động cho các event của `SpringApplication`, kể cả một số event xảy ra trước khi context tồn tại, tài liệu Spring Boot vẫn hướng dẫn dùng `META-INF/spring.factories`:

```properties
org.springframework.context.ApplicationListener=\
com.acme.catalog.CatalogStartupListener
```

Listener dạng bean có thể xử lý các event sau khi context được tạo. Với những event rất sớm, đăng ký qua `SpringApplication.addListeners(...)` hoặc `spring.factories` phù hợp hơn.

### 4.3. FailureAnalyzer

Một thư viện có thể cung cấp `FailureAnalyzer` để chuyển exception khó hiểu thành thông báo lỗi có mô tả và hành động khắc phục:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.acme.catalog.CatalogConfigurationFailureAnalyzer
```

Đây cũng là một factory key riêng. Việc auto-configuration đã chuyển sang imports không thay đổi quy tắc đăng ký FailureAnalyzer trong Boot 3.3.

## 5. Ví dụ SPI tự định nghĩa với SpringFactoriesLoader

Giả sử thư viện cho phép ứng dụng mở rộng bằng plugin catalog. API:

```java
package com.acme.catalog;

public interface CatalogPlugin {

    String name();
}
```

Một implementation:

```java
package com.acme.catalog.plugin;

import com.acme.catalog.CatalogPlugin;

public class FastCatalogPlugin implements CatalogPlugin {

    @Override
    public String name() {
        return "fast";
    }
}
```

Đăng ký trong `META-INF/spring.factories`:

```properties
com.acme.catalog.CatalogPlugin=\
com.acme.catalog.plugin.FastCatalogPlugin
```

Code tiêu thụ:

```java
package com.acme.catalog;

import java.util.List;

import org.springframework.core.io.support.SpringFactoriesLoader;

public class CatalogPluginRegistry {

    public List<CatalogPlugin> loadPlugins() {
        return SpringFactoriesLoader
                .forDefaultResourceLocation()
                .load(CatalogPlugin.class);
    }
}
```

Khi `loadPlugins()` được gọi, Spring Framework tìm các `spring.factories` trên classpath và đọc key `com.acme.catalog.CatalogPlugin`.

Nếu chỉ viết key trong file mà không có code nào gọi loader hoặc xử lý SPI đó, plugin không tự xuất hiện trong ứng dụng. Registry và implementation contract là phần mà thư viện phải thiết kế.

Trong dự án thực tế, nên cân nhắc constructor injection, ordering, xử lý lỗi khởi tạo và khả năng nhiều thư viện cùng cung cấp plugin. Không nên dùng factory loading nếu một bean thông thường hoặc `@Import` đã giải quyết yêu cầu đơn giản hơn.

## 6. Ví dụ hoàn chỉnh: một JAR Boot 3.3 dùng cả hai file

Ví dụ này chứng minh hai cơ chế có thể cùng tồn tại trong một thư viện:

- `CatalogEnvironmentPostProcessor` được đăng ký bằng `spring.factories`.
- `CatalogAutoConfiguration` được đăng ký bằng `AutoConfiguration.imports`.

Ứng dụng khởi động sẽ in một giá trị do EnvironmentPostProcessor thêm vào và trạng thái bean do auto-configuration tạo ra.

### 6.1. Cấu trúc dự án

```text
catalog-compat-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   ├── com/acme/catalog/
    │   │   ├── CatalogEnvironmentPostProcessor.java
    │   │   └── CatalogFeature.java
    │   ├── com/acme/catalog/autoconfigure/
    │   │   └── CatalogAutoConfiguration.java
    │   └── com/acme/demo/
    │       └── CatalogDemoApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/
            ├── spring.factories
            └── spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 6.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.acme</groupId>
    <artifactId>catalog-compat-demo</artifactId>
    <version>1.0.0</version>

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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. CatalogFeature.java

```java
package com.acme.catalog;

public record CatalogFeature(String status) {
}
```

### 6.4. CatalogEnvironmentPostProcessor.java

```java
package com.acme.catalog;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class CatalogEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        Map<String, Object> values = Map.of(
                "acme.catalog.bootstrap-marker",
                "loaded");

        environment.getPropertySources().addLast(
                new MapPropertySource("catalogBootstrapMarker", values));
    }
}
```

Class này thêm một property vào Environment trước khi context được refresh. Nó không phải auto-configuration class và không được liệt kê trong `AutoConfiguration.imports`.

### 6.5. CatalogAutoConfiguration.java

```java
package com.acme.catalog.autoconfigure;

import com.acme.catalog.CatalogFeature;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CatalogFeature catalogFeature() {
        return new CatalogFeature("enabled");
    }
}
```

Auto-configuration được kích hoạt khi `acme.catalog.enabled=true`. Bean `CatalogFeature` là kết quả của cơ chế auto-configuration.

### 6.6. CatalogDemoApplication.java

```java
package com.acme.demo;

import com.acme.catalog.CatalogFeature;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class CatalogDemoApplication implements CommandLineRunner {

    private final Environment environment;
    private final CatalogFeature feature;

    public CatalogDemoApplication(
            Environment environment,
            CatalogFeature feature) {
        this.environment = environment;
        this.feature = feature;
    }

    public static void main(String[] args) {
        SpringApplication.run(CatalogDemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println(
                "environmentPostProcessor="
                        + environment.getProperty(
                                "acme.catalog.bootstrap-marker"));

        System.out.println(
                "autoConfiguration=" + feature.status());
    }
}
```

Package `com.acme.demo` là package của ứng dụng. `CatalogAutoConfiguration` nằm ngoài component scan thông thường và được phát hiện qua file imports. Đây là cách thể hiện đúng vai trò của auto-configuration candidate list.

### 6.7. spring.factories

Tạo file:

`src/main/resources/META-INF/spring.factories`

Nội dung:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.catalog.CatalogEnvironmentPostProcessor
```

File này đăng ký `EnvironmentPostProcessor`. Không đưa `CatalogAutoConfiguration` vào key `EnableAutoConfiguration` khi mục tiêu là Boot 3.x.

### 6.8. AutoConfiguration.imports

Tạo file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

File này chỉ liệt kê auto-configuration class. Không thêm `CatalogEnvironmentPostProcessor` vào đây.

### 6.9. application.properties

```properties
acme.catalog.enabled=true
```

### 6.10. Chạy ứng dụng

Từ thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

```bash
mvn -q spring-boot:run
```

Hai dòng do ứng dụng in ra:

```text
environmentPostProcessor=loaded
autoConfiguration=enabled
```

Log khởi động của Spring Boot có thể xuất hiện thêm. Hai dòng trên là output của các lệnh `System.out.println` trong `CommandLineRunner`.

Kết quả chứng minh:

1. Spring Boot vẫn đọc `spring.factories` để nạp EnvironmentPostProcessor.
2. Spring Boot đọc `AutoConfiguration.imports` để tìm CatalogAutoConfiguration.
3. Hai cơ chế cùng hoạt động trong một JAR, mỗi cơ chế phục vụ một extension point khác nhau.

## 7. Chiến lược tương thích khi thư viện hỗ trợ nhiều phiên bản Boot

Một thư viện có thể cần hỗ trợ nhiều thế hệ ứng dụng. Chọn file đăng ký dựa trên phiên bản thấp nhất và cao nhất mà thư viện cam kết hỗ trợ.

| Mục tiêu thư viện | Đăng ký auto-configuration | Nội dung spring.factories khác |
|---|---|---|
| Chỉ Boot 2.6 hoặc cũ hơn | Dùng key EnableAutoConfiguration trong spring.factories | Giữ các key cần thiết |
| Chỉ Boot 2.7 | Dùng AutoConfiguration.imports; key cũ vẫn được đọc nhưng đã deprecated | Giữ các key cần thiết |
| Boot 2.7 và Boot 3.x | Có thể liệt kê cùng class trong cả imports và spring.factories để hỗ trợ hai thế hệ; Boot 2.7 khử trùng lặp | Giữ các key cần thiết |
| Boot 3.x only | Chỉ dùng AutoConfiguration.imports cho auto-configuration | Giữ spring.factories cho extension point vẫn dùng nó |

### 7.1. Mẫu dual registration cho Boot 2.6, 2.7 và 3.x

Nếu một artifact thật sự hỗ trợ cả Boot 2.6 lẫn Boot 3.x, có thể giữ key auto-configuration cũ và bổ sung file imports.

`META-INF/spring.factories`:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.catalog.autoconfigure.CatalogAutoConfiguration

org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.catalog.CatalogEnvironmentPostProcessor
```

`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

Kết quả theo phiên bản:

- Boot 2.6 đọc entry auto-configuration trong `spring.factories`; file imports mới không được dùng để thay thế cơ chế cũ.
- Boot 2.7 đọc cả hai, vẫn hỗ trợ key cũ để tương thích ngược và khử trùng lặp candidate trùng.
- Boot 3.x lấy auto-configuration từ imports; key `EnableAutoConfiguration` trong `spring.factories` không còn được hỗ trợ. Entry EnvironmentPostProcessor vẫn được xử lý.

### 7.2. Dual registration không tự bảo đảm tương thích bytecode

Hai file đăng ký chỉ giải quyết **khả năng phát hiện class**. Chúng không bảo đảm code tương thích API, dependency hoặc Java baseline giữa các phiên bản.

Ví dụ, `@AutoConfiguration` được giới thiệu trong Spring Boot 2.7. Nếu một thư viện tuyên bố hỗ trợ Boot 2.6 nhưng code được biên dịch phụ thuộc vào annotation chỉ có từ Boot 2.7, việc thêm cả hai file đăng ký không tự làm annotation đó xuất hiện trong Boot 2.6.

Khi hỗ trợ nhiều phiên bản:

- Xác định rõ phiên bản Spring Boot thấp nhất.
- Chọn API có mặt trong baseline đó hoặc tách artifact/version nếu cần.
- Kiểm tra cả Java bytecode target và phiên bản Spring Framework đi kèm.
- Chạy consumer integration test trên từng dòng phiên bản được cam kết.
- Không chỉ kiểm tra rằng JAR chứa cả hai file.

### 7.3. Không xóa key khác khi chuyển auto-configuration

Giả sử file cũ có ba key:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.catalog.autoconfigure.CatalogAutoConfiguration

org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.catalog.CatalogEnvironmentPostProcessor

org.springframework.context.ApplicationListener=\
com.acme.catalog.CatalogStartupListener
```

Khi chuyển sang Boot 3:

1. Chuyển `CatalogAutoConfiguration` sang imports.
2. Giữ `EnvironmentPostProcessor` nếu vẫn dùng.
3. Giữ `ApplicationListener` nếu vẫn dùng.
4. Kiểm tra mỗi implementation còn phù hợp với API của phiên bản Spring Boot/Spring Framework mục tiêu.

## 8. Đóng gói JAR và xử lý resource trùng tên

Một lỗi thường gặp xuất hiện khi đóng gói thư viện hoặc ứng dụng bằng Maven Shade Plugin, Gradle Shadow Plugin hoặc công cụ tạo fat JAR.

Nhiều dependency có thể chứa file cùng tên:

- `META-INF/spring.factories`
- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nếu công cụ đóng gói chỉ giữ một resource cuối cùng thay vì merge đúng cách, một số extension implementation hoặc auto-configuration candidate có thể biến mất.

Cần phân biệt cách merge:

- `spring.factories` là file properties: các key và danh sách implementation từ nhiều JAR cần được merge theo ngữ nghĩa properties.
- `AutoConfiguration.imports` là danh sách dòng: khi tạo shaded JAR, cần append/merge các dòng từ nhiều dependency.

Spring Boot 2.7 Release Notes có ví dụ cấu hình `AppendingTransformer` cho file imports khi dùng Maven Shade Plugin, và cấu hình `append(...)` cho Gradle Shadow Plugin. Không nên giả định mọi plugin đóng gói tự xử lý các resource này đúng mặc định.

### 8.1. Kiểm tra resource trong JAR

Sau khi build:

```bash
mvn clean package
```

Liệt kê các resource:

```bash
jar tf target/catalog-compat-demo-1.0.0.jar
```

Tìm tối thiểu:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nếu dùng executable JAR của Spring Boot, các dependency có thể được đóng gói dưới `BOOT-INF/lib`. Khi kiểm tra một dependency JAR cụ thể, có thể giải nén nested JAR đó và kiểm tra resource bên trong.

### 8.2. Kiểm tra nội dung sau merge

Đừng chỉ xác nhận file tồn tại. Mở nội dung và kiểm tra:

- `spring.factories` có đủ các key mà thư viện yêu cầu không.
- Key có đúng tên interface đầy đủ không.
- Tên implementation có đúng package/class không.
- `AutoConfiguration.imports` có đầy đủ candidate, mỗi dòng một class không.
- Không còn tên class đã đổi package hoặc bị xóa.
- Các dependency JAR khác vẫn đóng góp resource của chúng sau khi shade.

Với một library JAR bình thường không shade dependency, mỗi dependency vẫn giữ resource riêng trên classpath; loader tổng hợp các resource. Vấn đề merge thường phát sinh khi gộp nhiều JAR thành một JAR duy nhất.

## 9. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế | Cách xử lý |
|---|---|---|
| Boot 3 đã xóa `spring.factories` | Chỉ key EnableAutoConfiguration bị loại bỏ cho auto-configuration registration | Kiểm tra từng key trong file |
| Tất cả extension point phải chuyển sang imports | Imports dành cho auto-configuration candidates | Xác định loader của extension point |
| EnvironmentPostProcessor phải chuyển sang imports | Boot 3.3 vẫn yêu cầu đăng ký trong spring.factories | Giữ key EnvironmentPostProcessor |
| ApplicationListener không còn được đăng ký qua spring.factories | Tài liệu Spring Boot vẫn hỗ trợ key ApplicationListener cho listener tự động | Giữ key nếu cần listener sớm |
| Thấy key tùy chỉnh trong spring.factories là class tự chạy | Loader phải gọi đúng factory type/key | Tìm code sử dụng SpringFactoriesLoader |
| Đặt auto-config trong cả hai file luôn gây đăng ký bean hai lần | Boot 2.7 khử trùng lặp candidate trùng; Boot 3 dùng imports cho auto-config | Dùng dual registration có chủ đích khi cần hỗ trợ phiên bản |
| Có imports là mọi bean chắc chắn được tạo | Auto-configuration vẫn chịu các condition | Kiểm tra Condition Evaluation Report |
| Xóa spring.factories là bước bắt buộc khi nâng Boot 3 | Có thể làm mất EnvironmentPostProcessor, listener hoặc SPI khác | Chỉ xóa key auto-config cũ khi không cần Boot 2.x |
| spring.factories là Java ServiceLoader | Hai cơ chế có format và loader khác nhau | Dùng đúng SpringFactoriesLoader hoặc ServiceLoader |
| File resource tồn tại trong source nghĩa là đã nằm trong JAR | Build/shading có thể bỏ hoặc ghi đè resource | Kiểm tra artifact sau package |

## 10. Quy trình migration an toàn

Khi nâng một thư viện từ Boot 2.x lên Boot 3.x:

1. Tìm toàn bộ file `META-INF/spring.factories` trong module và dependency do bạn quản lý.
2. Liệt kê từng key, không chỉ nhìn tên file.
3. Với key `org.springframework.boot.autoconfigure.EnableAutoConfiguration`, chuyển các class sang `AutoConfiguration.imports`.
4. Giữ các key như `EnvironmentPostProcessor`, `ApplicationListener` hoặc `FailureAnalyzer` nếu extension point đó còn được sử dụng trong phiên bản mục tiêu.
5. Nếu hỗ trợ Boot 2.7 và Boot 3, quyết định có cần dual registration hay không.
6. Nếu hỗ trợ Boot 2.6 trở về trước cùng Boot 3, giữ dual registration và kiểm tra API/bytecode compatibility.
7. Kiểm tra resource merge nếu dùng shade/shadow/fat JAR.
8. Build JAR và kiểm tra nội dung resource cuối.
9. Chạy ứng dụng consumer trên từng phiên bản Spring Boot được hỗ trợ.
10. Bật `--debug` khi cần xem auto-configuration candidate và condition report.

Có thể dùng tìm kiếm văn bản trong source:

```bash
rg -n "EnableAutoConfiguration|EnvironmentPostProcessor|ApplicationListener|FailureAnalyzer" .
```

Sau đó phân loại key theo mục đích. Đừng thay mọi dòng có chữ Spring bằng một file imports duy nhất.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Spring Boot 3 loại bỏ key nào trong `spring.factories`?

**Đáp án:** `org.springframework.boot.autoconfigure.EnableAutoConfiguration`, tức key dùng để đăng ký auto-configuration candidates.

**Câu 2.** File nào thay thế key đó?

**Đáp án:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, mỗi dòng ghi tên đầy đủ của một auto-configuration class.

**Câu 3.** Spring Boot 2.7 có còn đọc key auto-configuration cũ không?

**Đáp án:** Có. Boot 2.7 giữ hỗ trợ tương thích ngược nhưng đánh dấu cơ chế cũ là deprecated; nếu cùng class được liệt kê ở hai nơi thì candidate trùng được khử trùng lặp.

**Câu 4.** Trong Boot 3.3, EnvironmentPostProcessor đăng ký ở đâu?

**Đáp án:** Trong `META-INF/spring.factories`, với key `org.springframework.boot.env.EnvironmentPostProcessor`.

**Câu 5.** `SpringFactoriesLoader` dùng file nào?

**Đáp án:** `META-INF/spring.factories`; key là tên factory type và value là danh sách implementation.

**Câu 6.** Nếu khai báo một key SPI tự định nghĩa trong `spring.factories`, implementation có tự chạy không?

**Đáp án:** Không. Code phải gọi `SpringFactoriesLoader` cho đúng factory type hoặc có một loader riêng xử lý key đó.

**Câu 7.** Khi một thư viện hỗ trợ cả Boot 2.6 và Boot 3, chỉ thêm AutoConfiguration.imports đã đủ chưa?

**Đáp án:** Chưa. Boot 2.6 cần key `EnableAutoConfiguration` cũ; có thể dual-register cả hai vị trí. Đồng thời phải kiểm tra source/API/bytecode compatibility, vì hai file đăng ký không làm API mới xuất hiện trong phiên bản cũ.

**Câu 8.** Khi build shaded JAR, vì sao phải merge cả spring.factories và imports?

**Đáp án:** Nhiều dependency có thể đóng góp implementation/candidate. Nếu resource bị ghi đè, một số extension point hoặc auto-configuration có thể biến mất.

## 12. Ghi nhớ

- Thay đổi ở Boot 3 chỉ loại bỏ key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `spring.factories` để đăng ký auto-configuration.
- Boot 2.7 giới thiệu `AutoConfiguration.imports`, vẫn đọc key cũ để tương thích ngược và khử trùng lặp candidate.
- Boot 3.x dùng `AutoConfiguration.imports` cho auto-configuration candidates.
- `spring.factories` vẫn được dùng cho extension point khác, ví dụ `EnvironmentPostProcessor`, `ApplicationListener`, `FailureAnalyzer` và SPI do thư viện tự định nghĩa.
- `SpringFactoriesLoader` là cơ chế factory loading tổng quát của Spring Framework; key chỉ có tác dụng khi có loader xử lý nó.
- `AutoConfiguration.imports`, `spring.factories`, `@Import`, component scan và Java `ServiceLoader` là các cơ chế khác nhau.
- Khi migration, phân loại từng key trước khi xóa hoặc chuyển file.
- Kiểm tra resource trong JAR cuối và chạy consumer test trên các phiên bản được hỗ trợ.

### Tài liệu chính thức

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes)
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3.13 API — EnvironmentPostProcessor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html)
- [Spring Boot 3.3 — Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Framework 6.1 API — SpringFactoriesLoader](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/core/io/support/SpringFactoriesLoader.html)
