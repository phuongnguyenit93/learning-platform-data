# Phân biệt dependency của ứng dụng, plugin và build script trong Gradle

## 1. Ba nghĩa khác nhau của “dependency”

Trong Gradle, một dependency có thể phục vụ **mã sản phẩm**, **plugin mở rộng hệ thống build** hoặc **chính mã build script**. Cả ba đều có thể tải JAR từ một Maven repository, nhưng chúng **không nằm mặc định trên cùng một classpath** và không được khai báo qua cùng một API.

- **Application/project dependency**: thư viện để Java/Kotlin source code biên dịch, test hoặc chạy. Khai báo thường ở `dependencies { implementation ... }`, `api`, `runtimeOnly`, `testImplementation`.
- **Plugin dependency**: mã áp dụng vào Gradle để tạo task, extension, dependency configurations, quy tắc đóng gói/publishing… Khai báo hiện đại ở `plugins { id '...' version '...' }`, resolve qua plugin management.
- **Build script dependency**: thư viện mà Groovy/Kotlin build script dùng khi Gradle **cấu hình build**. Với cách legacy, khai báo ở `buildscript { dependencies { classpath '...' } }`.

Hãy xem ba khai báo:

~~~groovy
// Thư viện cho mã ứng dụng, khi đặt trong dependencies {} của project:
implementation 'org.apache.commons:commons-lang3:3.17.0'

// Plugin để Gradle biết cách đóng gói/chạy app, khi đặt trong plugins {}:
id 'application'

// Helper library cho build script, khi đặt trong buildscript.dependencies {}:
classpath 'org.yaml:snakeyaml:2.7'
~~~

Đây là **ba trích đoạn riêng về vị trí khai báo**, không phải một script có thể dán nguyên cả ba dòng vào cùng một block. Vấn đề cốt lõi: `implementation` không làm Gradle tự áp dụng plugin; `plugins { }` không tự đưa JAR plugin vào runtime của app; `buildscript.classpath` không làm Java source code import được thư viện.

Bài học thuộc nhóm **Mô hình dependency** trong Build Tool Gradle. Mọi ví dụ là **Groovy DSL** (`build.gradle`, `settings.gradle`), với Java 17 cho ví dụ application. Khi dùng project thực tế, cần kiểm tra phiên bản Gradle Wrapper, JDK, plugin và Maven artifact tương thích.

## 2. Bảng phân biệt nhanh

| Tiêu chí | Ứng dụng | Plugin | Build script |
| --- | --- | --- | --- |
| Ai dùng? | Source code, test, chương trình chạy | Gradle và plugin code | Build script/build logic |
| Cách khai báo | `dependencies { implementation 'g:a:v' }` | `plugins { id 'plugin.id' version 'v' }` | `buildscript { dependencies { classpath 'g:a:v' } }` |
| Tên định danh | Maven coordinates, project dependency, file | **Plugin ID** và version, marker/implementation | Maven coordinates hoặc file trên script classpath |
| Repository | `repositories` hoặc `dependencyResolutionManagement.repositories` | `pluginManagement.repositories` (Plugin Portal mặc định) | `buildscript.repositories` |
| Lifecycle | Compile/test/run/đóng gói theo task | Resolve và apply khi cấu hình build | Tải class để biên dịch/đánh giá script |
| Kết quả | `compileClasspath`, `runtimeClasspath`, test classpath, variants | Task, extension, configuration, build behavior | Class có thể import/dùng trong `build.gradle` |
| Có tự trở thành runtime lib của app? | Tùy configuration | Không, trừ khi plugin chủ động thêm project dependency | Không |
| Có tự áp dụng Gradle plugin? | Không | Có khi được apply | Không; chỉ có class trên classpath chưa bằng apply |

Sơ đồ khái niệm:

~~~text
                   Gradle build process
                          |
            +-------------+------------------+
            |                                |
       Plugin resolution                Build script classpath
       id + version                      buildscript.classpath
            |                                |
       plugin JARs                        helper/library JARs
            |                                |
      apply vào Project                chạy logic build.gradle
            |
            +--> thêm task/extension/configuration
                         |
                         v
                Project dependency graph
                     implementation
                     api / runtimeOnly
                     testImplementation
                         |
             +-----------+-------------+
             |                         |
        compileClasspath         runtimeClasspath
             |                         |
           javac                  app/test process
~~~

Sơ đồ không tuyên bố ba JVM được tạo riêng biệt. Gradle có cơ chế classloader và cache phức tạp; điều cần bảo đảm là **đúng nguồn dependency và đúng scope**. Không nên dựa vào việc một class “tình cờ nhìn thấy” từ classloader khác làm thiết kế build.

