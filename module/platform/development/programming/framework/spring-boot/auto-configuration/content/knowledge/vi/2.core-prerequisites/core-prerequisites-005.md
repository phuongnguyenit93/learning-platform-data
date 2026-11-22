# Classpath, ClassLoader và sự hiện diện của dependency tùy chọn

> **Phạm vi:** Kiến thức nền tảng để hiểu Spring Boot auto-configuration, minh họa trên Java 17 và Spring Boot 3.3.x. Chủ đề là sự hiện diện của dependency tùy chọn tại **runtime**: vì sao cùng một thư viện nhưng có ứng dụng tạo được bean tự động, ứng dụng khác không tạo; vì sao kiểm tra class có mặt đôi khi vẫn chưa đủ.

## 1. Mục tiêu học tập

Sau bài này, bạn cần trả lời và thực hành được những câu hỏi sau:

1. **Classpath** là gì? Khác nhau thế nào giữa compile classpath, runtime classpath và test classpath?
2. **ClassLoader** dùng để làm gì; việc một file JAR nằm trong bản build có đồng nghĩa JVM hiện tại nhìn thấy mọi class trong JAR đó không?
3. Một dependency được gọi là **optional** có nghĩa gì đối với người xây thư viện và đối với ứng dụng tiêu thụ?
4. Spring Boot đánh giá `@ConditionalOnClass` và `@ConditionalOnMissingClass` như thế nào; khi nào cần dùng `name` thay vì `value`?
5. Làm thế nào để thiết kế và kiểm thử tích hợp tùy chọn mà ứng dụng vẫn khởi động khi JAR tích hợp không tồn tại?

Nguyên tắc xuyên suốt: **Classpath quyết định những class có thể được tìm thấy; ClassLoader quyết định phạm vi nhìn thấy và cách nạp class; auto-configuration dùng điều kiện để quyết định có đăng ký bean hay không.** Ba việc liên quan nhau nhưng không đồng nhất.

## 2. Classpath là gì?

Một chương trình Java được biên dịch từ `.java` thành `.class`. Để biên dịch và chạy chương trình, công cụ và JVM cần biết nơi có thể tìm các class và tài nguyên liên quan. Tập các đường dẫn đến thư mục chứa `.class` và các JAR dùng trong một ngữ cảnh được gọi chung là **classpath**.

Trong dự án có build tool, không nên nghĩ classpath chỉ có một danh sách bất biến:

| Ngữ cảnh | Mục đích | Ví dụ dependency có thể xuất hiện |
| --- | --- | --- |
| **Compile classpath** | `javac` phân giải tên type, method, field lúc biên dịch | API cần để code nguồn biên dịch |
| **Runtime classpath** | JVM / framework nạp class và resource khi ứng dụng chạy | Implementation, JDBC driver, SDK, bộ tích hợp tùy chọn |
| **Test classpath** | Biên dịch/chạy test; thường mở rộng classpath khác | JUnit, AssertJ, test container, mock library |
| **Classpath của một ClassLoader cụ thể** | Phạm vi class và resource mà loader đó có thể nhìn thấy | Có thể là một tập con của runtime toàn ứng dụng, tùy topology loader |

Một class có thể có mặt ở compile classpath nhưng **vắng mặt lúc chạy**. Ngược lại, một JDBC driver có thể chỉ cần ở runtime classpath nếu ứng dụng không trực tiếp dùng class của driver trong source.

### 2.1. Ví dụ Java độc lập, chạy bằng JDK 17

Tạo file `ClasspathProbe.java`:

```java
public class ClasspathProbe {
    public static void main(String[] args) {
        String target = args.length == 0
                ? "java.time.Instant"
                : args[0];

        ClassLoader loader = Thread.currentThread()
                .getContextClassLoader();

        try {
            Class<?> type = Class.forName(target, false, loader);
            System.out.println("PRESENT: " + type.getName());
        } catch (ClassNotFoundException ex) {
            System.out.println("ABSENT: " + target);
        }
    }
}
```

Chạy:

```bash
javac ClasspathProbe.java
java ClasspathProbe
java ClasspathProbe example.missing.OptionalClient
```

Hai dòng kết quả do chương trình in, tương ứng hai lệnh `java`:

```text
PRESENT: java.time.Instant
ABSENT: example.missing.OptionalClient
```

`Class.forName(name, false, loader)` yêu cầu tìm và liên kết class theo loader cho trước nhưng **không chủ động chạy static initializer** của class đó. `false` không có nghĩa là mọi lỗi liên kết đều bị loại trừ. Nếu class tồn tại nhưng còn phụ thuộc type khác bị thiếu, có thể xuất hiện `LinkageError`, chẳng hạn `NoClassDefFoundError`.

Ví dụ chỉ đo khả năng tìm thấy class bằng loader hiện tại. Nó **không** chứng minh bean Spring được tạo, tài nguyên bên ngoài sẵn sàng, database kết nối được, hoặc API giữa hai thư viện tương thích.

### 2.2. Thêm JAR qua `-cp` không tự bật mọi tính năng

