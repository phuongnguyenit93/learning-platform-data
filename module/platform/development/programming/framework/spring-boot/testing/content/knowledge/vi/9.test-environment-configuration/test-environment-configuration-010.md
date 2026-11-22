# Điều khiển command-line arguments và thuộc tính khởi động theo phiên bản

## 1. Mục tiêu của bài học

Trong Spring Boot, ứng dụng có thể nhận cấu hình ngay khi khởi động từ **đối số dòng lệnh (command-line arguments)**, **Java system properties**, **biến môi trường**, **file cấu hình**, hoặc từ **thuộc tính được khai báo trực tiếp trên bài test**. Những nguồn này có thể có cùng một tên property nhưng có **thứ tự ưu tiên khác nhau**. Spring TestContext và `@SpringBootTest` bổ sung các cách kiểm soát đầu vào cho một lần khởi tạo `ApplicationContext` trong test.

Bài học tập trung vào hai câu hỏi:

1. Làm thế nào kiểm soát **những đối số gốc mà SpringApplication nhận được**, để kiểm thử code phụ thuộc `ApplicationArguments`, `ApplicationRunner` hoặc `CommandLineRunner`?
2. Làm thế nào kiểm soát **giá trị property hiệu lực trong `Environment`**, để kiểm thử bean khởi tạo bằng `@Value`, `@ConfigurationProperties`, profile và các cấu hình khởi động?

Ngoài cú pháp, bạn cần nhận diện **khác biệt phiên bản Spring Boot**. Đặc biệt, thuộc tính `args` trên `@SpringBootTest` được bổ sung từ **Spring Boot 2.2.0**, còn `useMainMethod` được bổ sung từ **Spring Boot 3.0.0**. Một ví dụ dùng API của Boot 3.x không thể áp nguyên văn vào dự án Boot 2.1.x.

Sau bài học, bạn sẽ:

- Phân biệt đối số `--key=value`, cờ `--flag` và đối số không phải tùy chọn.
- Viết test kiểm tra `ApplicationArguments` và giá trị thực tế trong `Environment`.
- Dùng đúng `@SpringBootTest(args = ...)`, `@SpringBootTest(properties = ...)`, `@TestPropertySource` và `@ActiveProfiles`.
- Giải thích vì sao property test có thể thắng command-line property, còn `ApplicationArguments` vẫn giữ giá trị gốc.
- Nhận biết tác dụng của `useMainMethod` và thiết lập `SpringApplication` tùy phiên bản.
- Chạy kiểm thử tương đương từ IDE/Gradle/Maven/CI và điều tra kết quả lệch do source, timing hoặc context cache.

**Phạm vi:** các dự án Spring Boot Java 17+ hiện đại, nhất là Boot 3.x/4.x. Có ghi chú tương thích cho Boot 1.x/2.x; API và dependency phải đối chiếu với phiên bản mà dự án thực sự đang dùng. Không suy đoán một thuộc tính có ở mọi phiên bản chỉ vì ví dụ trên mạng hiện đại dùng được.

## 2. Ba loại “tham số lúc khởi động” rất dễ bị nhầm

### 2.1. Application arguments — đối số chương trình

Khi chạy ứng dụng đóng gói bằng JAR:

```bash
java -jar app.jar --demo.mode=fast --demo.retries=3 --feature.flag input.csv
```

Phần **sau `app.jar`** là các đối số truyền cho `main(String[] args)` và tiếp theo cho `SpringApplication.run(..., args)` nếu main chuyển tiếp chúng.

- `--demo.mode=fast` và `--demo.retries=3` là **option arguments có giá trị**.
- `--feature.flag` là **option argument có mặt nhưng không có giá trị**.
- `input.csv` là **non-option argument** (positional argument).

Khi ứng dụng được khởi động bởi `SpringApplication` theo cơ chế mặc định, Spring Boot phân tích các đối số thành đối tượng `ApplicationArguments`. Tên option (ví dụ `demo.mode`) **không bao gồm tiền tố `--`** khi gọi `getOptionValues("demo.mode")`.

Theo mặc định, các option dạng `--key=value` còn được Spring Boot thêm vào `Environment` như một nguồn property có ưu tiên cao hơn file cấu hình và Java system properties, nhưng trong test có thể xuất hiện những **test property sources** được ưu tiên cao hơn nữa.

### 2.2. Java system properties — tham số của JVM

So sánh:

```bash
java -Ddemo.mode=from-jvm -jar app.jar --demo.mode=from-cli
```

- `-Ddemo.mode=from-jvm` **đứng trước `-jar`**: đặt Java system property cho JVM.
- `--demo.mode=from-cli` **đứng sau tên JAR**: là application argument được SpringApplication phân tích.
- Khi không có test override, `Environment.getProperty("demo.mode")` thường lấy `from-cli` vì command-line property có mức ưu tiên cao hơn Java system property.
- `System.getProperty("demo.mode")` vẫn trả `from-jvm`: nó đọc nguồn Java system properties trực tiếp, **không thực hiện Spring property-source resolution**.

Đừng viết `java -jar app.jar -Ddemo.mode=from-jvm` rồi tin đó là JVM system property: sau tên JAR, token này được truyền làm **đối số chương trình**, không phải được JVM diễn giải như `-D` trước khi khởi động.

### 2.3. OS environment variables — biến môi trường của tiến trình

Chẳng hạn đặt `DEMO_MODE=from-env` trong môi trường trước khi chạy ứng dụng. Spring Boot hỗ trợ **relaxed binding** cho tên property, nhưng quy tắc chuyển đổi, dấu gạch nối và cách biểu diễn cấu trúc phức tạp tùy loại property source. Đối với khóa thử nghiệm `demo.mode` đơn giản, cách biểu diễn môi trường thường là `DEMO_MODE`.

**Phân biệt:**

- OS environment variable thuộc **môi trường tiến trình**.
- Java system property thuộc **JVM**.
- Application argument thuộc **mảng đối số gốc** của ứng dụng.
- Spring `Environment` là cơ chế **hợp nhất và phân giải property** từ nhiều nguồn theo thứ tự ưu tiên.

Không nên dùng ba khái niệm này thay nhau trong tài liệu, test hoặc CI.

## 3. Hai góc nhìn: `ApplicationArguments` và `Environment`

Một test có thể đọc **cùng một khóa** theo hai cách nhưng nhận giá trị khác nhau, hoàn toàn đúng theo thiết kế.

| API | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| `ApplicationArguments.getSourceArgs()` | Ứng dụng được khởi chạy với chuỗi đối số gốc nào? | Mảng `["--demo.mode=fast", "input.csv"]` |
| `containsOption("demo.mode")` | Option này có xuất hiện trong args không? | `true` hoặc `false` |
| `getOptionValues("demo.mode")` | Option xuất hiện với những giá trị nào? | `List.of("fast")` |
| `getNonOptionArgs()` | Các đối số positional là gì? | `List.of("input.csv")` |
| `Environment.getProperty("demo.mode")` | Giá trị property **hiệu lực** sau resolution là gì? | Có thể là `from-test` dù CLI truyền `fast` |
| `@Value("${demo.mode}")` | Bean nhận property hiệu lực là gì khi inject? | Theo `Environment`/placeholder resolution |
| `@ConfigurationProperties` | Một nhóm property được bind ra object kiểu mạnh ra sao? | Bind `demo.retries` thành số nguyên |

