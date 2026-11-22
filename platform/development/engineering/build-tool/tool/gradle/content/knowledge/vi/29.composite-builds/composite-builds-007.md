# Phạm vi riêng của settings, properties, catalog và repository giữa các build trong Gradle Composite Build

## 1. Composite build gồm nhiều build độc lập, không phải một multi-project khổng lồ

**Gradle composite build** là một build bao gồm một hoặc nhiều **included builds**. Mỗi included build có thể có `settings.gradle.kts`, `build.gradle.kts`, thư mục `gradle/`, `gradle.properties`, plugins, repositories, source sets, projects và task graph của chính nó. Build gốc có thể kết hợp các sản phẩm của included builds qua dependency substitution hoặc task references.

Điểm quan trọng nhất của bài này:

> **Included build được cấu hình độc lập.** Việc build A `includeBuild("B")` **không** khiến B mặc nhiên thừa hưởng settings, repositories, plugin management, version catalog hoặc user-defined project properties chỉ khai báo trong file `gradle.properties` của A.

Ngược lại, composite build vẫn có một số **ngữ cảnh chung của invocation**: Gradle Wrapper/phiên bản đang chạy, tham số dòng lệnh `-P` và `-D`, environment variables, Gradle User Home, một số runtime properties và hạ tầng cache. Cô lập **cấu hình build** không đồng nghĩa container sandbox/process isolation tuyệt đối.

### Tại sao cần hiểu ranh giới này?

Một developer có thể gặp:

- App dùng `libs.junit.jupiter` được nhưng included `build-logic` báo `Unresolved reference: libs` hoặc thiếu alias.
- Root khai báo `mavenCentral()`; included library không resolve được dependencies vì chưa có repository riêng.
- Root `gradle.properties` chứa `apiVersion=1.2`; included build đọc project property đó ra `null`.
- Root `pluginManagement.repositories` có internal plugin registry; included build vẫn báo `Plugin was not found`.
- Consumer đang yêu cầu `com.acme:library:1.0` nhưng Gradle lấy project trong included build thay vì file JAR trên Maven repository.
- Chạy build độc lập PASS, nhưng khi include vào composite thì kết quả khác do `-P`, system property, Gradle runtime flags, JDK hoặc substitutions.
- Người viết vô tình dùng `project(":library")` để tham chiếu module thuộc included build rồi gặp `UnknownProjectException`.

Bài học sẽ xây **hai Gradle builds thật, chạy Java 17 được** để quan sát settings/properties/catalog/repository của từng build, sau đó giải thích cách chia sẻ cấu hình **một cách tường minh** và cách chẩn đoán.

## 2. So sánh multi-project build với composite build

| Khía cạnh | Multi-project | Composite build |
| --- | --- | --- |
| Đưa thành phần vào build | `include(":lib")` | `includeBuild("lib-build")` |
| Thành phần được thêm | Subproject trong cùng build | Một **build độc lập**, có thể có nhiều subprojects |
| Settings | Cùng một settings hierarchy | Mỗi build có settings riêng |
| Project path dependency | `implementation(project(":lib"))` | **Không dùng** `project(":included-build:lib")` xuyên build |
| Dependency giữa hai build | Không áp dụng khái niệm “hai build” nếu cùng root | External coordinates + dependency substitution |
| Catalog mặc định | Chung trong một build (theo settings của nó) | **Mỗi build có catalog riêng** |
| Plugin/repository policy | Cấu hình cho projects của cùng build | **Không tự truyền** sang included builds |
| `gradle.properties` tại root | Thuộc root của build đó | File root build không tự truyền user properties sang included build |
| Task từ build khác | Không cần API included-build | `gradle.includedBuild("name").task(":task")` hoặc CLI qualified path |
| Dùng khi | Các modules phối hợp như một build | Nhiều builds muốn giữ khả năng phát triển độc lập |

### 2.1. `include` và `includeBuild` không thay thế nhau

~~~kotlin
// Cùng build, project hierarchy của settings hiện tại:
include(":app", ":domain")

// Toàn bộ một Gradle build riêng:
includeBuild("shared-lib")
~~~

`include(":domain")` cho phép module khác trong **cùng build** khai báo `implementation(project(":domain"))`.

`includeBuild("shared-lib")` đưa vào một build riêng, có root project và settings của nó. Consumer dùng dependency coordinates theo group/name của artifact mà included build cung cấp. Gradle có thể substitute external dependency bằng project local theo quy tắc đã xác lập.

### 2.2. Project path không xuyên ranh giới build

**Sai:**

~~~kotlin
dependencies {
    implementation(project(":shared-lib"))
}
~~~

nếu `shared-lib` chỉ tồn tại nhờ `includeBuild("shared-lib")`, không phải subproject được `include` trong settings hiện tại.

**Đúng theo mô hình composite:**

~~~kotlin
dependencies {
    implementation("org.example.training:shared-messages:1.0.0")
}
~~~

Khi included build có project với `group=org.example.training` và `name=shared-messages`, Gradle có thể thay external dependency này bằng local project của included build. Điều này khác với việc Maven repository bắt buộc phải có JAR đã publish. Chi tiết hoạt động và các giới hạn substitutions được trình bày ở phần sau.

## 3. Ma trận phạm vi: cái gì được chia sẻ, cái gì không?

| Thành phần | Root build → included build? | Ghi chú quan trọng |
| --- | --- | --- |
| Root `settings.gradle.kts` | **Không** | Included build tự đánh giá settings của nó |
| Root `pluginManagement { repositories }` | **Không** | Included build phải có plugin resolution policy riêng |
| Root `dependencyResolutionManagement.repositories` | **Không** | Repositories của included build phải được khai báo ở đúng build |
| Root `repositories` trong build scripts | **Không** | Không cấp repository mặc định cho included build |
| Root `repositoriesMode` | **Không** | Policies được áp dụng trong settings build tương ứng |
| Root `gradle/libs.versions.toml` | **Không tự động** | Catalog `libs` được tạo từ TOML của **mỗi build** |
| Root version catalog do settings khai báo | **Không tự động** | Included build phải import/publish cùng catalog một cách chủ đích |
| Root project `gradle.properties` với user-defined key | **Không** | Included build dùng file root của nó hoặc nguồn khác |
| Included build `gradle.properties` với user-defined key | **Không chảy ngược** | Root không tự thấy project property của included build |
| CLI `-Pkey=value` | **Có, trong composite invocation** | Project property truyền từ command line có thể đến các builds |
| CLI `-Dkey=value` | **Có, system property** | Hệ thống chung, không phải một Gradle project property |
| Environment variables | **Thường có**, theo môi trường tiến trình | Không phải cơ chế kế thừa settings; bảo vệ secrets |
| Gradle User Home | **Chung trong invocation** | Caches, global properties/init scripts có thể ảnh hưởng nhiều builds |
| Gradle runtime property `org.gradle.*` | **Thường invocation-wide** | Theo tài liệu composite, runtime flags chỉ đọc từ root build khi chạy composite |
| Source code và JAR output | **Không tự truy cập theo project path** | Cần dependency substitution, task ref hoặc artifact model |
| Task graph orchestration | **Có thể phối hợp** | Tasks của included builds có thể chạy để tạo dependency artifact |
| Build Cache | **Không đồng nghĩa config share** | Global cache có thể dùng chung nhưng Gradle vẫn tính input fingerprints |

**Quy tắc nhớ:** nếu đó là **configuration file của một build**, hãy giả định nó **chỉ thuộc build đó**, trừ khi tài liệu nêu cơ chế chia sẻ tường minh. Nếu đó là **invocation/runtime environment**, hãy kiểm tra phạm vi thực tế của command line, Gradle runtime và Gradle User Home.

## 4. Demo hoàn chỉnh: hai builds chạy cùng nhau nhưng giữ settings riêng

Demo gồm:

- **Root build `app-host`:** một Java CLI dùng Application plugin, cấu hình repository/catalog/properties của chính nó.
- **Included build `shared-lib`:** một Java library build độc lập tên project `shared-messages`, có catalog, repositories và properties riêng.
- **Composite link:** root `includeBuild("shared-lib")` và khai báo dependency bằng coordinates `org.example.training:shared-messages:1.0.0`.

Chúng ta có thể quan sát ba thứ:

1. App chạy được với Java class do included build compile mà không cần publish JAR.
2. `showScope` của mỗi build in giá trị property **khác nhau** từ file `gradle.properties` riêng.
3. Alias `libs.junit.jupiter` ở mỗi build có thể trỏ đến **phiên bản khác nhau** vì catalogs không tự đồng bộ.

### 4.1. Yêu cầu môi trường

