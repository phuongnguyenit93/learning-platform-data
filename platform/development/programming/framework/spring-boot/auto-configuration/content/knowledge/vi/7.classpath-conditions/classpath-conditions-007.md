# Cô lập chữ ký phương thức và mã triển khai phụ thuộc thư viện tùy chọn

## 1. Vấn đề thực sự: thư viện tùy chọn vắng mặt nhưng JVM vẫn có thể phải đọc chữ ký phương thức

Khi xây dựng **Spring Boot auto-configuration**, một thư viện thường muốn bật tích hợp chỉ nếu một dependency bên ngoài hiện diện. Ví dụ một starter có thể tích hợp với SDK gửi thông báo, driver dữ liệu hoặc client của hệ thống khác. Ứng dụng không dùng tích hợp ấy **không nên buộc phải mang theo SDK tùy chọn**, cũng không nên bị lỗi khởi động khi SDK không có trên runtime classpath.

Spring Boot có **@ConditionalOnClass** để chọn cấu hình theo sự hiện diện của lớp. Tuy nhiên, có một rủi ro ít hiển nhiên: **đặt @ConditionalOnClass ngay trên phương thức @Bean mà chữ ký trả về hoặc tham số của nó tham chiếu lớp vắng mặt không phải là cách cô lập an toàn nhất**. Spring hoặc JVM có thể cần nạp/phân tích class chứa các phương thức đó, đọc method metadata, kiểu trả về, tham số hoặc annotation trước khi điều kiện ở mức phương thức bảo vệ được chỗ tham chiếu nguy hiểm.

Ví dụ có rủi ro khi SDK không tồn tại:

~~~java
// Minh họa RỦI RO; không đưa class này vào ứng dụng chạy demo.
@AutoConfiguration
class RiskyAutoConfiguration {

    @Bean
    @ConditionalOnClass(ExternalClient.class)
    ExternalClient externalClient() {
        return new ExternalClient("auto");
    }
}
~~~

Đoạn mã này giả định **ExternalClient** nằm trong thư viện tùy chọn. Vấn đề không phải Java không thể compile: lúc **compile**, dự án auto-config có thể có dependency SDK. Vấn đề xuất hiện **lúc chạy**, khi SDK không có trên classpath của ứng dụng sử dụng starter. Trong quá trình introspection, việc truy cập method signature hoặc liên kết lớp có thể dẫn đến **NoClassDefFoundError**, **TypeNotPresentException** hay lỗi đọc metadata liên quan. Tùy cơ chế/phiên bản/framework, đoạn code có thể tình cờ hoạt động, nhưng không nên dựa vào điều đó làm contract của thư viện.

**Giải pháp được khuyến nghị:** đặt toàn bộ **@Bean method có chữ ký và triển khai phụ thuộc SDK** vào một lớp **@Configuration tách biệt** (thường là một lớp **static nested configuration**) và gắn **@ConditionalOnClass** lên **lớp cấu hình bao bọc đoạn code phụ thuộc**, để Spring quyết định có nhập lớp cấu hình đó hay không **trước khi cần phản chiếu các method phụ thuộc của nó**.

Tư duy cần nhớ:

- **Ứng viên** auto-configuration ở lớp ngoài nên có thể được xử lý khi thư viện tùy chọn vắng mặt.
- **Điều kiện classpath** nằm trên ranh giới cấu hình con.
- **Chữ ký @Bean và logic new/call SDK** chỉ xuất hiện bên trong cấu hình con đã được bảo vệ.
- **Runtime dependency** có thể vắng mặt, nhưng ứng dụng và các auto-configuration khác vẫn khởi động bình thường.

## 2. Phân biệt compile-time dependency và runtime classpath

Có hai thời điểm khác nhau:

| Thời điểm | SDK tùy chọn có cần thiết? | Tại sao? |
| --- | --- | --- |
| Biên dịch module auto-configuration | Có, nếu source trực tiếp import kiểu SDK | Java compiler phải phân giải kiểu dùng ở chữ ký/mã triển khai |
| Chạy ứng dụng không dùng integration | Không nên bắt buộc | Tính năng phải tự rút lui khi kiểu SDK không hiện diện |
| Chạy ứng dụng có dùng integration | Có | Bean cần kiểu SDK và class triển khai thực sự |
| Chạy unit test chỉ xét negative classpath | Cần môi trường thật sự loại SDK khỏi runtime | Có SDK trên test classpath sẽ không kiểm tra được trường hợp vắng mặt |
| Đóng gói starter phổ biến | Dependency tùy chọn không nên tự kéo vào mọi app | Tách thư viện hoặc dùng tùy chọn phụ thuộc phù hợp với build tool |

**Maven optional dependency** có ý nghĩa ở bước lan truyền dependency: module auto-configuration vẫn có dependency để **biên dịch**, nhưng dependency được đánh dấu **optional=true** không tự trở thành dependency bắc cầu bắt buộc đối với consumer. Ứng dụng muốn dùng integration phải khai báo SDK trực tiếp hoặc thông qua một starter feature riêng được thiết kế như vậy.

Trong Gradle, cấu trúc dependency và cách công bố variant khác Maven. Không dịch máy móc **optional=true** thành một cấu hình Gradle cùng tên; phải kiểm tra API/implementation/compileOnly/runtimeOnly và metadata publishing của hệ sinh thái Gradle.

### 2.1. Ba khả năng phải kiểm tra độc lập

1. **Class có mặt không?** Có thể kiểm tra tên class trên classpath khi xây context.
2. **Auto-configuration được chọn không?** Còn phụ thuộc imports metadata, exclusions, property và điều kiện khác.
3. **Bean đã được đăng ký/khởi tạo không?** Chịu điều kiện method, bean người dùng, dependency và lifecycle.

**@ConditionalOnClass** chỉ trả lời một phần của câu 1. Nó không chứng minh SDK đã cấu hình endpoint/token, kết nối có thể thành công, hoặc feature luôn tạo được bean.

