# @ComponentScan và ranh giới package của cấu hình do ứng dụng sở hữu

> **Bối cảnh:** Spring Boot — auto-configuration; kiến thức nền về nơi Spring tìm các component thuộc ứng dụng. Chủ đề chính là cơ chế `@ComponentScan`, phạm vi package và cách kiểm soát các cấu hình do **ứng dụng** sở hữu. Cần phân biệt rành mạch với cơ chế nạp **auto-configuration** từ Spring Boot và thư viện.

## 1. Vì sao vị trí package ảnh hưởng đến bean?

Spring quản lý các bean trong `ApplicationContext`. Một bean có thể được khai báo bằng `@Bean` trong một class `@Configuration`, được nhập bằng `@Import`, được đăng ký qua API, hoặc được phát hiện khi Spring **quét classpath** bằng `@ComponentScan`.

Cơ chế scan duyệt các package gốc và các package con được cấu hình, tìm những class phù hợp với bộ lọc, rồi đăng ký chúng thành **bean definition**. Khi khởi tạo context, Spring sẽ tạo instance phù hợp từ các định nghĩa này. Spring không tự động quét mọi class trong toàn bộ classpath.

Trong ứng dụng Spring Boot thường gặp:

```text
dev.example.shop
├── ShopApplication.java             <- @SpringBootApplication
├── catalog
│   ├── CatalogService.java          <- @Service
│   └── CatalogController.java       <- @RestController
└── order
    ├── OrderService.java            <- @Service
    └── OrderConfiguration.java       <- @Configuration

dev.example.integration
└── PartnerClient.java                <- @Component
```

Nếu `ShopApplication` nằm trong package `dev.example.shop` và không đổi phạm vi scan:

- Spring thấy các component trong `dev.example.shop` và **mọi package con** như `catalog`, `order`.
- `dev.example.integration.PartnerClient` là **package anh em**, không thuộc cây `dev.example.shop`; chỉ có `@Component` không đủ khiến nó được đăng ký.
- Không cần thêm `@ComponentScan` vào từng service hay controller; phạm vi scan được xác lập từ cấu hình khởi động.
- Spring có thể nạp class ngoài cây scan bằng cách khác, chẳng hạn `@Import` hoặc cấu hình tự động; vì vậy câu “ngoài phạm vi scan” chỉ có nghĩa **không được tìm thấy bằng scan đang xét**, không có nghĩa “không bao giờ thành bean”.

**Khái niệm quan trọng:** package trong Java là tên phân cấp theo dấu chấm, không phải quan hệ kế thừa class. `dev.example.shop.order` nằm dưới `dev.example.shop`; `dev.example.shopping` thì không.

## 2. `@SpringBootApplication` thiết lập component scan như thế nào?

`@SpringBootApplication` kết hợp ba chức năng chính:

```java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(
    excludeFilters = {
        @ComponentScan.Filter(type = FilterType.CUSTOM,
                              classes = TypeExcludeFilter.class),
        @ComponentScan.Filter(type = FilterType.CUSTOM,
                              classes = AutoConfigurationExcludeFilter.class)
    }
)
```

Đây là **diễn giải thành phần chính** của meta-annotation để hiểu cơ chế, không phải một chương trình Java độc lập. Spring Boot sử dụng các filter bổ sung của chính Boot; cú pháp và chi tiết nội bộ có thể khác tùy phiên bản.

- `@SpringBootConfiguration` đánh dấu class cấu hình gốc của ứng dụng (chuyên biệt từ `@Configuration`).
- `@EnableAutoConfiguration` kích hoạt việc xét các ứng viên auto-configuration.
- `@ComponentScan` phát hiện component của ứng dụng trong phạm vi package.

Khi không chỉ định `basePackages` hay `basePackageClasses`, package chứa class khai báo `@ComponentScan` là điểm xuất phát. Với `@SpringBootApplication`, đó thường là package chứa class `main`.

