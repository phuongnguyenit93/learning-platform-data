# Cung cấp nguồn bean bổ sung bằng addPrimarySources và setSources

## 1. Tại sao SpringApplication cần nhiều nguồn bean?

Khi khởi động, `SpringApplication` phải biết **những nguồn định nghĩa bean** cần đưa vào `ApplicationContext`. Trường hợp quen thuộc nhất là:

```java
SpringApplication.run(MyApplication.class, args);
```

Ở đây `MyApplication.class` là **nguồn chính (primary source)**. Nếu lớp này gắn `@SpringBootApplication`, nó thường mang theo cấu hình tự động và quy tắc quét các thành phần Spring ở package của lớp khởi động cùng các package con. Khi một nhóm bean được định nghĩa ở **package nằm ngoài vùng quét mặc định**, hoặc được cung cấp bằng lớp cấu hình/XML theo một tổ hợp chạy cụ thể, ứng dụng có thể cần khai báo thêm nguồn.

`SpringApplication` cung cấp hai API liên quan trực tiếp đến việc này:

- `addPrimarySources(Collection<Class<?>>)`: **bổ sung các lớp nguồn chính** vào tập nguồn đã có từ constructor. Đối số là các đối tượng `Class<?>`.
- `setSources(Set<String>)`: **thiết lập tập nguồn bổ sung dạng chuỗi**, có thể là **tên lớp đầy đủ**, **tên package** hoặc **vị trí tài nguyên XML**. Tập này được nạp **cùng với** các nguồn chính, chứ không thay thế chúng.

Sau khi cấu hình, `application.run(args)` mới tạo và làm mới `ApplicationContext`, trong đó Spring sẽ nạp định nghĩa bean từ các nguồn phù hợp.

> **Phân biệt thuật ngữ:** `primary source` ở đây là *nguồn nạp cấu hình/bean* của ứng dụng. Nó **không phải** chú thích `@Primary` dùng để ưu tiên một bean khi tiêm phụ thuộc giữa nhiều bean cùng kiểu. “Thêm nguồn” cũng không đồng nghĩa với “tạo đúng một bean”: một lớp `@Configuration` có thể khai báo nhiều phương thức `@Bean` và có thể đưa vào các cấu hình khác.

## 2. Ba tập nguồn và thời điểm chúng được dùng

Hãy hình dung:

```text
new SpringApplication(App.class)
        │
        ├── Primary sources ban đầu
        │       └── App.class
        │
        ├── addPrimarySources(List.of(ExtraConfig.class))
        │       └── Thêm ExtraConfig.class vào primary sources
        │
        └── setSources(Set.of("com.example.other.NamedConfig"))
                └── Thiết lập additional sources dạng String
                                │
                          getAllSources()
                                │
               App.class + ExtraConfig.class
                     + "com.example.other.NamedConfig"
                                │
                             run(args)
                                │
                     Nạp định nghĩa bean
                                │
                        ApplicationContext
```

Có bốn phương thức cần phân biệt:

| API | Tham số / kiểu trả về | Ý nghĩa |
|---|---|---|
| `new SpringApplication(App.class)` | `Class<?>...` | Xác lập lớp nguồn chính ban đầu. |
| `addPrimarySources(...)` | `Collection<Class<?>>` | Thêm các lớp nguồn chính mà không xóa nguồn chính từ constructor. |
| `setSources(...)` | `Set<String>` | Thiết lập lại tập **nguồn bổ sung dạng chuỗi**. Không xóa các primary source. |
| `getSources()` | `Set<String>`, có thể sửa | Xem/thêm/bớt các nguồn bổ sung dạng chuỗi. Không bao gồm primary source. |
| `getAllSources()` | `Set<Object>`, không thể sửa | Xem hợp nhất primary sources và additional sources; phần tử có thể vừa là `Class` vừa là `String`. |

**Phép cộng và phép thay thế xảy ra ở hai tập khác nhau.** `addPrimarySources(...)` bổ sung vào tập primary, còn một lần `setSources(...)` thay tập additional hiện tại bằng giá trị được cung cấp. Ngay cả khi gọi `setSources(Set.of())`, nguồn `App.class` truyền vào constructor vẫn còn.

