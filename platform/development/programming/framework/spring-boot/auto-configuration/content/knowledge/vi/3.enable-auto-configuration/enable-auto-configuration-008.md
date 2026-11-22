# Từ SpringApplication.run đến xử lý lớp cấu hình và đăng ký định nghĩa bean

## 1. Mục tiêu và bức tranh tổng thể

Khi chạy một ứng dụng Spring Boot:

```java
@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
```

Spring không lập tức gọi constructor của tất cả lớp `@Component`. Trước hết, Boot chuẩn bị môi trường và `ApplicationContext`, rồi Spring Framework **phân tích các nguồn cấu hình**, đăng ký **`BeanDefinition`**, giải quyết dependency và tạo những bean cần thiết. Quá trình khởi tạo này giải thích cách Spring Boot kết hợp cấu hình do ứng dụng viết, component scanning và auto-configuration.

Bài học đi theo tuyến đường:

```text
main()
  -> SpringApplication.run(...)
  -> chuẩn bị Environment, ApplicationContext và sources
  -> refresh() context
       -> đọc @Configuration / @ComponentScan / @Import / @Bean
       -> xét auto-configuration và @Conditional
       -> đăng ký BeanDefinition vào registry
       -> đăng ký BeanPostProcessor
       -> tạo các singleton không lazy và xử lý vòng đời
  -> context được refresh thành công
  -> gọi ApplicationRunner / CommandLineRunner
  -> báo ứng dụng sẵn sàng
```

Đây là **sơ đồ khái niệm**, không phải trace mọi lệnh nội bộ. Một số bean infrastructure được tạo sớm để tham gia việc phân tích cấu hình; không phải mọi bean đợi đến cùng một bước. Các bước tiếp theo sẽ nêu rõ nơi nào là quyết định về **định nghĩa bean**, nơi nào thực sự **tạo bean instance**.

Kết quả mong đợi sau bài:

- Phân biệt trách nhiệm của `SpringApplication`, `ApplicationContext`, `BeanFactory` và `BeanDefinitionRegistry`.
- Mô tả được cách Spring xử lý `@SpringBootApplication`, `@Configuration`, `@ComponentScan`, `@Import` và `@Bean`.
- Hiểu auto-configuration được chọn từ metadata, chịu các điều kiện và đóng góp bean definitions như thế nào.
- Đọc log/stack trace đúng pha: thiếu bean definition, điều kiện không khớp, tạo bean lỗi hay runner thất bại.
- Tự quan sát một bean **đã có definition nhưng chưa có instance** bằng ví dụ Java 17 + Spring Boot.

## 2. Đối tượng nào làm việc gì?

| Thành phần | Trách nhiệm | Điểm cần nhớ |
| --- | --- | --- |
| `SpringApplication` (Boot) | Điều phối startup, chuẩn bị môi trường/context, nạp nguồn cấu hình, gọi runner và phát các mốc lifecycle | Không thay thế IoC container của Spring Framework |
| `Environment` | Gom property sources, profiles và giá trị cấu hình | Có thể ảnh hưởng tới `@Profile`, `@ConditionalOnProperty`, binding |
| `ApplicationContext` | Container cấp ứng dụng: cung cấp bean, events, resources, lifecycle, environment | `refresh()` là mốc chủ chốt để đưa cấu hình thành context hoạt động |
| `BeanDefinitionRegistry` | Lưu/đăng ký/tra cứu định nghĩa bean | Một definition không đồng nghĩa với một instance đã được tạo |
| `BeanFactory` | Tạo/tra cứu bean, DI, scope, initialization và destruction | `getBean()` đôi khi kích hoạt tạo bean |
| `BeanDefinition` | Metadata cho biết cách tạo một bean, ví dụ class, factory method, scope, lazy | Là cấu hình của bean, không phải bản thân bean |
| `BeanFactoryPostProcessor` | Chỉnh metadata trước khi khởi tạo phần lớn bean thông thường | Không nên gọi `getBean()` tùy tiện trong processor này |
| `BeanPostProcessor` | Can thiệp instance trước/sau initialization; có thể tạo proxy | Hoạt động ở pha khác với xử lý definition |

Một triển khai như `DefaultListableBeanFactory` có thể đồng thời hiện thực nhiều giao diện, bao gồm cả factory và registry. Sơ đồ phân trách nhiệm không có nghĩa mỗi vai trò phải là một đối tượng vật lý riêng biệt.

**Hai trạng thái độc lập của bean:**

```text
Đã có BeanDefinition?     Có
Đã tạo singleton instance? Có thể chưa
```