## 3. Application dependency: điều gì đi vào mã nguồn?

Ví dụ một Java application:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

application {
    mainClass = 'demo.App'
}
~~~

Phần `plugins` áp dụng Application plugin, mang theo hỗ trợ Java và task `run`. Phần `dependencies` khai báo Commons Lang3 để Java source như `App.java` có thể dùng `org.apache.commons.lang3.StringUtils`. `repositories` cho Gradle biết nơi tìm **project libraries**, không phải mọi plugin.

Plugin tạo ra các **dependency configurations**. `implementation` không phải cú pháp được Groovy hỗ trợ độc lập: một plugin như `java`, `java-library`, `application` phải tạo configuration liên quan. Nếu quên plugin, build có thể báo `Could not find method implementation()`.

### 3.1. Chọn scope theo compile, runtime, test và API

| Configuration | Tình huống | Lưu ý |
| --- | --- | --- |
| `implementation` | Mã chính cần thư viện lúc compile và runtime | Không công bố thư viện như một API dependency của Java library |
| `api` | Public API của Java library để lộ kiểu từ dependency | Do `java-library` cung cấp; consumer có thể cần khi compile |
| `compileOnly` | API chỉ cần để compile, runtime được nơi khác cung cấp | Không tự đưa JAR vào runtime app |
| `runtimeOnly` | Driver/implementation chỉ cần khi chạy | Không tự có trên main compile classpath |
| `testImplementation` | Dependencies của code test | Không có nghĩa ship cùng artifact ứng dụng |
| `testRuntimeOnly` | Test engine hoặc runtime-only test helper | Chỉ trong test runtime phù hợp |
| `annotationProcessor` | Annotation processor cho Java compiler | Processor path riêng; không phải runtime app |

Đừng đoán scope từ việc “JAR là dependency”. Nếu một Java library công khai phương thức có tham số/return type từ thư viện khác, `api` thường có ý nghĩa hơn `implementation`; nếu là chi tiết triển khai, `implementation` thường đủ.

### 3.2. Bucket khai báo khác configuration được resolve

`implementation` là nơi **khai báo**, còn `compileClasspath` và `runtimeClasspath` là các configuration được Gradle **resolve** để thực thi tác vụ.

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.16'
}
~~~

Trong Gradle Java ecosystem, Commons Lang có thể đi vào compile/runtime classpath của source chính; SLF4J Simple từ `runtimeOnly` được dùng lúc chạy, không giúp Java source import một class chỉ có trong SLF4J Simple khi compile. Chi tiết variants và transitive graph phụ thuộc metadata của artifact và plugin.

### 3.3. Application dependency có thể là module khác

Với `settings.gradle`:

~~~groovy
rootProject.name = 'store'
include 'app', 'library'
~~~

`app/build.gradle`:

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':library')
}
~~~

Đây là quan hệ dependency **giữa hai module sản phẩm**. Nó không có nghĩa Gradle tải `library/build.gradle` làm plugin cho `app` hoặc tự áp dụng cùng một plugin vào hai module.

Nếu thư viện `:library` được phát hành và có public API cần một dependency khác, plugin `java-library` giúp mô hình hóa `api`/`implementation` để consumers nhìn thấy đúng compile/runtime variants.

### 3.4. Transitive dependencies và version conflict

Một library có thể phụ thuộc những library khác. Gradle giải quyết **transitive dependencies**, metadata/variants, version constraints và conflicts **trong đúng configuration**. Có JAR trên disk cache không có nghĩa JAR đó thuộc `runtimeClasspath`.

Kiểm tra:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

Đây là các lệnh đọc graph của **project** đang chọn. Trong multi-project build cần thêm project path, ví dụ `:app:dependencies` và `:app:dependencyInsight`. Không dùng report này để khẳng định plugin implementation classpath gồm những JAR gì.

## 4. Plugin dependency: “Gradle cần khả năng build nào?”

Plugin có thể bổ sung:

- Task như `compileJava`, `test`, `run`, `jar`, `shadowJar`.
- Extension cấu hình DSL, ví dụ `application { }` hoặc `java { }`.
- Dependency configurations, task types, artifact transforms, publishing và packaging behavior.
- Logic thêm **project dependencies** nếu plugin chủ động làm vậy.

### 4.1. Core plugin

~~~groovy
plugins {
    id 'java'
    id 'application'
}
~~~

`java` và `application` là **core plugins** theo Gradle distribution. Chúng không yêu cầu version riêng: bản Gradle Wrapper quyết định implementation. Không viết `implementation 'gradle:java:...'` để thay plugin.

### 4.2. External plugin

Ví dụ một GradleUp Shadow plugin, dùng để tạo fat JAR:

~~~groovy
plugins {
    id 'com.gradleup.shadow' version '9.6.1'
}
~~~

Đây là cú pháp plugin DSL với **plugin ID + plugin version**; `9.6.1` là một bản đã công bố trên Plugin Portal, không phải version mặc định đúng cho mọi Wrapper. Kiểm tra tương thích với Gradle/JDK trước khi dùng trên project thật.

Plugin DSL không yêu cầu bạn tự viết Maven coordinates của implementation JAR. Với plugin xuất bản theo cơ chế chuẩn, Gradle dùng **plugin marker artifact** hoặc resolution rule/included build để tìm implementation tương ứng. Do đó, **Plugin ID không nhất thiết trùng Maven group hay artifact name** của JAR chứa code plugin.

### 4.3. `pluginManagement.repositories`

Một `settings.gradle` có thể khai báo:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = 'plugin-demo'
~~~

`pluginManagement` nằm đầu settings script và là nơi cấu hình repository cho plugin DSL, phiên bản và resolution strategy khi cần. Plugin Portal thường là repository mặc định cho plugin resolution, nhưng plugin nội bộ có thể yêu cầu Maven repository riêng và credentials phù hợp.

Đoạn sau trong `build.gradle` **không thay thế pluginManagement**:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Nó phục vụ project dependencies, không tự làm Gradle tìm thấy plugin marker trong mọi repository.

### 4.4. Dùng cùng plugin trên nhiều module với `apply false`

Root `build.gradle`:

~~~groovy
plugins {
    id 'com.gradleup.shadow' version '9.6.1' apply false
}
~~~

`app/build.gradle`:

~~~groovy
plugins {
    id 'application'
    id 'com.gradleup.shadow'
}
~~~

`apply false` nói rằng plugin **không áp dụng vào project root**, nhưng có thể được resolve và sử dụng ở module cần nó. Đây là cách tổ chức cho multi-project build; không có nghĩa plugin trở thành runtime library của app.

Không nên ép mọi plugin lên `allprojects`/`subprojects` chỉ vì muốn chia sẻ version. Đối với tập module lớn, convention plugin thường rõ trách nhiệm hơn.

### 4.5. Plugin implementation dependency không phải app dependency

Một plugin có thể cần các JAR riêng để thực hiện chức năng. Những JAR đó thuộc phía **Gradle/plugin classpath**, không tự xuất hiện trên `runtimeClasspath` của ứng dụng. Khi một packaging plugin tạo fat JAR, nó đọc dependency graph của project theo logic riêng, chứ không “tự lấy tất cả JAR của plugin classpath để gộp”.

Ngoại lệ hợp lệ: plugin có thể **chủ động thêm project dependencies** vào `implementation` hoặc configuration khác nếu đó là một phần hợp đồng plugin. Vì vậy tránh khẳng định “plugin không bao giờ tác động dependencies app”; đúng hơn là **không có tác động mặc định chỉ từ việc tải implementation JAR của plugin**.

## 5. Build script dependency: “Chính build.gradle cần class nào?”

Cách legacy để cấp class cho Groovy build script:

~~~groovy
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath 'org.yaml:snakeyaml:2.7'
    }
}

// Mã của chính build.gradle dùng thư viện trên.
def document = new org.yaml.snakeyaml.Yaml()
    .load('label: gradle-script')

assert document.label == 'gradle-script'
~~~

- `buildscript.repositories` là nguồn để resolve **build script classpath**.
- `buildscript.dependencies.classpath` đưa class SnakeYAML vào môi trường **biên dịch/đánh giá Gradle script**.
- `new org.yaml.snakeyaml.Yaml()` chạy trong **configuration phase** của build.
- Java source của project **không được** thêm SnakeYAML chỉ vì script sử dụng nó.

Nếu Java `src/main/java/demo/App.java` cũng cần import `org.yaml.snakeyaml.Yaml`, bạn phải khai báo riêng `implementation 'org.yaml:snakeyaml:2.7'` trong dependencies của project. Việc JAR giống nhau có thể giúp Gradle cache tải xuống, nhưng không biến các scope thành một.

### 5.1. Buildscript classpath khác `compileClasspath`

| Classpath | Ai tiêu thụ |
| --- | --- |
| `buildscript.dependencies.classpath` | Mã Groovy/Kotlin trong build script |
| Plugin classpath | Gradle/plugin implementation để cấu hình/thi hành build |
| `compileClasspath` | Compiler biên dịch Java source chính |
| `runtimeClasspath` | JVM chạy ứng dụng và task dùng runtime files |
| `testCompileClasspath`/`testRuntimeClasspath` | Compile/run tests |
| Annotation processor path | Processor chạy khi Java compile |

