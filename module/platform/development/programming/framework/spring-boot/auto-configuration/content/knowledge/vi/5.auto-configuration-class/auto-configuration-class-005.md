# Cô lập cấu hình cho dependency tùy chọn bằng lớp cấu hình lồng nhau

## 1. Bài toán: thư viện có tính năng tùy chọn nhưng không phải ứng dụng nào cũng cài dependency

Giả sử một thư viện Spring Boot cung cấp một tính năng cốt lõi luôn sẵn có và một tích hợp chỉ hoạt động khi người dùng cài thêm thư viện bên ngoài. Ví dụ, một auto-configuration tạo bean **CoreMarker** mặc định và, nếu class **OptionalFormatter** có trên classpath, tạo thêm bean **OptionalFormatter**.

Yêu cầu hợp lý là:

- Ứng dụng **không có** thư viện optional vẫn khởi động bình thường và dùng được tính năng cốt lõi.
- Ứng dụng **có** thư viện optional được Spring Boot tự cấu hình thêm bean thích hợp.
- Ứng dụng có thể cung cấp bean riêng để thay thế bean mặc định.
- Khi thư viện optional **vắng mặt**, Spring không phải tải hoặc phân tích đầy đủ những phương thức **@Bean** có chữ ký phụ thuộc class của thư viện ấy.
- Thư viện auto-configuration được phát hiện qua **AutoConfiguration.imports**, không yêu cầu người dùng tự thêm **@ComponentScan** hay **@Import** cho các package nội bộ.

Chỉ viết **@ConditionalOnClass** trên phương thức **@Bean** chưa phải cách cách ly chắc chắn khi phương thức đó có **kiểu trả về hoặc kiểu tham số** thuộc dependency không có tại runtime. Để tránh rủi ro tải/đọc class quá sớm, Spring Boot khuyến nghị **đặt các phương thức liên quan trong một lớp @Configuration riêng, thường là lớp static lồng nhau**, rồi gắn điều kiện classpath **lên chính lớp cấu hình lồng nhau**.

Đây là trọng tâm của bài học. Người học sẽ xem cách thiết kế, hiện thực, kiểm thử và chẩn đoán cơ chế cô lập ấy bằng một project Java 21/Gradle/Spring Boot 3.3.

## 2. Phân biệt thư viện tùy chọn, auto-configuration và class loading

**Dependency tùy chọn** là thư viện mà tính năng bổ sung có thể sử dụng nhưng **không bắt buộc phải tồn tại trong mọi ứng dụng tiêu thụ**. Ví dụ: một module tích hợp database, message broker, cache, JSON library hoặc công cụ quan sát có thể chỉ hoạt động khi API của hệ thống tương ứng hiện diện.

**Auto-configuration** là tập các class cấu hình mà Spring Boot có thể khám phá, xét điều kiện và dùng để tạo bean mặc định.

**Class loading và introspection** là những hoạt động của JVM/Spring khi cần nạp class, kiểm tra kiểu trả về, tham số, annotation hoặc phương thức. Nếu class được phân tích có signature hoặc bytecode tham chiếu trực tiếp một class không tồn tại, quá trình đó có thể dẫn tới lỗi như **NoClassDefFoundError**, **ClassNotFoundException** hoặc lỗi introspection tùy đường xử lý.

Ví dụ, class **OptionalFormatter** chỉ có nếu ứng dụng đưa artifact optional-api lên runtime classpath. Việc **source** của module auto-configuration từng biên dịch cùng optional-api không bảo đảm **consumer runtime** luôn có artifact ấy.

### 2.1. Tại sao một điều kiện classpath đôi khi chưa đủ?

Hãy xét mẫu **có rủi ro** sau. Đây là mã minh họa một cách viết cần tránh, không phải file Java độc lập:

~~~java
@AutoConfiguration
class RiskyAutoConfiguration {

    @Bean
    @ConditionalOnClass(OptionalFormatter.class)
    OptionalFormatter optionalFormatter() {
        return new OptionalFormatter();
    }
}
~~~

Ở đây annotation **@ConditionalOnClass** gắn trực tiếp lên **phương thức @Bean**. Trong khi đó, chữ ký phương thức trả về **OptionalFormatter**, tức là đã tham chiếu một type chỉ có khi dependency tùy chọn xuất hiện.

Spring có thể phải tải cấu hình và kiểm tra method signature **trước khi điều kiện phương thức được đánh giá theo cách ta kỳ vọng**. Nếu type không có, cấu hình có nguy cơ lỗi trong giai đoạn phân tích class. Vì vậy không nên trông chờ annotation trên method để bảo vệ chính chữ ký method đó.

**Kết luận:** điều kiện đặt trên method và điều kiện đặt trên một configuration class **không tương đương** về khả năng cách ly class tùy chọn.

### 2.2. Tại sao lớp cấu hình lồng nhau giải quyết được?

Thay vì để method dùng OptionalFormatter nằm trực tiếp trong auto-configuration luôn được đọc, ta tách nó ra:

~~~java
@AutoConfiguration
public class SafeAutoConfiguration {