- Có JDK **17+** hoặc toolchain Java 17 được Gradle phát hiện/provision theo cấu hình.
- Có Gradle Wrapper được tạo hợp lệ, tương thích JDK và những plugin được sử dụng.
- Maven Central/approved mirror có thể truy cập nếu chạy các JUnit tests trong demo.
- Không cần database, container, cloud credentials hay third-party runtime dependency để chạy Java Main.
- Chạy lệnh từ root `composite-lab`, trừ khi hướng dẫn chuyển directory để thử included build độc lập.

**Wrapper là file thật** gồm scripts và `gradle-wrapper.jar`/`gradle-wrapper.properties`; không thể thay bằng file script tên giống nhưng rỗng.

### 4.2. Cấu trúc thư mục

~~~text
composite-lab/
├── settings.gradle.kts                  # settings CỦA ROOT BUILD
├── build.gradle.kts                     # app-host root project
├── gradle.properties                    # root build project properties
├── gradle/
│   ├── libs.versions.toml               # root catalog
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── src/
│   ├── main/java/training/app/Main.java
│   └── test/java/training/app/MainTest.java
└── shared-lib/
    ├── settings.gradle.kts              # settings CỦA INCLUDED BUILD
    ├── build.gradle.kts                 # shared-messages project
    ├── gradle.properties                # included build properties
    ├── gradle/
    │   └── libs.versions.toml           # included catalog
    └── src/
        ├── main/java/training/lib/Greeting.java
        └── test/java/training/lib/GreetingTest.java
~~~

**Lưu ý:** `shared-lib` có settings file riêng nên nó là build riêng dù nằm bên trong directory root. Nó không được `include(":shared-lib")` như subproject. Khi chạy riêng, có thể đi vào directory `shared-lib` và gọi một Gradle Wrapper tương thích.

## 5. File root settings.gradle.kts

~~~kotlin
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "app-host"

includeBuild("shared-lib")
~~~

Giải thích:

- `pluginManagement.repositories` chọn nơi resolve **plugin requests** của root build.
- `dependencyResolutionManagement.repositories` chọn nơi resolve **library dependencies** của root build.
- `repositoriesMode = FAIL_ON_PROJECT_REPOS` cấm root project tự khai báo dependency repositories ở build script; đó là lựa chọn minh bạch, dễ audit.
- `rootProject.name = "app-host"` đặt tên root project của build hiện tại.
- `includeBuild("shared-lib")` kết hợp **build ở directory `shared-lib`**. Nó không biến `shared-lib` thành subproject của app-host.
- Relative path của `includeBuild` được resolve từ directory chứa settings file, không từ arbitrary workingDir của Java application.
- Các settings trên **không tự được áp dụng** vào `shared-lib/settings.gradle.kts`.

Bạn có thể thay Maven Central/Plugin Portal bằng repositories được tổ chức phê duyệt. Các repository URLs và credentials phải được cấu hình ở **đúng build** và theo security policy.

## 6. File shared-lib/settings.gradle.kts là độc lập

~~~kotlin
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "shared-messages"
~~~

**Không có `includeBuild` trong included build**, vì bản demo chỉ cần hai builds. Included project tên `shared-messages` trong khi directory của included build tên `shared-lib`. Hai tên phục vụ mục đích khác nhau:

- Directory/build path từ `shared-lib` giúp tham chiếu các tasks của included build trong composite.
- `rootProject.name = "shared-messages"` xác định **project name** mà default dependency substitution dùng cùng `group`.
- Application root tên `app-host` không tự có quyền can thiệp vào `rootProject.name` của included build.

Dù hai settings files gần giống nhau, chúng là **hai cấu hình tách biệt**. Nếu root bỏ `mavenCentral()` nhưng included giữ, included có thể vẫn resolve dependency của nó. Nếu included bỏ `mavenCentral()` mà root giữ, các test dependencies của included có thể fail vì chúng không tự dùng repo của root.

### 6.1. Tại sao cần lặp repositories?

Không phải vì Gradle yêu cầu copy/paste mọi file, mà vì **mỗi build có repository policy riêng**. Khi nhiều builds cùng tuân chính sách công ty, hãy chia sẻ policy qua settings plugin/init policy được kiểm soát, hoặc khai báo cụ thể trong mỗi settings. Đừng giả định root settings “bao trùm” mọi included builds.

### 6.2. Tại sao `pluginManagement` khác `dependencyResolutionManagement`?

Một plugin như `com.example.build-policy` trong `plugins { ... }` được resolve theo plugin repositories. Một library như `org.junit.jupiter:junit-jupiter` trong `dependencies { ... }` được resolve theo dependency repositories.

Khai báo `mavenCentral()` trong `dependencyResolutionManagement` không tự giải quyết mọi plugin request. Ngược lại, `gradlePluginPortal()` trong `pluginManagement` không tự thay thế tất cả dependency repositories. Nên đặt rõ hai nhóm ở settings của **từng build**.

## 7. Mỗi build có version catalog của chính nó

Gradle tự nạp file `gradle/libs.versions.toml` trong **root directory của mỗi build**, tạo accessor `libs` cho project/build scripts thuộc build tương ứng.

**Root file `composite-lab/gradle/libs.versions.toml`:**

~~~toml
[versions]
junit = "5.11.4"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
junit-launcher = { module = "org.junit.platform:junit-platform-launcher", version = "1.11.4" }
~~~

**Included file `composite-lab/shared-lib/gradle/libs.versions.toml`:**

~~~toml
[versions]
junit = "5.10.2"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
junit-launcher = { module = "org.junit.platform:junit-platform-launcher", version = "1.10.2" }
~~~

Hai builds đều có alias `libs.junit.jupiter` và `libs.junit.launcher`, nhưng **giá trị/version khác**. Đó là chủ ý của demo để thấy catalogs độc lập:

| Build | Accessor | Nội dung |
| --- | --- | --- |
| app-host | `libs.junit.jupiter` | `org.junit.jupiter:junit-jupiter:5.11.4` |
| shared-messages | `libs.junit.jupiter` | `org.junit.jupiter:junit-jupiter:5.10.2` |
| app-host | `libs.junit.launcher` | `org.junit.platform:junit-platform-launcher:1.11.4` |
| shared-messages | `libs.junit.launcher` | `org.junit.platform:junit-platform-launcher:1.10.2` |

Đây là **hai catalogs**, không phải hai scopes của cùng một catalog. Đổi version trong root TOML **không** đổi included TOML; Gradle không copy aliases tự động sang included build.

### 7.1. Version catalog là dependency notation, không phải version lock

Alias `libs.junit.jupiter` hỗ trợ khai báo version tập trung **trong một build**, nhưng bản thân catalog không giống dependency locking hay enforced platform. Khi có nhiều dependency constraints/version conflicts, resolved version còn phụ thuộc Gradle resolution rules. Vì vậy đừng suy chỉ từ alias mà biết chắc toàn bộ runtime graph; dùng `dependencies`/`dependencyInsight` và lockfiles/verification metadata theo nhu cầu.

### 7.2. Catalog aliases không đi qua Java dependency substitution

Root app dùng catalog `libs.junit.jupiter` cho **test dependency riêng**. Khi phụ thuộc included project, app dùng coordinates `org.example.training:shared-messages:1.0.0`; included library dùng catalog của nó cho **chính tests của nó**. Root catalog không được “bơm” vào included build chỉ vì app consumer phụ thuộc library.

## 8. Mỗi build có user-defined properties riêng

**Root `composite-lab/gradle.properties`:**

~~~properties
scopeMessage=ROOT_FILE
~~~

**Included `composite-lab/shared-lib/gradle.properties`:**

~~~properties
scopeMessage=INCLUDED_FILE
~~~

`scopeMessage` là một **user-defined Gradle project property** để minh họa. Khi không có CLI/Gradle User Home overrides, app-host đọc giá trị `ROOT_FILE`; included shared-messages đọc `INCLUDED_FILE`.

Đây là điểm quan trọng nhất về `gradle.properties` trong composite: **file root của bao gồm build không tự truyền custom project properties sang included build**. Và file included không tự truyền ngược giá trị sang root.

### 8.1. Lỗi rất thường gặp

Root có:

~~~properties
serviceEndpoint=https://example.invalid
~~~

Developer trong included build viết:

~~~kotlin
val endpoint = providers.gradleProperty("serviceEndpoint")
~~~

rồi tưởng sẽ nhận giá trị root. Theo isolation của composite, custom property trong root `gradle.properties` không được tự động kế thừa. Nếu muốn property đó được truyền, hãy dùng cơ chế rõ ràng: cấu hình riêng trong included build, CLI `-P` (cùng invocation), environment variable/credentials provider, hoặc convention/settings plugin phù hợp.

