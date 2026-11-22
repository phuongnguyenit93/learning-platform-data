# Checklist phát hành JAR: imports, metadata, dependency, kiểm thử và ứng dụng tiêu thụ

## 1. Mục tiêu của lần phát hành

Một custom Spring Boot starter có thể biên dịch và test thành công trong repository nhưng vẫn không hoạt động khi một ứng dụng khác thêm dependency. Lý do thường nằm ở artifact đã publish: file đăng ký auto-configuration bị thiếu, metadata không được đóng gói, dependency optional khai báo sai, POM không mô tả đúng runtime classpath hoặc test chỉ chạy trong module producer.

Vì vậy, phát hành starter cần kiểm tra ba lớp:

1. **Nội dung JAR:** class, resource, imports và metadata có thật sự nằm trong artifact không?
2. **Dependency metadata:** Maven POM hoặc Gradle Module Metadata có đưa đúng dependency đến consumer không?
3. **Ứng dụng tiêu thụ:** một project độc lập chỉ khai báo starter có khởi động, nhận auto-configuration và dùng được tính năng không?

Bài này dùng Spring Boot 3.5.x, Java 17 và thư viện giả định com.acme:acme-client. Tên artifact, class và version Acme là ví dụ; thay bằng thư viện thật của dự án.

## 2. Phân biệt các artifact cần phát hành

Với một integration có dependency tùy chọn, cấu trúc hai module thường dễ kiểm soát:

~~~text
acme-spring-boot-autoconfigure/
    - @AutoConfiguration và các nested configuration
    - @ConfigurationProperties
    - điều kiện classpath/property/bean
    - callback hoặc API Spring-facing
    - metadata và AutoConfiguration.imports

acme-spring-boot-starter/
    - thường không có Java source
    - dependency tới acme-spring-boot-autoconfigure
    - dependency tới acme-client và thư viện cần cho trải nghiệm mặc định
    - không đóng gói lại dependency bên trong JAR

consumer-app/
    - chỉ khai báo acme-spring-boot-starter
    - kiểm tra auto-configuration được phát hiện từ JAR đã publish
    - kiểm tra runtime classpath và hành vi thực tế
~~~

**Autoconfigure module** chứa logic tích hợp. Nó có thể được ứng dụng khác dùng trực tiếp để tự chọn thư viện, vì vậy dependency của thư viện Acme thường được đánh dấu optional trong Maven hoặc compile-only trong Gradle nếu chỉ cần để biên dịch phần integration.

**Starter module** thể hiện lựa chọn dependency mặc định của nhà phát hành. Nếu trải nghiệm mặc định cần Acme Client, starter khai báo Acme Client trực tiếp và không optional. Khi consumer thêm starter, dependency đó phải đến runtime classpath của ứng dụng.

**Consumer application** là phép thử quan trọng cho artifact đã publish. Test trong module autoconfigure có thể luôn nhìn thấy dependency do module đó khai báo; consumer độc lập cho biết POM/Gradle metadata và resource thực sự có hoạt động ngoài producer hay không.

### 2.1. Starter JAR khác executable Spring Boot JAR

| Loại artifact | Nội dung điển hình | Mục đích |
| --- | --- | --- |
| Autoconfigure library JAR | com/acme/...class, META-INF/spring/...imports, metadata | Được ứng dụng khác đưa lên classpath |
| Starter JAR | Thường chỉ có manifest và metadata artifact; dependency được khai báo trong POM/module metadata | Dependency bundle, không chứa bản sao các JAR phụ thuộc |
| Executable application JAR | BOOT-INF/classes, BOOT-INF/lib, Spring Boot loader và manifest chạy được | Chạy bằng java -jar |

Không dùng Spring Boot Maven repackage để biến autoconfigure hoặc starter thành executable JAR. Plugin đó dành cho ứng dụng cần chạy bằng java -jar. Library JAR phải giữ cấu trúc JAR Java thông thường để consumer có thể nạp class trực tiếp. Executable JAR của ứng dụng tiêu thụ mới là nơi có BOOT-INF/classes và BOOT-INF/lib.

## 3. Đăng ký auto-configuration bằng AutoConfiguration.imports

### 3.1. Đúng đường dẫn và nội dung

Spring Boot 3 tìm ứng viên auto-configuration trong resource sau bên trong JAR đã publish:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ trong module acme-spring-boot-autoconfigure:

~~~text
com.acme.boot.autoconfigure.AcmeAutoConfiguration
com.acme.boot.autoconfigure.AcmeMetricsAutoConfiguration
~~~

Mỗi class nằm trên một dòng, dùng fully qualified class name. Có thể thêm dòng comment bắt đầu bằng dấu #.

Các lỗi dễ mắc:

- Đặt file ở src/main/java thay vì src/main/resources.
- Sai tên file, sai chữ hoa/chữ thường hoặc thiếu thư mục META-INF/spring.
- Ghi package name nhưng quên tên class.
- Dùng dấu phẩy hoặc định dạng danh sách trên một dòng.
- Tạo file đúng trong source nhưng resource không được đưa vào artifact.
- Chỉ đăng ký trong test configuration nên test pass nhưng consumer không phát hiện được.

