# So sánh checksum từ hai môi trường build độc lập bằng Maven

**Một build được xem là có khả năng tái lập ở mức byte (reproducible build) khi cùng source, build instructions và các input/môi trường đã kiểm soát tạo ra cùng những artifact bytes, dù được thực hiện độc lập.** Với Java/Maven, cách kiểm rõ ràng là lấy đúng một Git commit, build trên hai máy hoặc hai CI runners tách biệt, xuất bản **SHA-256 checksum của chính file JAR** ở mỗi bên, so sánh digest và kiểm tra điều kiện xây dựng. Hai file có cùng tên, cùng version hay cùng output chương trình **chưa chắc có cùng bytes**.

Bài thuộc nhóm **Thực hành tổng hợp**; triển khai đầy đủ từ **Java 17 + Maven 3.9.x + JUnit 5**, cấu hình `project.build.outputTimestamp`, ghim plugin/dependency versions, đến thu thập SHA-256 bằng Linux/macOS/PowerShell và một chương trình Python 3 kiểm tra độc lập. Bài cũng phân biệt **build lại hai lần trên cùng máy** với **rebuild thực sự độc lập**, diễn giải trường hợp checksums không khớp, khảo sát nội dung JAR/ZIP, sử dụng Maven Artifact Plugin để so với reference artifacts và thiết kế CI gate không bỏ qua kiểm thử.

**Kết quả mong đợi:** hai bên tạo `checksum-compare-lab-1.0.0.jar` từ cùng commit; khi thực sự kiểm soát các inputs và build tooling, SHA-256 hai JAR **phải trùng nhau**. Bài không bịa một digest 64 ký tự vì SHA thực tế chỉ có thể biết sau khi chạy build. Đầu ra của ứng dụng Java trong ví dụ thì xác định chính xác: `receipt=BOOK:450` và `verified=true`.

## 1. Ba thuật ngữ quan trọng

| Thuật ngữ | Ý nghĩa | Bằng chứng |
| --- | --- | --- |
| **Deterministic build** | Cùng input và điều kiện cho cùng output | Nhiều lần build có bytes giống nhau |
| **Reproducible build** | Bên khác có thể xây lại artifact byte-for-byte từ cùng source/build definition và môi trường được kiểm soát | Hai môi trường độc lập, SHA-256 trùng, provenance đủ |
| **Verifiable build** | Bên kiểm tra xác nhận artifact tham chiếu liên hệ với đúng source/build instructions | Checksum + provenance + quy trình tin cậy |
| **Artifact checksum** | Digest của bytes file cụ thể, ví dụ SHA-256 của JAR | 64 ký tự hex, cùng digest khi bytes giống |
| **Provenance** | Dữ liệu nguồn và điều kiện build: commit, Maven/JDK, OS, plugin/dependency resolution | Metadata được ghi **ngoài** JAR, CI attestations |
| **Bitwise identical** | Mọi byte ở cùng vị trí đều bằng nhau | `cmp` / SHA-256 / file compare |

Không đánh đồng **functional equivalence** và **bitwise equality**. Hai JAR khác metadata ZIP timestamps vẫn có thể chạy cùng kết quả. Ngược lại, hai JAR có cùng SHA-256 cho biết xác suất cực cao chúng cùng bytes, nhưng **không chứng minh** code vô hại, đúng nghiệp vụ hoặc không có vulnerability.

### 1.1. SHA-256 thật sự kiểm cái gì?

SHA-256 nhận dãy bytes B và tạo digest dài 256 bit:

```text
SHA256(B) -> 256 bit -> 64 hex characters
```

Nếu `A.jar` và `B.jar` thật sự có cùng bytes, tất yếu `SHA256(A.jar) = SHA256(B.jar)`. Nếu hashes khác nhau, chắc chắn files khác bytes. Nếu hashes trùng, trong ngữ cảnh kiểm checksum đáng tin, có thể xem đó là bằng chứng rất mạnh về byte identity, nhưng về mặt toán học không phải chứng minh bất khả có hash collision.

SHA-256 **không** tự mã hóa dữ liệu, không tự xác thực người đã build, và không ngăn một attacker thay **cả JAR lẫn file chứa checksum**. Khi xác nhận nguồn phát hành, cần signed checksum, chữ ký artifact, attestation/provenance và kênh phát hành đáng tin.

### 1.2. Hash file JAR, không hash cả thư mục target một cách tùy tiện

`target` chứa generated classes, compiler metadata, Surefire reports, timestamps/logs và nhiều file trung gian; một số phần **không phải release artifacts** hoặc không được hứa tái lập byte-for-byte. Đầu tiên xác định scope:

```text
Release artifact (lab):
target/checksum-compare-lab-1.0.0.jar

Các output khác cần policy riêng:
target/classes/
target/test-classes/
target/surefire-reports/
target/*.buildinfo
target/*.buildcompare
build logs
SBOM/signatures/sources/javadoc JAR nếu phát hành
```

Nếu project phát hành **nhiều files** (main JAR, sources JAR, javadoc JAR, POM, BOM, ZIP, OCI image...), CI phải lập manifest cho **tất cả artifacts bắt buộc**, không chỉ main JAR. Các reports/logs nên lưu làm bằng chứng riêng, không vô tình coi digest của một file log không ổn định là build reproducibility của JAR.

## 2. “Hai môi trường độc lập” nghĩa là gì?

Cần ít nhất **hai build executions tách biệt**. Mức độ tin cậy tăng dần:

1. **A và B là hai thư mục khác nhau trên cùng máy.** Hữu ích phát hiện absolute path/timestamp; chưa chứng minh khác JDK/OS/username.
2. **Hai sạch Git checkouts trên hai CI workers/containers độc lập.** Có filesystem, process, Maven cache và working directory riêng; rất phù hợp để luyện reproducibility.
3. **Hai máy độc lập, khác người quản trị/nguồn build.** Kiểm mạnh hơn về hidden state/đường dẫn/username, nhưng phải bảo đảm toolchains/inputs được xác định.
4. **Rebuilder bên thứ ba so với artifact đã xuất bản.** Phải tin cậy reference artifact identity, source commit/tag và build instructions; đây là bối cảnh bảo đảm software supply chain mạnh hơn.

**Hai lần `mvn clean package` liên tiếp trên cùng checkout, cùng local Maven repo và cùng user chỉ là bài kiểm sơ bộ.** Apache Maven guide cũng cảnh báo so local build với bản đã `install` chưa chứng minh được third-party reproducibility vì vẫn có các rò rỉ môi trường như username/current directory.

### 2.1. Tối thiểu phải thống nhất những gì?

| Biến | Yêu cầu khi so sánh lần đầu |
| --- | --- |
| Source revision | **Cùng Git commit SHA**, checkout không bị sửa |
| POM/parent/BOM | Cùng effective model, phụ thuộc/phần mở rộng/plugins được pin |
| Maven distribution | Cùng Maven version, ví dụ Maven 3.9.x đã chốt ở CI image |
| Java | Cùng JDK 17 toolchain; nên giữ cùng vendor/build khi baseline |
| Build command | Cùng goals/phases/profiles/`-D` flags |
| Dependency resolution | Không version ranges/snapshot trôi; mirrors/repositories nhất quán |
| Encoding | UTF-8 cho Java/resources, line endings được chuẩn hóa |
| Archive timestamp | `project.build.outputTimestamp` cố định hoặc nguồn thời gian deterministic |
| Runtime external inputs | Env vars, templates, generated sources, network, random, locale, timezone được kiểm |
| Output set | Cùng artifact path/GAV/classifier/packaging |
| Test gate | `mvn clean verify` thành công; cùng test selection, không skip |
| Build caches | Không sử dụng cache hit thiếu minh bạch để giả vờ một independent rebuild |

**Không cần mọi yếu tố vật lý giống nhau mãi mãi**: sau khi baseline cùng OS/JDK pass, cố ý thay path, timezone, locale, user, OS hoặc JDK vendor để kiểm mức độ robust. Nhưng khi mismatch xảy ra, phải xác định **đầu vào nào đã khác**, tránh kết luận Maven sai từ hai build commands thực ra khác nhau.

## 3. Vì sao JAR có thể khác checksum dù code giống hệt?

JAR là một **ZIP archive** chứa class files, resources và metadata. Những nguồn khác biệt thường gặp:

- **ZIP entry timestamps:** thời gian lúc package/created file; hai runners có clock khác nhau.
- **Archive ordering:** thứ tự files trong ZIP không ổn định nếu plugin/generator phụ thuộc filesystem enumeration.
- **Manifest metadata:** `Build-Jdk-Spec`, `Created-By`, commit/build time, arbitrary build host.
- **Resources filtering:** chèn `${user.name}`, `${env.HOSTNAME}`, path/username, current date hoặc branch names.
- **Generated code:** sinh UUID, timestamp, sequence/order ngẫu nhiên, absolute source path.
- **Java compiler/toolchain:** bytecode khác giữa major JDK hoặc compiler implementation/flags.
- **Newline:** Windows CRLF và Unix LF trong `.properties`/`.xml`/text resources.
- **Locale/timezone:** string formatting, sorting, date generation, `Locale.getDefault()`.
- **File permissions/ZIP extra fields:** metadata phụ thuộc OS/plugin.
- **Dependency transitivity:** dynamic versions, timestamped snapshots, repository metadata thay đổi.
- **Signatures:** signatures có randomness/timestamp hoặc ký bởi người/khóa khác; ký sau khi build và có policy kiểm riêng.
- **Post-processing:** Shade, Assembly, minimization, obfuscation, coverage, code generation không deterministic.

Một Maven build report `BUILD SUCCESS` chỉ nói các goals được chọn thành công. Nó **không** đồng nghĩa JAR bytes đã ổn định giữa máy A và B.

### 3.1. project.build.outputTimestamp giải quyết phần nào?

Apache Maven hướng dẫn khai property:

```xml
<properties>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Các Maven archive plugins có hỗ trợ sẽ dùng timestamp đó khi tạo archive entries thay vì lấy thời điểm build thực. `maven-jar-plugin` phiên bản hiện đại như **3.4.2** hỗ trợ giá trị này. Giá trị có thể là ISO-8601 UTC hoặc integer seconds-since-epoch theo plugin/docs.

**Lưu ý:** property chỉ là một input; **không tự làm deterministic code generation, manifest fields tùy chỉnh, JDK bytecode, sorted input order hay external timestamps**. Một plugin cũ không hỗ trợ reproducible archiving vẫn có thể gây khác biệt dù property đã khai.

### 3.2. SOURCE_DATE_EPOCH là gì?

`SOURCE_DATE_EPOCH` là biến môi trường tiêu chuẩn từ Reproducible Builds effort, biểu diễn **số giây nguyên UTC kể từ 1970-01-01** và phải có giá trị phụ thuộc nguồn/phát hành, không phải giờ hiện tại. Một số công cụ dùng nó làm nguồn timestamp deterministic.

Ví dụ:

```bash
export SOURCE_DATE_EPOCH=1735689600
```

Giá trị trên ứng với **2025-01-01T00:00:00Z**. Tuy nhiên không suy rằng mọi Maven plugin/JDK version đều tự đọc biến này. Trong lab ta **đặt trực tiếp `project.build.outputTimestamp` trong POM** để hành vi archive rõ ràng với Maven 3.9.x. Nếu org dùng release automation, có thể cập nhật timestamp theo Git commit/release tag bằng công cụ có hỗ trợ, miễn là cùng source cho cùng timestamp.

## 4. Project lab Java 17 đầy đủ để tạo JAR deterministic

Project có **main JAR, một resource file text và 5 JUnit Jupiter test methods**. Code không đọc thời gian hiện tại, random seed, absolute path, hostname hoặc environment variables. Maven plugins và dependency versions được pin.

### 4.1. Cây thư mục

```text
checksum-compare-lab/
├── .gitattributes
├── .gitignore
├── pom.xml
├── scripts/
│   ├── build-and-hash.sh
│   └── compare_jars.py
└── src/
    ├── main/
    │   ├── java/vn/example/repro/
    │   │   ├── PriceMath.java
    │   │   ├── Receipt.java
    │   │   └── Main.java
    │   └── resources/
    │       └── catalog.properties
    └── test/
        └── java/vn/example/repro/
            ├── PriceMathTest.java
            └── ReceiptTest.java
```

`scripts` chứa hai files sẽ viết đầy đủ ở mục 6–7. Có thể tạo chúng sau khi các Java/POM files đã được lưu. Thư mục `target` chỉ được tạo bởi Maven và được ignore trong Git. Để làm reproducibility test có giá trị, toàn bộ source/scripts/POM/resource phải được commit và hai bên checkout cùng commit SHA.

### 4.2. .gitattributes: thống nhất line endings

File `.gitattributes`:

```gitattributes
*.java text eol=lf
*.xml text eol=lf
*.properties text eol=lf
*.sh text eol=lf
*.py text eol=lf
*.md text eol=lf
```

Git sẽ checkout các text files trên với **LF** bất kể Windows/Unix, trừ trường hợp local config và files đặc biệt cần xử lý khác. Điều này đặc biệt quan trọng cho `src/main/resources/catalog.properties` vì resource bytes thực sự được đưa vào JAR.

File `.gitignore`:

```gitignore
/target/
*.log
```

Không nên để source resources, generated sources quan trọng hoặc reproducibility config nằm ngoài Git rồi kỳ vọng hai checkouts tự đồng nhất.

### 4.3. pom.xml đầy đủ

File `checksum-compare-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>checksum-compare-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
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
                <configuration>
                    <release>${maven.compiler.release}</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-artifact-plugin</artifactId>
                <version>3.7.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích:**

1. `project.build.outputTimestamp` cố định; không lấy `new Date()` hoặc giờ chạy Maven.
2. `maven-jar-plugin:3.4.2` tạo JAR có timestamps deterministic, hỗ trợ property; khai `outputTimestamp` tường minh để bài học dễ kiểm.
3. `maven-compiler-plugin:3.13.0` dùng `--release 17`, nhưng cần chạy Maven với JDK hỗ trợ release 17.
4. `maven-resources-plugin:3.3.1` copy `catalog.properties` nguyên bytes. Không bật filtering chứa biến môi trường.
5. `maven-surefire-plugin:3.5.2` chạy JUnit Jupiter và `failIfNoTests=true` nhằm tránh build xanh khi không có tests.
6. `maven-artifact-plugin:3.7.0` cho phép dùng `artifact:check-buildplan` và `artifact:compare` khi cần; chỉ khai plugin **không tự chạy compare trong mọi `verify`**, nên main lab build vẫn độc lập.
7. Test-only `junit-jupiter` không được nhét vào main runtime JAR; Java main chỉ cần JDK.
8. Không dùng version ranges, `LATEST`, `RELEASE` hoặc floating SNAPSHOT trong lab.
9. POM không tự khai một Maven Wrapper. Trong CI thực tế nên pin Maven distribution bằng Maven Wrapper hoặc image có digest; không tự invent wrapper files khi lab chưa có.

**Phạm vi tương thích:** Maven 3.9.x, JDK 17+ và plugins được pin như trên. Để kiểm cross-environment dễ nhất, hai hosts dùng **cùng JDK 17 distribution/version** và cùng Maven version ở baseline.

### 4.4. PriceMath.java

File `src/main/java/vn/example/repro/PriceMath.java`:

```java
package vn.example.repro;

public final class PriceMath {
    private PriceMath() {
    }

    public static long subtotal(int unitCents, int quantity) {
        if (unitCents < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "unitCents and quantity must be nonnegative");
        }
        return (long) unitCents * quantity;
    }
}
```

Phép tính dùng `long` trước khi nhân hai `int` không âm; giá trị tối đa nhỏ hơn `Long.MAX_VALUE`. Method không dựa trên clock, locale hoặc random nên tạo cùng behavior trên hai JVM tương thích.

### 4.5. catalog.properties (resource thật trong JAR)

File `src/main/resources/catalog.properties`:

```properties
item=book
unitPriceCents=150
quantity=3
```

File text chỉ chứa ASCII và LF. Maven Resources Plugin copy nguyên nội dung từ `src/main/resources` vào `target/classes` rồi Maven JAR Plugin đưa vào archive. Nếu một host checkout CRLF và host kia LF, **SHA có thể khác dù Java functionality giống**, vì vậy .gitattributes có ý nghĩa thực tế.

### 4.6. Receipt.java: đọc resource từ classpath

File `src/main/java/vn/example/repro/Receipt.java`:

```java
package vn.example.repro;

import java.io.IOException;
import java.io.InputStream;
import java.util.Locale;
import java.util.Properties;

public final class Receipt {
    private Receipt() {
    }

    public static String line() throws IOException {
        try (InputStream in =
                     Receipt.class.getResourceAsStream("/catalog.properties")) {
            if (in == null) {
                throw new IOException("Missing catalog.properties");
            }
            Properties props = new Properties();
            props.load(in);

            String item = props.getProperty("item");
            if (item == null || item.isBlank()) {
                throw new IllegalArgumentException("Missing item");
            }
            int price = Integer.parseInt(
                    props.getProperty("unitPriceCents"));
            int quantity = Integer.parseInt(
                    props.getProperty("quantity"));

            return item.strip().toUpperCase(Locale.ROOT)
                    + ":" + PriceMath.subtotal(price, quantity);
        }
    }
}
```

`getResourceAsStream("/catalog.properties")` tìm resource từ **classpath**, không phụ thuộc absolute working directory của Host A/B. `Locale.ROOT` loại bỏ hành vi uppercase phụ thuộc default locale. `Properties.load(InputStream)` đọc file properties theo quy tắc Java, dữ liệu mẫu toàn ASCII nên ổn định.

### 4.7. Main.java: output xác định

File `src/main/java/vn/example/repro/Main.java`:

```java
package vn.example.repro;

import java.io.IOException;

public final class Main {
    private Main() {
    }

    public static String output() throws IOException {
        String receipt = Receipt.line();
        return "receipt=" + receipt
                + "\nverified=" + "BOOK:450".equals(receipt);
    }

    public static void main(String[] args) throws IOException {
        System.out.println(output());
    }
}
```

Sau khi Maven package:

```bash
java -cp target/checksum-compare-lab-1.0.0.jar vn.example.repro.Main
```

**Stdout chính xác từ chương trình**, thể hiện dưới dạng hai dòng:

```text
receipt=BOOK:450
verified=true
```

Trên Windows console, line separator cuối cùng của `System.out.println` có thể là CRLF; đó là **console output ngoài artifact**, không được đưa vào JAR. `Main.output()` lại nối hai dòng nội bộ bằng `\n` một cách tường minh để JUnit assertion nhất quán. Plain JAR này không có cấu hình manifest `Main-Class`; `java -jar` không mặc định chạy được.

### 4.8. PriceMathTest.java — ba tests

File `src/test/java/vn/example/repro/PriceMathTest.java`:

```java
package vn.example.repro;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceMathTest {

    @Test
    void computesSubtotal() {
        assertEquals(450L, PriceMath.subtotal(150, 3));
    }

    @Test
    void zeroQuantity() {
        assertEquals(0L, PriceMath.subtotal(150, 0));
    }

    @Test
    void rejectsNegativeInputs() {
        assertThrows(IllegalArgumentException.class,
                () -> PriceMath.subtotal(-1, 2));
        assertThrows(IllegalArgumentException.class,
                () -> PriceMath.subtotal(1, -2));
    }
}
```

Có **ba** JUnit Jupiter test methods. Tên `*Test` khớp Surefire default patterns; code test đúng business behavior, không có `assertTrue(true)` giả tạo.

### 4.9. ReceiptTest.java — hai tests

File `src/test/java/vn/example/repro/ReceiptTest.java`:

```java
package vn.example.repro;

import java.io.IOException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReceiptTest {

    @Test
    void readsBundledResource() throws IOException {
        assertEquals("BOOK:450", Receipt.line());
    }

    @Test
    void mainOutputContract() throws IOException {
        assertEquals("receipt=BOOK:450\nverified=true",
                Main.output());
    }
}
```

Tổng: `PriceMathTest` 3 + `ReceiptTest` 2 = **5 JUnit methods**. Nếu Surefire reports hiển thị `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`, đó là bằng chứng cụ thể các test methods được thực thi trong build lab. Những tests này tự chúng **không** chứng minh checksum hai host giống nhau; phải chạy bước SHA.

## 5. Baseline trên một môi trường trước khi tách hai host

Khi tạo source lần đầu, chạy từ root:

```bash
java -version
mvn --version
mvn -B --no-transfer-progress clean verify
java -cp target/checksum-compare-lab-1.0.0.jar vn.example.repro.Main
```

Kỳ vọng Maven có **5 tests pass**, build thành công và Java stdout như mục 4.7. Lệnh `clean` loại bỏ output từ build trước; `verify` đi qua compile/test/package. Đừng thêm `-DskipTests` hoặc `-Dmaven.test.skip=true` vào một job muốn chứng minh đúng quality gates.

Kiểm artifact:

```bash
jar tf target/checksum-compare-lab-1.0.0.jar
```

Một số entries quan trọng:

```text
META-INF/MANIFEST.MF
catalog.properties
vn/example/repro/PriceMath.class
vn/example/repro/Receipt.class
vn/example/repro/Main.class
```

Thứ tự hiển thị/entry phụ có thể khác theo plugin; không dùng một `jar tf` screenshot làm chứng cứ byte identity. Nó chỉ xác nhận những thành phần chính có trong artifact.

### 5.1. Một lần build sạch trước tiên phải rõ nguồn

Nếu source đã commit trong Git:

```bash
git rev-parse HEAD
git status --porcelain
```

`git rev-parse HEAD` in commit SHA, ví dụ **một chuỗi 40 hoặc 64 ký tự hex tùy Git object format**. Đừng lấy một SHA ví dụ giả làm revision thật. `git status --porcelain` phải **trống** trước mỗi độc lập build; local modifications hoặc untracked source files có thể ảnh hưởng output mà commit ID không phản ánh.

Sau khi tạo đầy đủ lab, commit `pom.xml`, `src`, `.gitattributes`, `.gitignore` và `scripts` trong repository do bạn quản lý. Với CI thật, hai runners phải checkout **cùng commit SHA được công bố từ đầu**, không dùng tên nhánh `main` mutable rồi hy vọng nó không đổi giữa hai jobs.

## 6. Script chạy build + lưu bằng chứng SHA trên từng host

Để tránh sai lệch cách gõ lệnh ở hai bên, dùng **cùng một script tracked trong Git**. File `scripts/build-and-hash.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f pom.xml ]]; then
  echo "ERROR: run at repository root" >&2
  exit 2
fi
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: source must be a Git checkout" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: checkout must be clean before build" >&2
  exit 2
fi

commit="$(git rev-parse HEAD)"
artifact="checksum-compare-lab-1.0.0.jar"
evidence_dir="${EVIDENCE_DIR:-../checksum-evidence}"

mvn -B --no-transfer-progress clean verify

if [[ ! -s "target/$artifact" ]]; then
  echo "ERROR: expected artifact missing/empty" >&2
  exit 2
fi

mkdir -p "$evidence_dir"
cp "target/$artifact" "$evidence_dir/$artifact"
printf '%s\n' "$commit" > "$evidence_dir/commit.txt"
java -version > "$evidence_dir/java-version.txt" 2>&1
mvn --version > "$evidence_dir/maven-version.txt"

(
  cd "$evidence_dir"
  sha256sum "$artifact" > SHA256SUMS
  sha256sum -c SHA256SUMS
)

echo "Commit: $commit"
echo "Evidence directory: $evidence_dir"
```

**Điều kiện của script:** Bash, Git, Maven 3.9.x, JDK 17, GNU `sha256sum` (Linux; macOS có thể cần GNU coreutils hoặc đổi sang `shasum -a 256`) và repository sạch. `EVIDENCE_DIR` mặc định nằm **ngoài repository root** để không làm dirty checkout; nên đặt một giá trị tuyệt đối, riêng cho từng runner. Script sao chép **artifact bytes** và tạo `SHA256SUMS` trong cùng evidence directory để lệnh `sha256sum -c` có thể xác minh ngay.

Cấu trúc bằng chứng sau khi chạy:

```text
checksum-evidence/
├── checksum-compare-lab-1.0.0.jar
├── SHA256SUMS
├── commit.txt
├── java-version.txt
└── maven-version.txt
```

Đây là **evidence sidecar** không được tự nhúng vào JAR. Nếu nhúng `java-version.txt`/build-time vào archive thì hai máy có thể tạo JAR khác nhau dù source giống hệt.

### 6.1. Tại sao phải có git status --porcelain?

Chỉ `git rev-parse HEAD` không chứng minh working tree giống commit, vì source có thể bị sửa chưa commit hoặc có untracked resource được generator đọc. Script **fail** nếu Git checkout không sạch khi bắt đầu. Lệnh kiểm này không thay thế kiểm external inputs, nhưng loại bỏ một nguồn mismatch phổ biến.

