# Test task trong Java build integration

## Mục tiêu

Sau bài này, bạn có thể giải thích vai trò của test task trong quy trình build Java; phân biệt task của Gradle với lifecycle phase của Maven; hiểu cách build tool biên dịch test, chuẩn bị classpath, tìm test và khởi chạy test engine; cấu hình JUnit Platform; chạy toàn bộ hoặc một phần test; đọc báo cáo và xử lý test failure; tách unit test khỏi integration test; kiểm soát fork, parallel execution và JVM options; tích hợp test vào CI; và xử lý các lỗi thường gặp khi build tool không tìm thấy hoặc không chạy test như mong đợi.

## 1. Test task là gì?

**Test task** là bước trong build dùng để thực thi các test đã được biên dịch và tổng hợp kết quả. Nó kết nối source test, thư viện test, runtime classpath, test framework, JVM chạy test và báo cáo kết quả.

Khi chạy test từ build tool, công việc thường gồm:

1. Xác định source test và resource dành cho test.
2. Biên dịch test source.
3. Chuẩn bị classpath có code ứng dụng và thư viện test.
4. Chọn test engine tương ứng với framework.
5. Tìm các test class và test method hợp lệ.
6. Khởi chạy test process và thực thi test.
7. Thu thập kết quả, log, lỗi và thời gian chạy.
8. Tạo báo cáo cho developer và CI.
9. Đánh dấu build thành công hoặc thất bại dựa trên kết quả.

Build tool không phải test framework. Gradle hoặc Maven điều phối việc chạy test; JUnit, TestNG và test engine mới cung cấp cách định nghĩa, phát hiện và thực thi test.

### Các thành phần cần phân biệt

| Thành phần | Vai trò |
|---|---|
| Build tool | Điều phối task/phase và dependency giữa các bước |
| Test task hoặc test phase | Khởi chạy quá trình thực thi test |
| Test source set | Nhóm source, resource và dependency dành cho test |
| Test framework | API để viết test như JUnit Jupiter hoặc TestNG |
| Test engine/provider | Phát hiện và thực thi test theo framework |
| Test JVM/process | Process thực tế chạy test |
| Test report | Kết quả test dạng HTML, XML hoặc log |

Nếu thiếu test engine, build có thể biên dịch được class test nhưng không biết cách phát hiện hoặc chạy test. Nếu test source không nằm đúng source set, test task có thể không nhìn thấy class dù file tồn tại trong project.

## 2. Gradle task và Maven lifecycle phase khác nhau thế nào?

Hai build tool có cách mô hình hóa build khác nhau.

- **Gradle:** `test` là một task có kiểu `Test`. Task có input, output, dependency và cấu hình riêng. Java plugin tạo task này và nối nó với các task biên dịch test.
- **Maven:** `test` là một lifecycle phase trong default lifecycle. Maven chạy lần lượt các phase trước đó và goal plugin được bind vào phase `test`, thường là `surefire:test`.

| Nội dung | Gradle | Maven |
|---|---|---|
| Đơn vị điều phối | Task | Lifecycle phase và plugin goal |
| Lệnh chạy test | `./gradlew test` | `mvn test` |
| Thành phần chạy test | Gradle task type `Test` | Maven Surefire Plugin |
| Unit test mặc định | Task `test` | Phase `test` |
| Integration test | Có thể tạo task riêng như `integrationTest` | Failsafe Plugin gắn với `integration-test` và `verify` |
| Chạy full verification | `check` hoặc `build` | `verify` hoặc `install` |

Điểm quan trọng là cùng một lệnh chạy test có thể kéo theo nhiều bước chuẩn bị. Không nên nghĩ `test` chỉ đơn giản là gọi một method trong JUnit.

## 3. Vị trí source test theo quy ước Java

Cả Gradle Java plugin và Maven đều sử dụng cấu trúc source phổ biến:

~~~text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
├── build.gradle
└── pom.xml
~~~

| Thư mục | Nội dung |
|---|---|
| `src/main/java` | Source code của ứng dụng |
| `src/main/resources` | Resource khi chạy ứng dụng |
| `src/test/java` | Source test |
| `src/test/resources` | Resource chỉ dành cho test |

Test class thường nằm trong cùng package với class cần kiểm thử để dễ truy cập package-private API. Test source được biên dịch riêng và sử dụng classpath riêng, không được đóng gói vào artifact production theo cấu hình Java mặc định.

Trong Gradle, Java plugin tạo source set `main` và `test`. Trong Maven, các thư mục trên là convention mặc định của project layout.

Nếu project dùng thư mục khác, cần cấu hình source set hoặc build plugin tương ứng. Chỉ tạo file test trong một thư mục tùy ý không bảo đảm build tool sẽ tự tìm thấy file đó.

## 4. Gradle Java plugin tạo test task như thế nào?

Khi thêm Java plugin:

~~~groovy
plugins {
    id 'java'
}
~~~

Gradle tạo các task cơ bản:

| Task | Chức năng |
|---|---|
| `compileJava` | Biên dịch source ứng dụng |
| `processResources` | Copy resource ứng dụng |
| `classes` | Gom các bước tạo main classes |
| `compileTestJava` | Biên dịch source test |
| `processTestResources` | Copy resource test |
| `testClasses` | Chuẩn bị test classes và resource |
| `test` | Chạy unit test |
| `check` | Gom các bước kiểm tra, mặc định phụ thuộc `test` |
| `build` | Thực hiện `check` và `assemble` |

Task `test` phụ thuộc `testClasses` và các task tạo test runtime classpath. Vì vậy, khi chạy:

~~~bash
./gradlew test
~~~

Gradle tự thực hiện các dependency cần thiết trước khi khởi chạy test process.

Có thể hình dung luồng task:

~~~text
compileJava -----> classes
                      |
processResources -----+
                      |
                      v
                compileTestJava
                      |
processTestResources-+
                      |
                      v
                  testClasses
                      |
                      v
                    test
                      |
                      v
                    check
                      |
                      v
                    build
~~~

`classes` và `testClasses` là các aggregate task: chúng gom dependency để chuẩn bị output, không tự biên dịch code bằng một compiler riêng.

### Xem task graph

Liệt kê task:

~~~bash
./gradlew tasks --all
~~~

Xem những task sẽ được thực hiện mà chưa chạy:

~~~bash
./gradlew test --dry-run
~~~

Bật log chi tiết:

~~~bash
./gradlew test --info
~~~

Các lệnh này hữu ích khi cần biết vì sao một task chạy, task nào phụ thuộc nó hoặc vì sao test process chưa được khởi chạy.

## 5. Gradle Test task thực thi test trong JVM riêng

Gradle sử dụng kiểu task `org.gradle.api.tasks.testing.Test`. Task này cần hai thành phần cốt lõi:

- Thư mục chứa test class đã biên dịch.
- Execution classpath có class ứng dụng và test framework cần thiết.

Test thường chạy trong một hoặc nhiều JVM process riêng, tách khỏi Gradle daemon. Điều này giúp tránh classpath của test làm nhiễm build process và cho phép cấu hình JVM test độc lập.

Một số thuộc tính quan trọng:

| Thuộc tính | Tác dụng |
|---|---|
| `testClassesDirs` | Thư mục chứa test class |
| `classpath` | Classpath khi chạy test |
| `maxParallelForks` | Số test worker process chạy song song tối đa |
| `forkEvery` | Số test class tối đa chạy trong một worker trước khi fork JVM mới |
| `maxHeapSize` | Heap tối đa cho test JVM |
| `jvmArgs` | JVM arguments cho test process |
| `systemProperty` | System property truyền vào test JVM |
| `environment` | Environment variables của test process |
| `workingDir` | Working directory khi chạy test |
| `failFast` | Dừng task khi gặp failure đầu tiên |
| `ignoreFailures` | Không làm build thất bại vì test failure |
| `failOnNoDiscoveredTests` | Quy định task có thất bại khi không phát hiện test hay không |

Mặc định Gradle chạy một test worker process cho task `test`. Khi tăng parallelism, test có thể hoàn thành nhanh hơn nhưng phải bảo đảm các test độc lập và không ghi đè dữ liệu dùng chung.

## 6. Test framework và test engine

Test framework cung cấp API viết test. Test engine chịu trách nhiệm phát hiện và chạy test trên runtime.

JUnit 5 sử dụng JUnit Platform làm nền tảng:

- **JUnit Platform:** nền tảng launch và discovery.
- **JUnit Jupiter:** API và engine cho test kiểu JUnit 5.
- **JUnit Vintage:** engine để chạy test JUnit 3/4 cũ trên JUnit Platform.

Với Gradle, cần cấu hình test task dùng JUnit Platform và thêm engine vào runtime:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.13.1'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`testImplementation` cung cấp JUnit Jupiter cho việc biên dịch test. `testRuntimeOnly` cung cấp JUnit Platform Launcher khi test process chạy.

Nếu dùng JUnit 4, có thể cấu hình engine tương ứng. Nếu project trộn JUnit 4 và JUnit 5, cần có Vintage Engine để các test JUnit 4 được chạy qua JUnit Platform.

Với Maven Surefire 3.6.0 trở lên, các test chạy qua JUnit Platform provider thống nhất. Surefire tự chọn engine/provider phù hợp dựa trên dependency. Hãy kiểm tra dependency tree khi test compile được nhưng không chạy.

## 7. Discovery: build tool tìm test như thế nào?

Test discovery là quá trình tìm class và method đáp ứng quy tắc của framework và build tool.

Một test có thể không chạy dù source compile thành công vì:

- File nằm sai source directory.
- Test class không được biên dịch vào output directory mà task sử dụng.
- Class name không khớp include/exclude pattern.
- Test method thiếu annotation hoặc visibility/structure không hợp lệ theo framework.
- Test engine không có trên runtime classpath.
- Custom task trỏ tới nhầm testClassesDirs hoặc classpath.
- Test bị loại bởi filter, tag hoặc profile.

### Quy tắc tên test mặc định của Maven Surefire

Surefire mặc định tìm các class theo các pattern phổ biến:

- `Test*.java`
- `*Test.java`
- `*Tests.java`
- `*TestCase.java`

