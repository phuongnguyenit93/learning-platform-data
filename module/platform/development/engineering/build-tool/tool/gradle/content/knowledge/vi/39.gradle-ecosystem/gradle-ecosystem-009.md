# Phân biệt API cốt lõi Gradle với khả năng do plugin của từng hệ sinh thái cung cấp

## Mục tiêu và bức tranh tổng thể

Gradle không phải một bộ lệnh cố định chỉ biết `compileJava`, `compileKotlin`, `assembleDebug`, `bootJar` hoặc `shadowJar`. Gradle trước hết là **build engine có mô hình Project, Task, dependency resolution, configuration, Provider, build lifecycle và plugin mechanism**. Những công việc đặc thù cho Java, Kotlin, Android, Spring Boot, publishing hoặc đóng gói fat JAR thường được một **plugin** đưa vào project.

Điểm quan trọng là có **hai chữ “core” dễ bị nhầm**:

1. **Gradle core API / infrastructure**: các interface, services và cơ chế engine như `Project`, `Settings`, `Task`, `TaskContainer`, `Provider`, `Property`, `Configuration`, `DependencyHandler`, `PluginManager` và task graph. Chúng dùng để **diễn tả, cấu hình, lập lịch, thực thi và cache** công việc.
2. **Gradle core plugins**: những plugin **đi kèm Gradle distribution**, ví dụ `java`, `java-library`, `application`, `base`, `maven-publish`, `signing`, `jacoco`. Tuy plugin có sẵn không cần tải từ Plugin Portal, **khả năng của plugin vẫn phải được áp dụng vào project phù hợp**.

Ngoài ra còn **external/community plugins** như JetBrains Kotlin Gradle Plugin, Android Gradle Plugin, Spring Boot plugin, Spotless/Shadow và **custom/convention plugins** do đội phát triển tạo ra. Chúng đều dựa trên Gradle plugin mechanism nhưng đóng góp domain model, task types, tasks, configurations, extensions và conventions khác nhau.

Sau bài này bạn có thể:
- Xác định một tên trong build.gradle thuộc **Gradle API**, **core plugin**, **external plugin**, **project code** hay **convention plugin**.
- Giải thích vì sao `tasks.register` dùng được trong build script nhưng `compileJava`, `implementation`, `java {}`, `android {}` hoặc `bootJar` không tồn tại trên mọi project.
- Hiểu việc **có class trong Gradle API** khác với **có instance/task/extension được đăng ký trong project**.
- Đọc `plugins {}`, `pluginManagement {}`, `repositories {}`, `dependencies {}`, extension DSL và tasks đúng vai trò.
- Điều tra lỗi “Could not find method”, “Task not found”, unresolved plugin id và version compatibility.
- Tạo lab **Java 17 multi-project** có root task được đăng ký bằng core APIs, thư viện `java-library` và ứng dụng `application`.
- Bổ sung một **custom binary plugin trong buildSrc** và xác nhận task mới chỉ tồn tại sau khi plugin được áp dụng.
- Thao tác đúng với `PluginManager`, `TaskProvider`, lazy configuration, plugin callbacks, scope và multi-project builds.
- Đọc bảng đối chiếu Java/Kotlin/Android/Spring/publishing và chọn plugin phù hợp.
- Vận dụng checklist khi thiết kế project hoặc chuyển build từ một hệ sinh thái khác sang Gradle.

Bài dùng **Groovy DSL** cho lab chính, có Kotlin DSL và mã Java 17. Các ví dụ liên quan Android/Kotlin/Spring có thể là **fragment minh họa**, vì để chạy thật cần SDK, plugin version, repository và compatibility riêng. Lab Java chính không đòi Maven dependencies ngoài Gradle Wrapper/JDK.

---

## 1. Tư duy kiến trúc: engine là nền, plugin định nghĩa nghiệp vụ build

Hình dung Gradle như một bộ máy tổ chức công việc:

~~~text
                           Gradle Build Engine
          +--------------------------------------------------+
          | Project / Settings / Gradle / Task graph          |
          | Providers / Properties / dependency resolution     |
          | Repositories / Configurations / execution          |
          | Incremental build / Build Cache / lifecycle       |
          | PluginManager / ExtensionContainer / logging      |
          +------------------------+-------------------------+
                                   |
                 plugin mechanism: apply plugin
                                   |
                 +-----------------+-------------------+
                 |                 |                   |
           Core Plugins      External Plugins    Team Plugins
           java, base,       Kotlin, AGP,        convention,
           application,      Spring, Shadow      custom binary
           maven-publish     Spotless, etc.     or script
                 |                 |                   |
                 +-----------------+-------------------+
                                   |
                         Project-specific model
                  tasks / extensions / configurations
                         conventions / outputs
~~~

Gradle cung cấp **cơ chế đăng ký một task**. Nhưng task `compileJava` thường do Java plugin đăng ký; `bootJar` do Spring Boot plugin tạo/cấu hình; `assembleDebug` phát sinh từ mô hình Android variants của Android Gradle Plugin (AGP) khi app/variant phù hợp.

Vì vậy:

- **“Gradle có API Task”** không đồng nghĩa **“mọi project có task compileJava”**.
- **“Gradle distribution có Java plugin”** không đồng nghĩa **“project không cần apply Java plugin”**.
- **“Gradle hiểu dependency configurations”** không đồng nghĩa **“mọi project có configuration implementation”**.
- **“Build file dùng Groovy/Kotlin DSL”** không đồng nghĩa **“project đang compile Groovy/Kotlin source”**.
- **“Có plugin ID trong catalog”** không đồng nghĩa **“plugin đã được apply”**.

### 1.1. Cách xác định nguồn gốc một khả năng

Với bất kỳ biểu thức nào, hãy hỏi:

1. Nó là **API có sẵn trên `Project`/`Settings`/`Task`** hay extension/task được plugin đăng ký?
2. Plugin nào **áp dụng trực tiếp hoặc gián tiếp** tạo ra nó?
3. Plugin đó là **core bundled** hay external có version phải resolve?
4. Plugin được apply **ở project nào**?
5. Capability là một **task instance**, **task type**, **configuration**, **extension** hay **convention**?
6. Nó xuất hiện trong **configuration phase** hay chỉ chạy action ở **execution phase**?
7. Nếu thay plugin/version, tên hoặc hành vi có đổi không?

---

## 2. Gradle core API: những đối tượng quan trọng

| API hoặc cơ chế | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `Project` | Mô hình một build project và các containers/services | `project.name`, `project.path`, `project.layout` |
| `Settings` | Xác định build layout, subprojects, plugin management | `include 'app'`, `pluginManagement {}` |
| `Gradle` | Truy cập build runtime/lifecycle services | `gradle.gradleVersion` |
| `Task` | Đơn vị công việc, actions, inputs/outputs, dependencies | `doLast`, `dependsOn` |
| `TaskContainer` | Đăng ký/tìm/cấu hình tasks của project | `tasks.register('hello')` |
| `TaskProvider<T>` | Handle lazy để cấu hình/truy cập task | `tasks.named('jar')`, `dependsOn` |
| `Provider<T>` | Giá trị tính lazy có dependency semantics | `providers.gradleProperty('mode')` |
| `Property<T>` | Mutable lazy property có conventions và finalization | `Property<String>` |
| `ProjectLayout` | File/Directory Providers, đường dẫn build | `layout.buildDirectory.file('x.txt')` |
| `ConfigurationContainer` | Quản lý dependency configurations | `configurations.create('myBucket')` |
| `DependencyHandler` | Tuyên bố dependencies giữa modules/artifacts | `dependencies { ... }` |
| `RepositoryHandler` | Khai báo sources để resolve dependencies | `repositories { mavenCentral() }` |
| `PluginManager` | Apply/kiểm tra/phản ứng khi plugin xuất hiện | `pluginManager.hasPlugin('java')` |
| `ExtensionContainer` | Chứa extension objects được plugin/project tạo | `extensions.findByName('java')` |
| `ObjectFactory` | Tạo Gradle managed objects/Property | `objects.property(String)` |
| Gradle build lifecycle | Initialization, configuration, execution | tasks registered then executed |

