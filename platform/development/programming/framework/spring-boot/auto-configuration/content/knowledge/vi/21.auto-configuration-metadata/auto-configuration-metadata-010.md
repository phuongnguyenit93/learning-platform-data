# Phân biệt metadata phục vụ công cụ với logic quyết định tạo bean

## 1. Mục tiêu: cùng là metadata nhưng không cùng nhiệm vụ

Khi xây dựng Spring Boot starter hoặc thư viện tự cấu hình, bạn có thể gặp nhiều file metadata được tạo trong lúc compile hoặc được đóng gói vào JAR. Tên file khá giống nhau, nhưng chúng phục vụ những giai đoạn khác nhau. Nhầm lẫn giữa chúng dễ dẫn đến các kết luận sai như: “Đã có metadata thì bean tự được tạo”, “IDE gợi ý property nghĩa là ứng dụng chắc chắn xử lý property đó”, hoặc “Xóa file metadata thì điều kiện tạo bean sẽ không còn chạy”.

Bài học này tập trung vào Spring Boot **3.3.13**, Spring Framework 6.1 và Java 17+. Ta sẽ phân biệt bốn thành phần:

1. `META-INF/spring-configuration-metadata.json`: mô tả property để IDE và công cụ cấu hình hỗ trợ gợi ý, completion và tài liệu.
2. `META-INF/spring-autoconfigure-metadata.properties`: metadata điều kiện auto-configuration để Spring Boot có thể lọc sớm những cấu hình không khớp, giúp tối ưu startup.
3. `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`: danh sách lớp auto-configuration candidate mà Spring Boot cần phát hiện.
4. Các API runtime như `@ConfigurationProperties`, `Binder`, `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnMissingBean` và `@Bean`: những thành phần thực sự tham gia bind giá trị, đánh giá điều kiện và đăng ký bean.

**Điểm cốt lõi:** metadata hỗ trợ công cụ và tối ưu xử lý không thay thế logic runtime. Muốn biết một bean có được tạo hay không, hãy lần theo đường đăng ký auto-configuration, property binding, condition và bean definition.

## 2. Bảng phân biệt nhanh

| Thành phần | Ai sử dụng / thời điểm | Mục đích | Có trực tiếp định nghĩa bean không? |
| --- | --- | --- | --- |
| `spring-configuration-metadata.json` | IDE, công cụ hỗ trợ cấu hình | Gợi ý tên property, kiểu, mô tả, default/hints và deprecation | **Không** |
| `spring-autoconfigure-metadata.properties` | Spring Boot khi chọn/lọc auto-configuration | Lọc sớm candidate không khớp condition để cải thiện startup | **Không**; nó mô tả condition phục vụ tối ưu |
| `AutoConfiguration.imports` | Spring Boot khi phát hiện auto-configuration | Đăng ký danh sách lớp auto-configuration candidate | **Không**; candidate vẫn phải vượt qua condition |
| `@ConfigurationProperties` + Binder | Spring runtime khi tạo/bind properties bean | Đọc Environment và bind giá trị vào đối tượng Java | Tạo/bind properties bean khi được đăng ký đúng cách |
| `@Conditional...` + `@Bean` | Spring runtime khi xử lý cấu hình | Quyết định cấu hình/bean method có được áp dụng hay không | **Có**, thông qua bean definition và BeanFactory |

Ba file đầu đều có chữ “metadata” hoặc “imports”, nhưng không thể thay thế lẫn nhau. Cần hiểu cả nơi tạo file lẫn nơi đọc file.

## 3. Configuration metadata: hỗ trợ IDE và công cụ cấu hình

### 3.1. File `spring-configuration-metadata.json` làm gì?

Spring Boot đặt configuration metadata trong JAR tại:

```text
META-INF/spring-configuration-metadata.json
```

File JSON này mô tả các cấu hình được thư viện hỗ trợ. IDE tương thích có thể đọc nó để cung cấp:

- Gợi ý tên property khi viết `application.properties` hoặc `application.yaml`.
- Hoàn thành tên key và một số giá trị thường dùng.
- Kiểu dữ liệu dự kiến, ví dụ `Boolean`, `String`, `Duration` hoặc collection.
- Mô tả giúp người dùng hiểu mục đích property.
- Giá trị mặc định được ghi nhận trong metadata.
- Hint cho những giá trị/option có ý nghĩa.
- Thông tin deprecation và property thay thế.