Một lỗi “Could not resolve for configuration ':classpath'” trong `buildscript` khác với lỗi `:app:runtimeClasspath`. Phải xem lỗi có xuất hiện từ `buildscript { }`, plugin resolver hay project configuration nào.

### 5.2. Legacy plugin application: nạp class chưa đồng nghĩa apply

Một build cũ có thể khai báo:

~~~groovy
buildscript {
    repositories {
        gradlePluginPortal()
    }
    dependencies {
        classpath 'com.gradleup.shadow:com.gradleup.shadow.gradle.plugin:9.6.1'
    }
}

apply plugin: 'com.gradleup.shadow'
~~~

Phần `classpath` thêm plugin implementation/marker dependency vào buildscript environment, còn `apply plugin:` mới là bước **áp dụng** plugin vào project. Đây là **cách legacy**, thường nên dùng `plugins { id 'com.gradleup.shadow' version '9.6.1' }` khi có thể.

Đừng vừa khai báo plugin version ở `plugins { }` lại vừa thêm cùng plugin version khác ở `buildscript.classpath` trong một project mà không hiểu classloader/version conflict. Tương tự, chỉ đặt Maven artifact vào `implementation` không làm `apply plugin:` tự được gọi.

### 5.3. Script plugin `apply from:`

~~~groovy
// build.gradle — minh họa khi file có thật:
apply from: "$rootDir/gradle/quality.gradle"
~~~

Đây là cách nạp một **script plugin** (file Gradle DSL) trong ngữ cảnh target nhận script, không phải binary plugin được khai báo từ Plugin Portal bằng plugin ID. Một script plugin thông thường không hỗ trợ `plugins { }` theo cách project build script sử dụng; plugin cần thiết nên được khai báo trong build chính hoặc đóng gói thành precompiled script plugin.

Với logic lặp lại nhiều nơi, hãy cân nhắc convention plugin và typed APIs thay vì phụ thuộc thứ tự thực thi của nhiều script legacy.

## 6. Ba nơi cấu hình repository

Đặt cạnh nhau:

~~~text
settings.gradle
    pluginManagement.repositories
        -> plugins { id + version }

    dependencyResolutionManagement.repositories
        -> project dependencies, nếu được cấu hình ở settings

build.gradle
    repositories
        -> dependencies { implementation, runtimeOnly, ... }

    buildscript.repositories
        -> buildscript.dependencies { classpath ... }
~~~

Một ví dụ quản lý repository **tập trung** ở settings:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'central-repositories'
~~~

Với `FAIL_ON_PROJECT_REPOS`, các project không được khai báo thêm `repositories { ... }` riêng: nếu vẫn làm, Gradle có thể báo lỗi. Vì vậy **đừng ghép ví dụ settings này với build.gradle có project repositories của demo dưới đây** mà không điều chỉnh. Nó là một chiến lược khác.

Điểm then chốt:

- `pluginManagement.repositories` giải quyết plugin DSL, không phải app library.
- `dependencyResolutionManagement.repositories` giải quyết project dependencies khi settings quản lý nguồn.
- `buildscript.repositories` giải quyết thư viện/plugin legacy mà script cần.
- `GRADLE_USER_HOME/caches` có thể cache các artifact cho nhiều scope, nhưng cache vật lý **không đồng nghĩa một classpath duy nhất**.

Trong enterprise, có thể cần một Maven proxy/mirror khác cho từng loại, với chính sách credentials/allowlist khác nhau. Thêm repository bừa bãi có thể làm dependency resolution thay đổi nguồn và gây rủi ro supply-chain.

## 7. Demo hoàn chỉnh: cả ba loại trong một Java 17 project

Để thấy khác biệt, dự án demo dùng:

1. `application` **core plugin**.
2. Commons Lang3 **project implementation dependency** cho class Java.
3. SnakeYAML **buildscript classpath dependency** để build.gradle parse chuỗi YAML.

Cần một project đã có Gradle Wrapper hợp lệ, Java 17 được phát hiện (hoặc provision qua toolchain resolver phù hợp), và truy cập Maven Central để tải Commons Lang/SnakeYAML.

### 7.1. Cấu trúc file

~~~text
dependency-scopes-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    └── main/
        └── java/
            └── demo/
                └── App.java
~~~

Bốn file Wrapper là thành phần chuẩn của một dự án đã thiết lập Wrapper, không được thay thế bằng các file trống.

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'dependency-scopes-demo'
~~~

### 7.3. `build.gradle` — file đầy đủ

~~~groovy
// Classpath cho chính Groovy build script.
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath 'org.yaml:snakeyaml:2.7'
    }
}

