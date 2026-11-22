# Phân biệt source set kiểm thử riêng với JVM Test Suite trong Gradle

## Mục tiêu bài học

Một dự án Java có thể chứa **unit tests** nhanh trong **src/test/java**, đồng thời cần **integration tests** tương tác nhiều thành phần, cơ sở dữ liệu, HTTP hoặc hệ thống tệp. Hai nhóm này cần chạy riêng, có thể dùng thư viện, tài nguyên, JVM, cấu hình môi trường và chính sách CI khác nhau.

Trong Gradle, có hai phương pháp tổ chức kiểm thử bổ sung:

1. **Tạo một SourceSet riêng rồi đăng ký Test task thủ công**: cấu hình tường minh source directories, compile/runtime classpaths, các dependencies/framework, Test task, reports và lifecycle.
2. **Dùng JVM Test Suite plugin**: khai báo một **JvmTestSuite** trong **testing.suites**; Gradle quản lý SourceSet, dependency configurations, framework và một hoặc nhiều test targets, mỗi target có Test task.

**JVM Test Suite không phải framework kiểm thử mới** và cũng không thay thế SourceSet. Đây là một lớp trừu tượng cao hơn **xây dựng trên SourceSet và Test task**. Cả hai phương pháp đều có thể chạy JUnit Jupiter/TestNG nếu khai báo đúng.

Sau khi học, bạn có thể:
- Phân biệt **SourceSet**, **Test**, **JvmTestSuite**, **Target** và **testing extension**.
- Dự đoán task/configuration nào được sinh tự động và task nào phải tự khai báo.
- Hiểu vì sao manual source set cần **sourceSets.main.output** và dependencies, còn suite bổ sung cần **implementation project()** nếu muốn truy cập mã sản phẩm.
- Chạy cùng ví dụ **Java 17** bằng hai build.gradle thay thế nhau, với unit test và integration test ghi/đọc file thật.
- Phân biệt **Test.useJUnitPlatform()** với **JvmTestSuite.useJUnitJupiter()**.
- Kết nối **integrationTest** với **check**, dùng **shouldRunAfter** hợp lý.
- Tạo nhiều suite targets cho các Java runtimes khác nhau mà không nhân đôi test sources.
- Chẩn đoán **NO-SOURCE**, **no tests found**, missing test engine/launcher, classpath và task trùng tên.
- Migrate an toàn từ manual SourceSet sang JVM Test Suite và chọn mô hình phù hợp.

Ví dụ chính dùng **Groovy DSL**, có đối chiếu **Kotlin DSL**. Gradle Wrapper cần tương thích Java17 và hỗ trợ JVM Test Suite (API này được giới thiệu từ Gradle 7.3, đến tài liệu Gradle hiện hành vẫn được đánh dấu **incubating**). Phần JUnit cần kết nối tới Maven Central/mirror hoặc cache đã có. Các đoạn ở mục A và B là **hai cấu hình thay thế**, tuyệt đối không dán cả hai vào một build.gradle.

## 1. Nắm chắc ba lớp: SourceSet, Test và JvmTestSuite

### 1.1. SourceSet: nguồn, compilation và classpaths

Một **org.gradle.api.tasks.SourceSet** thuộc Java plugin mô tả:
- Các thư mục nguồn **java** và **resources**.
- **output** chứa compiled classes và processed resources.
- **compileClasspath** cho compiler.
- **runtimeClasspath** cho JVM thực thi mã đã biên dịch.
- Các configurations sinh theo tên như **integrationTestImplementation**, **integrationTestRuntimeOnly**, **integrationTestCompileClasspath**, **integrationTestRuntimeClasspath**.

Ví dụ:

~~~groovy
sourceSets {
    integrationTest {
        java.srcDirs = ['src/integrationTest/java']
        resources.srcDirs = ['src/integrationTest/resources']
    }
}
~~~

Các tên thư mục là convention của source set tên **integrationTest**; có thể bỏ hai dòng srcDirs nếu dùng đúng convention. SourceSet mới dẫn tới tasks như:

~~~text
compileIntegrationTestJava
processIntegrationTestResources
integrationTestClasses
~~~

**Không tự động sinh Test task chạy những classes đó** chỉ từ việc tạo SourceSet.

### 1.2. Test task: thực thi bài kiểm thử

**org.gradle.api.tasks.testing.Test** là task:
- Chọn directories chứa test classes qua **testClassesDirs**.
- Xác định runtime classpath qua **classpath**.
- Chọn test framework: **useJUnitPlatform()**, **useJUnit()**, **useTestNG()** theo nhu cầu.
- Khởi động JVM thực hiện tests, cấu hình heap, launcher, systemProperties và environment.
- Lọc tests và ghi JUnit XML, HTML reports.

Ví dụ một Test task độc lập (fragment, giả định SourceSet đã tồn tại):

~~~groovy
tasks.register('integrationTest', Test) {
    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
}
~~~

**Chỉ đăng ký Test task cũng không tự tạo SourceSet hoàn chỉnh**. Đặc biệt từ Gradle 9 trở lên, một custom Test task không còn được mặc định gắn vào built-in test source set như các conventions cũ: hãy tự khai báo testClassesDirs/classpath.

### 1.3. JvmTestSuite: mô hình nhóm test cấp cao

Plugin **jvm-test-suite** bổ sung:

~~~groovy
testing {
    suites {
        test {
            useJUnitJupiter('5.11.4')
        }
        integrationTest(JvmTestSuite) {
            useJUnitJupiter('5.11.4')
            dependencies {
                implementation project()
            }
        }
    }
}
~~~

Mỗi JvmTestSuite quản lý:
- **Một SourceSet**.
- Dependencies và configurations compile/runtime.
- Framework dùng trong suite.
- **Targets**: mỗi target có Test task, target mặc định thường đặt tên theo suite.
- Outgoing **test result variants** phục vụ test report aggregation.

Java plugin hiện đại **tự áp jvm-test-suite**; không cần apply cả hai plugins nếu đã có **id 'java'**. Plugin cần JVM language support, không phải công cụ thay thế Java plugin. API **incubating** có thể thay đổi khi cập nhật Gradle Wrapper.

### 1.4. Sơ đồ so sánh

~~~text
MANUAL
SourceSet integrationTest
  + compile/runtime configurations
  + compileIntegrationTestJava
  + integrationTestClasses
                |
                v
Custom Test task integrationTest   [bạn register]
  + testClassesDirs
  + runtime classpath
  + framework
  + check.dependsOn

JVM TEST SUITE
testing.suites.integrationTest
  + SourceSet integrationTest    [Gradle quản lý]
  + configurations               [Gradle quản lý]
  + testing framework            [useJUnitJupiter]
  + targets
       + default Test task integrationTest
       + optional additional Test tasks
  + check.dependsOn              [vẫn cần khai báo nếu muốn]
