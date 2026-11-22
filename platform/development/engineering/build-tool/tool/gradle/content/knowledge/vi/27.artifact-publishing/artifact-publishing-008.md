# Kiểm tra metadata và dùng dự án consumer để xác minh artifact trong Gradle

## 1. Bối cảnh và mục tiêu

Một thư viện Java có thể biên dịch và publish thành công, nhưng downstream project vẫn không thể sử dụng: tọa độ Maven sai, POM thiếu dependency bắc cầu, Gradle Module Metadata có variant không tương thích, JAR không chứa class mong đợi, hoặc consumer đang dùng một release cũ được cache. Vì vậy việc kiểm tra **Xuất bản artifact** không dừng ở việc nhìn thấy `BUILD SUCCESSFUL` của task `publish`.

Cần xác minh ba lớp:

1. **Artifact thực tế:** file JAR, sources/Javadoc, bytecode, checksums.
2. **Metadata:** Maven POM, Gradle Module Metadata (`.module`), Maven repository layout và versions.
3. **Hành vi consumer:** một Gradle build **độc lập** resolve module từ repository theo tọa độ `group:artifact:version`, biên dịch Java 17, chạy test và dùng đúng transitive dependencies.

Bài Knowledge thuộc nhóm **Xuất bản artifact** của **Build Tool Gradle**, sử dụng Gradle Kotlin DSL và Java 17. Ta tạo producer library tên `greeting-lib` và consumer application độc lập, xuất bản vào một Maven repository dạng thư mục. Producer dùng Commons Lang chỉ ở implementation; consumer không khai báo Commons Lang trực tiếp, nên kiểm tra runtime sẽ cho biết metadata bắc cầu có được publish đúng hay không.

Sau khi học, bạn sẽ biết cách:

- Cấu hình `java-library` và `maven-publish` với `MavenPublication`.
- Dùng `from(components["java"])` để xuất bản cả JAR lẫn thông tin dependencies.
- Xác minh groupId, artifactId, version, JAR, POM, `.module`, source/Javadoc.
- Phân biệt POM Maven scopes `compile`/`runtime` và Gradle variants `apiElements`/`runtimeElements`.
- Dùng `outgoingVariants`, `dependencies` và `dependencyInsight` để điều tra variant resolution.
- Viết Gradle consumer fixture độc lập, test public API và transitive runtime classpath.
- Phát hiện lỗi do caches, Maven local, repository URL, Java target và sai variant attributes.
- Thiết kế staging-repository quality gate trước khi phát hành artifact chính thức.

## 2. Publication có những tệp nào?

Với Java component và Maven Publish plugin, thư viện có thể tạo:

| File | Ý nghĩa | Kiểm tra chính |
| --- | --- | --- |
| `greeting-lib-1.0.0.jar` | Binary artifact chứa `.class` | Public API class/method có mặt |
| `greeting-lib-1.0.0.pom` | Maven metadata | Coordinates, dependencies và scopes |
| `greeting-lib-1.0.0.module` | Gradle Module Metadata JSON | Variants, attributes, deps/capabilities |
| `greeting-lib-1.0.0-sources.jar` | Source attachment | `.java` có trong JAR |
| `greeting-lib-1.0.0-javadoc.jar` | Documentation attachment | HTML API docs |
| `.sha256`/`.sha512` sidecars | Artifact integrity data | Hash phù hợp trusted source |
| `maven-metadata.xml` | Maven repository metadata | Versions/snapshots trong repo |

**Đừng nhầm:** POM là mô tả một Maven module, `.module` là mô hình Gradle variant-aware resolution và `maven-metadata.xml` là metadata cấp repository/version listing. Chúng không thay thế cho nhau.

Một Maven coordinate có ba thành phần:

~~~text
groupId    = dev.example
artifactId = greeting-lib
version    = 1.0.0

Gradle dependency notation:
dev.example:greeting-lib:1.0.0
~~~

Repository layout chuyển dấu chấm của group thành đường dẫn:

~~~text
repository/dev/example/greeting-lib/1.0.0/
    greeting-lib-1.0.0.jar
    greeting-lib-1.0.0.pom
    greeting-lib-1.0.0.module
    greeting-lib-1.0.0-sources.jar
    greeting-lib-1.0.0-javadoc.jar
~~~

Có thể có checksum files cạnh từng artifact. File list này chỉ minh họa phần chính của một publication, không phải cam kết mọi repository đều có cùng sidecars.

## 3. POM và Gradle Module Metadata khác nhau

Maven POM chứa tọa độ, dependencies, dependency scopes và các trường dự án:

~~~xml
<groupId>dev.example</groupId>
<artifactId>greeting-lib</artifactId>
<version>1.0.0</version>
~~~

Thông tin phụ thuộc xuất bản từ Gradle Java Library plugin thường map:

- Producer `api(...)` -> Maven `compile` scope.
- Producer `implementation(...)` -> Maven `runtime` scope.
- Producer `runtimeOnly(...)` -> Maven `runtime` scope.
- Producer `testImplementation(...)` -> không tự là production transitive dependency.
- Một số trường hợp `compileOnlyApi`, constraints và feature variants cần xem mapping cụ thể.

Gradle Module Metadata (`.module`) là JSON có component group/module/version và **các variants**. Gradle có thể dùng:

- `apiElements`: dùng cho Java compile/API consumption.
- `runtimeElements`: dùng cho runtime consumption.
- Các variants cho sources/Javadoc nếu component publish chúng.
- Attributes như `org.gradle.usage`, `org.gradle.category`, `org.gradle.libraryelements`, `org.gradle.jvm.version`.
- Dependencies, dependency constraints, capabilities hoặc rich versions.