// Plugin cung cấp model/task để build Java app.
plugins {
    id 'application'
}

// Repository của thư viện dùng cho application.
repositories {
    mavenCentral()
}

// App source dùng Commons Lang khi compile và runtime.
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

// Chọn JDK của các task Java phù hợp.
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}

// Chỉ build script sử dụng class SnakeYAML trong configuration.
def parsed = new org.yaml.snakeyaml.Yaml()
    .load('label: build-script-only')
assert parsed.label == 'build-script-only'
~~~

**Thứ tự block:** khi dùng chung `buildscript { }` và `plugins { }` trong cùng một Groovy build script, khối `buildscript` đứng trước `plugins`. `plugins` phải nằm đầu script theo các ràng buộc của plugin DSL, trước những logic thông thường như `repositories`, `dependencies` và khai báo task. Tránh chèn mã tùy ý trước `plugins`.

Ở đây `assert` không in output; nó chỉ kiểm tra SnakeYAML có trên buildscript classpath. Nếu bỏ dòng `classpath` của SnakeYAML, Gradle không thể resolve class mà script cần, dù Commons Lang vẫn được khai báo cho app. Việc parse YAML như trên phục vụ học tập; trong production nên tránh làm cấu hình dài và phức tạp ở top level chỉ vì có thể chạy mã Groovy.

### 7.4. `src/main/java/demo/App.java`

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String input = args.length == 0 ? "Gradle" : args[0];
        System.out.println("app.reverse=" + StringUtils.reverse(input));
    }
}
~~~

Public class `App` nằm trong file `App.java` đúng package `demo`. Nó có thể chạy trên Java 17 khi Commons Lang JAR có trong classpath. Nếu chỉ gọi `javac App.java` không kèm classpath, chương trình sẽ **không biên dịch** vì không biết `StringUtils`; Gradle lo việc này qua `implementation`.

### 7.5. Chạy và stdout

Linux/macOS, ở thư mục root:

~~~bash
./gradlew -q run
./gradlew -q run --args='Hello'
~~~

Stdout của chương trình Java lần lượt là:

~~~text
app.reverse=eldarG
~~~

và:

~~~text
app.reverse=olleH
~~~

PowerShell Windows:

~~~powershell
.\gradlew.bat -q run
.\gradlew.bat -q run --args="Hello"
~~~

`run` là task do `application` plugin cung cấp; `--args` là **application arguments** truyền vào `main(String[])`, khác với `-P` project property và JVM options như `-Xmx`.

Các dòng trên là stdout của `App.main`. Gradle/JDK vẫn có thể đưa ra cảnh báo môi trường riêng. Khi Wrapper hoặc Maven repositories chưa sẵn, build có thể cần mạng và không nên kỳ vọng lệnh `--offline` luôn hoạt động.

### 7.6. Đối chiếu graph

~~~bash
# Dependency cho runtime của Java app:
./gradlew dependencies --configuration runtimeClasspath

# Dependency của build script:
./gradlew buildEnvironment

# Phân tích version Commons Lang trong runtime graph:
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3

# Xem các task do plugin tạo:
./gradlew tasks --all
~~~

Về mặt khái niệm:

- `runtimeClasspath` phải có Commons Lang3 phục vụ Java app; **không tự chứa SnakeYAML chỉ do build.gradle dùng nó**.
- `buildEnvironment` hiển thị dependency graph của buildscript classpath; nó không phải report runtime của app.
- `tasks` có task `run` nhờ Application plugin.
- `dependencyInsight` giúp tìm đường dẫn resolution và version cuối của một dependency **trong configuration được chỉ định**.

Plugin DSL có cơ chế resolution riêng; không mặc định mọi external plugin JAR sẽ được hiển thị trong report `buildEnvironment` y như một dependency khai báo trực tiếp trong `buildscript.classpath`.

### 7.7. Ba thử nghiệm lỗi độc lập

Chỉ làm trên **bản sao demo**, thay từng mục rồi khôi phục:

1. Bỏ `implementation 'org.apache.commons:commons-lang3:3.17.0'`: `App.java` import `StringUtils` sẽ thiếu class khi compile. Plugin và SnakeYAML buildscript vẫn có thể được tải.
2. Bỏ `classpath 'org.yaml:snakeyaml:2.7'` nhưng giữ `new org.yaml.snakeyaml.Yaml()`: build script có thể fail **ngay ở configuration**, trước task compile app.
3. Bỏ `id 'application'` và khối `application { }`: Gradle sẽ không có task `run` của Application plugin. Commons Lang không tự tạo task chạy app.

Ba lỗi này không thể “chữa chung” bằng cách thêm mọi JAR vào mọi block.

