# Tên lớp đầy đủ, mỗi dòng một ứng viên và quy tắc chú thích trong AutoConfiguration.imports

## 1. Mục đích của tệp imports trong Spring Boot

Trong Spring Boot 3.x, thư viện có thể công bố các lớp **auto-configuration ứng viên** để ứng dụng sử dụng thư viện được Spring Boot tự phát hiện. Danh sách ứng viên nằm ở một tài nguyên văn bản có **đường dẫn và tên tệp cố định** trên classpath:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Tệp này có thể nằm trong thư mục **src/main/resources** khi viết thư viện; sau khi đóng gói, nó phải xuất hiện đúng đường dẫn trên trong JAR. Khi ứng dụng khởi động và bật auto-configuration, Spring Boot thu thập những tài nguyên imports tương ứng có mặt trên classpath, đọc các tên lớp ứng viên và xử lý chúng như cấu hình tự động.

**Ba quy tắc cốt lõi của nội dung tệp:**

1. **Mỗi dòng cấu hình là một tên lớp đầy đủ** (*fully qualified class name*, viết tắt FQCN), bao gồm package và tên lớp Java.
2. **Mỗi dòng chỉ khai báo một ứng viên**, không gom nhiều tên lớp bằng dấu phẩy, dấu chấm phẩy hoặc ký pháp YAML/JSON.
3. **Dòng bắt đầu bằng ký tự # là chú thích**; dòng trống dùng để phân tách cho dễ đọc. Chú thích nên để riêng trên một dòng với ký tự **#** ở đầu dòng; không dùng chú thích cuối dòng theo kiểu **TênLớp # giải thích**.

Tệp imports trả lời câu hỏi **“Spring Boot nên xét những lớp auto-configuration nào?”**. Nó không đảm bảo mọi lớp trong danh sách đều tạo bean: điều kiện trên class, phương thức **@Bean** và môi trường ứng dụng vẫn được Spring đánh giá trước khi quyết định đăng ký bean.

## 2. Tên lớp đầy đủ (FQCN) là gì?

Trong Java, tên lớp đầy đủ gồm **package + dấu chấm + tên lớp**, ví dụ:

~~~java
package com.example.greeting.autoconfigure;

public class GreetingAutoConfiguration {
}
~~~

FQCN của class trên là:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

So sánh:

| Cách viết | Dùng làm một dòng imports? | Lý do |
| --- | --- | --- |
| **com.example.greeting.autoconfigure.GreetingAutoConfiguration** | Có | Đầy đủ package và tên lớp. |
| **GreetingAutoConfiguration** | Không | Chỉ có simple class name; Boot không thể suy ra package. |
| **com.example.greeting.autoconfigure** | Không | Chỉ là package, không phải class. |
| **com.example.greeting.autoconfigure.\*** | Không | Imports không chấp nhận wildcard package scanning. |
| **com.example.greeting.autoconfigure.GreetingAutoConfiguration.class** | Không | Đây là ký pháp gần với class literal trong Java, không phải FQCN của class. |
| **@AutoConfiguration(GreetingAutoConfiguration.class)** | Không | Đây không phải cú pháp của tệp imports. |

**FQCN phải khớp chính xác class đã biên dịch.** Nếu đổi tên hoặc chuyển package của class thì phải cập nhật dòng imports. Một sai lệch một ký tự có thể khiến việc import ứng viên thất bại khi Boot cố nạp cấu hình.

Với **lớp lồng nhau** được đăng ký làm ứng viên, phải dùng tên binary tương ứng; trong trường hợp nested class thông thường, dấu **$** ngăn giữa outer và inner class, ví dụ **com.example.autoconfig.Outer$Nested**. Để tránh nhầm và làm package rõ ràng, một thư viện mới thường thuận tiện hơn khi mỗi lớp auto-configuration công khai là một top-level class.

## 3. Một dòng tương ứng một ứng viên