    @Bean
    CoreMarker coreMarker() {
        return new CoreMarker("core");
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(OptionalFormatter.class)
    static class OptionalFormatterConfiguration {

        @Bean
        OptionalFormatter optionalFormatter() {
            return new OptionalFormatter();
        }
    }
}
~~~

Đây là **mẫu minh họa ngắn**, chưa bao gồm package, import và điều kiện override. Lớp ngoài chỉ tham chiếu type core ở phương thức bean của mình. Method có chữ ký **OptionalFormatter** được đặt trong **static nested configuration**. Điều kiện classpath gắn ở **cấp lớp lồng nhau**, cho phép Spring đọc metadata annotation của lớp ấy và quyết định **có nên xử lý class cấu hình lồng nhau hay không** trước khi kiểm tra sâu các method của nó.

**@Configuration(proxyBeanMethods = false)** phù hợp với cấu hình dạng factory method độc lập, nơi ta không cần proxy để chặn lời gọi giữa các phương thức **@Bean**. Từ khóa **static** ở nested class giúp class lồng nhau không yêu cầu instance của class ngoài.

Đây là pattern được tài liệu chính thức Spring Boot khuyến nghị cho trường hợp kiểu trả về của **@Bean** thuộc dependency tùy chọn.

## 3. Cơ chế đánh giá điều kiện ở cấp lớp cấu hình

Khi Spring Boot phát hiện auto-configuration từ tài nguyên **AutoConfiguration.imports**, Spring sẽ xử lý metadata và điều kiện của các class cấu hình phù hợp.

Có thể hình dung:

~~~text
AutoConfiguration.imports
          |
          v
SafeAutoConfiguration (class ngoài)
          |
          +-----> CoreMarker coreMarker()
          |         không phụ thuộc optional-api
          |
          +-----> OptionalFormatterConfiguration (static nested)
                     |
                     v
             @ConditionalOnClass(OptionalFormatter)
                     |
             +-------+-------+
             |               |
      Class không có      Class có mặt
             |               |
             v               v
      Không xử lý sâu     Xử lý cấu hình lồng nhau
      method signature             |
                                  v
                         @ConditionalOnMissingBean
                                  |
                                  v
                         Đăng ký OptionalFormatter
                         khi chưa có bean khác
~~~

Cách tách này giữ **nhánh cốt lõi** khỏi phụ thuộc vào type chỉ có ở nhánh optional. Khi class tùy chọn không có, nested configuration không được chọn để đăng ký các bean của nó.

### 3.1. ASM metadata và @ConditionalOnClass

Tài liệu Spring Boot mô tả việc đọc annotation metadata bằng ASM. Vì vậy, khi **@ConditionalOnClass(OptionalFormatter.class)** đặt **trực tiếp trên class @Configuration**, Spring có thể kiểm tra metadata class mà không cần tải đầy đủ class cấu hình theo cách làm phân giải mọi method signature trước. Đây là lý do pattern nested class hữu ích.

Có hai cách chỉ định type:

~~~java
@ConditionalOnClass(OptionalFormatter.class)
~~~

hoặc:

~~~java
@ConditionalOnClass(name = "com.example.optionalapi.OptionalFormatter")
~~~

Hai đoạn trên đều là **annotation minh họa**, không phải chương trình Java độc lập. **value/class literal** thường được dùng khi module có class optional ở compile classpath; **name** dùng khi không muốn tham chiếu class literal hoặc khi xây annotation tổng hợp.

**Lưu ý:** Nếu dùng **@ConditionalOnClass** làm meta-annotation trong một annotation do mình tự định nghĩa, tài liệu Spring Boot yêu cầu dùng **name** thay cho class literal để đảm bảo cách xử lý metadata phù hợp. Điều này khác với việc đặt annotation trực tiếp lên nested configuration như ở ví dụ bài học.

### 3.2. Lớp lồng nhau có cần @AutoConfiguration riêng không?

**Không.** Ở mẫu thông dụng, chỉ **lớp ngoài** được đăng ký làm ứng viên auto-configuration:

~~~text
com.example.autoconfigure.OptionalFormatterAutoConfiguration
~~~

Lớp lồng nhau là một **@Configuration** hỗ trợ nằm trong class ngoài, được Spring xử lý theo cơ chế class cấu hình lồng nhau. Không cần thêm dòng thứ hai cho **OptionalFormatterAutoConfiguration$OptionalFormatterConfiguration** vào imports chỉ để nested class có hiệu lực.

Có thể có những kiến trúc tách cấu hình optional thành **top-level @Configuration** riêng và import có điều kiện. Nhưng khi phạm vi bài học là **static nested @Configuration**, hãy giữ imports cho class ngoài và kiểm chứng nested class theo cách đó.

### 3.3. Đừng nhầm type condition với bean condition

- **@ConditionalOnClass** hỏi: class có trên classpath không?
- **@ConditionalOnMissingBean** hỏi: có bean phù hợp đã được đăng ký trong context chưa?
- **@ConditionalOnProperty** hỏi: property có phù hợp không, theo semantics được khai báo?
- **@ConditionalOnWebApplication** hỏi: loại web application có phù hợp không?

Đây là những điều kiện bổ trợ. Class xuất hiện **chưa đủ** để khẳng định bean mặc định được tạo. Khi người dùng đã tự khai báo bean, **@ConditionalOnMissingBean** có thể khiến cấu hình mặc định nhường quyền (*back off*).

## 4. Thiết kế ví dụ: ba module và một integration tùy chọn

Ta xây project:

~~~text
optional-config-lab/
├── settings.gradle
├── build.gradle
├── optional-api/
│   ├── build.gradle
│   └── src/main/java/com/example/optionalapi/OptionalFormatter.java
├── optional-autoconfigure/
│   ├── build.gradle
│   ├── src/main/java/com/example/autoconfigure/
│   │   ├── CoreMarker.java
│   │   └── OptionalFormatterAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/autoconfigure/
│       └── OptionalFormatterAutoConfigurationTests.java
└── demo-app/
    ├── build.gradle
    └── src/main/java/com/example/consumer/
        └── DemoApplication.java
~~~

Vai trò:

1. **optional-api:** một JAR nhỏ chứa class **OptionalFormatter**. Nó chỉ bắt buộc nếu ứng dụng muốn dùng tích hợp.
2. **optional-autoconfigure:** JAR chứa **CoreMarker** và lớp auto-configuration. Module này **biên dịch được** khi thấy optional-api, nhưng **không kéo optional-api vào runtime** của ứng dụng tiêu thụ.
3. **demo-app:** ứng dụng Spring Boot nhận auto-configuration qua classpath và tự in trạng thái hai bean. Thí nghiệm đầu không cài optional-api, thí nghiệm sau cài thêm.

**Ràng buộc quan trọng:** Module auto-configuration phải thực sự dùng **compileOnly** cho dependency tùy chọn. Nếu vô tình dùng **implementation project(':optional-api')**, Gradle có thể đưa optional-api vào runtimeClasspath của consumer, khiến thí nghiệm “vắng dependency” không còn đúng.

## 5. Cấu hình Gradle đầy đủ

Ví dụ cố định Spring Boot **3.3.13** cùng Java **21** để phù hợp một phiên bản cụ thể. Đó là version của bài thực hành, không phải tuyên bố phiên bản mới nhất. Cần JDK 21, Gradle 8.x tương thích và quyền tải dependency khi chạy lần đầu.

### 5.1. settings.gradle ở root

~~~groovy
rootProject.name = 'optional-config-lab'
include 'optional-api', 'optional-autoconfigure', 'demo-app'
~~~

### 5.2. build.gradle ở root

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

File root áp dụng Java plugin và BOM cho các subproject. **apply false** ở Spring Boot plugin root chỉ công bố plugin; module **demo-app** mới áp dụng plugin để có **bootRun** và **bootJar**. Modules thư viện dùng JAR thông thường.

### 5.3. optional-api/build.gradle

~~~groovy
plugins {
    id 'java-library'
}
~~~

### 5.4. optional-autoconfigure/build.gradle

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

Điểm mấu chốt là:

- **compileOnly project(':optional-api')**: cho phép trình biên dịch Java hiểu kiểu OptionalFormatter trong nested configuration nhưng không đưa optional-api vào runtime classpath của consumer.
- **testImplementation project(':optional-api')**: cho test thấy class OptionalFormatter, đồng thời có thể cố tình **ẩn** nó bằng FilteredClassLoader để kiểm tra nhánh thiếu class.
- **implementation spring-boot-autoconfigure**: cung cấp annotation và API Spring Boot cần thiết cho class cấu hình.
- **spring-boot-starter-test**: cung cấp JUnit 5, AssertJ, Spring Boot test và ApplicationContextRunner cho các kiểm thử.

Đừng thay **compileOnly** bằng **runtimeOnly** trong module autoconfigure: thư viện cần thấy class OptionalFormatter **khi compile method signature**. Ngược lại, đừng dùng **implementation** nếu mục tiêu là đảm bảo optional-api không tự lan vào runtime của mọi consumer.

### 5.5. demo-app/build.gradle

~~~groovy
plugins {
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':optional-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Ứng dụng này **chưa khai báo** optional-api. Starter nền tảng cung cấp runtime Spring Boot thông thường, không cần web server để chạy ApplicationRunner.

## 6. Cài đặt optional-api độc lập

Tệp **optional-api/src/main/java/com/example/optionalapi/OptionalFormatter.java**:

~~~java
package com.example.optionalapi;

public final class OptionalFormatter {

    public String format(String name) {
        return "Optional: " + name;
    }
}
~~~

Đây là class Java độc lập, không cần Spring. Nó mô phỏng một API của thư viện ngoài. Cách để class này vào module riêng là để **chủ động thay đổi runtimeClasspath** và xem Spring Boot có cách ly configuration đúng khi class vắng mặt không.

Nếu viết lớp này ngay trong module autoconfigure, nó sẽ luôn ở classpath cùng thư viện và không còn là dependency tùy chọn thật sự.

## 7. Tạo CoreMarker và cấu hình auto-configuration có nested class

### 7.1. Tệp CoreMarker.java

Tệp **optional-autoconfigure/src/main/java/com/example/autoconfigure/CoreMarker.java**:

~~~java
package com.example.autoconfigure;

public record CoreMarker(String name) {
}
~~~

CoreMarker không phụ thuộc optional-api. Nó là bean cốt lõi giúp chứng minh ứng dụng vẫn có tính năng nền tảng khi tích hợp tùy chọn bị bỏ qua.

### 7.2. Tệp OptionalFormatterAutoConfiguration.java

Tệp **optional-autoconfigure/src/main/java/com/example/autoconfigure/OptionalFormatterAutoConfiguration.java**:

~~~java
package com.example.autoconfigure;

import com.example.optionalapi.OptionalFormatter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class OptionalFormatterAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CoreMarker.class)
    public CoreMarker coreMarker() {
        return new CoreMarker("core");
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(OptionalFormatter.class)
    static class OptionalFormatterConfiguration {

        @Bean
        @ConditionalOnMissingBean(OptionalFormatter.class)
        OptionalFormatter optionalFormatter() {
            return new OptionalFormatter();
        }
    }
}
~~~

Đây là toàn bộ source của class cấu hình. **@AutoConfiguration** trên lớp ngoài giúp Spring Boot hiểu đây là một ứng viên auto-configuration; **@ConditionalOnClass** được gắn trực tiếp lên nested configuration.

**Tại sao đặt OptionalFormatter.class trong lớp lồng nhau?** Lớp ngoài không có **@Bean** nào trả về OptionalFormatter. Chữ ký method dùng type tùy chọn được nhốt trong class **OptionalFormatterConfiguration**; Spring có thể bỏ qua class này dựa trên metadata khi OptionalFormatter vắng mặt. Đây là cách tránh rủi ro introspection trong trường hợp không có JAR optional.

**Tại sao @ConditionalOnMissingBean(OptionalFormatter.class) vẫn cần?** Khi optional-api có mặt, ứng dụng có thể tự đăng ký OptionalFormatter tùy chỉnh. Điều kiện này tránh đăng ký bean mặc định thứ hai. Classpath condition và bean condition phục vụ hai mục đích khác nhau.

**Tại sao nested class là static?** Nested static class không cần instance của class ngoài. Nó phù hợp vai trò một configuration nhỏ độc lập, chỉ dùng khi condition đạt.

**Tại sao proxyBeanMethods = false?** Nested class không gọi các method **@Bean** khác bằng Java method calls. Không cần proxy subclass để bảo đảm các lời gọi nội bộ tới bean đi qua container; setting này giảm overhead và thể hiện rõ ý định.

**Có thể dùng @ConditionalOnClass(name = "...") không?** Có. Nếu thay bằng:

~~~java
@ConditionalOnClass(
    name = "com.example.optionalapi.OptionalFormatter"
)
~~~

thì Spring dùng FQCN dạng chuỗi. Trong ví dụ này dùng class literal trực tiếp để thể hiện type checking lúc compile. Điều kiện gắn ở cấp configuration nên an toàn theo cơ chế metadata được Spring Boot tài liệu hóa.

### 7.3. Thêm đúng một dòng AutoConfiguration.imports

Tạo tệp:

~~~text
optional-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung chính xác:

~~~text
com.example.autoconfigure.OptionalFormatterAutoConfiguration
~~~

**Chỉ đăng ký lớp ngoài**, không thêm nested class vào imports. Nested class được Spring xem xét khi xử lý cấu hình ngoài. Đừng thêm dấu phẩy, ký pháp **.class** hoặc Java import statement.

Spring Boot 3.x dùng resource **AutoConfiguration.imports** để khám phá các class auto-configuration. File nằm trong main resources, nên sẽ được đóng gói vào JAR thư viện khi build đúng.

## 8. Kiểm thử bằng ApplicationContextRunner

Một thiết kế tốt phải kiểm chứng ít nhất ba tình huống:

1. OptionalFormatter hiện diện → context có bean core và bean optional.
2. OptionalFormatter vắng mặt → context vẫn tạo core, không tạo bean optional và không lỗi class loading.
3. Người dùng đã đăng ký OptionalFormatter → auto-configuration nhường quyền, không tạo bản mặc định.

**ApplicationContextRunner** là công cụ phù hợp để chạy ApplicationContext nhỏ có các điều kiện khác nhau mà không khởi động web server.

Tệp **optional-autoconfigure/src/test/java/com/example/autoconfigure/OptionalFormatterAutoConfigurationTests.java**:

~~~java
package com.example.autoconfigure;

import com.example.optionalapi.OptionalFormatter;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalFormatterAutoConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    OptionalFormatterAutoConfiguration.class
                )
            );

    @Test
    void createsOptionalBeanWhenDependencyExists() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(CoreMarker.class);
            assertThat(context).hasSingleBean(OptionalFormatter.class);
            assertThat(
                context.getBean(OptionalFormatter.class).format("An")
            ).isEqualTo("Optional: An");
        });
    }

    @Test
    void startsWithoutOptionalDependency() {
        runner.withClassLoader(
            new FilteredClassLoader("com.example.optionalapi")
        ).run(context -> {
            assertThat(context).hasSingleBean(CoreMarker.class);
            assertThat(context.containsBean("optionalFormatter"))
                .isFalse();
            assertThat(context.getBean(CoreMarker.class).name())
                .isEqualTo("core");
        });
    }

    @Test
    void backsOffWhenUserSuppliesOptionalBean() {
        runner.withUserConfiguration(UserFormatterConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(OptionalFormatter.class);
                assertThat(context.containsBean("optionalFormatter"))
                    .isFalse();
                assertThat(context.containsBean("customFormatter"))
                    .isTrue();
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFormatterConfiguration {

        @Bean
        OptionalFormatter customFormatter() {
            return new OptionalFormatter();
        }
    }
}
~~~

### 8.1. Giải thích từng kiểm thử

**createsOptionalBeanWhenDependencyExists:** Test dùng **testImplementation project(':optional-api')**, nên class OptionalFormatter nằm trên test classpath. Nested configuration được cho phép, auto-configuration đăng ký một bean OptionalFormatter mặc định.

**startsWithoutOptionalDependency:** **FilteredClassLoader** che các class thuộc package optional-api khi context đang chạy. Kiểm thử không gọi **getBean(OptionalFormatter.class)** trong nhánh thiếu class vì chính hành động ấy sẽ phụ thuộc type đang bị ẩn. Thay vào đó kiểm tra bằng tên bean. Nếu Spring xử lý trực tiếp method signature sai thời điểm, test này có thể bộc lộ lỗi khởi tạo context.

**backsOffWhenUserSuppliesOptionalBean:** Test đưa một class **@Configuration** của ứng dụng vào trước. Khi nested auto-configuration được xử lý, điều kiện **@ConditionalOnMissingBean(OptionalFormatter.class)** không match, nên bean **optionalFormatter** mặc định không được đăng ký. Bean người dùng **customFormatter** vẫn tồn tại.

### 8.2. Chạy test

Trong thư mục root project:

~~~bash
gradle :optional-autoconfigure:test
~~~

Nếu project có Gradle Wrapper, sử dụng **./gradlew :optional-autoconfigure:test** trên macOS/Linux hoặc **.\gradlew.bat :optional-autoconfigure:test** trên Windows.

**Kết quả dự kiến:** Task test thành công; Gradle/JUnit ghi thông tin console theo thiết lập máy và test logging. Không có stdout cố định cần sao chép. Mỗi assertion là bằng chứng cụ thể về sự tồn tại hoặc vắng mặt của bean.

### 8.3. Phạm vi mà unit test chứng minh

Test **AutoConfigurations.of(OptionalFormatterAutoConfiguration.class)** chỉ định auto-configuration trực tiếp cho runner. Nó **kiểm tra logic condition và mức an toàn khi class tùy chọn bị ẩn**.

Nó **chưa chứng minh** file **AutoConfiguration.imports** được đóng gói vào JAR và Spring Boot tự phát hiện class khi consumer chỉ thêm dependency. Cần thêm bước kiểm chứng ứng dụng tiêu thụ, không nên nhầm test condition với test discovery.

## 9. Chạy ứng dụng tiêu thụ và chứng minh dependency optional thật sự

Tệp **demo-app/src/main/java/com/example/consumer/DemoApplication.java**:

~~~java
package com.example.consumer;

import com.example.autoconfigure.CoreMarker;
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
    ApplicationRunner inspectBeans(ApplicationContext context) {
        return args -> {
            System.out.println(
                "Core bean: " + !context.getBeansOfType(CoreMarker.class)
                    .isEmpty()
            );
            System.out.println(
                "Optional bean: " + context.containsBean("optionalFormatter")
            );
        };
    }
}
~~~