Giả sử có thư viện `vendor-client.jar`:

```bash
java -cp "app.jar:vendor-client.jar" com.example.Main
```

Trên Linux/macOS, dấu phân cách classpath truyền thống là `:`; trên Windows là `;`:

```powershell
java -cp "app.jar;vendor-client.jar" com.example.Main
```

Đây là ví dụ lệnh của **Java classpath truyền thống**. Spring Boot executable JAR thường có thư viện nằm bên trong `BOOT-INF/lib` và cơ chế launcher riêng; lệnh `java -jar app.jar` không xử lý `-cp` theo cách thêm JAR ngoài tùy ý. Khi điều tra ứng dụng Spring Boot đóng gói, cần nhìn vào cách launcher và build plugin thực sự tạo runtime classpath.

Việc thêm `vendor-client.jar` chỉ tạo cơ hội cho class được nhìn thấy. Spring Boot vẫn phải chọn được auto-configuration, các class condition/bean condition/property condition phải khớp, và bean phải khởi tạo thành công.

## 3. ClassLoader: ai nhìn thấy class nào?

`ClassLoader` là cơ chế JVM dùng để tìm bytecode, định nghĩa class và tìm resource. Các loader chuẩn trong Java hiện đại có phân cấp bootstrap, platform và application; ngoài ra framework, máy chủ ứng dụng hoặc plugin system có thể tạo loader riêng.

Mô hình thường gặp:

```text
Bootstrap loader
  -> các class nền tảng của Java
         |
         v
Platform loader
  -> các module nền tảng được platform loader quản lý
         |
         v
Application / System ClassLoader
  -> classpath ứng dụng, dependency runtime
         |
         v
Custom loader (khi được sử dụng)
  -> JAR plugin, module con, phạm vi cô lập
```

**Parent delegation** là hành vi phổ biến: loader thường nhờ parent tìm class trước khi tự tìm. Đây không phải quy luật cứng cho mọi custom loader. Trong container hoặc plugin system, hai loader có thể nhìn thấy tập JAR khác nhau.

Một class trong JVM không chỉ được nhận diện bằng tên đầy đủ như `com.vendor.Client`; **loader định nghĩa class cũng là một phần của danh tính type**. Hai loader khác nhau định nghĩa cùng tên class có thể tạo thành hai type khác nhau, dẫn tới lỗi cast hoặc injection khó hiểu. Đừng mặc định “cùng tên class” là cùng type ở mọi môi trường.

### 3.1. Thread Context ClassLoader

Nhiều framework dùng `Thread.currentThread().getContextClassLoader()` (TCCL) để khám phá thư viện/resource theo ngữ cảnh luồng gọi. Nó có thể khác loader của class đang chạy.

Một số API để phân biệt:

| API | Cho bạn biết gì? | Điểm cần nhớ |
| --- | --- | --- |
| `SomeType.class.getClassLoader()` | Loader định nghĩa `SomeType` | Có thể trả `null` đối với class do bootstrap loader định nghĩa |
| `Thread.currentThread().getContextClassLoader()` | Loader ngữ cảnh của thread | Có thể thay đổi theo môi trường; không nhất thiết là loader tạo class hiện tại |
| `Class.forName(name, false, loader)` | Yêu cầu tìm/liên kết class với loader được chọn | Có thể ném `ClassNotFoundException` hoặc lỗi liên kết khác |
| `loader.loadClass(name)` | Tìm/nạp class thông qua loader | Không mặc định kích hoạt static initialization |
| `loader.getResource("META-INF/...")` | Tìm một resource theo đường dẫn | Tìm thấy resource không chứng minh mọi class liên quan có thể nạp thành công |

Spring Boot còn có các abstraction đọc metadata mà **không cần khởi tạo class trước**; điểm này rất quan trọng đối với thư viện có phụ thuộc tùy chọn.

### 3.2. Loading, linking và initialization không phải một việc

Khái quát vòng đời class:

1. **Loading:** tìm bytecode và tạo đại diện `Class`.
2. **Linking:** xác minh bytecode, chuẩn bị trạng thái, phân giải tham chiếu theo quy tắc JVM; không phải mọi tham chiếu đều bắt buộc được phân giải cùng một thời điểm.
3. **Initialization:** chạy static initializer và phần khởi tạo static field tương ứng.

Đặt `SomeOptionalType.class` hoặc `new SomeOptionalType()` ở một vị trí được nạp quá sớm có thể khiến ứng dụng không kịp xét điều kiện. Ngược lại, chỉ đọc annotation metadata bằng parser thích hợp có thể tránh nạp type tùy chọn lúc chưa cần.

## 4. Dependency tùy chọn thực sự có nghĩa gì?

Có hai câu hỏi tách biệt:

- **Dependency resolution:** Build tool có đưa artifact đó vào classpath của **ứng dụng tiêu thụ** không?
- **Runtime condition:** Tại thời điểm Spring Boot đánh giá, loader liên quan có nhìn thấy class đánh dấu tính năng không?