### 3.1. Ý nghĩa chính xác của `getOptionValues`

Theo API `ApplicationArguments`:

- **Option vắng mặt:** `getOptionValues("missing") == null`.
- **Option xuất hiện không có dấu `=value`:** trả về **danh sách rỗng**.
- **Option có một giá trị:** trả về danh sách chứa một phần tử.
- **Option lặp lại nhiều lần:** danh sách có thể chứa nhiều giá trị ứng với các lần xuất hiện.

Ví dụ:

```text
--demo.mode=alpha --demo.mode=beta --feature.flag report.csv
```

Bạn có thể kỳ vọng `getOptionValues("demo.mode")` chứa `["alpha", "beta"]`, `containsOption("feature.flag")` là `true`, giá trị của `feature.flag` là danh sách rỗng, và `getNonOptionArgs()` chứa `"report.csv"`.

**Đừng đánh đồng** option có mặt nhưng không có value với option không tồn tại; hai tình huống này khác nhau. Và khi option có nhiều giá trị, đừng mặc định `Environment.getProperty(...)` sẽ có cùng kiểu `List<String>` với `ApplicationArguments`; hãy chọn cách bind/parse cụ thể cần dùng.

### 3.2. Đối số không phải option không tự trở thành property

`report.csv` có thể xuất hiện trong `getNonOptionArgs()` nhưng nó **không tương đương** `--report.file=report.csv` và không tự tạo property `report.file`. Nếu ứng dụng yêu cầu file qua property, hãy thiết kế giao diện CLI rõ ràng hoặc tự xử lý positional arguments trong `ApplicationRunner`.

### 3.3. Runner nào nhận dạng đối số nào?

Hai interface Spring Boot dùng phổ biến:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

Đây là **chữ ký API minh họa**, không phải hai source file chạy độc lập.

- `ApplicationRunner` nhận đối số đã parse thành `ApplicationArguments`.
- `CommandLineRunner` nhận mảng chuỗi raw arguments.
- Hai loại runner thường được gọi sau khi ứng dụng khởi động thành công. Trong một `@SpringBootTest` thực sự chạy `SpringApplication`, runner có thể được thực thi khi context được dựng; test cần bảo đảm side effect của runner được cô lập.
- Đừng tạo `ApplicationRunner` chỉ để xác nhận `Environment` đã đọc property; có thể inject `Environment` trực tiếp trong test.

## 4. Ma trận khả năng theo Spring Boot version

| Nhánh Spring Boot | Các API/điểm đáng chú ý | Lưu ý tương thích |
|---|---|---|
| **1.4.x–2.1.x** | Có `@SpringBootTest` và khả năng khai báo `properties/value` | **Chưa có `@SpringBootTest(args=...)`**; nếu cần test parsing, dùng `DefaultApplicationArguments` hoặc xây context/run có chủ đích |
| **2.2.x–2.3.x** | `@SpringBootTest(args=...)` có từ **2.2.0** | Kiểm tra dependencies/JUnit engine theo dự án; `useMainMethod` chưa có |
| **2.4.x–2.7.x** | Vẫn có `args`; Spring Boot **Config Data API** thay đổi đáng kể việc load `application.*`, config import/location | Một số ví dụ cấu hình file từ Boot trước 2.4 cần điều chỉnh; `useMainMethod` vẫn chưa có |
| **3.0.x trở lên** | `useMainMethod` được thêm từ **3.0.0**; `args` và `properties` vẫn có | Spring Boot 3 yêu cầu Java 17+; kiểm tra lựa chọn `NEVER/WHEN_AVAILABLE/ALWAYS` |
| **4.x** | Tiếp tục phải kiểm tra API/Javadoc và các starter/module trên nhánh được chọn | Không mặc định dependency/layout test của ứng dụng Boot 2/3 giống hoàn toàn Boot 4 |

**Chỉ dựa vào phiên bản Boot để chọn API chưa đủ.** JUnit Jupiter, Spring Framework, Maven Surefire/Gradle test task và Java toolchain cũng phải tương thích. Khi IDE gợi ý một annotation attribute nhưng Maven/Gradle báo “cannot find symbol”, hãy xác nhận **dependency thực sự được resolve** và build có đang dùng đúng nhánh Spring Boot hay không.

### 4.1. Mốc phiên bản có bằng chứng trực tiếp

Javadoc của `@SpringBootTest` ghi:

- `args(): String[]` — **Since 2.2.0**.
- `useMainMethod(): SpringBootTest.UseMainMethod` — **Since 3.0.0**, giá trị mặc định **`NEVER`**.

Vì vậy trên Boot 2.1, cách viết `@SpringBootTest(args = {"--mode=test"})` không phải “hành vi không đúng” mà đơn giản là **API chưa tồn tại**. Tương tự, `useMainMethod = ...` không thể biên dịch trên Boot 2.x.

## 5. Thứ tự ưu tiên của property: tại sao args có nhưng giá trị bị ghi đè?

Spring Boot tổng hợp các property source vào `Environment`. Theo tài liệu Externalized Configuration của các nhánh Boot hiện đại, khi hai nguồn có cùng khóa thì nguồn ưu tiên cao hơn quyết định giá trị hiệu lực.

**Một trật tự thường gặp từ thấp lên cao đối với khóa cùng tên:**

1. Các default properties (ví dụ `SpringApplication.setDefaultProperties(...)`).
2. Các nguồn cấu hình ứng dụng như `application.properties` hoặc `application.yaml`, bao gồm file theo profile và vị trí/config data phù hợp.
3. OS environment variables.
4. Java system properties.
5. Spring Boot command-line option properties (theo mặc định).
6. Test properties khai báo bằng `@SpringBootTest(properties = ...)`.
7. Những cơ chế override dành riêng cho test như `@TestPropertySource`/`@DynamicPropertySource` theo quy tắc và phiên bản Spring tương ứng.

Danh sách rút gọn này phục vụ **các tình huống thực hành của bài**, không phải bản chép toàn bộ các nguồn JNDI, servlet init params, `SPRING_APPLICATION_JSON` hay devtools. Khi đồng thời dùng nhiều cơ chế override mức cao, hãy xem tài liệu cho đúng nhánh Spring Boot/Spring Framework và tránh phụ thuộc vào một thứ tự bạn chưa kiểm chứng. Bài thực hành chỉ dùng những cặp có quan hệ ưu tiên rõ: `@SpringBootTest(properties)` **thắng** command-line property; `@TestPropertySource(properties)` **thắng** property cùng tên trong `@SpringBootTest`.

### 5.1. Ví dụ xung đột có chủ đích

Giả sử:

- File `application-test.properties`: `demo.mode=from-profile-file`.
- Args: `--demo.mode=from-cli`.
- Annotation: `@SpringBootTest(properties = "demo.mode=from-boot-test")`.

Khi test gọi:

```java
assertEquals("from-boot-test",
        environment.getProperty("demo.mode"));

assertEquals(List.of("from-cli"),
        arguments.getOptionValues("demo.mode"));
```

Cả hai đều **đúng**: `Environment` phản ánh giá trị hiệu lực **sau precedence**, còn `ApplicationArguments` phản ánh nội dung gốc của CLI. Đừng sửa test bằng cách đổi expected của `ApplicationArguments` thành `from-boot-test`.

