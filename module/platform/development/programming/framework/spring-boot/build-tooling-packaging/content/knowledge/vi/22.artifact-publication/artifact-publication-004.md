# Xuất bản artifact bằng Gradle maven-publish và MavenPublication

## Mục tiêu

Một Java library có thể build thành công trên máy developer nhưng module khác chưa chắc dùng được nếu artifact chưa được **định danh, đóng gói và đưa vào repository**. Gradle cung cấp plugin `maven-publish` cùng kiểu `MavenPublication` để mô tả artifact, Maven coordinates, POM metadata và repository nhận file.

Quy trình xuất bản trả lời ba câu hỏi:

1. **Publish cái gì?** Java component, executable Spring Boot JAR, sources JAR hoặc artifact tùy chỉnh.
2. **Publish ở đâu?** Maven Local, file-based repository để thử nghiệm, hoặc remote repository như Nexus/Artifactory/GitHub Packages.
3. **Publish bằng task nào?** Gradle sinh task từ tên publication và repository.

Sau bài này, bạn có thể:

- Phân biệt `maven-publish`, `publishing`, `MavenPublication` và Maven repository.
- Tạo publication từ `components.java` để publish Java library kèm dependency metadata.
- Tùy chỉnh `groupId`, `artifactId`, `version` và POM.
- Thêm artifact do task tạo bằng `artifact(tasks.named(...))`.
- Publish Spring Boot executable JAR bằng `bootJar`.
- Đọc task `generatePomFileFor...`, `publish...To...Repository` và `publishToMavenLocal`.
- Kiểm tra repository layout, POM, Gradle Module Metadata và thử resolve artifact từ consumer project.
- Cấu hình remote credentials, snapshot/release và CI mà không hardcode secrets.
- Chẩn đoán sai GAV, thiếu dependencies, sai classifier, publish nhầm JAR hoặc repository từ chối upload.

**Bối cảnh thực hành:** Java 17+, Gradle 8.x tương thích, Groovy DSL và Kotlin DSL. Ví dụ library dùng `java-library`; ví dụ application dùng Spring Boot plugin **3.3.13**. URL remote bên dưới chỉ là địa chỉ mẫu, không phải endpoint để upload thật.

---

## 1. Maven repository và tọa độ GAV

### 1.1 GAV định danh một module

Một Maven artifact thường được nhận diện bằng:

- `groupId`: nhóm/tổ chức, ví dụ `com.example.libs`.
- `artifactId`: tên module, ví dụ `greeting-library`.
- `version`: phiên bản, ví dụ `1.2.0` hoặc `1.3.0-SNAPSHOT`.

Ba thành phần này gọi là **GAV**:

```text
com.example.libs:greeting-library:1.2.0
```

Repository Maven dùng GAV để tổ chức thư mục và tên file:

```text
repository-root/
└── com/
    └── example/
        └── libs/
            └── greeting-library/
                └── 1.2.0/
                    ├── greeting-library-1.2.0.jar
                    ├── greeting-library-1.2.0.pom
                    ├── greeting-library-1.2.0.module
                    └── greeting-library-1.2.0-sources.jar
```

Đây là cấu trúc minh họa. Gradle có thể publish thêm `.module`, checksum và signature tùy cấu hình. Maven chủ yếu dùng POM; Gradle có thể dùng Gradle Module Metadata để hiểu variants phong phú hơn.

### 1.2 Repository tải dependency và repository upload

Trong Gradle:

```groovy
repositories {
    mavenCentral()
}
```

khai báo nơi project **tải dependencies để build**.

Còn:

```groovy
publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri('https://repo.example.com/repository/releases/')
        }
    }
}
```

khai báo nơi Gradle **upload publication**. Hai block có vai trò khác nhau. Khai báo Maven Central trong `repositories` không tự publish artifact; khai báo repository trong `publishing.repositories` cũng không làm nó trở thành nguồn dependency của project.

### 1.3 Các loại repository

| Loại | Vị trí | Mục đích |
| --- | --- | --- |
| Maven Local | `~/.m2/repository` hoặc `%USERPROFILE%\.m2\repository` | Thử nghiệm trên máy hiện tại |
| File repository | Ví dụ `build/repo` | Test publish/resolve mà không cần server |
| Remote repository | Nexus, Artifactory, GitHub Packages, repository nội bộ | Chia sẻ cho team và CI |

`mavenLocal()` trong block `repositories` giúp consumer resolve từ Maven Local. Nó không phải cấu hình upload. Gradle có task riêng `publishToMavenLocal` và không cần thêm Maven Local vào `publishing.repositories`.

Maven Central có quy trình phát hành công khai riêng về namespace, xác thực, signing và portal. Không coi một URL Maven bất kỳ là endpoint Central hợp lệ.

---

## 2. Maven Publish Plugin và MavenPublication

### 2.1 Áp dụng plugin