Khai báo tùy chọn tác động đến cách dependency được truyền cho bên tiêu thụ. Nó **không** tự tạo điều kiện cho Spring, và không ngăn thư viện đang được biên dịch/test của bạn dùng class đó.

### 4.1. Maven: `optional=true`

Trong POM của thư viện tích hợp:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <optional>true</optional>
</dependency>
```

Ở **chính project** khai báo dependency, Jackson vẫn tham gia các classpath theo scope của dependency (mặc định là `compile`, nên có cả runtime của project đó). Khi một ứng dụng khác thêm thư viện của bạn làm dependency, Maven **không tự truyền Jackson như transitive dependency** từ cạnh được đánh dấu optional này. Ứng dụng muốn dùng tính năng Jackson cần khai báo dependency thích hợp hoặc dùng một starter có chủ đích cung cấp nó.

Do đó không được hiểu `optional=true` là “JAR này vắng mặt cả trong project đang chạy thử” hay “Spring tự biết bỏ bean”. Spring cần điều kiện classpath để quyết định bean.

### 4.2. Gradle: `compileOnly`, `implementation`, `runtimeOnly`

Ví dụ Gradle Groovy DSL cho **module autoconfigure**:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
    compileOnly 'com.fasterxml.jackson.core:jackson-databind'
    testImplementation 'com.fasterxml.jackson.core:jackson-databind'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là **đoạn cấu hình minh họa**, chưa phải file Gradle độc lập: cần quản lý version qua Spring Boot BOM/plugin hoặc ràng buộc version ở project thực tế. Trong module này, `compileOnly` cho phép code tích hợp compile với Jackson nhưng không đưa Jackson vào runtime classpath từ chính khai báo đó; `testImplementation` đưa Jackson vào môi trường test. Nếu ứng dụng tiêu thụ cần tính năng, chính ứng dụng/starter phải cung cấp runtime dependency.

| Cấu hình Gradle | Ý nghĩa thường gặp đối với `java-library` |
| --- | --- |
| `api` | Dependency thuộc API công khai mà consumer cũng cần để biên dịch |
| `implementation` | Dependency nội bộ để compile/run module, được đưa vào runtime dependency của consumer theo metadata phù hợp |
| `compileOnly` | Chỉ cần khi compile module; không có nghĩa consumer sẽ tự nhận dependency |
| `runtimeOnly` | Cần lúc chạy nhưng không dùng trực tiếp để compile source |
| `testImplementation` | Dependency dùng cho test của module, không đồng nghĩa runtime của consumer |

**Lưu ý:** Maven `optional` và Gradle `compileOnly` không phải hai từ khóa có cơ chế xuất bản metadata hoàn toàn giống nhau. Hãy kiểm tra POM/Gradle Module Metadata được phát hành và classpath **thực tế của consumer**.

### 4.3. “Có dependency” chưa đủ để bật auto-configuration

| Tình huống | Kết quả có thể xảy ra |
| --- | --- |
| Jackson có trong compile classpath nhưng không ở runtime | Code compile nhưng `@ConditionalOnClass(ObjectMapper)` không match khi chạy; hoặc lỗi liên kết nếu code tham chiếu sai cách |
| Jackson có ở runtime nhưng property `demo.json.enabled=false` | Class condition match, property condition ngăn cấu hình mặc định |
| Jackson có ở runtime và không có bean do app tự cung cấp | Auto-configuration có thể tạo bean nếu toàn bộ điều kiện khác đều khớp |
| Jackson có ở runtime và app đã có `MessageEncoder` | `@ConditionalOnMissingBean` khiến bean mặc định back off |
| JAR nằm đâu đó trên máy nhưng không thuộc classpath mà loader dùng | Không thể kết luận class hiện diện cho Spring Boot |
| Một class có tên đúng nhưng API phiên bản không tương thích | Có thể match class condition ban đầu rồi vẫn lỗi khi liên kết/khởi tạo/sử dụng |

## 5. Spring Boot kiểm tra sự hiện diện của class thế nào?

Spring Boot dùng condition trong quá trình xử lý auto-configuration. Những annotation liên quan:

```java
@ConditionalOnClass(name = "com.vendor.OptionalClient")
@ConditionalOnMissingClass("com.vendor.LegacyClient")
```

Hai dòng trên là **mẫu annotation độc lập về mặt cú pháp đặt trên class cấu hình**, không phải một file `.java` chạy được. `@ConditionalOnClass` yêu cầu class hiện diện; `@ConditionalOnMissingClass` yêu cầu không hiện diện. Đây là điều kiện dựa trên tên class trong loader, không kiểm tra bean đã được tạo hay phương thức được gọi thành công.

### 5.1. `value` và `name`

Spring Boot 3.3 đọc **annotation metadata của class cấu hình bằng ASM**. Vì vậy với annotation `@ConditionalOnClass` gắn **trực tiếp trên class cấu hình**, cú pháp dùng class literal có thể an toàn ngay cả khi type không có ở runtime:

```java
@ConditionalOnClass(com.vendor.OptionalClient.class)
```

Khi type thực sự là optional, dùng chuỗi tên để biểu lộ ranh giới, tránh tham chiếu compile-time ở lớp ngoài:

```java
@ConditionalOnClass(name = "com.vendor.OptionalClient")
```

**Ngoại lệ quan trọng:** Nếu bạn viết một **meta-annotation tự tạo** chứa `@ConditionalOnClass` hay `@ConditionalOnMissingClass`, hãy dùng thuộc tính `name` thay vì dựa vào `value`; cơ chế xử lý metadata không giống annotation trực tiếp trên configuration class.

### 5.2. Không đặt toàn bộ rủi ro ở `@Bean` method

Mẫu dễ gây sự cố khi class `OptionalClient` không có ở runtime:

```java
// MINH HỌA SAI: chỉ dùng để phân tích, không phải file compile độc lập.
@Bean
@ConditionalOnClass(name = "com.vendor.OptionalClient")
com.vendor.OptionalClient optionalClient() {
    return new com.vendor.OptionalClient();
}
```

Dù `@ConditionalOnClass` đặt trên method, Spring/JVM có thể cần kiểm tra cấu trúc class cấu hình và **return type** của `@Bean` trước khi condition trên method được áp dụng. Khi type không tồn tại, có thể xảy ra `NoClassDefFoundError` hoặc lỗi phân tích metadata trước khi cấu hình được loại trừ.

**Thiết kế đúng:** cô lập bean phụ thuộc thư viện optional trong **một class `@Configuration` riêng hoặc static nested configuration**, và đặt class condition ở chính class bảo vệ đó. Lớp auto-configuration bên ngoài không được buộc JVM tải optional type ngay khi vừa được phát hiện.

### 5.3. Khi nào cần cả class, property và bean condition?

- `@ConditionalOnClass`: có đủ API để **có thể** tích hợp.
- `@ConditionalOnProperty`: ứng dụng **cho phép** tích hợp chạy theo lựa chọn cấu hình.
- `@ConditionalOnMissingBean`: ứng dụng **chưa tự cung cấp** bean tương ứng, nên thư viện mới dùng mặc định.
- Các condition khác như `@ConditionalOnWebApplication`, `@ConditionalOnResource`: chỉ thêm khi đó thật sự là điều kiện của tính năng.

Đừng sử dụng class condition thay cho việc kiểm tra tương thích phiên bản API hoặc khả năng truy cập dịch vụ. Một class có thể tồn tại nhưng constructor/method đổi chữ ký; bean có thể khởi tạo nhưng endpoint bên ngoài bị từ chối kết nối.

## 6. Demo hoàn chỉnh: Jackson có hoặc không có trên runtime classpath

Ta làm một ứng dụng nhỏ có `MessageEncoder` là **hợp đồng lõi không phụ thuộc Jackson**. Khi Jackson hiện diện, auto-configuration tạo encoder mặc định; khi Jackson vắng mặt hoặc bị tắt, ứng dụng vẫn khởi động và báo tính năng chưa sẵn sàng. App có thể tạo encoder riêng mà không phụ thuộc vào default của thư viện.

### 6.1. Cấu trúc source

```text
optional-classpath-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── optional/
    │   │       ├── MessageEncoder.java
    │   │       └── autoconfigure/OptionalJacksonAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/example/optional/autoconfigure/
        └── OptionalJacksonAutoConfigurationTest.java