### 5.2. `@SpringBootTest(properties)` không tạo CLI args

Nếu chỉ khai báo:

```java
@SpringBootTest(properties = "demo.mode=from-test")
class PropertiesOnlyTest {
}
```

thì bạn **không thể kết luận** `ApplicationArguments.containsOption("demo.mode")` sẽ là `true`. Property chỉ được thêm vào Environment cho test; nó không phải một token trong mảng args. Đây là phân biệt rất quan trọng khi service có hai đường đọc cấu hình: một đường thông qua `@Value/Environment`, đường khác qua `ApplicationArguments`.

### 5.3. `@TestPropertySource` và `@DynamicPropertySource`

- `@TestPropertySource(locations = "classpath:/startup-test.properties")` nạp test property từ resource theo cơ chế Spring TestContext.
- `@TestPropertySource(properties = "demo.mode=inline-test")` định nghĩa key/value trực tiếp; inlined entries thường có ưu tiên cao hơn resource locations trong chính annotation.
- `@DynamicPropertySource` thích hợp khi giá trị chỉ biết **sau khi tài nguyên test được tạo**, ví dụ cổng ngẫu nhiên của Testcontainers. Nó có precedence riêng và bị ảnh hưởng bởi version Spring Framework/test bootstrapper.
- `@ActiveProfiles("test")` là cách rõ để chọn cấu hình `application-test.properties` cho Spring integration test, thay vì phụ thuộc profile đang bật trên máy cá nhân.

Khi kiểm thử một giá trị đơn giản, **đừng chồng cả ba annotation** lên cùng key chỉ để “chắc chắn” vì sẽ che ý định test và gây khó chẩn đoán. Chỉ dùng nhiều nguồn cùng khóa khi bài test **cố ý chứng minh precedence** như ví dụ ở phần 7.

## 6. Ví dụ hoàn chỉnh Java 17+: kiểm tra args thật và thuộc tính hiệu lực

Ví dụ sau dùng Spring Boot 3.x, Java 17+, JUnit Jupiter và `spring-boot-starter-test`. Nó **không cần Docker, database, máy chủ HTTP hoặc mock**, đồng thời kiểm tra trực tiếp ranh giới giữa `ApplicationArguments` và `Environment`.

### 6.1. Cấu trúc file

```text
src/
├── main/
│   └── java/com/example/testing/arguments/
│       └── ArgumentsDemoApplication.java
└── test/
    ├── java/com/example/testing/arguments/
    │   └── StartupArgumentsTest.java
    └── resources/
        └── application-test.properties
```

Đặt các file chính xác như sau; package Java tương ứng với đường dẫn thư mục.

### 6.2. Ứng dụng Spring Boot

**File `src/main/java/com/example/testing/arguments/ArgumentsDemoApplication.java`:**

```java
package com.example.testing.arguments;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ArgumentsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ArgumentsDemoApplication.class, args);
    }
}
```

Class này là điểm khởi động tiêu chuẩn. Không có runner với side effect, không có service cần database. Trong test bên dưới, `@SpringBootTest` mặc định **không gọi trực tiếp method `main`** của class này, nhưng vẫn dùng Spring Boot test bootstrap để tạo context với args đã được chỉ định.

### 6.3. File property theo test profile

**File `src/test/resources/application-test.properties`:**

```properties
demo.mode=from-profile-file
demo.count=1
demo.origin=from-profile-file
demo.source=from-profile-file
```

File này là **test resource**; vì thế test runtime có thể nạp nó lên classpath. Không mặc định nó được đóng gói vào production JAR. Annotation `@ActiveProfiles("test")` bên dưới kích hoạt profile test và làm `application-test.properties` được xét theo quy tắc Config Data tương ứng.

### 6.4. Bộ test hoàn chỉnh

**File `src/test/java/com/example/testing/arguments/StartupArgumentsTest.java`:**

```java
package com.example.testing.arguments;

import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ArgumentsDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    args = {
        "--demo.mode=from-cli",
        "--demo.count=7",
        "--feature.flag",
        "report.csv"
    },
    properties = {
        "demo.mode=from-boot-test",
        "demo.origin=from-boot-test"
    }
)
@ActiveProfiles("test")
@TestPropertySource(properties =
        "demo.origin=from-test-property-source")
class StartupArgumentsTest {

    @Autowired
    ApplicationArguments arguments;

    @Autowired
    Environment environment;

    @Value("${demo.mode}")
    String injectedMode;

    @Test
    void exposesOriginalApplicationArguments() {
        assertArrayEquals(new String[] {
            "--demo.mode=from-cli",
            "--demo.count=7",
            "--feature.flag",
            "report.csv"
        }, arguments.getSourceArgs());

        assertTrue(arguments.containsOption("demo.mode"));
        assertTrue(arguments.containsOption("demo.count"));
        assertTrue(arguments.containsOption("feature.flag"));
        assertFalse(arguments.containsOption("not-present"));

        assertEquals(List.of("from-cli"),
                arguments.getOptionValues("demo.mode"));
        assertEquals(List.of("7"),
                arguments.getOptionValues("demo.count"));

        // Option có mặt nhưng không kèm giá trị.
        assertEquals(List.of(),
                arguments.getOptionValues("feature.flag"));

        // Option hoàn toàn vắng mặt.
        assertNull(arguments.getOptionValues("not-present"));

        // Token không bắt đầu bằng "--".
        assertEquals(List.of("report.csv"),
                arguments.getNonOptionArgs());
    }

    @Test
    void testPropertySourcesOverrideCliForEnvironment() {
        // @SpringBootTest(properties) thắng CLI property.
        assertEquals("from-boot-test",
                environment.getProperty("demo.mode"));
        assertEquals("from-boot-test", injectedMode);

        // Không có override từ annotation cho demo.count.
        assertEquals("7",
                environment.getProperty("demo.count"));

        // @TestPropertySource thắng property cùng tên
        // khai báo bởi @SpringBootTest(properties).
        assertEquals("from-test-property-source",
                environment.getProperty("demo.origin"));

        // Khóa chỉ có trong application-test.properties.
        assertEquals("from-profile-file",
                environment.getProperty("demo.source"));
    }

    @Test
    void profileAndArgumentsRemainDistinct() {
        assertTrue(Arrays.asList(
                environment.getActiveProfiles()).contains("test"));

        String originalCliValue =
                arguments.getOptionValues("demo.mode").get(0);
        String effectiveEnvironmentValue =
                environment.getProperty("demo.mode");

        assertEquals("from-cli", originalCliValue);
        assertEquals("from-boot-test",
                effectiveEnvironmentValue);
        assertNotEquals(originalCliValue,
                effectiveEnvironmentValue);
    }
}
```

**Kết quả mong đợi:** lớp có **3 phương thức `@Test`**; cả ba pass trong dự án Spring Boot 3.x được thiết lập như mô tả. Chúng không chủ động in stdout. Format thông báo `BUILD SUCCESSFUL`, Surefire summary hoặc báo cáo IDE có thể khác nhau tùy build tool và version, vì vậy hãy xác nhận test count và trạng thái thay vì dựa vào một chuỗi log cố định.

### 6.5. Dependency test và cách chạy

