# Kiểm chứng artifact bằng một dự án tiêu thụ độc lập trong Maven

## 1. Mục tiêu

Một thư viện Java chạy `mvn clean verify` thành công trong repository của chính nó chưa chứng minh người dùng khác có thể tải và sử dụng artifact đó. Unit tests của producer có thể dùng class trực tiếp từ `target/classes`, trong khi một dự án bên ngoài cần **JAR, POM, Maven coordinates, dependencies bắc cầu và tài nguyên đóng gói** đúng.

Cách kiểm chứng thực tế là tạo **independent consumer project** có `pom.xml` riêng, không nằm trong Maven Reactor của producer, không dùng `systemPath`, không truy cập source/target của producer và chỉ nhận thư viện bằng tọa độ:

```xml
<dependency>
    <groupId>lab.release</groupId>
    <artifactId>price-contract</artifactId>
    <version>1.0.0</version>
</dependency>
```

Sau đó:

1. **Local install check:** producer chạy `mvn install` vào một Maven local repository thử nghiệm; consumer độc lập resolve từ đó và chạy tests.
2. **Staged deploy check:** producer deploy JAR và POM lên một repository staging; consumer dùng **local repository sạch khác** để tải artifact và kiểm chứng giống người dùng thật.
3. **Compatibility check:** consumer biên dịch, chạy API, đọc classpath resource, kiểm runtime dependency và xét binary/behavior contract khi chuẩn bị release.

Bài gồm dự án Java 17 với producer dùng Commons Lang và consumer JUnit Jupiter 5. Có các lệnh Bash và Windows PowerShell, expected output, negative tests, CI gate và các tình huống lỗi thường gặp.

**Nguyên tắc:** có file `.jar` không đủ. Một artifact hợp lệ còn cần **POM có metadata đúng, GAV, dependencies, public API, runtime classpath, resource và provenance**.

## 2. Maven install, deploy và consumer resolution

| Hoạt động | Vai trò | Giới hạn |
| --- | --- | --- |
| `mvn test` | Chạy producer unit tests | Chưa tạo và công bố main artifact |
| `mvn verify` | Compile/test/package và các bước được cấu hình tới verify | Chưa install hoặc deploy theo mặc định |
| `mvn install` | Cài main artifact, POM và attached artifacts vào local Maven repository | Không xuất bản cho máy khác |
| `mvn deploy` | Đưa artifacts tới remote repository được cấu hình | Chưa chứng minh consumer resolve/run thành công |
| Consumer `mvn verify` | Resolve producer theo GAV, compile và chạy consumer tests | Phải kiểm cache/repository origin để tránh kết quả giả |

Với thư viện mẫu, tọa độ đầy đủ là:

```text
groupId:    lab.release
artifactId: price-contract
version:    1.0.0
type:       jar
classifier: (không có)
```

Bố cục Maven repository thường có các file:

```text
lab/release/price-contract/1.0.0/
├── price-contract-1.0.0.jar
└── price-contract-1.0.0.pom
```

Đây chỉ là các file chính để minh họa. Repository thật có thể có metadata/checksum/tracking files khác. Không chỉnh sửa trực tiếp cache Maven như một cách “sửa” dependency; nên dùng Maven Resolver và các Maven goals chuẩn.

**Local repository** thường là `~/.m2/repository` nhưng có thể cấu hình qua `settings.xml` hoặc CLI `-Dmaven.repo.local=<path>`. **Remote repository** có thể là HTTPS repository manager hoặc một file-based Maven repository dùng URL `file://`.

Lời gọi `mvn install` từ project chạy các lifecycle phases cần thiết trước đó rồi cài artifact. Goal `install:install-file` dành cho việc cài một file đã tồn tại, thường ngoài Maven build. Nếu nó tạo một POM tối giản không có dependencies, consumer có thể không nhận các thư viện bắc cầu mà producer thực sự cần.

## 3. Consumer độc lập khác gì module chung Reactor?

Khi producer và consumer thuộc cùng một Maven Reactor, Maven có thể resolve producer qua chính reactor project output. Đó là thiết kế tốt cho build đa mô-đun, nhưng **không xác thực rằng một artifact được install/deploy với POM đúng**.

Trong bài, hai dự án chỉ đặt cạnh nhau để dễ thao tác:

```text
artifact-consumer-lab/
├── producer/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/lab/release/contract/PriceText.java
│       │   └── resources/contract/banner.txt
│       └── test/java/lab/release/contract/PriceTextTest.java
└── consumer/
    ├── pom.xml
    └── src/
        ├── main/java/lab/consumer/ConsumerApp.java
        └── test/java/lab/consumer/IndependentConsumerTest.java
```