Package của ứng dụng là **com.example.consumer**, khác **com.example.autoconfigure**. Vì vậy, component scanning mặc định từ **DemoApplication** không tìm auto-configuration một cách tình cờ. Spring Boot khám phá nó qua **AutoConfiguration.imports** của JAR module thư viện.

### 9.1. Lần chạy A: chỉ có autoconfigure, không có optional-api

Giữ dependencies của **demo-app** như chặng 5, không thêm **optional-api**. Kiểm tra runtimeClasspath:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
~~~

Đối chiếu rằng **optional-api** không xuất hiện như dependency runtime được chọn. Nếu thấy artifact ấy, hãy tìm nhánh đưa nó vào, vì thử nghiệm mất ý nghĩa khi class thực tế vẫn có mặt.

Sau đó chạy:

~~~bash
gradle :demo-app:bootRun
~~~

Khi cấu hình đúng, hai dòng do ApplicationRunner in ra dự kiến:

~~~text
Core bean: true
Optional bean: false
~~~

Ứng dụng vẫn khởi động dù không có OptionalFormatter. Đó là hành vi quan trọng nhất cần chứng minh: **nhánh cốt lõi tồn tại, nhánh phụ thuộc kiểu tùy chọn được bỏ qua an toàn**.

### 9.2. Lần chạy B: thêm optional-api vào runtime

