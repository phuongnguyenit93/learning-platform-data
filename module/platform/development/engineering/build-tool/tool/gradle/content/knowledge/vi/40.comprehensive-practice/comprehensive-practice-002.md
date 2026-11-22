# Thiết kế thư viện Java công khai API rõ ràng và xuất bản thử bằng Gradle

## 1. Bài thực hành tổng hợp: từ thiết kế API đến một artifact có thể tiêu thụ

Bài thuộc nhóm **Thực hành tổng hợp** của chủ đề **Build Tool Gradle**. Mục tiêu là hoàn thành một chu trình thực tế: **thiết kế thư viện Java 17 có public API dễ hiểu, tách implementation dependencies khỏi public contract, viết unit tests, tạo JAR/sources/Javadoc, xuất bản thử qua Maven repository cục bộ, rồi dùng một ứng dụng độc lập tiêu thụ chính artifact đã xuất bản**.

Khi một thư viện `./gradlew :library:build` thành công, điều đó mới chứng minh nó tự biên dịch và tự kiểm thử. Nó **chưa chứng minh** artifact đã công bố có tọa độ đúng, có metadata đúng, không rò implementation dependencies vào compile classpath của consumer, hoặc consumer thật sự chạy được. Vì vậy bài sẽ có **một producer, một published Maven module và một consumer đọc module từ repository** thay vì consumer phụ thuộc trực tiếp `project(":library")`.

Sau bài, bạn có thể:

1. Định nghĩa public API bằng interface, record và factory nhỏ, có tài liệu và hợp đồng ngoại lệ.
2. Giữ implementation class ở package-private, không đưa thư viện nội bộ vào chữ ký công khai.
3. Dùng plugin `java-library` cùng `api`, `implementation`, `compileOnlyApi`, `runtimeOnly`, `testImplementation` đúng ý nghĩa.
4. Chọn Java 17 toolchain/`options.release` để tạo API nhất quán cho consumers.
5. Cài đặt JUnit Jupiter test để kiểm tra public contract, edge cases và Unicode.
6. Tạo JAR, sources JAR, Javadoc JAR và Gradle `maven-publish` từ `components["java"]`.
7. Xuất bản **thử vào repository Maven trên filesystem**, không cần credentials hoặc đụng `~/.m2`/Maven Central.
8. Dùng app `:consumer` resolve artifact qua tọa độ Maven `dev.example:greeting-library:1.0.0`, thay vì project dependency.
9. Phân tích POM runtime scope và Gradle Module Metadata variants `apiElements`/`runtimeElements`.
10. Dùng một Java 17 audit tool độc lập để xác minh JAR classes, sources/Javadoc artifacts, POM và Module Metadata; chạy bằng `javac`/`java` với stdout chính xác.
11. Phân biệt publishing local, Maven Local, staging remote và release production; hiểu bất biến version và supply-chain security.
12. Chẩn đoán lỗi build pass nhưng consumer fail, sai API exposure, 401/403, checksum, stale metadata và Javadoc/test failures.

**Điều quan trọng:** `api` trong Gradle là **dependency configuration**. “Public Java API” là tập type/method/constructor mà consumer được phép sử dụng. Chúng liên quan nhưng không đồng nhất: library có thể công khai API chỉ gồm JDK types và **không cần khai báo một external `api` dependency nào**.

## 2. Thiết kế public contract trước khi viết Gradle

Giả sử thư viện cung cấp lời chào. Consumer chỉ cần biết:

~~~java
GreetingService service = GreetingServices.standard();
GreetingMessage result = service.greet("  Lan   Anh ");
System.out.println(result.text());
~~~

Contract:

- `GreetingService` là **public interface**, cho phép consumer phụ thuộc abstraction.
- `GreetingMessage` là **public Java 17 record**, là kiểu dữ liệu bất biến có accessor `text()`.
- `GreetingServices` là **public factory**, cung cấp implementation mặc định mà không yêu cầu consumer khởi tạo một lớp nội bộ.
- `DefaultGreetingService` là class **package-private**, không được consumer truy cập trực tiếp.
- `greet(String name)` chuẩn hóa chuỗi khoảng trắng; với null/blank name ném `IllegalArgumentException`.
- Output với `"  Lan   Anh "` đúng là `"Xin chào, Lan Anh!"`.
- Consumer không cần biết library xử lý whitespace bằng `org.apache.commons:commons-lang3`.

Một API rõ ràng tránh dùng kiểu phụ thuộc nội bộ trong method signature. Ví dụ không nên công khai:

~~~java
// Chỉ là ANTI-PATTERN minh họa, không thuộc mã chạy của lab:
public org.apache.commons.lang3.mutable.MutableInt greetInternal(
    String name
);
~~~

Nếu `MutableInt` nằm trong public/protected signature, library đã làm lộ Commons Lang types vào ABI, và consumer có thể cần thư viện này trên compile classpath. Khi đó `api("org.apache.commons:commons-lang3:...")` có thể là lựa chọn đúng; nhưng tốt hơn là thiết kế public domain types độc lập nếu chúng không thực sự cần có trong hợp đồng.

### 2.1. Một API tốt nên nói rõ điều gì?

- **Tên và mục đích:** `GreetingService.greet`, không phải `doWork`.
- **Đầu vào/đầu ra:** nhận String, trả về GreetingMessage.
- **Null/empty policy:** null hoặc blank bị từ chối với IllegalArgumentException.
- **Biến đổi dữ liệu:** trim/normalize nhiều dấu cách thành một khoảng trắng.
- **Encoding/ngôn ngữ:** dùng Java Unicode String; Java source files UTF-8.
- **Thread-safety/state:** implementation stateless nên mỗi invocation không lưu mutable shared state.
- **Versioning:** thay đổi public record component hay method signature có thể là breaking change.
- **Extension point:** public interface cho phép người dùng viết implementation riêng.
- **Những gì không cam kết:** internal class, third-party implementation library, classpath ordering.

### 2.2. API-level vs implementation-level compatibility

Nếu đổi `DefaultGreetingService` sang implementation khác nhưng output/exception contract và public ABI giữ nguyên, nhiều consumers không cần sửa. Nếu xóa `GreetingMessage.text()` hoặc đổi `GreetingService.greet` sang nhận `List<String>`, đó là public API/ABI change; đừng chỉ kiểm tra unit tests nội bộ rồi phát hành cùng release version.

## 3. Gradle java-library: dependency separation

Áp dụng:

~~~kotlin
plugins {
    `java-library`
}
~~~

Plugin này mở rộng Java plugin và cung cấp:

| Gradle configuration | Dùng cho | Có trên compile classpath của consumer? |
| --- | --- | --- |
| `api` | Thư viện chứa public types được lộ qua library ABI | Có, trong variant tương ứng |
| `implementation` | Thư viện chỉ cần để compile/run nội bộ | **Không** ở consumer compile classpath; có ở consumer runtime |
| `compileOnlyApi` | Public API compile dependency nhưng không cung cấp runtime | Có ở compile side, không bảo đảm runtime |
| `compileOnly` | Thư viện chỉ cần khi compile library | Không truyền runtime |
| `runtimeOnly` | Thư viện cần lúc chạy, không cần khi compile | Không ở compile, có ở runtime |
| `annotationProcessor` | Annotation processor khi biên dịch library | Không phải public/runtime API |
| `testImplementation` | JUnit/test helpers | Chỉ dùng cho library tests |
| `testRuntimeOnly` | Test engine/launcher | Chỉ cho test runtime |

Các configurations **declarable** như `api`/`implementation` thường không được gọi trực tiếp để resolve file set. Gradle tạo **consumable variants** như `apiElements` và `runtimeElements`, cùng resolvable `compileClasspath`/`runtimeClasspath` cho các tác vụ cụ thể.

Trong lab:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
~~~

`StringUtils` dùng bên trong implementation. Consumer **không được dựa vào Commons Lang3 như một compile-time API kế thừa ngầm**. Nhưng consumer runtime vẫn phải nhận Lang3 vì mã `DefaultGreetingService` sẽ gọi nó.

### 3.1. Vì sao implementation không đồng nghĩa “không publish dependency”?

`implementation` **không bị xóa khỏi runtime dependency graph**. Gradle publication từ Java component sẽ đưa dependency nội bộ vào **runtime variant** của Gradle Module Metadata và thường là Maven POM `runtime` scope, để Java runtime consumer có library cần thiết.