```java
package dev.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Do class nằm ở `dev.example.shop`, phạm vi component scan mặc định là `dev.example.shop` và các package con. Đây là lý do hướng dẫn Spring Boot thường khuyên đặt class khởi động ở package **gốc của mã ứng dụng**.

### Cụm “cấu hình do ứng dụng sở hữu” có nghĩa gì?

Ở đây có thể hiểu là các component và class `@Configuration` mà nhóm phát triển ứng dụng **chủ động viết, chọn và tổ chức** để tạo hành vi nghiệp vụ: service, controller, repository dạng component, adapter, mapper, cấu hình `@Bean`,...

Ranh giới package giúp định nghĩa **mặc định** những class nào ứng dụng tự động tiếp nhận. Một module hoặc thư viện bên ngoài có thể có class `@Component`, nhưng không nên giả định ứng dụng sẽ quét toàn bộ package của thư viện để lấy chúng. Thư viện phát hành auto-configuration có cách đăng ký riêng, trình bày ở phần 6.

## 3. Spring thực sự phát hiện class nào?

Các annotation thường được phát hiện thông qua `@Component` hoặc meta-annotation của nó:

| Annotation | Vai trò chính | Có thể được component scan tìm thấy? |
| --- | --- | --- |
| `@Component` | Component tổng quát | Có, trong phạm vi scan. |
| `@Service` | Service nghiệp vụ | Có; đây là specialization của `@Component`. |
| `@Repository` | Thành phần truy cập dữ liệu | Có; ngoài stereotype, còn hỗ trợ xử lý ngoại lệ truy cập dữ liệu khi được cấu hình phù hợp. |
| `@Controller` | Controller Spring MVC | Có, nếu package được quét và hệ sinh thái MVC tương ứng được cấu hình. |
| `@RestController` | Controller REST (gồm `@Controller` và `@ResponseBody`) | Có, trong phạm vi scan. |
| `@Configuration` | Class định nghĩa cấu hình Spring | Có, cũng là specialization của `@Component`. |
| `@Bean` | Phương thức khai báo bean | Bản thân method không được “quét như một class”; phương thức được xử lý khi class chứa nó đã được nạp làm configuration. |

Thí dụ:

```java
package dev.example.shop.order;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String status() {
        return "ready";
    }
}
```

Với `ShopApplication` ở `dev.example.shop`, class trên được tìm thấy. Ngược lại, một class Java thông thường không có stereotype hoặc không được import/đăng ký sẽ không tự biến thành bean chỉ vì nằm trong package được quét.

### Không phải annotation nào cũng do `@ComponentScan` xử lý

- `@Entity` của JPA là đánh dấu entity, **không phải `@Component`**. Phạm vi entity scanning là cơ chế khác, có thể điều chỉnh bằng `@EntityScan`.
- Interface `JpaRepository` thường được Spring Data tạo proxy thông qua cơ chế repository scanning, không phải do interface đó là `@Component`. Có thể điều chỉnh bằng `@EnableJpaRepositories`; Boot cũng có cấu hình mặc định dựa trên package của ứng dụng.
- `@ConfigurationProperties` mô tả cấu hình kiểu mạnh nhưng có nhiều đường đăng ký: `@EnableConfigurationProperties`, `@ConfigurationPropertiesScan` hoặc một component được quét. Chỉ gắn `@ConfigurationProperties` lên class thường **không đồng nghĩa** class đó được `@ComponentScan` phát hiện.
- Class được nhắc đến trong `@Import` hoặc bean được đăng ký programmatically không nhất thiết nằm trong package scan.

Vì thế, đừng dùng một tham số `scanBasePackages` để kết luận rằng entity, Spring Data repository và mọi loại cấu hình khác cũng tự đổi phạm vi tương ứng.

## 4. Ví dụ chạy được: một component trong cây package và một component ở ngoài

Tạo Maven project Java 17, Spring Boot 3.5.7 theo cấu trúc:

```text
package-boundary-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── dev/example/
    │           ├── app/
    │           │   ├── BoundaryApplication.java
    │           │   └── order/OrderService.java
    │           └── integration/
    │               ├── BillingMarker.java
    │               ├── BillingClient.java
    │               └── BillingConfiguration.java
    └── test/
        └── java/
            └── dev/example/scan/ComponentScanBoundaryTest.java
