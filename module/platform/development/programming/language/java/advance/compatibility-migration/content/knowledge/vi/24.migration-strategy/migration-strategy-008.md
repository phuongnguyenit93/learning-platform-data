# Tách sửa tương thích khỏi việc áp dụng cú pháp hoặc API mới

Khi nâng một ứng dụng Java từ JDK cũ sang JDK mới, nhóm phát triển thường đứng trước hai mục tiêu hấp dẫn nhưng không đồng nhất:

1. **Làm cho hệ thống hiện tại chạy đúng trên JDK mục tiêu**: xử lý lỗi build, API đã bị loại bỏ, thư viện không tương thích, module encapsulation, các thay đổi runtime, packaging và cấu hình vận hành.
2. **Tận dụng khả năng của Java mới**: dùng `record`, switch expression, pattern matching, text block, collection factory methods, API `java.time`/`java.nio.file` mới, virtual threads, hoặc tái cấu trúc code theo phong cách hiện đại.

Mục tiêu thứ nhất là **compatibility migration**; mục tiêu thứ hai là **modernization**. Chúng có thể được triển khai trong cùng một chương trình nâng cấp, nhưng nên được quản lý như **hai dòng thay đổi riêng** nếu điều kiện kỹ thuật cho phép.

Vì sao? Nếu vừa sửa lỗi tương thích, vừa thay cấu trúc domain object, thay concurrency model và viết lại parser, khi kết quả nghiệp vụ thay đổi nhóm sẽ khó biết nguyên nhân là JDK mới hay refactor mới. Một rollback cũng khó hơn: muốn quay lại hành vi cũ có thể phải quay lại cả những bản vá tương thích cần thiết.

Bài học này xây dựng cách tiếp cận thực tế để **nâng JDK trước mà không đổi chủ đích hành vi nghiệp vụ**, thiết lập bằng chứng hệ thống đã tương thích, rồi hiện đại hóa Java syntax/API qua các đợt riêng có thể kiểm thử và rollback độc lập.

## 1. Phân biệt ba loại thay đổi trong Java migration

Không phải thay đổi nào xuất hiện trong pull request nâng Java cũng thuộc cùng một nhóm.

| Nhóm | Mục đích | Ví dụ | Điều kiện chấp nhận |
|---|---|---|---|
| Sửa tương thích bắt buộc | Khôi phục build hoặc behavior cũ trên JDK đích | Thay API đã bị loại, nâng driver hoặc JVM flag | Kết quả nghiệp vụ không thay đổi ngoài những sửa lỗi đã được chấp nhận |
| Sửa bảo mật/correctness bắt buộc | Đáp ứng chính sách vận hành khi lên JDK mới | Thay thuật toán TLS yếu, sửa deserialization không an toàn | Có yêu cầu, review và kiểm thử tác động rõ ràng |
| Hiện đại hóa tùy chọn | Cải thiện cách viết, bảo trì hoặc khai thác API mới | Thay DTO thành record, dùng switch expression, virtual threads | Đánh giá như một thay đổi độc lập, có bằng chứng lợi ích và regression tests |

Một PR có thể chứa một vài cập nhật dependency bắt buộc để build chạy được trên JDK mới. Điều này không làm cho toàn bộ thay đổi thành “modernization”. Ngược lại, việc đổi từ vòng lặp truyền thống sang stream không phải bản vá tương thích chỉ vì dự án đang nâng Java.

### 1.1. Compatibility không có nghĩa giữ nguyên mọi bytecode

Mục tiêu compatibility là **giữ nguyên những hợp đồng quan trọng**, không phải yêu cầu source và binary output giống hệt:

- Public API/CLI behavior.
- Kết quả nghiệp vụ với cùng input.
- Database schema và persisted data contracts.
- HTTP/event/message formats được các consumer hiện tại sử dụng.
- Security guarantees và quyền truy cập.
- Hiệu năng trong ngưỡng chấp nhận.
- Cơ chế triển khai, quan sát và phục hồi.

Khi JDK mới thay đổi chính sách bảo mật, có thể cần điều chỉnh thuật toán hoặc trust configuration. Đây vẫn là migration cần thiết, nhưng phải ghi rõ phần behavior thay đổi và ai phê duyệt.

### 1.2. Modernization không phải bằng chứng về compatibility

Một lớp được viết lại thành `record` có thể ngắn hơn, nhưng hệ thống vẫn có thể lỗi với JDBC driver cũ hoặc một Java agent không hiểu class-file version. Dùng API mới không chứng minh runtime đã tương thích. Hai mục tiêu cần có kiểm chứng riêng.

## 2. Chiến lược hai đường thay đổi

Một cách diễn đạt rõ:

~~~text
Baseline đang chạy trên JDK cũ
                |
                v
     Compatibility workstream
     - Build tool / dependency
     - Removed APIs / reflection
     - Runtime flags / security
     - Data / protocol compatibility
                |
                v
 Hệ thống cùng hành vi trên JDK mới
                |
                | Baseline mới đã có bằng chứng
                v
      Modernization workstream
     - New syntax / language features
     - New standard-library APIs
     - Refactor cấu trúc code
     - New concurrency / architecture
                |
                v
    Hệ thống được hiện đại hóa có chủ đích
~~~

Khi có đủ khả năng, mỗi mũi tên là một thay đổi có thể phát hành, so sánh và rollback riêng.

### 2.1. Điều kiện “khi có thể”

Không phải lúc nào cũng tách tuyệt đối. Ví dụ:

- Framework target yêu cầu một JDK tối thiểu mới nên phải nâng framework cùng JDK.
- API cũ bị loại bỏ buộc phải thay bằng một library bên ngoài.
- Một thư viện không tương thích JDK mục tiêu chỉ có bản hỗ trợ mới với API đã đổi.
- Chính sách bảo mật bắt buộc loại giao thức/thuật toán yếu ngay trong đợt nâng.
- Hạ tầng deployment không thể vận hành hai phiên bản JDK song song.

Trong các trường hợp này, cần ghi rõ **thay đổi hỗ trợ bắt buộc**, chốt ranh giới và kiểm thử. “Tách” là nguyên tắc giảm biến số, không phải quy tắc cấm mọi sự phụ thuộc.

## 3. Thiết lập đích migration cụ thể

Một mục tiêu chưa đủ rõ:

~~~text
Upgrade Java 8 to latest Java.
~~~

Một mục tiêu tốt hơn:

~~~text
Phase A: Chạy application version hiện tại trên JDK 21.
- Không thay đổi public REST endpoints.
- Không thay đổi JSON/message schemas.
- Không đổi database schema nếu không bắt buộc.
- Sửa lỗi compile/runtime do JDK hoặc dependencies.
- Chạy regression và production-like integration tests.
- Có thể rollback runtime/artifact theo thiết kế.

Phase B: Hiện đại hóa những module được chọn.
- Có đề xuất riêng cho records/switch/API mới.
- Đo tác động và kiểm thử theo từng module.
- Không gộp thay đổi architecture chưa được duyệt.
~~~