**Không** copy secrets/credentials thẳng vào source-controlled `gradle.properties` chỉ để đạt “chia sẻ”. Với repository credentials, dùng secret manager, CI environment hoặc Gradle User Home credentials có quyền hạn thích hợp và kiểm soát log.

## 9. Root build.gradle.kts: app và scope diagnostic task

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
}

group = "org.example.training"
version = "1.0.0"

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
    implementation("org.example.training:shared-messages:1.0.0")

    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.launcher)
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set("training.app.Main")
}

// Đọc property của ROOT build trong configuration phase,
// lưu thành String để không truy cập Project trong task action.
val rootScopeMessage =
    providers.gradleProperty("scopeMessage").getOrElse("<unset>")

tasks.register("showScope") {
    group = "help"
    description = "Print the property seen by app-host"

    doLast {
        println("app-host scopeMessage=" + rootScopeMessage)
    }
}
~~~

**Giải thích:**

- `application` tạo Java/application tasks như `run` và `test` (qua Java plugin).
- `implementation("org.example.training:shared-messages:1.0.0")` là **external dependency notation**, được Gradle composite substitution thay bằng included project.
- `testImplementation(libs.junit.jupiter)` là alias **root** catalog, version 5.11.4.
- `testRuntimeOnly(libs.junit.launcher)` nhận launcher theo root catalog.
- Java toolchain và `options.release` chọn Java 17 compile target.
- `showScope` lấy `scopeMessage` thuộc project root tại configuration phase rồi in string. Không đọc shared-lib file hay gọi shell để lấy một root property.
- Không khai báo `repositories` ở file này: root settings đã đặt `FAIL_ON_PROJECT_REPOS` và khai báo repo ở `dependencyResolutionManagement`.

Lệnh `./gradlew run` tự compile included library cần thiết qua project dependency substitution. Không cần developer chạy Maven publish hoặc copy JAR thủ công.

## 10. Included shared-lib/build.gradle.kts: thư viện độc lập

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    `java-library`
}

group = "org.example.training"
version = "1.0.0"

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
    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.launcher)
}

tasks.test {
    useJUnitPlatform()
}

val includedScopeMessage =
    providers.gradleProperty("scopeMessage").getOrElse("<unset>")

tasks.register("showScope") {
    group = "help"
    description = "Print the property seen by shared-messages"

    doLast {
        println("shared-messages scopeMessage=" + includedScopeMessage)
    }
}
~~~

Điểm cần quan sát:

- `group="org.example.training"` và `rootProject.name="shared-messages"` xác định group:name của project được included build cung cấp.
- `version="1.0.0"` là version của library; default composite substitution chủ yếu nhận diện bằng **group:name**, nên kiểm tra compatibility nếu caller yêu cầu version khác.
- `java-library` phù hợp vì đây là reusable Java library, không có main method.
- `libs.junit.jupiter` tại đây lấy **included catalog 5.10.2**, không phải root catalog.
- `providers.gradleProperty("scopeMessage")` đọc property trong phạm vi build included và các nguồn property chung thích hợp, không tự lấy root `gradle.properties`.
- Included settings đã khai báo Maven Central/plugin repositories của chính nó.
- Task `showScope` ở đây độc lập với `showScope` của root, dù trùng task name.

## 11. Mã Java 17 chạy được

**Included file `shared-lib/src/main/java/training/lib/Greeting.java`:**

~~~java
package training.lib;

public final class Greeting {
    private Greeting() {
    }

    public static String messageFor(String name) {
        return "Hello, " + name + " from composite!";
    }
}
~~~

**Root file `src/main/java/training/app/Main.java`:**

~~~java
package training.app;

import training.lib.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Gradle";
        System.out.println(Greeting.messageFor(name));
    }
}
~~~

Application class chỉ sử dụng public API của included library. Library không biết app.

### 11.1. Chạy từ composite root

Linux/macOS:

~~~bash
./gradlew -q run --args="Ada"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q run --args="Ada"
~~~

**Dòng stdout chính xác từ Java Main:**

~~~text
Hello, Ada from composite!
~~~

Không truyền arguments:

~~~bash
./gradlew -q run
~~~

**Dòng từ Java Main:**

~~~text
Hello, Gradle from composite!
~~~

Gradle `-q` hạn chế build logging nhưng tùy môi trường/JDK còn có thể có warnings. Hai kết quả trên mô tả riêng stdout của Java Main.

### 11.2. Lệnh chẩn đoán cấu hình build

~~~bash
./gradlew showScope
./gradlew :shared-lib:showScope
~~~

Hai dòng quan trọng do các task in:

~~~text
app-host scopeMessage=ROOT_FILE
shared-messages scopeMessage=INCLUDED_FILE
~~~

Đây là output **trong hai lần gọi khác nhau**, không phải toàn bộ Gradle console log. Tên build path `shared-lib` bắt nguồn từ tên directory included build theo cấu trúc demo. Trong một composite lớn có custom build path, cần dùng chính xác included build path hiện có.

### 11.3. Cùng một invocation gọi cả hai tasks

~~~bash
./gradlew showScope :shared-lib:showScope --console=plain
~~~

Kết quả quan trọng:

~~~text
app-host scopeMessage=ROOT_FILE
shared-messages scopeMessage=INCLUDED_FILE
~~~

Thứ tự tasks/logs có thể khác trong một graph phức tạp; điều quan trọng là **hai project properties tách biệt**.

### 11.4. Override tường minh qua CLI -P

~~~bash
./gradlew -PscopeMessage=CLI_VALUE \
    showScope :shared-lib:showScope
~~~

Trong PowerShell, có thể dùng một dòng:

~~~powershell
.\gradlew.bat -PscopeMessage=CLI_VALUE showScope :shared-lib:showScope
~~~

Hai giá trị in từ tasks:

~~~text
app-host scopeMessage=CLI_VALUE
shared-messages scopeMessage=CLI_VALUE
~~~

**Tại sao?** Gradle CLI project properties được truyền theo invocation composite, khác với việc root build chỉ có một custom key trong file `gradle.properties`. Không suy rộng rằng root file đã được copy; source là **command-line argument**. Cũng không dùng `-Ppassword=...` trong CI logs hay shell history để phân phối secret.

## 12. Thêm tests để chứng minh mỗi catalog dùng trong build riêng

Hai tests là tùy chọn đối với `run`, nhưng chúng giúp kiểm tra Maven dependency resolution và catalog scopes.

**Root `src/test/java/training/app/MainTest.java`:**

~~~java
package training.app;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import training.lib.Greeting;

class MainTest {
    @Test
    void usesIncludedLibrary() {
        assertEquals(
            "Hello, Ada from composite!",
            Greeting.messageFor("Ada")
        );
    }
}
~~~

**Included `shared-lib/src/test/java/training/lib/GreetingTest.java`:**

~~~java
package training.lib;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void createsMessage() {
        assertEquals(
            "Hello, Gradle from composite!",
            Greeting.messageFor("Gradle")
        );
    }
}
~~~

Lệnh:

~~~bash
./gradlew test
./gradlew :shared-lib:test
~~~

- `./gradlew test` chạy **test task của root app-host**, không có nghĩa nó tự chạy tất cả tests của mọi included build.
- `./gradlew :shared-lib:test` chạy **test task của included build**.
- Root Test task resolve `libs.junit.jupiter` từ root catalog (5.11.4).
- Included Test task resolve alias từ included catalog (5.10.2).
- Gradle có thể cần download dependencies/JUnit runtime từ Maven Central hoặc mirror riêng đã được cấu hình ở từng settings.
- Không có stdout cố định từ test methods vì chúng chỉ assert; console Gradle có thể hiện UP-TO-DATE hoặc BUILD SUCCESSFUL theo lần chạy.
- Nếu JUnit tests báo `NO-SOURCE`, kiểm tra file path/class/method annotations thay vì coi kết quả là đủ test coverage.

### 12.1. Kiểm tra các graph khác nhau

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew :shared-lib:dependencies --configuration testRuntimeClasspath
~~~

Ở root, quan sát JUnit 5.11.4; ở included build, quan sát 5.10.2. Những graph cụ thể có thể chứa transitive modules/BOM platform constraints và format khác theo Gradle version. Không mặc định rằng cùng một catalog alias ở hai builds luôn resolve cùng một version.

## 13. Compile Java trực tiếp bằng javac/java: giải thích ranh giới

Nếu muốn kiểm tra Java source mà chưa kết nối Gradle hoặc Maven:

Linux/macOS, từ `composite-lab`:

~~~bash
mkdir -p out/lib out/app

javac --release 17 -encoding UTF-8 \
    -d out/lib \
    shared-lib/src/main/java/training/lib/Greeting.java

javac --release 17 -encoding UTF-8 \
    -cp out/lib \
    -d out/app \
    src/main/java/training/app/Main.java