Ví dụ Gradle Groovy DSL, giả sử dự án đã có Spring Boot plugin, repositories và dependency management phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Ví dụ Maven: dự án đã có Spring Boot parent hoặc BOM cấu hình version thì khai báo các dependency tương ứng:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Các snippet **không phải build file hoàn chỉnh**; không thêm dependency trùng nếu project đã có. Với Spring Boot 4.x, xác minh tên starter và cơ chế module tương ứng trong tài liệu nhánh 4.x trước khi sao chép cấu hình từ Boot 3.

Chạy từ thư mục chứa wrapper của dự án:

```bash
# Gradle:
./gradlew test --tests "com.example.testing.arguments.StartupArgumentsTest"

# Hoặc Maven Surefire:
./mvnw -Dtest=StartupArgumentsTest test
```

Trên Windows PowerShell dùng `.\gradlew.bat test --tests "com.example.testing.arguments.StartupArgumentsTest"` hoặc `.\mvnw.cmd "-Dtest=StartupArgumentsTest" test`.

**Chú ý:** các lệnh trên **chọn test để chạy**. Chúng không truyền `"--demo.mode=from-cli"` từ terminal vào test. Bộ đối số ứng dụng được `@SpringBootTest(args = ...)` chỉ định **ngay trong source test**. Đây là cách để IDE và CI tạo cùng input test, không phụ thuộc câu lệnh người chạy gõ.

### 6.6. Diễn giải luồng thực thi

1. JUnit Platform khám phá `StartupArgumentsTest`.
2. Spring Boot TestContext load application class và cấu hình context với `@ActiveProfiles("test")`.
3. `@SpringBootTest(args=...)` cung cấp bốn token gốc cho quá trình bootstrap `SpringApplication`.
4. Spring Boot tạo `ApplicationArguments` với các option/non-option đã parse; đây là thông tin gốc.
5. Boot bổ sung command-line option properties vào `Environment` theo hành vi mặc định.
6. Test property sources như `@SpringBootTest(properties)` và `@TestPropertySource` tác động vào resolution theo thứ tự ưu tiên riêng; `demo.mode` hiệu lực trở thành `from-boot-test`, không phải `from-cli`.
7. `@Value("${demo.mode}")` được inject từ giá trị hiệu lực, vì vậy nhận `from-boot-test`.
8. Ba test xác nhận riêng **đối số gốc**, **kết quả resolution**, **profile và sự khác nhau giữa hai góc nhìn**.

Không có mâu thuẫn khi `arguments.getOptionValues("demo.mode")` chứa `from-cli` còn `environment.getProperty("demo.mode")` trả `from-boot-test`: đó là mục tiêu cố ý của test.

## 7. Chọn cách truyền đầu vào theo mục tiêu kiểm thử

### 7.1. Kiểm tra parser/runner nhận args nào

Chọn `@SpringBootTest(args = { ... })` khi test thật sự cần biết Spring Boot xử lý các token đầu vào như thế nào, ví dụ:

- App có `ApplicationRunner` sử dụng `getNonOptionArgs()` để chọn file.
- Startup task phân nhánh theo `arguments.containsOption("dry-run")`.
- Command-line option được chuyển thành Environment property.
- Một component phụ thuộc việc có/không có flag, phân biệt flag với giá trị boolean.

Ví dụ minh họa trong một test class có Boot 2.2+:

```java
@SpringBootTest(args = {"--job.name=import", "--dry-run"})
class ImportJobArgumentsTest {
}
```

Đây **không phải ví dụ độc lập**. Nó chỉ chỉ ra cấu hình annotation; để chạy cần application class và các test method phù hợp. `--dry-run` là một flag **không có value**. Nếu business rule cần một property boolean rõ ràng, `--dry-run=true` thường dễ bind qua `@ConfigurationProperties` hơn; đừng mặc định mọi flag rỗng đều đã biến thành boolean `true` theo tất cả cơ chế binding.

### 7.2. Kiểm tra bean đọc một property có giá trị cụ thể

Chọn `@SpringBootTest(properties = "app.retry.max-attempts=2")` khi mục tiêu là cấu hình hiệu lực, không cần mô phỏng nguyên văn token CLI.

```java
@SpringBootTest(properties = {
    "app.retry.max-attempts=2",
    "app.remote.enabled=false"
})
class RetryConfigurationTest {
}
```

Điều này ít phụ thuộc parsing CLI hơn. Test vẫn nên assert kết quả hành vi hoặc giá trị bean được bind, chứ không chỉ nhìn thấy context khởi động thành công.

### 7.3. Chọn profile test thay vì tự gõ nhiều property mỗi lần

Đối với những cấu hình có liên quan như datasource giả lập, logging hay broker, có thể đặt chúng trong `src/test/resources/application-test.properties` hoặc `application-test.yaml` rồi dùng:

```java
@ActiveProfiles("test")
@SpringBootTest
class TestProfileIntegrationTest {
}
```

File `application-test.*` là Config Data theo profile; `@ActiveProfiles` thuộc Spring TestContext. Chúng dễ quản lý khi nhiều test dùng chung bối cảnh, và thường tốt hơn một annotation chứa hàng chục string literal.

### 7.4. Giá trị động từ hạ tầng test

Với Testcontainers, port của database thường chỉ biết sau khi container chạy. Dùng cơ chế động được framework/version hỗ trợ (ví dụ `@DynamicPropertySource` trong Spring TestContext) thay vì viết cố định `jdbc:...:5432` vào args. Điều này giảm xung đột cổng trên CI. Nếu cần kiểm chứng **CLI override**, hãy tách thành test riêng và không vô tình áp một dynamic property cùng tên vì nó sẽ gây khó nhận biết nguồn hiệu lực.

## 8. `useMainMethod`: khác biệt quan trọng từ Spring Boot 3.0

### 8.1. `@SpringBootTest` có luôn gọi main không?

**Không.** Theo mặc định, `@SpringBootTest` không gọi trực tiếp `main(String[] args)` trong application class; framework khởi tạo context bằng cơ chế test bootstrap. Điều này giúp test tránh những side effect hoặc tùy biến mà `main` thực hiện, nhưng cũng khiến **những cấu hình chỉ nằm trong main không được áp dụng**.

Ví dụ production `main` có:

```java
public static void main(String[] args) {
    SpringApplication app =
            new SpringApplication(ArgumentsDemoApplication.class);
    app.setAdditionalProfiles("batch");
    app.setDefaultProperties(
            java.util.Map.of("demo.mode", "from-main-default"));
    app.run(args);
}
```

Đây là **đoạn minh họa để thay phần body của main trong ứng dụng hiện có**, không phải source file độc lập. Nó cho thấy những tùy chỉnh programmatic có thể không xuất hiện khi test bypass `main`. Đừng dùng profile `batch` để thay thế `@ActiveProfiles("test")` trong mọi test; đó chỉ là ví dụ customization.

### 8.2. Ba chế độ `SpringBootTest.UseMainMethod`

Từ **Spring Boot 3.0.0**, có thể chỉ định:

| Giá trị | Ý nghĩa |
|---|---|
| `NEVER` | **Mặc định:** không dùng main method để tạo test application |
| `WHEN_AVAILABLE` | Dùng main khi tìm thấy main method phù hợp; nếu không có thì dùng cơ chế thông thường |
| `ALWAYS` | Yêu cầu phải dùng main; khi không có main phù hợp thì việc bootstrap không thể đáp ứng yêu cầu |