Thêm **duy nhất dòng** này vào block dependencies của **demo-app/build.gradle**:

~~~groovy
runtimeOnly project(':optional-api')
~~~

Vì DemoApplication không import hoặc tham chiếu trực tiếp OptionalFormatter trong mã nguồn, **runtimeOnly** là đủ để thêm class optional vào runtime của consumer.

Chạy lại:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
gradle :demo-app:bootRun
~~~

Dòng output dự kiến:

~~~text
Core bean: true
Optional bean: true
~~~

Giờ class OptionalFormatter có trên classpath nên nested configuration qua được **@ConditionalOnClass**. Chưa có bean OptionalFormatter do user cung cấp, nên bean mặc định được tạo.

### 9.3. Một phép thử để so sánh nguyên nhân khác nhau

Giữ optional-api trên runtimeClasspath, rồi tắt toàn bộ auto-configuration của thư viện bằng tham số:

~~~bash
gradle :demo-app:bootRun --args='--spring.autoconfigure.exclude=com.example.autoconfigure.OptionalFormatterAutoConfiguration'
~~~

Khi đó cả bean core và bean optional do thư viện tạo đều không được tự cấu hình. Đây là **exclude ở lớp auto-configuration ngoài**, không tương đương với việc chỉ thiếu dependency tùy chọn; nó cho thấy cần phân biệt **điều kiện của nested class** với **quyết định loại toàn bộ outer auto-configuration**.

