# Thiết lập test runner và dependency tương thích Java 21

Để kiểm thử dự án Java 21, cần cấu hình ba thành phần khớp nhau: **JDK dùng để biên dịch và chạy test**, **test framework/engine cung cấp API và thực thi test**, và **build tool gọi test runner**. Một cấu hình phổ biến hiện nay là JUnit 6 với JUnit Platform, kết hợp Maven Surefire hoặc Gradle Test.

JUnit 6 yêu cầu Java 17 trở lên khi chạy, vì vậy tương thích với Java 21. Tại thời điểm biên soạn, ví dụ dùng JUnit 6.1.3, Maven Surefire/Failsafe 3.6.0 và Maven Compiler Plugin 3.16.0. Hãy kiểm tra phiên bản ổn định mới nhất khi bắt đầu dự án mới; nếu dự án dùng Spring Boot hoặc một BOM quản lý dependency, ưu tiên phiên bản do nền tảng đó quản lý thay vì ép version riêng.

## 1. Vai trò của test runner và các thành phần JUnit

JUnit được chia thành các thành phần có trách nhiệm riêng:

| Thành phần | Vai trò |
|---|---|
| JUnit Jupiter API | Annotation và assertion dùng để viết test như `@Test`, `@BeforeEach`, `assertEquals` |
| JUnit Jupiter Engine | Phát hiện và thực thi test được viết theo mô hình Jupiter |
| JUnit Platform | Nền tảng chung để khám phá, lập lịch và chạy test engine |
| JUnit Platform Launcher | API khởi chạy test platform; được build tool và IDE sử dụng khi cần |
| Maven Surefire / Gradle Test | Tích hợp test runner vào vòng đời build, chọn test class, tạo tiến trình test và báo cáo kết quả |

Để chạy test Jupiter, runtime test phải có một `TestEngine` tương ứng. Chỉ thêm API để biên dịch test mà thiếu engine thì build tool có thể không tìm thấy test nào để chạy.

JUnit 6 thống nhất version giữa Platform, Jupiter và Vintage. Dùng JUnit BOM để các artifact JUnit được căn chỉnh cùng một version, tránh trộn những phiên bản Platform và Jupiter không tương thích.

## 2. Cấu trúc thư mục test thông dụng

Maven và Gradle Java plugin đều dùng cấu trúc source set chuẩn:

```text
project/
├── pom.xml                 # hoặc build.gradle.kts
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/Calculator.java
    └── test/
        └── java/
            └── com/example/CalculatorTest.java
```

Mã test nằm trong `src/test/java` và chỉ được đưa vào test classpath. Dependency khai báo với scope/configuration test không bị đóng gói như dependency runtime của ứng dụng production.

## 3. Cấu hình Maven với JUnit 6 và Java 21

Với Maven, đặt `maven.compiler.release` bằng 21, import JUnit BOM và khai báo `junit-jupiter` ở scope `test`. Surefire chạy unit test trong phase `test`; Failsafe phù hợp với integration test chạy qua `integration-test` và `verify`.

Ví dụ `pom.xml` tối thiểu:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>java21-testing</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>6.1.3</junit.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit</groupId>
                <artifactId>junit-bom</artifactId>
                <version>${junit.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
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
                <version>3.6.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

`junit-jupiter` gom API và engine cần thiết cho test Jupiter. BOM quản lý version của các artifact thuộc nhóm JUnit; không cần lặp version ở từng dependency.

JUnit 6 yêu cầu Maven Surefire/Failsafe tối thiểu 3.0.0. Cấu hình ví dụ dùng 3.6.0 để tận dụng provider JUnit Platform thống nhất ở dòng 3.6.x. Nếu chỉ chạy unit test, có thể bỏ cấu hình Failsafe và chỉ giữ Surefire.

### Chạy test bằng Maven

```bash
# Chạy unit test
mvn test

# Chạy unit test và integration test
mvn verify

# Chạy một test class
mvn -Dtest=CalculatorTest test

# Bỏ qua thực thi test trong một lần build (không dùng cho CI kiểm chứng)
mvn -DskipTests package
```

Surefire chạy unit test trong phase `test`. Failsafe chạy integration test ở `integration-test` và kiểm tra kết quả ở `verify`; vì vậy nên gọi `mvn verify` khi cần chạy toàn bộ pipeline integration test.

## 4. Cấu hình Gradle Kotlin DSL với JUnit 6

Với Gradle, dùng Java toolchain để chọn JDK 21 cho compile và test. Cấu hình `useJUnitPlatform()` để Gradle Test task khám phá test qua JUnit Platform.

Ví dụ `build.gradle.kts`: 

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:6.1.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        events("passed", "skipped", "failed")
    }
}
```

BOM giữ các dependency JUnit tương thích với nhau. `junit-platform-launcher` được khai báo runtime để bảo đảm launcher có mặt trong test runtime classpath, bao gồm một số tích hợp IDE/build cần dùng launcher tường minh.

Ví dụ Groovy DSL `build.gradle`: 

```groovy
plugins {
    id "java"
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    testImplementation platform("org.junit:junit-bom:6.1.3")
    testImplementation "org.junit.jupiter:junit-jupiter"
    testRuntimeOnly "org.junit.platform:junit-platform-launcher"
}