`.gitignore` đã ignore `target/` để build outputs không làm working tree dirty. Evidence đặt ra ngoài repo giúp chạy lại trên clean checkout mà không tạo file `SHA256SUMS` bên trong tracked directory. Nếu team không dùng Git, thay bằng signed source archive digest/provenance tương đương, nhưng phải định nghĩa chính xác nguồn.

### 6.2. Host A thực hiện

Trên **Host A hoặc CI Runner A**, checkout cùng immutable commit đã thống nhất bằng Git, bảo đảm `git status --porcelain` trống, rồi:

```bash
export EVIDENCE_DIR="$HOME/repro-evidence-host-a"
bash scripts/build-and-hash.sh
```

Gói evidence được tạo ở `$HOME/repro-evidence-host-a`. Lưu lại `commit.txt`, `java-version.txt`, `maven-version.txt`, `SHA256SUMS` và JAR dưới dạng CI artifacts **cùng job/build ID**. Không publish một số hash tự gõ mà không kèm artifact tương ứng.

### 6.3. Host B thực hiện

Trên **Host B hoặc CI Runner B**, làm tương tự:

```bash
export EVIDENCE_DIR="$HOME/repro-evidence-host-b"
bash scripts/build-and-hash.sh
```

Hai hosts **không được chia sẻ `target/`** hay một Docker volume đang chứa build outputs của host kia. Mỗi bên tự chạy `mvn clean verify`, không chỉ tải bản JAR A về rồi hash lại dưới tên B. Có thể dùng Maven local dependency repository cache riêng cho mỗi runner; để kiểm mạnh hơn, dùng isolated Maven repository và pin released dependencies.

**Lưu ý trách nhiệm của bài thực hành:** Các lệnh trên **giả định source repository đã được clone trên mỗi host**. Không có URL giả được bịa ra cho một Git remote. Với GitHub/GitLab/CI bất kỳ, người điều phối checkout cùng exact commit trước khi gọi script.

### 6.4. Nếu chỉ có một máy?

Có thể tạo hai clean clones trong hai folders riêng, mỗi clone có `target` riêng, rồi chạy script với EVIDENCE_DIR khác nhau. Đây là **thực hành sơ bộ**, đủ kiểm một số dependency vào path/directory; vẫn chưa là bằng chứng hoàn chỉnh rằng một bên độc lập quản lý môi trường có thể rebuild.

Để thử khác user/path/timezone mà vẫn cùng Java/JDK, dùng hai sandbox containers/VMs đã pin image digest và để JAR/artifact repositories tách biệt. Không tạo ảo giác “independent build” chỉ vì chạy lại cùng JAR từ một `target` đã có.

## 7. So sánh bằng SHA256SUMS trên Linux/macOS

Chuyển hai evidence packages sang một máy so sánh (gọi là **verifier**) qua kênh đáng tin, giữ nguyên tên files và provenance. Sơ đồ:

```text
verifier/
├── host-a/
│   ├── checksum-compare-lab-1.0.0.jar
│   ├── SHA256SUMS
│   ├── commit.txt
│   ├── java-version.txt
│   └── maven-version.txt
└── host-b/
    ├── checksum-compare-lab-1.0.0.jar
    ├── SHA256SUMS
    ├── commit.txt
    ├── java-version.txt
    └── maven-version.txt
```

Từ thư mục `verifier`:

```bash
(cd host-a && sha256sum -c SHA256SUMS)
(cd host-b && sha256sum -c SHA256SUMS)

cmp -s host-a/commit.txt host-b/commit.txt
diff -u host-a/SHA256SUMS host-b/SHA256SUMS

cmp -s \
  host-a/checksum-compare-lab-1.0.0.jar \
  host-b/checksum-compare-lab-1.0.0.jar

echo "Both JAR files are byte-identical."
```

Đây là **chuỗi commands để thực hành**; khi dùng trong CI shell có `set -e` hoặc `set -eu`, lệnh `cmp`/`diff` báo exit nonzero làm job fail và không in thông báo thành công. Nếu chỉ paste commands vào terminal interactive mặc định, terminal có thể vẫn chạy dòng cuối kể cả `cmp` trước đó fail; **đừng lấy dòng echo cuối làm quality gate**. Script chuẩn dùng `set -eu`, điều kiện `if` hoặc kiểm exit statuses.

### 7.1. Script verifier shell có fail thật

Ví dụ file `verify-both.sh` có thể lưu ngoài hai artifacts:

```bash
#!/usr/bin/env sh
set -eu

(
  cd host-a
  sha256sum -c SHA256SUMS
)
(
  cd host-b
  sha256sum -c SHA256SUMS
)

cmp host-a/commit.txt host-b/commit.txt
cmp host-a/SHA256SUMS host-b/SHA256SUMS
cmp host-a/checksum-compare-lab-1.0.0.jar \
    host-b/checksum-compare-lab-1.0.0.jar

echo "PASS: same commit, matching SHA-256, identical JAR bytes"
```

Nếu bất kỳ `cmp` nào thấy mismatch hoặc file thiếu, shell `set -e` kết thúc nonzero. `sha256sum -c` kiểm mỗi artifact đúng digest của manifest nhận được; sau đó `cmp SHA256SUMS` kiểm hai bên báo cùng digest; `cmp JAR` bảo đảm bytes thực tế cũng trùng, không chỉ checksum text.

Nếu muốn thêm provenance gate mạnh, so chính xác `maven-version.txt` và `java-version.txt` của hai bên trong baseline. Trong thử nghiệm cố tình khác OS/vendor, không nên đòi metadata giống nhau vô điều kiện, nhưng **phải lưu và xem chênh lệch**.

### 7.2. Khi chỉ có checksum chứ chưa có JAR B

Có thể kiểm digest text bằng:

```bash
diff -u host-a/SHA256SUMS host-b/SHA256SUMS
```

Nếu giống, đó là bằng chứng **hai bên công bố cùng checksum**, nhưng verifier chưa tự tính lại digest từ bytes của cả hai file. Hãy tải cả hai JAR và chạy `sha256sum -c` trong đúng evidence folders. Không tin một checksum có thể bị sửa trên cùng kênh không xác thực.

### 7.3. Có phải SHA256SUMS luôn cùng nội dung?

`sha256sum` thường ghi dòng:

```text
<64_hex_chars>  checksum-compare-lab-1.0.0.jar
```

Dòng trên là **mô tả format, không phải digest thật**. Bản `SHA256SUMS` từ Host A/B phải dùng **cùng basename** để text compare được. Nếu một bên hash bằng absolute path, bên kia relative path, file manifest có thể khác phần tên dù bytes JAR giống nhau; xử lý bằng hash digest riêng hoặc chuẩn hóa tên artifact trong manifest như script đã làm.

## 8. So sánh trên Windows PowerShell

Nếu Host A/B sử dụng Windows, PowerShell có `Get-FileHash`:

```powershell
$jar = "target\checksum-compare-lab-1.0.0.jar"
$hash = (Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash
"SHA256=$hash"
```

`Get-FileHash` trả digest hex, thường viết **uppercase**. `sha256sum` trên Unix thường cho lowercase. **So sánh digest case-insensitive** khi chuyển giữa hai công cụ; đừng kết luận khác bytes vì khác chữ hoa/chữ thường trong biểu diễn hex.

Một verifier PowerShell có hai JAR đã copy:

```powershell
$a = "host-a\checksum-compare-lab-1.0.0.jar"
$b = "host-b\checksum-compare-lab-1.0.0.jar"

$ha = (Get-FileHash -LiteralPath $a -Algorithm SHA256).Hash
$hb = (Get-FileHash -LiteralPath $b -Algorithm SHA256).Hash

if (-not ($ha -ceq $hb)) {
    throw "FAIL: artifact SHA-256 differs"
}
Write-Output "PASS: two JAR SHA-256 digests match"
```

Vì cả hai digest do cùng cmdlet trả, chữ hoa nhất quán, `-ceq` dùng được. Khi so Windows với Unix hash text, chuẩn hóa `ToLowerInvariant()` hoặc bỏ phân biệt case. Luôn kiểm `commit.txt`/toolchain trước khi gọi đó là independent reproducible build.

**Cẩn thận PowerShell exits:** `throw` làm script/job fail; chỉ `Write-Output` không phải bằng chứng fail/pass nếu lệnh hash trước đó bị exception nhưng bị swallow. Dùng CI PowerShell error handling nghiêm ngặt theo platform, không bỏ exception.