Ví dụ dùng khi muốn test **đúng customization trong main**:

```java
@SpringBootTest(
    classes = ArgumentsDemoApplication.class,
    args = "--demo.mode=from-cli",
    useMainMethod = SpringBootTest.UseMainMethod.WHEN_AVAILABLE
)
class MainMethodCustomizationTest {
}
```

Đây là **snippet cấu hình**, không phải bài test tự chạy. Nếu `main` cấu hình `SpringApplication` theo cách đặc biệt, `WHEN_AVAILABLE` có thể giúp tái hiện hành vi ấy. Tuy nhiên cần kiểm tra các side effect: startup listener, runner, application event, banner, proxy và profile bổ sung. Không bật `ALWAYS` trên mọi test chỉ vì “nó giống production hơn”; test dùng một tập cấu hình tối giản đôi khi đúng và nhanh hơn.

**Với Boot 2.x:** `useMainMethod` không tồn tại. Nếu cần xác minh logic mà chỉ được thiết lập trong main, nên tách phần cấu hình thành một bean/utility kiểm thử được, hoặc tạo bài test khởi động toàn ứng dụng theo API phù hợp của nhánh Boot đang dùng. Không copy annotation Boot 3 rồi sửa import ngẫu nhiên.

## 9. Bật/tắt việc biến command-line args thành Environment properties

Mặc định, `SpringApplication` thêm các option kiểu `--key=value` vào `Environment`. Đôi khi ứng dụng muốn **giữ args cho `ApplicationRunner` nhưng không cho CLI ghi đè cấu hình**. Spring Boot cung cấp:

```java
SpringApplication app =
        new SpringApplication(ArgumentsDemoApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
```

**Đây là đoạn code đặt trong main hoặc nơi bạn kiểm soát SpringApplication**, không phải đoạn Java độc lập. Khi dùng cấu hình này:

- Đối số vẫn được truyền vào application và có thể được nhìn thấy qua `ApplicationArguments` theo cơ chế bootstrap tương ứng.
- Nhưng các option `--demo.mode=...` không tự thêm thành property source cho `Environment`.
- `Environment.getProperty("demo.mode")` có thể lấy từ Java system property, OS env, file cấu hình hoặc test override khác.
- Nếu `@SpringBootTest` đang dùng `useMainMethod = NEVER` mặc định, tùy chỉnh chỉ được thực hiện trong main **không tự động áp dụng** cho test. Cần kiểm tra bootstrapper hoặc dùng `useMainMethod` từ Boot 3.0+ khi mục tiêu là kiểm thử main customization.

Đừng đánh đồng việc **tắt command-line properties** với việc **xóa mảng args**. Đây là hai hành vi độc lập.

## 10. Thuộc tính khởi động “rất sớm”: không phải nguồn property nào cũng đúng thời điểm

Một số khóa ảnh hưởng **quá trình chọn và load cấu hình**, nên chúng phải có sẵn từ đầu; điển hình là:

- `spring.config.name` — thay tên base của config file.
- `spring.config.location` — thay các vị trí mặc định mà Boot tìm config data.
- `spring.config.additional-location` — bổ sung vị trí ngoài mặc định.

Theo tài liệu Spring Boot, các khóa đó cần được đặt **rất sớm** trong Environment, thường qua CLI args, JVM system properties hoặc OS environment variables. `@PropertySource` trên một `@Configuration` class có thể được xử lý **quá muộn** để ảnh hưởng việc xác định file cấu hình và một số tùy chọn `logging.*`/`spring.main.*`.

Ví dụ chạy một app sau khi đóng gói:

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./test-config/ \
  --demo.mode=from-cli
```

Lệnh kiểu Linux/macOS; nếu trên Windows, dùng một dòng hoặc syntax continuation của PowerShell. Ví dụ giả định thư mục `./test-config/` tồn tại hoặc được cho phép vắng nhờ `optional:`.

**Cẩn thận trong test:** đừng mặc định đặt bất kỳ startup-critical key nào qua annotation test cũng tương đương với truyền nó từ **đầu tiến trình**. Cơ chế bootstrap/test property setup có thời điểm khác nhau theo phiên bản. Khi cần xác minh việc định vị và nạp Config Data, hãy xây một bài integration test thật sự bootstrap ứng dụng với nguồn cấu hình đã chọn, dùng API đúng version, và quan sát property source đã load.

### 10.1. Khác biệt Spring Boot trước và sau 2.4

Spring Boot **2.4** đưa ra cơ chế Config Data mới. Tài liệu cũ dùng xử lý profile/config locations ở Boot 2.3 trở xuống có thể không khớp logic `spring.config.import`, profile activation và location groups ở Boot mới. Do đó khi test thuộc tính khởi động rất sớm, hãy dùng tài liệu đúng nhánh Boot và thiết lập rõ file/nguồn thay vì kết luận từ một ví dụ của phiên bản khác.

### 10.2. `@TestPropertySource` không mặc định là YAML loader

`@TestPropertySource(locations = "...")` truyền thống đọc resource theo định dạng `.properties`. Với các phiên bản Spring Framework mới, có thể cung cấp `PropertySourceFactory` phù hợp cho định dạng khác, nhưng **đừng mặc định một file `.yaml` sẽ được đọc như Spring Boot Config Data** chỉ bằng cách viết `@TestPropertySource("classpath:/app-test.yaml")`.

Muốn dùng cấu hình profile `application-test.yaml`, ưu tiên cơ chế **Spring Boot Config Data + `@ActiveProfiles("test")`**. Khi mục tiêu là một test property resource đơn giản, `.properties` là lựa chọn dễ dự đoán.

## 11. Đối chiếu cách chạy từ IDE, Gradle, Maven và CI

Điều khiển CLI args của **ứng dụng** khác với đối số bạn truyền cho **build tool**.

### 11.1. Bốn đường chạy khác nhau

| Cách chạy | Đối số đi vào đâu? | Ý nghĩa |
|---|---|---|
| `java -jar app.jar --demo.mode=cli` | SpringApplication args của **ứng dụng thật**, nếu main chuyển tiếp | Kiểm tra bootstrap runtime |
| IDE → Run application, **Program arguments** | Mảng `main(String[] args)` của ứng dụng | Đối chiếu với `java -jar` |
| IDE → Run JUnit test | JUnit runner khởi chạy test; `@SpringBootTest(args=...)` cung cấp app args trong test | Không đồng nghĩa nhập args cho app main |
| `./gradlew test ...` hoặc `./mvnw test` | Tham số cấu hình **task/goal test** | Không tự động là SpringApplication args |

Ví dụ:

```bash
./gradlew test --tests "com.example.testing.arguments.StartupArgumentsTest"
```

Tùy chọn `--tests` chọn test class/method của Gradle; **nó không phải** `--demo.mode=...` gửi cho Spring Boot ApplicationArguments.

Tương tự, `-Dtest=StartupArgumentsTest` của Maven Surefire chọn lớp test, không phải `ApplicationArguments` của ứng dụng.

### 11.2. JVM arguments trong test task/fork riêng

Gradle và Maven có thể chạy test ở **JVM fork** khác với tiến trình build tool:

- `./gradlew -Ddemo.mode=from-gradle test` đặt property cho Gradle JVM; **đừng mặc định** nó đã được truyền y nguyên vào JVM thực thi test.
- Gradle `Test` task có cấu hình `systemProperty(...)`, `jvmArgs(...)` và các cơ chế truyền môi trường riêng.
- Maven Surefire có cấu hình `systemPropertyVariables`, `argLine` và lựa chọn fork. Maven user properties có thể tương tác với plugin, nhưng phải xác minh plugin/version thay vì mặc định coi `-D...` là app CLI args.
- IDE JUnit runner có **VM options** và **environment variables** riêng. Khi IDE ủy quyền cho Gradle chạy test, cấu hình trên Gradle task có thể là nguồn quyết định.

Ví dụ Gradle (trong `build.gradle`):

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'demo.mode', 'from-test-jvm'
}
```