Nếu auto-configuration candidate là nested class thay vì top-level class, tên trong imports dùng dấu $ để phân cách class chứa và class lồng nhau, ví dụ com.acme.Outer$NestedAutoConfiguration. Thông thường nên đăng ký top-level auto-configuration rồi để nó dùng @Import hoặc chứa nested configuration theo nhu cầu.

### 3.2. Boot 3 và spring.factories

Với Spring Boot 3, đăng ký auto-configuration bằng META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports. Không dựa vào key EnableAutoConfiguration trong META-INF/spring.factories theo cách của các starter Boot cũ.

spring.factories vẫn có thể được dùng cho một số cơ chế extension khác của Spring Boot; điều cần thay đổi là cơ chế đăng ký danh sách auto-configuration candidate.

### 3.3. Auto-configuration không được component scan

Auto-configuration phải được tìm thấy qua imports file. Không đặt class auto-configuration vào package ứng dụng với hy vọng component scan tự tìm thấy nó; cũng không dùng @ComponentScan trong auto-configuration để quét thêm component.

Hãy dùng @Import cho các cấu hình cụ thể cần nạp. Cách này giới hạn phạm vi, tránh vô tình tạo bean từ package nội bộ và giúp hành vi của starter dễ dự đoán.

### 3.4. Kiểm soát điều kiện và thứ tự

Một auto-configuration điển hình:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.client.AcmeClient")
    static class AcmeClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AcmeOperations acmeOperations(AcmeProperties properties) {
            return new DefaultAcmeOperations(properties);
        }
    }
}
~~~

**@ConditionalOnClass** bảo vệ integration khi thư viện tùy chọn không có mặt. Nested configuration cô lập reference tới optional class; tránh đặt method signature chứa optional type trực tiếp trong cấu hình gốc rồi chỉ trông chờ condition trên @Bean method.

**@ConditionalOnMissingBean** cho phép ứng dụng thay implementation mặc định. **@ConditionalOnProperty** có thể điều khiển feature flag. Hãy kiểm thử cả nhánh có class, thiếu class, property bật/tắt và user bean override.

Nếu cấu hình phụ thuộc thứ tự với auto-configuration khác, dùng before, after, @AutoConfigureBefore, @AutoConfigureAfter hoặc @AutoConfigureOrder có chủ đích. Không dùng thứ tự imports file để thay cho cơ chế ordering chính thức.

### 3.5. Khi đổi tên hoặc thay thế auto-configuration

Nếu một class đã phát hành bị đổi package hoặc thay bằng class khác, có thể cần resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Nội dung ánh xạ class cũ sang class mới:

~~~text
com.acme.boot.autoconfigure.OldAcmeAutoConfiguration=com.acme.boot.autoconfigure.core.AcmeAutoConfiguration
~~~

Sau đó cập nhật AutoConfiguration.imports chỉ còn class thay thế. Việc này giúp xử lý các tham chiếu cũ trong ordering và excludes; không nên đổi tên class đã public mà bỏ qua compatibility.

## 4. Hai loại metadata cần phân biệt

Một starter có thể tạo hai metadata file khác nhau. Chúng không thay thế nhau.

| Metadata | Được tạo bởi | Vai trò |
| --- | --- | --- |
| META-INF/spring-configuration-metadata.json | spring-boot-configuration-processor | Mô tả property, kiểu, default, description và hint để IDE hỗ trợ cấu hình |
| META-INF/spring-autoconfigure-metadata.properties | spring-boot-autoconfigure-processor | Ghi metadata condition để Spring Boot có thể lọc sớm auto-configuration không phù hợp |

### 4.1. Configuration metadata cho IDE

Nếu module có @ConfigurationProperties, thêm spring-boot-configuration-processor vào annotation processor. Processor đọc class/property khi compile và tạo META-INF/spring-configuration-metadata.json.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "acme.client")
public class AcmeProperties {

    /**
     * Whether the Acme integration is enabled.
     */
    private boolean enabled = true;