```

### 4.1. `pom.xml`

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
    <groupId>dev.example</groupId>
    <artifactId>package-boundary-demo</artifactId>
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

Không thêm `spring-boot-starter-web` vì ví dụ chỉ cần context và component scan, không cần server HTTP.

### 4.2. Một bean **nằm trong** cây scan

File `src/main/java/dev/example/app/order/OrderService.java`:

```java
package dev.example.app.order;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String status() {
        return "ready";
    }
}
```

### 4.3. Một bean **nằm ngoài** cây scan

File `src/main/java/dev/example/integration/BillingClient.java`:

```java
package dev.example.integration;

import org.springframework.stereotype.Component;

@Component
public class BillingClient {
    public String provider() {
        return "partner";
    }
}
```

File `src/main/java/dev/example/integration/BillingMarker.java`:

```java
package dev.example.integration;

// Marker không cần @Component; dùng để tham chiếu package an toàn khi refactor.
public interface BillingMarker {
}
```

Hai class nằm trong `dev.example.integration`, là package anh em của `dev.example.app`.

### 4.4. Chạy ứng dụng với scan mặc định

File `src/main/java/dev/example/app/BoundaryApplication.java`:

```java
package dev.example.app;

import dev.example.app.order.OrderService;
import dev.example.integration.BillingClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class BoundaryApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(BoundaryApplication.class, args)) {
            System.out.println(
                "orderService=" + !context.getBeansOfType(OrderService.class).isEmpty()
            );
            System.out.println(
                "billingClient=" + !context.getBeansOfType(BillingClient.class).isEmpty()
            );
        }
    }
}
```

Lệnh chạy ở thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

Hai dòng do chương trình in ra (bỏ qua log startup của Spring Boot):

```text
orderService=true
billingClient=false
```

Đây là dấu hiệu phạm vi scan hoạt động đúng. Import class `BillingClient` trong mã Java chỉ cho compiler biết kiểu của class; câu lệnh `import dev.example.integration.BillingClient;` **không** đăng ký class đó thành Spring bean.

## 5. Khi cần mở rộng phạm vi scan

Có ba cách phổ biến, phục vụ các mục tiêu khác nhau. Chọn dựa trên quyền sở hữu package và độ rộng cần nạp.

### Cách A: tổ chức class khởi động tại package gốc chung

Nếu toàn bộ mã dưới `dev.example` thuộc cùng một ứng dụng, có thể đặt class `BoundaryApplication` trong `dev.example`. Scan mặc định sẽ bao trùm `dev.example.app` và `dev.example.integration`.

Cách này đơn giản với ứng dụng nhỏ hoặc monolith có package root rõ ràng, nhưng **chỉ hợp lý khi chủ động muốn quét tất cả component dưới root đó**. Nếu root quá cao hoặc chứa nhiều module/library chung, phạm vi vô tình nạp có thể lớn và khó kiểm soát.

### Cách B: cấu hình rõ các package cần scan

Có thể dùng thuộc tính `scanBasePackages` hoặc `scanBasePackageClasses` của `@SpringBootApplication`. Ví dụ sửa **duy nhất annotation** trong `BoundaryApplication.java`:

```java
@SpringBootApplication(
    scanBasePackageClasses = {
        BoundaryApplication.class,
        dev.example.integration.BillingMarker.class
    }
)
```

Đây là **đoạn annotation thay thế** trong class đã trình bày ở trên, không phải file Java độc lập. Chạy lại `mvn -q spring-boot:run` sẽ in:

```text
orderService=true
billingClient=true
```

Giải thích: Spring quét package chứa `BoundaryApplication` (`dev.example.app`) và package chứa `BillingMarker` (`dev.example.integration`), bao gồm các package con. Marker là **chỉ dấu package**, không cần là bean.

Có thể dùng literal string:

```java
@SpringBootApplication(scanBasePackages = {
    "dev.example.app",
    "dev.example.integration"
})
```

Cách dùng marker qua `scanBasePackageClasses` an toàn hơn khi IDE refactor tên package. Hãy nhớ: **khai báo giá trị scan tùy chỉnh là chỉ định toàn bộ tập package cần quét**; đừng quên giữ root ứng dụng nếu vẫn muốn các component cũ xuất hiện.

Với cấu hình Spring thuần, có thể viết `@ComponentScan(basePackageClasses = {...})` trên class `@Configuration` được nạp. Tuy nhiên, trong ứng dụng Boot, `scanBasePackageClasses` trực tiếp trên `@SpringBootApplication` thường rõ ý hơn và giữ được các filter đặc biệt trong meta-annotation của Boot.

### Cách C: `@Import` một cấu hình cụ thể, tránh quét cả package

Đôi khi ứng dụng chỉ cần một cấu hình bên ngoài root, không muốn lấy toàn bộ `@Component` trong package đó. File `src/main/java/dev/example/integration/BillingConfiguration.java`:

```java
package dev.example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BillingConfiguration {

    @Bean
    BillingClient billingClient() {
        return new BillingClient();
    }
}
```

Khi **giữ nguyên scan mặc định**, sửa annotation của `BoundaryApplication` thành:

```java
@SpringBootApplication
@Import(dev.example.integration.BillingConfiguration.class)
public class BoundaryApplication {
    // Giữ nguyên main(...) trong ví dụ.
}
```

Cần thêm `import org.springframework.context.annotation.Import;` vào file. Với cách này, `BillingConfiguration` được nhập trực tiếp, method `@Bean` tạo bean `BillingClient`, còn package `dev.example.integration` không bị quét toàn bộ. Hai dòng kiểm tra cũng cho `true` và `true`.

**Không bật đồng thời** ví dụ C với cách B khi không có chủ đích: nếu đã scan `dev.example.integration`, `BillingClient` có thể được tìm từ `@Component`, rồi `@Bean` trong `BillingConfiguration` tạo thêm bean cùng kiểu. Điều đó dễ gây ambiguity khi injection; trong trường hợp hai định nghĩa trùng tên có thể gây lỗi đăng ký. Với thư viện thật, nên chọn **một cơ chế đăng ký rõ ràng**, hoặc dùng điều kiện `@ConditionalOnMissingBean` cho một bean mặc định phù hợp.

Tùy nhu cầu, `@Import(SomeComponent.class)` cũng có thể đăng ký trực tiếp một class cụ thể mà không quét cả package. Import class cấu hình thích hợp hơn khi muốn gom nhiều bean có quan hệ phụ thuộc vào một điểm cấu hình.

## 6. Phân biệt component scan và auto-configuration

Đây là điểm mấu chốt của module “Spring Boot - auto-configuration”:

| Nội dung | Component scan | Spring Boot auto-configuration |
| --- | --- | --- |
| Nhiệm vụ | Tìm class ứng dụng trong các package được chỉ định | Đề xuất cấu hình/bean mặc định phù hợp với môi trường và dependency |
| Điểm vào | `@ComponentScan`, mặc định từ `@SpringBootApplication` | `@EnableAutoConfiguration`, mặc định từ `@SpringBootApplication` |
| Danh sách ứng viên | Class trên classpath thỏa filter trong cây package scan | Các lớp auto-configuration được khai báo, điển hình trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Điều kiện | Phạm vi package, include/exclude filters và stereotype | `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`,... |
| Người sở hữu điển hình | Mã application và cấu hình ứng dụng chủ động chọn | Spring Boot hoặc starter/library cung cấp cấu hình |
| Khi có bean do người dùng cung cấp | Scan vẫn có thể đăng ký bean cùng kiểu; không tự back off | Bean mặc định có thể back off nếu được bảo vệ bằng điều kiện tương ứng |

**Quan hệ trong thực tế:**

1. `@SpringBootApplication` kích hoạt **cả hai** cơ chế.
2. Component scan tìm các bean/configuration của người dùng trong phạm vi package định nghĩa.
3. Các auto-configuration được nhập riêng, thường đánh giá sau các định nghĩa cấu hình người dùng để điều kiện như `@ConditionalOnMissingBean` nhìn thấy bean ứng dụng đã khai báo.
4. Nếu application khai báo bean của mình, một auto-configuration có `@ConditionalOnMissingBean` phù hợp có thể không tạo bean mặc định.
5. Đổi `scanBasePackages` **không phải** thao tác bật/tắt thư viện auto-configuration. Muốn loại một auto-configuration có thể dùng `exclude` của `@SpringBootApplication` hoặc `spring.autoconfigure.exclude`, sau khi hiểu rõ ảnh hưởng.

Trong starter/library tùy biến, nên tránh suy nghĩ “đặt các class `@Component` trong package của dependency thì ứng dụng sẽ tự tìm thấy”. Nếu muốn cung cấp auto-configuration thực sự, thư viện nên khai báo lớp `@AutoConfiguration` và liệt kê đúng tên class trong `AutoConfiguration.imports`. Một auto-configuration điển hình dùng `@Bean` cùng các condition, thay vì chủ động component-scan package của ứng dụng để tìm class ngẫu nhiên.

**Tách hai phạm vi:** `scanBasePackages` cấu hình component scan; các package mặc định khác mà Boot suy ra từ vị trí `@EnableAutoConfiguration` không nhất thiết thay đổi theo tham số này. Điều này đặc biệt quan trọng với JPA entity và Spring Data repository.

## 7. Lọc component khi package chưa thể tổ chức lại

Có trường hợp nhiều component cùng nằm trong một package nhưng ứng dụng chỉ muốn phát hiện một nhóm. `@ComponentScan` hỗ trợ `includeFilters` và `excludeFilters`, với các kiểu `FilterType.ANNOTATION`, `ASSIGNABLE_TYPE`, `REGEX`, `ASPECTJ`, `CUSTOM`,...

Ví dụ chọn package nhưng bỏ qua một class:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(
    basePackages = "dev.example.integration",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyBillingAdapter.class
    )
)
class IntegrationScanConfiguration {
}
```