```

Trong demo một Maven project giúp chạy nhanh. Khi phát hành thư viện thật, tách API/core, autoconfigure và starter thành các artifact phù hợp. Package của ứng dụng `com.example.app` **không bao phủ** package `com.example.optional.autoconfigure`, giúp quan sát đúng việc Spring Boot tìm cấu hình qua file imports.

### 6.2. Build file có dependency Jackson optional

Tạo `pom.xml`:

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

    <groupId>com.example</groupId>
    <artifactId>optional-classpath-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <optional>true</optional>
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

Spring Boot parent quản lý version Jackson tương thích với nhánh Boot 3.3. `optional=true` chỉ ngăn truyền Jackson theo đường transitive tới **ứng dụng khác**; nó vẫn nằm trong runtime classpath của **project demo này**. Để kiểm thử “Jackson vắng mặt”, ta dùng `FilteredClassLoader` thay vì giả vờ rằng đánh dấu optional làm Jackson tự biến mất trong project hiện tại.

### 6.3. API lõi không nhắc đến Jackson

Tạo `src/main/java/com/example/optional/MessageEncoder.java`:

```java
package com.example.optional;

@FunctionalInterface
public interface MessageEncoder {
    String encode(String message);
}
```

Interface này chỉ phụ thuộc JDK. Consumer có thể dùng API mà không buộc phải có `ObjectMapper`; đó là ranh giới rất quan trọng nếu tích hợp Jackson thực sự optional.

### 6.4. Auto-configuration cô lập phần có Jackson

Tạo `src/main/java/com/example/optional/autoconfigure/OptionalJacksonAutoConfiguration.java`:

```java
package com.example.optional.autoconfigure;