POM không biểu diễn đầy đủ mọi Gradle-specific feature. Vì vậy, nếu thư viện phục vụ cả Gradle và Maven, phải kiểm tra POM **và** `.module`, thậm chí dùng hai consumer fixtures riêng khi có variant/capability semantics phức tạp.

## 4. Thiết kế lab bằng hai build độc lập

Ta không tạo `root settings.gradle.kts` include cả producer và consumer như subprojects. Cấu trúc:

~~~text
publishing-lab/
├── producer/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   ├── src/main/java/dev/example/greeting/Greeting.java
│   ├── gradlew, gradlew.bat
│   └── gradle/wrapper/...
├── consumer/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   ├── src/main/java/client/Main.java
│   ├── src/test/java/client/PublishedLibraryTest.java
│   ├── gradlew, gradlew.bat
│   └── gradle/wrapper/...
└── repository/        (producer publish sẽ tạo)
~~~

Điều kiện: Có Gradle Wrapper hợp lệ trong mỗi build, JDK 17 được Gradle tìm thấy qua toolchain hoặc resolver, và có Maven Central/mirror hợp lệ để tải Commons Lang và JUnit. Nếu tạo mới từ thư mục rỗng, trước tiên khởi tạo Wrapper theo quy trình tin cậy; không tải một `gradle-wrapper.jar` không rõ nguồn.

Ưu điểm của file repository `../repository`:

- Cách ly khỏi `~/.m2/repository` (Maven local) đã có artifacts từ những lần publish khác.
- Dễ kiểm tra từng file POM/.module/JAR.
- Consumer có thể được cấu hình chỉ dùng repo này cho group `dev.example`.
- Trong CI có thể tạo workspace/repo tạm để test đúng candidate.

Với một release thật, thay file repository bằng một **staging repository** được quản lý; giữ nguyên ý tưởng consumer chỉ đọc artifacts đã publish.

## 5. Producer: Gradle Java Library hoàn chỉnh

**producer/settings.gradle.kts**

~~~kotlin
rootProject.name = "producer"
~~~

**producer/build.gradle.kts**

~~~kotlin
import org.gradle.api.publish.maven.MavenPublication
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    `java-library`
    `maven-publish`
}

group = "dev.example"
version = "1.0.0"

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
    // Dependency chỉ dùng bên trong method body.
    implementation("org.apache.commons:commons-lang3:3.14.0")
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            // Publish software component, không chỉ JAR rời.
            from(components["java"])

            artifactId = "greeting-lib"

            pom {
                name.set("Greeting Library")
                description.set(
                    "Library for verifying Gradle publication metadata."
                )
            }
        }
    }

    repositories {
        maven {
            name = "lab"
            // Đường dẫn tương đối producer/../repository
            url = uri("../repository")
        }
    }
}
~~~

Các quyết định quan trọng:

- `java-library` tạo Java software component với API/runtime variant separation.
- `maven-publish` tạo các tasks generate POM/module và publish.
- `group="dev.example"`, `artifactId="greeting-lib"`, `version="1.0.0"` tạo tọa độ Maven thật.
- `rootProject.name="producer"` **không đồng nghĩa** artifactId `producer`, bởi publication override artifactId.
- `from(components["java"])` lấy các artifacts/dependencies theo Java component. Nếu chỉ thêm `artifact(tasks.jar)`, POM có thể thiếu thông tin dependency contract.
- `withSourcesJar()` và `withJavadocJar()` gắn secondary artifacts; `-sources.jar`/`-javadoc.jar` không thay primary `.jar`.
- Java toolchain và `options.release.set(17)` quy định compiler/JVM target; consumer Java 11 không mặc định tương thích.
- `implementation` giữ Commons Lang trong runtime dependency metadata nhưng không xuất ra compile API khi public signature không dùng type của nó.

### 5.1. Producer source Java 17

**producer/src/main/java/dev/example/greeting/Greeting.java**

~~~java
package dev.example.greeting;

import java.util.Objects;
import org.apache.commons.lang3.StringUtils;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        Objects.requireNonNull(name, "name");
        return "Xin chào, "
                + StringUtils.capitalize(name)
                + "!";
    }
}
~~~

File phải được lưu UTF-8. Public API nhận `String`, trả `String`; `StringUtils` chỉ xuất hiện **trong implementation**, không phải trong public method signature. Vì vậy `implementation("commons-lang3")` là lựa chọn hợp lý, còn runtime của consumer phải có Commons Lang nếu gọi `message()`.

Trong lab này producer không có unit tests riêng; một thư viện thật nên có producer tests trước publish. Consumer contract test ở phần sau kiểm tra trực tiếp JAR đã xuất bản.

## 6. Sinh metadata và JAR ở producer

Trong thư mục `producer/`:

~~~bash
./gradlew clean build --console=plain
~~~

Sau đó có thể sinh hai metadata files riêng để xem:

~~~bash
./gradlew \
  generatePomFileForMavenJavaPublication \
  generateMetadataFileForMavenJavaPublication \
  --console=plain
~~~

Các tên task được tạo từ publication tên `mavenJava`. Gradle Maven Publish plugin thường lưu output như:

~~~text
build/publications/mavenJava/
├── pom-default.xml
└── module.json
~~~

**Đây chỉ là generated intermediate metadata**, chưa chứng minh repository đã nhận chúng. Cần kiểm tra lại file đã publish sau khi chạy task publish.

### 6.1. Xem outgoingVariants

~~~bash
./gradlew outgoingVariants --console=plain
~~~

