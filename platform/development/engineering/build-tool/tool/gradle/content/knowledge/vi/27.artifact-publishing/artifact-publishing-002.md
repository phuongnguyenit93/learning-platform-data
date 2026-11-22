# Công bố thư viện Java cùng sources JAR và Javadoc JAR bằng Gradle

## 1. Mục tiêu

Một Java library được dùng bởi nhiều ứng dụng thường không nên chỉ công bố file `.jar` chứa bytecode. Người dùng còn cần mã nguồn để IDE hỗ trợ đọc/debug và tài liệu Javadoc để tra cứu public API. Maven repository có thể lưu cả ba artifact của một phiên bản:

| File | Nội dung | Dành cho |
| --- | --- | --- |
| `greeter-lib-1.0.0.jar` | Java `.class`, runtime resources | Consumer compile/runtime |
| `greeter-lib-1.0.0-sources.jar` | Mã Java `.java` thuộc source set main | IDE/source attachment/debug |
| `greeter-lib-1.0.0-javadoc.jar` | HTML Javadoc do Javadoc tool tạo | API docs/IDE |

Chúng thuộc cùng Maven module:

~~~text
groupId    = org.example.training
artifactId = greeter-lib
version    = 1.0.0

GAV = org.example.training:greeter-lib:1.0.0
~~~

**Sources JAR và Javadoc JAR không thay thế binary JAR.** Khi consumer khai `implementation 'org.example.training:greeter-lib:1.0.0'`, Gradle giải quyết binary Java variant cho compile/runtime. IDE có thể tải các artifacts tài liệu; bạn không thêm `-sources.jar` hoặc `-javadoc.jar` vào application classpath như một thư viện chạy riêng.

Bài học tập trung vào Gradle **Groovy DSL** (`build.gradle`/`settings.gradle`) với Java 17. Bạn sẽ:
1. Tạo `java-library` và `maven-publish` publication.
2. Bật `java.withSourcesJar()`, `java.withJavadocJar()`.
3. Dùng `from components.java` để xuất bản đồng thời binary, sources, Javadoc.
4. Publish vào một **Maven file repository** trong `build/repo` để không đụng remote server.
5. Kiểm tra JAR contents, POM, Gradle Module Metadata và chạy consumer Java 17.
6. Phân biệt `assemble`, `publish`, `publishToMavenLocal`.
7. Hiểu versioning, API dependency scopes, signing, release CI và lỗi thường gặp.

## 2. Các khái niệm của Gradle publishing

~~~text
src/main/java
    |
    +--> compileJava --> jar ----------+
    |                                 |
    +--> sourcesJar -------------------+--> Java software component
    |                                 |          |
    +--> javadoc --> javadocJar -------+          |
                                                  v
                                            MavenPublication
                                             mavenJava
                                                  |
                                         POM + .module
                                                  |
                                                  v
                                     publishing.repositories
                                                  |
                                                  v
                                              build/repo
~~~

**Project:** chứa source code, tasks, `group`, `version`, dependencies.

**Component:** `components.java` mô tả Java output và variants, bao gồm API/runtime và documentation variants khi bật. Không phải một thư mục vật lý.

**Publication:** `MavenPublication` chọn artifact/component nào sẽ được publish, tọa độ GAV và POM metadata. Tên `mavenJava` trong bài là tên do build author đặt.

**Repository:** đích lưu các artifacts. `publishing.repositories` khác `repositories` dùng để resolve dependencies. Maven repository có thể là filesystem, Nexus/Artifactory hoặc endpoint từ xa.

### 2.1. `java-library`

~~~groovy
plugins {
    id 'java-library'
}
~~~

Java Library plugin áp dụng Java plugin capabilities, tạo `compileJava`, `jar`, `test`, source sets và phân biệt `api` với `implementation`:
- `api`: dependencies mà consumer cần trên compile classpath khi public API của thư viện dùng type của dependency.
- `implementation`: dependencies nội bộ, có thể cần khi chạy nhưng không tự lộ vào consumer compile classpath.
- `runtimeOnly`: dependencies cần tại runtime.
- `testImplementation`: dùng trong tests của publisher, không tự thuộc main library publication.

`java-library` tạo Java component nhưng **không tự upload** lên Maven repository.

### 2.2. `maven-publish`

~~~groovy
plugins {
    id 'maven-publish'
}
~~~

Plugin này thêm `publishing` extension, `MavenPublication`, tasks tạo POM/Gradle Module Metadata và các tasks publish. Chỉ áp plugin mà không tạo publication/component/repository chưa phải một quá trình xuất bản đầy đủ.

## 3. Hai methods để sinh sources và Javadoc artifacts

### 3.1. `withSourcesJar()`

~~~groovy
java {
    withSourcesJar()
}
~~~

Gradle đăng ký `sourcesJar` (classifier `sources`). Task này đóng gói Java sources thuộc `main` source set thành JAR, ví dụ:

~~~text
build/libs/greeter-lib-1.0.0-sources.jar
~~~

Gradle thêm một **documentation variant** vào Java component. Khi `maven-publish` lấy `components.java`, nguồn Java được đính kèm tự động. Sources Jar không chứa toàn bộ source của external dependencies và không phải runtime artifact.