import com.example.optional.MessageEncoder;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class OptionalJacksonAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
    @ConditionalOnProperty(
            prefix = "demo.json",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(MessageEncoder.class)
        MessageEncoder messageEncoder() {
            ObjectMapper mapper = new ObjectMapper();

            return message -> {
                try {
                    return mapper.writeValueAsString(Map.of("message", message));
                } catch (JsonProcessingException ex) {
                    throw new IllegalStateException("Cannot encode message", ex);
                }
            };
        }
    }
}
```

Phân tích kỹ:

- Lớp ngoài `OptionalJacksonAutoConfiguration` không dùng Jackson trong constructor, superclass, interface hoặc `@Bean` method. Spring Boot có thể phát hiện lớp này khi Jackson không có.
- Lớp lồng `JacksonConfiguration` mới chứa các import và lời gọi Jackson; nó được **bảo vệ ở mức configuration class** bằng `@ConditionalOnClass(name=...)`.
- `@ConditionalOnProperty` cho người dùng tắt tích hợp bằng `demo.json.enabled=false`. Không có key thì bật mặc định, **nếu** Jackson hiện diện.
- `@ConditionalOnMissingBean(MessageEncoder.class)` khiến thư viện không đăng ký encoder mặc định khi ứng dụng đã có encoder riêng.
- JSON được tạo bằng `ObjectMapper` trên `Map` có một entry. Exception checked `JsonProcessingException` được chuyển thành exception runtime để đáp ứng interface không khai báo checked exception.
- Vì demo tạo `ObjectMapper` bằng `new`, đây chỉ là một bộ mã hóa nhỏ để minh họa class condition. Trong thư viện production, hãy cân nhắc tận dụng `ObjectMapper` do ứng dụng tùy biến cung cấp nếu đó là hợp đồng mong muốn; đồng thời xét rõ điều kiện bean và chính sách cấu hình chung.

**Lưu ý quan trọng:** Đây là ví dụ sử dụng Jackson khi *library hiện diện*, không phải cơ chế đảm bảo mọi phiên bản Jackson đều tương thích. Nếu code biên dịch với phiên bản mới nhưng consumer dùng phiên bản cũ thiếu method, điều kiện class vẫn có thể match và lỗi liên kết xảy ra lúc chạy.

### 6.5. Công bố auto-configuration đúng chuẩn Spring Boot 3.x

Tạo file có tên chính xác:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.optional.autoconfigure.OptionalJacksonAutoConfiguration
```

Spring Boot đọc metadata để tìm các auto-configuration ứng viên. `@AutoConfiguration` một mình không đủ bảo đảm auto-configuration được tìm thấy trong ứng dụng khác nếu không có imports file. Trong thư viện chia JAR, file này phải được đóng gói ở JAR chứa auto-configuration. Tránh `@ComponentScan` toàn package của thư viện, vì có thể bypass ranh giới điều kiện hoặc quét bean không mong muốn.

### 6.6. Ứng dụng tiêu thụ xử lý trường hợp tính năng không có

Tạo `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.optional.MessageEncoder;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printMessage(ObjectProvider<MessageEncoder> providers) {
        return args -> {
            MessageEncoder encoder = providers.getIfAvailable();
            System.out.println(encoder == null
                    ? "JSON integration disabled"
                    : encoder.encode("Xin chào"));
        };
    }
}
```

`ObjectProvider<MessageEncoder>` cho phép ứng dụng **không yêu cầu bắt buộc** phải có bean encoder ngay khi tạo `ApplicationRunner`. Như vậy demo có thể chứng minh cả tình huống có lẫn không có Jackson. Nếu thay `ObjectProvider` bằng tham số `MessageEncoder` bắt buộc, khi condition không match mà không có bean riêng, ứng dụng sẽ lỗi injection: đó là lỗi hợp đồng giữa consumer và tùy chọn tính năng, không phải lỗi của `@ConditionalOnClass`.

Chạy tại thư mục chứa `pom.xml` bằng Maven và JDK 17+:

```bash
mvn test
mvn spring-boot:run
```

Vì Jackson tồn tại trong runtime classpath của **project demo** và mặc định `demo.json.enabled` chưa bị tắt, `ApplicationRunner` in **một dòng**:

```text
{"message":"Xin chào"}
```

Đây là dòng do chương trình in; log khởi động và log Maven có thể xuất hiện thêm. Để thử property condition, tạo `src/main/resources/application.properties` với nội dung:

```properties
demo.json.enabled=false
```

Sau đó chạy lại `mvn spring-boot:run`. Dòng từ `ApplicationRunner` chuyển thành:

```text
JSON integration disabled
```

Để ứng dụng tự cung cấp encoder, xóa property `demo.json.enabled=false`, rồi **thêm method sau vào bên trong `DemoApplication`**:

```java
@Bean
MessageEncoder applicationEncoder() {
    return value -> "App: " + value;
}
```

Đây là **đoạn bổ sung**, không phải file Java độc lập. Kết quả một dòng từ runner:

```text
App: Xin chào
```