`build.gradle`:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}
```

`maven-publish` là plugin lõi Gradle, không cần version riêng. Plugin đăng ký extension `publishing` với hai nhóm cấu hình:

- `publications`: các publication có tên, mô tả artifact và metadata.
- `repositories`: các repository đích, có tên và URL.

`MavenPublication` là đối tượng mô tả cách một module được phát hành theo Maven format. Nó không phải file POM và cũng không phải repository.

### 2.2 Publication lấy artifact từ component hoặc task

Java library thường dùng:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
```

Spring Boot executable archive có thể dùng:

```groovy
publishing {
    publications {
        bootApp(MavenPublication) {
            artifact tasks.named('bootJar')
        }
    }
}
```

`from components.java` publish Java software component cùng dependency/variant metadata. `artifact(tasks.named('bootJar'))` thêm đúng archive được tạo bởi task `bootJar`. Chọn theo cách consumer sử dụng artifact.

### 2.3 Tên publication khác artifactId

Trong:

```groovy
publications {
    mavenJava(MavenPublication) {
        from components.java
    }
}
```

`mavenJava` là tên publication của Gradle, được dùng trong tên task và đường dẫn POM. Nó không bắt buộc trùng với Maven `artifactId`.

Mặc định Gradle ánh xạ:

| Maven field | Gradle project property |
| --- | --- |
| `groupId` | `project.group` |
| `artifactId` | `project.name` |
| `version` | `project.version` |

Có thể override:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            groupId = 'com.example.platform'
            artifactId = 'shared-utils'
            version = '2.4.0'
            from components.java
        }
    }
}
```

Nếu `rootProject.name` là `greeting-library`, `group` là `com.example.libs` và `version` là `1.2.0`, GAV mặc định là `com.example.libs:greeting-library:1.2.0`. Luôn kiểm tra POM được tạo trước khi upload.

---

## 3. Java library thực hành hoàn chỉnh

### 3.1 Cấu trúc

```text
greeting-library/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/com/example/greeting/GreetingService.java
    └── test/java/com/example/greeting/GreetingServiceTest.java
```

Project cần Gradle Wrapper hợp lệ và JDK 17 hoặc toolchain provisioning tương ứng.

### 3.2 `settings.gradle`

```groovy
rootProject.name = 'greeting-library'
```

Tên project là nguồn mặc định cho Maven `artifactId`.

### 3.3 Java library class

File `src/main/java/com/example/greeting/GreetingService.java`:

```java
package com.example.greeting;

import org.apache.commons.lang3.StringUtils;

public final class GreetingService {

