# @ConditionalOnMissingClass chọn phương án khi thư viện không có mặt

## 1. Mục tiêu

Một thư viện Spring Boot có thể hỗ trợ hai cách hoạt động: sử dụng một SDK/JAR tùy chọn khi nó có mặt và dùng cách dự phòng khi nó vắng mặt. Ví dụ, một module có thể ưu tiên tích hợp trình mã hóa của bên thứ ba; nhưng nếu người dùng không cài thư viện đó, module vẫn cần một implementation cơ bản không phụ thuộc SDK.

`@ConditionalOnMissingClass` của Spring Boot phục vụ đúng trường hợp **phụ thuộc classpath vắng mặt**:

```java
@ConditionalOnMissingClass("com.vendor.sdk.OptionalClient")
```

Khi class có tên trên không thể được tìm thấy bằng classloader đang được Spring Boot xét, điều kiện có thể khớp. Khi class có mặt, điều kiện không khớp và phần cấu hình được đánh dấu sẽ không được đăng ký qua đường xử lý tương ứng.

Bài học sẽ làm rõ:

1. Điều kiện dựa trên **class** khác với điều kiện dựa trên **bean** hoặc **property** như thế nào.
2. Vì sao `@ConditionalOnMissingClass` cần tên class dưới dạng `String`, và việc đặt trên lớp cấu hình có lợi gì cho an toàn class loading.
3. Cách phối hợp điều kiện vắng mặt và có mặt để chọn đúng một strategy.
4. Cách thiết kế auto-configuration với dependency tùy chọn, đăng ký qua `.imports`, không mở rộng component scan.
5. Cách tự chạy một ứng dụng Spring Boot ở hai chế độ: **không có Jackson** và **có Jackson**, kiểm tra kết quả, điều kiện và lỗi cấu hình.

Trọng tâm là **lựa chọn cấu hình theo sự vắng mặt của thư viện**, không phải chỉ giới thiệu cú pháp annotation.

## 2. Phân biệt ba loại “không có”

Các annotation điều kiện thường gặp kiểm tra những tầng khác nhau:

| Annotation | Nó hỏi điều gì? | Ví dụ |
| --- | --- | --- |
| `@ConditionalOnMissingClass` | Class có tên xác định **không hiện diện** trên classpath được kiểm tra? | Không có `com.vendor.sdk.Client` |
| `@ConditionalOnClass` | Class có tên xác định **hiện diện** trên classpath? | Có `com.fasterxml.jackson.databind.ObjectMapper` |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp trong `ApplicationContext` khi điều kiện được xét? | Không có bean type `MessageFormatter` |
| `@ConditionalOnProperty` | Một property cấu hình có giá trị phù hợp? | `feature.enabled=true` |
| `@ConditionalOnResource` | Một resource có mặt tại vị trí chỉ định? | Resource cấu hình bổ sung tồn tại? |

**Có class không đồng nghĩa có bean.** Một JAR có thể chứa `ObjectMapper.class`, nhưng không có bean `ObjectMapper` vì auto-configuration bị loại hoặc người dùng không đăng ký bean ấy.

**Không có class khác với không có dependency Maven ở mức khai báo.** Một class có thể được đưa vào runtime qua một dependency gián tiếp; ngược lại, Maven có thể biên dịch cùng một dependency nhưng đóng gói hoặc chạy với classpath loại bỏ nó. Điều kiện dựa vào classloader hiệu lực khi ứng dụng chạy, không đơn thuần đọc danh sách dependency trực tiếp trong `pom.xml`.

**Không có bean khác với không tạo bean vì lazy.** `@ConditionalOnMissingBean` xét thông tin bean definition tại thời điểm thích hợp; bean có definition nhưng chưa khởi tạo singleton vẫn không mặc nhiên bị xem là “missing”.

## 3. API chính xác của @ConditionalOnMissingClass

Trong Spring Boot 3.3.x, tên đầy đủ:

```java
org.springframework.boot.autoconfigure.condition.ConditionalOnMissingClass
```

Cấu trúc annotation được rút gọn để đọc:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnClassCondition.class)
public @interface ConditionalOnMissingClass {
    String[] value() default {};
}
```

Đây là **mô tả API**, không phải file Java cần copy vào dự án. Spring Boot đã cung cấp annotation này.

Cách dùng:

```java
@ConditionalOnMissingClass("com.vendor.sdk.Client")
```

Hoặc với nhiều tên:

```java
@ConditionalOnMissingClass({
    "com.vendor.sdk.Client",
    "com.vendor.sdk.ClientBuilder"
})
```

Với nhiều class, điều kiện yêu cầu **các class được liệt kê đều vắng mặt**. Nếu bất kỳ class nào được phát hiện, điều kiện thiếu class không còn được thỏa đối với tập đó.

### Chú ý đặc biệt: không có thuộc tính name

`@ConditionalOnMissingClass` có **một thuộc tính `value()` kiểu `String[]`**, vì vậy dạng sau là **sai cú pháp**:

```java
// SAI: @ConditionalOnMissingClass không khai báo "name".
@ConditionalOnMissingClass(name = "com.vendor.sdk.Client")
```

Cách đúng:

```java
@ConditionalOnMissingClass("com.vendor.sdk.Client")
```

Ngược lại, `@ConditionalOnClass` có thể dùng cả class literal:

```java
@ConditionalOnClass(SomeLibraryType.class)
```

hoặc tên class:

```java
@ConditionalOnClass(name = "com.vendor.sdk.Client")
```

Với điều kiện vắng mặt, sử dụng **chuỗi tên class** tránh việc source code trực tiếp yêu cầu import `Client` chỉ để xác định class không có. Nó cũng phù hợp với việc một nhánh được biên dịch và chạy trong môi trường không mang SDK tùy chọn.

### Kết quả của điều kiện

```text
@ConditionalOnMissingClass("com.vendor.sdk.Client")

