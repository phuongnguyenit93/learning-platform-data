# Chế độ lite và @Configuration(proxyBeanMethods = false) trong Spring Core Container

## 1. Mục tiêu học tập

Khi viết Java configuration cho Spring, hai cách khai báo sau đều tạo bean definitions nhưng **khác nhau về hành vi khi một phương thức `@Bean` gọi phương thức `@Bean` khác**:

```java
@Configuration
class FullConfig {
    // Các phương thức @Bean
}
```

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {
    // Các phương thức @Bean
}
```

Mặc định, `@Configuration` có `proxyBeanMethods = true`. Spring xử lý class này theo **full configuration mode**: tăng cường (*enhance*) đối tượng cấu hình bằng subclass dựa trên CGLIB để một lời gọi tới phương thức `@Bean` của đối tượng cấu hình đã được Spring quản lý có thể được chuyển thành yêu cầu lấy bean từ container, qua đó giữ đúng scope và các hành vi liên quan.

Khi viết `@Configuration(proxyBeanMethods = false)`, bạn **tắt interception của các lời gọi phương thức `@Bean`**. Spring vẫn đăng ký các bean definitions và quản lý những bean nó tạo, nhưng nếu trong Java code bạn tự gọi `anotherBean()` thì đó chỉ là **lời gọi Java bình thường**, không phải `BeanFactory.getBean(...)` ngầm. Spring gọi đây là **lite mode**; các phương thức `@Bean` nằm trong class `@Component` thông thường cũng thuộc nhóm lite.

Sau bài này, bạn sẽ:

- Phân biệt **full `@Configuration`**, **`@Configuration(proxyBeanMethods=false)`** và **`@Bean` trong plain `@Component`**.
- Hiểu chính xác lúc nào Spring bảo toàn singleton identity, scope và bean lifecycle, lúc nào một lời gọi trực tiếp tạo đối tượng ngoài container.
- Biết vì sao **tham số phương thức `@Bean`** là cách biểu diễn inter-bean dependency an toàn trong cả hai chế độ.
- Biết ưu, nhược điểm và ràng buộc kỹ thuật của CGLIB enhancement.
- Phân biệt `proxyBeanMethods` với proxy Spring AOP, `@Lazy`, `@Scope` và `ObjectProvider`.
- Chạy ví dụ Java 17 + Spring Framework thuần và đọc output có thể kiểm chứng.
- Chuyển cấu hình full sang lite mà không âm thầm thay đổi hành vi.

**Thông điệp trọng tâm:** Lite mode **không tắt quản lý bean của Spring**. Nó chỉ không intercept **lời gọi Java trực tiếp giữa những `@Bean` methods**. Muốn truyền đúng bean do container quản lý, khai báo dependency qua **tham số factory method** hoặc cơ chế dependency injection phù hợp.

## 2. `@Configuration` và `@Bean` vẫn hoạt động trong lite mode

`@Configuration` đánh dấu nguồn Java configuration; `@Bean` công bố factory method mà container dùng để tạo và quản lý bean. Ví dụ minh họa (cần định nghĩa `Catalog` và `CatalogConsumer`):

```java
@Configuration(proxyBeanMethods = false)
class CatalogConfig {
    @Bean Catalog catalog() { return new Catalog(); }
    @Bean CatalogConsumer consumer(Catalog catalog) {
        return new CatalogConsumer(catalog);
    }
}
```

Spring vẫn đăng ký hai bean definitions và resolve tham số `Catalog` qua BeanFactory. Cần phân biệt **đăng ký definition**, **container gọi factory method**, và **Java code tự gọi factory method**; chỉ trường hợp cuối chịu ảnh hưởng trực tiếp của `proxyBeanMethods`.

## 3. Full mode: cơ sở để hiểu lite mode

`@Configuration` mặc định `proxyBeanMethods=true`; Spring có thể tạo subclass CGLIB để chặn các lời gọi instance `@Bean` methods phù hợp trên enhanced configuration object.

```java
@Configuration
class FullConfig {
    @Bean Catalog catalog() { return new Catalog(); }
    @Bean CatalogConsumer consumer() {
        return new CatalogConsumer(catalog());
    }
}
```

Ví dụ minh họa dùng hai kiểu `Catalog`/`CatalogConsumer`. Trong full mode, `catalog()` được gọi từ `consumer()` trên enhanced config có thể được chuyển thành lookup bean `catalog`, bảo toàn singleton reference hoặc scope phù hợp. Trong lite mode, đó là lời gọi Java bình thường và có thể tạo một object khác.

### Điều kiện cần để interception xảy ra

Interception gắn với **configuration bean được Spring quản lý và tăng cường**; `new FullConfig().catalog()` ngoài context không có ngữ nghĩa ấy. `static @Bean` không có virtual dispatch để CGLIB override. Bài này tiếp tục ở thao tác dùng lite và refactor dependency; bài full mode và giới hạn factory methods đào sâu CGLIB.

## 4. Lite mode là gì?

Trong Spring, phương thức `@Bean` được xử lý theo **lite mode** khi:

- Nó nằm trong class **không có `@Configuration`**, nhưng class đó là thành phần được Spring xử lý, ví dụ một bean `@Component`.
- Hoặc nó nằm trong class có `@Configuration(proxyBeanMethods = false)`.

Ví dụ lite rõ nhất:

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {

    @Bean
    Catalog catalog() {
        return new Catalog();
    }

    @Bean
    CatalogConsumer consumer() {
        return new CatalogConsumer(catalog());
    }
}
```

Spring vẫn đăng ký hai bean `catalog` và `consumer`. Nhưng bên trong `consumer()`, lời gọi `catalog()` không được intercept. Khi Java chạy `new CatalogConsumer(catalog())`, phương thức `catalog()` có thể tạo **một `Catalog` riêng**, ngoài instance Spring quản lý dưới bean name `catalog`.

Điều đáng chú ý:

- Container vẫn có **một singleton bean `catalog`** nếu mặc định scope singleton.
- Object do lời gọi trực tiếp `catalog()` tạo ra trong `consumer()` có thể **không phải** singleton đó.
- Object tạo trực tiếp không tự được áp dụng `BeanPostProcessor`, các proxy, init/destroy callbacks hoặc scope của bean definition `catalog`.
- Việc hai object cùng class `Catalog` không làm chúng trở thành cùng một managed bean.
- `@Configuration(proxyBeanMethods=false)` vẫn là annotation cấu hình, vẫn có thể được component scan tìm thấy và vẫn có thể khai báo `@Import`, `@Bean` hoặc metadata liên quan như bình thường.

Spring dùng từ “lite” để nói về **xử lý factory methods không có CGLIB inter-bean interception**, không phải Spring tắt dependency injection hoặc giảm bean thành “object không quản lý”.

### Lite @Bean trong @Component thông thường

```java
@Component
class CatalogFactoryComponent {

    @Bean
    Catalog catalog() {
        return new Catalog();
    }

    @Bean
    CatalogConsumer consumer() {
        return new CatalogConsumer(catalog());
    }
}
```

Các đoạn trên dùng annotation `org.springframework.stereotype.Component` và phải được **đăng ký hoặc phát hiện** trong context mới có hiệu lực. Vì class chỉ là `@Component` thông thường, factory methods là **lite `@Bean`**. Việc gọi `catalog()` từ `consumer()` có nghĩa Java thông thường giống ví dụ `LiteConfig`.

Không cần biến mọi class chứa `@Bean` thành `@Configuration` nếu chúng có ý định làm component thông thường, nhưng khi một class chủ yếu đóng vai trò cấu hình bean definitions, `@Configuration(proxyBeanMethods=false)` làm ý định rõ hơn.

## 5. So sánh full và lite bằng hợp đồng cụ thể

| Khía cạnh | Full `@Configuration` | Lite `@Configuration(proxyBeanMethods=false)` hoặc plain `@Component` |
| --- | --- | --- |
| Phương thức `@Bean` được đăng ký vào container | Có | Có |
| Các bean được Spring quản lý khi container tạo | Có | Có |
| Scoped/lifecycle semantics của `context.getBean(...)` | Có | Có |
| CGLIB enhance class cấu hình để intercept bean methods | Có | Không dùng enhancement này |
| Một `@Bean` method gọi trực tiếp `otherBean()` | Có thể được intercept theo BeanFactory | Chỉ là lời gọi Java bình thường |
| Có thể tạo thêm object ngoài container khi gọi method trực tiếp | Có nếu gọi trên **instance không được Spring enhance** hoặc trường hợp không intercept | Có, ngay cả khi method được gọi từ một factory method khác |
| Factory method nhận tham số dependency do Spring tiêm | Có | Có |
| Cần tuân thủ ràng buộc subclassing `final`/`private` cho intercepted methods | Có | Được nới lỏng vì không cần inter-bean subclass |
| Dùng để định nghĩa những bean độc lập không gọi lẫn nhau | Có | Có, thường là lựa chọn gọn |
| Phù hợp với code cố ý dùng direct inter-bean method calls | Có, nếu hiểu rõ điều kiện full | Không |

**Lưu ý về tối ưu:** `proxyBeanMethods=false` có thể tránh chi phí tạo CGLIB subclass cho class cấu hình, giảm footprint/enhancement overhead. Đây thường là tối ưu cấu hình hợp lý, nhưng **không nên** đổi chỉ vì muốn “nhanh hơn” trước khi rà soát mọi lời gọi trực tiếp giữa các `@Bean` methods.

## 6. Cách viết đúng trong cả full và lite: tiêm dependency qua tham số @Bean

Đây là mẫu nên ưu tiên:

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {

    @Bean
    Catalog catalog() {
        return new Catalog();
    }

    @Bean
    CatalogConsumer consumer(Catalog catalog) {
        return new CatalogConsumer(catalog);
    }
}
```

`Catalog` là class ứng dụng minh họa. Khi Spring gọi factory method `consumer(Catalog catalog)`, Spring **giải quyết tham số `Catalog` thông qua container**:

1. Container biết method `consumer` cần bean kiểu `Catalog`.
2. Spring tìm ứng viên `Catalog` theo kiểu, qualifier, primary, generic và các quy tắc khác.
3. Nếu dùng singleton mặc định, nó truyền singleton bean `catalog` đã có hoặc tạo bean đó đúng cơ chế.
4. `CatalogConsumer` nhận reference tới **managed bean**, không phải một object khác do method call tự tạo.

Cách viết này hoạt động trong:

- Full `@Configuration(proxyBeanMethods=true)`.
- Lite `@Configuration(proxyBeanMethods=false)`.
- Lite `@Bean` methods trong `@Component` thông thường.
- Các cấu hình nhiều class khi dependency bean được đăng ký/import vào cùng context.

**Ưu điểm lớn:** dependency hiện ngay trong chữ ký method, dễ tìm, dễ test, không cần dựa vào CGLIB để duy trì bean identity.

### Mẫu nên tránh trong lite mode

```java
@Bean
CatalogConsumer consumer() {
    return new CatalogConsumer(catalog()); // Lời gọi Java thuần.
}
```

### Mẫu nên dùng

```java
@Bean
CatalogConsumer consumer(Catalog catalog) {
    return new CatalogConsumer(catalog); // Spring inject bean.
}
```

Ngay cả khi code hiện đang chạy full mode, chuyển từ direct call sang method parameter trước giúp cấu hình an toàn hơn nếu sau này cần chuyển sang lite mode.

## 7. Ví dụ Java 17 chạy được: so sánh full, lite và @Component

Ví dụ độc lập dưới đây dùng Spring Framework 6.2 và không cần Spring Boot. Mỗi chế độ được tạo trong **ApplicationContext riêng** để tránh trùng bean names và trùng kiểu.

Chương trình sẽ kiểm tra ba kết quả:

- Bao nhiêu lần method factory `catalog()` thực sự chạy.
- `directConsumer()` có nhận đúng `Catalog` singleton do container quản lý hay không.
- `injectedConsumer(Catalog catalog)` có nhận đúng singleton do Spring inject hay không.

### 7.1. Cấu trúc dự án

```text
spring-lite-configuration/
├── pom.xml
└── src/main/java/demo/LiteConfigurationDemo.java
```

### 7.2. POM cho Java 17

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-lite-configuration</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. Mã nguồn đầy đủ

Tạo `src/main/java/demo/LiteConfigurationDemo.java`:

```java
package demo;