Các phương thức này nên được gọi **trước `run(args)`**. Sau khi một `ApplicationContext` đã được tạo và làm mới, việc thay đổi danh sách nguồn trên đối tượng `SpringApplication` không phải cơ chế bổ sung bean động vào context đang chạy.

## 3. Ví dụ Java 17+ chạy được: một nguồn chính và hai nguồn bổ sung

Mục tiêu thực hành: lớp khởi động nằm ở `com.example.launch`, còn hai lớp cấu hình nằm ở các package anh em `com.example.extra.primary` và `com.example.extra.named`. Vì vậy chúng **không nằm trong phạm vi quét mặc định** của `@SpringBootApplication` đặt tại `com.example.launch`. Ta chủ động đưa chúng vào context bằng hai API tương ứng.

Cấu trúc nguồn:

```text
source-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/
    └── com/example/
        ├── launch/
        │   └── SourceLaunchApplication.java
        └── extra/
            ├── primary/
            │   └── WarehouseConfiguration.java
            └── named/
                └── FeatureConfiguration.java
```

`settings.gradle`:

```groovy
rootProject.name = 'source-demo'
```

`build.gradle` (dự án ví dụ Spring Boot 3.3.x, Gradle wrapper phù hợp, Java 17):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Ứng dụng không cần HTTP, vì vậy dùng `spring-boot-starter` và đặt chế độ `WebApplicationType.NONE`. Dự án thực tế phải giữ plugin/phiên bản Java đã được cấu hình sẵn nếu khác ví dụ này.

**Tệp `src/main/java/com/example/extra/primary/WarehouseConfiguration.java`:**

```java
package com.example.extra.primary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class WarehouseConfiguration {

    @Bean("warehouse")
    public String warehouse() {
        return "primary-class";
    }
}
```

**Tệp `src/main/java/com/example/extra/named/FeatureConfiguration.java`:**

```java
package com.example.extra.named;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean("feature")
    public String feature() {
        return "string-class-name";
    }
}
```

**Tệp `src/main/java/com/example/launch/SourceLaunchApplication.java`:**

```java
package com.example.launch;

import java.util.List;
import java.util.Set;

import com.example.extra.named.FeatureConfiguration;
import com.example.extra.primary.WarehouseConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class SourceLaunchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(SourceLaunchApplication.class);

        // Thêm một Class vào nhóm primary sources.
        application.addPrimarySources(List.of(WarehouseConfiguration.class));

        // Tên lớp đầy đủ là một String trong nhóm additional sources.
        application.setSources(Set.of(FeatureConfiguration.class.getName()));

        // Ví dụ không tạo Web server, nên tiến trình có thể kết thúc sau khi in.
        application.setWebApplicationType(WebApplicationType.NONE);

        System.out.println("Nguon khai bao: " + application.getAllSources().size());

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("warehouse=" +
                    context.getBean("warehouse", String.class));
            System.out.println("feature=" +
                    context.getBean("feature", String.class));
        }
    }
}
```

Nếu dự án có Gradle Wrapper, chạy tại thư mục dự án:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Các dòng do **chính chương trình** in ra là:

```text
Nguon khai bao: 3
warehouse=primary-class
feature=string-class-name
```

Ngoài ba dòng trên, Spring Boot/Gradle có thể in banner và log khởi động/kết thúc. Giá trị `3` là **số nguồn được khai báo**, không phải tổng số bean trong context. `WarehouseConfiguration.class` được nạp từ `addPrimarySources`; `FeatureConfiguration` được nạp từ **tên lớp đầy đủ** trong `setSources`. Mỗi lớp cấu hình khai báo một bean chuỗi có tên riêng để phép kiểm tra đơn giản, rõ ràng.

Chú ý: hai package `com.example.extra.*` cùng bắt đầu bằng `com.example` nhưng không nằm trong `com.example.launch`. Spring không tự quét **mọi package có chung tiền tố cao hơn**. Vì vậy ví dụ này thể hiện được tác dụng của việc bổ sung nguồn.

### Quan sát từng API bằng thay đổi có kiểm soát