~~~

### 1.5. Tên tương đồng nhưng bản chất khác

- **SourceSet tên integrationTest** là một tập nguồn và classpath.
- **Test task tên integrationTest** là một công việc chạy tests.
- **Suite tên integrationTest** là một đối tượng declarative bao gồm SourceSet và các Test targets.
- **integrationTestImplementation** là configuration để khai báo dependencies.
- **integrationTestRuntimeClasspath** là một configuration được Gradle resolve thành files.

Trong phương án manual, những khối có thể mang cùng tiền tố nhưng do bạn lắp lại. Trong suite approach, Gradle nối chúng theo conventions.

## 2. So sánh hai phương pháp theo trách nhiệm

| Câu hỏi | SourceSet + Test thủ công | JVM Test Suite |
| --- | --- | --- |
| Ai khai báo nguồn? | **sourceSets { integrationTest { ... } }** | **integrationTest(JvmTestSuite)** tạo SourceSet |
| Ai tạo compilation tasks? | Java plugin từ SourceSet | Java plugin từ SourceSet của suite |
| Ai tạo Test task? | Bạn với **tasks.register** | Suite target |
| Ai đặt testClassesDirs/classpath? | Bạn | Suite target tự nối |
| Ai chọn framework? | **Test.useJUnitPlatform()** | **JvmTestSuite.useJUnitJupiter()** |
| Ai thêm JUnit dependencies? | Bạn phải khai báo đúng | Suite framework method có thể làm tự động |
| Ai cung cấp main classes? | **main.output** trong classpaths, cùng các deps | Suite dependencies **implementation project()** |
| Ai thêm test-specific dependencies? | **integrationTestImplementation** v.v. | **suite.dependencies.implementation** v.v. |
| Thư mục mặc định | src/integrationTest/java | src/integrationTest/java |
| Nhiều JVM chạy cùng tests | Tạo nhiều Test tasks cùng SourceSet | Tạo nhiều targets trong cùng suite |
| Thêm vào check | Tự nối | Vẫn tự nối |
| Thứ tự chạy sau test | **shouldRunAfter test** | **targets.testTask.shouldRunAfter test** |
| Test report HTML/XML | Có | Có |
| Outgoing test result variant | Không mặc nhiên giống suite | Có model cho aggregation |
| Ổn định API | SourceSet/Test lâu đời | JVM Test Suite còn incubating |
| Boilerplate | Nhiều hơn | Ít hơn |
| Khi chọn | Custom/legacy build phức tạp | Nhiều nhóm test với conventions đồng bộ |

**Điểm dễ hiểu sai:** JVM Test Suite *có* SourceSet, không phải phương án “không dùng SourceSet”. Và manual SourceSet *không* tự chạy test nếu thiếu Test task.

## 3. Unit test và integration test khác nhau ở đâu?

**Unit test** thường kiểm tra một hàm/class đơn lẻ, nhanh, ít I/O, chạy liên tục. **Integration test** kiểm tra tương tác giữa nhiều thành phần hoặc với hạ tầng, có thể cần trạng thái và chuẩn bị môi trường.

| Khía cạnh | Unit test | Integration test |
| --- | --- | --- |
| Thư mục mặc định dự án mẫu | src/test/java | src/integrationTest/java |
| Task mục tiêu | test | integrationTest |
| Dependencies | testImplementation/testRuntimeOnly | integrationTestImplementation/integrationTestRuntimeOnly |
| Vận tốc | Nên nhanh và độc lập | Có thể chậm do I/O/service |
| Môi trường | Thường mock/in-memory | File system, DB, HTTP hoặc service |
| CI | PR nhanh | PR hoặc nightly/release tùy policy |

Thư mục không tự xác định bản chất test: integration test đặt trong thư mục unit vẫn là integration test về mặt hành vi. Tách SourceSet/suite cho phép quản lý **compilation, classpaths, resources, JVM và lifecycle** khác nhau.

Nếu chỉ cần phân nhóm trong cùng test source set và cùng dependencies, JUnit Jupiter **@Tag("integration")** và Test filter có thể đủ. Khi thật sự muốn tách dependency graph hoặc CI job, SourceSet/suite mới có giá trị rõ hơn.

## 4. Ví dụ Java 17 dùng chung cho cả hai phương án

Mục tiêu: **GreetingService** tạo lời chào, **GreetingFileStore** ghi lời chào thành file thật. Unit test kiểm tra chuỗi; integration test phối hợp cả hai class và hệ thống tệp.

### 4.1. Cây dự án

~~~text
gradle-testing-lab/
├── settings.gradle
├── build.gradle                  # Dùng phương án A hoặc B
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/
    │   ├── GreetingService.java
    │   └── GreetingFileStore.java
    ├── test/java/demo/
    │   └── GreetingServiceTest.java
    └── integrationTest/java/demo/
        └── GreetingFileStoreIT.java
~~~

Lấy **Gradle Wrapper** từ project do Gradle tạo hoặc nguồn tin cậy. Cài JDK 17+, đảm bảo Wrapper tương thích và Maven Central/mirror sẵn sàng khi tải JUnit lần đầu.

### 4.2. settings.gradle

~~~groovy
rootProject.name = 'gradle-testing-lab'
~~~

### 4.3. src/main/java/demo/GreetingService.java

~~~java
package demo;

public final class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is blank");
        }
        return "Xin chào, " + name + "!";
    }
}
~~~

Cú pháp Java 17 hợp lệ. **String.isBlank()** có từ Java 11. Code độc lập, không cần thư viện bên ngoài.

### 4.4. src/main/java/demo/GreetingFileStore.java

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GreetingFileStore {
    private final GreetingService service = new GreetingService();

    public Path save(Path directory, String name) throws IOException {
        Files.createDirectories(directory);
        Path target = directory.resolve("greeting.txt");
        Files.writeString(
                target,
                service.greet(name),
                StandardCharsets.UTF_8
        );
        return target;
    }
}
~~~

Đây là thành phần thật truy cập filesystem. **Files.writeString** và **Files.readString** dùng trong test đều có từ Java 11; Java 17 không cần dependency khác.

### 4.5. src/test/java/demo/GreetingServiceTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

public final class GreetingServiceTest {
    @Test
    void createsGreeting() {
        assertEquals(
                "Xin chào, Lan!",
                new GreetingService().greet("Lan")
        );
        System.out.println("Unit OK: Xin chào, Lan!");
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new GreetingService().greet("  ")
        );
    }
}
~~~

JUnit Jupiter chạy hai tests; dòng **Unit OK: Xin chào, Lan!** do một test in, chỉ hiển thị trên console khi bật testLogging.showStandardStreams.

