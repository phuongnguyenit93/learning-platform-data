# Kiểm tra tài nguyên đăng ký và các lớp triển khai trong JAR phân phối

## 1. Mục tiêu và phạm vi

Một thư viện Spring Boot có thể biên dịch thành công nhưng auto-configuration vẫn không được ứng dụng nhận ra. Nguyên nhân không nhất thiết nằm trong annotation hoặc logic bean: file đăng ký có thể bị thiếu khỏi JAR, sai đường dẫn, chứa tên class sai, bị ghi đè khi đóng gói nhiều dependency, hoặc class triển khai không nằm trong artifact/runtime classpath như dự kiến.

Khi kiểm tra một thư viện tự cấu hình, cần xác minh ít nhất bốn lớp bằng chứng:

1. **Tài nguyên đăng ký:** JAR phân phối có file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` và file liệt kê đúng auto-configuration class hay không?
2. **Class đã biên dịch:** các class được liệt kê và các implementation mà chúng tham chiếu có thực sự nằm trong JAR hoặc dependency runtime hay không?
3. **Cấu trúc artifact:** bạn đang kiểm tra plain library JAR, executable Spring Boot JAR có nested dependency JAR, hay shaded/uber JAR đã hợp nhất nội dung?
4. **Khả năng sử dụng thực tế:** một ứng dụng tiêu thụ đúng JAR phân phối có phát hiện auto-configuration và tạo được bean khi các condition khớp hay không?

Bài học dùng **Spring Boot 3.3.13, Java 17+ và Maven** để minh họa. Các lệnh kiểm tra JAR dùng công cụ `jar` đi kèm JDK; một số ví dụ PowerShell được cung cấp cho Windows. Gradle và cách đóng gói shaded JAR cũng được đề cập.

**Nguyên tắc:** nhìn thấy file/class trong `target/classes` chỉ chứng minh kết quả biên dịch trong workspace. Phải kiểm tra artifact đã đóng gói và một ứng dụng tiêu thụ artifact đó mới xác nhận được đường phân phối.

## 2. Tài nguyên đăng ký auto-configuration trong Spring Boot 3

### 2.1. Đường dẫn bắt buộc

Spring Boot 3 tìm danh sách auto-configuration trong resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Đây là file văn bản UTF-8, mỗi dòng chứa **tên lớp đầy đủ (fully qualified class name)** của một auto-configuration. Ví dụ:

```text
# Auto-configurations provided by the Acme Greeting library
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
com.acme.greeting.autoconfigure.GreetingWebAutoConfiguration
```

Các quy tắc cần nhớ:

- Tên class phải khớp package và tên lớp đã biên dịch.
- Mỗi class nằm trên một dòng riêng; có thể dùng `#` cho comment.
- Nếu auto-configuration là nested class, dùng ký tự `$` giữa lớp bao ngoài và lớp lồng, ví dụ `com.acme.Outer$NestedAutoConfiguration`.
- Auto-configuration phải được nạp bằng cách khai báo trong imports file. Đặt class vào package được component scan không phải cơ chế đăng ký được khuyến nghị.
- Auto-configuration không nên bật `@ComponentScan` để tự quét thêm component. Dùng `@Import` cho những cấu hình cụ thể cần thiết.
- Một imports file có thể liệt kê nhiều auto-configuration; không cần tạo một file cho mỗi class.

### 2.2. Class được đăng ký phải là auto-configuration hợp lệ

Ví dụ:

```java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.DefaultGreetingService;
import com.acme.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
```

Đây là class minh họa sẽ được đóng gói trong JAR mẫu ở mục 6. Khi kiểm tra artifact, cần xác minh cả:

- `GreetingAutoConfiguration.class` tồn tại.
- `GreetingService.class` và `DefaultGreetingService.class` tồn tại trong JAR hoặc dependency mà auto-configuration cần.
- Imports file có đúng tên `com.acme.greeting.autoconfigure.GreetingAutoConfiguration`.
- Các condition và bean method có thể được Spring xử lý khi ứng dụng tiêu thụ JAR.

**Đừng nhầm đăng ký với điều kiện kích hoạt:** imports file đưa lớp vào tập ứng viên; `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` và các condition khác vẫn có thể khiến cấu hình không được áp dụng. Vì vậy, thấy class trong imports file chưa chứng minh bean đã xuất hiện.

### 2.3. Tên nested class và tên binary

Nếu imports file khai báo nested auto-configuration:

```java
@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class WebConfiguration {
    }
}
```

Tên binary của lớp lồng là `com.acme.AcmeAutoConfiguration$WebConfiguration`, không phải `com.acme.AcmeAutoConfiguration.WebConfiguration`. Tuy nhiên, nested configuration được import bởi lớp auto-configuration thường không cần liệt kê thành một auto-configuration candidate riêng. Chỉ liệt kê class nào thực sự được thiết kế làm entry point auto-configuration.