Một thư viện có thể cung cấp nhiều auto-configuration. Mỗi class được liệt kê trên **một dòng riêng**, ví dụ:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

Các dòng trên công bố **hai ứng viên độc lập**. Trong quá trình khởi động, Spring Boot có thể áp dụng cả hai, chỉ một hoặc không ứng viên nào, tùy điều kiện của từng cấu hình. Việc cả hai được liệt kê không chứng minh các bean của chúng tồn tại.

### Những cách viết sai cần nhận diện

**Sai — ngăn cách bằng dấu phẩy:**

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration,com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

Đây vẫn là **một dòng**, không phải hai class hợp lệ. Spring Boot sẽ không hiểu dấu phẩy ở đây như cú pháp tách danh sách ứng viên.

**Sai — thêm nhãn hoặc dấu hai chấm như cấu hình thuộc tính:**

~~~text
autoConfigurations:
  - com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Tệp imports không phải YAML, cũng không phải tệp **.properties** có key **autoConfigurations**.

**Sai — đưa câu lệnh Java vào tệp:**

~~~text
import com.example.greeting.autoconfigure.GreetingAutoConfiguration;
~~~

Từ khóa **import** và dấu chấm phẩy thuộc cú pháp file **.java**, không dùng trong **AutoConfiguration.imports**.

**Đúng — tên lớp trần, từng dòng một:**

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

Mỗi tên phải chỉ đến một class có thật trong JAR của thư viện hoặc trên classpath mà thư viện hỗ trợ. Không khai báo lặp cùng một class chỉ để “tăng độ ưu tiên”.

## 4. Quy tắc chú thích và dòng trống

Có thể chèn **chú thích toàn dòng bắt đầu bằng #** để giải thích nhóm cấu hình hoặc ghi chú mục đích của từng class. Dòng trống giúp phân nhóm theo trách nhiệm:

~~~text
# Cau hinh dich vu loi chao mac dinh
com.example.greeting.autoconfigure.GreetingAutoConfiguration

# Cau hinh metadata cua thu vien
com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

Đây là nội dung hợp lệ: hai dòng **#...** được xem là chú thích, dòng trống không đại diện cho ứng viên, còn hai dòng FQCN là hai ứng viên cần xét. Dùng tiếng Việt có dấu trong chú thích khi tệp được lưu bằng UTF-8 cũng hợp lý; ví dụ dùng chữ ASCII để các công cụ hiển thị trên nhiều môi trường dễ đồng nhất.

### Những điều không nên suy đoán về cú pháp chú thích

- **# ở đầu dòng** là dạng được công bố, rõ ràng và an toàn. Đừng dựa vào việc parser có thể tự cắt khoảng trắng trước dấu **#** ở một bản Boot cụ thể; khi viết, đặt dấu **#** đầu dòng.
- **Không chèn chú thích sau FQCN cùng dòng**. Ví dụ **com.example.FooAutoConfiguration # foo** không phải dạng documented của một ứng viên và có thể bị coi là tên lớp sai.
- **Không dùng // hoặc /* ... */** theo thói quen Java làm marker chú thích. Quy tắc định dạng imports là dòng bắt đầu bằng **#**.
- **Không dùng dấu nháy** quanh FQCN và không thêm dấu **;** cuối dòng.
- **Không dùng dòng chú thích để vô hiệu hóa điều kiện trong class**. Chú thích một dòng FQCN khiến class đó không còn được liệt kê như ứng viên từ tệp ấy; bản thân nó không thay đổi code của class hay các auto-configuration do JAR khác cung cấp.

Nên tạo tệp ở dạng **plain text UTF-8**, giữ tên tệp và đường dẫn chính xác, dùng một FQCN mỗi dòng. Đừng tạo BOM hoặc nội dung trang trí ở đầu tệp: ký tự không mong muốn có thể làm hỏng tên ứng viên đầu tiên. Dòng trống cuối tệp bình thường không gây vấn đề.

## 5. Vị trí và cách đóng gói tệp vào JAR

