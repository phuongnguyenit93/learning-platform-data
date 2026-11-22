# Kiểm thử khám phá qua JAR để phát hiện thiếu hoặc sai tệp imports

## 1. Mục tiêu: kiểm tra artifact mà ứng dụng thực sự sử dụng

Một auto-configuration có thể hoạt động hoàn hảo trong unit test nhưng không chạy khi người dùng thêm starter vào ứng dụng. Nguyên nhân thường nằm ở khâu đóng gói hoặc discovery:

- File `AutoConfiguration.imports` bị thiếu khỏi JAR.
- File được đặt sai thư mục hoặc sai chữ hoa/thường.
- Dòng trong file ghi sai fully qualified class name (FQCN).
- Class đã đổi package/tên nhưng imports resource chưa cập nhật.
- Resource filtering, shading hoặc quá trình đóng gói làm mất/ghi đè nội dung.
- Test chỉ import class trực tiếp nên không kiểm tra cơ chế discovery của Spring Boot.

Bài này tập trung vào kiểm chứng ở **ranh giới artifact**: build thư viện, cài/publish JAR, rồi chạy một project consumer độc lập chỉ phụ thuộc artifact đó. Test consumer vừa kiểm tra resource nằm trong đúng JAR, vừa khởi động Spring Boot để chứng minh auto-configuration được phát hiện qua imports file.

Phạm vi ví dụ: Spring Boot 3.3.x, Java 17+, Maven và JUnit 5. Các ví dụ dùng thư viện giả định `acme-audit` để có thể thay bằng artifact thật.

## 2. Cơ chế discovery của Spring Boot 3.x

Trong Spring Boot 3.x, auto-configuration được khai báo trong resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Spring Boot tìm resource này trên classpath, kể cả bên trong các JAR dependency đã publish. Mỗi dòng chứa **một tên class auto-configuration đầy đủ**:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
com.acme.audit.autoconfigure.AuditWebAutoConfiguration
```

Có thể thêm comment bắt đầu bằng `#` và dòng trống. Tên class phải đúng package, đúng chữ hoa/thường và đúng tên class.

Ví dụ resource trong module `acme-audit-spring-boot-autoconfigure`:

```text
src/main/resources/
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung file:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
```

### 2.1. Vì sao test import trực tiếp chưa đủ?

Một unit test thường viết:

```java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(AuditAutoConfiguration.class))
        .run(context -> {
            // Assert bean ở đây.
        });
```

Test này hữu ích để kiểm tra condition, properties, bean creation và back-off. Nhưng nó **đưa class vào context trực tiếp qua code test**. Vì vậy, test vẫn có thể pass dù JAR không chứa file imports, file đặt sai đường dẫn hoặc dòng class name bị typo.

Đây là hai câu hỏi khác nhau:

| Loại test | Kiểm tra điều gì? | Có kiểm tra imports resource không? |
| --- | --- | :---: |
| `ApplicationContextRunner` + `AutoConfigurations.of(...)` | Logic bên trong auto-configuration | Không |
| Đọc trực tiếp resource trong JAR | Đường dẫn và class name đã được đóng gói | Có |
| Consumer dùng `@EnableAutoConfiguration` / `@SpringBootTest` | Boot có thật sự discover và áp dụng auto-configuration từ classpath không | Có, theo luồng runtime |
| Chỉ dùng `@Import(AuditAutoConfiguration.class)` | Import class theo yêu cầu của test/app | Không chứng minh discovery |

Một bộ kiểm thử starter nên giữ cả unit test condition lẫn consumer integration test. Unit test nhanh và khoanh vùng lỗi; consumer test xác nhận artifact hoàn chỉnh.

### 2.2. Không dựa vào component scanning để nạp auto-configuration

Auto-configuration phải được nạp bằng imports resource. Đặt class trong package mà `@SpringBootApplication` quét có thể khiến test vẫn tìm thấy class dù imports file bị thiếu.