Nếu main Java sources được sinh từ generator, bạn cần nối generated source folder bằng task provider/output property và đảm bảo generator chạy đúng trước khi packaging; đừng hard-code một output path thiếu dependency wiring.

### 3.2. `withJavadocJar()`

~~~groovy
java {
    withJavadocJar()
}
~~~

Gradle đăng ký `javadocJar` (classifier `javadoc`), sử dụng HTML do `javadoc` task sinh. File thường:

~~~text
build/libs/greeter-lib-1.0.0-javadoc.jar
~~~

Javadoc Jar chứa `Greeter.html` và HTML assets, không phải `Greeter.java` hay `Greeter.class`. Việc có Javadoc Jar đúng tên không bảo đảm docs tốt: public API comments phải được review và Javadoc task cần PASS.

### 3.3. Phối hợp với `from components.java`

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

Đây là đường tiêu chuẩn. Java extensions đăng ký artifacts và variants; Maven publication lấy component, nên **không cần thêm thủ công** `artifact tasks.sourcesJar`/`artifact tasks.javadocJar`.

Nếu vừa dùng `withSourcesJar()` vừa đăng ký một task tên `sourcesJar` khác, bạn có thể tạo task name conflict. Nếu tự thêm artifact có classifier `sources` vào cùng publication đã có documentation variant, có thể gây duplicate artifact conflict. Chỉ custom khi cần một variant đặc biệt và hiểu Gradle publishing APIs.

## 4. Maven coordinates, JAR names, classifier

Giả sử:

~~~groovy
group = 'org.example.training'
version = '1.0.0'

publishing {
    publications {
        mavenJava(MavenPublication) {
            artifactId = 'greeter-lib'
            from components.java
        }
    }
}
~~~

Kết quả GAV:

~~~text
org.example.training:greeter-lib:1.0.0
~~~

Maven repository layout thông thường:

~~~text
repo/
└── org/
    └── example/
        └── training/
            └── greeter-lib/
                ├── maven-metadata.xml
                └── 1.0.0/
                    ├── greeter-lib-1.0.0.jar
                    ├── greeter-lib-1.0.0-sources.jar
                    ├── greeter-lib-1.0.0-javadoc.jar
                    ├── greeter-lib-1.0.0.pom
                    └── greeter-lib-1.0.0.module
~~~

Đây là sơ đồ cốt lõi; Gradle có thể ghi thêm checksums như `.sha1`/`.sha256`/`.sha512`, repository metadata khác. Sources và Javadoc được phân biệt bằng **classifier**, nhưng giữ cùng group/artifact/version.

**Điểm dễ nhầm:** `artifactId` dùng cho **tên module khi publish**; filename do local task `jar` ghi trong `build/libs` còn phụ thuộc project/archive settings. Nếu project name khác artifactId, hai filename có thể khác nhau mà không phải lỗi.

## 5. Bài thực hành Java 17 chạy được

Bài lab không cần external Java libraries và **chỉ publish vào file Maven repository `build/repo`**, không dùng URL remote hay credentials.

### 5.1. Cấu trúc

~~~text
greeter-lib/
├── settings.gradle
├── build.gradle
├── src/
│   └── main/
│       └── java/
│           └── org/
│               └── example/
│                   └── greeter/
│                       └── Greeter.java
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Cần Gradle Wrapper tương thích với Java 17 và JDK 17 có sẵn hoặc Java toolchain resolver đã cấu hình. Nếu chưa có wrapper, dùng một Gradle tương thích đã cài để chạy `gradle wrapper` rồi commit đủ các file Wrapper.

### 5.2. `settings.gradle`

~~~groovy
rootProject.name = 'greeter-lib'
~~~

Project name trùng với publication artifactId để dễ đối chiếu. Trong dự án khác, không bắt buộc phải trùng.

### 5.3. `build.gradle` — toàn bộ file

~~~groovy
import org.gradle.api.publish.maven.MavenPublication
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.javadoc.Javadoc

plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'org.example.training'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }

    withSourcesJar()
    withJavadocJar()
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

tasks.withType(Javadoc).configureEach {
    options.encoding = 'UTF-8'
}

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            artifactId = 'greeter-lib'
            from components.java

            pom {
                name = 'Greeter Library'
                description = 'Java 17 library with sources and Javadoc'
            }
        }
    }

    repositories {
        maven {
            name = 'buildRepo'
            url = layout.buildDirectory.dir('repo')
        }
    }
}
~~~

**Phân tích theo thứ tự:**

1. `java-library` tạo Java model/component; `maven-publish` tạo publication/repository DSL.
2. `group`, `version`, `artifactId` xác định GAV.
3. `JavaLanguageVersion.of(17)` yêu cầu Java 17 toolchain cho những task tích hợp.
4. `withSourcesJar` và `withJavadocJar` tạo đúng documentation variants.
5. `JavaCompile.options.encoding` và `options.release` cấu hình source charset/Java API/bytecode target.
6. `Javadoc.options.encoding` giúp đọc Unicode comments.
7. `AbstractArchiveTask` flags giảm chênh lệch timestamps và entry ordering của ZIP/JAR.
8. `mavenJava(MavenPublication)` tạo publication có tên `mavenJava`.
9. `from components.java` lấy binary Java Jar và docs variants đã đăng ký.
10. `pom.name`/`description` thêm metadata POM cho người đọc.
11. Maven repo tên `buildRepo` được đặt dưới `build/repo`: **chỉ filesystem local**.
12. Không có `repositories { mavenCentral() }` vì lab không tải external dependencies. `publishing.repositories` chỉ định **nơi công bố**, không phải nơi tải Java dependencies.