Đối với yêu cầu tắt riêng nhánh optional mà vẫn giữ core, có thể bổ sung **@ConditionalOnProperty** ở nested configuration và một property enablement riêng. Không cần viết AutoConfigurationImportFilter tùy chỉnh cho tình huống phổ biến này.

## 10. Kiểm tra JAR thư viện và file imports

Đóng gói module autoconfigure:

~~~bash
gradle :optional-autoconfigure:jar
~~~

Với version ở root, JAR mặc định:

~~~text
optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar
~~~

Liệt kê nội dung:

~~~bash
jar tf optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar
~~~

Kiểm tra ba nhóm entry:

~~~text
com/example/autoconfigure/CoreMarker.class
com/example/autoconfigure/OptionalFormatterAutoConfiguration.class
com/example/autoconfigure/OptionalFormatterAutoConfiguration$OptionalFormatterConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Tên file bytecode của nested class có dấu **$** giữa tên lớp ngoài và lớp lồng nhau. Điều này bình thường với **static nested class**.

**JAR autoconfigure không cần chứa OptionalFormatter.class**, vì class đó thuộc **optional-api**. Hãy đảm bảo optional-api vẫn ở JAR riêng, để khi ứng dụng không cài nó thì nhánh nested condition thực sự có cơ hội bị loại.