    public String greet(String name) {
        String normalized = StringUtils.trimToNull(name);

        if (normalized == null) {
            throw new IllegalArgumentException("name must not be blank");
        }

        return "Hello, " + normalized + "!";
    }
}
```

`StringUtils` chỉ được dùng nội bộ; public API chỉ nhận và trả về `String`. Vì consumer không cần kiểu Commons Lang để compile lời gọi, dependency này phù hợp với `implementation`.

### 3.4 Unit test

File `src/test/java/com/example/greeting/GreetingServiceTest.java`:

```java
package com.example.greeting;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {

    private final GreetingService service = new GreetingService();

    @Test
    void greetsTrimmedName() {
        assertEquals("Hello, Linh!", service.greet("  Linh  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.greet("   ")
        );
    }
}
```

Test kiểm tra hành vi bình thường và input không hợp lệ. JUnit là dependency test, không phải dependency production của library.

### 3.5 `build.gradle` đầy đủ

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.libs'
version = '1.2.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

tasks.named('test') {
    useJUnitPlatform()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            pom {
                name = 'Greeting Library'
                description = 'A small reusable Java greeting library.'
                url = 'https://example.com/projects/greeting-library'

                licenses {
                    license {
                        name = 'The Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
                        distribution = 'repo'
                    }
                }

                developers {
                    developer {
                        id = 'platform-team'
                        name = 'Platform Team'
                    }
                }

                scm {
                    connection = 'scm:git:https://example.com/team/greeting-library.git'
                    developerConnection = 'scm:git:ssh://git@example.com/team/greeting-library.git'
                    url = 'https://example.com/team/greeting-library'
                }
            }
        }
    }

    repositories {
        maven {
            name = 'localTestRepo'
            url = layout.buildDirectory.dir('repo')
        }
    }
}
```

Đây là build script đầy đủ cho project lab. URL POM chỉ là metadata mẫu, hãy thay bằng thông tin dự án thật khi phát hành. Repository `build/repo` là file-based local repository, chưa phải remote production repository.

### 3.6 Vì sao dùng `java-library`?

`java-library` cung cấp Java component với ranh giới API:

- `api`: dependency xuất hiện trong public API và cần có trên compile classpath của consumer.
- `implementation`: dependency triển khai nội bộ; consumer không cần nó để compile public API.
- `compileOnly`: cần khi compile producer nhưng không được publish như runtime dependency thông thường.
- `testImplementation`: chỉ phục vụ test, không được đưa thành dependency production.

Trong ví dụ, `commons-lang3` là `implementation` nên POM thường ánh xạ nó thành Maven runtime scope. Nếu public method dùng type Commons Lang mà consumer cần thấy lúc compile, hãy xem xét `api`.

`from components.java` giúp Gradle lấy artifact và dependency/variant metadata từ Java component. Chỉ upload file JAR rời sẽ không tự tạo dependency contract tương đương.

### 3.7 Sources JAR

`withSourcesJar()` đăng ký task tạo source JAR và thêm source variant vào Java component. Khi publication dùng `from components.java`, source artifact được publish theo metadata của component.

Tên file thường có classifier `sources`:

```text
greeting-library-1.2.0-sources.jar
```

IDE có thể dùng file này để hiển thị source khi debug. Nó không thay binary JAR và không phải dependency runtime.

---

## 4. Build, sinh POM và publish vào file repository

### 4.1 Chạy verification trước

```bash
./gradlew clean check
```

Windows PowerShell:

```powershell
.\gradlew.bat clean check
```

`check` chạy verification lifecycle, trong đó có test. Publishing task không mặc định thay verification; hãy chạy test/check trước khi phát hành.

### 4.2 Sinh POM để kiểm tra

```bash
./gradlew generatePomFileForMavenJavaPublication
```

POM mặc định được tạo tại:

```text
build/publications/mavenJava/pom-default.xml
```

Kiểm tra GAV, name/description/license/SCM, dependency scope và bảo đảm JUnit không xuất hiện như dependency production. POM đã sinh chưa có nghĩa artifact đã upload.

### 4.3 Publish vào file repository

```bash
./gradlew publishMavenJavaPublicationToLocalTestRepoRepository
```

Tên task được tạo từ publication `mavenJava` và repository `localTestRepo`. Sau khi publish thành công, repository dự kiến có:

```text
build/repo/
└── com/example/libs/greeting-library/1.2.0/
    ├── greeting-library-1.2.0.jar
    ├── greeting-library-1.2.0.pom
    ├── greeting-library-1.2.0.module
    └── greeting-library-1.2.0-sources.jar
```

Checksum hoặc metadata bổ sung có thể xuất hiện tùy Gradle/repository. Kiểm tra file thực tế thay vì coi danh sách minh họa là cố định.

### 4.4 Task aggregate

`./gradlew publish` là task tổng hợp cho các publication tới những remote/file Maven repositories được khai báo trong `publishing.repositories`. Nếu có nhiều publication và nhiều repository, task có thể upload nhiều tổ hợp.

`publish` **không bao gồm `publishToMavenLocal`**. Để publish Maven Local, dùng task riêng.

### 4.5 Xem task

```bash
./gradlew tasks --all
./gradlew tasks --group publishing
```

Một số task thường gặp:

| Task | Tác dụng |
| --- | --- |
| `generatePomFileForMavenJavaPublication` | Sinh POM cho publication `mavenJava` |
| `publishMavenJavaPublicationToLocalTestRepoRepository` | Upload vào `localTestRepo` |
| `publishMavenJavaPublicationToMavenLocal` | Publish một publication vào Maven Local |
| `publish` | Publish tới các repository đích được khai báo |
| `publishToMavenLocal` | Publish mọi publication vào Maven Local |

Tên task phụ thuộc tên publication/repository. Đổi `mavenJava` thành `releaseLibrary` thì task name cũng đổi.

---

## 5. Maven Local và consumer project

### 5.1 Publish Maven Local

```bash
./gradlew publishToMavenLocal
```

Maven Local thường nằm tại `~/.m2/repository` trên Linux/macOS hoặc `%USERPROFILE%\.m2\repository` trên Windows.

Đây là repository/cache cá nhân, tiện để thử nghiệm trên một máy. Nó không phải server dùng chung cho team hoặc CI. Artifact cũ còn trong Maven Local có thể khiến consumer resolve nhầm phiên bản đã publish trước đó.

### 5.2 Consumer Gradle

Tạo project `greeting-consumer` với `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenLocal()
    mavenCentral()
}

dependencies {
    implementation 'com.example.libs:greeting-library:1.2.0'
}

application {
    mainClass = 'com.example.consumer.ConsumerApplication'
}
```

File `src/main/java/com/example/consumer/ConsumerApplication.java`:

```java
package com.example.consumer;

import com.example.greeting.GreetingService;

public class ConsumerApplication {

    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Linh"));
    }
}
```

Chạy `./gradlew run`. Stdout chính xác theo mã mẫu:

```text
Hello, Linh!
```

Consumer compile và gọi được library theo GAV. Dependency runtime `commons-lang3` cũng phải được resolve từ metadata publication.

### 5.3 Consumer dùng file repository

Thay Maven Local bằng:

```groovy
repositories {
    maven {
        url = uri('../greeting-library/build/repo')
    }
    mavenCentral()
}
```

URL phải trỏ tới **repository root**, không trỏ thẳng vào thư mục version. Gradle tự tìm artifact theo Maven layout.

### 5.4 Consumer Maven

Nếu đã publish Maven Local, Maven consumer khai báo:

```xml
<dependency>
    <groupId>com.example.libs</groupId>
    <artifactId>greeting-library</artifactId>
    <version>1.2.0</version>
</dependency>
```

Maven resolve từ local repository trước khi dùng remote repositories theo cấu hình. Nếu artifact nằm trong file/remote repository riêng, consumer phải khai báo repository phù hợp trong POM hoặc Maven settings.

### 5.5 Vì sao cần consumer test?

Chỉ thấy file JAR trong repository không chứng minh module dùng được. Consumer test phát hiện GAV/repository sai, thiếu dependency runtime, artifact thiếu class, POM scope sai, sources JAR có nhưng binary sai hoặc resolve nhầm version cũ.

Với release quan trọng, dùng consumer project sạch thay vì chỉ dựa vào IDE cache của producer.

---

## 6. POM và dependency metadata

### 6.1 POM là hợp đồng Maven

POM publication thường chứa GAV, packaging, dependencies/scopes, name, description, URL, license, developers và SCM.

Trích đoạn:

```xml
<groupId>com.example.libs</groupId>
<artifactId>greeting-library</artifactId>
<version>1.2.0</version>
<packaging>jar</packaging>
<name>Greeting Library</name>
<description>A small reusable Java greeting library.</description>
```

POM thật còn có modelVersion, namespace và dependency metadata do Gradle sinh.

### 6.2 `api` và `implementation`

Ví dụ:

```groovy
dependencies {
    api 'org.example:public-contract:1.0.0'
    implementation 'org.example:internal-helper:2.0.0'
    compileOnly 'org.example:provided-at-compile:1.0.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}
```

`api` là dependency nằm trong public contract, cần trên compile classpath consumer. `implementation` là dependency nội bộ, thường được ánh xạ thành Maven runtime scope. `compileOnly` chỉ cần lúc compile producer; `testImplementation` chỉ dành cho test.

Gradle có thể publish thêm `.module` để consumer Gradle hiểu API/runtime variants. Đừng sửa scope bằng `pom.withXml` tùy tiện khi Java component đã mô tả đúng dependency.

### 6.3 `versionMapping`

Khi cần ghi version dependency đã resolve vào POM:

```groovy
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
```

Đây là cấu hình nâng cao. Chọn resolution configuration theo dependency model. Dynamic/changing dependencies có thể khiến metadata thay đổi theo kết quả resolve; chỉ bật khi chính sách version cần điều đó.

### 6.4 Hạn chế sửa XML trực tiếp

Gradle có `pom.withXml` để thao tác XML trực tiếp, nhưng nên ưu tiên DSL typed như `pom.name`, `pom.description`, `pom.licenses`, `pom.developers` và `pom.scm`. Chỉ dùng XML patch khi metadata đặc biệt không có API tương ứng.

---

## 7. Artifact tùy chỉnh và sources JAR

### 7.1 Tạo sources JAR thủ công

Nếu không dùng `withSourcesJar()`:

```groovy
tasks.register('customSourcesJar', Jar) {
    archiveClassifier = 'sources'
    from sourceSets.main.allJava
}
```

Thêm vào publication:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifact tasks.named('customSourcesJar')
        }
    }
}
```

Không khai báo cả `withSourcesJar()` lẫn custom sources JAR cùng classifier nếu không có chủ đích; publication có thể bị trùng extension/classifier.

### 7.2 Dùng TaskProvider

`artifact(tasks.named('customSourcesJar'))` liên kết publication với task tạo artifact, giúp Gradle suy ra dependency cần thiết. Nếu truyền file path thuần, Gradle biết file cần publish nhưng task tạo file có thể không được nối đúng nếu thiếu `builtBy` hoặc dependency.

Artifact Maven được phân biệt bởi extension và classifier. Tránh publish hai JAR chính có cùng classifier rỗng trong một publication.

---

## 8. Publish Spring Boot executable JAR bằng bootJar

Spring Boot Gradle plugin tạo executable JAR qua task `bootJar`. Hướng dẫn Spring Boot chỉ rõ có thể thêm output của task này vào `MavenPublication` bằng `artifact`.

### 8.1 Cấu hình đầy đủ

`settings.gradle`:

```groovy
rootProject.name = 'orders-service'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'maven-publish'
}

