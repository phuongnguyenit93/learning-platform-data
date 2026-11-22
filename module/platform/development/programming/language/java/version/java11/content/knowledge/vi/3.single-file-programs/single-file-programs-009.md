# Java 11 — Khi chuyển từ một tệp sang dự án build có kiểm thử

**Chủ đề:** Java 11 → Chương trình một tệp. Bài này hướng dẫn quyết định *khi nào* nên rời cách chạy `java Hello.java`, *chuyển thế nào* sang cấu trúc dự án có build tool và *chứng minh kết quả* bằng unit test và một quy trình build lặp lại được. Chỉ sử dụng các kiến thức còn áp dụng hiện nay. Mã Java giữ tương thích **JDK 11**; version của công cụ build/test là ví dụ tương thích, cần kiểm tra lại khi nâng cấp dependency.

## 1. Một tệp Java 11 giải quyết vấn đề gì?

Từ Java 11, source-file mode cho phép chạy thẳng chương trình đơn giản:

~~~java
// Hello.java
public class Hello {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0].strip() : "bạn";
        if (name.isBlank()) {
            name = "bạn";
        }
        System.out.println("Xin chào, " + name + "!");
    }
}
~~~

~~~bash
java Hello.java Linh
~~~

Stdout:

~~~text
Xin chào, Linh!
~~~

`java Hello.java` dùng Java launcher biên dịch trong bộ nhớ rồi chạy chương trình, nên không cần thao tác `javac Hello.java` riêng. Tính năng single-file source launch có từ **Java 11**, rất phù hợp cho học tập, thử ý tưởng, script nhỏ và demo không có nhiều phụ thuộc. Không dùng những mở rộng source launcher xuất hiện sau JDK 11 để suy luận về khả năng biên dịch nhiều tệp trong Java 11. Khi tách thành nhiều tệp/class độc lập, cách vận hành và kiểm thử nên đi qua build chuẩn.

**Dấu hiệu nên chuyển thành dự án:**

- Logic cần dùng lại hoặc đã có nhiều class/package; `main` bắt đầu vừa parse input, vừa tính toán và vừa thao tác file/network.
- Cần **dependency bên thứ ba** và kiểm soát phiên bản; chạy thủ công từng JAR/classpath trở nên khó kiểm soát.
- Cần **unit test**, test trên CI, báo cáo lỗi/coverage, kiểm tra chất lượng hoặc review thay đổi.
- Nhiều người cùng phát triển; cần cấu trúc quen thuộc, lệnh build thống nhất và cơ chế tái hiện lỗi.
- Cần đóng gói, phát hành, quản lý cấu hình theo môi trường và xử lý tài nguyên.

**Không phải cứ có một tệp là phải tạo Maven/Gradle:** thử nghiệm không dependency, ngắn hạn, không cần test tự động vẫn hợp với source-file mode. Chọn độ phức tạp vừa đủ, nhưng khi dự án tăng trưởng nên chuyển sớm để tránh code khó test.

## 2. Điều gì thay đổi khi có build project?

| Khía cạnh | Một tệp | Dự án có build và test |
| --- | --- | --- |
| Chạy | `java Hello.java` | Compile qua Maven/Gradle, chạy main class hoặc artifact phù hợp. |
| Tổ chức | Class chính nằm trong một file; logic thường dồn vào `main`. | Phân biệt source, tests, resources, package; phân tách entry point và nghiệp vụ. |
| Dependency | Không có hoặc tự quản lý classpath. | Dependency tọa độ/phiên bản, scope và phụ thuộc bắc cầu do build tool quản lý. |
| Test | Thử tay với một vài input/output. | JUnit test nhiều trường hợp, chạy lặp lại tự động trong local/CI. |
| Build output | Launcher chạy mã nguồn trực tiếp. | Bytecode, test reports và artifact được tạo dưới thư mục build. |
| Khả năng tái lập | Phụ thuộc lệnh từng người và JDK đang dùng. | Version JDK, plugin/dependency và wrapper được xác định rõ. |

**Maven** phù hợp khi muốn cấu trúc theo quy ước, POM khai báo tường minh và vòng đời build quen thuộc. **Gradle** phù hợp khi cần build script linh hoạt, toolchains và cấu hình nhiều module; cần chú ý phiên bản JVM chạy chính Gradle khác với Java version của mã nguồn. Chọn một build tool chính, tránh duy trì hai mô tả build song song khi không có lý do cụ thể.