Khi kiểm tra bằng `jar tf`, đường dẫn class dùng dấu `/` và phần nested class vẫn dùng `$`, ví dụ:

```text
com/acme/AcmeAutoConfiguration.class
com/acme/AcmeAutoConfiguration$WebConfiguration.class
```

## 3. Các resource META-INF khác và mục đích của chúng

Một JAR Spring Boot có thể chứa nhiều file metadata. Chúng không thay thế lẫn nhau.

| Resource | Mục đích | Có phải danh sách đăng ký auto-configuration không? |
| --- | --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Liệt kê các auto-configuration candidate | **Có** |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements` | Ánh xạ class auto-configuration cũ sang class thay thế khi đổi package/tên | Không; hỗ trợ thay thế/di trú |
| `META-INF/spring-autoconfigure-metadata.properties` | Metadata condition do annotation processor tạo để Boot lọc sớm những auto-configuration không phù hợp, cải thiện startup | Không; hỗ trợ tối ưu |
| `META-INF/spring-configuration-metadata.json` | Metadata cấu hình để IDE gợi ý property, kiểu, mô tả và giá trị mặc định | Không; hỗ trợ cấu hình/IDE |
| `META-INF/spring.factories` | Đăng ký một số factory/extension point khác theo key tương ứng | Không còn là nơi đăng ký `EnableAutoConfiguration` trong Boot 3 |

### 3.1. spring-autoconfigure-metadata.properties là tùy chọn

Spring Boot có annotation processor `spring-boot-autoconfigure-processor` để thu thập condition metadata. Nếu file `META-INF/spring-autoconfigure-metadata.properties` được tạo, Boot có thể dùng metadata đó để **eagerly filter** các auto-configuration không khớp trước khi xử lý đầy đủ, giúp cải thiện thời gian khởi động.

Điều cần phân biệt:

- `AutoConfiguration.imports` là danh sách candidate.
- `spring-autoconfigure-metadata.properties` là metadata hỗ trợ lọc candidate sớm.
- Không có file metadata này **không đồng nghĩa** imports file không được đọc hoặc auto-configuration không thể chạy.
- Khi build thư viện, cấu hình annotation processor theo hướng dẫn Spring Boot để tạo metadata; sau đó kiểm tra xem resource có được đưa vào JAR không.

### 3.2. spring-configuration-metadata.json phục vụ property metadata

Nếu thư viện có `@ConfigurationProperties`, annotation processor tương ứng có thể tạo:

```text
META-INF/spring-configuration-metadata.json
```

File này hỗ trợ IDE hiển thị gợi ý property và mô tả. Nó không liệt kê auto-configuration class. Khi một IDE không gợi ý property, hãy kiểm tra file này và `spring-boot-configuration-processor`; khi auto-configuration không được phát hiện, hãy kiểm tra `AutoConfiguration.imports` trước.

### 3.3. spring.factories và thay đổi từ Spring Boot 2.7/3.0

Trước đây, auto-configuration thường được đăng ký trong `META-INF/spring.factories` dưới key:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

Spring Boot 2.7 giới thiệu imports file mới và vẫn hỗ trợ cơ chế cũ để tương thích. Spring Boot 3 đã loại bỏ việc đăng ký auto-configuration qua key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `spring.factories`; các key `spring.factories` khác vẫn có thể được dùng cho extension point tương ứng.

Vì vậy:

- Với thư viện chỉ nhắm Spring Boot 3.x, đăng ký auto-configuration trong `AutoConfiguration.imports`.
- Nếu thư viện cần hỗ trợ cả Spring Boot 2.7 và 3.x, có thể cần giữ đăng ký ở cả hai vị trí theo hướng dẫn migration; Boot 2.7 khử trùng lặp các entry xuất hiện ở cả hai.
- Không xóa toàn bộ `spring.factories` chỉ vì chuyển auto-configuration sang imports file. File đó có thể còn đăng ký `FailureAnalyzer`, `ApplicationListener` hoặc extension point khác.
- Kiểm tra đúng version Spring Boot mà thư viện công bố hỗ trợ trước khi kết luận resource cũ không còn cần thiết.

### 3.4. AutoConfiguration.replacements khi đổi tên class

Nếu đổi package hoặc tên một auto-configuration class đã được thư viện phát hành, class cũ có thể được tham chiếu từ `before`, `after`, `exclude` hoặc cấu hình bên ngoài. Spring Boot hỗ trợ resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
```

Ví dụ:

```text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration=com.acme.greeting.autoconfigure.core.GreetingAutoConfiguration
```