### 4.6. src/integrationTest/java/demo/GreetingFileStoreIT.java

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

public final class GreetingFileStoreIT {
    @Test
    void persistsActualFile(@TempDir Path directory) throws IOException {
        Path result = new GreetingFileStore().save(directory, "Lan");

        assertTrue(Files.exists(result));
        assertEquals(
                "Xin chào, Lan!",
                Files.readString(result, StandardCharsets.UTF_8)
        );

        System.out.println("Integration OK: " + result.getFileName());
    }
}
~~~

JUnit **@TempDir** cung cấp một temporary directory riêng cho test. Kết quả stdout quan sát khi hiển thị test streams:

~~~text
Integration OK: greeting.txt
~~~

Đường dẫn thư mục tạm thay đổi, nhưng **getFileName()** luôn in tên file mà production class tạo.

### 4.7. Biên dịch thử main Java sources không có JUnit

Nếu cần xác minh hai production classes bằng JDK 17, Linux/macOS:

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out src/main/java/demo/GreetingService.java src/main/java/demo/GreetingFileStore.java
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out .\src\main\java\demo\GreetingService.java .\src\main\java\demo\GreetingFileStore.java
~~~

**javac** thành công không in stdout; output classes:

~~~text
out/demo/GreetingService.class
out/demo/GreetingFileStore.class
~~~

Hai JUnit test classes vẫn cần JUnit JARs để biên dịch. Gradle sẽ cung cấp chúng qua test-specific dependencies trong mỗi phương án.

## 5. Phương án A: custom SourceSet + Test task

Đây là phương án **tường minh, ổn định và rất linh hoạt**. Sử dụng **build.gradle (Groovy DSL) hoàn chỉnh sau**, không kết hợp với phương án B.

### 5.1. build.gradle phương án A

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

