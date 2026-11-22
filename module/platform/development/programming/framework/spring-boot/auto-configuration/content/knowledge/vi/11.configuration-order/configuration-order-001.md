# Vì sao cấu hình tạo bean nền phải được xử lý trước cấu hình sử dụng bean đó?

> **Spring Boot Auto Configuration → Thứ tự cấu hình.** Bài học phân biệt thứ tự **xử lý các auto-configuration/đăng ký bean definition** với thứ tự **khởi tạo bean instance**, giải thích lúc nào sự phụ thuộc vào bean nền khiến thứ tự cấu hình trở nên quan trọng, và hướng dẫn khai báo, kiểm thử, chẩn đoán thứ tự bằng Spring Boot 3.x / Java 17+.

## 1. Bài toán: một bean nền phục vụ cho nhiều tính năng

Giả sử một thư viện tích hợp cung cấp:

- **CoreAutoConfiguration**: tạo bean nền `CoreClient` (quản lý kết nối, bộ mã hóa, cấu hình chung hoặc một dịch vụ hạ tầng).
- **FeatureAutoConfiguration**: chỉ đăng ký bean `FeatureService` khi trong context đã có `CoreClient`.
- **Ứng dụng**: có thể bật/tắt phần lõi, tự cung cấp bean hoặc chỉ muốn một vài tính năng.

Mô hình phụ thuộc:

~~~text
          CoreAutoConfiguration
                |
                v
       bean definition: CoreClient
                |
                v  (@ConditionalOnBean)
         FeatureAutoConfiguration
                |
                v
       bean definition: FeatureService
                |
                v
       FeatureService dùng CoreClient
~~~

Một cấu hình tiêu thụ có thể khai báo điều kiện:

~~~java
@AutoConfiguration
@ConditionalOnBean(CoreClient.class)
public class FeatureAutoConfiguration {
    // @Bean FeatureService...
}
~~~

`@ConditionalOnBean` **không chờ mọi cấu hình được duyệt xong** rồi mới quyết định. Điều kiện này dựa trên **các bean definition mà Spring đã xử lý đến thời điểm đánh giá**. Nếu cấu hình tạo `CoreClient` chưa được xử lý, điều kiện của `FeatureAutoConfiguration` có thể không match; khi đó bean tính năng bị bỏ qua dù lớp cấu hình nền sẽ được xử lý sau.

Bởi vậy, khi một auto-configuration **dùng điều kiện về sự tồn tại của bean được cấu hình khác cung cấp**, cần sắp xếp để **cấu hình cung cấp bean nền được xử lý trước**. Điều này giúp điều kiện nhìn thấy đầy đủ những definition nó phụ thuộc vào.

**Điểm cực kỳ quan trọng:** không phải mọi constructor injection đều cần ép thứ tự auto-configuration. Spring thường có thể tạo bean nền trước bean sử dụng nó **dựa trên đồ thị dependency**, ngay cả khi thứ tự khai báo các definition khác nhau. Vấn đề đặc trưng ở đây là **thời điểm đánh giá điều kiện và đăng ký bean definition**.

## 2. Hai loại “thứ tự” thường bị nhầm với nhau

| Giai đoạn | Spring Boot/Spring đang làm gì? | Thứ tự có tác dụng gì? | Công cụ liên quan |
| --- | --- | --- | --- |
| **Chọn và sắp xếp auto-configuration** | Tìm các cấu hình ứng viên rồi sắp xếp chúng để được áp dụng | Quyết định auto-configuration nào được xử lý trước | `@AutoConfiguration(before/after)`, `@AutoConfigureBefore`, `@AutoConfigureAfter`, `@AutoConfigureOrder` |
| **Xử lý điều kiện và đăng ký bean definitions** | Đọc metadata `@Configuration`, `@Bean`, `@Conditional...` và đăng ký định nghĩa các bean hợp lệ | Các điều kiện như `@ConditionalOnBean` / `@ConditionalOnMissingBean` thấy những definition đã được xử lý | Cấu hình có điều kiện, thứ tự auto-configuration |
| **Khởi tạo và nối các bean instances** | Spring tạo object, giải quyết constructor arguments, phụ thuộc, callback, lifecycle | Bean cần thiết cho dependency thường phải được tạo trước bean sử dụng nó | Constructor injection, `@DependsOn`, vòng đời bean |
| **Chạy logic ứng dụng** | `ApplicationRunner`, request handlers, scheduled jobs... sử dụng những bean đã sẵn sàng | Xác định thời điểm tính năng bắt đầu hoạt động | Lifecycle và thiết kế logic runtime |

