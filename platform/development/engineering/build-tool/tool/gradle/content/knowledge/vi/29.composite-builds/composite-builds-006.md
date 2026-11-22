# Plugin development build và includeBuild trong pluginManagement

## 1. Bài toán: viết và sử dụng Gradle plugin ngay trong cùng workspace

Giả sử tổ chức phát triển một **Gradle plugin nội bộ** để tạo task, cấu hình compiler hoặc áp dụng convention cho nhiều dự án Java. Khi đang sửa plugin, quy trình “sửa mã → build JAR → publish lên repository → nâng version trong ứng dụng → kiểm thử” làm vòng phản hồi chậm và dễ lấy nhầm binary cũ.

**Gradle Composite Build** cho phép dùng một **plugin development build** (ví dụ thư mục `plugin-build/` hoặc `build-logic/`) trực tiếp từ consumer build:

```groovy
// settings.gradle của consumer
pluginManagement {
    includeBuild('plugin-build')
}
```

Lúc này một build độc lập cung cấp **plugin IDs**, còn các project trong consumer chỉ cần request đúng ID:

```groovy
// app/build.gradle của consumer
plugins {
    id 'com.example.trace'
}
```

Không cần publish plugin lên Gradle Plugin Portal hay Maven repository trước khi thử nghiệm. Khi mã nguồn của plugin build thay đổi, Gradle có thể biên dịch lại plugin build và consumer dùng kết quả local theo cơ chế task inputs/cache.

**Trọng tâm bài:** `pluginManagement { includeBuild(...) }` khác `includeBuild(...)` thông thường ở **thời điểm đăng ký plugin provider**. Nó đặc biệt cần thiết để một **Settings plugin** được sử dụng **ngay trong `settings.gradle`**, vì Gradle phải giải quyết settings `plugins { }` trước khi đi vào phần thân settings script.

Sau bài học, bạn sẽ biết:

1. Phân biệt project, subproject, included build, plugin build và plugin ID.
2. So sánh `include`, top-level `includeBuild`, `pluginManagement.includeBuild` và `--include-build` CLI.
3. Tạo plugin development build Java 17+ với `java-gradle-plugin`, đăng ký **Project plugin** và **Settings plugin** trong cùng một build.
4. Áp dụng hai plugins bằng `plugins { }` từ đúng scope, chạy task/plugin và Java application có stdout xác định.
5. Hiểu plugin resolution và dependencies/substitution, ranh giới repositories, version catalogs và properties của các builds.
6. Kiểm thử plugin bằng **Gradle TestKit**, `GradleRunner` và `validatePlugins`.
7. Nhận biết lựa chọn **precompiled convention plugins** ở `build-logic` thay cho Java binary plugins.
8. Xử lý lỗi về plugin IDs, `implementationClass`, plugin timing, build tree path, Gradle/JDK compatibility và CI.

Ví dụ dùng **Gradle Groovy DSL**, Java 17+, một Gradle Wrapper hiện đại và mã nguồn độc lập. Code Java trong lab chính chỉ dùng Java standard library cùng Gradle API có sẵn trong plugin development plugin. Phần TestKit thêm JUnit 5.11.4 từ Maven Central.

## 2. Cấu trúc multi-project và composite build không giống nhau

**Multi-project build** gồm root project và các subprojects cùng chia sẻ một Settings instance:

```groovy
rootProject.name = 'consumer'
include 'app'
```

Ở đây có project paths `:` và `:app`. Khi dùng `project(':app')`, bạn nói tới một project **trong consumer build**.

**Composite build** ghép nhiều Gradle builds. Mỗi included build có `settings.gradle`, project hierarchy, source sets, Gradle build script, dependencies và repository policy riêng:

```text
consumer/                        main/including build
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── app/
│   ├── build.gradle              consumer subproject :app
│   └── src/main/java/...
└── plugin-build/                 included build riêng
    ├── settings.gradle
    ├── build.gradle
    └── src/main/java/...
```

Cơ chế inclusion không tự biến `plugin-build` thành subproject. Không thể gọi `project(':plugin-build')` từ consumer, trừ khi bạn **thật sự** include nó bằng `include('plugin-build')` — điều mà lab này **không làm**.

Trong composite, task của included build có thể được gọi bằng build-tree path như `:plugin-build:validatePlugins`. Đó là **task path**, không phải bằng chứng rằng included build là một child Project của consumer.

### 2.1. Bảng so sánh bốn phương thức

| Cú pháp | Tác dụng | Phạm vi quan trọng |
| --- | --- | --- |
| `include 'app'` | Thêm subproject `:app`. | **Một build**, cùng settings/project tree. |
| `includeBuild('../shared-lib')` | Đưa build thư viện khác vào composite. | Build riêng; thường phục vụ external dependency substitution. |
| `pluginManagement { includeBuild('plugin-build') }` | Đăng ký **plugin provider** từ included build. | Trước settings plugin resolution, có thể cung cấp Settings/Project plugins. |
| `gradle --include-build ../other-build` | Ghép build từ command line tại invocation. | Có thể dùng cho composite/library; không phải cách đáng tin bằng settings cho unpublished plugins với `plugins { }`. |

`includeBuild` trỏ đến **thư mục root của một Gradle build**, thông thường là nơi có `settings.gradle`. Relative path tính từ directory chứa settings script, không phải current working directory ngẫu nhiên của một plugin implementation.

### 2.2. Plugin build là build độc lập, không phải module dependency

Phản ví dụ từ `app/build.gradle`:

```groovy
// SAI cho lab: plugin-build không phải subproject.
dependencies {
    implementation project(':plugin-build')
}
```

`implementation` là một **dependency bucket** cho code/runtime của ứng dụng; nó không có nhiệm vụ load `Plugin<Project>` vào Gradle. Cách đúng là khai báo plugin **trong `plugins { }`** bằng ID được plugin development build cung cấp.

Nếu included build thật sự là một library, dependency substitution lại có quy tắc khác; sẽ phân biệt ở phần 10.

## 3. Vì sao đặt includeBuild trong pluginManagement?

Gradle xử lý settings file rất sớm để xác định cấu trúc build và cách resolve plugins. Trong Groovy DSL, cấu trúc khuyến nghị:

```groovy
pluginManagement {
    includeBuild('plugin-build')
    repositories {
        gradlePluginPortal()
    }
}

plugins {
    id 'com.example.settings-info'
}

rootProject.name = 'consumer'
include 'app'
```

Trình tự logic:

1. Gradle biết `pluginManagement` và các plugin repositories/plugin builds.
2. Gradle xử lý `plugins { }` dành cho **Settings**.
3. Settings plugin, nếu tìm được, được apply lên đối tượng `Settings`.
4. Phần còn lại của `settings.gradle` khai báo root project, include subprojects và build logic.
5. Gradle mới đánh giá các project build scripts và xử lý các project plugin requests.

