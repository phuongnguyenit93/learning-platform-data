# Phân biệt `plugins { }`, `apply plugin` và `buildscript classpath` trong Gradle

Trong Gradle, **plugin** là một gói logic mở rộng build: nó có thể đăng ký task, tạo extension để cấu hình, thêm configurations, đặt conventions, và kết nối những công việc như biên dịch Java, chạy kiểm thử, tạo JAR hoặc xuất bản artifacts. Ba cú pháp sau đều thường xuất hiện trong các dự án Java:

```kotlin
plugins {
    id("java")
}
```

```kotlin
apply(plugin = "java")
```

```kotlin
buildscript {
    repositories {
        gradlePluginPortal()
    }
    dependencies {
        classpath("org.barfuin.gradle.taskinfo:org.barfuin.gradle.taskinfo.gradle.plugin:3.1.0")
    }
}
apply(plugin = "org.barfuin.gradle.taskinfo")
```

Chúng **không tương đương về cách Gradle tìm plugin, thời điểm cung cấp plugin classpath, cách Kotlin DSL sinh type-safe accessors và cách quản lý version**. Đặc biệt, `buildscript { dependencies { classpath(...) } }` mới chỉ **đưa mã build logic vào classpath của build script**; nó **không tự áp dụng plugin**.

Bài học này thuộc phần **Sử dụng plugin** của *Build Tool Gradle*. Nội dung gồm cơ chế plugin resolution và application, so sánh chi tiết Kotlin/Groovy DSL, các ví dụ Java 17+ chạy được, plugin portal và plugin marker, `pluginManagement`, `apply false`, version catalog, script plugin, custom/convention plugin, các trường hợp legacy cần giữ, lỗi thường gặp và bài tập tự kiểm tra.

## 1. Cần tách ba hành động khác nhau

Một plugin bên ngoài muốn tác động đến project thường cần ba việc:

1. **Xác định plugin cần dùng**: bằng plugin ID như `org.barfuin.gradle.taskinfo`, hoặc bằng class triển khai `Plugin<Project>`.
2. **Làm mã triển khai có sẵn**: Gradle core plugin đã nằm trong Gradle distribution; third-party plugin phải được resolve từ Plugin Portal/repository, included plugin build hoặc classpath đã có.
3. **Áp dụng plugin vào đúng đối tượng**: Gradle gọi logic `apply(...)` của plugin để thêm task/extensions/conventions vào `Project`, `Settings` hoặc `Gradle` tùy loại.

`plugins { }` thường kết hợp cả **request + resolution + application** theo cách declarative. `apply(plugin = "...")` làm bước **application**, với điều kiện plugin implementation **đã có sẵn** trong môi trường thích hợp. `buildscript.classpath` cung cấp mã cho **build script**, có thể là thư viện hỗ trợ hoặc implementation của plugin, nhưng **không thực thi `Plugin.apply` chỉ vì đã thêm dependency**.

Sơ đồ:

```text
plugins { id("some.plugin") version "1.0" }
    │
    ├─ Yêu cầu plugin ID / version
    ├─ Plugin resolution (repo, marker, implementation)
    └─ Apply plugin to target
            └─ tasks / extensions / configurations / conventions

buildscript {
    dependencies { classpath("group:artifact:1.0") }
}
    │
    └─ Nạp artifact vào buildscript classpath
            └─ Chưa nhất thiết áp dụng bất cứ plugin nào

apply(plugin = "some.plugin")
    │
    └─ Tìm plugin đã có sẵn bằng ID và áp dụng vào target
```

**Từ “classpath” ở đây là buildscript/plugin classpath**, không phải Java `compileClasspath`, `runtimeClasspath` hay `annotationProcessor` của ứng dụng.

## 2. Bảng so sánh nhanh

| Tiêu chí | `plugins { }` | `apply(plugin = "...")` | `buildscript { dependencies { classpath(...) } }` |
| --- | --- | --- | --- |
| Vai trò chính | Khai báo, resolve và mặc định **apply** plugin | **Apply** plugin đã có trên classpath/Gradle core | Thêm artifact cho **mã của build script** |
| Thường dùng cho | Core plugins, community plugins, convention plugins | Legacy builds, điều kiện/dynamic logic phù hợp, tình huống không dùng plugin DSL | Legacy third-party plugin, thư viện buildscript, plugin implementation cần nạp thủ công |
| Chỉ định plugin | `id("java")`, `id("g.plugin") version "x"` | `apply(plugin = "java")` | `classpath("group:artifact:version")` |
| Có tự apply plugin? | **Có**, trừ `apply false` | **Có** | **Không** |
| Có tự tải third-party plugin? | Có thể, qua plugin repositories/marker rules | Không chỉ bằng một ID; implementation phải sẵn có | Có thể tải artifact đã khai báo qua `buildscript.repositories` |
| Version của external plugin | Trong request, `pluginManagement`, alias hoặc convention | Không có tham số `version` tương đương trong `apply(plugin=...)` | Thường thể hiện trong Maven coordinates của `classpath` |
| Type-safe Kotlin DSL accessors | Tốt nhất khi plugin được apply trong `plugins` block của project script | Accessors cho extension plugin có thể **không được sinh** đúng thời điểm compile script | Chỉ đưa class vào classpath, không sinh model accessors do plugin chưa được apply |
| Repository | `pluginManagement.repositories`/Plugin Portal | Phụ thuộc cách plugin đã được nạp | `buildscript.repositories` |
| Gradle khuyến nghị cho build mới | **Ưu tiên** | Duy trì khi có lý do thực tế | Tránh dùng chỉ để apply một plugin có hỗ trợ Plugin DSL |

**Câu nhớ nhanh:** `plugins` là **khai báo plugin sẽ dùng**, `apply` là **kích hoạt plugin**, còn `buildscript classpath` là **cấp mã cho build script**. Ba điều này có thể phối hợp trong một build, nhưng không được coi như ba cách gọi cùng một câu lệnh.

## 3. Gradle plugin thực chất làm gì?

Đa số binary plugins implement giao diện Gradle:

```kotlin
import org.gradle.api.Plugin
import org.gradle.api.Project

class ExamplePlugin : Plugin<Project> {
    override fun apply(target: Project) {
        target.tasks.register("exampleTask") {
            doLast {
                println("Example task executed")
            }
        }
    }
}
```

Đây là **một class plugin minh họa**, không phải file build script chạy độc lập: muốn publish/apply bằng ID cần cấu hình Gradle plugin development/descriptor hoặc đặt class trong build logic được nạp đúng cách.

Khi plugin được apply lên `Project`, phương thức `apply(target)` có thể đăng ký `exampleTask`, cấu hình extension, dependencies và các tasks liên quan. **Áp dụng plugin không đồng nghĩa mọi task của plugin đều thực thi ngay**. Phần lớn các task được **đăng ký/cấu hình** trong Configuration; task actions chỉ thực sự thực thi khi graph chọn task ở Execution.

Ví dụ plugin `java` có thể đưa vào project:

- Source sets `main` và `test`.
- Các configuration như `implementation`, `runtimeOnly`, `testImplementation`.
- Các task như `compileJava`, `processResources`, `classes`, `jar`, `test`, `build`.
- Extension `java` để thiết lập toolchain, compatibility và cấu hình Java.

Đây là lý do thêm `implementation(...)` trước khi apply Java plugin có thể lỗi: configuration `implementation` do plugin tạo ra, chứ không phải một từ khóa Kotlin luôn tồn tại ở mọi Gradle project.

## 4. `plugins { }`: phương thức declarative được ưu tiên