    /**
     * Timeout for establishing a connection to the Acme service.
     */
    private Duration connectTimeout = Duration.ofSeconds(3);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Javadoc của field giúp sinh description cho IDE. Nên:

- Dùng namespace do thư viện sở hữu, ví dụ acme.client; tránh dùng namespace của Spring Boot như spring, server hoặc management.
- Dùng câu mô tả ngắn, rõ nghĩa.
- Với boolean, mô tả bằng “Whether” hoặc “Enable”.
- Dùng Duration thay cho long nếu biểu diễn thời gian.
- Ghi rõ đơn vị mặc định nếu property cho phép giá trị không kèm hậu tố.
- Không đưa default value vào description nếu processor có thể suy ra default từ source.

Metadata giúp IDE gợi ý key và giá trị; nó không tự đăng ký bean, không thay thế @EnableConfigurationProperties và không thay thế AutoConfiguration.imports.

### 4.2. Maven: cấu hình annotation processors

Trong module autoconfigure, ví dụ cấu hình Maven Compiler Plugin 3.13.0 trở lên:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        <version>${spring-boot.version}</version>
                    </path>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                        <version>${spring-boot.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đặt version trong parent POM hoặc dependency management để các module dùng cùng một Spring Boot version. Nếu project dùng Lombok hoặc annotation processor khác, khai báo tất cả processor cần thiết và kiểm tra thứ tự chạy; việc chỉ định annotationProcessorPaths có thể làm processor không nằm trong danh sách bị bỏ qua.

Nếu module không có @ConfigurationProperties, configuration processor không bắt buộc. Nếu muốn metadata condition để lọc auto-configuration sớm, cấu hình spring-boot-autoconfigure-processor trong module chứa auto-configuration.

### 4.3. Gradle: cấu hình annotationProcessor

Với Gradle Kotlin DSL:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")

    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Hai processor nằm ở configuration annotationProcessor, không đặt thành dependency runtime của consumer. Nếu dùng file metadata bổ sung, bảo đảm task compile xử lý file resource trước khi annotation processor cần đọc nó.

### 4.4. Metadata bổ sung do người viết cung cấp

Processor không phải lúc nào cũng suy ra được default value, description hoặc hint. Có thể thêm file:

~~~text
META-INF/additional-spring-configuration-metadata.json
~~~

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "acme.client.retry-delays",
      "type": "java.util.List<java.time.Duration>",
      "description": "Delays used between connection attempts.",
      "defaultValue": ["1s", "3s", "5s"]
    }
  ],
  "hints": [
    {
      "name": "acme.client.mode",
      "values": [
        { "value": "sync", "description": "Use synchronous calls." },
        { "value": "async", "description": "Use asynchronous calls." }
      ]
    }
  ]
}
~~~

Định dạng minh họa cần khớp với kiểu dữ liệu và property thật. File bổ sung được processor hợp nhất vào metadata chính. Không tạo file rỗng nếu không có property/hint bổ sung.

### 4.5. Không nhầm metadata với imports

- AutoConfiguration.imports là danh sách candidate để Boot tìm và nạp auto-configuration.
- spring-configuration-metadata.json giúp IDE hiểu property.
- spring-autoconfigure-metadata.properties hỗ trợ lọc condition sớm.

Một artifact có đủ hai metadata file nhưng thiếu AutoConfiguration.imports vẫn có thể không được phát hiện. Ngược lại, auto-configuration vẫn có thể chạy khi metadata tối ưu condition chưa được tạo; file đó không thay thế imports.

## 5. Kiểm tra dependency declaration và metadata được publish

### 5.1. Maven: autoconfigure module

Ví dụ dependency trong POM của acme-spring-boot-autoconfigure:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-client</artifactId>
        <version>${acme-client.version}</version>
        <optional>true</optional>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Dependency acme-client vẫn có trên compile/runtime classpath của chính module autoconfigure, nhưng không tự truyền sang consumer chỉ phụ thuộc vào autoconfigure module. Đây là cách cho phép ứng dụng tự chọn integration.

### 5.2. Maven: starter module

Starter khai báo dependency cần thiết cho trải nghiệm mặc định:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-spring-boot-autoconfigure</artifactId>
        <version>${project.version}</version>
    </dependency>

    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-client</artifactId>
        <version>${acme-client.version}</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

acme-client ở starter không optional nếu starter cam kết bật integration đó theo mặc định. Khi consumer chỉ thêm starter, dependency phải xuất hiện trên runtime classpath.

Starter phải tham chiếu spring-boot-starter trực tiếp hoặc gián tiếp; không cần thêm một lần nữa nếu starter đã phụ thuộc một starter khác mang core starter vào.

### 5.3. Gradle: phân biệt compile và runtime

Trong autoconfigure module:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")
    compileOnly("com.acme:acme-client:4.2.0")

    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("com.acme:acme-client:4.2.0")
}
~~~

compileOnly giúp code autoconfigure biên dịch với API Acme nhưng không tự đưa Acme vào runtime của consumer. Test cần thư viện thật để chạy nhánh integration nên có testImplementation.

Trong starter module:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api(project(":acme-spring-boot-autoconfigure"))
    implementation("com.acme:acme-client:4.2.0")
    implementation("org.springframework.boot:spring-boot-starter")
}
~~~

Ví dụ dùng api(project(...)) vì consumer smoke test có sử dụng public type AcmeOperations được công bố từ autoconfigure module. Nếu consumer chỉ cần starter để kích hoạt bean mà không compile với API của autoconfigure, có thể dùng implementation(project(...)).

Chọn api hay implementation dựa trên public API thật sự. compileOnly trong autoconfigure không có nghĩa runtime consumer tự nhận Acme Client; starter phải đưa dependency đó vào runtime nếu tính năng mặc định cần nó.