**Đặt top-level `includeBuild('plugin-build')` ở phía dưới settings `plugins { }` là quá muộn để cung cấp Settings plugin cho block đó.** Đây là lý do cụ thể khiến `pluginManagement.includeBuild` có ý nghĩa riêng.

Theo tài liệu Gradle Composite Builds:

- Plugin dùng trong `build.gradle` có thể được cung cấp qua included build. Đăng ký nó trong `pluginManagement` giúp plugin DSL có nguồn local minh bạch.
- Với **Settings plugin**, việc include plugin development build **trong pluginManagement** là cách cần dùng để resolver biết nó từ sớm.
- `--include-build` từ CLI không nên dùng thay cơ chế này khi bạn cần `plugins { }` luôn tìm đúng unpublished plugin.

### 3.1. Project plugin và Settings plugin khác target

| Loại plugin | Java interface | Nơi áp dụng |
| --- | --- | --- |
| Project plugin | `Plugin<Project>` | `build.gradle` của project tương ứng. |
| Settings plugin | `Plugin<Settings>` | `settings.gradle` của build. |
| Init plugin | `Plugin<Gradle>` | Init scripts/lifecycle của Gradle. |

Một `Plugin<Project>` nhận Project khi `apply`, có thể đăng ký task cho project đó. Nó không trở thành Settings plugin chỉ vì bạn chuyển câu lệnh `id 'some.plugin'` lên settings script. Đúng scope phải được chọn ngay khi thiết kế plugin.

### 3.2. Plugin repositories không phải project repositories

```groovy
pluginManagement {
    includeBuild('plugin-build')
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

Đây là **plugin resolution repositories** của consumer. Nó không tự cung cấp external Java libraries cho `app` hoặc JUnit dependencies của plugin-build. Muốn resolve `implementation 'group:artifact:version'`, hãy cấu hình **project dependency repositories** qua `repositories { }` hoặc `dependencyResolutionManagement`.

**Một plugin ID** như `com.example.trace` không phải module coordinate `com.example:trace:1.0.0`. Plugin request có thể được đáp ứng từ included plugin build hoặc published marker artifacts; normal dependencies dùng group/name/version và variant attributes.

## 4. Tạo plugin development build bằng java-gradle-plugin

Gradle có core plugin `java-gradle-plugin` hỗ trợ **plugin authoring**:

```groovy
plugins {
    id 'java-gradle-plugin'
}
```

Nó cung cấp Gradle API cho Java/Groovy/Kotlin plugin code, sinh **plugin descriptors**, hỗ trợ validation và TestKit. Nó khác với `java` hay `application` dùng cho ứng dụng production.

### 4.1. Vì sao cần plugin ID và implementationClass?

Plugin development build thường khai báo:

```groovy
gradlePlugin {
    plugins {
        tracePlugin {
            id = 'com.example.trace'
            implementationClass = 'example.buildlogic.TracePlugin'
        }
    }
}
```

`tracePlugin` là tên declaration trong Groovy DSL. **Plugin ID thật** là `com.example.trace`, được consumer request trong `plugins { }`. `implementationClass` là fully qualified name của Java class implements `Plugin<Project>`.

Plugin descriptors trong JAR (ví dụ `META-INF/gradle-plugins/com.example.trace.properties`) ánh xạ ID tới implementation class. Gradle `java-gradle-plugin` tự tạo descriptors theo `gradlePlugin.plugins`; bạn không cần tự viết file properties trong lab.

Một **plugin-build có thể đăng ký nhiều plugin IDs**, kể cả loại Project và Settings, như ví dụ dưới đây.

### 4.2. Các task hỗ trợ plugin development

| Task | Mục đích |
| --- | --- |
| `compileJava` | Compile plugin implementation classes. |
| `pluginDescriptors` | Sinh metadata mapping plugin ID → implementationClass. |
| `jar` | Đóng gói plugin implementation và descriptors thành plugin JAR. |
| `validatePlugins` | Kiểm tra plugin tasks/transform types theo validation rules, đặc biệt task property annotations. |
| `pluginUnderTestMetadata` | Sinh thông tin classpath cho TestKit functional tests. |
| `test` | Chạy unit/functional tests của plugin build nếu có test framework. |

`validatePlugins` **không** thực thi mọi use case của plugin; một plugin có thể pass validation nhưng vẫn tạo task sai logic. TestKit mới là nơi thích hợp để chạy một build fixture và assert hành vi thật.

## 5. Lab: một included plugin build cung cấp Project + Settings plugins

Dự án mẫu hoàn chỉnh bên dưới sử dụng **Java 17+**, Gradle **Groovy DSL**. Plugin build chứa **hai Java classes**, consumer chứa một Java application. Mọi file được ghi đúng path/packaging thì có thể chạy với Gradle Wrapper/JDK phù hợp, không cần publish plugin.

**Kết quả mong đợi:**

- Lệnh `:app:pluginStatus` in `plugin-status=loaded`.
- Lệnh `:app:run` in `Hello, composite!`.
- Lệnh `:app:run --args="Team"` in `Hello, Team!`.
- Settings plugin đặt một extra property mà settings consumer kiểm tra được ngay sau `plugins { }`.

### 5.1. Cây thư mục

```text
consumer/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── app/
│   ├── build.gradle
│   └── src/main/java/example/app/Main.java
└── plugin-build/
    ├── settings.gradle
    ├── build.gradle
    └── src/main/java/example/buildlogic/
        ├── TracePlugin.java
        └── SettingsInfoPlugin.java
```

Wrapper được tạo bằng `gradle wrapper` hoặc `gradle init` với Gradle tương thích; nó không tự xuất hiện chỉ vì bạn tạo build files. Gradle 9 cần JVM chạy Gradle tối thiểu Java 17. Code plugin được compile với `options.release = 17` trong lab.

### 5.2. File consumer/settings.gradle

```groovy
pluginManagement {
    includeBuild('plugin-build')
    repositories {
        gradlePluginPortal()
    }
}

plugins {
    id 'com.example.settings-info'
}

rootProject.name = 'consumer'
include 'app'

// Đảm bảo Settings plugin local đã được áp dụng.
assert extensions.extraProperties.get('pluginOrigin') ==
    'included-build'
