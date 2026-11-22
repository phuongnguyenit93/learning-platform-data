# Maven Publish plugin và mô hình publication, component, repository trong Gradle

Một project Java tạo được `build/libs/my-library.jar` bằng `./gradlew jar` chưa có nghĩa rằng project khác đã có thể khai báo `implementation("com.example:my-library:1.0.0")`. Để một thư viện được tải theo tọa độ Maven, cần xuất bản **artifact, metadata và danh tính module** tới một **Maven-compatible repository**. Gradle cung cấp plugin `maven-publish` cho quy trình này.

Bài học thuộc phần **Xuất bản artifact** của *Build Tool Gradle*. Các trọng tâm: `SoftwareComponent`, `MavenPublication`, `MavenArtifactRepository`, generated publishing tasks, Maven POM, Gradle Module Metadata, Java API/runtime dependencies và cách consumer sử dụng artifact. Ví dụ thực hành xây một thư viện **Java 17 + Gradle Kotlin DSL**, publish vào repository dạng thư mục rồi dùng **Gradle consumer độc lập** tải artifact bằng GAV. Cuối bài là cách publish lên Maven Local, remote repository, snapshot/release, signing, CI và chẩn đoán lỗi.

## 1. Ba khái niệm nền tảng

| Khái niệm | Đối tượng Gradle | Câu hỏi trả lời |
| --- | --- | --- |
| Component | `SoftwareComponent` | **Thứ gì** do project tạo, gồm artifacts và variants/dependencies nào? |
| Publication | `MavenPublication` | Bản phát hành Maven có **tọa độ GAV, artifacts và metadata** gì? |
| Repository | `MavenArtifactRepository` | **Upload** publication tới đâu? |

Sơ đồ:

~~~text
src/main/java
    |
    v
Java library component: components["java"]
    | Java API/runtime variants + artifacts + dependencies
    |
    v
MavenPublication "mavenJava"
    | groupId:artifactId:version
    | JAR, POM, Gradle .module, sources/Javadoc
    |
    v
publishing.repositories.maven("file/remote URL")
    |
    v
Maven repository
    |
    v
Consumer repositories + implementation("group:artifact:version")
~~~

**Component không phải một thư mục JAR**, publication không phải tên repository, và repository để **publish** không phải repository để **tải source dependencies**.

## 2. Build JAR chưa phải publish Maven module

`java-library` plugin tạo các task Java như `compileJava`, `jar` và `build`:

~~~kotlin
plugins {
    id("java-library")
}
~~~

Lệnh:

~~~bash
./gradlew jar
~~~

tạo JAR trong `build/libs/`, nhưng không tạo đầy đủ quyền/khả năng resolve GAV trên registry. Một Maven consumer còn cần:

- `groupId`, `artifactId`, `version`.
- Cấu trúc repository `group/path/artifact/version/`.
- Maven POM chứa identity và external dependencies.
- Gradle Module Metadata nếu dùng variant-aware resolution.
- Sources/Javadoc artifacts nếu publisher cần.
- Một đích upload thực sự có thể được consumer truy cập.

Thêm plugin:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}
~~~

`maven-publish` tạo hạ tầng `publishing` nhưng bạn vẫn phải xác định publication/component và destination repository để một `publish` tới registry có ý nghĩa.

## 3. Maven coordinates GAV

Một dependency có dạng:

~~~text
groupId:artifactId:version

com.example.learning:greeting-lib:1.0.0
~~~

MavenPublication mặc định lấy thông tin:

| Publication | Nguồn |
| --- | --- |
| `groupId` | `project.group` |
| `artifactId` | `project.name` |
| `version` | `project.version` |

Ví dụ:

~~~kotlin
group = "com.example.learning"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

Nếu project tên `greeting-lib`, GAV mặc định là `com.example.learning:greeting-lib:1.0.0`. Tên `mavenJava` là tên **Gradle publication**, không phải Maven artifactId.

Có thể override:

~~~kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            groupId = "com.example.learning"
            artifactId = "greeting-api"
            version = "2.0.0"
            from(components["java"])
        }
    }
}
~~~

Đây là **mảnh cấu hình** cần Java component và repository để publish. Gradle project path, artifactId, Java package và JPMS module name là các định danh khác nhau; không suy ra chúng phải trùng.

## 4. `components["java"]` thực sự mang thông tin gì?

Với Java Library plugin:

~~~text
SoftwareComponent "java"
  |
  +-- apiElements
  |     usage = java-api
  |     main JAR + API dependencies
  |
  +-- runtimeElements
        usage = java-runtime
        main JAR + runtime dependencies