Không có root aggregator POM. Hai project:

- Không khai báo `<modules>` trỏ tới nhau.
- Consumer không có `<parent>` trỏ producer.
- Consumer không có `systemPath` trỏ sang producer `target`.
- Consumer chỉ khai báo producer bằng Maven GAV.
- Consumer có classpath, Surefire reports và `target` riêng.
- Có thể dùng chung local repository đã install, hoặc dùng staging repo và cache riêng.

**Một thư mục cha chung không tự biến các project thành cùng Maven Reactor.**

## 4. Phiên bản và môi trường thực hành

Ví dụ chọn:

- Java Development Kit 17+; compiler dùng `release=17`.
- Maven 3.9.x hoặc một Maven 3 tương thích các plugin đã chọn.
- Maven Compiler Plugin 3.13.0, Surefire 3.2.5, Resources 3.3.1, JAR 3.4.2.
- Maven Install Plugin 3.1.2 và Deploy Plugin 3.1.2.
- JUnit Jupiter 5.10.2.
- Apache Commons Lang 3.14.0 là **producer compile/runtime dependency**.
- Exec Maven Plugin 3.3.0 cho consumer runtime smoke test.

Các version này phục vụ ví dụ đồng nhất, **không được hiểu là mới nhất hoặc an toàn theo mọi security policy tại thời điểm đọc**. Maven/JDK cần được pin và kiểm theo chính sách dự án khi chuyển sang production.

## 5. Producer pom.xml hoàn chỉnh

Tệp `producer/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lab.release</groupId>
    <artifactId>price-contract</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Ở đây:

- `packaging=jar` tạo main JAR có classifier rỗng.
- `commons-lang3` có scope compile mặc định, cần thiết khi consumer chạy producer code.
- JUnit ở scope test chỉ dùng để kiểm thử producer, không được tự đưa vào consumer runtime graph.
- Plugin install/deploy lấy tọa độ project và artifact/POM đã đóng gói từ Maven lifecycle.
- Producer không cần Main-Class trong manifest vì đây là library JAR.

POM **chưa** chứa `distributionManagement`; kịch bản staging dùng một URL file repository từ CLI, tránh trỏ nhầm repository production.

## 6. Producer Java class và resource

Tệp `producer/src/main/java/lab/release/contract/PriceText.java`:

```java
package lab.release.contract;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class PriceText {
    private PriceText() {
    }

    public static String label(String sku, long cents) {
        String normalized = StringUtils.upperCase(
                StringUtils.trimToEmpty(sku), Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("sku required");
        }
        if (cents < 0) {
            throw new IllegalArgumentException("cents must be >= 0");
        }
        return "SKU " + normalized + ": " + cents + " cents";
    }

    public static String banner() throws IOException {
        try (InputStream input = PriceText.class.getResourceAsStream(
                "/contract/banner.txt")) {
            if (input == null) {
                throw new IOException("Missing contract/banner.txt");
            }
            return new String(input.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }
}
```

`StringUtils.upperCase(String,Locale)` và `StringUtils.trimToEmpty(String)` thuộc Commons Lang. Class này **thực sự cần** Commons Lang khi chạy; bỏ dependency khỏi published POM có thể gây lỗi runtime. `Locale.ROOT` tránh việc uppercase khác nhau theo locale của máy.

Public API là `label(String,long)` và `banner()`. Khi gọi `PriceText.label("  tea  ",2500)`, chuỗi trả về:

```text
SKU TEA: 2500 cents
```

Đây là biểu thức minh họa, không phải một class Java độc lập.

Tệp `producer/src/main/resources/contract/banner.txt`:

```text
CONTRACT_READY
```

Maven Resources Plugin đưa nó vào `target/classes/contract/banner.txt`; JAR Plugin đóng gói entry `contract/banner.txt`. Hàm `banner()` đọc **classpath resource**, không dùng đường dẫn filesystem `src/main/resources` vốn không tồn tại ở consumer.

## 7. Producer unit tests

Tệp `producer/src/test/java/lab/release/contract/PriceTextTest.java`:

```java
package lab.release.contract;

import java.io.IOException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceTextTest {

    @Test
    void formatsSku() {
        assertEquals("SKU TEA: 2500 cents",
                     PriceText.label("  tea  ", 2500));
    }

    @Test
    void rejectsBlankSku() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> PriceText.label(" ", 100));
        assertEquals("sku required", error.getMessage());
    }

    @Test
    void readsBanner() throws IOException {
        assertEquals("CONTRACT_READY", PriceText.banner());
    }
}
```

Producer có **3 JUnit tests**. Chúng xác nhận source/provider behavior nhưng không chứng minh một JAR đã install/deploy cùng published POM có thể dùng từ project khác. Test classpath trong producer có thể chứa `target/classes` và các libraries chỉ dành cho test.

## 8. Consumer pom.xml hoàn chỉnh

Tệp `consumer/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lab.consumer</groupId>
    <artifactId>artifact-consumer-check</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>lab.release</groupId>
            <artifactId>price-contract</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>qa-stage</id>
            <repositories>
                <repository>
                    <id>qa-file-repo</id>
                    <url>${qa.repo.url}</url>
                    <releases>
                        <enabled>true</enabled>
                    </releases>
                    <snapshots>
                        <enabled>false</enabled>
                    </snapshots>
                </repository>
            </repositories>
        </profile>
    </profiles>