```

Cần quan sát:

- `pluginManagement` nằm **đầu file**, trước settings `plugins { }`.
- `com.example.settings-info` là **Settings plugin ID** mà plugin-build đăng ký; không có `version '1.0.0'` trong request vì consumer đang dùng local plugin provider.
- `include 'app'` tạo project `:app`; không có `include 'plugin-build'`.
- `assert` xác nhận plugin đã chạy và đặt `pluginOrigin`. Nếu plugin implementation/version/path không đúng, build sẽ fail ở initialization/configuration; sẽ không chạy tiếp app như thể không có gì xảy ra.
- `gradlePluginPortal()` (DSL ở đây là `gradlePluginPortal()`) cho external plugin resolution khi cần. Plugin lab được nhận từ included build, không phải từ Portal.

### 5.3. File consumer/build.gradle

```groovy
// Root project chỉ quản lý cấu trúc, không apply Java.
```

File có thể chỉ chứa comment, root không nhất thiết là Java project. Không apply `java` cho root chỉ vì `:app` dùng Java.

### 5.4. File plugin-build/settings.gradle

```groovy
rootProject.name = 'plugin-build'
```

Đây là Settings riêng của included build. Nó có repositories/plugin policies và properties riêng khi dự án phát triển phức tạp hơn; không tự kế thừa `consumer/settings.gradle`.

### 5.5. File plugin-build/build.gradle

```groovy
plugins {
    id 'java-gradle-plugin'
}

group = 'example.buildlogic'
version = '1.0.0'

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

gradlePlugin {
    plugins {
        tracePlugin {
            id = 'com.example.trace'
            implementationClass =
                'example.buildlogic.TracePlugin'
        }

        settingsInfoPlugin {
            id = 'com.example.settings-info'
            implementationClass =
                'example.buildlogic.SettingsInfoPlugin'
        }
    }
}
```

**Ý nghĩa:**

1. `java-gradle-plugin` là Gradle core plugin; nó hỗ trợ biên dịch plugin code, descriptors, TestKit.
2. `group/version` là metadata của artifact trong included build, **không** đổi tên plugin ID; consumer vẫn request bằng `com.example.trace`.
3. `options.release=17` nhắm class bytecode Java 17, không tự provision JDK 17; compiler và JVM chạy Gradle phải tương thích.
4. `gradlePlugin.plugins` đăng ký **hai IDs** độc lập và hai implementations. Tên declaration như `tracePlugin` không phải tên class, không phải ID request.
5. `implementationClass` phải khớp Java package/class; sai chữ hoa/đường dẫn có thể khiến Gradle không load được class hoặc báo `ClassNotFoundException`.
6. Không cần `repositories { }` trong baseline, vì plugin dùng Gradle API có sẵn. Khi thêm JUnit để test hoặc external plugin libraries, cần repository riêng ở plugin-build.

### 5.6. Java Project plugin: TracePlugin.java

**Path:** `plugin-build/src/main/java/example/buildlogic/TracePlugin.java`.

```java
package example.buildlogic;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class TracePlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getTasks().register("pluginStatus", task -> {
            task.setGroup("verification");
            task.setDescription(
                    "Prints a marker from the included plugin build.");
            task.doLast(ignored ->
                    System.out.println("plugin-status=loaded"));
        });
    }
}
```

**Cơ chế:**

- `Plugin<Project>` cho phép Gradle apply implementation lên `:app`.
- `project.getTasks().register` đăng ký một task **lazily**; không gọi `create` eagerly.
- Task `pluginStatus` thuộc `:app` vì consumer request plugin trong `app/build.gradle`.
- `setGroup("verification")` giúp task dễ thấy khi chạy `:app:tasks`.
- `doLast` in một marker cố định; lambda không đọc `Project` trong task action.
- Plugin **không tự apply vào tất cả subprojects** của consumer; project nào muốn task phải request/apply plugin.

Plugin code **chạy trong Gradle build environment**, không phải class được import vào `Main.java` của app.

### 5.7. Java Settings plugin: SettingsInfoPlugin.java

**Path:** `plugin-build/src/main/java/example/buildlogic/SettingsInfoPlugin.java`.

```java
package example.buildlogic;

import org.gradle.api.Plugin;
import org.gradle.api.initialization.Settings;

public final class SettingsInfoPlugin implements Plugin<Settings> {
    @Override
    public void apply(Settings settings) {
        settings.getExtensions()
                .getExtraProperties()
                .set("pluginOrigin", "included-build");
    }
}
```

Plugin:

- Implement `Plugin<Settings>`, không phải Project plugin.
- Được apply khi consumer settings xử lý `plugins { id 'com.example.settings-info' }`.
- Đặt extra property `pluginOrigin` trên **Settings**, không phải lên một subproject.
- Không in bất kỳ dòng stdout nào; giúp lệnh `:app:pluginStatus` có output rõ.
- Trong ứng dụng thực, Settings plugin có thể hỗ trợ plugin/repository policy, catalog, settings extensions và lifecycle callbacks; phải thiết kế tránh đọc/sửa Project model chéo không an toàn.

Nếu bạn đặt ID này vào `app/build.gradle` và yêu cầu apply như Project plugin, target không đúng. Plugin target type phải phù hợp **ngữ cảnh nơi được apply**.

### 5.8. File consumer/app/build.gradle

```groovy
plugins {
    id 'application'
    id 'com.example.trace'
}

