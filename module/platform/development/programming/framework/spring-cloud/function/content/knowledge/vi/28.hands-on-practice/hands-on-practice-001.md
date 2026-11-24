# Xây dựng bộ Supplier, Function và Consumer xử lý văn bản

## 1. Bài toán thực hành và kết quả cần đạt

Trong module **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), mục tiêu không chỉ là viết vài lambda Java, mà còn là đóng gói logic nghiệp vụ thành các hàm có thể **tái sử dụng độc lập với giao thức gọi**. `FunctionCatalog` giúp đăng ký/tra cứu các hàm, hỗ trợ composition và chuyển đổi thông điệp; adapter có thể mang cùng logic sang HTTP, hệ thống sự kiện hoặc môi trường serverless.

Trong bài thực hành này, ta xây dựng **Text Function Lab**: một ứng dụng nhận văn bản đầu vào, chuẩn hóa khoảng trắng/chữ hoa, gắn nhãn, đếm từ và ghi nhận nội dung đã xử lý.

Thay vì tạo controller cho từng nghiệp vụ, ta đăng ký các functional bean:

| Bean | Giao diện Java | Vai trò | Ví dụ |
| --- | --- | --- | --- |
| `sampleText` | `Supplier<String>` | Cung cấp văn bản mẫu | `"  Spring   Cloud  Function  "` |
| `normalizeText` | `Function<String, String>` | Chuẩn hóa khoảng trắng và chữ hoa | `"SPRING CLOUD FUNCTION"` |
| `tagText` | `Function<String, String>` | Gắn tiền tố vào kết quả | `"[TEXT] SPRING CLOUD FUNCTION"` |
| `countWords` | `Function<String, Integer>` | Đếm các từ phân tách bằng khoảng trắng | `3` |
| `auditText` | `Consumer<String>` | Ghi nhận văn bản sau khi xử lý | Thêm vào kho audit trong bộ nhớ |

Luồng sử dụng các bean:

~~~text
                  +----------------+
                  | sampleText     |  Supplier<String>
                  +--------+-------+
                           |
                           v
                  "  Spring   Cloud  Function  "
                           |
                           v
                  +----------------+
                  | normalizeText  |  Function<String,String>
                  +--------+-------+
                           |
                "SPRING CLOUD FUNCTION"
                      /         \
                     v           v
             +-----------+   +-----------+
             | tagText   |   | countWords|
             +-----------+   +-----------+
                     |
                     v
                +-----------+
                | auditText |  Consumer<String>
                +-----------+
~~~

**Đầu ra mong muốn sau khi hoàn thành:**

1. Tạo được ứng dụng Spring Boot chứa các bean `Supplier`, `Function`, `Consumer`.
2. Tra cứu và gọi từng bean qua `FunctionCatalog` thay vì phụ thuộc lớp triển khai.
3. Nối `normalizeText|tagText` bằng composition và quan sát kết quả.
4. Test logic thuần và test Spring context bằng JUnit 5.
5. Chạy web adapter và thử `GET`/`POST` bằng `curl`.
6. Nhận biết rõ giới hạn: audit trong bộ nhớ không bền vững, input HTTP cần kiểm soát, và web adapter không đồng nghĩa đã có message broker.

> **Phạm vi:** Chỉ viết **một ứng dụng thực hành** và các kiểm thử liên quan. Chưa thêm Kafka/RabbitMQ, database hay triển khai serverless thật; bài học sẽ chỉ ra cách mở rộng mà không làm biến dạng logic cốt lõi.

## 2. Điều kiện tiên quyết và lựa chọn phiên bản

Để làm theo ví dụ, cần:

- JDK **17 trở lên** và Maven 3.9+.
- IDE hỗ trợ Java/Spring hoặc một terminal.
- Cổng localhost `8080` còn trống (hoặc đổi trong cấu hình).
- Công cụ `curl` để gọi HTTP, và JUnit chạy thông qua Maven.

**Cặp phiên bản minh họa đã được công bố tương thích:** Spring Boot **3.5.0** và Spring Cloud release train **2025.0.0**. Spring Cloud Function thuộc BOM của Spring Cloud; **không tự ghép các phiên bản bất kỳ** của Boot và Cloud Function. Với một dự án mới, nên cập nhật lên các bản vá còn được hỗ trợ nhưng phải giữ cặp release train tương thích. Trong lab này, ta ghim cặp phiên bản trên để các đoạn mã và dependency có một mốc thống nhất.

Không cần cài Docker, Kafka, RabbitMQ hoặc serverless CLI để hoàn thành bài thực hành chính.

## 3. Cấu trúc dự án

Tạo thư mục dự án `text-function-lab`:

~~~text
text-function-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/textlab/
    │   │   ├── TextLabApplication.java
    │   │   ├── TextOperations.java
    │   │   ├── TextAuditStore.java
    │   │   └── TextFunctions.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/textlab/
            ├── TextOperationsTest.java
            ├── TextFunctionCatalogTest.java
            └── TextFunctionHttpTest.java
~~~

**Quy ước package:** các lớp dưới đây đều thuộc `com.example.textlab`. Đặt ứng dụng `@SpringBootApplication` ở cùng package giúp Spring quét các bean cần thiết theo quy tắc component scanning thông thường.