Trong Gradle Kotlin DSL (`build.gradle.kts`):

```kotlin
plugins {
    id("java")
}
```

hoặc cú pháp Kotlin DSL cho core plugin:

```kotlin
plugins {
    java
}
```

Dùng `plugins` block giúp Gradle nhận diện plugin requests sớm để resolve plugin dependencies, tạo mô hình extension/configuration ổn định và sinh **type-safe accessors** cho Kotlin DSL. Gradle có thể tối ưu việc tải, chia sẻ classloader và hỗ trợ IDE autocomplete tốt hơn so với apply động.

Với community plugin:

```kotlin
plugins {
    id("org.barfuin.gradle.taskinfo") version "3.1.0"
}
```

Plugin trên là một ví dụ có thật trên Gradle Plugin Portal; phiên bản `3.1.0` xuất bản ngày 10/10/2026. Khi dùng thực tế, **kiểm tra compatibility của plugin với Gradle Wrapper đang sử dụng** trước khi nâng phiên bản hoặc đưa vào production.

### Không lẫn version của plugin và version của thư viện Java

```kotlin
plugins {
    id("org.barfuin.gradle.taskinfo") version "3.1.0"
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Đoạn này **chưa phải project độc lập** nếu chưa áp dụng Java plugin hoặc một plugin khác tạo `implementation`; cần thêm `java`/`application` khi demo Java. Ý nghĩa:

- `version "3.1.0"` thuộc **Gradle plugin**.
- `implementation(...:3.17.0)` thuộc **dependency của mã Java**.
- Plugin được resolve bằng plugin repositories, còn Commons Lang được resolve qua **project repositories**.
- `mavenCentral()` dưới project `repositories` không mặc định thay cho cấu hình repo plugin trong `pluginManagement`.

Plugin ID là **chuỗi ID**, không nhất thiết trùng tọa độ Maven của implementation artifact.

## 5. Ví dụ Java 17 chạy được với `plugins { }`

Ví dụ đầu tiên **chỉ dùng core Gradle plugins**, nên không cần Maven Central hay external plugin; có thể chạy offline nếu Gradle Wrapper/JDK đã sẵn có.

### 5.1. Cây tệp

```text
plugin-dsl-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/demo/Main.java
```

Nếu project đã có Wrapper, giữ nguyên phiên bản Wrapper phù hợp Java 17. Nếu chưa có, tạo Wrapper từ Gradle installation tương thích theo hướng dẫn chính thức. Không tự chế các file Wrapper.

### 5.2. `settings.gradle.kts`

```kotlin
rootProject.name = "plugin-dsl-demo"
```

### 5.3. `build.gradle.kts` đầy đủ

```kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

// Đọc trạng thái plugin ở Configuration, chỉ đưa Boolean vào task action.
val hasJava = plugins.hasPlugin("java")
val hasApplication = plugins.hasPlugin("application")

tasks.register("showPluginState") {
    doLast {
        println("java=" + hasJava + "; application=" + hasApplication)
    }
}
```

`application` là core plugin. Nó tự áp dụng Java plugin, vì vậy cả `java` extension và `application` extension tồn tại trong script. Việc các accessors `java { }` và `application { }` hoạt động là lợi ích rõ rệt của declarative plugin application trong Kotlin DSL.

### 5.4. `src/main/java/demo/Main.java`

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Hello from Gradle plugins DSL");
    }
}
```

### 5.5. Chạy

Linux/macOS:

```bash
./gradlew showPluginState --quiet
./gradlew run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat showPluginState --quiet
.\gradlew.bat run --quiet
```

**Stdout task `showPluginState`:**

```text
java=true; application=true
```

**Stdout từ Java `Main`:**

```text
Hello from Gradle plugins DSL
```

Đây là **hai lệnh riêng**; mỗi khối stdout thuộc lệnh tương ứng. Gradle có thể in log/cảnh báo riêng theo môi trường, nhưng `System.out.println` của chương trình có nội dung trên. Đặc biệt, Gradle đã **apply** cả hai plugins ngay ở lúc cấu hình build; chỉ task `showPluginState` hoặc `run` được chọn mới thực thi task actions liên quan.

## 6. `apply(plugin = "...")`: imperative/legacy application

Trong Kotlin DSL:

```kotlin
apply(plugin = "java")
```

Tương ứng Groovy DSL trong `build.gradle`:

```groovy
apply plugin: 'java'
```

Cú pháp này yêu cầu Gradle **áp dụng plugin ngay tại vị trí lệnh được thực thi**. Với core `java`, mã triển khai luôn có trong Gradle distribution nên không cần khai báo `buildscript.classpath`.

Một ví dụ Kotlin DSL:

```kotlin
apply(plugin = "java")

tasks.register("printPluginInfo") {
    val active = plugins.hasPlugin("java")
    doLast {
        println("Java plugin active: " + active)
    }
}
```

Chạy `./gradlew printPluginInfo --quiet`, stdout task:

```text
Java plugin active: true
```

Trong build script kiểu này, lệnh `apply` là imperative, không được phân tích sớm theo cùng cách với `plugins` DSL để sinh Kotlin type-safe accessors. Bạn **không nên giả định** có thể dùng `java { }` hay một accessor contributed extension ở cùng script như khi dùng `plugins { java }`.

### `apply` không mang version của external plugin

Sai về ý nghĩa:

```kotlin
// Không có cú pháp apply(plugin = ..., version = ...) tương đương:
apply(plugin = "com.example.some-plugin")
```

Nếu đó là non-core plugin và implementation chưa có sẵn trên buildscript/plugin classpath, Gradle không thể tìm chỉ bằng ID như với `plugins { id(...) version "..." }`. Phải làm plugin có sẵn qua cơ chế build logic được chấp nhận hoặc `buildscript { classpath(...) }`, sau đó mới apply.

Nếu đã có plugin implementation class trên classpath và muốn apply theo class, Gradle còn hỗ trợ dạng như `apply<MyPlugin>()` khi type `MyPlugin` nhìn thấy trong build script, nhưng đó không phải là phương thức ưu tiên cho build mới.

## 7. Ví dụ hoàn chỉnh thứ hai: dùng `apply` nhưng vẫn chạy Java application

Để so sánh công bằng với ví dụ `plugins { application }` ở mục 5, có thể **thay toàn bộ** `build.gradle.kts` của cùng project bằng:

```kotlin
import org.gradle.api.plugins.JavaApplication
import org.gradle.api.plugins.JavaPluginExtension

apply(plugin = "application")

// Do plugin không được apply trong plugins {} của chính script,
// truy cập extension theo class thay cho accessor application { }.
extensions.configure<JavaApplication> {
    mainClass.set("demo.Main")
}

extensions.configure<JavaPluginExtension> {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

val hasJava = plugins.hasPlugin("java")
val hasApplication = plugins.hasPlugin("application")

tasks.register("showPluginState") {
    doLast {
        println("java=" + hasJava + "; application=" + hasApplication)
    }
}
```

**Giữ nguyên** file `settings.gradle.kts` và `src/main/java/demo/Main.java` như mục 5. Đây là một `build.gradle.kts` độc lập; **không ghép cả hai ví dụ ở mục 5 và 7 vào cùng file**.

Chạy:

```bash
./gradlew showPluginState --quiet
./gradlew run --quiet
```

Kết quả từ task tương ứng:

```text
java=true; application=true
```

Và stdout Java:

```text
Hello from Gradle plugins DSL
```