Runtime classpath KHÔNG có class đó -> condition MATCH
Runtime classpath CÓ class đó       -> condition NO MATCH
```

Đây là quyết định có cho phép thành phần được cấu hình tiếp hay không. `MATCH` không đảm bảo mọi bean trong lớp cấu hình đều được tạo, vì vẫn có thể có các condition khác và lỗi khởi tạo bean.

## 4. Vì sao điều kiện classpath được kiểm tra sớm?

`@ConditionalOnMissingClass` sử dụng `OnClassCondition` của Spring Boot. Khi Spring phân tích cấu hình, Boot có thể đánh giá sự hiện diện của các tên class mà không nhất thiết phải khởi tạo class hay tạo bean nghiệp vụ.

Trong cơ chế auto-configuration:

```text
@SpringBootApplication
  -> @EnableAutoConfiguration
    -> tìm ứng viên từ AutoConfiguration.imports
      -> chọn / lọc ứng viên phù hợp
        -> kiểm tra các @Conditional trên lớp @AutoConfiguration
          -> kiểm tra cấu hình lồng và @Bean
            -> đăng ký BeanDefinition hợp lệ
              -> tạo bean theo BeanFactory/lifecycle
```

Sơ đồ trên chỉ diễn tả các giai đoạn lớn. Một số bộ lọc tối ưu có thể quyết định sớm hơn việc phân tích chi tiết lớp cấu hình, nhờ metadata được sinh ở pha compile. Thứ tự xử lý condition, import và bean definition có các chi tiết triển khai mà sơ đồ cố ý bỏ qua.

Điều quan trọng: **class condition là phép chọn cấu hình theo môi trường classpath**, không phải lời gọi `Class.forName(...)` tùy tiện trong code nghiệp vụ. Spring Boot hỗ trợ các đường đọc annotation metadata, có thể dùng ASM để kiểm tra mà không phải nạp class được mô tả ngay.

### Metadata và annotation

Đối với auto-configuration do thư viện tạo, annotation processor có thể sinh:

```text
META-INF/spring-autoconfigure-metadata.properties
```

Thông tin tĩnh có thể hỗ trợ bước lọc ứng viên. Nó **khác** tệp:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Tệp `.imports` cung cấp **tên lớp ứng viên**, còn metadata `.properties` hỗ trợ **tối ưu điều kiện**. Và cả hai đều khác `spring-configuration-metadata.json` vốn phục vụ IDE/tooling về các key cấu hình.

Không được suy luận rằng metadata thiếu thì tính năng dự phòng không thể hoạt động. Spring vẫn có đường đánh giá điều kiện chính thức khi ứng viên được xử lý; metadata tối ưu không thay thế nguồn sự thật là annotation cùng classpath runtime.

## 5. Đặt điều kiện trên lớp cấu hình thay vì chỉ trên phương thức @Bean

Xét một module giả định phụ thuộc SDK tùy chọn:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.sdk.OptionalClient")
class VendorClientConfiguration {

    @Bean
    VendorClientAdapter adapter(com.vendor.sdk.OptionalClient client) {
        return new VendorClientAdapter(client);
    }
}
```

Đây là **snippet minh họa, không biên dịch độc lập**: `VendorClientAdapter` và `OptionalClient` thuộc các lớp giả định. Khi SDK không có mặt, class hoặc method signature của nhánh này có thể gây vấn đề class loading nếu chúng được tham chiếu trước khi điều kiện có cơ hội can thiệp.

Spring Boot khuyến cáo đặt **class condition trên một lớp cấu hình riêng** để cô lập những chữ ký phương thức `@Bean` phụ thuộc thư viện tùy chọn. Dùng `@Configuration(proxyBeanMethods=false)` lồng tĩnh hoặc một lớp cấu hình độc lập là những cách phổ biến.

Ví dụ tổ chức hai nhánh:

```java
@AutoConfiguration
class ClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.OptionalClient")
    static class VendorConfiguration {
        // Chỉ định nghĩa những bean sử dụng SDK khi SDK hiện diện.
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingClass("com.vendor.sdk.OptionalClient")
    static class FallbackConfiguration {
        // Định nghĩa bean dự phòng không cần SDK.
    }
}
```

Đây là code sơ đồ về tổ chức lớp. Điểm mấu chốt: **nhánh dự phòng không được import, return hoặc inject type chỉ có trong SDK bị thiếu**. Trả về một interface/kiểu thuộc API cốt lõi của module để dependency injection không yêu cầu class vắng mặt.