### 5.4. Quản lý version nhất quán

Với Maven, dùng Spring Boot parent hoặc import spring-boot-dependencies BOM. Với Gradle, dùng Spring dependency management plugin hoặc platform/BOM phù hợp.

Kiểm tra:

- Autoconfigure và starter cùng release version.
- Spring Boot artifacts cùng một dòng version được hỗ trợ.
- Third-party library tương thích với Spring Boot/Java mục tiêu.
- Không khai báo version khác nhau của cùng một thư viện ở hai module.
- Dependency test không bị đưa vào POM/runtime của consumer.
- Dependency optional không vô tình trở thành bắt buộc qua một đường transitive khác.

Không dựa vào dependency được kéo tình cờ từ một starter khác. Nếu code trực tiếp dùng một thư viện, khai báo dependency trực tiếp ở module cần nó.

### 5.5. Kiểm tra POM và Gradle Module Metadata

Build file source chưa phải metadata mà consumer đọc. Sau khi publish, kiểm tra:

- POM có đúng groupId, artifactId, version không?
- Dependency compile/runtime/optional có đúng không?
- Dependency test có bị lộ ra consumer không?
- Version được quản lý bằng dependency management có còn đúng không?
- Nếu dùng Gradle, file .module có các variant và dependency như dự kiến không?

Gradle Module Metadata giữ được nhiều thông tin variant hơn POM. Khi publish cho nhiều build tool, hãy kiểm tra cả POM lẫn .module; đừng giả định mọi consumer đều đọc cùng một metadata format.

## 6. Kiểm thử auto-configuration trong module producer

### 6.1. ApplicationContextRunner

Dùng ApplicationContextRunner để kiểm thử các condition trong context nhỏ:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(AcmeAutoConfiguration.class)
                );
~~~

Các scenario nên có:

| Scenario | Kết quả cần xác nhận |
| --- | --- |
| Dependency có mặt, feature mặc định bật | Bean mặc định được tạo |
| Property tắt feature | Bean mặc định không xuất hiện |
| Optional class vắng mặt | Context vẫn khởi động; integration được bỏ qua |
| User cung cấp bean | Bean mặc định back off |
| Property hoặc cấu hình không hợp lệ | Lỗi/behavior đúng với hợp đồng được tài liệu hóa |

Để giả lập thiếu optional dependency:

~~~java
runner.withClassLoader(new FilteredClassLoader(AcmeClient.class))
        .run(context -> {
            assertThat(context).doesNotHaveBean("acmeOperations");
        });
~~~

Test này chỉ có ý nghĩa nếu auto-configuration thật sự bảo vệ optional class bằng class condition và cô lập reference cần thiết.

### 6.2. Test metadata property

Nếu thư viện có @ConfigurationProperties, kiểm tra file JSON đã được tạo và có các key quan trọng:

- Prefix có đúng namespace của thư viện không?
- Property name có canonical kebab-case không?
- Description có rõ và không chứa markup không?
- Default value có đúng không?
- Type có đúng với Java field/record component không?
- Hint cho enum/list có phản ánh các lựa chọn thực tế không?

Metadata sai có thể khiến IDE gợi ý sai dù runtime binding vẫn hoạt động. Đây là lý do cần review artifact sau compile, không chỉ review source Javadoc.

### 6.3. Kiểm tra classpath thật của producer

Trong module autoconfigure, chạy:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.acme:acme-client
~~~

Trong Gradle:

~~~bash
./gradlew :acme-spring-boot-autoconfigure:dependencies --configuration compileClasspath
./gradlew :acme-spring-boot-autoconfigure:dependencies --configuration runtimeClasspath
~~~

Xác nhận Acme Client có trong classpath module producer để compile/test. Sau đó kiểm tra consumer riêng ở phần tiếp theo; producer pass chưa chứng minh optional dependency được truyền đúng.

## 7. Kiểm tra nội dung JAR sau khi build

### 7.1. Build artifact sạch

Maven:

~~~bash
mvn clean verify
~~~

Gradle:

~~~bash
./gradlew clean build
~~~

Không chỉ chạy compile. verify/build phải chạy các test và bước đóng gói cần thiết.

### 7.2. Liệt kê nội dung JAR

Dùng JDK jar:

~~~bash
jar tf acme-spring-boot-autoconfigure/target/acme-spring-boot-autoconfigure-1.0.0.jar
~~~

Tìm các entry tương ứng:

~~~text
com/acme/boot/autoconfigure/AcmeAutoConfiguration.class
com/acme/boot/autoconfigure/AcmeProperties.class
META-INF/MANIFEST.MF
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
META-INF/spring-configuration-metadata.json
~~~

Hai metadata processor chỉ xuất hiện khi module đã cấu hình processor tương ứng và có nội dung cần sinh. Không kết luận build hỏng chỉ vì một metadata tùy chọn không được tạo khi project không cần nó; nhưng imports phải có nếu đây là artifact đăng ký auto-configuration.

