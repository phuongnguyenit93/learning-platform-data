# Công bố plugin nội bộ hoặc lên Gradle Plugin Portal

## 1. Vì sao plugin cần một quy trình phát hành riêng?

Một Gradle plugin là mã **chạy trong quá trình Gradle thực hiện build**, thường được dùng để đăng ký task, tạo extension, áp dụng conventions, kiểm soát dependency hoặc cấu hình công cụ. Plugin có thể hoạt động tốt trong `buildSrc` hoặc `includeBuild("build-logic")` nhưng vẫn chưa phải là một **bản phát hành** có thể dùng từ repository.

Khi muốn tái sử dụng ở nhiều Gradle builds độc lập, nhà phát triển phải cung cấp:

- **Plugin ID** ổn định để consumer viết trong `plugins { ... }`.
- **Implementation class** thực hiện `Plugin<Project>`.
- **Implementation JAR** có classes và descriptor.
- **Plugin marker module** giúp Gradle tra plugin ID ra tọa độ của implementation.
- **Maven POM** và thường có Gradle Module Metadata `.module` để mô tả artifact và dependencies.
- **Version** thể hiện một bản phát hành được quản trị.
- **Repository** mà consumer có quyền đọc và producer có quyền publish.
- **Kiểm thử và metadata** đảm bảo consumer bên ngoài sử dụng được plugin.

Hai kênh phổ biến:

1. **Công bố nội bộ** qua Maven-compatible repository của tổ chức: kết hợp `java-gradle-plugin` với `maven-publish`.
2. **Công bố công khai** qua **Gradle Plugin Portal**: dùng plugin `com.gradle.plugin-publish`, metadata công khai, tài khoản/credentials và quy trình duyệt của Portal.

Một plugin có thể phát hành trên cả hai kênh, nhưng **không phải mọi plugin nội bộ đều phù hợp với Portal**. Plugin chứa policy độc quyền, địa chỉ infrastructure không được công khai hoặc mã nhạy cảm nên được quản lý tại repository riêng.

### 1.1. Luồng tổng quát

```text
Producer Gradle plugin source
   |
   +-- Java Plugin<Project> implementation
   +-- plugin ID / implementationClass registration
   +-- tests + validatePlugins
   |
   v
java-gradle-plugin + maven-publish
   |
   +-- plugin implementation JAR
   +-- main implementation Maven POM / .module
   +-- plugin marker POM
   |
   v
Maven nội bộ hoặc Portal
   |
   v
Consumer settings.gradle.kts
   pluginManagement { repositories { ... } }
   |
   v
Consumer build.gradle.kts
   plugins { id("dev.learning.greeting") version "1.0.0" }
   |
   v
Marker → implementation module → load plugin → register tasks
```

Điểm then chốt: **publish JAR thôi thường chưa đủ để `plugins` DSL tự tìm thấy plugin**. Consumer cần một plugin marker hoặc một cơ chế mapping tương đương.

## 2. Công bố nội bộ và Gradle Plugin Portal khác nhau thế nào?

| Hạng mục | Maven repository nội bộ | Gradle Plugin Portal |
| --- | --- | --- |
| Mục đích | Dùng trong nhóm/doanh nghiệp | Chia sẻ công khai |
| Repository | Nexus, Artifactory, GitHub Packages, Maven file/HTTP | Dịch vụ Gradle Plugin Portal |
| Plugin publishing | `java-gradle-plugin` + `maven-publish` | `com.gradle.plugin-publish` |
| Authentication | Token, user/password hoặc cơ chế riêng của repository | Portal API key và secret |
| Quyền truy cập | Có thể chỉ cấp cho nội bộ | Plugin đã duyệt thường có thể tải công khai |
| Marker module | Cần publish cho `plugins` DSL thông thường | Được công cụ plugin publishing xử lý |
| Metadata | POM, GMM, JAR, checksums, có thể signatures | Thêm website, VCS URL, displayName, description, tags và thông tin compatibility |
| Quy trình duyệt | Theo policy tổ chức | Theo điều khoản và quá trình phê duyệt Portal |
| Hợp với plugin chuyên biệt công ty | Rất phù hợp | Thường không |
| Upload thật | `publish` hoặc task Maven publication cụ thể | `publishPlugins` |

Một Maven repository có thể chứa nhiều loại artifact, từ thư viện đến Gradle plugin. Nó không tự biết plugin ID nào thuộc implementation artifact nào nếu thiếu metadata marker. Ngược lại, Gradle Plugin Portal có workflow và yêu cầu metadata dành riêng cho plugin.

## 3. Plugin ID, implementation module, marker: ba danh tính cần tách

Giả sử plugin của bài học có:

```text
Plugin ID:
  dev.learning.greeting

Implementation class:
  dev.learning.GreetingPlugin

Implementation Maven module:
  dev.learning:greeting-plugin:1.0.0

Plugin marker Maven module:
  dev.learning.greeting:dev.learning.greeting.gradle.plugin:1.0.0
```

Mặc dù các tên liên quan, chúng **không đồng nhất**.

- `dev.learning.greeting` là định danh người dùng ghi trong `plugins` DSL.
- `dev.learning.GreetingPlugin` là Java class được load.
- `dev.learning:greeting-plugin:1.0.0` là Maven coordinates của implementation.
- Marker có quy ước `plugin-id:plugin-id.gradle.plugin:version`.

Một consumer dùng:

```kotlin
plugins {
    id("dev.learning.greeting") version "1.0.0"
}
```

Gradle tìm **plugin marker** qua plugin repositories. Marker trỏ đến implementation coordinates. Sau đó Gradle lấy implementation JAR và dependencies cần để chạy plugin.

### 3.1. Plugin descriptor trong JAR

Gradle còn cần một descriptor ánh xạ plugin ID tới implementation class. Với ví dụ này, implementation JAR chứa đường dẫn:

```text
META-INF/gradle-plugins/dev.learning.greeting.properties
```

và nội dung tương đương:

```properties
implementation-class=dev.learning.GreetingPlugin
```

`java-gradle-plugin` có thể sinh descriptor từ khai báo `gradlePlugin { plugins { ... } }`.

**Phân biệt rõ:** descriptor nằm **trong JAR** giúp Gradle áp dụng plugin; marker nằm **ở repository** giúp Gradle tra từ plugin ID tới JAR.

### 3.2. Không nhầm plugin marker với Maven POM của implementation

| File/module | Công dụng |
| --- | --- |
| `greeting-plugin-1.0.0.jar` | Bytecode/plugin descriptor |
| `greeting-plugin-1.0.0.pom` | Maven metadata của implementation module |
| `greeting-plugin-1.0.0.module` | Gradle Module Metadata khi được phát hành |
| `dev.learning.greeting.gradle.plugin-1.0.0.pom` | Marker POM cho plugin ID |
| `META-INF/gradle-plugins/dev.learning.greeting.properties` | File bên trong JAR khai báo implementation class |