test {
    useJUnitPlatform()
    testLogging {
        events "passed", "skipped", "failed"
    }
}
```

Để chạy Gradle daemon bằng JDK 21, dùng Gradle 8.5 trở lên. Java toolchain tách JDK dùng cho compile/test khỏi JVM chạy Gradle; nhờ đó build có thể chọn rõ Java 21 thay vì phụ thuộc JDK mặc định trên máy developer.

### Chạy test bằng Gradle

```bash
./gradlew test

# Chạy một class
./gradlew test --tests "com.example.CalculatorTest"

# Chạy test có tag được cấu hình
./gradlew test --tests "com.example.*"

# Kiểm tra toàn bộ lifecycle verification
./gradlew check
```

Trên Windows có thể dùng `gradlew.bat` thay cho `./gradlew`. Dùng Gradle Wrapper của repository để mọi developer và CI chạy cùng phiên bản Gradle.

## 5. Viết test Jupiter đầu tiên

Một class test đơn giản dùng `@Test` để đánh dấu phương thức kiểm thử và assertion để xác nhận kết quả:

```java
package com.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        Calculator calculator = new Calculator();

        int result = calculator.add(10, 5);

        assertEquals(15, result);
    }

    @Test
    void rejectsDivisionByZero() {
        Calculator calculator = new Calculator();

        assertThrows(
                ArithmeticException.class,
                () -> calculator.divide(10, 0));
    }
}
```

Test class và phương thức test trong Jupiter không bắt buộc phải `public`. Dùng package-private thường giúp test gọn hơn. Class test không nhất thiết phải kế thừa lớp base nào.

## 6. Kiểm thử nhiều trường hợp với ParameterizedTest

JUnit Jupiter cung cấp parameterized test để chạy cùng một hành vi với nhiều bộ dữ liệu. Cần có dependency `junit-jupiter-params`; artifact `junit-jupiter` trong cấu hình ở trên đã bao gồm thành phần này.

```java
package com.example;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class CalculatorParameterizedTest {
    @ParameterizedTest
    @CsvSource({
            "2, 3, 5",
            "10, 5, 15",
            "-2, 2, 0"
    })
    void addsValues(int left, int right, int expected) {
        Calculator calculator = new Calculator();

        assertEquals(expected, calculator.add(left, right));
    }
}
```

Parameterized test giúp giảm mã lặp và thể hiện rõ dữ liệu đầu vào/đầu ra. Mỗi invocation vẫn được JUnit báo cáo riêng.

## 7. Lifecycle và chia sẻ fixture

Jupiter cung cấp các annotation lifecycle phổ biến:

| Annotation | Thời điểm chạy |
|---|---|
| `@BeforeEach` | Trước mỗi test method/invocation |
| `@AfterEach` | Sau mỗi test method/invocation |
| `@BeforeAll` | Một lần trước tất cả test trong class |
| `@AfterAll` | Một lần sau tất cả test trong class |
| `@Nested` | Nhóm test lồng nhau để mô tả ngữ cảnh |
| `@DisplayName` | Đặt tên hiển thị dễ hiểu cho test |

Mặc định Jupiter tạo một instance test class cho mỗi test method (`PER_METHOD`). Nếu chuyển sang `PER_CLASS` để chia sẻ state hoặc dùng `@BeforeAll` không static, cần chú ý test có thể ảnh hưởng lẫn nhau; tránh phụ thuộc thứ tự thực thi.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CalculatorLifecycleTest {
    private Calculator calculator;

    @BeforeEach
    void setUp() {
        calculator = new Calculator();
    }

    @Test
    void addsValues() {
        // Dùng calculator đã được tạo mới cho test này.
    }
}
```