sourceSets {
    integrationTest {
        // Main classes + resources cho integration tests.
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

configurations {
    // Truyền các production libraries cần thiết.
    integrationTestImplementation.extendsFrom implementation
    integrationTestRuntimeOnly.extendsFrom runtimeOnly
}

dependencies {
    // Dependencies dành riêng cho unit tests.
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'

    // Dependencies dành riêng cho integration tests.
    integrationTestImplementation platform('org.junit:junit-bom:5.11.4')
    integrationTestImplementation 'org.junit.jupiter:junit-jupiter'
    integrationTestRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

def integrationTestTask = tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'Runs integration tests'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    useJUnitPlatform()
    shouldRunAfter 'test'
}

tasks.withType(Test).configureEach {
    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }
}

tasks.named('check') {
    dependsOn integrationTestTask
}
~~~

### 5.2. Phân tích từng cấu hình

**sourceSets.integrationTest** tạo compile tasks và các configurations theo convention, đọc nguồn **src/integrationTest/java**, resources **src/integrationTest/resources**.

**compileClasspath += sourceSets.main.output** cho compiler của integration test thấy **demo.GreetingFileStore** và **demo.GreetingService**. Không có nó, compiler có thể báo **cannot find symbol**.

**runtimeClasspath += sourceSets.main.output** để lúc chạy test Java load được production classes/resources. Không phải mọi loại integration test đều cần main.output: một test chỉ gọi HTTP server bên ngoài có thể không import class sản phẩm.

**integrationTestImplementation.extendsFrom implementation** để external dependencies do main code yêu cầu được tham gia vào classpath kiểm thử; **integrationTestRuntimeOnly.extendsFrom runtimeOnly** tương tự cho runtime-only dependencies. ExtendsFrom **không tự chứa main compiled classes**, bởi vậy vẫn cần main.output.

**testImplementation** không tự được kế thừa bởi **integrationTestImplementation**. Ta khai báo JUnit riêng cho từng source set. Có thể cho integration test kế thừa testImplementation nếu thật sự cần tất cả unit test libraries, nhưng điều đó dễ kéo dependencies không cần thiết như Mockito/fixtures chỉ dành cho unit tests.

**tasks.register('integrationTest', Test)** mới là bước tạo runner. Chỉ có SourceSet chưa đủ để Gradle chạy tests.

**testClassesDirs** trỏ tới integration test output classes; **classpath** trỏ tới integration test runtimeClasspath, gồm JUnit, main classes, test classes và các runtime dependencies.

**useJUnitPlatform()** chỉ chọn framework cho Test task; nó không tự tải đầy đủ JUnit Jupiter hoặc JUnit Platform Launcher, nên các declarations trong dependencies là cần thiết.

**shouldRunAfter('test')** chỉ khuyến nghị thứ tự khi cả hai tasks có mặt trong graph; **không tự chạy test** khi integrationTest được gọi riêng.

**check.dependsOn(integrationTestTask)** nối integration tests vào lifecycle verification. Nếu bỏ dòng này, **./gradlew check** của Java plugin không tự chạy custom integrationTest task.

### 5.3. Task và configuration dự kiến

~~~text
compileJava
processResources
classes
compileTestJava
processTestResources
testClasses
test
compileIntegrationTestJava
processIntegrationTestResources
integrationTestClasses
integrationTest
check
~~~

Configurations:

~~~text
implementation
runtimeOnly
testImplementation
testRuntimeOnly
integrationTestImplementation
integrationTestRuntimeOnly
integrationTestCompileClasspath
integrationTestRuntimeClasspath
~~~

Phân biệt task **integrationTest** với SourceSet **integrationTest**: tên trùng nhưng một bên compile model, một bên execution task.

### 5.4. Chạy lab phương án A

Linux/macOS:

~~~bash
./gradlew clean test
./gradlew integrationTest
./gradlew check
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
.\gradlew.bat integrationTest
.\gradlew.bat check
~~~

Khi testLogging bật streams, các dòng từ test code dự kiến:

~~~text
Unit OK: Xin chào, Lan!
Integration OK: greeting.txt
~~~

Phần task logs/summary có thể khác theo Gradle/OS/parallel scheduling. Không so toàn bộ transcript như expected output duy nhất.

### 5.5. SourceSet không nhất thiết cùng tên Test task

Ví dụ tài liệu Gradle dùng source set **intTest**, nhưng Test task có thể tên **integrationTest**:

~~~groovy
sourceSets {
    intTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

tasks.register('integrationTest', Test) {
    testClassesDirs = sourceSets.intTest.output.classesDirs
    classpath = sourceSets.intTest.runtimeClasspath
    useJUnitPlatform()
}
~~~

Đây chỉ là **fragment**, cần thêm dependencies/configurations/JUnit runner và repository. Nó minh họa source set quyết định tên **compileIntTestJava/intTestImplementation** còn task kiểm thử có thể mang tên khác.

## 6. Phương án B: JVM Test Suite DSL

**Thay toàn bộ build.gradle của phương án A** bằng nội dung dưới đây. Java sources ở mục 4 giữ nguyên.

### 6.1. build.gradle phương án B

~~~groovy
plugins {
    id 'java'
    // java plugin đã tự áp jvm-test-suite trong Gradle hiện đại.
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

testing {
    suites {
        // Built-in suite: khai báo framework mong muốn.
        test {
            useJUnitJupiter('5.11.4')
        }

        // Suite mới được Gradle quản lý.
        integrationTest(JvmTestSuite) {
            useJUnitJupiter('5.11.4')

            dependencies {
                // Cần thiết nếu test code truy cập lớp sản phẩm.
                implementation project()
            }

            targets {
                all {
                    testTask.configure {
                        shouldRunAfter 'test'
                    }
                }
            }
        }
    }
}

tasks.withType(Test).configureEach {
    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }
}

tasks.named('check') {
    dependsOn testing.suites.integrationTest
}
~~~

### 6.2. JVM Test Suite làm gì tự động?

Khi khai báo **integrationTest(JvmTestSuite)**, plugin:

- Tạo SourceSet và conventions **src/integrationTest/java/resources**.
- Tạo compile/resources/classes tasks.
- Tạo dependency configurations như **integrationTestImplementation**, **integrationTestRuntimeOnly**.
- Tạo target mặc định với Test task **integrationTest**.
- Kết nối test classes, runtime classpath và framework với Test task.
- Tạo suite-scoped dependencies DSL và outgoing test result variant.

Bạn **không cần** viết thủ công:

~~~groovy
sourceSets {
    integrationTest {}
}
tasks.register('integrationTest', Test) {
    ...
}
~~~

Thêm chúng vào file B có thể gây trùng tên, vì suite đã tạo cấu trúc tương ứng.

### 6.3. Tại sao phải thêm implementation project()?

Theo tài liệu Gradle, **chỉ built-in test suite** mặc định có thể thấy production dependencies/outputs theo convention. **Suite bổ sung không mặc nhiên phụ thuộc code sản phẩm của project**.

Trong B:

~~~groovy
dependencies {
    implementation project()
}
~~~

nằm bên trong **integrationTest(JvmTestSuite)**. Dòng này bổ sung **project dependency** tới chính module hiện tại, tạo compile/runtime access tới production code và những dependencies được công bố theo variants phù hợp.

Nếu bỏ nó, **GreetingFileStoreIT.java** có thể không compile vì không tìm thấy **GreetingFileStore**. Đừng đoán suite biết “integrationTest” phải test project hiện tại chỉ qua tên.

### 6.4. useJUnitJupiter() không giống Test.useJUnitPlatform()

**Test.useJUnitPlatform()** chọn test framework runner cho một Test task; bạn vẫn phải cung cấp compile/runtime dependencies.

**JvmTestSuite.useJUnitJupiter('5.11.4')** có trách nhiệm cấu hình framework đồng thời thêm JUnit-related dependencies cho suite và cấu hình targets thực thi tương ứng. JvmTestSuite cũng hỗ trợ methods framework khác theo Gradle API.

Ở built-in **test** suite, nếu muốn JUnit Jupiter, gọi **test { useJUnitJupiter(...) }** tường minh. Built-in test suite giữ backward compatibility với JUnit 4 conventions, trong khi additional suites mặc định thường dùng JUnit Jupiter; khai báo version tường minh giảm bất ngờ khi nâng Gradle.

### 6.5. check vẫn cần phụ thuộc suite

~~~groovy
tasks.named('check') {
    dependsOn testing.suites.integrationTest
}
~~~

Nếu bỏ dòng này, **check** không tự bao gồm additional integrationTest suite. **shouldRunAfter('test')** chỉ là ordering mềm, không thêm task vào graph.

Chạy:

~~~bash
./gradlew clean test
./gradlew integrationTest
./gradlew check
~~~

Hai test classes từ mục 4 sẽ chạy với JUnit Jupiter, in những dòng unit/integration đã nêu khi bật testLogging. Không cần tự đặt testClassesDirs/classpath vì suite target đã nối.

### 6.6. Suite không tự chuẩn bị database hoặc external service

Tên integrationTest không làm Gradle tự chạy Docker, mở server, tạo database hoặc dọn resources. Nếu suite thực sự phụ thuộc service, cần khai báo setup/cleanup tasks/Build Services/provisioning và dùng **dependsOn/finalizedBy** đúng nơi. Suite chỉ giúp quản lý nguồn, framework, dependencies và tasks.

## 7. So sánh classpath và dependencies sâu hơn

### 7.1. Main output vs implementation configuration

Trong A:

~~~groovy
sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}
configurations {
    integrationTestImplementation.extendsFrom implementation
    integrationTestRuntimeOnly.extendsFrom runtimeOnly
}
~~~

**sourceSets.main.output** chứa project classes/resources. **implementation** chứa external library dependencies được khai báo cho production code. Đây là **hai loại dữ liệu khác nhau**. ExtendsFrom implementation không tự đưa compiled main classes vào classpath; chỉ thêm main.output cũng chưa bảo đảm đủ external dependencies.

Trong B:

~~~groovy
integrationTest(JvmTestSuite) {
    dependencies {
        implementation project()
    }
}
~~~

**project()** là một project dependency có variant-aware resolution. Tùy publication/variants, nó cung cấp production outputs cùng những dependencies được expose thích hợp ở compile/runtime.

### 7.2. testImplementation không tự thêm cho integrationTest

Ngay cả khi cả hai nằm trong cùng project, **testImplementation** và **integrationTestImplementation** là hai configurations khác nhau. Nếu JUnit/Mockito/AssertJ chỉ khai báo ở testImplementation trong manual A, integrationTest không tự thấy chúng.

Với B:

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            dependencies {
                implementation 'org.assertj:assertj-core:3.27.6'
            }
        }
    }
}
~~~

Đây là fragment, không phải file độc lập. Dependency thêm vào **integrationTestImplementation** bởi suite DSL, không phải global **implementation** của production. Version chỉ để minh họa, nên dùng bản được tổ chức phê duyệt trong project thật.

### 7.3. Framework dependency nào cần tự khai báo?

| Nhu cầu | SourceSet + Test | JvmTestSuite |
| --- | --- | --- |
| JUnit Jupiter compile/runtime | **integrationTestImplementation** | **useJUnitJupiter(version)** |
| JUnit Platform Launcher | **integrationTestRuntimeOnly** | Framework method thiết lập runtime tương ứng |
| Helper thư viện test-only | integrationTestImplementation | suite.dependencies.implementation |
| Dependency chỉ runtime | integrationTestRuntimeOnly | suite.dependencies.runtimeOnly |
| Project code | main.output + main deps | suite.dependencies.implementation project() |
| Test fixtures | integrationTestImplementation testFixtures(project()) | suite.dependencies.implementation testFixtures(project()) |