</project>
```

Consumer có dependency theo GAV, **không có parent/modules trỏ producer**. `qa-stage` chỉ được bật bằng `-Pqa-stage` cho kiểm thử staging; khi dùng local install không bật profile và không cần giá trị `qa.repo.url`.

Producer dùng Commons Lang, nhưng consumer source chỉ gọi `PriceText`. Vì vậy consumer **không trực tiếp khai báo Commons Lang**: một trong những mục tiêu là kiểm transitive dependency từ published producer POM. Nếu consumer source trực tiếp import `StringUtils`, trong ứng dụng thật nên khai báo dependency Commons Lang **trực tiếp**.

JUnit Jupiter là test dependency riêng của consumer, không lấy bắc cầu từ producer test scope.

## 9. Consumer application

Tệp `consumer/src/main/java/lab/consumer/ConsumerApp.java`:

```java
package lab.consumer;

import java.io.IOException;
import lab.release.contract.PriceText;

public final class ConsumerApp {
    private ConsumerApp() {
    }

    public static String message() throws IOException {
        return "Invoice => " + PriceText.label("  tea  ", 2500)
                + " | " + PriceText.banner();
    }

    public static void main(String[] args) throws IOException {
        System.out.println(message());
    }
}
```

Consumer chỉ import public class của producer JAR. Nếu runtime thiếu Commons Lang, `PriceText.label()` có thể lỗi. Nếu resource thiếu, `banner()` ném IOException. Với đúng artifact và classpath, **stdout chính xác của riêng chương trình**:

```text
Invoice => SKU TEA: 2500 cents | CONTRACT_READY
```

## 10. Consumer contract tests

Tệp `consumer/src/test/java/lab/consumer/IndependentConsumerTest.java`:

```java
package lab.consumer;

import java.nio.file.Path;
import java.security.CodeSource;
import lab.release.contract.PriceText;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class IndependentConsumerTest {

    @Test
    void usesPublicApiAndBehavior() throws Exception {
        assertEquals(
                "Invoice => SKU TEA: 2500 cents | CONTRACT_READY",
                ConsumerApp.message());
    }

    @Test
    void readsResourceFromArtifact() throws Exception {
        assertEquals("CONTRACT_READY", PriceText.banner());
    }

    @Test
    void resolvesRuntimeTransitiveDependency() throws Exception {
        Class<?> type = Class.forName(
                "org.apache.commons.lang3.StringUtils");
        assertNotNull(type);
    }

    @Test
    void loadsVersionedJarNotProducerTarget() throws Exception {
        CodeSource source =
                PriceText.class.getProtectionDomain().getCodeSource();
        assertNotNull(source);
        Path path = Path.of(source.getLocation().toURI());
        assertEquals("price-contract-1.0.0.jar",
                     path.getFileName().toString());
    }
}
```

**Bốn tests** có mục đích:

1. Gọi public API, xác minh behavior mà consumer phụ thuộc.
2. Đọc resource qua classpath từ artifact JAR.
3. Chứng minh Commons Lang hiện diện trên consumer test/runtime graph, dù consumer không thêm trực tiếp nó.
4. Kiểm class `PriceText` được load từ file JAR có version mong đợi, **không phải** thư mục `producer/target/classes`.

Assertion `CodeSource` phù hợp với Maven JAR thông thường trên Surefire classpath. Với JPMS custom loaders, Spring Boot nested JAR hoặc OSGi, class origin có thể khác và kiểm tra phải điều chỉnh.

**Giới hạn:** filename JAR không chứng minh repository tải về. Để khẳng định staging origin, cần **fresh local repository**, transfer evidence và checksum.

## 11. Chạy producer install, consumer verify độc lập

Từ thư mục `artifact-consumer-lab` trên Linux/macOS:

```bash
REPO="$PWD/.qa-m2-local"