Ví dụ `CalculatorTest` thường được phát hiện. Một class tên `CalculatorSpec` có thể không được chạy nếu không cấu hình include riêng.

### Quy tắc Gradle

Gradle Java plugin tự cấu hình task `test` để dùng test source set mặc định. Task custom cần chỉ rõ test class directories và classpath.

Nếu không có test source hoặc không có candidate class, task có thể được đánh dấu `NO-SOURCE` hoặc bỏ qua. Nếu đã có test source/class nhưng không phát hiện được test, thuộc tính `failOnNoDiscoveredTests` mặc định true giúp build phát hiện tình trạng này. Hãy đọc log để phân biệt hai trường hợp.

## 8. Chạy toàn bộ hoặc một phần test bằng Gradle

Chạy toàn bộ test:

~~~bash
./gradlew test
~~~

Chạy một class:

~~~bash
./gradlew test --tests com.example.CalculatorTest
~~~

Chạy một method:

~~~bash
./gradlew test --tests "com.example.CalculatorTest.addsTwoNumbers"
~~~

Chạy các class khớp wildcard:

~~~bash
./gradlew test --tests "*Calculator*"
~~~

Test filtering có thể dùng fully-qualified class name hoặc method name. Pattern wildcard giúp chạy một nhóm test mà không cần sửa build script.

### Chạy task verification

~~~bash
./gradlew check
~~~

`check` là lifecycle task gom các bước verification. Java plugin mặc định gắn `test` vào `check`; plugin khác có thể thêm static analysis, code quality hoặc custom verification task.

Chạy full build:

~~~bash
./gradlew build
~~~

`build` phụ thuộc `check` và `assemble`. Vì vậy, lệnh này thường phù hợp với bước CI cần cả artifact lẫn kiểm tra.

### Debug test process

Có thể chạy test JVM ở chế độ debug:

~~~bash
./gradlew test --debug-jvm
~~~

IDE hoặc debugger có thể attach vào debug port mà Gradle mở cho test process. Chỉ bật khi cần điều tra test cụ thể và đóng phiên debug sau khi xong.

## 9. Cấu hình Gradle test execution

Có thể cấu hình logging, JVM, system property, filter và parallel execution trong build script.

Ví dụ Groovy DSL:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()

    maxParallelForks = 2
    maxHeapSize = '1g'

    systemProperty 'app.environment', 'test'

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showStandardStreams = true
    }
}
~~~

Giải thích:

- `maxParallelForks = 2` cho phép tối đa hai test worker process chạy song song.
- `maxHeapSize` giới hạn heap của mỗi test JVM.
- `systemProperty` truyền cấu hình test vào JVM.
- `testLogging` chọn sự kiện và mức chi tiết được in ra console.

Không tăng parallelism chỉ vì CI có nhiều core. Test ghi cùng file, dùng chung port, sửa cùng database row hoặc phụ thuộc thứ tự thực thi có thể tạo failure ngẫu nhiên.

### forkEvery và process isolation

`forkEvery` quy định số test class được chạy trong một worker process trước khi Gradle khởi tạo worker mới.

- Giá trị 0: tái sử dụng test process cho tất cả test class; đây là mặc định.
- Giá trị 1: tạo process mới cho mỗi test class; có chi phí startup cao.
- Giá trị N: tạo process mới sau mỗi N test class.

Fork mới có thể giúp cô lập state bị rò rỉ giữa các test class, nhưng làm build chậm hơn. Chỉ thay đổi khi có bằng chứng về state leakage hoặc yêu cầu isolation.

### Parallel test cần dữ liệu riêng

Gradle cung cấp property `org.gradle.test.worker` có giá trị riêng cho mỗi worker process. Có thể dùng property này để tạo tên file, thư mục tạm hoặc resource identifier không trùng nhau.

Test cần tự quản lý dữ liệu dùng chung. Không dựa vào thứ tự test hoặc việc một test luôn chạy trước test khác.

## 10. Maven test phase và Surefire

Maven dùng default build lifecycle. Với project packaging kiểu JAR, phase `test` được bind với goal `surefire:test`.

Khi chạy:

~~~bash
mvn test
~~~

Maven thực hiện các phase cần thiết trước `test`, bao gồm validate, xử lý resource, compile main source, xử lý test resource và compile test source. Sau đó Surefire chạy unit test.

Một số phase thường gặp:

| Phase | Ý nghĩa |
|---|---|
| `validate` | Kiểm tra project và thông tin build |
| `compile` | Biên dịch source ứng dụng |
| `test-compile` | Biên dịch source test |
| `test` | Chạy unit test bằng Surefire |
| `package` | Đóng gói artifact |
| `integration-test` | Chạy integration test trong môi trường đã chuẩn bị |
| `verify` | Kiểm tra kết quả và tiêu chí chất lượng |
| `install` | Cài artifact vào local repository |
| `deploy` | Đưa artifact lên remote repository |

Chạy `mvn test` không tạo JAR cuối cùng. Nếu muốn tạo package, dùng `mvn package`. Nếu project có integration test gắn với Failsafe, dùng `mvn verify`.

### Surefire Plugin