Có thể hình dung:

~~~text
A. ĐỌC CẤU HÌNH VÀ ĐĂNG KÝ DEFINITION
   CoreAutoConfiguration -> đăng ký CoreClient
   FeatureAutoConfiguration -> kiểm tra CoreClient -> đăng ký FeatureService

B. KHỞI TẠO INSTANCE
   Spring tạo CoreClient khi FeatureService cần
   Spring tạo FeatureService với CoreClient đã được inject

C. SỬ DỤNG
   ApplicationRunner hoặc request gọi FeatureService
~~~

`@AutoConfiguration(after = CoreAutoConfiguration.class)` tác động đến **A**, không trực tiếp ép trình tự gọi constructor trong **B**. Spring Boot ghi rõ rằng thứ tự áp dụng các auto-configuration ảnh hưởng đến **thứ tự bean definitions được định nghĩa**; thời điểm tạo bean sau đó phụ thuộc vào các dependency của bean và `@DependsOn`.

## 3. Khi thứ tự sai gây ra hiện tượng gì?

### 3.1. @ConditionalOnBean: bean nền có thể chưa được nhìn thấy

Nếu `FeatureAutoConfiguration` được xét trước:

~~~text
1. FeatureAutoConfiguration được xử lý.
2. @ConditionalOnBean(CoreClient.class) kiểm tra: chưa có definition CoreClient.
3. Điều kiện KHÔNG MATCH -> FeatureService không được đăng ký.
4. CoreAutoConfiguration được xử lý và đăng ký CoreClient.
5. Spring không tự quay lại đăng ký FeatureService chỉ vì CoreClient đã xuất hiện sau.
~~~

Kết quả có thể là **CoreClient tồn tại nhưng FeatureService không tồn tại**. Cấu hình không nhất thiết gây crash; tính năng có thể đơn giản không xuất hiện vì điều kiện bị đánh giá quá sớm.

Nếu xử lý theo đúng quan hệ:

~~~text
1. CoreAutoConfiguration -> đăng ký CoreClient.
2. FeatureAutoConfiguration -> @ConditionalOnBean(CoreClient.class) MATCH.
3. FeatureAutoConfiguration -> đăng ký FeatureService.
4. Khi khởi tạo FeatureService, Spring cung cấp CoreClient.
~~~

Đây là lý do chủ yếu của thứ tự **cấu hình nền trước cấu hình sử dụng bean nền**.

### 3.2. @ConditionalOnMissingBean: cấu hình fallback có thể đăng ký nhầm

`@ConditionalOnMissingBean` còn nhạy cảm với thời điểm đánh giá. Ví dụ `FallbackAutoConfiguration` chỉ muốn tạo `CoreClient` mặc định khi không có cấu hình nào cung cấp bean phù hợp:

~~~java
@Bean
@ConditionalOnMissingBean(CoreClient.class)
CoreClient defaultCoreClient() {
    return new CoreClient();
}
~~~

Đây là **đoạn minh họa**: `CoreClient` cần được định nghĩa/import trong dự án tương ứng. Nếu một cấu hình khác định nghĩa `CoreClient` **sau** khi điều kiện trên đã được đánh giá, bean mặc định có thể được đăng ký dù ý định là nhường chỗ cho bean chuyên biệt. Tùy tên bean, type và cách inject, điều này có thể dẫn đến nhiều bean cùng type hoặc một bean bị chọn sai.

Cách tốt hơn: xác định **ai là nhà cung cấp bean thực**, ai là **fallback**, rồi sắp xếp các auto-configuration để điều kiện fallback quan sát được những bean cần ưu tiên trước nó. Trong starter, `@ConditionalOnMissingBean` cũng giúp nhường quyền cho bean do ứng dụng người dùng tự định nghĩa: Spring Boot xử lý cấu hình do người dùng cung cấp trước auto-configuration.

**Giới hạn quan trọng:** cấu hình được xếp sớm hơn **không bảo đảm nó tạo bean**. Nó vẫn có thể bị chặn bởi `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` hoặc lỗi thực thi. Thứ tự chỉ sửa quan hệ **đánh giá/đăng ký**, không tự đáp ứng điều kiện đã thiếu.