Task in variants/attributes của producer, ví dụ `apiElements`, `runtimeElements`, `sourcesElements`, `javadocElements`. Nó hữu ích để so với `.module` ở repository khi consumer gặp **No matching variant**.

Đừng suy luận `outgoingVariants` tự kiểm chứng remote Maven repository; đó là view của producer component model trong build hiện tại.

### 6.2. Kiểm tra JAR từ producer

~~~bash
jar tf build/libs/producer-1.0.0.jar
~~~

Tên local binary JAR thường dựa vào project name `producer`, trong khi published primary artifact sẽ có tên dựa trên `artifactId` là `greeting-lib`. Nếu producer đã tùy biến archiveFileName, phải xem tên file thật.

Trong file listing mong đợi có:

~~~text
dev/example/greeting/Greeting.class
~~~

## 7. Publish vào Maven file repository

Trong `producer/`:

~~~bash
./gradlew publishMavenJavaPublicationToLabRepository \
  --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat publishMavenJavaPublicationToLabRepository --console=plain
~~~

Vì publication tên `mavenJava`, repo tên `lab`, Gradle tạo task này tự động. Task được nhắm **duy nhất một publication và một repository**.

Có thể dùng:

~~~bash
./gradlew publish --console=plain
~~~

nếu chỉ có một repository. Nhưng khi build thật thêm nhiều publishing repositories, `publish` là aggregate task có thể publish vào nhiều nơi. Vì vậy staging/CI nên chọn explicit task để tránh vô tình publish production.

### 7.1. Kiểm tra files tại repository

Từ `producer/`:

~~~bash
find ../repository/dev/example/greeting-lib \
  -maxdepth 3 -type f -print

cat ../repository/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.pom

cat ../repository/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.module

jar tf ../repository/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.jar
~~~

PowerShell tương đương:

~~~powershell
Get-ChildItem ..\repository\dev\example\greeting-lib -Recurse -File

Get-Content ..\repository\dev\example\greeting-lib\1.0.0\greeting-lib-1.0.0.pom

Get-Content ..\repository\dev\example\greeting-lib\1.0.0\greeting-lib-1.0.0.module

jar tf ..\repository\dev\example\greeting-lib\1.0.0\greeting-lib-1.0.0.jar
~~~

File repository đã xuất bản mới là nguồn quan trọng để đánh giá publication. Không chỉ đọc POM trung gian dưới `build/publications` rồi kết luận remote/local repository đã có metadata đúng.

## 8. Đọc Maven POM sau publish

Kiểm tra file:

~~~text
repository/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.pom
~~~

Những thứ cần xác minh:

1. `<groupId>dev.example</groupId>`.
2. `<artifactId>greeting-lib</artifactId>`.
3. `<version>1.0.0</version>`.
4. Dependency `org.apache.commons:commons-lang3:3.14.0`.
5. Commons Lang có Maven `<scope>runtime</scope>` bởi producer khai báo `implementation`.
6. Không có JUnit test libraries trong production runtime dependencies.
7. Những POM fields bắt buộc bởi publishing repository (SCM, license, developers, description) đầy đủ nếu cần.
8. Có metadata redirection marker khi Gradle sinh `.module` và POM theo convention.

**Trích đoạn POM minh họa**:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>greeting-lib</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
</project>
~~~

Đây **không phải POM hoàn chỉnh** để thay file do Gradle sinh: POM thật có thể có XML namespace, `pom.name`, `description`, comments và các trường khác.

### 8.1. Vì sao Commons Lang nằm ở runtime scope?

Public API là:

~~~java
public static String message(String name)
~~~

Consumer compiler chỉ cần biết `Greeting` và `String`, nhưng method body của Greeting dùng `StringUtils` khi chạy. Java Library plugin biết `implementation` là implementation detail; thông tin này được phản ánh trong Gradle runtime variant và Maven POM runtime scope.

Nếu public method nhận/trả type của một external library, ví dụ `Pair<String,String>`, dependency tương ứng có thể phải được khai báo `api` để consumer compile nhận được type đó. Khi sửa API, phải publish **version mới** và thử consumer compile lại.

### 8.2. POM không tự kiểm chứng JAR

POM đúng group/version/dependencies nhưng primary JAR thiếu `Greeting.class` vẫn là publication hỏng. Vì thế sau POM còn phải đọc JAR và chạy consumer compile/test/runtime.

## 9. Đọc Gradle Module Metadata `.module`

Mở:

~~~text
repository/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.module
~~~

File JSON có `component` và `variants`. Trích đoạn cấu trúc:

~~~json
{
  "formatVersion": "1.1",
  "component": {
    "group": "dev.example",
    "module": "greeting-lib",
    "version": "1.0.0"
  },
  "variants": [
    {
      "name": "apiElements",
      "attributes": {
        "org.gradle.usage": "java-api"
      }
    },
    {
      "name": "runtimeElements",
      "attributes": {
        "org.gradle.usage": "java-runtime"
      },
      "dependencies": [
        {
          "group": "org.apache.commons",
          "module": "commons-lang3",
          "version": {
            "requires": "3.14.0"
          }
        }
      ]
    }
  ]
}
~~~

Đây chỉ là sơ đồ giản lược để đọc hiểu, **không phải metadata JSON đầy đủ để ghi đè vào repository**. Gradle sinh thêm `files`/URLs/hashes, capabilities, category, libraryelements, JVM target, sources/javadoc variants và các fields khác tùy plugin/Gradle version.

Checklist:

- `component` trùng POM: `dev.example:greeting-lib:1.0.0`.
- `apiElements` có Java API attributes, được compileClasspath chọn.
- `runtimeElements` có Java runtime attributes, truyền Commons Lang đúng.
- `org.gradle.jvm.version` phản ánh Java 17.
- `files` cho biết JAR được variant publish, không trỏ sai classifier.
- Additional variants/constraints/capabilities phù hợp nếu dự án có cấu hình nâng cao.

### 9.1. API variant và runtime variant

`apiElements` có thể **không chứa Commons Lang** vì producer dùng `implementation`, trong khi `runtimeElements` chứa nó. Đây chính là điều consumer sẽ kiểm tra qua hai configurations.

Không sửa `.module` bằng tay để đổi runtime deps hoặc JVM target. Source-of-truth là producer dependency declarations và publishing component model; metadata cần được Gradle sinh lại từ source rồi phát hành một version mới.

### 9.2. No matching variant

Nếu Gradle báo `No matching variant of dev.example:greeting-lib:1.0.0 was found`, các nguyên nhân có thể là consumer yêu cầu Java target/version khác, usage attributes không khớp hoặc producer thiếu variant. Đọc message Gradle về requested vs available variants, so `outgoingVariants` với **published `.module`**.

Không chỉnh `org.gradle.jvm.version` từ 17 thành 11 chỉ để consumer Java 11 resolve được: binary thật vẫn target Java 17 và có thể gây `UnsupportedClassVersionError`.

## 10. Consumer: project độc lập tải Maven module

**consumer/settings.gradle.kts**

~~~kotlin
rootProject.name = "consumer"
~~~

**consumer/build.gradle.kts**

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
}

repositories {
    maven {
        url = uri("../repository")
        content {
            includeGroup("dev.example")
        }
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
    // Dependency tới publication, không phải local source project.
    implementation("dev.example:greeting-lib:1.0.0")

    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

application {
    mainClass.set("client.Main")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Những điểm quan trọng:

- `maven { url=uri("../repository") }` trỏ đúng Maven repository đã publish.
- `content.includeGroup("dev.example")` chỉ cho repo đó phục vụ group test; Commons Lang/JUnit sẽ đến từ Maven Central.
- `implementation("dev.example:greeting-lib:1.0.0")` kiểm thử module coordinates.
- Consumer **không khai báo Commons Lang trực tiếp**: đó là phép thử cho dependency bắc cầu.
- Consumer Java toolchain 17 tương thích với producer.
- `application` tạo task `run`, còn `tasks.test` dùng JUnit Platform.

### 10.1. Java app của consumer

**consumer/src/main/java/client/Main.java**

~~~java
package client;

import dev.example.greeting.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message("gradle"));
    }
}
~~~

### 10.2. JUnit contract test

**consumer/src/test/java/client/PublishedLibraryTest.java**

~~~java
package client;

import dev.example.greeting.Greeting;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PublishedLibraryTest {

    @Test
    void canRunPublishedLibrary() {
        assertEquals(
            "Xin chào, Gradle!",
            Greeting.message("gradle")
        );
    }
}
~~~

### 10.3. Chạy consumer

Linux/macOS, từ `consumer/`:

~~~bash
./gradlew clean test run --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean test run --console=plain
~~~

**Stdout chính xác từ `client.Main`:**

~~~text
Xin chào, Gradle!
~~~

JUnit có một test method, kỳ vọng pass. Gradle sẽ có thêm task logs tùy phiên bản, console mode và cache; không có một đoạn `BUILD SUCCESSFUL` hoặc dòng thông báo JUnit cố định giữa mọi máy.

Consumer compile có thể pass nếu primary JAR chứa Greeting. Consumer test/runtime còn gọi `StringUtils`, giúp xác minh Commons Lang được truyền qua metadata.

## 11. Kiểm tra dependency graph từ consumer

Trong `consumer/`:

~~~bash
./gradlew dependencies \
  --configuration compileClasspath \
  --console=plain

./gradlew dependencies \
  --configuration runtimeClasspath \
  --console=plain
~~~

### 11.1. Kỳ vọng compileClasspath

~~~text
compileClasspath
\--- dev.example:greeting-lib:1.0.0
~~~

Đây là trích đoạn minh họa. Commons Lang **không cần** nằm trong compileClasspath của consumer do dependency chỉ là `implementation` ở producer và public signature không lộ type từ Commons Lang.

### 11.2. Kỳ vọng runtimeClasspath

~~~text
runtimeClasspath
\--- dev.example:greeting-lib:1.0.0
     \--- org.apache.commons:commons-lang3:3.14.0
~~~

Nếu version được nâng bởi constraints/conflict resolution khác của consumer, version actual có thể khác; điều cần xác minh là Commons Lang được kéo vào runtime graph **từ published metadata**.

### 11.3. dependencyInsight

~~~bash
./gradlew dependencyInsight \
  --dependency greeting-lib \
  --configuration runtimeClasspath \
  --console=plain

./gradlew dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  --console=plain
~~~

`dependencyInsight` hiển thị selected module, version/selection reasons và đường dependency. Đây là nguồn để điều tra transitive dependency bị thiếu hoặc version khác dự kiến.

Đừng nhìn `build.gradle.kts` của producer rồi khẳng định consumer sẽ chọn cùng version trong mọi circumstances. BOM/platform, constraints, metadata rules và locks của consumer có thể tham gia resolution.

## 12. Kiểm tra binary artifact bằng JDK tools

Tại `producer/` sau publish:

~~~bash
jar tf ../repository/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.jar
~~~

Trong listing phải có:

~~~text
dev/example/greeting/Greeting.class
~~~

