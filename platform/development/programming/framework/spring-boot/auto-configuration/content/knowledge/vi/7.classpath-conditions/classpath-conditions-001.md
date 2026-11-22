# @ConditionalOnClass: kiểm tra sự hiện diện của các kiểu bắt buộc

## 1. Vì sao auto-configuration cần kiểm tra classpath?

Một ứng dụng Spring Boot có thể thêm nhiều starter nhưng không nhất thiết bật mọi tích hợp. Ví dụ, thư viện cấu hình tự động cho JSON cần biết API Jackson có trên classpath hay không; thư viện cấu hình cho JDBC cần biết các lớp JDBC tương ứng có xuất hiện không. Nếu auto-configuration cố tạo bean phụ thuộc một thư viện **không được cài**, ứng dụng có thể gặp lỗi class loading hoặc bean creation ngay khi khởi động.

**@ConditionalOnClass** là điều kiện do Spring Boot cung cấp để kiểm tra **sự hiện diện của các kiểu Java yêu cầu** trước khi cho phép xử lý một lớp cấu hình hoặc phương thức tạo bean.

Ví dụ:

~~~java
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
~~~

Đoạn annotation này có nghĩa: thành phần mang annotation chỉ được xem là phù hợp khi Spring có thể tìm thấy class **com.fasterxml.jackson.databind.ObjectMapper** trên classpath mà framework sử dụng.

Nó không có nghĩa rằng đã có một **ObjectMapper bean**, không hứa class có thể hoạt động với mọi phiên bản thư viện, và không tự thêm Jackson vào dependency graph.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc đúng **@ConditionalOnClass(value = ...)** và **@ConditionalOnClass(name = ...)**.
2. Giải thích vì sao nhiều kiểu bắt buộc trong cùng annotation phải **đồng thời hiện diện**.
3. Phân biệt **class present**, **bean present**, **dependency declared**, **dependency resolved** và **API tương thích**.
4. Hiểu khác biệt khi đặt điều kiện ở **lớp @AutoConfiguration** và **phương thức @Bean**.
5. Tách phần tham chiếu API tùy chọn sang nested **@Configuration** để tránh introspection type quá sớm.
6. Dùng **ApplicationContextRunner** và **FilteredClassLoader** kiểm thử khi class hiện diện/vắng mặt.
7. Xác minh **AutoConfiguration.imports**, JAR và **runtimeClasspath** trong ứng dụng tiêu thụ.
8. Chẩn đoán nguyên nhân condition không match mà không nhầm với lỗi tạo bean.

Ví dụ thực hành sử dụng **Java 21, Gradle 8.x và Spring Boot 3.3.13** như bộ phiên bản cố định phục vụ bài học, **không phải** khẳng định đây là các bản mới nhất.

## 2. Khái niệm: kiểm tra kiểu Java có thể tìm thấy

**Classpath** là tập đường dẫn tới class, JAR và các tài nguyên mà JVM/classloader có thể truy cập. Tùy cấu hình build, test và runtime có thể có các classpath khác nhau.

Với:

~~~java
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
~~~

Spring Boot đặt câu hỏi đại ý: **“ClassLoader phù hợp của context có thể tìm thấy class được yêu cầu hay không?”**.

| Tình huống | Điều kiện classpath | Kết luận đúng |
| --- | --- | --- |
| JAR optional-api có class **OptionalCodec** trong runtimeClasspath | Thường match | Có thể tiếp tục xử lý cấu hình được bảo vệ. |
| Chỉ khai báo optional-api ở **testImplementation**, ứng dụng production không có JAR | Không match ở production | Không nên tạo bean cần OptionalCodec. |
| Source code dự án khác có OptionalCodec nhưng không nằm trên classpath ứng dụng | Không match | Source tồn tại không có nghĩa runtime nhìn thấy class. |
| Class có trên classpath nhưng chưa đăng ký bean | Vẫn có thể match | Điều kiện class khác điều kiện bean. |
| Class cùng tên tồn tại nhưng API thay đổi không tương thích | Có thể match | Điều kiện chỉ kiểm tra hiện diện, không bảo đảm các method/constructor cần dùng tương thích. |

### 2.1. Một class có mặt không đồng nghĩa một bean có mặt

Hai đoạn sau hỏi **hai câu khác nhau**:

~~~java
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
~~~

~~~java
@ConditionalOnBean(OptionalCodec.class)
~~~

Đoạn thứ hai chỉ là một ví dụ annotation **cần class OptionalCodec ở compile classpath** và có ý nghĩa khác: bean **OptionalCodec** đã tồn tại trong Spring context theo semantics của condition hay chưa. Nếu mục tiêu là cho phép thư viện hoạt động khi **JAR** được cài, **@ConditionalOnClass** là công cụ phù hợp. Nếu muốn cấu hình phụ thuộc một **bean đã đăng ký**, hãy dùng condition về bean và cân nhắc thứ tự xử lý cấu hình.

**Không viết @ConditionalOnBean thay cho @ConditionalOnClass** chỉ vì tên giống nhau. Có class không có nghĩa có bean; có bean phù hợp cũng phụ thuộc tiến trình đăng ký bean definitions.