### 3.3. Trường hợp chỉ có constructor injection thì khác

Giả sử cả hai bean definitions đã tồn tại trong context, không có `@ConditionalOnBean` trên lớp tiêu thụ:

~~~java
@Bean
FeatureService featureService(CoreClient coreClient) {
    return new FeatureService(coreClient);
}
~~~

Khi tạo `FeatureService`, Spring biết cần `CoreClient` vì đó là tham số method `@Bean`. Nó sẽ resolve dependency, tạo `CoreClient` trước nếu cần, rồi mới tạo `FeatureService`. **Không bắt buộc** ép thứ tự auto-configuration chỉ để “constructor của CoreClient chạy trước”.

Đây là khác biệt giữa:
- **Bean definition có tồn tại để condition xét hay không**; và
- **Bean instance nào được tạo trước khi một instance khác cần nó**.

## 4. Khai báo thứ tự đúng bằng Spring Boot

Với Spring Boot 2.7+/3.x, ưu tiên `@AutoConfiguration` có thuộc tính `before` / `after`.

### 4.1. Cấu hình sử dụng đứng sau cấu hình nền

~~~java
@AutoConfiguration(after = CoreAutoConfiguration.class)
public class FeatureAutoConfiguration {
    // Bean phụ thuộc vào CoreClient
}
~~~

Ý nghĩa: **Nếu cả hai auto-configuration được tham gia xử lý**, Boot sắp xếp `FeatureAutoConfiguration` sau `CoreAutoConfiguration`. Đây là cách diễn đạt quan hệ “Feature cần Core đã được khai báo”.

Cách viết tương đương bằng annotation chuyên dụng:

~~~java
@AutoConfiguration
@AutoConfigureAfter(CoreAutoConfiguration.class)
public class FeatureAutoConfiguration {
}
~~~

Đây là **đoạn minh họa**, phải import `AutoConfiguration` / `AutoConfigureAfter` và có `CoreAutoConfiguration` tương ứng để biên dịch.

### 4.2. Khai báo từ phía cấu hình nền

~~~java
@AutoConfiguration(before = FeatureAutoConfiguration.class)
public class CoreAutoConfiguration {
}
~~~

Hoặc:

~~~java
@AutoConfiguration
@AutoConfigureBefore(FeatureAutoConfiguration.class)
public class CoreAutoConfiguration {
}
~~~

Cả hai nêu cùng quan hệ bằng hai hướng. **Không cần khai báo lặp cả before và after** nếu một quan hệ đã đủ rõ; giữ một nguồn diễn đạt tránh tạo ràng buộc dư thừa hoặc vòng thứ tự.

### 4.3. Tham chiếu lớp chưa muốn phụ thuộc trực tiếp

Có thể dùng `beforeName` / `afterName` với tên class đầy đủ:

~~~java
@AutoConfiguration(afterName = "com.vendor.core.CoreAutoConfiguration")
public class FeatureAutoConfiguration {
}
~~~

Lợi ích: không cần tham chiếu trực tiếp `Class` của auto-configuration tùy chọn khi biên dịch. Tên phải chính xác, bao gồm package. Với lớp lồng nhau, convention tên JVM có ký tự `$`.

### 4.4. @AutoConfigureOrder và @Order khác nhau thế nào?

- `@AutoConfigureOrder` cung cấp thứ tự chung cho **các auto-configuration**, hữu ích khi hai cấu hình không có quan hệ tham chiếu trực tiếp mà vẫn cần ưu tiên tương đối.
- `@Order` thường được dùng cho thứ tự nhiều bean cùng loại khi inject collection, các processor, aspect... tùy ngữ cảnh; **không thay thế** chỉ dẫn `before/after` để xếp các auto-configuration.
- Nếu có quan hệ rõ ràng “Feature cần bean nền do Core cung cấp”, `@AutoConfiguration(after = CoreAutoConfiguration.class)` dễ đọc hơn một con số order mơ hồ.

Cả thứ tự của các dòng trong `AutoConfiguration.imports` lẫn thứ tự tên tệp source không nên trở thành cơ chế điều khiển quan hệ nền–phụ thuộc. Hãy ghi ràng buộc tường minh.

### 4.5. @DependsOn giải quyết vấn đề khác

~~~java
@Bean
@DependsOn("coreClient")
FeatureService featureService(CoreClient coreClient) {
    return new FeatureService(coreClient);
}
~~~