Đây là **đoạn minh họa**, cần có các `import` phù hợp và class `LegacyBillingAdapter` thật mới biên dịch. Với `includeFilters`, nếu chỉ muốn nhận class khớp filter và loại default stereotype, có thể đặt `useDefaultFilters = false` để tránh tiếp tục nhận mọi class gắn `@Component`.

Lưu ý khi viết cấu hình:

- Filter được áp dụng trong **lượt scan đó**, không phải cơ chế loại bean đã được đăng ký qua cách khác.
- `excludeFilters` ở một `@ComponentScan` không tự động xóa bean được khai báo bằng `@Bean` hoặc `@Import`.
- Đặt `@ComponentScan` trực tiếp trên class đã có `@SpringBootApplication` có thể khiến các filter mặc định do meta-annotation của Boot cung cấp không được áp dụng như dự tính. Boot dùng `TypeExcludeFilter` trong các test slice và `AutoConfigurationExcludeFilter`; thay đổi tùy tiện có thể làm test nạp quá nhiều component. Ưu tiên tham số `scanBasePackageClasses` nếu chỉ cần đổi ranh giới package.
- Filter phức tạp thường báo hiệu ranh giới package/module chưa rõ; xem lại cấu trúc hoặc dùng `@Import` cho cấu hình hẹp.