Số version dùng trong ví dụ mang tính minh họa; tổ hợp JDK/framework thực tế phải đối chiếu support matrix. Không mặc định mọi framework cũ có thể chạy trực tiếp trên JDK 21.

## 4. Chốt baseline trước khi sửa mã

Nếu không có baseline, nhóm sẽ khó biết lỗi có mới phát sinh hay đã tồn tại.

Tối thiểu cần lưu:

| Phạm vi | Bằng chứng baseline |
|---|---|
| Source | Commit/tag đang chạy, release branch |
| Build | Maven/Gradle Wrapper, plugins, dependency graph |
| JDK | Vendor, release, update, runtime image |
| Framework | Version, BOM, các extension quan trọng |
| Compilation | Source target, `--release` hoặc `source/target` |
| API | HTTP, CLI, event, file, serialization contracts |
| Database | Schema, migrations, dữ liệu lịch sử đặc trưng |
| Operations | JVM flags, GC, memory limits, TLS, agents |
| Tests | Regression, integration, contract, security, performance |
| Metrics | Error rate, p95/p99 latency, CPU, heap, startup, throughput |
| Rollback | Artifact, configuration, data compatibility |

Nếu baseline đã có failing tests, hãy ghi rõ thay vì quy chúng thành lỗi do JDK mới sau này.

### 4.1. Characterization tests

Với legacy code ít test, trước khi refactor có thể bổ sung **characterization tests**: đưa input đại diện vào code hiện tại và ghi nhận output/hành vi đang được dùng. Không phải mọi hành vi cũ đều đúng; lỗi đã biết cần được đánh dấu để không tự động hợp thức hóa bug.

Ví dụ với formatter đơn hàng:

~~~java
public final class ReceiptFormatter {
    public String format(long amount, String currency) {
        return amount + " " + currency;
    }
}
~~~

Test:

~~~java
@Test
void existingReceiptFormatIsStable() {
    ReceiptFormatter formatter = new ReceiptFormatter();
    assertEquals("125000 VND", formatter.format(125000L, "VND"));
}
~~~

Trong compatibility phase, mục tiêu là test vẫn xanh khi runtime/SDK đổi. Sau đó, nếu muốn đưa tiền tệ sang `BigDecimal` hoặc localization API, hãy thực hiện như một thay đổi nghiệp vụ/correctness được xem xét riêng.

## 5. Ma trận JDK, framework và target bytecode

Có ít nhất bốn trục cần phân biệt:

1. JDK đang chạy Maven/Gradle.
2. JDK đang được dùng làm compiler/toolchain.
3. Java source/API/bytecode baseline của artifact.
4. JDK thực sự chạy ứng dụng trong production.

Ví dụ:

~~~text
Build tool: Gradle dùng JDK 21
Compiler toolchain: JDK 21
Compile release target: Java 17
Production runtime: JDK 17 hoặc 21 theo ma trận đã test
~~~

Cấu hình `--release 17` giới hạn source language level, Java SE API được compiler biết và class-file target. Nó **không bảo đảm toàn bộ third-party dependencies** đều chạy trên Java 17, cũng không tự cài runtime Java 17.

### 5.1. Phân biệt đổi runtime và nâng minimum supported Java

Nếu mục tiêu chỉ là cho production chạy JDK 21, có thể giữ `--release 17` hoặc release baseline cũ khi compiler hỗ trợ. Nếu dự án quyết định dùng `record` hoặc một API chỉ có từ Java mới hơn, đây là quyết định **nâng minimum language/API baseline**; nó cần xét mọi consumer đang chạy JDK cũ.

Đừng âm thầm nâng bytecode target chỉ vì CI đã cài JDK mới.

### 5.2. Ma trận framework

Đánh giá:

| Tổ hợp | Khả thi? | Cần xác minh |
|---|---|---|
| Framework cũ + JDK cũ | Baseline | Hiện đang vận hành |
| Framework cũ + JDK mới | Chỉ khi được hỗ trợ | Tốt để tách tác động JDK |
| Framework mới + JDK cũ | Chỉ khi được hỗ trợ | Tốt để tách tác động framework |
| Framework mới + JDK mới | Trạng thái đích | Test đầy đủ |

Nếu hai điểm trung gian không được hỗ trợ, xây bản cầu nối (framework patch/minor hoặc JDK trung gian) hoặc kế hoạch nâng phối hợp. Không chạy một tổ hợp “không được vendor hỗ trợ” trong production chỉ để giữ hình thức hai bước.

## 6. Sửa lỗi compile là compatibility work

Một đợt nâng JDK có thể phát hiện code dùng API đã bị loại bỏ, API chỉ tồn tại ở môi trường cũ hoặc import sai sau khi dependency đổi.

Ví dụ một ứng dụng cũ sử dụng JAXB:

~~~java
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Unmarshaller;
~~~

Ở những bản JDK cũ, các thành phần Java EE liên quan từng được phân phối cùng JDK. Từ JDK 11, nhiều module như JAXB không còn nằm trong JDK distribution. Code có thể báo lỗi thiếu package dù business logic XML không thay đổi.

Cách tiếp cận compatibility:

1. Kiểm tra đúng dependency/API mà ứng dụng hiện dùng.
2. Thêm API và implementation phù hợp bằng Maven/Gradle, theo hệ sinh thái được hỗ trợ.
3. Giữ XML schema, dữ liệu và serialization behavior ổn định.
4. Chạy test unmarshalling/marshalling với XML fixtures cũ.
5. Tách kế hoạch chuyển sang các API/package thế hệ Jakarta (nếu cần) khỏi việc đơn giản giải quyết module đã bị loại, trừ khi bộ dependency bắt buộc kết hợp.

Không lấy lý do JAXB thiếu để viết lại cả protocol XML thành JSON trong cùng một compatibility PR. Đó là **thay đổi hợp đồng dữ liệu** có consumer và rollback riêng.

### 6.1. API nội bộ JDK

Code hoặc dependency có thể từng sử dụng package nội bộ như `sun.*` hoặc gọi reflection vào các module của JDK. Trên JDK mới, điều này có thể gây:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
java.lang.NoClassDefFoundError
~~~

Cách xử lý ưu tiên:

- Tìm API công khai thay thế được JDK hỗ trợ.
- Nâng library/agent tương thích với runtime đích.
- Chỉnh code custom dùng reflection không cần thiết.
- Chỉ dùng `--add-opens` hoặc `--add-exports` như giải pháp chuyển tiếp có phạm vi và kế hoạch loại bỏ.

Ví dụ `--add-opens`:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED \
  -jar app.jar
~~~

Đây là ví dụ cú pháp, **không phải khuyến nghị bật mặc định**. Nó không phục hồi class đã bị xóa, không tự sửa binary incompatibility và có thể nới lỏng encapsulation không mong muốn.

## 7. Dependency upgrade: chỉ nâng mức cần để đạt compatibility

Khi JDK mới khiến một thư viện thất bại, ví dụ ASM/Byte Buddy/Mockito/annotation processor/Java agent cũ không hiểu class-file version mới, cần tìm bản được vendor hỗ trợ.

Nhưng nâng cả framework và hàng chục dependencies khác không liên quan trong cùng commit làm tăng rủi ro.