Consumer có thể bị lỗi **Plugin not found** dù file JAR chính đã có trong repository nếu marker không hiện diện và không có custom resolution strategy phù hợp.

## 4. `java-gradle-plugin` và `maven-publish` tạo những gì?

Plugin phát triển Gradle:

```kotlin
plugins {
    `java-gradle-plugin`
    `maven-publish`
}
```

Trong Kotlin DSL hai plugin accessors có dấu gạch nối được viết trong **backticks**.

- `java-gradle-plugin` hỗ trợ Java Gradle plugin development, plugin IDs, descriptors, các task/test integration liên quan.
- `maven-publish` cho phép publish Maven publications đến repository được định nghĩa.
- Khi cả hai được áp dụng và không tắt automated publishing, Gradle tạo một implementation publication và các marker publications phù hợp.

Với registration name `greeting`:

- Implementation publication thường có tên `pluginMaven`.
- Marker publication thường có tên `greetingPluginMarkerMaven`.
- Main POM task: `generatePomFileForPluginMavenPublication`.
- Marker POM task: `generatePomFileForGreetingPluginMarkerMavenPublication`.
- Main GMM task: `generateMetadataFileForPluginMavenPublication`.
- Aggregate Maven publishing task: `publish`.

Không cần tạo thêm một `MavenPublication` chỉ attach `jar` nếu `java-gradle-plugin` đã cấu hình đầy đủ. Việc publish artifact thủ công mà không hiểu marker dễ khiến consumer không tìm được plugin.

### 4.1. Plugin ID và tên registration

Trong:

```kotlin
gradlePlugin {
    plugins {
        create("greeting") {
            id = "dev.learning.greeting"
            implementationClass = "dev.learning.GreetingPlugin"
        }
    }
}
```

`create("greeting")` là **tên registration** phục vụ Gradle model/task/publication naming; `id` mới là **ID công khai** dùng trong consumer. Đổi registration name không đồng nghĩa đổi plugin ID. Đổi `id` có thể là breaking change và cần migration plan.

## 5. Bài thực hành có thể chạy: Java 17, publish vào Maven repository file-based

Ta sẽ tạo **hai Gradle builds độc lập**: `plugin-producer` và `plugin-consumer`. Một thư mục thứ ba `plugin-repo` đóng vai trò kho Maven nội bộ thử nghiệm.

Ưu điểm: không cần upload Internet, không cần API key Portal và không sửa Maven local của máy. Consumer vẫn thử đúng **cơ chế plugin marker + implementation artifact** như một project bên ngoài.

### 5.1. Cây thư mục

```text
plugin-publishing-lab/
├── plugin-producer/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/dev/learning/
│       │   ├── GreetingPlugin.java
│       │   └── GreetingTask.java
│       └── test/java/dev/learning/
│           └── GreetingPluginTest.java
├── plugin-consumer/
│   ├── settings.gradle.kts
│   └── build.gradle.kts
└── plugin-repo/
    └── ...             (được tạo khi publish)
```

Hai builds có settings riêng. Bài thực hành chọn plugin ID `dev.learning.greeting`, group `dev.learning` và version `1.0.0` chỉ trong phạm vi lab.

Môi trường cần Gradle hiện đại chạy với Java 17, có JDK 17/toolchain và Maven Central hoặc cache để tải dependencies của JUnit tests. Gradle Wrapper có thể được tạo cho mỗi build nếu chưa có.

### 5.2. Producer settings

**File `plugin-producer/settings.gradle.kts`:**

```kotlin
rootProject.name = "greeting-plugin"
```

Tên root project ảnh hưởng artifactId của Maven implementation module, tạo `dev.learning:greeting-plugin:1.0.0` khi group/version được cấu hình bên dưới.

### 5.3. Producer build script

**File `plugin-producer/build.gradle.kts`:**

```kotlin
plugins {
    `java-gradle-plugin`
    `maven-publish`
}

group = "dev.learning"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

gradlePlugin {
    plugins {
        create("greeting") {
            id = "dev.learning.greeting"
            implementationClass = "dev.learning.GreetingPlugin"
        }
    }
}

publishing {
    repositories {
        maven {
            name = "Lab"
            url = uri("../plugin-repo")
        }
    }
}

tasks.test {
    useJUnitPlatform()
}
```

Phân tích:

- `java-gradle-plugin` đăng ký plugin và hỗ trợ sinh descriptor, publications/validation.
- `maven-publish` tạo khả năng publish tới repository Maven.
- `gradlePlugin.plugins` quyết định plugin ID và implementation class.
- `group`, root project name và `version` tạo implementation coordinates.
- `publishing.repositories` chọn nơi **ghi artifact** chứ không phải nơi resolve dependencies của consumer.
- JUnit dependencies chỉ phục vụ **test của producer**, không phải plugin runtime dependency.
- File repo `../plugin-repo` được tạo bên cạnh build, không phải kho public.

Đừng thêm `artifact(tasks.jar)` vào một publication trùng khi publications tự động đã tồn tại.

### 5.4. Java plugin implementation

**File `plugin-producer/src/main/java/dev/learning/GreetingPlugin.java`:**

```java
package dev.learning;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class GreetingPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getTasks().register("greet", GreetingTask.class, task -> {
            task.setGroup("demo");
            task.setDescription("Print a greeting from a Gradle plugin");
        });
    }
}
```

**File `plugin-producer/src/main/java/dev/learning/GreetingTask.java`:**

```java
package dev.learning;

import org.gradle.api.DefaultTask;
import org.gradle.api.tasks.TaskAction;

public abstract class GreetingTask extends DefaultTask {
    @TaskAction
    public void greet() {
        getLogger().lifecycle("Hello from internal plugin!");
    }
}
```

Plugin tạo một task `greet`. Task class ghi thông báo qua Gradle logger, không tạo output file. Với code sản xuất có file output, task cần các property/input/output annotations và kiểm thử tính tương thích Gradle configuration cache.

Dòng log do task tạo ra là:

```text
Hello from internal plugin!
```

Đây không phải toàn bộ console log của Gradle, chỉ là thông điệp của task.

### 5.5. Test plugin bằng Gradle TestKit

`java-gradle-plugin` có tích hợp hỗ trợ plugin-under-test classpath cho Gradle TestKit. Functional test tạo một Gradle project tạm, áp dụng ID của plugin và chạy `greet` mà không publish artifact.

**File `plugin-producer/src/test/java/dev/learning/GreetingPluginTest.java`:**