Một singleton `@Lazy` minh họa rất rõ: metadata đã được đăng ký từ lúc xử lý cấu hình, nhưng instance có thể chỉ xuất hiện khi được yêu cầu. Ngược lại, auto-configuration có điều kiện không khớp có thể **không đăng ký definition** ngay từ đầu; đó không phải vấn đề lazy initialization.

## 3. Từ main() vào SpringApplication.run(...)

`SpringApplication.run(MyApplication.class, args)` là lời gọi thuận tiện tạo một `SpringApplication` và khởi chạy nó. Lớp `MyApplication.class` là **primary source**: Boot dùng nó làm nguồn cấu hình ban đầu. Những nguồn bổ sung có thể được thêm qua các API thích hợp của `SpringApplication` hoặc cơ chế cấu hình.

### 3.1. Chuẩn bị môi trường

Boot tổ chức việc chuẩn bị `Environment` từ nhiều nguồn như command-line arguments, system properties, environment variables và cấu hình ứng dụng. Các quy tắc ưu tiên property quyết định giá trị hiệu lực. Môi trường này tác động đến việc chọn profile và các điều kiện cấu hình, nên hai lần khởi động cùng bộ class có thể tạo ra tập bean definitions khác nhau.

Ví dụ:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Dòng lệnh này minh họa cú pháp property Spring Boot; tên `app.jar` là ví dụ, không phải artifact tạo ở phần thực hành. Khi profile `dev` hoạt động, những cấu hình có `@Profile("dev")` có thể được xét, còn cấu hình chỉ dành cho `prod` có thể bị bỏ qua.

`Environment` không tự biến mọi property thành bean. Một property có thể được dùng để điều khiển condition, được bind vào `@ConfigurationProperties` hoặc được đọc qua API; kết quả phụ thuộc vào cơ chế cụ thể.

### 3.2. Chọn loại ApplicationContext

Boot suy luận loại ứng dụng từ classpath và cấu hình (chẳng hạn `spring.main.web-application-type`), rồi tạo context phù hợp. Ví dụ:

- Ứng dụng **non-web** có thể sử dụng `AnnotationConfigApplicationContext`.
- Ứng dụng **servlet web** thường dùng `AnnotationConfigServletWebServerApplicationContext`.
- Ứng dụng **reactive web** thường dùng `AnnotationConfigReactiveWebServerApplicationContext`.

Những tên trên mô tả các triển khai thường gặp trong Spring Boot 3.x, không phải cam kết một class duy nhất trong mọi cấu hình tùy biến. Việc chọn context ảnh hưởng đến infrastructure được tạo và những điều kiện `@ConditionalOnWebApplication` có thể khớp.

### 3.3. Chuẩn bị và nạp nguồn cấu hình

Boot chuẩn bị context, gắn environment, áp dụng những initializer phù hợp và nạp các primary sources. Điều đó không có nghĩa toàn bộ bean của ứng dụng được tạo ngay ở bước này. Lớp gốc thường được đưa vào registry dưới dạng một định nghĩa để các bộ xử lý cấu hình có thể phân tích sâu khi `refresh()`.

Quan sát khác biệt:

```text
Biết lớp cấu hình gốc
  != đã phân tích hết các import và @Bean
  != đã tạo xong mọi instance
```

`SpringApplication.run()` cuối cùng trả về `ConfigurableApplicationContext` **nếu startup thành công**; nếu lỗi nghiêm trọng trong `refresh()`, Boot xử lý thất bại khởi động và ném exception phù hợp.

## 4. Vì sao ApplicationContext.refresh() là bước quyết định?

Trong triển khai `AbstractApplicationContext`, `refresh()` điều phối nhiều bước để biến các định nghĩa ban đầu thành container dùng được. Có thể hình dung trình tự lớn:

```text
refresh()
  prepareRefresh()
  obtainFreshBeanFactory()
  prepareBeanFactory(beanFactory)
  postProcessBeanFactory(beanFactory)
  invokeBeanFactoryPostProcessors(beanFactory)
  registerBeanPostProcessors(beanFactory)
  initMessageSource()
  initApplicationEventMulticaster()
  onRefresh()
  registerListeners()
  finishBeanFactoryInitialization(beanFactory)
  finishRefresh()
```

Đây là tên các pha ở mức Framework (đã đơn giản hóa phần chi tiết implementation). Một số bước gọi extension points có thể đăng ký bean definition bổ sung; các loại context (đặc biệt web) còn có công việc riêng.

Hai pha đặc biệt quan trọng cho bài học:

- **`invokeBeanFactoryPostProcessors(...)`**: các factory/registry post-processor tham gia hoàn thiện metadata. Trong đó `ConfigurationClassPostProcessor` phân tích `@Configuration`, `@ComponentScan`, `@Import`, `@Bean` và giúp đăng ký thêm definitions.
- **`finishBeanFactoryInitialization(...)`**: sau khi đã cấu hình các processors cần thiết, Spring thường khởi tạo những singleton còn lại thuộc diện **non-lazy** (`preInstantiateSingletons`). Một bean `@Lazy`, prototype hoặc scope khác có thể được tạo ở thời điểm khác.

Không nên hiểu sơ đồ này thành “không có instance nào trước `finishBeanFactoryInitialization`”. Một số processor và hạ tầng cần được khởi tạo sớm để Spring có thể tiếp tục; điều quan trọng là phần lớn bean nghiệp vụ singleton không lazy thường được hoàn tất ở pha sau.

Với web context, công việc tạo/chuẩn bị server nhúng có thể nằm trong các pha lifecycle tương ứng; không nên suy diễn rằng server chạy ngay khi `@SpringBootApplication` được nhìn thấy.

## 5. ConfigurationClassPostProcessor đọc cấu hình ra sao?

`ConfigurationClassPostProcessor` là một `BeanDefinitionRegistryPostProcessor` thuộc Spring Framework, được đăng ký trong cơ chế xử lý annotation. Nó làm việc với các lớp cấu hình đã được biết, phát hiện thông tin cấu hình và giúp chuyển chúng thành bean definitions trong registry.

### 5.1. Lớp gốc @SpringBootApplication

`@SpringBootApplication` là annotation tổng hợp, mang ba vai trò chính:

```java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
```

`@SpringBootConfiguration` là dạng chuyên biệt của `@Configuration`. `@ComponentScan` tìm các stereotype trong phạm vi package phù hợp. `@EnableAutoConfiguration` kích hoạt cơ chế lựa chọn auto-configuration. Phép liệt kê trên diễn đạt ý nghĩa, không phải phép thay thế chính xác mọi metadata/filter/alias của annotation tổng hợp.

Ví dụ lớp gốc:

```java
package example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

Khi đặt ở `example.shop`, mặc định component scanning sẽ hướng tới `example.shop` và các package con như `example.shop.service` hoặc `example.shop.config`. Điều đó **không** có nghĩa Boot quét toàn bộ classpath hay tìm các auto-configuration JAR bằng `@ComponentScan`.

### 5.2. Đọc @ComponentScan

Giả sử có lớp:

```java
package example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public int finalPrice(int price) {
        return price - 10;
    }
}
```

Nếu package này thuộc vùng scan, Spring phát hiện class phù hợp và đăng ký bean definition cho `PriceService`. Object `PriceService` chưa nhất thiết được tạo tại khoảnh khắc metadata được phát hiện.

Nếu đặt `ShopApplication` tại `example.shop.launcher`, còn `PriceService` tại `example.shop.service`, thì chúng là package anh em và quét mặc định từ `launcher` **không bao phủ** `service`. Đặt main ở package gốc hoặc cấu hình phạm vi scan có chủ đích sẽ giải quyết vấn đề.

### 5.3. Đọc @Configuration và @Bean

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class PricingConfiguration {
    @Bean
    PricingPolicy pricingPolicy() {
        return new PricingPolicy();
    }
}
```

Đây là snippet minh họa: `PricingPolicy` cần được định nghĩa và import phù hợp. Spring biến phương thức `pricingPolicy()` thành một bean definition có thông tin factory method. Khi cần tạo bean, BeanFactory gọi factory method qua cơ chế thích hợp và áp dụng DI/lifecycle.

Một số trường hợp có thể dùng `@Bean` trên class không mang `@Configuration` đầy đủ; semantics của gọi chéo các phương thức `@Bean` khác nhau giữa **full configuration** (`proxyBeanMethods=true`) và chế độ lite hoặc `proxyBeanMethods=false`. Cách rõ ràng để một bean phụ thuộc bean khác là khai báo dependency qua **tham số `@Bean`** hoặc constructor.

### 5.4. Đọc @Import và các cơ chế mở rộng

`@Import` đưa class cấu hình hoặc các cách đăng ký có kiểm soát vào quá trình phân tích:

```java
@Configuration
@Import(ExternalModuleConfiguration.class)
class ModuleConfiguration {
}
```

Đoạn trên minh họa; `ExternalModuleConfiguration` là kiểu giả định, không phải tệp tự chạy. `@Import` có thể liên quan đến `ImportSelector`, `DeferredImportSelector` hoặc `ImportBeanDefinitionRegistrar`, không chỉ import một lớp có sẵn.