java -cp out/app:out/lib training.app.Main Ada
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out\lib,out\app | Out-Null

javac --release 17 -encoding UTF-8 -d out\lib shared-lib\src\main\java\training\lib\Greeting.java

javac --release 17 -encoding UTF-8 -cp out\lib -d out\app src\main\java\training\app\Main.java

java -cp "out\app;out\lib" training.app.Main Ada
~~~

**Stdout chính xác:**

~~~text
Hello, Ada from composite!
~~~

Cách chạy này **không kiểm thử Gradle composite substitution**, catalogs, repositories hay properties. Nó chứng minh mã Java và compile/runtime classpath hợp lệ khi được ghép đúng. Gradle thay bạn quản lý những bước biên dịch/phụ thuộc đó thông qua dependency graph.

## 14. Vì sao default dependency substitution hoạt động?

Trong root build:

~~~kotlin
dependencies {
    implementation("org.example.training:shared-messages:1.0.0")
}
~~~

Trong included build:

~~~kotlin
group = "org.example.training"
version = "1.0.0"
~~~

và `shared-lib/settings.gradle.kts` đặt:

~~~kotlin
rootProject.name = "shared-messages"
~~~

Theo cơ chế composite mặc định, Gradle cấu hình included build, xác định group:name mà project cung cấp và thay một external dependency matching **group:name** thành dependency tới project local. Bạn không cần publish `shared-messages-1.0.0.jar` lên Maven Central cho ví dụ.

### 14.1. Một điểm rất dễ hiểu sai: requested version

Default substitution chủ yếu dựa trên **group:name** của included project. Vì vậy nếu consumer yêu cầu một version khác version local, Gradle **vẫn có thể substitute** project local tùy rules. Không được xem requested version trong dependency notation là một biện pháp pin nguồn binary từ registry khi composite đang bật.

Nếu mục tiêu là kiểm thử against **published binary**, cần quản lý substitution scopes hoặc chạy consumer ở môi trường **không include** build đó. Đừng dựa vào việc sửa version trong `implementation("g:a:v")` rồi mong Gradle tự từ chối local source.

### 14.2. Khi default coordinates không khớp

Có thể cấu hình substitution tường minh ở root settings:

~~~kotlin
includeBuild("shared-lib") {
    dependencySubstitution {
        substitute(module("org.example.training:message-api"))
            .using(project(":"))
    }
}
~~~

**Đây là snippet thay thế** cho dòng `includeBuild("shared-lib")` ở demo, không nên paste thêm vào settings đã có includeBuild cùng đường dẫn. Nó ánh xạ external coordinate `org.example.training:message-api` tới root project `:` của included build. Consumer khi đó phải yêu cầu alias coordinate `org.example.training:message-api:someVersion`.

Với demo gốc group/name đã khớp, **không cần** substitution tường minh. Khi dùng custom publications, classifiers, capabilities hoặc tailored variants, cần đọc kỹ giới hạn composite substitution — project default configuration không phải lúc nào cũng giống published Maven POM/module metadata.

### 14.3. Đừng khai báo project dependency xuyên builds

Không dùng:

~~~kotlin
dependencies {
    implementation(project(":shared-lib"))
    implementation(project(":shared-lib:shared-messages"))
}
~~~

Trừ khi các paths đó thực sự tồn tại là **subprojects của cùng root build** (không phải trường hợp demo), chúng không hợp lệ. Included build có **project hierarchy độc lập**.

## 15. Task orchestration xuyên build: API nào dùng được?

Nếu muốn root task chạy một task của included build mà không có Java artifact dependency, dùng Gradle included-build task reference:

~~~kotlin
tasks.register("checkIncludedBuild") {
    group = "verification"
    dependsOn(
        gradle.includedBuild("shared-lib").task(":test")
    )
}
~~~

Snippet bổ sung vào **root `build.gradle.kts`**. Khi gọi:

~~~bash
./gradlew checkIncludedBuild
~~~

Gradle đưa task `:test` của included build vào graph. Điều này **khác** với việc giả định root `test` tự chạy mọi test suites trong included build.

Từ CLI cũng có thể gọi:

~~~bash
./gradlew :shared-lib:test
./gradlew :shared-lib:showScope
~~~

**Cần phân biệt:**

- `gradle.includedBuild("shared-lib").task(":test")` là một **task reference** dành cho orchestration.
- `implementation("org.example.training:shared-messages:1.0.0")` là **dependency declaration** dùng cho classpath/artifact.
- `project(":test")` không phải API tham chiếu included task.
- Khi một build có subprojects, task path trong included build là `:subproject:task` theo hierarchy nội bộ của nó.

### 15.1. Không tự nối mọi lifecycle task

Một `checkIncludedBuild` tường minh có ích trong CI, nhưng đừng tự gắn tất cả included tasks vào root `build` nếu không có nhu cầu. Điều đó làm root build chậm và phá khả năng phát triển included build độc lập. Hãy xác định quality gate theo kiến trúc: app tests, library tests, contract tests, packaging và deploy là các bước có phạm vi khác nhau.

## 16. Repositories thuộc về settings của từng build

Ba nhóm repository thường bị nhầm:

1. **Plugin repositories:** phục vụ `plugins { id(...) version(...) }`.
2. **Dependency repositories:** phục vụ libraries như JUnit, Guava, HTTP client.
3. **Publishing repositories:** nơi upload Maven artifacts, khác với nơi Gradle resolve.

### 16.1. Plugin repositories

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}
~~~

Đoạn này trong **root settings** không tự cấu hình Plugin Portal cho included settings. Nếu included build cần plugin từ internal plugin registry, phải có resolution policy đúng trong settings của included build hoặc dùng shared settings plugin/convention được thiết kế cho phạm vi đó.

### 16.2. Dependency repositories

~~~kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
~~~

Đoạn này chỉ quản lý repositories của **build có settings file đó**. Nếu included build chưa có nơi chứa dependency, không thể mong root `mavenCentral()` “cứu” nó.

Ngoài `FAIL_ON_PROJECT_REPOS` còn có `PREFER_SETTINGS` và `PREFER_PROJECT` với cách xử lý khác. Để có policy minh bạch/audit chặt chẽ, `FAIL_ON_PROJECT_REPOS` phù hợp nhưng phải bảo đảm **mỗi build** đặt đúng repositories tại settings.

### 16.3. Publishing không tự chia sẻ credentials

Nếu library included có task `publish`, publishing repository/credentials do **included build** cấu hình. Root có Maven publish credentials không tự truyền như một thuộc tính project-local chỉ vì build được include.

Nếu tổ chức muốn dùng chung repository credentials, dùng **approved credential providers/CI secrets/settings plugin** hoặc nguồn invocation-wide phù hợp và cấp quyền tối thiểu. Không hardcode token trong TOML, build scripts hay logs.

### 16.4. Vì sao plugin resolution và dependency resolution lỗi khác nhau?

| Triệu chứng | Nguyên nhân thường gặp |
| --- | --- |
| `Plugin ... was not found` | `pluginManagement.repositories` thiếu plugin marker/repository |
| `Could not resolve ...` trong `testRuntimeClasspath` | Dependency repository thiếu module/metadata |
| `401 Unauthorized` | Credentials không có/hết hạn/sai quyền |
| `PKIX path building failed` | TLS CA/certificate/trust chain |
| `Could not find org...` chỉ ở included build | Repository policy included không trùng root |
| `Cannot add a repository ... FAIL_ON_PROJECT_REPOS` | Repo được thêm ở project trái policy của settings build đó |

Không “sửa” lỗi Plugin Portal bằng cách thêm `mavenCentral()` trong `dependencies`, và ngược lại. Xem **config phase** và tên configuration/URL đang được resolve.

## 17. Cách chia sẻ version catalog có chủ đích

Nếu muốn cùng một TOML dùng ở nhiều builds, Gradle hỗ trợ import bằng `versionCatalogs.create(...).from(files(...))`. Nhưng cần cấu hình **từng build**, không có kế thừa tự động.

Ví dụ một monorepo có shared catalog ở root:

~~~text
composite-lab/
├── gradle/libs.versions.toml
└── shared-lib/
    └── settings.gradle.kts
~~~

Giả sử **đã bỏ file `shared-lib/gradle/libs.versions.toml` riêng** để tránh tự tạo catalog `libs` trùng tên. Trong `shared-lib/settings.gradle.kts` có thể thêm vào `dependencyResolutionManagement` sẵn có:

~~~kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}
~~~

**Đây là một phương án THAY THẾ** cho cấu hình included settings/catalog của demo, không dùng đồng thời với file catalog local `shared-lib/gradle/libs.versions.toml` đang tự được import dưới cùng tên. `from(files(...))` phải chỉ tới **một file TOML** phù hợp.