```java
package dev.learning;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertTrue;

final class GreetingPluginTest {
    @TempDir
    Path projectDir;

    @Test
    void appliesPluginAndExecutesTask() throws IOException {
        Files.writeString(
                projectDir.resolve("settings.gradle.kts"),
                "rootProject.name = \"fixture\"\n"
        );
        Files.writeString(
                projectDir.resolve("build.gradle.kts"),
                "plugins { id(\"dev.learning.greeting\") }\n"
        );

        BuildResult result = GradleRunner.create()
                .withProjectDir(projectDir.toFile())
                .withArguments("greet", "--stacktrace")
                .withPluginClasspath()
                .build();

        assertTrue(
                result.getOutput().contains("Hello from internal plugin!")
        );
    }
}
```

Chạy từ `plugin-producer`:

```bash
./gradlew test --console=plain
./gradlew validatePlugins --console=plain
```

TestKit xác minh plugin có thể được áp dụng và task thực thi. `validatePlugins` kiểm tra một số quy tắc cấu hình task/plugin của Gradle. Hai bước này hữu ích, nhưng **chưa chứng minh artifact đã publish có marker/POM đúng**; bước tiếp theo phải kiểm tra repository.

### 5.6. Chuẩn bị Gradle Wrapper

Nếu repo đã có Gradle Wrapper, dùng Wrapper của repo. Nếu mới tạo thư mục, cần một bản Gradle tương thích đã cài để sinh Wrapper:

```bash
gradle wrapper
```

Chạy một lần trong mỗi build khi cần, rồi dùng `./gradlew` hoặc Windows PowerShell `.\gradlew.bat`. Kiểm tra `./gradlew --version` để biết Gradle JVM và phiên bản Gradle, không giả định JDK 17 tự được đóng vào wrapper.

## 6. Công bố vào repository nội bộ mô phỏng

Từ thư mục `plugin-producer`:

```bash
./gradlew clean check publish --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat clean check publish --console=plain
```

Task `publish` được `maven-publish` tạo để yêu cầu các publication được cấu hình đến publishing repositories. Nó khác `publishPlugins` của Plugin Publish Plugin dùng cho Gradle Plugin Portal.

### 6.1. Implementation publication

Đường dẫn chính:

```text
plugin-repo/
└── dev/learning/greeting-plugin/1.0.0/
    ├── greeting-plugin-1.0.0.jar
    ├── greeting-plugin-1.0.0.pom
    └── greeting-plugin-1.0.0.module
```

Artifact repository có thể thêm checksum sidecars và Maven metadata, tùy Gradle/repository.

### 6.2. Marker publication

Marker coordinates có quy tắc:

```text
group    = dev.learning.greeting
artifact = dev.learning.greeting.gradle.plugin
version  = 1.0.0
```

Đường dẫn file Maven marker:

```text
plugin-repo/
└── dev/learning/greeting/
    └── dev.learning.greeting.gradle.plugin/
        └── 1.0.0/
            └── dev.learning.greeting.gradle.plugin-1.0.0.pom
```

Marker POM tham chiếu implementation module `dev.learning:greeting-plugin:1.0.0`. Khi marker sai hoặc bị thiếu, consumer `plugins` DSL thường không tìm được plugin ID theo đường resolution chuẩn dù implementation JAR còn nguyên.

### 6.3. Kiểm tra POM và Gradle metadata

Từ producer:

```bash
./gradlew generatePomFileForPluginMavenPublication
./gradlew generatePomFileForGreetingPluginMarkerMavenPublication
./gradlew generateMetadataFileForPluginMavenPublication
```

Output trung gian thường nằm ở:

```text
build/publications/pluginMaven/pom-default.xml
build/publications/pluginMaven/module.json
build/publications/greetingPluginMarkerMaven/pom-default.xml
```

Đọc:

- Main POM: implementation coordinates và runtime dependencies của plugin.
- Main `.module`: Gradle Module Metadata mô tả variants/artifacts/dependencies.
- Marker POM: tọa độ theo plugin ID và dependency đến main module.

Nếu các publications không tồn tại, kiểm tra plugin IDs, `java-gradle-plugin`, `maven-publish` và việc có ai đã tắt `gradlePlugin.automatedPublishing` hoặc thay đổi publication setup không.

### 6.4. Kiểm tra plugin descriptor trong JAR

Với JDK cung cấp lệnh `jar`:

```bash
jar tf build/libs/greeting-plugin-1.0.0.jar
```

Tìm:

```text
META-INF/gradle-plugins/dev.learning.greeting.properties
dev/learning/GreetingPlugin.class
dev/learning/GreetingTask.class
```

Một JAR có descriptor đúng chưa đủ nếu plugin marker chưa được publish. Ngược lại marker đúng nhưng implementation class bị thiếu cũng không dùng được.

## 7. Consumer dùng plugin đã publish, không dùng source local

**File `plugin-consumer/settings.gradle.kts`:**

```kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("../plugin-repo")
        }
        gradlePluginPortal()
    }
}

rootProject.name = "plugin-consumer"
```

**File `plugin-consumer/build.gradle.kts`:**

```kotlin
plugins {
    id("dev.learning.greeting") version "1.0.0"
}
```

Chạy trong `plugin-consumer`:

```bash
./gradlew tasks --all
./gradlew greet --console=plain
```

PowerShell:

```powershell
.\gradlew.bat tasks --all
.\gradlew.bat greet --console=plain
```

Khi plugin resolve được, dòng do task in:

```text
Hello from internal plugin!
```

**Đây là phép thử publish end-to-end.** Consumer không có `includeBuild("../plugin-producer")`, không dùng `withPluginClasspath()` của TestKit và không dùng implementation JAR như dependency Java application. Gradle phải truy cập marker và implementation từ repository.

### 7.1. `pluginManagement.repositories` không giống `repositories`

`plugins` DSL cần resolve plugin **trước khi** Gradle chạy các câu lệnh project build script thông thường. Plugin repositories được khai báo tại settings:

```kotlin
pluginManagement {
    repositories {
        maven { url = uri("../plugin-repo") }
        gradlePluginPortal()
    }
}
```

Đoạn này đặt tại **settings.gradle.kts**. Chỉ khai báo:

```kotlin
repositories {
    maven { url = uri("../plugin-repo") }
}
```

trong `build.gradle.kts` chỉ cấu hình project dependency repositories, không phải thay thế cho plugin resolution.

### 7.2. Đừng dùng `implementation` để áp dụng plugin

Sai mục đích:

```kotlin
dependencies {
    implementation("dev.learning:greeting-plugin:1.0.0")
}
```

Đây là dependency dành cho Java application/library code nếu project có configuration `implementation`. Nó **không tự gọi `Plugin.apply`** hoặc tạo task `greet`. Muốn áp dụng plugin hãy dùng `plugins` DSL hay cơ chế plugin application tương ứng.

