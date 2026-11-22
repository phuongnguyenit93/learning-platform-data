# Plugins DSL, plugin ID, phiên bản và `apply false` trong Gradle

## 1. Vì sao phải hiểu đúng Plugin DSL?

Gradle tổ chức phần lớn tính năng build thông qua **plugins**. Plugin có thể tạo task, extension, configuration, source set, model và convention. Ví dụ `java` tạo `compileJava`/`test`; `application` tạo `run`; plugin bên ngoài có thể cung cấp nhiệm vụ kiểm tra phiên bản dependencies.

Trong **Gradle Kotlin DSL** (`build.gradle.kts`), ví dụ điển hình:

~~~kotlin
plugins {
    application
    id("io.github.ben-manes.versions") version "0.66.0"
}
~~~

Cách đọc:

- `plugins { }` là **Plugin DSL**. Gradle nhận plugin requests sớm, resolve plugin classpath, apply plugin và tạo type-safe DSL accessors.
- `application` là **core Gradle plugin**, có thể viết `id("application")`. Không có version riêng vì implementation nằm trong Gradle distribution.
- `io.github.ben-manes.versions` là **plugin ID**, được Gradle Plugin Portal công bố; không phải Maven coordinate của JAR app.
- `version "0.66.0"` chọn **version plugin**. Đây là bản ví dụ thực tế, không phải cam kết plugin sẽ tương thích mọi Gradle/JDK.
- Không có `apply false`, plugin được yêu cầu thông thường sẽ **được apply vào chính project** đang viết block.

Bài này giải thích mối liên hệ giữa **plugin ID, version và nơi plugin được apply**. Sau khi học, bạn sẽ biết khi nào dùng root `apply false`, Settings `pluginManagement`, plugin aliases từ catalog hoặc convention plugin; phân biệt project dependencies với plugin dependencies; kiểm tra plugin đã được apply bằng task list; và xử lý lỗi plugin resolution/classpath.

Các ví dụ chính dùng Java 17+, Kotlin DSL và Gradle Wrapper. Ngoại trừ external plugin cần tải từ repository (nếu chưa có cache), chương trình Java minh họa không cần library bên thứ ba.

## 2. Plugin ID khác tên class, tọa độ dependency và task name

**Plugin ID** là chuỗi định danh dùng để yêu cầu Gradle apply một plugin. Một số core plugin được phân phối sẵn:

| Plugin ID | Công dụng | Kotlin DSL |
| --- | --- | --- |
| `java` | Java source sets, biên dịch, test. | `plugins { java }` |
| `java-library` | Java library, `api`/`implementation` scopes. | `plugins { id("java-library") }` |
| `application` | Chạy/distribute JVM application. | `plugins { application }` |
| `maven-publish` | Xuất bản artifacts theo Maven. | `plugins { id("maven-publish") }` |
| `jacoco` | Coverage Java tests. | `plugins { jacoco }` |
| `checkstyle` | Checkstyle tasks. | `plugins { checkstyle }` |

Kotlin DSL còn cho phép accessor có dấu backtick, như `plugins { `java-library` }`. Cặp backtick là một phần cú pháp Kotlin khi identifier có dấu gạch. `id("java-library")` thường dễ đọc hơn trong tài liệu có nhiều ký hiệu.

External plugin thường có namespace, ví dụ:

~~~kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.66.0"
}
~~~

Đây là Gradle Versions Plugin; nó cung cấp task `dependencyUpdates` để tìm bản cập nhật dependencies. Một **plugin ID** có thể ánh xạ tới một implementation class khác tên, qua metadata/plugin marker. Không coi `io.github.ben-manes.versions` là một Java package mà app có thể import.

### Khác với dependency của source Java

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

`application` là Gradle plugin: nó tác động tới **build logic**. `commons-lang3` là Java library dependency: nó đi vào **compile/runtime classpath** của chương trình khi phù hợp. `implementation("some.plugin:...")` **không tự apply** plugin. Ngược lại, `id("plugin.id")` không có nghĩa mã Java của app sẽ có plugin implementation trên runtimeClasspath.

Các tên như `:app` (project path), `run` (task), `java` (plugin ID), `org.apache.commons:commons-lang3:3.14.0` (module coordinate) có mục đích riêng; không thay thế lẫn nhau.

## 3. Tại sao `plugins { }` phải dùng cú pháp tĩnh?

Gradle cần xác định plugin requests **trước khi đánh giá** cấu hình thông thường của project. Nhờ vậy Kotlin DSL biết các extensions/tasks mà plugin tạo ra và có thể cung cấp accessors mạnh kiểu:

~~~kotlin
plugins {
    application
}

application {
    mainClass.set("example.App")
}
~~~

Ở đây `application { ... }` hoạt động vì plugin đã apply sớm. Nếu plugin bị apply muộn trong script body, type-safe accessor tương ứng có thể không được sinh khi body được biên dịch.

Trong project `plugins` block, dạng chuẩn:

~~~kotlin
plugins {
    id("java")
    id("io.github.ben-manes.versions") version "0.66.0"
}
~~~

ID và version thường phải là **literal strings** hoặc biểu thức đặc biệt mà Plugin DSL hỗ trợ như `alias(libs.plugins.versions.check)`. Một đoạn sau là **phản ví dụ về cú pháp**:

~~~kotlin
// Không dùng biến tùy ý làm plugin ID trong project plugins block.
val pluginId = "io.github.ben-manes.versions"

plugins {
    id(pluginId) version "0.66.0"
}
~~~

Cũng không đặt `plugins { }` trong vòng lặp, nhánh `if` hoặc function. Nó phải ở vị trí top-level được Gradle cho phép, trước phần cấu hình thông thường. Nếu cần version được tính từ file properties, dùng `pluginManagement` trong Settings. Nếu muốn chia sẻ quy tắc giữa modules, dùng **convention plugin** thay vì đưa logic động vào Plugin DSL.

**Điểm cần nhớ:** `plugins { }` là cơ chế khai báo plugin sớm, không phải một Kotlin function tùy ý có thể gọi ở mọi nơi.

## 4. Core plugin không có external version độc lập

~~~kotlin
plugins {
    java
    application
}
~~~

Core plugins được vận chuyển cùng Gradle. Phiên bản thực thi của chúng gắn với **Gradle Wrapper**; không lấy từ Maven repository bằng một version tùy chọn:

~~~kotlin
// Sai: không đặt external plugin version cho core Java plugin.
plugins {
    id("java") version "1.0"
}
~~~

Tương tự, đoạn dưới không phải chiến lược được hỗ trợ để giữ Java plugin cho subprojects:

~~~kotlin
// Sai/không nên dùng: core plugin đã nằm trên Gradle classpath.
plugins {
    id("java") apply false
}
~~~

Gradle có thể báo core plugin đã có sẵn, yêu cầu `apply false` là no-op hoặc không hợp lệ. Nếu root chỉ điều phối multi-project và **không phải Java project**, đừng khai báo `java` ở root. Tại mỗi subproject cần Java, viết `plugins { java }`.

External plugin khác: cần chọn version vì implementation không nằm trong Gradle distribution. Đây là lý do root `apply false` phổ biến cho **external plugins** nhưng không cần cho `java`, `application` hay `maven-publish`.

## 5. Ý nghĩa chính xác của `apply false`

~~~kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.66.0" apply false
}
~~~

`apply false` có nghĩa: **không áp plugin vào project chứa declaration này**. Plugin request vẫn có thể được resolve và implementation được chuẩn bị trên classpath phù hợp. Nó không có nghĩa “không tải plugin, không kiểm tra ID/version, không dùng mạng”.

So sánh:

| Cấu hình | Plugin có thể được resolve? | Plugin apply tại project chứa block? | Tasks/extensions do plugin tạo tại project? |
| --- | --- | --- | --- |
| `id("x") version "v"` | Có. | **Có.** | Có nếu plugin tạo. |
| `id("x") version "v" apply false` | Có. | **Không.** | **Không chỉ do declaration này.** |
| `id("x")` ở subproject với root external `apply false` | Có, từ phiên bản/classpath root phù hợp. | **Có tại subproject.** | Có tại subproject. |
| `id("java")` | Core đã sẵn. | **Có tại project.** | Có model/tasks Java. |
| `id("java") apply false` | Core đã sẵn; use case không hợp lệ. | Không nên dùng. | Không dùng để quản lý version. |

`apply false` không tương đương `enabled = false` của Task, `-x test` khi chạy command hoặc `onlyIf { ... }` của task action. Những API ấy điều khiển **task execution**, còn `apply false` điều khiển **plugin application** tại một project.

### Root `apply false` không tự tạo extension/task

Nếu chỉ viết:

~~~kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.66.0" apply false
}
~~~

ở root, root **không có `dependencyUpdates` task do plugin này tạo** và cũng không có extensions do plugin register khi apply. Chỉ project nào thực sự apply plugin mới có chúng.

Không viết cấu hình root như thể plugin đã apply:

~~~kotlin
// Phản ví dụ: task có thể không tồn tại tại root.
// tasks.named("dependencyUpdates") { ... }
~~~

Đoạn comment minh họa lỗi tên task ở project sai. Nếu muốn task `dependencyUpdates` ở root, phải apply plugin tại root; nếu chỉ cần nó ở `:app`, apply tại `:app`.

## 6. Bài thực hành hoàn chỉnh: multi-project Java 17

Mục tiêu: root quản lý **một phiên bản external plugin** bằng `apply false`; ứng dụng `:app` apply plugin; module `:core` không apply plugin. Một Java main method in stdout cố định.

### 6.1. Cấu trúc

~~~text
gradle-plugin-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── app/
│   ├── build.gradle.kts
│   └── src/main/java/example/App.java
└── core/
    └── build.gradle.kts
~~~