## 9. Python 3 verifier: không phụ thuộc công cụ sha256sum

File `scripts/compare_jars.py` dùng thư viện chuẩn và nhận **hai paths tới file JAR được xây độc lập**:

```python
#!/usr/bin/env python3
import hashlib
import sys
from pathlib import Path

ARTIFACT = "checksum-compare-lab-1.0.0.jar"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()

def resolve_file(argument: str) -> Path:
    p = Path(argument)
    if p.is_dir():
        p = p / ARTIFACT
    if not p.is_file():
        raise SystemExit(f"ERROR: missing artifact: {p}")
    return p

def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: compare_jars.py HOST_A_JAR HOST_B_JAR",
              file=sys.stderr)
        return 2

    a = resolve_file(sys.argv[1])
    b = resolve_file(sys.argv[2])
    hash_a = sha256(a)
    hash_b = sha256(b)
    size_a = a.stat().st_size
    size_b = b.stat().st_size

    print(f"A size={size_a} sha256={hash_a}")
    print(f"B size={size_b} sha256={hash_b}")

    if size_a != size_b or hash_a != hash_b:
        print("FAIL: artifacts are not byte-identical")
        return 1
    print("PASS: matching SHA-256 and file size")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Ví dụ chạy từ thư mục `verifier`:

```bash
python3 scripts/compare_jars.py \
  host-a/checksum-compare-lab-1.0.0.jar \
  host-b/checksum-compare-lab-1.0.0.jar
```

**Đầu ra cuối khi bằng nhau** (hai dòng size/hash trước thay đổi theo artifact thực tế):

```text
PASS: matching SHA-256 and file size
```

Khi khác, script in `FAIL: artifacts are not byte-identical` và exit code **1**; khi thiếu arguments hoặc missing file thì exit code **2**. Dùng mã này như verifier độc lập, **không chạy như Java unit test** và không nhúng kết quả hash vào chính JAR.

Vì script tự tính SHA-256 từ bytes thật, nó phù hợp cả Windows, macOS và Linux khi có Python 3. Tuy nhiên script này không tự kiểm commit/JDK, nên vẫn phải đối chiếu `commit.txt`/provenance trước khi kết luận cross-environment reproducibility.

## 10. Positive control: quy trình đầy đủ ở hai môi trường

Mục tiêu positive control là chứng minh **khi inputs được khóa thì SHA trùng**. Không dùng số đo/digest giả, làm thật:

1. Commit POM, Java source, resources, tests, scripts và `.gitattributes`.
2. Ghi Git commit SHA vào CI job parameters hoặc signed release source manifest.
3. Host A và B checkout **đúng commit SHA**, bảo đảm clean working tree.
4. Mỗi host xác nhận Maven/JDK versions, active profiles và dependency mirrors.
5. Mỗi host chạy `scripts/build-and-hash.sh` từ root của checkout riêng.
6. Thu cả hai folders evidence; không cho A tải JAR của B trước khi build xong.
7. Verifier kiểm mỗi `SHA256SUMS` dựa trên JAR gốc, so `commit.txt`, rồi so hai JAR bằng Python hoặc `cmp`.
8. Nếu tất cả pass, ghi `REPRODUCIBLE=PASS` cho **artifact/version/commit/toolchain matrix đó**.
9. Đính kèm evidence CI: Maven/JDK metadata, exact commit, file size, hashes, job IDs và test reports.
10. Nếu khác, ghi `REPRODUCIBLE=FAIL` và bắt đầu diff, không chọn một digest “đẹp hơn”.

**Không hứa hai JAR nhất định trùng trên mọi hệ điều hành/JDK vendor**. Kết quả mong đợi dựa trên POM/plugin versions và môi trường được kiểm soát, phải đo thực tế để kết luận. Một thay đổi môi trường cố ý chỉ là phép thử bổ sung sau baseline.

### 10.1. Cách kiểm đường dẫn và user không rò vào JAR

Để kiểm robustness, chạy cùng commit trong hai thư mục có tên rất khác:

```text
Host A: /home/builder-a/work/checksum-compare-lab/
Host B: /opt/ci/sandbox/very-different-path/checksum-compare-lab/
```

Đây là **minh họa path layout**, không phải paths bắt buộc tồn tại. Nếu JAR khác SHA, kiểm generated resources/manifest/classfiles có chứa absolute path, username hoặc workdir không. Đừng tự sửa thư mục Host B cho “giống” Host A rồi coi đó là chứng minh độc lập mạnh.

## 11. Negative control: cố ý làm artifact khác và đảm bảo gate bắt được

Một bài tập tốt phải có **negative control**: chứng minh gate fail khi bytes thay đổi, kể cả Java runtime output chưa chắc đổi.

### 11.1. Thử thay đổi nội dung resource

Trong **bản sao/nhánh thực nghiệm** của Host B, đổi:

```properties
item=book
unitPriceCents=150
quantity=4
```

Sau đó `mvn clean verify` sẽ có unit test `ReceiptTest` thất bại vì expected `BOOK:450`, tức test gate đã phát hiện thay đổi về hành vi. Nếu bỏ qua tests thì JAR cũng khác vì `catalog.properties` byte khác; SHA mismatch là chắc chắn.

**Hoàn nguyên** thay đổi trước khi lại thử “cùng commit”. Nếu source Host A/B khác, mismatch **không chứng minh non-determinism**; nó chỉ xác nhận hai inputs khác nhau tạo outputs khác nhau.

### 11.2. Test checksum gate mà không sửa source

Sao chép một artifact vào verifier và thay **một byte** của bản sao (chỉ trong thư mục kiểm thử, không sửa JAR release). Ví dụ script Python sau chạy **trên bản sao `host-b`**:

```python
from pathlib import Path

p = Path("host-b/checksum-compare-lab-1.0.0.jar")
data = bytearray(p.read_bytes())
if not data:
    raise SystemExit("JAR is empty")
data[-1] ^= 1
p.write_bytes(data)
```

Sau khi biến đổi, `sha256sum -c` của Host B và script `compare_jars.py` phải báo **FAIL**. Đây là bài test của **integrity/checksum verifier**, không phải một Maven build hợp lệ: sửa JAR hậu kiểm có thể làm ZIP hỏng. Phải dùng **bản sao disposable**, không sửa artifact thật hoặc bằng chứng đã ký.

### 11.3. Kiểm timestamp issue có chủ đích

Tạm bỏ `project.build.outputTimestamp` trên một nhánh thực nghiệm và build hai lần vào các thời điểm khác nhau. Nếu plugin lấy current ZIP entry timestamps, hashes có thể khác; **nhưng không khẳng định chắc chắn** vì Maven/JAR plugin version có thể có default reproducible timestamp khác. Cách đo đúng là dùng một baseline đã biết, kiểm `jar tvf`, rồi ghi nhận các khác biệt thực tế.

## 12. Khi checksum không khớp: chẩn đoán ở tầng nào?

Một mismatch cần được chia thành các lớp:

```text
SHA(A.jar) != SHA(B.jar)
        |
        +--> Source revision có khác? Dirty/untracked inputs?
        |
        +--> POM/parent/BOM/dependency/plugin versions khác?
        |
        +--> JDK/Maven/OS/env/locale/timezone khác?
        |
        +--> Archive ZIP entries timestamps/order/metadata khác?
        |
        +--> Classfiles khác (compiler, generated code, debug paths)?
        |
        +--> Resources khác (CRLF/LF, filtering, env substitution)?
        |
        +--> Shading/repackaging/signing/tooling khác?
        |
        +--> Artifact bị sửa sau build hoặc lấy nhầm classifier?
```

**Không đổ lỗi cho timestamp ngay từ đầu.** Kiểm evidence/sizes trước, rồi mở archive. Chỉ khi hai builds **cùng commit và được kiểm soát inputs** mà vẫn khác mới là bằng chứng cần điều tra nondeterministic build pipeline.

### 12.1. So files, sizes và archive entries

```bash
ls -l host-a/checksum-compare-lab-1.0.0.jar \
      host-b/checksum-compare-lab-1.0.0.jar

jar tf host-a/checksum-compare-lab-1.0.0.jar > jar-a.list
jar tf host-b/checksum-compare-lab-1.0.0.jar > jar-b.list
diff -u jar-a.list jar-b.list