Ví dụ một phần metadata:

```json
{
  "groups": [
    {
      "name": "acme.greeting",
      "type": "com.acme.greeting.autoconfigure.GreetingProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.greeting.enabled",
      "type": "java.lang.Boolean",
      "description": "Whether the greeting service is enabled.",
      "defaultValue": false
    },
    {
      "name": "acme.greeting.prefix",
      "type": "java.lang.String",
      "description": "Prefix used when creating a greeting.",
      "defaultValue": "Hello"
    }
  ]
}
```

Đây là ví dụ rút gọn để minh họa cấu trúc. File thực tế có thể chứa thêm `sourceType`, `hints`, deprecation và các metadata khác.

### 3.2. Các nhóm thông tin trong JSON

| Nhóm | Nội dung | Công cụ có thể dùng để làm gì? |
| --- | --- | --- |
| `groups` | Nhóm namespace hoặc nhóm property | Hiển thị cấu trúc cấu hình có tổ chức |
| `properties` | Tên property, kiểu, mô tả, default, deprecation | Gợi ý key, giải thích và kiểu giá trị |
| `hints` | Giá trị gợi ý hoặc provider cung cấp gợi ý | Completion cho enum, mode hoặc danh sách giá trị |
| `ignored` | Property được đánh dấu bỏ qua trong metadata | Không đưa property đó vào danh sách gợi ý tương ứng |

Một property có thể không cần group riêng. `groups` chủ yếu giúp công cụ hiểu namespace; `properties` mới mô tả từng key người dùng có thể nhập.

Ví dụ `hints`:

```json
{
  "hints": [
    {
      "name": "acme.greeting.mode",
      "values": [
        {
          "value": "formal",
          "description": "Use a formal greeting."
        },
        {
          "value": "casual",
          "description": "Use a casual greeting."
        }
      ]
    }
  ]
}
```

IDE có thể hiển thị `formal` và `casual` khi người dùng cấu hình property. Nhưng hint **không phải validator runtime**. Nếu ứng dụng cần từ chối giá trị ngoài danh sách, phải có logic bind/validation/condition phù hợp; chỉ thêm hint không làm Spring tự động ném lỗi khi người dùng nhập giá trị khác.

### 3.3. Default trong metadata không phải lệnh gán giá trị runtime

Giả sử metadata mô tả:

```json
{
  "name": "acme.greeting.prefix",
  "type": "java.lang.String",
  "defaultValue": "Hello"
}
```

Giá trị `defaultValue` trong JSON giúp công cụ hiển thị tài liệu/gợi ý. Giá trị thực tế trong ứng dụng đến từ cách properties object được khởi tạo, constructor, cấu hình được bind và logic runtime.

Ví dụ:

```java
@ConfigurationProperties("acme.greeting")
public class GreetingProperties {

    private String prefix = "Hello";

    public String getPrefix() {
        return this.prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
```

Trong trường hợp này, `"Hello"` là giá trị mặc định do Java object cung cấp. Metadata processor có thể suy ra giá trị đó để ghi vào JSON. Nếu ai đó sửa JSON thành `"Hi"` nhưng không sửa Java code, IDE có thể gợi ý `"Hi"` trong khi runtime vẫn khởi tạo `prefix` bằng `"Hello"`. Hai nơi không đồng bộ sẽ khiến tài liệu gây hiểu nhầm.

### 3.4. Metadata không đồng nghĩa property được runtime sử dụng

Một key xuất hiện trong `spring-configuration-metadata.json` không chứng minh:

- Có một bean `@ConfigurationProperties` thực sự bind key đó.
- Có code gọi `Environment.getProperty(...)` để đọc key đó.
- Có `@ConditionalOnProperty` sử dụng key đó.
- Có bean nào được tạo hoặc bị loại vì key đó.
- Runtime sẽ từ chối mọi giá trị không nằm trong hint.

Metadata có thể chứa property khai báo thủ công cho trường hợp key được xử lý bằng `@Value`, `Environment` hoặc logic riêng. Công cụ có thể biết key đó để gợi ý, nhưng ứng dụng chỉ phản ứng nếu mã runtime thực sự đọc hoặc bind nó.