Kiểm tra thêm nội dung tài nguyên imports trong JAR, nếu có công cụ đọc ZIP:

~~~bash
unzip -p optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Output phải có FQCN của lớp ngoài. Nếu môi trường không có lệnh **unzip**, dùng công cụ ZIP/JAR tương đương. Test ApplicationContextRunner pass nhưng imports thiếu vẫn có thể khiến consumer không tự phát hiện thư viện.

## 11. Vì sao một nested configuration tốt hơn điều kiện ở @Bean?

So sánh:

| Thiết kế | Nếu class OptionalFormatter không có | Khả năng an toàn |
| --- | --- | --- |
| **@ConditionalOnClass** ngay trên method trả về OptionalFormatter trong class cấu hình luôn được xử lý | Spring có thể phải introspect method signature trước khi áp điều kiện | Có rủi ro lỗi nạp type; không phải pattern được khuyến nghị. |
| **@ConditionalOnClass** đặt lên **static nested @Configuration** chứa method trả về OptionalFormatter | Condition cấp class được xét trước khi nested configuration cần được xử lý đầy đủ | Pattern cô lập được Spring Boot tài liệu hóa. |
| Điều kiện chỉ dùng **@ConditionalOnMissingBean** | Phụ thuộc trạng thái bean, không chứng minh class optional có mặt | Không đủ bảo vệ việc thiếu thư viện. |
| Dùng **name** ở điều kiện classpath nhưng method vẫn nằm trong lớp ngoài | Tránh class literal trong annotation, nhưng signature của method vẫn tham chiếu type optional | Không giải quyết triệt để rủi ro introspection. |
| Ép optional-api thành dependency runtime bắt buộc | Tránh thiếu class bằng cách đưa luôn thư viện vào | Không còn đáp ứng mục tiêu dependency tùy chọn. |

Câu hỏi thiết kế đúng nên là: **Class nào có thể được framework đọc khi optional dependency vắng mặt?** Sau đó đặt mọi chữ ký phương thức trực tiếp dùng type optional vào một cấu hình được bảo vệ bằng condition ở cấp lớp.

### 11.1. Các lưu ý khi nested class có phụ thuộc phức tạp

Thư viện thật có thể dùng method parameter, constructor parameter, field, static initializer, generic type và annotation chứa class tùy chọn. Mỗi tham chiếu có thể làm phát sinh liên hệ class loading khác nhau.

Vì vậy:

- Đừng để **class ngoài** giữ một **field kiểu OptionalFormatter** hoặc dùng class optional trong static initializer.
- Đừng khai báo một bean method của class ngoài có **return type** hoặc parameter là class optional.
- Giữ phụ thuộc tùy chọn trong **nested configuration** và các class implementation được khởi tạo chỉ sau khi condition match.
- Nếu dùng API tùy chọn trong nhiều nhóm, cân nhắc tách mỗi nhóm vào một nested configuration có điều kiện phù hợp.
- Đặt các **@ConditionalOnMissingBean** trên cấu hình auto-configuration khi có bean mặc định cần nhường quyền.
- Kiểm tra compatibility theo version của thư viện optional: **class tồn tại** chưa bảo đảm những method/constructor mà code dùng vẫn tương thích. Có thể phải kết hợp kiểm tra version hoặc cung cấp module integration riêng khi API thay đổi lớn.

