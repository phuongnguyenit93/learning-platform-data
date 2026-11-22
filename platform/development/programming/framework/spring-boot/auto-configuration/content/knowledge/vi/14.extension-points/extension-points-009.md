# Phân biệt mở rộng qua API công khai với phụ thuộc vào lớp nội bộ của framework

## 1. Vì sao phải phân biệt?

Spring Framework và Spring Boot cung cấp nhiều cách mở rộng đã được thiết kế để ứng dụng sử dụng: interface, annotation, callback, event, builder, customizer và cơ chế đăng ký cấu hình. Bên cạnh đó, framework có các lớp phục vụ triển khai nội bộ như parser, resolver, registry, selector, cache và proxy factory.

Hai nhóm có thể cùng nằm dưới package `org.springframework`. Một số class nội bộ còn có modifier `public`. Vì vậy, **import được một class không chứng minh nó là API mở rộng được hỗ trợ**.

Khi code dựa vào implementation detail, nâng cấp Spring Boot hoặc Spring Framework có thể làm hỏng ứng dụng dù contract công khai vẫn hoạt động. Framework có thể đổi package, constructor, field, thứ tự gọi callback, cấu trúc `BeanDefinition` hoặc thuật toán xử lý annotation. Những chi tiết đó không nhất thiết phải giữ tương thích cho code bên ngoài.

Mục tiêu là biết cách chọn extension point được tài liệu hóa, đúng lifecycle và có thể kiểm thử độc lập với cách framework triển khai bên trong.

## 2. API, SPI và implementation detail

**API (Application Programming Interface)** là bề mặt mà ứng dụng gọi hoặc cấu hình. Ví dụ: `ApplicationContext.getBean(...)`, `RestClient.Builder` và `@ConfigurationProperties`.

**SPI (Service Provider Interface)** là hợp đồng mà ứng dụng hoặc thư viện khác triển khai để framework gọi ngược lại. Ví dụ: `BeanPostProcessor`, `ApplicationContextInitializer` và `RestClientCustomizer`.

Khác biệt chủ yếu nằm ở hướng gọi:

- API: code ứng dụng gọi framework.
- SPI: framework gọi implementation do ứng dụng cung cấp.

**Implementation detail** là cách framework thực hiện contract bên trong. Ví dụ: parser phân tích annotation, registry lưu bean definitions, comparator sắp thứ tự, cache giữ metadata hoặc proxy factory tạo đối tượng bao bọc. Những class này có thể thay đổi khi framework tái cấu trúc.

### 2.1. Cách nhận diện API/SPI được hỗ trợ

Trước khi phụ thuộc vào một type, hãy kiểm tra:

1. **Reference documentation:** tài liệu có hướng dẫn ứng dụng triển khai hoặc sử dụng type đó như một extension point không?
2. **Javadoc:** callback, lifecycle, thứ tự, phạm vi và cách đăng ký có được mô tả rõ không?
3. **Registration mechanism:** có cơ chế chính thức như bean trong ApplicationContext, `AutoConfiguration.imports`, event listener hay builder customizer không?
4. **Examples and tests:** tài liệu hoặc test chính thức có sử dụng contract đó theo cách ứng dụng có thể lặp lại không?
5. **Version information:** xem `@since`, `@Deprecated`, `forRemoval`, release notes và migration guide.
6. **Internal marker:** package hoặc Javadoc có ghi rõ internal, implementation, do not use hoặc không hỗ trợ subclass không?
7. **Reflection:** code có phải truy cập field private, method không được công bố, tên bean nội bộ hoặc thứ tự xử lý không được bảo đảm không?

Một interface có callback được tài liệu hóa và registration path rõ ràng là dấu hiệu tốt của SPI. Một parser nội bộ không trở thành SPI chỉ vì nó có thể được import.

### 2.2. Modifier public không phải lời hứa tương thích

Modifier `public` chỉ quy định khả năng truy cập theo Java. Nó không tự khẳng định class đó dành cho ứng dụng mở rộng.

Class public có thể được dùng để framework chia sẻ implementation giữa các module, để test/debug hoặc để tích hợp nội bộ. Hãy tìm tài liệu nói rõ cách ứng dụng nên sử dụng type đó. Không kết luận chỉ từ package, modifier hoặc việc IDE gợi ý import.