### 5.4. `src/main/java/org/example/greeter/Greeter.java`

~~~java
package org.example.greeter;

/**
 * A tiny reusable Java library.
 *
 * <p>The publication includes binary, sources, and Javadoc JARs.
 */
public final class Greeter {

    private Greeter() {
        // Utility class.
    }

    /**
     * Builds a greeting for a recipient.
     *
     * @param name the recipient name
     * @return an English greeting
     */
    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

`Greeter` không có `main(String[])` vì đây là library. `Greeter.greet("Gradle")` trả chuỗi `"Hello, Gradle!"`; muốn thấy stdout, dùng consumer ở phần 8.

Javadoc comments có description class, method, `@param` và `@return`, nên Javadoc tool có đủ metadata cơ bản để tạo API HTML.

## 6. Xây và kiểm tra ba JAR trong `build/libs`

Từ thư mục root:

~~~bash
./gradlew clean assemble
~~~

`assemble` là lifecycle task tạo artifacts, và documentation JARs được Java extension đăng ký vào assemble khi có main feature. Những tasks có thể thấy trong log:

~~~text
:compileJava
:jar
:javadoc
:javadocJar
:sourcesJar
:assemble
~~~

Đây là **minh họa task names**, không phải stdout cố định. Thứ tự/status có thể khác theo Gradle version, cache, source set và configuration.

Kết quả theo cấu hình lab:

~~~text
build/libs/greeter-lib-1.0.0.jar
build/libs/greeter-lib-1.0.0-sources.jar
build/libs/greeter-lib-1.0.0-javadoc.jar
~~~

Kiểm tra archive contents:

~~~bash
jar tf build/libs/greeter-lib-1.0.0.jar
jar tf build/libs/greeter-lib-1.0.0-sources.jar
jar tf build/libs/greeter-lib-1.0.0-javadoc.jar
~~~

| JAR | Entry quan trọng |
| --- | --- |
| Binary | `org/example/greeter/Greeter.class` |
| Sources | `org/example/greeter/Greeter.java` |
| Javadoc | `org/example/greeter/Greeter.html` |

Các JAR cũng có thể chứa `META-INF/MANIFEST.MF`, `index.html`, CSS/JS/assets. Đừng coi một thứ tự entries cố định là hợp đồng: chỉ cần nội dung thực tế đúng.

### 6.1. Javadoc HTML nằm đâu trước khi package?

~~~bash
./gradlew javadoc
~~~

Đầu ra thường:

~~~text
build/docs/javadoc/index.html
build/docs/javadoc/org/example/greeter/Greeter.html
~~~

`javadocJar` đóng gói HTML output ấy. Nếu `javadoc` fail do doclint, `@param` sai tên, malformed HTML, source/encoding hoặc JDK toolchain, đừng bỏ `withJavadocJar` để “lách” yêu cầu có docs. Hãy sửa nguồn gây lỗi.

### 6.2. Tại sao Javadoc JAR không thể chạy?

Javadoc HTML không chứa Java bytecode mà JVM load làm class. Sources Jar chứa `.java` chưa compile, cũng không thể thay binary Jar. Các JAR này hỗ trợ developer, không phải artifacts runtime mặc định.

## 7. Publish đến local Maven repository

Task đích danh của lab:

~~~bash
./gradlew publishMavenJavaPublicationToBuildRepoRepository
~~~

Tên task được sinh từ:
- Publication `mavenJava`.
- Repository name `buildRepo`.
- Naming convention `publish<Publication>PublicationTo<Repository>Repository`.

Nó tạo POM và metadata, rồi copy artifacts vào Maven layout:

~~~text
build/repo/org/example/training/greeter-lib/1.0.0/
~~~

Files trọng tâm:

~~~text
greeter-lib-1.0.0.jar
greeter-lib-1.0.0-sources.jar
greeter-lib-1.0.0-javadoc.jar
greeter-lib-1.0.0.pom
greeter-lib-1.0.0.module
~~~

Có thể có checksum files kèm theo. Linux/macOS:

~~~bash
find build/repo/org/example/training/greeter-lib/1.0.0 -maxdepth 1 -type f | sort
~~~

PowerShell:

~~~powershell
Get-ChildItem -LiteralPath 'build/repo/org/example/training/greeter-lib/1.0.0'
~~~

Bài lab cũng có thể chạy:

~~~bash
./gradlew publish
~~~

Vì chỉ khai một Maven publication và một `publishing.repositories` nằm ở `build/repo`, `publish` trong lab không gửi gì lên remote server. Trong dự án có nhiều remote repositories, `publish` có thể publish **mọi publications đến mọi configured repositories**; không chạy khi chưa hiểu tác động.

### 7.1. Sinh metadata riêng không phải upload

~~~bash
./gradlew generatePomFileForMavenJavaPublication
./gradlew generateMetadataFileForMavenJavaPublication
~~~

Hai task tạo:
- Maven POM XML.
- Gradle Module Metadata `.module`.

Chúng có thể tạo files dưới `build/publications/mavenJava` nhưng **không publish toàn bộ artifacts** vào repository cho đến khi task publication chạy.

### 7.2. POM khác Gradle Module Metadata

**POM:** GAV, metadata dự án và dependencies/scopes theo Maven model.

**Gradle Module Metadata:** mô tả variant-aware dependencies/attributes/capabilities, có thể gồm documentation variants. Gradle consumers có thể sử dụng `.module` để chọn đúng compile/runtime variants, trong khi Maven consumers chủ yếu dùng POM.

Không sửa POM hoặc `.module` đã sinh bằng tay; cấu hình publishing model trong Gradle rồi generate lại.

## 8. Kiểm tra binary JAR bằng chương trình Java 17 consumer

### 8.1. Consumer trực tiếp với `javac`/`java`

Thêm file bên ngoài main source set của thư viện:

~~~text
greeter-lib/
└── demo-consumer/
    └── Consumer.java
~~~

**`demo-consumer/Consumer.java`:**

~~~java
import org.example.greeter.Greeter;

public final class Consumer {