## 8. Kiểm thử độc lập ranh giới quét

Kiểm thử này dùng `AnnotationConfigApplicationContext` của Spring Framework để chỉ kiểm tra **component scan**, không cần khởi động Boot hoặc những auto-configuration khác. Nó kiểm tra hai nhánh: chỉ quét service nội bộ, sau đó quét cả integration.

File `src/test/java/dev/example/scan/ComponentScanBoundaryTest.java`:

```java
package dev.example.scan;

import dev.example.app.order.OrderService;
import dev.example.integration.BillingClient;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ComponentScanBoundaryTest {

    @Test
    void defaultOwnedPackageContainsOnlyOrderService() {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(OrdersOnlyScan.class)) {
            assertThat(context.getBeansOfType(OrderService.class)).hasSize(1);
            assertThat(context.getBeansOfType(BillingClient.class)).isEmpty();
        }
    }

    @Test
    void explicitPackagesIncludeExternalBillingClient() {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(ExpandedScan.class)) {
            assertThat(context.getBeansOfType(OrderService.class)).hasSize(1);
            assertThat(context.getBeansOfType(BillingClient.class)).hasSize(1);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackageClasses = OrderService.class)
    static class OrdersOnlyScan {
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackageClasses = {
        OrderService.class, BillingClient.class
    })
    static class ExpandedScan {
    }
}
```