## 3. Những extension point công khai thường gặp

| Nhu cầu | Contract nên xem trước | Lifecycle |
| --- | --- | --- |
| Khởi tạo context trước refresh | `ApplicationContextInitializer` | Trước khi context refresh |
| Chỉnh bean definitions/metadata | `BeanFactoryPostProcessor` hoặc `BeanDefinitionRegistryPostProcessor` | Sau khi nạp metadata, trước khi tạo phần lớn bean |
| Chỉnh hoặc wrap bean instance | `BeanPostProcessor` | Trong quá trình khởi tạo bean |
| Lắng nghe event | `ApplicationListener` hoặc `@EventListener` | Khi event được publish |
| Chọn cấu hình cần import | `ImportSelector` hoặc `DeferredImportSelector` | Khi Spring xử lý configuration classes |
| Tùy chỉnh builder của Boot | Customizer SPI được Boot công bố | Trong pipeline tạo thành phần |
| Cung cấp bean mặc định có thể thay thế | `@AutoConfiguration`, `@Bean`, `@ConditionalOnMissingBean` | Khi Boot đăng ký auto-configuration |
| Công bố cấu hình thư viện | `@ConfigurationProperties` | Khi binding properties |

Đây là các contract được tài liệu hóa, không có nghĩa tất cả đều là lựa chọn đầu tiên cho mọi bài toán. Hãy chọn hook có phạm vi nhỏ nhất và đúng giai đoạn nhất.

### 3.1. Ưu tiên customizer cấp cao khi có

Spring Boot 3.5 công bố một số callback cụ thể:

- `org.springframework.boot.web.client.RestClientCustomizer` tùy chỉnh `RestClient.Builder`.
- `org.springframework.boot.web.client.RestTemplateCustomizer` tùy chỉnh `RestTemplate`.
- `org.springframework.boot.web.server.WebServerFactoryCustomizer` tùy chỉnh web server factory trước khi server khởi động.

Ví dụ:

```java
@Bean
RestClientCustomizer applicationHeader() {
    return builder -> builder.defaultHeader("X-Application", "catalog");
}
```

Customizer chỉ được áp dụng trên những builder đi qua pipeline có gọi nó. Nếu tự dùng `RestClient.create()`, ứng dụng bỏ qua auto-configuration và customizer của Boot. `RestClient.Builder` là đối tượng có trạng thái, nên thay đổi builder ảnh hưởng các client được tạo sau đó từ builder ấy.

Nếu có hook cấp cao đúng mục tiêu, dùng hook đó thường ít rủi ro hơn việc thay cả bean hoặc can thiệp container.

### 3.2. Auto-configuration là contract công khai

Khi phát triển starter, dùng annotation và cơ chế đăng ký được Spring Boot công bố:

```java
@AutoConfiguration
@ConditionalOnClass(ExternalClient.class)
public class ExternalClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ExternalClient.class)
    ExternalClient externalClient(ExternalClientProperties properties) {
        return new ExternalClient(properties.getEndpoint());
    }
}
```

`ExternalClient` và `ExternalClientProperties` là kiểu giả định của thư viện ví dụ.

Trong JAR starter, đăng ký auto-configuration trong file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng là tên đầy đủ của một class auto-configuration. Đây là registration mechanism được tài liệu Spring Boot hướng dẫn. Nếu cần sắp thứ tự, dùng `before`/`after` trên `@AutoConfiguration` hoặc annotation thứ tự tương ứng. Không dựa vào thứ tự scan classpath hay vị trí class trong JAR.

## 4. Hiểu đúng lifecycle của các SPI nền tảng

### 4.1. BeanPostProcessor: xử lý bean instance

`BeanPostProcessor` nhận callback khi bean instance được tạo. Nó có thể kiểm tra bean, bổ sung hành vi hoặc trả về wrapper/proxy.

- `postProcessBeforeInitialization` chạy trước các callback initialization như `afterPropertiesSet()` hoặc init method.
- `postProcessAfterInitialization` chạy sau các callback initialization.
- `ApplicationContext` tự phát hiện bean triển khai BPP.
- BPP thuộc về từng container; BPP ở context cha không tự động xử lý bean được tạo trong context con.