Cấu hình lồng nhau giúp quản lý ranh giới dependency; nó không thay thế việc khai báo dependency đúng hoặc kiểm thử với các version được hỗ trợ.

## 12. Chẩn đoán lỗi thực tế

### Trường hợp A — Có @ConditionalOnClass nhưng vẫn NoClassDefFoundError

Hãy xác định annotation đặt ở đâu. Nếu annotation nằm trên phương thức **@Bean** trả về chính class bị thiếu, code vẫn có nguy cơ lỗi khi Spring introspect phương thức. Chuyển **toàn bộ method liên quan** vào nested **@Configuration(proxyBeanMethods = false)** và đặt condition lên nested class.

Nếu lỗi còn tồn tại, tìm các tham chiếu tùy chọn khác ở outer class, constructor, field, static initializer hoặc class khởi tạo sớm. Lỗi class loading có thể xuất phát từ tham chiếu khác chứ không chỉ method đang xem.

### Trường hợp B — Class optional có mặt nhưng bean không được tạo

Đọc Condition Evaluation Report bằng cách chạy ứng dụng với:

~~~bash
gradle :demo-app:bootRun --args='--debug'
~~~

Kiểm tra những khả năng:

1. Ứng viên auto-configuration có được tìm qua imports không?
2. Có cấu hình exclude loại outer class không?
3. Class optional có đúng trên **runtimeClasspath** của demo-app không, hay chỉ ở compileClasspath/testRuntimeClasspath?
4. **@ConditionalOnMissingBean** có nhường quyền cho bean do người dùng khai báo không?
5. Có property, profile, condition khác hoặc lỗi tạo bean nào tác động không?

Nên kiểm tra bean theo **type và tên**, thay vì chỉ nhìn dòng log của startup.

### Trường hợp C — Test pass, ứng dụng consumer vẫn lỗi

**ApplicationContextRunner** truyền class cấu hình trực tiếp nên có thể bỏ qua lỗi tệp imports. Hãy dùng **jar tf** để kiểm tra resource, xác minh tên class trong file imports và kiểm tra dependency graph của consumer.

Nếu consumer có một version khác của optional API, test dùng version tại module có thể chưa bao phủ trường hợp đó. Khi cần, thêm bài test tích hợp với version tương ứng.

### Trường hợp D — Luôn thấy optional-api dù nghĩ đã để compileOnly

Có thể một dependency **khác** mang optional-api vào runtime transitively. Dùng:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
gradle :demo-app:dependencyInsight --configuration runtimeClasspath --dependency optional-api
~~~

Trong project bài tập, cả optional-api và các project nằm chung Gradle build, nhưng dependency vẫn được đưa vào runtime theo đúng configuration của từng project. **compileOnly ở optional-autoconfigure** không có nghĩa “không package” trong mọi công nghệ build khác, nên hãy kiểm tra artifact và runtimeClasspath thực tế thay vì suy luận từ một nhãn.

### Trường hợp E — Có hai bean OptionalFormatter

Kiểm tra bean tự khai báo và điều kiện **@ConditionalOnMissingBean(OptionalFormatter.class)** trong nested class. Nếu cả hai bean tồn tại, hãy kiểm tra thứ tự đăng ký bean definitions, type có đúng không và việc một class cấu hình bị import nhiều lần theo đường khác. Đừng vội bật global bean definition overriding để che xung đột.

## 13. Khi nào dùng top-level configuration riêng thay vì nested class?

Nested static **@Configuration** rất tiện khi tính năng tùy chọn nhỏ, có một nhóm bean và gắn tự nhiên với một outer auto-configuration. Khi tích hợp lớn hơn, bạn có thể tách ra **top-level configuration** độc lập (hoặc module auto-configuration riêng), rồi gắn classpath condition trên class đó và quản lý import/order rõ ràng.

Dù nested hay top-level, nguyên tắc vẫn giống nhau: **không để phần cấu hình luôn được xử lý tham chiếu sớm tới những type chỉ có ở classpath tùy chọn**.

Không nên thêm package-wide **@ComponentScan** trong autoconfiguration để tìm mọi bean của thư viện. Làm vậy khiến phạm vi phụ thuộc khó kiểm soát và có thể đăng ký bean khi dependency/condition không phù hợp.

## 14. Bài tập mở rộng

1. **Đổi điều kiện từ class sang method:** Trong nhánh thử nghiệm, đưa method optional ra outer class và chỉ đặt @ConditionalOnClass trên method. Chạy test FilteredClassLoader; quan sát kết quả và giải thích vì sao cách bố trí mới có rủi ro class loading.
2. **Thêm property bật/tắt:** Đặt **@ConditionalOnProperty(prefix="demo.formatter", name="enabled", havingValue="true", matchIfMissing=true)** lên nested configuration. Viết hai test cho enabled true/false; giữ cơ chế vắng class hoạt động.
3. **Thay bean mặc định:** Viết một custom OptionalFormatter bean trong consumer có phương thức format khác. Kiểm tra chỉ một bean đúng type được dùng.
4. **Kiểm tra runtimeClasspath:** Cố ý chuyển **compileOnly** thành **implementation** ở thư viện (trong nhánh thực nghiệm) và đọc lại dependency graph. Giải thích vì sao ứng dụng mất khả năng chứng minh thư viện optional vắng mặt.
5. **Tách top-level config:** Tách nested class thành một class cấu hình riêng có điều kiện tương đương và import có chủ đích. So sánh cách quản lý metadata, code và kiểm chứng.
6. **Mất imports:** Trong một nhánh thử nghiệm, tạm bỏ AutoConfiguration.imports. So sánh test ApplicationContextRunner với demo-app để phân biệt condition logic và discovery của JAR.