Đoạn text cuối vẫn có chữ `plugins DSL` vì đó là chuỗi **do Java source tự in**, không phải Gradle tự đặt tên theo cách plugin được apply. Muốn thay nội dung, hãy sửa `Main.java`, không sửa dependency configuration.

### So sánh điều kiện cần

| Bản `plugins` | Bản `apply` |
| --- | --- |
| `plugins { application }` | `apply(plugin = "application")` |
| `application { mainClass.set(...) }` | `extensions.configure<JavaApplication> { mainClass.set(...) }` |
| `java { toolchain { ... } }` | `extensions.configure<JavaPluginExtension> { toolchain { ... } }` |
| Gradle nhận plugin request sớm và sinh accessors | Plugin được apply imperative; dùng API theo type/name để cấu hình |
| Dễ đọc, Gradle khuyên dùng | Hữu ích cho legacy/động, ít tiện hơn trong Kotlin DSL |

Bản `apply` **không thêm chức năng Java nào mới**. Nó chỉ minh họa cách bật core plugin qua cơ chế imperative và cách cấu hình extensions khi Kotlin DSL không có generated accessors.

## 8. `buildscript { dependencies { classpath(...) } }`: nạp mã, không tự apply

Đây là lỗi khái niệm phổ biến nhất:

```kotlin
buildscript {
    repositories {
        gradlePluginPortal()
    }
    dependencies {
        classpath("org.barfuin.gradle.taskinfo:org.barfuin.gradle.taskinfo.gradle.plugin:3.1.0")
    }
}
```

Đoạn này cho Gradle biết **lấy artifact nào để build script có thể dùng nó**. Nó chưa yêu cầu Gradle gọi logic plugin. Muốn plugin được áp dụng:

```kotlin
apply(plugin = "org.barfuin.gradle.taskinfo")
```

Khi đặt **đủ hai phần** trong một `build.gradle.kts`:

```kotlin
buildscript {
    repositories {
        gradlePluginPortal()
    }
    dependencies {
        classpath("org.barfuin.gradle.taskinfo:org.barfuin.gradle.taskinfo.gradle.plugin:3.1.0")
    }
}

apply(plugin = "org.barfuin.gradle.taskinfo")
```

Đây là ví dụ legacy có thể resolve plugin đã xuất bản trên Plugin Portal (đường dẫn plugin marker nêu trong tài liệu plugin). Nó **cần network/Gradle cache** và plugin version tương thích với Gradle Wrapper. Lệnh `./gradlew tasks --all` có thể dùng để kiểm tra tác động và tasks plugin bổ sung. Không cam kết một task name nhất định nếu chưa xem tài liệu version của plugin.

Cùng plugin với cú pháp được ưu tiên:

```kotlin
plugins {
    id("org.barfuin.gradle.taskinfo") version "3.1.0"
}
```

Không cần `buildscript.classpath` hay `apply(plugin=...)` thủ công trong cách này.

**Đừng ghép cả hai cách nạp/áp dụng vào cùng một build file để “cho chắc”.** Có thể gây duplicate plugin request, version conflicts, classloader ambiguity hoặc lỗi plugin đã ở classpath không xác định version. Chọn một cách nhất quán theo khả năng hỗ trợ của plugin.

## 9. `classpath` của `buildscript` khác `implementation` của Java project

Xét hai nơi khai báo trông giống nhau:

```kotlin
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath("org.yaml:snakeyaml:2.2")
    }
}

plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Ví dụ là **khung minh họa vai trò classpath**, không yêu cầu bạn dùng SnakeYAML trong build logic. Nó nhấn mạnh:

- `buildscript.classpath("org.yaml:snakeyaml:...")`: cho **mã Kotlin/Groovy build script** có thể dùng thư viện SnakeYAML trong configuration logic, nếu script import/call class của nó.
- `implementation("org.apache.commons:commons-lang3:...")`: cho **source Java dưới `src/main/java`** có Commons Lang khi compile và runtime.
- Thêm SnakeYAML vào buildscript classpath **không tự cho Java app import `org.yaml.snakeyaml.Yaml`**.
- Thêm Commons Lang vào `implementation` **không làm các class của nó tự sẵn có cho code chạy trong `build.gradle.kts`**.

Một sơ đồ:

```text
Gradle Daemon / Gradle build logic
    └─ buildscript classpath / plugin classloader
          ├─ custom plugin JAR
          └─ thư viện hỗ trợ build logic

JavaCompile / application runtime
    └─ compileClasspath / runtimeClasspath
          ├─ application classes
          └─ implementation / runtimeOnly dependencies
```

Đây là **hai thế giới classloading** khác nhau. Không sửa lỗi `package org.example does not exist` ở `src/main/java` bằng cách cho artifact vào `buildscript.dependencies.classpath`.

Ngược lại, nếu `build.gradle.kts` import `org.yaml.snakeyaml.Yaml` để xử lý metadata build-time, thêm SnakeYAML vào `implementation` không tự giải quyết lỗi compile của build script.

### Lưu ý security

Mã plugin và thư viện buildscript được thực thi trong **quá trình build**; chúng có thể truy cập hệ thống file, môi trường và thông tin CI theo quyền tiến trình Gradle. Chỉ dùng plugin/artifact từ nguồn tin cậy, kiểm tra version, checksum/dependency verification theo chính sách và tránh log secrets.

## 10. Ba loại repositories khác nhau

Gradle không dùng một khối `repositories { }` duy nhất cho mọi loại dependency.

| Khối | Đặt ở đâu | Dùng để giải quyết |
| --- | --- | --- |
| `pluginManagement { repositories { ... } }` | `settings.gradle.kts` | Các plugin requests từ `plugins { }` |
| `buildscript { repositories { ... } }` | `build.gradle.kts`/build logic | Các dependency trong `buildscript.dependencies.classpath` |
| `repositories { ... }` hoặc `dependencyResolutionManagement.repositories` | Project build script hoặc settings | Các **project dependencies** như `implementation`, `testImplementation` |

Ví dụ một settings file cấu hình rõ plugin repositories và app repositories:

```kotlin
// settings.gradle.kts
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "repository-boundaries"
```

Lưu ý đây là cấu hình minh họa khi bạn thực sự cần Maven Central trong plugin resolution. Đối với hầu hết plugins community trên Portal, `gradlePluginPortal()` là mặc định phù hợp. Một Maven repository riêng có thể chứa plugin implementation nhưng **thiếu plugin marker artifact** nên `plugins { id(...) version ... }` vẫn báo không tìm thấy plugin.

**Không sửa lỗi plugin missing bằng cách chỉ thêm `mavenCentral()` trong project `repositories`.** Cần kiểm tra `pluginManagement.repositories` hoặc `buildscript.repositories` theo chính kiểu khai báo bạn đang dùng.

### `pluginManagement` phải đặt ở đầu settings script

Ví dụ đúng:

```kotlin
// settings.gradle.kts
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}
rootProject.name = "demo"
include("app")
```

Không đặt `include("app")` hay root project logic trước `pluginManagement` rồi mong Gradle xử lý như khối cấu hình bình thường. Đây là một block đặc biệt được xử lý sớm.

## 11. Plugin ID, version, implementation artifact và marker artifact

Với plugin DSL:

```kotlin
plugins {
    id("org.barfuin.gradle.taskinfo") version "3.1.0"
}
```

Gradle cần biết cách đi từ **ID + version** đến artifact thực thi. Một cơ chế phổ biến là **plugin marker artifact** với tọa độ:

```text
<plugin-id>:<plugin-id>.gradle.plugin:<plugin-version>
```

Ví dụ:

```text
org.barfuin.gradle.taskinfo:
org.barfuin.gradle.taskinfo.gradle.plugin:
3.1.0
```

Đó là ba phần của **một Maven GAV**, được xuống dòng chỉ để giải thích:

```text
org.barfuin.gradle.taskinfo:org.barfuin.gradle.taskinfo.gradle.plugin:3.1.0
```

Marker thường trỏ tới **plugin implementation artifact**, không nhất thiết có cùng group/name với ID. Đó là lý do:

```kotlin
id("com.example.some-plugin") version "1.0"
```

không tự chuyển thành:

```kotlin
classpath("com.example:some-plugin:1.0")
```

trong mọi trường hợp. Bạn phải biết đúng Maven coordinates của implementation/marker, hoặc cấu hình `pluginManagement.resolutionStrategy` để ánh xạ ID sang module thật.

### Plugin metadata tối thiểu của binary plugin

Một plugin JAR thường cung cấp descriptor tại:

```text
META-INF/gradle-plugins/<plugin-id>.properties
```

Chẳng hạn:

```properties
implementation-class=com.example.build.MyPlugin
```

Đây là **format minh họa**, không phải file đủ để phát hành plugin. Descriptor cho phép Gradle map plugin ID tới implementation class khi artifact đã được nạp. Với `java-gradle-plugin`, Gradle có thể tạo plugin descriptors và marker publications theo cấu hình plugin development chuẩn.

Lỗi `Plugin with id '...' not found` thường do **không có ID trong plugin descriptors của classpath hiện có**, không phải do project thiếu Java source file.

## 12. `pluginManagement` đặt version và resolution rules tập trung

Một team có thể quản lý plugin repositories và default versions trong `settings.gradle.kts`:

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
    plugins {
        id("org.barfuin.gradle.taskinfo") version "3.1.0"
    }
}

rootProject.name = "managed-plugin-demo"
```