unzip -l host-a/checksum-compare-lab-1.0.0.jar > jar-a.ziplist
unzip -l host-b/checksum-compare-lab-1.0.0.jar > jar-b.ziplist
diff -u jar-a.ziplist jar-b.ziplist
```

`jar tf` xem entry names; `unzip -l` xem kích thước/timestamps theo hiển thị tool. Các lệnh này giúp khoanh vùng, **không bảo đảm phát hiện mọi khác biệt**: hai archives có cùng filenames/timestamps nhưng khác bytecode, compressed data, file mode hoặc ZIP extra fields vẫn có hash khác.

### 12.2. So manifest và resource thật

```bash
unzip -p host-a/checksum-compare-lab-1.0.0.jar \
  META-INF/MANIFEST.MF > manifest-a.txt
unzip -p host-b/checksum-compare-lab-1.0.0.jar \
  META-INF/MANIFEST.MF > manifest-b.txt
diff -u manifest-a.txt manifest-b.txt

unzip -p host-a/checksum-compare-lab-1.0.0.jar \
  catalog.properties > resource-a.properties
unzip -p host-b/checksum-compare-lab-1.0.0.jar \
  catalog.properties > resource-b.properties
diff -u resource-a.properties resource-b.properties
```

Nếu manifest khác, xem `Build-Jdk-Spec`, `Created-By`, custom build time/user/commit fields. Nếu resource khác chỉ ở CRLF/LF, sửa source normalization/filtering. Không sửa JAR thủ công rồi ký lại; sửa POM/plugin/source để build tự xuất ra deterministic bytes.

### 12.3. Dùng diffoscope khi khác biệt tinh vi

Nếu máy phân tích có `diffoscope`:

```bash
diffoscope \
  host-a/checksum-compare-lab-1.0.0.jar \
  host-b/checksum-compare-lab-1.0.0.jar
```

`diffoscope` có thể đi sâu vào ZIP members, manifests và classfiles để giải thích khác biệt. Nó có thể cần thêm tools/decompilers và có thể xuất rất nhiều output. Bài không cung cấp output giả của diffoscope; cần đọc kết quả thực tế. Tránh công khai build logs có secrets/paths nội bộ mà chưa rà soát.

### 12.4. Nếu .class khác nhưng source giống

Cần đối chiếu `javac -version` và Maven Compiler Plugin args. `--release 17` giới hạn target bytecode/public APIs, nhưng **không đảm bảo bytecode byte-identical khi build bằng JDK major khác** hoặc compiler implementation khác. Để baseline thành công, giữ đúng JDK distribution/vendor/build; chỉ đổi một yếu tố mỗi thí nghiệm.

### 12.5. Nếu archive metadata khác

Maven JAR Plugin và shared archiver cần version hỗ trợ reproducible mode. Kiểm `project.build.outputTimestamp` hiệu dụng, các plugin đóng gói khác (Shade, Assembly, Spring Boot repackage...) có ghi timestamp riêng không, và liệu input order được sort hay phụ thuộc filesystem. Không cố dùng `zip -X` sau khi package như giải pháp duy nhất vì hậu xử lý phá manifest/signature hoặc không được pipeline kiểm.

## 13. Maven Artifact Plugin: kiểm chính thức bên cạnh SHA-256

Apache cung cấp **Maven Artifact Plugin** để chẩn đoán Reproducible Builds. Ba goals đáng biết:

- `artifact:check-buildplan`: kiểm buildplan xem plugins có vấn đề reproducibility đã biết.
- `artifact:compare`: so current build outputs (sau package) với reference đã `install` hoặc artifact từ remote repository; ghi `.buildcompare`.
- `artifact:describe-build-output`: mô tả build outputs, tính năng còn experimental, phù hợp chạy CLI tại reactor root khi cần.

Artifact Plugin **không thay thế bản thân SHA-256 evidence** của hai môi trường. Nó hỗ trợ xác định plugin/update path và so với artifact reference. `artifact:buildinfo` là goal cũ đã deprecated; không nên xây runbook mới lệ thuộc format nội bộ đó.

### 13.1. Kiểm plugin readiness

Từ project lab:

```bash
mvn -B \
  org.apache.maven.plugins:maven-artifact-plugin:3.7.0:check-buildplan
```

Nếu goal báo một plugin chưa hỗ trợ reproducible builds, cần xem recommended plugin version, nâng có kiểm soát và kiểm artifact bytes. “Không có known issue” **không chứng minh** build có SHA giống nhau; phải thực hiện rebuild.

### 13.2. So với local artifact tham chiếu trên cùng máy

Đây là **bài kiểm sơ bộ** (không phải independent two-host proof):

```bash
mvn -B clean install

mvn -B clean verify \
  org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

Lượt đầu `install` artifact reference vào local Maven repo. Lượt hai `verify` build current artifact mà không overwrite reference. `artifact:compare` có thể dùng reference trong local repo và tạo `.buildcompare` ở `target`. Theo Maven Artifact Plugin 3.7.0, tham số `compare.fail` **mặc định true** nên diff có thể làm build fail; goal **không marked thread-safe**, không nên mặc định chạy với `-T`.

Khi so với **reference đã được deploy** ở repository khác, dùng `-Dreference.repo` theo docs của plugin, dạng repository ID hoặc URL; phải có artifact GAV/version ở nguồn đó. Không chạy lab chưa xuất bản với `-Dreference.repo=central` rồi coi 404 là lỗi reproducibility.

### 13.3. So artifact với tham chiếu remote thực sự

Trong release pipeline, Host A có thể publish release candidate artifact lên **staging repository immutable** với GAV/version và checksum/metadata. Host B độc lập checkout cùng source và build, sau đó gọi `artifact:compare` với `reference.repo` trỏ repository ID/URL ấy (credentials qua settings).

**Không đưa repository URL giả của tổ chức vào lệnh runnable của lab.** Cú pháp tham số chính thức:

```text
-Dreference.repo=central
-Dreference.repo=<repository-id>
-Dreference.repo=<repository-url>
-Dreference.repo=<repository-id>::<repository-url>
```

Các dòng chứa dấu ngoặc nhọn chỉ **mô tả các dạng tham số**, không phải lệnh chạy nguyên văn. Tài liệu goal có options `compare.fail`, `compare.aggregate.only`, `buildinfo.skipModules`, `buildinfo.ignoreJavadoc` và `diagnose`. Đừng sử dụng `compare.fail=false` để che mismatch trong quality gate.

### 13.4. Khác biệt compare và SHA manifest

| Vấn đề | SHA256SUMS + byte compare | Maven Artifact Plugin compare |
| --- | --- | --- |
| Dữ liệu so | Bytes của file cụ thể do bạn chọn | Maven project output artifacts/reference theo goal |
| Phụ thuộc Maven | Không cần ở verifier | Có; chạy trong Maven project |
| Nguồn reference | Hai files đã thu từ hosts | Local installed hoặc remote repository |
| Kết quả | SHA text, exit code, file size | Maven log và `.buildcompare` |
| Multi-module | Cần manifest từng artifact/module | Có hỗ trợ aggregate/module config |
| Có chứng minh độc lập không? | Chỉ nếu hai JAR thực sự được build độc lập | Chỉ nếu reference đến từ build độc lập đáng tin |
| Giải thích mismatch | Cần ZIP/diffoscope | Goal cung cấp summary/diagnostics |

Dùng **cả hai** khi xây release assurance: SHA evidence độc lập là contract đơn giản; Artifact Plugin cung cấp Maven-specific diagnostic và kiểm đối chiếu với reference release.

## 14. Checksum, signature và provenance trong software supply chain

Một file `SHA256SUMS` có thể bị thay đổi cùng JAR; checksum chỉ kiểm **tính nhất quán** với digest đã biết. Đối với release chất lượng cao:

1. Chọn immutable Git commit/tag (có thể ký tag theo policy).
2. Pin Maven Wrapper/JDK image, dependency/plugin versions.
3. Build độc lập trên hai trusted runners hoặc có third-party rebuilder.
4. Đính kèm **artifact digest** và thông tin nguồn/build command.
5. Ký checksum/attestation hoặc dùng artifact signing/Sigstore/GPG theo hệ thống phát hành.
6. Verify chữ ký bằng trusted key/identity trước khi tin digest.
7. So artifact bytes; nếu mismatch, fail release.
8. Ghi audit trail của CI jobs, OS/toolchains, input set và validators.

**Digest trùng không nói artifact an toàn**; cả A và B có thể build lại đúng một source chứa bug/malware. Reproducibility giúp tăng khả năng kiểm tra mối liên hệ source↔binary, không thay thế code review/SAST/dependency scanning/integration tests.