Imports file cần cập nhật để chỉ tham chiếu class thay thế. Resource replacements giúp Boot xử lý các tham chiếu đến tên cũ trong các ngữ cảnh được hỗ trợ; nó không thay thế imports file và không tự làm class mới được đăng ký nếu imports file thiếu class đó.

## 4. Kiểm tra artifact: plain library JAR và executable Boot JAR

### 4.1. Plain library JAR

Một JAR thư viện Maven/Gradle thông thường thường có dạng:

```text
greeting-autoconfigure-1.0.0.jar
├── META-INF/
│   ├── MANIFEST.MF
│   ├── spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── spring-autoconfigure-metadata.properties
└── com/
    └── acme/
        └── greeting/
            ├── GreetingService.class
            ├── DefaultGreetingService.class
            └── autoconfigure/
                └── GreetingAutoConfiguration.class
```

Đây là dạng ví dụ; file metadata có thể không tồn tại nếu processor không tạo ra. Khi mở plain JAR, resource và class nằm trực tiếp ở root của archive.

### 4.2. Executable Spring Boot JAR

Một executable JAR được plugin Spring Boot repackage có cấu trúc khác:

```text
consumer-app-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/consumer/ConsumerApplication.class
    └── lib/
        ├── spring-boot-autoconfigure-3.3.13.jar
        ├── spring-boot-starter-3.3.13.jar
        └── greeting-autoconfigure-1.0.0.jar
```

Trong executable JAR:

- Class của ứng dụng nằm dưới `BOOT-INF/classes/`.
- Dependency JAR nằm nguyên dạng lồng bên trong `BOOT-INF/lib/`.
- `AutoConfiguration.imports` của thư viện có thể nằm **bên trong nested JAR** `BOOT-INF/lib/greeting-autoconfigure-1.0.0.jar`, chứ không nằm trực tiếp ở root executable JAR.
- Vì thế, tìm không thấy imports file ở root của executable JAR không đủ để kết luận thư viện bị đóng gói thiếu. Phải tìm và kiểm tra nested JAR.

**Phân biệt cấu trúc đóng gói:** `jar tf app.jar` chỉ liệt kê entry của archive bên ngoài. Nó không tự bung nội dung các nested JAR để hiển thị từng class/resource bên trong chúng.

### 4.3. Shaded/uber JAR

Maven Shade hoặc Gradle Shadow có thể hợp nhất class và resource từ nhiều JAR thành một archive. Khi nhiều dependency cùng chứa một resource có cùng đường dẫn, ví dụ nhiều file `AutoConfiguration.imports`, plugin đóng gói phải **append/merge** nội dung theo đúng cách.

Nếu một resource bị ghi đè bởi file của dependency khác, một số auto-configuration có thể biến mất khỏi JAR cuối dù JAR nguồn riêng lẻ đều đúng. Khi dùng Shade/Shadow, cần cấu hình transformer/append cho imports file; không mặc định rằng mọi resource cùng tên sẽ tự được hợp nhất.

## 5. Quy trình kiểm tra JAR bằng JDK

Các bước dưới đây áp dụng cho plain library JAR ở mục 6.

### 5.1. Build artifact từ source

Trong thư mục module thư viện:

```bash
mvn clean package
```

Maven tạo JAR trong `target/`. Kiểm tra đúng artifact/version đang định phát hành, tránh mở nhầm JAR cũ còn sót lại từ lần build trước. `clean` loại output cũ trước khi đóng gói.

Nếu muốn ứng dụng khác dùng artifact qua local Maven repository:

```bash
mvn clean install
```

`install` cài artifact vừa build vào local repository. Đây là bước cần thiết cho ví dụ consumer độc lập ở mục 6.

### 5.2. Liệt kê toàn bộ entry

```bash
jar tf target/greeting-autoconfigure-1.0.0.jar
```

Lọc những entry quan trọng trên Windows PowerShell:

```powershell
jar tf target/greeting-autoconfigure-1.0.0.jar |
    Select-String 'AutoConfiguration.imports|GreetingAutoConfiguration.class|GreetingService.class|DefaultGreetingService.class|spring-autoconfigure-metadata'
```

Hoặc dùng `findstr` trong Windows Command Prompt:

```bat
jar tf target\greeting-autoconfigure-1.0.0.jar | findstr /i "AutoConfiguration.imports GreetingAutoConfiguration.class GreetingService.class DefaultGreetingService.class spring-autoconfigure-metadata"
```