## 4. Khai báo dependency bằng Maven

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>text-function-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>text-function-lab</name>
    <description>Supplier, Function, Consumer text processing lab</description>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <!-- Spring Boot MVC/Tomcat cho bài thử HTTP -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Web adapter và các thành phần Spring Cloud Function cần thiết -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-web</artifactId>
        </dependency>

        <!-- JUnit 5, SpringBootTest, MockMvc -->
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
~~~

Ở ví dụ này:

- `spring-boot-starter-web` kích hoạt web application dùng Spring MVC.
- `spring-cloud-function-web` cung cấp cơ chế export functional bean qua HTTP và tích hợp `FunctionCatalog`.
- Spring Cloud BOM quản lý phiên bản module Spring Cloud Function tương ứng, tránh ghi version riêng cho từng artifact.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, MockMvc và hạ tầng Spring Test.

**Lưu ý:** `spring-cloud-function-web` và `spring-cloud-starter-function-web` là hai cách khai báo dependency khác nhau được tài liệu nhắc đến; trong lab này chủ động dùng `spring-cloud-function-web` cùng Spring MVC starter. Không cần thêm cả hai vào cùng một dự án. Khi đổi sang Spring Boot 4.x, hãy kiểm tra lại tên starter web và Cloud release train tương ứng thay vì thay số version một cách máy móc.

## 5. Tạo lớp khởi động Spring Boot

Tạo `src/main/java/com/example/textlab/TextLabApplication.java`:

~~~java
package com.example.textlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TextLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(TextLabApplication.class, args);
    }
}
~~~

`@SpringBootApplication` sẽ quét các component trong `com.example.textlab` và các package con. `TextFunctions` phía dưới dùng `@Configuration`/`@Bean`, còn `TextAuditStore` dùng `@Component`.

## 6. Viết logic xử lý văn bản độc lập với framework

Tạo `src/main/java/com/example/textlab/TextOperations.java`:

~~~java
package com.example.textlab;

import java.util.Locale;
import java.util.regex.Pattern;

public final class TextOperations {

    private static final Pattern WHITESPACE = Pattern.compile(
            "\\s+",
            Pattern.UNICODE_CHARACTER_CLASS);

    private TextOperations() {
    }

    public static String normalize(String input) {
        if (input == null) {
            throw new IllegalArgumentException("text must not be null");
        }

        String trimmed = input.strip();
        if (trimmed.isEmpty()) {
            return "";
        }

        String collapsed = WHITESPACE.matcher(trimmed)
                .replaceAll(" ");
        return collapsed.toUpperCase(Locale.ROOT);
    }

    public static int countWords(String input) {
        String normalized = normalize(input);
        if (normalized.isEmpty()) {
            return 0;
        }

        return normalized.split(" ").length;
    }
}
~~~

Đây là **lõi nghiệp vụ thuần Java**, không phụ thuộc Spring. Nó đảm nhận hai việc:

1. `normalize`: bỏ khoảng trắng ở hai đầu bằng `strip()`, gộp các nhóm whitespace thành một dấu cách, rồi đổi thành chữ hoa với `Locale.ROOT`.
2. `countWords`: chuẩn hóa đầu vào và đếm các nhóm ký tự ngăn cách bằng dấu cách.

**Vì sao dùng `Locale.ROOT`?** `String.toUpperCase()` không truyền locale có thể chịu ảnh hưởng locale mặc định của máy. Khi kết quả cần nhất quán giữa máy phát triển và môi trường triển khai, dùng `Locale.ROOT` giúp giảm bất ngờ.

**Vì sao dùng `Pattern.UNICODE_CHARACTER_CLASS`?** Với dữ liệu tiếng Việt hoặc văn bản Unicode, các dạng whitespace có thể rộng hơn dấu cách ASCII. Cách biên dịch pattern này giúp `\\s` xử lý Unicode whitespace theo quy tắc Java. Tuy nhiên, ví dụ chỉ dạy cách **tách từ theo whitespace**, không phải phân đoạn từ ngôn ngữ tự nhiên: dấu câu vẫn đi cùng token; tiếng Việt nhiều âm tiết không đồng nhất với từ ngữ nghĩa.

### 6.1. Ví dụ kết quả

| Input | `normalize(input)` | `countWords(input)` |
| --- | --- | ---: |
| `"  Spring   Cloud  Function  "` | `"SPRING CLOUD FUNCTION"` | 3 |
| `"  học    Java  "` | `"HỌC JAVA"` | 2 |
| `"hello"` | `"HELLO"` | 1 |
| `"  "` | `""` | 0 |
| `null` | Ném `IllegalArgumentException` | Ném `IllegalArgumentException` |

Ta xác định rõ chính sách input null thay vì để `NullPointerException` xảy ra ngẫu nhiên trong phép xử lý chuỗi. Ở biên HTTP/messaging, việc chuyển lỗi này thành mã trạng thái hoặc message lỗi phụ thuộc adapter; đừng giả định cứ `IllegalArgumentException` là HTTP 400.

## 7. Tạo nơi ghi nhận kết quả của Consumer

Tạo `src/main/java/com/example/textlab/TextAuditStore.java`:

~~~java
package com.example.textlab;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class TextAuditStore {

    private final CopyOnWriteArrayList<String> entries =
            new CopyOnWriteArrayList<>();

    public void record(String value) {
        entries.add(value);
    }

    public List<String> snapshot() {
        return List.copyOf(entries);
    }

    public void clear() {
        entries.clear();
    }
}
~~~