~~~

Mỗi variant có attributes và dependencies thích hợp. Consumer compiler thường cần API variant; consumer runtime cần runtime variant.

Một publication đúng với Java library thường dùng:

~~~kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

Lời gọi `from(components["java"])` đưa **artifacts và dependency metadata** từ Java component vào publication. Nó đặc biệt quan trọng khi thư viện có `api` và `implementation` dependencies.

Không dùng cách chỉ gắn JAR rồi tưởng metadata tự đủ:

~~~kotlin
publishing {
    publications {
        create<MavenPublication>("rawJar") {
            artifact(tasks.named("jar"))
        }
    }
}
~~~

Mảnh này có thể upload một JAR nếu kết hợp với repository, nhưng **không tự công bố Java component variants/dependencies** như `from(components["java"])`. Với một library tiêu chuẩn, nên dùng component, không chỉ một file archive.

## 5. Publication không chỉ là một JAR

Một MavenPublication thông thường có:

- Tên Gradle publication (ví dụ `mavenJava`).
- GAV, POM name/description/license/SCM/developers.
- Component hoặc custom artifacts.
- Main JAR.
- Sources/Javadoc JARs nếu đã bật.
- Maven POM và Gradle Module Metadata.

Cùng một publication có thể sinh:

~~~text
greeting-lib-1.0.0.jar
greeting-lib-1.0.0-sources.jar
greeting-lib-1.0.0-javadoc.jar
greeting-lib-1.0.0.pom
greeting-lib-1.0.0.module
~~~

**Không cần tạo một MavenPublication cho từng JAR**. Các artifacts bổ sung thường có cùng GAV và dùng classifier/extension để phân biệt.

Một MavenPublication chỉ nên lấy một SoftwareComponent bằng `from(...)`; khi cần nhiều hình thái sản phẩm riêng, thiết kế nhiều publications/variants thích hợp thay vì cố trộn các component không tương thích.

## 6. `publishing.repositories` khác `repositories`

Ví dụ:

~~~kotlin
repositories {
    mavenCentral()
}
~~~

là nơi **tải** external dependencies cho build. Còn:

~~~kotlin
publishing {
    repositories {
        maven {
            name = "demoFileRepo"
            url = uri(layout.buildDirectory.dir("repo"))
        }
    }
}
~~~

là nơi **upload** Maven publications.

| Block | Mục đích |
| --- | --- |
| Project `repositories` | Resolve `implementation`, `testImplementation`... |
| Settings `dependencyResolutionManagement.repositories` | Quản lý dependency-resolution repositories tập trung |
| Settings `pluginManagement.repositories` | Tìm Gradle plugins |
| `buildscript.repositories` | Tải thư viện cho buildscript classpath |
| `publishing.repositories` | Publish bản phát hành tới Maven-compatible repository |

**`repositories { mavenCentral() }` không tự publish tới Maven Central.** Consumer cũng không tự biết producer `publishing.repositories`: consumer phải khai báo repo phù hợp trong chính build của nó.

Repository name `demoFileRepo` góp phần tạo tên publishing task, không phải Maven GAV.

## 7. Ví dụ runnable: Java 17 library → Maven file repository → consumer

Bài tập sử dụng **hai Gradle builds tách biệt** trong một thư mục, không cần network upload hay credential registry. Producer tạo library và publish vào `build/repo`; consumer phụ thuộc artifact qua GAV thay vì project dependency.

### 7.1. Cây thư mục

~~~text
greeting-publish-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── src/main/java/demo/library/GreetingService.java
└── consumer-demo/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/java/demo/consumer/Main.java
~~~

`consumer-demo` có `settings.gradle.kts` riêng và **không được include** ở root settings; đó là một build độc lập. Nếu thay bằng `project(":consumer")` và project dependency, bạn không thực sự kiểm thử Maven publishing.

Bạn cần Gradle Wrapper hợp lệ, toolchain Java 17 tương thích với Gradle đang dùng. Có thể tạo Wrapper qua Gradle installation phù hợp khi cần; không tự viết file `gradle-wrapper.jar` bằng tay.

### 7.2. Producer `settings.gradle.kts`

~~~kotlin
rootProject.name = "greeting-lib"
~~~

### 7.3. Producer `build.gradle.kts` — đầy đủ

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

group = "com.example.learning"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }

    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])

            pom {
                name.set("Greeting Library")
                description.set(
                    "Java 17 library used to demonstrate Maven publishing"
                )
            }
        }
    }

    repositories {
        maven {
            name = "demoFileRepo"
            url = uri(layout.buildDirectory.dir("repo"))
        }
    }
}
~~~