## 3. JVM linkage: vì sao method signature là ranh giới quan trọng?

Xét một class chứa:

~~~java
import dev.demo.optionalapi.ExternalClient;

public class MixedConfiguration {
    public ExternalClient create(ExternalClient client) {
        return client;
    }
}
~~~

Đây chỉ là snippet Java; **ExternalClient** thuộc một artifact khác. Method descriptor trong bytecode liên quan đến kiểu **dev.demo.optionalapi.ExternalClient**. Nếu class ấy không có ở runtime, việc Java/Spring cần liên kết, phản chiếu hoặc phân giải một số thành phần của **MixedConfiguration** có thể gặp lỗi.

Không nên đơn giản hóa thành “JVM luôn nạp tất cả class được nhắc đến ngay khi nạp class chính”: **thời điểm resolution khác nhau theo thao tác, implementation và JVM**. Nhưng cũng **không** được kết luận “nếu chưa gọi create() thì mọi chữ ký chứa kiểu vắng mặt đều an toàn”. Chỉ cần framework dùng reflection như **getDeclaredMethods()**, đọc return/parameter types hoặc xử lý metadata ở một giai đoạn không thích hợp, lỗi vẫn có thể xuất hiện trước khi logic trong method thực thi.

Các vị trí dễ tạo phụ thuộc classpath:

- **Kiểu trả về** trực tiếp của @Bean method.
- **Kiểu tham số** của @Bean method, constructor hoặc một số factory method.
- **Superclass/interface** hoặc field của class bị load.
- **Annotation attribute có Class literal** và annotation/metadata mà framework hoặc reflection cố resolve.
- **Tham chiếu đến class SDK trong static initializer**, field initializer hay code được gọi quá sớm.
- **Generic signature**, method exception type hoặc kiểu lồng nhau có thể bị công cụ reflection xử lý.
- **Mã triển khai** sử dụng new, cast, invoke API SDK khi một nhánh được thực thi.

Không phải tất cả vị trí trên đều phát sinh cùng một lỗi, và không phải mọi kiểu tham chiếu đều bị resolve ngay lập tức. Nguyên tắc thiết kế là **đừng để class bắt buộc phải xử lý khi SDK vắng mặt mang những chữ ký/mã khởi tạo phụ thuộc SDK**.

## 4. Vì sao class-level @ConditionalOnClass an toàn hơn method-level?

Spring Boot hỗ trợ tối ưu đọc metadata annotation, trong đó class-level condition như **@ConditionalOnClass** có thể được đánh giá dựa trên metadata của class cấu hình (thông qua cơ chế đọc metadata bytecode) trước khi Spring phải nạp toàn bộ các method bean phụ thuộc SDK.

Một thiết kế theo mẫu:

~~~java
@AutoConfiguration
public class ExternalIntegrationAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "dev.demo.optionalapi.ExternalClient")
    static class ExternalClientConfiguration {

        @Bean
        ExternalClient externalClient() {
            return new ExternalClient("auto");
        }
    }
}
~~~

**Snippet này rút gọn**, chưa có import statements và định nghĩa ExternalClient. Nó minh họa ranh giới quan trọng:

1. **ExternalIntegrationAutoConfiguration** không để method signature hoặc field của chính lớp ngoài tham chiếu trực tiếp SDK.
2. Cấu hình con là **static nested @Configuration**, có class-level guard **@ConditionalOnClass**.
3. **externalClient()** trả kiểu SDK trực tiếp nhưng nằm trong lớp cấu hình con chỉ nên được xử lý sau khi guard đạt.
4. Có thể dùng thuộc tính **name** để kiểm tra theo fully qualified class name mà không cần class literal trong annotation guard.

Đối với **@ConditionalOnClass** gắn trực tiếp trên class @Configuration hoặc auto-configuration, dùng **value=ExternalClient.class** cũng có thể an toàn trong đường Spring Boot đọc metadata. Dùng **name="..."** đặc biệt tiện khi muốn tránh tham chiếu class literal ngay trên annotation bảo vệ hoặc khi dependency thực sự tùy chọn ở compile time. Trong ví dụ này, source của nested class vẫn phải compile với SDK, nên module vẫn khai báo dependency compile-time.

**Không kết luận rằng đổi value sang name trên một @Bean method là đủ.** Vấn đề của ví dụ rủi ro không chỉ ở annotation value mà còn ở **chữ ký method**. Ranh giới phải được đưa lên **lớp cấu hình riêng**, để framework có thể loại cả class trước khi introspect method phụ thuộc.

### 4.1. Vì sao dùng static nested @Configuration?

Một nested class **static** không cần reference đến instance của cấu hình ngoài. Nó dễ được xem như đơn vị cấu hình riêng, có @ConditionalOnClass ở đúng ranh giới và ít mang phụ thuộc vào enclosing instance. Spring Boot thường dùng các nested configuration để nhóm những bean cần thêm classpath dependency.

Bạn cũng có thể dùng một **top-level @Configuration class** riêng được bảo vệ bằng condition và chỉ import khi phù hợp. Điều quan trọng không phải từ khóa nested mà là **tách biệt class Spring cần đọc trong nhánh không có dependency** với class chứa những method phụ thuộc dependency.

Đừng đặt logic khởi tạo SDK trong static initializer hoặc constructor của lớp ngoài rồi kỳ vọng condition trên lớp con sẽ bảo vệ. Lớp ngoài vẫn có thể được load khi SDK vắng mặt.

### 4.2. Condition chưa bảo đảm tính đúng của bean

Ngay cả khi ExternalClient có mặt trên classpath, bean có thể bị bỏ qua vì property, có bean do người dùng khai báo trước, cấu hình bị exclude hoặc condition khác không đạt. Nếu bean được đăng ký, factory method vẫn có thể thất bại do cấu hình kết nối sai hoặc API SDK không tương thích.