Để test discovery có ý nghĩa:

- Đặt class auto-configuration trong package riêng của thư viện.
- Không khai báo `@ComponentScan` rộng để quét package đó.
- Trong consumer smoke test, dùng `@SpringBootConfiguration` và `@EnableAutoConfiguration` mà không thêm `@ComponentScan`.
- Không dùng `@Import` trực tiếp class auto-configuration trong test discovery.

Spring Boot khuyến nghị auto-configuration nằm trong package riêng, không phải mục tiêu của component scanning và không tự bật component scanning để tìm thêm component. Hãy dùng `@Import` cụ thể cho các configuration phụ thuộc.

### 2.3. Nested auto-configuration class

Nếu imports file cần tham chiếu một auto-configuration nested (không phải top-level), tên class dùng dấu `$`:

```text
com.acme.OuterAutoConfiguration$NestedAutoConfiguration
```

Không ghi dấu chấm thay cho `$`. Nếu có thể, ưu tiên khai báo auto-configuration top-level để resource dễ đọc và refactor ít rủi ro hơn.

## 3. Dựng thư viện mẫu

Ta tạo hai artifact theo cách tổ chức starter thông thường:

```text
acme-audit/
├── acme-audit-spring-boot-autoconfigure/
│   └── src/main/
│       ├── java/com/acme/audit/
│       │   ├── AuditMarker.java
│       │   └── autoconfigure/AuditAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-audit-spring-boot-starter/
    └── pom.xml
```

Module autoconfigure chứa class và imports resource. Starter chỉ gom dependency đến module autoconfigure và các dependency cần thiết cho trải nghiệm mặc định.

### 3.1. Bean đánh dấu để test

File `AuditMarker.java`:

```java
package com.acme.audit;

public record AuditMarker(String origin) {
}
```

Đây là bean đơn giản, không kết nối mạng, database hoặc hệ thống ngoài. Test có thể xác nhận auto-configuration được áp dụng bằng cách kiểm tra bean này.

### 3.2. Auto-configuration

File `AuditAutoConfiguration.java`:

```java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditMarker;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true")
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public AuditMarker auditMarker() {
        return new AuditMarker("auto-configuration");
    }
}
```

Điều kiện `acme.audit.enabled=true` giúp test kiểm soát rõ thời điểm bean phải xuất hiện. `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp bean riêng để thay thế default.

Class này cần nằm trong module autoconfigure, có dependency compile tới `spring-boot-autoconfigure` và class `AuditMarker`.

### 3.3. Imports resource

Tạo đúng file:

```text
acme-audit-spring-boot-autoconfigure/
└── src/main/resources/META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
```

Không thêm dấu nháy, dấu phẩy hoặc annotation vào dòng class name. Không đặt file tại `META-INF/spring.factories` để đăng ký auto-configuration theo cơ chế cũ của Boot 2.x. Với Spring Boot 3.x, dùng imports resource chuyên biệt này.

### 3.4. POM tối thiểu của autoconfigure

Ví dụ dependency cần thiết:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>
</dependencies>
```

Version Spring Boot nên được quản lý bởi parent hoặc `spring-boot-dependencies` BOM ở project. Không hard-code version khác nhau cho `spring-boot-autoconfigure` và `spring-boot-test`.

### 3.5. POM tối thiểu của starter

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-audit-spring-boot-autoconfigure</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </dependency>
</dependencies>
```

Starter không cần tự chứa lại class auto-configuration. Nó kéo module autoconfigure như dependency thường để resource được phân phối trong artifact đó.

## 4. Tạo consumer integration test độc lập

Đây là bước quan trọng nhất. Consumer phải resolve **JAR đã cài/publish**, không dùng class output của module autoconfigure trong cùng Maven reactor.

Cấu trúc project:

```text
consumer-it/
├── pom.xml
└── src/test/java/example/consumer/
    ├── ConsumerApplication.java
    └── StarterJarDiscoveryTest.java