Ý nghĩa:

1. `java-library` tạo Java component.
2. `maven-publish` thêm `publishing` extension.
3. `group`, project name, `version` tạo GAV.
4. `withSourcesJar()` và `withJavadocJar()` tạo source/docs artifacts.
5. `MavenPublication("mavenJava")` mô tả Maven module.
6. `from(components["java"])` lấy Java JAR, variants và dependencies.
7. `pom` thêm metadata đọc được trong POM.
8. Repository `demoFileRepo` có URL là folder `build/repo`.

Đây là **producer file hoàn chỉnh**. Không khai báo `repositories { mavenCentral() }` vì library demo không dùng external dependencies. Repository nhận publish dạng file nên không đòi credentials.

### 7.4. Java source của producer

`src/main/java/demo/library/GreetingService.java`:

~~~java
package demo.library;

/** A small public API for a published library. */
public final class GreetingService {

    /** Returns a greeting for the supplied name. */
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Method công khai, không sử dụng third-party libraries. Javadoc giúp task `javadoc` có nội dung.

### 7.5. Build và publish

Từ producer root, Linux/macOS:

~~~bash
./gradlew clean build publish --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean build publish --console=plain
~~~

Các bước:

- `clean` xóa output cũ (gồm `build/repo` nếu tồn tại).
- `build` compile Java và chạy lifecycle checks; demo không có test source nên test có thể `NO-SOURCE`.
- `publish` chạy publishing tasks phù hợp để tạo POM/module metadata, JARs và ghi vào `demoFileRepo`.
- Không có remote network upload; file Maven repository nằm trong project `build/repo`.

**Không chạy `clean` riêng giữa bước publish và consumer run**: nó sẽ xóa file repo mà consumer cần đọc.

### 7.6. Thư mục sau publish

Một cấu trúc dự kiến:

~~~text
build/
├── libs/
│   ├── greeting-lib-1.0.0.jar
│   ├── greeting-lib-1.0.0-sources.jar
│   └── greeting-lib-1.0.0-javadoc.jar
├── publications/
│   └── mavenJava/
│       └── pom-default.xml
└── repo/
    └── com/example/learning/greeting-lib/1.0.0/
        ├── greeting-lib-1.0.0.jar
        ├── greeting-lib-1.0.0.pom
        ├── greeting-lib-1.0.0.module
        ├── greeting-lib-1.0.0-sources.jar
        ├── greeting-lib-1.0.0-javadoc.jar
        └── ... checksums hoặc metadata khác
~~~

**Cây trên minh họa dạng output**, không phải bản in kiểm kê một lần build thật. Maven GAV được ánh xạ vào path:

~~~text
com.example.learning -> com/example/learning
greeting-lib         -> greeting-lib
1.0.0                -> 1.0.0

=> com/example/learning/greeting-lib/1.0.0/
~~~

Đặt JAR trực tiếp ở `build/repo/greeting-lib.jar` sẽ không tương đương việc publish theo Maven layout + metadata.

### 7.7. Consumer settings

`consumer-demo/settings.gradle.kts`:

~~~kotlin
rootProject.name = "greeting-consumer"
~~~

### 7.8. Consumer build script

`consumer-demo/build.gradle.kts`:

~~~kotlin
plugins {
    application
}

repositories {
    maven {
        url = uri("../build/repo")
    }
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation("com.example.learning:greeting-lib:1.0.0")
}

application {
    mainClass.set("demo.consumer.Main")
}
~~~

`../build/repo` là đường dẫn tương đối từ thư mục consumer tới file repo ở producer. Nếu thay đổi cây folder, phải điều chỉnh repository URL. Không cần `maven-publish` trong consumer.

### 7.9. Consumer Java source

`consumer-demo/src/main/java/demo/consumer/Main.java`:

~~~java
package demo.consumer;

import demo.library.GreetingService;

public final class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Gradle"));
    }
}
~~~

### 7.10. Chạy consumer sau publish

Từ **producer root**:

~~~bash
./gradlew -p consumer-demo run --quiet
~~~

PowerShell:

~~~powershell
.\gradlew.bat -p consumer-demo run --quiet
~~~

**Stdout do Java `Main.main` in ra**, chính xác:

~~~text
Hello, Gradle!
~~~

Đây là bằng chứng consumer dùng artifact thông qua Maven GAV. Gradle có thể thêm logs/warnings theo môi trường, nhưng câu trên là output Java được thiết kế.

Kiểm tra dependency graph của consumer:

~~~bash
./gradlew -p consumer-demo dependencies --configuration compileClasspath
./gradlew -p consumer-demo dependencyInsight --configuration runtimeClasspath --dependency greeting-lib
~~~

Cần thấy `com.example.learning:greeting-lib:1.0.0` được chọn. Nếu không, kiểm tra GAV, file repo path và publishing task trước khi sửa Java source.

## 8. Generated Maven publishing tasks

Với publication `mavenJava` và publishing repository `demoFileRepo`:

| Task | Vai trò |
| --- | --- |
| `generatePomFileForMavenJavaPublication` | Tạo Maven POM |
| `generateMetadataFileForMavenJavaPublication` | Tạo Gradle Module Metadata |
| `publishMavenJavaPublicationToDemoFileRepoRepository` | Publish đúng một publication tới một repo |
| `publish` | Aggregate, publish mọi publication tới mọi configured publishing repo |
| `publishMavenJavaPublicationToMavenLocal` | Publish publication này vào Maven Local |
| `publishToMavenLocal` | Aggregate Maven Local của mọi publication |

Xem tasks thật:

~~~bash
./gradlew tasks --all
~~~

Chỉ sinh POM:

~~~bash
./gradlew generatePomFileForMavenJavaPublication
~~~

Chỉ publish một cặp publication/repo:

~~~bash
./gradlew publishMavenJavaPublicationToDemoFileRepoRepository
~~~

**`publish` không mặc định ghi vào Maven Local.** Đó là task `publishToMavenLocal` riêng. Nếu có nhiều remote repositories gồm staging và production, **không gọi aggregate `publish`** khi chỉ muốn upload một nơi; chọn đúng per-repo task.

## 9. Maven POM và Gradle Module Metadata

Khi xuất bản Java component, bạn thường thấy:

~~~text
greeting-lib-1.0.0.pom
greeting-lib-1.0.0.module
~~~

**POM** là XML metadata dành cho Maven-compatible consumers, gồm GAV, dependencies và mô tả. **Gradle Module Metadata (`.module`)** hỗ trợ đầy đủ hơn:

- `java-api`/`java-runtime` variants.
- Attributes như Java version, usage, library elements.
- Variant-specific dependencies/constraints.
- Rich versions và component capabilities.
- Feature variants nếu library cung cấp.

POM không biểu diễn hết variant/capability concepts của Gradle. Gradle publish `.module` **cùng** POM để hỗ trợ Maven clients và Gradle clients. Gradle có thể đưa marker comment trong POM báo có metadata phong phú hơn.

Trích đoạn POM **minh họa**, không phải bản XML đầy đủ có namespace:

~~~xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.learning</groupId>
  <artifactId>greeting-lib</artifactId>
  <version>1.0.0</version>
  <name>Greeting Library</name>
</project>
~~~

Xem POM **thật** từ `build/publications/mavenJava/pom-default.xml` hoặc `build/repo/.../greeting-lib-1.0.0.pom`. Không chỉnh generated POM bằng tay; chỉnh `publishing.publications...pom` trong Gradle DSL.

## 10. Java `api` và `implementation` trở thành published dependencies

Ví dụ một thư viện sử dụng Gson trong **public API** và Commons Lang trong **implementation**:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

repositories {
    mavenCentral()
}