Nhờ `@ConditionalOnMissingBean`, bean mặc định của auto-configuration nhường chỗ. Dù Jackson có trên classpath, ứng dụng có quyền chọn encoder riêng.

## 7. Test chính xác hai trạng thái classpath bằng FilteredClassLoader

Ứng dụng demo chỉ có một tập dependency thực tại một thời điểm. Để kiểm thử hành vi “có Jackson” và “không có Jackson” mà không đổi POM liên tục, Spring Boot cung cấp `FilteredClassLoader`. Loader thử nghiệm cố tình che một class/package; condition sẽ nhìn thấy môi trường tương ứng.

Tạo `src/test/java/com/example/optional/autoconfigure/OptionalJacksonAutoConfigurationTest.java`:

```java
package com.example.optional.autoconfigure;

import com.example.optional.MessageEncoder;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalJacksonAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            OptionalJacksonAutoConfiguration.class));

    @Test
    void createsEncoderWhenJacksonPresent() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(MessageEncoder.class);
            assertThat(context.getBean(MessageEncoder.class)
                    .encode("Lan")).isEqualTo("{\"message\":\"Lan\"}");
        });
    }

    @Test
    void skipsEncoderWhenJacksonAbsent() {
        runner.withClassLoader(new FilteredClassLoader(ObjectMapper.class))
                .run(context -> assertThat(context)
                        .doesNotHaveBean(MessageEncoder.class));
    }

    @Test
    void skipsEncoderWhenDisabledByProperty() {
        runner.withPropertyValues("demo.json.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(MessageEncoder.class));
    }

    @Test
    void applicationBeanOverridesLibraryDefault() {
        runner.withUserConfiguration(UserEncoderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(MessageEncoder.class);
                    assertThat(context.getBean(MessageEncoder.class)
                            .encode("Lan")).isEqualTo("App: Lan");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserEncoderConfiguration {

        @Bean
        MessageEncoder appEncoder() {
            return message -> "App: " + message;
        }
    }
}
```

Chạy:

```bash
mvn test
```

Bốn test tương ứng bốn hợp đồng:

| Test | Giả lập / thiết lập | Điều phải đúng |
| --- | --- | --- |
| `createsEncoderWhenJacksonPresent` | Jackson được load trong test runtime | Có đúng một encoder mặc định |
| `skipsEncoderWhenJacksonAbsent` | `FilteredClassLoader` che `ObjectMapper` | Context vẫn chạy, không có encoder mặc định |
| `skipsEncoderWhenDisabledByProperty` | Property tắt tích hợp | Không có encoder mặc định |
| `applicationBeanOverridesLibraryDefault` | App định nghĩa encoder | Chỉ có encoder của ứng dụng |

`ApplicationContextRunner` phù hợp để kiểm tra từng tổ hợp condition, nhưng **không chạy trong native-image test mode**. Ngoài ra, `withConfiguration(AutoConfigurations.of(...))` chỉ định trực tiếp class; các test trên **chưa kiểm chứng** quá trình tìm kiếm `AutoConfiguration.imports` khi đóng gói JAR. Muốn kiểm tra khả năng công bố ra ngoài, cần thêm integration test ở dự án consumer hoặc kiểm tra resource trong JAR thật.

### 7.1. Kiểm tra classpath ở cả build và runtime

Trong Maven:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
mvn dependency:build-classpath
```

Trong Gradle dùng plugin Java:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Lệnh Gradle minh họa cần project có wrapper tương ứng; trên Windows dùng `gradlew.bat`. Kiểm tra test classpath riêng khi test nhìn thấy Jackson nhưng ứng dụng production không thấy.

Các lệnh này cho biết dependency **được build tool giải quyết** thế nào. Với executable JAR, container, classloader riêng hoặc các runtime khác nhau, vẫn phải kiểm tra artifact và cơ chế nạp thực tế. `mvn dependency:tree` không thay thế hoàn toàn bằng chứng class đã được loader trong JVM tìm thấy.

## 8. Vì sao vẫn gặp ClassNotFoundException hoặc NoClassDefFoundError?

Hai lỗi thường xuất hiện ở những giai đoạn khác nhau:

- **`ClassNotFoundException`:** thường gặp khi code chủ động tìm class theo tên, chẳng hạn `Class.forName("com.vendor.Client")`, nhưng loader không tìm thấy định nghĩa class. Đây là checked exception.
- **`NoClassDefFoundError`:** lỗi liên kết ở runtime (subclass của `LinkageError`), thường gặp khi JVM cố dùng một class mà định nghĩa cần thiết không khả dụng; cũng có thể xảy ra sau khi static initialization của class trước đó đã thất bại. Nó **không đơn giản chỉ là tên khác của `ClassNotFoundException`**.
- **`NoSuchMethodError` / `NoSuchFieldError`:** class có thể tồn tại, nhưng API runtime thiếu method/field mà bytecode đã biên dịch mong đợi; thường liên quan version không tương thích.
- **`ClassCastException`:** type không tương thích; trong hệ thống plugin, một nguyên nhân có thể là cùng tên class do hai ClassLoader khác nhau định nghĩa.

Tình huống cụ thể:

```text
autoconfigure.jar
    |
    +-- OptionalJacksonAutoConfiguration
    |       |
    |       +-- @ConditionalOnClass("ObjectMapper")
    |               |
    |               +-- Jackson chưa có -> bỏ qua JacksonConfiguration
    |               |
    |               +-- Jackson có -> tiếp tục kiểm tra property/bean
    |
    +-- API MessageEncoder (không phụ thuộc Jackson)