`BeanDefinitionRegistryPostProcessor` cũng có thể tự đăng ký thêm definitions nếu được dùng đúng thời điểm. Đây là extension cho infrastructure/framework, không phải công cụ cần dùng hàng ngày để thay thế `@Bean` đơn giản.

## 6. Auto-configuration nhập vào quy trình ở bước nào?

`@EnableAutoConfiguration` (được mang theo `@SpringBootApplication`) sử dụng cơ chế import của Spring. Trong Spring Boot 3.x, `AutoConfigurationImportSelector` tham gia lựa chọn các ứng viên auto-configuration; các JAR khai báo danh sách trong:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng trong tệp metadata chứa tên đầy đủ của một lớp auto-configuration. Danh sách ứng viên này **khác** với vùng package mà `@ComponentScan` quét. Cơ chế lựa chọn còn hỗ trợ lọc exclusions, điều kiện và thứ tự tương đối thích hợp giữa các auto-configuration.

Một lớp tự cấu hình điển hình:

```java
@AutoConfiguration
@ConditionalOnClass(ExternalClient.class)
class ExternalClientAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(ExternalClient.class)
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

`ExternalClient` là kiểu giả định và đoạn trên **chỉ minh họa**, không phải chương trình biên dịch độc lập. Điều kiện class và điều kiện bean khiến một định nghĩa mặc định chỉ xuất hiện khi đáp ứng những yêu cầu của module.

### Điều kiện được kiểm tra khi nào?

Một số điều kiện có thể loại lớp cấu hình từ pha phân tích cấu hình; những điều kiện khác được xét khi chuẩn bị đăng ký bean definition. Vì vậy không có một mốc duy nhất “mọi `@Conditional` chạy sau mọi `@Bean`”. Spring/Boot có logic phase và thứ tự cấu hình, đặc biệt đối với `@ConditionalOnBean` và `@ConditionalOnMissingBean`.

Những loại điều kiện thường gặp:

| Điều kiện | Kiểm tra | Kết quả có thể thấy |
| --- | --- | --- |
| `@ConditionalOnClass` | Class/thư viện có trên classpath | Thiếu dependency thì bỏ qua cấu hình cần nó |
| `@ConditionalOnProperty` | Property có giá trị yêu cầu | Bật/tắt cấu hình theo environment |
| `@ConditionalOnBean` | Bean phù hợp đã được đăng ký | Cấu hình phụ thuộc vào infrastructure có sẵn |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp ở thời điểm xét | Mặc định **nhường chỗ** cho cấu hình ứng dụng |
| `@ConditionalOnWebApplication` | Loại ứng dụng web | Cấu hình web chỉ chạy khi phù hợp |

Trình tự xử lý được thiết kế để auto-configuration có thể phản ứng trước những bean ứng dụng đã đăng ký. Tuy nhiên **không nên** hiểu rằng mọi bean của Boot đều có `@ConditionalOnMissingBean` hoặc mọi bean người dùng luôn tự động thắng trong mọi trường hợp; phải xem condition thực tế theo type/name và điều kiện đi kèm.

### Phân biệt ba việc hay bị nhầm

1. **Không đăng ký definition:** Condition không khớp; bean mặc định có thể không xuất hiện trong registry.
2. **Đã đăng ký definition nhưng chưa tạo instance:** Đối tượng có thể được đánh dấu `@Lazy`, thuộc scope khác hoặc chưa cần dùng.
3. **Đã có definition nhưng tạo instance lỗi:** Lỗi constructor, thiếu dependency, bean vòng, cấu hình properties hoặc initialization callback khiến startup thất bại.

Ba tình huống có cách chẩn đoán khác nhau; chỉ nhìn một thông báo “không có bean” sẽ không đủ.

## 7. BeanDefinition được lưu và dùng để tạo bean thế nào?

Một `BeanDefinition` có thể mang thông tin:

- Bean name và nguồn định nghĩa.
- Class cần khởi tạo hoặc factory bean/factory method.
- Scope như singleton/prototype và trạng thái lazy.
- Constructor arguments, property values, autowire metadata.
- Init/destroy method và những thuộc tính vòng đời khác.

Ví dụ một phương thức:

```java
@Bean
@Lazy
ReportFormatter reportFormatter() {
    return new ReportFormatter("REPORT");
}
```

là mã minh họa, giả định có class `ReportFormatter`. Spring có thể đăng ký bean definition tên `reportFormatter` khi xử lý cấu hình. Do `@Lazy`, singleton không cần thiết được tạo ngay nếu chưa có dependency buộc phải dùng nó sớm.

Khi một bean được yêu cầu hoặc đến thời điểm pre-instantiation, `BeanFactory` có thể:

1. Chọn constructor/factory method từ definition.
2. Giải quyết dependency và tạo những bean cần thiết.
3. Tạo object, inject giá trị, chạy callback và `BeanPostProcessor`.
4. Cung cấp bean cuối cùng, có thể là proxy, cho consumer.
5. Lưu singleton instance để dùng lại khi scope là singleton.

**`BeanDefinition` không phải object runtime**. Ví dụ, `containsBeanDefinition("reportFormatter") == true` chưa đủ để kết luận `containsSingleton("reportFormatter") == true`.

Không nên dùng khái niệm “singleton duy nhất trên JVM”: singleton của Spring mặc định là một instance cho mỗi bean definition trong một container. Hai `ApplicationContext` độc lập có thể có hai singleton khác nhau cho cùng một bean name.

## 8. Ví dụ chạy được: từ cấu hình tới định nghĩa và instance

Để quan sát trọn quá trình, ta dùng **Java 17+, Spring Boot 3.3.13, Maven** với một dự án non-web. Có ba nguồn bean:

- Bean do `@Configuration` + `@Bean` khai báo.
- Bean `@Service` do component scan tìm thấy.
- `ObjectMapper` được auto-configuration của Spring Boot cung cấp khi có Jackson và điều kiện cần thiết.

Đồng thời, một bean `@Lazy` được dùng để chứng minh **định nghĩa có trước instance**.

### 8.1. Cấu trúc dự án

```text
bean-startup-demo/
├── pom.xml
└── src/main/java/demo/
    ├── TraceApplication.java
    ├── config/
    │   └── GreetingConfiguration.java
    ├── model/
    │   └── GreetingFormatter.java
    └── service/
        └── GreetingService.java