import java.util.function.IntSupplier;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

public class LiteConfigurationDemo {

    static final class Catalog {
    }

    static final class CatalogConsumer {
        private final Catalog catalog;

        CatalogConsumer(Catalog catalog) {
            this.catalog = catalog;
        }

        Catalog catalog() {
            return catalog;
        }
    }

    private static int fullCalls;
    private static int liteCalls;
    private static int componentCalls;

    @Configuration
    static class FullConfig {

        @Bean
        Catalog catalog() {
            fullCalls++;
            return new Catalog();
        }

        @Bean
        CatalogConsumer directConsumer() {
            return new CatalogConsumer(catalog());
        }

        @Bean
        CatalogConsumer injectedConsumer(Catalog catalog) {
            return new CatalogConsumer(catalog);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class LiteConfig {

        @Bean
        Catalog catalog() {
            liteCalls++;
            return new Catalog();
        }

        @Bean
        CatalogConsumer directConsumer() {
            return new CatalogConsumer(catalog());
        }

        @Bean
        CatalogConsumer injectedConsumer(Catalog catalog) {
            return new CatalogConsumer(catalog);
        }
    }

    @Component
    static class ComponentFactory {

        @Bean
        Catalog catalog() {
            componentCalls++;
            return new Catalog();
        }

        @Bean
        CatalogConsumer directConsumer() {
            return new CatalogConsumer(catalog());
        }

        @Bean
        CatalogConsumer injectedConsumer(Catalog catalog) {
            return new CatalogConsumer(catalog);
        }
    }

    private static void report(
            String label, Class<?> configurationClass, IntSupplier calls) {

        try (var context = new AnnotationConfigApplicationContext(
                configurationClass)) {

            Catalog managed = context.getBean(Catalog.class);
            CatalogConsumer direct =
                    context.getBean("directConsumer", CatalogConsumer.class);
            CatalogConsumer injected =
                    context.getBean("injectedConsumer", CatalogConsumer.class);

            System.out.println(label + ".factoryCalls=" + calls.getAsInt());
            System.out.println(label + ".directIsManaged=" +
                    (direct.catalog() == managed));
            System.out.println(label + ".parameterIsManaged=" +
                    (injected.catalog() == managed));
        }
    }

    public static void main(String[] args) {
        report("full", FullConfig.class, () -> fullCalls);
        report("lite", LiteConfig.class, () -> liteCalls);
        report("component", ComponentFactory.class, () -> componentCalls);
    }
}
```

**Giải thích cấu trúc:** Mỗi context đăng ký một class cấu hình/component và có đúng một bean `Catalog`, hai bean `CatalogConsumer` mang tên `directConsumer` và `injectedConsumer`. Ta tra các consumer **bằng tên kèm kiểu** để tránh nhập nhằng vì có hai bean cùng type `CatalogConsumer`.

`FullConfig` không `final`, và các `@Bean` instance methods cũng không `final`/`private`; như vậy có thể được Spring enhance cho full mode. `LiteConfig` tắt enhancement, còn `ComponentFactory` được đăng ký trực tiếp vào context để Spring xử lý các `@Bean` methods theo lite mode, dù không cần bật component scan trong ví dụ.

### 7.4. Lệnh chạy

Chạy trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.LiteConfigurationDemo
```

Cần JDK 17+ và Maven. **Những dòng do chính chương trình in ra** (không tính log của Spring/Maven nếu môi trường có cấu hình logging khác):

```text
full.factoryCalls=1
full.directIsManaged=true
full.parameterIsManaged=true
lite.factoryCalls=2
lite.directIsManaged=false
lite.parameterIsManaged=true
component.factoryCalls=2
component.directIsManaged=false
component.parameterIsManaged=true
```

### 7.5. Vì sao full.factoryCalls = 1?

Trong full mode, `catalog()` được Spring intercept ở lời gọi từ `directConsumer()` để lấy bean singleton. Container chỉ cần thực thi factory logic để tạo một bean `Catalog` được quản lý. Việc tạo `injectedConsumer(Catalog catalog)` cũng chỉ phân giải singleton đang có.

Kết quả:

- `full.directIsManaged=true`.
- `full.parameterIsManaged=true`.
- `full.factoryCalls=1`.

Điểm quan trọng: giá trị `true` của direct call chỉ đúng vì nó diễn ra trên **Spring-enhanced configuration instance** theo full semantics. Nếu tự gọi `new FullConfig().catalog()` thì CGLIB không intercept instance đó.

### 7.6. Vì sao lite.factoryCalls = 2?

Trong lite mode:

1. Spring tạo bean `catalog` thông qua factory method một lần theo singleton scope.
2. Khi tạo bean `directConsumer`, code trong method gọi `catalog()` trực tiếp theo Java, chạy factory logic thêm một lần để tạo một `Catalog` **khác**.
3. Khi tạo `injectedConsumer`, Spring truyền bean `Catalog` container-managed qua tham số.

Do đó:

- `lite.directIsManaged=false`: consumer tạo bằng direct call giữ object ngoài managed bean.
- `lite.parameterIsManaged=true`: consumer qua parameter giữ singleton đúng.
- `lite.factoryCalls=2`: một lần do BeanFactory tạo bean, một lần do direct Java call.

Ngay cả khi Spring khởi tạo các singleton theo thứ tự khác nhau, tổng số lần gọi factory method vẫn là 2 trong ví dụ này, vì có một bean definition `Catalog` và đúng một direct call từ `directConsumer`.

### 7.7. Vì sao @Component cũng cho kết quả lite?

`ComponentFactory` không có `@Configuration`. Tuy nó có các phương thức `@Bean` và đã được đăng ký vào context, Spring không enhance nó để intercept những lời gọi giữa các bean methods. Vì thế nó có cùng hành vi direct Java call như `LiteConfig`:

- `component.factoryCalls=2`.
- `component.directIsManaged=false`.
- `component.parameterIsManaged=true`.

Ví dụ này chứng minh **lite mode không có nghĩa “không tìm thấy @Bean”**. Cả ba context đều tạo bean `Catalog` và hai bean `CatalogConsumer`; điều khác biệt nằm ở cách phân giải reference trong method call trực tiếp.

## 8. Rà soát mã trước khi chuyển full sang lite

Giả sử cấu hình hiện tại là:

```java
@Configuration
class OriginalConfig {

    @Bean
    DataSource dataSource() {
        return createDataSource();
    }

    @Bean
    UserRepository userRepository() {
        return new JdbcUserRepository(dataSource());
    }

    @Bean
    UserService userService() {
        return new UserService(userRepository());
    }
}
```

Đây là **đoạn minh họa**, cần khai báo các kiểu `DataSource`, `JdbcUserRepository`, `UserRepository` và `UserService`. Nó hoạt động theo full inter-bean method references nếu được Spring manage đúng cách.

Nếu bạn chỉ thêm `proxyBeanMethods = false` mà **không sửa** hai lời gọi `dataSource()` và `userRepository()`, có nguy cơ tạo:

- `UserRepository` ngoài container trong khi Spring vẫn đăng ký bean `userRepository` riêng.
- `DataSource` ngoài container cho instance repository tạo thủ công.
- Những object bị bỏ qua việc áp dụng lifecycle, transaction/proxy, init/destroy callbacks hoặc scope của bean definitions.
- Nhiều connection pools hay clients ngoài ý định, gây tốn tài nguyên và cleanup sai.

### Cách refactor an toàn

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {

    @Bean
    DataSource dataSource() {
        return createDataSource();
    }

    @Bean
    UserRepository userRepository(DataSource dataSource) {
        return new JdbcUserRepository(dataSource);
    }

    @Bean
    UserService userService(UserRepository userRepository) {
        return new UserService(userRepository);
    }
}
```

Các object phụ thuộc được tiêm qua tham số. Đây cũng là thiết kế ít phụ thuộc vào cơ chế interception hơn. Nếu một bean chỉ cần tham số từ cấu hình khác, Spring vẫn phân giải theo type/qualifier trong **cùng context**, miễn các bean definitions đã được đăng ký.

### Checklist tìm inter-bean direct calls

Trước khi bật lite mode:

- Tìm tất cả lời gọi `anotherBeanMethod()` bên trong các `@Bean` methods.
- Tìm lời gọi tương tự trong helper methods được gọi từ `@Bean`.
- Tìm cách dùng `this.anotherBeanMethod()`, method reference hoặc gọi qua reference tới config object.
- Kiểm tra bean methods trả tài nguyên như `DataSource`, `Executor`, `Client`, `SessionFactory`, `ConnectionFactory`, vì một instance phụ có thể gây hậu quả vận hành lớn.
- Đổi các dependency thành **tham số `@Bean`**, constructor injection, factory hoặc `ObjectProvider` khi có nhu cầu lookup theo thời điểm.
- Tạo integration test xác nhận managed bean identity, lifecycle, số instance và các failure paths.
- Chỉ sau đó đổi `@Configuration` thành `@Configuration(proxyBeanMethods=false)`.

Chú ý: không phải mọi lời gọi method trong class cấu hình là lỗi. Gọi **helper method không phải `@Bean`** để parse thuộc tính hoặc build một value object bên trong factory thường hợp lệ; điểm rủi ro là gọi **phương thức được dùng làm Spring bean factory** rồi tưởng kết quả là managed bean.

## 9. Scope: tại sao direct call nguy hiểm hơn chỉ tạo hai singleton?

Bean scope là hợp đồng BeanFactory. Dù Java method luôn trả `new Catalog()`, container có thể quản lý nó như singleton, prototype hoặc scoped proxy tùy bean definition.

### 9.1. Singleton

```java
@Bean
Catalog catalog() {
    return new Catalog();
}
```

Mặc định, bean này có singleton scope trong **một ApplicationContext**. `context.getBean(Catalog.class)` hai lần thường trả cùng instance. Nhưng `catalog()` được gọi trực tiếp trong lite mode là một method call và có thể tạo object mới ngoài managed singleton.

Vì vậy đừng kết luận: "Method có `@Bean` thì gọi thế nào cũng là singleton". Singleton là quy tắc **lấy bean qua container**, không phải lời hứa rằng mọi lần thực thi factory method từ Java đều trả cùng object.

### 9.2. Prototype

```java
@Bean
@Scope("prototype")
TaskWorker taskWorker() {
    return new TaskWorker();
}
```

Đây là **đoạn minh họa** cần `TaskWorker`, `@Scope` import và cấu hình hợp lệ. Khi Spring phân giải prototype bean qua container, nó tạo instance theo yêu cầu. Lite direct call `taskWorker()` cũng có thể tạo một object mới, nhưng đối tượng được gọi trực tiếp **không tự nhận quy trình quản lý bean**.

Sự trùng hợp “mỗi lần gọi đều ra object mới” **không** có nghĩa hai cơ chế tương đương. Chẳng hạn, post-processing, dependency injection, bean init callback, scope-aware proxy hoặc type conversion của Spring không được tự áp dụng lên object tạo trực tiếp.

Nếu một singleton service cần prototype worker mới tại mỗi lần xử lý, hãy xét `ObjectProvider<TaskWorker>` hoặc factory chuyên dụng, không dựa vào lời gọi trực tiếp `@Bean` trong lite mode.

### 9.3. Request/session scope

Khi dùng web scope hoặc scoped proxy, việc phân giải bean qua container có thể phụ thuộc request/session hiện hành. Direct method call trong lite mode bỏ qua bước tìm target/proxy được Spring quản lý. Nó không chỉ gây khác identity mà còn có thể sai **context nghiệp vụ và lifecycle**, đặc biệt khi đối tượng chứa trạng thái phiên làm việc.

Với các scope phức tạp, luôn viết code nhận dependency bằng injection/`ObjectProvider` theo đúng scope contract.

## 10. Lifecycle và BeanPostProcessor

Khi Spring tạo bean qua `@Bean` method, nó có thể:

- Giải quyết dependencies và apply các callback phù hợp.
- Chạy `BeanPostProcessor` trước/sau initialization.
- Áp dụng AOP proxying nếu infrastructure tương ứng được bật.
- Gọi `initMethod` hoặc callback khởi tạo theo cấu hình.
- Với singleton phù hợp, gọi `destroyMethod` khi context đóng.
- Áp dụng các scope và lifecycle rules liên quan.

Xem:

```java
@Configuration(proxyBeanMethods = false)
class ResourceConfig {