Điều ngược lại mới nguy hiểm: nếu chỉ viết `compileOnly("org.apache.commons:commons-lang3:3.17.0")`, library có thể compile nhưng consumer runtime bị lỗi `NoClassDefFoundError` vì Commons Lang không được đưa vào runtime graph.

### 3.2. Khi nào thật sự dùng api?

Nếu public API là:

~~~java
// Chỉ là mảnh giải thích, không thêm vào lab:
public org.someapi.HttpResponse process(
    org.someapi.HttpRequest request
);
~~~

consumer phải có `HttpRequest`/`HttpResponse` để biên dịch. Khi dependency cung cấp các types này, dùng `api(...)` hoặc một giải pháp compile exposure tương ứng. **Ưu tiên `implementation` khi public ABI không chứa external types**, giúp hạn chế compile classpath, tránh accidental dependency và giảm recompilation.

## 4. Kiến trúc lab: Producer, repository thử và consumer

Sơ đồ:

~~~text
              gradle-library-publication/
                     settings.gradle.kts
                            |
                +-----------+-----------+
                |                       |
                v                       v
             :library               :consumer
        plugin java-library      plugin application
        public Java API          Consumer Java Main
        package-private impl     consumer JUnit smoke test
        MavenPublication         dependency: Maven GAV
                |                       ^
                v                       |
    :library:publish...                  |
                |                       |
                v                       |
    build/local-staging-repository/ -----+
      dev/example/greeting-library/1.0.0/
         greeting-library-1.0.0.jar
         greeting-library-1.0.0.pom
         greeting-library-1.0.0.module
         greeting-library-1.0.0-sources.jar
         greeting-library-1.0.0-javadoc.jar
~~~

**Chủ ý:** Consumer dùng external Maven coordinates, **không** dùng `implementation(project(":library"))`. Vì vậy phải **publish trước, run/test consumer sau**. Gradle không thể tự suy ra task dependency từ một external Maven dependency và automatically gọi producer `publish` trong cùng multi-project build.

### 4.1. Cấu trúc thư mục

~~~text
gradle-library-publication/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── library/
│   ├── build.gradle.kts
│   ├── src/main/java/dev/example/greetings/
│   │   ├── GreetingService.java
│   │   ├── GreetingMessage.java
│   │   ├── GreetingServices.java
│   │   └── DefaultGreetingService.java
│   └── src/test/java/dev/example/greetings/
│       └── GreetingServicesTest.java
├── consumer/
│   ├── build.gradle.kts
│   ├── src/main/java/dev/example/consumer/
│   │   └── Main.java
│   └── src/test/java/dev/example/consumer/
│       └── ConsumerSmokeTest.java
└── tools/
    └── PublicationAudit.java
~~~

Cần: **JDK 17**, Gradle Wrapper tương thích và network/mirror cho Commons Lang3 + JUnit. Nếu dự án chưa có Wrapper, tạo bằng Gradle distribution đáng tin theo version team chọn; commit `gradlew`, `gradlew.bat`, Wrapper JAR và properties. Các mã phía dưới là toàn bộ các file cấu hình/Java nội dung cần thiết, ngoài bộ Wrapper được khởi tạo riêng.

### 4.2. settings.gradle.kts

~~~kotlin
rootProject.name = "gradle-library-publication"
include(":library", ":consumer")
~~~

Không cần root `build.gradle.kts`, vì mỗi module tự định nghĩa plugins/repositories/toolchain. Gradle root directory là vị trí đặt **repository thử** dưới `build/`. Không nhầm với `~/.m2/repository`.

## 5. library/build.gradle.kts — cấu hình producer đầy đủ

~~~kotlin
import org.gradle.api.publish.maven.MavenPublication
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    `java-library`
    `maven-publish`
}

group = "dev.example"
version = "1.0.0"

base {
    archivesName.set("greeting-library")
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }

    withSourcesJar()
    withJavadocJar()
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    reports.junitXml.required.set(true)
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])

            groupId = "dev.example"
            artifactId = "greeting-library"
            version = project.version.toString()

            pom {
                name.set("Greeting Library")
                description.set(
                    "Java 17 greeting API with a hidden Commons Lang implementation"
                )
            }
        }
    }

    repositories {
        maven {
            name = "localStaging"
            url = uri(
                rootProject.layout.projectDirectory
                    .dir("build/local-staging-repository").asFile
            )
        }
    }
}
~~~

Giải thích từng thành phần:

1. `java-library` tạo Java component/variants, JavaCompile, JAR/Javadoc/test tasks.
2. `maven-publish` tạo infrastructure để publish `MavenPublication`.
3. `group`/`version` xác định identity; `base.archivesName` đổi JAR base name theo artifact.
4. `withSourcesJar()` và `withJavadocJar()` đăng ký nguồn/Javadoc variants để xuất bản cùng component.
5. Java 17 toolchain và `options.release.set(17)` giữ API/JDK compatibility.
6. `implementation(commons-lang3)` không làm lộ Lang3 cho consumer compile.
7. JUnit Jupiter ở **test** scope, không publish thành runtime dependency của thư viện.
8. `from(components["java"])` giữ metadata của Java library: không publish “JAR trần” rồi bỏ mất dependency declarations.
9. Publication identity tường minh `dev.example:greeting-library:1.0.0`, dễ audit.
10. Maven repository **file-based** nằm tại project root `build/local-staging-repository`; nó không cần username/password và không gửi byte nào lên Maven Central.

**Không copy thẳng các version demo để release:** Commons Lang3 3.17.0 và JUnit 5.11.4 được pin nhằm giúp ví dụ ổn định; production phải theo catalog/locking/security policy. `mavenCentral()` là nguồn ví dụ; doanh nghiệp có thể dùng mirror/proxy repository đã kiểm duyệt.

### 5.1. Vì sao không cấu hình mavenLocal() ở producer?

`publishToMavenLocal` là một task khác do Maven Publish plugin cung cấp, thường ghi vào Maven local repository của người dùng. Bài này **cố ý dùng repository thử trong project** để:

- Dễ quan sát chính xác các artifacts/POM/module metadata.
- Tránh làm bẩn `~/.m2/repository` của developer.
- Không làm consumer vô tình dùng artifact cũ cùng tọa độ từ máy khác.
- Có thể xóa thư mục thử khi cần, không ảnh hưởng Maven Local hoặc remote registry.
- Thể hiện rõ repository URL và publish task.

## 6. Public API: các kiểu Java 17

### 6.1. GreetingService.java — public interface

File `library/src/main/java/dev/example/greetings/GreetingService.java`:

~~~java
package dev.example.greetings;

/**
 * Contract for producing a greeting from a human-readable name.
 */
public interface GreetingService {

    /**
     * Returns a greeting message for the given name.
     *
     * @param name a non-null, non-blank human-readable name
     * @return a structured greeting result
     * @throws IllegalArgumentException if name is null or blank
     */
    GreetingMessage greet(String name);
}
~~~

Không phụ thuộc `StringUtils` ở signature. Nếu consumer chỉ sử dụng interface và record, compile-time contract không gắn với Commons Lang.

### 6.2. GreetingMessage.java — public immutable record

File `library/src/main/java/dev/example/greetings/GreetingMessage.java`:

~~~java
package dev.example.greetings;

import java.util.Objects;

/**
 * Immutable value object representing a fully formatted greeting.
 *
 * @param text non-null human-readable greeting text
 */
public record GreetingMessage(String text) {

    public GreetingMessage {
        Objects.requireNonNull(text, "text");
    }
}
~~~

Java 17 `record` tạo accessor `text()`, `equals`, `hashCode` và `toString` theo semantics record. Compact constructor kiểm tra null. Public record components trở thành một phần ABI; thay component names/types có thể gây breaking changes với consumers.

### 6.3. GreetingServices.java — public factory

File `library/src/main/java/dev/example/greetings/GreetingServices.java`:

~~~java
package dev.example.greetings;

/**
 * Entry point for obtaining supported GreetingService implementations.
 */
public final class GreetingServices {

    private GreetingServices() {
    }

    /**
     * Creates a stateless default greeting service.
     *
     * @return a default GreetingService implementation
     */
    public static GreetingService standard() {
        return new DefaultGreetingService();
    }
}
~~~

Factory trả interface, không trả concrete implementation type. Consumer có thể viết `GreetingServices.standard()` mà không cần biết tên nội bộ.