### 7.3. TestKit không thay thế consumer test

TestKit với `withPluginClasspath()` kiểm tra plugin code hiện tại. Consumer từ repo kiểm tra cả publication artifacts, marker, POM/GMM, coordinates, plugin implementation và repository accessibility. Cả hai loại test bổ trợ nhau.

## 8. Nếu thiếu marker: cách dùng `resolutionStrategy`

Một plugin đời cũ có thể chỉ publish implementation JAR/POM, không có marker. Một consumer có thể ánh xạ plugin ID sang implementation coordinates trong settings:

```kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("../plugin-repo")
        }
    }

    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "dev.learning.greeting") {
                useModule("dev.learning:greeting-plugin:1.0.0")
            }
        }
    }
}

rootProject.name = "plugin-consumer"
```

Đây là **phương án thay thế** cho settings ở mục 7, không phải block cần dán thêm vào cấu hình đã có marker.

Lợi ích: workaround cho một implementation module đã biết.

Giới hạn:

- Không sửa hoặc tạo marker trong repository.
- Hardcode implementation coordinates, nên phải quản lý version mapping.
- Nếu consumer request `2.0.0` mà rule vẫn ép `1.0.0`, consumer có thể dùng sai version.
- Một rule quá rộng có thể đổi plugin ID khác ngoài dự kiến.

Hướng bền vững là **sửa producer publishing** để phát hành marker đúng, không bắt mọi consumer giữ workaround riêng.

## 9. Đưa plugin lên Maven repository nội bộ thực

Khi chuyển từ file repo sang Nexus/Artifactory hoặc Maven server khác, cần xác định:

- HTTPS repository URL đúng, endpoint snapshot/release nếu tách.
- Phương thức authentication: username/password, token hoặc HTTP header.
- Publisher có quyền ghi, consumer chỉ cần quyền đọc.
- Chính sách immutable release và retention.
- Các loại file được cho phép: marker POM, main POM, `.module`, JAR, checksums.
- Mirror/proxy configuration của máy dev và CI.
- Credentials được cấp qua secret store, không commit.

Ví dụ Kotlin DSL **minh họa private Maven endpoint**:

```kotlin
publishing {
    repositories {
        maven {
            name = "Internal"
            url = uri("https://repo.example.org/repository/gradle-plugins/")

            credentials(PasswordCredentials::class) {
                username = providers.environmentVariable("INTERNAL_REPO_USER").orNull
                password = providers.environmentVariable("INTERNAL_REPO_PASSWORD").orNull
            }
        }
    }
}
```

`example.org` là domain minh họa, không phải server của một tổ chức cụ thể. Cần dùng endpoint thật do quản trị kho cung cấp trước khi chạy upload. Với repository dùng HTTP header token, phải dùng cơ chế auth tương ứng; đừng giả định `PasswordCredentials` áp dụng cho mọi dịch vụ.

### 9.1. Phân biệt hai chiều repository

Trong producer:

```kotlin
publishing {
    repositories {
        maven { url = uri("https://repo.example.org/repository/gradle-plugins/") }
    }
}
```

chỉ định **nơi ghi** publication.

Trong consumer settings:

```kotlin
pluginManagement {
    repositories {
        maven { url = uri("https://repo.example.org/repository/gradle-plugins/") }
    }
}
```

chỉ định **nơi đọc** plugin marker/implementation khi resolve `plugins` DSL. Hai cấu hình có thể cùng URL, nhưng quyền truy cập và mục đích khác nhau.

### 9.2. Plugin dependencies phải resolve được

Nếu plugin implementation có:

```kotlin
dependencies {
    implementation("com.google.guava:guava:33.3.0-jre")
}
```

thì Maven publication của plugin phải biểu diễn Guava dependency phù hợp; consumer còn cần plugin repositories/mirrors để tải Guava khi Gradle load plugin.

Việc main JAR tồn tại trên internal repo chưa chắc đủ nếu transitive dependency nằm ở Maven Central mà consumer bị chặn network. Kiểm tra cả dependency graph và repository access ở **Gradle plugin classpath**, không chỉ project `runtimeClasspath` của ứng dụng.

## 10. Gradle Plugin Portal: con đường công khai

Gradle Plugin Portal cung cấp khả năng khám phá plugins và áp dụng qua:

```kotlin
plugins {
    id("dev.learning.greeting") version "1.0.0"
}
```

khi plugin ID và version đã được xuất bản/chấp nhận. Khác kho Maven riêng, Portal có yêu cầu về account, plugin metadata, plugin ID, tài liệu và quá trình phê duyệt.

Theo tài liệu chính thức được tham khảo cho bài này, phiên bản ví dụ của **Plugin Publish Plugin** là `2.2.1`. Nên pin version phù hợp Gradle Wrapper của project và đối chiếu release notes trước khi nâng cấp.

### 10.1. Plugin Publish Plugin tự động làm gì?

Khi dùng:

```kotlin
plugins {
    id("com.gradle.plugin-publish") version "2.2.1"
}
```

Plugin Publish Plugin hiện đại (1.0+) tự áp dụng **Gradle Plugin Development Plugin** và **Maven Publish Plugin**. Nó dùng Maven publication model để tạo implementation/marker metadata và cung cấp task **`publishPlugins`** cho Portal.

Không cần lặp `java-gradle-plugin`/`maven-publish` chỉ vì muốn kích hoạt Portal plugin. Nhưng nếu cùng project còn phát hành nội bộ, phải hiểu publication tự động để tránh tạo trùng.

### 10.2. Cấu hình Portal bằng Kotlin DSL

Đây là **cấu hình mô phỏng**, không phải project được phép phát hành công khai ngay lập tức:

```kotlin
plugins {
    id("com.gradle.plugin-publish") version "2.2.1"
}

group = "dev.learning"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

gradlePlugin {
    website.set("https://example.org/gradle/greeting")
    vcsUrl.set("https://example.org/scm/greeting-plugin")

    plugins {
        create("greeting") {
            id = "dev.learning.greeting"
            implementationClass = "dev.learning.GreetingPlugin"
            displayName = "Greeting task for Gradle"
            description = "Adds a greet task that prints a greeting"
            tags.set(listOf("greeting", "task", "build"))
        }
    }
}
```

Trong bài tập, `example.org` chỉ giúp thể hiện định dạng URL; nó không chứng minh có docs/source repo thật. Plugin ID cũng chỉ là một ID minh họa trong lab, không khẳng định quyền sở hữu namespace trên Portal.

**Trước khi publish thật:** dùng website/VCS URL thực có tài liệu và source phù hợp, plugin ID thuộc quyền sử dụng của chủ dự án, nội dung có ích cho công chúng, metadata đúng yêu cầu Portal, và bảo đảm mã có thể được phân phối hợp pháp.