Với thư viện Java/Gradle thông thường:

~~~text
greeting-autoconfigure/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/greeting/
    │   │       ├── GreetingService.java
    │   │       ├── GreetingMetadata.java
    │   │       └── autoconfigure/
    │   │           ├── GreetingAutoConfiguration.java
    │   │           └── GreetingMetadataAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/consumer/
            └── GreetingDiscoveryTest.java
~~~

**Chú ý tên thư mục và chữ hoa/chữ thường**: **META-INF** là thư mục cấp trên, bên trong là **spring**, và tên tệp chứa toàn bộ chuỗi **org.springframework.boot.autoconfigure.AutoConfiguration.imports**. Tệp không mang đuôi **.java** hoặc **.txt**. Không đặt tại **src/test/resources** nếu muốn nó được đóng gói vào JAR chính của thư viện.

Khi dùng cấu trúc resource mặc định của plugin **java** hoặc **java-library** trong Gradle, tài nguyên **src/main/resources** được đưa vào JAR thông qua các task xử lý resource và jar. Nếu build tùy chỉnh source sets hoặc resources, phải xác minh nội dung artifact thay vì chỉ thấy tệp ở source tree.

### 5.1. Khác nhau giữa mã class và tên xuất hiện trong imports

Tệp **.java** định nghĩa class thực tế. Tệp **.imports** chứa *tên* class để framework tìm và xét. Chỉ thêm tên vào tệp không khiến class được sinh ra, biên dịch hay tạo bytecode.

Vì vậy, nếu có dòng:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

thì khi build cần có class bytecode tương ứng:

~~~text
com/example/greeting/autoconfigure/GreetingAutoConfiguration.class
~~~

Tên package/class phải thống nhất. Nếu source đã đổi package mà quên đổi imports, lỗi này có thể chỉ bộc lộ ở một ứng dụng khác khi tự phát hiện auto-configuration.

## 6. Ví dụ hoàn chỉnh: hai auto-configuration ứng viên trong một JAR

Để tránh chỉ đọc cú pháp suông, hãy tạo một thư viện nhỏ có **hai class @AutoConfiguration độc lập**, một cung cấp **GreetingService**, một cung cấp **GreetingMetadata**. Chúng được liệt kê bằng hai dòng FQCN và được tìm thấy khi một Spring Boot application bật auto-configuration.

Ví dụ dùng **Java 21, Gradle 8.x, Spring Boot 3.3.13**. Đây là phiên bản cụ thể của bài thực hành, không phải khẳng định về phiên bản mới nhất. Chương trình cần tải dependency từ Maven Central trong lần đầu chạy.

### 6.1. Tệp settings.gradle

~~~groovy
rootProject.name = 'greeting-autoconfigure'
~~~

### 6.2. Tệp build.gradle

~~~groovy
plugins {
    id 'java-library'
}

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

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Giải thích:** module là thư viện JAR nên chỉ cần plugin **java-library**; không cần Spring Boot executable bootJar. BOM quản lý version cho Spring Boot và các dependency tương ứng. **spring-boot-autoconfigure** cung cấp **@AutoConfiguration** và các điều kiện; JUnit và Spring Boot test hỗ trợ kiểm chứng ứng viên trong context.

### 6.3. Public API: GreetingService

Tệp **src/main/java/com/example/greeting/GreetingService.java**:

~~~java
package com.example.greeting;

public final class GreetingService {

    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

### 6.4. Public API: GreetingMetadata

Tệp **src/main/java/com/example/greeting/GreetingMetadata.java**:

~~~java
package com.example.greeting;

public record GreetingMetadata(String moduleName) {
}
~~~

Đây là record Java 21 lưu một tên module để có thêm bean độc lập minh họa việc khai báo **hai** ứng viên.

### 6.5. Ứng viên số 1: GreetingAutoConfiguration

Tệp **src/main/java/com/example/greeting/autoconfigure/GreetingAutoConfiguration.java**:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

**@ConditionalOnMissingBean** cho phép ứng dụng cung cấp GreetingService riêng để auto-configuration không đăng ký thêm bean mặc định. Điều kiện này hoàn toàn nằm trong Java class; dòng imports không chứa cú pháp điều kiện.

### 6.6. Ứng viên số 2: GreetingMetadataAutoConfiguration

Tệp **src/main/java/com/example/greeting/autoconfigure/GreetingMetadataAutoConfiguration.java**:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingMetadata;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingMetadataAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingMetadata.class)
    public GreetingMetadata greetingMetadata() {
        return new GreetingMetadata("greeting");
    }
}
~~~