### 2.2. Classpath nào được kiểm tra?

Khi chạy **gradle test**, dependency từ **testImplementation** có thể xuất hiện và làm classpath condition match. Khi chạy **gradle bootRun**, runtimeClasspath của ứng dụng có thể thiếu dependency đó, nên condition không match.

Đừng kết luận chỉ từ việc IDE có thể import một type. Cần kiểm tra **runtimeClasspath thật**, đặc biệt khi dùng **compileOnly**, **runtimeOnly**, multi-module hoặc dependency bắc cầu.

## 3. Cú pháp chính xác của @ConditionalOnClass

Spring Boot cung cấp annotation:

~~~text
org.springframework.boot.autoconfigure.condition.ConditionalOnClass
~~~

Hai thuộc tính cốt lõi:

- **value**: mảng các **Class<?>** bắt buộc có mặt.
- **name**: mảng các **tên class đầy đủ** (**FQCN**) dạng String bắt buộc có mặt.

Các cách dùng thông thường:

~~~java
@ConditionalOnClass(ObjectMapper.class)
~~~

~~~java
@ConditionalOnClass(value = {ObjectMapper.class, JsonNode.class})
~~~

~~~java
@ConditionalOnClass(
    name = "com.fasterxml.jackson.databind.ObjectMapper"
)
~~~

~~~java
@ConditionalOnClass(
    name = {
        "com.fasterxml.jackson.databind.ObjectMapper",
        "com.fasterxml.jackson.databind.JsonNode"
    }
)
~~~

Đây là các **đoạn annotation minh họa**, không phải các file Java chạy độc lập. Các ví dụ dùng class literal **ObjectMapper** và **JsonNode** yêu cầu module biên dịch nhìn thấy các class tương ứng; dạng **name** không cần import chúng để viết annotation.

### 3.1. value là class literal, không phải tên file .class

Với code:

~~~java
@ConditionalOnClass(com.fasterxml.jackson.databind.ObjectMapper.class)
~~~

**.class** ở đây là cú pháp Java cho **class literal**. Nó khác một dòng trong tệp **AutoConfiguration.imports**, nơi cần viết **FQCN** không có **.class**.

Ở annotation, cú pháp **@ConditionalOnClass(ObjectMapper.class)** được dùng phổ biến nếu có import:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
~~~

### 3.2. name là FQCN chính xác

Ví dụ:

~~~java
@ConditionalOnClass(
    name = "com.fasterxml.jackson.databind.ObjectMapper"
)
~~~

Không dùng **ObjectMapper**, **com.fasterxml.jackson.databind.\***, **ObjectMapper.class** dạng chuỗi hoặc tên artifact Maven như **com.fasterxml.jackson.core:jackson-databind**. Những giá trị này không phải tên class đầy đủ để framework tìm kiếm.

**name** thuận tiện khi thư viện tùy chọn **không có trên compile classpath**, hoặc khi tạo composed annotation cần tránh class literal.

### 3.3. Mặc định nhiều class là AND

Giả sử:

~~~java
@ConditionalOnClass(
    name = {
        "com.example.api.Alpha",
        "com.example.api.Beta"
    }
)
~~~

Điều kiện chỉ match khi **cả Alpha và Beta** đều có mặt. Nếu một class thiếu, kết quả không match.

| Alpha | Beta | @ConditionalOnClass match? |
| --- | --- | --- |
| Có | Có | **Có** |
| Có | Không | Không |
| Không | Có | Không |
| Không | Không | Không |

Đây là phép **AND**, không phải phép OR. Tương tự, nếu đồng thời khai báo yêu cầu ở cả **value** và **name**, những yêu cầu được khai báo đều phải thỏa mãn.

### 3.4. Muốn “A hoặc B” thì sao?

Không thể viết hai giá trị trong cùng **@ConditionalOnClass** rồi kỳ vọng “chỉ cần một”. Khi tích hợp có hai backend thay thế cho nhau, bạn có thể **tách thành hai cấu hình được bảo vệ riêng**, hoặc viết một condition tổng hợp có logic OR khi thật sự cần.

Đừng đổi phép AND thành OR bằng cách thay **@ConditionalOnClass** thành nhiều dòng comment, hoặc khai báo property “or” tưởng tượng. Logic điều kiện phải được biểu diễn rõ ràng.

## 4. Điều kiện cấp class và cấp phương thức @Bean

**@ConditionalOnClass** có thể bảo vệ một auto-configuration class:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
public class OptionalCodecAutoConfiguration {
    // Các @Bean chỉ được xét khi lớp cấu hình phù hợp.
}
~~~

Khi class **OptionalCodec** không tồn tại, **OptionalCodecAutoConfiguration** không được dùng để đăng ký những bean của nó.

Với điều kiện trên một bean method:

~~~java
@Bean
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
public String optionalFeatureLabel() {
    return "optional";
}
~~~

Trong trường hợp method chỉ trả về **String**, không có reference kiểu tùy chọn trong chữ ký. Đặt condition trên method có thể phù hợp khi chỉ muốn chặn **một bean** chứ không chặn toàn bộ class.