- Tạm bỏ dòng `application.addPrimarySources(...)`, chạy lại: bean `warehouse` không được khai báo bởi nguồn nào còn lại. Lệnh `getBean("warehouse", String.class)` sẽ báo lỗi không tìm thấy bean đó; `feature` vẫn là nguồn bổ sung. Để quan sát `feature` trước khi lỗi, hãy đổi thứ tự hai dòng `getBean` hoặc kiểm tra `context.containsBean("feature")`.
- Khôi phục dòng trên rồi bỏ `application.setSources(...)`: `warehouse` vẫn có vì primary sources còn nguyên; bean `feature` không được định nghĩa bởi nguồn còn lại, nên phép `getBean("feature", String.class)` sẽ thất bại.
- Khôi phục cả hai: cả hai bean được nạp. Đây là bằng chứng thực nghiệm rằng hai nhóm nguồn được **hợp nhất** khi Spring khởi động.

Nếu chạy với đối số hoặc tệp cấu hình thực tế làm thay đổi danh sách nguồn/điều kiện tạo bean, cần kiểm tra thêm những đầu vào ấy trước khi diễn giải kết quả.

## 4. Sử dụng addPrimarySources đúng cách

Chữ ký API:

```java
void addPrimarySources(Collection<Class<?>> additionalPrimarySources);
```

`Class<?>` là đối tượng đại diện cho lớp Java, không phải chuỗi tên lớp. Dùng `List.of(...)` hoặc một `Collection<Class<?>>` tương ứng:

```java
SpringApplication application = new SpringApplication(App.class);

application.addPrimarySources(
        List.of(DatabaseConfig.class, BusinessConfig.class));

application.run(args);
```

Đoạn này chỉ minh họa cấu hình API, giả định `App`, `DatabaseConfig` và `BusinessConfig` là các lớp thật trên classpath. Lớp nguồn thường là `@Configuration` hoặc lớp được Spring hỗ trợ làm nguồn định nghĩa bean. Đừng gán mọi lớp Java thông thường vào đây và kỳ vọng bất kỳ đối tượng nào cũng trở thành bean hữu ích.

Các đặc điểm quan trọng:

1. **Thêm, không thay thế:** `App.class` từ constructor được giữ; `DatabaseConfig.class` và `BusinessConfig.class` được bổ sung.
2. **Có thể gọi nhiều lần:** các lớp được hợp vào tập primary sources; vì dùng cơ chế tập hợp, đưa chính cùng một đối tượng `Class` nhiều lần không nhằm tạo nhiều bean khác nhau.
3. **Kiểm tra tính hiện diện của lớp khi biên dịch:** viết `DatabaseConfig.class` giúp compiler xác nhận lớp được tham chiếu có thể truy cập. Đây là lợi thế khi cấu hình tĩnh bằng mã Java.
4. **Không chọn bean mặc định:** `primary` trong API không khiến các bean từ nguồn này thắng bean cùng kiểu được định nghĩa ở nguồn khác; chọn bean khi tiêm phụ thuộc là trách nhiệm của `@Primary`, `@Qualifier`, tên bean và các quy tắc của Spring.
5. **Không tự mở rộng quét package toàn ứng dụng:** thêm một lớp `@Configuration` ngoài vùng quét là cách nạp rõ ràng cấu hình đó; cơ chế quét phụ thuộc vào những annotation và quy tắc cấu hình thực tế của mỗi nguồn.

Spring Boot Javadoc lưu ý rằng phần lớn trường hợp có thể cân nhắc `getSources()`/`setSources(...)` thay cho `addPrimarySources(...)`. Tuy nhiên API này hữu ích khi cần thêm **lớp cấu hình bằng tham chiếu kiểu Java trực tiếp** vào tập primary.

## 5. Sử dụng setSources đúng cách

Chữ ký API:

```java
void setSources(Set<String> sources);
```

Mỗi phần tử `String` có thể biểu thị một trong các loại nguồn Spring Boot hỗ trợ:

| Kiểu nguồn | Ví dụ | Điều kiện để hoạt động |
|---|---|---|
| Tên lớp đầy đủ (FQCN) | `"com.example.extra.named.FeatureConfiguration"` | Lớp có trên runtime classpath và có thể được Spring nạp làm nguồn. |
| Tên package | `"com.example.plugins"` | Có các thành phần phù hợp quy tắc quét trong package đó và classpath thực tế. |
| Vị trí tài nguyên XML | `"classpath:extra-beans.xml"` | Tài nguyên XML hợp lệ có thể được `XmlBeanDefinitionReader` đọc. |

### Cấp lớp cấu hình bằng tên đầy đủ

```java
SpringApplication application = new SpringApplication(App.class);
application.setSources(Set.of(
        "com.example.extra.named.FeatureConfiguration",
        "com.example.extra.audit.AuditConfiguration"));
application.run(args);
```

Ở đây các chuỗi là **tên lớp**, không phải tên bean. Spring phải có thể tìm thấy chúng trên classpath. Khi biết lớp ở thời điểm viết mã, `FeatureConfiguration.class.getName()` an toàn hơn việc gõ tên thủ công vì thao tác đổi tên lớp trong IDE thường cập nhật tham chiếu Java.

### Cấp tên package để quét

```java
SpringApplication application = new SpringApplication(App.class);
application.setSources(Set.of("com.example.plugins"));
application.run(args);
```

Nguồn dạng package yêu cầu có các lớp mà bộ quét Spring nhận diện được (ví dụ lớp gắn `@Component`/`@Service` hoặc `@Configuration`). Chỉ tạo một lớp POJO không annotation trong package đó không đồng nghĩa Spring sẽ đăng ký nó thành bean. Cần cân nhắc phạm vi quét, bởi quét rộng có thể nạp thêm nhiều component ngoài ý định.

### Cấp nguồn XML

Với tệp `src/main/resources/extra-beans.xml` hợp lệ, có thể dùng:

```java
SpringApplication application = new SpringApplication(App.class);
application.setSources(Set.of("classpath:extra-beans.xml"));
application.run(args);
```

Ví dụ XML tối giản để khai báo bean tên `externalName`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="externalName" class="java.lang.String">
        <constructor-arg value="from-xml"/>
    </bean>
</beans>
```

Khi XML có trên classpath và đọc thành công, có thể truy xuất `context.getBean("externalName", String.class)`. Hãy kiểm tra thực tế phụ thuộc và khả năng đọc tài nguyên XML khi áp dụng vào project cụ thể. Cơ chế này dành cho ứng dụng cần tích hợp cấu hình XML cũ; với ứng dụng Spring Boot mới, cấu hình Java thường đơn giản hơn.

## 6. Thay thế và nối thêm: lỗi hiểu nhầm phổ biến nhất

`setSources(...)` có **nghĩa là đặt tập additional sources hiện tại**, không mang nghĩa “cộng thêm mỗi lần gọi”.

```java
SpringApplication application = new SpringApplication(App.class);

application.setSources(Set.of("com.example.config.OneConfig"));
application.setSources(Set.of("com.example.config.TwoConfig"));

// Additional sources hiện tại: chỉ "TwoConfig".
// Primary source App.class vẫn còn.
```

Nếu muốn nối thêm nguồn chuỗi và giữ nguồn đã có, dùng tập mutable mà API trả về:

```java
SpringApplication application = new SpringApplication(App.class);

application.setSources(Set.of("com.example.config.OneConfig"));
application.getSources().add("com.example.config.TwoConfig");

// Cả OneConfig và TwoConfig thuộc additional sources.
```

Hoặc tập hợp tất cả nguồn cần nạp rồi gọi `setSources(...)` **một lần**:

```java
application.setSources(Set.of(
        "com.example.config.OneConfig",
        "com.example.config.TwoConfig"));