Đây là **cấu hình bổ sung trong build file hợp lệ**, không phải project độc lập. Với bài test phần 6, `demo.mode` vẫn được `@SpringBootTest(properties = "demo.mode=from-boot-test")` ghi đè trong `Environment`. Vì vậy đừng đổi expected của test từ `from-boot-test` sang `from-test-jvm` chỉ vì task đã có system property.

### 11.3. Khi chạy chính ứng dụng bằng build tool

Trong Gradle Spring Boot plugin, `bootRun` khởi chạy app thực, khác hoàn toàn `test`:

```bash
./gradlew bootRun --args="--demo.mode=from-cli"
```

Đoạn này giả định project sử dụng plugin Spring Boot/Gradle và `bootRun` có hỗ trợ truyền `--args`. Nó cho ứng dụng nhận argument khi chạy qua task `bootRun`, **không giúp `@SpringBootTest` của một lớp test tự đọc cùng giá trị**.

Với Maven, plugin Spring Boot cũng có khả năng cấu hình arguments cho goal `spring-boot:run`, nhưng cú pháp/khả năng cần kiểm tra theo version plugin. Đừng hoán đổi cờ `--args` của Gradle sang Maven hoặc ngược lại.

### 11.4. Nên lưu gì vào CI?

Trong CI, hãy lưu:

- Version Java, Spring Boot, Gradle/Maven Wrapper và resolved test dependencies.
- Task/goal/module/test filters thực sự được gọi.
- Active profiles và **tên** các config sources, không in bí mật.
- Số test chạy, skipped/failed, report và stacktrace khi context startup lỗi.
- Các environment variables cần thiết, tốt hơn bằng tên/nguồn hoặc giá trị không nhạy cảm.

Nếu CI đỏ nhưng IDE xanh, ưu tiên tái hiện bằng wrapper và kiểm tra **JVM của test**, **source priority** và **test context cache**, không chỉnh assertion cho hợp một môi trường trước khi tìm nguyên nhân.

## 12. Cấu hình profile và ranh giới giữa test context với app runtime

### 12.1. `@ActiveProfiles` giúp test tách biệt môi trường

Nếu mục tiêu là load `application-test.properties`, dùng `@ActiveProfiles("test")` trong test integration. Điều này thể hiện rõ ý định và ổn định hơn phụ thuộc profile mặc định mà máy phát triển vô tình bật.

**Không tự coi**:

```text
@ActiveProfiles("test")
```

là phiên bản viết ngắn của:

```text
--spring.profiles.active=test
```

Hai cách có thể đưa đến những active profiles tương tự trong một số trường hợp, nhưng **đường đi bootstrap, nguồn thiết lập và khả năng tương tác với test context** là khác nhau. Khi test cần chứng minh startup CLI profile activation, hãy viết test riêng cho CLI và kiểm tra context thực tế.

### 12.2. Cẩn trọng với profile từ main method

Nếu production `main` gọi `setAdditionalProfiles("staging")` nhưng test dùng `@SpringBootTest` mặc định không gọi main, staging có thể không xuất hiện trong test. Boot 3.0+ có `useMainMethod = WHEN_AVAILABLE/ALWAYS` để thay đổi điều đó. Tuy nhiên việc bật main có thể kích hoạt các startup customizations không mong muốn trong unit/integration test, nên chỉ dùng khi thật sự cần.

### 12.3. Các tên khóa nên mang ý nghĩa rõ ràng

Ưu tiên cấu trúc như:

```properties
app.import.enabled=false
app.import.batch-size=100
app.remote.timeout=5s
```

Spring Boot Binder có thể bind về `@ConfigurationProperties(prefix = "app.import")`, chuyển kiểu dữ liệu (boolean/int/duration) theo cơ chế hỗ trợ. Tránh dùng khóa chung kiểu `mode` hoặc `timeout` khi nhiều subsystem cùng đọc, vì xung đột giữa args, env vars và default config sẽ khó truy nguyên.

Đối với các setting cấu trúc phức tạp, `@ConfigurationProperties` thường rõ và dễ xác minh hơn một chuỗi `@Value` riêng lẻ; tuy nhiên bài học này vẫn tập trung vào **nguồn và thứ tự ưu tiên tại startup**.

## 13. Context cache và sự độc lập của test

Spring TestContext Framework cache `ApplicationContext` để giảm chi phí khởi động. Cấu hình test như các property override, profile và các tùy biến context góp phần vào **cache key**; do đó hai lớp test có cấu hình startup khác nhau thường không dùng chung một context y hệt.

### 13.1. Không thay `@SpringBootTest(args)` giữa các test method

`@SpringBootTest(args=...)` khai báo tại **class level**; trong một lớp, các test method thông thường cùng sử dụng context đã dựng. Nếu mỗi method cần một tập args khác nhau, hãy tách thành các lớp test hoặc áp dụng cơ chế bootstrap tường minh phù hợp, thay vì cố thay `ApplicationArguments` trên context đã tạo.

Cũng đừng đặt giả định “chạy test method A trước rồi sửa system property để method B nhận giá trị khởi động mới”; bean đã được khởi tạo và binding có thể đã diễn ra. Việc đổi một nguồn property sau bootstrap **không tự tái tạo mọi bean**.

### 13.2. Không dùng `System.setProperty` bừa bãi

Mẫu nguy hiểm:

```java
@Test
void changesGlobalProperty() {
    System.setProperty("demo.mode", "temporary");
    // Test này không khôi phục state ...
}
```

**Đoạn phản mẫu**, không phải lời khuyên thực thi. Java system properties là trạng thái toàn JVM, có thể rò sang test khác hoặc gây race khi chạy song song. Ưu tiên annotation test, cấu hình source rõ ràng, hoặc extension/resource quản lý giá trị rồi khôi phục trong `finally` nếu thật sự buộc thay đổi global state.

Tương tự, tránh sửa OS environment variables trong lúc test và coi đó là phương án chung: JVM không có API chuẩn an toàn để thay đổi environment process cho các test một cách độc lập.

### 13.3. Khi nào dùng `@DirtiesContext`?

`@DirtiesContext` có thể buộc Spring loại context khỏi cache khi test đã làm context không còn tái sử dụng an toàn. Đây **không phải** cách mặc định để nạp lại args/property cho mỗi method. Nếu input test thực sự cần khác nhau, thiết kế test classes/cấu hình độc lập là lựa chọn rõ hơn; không dùng `@DirtiesContext` để che state leakage.

### 13.4. Startup side effects là chuyện có thật