    @Bean(initMethod = "open", destroyMethod = "close")
    ResourceClient resourceClient() {
        return new ResourceClient();
    }

    @Bean
    WorkService workService(ResourceClient client) {
        return new WorkService(client);
    }
}
```

Đây là minh họa cần định nghĩa `ResourceClient.open()/close()` và `WorkService`. Khi Spring tạo `resourceClient`, bean được chạy init callback rồi có thể được đưa vào `workService`. Sau đó Spring gọi destroy callback khi container đóng nếu bean là singleton thuộc lifecycle container.

**Phản ví dụ:**

```java
@Bean
WorkService workService() {
    return new WorkService(resourceClient());
}
```

Trong lite mode, `resourceClient()` bên trong `workService()` tự chạy factory code, object tạo ra **không được BeanFactory tự động xử lý như bean `resourceClient`**. Nếu `open` phải được gọi trước khi sử dụng, object phụ có thể chưa được init; nếu có tài nguyên phải đóng, object đó có thể không nhận destroy callback của bean definition. Đây là lý do lifecycle bug thường khó nhận ra hơn lỗi singleton identity.

### Có phải lite tắt lifecycle cho @Bean?

**Không.** Khi Spring trực tiếp gọi `resourceClient()` để tạo bean definition `resourceClient`, instance đó **vẫn nhận** lifecycle đúng theo cấu hình. Chỉ những object được tạo qua **lời gọi Java không do container phân giải như một bean** mới không tự được quản lý theo bean definition ấy.

## 11. proxyBeanMethods không phải công tắc Spring AOP

Tên thuộc tính `proxyBeanMethods` rất dễ khiến người học hiểu nhầm là "bật/tắt mọi proxy". Thực tế nó chỉ kiểm soát **việc proxy các phương thức `@Bean` của class cấu hình**, không trực tiếp quyết định:

- Spring AOP có tạo proxy cho service hay không.
- `@Transactional` có được áp dụng lên service không.
- Scoped proxies được tạo ra hay không.
- JDK dynamic proxy hay class-based proxy được dùng cho một bean nghiệp vụ.
- Method security có được bật không.

Ví dụ một `@Service` nhận đối tượng do `@Bean` cung cấp:

```java
@Configuration(proxyBeanMethods = false)
class DatabaseConfig {