dependencies {
    api("com.google.code.gson:gson:2.13.1")
    implementation("org.apache.commons:commons-lang3:3.17.0")
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

Đây là **mảnh minh họa dependency metadata**, không phải build file đầy đủ của demo có file repo.

| Gradle producer scope | Consumer compile API | Consumer runtime | Maven POM thường ánh xạ |
| --- | --- | --- | --- |
| `api` | Có | Có | `compile` |
| `implementation` | Không tự lộ qua API variant | Có | `runtime` |
| `runtimeOnly` | Không | Có | `runtime` |
| `compileOnly` | Chỉ cho producer compiler | Không tự publish như runtime dependency | Không mặc định là main dependency |
| `compileOnlyApi` | Compile-only public contract | Không tự đưa vào runtime | Có giới hạn khi biểu diễn bằng Maven POM |

Nếu library public method trả một kiểu Gson, Gson cần được công bố cho consumer compiler. Commons Lang chỉ được gọi trong method body thì không nên tự đưa vào public API.

`from(components["java"])` mới làm việc này đáng tin vì nó mang metadata của Java component. Chỉ upload JAR bằng `artifact(...)` không cung cấp cùng hợp đồng.

## 11. Sources và Javadoc

Trong Java extension:

~~~kotlin
java {
    withSourcesJar()
    withJavadocJar()
}
~~~

Gradle tạo sources/Javadoc artifacts cho Java component:

~~~text
greeting-lib-1.0.0.jar
greeting-lib-1.0.0-sources.jar
greeting-lib-1.0.0-javadoc.jar
~~~

Main JAR là bytecode; sources JAR dùng cho IDE/debug; Javadoc JAR chứa HTML tài liệu API. Hai file bổ sung không tự là runtime dependencies.

Không cần viết custom Jar task cho source/doc nếu Java component đã hỗ trợ. Việc vừa bật `withSourcesJar` vừa thêm custom sources JAR cùng classifier có thể tạo duplicate artifact validation failure.

Xem output:

~~~bash
./gradlew jar sourcesJar javadocJar
~~~

Một public library nên cung cấp đầy đủ metadata và sources theo yêu cầu của consumer/registry, nhưng vẫn cần tránh gây lỗi Javadoc build vì tài liệu/source không hợp lệ.

## 12. Tùy biến POM một cách có cấu trúc

Ví dụ mở rộng publication (mảnh minh họa cho project có Maven Publish plugin và Java component):

~~~kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])

            pom {
                name.set("Greeting Library")
                description.set("Reusable Java library for greeting examples")

                licenses {
                    license {
                        name.set("Apache License, Version 2.0")
                        url.set("https://www.apache.org/licenses/LICENSE-2.0")
                    }
                }

                developers {
                    developer {
                        id.set("java-team")
                        name.set("Java Team")
                    }
                }
            }
        }
    }
}
~~~

Đây là **cú pháp minh họa**. Với sản phẩm thật, khai báo license/developer/SCM/project URL theo dữ liệu thực; không tự nhận giấy phép không thuộc dự án.

Maven Central và nhiều registries có thể yêu cầu một số POM fields, signatures hoặc namespace ownership. Nếu phải sửa POM, **sửa Gradle `pom { ... }`**, không sửa output XML do Gradle sinh.

## 13. Declared versions và resolved versions với `versionMapping`

Nếu producer dùng dynamic dependency version hoặc dependency locking, phiên bản **được khai báo** và phiên bản **được resolve/kiểm thử** có thể khác nhau. Gradle Maven Publish cung cấp `versionMapping` để sử dụng resolved versions trong metadata khi cần:

~~~kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])

            versionMapping {
                usage("java-api") {
                    fromResolutionOf("runtimeClasspath")
                }
                usage("java-runtime") {
                    fromResolutionResult()
                }
            }
        }
    }
}
~~~

Đây là **mảnh cấu hình**, cần Java component và dependencies phù hợp. Nó có ý nghĩa khi bạn muốn một public release phản ánh versions đã được kiểm thử, đặc biệt với dynamic selectors hoặc dependency locking.

Tuy vậy, version resolution của producer không phải lúc nào cũng là contract tốt nhất cho mọi consumer. Cần xem public ABI, Maven POM mapping và transitive compatibility trước khi áp dụng. Version Catalog quản lý aliases khai báo trong producer; consumer không cần tải file TOML của producer để resolve published GAV.

## 14. Nhiều publications và repositories

Một project có thể khai báo nhiều publications, ví dụ Java library chính và artifact phụ khác danh tính Maven. Một publication cũng có thể publish tới nhiều repositories.

Khi có hai publishing repositories:

~~~kotlin
publishing {
    repositories {
        maven {
            name = "preview"
            url = uri(layout.buildDirectory.dir("preview-repo"))
        }
        maven {
            name = "staging"
            url = uri(layout.buildDirectory.dir("staging-repo"))
        }
    }
}
~~~

Gradle tạo per-repository tasks như:

~~~text
publishMavenJavaPublicationToPreviewRepository
publishMavenJavaPublicationToStagingRepository
~~~

`publish` yêu cầu cả hai đích. Với **2 publications × 3 repos**, có thể có 6 task pairs. Hãy thiết kế CI sao cho staging không vô tình upload vào production.

**Không tạo nhiều publications chỉ vì main/sources/Javadoc files.** Một publication có thể mang nhiều artifacts bằng classifiers. Nếu một project thật sự sản xuất Maven BOM khác Java library, đó mới là trường hợp cần component/publication riêng.

## 15. Publish vào Maven Local

Chỉ cần publication hợp lệ:

~~~bash
./gradlew publishToMavenLocal
~~~

Gradle ghi module vào local Maven repository, thường:

~~~text
~/.m2/repository/
~~~

Consumer:

~~~kotlin
repositories {
    mavenLocal()
}
~~~