```

Ở cả ba đoạn, những lớp `App`/`OneConfig`/`TwoConfig` là tên minh họa; chúng phải thật sự tồn tại nếu bạn dùng để chạy. Việc gọi `getSources().add(...)` thay đổi **tập additional sources**, không sửa tập primary sources.

Để quan sát, có thể dùng:

```java
System.out.println(application.getSources());
System.out.println(application.getAllSources());
```

Với mô hình đơn giản ở phần 3, `getSources()` có một **chuỗi** tên lớp `FeatureConfiguration`; `getAllSources()` có ba nguồn gồm hai đối tượng `Class` và một `String`. `getAllSources()` là tập xem tổng hợp không sửa trực tiếp; muốn thay đổi hãy dùng API thích hợp **trước khi chạy**.

## 7. Một bean được nạp thêm không có nghĩa nó luôn sẵn sàng sử dụng

Việc thêm source chỉ tạo cơ hội để Spring **đọc và đăng ký định nghĩa bean**. Bean còn phụ thuộc vào các điều kiện và vòng đời Spring:

- **`@Profile`:** một cấu hình hoặc bean gắn `@Profile("dev")` có thể bị bỏ qua khi profile `dev` không kích hoạt.
- **`@Conditional...`:** định nghĩa bean có thể chỉ được đăng ký khi điều kiện được đáp ứng.
- **Phụ thuộc constructor/`@Bean`:** source đã được tìm thấy nhưng quá trình khởi tạo vẫn có thể lỗi do thiếu bean phụ thuộc, cấu hình hoặc kết nối dịch vụ.
- **Tên bean trùng:** hai nguồn đưa vào cùng một bean name có thể gây lỗi trùng định nghĩa (Spring Boot thường không cho phép ghi đè bean definition theo mặc định). Không giải quyết xung đột bằng cách cho phép override toàn cục một cách tùy tiện.
- **Classpath:** một FQCN hoặc XML resource được khai báo nhưng không có trong gói chạy sẽ làm nạp source thất bại; việc khai báo chuỗi không tự thêm dependency hay copy resource vào JAR.

Muốn kiểm tra **bean đã có trong context**, dùng `containsBean(...)` hoặc `getBean(...)` sau khi `run(args)` hoàn tất:

```java
try (ConfigurableApplicationContext context = application.run(args)) {
    System.out.println(context.containsBean("warehouse"));
}
```

Khi dự án không có bean tên `warehouse` thì `containsBean` cho `false`; khi có thì cho `true`. Ngược lại, `getAllSources()` chỉ chứng minh ứng dụng đang **khai báo nguồn**, không chứng minh bean cụ thể đã được tạo thành công.

## 8. So sánh với những cách thêm bean khác

| Nhu cầu | Cơ chế thường dùng | Khác với việc chỉnh source của SpringApplication |
|---|---|---|
| Thêm lớp `@Configuration` không nằm trong component scan | `addPrimarySources(List.of(Config.class))` hoặc `setSources(Set.of(Config.class.getName()))` | Nạp cấu hình trực tiếp tại bước bootstrap. |
| Cấu hình biết trước từ một lớp cấu hình | `@Import(Config.class)` | Quan hệ import nằm trong cấu hình Spring, không cần lệnh trong `main`. |
| Muốn quét một vùng package cố định | `@ComponentScan(basePackages = "...")` hoặc một source dạng package | Component scan có thể mở rộng số component được tìm thấy. |
| Muốn khai báo bean do code tạo | `@Bean` trong `@Configuration` | Chính phương thức `@Bean` định nghĩa bean; source chỉ giúp Spring tìm thấy cấu hình chứa nó. |
| Muốn đổi giá trị cấu hình runtime | `application.properties`, môi trường, command-line properties | Đây là dữ liệu cấu hình (property), không phải danh sách lớp/package/XML được dùng để nạp bean. |
| Muốn đăng ký bean sau khi context đã chạy | Cơ chế đăng ký động được thiết kế riêng, nếu thực sự cần | Không thể coi việc gọi `setSources` sau `run` là hot reload các bean. |

Với ứng dụng bình thường, một lớp `@SpringBootApplication` ở package gốc hợp lý, các `@Configuration` liên quan được quét hoặc `@Import`, thường dễ hiểu và dễ bảo trì. Dùng hai API đang học khi **quyền quyết định nguồn nạp cần nằm ở mã bootstrap** hoặc cấu hình source phải được lắp ghép theo môi trường/module.

## 9. Chẩn đoán lỗi khi khai báo nguồn bổ sung

| Biểu hiện | Nguyên nhân có thể gặp | Cách xác minh |
|---|---|---|
| `NoSuchBeanDefinitionException` cho bean mong đợi | Source chưa nạp, bean có điều kiện không thỏa, hoặc sai tên/kiểu bean | So sánh `getAllSources()`; kiểm tra annotation, profile/condition, tên bean và package. |
| Không tìm thấy lớp khi nạp nguồn chuỗi | Gõ sai FQCN hoặc classpath thiếu lớp/dependency | Xem chuỗi `setSources`, kiểm tra class/đường dẫn trong output build và JAR. |
| Đọc XML thất bại | Vị trí resource sai, XML không hợp lệ, hoặc thiếu phụ thuộc hỗ trợ | Xác nhận tệp dưới `src/main/resources` và đường dẫn `classpath:...`; đọc lỗi gốc. |
| Nạp nhiều bean ngoài dự tính | Dùng nguồn package/quét package quá rộng | Thu hẹp package; dùng `@Import`/lớp cấu hình cụ thể nếu phù hợp. |
| Trùng tên bean hoặc xung đột bean definition | Hai cấu hình khai báo cùng bean name hoặc bị quét lặp bằng cơ chế khác | Đối chiếu mọi source và vùng component scan, sửa tên/cấu hình trùng. |
| Đã gọi hai lần `setSources` nhưng mất source lần đầu | Lần sau **thay** tập additional sources | Dùng một `Set` đầy đủ hoặc `getSources().add(...)`. |
| Hiểu `getAllSources().size()` là số bean | Source ≠ bean; một source có thể sinh nhiều bean | Dùng `context.getBeanDefinitionNames()` hoặc truy vấn bean cụ thể sau khi chạy. |
| Sửa sources khi ứng dụng đang chạy nhưng không thấy thay đổi | Context đã được refresh | Thiết lập nguồn trước `run` và khởi động lại khi cần. |

Không dựa vào thứ tự phần tử của tập sources để điều khiển ưu tiên tiêm phụ thuộc hay giải quyết xung đột. Ngay cả khi `LinkedHashSet` giữ thứ tự lặp, điều đó không tạo một cam kết “bean nguồn sau thắng nguồn trước”. Dùng cơ chế Spring phù hợp cho việc lựa chọn bean.

## 10. Bài tập tự kiểm chứng

Thực hiện với project ở phần 3, mỗi lần thay đổi chỉ một yếu tố:

1. Chạy đủ hai dòng `addPrimarySources(...)` và `setSources(...)`; xác nhận số nguồn là `3` và hai bean `warehouse`, `feature` cùng tồn tại.
2. Tạm bỏ `addPrimarySources(...)`. Thay `getBean("warehouse", ...)` bằng `containsBean("warehouse")` để ứng dụng không dừng vì exception; kiểm tra `false`. Giữ `getBean("feature", ...)` để thấy bean còn lại.
3. Khôi phục nguồn primary, tạm bỏ `setSources(...)`. Kiểm tra `containsBean("feature") == false` trong khi `warehouse` vẫn xuất hiện.
4. Thay nguồn chuỗi của `FeatureConfiguration` bằng FQCN gõ sai, rồi quan sát lỗi nạp source. Khôi phục tên đúng; cân nhắc dùng `FeatureConfiguration.class.getName()` khi mã tham chiếu trực tiếp đến class.
5. Thử gọi `setSources(...)` hai lần với hai nguồn khác nhau; in `getSources()` trước `run` để xác minh chỉ tập cuối cùng được giữ, sau đó sửa thành một lần gọi với tập đầy đủ.

Có thể tự giải thích được ba câu sau là bạn đã nắm cơ chế: **(a)** nguồn chính khác nguồn bổ sung ở điểm nào, **(b)** vì sao `setSources` không xóa lớp truyền vào constructor, **(c)** vì sao một source có trong `getAllSources()` vẫn chưa chắc tạo ra bean mong đợi.

## Tài liệu tham khảo

- Spring Boot 3.3 API, `SpringApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Đọc trực tiếp JavaDoc của `addPrimarySources`, `setSources`, `getSources` và `getAllSources` để đối chiếu chữ ký, các loại nguồn hợp lệ và ý nghĩa của tập nguồn trước khi áp dụng vào phiên bản Spring Boot khác.