### 7.1. Cách quản lý

- Chốt dependency graph baseline.
- Xác định artifact nào thực sự gây lỗi, dựa trên stack trace và resolved version.
- Chọn bản tối thiểu phù hợp support/security policy, không nhất thiết bản mới nhất.
- Ghi migration guide của dependency khi có breaking changes.
- Không đổi application-facing API trừ khi cần.
- So resolved graph sau thay đổi.
- Chạy tests cho subsystem sử dụng dependency đó.
- Tách nâng major framework khi có lộ trình hỗ trợ độc lập.

### 7.2. Trường hợp dependency bắt buộc kéo API thay đổi

Nếu library chỉ có bản hỗ trợ JDK mới mà public API đã đổi, việc cập nhật call sites là compatibility work **bắt buộc**, nhưng cần mô tả rõ tại sao. Một compatibility PR không nhất thiết chỉ có các thay đổi một dòng; điều quan trọng là **không trộn thêm refactor tùy chọn** vào đúng phần code đang sửa.

## 8. Ví dụ Maven: giữ release target rõ ràng

Trong `pom.xml` có thể dùng Maven Compiler Plugin phù hợp:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Hoặc khai báo rõ trong plugin:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>VERSION_DA_XAC_MINH</version>
  <configuration>
    <release>17</release>
  </configuration>
</plugin>
~~~

`VERSION_DA_XAC_MINH` là placeholder; phải chọn plugin version thật phù hợp Maven/JDK.

Trong compatibility phase:

~~~bash
./mvnw --version
./mvnw -B clean verify
./mvnw dependency:tree
~~~

Kiểm tra Maven runtime JVM, compiler release và dependency tree. Nâng Maven Wrapper/Compiler Plugin nếu chúng không hỗ trợ JDK build, nhưng không đổi toàn bộ business source sang cú pháp Java mới chỉ vì compiler đã nâng.

## 9. Ví dụ Gradle: tách toolchain và source target

Với Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Các ý nghĩa:

- Wrapper chọn Gradle distribution.
- JVM chạy Gradle daemon có yêu cầu tương thích riêng.
- Java toolchain chọn JDK dùng cho JavaCompile và các task liên quan.
- `options.release` kiểm soát baseline của artifact.
- Test tasks có thể có JavaLauncher/toolchain hoặc JVM runtime riêng, cần kiểm tra.

Kiểm tra:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean build
~~~

Những lệnh này là ví dụ cho người học trong bài; không phải yêu cầu worker chạy build ở STEP 4.

## 10. Sửa tương thích nhưng giữ nguyên hành vi: một ví dụ

Một service cũ tải cấu hình từ resource:

~~~java
package com.acme.app;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ConfigLoader {

    public Properties load() throws IOException {
        Properties config = new Properties();

        try (InputStream input =
                     ConfigLoader.class.getResourceAsStream(
                             "/application.properties")) {
            if (input == null) {
                throw new IOException("Missing application.properties");
            }
            config.load(input);
        }

        return config;
    }
}
~~~

Giả sử sau khi đổi cách đóng gói/JDK, lỗi là launcher dùng sai classpath hoặc resource không được đưa vào JAR. **Bản vá tương thích đúng** có thể là sửa build resource configuration hoặc startup script để resource có mặt, không cần viết lại `ConfigLoader` bằng API mới.

Một refactor hiện đại hóa tùy chọn có thể đổi sang `Files.readString` và external configuration path; nhưng nó có thể thay đổi:

- Nguồn cấu hình: classpath resource → filesystem.
- Quy tắc charset và parsing của `Properties`.
- Working directory assumptions.
- Error behavior, exception messages.
- Security/permission model.

Vì vậy, “code ngắn hơn” không phải bằng chứng behavior tương đương.

## 11. Java mới có API mới: không đồng nghĩa phải áp dụng ngay

Ví dụ `Files.readString` (Java 11+) giúp đọc text:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Trong Java 8, code tương ứng có thể là:

~~~java
String text = new String(
        Files.readAllBytes(path),
        StandardCharsets.UTF_8);
~~~

Nếu dự án chỉ cần chạy trên JDK 21 mà vẫn duy trì source/API baseline Java 8 ở một thư viện dùng chung, **không thể tự thay bằng `Files.readString`** mà vẫn kỳ vọng thư viện chạy trên Java 8. API availability là một hợp đồng runtime, không chỉ là sở thích cú pháp.

Ngoài ra, nếu đọc tệp lớn hoặc muốn streaming, cả hai cách đọc toàn bộ tệp vào memory đều có trade-off. Chọn API mới phải đi kèm đánh giá semantic/performance, không phải tự động đổi mọi chỗ có thể.

### 11.1. List.of và Arrays.asList khác nhau

Java 9 có collection factory methods:

~~~java
List<String> roles = List.of("USER", "ADMIN");
~~~

Code cũ có thể dùng:

~~~java
List<String> roles = Arrays.asList("USER", "ADMIN");
~~~

Chúng không tương đương tuyệt đối:

- `List.of` tạo list không cho phép thay đổi cấu trúc/giá trị qua mutator operations và không chấp nhận phần tử `null`.
- `Arrays.asList` tạo fixed-size list được backing bởi array; có thể `set` phần tử, nhưng không thêm/xóa.
- Hai API có thể khác về exception và aliasing nếu array được chia sẻ.

Một refactor tìm-thay `Arrays.asList` → `List.of` có thể phá logic dù output trước mắt vẫn giống nhau. Hãy xem đây là **modernization change có semantic review**, không phải một bước bắt buộc để hỗ trợ JDK mới.

## 12. Record: ít boilerplate nhưng khác contract

Java `record` phù hợp một số data carrier với trạng thái thành phần rõ và semantics value-like. Ví dụ class DTO cũ:

~~~java
public final class UserView {
    private final String id;
    private final String displayName;