Để kiểm tra public API:

~~~bash
javap \
  -classpath ../repository/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.jar \
  dev.example.greeting.Greeting
~~~

Dòng method expected trong output:

~~~text
public static java.lang.String message(java.lang.String);
~~~

Đoạn trên là **dòng cần quan sát**, không phải toàn bộ stdout của `javap`, vì các dòng khác và format có thể phụ thuộc JDK.

Với class target Java 17, `javap -v` có thể hiện **major version 61**. Bytecode Java 17 không chạy trên JVM Java 11; một consumer target Java 11 có thể gặp variant mismatch hoặc class version error.

### 12.1. Sources/Javadoc JAR

~~~bash
jar tf ../repository/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0-sources.jar

jar tf ../repository/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0-javadoc.jar
~~~

Trong sources JAR kỳ vọng có `dev/example/greeting/Greeting.java`. Javadoc JAR chứa HTML/API pages nếu Javadoc task hoàn thành. Không nhầm `sources.jar` và `javadoc.jar` với binary JAR thực thi.

### 12.2. Maven POM không tự chứng minh JAR đúng

POM có đúng metadata nhưng JAR thiếu `Greeting.class` vẫn là publication hỏng. Cần kiểm tra **files thực tế** cùng với các contract tests ở consumer.

## 13. Ba thử nghiệm âm để chứng minh consumer đang dùng publication

Thực hiện trong một bản sao lab; sau thử phải khôi phục consumer dependency.

### 13.1. Đổi artifactId sai

Thay dependency thành:

~~~kotlin
implementation("dev.example:producer:1.0.0")
~~~

Nếu file repository chỉ có `greeting-lib`, Gradle không tìm thấy module. Điều này cho thấy project name và Maven artifactId không phải lúc nào cũng giống nhau.

### 13.2. Đổi version chưa publish

~~~kotlin
implementation("dev.example:greeting-lib:1.0.1")
~~~

Nếu repository chỉ có `1.0.0`, consumer không resolve được. Nó chứng minh không có một project dependency ngầm cung cấp classes bất kể tọa độ.

### 13.3. Thêm binary JAR như file dependency

Trong một fixture độc lập:

~~~kotlin
dependencies {
    implementation(
        files("../repository/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.jar")
    )
}
~~~

File dependency trực tiếp không tự đọc POM/`.module` để biết Commons Lang là transitive runtime dependency. Nếu không có Commons Lang từ nguồn khác, compile consumer vẫn có thể pass nhưng run có thể fail với:

~~~text
java.lang.NoClassDefFoundError:
  org/apache/commons/lang3/StringUtils
~~~

Đây là symptom **nếu metadata bắc cầu không có**, không phải stdout expected của bài lab hoàn chỉnh. Nó giải thích vì sao chỉ kiểm tra JAR chưa đủ.

## 14. Maven local, cache và version bất biến

`publishToMavenLocal` có thể hữu ích cho thử nghiệm thủ công:

~~~bash
./gradlew publishToMavenLocal
~~~

Consumer lúc ấy dùng:

~~~kotlin
repositories {
    mavenLocal()
    mavenCentral()
}
~~~

Đây là **cấu hình thay thế** cho file repo bài lab, không cần dùng đồng thời cả hai. Maven local thường ở `~/.m2/repository` và có thể lưu artifact cùng tọa độ từ lần thử trước.

Những hiểu nhầm cần tránh:

- `publish` **không tự thực hiện** `publishToMavenLocal`; chúng là các tasks khác nhau.
- `--refresh-dependencies` có thể giúp chẩn đoán một số tình huống cache, nhưng **không phải chiến lược release versioning**.
- Overwrite cùng release `1.0.0` bằng bytes khác làm consumers/caches có kết quả khác nhau.
- Trong CI, dùng version candidate riêng và repository staging sạch.
- Khi test pass, promote **cùng bytes** vào release repository; nếu rebuild lại sau test thì cần re-verify.

Không đẩy Maven local cache của developer lên CI hoặc dùng nó làm nguồn duy nhất chứng minh release mới đã được publish.

## 15. Version, scope và Gradle metadata là hợp đồng public API

Giả sử một library có:

~~~kotlin
dependencies {
    api("org.example:public-types:1.0")
    implementation("org.example:internal-tool:2.0")
}
~~~

Đây là các tọa độ **giả định để giải thích**, không phải dependencies cần thêm vào lab.

`public-types` được lộ qua API nên consumer compile cần nó; POM thường map compile scope. `internal-tool` chỉ phục vụ method body nên consumer runtime cần nó, nhưng compile không cần; POM thường map runtime scope.

Nếu public method signature chứa một class của `internal-tool` mà producer vẫn khai báo `implementation`, consumer compile có thể fail vì class đó thiếu. Cách khắc phục là sửa producer thành `api`, **publish version mới**, rồi kiểm thử lại consumer. Đừng sửa từng consumer bằng cách khai báo bù dependency khi metadata contract của library sai.

### 15.1. `runtimeOnly`, `compileOnly`, `compileOnlyApi`

- `runtimeOnly`: dependency chỉ cần lúc chạy.
- `compileOnly`: dependency cần để compile producer nhưng không tự là runtime dep.
- `compileOnlyApi`: dependency cần compile public API consumer nhưng không cần runtime theo Java Library model.

Khi có dependency loại này, phải kiểm tra cả API/runtime variants và Maven POM vì mapping có giới hạn.

### 15.2. Version Mapping và BOM