`TextAuditStore` là một **Spring component** được inject vào bean consumer. `CopyOnWriteArrayList` giúp các phép thêm/đọc đơn giản tránh lỗi truy cập đồng thời trong lab.

**Không dùng thiết kế này cho production:**

- Dữ liệu biến mất khi ứng dụng khởi động lại.
- Bộ nhớ tăng nếu nhận vô số văn bản mà không giới hạn.
- `CopyOnWriteArrayList` sao chép mảng khi ghi, không phù hợp với luồng ghi dày đặc.
- Văn bản có thể chứa dữ liệu cá nhân hoặc bí mật; không nên giữ vô hạn hoặc in nguyên văn vào log.

Trong ứng dụng thật, hãy thay bằng một interface audit và implementation dùng kho lưu trữ/queue phù hợp, kèm chính sách retention, kiểm soát quyền truy cập và quan sát lỗi.

## 8. Đăng ký Supplier, Function và Consumer thành @Bean

Tạo `src/main/java/com/example/textlab/TextFunctions.java`:

~~~java
package com.example.textlab;

import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TextFunctions {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(TextFunctions.class);

    @Bean
    public Supplier<String> sampleText() {
        return () -> "  Spring   Cloud  Function  ";
    }

    @Bean
    public Function<String, String> normalizeText() {
        return TextOperations::normalize;
    }

    @Bean
    public Function<String, String> tagText() {
        return value -> "[TEXT] " + value;
    }

    @Bean
    public Function<String, Integer> countWords() {
        return TextOperations::countWords;
    }

    @Bean
    public Consumer<String> auditText(TextAuditStore auditStore) {
        return value -> {
            auditStore.record(value);
            // Trong lab, chỉ ghi số ký tự để không log văn bản thô.
            LOGGER.info("Đã ghi nhận văn bản dài {} ký tự",
                    value.length());
        };
    }
}
~~~

Đoạn code trên thể hiện ba kiểu bean:

**Supplier:** `sampleText()` trả một hàm không có đối số. Framework gọi `get()` để lấy văn bản mẫu khi adapter tương ứng cần dữ liệu.

**Function:** `normalizeText()`, `tagText()` và `countWords()` nhận một `String` và trả kết quả. Nhờ có return type với generic tường minh, `FunctionCatalog` và adapter có thông tin kiểu đích để chuyển đổi.

**Consumer:** `auditText()` nhận `String`, ghi nhận bằng `TextAuditStore` và không trả kết quả nghiệp vụ. `accept(...)` trong Java có kiểu `void`; đây **không phải** một `Function<String, Void>`.

### 8.1. Đừng nhầm tên bean với tên lớp

| Bean trong catalog | Được tạo bởi method | Java functional interface |
| --- | --- | --- |
| `sampleText` | `TextFunctions.sampleText()` | `Supplier<String>` |
| `normalizeText` | `TextFunctions.normalizeText()` | `Function<String,String>` |
| `tagText` | `TextFunctions.tagText()` | `Function<String,String>` |
| `countWords` | `TextFunctions.countWords()` | `Function<String,Integer>` |
| `auditText` | `TextFunctions.auditText(...)` | `Consumer<String>` |

Tên mặc định trong `FunctionCatalog` đến từ tên bean/method `@Bean`. Khi một dự án có nhiều functional bean, hãy luôn **lookup đúng tên** hoặc chọn function bằng cấu hình adapter; không phụ thuộc vào cơ chế fallback dành cho catalog chỉ có một function.

### 8.2. Vì sao chưa gọi get/apply/accept ngay trong @Bean?

Mỗi phương thức `@Bean` trả **một đối tượng thực thi giao diện functional**, ví dụ lambda. Nó không thực hiện toàn bộ nghiệp vụ ngay lúc Spring tạo bean:

~~~text
Spring tạo bean normalizeText
        |
        v
Bean chứa Function<String,String>
        |
        v
FunctionCatalog tra cứu hoặc adapter chọn hàm
        |
        v
apply(input) được gọi khi có dữ liệu
~~~

Điều này quan trọng với `Supplier`: tạo bean `sampleText` không có nghĩa nội dung mẫu đã được phát lên Kafka hay trả cho client. Chỉ có adapter/đoạn code gọi `get()` mới thực sự lấy giá trị.

## 9. Cấu hình application.yml cho bài HTTP

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: text-function-lab
  cloud:
    function:
      single-function-fallback-enabled: false

server:
  port: 8080
~~~

Vì ứng dụng có **nhiều bean**, bài thực hành sử dụng đường dẫn HTTP theo đúng **tên function**: `/sampleText`, `/normalizeText`, `/auditText`... Không đặt `spring.cloud.function.definition` chỉ để chọn một bean, vì ta muốn thử tất cả các hàm trong cùng một ứng dụng web.

`single-function-fallback-enabled: false` ngăn tình huống catalog chỉ có một hàm mà tên bất kỳ cũng được fallback về hàm đó. Thuộc tính này giúp kiểm thử sai tên rõ ràng hơn; nó **không phải** công tắc bật/tắt bean trong Spring context.

### 9.1. Khi nào cần spring.cloud.function.definition?