## 8. Plugin alias và library alias trong Version Catalog

Version Catalog có thể tập trung thông tin vào `gradle/libs.versions.toml`:

~~~toml
[versions]
commons = "3.17.0"
shadow = "9.6.1"

[libraries]
commonsLang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commons" }

[plugins]
shadow = { id = "com.gradleup.shadow", version.ref = "shadow" }
~~~

Groovy `build.gradle`:

~~~groovy
plugins {
    id 'application'
    alias(libs.plugins.shadow)
}

repositories {
    mavenCentral()
}

dependencies {
    implementation libs.commonsLang3
}
~~~

- `libs.plugins.shadow` là **plugin alias** dùng trong `plugins`.
- `libs.commonsLang3` là **library alias** dùng trong `dependencies`.
- Catalog giúp tập trung tọa độ/versions, **không tự biến hai loại thành cùng classpath**.
- Catalog version không nhất thiết cưỡng chế version cuối khi constraints/resolution override khác được dùng.
- Không mặc định có thể dùng `libs.plugins.*` cho **settings plugin**, vì catalog accessor chưa sẵn tại mọi giai đoạn settings.
- `buildscript.classpath` vẫn là một yêu cầu dành cho **build script**; một alias library không tự được dùng như plugin ID chỉ vì đặt nó trong TOML.

Đối với nhiều dự án, plugin DSL và catalogs giúp giảm lặp version. Với build logic nội bộ phức tạp, nên đóng gói thành convention plugin thay vì tăng dần `buildscript.classpath` ở mọi module.

## 9. `buildSrc` và included build `build-logic` có graph riêng

Một build lớn có thể tái sử dụng logic qua:

- `buildSrc`: build riêng ở root được Gradle tự compile rồi đưa build logic thích hợp vào buildscript classpath của main build.
- Included build `build-logic`: build Gradle riêng để tạo convention/binary plugins, có thể khai báo trong `pluginManagement.includeBuild`.
- Plugin phát hành ở repository: resolve theo plugin ID/version giống external plugin.

Mẫu layout:

~~~text
repo/
├── settings.gradle
├── build.gradle
├── app/build.gradle
└── build-logic/
    ├── settings.gradle
    ├── build.gradle
    └── src/main/groovy/
        └── company.java-conventions.gradle
~~~

Root `settings.gradle` có thể cấu hình:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'example'
include 'app'
~~~

Trong `app/build.gradle`:

~~~groovy
plugins {
    id 'company.java-conventions'
}
~~~

Đây là **mô hình minh họa**, chưa đủ standalone để chạy: project `build-logic` cần plugin như `groovy-gradle-plugin` và source/metadata đúng để tạo plugin ID này. Ý chính: `implementation` **bên trong build-logic build** phục vụ **code của plugin/build logic**; nó không đồng nghĩa `implementation` **bên trong app** phục vụ app source/runtime.

Ví dụ nếu convention plugin phải dùng SnakeYAML để xử lý dữ liệu build, nó có thể khai báo SnakeYAML trong **dependencies của build-logic project**. Nếu Java app cũng cần SnakeYAML để xử lý nghiệp vụ, app vẫn phải có dependency của chính nó.

Không biến một module `:library` bình thường thành plugin chỉ bằng cách dùng `implementation project(':library')`. Plugin cần được triển khai, đăng ký và áp dụng theo plugin mechanisms.

## 10. Các nhầm lẫn thường gặp

| Triệu chứng | Phạm vi cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Java compile báo `package ... does not exist` | Project `compileClasspath` | Bổ sung `implementation`/`api`/`compileOnly` phù hợp, kiểm repository |
| App chạy báo `ClassNotFoundException`/`NoClassDefFoundError` | Project `runtimeClasspath` | Kiểm runtime variants, `compileOnly` dùng sai, dependency transitive |
| `Could not find method implementation()` | Plugin/configuration của project | Áp dụng Java/Application/plugin tạo configuration |
| `Could not find method api()` | Java library model | `api` cần plugin `java-library` hoặc plugin cung cấp tương đương |
| `Plugin [id: ...] was not found` | Plugin resolution | Plugin ID/version, marker, `pluginManagement.repositories`, included build |
| Có plugin nhưng task chưa tồn tại | Plugin application/target | Kiểm đã apply đúng project và task có được plugin tạo không |
| Script không biết class `org.yaml.snakeyaml.Yaml` | Buildscript classpath | `buildscript.dependencies.classpath` và nguồn repo |
| `Could not resolve ... for configuration ':classpath'` | Buildscript/related script classpath | Kiểm nguồn của đúng classpath; không chỉ sửa app repositories |
| Thêm `buildscript.classpath` nhưng plugin không được apply | Legacy plugin mechanism | Cần `apply plugin: 'id'` nếu plugin legacy và classpath đã sẵn |
| Thêm plugin vào `implementation` nhưng `plugins { }` không hoạt động | Sai loại dependency | Dùng đúng Plugin ID/version và repository |
| Thêm `repositories { mavenCentral() }` vẫn không resolve plugin | Plugin repository khác app repo | Thêm đúng `pluginManagement.repositories` |
| App phụ thuộc thư viện đúng nhưng version khác | Project conflict resolution | `dependencyInsight` trên đúng configuration/project |
| Plugin báo “already on classpath” hoặc yêu cầu không khai version | Plugin classloader/version | Kiểm root `apply false`, `buildSrc`/build-logic, khai báo trùng version |
| Cache có JAR nhưng build offline fail | Cache thiếu artifact cho scope khác | Kiểm Wrapper, Plugin Portal, project dependencies và buildscript graph |
| Multi-module app chưa thấy output library | Project dependency và variants | `implementation project(':library')`, settings include, plugin của library |