Giả sử dự án đã có **Gradle Wrapper** hoạt động và JDK 17. Lần đầu resolve `io.github.ben-manes.versions` phải truy cập Plugin Portal hoặc có đủ cache/mirror. Plugin version `0.66.0` tồn tại thực, nhưng bạn vẫn phải kiểm tra nó tương thích với phiên bản Gradle Wrapper hiện tại trước khi dùng trong production.

### 6.2. `settings.gradle.kts`

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "gradle-plugin-lab"
include("app", "core")
~~~

`pluginManagement` xuất hiện **đầu Settings script**, quyết định nơi Gradle tìm plugin marker/implementation. `include(...)` tạo hai project paths. Không cần `mavenCentral()` cho Java app trong bài vì Java main source không có thư viện ngoài.

### 6.3. Root `build.gradle.kts`

~~~kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.66.0" apply false
}
~~~

Root chỉ thống nhất external plugin version. **Root không apply** versions plugin, nên không có `dependencyUpdates` task tự sinh tại root từ declaration trên.

### 6.4. `app/build.gradle.kts`

~~~kotlin
plugins {
    application
    id("io.github.ben-manes.versions")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("example.App")
}
~~~

Ở đây external plugin dùng ID **không kèm version** vì root đã cung cấp version/classpath. `application` là core plugin và tự tạo `run`, Java source sets và tasks. `java.toolchain` hướng compile tới JDK 17.

### 6.5. `app/src/main/java/example/App.java`

~~~java
package example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("PLUGIN_DSL_OK");
    }
}
~~~

Java 17 compile được và không có dependency ngoài.

### 6.6. `core/build.gradle.kts`

~~~kotlin
plugins {
    java
}
~~~

`:core` chỉ apply core Java plugin, **không có external versions plugin**. Điều này không làm `:app` mất quyền áp external plugin đã khai báo ở root.

### 6.7. Các lệnh kiểm tra

~~~bash
./gradlew --version
./gradlew :app:help
./gradlew :app:tasks --all
./gradlew :core:tasks --all
./gradlew :tasks --all
./gradlew -q :app:run
~~~

Stdout **do `App.main` in**:

~~~text
PLUGIN_DSL_OK
~~~

Các dòng khác từ Gradle/daemon/network có thể khác theo máy; kết quả Java in một dòng như trên khi build/run thành công.

Kiểm tra task lists:
1. `:app:tasks --all` có task `dependencyUpdates` do external plugin tạo.
2. `:core:tasks --all` không có task đó do plugin, vì core không apply.
3. Root `:tasks --all` không có task đó **chỉ từ `apply false`**.
4. `:app:run` tồn tại nhờ Application plugin.

Không cần chạy `:app:dependencyUpdates` để chứng minh plugin application, vì tác vụ này có thể đi tìm phiên bản dependencies từ mạng. `:app:tasks` là đủ cho kiểm tra scope.

### 6.8. Kiểm tra Java source không phụ thuộc plugin resolution

Vì Java code không dùng library ngoài, trên Linux/macOS bạn có thể biên dịch độc lập tại root:

~~~bash
mkdir -p build/manual-classes
javac -encoding UTF-8 -d build/manual-classes app/src/main/java/example/App.java
java -cp build/manual-classes example.App
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual-classes | Out-Null
javac -encoding UTF-8 -d build/manual-classes app/src/main/java/example/App.java
java -cp build/manual-classes example.App
~~~

Cả hai in:

~~~text
PLUGIN_DSL_OK
~~~

Điều này chứng minh **mã Java hợp lệ**, không chứng minh Gradle đã resolve external plugin. Để kiểm tra plugin, phải chạy `:app:tasks --all` hoặc một task do plugin đăng ký.

## 7. Vì sao subproject phải yêu cầu plugin riêng?

Multi-project Gradle là nhiều Project objects, mỗi project có tasks/plugins riêng:

~~~text
root ":":
  id("io.github.ben-manes.versions") version "0.66.0" apply false
  -> plugin chưa apply ở root

:app:
  application
  id("io.github.ben-manes.versions")
  -> có run và dependencyUpdates

:core:
  java
  -> có Java compile/test tasks, không có dependencyUpdates
~~~

`apply false` ở root không tự apply plugin vào `subprojects`; nó chỉ làm plugin/version khả dụng. Việc apply từng project là **quyết định độc lập**.

Nếu root bỏ `apply false`:

~~~kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.66.0"
}
~~~

thì plugin apply vào root và tạo tasks/extensions ở root. Nó **vẫn không có nghĩa** plugin tự áp vào mọi subproject. Vì vậy không có “một declaration tự apply cho tất cả” chỉ nhờ `plugins { }`.

## 8. `pluginManagement.repositories` khác `repositories` của project

Hai cơ chế khác nhau:

~~~kotlin
// settings.gradle.kts
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

Đây là **plugin repositories**, dùng để tìm marker và implementation của Gradle plugin.

~~~kotlin
// app/build.gradle.kts
repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