Giờ included build sử dụng **nội dung root TOML được import tường minh**. Đây là sharing có chủ đích qua file path, **không phải** composite tự chuyển catalog.

### 17.1. Tên catalog khác để tránh collision

Nếu muốn giữ catalog `libs` riêng cho included build, có thể import shared catalog dưới tên khác như `sharedLibs`, sau đó gọi accessor `sharedLibs.xxx` trong build script. Việc dùng nhiều catalogs tạo thêm trách nhiệm quản lý alias naming và version convergence; chỉ làm khi có boundary thật sự.

### 17.2. Catalog phát hành riêng

Khi builds nằm ở những repositories độc lập, hardcode `../gradle/libs.versions.toml` có thể làm included build không còn standalone. Gradle hỗ trợ publish catalog qua `version-catalog` plugin thành Maven/Ivy artifact hoặc dùng settings plugin để khai báo policy chung. Chọn giải pháp phù hợp mức độ độc lập và ownership.

### 17.3. Đặc biệt với build-logic/buildSrc

`build-logic` và `buildSrc` là những builds có môi trường resolution riêng; đừng nghĩ chúng nhìn thấy root `libs` accessor mặc định. Có thể import root TOML tường minh vào settings của build-logic hoặc công bố shared catalog. Đối với convention plugins, plugin dependency versions có thể cần khai báo khác với các library aliases của app.

### 17.4. Một catalog không có TOML include tùy ý

Gradle TOML version catalogs không có cơ chế `include` trong file để tự nhập một catalog khác. `from(...)` chỉ được gọi **một lần** cho một catalog import. Không ghép nhiều TOML files vào cùng `libs` rồi mong Gradle tự merge. Nếu cần override/extend, dùng VersionCatalogBuilder APIs hoặc một policy rõ ràng.

## 18. gradle.properties: phân biệt custom project properties và Gradle runtime flags

Với composite builds, Gradle docs tách hai lớp:

**Lớp A — Custom/user-defined project properties:**

~~~properties
scopeMessage=ROOT_FILE
businessRegion=local
~~~

Khi ở **root project gradle.properties**, các keys này không tự chảy sang included build. Included có thể có giá trị của chính nó.

**Lớp B — Gradle runtime properties:**

~~~properties
org.gradle.configuration-cache=true
org.gradle.parallel=true
org.gradle.jvmargs=-Xmx2g
~~~

Trong **composite invocation**, những runtime properties này được xem xét từ **root build** để điều khiển cả invocation; theo tài liệu Gradle composite, khai báo tương tự trong `gradle.properties` của included build **không điều khiển invocation đang chạy từ root**.

Đừng suy “mỗi included build có một Gradle Daemon/JVM cache riêng” chỉ vì settings riêng. Mỗi included build có project/settings configuration isolation, nhưng CLI và Gradle runtime context vẫn có các cơ chế chung.

### 18.1. Khi chạy included build độc lập thì sao?

Nếu bạn đổi working directory sang `shared-lib` và chạy một Gradle invocation lấy `shared-lib/settings.gradle.kts` làm root settings, lúc đó **shared-lib là root build của invocation mới**. Những `org.gradle.*` runtime properties tại `shared-lib/gradle.properties` có thể được áp dụng theo quy tắc thông thường cho root build đó. Vì thế cùng file có thể bị bỏ qua như “included runtime config” khi gọi từ composite root nhưng có hiệu lực lúc chạy standalone.

### 18.2. CLI -P / -D khác file properties riêng

Chạy:

~~~bash
./gradlew -PscopeMessage=CLI_VALUE showScope :shared-lib:showScope
~~~

cấp project property ở invocation; cả hai builds có thể đọc giá trị này. Còn `-DmyKey=value` đặt **Java system property** cho Gradle process, dùng `providers.systemProperty("myKey")` hoặc API tương ứng; nó không tự trở thành `providers.gradleProperty("myKey")`.

**Không nhầm:**

- `providers.gradleProperty("scopeMessage")`: Gradle project property.
- `providers.systemProperty("scopeMessage")`: Java system property.
- `providers.environmentVariable("SCOPE_MESSAGE")`: environment variable.
- `applicationDefaultJvmArgs`: JVM arguments cho **ứng dụng Java**, không tự là project property của included build.

### 18.3. Property precedence có nhiều nguồn

Gradle có project properties từ CLI, file `gradle.properties` ở các scope hợp lệ, Gradle User Home hoặc environment variables dạng `ORG_GRADLE_PROJECT_...` theo quy tắc precedence. Vì vậy khi quan sát một giá trị không như dự kiến, đừng chỉ mở một file rồi kết luận. Kiểm tra nguồn CLI/system/env/global và chính sách priority của Gradle version đang dùng.

Trong demo không đặt cùng key ở Gradle User Home và không truyền `-P` trừ khi thực hiện thí nghiệm override, nên hai kết quả `ROOT_FILE`/`INCLUDED_FILE` có thể dự đoán.

## 19. Gradle User Home và environment: không phải sandbox riêng

Gradle User Home mặc định thường là `~/.gradle` (Windows thường trong profile user). Biến môi trường `GRADLE_USER_HOME` có thể thay directory. Nó chứa các loại dữ liệu như:

- Gradle distributions/Wrapper cache.
- Dependency cache, metadata, transformed artifacts.
- Gradle Daemon state/logs.
- Global `gradle.properties`.
- Global init scripts và toolchains downloaded (theo cấu hình).
- Gradle cache directories phục vụ các invocations.

Khi root và included builds chạy **trong cùng invocation và Gradle User Home**, chúng có thể dùng chung caches và bị ảnh hưởng bởi global properties/init scripts. Nhưng các settings/plugin/catalog files riêng vẫn không trở thành cùng một file.

### 19.1. Để kiểm tra môi trường sạch có thể dùng

Linux/macOS:

~~~bash
GRADLE_USER_HOME="$PWD/.gradle-test-home" ./gradlew test
~~~

Windows PowerShell:

~~~powershell
$env:GRADLE_USER_HOME = (Join-Path (Get-Location) ".gradle-test-home")
.\gradlew.bat test
~~~

Đây là **thí nghiệm tùy chọn** để dùng một Gradle User Home khác, có thể khiến Gradle download dependencies/JDK Wrapper lại. Directory `.gradle-test-home` nằm trong workspace và nên được ignore khỏi Git, xóa có kiểm soát sau thí nghiệm. Không xóa toàn bộ `~/.gradle` của người khác.

### 19.2. Môi trường chung không có nghĩa credentials được quyền dùng chung

Một CI runner có thể cấp `REGISTRY_TOKEN` cho cả root/included build qua environment. Điều đó không bảo đảm mọi task được phép upload/publish. Thiết kế secret scopes cần tương ứng repositories/task ownership và least privilege, không log token.

### 19.3. Init scripts là ngoại lệ cần chú ý

Gradle init scripts từ invocation hoặc Gradle User Home có thể cấu hình một hoặc nhiều builds theo hooks mà script sử dụng. Vì vậy nếu repository behavior thay đổi bất ngờ, xem cả init scripts/company Gradle distributions, không chỉ settings. Đây là **cơ chế dùng chung có chủ đích** chứ không phải root settings tự được kế thừa.

## 20. Plugin resolution và build-logic: trường hợp đặc biệt

Composite builds thường dùng `build-logic` để chia sẻ convention plugins, ví dụ toolchain, compiler flags và test policy. Tuy nhiên, **plugin build cũng có settings/catalog/repositories riêng**.

Ví dụ layout:

~~~text
composite-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── build-logic/
    ├── settings.gradle.kts
    └── build.gradle.kts
~~~

Để sử dụng plugin do included build cung cấp qua `plugins { ... }`, root settings có thể cấu hình:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
    repositories {
        gradlePluginPortal()
    }
}
~~~

Đây là **snippet phương án khác**, không áp dụng trực tiếp vào demo nếu `build-logic` chưa có project/plugin thật. Nó biểu diễn include build vào plugin resolution context. Build-logic phải tự cấu hình dependencies/plugins của chính nó và công bố plugin IDs hợp lệ.

Nếu một **settings plugin** cần được áp dụng trong settings `plugins { id("...") }`, `includeBuild` trong `pluginManagement` của settings là cơ chế quan trọng. Với plugin dùng trong project build scripts, cũng nên xác định plugin resolution bằng settings thay vì hy vọng CLI `--include-build` luôn xử lý plugin unpublished qua `plugins` DSL.

### 20.1. Không tự truyền pluginManagement sang included consumers