```

Project này nằm ngoài reactor build của thư viện hoặc được chạy bằng một Maven invocation riêng sau khi thư viện đã cài vào local repository.

### 4.1. POM consumer

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example.consumer</groupId>
    <artifactId>acme-audit-consumer-it</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-audit-spring-boot-starter</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Dependency starter sẽ kéo module autoconfigure vào runtime classpath. Test không cần khai báo trực tiếp auto-configuration class như một import.

### 4.2. Consumer application không component-scan thư viện

File `ConsumerApplication.java`:

```java
package example.consumer;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;

@SpringBootConfiguration
@EnableAutoConfiguration
public class ConsumerApplication {
}
```

Không thêm `@ComponentScan` hoặc `@Import(AuditAutoConfiguration.class)`. Như vậy, khi bean `AuditMarker` xuất hiện, test có thể truy nguyên nó qua luồng auto-configuration discovery của Boot.

Nếu dùng `@SpringBootApplication`, annotation đó bao gồm component scanning. Khi ấy phải bảo đảm package scan không vô tình quét package auto-configuration của thư viện, nếu không test có thể pass vì một đường nạp khác.

## 5. Test: xác minh resource và discovery từ JAR

Test này lấy vị trí JAR chứa class `AuditAutoConfiguration`, mở JAR và kiểm tra:

1. Artifact thật sự là một file JAR, không phải thư mục `target/classes`.
2. Resource nằm đúng đường dẫn `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
3. Nội dung resource có chính xác FQCN của `AuditAutoConfiguration`.
4. Spring Boot tạo được bean khi consumer bật property.

File `StarterJarDiscoveryTest.java`:

```java
package example.consumer;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

import com.acme.audit.AuditMarker;
import com.acme.audit.autoconfigure.AuditAutoConfiguration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ConsumerApplication.class,
        properties = "acme.audit.enabled=true")
class StarterJarDiscoveryTest {

    private static final String IMPORTS_PATH =
            "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

    @Autowired
    private ApplicationContext context;

    @Test
    void autoConfigurationImportsFileIsPackagedInItsJar()
            throws Exception {

        var codeSource =
                AuditAutoConfiguration.class
                        .getProtectionDomain()
                        .getCodeSource();

        assertThat(codeSource)
                .as("Auto-configuration class must come from a dependency artifact")
                .isNotNull();

        URL location = codeSource.getLocation();
        Path jarPath = Path.of(location.toURI());

        assertThat(Files.isRegularFile(jarPath))
                .as("Expected a packaged JAR, not target/classes: " + jarPath)
                .isTrue();

        assertThat(jarPath.getFileName().toString())
                .endsWith(".jar");

        try (JarFile jar = new JarFile(jarPath.toFile())) {
            JarEntry imports = jar.getJarEntry(IMPORTS_PATH);

            assertThat(imports)
                    .as("Imports resource must be inside the autoconfigure JAR")
                    .isNotNull();

            List<String> classNames;

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                            jar.getInputStream(imports),
                            StandardCharsets.UTF_8))) {

                classNames = reader.lines()
                        .map(String::trim)
                        .filter(line -> !line.isEmpty())
                        .filter(line -> !line.startsWith("#"))
                        .toList();
            }

            assertThat(classNames)
                    .contains(AuditAutoConfiguration.class.getName());
        }
    }

    @Test
    void bootDiscoversAutoConfigurationFromTheConsumerClasspath() {
        assertThat(context.getBeansOfType(AuditMarker.class))
                .hasSize(1);

        assertThat(context.getBean(AuditMarker.class).origin())
                .isEqualTo("auto-configuration");
    }
}
```

Đây là test chạy trong project consumer. Nó không gọi `AutoConfigurations.of(...)`. `@SpringBootTest` tạo context bằng `SpringApplication`, còn `@EnableAutoConfiguration` kích hoạt cơ chế tìm imports resource trên classpath.

