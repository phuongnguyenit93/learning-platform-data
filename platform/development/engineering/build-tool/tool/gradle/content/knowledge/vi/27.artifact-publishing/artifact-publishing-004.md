# Gradle Module Metadata và thông tin variant khi công bố artifact

## 1. Công bố artifact là công bố cả hợp đồng cho consumer

Khi một thư viện Java được phát hành dưới tọa độ `group:artifact:version`, người sử dụng cần nhiều thông tin hơn tên JAR. Họ cần biết thư viện nào xuất hiện trên **compile classpath**, thư viện nào cần ở **runtime**, JDK baseline được hỗ trợ, có những sources/Javadoc artifacts nào, có feature tùy chọn và những version constraints nào phải được xem xét.

**Gradle Module Metadata (GMM)** là định dạng metadata do Gradle thiết kế để diễn đạt những thông tin đó. File thường có extension `.module`, lưu dưới dạng JSON trong repository cạnh Maven POM và các JAR.

**Maven POM** vẫn là hợp đồng quan trọng cho Maven consumers, nhưng mô hình Maven scopes không thể mô tả đầy đủ Gradle variants, attributes, capabilities và nhiều dạng rich version constraints. Khi publish bằng Gradle hiện đại, nhà phát hành thường giữ **cả POM lẫn GMM**.

```text
Java Library project
    |
    +-- java software component
    |     |
    |     +-- apiElements        usage=java-api
    |     +-- runtimeElements    usage=java-runtime
    |     +-- sourcesElements    documentation=sources (nếu bật)
    |     +-- javadocElements    documentation=javadoc (nếu bật)
    |
    v
maven-publish / MavenPublication
    |
    +-- library-1.0.0.jar
    +-- library-1.0.0.pom
    +-- library-1.0.0.module
    +-- library-1.0.0-sources.jar (nếu bật)
    +-- library-1.0.0-javadoc.jar (nếu bật)
    |
    v
Maven-compatible repository
    |
    +-- Gradle consumer: chọn variant bằng attributes
    +-- Maven consumer: đọc POM và dependency scopes
```

Mục tiêu bài học là hiểu **metadata thực sự được publish**, tại sao API/runtime variants có dependency khác nhau, cách Gradle chọn variant và cách kiểm tra một thư viện sau khi phát hành. Phần thực hành có hai project Java 17, publish vào Maven repository **cách ly trong thư mục build**, rồi để một consumer đọc lại metadata bằng tọa độ Maven. Không cần tài khoản xuất bản công khai.

## 2. Phân biệt component, publication, variant và artifact

| Thuật ngữ | Vai trò | Ví dụ |
| --- | --- | --- |
| Software component | Mô hình phần mềm để công bố, thường được plugin cung cấp | `components["java"]` |
| Variant | Một cách tiêu thụ component, có attributes/dependencies/files riêng | `apiElements`, `runtimeElements` |
| Attributes | Những đặc tính để matching producer và consumer | `org.gradle.usage=java-api` |
| Capability | Định danh tính năng/capability mà một variant cung cấp | Default capability theo module, hoặc capability tùy biến |
| Artifact | File cụ thể được tải về | `variant-lib-1.0.0.jar` |
| Publication | Cấu hình xuất bản component/artifacts/metadata dưới tọa độ | `MavenPublication("mavenJava")` |
| Repository | Kho lưu artifacts và metadata | Maven local, Nexus, Artifactory, file-based Maven repository |
| Consumer configuration | Nơi consumer yêu cầu dependency với những attributes cụ thể | `compileClasspath`, `runtimeClasspath` |

Một file JAR chỉ chứa bytecode/resources; nó **không tự cho Gradle biết dependency nào thuộc API** hoặc JVM baseline của tất cả variants. Component và publication kết nối thông tin trong Gradle model với files cần publish.

### 2.1. `from(components["java"])` khác `artifact(...)`

Trong một Java library có `maven-publish`:

```kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
```

Đây là cách publish **Java component**. Gradle có thể lấy artifacts, dependency variants và metadata từ model được Java plugin cung cấp.

Nếu chỉ attach một file thủ công:

```kotlin
publishing {
    publications {
        create<MavenPublication>("manual") {
            artifact(tasks.named("jar"))
        }
    }
}
```

thì file có thể được publish nhưng **không mặc nhiên có đầy đủ variant/dependency metadata** như publication xuất phát từ `components["java"]`. Mảnh `manual` chỉ minh họa cơ chế, không nên thêm cạnh `mavenJava` trong bài thực hành chính.

### 2.2. Variant không phải một repository hay một phiên bản module khác

Một module `dev.learning:variant-lib:1.0.0` có thể có nhiều variants mà vẫn chung coordinates. Gradle chọn cách tiêu thụ phù hợp với usage/attributes; không cần phát hành mỗi variant dưới một group:artifact:version mới. Một variant có thể trỏ tới cùng JAR nhưng dependencies khác nhau, hoặc trỏ tới artifact khác nếu nhà phát hành thiết kế như vậy.

Tên như `apiElements` chủ yếu hữu ích cho debug; **variant matching dùng attributes và capabilities**, không chỉ so tên variant.

## 3. GMM chứa những thông tin gì?

File `.module` do Gradle tạo thường mô tả:

- Module identity `group`, `module`, `version`.
- Version định dạng metadata và thông tin build tool tạo ra.
- Các variants công bố.
- Attributes của từng variant, ví dụ usage/category/JVM version.
- Artifacts/files, tên và checksum/size nếu có.
- Dependencies theo variant và version requirements.
- Dependency constraints, rich versions, capabilities khi được khai báo.
- Documentation/feature variants và các metadata liên quan.

Một **trích lược cấu trúc để đọc hiểu** (không phải nguyên văn file do Gradle sinh và không đầy đủ để tự publish):

```json
{
  "formatVersion": "1.1",
  "component": {
    "group": "dev.learning",
    "module": "variant-lib",
    "version": "1.0.0"
  },
  "variants": [
    {
      "name": "apiElements",
      "attributes": {
        "org.gradle.usage": "java-api",
        "org.gradle.jvm.version": 17
      }
    },
    {
      "name": "runtimeElements",
      "attributes": {
        "org.gradle.usage": "java-runtime",
        "org.gradle.jvm.version": 17
      }
    }
  ]
}
```

