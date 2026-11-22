# Giới hạn ứng viên bằng `autowire-candidate` trong Spring Core Container

## 1. Bean tồn tại không có nghĩa bean được phép autowire

Một Spring `ApplicationContext` có thể đăng ký nhiều beans cùng Java type. Ví dụ `activeTransport` phục vụ nghiệp vụ chính, còn `internalTransport` là implementation dùng để bảo trì hoặc kiểm thử một đường xử lý đặc biệt. Cả hai implement `Transport`, nhưng service thông thường **không nên tự nhận** `internalTransport` chỉ vì nó có type tương thích.

Spring Core Container tách những khái niệm sau:

1. **Bean registration:** bean có tên, định nghĩa và thuộc container hay không?
2. **Type matching:** bean có kiểu có thể gán vào kiểu mà injection point yêu cầu hay không?
3. **Autowire candidate eligibility:** bean matching type có **được tham gia autowiring** không?
4. **Candidate selection:** khi có nhiều candidates được phép, `@Primary`, `@Qualifier`, `@Fallback` và các quy tắc khác có chọn được bean phù hợp không?
5. **Explicit reference:** caller/cấu hình chủ động tra một bean theo **tên tường minh** có còn được sử dụng bean ấy không?

Cơ chế **`autowire-candidate=false`** (XML) hoặc **`@Bean(autowireCandidate=false)`** (Java configuration) đặt giới hạn vào **mục 3**. Nó không xóa bean và **không cấm mọi lookup bằng tên**.

Ví dụ Spring Java configuration:

~~~java
// Snippet: Transport là interface có trong project hoàn chỉnh ở mục 7.
@Bean(name = "internalTransport", autowireCandidate = false)
Transport internalTransport() {
    return () -> "INTERNAL";
}
~~~

Bean `internalTransport` vẫn được đăng ký; `context.getBean("internalTransport", Transport.class)` vẫn có thể trả về instance. Tuy nhiên, Spring sẽ loại bean này khỏi việc chọn theo type tại những injection points như:

~~~java
@Autowired
private Transport transport;

// Hoặc factory method nhận dependency do Spring resolve:
@Bean
Report report(Transport selected) {
    return new Report(selected);
}
~~~

Hai đoạn trên chỉ minh họa, **không phải các file Java độc lập**. Chương trình có cấu trúc đầy đủ ở mục 7.

**Thông điệp chính:** Không thể dùng kết quả `getBeanNamesForType(Transport.class)` như một bản sao chính xác của danh sách beans mà `@Autowired Transport` sẽ cân nhắc. Một bean match type vẫn có thể bị đánh dấu **không phải autowire candidate**.

## 2. Cấu hình `autowire-candidate` ở đâu?

### 2.1. Trên bean definition XML

Trong XML, attribute đúng tên là **`autowire-candidate`**:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="activeTransport"
          class="demo.ActiveTransport"/>

    <bean id="internalTransport"
          class="demo.InternalTransport"
          autowire-candidate="false"/>
</beans>
~~~

Đây là ví dụ cấu hình XML **minh họa** với hai class độc lập giả định `demo.ActiveTransport`/`demo.InternalTransport`; dự án chạy ở mục 7 **không đọc XML** mà dùng `@Bean` và Java 17.

Giá trị `false` có nghĩa **định nghĩa `internalTransport` không được đưa vào autowire candidate set cho type-based injection**. Nếu XML cấu hình explicit dependency:

~~~xml
<bean id="specialReport" class="demo.SpecialReport">
    <constructor-arg ref="internalTransport"/>
</bean>
~~~

thì explicit `ref` **vẫn có thể hoạt động**; không được diễn giải flag thành “bean không tồn tại”. File XML trên chỉ minh họa điều đó; class `demo.SpecialReport` cũng là một class minh họa, không thuộc source Maven chạy độc lập phía dưới.

### 2.2. Trên method `@Bean`