```

Lớp `TraceApplication` ở package `demo`, là package cha của `config`, `model`, `service`. Vì vậy `@ComponentScan` mặc định sẽ tìm được cấu hình và service trong các package con.

### 8.2. pom.xml

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
    <artifactId>bean-startup-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-json</artifactId>
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

`spring-boot-starter-json` đưa Jackson vào classpath. Trong cấu hình mặc định của ví dụ, Boot auto-configuration có điều kiện có thể cung cấp bean `ObjectMapper`. Không cần khai báo web server để minh họa Jackson.

### 8.3. Bean model và cấu hình ứng dụng

**`src/main/java/demo/model/GreetingFormatter.java`:**

```java
package demo.model;

public record GreetingFormatter(String prefix) {
    public String greet(String name) {
        return prefix + " " + name;
    }
}
```

Đây là class Java bình thường; không có stereotype nên chỉ tồn tại trên classpath **chưa đủ** để Spring tự đăng ký bean.

**`src/main/java/demo/config/GreetingConfiguration.java`:**

```java
package demo.config;

import demo.model.GreetingFormatter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter("Chào");
    }
}
```

`GreetingConfiguration` được component scanning tìm thấy; Spring phân tích `@Bean greetingFormatter()` thành bean definition. `proxyBeanMethods=false` phù hợp vì các phương thức `@Bean` ở đây không tự gọi nhau. Cách nhận bean trong service là **constructor injection**.

### 8.4. Service được quét

**`src/main/java/demo/service/GreetingService.java`:**

```java
package demo.service;

import demo.model.GreetingFormatter;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final GreetingFormatter formatter;

    public GreetingService(GreetingFormatter formatter) {
        this.formatter = formatter;
    }

    public String say(String name) {
        return formatter.greet(name);
    }
}
```

`@Service` được phát hiện qua component scan. Spring tạo bean `GreetingService` và giải quyết dependency `GreetingFormatter` đã được định nghĩa từ phương thức `@Bean`.

### 8.5. Lớp khởi động và quan sát registry

**`src/main/java/demo/TraceApplication.java`:**

```java
package demo;

import java.util.Map;
import com.fasterxml.jackson.databind.ObjectMapper;
import demo.service.GreetingService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;

@SpringBootApplication
public class TraceApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(TraceApplication.class, args)) {

            String beanName = "delayedMarker";
            System.out.println("DEFINITION: "
                + context.containsBeanDefinition(beanName));
            System.out.println("BEFORE_GET: "
                + context.getBeanFactory().containsSingleton(beanName));

            context.getBean(DelayedMarker.class);