Trong ví dụ dưới đây, dùng Maven để chạy được toàn bộ với môi trường **JDK 11**. Phần Gradle ở cuối chỉ ra lựa chọn tương đương và điểm tương thích phiên bản.

## 3. Giữ hợp đồng hành vi trước khi di chuyển

Trước khi tách file, ghi ra ít nhất:

1. **Đầu vào:** args, stdin, biến môi trường, tệp hoặc HTTP; kiểu và giá trị mặc định.
2. **Đầu ra:** stdout/stderr, tệp, kết quả trả về; những dòng có ý nghĩa ổn định.
3. **Tác động phụ:** kết nối, ghi file, cập nhật dữ liệu, gọi hệ thống ngoài.
4. **Lỗi:** input không hợp lệ, exception, mã thoát, thông điệp có thể kiểm tra.
5. **Môi trường:** JDK version, encoding, timezone, working directory, dependency.

Ví dụ trên có hợp đồng quan sát được: `java Hello.java Linh` in `Xin chào, Linh!`; chạy không có đối số in `Xin chào, bạn!`; input chỉ toàn khoảng trắng cũng cho tên mặc định. Khi chuyển thành dự án, hãy giữ nguyên các hành vi đó; chỉ thay cấu trúc, lệnh build và cách kiểm chứng.

Một kỹ thuật quan trọng là **tách logic thuần (pure logic) khỏi I/O**. `main` chỉ đọc tham số và in kết quả; một class khác nhận đầu vào và trả về giá trị. Điều này làm unit test nhanh, ổn định, không cần mock console/hệ thống file để kiểm tra từng quy tắc.

## 4. Cấu trúc dự án Java chuẩn

Tạo một dự án Maven tên `greeting-app`:

~~~text
greeting-app/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
├── src/
│   ├── main/
│   │   ├── java/com/example/
│   │   │   ├── App.java
│   │   │   └── Greeting.java
│   │   └── resources/
│   └── test/
│       ├── java/com/example/GreetingTest.java
│       └── resources/
└── .gitignore
~~~

Các tệp wrapper `mvnw`, `mvnw.cmd` và `.mvn/wrapper/...` chỉ xuất hiện sau khi sinh wrapper; thư mục `resources` có thể để trống và không bắt buộc tạo nếu chưa dùng.

- `src/main/java` chứa mã nguồn sản phẩm.
- `src/test/java` chứa mã kiểm thử, thường theo package tương ứng.
- `src/main/resources` và `src/test/resources` chứa file cấu hình/fixture nếu cần.
- `pom.xml` là mô tả tọa độ dự án, dependencies, plugins, version compile/test.
- `target/` do Maven tự tạo sau build; **không commit** output, class đã compile và báo cáo test.
- Với package `com.example`, thư mục và câu lệnh `package com.example;` phải khớp nhau theo quy ước, và chạy bằng fully qualified class name `com.example.App`.

Tên package trong ví dụ chỉ để minh họa; khi dùng sản phẩm thật, chọn namespace phù hợp tổ chức.

## 5. Mẫu Maven + JUnit chạy được trên Java 11

Ví dụ sau dùng **Maven Compiler Plugin 3.16.0**, **Maven Surefire 3.6.1** và **JUnit Jupiter 5.14.4**. Đây là những phiên bản được chọn cho môi trường Java 11 tại thời điểm xây bài; khi nâng cấp nên đọc release notes/requirements thay vì thay bằng major mới nhất một cách máy móc. **JUnit 6 yêu cầu Java 17+**, nên không dùng trực tiếp cho test chạy bằng Java 11. Plugin Maven Compiler 4.x dành cho hệ Maven/JDK mới hơn; nhánh 3.x phù hợp ví dụ này.

### 5.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>greeting-app</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>11</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.14.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.14.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- `groupId` + `artifactId` + `version` định danh artifact Maven.
- `maven.compiler.release=11` dùng cơ chế compiler `--release 11` khi chạy javac phù hợp: giới hạn cú pháp **và API Java SE** theo target, tốt hơn chỉ đặt `source`/`target`. Dùng JDK 11 để compile và chạy cũng giúp tránh lệch môi trường. Nếu dùng JDK mới hơn, `--release 11` **không đảm bảo mọi dependency có bytecode tương thích Java 11**; phải kiểm tra chúng.
- `project.build.sourceEncoding=UTF-8` giúp source tiếng Việt được đọc nhất quán.
- Dependency `junit-jupiter` chỉ thuộc scope `test`: không đi vào classpath runtime chính của ứng dụng. Nó gồm API và test engine qua dependencies cần thiết.
- Plugin `maven-surefire-plugin` chạy unit test trong giai đoạn `test`. Với tên `GreetingTest.java`, test sẽ được phát hiện theo quy ước; không cần chạy từng class bằng tay.