Và dùng trong `build.gradle.kts`:

```kotlin
plugins {
    id("org.barfuin.gradle.taskinfo")
}
```

Build script không phải lặp version vì settings đã cung cấp **mặc định version** cho plugin request phù hợp. Đây là cách **khai báo plugin DSL**, không phải cách nạp plugin vào `buildscript.classpath`.

### Khi Plugin Portal không cung cấp đúng mapping

Ví dụ rule để plugin ID do tổ chức bạn quản lý dùng implementation artifact riêng:

```kotlin
// settings.gradle.kts — mảnh ghép minh họa, tọa độ giả định.
pluginManagement {
    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-plugins")
        }
        gradlePluginPortal()
    }

    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "org.example.company-quality") {
                useModule("org.example.build:quality-gradle-plugin:1.0")
            }
        }
    }
}
```

URL và artifact trên là **placeholder kiến trúc**, không phải repository hay module được xác minh tồn tại. Bạn phải thay bằng cấu hình thật và xác nhận quyền truy cập. `useModule(...)` cho phép thay cơ chế plugin marker mặc định bằng tọa độ implementation đã được tổ chức xác định.

Chỉ nên dùng resolution rules để giải quyết yêu cầu plugin cụ thể, không override tất cả plugins ngẫu nhiên. Các rules phức tạp nên được review vì chúng ảnh hưởng đến **mã thực thi trong quá trình build**.

## 13. Ràng buộc cú pháp và vị trí của `plugins { }`

`plugins { }` không phải một Kotlin `if` block tùy ý. Gradle xử lý nó sớm và yêu cầu declaration có thể phân tích **tĩnh**, đặc biệt đối với plugin ID/version trong project build scripts.

Ví dụ không hợp lệ theo tinh thần constrained syntax:

```kotlin
// KHÔNG HỢP LỆ: plugins block không đặt bên trong if.
if (project.hasProperty("usePlugin")) {
    plugins {
        id("org.barfuin.gradle.taskinfo") version "3.1.0"
    }
}
```

Cũng không nên truyền một expression được tính tùy ý từ `project.version` vào `version` trong `plugins { }` của build script, vì Gradle cần biết plugin requests trước khi cấu hình project bình thường.

Các quy tắc:

- `plugins { }` của project script phải là **top-level block** trong `build.gradle(.kts)`.
- Nó phải nằm **trước phần lớn các blocks và statements cấu hình build khác**; `buildscript { }` và imports có ngoại lệ về cú pháp/đặt vị trí khi cần.
- Plugin IDs và versions trong project `plugins` DSL tuân theo dạng literals/aliases được Gradle hỗ trợ, không phải mọi Kotlin expression tùy ý.
- `plugins { }` thường dùng trong project/settings scripts; script plugins áp dụng bằng `apply(from = ...)` không được xử lý giống các project plugins declarations (precompiled script plugins là trường hợp build logic chuyên dụng có quy tắc riêng).
- `plugins { }` mặc định **apply ngay**, trừ khi dùng `apply false`.

Nếu cần chọn plugin theo điều kiện thật sự động, cân nhắc config ở **settings.pluginManagement**, convention plugin, hoặc `apply(plugin = ...)` khi plugin implementation sẵn có. Không đưa arbitrary `if` vào trong `plugins` block.

## 14. `apply false`: resolve/khai báo trước nhưng không áp dụng tại project hiện tại

Trong multi-project build, root thường muốn giữ version plugin tập trung nhưng chỉ subprojects cụ thể mới cần plugin.

```text
root/
├── settings.gradle.kts
├── build.gradle.kts
├── app/build.gradle.kts
└── library/build.gradle.kts
```

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "multi-plugin-demo"
include("app", "library")
```

**Root `build.gradle.kts`:**

```kotlin
plugins {
    id("org.barfuin.gradle.taskinfo") version "3.1.0" apply false
}
```

**`app/build.gradle.kts`:**

```kotlin
plugins {
    application
    id("org.barfuin.gradle.taskinfo")
}
```

**`library/build.gradle.kts`:**

```kotlin
plugins {
    `java-library`
}
```

Trong ví dụ:

- Root **không tự áp dụng** taskinfo plugin chỉ vì có `apply false`.
- `:app` chủ động yêu cầu plugin và không phải lặp version nếu plugin đã được quản lý trên classpath trong cùng build theo pattern đó.
- `:library` không áp dụng taskinfo plugin; nó chỉ dùng core `java-library`.
- `apply false` không phải “không tải gì”: Gradle vẫn xử lý plugin request và có thể cần resolve plugin artifact.

**Lưu ý kiến trúc:** Root `apply false` cho community plugin là một pattern được Gradle tài liệu hóa. Với build lớn, **convention plugins** trong included build/buildSrc và version catalogs thường dễ quản trị hơn là root ép plugin lên mọi subproject.

Đừng dùng `subprojects { apply(plugin = "...") }` mặc định như một cách tổ chức module mà không cân nhắc cross-project configuration, khả năng tái sử dụng và các chế độ như isolated projects.

## 15. Version Catalog alias cho plugins

Nếu nhiều subprojects cần chung version plugin, có thể lưu trong `gradle/libs.versions.toml`:

```toml
[versions]
taskinfo = "3.1.0"

