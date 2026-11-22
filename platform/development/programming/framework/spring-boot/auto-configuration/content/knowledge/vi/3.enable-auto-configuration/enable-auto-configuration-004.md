# Phân biệt package tự cấu hình với phạm vi @ComponentScan trong Spring Boot

> **Mục tiêu:** Hiểu vì sao một lớp `@AutoConfiguration` nằm ngoài package ứng dụng vẫn có thể được nạp, trong khi một lớp `@Component` ở cùng vị trí lại không được component scan tìm thấy. Nhận diện ba khái niệm dễ nhầm: **package chứa auto-configuration class**, **package được `@ComponentScan` quét**, và **danh sách `AutoConfigurationPackages`** của Spring Boot. Ví dụ sử dụng Java 17 và Spring Boot 3.5.7; nguyên lý quan trọng áp dụng cho Spring Boot 3.x và các phiên bản hiện đại.

## 1. Cùng là “package”, nhưng có ba vai trò khác nhau

Hãy giả sử một ứng dụng có cấu trúc Java package:

```text
dev.demo
├── app
│   ├── DemoApplication.java            @SpringBootApplication
│   └── owned
│       └── OwnedService.java           @Service
├── infra
│   └── ExternalComponent.java          @Component
├── api
│   └── MessageSource.java              interface
└── autoconfigure
    └── MessageAutoConfiguration.java   @AutoConfiguration
```

**Ba phạm vi cần tách bạch:**

1. **Phạm vi component scan.** Mặc định, `@SpringBootApplication` quét package chứa lớp ứng dụng và các package con. Trong ví dụ là `dev.demo.app`, nên tìm `OwnedService`; không tự quét `dev.demo.infra` hay `dev.demo.autoconfigure`.
2. **Nơi đặt class auto-configuration.** `MessageAutoConfiguration` được tìm qua **danh sách ứng viên auto-configuration**, cụ thể là metadata `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` có trong classpath/JAR. Cơ chế này **không tìm ứng viên bằng cách quét package** của ứng dụng.
3. **`AutoConfigurationPackages`.** Đây là danh sách **base package mặc định của ứng dụng** mà Boot đăng ký để một số chức năng tự cấu hình có thể tham chiếu, điển hình tìm JPA entity hoặc Spring Data repository. Tên gọi dễ gây hiểu nhầm: nó **không phải** danh sách các package chứa class `@AutoConfiguration` để Boot quét tìm lớp đó.

Một tên package giống nhau không hợp nhất ba cơ chế này; chúng có đường đăng ký và trách nhiệm khác nhau.

| Câu hỏi | Cơ chế trả lời |
| --- | --- |
| Spring có tự tìm `@Service` trong `dev.demo.app.owned` không? | `@ComponentScan` với base package `dev.demo.app`: **có**. |
| Spring có tự tìm `@Component` trong `dev.demo.infra` không? | Với scan mặc định trên: **không**. |
| Boot có xét `MessageAutoConfiguration` ở `dev.demo.autoconfigure` không? | **Có thể có**, nếu class có trong `AutoConfiguration.imports`, auto-configuration được bật và không bị loại; package không cần nằm trong component scan. |
| Boot có tự xem mọi class trong `dev.demo.autoconfigure` là auto-configuration không? | **Không**. Chỉ có class nằm trong danh sách ứng viên, hoặc được nạp theo cơ chế đăng ký cụ thể khác, mới được xét. |
| Thay `scanBasePackages` có tự đổi base package của JPA entity/repository không? | **Không**; những phạm vi đó có cơ chế riêng và thường tham chiếu `AutoConfigurationPackages`. |

## 2. Dòng xử lý khi khởi động ứng dụng

`@SpringBootApplication` kết hợp ba chức năng chính:

- `@SpringBootConfiguration`: đánh dấu cấu hình gốc của ứng dụng.
- `@ComponentScan`: phát hiện các component theo base package và filter.
- `@EnableAutoConfiguration`: kích hoạt quá trình tìm, lọc và nhập ứng viên auto-configuration.