**Lưu ý version:** ví dụ giữ dependency và plugin cụ thể để dễ tái hiện. Sau này muốn cập nhật cần kiểm tra Java minimum, BOM/transitive dependencies, lỗ hổng bảo mật và CI trước khi đổi version. Đừng dùng version range không kiểm soát cho dự án cần build lặp lại.

### 5.2. `src/main/java/com/example/Greeting.java`

~~~java
package com.example;

public final class Greeting {
    private Greeting() {
        // Utility class: không cần tạo instance.
    }

    public static String greet(String rawName) {
        String name = rawName == null ? "" : rawName.strip();
        if (name.isBlank()) {
            name = "bạn";
        }
        return "Xin chào, " + name + "!";
    }
}
~~~

`strip()` và `isBlank()` có trong Java 11; không dùng `record`, text blocks, switch expressions hay API chỉ xuất hiện ở JDK cao hơn. `greet` không có I/O, không đọc biến môi trường hoặc thời gian, nên dễ test với input cố định.

### 5.3. `src/main/java/com/example/App.java`

~~~java
package com.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String rawName = args.length > 0 ? args[0] : null;
        System.out.println(Greeting.greet(rawName));
    }
}
~~~

`main` là entry point, giữ thật mỏng. Nếu ứng dụng lớn lên, tách thêm services, repositories, HTTP clients và configuration qua dependency injection hợp lý; chưa cần framework chỉ để chạy một phép tính.

### 5.4. `src/test/java/com/example/GreetingTest.java`

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {

    @Test
    void trimsName() {
        assertEquals("Xin chào, Linh!",
                Greeting.greet("  Linh  "));
    }

    @Test
    void usesDefaultWhenBlank() {
        assertEquals("Xin chào, bạn!",
                Greeting.greet(" \t "));
    }

    @Test
    void usesDefaultWhenNull() {
        assertEquals("Xin chào, bạn!",
                Greeting.greet(null));
    }
}
~~~

Test dùng JUnit Jupiter `@Test` và `assertEquals`. Tên test mô tả hành vi thay vì mô tả từng dòng code. Kiểm thử cả **đường chính** và **biên**; không nên chỉ test “happy path” có input đầy đủ. Không tạo `main` riêng để tự gọi test và in “PASS”, vì cách đó không tích hợp đúng discovery/reporting/CI.

### 5.5. Lệnh build và chạy

Chuẩn bị **JDK 11** và **Maven 3.6.3+ phiên bản tương thích**, kết nối Maven Central cho lần lấy dependency đầu tiên:

~~~bash
java -version
javac -version
mvn -version
mvn test
mvn package
java -cp target/classes com.example.App Linh
~~~

Khi chạy lệnh cuối, **stdout chính xác**:

~~~text
Xin chào, Linh!
~~~

`mvn test` compile mã chính + mã test rồi chạy 3 unit tests; báo cáo surefire sẽ thể hiện **3 tests, 0 failures, 0 errors, 0 skipped** nếu không có thay đổi và môi trường thiết lập đúng. Log Maven không có stdout cố định vì phụ thuộc phiên bản/cấu hình build. `mvn package` gồm các phase trước đó, vì vậy mặc định cũng chạy test trước khi đóng gói.

**Phân biệt chạy class và JAR:** Maven `package` mặc định có thể sinh `target/greeting-app-1.0.0-SNAPSHOT.jar`, nhưng `java -jar ...` chỉ chạy được nếu manifest có `Main-Class` đúng (và application không thiếu dependency runtime). Trong ví dụ đơn giản, lệnh `java -cp target/classes com.example.App Linh` là đầy đủ. Nếu cần artifact chạy trực tiếp hoặc phân phối, cấu hình JAR manifest/plugin và chiến lược đóng gói dependencies phù hợp; không giả định mọi JAR tự thực thi.