**Classpath presence khác dependency compatibility.** Ví dụ có class **ExternalClient** ở runtime nhưng version SDK thiếu một method mà integration đang gọi; trong tình huống đó, **@ConditionalOnClass** có thể đạt nhưng mã vẫn phát sinh **NoSuchMethodError**, **NoSuchFieldError** hoặc lỗi linkage khác. Cần dependency/version alignment và test matrix, không chỉ kiểm tra tên class.

## 5. Pattern khuyến nghị cho thư viện Spring Boot

Giả sử thư viện tích hợp với API **ExternalClient** tùy chọn. Một thiết kế gọn:

~~~text
IntegrationAutoConfiguration
  - @AutoConfiguration
  - Không chứa chữ ký method tham chiếu ExternalClient
  |
  +-- ExternalClientBeans (static @Configuration)
         - @ConditionalOnClass(name = "...")
         - @ConditionalOnProperty(...)
         - @Bean ExternalClient externalClient()
         - @ConditionalOnMissingBean(ExternalClient.class)
~~~

Luồng xử lý:

~~~text
Ứng dụng bật @EnableAutoConfiguration
              |
              v
AutoConfiguration.imports liệt kê cấu hình ngoài
              |
              v
ExternalIntegrationAutoConfiguration được xét
              |
              v
Nested ExternalClientBeans có guard classpath
         /                      \
SDK thiếu                        SDK có
   |                              |
Bỏ nested config             Xét property và bean
   |                              |
KHÔNG introspect bean        Đọc chữ ký và method
method phụ thuộc SDK           dùng SDK
   |                              |
Không cần SDK tại runtime    Có thể đăng ký bean
~~~

Sơ đồ rút gọn các bước thực thi; điều cần thiết là **guard ở cấp configuration class trước khi cần xử lý chữ ký phụ thuộc SDK**.

### 5.1. Đặt condition vào đúng ranh giới

Nên phân biệt:

- **@ConditionalOnClass**: bao quanh lớp cấu hình có mã tùy chọn.
- **@ConditionalOnProperty**: bật/tắt tính năng theo cấu hình.
- **@ConditionalOnMissingBean**: cho phép user cung cấp bean thay cho mặc định.
- **@AutoConfiguration(before/after)**: thứ tự cấu hình nếu có phụ thuộc đến các auto-config khác, không tạo ra dependency tùy chọn.
- **exclude/excludeName** hoặc **spring.autoconfigure.exclude**: loại auto-configuration được chọn, không tự xóa mọi import/registration độc lập.

Tại cấp nested configuration, bạn có thể dùng đồng thời class guard và property guard. Nhưng **condition không phải runtime feature flag**: chúng quyết định bean definitions khi context được xây, không theo dõi SDK/JAR mới xuất hiện sau startup.

## 6. Demo Maven reactor: thực sự chạy khi SDK có và không có trên runtime classpath

Để thực hành đúng nghĩa “optional”, demo không chỉ giả lập property mà **đóng gói hai ứng dụng có runtime dependencies khác nhau từ cùng source**:

- Build mặc định: auto-configuration có mặt, nhưng **optional-api không nằm trong ứng dụng**, do Maven đánh dấu dependency optional ở module auto-config. Kết quả cần là **khởi động thành công và không tạo bean tích hợp**.
- Build bật Maven profile **with-api**: ứng dụng khai báo **optional-api** trực tiếp, nên class có trên runtime classpath; nested configuration đạt condition và tạo bean.
- Khi class có mặt, **--demo.external.enabled=false** làm bean mặc định không được đăng ký.
- Khi class có mặt, **spring.autoconfigure.exclude** có thể tắt toàn bộ ExternalIntegrationAutoConfiguration.

Ví dụ dùng **JDK 21**, **Maven 3.9+** và **Spring Boot 3.3.13**. Không cần web server và không kết nối tới SDK thật. **ExternalClient** là lớp giả lập nằm trong artifact tùy chọn riêng để kiểm tra chuyện thiếu class một cách an toàn và có thể lặp lại.

### 6.1. Cấu trúc toàn bộ project

~~~text
optional-isolation/
├── pom.xml
├── optional-api/
│   ├── pom.xml
│   └── src/main/java/dev/demo/optionalapi/
│       └── ExternalClient.java
├── starter-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/dev/demo/autoconfig/
│       │   └── ExternalIntegrationAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── demo-app/
    ├── pom.xml
    └── src/main/
        ├── java/dev/demo/app/DemoApplication.java
        └── resources/application.properties
~~~

Có ba Maven modules:

| Module | Vai trò | Phụ thuộc quan trọng |
| --- | --- | --- |
| **optional-api** | Định nghĩa kiểu ExternalClient giả lập | Chỉ JDK |
| **starter-autoconfigure** | Compile auto-config và nested config có kiểu ExternalClient | spring-boot-autoconfigure, optional-api với optional=true |
| **demo-app** | Consumer dùng auto-configuration | spring-boot-starter, starter-autoconfigure; tùy profile mới có optional-api |

Để giữ bài dễ đọc, tên **starter-autoconfigure** biểu thị một JAR autoconfiguration; nó không giả vờ có module starter dependencies riêng. Trong dự án phát hành thật, có thể tách thêm artifact “starter” tùy theo yêu cầu phân phối.

### 6.2. Parent pom.xml

**optional-isolation/pom.xml**

~~~xml
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
    <groupId>dev.demo</groupId>
    <artifactId>optional-isolation-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>optional-api</module>
        <module>starter-autoconfigure</module>
        <module>demo-app</module>
    </modules>

    <properties>
        <java.version>21</java.version>
    </properties>
</project>
~~~

### 6.3. Module optional-api

**optional-isolation/optional-api/pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.demo</groupId>
        <artifactId>optional-isolation-parent</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>optional-api</artifactId>
</project>
~~~

**optional-isolation/optional-api/src/main/java/dev/demo/optionalapi/ExternalClient.java**

~~~java
package dev.demo.optionalapi;

public final class ExternalClient {
    private final String source;

    public ExternalClient(String source) {
        this.source = source;
    }

    @Override
    public String toString() {
        return "client:" + source;
    }
}
~~~