Các entry quan trọng kỳ vọng có mặt:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
com/acme/greeting/GreetingService.class
com/acme/greeting/DefaultGreetingService.class
com/acme/greeting/autoconfigure/GreetingAutoConfiguration.class
```

Nếu đã cấu hình annotation processor, có thể còn:

```text
META-INF/spring-autoconfigure-metadata.properties
```

Thứ tự entry trong JAR không phải giao ước; chỉ cần các entry cần thiết tồn tại.

### 5.3. Đọc nội dung imports file từ JAR

Có thể bung riêng resource bằng JDK `jar`. Trên PowerShell, từ thư mục module:

```powershell
New-Item -ItemType Directory -Force target\inspect | Out-Null
Push-Location target\inspect
jar xf ..\greeting-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
Get-Content META-INF\spring\org.springframework.boot.autoconfigure.AutoConfiguration.imports
Pop-Location
```

Kết quả mong đợi:

```text
# Acme Greeting auto-configuration
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

Trên macOS/Linux, nếu đã có `unzip`, có thể đọc trực tiếp mà không bung ra thư mục:

```bash
unzip -p target/greeting-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Đối chiếu tên class trong file với package/class đã biên dịch. Kiểm tra cả chữ hoa/thường, dấu chấm, ký tự `$` nếu có nested class và khoảng trắng ngoài ý muốn.

### 5.4. Xác minh class triển khai bằng javap

`javap` là công cụ JDK để đọc chữ ký và bytecode của class đã biên dịch. Ví dụ:

```bash
javap -classpath target/greeting-autoconfigure-1.0.0.jar -p com.acme.greeting.autoconfigure.GreetingAutoConfiguration
javap -classpath target/greeting-autoconfigure-1.0.0.jar -p com.acme.greeting.GreetingService
javap -classpath target/greeting-autoconfigure-1.0.0.jar -p -c com.acme.greeting.DefaultGreetingService
```

Ý nghĩa:

- `-p`: hiển thị cả member không public.
- `-c`: hiển thị bytecode của method.
- `-v`: hiển thị thông tin chi tiết hơn, bao gồm annotation/constant pool khi cần.

Ví dụ xem annotation trên auto-configuration:

```bash
javap -classpath target/greeting-autoconfigure-1.0.0.jar -v com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

`javap` không phải decompiler tạo lại source Java nguyên bản. Nếu cần đọc source, tìm `-sources.jar` tương ứng và xác nhận version/class khớp với binary đang kiểm tra. Với nested class, dùng tên binary có `$`, ví dụ:

```powershell
javap -classpath target\greeting-autoconfigure-1.0.0.jar -p 'com.acme.AcmeAutoConfiguration$WebConfiguration'
```

### 5.5. Kiểm tra dependency JAR riêng

Plain library JAR thường **không nhúng toàn bộ dependency** của nó. Nếu `GreetingAutoConfiguration` tham chiếu class thuộc artifact khác, hãy kiểm dependency graph:

```bash
mvn dependency:tree
```

Hoặc lọc artifact quan tâm:

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-autoconfigure
```

Một class có thể không nằm trong `greeting-autoconfigure-1.0.0.jar` nhưng vẫn hợp lệ nếu được cung cấp bởi dependency runtime. Ngược lại, một class có trong compile classpath nhưng dependency bị đánh dấu sai scope hoặc bị loại khỏi runtime có thể gây lỗi khi ứng dụng chạy. Kiểm đúng scope/configuration và artifact được triển khai.

## 6. Ví dụ hoàn chỉnh: build thư viện và kiểm tra từ ứng dụng tiêu thụ JAR

Ví dụ có **hai Maven project độc lập**. Project `greeting-autoconfigure` tạo thư viện JAR. Project `consumer` cài dependency đó từ local Maven repository và khởi động Spring Boot để chứng minh imports file trong JAR được phát hiện.

### 6.1. Cấu trúc thư mục

```text
jar-inspection-demo/
├── greeting-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/acme/greeting/
│       │   ├── GreetingService.java
│       │   ├── DefaultGreetingService.java
│       │   └── autoconfigure/GreetingAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── consumer/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/consumer/ConsumerApplication.java
        └── test/java/com/example/consumer/GreetingPackagingTests.java
```

### 6.2. Project greeting-autoconfigure/pom.xml

```xml
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

    <groupId>com.acme</groupId>
    <artifactId>greeting-autoconfigure</artifactId>
    <version>1.0.0</version>
    <name>greeting-autoconfigure</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Processor tạo `META-INF/spring-autoconfigure-metadata.properties` khi có metadata condition phù hợp. Nếu chỉ muốn kiểm imports file, resource registration vẫn là thành phần chính cần kiểm.

### 6.3. Interface GreetingService.java

Đường dẫn `src/main/java/com/acme/greeting/GreetingService.java`:

```java
package com.acme.greeting;

public interface GreetingService {
    String greet(String name);
}
```

### 6.4. Implementation DefaultGreetingService.java

Đường dẫn `src/main/java/com/acme/greeting/DefaultGreetingService.java`:

```java
package com.acme.greeting;

public final class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

### 6.5. Auto-configuration GreetingAutoConfiguration.java

Đường dẫn `src/main/java/com/acme/greeting/autoconfigure/GreetingAutoConfiguration.java`:

```java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.DefaultGreetingService;
import com.acme.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
```

Auto-configuration có hai nhóm điều kiện:

- Class `GreetingService` phải hiện diện trên classpath.
- Property `acme.greeting.enabled` phải là `true`.
- Nếu ứng dụng đã khai báo bean `GreetingService`, bean mặc định sẽ back off.

### 6.6. Resource đăng ký

Tạo file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung:

```text
# Acme Greeting auto-configuration
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

Tên trong file phải khớp chính xác với package/class đã biên dịch ở mục 6.5.

### 6.7. Consumer project consumer/pom.xml

```xml
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

    <groupId>com.example</groupId>
    <artifactId>consumer</artifactId>
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
            <groupId>com.acme</groupId>
            <artifactId>greeting-autoconfigure</artifactId>
            <version>1.0.0</version>
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

Vì consumer kế thừa `spring-boot-starter-parent`, cần khai báo `spring-boot-maven-plugin` trong `build/plugins`; parent đã cấu hình execution `repackage` cho plugin nên không cần lặp lại goal trong ví dụ này. Xem [Spring Boot 3.3 Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html).

Hai project độc lập để consumer giải quyết artifact đã cài trong local Maven repository. Không đặt chúng trong cùng Maven reactor nếu mục tiêu của bài thực hành là xác minh JAR đã đóng gói được consumer sử dụng.

### 6.8. ConsumerApplication.java

Đường dẫn `src/main/java/com/example/consumer/ConsumerApplication.java`:

```java
package com.example.consumer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }
}
```

Package ứng dụng là `com.example.consumer`; auto-configuration nằm ở `com.acme.greeting.autoconfigure`. Component scan mặc định của ứng dụng không quét package thư viện; auto-configuration được phát hiện qua imports file.

### 6.9. Test kiểm tra resource và bean từ JAR

Đường dẫn `src/test/java/com/example/consumer/GreetingPackagingTests.java`:

```java
package com.example.consumer;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;

import com.acme.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = ConsumerApplication.class,
    properties = "acme.greeting.enabled=true"
)
class GreetingPackagingTests {

    private static final String IMPORTS_RESOURCE =
        "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

    private static final String AUTO_CONFIGURATION =
        "com.acme.greeting.autoconfigure.GreetingAutoConfiguration";

    @Autowired
    private GreetingService greetingService;

    @Test
    void autoConfigurationIsDiscoveredFromDependencyJar() {
        assertThat(greetingService).isNotNull();
        assertThat(greetingService.getClass().getName())
            .isEqualTo("com.acme.greeting.DefaultGreetingService");
        assertThat(greetingService.greet("Ada"))
            .isEqualTo("Hello, Ada");
    }

    @Test
    void importsResourceContainsAutoConfigurationClass() throws IOException {
        ClassLoader classLoader =
            Thread.currentThread().getContextClassLoader();

        Enumeration<URL> resources =
            classLoader.getResources(IMPORTS_RESOURCE);

        List<URL> locations = Collections.list(resources);
        assertThat(locations).isNotEmpty();

        boolean found = false;

        for (URL location : locations) {
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                        location.openStream(),
                        StandardCharsets.UTF_8
                    ))) {

                if (reader.lines()
                        .map(String::trim)
                        .anyMatch(AUTO_CONFIGURATION::equals)) {
                    found = true;
                    break;
                }
            }
        }

        assertThat(found).isTrue();
    }
}
```

Hai test kiểm tra hai bằng chứng khác nhau:

1. **Resource hiện diện:** class loader tìm thấy ít nhất một imports resource và có entry đúng tên auto-configuration.
2. **Discovery thực tế:** Spring Boot khởi động context consumer, tạo bean từ auto-configuration và gọi được implementation.

Việc duyệt tất cả URL resource là có chủ ý: nhiều JAR dependency có thể cùng cung cấp file `AutoConfiguration.imports`. Không giả định class loader chỉ tìm được một resource.

### 6.10. Build và chạy kiểm thử theo đúng thứ tự

Đầu tiên, build và cài JAR thư viện:

```bash
cd greeting-autoconfigure
mvn clean install
```

Tiếp theo, chạy consumer trong thư mục project riêng:

```bash
cd ../consumer
mvn clean test
```

Kết quả mong đợi: Maven `BUILD SUCCESS`, hai test của `GreetingPackagingTests` đều pass. Nếu test không tìm thấy bean hoặc resource, hãy kiểm tra JAR đã cài trong local repository, dependency tree và nội dung imports file trong artifact.

Sau test, đóng gói consumer thành executable Boot JAR:

```bash
mvn package
```

Kiểm tra dependency đã được đóng gói:

```bash
jar tf target/consumer-1.0.0.jar
```

Trên Windows có thể lọc entry:

```powershell
jar tf target\consumer-1.0.0.jar |
    Select-String 'BOOT-INF/lib/greeting-autoconfigure|BOOT-INF/classes'