**Maven Wrapper:** sau khi bootstrap từ Maven đã cài, chạy `mvn wrapper:wrapper` để tạo wrapper theo plugin phù hợp rồi **commit các tệp wrapper**. Đồng đội/CI dùng `./mvnw test` trên Unix/macOS hoặc `mvnw.cmd test` trên Windows, thay vì phụ thuộc một bản Maven cài ngẫu nhiên toàn máy. Wrapper không thay thế nhu cầu có JDK tương thích; cấu hình version của wrapper cũng cần được quản lý và cập nhật bảo mật.

## 6. Kiểm thử có ích: hành vi, trường hợp biên, tích hợp

**Unit test** nên tập trung vào điều kiện nhỏ, ổn định, chạy nhanh và độc lập với mạng, giờ hệ thống hoặc thứ tự chạy. Với chương trình một file đang chứa tất cả logic trong `main`, bước quan trọng nhất là **refactor phần tính toán ra method/class có tham số và giá trị trả về**. Sau đó viết test trước cho các trường hợp đã cam kết; chỉ đổi code tổ chức, kiểm tra không thay hành vi.

**Test có giá trị** thường gồm:

- Trường hợp hợp lệ: input thường, Unicode/tiếng Việt, dữ liệu dài nhưng nằm trong giới hạn.
- Biên: null, rỗng, whitespace, số 0, giá trị âm, mảng không có phần tử, giới hạn độ dài.
- Lỗi: invalid arguments, parse thất bại, exception đúng loại, thông báo phù hợp.
- Kiểm chứng tác động: gọi dependency đúng số lần, tài nguyên được đóng, không có ghi trùng khi retry.
- Kiểm chứng integration khi có DB/HTTP/file: dùng fixture/tài nguyên kiểm soát được, cấu hình riêng, cleanup và thời gian chờ có giới hạn.

JUnit Jupiter còn hỗ trợ `@BeforeEach`, `@AfterEach`, `@ParameterizedTest`, `assertThrows` và `@TempDir` khi phù hợp; không cần đưa tất cả vào một bài test mẫu. Ưu tiên test **đầu ra/contract**, không trói test vào cách triển khai nội bộ. Một bài test chỉ mô phỏng lại đúng thuật toán của code mà không kiểm tra hành vi dễ tạo cảm giác an toàn giả.

Khi dependency ngoài được thêm vào, dùng mock/fake tại interface đã kiểm soát cho unit test; test integration riêng có thể dùng embedded service/test container khi môi trường và dependency cho phép. Không gọi API Internet thật tùy ý trong unit test vì flaky, chậm, khó tái hiện và có thể tạo side effects.

**TDD khi thích hợp:** viết một test thất bại có nghĩa, triển khai vừa đủ để pass, sau đó refactor. Với quá trình chuyển một file cũ, “characterization tests” trước khi refactor giúp đóng băng hành vi đang có, kể cả các trường hợp đặc biệt.

**Phân chia unit và integration tests trong Maven:** Surefire thường dùng cho unit tests ở phase `test`. Nếu cần integration test có setup/teardown bên ngoài, xem Maven Failsafe Plugin ở phases `integration-test` và `verify`; nó **không tự được cài** bởi POM ở trên. Không hiểu sai rằng chạy `mvn verify` tự tìm mọi integration test khi chưa cấu hình plugin/phân loại chúng.

## 7. Build lifecycle, tính tái lập và quản lý dependency

Các lệnh cần hiểu:

| Lệnh | Tác dụng |
| --- | --- |
| `mvn compile` | Biên dịch source của ứng dụng. |
| `mvn test` | Biên dịch và chạy unit test qua Surefire. |
| `mvn package` | Chạy các phase trước rồi đóng gói artifact. |
| `mvn verify` | Chạy đến phase kiểm chứng, bao gồm plugin/check có cấu hình ở phase đó. |
| `mvn clean verify` | Xóa output cũ rồi build/test/verify từ đầu để phát hiện lỗi build chỉ thành công nhờ file cũ. |
| `mvn -Dtest=GreetingTest test` | Chạy riêng class test phù hợp trong giai đoạn phát triển. |

Maven lưu dependency vào local cache (`~/.m2/repository` theo cấu hình thông thường); build lần đầu có thể cần mạng. Chỉ kiểm soát version trong POM **chưa đủ** bảo đảm build byte-for-byte giống nhau: cần ổn định JDK/toolchain, OS khi tác động kết quả, plugin, repository, biến môi trường, timestamp, resource ordering và nguồn artifact.

Đối với CI hoặc nhóm phát triển:

1. Commit source, tests, POM, wrapper và cấu hình cần thiết; không commit `target/`, cache hoặc secret.
2. Xác định JDK build/test (ví dụ JDK 11 cho dự án này); trong CI kiểm tra `java -version` và Maven version.
3. Chạy `./mvnw --batch-mode --no-transfer-progress clean verify` hoặc `mvnw.cmd ...` tương đương trên Windows.
4. Lưu test results/artifact khi build pass; fail pipeline nếu test fail. Xem báo cáo `target/surefire-reports/` nếu có lỗi.
5. Dùng dependency scanning, cập nhật định kỳ và kiểm soát nguồn artifact; không lưu credentials trong POM hoặc repository.

`.gitignore` tối thiểu:

~~~gitignore
target/
.gradle/
build/
.idea/
*.iml
*.log
~~~

Các mục `.gradle/`, `build/` chỉ có tác dụng khi dùng Gradle; với Maven không cần tạo chúng. **Không ignore** các scripts/tệp wrapper được sinh và review. Với secrets, dùng CI secrets/biến môi trường hoặc secret manager; không commit mật khẩu, token, file cấu hình production nhạy cảm.

Nếu dự án có resources, nhớ rằng đường dẫn tương đối phụ thuộc working directory; dùng `ClassLoader.getResourceAsStream` hoặc `getResource` phù hợp cho tài nguyên **đóng gói** thay vì hard-code `src/main/resources`. Test không được giả định IDE và CI có cùng working directory một cách không kiểm chứng.

## 8. Phương án Gradle hiện nay: tách JVM chạy build và JVM biên dịch

Gradle có Java plugin và **Java toolchains**, cũng hỗ trợ cấu trúc `src/main/java` / `src/test/java`. Tuy nhiên **Gradle 9+ yêu cầu Java 17 hoặc mới hơn để chạy Gradle**, mặc dù nó vẫn có thể biên dịch/test project target Java 11 qua toolchain. Nếu máy chỉ có JDK 11, Maven cấu hình ở trên là con đường dễ thực thi; nếu muốn dùng Gradle hiện hành, cài JDK 17+ cho Gradle daemon và cung cấp toolchain Java 11 cho source/tests. Không chọn ngẫu nhiên Gradle cũ chỉ để né yêu cầu runtime rồi coi đó là chiến lược cập nhật lâu dài.

Mẫu `build.gradle.kts` cho môi trường **Gradle 9+, runtime build JDK 17+, toolchain JDK 11**:

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(11)
    }
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.14.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass = "com.example.App"
}
~~~

Mẫu này dùng cùng `App.java`, `Greeting.java` và `GreetingTest.java`. Khi wrapper, JDK build và toolchain đã có:

~~~bash
./gradlew test
./gradlew run --args="Linh"
~~~

Trên Windows dùng `gradlew.bat`. `./gradlew run --args="Linh"` in dòng `Xin chào, Linh!` trong output Gradle; output đầy đủ có thêm build log và không cố định. Với Gradle, **commit wrapper** cùng `gradle/wrapper/gradle-wrapper.properties`, và cân nhắc dependency locking/verification khi cần tái lập, bảo mật chuỗi cung ứng. Không cần dùng cả Maven và Gradle cho cùng dự án minh họa.

## 9. Lộ trình chuyển đổi an toàn từ một tệp

1. **Chụp baseline:** ghi lệnh đang dùng, dữ liệu vào, stdout/stderr, exit code và các hiệu ứng có thể quan sát.
2. **Tạo cấu trúc chuẩn:** `pom.xml`, `src/main/java` và `src/test/java` theo package.
3. **Tách logic:** chuyển xử lý từ `main` sang class/method trả kết quả; để I/O tại entry point hoặc adapter.
4. **Đưa mã vào package:** thêm `package`, sửa import, bảo đảm tên class/file và FQCN đúng.
5. **Thêm unit tests:** ít nhất một case chính và các case biên quan trọng; chạy `mvn test`.
6. **Chuyển dependency:** khai báo trong `pom.xml` với scope/phiên bản phù hợp, loại bỏ JAR copy tay nếu không cần.
7. **Kiểm tra hợp đồng:** so sánh output/side effects trước-sau; chạy `mvn clean verify` từ workspace sạch.
8. **Cố định quy trình nhóm:** wrapper, `.gitignore`, README lệnh chạy, pipeline CI, version JDK và hướng dẫn lỗi thường gặp.
9. **Đóng gói/phát hành khi cần:** cấu hình runnable JAR, container hoặc distribution riêng; đo lại cold start, cấu hình và các đường dẫn tài nguyên.