### 10.3. Metadata đáng chú ý

| Trường | Mục đích |
| --- | --- |
| `website` | Trang giới thiệu/docs plugin |
| `vcsUrl` | URL hệ thống quản lý mã nguồn |
| `id` | Plugin ID được người dùng áp dụng |
| `implementationClass` | Implementation class load trong Gradle |
| `displayName` | Tên hiển thị |
| `description` | Chức năng và giá trị plugin |
| `tags` | Phân loại/tìm kiếm |
| `group` / `version` | Coordinates và release identity |
| Compatibility declarations | Tình trạng hỗ trợ các Gradle features |

Một plugin demo chỉ in “Hello world” mà không có chức năng có giá trị rộng rãi có thể không đạt yêu cầu phê duyệt Portal. **Không dùng Portal để test một plugin học tập chưa hoàn thiện**.

### 10.4. Compatibility với Gradle features

Với Plugin Publish Plugin 2.1+, có API để khai báo hỗ trợ configuration cache và một số tính năng. Mảnh Kotlin DSL tham khảo:

```kotlin
import org.gradle.plugin.compatibility.compatibility

gradlePlugin {
    plugins {
        create("greeting") {
            id = "dev.learning.greeting"
            implementationClass = "dev.learning.GreetingPlugin"
            displayName = "Greeting task for Gradle"
            description = "Adds a greet task"
            tags.set(listOf("greeting", "task", "build"))

            compatibility {
                features {
                    configurationCache = true
                }
            }
        }
    }
}
```

Đây là **cấu hình thay thế registration `greeting` trong ví dụ Portal**, không nên khai báo hai registration cùng tên trong một project. `configurationCache = true` chỉ được khai báo khi plugin đã qua kiểm thử tương thích thật. Đừng khai báo sai chỉ để có badge hay ranking tốt.

Nếu chưa kiểm tra tương thích, cần đánh giá rõ trước khi công khai tuyên bố. Plugin có task action sử dụng `Project` object sai giai đoạn hoặc giữ state không serialize được có thể gây lỗi configuration cache.

## 11. Chuẩn bị tài khoản và credentials Portal

Để publish, nhà phát triển cần đăng ký tài khoản Portal và lấy **API key/secret** trong khu vực quản lý API Keys theo hướng dẫn chính thức.

Gradle có thể dùng hai Gradle properties:

```properties
gradle.publish.key=...
gradle.publish.secret=...
```

Dấu ba chấm ở đây chỉ mô tả **kiểu giá trị bí mật được cấp ngoài source**, không phải credentials có thể dùng thử. Không commit credentials thật trong `gradle.properties` của repository.

Môi trường CI thường cấp:

```text
GRADLE_PUBLISH_KEY
GRADLE_PUBLISH_SECRET
```

Sử dụng secret manager của CI để inject environment vars chỉ vào **release job** có quyền publish. Không truyền raw secret như `-Pgradle.publish.secret=...` trên command line nếu môi trường có phương án injection an toàn hơn, vì command-line args có thể bị ghi vào process listing/logs.

### 11.1. Không nhầm nội bộ và Portal credentials

- `INTERNAL_REPO_USER`/`INTERNAL_REPO_PASSWORD` trong ví dụ là secrets của Maven nội bộ.
- `GRADLE_PUBLISH_KEY`/`GRADLE_PUBLISH_SECRET` là secrets cho Gradle Plugin Portal.
- Chúng không được dùng thay nhau.
- Một CI job thử Maven repo cục bộ không cần Portal credentials.
- PR từ nguồn không tin cậy không nên được cấp quyền publish production/Portal.

### 11.2. Không in secrets để debug

Sai:

```kotlin
// KHÔNG sử dụng:
println(System.getenv("GRADLE_PUBLISH_SECRET"))
```

Nếu cần xác minh biến được cấu hình, chỉ log **trạng thái có/không**, không log giá trị. Khi credentials bị lộ trong log, cần xử lý/rotate theo chính sách sự cố của tổ chức.

## 12. Kiểm tra trước khi upload và publish thật lên Portal

### 12.1. Kiểm tra producer

Trong project Plugin Publish Plugin đã cấu hình:

```bash
./gradlew clean check validatePlugins --console=plain
```

Kiểm tra compilation, unit/functional tests và plugin validation. Tùy test setup, `check` có thể bao gồm nhiều loại verification hơn hoặc ít hơn; phải biết task graph thực tế.

### 12.2. Portal validation mà không upload

```bash
./gradlew publishPlugins --validate-only --console=plain
```

`--validate-only` phục vụ kiểm tra publication mà **không tải plugin lên Portal**. Nó không thay thế việc review license, quyền plugin ID, source/docs, TestKit và các integration tests từ Maven staging.

### 12.3. Publish thật

Chỉ khi đã được cấp quyền và phê duyệt phát hành công khai:

```bash
./gradlew publishPlugins --console=plain
```

**Đây là lệnh có side effect bên ngoài**. Không chạy chỉ để “xem có ổn không”. Sau khi upload, plugin có thể trải qua quá trình xét duyệt của Portal; thành công ở task upload không đồng nghĩa plugin đã có thể được consumer tải ngay.

Khi plugin được chấp nhận/hiển thị, cần thử một **consumer sạch** sử dụng `gradlePluginPortal()` và ID/version chính thức. Consumer test từ Maven file repo không bảo đảm Portal approval hoặc indexing đã xong.

### 12.4. Không dùng SNAPSHOT release trên Portal như Maven nội bộ

Plugin Portal có chính sách version/release riêng; không coi nó như Maven snapshot repository được phép liên tục overwrite. Với bản công khai, phát hành version ổn định và quản lý sự thay đổi qua version mới.

Nếu phải sửa bug của `1.0.0` sau khi công bố, quy trình nên là sửa nguồn, kiểm thử và phát hành `1.0.1` (hoặc version thích hợp), không upload bytes khác dưới cùng tọa độ release.

## 13. Groovy DSL tương đương

Một producer Groovy DSL cho kho Maven nội bộ có thể viết:

**`plugin-producer/build.gradle`:**