Khi thử nghiệm, mỗi lần chỉ thay một yếu tố. Trước khi chạy hãy ghi **dự đoán**, sau đó ghi **output**, **nguyên nhân** và **kết luận** từ bằng chứng.

## 15. Các hiểu lầm thường gặp

**“Đặt @ConditionalOnClass trên method nào cũng an toàn.”** Sai. Phương thức có return type thuộc dependency vắng mặt có thể bị phân tích trước khi method condition được xử lý. Pattern cô lập bằng nested configuration an toàn hơn.

**“Thêm name thay value là hết lỗi class loading.”** Không hẳn. name tránh tham chiếu class literal trong annotation, nhưng không loại bỏ chữ ký method/field đang tham chiếu type optional ở class phải tải.

**“Nested class phải ghi vào AutoConfiguration.imports.”** Không đúng với mẫu bài học. Chỉ cần đăng ký outer auto-configuration; Spring xử lý nested @Configuration trong cấu trúc của nó.

**“compileOnly đảm bảo mọi consumer không có optional-api.”** Không đúng. Nó chỉ ngăn dependency đó được module autoconfigure mang vào runtime theo configuration thông thường. Consumer hoặc một thư viện khác vẫn có thể thêm optional-api.

**“Có class optional thì chắc chắn có bean.”** Sai. Bean condition, property, exclude và lỗi runtime vẫn quyết định.

**“Lớp static lồng nhau là một bean tự tạo.”** Không. Nó là một class cấu hình được Spring có thể xử lý; các phương thức @Bean và condition trong nó mới quyết định những bean nghiệp vụ nào được đăng ký.

**“Auto-configuration có thể tự tải dependency thiếu.”** Không. Dependency resolution xảy ra ở build/runtime packaging; Spring Boot condition quyết định dựa trên classpath đã có, không tự tải JAR từ Maven Central khi khởi động.

**“Test context nhỏ đã chứng minh JAR thực tế đúng.”** Chưa đủ. Cần kiểm tra imports và chạy ứng dụng tiêu thụ tự khám phá cấu hình.

**“Class tồn tại nghĩa là API tương thích.”** Sai. Hai version khác nhau có thể có cùng class nhưng khác method/constructor; cần kiểm tra phiên bản mà thư viện hỗ trợ.

## 16. Checklist hoàn thành

- [ ] Giải thích được vấn đề method signature tham chiếu class vắng mặt trước khi method condition áp dụng.
- [ ] Phân biệt @ConditionalOnClass ở cấp configuration class và ở cấp @Bean method.
- [ ] Viết được static nested **@Configuration(proxyBeanMethods = false)** có **@ConditionalOnClass**.
- [ ] Giữ bean cốt lõi ở class ngoài, bean tùy chọn ở class lồng nhau.
- [ ] Dùng **@ConditionalOnMissingBean** để nhường quyền cho bean người dùng khi integration có mặt.
- [ ] Biết vì sao module autoconfigure dùng **compileOnly** cho API tùy chọn.
- [ ] Chạy pass kiểm thử context khi optional dependency có mặt và khi bị ẩn bằng FilteredClassLoader.
- [ ] Chạy pass kiểm thử back off khi ứng dụng định nghĩa bean riêng.
- [ ] Xác minh trong demo-app rằng thiếu optional-api vẫn có core bean mà không có optional bean.
- [ ] Thêm optional-api ở runtime và xác minh optional bean được tạo.
- [ ] Kiểm tra JAR và FQCN outer class trong AutoConfiguration.imports.
- [ ] Dùng dependency graph và Condition Evaluation Report để phân biệt lỗi classpath, discovery và bean condition.

## Kết luận

**Cô lập cấu hình cho dependency tùy chọn bằng lớp cấu hình lồng nhau** là kỹ thuật quan trọng khi viết Spring Boot auto-configuration cho thư viện tái sử dụng. Đặt **@ConditionalOnClass** ở cấp **static nested @Configuration**, giữ các phương thức @Bean có signature phụ thuộc type optional bên trong lớp này, và dùng **@ConditionalOnMissingBean** để cho phép ứng dụng thay thế mặc định.

Nhờ đó, ứng dụng không có thư viện optional vẫn có thể khởi động và dùng phần core, còn ứng dụng có thư viện đó sẽ nhận thêm bean khi điều kiện phù hợp. Bằng chứng đầy đủ gồm **test classloader thiếu dependency**, **test với dependency hiện diện**, **test custom bean**, **runtimeClasspath của consumer** và **resource imports trong JAR**.

## Tài liệu tham khảo

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot — ConditionalOnClass API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