Spring cung cấp thuộc tính `autowireCandidate` ngay trong `org.springframework.context.annotation.Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean("activeTransport")
    Transport activeTransport() {
        return () -> "ACTIVE";
    }

    @Bean(name = "internalTransport", autowireCandidate = false)
    Transport internalTransport() {
        return () -> "INTERNAL";
    }
}
~~~

Cấu hình này tạo ra hai definitions `activeTransport` và `internalTransport` cùng type `Transport`. Chỉ `activeTransport` là candidate cho plain `@Autowired Transport`. **Flag nằm trên bean definition**, không nằm trong interface hay instance `Transport`.

### 2.3. Điều chỉnh bằng BeanDefinition API

Nếu thật sự cần điều khiển metadata bằng Java lúc đăng ký definitions (thường thuộc infrastructure code):

~~~java
// Snippet: chạy trước khi bean factory bắt đầu resolve dependencies.
BeanDefinition definition =
        registry.getBeanDefinition("internalTransport");
definition.setAutowireCandidate(false);
~~~

Snippet này cần kiểu `BeanDefinition`, `BeanDefinitionRegistry` và registration phase thích hợp; **không phải** lời khuyên để business service sửa bean definition khi ứng dụng đã chạy. Với code mới, thường khai `@Bean(autowireCandidate=false)` tường minh sẽ dễ kiểm tra hơn.

Spring bean definition cũng có `isAutowireCandidate()` để truy vấn metadata, rất hữu ích khi debug nguyên nhân “bean có trong context nhưng không được inject”.

### 2.4. Giá trị mặc định

Với phần lớn ordinary bean definitions, **autowire candidate mặc định là `true`**. Việc có một bean trùng type thường khiến nó có thể tham gia autowiring, nhưng còn tùy qualifiers, generic signatures, scope và các bộ lọc khác.

Đừng đánh `false` tùy tiện để né lỗi `NoUniqueBeanDefinitionException` mà không biết use case nào có thể cần bean đó. Đây là **chính sách đóng quyền tham gia DI**, có hệ quả ở nhiều injection points.

## 3. Có thể tra tên hoặc type, nhưng danh sách injection đã bị lọc

So sánh bốn trường hợp:

| Thao tác | `activeTransport` bình thường | `internalTransport` `autowireCandidate=false` |
| --- | --- | --- |
| Đăng ký bean definition | Có | Có |
| `context.containsBean("...")` | Có | Có |
| `getBean("name", Transport.class)` | Có thể lấy | **Vẫn có thể lấy bằng tên** |
| `getBeanNamesForType(Transport.class)` | Thường xuất hiện | **Vẫn xuất hiện** nếu type tương thích |
| `getBeansOfType(Transport.class)` | Có thể xuất hiện trong map | **Vẫn có thể xuất hiện** vì đây là type discovery/lookup API |
| Plain `@Autowired Transport` | Được cân nhắc | **Bị loại** |
| `@Autowired List<Transport>` | Được xét vào collection | **Bị loại khỏi candidates tiêm** |
| `@Autowired Map<String,Transport>` | Được xét vào map | **Bị loại khỏi candidates tiêm** |
| `@Qualifier("internalTransport") Transport` | Không chọn bean không khớp qualifier | **Không làm excluded bean trở lại** type-based autowiring |

### Discovery khác injection

~~~java
String[] names =
        context.getBeanNamesForType(Transport.class);
Map<String, Transport> all =
        context.getBeansOfType(Transport.class);
~~~

Hai API trên là **khám phá/tra cứu beans theo type** trong `ListableBeanFactory`. Chúng không trực tiếp trả về “tập ứng viên đã lọc cho một điểm autowire cụ thể”. Một bean có thể vừa match type vừa bị gắn `autowireCandidate=false`.

Ngược lại, Spring resolve dependency cho field/constructor/factory-method parameter thông qua các quy tắc autowiring. **Kết quả có thể ít hơn type discovery**, đặc biệt khi có exclusions, qualifiers hoặc generic constraints.

### Name-based explicit reference còn hoạt động

~~~java
Transport internal =
        context.getBean("internalTransport", Transport.class);
~~~

Đây là **lệnh chủ động yêu cầu bean name**; flag autowire candidate không xóa `internalTransport`. Theo tài liệu Spring, explicit references bằng tên vẫn được resolve. XML `<ref bean="internalTransport"/>` và các cơ chế by-name explicit có nguyên tắc tương tự khi được sử dụng đúng.

**Cần phân biệt:** `@Qualifier("internalTransport")` trên `@Autowired Transport` **vẫn là type-based autowiring với filter qualifier**. Qualifier **không** chuyển injection ấy thành một explicit `getBean(name)` bỏ qua exclusion. Đó là lý do không được dùng qualifier như “cách phá khóa” `autowireCandidate=false`.

## 4. `autowireCandidate=false` không ngăn bean tự được cấu hình

Một điểm thường bị hiểu ngược:

> “Bean bị loại khỏi autowire candidates sẽ không còn được Spring inject dependencies vào chính nó.”

Sai. Flag mô tả **bean có được người khác autowire vào không**, không phải bean ấy có được Spring khởi tạo/cấp dependencies của chính nó không.

Ví dụ:

~~~java
// Snippet minh họa (đưa vào class config có @Bean phù hợp).
@Bean(name = "internalTransport", autowireCandidate = false)
Transport internalTransport(Settings settings) {
    return new InternalTransport(settings);
}
~~~

Trong đó `Settings` là bean hợp lệ và Spring có thể resolve tham số `Settings settings` để tạo `internalTransport`. Sau khi được tạo, `internalTransport` vẫn bị loại **khi một consumer khác yêu cầu Transport theo type**.

**Hai hướng phụ thuộc khác nhau:**

~~~text
          Settings (ordinary candidate)
                    |
                    | Inject Settings để TẠO bean
                    v
    internalTransport (autowireCandidate=false)
                    |
                    X Không được autowire THEO TYPE
                    |
                    v
               RegularConsumer

   Explicit getBean("internalTransport") vẫn có thể hoạt động
~~~

Khi viết hệ thống có plugin/internal delegates hoặc adapter hỗ trợ, đây là sự phân biệt quan trọng: ta muốn một bean hoạt động đầy đủ bên trong context, nhưng **không chen vào candidate set mặc định** của các services khác.

Bean đó vẫn chịu scope, constructor, field/method injection, initialization và destruction callbacks theo những quy tắc Spring áp dụng cho bean tương ứng. Flag không biến một Spring bean thành object ngoài container.

## 5. `autowireCandidate=false` khác `defaultCandidate=false`

Từ Spring Framework **6.2+**, `@Bean` có thêm hai biến thể quan trọng:

| Metadata | Không có qualifier, inject chỉ theo type | Có `@Qualifier` phù hợp | Explicit name lookup |
| --- | --- | --- | --- |
| `autowireCandidate=true, defaultCandidate=true` (mặc định) | Có thể là candidate | Có thể là candidate | Có |
| **`autowireCandidate=false`** | **Không được autowire** | **Vẫn không được autowire theo type** | **Có** |
| **`defaultCandidate=false`** nhưng autowireCandidate=true | Không phải lựa chọn mặc định chỉ theo type | **Có thể được chọn với qualifier** | Có |

### Restriction “cứng”: `autowireCandidate=false`

~~~java
@Bean(name = "internalTransport", autowireCandidate = false)
Transport internalTransport() {
    return () -> "INTERNAL";
}
~~~

Không dùng `@Autowired @Qualifier("internalTransport")` để đòi bean này như một type-based candidate thông thường. Nếu nghiệp vụ cần tham chiếu chính xác bean tên ấy, hãy diễn đạt đó là **explicit reference by name** tại composition root/bean wiring khi thích hợp.

### Restriction “có điều kiện”: `defaultCandidate=false`

~~~java
@Bean(name = "specialTransport", defaultCandidate = false)
Transport specialTransport() {
    return () -> "SPECIAL";
}
~~~

Bean này vẫn có `isAutowireCandidate=true`, nhưng được dự kiến chỉ tham gia vào những injection points có **chỉ báo bổ sung** như `@Qualifier("specialTransport")`.

Ví dụ:

~~~java
@Bean
NamedConsumer selectedClient(
        @Qualifier("specialTransport") Transport selected) {
    return new NamedConsumer(selected);
}
~~~

Đoạn này là snippet: class `NamedConsumer` phải được định nghĩa và import qualifier đúng. Dự án đầy đủ ở mục 7 minh họa cùng cơ chế với tên `restrictedTransport`.

**Khi cần “không bao giờ tự chọn khi inject theo type”, dùng `autowireCandidate=false`. Khi cần “không mặc định nhưng vẫn cho phép yêu cầu có qualifier”, cân nhắc `defaultCandidate=false`.** Không lẫn chúng với `@Primary`/`@Fallback`: hai annotation sau ảnh hưởng mức ưu tiên giữa các candidates đủ điều kiện, còn metadata candidates ảnh hưởng việc một bean có đủ điều kiện ngay từ đầu hay không.

## 6. `@Primary`, `@Qualifier`, `@Fallback` và tên field có cứu được bean bị exclude không?

### `@Primary` không ghi đè exclusion

Nếu bean `internalTransport` vừa gắn `autowireCandidate=false` vừa gắn `@Primary`:

~~~java
@Bean(name = "internalTransport", autowireCandidate = false)
@Primary
Transport internalTransport() {
    return () -> "INTERNAL";
}
~~~

Khi một service yêu cầu plain `Transport`, Spring vẫn **không sử dụng internalTransport làm autowire candidate**. `@Primary` chỉ có thể ưu tiên **ứng viên còn hợp lệ**; không biến một definition excluded thành candidate.

Trong demo, chúng ta **cố tình** đánh dấu `@Primary` trên bean bị loại để kiểm chứng quy tắc này. Sau đó metadata `isPrimary()` và `isAutowireCandidate()` đều được in; bạn sẽ thấy **primary=true nhưng autowireCandidate=false**, và service vẫn nhận bean bình thường.

### `@Qualifier` là filter, không phải explicit ref

~~~java
@Autowired
@Qualifier("internalTransport")
private Transport transport;
~~~

Khi bean `internalTransport` có `autowireCandidate=false`, đây vẫn là một injection point dựa trên type nên **không được phép lấy bean ấy chỉ nhờ qualifier**. Đừng nhầm `@Qualifier("beanName")` với `getBean("beanName")`; hai cách có ý nghĩa khác nhau.

### `@Fallback` không loại bean khỏi autowire candidates

Với Spring 6.2+, `@Fallback` đánh dấu bean là phương án dự phòng; nó **vẫn có thể là một autowire candidate** và tham gia collections, tùy qualifiers/eligibility. `@Primary` ưu tiên một candidate, `@Fallback` hạ độ ưu tiên so với non-fallback candidates, còn **`autowireCandidate=false` loại hẳn khỏi type-based autowiring**.

### Tên field/parameter không phá exclusion

Một field tên `internalTransport` với `@Autowired` không thể mặc định “khôi phục” autowiring cho bean excluded chỉ vì field trùng bean name. Tên injection point giúp chọn giữa candidates, **không nên coi là đường vòng qua điều kiện candidate eligibility**.

**Ngoại lệ cần phân biệt:** XML autowiring mode **`byName`** hoặc một explicit bean reference by name có semantics riêng; tài liệu Spring nêu rõ `autowire-candidate` không chặn explicit references theo tên. Không suy luận rằng mọi kỹ thuật nhìn có chữ “name” đều là cùng một loại injection.

## 7. Project Maven Java 17: nhìn rõ discovery, filtering và explicit lookup

Mục tiêu là **chạy ba context độc lập**:

1. **MainConfig:** có một ordinary bean `activeTransport` và một bean `internalTransport` mang `autowireCandidate=false` **và `@Primary`**. `getBeanNamesForType(Transport.class)` thấy cả hai; `@Bean Report report(Transport selected, List<Transport> ..., Map<String,Transport> ...)` chỉ được inject **ACTIVE**. `getBean("internalTransport")` vẫn trả **INTERNAL**.
2. **ExcludedOnlyConfig:** chỉ có một bean cùng type nhưng **không phải candidate**, trong khi một `@Bean` cần Transport required → context **khởi động thất bại**, chứng minh “khớp type nhưng bị exclude” vẫn không đủ.
3. **RestrictedConfig:** có `regularTransport` thường và `restrictedTransport` với `defaultCandidate=false`. Plain `Transport` được cấp **REGULAR**; tham số mang `@Qualifier("restrictedTransport")` được cấp **RESTRICTED**.

Code không cần Spring Boot, không dùng HTTP server hay database; tất cả kết quả ứng dụng do source chủ động in.

### 7.1. Cấu trúc thư mục

~~~text
candidate-restriction-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CandidateRestrictionDemo.java
~~~

Yêu cầu **JDK 17+**, Maven **3.9+**, có thể tải Maven artifacts từ repository khi build lần đầu.

### 7.2. `pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>candidate-restriction-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.CandidateRestrictionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` kéo các Spring Core Container modules phụ thuộc qua Maven; plugin compiler dùng Java 17. Không cần Jakarta annotation API vì demo dùng Spring `@Bean`, `@Primary`, `@Qualifier`; không dùng `@Resource` trong chương trình chính.

### 7.3. `src/main/java/demo/CandidateRestrictionDemo.java`

~~~java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public final class CandidateRestrictionDemo {

    private CandidateRestrictionDemo() {
    }

    @FunctionalInterface
    interface Transport {
        String id();
    }

    record FixedTransport(String id) implements Transport {
    }

    static final class Report {
        private final Transport selected;
        private final List<Transport> available;
        private final Map<String, Transport> byName;

        Report(Transport selected, List<Transport> available,
                Map<String, Transport> byName) {
            this.selected = selected;
            this.available = available;
            this.byName = byName;
        }

        String chosen() {
            return selected.id();
        }

        String injectedIds() {
            return available.stream()
                    .map(Transport::id)
                    .sorted()
                    .collect(Collectors.joining(","));
        }

        String injectedNames() {
            return byName.keySet().stream()
                    .sorted()
                    .collect(Collectors.joining(","));
        }

        boolean containsInternal() {
            return byName.containsKey("internalTransport");
        }
    }

    static final class SingleConsumer {
        private final Transport selected;

        SingleConsumer(Transport selected) {
            this.selected = selected;
        }

        String chosen() {
            return selected.id();
        }
    }

    static final class RestrictedReport {
        private final Transport plain;
        private final Transport qualified;

        RestrictedReport(Transport plain, Transport qualified) {
            this.plain = plain;
            this.qualified = qualified;
        }

        String plain() {
            return plain.id();
        }

        String qualified() {
            return qualified.id();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class MainConfig {
        @Bean("activeTransport")
        public Transport activeTransport() {
            return new FixedTransport("ACTIVE");
        }

        @Bean(name = "internalTransport", autowireCandidate = false)
        @Primary
        public Transport internalTransport() {
            return new FixedTransport("INTERNAL");
        }

        @Bean
        public Report report(
                Transport selected,
                List<Transport> transports,
                Map<String, Transport> transportsByName) {
            return new Report(selected, transports, transportsByName);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ExcludedOnlyConfig {
        @Bean(name = "excludedOnly", autowireCandidate = false)
        public Transport excludedOnly() {
            return new FixedTransport("EXCLUDED");
        }

        @Bean
        public SingleConsumer needsTransport(Transport candidate) {
            return new SingleConsumer(candidate);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class RestrictedConfig {
        @Bean("regularTransport")
        public Transport regularTransport() {
            return new FixedTransport("REGULAR");
        }

        @Bean(name = "restrictedTransport", defaultCandidate = false)
        public Transport restrictedTransport() {
            return new FixedTransport("RESTRICTED");
        }

        @Bean
        public RestrictedReport restrictedReport(
                Transport plain,
                @Qualifier("restrictedTransport") Transport explicit) {
            return new RestrictedReport(plain, explicit);
        }
    }

    private static String sortedNames(String[] input) {
        Arrays.sort(input);
        return String.join(",", input);
    }

    private static String sortedKeys(Map<String, ?> input) {
        return input.keySet().stream()
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(MainConfig.class)) {
            var report = context.getBean(Report.class);
            var factory = context.getBeanFactory();
            var internal =
                    context.getBean("internalTransport", Transport.class);

            System.out.println("main.typeNames=" + sortedNames(
                    context.getBeanNamesForType(Transport.class)));
            System.out.println("main.allTypeObjects=" + sortedKeys(
                    context.getBeansOfType(Transport.class)));
            System.out.println("main.internalRegistered="
                    + context.containsBeanDefinition("internalTransport"));
            System.out.println("main.internalCandidate="
                    + factory.getBeanDefinition(
                            "internalTransport").isAutowireCandidate());
            System.out.println("main.internalPrimary="
                    + factory.getBeanDefinition(
                            "internalTransport").isPrimary());
            System.out.println("main.activeCandidate="
                    + factory.getBeanDefinition(
                            "activeTransport").isAutowireCandidate());
            System.out.println("main.selected=" + report.chosen());
            System.out.println("main.injectedList=" + report.injectedIds());
            System.out.println("main.injectedMap=" + report.injectedNames());
            System.out.println("main.mapContainsInternal="
                    + report.containsInternal());
            System.out.println("main.explicitByName=" + internal.id());
            System.out.println("main.explicitSame="
                    + (internal == context.getBean(
                            "internalTransport", Transport.class)));
        }

        // Chỉ có excluded bean cùng type: không đủ điều kiện autowiring.
        try (var context = new AnnotationConfigApplicationContext(
                ExcludedOnlyConfig.class)) {
            System.out.println("excludedOnly.unexpected");
        } catch (BeansException expected) {
            System.out.println("excludedOnly.failed=true");
        }

        try (var context = new AnnotationConfigApplicationContext(
                RestrictedConfig.class)) {
            var report = context.getBean(RestrictedReport.class);
            var factory = context.getBeanFactory();

            System.out.println("restricted.typeNames=" + sortedNames(
                    context.getBeanNamesForType(Transport.class)));
            System.out.println("restricted.plain=" + report.plain());
            System.out.println("restricted.qualified=" + report.qualified());
            System.out.println("restricted.canAutowire="
                    + factory.getBeanDefinition(
                            "restrictedTransport").isAutowireCandidate());
            System.out.println("restricted.defaultCandidate="
                    + factory.getBeanDefinition(
                            "restrictedTransport").isDefaultCandidate());
            System.out.println("restricted.byName="
                    + context.getBean(
                            "restrictedTransport", Transport.class).id());
        }
    }
}
~~~

### 7.4. Đọc chính xác ba thí nghiệm

**MainConfig — internal không tham gia autowiring:**

- Spring tạo definitions cho hai beans type `Transport` và bean `Report`.
- `internalTransport` vẫn có metadata `isPrimary=true`, nhưng `isAutowireCandidate=false`. Do đó `@Primary` trên bean ấy **không đè** điều kiện excluded.
- Tham số `Transport selected` tại factory method `report` nhận `activeTransport` (ứng viên hợp lệ duy nhất).
- `List<Transport>` và `Map<String,Transport>` được inject vào `Report` chỉ chứa ACTIVE, **không** chứa INTERNAL.
- `getBeanNamesForType(Transport.class)` và `getBeansOfType(Transport.class)` vẫn quan sát thấy hai bean type matches.
- `context.getBean("internalTransport", Transport.class)` vẫn hoạt động. Hai lần lookup theo tên trên một context trả cùng instance vì scope mặc định là singleton.

**ExcludedOnlyConfig — type match nhưng không có candidate:**

- Context có đúng một `Transport` type match, nhưng bean ấy `autowireCandidate=false`.
- `needsTransport(Transport candidate)` là required injection point; không có eligible candidate nên Spring không thể tạo bean `SingleConsumer` và context `refresh()` thất bại.
- `BeansException` được catch có chủ đích. **Không** dựa vào exact exception subclass/stack trace để chốt expected stdout.

**RestrictedConfig — defaultCandidate khác autowireCandidate:**

- `regularTransport` mặc định autowire candidate và default candidate.
- `restrictedTransport` được gắn `defaultCandidate=false` nhưng `isAutowireCandidate=true`.
- Tham số `Transport plain` chọn REGULAR khi không qualifier, còn `@Qualifier("restrictedTransport") Transport explicit` nhận RESTRICTED.
- `getBean("restrictedTransport")` cũng hoạt động; không phải vì setting là `true` hay `false`, mà vì đây là explicit lookup by name.

**Vì sao không có race/order dependency trong output:** ba contexts được tạo rồi đóng **lần lượt**. Mỗi method factory không cần gọi một `@Bean` khác trực tiếp; `proxyBeanMethods=false` là phù hợp. Phần liệt kê tên được sort; giá trị trả từ `FixedTransport` là cố định.

## 8. CLI và expected stdout

Đứng trong thư mục `candidate-restriction-demo` chứa `pom.xml`, chạy:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Ba lệnh phiên bản có output phụ thuộc môi trường. Lệnh cuối compile target Java 17 qua Maven Compiler Plugin rồi chạy main class với Spring dependencies.

**19 dòng stdout do chính chương trình Java in** (không tính Maven/Spring logging, warning hoặc exception diagnostics):

~~~text
main.typeNames=activeTransport,internalTransport
main.allTypeObjects=activeTransport,internalTransport
main.internalRegistered=true
main.internalCandidate=false
main.internalPrimary=true
main.activeCandidate=true
main.selected=ACTIVE
main.injectedList=ACTIVE
main.injectedMap=activeTransport
main.mapContainsInternal=false
main.explicitByName=INTERNAL
main.explicitSame=true
excludedOnly.failed=true
restricted.typeNames=regularTransport,restrictedTransport
restricted.plain=REGULAR
restricted.qualified=RESTRICTED
restricted.canAutowire=true
restricted.defaultCandidate=false
restricted.byName=RESTRICTED
~~~

### Nhóm output trọng tâm

| Output | Điều được kiểm chứng |
| --- | --- |
| `main.typeNames=activeTransport,internalTransport` | Type discovery nhận ra bean bị excluded |
| `main.internalCandidate=false` | Metadata definition chủ động loại internal khỏi autowiring |
| `main.internalPrimary=true` | Primary vẫn có trong metadata nhưng **không cứu** bean excluded |
| `main.injectedList=ACTIVE` | Autowired collection chỉ gồm eligible beans |
| `main.injectedMap=activeTransport` | Autowired map không có internal |
| `main.explicitByName=INTERNAL` | Name lookup vẫn lấy được excluded bean |
| `excludedOnly.failed=true` | Chỉ có excluded bean không đủ để thỏa required injection |
| `restricted.plain=REGULAR` | Bean defaultCandidate=false không chen vào plain type injection |
| `restricted.qualified=RESTRICTED` | Qualifier cho phép restricted default candidate được inject |
| `restricted.canAutowire=true` | `defaultCandidate=false` không đồng nghĩa `autowireCandidate=false` |

Chạy một bản sửa đổi khác với defaultCandidate/qualifier/primary/beans có thể làm các dòng trên đổi; dùng source gốc để đối chiếu. Spring có thể log context startup failure ở case excluded-only, nhưng expected output chỉ tính `System.out.println` của code.

## 9. Java 17 thuần: phân biệt registry và eligible candidates

Để hiểu cơ chế mà không cần Spring, tạo file độc lập **`ManualCandidateFilter.java`**:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class ManualCandidateFilter {
    interface Transport {
        String id();
    }

    public static void main(String[] args) {
        Map<String, Transport> registered = Map.of(
                "core", () -> "CORE",
                "internal", () -> "INTERNAL");
        Set<String> excluded = Set.of("internal");

        String names = registered.keySet().stream()
                .sorted().collect(Collectors.joining(","));
        String eligible = registered.keySet().stream()
                .filter(name -> !excluded.contains(name))
                .sorted().collect(Collectors.joining(","));

        System.out.println("registered=" + names);
        System.out.println("eligible=" + eligible);
        System.out.println("byType=" + registered.get("core").id());
        System.out.println("explicit=" + registered.get("internal").id());
    }
}
~~~

Lệnh Java thuần, chạy từ thư mục chứa file:

~~~bash
javac ManualCandidateFilter.java
java ManualCandidateFilter
~~~

Stdout chính xác:

~~~text
registered=core,internal
eligible=core
byType=CORE
explicit=INTERNAL
~~~

**Đây là mô hình tư duy bằng Java collections, không phải một bản sao thuật toán Spring.** `Map` không có BeanDefinition, qualifier, scope hoặc lifecycle. Điểm duy nhất cần nhìn là: object có trong registry (`registered`) **khác** object được phép chọn tự động (`eligible`), nhưng explicit lookup theo tên vẫn có thể lấy một object đã excluded.

## 10. XML pattern `default-autowire-candidates` và precedence

Ngoài cấu hình per bean, XML cho phép giới hạn **theo mẫu bean name** bằng `default-autowire-candidates` ở **top-level `<beans>`**:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd"
       default-autowire-candidates="*Repository,*Gateway">

    <bean id="orderRepository" class="demo.OrderRepository"/>
    <bean id="internalHelper" class="demo.InternalHelper"/>

    <bean id="explicitHelper"
          class="demo.InternalHelper"
          autowire-candidate="true"/>

    <bean id="blockedGateway"
          class="demo.InternalHelper"
          autowire-candidate="false"/>
</beans>
~~~

Đây là đoạn XML **giải thích chính sách**, giả định các demo classes `demo.OrderRepository`/`demo.InternalHelper` có tồn tại trong một project XML riêng.

Các mẫu `*Repository,*Gateway` dùng để chỉ những bean names phù hợp **mặc định** có thể làm autowire candidates. Nếu `internalHelper` không khớp mẫu, nó mặc định bị loại. Nhưng **khai tường minh** `autowire-candidate="true"` hoặc `"false"` trên một bean definition **được ưu tiên** so với pattern.

**Tại sao dùng tên để quy định candidate eligibility?** Đôi khi module có nhiều internal adapters không muốn expose cho autowiring toàn cục, và naming conventions đã tương đối chặt chẽ. Tuy nhiên, đổi bean name có thể làm nó bị lọc khác, nên cách này cần conventions/tests rõ ràng.

**Không nhầm** XML `default-autowire-candidates` (pattern, áp dụng theo bean names) với thuộc tính Java `@Bean(defaultCandidate=false)` (restricted default selection theo type/qualifier). Hai cơ chế này khác nhau cả vị trí khai báo lẫn semantics.

## 11. Các use case nên và không nên dùng exclusion

### Tình huống phù hợp

- **Infrastructure helper:** implementation cùng interface với các beans nghiệp vụ nhưng chỉ dùng nội bộ bởi một adapter riêng.
- **Diagnostic/probe client:** một client giả lập dùng để kiểm thử đường xử lý khác, không nên là lựa chọn tự động cho service sản phẩm.
- **Legacy compatibility bean:** bean vẫn phải tồn tại để giữ explicit references trong cấu hình cũ, nhưng không tham gia type-based autowiring mới.
- **Tách public API và internal delegate:** có bean được cấp theo đường explicit wiring ở composition root, nhưng các component khác inject interface theo type cần một implementation mặc định rõ ràng.

### Tình huống không nên dùng để che vấn đề khác

- Có nhiều implementations cùng type, nhưng mọi implementation đều hợp lệ cho một số use case: nên dùng **qualifier** hoặc policy `@Primary` thay vì exclude bừa một bean mà module khác cần.
- Một dependency **thật sự optional**: hãy diễn đạt bằng `Optional<T>`, `ObjectProvider<T>`, setter optional hoặc no-op strategy hợp lệ; exclusion không làm dependency required thành optional.
- Circular dependencies: thay đổi candidate filtering không phá vòng phụ thuộc giữa các objects.
- Bean bị thiếu do chưa đăng ký/cấu hình sai: đặt autowireCandidate=false khiến tình hình khó hiểu hơn.
- Dùng flag để tránh thiết kế interface phân biệt trách nhiệm: nếu một interface bị implement bởi 20 delegates không liên quan, hãy xem lại abstraction/module boundary.

Cũng không nên gắn `@Primary` cho excluded bean với hy vọng nó được chọn lại. **Primary là ưu tiên giữa candidates; exclusion là cắt một bean ra khỏi tập ấy.**

## 12. Lỗi thường gặp và cách debug theo đúng thứ tự

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Bean có trong `getBeanNamesForType` nhưng không được inject | `autowireCandidate=false` hoặc qualifier/generic filtering | Kiểm `BeanDefinition.isAutowireCandidate()` và injection point |
| `@Autowired Transport` báo thiếu dù có một bean cùng type | Bean ấy bị loại khỏi autowiring | Bỏ exclusion nếu đúng contract hoặc explicit wiring |
| Thêm `@Qualifier("internalTransport")` vẫn lỗi | Qualifier không biến excluded bean thành type candidate | Dùng đúng loại reference by name hoặc đổi metadata có chủ đích |
| `@Primary` trên bean bị loại không có hiệu lực | Primary chỉ chọn trong candidates hợp lệ | Kiểm `isPrimary` **và** `isAutowireCandidate` |
| `List<Transport>` thiếu một bean được đăng ký | Collection injection cũng lọc candidate eligibility | Phân biệt injected list với `getBeansOfType` |
| `Map<String,Transport>` khác type discovery map | Điểm autowire có rules riêng | Kiểm `getBeanNamesForType` rồi candidate filtering |
| `getBean("internalTransport")` vẫn thành công | Exclusion không xóa definition và không chặn name lookup | Đây là hành vi đúng |
| Bean bị excluded nhưng vẫn được tiêm `Settings` vào chính nó | Flag giới hạn bean như dependency của người khác | Đây là hành vi đúng; xem hai hướng phụ thuộc |
| `defaultCandidate=false` vẫn inject được qua qualifier | Chỉ loại khỏi default/plain type selection | Đây là hành vi đúng; khác autowireCandidate=false |
| Plain `Transport` chọn implementation lạ | Bean metadata, primary/fallback/defaultCandidate hoặc tên injection point | Xác định actual candidates từng context |
| `NoUniqueBeanDefinitionException` dù vừa exclude một bean | Vẫn còn nhiều eligible candidates | Dùng qualifier/primary hoặc tách interface hợp lý |
| XML pattern loại bean ngoài ý muốn | Bean name không khớp `default-autowire-candidates` | Kiểm patterns và explicit override |
| `@Bean` method không compile khi thêm attribute | Spring version/API khác giả định | Dùng Spring line phù hợp, kiểm actual `Bean` Javadoc |
| `NoSuchBeanDefinitionException` nhưng type discovery có beans | Candidate eligibility, qualifier hoặc scope/hierarchy | Đọc cause chain, không kết luận class không tồn tại |
| Java compile báo thiếu Spring annotation | Dependency/classpath Maven bị lỗi | Kiểm `spring-context` và JDK |
| Bean không được tạo dù vẫn registered | `@Lazy`, prototype, scope hoặc lifecycle khác | Đừng đồng nhất registration với eager instance creation |

### Quy trình chẩn đoán tối thiểu

1. Xác nhận **đúng context**, đúng bean registrations và interface/implementation type compatibility.
2. Dùng `getBeanNamesForType(T.class)` xem **những tên** được phát hiện.
3. Với bean nghi vấn, xem `BeanDefinition.isAutowireCandidate()`, `isDefaultCandidate()`, `isPrimary()`, `isFallback()` khi API line tương ứng hỗ trợ.
4. Kiểm **injection point**: `@Autowired T`, `List<T>`, `Map<String,T>`, qualifier, generic signatures hay explicit name reference?
5. Kiểm các điều kiện khác: Java module/classloader, proxy, scope, primary/fallback, XML patterns và parent contexts nếu có.
6. Đọc **root cause** của `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException`, thay vì cố match từng câu exception message.
7. Có test integration riêng cho composition root; giữ unit tests nghiệp vụ độc lập Spring bằng fake objects qua constructor khi phù hợp.

## 13. Bài tập tự kiểm chứng và checklist

Thử từng thay đổi **trên bản sao** của project, khôi phục source gốc trước khi so stdout mục 8:

1. **Bỏ exclusion:** sửa `@Bean(name="internalTransport",autowireCandidate=false)` thành bean bình thường. Dự đoán `main.injectedList`, `main.injectedMap` có thêm INTERNAL; vì INTERNAL còn `@Primary`, `main.selected` có thể đổi thành INTERNAL.
2. **Chỉ bỏ primary:** giữ `autowireCandidate=false`, bỏ `@Primary`. Dự đoán Report vẫn chọn ACTIVE, vì internal vốn không tham gia autowiring.
3. **Cố dùng qualifier để lấy excluded bean:** thêm `@Qualifier("internalTransport") Transport t` vào một bean khác. Dự đoán failure khi type-based autowiring không tìm eligible candidate ấy.
4. **Lookup bằng tên:** so `getBean("internalTransport", Transport.class)` hai lần; với singleton mặc định, identity phải trùng.
5. **Type-discovery snapshot:** so `getBeanNamesForType(Transport.class)` với `Report.injectedNames()` và giải thích khác biệt.
6. **Không có eligible bean:** chạy riêng ExcludedOnlyConfig, xác định lỗi tại injection point `needsTransport(Transport candidate)`, không phải do Java không biết Transport type.
7. **Giữ defaultCandidate=false:** thử `@Qualifier("restrictedTransport")` và bỏ qualifier trên bản sao; giải thích điểm khác với hard exclusion.
8. **Đổi restricted thành excluded:** thay `defaultCandidate=false` bằng `autowireCandidate=false` trong RestrictedConfig. Dự đoán qualifier lúc này không đủ để chọn bean.
9. **Biến excluded bean thành prototype:** thêm `@Scope("prototype")`, gọi `getBean("internalTransport")` hai lần; so việc lookup theo tên vẫn hoạt động với instance identity.
10. **Thêm second eligible bean:** đăng ký thêm `backupTransport` mà không primary. Dự đoán một required `Transport selected` có thể trở nên mơ hồ, dù excluded internal vẫn bị loại.
11. **Cấu hình XML:** thử `autowire-candidate="false"` và explicit XML `ref`, quan sát bean vẫn dùng được khi tham chiếu tên.
12. **XML pattern:** dùng `default-autowire-candidates="*Transport"`, quan sát bean names không khớp bị lọc trừ khi explicit override.
13. **In metadata trước khi inject:** viết một công cụ kiểm definition flags và type names trước khi gọi consumer beans.
14. **Dependency của excluded bean:** khai báo constructor method `internalTransport(Settings settings)`, chứng minh bean excluded **vẫn nhận Settings** từ container.
15. **Biên dịch Java thuần:** chạy `ManualCandidateFilter`, thêm một registry entry và điều chỉnh excluded set, rồi xem registered/eligible lists khác nhau.

### Checklist đạt bài

- [ ] Hiểu **registered bean**, **type match**, **autowire candidate** và **chosen bean** là các bước khác nhau.
- [ ] Biết XML `autowire-candidate="false"` và Java `@Bean(autowireCandidate=false)`.
- [ ] Biết bean excluded vẫn có thể tra bằng `getBean(name)`/explicit ref.
- [ ] Biết type-discovery APIs có thể hiển thị bean excluded.
- [ ] Biết injection đơn lẻ **và** injected List/Map đều xem candidate eligibility.
- [ ] Biết `@Primary` hoặc `@Qualifier` không tự phá hard exclusion.
- [ ] Phân biệt **`defaultCandidate=false`** với **`autowireCandidate=false`**.
- [ ] Hiểu excluded bean vẫn có thể **nhận dependencies vào chính nó**.
- [ ] Biết tác động của XML `default-autowire-candidates` patterns và override.
- [ ] Chạy được Spring Maven Java 17 demo ra đúng 19 dòng stdout và Java thuần ra 4 dòng.
- [ ] Debug theo bean definition metadata + injection point thay vì suy đoán từ type names.

## 14. Tổng kết và nguồn chính thức

`autowire-candidate=false` đặt một **ranh giới tham gia dependency injection**: bean vẫn tồn tại trong Spring container nhưng **không trở thành type-based autowire candidate** cho những nơi cần cùng interface/superclass. Các explicit references bằng tên vẫn có thể hoạt động.

`defaultCandidate=false` là mức hạn chế **nhẹ hơn** từ Spring 6.2+: tránh plain type injection nhưng vẫn cho phép qualified injection khi metadata phù hợp. `@Primary`/`@Fallback` chỉ giải quyết **ưu tiên trong tập candidates hợp lệ**, không thay đổi cờ exclusion.

Nguồn tài liệu:
- [Spring Framework — Autowiring Collaborators / Excluding a Bean from Autowiring](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-autowire.html)
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Primary and Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring API — `@Bean`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Bean.html)
- [Spring API — `BeanDefinition`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html)
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)

**Ghi nhớ:** Nếu Spring “nhìn thấy” một bean theo type nhưng không tự tiêm, hãy kiểm tra **`isAutowireCandidate()` trước khi thêm `@Primary` hoặc `@Qualifier`**. Chọn đúng cấp độ cấu hình giữa hard exclusion, restricted-default candidate và ưu tiên primary giúp DI rõ ràng, dễ bảo trì và không tạo dependency ambiguity ngoài dự kiến.