    @Bean
    DataSource dataSource() {
        return createDataSource();
    }
}
```

Bản thân việc tắt configuration method proxy **không tắt** Spring AOP/transaction proxy trên một service khác. Những proxy đó còn phụ thuộc annotation, advisor, transaction manager và infrastructure thực tế.

Ngược lại, dù cấu hình full bật `proxyBeanMethods=true`, không thể suy ra mỗi business method trong mọi bean đều được AOP intercept. Đây là **hai cơ chế proxy có mục đích khác nhau**.

### Self-invocation ở hai ngữ cảnh khác nhau

- Trong **full `@Configuration`**, lời gọi từ một `@Bean` method sang một `@Bean` method khác trên enhanced configuration instance có thể được intercept bởi CGLIB cấu hình để lấy managed bean.
- Trong **Spring AOP proxy mode** thông thường, self-invocation từ một method target sang method khác trên cùng target có thể **bỏ qua advice** vì lời gọi không đi qua external proxy.

Không nên lấy quy tắc self-invocation của AOP rồi khẳng định full `@Configuration` cũng luôn bỏ qua interception; ngược lại cũng không lấy interception của `@Bean` để suy ra self-invocation của `@Transactional` sẽ hoạt động.

## 12. CGLIB: lợi ích và ràng buộc

Full mode cần subclassing/method interception nên có những ràng buộc đáng lưu ý:

### Class cấu hình không final

```java
// Phản ví dụ trong full mode:
@Configuration
public final class FinalFullConfig {
    @Bean
    Catalog catalog() {
        return new Catalog();
    }
}
```

CGLIB không thể subclass class `final`. Nếu thật sự cần full interception, class cấu hình và những instance `@Bean` methods cần override phải đáp ứng giới hạn của Spring/CGLIB.

### Phương thức @Bean private/final

```java
// Phản ví dụ về method cần full interception:
@Configuration
class FullConfig {
    @Bean
    private final Catalog catalog() {
        return new Catalog();
    }
}
```

Một method `private` hoặc `final` không thể được CGLIB override theo cách cần cho intercepted bean method; ở full mode cấu hình có thể không hợp lệ. Không dùng chúng với giả định Spring vẫn có thể intercept method call bình thường.

### Lite mode giảm ràng buộc subclassing

Khi tắt `proxyBeanMethods`, Spring **không cần subclass class cấu hình để intercept bean methods**, nên một số hạn chế do enhancement được nới lỏng. Điều đó hữu ích cho class immutable/final hoặc code do compiler khác tạo, miễn vẫn thỏa các điều kiện của Java, `@Bean` factory methods và cấu hình container.

Ví dụ có thể dùng:

```java
@Configuration(proxyBeanMethods = false)
public final class ImmutableConfig {
    @Bean
    public Catalog catalog() {
        return new Catalog();
    }
}
```

Đây là **minh họa riêng**, không nằm trong file Java chạy đầy đủ. Lite mode cho phép `final` ở góc nhìn không cần CGLIB subclassing. Tuy nhiên, không nên dùng điểm này để hợp thức hóa lời gọi giữa các bean factory methods; ràng buộc lifecycle/DI vẫn như phần trước.

### Không cần tự thêm dependency CGLIB ngoài

Spring Framework đã tích hợp/repackage các thành phần CGLIB cần dùng trong `spring-core`. Bạn không phải thêm một thư viện CGLIB riêng chỉ để `@Configuration` full mode hoạt động. Điều kiện quan trọng là class/method hợp lệ cho enhancement và phiên bản Spring/JDK tương thích.

## 13. Lite mode và static @Bean

Spring cho phép khai báo một số `@Bean` methods là `static`. Method static không cần instance config để gọi, cũng không phải đối tượng cho instance-method interception:

```java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfig {

    @Bean
    static CustomRegistryPostProcessor customRegistryPostProcessor() {
        return new CustomRegistryPostProcessor();
    }
}
```

Đoạn minh họa cần định nghĩa `CustomRegistryPostProcessor`, không phải chương trình độc lập. Static `@Bean` có ích cho một số bean infrastructure được cần **rất sớm** trong quá trình container bootstrap, đặc biệt các loại `BeanFactoryPostProcessor`/`BeanDefinitionRegistryPostProcessor` thích hợp.

Lý do: Spring có thể gọi static factory method **mà không buộc tạo instance cấu hình quá sớm**, qua đó tránh một số vấn đề về dependency injection hoặc BeanPostProcessor trên chính class cấu hình.

Nhưng `static` không tự động làm bean singleton/prototype hoặc biến nó thành đối tượng không được quản lý. Container vẫn dựa trên bean definition, scope, lifecycle. Chỉ lời gọi `InfrastructureConfig.customRegistryPostProcessor()` do code Java tự thực hiện sẽ là direct static factory call, không tự lấy managed singleton.

Không chuyển tất cả bean methods thành static chỉ vì dùng lite mode. Đây là kỹ thuật hạ tầng dành cho tình huống cụ thể.

## 14. @Import, @ComponentScan và nhiều class cấu hình

Lite mode không giới hạn việc ghép cấu hình bằng `@Import`:

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(RepositoryConfig.class)
class ServiceConfig {

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
```

Đây là ví dụ minh họa, cần interface/implementation tương ứng và import `org.springframework.context.annotation.Import`. Khi đăng ký `ServiceConfig`, Spring import `RepositoryConfig` và có thể tiêm `OrderRepository` qua tham số `orderService(...)`.

Tại đây, **không cần** viết:

```java
// Phản ví dụ với config không được quản lý:
@Bean
OrderService orderService() {
    return new OrderService(new RepositoryConfig().orderRepository());
}
```

Đoạn đó tạo `RepositoryConfig` ngoài container và gọi factory trực tiếp, có nguy cơ tạo repository ngoài managed bean identity/lifecycle.

`@ComponentScan` cũng tiếp tục có ý nghĩa:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "com.example.application")
class ApplicationConfig {
}
```

Các class mang stereotype nằm trong vùng quét có thể được đăng ký như bình thường; lite mode **không tắt quét component**. Cần phân biệt class cấu hình có được **đăng ký vào context** hay không với việc Spring có intercept các phương thức `@Bean` trên class đó hay không.

## 15. Phụ thuộc tùy chọn và nhiều bean trong lite mode

Tham số của `@Bean` method được Spring giải quyết bằng dependency injection tiêu chuẩn. Có thể dùng:

### Dependency bắt buộc

```java
@Bean
PaymentService paymentService(PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

Thiếu bean `PaymentGateway` phù hợp là lỗi cấu hình; Spring thường thất bại khi tạo `paymentService`.

### Dependency tùy chọn

```java
@Bean
ReportService reportService(
        java.util.Optional<AuditSink> auditSink) {
    return new ReportService(auditSink);
}
```

Nếu không có bean `AuditSink`, Optional có thể rỗng, miễn dependency thực sự là tùy chọn theo nghiệp vụ. Lite mode không làm mọi dependency tự chuyển thành optional.

### Nhiều ứng viên

```java
@Bean
Pipeline pipeline(java.util.List<PipelineStep> steps) {
    return new Pipeline(steps);
}
```

Spring có thể tập hợp nhiều bean `PipelineStep` thành danh sách theo các quy tắc collection injection. Nếu pipeline cần thứ tự rõ, cấu hình `@Order`/`Ordered` và kiểm thử; nếu cần lookup động 0..n bean, cân nhắc `ObjectProvider<PipelineStep>`.

**Điểm chính:** Constructor/factory-method parameter injection hoạt động trong full và lite. `proxyBeanMethods=false` không làm Spring bỏ qua `@Qualifier`, generic type, `@Primary`, dependency resolution hoặc lifecycle.

## 16. Hiểu đúng hiệu năng và bootstrapping

Lý do phổ biến để dùng lite configuration là tránh enhancement CGLIB cho class cấu hình khi không cần inter-bean calls. Điều này có thể:

- Giảm lượng lớp proxy/enhanced class cần tạo lúc khởi động.
- Giảm overhead ở giai đoạn cấu hình.
- Tránh ràng buộc subclassing với final class/method.
- Làm hợp đồng wiring nhất quán hơn khi luôn dùng method parameter injection.

Tuy nhiên, **không có một con số tăng tốc chung** cho mọi ứng dụng. Thời gian startup thường còn phụ thuộc việc scan classpath, số bean, tạo connection pool, I/O và các phần khác. Một ứng dụng chỉ có vài `@Bean` methods có thể không cảm nhận được lợi ích đáng kể.

Quan trọng hơn, chuyển full sang lite **có thể thay đổi hành vi** nếu code đang dựa vào inter-bean method interception. Hãy ưu tiên đúng semantics trước; đo hiệu năng sau bằng benchmark thực tế.

### Về Spring Boot

Spring Boot dùng nhiều Java configurations, và một số auto-configuration được khai báo với `proxyBeanMethods=false` vì các bean factory methods có thể thiết kế độc lập và nhận dependencies qua tham số. Điều đó không làm toàn bộ ứng dụng Boot tự thành lite mode; mỗi configuration class có metadata riêng.

`@SpringBootApplication(proxyBeanMethods = false)` là một tùy chọn ở Boot để cấu hình cách xử lý bean methods trên **class ứng dụng được chú giải**, không đồng nghĩa bật/tắt toàn bộ Spring AOP hay áp đặt cờ này lên mọi configuration class nhập vào. Đây là ranh giới khái niệm; ví dụ Maven chính ở mục 7 chỉ dùng Spring Framework thuần.

## 17. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Hai object có cùng class nhưng `==` false dù bean singleton | Lite config gọi trực tiếp `@Bean` method bên trong factory khác | Dùng method parameter injection và so với `context.getBean(...)` |
| Init callback chỉ chạy trên một instance | Instance còn lại do direct Java method call tạo, không qua BeanFactory | Đảm bảo consumer dùng managed bean |
| Tài nguyên bị mở hai lần hoặc không được đóng hết | Direct call trong lite mode tạo resource không do context quản lý | Refactor dependency qua tham số/factory, kiểm tra lifecycle |
| `@Configuration` không enhance được | Full mode nhưng class/method `final` hoặc `private` không phù hợp | Loại ràng buộc cản enhancement hoặc dùng lite với wiring đúng |
| Chuyển `proxyBeanMethods=false` rồi test thất bại | Code cũ dựa vào CGLIB redirect inter-bean calls | Rà soát và thay lời gọi trực tiếp bằng injection |
| `@Bean` trong `@Component` tạo bean nhưng direct call sai identity | Plain component đã là lite mode | Không gọi một bean method từ bean method khác để lấy managed bean |
| `NoSuchBeanDefinitionException` khi parameter injection | Bean dependency chưa đăng ký/import/scanned | Kiểm tra configuration class, type, qualifier, bean definitions |
| `NoUniqueBeanDefinitionException` | Có nhiều ứng viên cùng type và thiếu quy tắc chọn | Dùng `@Qualifier`/`@Primary` hoặc nhận collection đúng nhu cầu |
| Bean không lazy dù dùng provider | Singleton được Spring eager-initialize bởi cơ chế khác | Kiểm tra `@Lazy`, scope, eager dependencies |
| Tưởng `proxyBeanMethods=false` tắt `@Transactional` | Nhầm configuration method proxy với AOP proxy | Kiểm tra AOP/transaction infrastructure riêng |
| Prototype direct call có vẻ tạo mới đúng nhưng lifecycle sai | Java method trả object mới ngoài bean post-processing | Lấy prototype qua BeanFactory/`ObjectProvider` |
| Test chỉ gọi `new LiteConfig().catalog()` | Bỏ qua container nên không kiểm tra được managed identity | Dùng `AnnotationConfigApplicationContext` trong integration test |

Quy trình debug có thứ tự:

1. Xác định class đang dùng **full** (`@Configuration` mặc định), **lite** (`proxyBeanMethods=false`), hay plain `@Component`.
2. Tìm tất cả factory methods `@Bean` và các lời gọi trực tiếp giữa chúng.
3. Kiểm tra bean lấy bằng `context.getBean(...)` có cùng reference với dependency được consumer giữ không.
4. Phân biệt **bean singleton của container** với object Java tự tạo bằng `new` hoặc direct method call.
5. Kiểm tra lifecycle callbacks và khả năng bean bị proxy/scoped.
6. Đưa inter-bean dependencies vào factory method parameters.
7. Chạy lại integration test trước khi đo tối ưu startup.

## 18. Kiểm thử để ngăn regression

Các test quan trọng khi chuyển full sang lite:

### Kiểm tra bean identity

Với ví dụ mục 7, assert:

```java
// Đoạn kiểm tra bên trong report(...) khi context còn mở:
Catalog managed = context.getBean(Catalog.class);

CatalogConsumer injected =
        context.getBean("injectedConsumer", CatalogConsumer.class);

if (injected.catalog() != managed) {
    throw new AssertionError(
            "Factory method parameter did not inject managed Catalog");
}
```

Đây là đoạn bổ sung, không phải class độc lập. Nó chứng minh consumer nhận **đúng instance** container quản lý, không chỉ một object cùng kiểu.

### Kiểm tra lifecycle callback

Tạo test resource bean có `initMethod` và `destroyMethod`, kiểm tra số lần mở/đóng của managed bean khi context startup/close. Nếu code tạo thêm resource từ direct call, kết quả sẽ chỉ ra rủi ro leak hoặc thiếu initialization.

### Kiểm tra bean definition và scope

Dùng `context.getBean(Catalog.class)` hai lần để xác nhận singleton trong context. Điều này **không thay thế** test identity của object nằm trong consumer: container singleton vẫn đúng ngay cả khi consumer tình cờ giữ unmanaged object khác.

### Kiểm tra cấu hình nhiều module

Nếu một `@Configuration(proxyBeanMethods=false)` phụ thuộc bean từ `@Import` khác, integration test nên khởi tạo đúng class cấu hình root, tránh mock bằng `new` rồi nghĩ rằng dependency resolution hoạt động.

### Kiểm tra fail-fast của dependency bắt buộc

Với tham số `@Bean Consumer consumer(RequiredRepository repo)`, context phải phát hiện thiếu `RequiredRepository` khi tạo consumer. Đây là hành vi tốt; đừng chuyển dependency bắt buộc thành `getIfAvailable()` rồi bỏ qua chỉ để test startup xanh.

## 19. Bài tập và đáp án

### Bài 1: hai chế độ khác nhau ở đâu?

`@Configuration` và `@Configuration(proxyBeanMethods=false)` đều có method `@Bean`. Cả hai có tạo bean definitions không? Khác biệt cốt lõi?

**Đáp án:** Cả hai đều tạo bean definitions; bean do container tạo được quản lý bình thường. Khác biệt cốt lõi là full configuration có thể intercept inter-bean method calls trên enhanced config instance, còn lite thì direct calls chỉ là Java method invocations.

### Bài 2: dự đoán identity

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Worker worker() { return new Worker(); }

    @Bean
    Manager manager() { return new Manager(worker()); }
}
```

`Manager` có chắc giữ đúng bean `worker` singleton do `context.getBean(Worker.class)` trả về không?

**Đáp án:** Không. `worker()` được gọi trực tiếp trong `manager()`, tạo object Java riêng theo body method. Sửa thành `Manager manager(Worker worker) { return new Manager(worker); }`.

### Bài 3: làm việc trong @Component

Một class `@Component` có hai `@Bean` methods và một method gọi method kia. Có được Spring tự intercept như full `@Configuration` không?

**Đáp án:** Không. Đây là lite `@Bean` processing. Dùng injection qua method parameter nếu consumer cần một managed bean.

### Bài 4: thay đổi proxyBeanMethods có làm mất @Bean không?

Bạn đổi `@Configuration` thành `@Configuration(proxyBeanMethods=false)` và không thay gì khác. Các `@Bean` methods còn được đăng ký chứ?

**Đáp án:** Có, nếu configuration class vẫn được nạp đúng. Nhưng **hành vi direct method call** có thể đổi, nên cần rà soát code thay vì kết luận không có tác động.

### Bài 5: full mode và new Config()

`new FullConfig().catalog()` có chắc nhận bean singleton của context không?

**Đáp án:** Không. Instance tạo bằng `new` không phải enhanced configuration bean được container quản lý.

### Bài 6: prototype

Một prototype bean được gọi qua method `@Bean` trực tiếp trong lite mode có chắc nhận lifecycle và post-processors của Spring không?

**Đáp án:** Không. Nó chỉ là object do Java method tạo. Muốn managed prototype, phân giải bean qua container/`ObjectProvider`.

### Bài 7: so sánh với Spring AOP

`proxyBeanMethods=false` có đồng nghĩa tắt proxy của `@Transactional` không?

**Đáp án:** Không. Nó chỉ tắt CGLIB interception dành cho bean factory methods của configuration class. AOP transaction proxy là cơ chế khác với điều kiện kích hoạt riêng.

### Bài 8: tối ưu startup

Bạn có một config không có direct inter-bean calls, mọi dependency đều được inject qua factory method parameters. Có thể cân nhắc cờ nào?

**Đáp án:** `@Configuration(proxyBeanMethods=false)` có thể giảm enhancement overhead mà vẫn giữ đúng wiring. Cần test cả managed instance và behavior quan trọng sau khi chuyển.

### Bài 9: static @Bean

Một `static @Bean` method có được CGLIB override/intercept giống instance method trong full configuration không?

**Đáp án:** Không. Static method không phải virtual instance method. Container vẫn có thể quản lý bean tạo qua bean definition, nhưng direct static call là Java thường.

### Bài 10: sửa cấu hình nhiều tầng

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    A a() { return new A(); }

    @Bean
    B b() { return new B(a()); }

    @Bean
    C c() { return new C(b()); }
}
```

Hãy sửa để `B` và `C` dùng đúng managed dependencies.

**Đáp án định hướng:**

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    A a() { return new A(); }