Phải xem resolved graph khi debug, không chỉ nhìn tên configurations.

### 7.4. Những thay đổi Gradle 9 cần để ý

Tài liệu Gradle nêu rằng trước Gradle 9, một số internal dependencies vô tình rò sang test runtime classpath, che trường hợp thiếu JUnit launcher/engine. Từ Gradle 9, nếu dùng **manual Test task**, hãy khai báo runtime dependencies rõ; không kỳ vọng Gradle “tình cờ” cung cấp chúng.

Tương tự, custom Test tasks không nên dựa vào convention ngầm rằng tất cả Test tasks tự gắn built-in **test** SourceSet. Cấu hình **testClassesDirs/classpath** tường minh, như phương án A, là đúng và bền hơn.

### 7.5. Isolation và phiên bản

Một lý do tách test suites là các nhóm kiểm thử có các dependency khác nhau: integration tests cần JDBC client, Testcontainers hoặc HTTP test client, còn unit tests không cần. Nếu để mọi integration dependencies trong testImplementation, unit test classpath lớn lên, có thể tăng xung đột version/thời gian resolve. Dùng đúng configurations giúp các graphs dễ hiểu.

## 8. Multi-target của JVM Test Suite

**Một suite có thể có nhiều targets**. Mỗi target sở hữu Test task riêng nhưng **chia sẻ SourcesSet, framework và suite dependencies**. Đây là một điểm mạnh khi muốn chạy cùng integration tests với Java 17 và Java 21.

Trong B, **mở rộng block integrationTest đã có**, không đăng ký thêm suite cùng tên:

~~~groovy
integrationTest(JvmTestSuite) {
    useJUnitJupiter('5.11.4')
    dependencies {
        implementation project()
    }

    targets {
        register('integrationTestOn21') {
            testTask.configure {
                javaLauncher = javaToolchains.launcherFor {
                    languageVersion = JavaLanguageVersion.of(21)
                }
            }
        }
    }
}
~~~

Fragment trên giả định project đã áp Java plugin, JDK21 được phát hiện hoặc provisioned và test classfiles tương thích. Sau khi bổ sung, default target vẫn có Test task **integrationTest**, và target bổ sung có Test task riêng để chạy cùng test sources.

**Không tạo thêm một SourceSet** cho target thứ hai. Nếu muốn **tests khác hoặc dependencies khác**, hãy khai báo **suite mới** thay vì chỉ thêm target.

### 8.1. Manual tương đương bằng task thứ hai

~~~groovy
tasks.register('integrationTestOn21', Test) {
    group = 'verification'
    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Fragment cho A, cần SourceSet/Dependencies đã được khai báo. Manual làm được tương tự, nhưng lặp lại testClassesDirs/classpath/useJUnitPlatform.

### 8.2. Runtime JVM khác compilation target

Nếu test classes được compile thành **Java 21 major version 65**, target chạy Java17 sẽ lỗi **UnsupportedClassVersionError**. Để chạy trên cả Java17/21, compile source bằng JDK phù hợp với **options.release = 17**, và đảm bảo dependencies hỗ trợ Java17. Đổi **javaLauncher** không tự biên dịch lại test sources.

### 8.3. Nhiều suites khi muốn nguồn khác nhau

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            dependencies { implementation project() }
        }
        functionalTest(JvmTestSuite) {
            dependencies { implementation project() }
        }
    }
}
~~~

Đây là fragment minh họa cho project chưa đăng ký hai suites; framework, sources, check lifecycle còn phải cấu hình theo nhu cầu. Các suites có source directories riêng **src/integrationTest/java** và **src/functionalTest/java**.

**Nguyên tắc:** cùng source/framework/dependencies nhưng chạy nhiều environments → **nhiều targets trong một suite**; khác source hoặc dependencies/framework → **nhiều suites**.

## 9. Lifecycle: check, shouldRunAfter, dependsOn, finalizedBy

### 9.1. Check có bao gồm integration tests không?

**test** built-in mặc định nằm trong **check** của Java plugin, nhưng custom Test task/additional suite **không tự được thêm** vào check.

Manual:

~~~groovy
tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
~~~

Suite:

~~~groovy
tasks.named('check') {
    dependsOn testing.suites.integrationTest
}
~~~

Nếu CI chỉ gọi **./gradlew check** và không có wiring, integration tests có thể **không chạy** dù build trả về SUCCESSFUL. Hãy kiểm tra task graph.

### 9.2. Phân biệt task relationships

| API | Ý nghĩa thực tế |
| --- | --- |
| **dependsOn(test)** | Đưa task test vào task graph khi chạy task phụ thuộc |
| **shouldRunAfter(test)** | Gợi ý thứ tự nếu cả hai task đã trong graph |
| **mustRunAfter(test)** | Bắt buộc thứ tự nếu cả hai đã trong graph |
| **finalizedBy(cleanup)** | Gắn finalizer/cleanup theo semantics Gradle sau khi task được thực thi |

Thêm shouldRunAfter **không tự tạo dependency** tới test. Phần lớn integration tests chạy chậm nên nên xếp sau unit tests; docs ưu tiên **shouldRunAfter** khi không cần thứ tự cứng để Gradle vẫn có tự do parallel scheduling.

### 9.3. Chính sách CI

Bạn có thể chọn:

~~~text
PR pipeline:       ./gradlew test
Merge pipeline:    ./gradlew check
Nightly pipeline:  ./gradlew integrationTest
~~~

Nếu đã nối integrationTest vào check, merge sẽ chạy thêm integration tests. Nếu không nối, phải gọi nó tường minh. Không có một chính sách mặc định đúng cho mọi dự án; điều quan trọng là **CI biết chính xác task nào chạy**.

### 9.4. External service setup/cleanup

Khi integration tests cần database/service:

~~~text
startDatabase -> integrationTest -> stopDatabase
~~~

Hãy quản lý resources và credentials an toàn, ví dụ setup task/Build Services/Testcontainers, **dependsOn** để khởi tạo, **finalizedBy** để cleanup. Không giả định chỉ cần đặt tên suite là integrationTest thì Gradle tự quản lý database.

## 10. Kotlin DSL: hai cấu hình tương đương

Dưới đây là hai **file build.gradle.kts thay thế nhau**, không dán chung.

### 10.1. Phương án A Kotlin

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

val integrationTest by sourceSets.creating {
    compileClasspath += sourceSets.main.get().output
    runtimeClasspath += sourceSets.main.get().output
}

configurations[integrationTest.implementationConfigurationName]
    .extendsFrom(configurations["implementation"])