group = 'com.example.apps'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

publishing {
    publications {
        bootApp(MavenPublication) {
            groupId = project.group.toString()
            artifactId = 'orders-service'
            version = project.version.toString()

            artifact tasks.named('bootJar')

            pom {
                name = 'Orders Service'
                description = 'Executable Spring Boot application for order processing.'
                url = 'https://example.com/apps/orders-service'
            }
        }
    }

    repositories {
        maven {
            name = 'localBootRepo'
            url = layout.buildDirectory.dir('boot-repo')
        }
    }
}
```

### 8.2 Build và publish

```bash
./gradlew clean check
./gradlew publishBootAppPublicationToLocalBootRepoRepository
```

Artifact dự kiến:

```text
build/boot-repo/com/example/apps/orders-service/1.0.0/
├── orders-service-1.0.0.jar
└── orders-service-1.0.0.pom
```

POM được tạo tại `build/publications/bootApp/pom-default.xml`. Hãy kiểm tra GAV và archive thật.

### 8.3 Vì sao không dùng `from components.java` giống library?

`bootJar` là executable archive có Boot loader và runtime dependencies lồng bên trong, thường nằm dưới `BOOT-INF/lib`. Publication mẫu chỉ đưa **executable artifact** vào Maven repository để người nhận tải và chạy.

Khi publication chỉ có `artifact tasks.named('bootJar')` mà không `from components.java`, POM không tự nhận dependency graph từ Java component. Điều này có thể phù hợp vì executable JAR đã mang runtime dependencies bên trong. Người nhận tải artifact để chạy, không mặc định coi nó là Java library.

Nếu mục tiêu là để project khác compile against public Java API, hãy publish Java library component riêng bằng `from components.java`. Không dùng executable application JAR làm contract library chỉ vì cả hai đều có đuôi `.jar`.

### 8.4 Phát hành cả library và executable JAR

Nếu cần cả hai, định nghĩa publication riêng hoặc dùng classifier/artifactId riêng:

| Publication | Nội dung | Người dùng |
| --- | --- | --- |
| `library` | Java component và dependency metadata | Project khác compile/link vào code |
| `bootApp` | Output `bootJar` executable | Release pipeline hoặc operator tải và chạy |

Hai artifact cần identity rõ ràng và POM phù hợp với consumer. Nếu thêm Boot JAR làm artifact phụ của library publication, cần classifier riêng; Maven POM không biểu diễn đầy đủ mọi variant của Gradle.

---

## 9. Kotlin DSL tương đương

Nếu project dùng `build.gradle.kts`:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "com.example.libs"
version = "1.2.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
    withSourcesJar()
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

tasks.test {
    useJUnitPlatform()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])

            pom {
                name.set("Greeting Library")
                description.set("A small reusable Java greeting library.")
                url.set("https://example.com/projects/greeting-library")
            }
        }
    }

    repositories {
        maven {
            name = "localTestRepo"
            url = uri(layout.buildDirectory.dir("repo"))
        }
    }
}
```