Nếu ứng dụng có `ApplicationRunner` gọi service bên ngoài, việc chạy `@SpringBootTest` có thể kích hoạt code đó khi context khởi động. Để test tái lập:

- Tách logic runner thành service có thể kiểm tra riêng, mock cổng I/O ở test phù hợp.
- Dùng property `app.startup-job.enabled=false` để vô hiệu hóa công việc không liên quan trong test, và kiểm tra nhánh job bật bằng test có fixture riêng.
- Đừng dùng cùng database production hoặc gửi HTTP thật chỉ để kiểm chứng cách parse một flag.
- Với code thuần xử lý chuỗi args, cân nhắc unit test `DefaultApplicationArguments` thay vì load cả Spring context.

## 14. Test parser nhẹ mà không cần cả Spring context

Nếu bạn chỉ cần xác minh cách parse token, có thể dùng `DefaultApplicationArguments` của Spring Boot với JUnit mà **không khởi động context**.

Ví dụ **phương thức test** trong một lớp JUnit Jupiter có dependency Spring Boot:

```java
@Test
void parsesOptionsWithoutStartingSpring() {
    ApplicationArguments args = new DefaultApplicationArguments(
            "--job.name=import",
            "--dry-run",
            "orders.csv");

    assertTrue(args.containsOption("dry-run"));
    assertEquals(List.of(), args.getOptionValues("dry-run"));
    assertEquals(List.of("import"),
            args.getOptionValues("job.name"));
    assertEquals(List.of("orders.csv"),
            args.getNonOptionArgs());
}
```

Cần import `org.springframework.boot.ApplicationArguments`, `org.springframework.boot.DefaultApplicationArguments`, `org.junit.jupiter.api.Test` và các assertion JUnit; đây là **snippet nằm trong test class**, không phải file độc lập.

**Giới hạn:** test trên chỉ xác minh parser `ApplicationArguments`. Nó **không** kiểm tra rằng SpringApplication đã thêm command-line properties vào Environment, không khởi tạo `@ConfigurationProperties` bean, và không chứng minh main customization hoạt động. Với những mục tiêu đó, dùng Spring Boot integration test đúng phạm vi.

## 15. Xử lý lỗi phổ biến theo triệu chứng

| Triệu chứng | Nguyên nhân có khả năng | Hướng điều tra/sửa |
|---|---|---|
| Annotation không có thuộc tính `args` | Spring Boot **trước 2.2** hoặc dependency test bị resolve sai | Xem version; nâng cấp phù hợp hoặc dùng parser test/explicit bootstrap |
| Annotation không có `useMainMethod` | Spring Boot **trước 3.0** | Không dùng attribute này; tách main customization hoặc nâng cấp có kiểm soát |
| `ApplicationArguments.getOptionValues(...)` trả `null` | Option chưa xuất hiện trong args, hoặc tên tra cứu sai | Kiểm tra `getSourceArgs()` và tên option không có `--` |
| `getOptionValues("flag")` trả list rỗng | Flag có mặt nhưng không có `=value` | Đây thường là hành vi đúng; dùng `containsOption` để xét presence |
| `Environment` khác giá trị trong `ApplicationArguments` | Cùng key bị ghi đè bởi test property source hoặc nguồn có ưu tiên cao hơn | Kiểm tra `@SpringBootTest(properties)`, `@TestPropertySource` và resolved property |
| Test không thấy `application-test.properties` | Chưa bật profile test hoặc đặt resource sai đường dẫn | Dùng `@ActiveProfiles("test")`, đặt file ở `src/test/resources` |
| JVM `-Dfoo=bar` không thay đổi bean trong test | `@SpringBootTest(properties)` đang override; hoặc `-D` chỉ vào Gradle/Maven JVM | Kiểm tra effective Environment và test fork JVM |
| `@SpringBootTest(args)` không làm main customization có tác dụng | Default `useMainMethod=NEVER` | Với Boot 3+, cân nhắc `WHEN_AVAILABLE` nếu test cần đi qua main |
| Command-line option không xuất hiện trong Environment | `setAddCommandLineProperties(false)` hoặc bootstrap khác; token không đúng dạng | Xem cấu hình SpringApplication và source args |
| Spring Boot 2.3 vs 2.4 load config khác | Config Data API thay đổi logic config data/profile/location | Dùng tài liệu của đúng version, xác nhận property source |
| Một test pass riêng, fail trong suite | Global system property, static state, context cache hoặc runner side effect rò rỉ | Cô lập fixtures, bỏ mutation global, kiểm tra cache |
| IDE xanh, CI đỏ | JDK/dependencies/profile/OS env/test runner khác | Chạy wrapper, so task/goal và effective properties |
| Lỗi `Could not resolve placeholder` | Property không có, profile sai, đặt nguồn quá muộn hoặc typo | Tra nguồn thật, tên khóa, thời điểm load |
| Khóa `spring.config.location` không có hiệu lực | Set quá muộn qua `@PropertySource` hoặc sai path | Truyền sớm qua nguồn phù hợp, kiểm tra Config Data version |
| Chỉ kiểm tra context loads, không kiểm tra args | Assertion không đo lường input/behavior | Assert `ApplicationArguments` và kết quả bean/Environment cụ thể |

### 15.1. Quy trình truy nguyên từng bước

1. **Xác nhận phiên bản** bằng dependency resolution/bản Spring Boot thực tế; kiểm tra API `args`/`useMainMethod` trước.
2. **Xác nhận cách chạy:** application thật, IDE JUnit runner, Gradle test task, Maven Surefire hay SpringBootTest bootstrap.
3. **In/so sánh args gốc** ở môi trường test an toàn: `ApplicationArguments.getSourceArgs()`, option names/non-option args.
4. **Kiểm tra giá trị hiệu lực:** `Environment.getProperty("...")` và giá trị thực được inject/bind vào bean.
5. **Tìm nguồn ghi đè:** file profile, OS env, Java system props, CLI, `@SpringBootTest.properties`, `@TestPropertySource`, dynamic overrides.
6. **Kiểm tra early properties và main customization:** một số cấu hình phải có sớm; default test không gọi main.
7. **Kiểm tra cache/side effect:** global state có bị sửa, runner có làm I/O thật, test có chạy song song hay dùng context đã cache?
8. **Chạy lại qua wrapper** với đúng module và test scope; đọc test report chứ không chỉ thấy build command exit 0.

**Mẹo:** Spring Boot Actuator có endpoint `env` và `configprops` (khi được bật, bảo mật đúng và có quyền) hỗ trợ truy nguyên nguồn property/binding. Trong test, bạn có thể lấy `ConfigurableEnvironment.getPropertySources()` để xem các nguồn đang được xét, nhưng chỉ làm với khóa test an toàn, không in secrets hoặc toàn bộ môi trường vào log CI.

## 16. Bảo mật khi điều khiển command-line arguments

Command-line args thường xuất hiện trong process listing, log khởi động, lịch sử shell hoặc cấu hình CI. Do đó:

- Không truyền access token, password, private key hoặc secrets thật qua `--secret=...` chỉ vì test dễ setup.
- Ưu tiên secret manager, environment/protected variables của CI hoặc cơ chế cấu hình an toàn do tổ chức quy định.
- Chỉ log **tên** của biến nhạy cảm hoặc giá trị đã được mask; bài test không nên chụp toàn bộ `ApplicationArguments.getSourceArgs()` rồi lưu như artifact không hạn chế.
- Các ví dụ `demo.mode`, `demo.count`, `feature.flag` trong bài dùng giá trị giả, không có thông tin nhạy cảm.