Đây là **đoạn minh họa** cần các import và kiểu ứng dụng phù hợp. `@DependsOn("coreClient")` yêu cầu bean tên `coreClient` được **khởi tạo trước** `featureService`; nhưng:
- Không bắt buộc `CoreAutoConfiguration` phải được xử lý trước lúc một `@ConditionalOnBean` được đánh giá.
- Không tự đăng ký bean `coreClient` nếu bean này không tồn tại.
- Với constructor/method injection trực tiếp của `CoreClient` như trên, Spring đã biết quan hệ phụ thuộc từ tham số; `@DependsOn` thường là dư thừa.

Nên dùng `@DependsOn` khi thực sự có một quan hệ **khởi tạo** không biểu hiện qua tham số, chẳng hạn cần khởi tạo một hạ tầng trước bean có side effect. Không dùng nó để chữa điều kiện bean bị đánh giá quá sớm.

## 5. Dự án chạy được: chứng minh thứ tự definition, không nhầm thứ tự instance

Lab này dùng Java 17, Maven và Spring Boot 3.3.13. Có hai auto-configuration độc lập với component scan. Chúng được **liệt kê theo thứ tự ngược** trong tệp imports, nhưng ràng buộc `after` bảo đảm quan hệ xử lý đúng.

### 5.1. Cấu trúc dự án

~~~text
config-order-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── app/
        │       │   └── OrderDemoApplication.java
        │       └── autoconfigure/
        │           ├── CoreAutoConfiguration.java
        │           └── FeatureAutoConfiguration.java
        └── resources/
            └── META-INF/
                └── spring/
                    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Đặt application class trong `demo.app` và hai auto-configuration trong `demo.autoconfigure` để auto-configuration được nạp **qua imports**, không tình cờ xuất hiện do component scan của ứng dụng.

### 5.2. Tệp pom.xml

~~~xml
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
    <groupId>demo</groupId>
    <artifactId>config-order-demo</artifactId>
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
~~~

### 5.3. Tệp src/main/java/demo/autoconfigure/CoreAutoConfiguration.java

~~~java
package demo.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.core",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class CoreAutoConfiguration {

    @Bean
    public CoreClient coreClient() {
        return new CoreClient("core-ready");
    }

    public record CoreClient(String id) {}
}
~~~

`CoreClient` là kiểu bean nền. Ở đây nó là `record` Java 17 cho ngắn gọn. `demo.core.enabled` có chính sách **bật mặc định**; đặt `false` để bỏ qua toàn bộ `CoreAutoConfiguration`. Ví dụ không có việc kết nối mạng thật.

### 5.4. Tệp src/main/java/demo/autoconfigure/FeatureAutoConfiguration.java

~~~java
package demo.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = CoreAutoConfiguration.class)
@ConditionalOnBean(CoreAutoConfiguration.CoreClient.class)
public class FeatureAutoConfiguration {

    @Bean
    public FeatureService featureService(
            CoreAutoConfiguration.CoreClient coreClient) {
        return new FeatureService(coreClient);
    }

    public record FeatureService(
            CoreAutoConfiguration.CoreClient coreClient) {

        public String message() {
            return "feature uses " + coreClient.id();
        }
    }
}
~~~

Hai ý khác nhau cùng xuất hiện:
1. `after = CoreAutoConfiguration.class` bảo đảm cấu hình nền được xử lý **trước khi** điều kiện của Feature được đánh giá.
2. Tham số `CoreClient` trong `featureService(...)` bảo đảm khi tạo instance `FeatureService`, Spring có thể resolve bean nền.

Với `@ConditionalOnBean`, điều kiện kiểm tra **bean definition đã biết**, không gọi `new CoreClient(...)`. Do đó `after` giải quyết bài toán đăng ký definition; method injection giải quyết bài toán instance.

### 5.5. Tệp src/main/java/demo/app/OrderDemoApplication.java

~~~java
package demo.app;

import demo.autoconfigure.FeatureAutoConfiguration.FeatureService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> {
            boolean corePresent = context.containsBean("coreClient");
            boolean featurePresent = context.containsBean("featureService");

            System.out.println("coreBean=" + corePresent);
            System.out.println("featureBean=" + featurePresent);

            if (featurePresent) {
                FeatureService service = context.getBean(FeatureService.class);
                System.out.println(service.message());
            }
        };
    }
}
~~~