### 6.7. Tệp AutoConfiguration.imports

Tệp **src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** chứa:

~~~text
# Cau hinh service loi chao
com.example.greeting.autoconfigure.GreetingAutoConfiguration

# Cau hinh metadata cua module
com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

Hai dòng FQCN được giải thích như sau:

| Dòng | Ý nghĩa |
| --- | --- |
| **# Cau hinh service loi chao** | Chú thích; không được nạp như class. |
| **com.example.greeting.autoconfigure.GreetingAutoConfiguration** | Ứng viên thứ nhất. |
| Dòng trống | Phân nhóm, không tạo ứng viên. |
| **# Cau hinh metadata cua module** | Chú thích; không phải class. |
| **com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration** | Ứng viên thứ hai. |

**Không thêm** **com.example.greeting.GreetingService** hay **GreetingMetadata** vào imports. Hai class đó là kiểu dữ liệu/bean được tạo bởi cấu hình, không phải auto-configuration class cần đăng ký như ứng viên.

## 7. Kiểm thử Spring Boot tự phát hiện hai ứng viên

Để xác nhận tệp imports được Spring Boot đọc, hãy dùng một ứng dụng kiểm thử ở **package khác**: **com.example.consumer**. Test được bật **@EnableAutoConfiguration** và không dùng **@Import** để liệt kê trực tiếp hai class cấu hình.

Tệp **src/test/java/com/example/consumer/GreetingDiscoveryTest.java**:

~~~java
package com.example.consumer;

import com.example.greeting.GreetingMetadata;
import com.example.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = GreetingDiscoveryTest.TestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class GreetingDiscoveryTest {

    @Autowired
    ApplicationContext context;

    @Test
    void discoversBothCandidatesFromImports() {
        assertThat(context.getBeansOfType(GreetingService.class))
            .hasSize(1);
        assertThat(context.getBeansOfType(GreetingMetadata.class))
            .hasSize(1);

        assertThat(
            context.getBean(GreetingService.class).greet("Mai")
        ).isEqualTo("Xin chào, Mai!");

        assertThat(
            context.getBean(GreetingMetadata.class).moduleName()
        ).isEqualTo("greeting");
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }
}
~~~

Chạy ở thư mục root của project:

~~~bash
gradle test
~~~

Nếu đã tạo Gradle Wrapper, có thể dùng **./gradlew test** trên macOS/Linux hoặc **.\gradlew.bat test** trên Windows. Gradle kiểm thử và thông báo trạng thái task; không có một stdout cố định cần học thuộc.

**Vì sao test này có giá trị?** Class cấu hình được đăng ký qua resource imports trên test runtime classpath. Vì test application không trực tiếp **@Import(GreetingAutoConfiguration.class)**, một test pass giúp chứng minh cơ chế **discovery và condition** làm việc cùng nhau. Đặt application test trong package khác giảm khả năng cấu hình bị phát hiện tình cờ qua component scanning.

**Giới hạn:** Test chạy trên classpath của project, nơi **src/main/resources** đã tham gia resource processing; nó chưa chứng minh tệp đã nằm đúng trong **JAR được phát hành**. Vì vậy bước kiểm chứng JAR tiếp theo là bắt buộc khi cung cấp thư viện cho dự án khác.

### 7.1. Thử bỏ một dòng imports để thấy tác động