Kiểm tra nội dung imports bằng cách giải nén resource trong thư mục tạm hoặc dùng công cụ đọc ZIP:

~~~bash
unzip -p acme-spring-boot-autoconfigure/target/acme-spring-boot-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Kết quả phải liệt kê đúng class name, mỗi class một dòng. So sánh với class thực tế trong JAR; sai package hoặc sai tên class sẽ khiến Boot không nạp được cấu hình.

### 7.3. Kiểm tra starter JAR

Starter thường là JAR gần như rỗng. Hãy xác nhận:

- Không có bản sao các dependency Acme hoặc Spring nằm bên trong starter JAR.
- POM/Gradle metadata của starter khai báo các dependency cần thiết.
- Starter không bị Spring Boot Maven Plugin repackage biến thành executable archive.
- Artifact có đúng tọa độ và version.

Nếu thấy BOOT-INF/classes và BOOT-INF/lib bên trong starter JAR, kiểm tra xem plugin repackage có bị áp dụng nhầm vào module library hay không.

### 7.4. Kiểm tra executable JAR của consumer

Ứng dụng consumer sau khi package bằng Spring Boot Maven Plugin thường có:

~~~text
BOOT-INF/classes/
BOOT-INF/lib/
org/springframework/boot/loader/
META-INF/MANIFEST.MF
~~~

Manifest có Main-Class trỏ đến Boot loader và Start-Class trỏ đến main application class. Đây là cấu trúc của executable application JAR, khác với library JAR của starter.

Chạy thử:

~~~bash
java -jar consumer-app/target/consumer-app-1.0.0.jar
~~~

Nếu ứng dụng chạy từ IDE nhưng không chạy từ JAR, hãy kiểm tra resource và dependency trong archive đã package, không chỉ classpath của IDE.

### 7.5. Cẩn thận khi tạo shaded/uber JAR

Nếu dùng Maven Shade Plugin hoặc công cụ tạo một uber JAR bằng cách gộp nhiều dependency, các resource cùng đường dẫn có thể ghi đè nhau. Nhiều library có thể cùng chứa AutoConfiguration.imports.

Phải cấu hình resource transformer để hợp nhất danh sách imports, đồng thời kiểm tra các metadata cần giữ. Với Spring Boot executable JAR thông thường, Boot loader giữ dependency ở các JAR lồng trong BOOT-INF/lib, nên không cần gộp toàn bộ resource vào một uber JAR.

## 8. Kiểm thử bằng một ứng dụng consumer độc lập

Đây là bước chứng minh starter hoạt động sau khi đóng gói và publish.

### 8.1. Consumer chỉ khai báo starter

POM của consumer nên khai báo starter và test dependency. Không khai báo trực tiếp acme-client nếu mục tiêu là kiểm tra starter có mang dependency đó đến runtime:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-spring-boot-starter</artifactId>
        <version>1.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu consumer phải thêm trực tiếp Acme Client để khởi động thì cần xem lại POM starter hoặc dependency optional ở module autoconfigure.

### 8.2. Consumer application

~~~java
package example.consumer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }
}
~~~

Không import AcmeAutoConfiguration trực tiếp và không dùng @Import để cứu test. Mục tiêu là chứng minh Spring Boot tự phát hiện auto-configuration từ resource trong dependency JAR.

### 8.3. Smoke test của consumer

Giả sử autoconfigure module công bố public interface AcmeOperations:

~~~java
package example.consumer;

import example.acme.AcmeOperations;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class StarterSmokeTests {

    @Autowired
    private AcmeOperations operations;

    @Test
    void starterProvidesTheDefaultIntegration() {
        assertThat(operations).isNotNull();
        assertThat(operations.health()).isEqualTo("ready");
    }
}
~~~

Consumer chỉ dùng API public của starter/autoconfigure. Nó không cần import type nội bộ của thư viện Acme nếu API của starter đã bọc dependency đó.

Nếu thư viện được thiết kế để consumer gọi trực tiếp AcmeClient, consumer phải khai báo dependency đó trực tiếp hoặc starter phải export dependency ở compile classpath theo contract đã công bố. Không để consumer phụ thuộc tình cờ vào transitive implementation detail.

### 8.4. Test consumer không có optional integration

Nếu người dùng chỉ thêm autoconfigure module và không thêm Acme Client, tạo một consumer scenario riêng. Ứng dụng phải khởi động được và bean integration tùy chọn không được tạo.

Có thể dùng một project test khác chỉ phụ thuộc autoconfigure, hoặc dùng FilteredClassLoader trong test auto-configuration. Project consumer riêng chứng minh cả dependency metadata lẫn runtime startup.

### 8.5. Cài artifact vào local Maven repository rồi mới test consumer

Một quy trình Maven thực tế:

~~~bash
mvn -pl acme-spring-boot-autoconfigure,acme-spring-boot-starter -am clean install
mvn -f samples/consumer-app/pom.xml clean verify
~~~