File thực tế còn có các trường khác, đặc biệt `files` và `dependencies`; thứ tự trường, hashes và attributes tùy model/plugin/version. **Không tự tạo metadata JSON bằng tay từ ví dụ lược bỏ này**. Hãy dùng task Gradle sinh GMM và đọc output thật.

### 3.1. GMM không phải version catalog

`gradle/libs.versions.toml` giúp một build khai báo **aliases và version requests**. GMM mô tả **module đã được producer publish**.

Consumer có thể khai báo:

```kotlin
dependencies {
    implementation("dev.learning:variant-lib:1.0.0")
}
```

hoặc khai báo cùng tọa độ qua catalog alias. Cả hai vẫn cần resolver tìm metadata trong repository rồi chọn variant phù hợp. Thay alias không làm thay attributes của thư viện đã publish.

### 3.2. GMM không phải dependency locking

`gradle.lockfile` của consumer ghi lại các **module versions đã resolve** ở các configurations bật locking. File `.module` của producer mô tả các variants/requirements, không đóng băng version graph của mọi consumer. Một GMM có thể được nhiều ứng dụng dùng với version constraints và lock states khác nhau.

## 4. So sánh Gradle Module Metadata và Maven POM

| Chủ đề | Gradle `.module` | Maven `.pom` |
| --- | --- | --- |
| Định dạng | JSON theo mô hình Gradle | XML theo Maven |
| Coordinates | Có | Có |
| API/runtime dependency information | Theo từng variant | Theo Maven dependency scopes |
| Variant attributes | **Có** | Không có mô hình tương đương đầy đủ |
| JVM target attribute | Có thể công bố | Không như Gradle attribute |
| Feature variants | Biểu diễn được | Bị giới hạn |
| Rich version constraints/capabilities | Diễn đạt phong phú hơn | Không chuyển trọn vẹn semantics |
| Sources/Javadoc | Có thể là documentation variants | Thường dùng artifact classifiers |
| Gradle consumer | Được ưu tiên khi marker/repository cho phép | Có thể được sử dụng và suy ra variants |
| Maven consumer truyền thống | Không phải định dạng chính | **Định dạng chính** |

**Không nhầm “POM mất thông tin” với “POM không dùng được”**. Với một Java library cơ bản, Maven scopes có thể biểu đạt đủ những dependency thường gặp. Nhưng khi mô hình variants phong phú hơn, GMM mang ý nghĩa quan trọng cho Gradle consumer.

### 4.1. Mapping API/runtime sang Maven scopes

Trong Java Library plugin:

```kotlin
dependencies {
    api("org.apache.commons:commons-lang3:3.14.0")
    implementation("com.google.guava:guava:33.3.0-jre")
}
```

Thông thường:

- `api` được ánh xạ sang Maven **compile scope**.
- `implementation` được ánh xạ sang Maven **runtime scope**.
- Trong GMM, `apiElements` và `runtimeElements` có tập dependencies riêng.

Nếu thư viện publish custom variants hoặc rich constraints, Maven POM có thể không biểu diễn cùng mức chi tiết. Gradle có thể cảnh báo phần không thể chuyển hoàn toàn sang Maven scopes; đừng tắt những cảnh báo đó mà chưa đánh giá consumer Maven.

### 4.2. Metadata marker trong POM

POM của một module publish kèm GMM thường có comment marker chứa:

```text
published-with-gradle-metadata
```

Marker giúp Gradle consumer nhận biết có một metadata file `.module` phù hợp. Repository/proxy có thể gặp vấn đề nếu **chỉ giữ POM/JAR nhưng loại bỏ `.module`** hoặc sửa mất marker.

Với Gradle repository configuration thông thường, nếu POM chỉ đến Gradle metadata, Gradle có thể ưu tiên đọc GMM. Maven consumers vẫn dựa vào Maven POM.

## 5. Java Library có những variants nào?

Với Kotlin DSL, Java Library plugin được áp dụng:

```kotlin
plugins {
    `java-library`
}
```

Đoạn code này dùng dấu backtick từ cú pháp Kotlin DSL ở `java-library` (được biểu diễn bằng inline/code Markdown sau khi khôi phục nội dung). Gradle tạo Java component có outgoing variants cơ bản:

- **`apiElements`:** variant dành cho compile/API usage.
- **`runtimeElements`:** variant dành cho runtime usage.
- **`sourcesElements`:** documentation variant khi `withSourcesJar()` được bật.
- **`javadocElements`:** documentation variant khi `withJavadocJar()` được bật.

Các plugins bổ sung có thể tạo thêm feature variants hoặc những attributes khác.

### 5.1. Compile variant và runtime variant

`apiElements` thường mang usage:

```text
org.gradle.usage = java-api
```

`runtimeElements` thường mang usage:

```text
org.gradle.usage = java-runtime
```

Nếu public API của producer dùng kiểu `Pair` từ commons-lang3, `apiElements` cần diễn đạt dependency commons-lang3 để compiler của consumer nhìn thấy kiểu đó.

Nếu producer dùng Guava chỉ bên trong method implementation, `runtimeElements` cần diễn đạt Guava để ứng dụng chạy đúng; không nhất thiết đưa Guava vào compile classpath của consumer.

### 5.2. Sources và Javadoc là documentation artifacts

Để bật thêm tài liệu của producer:

```kotlin
java {
    withSourcesJar()
    withJavadocJar()
}
```

Sau publish có thể xuất hiện `variant-lib-1.0.0-sources.jar` và `variant-lib-1.0.0-javadoc.jar`. Chúng hữu ích cho IDE/tooling; **không phải runtime JARs để chạy `Main.main`**.

Một module có thể publish sources/Javadoc ở dạng classifier artifacts cho Maven và dạng documentation variants qua GMM, nhưng Maven POM không có cùng cơ chế lựa chọn theo `org.gradle.docstype`.

## 6. Cách Gradle chọn variant phù hợp

Consumer configuration biểu đạt các **attributes yêu cầu**, producer công bố các **variants có attributes**. Gradle áp dụng compatibility/disambiguation rules để tìm variant, sau đó mới chọn artifacts/files tương ứng.