Có thể hình dung:

```text
DemoApplication (@SpringBootApplication)
    |
    +-- Component scan: dev.demo.app và package con
    |      |
    |      +-- OwnedService (@Service)                 -> có bean
    |      +-- ExternalComponent (ở dev.demo.infra)   -> không thấy bằng scan
    |
    +-- EnableAutoConfiguration
           |
           +-- đọc AutoConfiguration.imports từ các JAR/classpath
           +-- tìm dev.demo.autoconfigure.MessageAutoConfiguration
           +-- kiểm tra các điều kiện (class, bean, property, ...)
           +-- xử lý @Bean đã đủ điều kiện               -> có bean MessageSource
```

Các nhánh đều góp bean definition vào Spring context, nhưng khác nhau về **nguồn danh sách ứng viên** và **điều kiện đăng ký**.

### Component scan chọn *theo package*

Một class chỉ có `@Component` mà nằm ngoài mọi base package được quét thì sẽ không được tìm thấy **qua scan đó**. Nếu bean được khai báo bằng `@Bean`, `@Import`, đăng ký thủ công hoặc auto-configuration, nó vẫn có thể tồn tại trong context. Vì vậy, từ “không được scan” không suy ra “không thể là bean”.

### Auto-configuration chọn *theo imports và điều kiện*

Spring Boot tìm các file `AutoConfiguration.imports` trên classpath, thu thập tên class cấu hình, sau đó áp dụng loại trừ và đánh giá các điều kiện, chẳng hạn `@ConditionalOnClass`, `@ConditionalOnMissingBean` và `@ConditionalOnProperty`. Một ứng viên **được liệt kê** vẫn có thể không tạo bean nào vì điều kiện không khớp.

Một auto-configuration nên được đặt trong package rõ ràng của thư viện, không phụ thuộc vào package scan của ứng dụng dùng thư viện đó. Hướng dẫn chính thức của Boot khuyến cáo **không đưa class auto-configuration vào component scan**, và **không cho auto-configuration tự bật component scan để lấy thêm component**; thay vào đó khai báo bean cụ thể hoặc dùng `@Import` có chủ đích.

## 3. Phạm vi thực tế của @ComponentScan

Đặt class `DemoApplication` ở `dev.demo.app`:

```java
package dev.demo.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Mặc định, Spring tìm các class có stereotype như `@Component`, `@Service`, `@Repository`, `@Controller`, `@RestController`, `@Configuration` trong `dev.demo.app` và package con. Một package cùng tiền tố ký tự nhưng khác nhánh, ví dụ `dev.demo.application`, không phải package con của `dev.demo.app`.

`@ComponentScan` cũng cho phép:

- `basePackages`: chỉ định tên package dạng chuỗi.
- `basePackageClasses`: tham chiếu class để xác định package chứa class đó; giúp đổi tên/refactor package an toàn hơn.
- `includeFilters`, `excludeFilters`, `useDefaultFilters`: chọn lớp theo annotation, kiểu class, regex hoặc filter tùy chỉnh.

Với `@SpringBootApplication`, thuộc tính tiện dụng là `scanBasePackages`/`scanBasePackageClasses` và chỉ áp dụng cho **component scan**. Khi chỉ định phạm vi mới, hãy liệt kê cả package ứng dụng cần giữ lại; nếu chỉ thêm package bên ngoài mà quên root ứng dụng, bean hiện có có thể biến mất khỏi scan.

Một ví dụ thay annotation ứng dụng bằng:

```java
@SpringBootApplication(scanBasePackages = {
    "dev.demo.app",
    "dev.demo.infra"
})
```

sẽ làm component ở cả hai nhánh được quét. Đây là đoạn thay thế annotation, không phải file Java độc lập. Nó **không có nghĩa** Spring Boot cần scan `dev.demo.autoconfigure` để tải auto-configuration.

## 4. Auto-configuration được đăng ký ở đâu?

Đối với Spring Boot 3.x, một JAR hoặc module muốn cung cấp auto-configuration khai báo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung là **tên class đủ package**, mỗi dòng một class, ví dụ:

```text
dev.demo.autoconfigure.MessageAutoConfiguration
```

Class tương ứng:

```java
package dev.demo.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class MessageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSource.class)
    MessageSource messageSource() {
        return () -> "from-auto";
    }
}
```

Đây là cấu trúc minh họa; để biên dịch cần `import dev.demo.api.MessageSource;` và định nghĩa interface ở ví dụ hoàn chỉnh phía dưới.

Quan hệ giữa các khái niệm:

- Tên `dev.demo.autoconfigure.MessageAutoConfiguration` trong file imports **chỉ định trực tiếp class** cần xét. Tên package ở đây là phần định danh Java class, không phải base package để quét tìm hàng loạt class.
- Chỉ đặt `@AutoConfiguration` mà **không đăng ký ứng viên** qua file imports (hoặc một cơ chế import khác có chủ đích) sẽ không khiến Boot tự phát hiện nó qua classpath.
- Thư viện chứa nhiều auto-configuration có thể liệt kê nhiều tên class trong file, mỗi dòng một tên. **Không có wildcard package** kiểu `dev.demo.autoconfigure.*` để tự động chọn mọi class.
- `@AutoConfiguration` được meta-annotate bằng `@Configuration`, nhưng auto-configuration chuẩn phải được kích hoạt qua con đường ứng viên auto-configuration, không dựa vào component scan.
- Spring Boot mặc định dùng các filter dành cho auto-configuration khi thực hiện scan từ `@SpringBootApplication`. Dù vậy, việc đưa package auto-configuration vào vùng quét là thiết kế dễ gây phụ thuộc chéo, đặc biệt với cấu hình tùy biến và test slice; hãy giữ các không gian package riêng.

Trong cấu hình thực tế, các condition quyết định khả năng áp dụng. Ví dụ `@ConditionalOnClass(PartnerSdk.class)` chỉ cho phép cấu hình khi dependency liên quan có mặt; `@ConditionalOnMissingBean(PartnerClient.class)` nhường chỗ nếu ứng dụng đã định nghĩa bean phù hợp. Back-off xảy ra khi xét bean definition, không phải vì package nằm trong hay ngoài vùng component scan.

## 5. Ví dụ runnable: ở ngoài component scan nhưng vẫn có bean auto-configured

Tạo Maven project Java 17 sau để quan sát **cả hai cơ chế đồng thời**.

```text
package-scope-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/demo/
    │   │   ├── api/MessageSource.java
    │   │   ├── app/DemoApplication.java
    │   │   ├── app/owned/OwnedService.java
    │   │   ├── infra/ExternalComponent.java
    │   │   └── autoconfigure/MessageAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/dev/demo/app/PackageScopeTest.java
```

### 5.1. Maven dependencies

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.demo</groupId>
    <artifactId>package-scope-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Không cần web starter hay database, vì bài đang quan sát cơ chế context.

### 5.2. Một interface để auto-configuration tạo bean

`src/main/java/dev/demo/api/MessageSource.java`:

```java
package dev.demo.api;

@FunctionalInterface
public interface MessageSource {
    String message();
}
```

Interface không gắn `@Component`; nó chỉ mô tả hợp đồng dependency.

### 5.3. Một component trong phạm vi scan

`src/main/java/dev/demo/app/owned/OwnedService.java`:

```java
package dev.demo.app.owned;

import org.springframework.stereotype.Service;

@Service
public class OwnedService {
    public String name() {
        return "owned";
    }
}
```

### 5.4. Một component ở ngoài phạm vi scan

`src/main/java/dev/demo/infra/ExternalComponent.java`:

```java
package dev.demo.infra;

import org.springframework.stereotype.Component;