Đọc thông báo lỗi để xác định **đúng configuration và đúng project**. Cùng có từ “classpath”, nhưng `:classpath` của buildscript và `:app:runtimeClasspath` có ý nghĩa khác nhau.

### 10.1. Bộ lệnh chẩn đoán

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew buildEnvironment

./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3

# Với module app:
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
~~~

`buildEnvironment` là report cho buildscript dependencies, trong khi `dependencies`/`dependencyInsight` nhắm vào project configuration đã chọn. Cần áp dụng plugin tạo `compileClasspath`/`runtimeClasspath` trước khi dùng các cấu hình đó. Với plugin bên thứ ba, đôi khi phải xem thêm report hoặc task chuyên biệt của plugin.

Đừng vội `--refresh-dependencies` hoặc xóa `~/.gradle/caches` nếu chưa biết đang thiếu **plugin ID**, artifact ở **script classpath**, hay library của **app**. Refresh không tạo ra một dependency mà build chưa khai báo, cũng không chữa sai repo/plugin ID.

## 11. Repository security, versions và khả năng tái lập

Vì các loại dependency có repository/resolution khác nhau, review cần cân nhắc:

1. **Pin phiên bản plugin và thư viện** phù hợp với compatibility matrix của Gradle/Java.
2. Ưu tiên **Gradle Wrapper** cho CI và máy dev, không tùy tiện dùng bản Gradle toàn cục.
3. Cân nhắc **dependency locking/verification**, checksum hoặc chính sách tổ chức khi cần supply-chain integrity.
4. Chỉ dùng repository có nguồn đáng tin; giới hạn Maven mirror/repository theo quy định nội bộ.
5. Không commit token/password trong `settings.gradle` hoặc `build.gradle`; truyền qua secret store, environment hay user-home configuration phù hợp.
6. Đừng suy rằng cùng một JAR trong Gradle cache nghĩa hai classpath chia sẻ version và behavior.
7. Plugin là mã **chạy với quyền của build process**; cần review plugin không kém review application dependency.
8. Khi plugin bên thứ ba tự thêm library vào project, đọc tài liệu của plugin và xác định scope/version thật của library đó.

Tính an toàn cần được xét cho cả **cấu hình build** lẫn **mã sản phẩm**, vì plugin/script helper thực thi code trong quy trình build trước khi artifact ứng dụng được tạo.

## 12. Quy trình chọn đúng loại dependency

Dùng ba câu hỏi:

1. **Java/Kotlin source hay test cần class?** Chọn dependency configuration của **project** như `implementation`, `api`, `testImplementation`, `runtimeOnly`.
2. **Muốn Gradle có task, extension hoặc logic build mới?** Chọn **plugin** qua `plugins { id ... version ... }` hoặc convention plugin nội bộ.
3. **Chính `build.gradle` cần import/call library?** Đó là dependency build logic; với script legacy có thể dùng `buildscript.classpath`, còn giải pháp lâu dài thường là build-logic plugin.

Ví dụ:

| Nhu cầu | Cách khai báo đúng |
| --- | --- |
| App dùng `StringUtils` | `implementation 'org.apache.commons:commons-lang3:3.17.0'` |
| Gradle tạo task chạy app | `plugins { id 'application' }` |
| Gradle tạo fat JAR | `plugins { id 'com.gradleup.shadow' version '9.6.1' }` |
| Script dùng SnakeYAML khi configuration | `buildscript { dependencies { classpath 'org.yaml:snakeyaml:2.7' } }` |
| Java source dùng SnakeYAML lúc runtime | `implementation 'org.yaml:snakeyaml:2.7'` |
| Test code cần JUnit | `testImplementation`/`testRuntimeOnly` thích hợp |
| App cần module `:library` | `implementation project(':library')` |
| Convention plugin cần helper library | `implementation` của **build-logic project**, không tự thêm vào app |
| Build dùng plugin nội bộ được include | `pluginManagement.includeBuild` và `plugins { id '...' }` |