### 4.1. Một rủi ro quan trọng khi @Bean trả về type tùy chọn

Cách viết **có rủi ro**:

~~~java
@Bean
@ConditionalOnClass(OptionalCodec.class)
OptionalCodec optionalCodec() {
    return new OptionalCodec();
}
~~~

Đây là đoạn code minh họa cần tránh trong class cấu hình được xử lý ngay cả khi OptionalCodec vắng mặt. **Return type của method** đã tham chiếu OptionalCodec. Spring/JVM có thể cần introspect signature **trước khi điều kiện method được áp dụng đúng cách**, khiến class không tồn tại gây lỗi.

Tài liệu Spring Boot khuyên **cô lập method ấy trong configuration class riêng**, thường là static nested class, và đặt **@ConditionalOnClass ở cấp lớp**.

### 4.2. Mẫu nested @Configuration an toàn hơn

~~~java
@AutoConfiguration
public class ExampleAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
    static class OptionalCodecConfiguration {

        @Bean
        OptionalCodec optionalCodec() {
            return new OptionalCodec();
        }
    }
}
~~~

Đây là **đoạn mẫu**, chưa gồm package/import và bean override. Nested class giữ chữ ký method phụ thuộc OptionalCodec bên trong class chỉ cần xử lý khi điều kiện cấp class đạt.

**static** bảo đảm nested class không cần một instance của class ngoài. **proxyBeanMethods=false** phù hợp nếu method @Bean không cần gọi chéo để lấy bean thông qua proxy.

Đặt **@ConditionalOnClass** lên nested configuration cho phép Spring sử dụng metadata annotation để loại nhánh không hợp lệ trước khi xử lý sâu method signature. Đây là pattern quan trọng trong các thư viện auto-configuration phục vụ dependency tùy chọn.

## 5. Vì sao @ConditionalOnClass có thể kiểm tra mà không cần tải class quá sớm?

Tài liệu Spring Boot mô tả rằng annotation metadata của class cấu hình có thể được xử lý bằng **ASM**, vì vậy **@ConditionalOnClass** đặt trực tiếp trên class có thể được kiểm tra mà không cần tải class được đánh dấu theo cách khiến mọi kiểu của các bean methods phải được phân giải trước.

Lợi ích:

- Không ép runtime phải có **toàn bộ tích hợp optional** chỉ để xem một điều kiện.
- Bảo vệ từng nhánh cấu hình trong library.
- Giúp framework loại các candidate không phù hợp và giảm xử lý cấu hình không cần thiết.
- Cho phép những tính năng cốt lõi tiếp tục hoạt động khi dependency optional vắng mặt.

Tuy nhiên:

- **@ConditionalOnClass** không tự sửa một outer configuration có static initializer, field, superclass hoặc signature khác tham chiếu class optional.
- Một class có mặt có thể vẫn gặp **NoSuchMethodError/NoClassDefFoundError** khi chạy nếu API binary không tương thích hoặc thiếu một dependency bắc cầu cần thiết.
- Phần xử lý metadata và class loading thuộc framework/JVM; không suy đoán “class nào tuyệt đối chưa từng được load” chỉ từ log thông thường.

### 5.1. Composed annotation nên dùng name

Khi **@ConditionalOnClass** được dùng làm meta-annotation trong một annotation tổng hợp do tác giả thư viện tạo, tài liệu Spring Boot lưu ý nên sử dụng **name** thay cho class literal. Ví dụ:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
public @interface ConditionalOnOptionalCodec {
}
~~~

Đây là **đoạn annotation Java minh họa**, cần import **java.lang.annotation.Target**, **ElementType**, **Retention**, **RetentionPolicy** và loại **ConditionalOnClass**. Với một annotation hoàn chỉnh, có thể thêm **@Documented** khi muốn annotation xuất hiện trong JavaDoc.

Đừng hiểu nhầm rằng **name** làm “mạnh hơn” về điều kiện. Về ý nghĩa class hiện diện, value/name cùng biểu diễn yêu cầu tồn tại. Sự khác biệt là cách cung cấp tên và khả năng xử lý metadata/class literal.

## 6. Ví dụ thực hành: class có mặt hoặc vắng mặt một cách thật sự

Ta tạo ba module:

~~~text
classpath-condition-lab/
├── settings.gradle
├── build.gradle
├── optional-api/
│   ├── build.gradle
│   └── src/main/java/com/example/optionalapi/OptionalCodec.java
├── optional-autoconfigure/
│   ├── build.gradle
│   ├── src/main/java/com/example/autoconfigure/
│   │   ├── BaseMarker.java
│   │   └── CodecAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/autoconfigure/
│       └── CodecAutoConfigurationTests.java
└── demo-app/
    ├── build.gradle
    └── src/main/java/com/example/demo/
        └── DemoApplication.java
~~~

Trong thiết kế này:

1. **optional-api** có class **OptionalCodec** nhưng không phụ thuộc Spring.
2. **optional-autoconfigure** định nghĩa một bean nền tảng **BaseMarker**, và **một nhánh cấu hình lồng nhau** chỉ tạo OptionalCodec nếu optional-api hiện diện.
3. **demo-app** chỉ phụ thuộc auto-configuration và Spring Boot starter lúc đầu; sau đó chủ động thêm optional-api ở runtime để nhìn thấy kết quả khác.