Các API này tạo **khả năng mô hình hóa** build. Ví dụ `tasks.register('hello')` hoạt động trên một project thông thường, ngay cả khi không có plugin Java. Nhưng để build Java với các conventions như `src/main/java`, `compileJava`, `test`, `jar`, bạn cần plugin phù hợp.

### 2.1. Root Project khác Settings

`settings.gradle` hoặc `settings.gradle.kts` chứa `rootProject.name`, `include`, `pluginManagement`. `build.gradle` hoặc `.kts` cấu hình **Project** và tasks. Không thể chép trực tiếp `settings { include(...) }` vào mọi `build.gradle` như một extension plugin.

`settings.gradle`:

~~~groovy
rootProject.name = 'capability-lab'
include 'library', 'app'
~~~

`build.gradle`:

~~~groovy
tasks.register('coreHello') {
    doLast {
        println 'CORE_TASK_OK'
    }
}
~~~

`include` là của Settings, còn `tasks` là TaskContainer của Project. Cả hai thuộc Gradle core model, nhưng ở **scope khác nhau**.

### 2.2. Task registration khác task execution

~~~groovy
tasks.register('hello') {
    group = 'learning'
    description = 'Print a message'

    doLast {
        println 'HELLO_FROM_TASK'
    }
}
~~~

- `tasks.register` **đăng ký** một task (thường lazy).
- Trong configuration phase Gradle tạo mô hình cần thiết.
- `doLast` là action thực thi khi task được chọn vào task graph và chạy.
- Chỉ `./gradlew hello` mới yêu cầu action chạy; `./gradlew help` không tự thực thi hello.
- Task có thể bị skip/UP-TO-DATE tùy inputs/outputs và build semantics.

**Task là API core; tên task hello là do chính build author đăng ký.**

### 2.3. Provider và Property không chỉ dành cho Java plugin

~~~groovy
def mode = providers.gradleProperty('mode')
    .orElse('local')

tasks.register('showMode') {
    def selectedMode = mode
    doLast {
        println "MODE=${selectedMode.get()}"
    }
}
~~~

Trong Groovy script, `providers` là service của Gradle Project. Đoạn này không cần Java plugin. Tuy nhiên, khi dùng configuration cache, cần tránh capture Project/script objects trong task actions; một convention plugin với typed task input là cấu trúc vững hơn cho công việc production. Đoạn trên chỉ giải thích khái niệm Provider.

### 2.4. Dependency resolution core không quyết định tên configuration

Gradle biết cách tạo và resolve `Configuration` objects. Nhưng `implementation`, `api`, `testImplementation` không phải “các biến cố định toàn cục” của Gradle:
- `java` tạo configurations theo conventions Java.
- `java-library` bổ sung `api` và tách API vs implementation.
- Kotlin plugin bổ sung model/configurations phù hợp targets.
- Android plugin thiết kế thêm build types, flavors/variants và classpaths.

**Configuration là cơ chế; tên và nghĩa của nhiều configurations là do plugin.**

---

## 3. Core plugins là plugin, không phải toàn bộ core API

“Core plugin” trong tài liệu Gradle nghĩa là plugin **được đóng gói sẵn trong Gradle distribution**, thường apply bằng ID không có version trong `plugins {}`:

~~~groovy
plugins {
    id 'java-library'
}
~~~

Không cần khai `version` vì plugin này đi kèm Gradle Wrapper. Điều đó **không** làm `java-library` trở thành global API tự động áp vào mọi project.

### 3.1. Một số core plugin nổi bật

| Plugin ID | Đóng góp tiêu biểu | Lưu ý |
| --- | --- | --- |
| `base` | `clean`, `assemble`, `check`, `build` lifecycle tasks | Lifecycle conventions do plugin tạo |
| `java` | Source sets, JavaCompile/Test/Jar tasks, Java dependency configurations | `compileJava`, `test`, `jar`, `java {}` |
| `java-library` | Mở rộng Java với `api` vs `implementation` | Dành cho reusable Java libraries |
| `application` | `run`, `startScripts`, `installDist`, `distZip`, `distTar`, `application {}` | Áp dụng Java/Distribution tương ứng |
| `maven-publish` | `publishing {}`, MavenPublication và publish tasks | Không phải mọi project đều có publish |
| `signing` | `signing {}`, sign tasks và signature artifacts | Không tự cấp key |
| `jacoco` | Coverage-related tasks và report integrations | Coverage verification gate cần cấu hình |
| `java-platform` | Platform/constraints/BOM-style publishing | Không compile Java sources |
| `groovy` | Compile Groovy, Groovydoc, Groovy configurations | Là core plugin, khác Groovy DSL script |
| `java-gradle-plugin` | Hỗ trợ author/publish Gradle plugins và descriptors | Dùng trong plugin development |

**Quan trọng:** `java`/`java-library` là plugins có sẵn, nhưng `implementation` chỉ có khi JVM Java model tương ứng được apply. `maven-publish` là core plugin nhưng `publishing {}` không phải Project method mặc định cho mọi project.

### 3.2. `assemble` và `build` cũng có nguồn gốc plugin

Các lifecycle tasks này được đưa vào bởi `base` plugin, thường được các JVM/application plugins apply transitively. Một root Project **không apply plugin nào** vẫn có thể đăng ký task thủ công nhưng không nên giả định mọi lifecycle task đều tồn tại ở đó.

### 3.3. `java-library` khác `java`

`java-library` áp Java functionality và bổ sung API/implementation separation:
- `api` cho dependencies được phơi vào compile classpath của consumers.
- `implementation` cho dependencies nội bộ của library.
- Compilation/test/JAR conventions từ Java model.

Không nhầm `api` Gradle **core API** (nhóm interface của Gradle) với `api` **dependency configuration** do Java Library plugin đưa vào. Hai từ trùng tên nhưng không cùng khái niệm.

### 3.4. `application` khác `java`

`java` cung cấp Java compilation/test/JAR. `application` bổ sung khả năng **chạy application**, chỉ định mainClass và tạo distributions có start scripts/dependencies. Nếu project chỉ apply `java`, `:app:run` và `:app:distZip` không mặc định có; cần `application` hoặc plugin tương đương.

---

## 4. External plugins: mỗi hệ sinh thái bổ sung một mô hình

External/community plugin được publish ngoài Gradle distribution, thường cần plugin ID **và version**, cùng plugin repository tương ứng.

### 4.1. Ma trận hệ sinh thái

| Hệ sinh thái | Plugin ví dụ | DSL/task tiêu biểu | Không phải Gradle core mặc định |
| --- | --- | --- | --- |
| Kotlin JVM | `org.jetbrains.kotlin.jvm` | `kotlin {}`, `compileKotlin`, `compileTestKotlin`, Kotlin compiler options | Kotlin compilation |
| Kotlin Multiplatform | `org.jetbrains.kotlin.multiplatform` | `kotlin { targets/sourceSets }`, tasks theo target | KMP targets/variants |
| Android application | `com.android.application` | `android {}`, `assembleDebug`, Android variant tasks | Android SDK model |
| Android library | `com.android.library` | Android library variants/AAR packaging | AAR model |
| Spring Boot | `org.springframework.boot` | `bootJar`, `bootRun` khi plugin/Java context phù hợp | Spring Boot packaging |
| Shadow | Shadow plugin | `shadowJar`, dependency bundling | Fat/uber-JAR conventions |
| Spotless | `com.diffplug.spotless` | `spotlessApply`, `spotlessCheck` | Formatting policies |
| Protobuf | Protobuf Gradle plugin | Proto source sets/generation/compile wiring | protoc integration |
| Other frameworks | Plugin phù hợp | Custom extension/tasks/variants | Framework-specific work |

Các tasks trong bảng là **điển hình**, không bảo đảm cùng tên ở mọi plugin version và cấu hình. Android tasks thay đổi theo build variants; Spring Boot plugin có tương tác với Java/War/application plugins; Shadow plugin ID đã thay đổi giữa các thế hệ. Luôn kiểm documentation và **phiên bản plugin thực tế**.