## 4. Tạo configuration metadata bằng annotation processor

### 4.1. `spring-boot-configuration-processor`

Spring Boot cung cấp annotation processor `spring-boot-configuration-processor`. Processor chạy trong quá trình compile và thu thập thông tin từ các class hoặc method được đánh dấu `@ConfigurationProperties` để tạo:

```text
META-INF/spring-configuration-metadata.json
```

Processor không phải một bean và không được gọi để tạo bean khi ứng dụng khởi động. Nó chạy ở **build time** để tạo tài liệu máy đọc được.

### 4.2. Cấu hình Maven

Với Maven, có thể khai báo processor là optional dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

Trong dự án dùng Maven Compiler Plugin với cấu hình annotation processor tường minh, khai báo processor trong `annotationProcessorPaths`. Ví dụ cho Spring Boot 3.3.13 và compiler plugin 3.13.0:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <annotationProcessorPaths>
            <path>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-configuration-processor</artifactId>
                <version>3.3.13</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
```

Chọn một cách cấu hình phù hợp với build hiện tại và tránh cấu hình trùng lặp annotation processing. Nếu dự án sử dụng Lombok, cần bảo đảm thứ tự processor phù hợp để metadata processor nhìn thấy model sau khi Lombok xử lý.

### 4.3. Cấu hình Gradle

Với Gradle, khai báo processor trong configuration riêng:

```groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-configuration-processor"
}
```

Không đặt processor vào `implementation` chỉ để tạo gợi ý IDE. `annotationProcessor` là nơi dành cho công cụ chạy khi biên dịch; consumer không cần mang processor này vào runtime chỉ để bind properties.

### 4.4. Metadata tự động và metadata bổ sung

Processor đọc `@ConfigurationProperties` và mô hình source để tạo phần lớn metadata tự động. Tuy nhiên, có những trường hợp cần bổ sung thủ công:

- Property được xử lý bằng `Environment` hoặc `@Value` mà không có properties class.
- Giá trị mặc định không thể suy ra tĩnh từ source.
- Cần cung cấp thêm hint hoặc mô tả.
- Cần khai báo deprecation/replacement.
- Cần loại một key khỏi metadata được tạo tự động.

File bổ sung có tên:

```text
META-INF/additional-spring-configuration-metadata.json
```

Ví dụ:

```json
{
  "properties": [
    {
      "name": "acme.greeting.mode",
      "type": "java.lang.String",
      "description": "Mode used by the custom greeting strategy."
    }
  ],
  "hints": [
    {
      "name": "acme.greeting.mode",
      "values": [
        {
          "value": "formal",
          "description": "Use a formal greeting."
        },
        {
          "value": "casual",
          "description": "Use a casual greeting."
        }
      ]
    }
  ]
}
```

Processor hợp nhất metadata bổ sung với metadata chính. File bổ sung không tự làm cho `acme.greeting.mode` được bind hoặc được dùng trong condition. Nếu ứng dụng muốn key này có tác dụng, phải bổ sung code runtime đọc hoặc bind nó.

### 4.5. Mô tả property bằng Javadoc

Spring Boot có thể dùng Javadoc của field trong `@ConfigurationProperties` để điền `description`. Nên viết mô tả ngắn, chính xác và bằng plain text:

```java
@ConfigurationProperties("acme.greeting")
public class GreetingProperties {

    /**
     * Whether the greeting service is enabled.
     */
    private boolean enabled;

    /**
     * Prefix used when creating a greeting.
     */
    private String prefix = "Hello";