```

Nếu thiếu Jackson nhưng startup vẫn lỗi `NoClassDefFoundError: com/fasterxml/jackson/databind/ObjectMapper`, hãy điều tra **chỗ tham chiếu nào bị nạp sớm**, nhất là kiểu trả về của `@Bean`, superclass/interface, static initializer và class cấu hình chưa được cô lập, thay vì chỉ thêm condition lên method một cách máy móc.

Nếu class hiện diện nhưng báo `NoSuchMethodError`, kiểm tra version đã được resolve, dependency conflict và chữ ký method thực tế. `@ConditionalOnClass` chỉ kiểm tra class hiện diện chứ không xác nhận API phù hợp với version lúc compile.

## 9. Quy trình điều tra khi auto-configuration không hoạt động

Đọc bằng chứng theo thứ tự hợp lý, tránh đoán từ mỗi tên starter:

1. **Xác nhận đúng artifact:** app đang chạy phiên bản build nào, có deploy image/JAR mới nhất không? Phần dependency optional có nằm trong runtime không?
2. **Kiểm tra đường phụ thuộc:** `mvn dependency:tree` hoặc Gradle `runtimeClasspath`; tìm exclude, `provided`, `compileOnly`, `runtimeOnly`, xung đột phiên bản, phạm vi `test`.
3. **Kiểm tra file imports:** trong JAR thư viện phải có `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` và tên auto-configuration đúng.
4. **Kiểm tra loader thực tế:** ai đang load app, có custom loader, container, plugin layer hoặc khác biệt TCCL không? Đường dẫn JAR được nhìn thấy bởi loader này chứ?
5. **Đọc condition report:** khởi động Spring Boot với `--debug`, đọc positive/negative matches. Hoặc dùng `ConditionEvaluationReport` trong test. Điều kiện class, property và bean cần phân biệt.
6. **Kiểm tra bean do ứng dụng tự định nghĩa:** `@ConditionalOnMissingBean` có thể đã back off. Đó là hành vi đúng, không nhất thiết là lỗi.
7. **Nếu lỗi khi khởi động:** đọc *cause* gốc trong stack trace. `ClassNotFoundException`, `NoClassDefFoundError` và `NoSuchMethodError` chỉ đến những hướng sửa khác nhau.
8. **Kiểm thử cả hai classpath:** viết test `FilteredClassLoader` cho thiếu dependency và test thường cho hiện diện; bổ sung test application override và property disable.
9. **Kiểm tra package/module boundary:** auto-configuration đừng bị component scan nhận ngoài ý muốn; tránh đưa optional library type vào API/core không tùy chọn.

Spring Boot hỗ trợ condition report bằng `--debug` hoặc cấu hình logging phù hợp. Có thể dùng endpoint Actuator `/actuator/conditions` nếu có Actuator và endpoint được cấu hình cho phép truy cập; không nên mở thông tin chẩn đoán rộng rãi trên production.

### 9.1. Cách đọc một kết quả negative match

Giả sử báo cáo cho thấy:

```text
OptionalJacksonAutoConfiguration.JacksonConfiguration did not match:
    - @ConditionalOnClass did not find required class
      'com.fasterxml.jackson.databind.ObjectMapper'