@Component
public class ExternalComponent {
    public String name() {
        return "external";
    }
}
```

Mặc dù có `@Component`, class này không nằm trong `dev.demo.app` hay package con.

### 5.5. Một auto-configuration cũng ở ngoài phạm vi scan

`src/main/java/dev/demo/autoconfigure/MessageAutoConfiguration.java`:

```java
package dev.demo.autoconfigure;

import dev.demo.api.MessageSource;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(MessageSource.class)
public class MessageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSource.class)
    MessageSource messageSource() {
        return () -> "from-auto";
    }
}
```

Đăng ký ứng viên trong `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
dev.demo.autoconfigure.MessageAutoConfiguration
```

Lớp `MessageAutoConfiguration` **không cần nằm trong vùng `@ComponentScan`**. Nó sẽ được Spring Boot xét vì được khai báo trong file imports. Điều kiện `@ConditionalOnClass` khớp vì `MessageSource` có trong project. Nếu chưa có bean `MessageSource` nào khác, `@ConditionalOnMissingBean` khớp và `messageSource` được đăng ký.

### 5.6. Ứng dụng quan sát kết quả

Thay `src/main/java/dev/demo/app/DemoApplication.java` bằng file hoàn chỉnh sau:

```java
package dev.demo.app;

import dev.demo.api.MessageSource;
import dev.demo.app.owned.OwnedService;
import dev.demo.infra.ExternalComponent;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {
            System.out.println(
                "owned.count=" + context.getBeansOfType(OwnedService.class).size()
            );
            System.out.println(
                "external.count=" + context.getBeansOfType(ExternalComponent.class).size()
            );
            System.out.println(
                "message.count=" + context.getBeansOfType(MessageSource.class).size()
            );
            System.out.println(
                "message.value=" + context.getBean(MessageSource.class).message()
            );
        }
    }
}
```

Chạy ở thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

Bốn dòng do chương trình in ra (không tính log startup):

```text
owned.count=1
external.count=0
message.count=1
message.value=from-auto
```

**Đọc kết quả:**

1. `OwnedService` nằm dưới package `dev.demo.app` nên được component scan tìm thấy.
2. `ExternalComponent` chỉ được đánh dấu `@Component` nhưng nằm dưới `dev.demo.infra` nên không được scan mặc định.
3. `MessageAutoConfiguration` nằm dưới `dev.demo.autoconfigure`, cũng ngoài phạm vi scan, nhưng **vẫn được nạp qua file imports**.
4. Bean `MessageSource` xuất hiện do method `@Bean` trong auto-configuration thỏa các condition.

Một quan sát rất quan trọng: **việc Java source có `import dev.demo.infra.ExternalComponent;` trong `DemoApplication` chỉ để trình biên dịch biết kiểu class**. Java `import` không đồng nghĩa Spring `@Import`; nó không đăng ký bean.

### 5.7. Hai thay đổi để chứng minh cơ chế

**Thử nghiệm A — mở component scan:** Thay annotation `@SpringBootApplication` bằng:

```java
@SpringBootApplication(scanBasePackages = {
    "dev.demo.app",
    "dev.demo.infra"
})
```

Khi đó, `external.count=1`; `owned.count=1` và `message.count=1` như cũ. Bạn đã thêm phạm vi scan cho component, **không cần thay file `AutoConfiguration.imports`**.

**Thử nghiệm B — loại auto-configuration:** Trở lại annotation ban đầu, rồi thay bằng:

```java
@SpringBootApplication(
    exclude = dev.demo.autoconfigure.MessageAutoConfiguration.class
)
```

Đây là đoạn annotation thay thế. Vì `MessageSource` không còn được tạo, câu `context.getBean(MessageSource.class)` trong main mẫu sẽ ném `NoSuchBeanDefinitionException`. Nếu muốn chạy và quan sát trạng thái sau khi exclude, **đổi dòng cuối** thành:

```java
System.out.println(
    "message.present=" + !context.getBeansOfType(MessageSource.class).isEmpty()
);
```

Các dòng liên quan khi chạy biến thể B:

```text
owned.count=1
external.count=0
message.count=0
message.present=false
```

Kết quả chứng minh `exclude` tác động đến auto-configuration ứng viên, còn component scan mặc định vẫn độc lập.

**Phân biệt thêm:** Nếu chỉ xóa tên class khỏi file `AutoConfiguration.imports` và không có cách import khác, `MessageAutoConfiguration` không còn là ứng viên tự động được Boot phát hiện; `@AutoConfiguration` đứng riêng không tự tìm ra class.

## 6. Kiểm thử ranh giới và điều kiện bằng JUnit

Đặt file `src/test/java/dev/demo/app/PackageScopeTest.java`:

```java
package dev.demo.app;