Lệnh đầu build và cài các module cùng dependency nội bộ vào local Maven repository. Lệnh thứ hai build consumer độc lập, chỉ đọc artifact theo tọa độ đã publish.

Dùng version thử nghiệm riêng hoặc version SNAPSHOT có kiểm soát để tránh vô tình test một artifact cũ trong local repository. Consumer test phải trỏ đúng groupId/artifactId/version vừa build.

### 8.6. Kiểm tra dependency tree của consumer

~~~bash
mvn -f samples/consumer-app/pom.xml dependency:tree
mvn -f samples/consumer-app/pom.xml dependency:tree -Dincludes=com.acme:acme-client
~~~

Kết quả mong đợi khi dùng starter chuẩn:

- Consumer nhận acme-spring-boot-autoconfigure.
- Consumer nhận acme-client qua dependency khai báo trực tiếp của starter.
- Consumer nhận spring-boot-starter trực tiếp hoặc qua starter khác.
- Dependency scope/version đúng với mục tiêu runtime.
- Không có version Acme không mong muốn do một nhánh transitive khác kéo vào.

Nếu consumer chỉ phụ thuộc autoconfigure module, Acme Client optional không tự xuất hiện qua module đó. Đây là một kiểm tra quan trọng để xác nhận optional dependency hoạt động đúng.

## 9. Kiểm tra phát hành bằng Gradle

Nếu publish bằng Gradle, dùng java-library cho module library và maven-publish để tạo publication:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

group = "com.example"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

Tạo artifact trong local Maven repository:

~~~bash
./gradlew :acme-spring-boot-autoconfigure:publishToMavenLocal
./gradlew :acme-spring-boot-starter:publishToMavenLocal
~~~

Sau đó dùng một Maven consumer độc lập hoặc Gradle consumer độc lập để resolve tọa độ đã publish.

Kiểm tra publication:

- JAR đã có AutoConfiguration.imports.
- POM phản ánh đúng dependency và scope.
- File .module có variant compile/runtime dự kiến.
- Annotation processor không bị publish thành runtime dependency.
- compileOnly không vô tình trở thành runtime dependency của consumer.
- api chỉ được dùng khi consumer thật sự cần dependency/type đó trên compile classpath.

Với Gradle, có thể kiểm tra:

~~~bash
./gradlew :consumer-app:dependencies --configuration compileClasspath
./gradlew :consumer-app:dependencies --configuration runtimeClasspath
./gradlew :consumer-app:dependencyInsight --dependency acme-client --configuration runtimeClasspath
~~~

Khi dùng Maven consumer để đọc publication của Gradle, kiểm tra POM được sinh ra. Khi dùng Gradle consumer, kiểm tra cả Gradle Module Metadata vì nó lưu được nhiều thông tin variant hơn POM.

## 10. Checklist phát hành theo từng giai đoạn

### 10.1. Trước khi build

- [ ] Chốt groupId, artifactId, version và tên module có namespace riêng.
- [ ] Chốt phiên bản Java tối thiểu và Spring Boot line được hỗ trợ.
- [ ] Phân biệt rõ autoconfigure module, starter module và consumer sample.
- [ ] Xác định dependency nào bắt buộc, dependency nào optional.
- [ ] Xác định API nào được công bố cho consumer; dependency nào chỉ là implementation detail.
- [ ] Quản lý Spring Boot và third-party versions bằng BOM/parent/version catalog.
- [ ] Không để version SNAPSHOT trong release chính thức.

### 10.2. Auto-configuration imports

- [ ] Có META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports trong autoconfigure module.
- [ ] Mỗi candidate là fully qualified class name trên một dòng.
- [ ] Class name khớp package và class đã compile.
- [ ] Không đăng ký class bằng component scan.
- [ ] Dùng @Import cho cấu hình bổ sung cần thiết.
- [ ] Có condition phù hợp cho classpath, property và user bean.
- [ ] Optional type được cô lập trong nested configuration khi cần.
- [ ] Ordering dùng @AutoConfigureBefore, @AutoConfigureAfter hoặc thuộc tính tương ứng khi có lý do.
- [ ] Nếu đổi tên class đã phát hành, cập nhật imports và replacements file phù hợp.
- [ ] Không dựa vào key EnableAutoConfiguration cũ trong spring.factories.

### 10.3. Metadata

- [ ] Có spring-boot-configuration-processor nếu module có @ConfigurationProperties.
- [ ] Có spring-boot-autoconfigure-processor nếu cần metadata condition để lọc sớm.
- [ ] Processor được khai báo trong annotationProcessor path/configuration.
- [ ] Javadoc property có description rõ, dùng namespace riêng.
- [ ] META-INF/spring-configuration-metadata.json được tạo khi cần.
- [ ] META-INF/spring-autoconfigure-metadata.properties được tạo nếu dùng autoconfigure processor.
- [ ] Manual metadata nằm đúng META-INF/additional-spring-configuration-metadata.json.
- [ ] Metadata phản ánh đúng type, default, deprecation và hint.
- [ ] Đã mở metadata trong JAR đã package, không chỉ trong target/classes hoặc build/classes.