configurations[integrationTest.runtimeOnlyConfigurationName]
    .extendsFrom(configurations["runtimeOnly"])

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")

    add(
        integrationTest.implementationConfigurationName,
        platform("org.junit:junit-bom:5.11.4")
    )
    add(
        integrationTest.implementationConfigurationName,
        "org.junit.jupiter:junit-jupiter"
    )
    add(
        integrationTest.runtimeOnlyConfigurationName,
        "org.junit.platform:junit-platform-launcher"
    )
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

val integrationTestTask = tasks.register<Test>("integrationTest") {
    group = "verification"
    description = "Runs integration tests"
    testClassesDirs = integrationTest.output.classesDirs
    classpath = integrationTest.runtimeClasspath
    useJUnitPlatform()
    shouldRunAfter("test")
}

tasks.withType<Test>().configureEach {
    testLogging {
        events("passed", "failed", "skipped")
        showStandardStreams = true
    }
}

tasks.named("check") {
    dependsOn(integrationTestTask)
}
~~~

Dùng biến **integrationTest** cho SourceSet, **integrationTestTask** cho TaskProvider để không nhầm hai kiểu. Cú pháp **add(configName, dependency)** khai báo dependencies đúng configuration được sinh từ SourceSet.

### 10.2. Phương án B Kotlin

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

testing {
    suites {
        named<JvmTestSuite>("test") {
            useJUnitJupiter("5.11.4")
        }

        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter("5.11.4")
            dependencies {
                implementation(project())
            }
            targets {
                all {
                    testTask.configure {
                        shouldRunAfter("test")
                    }
                }
            }
        }
    }
}

tasks.withType<Test>().configureEach {
    testLogging {
        events("passed", "failed", "skipped")
        showStandardStreams = true
    }
}

tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}
~~~

Kotlin dùng **named<JvmTestSuite>** cho built-in suite, **register<JvmTestSuite>** cho suite mới. Test task wiring nằm trong suite.

### 10.3. Đổi thư mục nguồn suite

Nếu muốn code ở **src/it/java** thay vì **src/integrationTest/java**:

Groovy (fragment trong suite đã tồn tại):

~~~groovy
integrationTest {
    sources {
        java {
            srcDirs = ['src/it/java']
        }
    }
}
~~~

Kotlin (fragment):

~~~kotlin
named<JvmTestSuite>("integrationTest") {
    sources {
        java {
            setSrcDirs(listOf("src/it/java"))
        }
    }
}
~~~

**Đổi srcDirs chỉ thay nơi Gradle tìm source files; nó không tự di chuyển files.** Nếu code vẫn ở đường dẫn cũ, compilation có thể **NO-SOURCE** và integrationTest không chạy case nào.

## 11. Migrate an toàn: không khai báo cả hai cách cùng lúc

Một project đang có:

~~~groovy
sourceSets {
    integrationTest {
        // ...
    }
}
tasks.register('integrationTest', Test) {
    // ...
}
~~~

Nếu bạn thêm:

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            // ...
        }
    }
}
~~~

vào cùng build, hai hệ thống cùng định tạo SourceSet/task **integrationTest**, có thể gây **task already exists**, duplicate source set hoặc nhiều cấu hình chồng nhau.

**Migration cần thay thế cấu hình, không cộng thêm cấu hình.**

### 11.1. Quy trình migration

1. Ghi nhận SourceSet name, sourceDirs, resourceDirs và custom Test task name cũ.
2. Chạy tests, ghi test count, duration và reports trước khi sửa.
3. Lưu cấu hình classpath, JUnit/framework version, runtimeOnly, test fixtures, JVM args, heap, filters.
4. Định nghĩa suite cùng mục đích bằng **testing.suites**.
5. Di chuyển dependency declarations từ configurations thủ công sang **suite.dependencies**.
6. Thêm **implementation project()** nếu test import code sản phẩm.
7. Chuyển **useJUnitPlatform()** thành **useJUnitJupiter()** của suite khi dùng Jupiter.
8. Chuyển Test-specific options sang **targets { all { testTask.configure { ... } } }** hoặc Test task config đã được suite tạo.
9. Xóa manual SourceSet/Test registration trùng tên.
10. Nối lại **check.dependsOn** hoặc CI job riêng.
11. Chạy **./gradlew tasks --all**, **integrationTest**, **check**, so test counts/reports trước và sau.
12. Kiểm tra **integrationTestRuntimeClasspath** và các artifact transitive để phát hiện dependency leakage/thiếu version.

### 11.2. Không đổi đường dẫn nguồn ngầm

Manual SourceSet có thể tên **intTest** với nguồn **src/intTest/java**, Test task tên **integrationTest**. Nếu chuyển sang suite **integrationTest**, convention mới sẽ dùng **src/integrationTest/java**. Cần **chuyển file** hoặc cấu hình **sources.java.srcDirs** phù hợp. Nếu không, task có thể báo NO-SOURCE mà build vẫn xanh.

### 11.3. So sánh dependency graph

Trước và sau migration:

~~~bash
./gradlew dependencies --configuration integrationTestCompileClasspath
./gradlew dependencies --configuration integrationTestRuntimeClasspath
./gradlew dependencyInsight --dependency org.junit.jupiter --configuration integrationTestRuntimeClasspath
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration integrationTestRuntimeClasspath
.\gradlew.bat dependencyInsight --dependency org.junit.jupiter --configuration integrationTestRuntimeClasspath
~~~

Cùng tên configuration không bảo đảm **resolved dependencies** giống nhau: manual dùng main.output + extendsFrom, suite dùng variant-aware **project()**; có thể làm rõ một sai lệch classpath lâu nay bị che giấu.

## 12. JUnit, Test Fixtures và report aggregation

### 12.1. JUnit dependencies phải đúng scope

Trong manual approach:
- **testImplementation** dành cho unit tests.
- **integrationTestImplementation** dành cho integration tests.
- **integrationTestRuntimeOnly** có thể cần JUnit Platform launcher.

Trong JVM Test Suite:
- **test.useJUnitJupiter()** và **integrationTest.useJUnitJupiter()** cấu hình framework cho từng suite.
- **suite.dependencies.implementation** chỉ thêm dependency cho suite đang xét.
- Không nhầm block **dependencies** trong suite với top-level **dependencies** cho source set main.

### 12.2. Test fixtures

Gradle **java-test-fixtures** plugin có **src/testFixtures/java** và variants riêng. Khi JVM Test Suite cần fixtures:

~~~groovy
plugins {
    id 'java-library'
    id 'java-test-fixtures'
}

testing {
    suites {
        integrationTest(JvmTestSuite) {
            dependencies {
                implementation project()
                implementation testFixtures(project())
            }
        }
    }
}
~~~