BPP được tạo rất sớm để xử lý các bean khác. Khi đăng ký bằng `@Bean`, nên dùng phương thức `static` và tránh dependency không cần thiết. Nếu BPP kéo theo việc khởi tạo sớm các bean khác, chúng có thể không được tất cả post-processors, ví dụ AOP auto-proxying, xử lý đầy đủ.

BPP có phạm vi rộng vì được gọi cho nhiều bean. Nếu chỉ muốn cấu hình một builder cụ thể, customizer chuyên biệt thường phù hợp hơn.

### 4.2. BeanFactoryPostProcessor: xử lý bean definition metadata

`BeanFactoryPostProcessor` làm việc với metadata cấu hình bean như `BeanDefinition` trước khi phần lớn bean instance được tạo. Dùng nó khi thực sự cần điều chỉnh metadata hoặc property values ở cấp container.

Không gọi `beanFactory.getBean(...)` bên trong BFPP để lấy instance rồi chỉnh object. Việc đó tạo bean quá sớm, có thể bỏ qua post-processing bình thường và gây lỗi lifecycle.

`BeanDefinitionRegistryPostProcessor` là SPI mở rộng cho trường hợp cần đăng ký hoặc sửa bean definitions ở cấp registry. Đây là hook mức thấp, chỉ dùng khi annotation, auto-configuration và bean factory method không đáp ứng được.

### 4.3. ApplicationContextInitializer: bootstrap trước refresh

`ApplicationContextInitializer` nhận `ConfigurableApplicationContext` trước khi context được refresh. Use case được tài liệu mô tả gồm đăng ký PropertySource hoặc kích hoạt profile theo cách lập trình.

Đây là hook cho bootstrap sớm. Nếu chỉ cần cấu hình giá trị, `application.yml` hoặc cơ chế externalized configuration thường đơn giản hơn. Tránh khởi tạo bean nghiệp vụ trong initializer khi context chưa hoàn tất lifecycle.

### 4.4. ApplicationListener và event

`ApplicationListener<E extends ApplicationEvent>` là contract nhận event; `@EventListener` cho phép khai báo listener bằng method. Dùng khi cần phản ứng với event có ý nghĩa công khai trong lifecycle hoặc domain.

Không dựa vào event nội bộ chỉ tình cờ được publish khi startup nếu tài liệu không cam kết nó là contract. Một event public vẫn cần được đọc tài liệu để hiểu thời điểm, thứ tự và phạm vi phát.

### 4.5. ImportSelector và DeferredImportSelector

Hai SPI này cho phép lựa chọn cấu hình cần import trong lúc Spring xử lý configuration classes. Chúng phù hợp khi thư viện có yêu cầu import động phức tạp hơn annotation condition thông thường.

Với auto-configuration Spring Boot, bắt đầu từ `@AutoConfiguration`, `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` và `AutoConfiguration.imports`. Chỉ viết selector tùy biến khi có yêu cầu thực sự.

## 5. Internal class và phụ thuộc mong manh

### 5.1. Dấu hiệu thường gặp

Implementation detail có thể xuất hiện dưới các dạng:

- Class trong package `internal` hoặc được Javadoc ghi rõ là internal.
- Parser, resolver, registry, selector hoặc processor cụ thể mà framework dùng để thực thi annotation.
- Field private/protected không được công bố như extension contract.
- Constructor chỉ phục vụ framework tạo instance.
- Thứ tự gọi method hoặc tên bean không được tài liệu cam kết.
- Cấu trúc `BeanDefinition` cụ thể mà framework tình cờ tạo ra cho một annotation.
- Proxy class, CGLIB enhancer, bytecode, reflection hoặc cache nội bộ.
- Log/stack trace được dùng như giao thức điều khiển.

Ví dụ, `ConfigurationClassParser` và `ConfigurationClassPostProcessor` là các thành phần trong quy trình xử lý cấu hình của Spring. Chúng giúp framework diễn giải `@Configuration`, nhưng không phải lựa chọn mặc định để ứng dụng tự xây logic mở rộng auto-configuration. Dùng `@AutoConfiguration`, `@Import`, selector SPI hoặc condition công khai phù hợp.