Gradle Maven Publish có `versionMapping` cho trường hợp muốn ghi resolved versions vào POM thay declared versions. Nếu producer dùng dynamic selectors, BOM/platform hay strict constraints, POM có thể không phản ánh đầy đủ sự khác biệt của Gradle resolution.

Trước release:

1. Xác định version thực sự muốn downstream consumers dùng.
2. Đọc published POM và `.module`, không chỉ producer `dependencies`.
3. Chạy consumer `dependencies`/`dependencyInsight`.
4. Kiểm tra binary compatibility khi nâng transitive versions.
5. Không nghĩ rằng producer `gradle.lockfile` tự được publish như lockfile của consumer.

Version Catalog giúp khai báo versions và aliases, nhưng **không thay Maven POM hoặc Gradle Module Metadata**.

## 16. Các task của Maven Publish và khi nào dùng

| Task | Ý nghĩa |
| --- | --- |
| `generatePomFileForMavenJavaPublication` | Sinh Maven POM trung gian |
| `generateMetadataFileForMavenJavaPublication` | Sinh Gradle `.module` trung gian |
| `publishMavenJavaPublicationToLabRepository` | Gửi publication `mavenJava` đến repository `lab` |
| `publish` | Gửi tất cả publications đến tất cả repositories được cấu hình |
| `publishMavenJavaPublicationToMavenLocal` | Gửi một publication đến Maven local |
| `publishToMavenLocal` | Gửi toàn bộ Maven publications đến Maven local |
| `jar`, `sourcesJar`, `javadocJar` | Tạo các artifacts thuộc Java component |

Một task như `publishMavenJavaPublicationToLabRepository` chỉ có nếu publication và repository names tương ứng đã được tạo. Nếu đổi `create<MavenPublication>("mavenJava")` sang tên khác, tên task cũng thay đổi.

### 16.1. Không dùng --dry-run để khẳng định upload

~~~bash
./gradlew publishMavenJavaPublicationToLabRepository --dry-run
~~~

Lệnh chỉ hiển thị graph, **không thực hiện publishing actions**. Hãy chạy publish thật rồi kiểm tra Maven repo.

### 16.2. Khi có nhiều repositories

Nếu `publishing.repositories` có staging và production, `publish` có thể publish cả hai. Dùng explicit `publish...To...Repository` và CI permissions để bảo đảm chỉ release job được upload production.

## 17. Lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Không có task publish | Chưa apply `maven-publish` | Xem plugins và `tasks --all` |
| `components["java"]` không tìm thấy | Chưa có Java component | Dùng `java-library` hoặc component plugin phù hợp |
| Sai tên task publish | Publication/repo không tên `mavenJava`/`lab` | So `publishing` DSL |
| Publish xong nhưng repo không có POM | Sai URL, repo policy, task chỉ sinh metadata | Đọc repo file tree |
| Consumer không tìm thấy module | group/artifact/version sai, repo chưa có artifact | So coordinates và repository path |
| Consumer dùng artifact cũ | Maven local hoặc Gradle/proxy cache | Unique version, staging sạch |
| Consumer compile pass nhưng run lỗi | Runtime transitive dependency thiếu | Kiểm tra POM scope, `.module`, runtimeClasspath |
| POM thiếu Commons Lang | Publish JAR thủ công thay component | Dùng `from(components["java"])` |
| POM lộ JUnit test libs | Test dependency scope sai | `testImplementation`, `testRuntimeOnly` |
| `No matching variant` | Usage/JVM/category/capabilities mismatch | `.module`, `outgoingVariants`, consumer attributes |
| Java 11 gặp class version error | Producer target Java 17 | Toolchain/release và javap |
| Maven consumer fail, Gradle consumer pass | Variant semantics không đủ trong POM | Kiểm tra Maven POM và Maven fixture |
| Gradle consumer fail, Maven consumer pass | Gradle-specific metadata mismatch | `.module` variants |
| Sources/Javadoc jar không có | Chưa bật jar tasks hoặc task failed | `withSourcesJar`/`withJavadocJar` |
| 401/403 khi upload remote | Auth/permissions sai | CI credentials và URL |
| 409 Conflict | Repository không cho overwrite version | Tăng version, không overwrite |
| Run sai artifact dù classpath có module | Composite build substitution | Bỏ `includeBuild` khỏi consumer fixture |
| Test chạy mà không thấy Commons Lang | Runtime khác classpath đã suy đoán | `dependencyInsight`, actual `run` task |
| Javadoc generation fail | Doclint/JDK/source docs lỗi | Sửa source/docs, chạy Javadoc lại |
| Artifact checksum khác | Binary/cache/proxy/rebuild changed | So trusted checksums, build reproducibility |
| `publish` thành công nhưng consumer fail | POM/.module/JAR sai hoặc repository stale | Inspect actual published files và consumer graph |

### 17.1. Quy trình xử lý một failure

1. Kiểm tra producer groupId/artifactId/version.
2. Chạy `outgoingVariants`, xem API/runtime variants.
3. Kiểm tra `build/publications/mavenJava` generated outputs.
4. Kiểm tra Maven repository **sau publish** có đúng artifacts.
5. Đọc POM dependencies và `.module` attributes.
6. Chạy consumer `dependencies` hai configurations.
7. Chạy `dependencyInsight` cho module và dependency bắc cầu.
8. Chạy consumer `clean test run`.
9. Sửa nguyên nhân tại producer hoặc consumer toolchain/repo, publish version mới và re-test.

Không loại bỏ dependency, force version hoặc sửa tay POM để làm CI xanh khi chưa xác định nguồn lỗi.

## 18. Cần test Maven consumer riêng khi nào?