application {
    mainClass = 'example.app.Main'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

`application` là Gradle core plugin, tạo JavaCompile và task `run`. `com.example.trace` được resolve từ included plugin build qua settings pluginManagement, rồi đăng ký `pluginStatus` vào chính app project. Không có `implementation project(':plugin-build')` hoặc copy JAR thủ công.

### 5.9. Java application: Main.java

**Path:** `consumer/app/src/main/java/example/app/Main.java`.

```java
package example.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String who = args.length == 0 ? "composite" : args[0];
        System.out.println("Hello, " + who + "!");
    }
}
```

Đây là Java 17+ source hoàn chỉnh, có main method hợp lệ và không phụ thuộc mã Gradle plugin.

### 5.10. Chạy từ thư mục consumer trên Linux/macOS

```bash
./gradlew --version
./gradlew :app:tasks --all --console=plain
./gradlew -q :app:pluginStatus
./gradlew -q :app:run
./gradlew -q :app:run --args="Team"
./gradlew :plugin-build:validatePlugins --console=plain
```

**Stdout từ task `pluginStatus` (một lệnh):**

```text
plugin-status=loaded
```

**Stdout Java từ `:app:run` không args (lệnh khác):**

```text
Hello, composite!
```

**Stdout Java từ `:app:run --args="Team"` (lệnh thứ ba):**

```text
Hello, Team!
```

Ba khối trên là kết quả của **ba lệnh độc lập**, không phải một lệnh in cả ba. Gradle có thể thêm messages khác về daemon, task outcomes, build cache và warnings. `-q` giảm Gradle logging nhưng không làm thay đổi chuỗi do task/app in.

Lệnh `:plugin-build:validatePlugins` gọi task trong **included build** bằng build-tree task path. Task validation thường không in marker Java application; đừng đoán stdout của nó thay cho exit code/build report.

### 5.11. Chạy Windows PowerShell

```powershell
.\gradlew.bat --version
.\gradlew.bat :app:tasks --all --console=plain
.\gradlew.bat -q :app:pluginStatus
.\gradlew.bat -q :app:run
.\gradlew.bat -q :app:run --args="Team"
.\gradlew.bat :plugin-build:validatePlugins --console=plain
```

Windows dùng `gradlew.bat`. Các Gradle project/task paths và plugin IDs vẫn dùng `:` hoặc dấu chấm như trên, **không** đổi thành path separator `\`.

### 5.12. Thử chỉnh plugin ngay tại source

Trong `TracePlugin.java`, đổi:

```java
System.out.println("plugin-status=loaded");
```

thành:

```java
System.out.println("plugin-status=updated");
```

Lưu source, chạy lại:

```bash
./gradlew -q :app:pluginStatus
```

Khi plugin build được rebuild/reused đúng, task in `plugin-status=updated`. Không cần tăng version trong `app/build.gradle` hoặc publish lên Maven, vì consumer đang dùng local included plugin provider.

**Lưu ý:** Gradle cache có thể dùng output cũ khi inputs không đổi; nếu bạn vừa sửa source, thông thường JavaCompile biết file đã đổi. Nếu thấy marker cũ, kiểm tra đúng checkout/file, task path, source code và build logs trước khi xóa toàn bộ caches.

## 6. Vòng đời của plugin resolution trong composite

```text
Consumer settings.gradle
    |
    v
pluginManagement.includeBuild('plugin-build')
    |
    +-- đăng ký included plugin provider
    +-- plugin-build compile/resolve khi cần
    |
    v
Consumer settings plugins {}
    |
    +-- com.example.settings-info
    +-- apply SettingsInfoPlugin to Settings
    +-- set pluginOrigin = included-build
    |
    v
rootProject.name = 'consumer'; include 'app'
    |
    v
Consumer app/build.gradle
    |
    +-- apply core plugin application
    +-- apply included plugin com.example.trace
    +-- TracePlugin.apply(Project :app)
    +-- register :app:pluginStatus
    |
    v
Task execution
    |
    +-- :app:pluginStatus
          |
          v
    plugin-status=loaded
```

Đây là sơ đồ **logic**, không phải transcript log byte-for-byte. Gradle có thể reuse outputs/plugin classes và configuration cache phù hợp; không build lại plugin-build khi không cần.

### 6.1. Plugin provider khác application dependency

Khi consumer viết:

```groovy
plugins {
    id 'com.example.trace'
}
```

Gradle resolve plugin implementation và áp dụng lên build model. Mã plugin **không** trở thành `implementation` library trên runtime classpath của Java app. Nếu application muốn gọi một shared Java API từ included library build, phải thiết kế **module dependency** riêng và dùng coordinates/substitution.

### 6.2. Project build files không tự thừa hưởng build-logic code

Một included build là Gradle build độc lập. Nó có thể được build/test một mình với `gradle -p plugin-build ...` hoặc Gradle Wrapper riêng nếu được cung cấp. Nhưng nó không tự nhận những `repositories`, `libs.versions.toml`, `group`, `gradle.properties` của consumer.

Ví dụ, consumer có `mavenCentral()` ở `app/build.gradle` không tự giúp plugin-build tải JUnit dependencies cho tests. Plugin-build phải khai báo repositories cho chính nó.

### 6.3. Task paths của included build

Từ consumer root, có thể gọi:

```bash
./gradlew :plugin-build:compileJava
./gradlew :plugin-build:pluginDescriptors
./gradlew :plugin-build:validatePlugins
```

Tên `plugin-build` trong task path là **included build identity**. Nó không cho phép bạn gọi `project(':plugin-build')` qua Project API.

Nếu muốn root consumer có một aggregate task:

```groovy
// consumer/build.gradle; phần bổ sung không cần cho lab cơ bản.
tasks.register('checkLocalPlugin') {
    dependsOn gradle.includedBuild('plugin-build')
            .task(':validatePlugins')
}
```

Đây là Gradle API chuyên cho **included build task reference**. Nó tạo một task dependency rõ ràng; **không** có nghĩa bạn phải tạo task này để `plugins { }` resolve được plugin local.

## 7. Precompiled convention plugin trong build-logic: phương án thay thế

Nếu mục tiêu là chuẩn hóa `java`, `test`, repositories hoặc Java release cho nhiều module, **precompiled script convention plugin** thường ít mã hơn binary Java plugin.

**Phương án sau thay thế lab `plugin-build`**, không dán các settings/scripts của hai lab chồng lên nhau.

### 7.1. Cấu trúc

```text
consumer/
├── settings.gradle
├── app/build.gradle
├── app/src/main/java/example/app/Main.java
└── build-logic/
    ├── settings.gradle
    ├── build.gradle
    └── src/main/groovy/
        └── java-conventions.gradle
```

### 7.2. settings.gradle của consumer trong phương án convention

```groovy
pluginManagement {
    includeBuild('build-logic')
}

rootProject.name = 'consumer'
include 'app'
```

Không còn `plugins { id 'com.example.settings-info' }` vì phương án này chỉ định nghĩa Project convention plugin.

### 7.3. build-logic/settings.gradle

```groovy
rootProject.name = 'build-logic'
```

### 7.4. build-logic/build.gradle

```groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
```

`groovy-gradle-plugin` hỗ trợ compile **precompiled Groovy script plugins**. Nếu convention chỉ áp các Gradle core plugins, chưa cần external dependency artifacts, nhưng repositories hữu ích khi bắt đầu dùng third-party plugins.

### 7.5. build-logic/src/main/groovy/java-conventions.gradle

```groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Từ tên file `java-conventions.gradle`, Gradle sinh plugin ID **`java-conventions`**. Đối với Groovy precompiled scripts, không đặt package declaration trong file để tạo ID như Java class. Một script `company-policy.settings.gradle` sẽ có **Settings plugin scope** theo suffix `.settings.gradle`; script `java-conventions.gradle` là **Project plugin**.

### 7.6. app/build.gradle với convention

```groovy
plugins {
    id 'application'
    id 'java-conventions'
}

application {
    mainClass = 'example.app.Main'
}
```

Giữ nguyên `Main.java` từ mục 5.9, `./gradlew -q :app:run` in `Hello, composite!`. Không cần self-authored Java `Plugin<Project>` để áp một vài Java conventions.

### 7.7. Vì sao Gradle khuyến nghị build-logic thay root injection?

Thay vì:

```groovy
// Anti-pattern trong root build.gradle khi dự án lớn.
subprojects {
    apply plugin: 'java'
    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }
}
```

Hãy để từng subproject chủ động request `java-conventions`. Các module Android/Docs/Platform không cần Java có thể không apply convention. Build logic có thể được compile/test riêng, dùng lại giữa builds, giảm coupling và giúp Isolated Projects dễ đáp ứng hơn.

### 7.8. Settings plugin trong precompiled script build

Khi cần Settings convention plugin, dùng file suffix `.settings.gradle` trong `src/main/groovy`, ví dụ `security-policy.settings.gradle`. Consumer phải đăng ký build logic ở **`pluginManagement.includeBuild`** rồi mới request `id 'security-policy'` trong settings `plugins { }`.

Gradle có cảnh báo thực tế: một included build logic lớn, nếu phải compile quá sớm để cung cấp Settings plugin, có thể ảnh hưởng build configuration/caching performance. Trong codebase lớn, hãy cân nhắc tách `settings-plugins` build nhỏ khỏi `build-logic` chứa hàng chục Project plugins.

## 8. Functional testing bằng Gradle TestKit

Thử plugin trong consumer thật giúp phát hiện vấn đề, nhưng một plugin nên có **functional tests** tự tạo build fixture. Gradle **TestKit** cung cấp `GradleRunner` để chạy một build Gradle ở thư mục tạm, áp dụng plugin bằng `plugins { }` và kiểm tra output.

Phần này **bổ sung vào plugin-build Java lab của mục 5**, không áp vào convention alternative ở mục 7.

### 8.1. Thêm JUnit dependencies vào plugin-build/build.gradle

Bổ sung ở cuối file:

```groovy
repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Lý do:**

- `java-gradle-plugin` tự tích hợp Gradle TestKit vào test configuration theo convention. Thông thường **không cần** khai báo thêm `testImplementation gradleTestKit()`; khi dùng build custom hãy kiểm tra test classpath.
- JUnit Jupiter `5.11.4` cung cấp annotation `@Test` và engine; BOM đồng bộ các JUnit module versions.
- `junit-platform-launcher` có mặt ở test runtime, phù hợp với Gradle/JUnit Platform hiện đại.
- `useJUnitPlatform()` bật framework runner cho Gradle Test task.
- `mavenCentral()` là repository của **plugin-build**, không phải repository trong consumer.

### 8.2. Java functional test có thể chạy

Tạo file `plugin-build/src/test/java/example/buildlogic/TracePluginFunctionalTest.java`:

```java
package example.buildlogic;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertTrue;

class TracePluginFunctionalTest {

    @TempDir
    Path testProjectDir;

    @Test
    void pluginRegistersExpectedTask() throws IOException {
        Files.writeString(
                testProjectDir.resolve("settings.gradle"),
                "rootProject.name = 'test-fixture'\n");

        Files.writeString(
                testProjectDir.resolve("build.gradle"),
                "plugins { id 'com.example.trace' }\n");

        BuildResult result = GradleRunner.create()
                .withProjectDir(testProjectDir.toFile())
                .withArguments("pluginStatus", "--stacktrace")
                .withPluginClasspath()
                .build();

        assertTrue(result.getOutput()
                .contains("plugin-status=loaded"));
    }
}
```

**Kiểm tra kỹ:**

1. `@TempDir` tạo một temporary directory cho fixture, không sửa project consumer thật.
2. `Files.writeString` là API Java 11+, chạy được với Java 17.
3. Hai strings tạo file `settings.gradle` và `build.gradle` cho build fixture; `\n` trong Java string là ký tự xuống dòng thực.
4. Fixture request chính xác plugin ID `com.example.trace` trong `plugins { }`.
5. `GradleRunner.withPluginClasspath()` nạp classpath của plugin đang test. `java-gradle-plugin` cung cấp metadata này, do đó không cần publish plugin hoặc tự `includeBuild('plugin-build')` bên trong fixture.
6. `BuildResult.getOutput()` chứa log build fixture; assertion kiểm tra marker task.
7. Đây là **functional test cho Project plugin**. Muốn test Settings plugin, fixture phải request nó trong settings plugins block và cung cấp plugin resolution/classpath phù hợp; không lấy việc test Project plugin làm chứng cứ Settings plugin cũng đã được test.

### 8.3. Chạy test/validation từ consumer

```bash
./gradlew :plugin-build:test --console=plain
./gradlew :plugin-build:validatePlugins --console=plain
```

Windows:

```powershell
.\gradlew.bat :plugin-build:test --console=plain
.\gradlew.bat :plugin-build:validatePlugins --console=plain
```

Với môi trường/plugin metadata/JUnit đầy đủ, **một TestKit functional test được chạy và pass**. Không suy đoán số dòng stdout Gradle test task; trong test, assertion yêu cầu output fixture **chứa** `plugin-status=loaded`.

`validatePlugins` kiểm tra các public task properties/annotations, transform contracts và những quy tắc plugin metadata có liên quan; nó **không** test logic ứng dụng end-to-end. Một pipeline plugin tốt nên chạy cả TestKit tests và validation.

### 8.4. TestKit Gradle version khác nhau

`GradleRunner` hỗ trợ `withGradleVersion`. Ví dụ một **fragment** khi biến `testProjectDir` đã được tạo và fixture đã viết:

```java
GradleRunner.create()
        .withProjectDir(testProjectDir.toFile())
        .withGradleVersion("9.0")
        .withArguments("pluginStatus")
        .withPluginClasspath()
        .build();
```

Đây không phải Java class độc lập, chỉ minh họa API. Đừng đưa version string `9.x` không tồn tại vào code, mà phải dùng phiên bản Gradle thực được tổ chức hỗ trợ. TestKit có thể tải Gradle distribution nếu cache chưa có. Java runtime của test runner phải tương thích version Gradle và plugin bytecode được kiểm thử.

## 9. Included plugin build, plugin markers và publish sau này

### 9.1. Vì sao lab không cần version ở consumer plugins block?

```groovy
plugins {
    id 'com.example.trace'
}
```

Trong lab, plugin ID đã được đăng ký trong included build qua `gradlePlugin.plugins`, và plugin provider local được đăng ký qua `pluginManagement.includeBuild`. Consumer không cần publish một version lên Plugin Portal rồi mới request.

Khi plugin được publish, Gradle Plugin DSL thường dùng ID/version:

```groovy
// MINH HỌA workflow plugin đã publish, không phải lab local.
plugins {
    id 'com.example.trace' version '1.0.0'
}
```

Để plugin published thực sự resolve được, bạn phải publish implementation artifact **và plugin marker metadata** theo plugin publishing/Maven rules, cấu hình repository và credentials phù hợp. Đừng mặc định `./gradlew :plugin-build:jar` có nghĩa plugin đã được publish.

### 9.2. Plugin marker vs implementation JAR

Khi resolve một plugin published từ plugin repository, Gradle có thể tìm marker artifact theo mẫu:

```text
com.example.trace:com.example.trace.gradle.plugin:<version>
```

Marker ánh xạ ID/version tới implementation JAR. Nhưng khi sử dụng local included plugin build, Gradle có thể lấy plugin provider trực tiếp từ plugin-build descriptors/metadata mà không cần external published marker.

Đừng nhầm marker artifact với `gradlePlugin.plugins.tracePlugin` declaration name: consumer chỉ quan tâm plugin ID `com.example.trace`.

### 9.3. Khi nào nên publish thay cho include local build?

Nên cân nhắc publish khi:

- Nhiều repositories/teams cần một release plugin ổn định.
- Consumer CI không muốn checkout/compile plugin source.
- Tổ chức yêu cầu signed/approved binaries, provenance, dependency locking và release history.
- Muốn version plugin độc lập với version application.
- Có plugin consumers ở ngoài cùng workspace hoặc ngoài tổ chức.

**Hai workflow khác nhau:** local development ưu tiên includeBuild; release consumption ưu tiên published plugin version được kiểm soát. Tránh mơ hồ “có local source nhưng build vẫn đang dùng published release” bằng cách kiểm tra settings plugin provider và plugin IDs thực.

## 10. includeBuild của library vs plugin provider

Một included build có thể cung cấp **library module** qua dependency substitution:

```groovy
rootProject.name = 'consumer'
include 'app'
includeBuild('../shared-library')
```

Nếu included library build khai báo `group='org.example'` và `name='shared-library'`, consumer project có thể yêu cầu dependency:

```groovy
// app/build.gradle fragment; cần Java plugin.
dependencies {
    implementation 'org.example:shared-library:1.0.0'
}
```

Gradle có thể thay external dependency bằng output của project tương ứng trong included build khi module coordinates khớp. Đây là **library dependency substitution** dựa trên module coordinates, không phải cách `plugins { id 'com.example.trace' }` tự đọc class plugin.

| Đặc điểm | Included library build | Included plugin build |
| --- | --- | --- |
| Consumer request | `implementation 'group:name:version'` | `plugins { id 'some.id' }` |
| Identifier chính | Module coordinates, variants. | Plugin ID và plugin implementation metadata. |
| Include hợp lý | Top-level `includeBuild`. | `pluginManagement { includeBuild(...) }`. |
| Mục tiêu | Dùng library source local thay binary dependency. | Load plugin source local thay published plugin. |
| Settings plugin | Không phải mục tiêu mặc định. | Có thể cung cấp khi include rất sớm trong pluginManagement. |

**Tinh tế:** Gradle cũng cho phép top-level `includeBuild` góp Project plugins trong nhiều trường hợp; không nên nói nó “không bao giờ” dùng được cho plugins. Tuy nhiên với Settings plugin, cách **đúng và ổn định** là `pluginManagement.includeBuild` để được đăng ký trước settings `plugins { }`.

## 11. Các giới hạn thực tế của composite plugin builds

### 11.1. Tách biệt configuration giữa các builds

Một included build không tự chia sẻ repositories, plugin management hay version catalogs với consumer. Nó có file `settings.gradle` và `gradle.properties` riêng. Project-defined properties từ consumer root gradle.properties không tự có ở included build, trong khi CLI `-P` và `-D` có những quy tắc riêng theo Gradle invocation.

Vì vậy nếu consumer có:

```groovy
repositories {
    mavenCentral()
}
```

plugin-build vẫn có thể fail khi resolve JUnit nếu chưa tự khai báo repositories. Cần sửa **plugin-build/build.gradle**, không thêm bừa project repository ở app.

### 11.2. Build tree identity và namespace conflict

Composite cần unique build paths. Nếu consumer có `:plugin-build` subproject và đồng thời included build tên `plugin-build`, có thể trùng namespace. Hãy dùng tên build rõ ràng như `build-logic` hoặc `settings-plugins`, hoặc điều chỉnh tên included build bằng supported API khi cần.

### 11.3. Đừng cấu hình chéo projects của included build

`project(':plugin-build')` **không** tìm được included build từ consumer. Muốn liên kết task, dùng:

```groovy
// Root consumer build.gradle, fragment bổ sung.
tasks.register('checkPlugin') {
    dependsOn gradle.includedBuild('plugin-build')
            .task(':validatePlugins')
}
```

`gradle.includedBuild('plugin-build').task(':validatePlugins')` tạo task reference được hỗ trợ, không phải Project object. Fragment này **không** cần thiết chỉ để plugin resolution hoạt động: khi consumer cần plugin code, Gradle tự xây artifacts plugin cần thiết.

### 11.4. Java/JVM của Gradle và Java target application

Một plugin binary chạy **bên trong Gradle**. Nếu plugin compile ở Java 21 bytecode và Gradle Daemon JVM là Java 17, plugin load có thể báo `UnsupportedClassVersionError` ngay khi settings hoặc project plugins được apply. Đây là lỗi **build logic runtime**, không phải `Main.java`.

Lab đặt `options.release=17` cả plugin-build và app, dùng JDK compiler hỗ trợ `--release 17`. Nhưng chỉ đặt Java release không bảo đảm JDK đã tồn tại; nếu muốn toolchain major cụ thể cần cấu hình Java toolchain và resolver phù hợp.

### 11.5. Không tự tin rằng offline sẽ luôn hoạt động

Dù plugin source local, plugin-build vẫn có thể cần tải JUnit, Groovy/Kotlin toolchain hoặc external library dependencies. Wrapper có thể cần tải Gradle distribution lần đầu. `--offline` không giúp những artifacts chưa có trong caches tự xuất hiện. Phân biệt lỗi plugin source resolution với lỗi download một third-party dependency.

### 11.6. Cần kiểm soát concurrent CI builds

Plugin-build được orchestrate chung trong composite invocation nhưng vẫn có output directories/caches riêng. Nhiều Gradle invocations đồng thời trên **cùng một checkout/plugin-build directory** có thể chạm vào cùng outputs, và composite build docs có các giới hạn về concurrent shared builds. Dùng workspace cách ly cho từng CI job hoặc cache policy đúng.

### 11.7. Settings plugin chạy sớm và có quyền lớn

Plugin source được include là **code có thể thực thi** khi Gradle khởi tạo/configure, đôi khi trước khi build Java application. Không include plugin code không đáng tin vào runner có signing key/publishing tokens; kiểm tra nguồn Git commit, plugin dependencies, HTTPS repositories, credentials và audit quyền truy cập.

Một Settings plugin lỗi có thể làm **cả Gradle invocation fail trước khi mọi application task bắt đầu**. Nếu lỗi xuất hiện ở settings, đừng sửa Application plugin hoặc source Java trước khi kiểm tra plugin build.

### 11.8. buildSrc, build-logic và settings plugin build

`buildSrc` được Gradle xử lý tự động, phù hợp khởi đầu nhanh. Explicit `build-logic` included build có boundary rõ hơn, có thể test/version/publish độc lập và thường phù hợp multi-project lớn. Tuy nhiên việc cần một Settings plugin sớm trong pluginManagement có thể yêu cầu build-logic được compile ngay từ initialization; với dự án lớn, tách một **minimal settings plugin build** để giảm chi phí.

## 12. Hướng dẫn chẩn đoán theo lỗi

| Thông báo/triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Plugin [id: 'com.example.trace'] was not found` | Sai plugin ID, included plugin build chưa đăng ký hoặc plugin descriptors lỗi. | Kiểm tra `pluginManagement.includeBuild`, `gradlePlugin.plugins.id`, implementationClass. |
| Settings plugin không resolve | Plugin build chỉ include top-level sau settings `plugins { }`. | Chuyển include vào `pluginManagement` ở đầu settings. |
| `ClassNotFoundException` / implementation class missing | Sai Java package, filename, class name hoặc compiler fail. | So sánh `implementationClass` với `package`/class thực, kiểm tra descriptors. |
| `UnsupportedClassVersionError` | Plugin bytecode target mới hơn JVM Gradle Daemon. | Xem `./gradlew --version`, compiler, release/toolchain plugin-build. |
| Không thấy `:app:pluginStatus` | App chưa apply `com.example.trace` hoặc task bị đổi tên. | Xem `app/build.gradle`, chạy `:app:tasks --all`. |
| Settings assert về `pluginOrigin` fail | Settings plugin chưa được apply/logic sai. | Kiểm tra `SettingsInfoPlugin` và settings `plugins { }`. |
| `project(':plugin-build')` fail | Included build không phải subproject. | Dùng plugin ID hoặc `gradle.includedBuild('plugin-build').task(...)`. |
| Có plugin ID nhưng target sai | Apply `Plugin<Settings>` từ app hoặc Project plugin từ settings. | Sửa scope hoặc vị trí request plugin. |
| `No such property 'implementation'` | App/module chưa apply Java plugin để tạo dependency bucket. | Apply đúng plugin, không dùng plugin-build như module dependency. |
| TestKit không tìm thấy plugin | Fixture không dùng `plugins { }`, thiếu `withPluginClasspath()`, classpath metadata sai. | Xem fixture, java-gradle-plugin và TestKit setup. |
| TestKit không tải được dependencies | Plugin-build không có Maven Central hoặc mạng bị chặn. | Thêm `repositories { mavenCentral() }` trong plugin-build. |
| `validatePlugins` PASS nhưng task chạy sai | Validation không phải test logic đầy đủ. | Viết thêm TestKit functional tests với assertions. |
| `java-conventions` not found | Build-logic chưa include; sai filename/source root hoặc chưa apply `groovy-gradle-plugin`. | Kiểm tra `src/main/groovy/java-conventions.gradle`, includeBuild settings. |
| Build-logic không nhận `libs` catalog | Included build có settings riêng. | Import catalog có chủ đích trong included build settings. |
| Consumer resolve plugin ở Portal thay vì local | ID/provider hoặc settings include không đúng; có published plugin cùng ID. | Kiểm tra plugin request, pluginManagement và build logs, không đoán từ version. |
| Plugin compile được local nhưng fail trên CI | Gradle/JDK version khác, code checkout thiếu, network/caches khác. | Dùng Wrapper, verify checkout plugin-build, pin toolchain và repos. |
| `--offline` fail dù plugin source có sẵn | Wrapper/JUnit/third-party deps chưa cache. | Preseed/cố định dependencies hoặc dùng online build có kiểm soát. |
| Included build name conflict | Build path trùng project path hoặc included build khác. | Đổi namespace/directory hoặc cấu hình build identity. |
| Hai CI jobs dùng chung checkout và làm hỏng outputs | Concurrency trên shared build directory. | Dùng workspaces cách ly. |

### 12.1. Quy trình debug thực tế

1. Chạy `./gradlew --version` để xác định Gradle JVM có thể khởi động.
2. Xem `consumer/settings.gradle`: `pluginManagement.includeBuild` ở đầu và đúng relative directory chưa?
3. Kiểm tra `plugin-build/settings.gradle`/`build.gradle`, plugin ID, `implementationClass`, Gradle core `java-gradle-plugin`.
4. Chạy `./gradlew :plugin-build:classes` và `:plugin-build:pluginDescriptors` để xác minh plugin build compile.
5. Chạy `:plugin-build:validatePlugins` kiểm tra metadata/Gradle task property rules.
6. Xem `app/build.gradle` có request đúng `com.example.trace`, sau đó `:app:tasks --all`.
7. Chạy `:app:pluginStatus --info --stacktrace` khi cần tìm exception ở execution.
8. Chạy `:plugin-build:test` để xác minh plugin behavior bằng TestKit và xem report.
9. So sánh local vs CI: Wrapper, JDK, Git checkout của included build, network/repositories, caches, permissions.
10. Sửa đúng pha: Settings plugin resolution khác Project plugin configuration khác task execution; không dùng việc xóa toàn bộ Gradle User Home làm cách sửa mặc định.

## 13. Ví dụ các quyết định thiết kế phù hợp doanh nghiệp

### 13.1. Nhóm nhỏ, plugin chỉ có vài convention

Dùng `build-logic` với precompiled script plugin `java-conventions.gradle`, mỗi module tự apply. Đừng tạo một Java binary plugin phức tạp chỉ để đặt `options.release = 17` hoặc `testLogging`.

### 13.2. Plugin cần custom task types, extensions, API public

Dùng `java-gradle-plugin` (Java/Groovy/Kotlin), thiết kế typed tasks với `@Input`/`@Output` annotations, Gradle Providers và lazy task registration. Viết TestKit functional tests, chạy `validatePlugins`.

### 13.3. Tổ chức có nhiều Settings plugins

Nếu một Settings plugin được dùng ngay khi settings script đánh giá, đưa plugin build vào `pluginManagement.includeBuild`. Nếu build logic lớn, cân nhắc tách `settings-plugins` build nhỏ để không compile quá nhiều plugins khi chỉ cần policies ban đầu.

### 13.4. Plugin chia sẻ giữa nhiều repositories độc lập

Trong giai đoạn phát triển plugin, consumer dùng local included build. Khi phát hành, publish plugin binaries/markers đã kiểm chứng, pin versions cho consumers và loại bỏ local override không còn cần; dùng release promotion/trust policy.

### 13.5. CI yêu cầu provenance rõ ràng

Build được dùng để phát hành nên ghi Git commit của plugin-build, Gradle Wrapper version, JDK version, plugin IDs, source/build artifact hashes và TestKit/validatePlugins results. Không suy luận rằng plugin source local luôn đáng tin chỉ vì không đi qua Portal.

## 14. Bài tập tự luyện

**Bài 1 — Phân biệt build:** Vì sao `plugin-build` không phải `:plugin-build`? Bởi vì `includeBuild` ghép một build riêng, không tạo consumer subproject.

**Bài 2 — Settings plugin timing:** Nếu bỏ `pluginManagement.includeBuild` và đặt `includeBuild` sau settings `plugins { }`, vì sao plugin `com.example.settings-info` có thể không resolve? Vì provider không được đăng ký trước plugin request.

**Bài 3 — Plugin ID:** Trong `gradlePlugin.plugins.tracePlugin`, đâu là plugin ID? `com.example.trace`, không phải `tracePlugin` hay `TracePlugin.java`.

**Bài 4 — Hai scopes:** Tại sao `SettingsInfoPlugin` không tạo `:app:pluginStatus`? Nó là `Plugin<Settings>`, còn task được tạo bởi `Plugin<Project>`.

**Bài 5 — CLI:** Chạy `./gradlew -q :app:pluginStatus`. Kỳ vọng `plugin-status=loaded`. Sửa source plugin marker thành `updated`, chạy lại và giải thích local provider rebuild.

**Bài 6 — Java app:** Chạy `./gradlew -q :app:run --args="Team"`. Java app in `Hello, Team!`; plugin project không phải ứng dụng chính.

**Bài 7 — TestKit:** Vì sao `withPluginClasspath()` giúp fixture request plugin local mà không cần publish? Vì `java-gradle-plugin` cung cấp plugin-under-test classpath cho runner.

**Bài 8 — validatePlugins:** `validatePlugins` có kiểm tra đầy đủ output mọi plugin task không? Không; nó kiểm tra plugin/task API properties và các quy tắc validation, cần thêm functional tests.

**Bài 9 — Precompiled scripts:** Plugin ID `java-conventions` lấy từ đâu? Từ file `java-conventions.gradle` trong đúng source root và `groovy-gradle-plugin`.

**Bài 10 — Settings suffix:** Precompiled Settings plugin dùng hậu tố nào? `.settings.gradle` ở Groovy DSL, không phải một `.gradle` Project plugin thông thường.

**Bài 11 — Repositories:** Consumer đã khai báo plugin portal và Maven Central, sao plugin-build không resolve JUnit? Vì included build có repositories riêng.

**Bài 12 — Library substitution:** `implementation 'org.example:shared-library:1.0.0'` với top-level includeBuild thư viện có phải plugin request không? Không; đó là external dependency substitution.

**Bài 13 — Build tree task:** Viết task consumer phụ thuộc `:plugin-build:validatePlugins` qua Gradle API. Gợi ý `gradle.includedBuild('plugin-build').task(':validatePlugins')`.

**Bài 14 — Gradle JVM:** App source target Java 17 nhưng plugin compiled Java 21; Gradle Daemon chỉ chạy Java 17. Lỗi nào có thể xuất hiện khi load plugin? `UnsupportedClassVersionError`, trước lúc app compile.

**Bài 15 — CI:** Thiết kế pipeline checkout plugin-build, pin Wrapper/JDK, chạy `:plugin-build:validatePlugins`, `:plugin-build:test`, `:app:pluginStatus`, `:app:run` và lưu test reports/source revisions.

### Câu hỏi nhanh

1. **Có cần publish plugin trước khi dùng included plugin build?** Không.
2. **`includeBuild` có tự tạo child project?** Không.
3. **Settings plugin nên include build ở đâu?** Trong `pluginManagement`.
4. **Một plugin build có thể cung cấp nhiều IDs?** Có.
5. **Project plugin implement interface nào?** `Plugin<Project>`.
6. **Settings plugin implement interface nào?** `Plugin<Settings>`.
7. **`java-gradle-plugin` có tạo plugin descriptors không?** Có.
8. **Gradle TestKit dùng class nào để chạy fixture?** `GradleRunner`.
9. **`--include-build` CLI nên thay settings pluginManagement không?** Không nên với unpublished plugin DSL.
10. **`pluginManagement.repositories` có phải app dependency repositories?** Không.
11. **Included build có tự kế thừa root `libs` catalog không?** Không.
12. **BuildSrc có tự được Gradle nhận biết không?** Có.
13. **Precompiled Groovy script plugin dùng core plugin nào?** `groovy-gradle-plugin`.
14. **Project convention plugin phải apply ở đâu?** Ở project muốn nhận quy ước.
15. **`validatePlugins` có thể thay TestKit không?** Không.
16. **Included plugin build có thể có Settings plugin không?** Có, được include đủ sớm.
17. **Plugin implementation class có được tự thêm vào app runtime classpath?** Không.
18. **Plugin build có cần JDK tương thích JVM chạy Gradle không?** Có.
19. **Plugin build có cần source checkout trong local workflow không?** Có.
20. **Có nên include plugin code không được review trong CI có secrets?** Không.

## 15. Nguồn chính thức

- **Gradle — Composite Builds (Included Builds):** plugin builds trong `pluginManagement`, Settings/Project plugin handling, build boundaries, task references, library substitutions và hạn chế: https://docs.gradle.org/current/userguide/composite_builds.html
- **Gradle — Plugin Management:** plugin requests và plugin repositories: https://docs.gradle.org/current/userguide/plugins_intermediate.html
- **Gradle — Plugins:** `java-gradle-plugin`, `gradlePlugin`, scopes: https://docs.gradle.org/current/userguide/plugins.html
- **Gradle — Gradle Plugin Development Plugin:** pluginDescriptors, pluginUnderTestMetadata, validatePlugins: https://docs.gradle.org/current/userguide/java_gradle_plugin.html
- **Gradle — Testing Build Logic with TestKit:** `GradleRunner`, `withPluginClasspath`, functional testing: https://docs.gradle.org/current/userguide/test_kit.html
- **Gradle — Testing Plugins:** manual testing qua included plugin build: https://docs.gradle.org/current/userguide/testing_gradle_plugins.html
- **Gradle — Precompiled Script Plugins:** `groovy-gradle-plugin`, plugin ID, Settings plugin filename suffix: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html
- **Gradle — Convention Plugins:** shared build logic với convention plugins thay root injection: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html
- **Gradle — Best Practices for Structuring Builds:** included `build-logic` và tối ưu Settings plugins: https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html
- **Gradle — Build Lifecycle:** initialization, settings pluginManagement, Settings plugin requests và project configuration: https://docs.gradle.org/current/userguide/build_lifecycle.html
- **Gradle API — PluginManagementSpec.includeBuild:** chính thức hỗ trợ included builds cung cấp Settings/Project plugins: https://docs.gradle.org/current/javadoc/org/gradle/plugin/management/PluginManagementSpec.html

**Kết luận:** **Plugin development build** là một Gradle build độc lập chứa plugin code và descriptors, không phải subproject của consumer. Khai báo **`pluginManagement { includeBuild('plugin-build') }`** giúp Gradle resolve plugin ID từ local source **trước khi xử lý Settings plugins**, đồng thời cung cấp Project plugins trong `build.gradle` mà không publish artifact. Chọn `java-gradle-plugin` khi viết binary plugins và TestKit khi kiểm thử; chọn `groovy-gradle-plugin` với precompiled convention scripts khi chỉ chia sẻ các quy tắc build. Đừng trộn plugin ID với module coordinates, target scope với classpath hay included build với subproject.