### 4.2. Kotlin JVM là external plugin

Một ví dụ Kotlin JVM build script fragment:

~~~groovy
plugins {
    id 'org.jetbrains.kotlin.jvm' version '2.4.21'
}
~~~

Plugin JetBrains Kotlin được resolve theo plugin repositories và compatibility. Khi áp dụng, nó cung cấp Kotlin compilation tasks và DSL/model riêng. **Gradle có thể dùng Kotlin DSL để viết `build.gradle.kts` mà không cần apply Kotlin JVM plugin**; Kotlin DSL là ngôn ngữ build script, còn KGP là compiler/build integration cho nguồn `.kt` trong dự án.

### 4.3. Android Gradle Plugin (AGP)

Ví dụ fragment ở Android app project (không phải lab Java17 này):

~~~groovy
plugins {
    id 'com.android.application' version '9.3.1'
}

android {
    namespace 'org.example.demo'
    compileSdk 36

    defaultConfig {
        applicationId 'org.example.demo'
        minSdk 23
        targetSdk 36
    }
}
~~~

Đây là **minh họa DSL**, cần Android SDK đúng, AGP/Gradle/JDK compatibility và repository plugin resolution (thường có Google Maven). Không thể chạy bằng JDK + Gradle Wrapper đơn thuần nếu thiếu Android SDK. **`android {}` do AGP đóng góp**, không phải built-in Gradle Project extension. Android build variants/task graph cũng do AGP model, không phải tên global task của Gradle.

### 4.4. Spring Boot

Plugin Spring Boot có thể bổ sung `bootJar`, `bootRun`, configuration for executable archives và build image integrations theo version và các plugins cùng được áp dụng. Một Java project **chỉ apply `java`** không tự có `bootJar`; một project có `spring-boot-starter` **dependency** cũng không tương đương với **áp Spring Boot Gradle plugin**.

### 4.5. Dependency không phải plugin

So sánh:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.example:utility:1.0.0'
}
~~~

Dòng `plugins` **thực thi plugin code cấu hình build**. Dòng `implementation` **thêm library artifact vào classpath/runtime graph** qua configuration do plugin Java tạo. Thêm Maven dependency vào `implementation` không có nghĩa áp plugin Gradle, trừ khi một plugin khác có logic đọc dependency đó.

### 4.6. Không copy DSL từ project khác mà không copy plugin

Một snippet `android { compileSdk 36 }` chỉ có nghĩa trong project có Android plugin. `kotlin { jvmToolchain(17) }` yêu cầu Kotlin plugin thích hợp. `publishing {}` yêu cầu maven-publish; `application {}` yêu cầu application. Trước khi sử dụng DSL, hãy xác định **plugin ID, version, scope và source repository**.

---

## 5. Plugin được áp dụng như thế nào?

### 5.1. Project plugins trong `plugins {}`

Groovy DSL:

~~~groovy
plugins {
    id 'java'
}
~~~

Kotlin DSL:

~~~kotlin
plugins {
    java
}
~~~

Core plugin ID có sẵn trong Gradle distribution. External plugin thường khai version:

~~~groovy
plugins {
    id 'org.jetbrains.kotlin.jvm' version '2.4.21'
}
~~~

Không dùng version chỉ vì thấy trên một bài blog cũ; cần compatibility matrix cho Gradle Wrapper/JDK/plugin version thực tế.

### 5.2. `pluginManagement` khác `repositories`

`pluginManagement { repositories { ... } }` trong **settings.gradle** định nghĩa nơi tìm **plugin marker/artifacts** khi dùng plugins DSL; `repositories { ... }` trong Project định nghĩa nơi resolve **project dependencies**.

Ví dụ settings fragment:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
        google()
    }
}
~~~

Với Android có thể cần Google Maven; với enterprise có thể dùng approved internal mirror. Đừng nghĩ đã thêm `mavenCentral()` vào Project dependencies là chắc chắn plugin resolution được.

### 5.3. `apply false` chỉ resolve/declare, chưa áp plugin vào project

Trong multi-project root build:

~~~groovy
plugins {
    id 'org.jetbrains.kotlin.jvm' version '2.4.21' apply false
}
~~~

Ý nghĩa thường là đưa plugin vào cơ chế resolution/classpath phù hợp mà **không apply** vào root project. Root không tự có `compileKotlin`. Subproject cần:

~~~groovy
plugins {
    id 'org.jetbrains.kotlin.jvm'
}
~~~

Cách khai báo này phụ thuộc Gradle/plugin management setup; không cần dùng cho core Java plugin lab. Đặc biệt với `alias(libs.plugins.example) apply false`, catalog alias **không tự apply plugin**.

### 5.4. Plugin apply scope là theo Project

~~~text
rootProject
  |
  +-- :library (java-library)
  |
  +-- :app (application)
~~~

`:library` và `:app` có plugin sets khác nhau. Việc root biết đến `:app` không tự làm root có `application {}` hay `run`. Một plugin được apply ở `:app` không mặc nhiên apply vào `:library`.

### 5.5. Plugins có thể apply plugins khác

`application` áp Java/Distribution functionality; `java-library` áp Java model. Vì vậy:

- Một plugin có thể là **nguyên nhân gián tiếp** tạo task.
- `plugins.hasPlugin('java')` có thể true dù build script chỉ ghi `id 'application'`.
- Không chỉ đọc một dòng `plugins {}` để suy ra toàn bộ plugin graph.

### 5.6. Plugin order và callbacks

Khi một convention plugin cần cấu hình Java chỉ khi Java plugin đã có, dùng:

~~~groovy
pluginManager.withPlugin('java') {
    tasks.named('compileJava') {
        // Cấu hình Java task khi plugin đã hiện diện.
    }
}
~~~

Đây là **configuration fragment** bên trong Project build logic/convention plugin; không đặt `withPlugin` trong task action. Callback giúp tránh truy cập task/extension quá sớm, nhưng phải review behavior của plugin/Gradle version và không dùng `afterEvaluate` như giải pháp mặc định cho mọi thứ.

---

## 6. Task type và task instance khác nhau

### 6.1. Task type là kiểu, task name là instance

Gradle có API `Task` và nhiều task types. Một plugin có thể dùng `JavaCompile` làm type cho task `compileJava`, dùng `Test` cho task `test`, `Jar` cho `jar`. **Có class type được hỗ trợ** không nghĩa **task với name đó đã được đăng ký**.

Ví dụ `tasks.register('customArchive', Zip)` tự đăng ký một Zip task bằng Gradle task class/API:

~~~groovy
tasks.register('customArchive', Zip) {
    destinationDirectory = layout.buildDirectory.dir('archives')
    archiveFileName = 'custom.zip'
    from('public-files')
}
~~~

**Chỉ là fragment**: `public-files` cần tồn tại nếu bạn muốn archive có contents. Task do bạn đăng ký, không phải `distZip` của Application plugin. Hai task đều có thể dùng Zip technology nhưng nguồn task khác.

### 6.2. `tasks.named` chỉ đúng khi task đã được đăng ký

~~~groovy
tasks.named('compileJava') {
    // Chỉ hợp lệ khi plugin tạo compileJava trong project.
}
~~~

Nếu chưa apply Java-related plugin, đoạn này có thể thất bại ngay trong configuration với unknown task. Hãy apply plugin trước hoặc dùng plugin callback để cấu hình khi task xuất hiện.

### 6.3. `tasks.register` và `tasks.named` giúp configuration avoidance

~~~groovy
def reportTask = tasks.register('makeReport') {
    doLast {
        println 'REPORT_TASK_OK'
    }
}

tasks.register('verifyReport') {
    dependsOn reportTask
    doLast {
        println 'VERIFY_REPORT_OK'
    }
}
~~~

TaskProvider giúp nối dependencies mà không cần `get()` ngay. Với production, tốt hơn khai báo inputs/outputs bằng typed task properties để Gradle incremental build/cache hoạt động đúng. Ví dụ trên chỉ minh họa relationship.

### 6.4. Không dùng `tasks.all` và eager realization tùy tiện