```groovy
plugins {
    id 'java-gradle-plugin'
    id 'maven-publish'
}

group = 'dev.learning'
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
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

gradlePlugin {
    plugins {
        greeting {
            id = 'dev.learning.greeting'
            implementationClass = 'dev.learning.GreetingPlugin'
        }
    }
}

publishing {
    repositories {
        maven {
            name = 'Lab'
            url = uri('../plugin-repo')
        }
    }
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Consumer `settings.gradle`:**

```groovy
pluginManagement {
    repositories {
        maven {
            url = uri('../plugin-repo')
        }
        gradlePluginPortal()
    }
}
rootProject.name = 'plugin-consumer'
```

**Consumer `build.gradle`:**

```groovy
plugins {
    id 'dev.learning.greeting' version '1.0.0'
}
```

Khi đổi DSL, Java classes `GreetingPlugin`, `GreetingTask` không cần đổi. Chọn **một** build script DSL phù hợp cho một project; không để hai file build scripts mâu thuẫn rồi kỳ vọng Gradle gộp.

Portal Groovy DSL:

```groovy
plugins {
    id 'com.gradle.plugin-publish' version '2.2.1'
}

group = 'dev.learning'
version = '1.0.0'

gradlePlugin {
    website = 'https://example.org/gradle/greeting'
    vcsUrl = 'https://example.org/scm/greeting-plugin'

    plugins {
        greeting {
            id = 'dev.learning.greeting'
            implementationClass = 'dev.learning.GreetingPlugin'
            displayName = 'Greeting task for Gradle'
            description = 'Adds a greet task'
            tags = ['greeting', 'task', 'build']
        }
    }
}
```

Đây cũng chỉ là **ví dụ cú pháp**, không phải metadata Portal của một dự án thật.

## 14. Kết hợp Portal và Maven private repository trong cùng producer

Plugin Publish Plugin hiện đại tự áp dụng Maven Publish Plugin, nên với project công khai có thể thêm một Maven staging repository để kiểm thử publication trước khi upload Portal.

Mảnh cấu hình bổ sung:

```kotlin
publishing {
    repositories {
        maven {
            name = "Staging"
            url = uri(layout.buildDirectory.dir("staging-plugins"))
        }
    }
}
```

Phân biệt:

- `publish` phát hành các Maven publications tới các `publishing.repositories` đã cấu hình.
- `publishPlugins` gửi plugin lên Gradle Plugin Portal.
- `publishPlugins --validate-only` chỉ kiểm tra metadata/upload readiness theo cơ chế Portal plugin mà không upload.
- `publishToMavenLocal` ghi vào Maven local của người dùng, không giống repository staging riêng.

**Không tạo publications trùng** khi Portal plugin đã tự áp dụng `java-gradle-plugin` và `maven-publish`. Kiểm tra task list/repository path trước khi thêm customization.

### 14.1. Vì sao staging consumer test quan trọng?

Một plugin dùng qua `includeBuild` có thể chạy tốt nhưng bản Maven publication thiếu marker hoặc POM dependencies. Consumer đọc từ staging repository sẽ phát hiện:

- Marker không tồn tại.
- Marker trỏ implementation sai.
- JAR thiếu descriptor.
- Transitive dependencies không resolve.
- Plugin compiled target không hợp Gradle JVM của consumer.

Vì vậy nên có ít nhất **một vòng published-mode test** trong release pipeline.

## 15. Source mode và published mode là hai phép thử khác nhau

**Source mode:**

```kotlin
pluginManagement {
    includeBuild("../plugin-producer")
}
```

Plugin có thể được áp dụng từ included build, không phải tải implementation/marker đã publish.

**Published mode:**

```kotlin
pluginManagement {
    repositories {
        maven { url = uri("../plugin-repo") }
    }
}
```

Consumer khai báo `id("dev.learning.greeting") version "1.0.0"` và phải resolve từ repository.

Source mode giúp debug nhanh. Published mode kiểm tra toàn bộ contract sau phát hành. **Đừng bật includeBuild trong smoke test mà lại tuyên bố marker đã hoạt động.**

## 16. Supply chain và bảo mật plugin

Gradle plugin có thể chạy code trong build process với quyền đọc source, filesystem và môi trường CI. Vì thế nó phải được review như **thành phần có khả năng thực thi**, không chỉ là một library ngẫu nhiên.

Cần:

1. Pin plugin version và Gradle Wrapper version.
2. Kiểm tra plugin source/maintainer/permissions.
3. Dùng repository HTTPS đáng tin, giới hạn mirror/filter theo policy.
4. Không cấp production tokens cho PR từ nguồn không tin cậy.
5. Kiểm tra plugin transitive dependency graph và CVE liên quan.
6. Quản lý checksum/signatures/dependency verification phù hợp.
7. Không in secrets trong task action hoặc build scan.
8. Xoay/revoke credentials khi lộ hoặc thay đổi quyền.
9. Có audit trail cho releases và approvals.
10. Không publish code, keys hoặc internal endpoints nhạy cảm ra public Portal.

### 16.1. Signing

Gradle có Signing Plugin `signing` để hỗ trợ ký artifacts khi pipeline cấu hình signing keys. Với Plugin Publish Plugin 1.0+, signing integration có thể áp dụng khi thêm plugin Signing và cấu hình phù hợp.

```kotlin
plugins {
    signing
}
```

Đoạn trên chỉ **áp dụng plugin Signing**, không phải một signing configuration hoàn chỉnh. Các khóa ký phải được cấp an toàn qua secrets manager và yêu cầu của kho. Không commit private signing keys hoặc passwords.

### 16.2. Không nhầm plugin classpath với application classpath

Nếu code plugin cần Guava:

```kotlin
dependencies {
    implementation("com.google.guava:guava:33.3.0-jre")
}
```

khai báo trong **plugin producer**, thì Guava hỗ trợ plugin implementation. Nó **không tự được thêm vào app `implementation`** chỉ vì app áp dụng plugin.

Nếu plugin chủ động gọi `project.dependencies.add(...)`, lúc đó nó mới thay đổi dependency graph của app. Đây là quyết định của plugin code, cần documentation và tests.

## 17. Tổ chức release CI/CD

Một pipeline đáng tin có thể đi theo hai nhánh:

```text
Pull request:
    compile plugin
         |
    test + TestKit + validatePlugins
         |
    generate implementation POM / marker POM
         |
    publish vào staging Maven file repo
         |
    consumer apply plugin / run greet
         |
    required quality checks

Release approval:
         |
    +----+----+
    |         |
    v         v
  Nội bộ    Public Portal
  publish   validate-only
  Maven     publishPlugins
  verify    Portal review
  consumer  consumer after approval