Test resource kiểm tra đúng artifact chứa class auto-configuration. Nếu project consumer vô tình resolve module source/classes thay vì JAR, assertion `Files.isRegularFile` sẽ thất bại và báo đúng vấn đề của test setup.

### 5.1. Vì sao cần cả hai assertion?

| Kiểm tra | Lỗi được phát hiện |
| --- | --- |
| Đọc JAR và kiểm tra imports resource | File thiếu, sai path, sai FQCN hoặc class đến từ thư mục build thay vì JAR |
| Khởi động context và kiểm tra `AuditMarker` | Boot không discover/apply được auto-configuration hoặc condition/bean behavior sai |

Kiểm tra resource trả lời “file có trong artifact và có đúng dòng không?”. Kiểm tra context trả lời “Boot có thật sự sử dụng artifact đó không?”. Cả hai cùng pass là bằng chứng mạnh hơn việc chỉ đọc resource hoặc chỉ assert bean.

## 6. Build theo đúng thứ tự để test không vô tình dùng target/classes

Với Maven multi-module, nếu consumer integration test nằm trong cùng reactor, Maven có thể giải quyết dependency module bằng output của module đang build. Khi đó code source có thể trỏ tới thư mục class đã compile thay vì JAR đã đóng gói.

Cách đơn giản, dễ kiểm soát:

1. Build và cài thư viện vào local Maven repository.
2. Chạy consumer project bằng Maven invocation riêng.
3. Consumer dependency dùng đúng GAV/version đã cài.
4. Test xác nhận code source là file JAR.

Ví dụ:

```bash
mvn -f acme-audit/pom.xml clean install
```

Sau khi lệnh hoàn tất:

```bash
mvn -f consumer-it/pom.xml clean verify
```

Nếu library parent có nhiều module, `clean install` phải build cả autoconfigure lẫn starter theo reactor order. Không bỏ qua bước install nếu consumer đang dùng version snapshot mới vừa thay đổi.

Với CI, có thể dùng hai job hoặc hai stage:

- Stage 1: build/test/install hoặc publish artifact.
- Stage 2: tạo consumer workspace sạch, resolve artifact từ repository, chạy integration test.

Nếu dùng remote repository, consumer phải resolve đúng version vừa publish; có thể dùng version build duy nhất để tránh cache snapshot cũ.

### 6.1. Maven command hữu ích

Xác nhận dependency được resolve từ tọa độ mong đợi:

```bash
mvn -f consumer-it/pom.xml dependency:tree -Dincludes=com.acme
```

Kiểm tra dependency cụ thể:

```bash
mvn -f consumer-it/pom.xml dependency:tree -Dincludes=com.acme:acme-audit-spring-boot-autoconfigure
```

Nếu output cho thấy dependency đến từ version cũ hoặc profile khác, sửa consumer dependency/repository trước khi kết luận imports file có vấn đề.

## 7. Kiểm tra JAR thủ công khi test thất bại

Test tự động là hàng rào chính. Khi test fail, kiểm tra artifact bằng JDK tool để xác định lỗi đóng gói.

### 7.1. Xem JAR có resource không

```bash
jar tf acme-audit-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar
```

Lọc riêng imports file trên Linux/macOS:

```bash
jar tf acme-audit-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar | grep AutoConfiguration.imports
```

PowerShell:

```powershell
jar tf acme-audit-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar |
    Select-String "AutoConfiguration.imports"
```

Kết quả phải chứa chính xác:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Chỉ nhìn `target/classes` hoặc source tree chưa đủ. Resource có thể tồn tại trong project nhưng bị loại khỏi JAR bởi cấu hình resources hoặc packaging plugin.

### 7.2. Đọc nội dung resource trong JAR

Nếu có lệnh `unzip`:

```bash
unzip -p acme-audit-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Hoặc giải nén đúng resource vào thư mục tạm:

```bash
jar xf acme-audit-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Sau đó đọc file đã giải nén. Lệnh `jar xf` ghi resource vào working directory hiện tại; nên chạy trong thư mục tạm để tránh ghi đè file cùng tên của project.

Kiểm tra nội dung có dòng:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
```

Không thêm dấu chấm phẩy cuối dòng, dấu nháy hoặc tiền tố `class`. Imports file là danh sách tên class dạng text, một class trên mỗi dòng.

### 7.3. Phân biệt resource source và resource packaged

| Vị trí | Chứng minh điều gì? |
| --- | --- |
| `src/main/resources/META-INF/spring/...` | Developer đã tạo file ở source tree |
| `target/classes/META-INF/spring/...` | Maven đã copy resource vào output directory |
| Bên trong JAR | Artifact phát hành thật sự có resource |
| Consumer classpath + SpringApplication | Boot có thể discover resource từ dependency |

Hai bước cuối mới kiểm chứng được hợp đồng mà người dùng starter nhận.

## 8. Thử nghiệm lỗi có chủ đích để chứng minh test bắt được regression

Một regression test tốt phải thất bại khi imports file bị phá. Có thể thực hiện negative control trong một nhánh làm việc hoặc artifact fixture riêng.

### 8.1. Trường hợp A: xóa hẳn imports resource

Tạm bỏ file khỏi module autoconfigure rồi build lại JAR và cài version test mới.

Kỳ vọng:

- Test đọc JAR thất bại vì `jar.getJarEntry(IMPORTS_PATH)` trả null.
- Consumer context không nhận được `AuditAutoConfiguration` qua auto-configuration discovery.
- Khi `acme.audit.enabled=true`, `AuditMarker` không xuất hiện; test bean discovery thất bại.

Không nên cố định một exception startup cụ thể cho trường hợp thiếu file. Thông thường đây là trường hợp auto-configuration đơn giản không được nạp, nên context vẫn có thể khởi động nhưng bean mong đợi vắng mặt.

### 8.2. Trường hợp B: sai đường dẫn resource

Ví dụ đặt nhầm:

```text
META-INF/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

hoặc:

```text
META-INF/spring/AutoConfiguration.imports
```

Test JAR thất bại vì không tìm thấy entry ở đường dẫn chuẩn. Boot cũng không coi resource ở vị trí khác là danh sách auto-configuration.

### 8.3. Trường hợp C: sai FQCN

Ví dụ resource ghi:

```text
com.acme.audit.autoconfigure.AuditAutoConfig
```

trong khi class thật là `AuditAutoConfiguration`.

Test resource thất bại vì danh sách không chứa `AuditAutoConfiguration.class.getName()`. Khi Boot xử lý entry sai, context có thể fail trong quá trình load configuration class hoặc không đăng ký bean mong đợi, tùy dạng lỗi tên class. Không phụ thuộc vào một exception message cố định; assertion chính xác FQCN đã phát hiện lỗi sớm hơn.

### 8.4. Trường hợp D: class đổi package nhưng resource cũ