    // getters and setters
}
```

Với record class, không có field instance theo cách thông thường để gắn field Javadoc; dùng class-level Javadoc tag `@param` cho record component theo hướng dẫn Spring Boot.

## 5. Auto-configuration metadata: hỗ trợ lọc condition sớm

### 5.1. File `spring-autoconfigure-metadata.properties`

Đây là một file khác, thường nằm tại:

```text
META-INF/spring-autoconfigure-metadata.properties
```

Spring Boot có annotation processor riêng là `spring-boot-autoconfigure-processor` để thu thập một số condition metadata của auto-configuration. Nếu file được tạo và có mặt trong JAR, Spring Boot có thể sử dụng nó để **eagerly filter** các auto-configuration không khớp trước khi xử lý đầy đủ, qua đó cải thiện thời gian khởi động.

Điểm cần nhớ:

- Đây không phải file để IDE gợi ý property.
- Nó mô tả condition metadata phục vụ quá trình lọc auto-configuration.
- Nó không thay thế `@ConditionalOnClass`, `@ConditionalOnProperty` hoặc `@ConditionalOnBean` trong source.
- Nó không định nghĩa method `@Bean` và không tạo bean.
- Thiếu file này không đồng nghĩa auto-configuration không thể chạy; Boot vẫn có cơ chế đánh giá condition thông thường.
- Đây là tối ưu xử lý candidate, không phải nơi đặt quy tắc nghiệp vụ mới.

### 5.2. Cấu hình processor cho Maven

Spring Boot 3.3 hướng dẫn thêm `spring-boot-autoconfigure-processor` vào annotation processor paths của Maven Compiler Plugin (phiên bản 3.12.0 trở lên). Ví dụ:

```xml
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
```

Nếu cùng module cũng cần `spring-boot-configuration-processor`, khai báo **cả hai processor** trong `annotationProcessorPaths`. Đặt version đồng bộ với Spring Boot BOM/parent của dự án. Không cấu hình một processor path rồi giả định processor còn lại vẫn tự được phát hiện trên classpath.

### 5.3. Cấu hình Gradle

Với Gradle, processor dùng configuration `annotationProcessor`:

```groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-autoconfigure-processor"
}
```

Nếu cần cả hai loại metadata, khai báo thêm `spring-boot-configuration-processor` trong cùng configuration.

### 5.4. Phân biệt vai trò của hai processor

| Processor | File được tạo | Công dụng |
| --- | --- | --- |
| `spring-boot-configuration-processor` | `spring-configuration-metadata.json` | Mô tả property để IDE/công cụ hỗ trợ cấu hình |
| `spring-boot-autoconfigure-processor` | `spring-autoconfigure-metadata.properties` | Ghi condition metadata để Boot lọc auto-configuration sớm |

Không thay processor này bằng processor kia. Một starter có thể cần cả hai: một để người dùng cấu hình dễ hơn trong IDE, một để Boot tối ưu việc chọn auto-configuration.

## 6. `AutoConfiguration.imports` là đăng ký candidate, không phải metadata gợi ý IDE

Một file khác cũng thường xuất hiện trong JAR:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung liệt kê tên lớp auto-configuration, mỗi dòng một fully qualified class name. Spring Boot đọc file này để tìm các candidate. Sau khi candidate được tìm thấy, condition trên class hoặc bean method vẫn quyết định có áp dụng cấu hình hay không.

| File | Trả lời câu hỏi nào? |
| --- | --- |
| `AutoConfiguration.imports` | Boot cần xem xét những lớp auto-configuration nào? |
| `spring-autoconfigure-metadata.properties` | Có thể loại sớm candidate nào theo condition metadata? |
| `spring-configuration-metadata.json` | IDE nên gợi ý/giải thích những property nào? |

Ví dụ, imports file có thể liệt kê `GreetingAutoConfiguration` nhưng `@ConditionalOnProperty` vẫn không khớp khi `acme.greeting.enabled=false`. Ngược lại, metadata JSON có thể mô tả `acme.greeting.enabled` nhưng nếu auto-configuration không được đăng ký hoặc không có code đọc property thì không có bean nào tự xuất hiện.

## 7. Logic runtime thực sự bind property và tạo bean

### 7.1. Bind property bằng `@ConfigurationProperties`

`@ConfigurationProperties` đánh dấu một class hoặc method chứa cấu hình có kiểu. Tuy nhiên, annotation này cần được đăng ký theo một cơ chế phù hợp, ví dụ:

- `@EnableConfigurationProperties(GreetingProperties.class)`.
- `@ConfigurationPropertiesScan`.
- `@Component` trên class theo mô hình được hỗ trợ.

Khi properties bean được đăng ký, Spring Boot dùng binding infrastructure để đọc `Environment` và gán giá trị vào object. Giá trị thực tế đến từ property sources và default trong Java object/constructor.

### 7.2. Condition quyết định bean có được đăng ký hay không

Ví dụ:

```java
@Bean
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService(GreetingProperties properties) {
    return name -> properties.getPrefix() + ", " + name;
}
```

Ở đây:

- `@ConditionalOnProperty` đọc giá trị từ Spring `Environment`.
- `havingValue = "true"` yêu cầu property có giá trị true theo điều kiện của annotation.
- `@ConditionalOnMissingBean` cho phép người dùng cung cấp implementation riêng.
- Nếu các condition khớp, Spring đăng ký bean definition cho `greetingService`.
- Khi bean được yêu cầu/khởi tạo, method trả về implementation.

`spring-configuration-metadata.json` không tham gia vào phép kiểm tra `enabled` này. Metadata chỉ có thể giúp IDE gợi ý key; condition đọc property thực tế từ Environment.

### 7.3. Một property có thể phục vụ cả binding và condition

Trong ví dụ, `acme.greeting.enabled` được bind vào `GreetingProperties.enabled` và đồng thời được `@ConditionalOnProperty` kiểm tra. Hai hoạt động cùng đọc một nguồn cấu hình nhưng có trách nhiệm khác nhau:

1. Binder đưa giá trị thành boolean trong object `GreetingProperties`.
2. Condition đánh giá Environment để quyết định bean `GreetingService` có được đăng ký không.

Không nên nghĩ rằng file metadata JSON “chuyển” property thành boolean hoặc tự kích hoạt condition. Hai hành vi đó được thực hiện bởi runtime infrastructure.

## 8. Ví dụ Java 17+ chạy độc lập: metadata có và không có bean logic

Ví dụ dưới đây tạo một ứng dụng Spring Boot 3.3.13 có properties class và một auto-configuration. Nó chạy hai context:

- `disabled`: properties bean vẫn được bind, nhưng `GreetingService` không được tạo.
- `enabled`: properties bean được bind và service được tạo khi property bật.

Cùng một code runtime có thể chạy ngay cả khi metadata dành cho IDE không được tạo. Processor chỉ giúp sinh file hỗ trợ công cụ trong quá trình compile.

### 8.1. Cấu trúc dự án

```text
metadata-vs-runtime/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── com/example/demo/MetadataVsRuntimeDemo.java
    │   │   └── com/acme/greeting/autoconfigure/
    │   │       ├── GreetingProperties.java
    │   │       ├── GreetingService.java
    │   │       └── GreetingAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Package ứng dụng là `com.example.demo`; auto-configuration nằm ở `com.acme.greeting.autoconfigure`. Package của thư viện không nằm trong component scan mặc định của ứng dụng. Boot tìm auto-configuration qua imports file.