mvn -B "-Dmaven.repo.local=$REPO" \
    -f producer/pom.xml clean install

mvn -B "-Dmaven.repo.local=$REPO" \
    -f consumer/pom.xml clean verify
```

Bước đầu:

- Biên dịch producer Java 17.
- Surefire chạy **3 tests**.
- JAR Plugin tạo `producer/target/price-contract-1.0.0.jar`.
- Install Plugin cài main JAR và POM vào `.qa-m2-local`.

Bước hai:

- Đọc POM consumer **tách biệt**.
- Resolve `lab.release:price-contract:1.0.0` từ local repository đã cài.
- Resolve Commons Lang 3.14.0 từ metadata producer và JUnit từ POM consumer.
- Compile ConsumerApp, chạy **4 consumer tests**, sau đó verify.

Tổng số tests của **hai Maven commands riêng** là **7** (3 producer + 4 consumer), không phải một Reactor có bảy tests.

### 11.1. Windows PowerShell

Từ cùng thư mục cha:

```powershell
$repo = Join-Path (Get-Location) '.qa-m2-local'

mvn -B "-Dmaven.repo.local=$repo" -f producer/pom.xml clean install
if ($LASTEXITCODE -ne 0) { throw 'Producer build/install failed' }

mvn -B "-Dmaven.repo.local=$repo" -f consumer/pom.xml clean verify
if ($LASTEXITCODE -ne 0) { throw 'Consumer verify failed' }
```

Không dùng cú pháp Bash `\` nối dòng trong Windows PowerShell. Nếu môi trường dùng localRepository tùy biến trong settings, `-Dmaven.repo.local` chỉ định rõ repository QA cho cả hai lệnh.

### 11.2. Test reports

```text
producer/target/surefire-reports/TEST-lab.release.contract.PriceTextTest.xml
consumer/target/surefire-reports/TEST-lab.consumer.IndependentConsumerTest.xml
```

Kỳ vọng producer **3 tests**, consumer **4 tests**, failures/errors/skipped = 0. Đọc XML mới cùng Maven exit code, không chỉ nhìn `BUILD SUCCESS`.

## 12. Chạy runtime smoke test qua Maven Exec Plugin

Khi consumer đã verify thành công, dùng runtime classpath được Maven xây từ GAV + POM:

```bash
mvn -B "-Dmaven.repo.local=$REPO" \
    -f consumer/pom.xml \
    org.codehaus.mojo:exec-maven-plugin:3.3.0:java \
    -Dexec.mainClass=lab.consumer.ConsumerApp \
    -Dexec.classpathScope=runtime
```

Trên PowerShell (với biến `$repo`):

```powershell
mvn -B "-Dmaven.repo.local=$repo" `
    -f consumer/pom.xml `
    org.codehaus.mojo:exec-maven-plugin:3.3.0:java `
    -Dexec.mainClass=lab.consumer.ConsumerApp `
    -Dexec.classpathScope=runtime
```

Dấu backtick nối lệnh PowerShell phải ở **cuối dòng** không có khoảng trắng theo sau. `exec.classpathScope=runtime` làm smoke test dùng compile/runtime dependencies và không dựa vào JUnit test-only classpath.

**Dòng mà chương trình in:**

```text
Invoice => SKU TEA: 2500 cents | CONTRACT_READY
```

Maven console còn có các dòng `[INFO]`; chúng không phải stdout của riêng ConsumerApp.

Không thử `java -jar consumer/target/artifact-consumer-check-1.0.0.jar` rồi kết luận artifact producer lỗi: consumer JAR bình thường không có Main-Class và không gộp runtime dependencies theo mặc định. Muốn dùng `java -jar`, phải thiết kế executable packaging riêng.

## 13. Đọc dependency tree ở consumer

Trên Linux/macOS:

```bash
mvn -B "-Dmaven.repo.local=$REPO" \
    -f consumer/pom.xml \
    org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Một phần cây dependency mong đợi:

```text
lab.consumer:artifact-consumer-check:jar:1.0.0
+- lab.release:price-contract:jar:1.0.0:compile
|  \- org.apache.commons:commons-lang3:jar:3.14.0:compile
\- org.junit.jupiter:junit-jupiter:jar:5.10.2:test
   ... JUnit transitive test dependencies ...
```

Đây là sơ đồ **rút gọn**, không phải toàn bộ Maven stdout. Tree thực có thể liệt kê thêm JUnit Platform/Jupiter artifacts.

Kiểm các điểm:

- Đúng GAV producer: `lab.release:price-contract:1.0.0`.
- Commons Lang 3.14.0 xuất hiện như transitive dependency.
- JUnit được dùng cho tests nhưng không là runtime dependency từ producer.
- Không có version xung đột bị dependency mediation chọn.
- Không có `system` scope trỏ filesystem producer.
- Không có warning về missing POM/parent/BOM.

### 13.1. Đọc JAR và POM là hai phép thử khác nhau

```bash
jar tf producer/target/price-contract-1.0.0.jar
```

Tìm entries:

```text
lab/release/contract/PriceText.class
contract/banner.txt
```

Nhưng `jar tf` không xác nhận published POM chứa Commons Lang dependency. Nếu chỉ cài một JAR bằng `install-file` với POM do tool tạo tối giản, consumer compile được class PriceText nhưng khi gọi `PriceText.label()` có thể gặp `NoClassDefFoundError` do thiếu `StringUtils`.

Để hiểu runtime dependency, phải kết hợp **JAR inspection + consumer dependency tree + consumer test/smoke**.

## 14. Vì sao test từ source của producer dễ che lỗi metadata?

Một project Maven có thể có:

```text
producer/src/main/java/...
producer/target/classes/...
producer/target/test-classes/...
producer/target/price-contract-1.0.0.jar
```

Surefire ở producer thường dùng `target/classes` và dependencies do POM producer cung cấp. Nó không tự bảo đảm JAR/POM **được publish** sẽ tương ứng hoàn toàn với classpath này.

Lỗi có thể đến từ:

- Resource chỉ nằm ở `src/test/resources`, nên producer tests thấy nhưng main JAR không có.
- Parent POM nội bộ build được qua `relativePath` nhưng chưa deploy, consumer báo `Non-resolvable parent POM`.
- Metadata dependency bị thiếu trong generated/deployed POM.
- Một plugin Shade/Assembly thay main artifact sau tests.
- Consumer chạy JVM thấp hơn Java bytecode release của producer.
- Consumer dùng phiên bản artifact cũ do cache.
- Dependency được đánh dấu `provided`/`optional` ngoài ý muốn nên không truyền bắc cầu.

Đó là lý do consumer riêng phải được build từ **artifact đã install/deploy**, không dựa vào source tree producer.

## 15. Staged deploy: kiểm chứng artifact có thể được tải bằng cache mới

Local install QA vẫn chỉ là hai project dùng chung một local repository. Muốn kiểm chứng **deploy và tải từ repository**, thử file-based Maven repository trước, không dùng quyền production.

### 15.1. Bash trên Linux/macOS

Từ `artifact-consumer-lab`:

```bash
ROOT="$PWD"
STAGE_DIR="$ROOT/qa-staging-repository"
STAGE_URL="file://$STAGE_DIR"
BUILD_M2="$ROOT/.qa-m2-build"
FETCH_M2="$ROOT/.qa-m2-fresh"

mvn -B "-Dmaven.repo.local=$BUILD_M2" \
    -f producer/pom.xml clean deploy \
    "-DaltDeploymentRepository=qa-file-repo::$STAGE_URL"

mvn -B "-Dmaven.repo.local=$FETCH_M2" \
    -f consumer/pom.xml -Pqa-stage \
    "-Dqa.repo.url=$STAGE_URL" clean verify
```

Với **Maven Deploy Plugin 3.1.2**, `altDeploymentRepository` dùng cú pháp **`id::url`**, ví dụ `qa-file-repo::file:///...`. Cú pháp ba phần `id::layout::url` thuộc Deploy Plugin 2.x.

Lệnh producer chạy lifecycle đến deploy, tạo JAR/POM rồi upload vào directory file repository. Lệnh consumer bật profile `qa-stage` và tải dependency qua file repository bằng Maven Resolver.

**`FETCH_M2` phải là directory mới** của lần QA hiện tại. Nếu có artifact đã cache từ trước, test có thể PASS dù staged deploy vừa lỗi. Chọn thư mục mới theo CI run ID; không xóa toàn bộ `~/.m2` cá nhân tùy tiện.

### 15.2. PowerShell với file URI

Trên Windows, file repository URL thường có dạng `file:///C:/path/to/repository`, không phải một raw path chứa backslash.

```powershell
$root = (Get-Location).Path
$stage = Join-Path $root 'qa-staging-repository'
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$stageUrl = ([System.Uri]::new(
    (Get-Item -LiteralPath $stage).FullName)).AbsoluteUri

$buildM2 = Join-Path $root '.qa-m2-build'
$freshM2 = Join-Path $root '.qa-m2-fresh'

mvn -B "-Dmaven.repo.local=$buildM2" `
    -f producer/pom.xml clean deploy `
    "-DaltDeploymentRepository=qa-file-repo::$stageUrl"
if ($LASTEXITCODE -ne 0) { throw 'Staging deploy failed' }

mvn -B "-Dmaven.repo.local=$freshM2" `
    -f consumer/pom.xml -Pqa-stage `
    "-Dqa.repo.url=$stageUrl" clean verify
if ($LASTEXITCODE -ne 0) { throw 'Fresh consumer verify failed' }
```