```

PR job không nên có release secrets. Khi cần credentials để đọc dependencies, chỉ cấp quyền tối thiểu; khi publish, job tách riêng có approval và protected environment.

### 17.1. Internal CI command

Khi dùng repo file-based của lab:

```bash
./gradlew clean check validatePlugins --console=plain
./gradlew publish --console=plain
```

Lệnh thứ hai là một hành động publish đến repository cấu hình. Nếu thay URL bằng kho production, cần đảm bảo job đã được phép làm điều đó.

### 17.2. Public Portal CI command

Với Plugin Publish Plugin đã cấu hình:

```bash
./gradlew clean check validatePlugins --console=plain
./gradlew publishPlugins --validate-only --console=plain
```

Chỉ sau release approval, credentials và plugin ID ownership hợp lệ:

```bash
./gradlew publishPlugins --console=plain
```

### 17.3. Artifact immutability

Một plugin release version nên tương ứng với **một bộ JAR/POM/GMM/marker bất biến**. Nếu version bị overwrite, caches và proxies có thể chứa các bản khác nhau. Dùng version mới để sửa, giữ changelog và support matrix rõ ràng.

## 18. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra/sửa |
| --- | --- | --- |
| `Plugin not found` | Không có `pluginManagement.repositories` đúng | Sửa consumer settings |
| Chỉ có plugin JAR, không có marker | Publish artifact thủ công | Dùng `java-gradle-plugin` + `maven-publish` và automated publishing |
| Marker trỏ implementation sai | Group/artifact/version mismatch | Đọc marker POM, main POM |
| Plugin descriptor thiếu | Plugin ID/implementation registration sai | Kiểm tra JAR `META-INF/gradle-plugins` |
| `ClassNotFoundException` implementation class | Sai package, JAR thiếu class | Kiểm tra `implementationClass` và archive |
| `UnsupportedClassVersionError` | Gradle daemon JVM quá cũ | Chọn JVM/target tương thích |
| `NoClassDefFoundError` bên trong plugin task | Plugin dependency thiếu hoặc conflict | Kiểm tra plugin POM/GMM và repositories |
| Consumer 401/403 | Auth/ACL của plugin repo không hợp lệ | Cấp quyền read đúng |
| 404 marker | Repository thiếu marker hoặc URL sai | Kiểm tra marker coordinates |
| 404 implementation | Marker đúng nhưng main module chưa publish | Publish implementation và marker |
| `publishPlugins` không tồn tại | Thiếu Plugin Publish Plugin | Kiểm tra `plugins` block |
| Portal từ chối ID | Namespace/ownership không đạt | Dùng plugin ID được phép |
| Portal từ chối metadata | Thiếu URL, description, tags, chức năng | Sửa metadata và docs |
| Portal chưa hiển thị sau upload | Review/approval/indexing chưa xong | Kiểm tra trạng thái Portal |
| Upload credential lỗi | Secret không inject/không còn quyền | Kiểm tra CI secret config mà không in secret |
| `publish` chạy nhưng consumer vẫn không thấy plugin | Sai repository, chưa có marker hoặc cache/proxy | Kiểm tra endpoint consumer thực sự truy cập |
| Portal plugin gây lỗi version | Plugin Publish Plugin và Gradle version không tương thích | Pin phiên bản được hỗ trợ |
| Local source mode pass, published mode fail | Publication metadata thiếu/sai | Test consumer từ Maven staging |
| Chỉ có POM mà không có `.module` | GMM không được publish/proxy chặn | Kiểm tra generation và Maven repository policy |
| Plugin Java test pass nhưng Portal validation fail | Portal yêu cầu metadata/policy bổ sung | Chạy `publishPlugins --validate-only` và đọc lỗi |
| Consumer load plugin nhưng `greet` không tồn tại | Plugin code/version khác hoặc task không đăng ký | Xem `tasks --all` và source |
| CI gửi token vào logs | Logging/command line sai | Rotate token, cải thiện secret handling |

### 18.1. Quy trình debug

1. Xác định plugin ID/version trong consumer.
2. Đọc `settings.pluginManagement.repositories` và URL/permissions.
3. Kiểm tra marker path theo `id:id.gradle.plugin:version`.
4. Đọc marker POM để biết implementation coordinates.
5. Kiểm tra main JAR/POM/GMM và dependencies.
6. Mở plugin JAR xem descriptor/class names.
7. Kiểm tra Gradle JVM/Java target compatibility.
8. Chạy `./gradlew greet --stacktrace --info`.
9. Với Proxy, kiểm tra đúng repository endpoint mà consumer sử dụng.
10. Nếu publication sai, sửa producer và phát hành version mới theo policy.

Đừng bắt đầu bằng xóa toàn bộ Gradle caches. `--refresh-dependencies` không tạo được marker chưa bao giờ được publish.

## 19. Plugin Publish Plugin version và metadata compatibility

Plugin Publish Plugin phiên bản 1.0+ dùng Maven publication và tự áp dụng Java Plugin Development/Maven Publish. Các hướng dẫn rất cũ dùng `pluginBundle` hoặc `mavenCoordinates` có thể không phù hợp với phiên bản mới.

Khi đọc ví dụ Internet:

- Kiểm tra **Plugin Publish Plugin version** mà tài liệu dùng.
- Kiểm tra **Gradle Wrapper version** được hỗ trợ.
- Ưu tiên các mẫu `gradlePlugin.website`, `gradlePlugin.vcsUrl`, `gradlePlugin.plugins` hiện đại.
- Không dùng `mavenCoordinates` của API cũ trong Plugin Publish Plugin 2.x.
- Khi dùng compatibility metadata 2.1+, làm theo extension/import và kiểm tra hỗ trợ thật.
- Không pin một version ngẫu nhiên chỉ vì khác bài viết có cùng cú pháp.

### 19.1. Version public và namespace

Plugin ID là một API tồn tại lâu. Trước khi công bố trên Portal, cần chắc chắn plugin ID được phép dùng, không giả mạo namespace của tổ chức khác và không gây nhầm lẫn với plugin đã tồn tại.

Đổi plugin ID có thể buộc mọi consumer sửa `plugins` DSL. Nếu cần đổi, phát hành và hướng dẫn migration rõ, không âm thầm dùng cùng implementation module với nhiều marker có ý nghĩa khác nhau.

### 19.2. Khi nào nên dùng một plugin project cho nhiều IDs?

Một producer có thể đăng ký:

```kotlin
gradlePlugin {
    plugins {
        create("greeting") {
            id = "dev.learning.greeting"
            implementationClass = "dev.learning.GreetingPlugin"
        }
        create("reporting") {
            id = "dev.learning.reporting"
            implementationClass = "dev.learning.ReportingPlugin"
        }
    }
}
```

Đây là **mảnh kiến trúc**, chỉ dùng khi `ReportingPlugin` được triển khai thật. Mỗi ID sẽ có marker riêng, có thể cùng trỏ về main implementation module theo model publishing. Nếu các plugin có release cycles, dependencies hoặc support matrix khác nhau đáng kể, tách project/module có thể dễ bảo trì hơn.

## 20. Bài tập thực hành

**Bài tập A — ánh xạ các định danh.** Với `dev.learning.greeting`, `dev.learning:greeting-plugin:1.0.0` và `dev.learning.greeting:dev.learning.greeting.gradle.plugin:1.0.0`, hãy giải thích vai trò mỗi tọa độ.

**Bài tập B — xây producer.** Tạo `plugin-producer` theo mục 5. Chạy `test`, `validatePlugins` và `jar`. Xác nhận JAR có plugin descriptor cùng hai Java classes.

**Bài tập C — publish private lab.** Chạy `publish`, kiểm tra `plugin-repo` có main JAR/POM/GMM và marker POM. Giải thích tại sao marker không giống implementation JAR.

**Bài tập D — chạy consumer.** Tạo `plugin-consumer`, sử dụng `plugins` DSL qua Maven repo. Chạy `greet` và xác nhận log `Hello from internal plugin!`.

**Bài tập E — thiếu marker.** Trong bản sao repository thử nghiệm, tạm bỏ marker POM rồi chạy consumer. Vì sao việc còn JAR không đủ?

**Bài tập F — explicit resolution.** Dùng `pluginManagement.resolutionStrategy` ánh xạ plugin ID vào implementation module, sau đó giải thích giới hạn với version thay đổi.

**Bài tập G — thiếu main module.** Trong repo thử nghiệm, giữ marker nhưng bỏ implementation JAR. Quan sát lỗi và giải thích việc marker không tự mang plugin classes.

**Bài tập H — đổi plugin ID.** Tạo version mới với plugin ID khác. Những phần của producer/consumer/marker sẽ cần thay đổi gì?

**Bài tập I — repository permissions.** Thiết kế private Maven repository có quyền read và write tách biệt, credentials cấp từ CI secret store.

**Bài tập J — plugin classpath.** Thêm một library vào implementation code của plugin. Vì sao phải khai báo dependency ở producer và bảo đảm consumer resolve được transitive module, không phải app `implementation`?

**Bài tập K — Portal validation.** Cấu hình metadata công khai trong môi trường được phép, chạy `publishPlugins --validate-only` rồi phân biệt với upload thật.

**Bài tập L — public hay private?** Một plugin áp dụng security policy bí mật cho repository công ty nên chọn kênh phát hành nào? Giải thích.

**Bài tập M — TestKit vs published mode.** Viết một test dùng `withPluginClasspath()` và một consumer test từ repository. Lỗi nào chỉ published-mode test mới phát hiện?

**Bài tập N — CI release.** Thiết kế PR job không có token và release job chỉ chạy sau approval; xác định chỗ upload thật xảy ra.

**Bài tập O — immutable version.** Sau khi phát hành `1.0.0`, thấy bug nhỏ. Vì sao nên xuất bản `1.0.1` thay vì overwrite `1.0.0`?

**Bài tập P — Gradle versions.** Dùng TestKit matrix để xác nhận plugin hoạt động trên versions được hỗ trợ. Vì sao không được quảng cáo compatibility khi chưa thử?

### Câu hỏi tự kiểm tra

1. Một Gradle plugin implementation có nhất thiết là một Java application có `main` không?
2. `Plugin<Project>.apply` được dùng lúc nào?
3. Plugin ID khác implementation Maven coordinates ra sao?
4. Plugin marker có convention group/artifact như thế nào?
5. Descriptor trong JAR chứa thông tin gì?
6. `java-gradle-plugin` và `maven-publish` phối hợp thế nào?
7. Publication `pluginMaven` khác marker publication ở điểm nào?
8. Vì sao `publish` không đồng nghĩa `publishPlugins`?
9. `pluginManagement.repositories` khác `repositories` project ở đâu?
10. Có thể dùng `plugins` DSL khi không có marker không, cần cơ chế nào?
11. Consumer TestKit với `withPluginClasspath` có kiểm tra repository upload không?
12. Vì sao nên kiểm thử consumer thật qua Maven repository staging?
13. Plugin Publish Plugin hiện đại tự áp dụng những plugin nền tảng nào?
14. `website`, `vcsUrl`, `description` và `tags` giúp ích gì trên Portal?
15. Credentials `GRADLE_PUBLISH_KEY`/`GRADLE_PUBLISH_SECRET` dùng khi nào?
16. `publishPlugins --validate-only` có upload công khai không?
17. Publish task thành công có đảm bảo Portal đã phê duyệt plugin chưa?
18. Vì sao không nên phát hành plugin nội bộ nhạy cảm lên Portal?
19. Plugin dependency trong producer có tự thành runtime dependency của Java app không?
20. Tại sao plugin code phải tương thích với JVM chạy Gradle?
21. Marker POM thiếu thì `--refresh-dependencies` có tự sửa được không?
22. Nếu repository proxy chặn file `.module`, cần kiểm tra những gì?
23. Version release bất biến giúp chống những lỗi cache nào?
24. Vì sao signing không thay thế source review và functional tests?
25. Khi nào dùng Gradle TestKit matrix?
26. Vì sao một plugin ID mới cần xét namespace/ownership?
27. Vì sao PR job không nên được cấp Portal publishing secrets?
28. Một plugin project đăng ký hai IDs có thể tạo bao nhiêu marker publications?
29. Vì sao không nên copy toàn bộ plugin implementation dependencies vào `app:implementation`?
30. Một plugin đã công bố cần duy trì documentation và migration policy thế nào?

## 21. Tài liệu chính thức

- [Gradle — Publishing Plugins to the Gradle Plugin Portal](https://docs.gradle.org/current/userguide/publishing_gradle_plugins.html)
- [Gradle Plugin Portal — How to Publish a Plugin](https://plugins.gradle.org/docs/publish-plugin)
- [Gradle — Preparing Plugins for Publication](https://docs.gradle.org/current/userguide/preparing_to_publish.html)
- [Gradle — Working with Plugins / Marker Artifacts](https://docs.gradle.org/current/userguide/plugins_intermediate.html)
- [Gradle — Plugin Development](https://docs.gradle.org/current/userguide/java_gradle_plugin.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle — Testing Plugins with TestKit](https://docs.gradle.org/current/userguide/test_kit.html)
- [Gradle Plugin Portal — Plugin Publish Plugin](https://plugins.gradle.org/plugin/com.gradle.plugin-publish)

**Ghi nhớ:** Khi công bố Gradle plugin, cần **implementation JAR/POM/GMM và plugin marker**, để consumer viết `plugins { id("...") version "..." }` và Gradle tìm được đúng implementation. Với plugin nội bộ, dùng `java-gradle-plugin` + `maven-publish` vào Maven repository có kiểm soát. Với plugin công khai, dùng `com.gradle.plugin-publish`, cung cấp metadata thật, credentials an toàn và tuân thủ xét duyệt của Portal. Kiểm thử **plugin thật từ repository đã publish** trước khi phát hành, không nhầm `publish` và `publishPlugins`.