Nếu root `pluginManagement.includeBuild("build-logic")`, included build `shared-lib` không mặc nhiên nhìn thấy mọi plugin ID hoặc repository của root trong namespace settings riêng. Với mỗi build cần plugin, phải có **resolution strategy rõ ràng**, qua plugin repository hoặc included plugin build phù hợp (chú ý tránh duplicate included-build path/cycle). Kiểm tra chính build độc lập thay vì assume root policy.

### 20.2. Convention plugin không làm mất isolation

Convention plugin có thể tái sử dụng **logic** (ví dụ Java toolchain, test task policy, repository configuration qua settings plugin), nhưng từng build vẫn **tự chọn áp dụng** theo contract. Nó không làm root settings tự trở thành settings của included build. Đây là lý do recommended `build-logic` khác với hack `subprojects { ... }` được áp từ root.

## 21. Cách chia sẻ repository/security policy mà vẫn rõ scope

Tổ chức lớn không muốn duy trì 20 bản copy repository URL ở 20 builds. Một số lựa chọn:

1. **Settings plugin đã publish:** từng build áp dụng cùng settings plugin để thiết lập `pluginManagement`/`dependencyResolutionManagement` theo API phù hợp.
2. **Convention build logic:** chia sẻ cách cấu hình project tasks/dependencies; nhưng lưu ý repository setup ở settings cần plugin/hook đúng lifecycle.
3. **Init scripts theo tổ chức/CI:** đặt policy và credentials theo máy/CI, cần kiểm soát nguồn script và quyền.
4. **Repository mirror/Artifactory/Nexus:** mọi builds tham chiếu endpoint chuẩn, nhưng vẫn cần cấu hình endpoint tại build scope.
5. **Version catalog phát hành:** đồng bộ aliases/versions qua artifact chung, không đồng nghĩa repositories tự được cấu hình.
6. **Gradle User Home credentials:** giảm copy secrets vào repositories, nhưng phải tuân access policy.

### 21.1. Ưu tiên least privilege

Đối với internal repo:

- Dùng read-only credentials cho dependency resolution.
- Không cấp publish credentials cho mọi developer hoặc tất cả included builds.
- Không in token trong `println`/`--info` logs.
- Dùng secure credential APIs/provider pattern và CI secret storage.
- Chỉ cho phép trusted repository endpoints với checksum/dependency verification khi cần.
- Xem việc root và included dùng chung Gradle User Home như **shared trust context**, không phải separation boundary.

### 21.2. FAIL_ON_PROJECT_REPOS theo từng build

Một included build có thể có:

~~~kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
~~~

và nó sẽ chặn project repositories **trong included build đó**. Root có cùng mode không chứng minh included cũng được khóa. Nếu muốn enforce across company builds, mỗi build phải nhận settings policy bằng con đường được kiểm soát.

## 22. Tình huống so sánh: root có repo nhưng included không có

Giả sử root settings có:

~~~kotlin
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

Còn included settings chỉ có:

~~~kotlin
rootProject.name = "shared-messages"
~~~

Khi included test `testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")` cần resolve mà included project **không** cấu hình repositories ở nơi nào khác, có thể gặp lỗi **no repositories are defined** hoặc không tìm thấy artifact. Root Maven Central **không tự được kế thừa**.

Cách sửa đúng: khai báo repository cho **included build** thông qua settings/project configuration hợp lệ theo policy. Đừng thêm `mavenCentral()` vào root một lần nữa hoặc chạy `publish` thư viện local để lấp một repository thiếu.

### 22.1. Settings `pluginManagement` cũng vậy

Nếu included build dùng plugin bên ngoài:

~~~kotlin
plugins {
    id("com.example.special") version "1.2.3"
}
~~~

thì plugin phải có thật và included build phải có plugin resolution path hợp lệ. Đoạn trên **chỉ minh họa ID/version**, không khẳng định plugin này tồn tại. Root `pluginManagement.repositories` không tự làm included resolve được.

### 22.2. Repository names không quyết định build boundary

Hai builds có thể cùng dùng Maven Central nhưng vẫn có **hai repository declarations riêng**. Ngược lại, included build có thể dùng internal mirror, còn root dùng public repository theo chính sách, miễn dependency substitution và compatibility đảm bảo. Cấu hình độc lập giúp build có thể chạy standalone; cũng đòi hỏi quản trị nhất quán khi security policy yêu cầu.

## 23. Tình huống so sánh: catalog tồn tại nhưng libs accessor không có

Lỗi `Unresolved reference: libs` trong included build có thể đến từ:

- Chưa có `shared-lib/gradle/libs.versions.toml` và chưa khai báo catalog trong included settings.
- File TOML đặt nhầm ở root và developer nghĩ nó được kế thừa.
- Catalog được tạo tên `sharedLibs` nhưng code lại gọi `libs`.
- Alias khác tên: `junit-jupiter` → `libs.junit.jupiter`, không phải `libs.junitJupiter` trong một số generator mappings.
- Kotlin DSL accessor chưa được generate do settings/schema errors.
- `build-logic`/`buildSrc` dùng settings riêng.
- TOML có syntax không hợp lệ hoặc import `from(files(...))` trỏ sai file.
- Trùng tên `libs` giữa auto-import và manual import.

### 23.1. Khắc phục theo thứ tự

1. Đứng ở root của **build gặp lỗi**, xác định settings file nó đọc.
2. Kiểm tra `gradle/libs.versions.toml` **của build đó**.
3. Nếu dùng import, kiểm tra relative path từ settings file, `from` có đúng một TOML không.
4. Xem catalog name/aliases theo Gradle documentation.
5. Chạy task đơn giản của included build để xác nhận settings parse.
6. Nếu muốn chia sẻ phiên bản, chọn explicit import/published catalog.
7. Không chữa bằng cách copy toàn bộ `build.gradle.kts` root sang included một cách mù quáng.

### 23.2. Catalog không được tự cộng gộp khi composite chạy

Root `libs.junit.jupiter` 5.11.4 và included `libs.junit.jupiter` 5.10.2 có thể tồn tại song song vì each build's Kotlin DSL được compile theo own settings. Nhưng khi **runtime dependency graph** của app kết hợp nhiều libraries, Gradle resolution vẫn có thể chọn một version trong graph cụ thể theo constraints. Việc catalog độc lập không bảo đảm classpath hoàn toàn độc lập ở runtime của **một process consumer**.

## 24. Khi chạy included build standalone

Included build được thiết kế để có thể phát triển/test riêng. Từ root demo, trên Linux/macOS:

~~~bash
cd shared-lib
../gradlew test
../gradlew showScope
~~~

Trên Windows PowerShell:

~~~powershell
Push-Location shared-lib
..\gradlew.bat test
..\gradlew.bat showScope
Pop-Location
~~~

Lời gọi Gradle chạy với directory included là root build. Bởi vì Wrapper script có thể được dùng từ directory parent còn Gradle chọn project theo current working directory, ví dụ này dùng **root wrapper distribution** để chạy included settings. Nếu tổ chức có Wrapper riêng trong included build, hãy dùng Wrapper của chính included build phù hợp policy.

Kết quả property task khi không override:

~~~text
shared-messages scopeMessage=INCLUDED_FILE
~~~

**Khác biệt quan trọng:** nếu included build có `org.gradle.*` runtime property riêng, khi chạy standalone nó có thể được xem xét vì giờ included chính là root of invocation. Khi chạy từ outer composite root, runtime flags của outer root là nguồn quy định invocation.

### 24.1. Đảm bảo included build không ngầm dựa vào parent checkout

Một library thật sự độc lập nên:

- Có settings, plugins và repositories đủ để build standalone.
- Không hardcode `../app-host/build` files.
- Không đọc root `gradle.properties` nếu không được truyền chủ đích.
- Không bắt buộc root TOML nếu mục tiêu tách repository trong tương lai.
- Có contract/coordinates và tests của chính nó.
- Tách các secret/repository policies theo trust boundary.
- Kiểm tra độc lập trong CI, không chỉ khi có composite consumer.

Đây là trade-off: sharing thông qua relative TOML/path trong monorepo giảm duplication nhưng có thể khiến included build khó checkout độc lập. Nếu độc lập về release là mục tiêu, ưu tiên published shared catalog/plugin thay vì file path xuyên repo.

## 25. Chẩn đoán phụ thuộc substituted và phiên bản

Với composite root, dùng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency shared-messages
~~~

Bạn mong thấy dependency `org.example.training:shared-messages:1.0.0` được xử lý bằng **project của included build**, không đơn giản tải JAR từ Maven Central. Gradle report có thể hiện substitution reason/project identifier theo version; không khẳng định log sẽ có một chuỗi chính xác trên mọi bản Gradle.

Để xem included build riêng:

~~~bash
./gradlew :shared-lib:dependencies --configuration testRuntimeClasspath
./gradlew :shared-lib:outgoingVariants
~~~