Một plugin eager-configure hàng nghìn tasks có thể làm `help` chậm. Ưu tiên `tasks.register`, `tasks.named`, `tasks.withType(...).configureEach` thay cho pattern eager khi áp dụng được. Lazy configuration là cơ chế Gradle core; plugin tác động trực tiếp tới lượng cấu hình phải xử lý.

---

## 7. Configuration, extension và convention: ba thứ dễ lẫn

### 7.1. Configuration

Configuration tổ chức dependencies/variants; ví dụ Java Library plugin tạo `api`, `implementation`, `compileClasspath`, `runtimeClasspath` theo vai trò declarable/resolvable/consumable. Không tự resolve mọi configuration như nhau; nhiều configurations chỉ dùng khai báo bucket hoặc publication.

### 7.2. Extension

Plugin có thể đăng ký một object trong `ExtensionContainer`. Ví dụ:
- Java plugin đăng ký Java model cho `java {}`.
- Application plugin đăng ký application model cho `application {}`.
- Maven Publish plugin đăng ký publishing model cho `publishing {}`.
- Android Gradle Plugin đăng ký Android model cho `android {}`.
- Kotlin Gradle Plugin đăng ký Kotlin model cho `kotlin {}`.

Không hiểu `java {}` là function built-in trên Gradle base Project. DSL block này được Groovy/Kotlin script accessors biểu diễn **extension được plugin cung cấp**.

### 7.3. Convention

Convention là **giá trị/mẫu mặc định** của plugin, không phải luật vĩnh viễn của engine:
- Java plugin mặc định `src/main/java` và `src/test/java`.
- JAR task theo convention từ Java plugin.
- Application plugin tạo start scripts và distributions.
- Android plugin định nghĩa variant graph theo build types/flavors.
- Kotlin plugin có conventions riêng cho Kotlin source sets/compilation.

Bạn có thể override conventions khi được API cho phép, nhưng phải bảo toàn task inputs/outputs, dependency graphs và configuration-cache compatibility.

### 7.4. `implementation` không phải extension

Trong:

~~~groovy
dependencies {
    implementation project(':library')
}
~~~

`implementation` là một **dependency configuration name** đã được Java model tạo, không phải method mọi Project đều có. Groovy DSL khiến nó trông như method, còn Kotlin DSL sinh type-safe accessors theo plugin model. Cần đọc tài liệu configuration tương ứng, đừng suy diễn từ cú pháp giống nhau.

---

## 8. Lab Java 17: cùng engine, hai plugin sets

Lab có một root Project tạo task bằng core Task API, subproject `:library` dùng core **java-library plugin**, subproject `:app` dùng core **application plugin**. Không cần Kotlin/Android SDK, Maven dependencies hoặc third-party plugin.

### 8.1. Cấu trúc project

~~~text
gradle-capability-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── library/
│   ├── build.gradle
│   └── src/main/java/lab/library/Message.java
└── app/
    ├── build.gradle
    └── src/main/java/lab/app/Main.java
~~~

Gradle Wrapper phải được tạo từ Gradle distribution tin cậy hoặc dùng Wrapper đã được commit từ một project đúng version. Không tự tạo gradle-wrapper.jar. Cần **JDK 17** và Gradle Wrapper tương thích Java 17.

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'gradle-capability-lab'
include 'library', 'app'
~~~

Settings API định nghĩa root và hai subprojects. Nó **không** apply Java plugin cho toàn build.

### 8.3. Root build.gradle — chỉ dùng core Task API

~~~groovy
tasks.register('coreHello') {
    group = 'learning'
    description = 'Task registered by Gradle core Task API'

    doLast {
        println 'CORE_TASK_OK'
    }
}
~~~

**Không có plugins block** trong root. Vẫn có thể đăng ký task vì `TaskContainer` thuộc core Project API. Không suy ra root tự có Java's `compileJava` hoặc Application's `distZip`.

### 8.4. library/build.gradle

~~~groovy
plugins {
    id 'java-library'
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
~~~

`java {}` và `JavaCompile` configuration có nghĩa vì `java-library` áp Java plugin. `java-library` thêm `api`/`implementation` configuration semantics cho Java library consumers.

### 8.5. library/src/main/java/lab/library/Message.java

~~~java
package lab.library;

public final class Message {
    private Message() {
    }

    public static String text() {
        return "LIBRARY_READY";
    }
}
~~~

Java17 class không cần external libraries. `compileJava` của `:library` được plugin tạo, không phải một task đã viết thủ công trong build.gradle.

### 8.6. app/build.gradle

~~~groovy
plugins {
    id 'application'
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
    implementation project(':library')
}

application {
    mainClass = 'lab.app.Main'
}
~~~

- `application` plugin đóng góp `run`, `startScripts`, `distZip` và `application {}`.
- Plugin này áp Java model transitively, nên có `java {}` và `implementation`.
- `implementation project(':library')` dùng Gradle project dependency mechanism cùng configuration do Java plugin model đăng ký.
- Không cần một task shell thủ công để build :library trước :app; Gradle tính task dependencies từ Project dependency.

### 8.7. app/src/main/java/lab/app/Main.java

~~~java
package lab.app;

import lab.library.Message;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
                "PLUGIN_APP_OK: " + Message.text()
        );
    }
}
~~~

### 8.8. Chạy root task

Linux/macOS:

~~~bash
./gradlew :coreHello
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :coreHello
~~~

Dòng stdout **do task in chính xác**:

~~~text
CORE_TASK_OK
~~~

Gradle còn task logs và BUILD SUCCESSFUL. Đây là task tự đăng ký từ core Task API, không cần Java/Application plugin ở root.

### 8.9. Chạy application plugin task

Linux/macOS:

~~~bash
./gradlew :app:run
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:run
~~~

Dòng stdout **do Java main in chính xác**:

~~~text
PLUGIN_APP_OK: LIBRARY_READY
~~~

Điều này chứng minh `:app:run` do application plugin cung cấp và `:library` được build qua project dependency graph.

### 8.10. Build hai modules

~~~bash
./gradlew :library:jar :app:distZip
~~~

`:library:jar` là task từ Java plugin model được `java-library` áp dụng; `:app:distZip` do application/distribution model đóng góp. Gradle sẽ sinh JAR và distribution archive theo plugin conventions.

Kết quả thường có:

~~~text
library/build/libs/library.jar
app/build/distributions/app.zip
~~~

Tên archive thực tế có thể bao gồm project version tùy config; ở lab chưa set version explicit, filename conventions có thể thay theo Gradle version. Không hardcode artifact name cho production nếu cần provenance/versioning.

### 8.11. So danh sách tasks

~~~bash
./gradlew :tasks --all
./gradlew :library:tasks --all
./gradlew :app:tasks --all
~~~

Quan sát:
- Root có `coreHello`, không có `:app:run` như task của root.
- `:library` có `compileJava`, `jar`, `test` và related Java lifecycle tasks.
- `:app` ngoài Java tasks còn có `run`, `startScripts`, `distZip`.
- Root `:tasks --all` có thể hiển thị tasks subprojects tùy CLI/view; dùng **fully qualified task paths** để tránh hiểu nhầm nguồn task.

**Quan trọng:** Khi Java project không có test sources/framework, task `test` có thể `NO-SOURCE` hoặc không chạy tests. Việc có `test` task không chứng minh có một unit test thực sự chạy thành công.

### 8.12. Chạy thử task không tồn tại đúng scope

~~~bash
./gradlew :library:distZip
~~~

Với đúng lab trên, `java-library` không tạo `distZip`, nên lệnh này được kỳ vọng **thất bại do task không tồn tại**. Đây là negative test có chủ đích: source Gradle core API vẫn có thể biết `Zip` type, nhưng `distZip` là task instance do plugin mô hình phân phối tạo.

Không dùng lệnh này trong normal CI success path. Nếu Gradle báo task khác được gợi ý, xem task path cụ thể chứ không giả sử `distZip` là global feature.

### 8.13. Chạy Java độc lập không dùng Gradle

Linux/macOS:

~~~bash
mkdir -p out/lib out/app

javac --release 17 -encoding UTF-8 \
    -d out/lib \
    library/src/main/java/lab/library/Message.java

javac --release 17 -encoding UTF-8 \
    -cp out/lib \
    -d out/app \
    app/src/main/java/lab/app/Main.java

java -cp out/app:out/lib lab.app.Main
~~~

Stdout chính xác:

~~~text
PLUGIN_APP_OK: LIBRARY_READY
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out\lib,out\app | Out-Null

javac --release 17 -encoding UTF-8 -d out\lib library\src\main\java\lab\library\Message.java

javac --release 17 -encoding UTF-8 -cp out\lib -d out\app app\src\main\java\lab\app\Main.java

java -cp "out\app;out\lib" lab.app.Main
~~~

Dùng javac chứng minh Java program hoạt động độc lập. Nó **không tái tạo Gradle source set/task/model**, và không thay thế CI Gradle tests.

---

## 9. Mở rộng lab: custom plugin trong buildSrc

Một Gradle plugin có thể do **team tự tạo** và vẫn dựa trên core APIs. Để chứng minh plugin thực sự **đóng góp task**, tạo optional buildSrc plugin. Phần này là một **bước mở rộng sau khi lab 8 đã chạy**, không cần cho ứng dụng Java hoạt động.

### 9.1. Cây thư mục bổ sung

~~~text
gradle-capability-lab/
└── buildSrc/
    ├── build.gradle
    └── src/main/java/lab/build/GreetingPlugin.java
~~~

BuildSrc là một auxiliary build được Gradle xử lý để đưa build logic lên classpath của main build. Nó có build.gradle riêng; apply `java-gradle-plugin` là dùng **core Gradle plugin dành cho plugin authoring**.

### 9.2. buildSrc/build.gradle

~~~groovy
plugins {
    id 'java-gradle-plugin'
}

gradlePlugin {
    plugins {
        greeting {
            id = 'lab.greeting'
            implementationClass = 'lab.build.GreetingPlugin'
        }
    }
}
~~~

`gradlePlugin {}` không phải global Gradle DSL. Nó xuất hiện vì **java-gradle-plugin**. Khối này định nghĩa **plugin ID** và **implementation class** được đóng gói.

### 9.3. buildSrc/src/main/java/lab/build/GreetingPlugin.java

~~~java
package lab.build;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class GreetingPlugin
        implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        project.getTasks().register(
                "pluginGreeting",
                task -> {
                    task.setGroup("learning");
                    task.setDescription(
                            "Task contributed by the custom plugin"
                    );
                    task.doLast(ignored ->
                            System.out.println("CUSTOM_PLUGIN_OK")
                    );
                }
        );
    }
}
~~~

Mã dùng **Gradle Plugin<Project> API** và `project.getTasks().register`, không cần Kotlin/Android/Spring internals. `@Override apply` được gọi khi plugin apply vào Project; task action chỉ in khi task được thực thi.

### 9.4. Thay root build.gradle để apply custom plugin

Sau khi đã tạo buildSrc files, dùng **toàn bộ** root build.gradle sau (thay cho bản root ở mục 8.3):

~~~groovy
plugins {
    id 'lab.greeting'
}

tasks.register('coreHello') {
    group = 'learning'
    description = 'Task manually registered with Gradle core API'

    doLast {
        println 'CORE_TASK_OK'
    }
}
~~~

Hai tasks nay có **nguồn gốc khác nhau**:
- `coreHello`: chính build.gradle root đăng ký bằng core API.
- `pluginGreeting`: `lab.greeting` plugin đăng ký trong `apply(Project)`.

### 9.5. Chạy kiểm chứng

~~~bash
./gradlew :coreHello :pluginGreeting
~~~

Hai dòng do actions in (Gradle còn task logs):

~~~text
CORE_TASK_OK
CUSTOM_PLUGIN_OK
~~~

**Nếu bạn bỏ `id 'lab.greeting'` khỏi plugins block**, project không có `:pluginGreeting`, dù class GreetingPlugin nằm trong buildSrc. Đây là bằng chứng plugin implementation **có trên build classpath** không đồng nghĩa plugin **đã apply**.

### 9.6. Vì sao buildSrc không phải nơi duy nhất viết plugin?

Có thể dùng:
- `buildSrc` cho build logic cục bộ.
- Included build `build-logic` qua `pluginManagement.includeBuild(...)` cho convention plugins.
- Binary plugin publish ra plugin repository.
- Precompiled script plugin (`.gradle(.kts)`) cho conventions.

Các cách này dùng cùng Gradle plugin model nhưng khác source resolution, compilation, isolation và reuse. Với monorepo lớn, convention plugin trong dedicated included build thường giúp quản lý build logic rõ ràng hơn.

---

## 10. Plugin không chỉ đăng ký task: extension và configuration

Một plugin có thể:
- Đăng ký tasks.
- Tạo `Extension` để exposed DSL.
- Tạo dependency `Configuration`.
- Áp plugin khác.
- Thêm conventions cho file paths, compiler options, source sets.
- Đăng ký artifact variants/attributes.
- Nối task dependencies, inputs/outputs.
- Thêm services/transforms/build lifecycle listeners.

### 10.1. Custom extension ví dụ Java plugin code (fragment)

~~~java
import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class ExampleExtensionPlugin
        implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        project.getExtensions().add(
                "exampleInfo",
                new ExampleInfo("hello")
        );
    }

    public static final class ExampleInfo {
        private final String message;

        public ExampleInfo(String message) {
            this.message = message;
        }

        public String getMessage() {
            return message;
        }
    }
}
~~~

Đây là **code fragment minh họa**, chưa khai plugin ID/descriptor nên không standalone. Nó chứng minh `ExtensionContainer` là API core, còn object `exampleInfo` do plugin thêm vào Project; trước apply không có `exampleInfo` DSL.

Trong production nên dùng Gradle managed objects, `Property<T>` và `ObjectFactory` để hỗ trợ lazy conventions và configuration cache đúng.

### 10.2. Plugin conventions khác public API

Ví dụ Java plugin mặc định code ở `src/main/java`; nhưng `SourceSet` là một domain model do JVM plugin đưa vào. Gradle engine không bắt mọi project phải có thư mục src/main/java; Android/Kotlin/native plugins có layout khác.

### 10.3. Task graph được tạo từ declarations

Khi :app phụ thuộc :library, `compileJava`/classes/jar producer tasks có thể được kết nối theo variant/project dependency. Không cần viết shell `cd library && gradle jar` rồi `cd app && gradle compileJava`. Gradle core graph execution + plugin model cộng lại tạo đúng build behavior.

---

## 11. Source, plugin ID, plugin version và repository là bốn thứ khác nhau

### 11.1. Plugin ID

`java-library` là core plugin ID. `org.jetbrains.kotlin.jvm` là external plugin ID. `lab.greeting` là local custom ID trong lab. Chúng không phải Maven dependency coordinates.

### 11.2. Plugin version

Core plugins được version theo Gradle distribution, không cần `version '...'` ở plugins DSL. External plugins thường cần version qua block, settings pluginManagement, version catalog hoặc plugin resolution strategy.

### 11.3. Plugin repository

Gradle Plugin Portal, Google Maven, Maven Central hoặc internal mirror có thể là nơi resolve plugin marker/artifacts. `repositories` trong Project dùng cho project libraries, không tự đảm bảo plugin resolution.

### 11.4. Dependency coordinates

`org.example:utility:1.0.0` trong `implementation` là library dependency coordinate. Nó không apply Gradle plugin. Plugin marker resolution và project dependency resolution là hai graph có thể dùng repositories khác nhau.

### 11.5. Version catalog aliases không áp plugin tự động

TOML plugin alias:

~~~toml
[plugins]
kotlin-jvm = { id = "org.jetbrains.kotlin.jvm", version = "2.4.21" }
~~~

Đây là **metadata**. Chỉ khi sử dụng:

~~~kotlin
plugins {
    alias(libs.plugins.kotlin.jvm)
}
~~~