Surefire được thiết kế để chạy unit test trong phase `test`. Nó hỗ trợ JUnit, JUnit Platform và TestNG tùy phiên bản plugin cùng dependency.

Surefire tạo report text và XML. Thư mục mặc định:

~~~text
target/surefire-reports/
~~~

Ví dụ file report:

~~~text
TEST-com.example.CalculatorTest.xml
com.example.CalculatorTest.txt
~~~

Report XML có thể được CI server dùng để hiển thị test result, failure và thống kê.

### Chọn một test class bằng Maven

~~~bash
mvn -Dtest=CalculatorTest test
~~~

Có thể dùng wildcard:

~~~bash
mvn -Dtest=Calculator*Test test
~~~

Với JUnit Platform provider, hãy ưu tiên filter theo class nếu cần tính tương thích giữa các test engine và plugin version. Cú pháp chọn method có thể phụ thuộc provider/framework; kiểm tra tài liệu phiên bản Surefire đang dùng trước khi đưa vào script CI.

## 11. Failsafe cho integration test trong Maven

Unit test thường kiểm tra logic trong phạm vi hẹp. Integration test kiểm tra sự phối hợp với filesystem, database, HTTP server, message broker hoặc service khác.

Maven có plugin riêng là Failsafe để chạy integration test. Failsafe có hai goal:

- `failsafe:integration-test` chạy integration test.
- `failsafe:verify` xác minh kết quả integration test và làm build thất bại nếu có failure.

Lifecycle integration test thường gồm:

1. `pre-integration-test`: chuẩn bị môi trường, container hoặc service.
2. `integration-test`: thực thi integration test.
3. `post-integration-test`: thu dọn môi trường và tài nguyên.
4. `verify`: xác minh kết quả test.

Failsafe không làm build thất bại ngay trong phase `integration-test` khi phát hiện test failure. Điều này cho phép phase `post-integration-test` chạy để dọn tài nguyên trước khi phase `verify` quyết định build thành công hay thất bại.

Vì vậy, hãy gọi:

~~~bash
mvn verify
~~~

Không gọi riêng `mvn integration-test` trong workflow thông thường. Nếu dừng ở phase đó, các bước teardown ở `post-integration-test` có thể không được thực hiện.

### Tên integration test

Failsafe có convention riêng cho integration test, thường dùng tên bắt đầu bằng `IT` hoặc kết thúc bằng `IT`/`ITCase`. Trong ví dụ bên dưới, plugin cấu hình include rõ `**/*IT.java` để tránh phụ thuộc vào việc người đọc nhớ pattern mặc định.

Integration test vẫn có thể nằm trong `src/test/java` của Maven project; Failsafe phân biệt test bằng include/exclude pattern. Với Gradle, có thể tạo source set và task riêng.

## 12. Ví dụ Java 17+: Calculator và test task

Ví dụ này tạo một project có unit test cho phép cộng và integration test đọc/ghi file. Cùng một source code có thể chạy bằng Maven Surefire/Failsafe hoặc Gradle.

### Cấu trúc project

~~~text
test-task-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/
    │           ├── Calculator.java
    │           └── FileTotalStore.java
    └── test/
        └── java/
            └── com/example/
                ├── CalculatorTest.java
                └── FileTotalStoreIT.java
~~~

### Source ứng dụng: Calculator.java

~~~java
package com.example;

public class Calculator {
    public int add(int left, int right) {
        return left + right;
    }
}
~~~

### Source ứng dụng: FileTotalStore.java

~~~java
package com.example;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileTotalStore {
    public void save(Path file, int total) throws IOException {
        Files.writeString(file, Integer.toString(total),
                StandardCharsets.UTF_8);
    }

    public int load(Path file) throws IOException {
        String value = Files.readString(file, StandardCharsets.UTF_8);
        return Integer.parseInt(value);
    }
}
~~~

### Unit test: CalculatorTest.java

~~~java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        Calculator calculator = new Calculator();

        assertEquals(7, calculator.add(3, 4));
    }
}
~~~

### Integration test: FileTotalStoreIT.java

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;

class FileTotalStoreIT {
    @TempDir
    Path tempDir;

    @Test
    void savesAndReadsTotalFromFile() throws IOException {
        Path file = tempDir.resolve("total.txt");
        FileTotalStore store = new FileTotalStore();

        store.save(file, 42);

        assertEquals(42, store.load(file));
    }
}
~~~

`@TempDir` yêu cầu JUnit tạo thư mục tạm riêng cho test và quản lý vòng đời thư mục. Integration test này đi qua API filesystem thực tế, nên kiểm tra được việc ghi và đọc file cùng encoding.

## 13. Maven POM đầy đủ cho ví dụ