### 14.1. Tránh nhúng bằng chứng động vào JAR

Nếu CI sau build sinh:

```text
build-id.txt
runner-hostname.txt
current-time.txt
sha256-of-current-jar.txt
```

rồi cho chúng vào JAR, bạn tạo vòng phụ thuộc hoặc non-determinism. Đặc biệt **không thể tự chứa SHA-256 của toàn bộ JAR trong chính JAR đó theo cách đơn giản** mà vẫn giữ một checksum bất biến. Lưu evidence ngoài artifact (sidecar) hoặc dùng hệ thống provenance/signing phù hợp.

### 14.2. Cùng artifact name chưa đủ

Ví dụ `checksum-compare-lab-1.0.0.jar` trên A và B có thể cùng tên nhưng khác commit hoặc Maven profile. Vì vậy verifier phải kiểm:

- Maven GAV: `vn.example:checksum-compare-lab:1.0.0:jar`.
- Commit SHA giống nhau.
- Repo dirty/untracked state đã kiểm.
- Compiler/JDK/Maven/plugin versions.
- Command, profiles/test flags.
- Số tests được chạy và pass.
- File bytes + digest, không chỉ tên.

## 15. Multi-module và attached artifacts

Trong reactor:

```text
root/
├── pom.xml       # packaging pom
├── core/target/core-1.0.0.jar
├── app/target/app-1.0.0.jar
└── docs/target/docs-1.0.0.jar
```

Không chỉ hash `app` rồi tuyên bố “cả reactor reproducible”. Một build có thể có các outputs:

- Parent POM effective/published POM.
- Binary JAR theo từng module.
- Sources JAR/Javadoc JAR (attached artifacts).
- Shaded/assembly ZIP/TAR, boot executable JAR.
- Maven metadata, BOM, generated sources, SBOM hoặc native binaries.
- Chữ ký và checksum sidecars tạo sau build.

Với release scope rõ, lập **manifest sorted theo artifact coordinates/classifier/filename** rồi compute digest từng file. Sorting inputs giúp manifest deterministic; nếu dùng `find`/`sort`, đặt `LC_ALL=C` khi cần. Một module không xuất JAR (POM packaging) không bị coi là lỗi chỉ vì không có `target/*.jar`; policy xác định artifact type riêng.

### 15.1. Vì sao hash tất cả target/*.jar đôi khi sai?

Có thể có `original-...jar` do Shade Plugin, test-jar, sources/javadoc và JAR tạm. Nếu chỉ chạy glob `target/*.jar` mà không hiểu classifier, có nguy cơ:

- So artifact không được publish.
- Bỏ attached artifacts ở thư mục khác.
- Dùng file JAR trước repackage thay vì final artifact.
- Lẫn output từ build trước nếu không `clean`.

Giải pháp: lấy artifact set từ Maven release/publishing plan, hoặc đặt danh sách paths tường minh với stable GAV/classifier. Ví dụ bài lab intentionally chỉ có **một main JAR** để không làm rối bước kiểm cơ bản.

## 16. CI pipeline: hai jobs xây riêng, job thứ ba kiểm SHA

Một workflow tổng quát:

```text
Immutable Git commit
      |
      +--> Job A: Linux runner A / JDK17 / Maven3.9
      |       clean verify -> JAR_A + SHA256SUMS_A + provenance_A
      |
      +--> Job B: Linux runner B / JDK17 / Maven3.9
              clean verify -> JAR_B + SHA256SUMS_B + provenance_B
                        |
                        v
                 Verifier job
                 check exact commit
                 check JDK/Maven matrix
                 verify each SHA256SUMS against JAR
                 compare SHA256SUMS / bytes
                        |
          +-------------+-------------+
          |                           |
      SAME SHA                    DIFFERENT SHA
          |                           |
      gate PASS                 gate FAIL + diffoscope
          |                           |
     eligible for later QA      block release, investigate
```

Các CI providers khác nhau ở cách download/upload artifacts, cấu hình runners/permissions và job dependencies. Sơ đồ không ngụ ý tất cả CI systems mặc định có isolated jobs. **Cần cấu hình thật** để mỗi runner checkout source riêng, không share `target` và không dùng reused build output làm “independent artifact”.

### 16.1. Shell fragment cho mỗi build job

```bash
#!/usr/bin/env sh
set -eu

java -version
mvn --version

mvn -B --no-transfer-progress clean verify
test -s target/checksum-compare-lab-1.0.0.jar

sha256sum target/checksum-compare-lab-1.0.0.jar
```

Đây là **fragment của CI job đã checkout source**, không thay script evidence đầy đủ ở mục 6. Trong release pipeline, nên lưu Surefire reports dù build fail, đánh giá Maven exit code, và chặn build có `-DskipTests`. Job verifier phải phụ thuộc **cả hai jobs build thành công**, không chạy chỉ vì job A pass.

### 16.2. Dùng Maven Wrapper đúng vai trò

Nếu repository có Maven Wrapper:

```bash
./mvnw -B --no-transfer-progress clean verify
```

Wrapper giúp cố định Maven distribution nhưng **không tự cài hoặc pin JDK distribution**. Nếu dùng Wrapper trong CI, cả script build và policy phải dùng nó nhất quán; không để Host A gọi `mvn` hệ thống và Host B gọi `./mvnw` trừ khi đã đối chiếu versions tương đương.

### 16.3. Dependency/mirror caches có làm mất tính độc lập?

