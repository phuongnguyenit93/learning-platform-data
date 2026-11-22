# Xác minh consumer hoạt động với cả source build lẫn artifact đã phát hành trong Gradle

## 1. Vì sao phải kiểm tra hai đường tiêu thụ?

Một thư viện Java do nhóm A phát triển được nhóm B sử dụng qua tọa độ Maven, ví dụ `dev.example:greeting-lib:1.0.0`. Khi hai nhóm cùng sửa code, Gradle **composite build** giúp consumer thử ngay library ở local source mà không phải publish trung gian. Điều này rất tiện, nhưng có một rủi ro quan trọng:

> **Consumer chạy tốt với source build chưa chứng minh consumer chạy tốt với artifact đã phát hành.**

Ở source mode, Gradle có thể thay dependency module bằng **project từ included build**. Ở binary mode, Gradle giải quyết **JAR, POM và Gradle Module Metadata** từ repository. Hai đường có thể khác nhau về classes, resource đóng gói, outgoing variants, API/runtime dependencies, artifact classifier, publication customizations, bytecode target và version thực tế.

Một số tình huống hay gặp:

- Consumer compile/run thành công khi `includeBuild("../producer")` nhưng thất bại khi tải published JAR: file JAR thiếu class/resource.
- Source code mới nhất đã sửa một method, nhưng artifact `1.0.0` trong repository vẫn là phiên bản cũ.
- Publication POM vô tình thiếu một transitively required dependency dù project-to-project dependency hoạt động.
- Binary JAR có bytecode Java 21 nhưng consumer production cần Java 17.
- Plugin/custom publication tạo khác artifact so với `default` project variant mà composite build dùng.
- Consumer test đang chạy local source vì dependency substitution dù developer tưởng đã kiểm bản published.
- Một dependency version được ghi `1.0.0` nhưng included source project là code `1.1.0-SNAPSHOT`: mặc định substitution dựa vào group/name, không chứng minh source đúng release tag.

**Mục tiêu:** kiểm chứng một consumer Java hoạt động ở **cả hai chế độ độc lập**, xác nhận mode thực tế được sử dụng và so sánh contract/metadata trước khi ra quyết định phát hành.

Bài thuộc nhóm **Composite build** của module **Build Tool Gradle**. Ví dụ xuyên suốt sử dụng **Java 17**, Gradle Kotlin DSL, một producer `greeting-lib`, một consumer `consumer-app` và một **Maven repository local riêng** nằm trong workspace; không cần tài khoản Maven Central.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt root build, included build, project dependency và published module dependency.
2. Giải thích Gradle dependency substitution mặc định theo `group:name`.
3. Dựng producer Java library có `java-library`, `maven-publish` và artifact `1.0.0`.
4. Tạo consumer dùng **cùng một dependency notation** trong cả source và published mode.
5. Điều khiển mode bằng `-PsourceMode=true/false` ở `settings.gradle.kts`.
6. Publish producer vào repository local và chạy consumer bằng binary dependency thật.
7. Include source producer vào composite rồi chạy đúng consumer bằng substituted project.
8. Dùng `dependencies` và `dependencyInsight` để chứng minh Gradle đang chọn file published hay included project.
9. Viết smoke/contract test có stdout cố định và exit status khác 0 nếu kết quả sai.
10. Xây release gate trên CI gồm source consumer test, binary consumer test, metadata/bytecode verification.
11. Phát hiện trường hợp composite pass nhưng publication fail, và trường hợp binary pass nhưng source fail.
12. Hiểu giới hạn của composite: publication-specific variants, POM customization, classifiers, version semantics.
13. Cấu hình explicit substitution hoặc tắt global substitution rules cho một configuration khi cần.
14. Tránh cache/repository/CI settings khiến bài kiểm tra binary chỉ là source test ngụy trang.

## 2. Hai chế độ kiểm thử khác nhau ở đâu?

### 2.1. Source mode qua composite build

Ví dụ consumer khai báo:

~~~kotlin
dependencies {
    implementation("dev.example:greeting-lib:1.0.0")
}
~~~

Settings:

~~~kotlin
includeBuild("../producer")
~~~

Nếu included build cung cấp project có `group=dev.example` và `name=greeting-lib`, Gradle mặc định thay module dependency bằng project từ source build. Gradle biên dịch producer theo task graph và đưa output vào compile/runtime classpaths của consumer.

Điều này hữu ích khi phát triển song song, debug source code mới nhất, không phải publish từng lần sửa. Nó **không tự kiểm tra POM/JAR trong Maven repository**.

### 2.2. Binary/published mode

Cùng consumer dependency:

~~~kotlin
dependencies {
    implementation("dev.example:greeting-lib:1.0.0")
}
~~~

Nhưng consumer **không include producer build** hoặc có configuration tắt global composite substitution. Gradle giải quyết module từ repository:

~~~text
dev/example/greeting-lib/1.0.0/
├── greeting-lib-1.0.0.jar
├── greeting-lib-1.0.0.pom
└── greeting-lib-1.0.0.module
~~~

Thư mục trên mô tả các **đầu ra chính** của Maven Publish khi module metadata được xuất bản; có thể còn files `.sha1`, `.sha256` và sources JAR. Test này kiểm đúng artifacts/metadata mà một consumer bên ngoài nhận.

### 2.3. Bảng so sánh

| Tiêu chí | Source mode (composite) | Binary mode (published) |
| --- | --- | --- |
| Dependency declaration | `group:name:version` | `group:name:version` |
| Source resolved from | Included build project | Maven/Ivy repository |
| Compile input | Producer project output/variants | Published JAR và module metadata |
| Source changes local | Có thể áp ngay sau rebuild | Không tác động tới bản đã publish |
| Publication POM được dùng | Thông thường không | Có, tùy Gradle metadata selection |
| Version string bảo đảm tag trùng? | Không | Trỏ module version cụ thể |
| Khả năng phát hiện missing publication resource | Có thể bỏ sót | Có thể phát hiện bằng runtime test |
| Khả năng phát hiện source regression chưa publish | Có | Không nếu binary không đổi |
| Tốc độ inner-loop | Thuận tiện, không cần publish | Cần có artifact sẵn |
| Dùng làm release gate | Một nửa của kiểm chứng | Nửa còn lại bắt buộc |

**Kết luận quan trọng:** Không cho rằng source và binary tương đương chỉ vì cùng tọa độ dependency trong build script.

## 3. Composite build khác multi-project build

### 3.1. Multi-project build

Trong một build có:

~~~kotlin
include(":api", ":app")
~~~

consumer có thể dùng:

~~~kotlin
dependencies {
    implementation(project(":api"))
}
~~~

Đây là project dependency **trong cùng build**.

### 3.2. Composite build

Trong consumer settings:

~~~kotlin
includeBuild("../producer")
~~~

`producer` là **một build độc lập**, có `settings.gradle.kts`/`build.gradle.kts` riêng. Trong consumer build, **không** sử dụng `project(":producer")` để tham chiếu một project thuộc included build. Đúng là:

~~~kotlin
dependencies {
    implementation("dev.example:greeting-lib:1.0.0")
}
~~~

Gradle đối chiếu external module coordinates với projects do included build cung cấp rồi thực hiện substitution.

### 3.3. included build không tự chia sẻ mọi cấu hình

Producer build và consumer build có thể có:

- Repositories khác nhau.
- Version catalogs khác nhau.
- `gradle.properties` riêng.
- Plugins, source sets và toolchains riêng.
- Task paths, group/name/version và CI policies riêng.

Dù chạy cùng Gradle invocation trong composite, chúng vẫn là **các builds riêng**. Đừng giả định root consumer `repositories { ... }` đã thêm repository cho included producer build. CLI project properties có cơ chế truyền vào cả build tree theo Gradle, nhưng file `gradle.properties` của một build không phải cấu hình dùng chung vô điều kiện cho các build khác.

## 4. Điều kiện để default dependency substitution hoạt động