Refactor:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
```

thành:

```text
com.acme.audit.boot.AuditAutoConfiguration
```

Nếu quên sửa imports resource, test so sánh với `AuditAutoConfiguration.class.getName()` sẽ thất bại. Đây là lợi ích của việc dùng class literal trong assertion để lấy FQCN mong đợi thay vì copy một chuỗi test độc lập.

### 8.5. Trường hợp E: resource có đúng class nhưng auto-configuration bị loại bởi condition

Lúc này test JAR vẫn pass, vì resource đã đúng. Consumer test có thể không thấy bean vì:

- `@ConditionalOnProperty` không khớp.
- `@ConditionalOnClass` không tìm thấy dependency cần thiết.
- `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` không thỏa.
- Ứng dụng đã cung cấp bean override.
- Auto-configuration bị exclude bởi `spring.autoconfigure.exclude` hoặc `@EnableAutoConfiguration(exclude=...)`.

Đây là lý do cần phân biệt test resource với test context. Nếu resource đúng nhưng bean không xuất hiện, hãy xem condition report và input của consumer trước khi sửa file imports.

## 9. Các lỗi đóng gói thường gặp

### 9.1. Đặt file sai source directory

Maven/Gradle mặc định copy resource từ `src/main/resources`. Nếu đặt file ở `src/test/resources`, file chỉ có trong test classpath, không có trong JAR phát hành.

Đây là lỗi nguy hiểm vì test trong chính module autoconfigure có thể thấy resource test và pass. Consumer project không có resource đó nên auto-configuration biến mất.

### 9.2. Sai chữ hoa/thường

Resource path là tên entry phân biệt chữ hoa/thường trong JAR. Trên Windows filesystem, khác biệt này đôi khi khó nhận ra trong quá trình phát triển. CI chạy Linux có thể bộc lộ lỗi.

Giữ chính xác tên:

```text
AutoConfiguration.imports
```

Không dùng `Autoconfiguration.imports`, `AutoConfigurations.imports` hoặc tên biến thể khác.

### 9.3. Resource filtering làm thay đổi file

Imports file thường chỉ chứa FQCN, nhưng nếu build bật filtering cho mọi resource, ký tự đặc biệt hoặc chuỗi có dạng placeholder có thể bị thay đổi.

Nên cấu hình resource filtering có chủ đích. Với Maven, có thể loại imports resource khỏi filtering nếu project bật filtering toàn cục. Với Gradle, tránh custom task xử lý file như template. Sau build, luôn kiểm tra nội dung bên trong JAR.

### 9.4. Shading/uber-JAR ghi đè resource cùng tên

Nếu đóng gói nhiều dependency vào một uber-JAR bằng shading, nhiều JAR có thể cùng chứa `AutoConfiguration.imports`. Nếu plugin chỉ giữ resource cuối cùng, danh sách của các dependency khác có thể bị mất.

Khi dùng Maven Shade Plugin hoặc công cụ tương đương:

- Cấu hình resource transformer/append phù hợp để **gộp nội dung** các imports resource.
- Không để resource cùng tên bị ghi đè tùy theo thứ tự dependency.
- Sau khi shade, kiểm tra danh sách cuối có đủ class của tất cả artifact cần thiết.
- Chạy consumer smoke test với chính uber-JAR đã tạo.

Nếu ứng dụng dùng executable JAR chuẩn của Spring Boot, dependency thường nằm trong nested JAR; không cần flatten tất cả dependency chỉ để nạp auto-configuration. Tránh tự shade khi không có yêu cầu triển khai cụ thể.

### 9.5. Dùng nhầm spring.factories của Boot 2

Trong Boot 2, auto-configuration thường được đăng ký qua key `EnableAutoConfiguration` trong `META-INF/spring.factories`. Với Boot 3, đăng ký candidate qua `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

Khi nâng cấp thư viện từ Boot 2 lên Boot 3:

- Chuyển danh sách auto-configuration sang imports resource.
- Kiểm tra FQCN đã di chuyển package nếu có.
- Cập nhật test consumer để dùng Boot 3.
- Không xóa các entry `spring.factories` khác vẫn cần cho extension point tương thích riêng; chỉ bỏ cách đăng ký auto-configuration cũ khi không còn target Boot 2.

### 9.6. Resource chỉ có trong starter nhưng không có trong autoconfigure

Boot tìm imports resource trên toàn classpath nên một resource trong starter vẫn có thể liệt kê class từ dependency khác. Tuy nhiên, cấu trúc dễ bảo trì là để file trong module sở hữu auto-configuration.

Khi kiểm thử artifact, kiểm tra đúng JAR chứa class auto-configuration. Điều này giúp phát hiện việc resource bị chuyển nhầm sang starter aggregator hoặc module khác và giữ packaging contract rõ ràng.