Điểm mấu chốt là dependency vào optional-api phải **compileOnly** ở module autoconfigure. Nếu dùng **implementation**, người tiêu thụ sẽ thường nhận optional-api transitively và thí nghiệm vắng class sẽ không còn giá trị.

### 6.1. Tệp settings.gradle

~~~groovy
rootProject.name = 'classpath-condition-lab'
include 'optional-api', 'optional-autoconfigure', 'demo-app'
~~~

### 6.2. Tệp build.gradle ở root

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'io.spring.dependency-management'

    group = 'com.example'
    version = '1.0.0'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    repositories {
        mavenCentral()
    }

    dependencyManagement {
        imports {
            mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.13'
        }
    }

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
~~~

Root thống nhất toolchain và version cho cả ba module. Plugin Spring Boot được khai báo **apply false** ở root và sẽ áp dụng ở demo-app. Hai module library dùng Java JAR bình thường.

### 6.3. optional-api/build.gradle

~~~groovy
plugins {
    id 'java-library'
}
~~~

### 6.4. optional-autoconfigure/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    compileOnly project(':optional-api')

    testImplementation project(':optional-api')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**compileOnly** cho phép viết **OptionalCodec.class**, gọi constructor và biên dịch method signature nhưng **không đưa dependency này vào runtime** của project khác chỉ vì đã thêm module auto-configuration.

**testImplementation** giúp class OptionalCodec xuất hiện trong test classpath bình thường; các test vắng class dùng **FilteredClassLoader** để mô phỏng trường hợp optional dependency không được nhìn thấy.

### 6.5. demo-app/build.gradle