            System.out.println("AFTER_GET: "
                + context.getBeanFactory().containsSingleton(beanName));
        }
    }

    @Bean
    ApplicationRunner showBeans(GreetingService service, ObjectMapper mapper) {
        return args -> {
            System.out.println("SERVICE: " + service.say("Spring"));
            System.out.println("JACKSON: "
                + mapper.writeValueAsString(Map.of("ready", true)));
        };
    }

    @Bean
    @Lazy
    DelayedMarker delayedMarker() {
        System.out.println("CREATE_DELAYED");
        return new DelayedMarker();
    }

    public static class DelayedMarker {
    }
}
```

Dòng `context.getBean(DelayedMarker.class)` xuất hiện **sau** `SpringApplication.run` nên trước đó không có consumer nào yêu cầu `delayedMarker` trong ví dụ. Vì `@Lazy`, definition đã có nhưng instance chưa nằm trong singleton cache.

`showBeans()` là một `@Bean` của ứng dụng. `ApplicationRunner` được Boot thực thi sau khi context refresh thành công; nó nhận `GreetingService` do component scanning và `ObjectMapper` do auto-configuration cung cấp. Lưu ý `ApplicationRunner` được gọi **trước khi** phương thức `SpringApplication.run` trả về, vì vậy các dòng `SERVICE`/`JACKSON` xuất hiện trước phần quan sát `DEFINITION`.

### 8.6. Build, chạy và đối chiếu output

Tại thư mục có `pom.xml`, với JDK 17+ và Maven:

```bash
mvn -q -DskipTests package
java -jar target/bean-startup-demo-0.0.1-SNAPSHOT.jar --spring.main.web-application-type=none
```

Bỏ qua banner, log startup và log shutdown, các dòng **do chính ví dụ in** theo thứ tự:

```text
SERVICE: Chào Spring
JACKSON: {"ready":true}
DEFINITION: true
BEFORE_GET: false
CREATE_DELAYED
AFTER_GET: true
```

Cách lý giải:

1. `SERVICE` xuất phát từ `GreetingService` đã được scan, phụ thuộc `GreetingFormatter` do `@Bean` khai báo.
2. `JACKSON` chứng minh `ObjectMapper` có sẵn qua Spring Boot auto-configuration trong điều kiện classpath của dự án.
3. `DEFINITION: true`: Spring đã đăng ký bean definition tên `delayedMarker`.
4. `BEFORE_GET: false`: singleton instance `delayedMarker` chưa được tạo bởi vì `@Lazy` và chưa có dependency nào yêu cầu nó.
5. `CREATE_DELAYED`: phương thức `@Bean delayedMarker()` thực sự chạy tại lần gọi `getBean()`.
6. `AFTER_GET: true`: instance singleton đã được quản lý bởi factory.

Trong một ứng dụng khác, nếu bean singleton không lazy phụ thuộc vào bean lazy, instance lazy vẫn có thể được tạo sớm để thỏa dependency. Vì thế **lazy là chính sách trì hoãn khi có thể**, không phải lời hứa không bao giờ khởi tạo trong startup.

Nếu muốn kiểm tra môi trường của ví dụ, có thể chạy:

```bash
java -version
mvn -version
```

Các lệnh này cho biết phiên bản công cụ đang cài; chúng không thay đổi cơ chế bean lifecycle.

## 9. So sánh những mốc hay nhầm

| Mốc | Có thể khẳng định | Chưa thể khẳng định |
| --- | --- | --- |
| Class `.class` có trên classpath | JVM/classloader có thể nạp class nếu hợp lệ | Class đã là Spring bean |
| Component scan tìm được class | Class có thể trở thành ứng viên bean definition | Bean instance đã được tạo thành công |
| `@Bean` được phân tích | Có thể đăng ký definition với factory method | Factory method đã chạy |
| Auto-configuration được liệt kê trong `.imports` | Có một ứng viên cấu hình để xem xét | Tất cả condition đều khớp hoặc mọi bean của nó đều tồn tại |
| `containsBeanDefinition(name)` trả `true` | Registry biết definition có tên đó | Singleton instance đã nằm trong cache |
| `containsSingleton(name)` trả `true` | BeanFactory đã đăng ký singleton instance với tên đó | Không nhất thiết mọi consumer đã gọi bean |
| Context refresh xong | Phần lớn non-lazy singleton và infrastructure đã sẵn sàng | Mọi lazy/prototype bean đều đã được tạo |
| `SpringApplication.run()` trả về bình thường | Các bước startup do Boot thực hiện đã thành công | Các thao tác nghiệp vụ trong tương lai sẽ không lỗi |

`containsBeanDefinition(name)` kiểm tra local registry của context theo API tương ứng; cần lưu ý context phân cấp hoặc alias có thể tạo khác biệt khi tra cứu bean bằng tên. Với đối tượng cuối cùng, còn có trường hợp AOP proxy khiến runtime class khác với lớp định nghĩa.

### Phân biệt bean overriding với condition back-off

- **Condition back-off:** một cấu hình có `@ConditionalOnMissingBean` quyết định **không** thêm bean mặc định khi đã có bean phù hợp.
- **Bean definition overriding:** một definition đăng ký sau dùng cùng tên để thay definition trước, nếu được phép. Boot thường vô hiệu hóa overriding mặc định.
- **`@Primary`/`@Qualifier`:** chọn giữa những bean cùng type khi injection; không tự xóa bean khác.

Ba cơ chế có quan hệ đến lựa chọn bean nhưng xảy ra tại các tầng khác nhau. Đặc biệt `@Primary` **không** khiến một auto-configuration bất kỳ chắc chắn back off.

## 10. Chẩn đoán lỗi theo đúng giai đoạn

### 10.1. Lỗi không tìm được @Service

Ví dụ `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException` liên quan đến một service ứng dụng. Kiểm tra:

- `@Component`/`@Service` có được khai báo đúng?
- Lớp main ở package cha của service không?
- Có `@Profile` hoặc điều kiện khiến bean definition không được đăng ký?
- Lớp cấu hình có được import hay scan?
- Có nhiều context, nhưng bean lại ở context khác?

Nếu phạm vi scan không chứa service, việc thêm property của auto-configuration thường **không giải quyết** nguyên nhân.

### 10.2. Bean hạ tầng không xuất hiện

Nếu thiếu `DataSource`, `ObjectMapper` hay bean hạ tầng tương tự, cần kiểm tra dependency, thuộc tính, condition, exclusion và bean đã được ứng dụng khai báo. Bật chẩn đoán điều kiện:

```bash
java -jar target/bean-startup-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none --debug
```

Boot in **Conditions Evaluation Report** trong thông tin khởi động. Các phần *Positive matches*, *Negative matches* và *Exclusions* giúp hiểu tại sao ứng viên auto-configuration được áp dụng hay không. Có thể cần đọc root cause nếu definition tồn tại nhưng bean khởi tạo lỗi.

Không nên nhìn thấy một auto-configuration trong danh sách ứng viên rồi suy ra mọi bean của nó phải hiện diện.

### 10.3. Bean definition có nhưng vẫn thất bại

Những nguyên nhân thường gặp:

- Factory method `@Bean` ném exception.
- Constructor không thể resolve dependency hoặc dependency tạo vòng.
- Binding properties hoặc init callback thất bại.
- Bean được tạo quá sớm bởi một extension và chưa đi qua đủ processors.
- Có nhiều bean cùng type khiến injection không xác định (`NoUniqueBeanDefinitionException`).

Khi thấy `BeanCreationException`, hãy đọc **chuỗi `Caused by` sâu nhất có ý nghĩa**, class/method tạo bean và tên bean bị lỗi. Một exception tạo bean có thể được bọc trong `UnsatisfiedDependencyException` khi bean khác phụ thuộc vào nó.

### 10.4. Điều kiện chạy khi nào?

Không nên ghi nhớ quy tắc sai “mọi điều kiện chỉ được xét sau khi mọi bean đã tạo”. Đối với auto-configuration, điều kiện theo class/property/bean được xét trong quá trình phân tích và đăng ký, trước khi phần lớn singleton được khởi tạo. Điều kiện bean dựa vào các định nghĩa đã biết tại thời điểm đánh giá, nên thứ tự xử lý đặc biệt quan trọng.

Tại đây, cần phân biệt:

```text
Condition false -> không có bean definition mặc định
@Lazy           -> definition có, instance có thể chưa có
BeanCreationError -> definition có, tạo instance thất bại
```

Đó là ba vấn đề độc lập và nên xác định trước khi sửa code.

## 11. Extension points: khi nào thực sự cần can thiệp?

Đối với nhu cầu ứng dụng thông thường, hãy ưu tiên `@Configuration`, `@Bean`, `@Component`, properties và constructor injection. Những extension dưới đây phục vụ thư viện hoặc infrastructure chuyên biệt:

| Extension | Pha tác động | Dùng cho |
| --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Đăng ký/thao tác definitions khi container đang xây registry | Sinh definition theo một cấu trúc metadata đặc biệt |
| `BeanFactoryPostProcessor` | Điều chỉnh metadata/factory trước phần lớn bean initialization | Thay property hoặc đặc tính definition |
| `BeanPostProcessor` | Trước/sau initialization của instance | Trang trí bean, tạo proxy, xử lý callback |
| `ApplicationContextInitializer` | Khi context đã được tạo nhưng chưa refresh | Điều chỉnh context/environment trước startup |
| `ApplicationRunner` / `CommandLineRunner` | Sau context refresh thành công | Chạy tác vụ ở pha khởi động ứng dụng |

Lưu ý: việc tạo bean quá sớm trong một `BeanFactoryPostProcessor` có thể khiến một số `BeanPostProcessor` chưa được đăng ký, làm hành vi khác mong đợi. Không nên dùng `getBean()` ở pha này chỉ để chạy trước một tác vụ nghiệp vụ.

Khi phát triển **auto-configuration cho thư viện**, dùng `@AutoConfiguration`, điều kiện thích hợp, và khai báo `.imports` theo hướng dẫn của Spring Boot. Khi chỉ phát triển ứng dụng, tự viết một auto-configuration riêng thường không cần thiết cho mỗi bean.

## 12. Quy tắc thiết kế và kiểm thử thực tế

1. Đặt lớp `@SpringBootApplication` tại package gốc thích hợp, các component ở package con.
2. Dùng `@Bean` cho những đối tượng cần factory method hoặc từ thư viện không có stereotype.
3. Thêm starter để có dependency cần thiết; dùng Conditions Evaluation Report để biết auto-configuration nào khớp.
4. Dùng constructor injection để lộ rõ dependency, tránh gọi `ApplicationContext.getBean()` tùy tiện trong nghiệp vụ.
5. Khi đặt `@Lazy`, hiểu rằng lỗi có thể bị trì hoãn đến lúc sử dụng; cân nhắc fail-fast cho bean hạ tầng quan trọng.
6. Nếu cần thay mặc định, kiểm tra điều kiện `@ConditionalOnMissingBean` cụ thể thay vì giả định `@Primary` sẽ thay nó.
7. Khi debug, xác định chính xác pha: **đăng ký definition**, **giải quyết dependency**, **tạo instance**, **runner/startup**.

Trong test Spring Boot, một lỗi startup thường xảy ra khi test context đang refresh. Cách tiếp cận hiệu quả là đọc tên bean lỗi, root cause và cấu hình liên quan; sau đó xác định đây là **thiếu definition** hay **lỗi khởi tạo**. Không nên sửa bằng cách mở scan package quá rộng hoặc tắt hàng loạt auto-configuration chưa xác định nguyên nhân.

## 13. Tự kiểm tra

**Câu 1.** `SpringApplication.run()` và `ApplicationContext.refresh()` có phải cùng một phương thức không?

**Đáp án:** Không. Boot `SpringApplication` điều phối quá trình startup; bên trong đó context của Spring Framework được refresh. Boot còn quản lý environment, lifecycle events và gọi runner.

**Câu 2.** `@Bean` được parser tìm thấy nghĩa là factory method đã chạy chưa?

**Đáp án:** Chưa chắc. Spring thường đăng ký bean definition trước; factory method chỉ chạy khi container tạo bean.

**Câu 3.** Một `@Service` nằm ngoài package scan mặc định có xuất hiện chỉ vì class nằm trên classpath?

**Đáp án:** Không. Nó cần được component scan phát hiện, import qua cấu hình thích hợp hoặc đăng ký bằng cơ chế khác.

**Câu 4.** Vì sao `.imports` chứa auto-configuration không đồng nghĩa luôn có bean do cấu hình ấy cung cấp?

**Đáp án:** Đó mới là danh sách ứng viên. Classpath, properties, loại context, beans đã có và exclusion tiếp tục quyết định những phần cấu hình hợp lệ.

**Câu 5.** Trong ví dụ, vì sao `DEFINITION: true` nhưng `BEFORE_GET: false`?

**Đáp án:** `@Bean delayedMarker` đã được xử lý thành bean definition, nhưng `@Lazy` trì hoãn tạo singleton đến lần `getBean()` đầu tiên (vì không có consumer sớm).

**Câu 6.** Khi một bean hạ tầng không có, nên bắt đầu từ đâu?

**Đáp án:** Kiểm tra dependency, điều kiện auto-configuration, profiles/properties, exclusions, bean đã tồn tại; dùng Conditions Evaluation Report và đọc root cause thay vì chỉ tăng `@ComponentScan`.

## Tài liệu tham khảo

- Spring Boot — SpringApplication: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Framework — The IoC Container: https://docs.spring.io/spring-framework/reference/core/beans.html
- Spring Framework — Java-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Framework — Classpath Scanning: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