## 10. Đọc condition report khi resource đã đúng nhưng bean vẫn vắng

Nếu test JAR pass nhưng consumer context không có bean, bật debug bằng cách cấu hình `debug=true` trong consumer test/application hoặc chạy ứng dụng với tham số `--debug`. Đọc Condition Evaluation Report để phân biệt:

- Auto-configuration có được import và condition nào match/no-match.
- Property hoặc classpath condition có loại cấu hình không.
- Bean condition có back-off vì user bean đã có.
- Auto-configuration bị exclude hay không được chọn.

Nếu có Actuator và expose endpoint phù hợp, `/actuator/conditions` cũng có thể cung cấp report. Không mở endpoint diagnostics công khai chỉ để debug một lỗi packaging.

Nếu source auto-configuration hoàn toàn không xuất hiện trong report, hãy quay lại kiểm tra imports candidate, classpath và exclusion. Nếu source xuất hiện với condition no-match, imports discovery đã đi xa hơn; lúc đó sửa condition input hoặc user configuration.

## 11. Mở rộng cho nhiều auto-configuration

Một imports file có thể liệt kê nhiều class:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
com.acme.audit.autoconfigure.AuditWebAutoConfiguration
com.acme.audit.autoconfigure.AuditMetricsAutoConfiguration
# Reactive integration is loaded from a separate optional artifact
```

Mỗi class có thể có condition riêng. Consumer test nên xác minh các capability mà starter cam kết cung cấp:

| Auto-configuration | Điều kiện ví dụ | Assertion consumer |
| --- | --- | --- |
| `AuditAutoConfiguration` | Core SDK có mặt, feature enabled | Có `AuditMarker` |
| `AuditWebAutoConfiguration` | Servlet web application | Có web adapter |
| `AuditMetricsAutoConfiguration` | Actuator có mặt | Có metrics contributor |
| `AuditReactiveAutoConfiguration` | Reactive context và reactive SDK có mặt | Có reactive adapter |

Không cần một test duy nhất kiểm tra mọi integration. Tách consumer fixture theo optional dependency để tránh kéo tất cả SDK vào một classpath test rồi vô tình che lỗi thiếu dependency.

Nếu có nhiều imports resource từ nhiều artifact, Boot đọc candidate từ resource trên classloader. Vì vậy, đừng giả định chỉ có một file imports duy nhất trong toàn bộ application classpath. Test JAR trực tiếp kiểm tra artifact của bạn; test consumer kiểm tra tập resource tổng thể mà ứng dụng thực sự nhìn thấy.

## 12. CI pipeline khuyến nghị

Một pipeline ngắn nhưng có giá trị:

```text
Compile & unit tests
        |
        v
Package autoconfigure + starter JAR
        |
        v
Inspect JAR entries and imports content
        |
        v
Install/publish artifacts
        |
        v
Build isolated consumer project
        |
        v
SpringApplication discovery smoke test
        |
        v