    private Consumer() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("Gradle"));
    }
}
~~~

Sau khi chạy `./gradlew jar` hoặc `assemble`, từ library root trên Linux/macOS:

~~~bash
mkdir -p demo-consumer/out
javac --release 17 -encoding UTF-8 -cp build/libs/greeter-lib-1.0.0.jar -d demo-consumer/out demo-consumer/Consumer.java
java -cp "demo-consumer/out:build/libs/greeter-lib-1.0.0.jar" Consumer
~~~

**Stdout chính xác:**

~~~text
Hello, Gradle!
~~~

`-cp` của javac cung cấp Greeter type cho compiler; Java runtime classpath gồm directory chứa `Consumer.class` và binary JAR. Trên Unix-like OS dùng `:` giữa classpath entries.

PowerShell trên Windows dùng dấu `;`:

~~~powershell
New-Item -ItemType Directory -Force -Path 'demo-consumer/out' | Out-Null
javac --release 17 -encoding UTF-8 -cp 'build/libs/greeter-lib-1.0.0.jar' -d 'demo-consumer/out' 'demo-consumer/Consumer.java'
java -cp 'demo-consumer/out;build/libs/greeter-lib-1.0.0.jar' Consumer
~~~

**Không chạy** `java -cp ... org.example.greeter.Greeter` như một ứng dụng độc lập. `Greeter` không có `main`.

### 8.2. Consumer Gradle resolve Maven coordinates thật

Để xác minh repository vừa publish, tạo build độc lập trong thư mục:

~~~text
greeter-lib/
└── consumer-demo/
    ├── settings.gradle
    ├── build.gradle
    └── src/main/java/Consumer.java
~~~

**`consumer-demo/settings.gradle`:**

~~~groovy
rootProject.name = 'greeter-consumer'
~~~