```

Bạn sẽ thấy nested dependency có tên gần như:

```text
BOOT-INF/lib/greeting-autoconfigure-1.0.0.jar
```

Để kiểm tra imports file bên trong nested dependency:

```powershell
New-Item -ItemType Directory -Force target\inspect | Out-Null
Push-Location target\inspect
jar xf ..\consumer-1.0.0.jar BOOT-INF/lib/greeting-autoconfigure-1.0.0.jar
jar tf BOOT-INF/lib/greeting-autoconfigure-1.0.0.jar
Pop-Location
```

Sau đó dùng quy trình ở mục 5.3 để bung resource từ nested JAR. Như vậy bạn đã kiểm tra cả **plain library JAR** và **JAR ứng dụng cuối cùng**.

## 7. Kiểm tra JAR khi đóng gói nhiều thư viện

### 7.1. Vấn đề trùng đường dẫn resource

Giả sử hai dependency cùng chứa:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nếu plugin shade chỉ giữ một file mà không merge nội dung, entry của dependency còn lại có thể mất. Class của cả hai thư viện vẫn có thể tồn tại trong JAR nhưng auto-configuration của một thư viện không được đăng ký.

Đây là lỗi đặc biệt dễ gặp khi chuyển từ các JAR lồng riêng biệt sang **một shaded/uber JAR**.

### 7.2. Maven Shade Plugin: append imports resource

Với Maven Shade Plugin, dùng `AppendingTransformer` cho imports file:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
```

Nếu ứng dụng cũng đóng gói management context auto-configuration, xem xét append resource tương ứng theo hướng dẫn Spring Boot. Đừng chỉ cấu hình cho một file khi artifact còn hợp nhất resource đăng ký khác.

### 7.3. Gradle Shadow Plugin: append imports resource

Ví dụ Groovy DSL theo hướng dẫn Spring Boot 2.7:

```groovy
tasks.withType(ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
}
```

Cấu hình chính xác có thể phụ thuộc version plugin và cách dự án tổ chức task. Kiểm tra tài liệu Shadow Plugin của version đang dùng, sau đó kiểm tra JAR kết quả bằng `jar tf` và đọc nội dung imports file.

### 7.4. Không áp dụng merge nhầm cho executable Boot JAR thông thường

Spring Boot executable JAR thông thường giữ dependency dưới dạng nested JAR trong `BOOT-INF/lib`; các imports resource của dependency vẫn nằm trong từng nested archive. Trường hợp này khác shaded JAR đã flatten các dependency vào một archive.

Vì vậy, trước khi thêm transformer, hãy xác định loại artifact:

- **Plain library JAR:** resource nằm trong library JAR.
- **Executable Boot JAR:** resource thường nằm trong nested dependency JAR.
- **Shaded/uber JAR:** resource trùng đường dẫn phải được merge/append.

## 8. Quy trình chẩn đoán khi auto-configuration không được phát hiện

Đi theo thứ tự từ artifact tới runtime để tìm đúng nguyên nhân.

### 8.1. Imports file có nằm trong JAR phân phối không?

- Kiểm tra `target/classes/META-INF/spring/...` sau compile/process-resources.
- Chạy `jar tf` trên đúng JAR release.
- Bung và đọc nội dung imports file.
- Xác nhận tên class là FQCN chính xác.
- Nếu là nested class, xác nhận ký tự `$`.
- Nếu là shaded JAR, kiểm tra mọi entry đã được append/merge.

Nếu resource thiếu, kiểm tra source resource path, cấu hình `resources`, `excludes`, `filtering`, plugin đóng gói và artifact đang kiểm tra.

### 8.2. Class được liệt kê có nằm trong runtime classpath không?

Với mỗi class trong imports file:

- Xác nhận class tương ứng có trong JAR.
- Nếu class thuộc dependency khác, kiểm `mvn dependency:tree` hoặc Gradle `runtimeClasspath`.
- Kiểm scope/configuration: compile-only/provided/test không tự bảo đảm có mặt lúc ứng dụng chạy.
- Nếu JAR consumer có nested dependency, kiểm tra nested JAR thực sự được đóng gói.
- Nếu class optional, bảo đảm condition và cấu trúc cấu hình không buộc JVM tải class thiếu quá sớm.

Không cần mọi implementation class phải nằm trong cùng auto-config JAR; chúng có thể thuộc dependency riêng. Điều cần xác nhận là tất cả dependency bắt buộc có mặt ở runtime khi feature được bật.