[plugins]
taskinfo = { id = "org.barfuin.gradle.taskinfo", version.ref = "taskinfo" }
```

Sau đó trong `build.gradle.kts`:

```kotlin
plugins {
    alias(libs.plugins.taskinfo)
}
```

Tính năng này giúp version được quản lý tập trung, giảm lỗi copy-paste. `libs.plugins.taskinfo` là một **type-safe alias** được sinh từ version catalog. Alias trong `plugins` block vẫn được Gradle xử lý theo cơ chế plugin requests, **không biến thành `implementation(...)` hoặc `buildscript.classpath(...)`**.

Một số trường hợp precompiled script plugins/convention plugin builds có rules riêng cho plugin alias/version; hãy tham khảo cách đưa plugin dependency vào **build logic implementation** thay vì giả định mọi catalog accessor đều dùng được trong mọi `plugins { }` ở mọi loại script.

**Plugin version catalogs và dependency catalogs** cùng có thể nằm trong một TOML nhưng xuất hiện ở hai phần khác nhau:

```toml
[plugins]
taskinfo = { id = "org.barfuin.gradle.taskinfo", version = "3.1.0" }

[libraries]
commons-lang = { module = "org.apache.commons:commons-lang3", version = "3.17.0" }
```

`alias(libs.plugins.taskinfo)` là **plugin request**, còn `implementation(libs.commons.lang)` (sau khi apply Java plugin) là **dependency của source project**.

## 16. `apply(from = "...")` không giống `apply(plugin = "...")`

Hai dạng legacy trong Kotlin DSL:

```kotlin
apply(plugin = "java")
```

```kotlin
apply(from = "shared.gradle.kts")
```

Khác biệt hoàn toàn:

- `apply(plugin = "...")`: apply một **plugin bằng ID** đã có trên classpath.
- `apply(from = "...")`: thực thi và apply một **script plugin** từ file `.gradle.kts` hoặc `.gradle`.

Ví dụ file **`shared.gradle.kts`**:

```kotlin
tasks.register("helloFromScript") {
    doLast {
        println("Hello from applied script")
    }
}
```

File **`build.gradle.kts`**:

```kotlin
apply(from = "shared.gradle.kts")
```

Chạy:

```bash
./gradlew helloFromScript --quiet
```

Task action in:

```text
Hello from applied script
```

Đây là ví dụ script plugin hoàn chỉnh nếu file settings/Wrapper hợp lệ. Nhưng với build logic được tái sử dụng nhiều nơi, Gradle hiện **không khuyến nghị áp dụng ad-hoc script plugins** như một giải pháp kiến trúc lâu dài: chúng thường khó test, thiếu type-safe Kotlin DSL accessors và dễ phát sinh cross-project coupling.

**Không coi `apply(from = "shared.gradle.kts")` là tương đương `plugins { id("shared") }`.** Một file script local không tự trở thành một binary plugin đã đăng ký ID và marker artifact.

## 17. Khi nên dùng convention plugin thay script plugin

Nếu nhiều modules cùng yêu cầu Java toolchain 17, test conventions và compiler flags, việc copy `plugins { java }`, `java { ... }` vào từng `build.gradle.kts` sẽ dần khó bảo trì. **Convention plugin** chuyển logic dùng chung thành một plugin thật.

Các nguồn build logic thông dụng:

- **`buildSrc`**: Gradle tự build và đưa mã logic vào build scripts của build tương ứng; đơn giản khi quy mô vừa.
- **Included build** (ví dụ `build-logic`) qua `pluginManagement.includeBuild("build-logic")`: tách biệt build logic rõ ràng, dễ tái sử dụng/test độc lập.
- **Binary plugin được publish** bằng `java-gradle-plugin`: thích hợp khi nhiều repositories/teams sử dụng chung.

Ví dụ cấu trúc:

```text
repo/
├── settings.gradle.kts
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/kotlin/acme.java-conventions.gradle.kts
└── app/
    └── build.gradle.kts