## 8. Phân biệt unit test và integration test

Unit test kiểm tra một đơn vị nhỏ với dependency được kiểm soát. Integration test kiểm tra tương tác giữa nhiều thành phần như database, HTTP server, message broker hoặc filesystem.

| Loại test | Mục tiêu | Vị trí/cách chạy thường dùng |
|---|---|---|
| Unit test | Kiểm tra logic nhỏ, nhanh, ít phụ thuộc môi trường | `src/test/java`, Maven Surefire, Gradle `test` |
| Integration test | Kiểm tra tích hợp với thành phần thật hoặc môi trường kiểm thử | Source set/thư mục riêng, Maven Failsafe hoặc Gradle task riêng |
| End-to-end test | Kiểm tra luồng nghiệp vụ qua nhiều lớp của hệ thống | Pipeline riêng, môi trường gần production |

Không nên đặt toàn bộ integration test vào cùng nhóm unit test nếu chúng cần dịch vụ bên ngoài hoặc mất nhiều thời gian. Tách task giúp CI chạy nhanh unit test trước, sau đó chạy integration test theo stage phù hợp.

### Quy ước tên integration test với Maven Failsafe

Các tên như `OrderServiceIT` hoặc `DatabaseITCase` thường phù hợp với mặc định discovery của Failsafe. Surefire chủ yếu chạy các class test unit; Failsafe nhận diện nhóm integration test theo quy ước tên và chạy ở phase riêng.

## 9. JUnit Vintage chỉ dùng trong giai đoạn migration

JUnit Vintage Engine cho phép chạy test viết bằng JUnit 3/4 thông qua JUnit Platform. Đây là cầu nối tạm thời cho dự án đang chuyển sang Jupiter; JUnit 6 đánh dấu Vintage là deprecated, vì vậy không nên thêm Vintage vào dependency mới nếu không có test cũ cần duy trì.

Khi cần duy trì test JUnit 4 trong lúc chuyển đổi, thêm dependency `junit:junit` và `org.junit.vintage:junit-vintage-engine` cùng version được quản lý bởi JUnit BOM. Lập kế hoạch chuyển test sang Jupiter rồi loại bỏ Vintage sau khi không còn test legacy.

Không trộn annotation của JUnit 4 và Jupiter trong cùng một class với kỳ vọng engine sẽ tự suy luận. Mỗi test nên dùng một mô hình rõ ràng; nếu duy trì cả hai engine, bảo đảm dependency và discovery được cấu hình có chủ đích.

## 10. Dependency scope và version alignment

| Build tool | Dependency configuration | Ý nghĩa |
|---|---|---|
| Maven | `<scope>test</scope>` | Chỉ có trong compile/test runtime classpath, không phải dependency production thông thường |
| Gradle | `testImplementation` | Dependency cần để biên dịch test và có trong test runtime |
| Gradle | `testRuntimeOnly` | Dependency chỉ cần lúc thực thi test, ví dụ Platform Launcher |
| Maven/Gradle | JUnit BOM | Đồng bộ version giữa Jupiter, Platform và Vintage |

Không khai báo nhiều version khác nhau cho `junit-jupiter-api`, `junit-jupiter-engine` và `junit-platform-*`. Nếu dùng Spring Boot dependency management, kiểm tra version JUnit do Spring Boot BOM chọn trước khi override.

## 11. Chọn phiên bản build tool tương thích Java 21

- **JUnit:** JUnit 6 yêu cầu Java 17 trở lên tại runtime, nên có thể chạy trên Java 21.
- **Maven Compiler Plugin:** dùng phiên bản hiện hành có hỗ trợ `maven.compiler.release`; ví dụ ở trên dùng 3.16.0 và `release` bằng 21.
- **Maven Surefire/Failsafe:** JUnit 6 yêu cầu tối thiểu 3.0.0; ví dụ dùng 3.6.0 với JUnit Platform provider thống nhất.
- **Gradle:** Gradle 8.5 trở lên hỗ trợ chạy Gradle trên JDK 21; dùng wrapper để cố định phiên bản build.
- **IDE:** chọn JDK 21 cho project SDK và đồng bộ runner với Maven/Gradle của dự án. Test chạy từ IDE và command line cần dùng cùng JUnit engine/dependency để tránh kết quả khác nhau.