**`consumer-demo/build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    maven {
        url = uri('../build/repo')
    }
}

dependencies {
    implementation 'org.example.training:greeter-lib:1.0.0'
}

application {
    mainClass = 'Consumer'
}
~~~

**`consumer-demo/src/main/java/Consumer.java`:**

~~~java
import org.example.greeter.Greeter;

public final class Consumer {

    private Consumer() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("Gradle"));
    }
}
~~~

Từ root publisher:

~~~bash
./gradlew publish
cd consumer-demo
../gradlew run --quiet
~~~

**Stdout consumer:**

~~~text
Hello, Gradle!
~~~

`consumer-demo` có settings.gradle riêng nên là Gradle build độc lập. `uri('../build/repo')` trỏ tới repository do parent library vừa publish. Consumer dùng GAV thay vì `project(':greeter-lib')`. Nếu chưa chạy `publish`, hoặc `clean` đã xóa `build/repo`, consumer có thể không resolve được module.

PowerShell:

~~~powershell
.\gradlew.bat publish
Set-Location consumer-demo
..\gradlew.bat run --quiet
~~~

Kiểm tra graph trong `consumer-demo`:

~~~bash
../gradlew dependencies --configuration runtimeClasspath
../gradlew dependencyInsight --configuration runtimeClasspath --dependency greeter-lib
~~~

Báo cáo phụ thuộc version/configuration nên không có stdout chuẩn cố định; cần thấy GAV được resolve. IDE có thể tải sources/Javadoc từ Maven repo, nhưng consumer `implementation` chỉ nêu GAV chính.

## 9. `assemble`, `publish` và `publishToMavenLocal`

| Lệnh | Thực hiện |
| --- | --- |
| `assemble` | Tạo JARs trong `build/libs`, không publish repository |
| `jar` | Binary main JAR |
| `sourcesJar` | Java source JAR |
| `javadoc` | HTML documentation |
| `javadocJar` | HTML Javadoc đóng gói trong JAR |
| `generatePomFileForMavenJavaPublication` | Sinh POM |
| `generateMetadataFileForMavenJavaPublication` | Sinh `.module` |
| `publishMavenJavaPublicationToBuildRepoRepository` | Publish mavenJava vào buildRepo |
| `publish` | Publish mọi publications đến mọi configured `publishing.repositories` |
| `publishToMavenLocal` | Publish vào Maven Local của user, thường `~/.m2/repository` |
| `publishMavenJavaPublicationToMavenLocal` | Publish đúng mavenJava vào Maven Local |

Maven Local **không đồng nghĩa** folder `build/repo`. `publishToMavenLocal` không phải cách kiểm tra chính của lab vì có thể làm cache người dùng chứa artifact cùng GAV từ lần thử cũ và khiến consumer resolve nhầm.

Các hướng dẫn Gradle cũng lưu ý Maven Local không phải một repository phát hành đáng tin cậy cho production: có thể thiếu artifacts, dễ overwrite và làm CI khó tái lập. Với lab dùng file Maven repository riêng trong `build/` để thấy đúng bộ publication vừa xây.

## 10. Phân biệt `api`, `implementation` và published dependencies

Nếu một Java library có third-party dependencies, dùng `java-library` giúp đưa thông tin đúng cho consumer. Ví dụ **snippet minh họa** (không thêm vào lab offline nếu không cần):

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    api 'com.google.guava:guava:33.4.0-jre'
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}
~~~

- `api` khi public API cần Guava types ở compile classpath của consumer.
- `implementation` cho code nội bộ; consumer runtime có thể cần nó, nhưng compile API không nên phơi ra.
- `testImplementation` phục vụ tests của publisher.

POM có mapping sang Maven compile/runtime scopes, Gradle Module Metadata mô tả variants chi tiết hơn. Nếu public method trả Guava type mà Guava khai `implementation`, consumer có thể compile fail. Sửa scope trong publisher, đừng patch generated POM bằng tay.

### 10.1. Declared vs resolved versions

Khi phát hành Maven publication, version declarations trong POM mặc định thường dựa trên các dependency version được **khai trong build model**, không nhất thiết version cuối sau conflict resolution. Gradle hỗ trợ `versionMapping` nếu release cần publish resolved versions.

Snippet nâng cao, **thay cho** block publication khác:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            versionMapping {
                usage('java-api') {
                    fromResolutionOf('runtimeClasspath')
                }
                usage('java-runtime') {
                    fromResolutionResult()
                }
            }
        }
    }
}
~~~

Dùng khi có lý do rõ, hiểu graph/locking và khả năng khác nhau giữa API/runtime variants. Không áp mù quáng hoặc lặp `from components.java` trong cùng publication.

## 11. Publication và POM metadata khi phát hành thật

Lab có `pom.name`/`description` nhưng public repositories thường yêu cầu thêm:
- `groupId`/`artifactId`/`version` hợp lệ và namespace bạn có quyền sử dụng.
- Project URL và source-code management URLs.
- Developer/maintainer metadata.
- License thực sự áp dụng.
- Signed artifacts và checksums theo policy.
- Release không bị overwrite âm thầm.

Ví dụ **snippet POM metadata**:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            pom {
                name = 'Greeter Library'
                description = 'Example Java library'
                licenses {
                    license {
                        name = 'The Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
                    }
                }
            }
        }
    }
}
~~~

**Chỉ khai Apache-2.0 khi thư viện thực sự mang license ấy.** Đây là ví dụ cấu trúc, không phải license tự động cho mọi project. Project URL/SCM/developer details cần được điền bằng thông tin thật khi release.

**Không nhầm POM description với Javadoc JAR.** POM mô tả module và dependencies; Javadoc JAR chứa HTML documentation của API.

## 12. Remote Maven repositories và quyền phát hành

Khi chuyển từ `build/repo` sang Nexus/Artifactory/GitHub Packages:
1. Chọn releases/snapshots repository URL đúng.
2. Dùng HTTPS hoặc transport được doanh nghiệp cho phép.
3. Lấy credentials/token từ CI secret store hoặc user-private properties.
4. Giới hạn publish jobs trên tags/branches/trusted release context.
5. Chạy checks/tests trước publish.
6. Xác minh repo có policy immutable releases.
7. Kiểm tra đủ binary/sources/Javadoc/POM/signature/checksum artifacts.

Ví dụ **snippet** cần Gradle project property và CI environment variables thực, **không dùng trong lab local**:

~~~groovy
def releaseUrl = providers.gradleProperty('releaseRepositoryUrl')

publishing {
    repositories {
        maven {
            name = 'releaseRepo'
            url = uri(releaseUrl.get())

            credentials {
                username = providers.environmentVariable('MAVEN_USER').orNull
                password = providers.environmentVariable('MAVEN_PASSWORD').orNull
            }
        }
    }
}
~~~

Cấu hình trên đòi `releaseRepositoryUrl` có giá trị; nếu không có, `.get()` có thể fail ngay trong configuration. Trong build production nên chỉ kích hoạt remote release repository ở đúng release pipeline và kiểm soát missing credentials rõ, tránh làm mọi lệnh `help` của developer cần deploy secrets.

**Maven Central:** Từ năm 2025, Central đã thay đổi khỏi OSSRH legacy upload protocol. Không giả định chỉ thêm Maven Central URL vào Gradle `maven-publish` là publish được; dùng Central Publishing workflow/plugin/portal hiện hành và đáp ứng namespace/metadata/signing rules.

### 12.1. Snapshot và release version

- `1.0.0`: release, thường cần immutable bytes.
- `1.0.1`: phiên bản mới khi sửa lỗi.
- `1.1.0-SNAPSHOT`: bản phát triển thử nghiệm nếu repository policy dùng snapshot naming.

Không upload nhiều artifacts khác bytes dưới **cùng release GAV** rồi cho rằng consumers sẽ luôn nhìn bản mới. Caches, mirrors và checksum verification có thể lưu version cũ; phiên bản phải phản ánh release.

## 13. Signing và checksums

Gradle có **Signing Plugin**:

~~~groovy
plugins {
    id 'signing'
}

signing {
    sign publishing.publications.mavenJava
}
~~~

Đây là snippet bổ sung khi publication `mavenJava` đã có, cần cấu hình signing keys/credentials phù hợp. Signing plugin có thể nối tasks ký vào publication tasks. Không lưu private keys/passwords trong tracked `build.gradle` hoặc `gradle.properties` của repository.

Phân biệt:
- SHA-256 checksum dùng để kiểm tra **bytes có khớp không** với nguồn tin cậy.
- Digital signature dùng **key identity/trust model** để kiểm tra nguồn gốc và integrity.
- Checksums không tự xác nhận publisher identity.
- Signing không làm code hết bug/security vulnerabilities.

Maven Publish có thể sinh checksum files cho file/remote Maven repository; `publishToMavenLocal` không tạo checksum sidecars theo cùng cách. Vì vậy đừng dùng Maven Local làm bằng chứng duy nhất về signing/checksum policy.

**Tính nhất quán sources/Javadoc:** ba JAR nên tạo từ cùng source commit, cùng version, cùng Java toolchain và cùng build pipeline. Nếu binary từ commit A nhưng sources từ commit B, IDE có thể hiển thị code khác bytecode thực. Review contents chứ không chỉ filename.

## 14. Reproducible JAR và Javadoc

Trong lab:

~~~groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Hai tùy chọn giúp archive entries không phụ thuộc vào mtime/tùy tiện thứ tự files. Với Gradle versions hiện đại, những behavior này có thể đã là defaults; explicit config cho thấy policy và hỗ trợ đối chiếu.

Nhưng **chưa đủ** để khẳng định artifacts hoàn toàn byte-for-byte reproducible:
- Javadoc HTML có thể chèn timestamp của doc generator.
- Annotation processors/generated Java có thể ghi build time/random values.
- Compiler/JDK vendor/patch version khác nhau tạo output khác.
- Manifest/POM/metadata có thể dùng hostname/absolute paths.
- Newline/encoding và dependency versions ảnh hưởng output.
- Source/formatter/code-generator plugin versions khác nhau.

Nếu yêu cầu tái lập Javadoc JAR chính xác, cần kiểm tra Javadoc tool option bỏ timestamp trên JDK đang dùng và so sánh HTML bytes. Đừng tin rằng ZIP timestamp settings tự sửa nội dung HTML.

Thử hai clean builds trên cùng môi trường:

~~~bash
./gradlew clean assemble
sha256sum build/libs/greeter-lib-1.0.0.jar
sha256sum build/libs/greeter-lib-1.0.0-sources.jar
sha256sum build/libs/greeter-lib-1.0.0-javadoc.jar
~~~

Lưu ba hashes, chạy lại và so sánh. Nếu khác, điều tra từng artifact theo entries, generated docs, toolchain và metadata. Việc hash trùng trên một máy **không** chứng minh tất cả OS/JDK environments sẽ có output giống nhau.

## 15. Nhiều Gradle modules: publish từng library

Giả sử:

~~~text
root/
├── settings.gradle
├── build.gradle
├── core/build.gradle
└── client/build.gradle
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'multi-library'
include 'core', 'client'
~~~

Mỗi Java library module có thể dùng một convention cấu hình tương tự:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'org.example.training'
version = '1.0.0'

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            artifactId = project.name
            from components.java
        }
    }
}
~~~

Đây là **snippet module**, chưa phải project chạy độc lập (cần repository, sources và policy khác). Nếu `core` và `client` là hai projects, published GAVs có thể là:

~~~text
org.example.training:core:1.0.0
org.example.training:client:1.0.0
~~~

Không publish root project không có Java component bằng `from components.java`. Nếu `client` phụ thuộc `api project(':core')`, hãy publish cả hai modules và kiểm tra published POM/`.module` để consumers ngoài multi-project build resolve đúng `core`.

Với 10–20 modules, dùng **convention plugin** để thống nhất toolchain, sources/Javadoc policy, versioning và Maven metadata, thay vì copy/paste cấu hình quá nhiều lần. Nhớ rằng một convention plugin áp tại module mới thấy `components.java` của module đó.

## 16. Chẩn đoán lỗi phổ biến

| Dấu hiệu | Lý do có thể | Cách sửa |
| --- | --- | --- |
| `Task sourcesJar not found` | Chưa gọi `withSourcesJar()` đúng project | Bật Java sources artifact |
| `Task javadocJar not found` | Chưa gọi `withJavadocJar()` | Bật Javadoc artifact |
| `components.java` không tồn tại | Không apply Java plugin ở project ấy | Áp `java-library` đúng module |
| Không nhận `MavenPublication` | Chưa apply `maven-publish` | Áp plugin và khai publication |
| Chỉ publish binary | Chưa bật docs variants hoặc publication không dùng Java component | Bật hai methods và `from components.java` |
| Duplicate `sourcesJar` task | Tạo custom task trùng Java extension task | Bỏ duplicate manual registration |
| `javadoc` fail | Malformed comments, doclint, JDK/encoding | Chạy `javadoc --info` và sửa nguồn |
| `No matching toolchains` | Không có JDK17 matching | Cài/provision JDK17 đúng policy |
| `build/libs` có JAR, `build/repo` trống | Chưa chạy publish | Chạy publication task đích danh |
| `publishToMavenLocal` không có file trong build repo | Maven Local là repository khác | Dùng `publish`/buildRepo task của lab |
| Consumer không tìm thấy module | Chưa publish, sai GAV, sai Maven URL | Kiểm tra repository tree và coordinates |
| Runtime `ClassNotFoundException` | Binary Jar thiếu khỏi classpath | Dùng binary JAR, không dùng sources/Javadoc thay thế |
| IDE thiếu sources | Artifact docs chưa publish/IDE chưa tải | Kiểm tra `-sources.jar` và IDE download |
| Sources jar không có file mong đợi | Main source set/generator output sai | Xem `sourceSets.main`, `jar tf` |
| Javadoc jar thiếu HTML | Javadoc task/source không tạo docs | Xem `build/docs/javadoc` |
| Consumer compile thiếu API type | `api`/`implementation` không đúng | Sửa public API dependency scopes |
| POM version lạ | Declared vs resolved version mapping | Kiểm tra POM, `versionMapping`, dependency graph |
| Remote 401/403 | Token/role/URL không hợp lệ | Kiểm tra CI secrets và permissions |
| Remote release đã có | GAV immutable | Bump version, không overwrite |
| Central upload lỗi | Legacy endpoint/workflow | Dùng Central workflow mới |
| Hash Javadoc JAR thay đổi | HTML timestamp/generator/toolchain | Kiểm tra docs byte determinism |
| `publish` tác động server ngoài ý muốn | Có remote repository trong publishing | Giới hạn publish tasks và CI permissions |

### 16.1. Bộ lệnh chẩn đoán lab

~~~bash
./gradlew tasks --all
./gradlew clean assemble
./gradlew javadoc --info
./gradlew generatePomFileForMavenJavaPublication
./gradlew generateMetadataFileForMavenJavaPublication
./gradlew publishMavenJavaPublicationToBuildRepoRepository
jar tf build/libs/greeter-lib-1.0.0.jar
jar tf build/libs/greeter-lib-1.0.0-sources.jar
jar tf build/libs/greeter-lib-1.0.0-javadoc.jar
~~~

Các task publication names tương ứng cụ thể `mavenJava` và `buildRepo` trong lab; nếu tên khác, chạy `tasks --all` thay vì đoán.

## 17. Bài tập có đáp án

### Bài 1 — Phân biệt JAR
**Hỏi:** Binary JAR, sources JAR, Javadoc JAR chứa những gì?

**Đáp án:** Bytecode `.class` và runtime resources; main Java sources `.java`; HTML API docs do Javadoc tool tạo.

### Bài 2 — Bật tài liệu
**Hỏi:** Cần hai methods nào trong `java {}`?

**Đáp án:** `withSourcesJar()` và `withJavadocJar()`.

### Bài 3 — Publish thành phần Java
**Hỏi:** Dòng nào trong `MavenPublication` lấy Java binary và docs variants?

**Đáp án:** `from components.java`.

### Bài 4 — Tọa độ
**Hỏi:** Group `org.example.training`, artifactId `greeter-lib`, version `1.0.0` tạo GAV/path nào?

**Đáp án:** `org.example.training:greeter-lib:1.0.0`, path `org/example/training/greeter-lib/1.0.0/`.

### Bài 5 — Local output khác publish
**Hỏi:** Sau `assemble` có đủ ba JAR dưới `build/libs` nhưng chưa có `build/repo`, có lỗi không?

**Đáp án:** Không. `assemble` chỉ xây archives, cần `publish` hoặc publish task của lab mới tạo Maven repository.

### Bài 6 — Maven Local
**Hỏi:** `publishToMavenLocal` có publish vào `build/repo` không?

**Đáp án:** Không. Maven Local thường dưới `~/.m2/repository`, khác `publishing.repositories` của lab.

### Bài 7 — Consumer
**Hỏi:** Vì sao `java -cp greeter-lib-1.0.0.jar org.example.greeter.Greeter` không chạy như ứng dụng?

**Đáp án:** `Greeter` không có `main`. Consumer.main gọi Greeter.greet rồi in `Hello, Gradle!`.

### Bài 8 — Scope
**Hỏi:** Public method trả về Guava type, consumer cần Guava compile. Khai `api` hay `implementation`?

**Đáp án:** `api` khi public API thực sự phụ thuộc type Guava.

### Bài 9 — Javadoc fail
**Hỏi:** `jar` PASS, `javadocJar` FAIL vì malformed comment. Có nên xóa Javadoc variant?

**Đáp án:** Không nếu phát hành yêu cầu docs. Sửa comments/doclint trước release.

### Bài 10 — Metadata
**Hỏi:** Có POM rồi, tại sao còn `.module`?

**Đáp án:** Gradle Module Metadata giữ variant/attribute/dependency details phong phú hơn POM và giúp Gradle consumers chọn đúng biến thể.

### Bài 11 — Artifact integrity
**Hỏi:** Binary và source jars cùng version nhưng source khác commit thì có ổn không?

**Đáp án:** Không, debugger/IDE sẽ đọc source không khớp bytecode. Build cả ba từ cùng release state.

### Bài 12 — Signatures
**Hỏi:** SHA-256 có chứng minh publisher identity không?

**Đáp án:** Không. SHA-256 là checksum; để xác minh nguồn gốc cần signature và trust model phù hợp.

### Bài 13 — Repository
**Hỏi:** Thêm `repositories { mavenCentral() }` trong Java project có nghĩa đã publish lên Central chưa?

**Đáp án:** Không. Đó là repository để tải dependencies, không phải publishing target.

### Bài 14 — Trùng task
**Hỏi:** Tại sao không nên tự tạo `sourcesJar` nếu đã gọi `withSourcesJar()`?

**Đáp án:** Java extension đã đăng ký task/variant; custom task trùng có thể gây conflict. Dùng model chuẩn trừ khi có yêu cầu đặc biệt.

### Bài 15 — Thực hành tự kiểm tra
1. Tạo toàn bộ project Java 17 phần 5.
2. Chạy `clean assemble`, tìm ba files `build/libs`.
3. Chạy `jar tf` trên từng JAR và kiểm tra entries class/source/HTML.
4. Chạy `publishMavenJavaPublicationToBuildRepoRepository`, kiểm tra Maven folder.
5. Đọc POM/`.module` và xác minh GAV.
6. Biên dịch/chạy consumer bằng `javac`/`java`, so stdout.
7. Tạo consumer Gradle độc lập, resolve từ `../build/repo` và chạy.
8. Đổi version thư viện thành `1.0.1`, publish, rồi đổi consumer dependency và chạy lại.
9. Sửa Javadoc comment, rebuild, xem file HTML trong Javadoc JAR thay đổi đúng.
10. Giải thích vì sao không dùng `publishToMavenLocal` làm release pipeline production.

**Tiêu chí đạt:** bạn tự tạo được Java library publication với ba JAR, hiểu Maven coordinates/POM/`.module`, phân biệt publish và Maven Local, kiểm tra consumer chạy đúng và biết các điều kiện cần có khi release lên server.

## 18. Checklist trước khi phát hành

- [ ] Có Java component đúng và `maven-publish`.
- [ ] `groupId`/`artifactId`/`version` đúng release policy.
- [ ] `withSourcesJar()` và `withJavadocJar()` đã bật.
- [ ] MavenPublication dùng `from components.java` không duplicate artifacts.
- [ ] `javadoc` task và Java compile PASS.
- [ ] Binary/sources/Javadoc JAR đều có đúng entries.
- [ ] Sources artifact không chứa secrets/private files ngoài dự kiến.
- [ ] POM/Gradle Module Metadata có tọa độ và dependencies đúng.
- [ ] `api`/`implementation` phản ánh public API.
- [ ] Consumer độc lập resolve GAV và chạy test.
- [ ] Gradle Wrapper/toolchain/generator versions ổn định.
- [ ] Release artifacts tạo từ cùng commit/version/config.
- [ ] Repositories publish khác dependencies repositories được cấu hình rõ.
- [ ] CI release không chạy từ PR không tin cậy.
- [ ] Credentials và signing keys nằm trong secret store, không commit.
- [ ] License/project/SCM metadata phản ánh thông tin thật.
- [ ] Checksum/signature verification đáp ứng chính sách repository.
- [ ] Không overwrite immutable release version.
- [ ] Maven Central nếu cần dùng Central Publishing workflow hiện hành.
- [ ] Không dùng Maven Local làm nguồn duy nhất kiểm chứng release.
- [ ] Multi-module dependencies được publish đầy đủ.
- [ ] Không xóa documentation variants để che lỗi Javadoc/source set.

## 19. Tài liệu chính thức

- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): `MavenPublication`, `publish`, `publishToMavenLocal`, sources/Javadoc và repositories.
- [Gradle — Publishing a Project as a Module](https://docs.gradle.org/current/userguide/publishing_setup.html): Java component và local Maven file repository.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`/`implementation` và consumer dependencies.
- [Gradle — JavaPluginExtension API](https://docs.gradle.org/current/javadoc/org/gradle/api/plugins/JavaPluginExtension.html): `withSourcesJar`, `withJavadocJar` và documentation variants.
- [Gradle — Publishing Customization](https://docs.gradle.org/current/userguide/publishing_customization.html): variants, metadata và version mapping.
- [Gradle — Publishing Overview](https://docs.gradle.org/current/userguide/publishing_overview.html): component/publication/repository concepts.
- [Gradle — Repository Types](https://docs.gradle.org/current/userguide/supported_repository_types.html): local Maven repo và Maven Local caveats.
- [Gradle — Signing Artifacts](https://docs.gradle.org/current/userguide/publishing_signing.html): Signing Plugin.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum/signature verification.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `jar`, `javadoc`, source sets và Java toolchains.
- [Gradle — Working With Files](https://docs.gradle.org/current/userguide/working_with_files.html): archive normalization và reproducible artifacts.