trong một Project plugin block phù hợp mới apply plugin. Ngoài ra `apply false` vẫn không apply vào project hiện tại.

**TOML không tự thêm `compileKotlin`, không tự lập source set, không tự sinh `kotlin {}` extension.**

---

## 12. Troubleshooting: đọc lỗi theo đúng lớp

### 12.1. “Could not find method implementation()”

Khả năng:
- Project chưa apply Java/Kotlin/Android plugin có configuration `implementation`.
- Đặt `implementation` ngoài `dependencies {}`.
- Sai project scope/root vs subproject.
- Cú pháp Groovy/Kotlin DSL hoặc dependency configuration khác theo plugin.

Kiểm `plugins {}`, task/dependency configurations và project path, không thêm Maven repository ngẫu nhiên.

### 12.2. “Could not find method android()”

`android {}` là extension do Android Gradle Plugin cung cấp. Kiểm:
- Project `com.android.application` hoặc `com.android.library` được apply?
- AGP version và Gradle/JDK/SDK compatibility?
- Plugin repositories có Google Maven?
- Đang sửa đúng module Android chứ không phải root Java project?

Đừng giả định Gradle core có `android {}`.

### 12.3. “Unresolved reference: kotlin” trong Kotlin DSL

Kotlin DSL script language và Kotlin source plugin khác nhau. Có thể chưa apply KGP, đang ở sai project scope hoặc type-safe DSL accessor chưa được tạo. Kiểm plugin ID, version, source repositories và DSL APIs theo KGP version.

### 12.4. “Task bootJar not found”

Spring Boot plugin/Java plugin interplay chưa được cấu hình; `bootJar` không phải task của Java core plugin. Kiểm plugin ID, version, các điều kiện tạo task, task path và docs phù hợp.

### 12.5. “Task assembleDebug not found”

`assembleDebug` là Android variant task điển hình, không phải Gradle generic. Kiểm Android module, build types/flavors, AGP version, Android SDK và đúng variant. Java-only project không có task này.

### 12.6. “Task shadowJar not found”

Có thể Shadow plugin chưa được apply, ID/version đã thay, project không đúng scope, hoặc plugin không tương thích. Đừng tự tạo task tên shadowJar rồi hy vọng có logic shaded JAR; cần plugin hoặc custom archive implementation đúng.

### 12.7. “Plugin not found” khác “Task not found”

- **Plugin not found**: thất bại ở plugin resolution/apply; kiểm plugin ID/version/repositories, network, marker artifacts.
- **Task not found**: plugin có thể resolved nhưng chưa apply ở Project cần, hoặc version/feature không tạo task.
- **Extension not found**: DSL block chưa tồn tại, sai scope/timing hoặc plugin apply.
- **No matching variant**: variant attributes/capabilities/toolchain/configuration mismatch, không chỉ thiếu repository URL.

---

## 13. Cách khám phá build đang có những khả năng nào

Chạy trong đúng project root:

~~~bash
./gradlew projects
./gradlew :tasks
./gradlew :tasks --all
./gradlew :library:tasks --all
./gradlew :app:tasks --all
./gradlew :app:dependencies
./gradlew :app:properties
~~~

Ý nghĩa:
- `projects` cho cấu trúc build.
- `tasks --all` liệt kê tasks registered/available theo view.
- `dependencies` hiển thị dependency graph/configurations phù hợp.
- `properties` hiển thị project properties (cẩn thận nếu environment có secret).
- `help` giúp xác minh build configuration cơ bản.
- `--dry-run` kiểm task selection/dependency ordering mà không chạy task actions.

**An toàn thông tin:** Không chạy `properties`/`--debug` và chia sẻ log công khai khi build có credentials thật; Gradle diagnostics có thể bao gồm thông tin nhạy cảm tùy plugin.

### 13.1. Fully qualified task paths

Dùng `:app:run`, `:library:jar`, `:coreHello` thay vì task name ngắn khi monorepo có nhiều modules. Lệnh `./gradlew test` có thể match tasks ở nhiều projects theo Gradle task selection semantics; không suy ra tất cả đều đến từ cùng plugin.

### 13.2. Đọc task type, group, description

`tasks --all` thường cho group/description, nhưng không luôn hiển thị plugin ID “đã tạo task”. Muốn xác định nguồn cần đối chiếu applied plugin IDs/Gradle docs và Gradle plugin code, hoặc dùng build diagnostic task nội bộ đã được review.

### 13.3. Đừng kiểm chứng bằng số task đơn giản

Một plugin có thể chỉ tạo tasks khi extension/configuration/variant đúng. Plugin khác có thể tạo nhiều tasks ở module lớn. **Task count** không đo trực tiếp build correctness, performance hoặc plugin compatibility.

---

## 14. Multi-project và convention plugins

### 14.1. Áp plugin ở đâu?

Một team có 100 JVM modules có thể dùng **convention plugin** để thống nhất Java toolchain/test configuration, thay vì copy lặp 100 khối `java {}`. Convention plugin có thể apply Java plugin rồi configure tasks lazily.

Ví dụ precompiled script convention plugin Groovy fragment:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Nếu đặt trong convention build thích hợp, plugin này đóng gói conventions. Đây là **fragment**, không tự chạy ở lab nếu chưa có plugin build setup.

### 14.2. Vì sao không cấu hình bằng `allprojects` bừa bãi?

Eager cross-project configuration làm tăng configuration overhead và giảm tính độc lập của projects, có thể ảnh hưởng configuration cache/isolated projects. Ưu tiên per-project plugins/conventions và lazy `tasks.register`/`configureEach`.

### 14.3. `withPlugin` để tương thích thứ tự apply

Một plugin company có thể chỉ bổ sung Java options khi project áp Java plugin:

~~~groovy
pluginManager.withPlugin('java') {
    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }
}
~~~

Với implementation trong Java binary plugin, dùng `project.getPluginManager().withPlugin("java", applied -> { ... })`, kết hợp Gradle APIs phù hợp. Không cần dùng `afterEvaluate` cho mọi thứ.

### 14.4. Plugin IDs không đồng nghĩa “tính năng toàn hệ thống”

Một convention plugin chỉ ảnh hưởng Projects được apply. Root apply convention plugin không mặc nhiên làm subprojects nhận nó trừ khi code/plugin management cấu hình như vậy. Hãy xác định **phạm vi** từng plugin và task path.

---

## 15. Build lifecycle: plugin code chạy ở giai đoạn nào?

Gradle có ba phase khái niệm:

1. **Initialization:** xử lý settings, xác định build/project structure và plugin management.
2. **Configuration:** đánh giá build scripts, apply plugins, đăng ký/configure tasks, extension/conventions.
3. **Execution:** chạy actions của tasks trong selected task graph.

Khi apply một plugin:

~~~groovy
plugins {
    id 'application'
}
~~~

Gradle phải resolve/load plugin rồi thực thi plugin configuration logic đúng thời điểm, thường ở **configuration phase** cho Project plugin. Nhưng **`run` task không thực thi ngay khi plugin được áp dụng**. Nó chỉ là task được đăng ký; `./gradlew :app:run` mới thực thi action tương ứng.

### 15.1. Hiệu năng: plugin apply cũng có chi phí

Một plugin có thể đăng ký hàng trăm tasks lazily, resolve dependencies quá sớm hoặc thực hiện I/O trong apply. Điều này ảnh hưởng mọi command, kể cả `help`. Gradle core cung cấp configuration avoidance, Providers và Configuration Cache; plugin tác động tới mức tận dụng được chúng.

### 15.2. Configuration Cache compatibility

Custom plugin phải tránh giữ Project/Gradle instances trong task actions serialized khi configuration cache, khai báo inputs/outputs đúng, sử dụng Provider API và Services thích hợp. Một plugin tạo task chạy đúng mà không tương thích Configuration Cache vẫn cần cải thiện nếu team bật cache.

### 15.3. Task API và TestKit