Đối chiếu cú pháp:

| Groovy DSL | Kotlin DSL |
| --- | --- |
| `id 'maven-publish'` | `maven-publish` |
| `mavenJava(MavenPublication)` | `create<MavenPublication>("mavenJava")` |
| `from components.java` | `from(components["java"])` |
| `artifact tasks.named('bootJar')` | `artifact(tasks.named("bootJar"))` |
| `url = layout.buildDirectory.dir('repo')` | `url = uri(layout.buildDirectory.dir("repo"))` |
| `name = 'Greeting Library'` | `name.set("Greeting Library")` |

Đừng trộn Groovy closure vào `.gradle.kts`. Kiểm tra `maven-publish` đã được apply nếu IDE không resolve `MavenPublication`.

---

## 10. Remote repository và credentials

### 10.1 Khai báo repository đích

```groovy
publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri('https://repo.example.com/repository/releases/')
        }
    }
}
```

Tên `internal` là repository name trong Gradle, không phải GAV. Nó ảnh hưởng task name, ví dụ `publishMavenJavaPublicationToInternalRepository`.

URL phải là **endpoint upload** do repository manager cung cấp. URL tải dependency và URL upload có thể khác nhau.

### 10.2 Credentials từ environment

Không hardcode username/password trong `build.gradle` hoặc commit `gradle.properties` chứa secret. Có thể lấy từ CI secret store:

```groovy
publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri(providers.environmentVariable('MAVEN_REPO_URL').get())

            credentials {
                username = providers.environmentVariable('MAVEN_REPO_USER').orNull
                password = providers.environmentVariable('MAVEN_REPO_PASSWORD').orNull
            }
        }
    }
}
```

CI cần cấu hình ba biến tương ứng. Không echo giá trị, không bật debug logs làm lộ credentials và chỉ cấp quyền upload cho job phát hành cần thiết. Nếu `MAVEN_REPO_URL` thiếu, Gradle fail khi evaluate URL thay vì upload tới một đích không xác định.

### 10.3 Basic Authentication

Nếu repository yêu cầu Basic Authentication rõ ràng:

```groovy
import org.gradle.authentication.http.BasicAuthentication

publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri('https://repo.example.com/repository/releases/')
            credentials {
                username = providers.environmentVariable('MAVEN_REPO_USER').orNull
                password = providers.environmentVariable('MAVEN_REPO_PASSWORD').orNull
            }
            authentication {
                basic(BasicAuthentication)
            }
        }
    }
}
```

Chỉ bật authentication mà server thực sự hỗ trợ. Dùng HTTPS để bảo vệ credentials khi truyền qua mạng.

### 10.4 Snapshot và release

- `1.2.0-SNAPSHOT` dành cho phát triển tích hợp, có thể được cập nhật.
- `1.2.0` là release version, thường phải bất biến sau khi phát hành.

Có thể chọn URL theo version:

```groovy
def isSnapshot = version.toString().endsWith('-SNAPSHOT')

publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri(
                isSnapshot
                    ? 'https://repo.example.com/repository/snapshots/'
                    : 'https://repo.example.com/repository/releases/'
            )
        }
    }
}
```

Đây là ví dụ chọn **một đích duy nhất** cho mỗi build. Nếu cấu hình hai repository snapshot và release cùng lúc rồi gọi `publish`, Gradle có thể publish tới cả hai. Hiểu task graph và chọn đích đúng.

Repository server có thể cấm redeploy cùng release GAV. Khi phát hành code mới, tăng version thay vì ghi đè `1.2.0` đã phát hành. Snapshot metadata timestamp/build number được repository manager quản lý.

### 10.5 Publish remote là upload thật

`./gradlew publish` có thể upload artifact lên mọi repository đích đã khai báo. Trong bài lab, dùng file repository hoặc Maven Local. Chỉ chạy remote publish khi đã có quyền, đúng endpoint, đúng version và pipeline release được duyệt.

---

## 11. Task graph và tên task

Với publication `mavenJava` và repository `internal`, Gradle thường tạo:

- `generatePomFileForMavenJavaPublication`
- `publishMavenJavaPublicationToInternalRepository`
- `publishMavenJavaPublicationToMavenLocal`
- `publish`
- `publishToMavenLocal`

Task cụ thể phụ thuộc tên publication/repository.

`generatePomFileFor...` tạo POM để kiểm tra trước upload. Đường mặc định thường là:

```text
build/publications/<publicationName>/pom-default.xml
```

`publish...To...Repository` upload một publication tới một repository cụ thể. Ví dụ:

```bash
./gradlew publishMavenJavaPublicationToInternalRepository
```

`publish` là aggregate cho remote/file repositories trong `publishing.repositories`; `publishToMavenLocal` là aggregate cho Maven Local. `mavenLocal()` trong dependency resolution không tự kích hoạt publish.

Có thể dùng `--dry-run` để xem task graph:

```bash
./gradlew publish --dry-run
```

`--dry-run` không chứng minh credentials, permission, endpoint hoặc upload thành công.

---

## 12. Gradle Module Metadata và Maven POM

Gradle hỗ trợ Gradle Module Metadata để mô tả variants và dependency graph phong phú hơn Maven POM. Khi publish Java component, Gradle thường phát hành metadata Gradle cùng POM Maven.

- Maven consumer chủ yếu dùng `.pom`.
- Gradle consumer có thể dùng `.module` để hiểu variant-aware metadata.
- JAR là binary artifact chính.
- Sources/Javadoc JAR là artifacts phụ có classifier/variant.
- Checksum/signature được thêm tùy cấu hình.

POM không biểu diễn mọi variant Gradle. Khi publish sang Maven format, một số thông tin phải được ánh xạ hoặc có thể phát sinh compatibility warning. Đừng suppress warnings theo thói quen; hãy hiểu dependency/variant nào không thể biểu diễn chính xác.

Artifact thêm trực tiếp bằng `artifact(...)` có thể được publish với classifier/extension nhưng không tự tạo variant có dependency contract riêng. Với feature variants, xem Gradle custom component/variant publishing.

---

## 13. Multi-project build

Ví dụ:

```text
platform/
├── settings.gradle
├── build.gradle
├── greeting-library/
│   └── build.gradle
└── orders-service/
    └── build.gradle
```

`settings.gradle`:

```groovy
rootProject.name = 'platform'
include 'greeting-library', 'orders-service'
```

Nếu `greeting-library` là Java library, module đó áp dụng `java-library` và `maven-publish` rồi publish `components.java`. Module `orders-service` có thể phụ thuộc project library:

```groovy
dependencies {
    implementation project(':greeting-library')
}
```

Publish module library bằng task path:

```bash
./gradlew :greeting-library:publishMavenJavaPublicationToInternalRepository
```

Đừng chạy `publish` ở root mà chưa biết task bao gồm publication/repository nào của từng subproject. Mỗi module có thể có GAV và repository policy riêng. Hai subprojects không nên publish binary khác nhau vào cùng GAV.

Gradle project dependency giúp build graph nội bộ, nhưng publish lên remote repository là bước phân phối riêng. CI cần quyết định publish dependency module trước hay publish một release set có kiểm soát.