Từ package `demo.app`, `@SpringBootApplication` không component-scan package ngang cấp `demo.autoconfigure`. Hai auto-configuration phải được Boot lấy từ tệp imports, nên lab thể hiện chính cơ chế cần học.

### 5.6. Tệp đăng ký auto-configuration

Tạo đúng đường dẫn:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
demo.autoconfigure.FeatureAutoConfiguration
demo.autoconfigure.CoreAutoConfiguration
~~~

Cố tình đặt **Feature lên trước Core trong tệp** để minh họa: quan hệ chuẩn được xác định bằng `@AutoConfiguration(after = CoreAutoConfiguration.class)`, **không dựa vào thứ tự viết dòng**. Trong một starter thực tế, mỗi auto-configuration cần được liệt kê bằng tên class đầy đủ hợp lệ.

### 5.7. Đóng gói và chạy

Tại thư mục `config-order-demo`, cần JDK 17+ và Maven:

~~~bash
mvn -q -DskipTests package
java -jar target/config-order-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Ba dòng do chương trình in:

~~~text
coreBean=true
featureBean=true
feature uses core-ready
~~~

Kết luận: `CoreAutoConfiguration` có mặt và được xử lý đủ sớm, nên điều kiện của `FeatureAutoConfiguration` match; bean feature được đăng ký và sau đó có thể nhận dependency `CoreClient`.

### 5.8. Tắt hẳn cấu hình nền: thứ tự đúng vẫn không thể tạo ra bean vắng mặt

Chạy lại:

~~~bash
java -jar target/config-order-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.core.enabled=false
~~~

Hai dòng do chương trình in:

~~~text
coreBean=false
featureBean=false
~~~

Vì `@ConditionalOnProperty` không match, cấu hình nền không cung cấp bean. `FeatureAutoConfiguration` được xếp sau đúng thứ tự, nhưng `@ConditionalOnBean(CoreClient.class)` vẫn **không match**. Đó là kết quả đúng: **sắp xếp thứ tự không thay thế điều kiện cần thiết**.

Nếu khởi động với `--debug` và bật log bình thường, có thể đọc *Condition Evaluation Report* để kiểm tra vì sao từng auto-configuration match hoặc không match.

## 6. Kiểm thử thứ tự bằng ApplicationContextRunner

Chỉ chạy ứng dụng một lần chưa đủ bảo vệ starter trước thay đổi sau này. Có thể kiểm tra cả trường hợp cấu hình nền được bật và bị tắt.