~~~groovy
plugins {
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':optional-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Chưa có dependency **optional-api** trong runtimeClasspath của ứng dụng.

## 7. Các class Java đầy đủ

### 7.1. API tùy chọn: OptionalCodec.java

Tệp **optional-api/src/main/java/com/example/optionalapi/OptionalCodec.java**:

~~~java
package com.example.optionalapi;

public final class OptionalCodec {

    public String encode(String text) {
        return "encoded:" + text;
    }
}
~~~

Class này không có Spring annotation; nó là kiểu của thư viện bên ngoài mà auto-configuration sẽ kiểm tra.

### 7.2. Type nền tảng: BaseMarker.java

Tệp **optional-autoconfigure/src/main/java/com/example/autoconfigure/BaseMarker.java**:

~~~java
package com.example.autoconfigure;

public record BaseMarker(String value) {
}
~~~

BaseMarker không tham chiếu OptionalCodec, nên có thể được tạo dù optional-api vắng mặt.

### 7.3. Auto-configuration có nested condition: CodecAutoConfiguration.java

Tệp **optional-autoconfigure/src/main/java/com/example/autoconfigure/CodecAutoConfiguration.java**:

~~~java
package com.example.autoconfigure;

import com.example.optionalapi.OptionalCodec;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class CodecAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(BaseMarker.class)
    public BaseMarker baseMarker() {
        return new BaseMarker("core");
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(OptionalCodec.class)
    static class OptionalCodecConfiguration {

        @Bean
        @ConditionalOnMissingBean(OptionalCodec.class)
        OptionalCodec optionalCodec() {
            return new OptionalCodec();
        }
    }
}
~~~

**Phân tích:**

- **@AutoConfiguration**: lớp ngoài là ứng viên được Spring Boot khám phá.
- **@Bean BaseMarker**: cung cấp bean core khi ứng dụng chưa khai báo.
- **@Configuration(proxyBeanMethods=false)**: lớp lồng nhau là cấu hình riêng với bean method cần thiết.
- **@ConditionalOnClass(OptionalCodec.class)**: chỉ cho nhánh nested hoạt động khi runtime tìm thấy OptionalCodec.
- **@ConditionalOnMissingBean(OptionalCodec.class)**: ứng dụng được ưu tiên nếu đã đăng ký một bean OptionalCodec riêng.

**Tại sao không đặt OptionalCodec ở method signature của class ngoài?** Vì class ngoài phải hoạt động cả khi optional-api không có. Nested configuration là ranh giới tránh introspection những method phụ thuộc type tùy chọn trong trường hợp không có JAR.

### 7.4. Đăng ký ứng viên qua AutoConfiguration.imports

Tệp **optional-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**:

~~~text
com.example.autoconfigure.CodecAutoConfiguration
~~~

Chỉ liệt kê lớp auto-configuration **bên ngoài**, không thêm **CodecAutoConfiguration$OptionalCodecConfiguration** vào file imports. Spring xử lý nested configuration theo cơ chế của configuration classes.

Đặt tệp chính xác trong **src/main/resources**. Nếu vô tình đặt trong **src/test/resources**, test có thể nhìn thấy nhưng consumer chạy từ JAR chính không tự phát hiện.

## 8. Kiểm thử @ConditionalOnClass bằng ApplicationContextRunner

Dùng **ApplicationContextRunner** tạo context nhỏ để kiểm tra:

1. Class OptionalCodec hiện diện → có bean core và optional mặc định.
2. Class OptionalCodec bị che → chỉ có bean core, context khởi động bình thường.
3. Class OptionalCodec có mặt nhưng ứng dụng định nghĩa bean riêng → auto-configuration **back off**.
4. Một class yêu cầu khác bị che trong điều kiện nhiều class → nhánh được bảo vệ không match.

Trong bài học, ba test đầu kiểm chứng toàn bộ project. Test thứ tư được giải thích bằng một class bổ sung để không trộn quá nhiều cấu hình vào demo.

### 8.1. Tệp CodecAutoConfigurationTests.java

Tệp **optional-autoconfigure/src/test/java/com/example/autoconfigure/CodecAutoConfigurationTests.java**:

~~~java
package com.example.autoconfigure;

import com.example.optionalapi.OptionalCodec;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CodecAutoConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(CodecAutoConfiguration.class)
            );

    @Test
    void createsOptionalBeanWhenClassPresent() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(BaseMarker.class);
            assertThat(context).hasSingleBean(OptionalCodec.class);
            assertThat(context.getBean(OptionalCodec.class).encode("An"))
                .isEqualTo("encoded:An");
        });
    }

    @Test
    void skipsOptionalBeanWhenClassAbsent() {
        runner.withClassLoader(
            new FilteredClassLoader("com.example.optionalapi")
        ).run(context -> {
            assertThat(context).hasSingleBean(BaseMarker.class);
            assertThat(context.containsBean("optionalCodec")).isFalse();
            assertThat(context.getBean(BaseMarker.class).value())
                .isEqualTo("core");
        });
    }

    @Test
    void backsOffWhenApplicationSuppliesBean() {
        runner.withUserConfiguration(UserCodecConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(OptionalCodec.class);
                assertThat(context.containsBean("optionalCodec")).isFalse();
                assertThat(context.containsBean("customCodec")).isTrue();
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCodecConfiguration {

        @Bean
        OptionalCodec customCodec() {
            return new OptionalCodec();
        }
    }
}
~~~

**Điểm cần hiểu về test thiếu dependency:** Trong nhánh **FilteredClassLoader**, test không gọi **getBean(OptionalCodec.class)** vì điều đó trực tiếp tham chiếu type đang được giả lập là thiếu. Thay vào đó, test kiểm tra bằng **tên bean**. Spring có thể đọc metadata class lồng nhau rồi bỏ qua nó mà không cố tạo bean OptionalCodec.

**Điểm cần hiểu về test back off:** Condition classpath đã match, nhưng **@ConditionalOnMissingBean** thấy bean **customCodec**. Vì thế **chỉ một bean** tồn tại. Điều này không phủ nhận kết quả **@ConditionalOnClass**; nó chỉ minh họa thêm một condition bắt buộc khác.

### 8.2. Chạy test với Gradle

~~~bash
gradle :optional-autoconfigure:test
~~~

Hoặc với Gradle Wrapper, nếu đã tạo:

~~~bash
./gradlew :optional-autoconfigure:test
~~~

Trên Windows PowerShell: **.\gradlew.bat :optional-autoconfigure:test**.

Khi test pass, Gradle báo task thành công; console logging phụ thuộc cấu hình máy. Không có stdout duy nhất cố định cần học thuộc.

### 8.3. Test trực tiếp không thay thế kiểm tra discovery

**AutoConfigurations.of(CodecAutoConfiguration.class)** đưa class vào context runner trực tiếp. Điều này kiểm tra **logic điều kiện**, nhưng **chưa chứng minh** class được tự động tìm thấy qua resource **AutoConfiguration.imports** trong JAR đã phát hành.

Một project hoàn chỉnh cần thêm consumer application và kiểm tra artifact, như hai phần sau.

## 9. Chạy ứng dụng tiêu thụ trong hai trạng thái classpath

Tệp **demo-app/src/main/java/com/example/demo/DemoApplication.java**:

~~~java
package com.example.demo;

import com.example.autoconfigure.BaseMarker;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(ApplicationContext context) {
        return args -> {
            System.out.println(
                "BaseMarker present: " +
                !context.getBeansOfType(BaseMarker.class).isEmpty()
            );
            System.out.println(
                "OptionalCodec bean present: " +
                context.containsBean("optionalCodec")
            );
        };
    }
}
~~~

Ứng dụng ở package **com.example.demo**, tách khỏi package cấu hình **com.example.autoconfigure**. Component scan mặc định của **@SpringBootApplication** không quét thư viện theo package này. Vì thế class **CodecAutoConfiguration** chỉ được áp dụng nhờ cơ chế auto-configuration discovery qua imports.

### 9.1. Khi optional-api vắng mặt

Giữ **demo-app/build.gradle** như phần 6.5, chạy:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
gradle :demo-app:bootRun
~~~

Kiểm tra dependency tree cho thấy **optional-api** không phải dependency runtime được chọn của demo-app. Hai dòng do ApplicationRunner in ra dự kiến:

~~~text
BaseMarker present: true
OptionalCodec bean present: false
~~~

Log Spring Boot có thể bao quanh các dòng trên. Kết quả quan trọng là **ứng dụng khởi động bình thường**, BaseMarker có mặt và OptionalCodec không được tạo. Nếu optional-api vẫn xuất hiện trong dependency tree, hãy tìm dependency bắc cầu thay vì kết luận **@ConditionalOnClass** đã hỏng.

### 9.2. Khi optional-api có mặt

Thêm **một dòng** sau vào block dependencies của **demo-app/build.gradle**:

~~~groovy
runtimeOnly project(':optional-api')
~~~

Chạy lại:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
gradle :demo-app:bootRun
~~~

Hai dòng kỳ vọng:

~~~text
BaseMarker present: true
OptionalCodec bean present: true
~~~

Đây là sự khác biệt do **classpath**, không phải do Spring Boot tải dependency động. Dependency đã được Gradle đưa vào runtime khi khởi động.

### 9.3. Bản chất của điều kiện @ConditionalOnClass

~~~text
Có OptionalCodec trên classpath?
            |
      +-----+-----+
      |           |
     Không        Có
      |           |
      v           v
Bỏ qua nested     Xét tiếp điều kiện
configuration     @ConditionalOnMissingBean
                        |
                 +------+------+
                 |             |
              Đã có bean   Chưa có bean
                 |             |
                 v             v
              Back off       Tạo bean
              mặc định      OptionalCodec
~~~

**Không suy ra** từ hình này rằng mọi class/configuration trong Spring Boot đều phải đi qua đúng thứ tự các bước trên trong một vòng lặp đơn giản. Đây là mô hình logic của pattern tự cấu hình được giới thiệu.

## 10. Nhiều kiểu bắt buộc: kiểm tra tất cả, không phải chỉ một

Đôi khi tích hợp cần **hai API khác nhau**:

~~~java
@ConditionalOnClass(
    name = {
        "com.example.optionalapi.OptionalCodec",
        "com.example.metrics.Meter"
    }
)
~~~

Nếu OptionalCodec hiện diện nhưng Meter thiếu, cấu hình vẫn **không match**. Điều kiện yêu cầu cả hai.

**Bảng chân trị:**

| OptionalCodec | Meter | Kết quả |
| --- | --- | --- |
| Có | Có | Match |
| Có | Không | Không match |
| Không | Có | Không match |
| Không | Không | Không match |

Nếu hai thư viện có thể thay thế lẫn nhau, đừng gộp chúng trong một **@ConditionalOnClass**. Hãy tạo hai class cấu hình có điều kiện độc lập, mỗi class đăng ký một implementation tương ứng; nếu cần OR thật sự, thiết kế condition tổng hợp và kiểm tra trường hợp **cả hai cùng có mặt** để tránh đăng ký bean xung đột.

### 10.1. Kết hợp @ConditionalOnClass với điều kiện khác

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
@ConditionalOnProperty(
    prefix = "example.codec",
    name = "enabled",
    havingValue = "true"
)
public class CodecFeatureAutoConfiguration {
}
~~~

Đoạn trên minh họa việc **cả hai điều kiện phải thỏa mãn**: class OptionalCodec có mặt **và** property **example.codec.enabled=true**. Class có mặt nhưng feature bị tắt vẫn không áp dụng cấu hình.

Trong bài thực hành, **@ConditionalOnMissingBean** ở phương thức @Bean cũng là điều kiện bổ sung. **@ConditionalOnClass** không ưu tiên tuyệt đối để bỏ qua các điều kiện khác.

## 11. Kiểm tra JAR và tài nguyên đăng ký

Chạy:

~~~bash
gradle :optional-autoconfigure:jar
~~~

Với version **1.0.0** ở root:

~~~text
optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar
~~~

Liệt kê nội dung:

~~~bash
jar tf optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar
~~~

Tìm:

~~~text
com/example/autoconfigure/BaseMarker.class
com/example/autoconfigure/CodecAutoConfiguration.class
com/example/autoconfigure/CodecAutoConfiguration$OptionalCodecConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Chỉ **class ngoài** được liệt kê trong imports:

~~~text
com.example.autoconfigure.CodecAutoConfiguration
~~~

Dù OptionalCodec **không có trong JAR autoconfigure**, class bytecode của nested configuration vẫn có thể được đóng gói vì đã được biên dịch dựa trên optional-api ở **compileOnly**. Spring chỉ cần không cố xử lý nhánh ấy khi runtime thiếu dependency.

Để đọc nội dung imports từ JAR (khi có công cụ unzip):

~~~bash
unzip -p optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nếu không có **unzip**, dùng công cụ xem ZIP/JAR tương đương. Đối chiếu FQCN với package/class đã biên dịch để loại lỗi resource sai tên.

## 12. Chẩn đoán khi @ConditionalOnClass không như mong đợi

### 12.1. Class chắc chắn có trong source nhưng condition không match

Kiểm tra **runtimeClasspath**, không chỉ source:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
gradle :demo-app:dependencyInsight --configuration runtimeClasspath --dependency optional-api
~~~