## 7. Implementation riêng: DefaultGreetingService.java

File `library/src/main/java/dev/example/greetings/DefaultGreetingService.java`:

~~~java
package dev.example.greetings;

import org.apache.commons.lang3.StringUtils;

final class DefaultGreetingService implements GreetingService {

    @Override
    public GreetingMessage greet(String name) {
        if (StringUtils.isBlank(name)) {
            throw new IllegalArgumentException(
                    "name must not be blank"
            );
        }

        String normalized = StringUtils.normalizeSpace(name);
        return new GreetingMessage("Xin chào, " + normalized + "!");
    }
}
~~~

Lớp này **không có `public` modifier**, do đó consumer ở package khác không thể import/khởi tạo nó bằng Java source bình thường. Nó ở cùng package với factory nên `GreetingServices` có thể gọi constructor mặc định package-private.

`StringUtils.isBlank` xử lý null/blank; `normalizeSpace` chuẩn hóa ví dụ khoảng trắng ASCII trong lab. Với `"  Lan    Anh  "`, giá trị normalize thành `"Lan Anh"`. Nền tảng API công khai vẫn không cần biết thư viện xử lý whitespace nào.

### 7.1. Có nên dùng internal package khác?

Có thể đặt implementation vào `dev.example.greetings.internal`, nhưng nếu class package-private thì factory ở package `dev.example.greetings` không thể trực tiếp tạo đối tượng từ package khác. Khi thiết kế package boundary, phải cân nhắc access modifiers/module boundaries/DI mechanisms. Trong lab, implementation được giữ package-private **ngay trong API package** để thể hiện kỹ thuật không lộ class; không phải hướng dẫn bắt buộc đặt tất cả implementation vào API package cho mọi library lớn.

### 7.2. Chỉ internal dependency nghĩa là binary vẫn cần nó lúc chạy

Bytecode của DefaultGreetingService gọi `StringUtils`. Nếu JAR library được chuyển đi mà không kèm Commons Lang runtime dependency (hoặc application không resolve đúng Maven metadata), sẽ gặp `NoClassDefFoundError: org/apache/commons/lang3/StringUtils` khi gọi `greet`. Đây là lý do Gradle `implementation` cần xuất hiện ở published runtime metadata.

## 8. Kiểm thử thư viện từ public API

File `library/src/test/java/dev/example/greetings/GreetingServicesTest.java`:

~~~java
package dev.example.greetings;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServicesTest {

    @Test
    void normalizesExtraSpaces() {
        GreetingMessage message = GreetingServices.standard()
                .greet("  Lan    Anh  ");

        assertEquals("Xin chào, Lan Anh!", message.text());
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> GreetingServices.standard().greet("   ")
        );
    }

    @Test
    void rejectsNullName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> GreetingServices.standard().greet(null)
        );
    }
}
~~~

**Ba JUnit Jupiter test cases** được kỳ vọng PASS. Tests chỉ gọi `GreetingServices`/`GreetingService` public contract, không instantiate implementation class trực tiếp. Điều này làm test tương đồng cách consumer dùng thư viện.

### 8.1. Chạy unit tests producer

Linux/macOS:

~~~bash
./gradlew :library:clean :library:test --console=plain
./gradlew :library:javadoc :library:jar --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat :library:clean :library:test --console=plain
.\gradlew.bat :library:javadoc :library:jar --console=plain
~~~

Test XML report theo Java plugin:

~~~text
library/build/test-results/test/TEST-dev.example.greetings.GreetingServicesTest.xml
library/build/reports/tests/test/index.html
~~~

Bản build có thể in `BUILD SUCCESSFUL` nhưng CI nên kiểm tra số tests thực thi, failures/errors/skips, không chỉ exit code. Một `Test` task có thể không discover tests nếu source set/engine classpath sai; đặc biệt kiểm tra custom Test tasks khi nâng Gradle major.

### 8.2. Test behavior vs test implementation detail

Một test chỉ verify `new DefaultGreetingService()` qua package access không chứng minh factory luôn trả service tương thích. Dùng public entrypoint giảm sự ràng buộc với implementation. Có thể bổ sung:
- Unicode/diacritics như `"Đặng"` không bị mất dấu.
- Control whitespace và multi-word input.
- Null/blank failure behavior.
- Thread-safety nếu implementation có state.
- Contract tests ở module consumer (bài có).

## 9. Module consumer: dùng published Maven coordinates