Khi sử dụng Spring Cloud Stream, nên khai báo function cần bind:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeText
~~~

Với web adapter, `definition` có thể dùng để chọn các function được export, chỉ định composition hoặc ánh xạ hàm vào root path. **Không áp dụng đồng thời cấu hình minh họa này với cấu hình lab đang thử tất cả các endpoint** nếu chưa hiểu quy tắc lọc function. Cùng một `FunctionCatalog` có thể chứa nhiều bean, nhưng adapter chỉ export/bind những gì cấu hình yêu cầu.

## 10. Kiểm thử từng bước bằng Java thuần

Trước khi khởi tạo Spring, nên kiểm chứng `TextOperations` độc lập. Tạo `src/test/java/com/example/textlab/TextOperationsTest.java`:

~~~java
package com.example.textlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class TextOperationsTest {

    @Test
    void normalizesSpacesAndUppercase() {
        assertEquals("SPRING CLOUD FUNCTION",
                TextOperations.normalize(
                        "  Spring   Cloud  Function  "));
    }

    @Test
    void supportsVietnameseLetters() {
        assertEquals("HỌC SPRING CLOUD",
                TextOperations.normalize(
                        "  học   Spring\t Cloud "));
    }

    @Test
    void countsWordsAndHandlesBlankText() {
        assertEquals(3,
                TextOperations.countWords(
                        "  Spring  Cloud Function  "));
        assertEquals(0, TextOperations.countWords("  \t  "));
        assertEquals("", TextOperations.normalize("  \t  "));
    }

    @Test
    void rejectsNullExplicitly() {
        assertThrows(IllegalArgumentException.class,
                () -> TextOperations.normalize(null));
        assertThrows(IllegalArgumentException.class,
                () -> TextOperations.countWords(null));
    }
}
~~~

Các test này giúp bắt lỗi ở thuật toán chuẩn hóa và đếm từ nhanh chóng, không cần khởi động web server. Nhưng chúng chưa chứng minh Spring đã đăng ký functional bean hoặc `FunctionCatalog` tra cứu đúng tên.

## 11. Kiểm thử toàn bộ Supplier → Function → Consumer qua FunctionCatalog

Tạo `src/test/java/com/example/textlab/TextFunctionCatalogTest.java`:

~~~java
package com.example.textlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(
        classes = TextLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class TextFunctionCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    @Autowired
    private TextAuditStore auditStore;

    @BeforeEach
    void resetAudit() {
        auditStore.clear();
    }

    @Test
    void executesSupplierFunctionConsumerPipeline() {
        Supplier<String> supplier = catalog.lookup("sampleText");
        Function<String, String> normalize =
                catalog.lookup("normalizeText");
        Consumer<String> consumer = catalog.lookup("auditText");

        assertNotNull(supplier);
        assertNotNull(normalize);
        assertNotNull(consumer);

        String raw = supplier.get();
        String processed = normalize.apply(raw);
        consumer.accept(processed);

        assertEquals("SPRING CLOUD FUNCTION", processed);
        assertEquals(
                List.of("SPRING CLOUD FUNCTION"),
                auditStore.snapshot());
    }

    @Test
    void countsWordsThroughCatalog() {
        Function<String, Integer> count =
                catalog.lookup("countWords");

        assertNotNull(count);
        assertEquals(3,
                count.apply("  Spring   Cloud   Function  "));
        assertEquals(0, count.apply(" "));
    }

    @Test
    void handlesUnknownName() {
        assertNull(catalog.lookup("missingFunction"));
    }
}
~~~

**Điều được chứng minh:**

- Spring context có các functional bean cần dùng.
- `FunctionCatalog` nhận diện `Supplier`, `Function` và `Consumer` theo tên.
- Mỗi hàm thực thi đúng kiểu và dữ liệu.
- Tác dụng phụ của consumer có thể quan sát qua `TextAuditStore`.

**Điều chưa được chứng minh:** HTTP endpoint, chuyển đổi JSON, Spring Cloud Stream binding, acknowledgment trên broker hoặc hành vi retry ở môi trường serverless. Đó là các kiểm thử adapter riêng.

### 11.1. Tại sao lookup qua catalog thay vì lấy bean gốc?

~~~java
// Bean gốc: chỉ là functional object do Spring tạo.
Function<String, String> original =
        new TextFunctions().normalizeText();

// Hàm qua catalog: có thể được SCF bọc để hỗ trợ conversion/composition.
Function<String, String> instrumented =
        catalog.lookup("normalizeText");
~~~

Hai function có thể có hành vi nghiệp vụ giống nhau, nhưng **không nên so class runtime hoặc instance identity của chúng**: `FunctionCatalog` có thể cung cấp wrapper khác với bean gốc. Trong test tích hợp, hãy kiểm tra lookup theo tên và giá trị thực tế.

## 12. Composition: ghép các Function mà không viết một controller mới

Spring Cloud Function hỗ trợ composition dạng:

~~~text
normalizeText|tagText
~~~

Nó biểu diễn:

~~~text
Input: "  Spring   Cloud Function  "
          |
          v
normalizeText.apply(...)
          |
          v
"SPRING CLOUD FUNCTION"
          |
          v
tagText.apply(...)
          |
          v
"[TEXT] SPRING CLOUD FUNCTION"
~~~

Thêm test sau vào `TextFunctionCatalogTest`:

~~~java
@Test
void composesTwoFunctionsInOrder() {
    Function<String, String> pipeline =
            catalog.lookup("normalizeText|tagText");

    assertNotNull(pipeline);
    assertEquals(
            "[TEXT] SPRING CLOUD FUNCTION",
            pipeline.apply("  Spring   Cloud Function  "));
}
~~~

Composition **ghép tuần tự**, không phát cùng một payload ra hai topic hay tự tạo nhiều endpoint. `normalizeText|tagText` vẫn là một function nhận một chuỗi và trả một chuỗi.

### 12.1. Chữ ký giữa hai hàm phải tương thích

| Cách ghép | Đánh giá |
| --- | --- |
| `normalizeText|tagText` | Hợp lệ: String → String → String |
| `normalizeText|countWords` | Hợp lệ: String → String → Integer |
| `sampleText|normalizeText` | Supplier sau composition: không có input, trả String |
| `normalizeText|auditText` | Consumer sau composition: nhận String và kết thúc bằng side effect |
| `auditText|normalizeText` | Không hợp lý: consumer không tạo payload đầu ra cho function sau |
| `countWords|tagText` | Không trực tiếp tương thích: Integer → String, cần converter hoặc hàm đổi kiểu có chủ đích |

Spring Cloud Function còn hỗ trợ composition có `Supplier` hoặc `Consumer` với hợp đồng kết quả riêng. Để lab dễ kiểm chứng, ta dùng hai `Function<String,String>` trong test composition chính, còn luồng từ Supplier đến Consumer được minh họa bằng cách gọi từng bean trực tiếp.

### 12.2. Thực hành composition với kết quả số

Thêm một test:

~~~java
@Test
void composedFunctionCanReturnInteger() {
    Function<String, Integer> pipeline =
            catalog.lookup("normalizeText|countWords");

    assertNotNull(pipeline);
    assertEquals(3,
            pipeline.apply("  Spring Cloud   Function "));
}
~~~

Ở đây `countWords` tự chuẩn hóa đầu vào để dùng độc lập; việc chuẩn hóa lặp trong composition là chấp nhận được trong lab, nhưng có thể tối ưu khi quy mô lớn. **Không** đặt bean `countWords` dưới dạng `Consumer` vì nghiệp vụ cần một kết quả `Integer`.

## 13. Kiểm thử HTTP adapter bằng MockMvc

Vì dự án có `spring-cloud-function-web` và Spring MVC, các function có thể được export dưới dạng endpoint với tên function trong URL.

Tạo `src/test/java/com/example/textlab/TextFunctionHttpTest.java`:

~~~java
package com.example.textlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = TextLabApplication.class)
@AutoConfigureMockMvc
class TextFunctionHttpTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private TextAuditStore auditStore;

    @BeforeEach
    void resetAudit() {
        auditStore.clear();
    }

    @Test
    void exposesFunctionOverHttp() throws Exception {
        mvc.perform(post("/normalizeText")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.TEXT_PLAIN)
                        .content("  Spring   Cloud Function  "))
                .andExpect(status().isOk())
                .andExpect(content().string("SPRING CLOUD FUNCTION"));
    }

    @Test
    void invokesConsumerOverHttp() throws Exception {
        mvc.perform(post("/auditText")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("SPRING CLOUD FUNCTION"))
                .andExpect(status().isAccepted());

        assertEquals(
                List.of("SPRING CLOUD FUNCTION"),
                auditStore.snapshot());
    }
}
~~~

**Vì sao test consumer trả 202?** Tài liệu web adapter của Spring Cloud Function mô tả `POST /{consumer}` với trạng thái `202 Accepted` (và thường trả lại request body). Nó khác `POST /{function}` trả kết quả xử lý với `200 OK`. Trạng thái 202 **không** có nghĩa dữ liệu đã được lưu bền vững hoặc gửi broker; trong lab consumer chỉ ghi vào bộ nhớ.

Nếu một test HTTP có hành vi khác sau khi cập nhật phiên bản, đối chiếu tài liệu web adapter và HTTP response thực tế, không thay assertion một cách tùy tiện để test pass.

## 14. Chạy ứng dụng và gọi từng endpoint

Trong thư mục `text-function-lab`, chạy test:

~~~bash
mvn test
~~~

Nếu toàn bộ test pass, chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Ứng dụng Spring Boot có thể lắng nghe tại `http://localhost:8080` theo `application.yml`. Mở **terminal thứ hai** để thử các lời gọi dưới đây.

### 14.1. Gọi Supplier bằng GET

~~~bash
curl -i http://localhost:8080/sampleText
~~~

HTTP status mong đợi: **200 OK**. Response body chứa chuỗi mẫu `"  Spring   Cloud  Function  "` với whitespace như ban đầu. `Supplier` không nhận request body.

### 14.2. Gọi Function chuẩn hóa bằng POST

~~~bash
curl -i -X POST http://localhost:8080/normalizeText \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data-binary "  Spring   Cloud Function  "
~~~

Response body mong đợi:

~~~text
SPRING CLOUD FUNCTION
~~~

Chọn `Content-Type: text/plain` vì bean nhận `String`, và chọn `Accept: text/plain` để yêu cầu kết quả text. Những ví dụ có khoảng trắng sử dụng `--data-binary` để bảo toàn nội dung được gửi.