Trong một nhánh thực hành riêng, chỉ comment dòng thứ hai:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
# com.example.greeting.autoconfigure.GreetingMetadataAutoConfiguration
~~~

Khi chạy lại test discovery (và không có bean Metadata do nguồn khác cung cấp), assertion về **GreetingMetadata** sẽ thất bại, còn GreetingService vẫn có thể được tạo. Từ đó thấy rõ **comment một dòng ứng viên** đồng nghĩa loại class ấy khỏi danh sách discovery của tệp này, nhưng không thay đổi class Java hoặc xóa bytecode của nó. Hãy khôi phục imports hợp lệ sau thử nghiệm.

## 8. Kiểm tra tài nguyên chính xác bên trong JAR

Đóng gói thư viện bằng task **jar**:

~~~bash
gradle jar
~~~

Vì build.gradle đặt version **1.0.0**, artifact tiêu chuẩn là:

~~~text
build/libs/greeting-autoconfigure-1.0.0.jar
~~~

Kiểm tra entry:

~~~bash
jar tf build/libs/greeting-autoconfigure-1.0.0.jar
~~~

Trong danh sách cần có:

~~~text
com/example/greeting/autoconfigure/GreetingAutoConfiguration.class
com/example/greeting/autoconfigure/GreetingMetadataAutoConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

**jar tf** chỉ xác nhận tệp có mặt. Muốn chắc nội dung không bị đóng gói khác source, hãy mở entry **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** trong JAR bằng công cụ đọc ZIP/JAR, đối chiếu chính xác các dòng FQCN với class đã build. Với lệnh **unzip** trên hệ thống có sẵn công cụ này:

~~~bash
unzip -p build/libs/greeting-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung phải chứa hai dòng FQCN và những dòng comment đã viết, giữ nguyên thứ tự trong resource. Không phải hệ thống Windows nào cũng có **unzip**; khi không có, dùng công cụ duyệt ZIP/JAR tương đương.

**Các mốc bằng chứng cần giữ:** tệp nằm đúng đường dẫn source, bytecode cho từng class có trong JAR, nội dung resource sau đóng gói đúng tên class và test discovery pass. Từng mốc trả lời một loại lỗi khác nhau.

## 9. Imports tham gia quá trình lựa chọn ứng viên ở bước nào?

Hãy phân biệt **tìm ứng viên** và **áp dụng điều kiện**:

~~~text
Application bật auto-configuration
            |
            v
Spring Boot tìm AutoConfiguration.imports
trên runtime classpath
            |
            v
Đọc các FQCN, bỏ dòng trống và dòng chú thích #
            |
            v
Có danh sách class auto-configuration ứng viên
            |
            v
Áp dụng cơ chế chọn/lọc, sắp xếp và đánh giá condition
            |
      +-----+------+
      |            |
     Match       Không match
      |            |
      v            v
Áp dụng config   Bỏ qua config/bean
phù hợp          không thỏa điều kiện
~~~

Tệp imports không có cột **enabled**, **priority** hay biểu thức **ConditionalOnClass**. Những yếu tố này được thể hiện bằng code annotation hoặc cơ chế cấu hình tương ứng của Spring Boot.

### 9.1. Thứ tự các dòng có phải thứ tự khởi tạo bean?

**Không nên coi thứ tự dòng trong imports là hợp đồng về thứ tự tạo bean.** Spring Boot có cơ chế sắp xếp auto-configuration riêng. Khi phải khai báo quan hệ thứ tự, dùng metadata trên class như **@AutoConfiguration(before = ...)**, **@AutoConfiguration(after = ...)** hoặc cơ chế được Boot hỗ trợ. Việc đổi thứ tự dòng chỉ để ép thứ tự đăng ký bean là cách làm không vững.

### 9.2. Nếu hai JAR đều có tệp imports thì sao?

Mỗi thư viện có thể đóng gói **một resource cùng tên đường dẫn** trong JAR riêng của mình. Spring Boot thu thập danh sách ứng viên từ các resource đó trên classpath. Nhà phát triển không cần gom tất cả FQCN của mọi starter vào một tệp duy nhất trong ứng dụng.