Tạo file `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>test-task-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit</groupId>
                <artifactId>junit-bom</artifactId>
                <version>5.13.1</version>
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
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
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
                        <configuration>
                            <includes>
                                <include>**/*IT.java</include>
                            </includes>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

BOM giúp đồng bộ version giữa các artifact JUnit. Dependency `junit-jupiter` cung cấp API và engine Jupiter cần thiết cho test.

Surefire chạy `CalculatorTest` ở phase `test`. Failsafe chọn `FileTotalStoreIT` theo include pattern ở phase `integration-test` rồi xác minh kết quả ở phase `verify`.

### Chạy bằng Maven

Chạy unit test:

~~~bash
mvn test
~~~

Chạy riêng unit test:

~~~bash
mvn -Dtest=CalculatorTest test
~~~

Chạy cả unit test, package và integration test:

~~~bash
mvn verify
~~~

Sau khi chạy, kiểm tra:

~~~text
target/surefire-reports/
target/failsafe-reports/
~~~

Trong lần chạy thành công, report của unit test có một test pass và report của integration test có một test pass. Dòng tổng kết console có thể khác theo phiên bản Maven/plugin, nhưng build phải kết thúc với trạng thái BUILD SUCCESS.

## 14. Chạy cùng ví dụ bằng Gradle

Nếu dùng Gradle, có thể giữ nguyên các file Java và đặt test source theo source set.

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.13.1'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Gradle mặc định dùng `src/test/java` cho unit test. Nếu chỉ cần chạy unit test:

~~~bash
./gradlew test
~~~

Chạy riêng test class:

~~~bash
./gradlew test --tests com.example.CalculatorTest
~~~

Chạy cả verification task:

~~~bash
./gradlew check
~~~

Gradle HTML report mặc định:

~~~text
build/reports/tests/test/index.html
~~~

XML test results:

~~~text
build/test-results/test/
~~~

### Tạo integrationTest task riêng trong Gradle

Java plugin mặc định chỉ tạo task `test` cho source set test. Nếu cần tách integration test, tạo source set `integrationTest` và task kiểu `Test`.

Chuyển `FileTotalStoreIT.java` vào:

~~~text
src/integrationTest/java/com/example/FileTotalStoreIT.java
~~~

Bổ sung vào `build.gradle`:

~~~groovy
sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'

        compileClasspath += sourceSets.main.output
        compileClasspath += configurations.testRuntimeClasspath

        runtimeClasspath += output + compileClasspath
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    useJUnitPlatform()
    shouldRunAfter tasks.named('test')
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
~~~

Task custom sử dụng output của source set integration test và runtime classpath tương ứng. `shouldRunAfter` đặt thứ tự khi cả hai task cùng được yêu cầu; `dependsOn` gắn integration test vào lifecycle task `check`.

Chạy integration test:

~~~bash
./gradlew integrationTest
~~~

Chạy toàn bộ verification:

~~~bash
./gradlew check
~~~

Ví dụ này dùng source set và task custom để minh họa cơ chế Gradle. Với project lớn, có thể cân nhắc JVM Test Suite DSL để mô hình hóa nhiều test suite theo cấu trúc chuẩn của Gradle.

## 15. Báo cáo test và cách đọc kết quả

Báo cáo giúp phân biệt build failure do compile, test assertion, test discovery hay môi trường.

### Gradle

Mặc định Gradle tạo:

- HTML report tại `build/reports/tests/test/index.html`.
- XML result tại `build/test-results/test/`.
- Binary result nội bộ để tạo report.

Report hiển thị test suite, class, method, duration, failure và stack trace. Task custom có thể có report riêng dựa trên tên task.

### Maven Surefire và Failsafe

Surefire:

~~~text
target/surefire-reports/
~~~

Failsafe:

~~~text
target/failsafe-reports/
~~~

Các plugin tạo text và XML report. Failsafe còn tạo summary report để xác minh integration test.

### Phân biệt test result với build result

| Kết quả | Ý nghĩa |
|---|---|
| Tests passed | Các test được phát hiện và đều pass |
| Tests failed | Assertion hoặc test logic thất bại |
| Tests errored | Test gặp exception/lỗi thực thi không phải assertion failure |
| Tests skipped | Test bị bỏ qua theo annotation/configuration |
| No tests discovered | Build tool không tìm thấy test hợp lệ |
| Test JVM crashed | Process chạy test không khởi động hoặc bị kết thúc bất thường |
| Compilation failed | Test source không biên dịch được; test task chưa thực thi |

Build có thể thất bại trước khi một test nào được chạy. Luôn đọc phần task/phase đầu tiên thất bại và report liên quan.

## 16. Chạy test có chọn lọc và kiểm soát việc bỏ qua test

Trong lúc phát triển, chạy một test class giúp vòng phản hồi nhanh hơn. Nhưng pipeline CI cần chạy đủ test suite theo chính sách dự án.

### Gradle

Chạy một class:

~~~bash
./gradlew test --tests com.example.CalculatorTest
~~~

Chạy một method:

~~~bash
./gradlew test --tests "com.example.CalculatorTest.addsTwoNumbers"
~~~

Chạy lại task bất kể trạng thái up-to-date:

~~~bash
./gradlew test --rerun-tasks
~~~

Loại trừ task test:

~~~bash
./gradlew build -x test
~~~

`-x test` loại task test khỏi build graph của lần chạy đó. Dùng có chủ đích vì các bước verification phụ thuộc test có thể không còn kiểm tra được điều cần thiết.

### Maven

Chạy riêng class:

~~~bash
mvn -Dtest=CalculatorTest test
~~~

Bỏ qua việc thực thi test nhưng vẫn compile test source:

~~~bash
mvn -DskipTests package
~~~

Bỏ qua cả compile test source và thực thi test:

~~~bash
mvn -Dmaven.test.skip=true package
~~~

Hai tùy chọn Maven không giống nhau. `skipTests` giữ bước biên dịch test; `maven.test.skip` bỏ cả biên dịch lẫn chạy test.

Không đưa tùy chọn skip vào lệnh CI thông thường nếu pipeline yêu cầu test là quality gate. Khi buộc phải bỏ qua test trong một tình huống đặc biệt, cần ghi rõ lý do và chạy lại verification đầy đủ trước khi phát hành.

## 17. Test task trong CI pipeline

CI thường chạy test task sau khi checkout source và thiết lập JDK/build tool.

Một pipeline cơ bản:

1. Checkout đúng commit.
2. Cài hoặc chọn JDK/toolchain.
3. Dùng Gradle Wrapper hoặc Maven Wrapper của repository.
4. Resolve dependency.
5. Compile source và test source.
6. Chạy unit test.
7. Chạy integration test nếu pipeline có môi trường cần thiết.
8. Thu thập XML/HTML report kể cả khi test thất bại.
9. Đánh dấu job thành công/thất bại dựa trên exit code.
10. Chỉ tiếp tục publish/deploy khi các quality gate bắt buộc đã pass.

Lệnh Gradle thường dùng:

~~~bash
./gradlew clean check
~~~

Lệnh Maven thường dùng:

~~~bash
./mvnw clean verify
~~~

Trên Windows, dùng wrapper tương ứng:

~~~powershell
gradlew.bat clean check
mvnw.cmd clean verify
~~~

Wrapper giúp CI dùng đúng phiên bản build tool mà project khai báo, giảm khác biệt giữa máy developer và runner.

### Multi-module project

Gradle có thể chạy task ở một module cụ thể:

~~~bash
./gradlew :service:test
~~~

Maven có thể chọn project/module và build dependency cần thiết:

~~~bash
mvn -pl service -am test
~~~

`-am` yêu cầu Maven build cả các module mà module được chọn phụ thuộc vào. Điều này giúp test module không sử dụng nhầm artifact cũ trong local repository.

### Giữ report khi job thất bại

CI nên cấu hình upload test report trong bước luôn chạy, kể cả khi task test trả exit code khác 0. Nếu chỉ upload report sau khi build thành công, những failure cần điều tra nhất có thể không còn report.

## 18. Incremental build và task outcome trong Gradle

Gradle theo dõi input/output của task để tránh thực hiện lại công việc không cần thiết khi kết quả vẫn hợp lệ.

Một số trạng thái thường thấy:

| Trạng thái | Ý nghĩa |
|---|---|
| EXECUTED | Task đã thực thi |
| UP-TO-DATE | Input/output không đổi nên không cần chạy lại |
| FROM-CACHE | Output được khôi phục từ build cache |
| NO-SOURCE | Không có source phù hợp để task xử lý |
| SKIPPED | Task bị bỏ qua theo điều kiện hoặc cấu hình |
| FAILED | Task thực thi và thất bại |

Không nhầm `UP-TO-DATE` với test đã bị vô hiệu hóa. Gradle có thể xác định output hiện tại còn hợp lệ so với input đã khai báo.

Tuy nhiên, test phụ thuộc trạng thái bên ngoài như database dùng chung, service remote hoặc file thay đổi ngoài build có thể không được mô tả đầy đủ trong task input. Khi đó, trạng thái up-to-date không nhất thiết phản ánh trạng thái mới của hệ thống bên ngoài.

Cách xử lý:

- Khai báo input/output và dependency cần thiết rõ ràng.
- Chuẩn bị fixture/database theo cách có thể lặp lại.
- Dùng `--rerun-tasks` để kiểm tra task có chạy lại hay không.
- Tránh test phụ thuộc vào trạng thái ngoài build mà không có setup/cleanup.
- Không xóa build output thủ công để ép test chạy nếu có lệnh Gradle phù hợp.

## 19. Parallel execution và test isolation

Chạy test song song có thể giảm tổng thời gian nhưng tạo ra nhiều tương tác giữa test.

Các rủi ro thường gặp:

- Hai test ghi cùng file hoặc cùng database record.
- Test dùng chung port hoặc tên queue.
- Test phụ thuộc thứ tự thực thi.
- Static mutable state còn tồn tại giữa test.
- Test dùng clock/randomness không kiểm soát.
- Cleanup chưa hoàn tất trước khi test khác sử dụng resource.

Trong Gradle, `maxParallelForks` điều khiển số worker process của một Test task. Build có thể đồng thời chạy nhiều Test task khác nhau; Gradle vẫn giới hạn tổng process theo cấu hình worker của build.

Trong Maven Surefire, `forkCount` và `reuseForks` điều khiển số JVM fork và việc tái sử dụng process. Parallel execution còn phụ thuộc test framework/provider và cấu hình plugin.

Bắt đầu với execution tuần tự. Chỉ bật parallel sau khi test có isolation rõ ràng và kết quả lặp lại ổn định.

## 20. Cấu hình test JVM và môi trường

Test JVM có thể cần cấu hình khác JVM chạy build hoặc ứng dụng production.

Gradle ví dụ:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()

    minHeapSize = '256m'
    maxHeapSize = '1g'

    jvmArgs '-Dfile.encoding=UTF-8'
    systemProperty 'app.environment', 'test'

    environment 'APP_TEST_MODE', 'true'
    workingDir = project.projectDir
}
~~~

Maven Surefire có thể cấu hình JVM arguments qua `argLine` và system properties qua `systemPropertyVariables` khi chạy forked test process.

Không đặt secret production trong test JVM arguments hoặc log. Dùng test credential riêng và cấp theo cơ chế bảo mật của CI.

Nếu test cần database hoặc HTTP service, hãy kiểm soát endpoint và port, credentials, database/schema riêng, timeout, setup và teardown, network availability, cùng resource cleanup khi test failure.

Một test phụ thuộc service ngoài nhưng không khai báo dependency trong pipeline có thể pass trên laptop và fail trên CI.

## 21. Phân biệt unit test, integration test và end-to-end test

Test task là nơi thực thi; loại test được xác định bởi phạm vi và dependency của test.

| Loại test | Phạm vi | Ví dụ |
|---|---|---|
| Unit test | Một class hoặc logic nhỏ, dependency được cô lập | Calculator cộng hai số |
| Integration test | Nhiều thành phần phối hợp với resource thật hoặc test instance | Ghi/đọc file, database repository |
| Component test | Một component hoặc service với dependency có kiểm soát | REST controller + service + test database |
| End-to-end test | Luồng nghiệp vụ qua nhiều hệ thống | Đăng nhập và hoàn tất đơn hàng qua HTTP |

Không phải mọi test đặt trong task `test` đều là unit test. Build tool không tự suy ra loại test từ nội dung method; naming, source set, tag, task và plugin configuration quyết định test được chạy ở đâu.

Tách suite theo thời gian chạy và dependency giúp CI tổ chức pipeline hợp lý: unit test chạy thường xuyên, integration test chạy trong môi trường được chuẩn bị, end-to-end test chạy ở stage phù hợp.

## 22. Lỗi thường gặp và cách xử lý

### Test class compile thành công nhưng không chạy

**Nguyên nhân:** tên class không khớp pattern, source directory sai, test engine thiếu hoặc filter đang loại test.

**Cách xử lý:** kiểm tra output test classes; kiểm tra Surefire include/exclude hoặc Gradle filter; xác nhận JUnit Platform/Jupiter Engine có trên runtime classpath.

### Gradle báo NO-SOURCE

**Nguyên nhân:** source set không có source phù hợp hoặc task trỏ tới sai thư mục.

**Cách xử lý:** kiểm tra `src/test/java`, sourceSets và testClassesDirs; xác nhận task đang dùng đúng source set.

### Gradle không phát hiện test dù có class

**Nguyên nhân:** class chưa được biên dịch, annotation không hợp lệ, engine thiếu hoặc custom Test task thiếu classpath.

**Cách xử lý:** chạy `compileTestJava` và xem output; kiểm tra `useJUnitPlatform()`; với task custom, cấu hình cả `testClassesDirs` và `classpath`.

### Maven test không chạy class có tên khác convention

**Nguyên nhân:** class không khớp Surefire default patterns.

**Cách xử lý:** đổi tên theo convention như `*Test.java` hoặc cấu hình include/exclude rõ ràng trong plugin.

### JUnit 5 test được compile nhưng không được thực thi

**Nguyên nhân:** JUnit Jupiter engine hoặc JUnit Platform provider không có trên runtime classpath; plugin quá cũ hoặc cấu hình framework không khớp.

**Cách xử lý:** kiểm tra dependency tree; dùng `junit-jupiter`; cấu hình `useJUnitPlatform()` cho Gradle; dùng Surefire/Failsafe tương thích với JUnit Platform.

### Maven verify chạy integration test nhưng môi trường không được dọn

**Nguyên nhân:** chỉ gọi trực tiếp phase `integration-test` hoặc setup/teardown plugin không được bind đúng lifecycle.

**Cách xử lý:** gọi `mvn verify` để chạy cả `post-integration-test` và `verify`; kiểm tra execution binding của Failsafe và plugin quản lý môi trường.

### Test pass trên máy local nhưng fail trên CI

**Nguyên nhân:** JDK, timezone, locale, environment variable, filesystem, dependency service hoặc test data khác nhau.

**Cách xử lý:** ghi lại toolchain và môi trường; dùng wrapper; cấp test data độc lập; xem XML report và log test JVM; tránh phụ thuộc trạng thái máy cá nhân.

### Test thỉnh thoảng mới fail

**Nguyên nhân:** race condition, test dùng chung resource, sleep cố định, clock/randomness hoặc cleanup không hoàn chỉnh.

**Cách xử lý:** làm test deterministic; dùng synchronization và timeout phù hợp; tạo resource riêng cho mỗi worker; không phụ thuộc thứ tự test; lặp lại test để tái hiện.

### Test task chạy quá lâu

**Nguyên nhân:** integration test gọi service thật, timeout quá dài, test bị block hoặc parallelism chưa phù hợp.

**Cách xử lý:** xem report theo duration; phân tách suite; xác định test chậm; dùng timeout hợp lý; chỉ bật parallel khi isolation được bảo đảm.

### Build thất bại trước khi chạy test

**Nguyên nhân:** main source compile, test source compile, dependency resolution hoặc task setup bị lỗi.

**Cách xử lý:** đọc task/phase đầu tiên thất bại; sửa compile hoặc dependency trước; không chẩn đoán đây là test assertion failure nếu test process chưa chạy.

### CI báo BUILD SUCCESS dù test không chạy

**Nguyên nhân:** test bị skip, task bị exclude, Maven skip property bật hoặc test discovery không được kiểm tra.

**Cách xử lý:** kiểm tra command line và environment properties; kiểm tra task graph; bật kiểm tra no-discovered-tests phù hợp; bảo đảm CI chạy `check` hoặc `verify` theo quality gate.

## 23. Quy trình sử dụng test task trong dự án

### Khi phát triển tính năng

1. Viết test trong source set test.
2. Chạy test class liên quan để nhận phản hồi nhanh.
3. Chạy toàn bộ unit test trước khi hoàn tất thay đổi.
4. Kiểm tra report khi có failure.
5. Thêm integration test khi logic đi qua boundary với resource thật.
6. Chạy task verification trước khi tạo commit/PR.

### Khi sửa bug

1. Tạo test tái hiện bug.
2. Chạy test và xác nhận failure trước khi sửa.
3. Sửa code.
4. Chạy lại test liên quan.
5. Chạy toàn bộ suite.
6. Xem regression và integration test nếu thay đổi ảnh hưởng nhiều thành phần.

### Khi cấu hình CI

1. Dùng wrapper và JDK/toolchain thống nhất.
2. Chạy Gradle `check` hoặc Maven `verify`.
3. Không bật skip test trong job quality gate.
4. Thu thập report kể cả khi job thất bại.
5. Chỉ publish artifact sau khi các test bắt buộc pass.
6. Tách suite chậm hoặc cần service riêng thành stage phù hợp.
7. Theo dõi flaky test và thời gian chạy qua nhiều build.

## 24. Checklist kiểm tra test task

### Cấu hình project

- [ ] Đúng JDK và build tool version.
- [ ] Test source nằm trong source set/thư mục đã cấu hình.
- [ ] Test dependency có scope phù hợp.
- [ ] Test engine/provider có trên runtime classpath.
- [ ] Test naming và discovery pattern phù hợp.
- [ ] Gradle custom task có testClassesDirs và classpath đúng.
- [ ] Maven Surefire/Failsafe version được pin rõ ràng.

### Thực thi

- [ ] Task/phase được gọi đúng mục tiêu.
- [ ] Test compile thành công.
- [ ] Test discovery tìm được số test dự kiến.
- [ ] Filter không vô tình loại test cần chạy.
- [ ] Test JVM dùng đúng arguments, environment và working directory.
- [ ] Parallelism không gây xung đột dữ liệu.
- [ ] Integration environment có setup/teardown.

### Kết quả và CI

- [ ] Đã đọc HTML/XML report.
- [ ] Đã phân biệt assertion failure, error và compile failure.
- [ ] Test report được lưu khi CI job thất bại.
- [ ] Không có skip property ngoài ý muốn.
- [ ] CI dùng wrapper và cùng JDK/toolchain.
- [ ] Quality gate gọi `check` hoặc `verify` phù hợp.
- [ ] Build chỉ publish/deploy khi test bắt buộc đã pass.

## 25. Tài liệu tham khảo chính thức

- [The Java Plugin — Gradle 9.9](https://docs.gradle.org/9.9.0/userguide/java_plugin.html) — task `test`, `testClasses`, source set, `check`, `build` và dependency configuration.
- [Testing in Java & JVM Projects — Gradle 9.9](https://docs.gradle.org/9.9.0/userguide/java_testing.html) — test execution, discovery, filtering, reports và parallel execution.
- [Test — Gradle DSL Reference](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html) — cấu hình Test task, JVM options, worker, filter và report.
- [Introduction to the Build Lifecycle — Maven](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — default lifecycle, test phase, verify và thứ tự thực thi.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/) — chạy unit test, report và các cấu hình test.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/) — integration-test, verify và quản lý teardown.
- [JUnit 5 User Guide — Build Support](https://docs.junit.org/5.13.1/user-guide/) — JUnit Jupiter, JUnit Platform, dependency và cấu hình Gradle/Maven.

Test task là cầu nối giữa code test và quy trình build. Hãy kiểm tra đồng thời source set, classpath, test engine, discovery, test JVM và report để biết chính xác test nào đã chạy. Với Gradle, dùng `test` và `check` theo task graph; với Maven, dùng `test` cho unit test và `verify` khi cần Failsafe integration test. Khi build thất bại, xác định đúng task hoặc phase đầu tiên lỗi trước khi sửa test hoặc cấu hình.