Đây là fragment kiến trúc; giả định suite chưa đăng ký và project có plugin để publish fixtures variant. Manual tương đương:

~~~groovy
dependencies {
    integrationTestImplementation testFixtures(project())
}
~~~

Không dùng **testFixtures(project())** khi producer không cung cấp fixture variant. Với multi-project, **testFixtures(project(':support'))** dùng fixtures do project :support công bố, khác với **project(':support')** lấy production code.

### 12.3. Reporting

Cả hai phương án đều thực thi qua Test task nên đều có HTML/JUnit XML reports và test logs:

~~~groovy
tasks.withType(Test).configureEach {
    reports {
        junitXml.required = true
        html.required = true
    }
}
~~~

Tuy nhiên, JVM Test Suite còn tạo **outgoing test results variants** theo mô hình test suites, có thể được **Test Report Aggregation plugin** sử dụng. Manual Test task không tự có cùng model outgoing variant. Điều này hữu ích khi tổng hợp nhiều suite từ nhiều modules.

**Không kết luận manual Test task không tạo reports.** Khác biệt là mức độ model hóa kết quả phục vụ những plugin khác.

### 12.4. Performance/caching

Integration tests thường liên quan external services, filesystem hoặc network. Dù được tổ chức bằng SourceSet hay suite, phải quản lý test isolation, resource cleanup và những điều kiện môi trường ảnh hưởng kết quả. Build cache/up-to-date checks không thay thế test correctness nếu môi trường ngoài thay đổi mà Gradle không biết.

## 13. Lệnh debug cốt lõi

~~~bash
./gradlew tasks --all
./gradlew help --task integrationTest
./gradlew dependencies --configuration integrationTestCompileClasspath
./gradlew dependencies --configuration integrationTestRuntimeClasspath
./gradlew integrationTest --info
./gradlew check --dry-run
~~~

Chúng giúp:

1. Xem **integrationTest** task có thật không.
2. Kiểm tra **compileIntegrationTestJava** và **integrationTestClasses** có trong task graph.
3. Xác minh JUnit/test runner dependencies được resolve.
4. Xem source set runtime classpath có chứa code sản phẩm không.
5. Xem **check** có gọi integrationTest theo policy không.
6. Kiểm tra NO-SOURCE hoặc không tìm thấy tests.

**--dry-run** chỉ preview scheduling, không chạy tests; BUILD SUCCESSFUL từ dry-run **không chứng minh bài test pass**.

Sau compile:

~~~bash
./gradlew compileIntegrationTestJava
~~~

Nếu Gradle dùng layout thông thường, class file:

~~~text
build/classes/java/integrationTest/demo/GreetingFileStoreIT.class
~~~

Nếu không có, kiểm tra srcDirs, class name/package, compile errors và những plugins đã đổi output paths.

## 14. Troubleshooting theo tình huống

| Hiện tượng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Có compileIntegrationTestJava nhưng không có integrationTest | Manual chỉ tạo SourceSet | Register Test task |
| integrationTest **NO-SOURCE** | Sai srcDirs hoặc chưa có test Java | Kiểm tra convention và files |
| **cannot find symbol GreetingFileStore** | Compile classpath thiếu main code | Manual thêm main.output, suite implementation project() |
| **NoClassDefFoundError** | Runtime classpath thiếu project/dependency | Kiểm tra main.output, extendsFrom, suite dependencies |
| TestEngine/Launcher không tìm thấy | JUnit runtime artifacts thiếu | Manual khai báo jupiter/launcher, suite useJUnitJupiter đúng |
| Gradle 9 không chạy custom Test task | Thiếu testClassesDirs/classpath conventions | Gán tường minh |
| **No tests found** | Sai source roots, filters, framework | Xem compile outputs, Test task config |
| **check** bỏ integration tests | Chưa dependsOn | Nối check đúng policy |
| Chỉ shouldRunAfter nhưng unit không chạy | shouldRunAfter không phải dependsOn | Thêm dependency khi cần |
| Trùng task tên integrationTest | Manual và suite cùng register | Chọn một cấu hình, migrate đúng |
| Unit có Mockito nhưng integration không | Configurations tách biệt | Thêm library vào integrationTest scope |
| Suite không thấy production outputs | Thiếu implementation project() | Thêm project dependency |
| Tests JUnit chạy trong IDE nhưng Gradle không | IDE runner/classpath khác | Chạy Gradle tasks và xem reports |
| Build ở Gradle9 lỗi JUnit runtime | Internal classpath leakage cũ bị loại | Khai báo dependencies đầy đủ |
| JDK chạy test không hỗ trợ bytecode | Target JVM/classfile mismatch | Dùng options.release/toolchain phù hợp |
| Multi-target Java17 fail, Java21 pass | Bytecode/dep chỉ hỗ trợ Java21 | Compile target17 hoặc đổi compatibility policy |
| Test fixtures variant not found | Producer không áp java-test-fixtures | Thêm plugin hoặc sửa dependency |
| Integration test lỗi cổng DB | Service setup/cleanup không đúng | Quản lý resources/port/credentials |
| Maven Central không truy cập được | Repository/proxy/network lỗi | Dùng mirror hợp lệ/cache |
| Check reports thiếu integrationTest | Task chưa chạy hoặc aggregation config | Kiểm tra graph và test result variants |

### 14.1. Quy trình xử lý lỗi nhanh

1. **./gradlew tasks --all**: test task có tồn tại?
2. **./gradlew compileIntegrationTestJava**: source compile thành công?
3. Xem **build/classes/java/integrationTest** và srcDirs.
4. **./gradlew dependencies --configuration integrationTestRuntimeClasspath**: framework/project dependencies có đủ?
5. **./gradlew integrationTest --info**: runner có tìm thấy tests?
6. **./gradlew check --dry-run**: test task có trong check?
7. Nếu framework lỗi, phân biệt **Test.useJUnitPlatform** và **suite.useJUnitJupiter**.
8. Nếu migrate, tìm manual SourceSet/Test task registration trùng suite name.

## 15. Bài tập tự kiểm tra kèm đáp án

### Bài 1 — Chỉ tạo SourceSet

~~~groovy
sourceSets {
    integrationTest {}
}
~~~

**Hỏi:** integration tests sẽ tự chạy chưa? **Đáp án:** chưa. Compilation tasks được tạo nhưng cần Test task để thực thi.

### Bài 2 — Test task cần khai báo gì?

**Đáp án:** testClassesDirs, classpath, framework và runtime dependencies. Không dựa vào implicit test SourceSet conventions của các Gradle versions cũ.

### Bài 3 — Suite bổ sung không tìm thấy GreetingFileStore