---

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `No publications configured` | Chưa khai báo `publishing.publications` | Apply `maven-publish` và tạo `MavenPublication` |
| `MavenPublication` không được nhận diện | Plugin chưa apply hoặc sai DSL | Kiểm tra `plugins`, Groovy/Kotlin syntax |
| Task publish không tồn tại | Sai publication/repository name | Chạy `tasks --all` và xem task name thực |
| POM không có dependency | Chỉ thêm `artifact(file/task)`, không `from components.java` | Với library, publish component; với app executable, POM artifact-only có thể là chủ đích |
| Consumer không resolve | Sai GAV/repository URL/version | Đọc POM, repository layout và consumer repositories |
| JAR được publish nhưng thiếu class | Chọn sai task/output | Kiểm tra JAR bằng `jar tf` |
| Spring Boot JAR lỗi main manifest | Publish plain `jar` thay vì `bootJar` | Dùng `artifact tasks.named('bootJar')` |
| Sources JAR không xuất hiện | Chưa bật `withSourcesJar()` | Cấu hình Java component |
| POM chứa dependency test | Đưa test configuration vào publication | Giữ test dependency trong `testImplementation` |
| HTTP 401 | Credentials sai hoặc auth scheme không đúng | Kiểm tra credential source/auth, không log secret |
| HTTP 403 | Tài khoản thiếu quyền hoặc policy từ chối | Kiểm tra quyền và snapshot/release endpoint |
| HTTP 404 | URL upload sai | Dùng endpoint do repository manager cấp |
| Lỗi TLS/proxy | CA, proxy hoặc network không đúng | Kiểm tra HTTPS/CA/proxy |
| Release version đã tồn tại | Repository cấm redeploy release | Tăng version, không ghi đè |
| Snapshot không cập nhật | Snapshot metadata/cache hoặc resolve nhầm repo | Kiểm tra metadata và repository order |
| Consumer thấy artifact cũ | Maven Local hoặc Gradle cache còn bản cũ | Kiểm tra repo identity/version, refresh có kiểm soát |
| `publish` upload nhiều nơi | Nhiều remote repository trong publishing | Dùng task cụ thể hoặc chọn URL theo version |
| `publish` không chạy test | Publish task không thay verification lifecycle | Chạy `check`/`build` trước publish |
| Classifier bị trùng | Hai artifacts cùng extension/classifier | Đặt classifier riêng hoặc bỏ artifact dư |
| Maven Central publish thất bại | Thiếu workflow Portal/signing phù hợp | Theo quy trình Central hiện hành |
| Dùng `uploadArchives` cũ | Ví dụ Gradle đời cũ | Dùng `maven-publish` |
| Maven Local chạy nhưng remote fail | Local không cần network/credentials | Test staging repository và quyền upload |
| Boot JAR bị dùng như library | Executable archive không phải public API component | Tách module library và application |

Quy trình điều tra:

1. Xác định mục tiêu: library binary, executable app, sources hay distribution.
2. Kiểm tra plugin và publication name.
3. Kiểm tra GAV trong generated POM.
4. Kiểm tra artifacts, extension và classifier.
5. Kiểm tra dependency scopes và metadata.
6. Xác minh URL repository và task publish cụ thể.
7. Kiểm tra credentials/permission mà không in secret.
8. Sau upload, kiểm tra repository và thử consumer project sạch.
9. Ghi version/hash để xác định artifact đã phát hành.

---

## 15. CI/CD và chính sách phát hành

### 15.1 Pipeline gợi ý

```text
Checkout source
      |
      v
Resolve Gradle Wrapper / JDK
      |
      v
./gradlew clean check
      |
      v
Generate POM + validate GAV/artifacts
      |
      v
Publish to staging repository
      |
      v
Consumer integration test
      |
      v
Approve release
      |
      v
Publish immutable release version
      |
      v
Record repository URL, GAV and checksums
```

Tách **verification** và **publishing**. Không nên để job upload release chỉ vì Gradle build script đã evaluate thành công.

### 15.2 Bảo vệ credentials

Không hardcode credentials trong build script. Dùng CI secret variables hoặc credential store. Hạn chế log command line chứa token, không upload debug logs có credentials và rotate token nếu có dấu hiệu lộ.

### 15.3 Snapshot và release policy

- Snapshot dành cho phát triển tích hợp và có thể được cập nhật.
- Release version nên bất biến; mỗi thay đổi phát hành cần version mới.
- Không dùng snapshot làm production dependency nếu hệ thống yêu cầu artifact bất biến.
- Kiểm tra retention/cleanup policy của snapshot repository.
- Đảm bảo release pipeline không vô tình publish vào snapshot endpoint và ngược lại.

### 15.4 Kiểm chứng sau upload

Sau khi publish, xác minh GAV, JAR/Sources JAR, POM dependency scopes, Gradle Module Metadata, consumer resolution và version không bị thay thế ngoài ý muốn.

Đối với release quan trọng, ghi checksum/signature theo chính sách. **HTTP 200 từ upload không tự chứng minh consumer dùng đúng artifact**; cần kiểm tra download/resolve từ phía consumer.

### 15.5 Maven publishing không phải deploy ứng dụng

`maven-publish` đưa binary/metadata vào Maven repository để công cụ khác resolve. Nó không tự triển khai Spring Boot service lên server, Kubernetes hoặc Docker registry. Deploy ứng dụng là workflow khác.

---

## 16. Thực hành tổng hợp

### A. Publish Java library