```

**`repo/settings.gradle.kts`**:

```kotlin
pluginManagement {
    includeBuild("build-logic")
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "convention-demo"
include("app")
```

**`build-logic/build.gradle.kts`**:

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
```

**`build-logic/src/main/kotlin/acme.java-conventions.gradle.kts`**:

```kotlin
plugins {
    id("java")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

**`app/build.gradle.kts`**:

```kotlin
plugins {
    id("acme.java-conventions")
}
```

Ví dụ này minh họa **cấu trúc cốt lõi của precompiled script convention plugin**. Để chạy trong một môi trường cụ thể, `build-logic` có thể cần plugin repositories/Gradle Kotlin DSL provisioning hợp lệ và build/test conventions tương ứng; những file thiếu như Wrapper vẫn phải được tạo theo setup của project. Với core Java plugin, ví dụ không yêu cầu external taskinfo plugin.

Trong một precompiled script plugin, `plugins { }` dùng để **áp dụng các plugin mà convention plugin cần**, khác với ad-hoc `apply(from = ...)`. Tên plugin ID được suy từ file `acme.java-conventions.gradle.kts` khi không có package declaration.

### Tại sao convention plugin là lựa chọn dài hạn tốt hơn?

- Một điểm cấu hình chuẩn cho Java toolchain/test/dependency conventions.
- Được compile, test và IDE hiểu tốt hơn so với script plugin rời.
- Giảm cross-project configuration và việc áp dụng một plugin không cần thiết lên mọi module.
- Phù hợp hơn khi build sử dụng Configuration Cache và mô hình cô lập projects, nếu implementation cũng tuân thủ quy tắc tương ứng.

Không phải mọi file `.gradle.kts` đều là precompiled script plugin; sự khác biệt nằm ở **build logic project/Gradle Kotlin DSL plugin** tạo ra plugin ID, compile và publish/đưa nó lên plugin classpath.

## 18. Plugin ở settings khác plugin ở project

Gradle có nhiều đối tượng có thể là target của plugin:

| Plugin target | Nơi áp dụng điển hình | Mục đích |
| --- | --- | --- |
| `Plugin<Project>` | `build.gradle.kts` của root/subproject | Tạo tasks, extensions, configurations cho project |
| `Plugin<Settings>` | `settings.gradle.kts` | Thêm/điều chỉnh cấu hình build, project inclusion, plugin management |
| `Plugin<Gradle>` / init plugin | Initialization scripts phù hợp | Tác động phạm vi Gradle initialization/builds theo cơ chế init |

Một plugin chỉ implement `Plugin<Project>` **không tự áp dụng hợp lệ vào `Settings`** chỉ vì bạn đưa ID của nó vào `settings.gradle.kts`. Cần kiểm tra documentation của plugin nói rõ target và nơi nó được áp dụng.

Tương tự, `pluginManagement { }` là **cấu hình cách resolve plugins**, không phải tự động apply mọi plugin được liệt kê trong đó. Ví dụ:

```kotlin
// settings.gradle.kts
pluginManagement {
    plugins {
        id("org.barfuin.gradle.taskinfo") version "3.1.0"
    }
}
```

chỉ đặt default version cho request, **không có nghĩa plugin đã chạy** trong mọi project. Một project cần:

```kotlin
plugins {
    id("org.barfuin.gradle.taskinfo")
}
```

nếu muốn thực sự áp dụng taskinfo plugin lên project đó.

## 19. Vòng đời build: plugin được xử lý khi nào?

Gradle thường xét ba giai đoạn:

1. **Initialization**: tìm settings/build, xác định projects, cấu hình plugin management và các cấu trúc ban đầu.
2. **Configuration**: đánh giá settings/project build logic phù hợp, xử lý plugin requests, apply plugins, đăng ký/cấu hình tasks/extensions/dependencies, dựng task graph.
3. **Execution**: thực thi task actions được chọn sau khi Gradle quyết định cần chạy.

`plugins { }` có **cơ chế xử lý sớm**, nên Gradle resolve/apply plugin theo model phù hợp trước phần lớn project build script body. `apply(plugin = ...)` được thực thi **theo thứ tự của script**; nếu cố cấu hình extension trước khi plugin được apply, có thể không có extension đó.

Ví dụ thứ tự không đúng:

```kotlin
// MẢNH GHÉP KHÔNG ĐÚNG VỀ THỨ TỰ
// JavaPluginExtension chưa tồn tại vì chưa apply Java plugin.
extensions.configure<org.gradle.api.plugins.JavaPluginExtension> {
    sourceCompatibility = JavaVersion.VERSION_17
}

apply(plugin = "java")
```

Hãy apply plugin trước khi cấu hình extension nó cung cấp, hoặc ưu tiên `plugins { java }` để Gradle thiết lập model và Kotlin DSL accessors phù hợp.

**Một plugin được apply ở Configuration có thể đăng ký 100 tasks nhưng không chạy cả 100 tasks.** Chạy `./gradlew help` có thể cấu hình plugin mà không thực thi `compileJava` hoặc `test`. Vì vậy phân biệt log plugin application với log task execution.

## 20. Plugin và Configuration Cache

Các khái niệm khác nhau:

- **Plugin application**: thêm cấu trúc build, tasks và conventions.
- **Task graph**: danh sách các tasks được chọn và quan hệ dependency.
- **Configuration Cache**: có thể tái sử dụng kết quả configuration trên lần chạy tương thích sau, giúp không phải đánh giá lại tất cả build logic.

Không được suy rằng plugin “không apply” vì một `println` trong configuration không xuất hiện ở lần chạy có cache hit. Khi Configuration Cache được tái sử dụng, Gradle có thể bỏ qua đánh giá lại cấu hình theo cơ chế cache.

Trong ví dụ học tập, khi cần quan sát quá trình cấu hình từ đầu, có thể dùng:

```bash
./gradlew help --no-configuration-cache --console=plain
```

Nhưng đây là công cụ chẩn đoán, **không phải cách chữa lâu dài** mọi lỗi plugin. Nếu plugin không hỗ trợ Configuration Cache, cần nâng plugin, sửa custom build logic hoặc tuân theo yêu cầu Gradle về task isolation.

Một build mới nên tránh việc plugin tạo side effects ngoài ý muốn trong configuration, như viết file deployment hoặc gọi network tùy tiện khi chỉ chạy `help`.

## 21. Chẩn đoán: plugin “not found”

Thông báo kiểu:

```text
Plugin [id: 'org.example.my-plugin', version: '1.2.3'] was not found
```

thường đến từ **plugin DSL resolution**. Trình tự kiểm tra:

1. Plugin ID có viết đúng không? Phân biệt plugin ID với Maven `group:name`.
2. Version có tồn tại và tương thích với Gradle version/JDK không?
3. `pluginManagement.repositories` có chứa Plugin Portal hoặc repository lưu marker/implementation không?
4. Nếu dùng Maven repo tự host, đã publish **plugin marker** chưa? Nếu chưa, có cần `pluginManagement.resolutionStrategy.eachPlugin { useModule(...) }`?
5. Network/proxy/certificates/credentials có cho Gradle tải metadata/artifact không?
6. Khi plugin đã ở buildscript classpath, có đang khai báo version lần nữa trong `plugins` DSL gây classpath/version conflict không?
7. Nếu plugin local nằm ở included build, settings đã khai báo đúng `pluginManagement.includeBuild(...)` chưa?

**Không sửa bằng cách thêm plugin JAR vào Java `implementation`**. Điều đó làm mã ứng dụng phụ thuộc plugin nhưng không khiến plugin implementation được nạp vào Gradle plugin classpath.

## 22. Chẩn đoán: `Plugin with id ... not found` khi dùng `apply`

Với:

```kotlin
apply(plugin = "com.example.my-plugin")
```

nếu implementation plugin không có sẵn, Gradle có thể không tìm được ID. Khác với `plugins { id(...) version ... }`, cú pháp `apply` không tự mang version/repository để resolve third-party plugin.

Kiểm tra:

- Đã khai báo **đúng implementation/marker artifact** vào `buildscript.dependencies.classpath` hay chưa?
- `buildscript.repositories` có chứa repository phù hợp không?
- Plugin JAR có descriptor `META-INF/gradle-plugins/<plugin-id>.properties` hoặc plugin class thích hợp không?
- Có áp dụng sai plugin target (`Project` vs `Settings`) không?
- Có trộn Groovy `apply plugin:` vào file `.gradle.kts` hay Kotlin `apply(plugin = ...)` vào file Groovy không?

**Đặc biệt:** nếu `buildscript { dependencies { classpath(...) } }` đã resolve thành công mà `apply(plugin=...)` vẫn báo not found, lỗi có thể do artifact **không cung cấp plugin ID bạn yêu cầu**, chứ không phải do thiếu network.

## 23. Chẩn đoán: thiếu Kotlin type-safe accessor sau `apply`

Ví dụ:

```kotlin
apply(plugin = "application")

application {
    mainClass.set("demo.Main")
}
```

Trong một `build.gradle.kts` thông thường, `application { }` do plugin đóng góp có thể **không được sinh thành Kotlin type-safe accessor**, bởi plugin được apply imperative **sau giai đoạn Gradle xác định plugin requests cho schema tĩnh**.

Sửa bằng một trong hai cách:

**Cách A — Ưu tiên:**

```kotlin
plugins {
    application
}

application {
    mainClass.set("demo.Main")
}
```

**Cách B — Nếu phải giữ legacy apply:**

```kotlin
import org.gradle.api.plugins.JavaApplication

apply(plugin = "application")

extensions.configure<JavaApplication> {
    mainClass.set("demo.Main")
}
```

Không phải extension nào cũng có cùng tên/type trong Gradle; hãy tra API của plugin tương ứng. Một số plugin cung cấp named extensions, task types hoặc conventions đặc biệt. `configure<T>()` đòi hỏi type **có trên classpath build logic** và target extension đã được tạo.

## 24. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Unresolved reference: implementation` | Chưa apply Java/Java Library plugin hoặc script schema không có accessor | Dùng `plugins { java }`/`application`/convention plugin; kiểm tra task model |
| `Unresolved reference: application` khi đã `apply(plugin = "application")` | Không có generated Kotlin accessor | Dùng `plugins { application }` hoặc `extensions.configure<JavaApplication>` |
| Plugin ID not found trong `plugins` DSL | Sai ID/version, repo plugin thiếu, marker thiếu | Kiểm tra `pluginManagement` và Plugin Portal |
| Plugin ID not found trong `apply` | Implementation chưa có trên classpath hoặc descriptor sai | Kiểm tra `buildscript.classpath`/included build và plugin ID |
| Khai báo `classpath` rồi không có task của plugin | Chỉ tải artifact, chưa apply | Thêm `apply(plugin = "...")` hoặc chuyển sang `plugins` |
| Thêm `repositories { mavenCentral() }` mà plugin vẫn not found | Đã sửa project dependency repo, không phải plugin repo | Sửa `pluginManagement.repositories` hoặc `buildscript.repositories` |
| Thêm plugin vào `implementation` nhưng build không nhận plugin | Nhầm app dependencies với buildscript/plugin dependencies | Dùng Plugin DSL hoặc buildscript classpath |
| `plugins` block nằm trong `if` hoặc giữa script | Vi phạm constrained/top-level syntax | Đưa block lên đầu; dùng settings/convention khi cần logic động |
| `pluginManagement` nằm sau `include` | Sai vị trí của block xử lý sớm | Đưa `pluginManagement` lên đầu settings |
| Plugin đã ở classpath nhưng plugin DSL lại yêu cầu version khác | Classloader/version ambiguity | Quản lý version tại một nơi, tránh khai báo trùng |
| Root dùng `apply false` nhưng plugin không có trong root tasks | Đây là hành vi đúng: chưa apply lên root | Apply ở subproject cần dùng |
| Core plugin `java` không yêu cầu download | Core plugin được Gradle bundle | Không thêm buildscript classpath hoặc version cho core Java |
| `apply(from = ...)` được tưởng là apply plugin ID | Script plugin khác binary plugin | Dùng đúng `apply(plugin=...)` hoặc convention plugin |
| Convention plugin không tìm thấy | Chưa include build logic hoặc chưa tạo đúng plugin ID | Xem `pluginManagement.includeBuild`, tên file/descriptor |
| Gradle task xuất hiện nhưng không thực thi | Task chỉ đăng ký, không được chọn hoặc UP-TO-DATE | Xem `--dry-run`, task graph và task status |
| Plugin chưa hỗ trợ Configuration Cache | Plugin giữ state hoặc truy cập Project từ task action | Nâng plugin, sửa plugin/task code; không coi caching là lỗi syntax |
| Plugin mới cần JDK/Gradle version mới hơn | Binary compatibility mismatch | Xem plugin compatibility matrix và Wrapper/JVM version |
| CI tải plugin thất bại nhưng local chạy được | Proxy, credentials, offline/cache khác | Xác nhận plugin repos và network policy của CI |

## 25. Các lệnh Gradle hữu ích khi debug

Từ root của một project có Gradle Wrapper:

```bash
./gradlew --version
./gradlew help --stacktrace
./gradlew tasks --all
./gradlew help --info
./gradlew buildEnvironment
```

- `--version`: Gradle version và JVM đang chạy Gradle.
- `help --stacktrace`: xem call stack khi plugin resolution/application/configuration thất bại.
- `tasks --all`: kiểm tra tasks được plugin đưa vào **project hiện tại**, không nhất thiết chỉ ra plugin nào đã tạo từng task.
- `help --info`: thêm thông tin về plugin resolution/build configuration, nhưng có thể rất nhiều log.
- `buildEnvironment`: hiển thị **buildscript classpath dependencies**, khác với `dependencies --configuration runtimeClasspath` của Java project.

Đối với subproject `:app`, chạy:

```bash
./gradlew :app:tasks --all
./gradlew :app:buildEnvironment
```

Nếu nghi plugin chưa apply, kiểm tra các extension/tasks mà tài liệu plugin hứa sẽ cung cấp. Không dựa hoàn toàn vào việc có JAR trong Gradle cache: artifact được tải không có nghĩa plugin đã apply vào project.

Khi không chắc build sẽ publish/deploy, dùng `--dry-run` để kiểm tra task scheduling trước:

```bash
./gradlew :app:build --dry-run --console=plain
```

**Giới hạn:** dry-run bỏ qua task actions nhưng vẫn chạy configuration, nên plugin có side effects ở configuration có thể vẫn tác động. Không dùng dry-run như sandbox bảo mật.

## 26. So sánh Groovy DSL và Kotlin DSL để tránh lỗi sao chép code

| Mục đích | `build.gradle.kts` (Kotlin) | `build.gradle` (Groovy) |
| --- | --- | --- |
| Core plugin declarative | `plugins { id("java") }` | `plugins { id 'java' }` |
| Third-party plugin declarative | `plugins { id("x.y") version "1.0" }` | `plugins { id 'x.y' version '1.0' }` |
| Imperative apply | `apply(plugin = "java")` | `apply plugin: 'java'` |
| Script plugin apply | `apply(from = "extra.gradle.kts")` | `apply from: 'extra.gradle'` |
| Buildscript dep | `classpath("group:artifact:1.0")` | `classpath 'group:artifact:1.0'` |
| Plugin version alias | `alias(libs.plugins.some)` | `alias(libs.plugins.some)` |
| Plugin management | `pluginManagement { ... }` trong settings Kotlin | `pluginManagement { ... }` trong settings Groovy |

Một đoạn `apply plugin: 'java'` nguyên văn **không hợp lệ** trong `build.gradle.kts`; ngược lại, `apply(plugin = "java")` là Kotlin DSL, không nên copy sang Groovy file như thể cú pháp Groovy mặc định.

Tương tự, backtick syntax `plugins { `java-library` }` thuộc Kotlin DSL; trong Groovy thường dùng `plugins { id 'java-library' }`.

## 27. Nên chọn cách nào khi thiết kế một repository?

| Tình huống | Lựa chọn nên ưu tiên |
| --- | --- |
| Dự án Java mới, plugin core | `plugins { java }` hoặc `plugins { `java-library` }` |
| Gradle community plugin có ID/version từ Plugin Portal | `plugins { id("...") version "..." }` |
| Nhiều subprojects dùng chung version plugin | Version catalog/pluginManagement; có thể root `apply false` |
| Nhiều subprojects chia sẻ conventions thực sự | Precompiled/binary convention plugin trong included build hoặc `buildSrc` |
| Plugin organization phát hành private, marker có đủ | `pluginManagement.repositories` + `plugins` |
| Private plugin không có marker theo convention | `pluginManagement.resolutionStrategy.useModule` hoặc cân nhắc legacy buildscript nếu cần |
| Legacy script nạp plugin artifact thủ công | `buildscript.classpath` + `apply(plugin=...)`, lên kế hoạch migrate |
| Thư viện chỉ dùng bởi **mã build script** | `buildscript.classpath` hoặc dependency của convention plugin, tùy kiến trúc |
| Mã Java application cần thư viện | `dependencies { implementation(...) }`, không dùng buildscript.classpath |
| Chỉ cần chạy thêm vài câu task registration local | Task trong `build.gradle.kts` hoặc precompiled convention plugin nếu tái sử dụng |
| File script plugin cũ `extra.gradle.kts` | `apply(from=...)` có thể duy trì, nhưng nên migrate khi logic lớn và dùng nhiều nơi |

**Khuyến nghị thiết kế:** với build mới, áp dụng plugin bằng `plugins { }` trước, sau đó cấu hình plugin qua typed DSL. Chỉ dùng `buildscript` + `apply` khi có yêu cầu cụ thể không thể giải quyết bằng Plugin DSL hoặc đang bảo trì legacy build có kế hoạch chuyển đổi.

## 28. Quy trình migrate từ legacy `buildscript` sang `plugins`

Giả sử build cũ:

```kotlin
buildscript {
    repositories {
        gradlePluginPortal()
    }
    dependencies {
        classpath("org.barfuin.gradle.taskinfo:org.barfuin.gradle.taskinfo.gradle.plugin:3.1.0")
    }
}

apply(plugin = "org.barfuin.gradle.taskinfo")
```

Lựa chọn migration khi plugin hỗ trợ Plugin DSL:

```kotlin
plugins {
    id("org.barfuin.gradle.taskinfo") version "3.1.0"
}
```

Thực hiện theo thứ tự:

1. **Ghi nhận môi trường**: version Gradle Wrapper/JDK, plugin version, task/configuration do plugin tạo, cách CI dùng chúng.
2. **Xác minh plugin ID và nguồn**: Plugin Portal/official docs; artifact trên `classpath` có thể là implementation JAR khác marker ID.
3. **Cấu hình `pluginManagement.repositories`** nếu dùng private repo hoặc plugin không nằm ở default Plugin Portal.
4. **Di chuyển request vào `plugins { }`** với version đúng; bỏ `buildscript.classpath` và `apply` chỉ phục vụ chính plugin này, nhưng giữ các buildscript libraries khác còn được sử dụng thực sự.
5. **Sửa Kotlin DSL accesses**: chuyển từ `extensions.configure<T>()` sang accessors typed khi hợp lý.
6. **Chạy các tasks chính** và so output của project, kiểm tra CI, Configuration Cache và dependency/classpath diagnostics khi có khác biệt.
7. **Review version management**: nếu nhiều modules, đưa version vào `pluginManagement` hoặc catalog; tránh định nghĩa nhiều nơi.
8. **Giữ khả năng rollback** nếu plugin version/Gradle compatibility có khác biệt với legacy.

Đừng chỉ xóa `buildscript` nếu bên trong còn thư viện được script import trực tiếp, vì khi đó build script có thể compile fail dù plugin migration đã đúng.

## 29. Tự kiểm tra kiến thức

**Câu 1.** `buildscript { dependencies { classpath("g:a:v") } }` có áp dụng plugin trong artifact không?

**Đáp:** Không tự động. Nó chỉ đưa artifact vào classpath của build script. Cần `apply(plugin = "...")` hoặc dùng Plugin DSL nếu plugin hỗ trợ.

**Câu 2.** Vì sao `plugins { application }` thường cho phép viết `application { mainClass.set(...) }`, còn `apply(plugin = "application")` có thể không?

**Đáp:** `plugins` được Gradle xử lý sớm để sinh type-safe Kotlin DSL accessors. `apply` là imperative; có thể cần `extensions.configure<JavaApplication>`.

**Câu 3.** `apply(plugin = "java")` có cần `buildscript.classpath` không?

**Đáp:** Không. Core Java plugin đã được Gradle distribution cung cấp.

**Câu 4.** Dùng `plugins { id("org.example.plugin") version "1.0" }` mà Gradle báo plugin không tìm thấy. Nên thêm `mavenCentral()` vào project repositories là đủ chưa?

**Đáp:** Chưa. Plugin DSL resolution dùng plugin repositories, chủ yếu do `pluginManagement.repositories` cấu hình, và có thể yêu cầu plugin marker/resolutionStrategy.

**Câu 5.** Trong `build.gradle.kts`, `apply(plugin = "java")` và `apply(from = "java.gradle.kts")` có cùng nghĩa không?

**Đáp:** Không. Dạng `plugin` dùng plugin ID, dạng `from` apply một script file.

**Câu 6.** `plugins { id("some.plugin") version "1.0" apply false }` có thêm tasks của plugin vào project hiện tại không?

**Đáp:** Không. Plugin request được khai báo/resolve nhưng **không apply** vào project hiện tại. Một project muốn dùng plugin phải apply nó riêng.

**Câu 7.** Thêm SnakeYAML vào `buildscript.classpath` có làm `src/main/java` import `org.yaml.snakeyaml.Yaml` được không?

**Đáp:** Không. Buildscript classpath phục vụ Gradle build logic; Java application compileClasspath là một tập dependencies khác.

**Câu 8.** `pluginManagement.plugins` khai báo version plugin có đồng nghĩa plugin đã chạy ở mọi subproject không?

**Đáp:** Không. Nó chỉ đặt default version cho plugin requests; mỗi project phải có request/apply thích hợp.

**Câu 9.** Khi nào có thể chọn convention plugin thay vì một file `shared.gradle.kts` apply từ nhiều projects?

**Đáp:** Khi logic cần reuse, test, quản lý dependency/plugin versions rõ ràng, type-safe accessors, và khả năng maintain/Configuration Cache tốt hơn.

**Câu 10.** `gradlew buildEnvironment` và `gradlew dependencies --configuration runtimeClasspath` có cùng mục đích không?

**Đáp:** Không. `buildEnvironment` báo buildscript classpath dependencies, còn `dependencies` theo `runtimeClasspath` báo dependencies dùng cho Java/app runtime.

**Câu 11.** Một plugin chỉ hỗ trợ `Plugin<Settings>`, có thể áp dụng nó trong `:app/build.gradle.kts` như `Plugin<Project>` không?

**Đáp:** Không. Plugin target type khác nhau; phải đọc tài liệu plugin và dùng đúng settings scope.

**Câu 12.** Sao chép dòng `apply plugin: 'java'` từ blog Groovy vào `build.gradle.kts` bị lỗi. Cần viết thế nào?

**Đáp:** Dùng `apply(plugin = "java")`, hoặc tốt hơn `plugins { java }` nếu đang tạo build mới.

## 30. Checklist trước khi kết luận plugin setup đúng

- [ ] Xác định plugin là **core**, community, custom hay convention plugin.
- [ ] Dùng `plugins { }` ở nơi có thể, với đúng ID/version hoặc version catalog alias.
- [ ] Không lẫn plugin ID với implementation artifact coordinates.
- [ ] Phân biệt rõ plugin repositories, buildscript repositories và project dependency repositories.
- [ ] Không dùng `buildscript.classpath` như cách tự apply plugin.
- [ ] Khi legacy apply non-core plugin, đảm bảo implementation và plugin descriptor đã có trên classpath.
- [ ] Với Kotlin DSL, xem plugin được apply từ `plugins` block hay imperative để dùng accessors hoặc `extensions.configure<T>` phù hợp.
- [ ] `pluginManagement` được đặt đúng ở đầu settings script.
- [ ] Root `apply false` không được coi là đã apply plugin cho mọi module.
- [ ] Không lạm dụng `subprojects { apply(...) }` khi có thể dùng convention plugin.
- [ ] Kiểm tra Plugin Portal/Gradle Wrapper/JDK compatibility trước khi cập nhật third-party plugin.
- [ ] Chạy `./gradlew tasks --all`, `help`, tasks thực tế và `buildEnvironment` đúng project khi cần debug.
- [ ] Không đọc stdout configuration ở một lần Configuration Cache hit rồi kết luận plugin chưa apply.
- [ ] Không đưa plugin JAR vào Java `implementation` trừ khi application thật sự sử dụng artifact đó theo nghĩa runtime library.

## 31. Tài liệu tham khảo chính thức

- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): `plugins` DSL, legacy `apply`, `buildscript`, `apply false`, `pluginManagement`, marker artifacts, version catalog.
- [Gradle — Introduction to Plugins](https://docs.gradle.org/current/userguide/plugins.html): core/community/custom, script/precompiled/binary plugins và Project/Settings/Gradle scope.
- [Gradle — Plugin Basics](https://docs.gradle.org/current/userguide/plugin_basics.html): plugin application, tasks, extensions, lifecycle.
- [Gradle — Best Practices](https://docs.gradle.org/current/userguide/best_practices_general.html): ưu tiên dùng `plugins { }` thay legacy `apply`.
- [Gradle — Plugin Development](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): các lựa chọn triển khai plugin.
- [Gradle — Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html): tách plugin repositories khỏi dependency repositories.
- [Gradle — Migrating Groovy to Kotlin DSL](https://docs.gradle.org/current/userguide/migrating_from_groovy_to_kotlin_dsl.html): khác biệt `apply` và generated type-safe accessors.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): cách `application` áp dụng Java plugin và chạy Java main.
- [Gradle — Kotlin DSL API: JavaApplication](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.plugins/-java-application/index.html): cấu hình extension qua type.
- [Gradle Plugin Portal — org.barfuin.gradle.taskinfo](https://plugins.gradle.org/plugin/org.barfuin.gradle.taskinfo): plugin ID/version và cách dùng Plugin DSL hoặc legacy `buildscript.classpath`.