ExternalClient là kiểu tùy chọn giả lập. Đặc biệt, **demo-app không import ExternalClient** trong source, nên ứng dụng biên dịch và chạy được khi JAR này bị bỏ khỏi runtime.

### 6.4. Module starter-autoconfigure khai báo SDK là optional

**optional-isolation/starter-autoconfigure/pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.demo</groupId>
        <artifactId>optional-isolation-parent</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>starter-autoconfigure</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>dev.demo</groupId>
            <artifactId>optional-api</artifactId>
            <version>1.0.0</version>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
~~~

Dòng **optional=true** là điều quan trọng: compiler vẫn nhìn thấy ExternalClient trong module autoconfigure, nhưng Maven không tự kéo **optional-api** bắc cầu vào **demo-app** qua dependency starter-autoconfigure. Đây là cách tạo một runtime không có SDK mà không phải sửa code.

### 6.5. Auto-configuration cô lập chữ ký và implementation SDK

**optional-isolation/starter-autoconfigure/src/main/java/dev/demo/autoconfig/ExternalIntegrationAutoConfiguration.java**

~~~java
package dev.demo.autoconfig;

import dev.demo.optionalapi.ExternalClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class ExternalIntegrationAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "dev.demo.optionalapi.ExternalClient")
    @ConditionalOnProperty(
        prefix = "demo.external",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    static class ExternalClientBeans {

        @Bean
        @ConditionalOnMissingBean(ExternalClient.class)
        ExternalClient externalClient() {
            return new ExternalClient("auto");
        }
    }
}
~~~

Đây là **file Java đầy đủ** cho module autoconfigure ở project demo.

Phân tích an toàn classpath:

1. Lớp ngoài **ExternalIntegrationAutoConfiguration** được Boot import qua file imports. Nó **không có @Bean method, field hoặc superclass phụ thuộc ExternalClient**; class này có thể được xử lý dù optional-api không nằm ở runtime.
2. Nested class **ExternalClientBeans** được Spring phát hiện như một nested configuration. **@ConditionalOnClass(name = "...")** gắn ở cấp nested configuration.
3. Spring dùng metadata condition để **loại nested configuration khi ExternalClient vắng**; do đó không phải introspect @Bean method mang chữ ký ExternalClient ở nhánh không có SDK.
4. Khi ExternalClient tồn tại, Spring có thể xử lý method **externalClient()**; **@ConditionalOnMissingBean(ExternalClient.class)** cho phép bean mặc định nhường chỗ cho bean cùng kiểu do ứng dụng khai báo.
5. **@ConditionalOnProperty** minh họa một điều kiện khác: có class nhưng property tắt thì vẫn không đăng ký bean.
6. Không đặt **new ExternalClient(...)** trong static initializer hoặc constructor của lớp ngoài. Logic dùng SDK nằm bên trong cấu hình đã được bảo vệ.

**Tại sao vẫn có import Java của ExternalClient ở đầu source file?** Câu lệnh import của Java là cú pháp ở bước biên dịch, không phải một lời gọi runtime tự load class khi ứng dụng đọc source. Bytecode của lớp ngoài không cần method signature trả kiểu đó. Kiểu ExternalClient được dùng trong nested class riêng, và nested class có guard trên metadata. Điều quan trọng không phải vị trí dòng import trong source, mà là **đường class loading và phạm vi các tham chiếu trong bytecode**.

### 6.6. Đăng ký class ngoài trong AutoConfiguration.imports

**optional-isolation/starter-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.demo.autoconfig.ExternalIntegrationAutoConfiguration
~~~

Chỉ liệt kê lớp **ExternalIntegrationAutoConfiguration**. Không liệt kê nested class là một auto-configuration ứng viên độc lập. Boot 3.x sẽ đọc file này khi **@EnableAutoConfiguration** được kích hoạt bởi ứng dụng.

Cơ chế chọn auto-configuration của Boot là khác với component scanning. Trong bài demo, package của lớp autoconfig đứng ngoài vùng scan của lớp chính và được nạp qua file imports.

### 6.7. Module demo-app với Maven profile bổ sung SDK

**optional-isolation/demo-app/pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.demo</groupId>
        <artifactId>optional-isolation-parent</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>demo-app</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>dev.demo</groupId>
            <artifactId>starter-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>

    <profiles>
        <profile>
            <id>with-api</id>
            <dependencies>
                <dependency>
                    <groupId>dev.demo</groupId>
                    <artifactId>optional-api</artifactId>
                    <version>1.0.0</version>
                </dependency>
            </dependencies>
        </profile>
    </profiles>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không có profile **with-api**, demo-app chỉ phụ thuộc trực tiếp vào starter-autoconfigure; SDK đã được đánh dấu optional ở module kia nên không trở thành runtime dependency bắc cầu. Bật **-Pwith-api** thì demo-app khai báo SDK trực tiếp, class hiện diện và điều kiện có thể đạt.

### 6.8. Ứng dụng không import SDK trong chữ ký

**optional-isolation/demo-app/src/main/java/dev/demo/app/DemoApplication.java**

~~~java
package dev.demo.app;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showSelection(ApplicationContext context) {
        return args -> {
            boolean classPresent = ClassUtils.isPresent(
                "dev.demo.optionalapi.ExternalClient",
                DemoApplication.class.getClassLoader());
            boolean beanPresent = context.containsBean("externalClient");

            System.out.println("api.present=" + classPresent);
            System.out.println("client.present=" + beanPresent);
            System.out.println("client.value=" +
                (beanPresent
                    ? context.getBean("externalClient").toString()
                    : "none"));
        };
    }
}
~~~

Lớp ứng dụng cố ý **không tham chiếu trực tiếp ExternalClient** trong kiểu trả về, tham số hoặc variable declaration. Nó kiểm tra sự hiện diện class bằng tên chuỗi qua **ClassUtils.isPresent** và chỉ lấy bean bằng tên nếu bean đã được đăng ký. Nhờ vậy một consumer không cần SDK vẫn chạy an toàn.