Không phân loại chỉ theo tên package. Một số package `support` chứa API có tài liệu, trong khi một class public vẫn có thể là infrastructure. Đánh giá từng type theo contract và hướng dẫn chính thức.

### 5.2. Ví dụ phụ thuộc nội bộ không nên làm

```java
// Anti-pattern: phụ thuộc implementation nội bộ
Class<?> parser = Class.forName(
    "org.springframework.context.annotation.ConfigurationClassParser"
);

// Sau đó dùng reflection để đọc field private hoặc gọi method nội bộ.
```

Không có contract được hỗ trợ để ứng dụng đọc trạng thái parser theo cách này. Code có thể hỏng khi package, field, module access hoặc thuật toán thay đổi.

Một dạng khác là subclass class infrastructure để override method protected không được tài liệu hóa như extension hook. Khi framework đổi constructor hoặc luồng gọi, subclass có thể không còn hoạt động.

### 5.3. Vì sao reflection đặc biệt rủi ro?

Reflection cho phép truy cập những thành phần mà code Java thông thường không thể gọi trực tiếp. Từ Java 9, module system có thể giới hạn truy cập sâu; các cờ như `--add-opens` làm triển khai phụ thuộc thêm vào runtime configuration.

Ngay cả khi reflection chạy hôm nay, nó không tạo cam kết tương thích cho field hoặc method private. Tương tự, tên bean nội bộ có thể đổi khi auto-configuration được tái cấu trúc. Nếu tài liệu cung cấp interface, type hoặc qualifier công khai, hãy inject theo contract đó.

## 6. Ví dụ runnable: BeanPostProcessor công khai

Ví dụ dùng **Java 17 và Spring Boot 3.5.0**. Bean triển khai interface `GreetingService` được đánh dấu `@Traceable`. BPP công khai kiểm tra annotation và wrap bean bằng JDK dynamic proxy. Test xác nhận bean đã được wrap và method vẫn delegate tới implementation.

Đây là ví dụ học SPI. Trong ứng dụng thật, nếu mục tiêu là tracing/metrics cho method, hãy đánh giá Spring AOP hoặc Micrometer Observation trước khi tự viết proxy. BPP tác động ở cấp container nên cần hiểu lifecycle.

### Cấu trúc

```text
public-spi-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── PublicExtensionPointTest.java
```