import dev.demo.api.MessageSource;
import dev.demo.app.owned.OwnedService;
import dev.demo.autoconfigure.MessageAutoConfiguration;
import dev.demo.infra.ExternalComponent;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = DemoApplication.class)
class PackageScopeTest {

    @Autowired
    ApplicationContext context;

    @Test
    void scanOnlyOwnsApplicationPackageButAutoConfigurationStillLoads() {
        assertThat(context.getBeansOfType(OwnedService.class)).hasSize(1);
        assertThat(context.getBeansOfType(ExternalComponent.class)).isEmpty();
        assertThat(context.getBeansOfType(MessageSource.class)).hasSize(1);
        assertThat(context.getBean(MessageSource.class).message())
            .isEqualTo("from-auto");
    }

    @Test
    void customMessageSourceMakesAutoConfigurationBackOff() {
        new ApplicationContextRunner()
            .withUserConfiguration(UserSourceConfiguration.class)
            .withConfiguration(
                AutoConfigurations.of(MessageAutoConfiguration.class)
            )
            .run(ctx -> {
                assertThat(ctx).hasSingleBean(MessageSource.class);
                assertThat(ctx).doesNotHaveBean("messageSource");
                assertThat(ctx.getBean(MessageSource.class).message())
                    .isEqualTo("from-user");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSourceConfiguration {
        @Bean
        MessageSource userMessageSource() {
            return () -> "from-user";
        }
    }
}
```

Chạy:

```bash
mvn -q test
```

Hai test bảo vệ hai khái niệm riêng:

- Test tích hợp dựng ứng dụng thật và xác minh component scan chỉ thấy `OwnedService`, trong khi imports vẫn đưa auto-configuration vào context.
- Test với `ApplicationContextRunner` chỉ nạp cấu hình người dùng và auto-configuration cần kiểm tra; thấy bean `userMessageSource` thì bean mặc định tên `messageSource` back off. **Cơ chế back-off phụ thuộc bean condition, không phụ thuộc package đặt class.**

Test thứ nhất áp dụng cho cấu hình **mặc định ở bước 5.6**; nếu đã sửa annotation theo thử nghiệm A hoặc B, hãy khôi phục cấu hình gốc trước khi chạy test.

## 7. “Auto-configuration package” trong API nghĩa là gì?

Tên `org.springframework.boot.autoconfigure.AutoConfigurationPackages` rất dễ khiến người học nghĩ đó là các package chứa auto-configuration class. Thực tế, lớp này lưu **base package của ứng dụng** để các chức năng của Boot tham chiếu. Theo quy ước, package chứa class `@EnableAutoConfiguration` (thường là class `@SpringBootApplication`) được đăng ký làm gốc.

Với ứng dụng mẫu:

- Class `DemoApplication` ở `dev.demo.app`.
- Component scan mặc định bắt đầu ở `dev.demo.app`.
- `AutoConfigurationPackages` mặc định cũng chứa `dev.demo.app` theo quy ước.
- Auto-configuration class `MessageAutoConfiguration` lại ở `dev.demo.autoconfigure` và được nạp **theo imports**, không vì `AutoConfigurationPackages` chứa `dev.demo.autoconfigure`.

Hai giá trị đầu bằng nhau **trong cấu hình mặc định**, nhưng chúng thuộc hai cơ chế khác nhau; vì thế không được đồng nhất.

Có thể quan sát trong ứng dụng mẫu bằng cách thêm vào khối try-with-resources trong `main`:

```java
System.out.println(
    "auto.packages=" +
    org.springframework.boot.autoconfigure.AutoConfigurationPackages.get(
        context.getBeanFactory()
    )
);
```

Với class gốc đặt ở `dev.demo.app` và cấu hình mặc định, dòng in thêm là:

```text
auto.packages=[dev.demo.app]
```

`AutoConfigurationPackages.get(...)` nhận `BeanFactory` và đọc thông tin package đã đăng ký; nó không trả về danh sách các class nằm trong `AutoConfiguration.imports`.

### Vì sao JPA entity và Spring Data repository liên quan?

Một số auto-configuration sử dụng danh sách base package này làm phạm vi mặc định cho entity/repository. Trong ứng dụng Spring Boot với JPA, việc đặt class ứng dụng ở package gốc thường giúp Spring tìm entity/repository theo quy ước. Tuy nhiên:

- `@Entity` không phải stereotype của component scan thông thường.
- Repository interface Spring Data được xử lý bởi cơ chế repository scanning.
- Thêm `scanBasePackages="dev.demo.infra"` cho `@SpringBootApplication` **không tự động** thêm `dev.demo.infra` vào danh sách `AutoConfigurationPackages`.
- Nếu entity/repository nằm ở package khác, hãy dùng cấu hình thích hợp như `@EntityScan` và `@EnableJpaRepositories` khi thực sự cần, hoặc tổ chức lại package gốc.

Đừng dùng `@ComponentScan` để sửa một lỗi entity scanning mà chưa xác định cơ chế gây ra lỗi.

## 8. Ba cấu trúc triển khai và kết quả

| Cách bố trí | Kết quả mong đợi | Nhận xét |
| --- | --- | --- |
| `@SpringBootApplication` tại `com.acme.orders`; service dưới `com.acme.orders.domain` | Service được scan | Đây là cấu trúc thông dụng và dễ hiểu. |
| Thư viện có `@AutoConfiguration` ở `com.vendor.cache.autoconfigure`, được liệt kê trong imports | Boot xét auto-configuration nếu dependency hiện diện và auto-configuration bật | Không cần thêm `com.vendor.cache.autoconfigure` vào `@ComponentScan`. |
| Một `@Component` ở `com.vendor.cache.internal`, ứng dụng chỉ scan `com.acme.orders` | Component không được scan theo mặc định | Một class có stereotype trong dependency không tự động thành bean. |
| Ứng dụng chỉ thêm `scanBasePackages="com.vendor.cache.internal"` | Package scan đổi; app component có thể không được tìm thấy nếu bỏ root ứng dụng | Luôn chỉ rõ toàn bộ tập package cần scan. |
| Ứng dụng exclude `CacheAutoConfiguration` | Auto-configuration đó bị loại khỏi danh sách áp dụng | Component scan không vì thế ngừng quét package ứng dụng. |
| Đăng ký trực tiếp `@Import(CustomCacheConfiguration.class)` | Chỉ configuration được import và các bean của nó được xử lý | Hữu ích khi ứng dụng chủ động chọn một cấu hình cụ thể. |

### Cách tổ chức nên áp dụng

Một ứng dụng và starter tích hợp có thể chia ranh giới:

```text
com.acme.orders
├── OrdersApplication.java
├── domain/...
└── infrastructure/...

com.acme.shared.cache
├── CacheClient.java                 (API/service library)
└── autoconfigure/
    └── CacheAutoConfiguration.java (auto-configuration library)
```

Với starter của tổ chức, lớp `CacheAutoConfiguration` nên được đăng ký trong file imports nằm trong JAR autoconfigure. Nó có thể dùng `@ConditionalOnClass` và `@ConditionalOnMissingBean` để không áp đặt một implementation khi ứng dụng đã có bean riêng. Không nên bảo ứng dụng scan toàn `com.acme.shared` như điều kiện bắt buộc để thư viện hoạt động.

## 9. Các lỗi hay gặp và cách chẩn đoán

### Lỗi 1: “Đã thêm starter mà bean @Component của thư viện không xuất hiện”

**Nguyên nhân có thể:** starter đưa JAR vào classpath, nhưng component nằm ngoài root scan và thư viện không cung cấp auto-configuration đăng ký bean đó.

Kiểm tra file imports của JAR, class `@AutoConfiguration` và method `@Bean`. Nếu thư viện chỉ yêu cầu import cấu hình thủ công, theo hướng dẫn của thư viện; không mở rộng scan đến mọi package phụ thuộc một cách tùy tiện.

### Lỗi 2: “@AutoConfiguration nằm ngoài package main nên không chạy”

**Suy luận này không chính xác.** Kiểm tra:

1. File `AutoConfiguration.imports` có nằm đúng `META-INF/spring/` trên classpath của ứng dụng không?
2. Tên fully-qualified trong file có đúng với tên class đã biên dịch không?
3. Có khai báo `@SpringBootApplication` hoặc `@EnableAutoConfiguration` không?
4. Class auto-configuration có bị exclude không?
5. Các `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` có khớp không?

Vị trí package của class auto-configuration không phải bộ lọc chính trong cơ chế này.

### Lỗi 3: “@ComponentScan(basePackages = ...) là đủ để đổi mọi phạm vi tìm kiếm”

`@ComponentScan` có thể thay ranh giới component, nhưng không đồng nghĩa thay danh sách imports, entity scanning, repository scanning hoặc `@ConfigurationPropertiesScan`. Khi lỗi phát sinh, xác định **loại class** đang thiếu: component, entity, repository interface hay auto-configuration.

### Lỗi 4: “Cho package autoconfigure vào scan để chắc chắn nó được nạp”

Thực hành này có thể tạo phụ thuộc vô tình, nạp sai thời điểm hoặc lặp việc đăng ký cấu hình khi phối hợp với import thủ công. Spring Boot khuyến cáo auto-configuration phải được đăng ký qua danh sách ứng viên và không làm đối tượng component scan. Việc thêm `@ComponentScan` thủ công vào cấu hình gốc cũng có thể làm mất các exclude filter dành cho test slice mà meta-annotation Boot cung cấp.

### Lỗi 5: “Sửa scanBasePackages mà JPA vẫn không tìm thấy entity”

Nhớ rằng danh sách `AutoConfigurationPackages` không tự đổi theo `scanBasePackages`. Xem lại package của class gốc, cấu hình `@EntityScan` và `@EnableJpaRepositories` nếu cần. Cũng cần kiểm tra việc tạo entity/repository có điều kiện theo dependency hoặc property.

### Lỗi 6: “Auto-configured bean xuất hiện, nhưng bean mặc định không xuất hiện”

Điều đó có thể là **back-off đúng**. Nếu `@ConditionalOnMissingBean(MessageSource.class)` thấy bean do ứng dụng cung cấp, bean mặc định sẽ không được đăng ký. Khác với việc auto-configuration **không được nạp**. Hãy phân biệt negative condition match với candidate chưa được đăng ký.

### Công cụ chẩn đoán hữu ích

Chạy ứng dụng với flag:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Condition Evaluation Report cho biết auto-configuration nào có positive/negative matches và lý do. Ngoài ra, kiểm tra output sau khi build:

```bash
mvn -q package
jar tf target/package-scope-demo-1.0.0.jar
```

Dùng lệnh `jar tf` để xác nhận tài nguyên imports thực sự nằm trong JAR ở đường dẫn tương ứng (ví dụ Spring Boot executable JAR thường đặt ứng dụng dưới `BOOT-INF/classes/`). Việc tìm file imports tại vị trí chính xác trong JAR giúp phân biệt lỗi đóng gói resource với lỗi scan.

Nếu thêm Spring Boot Actuator, endpoint conditions và beans cũng hữu ích khi được bật expose đúng và được bảo vệ; không nên mở rộng quyền truy cập endpoint chẩn đoán trên production chỉ để xem thử.

## 10. Quy tắc tư duy khi thiết kế module

1. **Ứng dụng chủ động sở hữu component:** đặt class `@SpringBootApplication` trên package gốc chứa phần lớn component ứng dụng; mở rộng scan khi thật sự có ranh giới package khác thuộc ứng dụng.
2. **Thư viện sở hữu auto-configuration:** khai báo auto-configuration bằng `@AutoConfiguration` và file imports; điều kiện classpath/property/bean bảo đảm cấu hình được áp dụng đúng nơi.
3. **Cấu hình tích hợp được chọn thủ công:** dùng `@Import` khi cần đưa vào một class cấu hình xác định, không mở rộng scan vô hạn.
4. **Entity/repository nằm ngoài gốc:** xử lý bằng cơ chế quét chuyên biệt nếu cần, thay vì mặc định cho rằng mọi chức năng phụ thuộc `@ComponentScan`.
5. **Thấy bean bất ngờ hoặc bean thiếu:** xác định nguồn đăng ký bean trong context, sau đó đọc Condition Evaluation Report và danh sách bean; tránh suy luận chỉ từ cấu trúc package.

## 11. Tự kiểm tra hiểu bài

1. `@SpringBootApplication` ở `com.demo.app`. Một `@Service` ở `com.demo.shared` có tự xuất hiện không? **Không** qua scan mặc định; cần nằm trong cây scan hoặc được đăng ký bằng cơ chế khác.
2. `com.vendor.autoconfigure.FooAutoConfiguration` nằm ngoài package ứng dụng nhưng có trong `AutoConfiguration.imports`. Có thể được xét không? **Có**, nếu auto-configuration được bật và không bị loại; điều kiện riêng còn quyết định bean có tạo hay không.
3. Class `@AutoConfiguration` có cần `@ComponentScan` để Spring tìm thấy không? **Không**. Thực hành tốt là không đưa các auto-configuration vào component scan.
4. `@SpringBootApplication(scanBasePackages = "com.demo.shared")` có chắc vẫn scan các service ở `com.demo.app` không? **Không**; cần khai báo root ứng dụng trong tập base package nếu muốn giữ.
5. `AutoConfigurationPackages.get(...)` trả về danh sách mọi class `@AutoConfiguration`? **Không**. Nó trả về base package đã đăng ký, vốn được dùng cho một số mặc định của ứng dụng.
6. `scanBasePackages` có tự thay đổi phạm vi entity scanning không? **Không**; hai loại cấu hình phải được xem riêng.
7. Nếu một auto-configuration được nạp nhưng `@ConditionalOnMissingBean` không khớp, điều gì xảy ra? **Bean mặc định liên quan không được đăng ký**; auto-configuration được xét và back off là hai chuyện khác nhau.
8. Khi thấy lỗi “thiếu bean”, kiểm tra điều gì trước? **Nguồn định nghĩa bean** (component scan, import, bean method, auto-configuration), rồi package, condition, property và log điều kiện tương ứng.

## Nguồn chính thức để đọc tiếp

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): cách khai báo imports, điều kiện và khuyến nghị không quét class auto-configuration.
- [Spring Boot — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html): vị trí main class và root package.
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): cơ chế quét component và filters.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): cách kích hoạt, loại trừ và đánh giá điều kiện.
- [Spring Boot API — AutoConfigurationPackages](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfigurationPackages.html): danh sách package gốc dùng làm mặc định cho các tính năng như JPA entity scanning.