### 10.4. Dependency và publication

- [ ] Dependency Acme trong autoconfigure là optional/compile-only khi thiết kế yêu cầu.
- [ ] Starter khai báo trực tiếp dependency cần cho trải nghiệm mặc định.
- [ ] Starter có spring-boot-starter trực tiếp hoặc gián tiếp.
- [ ] Dependency test không bị lộ ra consumer.
- [ ] api chỉ dùng khi public API yêu cầu compile dependency.
- [ ] implementation được dùng cho implementation detail.
- [ ] POM hoặc Gradle Module Metadata có đúng dependency/scope/variant.
- [ ] Không có version conflict ngoài dự kiến.
- [ ] Không dùng Boot repackage trên library/starter module.

### 10.5. Kiểm thử

- [ ] Unit test condition bằng ApplicationContextRunner.
- [ ] Test default, property override và feature disabled.
- [ ] Test user bean làm default bean back off.
- [ ] Test optional dependency vắng mặt bằng FilteredClassLoader.
- [ ] Test property binding và metadata của @ConfigurationProperties.
- [ ] Test classpath của consumer, không chỉ producer.
- [ ] Có consumer smoke test không import trực tiếp auto-configuration.
- [ ] Có consumer scenario không khai báo optional dependency khi cần chứng minh optional.
- [ ] Test chạy trên Java/Spring Boot version được công bố hỗ trợ.

### 10.6. Kiểm tra artifact và phát hành

- [ ] mvn clean verify hoặc ./gradlew clean build thành công.
- [ ] JAR chứa class và resource cần thiết.
- [ ] Imports file có đúng nội dung.
- [ ] Metadata được đóng gói.
- [ ] Starter JAR không bị repack thành executable archive.
- [ ] POM/.module được kiểm tra sau publish.
- [ ] Consumer độc lập resolve đúng version từ local/staging repository.
- [ ] Consumer khởi động và test tính năng thành công.
- [ ] JAR executable của consumer chạy được bằng java -jar.
- [ ] Release notes, nguồn, Javadoc, license, checksum hoặc signature được bổ sung theo chính sách repository.

## 11. Lỗi thường gặp khi phát hành starter

1. **Imports file nằm sai đường dẫn.** Source có auto-configuration nhưng Boot không phát hiện khi consumer chạy. Kiểm tra đúng resource trong JAR.
2. **Chỉ test bằng AutoConfigurations.of(...).** Test này nạp class trực tiếp, nên không chứng minh imports file đã được đóng gói. Cần thêm consumer smoke test.
3. **Dùng spring.factories theo hướng dẫn Boot cũ.** Boot 3 dùng AutoConfiguration.imports cho candidate auto-configuration.
4. **Auto-configuration bị component scan.** Bean có thể xuất hiện hai lần hoặc phụ thuộc package của ứng dụng. Chỉ đăng ký qua imports.
5. **Thiếu class condition cho optional library.** Consumer không dùng feature vẫn có thể gặp lỗi class loading.
6. **Dependency optional ở autoconfigure nhưng không được thêm lại ở starter.** Consumer thêm starter nhưng runtime thiếu thư viện cần thiết.
7. **Đánh dấu dependency bắt buộc là optional.** Ứng dụng chỉ thêm starter có thể thiếu class khi chạy.
8. **Nhầm hai metadata processor.** Configuration metadata giúp IDE; autoconfigure metadata hỗ trợ lọc condition. Cả hai không thay imports file.
9. **Đặt processor thành runtime dependency.** Processor chỉ cần ở thời gian compile; khai báo trong annotationProcessor path.
10. **Metadata không có description hoặc default đúng.** IDE gợi ý sai hoặc thiếu thông tin; review JSON sau compile.
11. **Starter kéo quá nhiều integration tùy chọn.** Runtime classpath phình to và dễ xung đột version; tách starter theo tính năng.
12. **Dùng api cho mọi dependency.** Consumer compile classpath bị lộ implementation detail và coupling tăng.
13. **Dùng implementation trong khi public API cần type dependency.** Consumer không compile được khi gọi API công bố type đó.
14. **Chỉ kiểm tra dependency tree của producer.** POM/Gradle metadata consumer có thể khác kỳ vọng; kiểm tra từ project tiêu thụ.
15. **Repackage nhầm starter JAR.** Library trở thành nested executable archive và không còn là dependency JAR thông thường.
16. **Consumer test import auto-configuration trực tiếp.** Điều đó che giấu lỗi imports file. Để Spring Boot tự phát hiện qua classpath.
17. **Chỉ chạy test trong reactor.** Consumer có thể vô tình dùng project dependency nội bộ thay vì artifact đã publish. Thử project độc lập với version đã install/publish.
18. **Shade JAR ghi đè imports resource.** Nhiều file cùng đường dẫn có thể bị mất khi gộp archive; cần merge resource đúng cách.
19. **Đổi tên auto-configuration nhưng quên replacements/order/excludes.** Có thể làm cấu hình downstream không tương thích.
20. **Không chạy executable JAR.** IDE hoặc spring-boot:run có thể dùng classpath khác artifact cuối; chạy thử java -jar trên consumer.