`@ConditionalOnMissingClass` có thể đặt trên phương thức, nhưng nếu chính **return type** hoặc **tham số** của phương thức là class có thể thiếu, JVM có thể phải resolve method metadata trước khi condition bảo vệ được chương trình. Do đó không nên dựa riêng vào annotation đặt trên `@Bean` method để che một chữ ký dùng SDK tùy chọn.

### Trường hợp annotation hợp thành (meta-annotation)

Spring Boot lưu ý khi gói điều kiện classpath trong annotation hợp thành, cần dùng **tên lớp dạng chuỗi** cho các class tùy chọn, vì sự an toàn của class literal khi điều kiện đặt trực tiếp không được bảo đảm như nhau khi qua tầng meta-annotation.

Với `@ConditionalOnMissingClass`, dạng string đã là lựa chọn bắt buộc; với `@ConditionalOnClass`, khi thiết kế annotation hợp thành hãy dùng `name` thay cho class literal.

## 6. Thiết kế phương án dự phòng: một abstraction, hai implementation

Giả sử thư viện cung cấp abstraction:

```java
public interface MessageFormatter {
    String mode();
}
```

Có hai implementation:

- `basic`: không phụ thuộc bất kỳ SDK bên ngoài nào.
- `jackson-ready`: chỉ được đăng ký khi runtime có `com.fasterxml.jackson.databind.ObjectMapper`.

Ở ví dụ thực hành, nhánh `jackson-ready` **chỉ mô phỏng quyết định chọn strategy**; nó không triển khai JSON serialization bằng Jackson. Điều này giữ ví dụ độc lập với class tùy chọn trong chữ ký Java, để ta quan sát chính xác ảnh hưởng của việc thêm/bỏ một dependency vào classpath.

Các condition tương ứng:

```java
@ConditionalOnMissingClass("com.fasterxml.jackson.databind.ObjectMapper")
```

và:

```java
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
```

Với cùng một tên class, hai điều kiện này là **phần bù** trong điều kiện classloader được đánh giá nhất quán: thiếu thì chọn nhánh basic; có thì chọn nhánh jackson-ready. Đây là mô hình quan trọng để thiết kế fallback mà không phải viết mã `if/else` kiểm tra dependency trong mọi service.

### Bảng quyết định

| Có `ObjectMapper` ở runtime? | MissingClass | OnClass | Bean mong đợi |
| --- | --- | --- | --- |
| Không | Match | No match | `basic` |
| Có | No match | Match | `jackson-ready` |

Khi các nhánh cùng định nghĩa một type, điều kiện phải **loại trừ nhau một cách rõ ràng**. Nếu viết điều kiện không đối xứng, cả hai nhánh có thể cùng tạo bean và gây `NoUniqueBeanDefinitionException` hoặc trùng tên bean.

Trong auto-configuration sản phẩm thật, nên kết hợp thêm `@ConditionalOnMissingBean` nếu chủ đích là để ứng dụng tự thay thế implementation mặc định; riêng điều kiện classpath chỉ chọn theo môi trường có/không có class, **không quyết định ưu tiên bean do người dùng cung cấp**.

## 7. Ví dụ Java 17 + Spring Boot 3.3.13 chạy được

Ví dụ tạo một ứng dụng Maven non-web, đăng ký auto-configuration riêng bằng `.imports`. Chạy hai bản build của **cùng một source**:

1. Bản mặc định chỉ có `spring-boot-starter`, không đưa Jackson Databind vào dependency: chọn fallback `basic`.
2. Bản dùng Maven profile `with-jackson` thêm `jackson-databind`: chọn strategy `jackson-ready`.

**Lưu ý:** Tên strategy `jackson-ready` chứng minh **classpath condition**; nó chưa phải codec JSON thực sự. Khi tích hợp thực tế, class ở nhánh có Jackson có thể gọi `ObjectMapper`, nhưng phải tổ chức lớp để classloader không đụng type tùy chọn khi SDK vắng mặt.

### 7.1. Cấu trúc tệp

```text
missing-class-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── api/
    │   │   └── MessageFormatter.java
    │   ├── app/
    │   │   └── MissingClassDemoApplication.java
    │   └── autoconfigure/
    │       └── MessageAutoConfiguration.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

`demo.app` và `demo.autoconfigure` là hai package **anh em**, nên `@ComponentScan` mặc định của lớp main trong `demo.app` không tìm thấy `MessageAutoConfiguration`. Lớp này được nạp qua **cơ chế auto-configuration** đúng trách nhiệm.

### 7.2. pom.xml có profile tùy chọn

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

    <groupId>demo</groupId>
    <artifactId>missing-class-demo</artifactId>
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

    <profiles>
        <profile>
            <id>with-jackson</id>
            <dependencies>
                <dependency>
                    <groupId>com.fasterxml.jackson.core</groupId>
                    <artifactId>jackson-databind</artifactId>
                </dependency>
            </dependencies>
        </profile>
    </profiles>

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

Phiên bản của `jackson-databind` được Spring Boot starter parent/dependency management quản lý cho dự án Boot 3.3.13. Không nên thêm version ngẫu nhiên chỉ để thử điều kiện classpath.

**Phân biệt hai lần build:** Maven `clean` ở mỗi lần build sẽ xóa bản JAR trước, sau đó tạo JAR mới cùng tên. Muốn so sánh lại bản cũ, hãy chạy và ghi nhận output **trước khi build bản mới** hoặc chủ động lưu hai artifact ở đường dẫn riêng.

### 7.3. Interface không phụ thuộc Jackson

**`src/main/java/demo/api/MessageFormatter.java`:**

```java
package demo.api;