Đây là **dependency repositories** dành cho Java compile/runtime libraries. Settings còn có `dependencyResolutionManagement.repositories` để quản lý repositories của project dependencies, nhưng nó **khác** `pluginManagement.repositories`.

Nếu lỗi “Plugin [id: 'x', version: 'v'] was not found”, việc thêm `mavenCentral()` trong `app/build.gradle.kts` **không tự sửa** nguồn plugin resolution. Ngược lại, chỉ có `gradlePluginPortal()` trong Settings **không bảo đảm** mọi Java library `implementation(...)` resolve được.

### Plugin marker artifact

Gradle Plugin DSL thường tìm artifact marker với tọa độ:

~~~text
plugin.id:plugin.id.gradle.plugin:plugin.version

Ví dụ một dòng:
io.github.ben-manes.versions:io.github.ben-manes.versions.gradle.plugin:0.66.0
~~~

Marker chỉ tới implementation artifact thật. Plugin ID có thể khác Java implementation class và implementation Maven module. `java-gradle-plugin` hỗ trợ publish marker khi tác giả phát triển plugin.

Nếu một plugin nội bộ chưa có marker, `pluginManagement.resolutionStrategy.eachPlugin` có thể ánh xạ ID sang implementation module:

~~~kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-plugins")
        }
    }

    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "org.example.internal") {
                useModule("org.example.build:internal-plugin:1.0")
            }
        }
    }
}
~~~

Đây là **cú pháp minh họa với repository/module giả định**, không chạy nếu server/artifact không tồn tại. `useModule` phải chỉ tới module thật sự cung cấp implementation cho ID đã yêu cầu; không áp dụng bừa để biến Java library thành Gradle plugin.

## 9. Quản lý version trong `pluginManagement.plugins`

Thay vì root `apply false`, bạn có thể dùng **Settings** làm nguồn plugin version duy nhất.

`settings.gradle.kts`:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }

    plugins {
        id("io.github.ben-manes.versions") version "0.66.0"
    }
}

rootProject.name = "settings-version-lab"
include("app")
~~~

`app/build.gradle.kts`:

~~~kotlin
plugins {
    application
    id("io.github.ben-manes.versions")
}
~~~

Đây là **phương án khác** với lab root `apply false`. `pluginManagement.plugins` chỉ đặt **default plugin version** cho requests, **không apply** plugin cho các projects. `:app` vẫn phải có `id(...)`. Cách này tránh root phải đưa plugin vào classpath chỉ để khai báo version khi chưa project nào cần nó.

### Version từ Gradle properties trong Settings

Trong Settings plugin management có thể dùng property:

~~~kotlin
pluginManagement {
    val selectedVersion =
        providers.gradleProperty("versionsPluginVersion").get()

    repositories {
        gradlePluginPortal()
    }
    plugins {
        id("io.github.ben-manes.versions") version selectedVersion
    }
}
~~~

`gradle.properties`:

~~~properties
versionsPluginVersion=0.66.0
~~~

Đây là **phương án thay thế** cho Settings version literal; không dán nhiều Settings files có cùng `pluginManagement` block. `get()` yêu cầu property có giá trị; có thể cung cấp default có chủ đích bằng `orElse(...)`.

**Khác biệt:** trong project Plugin DSL, `id(myVariable)` không hợp lệ theo cú pháp tĩnh thông thường, nhưng `pluginManagement` được thiết kế để có nhiều lựa chọn quản lý version linh hoạt hơn.

## 10. Version catalog plugin aliases

`gradle/libs.versions.toml`:

~~~toml
[versions]
versionsPlugin = "0.66.0"

[plugins]
versions-check = { id = "io.github.ben-manes.versions", version.ref = "versionsPlugin" }
~~~

Root `build.gradle.kts`:

~~~kotlin
plugins {
    alias(libs.plugins.versions.check) apply false
}
~~~

`app/build.gradle.kts`:

~~~kotlin
plugins {
    application
    alias(libs.plugins.versions.check)
}
~~~

Đây là **phương án dùng version catalog** thay cho root literal version trong lab mục 6. Alias `versions-check` sinh accessor `libs.plugins.versions.check`. `alias(...)` tạo plugin request với ID và version từ `[plugins]`, nhưng `apply false` ở root vẫn ngăn plugin apply vào root.

### Không nhầm plugins với libraries trong catalog

~~~toml
[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version = "3.14.0" }

[plugins]
versions-check = { id = "io.github.ben-manes.versions", version = "0.66.0" }
~~~

- `libs.commons.lang3` dùng trong `dependencies { implementation(libs.commons.lang3) }`.
- `libs.plugins.versions.check` dùng trong `plugins { alias(libs.plugins.versions.check) }`.
- Version catalog **không tự apply** plugins; chỉ project thực sự gọi alias mới yêu cầu plugin.
- Không gọi `implementation(libs.plugins.versions.check)` để apply plugin; đây là sai loại dependency.

### Giới hạn của catalog trong Settings