Kiểm tra `$stageUrl` là file URI tuyệt đối hợp lệ trước khi chạy. Các lệnh này chỉ sử dụng **repository trong thư mục thực hành**, không upload lên repository doanh nghiệp.

### 15.3. Những bằng chứng staged QA cần thêm

- Deploy logs xác nhận upload JAR và POM vào `qa-file-repo`.
- File staging có đúng coordinates/version, không chỉ file tên gần giống.
- Consumer bắt đầu với local cache mới **chưa có** producer artifact.
- Transfer logs/mirror settings hoặc repository manager logs xác nhận nguồn tải.
- Consumer dependency tree chọn đúng JAR và Commons Lang.
- Consumer tests pass, CodeSource là JAR đúng filename.
- Khi có yêu cầu provenance, SHA-256 của artifact staging và downloaded copy khớp với candidate.

**CodeSource filename không chứng minh URL nguồn tải.** Nếu artifact trùng GAV có sẵn trong Maven Central/corporate mirror, Maven có thể lấy từ repository khác. Để chứng minh stage, dùng namespace riêng, cache mới và evidence của transfer origin.

### 15.4. File repository khác repository manager thật

`file://` hỗ trợ kiểm Maven layout và cơ chế deploy/download nhưng không thử đầy đủ xác thực, phân quyền, snapshot metadata promotion, immutable release policies, mirror/proxy hoặc security scanning của Nexus/Artifactory/Archiva.

Trong production, chạy consumer stage QA với repository manager **thực tế** sau khi được cấp quyền đúng. Không deploy release lên production chỉ để thực hành.

## 16. Cấu hình repository thật: deploy và resolve khác nhau

Producer có thể khai báo:

```xml
<distributionManagement>
    <repository>
        <id>approved-releases</id>
        <url>https://repo.example.invalid/maven/releases</url>
    </repository>
    <snapshotRepository>
        <id>approved-snapshots</id>
        <url>https://repo.example.invalid/maven/snapshots</url>
    </snapshotRepository>
</distributionManagement>
```

Đây là **đoạn cấu hình minh họa**, domain `example.invalid` không phải endpoint sử dụng thật. Credentials cần được quản lý trong `settings.xml`/CI secret management; `<server><id>` khớp repository ID. Không đưa token/password vào POM hay log.

Nhớ phân biệt:

- `distributionManagement`: producer **deploy** lên đâu.
- `<repositories>`/settings: consumer **download** artifact ở đâu.
- `<pluginRepositories>`: Maven tải build plugins ở đâu.
- `mvn install`: chỉ đưa artifact vào **local** repo của môi trường chạy lệnh.

Một producer dùng repository thử nghiệm không tự làm consumer ở máy khác nhìn thấy repository đó.

## 17. Metadata POM và dependency scopes là một phần hợp đồng

Published POM có thể đòi một parent POM/BOM riêng. Nếu producer build trong Reactor nhờ `relativePath` nhưng parent chưa publish, consumer có thể không resolve được dependency model.

Các scopes quan trọng:

| Scope/flag tại producer | Tác động với consumer |
| --- | --- |
| `compile` | Thường truyền bắc cầu đến compile/runtime graph |
| `runtime` | Có thể cần khi chạy dù không dùng khi compile |
| `test` | Không tự truyền vào runtime consumer |
| `provided` | Producer trông chờ JDK/container cung cấp; không tự truyền như runtime library |
| `optional=true` | Consumer thường không tự được kéo transitive artifact đó |
| `exclusions` | Có thể làm thiếu dependency khi cấu hình sai |

Với `PriceText`, Commons Lang phải sẵn có khi runtime. Nếu POM producer bị tạo thủ công không khai báo Commons Lang, consumer có thể lỗi mặc dù JAR có `PriceText.class`.

Một consumer cần parent/BOM có thể được bảo vệ bằng cách **publish parent/BOM đúng tọa độ**, hoặc dùng Flatten Plugin/consumer POM strategy phù hợp khi dùng CI-friendly versions trên Maven 3. Không tự tạo POM trống để che lỗi parent.

## 18. Bảo vệ source, binary và behavioral compatibility

**Source compatibility:** nếu producer xóa `PriceText.label(String,long)`, source consumer không compile được.