public interface MessageFormatter {
    String mode();
}
```

Interface thuộc code của dự án, không có bất kỳ import nào từ Jackson. Đây là điểm cốt lõi của fallback: service phụ thuộc abstraction ổn định, không phụ thuộc SDK có thể không tồn tại.

### 7.4. Auto-configuration với hai cấu hình lồng tĩnh

**`src/main/java/demo/autoconfigure/MessageAutoConfiguration.java`:**

```java
package demo.autoconfigure;

import demo.api.MessageFormatter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class MessageAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingClass(
        "com.fasterxml.jackson.databind.ObjectMapper"
    )
    static class BasicConfiguration {

        @Bean
        MessageFormatter selectedMessageFormatter() {
            return () -> "basic";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
        name = "com.fasterxml.jackson.databind.ObjectMapper"
    )
    static class JacksonAvailableConfiguration {

        @Bean
        MessageFormatter selectedMessageFormatter() {
            return () -> "jackson-ready";
        }
    }
}
```

Trong file trên:

- `@AutoConfiguration` đánh dấu lớp chính là auto-configuration ứng viên.
- `BasicConfiguration` được phép tham gia xử lý **khi không có** `ObjectMapper` ở classpath.
- `JacksonAvailableConfiguration` được phép tham gia xử lý **khi có** `ObjectMapper`.
- Cả hai cung cấp bean type `MessageFormatter`, với cùng bean name `selectedMessageFormatter`, nhưng chỉ một nhánh khớp trong hai cấu hình đối xứng.
- Các phương thức `@Bean` trả interface chung, không phụ thuộc Jackson; khi thiếu Jackson, JVM không bị ép resolve class SDK từ return type.
- `static class` giúp cấu hình lồng không yêu cầu một instance lớp bao làm enclosing instance.
- `proxyBeanMethods=false` phù hợp vì các phương thức `@Bean` này không tự gọi nhau.

Phần code không dùng `@ConditionalOnMissingBean` để bài học tập trung vào **điều kiện classpath**. Nếu người dùng cần thay thế bean mặc định, hãy mở rộng auto-configuration có điều kiện theo bean đúng chỗ và kiểm thử kỹ tình huống user bean xuất hiện.

### 7.5. Đăng ký ứng viên trong resource .imports

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:**

```text
demo.autoconfigure.MessageAutoConfiguration
```

Đường dẫn này phải chính xác. Nếu thiếu `.imports`, Boot 3.x không khám phá auto-configuration trong ví dụ theo đường metadata dành cho auto-configuration. Không được khắc phục bằng cách cho `MessageAutoConfiguration` vào một package rộng rồi quét nó như component ứng dụng.

### 7.6. Lớp main và ApplicationRunner

**`src/main/java/demo/app/MissingClassDemoApplication.java`:**

```java
package demo.app;