Tuy nhiên, quá trình tạo **fat JAR hoặc shaded JAR** bằng công cụ tùy chỉnh có thể vô tình ghi đè resource cùng tên thay vì giữ/gộp nội dung. Nếu làm thư viện được package theo kiểu đó, phải kiểm tra resource cuối cùng và test discovery thật; không chỉ dựa vào tệp trong module nguồn.

### 9.3. Imports khác component scanning như thế nào?

Một class nằm ngoài phạm vi component scanning của ứng dụng vẫn có thể trở thành ứng viên auto-configuration nhờ tệp imports. Điều này cho phép thư viện cung cấp cấu hình tự động mà không yêu cầu người dùng thêm **@ComponentScan("com.example.greeting")**.

Cũng không nên đánh dấu mọi class thường như **@Component** rồi đưa chúng vào imports để thay component scan. Danh sách này dành cho **auto-configuration class**; bean của thư viện nên được đăng ký có chủ đích qua **@Bean**, import cấu hình thích hợp hoặc cơ chế được Boot hỗ trợ.

## 10. Các lỗi thường gặp khi biên soạn imports

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Không tìm thấy cấu hình thư viện | Tệp sai tên/đường dẫn, nằm trong test resources, không được đóng gói | Kiểm tra **jar tf**, đường dẫn đúng trong JAR. |
| Lỗi nạp tên class | Viết simple name, sai package, sai chữ hoa/chữ thường hoặc thêm ký tự **;** | So FQCN với package/class và bytecode trong JAR. |
| Hai class nằm trên cùng một dòng | Dùng dấu phẩy/dấu chấm phẩy để tách | Tách thành **hai dòng độc lập**. |
| Một chú thích bị hiểu như tên class | Dùng **//**, chú thích cuối dòng hoặc marker không được hỗ trợ | Dùng **#** ở đầu dòng riêng. |
| Class đã tồn tại nhưng không được Boot xét | Thiếu dòng FQCN hoặc dòng bị comment | Đọc entry imports trong JAR thực tế. |
| Candidate được xét nhưng bean không có | **@ConditionalOnMissingBean**, **@ConditionalOnProperty** hoặc điều kiện khác không match | Bật **--debug** và đọc Condition Evaluation Report. |
| Test trực tiếp @Import pass nhưng consumer không thấy bean | Test đã bypass bước imports discovery | Tạo test với **@EnableAutoConfiguration** không import trực tiếp; kiểm tra JAR. |
| Có lỗi sau đổi tên class | Cập nhật Java class nhưng quên FQCN trong imports | Sửa resource, rebuild JAR và chạy test. |
| Build dạng shaded làm mất ứng viên | Resource trong nhiều JAR bị overwrite | Kiểm tra artifact cuối cùng và chiến lược xử lý resource. |

### Phân biệt lỗi cú pháp tệp và lỗi condition

Một class **không xuất hiện trong danh sách ứng viên** thường khiến ta kiểm tra resource/classpath trước. Một class **được tìm thấy nhưng không tạo bean** lại cần kiểm tra condition. Thêm trực tiếp bean để “chữa” hai loại lỗi này có thể che mất vấn đề thực sự.

Có thể chạy ứng dụng Spring Boot với tham số:

~~~bash
java -jar app.jar --debug
~~~

Báo cáo condition evaluation giúp tìm vì sao candidate/configuration được áp dụng hay bị loại trừ khi ứng dụng đã nạp cấu hình liên quan. Kết hợp với kiểm tra nội dung JAR để chẩn đoán chính xác lỗi ở bước discovery.

## 11. Quy trình tạo imports an toàn khi phát triển thư viện