**Binary compatibility:** consumer đã compile trước có bytecode tham chiếu method descriptor cũ. Dùng JAR mới thiếu method đó có thể gây `NoSuchMethodError`, ngay cả khi một consumer được compile lại với API mới pass. Muốn thử, giữ **consumer bytecode cũ**, đổi runtime artifact theo kịch bản có kiểm soát, chạy smoke và so API/ABI bằng công cụ như Revapi/japicmp.

**Behavior compatibility:** nếu method vẫn còn nhưng đổi output từ `SKU TEA: 2500 cents` thành `TEA=2500`, consumer compile pass nhưng `usesPublicApiAndBehavior()` fail. Contract còn gồm errors, schema, encoding, timezone, ordering và serialization.

**JVM compatibility:** nếu producer compile lên class-file version cao hơn JVM consumer, có thể gặp `UnsupportedClassVersionError`. Test trên JDK tối thiểu mà sản phẩm hứa hỗ trợ, không chỉ JDK máy build.

Không dựa vào số SemVer/GAV để kết luận tương thích; Maven không tự chứng minh Java/public wire contract dựa vào version string.

## 19. Negative tests giúp phát hiện QA giả

Thực hiện trên branch/staging version riêng, không ghi đè release đã dùng:

| Thử sai có chủ đích | Kỳ vọng |
| --- | --- |
| Consumer yêu cầu một GAV không tồn tại | Maven dependency resolution fail |
| JAR producer thiếu PriceText.class | Consumer compile fail |
| JAR thiếu `contract/banner.txt` | Consumer resource test fail |
| POM producer bỏ Commons Lang | Runtime có thể báo `NoClassDefFoundError` |
| Producer đổi output string | Behavioral assertion fail |
| Producer xóa `label(String,long)` | Compile/linkage fail |
| Consumer load producer từ `target/classes` | CodeSource filename assertion fail |
| Bytecode producer yêu cầu JDK mới hơn | JVM class loading fail |
| Consumer được cấp artifact cũ trong cache | Staging origin check phát hiện sai source nếu cache/provenance được kiểm |

**Không sửa rồi redeploy đè cùng release GAV** để tạo lỗi. Nên dùng candidate/staging version riêng và kiểm lại QA sau khi khôi phục.

## 20. Những lỗi phổ biến khi kiểm chứng độc lập

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Consumer không tìm được price-contract | GAV sai, chưa install/deploy hoặc repository không thấy | Kiểm coordinates, settings, repo logs |
| Producer test pass nhưng consumer compile fail | Artifact/JAR khác source, POM/parent metadata lỗi | Xem published POM và JAR |
| `Non-resolvable parent POM` | Parent/BOM chưa publish | Publish đúng POM hoặc dùng consumer POM strategy |
| `NoClassDefFoundError` StringUtils | Commons Lang không vào consumer runtime classpath | Kiểm POM producer, dependency tree/scopes |
| `NoSuchMethodError` | Binary consumer dùng JAR API khác | So GAV, class origin, API diff |
| `UnsupportedClassVersionError` | JVM thấp hơn bytecode target | Kiểm Compiler release/JDK |
| `banner()` thiếu resource | File không được đóng vào main JAR | Kiểm `jar tf`, Maven Resources Plugin |
| CodeSource chỉ `target/classes` | Test đang dùng source output | Tách Reactor, bỏ classpath direct |
| Local PASS, CI FAIL | Local Maven repo có artifact cũ | Dùng cache sạch, pin toolchain |
| Staging deploy fail nhưng consumer PASS | Consumer đọc cache/mirror khác | Fresh repo, transfer origin/checksum |
| HTTP 401/403 khi deploy | Credentials/quyền/policy | Kiểm server ID và quyền được duyệt |
| qa-stage profile không lấy URL | Quên `-Pqa-stage`/`qa.repo.url` | Cấp file/HTTPS URI đúng |
| Dependency tree chọn version khác | Mediation/management/exclusion | Đọc effective POM và tree |
| Unit test count 0 nhưng build xanh | Test discovery/skip flags sai | `failIfNoTests`, Surefire XML |
| `java -jar` consumer fail | JAR không executable/fat JAR | Dùng Exec Plugin runtime classpath |
| Install-file làm POM mất dependencies | POM tự sinh thiếu metadata | Install/deploy qua project POM đầy đủ |
| SNAPSHOT cùng GAV cho byte khác nhau | Mutable artifact + Maven cache | Check checksum/provenance |
| Repo staging khác Nexus production | Features/policy khác | QA repository manager thực tế |

### 20.1. Thứ tự debug