Gradle tài liệu hóa rằng **plugin khai báo trong version catalog không thể dùng để apply settings plugin trong Settings file** theo cách dùng `alias(libs.plugins...)` của project scripts. `pluginManagement` được xử lý trước project version catalog. Khi cần version cho settings plugin, dùng `pluginManagement.plugins` hoặc APIs Settings phù hợp thay vì sao chép alias vào settings.

## 11. Một nguồn version là đủ: tránh conflict classpath

Các nguồn version phổ biến:
1. Version literal trong project `plugins { id(...) version "..." }`.
2. Root `plugins { ... apply false }`, subproject chỉ ghi ID.
3. `pluginManagement.plugins` trong Settings.
4. Catalog `[plugins]` và `alias(...)`.

Không cần đồng thời lặp mỗi plugin version trong tất cả bốn nơi. Ví dụ root đã declare:

~~~kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.66.0" apply false
}
~~~

thì child nên:

~~~kotlin
plugins {
    id("io.github.ben-manes.versions")
}
~~~

thay vì lặp version cùng ID trong child. Trong một số tình huống, version request trên plugin đã ở classpath gây lỗi kiểu **“already on the classpath with an unknown version”** hoặc **“plugin request must not include a version”**, nhất là khi plugin được đưa qua `buildSrc`/`buildscript`/included build. Thông điệp thực tế phụ thuộc Gradle version/classpath, nhưng cách điều tra là tìm **một nguồn classpath/version thống nhất**.

`Gradle Version Catalog` không phải một “version constraint” tự ép mọi external plugins về alias version; alias phải được dùng để sinh request. Tách quản lý plugin version khỏi library dependency conflict resolution trên `runtimeClasspath`.

## 12. Khi chỉ `apply false`, root chưa có plugin model

Root:

~~~kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.66.0" apply false
}

// Đây là phản ví dụ nếu nghĩ task đã tồn tại ở root:
// tasks.named("dependencyUpdates") { ... }
~~~

`tasks.named("dependencyUpdates")` sẽ thất bại nếu task không được đăng ký bởi plugin nào ở root. Đặt cấu hình ở app đã apply:

~~~kotlin
// app/build.gradle.kts
plugins {
    id("io.github.ben-manes.versions")
}

// Task của versions plugin được đăng ký cho :app:
// tasks.named("dependencyUpdates") { ... }
~~~

Tương tự, extension do plugin tạo **chỉ có sau apply**, không phải sau `apply false`. Với Kotlin DSL, type-safe accessors thường xuất hiện khi plugin apply sớm trong `plugins` block; apply muộn bằng `apply(plugin = "...")` trong script body có thể khiến accessor chưa có lúc body được biên dịch.

Khi cần cấu hình một plugin chỉ sau khi plugin khác đã có mặt:

~~~kotlin
pluginManager.withPlugin("java") {
    // Cấu hình kết hợp với Java plugin khi nó đã apply.
}
~~~

Đây là **mảnh project/plugin logic**, không phải build script đầy đủ. `withPlugin` phù hợp hơn việc dựa vào thứ tự áp plugin không rõ hoặc cố chờ bằng `afterEvaluate`.

## 13. Legacy `apply(plugin = "...")` và `buildscript`

Gradle vẫn hỗ trợ:

~~~kotlin
apply(plugin = "java")
~~~

Nhưng với project mới, ưu tiên:

~~~kotlin
plugins {
    java
}
~~~

Đối với plugin ngoài, cơ chế legacy có thể cần buildscript classpath:

~~~kotlin
buildscript {
    repositories {
        gradlePluginPortal()
    }
    dependencies {
        classpath(
            "io.github.ben-manes.versions:" +
                "io.github.ben-manes.versions.gradle.plugin:0.66.0"
        )
    }
}

apply(plugin = "io.github.ben-manes.versions")
~~~

Đây là **mẫu legacy độc lập**, không trộn với `plugins { id(...) version ... }` cho cùng plugin. `buildscript.dependencies.classpath` tải **plugin code cho build**, không phải dependencies cho Java app. Legacy apply có thể cần khi plugin không dùng Plugin DSL được hoặc script plugins đặc biệt, nhưng Plugin DSL cho khả năng khai báo/nhận diện model sớm rõ ràng hơn.

`apply(from = "shared.gradle.kts")` là cách áp **script plugin từ file**, không phải cách viết tắt của `id("binary.plugin")`. Khi build logic được chia sẻ lâu dài, nên thiết kế **convention plugin** thay vì duy trì nhiều script apply tản mác.

## 14. Cross-project apply và convention plugins

Root có thể áp Java cho mọi subproject:

~~~kotlin
subprojects {
    plugins.apply("java")
}
~~~

Cách này có thể chạy nhưng tạo **cross-project configuration**: subproject không tự cho thấy plugin nào đang áp, và các project không cần Java cũng nhận Java tasks/configurations. Gradle khuyến nghị dùng **convention plugins** khi chia cấu hình giữa nhiều modules.

Một subproject có thể khai báo convention plugin riêng:

~~~kotlin
plugins {
    id("company.java-conventions")
}
~~~

Đây là **mảnh code giả định đã có plugin nội bộ với ID tương ứng**. Convention plugin có thể apply core `java-library`, chọn toolchain, thiết lập JUnit, code style và publishing policy ở một nơi.

### Included build `build-logic`

Trong Settings của build chính:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "company-project"
include("app", "library")
~~~

Điều kiện: thư mục `build-logic` phải là một Gradle build hợp lệ chứa plugin implementation/precompiled script plugin. `pluginManagement.includeBuild` phục vụ **plugin resolution**, không giống `include("build-logic")` tạo một project thông thường.

### Precompiled script plugin dùng external plugin

External plugin trong precompiled script plugin thường cần dependency trên classpath **của build-logic**:

~~~kotlin
// build-logic/build.gradle.kts — mảnh config
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}

dependencies {
    implementation(
        "io.github.ben-manes.versions:" +
            "io.github.ben-manes.versions.gradle.plugin:0.66.0"
    )
}
~~~

Một precompiled script file:

~~~kotlin
// build-logic/src/main/kotlin/company.versions.gradle.kts
plugins {
    id("io.github.ben-manes.versions")
}
~~~

Đây là **hai file của một included build**, không phải hai block trong app. Đừng đặt `version "0.66.0"` trực tiếp vào precompiled script plugin `plugins`; implementation cần được cung cấp trong **build-logic dependencies**. Root `apply false` của build chính không mặc nhiên thiết lập classpath riêng của included build.

`buildSrc` cũng là cách cung cấp custom/convention plugins cho một build; hãy hiểu nó có build logic/classpath và vòng đời riêng. Trong nhiều modules, convention plugins giúp giảm việc áp một plugin ở root chỉ để “lây” mọi cấu hình vào subprojects.

## 15. Settings plugin và project plugin không cùng target

`settings.gradle.kts` có thể có `plugins { }` dành cho **Settings plugins**, ví dụ loại plugin thiết lập toàn build. Nó không phải chỗ thông thường để áp `java`/`application` cho `:app`.

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

// Settings plugins nếu có được đặt trong Settings plugins block.
// Ví dụ plugin nội bộ chỉ khi đã tồn tại:
// plugins {
//     id("org.example.settings-plugin") version "1.0"
// }

rootProject.name = "settings-lab"
include("app")
~~~

Đây là **ví dụ vị trí**, ID trong comment không phải external plugin đang được publish. Không đưa `plugins { java }` vào Settings rồi kỳ vọng có `:app:compileJava`; Java plugin target là `Project` và phải apply ở app build script hoặc convention.

`pluginManagement` chỉ thiết lập plugin repositories/version defaults/resolution, không tự apply plugins. `plugins` trong project build script điều khiển plugins ở project. `plugins` của Settings dành cho plugin target Settings. Version catalog plugin alias từ project không được sử dụng như settings plugin alias theo quy tắc Gradle đang tài liệu hóa.