**Đáp án:** thêm **dependencies { implementation project() }** bên trong suite integrationTest. Additional suite không tự phụ thuộc production code.

### Bài 4 — useJUnitPlatform và useJUnitJupiter giống nhau?

**Đáp án:** không. Test.useJUnitPlatform chỉ chọn framework runner. Suite.useJUnitJupiter còn cấu hình framework dependencies và các targets.

### Bài 5 — Chạy check nhưng không thấy integration tests

**Đáp án:** cần check.dependsOn manual task hoặc suite, hoặc gọi integrationTest trực tiếp trong CI. Additional suite không tự nối check.

### Bài 6 — shouldRunAfter có chạy test không?

**Đáp án:** không. Nó chỉ điều phối thứ tự nếu tasks đều trong graph.

### Bài 7 — Dùng cùng lúc manual integrationTest và suite integrationTest?

**Đáp án:** không nên, vì có thể trùng SourceSet/Task name. Chọn một mô hình, migrate bằng cách gỡ cấu hình cũ.

### Bài 8 — Tại sao SourceSet phải thêm main.output?

**Đáp án:** đó là compiled production classes/resources; extendsFrom implementation chỉ góp external dependency declarations, không tự thêm main class files.

### Bài 9 — Muốn hai Test JVMs cho cùng source?

**Đáp án:** cùng suite nhiều targets hoặc manual hai Test tasks cùng testClassesDirs/classpath. Ensure classfile và dependencies hỗ trợ JVM nhỏ nhất.

### Bài 10 — Muốn source code khác nhau?

**Đáp án:** tạo suite/SourceSet khác, không chỉ target mới, vì targets của cùng suite chia sẻ sources.

### Bài 11 — JUnit engine tự có trong manual Test task?

**Đáp án:** không thể giả định. useJUnitPlatform() cần JUnit runtime dependencies; khai báo jupiter và launcher đúng configurations.

### Bài 12 — JVM Test Suite có framework mặc định?

**Đáp án:** built-in test suite giữ conventions JUnit4 để tương thích cũ; additional suites mặc định có JUnit Jupiter. Nên khai báo useJUnitJupiter(version) rõ ràng để kiểm soát.

### Bài 13 — Vì sao src/intTest/java bị NO-SOURCE sau migration?

**Đáp án:** suite integrationTest theo convention tìm src/integrationTest/java. Di chuyển sources hoặc cấu hình sources.java.srcDirs.

### Bài 14 — Manual tests có reports không?

**Đáp án:** có HTML/JUnit XML reports từ Test task. Suite còn mô hình hóa outgoing test result variants cho aggregation.

### Bài 15 — API nào còn incubating?

**Đáp án:** JVM Test Suite plugin/API hiện vẫn đánh dấu incubating trong tài liệu. SourceSet/Test API là những API nền tảng lâu đời.

### Bài 16 — Khi nào chọn manual?

**Đáp án:** khi build cũ đã ổn, muốn tối đa hóa điều khiển chi tiết, API ổn định hoặc wiring classpath rất đặc thù.

### Bài 17 — Khi nào chọn suite?

**Đáp án:** khi có nhiều test groups, framework/dependency config nhất quán, multi-target JVM và aggregation, chấp nhận API incubating.

### Bài 18 — DB integration tests có tự setup nhờ suite?

**Đáp án:** không. Phải thiết kế setup/cleanup, Build Services/Testcontainers hoặc tasks liên quan và bảo vệ credentials.

## 16. Checklist trước khi merge/triển khai

- [ ] Chỉ chọn **một** phương pháp tạo integrationTest SourceSet/task.
- [ ] Biết SourceSet chỉ đảm nhiệm compilation, Test task đảm nhiệm execution.
- [ ] Tên source set/suite và **src/integrationTest/java** khớp.
- [ ] JavaCompile task **compileIntegrationTestJava** có source thật.
- [ ] Manual Test task đặt testClassesDirs và classpath đầy đủ.
- [ ] Manual JUnit có compile/runtime JUnit dependencies và launcher.
- [ ] JVM suite gọi useJUnitJupiter đúng phiên bản.
- [ ] Suite bổ sung có **implementation project()** khi import production code.
- [ ] integrationTestImplementation không bị nhầm với testImplementation.
- [ ] check.dependsOn integrationTest phù hợp CI policy.
- [ ] shouldRunAfter không bị coi như task dependency.
- [ ] Test tasks/targets ghi reports và log lỗi rõ.
- [ ] Nếu multi-target, bytecode/dependencies tương thích JVM thấp nhất.
- [ ] Unit tests và integration tests thật sự chạy, có số test cases mong đợi.
- [ ] Không dựa vào BUILD SUCCESSFUL khi task bị NO-SOURCE.
- [ ] Nếu cần fixtures, producer cung cấp java-test-fixtures variants.
- [ ] External services có setup/cleanup/isolation/secret policy.
- [ ] Gradle Wrapper/Java version được CI hỗ trợ.
- [ ] Nếu chọn suite, có quy trình theo dõi API incubating khi nâng Gradle.

## Tài liệu tham khảo chính thức

- [Gradle JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): suite, targets, frameworks, dependencies, production project(), lifecycle, outgoing results, incubating status.
- [Gradle Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): manual source sets, Test task, framework/runtime dependencies, Gradle 9 behavior và troubleshooting.
- [Gradle Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): SourceSet conventions và tasks.
- [Gradle JvmTestSuite Javadoc](https://docs.gradle.org/current/javadoc/org/gradle/api/plugins/jvm/JvmTestSuite.html): SourceSet, framework, targets, Since 7.3.
- [Gradle Test Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): testClassesDirs, classpath, runner, reports.
- [Gradle SourceSet API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.SourceSet.html): compile/runtime classpaths và outputs.
- [Gradle Java Test Fixtures](https://docs.gradle.org/current/userguide/java_testing.html#sec:java_test_fixtures): fixtures scope, variant-aware dependency.
- [Gradle Test Report Aggregation Plugin](https://docs.gradle.org/current/userguide/test_report_aggregation_plugin.html): aggregation của test results.
- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): Gradle/Java versions.

**Kết luận:** SourceSet là **mô hình nguồn và biên dịch**; Test task là **công việc thực thi tests**; JvmTestSuite là **cấu hình cấp cao gồm SourceSet + dependencies + framework + test targets**. Manual cho khả năng kiểm soát và API nền tảng ổn định nhưng phải tự wiring classpath/lifecycle. JVM Test Suite giảm boilerplate, thuận tiện khi nhiều nhóm/targets và reporting, song API còn incubating. Dù theo cách nào, hãy kiểm chứng **mã sản phẩm có trên classpath, JUnit runtime đầy đủ, check thật sự chạy integration tests, và test reports có đúng case đã thực thi**.