1. GAV, type, classifier đúng chưa?
2. Maven đang resolve JAR/POM từ repository nào?
3. Published POM có parent/BOM/dependency metadata đầy đủ không?
4. Consumer dependency tree và runtime scope đúng chưa?
5. JAR chứa class/resource cần thiết không?
6. Runtime JDK và Java bytecode release có tương thích?
7. CodeSource class thật sự là JAR nào?
8. Consumer compile, unit tests, runtime smoke có pass?
9. Local cache/mirror/provenance có làm sai kết luận?
10. API/ABI/behavior và external contract có đáp ứng release policy?

## 21. CI gate và evidence

Workflow khuyến nghị:

```text
Producer source commit + Maven/JDK đã pin
          |
          v
mvn clean verify + producer Surefire XML
          |
          v
Đối chiếu JAR, POM, resource, checksum
          |
          v
Deploy JAR/POM tới staging repository
          |
          v
Tạo fresh local Maven cache cho consumer job
          |
          v
Consumer Maven resolve GAV từ staged repository
          |
          v
Consumer clean verify + Surefire XML + dependency tree
          |
          v
Runtime smoke + class origin + checksum/provenance
          |
          v
API/ABI/behavior checks theo chính sách
          |
          v
Promote chính candidate artifact đã được QA
```

Evidence tối thiểu:

- Maven/JDK/tool versions và commit tạo artifact.
- Producer Surefire XML: **3 tests**, failures/errors/skipped 0.
- Consumer Surefire XML: **4 tests**, failures/errors/skipped 0.
- Main JAR đúng GAV và chứa PriceText.class + banner.txt.
- Published POM truyền Commons Lang 3.14.0.
- Consumer dependency tree nhận đúng artifact transitive.
- Consumer runtime stdout chính xác.
- CodeSource là JAR version được mong đợi.
- Khi staged: fresh cache, transfer logs và checksum.
- Khi release: repository policy, approvals và rollback.

Nếu verify fail, CI vẫn nên giữ XML/logs; đừng coi một module `SKIPPED` là pass. Không upload toàn bộ Maven local repo làm build artifact mặc định vì chứa cache không liên quan và có thể có metadata nội bộ.

## 22. Checklist bàn giao

- [ ] Producer clean build/test/package thành công với JDK hỗ trợ?
- [ ] Main artifact GAV/version/type/classifier đúng?
- [ ] JAR có class/resource/API cần thiết?
- [ ] Published POM có dependencies, scopes, parent/BOM đúng?
- [ ] Consumer thực sự tách khỏi Reactor/source/output của producer?
- [ ] Consumer chỉ khai báo Maven GAV, không systemPath?
- [ ] Local install check dùng đúng repo cô lập cho hai Maven runs?
- [ ] Producer 3 tests và consumer 4 tests chạy thật?
- [ ] Consumer API behavior, resource và transitive library tests pass?
- [ ] Consumer CodeSource cho biết JAR version đúng?
- [ ] Runtime smoke dùng runtime classpath đúng?
- [ ] Nếu kiểm deploy, consumer local cache mới và staging transfer được xác nhận?
- [ ] Dependency tree không kéo artifact cũ/scope sai?
- [ ] Test trên runtime JDK tối thiểu được hỗ trợ?
- [ ] API/ABI/binary consumer cũ được kiểm khi release policy đòi hỏi?
- [ ] Snapshot/release immutability và checksum/provenance được xử lý?
- [ ] Không publish secret hoặc debug logs nhạy cảm?
- [ ] Có CI evidence, approval và rollback path?

**Kết luận:** một Maven artifact không được coi là đủ điều kiện bàn giao chỉ vì producer tests thành công. Hãy để một **dự án tiêu thụ độc lập** resolve JAR và POM theo GAV từ local install hoặc staged deploy, kiểm tra class/resource, transitive dependencies, API/behavior và runtime. Với staged release, dùng **local cache mới** và xác minh source/checksum của artifact. Đây là cách phát hiện các lỗi phân phối mà IDE hay Maven Reactor nguồn dễ che giấu.

### Tài liệu tham khảo chính thức

- [Apache Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/)
- [Apache Maven Install Plugin — Usage](https://maven.apache.org/plugins/maven-install-plugin/usage.html)
- [Apache Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html)
- [Apache Maven Deploy Plugin — deploy:deploy](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven — Local Repositories](https://maven.apache.org/repositories/local.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven — Guide to Testing Staged Releases](https://maven.apache.org/guides/development/guide-testing-releases.html)
- [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
- [Apache Commons Lang — StringUtils API](https://commons.apache.org/proper/commons-lang/apidocs/org/apache/commons/lang3/StringUtils.html)