```

Đây là **mẫu mô phỏng ý nghĩa**, không cam kết từng ký tự của log ở mọi patch version. Kết luận phù hợp: với loader/context hiện tại, điều kiện lớp Jackson không đạt. Chưa có cơ sở kết luận POM thiếu dependency, vì có thể deploy sai artifact, classpath bị cô lập hoặc test dùng `FilteredClassLoader`.

Ngược lại, nếu condition class match nhưng condition property không match thì thêm Jackson không giúp. Nếu bean condition không match vì app đã có encoder, không nên xóa bean của app chỉ để ép thư viện tạo bean mặc định.

## 10. Lỗi thiết kế thường gặp

### 10.1. Đưa optional type vào API bắt buộc

Ví dụ API công khai:

```java
// MINH HỌA THIẾT KẾ KHÓ TÁI SỬ DỤNG:
public interface MessageEncoder {
    com.fasterxml.jackson.databind.ObjectMapper mapper();
}
```

Consumer dùng `MessageEncoder` giờ cũng phải có type của Jackson khi biên dịch phần liên quan. Nếu Jackson là tùy chọn, hãy thiết kế interface core trung tính, giữ type Jackson ở adapter riêng. Đây là lựa chọn thiết kế; trong API chuyên cho Jackson thì phụ thuộc trực tiếp có thể hợp lý, khi đó **đừng mô tả Jackson là optional đối với toàn bộ API**.

### 10.2. Cho class condition nằm quá sâu

Nếu optional class xuất hiện ngay ở return type của `@Bean` trong configuration luôn được xử lý, condition trên chính method có thể đến quá muộn. Dùng class cấu hình lồng được guard là hướng an toàn trong Spring Boot.

### 10.3. Nhầm “optional dependency” với “feature flag”

`optional=true` kiểm soát truyền dependency qua Maven consumer; `demo.json.enabled=false` kiểm soát điều kiện property tại runtime; `@ConditionalOnClass` kiểm soát sự hiện diện type. Ba thứ giải quyết ba vấn đề khác nhau, thường cần phối hợp.

### 10.4. Kiểm tra class hiện diện bằng cách tạo instance

`new OptionalClient()` không phải phép kiểm tra “an toàn nếu không có JAR”; nó buộc runtime tải type và thực thi constructor. Trong Spring Boot, dùng `@ConditionalOnClass` gắn đúng cấp và test bằng `FilteredClassLoader`. Nếu phải kiểm tra thủ công, tránh khởi tạo sớm và xử lý rõ lỗi phân giải.

### 10.5. Nghĩ chạy test thành công đồng nghĩa production đủ JAR

Test thường có dependency riêng và đôi khi phiên bản khác với runtime production. Luôn phân biệt test classpath, classpath của artifact đã đóng gói, classpath của container và môi trường tải class của ứng dụng đang chạy.

### 10.6. “Có class” nghĩa là hoạt động được

Dù condition match, bean vẫn có thể fail do API mismatch, cấu hình thiếu, network, credential hoặc tài nguyên ngoài. Class condition chỉ xác nhận *điều kiện cần về sự hiện diện type*, không bảo đảm tác vụ thực thi thành công.

## 11. Tự kiểm tra hiểu bài

**Câu 1.** Một thư viện Maven khai báo Jackson `optional=true`, chạy unit test của thư viện thành công. Consumer chỉ khai báo thư viện, không khai báo Jackson. Consumer chắc chắn có `ObjectMapper` không?

**Đáp án:** Không. Optional ngăn Jackson tự đi theo cạnh dependency transitively đó; vẫn có thể có Jackson từ một dependency khác. Cần kiểm tra runtime classpath thực tế.

**Câu 2.** Vì sao `@ConditionalOnClass` ở lớp cấu hình bảo vệ an toàn hơn `@ConditionalOnClass` trên `@Bean` method trả về optional type?

**Đáp án:** Khi Spring/JVM phân tích method signature, optional type có thể bị nạp trước khi xét condition trên method. Tách configuration class cho phép loại trừ cả phần chứa method trước khi tham chiếu optional type được xử lý.

**Câu 3.** `@ConditionalOnClass(ObjectMapper.class)` match, nhưng không có `MessageEncoder`. Có chắc là lỗi Spring không?

**Đáp án:** Không. Có thể property disable, class condition của lớp khác không match, bean condition back off, imports chưa công bố đúng hoặc bean initialization fail. Cần condition report và stack trace.

**Câu 4.** Một class cùng tên được hai custom ClassLoader độc lập định nghĩa có phải cùng một JVM type không?

**Đáp án:** Không nhất thiết. Danh tính type gồm cả binary name và defining classloader; có thể gặp `ClassCastException`.

**Câu 5.** Bạn muốn integration Jackson không làm hỏng consumer chỉ dùng phần core. Cần những ranh giới nào?

**Đáp án:** Core/API không ép consumer dùng Jackson; adapter được bảo vệ bằng class-level condition; artifact/metadata phát hành chính xác; consumer quyết định có dependency hay không; test cả missing/present class, property và bean override.

## 12. Ghi nhớ và tài liệu tham khảo

Một dependency tùy chọn chỉ thật sự “tùy chọn” đối với ứng dụng khi **cả dependency graph, API boundary, class loading và cơ chế đăng ký bean** được thiết kế theo hướng cho phép nó vắng mặt.

- **Classpath** trả lời: thư viện/class có khả năng được tìm ở ngữ cảnh nào?
- **ClassLoader** trả lời: loader cụ thể nhìn thấy và nạp class nào?
- **`@ConditionalOnClass`** trả lời: class cần thiết có hiện diện để thử bật auto-configuration không?
- **`@ConditionalOnProperty` và `@ConditionalOnMissingBean`** trả lời: ứng dụng có muốn tính năng này và đã cung cấp bean riêng chưa?
- **Kiểm thử thực tế** trả lời: khi thiếu JAR, feature tắt, hoặc có bean riêng, ứng dụng có hoạt động đúng hợp đồng không?

Đọc thêm từ tài liệu chính thức:
- Spring Boot 3.3 — Creating Your Own Auto-configuration (Class Conditions, Testing): https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Maven — Dependency Mechanism (`optional` và dependency scope): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Dependency Configurations: https://docs.gradle.org/current/userguide/dependency_configurations.html
- Java 17 — `Class.forName` và `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