## 16. Các lỗi Plugin DSL hay gặp

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Plugin [id: 'x', version: 'v'] was not found` | ID/version sai, repository không có marker, mạng/proxy hoặc auth. | Xem Plugin Portal, `pluginManagement.repositories`, marker coordinates. |
| External plugin version thiếu | Không có version trong project/root/settings/catalog và plugin chưa có classpath. | Ghi version tại một nguồn có kiểm soát. |
| `Plugin already on classpath ... version` | Version lặp/xung đột hoặc plugin được cung cấp từ buildSrc/classpath khác. | Bỏ version lặp ở child, thống nhất nguồn plugin implementation. |
| `id("java") apply false` báo lỗi | Core plugin đã nằm trên Gradle classpath. | Đừng dùng core `apply false`; subproject apply trực tiếp. |
| Root không có `dependencyUpdates` | Root chỉ `apply false`, chưa apply plugin. | Đây là đúng; apply vào project cần task. |
| App có `dependencyUpdates` nhưng core không | Chỉ app áp external plugin. | Đúng theo thiết kế; xem task lists riêng. |
| `Unresolved reference` đối với extension | Plugin chưa apply hoặc apply muộn, accessor chưa được sinh. | Ưu tiên project `plugins`, hoặc typed extension API khi cần. |
| `libs.plugins.*` không resolve | TOML alias sai, file không đúng chỗ, accessor chưa được tạo. | Kiểm tra `gradle/libs.versions.toml` và `[plugins]`. |
| Alias plugin không dùng được ở Settings | Settings không hỗ trợ plugin catalog aliases như project. | Dùng `pluginManagement.plugins`. |
| `plugins` không chấp nhận biến/`if` | Static syntax restrictions. | Dùng literals, catalog alias, Settings plugin management. |
| Plugin không tương thích Java/Gradle | Plugin yêu cầu Gradle API/JDK khác; đôi khi “No matching variant”. | Kiểm tra release notes, Wrapper và JVM. |
| External plugin không tìm thấy qua Maven Central của app | Dùng project dependency repository thay vì plugin repository. | Cấu hình `pluginManagement.repositories`. |
| Precompiled convention plugin thiếu plugin implementation | Build-logic không khai báo classpath dependency. | Thêm marker/implementation vào build-logic, dùng ID không version trong precompiled script. |
| Plugin bị áp vào quá nhiều modules | Root `subprojects { plugins.apply(...) }` hoặc convention áp rộng. | Áp rõ ở từng project và tách conventions. |
| Plugin task xuất hiện nhưng Java app compile fail | Plugin application không bảo đảm library/source đúng. | Kiểm tra Java source, toolchain, application.mainClass và runtime dependencies. |

Thông điệp lỗi cụ thể khác theo Gradle version, không nên sửa bằng cách xóa cache hàng loạt ngay khi chưa biết nguyên nhân. Hãy phân biệt **plugin resolution**, **plugin application** và **project task configuration**.

## 17. Quy trình debug từng bước

1. Xác định lỗi nằm ở **Settings**, root, `:app`, `:core`, `buildSrc` hay included build.
2. Xác định plugin ID là core hay external và thuộc target Settings/Project nào.
3. Tìm nguồn version: local project, root `apply false`, `pluginManagement`, catalog.
4. Kiểm tra ID có bị đổi/deprecated không và version có thực sự được publish.
5. Kiểm tra plugin marker/implementation ở `pluginManagement.repositories` và auth/mạng.
6. Kiểm tra plugin/version tương thích bản Gradle và JDK hiện tại.
7. Xem plugin đã **apply** vào project cần tasks hay chỉ `apply false` ở root.
8. Nếu tasks/extensions bị thiếu, xem `:app:tasks --all` rồi so sánh `:core:tasks --all`.
9. Nếu Kotlin DSL `Unresolved reference`, đưa plugin application vào project `plugins` sớm hoặc dùng typed extension APIs.
10. Nếu plugin đã có trên classpath, tránh yêu cầu một version khác từ child.
11. Với nhiều subprojects, xem có cấu hình chéo không rõ ràng từ root.
12. Chạy lại những task nhỏ `help`/`tasks` trước `build`, rồi kiểm tra Java main stdout.

Lệnh chẩn đoán:

~~~bash
./gradlew --version
./gradlew help --stacktrace
./gradlew :app:help --info
./gradlew :app:tasks --all
./gradlew :core:tasks --all
./gradlew -q :app:run
~~~

`--stacktrace` cho biết vị trí lỗi, `--info` cung cấp thông tin cấu hình. Tránh công khai log `--debug` không được kiểm soát vì có thể rất dài và chứa thông tin nhạy cảm.

### Kiểm tra plugin đã apply

Trong `app/build.gradle.kts`, nếu cần một task diagnostic tạm thời:

~~~kotlin
tasks.register("checkPluginApplication") {
    val isApplied =
        pluginManager.hasPlugin("io.github.ben-manes.versions")
    doLast {
        println("VERSIONS_PLUGIN_APPLIED=" + isApplied)
    }
}
~~~

Đây là **mảnh script đặt sau `plugins`** của app. Boolean được đọc khi cấu hình và capture vào task action, tránh truy cập trực tiếp Project/PluginManager từ action khi dùng Configuration Cache. Khi plugin đã apply, task in:

~~~text
VERSIONS_PLUGIN_APPLIED=true
~~~

Không dựa vào một `println` tại cấp build script như bằng chứng chạy mỗi lần, vì Configuration Cache có thể bỏ qua cấu hình ở cache hit.

## 18. Các lưu ý về bảo mật và khả năng tái lập

Plugin có thể chạy code với quyền của Gradle process. Những quy tắc hữu ích:

- Pin external plugin versions; không dùng dynamic versions nếu không có chính sách kiểm soát.
- Pin Gradle Wrapper, kiểm tra JDK/Gradle/plugin compatibility.
- Kiểm soát repositories, mirror/credentials và chỉ dùng plugin từ nguồn đáng tin.
- Không ghi secrets trực tiếp trong `build.gradle.kts` hay in chúng vào logs.
- Không thêm `apply false` cho plugin không ai dùng: nó vẫn có thể cần resolve/download.
- Không apply những plugin không cần lên root chỉ để tăng “tiện lợi”.
- Tránh `subprojects`/`allprojects` mutation ẩn, ưu tiên convention plugins.
- Test plugin upgrades bằng `help`, `tasks`, `test`, `build` và kiểm tra Configuration Cache nếu dự án sử dụng.
- Đừng nhầm quản lý plugin versions với dependency locking của **project module dependencies**.
- Khi một plugin đổi ID hoặc dừng hỗ trợ Gradle/JDK cũ, kiểm tra thông báo chính thức trước khi sửa alias/version.

## 19. Checklist code review

- [ ] Plugin ID đúng, không bị nhầm với Java dependency coordinates.
- [ ] Core plugins không ghi external version và không dùng `apply false`.
- [ ] External plugin version được pin và lấy từ một nguồn chủ đạo.
- [ ] Root `apply false` chỉ dùng khi root không muốn apply plugin.
- [ ] Mỗi subproject yêu cầu plugin mà nó cần.
- [ ] `pluginManagement.repositories` đúng, khác `repositories` cho Java libraries.
- [ ] Project `plugins` chỉ dùng cú pháp tĩnh/literal hoặc catalog alias hợp lệ.
- [ ] `[plugins]` catalog không bị dùng nhầm thay `[libraries]`.
- [ ] Không cố dùng project plugin catalog alias trong Settings.
- [ ] Không cấu hình root task/extension của plugin chưa được apply.
- [ ] Không lặp version external plugin ở child khi root đã cung cấp.
- [ ] Precompiled conventions có plugin implementation trong build-logic classpath.
- [ ] Tránh cross-project plugin application không kiểm soát.
- [ ] Đã xem tasks ở root, `:app`, `:core` và chạy Java 17 demo.
- [ ] Đã xác minh Gradle Wrapper/JDK/plugin version tương thích.
- [ ] Đã kiểm soát repository và nâng cấp plugin theo quy trình.

## 20. Câu hỏi tự kiểm tra

1. **`plugins { application }` làm gì?** Apply core Application plugin vào project chứa block.
2. **Plugin ID khác GAV library thế nào?** ID dành cho Gradle plugin application, GAV library dành cho module classpath ứng dụng.
3. **Core `java` cần `version "1.0"` không?** Không; đi cùng Gradle distribution.
4. **`apply false` có khiến Gradle không cần resolve plugin?** Không; nó chỉ ngăn apply vào target hiện tại.
5. **Root `apply false` có tự áp external plugin lên mọi subproject?** Không, child phải yêu cầu ID.
6. **Root có task plugin sau `apply false` không?** Không chỉ vì declaration ấy.
7. **Vì sao `id("java") apply false` không nên dùng?** Core plugin sẵn có, yêu cầu không apply là vô nghĩa/không hợp lệ.
8. **Child có cần lặp external plugin version do root đã ghi không?** Thường không.
9. **`pluginManagement.plugins` có tự apply plugin không?** Không, chỉ đặt default versions.
10. **`mavenCentral()` của Java project có chắc sửa “Plugin not found” không?** Không, cần plugin repositories.
11. **Catalog plugin alias thuộc đâu?** `[plugins]` trong `gradle/libs.versions.toml`, dùng `alias(libs.plugins.*)`.
12. **Catalog plugin alias có sẵn ở Settings không?** Không theo cách project script dùng.
13. **Marker artifact là gì?** Tọa độ quy ước giúp map plugin ID/version sang plugin implementation.
14. **Khi root không có `dependencyUpdates` nhưng `:app` có, đó có phải lỗi?** Không, đúng với root `apply false`/app apply.
15. **Tại sao Java main chạy bằng `javac` chưa chứng minh external plugin đã apply?** Java source không phụ thuộc plugin resolution; phải xem tasks của Gradle project.
16. **`apply(plugin = "...")` khác Plugin DSL ở đâu?** Legacy apply có thể xảy ra sau khi Kotlin DSL accessors được tính; Plugin DSL hỗ trợ resolve/apply sớm.
17. **Precompiled script convention plugin dùng version external plugin ở đâu?** Trong build-logic dependencies, không đặt version trong precompiled `plugins`.
18. **Khi nào nên dùng convention plugin?** Khi nhiều modules chia sẻ build rules, muốn tránh copy-paste/cross-project mutation.
19. **Bước đầu khi có version conflict của plugin?** Xác định tất cả nơi cung cấp plugin classpath và thống nhất version.
20. **Lệnh nào xem task có thật ở app?** `./gradlew :app:tasks --all`.

## Tài liệu Gradle chính thức

- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): Plugin DSL, external/core plugins, `apply false`, pluginManagement, plugin markers, multi-project.
- [Gradle — PluginDependenciesSpec](https://docs.gradle.org/current/dsl/org.gradle.plugin.use.PluginDependenciesSpec.html): `id`, `version`, `apply` và giới hạn cú pháp.
- [Gradle — PluginManagementSpec](https://docs.gradle.org/current/javadoc/org/gradle/plugin/management/PluginManagementSpec.html): `repositories`, `plugins`, `resolutionStrategy`, `includeBuild`.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): plugin aliases, `[plugins]`, settings limitations.
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): `buildSrc`, included build/convention plugins, `subprojects` alternatives.
- [Gradle — Kotlin DSL](https://docs.gradle.org/current/userguide/kotlin_dsl.html): type-safe accessors và plugin application timing.
- [Gradle Plugin Portal — Versions Plugin](https://plugins.gradle.org/search?term=ben): ID `io.github.ben-manes.versions` và các phiên bản thực tế.
- [Gradle — Custom Plugins](https://docs.gradle.org/current/userguide/custom_plugins.html): plugin IDs và Gradle plugin marker publishing.