```text
Consumer compileClasspath
  usage = java-api
  category = library
  JVM baseline phù hợp
           |
           v
Producer GMM
  apiElements
  runtimeElements
  sourcesElements
  javadocElements
           |
           v
Variant-aware matching
           |
           v
Chọn artifacts + dependencies của variant
```

Các attributes JVM thông dụng:

| Attribute | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| `org.gradle.usage` | `java-api`, `java-runtime` | Cấp độ compile hay runtime |
| `org.gradle.category` | `library`, `platform`, `documentation` | Loại variant |
| `org.gradle.libraryelements` | `jar`, `classes` | Dạng thư viện |
| `org.gradle.dependency.bundling` | `external`, `embedded` | Dependency ở ngoài hay gói cùng artifact |
| `org.gradle.jvm.version` | `17` | JVM compatibility do producer công bố |
| `org.gradle.docstype` | `sources`, `javadoc` | Kiểu documentation |

Không phải mọi variant đều có mọi attribute. Cần xem attributes **thực tế** thay vì suy đoán cố định cho tất cả Gradle releases.

### 6.1. Java version mismatch

Nếu producer công bố `org.gradle.jvm.version=17` nhưng consumer compile target Java 11, Gradle có thể báo:

```text
No matching variant of ... was found
```

Lỗi thường giải thích producer variants yêu cầu JVM 17 trong khi consumer cần Java 11. Điều này tốt hơn việc tải một JAR bytecode Java 17 rồi chỉ gặp `UnsupportedClassVersionError` lúc chạy.

**Không khắc phục bằng cách đổi metadata thành JVM 11 khi bytecode thật là Java 17**. Phải compile producer với Java baseline phù hợp, kiểm soát third-party dependencies hoặc nâng runtime của consumer.

### 6.2. Nhiều variants không phân biệt rõ

Một lỗi như:

```text
Cannot choose between the following variants ...
```

có thể xảy ra khi producer có nhiều variants cùng tương thích mà không đủ attributes/capabilities để phân biệt, hoặc consumer yêu cầu quá mơ hồ. Hãy kiểm tra attributes của cả hai phía. **Đổi tên `apiElements` thành một tên khác không tự sửa thuật toán matching**.

## 7. Bài thực hành đầy đủ: publish Java 17 library vào Maven repository riêng

Dự án gồm hai project:

- `:variant-lib`: Java library với API dependency commons-lang3, implementation dependency Guava.
- `:consumer`: Java application dùng tọa độ `dev.learning:variant-lib:1.0.0` qua Maven repository ở `build/lab-repo`, **không dùng `project(":variant-lib")`**.

Thử nghiệm này kiểm tra hành vi của **published metadata** như khi một ứng dụng tiêu thụ thư viện bên ngoài.

### 7.1. Cây thư mục

```text
module-metadata-lab/
├── settings.gradle.kts
├── variant-lib/
│   ├── build.gradle.kts
│   └── src/main/java/demo/library/GreetingLibrary.java
├── consumer/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/demo/app/Main.java
│       └── test/java/demo/app/MainTest.java
└── build/
    └── lab-repo/   (Gradle tạo khi publish)
```

Không commit `build/lab-repo` vào Git. Cần Gradle Wrapper phiên bản phù hợp Java 17, JDK 17/toolchain được Gradle nhận diện, Maven Central hoặc dependency cache để tải commons-lang3/Guava/JUnit.

### 7.2. File `settings.gradle.kts`

```kotlin
dependencyResolutionManagement {
    repositories {
        maven {
            url = uri(rootDir.resolve("build/lab-repo"))
        }
        mavenCentral()
    }
}

rootProject.name = "module-metadata-lab"
include("variant-lib", "consumer")
```

Repository đầu tiên là file-based Maven repository trong root build directory. `mavenCentral()` cung cấp dependencies bên ngoài. Lúc ban đầu `build/lab-repo` chưa có gì; phải publish producer trước khi chạy consumer.

### 7.3. File `variant-lib/build.gradle.kts`

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "dev.learning"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
    withSourcesJar()
    withJavadocJar()
}

dependencies {
    api("org.apache.commons:commons-lang3:3.14.0")
    implementation("com.google.guava:guava:33.3.0-jre")
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])

            pom {
                name.set("Variant Metadata Demo")
                description.set("Java library with API and runtime dependencies")
            }
        }
    }

    repositories {
        maven {
            name = "LocalLab"
            url = rootProject.layout.buildDirectory.dir("lab-repo")
                .get().asFile.toURI()
        }
    }
}
```

Các điểm cần nắm:

- ``java-library`` và ``maven-publish`` là plugin accessors có dấu gạch nối; trong Kotlin DSL dùng **backticks** (không phải dấu nháy đơn).
- `group + project name + version` tạo `dev.learning:variant-lib:1.0.0`.
- `from(components["java"])` dùng **Java software component**, không attach riêng JAR rồi bỏ metadata.
- `withSourcesJar` và `withJavadocJar` thêm documentation artifacts.
- API dependency commons-lang3 sẽ lộ cho consumer compile; Guava là implementation dependency cho runtime.
- `LocalLab` là tên repository để Gradle tạo task publish có tên cụ thể.
- `rootProject.layout.buildDirectory.dir("lab-repo")` đặt output ở root project, không đụng Maven local của người dùng.

Khi đã dùng `from(components["java"])`, không cần thêm `artifact(tasks.jar)` để “chắc có JAR”; làm thế có thể dẫn tới duplicate artifact.

### 7.4. Java source của producer

**`variant-lib/src/main/java/demo/library/GreetingLibrary.java`:**

```java
package demo.library;

import com.google.common.base.CharMatcher;
import org.apache.commons.lang3.tuple.Pair;

public final class GreetingLibrary {
    private GreetingLibrary() {
    }