**Một thay đổi ở một thời điểm:** đừng vừa tách file, vừa đổi framework, đổi format output và đổi nghiệp vụ rồi chỉ chạy lại một case. Chuyển cấu trúc trước, giữ hành vi, sau đó cải tiến có test bảo vệ.

## 10. Lỗi phổ biến và cách điều tra

| Dấu hiệu | Nguyên nhân hay gặp và cách kiểm tra |
| --- | --- |
| `Could not find or load main class` | `package`, đường dẫn output và tên đầy đủ `com.example.App` không khớp; kiểm tra `target/classes` và classpath. |
| `UnsupportedClassVersionError` | Class/dependency được compile cho Java mới hơn runtime; kiểm tra JDK, `--release 11` và dependency. |
| `No tests were executed` hoặc test count = 0 | File nằm sai `src/test/java`, tên không theo pattern Surefire, không có `@Test` đúng, thiếu test engine/plugin hoặc cấu hình lọc test. Không coi 0 test là thành công. |
| Lệnh `java -jar ...` không chạy main | JAR thiếu `Main-Class` trong manifest; thêm cấu hình packaging phù hợp thay vì cho rằng `package` đã tạo executable JAR. |
| Test pass trên IDE nhưng fail trên CI | Khác JDK, timezone, locale, working directory, path separator, thứ tự test hoặc dependency môi trường. |
| Maven không tải được dependency | Kiểm tra kết nối/proxy, repository cấu hình, thông tin xác thực qua cơ chế an toàn và artifact/version có tồn tại. |
| Gradle báo JVM không được hỗ trợ | Gradle 9 cần JVM 17+ để chạy build; Java 11 vẫn có thể là **toolchain** biên dịch/test. |
| Tất cả test phụ thuộc Internet/database thật | Test không cách ly, flaky hoặc tạo dữ liệu ngoài; chuyển logic thuần vào unit test và dùng integration test có fixture, cleanup rõ ràng. |

## 11. Tiêu chí hoàn thành và bài thực hành

Một chuyển đổi thành công phải trả lời được: (1) code Java 11 compile theo target 11 hay chưa; (2) hành vi người dùng có được giữ không; (3) ai cũng chạy test bằng một lệnh được không; (4) khi test fail có báo cáo để tìm nguyên nhân không; (5) artifact/build có quy trình tái lập và CI rõ ràng không.

**Bài thực hành:**

1. Chạy `java Hello.java Linh` và `java Hello.java "   "`, lưu stdout.
2. Tạo ba tệp Java/`pom.xml` đúng đường dẫn như trên; chạy `mvn test` và xác minh **3 unit tests pass**.
3. Đổi tạm `Greeting.greet` để bỏ `strip()`; dự đoán test nào fail, chạy test, đọc báo cáo rồi phục hồi code đúng.
4. Chạy `mvn clean verify`, sau đó `java -cp target/classes com.example.App Linh`; so sánh output với `Hello.java`.
5. Thêm input test có ký tự Unicode và một điều kiện validate mới; chứng minh test trước và sau khi thêm logic.
6. Giải thích vì sao không thể “chỉ đổi `--release 11`” là xong khi một dependency đã được biên dịch cho Java 17, và vì sao Gradle 9 có thể chạy bằng JDK 17 trong khi target/source vẫn là Java 11.

**Tài liệu chính thức để tra cứu khi nâng cấp công cụ:** Java source launch: https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/ ; Maven `--release`: https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html ; Maven + JUnit Platform: https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html ; JUnit 5 docs: https://docs.junit.org/5.14.4/ ; Gradle Java compatibility: https://docs.gradle.org/current/userguide/compatibility.html .

**Kết luận của bài học:** hãy chuyển từ một-file launcher sang dự án build khi cần tổ chức mã, dependencies, test tự động hoặc quy trình nhóm. Giữ `main` đơn giản, kiểm thử hành vi qua JUnit, dùng build tool có cấu hình Java 11 rõ ràng và tái hiện kết quả trên CI. Các công cụ mới có thể yêu cầu JVM mới hơn, nên tách bạch **JDK chạy build**, **JDK dùng compile/test** và **Java release của sản phẩm**.