## 12. Quy trình release mẫu có thể lặp lại

Với Maven multi-module, một pipeline phát hành có thể chạy:

~~~bash
# 1. Build và test tất cả module
mvn clean verify

# 2. Cài artifact vào local repository để consumer độc lập dùng
mvn -pl acme-spring-boot-autoconfigure,acme-spring-boot-starter -am clean install

# 3. Test consumer độc lập chỉ phụ thuộc starter
mvn -f samples/consumer-app/pom.xml clean verify

# 4. Kiểm tra dependency tree của consumer
mvn -f samples/consumer-app/pom.xml dependency:tree

# 5. Build executable JAR của consumer
mvn -f samples/consumer-app/pom.xml package

# 6. Chạy executable JAR
java -jar samples/consumer-app/target/consumer-app-1.0.0.jar
~~~

Sau build, kiểm tra JAR autoconfigure bằng jar tf và đọc trực tiếp imports file. Nếu consumer pass trong IDE nhưng fail từ executable JAR, so sánh nội dung BOOT-INF/lib, imports resource và manifest của JAR đã package.

Trong CI, nên chạy pipeline với repository sạch hoặc cache được kiểm soát để tránh consumer vô tình resolve nhầm artifact cũ từ Maven local.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Spring Boot 3 tìm auto-configuration candidate trong file nào?  
**Đáp án:** META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports bên trong JAR đã publish.

**Câu 2.** Một dòng trong imports file có định dạng gì?  
**Đáp án:** Fully qualified class name của một auto-configuration class; mỗi class một dòng, có thể có comment bắt đầu bằng #.

**Câu 3.** spring.factories có còn là cách đăng ký auto-configuration theo Boot 2 không?  
**Đáp án:** Không. Boot 3 dùng AutoConfiguration.imports cho auto-configuration candidates; spring.factories vẫn còn các mục đích extension khác.

**Câu 4.** spring-boot-configuration-processor tạo file nào?  
**Đáp án:** META-INF/spring-configuration-metadata.json, dùng để cung cấp metadata và IDE assistance cho @ConfigurationProperties.

**Câu 5.** spring-boot-autoconfigure-processor tạo file nào?  
**Đáp án:** META-INF/spring-autoconfigure-metadata.properties, hỗ trợ Spring Boot lọc sớm auto-configuration theo condition.

**Câu 6.** Vì sao dependency của thư viện bên ngoài thường optional ở autoconfigure module?  
**Đáp án:** Để consumer chỉ dùng autoconfigure có thể tự chọn có đưa thư viện đó vào classpath hay không; starter tiêu chuẩn sẽ khai báo dependency cần thiết trực tiếp.

**Câu 7.** Vì sao không dùng repackage cho starter JAR?  
**Đáp án:** Starter là library/dependency bundle, không phải ứng dụng executable. repackage tạo cấu trúc nested JAR với BOOT-INF, dành cho ứng dụng chạy bằng java -jar.

**Câu 8.** Test ApplicationContextRunner có đủ chứng minh imports file đúng không?  
**Đáp án:** Không nếu test truyền trực tiếp class bằng AutoConfigurations.of(...). Cần kiểm tra artifact và chạy consumer độc lập để chứng minh Boot tự phát hiện từ JAR.

**Câu 9.** Vì sao cần kiểm tra POM hoặc Gradle Module Metadata?  
**Đáp án:** Vì consumer resolve dependency từ metadata đã publish, không đọc build file source của producer.

**Câu 10.** Consumer chỉ thêm starter nhưng thiếu Acme Client ở runtime thì cần kiểm tra gì?  
**Đáp án:** Kiểm tra starter POM/Gradle metadata có khai báo Acme Client trực tiếp, không optional, và dependency tree runtime của consumer có chứa nó không.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, imports file, condition, testing và custom starter: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Reference — Configuration Metadata: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/index.html
- Spring Boot — Generating Your Own Metadata by Using the Annotation Processor: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/annotation-processor.html
- Spring Boot 3.5 Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Executable Jar Format: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html
- Gradle — The Java Library Plugin: https://docs.gradle.org/current/userguide/java_library_plugin.html
- Gradle — The Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Gradle — Gradle Module Metadata: https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html

**Ghi nhớ:** Một starter chỉ sẵn sàng phát hành khi JAR autoconfigure có đúng AutoConfiguration.imports, metadata property/condition được sinh và đóng gói, dependency metadata phản ánh đúng compile/runtime/optional, test condition pass, và một consumer độc lập chỉ khai báo starter vẫn khởi động được. Hãy kiểm tra artifact đã publish thay vì chỉ dựa vào build thành công trong module producer.