### 8.2. File `pom.xml`

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
    <artifactId>metadata-vs-runtime</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Hai annotation processor được khai báo riêng trong `annotationProcessorPaths`. Chúng chạy khi compile; không được thêm vào runtime chỉ để ứng dụng bind property hoặc tạo bean.

### 8.3. File `GreetingProperties.java`

Đường dẫn `src/main/java/com/acme/greeting/autoconfigure/GreetingProperties.java`:

```java
package com.acme.greeting.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.greeting")
public class GreetingProperties {

    /**
     * Whether the greeting service is enabled.
     */
    private boolean enabled = false;

    /**
     * Prefix used when creating a greeting.
     */
    private String prefix = "Hello";

    public boolean isEnabled() {
        return this.enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getPrefix() {
        return this.prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
```

Javadoc trên field giúp configuration processor tạo description trong metadata. Default Java field initializer cung cấp giá trị runtime ban đầu khi property không được cấu hình.

### 8.4. File `GreetingService.java`

Đường dẫn `src/main/java/com/acme/greeting/autoconfigure/GreetingService.java`:

```java
package com.acme.greeting.autoconfigure;

public interface GreetingService {
    String greet(String name);
}
```

### 8.5. File `GreetingAutoConfiguration.java`

Đường dẫn `src/main/java/com/acme/greeting/autoconfigure/GreetingAutoConfiguration.java`:

```java
package com.acme.greeting.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true"
    )
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService(
        GreetingProperties properties
    ) {
        return name -> properties.getPrefix() + ", " + name;
    }
}
```

Hai điều cần tách bạch:

- `@EnableConfigurationProperties` đăng ký properties bean để Spring Boot bind giá trị.
- `@ConditionalOnProperty` và `@ConditionalOnMissingBean` quyết định bean service có được đăng ký hay không.

Ngay cả khi `enabled=false`, properties bean vẫn tồn tại vì `@EnableConfigurationProperties` nằm trên auto-configuration class; chỉ bean service bị condition loại.

### 8.6. Resource `AutoConfiguration.imports`

Tạo file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung:

```text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

File này đăng ký candidate auto-configuration. Nó khác với file `spring-configuration-metadata.json` mà IDE đọc.

### 8.7. File `MetadataVsRuntimeDemo.java`

Đường dẫn `src/main/java/com/example/demo/MetadataVsRuntimeDemo.java`:

```java
package com.example.demo;

import com.acme.greeting.autoconfigure.GreetingProperties;
import com.acme.greeting.autoconfigure.GreetingService;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

public class MetadataVsRuntimeDemo {

    public static void main(String[] args) {
        runCase(
            "disabled",
            "--acme.greeting.enabled=false",
            "--acme.greeting.prefix=Hello"
        );

        runCase(
            "enabled",
            "--acme.greeting.enabled=true",
            "--acme.greeting.prefix=Hi"
        );
    }

    private static void runCase(String label, String... args) {
        SpringApplication application =
            new SpringApplication(MetadataVsRuntimeDemo.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context =
                 application.run(args)) {

            GreetingProperties properties =
                context.getBean(GreetingProperties.class);

            boolean serviceExists =
                !context.getBeansOfType(GreetingService.class).isEmpty();

            System.out.printf(
                "%s: propertiesBean=true, enabled=%s, serviceBean=%s%n",
                label,
                properties.isEnabled(),
                serviceExists
            );

            if (serviceExists) {
                GreetingService service =
                    context.getBean(GreetingService.class);
                System.out.println("greeting=" + service.greet("Ada"));
            }
        }
    }
}
```

### 8.8. Build và chạy

Yêu cầu: JDK 17+, Maven và quyền tải dependencies. Trong thư mục `metadata-vs-runtime` chạy:

```bash
mvn -q clean compile spring-boot:run
```

Các dòng do chương trình tự in:

```text
disabled: propertiesBean=true, enabled=false, serviceBean=false
enabled: propertiesBean=true, enabled=true, serviceBean=true
greeting=Hi, Ada
```

Log khởi động Spring có thể xuất hiện tùy logging configuration; ba dòng trên là output của các câu lệnh `System.out` trong chương trình.

**Giải thích kịch bản disabled:**

- Auto-configuration được tìm thấy qua imports file.
- `@EnableConfigurationProperties` đăng ký `GreetingProperties`.
- Binder đọc property command line và gán `enabled=false`.
- `@ConditionalOnProperty` không khớp nên không đăng ký `GreetingService`.

**Giải thích kịch bản enabled:**

- Properties bean được bind với `enabled=true` và `prefix=Hi`.
- Condition khớp.
- Không có bean `GreetingService` do người dùng cung cấp, nên `@ConditionalOnMissingBean` khớp.
- Bean service được đăng ký và trả về `Hi, Ada`.

Không có bước nào trong hai kịch bản cần đọc `spring-configuration-metadata.json` để quyết định bean. Nếu tắt annotation processor nhưng giữ nguyên dependency runtime, imports file, properties class và condition, hành vi bind/bean vẫn được quyết định bởi runtime code.

### 8.9. Kiểm tra các file metadata được tạo

Sau khi compile, dùng PowerShell:

```powershell
Get-Content target/classes/META-INF/spring-configuration-metadata.json
Get-Content target/classes/META-INF/spring-autoconfigure-metadata.properties
Get-Content src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Bạn sẽ thấy ba file có nguồn gốc và mục đích khác nhau:

- `spring-configuration-metadata.json`: property `acme.greeting.enabled` và `acme.greeting.prefix` cùng mô tả/default được suy ra.
- `spring-autoconfigure-metadata.properties`: các condition metadata mà auto-configuration processor thu thập được.
- `AutoConfiguration.imports`: dòng đăng ký `GreetingAutoConfiguration` được bạn viết trong resource source.