Trong bài mẫu, optional-api ban đầu chỉ là **compileOnly** của thư viện, nên **không lan** vào runtime app. Nếu sau đó thêm **runtimeOnly project(':optional-api')**, class mới có mặt cho runtime.

Cũng cần kiểm tra **ClassLoader** của context, nhất là khi có plugin architecture, custom classloader hoặc test isolation.

### 12.2. Class có mặt nhưng không tạo bean

Đó có thể là hành vi đúng. Xem điều kiện **@ConditionalOnMissingBean**, **@ConditionalOnProperty** hoặc condition khác. Nếu ứng dụng đã có bean cùng type, auto-config thường nhường quyền; không phải do @ConditionalOnClass sai.

Bật thông tin chẩn đoán khi chạy ứng dụng:

~~~bash
gradle :demo-app:bootRun --args='--debug'
~~~

Đọc **Condition Evaluation Report** để tìm nhánh không match. Thông tin hiển thị có thể khác tùy version và thời điểm một ứng viên bị loại; đừng coi việc thiếu một dòng log cụ thể là bằng chứng duy nhất.

### 12.3. Có NoClassDefFoundError dù đã đặt condition

Xác định lỗi phát sinh ở class nào. Nếu một phương thức @Bean trong class ngoài có return type/parameter thuộc optional-api, điều kiện tại method có thể không bảo vệ được việc introspection signature. Chuyển nhóm method đó vào nested **@Configuration** có **@ConditionalOnClass** ở cấp class.

Ngoài ra, rà soát superclass, interface, field, static initializer hoặc constructor đang trực tiếp cần class optional. **@ConditionalOnClass không thay thế quy tắc thiết kế ranh giới dependency**.

### 12.4. Điều kiện match nhưng runtime vẫn NoSuchMethodError

Class tồn tại không có nghĩa version tương thích. Một ứng dụng có thể cài bản OptionalCodec khác nhưng cùng FQCN, trong khi method **encode(String)** bị xóa hoặc thay đổi signature. **@ConditionalOnClass** có thể match và bean creation hoặc invocation vẫn lỗi.

Kiểm tra selected dependency version bằng **dependencyInsight**, đối chiếu API được hỗ trợ và dùng integration tests với nhiều version quan trọng. Không coi classpath condition là validation đầy đủ của binary compatibility.

### 12.5. Annotation value vs name không mang lại kết quả như dự đoán

Xem liệu class literal thuộc **compileOnly** và đang bị yêu cầu trong một method signature ở lớp không được bảo vệ hay không. Trong annotation cấp class thông thường, Spring Boot hỗ trợ đọc metadata để kiểm tra class literal, nhưng ở **meta-annotation** nên dùng **name** theo hướng dẫn của tài liệu.

Không dùng **name="OptionalCodec"** thiếu package. Cũng không dùng chuỗi **"com.example.optionalapi.OptionalCodec.class"** vì phần **.class** ở đó không phải FQCN.

### 12.6. Test pass nhưng ứng dụng consumer không nhận cấu hình

**ApplicationContextRunner** với **AutoConfigurations.of** chỉ import class cấu hình đã biết. Nó không chứng minh tệp imports được phát hiện qua JAR. Hãy kiểm tra **src/main/resources**, nội dung JAR và classpath consumer.

Tách ba bước khi chẩn đoán:

1. **Discovery**: class auto-configuration có được tìm làm ứng viên không?
2. **Condition**: class required có mặt không và bean conditions khác có phù hợp không?
3. **Creation**: Spring có tạo bean đúng type/name và dependencies hợp lệ không?

## 13. Những lỗi hiểu sai thường gặp

**Sai 1: “Có @ConditionalOnClass nghĩa là class đó đã được Spring đăng ký làm bean.”** Không. Đây là phép kiểm tra sự hiện diện của **kiểu Java**, không phải sự tồn tại bean.

**Sai 2: “Trong danh sách value chỉ cần một class có mặt.”** Không. Tất cả các kiểu được liệt kê phải hiện diện.

**Sai 3: “Khi thiếu class, Spring Boot tự tải JAR về.”** Không. Dependency resolution do build/deployment quyết định. Condition chỉ đọc classpath hiện có.

**Sai 4: “Dùng name ở @ConditionalOnClass thì không cần bất kỳ sự cách ly nào.”** Không. Dù annotation dùng chuỗi, method signature hoặc field trong class được tải vẫn có thể tham chiếu type optional bị thiếu.

**Sai 5: “Đặt @ConditionalOnClass trên @Bean trả về type tùy chọn luôn an toàn.”** Không. Có thể bị introspection method signature trước khi condition phương thức giúp bỏ qua bean. Dùng nested configuration có condition cấp class.

**Sai 6: “Class có mặt đồng nghĩa một API/version hợp lệ.”** Không. Tồn tại class không bảo đảm method tương thích, các phụ thuộc bắc cầu hay native resources cần thiết có mặt.

**Sai 7: “Chỉ cần thêm @ComponentScan để tìm auto-configuration.”** Không đúng với cách thư viện Boot 3.x công bố auto-configuration; dùng **AutoConfiguration.imports**.