### 14.3. Đếm từ

~~~bash
curl -i -X POST http://localhost:8080/countWords \
  -H "Content-Type: text/plain" \
  -H "Accept: application/json" \
  --data-binary "  Spring   Cloud   Function  "
~~~

Kết quả nghiệp vụ mong đợi là số nguyên `3`. Cách adapter biểu diễn response (text hoặc JSON scalar) phụ thuộc conversion/content negotiation; do đó cần kiểm tra `Content-Type` trên response thay vì mặc định đây là một DTO JSON có thuộc tính `count`.

### 14.4. Gọi Consumer và quan sát log

~~~bash
curl -i -X POST http://localhost:8080/auditText \
  -H "Content-Type: text/plain" \
  --data-binary "SPRING CLOUD FUNCTION"
~~~

Mong đợi HTTP **202 Accepted** và log tương tự:

~~~text
Đã ghi nhận văn bản dài 21 ký tự
~~~

Đây là log mẫu mô tả sự kiện xử lý; độ dài được tính theo `String.length()` của Java (số đơn vị UTF-16, không nhất thiết bằng số ký tự người dùng nhìn thấy với mọi Unicode). `TextAuditStore` đã nhận một phần tử, nhưng không có HTTP endpoint để đọc kho audit trong lab; ta xác nhận qua test catalog/MockMvc.

### 14.5. Gọi composition bằng URL

Web adapter hỗ trợ gọi composition bằng tên function phân tách bằng dấu phẩy hoặc pipe. Dùng **dấu phẩy** để tránh ký tự `|` bị shell diễn giải:

~~~bash
curl -i -X POST "http://localhost:8080/normalizeText,tagText" \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data-binary "  Spring   Cloud  Function  "
~~~

Kết quả mong đợi:

~~~text
[TEXT] SPRING CLOUD FUNCTION
~~~