Chạy:

```bash
mvn -q test
```

Với cấu trúc file đã nêu và không thêm component gây ảnh hưởng, **hai test phải pass**. Chúng không phụ thuộc việc ứng dụng đang dùng biến thể annotation ở cách A/B/C vì dùng `@ComponentScan` riêng trong hai class cấu hình test; test còn xác nhận cách chỉ định `basePackageClasses` bằng marker/class hoạt động theo **package chứa class** chứ không chỉ lấy riêng class đó.

Nếu muốn kiểm tra cả Spring Boot auto-configuration và injection thật, bổ sung integration test với `@SpringBootTest` cho ứng dụng; trong các module nhiều dependency, điều đó giúp bắt lỗi do những bean ngoài dự tính được scan và các condition back-off bị ảnh hưởng.

## 9. Sự cố và cách chẩn đoán

### 9.1. `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException`

Ví dụ constructor của `OrderService` yêu cầu `BillingClient` nhưng `BillingClient` nằm ngoài package scan. Spring tạo `OrderService` và không tìm được bean `BillingClient`.

Hướng kiểm tra:

1. Xác định **package thực** (câu `package ...;`) của class gốc `@SpringBootApplication`.
2. Xác định package của class bị thiếu; hỏi xem nó có nằm trong cây scan không.
3. Xác nhận class có stereotype hoặc được đăng ký bằng `@Bean`/`@Import` không. Chỉ có dependency trên classpath chưa đủ.
4. Xem có profile/condition/filter nào khiến class không được đăng ký không (ví dụ `@Profile`, `@Conditional`).
5. Kiểm tra tên bean/qualifier và trường hợp có nhiều bean cùng kiểu; lỗi “không có bean” và “nhiều ứng viên bean” là hai vấn đề khác nhau.

Để quan sát bean thực có:

```java
String[] names = context.getBeanNamesForType(BillingClient.class);
System.out.println(java.util.Arrays.toString(names));
```

Đây là **đoạn code thêm vào main khi đang có biến `context`**, không phải chương trình độc lập. Nếu trả về `[]`, hiện tại không có bean kiểu đó trong context mà lệnh đang đọc. Nếu bật Actuator endpoint `/actuator/beans`, nó có thể hỗ trợ kiểm tra danh sách bean; cần thêm dependency, cấu hình expose và bảo vệ truy cập phù hợp.

### 9.2. Một component được nạp bất ngờ

Kiểm tra liệu package gốc có đặt **quá cao** như `dev.example` hay không, khiến các class trong module không muốn nạp vẫn nằm dưới root. Kiểm tra `@Import`, các `@Configuration` được quét, hoặc dependency có auto-configuration riêng. Không kết luận ngay rằng lỗi do component scan.

### 9.3. Nhiều bean cùng loại hoặc trùng tên

Nếu một class đã được quét qua `@Component`, rồi bạn còn khai báo `@Bean` cùng kiểu, có thể có hai bean và gây `NoUniqueBeanDefinitionException` khi inject bằng type. Nếu cùng tên, hành vi còn tùy chính sách bean definition overriding, thường không nên dựa vào việc overriding.

`@Primary` hoặc `@Qualifier` giúp chọn bean trong một số trường hợp, nhưng không khắc phục gốc rễ của việc scan quá rộng; tốt nhất xác định cơ chế sở hữu và đăng ký bean.

### 9.4. Chạy production được nhưng test slice thất bại

Test slice như `@WebMvcTest` có cơ chế giới hạn bean được nạp. Nếu custom `@ComponentScan` trên class ứng dụng làm mất các exclude filter mặc định của Boot, test có thể thấy service/repository không mong muốn. Ưu tiên một application class gốc chuẩn và dùng `scanBasePackageClasses` khi cần mở rộng package; nếu phải đặt explicit `@ComponentScan`, hiểu và cấu hình filter phù hợp.

### 9.5. Đổi component scan nhưng JPA entity/repository vẫn bị thiếu

Hãy tách trách nhiệm: `@ComponentScan` không tự quản lý `@EntityScan` và `@EnableJpaRepositories`. Xem vị trí class `@SpringBootApplication`, các package mặc định của JPA/Spring Data và cấu hình scan chuyên biệt. Đừng chữa vấn đề entity/repository bằng cách nới component scan lên toàn classpath.