    public static Pair<String, String> greetingParts(String name) {
        String cleanName = CharMatcher.whitespace().trimFrom(name);
        return Pair.of("Hello", cleanName);
    }
}
```

Public method trả về `Pair<String,String>` từ commons-lang3, nên commons-lang3 là API dependency. Guava `CharMatcher` chỉ được dùng bên trong implementation.

### 7.5. File `consumer/build.gradle.kts`

```kotlin
plugins {
    application
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

dependencies {
    implementation("dev.learning:variant-lib:1.0.0")

    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

application {
    mainClass.set("demo.app.Main")
}

tasks.test {
    useJUnitPlatform()
}
```

Lưu ý consumer khai báo **tọa độ ngoài** `dev.learning:variant-lib:1.0.0`. Không thay bằng `implementation(project(":variant-lib"))`, vì mục tiêu của ví dụ là kiểm tra file GMM/POM **đã publish**.

### 7.6. Java source và JUnit test của consumer

**`consumer/src/main/java/demo/app/Main.java`:**

```java
package demo.app;

import demo.library.GreetingLibrary;
import org.apache.commons.lang3.tuple.Pair;

public final class Main {
    private Main() {
    }

    public static String message(String input) {
        Pair<String, String> parts = GreetingLibrary.greetingParts(input);
        return parts.getLeft() + ", " + parts.getRight() + "!";
    }

    public static void main(String[] args) {
        System.out.println(message("  gradle  "));
    }
}
```

Consumer trực tiếp import `Pair` trong Java source, nhưng không khai báo commons-lang3 một lần nữa ở consumer build script. Đây là cách kiểm tra **API dependency của producer được xuất bản và đưa vào compile classpath consumer**.

**`consumer/src/test/java/demo/app/MainTest.java`:**

```java
package demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class MainTest {
    @Test
    void formatsGreeting() {
        assertEquals("Hello, gradle!", Main.message("  gradle  "));
    }
}
```

### 7.7. Tạo Wrapper nếu cần

Nếu repo đã có `gradlew`, dùng Wrapper. Với thư mục hoàn toàn mới chưa có Wrapper, cần một Gradle distribution đã cài tương thích để chạy một lần:

```bash
gradle wrapper
```

Không cần đăng ký Maven Central account hoặc credentials cho bài này; producer chỉ ghi vào file-based Maven repository bên trong `build/`.

### 7.8. Publish rồi mới consume

Linux/macOS:

```bash
./gradlew :variant-lib:publishMavenJavaPublicationToLocalLabRepository --console=plain
./gradlew :consumer:run --quiet
./gradlew :consumer:test --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat :variant-lib:publishMavenJavaPublicationToLocalLabRepository --console=plain
.\gradlew.bat :consumer:run --quiet
.\gradlew.bat :consumer:test --console=plain
```

**Stdout do `demo.app.Main` in ra:**

```text
Hello, gradle!
```

Task `test` phải chạy JUnit 5 test `formatsGreeting` và không có assertion failures. Toàn bộ Gradle log không nhất thiết chỉ có một dòng, đặc biệt khi phải tải JAR lần đầu.

Nếu chạy `:consumer:run` **trước** publishing, consumer có thể báo không tìm thấy tọa độ `dev.learning:variant-lib:1.0.0`. Đây là hành vi hợp lý vì `implementation("...")` là external dependency, Gradle không tự biết phải chạy task publish của project `:variant-lib`.

### 7.9. Cẩn thận với `clean`

Repository thử nghiệm được lưu ở root `build/lab-repo`. Nếu chạy `./gradlew clean` ở root, directory này có thể bị xóa. Hãy publish lại trước khi chạy consumer.

Một quy trình rõ ràng:

```bash
./gradlew clean
./gradlew :variant-lib:publishMavenJavaPublicationToLocalLabRepository
./gradlew :consumer:test :consumer:run
```

Không nên dùng `publishToMavenLocal` trong lab nếu không muốn ghi vào `~/.m2/repository`. Repository cách ly dưới `build/` giúp xóa và dựng lại mà không ảnh hưởng kho Maven local chung.

## 8. Các file publication được tạo ở đâu?

Task `maven-publish` tạo metadata trung gian, thường ở:

```text
variant-lib/build/publications/mavenJava/
├── module.json
└── pom-default.xml
```

Sau publish, repository cục bộ có đường dẫn tương đương:

```text
build/lab-repo/dev/learning/variant-lib/1.0.0/
├── variant-lib-1.0.0.jar
├── variant-lib-1.0.0.pom
├── variant-lib-1.0.0.module
├── variant-lib-1.0.0-sources.jar
└── variant-lib-1.0.0-javadoc.jar
```

Đây là danh sách **những artifact chính** của lab. Repository còn có thể chứa checksums, metadata files hoặc sidecars khác tùy Gradle/registry.

### 8.1. Sinh metadata riêng trước khi publish

```bash
./gradlew :variant-lib:generateMetadataFileForMavenJavaPublication
./gradlew :variant-lib:generatePomFileForMavenJavaPublication
```

Lệnh này giúp kiểm tra JSON/POM đầu ra trước khi upload lên remote repository. Nó **không tự publish** producer lên Maven Central hoặc một kho từ xa.

### 8.2. Đọc JSON và POM thật

Linux/macOS:

```bash
cat variant-lib/build/publications/mavenJava/module.json
cat variant-lib/build/publications/mavenJava/pom-default.xml
```

Windows PowerShell:

```powershell
Get-Content variant-lib\build\publications\mavenJava\module.json
Get-Content variant-lib\build\publications\mavenJava\pom-default.xml
```

Trong JSON tìm:

1. Coordinates `dev.learning:variant-lib:1.0.0`.
2. `apiElements` với usage `java-api`.
3. `runtimeElements` với usage `java-runtime`.
4. Attributes JVM version tương thích Java 17.
5. Commons-lang3 thuộc API dependencies.
6. Guava thuộc runtime dependencies.
7. Sources/Javadoc variants nếu đã bật.
8. Artifact `files`, names và metadata mà Gradle thực sinh.

Trong POM, kiểm tra dependency scopes tương ứng.

### 8.3. Trích lược dependencies trong Maven POM

Đoạn XML dưới đây là **mảnh dependency section** có thể tương ứng với lab, không phải một file POM độc lập:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
        <scope>compile</scope>
    </dependency>
    <dependency>
        <groupId>com.google.guava</groupId>
        <artifactId>guava</artifactId>
        <version>33.3.0-jre</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Maven scopes vẫn dùng được cho consumer Maven, nhưng không diễn đạt chính xác toàn bộ Gradle attributes hoặc feature variants.

### 8.4. Không đoán file `.module` bằng cách nhìn POM

POM có thể chứa dependencies compile/runtime nhưng không có `org.gradle.jvm.version`, capabilities hoặc full variant model. Khi cần chắc chắn producer đã công bố Java 17 API/runtime variants, phải đọc **`.module` thật** và thử consumer resolution.

## 9. Lệnh quan sát producer và consumer variants

### 9.1. Outgoing variants của producer

```bash
./gradlew :variant-lib:outgoingVariants --console=plain
```

Lệnh hữu ích để xem outgoing configurations với attributes/artifacts. Nó cho thấy model producer trước khi publish, nhưng không chứng minh repository đã nhận file `.module` chính xác. **Kiểm tra cả producer model lẫn file đã xuất bản.**

### 9.2. Compile/runtime graph của consumer

```bash
./gradlew :consumer:dependencies --configuration compileClasspath
./gradlew :consumer:dependencies --configuration runtimeClasspath
./gradlew :consumer:dependencyInsight --dependency variant-lib --configuration runtimeClasspath
./gradlew :consumer:dependencyInsight --dependency guava --configuration runtimeClasspath
```

Ở consumer tối giản của lab:

- Compile classpath phải có `variant-lib` và commons-lang3 để import `Pair`.
- Runtime classpath cần `variant-lib`, commons-lang3, Guava và những dependencies bắc cầu cần thiết của Guava.
- Nếu Guava xuất hiện trên compile classpath, hãy kiểm tra xem một dependency khác hoặc consumer trực tiếp đã yêu cầu nó; không kết luận GMM sai ngay.

Task Gradle bổ sung:

```bash
./gradlew :consumer:resolvableConfigurations --console=plain
```

có thể giúp quan sát attributes/configurations phía consumer trong các Gradle releases hỗ trợ task này.

### 9.3. `dependencyInsight` không thay `outgoingVariants`

`outgoingVariants` trả lời: **producer có thể cung cấp những variants nào?**

`dependencies`/`dependencyInsight` trả lời: **consumer đã resolve graph/version nào trong configuration cụ thể?**

Muốn chẩn đoán variant mismatch, đọc cả producer offerings và consumer requirements; chỉ nhìn một phía sẽ thiếu bối cảnh.

## 10. Thí nghiệm chỉ dùng Maven POM

Gradle có thể dùng Maven POM để suy ra variants khi không tiêu thụ GMM. Để minh họa, trong **bản sao lab**, thay repository Maven cục bộ ở `settings.gradle.kts` bằng mảnh:

```kotlin
maven {
    url = uri(rootDir.resolve("build/lab-repo"))
    metadataSources {
        mavenPom()
        ignoreGradleMetadataRedirection()
    }
}
```

Đặt mảnh này trong `dependencyResolutionManagement.repositories`, **không** dán một block Maven thứ hai cùng URL để tránh nội dung không rõ. `mavenPom()` cho phép POM làm metadata source; `ignoreGradleMetadataRedirection()` ngăn marker chuyển sang GMM.

Khi chạy consumer với thư viện Java cơ bản, kết quả có thể **rất giống** khi đọc GMM vì Maven POM đã có scopes compile/runtime. Nhưng với feature variants, capabilities, JVM attributes và rich constraints, GMM giữ thêm semantics mà POM không truyền được.

**Không khuyến nghị ép POM-only để bỏ qua lỗi metadata trong production**. Hãy sửa publication/repository chính xác, dùng thí nghiệm chỉ để hiểu khác biệt.

## 11. Feature variants và capabilities

Một library có thể cung cấp chức năng tùy chọn qua **feature variants** hoặc nhiều implementations. Capabilities giúp Gradle nhận biết một loại chức năng có thể do một hoặc nhiều providers cung cấp; trong các tình huống phù hợp, conflict capabilities có thể chặn việc hai providers không tương thích cùng xuất hiện trong graph.

Ví dụ tình huống:

- Library API chuẩn.
- Tùy chọn thêm JDBC support với dependencies khác.
- Một implementation mặc định và một implementation tối ưu được chọn theo attributes/capabilities.
- Module cũ/mới đổi coordinates nhưng chứa cùng classes, cần phát hiện xung đột.

Maven POM không mô tả đầy đủ semantics của capabilities và nhiều feature variants. Một classifier JAR riêng **không tự biến thành Gradle feature variant có attributes đúng**. Nếu chức năng tùy chọn cần chọn theo variant-aware resolution, phải thiết kế outgoing configuration, attributes, capability và mapping cẩn thận.

### 11.1. Không coi tên variant là khóa chọn

Hai variants có tên khác nhưng cùng bộ attributes/capabilities không được phân biệt đủ có thể gây ambiguity. Ngược lại, variant không tên `apiElements` vẫn có thể thỏa consumer `java-api` nếu attributes phù hợp.

Khi debug, tìm **requested attributes** và **producer attributes** trong thông báo lỗi, không chỉ đổi tên `runtimeElements` cho hết trùng.

## 12. Tùy chỉnh variants khi publish

Gradle cung cấp API `AdhocComponentWithVariants` cho việc thêm/chỉnh variants của một component phù hợp.

Ví dụ muốn **không xuất bản sources variant** trong một dự án khác, nhưng vẫn publish Java API/runtime:

```kotlin
import org.gradle.api.component.AdhocComponentWithVariants

plugins {
    `java-library`
    `maven-publish`
}

java {
    withSourcesJar()
    withJavadocJar()
}

val javaComponent = components["java"] as AdhocComponentWithVariants

javaComponent.withVariantsFromConfiguration(
    configurations["sourcesElements"]
) {
    skip()
}
```

Đây là **phương án tùy biến**, không phải một phần cần thêm vào lab mục 7. Nó giả định component Java tồn tại và publication đầy đủ đã được cấu hình. Khi `skip()`, thông tin sources variant bị loại khỏi publication; IDE/consumer cần sources có thể bị ảnh hưởng.

Các API liên quan:

- `addVariantsFromConfiguration(...)`: thêm outgoing variant từ configuration.
- `withVariantsFromConfiguration(...)`: tùy chỉnh variant đã được đưa vào component.
- `mapToMavenScope("compile")`/`mapToMavenScope("runtime")`: ánh xạ dependency semantics sang Maven scopes khi cần.
- `mapToOptional()`: ánh xạ vào Maven optional semantics.
- `skip()`: bỏ variant khỏi publication.

**Không dùng những API trên như một phép chữa lỗi mặc định.** Một mapping sai có thể làm Maven consumers thiếu runtime dependencies hoặc tạo sự khác biệt khó thấy giữa Maven và Gradle.

### 12.1. Thêm file thủ công không tạo đầy đủ metadata

Nếu chỉ thêm:

```kotlin
// Mảnh ví dụ, chỉ có ý nghĩa khi file tài liệu thực sự tồn tại.
artifact(file("docs/manual.pdf"))
```

vào một publication, file có thể được upload nhưng không tự có variant attributes/dependencies như một phần mềm có thể được Gradle chọn theo usage. Với supplemental artifacts dùng classifier thủ công có thể hợp lý; với feature có dependencies riêng, thiết kế software component/variants sẽ phù hợp hơn.

## 13. Java Platform được publish bằng component khác

Java platform là loại component khác Java library. Một project `java-platform` publish constraints để consumer import platform:

```kotlin
plugins {
    `java-platform`
    `maven-publish`
}

group = "dev.learning"
version = "1.0.0"

dependencies {
    constraints {
        api("org.apache.commons:commons-lang3:3.14.0")
    }
}

publishing {
    publications {
        create<MavenPublication>("mavenPlatform") {
            from(components["javaPlatform"])
        }
    }
}
```

Đây là **một project platform riêng**, không dán đồng thời vào `variant-lib` của bài lab. Chú ý component `javaPlatform` thay vì `java`. Platform công bố version constraints, không phải một JAR chứa `GreetingLibrary`.

Khi tiêu thụ Maven BOM hoặc Gradle Java Platform, GMM và POM có thể mô tả constraints trong những mức semantics khác nhau. Đừng coi component `javaPlatform` và `java` là tên viết thay thế cho nhau.

## 14. Rich version constraints và version mapping

Gradle dependency constraints có thể dùng:

- `strictly("...")`: ràng buộc version strict.
- `prefer("...")`: version được ưu tiên.
- `reject("...")`: những version không được chấp nhận.
- Dependency constraints không nhất thiết tự thêm dependency vào graph.
- Những variants có thể biểu đạt dependencies và constraints khác nhau.

GMM có thể giữ nhiều semantics đó hơn Maven POM. Việc chuyển sang POM là **lossy** trong một số trường hợp; cần review warnings và thử consumer Maven nếu sản phẩm hỗ trợ Maven.

### 14.1. Publish declared hay resolved dependency versions?

Maven Publish hỗ trợ version mapping, ví dụ mảnh đặt trong `MavenPublication`:

```kotlin
versionMapping {
    usage("java-api") {
        fromResolutionOf("runtimeClasspath")
    }
    usage("java-runtime") {
        fromResolutionResult()
    }
}
```

Đây là **cấu hình tùy chọn** tùy chiến lược phát hành, không phải thứ phải thêm vào mọi publication. Nó ảnh hưởng cách Gradle chuyển dependency versions vào published metadata/POM trong những trường hợp phù hợp. Nếu dự án có dependency locking và muốn công bố versions đã được kiểm thử, cần hiểu graph resolution/lock state trước khi cấu hình.

Không sửa ngẫu nhiên `.module` hoặc `pom-default.xml` sau khi đã generate để ép version; hãy sửa model build, publish lại dưới một version được kiểm soát và kiểm thử consumer.

## 15. Các publishing tasks quan trọng

Với publication `mavenJava` và repository `LocalLab`:

| Task | Chức năng |
| --- | --- |
| `generateMetadataFileForMavenJavaPublication` | Tạo `module.json` |
| `generatePomFileForMavenJavaPublication` | Tạo `pom-default.xml` |
| `publishMavenJavaPublicationToLocalLabRepository` | Publish vào `build/lab-repo` |
| `publishMavenJavaPublicationToMavenLocal` | Publish vào local Maven repository của user |
| `publishToMavenLocal` | Aggregate publish các publications đến Maven local |
| `publish` | Aggregate publish đến repositories đã cấu hình |
| `jar` | Tạo JAR chính |
| `sourcesJar` | Tạo source artifact |
| `javadocJar` | Tạo Javadoc artifact |
| `outgoingVariants` | Quan sát variants từ producer model |

`publish` **không tự có nghĩa phát hành lên Maven Central**. Nó chỉ dùng những repositories được khai báo trong `publishing.repositories`. Trong bài lab đó là repository file nội bộ; không có upload public.

### 15.1. Publish task không tự là quality gate

`:variant-lib:build` thường gồm build/verification; `publish...` làm công việc xuất bản. Publication task không mặc định bảo đảm toàn bộ unit/integration tests, compatibility checks và security reviews đã đạt.

Trong CI, nên thiết kế:

```text
Producer unit tests + static checks
         |
         v
Generate POM + GMM
         |
         v
Validate coordinates/variants/dependencies
         |
         v
Publish staging repository
         |
         v
Consumer integration test from staging
         |
         v
Promote immutable release
```

Không upload artifact vào production repository khi chưa thử đúng **published artifacts và metadata**.

## 16. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân điển hình | Cách điều tra/sửa |
| --- | --- | --- |
| `Could not find dev.learning:variant-lib:1.0.0` | Chưa publish, URL/tọa độ sai hoặc root build/repo đã bị clean | Publish trước, kiểm tra path Maven repository |
| Có JAR/POM nhưng thiếu `.module` | Publication không xuất từ component, metadata bị bỏ hoặc repo chặn extension | Xem `generateMetadataFile...` và repository |
| POM có marker nhưng Gradle không đọc GMM | Proxy 403/404, file .module bị chặn hoặc config metadataSources | Kiểm tra marker, repo server và metadataSources |
| Gradle chỉ đọc POM dù GMM đúng | Marker mất hoặc đã cấu hình POM-only | Kiểm tra repository metadata configuration |
| `No matching variant` | Consumer và producer có incompatible attributes | Xem usage/category/JVM version của hai phía |
| `Cannot choose between variants` | Ambiguous attributes/capabilities | Xem outgoing variants và consumer requirements |
| Consumer compile thiếu `Pair` | Commons-lang3 bị khai báo `implementation` dù public API cần | Đưa vào `api` và publish version mới |
| Consumer runtime thiếu Guava `CharMatcher` | Guava dependency không có trong runtime graph | Kiểm tra `implementation`, runtimeElements |
| `UnsupportedClassVersionError` | Bytecode/JVM baseline không tương thích | Sửa compiler target hoặc runtime, test thực |
| Sources/Javadoc không có | Chưa bật `withSourcesJar`/`withJavadocJar` hoặc skip variant | Xem publication và artifacts thực |
| Maven consumer khác Gradle consumer | Maven POM ít semantics hơn GMM | Kiểm tra scopes, optional dependencies, feature design |
| `components["java"]` không tồn tại | Chưa áp dụng Java/Java Library plugin | Kiểm tra `plugins` và đúng project |
| `components["javaPlatform"]` không có | Chưa áp dụng `java-platform` | Dùng component đúng loại |
| `publishMavenJavaPublicationToLocalLabRepository` không tồn tại | Publication/repository name hoặc plugin khác | Chạy `tasks --all` của producer |
| POM báo warnings khi publish variants | Semantics không chuyển đầy đủ sang Maven | Review warning, không chỉ suppress |
| Consumer local pass nhưng CI fail | CI chưa publish hoặc repository path khác | Publish → consume theo đúng thứ tự |
| Repository cache giữ version cũ | Publish đè cùng tọa độ, proxy caching | Phát hành version mới, kiểm tra repository |
| Có test Gradle project dependency pass nhưng published consumer fail | Publication khác project outgoing model | Test consumer qua repository |
| Library JAR có dependency sai ở runtime | Artifact/POM/GMM không nhất quán | Kiểm tra .module + POM + runtimeClasspath |
| `clean` làm mất repo thử nghiệm | Repo nằm dưới root `build/` | Publish lại trước consumer |

### 16.1. Các lệnh chẩn đoán theo đúng thứ tự

```bash
./gradlew :variant-lib:tasks --all
./gradlew :variant-lib:outgoingVariants
./gradlew :variant-lib:generateMetadataFileForMavenJavaPublication
./gradlew :variant-lib:generatePomFileForMavenJavaPublication
./gradlew :variant-lib:publishMavenJavaPublicationToLocalLabRepository
./gradlew :consumer:dependencies --configuration compileClasspath
./gradlew :consumer:dependencies --configuration runtimeClasspath
./gradlew :consumer:dependencyInsight --dependency guava --configuration runtimeClasspath
./gradlew :consumer:test :consumer:run --console=plain
```

Kiểm tra **metadata ở repository đã publish**, không chỉ task `outgoingVariants`. Nếu producer đã tạo đúng JSON nhưng remote repository thiếu file, vấn đề nằm ở quá trình publish/proxy chứ không phải bản thân Java source.

## 17. Đảm bảo tính tin cậy và bất biến của publication

Một release đáng tin cần thêm:

1. **Coordinates rõ ràng:** group/module/version tuân thủ naming và không đè release cũ.
2. **Artifact integrity:** checksum, signature/verification theo chính sách.
3. **Metadata đúng:** POM và GMM phản ánh dependencies, variants, compatibility thực.
4. **Source/Javadoc:** artifacts có nội dung phù hợp nếu hứa cung cấp.
5. **Dependency versions:** được kiểm thử và có policy về dynamic/rich versions.
6. **JVM compatibility:** metadata target đúng với bytecode, APIs và runtime dependencies.
7. **Producer tests:** compile/test/static checks trên toolchain hỗ trợ.
8. **Consumer tests:** compile/run bằng artifact **đã publish**.
9. **Repository policy:** quyền publish hạn chế, tránh ghi đè versions và token trong logs.
10. **Release immutability:** không phát hành bytes khác dưới cùng release coordinates.

GMM có checksum/file metadata không tự thay thế dependency verification hoặc chữ ký đã được xác thực. POM đúng XML không chứng minh Java API tương thích. Tính tin cậy cần kết hợp model metadata, artifact bytes, repository và consumer tests.

### 17.1. Không sửa release cũ tại chỗ

Nếu publish `1.0.0` rồi mới phát hiện `api`/`implementation` sai, việc chỉnh JSON/POM/JAR và upload đè cùng tọa độ có thể khiến caches và consumers giữ các phiên bản metadata khác nhau. Trong production, thông thường cần xuất bản **version mới** sau khi sửa và kiểm thử, theo chính sách release.

Bài lab dùng một repository tạm dưới `build/` để học. Không bê nguyên thói quen ghi đè trong lab sang Maven Central hoặc kho artifact dùng chung.

### 17.2. Bảo mật credentials và metadata

Không để passwords/tokens vào POM `description`, generated resources hay Gradle metadata. Repository credentials phục vụ publish phải được cung cấp qua cơ chế secret management/credentials phù hợp, với quyền tối thiểu. Không in `System.getenv()` hay `gradle.properties` chứa credential thật vào báo cáo debug.

## 18. Checklist review Pull Request thay đổi publishing

Trước khi merge thay đổi liên quan `maven-publish`, nên trả lời:

1. Software component nào đang được publish: `java`, `javaPlatform` hay component custom?
2. Publication name và repository name đã phù hợp chưa?
3. `groupId`/`artifactId`/`version` có đổi ngoài ý muốn không?
4. API dependency có bị chuyển nhầm sang `implementation` không?
5. Runtime dependencies có được publish đủ không?
6. File `.module` có còn đúng variants/attributes không?
7. Maven POM có còn đúng scopes và marker không?
8. Java baseline trong metadata có phản ánh bytecode thực không?
9. Documentation variants có được publish đúng như cam kết không?
10. Có extra artifacts được attach “out of context” mà consumer không chọn được không?
11. Nếu có feature variants, capabilities/matching rules đã được kiểm tra chưa?
12. Có warnings do Maven mapping làm mất semantics không?
13. Một consumer Gradle từ repository đã publish có compile/run/test thành công không?
14. Nếu hỗ trợ Maven consumer, có thử hành vi Maven POM không?
15. Đã review repository permissions, provenance và version immutability chưa?

**Một bản publish đạt QA phải được đánh giá bằng mắt nhìn của consumer**, không chỉ bằng exit code của task `publish`.

## 19. Bài tập thực hành

**Bài tập A — định vị metadata.** Tạo lab mục 7 và publish producer. Tìm `variant-lib-1.0.0.pom`, `variant-lib-1.0.0.module` và JARs. Giải thích vì sao chỉ có JAR chưa thể truyền variant contract.

**Bài tập B — đọc outgoing variants.** Chạy `:variant-lib:outgoingVariants`. Ghi lại `apiElements`, `runtimeElements`, `sourcesElements` và `javadocElements`. Attributes nào thể hiện usage, category và JVM baseline?

**Bài tập C — consumer qua Maven repository.** Chạy `:consumer:run` sau publish, xác nhận stdout `Hello, gradle!`. Vì sao việc dùng `implementation("dev.learning:variant-lib:1.0.0")` khác test qua `project(":variant-lib")`?

**Bài tập D — API và implementation.** Xem compileClasspath/runtimeClasspath của consumer. Commons-lang3 và Guava xuất hiện ở đâu? Liên hệ `Pair` trong public signature và `CharMatcher` trong implementation.

**Bài tập E — công bố sai API dependency.** Trong bản sao, đổi commons-lang3 từ `api` thành `implementation`, publish version mới và thử consumer compile. Vì sao public signature dùng `Pair` có thể khiến consumer thiếu type?

**Bài tập F — kiểm tra POM.** Đọc `pom-default.xml`, tìm compile/runtime scopes và Gradle metadata marker. Những thông tin variant nào không thể hiện trọn vẹn qua POM?

**Bài tập G — POM-only experiment.** Thay local repository bằng `mavenPom(); ignoreGradleMetadataRedirection()`. So sánh graph với bản dùng GMM. Vì sao một Java library đơn giản vẫn có thể chạy tương tự?

**Bài tập H — JVM version mismatch.** Chuyển consumer sang Java 11 baseline nhưng giữ producer Java 17. Quan sát variant mismatch, sau đó giải thích cách sửa thật mà không khai gian attribute.

**Bài tập I — sources variant.** Bỏ `withSourcesJar()` trong producer phiên bản thử nghiệm mới. Publish và kiểm tra files/metadata nào không còn xuất hiện. IDE cần source attachments sẽ ảnh hưởng thế nào?

**Bài tập J — platform.** Tạo một project `java-platform` công bố constraint commons-lang3. Vì sao publication phải dùng `components["javaPlatform"]` thay cho `components["java"]`?

**Bài tập K — custom capability.** Thiết kế tình huống hai providers công bố cùng capability. Hãy giải thích Gradle xử lý conflict theo model capabilities và vì sao Maven POM không bảo toàn đầy đủ điều này.

**Bài tập L — CI gate.** Xây workflow: unit tests → generate POM/GMM → validate metadata → publish staging → chạy consumer test → promotion. Gate phải chặn những trường hợp nào?

**Bài tập M — immutable version.** Nếu metadata `1.0.0` sai, vì sao nên phát hành version mới thay vì ghi đè POM/.module của `1.0.0` trên repository chung?

### Câu hỏi tự kiểm tra

1. GMM là gì, extension file thông thường là gì?
2. File `.module` được tạo từ đâu trong Gradle publication?
3. GMM và Maven POM khác nhau về variant model ra sao?
4. `SoftwareComponent` khác `Artifact` ở điểm nào?
5. Vì sao `from(components["java"])` hữu ích hơn chỉ attach JAR?
6. `apiElements` khác `runtimeElements` ở những dependency nào?
7. Vì sao library trả `Pair` trong public API nên khai báo commons-lang3 qua `api`?
8. Guava thuộc implementation dependency thì consumer cần nó lúc nào?
9. `org.gradle.usage=java-api` nói gì với resolver?
10. `org.gradle.jvm.version=17` ảnh hưởng consumer Java 11 thế nào?
11. Tên variant có phải duy nhất tiêu chí Gradle dùng để chọn không?
12. `withSourcesJar()` có biến sources thành runtime dependencies không?
13. Maven POM marker `published-with-gradle-metadata` có vai trò gì?
14. Vì sao mất file `.module` ở repository proxy có thể thay đổi consumer behavior?
15. Khi nào Gradle phải suy ra variants từ Maven POM?
16. Capabilities có thể biểu diễn điều gì mà Maven scopes không diễn đạt đầy đủ?
17. `components["javaPlatform"]` khác `components["java"]` ra sao?
18. `versionMapping` có phải mặc định phải bật cho mọi Java library không?
19. Lệnh nào xem outgoing variants của producer?
20. Lệnh nào xem compile/runtime dependency graph phía consumer?
21. Vì sao `publishToMavenLocal` khác publish vào `build/lab-repo`?
22. Vì sao published consumer test quan trọng hơn chỉ chạy producer `build`?
23. Khi metadata/POM không nhất quán, người duy trì cần kiểm tra những phần nào?
24. Tại sao publish lại cùng coordinates có thể gây lỗi cache/reproducibility?
25. GMM có thay thế artifact checksum/signature verification không?

**Tài liệu chính thức:**
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html)
- [Gradle — Variants and Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html)
- [Gradle — Customizing Publishing](https://docs.gradle.org/current/userguide/publishing_customization.html)
- [Gradle — Supported Metadata Formats](https://docs.gradle.org/current/userguide/supported_metadata_formats.html)

**Ghi nhớ:** **JAR mang mã thực thi, POM truyền hợp đồng Maven, còn `.module` truyền hợp đồng variant-aware giàu thông tin hơn**. Hãy publish từ đúng component, khai báo `api`/`implementation` theo public API và runtime thực, kiểm tra file `.module`/POM trong repository, và xác minh bằng **consumer từ artifact đã publish**. Metadata đúng là một phần của chất lượng bản phát hành, không phải thủ tục phụ sau khi build JAR thành công.