**optional-isolation/demo-app/src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

Các thuộc tính trên chỉ làm gọn output. Khi cần chẩn đoán, hãy bật lại log ở phần debug.

### 6.9. Xây và chạy không có SDK tùy chọn

Mở terminal tại thư mục gốc **optional-isolation**. Yêu cầu JDK 21, Maven 3.9+ và dependency đã tải được từ kho Maven:

~~~bash
mvn -q -pl demo-app -am -DskipTests package
java -jar demo-app/target/demo-app-1.0.0.jar
~~~

Các dòng do ApplicationRunner in:

~~~text
api.present=false
client.present=false
client.value=none
~~~

Lý do:

- Module starter-autoconfigure đã được compile với kiểu ExternalClient, nhưng dependency optional không đi bắc cầu vào ứng dụng.
- Nested **ExternalClientBeans** bị bỏ qua vì class-level @ConditionalOnClass không đạt.
- Không xảy ra lỗi phải reflect method **ExternalClient externalClient()** trong nhánh bị loại.
- Ứng dụng vẫn có ApplicationContext bình thường và không có bean **externalClient**.

**Đây là kiểm thử quan trọng nhất của bài:** không chỉ property false, mà **class SDK thực sự vắng mặt tại runtime**.

### 6.10. Xây và chạy có SDK

Từ thư mục gốc, build lại với profile **with-api**:

~~~bash
mvn -q -Pwith-api -pl demo-app -am -DskipTests package
java -jar demo-app/target/demo-app-1.0.0.jar
~~~

Các dòng stdout dự kiến:

~~~text
api.present=true
client.present=true
client.value=client:auto
~~~

Bây giờ optional-api được demo-app khai báo trực tiếp, nested configuration đạt @ConditionalOnClass và property mặc định cho phép. Phương thức @Bean đăng ký ExternalClient; toString trả **client:auto**.

### 6.11. Có SDK nhưng tắt tính năng bằng property

Sau khi build với **-Pwith-api**, chạy:

~~~bash
java -jar demo-app/target/demo-app-1.0.0.jar --demo.external.enabled=false
~~~

Output:

~~~text
api.present=true
client.present=false
client.value=none
~~~

**@ConditionalOnClass vẫn đạt** vì class có mặt, nhưng **@ConditionalOnProperty** trên nested configuration không đạt. Tính năng không được tạo mặc dù SDK đã có trên classpath.

### 6.12. Có SDK nhưng exclude auto-configuration

Vẫn dùng JAR có SDK:

~~~bash
java -jar demo-app/target/demo-app-1.0.0.jar --spring.autoconfigure.exclude=dev.demo.autoconfig.ExternalIntegrationAutoConfiguration
~~~

Output:

~~~text
api.present=true
client.present=false
client.value=none
~~~

Khác với tắt property, tình huống này loại **ExternalIntegrationAutoConfiguration** khỏi đường chọn auto-config của Boot. SDK vẫn nằm trong JAR; việc có class không bắt buộc phải có bean.

### 6.13. Bảng kết quả thực hành

| Runtime SDK | Property feature | Auto-config có bị exclude? | Class hiện diện | Bean externalClient |
| --- | --- | --- | --- | --- |
| Không có | Mặc định | Không | false | false |
| Có | Mặc định | Không | true | true |
| Có | false | Không | true | false |
| Có | Mặc định | Có | true | false |

Cách nhận biết JAR có SDK hay không: với Spring Boot executable JAR, lệnh sau liệt kê các entries:

~~~bash
jar tf demo-app/target/demo-app-1.0.0.jar
~~~

Trong build có profile, danh sách thường có **BOOT-INF/lib/optional-api-1.0.0.jar**. Trong build mặc định, entry này không nên có. Đừng chỉ tin Maven log báo build thành công; hãy kiểm tra runtime dependency thực tế khi debug một starter có tùy chọn classpath.

**Giới hạn kiểm thử:** kết quả trên là stdout dự kiến suy từ source và cấu hình; không khẳng định Maven đã được chạy trong môi trường của người đọc. Một project thật cần chạy cả hai build và kiểm thử tích hợp trên các môi trường cần hỗ trợ.

## 7. Vì sao không chỉ đặt @ConditionalOnClass trên @Bean method?

Quay lại thiết kế rủi ro:

~~~java
@AutoConfiguration
class RiskyAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "dev.demo.optionalapi.ExternalClient")
    ExternalClient externalClient() {
        return new ExternalClient("auto");
    }
}
~~~

**Snippet minh họa điều cần tránh** và chưa có import/định nghĩa đầy đủ. Ta đã đổi class literal trong annotation thành tên chuỗi, nhưng **chữ ký return vẫn là ExternalClient**. Khi Spring/JVM phải introspect RiskyAutoConfiguration trước khi condition của method được đánh giá, kiểu vắng mặt có thể gây lỗi linkage. Đổi **name** không tự giải quyết ranh giới method signature.

So sánh:

| Thiết kế | SDK không có | Đánh giá |
| --- | --- | --- |
| @ConditionalOnClass đặt trên method trả kiểu SDK trong class luôn được xử lý | Có nguy cơ method introspection đụng kiểu vắng mặt | Không nên phụ thuộc vào khả năng may mắn hoạt động |
| Guard class-level ở chính auto-configuration và toàn bộ class chỉ dành cho SDK | Có thể an toàn khi metadata được xét trước khi class bị load | Phù hợp nếu cả auto-config chỉ có ý nghĩa khi SDK hiện diện |
| Guard class-level trên static nested configuration chứa mọi method SDK | Class ngoài có thể được xử lý; nested class bị bỏ qua khi SDK thiếu | Pattern linh hoạt, rõ ràng khi auto-config còn có các bean khác |
| Tách hẳn top-level @Configuration chứa SDK, được guard trước khi import | Có thể an toàn nếu ranh giới import/condition đúng | Phù hợp với cấu hình phức tạp |
| Đổi return type thành Object nhưng vẫn new SDK trong static initializer của class ngoài | Vẫn có nguy cơ linkage/side effect | Chưa cô lập đúng mã triển khai |
| Bọc mọi thứ bằng catch(NoClassDefFoundError) | Dễ che giấu lỗi version và khiến trạng thái context khó hiểu | Không phải cách thiết kế chủ đạo |