### Tệp `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>public-spi-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

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
</project>
```

### Tệp `src/test/java/example/PublicExtensionPointTest.java`

```java
package example;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class PublicExtensionPointTest {

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Traceable {}

    interface GreetingService {
        String greet(String name);
    }

    @Traceable
    static class DefaultGreetingService implements GreetingService {
        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    static class TraceableBeanPostProcessor implements BeanPostProcessor {

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {

            if (!(bean instanceof GreetingService)
                    || !bean.getClass().isAnnotationPresent(Traceable.class)) {
                return bean;
            }

            return Proxy.newProxyInstance(
                bean.getClass().getClassLoader(),
                new Class<?>[] { GreetingService.class },
                (proxy, method, args) -> {
                    try {
                        return method.invoke(bean, args);
                    }
                    catch (InvocationTargetException exception) {
                        throw exception.getCause();
                    }
                }
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SampleConfiguration {

        // BPP được phát hiện sớm: static factory, không có dependency.
        @Bean
        static BeanPostProcessor traceableBeanPostProcessor() {
            return new TraceableBeanPostProcessor();
        }

        @Bean
        GreetingService greetingService() {
            return new DefaultGreetingService();
        }
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(SampleConfiguration.class);

    @Test
    void publicBeanPostProcessorWrapsTheSelectedBean() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);

            GreetingService service = context.getBean(GreetingService.class);

            assertThat(Proxy.isProxyClass(service.getClass())).isTrue();
            assertThat(service.greet("Mai")).isEqualTo("Hello, Mai");
        });
    }
}
```

### Chạy và kết quả

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
java -version
mvn test
```

**Kết quả mong đợi:** một test JUnit pass và Maven kết thúc `BUILD SUCCESS` nếu dependency tải thành công. Code không gọi `System.out.println` nên không có stdout nghiệp vụ cố định.

Vì sao đây là mở rộng qua contract:

- Code triển khai `BeanPostProcessor`, interface Spring Framework công bố và tài liệu hóa.
- Context tự phát hiện BPP theo cơ chế chuẩn; không đọc registry nội bộ.
- BPP chỉ dựa vào interface `GreetingService` và annotation `Traceable` do ứng dụng sở hữu.
- `postProcessAfterInitialization` là callback công khai; không cần truy cập field private hoặc subclass parser.
- Proxy triển khai `GreetingService`, vì vậy consumer nên inject interface thay vì concrete class `DefaultGreetingService`.
- Phương thức đăng ký BPP là `static` và không có dependency để tránh khởi tạo sớm các bean không cần thiết.

Ví dụ dùng JDK proxy nên proxy chỉ expose interface `GreetingService`. Consumer inject theo concrete class có thể không tương thích với proxy. Đây là giới hạn của cách wrap, không phải lỗi của Spring.

## 7. Ví dụ auto-configuration dùng API công khai

Giả sử thư viện cung cấp `CatalogClient`. Người dùng muốn thay implementation mặc định thì dùng auto-configuration và condition công khai:

```java
@AutoConfiguration
@ConditionalOnClass(CatalogClient.class)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(CatalogProperties properties) {
        return new DefaultCatalogClient(properties.getBaseUri());
    }
}
```

Đây là snippet minh họa; `CatalogClient` và `CatalogProperties` thuộc thư viện ví dụ.

Đăng ký trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
com.example.catalog.autoconfigure.CatalogAutoConfiguration
```

Kiểm thử bằng `ApplicationContextRunner`, thêm user configuration rồi xác nhận bean mặc định back off. Không cần subclass `AutoConfigurationImportSelector` hoặc can thiệp parser nội bộ để thêm auto-configuration mới.

## 8. Chọn SPI theo đúng lifecycle

| Câu hỏi | Lựa chọn phù hợp | Tránh dùng |
| --- | --- | --- |
| Muốn thay đổi thuộc tính cấu hình của thành phần? | `@ConfigurationProperties` hoặc customizer/builder công khai | Reflection vào field của bean sau khi tạo |
| Muốn thay đổi bean instance sau khi tạo? | `BeanPostProcessor` nếu cần xử lý ở cấp container; AOP nếu mục tiêu là method interception | Sửa instance trong `BeanFactoryPostProcessor` bằng cách gọi `getBean` |
| Muốn chỉnh metadata trước khi tạo bean? | `BeanFactoryPostProcessor` hoặc `BeanDefinitionRegistryPostProcessor` | Truy cập parser private |
| Muốn cấu hình context trước refresh? | `ApplicationContextInitializer` | Gọi refresh nội bộ hoặc khởi tạo bean quá sớm |
| Muốn phản ứng với event? | `ApplicationListener` / `@EventListener` và event công khai | Theo dõi log hoặc event nội bộ không có contract |
| Muốn thêm auto-configuration? | `@AutoConfiguration` + `AutoConfiguration.imports` | Thay thế selector nội bộ |
| Muốn thêm option vào builder của Boot? | Customizer SPI tương ứng | Wrap bean infrastructure không liên quan |
| Muốn thay bean mặc định? | `@ConditionalOnMissingBean` + user bean | Đổi tên bean nội bộ hoặc bật overriding tùy tiện |

**Quy tắc thực hành:** chọn API cấp cao nhất đáp ứng yêu cầu. SPI thấp như BPP/BFPP có phạm vi ảnh hưởng lớn hơn, lifecycle phức tạp hơn và cần test kỹ hơn.

## 9. Kiểm tra độ ổn định khi nâng phiên bản

### 9.1. Kiểm tra Javadoc và release notes

Trước khi dùng một class:

- Mở Javadoc đúng phiên bản dependency của ứng dụng.
- Đọc mô tả class/interface, method, callback và `@since`.
- Kiểm tra annotation deprecated, phiên bản bắt đầu deprecated và `forRemoval`.
- Đọc migration guide giữa các major versions.
- Xem tài liệu có hướng dẫn triển khai interface hoặc đăng ký bean không.
- Nếu API đổi tên/thay package, ưu tiên API thay thế được chỉ ra trong Javadoc.

Không đọc Javadoc của `current` rồi mặc định dự án Boot 3.5 có cùng API. Hãy mở Javadoc versioned theo dependency thực tế.

### 9.2. Khai báo dependency rõ ràng

Nếu code thư viện gọi một type từ Spring Boot, khai báo dependency cần thiết rõ ràng. Không dựa vào việc dependency khác tình cờ kéo class vào transitive classpath. Với starter, phân biệt dependency cần compile/runtime với dependency chỉ cần test.

Không copy class nội bộ từ source framework vào code ứng dụng. Copy code không biến implementation detail thành contract và tạo trách nhiệm đồng bộ bug/security fix.

### 9.3. Viết test theo hành vi công khai

- Test bean nào tồn tại, bean nào back off và property nào được bind.
- Test callback thực sự được gọi qua registration path được hỗ trợ.
- Test context khởi động và đóng đúng lifecycle.
- Nếu hỗ trợ nhiều Spring Boot versions, chạy compatibility test matrix tương ứng.
- Không assert tên class proxy, field private, số thứ tự bean nội bộ hoặc log không được tài liệu hóa.

`ApplicationContextRunner` hữu ích để test auto-configuration với tổ hợp property, user beans và classpath. Với web context, có thể dùng `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner`.

### 9.4. Theo dõi deprecation

Khi gặp `@Deprecated(since = "x", forRemoval = true)`, không chỉ suppress warning. Đọc Javadoc và migration guide để biết API thay thế. Khi nâng major version, rà soát import thuộc Spring Framework/Boot, đặc biệt extension hook, customizer và SPI đăng ký qua resource file.

## 10. Lỗi thiết kế thường gặp

1. **Dựa vào modifier public:** class import được không chứng minh nó là API dành cho ứng dụng. Tìm tài liệu extension contract.
2. **Dùng reflection để lấy field private:** thay bằng property, accessor, event hoặc SPI được công bố. Reflection có thể hỏng vì module access hoặc refactor.
3. **Subclass infrastructure class:** chỉ subclass khi tài liệu nói class đó được thiết kế cho extension và mô tả method cần override. Nếu không, dùng interface/callback.
4. **Dựa vào thứ tự bean registration ngẫu nhiên:** dùng `@Order`/`Ordered` khi contract hỗ trợ và hiểu rõ semantics. Không dựa vào thứ tự classpath.
5. **Dựa vào bean name không công bố:** inject theo interface/type hoặc qualifier của ứng dụng; tên chỉ dùng khi là một phần contract rõ ràng.
6. **Dùng BFPP để chỉnh object instance:** BFPP làm việc với metadata; BPP làm việc với instance.
7. **Đăng ký BPP có dependency lớn:** BPP được tạo rất sớm; dependency có thể không được post-process đầy đủ. Dùng static factory method ít dependency.
8. **Wrap mọi bean khi chỉ cần hook hẹp:** BPP áp dụng trên nhiều bean. Dùng customizer chuyên biệt nếu có.
9. **Dựa vào class nội bộ của Boot để sửa auto-configuration:** dùng `@AutoConfiguration`, conditions và `AutoConfiguration.imports`.
10. **Test implementation thay vì contract:** kiểm tra kết quả ứng dụng cần, không khóa test vào tên class proxy hoặc cấu trúc bean definitions nội bộ.
11. **Bỏ qua deprecation:** code vẫn compile ở version hiện tại nhưng có thể bị loại trong bản tiếp theo.
12. **Phân loại chỉ theo tên package:** không kết luận mọi thứ trong package `support` là internal hoặc mọi thứ trong `autoconfigure` là API. Đọc từng type và mục đích được tài liệu mô tả.

## 11. Checklist review một extension point

Trước khi merge code tích hợp Spring, trả lời:

- [ ] Đã tìm tài liệu chính thức/Javadoc đúng version chưa?
- [ ] Đây là API ứng dụng gọi hay SPI framework gọi lại?
- [ ] Lifecycle callback xảy ra khi nào: trước hay sau refresh/initialization?
- [ ] Có cách đăng ký chính thức và đúng resource file/bean method không?
- [ ] Phạm vi ảnh hưởng là một builder, một bean, mọi bean hay toàn ApplicationContext?
- [ ] Có phụ thuộc package/class/field/method được ghi là internal không?
- [ ] Có dùng reflection, `setAccessible`, `--add-opens`, tên bean không công bố hoặc thứ tự không được bảo đảm không?
- [ ] Có API cấp cao hơn, hẹp hơn để đáp ứng yêu cầu không?
- [ ] Có test bằng `ApplicationContextRunner` hoặc context thật để kiểm chứng contract không?
- [ ] Đã xem `@since`, deprecation, migration guide và phiên bản được hỗ trợ chưa?

Nếu chưa trả lời được câu hỏi về contract, hãy xác minh trước khi phụ thuộc vào class đó.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một class có modifier `public` trong package Spring. Điều đó có chứng minh nó là API mở rộng được hỗ trợ?  
**Đáp án:** Không. `public` chỉ cho phép truy cập từ code khác; phải xem tài liệu, mục đích và extension contract.

**Câu 2.** Muốn can thiệp bean instance sau khi khởi tạo nên dùng SPI nào?  
**Đáp án:** `BeanPostProcessor`, hoặc AOP/customizer phù hợp hơn nếu có hook cấp cao.

**Câu 3.** `BeanFactoryPostProcessor` nên được dùng để gọi `getBean()` rồi sửa object?  
**Đáp án:** Không. Nó chỉnh bean definition metadata trước khi tạo bean. Dùng `BeanPostProcessor` nếu cần xử lý instance.

**Câu 4.** Vì sao BPP nên được đăng ký bằng static `@Bean` method ít dependency?  
**Đáp án:** BPP được tạo rất sớm để xử lý các bean khác; dependency không cần thiết có thể bị khởi tạo trước khi toàn bộ post-processors được đăng ký.

**Câu 5.** Muốn thêm auto-configuration trong starter Boot 3.x, có nên subclass parser nội bộ?  
**Đáp án:** Không. Dùng `@AutoConfiguration`, condition công khai và `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

**Câu 6.** Muốn thêm header vào `RestClient.Builder` do Boot quản lý, lựa chọn đầu tiên là gì?  
**Đáp án:** `RestClientCustomizer` của Spring Boot 3.5, nếu builder được tạo qua auto-configuration/customizer pipeline. `RestClient.create()` bỏ qua pipeline đó.

**Câu 7.** Nếu một API bị đánh dấu deprecated với `forRemoval=true`, có thể chỉ suppress warning?  
**Đáp án:** Không nên. Đọc Javadoc và migration guide để chuyển sang API thay thế.

**Câu 8.** Test có nên assert tên class proxy do Spring tạo ra?  
**Đáp án:** Thường không. Assert interface, hành vi và contract mà ứng dụng cần; tên class proxy là implementation detail.

## Tài liệu tham khảo chính thức

- Spring Framework Reference — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework Javadoc 6.2 — `BeanPostProcessor`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html
- Spring Framework Javadoc 6.2 — `BeanFactoryPostProcessor`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html
- Spring Framework Javadoc 6.2 — `ApplicationContextInitializer`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationContextInitializer.html
- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `RestClientCustomizer`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/client/RestClientCustomizer.html
- Spring Boot 3.5 API — `WebServerFactoryCustomizer`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizer.html
- Spring Boot Reference — Calling REST Services and `RestClientCustomizer`: https://docs.spring.io/spring-boot/reference/io/rest-client.html

**Ghi nhớ:** Hãy mở rộng Spring qua **contract được tài liệu hóa**: interface, annotation, callback, event, builder và cơ chế đăng ký chính thức. Một class có thể truy cập được mà vẫn chỉ là cách framework triển khai bên trong. Test hành vi công khai và nâng cấp theo migration guide giúp giảm phụ thuộc vào chi tiết dễ thay đổi.