1. Tạo project `greeting-library` theo phần 3.
2. Chạy `./gradlew clean check`.
3. Chạy `generatePomFileForMavenJavaPublication` và đọc POM.
4. Chạy `publishMavenJavaPublicationToLocalTestRepoRepository`.
5. Kiểm tra GAV path và JAR/Sources JAR.
6. Tạo `greeting-consumer`, resolve từ file repo và chạy `GreetingService`.
7. Ghi stdout và giải thích vì sao consumer nhận được `commons-lang3` dù nó là `implementation`.

### B. Publish Maven Local

1. Chạy `./gradlew publishToMavenLocal`.
2. Xác minh artifact dưới `~/.m2/repository`.
3. Tạo consumer khai báo `mavenLocal()` và GAV.
4. Đổi version trên branch lab để phân biệt artifact cache cũ với artifact mới.
5. Giải thích vì sao Maven Local không phải repository dùng chung cho team.

### C. Publish Spring Boot executable JAR

1. Tạo project `orders-service` với Spring Boot Gradle plugin.
2. Cấu hình publication bằng `artifact tasks.named('bootJar')`.
3. Chạy `clean check` và publish vào file repository.
4. Kiểm tra archive có `BOOT-INF/classes` và `BOOT-INF/lib`.
5. Tải đúng artifact và chạy `java -jar` trong môi trường lab.
6. Giải thích vì sao publication app-only không giống Java library publication từ `components.java`.

### D. Kiểm tra dependency metadata

1. Thêm dependency public vào `api` và dependency nội bộ vào `implementation`.
2. Generate POM và kiểm tra Maven scope.
3. Compile consumer dùng kiểu của dependency public.
4. Chuyển dependency từ `api` sang `implementation` trên branch lab, quan sát compile behavior và sửa lại.
5. Giải thích vì sao POM/Gradle Module Metadata là một phần của contract.

### E. Mô phỏng remote repository an toàn

1. Dùng URL staging được cấp hoặc file repository.
2. Cấp credentials qua CI secret variables.
3. Chạy task cụ thể `publishMavenJavaPublicationTo...Repository`.
4. Kiểm tra repository nhận đúng GAV.
5. Chạy consumer test từ staging repository.
6. Không dùng release version đã tồn tại để thử overwrite.

### F. Chẩn đoán sai artifact

Một đồng nghiệp viết:

```groovy
publishing {
    publications {
        bootApp(MavenPublication) {
            from components.java
        }
    }
}
```

nhưng mục tiêu là phát hành **Spring Boot executable JAR**. Hãy kiểm tra artifact mà `components.java` đại diện và đối chiếu task `bootJar`. Sửa publication:

```groovy
publishing {
    publications {
        bootApp(MavenPublication) {
            artifact tasks.named('bootJar')
        }
    }
}
```

Giải thích tác động của việc bỏ `from components.java` đối với POM dependencies, và vì sao điều này có thể phù hợp với executable JAR đã đóng gói runtime dependencies.

### G. Báo cáo kết quả thật

```text
Project:
Gradle Wrapper version:
Java toolchain:
Applied plugins:
Publication name:
Publication type:
GAV:
Primary artifact task/file:
Additional artifacts/classifiers:
Generated POM path:
POM dependency scopes:
Repository name/type:
Publish task:
Publish result:
Published repository path:
Consumer tool:
Consumer dependency coordinates:
Consumer compile/run result:
Observed stdout or error:
Checksum/hash (if required):
Release/Snapshot policy:
Remaining issue:
```

Đây là mẫu điền bằng chứng thật. Không ghi "publish thành công" khi chỉ generate POM hoặc chạy `--dry-run`. Nếu chỉ publish local, ghi rõ Maven Local/file repository, không tuyên bố đã upload remote.

---

## 17. Tài liệu tham khảo chính thức

- Gradle — Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Gradle — Publishing Setup: https://docs.gradle.org/current/userguide/publishing_setup.html
- Gradle API — MavenPublication, GAV mapping, `from`, `artifact` và POM: https://docs.gradle.org/current/javadoc/org/gradle/api/publish/maven/MavenPublication.html
- Gradle — Publishing Customization: https://docs.gradle.org/current/userguide/publishing_customization.html
- Gradle — Gradle Module Metadata: https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html
- Spring Boot 3.3 — Publishing your Application với Maven-publish Plugin và `bootJar`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/publishing.html
- Spring Boot 3.3 — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Apache Maven — POM Reference và `distributionManagement`: https://maven.apache.org/pom.html
- Apache Maven Deploy Plugin: https://maven.apache.org/plugins/maven-deploy-plugin/usage.html
- Apache Maven — Deployment over HTTP(S), repository IDs và `settings.xml`: https://maven.apache.org/guides/mini/guide-deployment-transports.html

**Ghi nhớ:** `maven-publish` tạo hạ tầng publication; `MavenPublication` mô tả artifact, GAV và POM metadata; `from components.java` publish Java component cùng dependency metadata; `artifact(tasks.named('bootJar'))` publish executable Spring Boot archive được chỉ định. `publishToMavenLocal` ghi vào Maven Local, còn `publish` upload tới repository đích đã khai báo. Hãy kiểm tra **POM, artifact/classifier, repository layout và consumer thực tế** trước khi phát hành version.