Các version trong ví dụ là mốc cụ thể để cấu hình có thể chạy được. Trước khi nâng cấp, đọc release notes của JUnit, Maven plugins và Gradle; đồng thời kiểm tra framework nền tảng có khóa version hoặc yêu cầu riêng hay không.

## 12. Kiểm tra test discovery khi build báo “No tests found”

Khi test không được phát hiện, kiểm tra theo thứ tự:

1. File test nằm trong `src/test/java` hoặc source set được khai báo đúng.
2. Class và method có annotation `org.junit.jupiter.api.Test` hoặc annotation test Jupiter phù hợp.
3. JUnit Jupiter Engine có mặt trong test runtime classpath; không chỉ có API.
4. Maven Surefire hoặc Gradle Test được cấu hình đúng để dùng JUnit Platform.
5. Tên class khớp quy tắc discovery/filter của build tool.
6. IDE và command line đang dùng đúng JDK, module path/classpath và dependency graph.
7. Không vô tình exclude package, tag, engine hoặc test task trong cấu hình build.

Với Maven, dùng `mvn -X test` để xem thông tin discovery khi cần. Với Gradle, dùng `./gradlew test --info` hoặc `--debug` khi điều tra; không bật debug logging thường trực trong CI nếu không cần.

## 13. CI: chạy test bằng đúng JDK và build wrapper

CI nên dùng JDK 21 rõ ràng, khôi phục dependency cache theo lock/configuration của dự án và gọi build wrapper thay vì một Maven/Gradle cài toàn cục không được kiểm soát.

Ví dụ pipeline command:

```bash
# Xác nhận JDK thực tế
java -version

# Maven
./mvnw -B clean verify

# Hoặc Gradle
./gradlew --no-daemon clean check
```

Không chạy cả Maven lẫn Gradle nếu dự án chỉ chọn một build tool. Lưu test reports và làm build thất bại khi có test failure; không dùng `-DskipTests` hoặc `-x test` trong bước xác nhận chất lượng.

## 14. Những lỗi cấu hình thường gặp

- **Chỉ thêm JUnit API:** test biên dịch được nhưng engine không có mặt để thực thi.
- **Thiếu `useJUnitPlatform()` trong Gradle:** Gradle Test task không chạy Jupiter theo cấu hình mong muốn.
- **Trộn version JUnit:** Platform, Jupiter và engine không tương thích; dùng BOM để căn chỉnh.
- **Dùng JUnit Vintage cho test mới:** tạo phụ thuộc legacy không cần thiết; viết test mới bằng Jupiter.
- **Nhầm `release` với JDK runtime:** Maven compiler release 21 không tự chọn JVM 21 để chạy Maven hoặc test.
- **Dùng Gradle quá cũ với JDK 21:** Gradle daemon có thể không chạy được trên JDK 21; dùng Gradle 8.5+.
- **Chỉ chạy unit test nhưng tưởng integration test đã chạy:** cấu hình Failsafe yêu cầu phase `verify` để hoàn tất lifecycle integration test.
- **Chỉ xác nhận build compile thành công:** phải chạy test task và xem report để biết test thực sự được phát hiện và thực thi.

## 15. Checklist thiết lập

- [ ] JDK 21 được chọn rõ ràng cho compile và test runtime.
- [ ] JUnit 6/Jupiter API và Engine có mặt trong test dependencies.
- [ ] JUnit BOM căn chỉnh version của các artifact.
- [ ] Maven Surefire hoặc Gradle Test được cấu hình dùng JUnit Platform.
- [ ] Test nằm trong source set và tên class được build tool phát hiện.
- [ ] Unit test và integration test được phân chia theo thời gian chạy/phụ thuộc.
- [ ] Vintage chỉ được thêm khi còn test JUnit 3/4 cần migration.
- [ ] CI dùng Maven/Gradle Wrapper và JDK 21.
- [ ] Test report được lưu và build thất bại khi test fail.

## 16. Tài liệu tham khảo

- [JUnit 6.1.3 User Guide](https://docs.junit.org/6.1.3/user-guide/)
- [JUnit 6.1.3 Release Notes](https://docs.junit.org/6.1.3/release-notes/)
- [JUnit Build Support](https://docs.junit.org/6.1.3/running-tests/build-support.html)
- [Apache Maven Surefire 3.6.0](https://maven.apache.org/surefire/)
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Gradle — Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