### 8.3. Imports entry đúng nhưng condition không khớp?

Sau khi xác nhận resource và class:

- Kiểm tra `@ConditionalOnClass`/`@ConditionalOnMissingClass`.
- Kiểm tra `@ConditionalOnBean`/`@ConditionalOnMissingBean`.
- Kiểm tra property qua `@ConditionalOnProperty`.
- Kiểm tra `@ConditionalOnWebApplication` nếu cấu hình phụ thuộc loại context.
- Kiểm tra auto-configuration có bị exclude qua annotation hoặc `spring.autoconfigure.exclude` không.
- Dùng `--debug` hoặc `ConditionEvaluationReport` để xem lý do matched/unmatched.

Imports file chỉ xác định candidate; condition vẫn quyết định có áp dụng cấu hình hay không.

### 8.4. Class có trong JAR nhưng bean vẫn không có?

Một số nguyên nhân:

- Class không được liệt kê trong imports file.
- Imports file bị ghi đè trong shaded JAR.
- Một condition không khớp.
- Người dùng đã cung cấp bean khiến `@ConditionalOnMissingBean` back off.
- Auto-configuration không được đưa vào context vì ứng dụng chưa bật `@EnableAutoConfiguration`/`@SpringBootApplication`.
- Class được component scan theo đường khác hoặc bị đăng ký sai cách.
- Bean method không được xử lý do lỗi cấu hình, linkage hoặc dependency khởi tạo.

Hãy tách kết luận theo ba tầng: **resource candidate**, **condition outcome**, **bean registration/creation**.

### 8.5. Kiểm tra artifact thực sự được ứng dụng sử dụng

Có thể build đúng JAR nhưng consumer vẫn dùng version cũ từ repository/cache hoặc một dependency khác. Hãy kiểm:

```bash
mvn dependency:tree -Dincludes=com.acme:greeting-autoconfigure
```

Đối chiếu version trong cây dependency với artifact bạn vừa cài/phát hành. Nếu cần, kiểm manifest, checksum hoặc vị trí JAR trong executable app. Không suy ra runtime đã dùng artifact mới chỉ từ việc `mvn package` của thư viện thành công.

## 9. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Đặt file trong `META-INF/AutoConfiguration.imports` | Sai đường dẫn resource | Dùng chính xác `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Ghi tên bean thay vì tên class | Imports file cần FQCN của auto-configuration | Ghi `com.acme...MyAutoConfiguration` |
| Ghi tên nested class với dấu chấm | Tên binary của nested class dùng `$` | Dùng `Outer$Nested` |
| Class tồn tại trong `target/classes` nhưng thiếu trong JAR | Resource/class có thể bị loại ở packaging | Kiểm `jar tf` trên artifact release |
| Chỉ kiểm outer executable JAR | Dependency JAR nằm trong `BOOT-INF/lib` | Extract nested JAR rồi kiểm tiếp |
| Shaded JAR chỉ giữ một imports file | Resource trùng path bị ghi đè | Dùng AppendingTransformer/Shadow `append` |
| Dùng `spring.factories` key EnableAutoConfiguration trên Boot 3 | Cơ chế đăng ký đó đã bị loại bỏ | Chuyển sang `AutoConfiguration.imports` |
| Xóa toàn bộ `spring.factories` | Các key factory khác vẫn có thể cần thiết | Chỉ chuyển key đăng ký auto-configuration; giữ entry khác |
| Tưởng `spring-autoconfigure-metadata.properties` là file bắt buộc | Đây là metadata tối ưu, không phải danh sách candidate | Kiểm imports file trước; cấu hình processor để tạo metadata khi cần |
| Tưởng `spring-configuration-metadata.json` đăng ký auto-configuration | File này mô tả configuration properties cho IDE | Phân biệt resource property metadata với imports file |
| Imports entry đúng nhưng condition false | Candidate không đồng nghĩa cấu hình được áp dụng | Đọc condition report và property/classpath/bean |
| Chỉ kiểm class name bằng `javap` | `javap` không chứng minh Boot đã import cấu hình | Chạy consumer integration test với artifact đã đóng gói |
| Consumer test chạy trong cùng reactor và dùng `target/classes` | Có thể chưa kiểm đúng JAR đã publish | Dùng consumer project riêng, phụ thuộc artifact đã `install` |
| Kiểm nhầm version JAR trong local repository | Consumer có thể dùng artifact cũ | Kiểm dependency tree và version thực tế |

## 10. Checklist phát hành thư viện auto-configuration

Trước khi phát hành starter/library, xác nhận:

- [ ] Auto-configuration class có `@AutoConfiguration` và package phù hợp.
- [ ] Imports file đúng đường dẫn và liệt kê đủ FQCN.
- [ ] Tên class trong imports file trùng class binary; nested class dùng `$`.
- [ ] Các class implementation và dependency cần thiết có mặt trên runtime classpath.
- [ ] Condition class/property/bean/web được kiểm thử cho cả match và no-match.
- [ ] `spring-boot-autoconfigure-processor` được cấu hình nếu cần condition metadata.
- [ ] `spring-configuration-metadata.json` được tạo nếu thư viện cung cấp `@ConfigurationProperties` và cần IDE metadata.
- [ ] Nếu đổi tên auto-configuration đã phát hành, đã cân nhắc `AutoConfiguration.replacements`.
- [ ] Không component-scan auto-configuration package; dùng imports file và `@Import` cụ thể.
- [ ] JAR release được kiểm bằng `jar tf`, đọc imports file và kiểm class.
- [ ] Nếu tạo shaded JAR, imports resource được append/merge.
- [ ] Consumer project độc lập đã kiểm thử discovery từ artifact đã `install`/publish.
- [ ] Executable Boot JAR cuối cùng đã được kiểm tra cả nested `BOOT-INF/lib`.
- [ ] Dependency tree và version artifact được consumer sử dụng đã được xác nhận.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Trong Spring Boot 3.3, resource nào liệt kê auto-configuration candidate?  
**Đáp án:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Mỗi dòng là FQCN của một auto-configuration.

**Câu 2.** Imports file có entry đúng và class tồn tại. Điều đó có đảm bảo bean được tạo không?  
**Đáp án:** Không. Class mới là candidate; các condition, exclude và quá trình đăng ký/khởi tạo bean vẫn quyết định kết quả.

**Câu 3.** Class lồng `Outer.NestedAutoConfiguration` được ghi thế nào trong imports file?  
**Đáp án:** Dùng tên binary với `$`: `Outer$NestedAutoConfiguration`.

**Câu 4.** `spring-autoconfigure-metadata.properties` có thay thế `AutoConfiguration.imports` không?  
**Đáp án:** Không. Imports file liệt kê candidate; metadata hỗ trợ lọc condition sớm và cải thiện startup.

**Câu 5.** Vì sao `jar tf app.jar` không hiện trực tiếp imports file của dependency trong executable Boot JAR?  
**Đáp án:** Dependency được giữ thành nested JAR dưới `BOOT-INF/lib`; cần extract nested JAR rồi kiểm tra nội dung bên trong.

**Câu 6.** Vì sao shaded JAR cần append imports resource?  
**Đáp án:** Nhiều dependency có thể chứa resource cùng đường dẫn; nếu file bị ghi đè thì entry của một số auto-configuration sẽ mất.

**Câu 7.** Spring Boot 3 còn đọc key `EnableAutoConfiguration` trong `spring.factories` để đăng ký auto-configuration không?  
**Đáp án:** Không. Boot 3 yêu cầu imports file cho auto-configuration; những key `spring.factories` khác vẫn có thể được dùng.

**Câu 8.** Làm sao chứng minh JAR đã phát hành được ứng dụng khác phát hiện?  
**Đáp án:** Build/install JAR thư viện, tạo consumer project độc lập phụ thuộc đúng artifact, khởi động context với `@SpringBootApplication` và assert bean do auto-configuration cung cấp; đồng thời kiểm imports resource trong classloader.

## 12. Ghi nhớ và tài liệu tham khảo

- **Imports file** là điểm đăng ký candidate: đúng path, đúng FQCN, đúng nội dung.
- **Class file** là implementation đã biên dịch; kiểm tra bằng `jar tf` và `javap`.
- **Dependency graph** quyết định những class ngoài thư viện có mặt lúc chạy.
- **Condition report và consumer test** xác nhận candidate có được áp dụng và bean có thực sự xuất hiện.
- **Plain JAR, executable Boot JAR và shaded JAR** có cấu trúc khác nhau; phải kiểm tra đúng tầng archive.
- Với Boot 3, dùng `AutoConfiguration.imports`; `spring.factories` vẫn có thể chứa các factory entry khác.
- Test artifact đã đóng gói trong consumer project riêng là bằng chứng mạnh hơn việc chỉ test source trong module thư viện.

Tài liệu chính thức:

1. Spring Boot 3.3.13 — [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html), mục *Locating Auto-configuration Candidates*, *The autoconfigure Module* và *Testing your Auto-configuration*.
2. Spring Boot 3.3.13 — [AutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html).
3. Spring Boot 3.3.13 — [AutoConfigurationImportSelector Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html).
4. Spring Boot 3.0 — [Migration Guide: Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide), thay đổi đăng ký từ `spring.factories` sang imports file.
5. Spring Boot 2.7 — [Release Notes: Auto-configuration Registration and Shade/Shadow configuration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes).
6. Apache Maven — [Maven Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html).
7. Java 17 — [The jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) và [javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