Gradle composite build mặc định phát hiện project theo:

~~~text
project.group + ":" + project.name
~~~

Nếu consumer yêu cầu:

~~~text
dev.example:greeting-lib:1.0.0
~~~

thì producer phải cung cấp project có:

~~~text
group = dev.example
project name = greeting-lib
~~~

**Mặc định Gradle chọn theo group:name, không yêu cầu source project.version bằng dependency version**. Đây là một điểm cực kỳ dễ gây hiểu nhầm khi kiểm release.

### 4.1. Tên thư mục không nhất thiết là project name

Producer có thư mục `producer/` nhưng settings khai:

~~~kotlin
rootProject.name = "greeting-lib"
~~~

Project name là `greeting-lib`, dù directory name là `producer`. Nếu bỏ tên này và Gradle lấy mặc định `producer`, dependency `dev.example:greeting-lib` có thể không được auto-substitute.

### 4.2. Group phải đúng

Trong producer:

~~~kotlin
group = "dev.example"
version = "1.0.0"
~~~

Nếu để group mặc định `unspecified`/`undefined`, composite có thể không tìm được match dự kiến. Kiểm `group`, `project.name` và publication coordinates thực tế.

### 4.3. Publication coordinates có thể khác project identity

Nếu publication đặt `artifactId = "greeting-api"` còn project name là `greeting-lib`, default substitution theo group:name **không tự match** artifact mới. Khi đó có thể cần explicit substitution, hoặc đổi identity để nhất quán. Đây là lý do phải test **đúng publication**.

## 5. Project thực hành: hai builds, một Maven repository local

Cây thư mục:

~~~text
consumer-source-binary-lab/
├── producer/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/java/dev/example/greeting/GreetingService.java
├── consumer/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/java/dev/example/consumer/Main.java
└── repo/
    └── (Maven publication được tạo khi publish)
~~~

Ở đây:

- `producer` là **source build** của library.
- `consumer` là **application build**.
- `repo` là **file-based Maven repository** tách khỏi `~/.m2`, Maven Central và Gradle cache.
- `producer` publish module `dev.example:greeting-lib:1.0.0` vào `repo`.
- `consumer` dùng đúng module notation ở cả hai mode.
- `consumer/settings.gradle.kts` chỉ include source producer khi `sourceMode=true`.
- Một Java program kiểm tra contract ở runtime, thất bại bằng exception nếu library trả kết quả sai.
- Java 17 toolchain và `--release 17` được khai báo cho cả producer và consumer.
- Không cần external dependencies hay JUnit để làm bài lab cơ bản.

**Yêu cầu môi trường:** JDK 17, bản Gradle có hỗ trợ chạy trên JDK tương ứng (ví dụ Gradle 8.5/9.x phù hợp), Internet/caches để có Gradle distribution nếu chưa cài. Bài chỉ dùng core plugins `java-library`, `application`, `maven-publish`, không tải library ngoài.

## 6. Producer: settings.gradle.kts

Tạo `producer/settings.gradle.kts`:

~~~kotlin
rootProject.name = "greeting-lib"
~~~

Tên này là một phần quan trọng của default composite substitution. Nếu producer là một multi-project build thì phải kiểm group/name **của đúng subproject cung cấp artifact**, không chỉ root.

## 7. Producer: build.gradle.kts đầy đủ

Tạo `producer/build.gradle.kts`:

~~~kotlin
import org.gradle.api.publish.maven.MavenPublication
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("java-library")
    id("maven-publish")
}

group = "dev.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
    withSourcesJar()
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

publishing {
    publications {
        create<MavenPublication>("lib") {
            from(components["java"])
        }
    }

    repositories {
        maven {
            name = "lab"
            url = uri("../repo")
        }
    }
}
~~~

**Giải thích từng phần:**

1. `java-library` cung cấp Java API/implementation separation và `jar`.
2. `maven-publish` tạo các tasks xuất bản Maven artifacts/metadata.
3. `group=dev.example` + `rootProject.name=greeting-lib` tạo module identity khớp consumer.
4. `version=1.0.0` là release version của publication trong lab.
5. Toolchain 17 chọn javac phù hợp; `options.release=17` tạo bytecode Java 17 và giới hạn Java platform APIs.
6. `withSourcesJar()` bổ sung sources archive cho consumers; không bắt buộc để chạy demo.
7. `create<MavenPublication>("lib")` đặt **publication name là `lib`**, vì vậy task publish có tên gắn với `LibPublication`.
8. `from(components["java"])` publish Java component; metadata chứa API/runtime variants tương ứng.
9. `name="lab"` đặt **repository name là `lab`**, sinh task có hậu tố `LabRepository`.
10. `url=uri("../repo")` trỏ tới thư mục `repo` cùng cấp với `producer`. Đây là **sandbox local** cho bài thực hành, không phải Internet repository.

**Task để publish:**

~~~bash
gradle -p producer publishLibPublicationToLabRepository
~~~

Đây là task được Maven Publish plugin sinh từ publication `lib` và repository `lab`. Nếu đổi tên publication/repository, task name sẽ đổi theo.

**Chú ý về bảo mật:** Không thêm credentials/token vào file build cho repo local. Khi publish lên Maven Central/Artifactory/Nexus trong dự án thật, dùng secret store và quy trình promotion riêng.

## 8. Producer: Java source đầy đủ

Tạo `producer/src/main/java/dev/example/greeting/GreetingService.java`:

~~~java
package dev.example.greeting;