Thêm vào phần `<dependencies>` của `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo tệp:

~~~text
src/test/java/demo/app/OrderAutoConfigurationTest.java
~~~

Nội dung:

~~~java
package demo.app;

import demo.autoconfigure.CoreAutoConfiguration;
import demo.autoconfigure.FeatureAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class OrderAutoConfigurationTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    FeatureAutoConfiguration.class,
                    CoreAutoConfiguration.class
            ));

    @Test
    void featureIsAvailableWhenCoreIsAvailable() {
        runner.run(context -> {
            assertThat(context).hasBean("coreClient");
            assertThat(context).hasBean("featureService");
            var feature = context.getBean(
                    FeatureAutoConfiguration.FeatureService.class
            );
            assertThat(feature.message()).isEqualTo("feature uses core-ready");
        });
    }

    @Test
    void featureIsSkippedWhenCoreIsDisabled() {
        runner.withPropertyValues("demo.core.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean("coreClient");
                    assertThat(context).doesNotHaveBean("featureService");
                });
    }
}
~~~

Thứ tự truyền vào `AutoConfigurations.of(...)` được cố tình liệt kê Feature trước Core; ràng buộc `after` vẫn chỉ ra quan hệ xử lý. Chạy:

~~~bash
mvn test
~~~

Kỳ vọng **2 test PASS**. Test kiểm tra cả hệ quả đúng của thứ tự và trường hợp điều kiện nền thực sự bị tắt. Khi viết starter phức tạp, nên mở rộng test để kiểm tra người dùng tự đăng ký bean, chế độ fallback, thiếu dependency trên classpath và thay đổi profile nếu đó là những hợp đồng của starter.

## 7. Phân biệt các công cụ bằng tình huống thực tế

| Nhu cầu | Cơ chế nên dùng | Vì sao |
| --- | --- | --- |
| Auto-configuration tính năng chỉ match nếu auto-configuration nền đã đăng ký bean | `@AutoConfiguration(after = CoreAutoConfiguration.class)` | Sắp xếp thứ tự áp dụng cấu hình trước khi kiểm tra `@ConditionalOnBean` |
| Cấu hình nền cần đứng trước một cấu hình cụ thể | `@AutoConfiguration(before = FeatureAutoConfiguration.class)` | Diễn đạt cùng quan hệ từ phía nền |
| Cấu hình không muốn phụ thuộc trực tiếp vào class auto-config tùy chọn | `afterName` / `beforeName` | Biểu diễn quan hệ bằng tên class đầy đủ |
| Chọn thứ tự tương đối cho auto-config độc lập, không có liên hệ trực tiếp | `@AutoConfigureOrder` | Dùng thứ tự auto-configuration |
| Bean B cần object A làm tham số để tạo | Constructor injection hoặc tham số `@Bean` | Dependency graph hướng dẫn Spring tạo A khi B cần |
| Bean B cần một bean A được khởi tạo trước dù không inject A | `@DependsOn("a")` | Điều khiển thứ tự **khởi tạo instance** |
| Muốn cố định thứ tự khi inject nhiều strategy vào một danh sách | `@Order` / `Ordered` tùy ngữ cảnh | Sắp xếp các phần tử được chọn, không thay ràng buộc auto-config |
| Muốn chỉ tạo bean mặc định nếu người dùng chưa cung cấp bean | `@ConditionalOnMissingBean` | Đăng ký fallback dựa trên bean definitions đã được xử lý |
| Muốn chỉ kích hoạt tính năng khi thư viện có trên classpath | `@ConditionalOnClass` | Kiểm tra classpath; không giải quyết thứ tự hoặc tạo dependency |

**Quy tắc thiết kế:** chọn đúng tầng cần sắp xếp. Auto-config ordering nhằm đảm bảo **definition/condition nhìn thấy nhau**; dependency injection và `@DependsOn` điều khiển **lúc tạo object**.

## 8. Điều kiện không match và lỗi runtime: cách đọc dấu hiệu

### Trường hợp A — Core tồn tại nhưng Feature vắng

- **Triệu chứng:** `CoreClient` có trong context; `FeatureService` không có.
- **Điều tra:** condition report của `FeatureAutoConfiguration` có ghi `@ConditionalOnBean` không match không? Auto-configuration Feature có được import không?
- **Nguyên nhân có thể:** Feature được xét trước khi Core đăng ký definition; điều kiện khác bị chặn; sai tên/type bean.
- **Cách sửa có bằng chứng:** nếu quan hệ xử lý là nguyên nhân, thêm `@AutoConfiguration(after=CoreAutoConfiguration.class)` hoặc `@AutoConfigureAfter`, rồi kiểm thử lại hai trạng thái. Không thêm `@DependsOn` để sửa một điều kiện đã bị bỏ qua.

### Trường hợp B — Core không tồn tại, Feature không tồn tại

- **Triệu chứng:** cả hai bean đều vắng.
- **Điều tra:** `CoreAutoConfiguration` có thực sự được liệt kê trong `AutoConfiguration.imports` không? Điều kiện classpath, property hoặc một bean có sẵn đã khiến Core bỏ qua không?
- **Cách sửa:** làm rõ hợp đồng của phần lõi và cung cấp dependency/property phù hợp. **Thứ tự đúng không thể tạo bean mà cấu hình nền đã bị điều kiện loại bỏ**.

### Trường hợp C — Context báo UnsatisfiedDependencyException

- **Triệu chứng:** bean yêu cầu `CoreClient` bắt buộc nhưng không có bean thỏa mãn, dẫn tới lỗi trong quá trình khởi tạo.
- **Điều tra:** phân biệt **bean definition thực sự thiếu** với **định nghĩa tồn tại nhưng không tạo được**. Xem chuỗi `Caused by` và nguyên nhân từ condition report.
- **Cách sửa:** bổ sung/cho phép bean nền, dùng điều kiện để bỏ qua đúng chức năng tùy chọn, hoặc sửa cấu hình inject. Thứ tự auto-config chỉ giúp nếu vấn đề là **thứ tự xử lý**.

### Trường hợp D — Circular dependency (vòng phụ thuộc)

~~~text
ServiceA -> cần ServiceB
ServiceB -> cần ServiceA
~~~

Đây là vấn đề **đồ thị phụ thuộc giữa các bean instances**. Ép `@AutoConfiguration(before/after)` hoặc đổi thứ tự tệp imports **không làm mất vòng phụ thuộc**. Cần tách trách nhiệm, loại quan hệ hai chiều hoặc thiết kế lại cách kết nối. Các biện pháp trì hoãn như `@Lazy` chỉ nên được xem xét với lý do rõ ràng, không dùng để che một thiết kế vòng.

### Trường hợp E — Hai bean cùng type và fallback gây ambiguity

- **Triệu chứng:** khi inject theo type có nhiều candidate, Spring báo lỗi không chọn được bean phù hợp.
- **Điều tra:** ai đăng ký bean mặc định, ai đăng ký bean chuyên biệt, `@ConditionalOnMissingBean` có được đánh giá quá sớm không?
- **Cách sửa:** sửa quan hệ thứ tự giữa các auto-config, sử dụng condition chính xác để fallback nhường cho bean phù hợp, và dùng `@Primary`/`@Qualifier` khi đó thực sự là thiết kế có nhiều bean. Không chọn một bean tùy ý để che nguồn gốc duplicate.

## 9. Chẩn đoán thứ tự theo một quy trình có thể lặp lại

1. **Vẽ quan hệ phụ thuộc giữa cấu hình**: “Feature muốn dùng bean gì; Core nào chịu trách nhiệm đăng ký bean đó; Feature dùng điều kiện `@ConditionalOnBean` hay chỉ inject?”
2. **Đọc các auto-configuration thực sự được import**: với Spring Boot 3.x, kiểm tra `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` trong JAR/starter. Một tên class sai hoặc tệp thiếu nghĩa là Boot không biết cấu hình đó.
3. **Xem điều kiện**: thử `--debug` để có Condition Evaluation Report; với Actuator đã bật và expose an toàn, có thể xem endpoint `/actuator/conditions`. Tìm positive/negative match của Core và Feature.
4. **Đọc giá trị hiệu lực của Environment và classpath**: `@ConditionalOnClass`, `@ConditionalOnProperty` và `@ConditionalOnMissingBean` có thể làm bean nền vắng dù cấu hình đã đứng trước.
5. **Kiểm tra ràng buộc `after/before`**: dùng type nếu cả hai cấu hình có mặt khi biên dịch; dùng `afterName/beforeName` nếu cần tham chiếu tên. Tránh tạo vòng ràng buộc (“A sau B” và “B sau A”).
6. **Tách nghĩa của lỗi**: không match → có thể do definition/order; injection thất bại → không có bean thỏa mãn; cycle → đồ thị instance; method runtime lỗi → kiểm tra logic bean, không quy hết cho thứ tự.
7. **Viết test xác nhận**: dùng `ApplicationContextRunner` để assert bean có/vắng trong điều kiện rõ ràng. Không chỉ kiểm tra log “started”.

Khi một bean đáng ra không được tạo, negative match có thể là **hành vi đúng**. Việc chẩn đoán phải xuất phát từ hợp đồng của module: Feature là tính năng tùy chọn hay bắt buộc? Có cho phép người dùng ghi đè bean nền không?

## 10. Lỗi thường gặp khi thiết kế thứ tự cấu hình

1. **“Tất cả bean phải khởi tạo theo thứ tự khai báo configuration.”** Sai: Spring chủ yếu dựa trên đồ thị dependency khi tạo instance; thứ tự auto-config tác động đến definition/condition.
2. **“@DependsOn sửa được @ConditionalOnBean không match.”** Sai: `@DependsOn` điều khiển initialization sau khi definition tồn tại; nó không làm một điều kiện bị đánh giá sớm trở thành match.
3. **“Cứ đặt Core ở dòng đầu AutoConfiguration.imports.”** Mong manh: cần quan hệ `before/after` rõ ràng, không phụ thuộc thứ tự viết trong tệp.
4. **“@Order và @AutoConfigureOrder là cùng cách viết.”** Không nên tráo đổi tùy tiện; mục tiêu ordering khác nhau. Khi có quan hệ Core–Feature, ưu tiên `@AutoConfiguration(after=...)`.
5. **“Nếu xếp Core trước, Feature chắc chắn sẽ có.”** Sai: Core có thể bị `@ConditionalOnProperty` hoặc `@ConditionalOnClass` loại, hoặc bean của Core được thay đổi do điều kiện khác.
6. **“@ConditionalOnMissingBean luôn nhìn được bean sẽ được khai báo ở bất kỳ cấu hình nào về sau.”** Sai: chỉ những definition đã được xử lý mới ảnh hưởng đến condition ở thời điểm đánh giá.
7. **“Constructor injection thất bại thì chỉ cần @AutoConfigureAfter.”** Không hẳn: phải xác nhận bean dependency có definition, không bị condition loại, không sai type/qualifier và có thể tạo thành công.
8. **“Vòng phụ thuộc có thể chữa bằng thứ tự cấu hình.”** Sai: phải sửa đồ thị runtime.
9. **“Tên bean giống nhau thì điều kiện type sẽ luôn giống nhau.”** Sai: `@ConditionalOnBean` có thể kiểm tra theo type hoặc name; type đủ cụ thể và return type của method `@Bean` rất quan trọng.
10. **“Component scan tự tìm mọi lớp @AutoConfiguration.”** Với starter Spring Boot 3.x, phải dùng cơ chế imports chuẩn; cấu hình của thư viện cần tránh bị component scan tình cờ nạp như configuration thông thường.

## 11. Tự kiểm tra

**Câu 1.** Feature chứa `@ConditionalOnBean(CoreClient.class)`; Core cung cấp CoreClient nhưng được xét sau Feature. Tại sao Feature có thể không xuất hiện?  
**Đáp án:** Điều kiện kiểm tra bean definitions đã được xử lý đến thời điểm đó; Core chưa đăng ký definition, nên Feature có thể bị loại và không tự được xét lại.

**Câu 2.** Annotation nào thể hiện rõ “Feature phải được áp dụng sau Core”?  
**Đáp án:** `@AutoConfiguration(after = CoreAutoConfiguration.class)` hoặc `@AutoConfigureAfter(CoreAutoConfiguration.class)` trên Feature.

**Câu 3.** Feature nhận CoreClient qua constructor nhưng không có `@ConditionalOnBean`. Có nhất thiết phải ép thứ tự auto-configuration để CoreClient được tạo trước không?  
**Đáp án:** Không nhất thiết. Khi các definitions đều tồn tại, Spring giải quyết dependency và tạo bean nền trước khi tạo bean tiêu thụ.

**Câu 4.** `@DependsOn("coreClient")` làm gì?  
**Đáp án:** Yêu cầu bean `coreClient` được khởi tạo trước bean khai báo `@DependsOn`; không khiến auto-configuration khác được đăng ký hoặc condition bị loại được xét lại.

**Câu 5.** Core bị tắt bởi `demo.core.enabled=false`. Thêm `after=CoreAutoConfiguration.class` có bảo đảm FeatureService xuất hiện không?  
**Đáp án:** Không. Thứ tự có thể đúng nhưng điều kiện `@ConditionalOnBean` vẫn không match vì CoreClient không có.

**Câu 6.** `@ConditionalOnMissingBean` của fallback nhìn được một bean được khai báo trong auto-configuration sẽ chỉ được xử lý sau đó không?  
**Đáp án:** Không bảo đảm. Điều kiện dựa trên các bean definitions đã được xử lý, nên cần thiết kế thứ tự phù hợp.

## 12. Kết luận và tài liệu đối chiếu

**Điều cần nhớ:** Trong Spring Boot Auto Configuration, “cấu hình nền phải được xử lý trước cấu hình sử dụng bean nền” đặc biệt quan trọng khi **cấu hình sử dụng kiểm tra sự tồn tại hoặc vắng mặt của bean để quyết định có đăng ký hay không**. Thứ tự này bảo đảm điều kiện được đánh giá trên những bean definitions cần thiết. Đến khi tạo instance, Spring lại dùng **dependency injection và lifecycle** để xác định thứ tự tạo object.

Có thể ghi nhớ bằng hai dòng:

~~~text
@AutoConfiguration(after = Core...) -> thứ tự XỬ LÝ CẤU HÌNH / ĐĂNG KÝ DEFINITION
constructor injection, @DependsOn  -> thứ tự KHỞI TẠO CÁC INSTANCE
~~~

Tài liệu chính thức:
- [Spring Boot — Creating Your Own Auto-configuration: Ordering Auto-configurations](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.condition-annotations)
- [Spring Boot 3.3.13 — @AutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3.13 — @AutoConfigureBefore Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html)
- [Spring Boot — Bean Conditions and @ConditionalOnBean/@ConditionalOnMissingBean](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Framework — @DependsOn Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/DependsOn.html)