**Có thể dùng class-level @ConditionalOnClass trực tiếp trên một auto-configuration riêng** nếu toàn bộ lớp chỉ triển khai tích hợp đó và metadata được Boot xử lý an toàn. Nested configuration đặc biệt hữu ích khi lớp ngoài phải còn chạy với SDK vắng mặt, hoặc khi muốn các nhánh tính năng tùy chọn độc lập.

## 8. Ranh giới an toàn gồm cả chữ ký, field và hành vi khởi tạo

Không phải chỉ cần sửa return type là xong. Khi xác định class nào phải load trong trường hợp SDK không có, hãy kiểm tra:

1. **Superclass/interfaces** của class: kế thừa interface SDK tùy chọn trong class luôn phải load có thể nguy hiểm.
2. **Constructor signature** và method parameter types: Spring có thể phân tích chúng để autowire.
3. **Field types** và annotation attributes: một số cơ chế reflection có thể resolve kiểu.
4. **@Bean return type** và factory method: đặc biệt nhạy trong quá trình Spring tìm kiểu bean.
5. **Static fields/initializers**: code tạo SDK object ngay khi class initialization có thể lỗi trước khi guard được áp dụng.
6. **Mã gọi SDK trong bean factory**: chỉ thực thi khi nhánh condition thật sự được chọn; cần giữ nó trong class đã được guard.
7. **Annotation kết hợp**: nếu viết một annotation riêng meta-annotated với @ConditionalOnClass dùng **Class literal**, bảo đảm cách alias/metadata được xử lý phù hợp. Với composed annotation, dùng **name** thường được khuyến nghị để tránh vấn đề đọc class-valued annotation attribute trực tiếp.
8. **Method reference/lambda chứa SDK**: bản thân lambda không xóa phụ thuộc bytecode. Nếu SDK được resolve trước khi guard, rủi ro vẫn còn.

Mục tiêu là loại các **liên kết bắt buộc với class tùy chọn** khỏi những class mà framework chắc chắn phải nạp/phản chiếu trong nhánh SDK không có.

### 8.1. Không dùng lỗi linkage làm cơ chế phát hiện classpath

Một anti-pattern:

~~~java
try {
    // Thử new hoặc gọi SDK rồi chờ NoClassDefFoundError.
} catch (NoClassDefFoundError ex) {
    // Giả định mọi lỗi đều có nghĩa SDK không được cài.
}
~~~

Đây là pseudocode minh họa, không phải file Java độc lập. **NoClassDefFoundError** còn có thể do một **transitive dependency thiếu**, lỗi binary compatibility hoặc class initialization thất bại. Nuốt lỗi có thể che giấu vấn đề thực và biến một integration bị hỏng thành trạng thái fallback âm thầm.

Dùng **@ConditionalOnClass** để chọn nhánh, quản lý dependency versions và kiểm thử classpath là hướng chủ đạo. Trong runtime code, nếu cần optional discovery thực sự, chỉ dùng cơ chế reflection/API được thiết kế có chủ đích và xử lý lỗi rõ ràng.

### 8.2. @ConditionalOnClass không tự chứng minh ABI tương thích

SDK class có mặt nhưng phương thức bị đổi giữa phiên bản 1 và 2. Điều kiện classpath có thể pass vì **tên ExternalClient** vẫn đúng. Khi code thực thi method của version không tương thích, có thể phát sinh **NoSuchMethodError**, **IncompatibleClassChangeError** hoặc lỗi tương tự.

Các biện pháp:

- Khóa và kiểm tra version SDK được thư viện hỗ trợ.
- Dùng dependency management/BOM thích hợp.
- Chạy integration test trên runtime classpath của từng version mục tiêu.
- Nếu cần nhiều API version khác nhau, tách nhánh có điều kiện và mã triển khai theo version thay vì để một class luôn load cả hai API.

## 9. Thêm điều kiện khác nhưng vẫn giữ classpath isolation

Một feature có thể cần ba tầng điều kiện:

~~~java
@AutoConfiguration
public class MessagingAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.messaging.Client")
    @ConditionalOnProperty(
        prefix = "app.messaging",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    static class VendorClientConfiguration {
        // @Bean trả về com.vendor.messaging.Client.
        // @ConditionalOnMissingBean nếu hỗ trợ custom client.
    }
}
~~~

Đây là minh họa cấu trúc; vendor Client không có trong project demo. Cấu hình được xét theo thứ tự ý nghĩa:

1. Có class SDK cần thiết không?
2. Property có bật feature không?
3. Ứng dụng đã cung cấp bean phù hợp chưa?
4. Nếu cần tạo bean, factory method có được cấp đầy đủ properties/credentials/dependencies không?

Đừng kiểm tra classpath bằng **@ConditionalOnClass** rồi bỏ qua các giới hạn tính năng; một bean kết nối mạng còn cần URL, credentials, timeout và cơ chế fail-fast/fallback hợp lý.

## 10. Debug một lỗi chỉ xảy ra khi bỏ dependency tùy chọn

### 10.1. Nhận dạng stack trace

Một lỗi như:

~~~text
java.lang.NoClassDefFoundError: dev/demo/optionalapi/ExternalClient
~~~

có thể chỉ ra rằng một class cần thiết đã được resolve khi không có trên classpath. Nhưng để biết vì sao, phải xem toàn bộ stack trace: lỗi xuất hiện khi Spring introspect @Bean method, trong bean creation hay trong code gọi SDK?