Không khai báo `implementation(project(":library"))` ở consumer. File `consumer/build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    application
}

repositories {
    maven {
        url = uri(
            rootProject.layout.projectDirectory
                .dir("build/local-staging-repository").asFile
        )
    }
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

dependencies {
    implementation("dev.example:greeting-library:1.0.0")

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set("dev.example.consumer.Main")
}
~~~

Tại đây, consumer biết **tọa độ Maven và repository**, không biết producer project path `:library`. Chính điều này biến lab thành một bước **publish-consume smoke test** thực sự.

### 9.1. consumer/src/main/java/dev/example/consumer/Main.java

~~~java
package dev.example.consumer;

import dev.example.greetings.GreetingMessage;
import dev.example.greetings.GreetingServices;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        GreetingMessage result = GreetingServices.standard()
                .greet("  Lan    Anh  ");

        System.out.println(result.text());
    }
}
~~~

Kết quả Java Main in ra chính xác:

~~~text
Xin chào, Lan Anh!
~~~

Gradle có thể thêm task headers/timing; chỉ dòng trên là stdout từ Java program.

### 9.2. consumer/src/test/java/dev/example/consumer/ConsumerSmokeTest.java

~~~java
package dev.example.consumer;

import dev.example.greetings.GreetingServices;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ConsumerSmokeTest {

    @Test
    void consumesPublishedPublicApi() {
        assertEquals(
                "Xin chào, Gradle!",
                GreetingServices.standard().greet("Gradle").text()
        );
    }
}
~~~

**Một JUnit consumer test** chứng minh published dependency có public Java types và runtime implementation hoạt động. Tổng lab có **3 tests producer + 1 test consumer**, không tính các Javadoc/publishing tasks.

## 10. Chạy theo thứ tự chuẩn: producer trước, consumer sau

### 10.1. Bước 1 — build và test thư viện

Linux/macOS:

~~~bash
./gradlew --version
./gradlew projects --console=plain
./gradlew :library:clean :library:check --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects --console=plain
.\gradlew.bat :library:clean :library:check --console=plain
~~~

Kiểm tra `projects` có `:library` và `:consumer`, `:library:test` có ba tests pass. Dùng Gradle Wrapper tin cậy và JDK 17 tương thích.

### 10.2. Bước 2 — publish thử vào filesystem Maven repository

Linux/macOS:

~~~bash
./gradlew \
  :library:publishMavenJavaPublicationToLocalStagingRepository \
  --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat :library:publishMavenJavaPublicationToLocalStagingRepository --console=plain
~~~

Task name được tạo từ **publication name `mavenJava`** và **repository name `localStaging`**. Nếu thay tên trong build script, task name tương ứng cũng đổi. Có thể kiểm tra bằng:

~~~bash
./gradlew :library:tasks --all --console=plain
~~~

**Không chạy consumer trước khi có artifact**: consumer sử dụng external Maven dependency và không có implicit task dependency tới producer `publish`.

### 10.3. Bước 3 — chạy consumer qua artifact đã publish

Linux/macOS:

~~~bash
./gradlew :consumer:run --console=plain
./gradlew :consumer:test --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat :consumer:run --console=plain
.\gradlew.bat :consumer:test --console=plain
~~~

**Stdout của consumer Java Main:**

~~~text
Xin chào, Lan Anh!
~~~

`:consumer:test` có một JUnit test expected pass. Khi chạy hai commands ở lần đầu, Gradle có thể tải JUnit/Commons Lang từ Maven Central hoặc mirror; điều này bình thường.

### 10.4. Vì sao chạy trong hai invocations?

Gradle resolution của `:consumer` cần repository files đã tồn tại. Nếu yêu cầu `:library:publish... :consumer:run` trong **một command line** hoặc chạy hai tasks song song, không nên dựa vào Gradle tự tạo dependency edge từ external Maven coordinates sang producer task. Hai invocations sequential dễ hiểu và mô phỏng cách downstream consumer thật hoạt động.

## 11. Kết quả publish: những tệp cần nhìn thấy

Theo tọa độ `dev.example:greeting-library:1.0.0`, Maven repository layout:

~~~text
build/local-staging-repository/
└── dev/example/greeting-library/1.0.0/
    ├── greeting-library-1.0.0.jar
    ├── greeting-library-1.0.0.pom
    ├── greeting-library-1.0.0.module
    ├── greeting-library-1.0.0-sources.jar
    └── greeting-library-1.0.0-javadoc.jar
~~~

Gradle có thể tạo thêm checksum files/metadata ngoài danh sách tối thiểu. `.module` là **Gradle Module Metadata**, `.pom` là Maven POM. Chúng không thay nhau hoàn toàn.

### 11.1. File POM cung cấp gì?

- `groupId`, `artifactId`, `version`.
- Name/description được định nghĩa qua `pom { }`.
- Dependency `commons-lang3` được publish với **runtime** scope từ `implementation`.
- POM không nhất thiết thể hiện đầy đủ mọi Gradle rich version constraint/capability/variant.
- `testImplementation` JUnit không bị xuất bản như dependency runtime của thư viện.

### 11.2. Gradle Module Metadata cung cấp gì?

Gradle `.module` metadata có thể biểu diễn:
- Java `apiElements` vs `runtimeElements`.
- Artifact attributes và compatibility (Java ecosystem usage, Java target).
- Sources/Javadoc variants.
- Dependency constraints/capabilities/rich metadata mà POM không mô tả đầy đủ.

Khi Gradle consumer truy cập repository có Gradle Module Metadata hợp lệ, nó có thể dùng richer variant-aware resolution. Maven consumers thường dùng POM, vì vậy một library xuất bản cho cả hai hệ sinh thái phải xem **cả POM lẫn `.module`**.

### 11.3. Tại sao xuất bản từ `components["java"]`?

~~~kotlin
create<MavenPublication>("mavenJava") {
    from(components["java"])
}
~~~

là phương thức phù hợp để publish Java software component gồm artifact + dependencies/variants metadata. Nếu chỉ gắn một JAR bằng `artifact(tasks.jar)` mà không publish metadata của component, consumer có thể **không nhận được runtime dependencies** cần thiết. Hãy dùng `from(components["java"])` trừ khi bạn có một lý do rõ ràng để tạo publication đặc biệt.

## 12. Kiểm tra apiElements và runtimeElements trong consumer

Sau khi publish, chạy:

~~~bash
./gradlew :consumer:dependencies \
  --configuration compileClasspath \
  --console=plain

./gradlew :consumer:dependencies \
  --configuration runtimeClasspath \
  --console=plain

./gradlew :consumer:dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  --console=plain
~~~

Trên Windows thay `./gradlew` bằng `.\gradlew.bat`. Mục tiêu:

- `compileClasspath` của consumer có `dev.example:greeting-library:1.0.0` nhưng **không phải trực tiếp kế thừa Commons Lang qua API variant**.
- `runtimeClasspath` có library và `org.apache.commons:commons-lang3:3.17.0` vì implementation needs Lang3.
- `dependencyInsight` cho thấy Commons Lang version và đường resolution của runtime.
- Library test dependencies JUnit không được tự động đưa vào consumer production runtime vì chúng là test-only.

Kết quả report chi tiết có thể thay theo Gradle version; **đừng hard-code toàn bộ Gradle CLI output** làm expected output vì dependency graph symbols/sorting có thể khác.

### 12.1. Một thử nghiệm cố ý fail compile

Trong **bản sao thử nghiệm** của consumer, nếu người dùng chỉ khai báo library GAV mà lại thêm:

~~~java
// Đây là ví dụ SAI có chủ ý, không thêm vào mã Main chạy đúng:
import org.apache.commons.lang3.StringUtils;
~~~

consumer Java compile không nên thấy Commons Lang chỉ vì thư viện dùng nó ở `implementation`. Nếu consumer thật sự cần trực tiếp sử dụng `StringUtils`, phải khai báo **một dependency của chính consumer** hoặc library chủ ý thay đổi public contract. **Không** chuyển library `implementation` thành `api` chỉ để làm xanh đoạn code consumer dùng nhầm internals.

### 12.2. Runtime dependency không phải shaded JAR

`library/build/libs/greeting-library-1.0.0.jar` chứa classes/resources do library tạo, **không nhúng bytecode Commons Lang**. Consumer Gradle runtime classpath chứa cả hai library JAR và Commons Lang JAR dựa trên metadata. Một fat JAR hoặc shading là chiến lược khác, cần task/plugin riêng.

## 13. Java 17 audit tool: kiểm chứng publication độc lập

Để audit artifact đã xuất bản mà không phụ thuộc Gradle implementation details, tạo `tools/PublicationAudit.java`. Chương trình chỉ dùng **JDK 17 standard library**, kiểm tra:

1. Các public API class files tồn tại trong published JAR.
2. Maven POM có dependency `commons-lang3` ở `runtime` scope.
3. Gradle Module Metadata có hai variants `apiElements` và `runtimeElements`.
4. Sources JAR/Javadoc JAR được publish.
5. Nếu thiếu bất kỳ điều kiện nào, ném exception để process exit nonzero.

### 13.1. tools/PublicationAudit.java

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.jar.JarFile;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

public final class PublicationAudit {

    private PublicationAudit() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: PublicationAudit <staging-repository-path>"
            );
        }

        Path folder = Path.of(args[0])
                .resolve("dev/example/greeting-library/1.0.0");

        Path jar = folder.resolve("greeting-library-1.0.0.jar");
        Path pom = folder.resolve("greeting-library-1.0.0.pom");
        Path module = folder.resolve("greeting-library-1.0.0.module");
        Path sources = folder.resolve(
                "greeting-library-1.0.0-sources.jar"
        );
        Path javadoc = folder.resolve(
                "greeting-library-1.0.0-javadoc.jar"
        );

        try (JarFile publishedJar = new JarFile(jar.toFile())) {
            Set<String> publicClasses = Set.of(
                    "dev/example/greetings/GreetingService.class",
                    "dev/example/greetings/GreetingMessage.class",
                    "dev/example/greetings/GreetingServices.class"
            );

            for (String entry : publicClasses) {
                require(
                        publishedJar.getJarEntry(entry) != null,
                        "Missing Java public API class: " + entry
                );
            }
        }
        System.out.println("PUBLIC_API_JAR_OK");

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true
        );
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true
        );
        factory.setExpandEntityReferences(false);
        factory.setXIncludeAware(false);

        NodeList dependencies = factory.newDocumentBuilder()
                .parse(pom.toFile())
                .getElementsByTagName("dependency");

        boolean runtimeLang3 = false;

        for (int index = 0; index < dependencies.getLength(); index++) {
            Element dep = (Element) dependencies.item(index);

            String group = childText(dep, "groupId");
            String artifact = childText(dep, "artifactId");
            String scope = childText(dep, "scope");

            if ("org.apache.commons".equals(group)
                    && "commons-lang3".equals(artifact)
                    && "runtime".equals(scope)) {
                runtimeLang3 = true;
            }
        }

        require(
                runtimeLang3,
                "POM is missing commons-lang3 in runtime scope"
        );
        System.out.println("POM_RUNTIME_SCOPE_OK");

        String metadata = Files.readString(
                module, StandardCharsets.UTF_8
        );

        require(
                metadata.contains("apiElements")
                        && metadata.contains("runtimeElements"),
                "Gradle Module Metadata variants are missing"
        );
        System.out.println("MODULE_METADATA_OK");

        require(
                Files.isRegularFile(sources)
                        && Files.isRegularFile(javadoc),
                "Sources/Javadoc JAR is missing"
        );
        System.out.println("SOURCES_JAVADOC_OK");
    }

    private static String childText(
            Element parent, String tag
    ) {
        NodeList children = parent.getElementsByTagName(tag);
        if (children.getLength() == 0) {
            return "";
        }
        return children.item(0).getTextContent().trim();
    }

    private static void require(
            boolean condition, String message
    ) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
~~~

Các XML parser features hạn chế DOCTYPE/external entity attacks, tránh parse untrusted POM thiếu kiểm soát. Chương trình không cho phép publish hay xóa file; chỉ đọc directory người dùng cung cấp.

### 13.2. Chạy audit Java17 bằng javac/java

Linux/macOS, tại root:

~~~bash
mkdir -p audit-classes
javac -encoding UTF-8 --release 17 \
  -d audit-classes tools/PublicationAudit.java
java -cp audit-classes PublicationAudit \
  build/local-staging-repository
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force audit-classes | Out-Null
javac -encoding UTF-8 --release 17 -d audit-classes tools\PublicationAudit.java
java -cp audit-classes PublicationAudit build\local-staging-repository
~~~

**Stdout chính xác khi tất cả kiểm tra đạt:**

~~~text
PUBLIC_API_JAR_OK
POM_RUNTIME_SCOPE_OK
MODULE_METADATA_OK
SOURCES_JAVADOC_OK
~~~

Điều kiện: published repository tồn tại và Java 17 JDK đã cài. Nếu POM runtime scope sai, không xuất bản `.module` hoặc sources/Javadoc thiếu, chương trình ném `IllegalStateException` hoặc lỗi I/O, **không** in đầy đủ bốn dòng. Đây là kiểm tra tốt để tích hợp vào CI artifact-validation gate.

### 13.3. Những điều audit chưa kiểm tra

Audit không thay:
- JUnit producer/consumer behavior tests.
- Full API binary compatibility/semantic versioning gates.
- Dependency checksum/signature/provenance verification.
- SHA-256 reproducibility giữa hai clean builds.
- Gradle variant attribute schema chi tiết.
- Consumer Maven/Gradle compatibility ở nhiều version/JDK.
- Quality/security audit của code trong published JAR.
- Javadoc HTML content correctness và public API documentation review.

Nó là **một smoke contract test có thật**, dễ mở rộng trong tổ chức.

## 14. Kiểm tra JAR, Javadoc, manifest và ABI bằng công cụ JDK

Sau khi publish:

~~~bash
jar tf library/build/libs/greeting-library-1.0.0.jar
jar tf library/build/libs/greeting-library-1.0.0-sources.jar
jar tf library/build/libs/greeting-library-1.0.0-javadoc.jar
~~~

Lưu ý archive paths ở đây dựa trên `base.archivesName = greeting-library` và `version = 1.0.0`. Trong project khác, tên files phụ thuộc conventions.

Các entry public API mong đợi trong main JAR:

~~~text
dev/example/greetings/GreetingService.class
dev/example/greetings/GreetingMessage.class
dev/example/greetings/GreetingServices.class
~~~

`DefaultGreetingService.class` cũng có thể có trong JAR để runtime thực thi, **nhưng nó không phải kiểu Java public** mà consumer được khuyến khích instantiate. `jar tf` không chứng minh access modifiers; dùng `javap`:

~~~bash
javap -public -classpath \
  library/build/libs/greeting-library-1.0.0.jar \
  dev.example.greetings.GreetingService
~~~

Mục đích: xem public methods/signatures ở binary API. Để kiểm tra class modifiers, có thể dùng `javap -p` với class cụ thể. Output của `javap` có header/format tùy JDK nên không đưa ra transcript giả.

### 14.1. Sources và Javadoc JAR

Sources JAR giúp IDE hiển thị/điều hướng mã nguồn thay vì decompiled bytecode. Javadoc JAR cung cấp tài liệu public API. Chúng không bắt buộc cho Java runtime nhưng là một phần trải nghiệm dùng thư viện chuyên nghiệp.

`withSourcesJar()` và `withJavadocJar()` trong Java component tự đăng ký các variants đi cùng publication, không nên tự tạo JAR trùng classifier nếu đã có.

### 14.2. Manifest có cần Main-Class?

**Không.** Thư viện Java không nhất thiết có entry point `Main-Class`. Library JAR được sử dụng qua dependency/classpath. Consumer Application plugin biết `mainClass = dev.example.consumer.Main` và chạy từ runtime classpath. Đừng cho rằng một thư viện “không chạy bằng `java -jar`” là publish sai.

### 14.3. API/ABI compatibility

Khi nâng từ `1.0.0` lên `1.1.0`, giữ các public signatures cho backward compatibility theo chính sách versioning. Một thay đổi Java `record GreetingMessage(String text)` sang `record GreetingMessage(String value)` sẽ đổi accessor `text()` thành `value()`, phá source compatibility. Thay `GreetingService.greet(String)` return type hoặc xóa `GreetingServices.standard()` có thể phá binary compatibility. Cần API comparison/consumer tests, không chỉ package-level unit tests.

## 15. Phân biệt source-level API và Gradle API variants

Java public API là kiểu/binary method signatures. Gradle `apiElements` là một **variant consumable** chứa library artifact và thông tin dependencies/API usage. Mọi type `public` trong JAR **không tự biến thư viện nó import thành `api` dependency**: bạn phải chủ động khai báo chính xác.

Ví dụ:

- `public GreetingMessage greet(String)`: chỉ JDK + class cùng library. Commons Lang được dùng trong body: `implementation` đúng.
- `public org.vendor.Result greet(...)`: public signature cần Vendor Result: cân nhắc `api` theo Java Library plugin.
- Annotation type trên public ABI có thể cần `api` hoặc `compileOnlyApi` tùy runtime presence contract.
- Annotation processor dependency là build-time tool, thường `annotationProcessor`, không đưa vào `api`.
- Reflection/ServiceLoader runtime dependency không nhất thiết nằm trong compile signature, thường `runtimeOnly`/`implementation`.

**Đừng tự tạo `apiElements`/`runtimeElements` configurations bằng tay** trong một `java-library` build thông thường. Plugin đã định nghĩa variants; thao tác tùy biến nâng cao cần hiểu Gradle variant attributes/capabilities.

## 16. POM và Gradle Module Metadata: hiểu cả hai

| Thông tin | Maven POM | Gradle Module Metadata |
| --- | --- | --- |
| Coordinates | Có | Có |
| Dependency Maven scopes | Có (`compile`/`runtime`/`test`/...) | Có dạng variants/dependencies |
| `apiElements`/`runtimeElements` attributes | Không đầy đủ | Có |
| Rich dependency constraints/capabilities | Hạn chế | Biểu đạt phong phú |
| Sources/Javadoc classifiers | Các artifact cùng coordinates | Variants tương ứng |
| Consumer | Maven và Gradle fallback | Gradle aware metadata |
| Binary verification | Cần checksum/signing ngoài metadata | Cũng cần xác minh artifact bytes |

Gradle khi publish Maven có thể thêm marker trong POM để Gradle consumers biết đến `.module`. **Không xóa Gradle metadata để sửa build** mà chưa hiểu lý do: xóa có thể khiến variant-aware Gradle consumer chỉ còn POM semantics.

### 16.1. Gradle dùng runtime scope cho implementation

`java-library` producer công bố `implementation("org.apache.commons:commons-lang3:3.17.0")` làm runtime requirement. Maven consumer dùng POM cũng sẽ biết runtime dependency. Đây là lợi ích của `from(components["java"])` so với publish JAR thủ công bỏ qua component metadata.

### 16.2. Kiểm tra dependency leakage

Nếu Commons Lang xuất hiện trên consumer `compileClasspath` dù chỉ `implementation`, hãy điều tra:
- Consumer có khai báo Commons Lang trực tiếp không?
- Một dependency khác có `api`/Maven compile scope tới Commons Lang không?
- Consumer bị đổi sang runtime variant hoặc classpath bị IDE sửa thủ công không?
- Repository có metadata từ một bản publish cũ cùng tọa độ không?
- Gradle resolution có substitution/component metadata rules không?

Không kết luận Gradle `implementation` “không hoạt động” trước khi xem toàn dependency graph.

## 17. Kiểm thử consumer thật: vì sao không chỉ dùng project dependency?

Producer test có thể truy cập library classes từ local source output; nhưng **published consumer** sẽ chịu thêm:
- Maven coordinates và repository URL.
- POM vs Gradle metadata.
- Public API class files thật trong JAR.
- Transitive runtime dependencies được khai báo đúng.
- Java target compatibility, missing classes/resources.
- Artifact filename/classifiers và checksum/integrity.

Nếu consumer dùng `implementation(project(":library"))`, Gradle có project dependency metadata ngay trong cùng build và **không kiểm tra được POM/GAV thực tế**. Vì vậy hai chiến lược đều có giá trị:

- **Development multi-project:** dùng project dependencies để IDE/Gradle build liên kết tự nhiên.
- **Publication smoke test:** dùng **binary Maven coordinates qua staging repo** để kiểm tra đúng sản phẩm đã publish.

Trong lab này, `:consumer` là smoke test của **published binary**, nên không dùng project dependency.

### 17.1. Có thể tự động hóa hai giai đoạn trong CI?

Có. Một CI pipeline hợp lý:

~~~text
Stage 1:
  ./gradlew :library:clean :library:check
  ./gradlew :library:publishMavenJavaPublicationToLocalStagingRepository

Stage 2:
  ./gradlew :consumer:clean :consumer:test :consumer:run
  javac --release 17 ... tools/PublicationAudit.java
  java -cp audit-classes PublicationAudit build/local-staging-repository
~~~

Nếu hai stages chạy trên hai ephemeral machines, **phải truyền staging repository artifacts** sang Stage 2 hoặc publish lên một staging registry có quyền phù hợp; local `build/` trên runner A không tự tồn tại ở runner B. Cân nhắc bảo mật artifacts, access scopes và cleanup. Đừng đưa signing/publishing secrets vào job chạy untrusted PR code.

## 18. API documentation và Java 17 design choices

Một public Java library cần có README/API docs giải thích:
- Supported Java versions và module/GAV.
- Public entrypoints và cách khởi tạo.
- Input/output, null/blank policy.
- Thread-safety và exceptions.
- Source/encoding và Unicode behavior.
- Compatibility guarantee và semantic versioning.
- Deprecation/migration policy.
- Supported platforms/JDK/toolchain.
- Known limitations.

### 18.1. Tại sao dùng record?

`GreetingMessage` record giúp tạo value object bất biến, nhưng record components là API ổn định cần cân nhắc versioning. Nếu thư viện phải hỗ trợ Java 8/11, Java 17 record không phù hợp; phải dùng class/value type khác và đặt toolchain/release tương ứng. Bài cố ý chọn Java 17, không tuyên bố tương thích Java 8.

### 18.2. Tại sao dùng factory trả interface?

`GreetingServices.standard()` trả `GreetingService` cho phép đổi implementation class mà không thay consumer source. Nó cũng giúp dependency injection/extension khi mở rộng tương lai. Tuy nhiên các public static factory methods vẫn là public API: đổi method name hoặc return semantics có thể gây breaking change.

### 18.3. Nguyên tắc tránh accidental API surface

- Public types phải có lý do sử dụng từ consumer.
- Chỉ dùng `public` khi thật sự là một phần contract.
- Không đưa Gradle/Commons Lang/JUnit classes vào API domain model nếu không cần.
- Không publish source/generated internals như một API được hỗ trợ.
- Chỉ công khai exception subclasses khi consumer cần bắt để xử lý.
- Javadoc không được mâu thuẫn runtime implementation.
- Kiểm thử qua public entrypoint, không ràng buộc quá sâu với implementation.

## 19. Đặt phiên bản và phát hành thử an toàn

Trong lab:
- `groupId = dev.example`
- `artifactId = greeting-library`
- `version = 1.0.0`
- `repository = build/local-staging-repository`

Đây là **tọa độ demo**, không phải một artifact đã tồn tại trên Maven Central. Nếu dùng version `1.0.0` rồi sửa binary và publish lại cùng GAV lên shared remote repo, consumers có thể gặp stale caches và integrity conflicts. Với release thật, ưu tiên **immutable versions** và staging/version promotion có kiểm soát.

### 19.1. Maven Local vs private staging vs production

| Đích publish | Phạm vi | Dùng khi nào? |
| --- | --- | --- |
| Project-local file Maven repo | Trong build lab, không credentials | Học và contract test |
| `publishToMavenLocal` | User Maven local repository | Debug local có chủ đích; tránh làm bẩn environment |
| Private staging registry | Team/CI, credentialed | Review candidate và consumer integration |
| Production Maven registry/Central | Public/internal release | Chỉ trusted release automation và chữ ký/policies |

`publish` có thể chạy nhiều publications/repositories; để demo chỉ chạy task rõ tên `publishMavenJavaPublicationToLocalStagingRepository`. Không gọi `publish` rồi vô tình upload đến các remote repositories đã cấu hình ở dự án thật.

### 19.2. Credentials và secrets

Khi thêm remote repository, không commit username/password/token vào source. Dùng Gradle credentials API/properties/environment hoặc CI secret store theo policy. Ví dụ **mảnh minh họa không chạy độc lập**:

~~~kotlin
// Một remote Maven repository đã được admin cấu hình:
credentials {
    username = providers.gradleProperty("repoUser").orNull
    password = providers.gradleProperty("repoPassword").orNull
}
~~~

Không bao giờ copy secret thật vào README hoặc debug logs. Nếu source là PR chưa tin cậy, không chạy Gradle publish task với production token; Gradle build scripts/plugins có khả năng thực thi arbitrary code.

## 20. Java API surface: kiểm tra code và binary

Cần phân biệt:
- `public`: public methods/classes trong source.
- `package-private`: không có public modifier, chỉ truy cập trong cùng package ở Java language level.
- `protected`: có thể là phần inheritance API.
- `private`: implementation detail.
- Java Module System `exports` nếu có `module-info.java`: thêm một tầng public package exposure.
- Published Gradle dependency variants: classpath/dependency metadata, không trực tiếp quyết định Java modifiers.

Một class có thể nằm trong JAR nhưng không phải stable API. Không có Java module descriptor trong lab; nếu project thực sự dùng JPMS, thiết kế `module-info.java`/exports/requires cùng với API dependencies. Đừng thêm module-info chỉ để mọi internal package tự ẩn khi chưa có JPMS migration plan.

### 20.1. Tính tương thích khi đổi method return type

Nếu consumer compile với:

~~~java
GreetingMessage value = GreetingServices.standard().greet("Lan");
~~~

và một release mới đổi `greet` thành trả trực tiếp `String`, consumer source/binary contract bị đổi. Không chỉ nâng patch version rồi giả định không ảnh hưởng. Với API evolution, có thể thêm method mới/deprecate method cũ và giữ binary signatures trong thời gian cam kết.

### 20.2. Nullability và checked exceptions

JDK Java17 không có nullability annotations chuẩn dùng ở mọi ecosystem. Lab ghi contract trong Javadoc và dùng IllegalArgumentException. Nếu library chọn annotation library trên public types/methods, hãy xem liệu annotation artifact có cần `compileOnlyApi`/`api` theo consumer compilation và runtime retention policy. Không tùy tiện đưa một annotation processor vào published API runtime.

## 21. Troubleshooting khi publish thử

| Hiện tượng | Khả năng | Cách chẩn đoán |
| --- | --- | --- |
| `Task ... not found` | Publication/repo name sai | `:library:tasks --all` |
| `MavenPublication` unresolved | Thiếu plugin/import `maven-publish` | Kiểm tra library script |
| `components["java"]` not found | Thiếu `java-library`/Java component | Áp Java library plugin trước |
| `:library:publish` pass nhưng consumer 404 | Publish sai repo/coordinates/path | Kiểm tra file Maven path và consumer repo |
| Consumer fail `Could not find dev.example...` | Chưa publish, wrong URL hoặc stale metadata | Publish trước, so tọa độ |
| Consumer JAR import đỏ nhưng CLI pass | IDE chưa reimport Gradle model | Gradle sync/refresh |
| Consumer compile thấy Commons Lang ngoài dự kiến | Consumer direct/transitive API dependency khác | `compileClasspath` + `dependencyInsight` |
| Consumer runtime `NoClassDefFoundError: StringUtils` | POM/module runtime deps thiếu/sai | Audit POM runtime scope, Gradle metadata |
| `GreetingServices` không xuất hiện trong JAR | Source set/package/path sai | `jar tf`, compile task |
| Javadoc task fail | Java doclint, invalid links, wrong JDK | Đọc task diagnostics, sửa docs |
| Sources/Javadoc JAR vắng | Chưa bật `withSourcesJar`/`withJavadocJar` | Kiểm tra Java component variants |
| Audit POM scope fail | Publish artifact trần hoặc `compileOnly` sai | `from(components["java"])`, implementation |
| `.module` vắng | Metadata disabled hoặc publication không chuẩn | Kiểm tra Gradle publish config |
| JUnit tests không chạy | Engine/runtime/`useJUnitPlatform` sai | XML test count, dependency reports |
| JUnit Jupiter khác version | BOM/version constraints conflict | `dependencyInsight` testRuntimeClasspath |
| Java bytecode incompatible | Consumer JDK thấp hơn target 17 | Chọn supported Java target/toolchain |
| `java -jar greeting-library...` fail | Library không có Main-Class và runtime classpath | Đây không phải runnable executable JAR |
| GAV trùng release cũ trong remote | Immutable version conflict/cache | Bump version, không overwrite |
| 401 Unauthorized / 403 Forbidden | Token/quyền publish repo sai | Credentials trong secret store, permissions |
| TLS/PKIX khi tải dependency | Proxy/certificates/repository trust | Sửa CA/mirror, không tắt verification |
| Source published thiếu file | Incorrect source set/JAR classifier | `jar tf` sources JAR |
| Hash artifact khác build trước | JDK/toolchain/archive bytes thay đổi | So compiler, entries, timestamps, manifests |

### 21.1. Lệnh điều tra nhanh

~~~bash
./gradlew :library:tasks --all --console=plain
./gradlew :library:outgoingVariants --console=plain
./gradlew :library:dependencies --configuration runtimeClasspath --console=plain
./gradlew :consumer:dependencies --configuration compileClasspath --console=plain
./gradlew :consumer:dependencies --configuration runtimeClasspath --console=plain
./gradlew :consumer:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath --console=plain
./gradlew :library:publishMavenJavaPublicationToLocalStagingRepository --info --console=plain
~~~

`outgoingVariants` là report về các outgoing variants mà Gradle sẽ expose; tên/cấu trúc output có thể khác version. Dùng `--info` để chẩn đoán nhưng tránh chia sẻ logs có private credentials/URLs.

## 22. Maven Central và remote publishing: không nhầm với thử nghiệm

Mục tiêu bài là **publish thử cục bộ**. Để release ra Maven Central thật, ngoài `maven-publish` còn phải có quyền namespace/registry, metadata POM hợp lệ, license/SCM/developer metadata theo rules hiện hành, cryptographic signing/provenance, staged validation và publish authority. Các yêu cầu có thể đổi theo Sonatype/Central Portal và tổ chức, nên không tuyên bố một lệnh `./gradlew publish` sẽ tự làm xong release.

**Không gán một license name giả cho source chưa có license.** POM của demo cố ý chỉ có name/description. Khi chọn license cho sản phẩm thật, phải đối chiếu quyền sở hữu mã và chính sách pháp lý trước khi đưa license metadata hoặc phát hành công khai.

### 22.1. Gradle Module Metadata và Maven consumers

Nếu consumer dùng Maven (không biết `.module`) và Gradle consumer (có richer metadata), kiểm thử cả hai để tránh chỉ tối ưu một bên. Java Library plugin mapping `api` vào Maven compile scope, `implementation` vào Maven runtime scope, nhưng Gradle variants/capabilities có thể phong phú hơn POM. Đừng giả định Maven `optional` hay `provided` tương đương đơn giản với mọi Gradle configuration.

## 23. CI quality gates cho thư viện

Một workflow publish candidate có thể đặt các gates:

~~~text
Untrusted pull request:
    Checkout -> Wrapper/JDK validation
      -> compileJava -> unit tests -> Javadoc
      -> publish to isolated scratch filesystem (no secrets)
      -> consumer smoke tests -> PublicationAudit
      -> report only; NEVER production publish

Trusted protected release:
    Source/commit approval
      -> dependency locks/verification
      -> unit + consumer tests
      -> API/ABI compatibility review
      -> artifact/Javadoc/sources/POM/metadata audit
      -> signing/SBOM/provenance
      -> staged remote publication
      -> release promotion
~~~

- Không cấp production publish token cho PR từ fork.
- Không dùng cached untrusted artifact để ký release.
- Dùng Gradle Wrapper pin version/JDK toolchain, dependency verification khi phù hợp.
- Giữ test XML và audit stdout làm CI artifacts.
- Tránh tự chấp nhận checksum changes.
- Không overwrite version đã phát hành; dùng release coordinates/version mới sau review.

### 23.1. Khi chạy trên ephemeral CI runner

Repository file path `build/local-staging-repository` chỉ tồn tại trong workspace của job. Nếu publish job và consume job ở hai VMs khác, upload repository directory như **trusted ephemeral artifact** hoặc publish vào staging registry, sau đó fetch ở job sau. Đừng nghĩ hai jobs chia sẻ filesystem nếu CI không cấu hình.

### 23.2. Tự động hóa thứ tự tasks

Có thể tạo một verification aggregate task riêng sau khi project workflow ổn định, nhưng nếu consumer phụ thuộc external published artifact, phải mô hình hóa **publisher task dependency** hoặc sử dụng tách phases. Không tạo cyclic Gradle task dependency hoặc phụ thuộc vào “thứ tự CLI” giữa hai tasks trong một invocation để che thiếu artifact.

## 24. Reproducibility, checksums và dependency trust

Lưu ý:
- `group:name:version` là tọa độ logical, không phải cryptographic proof.
- File Maven repo có thể bị sửa nếu actor có write permission; production registry nên có immutable release policy.
- Gradle dependency verification metadata có thể kiểm tra SHA/signatures của external artifacts khi được cấu hình.
- Dependency locking pin resolved versions, nhưng không thay artifact integrity verification.
- Publication JAR SHA có thể thay do timestamps/order/toolchain/compiler/build-info, không đồng nghĩa API changed.
- Khi yêu cầu byte-identical, dùng reproducible archive settings, cố định inputs/environment, rồi so SHA-256 với hai clean builds.

### 24.1. Xem hash trên Linux/macOS

~~~bash
sha256sum \
  build/local-staging-repository/dev/example/greeting-library/1.0.0/greeting-library-1.0.0.jar
~~~

Trên macOS có thể dùng `shasum -a 256`. PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 build\local-staging-repository\dev\example\greeting-library\1.0.0\greeting-library-1.0.0.jar
~~~

Đừng bịa một SHA “expected” trong README; giá trị thực phụ thuộc bytes đã build. Chỉ dùng hash so sánh khi môi trường/inputs được kiểm soát.

### 24.2. API compatibility không đồng nghĩa binary reproducibility

Hai JAR có hash khác nhưng public `GreetingService` binary signature giống và contract tests pass có thể tương đương theo mức behavioral/API. Ngược lại, cùng tên JAR nhưng POM thiếu runtime Commons Lang có thể làm downstream fail. **Phải kiểm tra cả artifact bytes khi cần và metadata/behavior**.

## 25. Bài tập mở rộng có đáp án định hướng

**Bài 1 — Thêm API operation mới.** Thêm `GreetingService.greetFormal(String name)` và implement ở DefaultGreetingService. Viết Javadoc, unit + consumer test. Cân nhắc binary compatibility: thêm abstract method vào public interface có thể ảnh hưởng những classes của consumer tự implement interface; đôi khi một default method hoặc interface mới phù hợp hơn.

**Bài 2 — Đổi implementation library.** Thay `StringUtils.normalizeSpace` bằng Java standard library logic rồi loại Commons Lang `implementation`. Chạy publish-consume-audit. Kỳ vọng public API và Java output giữ nguyên, nhưng POM runtime dependency graph thay đổi có chủ đích; audit POM phải được điều chỉnh **sau khi phê duyệt** design change, không bỏ gate âm thầm.

**Bài 3 — Thử sai scope.** Trong sandbox đổi `implementation(commons-lang3)` thành `compileOnly`. Library có thể compile; consumer có thể fail khi runtime. Giải thích Maven POM không còn cung cấp runtime dependency cần thiết.

**Bài 4 — Thử compile classpath leakage.** Trong Consumer thêm import `StringUtils` mà không khai báo Commons Lang trực tiếp. Sau publish, consumer compilation không nên kế thừa internals từ library `apiElements`. Khi muốn sử dụng thật, thêm dependency trực tiếp vào consumer.

**Bài 5 — Thêm API type từ external dependency.** Thiết kế một public method dùng type của thư viện thứ ba. Xác định vì sao `api` hoặc `compileOnlyApi` thích hợp tùy runtime contract. Đọc Gradle Java Library docs trước khi chọn.

**Bài 6 — Kiểm tra javadocJar/sourceJar.** Dùng `jar tf` kiểm tra các file. Thử tắt `withSourcesJar` trong bản sao rồi chạy `PublicationAudit`; expected fail `Sources/Javadoc JAR is missing`.

**Bài 7 — Thử sai GAV.** Trong consumer đổi version thành `1.0.1` khi producer mới publish `1.0.0`. Expected Gradle resolution fail; đây là lỗi “artifact chưa tồn tại”, không phải Java source lỗi.

**Bài 8 — Tạo consumer Maven thật.** Dùng một Maven consumer test project trỏ đến local staging repository và chạy compile/runtime. So xem Maven POM runtime scope vẫn kéo Commons Lang. Không dựa vào Gradle Module Metadata-only features cho Maven consumer.

**Bài 9 — Nâng major Java.** Thử compile library `--release 21` trên sandbox và dùng consumer JDK 17. Expected incompatibility; không coi một bài library Java17 là tương thích Java8/11/21 khi compile target đổi không review.

**Bài 10 — Publishing security.** Thiết kế policy nào cho PR/untrusted release, credentials, checksum, GAV immutability và provenance. Không đưa secrets vào demo staging repository, nên publish chỉ tạo local files.

## 26. Câu hỏi ôn tập

**1.** `java-library` khác `java` ở đâu? — Có API/implementation dependency separation phù hợp Java libraries.

**2.** Tại sao library API không cần chứa Commons Lang types? — Vì public contract được mô hình bằng Java 17 interface/record; Lang3 chỉ dùng implementation.

**3.** `implementation` có biến dependency thành private runtime không publish? — Không. Nó không xuất trên consumer compile classpath nhưng có trong runtime metadata.

**4.** `api` dùng khi nào? — Khi consumer cần external type ở public ABI/contract của library.

**5.** `compileOnlyApi` khác `api`? — Expose compile-time API dependency nhưng không tự cung cấp runtime dependency.

**6.** `testImplementation` JUnit có được publish cho consumer production? — Không, nó phục vụ test source set của producer.

**7.** Vì sao dùng `from(components["java"])`? — Publish Java component có dependencies/variants thay vì JAR trần thiếu metadata.

**8.** `maven-publish` có tự gửi lên Maven Central? — Không, phải cấu hình repository/permissions/metadata/security; lab chỉ dùng file Maven repo.

**9.** Consumer lab dùng project dependency hay published GAV? — Published GAV `dev.example:greeting-library:1.0.0`.

**10.** Vì sao publish phải chạy trước consumer? — Consumer resolution đọc external Maven file repo; Gradle không suy ra producer task tự động.

**11.** Maven POM đặt Commons Lang vào scope nào? — Runtime trong lab, vì producer khai báo `implementation`.

**12.** `.module` file là gì? — Gradle Module Metadata với variants như apiElements/runtimeElements.

**13.** `withSourcesJar` làm gì? — Tạo sources artifact để consumer IDE xem source.

**14.** `withJavadocJar` làm gì? — Tạo Javadoc artifact cho API documentation.

**15.** `java -jar greeting-library-1.0.0.jar` có phải cách đúng chạy thư viện? — Không, thư viện không có Main-Class/executable packaging.

**16.** Vì sao `DefaultGreetingService` package-private? — Giữ implementation class ngoài public API ở Java language level.

**17.** Chương trình Java Main in gì? — `Xin chào, Lan Anh!` và newline.

**18.** Có bao nhiêu JUnit tests? — Producer ba test; consumer một test.

**19.** `PublicationAudit` in gì khi pass? — `PUBLIC_API_JAR_OK`, `POM_RUNTIME_SCOPE_OK`, `MODULE_METADATA_OK`, `SOURCES_JAVADOC_OK` trên bốn dòng.

**20.** Có nên dùng version `1.0.0` lại cho binary khác khi release? — Không nên; tránh stale caches/immutable registry conflicts.

**21.** Dependency locking có thay checksum verification? — Không, nó chủ yếu pin selected versions.

**22.** API source compile pass đã đảm bảo ABI compatible chưa? — Chưa, cần public signatures/consumer compatibility tests.

**23.** Gradle User Home với `~/.m2/repository` có giống nhau? — Không, và lab dùng một project-local staging repo riêng.

**24.** Một CI job trên runner B tự thấy repo local của runner A? — Không, phải chuyển artifacts hoặc dùng shared staging registry.

**25.** Nếu `NoClassDefFoundError` liên quan StringUtils thì kiểm tra gì? — Library runtime dependency metadata, consumer runtimeClasspath và repository artifact.

## 27. Checklist hoàn thành lab

- [ ] Mở đúng root có `settings.gradle.kts` và Gradle Wrapper.
- [ ] JDK/toolchain Java17 được phát hiện, Gradle Daemon JVM tương thích Wrapper.
- [ ] Có hai subprojects `:library` và `:consumer`.
- [ ] Public `GreetingService`, `GreetingMessage`, `GreetingServices` có API/Javadoc rõ ràng.
- [ ] `DefaultGreetingService` package-private; Commons Lang chỉ trong implementation.
- [ ] `java-library` và `maven-publish` được apply ở producer.
- [ ] `withSourcesJar` và `withJavadocJar` được cấu hình.
- [ ] Ba JUnit producer tests pass; một consumer smoke test pass.
- [ ] Maven publication dùng `from(components["java"])` và đúng GAV.
- [ ] Repository thử nằm trong root build directory, không gửi ra public.
- [ ] Task publish local staging chạy thành công trước consumer.
- [ ] Published main JAR, POM, .module, sources JAR, Javadoc JAR tồn tại.
- [ ] Maven POM có Commons Lang runtime dependency.
- [ ] Gradle Module Metadata có apiElements/runtimeElements.
- [ ] Consumer compileClasspath không phụ thuộc implementation Lang3 do library leak.
- [ ] Consumer runtimeClasspath có Commons Lang.
- [ ] Consumer Java stdout chính xác `Xin chào, Lan Anh!`.
- [ ] `PublicationAudit` Java17 compile/run và in đủ bốn dòng PASS.
- [ ] Không có release credentials/secrets trong source hoặc cache thử.
- [ ] Chỉ trusted release automation được publish remote khi có approval.
- [ ] Ghi rõ API/ABI stability/versioning policy trước khi phát hành thật.

## 28. Tài liệu tham khảo chính thức

1. Gradle — Java Library Plugin: https://docs.gradle.org/current/userguide/java_library_plugin.html
2. Gradle — Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
3. Gradle — Publishing Overview: https://docs.gradle.org/current/userguide/publishing_setup.html
4. Gradle — Gradle Module Metadata: https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html
5. Gradle — How to Publish to Maven Local: https://docs.gradle.org/current/userguide/publishing_maven.html#publishing_maven:install
6. Gradle — Source and Javadoc JARs: https://docs.gradle.org/current/userguide/java_plugin.html
7. Gradle — Testing in Java Projects: https://docs.gradle.org/current/userguide/java_testing.html
8. Gradle — Declaring Dependencies: https://docs.gradle.org/current/userguide/declaring_dependencies.html
9. Gradle — Variants and Attributes: https://docs.gradle.org/current/userguide/variant_attributes.html
10. Gradle — Variant-aware Resolution: https://docs.gradle.org/current/userguide/variant_aware_resolution.html
11. Gradle — Toolchains for JVM Projects: https://docs.gradle.org/current/userguide/toolchains.html
12. Gradle — Java Compatibility: https://docs.gradle.org/current/userguide/compatibility.html
13. Gradle — Maven Repositories: https://docs.gradle.org/current/userguide/declaring_repositories.html
14. Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
15. Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
16. Gradle — The Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html
17. Gradle — The Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
18. Gradle — Best Practices for Securing Builds: https://docs.gradle.org/current/userguide/best_practices_security.html
19. Java SE 17 — Records: https://docs.oracle.com/en/java/javase/17/language/records.html
20. Java SE 17 — JAR File Format: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html

**Lưu ý về phiên bản:** Gradle URL `/current/` thể hiện docs hiện tại, trong khi project thật tuân theo **Gradle Wrapper version** và compatibility matrix của nó. JUnit BOM 5.11.4, Commons Lang3 3.17.0 và GAV dev.example:greeting-library:1.0.0 là các lựa chọn **demo được pin**; muốn dùng production phải kiểm tra release/security/organization policies và legal permissions.

**Kết luận:** Thư viện Java được thiết kế và xuất bản đúng không chỉ là một file JAR. Nó có **public API ổn định, implementation dependencies không rò vào consumer compile path, test contract rõ ràng, Java component publication đủ POM/Module Metadata/sources/Javadoc, và một consumer thật chứng minh binary được phát hành sử dụng được**. Xuất bản thử vào repository cục bộ trước giúp phát hiện sai sót mà không gây rủi ro cho release registry.