    public UserView(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Có thể hiện đại hóa thành record trên Java release hỗ trợ:

~~~java
public record UserView(String id, String displayName) {
}
~~~

Tuy nhiên, **không phải refactor thay thế tương đương trong mọi framework**:

| Đặc điểm | Class DTO cũ | Record |
|---|---|---|
| Method truy cập ví dụ | `getId()`, `getDisplayName()` | `id()`, `displayName()` |
| Constructor | Tùy ý do developer viết | Canonical constructor theo components |
| Inheritance | Có thể tùy class design | Record không extends user-defined class |
| Mutability | Tùy implementation | Components là final references; không bảo đảm deep immutability |
| equals/hashCode/toString | Do developer/IDE/Lombok viết | Có semantics tự sinh |
| Serialization/binding | Tùy framework | Cần kiểm tra hỗ trợ record của framework |
| Java language baseline | Có thể là Java 8 | Cần Java release có records |

Các tác động có thể gồm JSON serialization, validation, reflection, ORM, constructors và binary API của consumer. Nếu một public library đang được client Java 8 dùng, chuyển `UserView` thành record không chỉ là “cleanup”.

**Đề xuất:** sau khi compatibility phase đã ổn định, chọn record cho DTO mới hoặc module nội bộ trước; dùng contract tests để xác nhận JSON và API behavior.

## 13. Switch expression và pattern matching: cú pháp mới cũng thay semantics

Một enum mapper cũ:

~~~java
public String label(OrderStatus status) {
    switch (status) {
        case CREATED:
            return "Created";
        case PAID:
            return "Paid";
        case CANCELLED:
            return "Cancelled";
        default:
            throw new IllegalArgumentException("Unknown status");
    }
}
~~~

Với Java release có switch expressions:

~~~java
public String label(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case CANCELLED -> "Cancelled";
    };
}
~~~

Đây là refactor có thể hữu ích, nhưng cần đánh giá:

- Enum được thêm giá trị ở version mới.
- Handling `null`.
- Default/fallback behavior.
- Bytecode/source baseline.
- Các nhánh có side effects hoặc fallthrough trong switch cũ.
- Public methods dùng kết quả với assumptions khác.

Tương tự, thay cast truyền thống:

~~~java
if (value instanceof String) {
    String name = (String) value;
    process(name);
}
~~~

bằng pattern matching:

~~~java
if (value instanceof String name) {
    process(name);
}
~~~

thường dễ đọc hơn, nhưng **không cần thiết để ứng dụng chạy trên JDK 21**. Phần thưởng về readability không nên được dùng để biện minh cho việc sửa hàng nghìn file trong PR chỉ nhằm nâng runtime.

## 14. Text block và việc bảo toàn chuỗi đầu ra

Java text block làm SQL/JSON dễ đọc hơn:

~~~java
String query = """
    select o
    from OrderEntity o
    where o.status = :status
    """;
~~~

Nhưng chuyển một chuỗi nối thủ công sang text block có thể đổi whitespace, newline cuối, indentation hoặc escape processing. Với SQL thường không đáng kể trong nhiều trường hợp, nhưng với payload chữ ký số, template, regex, query format hoặc golden fixture thì từng byte có thể quan trọng.

Khi hiện đại hóa:

- So sánh output string nếu contract phụ thuộc byte-level representation.
- Kiểm tra escape sequences và line endings.
- Kiểm tra compiler source release.
- Không gộp thay đổi SQL semantics cùng lúc với việc đổi syntax.
- Giữ migration khỏi thay đổi hợp đồng external API nếu chưa được phê duyệt.

## 15. Virtual threads là modernization về concurrency, không phải “sửa để chạy”

Java 21 có virtual threads như một tính năng nền tảng. Một ứng dụng sử dụng thread pools thông thường có thể xem xét mô hình này, nhưng **nâng JDK lên 21 không yêu cầu chuyển mọi executor sang virtual threads**.

Code truyền thống:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(32);
try {
    Future<String> result = pool.submit(() -> fetchDocument());
    System.out.println(result.get());
} finally {
    pool.shutdown();
}
~~~

Một cách sử dụng API virtual-thread executor trong Java 21:

~~~java
try (ExecutorService pool =
             Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> result = pool.submit(() -> fetchDocument());
    System.out.println(result.get());
}
~~~

Điều này có thể ảnh hưởng:

- Mô hình giới hạn concurrency và backpressure.
- Database connection pool vẫn có số connection hữu hạn.
- Blocking I/O behavior, pinning trong một số trường hợp.
- ThreadLocal state và request context propagation.
- Monitoring, tracing và thread dump assumptions.
- Rate limits của downstream.
- Memory/throughput/latency dưới tải.

Không mặc định virtual threads luôn nhanh hơn hoặc sửa mọi vấn đề performance. Hãy làm pilot riêng có load test và operational monitoring sau khi migration JDK đã ổn định.

## 16. Cải thiện code không đồng nghĩa sửa lỗi runtime

Một anti-pattern là nhìn thấy lỗi trên JDK mới rồi viết lại cấu trúc subsystem:

~~~text
Lỗi gốc:
  Java agent cũ không nhận class-file version mới.

Thay đổi đề xuất sai phạm vi:
  Chuyển controller sang reactive,
  thay DTO thành records,
  viết lại thread pool,
  đổi JSON format.

Thay đổi đúng trọng tâm:
  Nâng Java agent lên version hỗ trợ JDK target,
  giữ behavior ứng dụng,
  test agent + startup + integration.
~~~

Một lỗi rất nhỏ có thể là lý do hợp pháp để áp dụng API mới nếu không còn lựa chọn tương thích, nhưng phải giải thích **quan hệ nhân quả** đó. Nguyên tắc là sửa đủ để đạt mục tiêu, không dùng upgrade như thời điểm “dọn luôn mọi thứ”.

## 17. Framework major upgrade là một workstream riêng

Một framework major thường chứa breaking changes độc lập JDK:

- `javax.*` ↔ `jakarta.*` namespace.
- Annotation và dependency injection changes.
- HTTP request mapping, security defaults, CORS/CSRF.
- Persistence/Hibernate ORM behavior.
- JSON serialization và validation defaults.
- Logging/metrics/health endpoints.
- Message consumer, cache/session serializer.
- Build plugins và dependency BOM.

Trong nhiều hệ sinh thái, framework major mới yêu cầu Java baseline cao hơn; việc tách hoàn toàn có thể không thực hiện được. Tuy nhiên, vẫn nên tách rõ trong kế hoạch: **đâu là thay đổi để JDK chạy được, đâu là thay đổi do framework contract mới**.

### 17.1. Ví dụ javax sang jakarta

Code cũ:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
~~~

Với một provider sử dụng Jakarta Persistence:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
~~~

Đây là thay đổi API namespace của persistence/framework ecosystem. Nó **không tự phát sinh chỉ vì JDK 17/21 được cài**. Nếu JVM migration có thể chạy trên framework cũ vẫn được hỗ trợ, đừng đổi package migration cùng lúc.

Nếu framework target bắt buộc namespace Jakarta và không có bản trung gian, hãy tách các commit/nhóm test nội bộ để ghi rõ tác động: build/runtime, persistence API, ORM mapping và schema/data compatibility.

## 18. Đừng đổi database hoặc message schema trong compatibility phase nếu không bắt buộc

Một deployment JDK mới có thể cùng thời điểm nhóm định đổi:

- Database column type hoặc timezone representation.
- Enum persisted value.
- Session serialization format.
- Cache key namespace.
- Kafka/AMQP event schema.
- HTTP JSON response field names.
- JWT claims/cookie format.

Đây là những hợp đồng giữa phiên bản cũ và mới. Chúng có thể tồn tại lâu hơn process tạo ra chúng.

Ví dụ:

~~~text
App v1 / JDK cũ  -- ghi event schema v1 --> Broker
App v2 / JDK mới -- đọc event schema v1 --> Broker
~~~

Trong compatibility migration, ưu tiên giữ event schema hiện tại, xác nhận app mới đọc được payload cũ, và chỉ thay serializer khi thư viện mới bắt buộc hoặc có migration đã thiết kế.

Nếu phải đổi schema:

1. Định nghĩa schema version.
2. Nâng reader trước writer khi mixed-version deployment cần.
3. Test W1→R2 và W2→R1 khi rollback yêu cầu.
4. Quản lý retention, retries và DLQ.
5. Ghi rõ thời điểm không thể rollback.
6. Tách rollout data contract khỏi việc đổi runtime khi khả thi.

Không xóa cache/session/durable messages đại trà chỉ để ứng dụng mới hết lỗi deserialize.

## 19. Đặt nguyên tắc “behavior-preserving” cho compatibility PR

Một compatibility PR nên có mô tả ngắn nhưng đủ kiểm chứng:

~~~text
Goal:
  Run the existing application on JDK Y.

Required changes:
  - Update Maven/Gradle toolchain to support JDK Y.
  - Replace removed JDK dependencies.
  - Upgrade incompatible bytecode library and Java agent.
  - Adjust JVM flags that no longer apply.

Not in scope:
  - New REST endpoints.
  - Database schema redesign.
  - Rewrite DTOs as records.
  - Replace thread pools with virtual threads.
  - Change JSON/event schema.
  - Major logging/framework refactor.

Expected behavior:
  Existing contracts remain stable.

Validation:
  Build, regression, integration, data compatibility,
  security and rollout/rollback checks.
~~~

Khi reviewer thấy một thay đổi `List.of` hoặc `record` trong PR này, có thể hỏi: nó cần để sửa lỗi nào trên JDK đích? Nếu không có lý do, đưa sang modernization PR.

## 20. Thiết kế PR/commit nhỏ để có thể bisect

Một chuỗi commit khả thi:

| Commit/PR | Nội dung | Trục thay đổi |
|---|---|---|
| 1 | Baseline tests, golden fixtures, CI metadata | Quan sát |
| 2 | Maven/Gradle Wrapper và build plugin hỗ trợ JDK | Build compatibility |
| 3 | Thêm dependency thay JDK module đã bị loại | Compile/runtime compatibility |
| 4 | Nâng thư viện reflection/bytecode/agent bắt buộc | Runtime compatibility |
| 5 | Sửa JVM launch flags, container runtime | Deployment compatibility |
| 6 | Chạy và chứng minh hệ thống trên JDK đích | Release gate |
| 7 | Thay DTO nội bộ bằng record (có test) | Modernization |
| 8 | Switch expressions/pattern matching | Modernization |
| 9 | API/stream refactor có test semantic | Modernization |
| 10 | Thử virtual threads dưới load | Architecture/performance modernization |

Không nhất thiết mỗi hàng là một PR riêng trong mọi hệ thống. Nhưng tách thành nhóm nguyên nhân giúp `git bisect`, code review và revert dễ hơn.

### 20.1. Đừng tối ưu theo số dòng thay đổi

Một PR 20 dòng nhưng thay serializer toàn hệ thống có thể nguy hiểm hơn PR 100 dòng cập nhật các import bị JDK loại. Phân loại theo **tác động hành vi và phạm vi dependency**, không theo kích thước diff.

## 21. Dùng branch và release train để tránh thay đổi đè lên nhau

Trong dự án còn phát triển features:

~~~text
main: feature development
  |
  +-- migration/jdk-compat
  |      |-- build/toolchain
  |      |-- runtime/dependency fixes
  |      +-- compatibility release
  |
  +-- modernization/java-features
         |-- records
         |-- switch/pattern matching
         +-- optional refactors
~~~

Cần điều phối cherry-pick/merge theo lịch phát hành và tránh để hai nhánh thay cùng code mà không có owner. Nếu modernization branch bắt đầu quá sớm, nó có thể khó merge với compatibility patches.

Một cách thường hợp lý là **chốt compatibility baseline trên JDK mới rồi tách các modernization PRs từ baseline đó**. Nếu nhiều team cần làm song song, có thể chuẩn bị đề xuất/PoC nhưng hạn chế merge vào release branch trước khi compatibility gate hoàn thành.

## 22. CI: mỗi giai đoạn kiểm tra điều khác nhau

### 22.1. Compatibility CI

Một pipeline tối thiểu nên có:

- Verify build bằng đúng Maven/Gradle Wrapper.
- Java compiler release target rõ ràng.
- Unit/integration tests.
- Consumer/API contract tests.
- Persistence/cache/message fixtures từ phiên bản cũ.
- Bytecode/dependency compatibility check.
- Security/TLS/keystore smoke tests.
- Launch thử artifact production-like.
- Performance baseline ở các use cases có rủi ro.

Nếu dự án còn hỗ trợ nhiều JDK runtimes, chạy test matrix cho từng version được cam kết. Không mặc định test trên Java 21 đủ chứng minh artifact cũng chạy Java 17.

### 22.2. Modernization CI

Cần thêm kiểm tra cho semantic changes:

- Contract tests trước/sau.
- Unknown/null/edge-case handling.
- Serialization/JSON differences.
- Memory/latency/throttling khi đổi concurrency.
- API public binary compatibility nếu thư viện được tiêu thụ bởi service khác.
- Coverage cho những nhánh đã được đổi sang switch/pattern matching.
- Benchmark có workload thật khi đổi performance design.

Các lỗi từ modernization phải được quy về modernization PR, không làm mất khả năng duy trì JDK compatibility baseline đã xanh.

## 23. Ma trận test hai chiều

Trong khi nâng runtime, có thể xét:

| Ứng dụng/source | Runtime | Mục tiêu |
|---|---|---|
| V1 baseline | JDK cũ | Bằng chứng hiện trạng |
| V1 tương thích (sau sửa bắt buộc) | JDK mới | Chứng minh compatibility |
| V1 tương thích | JDK cũ (nếu còn support) | Chứng minh khả năng chạy hai runtime |
| V2 hiện đại hóa | JDK mới | Kiểm tra thay đổi mới trên baseline ổn định |
| V2 hiện đại hóa | JDK cũ | Chỉ cần nếu V2 vẫn cam kết chạy JDK cũ |

Không nhất thiết có kết quả pass cho mọi ô. Ví dụ code dùng Java 21 virtual threads không thể yêu cầu chạy trên Java 17. Việc cần làm là **công bố thay đổi Java minimum baseline trong modernization release**, không âm thầm coi đó là compatibility regression.

### 23.1. Cần test runtime chứ không chỉ source

Một thư viện có thể compile với Java release thấp nhưng phụ thuộc transitive JAR có classfile target cao. Một service có thể start nhưng chỉ lỗi khi nạp class ở request hiếm. Vì vậy test phải exercise các đường runtime quan trọng.

## 24. Quan sát runtime: không tạo nhầm kết luận về hiệu năng

JDK mới có thể thay GC ergonomics, JIT, container behavior, TLS provider, logging và memory usage. Framework/modernization changes cũng có thể thay performance.

Nếu đổi cùng lúc JDK và concurrency model, khó biết cải thiện hoặc suy giảm đến từ đâu.

So sánh từng mốc:

~~~text
A: App V1 + JDK X
B: App V1-compatible + JDK Y
C: App V2-modernized + JDK Y
~~~

- `A→B` đo tác động của compatibility migration/JDK và các bản vá bắt buộc.
- `B→C` đo tác động của modernization thay đổi source/architecture.

Các số liệu:

- Startup/cold start và warm-up time.
- p50/p95/p99 latency, throughput.
- CPU, heap, GC pause và allocation.
- Thread count/connection pool saturation.
- DB query count và cache hit rate.
- Error rate, timeouts và retries.
- Native memory/OS resource usage.

Dùng cùng workload, dữ liệu và resource limits khi có thể. Không coi một microbenchmark ngắn hoặc chỉ một lần test là bằng chứng hệ thống đã nhanh hơn.

## 25. Security: sửa bắt buộc có thể đổi hành vi có chủ đích

Không phải mọi compatibility change đều nên giữ nguyên hành vi bảo mật của hệ thống cũ. Nếu JDK đích không còn cho phép một thuật toán yếu hoặc một TLS protocol cũ, việc mở lại thuật toán đó để “giữ nguyên behavior” có thể trái chính sách.

Cách làm:

1. Xác định thay đổi của JDK/security provider.
2. Kiểm tra hệ thống đối tác và các certificate/keystores hiện tại.
3. Chọn cấu hình/thuật toán được hỗ trợ và đạt policy.
4. Test TLS handshake, signing/verification hoặc crypto operation.
5. Ghi rõ giao thức/consumer cũ nào bị ảnh hưởng.
6. Chuẩn bị migration cho đối tác trước rollout.
7. Không bỏ qua certificate validation hoặc mở rộng `--add-opens` để che lỗi sai lớp.

Điều này thuộc **compatibility/security workstream**, nhưng có thể là một breaking change được phê duyệt. Hãy mô tả rõ thay vì gọi là refactor tùy chọn.

## 26. API mới không phải lựa chọn duy nhất để sửa deprecated code

Deprecated API không đồng nghĩa API đã bị loại khỏi runtime. Khi JDK mới vẫn hỗ trợ một API nhưng có replacement được đề xuất, nhóm cần cân nhắc:

- API cũ có còn được hỗ trợ đủ cho thời gian migration không?
- Có cảnh báo hoặc rủi ro bảo mật cụ thể không?
- Replacement có thay semantic hoặc format dữ liệu không?
- Có test chứng minh hành vi tương đương không?
- Có consumer JDK cũ cần tiếp tục chạy không?

Nếu replacement bắt buộc do removal hoặc policy, nó thuộc compatibility. Nếu chỉ để code hiện đại, hãy lên modernization backlog.

**Ví dụ:** chuyển từ `java.util.Date` sang `java.time` có thể là cải tiến rất tốt, nhưng cũng có rủi ro timezone, serialization và persistence schema. Đừng tự động chuyển mọi thời gian trong hệ thống chỉ vì nâng JDK.

## 27. Public libraries cần API và binary compatibility riêng

Với một ứng dụng nội bộ một process, đổi method signature có thể được phát hiện trong cùng build. Với library đã phát hành cho consumers khác, đổi source API trong modernization release có thể gây lỗi runtime dù artifact chính build xanh.

Ví dụ class cũ:

~~~java
public final class CustomerDto {
    public String getId() {
        return id;
    }
}
~~~

Nếu thay bằng record:

~~~java
public record CustomerDto(String id) {}
~~~

client đã biên dịch để gọi `getId()` có thể gặp `NoSuchMethodError` nếu không còn method đó, ngay cả khi JSON output tương tự. Ngoài ra, constructors, reflection và Java serialization form có thể đổi.

Cần đánh giá:

- Source compatibility: consumer cũ biên dịch lại được không?
- Binary compatibility: class/method descriptor cũ còn không?
- Serialization compatibility: payload cũ có đọc được không?
- Runtime compatibility: Java minimum release và dependency versions?
- Semantic compatibility: kết quả và side effects có còn đúng?

Nếu modernization làm breaking API, tăng version và triển khai deprecation/adapter theo chính sách library. Không gộp vào PR “support JDK 21”.

## 28. Khi nào có thể dùng tính năng mới ngay trong migration?

Có một số ngoại lệ hợp lý:

### 28.1. API mới là cách hỗ trợ chính thức duy nhất

Nếu API cũ đã bị loại bỏ và JDK đích cung cấp một public API thay thế phù hợp, việc chuyển sang API mới **có thể là sửa tương thích bắt buộc**. Cần giữ behavior hoặc ghi rõ các thay đổi không tránh được.

### 28.2. Framework mới yêu cầu Java baseline cao hơn

Nếu framework major target yêu cầu Java 17 và không có phiên bản trung gian hợp lệ, việc dùng import/API khác có thể là một phần mandatory framework migration. Tuy vậy không có lý do tự động rewrite business models sang records hoặc thêm virtual threads.

### 28.3. Security yêu cầu loại bỏ cách làm cũ

Khi cách dùng API cũ tạo rủi ro bảo mật thực tế, patch có thể cần đổi logic. Đây là thay đổi có chủ đích, phải có security review và regression test, không che nó dưới nhãn “code cleanup”.

### 28.4. Cần tạo một lớp compatibility adapter

Ví dụ facade nội bộ giữ public API cũ và bên trong gọi API mới:

~~~java
public final class LegacyFileReader {
    public static byte[] readBytes(Path path) throws IOException {
        return Files.readAllBytes(path);
    }
}
~~~

Adapter làm giảm phạm vi thay đổi ở consumer, nhưng phải đánh giá semantics, error mapping và Java release target. Dùng facade khi nó thực sự đơn giản hóa migration, không để tạo thêm tầng trừu tượng vô nghĩa.

## 29. Quy trình review: câu hỏi cho từng dòng thay đổi

Trong compatibility PR, reviewer có thể hỏi:

1. Lỗi cụ thể trên JDK target là gì?
2. Có log/test/stack trace hoặc support matrix xác nhận nguyên nhân không?
3. Thay đổi này có cần để giải quyết lỗi đó không?
4. Có làm public API/schema/format/behavior thay đổi không?
5. Nếu behavior thay đổi, đã được phê duyệt và test chưa?
6. Có phương án nhỏ hơn ít rủi ro hơn không?
7. Dependency/version được chọn có hỗ trợ cả môi trường hiện tại và target không?
8. Có ảnh hưởng rollback và mixed-version deployment không?
9. Có thể tách phần cleanup tùy chọn thành PR sau không?
10. Test nào chứng minh lỗi được sửa mà không tạo regression?

Trong modernization PR, câu hỏi khác:

- Lợi ích là readability, maintainability, performance hay giảm rủi ro?
- New Java minimum release có thay đổi không?
- Semantic differences của API/cú pháp mới đã được nhận diện chưa?
- Có tác động tới framework serializer, ORM hoặc reflection không?
- Có so sánh performance với compatibility baseline chưa?
- Có test bảo vệ public contracts/edge cases không?

## 30. Tránh “shotgun modernization” từ IDE

IDE có thể đề xuất nhiều automatic conversions:

- For-loop → streams.
- Anonymous class → lambda.
- Switch statement → switch expression.
- Class DTO → record.
- `Arrays.asList` → `List.of`.
- `StringBuilder`/concatenation → text blocks.
- Thread pool → virtual-thread executor.

Một thao tác áp dụng cho toàn bộ repository có thể tạo diff rất lớn và thay semantic ở các điểm ít được test. Trong compatibility phase, chỉ dùng automated rewrite khi có **mục tiêu bắt buộc được định nghĩa hẹp** và có validation phù hợp.

Ngay cả khi tool đảm bảo syntactic validity, nó không thể tự chứng minh mọi kết quả nghiệp vụ và giao thức vẫn giống trước. Với Java migration, ưu tiên transformations được giới hạn theo module, có thể rollback và được test.

## 31. Kiểm soát thay đổi cấu hình và packaging

Không chỉ code Java mới cần tách phạm vi. JVM options, container base image, Maven/Gradle Wrapper, startup scripts, Java agents và classpath thường phải đổi.

Một PR compatibility có thể cần:

~~~text
Dockerfile:
  Chuyển runtime base image sang JDK đã phê duyệt.

gradle-wrapper.properties:
  Nâng Gradle distribution để hỗ trợ JVM build.

build.gradle:
  Cập nhật Java toolchain/release.

start.sh:
  Loại JVM flag không được hỗ trợ; đặt options đúng vị trí.

dependencies:
  Nâng bytecode library và JDBC driver bắt buộc.
~~~

Không dùng cơ hội đó để thay luôn logging framework, package layout, deployment architecture hoặc format config nếu không cần.

### 31.1. Giữ đúng thứ tự JVM options

~~~bash
java -Xmx1g -Dapp.env=production -jar app.jar --mode=worker
~~~

Trong đó JVM options đứng trước `-jar`. Nếu đặt `-Xmx1g` sau JAR, nó có thể trở thành application argument. Một lỗi launcher như vậy không được giải quyết bằng cách rewrite Java source sang API mới.

## 32. Dữ liệu tồn tại qua triển khai là ranh giới quan trọng

Dù compatibility source đã hoàn tất, các trạng thái cũ vẫn tồn tại:

- Java serialized objects trong Redis/cache.
- HTTP sessions và authentication tokens.
- Kafka/AMQP messages, delayed retries và DLQ.
- Database rows dùng enum/timezone/UUID representation cũ.
- Outbox/inbox/deduplication records.
- Keystore/truststore và encrypted files.
- Backup/snapshot có thể restore sau nhiều tháng.

Nếu modernization thay class name, record shape, JSON serializer, enum representation hoặc object schema, reader mới có thể không đọc được dữ liệu cũ. Một thay đổi syntax bình thường như `List.of` ít rủi ro hơn những thay đổi cấu trúc public DTO nhưng vẫn cần xét null/mutability.

Trong chương trình nâng Java, nên đặt **data compatibility tests** ngay từ compatibility phase rồi tiếp tục sử dụng chúng để bảo vệ modernization changes.

## 33. Ví dụ dự án: Java 8 service nâng lên Java 21

Giả sử một order service có:

~~~text
JDK 8
Maven cũ
Spring/framework version cũ
JAXB dùng qua API từng có sẵn trong JDK
Java agent cũ
PostgreSQL JDBC driver cũ
REST API + Kafka + Redis sessions
~~~

Mục tiêu là đưa production sang JDK 21, sau đó cải thiện code readability và concurrency.

### Giai đoạn 0 — Baseline

- Lưu commit/build artifact đang chạy.
- Ghi API/event/session fixtures.
- Thu dependency tree, JDK/agent versions.
- Chạy regression và integration tests.
- Ghi startup, GC, latency và error rate.
- Xác nhận support matrix framework/JDK.

### Giai đoạn 1 — Build compatibility

- Nâng Maven Wrapper/Compiler/Surefire plugins khi bắt buộc.
- Chọn JDK build và compiler release rõ ràng.
- Thêm dependency cho API không còn đi kèm JDK, ví dụ JAXB phù hợp.
- Sửa annotation processors/bytecode tooling không tương thích.
- Giữ REST/message/database contracts.

### Giai đoạn 2 — Runtime compatibility

- Cập nhật Java agent, JDBC driver và JVM flags cần thiết.
- Chạy application artifact trên JDK 21.
- Test TLS, database, Kafka, Redis, session và serializer cũ.
- Kiểm tra classloading, reflection và log.
- Chạy canary nếu framework/version support cho phép.

### Giai đoạn 3 — Compatibility release

- Triển khai JDK mới với business behavior không đổi ngoài sửa bắt buộc.
- So production metrics với baseline.
- Có điểm rollback cụ thể.
- Xác nhận errors, user sessions và backlog ổn định.
- Lưu manifest artifact/JDK/dependency versions.

### Giai đoạn 4 — Modernization sau khi ổn định

- Chọn một internal DTO ít phụ thuộc external contract để thử record.
- Chuyển một số switch statements sang switch expressions có branch tests.
- Cân nhắc API file/string mới nơi semantics phù hợp.
- Thử virtual threads cho I/O-heavy workload trong nhánh thí nghiệm.
- Đánh giá hiệu năng/observability trước khi đưa vào production.

### Bảng theo dõi

| Release | JDK | Source style | API/data contract | Mục tiêu |
|---|---|---|---|---|
| R0 | 8 | Legacy | V1 | Baseline |
| R1 | 21 | Chủ yếu legacy, chỉ sửa bắt buộc | V1 | Compatibility |
| R2 | 21 | Một số records/switch/modern APIs | V1 nếu có thể | Modernization |
| R3 | 21 | Thay concurrency/architecture có kiểm thử | V1 hoặc version mới rõ ràng | Optimization |

Bảng không khẳng định framework cũ nào cũng chạy trên Java 21. Nếu framework buộc nâng major, ghi thành một phần bắt buộc của R1 hoặc thêm release cầu nối hợp lệ.

## 34. Rollback phải được định nghĩa theo từng loại thay đổi

### 34.1. Rollback compatibility

Nếu chỉ đổi JDK/runtime và giữ persisted format, rollback thường có thể quay về artifact/runtime trước đó nếu classfile target và dữ liệu vẫn tương thích. Tuy nhiên:

- JDK mới có thể ghi keystore hoặc file theo thuật toán khác mà JDK cũ không đọc được.
- Container và native dependencies có thể đã thay.
- Certificate/trust policy có thể làm phía đối tác thay cấu hình.
- Runtime mới có thể phát message hoặc dữ liệu không đúng nếu một library bắt buộc đã đổi behavior.

Vì vậy phải thử rollback trong môi trường mô phỏng trạng thái sau deploy, không chỉ kiểm tra image cũ khởi động được.

### 34.2. Rollback modernization

Một refactor record có thể thay binary API; một đổi JSON serializer có thể ghi payload mới; một concurrency change có thể làm số request đồng thời tăng. Rollback phải xem xét data compatibility, cache/session, messages và side effects.

Nếu modernization đã tạo dữ liệu mà compatibility release không đọc được, khả năng rollback sẽ bị thu hẹp. Nên thiết kế reader tương thích hoặc tách contract migration có cửa sổ chuyển đổi.

## 35. Khi nào có thể loại bỏ code legacy?

Một lỗi thường gặp là cố xóa toàn bộ legacy adapters ngay sau khi JDK mới đã rollout. Nhưng có thể còn:

- Consumer đang dùng library cũ.
- Data format v1 trong database/cache.
- Events nằm trong DLQ hoặc archive.
- Máy khách dùng Java baseline cũ.
- Scheduled jobs chạy ít khi.
- Backup có thể restore class/serialization cũ.

Chỉ xóa compatibility code khi đã có bằng chứng các nguồn dữ liệu/consumer đó hết vòng đời hoặc đã được nâng. Xóa adapter là một **contract change**, không chỉ cleanup.

### 35.1. Dấu hiệu “đã sẵn sàng” để hiện đại hóa

- Application chính đã chạy ổn trên JDK target.
- Build/test CI và production deployment đã xác định đúng toolchain.
- Các integration quan trọng đã pass.
- Monitoring, log và rollback đã sẵn sàng.
- Không còn lỗi JVM/provider/agent bắt buộc chưa xử lý.
- Có baseline hiệu năng trên JDK mới.
- Team có thể dành review/test capacity cho modernization.

Không nhất thiết phải chờ mọi module trong toàn tổ chức hoàn tất nếu modernization có phạm vi độc lập, nhưng phải kiểm soát API/data contracts dùng chung.

## 36. Bảng nhận diện anti-patterns

| Anti-pattern | Vì sao rủi ro | Cách thay thế |
|---|---|---|
| Nâng JDK và rewrite lớn một PR | Khó quy nguyên nhân, khó revert | Tách compatibility và modernization |
| Đổi framework major chỉ để có syntax mới | Thêm nhiều breaking changes không liên quan | Kiểm tra support matrix, nâng có chủ đích |
| “Compile xanh là xong” | Runtime/integration/data vẫn có thể lỗi | Test production-like và legacy fixtures |
| Sửa mọi deprecated API ngay | Có thể đổi semantics không cần thiết | Ưu tiên API bị loại/bắt buộc |
| Convert mọi DTO thành record | Có thể phá getters, ORM, serialization | Chọn DTO phù hợp, test contract |
| Convert mọi collection sang `List.of` | Null/mutability semantics khác | Đánh giá từng use case |
| Thay mọi executor bằng virtual threads | Backpressure và tài nguyên downstream khác | Pilot riêng, load test |
| Cập nhật tất cả dependencies lên latest | Transitive BOM và API thay hàng loạt | Chỉ nâng bắt buộc rồi tách maintenance |
| Thêm `--add-opens` khắp launcher | Che dependency cũ và nới encapsulation | Nâng library/agent, giới hạn workaround |
| Xóa cache/session khi lỗi parse | Có thể logout, mất idempotency | Versioned schema, compatible reader |
| Dùng `--release` làm bằng chứng runtime | Dependencies/runtime vẫn có vấn đề | Chạy test trên JVM thực |
| Rollback chỉ là `git revert` | Data/messaging có thể không đọc ngược | Xây data-aware rollback plan |

## 37. Checklist cho một compatibility phase rõ ràng

- [ ] Đã định nghĩa JDK target, vendor/update và runtime cần hỗ trợ.
- [ ] Đã lập ma trận JDK/framework/build tool phù hợp.
- [ ] Đã chốt baseline source/artifact/dependency versions.
- [ ] Đã phân biệt compile JDK, toolchain, `--release` và runtime JDK.
- [ ] Đã có characterization/regression/contract fixtures.
- [ ] Đã phân loại thay đổi bắt buộc, bảo mật và hiện đại hóa tùy chọn.
- [ ] Đã nâng build plugins, agent, bytecode/driver dependencies bắt buộc.
- [ ] Đã xử lý API JDK bị loại hoặc internal reflection có nguyên nhân rõ.
- [ ] Đã tránh thêm Java features mới nếu không phục vụ compatibility.
- [ ] Đã giữ REST, message, DB, cache/session schemas ổn định khi có thể.
- [ ] Đã ghi mọi thay đổi behavior bắt buộc và phê duyệt tác động.
- [ ] Đã chạy integration tests trên JDK target với dữ liệu lịch sử.
- [ ] Đã đo GC, TLS, startup, latency, memory và errors.
- [ ] Đã kiểm tra launcher, container runtime và JVM flags.
- [ ] Đã chuẩn bị artifact/runtime/data rollback phù hợp.
- [ ] Đã xác nhận release compatibility ổn định trước khi áp dụng modernization lớn.

## 38. Checklist cho modernization phase

- [ ] Mỗi đề xuất có lợi ích và phạm vi rõ ràng.
- [ ] Đã xác định Java language/API minimum baseline mới nếu có.
- [ ] Đã đánh giá semantic differences của API thay thế.
- [ ] Đã kiểm tra serialization, JSON, ORM, reflection và public API contracts.
- [ ] Đã chia nhỏ records/switch/pattern matching/text blocks thành changes review được.
- [ ] Đã tránh refactor hàng loạt không có coverage.
- [ ] Đã benchmark nếu thay concurrency/streaming/data access model.
- [ ] Đã xác nhận consumers trên JDK cũ không còn phụ thuộc binary API mới.
- [ ] Đã chạy mixed-version hoặc backward-read tests nếu cần.
- [ ] Đã ghi rõ rollback và dữ liệu do version mới có thể tạo.
- [ ] Đã giữ riêng lỗi modernization với lỗi JDK compatibility.
- [ ] Đã có đường dọn legacy adapters dựa trên bằng chứng, không chỉ thời gian deploy.

## 39. Kết luận

**Sửa tương thích** và **áp dụng cú pháp hoặc API Java mới** là hai mục tiêu liên quan nhưng khác bản chất. Sửa tương thích nhằm giúp **hành vi và hợp đồng hệ thống đang tồn tại tiếp tục hoạt động trên JDK mục tiêu**. Hiện đại hóa nhằm làm code dễ bảo trì, dễ hiểu, an toàn hoặc hiệu quả hơn bằng những khả năng mới của Java, và vì vậy có thể đi kèm semantic hoặc minimum-runtime changes.

Khi support matrix cho phép, hãy:

1. Chốt baseline và test hành vi cũ.
2. Sửa build/runtime/dependency/API bắt buộc để chạy trên JDK mới.
3. Kiểm chứng integration, dữ liệu cũ, bảo mật và performance.
4. Phát hành một compatibility baseline ổn định.
5. Sau đó mới triển khai records, switch expressions, APIs mới, concurrency redesign hoặc các refactor lớn theo từng đợt.

Nếu framework/JDK bắt buộc nâng phối hợp, vẫn phân tách **nhóm nguyên nhân, review và acceptance criteria** để tránh đẩy thêm thay đổi tùy chọn vào một lần nâng vốn đã rủi ro.

Nguyên tắc thực hành quan trọng nhất là: **đầu tiên chứng minh hệ thống vẫn làm đúng việc cũ trên nền Java mới; sau đó mới chủ động làm theo cách mới**. Đây là cách giảm rủi ro, giúp debug và rollback đơn giản hơn, đồng thời tạo một nền tảng đáng tin cậy cho quá trình hiện đại hóa Java lâu dài.