Nếu stack trace có dấu hiệu **getDeclaredMethods**, **ReflectionUtils.getDeclaredMethods** hoặc phân tích cấu hình, hãy kiểm tra chữ ký method trong auto-configuration mà Spring phải đọc. Nếu lỗi xảy ra trong factory method sau khi condition đã match, hãy kiểm tra SDK và các dependency bắc cầu.

### 10.2. Từng bước chẩn đoán

1. **Nhận diện class vắng mặt** từ lỗi và tìm artifact cung cấp class đó.
2. **Kiểm tra JAR cuối**: artifact thực sự có mặt trong BOOT-INF/lib hoặc runtime classpath không? Đừng chỉ xem compile classpath của module auto-config.
3. **Kiểm tra outer configuration**: có @Bean return type, constructor parameter, field hoặc static initializer tham chiếu SDK không?
4. **Đặt class-level guard** trên cấu hình chứa toàn bộ chữ ký phụ thuộc SDK; có thể dùng static nested configuration.
5. **Xác minh AutoConfiguration.imports** chỉ công bố class ngoài đúng, tránh component-scan cả package auto-config.
6. **Kiểm tra Maven optional/Gradle publishing semantics**: dependency nào được truyền sang consumer?
7. **Kiểm tra điều kiện kết hợp**: @ConditionalOnProperty, @ConditionalOnMissingBean và exclusions.
8. **Chạy negative classpath test**: bảo đảm runtime **không có** SDK, ứng dụng vẫn khởi động.
9. **Chạy positive classpath test**: có SDK, bean tạo được và API tương thích.
10. **Chạy disable test**: SDK có mặt nhưng feature tắt, bean không xuất hiện.

### 10.3. Condition Evaluation Report giúp ở đâu?

Với JAR có hoặc không có SDK, có thể chạy:

~~~bash
java -jar demo-app/target/demo-app-1.0.0.jar --debug --logging.level.root=INFO
~~~

Tìm **ExternalIntegrationAutoConfiguration** và nested class **ExternalClientBeans**. Condition report cho thấy lý do classpath/property match hoặc không match. Một ứng viên bị bỏ qua vì thiếu SDK là **hành vi bình thường**, không phải lỗi.

**Condition Evaluation Report không chứng minh mọi class linkage đều an toàn**: nếu ứng dụng đã crash do NoClassDefFoundError trong giai đoạn introspection, stack trace mới là bằng chứng chính. Nếu SDK có mặt nhưng ABI sai, positive classpath match cũng không bảo đảm factory method tạo bean thành công.

### 10.4. Kiểm thử bằng context nhỏ và ClassLoader có kiểm soát

Spring Boot cung cấp **ApplicationContextRunner** và **FilteredClassLoader** trong bộ test utilities để viết kiểm thử auto-configuration:

- Positive test dùng runtime classpath có SDK và kiểm tra bean được tạo.
- Negative test dùng FilteredClassLoader/hoặc một artifact thực sự vắng dependency, đảm bảo auto-config có thể dựng context mà không chạm vào class SDK.
- Test property false và bean người dùng có sẵn.
- Test các version SDK mục tiêu.

Ví dụ ý tưởng, không phải JUnit file độc lập:

~~~java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(
            ExternalIntegrationAutoConfiguration.class))
    .withClassLoader(
        new FilteredClassLoader("dev.demo.optionalapi"))
    .run(context ->
        assertThat(context).doesNotHaveBean("externalClient"));
~~~

Để chạy ví dụ test trên cần dependency **spring-boot-starter-test** ở test scope, imports và lớp JUnit/test assertions đầy đủ. Trong một số cấu trúc, test có ClassLoader lọc cần đặc biệt lưu ý dữ liệu đã được load hoặc classloader khác. **Maven reactor demo ở mục 6** mới là kiểm chứng rõ ràng rằng **artifact tùy chọn thực sự không được đóng gói vào ứng dụng**.

## 11. Những hiểu nhầm cần tránh

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “Đã gắn @ConditionalOnClass trên @Bean method thì mọi chữ ký dùng SDK vắng mặt đều an toàn.” | Method signature có thể bị load/introspect trước khi condition ở method bảo vệ được nó; cô lập bằng class-level guard. |
| “Dùng name thay value tại method thì hết lỗi.” | name tránh class literal ở annotation nhưng không xóa kiểu SDK trong return/parameter types. |
| “Compile được tức là chạy được nếu bỏ dependency.” | Compile classpath khác runtime classpath; thiếu SDK có thể dẫn tới linkage error. |
| “Maven optional=true khiến module tự không nhìn thấy SDK khi compile.” | Module khai báo dependency vẫn có SDK để compile; optional chủ yếu kiểm soát transitive dependency. |
| “Class có mặt là bean sẽ được tạo.” | Còn imports metadata, exclusions, property, back off, bean lifecycle và dependency compatibility. |
| “Class không có thì @ConditionalOnClass sẽ tự bọc mọi new SDK bên ngoài.” | Guard phải bao được các class/chữ ký và code cần thiết. |
| “Nested static configuration là class được Boot đọc từ AutoConfiguration.imports.” | File imports công bố auto-config ngoài; nested configuration được xử lý theo cấu trúc config/condition của nó. |
| “Không gọi method thì chữ ký chứa kiểu vắng mặt chắc chắn không sao.” | Reflection và JVM type resolution có thể chạm vào chữ ký trước khi gọi method. |
| “Cứ bắt NoClassDefFoundError là hỗ trợ optional dependency.” | Có thể che giấu SDK phiên bản sai hay thiếu dependency bắc cầu. |
| “@ConditionalOnClass kiểm tra cả phương thức SDK đúng phiên bản.” | Nó kiểm tra class presence; cần version alignment và integration tests cho ABI. |
| “Property false có thể thay thế test classpath vắng mặt.” | Tắt property không chứng minh ứng dụng an toàn khi SDK JAR bị loại khỏi runtime. |
| “Chỉ dùng @ComponentScan để tìm mọi class auto-config.” | Boot 3.x dùng AutoConfiguration.imports và condition/ordering/exclusions chuyên biệt. |