Dependency and condition diagnostics
```

Các bước cần bảo đảm:

1. Unit test condition chạy trong module autoconfigure.
2. Build tạo JAR thật.
3. Packaging assertion đọc JAR entry và FQCN.
4. Artifact được install/publish với version xác định.
5. Consumer project riêng chỉ phụ thuộc starter đã publish.
6. `@SpringBootTest` xác nhận bean mặc định xuất hiện khi property bật.
7. Có ít nhất một negative control cho resource thiếu hoặc class name sai trong quy trình phát triển/CI fixture.
8. Dependency tree và condition report được lưu khi smoke test thất bại để dễ chẩn đoán.

Có thể giữ một consumer fixture trong repository nhưng chạy nó như build riêng sau khi install artifact. Điều quan trọng là dependency phải được resolve như một người dùng bên ngoài; không để reactor thay bằng output directory.

## 13. Checklist chẩn đoán theo triệu chứng

| Triệu chứng | Kiểm tra đầu tiên | Nguyên nhân thường gặp |
| --- | --- | --- |
| Unit test pass, consumer không có bean | Consumer dùng `@EnableAutoConfiguration` và JAR đã publish chưa? | Unit test import trực tiếp, bỏ qua discovery |
| JAR không có imports resource | `jar tf` và build resource configuration | File đặt sai source path hoặc bị loại khi package |
| Resource có trong JAR nhưng sai nội dung | Đọc entry bằng `unzip -p` hoặc `JarFile` | FQCN typo, class refactor chưa cập nhật, filtering |
| Resource đúng nhưng context không có bean | Condition Evaluation Report | Property/class/bean condition không match |
| Context fail vì class không load được | Imports FQCN và class có trong JAR/dependency không | Entry trỏ tới class không tồn tại hoặc dependency thiếu |
| Test pass trong Windows nhưng fail trên Linux | Kiểm tra chữ hoa/thường của path | Filesystem local che giấu sai tên resource |
| Một số auto-configuration khác biến mất sau shading | So sánh imports trước và sau shade | Resource cùng tên bị overwrite thay vì append |
| Consumer test vô tình pass khi resource thiếu | Kiểm tra component scan và `@Import` | Auto-configuration được nạp bằng đường khác |
| Code source là `target/classes` | Kiểm tra reactor/build invocation | Consumer đang dùng project output, chưa test JAR |
| Test đọc JAR không thấy entry nhưng Boot vẫn discover | Xem resource có nằm trong một dependency JAR khác không | Resource được đặt nhầm artifact nhưng vẫn trên classpath |

## 14. Checklist review trước khi phát hành

- [ ] Auto-configuration class có annotation `@AutoConfiguration`.
- [ ] Imports resource nằm đúng `src/main/resources/META-INF/spring/`.
- [ ] File tên chính xác `org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- [ ] Mỗi dòng là một FQCN hợp lệ, không có dấu nháy/dấu phẩy.
- [ ] Nested class dùng `$` nếu cần.
- [ ] Auto-configuration không phụ thuộc vào component scanning để được nạp.
- [ ] JAR đã đóng gói có resource ở đúng path.
- [ ] Test đọc JAR chứa class để kiểm tra resource và FQCN.
- [ ] Consumer project độc lập dùng starter đã install/publish.
- [ ] Consumer dùng `@EnableAutoConfiguration`, không import class trực tiếp.
- [ ] Consumer test xác nhận bean xuất hiện theo property/condition đã định.
- [ ] Có negative control cho file thiếu, sai path hoặc sai FQCN.
- [ ] Nếu dùng shading, imports resources được append/merge đúng cách.
- [ ] Nếu nâng từ Boot 2, đã chuyển đăng ký auto-configuration sang imports file Boot 3.
- [ ] CI kiểm tra artifact phát hành, không chỉ source tree hoặc `target/classes`.

**Ghi nhớ:** `ApplicationContextRunner` với `AutoConfigurations.of(...)` kiểm tra logic của auto-configuration nhưng bỏ qua imports discovery. Để bắt lỗi thiếu hoặc sai resource, hãy kiểm tra trực tiếp JAR đã đóng gói và chạy một consumer project độc lập qua `@EnableAutoConfiguration`/`SpringApplication`. Test đầu xác minh file và FQCN; test sau xác minh Spring Boot thực sự khám phá và áp dụng cấu hình từ artifact. Đó là bằng chứng mà người dùng starter sẽ trải nghiệm.

## Tài liệu chính thức

- Spring Boot 3.3.13 — Creating Your Own Auto-configuration, locating candidates and imports resource: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 — Testing Auto-configuration with `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 — Testing Spring Boot Applications and `@SpringBootTest`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3.13 API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3.13 API — `AutoConfigurations` test utility: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html