import demo.api.MessageFormatter;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class MissingClassDemoApplication {

    private static final String JACKSON_CLASS =
        "com.fasterxml.jackson.databind.ObjectMapper";

    public static void main(String[] args) {
        SpringApplication.run(MissingClassDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showSelection(MessageFormatter formatter) {
        return args -> {
            boolean present = ClassUtils.isPresent(
                JACKSON_CLASS, getClass().getClassLoader());

            System.out.println("JACKSON_PRESENT: " + present);
            System.out.println("SELECTED: " + formatter.mode());
        };
    }
}
```

`ClassUtils.isPresent(...)` được dùng ở đây **chỉ để in trạng thái classpath khi demo**. Cơ chế ra quyết định thực sự nằm ở annotation `@ConditionalOnMissingClass` và `@ConditionalOnClass` của `MessageAutoConfiguration`. Trong mã sản phẩm, không cần gọi `ClassUtils` ở mọi nơi để lặp lại chức năng của điều kiện.

`ApplicationRunner` nhận bean `MessageFormatter` do auto-configuration cung cấp. Nếu hai điều kiện đều không khớp hoặc classpath có vấn đề khác khiến không có bean nào, ứng dụng sẽ fail-fast do không thể inject dependency — đó cũng là tín hiệu tốt khi đang kiểm thử setup.

### 7.7. Chạy khi không có Jackson

Tại thư mục `missing-class-demo`, có **JDK 17+ và Maven**, chạy:

```bash
mvn -q -DskipTests clean package
java -jar target/missing-class-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Với các dependency khai báo trong profile mặc định của ví dụ, ngoài banner và log Spring Boot, hai dòng do `ApplicationRunner` in ra là:

```text
JACKSON_PRESENT: false
SELECTED: basic
```

**Lý do:** `spring-boot-starter` cơ bản không khai báo Jackson Databind. `com.fasterxml.jackson.databind.ObjectMapper` vắng mặt; `@ConditionalOnMissingClass` khớp, nhánh `BasicConfiguration` đăng ký bean `selectedMessageFormatter`. Nhánh `JacksonAvailableConfiguration` không khớp.

Nếu một môi trường tự chỉnh POM/đưa thêm dependency gián tiếp làm class Jackson xuất hiện, kết quả có thể khác. Khi đó không phải condition sai: hãy kiểm tra cây dependency thực tế.

### 7.8. Chạy khi có Jackson

Tiếp theo, build lại cùng source với Maven profile:

```bash
mvn -q -Pwith-jackson -DskipTests clean package
java -jar target/missing-class-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Hai dòng dự kiến:

```text
JACKSON_PRESENT: true
SELECTED: jackson-ready
```

Vì profile `with-jackson` thêm `jackson-databind`, runtime classpath bên trong executable JAR có `ObjectMapper`. Điều kiện **vắng mặt** không còn khớp, trong khi điều kiện **có mặt** khớp. Nhánh còn lại cung cấp một bean `MessageFormatter`.

`jackson-ready` chỉ là nhãn để quan sát việc chọn nhánh. Nó **không khẳng định** chương trình đã tạo bean `ObjectMapper` hay thực hiện JSON serialization. Một auto-configuration của Boot có thể tạo thêm `ObjectMapper` nếu các điều kiện tương ứng khớp, nhưng điều đó là câu chuyện về bean/infrastructure riêng.

### 7.9. So sánh hai lần build

| Đặc điểm | Bản không profile | Bản `-Pwith-jackson` |
| --- | --- | --- |
| Class `ObjectMapper` ở runtime | Không | Có |
| `@ConditionalOnMissingClass` | Match | No match |
| `@ConditionalOnClass` | No match | Match |
| `MessageFormatter` được inject | Basic strategy | Jackson-ready strategy |
| Dòng `SELECTED` | `basic` | `jackson-ready` |
| Có phải sửa Java source? | Không | Không |
| Có cần web server? | Không | Không |

Thí nghiệm cho thấy **cùng code cấu hình** có thể điều chỉnh hành vi dựa vào khả năng có mặt của thư viện ở runtime, thay vì dùng những câu lệnh `if` rải rác trong service.

## 8. Phương án thực tế khi một SDK hoàn toàn không có mặt

Trong ví dụ vừa rồi cả hai nhánh chỉ trả về một tên strategy. Với một tích hợp thật, nhánh SDK thường có implementation cần import class của SDK. Để tránh `NoClassDefFoundError`, tách lớp theo package và điều kiện rõ ràng:

```text
com.acme.integration.api
  └── ClientGateway.java                   (interface ổn định)

com.acme.integration.basic
  └── BasicClientGateway.java              (chỉ dùng JDK/Spring core)

com.acme.integration.sdk
  └── SdkClientGateway.java                (phụ thuộc SDK tùy chọn)

com.acme.integration.autoconfigure
  └── ClientAutoConfiguration.java
       ├── FallbackConfiguration          (@ConditionalOnMissingClass)
       └── SdkConfiguration               (@ConditionalOnClass)
```

Trong auto-configuration, không được dùng `SdkClientGateway` trong chữ ký của **nhánh dự phòng**. Nếu nhánh SDK cần class tùy chọn, tách nó ra cấu hình được bảo vệ bằng điều kiện cấp lớp trước khi những method signatures bị phân tích.

Cần xem xét dependency theo hai chiều:

1. **Compile:** module chứa `SdkClientGateway` phải có SDK ở compile classpath; có thể dùng dependency optional hoặc mô hình module riêng.
2. **Runtime:** starter/ứng dụng tiêu thụ có thể không bao gồm SDK. Những class phụ thuộc SDK không được nạp trong nhánh vắng mặt.
3. **Condition:** check đúng class đặc trưng của SDK, tránh check một class quá chung có thể được kéo vào từ thư viện khác.
4. **Contract:** mọi implementation phải trả chung interface mà ứng dụng có thể inject.

Đặt auto-configuration trong package **ngoài vùng component scan của ứng dụng** và khai báo ứng viên ở `.imports`. Tránh để `@ComponentScan` quét toàn bộ package thư viện, vì class phụ thuộc SDK có thể bị quét không chủ định.

## 9. Các tình huống khó cần hiểu chính xác

### 9.1. Class vắng mặt khác với class không nạp được do dependency phụ thiếu

Có thể `com.vendor.sdk.Client` tồn tại trong JAR nhưng khi tải lại thiếu một type nó phụ thuộc, hoặc lỗi classloader/module. Không nên gộp tất cả trường hợp lỗi class loading thành “SDK không được cài”. Condition classpath xem xét khả năng nhận diện class theo classloader nhưng quá trình chạy thật còn có thể gặp liên kết lớp (`LinkageError`), quyền truy cập module hoặc native library không đáp ứng.

Nếu nhánh SDK được chọn mà bean tạo thất bại, hãy đọc root cause thay vì tự thay bằng fallback sau khi đã xảy ra exception. Fallback theo `@ConditionalOnMissingClass` là **quyết định cấu hình lúc startup**, không phải cơ chế retry/mạch dự phòng runtime.

### 9.2. Có dependency Maven nhưng điều kiện vẫn báo missing

Kiểm tra:

- Scope của dependency (`test`, `provided`, `runtime`, `compile`) và cách đóng gói executable JAR.
- Dependency có bị exclusion hoặc profile/variant loại bỏ không.
- Thư viện có đổi tên package/class giữa các phiên bản không.
- Có đang chạy đúng JAR mới build không.
- App có dùng classloader tùy chỉnh hoặc module path khác không.

Maven `dependency:tree` có ích để tìm bản được resolve, nhưng nó không thay thế việc xem **classpath runtime** của đúng process. Với Spring Boot executable JAR, có thể xem thư viện bên trong archive bằng lệnh `jar tf`.

### 9.3. Có class nhưng chưa có bean

`@ConditionalOnMissingClass("com.vendor.sdk.Client")` sẽ **không khớp** nếu class đã tồn tại, kể cả khi không có bean `Client`. Nếu cần quy tắc theo sự hiện diện của bean, phải xem `@ConditionalOnBean`/`@ConditionalOnMissingBean`. Nếu cần một nhánh SDK có điều kiện chỉ hoạt động khi user bật tính năng, thêm property condition phù hợp.

### 9.4. Nhiều class trong điều kiện

Với:

```java
@ConditionalOnMissingClass({
    "com.vendor.sdk.Client",
    "com.vendor.sdk.ClientBuilder"
})
```

điều kiện chỉ khớp khi **tất cả tên class đã liệt kê đều không được tìm thấy**. Nếu ý định là fallback khi **thiếu ít nhất một** trong hai class, cách biểu diễn phải được thiết kế lại, vì danh sách trong một annotation không đồng nghĩa logic “OR của việc thiếu”.

Một giải pháp đơn giản cho một SDK chuẩn là chọn **một class đặc trưng** duy nhất đại diện cho khả năng tích hợp. Nếu tính năng cần nhiều class, hãy kiểm tra danh sách cần có bằng `@ConditionalOnClass(name = {...})` ở nhánh nâng cao, sau đó thiết kế nhánh fallback sao cho bao phủ chính xác miền còn lại. Đừng cho rằng hai annotation với danh sách class nhiều phần tử tự động là phần bù logic của nhau.

### 9.5. Điều kiện phối hợp với @ConditionalOnMissingBean

Một thư viện muốn người dùng có quyền cấu hình bằng bean riêng có thể bổ sung:

```java
@Bean
@ConditionalOnMissingBean(MessageFormatter.class)
MessageFormatter defaultFormatter() {
    return ...;
}
```

Đây là snippet minh họa. Điều kiện classpath trước hết quyết định nhánh nào đủ điều kiện; điều kiện bean giúp mặc định **back off** khi ứng dụng đã đăng ký bean tùy chỉnh phù hợp. `@ConditionalOnMissingBean` có sắc thái về type/name, context hierarchy và thời điểm đánh giá; nên dùng trong auto-configuration và kiểm thử trường hợp user-defined bean.

Không nhầm việc mặc định back off với **bean overriding** (ghi đè definition trùng tên) hoặc `@Primary` (ưu tiên khi inject nhiều bean). Chúng là các cơ chế khác nhau.

## 10. @ConditionalOnMissingClass và @ConditionalOnClass có luôn thay thế nhau?

Với **một class duy nhất**, chúng biểu diễn hai tình huống có/không có class khá trực quan:

```java
@ConditionalOnMissingClass("com.example.OptionalApi")
```

so với:

```java
@ConditionalOnClass(name = "com.example.OptionalApi")
```

Nhưng khi tổng hợp điều kiện, cần kiểm tra **toàn bộ biểu thức**.

Ví dụ:

```text
Nhánh nâng cao: có A VÀ có B
Nhánh dự phòng: không có A VÀ không có B
```

Hai nhánh trên **không bao phủ** hai trường hợp trung gian:

```text
có A, thiếu B
thiếu A, có B
```

Vì vậy đối với thư viện cần hai class để chạy, không nên dùng hai cấu hình như trên rồi mặc định rằng luôn tạo ra chính xác một bean. Có thể:

- Chọn một class marker phản ánh đúng “SDK sử dụng được” ở cấp cấu hình.
- Tách các điều kiện theo capability nhỏ hơn.
- Viết custom condition chỉ khi các annotation built-in không biểu diễn được yêu cầu một cách rõ ràng.
- Bổ sung test cho từng tổ hợp classpath thực tế.

**Nên thiết kế ma trận trường hợp trước khi viết điều kiện**; điều này giảm lỗi “một số class có nhưng không nhánh nào khớp”.

## 11. Khi nào dùng fallback runtime thay vì fallback lúc startup?

`@ConditionalOnMissingClass` phù hợp với quyết định **môi trường triển khai cố định**: ứng dụng có hay không có một thư viện lúc khởi động.

Nếu SDK có mặt nhưng dịch vụ bên ngoài đang lỗi mạng, class vẫn tồn tại; `@ConditionalOnMissingClass` **không chuyển sang fallback**. Muốn xử lý tính sẵn sàng runtime, cần cơ chế khác:

- Bắt lỗi nghiệp vụ có kiểm soát và trả về giá trị dự phòng phù hợp.
- Timeout, retry có giới hạn và circuit breaker khi cần.
- Health checks/observability để phát hiện dependency không đáp ứng.
- Feature flag/property để chủ động chuyển cấu hình ở lần khởi động tiếp theo, nếu kiến trúc cho phép.

Không dùng condition classpath để thay thế resilience. Một nhánh được chọn khi khởi động không có nghĩa nó sẽ thay đổi tự động sau khi ứng dụng đang chạy.

## 12. Chẩn đoán bằng Conditions Evaluation Report

Spring Boot có thể in báo cáo condition khi chạy với `--debug`:

```bash
java -jar target/missing-class-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none --debug
```

Tìm các mục như `BasicConfiguration` và `JacksonAvailableConfiguration`. Tùy version/logging, báo cáo cho biết điều kiện classpath match hay không match và class nào được xét.

Các nhóm thông tin:

- **Positive matches**: điều kiện phù hợp.
- **Negative matches**: điều kiện không phù hợp; thường kèm lý do.
- **Exclusions**: auto-configuration bị loại trừ tường minh.

Báo cáo điều kiện trả lời **vì sao một configuration/bean definition được chọn hoặc bỏ qua**, không phải báo cáo chính xác mọi instance được tạo thành công. Nếu context lỗi sau đó, cần đọc exception và chuỗi `Caused by`.

Để chắc chắn runtime classpath có Jackson, xem output demo hoặc kiểm tra JAR:

```bash
jar tf target/missing-class-demo-0.0.1-SNAPSHOT.jar
```

Trong fat JAR, các dependency thường ở `BOOT-INF/lib/`. Nếu cần tìm cụ thể, dùng công cụ tìm chuỗi theo hệ điều hành; không nhất thiết phụ thuộc Bash khi chạy trên Windows.

### Quy trình debug nhanh

1. Kiểm tra đúng class name string: `com.fasterxml.jackson.databind.ObjectMapper` có viết chính xác không?
2. Kiểm tra JAR đang chạy chứa dependency mong muốn.
3. Kiểm tra annotation được đặt **ở lớp cấu hình** phù hợp, đặc biệt nếu phương thức trả về class tùy chọn.
4. Kiểm tra auto-configuration đã được nạp qua `.imports` và không bị exclude.
5. Bật `--debug`, tìm kết quả OnClassCondition.
6. Kiểm tra `@ConditionalOnMissingBean`/property khác nếu nhánh phù hợp nhưng bean chưa được đăng ký.
7. Nếu bean đã có definition mà tạo lỗi, đọc root cause; không coi đó là `MissingClass` không match.

## 13. Các lỗi phổ biến và cách sửa

### Lỗi 1: Dùng @ConditionalOnMissingClass(name = "...")

`@ConditionalOnMissingClass` không có `name`. Dùng:

```java
@ConditionalOnMissingClass("com.vendor.sdk.Client")
```

### Lỗi 2: Dùng Class literal cho class vốn không có trong dependency

Không dùng:

```java
// SAI: annotation yêu cầu chuỗi, không nhận Client.class.
@ConditionalOnMissingClass(com.vendor.sdk.Client.class)
```

Ngoài sai type, code còn không thể compile nếu SDK không nằm trong compile classpath. Dùng chuỗi tên class đầy đủ để biểu diễn dependency có thể thiếu.

### Lỗi 3: Đặt annotation chỉ ở @Bean method có return type thuộc SDK tùy chọn

Nếu JVM resolve method signature trước condition, ứng dụng có thể ném lỗi class loading. Tách một nested `@Configuration` tĩnh có class-level condition và giữ fallback không tham chiếu class SDK.

### Lỗi 4: Dùng MissingClass khi chỉ thiếu bean do ứng dụng chưa cấu hình

Nếu JAR có mặt, MissingClass không khớp bất kể bean đã được tạo hay chưa. Dùng BeanCondition đúng trường hợp.

### Lỗi 5: Có tên SDK trên Maven nhưng class runtime đổi package

Condition xét **tên class cụ thể** trong runtime classloader. Nếu vendor chuyển `com.old.Client` sang `com.new.Client`, kiểm tra tên cũ có thể báo thiếu dù SDK mới vẫn hiện diện. Đọc tài liệu API của đúng phiên bản SDK.

### Lỗi 6: Quét tự động mọi package của thư viện

Một class phụ thuộc SDK có thể bị scanner xử lý ngoài cấu hình dự kiến. Auto-configuration cần nằm ngoài vùng component scan của ứng dụng, được khai báo bằng `.imports`, và dùng `@Import` có chủ đích cho cấu hình phụ.

### Lỗi 7: Không xử lý trường hợp bean tự viết của người dùng

Điều kiện classpath không tự nhường quyền cho bean khác cùng type. Thêm `@ConditionalOnMissingBean` nếu cấu hình mặc định cần back off, và kiểm thử các bean tùy chỉnh.

### Lỗi 8: Tự gọi Class.forName trong constructor để quyết định fallback

Nếu constructor của bean đã được gọi, quá trình lựa chọn definition đã diễn ra. Hãy để auto-configuration chọn nhánh trước; dùng reflection chỉ khi một module thật sự cần adapter runtime động và có contract kiểm soát rõ ràng.

### Lỗi 9: Khẳng định class absent nghĩa là dependency luôn absent

Classpath có thể được lắp từ JAR phụ thuộc gián tiếp, plugin hoặc lớp do classloader đặc biệt cung cấp. Kiểm tra class thực tế, không chỉ quan sát một dòng `dependency` trong POM.

### Lỗi 10: Coi condition là giải pháp cho lỗi mạng khi SDK vẫn có mặt

MissingClass chỉ dựa vào classpath. Circuit breaker, retry và timeout là các giải pháp riêng cho lỗi runtime.

## 14. Checklist cho người viết auto-configuration

Trước khi phát hành một starter có fallback theo classpath, hãy kiểm tra:

1. **Abstraction ổn định:** các service ứng dụng inject interface/core API không phụ thuộc SDK.
2. **Classpath marker chuẩn:** class được dùng để kiểm tra tồn tại/vắng mặt thực sự phản ánh capability mong muốn.
3. **Điều kiện đầy đủ:** nhánh chính và nhánh fallback loại trừ nhau, bao phủ đúng những tổ hợp classpath cần hỗ trợ.
4. **Cô lập class loading:** các phương thức `@Bean` có chữ ký SDK nằm trong cấu hình lớp đã được bảo vệ bằng condition; nhánh fallback không import SDK.
5. **Bean override/back-off:** thêm condition theo bean khi người dùng cần cung cấp implementation riêng.
6. **Registration:** tên auto-configuration nằm trong `AutoConfiguration.imports`; không quét tùy ý package thư viện.
7. **Build matrix:** kiểm thử khi SDK vắng mặt, có mặt và có phiên bản không tương thích.
8. **Diagnostics:** kiểm tra Conditions Evaluation Report, root cause và cây dependency.
9. **Lifecycle:** phân biệt bean definition không được đăng ký với bean definition đã có nhưng tạo lỗi.
10. **Test:** với module riêng, có thể dùng `ApplicationContextRunner` và các classloader lọc (`FilteredClassLoader`) của thư viện test để giả lập class vắng mặt mà không phải build tay nhiều JAR.

`ApplicationContextRunner` và `FilteredClassLoader` là công cụ kiểm thử Spring Boot, không được nhập vào các file production của ví dụ. Chúng phù hợp để tự động kiểm tra cả hai nhánh condition trong CI.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `@ConditionalOnMissingClass` kiểm tra bean hay class?

**Đáp án:** Kiểm tra sự **vắng mặt của các class có tên được chỉ định** trong classpath/classloader hiệu lực khi condition được xét. Không kiểm tra bean instance.

**Câu 2.** Thuộc tính `name` có tồn tại trên `@ConditionalOnMissingClass` không?

**Đáp án:** Không. Spring Boot 3.3.x dùng thuộc tính `value` kiểu `String[]`; có thể viết `@ConditionalOnMissingClass("fully.qualified.ClassName")`.

**Câu 3.** Nếu thiếu Jackson Databind, ví dụ Maven chọn nhánh nào?

**Đáp án:** `BasicConfiguration`, vì class `com.fasterxml.jackson.databind.ObjectMapper` không có và condition `@ConditionalOnMissingClass` khớp.

**Câu 4.** Vì sao `MessageFormatter` là interface thuộc API cốt lõi thay vì trực tiếp dùng ObjectMapper trong return type của fallback?

**Đáp án:** Nhánh fallback phải compile và chạy khi thư viện tùy chọn vắng mặt; dùng abstraction không phụ thuộc SDK giúp tránh classloading không cần thiết và giữ DI ổn định.

**Câu 5.** Khi class `ObjectMapper` có mặt nhưng chưa có bean `ObjectMapper`, MissingClass có khớp không?

**Đáp án:** Không. Condition dựa vào classpath; bean presence là điều kiện khác.

**Câu 6.** Nếu hai class A và B trong danh sách `@ConditionalOnMissingClass`, có phải chỉ cần một class thiếu là condition match không?

**Đáp án:** Không. Với nhiều tên trong annotation này, điều kiện mong đợi các class đã liệt kê đều vắng mặt.

**Câu 7.** Vì sao đặt class-level condition trên nested configuration an toàn hơn đặt ở method có return type SDK?

**Đáp án:** Spring có thể bỏ qua cả lớp cấu hình tùy chọn trước khi JVM cần xử lý chữ ký method dùng class SDK, giảm rủi ro `NoClassDefFoundError`.

**Câu 8.** Một SDK có mặt nhưng gọi server bị timeout thì có kích hoạt MissingClass fallback không?

**Đáp án:** Không. Đây là lỗi runtime; dùng resilience/timeout/circuit breaker theo yêu cầu hệ thống.

**Câu 9.** Tên class trong `.imports` có phải tên của SDK để MissingClass kiểm tra không?

**Đáp án:** Không. `.imports` liệt kê **lớp auto-configuration của module**; annotation `MissingClass` chứa **tên class tùy chọn cần kiểm tra**.

**Câu 10.** Condition khớp có chắc bean sẵn sàng không?

**Đáp án:** Không. Các điều kiện khác có thể loại bean, hoặc bean có definition nhưng tạo lỗi hay bị lazy-initialized.

## 16. Tài liệu tham khảo

- Spring Boot 3.3.13, `ConditionalOnMissingClass` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingClass.html
- Spring Boot 3.3.13, `ConditionalOnClass` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3, Developing Auto-configuration / Class Conditions: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3, Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Framework, Classpath Scanning: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