## 12. Bài tập tự kiểm tra

**Câu 1.** Một @Bean method trả về kiểu **VendorClient**, có @ConditionalOnClass(VendorClient.class) trên chính method. Nếu vendor JAR không có, bạn có nên xem đây là ranh giới an toàn tuyệt đối?

**Đáp án:** Không. Reflection có thể phân giải method return type trước khi condition ở method được đánh giá. Nên đặt method trong một @Configuration riêng có class-level guard.

**Câu 2.** Vì sao đặt @ConditionalOnClass(name="...") trên static nested @Configuration lại hữu ích?

**Đáp án:** Spring có thể đọc metadata guard để bỏ qua nested class khi SDK vắng mặt, trước khi cần introspect các method tham chiếu SDK bên trong. Dùng name không đòi class literal trong annotation guard.

**Câu 3.** Maven module autoconfigure dùng dependency optional-api với optional=true. Nó có compile được method trả ExternalClient không?

**Đáp án:** Có. Module autoconfigure vẫn nhận dependency để compile. optional=true khiến dependency không tự được mang bắc cầu vào module app chỉ phụ thuộc autoconfigure.

**Câu 4.** Vì sao demo-app không cần import ExternalClient?

**Đáp án:** App chỉ kiểm tra class bằng tên chuỗi và bean bằng tên. Nó không có chữ ký hoặc mã compile-time phụ thuộc SDK, nên bản build mặc định có thể chạy khi SDK không nằm trong runtime classpath.

**Câu 5.** Có SDK, nhưng --demo.external.enabled=false; bean externalClient xuất hiện không?

**Đáp án:** Không qua auto-config này. Class condition đạt, nhưng property condition ở nested configuration không đạt.

**Câu 6.** Có SDK và property true, nhưng SDK version cũ thiếu method auto-config gọi; @ConditionalOnClass bảo đảm an toàn không?

**Đáp án:** Không. Nó không kiểm tra đầy đủ binary compatibility. Cần dependency management và test version thực tế.

**Câu 7.** Nếu chỉ cần một tích hợp tách biệt và không có cấu hình nào khác trong outer class, có thể dùng class-level @ConditionalOnClass trên toàn bộ auto-config không?

**Đáp án:** Có thể. Class-level guard của Spring Boot có thể được đánh giá từ metadata trước khi class bị load; nested config vẫn là lựa chọn linh hoạt hơn khi outer class có thêm các nhánh không phụ thuộc SDK.

**Câu 8.** Vì sao chỉ chạy test với property=false chưa đủ chứng minh optional dependency đúng?

**Đáp án:** Vì SDK vẫn có thể hiện diện trên classpath và che giấu lỗi linkage của chữ ký. Phải kiểm thử tối thiểu một lần với runtime thật sự không có SDK.

## 13. Checklist phát triển một auto-configuration dùng SDK tùy chọn

Trước khi phát hành thư viện:

1. **Xác nhận auto-config ngoài có thể được xử lý khi SDK vắng mặt.** Không để outer class bắt buộc load SDK ở superclass, method signature hoặc static initializer.
2. **Tạo lớp @Configuration cô lập**, thường là static nested config, cho các @Bean method trả/tham chiếu kiểu SDK.
3. **Đặt @ConditionalOnClass ở cấp cấu hình cô lập**, bằng Class literal hoặc name phù hợp; cân nhắc name trong composed annotations và các tình huống optional.
4. **Kết hợp property và @ConditionalOnMissingBean** nếu feature cần bật/tắt hoặc hỗ trợ user override.
5. **Công bố đúng auto-config candidate** bằng resource AutoConfiguration.imports của Spring Boot 3.x.
6. **Khai báo dependency để compile nhưng không bắt consumer mang SDK khi không cần**; với Maven kiểm tra optional/transitive dependency và runtime fat JAR.
7. **Thử runtime thiếu SDK thật**, không chỉ dùng giả lập property hoặc test classpath vẫn có SDK.
8. **Thử runtime có SDK** và kiểm tra bean tạo được, output/method tương thích.
9. **Thử version matrix** để phát hiện NoSuchMethodError, ClassNotFoundException/NoClassDefFoundError hoặc lỗi phụ thuộc bắc cầu.
10. **Đọc stack trace khi lỗi linkage**, phân biệt lỗi lúc introspect cấu hình, lúc tạo bean và lúc sử dụng SDK.
11. **Không nuốt linkage errors như một fallback thông thường**; để diagnostic rõ khi binary dependency sai.
12. **Giữ consumer không phụ thuộc vào kiểu optional nếu feature có thể vắng mặt**; dùng abstraction chung hoặc đặt mã consumer tùy chọn vào module được bảo vệ tương tự.

### Kết luận

**Cô lập chữ ký phương thức và mã triển khai dùng thư viện tùy chọn là yêu cầu thiết kế quan trọng của Spring Boot auto-configuration.** Không chỉ cần một annotation kiểm tra classpath; bạn còn cần bố trí lớp sao cho Spring/JVM **không bắt buộc phân giải các kiểu SDK vắng mặt trước khi condition ở cấp cấu hình có cơ hội bỏ qua nhánh đó**.

Mẫu thực tế là **auto-configuration ngoài không phụ thuộc trực tiếp vào SDK + một @Configuration con có @ConditionalOnClass + các @Bean dùng kiểu SDK chỉ nằm bên trong cấu hình được bảo vệ**. Ghép với dependency optional đúng nghĩa, kiểm thử có và không có JAR, và quản lý phiên bản API, thư viện sẽ hoạt động ổn định hơn trong những ứng dụng không chọn tích hợp đó.

### Tài liệu tham khảo

- Spring Boot, *Creating Your Own Auto-configuration*, mục Class Conditions: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot API, **@ConditionalOnClass**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Framework, *Conditionally Including @Configuration Classes*: https://docs.spring.io/spring-framework/reference/core/beans/java/conditional.html
- Maven, *Optional Dependencies and Dependency Exclusions*: https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html