**Windows PowerShell:** trong các bản PowerShell mà `curl` là alias của `Invoke-WebRequest`, hãy dùng `curl.exe` hoặc chuyển các lệnh sang cú pháp `Invoke-RestMethod`. Ký tự `\` xuống dòng trong ví dụ là cú pháp shell Unix/Git Bash, không phải cách nối dòng mặc định của PowerShell.

## 15. Phân biệt gọi hàm và luồng dữ liệu trên messaging

Trong lab, một `FunctionCatalog` chứa nhiều bean nhưng **chưa có message binder**. Nếu sau này muốn gắn `normalizeText` vào topic của Spring Cloud Stream, cần thêm dependency/binder thích hợp và chọn function:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeText
    stream:
      bindings:
        normalizeText-in-0:
          destination: texts.raw
          content-type: text/plain
        normalizeText-out-0:
          destination: texts.normalized
          content-type: text/plain
~~~

Sơ đồ:

~~~text
texts.raw
   |
   v
normalizeText-in-0
   |
   v
Function<String,String>
   |
   v
normalizeText-out-0
   |
   v
texts.normalized
~~~

Cấu hình này **chỉ mang tính minh họa mở rộng**; dự án Maven trong lab chưa thêm Spring Cloud Stream hoặc binder nên không thể gửi/nhận message broker.

### 15.1. Consumer và lỗi giao nhận

Nếu chuyển `auditText` từ HTTP sang messaging, consumer vẫn có hợp đồng `Consumer<String>` nhưng sẽ có thêm bài toán:

- Xử lý cùng message nhiều lần (*at-least-once delivery*) và idempotency.
- Số lượng message đã xử lý và chỉ số partition/binding.
- Retry/DLQ, lỗi mạng, khả năng lưu dữ liệu bền vững.
- Kiểm soát dữ liệu nhạy cảm và thời gian giữ audit.

Những trách nhiệm đó thuộc adapter/binder và tầng hạ tầng, không tự xuất hiện chỉ vì ta sử dụng `Consumer`. **Gọi thành công `accept(text)` trong unit test không chứng minh broker đã ACK message.**

### 15.2. Dùng lại cùng nghiệp vụ ở serverless

Nếu triển khai một hàm xử lý văn bản qua AWS Lambda, Azure Functions hoặc Google Cloud Functions, bean `normalizeText` vẫn là logic `String → String`. Tuy vậy adapter serverless phải ánh xạ request/event payload và output theo hợp đồng trigger cụ thể. Một function hiện có thể tái sử dụng, nhưng không có nghĩa tự động tạo HTTP route, SQS event source mapping hay queue đầu ra trên nền tảng.

## 16. Bài tập mở rộng theo mức độ

### Bài A — Cắt khoảng trắng nhưng giữ chữ thường

Thêm một bean:

~~~java
@Bean
public Function<String, String> collapseWhitespace() {
    return input -> {
        if (input == null) {
            throw new IllegalArgumentException("text must not be null");
        }
        return input.strip().replaceAll("\\s+", " ");
    };
}
~~~

Đây là ví dụ nhỏ với regex thông thường; để xử lý Unicode whitespace tương tự `TextOperations.normalize`, hãy tái sử dụng pattern đã khai báo trong lõi nghiệp vụ hoặc trích helper phù hợp. Đừng sao chép chính sách normalize sang nhiều vị trí mà rồi chúng cho kết quả khác nhau.

**Yêu cầu:** Test `collapseWhitespace("  Xin  chào  ") == "Xin chào"`. Sau đó ghép `collapseWhitespace|normalizeText` và so với gọi `normalizeText` trực tiếp.

### Bài B — Hàm lọc chuỗi rỗng

Viết `Function<String, String> rejectBlank` ném `IllegalArgumentException` khi chuỗi đầu vào chỉ có khoảng trắng:

~~~java
@Bean
public Function<String, String> rejectBlank() {
    return text -> {
        String normalized = TextOperations.normalize(text);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("text must not be blank");
        }
        return normalized;
    };
}
~~~

**Yêu cầu:** Test cả dữ liệu hợp lệ và trường hợp ném exception. Sau đó kiểm thử HTTP riêng để quan sát adapter ánh xạ lỗi thế nào. Đừng khẳng định `IllegalArgumentException` luôn trở thành HTTP 400 nếu chưa cấu hình và kiểm chứng.

### Bài C — Kết quả có cấu trúc

Thêm DTO và function:

~~~java
public record TextSummary(String normalized, int words) {
}

@Bean
public Function<String, TextSummary> summarizeText() {
    return raw -> new TextSummary(
            TextOperations.normalize(raw),
            TextOperations.countWords(raw));
}
~~~

**Yêu cầu:** Đặt `TextSummary` trong một file Java của riêng nó hoặc khai báo nested record phù hợp trong project thật. Viết unit/catalog test cho `summarizeText` và test HTTP `Accept: application/json` để quan sát response JSON có `normalized`, `words`. DTO giúp hợp đồng output rõ ràng hơn việc trả một chuỗi tự ghép dấu phân cách.

### Bài D — Dữ liệu tiếng Việt và dấu câu

Thử dữ liệu:

~~~text
  Xin   chào,   Spring Cloud Function!
~~~

Quan sát kết quả:

~~~text
XIN CHÀO, SPRING CLOUD FUNCTION!
~~~

**Câu hỏi:** Bộ đếm đơn giản sẽ đếm bao nhiêu token? Vì sao đếm token theo whitespace không đủ để xử lý “từ” về mặt ngôn ngữ tiếng Việt? Hãy viết một test cố định kỳ vọng, sau đó ghi rõ giới hạn trước khi nâng cấp thuật toán.

### Bài E — Composition có Consumer

Nghiên cứu chức năng `normalizeText|auditText`. Theo hợp đồng, ghép Function với Consumer cho ra **Consumer**: đầu vào String, cuối pipeline chỉ có side effect.

**Yêu cầu:** Tạo test catalog tra cứu composition tương ứng, gọi `accept(...)` rồi assert nội dung mới trong `TextAuditStore`. Không kiểm thử bằng cách chờ kết quả String vì Consumer không trả payload.

## 17. Lỗi thường gặp và cách khắc phục

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `mvn test` lỗi thiếu dependency Cloud Function | Spring Cloud BOM hoặc artifact khai báo sai | Kiểm tra `dependencyManagement`, phiên bản Boot/Cloud |
| Ứng dụng chạy nhưng `/normalizeText` trả 404 | Web adapter chưa được kích hoạt, tên bean sai hoặc bị lọc bởi `definition` | Kiểm tra dependency, `@Bean`, logs và cấu hình export |
| `FunctionCatalog.lookup(...)` trả null | Bean không được scan hoặc lookup sai tên | Kiểm tra package và `@SpringBootApplication` |
| `POST /normalizeText` không nhận chuỗi như mong đợi | Content type/charset/body không phù hợp | Dùng `text/plain` và `--data-binary` |
| `GET /sampleText` trả cùng chuỗi nhiều lần | Supplier hiện được cài là nguồn hằng | Đây là hành vi chủ ý; thay supplier khi cần nguồn động |
| `POST /auditText` nhận 202 nhưng không có bản ghi sau khởi động lại | Store chỉ trong bộ nhớ | Thay bằng lưu trữ bền vững nếu nghiệp vụ yêu cầu |
| Composition `tagText|normalizeText` cho kết quả khác `normalizeText|tagText` | Composition có thứ tự | Assert các bước và thứ tự |
| `countWords` sai với dấu câu hoặc tiếng Việt | Chỉ đếm token theo whitespace | Ghi rõ hợp đồng; nâng cấp tokenizer khi cần |
| Bài test audit thỉnh thoảng thất bại | Singleton store còn dữ liệu từ test khác/chạy song song | Dọn trạng thái, cô lập test, tránh parallel không kiểm soát |
| Code chạy trên máy A nhưng không chạy máy B | JDK/Maven/Boot/Cloud version không tương thích | Kiểm tra Java 17+, BOM và dependency graph |
| Nhầm kết quả consumer thành HTTP 200 của function | `Consumer` có hợp đồng không trả payload | Kiểm tra web adapter và trạng thái 202 |
| Đưa văn bản bí mật vào log | Logging raw input không được kiểm soát | Chỉ log metadata an toàn và áp dụng retention/security |

### 17.1. Các phép kiểm tra nhanh theo đúng thứ tự

1. Dùng `java -version` để xác nhận JDK.
2. Dùng `mvn -version` để xác nhận Maven và JDK mà Maven đang dùng.
3. Chạy `mvn test`, xử lý lỗi compile/logic trước.
4. Kiểm tra `@Bean` nằm trong package được Spring scan.
5. Xác minh `FunctionCatalog.lookup("normalizeText")` trong test context.
6. Chạy `mvn spring-boot:run` và kiểm tra cổng 8080.
7. Gửi `POST` với `text/plain`, quan sát status/content type.
8. Kiểm tra composition bằng URL có dấu phẩy.
9. Khi dùng messaging/serverless, bổ sung integration test riêng cho adapter thay vì suy từ HTTP test.

## 18. Tiêu chí hoàn thành bài thực hành

| Tiêu chí | Kết quả cần chứng minh | Phương pháp |
| --- | --- | --- |
| Supplier hoạt động | `sampleText.get()` trả văn bản mẫu | Catalog test hoặc `GET /sampleText` |
| Function chuẩn hóa đúng | Có `"SPRING CLOUD FUNCTION"` | `TextOperationsTest`, catalog test, HTTP test |
| Hàm đếm từ đúng | Văn bản ví dụ cho `3` | Unit/catalog test |
| Consumer có side effect | Kho audit nhận một giá trị chuẩn hóa | Catalog/MockMvc test |
| Composition chạy đúng | `normalizeText|tagText` cho `[TEXT] ...` | Catalog test và HTTP |
| Quản lý lỗi rõ ràng | Input `null` bị từ chối, chuỗi trống xử lý theo quy tắc | Unit test |
| Phân biệt tầng tích hợp | Nêu rõ catalog ≠ web route ≠ message broker | Phân tích kết quả test |
| Giới hạn được hiểu | Whitespace count đơn giản; audit trong bộ nhớ; không log raw text | Giải thích và đề xuất nâng cấp |

**Tóm tắt kiến thức rút ra:** `Supplier` cung cấp dữ liệu, `Function` biến đổi dữ liệu, `Consumer` thực hiện tác dụng phụ. Logic có thể được kiểm thử và gọi qua `FunctionCatalog` mà không phải gắn cứng vào HTTP; composition nối các function có chữ ký tương thích. Adapter đưa cùng hàm sang môi trường thực thi mới, nhưng mỗi adapter vẫn có hợp đồng, chuyển đổi dữ liệu, bảo mật và bảo đảm giao nhận riêng.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không gọi `new TextFunctions().normalizeText()` để thay thế toàn bộ `FunctionCatalog`?

**Đáp án:** Cách gọi trực tiếp chỉ lấy lambda gốc, bỏ qua nhận diện bean, wrapper, type conversion và composition do Spring Cloud Function cung cấp. Unit test có thể gọi trực tiếp, nhưng integration test của framework cần đi qua catalog.

**Câu 2.** Nếu `sampleText` trả dữ liệu giống nhau mỗi lần GET, đây có phải lỗi của `Supplier`?

**Đáp án:** Không. Đó là do implementation cố tình trả chuỗi hằng. `Supplier` chỉ mô tả hợp đồng không nhận input và tạo output; dữ liệu có thể hằng, động hoặc lấy từ nguồn khác tùy nghiệp vụ.

**Câu 3.** `countWords` trả Integer. Có thể nối `countWords|tagText` trực tiếp mà không xét kiểu không?

**Đáp án:** Không nên. Đầu ra Integer không tự tương thích đầu vào String của `tagText`. Nếu muốn ghép, nên thêm function chuyển số sang chuỗi hoặc kiểm tra converter/hợp đồng rõ ràng.

**Câu 4.** Vì sao test `auditText.accept(...)` thành công không có nghĩa thông điệp đã lưu vĩnh viễn?

**Đáp án:** Lab sử dụng `TextAuditStore` trong bộ nhớ. `Consumer` chỉ mô tả side effect; tính bền vững phụ thuộc implementation, database và/hoặc binder.

**Câu 5.** `POST /auditText` trả 202 có phải chứng minh message broker đã ACK?

**Đáp án:** Không. HTTP 202 là hợp đồng web adapter cho consumer; lab không có broker.

**Câu 6.** `normalizeText|tagText` và `tagText|normalizeText` có nhất thiết cho cùng output?

**Đáp án:** Không. Composition áp dụng các phép biến đổi **theo đúng thứ tự**. Chỉ khi các phép biến đổi có tính giao hoán với dữ liệu tương ứng thì kết quả mới giống nhau.

**Câu 7.** Việc dùng `Locale.ROOT` có giải quyết đầy đủ bài toán xử lý tiếng Việt?

**Đáp án:** Không. Nó hỗ trợ chuyển chữ hoa nhất quán hơn; tách từ theo `whitespace` vẫn chưa phải phân tích hình thái hoặc xử lý ngôn ngữ tự nhiên.

**Câu 8.** Khi muốn chuyển lab sang Kafka, cần thay toàn bộ `TextOperations` không?

**Đáp án:** Không. Có thể giữ logic chuẩn hóa. Cần bổ sung Spring Cloud Stream/binder, cấu hình binding và thiết kế lỗi/giao nhận theo Kafka.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model và FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Standalone Web Applications, GET Supplier/POST Function/Consumer](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html)
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html)
- [Spring Cloud — Compatibility giữa release train và Spring Boot](https://spring.io/projects/spring-cloud/)
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Java — Supplier, Function, Consumer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
- [Java — Pattern.UNICODE_CHARACTER_CLASS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