## 10. Thực hành tổ chức cấu hình ứng dụng

Một cấu trúc package có thể bảo trì tốt:

```text
com.acme.sales
├── SalesApplication.java
├── orders
│   ├── OrderService.java
│   ├── OrderController.java
│   └── OrdersConfiguration.java
├── customers
│   ├── CustomerService.java
│   └── CustomersConfiguration.java
└── infrastructure
    └── SecurityConfiguration.java

com.acme.shared.logging
└── SharedLoggingAutoConfiguration.java
```

Gợi ý thiết kế:

- Giữ class `@SpringBootApplication` ở **package gốc của ứng dụng** để scan mặc định bao hết mã do ứng dụng sở hữu.
- Tổ chức theo tính năng hoặc ranh giới module; dùng package như một phần tài liệu kiến trúc và một cách thể hiện phạm vi sở hữu.
- Với cấu hình thuộc thư viện khác, ưu tiên nhập **class cấu hình có chủ đích** hoặc cơ chế auto-configuration của library thay vì scan cả package của dependency.
- Tránh `@ComponentScan("com")`, `@ComponentScan("org")` hoặc root package quá rộng: tăng độ khó dự đoán, xung đột bean, thời gian scan và mức độ phụ thuộc giữa các module.
- Nếu có nhiều context, ví dụ parent/child context trong một hệ thống phức tạp, kiểm tra component thực sự thuộc context nào; package scan không thay thế ranh giới context.
- Tách các configuration mang tính tùy chọn (profile, property, dependency) và dùng điều kiện ở nơi phù hợp; việc class được scan không đảm bảo mọi `@Bean` trong đó đều được đăng ký nếu có condition.

## 11. Câu hỏi tự kiểm tra

1. `App` nằm ở `com.demo.a`, `@Service` nằm ở `com.demo.ab`. Scan mặc định có thấy service không? **Không**; hai package là anh em, dù chuỗi tên có tiền tố gần giống.
2. `App` nằm ở `com.demo`, service nằm ở `com.demo.orders.internal`. Có được quét không? **Có**, nếu không bị filter/condition loại và class là ứng viên component.
3. Một class trong dependency có `@Component`, không nằm trong package scan. Chỉ thêm dependency có tạo bean không? **Không** theo component scan; có thể tồn tại cách đăng ký khác, như auto-configuration hoặc `@Import`.
4. Khi khai báo `@SpringBootApplication(scanBasePackageClasses = PartnerMarker.class)`, các service nằm ở package chứa `App` có chắc còn được quét không? **Không** nếu package đó không nằm trong cây scan từ `PartnerMarker`. Phải khai báo cả root cần giữ.
5. `@Entity` và `JpaRepository` có tự được phát hiện nhờ mở rộng `scanBasePackages` không? **Không thể kết luận như vậy**; JPA và Spring Data có cơ chế scan riêng.
6. Một auto-configuration có `@ConditionalOnMissingBean(X.class)` có nhường chỗ khi component scan đã đăng ký bean `X` của ứng dụng không? **Thường có**, nếu bean definition tương ứng đã được xử lý và điều kiện đó xét đúng kiểu/tên/context.
7. Cần đúng một cấu hình ở package ngoài root; lựa chọn rõ ràng nào ít gây quét thừa? **`@Import` cấu hình cụ thể**, miễn là hiểu các bean nó đăng ký.
8. Vì sao test slice có thể hỏng sau khi thêm explicit `@ComponentScan`? **Có thể mất exclude filters do meta-annotation của Boot cung cấp**, làm nhiều component không thuộc slice bị nạp.

## Tài liệu tham khảo

- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): cách `@ComponentScan` tìm component, stereotype, bộ lọc và package.
- [Spring Boot Reference — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html): vị trí class `@SpringBootApplication` và package mặc định.
- [Spring Boot Reference — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): auto-configuration và điều kiện nhường chỗ.
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): đăng ký `AutoConfiguration.imports` và lý do tránh component scan trong auto-configuration.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): phạm vi context và các test slice.