Một Gradle consumer có thể ưu tiên `.module`, còn Maven dùng POM. Nếu library phát hành để dùng cả hai công cụ, cần ít nhất:

- Kiểm tra published POM có Maven compile/runtime scopes đúng.
- Đảm bảo các types public API được cung cấp cho Maven compile.
- Đảm bảo runtime dependencies có mặt cho Maven.
- Nếu xuất bản feature variants/capabilities chỉ Gradle hiểu, tài liệu hóa giới hạn của Maven hoặc cung cấp artifacts phù hợp.
- Chạy một Maven consumer fixture trên tọa độ staging khi đó là requirement của sản phẩm.

Việc test Gradle consumer pass không chứng minh tự động Maven consumer pass với mọi complex variants. Ngược lại, Maven consumer pass không chứng minh Gradle variant resolution đúng.

## 19. Multi-project: kiểm tra module nào được phát hành?

Trong monorepo `:core`, `:api`, `:app`, có thể có publication riêng cho từng library. Nếu `:api` dùng `project(":core")`, Gradle sẽ xuất bản module dependency metadata theo project publication coordinates khi configured đúng.

Những câu hỏi phải kiểm tra:

1. `:core` và `:api` có cùng repo staging không?
2. Group/artifact/version của `:core` trong POM của `:api` có đúng không?
3. Đã publish `:core` trước khi consumer resolve `:api` chưa?
4. Published `.module` của `:api` có dependencies đúng trên API/runtime variants không?
5. Consumer của `:api` có vô tình dùng included project substitution không?

Không nhầm `:app:build` (có thể dùng project dependencies) với bằng chứng đã publish POMs của mọi modules. Với mỗi publishable module quan trọng, dùng published-artifact consumer smoke test tương ứng.

## 20. Security và reproducibility của publication

Xuất bản là một phần của software supply chain:

- **Pin Gradle Wrapper/JDK/toolchain**, kiểm tra nguồn binary build tool.
- Dùng HTTPS repository và credentials trong secret store; không đặt secrets trong POM `description`, `url`, SCM fields hoặc log.
- Bảo vệ release repository bằng quyền ghi và immutable version policy.
- Dùng checksums/chữ ký theo yêu cầu để đối chiếu artifact bytes/nguồn ký.
- Cân nhắc Dependency Verification của Gradle khi consume dependencies bên ngoài.
- Dùng vulnerability scanning/SBOM cho module và transitive graph.
- Không coi checksum khớp là bảo đảm API compatible hoặc không có CVE.
- Chỉ promote **cùng bytes đã test** từ staging sang release, hoặc re-verify nếu buộc rebuild.
- Lưu metadata/version/checksum/test report như release evidence.

Một `gradle.lockfile` ở producer khóa dependency selection của build đó, **không tự biến thành lockfile áp dụng cho mọi consumer**. Consumers resolve theo published metadata, repositories, platforms, constraints và lock policies của chính họ.

## 21. CI pipeline đề xuất

Một pipeline có các bước:

~~~text
Checkout producer source
          |
          v
Producer compile + unit tests
          |
          v
Generate JAR + POM + .module
          |
          v
Publish candidate tới staging repository sạch
          |
          v
Kiểm tra POM/.module/JAR/sources/Javadoc/checksums
          |
          v
Consumer độc lập resolve coordinates
          |
          +-- compileClasspath -> apiElements
          +-- runtimeClasspath -> runtimeElements
          +-- JUnit contract test
          +-- run smoke test
          |
          v
Optional Maven consumer + security checks
          |
          v
Promote chính bytes đã test
~~~

Shell script trong thư mục `publishing-lab/`:

~~~bash
set -e

cd producer
./gradlew clean build \
  publishMavenJavaPublicationToLabRepository \
  --console=plain

cd ../consumer
./gradlew clean test run --console=plain
./gradlew dependencies \
  --configuration runtimeClasspath \
  --console=plain
~~~

Đây là **CI lab local file repo**. Trong CI thật có thể cần job artifacts/staging URL thay vì dùng chung filesystem, và cần xử lý version uniqueness/credentials theo policy.

**Điều kiện PASS** không chỉ là `publish` thành công, mà còn:

1. Published POM, `.module` và JAR đều tồn tại.
2. Tọa độ module khớp consumer declaration.
3. Primary JAR có public API class/method.
4. API/runtime metadata dependencies/scopes đúng.
5. Consumer độc lập compile và test/run pass.
6. Java target tương thích.
7. Không vô tình dùng `mavenLocal`, project dependency hay composite substitution.
8. Release candidate immutable và checksums đúng theo chính sách.

## 22. Bài tập tự kiểm tra và đáp án

**Câu 1.** Project tên `producer`, MavenPublication artifactId `greeting-lib`. Consumer yêu cầu gì?

**Đáp án:** `dev.example:greeting-lib:1.0.0`, không phải `dev.example:producer:1.0.0`.

**Câu 2.** Vì sao `from(components["java"])` quan trọng?

**Đáp án:** Nó lấy Java artifacts và component dependency/variant metadata cho publication; upload một JAR rời không bảo đảm metadata bắc cầu.

**Câu 3.** Consumer compile được nhưng run fail do thiếu `StringUtils`. Phân tích gì trước?

**Đáp án:** Published POM `<scope>runtime</scope>`, `.module` runtimeElements và consumer runtimeClasspath; kiểm tra repository/cache, không vội thêm Commons Lang trực tiếp vào consumer.

**Câu 4.** Maven POM và Gradle `.module` khác nhau thế nào?

**Đáp án:** POM là mô hình Maven dependencies/scopes; `.module` mô tả Gradle variants, attributes/capabilities và rich constraints.