`java-gradle-plugin` core plugin hỗ trợ plugin development và testing. **Gradle TestKit** cho phép thử plugin trên một build fixture thật bằng `GradleRunner` thay vì chỉ unit-test method apply. Khi viết plugin production, nên test:
- Plugin apply có đăng ký task/extension đúng không?
- Task chạy ra output chính xác?
- Missing configuration có diagnostic rõ?
- Gradle Wrapper/JDK/plugin version compatibility?
- Configuration Cache và incremental outputs?
- Build failure có propagated?

---

## 16. So sánh ba cách viết cùng một khả năng

### 16.1. Script tự đăng ký task bằng Gradle API

~~~groovy
tasks.register('generateReport') {
    doLast {
        println 'REPORT_OK'
    }
}
~~~

Đây là project-local logic, không cần plugin domain cụ thể. Dùng cho tác vụ đơn giản.

### 16.2. Core plugin cung cấp task domain

~~~groovy
plugins {
    id 'java-library'
}
~~~

Plugin đăng ký `compileJava`, `jar`, `test`, configurations và sourceSet conventions. Bạn không phải tự viết compiler invocation và task dependency graph.

### 16.3. Custom/external plugin cung cấp task domain

~~~groovy
plugins {
    id 'lab.greeting'
}
~~~

Với `buildSrc` plugin đã định nghĩa ở lab 9, ID này tạo `pluginGreeting`. Plugin có thể được tái sử dụng và versioned, không cần copy source Java plugin implementation vào từng build.gradle.

### 16.4. Khi nào chọn cách nào?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Một task nhỏ đặc thù project | `tasks.register` trực tiếp |
| Java library | Core `java-library` plugin |
| Java command-line application | Core `application` plugin |
| Maven publication | Core `maven-publish` plugin |
| Kotlin JVM compilation | Kotlin Gradle Plugin |
| Android variants/APK/AAB | Android Gradle Plugin |
| Spring Boot executable archive | Spring Boot Gradle Plugin |
| Quy ước chung nhiều modules | Convention plugin |
| Reusable build integration tổ chức | Binary plugin |

Đừng viết lại một plugin domain lớn bằng nhiều `Exec` tasks nếu đã có plugin uy tín có model inputs/outputs, variants và caching phù hợp. Nhưng cũng đừng áp plugin ngoài chỉ để tạo một dòng println; hãy cân nhắc scope, bảo trì và trust.

---

## 17. Bảo mật và khả năng tương thích plugin

### 17.1. Plugins là executable build code

External plugin có thể đọc filesystem/network và CI secrets theo quyền build process. Cần:
- Tin nguồn plugin.
- Pin versions/checksums và plugin repositories.
- Review permissions/trust boundary.
- Không cấp production signing keys cho untrusted PR build logic.
- Sử dụng dependency verification và repository policy phù hợp.
- Test plugin upgrades trước khi release.

### 17.2. Gradle plugin ABI/API compatibility

Một plugin build cho Gradle version khác có thể gọi API deprecated/removed. Compatibility cần xem:
- Gradle Wrapper version.
- JDK chạy Gradle.
- Java toolchains.
- Kotlin Gradle Plugin version.
- Android Gradle Plugin version và Android SDK.
- Spring Boot plugin version.
- Included build/convention plugin APIs.

**Lỗi “No such method” không luôn do thiếu plugin**: có thể API đã đổi giữa versions hoặc DSL đang sai scope.

### 17.3. Nâng cấp từng lớp

Khi đổi Gradle version/plugin version:
1. Chụp baseline tasks/plugins.
2. Pin Wrapper distribution/checksum.
3. Kiểm compatibility matrix.
4. Nâng một biến có kiểm soát.
5. Chạy tests, packaging và reports.
6. Kiểm task names/extension model thay đổi.
7. Đo configuration/task performance.
8. Review deprecations, warnings và Configuration Cache.

---

## 18. Bẫy phổ biến

| Nhầm lẫn | Sửa cách hiểu |
| --- | --- |
| Gradle biết Task API nên có `compileJava` mọi nơi | Java plugin đăng ký compileJava ở project áp dụng |
| `java-library` là Gradle API cốt lõi | Đây là core **plugin**, khác core API |
| Kotlin DSL nghĩa là compile Kotlin code | DSL script language khác Kotlin JVM plugin |
| `implementation` là method global | Configuration do JVM/Android plugin tạo |
| `api` dependency configuration = Gradle API | Hai nghĩa khác nhau |
| `android {}` là Gradle builtin | Do AGP tạo |
| `assembleDebug` là Gradle core task | Android variant task |
| Có Spring dependency thì có bootJar | Boot plugin cần apply/configure |
| `maven-publish` là external vì publish Maven | Đây là core plugin bundled, nhưng phải apply |
| Có plugin artifact trong classpath tức task đã được tạo | Plugin phải apply vào đúng Project |
| `apply false` nghĩa plugin đã hoạt động | Chưa apply vào project hiện tại |
| `alias(libs.plugins.foo)` trong TOML tự apply | Phải dùng alias trong plugins block |
| `repositories` luôn giải quyết plugin resolution | settings pluginManagement.repositories khác |
| Một root Project có `run` vì :app có `run` | Task scope theo Project |
| `tasks.register` chạy action ngay | Registration ở configuration, action ở execution |
| `tasks.named('x')` tạo task x | Nó tìm task đã đăng ký |
| KGP/AGP/Spring mọi version tạo cùng task names | Tasks có thể khác theo plugin/version/variants |
| Một plugin tạo nhiều tasks nên build phải chậm | Lazy registration; đo phase/timeline trước |
| Task `test` hiện diện chứng minh tests đã chạy | Có thể NO-SOURCE, UP-TO-DATE hoặc không có tests |
| Plugin version catalog quyết định selected dependency version | Plugin/dependency graphs có semantics riêng |
| `compileJava` là một Java CLI command do Gradle tự gọi thủ công | Là task/plugin model với inputs/classpath/toolchain |
| Project có `Zip` type nên mặc định có distZip | Type có thể tồn tại, task instance do plugin đăng ký |

---

## 19. Bài tập có đáp án

### Bài 1. `tasks.register('hello')` thuộc loại nào?

**Đáp án:** Dùng core `TaskContainer` API; task hello do build author đăng ký, không do Java plugin.

### Bài 2. `java { toolchain { ... } }` là Gradle global method?

**Đáp án:** Không. `java` extension được Java-related plugin tạo.

### Bài 3. Gradle core API và Gradle core plugin có giống nhau?

**Đáp án:** Không. API là engine/interface; core plugin là plugin bundled cần apply đúng project.

### Bài 4. `plugins { id 'java-library' }` cần version không?

**Đáp án:** Không, core plugin đi kèm Gradle distribution và version theo Wrapper.

### Bài 5. `implementation` xuất hiện trước khi apply Java plugin?

**Đáp án:** Không được giả định. Configuration này do plugin domain thích hợp tạo.

### Bài 6. `api` dependency configuration nghĩa Gradle API?

**Đáp án:** Không. `api` là configuration của Java Library plugin.

### Bài 7. `build.gradle.kts` có tự tạo compileKotlin?

**Đáp án:** Không. Kotlin DSL là ngôn ngữ script; compileKotlin do Kotlin Gradle Plugin.

### Bài 8. `android {}` đến từ đâu?

**Đáp án:** Android Gradle Plugin.

### Bài 9. `assembleDebug` là một task Java project có sẵn?

**Đáp án:** Không. Nó thuộc Android variant/task model khi AGP có variant phù hợp.

### Bài 10. `bootJar` do plugin nào?

**Đáp án:** Spring Boot Gradle Plugin với Java-related integration thích hợp.

### Bài 11. `distZip` trong lab đến từ đâu?

**Đáp án:** Application plugin, qua distribution model áp dụng vào :app.

### Bài 12. Vì sao :library:distZip fail?

**Đáp án:** java-library không tạo distribution task đó. Task type Zip có sẵn không đồng nghĩa distZip instance tồn tại.

### Bài 13. Root `coreHello` có cần Java plugin?

**Đáp án:** Không. Root đăng ký bằng core API.

### Bài 14. `:app:run` in gì?

**Đáp án:** Dòng Java output `PLUGIN_APP_OK: LIBRARY_READY`.