Tên key/nội dung cụ thể trong hai file metadata processor tạo ra phụ thuộc condition và source model. Không nên hard-code toàn bộ output của processor thành giao ước; kiểm tra các entry có ý nghĩa cần thiết và dùng test runtime để xác nhận hành vi.

## 9. Khi metadata gợi ý một property nhưng runtime không phản ứng

Giả sử IDE gợi ý:

```properties
acme.greeting.mode=formal
```

Nhưng code runtime chỉ có:

```java
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
```

và `GreetingProperties` không có field `mode`, cũng không có code đọc `acme.greeting.mode`. Khi đó:

- IDE có thể gợi ý `mode` nếu metadata chứa key này.
- Binder không tự tạo field `mode` trong object nếu không có property target phù hợp.
- Condition không kiểm `mode`.
- Bean không thay đổi hành vi chỉ vì `mode=formal` được nhập.

Muốn property có tác dụng, cần thêm cơ chế runtime. Ví dụ thêm field vào `GreetingProperties` và dùng giá trị đó trong service; hoặc viết logic đọc `Environment`; hoặc dùng condition phù hợp. Sau đó metadata nên được cập nhật để mô tả đúng hành vi mới.

**Không dùng metadata để giả lập feature.** Một property được autocomplete không phải bằng chứng tính năng đã được cài đặt.

## 10. Những lỗi phổ biến

| Hiểu nhầm / lỗi | Thực tế | Cách sửa |
| --- | --- | --- |
| Có `spring-configuration-metadata.json` thì bean tự được tạo | JSON chủ yếu hỗ trợ IDE/công cụ | Kiểm imports, runtime conditions và bean definitions |
| Không có configuration metadata thì property không bind được | Binder không phụ thuộc file JSON đó | Đăng ký `@ConfigurationProperties` và kiểm Environment |
| Hint liệt kê giá trị hợp lệ nên runtime tự reject giá trị khác | Hint phục vụ công cụ, không tự là validator | Dùng enum, validation hoặc code kiểm tra phù hợp |
| `defaultValue` trong JSON tự gán default runtime | Default thực tế đến từ object/constructor/binding | Giữ default trong code và metadata đồng bộ |
| `spring-autoconfigure-metadata.properties` giống config metadata JSON | Hai file có consumer và mục đích khác nhau | Phân biệt processor và runtime use |
| Có `spring-autoconfigure-metadata.properties` thì bean chắc chắn được tạo | File hỗ trợ lọc sớm; condition vẫn quyết định | Đọc condition và test bean |
| Có `AutoConfiguration.imports` là mọi bean của class đều xuất hiện | Candidate vẫn có thể bị condition loại | Kiểm condition, property, classpath và bean |
| Thêm processor vào `implementation`/runtime dependency | Processor chỉ cần ở build time | Dùng Maven annotation processor path hoặc Gradle `annotationProcessor` |
| Chỉ viết Javadoc nhưng không cấu hình processor | JSON có thể không được sinh | Cấu hình `spring-boot-configuration-processor` |
| Metadata thủ công mô tả property không có code runtime | IDE có thể gợi ý key không có tác dụng | Chỉ công bố property khi runtime thật sự hỗ trợ, hoặc giải thích rõ mục đích |
| Sửa JSON generated trong target rồi phát hành | File sẽ bị ghi đè ở lần build sau | Dùng `additional-spring-configuration-metadata.json` |
| Dùng một processor để thay cho processor còn lại | Mỗi processor tạo loại metadata khác nhau | Cấu hình đúng cả hai khi module cần cả hai |

## 11. Quy trình debug khi bean không được tạo

Đi theo thứ tự để tránh sửa nhầm metadata:

1. **Xác nhận auto-configuration được đăng ký:** kiểm `AutoConfiguration.imports` trong JAR hoặc candidate list.
2. **Kiểm classpath:** nếu có `@ConditionalOnClass`, xác nhận dependency thật sự hiện diện ở runtime.
3. **Kiểm property thực tế:** đọc `Environment` hoặc cấu hình test; không chỉ nhìn IDE autocomplete.
4. **Kiểm property binding:** xác nhận `@ConfigurationProperties` đã được đăng ký và giá trị trong object đúng.
5. **Kiểm condition:** đọc `ConditionEvaluationReport`, chạy với `--debug` hoặc dùng `ApplicationContextRunner`.
6. **Kiểm user bean:** `@ConditionalOnMissingBean` có thể back off vì ứng dụng đã cung cấp bean tương ứng.
7. **Kiểm bean registration/creation:** xem bean definition và lỗi khởi tạo dependency.
8. **Chỉ sau đó mới kiểm metadata tool:** nếu IDE không gợi ý key, kiểm processor và `spring-configuration-metadata.json`.