    @Bean
    B b(A a) { return new B(a); }

    @Bean
    C c(B b) { return new C(b); }
}
```

Các class `A`, `B`, `C` là kiểu minh họa; bài tập cần bổ sung định nghĩa thực nếu muốn biên dịch.

## 20. Checklist trước khi áp dụng vào dự án

- [ ] Xác định có thật sự cần CGLIB inter-bean references không.
- [ ] Nếu chọn lite, không viết `@Bean x() { return new X(y()); }` chỉ để lấy bean `y`.
- [ ] Chuyển các dependency thành factory method parameters hoặc constructor injection.
- [ ] Dùng `@Qualifier` khi có nhiều bean cùng type.
- [ ] Với prototype/scoped beans, truy vấn thông qua container/provider thay vì gọi factory method trực tiếp.
- [ ] Không giả định `proxyBeanMethods=false` tắt AOP proxies hoặc các lifecycle callbacks.
- [ ] Kiểm tra class cấu hình vẫn được import/scanned/registered vào context.
- [ ] Khi cần dùng final class/method, xác minh config được xử lý lite và các ràng buộc khác vẫn hợp lệ.
- [ ] Viết test cho identity, initialization, destruction và các bean quan trọng.
- [ ] Xác minh không tạo trùng các resource tốn kém như connection pool, HTTP client hoặc executor.
- [ ] Chỉ báo cải thiện hiệu năng khi có đo đạc, không suy đoán một mức tăng tốc cố định.

## Kết luận

**Full `@Configuration`** dùng CGLIB để bảo toàn inter-bean method references khi gọi `@Bean` methods trên enhanced configuration bean do Spring quản lý. **Lite mode**, gồm `@Configuration(proxyBeanMethods=false)` và `@Bean` methods trong plain `@Component`, không intercept các direct calls như vậy: chúng hành xử như phương thức Java thường.

Hai mode vẫn có **bean definitions, dependency resolution, singleton/prototype scopes và lifecycle đầy đủ cho các object được Spring tạo và quản lý**. Sự cố xuất hiện khi code vô tình tạo thêm object bằng direct factory-method call rồi coi chúng là managed beans.

Quy tắc áp dụng bền vững nhất: **mỗi `@Bean` method nên tự làm nhiệm vụ factory của nó, còn dependency cần lấy từ container nên truyền qua tham số**. Khi tuân thủ điều này, bạn có thể dùng lite mode một cách rõ ràng, giảm nhu cầu CGLIB enhancement mà không thay đổi identity và vòng đời các dependency.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html): full/lite mode và inter-bean method calls.
- [Spring Framework 6.2 — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): CGLIB enhancement, scope và điều kiện sử dụng.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory methods, lifecycle, scope và lite mode.
- [Spring Framework 6.2 — @Configuration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/Configuration.html): hợp đồng `proxyBeanMethods` và ràng buộc subclass.
- [Spring Framework 6.2 — @Bean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/Bean.html): cách `@Bean` được xử lý trong full/lite classes.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): `@Bean` trong plain `@Component` và khác biệt với `@Configuration`.