### Bài 15. `:coreHello` in gì?

**Đáp án:** `CORE_TASK_OK`.

### Bài 16. Custom plugin lab apply rồi có task nào?

**Đáp án:** `:pluginGreeting`, in `CUSTOM_PLUGIN_OK`.

### Bài 17. Bỏ `id 'lab.greeting'` nhưng giữ buildSrc JAR, task còn không?

**Đáp án:** Không, plugin code tồn tại trên classpath không tự áp plugin.

### Bài 18. Plugin ID và Maven dependency coordinate có giống nhau?

**Đáp án:** Không. Plugin ID dùng plugin resolution/apply; library coordinate dùng dependency graph.

### Bài 19. `pluginManagement.repositories` để làm gì?

**Đáp án:** Quy định nơi resolve plugin marker/artifacts cho plugins DSL.

### Bài 20. `repositories { mavenCentral() }` trong Project luôn resolve plugins?

**Đáp án:** Không. Nó chủ yếu dùng project dependencies; plugin resolution có settings pluginManagement.

### Bài 21. `apply false` có tạo task compileKotlin ở root?

**Đáp án:** Không.

### Bài 22. `TaskProvider` có lợi gì?

**Đáp án:** Lazy registration/configuration và wiring dependencies không cần eagerly realize tasks.

### Bài 23. `tasks.named` có tự tạo task?

**Đáp án:** Không, chỉ lookup/configure task đã registered.

### Bài 24. Java application có cùng model Android application?

**Đáp án:** Không. Application plugin tạo JVM distribution, AGP tạo Android variants/APK/AAB model.

### Bài 25. Plugin có thể apply plugin khác không?

**Đáp án:** Có. Application plugin áp Java/Distribution functionality, java-library áp Java model.

### Bài 26. `java-gradle-plugin` có phải external?

**Đáp án:** Không. Đây là Gradle core plugin để xây plugin, có trong distribution.

### Bài 27. `gradlePlugin {}` có xuất hiện toàn cục?

**Đáp án:** Không, được plugin authoring tạo khi apply java-gradle-plugin.

### Bài 28. Plugin scope trong multi-project?

**Đáp án:** Scope theo từng Project/Settings/Gradle tùy plugin; root apply không tự apply vào mọi subproject.

### Bài 29. `test` task xuất hiện chứng minh có test cases?

**Đáp án:** Không. Có thể NO-SOURCE, skip hoặc không có framework/cases.

### Bài 30. Vì sao không dùng `afterEvaluate` để chữa mọi lỗi task missing?

**Đáp án:** Nó tạo coupling về lifecycle/timing; thường nên apply đúng plugin, dùng `withPlugin`, `tasks.named`, Provider API.

### Bài 31. Plugin ID trong version catalog đã apply?

**Đáp án:** Chưa; cần dùng alias trong `plugins {}` tại Project cụ thể.

### Bài 32. Một plugin được tải từ Portal có an toàn tuyệt đối?

**Đáp án:** Không. Plugin chạy executable build code; cần tin nguồn, pin versions và giới hạn CI secrets.

### Bài 33. Nếu lỗi Kotlin plugin compatibility?

**Đáp án:** Đối chiếu Kotlin Gradle Plugin, Gradle Wrapper, JDK và target versions; không chỉ sửa syntax tùy ý.

### Bài 34. Task names có được giữ ổn định qua mọi AGP version?

**Đáp án:** Không; còn phụ thuộc build variants và plugin APIs.

### Bài 35. Kotlin DSL compile Java được không?

**Đáp án:** Có nếu project apply Java plugin; DSL build script language độc lập với source programming language.

### Bài 36. Tại sao phải phân biệt `JavaCompile` class và `compileJava` task?

**Đáp án:** Class/type có sẵn không quyết định task instance đã được đăng ký vào đúng Project.

---

## 20. Checklist khi đọc một Gradle project lạ

- [ ] Đã xác định root Settings và tất cả included projects?
- [ ] Đã phân biệt root build.gradle với subproject build.gradle?
- [ ] Đã ghi plugin IDs được apply trực tiếp và transitively?
- [ ] Đã phân loại core plugin, external plugin và custom plugin?
- [ ] Đã kiểm plugin version và repository nơi resolve?
- [ ] Đã xác minh Gradle Wrapper, JDK và plugin compatibility?
- [ ] Không nhầm Kotlin DSL với Kotlin compilation plugin?
- [ ] Không nhầm Java Plugin với core Gradle Task API?
- [ ] Không nhầm dependency library với Gradle plugin?
- [ ] Đã xem sourceSets, configurations và extensions do plugin tạo?
- [ ] Đã xác định `implementation`, `api` và classpath semantics đúng plugin?
- [ ] Đã kiểm `tasks --all` và fully qualified task paths?
- [ ] Có biết task nào do project author tự `tasks.register`?
- [ ] Có biết task nào do plugin apply đăng ký?
- [ ] Có phân biệt task type với task instance?
- [ ] Đã kiểm plugin callbacks thay vì gọi `tasks.named` quá sớm?
- [ ] Không dùng `afterEvaluate` không cần thiết?
- [ ] Đã hiểu `apply false` và version catalog aliases?
- [ ] Đã phân biệt pluginManagement.repositories với Project repositories?
- [ ] Android tasks/DSL không bị áp vào Java-only project?
- [ ] Spring Boot packaging không bị nhầm với Java JAR?
- [ ] Test task tồn tại đã được kiểm thực sự chạy tests?
- [ ] Có dùng Provider/TaskProvider và lazy configuration phù hợp?
- [ ] Build plugins được kiểm nguồn, version, secrets access và security?
- [ ] Có kiểm Configuration Cache và task inputs/outputs khi phát triển custom plugin?
- [ ] CI gọi đúng tasks trong đúng modules/variants?
- [ ] Có tài liệu rõ task ownership, plugin boundaries và lifecycle?

## Tài liệu tham khảo

- [Gradle — Plugin Basics](https://docs.gradle.org/current/userguide/plugin_basics.html): core infrastructure vs plugin-contributed tasks/configurations/DSL.
- [Gradle — Introduction to Plugins](https://docs.gradle.org/current/userguide/plugins.html): core/community/local plugins và plugin scopes.
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): applying plugins và đóng góp domain objects.
- [Gradle — Plugin Reference](https://docs.gradle.org/current/userguide/plugin_reference.html): danh mục core plugins.
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization/configuration/execution.
- [Gradle — Build File Basics](https://docs.gradle.org/current/userguide/build_file_basics.html): plugins, dependencies, DSL.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api/implementation configurations.
- [Gradle — Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): source sets, compileJava, test, jar.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): run, startScripts, distZip.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): Test tasks và framework integration.
- [Gradle — Custom Plugins](https://docs.gradle.org/current/userguide/custom_plugins.html): Plugin<Project>, buildSrc và plugin implementation.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): TaskProvider, tasks.register/configureEach.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): plugin compatibility.
- [Kotlin — Configure a Gradle Project](https://kotlinlang.org/docs/gradle-configure-project.html): Kotlin Gradle Plugin và compileKotlin.
- [Android — Configure your build](https://developer.android.com/build): Android Gradle Plugin và build variants.
- [Spring Boot — Gradle Plugin](https://docs.spring.io/spring-boot/gradle-plugin/): Boot plugin tasks/packaging.

**Kết luận:** Gradle core cung cấp **engine và API để mô tả build**; **core plugins** là các plugin đã có sẵn trong Gradle distribution, còn **external/custom plugins** bổ sung mô hình của từng hệ sinh thái. `tasks.register` có thể dùng với core Project API, nhưng `compileJava`, `application {}`, `android {}`, `compileKotlin`, `bootJar`, `shadowJar` chỉ có khi plugin tương ứng đã áp dụng vào **đúng Project** và đáp ứng version/configuration conditions. Đọc đúng nguồn gốc của task, extension và configuration giúp bạn sửa lỗi nhanh, viết build logic tái sử dụng, giảm coupling và bảo đảm build đúng trên mọi môi trường.