Các tasks/report availability phụ thuộc plugins và build version; trong demo `java-library` cung cấp các variants chính thức như `apiElements`/`runtimeElements`.

### 25.1. Những giới hạn của dependency substitution

- Default substitution dùng project group/name; published module metadata có thể khác project default variants.
- Custom publications/POM, capabilities, classifiers hoặc plugin-specific variants có thể cần explicit mapping hoặc kiểm tra tương thích.
- Khi consumer yêu cầu binary publication thực, composite substitution phải được tắt/giới hạn cho configuration cụ thể theo API Gradle.
- Task output của included build được build theo Gradle model khi consumer cần artifact; không phải `mavenLocal()` ngầm.
- Đừng dùng local composite success thay thế hoàn toàn kiểm thử published binary/metadata ở CI release.

### 25.2. Kiểm tra version catalog không phải kiểm tra substitution

`dependencies --configuration testRuntimeClasspath` của root cho biết JUnit version theo root catalog; included report cho biết included catalog. Nhưng kiểm tra library dependency substitution phải xem `runtimeClasspath`/`compileClasspath` của **consumer có external coordinate**. Hai thí nghiệm này độc lập về mục đích.

## 26. Debugging matrix: dấu hiệu, nguyên nhân và cách sửa

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Root build chạy, included build không tìm thấy dependency | Repositories không kế thừa | Thêm repo ở included settings theo policy |
| Included `plugins` resolve FAIL | Root pluginManagement không truyền sang included | Cấu hình pluginManagement của included |
| `libs` không được nhận diện trong build-logic | Root catalog không kế thừa | Import TOML/published catalog trong build-logic settings |
| `libs.junit.jupiter` khác version | Hai catalogs độc lập | Đối chiếu TOML mỗi build hoặc share explicit |
| Included project property ra null | Root file gradle.properties không truyền | Khai báo riêng hoặc CLI/system/env provider |
| -P override cả hai builds | CLI invocation-wide | Xác định muốn local hay shared property |
| Included runtime flag không có hiệu lực trong composite | Runtime properties đọc từ outer root | Đặt invocation policy ở root build |
| Included standalone behavior khác composite | Root of invocation thay đổi | So CLI, Gradle User Home, root runtime properties |
| `project(":shared-lib")` báo UnknownProject | Included build không phải subproject | Dùng external coordinates/substitution |
| App vẫn tải published JAR | group/name mismatch hoặc included build không thực sự include | Xem settings, group/name và dependencyInsight |
| Đổi version rồi vẫn dùng included project | Default substitution theo group/name | Giới hạn substitution hoặc test binary separately |
| Hai builds có tên/path xung đột | Không unique included build path | Đặt name trong includeBuild hoặc đổi directory |
| Plugin lỗi 401/403 | Credentials/plugin repository policy sai | Kiểm tra nguồn secret và đúng repository scope |
| PKIX/TLS chỉ ở included | Included dùng mirror/trust chain khác | Xem đúng URL và truststore |
| Build Cache hoạt động giữa builds nhưng catalogs không chung | Cache shared, settings riêng | Phân biệt filesystem/global cache với cấu hình |
| Root `test` pass nhưng included tests chưa chạy | Root test không schedule included test | Gọi included task hoặc CI check task explicit |
| `FAIL_ON_PROJECT_REPOS` báo lỗi chỉ ở một build | Repository rule theo settings của build đó | Đặt repo vào settings hoặc sửa plugin thêm repo |
| Included build không hoạt động sau khi copy thư mục | Dựa vào relative root TOML/paths | Package/publish shared config hoặc sửa standalone settings |
| Khi build trên CI khác local | Gradle User Home, -P, env, JDK, repo/proxy | So mọi invocation-level inputs và build-local settings |

### 26.1. Chẩn đoán có thứ tự

1. **Xác định build nào đang fail:** root, included `shared-lib` hay build-logic?
2. **Xác định loại resolution:** plugin ID, library dependency, version catalog alias, project property hay runtime flag?
3. Kiểm tra chính `settings.gradle.kts` của **build lỗi**, không chỉ settings root.
4. Kiểm tra chính `gradle/libs.versions.toml` của build lỗi.
5. Với property, phân biệt Gradle project, Java system, environment và runtime `org.gradle.*`.
6. Với dependency, kiểm tra `group:name` và composite substitution report.
7. Với repository, kiểm tra URL, `pluginManagement`, `dependencyResolutionManagement`, credentials và mode.
8. Chạy build included standalone để phân biệt lỗi do isolation và lỗi do composite invocation.
9. Nếu standalone khác, so CLI `-P`/`-D`, Gradle User Home, root runtime properties và toolchain.
10. Sửa đúng scope, không copy/ghi đè toàn bộ build scripts chỉ để tạm qua một lỗi.

## 27. An toàn và quản trị khi chia sẻ cấu hình

Cô lập build configuration là lợi ích kiến trúc, nhưng cũng tạo nguy cơ **policy drift**: root dùng repository có kiểm soát, included dùng public repository không được phê duyệt; root pin JDK 17, included build chạy JDK 21; root bật dependency verification, included bỏ qua.

Một checklist governance nên có:

- Mỗi build có owner của settings, repository policy và catalogs.
- Shared policy được phân phối qua settings/convention plugin được review.
- Repository URL/credentials được lấy từ nguồn an toàn, không commit password.
- Version catalogs được pin/publish với quy trình cập nhật rõ.
- Plugins được pin versions và có integrity/compatibility checks khi phù hợp.
- Gradle Wrapper/distribution checksum được kiểm soát.
- CI chạy tests cả root consumer lẫn included library nếu release gate yêu cầu.
- Build-local project properties không bị lạm dụng cho secrets.
- Global Gradle User Home được coi là shared trust resource, không phải security sandbox.
- Published artifact metadata được test riêng khi consumer production dùng Maven/OCI binaries.
- Dependency substitution có phạm vi rõ khi muốn test source vs binary.
- Không dùng arbitrary init script từ nơi không đáng tin.
- Khi include nhiều builds, tránh duplicate build identifiers và concurrent build races.
- Có smoke test chạy included build standalone để giữ khả năng phát triển độc lập.

**Bảo mật đặc biệt:** Dù root `gradle.properties` không tự truyền custom key sang included build, environment và system properties có thể vẫn chung. Đừng coi composite isolation như một cơ chế che secrets giữa hai codebases không tin cậy. Không chạy untrusted included build với credentials production trong cùng privileged Gradle invocation.

## 28. Bài tập thực hành và đáp án

**Bài 1.** Root settings có `includeBuild("shared-lib")`. Root `pluginManagement.repositories` có tự áp vào included settings không?  
**Đáp án:** không. Included build có settings/plugin repositories riêng.

**Bài 2.** Root có `dependencyResolutionManagement.repositories { mavenCentral() }`. Included tests không resolve JUnit vì thiếu repo. Nên sửa đâu?  
**Đáp án:** ở repository configuration của included build, theo policy của chính included.

**Bài 3.** Root và included đều có `gradle/libs.versions.toml`. Chúng có chung một catalog `libs` không?  
**Đáp án:** không; mỗi build tự tạo catalog từ file của mình.

**Bài 4.** Root catalog JUnit 5.11.4, included 5.10.2. `libs.junit.jupiter` trong included build dùng version nào?  
**Đáp án:** 5.10.2 theo TOML của included, trừ khi có resolution constraints khác tác động phiên bản thực.

**Bài 5.** Root `gradle.properties` có `scopeMessage=ROOT_FILE`, included có `INCLUDED_FILE`. Gọi hai task `showScope` không có override sẽ in gì?  
**Đáp án:** root in `ROOT_FILE`, included in `INCLUDED_FILE`.

**Bài 6.** Thêm `-PscopeMessage=CLI_VALUE` cho composite invocation thì hai giá trị thế nào?  
**Đáp án:** cả hai thấy `CLI_VALUE` trong demo.

**Bài 7.** `-DscopeMessage=SYS` có tự trở thành `providers.gradleProperty("scopeMessage")` không?  
**Đáp án:** không, đây là Java system property; dùng `providers.systemProperty` để đọc đúng nguồn.

**Bài 8.** Included `gradle.properties` đặt `org.gradle.parallel=true`; khi chạy từ outer root, runtime flag này có chắc áp dụng không?  
**Đáp án:** không. Theo composite docs, runtime flags trong included file không điều khiển outer invocation.

**Bài 9.** Vì sao included build chạy standalone có thể khác composite?  
**Đáp án:** khi standalone nó là root of invocation, runtime flags/CLI/Gradle User Home/paths có thể khác.

**Bài 10.** Có thể tham chiếu included library bằng `implementation(project(":shared-lib"))` không?  
**Đáp án:** không trong demo, vì included build không phải subproject của root build.