1. **Viết class auto-configuration** với package rõ ràng và annotation **@AutoConfiguration**; dùng **@Bean** và các điều kiện phù hợp.
2. **Lấy FQCN từ đúng package + class name**, tuyệt đối không dự đoán từ tên thư mục nếu source đã refactor.
3. **Tạo resource ở đường dẫn chuẩn** **src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
4. **Ghi mỗi class trên một dòng**, không có dấu phẩy, dấu ngoặc kép, dấu chấm phẩy hoặc từ khóa **import**.
5. **Đặt chú thích riêng trên dòng bắt đầu bằng #** nếu cần giải thích; không tạo cú pháp chú thích tự chế.
6. **Biên dịch và đóng gói JAR**, kiểm tra đủ class bytecode và entry imports.
7. **Kiểm tra nội dung resource trong artifact** để xác nhận FQCN còn chính xác.
8. **Chạy ứng dụng/test discovery không dùng @Import trực tiếp**, sau đó xem bean thực tế và condition report nếu khác dự kiến.
9. **Đưa kiểm chứng này vào CI** để phát hiện lỗi khi đổi package, đổi tên class hoặc thay pipeline đóng gói.

Đây là quy trình đủ gọn cho thư viện nhỏ và vẫn áp dụng được khi JAR chứa nhiều ứng viên. Điểm quan trọng là **cú pháp đúng chưa đủ; artifact phải đúng và runtime phải thực sự tự phát hiện các class**.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một dòng trong imports ghi **GreetingAutoConfiguration**. Sai ở đâu?

*Đáp án:* thiếu package. Phải ghi FQCN, ví dụ **com.example.greeting.autoconfigure.GreetingAutoConfiguration**.

**Câu 2.** Muốn đăng ký ba ứng viên, có thể ngăn cách bằng dấu phẩy trong một dòng không?

*Đáp án:* không. Phải dùng ba dòng FQCN riêng.

**Câu 3.** Dòng **# com.example.XAutoConfiguration** có khiến X được tải làm ứng viên từ tệp đó không?

*Đáp án:* không. Đây là chú thích toàn dòng.

**Câu 4.** Một tệp có hai FQCN hợp lệ. Có chắc Spring Boot tạo bean từ cả hai class không?

*Đáp án:* không. Tệp chỉ công bố ứng viên; điều kiện trên class/bean và môi trường vẫn quyết định.

**Câu 5.** Test dùng **AutoConfigurations.of(XAutoConfiguration.class)** pass. Có chứng minh imports trong JAR chính xác không?

*Đáp án:* chưa. Test này đưa class vào context một cách trực tiếp, có thể bypass discovery qua resource. Cần kiểm tra JAR và chạy consumer/test dùng **@EnableAutoConfiguration**.

**Câu 6.** Thư viện có đúng file imports trong **src/test/resources**, nhưng một ứng dụng tiêu thụ không thấy auto-configuration. Vì sao?

*Đáp án:* thông thường test resources không được đóng gói trong main library JAR. Hãy đặt tệp tại **src/main/resources** và kiểm tra artifact.

**Câu 7.** Chuyển auto-configuration sang package mới mà không cập nhật imports gây lỗi gì?

*Đáp án:* resource tiếp tục trỏ tới FQCN cũ không còn phù hợp; Boot có thể không nạp được class ứng viên. Phải sửa resource và chạy lại kiểm chứng discovery.

## Kết luận

Với Spring Boot 3.x, **AutoConfiguration.imports là danh sách văn bản của các class auto-configuration ứng viên**. Quy tắc viết quan trọng nhất là **FQCN chính xác, một class mỗi dòng, chú thích toàn dòng bắt đầu bằng #**, và resource được đóng gói đúng tại **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.

Từ danh sách ấy Spring Boot mới đi tiếp sang cơ chế chọn và đánh giá điều kiện. Vì vậy, để tin rằng một thư viện tự cấu hình đúng, hãy kiểm tra cả ba phần: **nội dung file đúng**, **JAR có đủ file và class**, **ứng dụng tiêu thụ tự phát hiện cấu hình và tạo bean theo điều kiện**.