## 13. Bài tập học theo lỗi

**Bài 1.** Java `App.java` import `StringUtils`, nhưng chỉ có `buildscript.classpath 'org.apache.commons:commons-lang3:3.17.0'`. Vì sao compiler không tìm thấy class? Vì buildscript classpath không phải project compile classpath. Sửa bằng `implementation` trong project.

**Bài 2.** Thêm `implementation 'com.gradleup.shadow:...'` rồi chạy `shadowJar` nhưng task không tồn tại. Vấn đề gì? Bạn đã thêm **library của app** thay vì áp dụng plugin. Dùng `plugins { id 'com.gradleup.shadow' version '...' }` với version tương thích.

**Bài 3.** `plugins { id 'application' }` đã có, nhưng `build.gradle` gọi `new org.yaml.snakeyaml.Yaml()` và lỗi class missing. Cần gì? Nếu vẫn xử lý YAML trong script, cần `buildscript.classpath` phù hợp hoặc chuyển logic sang plugin có dependency riêng; `implementation` app không cấp class cho script.

**Bài 4.** Project resolve được Commons Lang từ Maven Central nhưng external plugin báo “not found”. Xem ở đâu? `pluginManagement.repositories` và plugin marker/resolution, không chỉ `repositories` của project.

**Bài 5.** Chạy `./gradlew buildEnvironment` và `./gradlew dependencies --configuration runtimeClasspath` ở demo. Chỉ ra vì sao SnakeYAML và Commons Lang không được kỳ vọng xuất hiện ở cùng một report.

**Bài 6.** `:app` dùng `implementation project(':library')`. Điều đó có áp dụng plugin của `:library` vào `:app` không? Không. Dependency project để lấy output/library variants, còn plugin áp dụng riêng theo project.

**Bài 7.** Một version catalog có `[libraries]` và `[plugins]`. Thử `implementation libs.commonsLang3` và `alias(libs.plugins.shadow)`; hãy giải thích tại sao cùng catalog không đồng nghĩa cùng resolution scope.

**Bài 8.** Bỏ lần lượt một trong ba thành phần của demo: Application plugin, Commons Lang app dependency, SnakeYAML buildscript dependency. Ghi nhận lỗi phát sinh trong từng trường hợp (task không tồn tại, Java compile class missing, build script configuration class missing). Khôi phục file sau thử nghiệm; không thực hành trực tiếp trên build production.

## 14. Checklist ghi nhớ

1. “Dependency” là quan hệ **ai cần code gì**, không chỉ là tên một JAR.
2. `implementation` và các configuration tương tự thuộc **project source/test/runtime**; cần plugin thích hợp tạo ra chúng.
3. `plugins { }` dùng **Plugin ID**, để Gradle resolve/apply logic build; plugin implementation JAR không tự thành app runtime library.
4. `buildscript.classpath` cung cấp class cho **chính build script**; nó không tương đương `compileClasspath` của app.
5. Ba nguồn repository là `pluginManagement.repositories`, project `repositories`/`dependencyResolutionManagement` và `buildscript.repositories`.
6. Plugin có thể **chủ động thay đổi project dependencies**, nhưng chỉ tải plugin classpath không tự làm vậy.
7. `buildSrc` và `build-logic` là những **build riêng** có dependency graph của chính chúng.
8. Version Catalog gom khai báo versions chứ không xóa ranh giới giữa `[plugins]` và `[libraries]`.
9. Dùng `buildEnvironment`, `dependencies` và `dependencyInsight` với đúng project/configuration để phân tích lỗi.
10. Dùng Wrapper, chọn plugin/library version tương thích, bảo vệ credentials và tránh repository không tin cậy.

## Tài liệu tham khảo chính thức

- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html): dependency của project và các loại Maven/project/file dependency.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html): `implementation`, `api`, `compileOnly`, `runtimeOnly` và test classpaths.
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): `plugins { }`, `pluginManagement`, plugin marker và legacy `buildscript.classpath`.
- [Gradle — Declaring Repositories Basics](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html): plugin repositories khác project repositories.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): `[libraries]`, `[plugins]` và aliases.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): `buildSrc`, included build-logic và convention plugins.
- [Gradle Plugin Portal — Shadow](https://plugins.gradle.org/plugin/com.gradleup.shadow): plugin ID/version và cách áp dụng.