Maven local repository cache chứa dependencies/plugins đã download; dùng cùng **released, immutable artifact bytes** không vi phạm logic build độc lập. Nhưng khi hai jobs dùng **một shared target/** hoặc tải **JAR_A làm output thay vì compile**, đó không còn là independent rebuild. Với dependency versions mutable/compromised hoặc SNAPSHOT thay đổi giữa jobs, cache có thể làm kết quả không đáng tin; pin versions và nguồn artifacts, dùng mirrors có checksum/signature policy, cân nhắc isolated repository trong challenge độc lập.

### 16.4. Quota/tài nguyên, không ép hai job chạy song song

Hai build jobs có thể chạy cùng lúc hoặc lần lượt. “Độc lập” đề cập **nguồn/cách build**, không yêu cầu hai CPU thực thi đúng cùng một thời điểm. Tối ưu concurrency không nên làm mất reproducibility hoặc tạo file contention. Nếu chạy trong một build matrix, kiểm OS/JDK/command per job theo cấu hình thực tế.

## 17. Các lỗi chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Hai JAR có cùng tên nhưng SHA khác | Tên không chứng minh bytes | Kiểm commit, source, POM, digest, archive diff |
| SHA khác chỉ vì thời điểm build | ZIP entry timestamps | `project.build.outputTimestamp`, plugin versions |
| SHA khác Windows vs Linux | CRLF/LF resources, OS-specific metadata | `.gitattributes`, resource encoding/packaging |
| SHA khác giữa JDK 17 và JDK 21 | Bytecode/manifest/toolchain | Giữ same JDK ở baseline |
| SHA khác giữa username/path | Generated code/resources chèn absolute path | Loại env leakage, normalize paths |
| SHA khác sau version range resolve | Dependency drift | Pin versions/BOM/plugin repos |
| Build A và B pass, tests 0 | Skip flags, Surefire discovery sai | XML test gate, failIfNoTests, clean verify |
| Maven Artifact Plugin báo 404 reference | GAV/version chưa có trong reference repo | Publish staging immutably hoặc dùng local preliminary test |
| artifact:compare báo mismatch | Artifacts bytes khác hoặc artifact set khác | Đọc `.buildcompare` và diffoscope |
| artifact:compare + `-T` warning | Goal không marked thread-safe | Chạy compare tuần tự |
| SHA text khác do chữ hoa | PowerShell uppercase, sha256sum lowercase | Chuẩn hóa lowercase |
| SHA manifest khác vì absolute filename | Hash file cùng bytes, path label khác | Dùng basename ổn định |
| Verifier chỉ so file checksum text | Attacker có thể sửa cả JAR + manifest | Verify bytes và signed provenance |
| Two builds cùng shared target | Thực tế không độc lập | Isolated checkouts, output dirs |
| Test negative thay source và JAR hash khác | Inputs đã khác, không phải nondeterminism | Hoàn nguyên, so cùng commit |
| Files trong JAR cùng tên nhưng digest khác | Content/metadata/compression/order khác | manifest/resource/class/ZIP diff |
| JAR matches nhưng app test fail | Hash identity không chứng minh correctness | Chạy tests/quality gates độc lập |
| Dùng hash folder target | Log/report/timestamp khác | Hash final artifacts theo release inventory |
| SHA trùng nhưng versions khác | Có thể trùng bytes tình cờ; provenance lệch | Không bỏ qua mismatch source/build identity |

## 18. Một quy trình chẩn đoán có thể lặp lại

1. Ghi lại hai full file digests và file sizes, không làm tròn digest.
2. Kiểm `git rev-parse HEAD`, `git status --porcelain` và source checkout identity của A/B.
3. Kiểm Java/Maven versions, `JAVA_HOME`, Maven Wrapper, profiles, environment flags.
4. Kiểm POM, parent, BOM, plugin/dependency versions và Maven repositories.
5. Confirm cả hai chạy `mvn -B clean verify` và Surefire tests pass.
6. Xem `project.build.outputTimestamp` effective và các plugin hỗ trợ.
7. So `jar tf` entries, `unzip -l` metadata và `MANIFEST.MF`.
8. So resource bytes, line endings và generated resources.
9. So `.class` files/bytecode nếu ZIP entries tương tự mà hash khác.
10. Dùng `diffoscope` cho archive-level diagnostics.
11. Dùng Maven Artifact Plugin `check-buildplan` để phát hiện plugins có known reproducibility issues.
12. Chạy `artifact:compare` với reference đáng tin (local preliminary hoặc remote independent reference).
13. Sửa source/POM/build toolchain, không hậu sửa binary để che mismatch.
14. Build lại từ source sạch trên **cả hai môi trường**.
15. Lưu manifests/provenance của cả hai invocations và exit codes.
16. Chỉ đánh dấu PASS khi source identity, tests, artifact inventory và SHA equality đều được xác nhận.

## 19. Bài tập và đáp án

**Câu 1.** Hai build tạo cùng stdout `receipt=BOOK:450`, có chứng minh JAR identical không?

**Đáp án:** Không. Java behavior tương đương không bảo đảm ZIP entry timestamps, manifest và archive bytes trùng.

**Câu 2.** Vì sao hai lần build trên cùng máy chưa phải independent rebuild mạnh?

**Đáp án:** Chúng có thể chia sẻ username, path, JDK, Maven repo, cache và hidden state; cần một môi trường tách biệt hoặc bên thứ ba.

**Câu 3.** SHA-256 khác nhau cho cùng filename nói lên điều gì?

**Đáp án:** File bytes chắc chắn khác (giả sử digest được tính đúng từ files), nhưng nguyên nhân có thể là source/môi trường khác hoặc nondeterministic output.

**Câu 4.** `project.build.outputTimestamp` giải quyết tất cả nondeterminism không?

**Đáp án:** Không. Nó giúp archive plugins hỗ trợ dùng stable timestamp; không sửa random, JDK khác, generated sources, dependency drift hay plugin khác.

**Câu 5.** Tại sao phải so cùng Git commit SHA và kiểm working tree sạch?

**Đáp án:** Nếu inputs khác, checksum mismatch là điều bình thường; không thể gọi đó là bằng chứng reproducibility failure.

**Câu 6.** Host A dùng JDK17, Host B dùng JDK21. SHA khác có lạ không?

**Đáp án:** Không. Java major có thể đổi bytecode/manifest. Baseline hãy cố định cùng compiler toolchain.

**Câu 7.** `sha256sum` và `Get-FileHash` in chữ hex khác case, có nghĩa bytes khác?

**Đáp án:** Không. Digest bytes giống có thể được định dạng uppercase/lowercase. Chuẩn hóa representation.

**Câu 8.** Vì sao nên kèm JAR với `SHA256SUMS`?

**Đáp án:** Để verifier tính lại digest từ bytes thật. Một chuỗi SHA trong log hoặc email chưa chứng minh file cụ thể đã kiểm.

**Câu 9.** Hai files có cùng checksum, có đủ để tuyên bố source đáng tin không?

**Đáp án:** Không. Cần xác nhận source commit, provenance/signatures và trust của publisher; checksum không là chữ ký.

**Câu 10.** Maven Artifact Plugin `artifact:compare` có thể thay hai-host proof không?

**Đáp án:** Không tự động. Nó chỉ dùng reference artifacts; nếu reference là local install cùng máy thì vẫn chưa chứng minh độc lập.

**Câu 11.** Dùng `mvn -T 4 ... artifact:compare` có an toàn mặc định không?

**Đáp án:** Không nên; Artifact Plugin compare goal không marked thread-safe. Chạy so sánh tuần tự.

**Câu 12.** Khi JAR hashes khác, nên sửa ZIP timestamp thủ công sau build để PASS?

**Đáp án:** Không. Sửa build configuration/plugins để phát hành artifact deterministic trực tiếp và kiểm lại từ source.

**Câu 13.** Multi-module có 5 JAR nhưng chỉ hash 1 JAR; đã chứng minh full reactor reproducible chưa?

**Đáp án:** Chưa. Cần inventory và manifest cho mọi artifact thực sự phát hành.

**Câu 14.** Bản checksum được ký sau build có nhất thiết byte-identical giữa signer A và B?

**Đáp án:** Không. Signatures có entropy/timestamp/identity; policy thường kiểm binary artifact trước ký, và ký evidence theo quy trình riêng.

**Câu 15.** Hai CI jobs tải cùng JAR do một job đã compile rồi chỉ hash lại có phải independent builds?

**Đáp án:** Không. Đó là hai lần kiểm tính toàn vẹn của **một** artifact, không phải hai rebuild từ source.

## 20. Checklist nghiệm thu thực hành

- [ ] Project Java 17 có POM/Java/tests/resources/scripts được commit.
- [ ] `project.build.outputTimestamp` có giá trị stable và JAR Plugin hỗ trợ.
- [ ] Compiler/Resources/JAR/Surefire/Artifact Plugin versions được pin.
- [ ] Same immutable Git commit ở Host A và B; working trees sạch.
- [ ] Hai machines/CI runners có filesystem/`target` độc lập.
- [ ] Cùng Maven/JDK distribution/versions và build command ở baseline.
- [ ] Không có dependency version ranges/SNAPSHOT động/hidden inputs chưa kiểm.
- [ ] Resources text dùng LF theo `.gitattributes` và UTF-8 policy.
- [ ] `mvn -B clean verify` pass trên cả hai hosts, **5 JUnit tests executed**.
- [ ] Main JAR tồn tại, Java main in `receipt=BOOK:450` và `verified=true`.
- [ ] Từng host xuất JAR, SHA256SUMS, Git commit và toolchain provenance.
- [ ] Verifier chạy `sha256sum -c` trên **cả hai** evidence packages.
- [ ] Verifier xác nhận exact commit và artifact GAV/filename đúng.
- [ ] SHA-256 digests trùng và (nếu có cả JARs) byte compare trùng.
- [ ] Negative control thay một byte JAR bản sao làm gate FAIL.
- [ ] `artifact:check-buildplan` và `artifact:compare` được dùng khi cần diagnostic/reference.
- [ ] Khi mismatch, lưu evidence, diff ZIP/manifest/resources/classfiles, không sửa binary hậu kiểm.
- [ ] Multi-module/release artifacts có inventory và manifest riêng cho đầy đủ outputs.
- [ ] SHA manifests/provenance được lưu ở sidecar, tránh nhúng dữ liệu động vào JAR.
- [ ] Release gate chỉ PASS khi source, tests, provenance, artifact hash đều đạt policy.

## 21. Tài liệu chính thức

- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven Artifact Plugin — Goals](https://maven.apache.org/plugins/maven-artifact-plugin/plugin-info.html)
- [Apache Maven Artifact Plugin — compare Goal](https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html)
- [Apache Maven Artifact Plugin — Usage](https://maven.apache.org/plugins/maven-artifact-plugin/usage.html)
- [Apache Maven JAR Plugin — jar Goal](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Reproducible Builds — SOURCE_DATE_EPOCH specification](https://reproducible-builds.org/specs/source-date-epoch/)
- [Reproducible Builds — Timestamps](https://reproducible-builds.org/docs/timestamps/)
- [Reproducible Builds — Stable Inputs](https://reproducible-builds.org/docs/stable-inputs/)
- [Reproducible Builds — JVM](https://reproducible-builds.org/docs/jvm/)
- [Diffoscope](https://diffoscope.org/)