**Bài 11.** Cách dùng library của demo trong root dependencies?  
**Đáp án:** `implementation("org.example.training:shared-messages:1.0.0")` và includeBuild tương ứng.

**Bài 12.** Default substitution thường nhận diện theo gì?  
**Đáp án:** project group và project name trong included build.

**Bài 13.** Consumer đổi version yêu cầu, có bảo đảm Gradle chuyển về published JAR không?  
**Đáp án:** không, default composite substitution có thể vẫn chọn local project theo group:name.

**Bài 14.** Demo `./gradlew -q run --args="Ada"` in dòng Java nào?  
**Đáp án:** `Hello, Ada from composite!`.

**Bài 15.** Demo `java -cp out/app:out/lib training.app.Main Ada` có kiểm tra Gradle composite substitution không?  
**Đáp án:** không; đó là direct javac/java classpath test.

**Bài 16.** Gọi root `./gradlew test` có tự chạy included test suite không?  
**Đáp án:** không mặc nhiên. Dùng `./gradlew :shared-lib:test` hoặc explicit orchestration task.

**Bài 17.** Root muốn chạy included `:test` qua task reference thì dùng API nào?  
**Đáp án:** `gradle.includedBuild("shared-lib").task(":test")`.

**Bài 18.** Included build không có catalog TOML nhưng muốn reuse root catalog: nên làm gì?  
**Đáp án:** import bằng `versionCatalogs.create("libs") { from(files("../gradle/libs.versions.toml")) }` hoặc shared published catalog.

**Bài 19.** Nếu included đã auto-import local `libs`, có nên tạo thêm manual catalog cùng tên `libs` không?  
**Đáp án:** không; sẽ có name collision. Bỏ local catalog khi import thay thế hoặc dùng tên khác.

**Bài 20.** Có thể gọi `from(...)` hai lần để merge hai TOML vào một catalog không?  
**Đáp án:** không; mỗi catalog chỉ nhận một from import theo API được tài liệu hóa.

**Bài 21.** `pluginManagement` và `dependencyResolutionManagement` có cùng nhiệm vụ không?  
**Đáp án:** không; lần lượt là plugin resolution và library dependency resolution.

**Bài 22.** Root bật `FAIL_ON_PROJECT_REPOS`, included chưa bật. Policy root có cấm `repositories` ở included build script không?  
**Đáp án:** không; phải enforce tại settings của included build.

**Bài 23.** Hai builds dùng Gradle User Home chung có đồng nghĩa root TOML/catalog được dùng chung không?  
**Đáp án:** không; caches/global settings có thể chung nhưng catalogs/settings build-local vẫn riêng.

**Bài 24.** Composite giúp dùng local library source mà không publish, nhưng production app dùng published Maven binary. Cần kiểm tra gì trước release?  
**Đáp án:** published metadata/variants/coordinates và binary consumer tests, không chỉ local substitution.

**Bài 25.** Included build không resolve plugin từ internal registry nhưng root resolve được. Đầu tiên xem gì?  
**Đáp án:** included settings/pluginManagement.repositories và credentials đúng scope.

**Bài 26.** Một company settings plugin được dùng bởi nhiều builds có làm settings files biến thành một file chung không?  
**Đáp án:** không; nó là cơ chế **áp dụng cùng logic**, từng build vẫn có settings riêng.

**Bài 27.** Tại sao không đặt secrets vào `-Ppassword=...` trong CI?  
**Đáp án:** CLI args có thể lộ qua logs/process listing/history và truyền trong invocation; dùng secret provider an toàn.

**Bài 28.** Khi library thay tên project từ `shared-messages` sang `message-kit`, root dependency không còn substitute. Nên kiểm tra gì?  
**Đáp án:** group/name matching hoặc explicit `dependencySubstitution` mapping, không đổi thứ tự task.

**Bài 29.** Muốn điều tra JUnit version ở root và included, chạy lệnh nào?  
**Đáp án:** `./gradlew dependencies --configuration testRuntimeClasspath` và `./gradlew :shared-lib:dependencies --configuration testRuntimeClasspath`.

**Bài 30.** Vì sao không nên coi composite isolation là sandbox cho untrusted code?  
**Đáp án:** CLI/system/env/Gradle User Home và quyền process/host có thể dùng chung; isolation chỉ là model cấu hình build.

## 29. Checklist áp dụng Composite Build an toàn

- [ ] Đã xác định `include(...)` khác `includeBuild(...)`?
- [ ] Root và included đều có `settings.gradle.kts` độc lập?
- [ ] Included build vẫn chạy được standalone khi cần?
- [ ] Build paths/project names không collision?
- [ ] Không dùng `project(":included-build")` xuyên build boundary?
- [ ] Đã xác định external group:name và substitution behavior?
- [ ] Đã kiểm tra requested version không tự pin published binary khi composite bật?
- [ ] Mỗi build có plugin repositories riêng phù hợp?
- [ ] Mỗi build có dependency repositories riêng phù hợp?
- [ ] `repositoriesMode` được enforce riêng theo organization policy?
- [ ] Publishing credentials không bị hiểu nhầm từ root settings?
- [ ] Root catalog và included catalog được phân biệt?
- [ ] Nếu shared catalog, import/publish được cấu hình tường minh?
- [ ] Không tạo trùng catalog name `libs` auto/manual?
- [ ] Không dùng TOML `include` hoặc gọi `from` nhiều lần trái API?
- [ ] User-defined project properties trong root `gradle.properties` không bị giả định inherited?
- [ ] CLI `-P`/system `-D` được phân biệt rõ?
- [ ] Runtime `org.gradle.*` trong composite được hiểu theo outer invocation?
- [ ] Gradle User Home/global properties/init scripts được coi là shared context?
- [ ] Java Toolchain/Wrapper tương thích ở cả builds?
- [ ] Root `test` và included `test` được chạy đúng phạm vi CI yêu cầu?
- [ ] Lệnh `dependencies`/`dependencyInsight` chỉ rõ root vs included?
- [ ] Build-logic convention plugins có settings/catalog/repository resolution riêng?
- [ ] Dependency publication metadata được test khi dùng binaries thật?
- [ ] Secrets được inject an toàn, không in vào logs hoặc TOML?
- [ ] Khi dùng relative shared files, đã cân nhắc standalone portability?
- [ ] Không assume mọi included build inherit enterprise security policy tự động?
- [ ] Có kiểm thử một clean workspace/CI env với catalogs/repos đúng?

## 30. Tài liệu chính thức

- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): khái niệm included build, scope isolation, `gradle.properties`, task references, dependency substitution, plugin resolution và giới hạn.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): auto-import `libs.versions.toml`, `from(files(...))`, publishing catalogs và hạn chế import.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): `RepositoriesMode.FAIL_ON_PROJECT_REPOS` và plugin repository policy.
- [Gradle — Centralizing Repositories](https://docs.gradle.org/current/userguide/centralizing_repositories.html): `dependencyResolutionManagement` và chính sách repositories.
- [Gradle — Plugin Management](https://docs.gradle.org/current/userguide/plugins_intermediate.html): `pluginManagement.repositories`, plugin marker resolution và plugin versions.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): convention plugins, `build-logic` composite build và project boundaries.
- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html): cấu trúc multi-project và cách included builds được ghép.
- [Gradle — Declaring Dependencies Between Subprojects](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): project dependency nội bộ, khác cross-build substitution.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): Gradle project properties, CLI `-P`, system `-D` và property precedence.
- [Gradle — Anatomy of a Gradle Build](https://docs.gradle.org/current/userguide/gradle_directories.html): Gradle User Home, caches, global config và layout.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `java-library`, API/runtime variants và publication.
- [Gradle — Dependency Resolution](https://docs.gradle.org/current/userguide/dependency_resolution.html): consumer/producer variants và graph semantics.
- [Gradle — Dependency Inspection](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies` và `dependencyInsight`.

**Kết luận:** Trong Gradle Composite Build, **mỗi included build là một build độc lập**, có `settings`, repositories, pluginManagement, catalog và user-defined `gradle.properties` của chính mình. `includeBuild` **kết nối dependency/task graph**, không hợp nhất các file cấu hình. Các giá trị invocation-wide như `-P`, `-D`, environment, Gradle User Home và root Gradle runtime settings là **những ngoại lệ cần phân biệt**. Muốn chia sẻ catalog/policy, hãy import hoặc publish có chủ đích; muốn tiêu thụ Java library của included build, dùng external coordinates và dependency substitution, không dùng project path xuyên build. Khi debug, luôn hỏi trước: **lỗi thuộc build nào, thuộc loại setting nào và dữ liệu đến từ scope nào?**