Hai thao tác khác nhau: `publishToMavenLocal` là **ghi**; `mavenLocal()` trong consumer là **tải**. Maven Local không phải shared production registry, thường không có checksums giống file-backed Maven repo, và có thể lưu artifact cũ gây sai lệch so với CI.

Không tự thêm `mavenLocal()` vào mọi project để che một publishing error; nó có thể khiến consumer chọn bản local chưa được phát hành.

## 16. Remote Maven repository với credentials

Khi upload Nexus/Artifactory/GitHub Packages hoặc Maven server nội bộ, dùng HTTPS và credentials thích hợp:

~~~kotlin
publishing {
    repositories {
        maven {
            name = "internalRelease"
            url = uri(providers.gradleProperty("publishRepositoryUrl").get())
            credentials(PasswordCredentials::class)
        }
    }
}
~~~

**Mảnh trên cần Gradle property `publishRepositoryUrl` là endpoint thật**, cùng credentials do CI cung cấp. Theo repository name `internalRelease`, Gradle có thể tự nhận các properties:

~~~text
internalReleaseUsername
internalReleasePassword
~~~

Có thể truyền bằng môi trường CI:

~~~text
ORG_GRADLE_PROJECT_publishRepositoryUrl
ORG_GRADLE_PROJECT_internalReleaseUsername
ORG_GRADLE_PROJECT_internalReleasePassword
~~~

Đây là **tên biến môi trường**, không phải mật khẩu. Không hard-code secrets vào buildscript/Git/logs. Một số registries cần token trong HTTP header hoặc phương thức xác thực riêng, phải theo tài liệu của provider.

Không tắt TLS verification hoặc cho phép HTTP không an toàn chỉ để việc publish “đỡ lỗi”; sửa URL/certificates/network policy đúng cách.

## 17. Snapshots, releases và Maven Central

Một quy ước version:

~~~text
1.3.0-SNAPSHOT  -> bản thay đổi/thử nghiệm
1.3.0           -> release
~~~

Repositories có thể khác nhau cho snapshots/releases, với retention và quyền overwrite riêng. Release repos thường cấm overwrite GAV đã phát hành; lỗi `409 Conflict` có thể là dấu hiệu version đã tồn tại.

Đối với Maven Central, **đừng giả định một URL OSSRH cũ có thể nhận `maven-publish` mặc định**. Theo tài liệu Gradle, từ **30/06/2025**, Maven Central không còn hỗ trợ legacy deployment protocol/OSSRH upload workflow cũ. Public Central release cần plugin/workflow phù hợp **Central Portal hiện đại**, kèm namespace ownership, POM metadata và signing policy.

`maven-publish` vẫn là công cụ cốt lõi cho Maven-compatible repositories và publication model. Nhưng **Maven format** và **dịch vụ upload/phê duyệt của registry** là hai tầng khác nhau.

## 18. Signing, checksum và supply-chain safety

Một repository public có thể yêu cầu ký artifacts. Gradle có core `signing` plugin:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
    id("signing")
}

// Publication "mavenJava" phải được tạo trước.

signing {
    sign(publishing.publications["mavenJava"])
}
~~~

Đây là **mảnh bổ sung** chứ không phải phần bắt buộc của demo. Khi áp dụng signing, cần cấu hình khóa và passphrase an toàn; đừng đưa private key plaintext vào source repo.

| Đầu ra | Mục đích |
| --- | --- |
| `*.jar` | Binary library |
| `*.pom` | Maven metadata |
| `*.module` | Gradle variant metadata |
| `*-sources.jar` | Source attachment |
| `*-javadoc.jar` | Documentation attachment |
| `*.sha256`/`*.sha512` | Checksums kiểm tra bytes |
| Signature artifacts | Xác nhận publisher/content theo trust model |

Checksum không chứng minh publisher identity nếu attacker thay được **cả JAR và checksum**. Signing/verification và repository access controls bổ sung những lớp bảo vệ khác nhau. `publishToMavenLocal` thường không tạo checksum files trong local Maven repository giống file-backed publishing.

## 19. CI/CD: kiểm tra trước khi upload thật

Một chuỗi cục bộ có thể dùng:

~~~bash
./gradlew clean build
./gradlew generatePomFileForMavenJavaPublication
./gradlew generateMetadataFileForMavenJavaPublication
./gradlew publishMavenJavaPublicationToDemoFileRepoRepository
./gradlew -p consumer-demo run
~~~

Bốn bước cần hiểu:

1. **Build/test**: producer code thực sự compile và pass checks.
2. **Inspect metadata**: POM, Gradle Module Metadata, variants.
3. **Staging/file publish**: biết artifact GAV/layout đúng.
4. **Consumer smoke test**: dự án khác tải đúng module và chạy.

Production release cần thêm approved tag/version, CI secret management, signing, immutable artifact policy và đúng registry endpoint.

Lệnh:

~~~bash
./gradlew publish --dry-run
~~~

chỉ cho biết **tasks dự kiến**; không chạy upload actions nên **không chứng minh credentials/TLS/permissions của registry hoạt động**.

## 20. Chẩn đoán lỗi có hệ thống

| Triệu chứng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Unresolved reference: publishing` | Chưa áp dụng `maven-publish` | Thêm plugin vào project tương ứng |
| `SoftwareComponent with name 'java' not found` | Thiếu `java`/`java-library` hoặc cấu hình sai project | Áp dụng plugin tạo component |
| Có `build/libs/*.jar` nhưng `publish` không làm gì | Thiếu publication/repository | Kiểm tra `publishing` |
| Consumer thiếu transitive dependencies | Chỉ publish JAR thay vì Java component | Dùng `from(components["java"])` |
| `Could not find group:artifact:version` | GAV sai, file repo URL sai, chưa publish | So POM/Maven repository path |
| POM không có license/SCM | Chưa cấu hình metadata | Sửa `pom { ... }` DSL |
| Không có `*-sources.jar` | Chưa bật `withSourcesJar()` | Bật Java sources variant |
| `Javadoc` fail lúc publish | Source doc lỗi hoặc task configuration sai | Sửa Javadoc diagnostics |
| `401 Unauthorized` | Credentials/token không đúng | Kiểm tra CI secrets/auth scheme |
| `403 Forbidden` | Không có quyền namespace/repo | Kiểm tra publish permissions |
| `404 Not Found` | Endpoint sai hoặc auth server che giấu lỗi | Xác minh URL/provider docs |
| `409 Conflict` | Version đã tồn tại, repo cấm overwrite | Tăng version/tuân thủ release policy |
| SSL handshake fail | Truststore/cert/proxy | Sửa TLS, không bỏ xác minh |
| `No matching variant` | JVM version/attributes/capabilities không phù hợp | Kiểm tra `.module` và consumer environment |
| `publish` upload nhiều đích | Aggregate theo publication × repo | Gọi task đích cụ thể |
| `publish` không thấy Maven Local | Maven Local có task riêng | `publishToMavenLocal` |
| Consumer dùng bản local cũ | `mavenLocal()`/cache ưu tiên | Kiểm tra selected artifact/repo order |
| Maven Central từ chối upload cũ | Central Portal đổi workflow | Dùng plugin/workflow mới |
| `clean` xóa file repository demo | Repo nằm trong `build/repo` | Publish lại trước consumer |
| Duplicate artifact classifier | Custom source/doc JAR trùng | Bỏ artifact trùng |
| Generated POM sửa tay không bền | Gradle tái sinh POM | Sửa `pom` trên publication |

### Lệnh điều tra producer

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew components
./gradlew outgoingVariants
./gradlew generatePomFileForMavenJavaPublication
./gradlew generateMetadataFileForMavenJavaPublication
./gradlew publishMavenJavaPublicationToDemoFileRepoRepository --info
~~~

`components` và `outgoingVariants` cho biết SoftwareComponent và variants hiện có ở project. `tasks --all` liệt kê các task publishing đúng tên. Nếu task upload cần secrets, không công khai raw logs chưa được kiểm tra.

Kiểm tra JAR (với JDK tools):

~~~bash
jar tf build/libs/greeting-lib-1.0.0.jar
~~~

Kỳ vọng có:

~~~text
demo/library/GreetingService.class
~~~

Đây là một entry kỳ vọng trong JAR, không phải output duy nhất của lệnh `jar tf`.

### Lệnh điều tra consumer

~~~bash
./gradlew -p consumer-demo dependencies --configuration compileClasspath
./gradlew -p consumer-demo dependencyInsight --configuration runtimeClasspath --dependency greeting-lib
~~~

Phải phân biệt **repository không có artifact**, **metadata có nhưng variant không match**, **Java source compile fail** và **runtime binary incompatibility**. Chúng không cùng một nguyên nhân và không thể sửa bằng cách xóa cache vô điều kiện.

## 21. Tự kiểm tra

**Câu 1.** `SoftwareComponent` và `MavenPublication` khác nhau thế nào?

**Đáp:** Component mô tả sản phẩm/variants/dependencies; publication định danh và đóng gói những nội dung đó thành một Maven module.

**Câu 2.** `create<MavenPublication>("mavenJava")` có làm Maven artifactId thành `mavenJava` không?

**Đáp:** Không. `mavenJava` là tên publication trong Gradle; artifactId mặc định từ project name hoặc override.

**Câu 3.** `repositories { mavenCentral() }` có upload artifact lên Central không?

**Đáp:** Không. Nó là repository để tải dependencies; publish được cấu hình qua `publishing.repositories`.

**Câu 4.** Vì sao không nên chỉ `artifact(tasks.named("jar"))` khi publish Java library?

**Đáp:** Vì thiếu Java component dependency/variant model; consumer có thể không nhận transitive dependencies đúng.

**Câu 5.** Muốn xuất bản vào Maven Local dùng gì?

**Đáp:** `./gradlew publishToMavenLocal`. Task `publish` không tự làm việc đó.

**Câu 6.** `withSourcesJar()` và `withJavadocJar()` có cần thêm một MavenPublication mỗi cái không?

**Đáp:** Không. Chúng thường thành supplementary artifacts trong cùng Java publication.

**Câu 7.** `api` và `implementation` trong Java library thường map thành Maven scopes nào?

**Đáp:** `api` thường thành `compile`, `implementation` thành `runtime`, bên cạnh Gradle Module Metadata chi tiết hơn.

**Câu 8.** Maven POM có lưu mọi Gradle capabilities/variants không?

**Đáp:** Không. `.module` mô tả đầy đủ hơn các Gradle-specific concepts.

**Câu 9.** Một project có 2 publications và 3 publishing repositories. Aggregate `publish` có thể phát hành tới bao nhiêu cặp?

**Đáp:** Tối đa 6 cặp publication-repository được cấu hình hợp lệ.

**Câu 10.** Trong demo, vì sao không chạy `clean` sau publish trước khi consumer?

**Đáp:** Vì repository demo nằm ở `build/repo`; `clean` sẽ xóa nó.

**Câu 11.** Tại sao `publish --dry-run` không đảm bảo HTTPS credentials đúng?

**Đáp:** Dry-run không thực thi upload hay xác thực server thực tế.

**Câu 12.** Tại sao Maven Central không nên dùng một OSSRH URL cũ?

**Đáp:** Central Portal đã thay đổi deployment workflow; cần plugin/flow tương thích hiện hành và đáp ứng yêu cầu signing/metadata.

## 22. Checklist trước release

- [ ] Plugin `java-library` và `maven-publish` được áp dụng đúng project.
- [ ] Publication có GAV đúng, ổn định và hợp lệ.
- [ ] Dùng `from(components["java"])` cho Java library.
- [ ] Không nhầm repository tải dependency với repository nhận publish.
- [ ] Main JAR, source/Javadoc artifacts đầy đủ và không bị trùng.
- [ ] POM metadata, dependencies và Gradle Module Metadata đã được review.
- [ ] `api`/`implementation` đúng theo public ABI.
- [ ] Toolchain/JVM variant target phù hợp consumers.
- [ ] Build/test của producer đã PASS.
- [ ] Consumer build độc lập tải đúng GAV từ repository đích.
- [ ] CI publish task chỉ ghi vào môi trường được phê duyệt.
- [ ] Credentials/signing keys lưu an toàn, không commit secrets.
- [ ] Snapshot/release/version policy rõ ràng, không overwrite release tùy tiện.
- [ ] Maven Central workflow phù hợp Central Portal hiện hành.
- [ ] Có kiểm tra repository errors 401/403/404/409 và TLS.
- [ ] Không chỉnh generated POM hoặc metadata để che lỗi DSL.

## Tài liệu chính thức

- [Gradle — The Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publications, repositories, tasks, POM, version mapping, Maven Local và Maven Central.
- [Gradle — Publishing a Project as a Module](https://docs.gradle.org/current/userguide/publishing_setup.html): what/where/how và artifact metadata.
- [Gradle — Customizing Publishing](https://docs.gradle.org/current/userguide/publishing_customization.html): custom artifacts, multiple publications/repos.
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html): variants, capabilities, constraints và mapping Maven POM.
- [Gradle — Supported Repository Protocols](https://docs.gradle.org/current/userguide/supported_repository_protocols.html): HTTPS, auth schemes và Gradle credentials.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`/`implementation` và Java component.
- [Gradle — MavenPublication API](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.publish.maven/-maven-publication/index.html): `from`, `artifact`, GAV và POM.
- [Gradle — Signing Plugin](https://docs.gradle.org/current/userguide/signing_plugin.html): artifact signing.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): consumer dependency reports.