public final class GreetingService {
    private GreetingService() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Không có dependency ngoài. Method `greet(String)` là **public static API** mà consumer sẽ compile và thực thi.

Với JDK 17, class file thông thường tạo ra có **major version 61**. Nếu consumer runtime Java 17 nhưng library publish bằng Java 21 target (**major 65**), Gradle source-mode test trên JDK 21 có thể pass trong khi runtime Java 17 bị `UnsupportedClassVersionError`. Vì vậy release verification cần xét cả toolchain, bytecode và runtime.

## 9. Consumer: settings.gradle.kts bật/tắt source substitution

Tạo `consumer/settings.gradle.kts`:

~~~kotlin
rootProject.name = "consumer-app"

val sourceMode = providers.gradleProperty("sourceMode")
    .map { it.equals("true", ignoreCase = true) }
    .getOrElse(false)

if (sourceMode) {
    includeBuild("../producer")
}
~~~

Ý nghĩa:

- `-PsourceMode=true`: consumer tạo composite build với producer source, Gradle có thể substitute `dev.example:greeting-lib`.
- `-PsourceMode=false` hoặc không truyền property: **không include** producer; dependency phải resolve từ repository.
- `providers.gradleProperty(...)` đọc project property được truyền qua CLI.
- `includeBuild("../producer")` là đường **tương đối với consumer settings directory**, không phụ thuộc directory bạn đang đứng khi chạy Gradle.
- Không dùng `pluginManagement.includeBuild` vì producer ở đây cung cấp **Java library dependency**, không phải Gradle plugin.
- Không dùng `project(":producer")`: included build không phải subproject của consumer.

**Không nên dùng `includeBuild("../producer")` vô điều kiện** nếu mục tiêu là thử published JAR. Nếu include trong cả hai mode, bài test tưởng là binary có thể bị substitution mà không báo rõ.

## 10. Consumer: build.gradle.kts đầy đủ

Tạo `consumer/build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("application")
}

repositories {
    maven {
        url = uri("../repo")
    }
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

dependencies {
    implementation("dev.example:greeting-lib:1.0.0")
}

application {
    mainClass.set("dev.example.consumer.Main")
}
~~~

**Điểm đáng chú ý nhất:** Cả source mode và binary mode **đều dùng chính dòng dependency**:

~~~kotlin
implementation("dev.example:greeting-lib:1.0.0")
~~~

Không sửa dependency thành `project(":producer")` trong source mode. Gradle thực hiện module-to-project substitution khi producer included. Nhờ vậy consumer build script phản ánh đúng **public dependency contract** và phép so sánh hai mode có giá trị.

`repositories { maven { url = uri("../repo") } }` cho biết local Maven repository được consumer đọc ở binary mode. Khi source mode và substitution match, Gradle không cần lấy module library này từ repo; tuy nhiên build khác/dependencies khác vẫn có thể cần repositories.

## 11. Consumer: Java source có contract assertion

Tạo `consumer/src/main/java/dev/example/consumer/Main.java`:

~~~java
package dev.example.consumer;

import dev.example.greeting.GreetingService;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String actual = GreetingService.greet("consumer");
        String expected = "Hello, consumer!";

        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    "Contract mismatch: expected=" + expected
                            + ", actual=" + actual);
        }

        System.out.println("CONTRACT_OK=" + actual);
    }
}
~~~

Đây là một **consumer contract smoke test không cần JUnit**:

- Compiler phải tìm được `GreetingService` và method `greet(String)`.
- JVM phải nạp được class và runtime dependencies.
- Hành vi phải trả đúng chuỗi expected.
- Nếu output khác, ném `IllegalStateException`, Gradle `run` trả trạng thái failure.
- Nếu pass, in đúng **một dòng** do chương trình Java phát ra.

Stdout Java dự kiến ở cả hai mode:

~~~text
CONTRACT_OK=Hello, consumer!
~~~

**Không nhầm:** Gradle task logs có thể hiện thêm `> Task ...`, warning và `BUILD SUCCESSFUL` tùy log level. Dòng trên là payload từ `Main.main`, không phải full Gradle output.

## 12. Chạy thử binary/published mode đúng cách

Đứng tại thư mục cha `consumer-source-binary-lab` chứa `producer/` và `consumer/`.

### 12.1. Publish artifact vào Maven repository local

~~~bash
gradle -p producer publishLibPublicationToLabRepository
~~~

Sau khi task pass, repository local chứa tối thiểu các artifacts/metadata chính theo layout Maven, ví dụ:

~~~text
repo/dev/example/greeting-lib/1.0.0/
├── greeting-lib-1.0.0.jar
├── greeting-lib-1.0.0.pom
├── greeting-lib-1.0.0.module
└── greeting-lib-1.0.0-sources.jar
~~~

Có thể có checksum files, Maven metadata và khác biệt nhỏ theo Gradle version. Không dùng cây trên như bằng chứng rằng task đã chạy: **kiểm file thật**.

### 12.2. Chạy consumer với sourceMode=false

~~~bash
gradle -p consumer -PsourceMode=false clean run --quiet
~~~

Ở chế độ này consumer settings không `includeBuild("../producer")`, nên Gradle phải resolve `dev.example:greeting-lib:1.0.0` từ `repo`. Khi artifact vừa publish như dự kiến, stdout của Java program là:

~~~text
CONTRACT_OK=Hello, consumer!
~~~

Nếu chưa publish, có thể gặp:

~~~text
Could not find dev.example:greeting-lib:1.0.0
~~~

Đây là **dấu hiệu đúng** rằng binary mode đang cần artifact repository. Đừng “sửa” bằng cách bật source substitution: điều đó làm phép kiểm artifact mất ý nghĩa.

### 12.3. Chạy chỉ binary compile trước

~~~bash
gradle -p consumer -PsourceMode=false clean compileJava
~~~

Lệnh kiểm consumer public API compile được khi chỉ có published library. Sau đó `run` kiểm runtime behavior.

### 12.4. Dùng file repository riêng để tránh ngộ nhận

Bài lab **không** khai báo `mavenLocal()` hay `mavenCentral()` trong consumer. Điều này có lợi:

- Không lấy nhầm module cùng tọa độ từ cache của repository khác.
- Không dùng snapshot cũ trong `~/.m2/repository`.
- Dễ xem published POM/module/JAR trực tiếp.
- Không cần quyền upload Internet.

Gradle vẫn có dependency caches và execution caches. Nhưng khi không include build và repository chỉ trỏ local `repo`, module có nguồn resolution xác định hơn; dùng `dependencyInsight` để xác thực khi có nghi ngờ.

## 13. Chạy thử source/composite mode

Không cần publish lại source mỗi lần sửa.

~~~bash
gradle -p consumer -PsourceMode=true clean run --quiet
~~~

Settings sẽ include producer build. Gradle phát hiện project:

~~~text
group = dev.example
project name = greeting-lib
~~~

và substitute module dependency:

~~~text
dev.example:greeting-lib:1.0.0
       |
       v
included build :producer / project : (greeting-lib)
~~~

Đây là **sơ đồ logic**, không phải output của lệnh Gradle. Gradle lập task graph để build producer khi consumer cần classes/artifact, rồi chạy app.

Stdout Java của consumer vẫn:

~~~text
CONTRACT_OK=Hello, consumer!
~~~

**Quan trọng:** Hai chế độ cho cùng stdout không chứng minh chúng tải cùng file JAR. Để xác minh mode, xem dependency graph và selection reason (mục 14) hoặc thực hiện negative-control experiment (mục 16).

### 13.1. Vì sao dependency version không bảo vệ source mode?

Trong dependency string consumer có `:1.0.0`, nhưng default composite substitution chủ yếu match **group:name**. Nếu working tree của producer thực ra chứa code đang phát triển cho `1.1.0`, source test vẫn có thể chạy với code mới.

Do đó source mode kiểm **source checkout hiện tại**, không kiểm release `1.0.0`. Muốn đánh giá release candidate, pin đúng commit/tag và kiểm cả binary mode sau publish.

## 14. Chứng minh từng mode dùng đúng dependency

Một phép thử chỉ đáng tin nếu bạn có bằng chứng **đường resolution thực tế**.

### 14.1. Dependency graph trong binary mode

~~~bash
gradle -p consumer -PsourceMode=false \
    dependencies --configuration runtimeClasspath
~~~

Gradle report sẽ liệt kê module dependency đã resolve. Bạn mong đợi:

~~~text
dev.example:greeting-lib:1.0.0
~~~

Trích đoạn này chỉ minh họa, Gradle thực tế có tree markers, variants và các dòng phụ khác.

### 14.2. Dependency graph trong source mode

~~~bash
gradle -p consumer -PsourceMode=true \
    dependencies --configuration runtimeClasspath
~~~

Lúc này bạn mong thấy dependency được thay thế bằng **project từ included build**, thường report thể hiện `project :producer` hoặc build-tree project path tương ứng. Cách diễn đạt chính xác thay đổi theo Gradle release.

### 14.3. dependencyInsight cho selection reason

~~~bash
gradle -p consumer -PsourceMode=false \
    dependencyInsight --dependency greeting-lib \
    --configuration runtimeClasspath

gradle -p consumer -PsourceMode=true \
    dependencyInsight --dependency greeting-lib \
    --configuration runtimeClasspath
~~~

Trong source mode, hãy tìm dấu hiệu **composite build substitution** / project selection. Trong binary mode, hãy xác nhận module `dev.example:greeting-lib:1.0.0` từ repository, không phải project.

**Không suy đoán mode chỉ dựa vào output của Java application.** Library source và binary có thể có behavior giống nhau dù Gradle chọn đầu vào khác.

### 14.4. Kiểm tra đúng file được published

Linux/macOS:

~~~bash
jar --list --file \
    repo/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.jar
~~~

Tìm class:

~~~text
dev/example/greeting/GreetingService.class
~~~

Bytecode target:

~~~bash
javap -verbose \
    -classpath repo/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.jar \
    dev.example.greeting.GreetingService
~~~

Tìm:

~~~text
minor version: 0
major version: 61
~~~

Đây là **trích đoạn kiểm tra**; `javap -verbose` in thêm constant pool, methods và annotations.

### 14.5. Đọc Maven POM/Module Metadata

Trên Linux/macOS:

~~~bash
cat repo/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.pom
cat repo/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.module
~~~

Trên Windows PowerShell:

~~~powershell
Get-Content .\repo\dev\example\greeting-lib\1.0.0\greeting-lib-1.0.0.pom
Get-Content .\repo\dev\example\greeting-lib\1.0.0\greeting-lib-1.0.0.module
~~~

Kiểm `groupId`/`artifactId`/`version`, dependency scopes, variants, JVM target và artifacts. Một JAR tồn tại **không tự chứng minh metadata cho consumer là đúng**.

## 15. Chạy kiểm thử nhị phân và source tự động bằng Bash

Khi làm release gate, **một lệnh test phải fail nếu một mode fail**, không chỉ chạy tuần tự rồi xem logs thủ công. Trong thư mục cha của `producer` và `consumer`, Bash script:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

expected="CONTRACT_OK=Hello, consumer!"

# Bước 1: tạo published binary vào repository kiểm thử.
gradle -p producer publishLibPublicationToLabRepository

# Bước 2: chạy consumer trên binary.
binary_output="$(
  gradle -q -p consumer -PsourceMode=false --rerun-tasks run
)"
if [ "$binary_output" != "$expected" ]; then
  printf 'BINARY_MODE_FAILED: %s\n' "$binary_output" >&2
  exit 1
fi

# Bước 3: chạy consumer trên source included build.
source_output="$(
  gradle -q -p consumer -PsourceMode=true --rerun-tasks run
)"
if [ "$source_output" != "$expected" ]; then
  printf 'SOURCE_MODE_FAILED: %s\n' "$source_output" >&2
  exit 1
fi

printf 'BINARY_MODE=PASS\n'
printf 'SOURCE_MODE=PASS\n'
~~~

**Stdout của ba dòng cuối khi cả hai pass:**

~~~text
BINARY_MODE=PASS
SOURCE_MODE=PASS
~~~

Gradle publish task có logs riêng trước đó; hai dòng cuối là của script. `--rerun-tasks` giúp chạy lại các tasks liên quan thay vì chỉ thấy `UP-TO-DATE`, phù hợp bài kiểm tra behavior có chủ đích. Nó có thể tốn thời gian; CI thực tế chọn task cache strategy hợp lý theo mục tiêu.

**Không hard-code** script này cho production repository nếu release đã immutable; bài lab publish vào local `repo` và có thể chủ động thay file. Pipeline thực tế cần stage artifact theo version/commit và không overwrite cùng release tọa độ.

## 16. Negative controls: chứng minh hai đường thực sự độc lập

Một test dễ bị “pass giả” nếu luôn dùng source. Negative-control experiment làm khác biệt trở nên quan sát được.

### 16.1. Phát hành trước khi sửa source

1. Giữ `GreetingService.greet` trả `"Hello, " + name + "!"`.
2. Chạy `gradle -p producer publishLibPublicationToLabRepository`.
3. Chạy consumer binary, xác nhận `CONTRACT_OK=Hello, consumer!`.

### 16.2. Cố tình thay producer source, KHÔNG publish lại

Trong producer source, đổi method:

~~~java
public static String greet(String name) {
    return "Hi, " + name + "!";
}
~~~

Đây là **đoạn sửa tạm thời, cố tình làm contract sai**; không phải source cuối của project.

### 16.3. Consumer source mode sẽ fail

~~~bash
gradle -p consumer -PsourceMode=true --rerun-tasks run
~~~

App vẫn expected `Hello, consumer!` nhưng local source trả `Hi, consumer!`; vì vậy nó ném:

~~~text
java.lang.IllegalStateException:
Contract mismatch: expected=Hello, consumer!, actual=Hi, consumer!
~~~

Trên Gradle có thể thêm task failure wrapper và stacktrace; message trên là **nội dung exception quan trọng**, không phải toàn bộ stderr.

### 16.4. Consumer binary mode vẫn pass

~~~bash
gradle -p consumer -PsourceMode=false --rerun-tasks run --quiet
~~~

Vì repo vẫn chứa artifact đã publish **trước khi sửa source**, stdout Java vẫn:

~~~text
CONTRACT_OK=Hello, consumer!
~~~

Nếu binary cũng fail cùng contract mới, kiểm mode setting, selection reason và việc local `repo` có bị publish lại/overwrite không. **Khôi phục producer source** về bản `Hello` sau thí nghiệm.

### 16.5. Bài học rút ra

- Source mode thực sự phản ánh working tree.
- Binary mode thực sự phản ánh published bytes.
- Cùng dependency coordinates không buộc source working tree giống binary release.
- Test “hai chế độ đều pass” nên kết hợp dependency graph và artifact identity/checksum, không chỉ nhìn console.
- Không dùng negative-control sửa source trong production branch; chạy trong sandbox/temporary checkout rồi revert.

## 17. PowerShell: kiểm cả hai mode trên Windows

Khi có Gradle trong PATH và đang đứng ở thư mục cha:

~~~powershell
$expected = "CONTRACT_OK=Hello, consumer!"

& gradle -p producer publishLibPublicationToLabRepository
if ($LASTEXITCODE -ne 0) {
    throw "Producer publication failed"
}

$binary = (& gradle -q -p consumer -PsourceMode=false --rerun-tasks run |
    Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $binary -ne $expected) {
    throw "Binary consumer verification failed: $binary"
}

$source = (& gradle -q -p consumer -PsourceMode=true --rerun-tasks run |
    Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $source -ne $expected) {
    throw "Source consumer verification failed: $source"
}

Write-Output "BINARY_MODE=PASS"
Write-Output "SOURCE_MODE=PASS"
~~~

Trong PowerShell 5.1, `Out-String` giúp thu output ở dạng chuỗi; `Trim()` loại newline cuối. Đừng dùng riêng phép so output mà bỏ kiểm `$LASTEXITCODE`: Gradle có thể fail nhưng để lại một dòng stdout trùng expected trong trường hợp bất thường.

Windows classpath separator khi chạy Java trực tiếp là `;` thay vì dấu `:` trên Unix. Bài lab dùng Gradle Application task nên Gradle tự dựng classpath thích hợp.

## 18. Java 17 chạy độc lập với javac/java

Để tách vấn đề Gradle config khỏi Java source, bạn có thể compile hai classes trực tiếp bằng JDK17.

### 18.1. Linux/macOS

Từ thư mục cha:

~~~bash
mkdir -p out/producer out/consumer

javac --release 17 -d out/producer \
    producer/src/main/java/dev/example/greeting/GreetingService.java

javac --release 17 -cp out/producer -d out/consumer \
    consumer/src/main/java/dev/example/consumer/Main.java

java -cp out/producer:out/consumer dev.example.consumer.Main
~~~

Stdout chính xác:

~~~text
CONTRACT_OK=Hello, consumer!
~~~

### 18.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force -Path out\producer,out\consumer |
    Out-Null

javac --release 17 -d out\producer producer\src\main\java\dev\example\greeting\GreetingService.java

javac --release 17 -cp out\producer -d out\consumer consumer\src\main\java\dev\example\consumer\Main.java

java -cp "out\producer;out\consumer" dev.example.consumer.Main
~~~

Stdout giống trên.

**Giới hạn:** Các lệnh `javac/java` chỉ xác minh source contract khi library class đến từ source file; **không chứng minh** POM/Module Metadata hoặc published artifact. Phải làm bài `gradle -p consumer -PsourceMode=false run` để kiểm binary thật.

## 19. Khi source mode pass nhưng binary mode fail

Đây là trường hợp cốt lõi của bài.

### 19.1. Publication chưa được tạo

~~~text
Could not find dev.example:greeting-lib:1.0.0
~~~

Kiểm:

- Đã chạy `publishLibPublicationToLabRepository` đúng build?
- Local repo URL của producer và consumer có cùng trỏ thư mục `repo`?
- group/artifactId/version được publish đúng?
- Build trên CI đang tìm repository ở workspace khác?
- Module có bị policy repositories/filter/credentials chặn không?

**Không** bật sourceMode=true để làm binary test pass; nó bỏ qua artifact.

### 19.2. Published JAR thiếu class

Producer source có `GreetingService.java`, composite build biên dịch được; publication custom artifact trỏ nhầm JAR thiếu class. Binary consumer compile fail:

~~~text
package dev.example.greeting does not exist
~~~

Kiểm `jar tf`, `publishing { from(components["java"]) }` và publication primary artifact. Nếu một custom `artifact(...)` thay primary JAR, verify đúng producer.

### 19.3. Published JAR thiếu resource

Source build có resource trong `processResources` hoặc classpath, nhưng archive publish bị exclude. Source mode có thể chạy; binary runtime ném `null`/`IOException` vì resource không tồn tại.

Kiểm:

~~~bash
jar --list --file repo/dev/example/greeting-lib/1.0.0/greeting-lib-1.0.0.jar
~~~

và chạy consumer binary để thực sự nạp resource. Cần release validator ở producer, không chỉ unit test trên source tree.

### 19.4. Metadata API/runtime dependencies sai

Project source có `api(project(...))`/`implementation(...)` đúng; publication POM hoặc Module Metadata bị custom sai khiến external consumer thiếu transitive dependency.

Kiểm generated metadata:

~~~bash
gradle -p producer generatePomFileForLibPublication
gradle -p producer generateMetadataFileForLibPublication
~~~

Sau đó inspect `producer/build/publications/lib/pom-default.xml` và `module.json`. Tạo consumer test độc lập để compile/use public API và chạy runtime. Dependency resolution trong source mode và published mode có thể chọn variants khác.

### 19.5. Published bytecode target cao hơn

Java17 consumer runtime nạp class major65 và lỗi `UnsupportedClassVersionError`. Kiểm `javap -verbose` trên JAR published, đừng chỉ nhìn Java source toolchain. `--release 17` ở consumer **không hạ** bytecode library đã publish.

### 19.6. POM customization làm behavior khác default project

Composite substitution nhìn các project variants/default configuration; published module có thể chứa Maven POM/Gradle Module Metadata custom không mirror source project defaults. Khi metadata/artifacts khác, đây là **giới hạn được Gradle ghi nhận**: source mode có thể không phản ánh publication.

**Không chữa bằng cách ép Gradle luôn substitute rồi tuyên bố artifact pass.** Kiểm binary từ repo và sửa producer publication.

## 20. Khi binary mode pass nhưng source mode fail

Đây cũng là thông tin hữu ích, không có nghĩa release đang lỗi.

- Consumer đang dùng local source với breaking API change chưa publish.
- Included build cần JDK/plugin/repository riêng chưa có trên máy consumer.
- Included build không tự nhận version catalog/repository credentials từ consumer.
- Source working tree ở commit khác release artifact.
- Producer source module chưa build được, nhưng published `1.0.0` từ trước vẫn tốt.
- Group/name không match khiến substitution không xảy ra (nếu repo có binary, source mode **có thể pass giả** thay vì fail).

**Cách xử lý:** phân tách tính hợp lệ của release binary và tính tương thích của source candidate. Xem source compile error, plugin resolution và `dependencyInsight` để biết Gradle có thực sự substitute không. Không thay đổi release metadata chỉ để local source pass.

## 21. Explicit substitution khi coordinates không khớp

Giả sử producer project name là `greeting-project`, nhưng publication artifactId là `greeting-lib`. Default substitution theo group/project.name không match.

Trong `consumer/settings.gradle.kts`, khi bật sourceMode, thay block `includeBuild` bằng:

~~~kotlin
if (sourceMode) {
    includeBuild("../producer") {
        dependencySubstitution {
            substitute(module("dev.example:greeting-lib"))
                .using(project(":"))
        }
    }
}
~~~

Đây là **snippet thay thế** cho đoạn `if (sourceMode) { includeBuild("../producer") }` trong mục 9; không thêm cả hai lần `includeBuild`. Nó yêu cầu Gradle map external module `dev.example:greeting-lib` tới **root project `:` của included producer build**.

### 21.1. Không viết project(":greeting-lib") tùy tiện

Trong một **single-project included build**, project path của root là `:`, ngay cả khi `rootProject.name="greeting-lib"`. Với multi-project producer, đường thích hợp có thể là `:lib`. Phải kiểm settings của included build để biết đúng project path.

### 21.2. Substitution không đối chiếu published version mặc định

Explicit mapping `module("dev.example:greeting-lib")` không gắn điều kiện version. Consumer request `1.0.0` có thể nhận source checkout khác version. Đối với release parity, cần thêm gate kiểm commit/tag, group/name/version và published checksum/metadata.

### 21.3. Khi nào không nên explicit substitute?

Nếu group/name của producer đã match module notation, để Gradle tự đăng ký default substitution thường đơn giản hơn. Explicit rules hữu ích khi:

- Publication artifactId khác project.name.
- Có module coordinates legacy cần chuyển sang source project mới.
- Một build cung cấp module từ subproject với tên không khớp.
- Muốn giới hạn/mapping rõ dependency substitutions khi composite build lớn.

Không thêm mapping “cho chắc” mà không kiểm nó có thay dependency nào khác ngoài chủ đích.

## 22. Muốn thử published artifact trong cùng một composite build

Cách chính trong lab là **không include source producer ở binary mode**. Nhưng có tình huống build lớn luôn include producer và bạn vẫn muốn resolve published module cho một configuration riêng.

Gradle cung cấp:

~~~kotlin
resolutionStrategy.useGlobalDependencySubstitutionRules = false
~~~

Ví dụ Kotlin DSL **fragment nâng cao**, ở consumer đã áp `java`/`application`:

~~~kotlin
import org.gradle.api.attributes.Usage

val publishedRuntimeClasspath by configurations.creating {
    isCanBeConsumed = false
    isCanBeResolved = true

    extendsFrom(configurations.runtimeClasspath.get())

    resolutionStrategy.useGlobalDependencySubstitutionRules = false

    attributes.attribute(
        Usage.USAGE_ATTRIBUTE,
        objects.named(Usage.JAVA_RUNTIME)
    )
}
~~~

`publishedRuntimeClasspath` thừa hưởng declarations từ runtimeClasspath, nhưng **không áp các global composite substitution rules** vào resolution của configuration mới. Vì vậy nó có thể chọn binary từ Maven repository, trong khi `runtimeClasspath` thông thường vẫn chọn included project.

**Giới hạn quan trọng:**

- Đây là fragment minh họa, không phải thay thế `settings.gradle.kts` trong project runnable.
- Cần có Maven repository chứa artifact đúng.
- Phải đảm bảo attributes/variant selection đúng runtime expectations của project.
- Một configuration **không tự biến app `run` task thành published mode**. Để chạy trên configuration riêng, cần task JavaExec/Test launcher với classpath tương ứng và app classes phù hợp, đồng thời tránh compile-time project substitution làm test sai mục đích.
- Vì vậy **hai Gradle invocations với sourceMode=true/false** của bài lab dễ hiểu và ít nhầm hơn cho release pipeline.

Đây là cơ chế chính thức hữu ích khi xây advanced consumer tests nhưng không nên thêm complexity khi dùng hai modes ở settings đã đủ.

## 23. Phân biệt source compatibility, binary compatibility và publication compatibility

### 23.1. Source compatibility

Consumer Java source có thể compile với producer source đang checkout. Ví dụ method `greet(String)` tồn tại trong source module.

### 23.2. Binary compatibility

Một consumer đã compile trước đó có thể nạp và gọi method trên published JAR mà không gặp `NoSuchMethodError`, `NoClassDefFoundError` hay `IllegalAccessError`. Source compile success không luôn chứng minh ABI compatibility.

Một kiểm chứng mạnh gồm:

1. Compile consumer với version cũ đã phát hành.
2. Chạy compiled consumer class với candidate JAR mới theo chính sách binary compatibility.
3. Dùng binary compatibility analyzer nếu library có nhiều public APIs.
4. Chạy smoke/integration tests trên supported JDKs.

Đây là bài test **bổ sung**: yêu cầu khác với “cùng consumer source compile/run với cả source và published candidate”.

### 23.3. Publication compatibility

Những gì external consumer thấy là JAR + POM + Gradle Module Metadata, không chỉ compiled classes. Các metadata có thể xác định:

- API vs runtime dependencies.
- JVM target attributes.
- Capabilities và variant attributes.
- Optional/runtimeOnly dependencies.
- Dependency constraints/platforms.
- Sources/Javadoc artifacts.
- Publication coordinates và exclusions.

Một included source project không đảm bảo mọi publication-specific customization được mô phỏng chính xác. Do đó phải có binary consumer test từ staging repository.

## 24. Phân biệt các loại kiểm thử consumer

| Loại test | Phát hiện chính | Không thay thế |
| --- | --- | --- |
| Unit tests trong producer | Logic producer ở source | Publication metadata/artifact |
| Producer JAR inspection | Contents, manifest, bytecode | Consumer integration behavior |
| Source composite consumer test | Integration với latest source | Published binary |
| Published consumer compile test | Public API, metadata, transitive compile deps | Runtime behavior |
| Published consumer runtime test | Runtime classpath, classloading, behavior | Binary ABI full surface |
| Consumer chạy trên min JDK | Java compatibility | Version/metadata trust |
| Binary compatibility comparison | ABI regressions | Behavior semantic tests |
| SBOM/license/security gate | Supply chain policy | Functional compatibility |
| SHA-256/signature verification | Integrity/authenticity theo trust model | Correctness/functionality |

**Không nên** chỉ thêm `includeBuild("../producer")` rồi coi đã có consumer integration test đủ để release library. Đó mới là source integration test.

## 25. Kiểm tra transitive dependencies: bài toán thật

Project lab cố ý không có external deps để chạy ngay. Trong dự án thật, producer có thể khai báo:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api("org.example:public-api:1.2.0")
    implementation("org.example:internal-engine:3.4.0")
    runtimeOnly("org.example:runtime-adapter:2.0.0")
}
~~~

Các tọa độ `org.example:...` trên **chỉ minh họa**, không phải modules phải tải khi chạy lab.

Điểm cần kiểm:

- `api` dependencies được consumer nhìn thấy ở compile classpath nếu public API cần.
- `implementation` thường không xuất hiện trên compile classpath của external consumer nhưng có thể nằm trong runtime graph.
- `runtimeOnly` phải được publish/resolve đúng theo Java component runtime variant.
- Maven POM scopes và Gradle Module Metadata có thể biểu đạt model khác nhau; consumer Gradle chọn metadata theo rules của nó.
- Nếu plugin custom publication sai POM/module.json, source mode vẫn có thể chạy do project variants nhưng binary mode fail.

### 25.1. Dependency report cho từng mode

~~~bash
gradle -p consumer -PsourceMode=false \
    dependencies --configuration compileClasspath

gradle -p consumer -PsourceMode=false \
    dependencies --configuration runtimeClasspath

gradle -p consumer -PsourceMode=true \
    dependencies --configuration compileClasspath

gradle -p consumer -PsourceMode=true \
    dependencies --configuration runtimeClasspath
~~~

So module names, versions, capabilities và selected variants. Đừng chỉ xem `implementation` declarations; cần xem resolved graph đúng configuration.

### 25.2. Consumer độc lập chứng minh điều gì?

Với published mode consumer ở **một build khác**:

- Không có `project(":producer")`.
- Không nhận repositories/version catalogs của source producer build.
- Không đọc source/output directories của producer.
- Phải resolve published metadata từ repository.
- Phải compile/run trên JDK target của consumer.
- Kiểm được public contract mà một downstream project thực sự gặp.

Vì vậy independent consumer test có sức phát hiện lỗi publication tốt hơn việc chỉ chạy `producer:test`.

## 26. Version alignment và release candidate

### 26.1. group:name đúng nhưng version sai

Ví dụ consumer khai:

~~~text
dev.example:greeting-lib:1.0.0
~~~

và producer working tree có:

~~~text
group=dev.example
project.name=greeting-lib
project.version=1.1.0-SNAPSHOT
~~~

Gradle source substitution vẫn có thể map vào current project vì match group:name. Test source pass **không chứng minh** version 1.0.0 trong repo tương đương source 1.1.0-SNAPSHOT.

**Release QA cần pin:**

- Producer Git commit/tag ứng với release candidate.
- `group`/`artifactId`/`version`.
- Toolchain, Gradle Wrapper, dependency versions/locks.
- Published artifact checksum sau build.
- Consumer modes test cùng contract trên đúng release candidate.

### 26.2. Đừng overwrite immutable release

Bài lab dùng file repository local để thuận tiện thử nghiệm. Production Maven releases thường nên **immutable**. Không upload lại cùng `1.0.0` với bytes khác chỉ để làm một test pass; downstream caches có thể giữ phiên bản cũ và dẫn đến không tái lập.

Nên publish candidate vào **staging repository** hoặc version candidate riêng, test consumer binary từ staging, rồi promote chính artifact đó.

### 26.3. Snapshot/caches có thể làm méo kết quả

Nếu dependency version đang thay đổi và Gradle caches giữ metadata/artifacts, test binary có thể dùng bytes không phải bản kỳ vọng.

Hướng chẩn đoán:

- Dùng immutable version/staging repository khi có thể.
- Kiểm checksum artifact từ staging và file đã resolve.
- Dùng `--refresh-dependencies` khi có lý do thực sự cần làm mới resolution.
- Đừng lấy `--refresh-dependencies` làm cách chữa logic sai; nó không tắt composite substitution.
- Với `changing`/dynamic modules, kiểm caching policy và lockfiles.

### 26.4. Gradle Module Metadata có thể được ưu tiên

Gradle có thể dùng `.module` metadata cho Gradle consumers; Maven consumers dùng POM. Khi cả hai tồn tại, kiểm **cả hai** theo release policy. Một POM nhìn đúng nhưng Gradle module variants sai vẫn có thể làm Gradle consumer fail. Đó là lý do bài lab đọc `.pom` và `.module` ở mục 14.

## 27. CI pipeline hai lane: source và binary

Một release pipeline có thể được tổ chức:

~~~text
Producer commit / release candidate
              |
              v
          Producer tests
              |
              v
       Build JAR + metadata
              |
              +----------------------+
              |                      |
              v                      v
      Source lane               Published lane
    includeBuild(...)         publish to staging
    consumer compile/run      consumer clean build
              |                 from staging repo
              |                      |
              v                      v
       Contract result          Contract result
              |                      |
              +----------+-----------+
                         |
                         v
             Compare results/graphs
                         |
                         v
            Artifact QA + checksum
                         |
                         v
               Promote release
~~~

### 27.1. Lane A: source

- Checkout candidate source.
- Consumer includes producer source.
- Compile public APIs, run contract smoke/integration tests.
- Confirm dependencyInsight shows project substitution.
- Phát hiện breaking changes trong code mới chưa publish.

### 27.2. Lane B: published

- Build/publish candidate artifact vào staging.
- Consumer **không include source producer**, hoặc tắt substitution đúng configuration.
- Resolve version từ staging repository; ưu tiên clean isolated consumer workspace.
- Compile và run contract tests trên minimum supported JDK.
- Kiểm POM/module metadata, transitive dependencies và artifact contents.
- Confirm dependencyInsight shows module resolution.

### 27.3. So sánh đầu ra

Cả hai lanes phải đạt cùng **contract** (trong lab: `CONTRACT_OK=Hello, consumer!`). Với real projects, contract có thể gồm API compile, JSON responses, serialization formats, database migrations, CLI exit codes, file output schemas và integration interactions.

Không đòi source và binary nhất thiết có **cùng hash JAR** nếu build inputs hoặc packaging khác. Khi mục tiêu là reproducible same-commit build, phải kiểm bytes riêng với policies/toolchains khớp.

### 27.4. Release gate phải fail khi một lane fail

Một kết quả đúng:

~~~text
SOURCE_MODE=PASS
BINARY_MODE=PASS
PUBLICATION_METADATA=PASS
RUNTIME_TARGET=PASS
CHECKSUM=PASS
~~~

Đây là **mẫu báo cáo CI**, không phải output tự động của Gradle lab. Khi thiếu lane nào, **không promote release**.

### 27.5. Tách build tree nếu cần để tránh accidental substitution

Không chạy published consumer test trong composite settings vô điều kiện. Dùng:

- Settings flag `sourceMode=false` như lab.
- Một consumer build độc lập không include source.
- Hoặc configuration `useGlobalDependencySubstitutionRules=false` khi thiết kế nâng cao.

Đồng thời kiểm `dependencyInsight`; đừng chỉ tin tên task như `testPublished`.

## 28. Groovy DSL tương đương

Nếu nhóm dùng `build.gradle`/`settings.gradle`, có thể tạo cùng mô hình.

### 28.1. Producer settings.gradle

~~~groovy
rootProject.name = 'greeting-lib'
~~~

### 28.2. Producer build.gradle

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'dev.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

publishing {
    publications {
        lib(MavenPublication) {
            from components.java
        }
    }
    repositories {
        maven {
            name = 'lab'
            url = uri('../repo')
        }
    }
}
~~~

### 28.3. Consumer settings.gradle

~~~groovy
rootProject.name = 'consumer-app'

def sourceMode = providers.gradleProperty('sourceMode')
    .map { it.equalsIgnoreCase('true') }
    .getOrElse(false)

if (sourceMode) {
    includeBuild '../producer'
}
~~~

### 28.4. Consumer build.gradle

~~~groovy
plugins {
    id 'application'
}

repositories {
    maven {
        url = uri('../repo')
    }
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

dependencies {
    implementation 'dev.example:greeting-lib:1.0.0'
}

application {
    mainClass = 'dev.example.consumer.Main'
}
~~~

Java sources ở mục 8 và 11 không đổi. Đây là **phương án Groovy DSL thay thế** cho Kotlin DSL, không trộn hai build scripts trong cùng project. Nếu dùng Groovy, tên task Maven publication/repository vẫn dựa trên `lib` và `lab` theo cùng convention.

## 29. Những lỗi phổ biến nhất và cách xử lý

### Lỗi 1. Consumer tưởng thử binary nhưng settings luôn include producer

~~~kotlin
includeBuild("../producer")
~~~

được viết vô điều kiện. Gradle thay module bằng project source.

**Sửa:** tách modes qua settings flag/independent consumer, xác nhận `dependencyInsight`.

### Lỗi 2. Dùng project(":producer") trong composite

Producer là included build, không phải subproject.

**Sửa:** consumer khai `implementation("dev.example:greeting-lib:1.0.0")` và Gradle substitution theo coordinates.

### Lỗi 3. Project name khác artifactId

Producer root tên `producer` nhưng consumer yêu cầu `greeting-lib`, source substitution không match.

**Sửa:** thống nhất `rootProject.name` với published identity hoặc explicit substitution.

### Lỗi 4. group không được đặt

Producer group mặc định không match `dev.example`.

**Sửa:** đặt `group="dev.example"` cho project cung cấp module.

### Lỗi 5. Version 1.0.0 trong consumer nhưng source là 1.1.0

**Sửa:** hiểu default substitution dựa group/name; pin producer commit/tag và kiểm binary release riêng.

### Lỗi 6. Binary test chưa publish repo

Consumer binary báo `Could not find`.

**Sửa:** publish đúng task tới local/staging repository, kiểm GAV và repo path, không bật source mode để lấp lỗi.

### Lỗi 7. Producer publish sai JAR

Source compile pass nhưng binary thiếu class/resource.

**Sửa:** inspect primary publication artifact, `jar tf` và metadata, thêm producer artifact validation gate.

### Lỗi 8. POM customization khác project variant

Source mode pass, published mode fail.

**Sửa:** đọc `pom-default.xml`/`module.json`, test independent consumer và sửa publication config.

### Lỗi 9. Runtime dependency không được publish

Consumer compile pass nhưng `run` ném `NoClassDefFoundError`.

**Sửa:** kiểm `api/implementation/runtimeOnly` mapping và runtimeClasspath trong binary mode.

### Lỗi 10. Dùng Maven Local mơ hồ

Có nhiều module trùng tọa độ ở `~/.m2` hoặc repository khác.

**Sửa:** dùng staging/file repository rõ như lab, hạn chế repository order ambiguity, xem dependencyInsight.

### Lỗi 11. Chỉ kiểm `gradle help`

`help` pass không chứng minh dependency compile/run được.

**Sửa:** chạy `compileJava`, `run`, integration tests và quan sát actual graph.

### Lỗi 12. Chỉ chạy source test trên JDK mới

Production consumer dùng JDK17, library binary chứa class.major65.

**Sửa:** `--release 17` trong producer, kiểm `javap` trên published JAR và chạy binary consumer trên Java17.

### Lỗi 13. Không xác minh mode bằng dependencyInsight

Hai mode in giống nhau nên tưởng chắc chắn là hai nguồn.

**Sửa:** đọc graph/selection reason; negative control ở mục 16 cho thấy source/binary độc lập.

### Lỗi 14. Dùng --refresh-dependencies để tắt composite

Refresh chỉ tác động dependency resolution caches, không tự tắt global source substitution.

**Sửa:** gỡ includeBuild hoặc dùng `useGlobalDependencySubstitutionRules=false` đúng configuration.

### Lỗi 15. Dùng --offline khi repo chưa sẵn

Producer publish chưa tạo artifacts; consumer binary không thể resolve.

**Sửa:** publish trước; offline chỉ dùng khi dependencies/caches/repository sẵn và toolchain/plugins không cần network.

### Lỗi 16. Cùng release version bị overwrite

CI test lúc file cũ, deploy file mới.

**Sửa:** immutable candidate artifact, SHA-256 và staging promotion; không rebuild/overwrite sau QA.

### Lỗi 17. Đọc wrong build.gradle.kts

Producer/consumer có settings, repositories và catalogs riêng; root consumer không cấu hình giúp producer.

**Sửa:** kiểm từng build boundary và đúng path `producer/`, `consumer/`.

### Lỗi 18. Explicit substitution nhầm project path

Root project của included build có path `:`, không phải `:greeting-lib`.

**Sửa:** dùng `project(":")` cho single-project producer hoặc subproject path đúng.

### Lỗi 19. Consumer source test pass nhưng published API binary break

Compile consumer source với new library pass, nhưng compiled consumer cũ có thể cần method descriptor đã bị xóa.

**Sửa:** thêm ABI compatibility test và runtime binary linkage verification.

### Lỗi 20. Cho rằng publication khác source là lỗi Gradle

Composite sử dụng project/default configurations, còn published metadata có thể được custom khác.

**Sửa:** hiểu giới hạn được tài liệu Gradle công bố, test published consumer riêng và điều chỉnh publication contracts.

### Lỗi 21. Dùng snapshot changing dependency và hiểu sai caches

Artifact mới đã publish nhưng consumer vẫn resolve version cached.

**Sửa:** policy immutable versions, chọn đúng staging version, kiểm checksum, dùng refresh khi có căn cứ.

### Lỗi 22. Test binary trong same composite với runtimeClasspath vẫn bị substitution

**Sửa:** dùng separate sourceMode=false build hoặc configuration tắt global substitutions, xác minh selected components.

## 30. Bài tập có đáp án

### Bài 1. Composite substitution theo khóa nào?

Producer `group=dev.example` và `rootProject.name=greeting-lib`. Consumer yêu cầu `dev.example:greeting-lib:1.0.0`.

**Đáp án:** Default Gradle substitution match `dev.example:greeting-lib`; version không là bằng chứng source project đúng release1.0.0.

### Bài 2. Vì sao không dùng project(":producer")?

**Đáp án:** Producer là included build, không thuộc project hierarchy của consumer. Dùng external module coordinates và includeBuild để thay bằng source.

### Bài 3. Nhìn vào dependency declaration

Hai modes dùng cùng:

~~~kotlin
implementation("dev.example:greeting-lib:1.0.0")
~~~

**Hỏi:** Vậy làm sao đổi nguồn?

**Đáp án:** Consumer settings bật/tắt `includeBuild("../producer")` qua `-PsourceMode=true/false`; không sửa dependency notation.

### Bài 4. Producer root name sai

Producer settings đặt `rootProject.name="producer"`.

**Đáp án:** Default substitution không match `greeting-lib`. Đổi rootProject.name hoặc khai explicit module-to-project substitution.

### Bài 5. Chưa publish

Chạy `gradle -p consumer -PsourceMode=false run` và báo `Could not find dev.example:greeting-lib:1.0.0`.

**Đáp án:** Binary mode thiếu artifact repository; chạy `gradle -p producer publishLibPublicationToLabRepository` và kiểm repo.

### Bài 6. Stdout của consumer

Với source/binary đúng như project lab:

~~~bash
gradle -p consumer -PsourceMode=true run --quiet
~~~

**Đáp án:**

~~~text
CONTRACT_OK=Hello, consumer!
~~~

### Bài 7. Trước khi release có nên chỉ chạy source mode?

**Đáp án:** Không. Source mode không kiểm file JAR/POM/module metadata đã publish; cần binary consumer test từ staging.

### Bài 8. Negative control

Publish producer `Hello` rồi sửa local source thành `Hi` mà chưa publish lại.

**Đáp án:** Source mode sẽ fail contract, binary mode vẫn pass từ repo, chứng minh hai nguồn độc lập.

### Bài 9. Sai dependency graph

Source mode output vẫn hiện external module và không có project substitution.

**Đáp án:** Kiểm settings sourceMode, included path, producer group/name và dependencyInsight; không đánh dấu source test pass khi chưa xác minh mode.

### Bài 10. Publication artifactId khác project.name

**Đáp án:** Dùng explicit substitution hoặc align identity nếu hợp lý, sau đó xác minh mapping đúng project.

### Bài 11. Java bytecode

Published class major65, Java17 consumer.

**Đáp án:** Không chạy được; Java17 hỗ trợ major61, cần target release17 hoặc nâng runtime contract có chủ đích.

### Bài 12. POM và module.json khác source variants

**Đáp án:** Composite không chứng minh publication metadata. Inspect generated files và binary consumer từ repository.

### Bài 13. ABI compatibility

Consumer source mới compile với candidate library, nhưng consumer binary cũ dùng method đã bị xóa.

**Đáp án:** Cần runtime binary compatibility/ABI test với precompiled consumer, source compile test không đủ.

### Bài 14. useGlobalDependencySubstitutionRules

Trong composite bạn muốn resolve published artifact cho một configuration riêng.

**Đáp án:** Dùng `resolutionStrategy.useGlobalDependencySubstitutionRules = false` trên configuration cần resolve published module, đảm bảo variants/attributes và launcher dùng đúng classpath.

### Bài 15. Version drift

Consumer request1.0.0, included producer version1.1.0-SNAPSHOT.

**Đáp án:** Source mode có thể chọn producer vì match group/name; phải pin release candidate commit/tag và test binary1.0.0 riêng.

### Bài 16. Repositories không dùng chung

Producer có Maven Central, consumer chỉ có local repo; source producer có external deps.

**Đáp án:** Included build giữ repository configuration riêng; phải giải quyết dependencies của producer ở producer build, không giả root consumer tự cung cấp repos.

### Bài 17. Gradle TestKit có thay consumer binary test?

**Đáp án:** Không. TestKit dùng để kiểm Gradle plugins/build logic; binary consumer test vẫn cần giải quyết published artifact và chạy application/library contract.

### Bài 18. SHA sau publish khác trước QA

**Đáp án:** Dừng promote, xác minh file upload đúng bytes hoặc có rebuild/overwrite. Release gate cần immutable staged artifacts.

### Bài 19. Consumer run thành công, tests chỉ Java 21

Production yêu cầu Java17, có đủ evidence chưa?

**Đáp án:** Chưa. Run binary consumer trên Java17 và kiểm class majors/transitive deps, không chỉ build trên Java21.

### Bài 20. CI hai lane

Source consumer pass, binary consumer fail vì missing resource.

**Đáp án:** Release fail; sửa packaging/artifact policy, publish candidate mới vào staging và chạy lại cả hai lanes.

## 31. Checklist đưa vào pull request / release pipeline

| Mục tiêu | Tiêu chí đạt |
| --- | --- |
| Producer identity | `group`, project name, artifactId, version được kiểm rõ |
| Source build | Included build path hợp lệ, Java toolchain/plugin build đúng |
| Dependency notation | Consumer giữ `group:name:version` giống external consumers |
| Source mode | `includeBuild` bật có chủ đích; dependencyInsight xác nhận project substitution |
| Binary mode | `includeBuild` tắt hoặc substitution disabled; dependencyInsight xác nhận published module |
| Repository | Local/staging repository riêng, exact GAV có artifacts |
| Publication | Primary JAR đúng, POM + Gradle Module Metadata hợp lệ |
| Compile contract | Consumer compile được trên source và binary |
| Runtime contract | Consumer run/integration tests pass ở cả hai modes |
| Bytecode/JDK | Published class target phù hợp supported Java runtime thấp nhất |
| Transitives | API/runtime dependencies được resolve đúng từ publication |
| Version identity | Source checkout/commit/tag đúng candidate, không nhầm version do substitution |
| Caches | Snapshot/changing dependency/refresh policy được kiểm soát |
| ABI | Binary compatibility có test riêng nếu thư viện cam kết backward compatibility |
| Integrity | SHA-256 của candidate artifact cố định, verify sau publish |
| CI gate | Chỉ promote khi cả source lane và binary lane pass |
| Regression | Negative control hoặc periodic check chứng minh modes độc lập |
| Không ảnh hưởng repo thật | Lab publish local; production dùng staging và immutable release |

**Kết luận:** Composite build giải quyết rất tốt nhu cầu **consumer và library cùng phát triển từ source** nhờ dependency substitution, nhưng **không đại diện đầy đủ cho artifact đã phát hành**. Để xác minh release, hãy dùng **cùng consumer dependency coordinates** trong hai chế độ: một lần include producer source, một lần thực sự resolve published JAR/POM/Module Metadata từ repository. Kiểm selection reason để tránh “binary test” vẫn bị substitute, chạy compile + runtime contract trên JDK mục tiêu, kiểm publication metadata/bytecode và chỉ promote **chính artifact** đã qua QA.

## 32. Tài liệu tham khảo chính thức

- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html) — included builds, source substitution, module-to-project mapping, tắt global rules cho configuration, giới hạn publication/default variants.
- [Gradle — Dependency Substitution](https://docs.gradle.org/current/userguide/resolution_rules.html#sec:dependency_substitution_rules) — quy tắc thay module/project dependencies.
- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html) — `group:name:version`, configurations, external modules.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) — `dependencies`, `dependencyInsight`.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html) — MavenPublication, repositories, POM/module metadata và generated publish tasks.
- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html) — API/implementation separation, outgoing compile/runtime variants.
- [Gradle — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html) — consumer attributes và selected variants.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html) — Java compiler/toolchain release, Test/JavaExec launchers.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html) — kiểm downloaded artifact checksums/signatures.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html) — quản lý resolved versions.
- [Gradle — Java Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html) — `run` và runtime classpath.
- [Oracle javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — `--release` và Java 17 compile.
- [Oracle javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html) — class-file major/minor, `-verbose`.