Khi vấn đề là “IDE không gợi ý property”, hãy kiểm metadata. Khi vấn đề là “bean không được tạo”, hãy kiểm runtime condition và context. Hai quy trình có thể liên quan nhưng không nên thay thế nhau.

## 12. Bài tập tự kiểm tra

**Câu 1.** `spring-configuration-metadata.json` chủ yếu được dùng để làm gì?  
**Đáp án:** Cung cấp thông tin cho IDE/công cụ cấu hình như tên property, kiểu, mô tả, default và hint để hỗ trợ completion/documentation.

**Câu 2.** Nếu xóa file configuration metadata JSON khỏi JAR nhưng giữ nguyên `@ConfigurationProperties`, Binder và auto-configuration, property còn bind được không?  
**Đáp án:** Có. JSON metadata không phải đầu vào bắt buộc của runtime binder.

**Câu 3.** `spring-autoconfigure-metadata.properties` có vai trò gì?  
**Đáp án:** Chứa condition metadata do processor tạo để Spring Boot lọc sớm auto-configuration không khớp, giúp startup; nó không thay thế condition annotations hoặc bean methods.

**Câu 4.** File nào liệt kê auto-configuration candidate?  
**Đáp án:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

**Câu 5.** IDE gợi ý `acme.greeting.mode=formal`. Điều đó có chứng minh ứng dụng đọc property mode không?  
**Đáp án:** Không. Phải có code runtime bind/đọc property hoặc condition sử dụng nó.

**Câu 6.** `defaultValue` trong JSON khác gì giá trị mặc định trong Java field?  
**Đáp án:** JSON mô tả cho công cụ; field initializer/constructor cung cấp giá trị object runtime trước hoặc khi binding.

**Câu 7.** Muốn có gợi ý IDE cho property không được phát hiện tự động, nên làm gì?  
**Đáp án:** Dùng `META-INF/additional-spring-configuration-metadata.json` để bổ sung metadata; đồng thời bảo đảm runtime có code xử lý property nếu muốn nó thực sự có tác dụng.

**Câu 8.** Có imports file và metadata condition, nhưng bean không xuất hiện. Nên xem gì tiếp?  
**Đáp án:** Condition report, property thực tế, classpath, user bean và kết quả đăng ký bean. Metadata không chứng minh mọi condition đều khớp.

## 13. Ghi nhớ và tài liệu tham khảo

- `spring-configuration-metadata.json` dành cho IDE và công cụ hỗ trợ cấu hình; không tự bind property hoặc tạo bean.
- `spring-autoconfigure-metadata.properties` là metadata condition phục vụ lọc sớm auto-configuration; nó hỗ trợ hiệu năng chứ không thay thế logic condition.
- `AutoConfiguration.imports` đăng ký auto-configuration candidate; các condition vẫn quyết định cấu hình có được áp dụng hay không.
- `@ConfigurationProperties` phải được đăng ký đúng cách; Binder mới đọc Environment và bind giá trị vào object.
- `@Conditional...`, `@Bean` và BeanFactory quyết định bean definition nào được đăng ký.
- Hints và default trong metadata phục vụ công cụ; hãy giữ chúng đồng bộ với runtime code.
- Khi debug, phân biệt lỗi IDE metadata với lỗi binding/condition/bean creation.

Tài liệu chính thức Spring Boot 3.3.13:

1. [Configuration Metadata — mục đích và cách sinh metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html).
2. [Metadata Format — groups, properties, hints, ignored và deprecation](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html).
3. [Generating Your Own Metadata by Using the Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html).
4. [Creating Your Own Auto-configuration — conditions, imports, autoconfigure processor và testing](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
5. [`@ConfigurationProperties` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html).
6. [`@EnableConfigurationProperties` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/EnableConfigurationProperties.html).
7. [`@ConditionalOnProperty` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).
8. [`@AutoConfiguration` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html).