**Sai 8: “Tôi đã thêm testImplementation nên runtime app có class.”** Không. Phải kiểm tra runtimeClasspath của app hoặc artifact deploy.

**Sai 9: “Class được import nghĩa là bean chắc chắn được tạo.”** Không. Bean conditions khác vẫn có thể back off, property không match hoặc bean creation thất bại.

**Sai 10: “Unit test trực tiếp AutoConfigurations.of đủ chứng minh JAR đã phát hành đúng.”** Không. Cần test consumer và kiểm tra resource trong JAR.

## 14. Bài tập tự luyện

1. **Dự đoán hai class:** Với **@ConditionalOnClass(name={"com.example.A","com.example.B"})**, lập bảng kết quả khi A/B lần lượt có/không. Giải thích vì sao chỉ một class hiện diện không đủ.
2. **Sử dụng value và name:** Biên dịch một cấu hình dùng class literal ở **value**, một cấu hình dùng FQCN ở **name**. Đảm bảo hai cách đều có cùng điều kiện hiện diện trong ngữ cảnh hợp lệ; giải thích khác biệt compile dependency.
3. **Đặt condition sai vị trí:** Trong nhánh thử nghiệm, chuyển method tạo OptionalCodec ra class ngoài và chỉ bảo vệ method bằng **@ConditionalOnClass**. Quan sát test classloader thiếu class và giải thích rủi ro.
4. **Thêm property:** Đặt **@ConditionalOnProperty(prefix="example.codec",name="enabled",havingValue="true")** lên nested config. Test class có mặt/property false, class thiếu/property true, và cả hai đúng.
5. **Custom bean back off:** Tạo bean OptionalCodec từ app rồi xác nhận auto-config không đăng ký bean mặc định cùng kiểu.
6. **Lỗi version:** Giả lập class OptionalCodec vẫn còn nhưng method thay đổi ở bản mới; giải thích tại sao condition match nhưng invocation thất bại. Kiểm tra dependency selected version.
7. **Kiểm tra JAR:** Xóa tạm imports trong nhánh riêng, giữ code và test runner. So sánh unit test trực tiếp với demo-app để hiểu lỗi discovery.
8. **Không phụ thuộc optional-api ở runtime:** Đọc Gradle dependency tree để chứng minh **compileOnly** không kéo dependency vào consumer; sau đó thêm **runtimeOnly** và kiểm chứng.
9. **Thiết kế hai backend thay thế:** Tạo hai nested configuration, một yêu cầu CodecA, một yêu cầu CodecB. Viết test trường hợp A-only, B-only, cả hai và không có class nào. Chỉ định rõ cơ chế ưu tiên để tránh hai bean cùng type nếu cả hai được cài.

## 15. Checklist hoàn thành bài

- [ ] Giải thích được **@ConditionalOnClass** dùng để kiểm tra **class**, không kiểm tra bean.
- [ ] Phân biệt được **value** và **name** trong annotation, dùng FQCN chính xác với name.
- [ ] Biết nhiều class được chỉ định phải **cùng có mặt** mới match.
- [ ] Hiểu điều kiện ở cấp class ngăn cả cấu hình, còn điều kiện method chỉ ngăn một bean method.
- [ ] Hiểu vì sao method @Bean trả về type optional có thể cần nested configuration riêng.
- [ ] Biết cách sử dụng **@Configuration(proxyBeanMethods=false)** và **@ConditionalOnClass** ở nested class.
- [ ] Tạo được Java 21/Gradle multi-module sample có **compileOnly optional-api**.
- [ ] Chạy được **ApplicationContextRunner** với **FilteredClassLoader** để mô phỏng class thiếu.
- [ ] Viết test bean custom làm **@ConditionalOnMissingBean** back off.
- [ ] Chạy được demo-app khi optional-api vắng mặt và khi có mặt.
- [ ] Kiểm tra file **AutoConfiguration.imports** và các class bytecode trong JAR.
- [ ] Đọc được runtimeClasspath và Condition Evaluation Report để chẩn đoán.
- [ ] Không nhầm class presence với API compatibility hoặc bean presence.

## Kết luận

**@ConditionalOnClass** cho phép Spring Boot chỉ áp dụng auto-configuration khi **mọi kiểu Java bắt buộc đều hiện diện trên classpath**. Nó là điều kiện dành cho dependency/classpath, **không phải** kiểm tra sự tồn tại của bean. Với **value**, khai báo các class literal; với **name**, khai báo FQCN dạng chuỗi. Nếu nhiều class được yêu cầu, **tất cả phải có mặt**.

Khi API tùy chọn xuất hiện trong chữ ký của phương thức **@Bean**, hãy cô lập phương thức ấy trong **static nested @Configuration** được bảo vệ bởi **@ConditionalOnClass ở cấp class**. Kiểm thử bằng classloader thiếu dependency, context runner và ứng dụng tiêu thụ thật; kiểm tra thêm JAR/AutoConfiguration.imports và dependency graph để phân biệt lỗi discovery, condition và bean creation.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Developing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [ConditionalOnClass — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