**Câu 5.** `publishToMavenLocal` có tự chạy khi gọi `publish` không?

**Đáp án:** Không. Chúng là aggregate tasks riêng.

**Câu 6.** Producer `implementation` dùng type chỉ trong method body; consumer compileClasspath có nhất thiết có dependency đó?

**Đáp án:** Không. Nhưng runtimeClasspath thường cần nó khi method chạy.

**Câu 7.** Consumer dùng `implementation(project(":producer"))` có chứng minh published POM đúng không?

**Đáp án:** Không. Project dependency có thể bỏ qua POM/.module của repository.

**Câu 8.** `--dry-run` của publish có upload artifact không?

**Đáp án:** Không, chỉ xem task graph.

**Câu 9.** Maven consumer pass nhưng Gradle báo No matching variant. Xem gì?

**Đáp án:** `.module` variant attributes/capabilities/JVM target và consumer requested attributes.

**Câu 10.** Có thể sửa `org.gradle.jvm.version` trong `.module` từ 17 về 11 để Java 11 dùng JAR không?

**Đáp án:** Không. Phải build binary tương thích Java 11 hoặc nâng consumer JVM.

**Câu 11.** `sources.jar` có thay primary `jar` khi chạy Java không?

**Đáp án:** Không. Sources chứa `.java`, primary JAR chứa `.class`.

**Câu 12.** `gradle.lockfile` của producer có khóa consumer không?

**Đáp án:** Không. Consumer dùng policies/metadata và lock state của chính nó.

**Câu 13.** Vì sao không overwrite release `1.0.0`?

**Đáp án:** Cache/proxy/consumers có thể giữ bytes khác nhau cùng coordinates, làm mất tính tái hiện và audit trail.

**Câu 14.** Kiểm chứng publication bằng hai công cụ khi hỗ trợ cả Gradle và Maven thế nào?

**Đáp án:** Kiểm tra POM/.module và chạy Gradle consumer; dùng thêm Maven consumer fixture để kiểm thử Maven scopes.

**Câu 15.** `jar tf` và `javap` giúp gì?

**Đáp án:** Xác minh JAR chứa class và public method/bytecode version như kỳ vọng.

**Câu 16.** Consumer test pass có chứng minh library không có lỗ hổng bảo mật không?

**Đáp án:** Không. Cần security scanning, dependency verification/signing và các quality gates khác.

## 23. Checklist triển khai thực tế

1. Định danh module bằng groupId, artifactId, version.
2. Dùng Java Library component và Maven Publish plugin đúng mục tiêu.
3. Phân loại `api`/`implementation`/`runtimeOnly` phù hợp API contract.
4. Sinh JAR, POM và Gradle Module Metadata.
5. Kiểm tra outgoingVariants và Java target.
6. Publish tới staging/file Maven repository sạch.
7. Đọc **published** POM, `.module`, JAR, checksum files.
8. Kiểm tra Maven scopes và Gradle variant dependencies.
9. Kiểm tra sources/Javadoc nếu policy yêu cầu.
10. Consumer độc lập chỉ dùng repository + module coordinates.
11. Consumer compileClasspath và runtimeClasspath đúng.
12. Consumer JUnit test và smoke run pass.
13. Test Maven consumer nếu cần hỗ trợ Maven ecosystem.
14. Không bypass bằng composite substitution/Maven local cache cũ.
15. Không overwrite release version, dùng candidate version riêng.
16. Bảo vệ credentials, repository permissions và signing.
17. Lưu report/checksum/evidence của release.
18. Promote đúng bytes đã kiểm thử.

**Ghi nhớ:**

~~~text
PRODUCER Java Component
        |
        +-- apiElements
        +-- runtimeElements
        |
        v
MavenPublication from(components["java"])
        |
        v
Maven Repository
  JAR + POM + Gradle .module + sources/Javadoc
        |
        v
CONSUMER độc lập
  implementation("dev.example:greeting-lib:1.0.0")
        |
        +-- Compile bằng API variant
        +-- Runtime có transitive implementation deps
        +-- JUnit contract test và smoke run
        |
        v
PASS -> Release gate / Promotion
FAIL -> Sửa producer metadata, tăng version, test lại
~~~

## 24. Tài liệu chính thức

1. Gradle — Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
2. Gradle — Publishing Setup: https://docs.gradle.org/current/userguide/publishing_setup.html
3. Gradle — Publishing Overview: https://docs.gradle.org/current/userguide/publishing_overview.html
4. Gradle — Gradle Module Metadata: https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html
5. Gradle — Java Library Plugin: https://docs.gradle.org/current/userguide/java_library_plugin.html
6. Gradle — Dependency Configurations: https://docs.gradle.org/current/userguide/dependency_configurations.html
7. Gradle — Variant-Aware Resolution: https://docs.gradle.org/current/userguide/variant_aware_resolution.html
8. Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
9. Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
10. Gradle — MavenPublication API: https://docs.gradle.org/current/javadoc/org/gradle/api/publish/maven/MavenPublication.html
11. Apache Maven — POM Reference: https://maven.apache.org/pom.html
12. Apache Maven — Repository Layout: https://maven.apache.org/repositories/layout.html

**Lưu ý:** Các trang `current` phản ánh tài liệu Gradle hiện hành; khi áp dụng cho dự án thật, kiểm tra Gradle Wrapper và JDK cụ thể. XML POM và JSON `.module` rút gọn trong bài chỉ minh họa cách đọc, không thay output Gradle sinh. Điều được kiểm chứng phải là **publication đã có trong repository và được consumer dùng thật**.