Một test fail vì thiếu secret không nên được “sửa” bằng cách commit secret vào `application-test.properties`. Hãy thiết kế fixture giả hoặc dùng secret của môi trường test được quản lý.

## 17. Bài tập thực hành và đáp án

### Bài tập A — Chọn đúng cơ chế

Bạn muốn test service đọc `app.retry.max-attempts` bằng `@ConfigurationProperties`, không quan tâm user gõ token CLI nào. Nên dùng `@SpringBootTest(properties="app.retry.max-attempts=2")` hay `args="--app.retry.max-attempts=2"`?

**Gợi ý:** ưu tiên `properties` vì mục tiêu là giá trị hiệu lực, ít phụ thuộc parsing CLI. Nhưng nếu yêu cầu nghiệp vụ là “người dùng nhập CLI có thể override config file”, cần test riêng với `args` và **không khai báo property test cùng tên có ưu tiên cao hơn**.

### Bài tập B — Dự đoán đối số và Environment

Cho:

```java
@SpringBootTest(
    args = {"--demo.mode=cli", "report.csv"},
    properties = "demo.mode=inline-test")
class StartupTest {
}
```

Giả sử không có nguồn test khác ghi đè `demo.mode`. Giá trị nào đúng?

1. `arguments.getOptionValues("demo.mode")`
2. `arguments.getNonOptionArgs()`
3. `environment.getProperty("demo.mode")`

**Đáp án:** lần lượt là danh sách `["cli"]`, danh sách `["report.csv"]` và chuỗi `"inline-test"`. Vì `@SpringBootTest(properties)` có ưu tiên cao hơn command-line property; args gốc vẫn giữ nguyên.

### Bài tập C — Nhận biết cờ không có value

Bạn nhận `args = {"--dry-run"}`. So sánh:

```java
assertTrue(arguments.containsOption("dry-run"));
assertEquals(List.of(),
        arguments.getOptionValues("dry-run"));
assertNull(arguments.getOptionValues("missing"));
```

Các assertion này phản ánh ba trạng thái riêng: có flag, flag không có value, và một option vắng mặt.

### Bài tập D — Khả năng theo version

Dự án dùng Spring Boot **2.1.x** và Java 8; tài liệu mẫu viết `@SpringBootTest(args = "--job=sync", useMainMethod = ALWAYS)`. Vì sao không biên dịch?

**Đáp án:** `args` cần Boot **2.2+**; `useMainMethod` cần Boot **3.0+**, và Boot 3 yêu cầu Java 17+. Không thể làm API xuất hiện chỉ bằng cách thêm JUnit 5 hay import một enum. Có thể test `DefaultApplicationArguments` không khởi tạo context, hoặc lên kế hoạch nâng cấp phù hợp rồi mới sử dụng annotation mới.

### Bài tập E — Main configuration bị bỏ qua

Main của application gọi `setAddCommandLineProperties(false)`, nhưng test dùng `@SpringBootTest(args = "--demo.mode=cli")` mặc định. Có chắc Environment của test sẽ bỏ qua CLI không?

**Đáp án:** **không chắc/không được mặc định.** Test mặc định có `useMainMethod=NEVER` trên Boot 3+, nên nếu duy nhất main thực hiện việc tắt CLI properties, tùy chỉnh đó có thể không chạy. Test phải cấu hình bootstrap đúng phạm vi, ví dụ `useMainMethod=WHEN_AVAILABLE` từ Boot 3+, rồi kiểm chứng cả `ApplicationArguments` và `Environment`.

## 18. Checklist chốt bài kiểm thử

- [ ] Đã xác định chính xác **Spring Boot version**, Java toolchain và dependency test.
- [ ] Biết `@SpringBootTest(args)` có từ **2.2.0** và `useMainMethod` từ **3.0.0**.
- [ ] Phân biệt JVM `-D`, OS env vars, Java application args và Spring Environment.
- [ ] Biết `--key=value`, `--flag`, positional argument có semantics khác nhau.
- [ ] Kiểm tra `getOptionValues` trả `null` khi option vắng mặt, empty list khi flag không có value.
- [ ] Không dùng `@SpringBootTest(properties)` để giả làm raw `ApplicationArguments`.
- [ ] Không kỳ vọng `ApplicationArguments` đổi theo giá trị bị test property source ghi đè.
- [ ] Biết property resolution ưu tiên test overrides hơn CLI và file config khi cùng key.
- [ ] Dùng `@ActiveProfiles`/test resources thay vì phụ thuộc profile cục bộ không kiểm soát.
- [ ] Hiểu test mặc định không gọi main; chỉ bật `useMainMethod` khi cần kiểm thử customization trong main.
- [ ] Đặt những config-location/early properties ở nguồn phù hợp để có tác dụng đúng thời điểm.
- [ ] Không truyền flags của Gradle/Maven test runner như thể đó là application CLI args.
- [ ] Không vô tình sửa system properties/global state làm test phụ thuộc thứ tự.
- [ ] Nếu dùng context cache, thiết kế các tập args/config ở cấp test class rõ ràng.
- [ ] Không ghi secrets thật vào đối số, file test, log hay CI artifact.
- [ ] Test khẳng định được input và hành vi; không chỉ `assertNotNull(context)`.
- [ ] Có báo cáo test count, lỗi chi tiết và kết quả đồng nhất giữa IDE/CLI/CI.

## 19. Kết luận

**Command-line arguments** là các token nguyên gốc của ứng dụng; **startup properties** là giá trị hiệu lực sau khi nhiều `PropertySource` được kết hợp. Spring Boot Test cho phép điều khiển riêng hai điều này bằng `@SpringBootTest(args)` và `@SpringBootTest(properties)`; `@TestPropertySource`/`@ActiveProfiles` quản lý cấu hình test theo mục tiêu rõ hơn. Vì vậy, một app có thể nhận `--demo.mode=cli` nhưng bean vẫn thấy `demo.mode=from-boot-test` — đó là kết quả đúng khi test override được ưu tiên.

Để test đáng tin, hãy **chọn API tồn tại trong phiên bản thực**, hiểu test bootstrap có đi qua `main` hay không, phân biệt thời điểm tải cấu hình rất sớm và kiểm tra bằng assertion **cả đối số gốc lẫn cấu hình hiệu lực** khi chúng là điều kiện của hợp đồng.

## Tài liệu tham khảo chính thức

- [Spring Boot Javadoc — SpringBootTest (nhánh 3.4)](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/context/SpringBootTest.html): `args` từ Boot 2.2.0, `useMainMethod` từ Boot 3.0.0, `properties` và `webEnvironment`.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): Using Application Arguments, Testing With a Mock Environment, Using the Main Method.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property-source order, command-line properties, config files, early bootstrap keys và relaxed binding.
- [Spring Boot Javadoc — ApplicationArguments](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationArguments.html): option names/values, non-option args và source args.
- [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): `@TestPropertySource`, resource locations, precedence và inheritance.
- [Spring Boot — Spring Boot 2.2 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.2-Release-Notes): bối cảnh thay đổi giữa Boot 2.1 và Boot 2.2.
