# Phối hợp plugin bằng pluginManager.withPlugin trong phát triển Gradle plugin

## 1. Tại sao một plugin cần phối hợp với plugin khác?

Trong một hệ thống Gradle nhiều module, nhóm phát triển có thể viết plugin nội bộ để chuẩn hóa công cụ biên dịch, testing và cách chạy ứng dụng. Một plugin như vậy không nhất thiết muốn biến mọi project thành Java project.

Ví dụ một plugin `demo.plugin-coordination` có ba chính sách:

- **Khi Java plugin xuất hiện:** đặt Java toolchain 17, encoding UTF-8 và cấu hình Gradle Test tasks chạy JUnit Platform.
- **Khi Application plugin xuất hiện:** bổ sung JVM system property `demo.mode=coordinated` cho task `run`.
- **Khi Java/Application không xuất hiện:** không tự tạo `compileJava`, `test` hay `run`, chỉ cung cấp task `coordinationReport` để báo những plugin đã được phát hiện.

Plugin cũng phải chạy đúng nếu người dùng viết:

~~~groovy
plugins {
    id 'demo.plugin-coordination'
    id 'java-library'
}
~~~

hoặc đảo thành:

~~~groovy
plugins {
    id 'java-library'
    id 'demo.plugin-coordination'
}
~~~

Khi có cả hai cách khai báo, một câu kiểm tra tức thời `hasPlugin('java')` là không đủ. Giải pháp là **`PluginManager.withPlugin`**: đăng ký hành động **ngay sau khi một plugin cụ thể đã được áp dụng**, bất kể plugin đến trước hay sau.

Bài thuộc chủ đề **Phát triển plugin** của **Build Tool Gradle**, đề bài **Phối hợp plugin bằng pluginManager.withPlugin**. Nội dung dùng Gradle Groovy DSL, một binary plugin viết bằng Groovy, Java 17, JUnit Jupiter và Gradle TestKit. Có project đầy đủ để kiểm thử ba trường hợp thứ tự áp dụng: **before**, **after**, **absent**.

### 1.1. Kết quả học tập

Sau bài học, bạn sẽ:

1. Hiểu chính xác lúc nào callback `withPlugin` thực thi.
2. Phân biệt `withPlugin`, `apply`, `hasPlugin`, `findPlugin`, `plugins.withId` và `afterEvaluate`.
3. Cấu hình extension/task chỉ khi model do plugin khác tạo đã có.
4. Kết hợp `withPlugin` với `tasks.register`, `tasks.named` và `configureEach` để tránh eager task configuration.
5. Dùng `JavaPluginExtension`, `JavaCompile`, `Test` và `JavaExec` đúng kiểu.
6. Nhận biết giới hạn classpath, API compatibility và plugin ID của plugin bên ngoài.
7. Viết plugin trong included build `build-logic` và thử bằng ba modules Java/Application/plain.
8. Tạo Gradle TestKit tests bảo đảm plugin chạy đúng với nhiều thứ tự áp dụng.
9. Phân biệt configuration-time callback với task action và Configuration Cache.
10. Tự chẩn đoán lỗi plugin chưa có, task chưa đăng ký, toolchain/JUnit thiếu và callback đọc cấu hình quá sớm.

**Điều kiện để chạy demo:** Gradle Wrapper hợp lệ, bản Gradle tương thích Java 17, JDK 17 tìm được qua toolchain hoặc provisioning, kết nối Maven Central khi JUnit dependencies chưa có trong cache. Các lệnh `./gradlew` dùng trên Linux/macOS; Windows PowerShell dùng `.\gradlew.bat`.

## 2. Contract chính xác của PluginManager.withPlugin

Java API công khai:

~~~java
void withPlugin(
    String pluginId,
    Action<? super AppliedPlugin> action
);
~~~

Các tình huống:

| Trạng thái plugin khi gọi `withPlugin` | Hành vi |
| --- | --- |
| Plugin **đã được áp dụng** | Callback được thực hiện **ngay lập tức** |
| Plugin **chưa được áp dụng**, sau đó có plugin ấy | Callback được thực hiện **ngay sau** khi plugin được áp dụng |
| Plugin **không bao giờ được áp dụng** | Callback **không chạy** |
| Plugin ID không có trong classpath/plugin resolution, cũng không được apply | Không có việc resolve tự động; callback chỉ được đăng ký chờ |
| Plugin áp dụng vào một **project khác** | Callback của project hiện tại không chạy bởi sự kiện của project khác |

Ví dụ ngắn:

~~~groovy
project.pluginManager.withPlugin('java') { applied ->
    project.logger.lifecycle(
        'Detected plugin: ' + applied.id
    )
}
~~~

Đây là **trích đoạn Gradle plugin/configuration logic**, không phải một Java application. Tham số `applied` là `AppliedPlugin`, cung cấp metadata như `id`; nó không phải instance `JavaPluginExtension` hoặc `JavaCompile`.

### 2.1. “Sau khi áp dụng plugin” nghĩa là gì?

Khi callback thực thi, Gradle đã thực hiện thao tác **apply plugin** được theo dõi. Những extensions, configurations và task registrations do plugin đó tạo trong quá trình apply thông thường đã sẵn trong model.

**Nhưng:** điều đó **không có nghĩa project đã hoàn tất evaluation** hoặc người dùng đã cấu hình mọi property ở phía dưới `build.gradle`.

Ví dụ:

~~~groovy
plugins {
    id 'application'
    id 'demo.plugin-coordination'
}

application {
    mainClass = 'demo.app.Main'
}
~~~

Callback `withPlugin('application')` của custom plugin có thể chạy **trước** khi dòng `mainClass = ...` trong `application { }` được đánh giá. Do vậy nên **cấu hình task lazy**, không gọi `application.mainClass.get()` tức thì chỉ để lấy giá trị final.

### 2.2. Nếu custom plugin đến trước Java

~~~text
1. Gradle áp dụng demo.plugin-coordination
                   |
                   v
2. Plugin đăng ký withPlugin("java")
                   |
                   v
3. java chưa có -> callback được lưu
                   |
                   v
4. java-library được áp dụng
                   |
                   v
5. java-library đưa Java plugin vào project
                   |
                   v
6. Java plugin hoàn tất apply
                   |
                   v
7. Callback chạy, cấu hình Java extension/tasks
~~~

Nếu custom plugin không tự áp Java, project không dùng Java vẫn không bị can thiệp.

### 2.3. Nếu Java đến trước custom plugin

~~~text
1. Gradle áp dụng application
                   |
                   v
2. Application áp dụng Java plugin
                   |
                   v
3. Các plugins được áp dụng xong
                   |
                   v
4. Gradle áp dụng demo.plugin-coordination
                   |
                   v
5. withPlugin("java") -> chạy NGAY
                   |
                   v
6. withPlugin("application") -> chạy NGAY
~~~

Lưu ý Application plugin bao gồm khả năng Java, nên custom plugin nhận được **cả hai** callbacks. Đây là kết hợp tùy chọn, không phải hai lần chạy cùng một callback.

### 2.4. Listener gắn với đúng Project

Trong một class implements `Plugin<Project>`:

~~~groovy
void apply(Project project) {
    project.pluginManager.withPlugin('java') {
        // Theo dõi Java plugin của project này.
    }
}
~~~

Không đăng ký callback trên `project.rootProject.pluginManager` khi muốn theo dõi plugin của `:lib` hoặc `:app`. Root, library và application có model/plugin managers riêng. Việc áp `java` vào `:lib` không tự làm callback đã đăng ký trên root project chạy.

### 2.5. Một plugin được áp dụng sau callback không đồng nghĩa task phải chạy

`withPlugin` hoạt động trong **configuration**. Nó có thể đặt task properties, đăng ký providers và khai mô hình. Nó **không tự thực thi** `compileJava`, `test` hoặc `run`. Tasks chỉ được thực thi khi nằm trong selected task graph, sau khi Gradle lập kế hoạch.

Đừng đánh đồng “callback chạy” với “task action chạy”. Cũng đừng chờ callback sẽ in log trong mọi invocation: với Configuration Cache hit, Gradle có thể reuse state mà không đánh giá lại toàn bộ plugin configuration.

## 3. Chọn API phù hợp: với, apply, kiểm tra snapshot

| API | Vai trò | Khi Java chưa có |
| --- | --- | --- |
| `pluginManager.withPlugin('java') { ... }` | Listener có điều kiện, không ép áp plugin | Chờ Java được apply |
| `pluginManager.apply('java')` | Áp dụng plugin bằng ID | Chủ động áp Java |
| `pluginManager.hasPlugin('java')` | Boolean **ngay tại thời điểm hỏi** | `false` |
| `pluginManager.findPlugin('java')` | Trả `AppliedPlugin` khi đã apply | `null` |
| `plugins.withId('java') { ... }` | Listener qua `PluginContainer`, callback nhận `Plugin` | Chờ plugin |
| `afterEvaluate { ... }` | Callback khi project evaluation xong | Không phải plugin-specific listener |

### 3.1. Khi nào `apply` tốt hơn?

Nếu một custom plugin **chỉ dành cho Java** và không có ý nghĩa khi Java vắng mặt, việc áp Java có thể là một phần hợp đồng:

~~~groovy
class JavaRequiredPlugin implements Plugin<Project> {
    void apply(Project project) {
        project.pluginManager.apply('java')

        project.extensions.configure(JavaPluginExtension) {
            JavaPluginExtension ext ->
                ext.toolchain.languageVersion.set(
                    JavaLanguageVersion.of(17)
                )
        }
    }
}
~~~

Đây chỉ là **đoạn minh họa class**; file compile thực tế cần package/imports/plugin project. Vì `apply('java')` là bắt buộc, không nhất thiết dùng `withPlugin` chỉ để chờ Java.

Ngược lại, plugin phối hợp của bài này **có thể dùng mà không có Java**, nên không chủ động áp Java.

### 3.2. Vì sao `hasPlugin` một lần dễ phụ thuộc thứ tự?

Anti-pattern:

~~~groovy
class FragileCoordinationPlugin implements Plugin<Project> {
    void apply(Project project) {
        if (project.pluginManager.hasPlugin('java')) {
            project.tasks.withType(JavaCompile).configureEach {
                options.encoding = 'UTF-8'
            }
        }
    }
}
~~~

Nếu custom plugin được áp dụng **trước** Java, `hasPlugin` false và nhánh cấu hình không bao giờ được thêm. Khi đảo thứ tự plugins, nó có thể thành true, tạo hành vi không ổn định.

Thay bằng:

~~~groovy
class SafeCoordinationPlugin implements Plugin<Project> {
    void apply(Project project) {
        project.pluginManager.withPlugin('java') {
            project.tasks.withType(JavaCompile).configureEach {
                options.encoding = 'UTF-8'
            }
        }
    }
}
~~~

Hai class ở trên chỉ dùng để **so sánh semantics**, không phải code demo cần tạo trong project chính.

### 3.3. Phân biệt `plugins.withId` và `withPlugin`

Hai API đều quan sát plugin ID và có thể gọi callback khi plugin đã có hoặc được apply về sau. Khác biệt ở **loại đối tượng callback**:

- `PluginManager.withPlugin`: callback nhận `AppliedPlugin` (metadata về plugin đã apply).
- `PluginContainer.withId`: callback nhận `Plugin` instance.

Trong bài này, plugin chỉ cần biết **thời điểm plugin capability có mặt** để cấu hình extension/tasks, nên `project.pluginManager.withPlugin` diễn đạt đúng ý hơn.

Không assume `applied` là instance của `JavaPlugin` hoặc cố gọi `applied.java { }`. Đối với Java extension, dùng `project.extensions.configure(JavaPluginExtension)`.

### 3.4. Vì sao không dùng `afterEvaluate` để chữa ordering?

Một đoạn như:

~~~groovy
project.afterEvaluate {
    if (project.pluginManager.hasPlugin('java')) {
        project.tasks.named('compileJava') {
            options.encoding = 'UTF-8'
        }
    }
}
~~~

không diễn tả chính xác điều kiện cần: **Java được apply**. Nó chờ cuối evaluation không cần thiết, dễ phụ thuộc thứ tự callbacks và gây bất lợi cho task configuration avoidance.

`withPlugin` kết hợp `tasks.withType(...).configureEach`/`tasks.named(...).configure` thường rõ và ổn định hơn. Chỉ dùng các lifecycle hooks khác khi có yêu cầu khác thật sự, hiểu Gradle version và test đầy đủ.

## 4. Phối hợp Java và Application một cách có chủ đích

Custom plugin sẽ đăng ký **hai listeners độc lập**:

~~~groovy
project.pluginManager.withPlugin('java') {
    // Cấu hình Java-specific conventions.
}

project.pluginManager.withPlugin('application') {
    // Cấu hình application-specific conventions.
}
~~~

Vì Application plugin áp dụng Java plugin, một Application project sẽ thỏa **cả hai điều kiện**. Một Java Library project chỉ thỏa `java`. Một project chỉ dùng custom plugin sẽ không thỏa điều kiện nào.

### 4.1. Chọn đúng plugin ID

| Bạn cần | Listener ID nên dùng | Tại sao |
| --- | --- | --- |
| Quy ước compile/test của mọi Java projects | `java` | Cả Java Library và Application có Java plugin |
| Quy ước riêng Java Library API variants | `java-library` | Không ép Application project có library model |
| Cấu hình task `run` | `application` | Task `run` được Application plugin cung cấp |
| Quy ước liên quan Java Base nhưng không yêu cầu source sets | `java-base` khi phù hợp | Phải kiểm chính xác model tồn tại ở level này |
| Tích hợp một external plugin | ID đầy đủ của vendor | Đúng capability theo hợp đồng plugin đó |

Đừng lắng nghe `java-library` nếu bạn muốn cùng chính sách cho `application`. Ngược lại, không mặc định mọi JVM plugin đều apply `java`; plugin như `java-base` có phạm vi khác.

### 4.2. Task configuration avoidance vẫn cần thiết

`withPlugin` giải quyết **thời điểm plugin khả dụng**; nó không tự làm các task configuration lazy.

Bên trong listener Java, nên viết:

~~~groovy
project.pluginManager.withPlugin('java') {
    project.tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }
}
~~~

`configureEach` áp dụng cấu hình cho JavaCompile tasks khi chúng được cấu hình, kể cả tasks đăng ký sau. Không realize toàn bộ JavaCompile tasks chỉ để set encoding.

Với Application:

~~~groovy
project.pluginManager.withPlugin('application') {
    project.tasks.named('run', JavaExec).configure {
        systemProperty('demo.mode', 'coordinated')
    }
}
~~~

`tasks.named('run', JavaExec)` là hợp lý **sau** Application plugin, bởi task `run` đã được plugin này đăng ký. Nếu làm tương tự trong project chỉ có `java-library`, Gradle sẽ báo task tên `run` không tồn tại.

### 4.3. Không lạm dụng `dependsOn`

`withPlugin('java')` không tự đặt:

~~~groovy
tasks.named('compileJava') {
    dependsOn(tasks.named('test'))
}
~~~

Đoạn này là **anti-pattern**: compiler chính không cần chạy tests trước khi compile, có thể tạo task dependency cycle trong Java graph. Nếu muốn CI chạy tests, chọn `check`/`build` hoặc các verification tasks phù hợp. Plugin coordination là **cấu hình model**, không mặc định là ép mọi task chạy theo thứ tự tùy ý.

### 4.4. Callback được chạy sau apply, nhưng user config có thể đến sau

Trong build file:

~~~groovy
plugins {
    id 'java-library'
    id 'demo.plugin-coordination'
}

java {
    withSourcesJar()
}
~~~

Plugin callback có thể chạy trước `java.withSourcesJar()` trong consumer build script. Nếu cần một default cho property, dùng `Property.convention(...)`. Nếu muốn ép policy, `set(...)` có chủ đích; nếu phải đọc giá trị final do user cấu hình, dùng lazy Provider/wiring thay vì `get()` quá sớm.

`withPlugin` không tự quyết định **precedence** giữa những plugins cùng set một property. Nếu plugin A set Java 21 còn plugin B set Java 17, kết quả có thể phụ thuộc thứ tự hoặc bị từ chối nếu property đã finalize. Cần thống nhất policy owner và kiểm bằng functional tests.

## 5. Cấu trúc project demo đầy đủ

Ta xây một binary plugin Groovy trong included build `build-logic`. Plugin này được dùng trong ba subprojects:

~~~text
with-plugin-lab/
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/
│       ├── main/groovy/demo/buildlogic/
│       │   ├── CoordinationPlugin.groovy
│       │   └── CoordinationReportTask.groovy
│       └── test/java/demo/buildlogic/
│           └── CoordinationPluginTest.java
├── lib/
│   ├── build.gradle
│   └── src/
│       ├── main/java/demo/lib/Greeting.java
│       └── test/java/demo/lib/GreetingTest.java
├── app/
│   ├── build.gradle
│   └── src/
│       ├── main/java/demo/app/Main.java
│       └── test/java/demo/app/MainTest.java
└── plain/
    └── build.gradle
~~~

**Gradle Wrapper:** cần sinh bốn file thực bằng Gradle Wrapper, không tự tạo file rỗng. Có thể chạy lệnh `gradle wrapper` từ project root bằng một Gradle distribution đã cài phù hợp, sau đó commit `gradlew`, `gradlew.bat` và `gradle/wrapper`.

Các phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `build-logic` | Plugin implementation, task type và Gradle TestKit tests |
| `:lib` | Custom plugin được áp **trước** Java Library |
| `:app` | Application được áp **trước** custom plugin |
| `:plain` | Chỉ custom plugin, không Java/Application |
| `CoordinationReportTask` | Typed task in trạng thái callbacks |
| `Greeting` | Java 17 library class |
| `Main` | Java 17 application main class, in system property được Application callback gán |

### 5.1. Root `settings.gradle`

~~~groovy
pluginManagement {
    includeBuild('build-logic')

    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'with-plugin-lab'

include 'lib', 'app', 'plain'
~~~

`pluginManagement.includeBuild('build-logic')` cho phép root build resolve plugin ID `demo.plugin-coordination` từ included build, không cần publish plugin lên remote repository.

Không nhầm `build-logic` với subproject `:build-logic`. Nó là **một Gradle build riêng**. Vì vậy để chạy test của build-logic từ root, có thể dùng `./gradlew -p build-logic test`; không giả định có root subproject task `:build-logic:test`.

### 5.2. `build-logic/settings.gradle`

~~~groovy
rootProject.name = 'build-logic'
~~~

### 5.3. `build-logic/build.gradle`

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}

gradlePlugin {
    plugins {
        coordination {
            id = 'demo.plugin-coordination'
            implementationClass = 'demo.buildlogic.CoordinationPlugin'
        }
    }
}

dependencies {
    testImplementation gradleTestKit()
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

`groovy-gradle-plugin` cho phép triển khai Gradle plugin bằng Groovy và mang theo khả năng Gradle Plugin Development Plugin. `gradlePlugin { ... }` đăng ký plugin ID/implementation class để root build và TestKit fixture dùng qua `plugins { id 'demo.plugin-coordination' }`.

`gradleTestKit()` là test dependency của build-logic project. JUnit Jupiter/Platform Launcher thuộc **tests của plugin project**; chúng không tự chuyển thành dependencies của Java application `:app`.

## 6. Task có typed inputs để kiểm callback mà không truy cập Project lúc execution

File `build-logic/src/main/groovy/demo/buildlogic/CoordinationReportTask.groovy`:

~~~groovy
package demo.buildlogic

import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class CoordinationReportTask extends DefaultTask {
    @Input
    abstract Property<Boolean> getJavaDetected()

    @Input
    abstract Property<Boolean> getApplicationDetected()

    @TaskAction
    void printReport() {
        logger.quiet(
            'java=' + javaDetected.get() +
            ',application=' + applicationDetected.get()
        )
    }
}
~~~

Giải thích:

- `@Input` đánh dấu properties mà task action đọc.
- `Property<Boolean>` là managed Gradle property, có thể có convention/default và được cập nhật lúc configuration.
- `@TaskAction` chạy khi task được chọn, không phải ngay khi plugin được apply.
- Task action **không truy cập trực tiếp `project`/`rootProject`** và không tự đọc file hoặc network. Điều này giúp tương thích Configuration Cache hơn.
- Task chỉ in stdout/log, không sinh output file; không đánh dấu `@CacheableTask` bừa bãi hoặc giả định nó `UP-TO-DATE` chỉ vì input không đổi.

Khi plugin chưa phát hiện Java hoặc Application, properties sẽ giữ `false`. Khi listener chạy, chúng được set `true` trước lúc task action thực thi.

## 7. Viết binary plugin có hai listener độc lập

File `build-logic/src/main/groovy/demo/buildlogic/CoordinationPlugin.groovy`:

~~~groovy
package demo.buildlogic

import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.api.plugins.AppliedPlugin
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.api.tasks.JavaExec
import org.gradle.api.tasks.TaskProvider
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.jvm.toolchain.JavaLanguageVersion

class CoordinationPlugin implements Plugin<Project> {
    @Override
    void apply(Project project) {
        TaskProvider<CoordinationReportTask> report =
            project.tasks.register(
                'coordinationReport',
                CoordinationReportTask
            ) { CoordinationReportTask task ->
                task.group = 'verification'
                task.description =
                    'Reports optional plugin coordination.'
                task.javaDetected.convention(false)
                task.applicationDetected.convention(false)
            }

        project.pluginManager.withPlugin('java') {
            AppliedPlugin applied ->
                project.extensions.configure(
                    JavaPluginExtension
                ) { JavaPluginExtension javaExtension ->
                    javaExtension.toolchain.languageVersion.set(
                        JavaLanguageVersion.of(17)
                    )
                }

                project.tasks.withType(JavaCompile).configureEach {
                    JavaCompile compiler ->
                        compiler.options.encoding = 'UTF-8'
                }

                project.tasks.withType(Test).configureEach {
                    Test test ->
                        test.useJUnitPlatform()
                }

                report.configure { CoordinationReportTask task ->
                    task.javaDetected.set(true)
                }
        }

        project.pluginManager.withPlugin('application') {
            AppliedPlugin applied ->
                project.tasks.named('run', JavaExec).configure {
                    JavaExec runTask ->
                        runTask.systemProperty(
                            'demo.mode',
                            'coordinated'
                        )
                }

                report.configure { CoordinationReportTask task ->
                    task.applicationDetected.set(true)
                }
        }
    }
}
~~~

Đây là plugin Groovy hoàn chỉnh khi đặt cùng task type và build-logic files nói trên.

### 7.1. Giải thích từng hành động

**Task report:** `tasks.register` tạo `TaskProvider`, không gọi task action. Hai properties dùng `convention(false)`.

**Listener Java:** `withPlugin('java')` đợi Java plugin. Khi plugin có mặt, `JavaPluginExtension` tồn tại; callback chọn Java 17 toolchain. `tasks.withType(JavaCompile).configureEach` set UTF-8 cho mọi Java compile tasks, kể cả những tasks được đăng ký sau. `tasks.withType(Test).configureEach` chọn JUnit Platform; **nó không tự thêm JUnit dependencies**.

**Listener Application:** `withPlugin('application')` đợi Application plugin. Sau khi plugin được áp dụng, task `run` thuộc type `JavaExec` đã được đăng ký; callback dùng `tasks.named('run', JavaExec).configure` để thêm system property vào Java process của `run`.

**Không ép Java:** plugin custom **không gọi** `project.pluginManager.apply('java')`. Bởi vậy nó có thể được áp vào `:plain` mà không làm plain thành Java project.

**Không có coupling xuyên module:** `project.pluginManager` và `project.tasks` luôn thuộc chính project đang apply. Java trong `:lib` không buộc listener ở `:plain` chạy.

### 7.2. Vì sao không dùng `tasks.all` hoặc `tasks.getByName`?

`tasks.all` có thể gây eager configuration; `getByName` lấy task instance khi chưa cần. Trong example:

- `register` tạo provider.
- `report.configure` thêm cấu hình mà không gọi task action.
- `withType(...).configureEach` hỗ trợ lazy tasks.
- `tasks.named(...).configure` lấy provider của named task.
- Callback chỉ đăng ký rule cấu hình, không resolve dependencies/đọc source files khi configuration.

Đây là hai tầng phối hợp: **`withPlugin` quyết định “khi nào capability đã có?”**, còn **TaskProvider/configureEach quyết định “khi nào task cần cấu hình?”**.

### 7.3. Nếu plugin Java đã được áp thì callback có chạy không?

Có. `withPlugin` không chỉ nghe sự kiện tương lai; nó **chạy ngay** khi ID đã được apply. Nếu `CoordinationPlugin` được apply sau `application`, cả listener Java và Application đều chạy trong `apply(Project)` của custom plugin.

Vì vậy callback phải ngắn gọn và không phụ thuộc việc người dùng đã set các extension properties phía dưới build script. Trong example, không cần biết `application.mainClass` ở thời điểm callback; nó chỉ gắn cấu hình vào task `run`.

## 8. Tạo các consumer modules với thứ tự plugin khác nhau

### 8.1. `lib/build.gradle`: custom trước Java

~~~groovy
plugins {
    id 'demo.plugin-coordination'
    id 'java-library'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}
~~~

Khi custom plugin được apply, `java` chưa có, listener được đăng ký. `java-library` sẽ áp Java plugin; khi đó Java listener chạy và cấu hình toolchain/encoding/JUnit. Không có Application plugin, nên Application listener không chạy.

`:lib:coordinationReport` in:

~~~text
java=true,application=false
~~~

### 8.2. `app/build.gradle`: Application trước custom

~~~groovy
plugins {
    id 'application'
    id 'demo.plugin-coordination'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':lib')

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

application {
    mainClass = 'demo.app.Main'
}
~~~

Ở đây Application và Java plugins đã được áp dụng trước khi custom plugin chạy. Hai callbacks `withPlugin` **thực thi ngay** khi đăng ký.

`:app:coordinationReport` in:

~~~text
java=true,application=true
~~~

Application task `run` có system property `demo.mode=coordinated`. `implementation project(':lib')` cấp Java library trên compile/runtime classpaths của app; đây là project dependency riêng, không phải listener.

### 8.3. `plain/build.gradle`: custom plugin đơn độc

~~~groovy
plugins {
    id 'demo.plugin-coordination'
}
~~~

Project này không có Java/Application plugins. Vì thế callback Java/Application **không chạy** và report task giữ hai flags `false`.

`:plain:coordinationReport` in:

~~~text
java=false,application=false
~~~

Không có `:plain:compileJava` hoặc `:plain:run` theo mặc định. Điều này chứng minh plugin phối hợp thực sự **tùy chọn**, không có tác dụng phụ áp plugin khác.

### 8.4. Quan sát cả ba trạng thái

Từ root:

~~~bash
./gradlew -q :lib:coordinationReport
./gradlew -q :app:coordinationReport
./gradlew -q :plain:coordinationReport
~~~

Stdout lần lượt từ ba lệnh:

~~~text
java=true,application=false
java=true,application=true
java=false,application=false
~~~

Đừng nhầm ba dòng với một task duy nhất; mỗi dòng là kết quả của một command. Thử đảo thứ tự plugins trong `lib` hoặc `app` rồi chạy lại: nếu plugin dùng `withPlugin` đúng cách, kết quả phải giữ nguyên.

## 9. Java 17 application/library nguồn đầy đủ

### 9.1. `lib/src/main/java/demo/lib/Greeting.java`

~~~java
package demo.lib;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String rawName) {
        String name = rawName == null ? "" : rawName.strip();
        if (name.isEmpty()) {
            name = "bạn";
        }
        return "Xin chào, " + name + "!";
    }
}
~~~

Đây là Java 17 source có thể biên dịch. `strip()` hỗ trợ từ Java 11. Library chỉ dùng Java standard library, không cần thêm external production dependencies.

### 9.2. `lib/src/test/java/demo/lib/GreetingTest.java`

~~~java
package demo.lib;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void trimsName() {
        assertEquals("Xin chào, Linh!", Greeting.message(" Linh "));
    }

    @Test
    void usesFallbackForBlank() {
        assertEquals("Xin chào, bạn!", Greeting.message("   "));
    }

    @Test
    void usesFallbackForNull() {
        assertEquals("Xin chào, bạn!", Greeting.message(null));
    }
}
~~~

Có ba JUnit Jupiter methods. `useJUnitPlatform()` đã được cấu hình trong listener Java, nhưng dependencies vẫn phải khai trong `lib/build.gradle`. `testRuntimeOnly` cấp JUnit Platform Launcher cho Gradle versions hiện đại.

### 9.3. `app/src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.lib.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Gradle" : args[0];

        System.out.println(Greeting.message(name));
        System.out.println(
            "mode=" + System.getProperty("demo.mode", "absent")
        );
    }
}
~~~

`Main` in hai dòng: lời chào của lib và giá trị system property `demo.mode`. Plugin phối hợp cấu hình property ấy cho **Gradle Application task `run`**, không thay đổi Java program logic hay môi trường của mọi invocation.

### 9.4. `app/src/test/java/demo/app/MainTest.java`

~~~java
package demo.app;

import static org.junit.jupiter.api.Assertions.assertEquals;

import demo.lib.Greeting;
import org.junit.jupiter.api.Test;

class MainTest {
    @Test
    void seesLibraryClasses() {
        assertEquals("Xin chào, Mai!", Greeting.message(" Mai "));
    }
}
~~~

Có một JUnit test cho app. Nó kiểm classpath giữa app và lib, không chạy Java `main` và không phụ thuộc mutable `System.out` trong test JVM.

### 9.5. Chạy test theo project

~~~bash
./gradlew :lib:test
./gradlew :app:test
./gradlew :lib:build :app:build
~~~

Nếu JUnit/JDK có thể resolve, `:lib:test` chạy 3 tests và `:app:test` chạy 1 test. `:app:test` có thể cần build production classes/JAR của `:lib` nhưng không tự chạy `:lib:test`. `:plain` không có `test` task do không apply Java.

Từ root:

~~~bash
./gradlew test
~~~

chọn test tasks trong các subprojects có chúng; demo có tổng cộng 4 test methods. `:plain` không tự có `test` task.

### 9.6. Chạy Application và dự đoán stdout chính xác

~~~bash
./gradlew -q :app:run
./gradlew -q :app:run --args="Linh"
~~~

Với lệnh không args, Java program in:

~~~text
Xin chào, Gradle!
mode=coordinated
~~~

Với argument `Linh`, Java program in:

~~~text
Xin chào, Linh!
mode=coordinated
~~~

`-q` giảm Gradle lifecycle logs nhưng vẫn hiển thị stdout từ Java process. Đây là bằng chứng mạnh hơn report boolean: callback `withPlugin('application')` đã thật sự cấu hình system property trên task `run`.

### 9.7. Kiểm `javac`/`java` thủ công, không đi qua Gradle Application task

Các classes sản phẩm không cần Maven libraries. Trên Linux/macOS từ root project:

~~~bash
mkdir -p manual/lib manual/app

javac -encoding UTF-8 \
    -d manual/lib \
    lib/src/main/java/demo/lib/Greeting.java

javac -encoding UTF-8 \
    -cp manual/lib \
    -d manual/app \
    app/src/main/java/demo/app/Main.java

java -cp "manual/lib:manual/app" demo.app.Main Linh
~~~

Stdout:

~~~text
Xin chào, Linh!
mode=absent
~~~

Lý do: lệnh `java` thủ công không dùng `:app:run`, nên không được custom plugin truyền `-Ddemo.mode=coordinated`. Java code dùng default `absent`.

Trên Windows PowerShell, dùng separator classpath `;` thay dấu `:`:

~~~powershell
java -cp "manual\lib;manual\app" demo.app.Main Linh
~~~

Kết quả tương tự nếu đã compile classes vào hai thư mục tương ứng. Chạy `javac` bằng JDK 17 và lưu source UTF-8 để chữ tiếng Việt đúng.

## 10. Gradle TestKit kiểm chứng plugin order một cách tự động

Ba lệnh report thủ công giúp quan sát, nhưng một plugin chia sẻ cho nhiều dự án cần **functional tests** để bắt lỗi hồi quy nếu ai đó thay `withPlugin` bằng `hasPlugin` hoặc bắt đầu áp Java vô điều kiện.

Gradle TestKit có `GradleRunner` để chạy một Gradle build fixture trong thư mục tạm. Vì đây là **binary plugin** được build bằng `groovy-gradle-plugin`/Gradle Plugin Development Plugin, `withPluginClasspath()` có thể inject compiled plugin-under-test classpath vào fixture, không cần publish plugin lên repository.

### 10.1. `build-logic/src/test/java/demo/buildlogic/CoordinationPluginTest.java`

~~~java
package demo.buildlogic;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CoordinationPluginTest {
    @TempDir
    Path fixtureDirectory;

    private BuildResult execute(String buildScript) throws IOException {
        Files.writeString(
            fixtureDirectory.resolve("settings.gradle"),
            "rootProject.name = 'fixture'\n",
            StandardCharsets.UTF_8
        );

        Files.writeString(
            fixtureDirectory.resolve("build.gradle"),
            buildScript,
            StandardCharsets.UTF_8
        );

        return GradleRunner.create()
            .withProjectDir(fixtureDirectory.toFile())
            .withArguments(
                "coordinationReport",
                "--quiet",
                "--stacktrace"
            )
            .withPluginClasspath()
            .build();
    }

    @Test
    void customPluginBeforeJavaPlugin() throws IOException {
        BuildResult result = execute(
            "plugins {\n" +
            "    id 'demo.plugin-coordination'\n" +
            "    id 'java-library'\n" +
            "}\n"
        );

        assertTrue(
            result.getOutput().contains(
                "java=true,application=false"
            )
        );
        assertNotNull(result.task(":coordinationReport"));
    }

    @Test
    void customPluginAfterApplicationPlugin() throws IOException {
        BuildResult result = execute(
            "plugins {\n" +
            "    id 'application'\n" +
            "    id 'demo.plugin-coordination'\n" +
            "}\n"
        );

        assertTrue(
            result.getOutput().contains(
                "java=true,application=true"
            )
        );
    }

    @Test
    void customPluginWithoutJavaOrApplication() throws IOException {
        BuildResult result = execute(
            "plugins {\n" +
            "    id 'demo.plugin-coordination'\n" +
            "}\n"
        );

        assertTrue(
            result.getOutput().contains(
                "java=false,application=false"
            )
        );
    }
}
~~~

Đây là Java 17/JUnit test class hoàn chỉnh **trong build-logic project**, không phải Java product test của `:app`. Mỗi test có thư mục `@TempDir` riêng, tạo `settings.gradle` và `build.gradle` của fixture rồi chạy GradleRunner.

Ba tests xác nhận:

1. **Custom plugin trước Java:** listener được đăng ký trước, sau đó mới kích hoạt.
2. **Custom plugin sau Application:** Java/Application đã được apply, callbacks chạy ngay.
3. **Không có Java/Application:** plugin coordination không buộc áp chúng, cả hai flags vẫn false.

Không chỉ kiểm có task: test còn assert dòng output do typed task action in.

### 10.2. Chạy tests của included build

Từ root demo:

~~~bash
./gradlew -p build-logic test
~~~

Điều này gọi `test` trong included build `build-logic`, không phải root task `:build-logic:test`. Report theo convention ở:

~~~text
build-logic/build/reports/tests/test/index.html
~~~

Dự kiến có ba TestKit test methods pass khi plugin code, JUnit classpath và GradleRunner environment hoạt động. Nếu fail, đọc output của fixture và `--stacktrace` để xác định plugin ID/classpath hay callback timing.

### 10.3. Cần kiểm thêm gì ngoài ba order tests?

Các test trên chứng minh **callback được kích hoạt đúng**, nhưng chưa chứng minh mọi cấu hình Java/task thật sự đúng. Trong production nên bổ sung các fixture tests:

- Java plugin applied → `JavaPluginExtension.toolchain.languageVersion` là 17.
- JavaCompile task cần UTF-8 → chạy một source file có ký tự có dấu.
- Test task → JUnit Jupiter test được phát hiện và chạy bằng `useJUnitPlatform()`.
- Application plugin → `run` thật sự truyền `demo.mode` và stdout có `mode=coordinated`.
- Chỉ custom plugin → `compileJava` và `run` không được tạo.
- Nhiều Gradle versions theo support matrix → plugin vẫn tương thích.
- Chạy hai lần với `--configuration-cache` → không đọc Project mutable state trong task action.

Functional tests tốn thời gian spawn Gradle build, nên nhóm theo behavior và reuse fixture setup hợp lý.

### 10.4. `withPluginClasspath()` khác `pluginManager.withPlugin` như thế nào?

Hai API có chữ “Plugin” nhưng mục tiêu hoàn toàn khác:

- **`GradleRunner.withPluginClasspath()`**: chuẩn bị classpath cho **binary/precompiled plugin under test** bên trong fixture build; cho phép dùng plugin ID.
- **`Project.pluginManager.withPlugin(...)`**: đăng ký listener để phối hợp với **một plugin khác đã/đang được áp dụng** trong Project được cấu hình.

Nếu bạn thử một **applied script plugin** `apply from: 'gradle/helper.gradle'`, TestKit không tự cấp plugin ID cho file script; fixture phải copy hoặc tham chiếu đúng file đó. Demo này là binary plugin có ID được đăng ký, nên TestKit classpath injection là phù hợp.

## 11. Kotlin DSL / Java plugin API tương đương

### 11.1. Kotlin DSL trích đoạn

Trong `build.gradle.kts` hoặc precompiled plugin nơi các Gradle API types có sẵn:

~~~kotlin
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.jvm.toolchain.JavaLanguageVersion

pluginManager.withPlugin("java") {
    extensions.configure<JavaPluginExtension> {
        toolchain.languageVersion.set(JavaLanguageVersion.of(17))
    }

    tasks.withType<JavaCompile>().configureEach {
        options.encoding = "UTF-8"
    }
}
~~~

Đây là **đoạn minh họa**, không phải một file project độc lập. Nếu Java plugin chưa được apply, callback chờ; khi Java xuất hiện, nó cấu hình typed extension và compiler tasks. Đừng sao chép mọi generated Kotlin DSL type-safe accessor vào một applied Kotlin script nếu loại script đó không hỗ trợ chúng.

### 11.2. Java binary plugin trích đoạn

~~~java
project.getPluginManager().withPlugin("java", applied -> {
    project.getExtensions().configure(
        JavaPluginExtension.class,
        ext -> ext.getToolchain()
            .getLanguageVersion()
            .set(JavaLanguageVersion.of(17))
    );
});
~~~

Đây là **method-body fragment**, cần class implements `Plugin<Project>`, imports và plugin project để compile. Contract không đổi: callback chạy sau Java plugin apply, không tự apply Java.

## 12. Tích hợp plugin bên thứ ba: thời điểm không giải quyết classpath

### 12.1. Listener không tự tải/resolve external plugin

Ví dụ:

~~~groovy
project.pluginManager.withPlugin('org.example.analysis') {
    // Chỉ chạy khi plugin đó được áp dụng.
}
~~~

`org.example.analysis` là ID **minh họa**, không phải một external plugin có thật. Callback này không khai version hoặc repository. Người dùng hay convention plugin khác phải resolve và apply plugin theo cách hỗ trợ.

Nếu custom plugin **bắt buộc** phải có external plugin, đó là một hợp đồng khác: có thể cần plugin implementation dependency trong build-logic và explicit `pluginManager.apply('vendor.id')`.

### 12.2. Vendor task type cần Gradle plugin classpath

Nếu muốn trong callback:

~~~groovy
project.pluginManager.withPlugin('org.example.analysis') {
    project.tasks.withType(SomeVendorTask).configureEach {
        // Cấu hình vendor task type.
    }
}
~~~

`SomeVendorTask` là kiểu giả định, không thuộc Gradle API. Nó phải khả dụng trên **plugin compilation/runtime classpath** phù hợp; dependency `implementation '...'` của ứng dụng Java không tự làm vendor type có thể import trong Gradle plugin code.

Với optional external integration, Gradle hướng dẫn cân nhắc `compileOnly` cho vendor API để tránh làm rò một phiên bản vendor implementation vào classpath của consumer. Tuy nhiên `compileOnly` không đi vào runtime nên phải guard việc sử dụng type và thiết kế TestKit fixture có vendor plugin implementation khi kiểm tích hợp. Nếu cần tích hợp bắt buộc/pin version, `implementation` có thể phù hợp nhưng phải quản lý xung đột versions.

### 12.3. Plugin ID đã xuất hiện không bảo đảm ABI tương thích

`withPlugin` giải quyết **thứ tự và model availability**, không bảo đảm class/method trong vendor API của version mới còn tương thích. Nếu plugin author compile với API version A nhưng consumer áp version B không tương thích, vẫn có thể gặp `NoClassDefFoundError`, `NoSuchMethodError` hoặc lỗi task configuration.

Giải pháp: khai support matrix, dùng public APIs, đặt đúng dependency scopes và TestKit chạy với những vendor Gradle/plugin versions được hỗ trợ. Không dùng ID availability như một thay thế cho binary-compatibility testing.

## 13. Callback kết hợp nhiều plugin: hai listener hay listener lồng nhau?

Nếu Java và một plugin tùy chọn đều phải có trước khi làm thao tác chung:

~~~groovy
project.pluginManager.withPlugin('java') {
    project.pluginManager.withPlugin('org.example.analysis') {
        // Chạy khi cả hai plugin đã được áp dụng.
    }
}
~~~

Đây là trích đoạn cấu trúc. Nếu analysis đã apply trước Java, inner listener thấy nó đã có và chạy ngay khi Java callback đăng ký. Nếu analysis xuất hiện sau Java, inner listener đợi. Trong trường hợp chỉ cần hai hành động độc lập, nên khai **hai listeners ngang hàng** để dễ hiểu:

~~~groovy
project.pluginManager.withPlugin('java') {
    // Quy ước Java.
}

project.pluginManager.withPlugin('application') {
    // Quy ước run.
}
~~~

Không sử dụng tên plugin giả `org.example.analysis` trong demo thực tế nếu bạn chưa có plugin ID/implementation tương ứng.

### 13.1. Callback có thể chạy “sớm” đối với user extension settings

`withPlugin` không đợi user cấu hình mọi property. Tránh:

~~~groovy
project.pluginManager.withPlugin('application') {
    def finalMainClass = project.extensions
        .getByType(ApplicationPluginExtension)
        .mainClass.get()

    // Có thể lỗi nếu user chưa set mainClass.
}
~~~

Đây là **anti-pattern minh họa**: không đọc `.get()` trước khi người dùng set property. Thay vì thế, dùng lazy task configuration/Provider hoặc wire dependency để giá trị được giải quyết khi cần.

### 13.2. Cấu hình policy Java khi nhiều plugins cùng can thiệp

Nếu shared convention khác muốn Java 21 nhưng custom plugin đặt 17:

~~~groovy
javaExtension.toolchain.languageVersion.set(
    JavaLanguageVersion.of(17)
)
~~~

`withPlugin` không quyết định ai thắng. Nếu property bị set/finalize theo chính sách khác, plugin có thể gây xung đột. Với một **default** cho user override, dùng `convention(JavaLanguageVersion.of(17))`. Với policy bắt buộc, dùng `set(...)` và document ownership rõ ràng; CI cần kiểm chính sách cuối cùng.

### 13.3. `useJUnitPlatform` không cài JUnit cho consumer

Task configuration:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

chỉ chọn JUnit Platform; nếu `testImplementation`/`testRuntimeOnly` thiếu, test execution có thể fail. Đừng trông chờ core Java plugin hay plugin coordination tự đem JUnit Jupiter API/engine/Launcher vào test runtime.

Nếu một module dùng TestNG, tự ép `useJUnitPlatform` trên mọi Test task có thể xung đột với test framework mà người dùng chọn. Tổ chức cần chính sách rõ: plugin dành riêng JUnit, hoặc có opt-in cho từng framework.

## 14. Debug bằng Gradle CLI

### 14.1. Task nào có mặt ở từng project?

~~~bash
./gradlew :lib:tasks --all
./gradlew :app:tasks --all
./gradlew :plain:tasks --all
~~~

Kỳ vọng:

| Task | lib | app | plain |
| --- | --- | --- | --- |
| `coordinationReport` | Có | Có | Có |
| `compileJava` | Có | Có | Không |
| `test` | Có | Có | Không |
| `run` | Không | Có | Không |

Nếu plain có `compileJava`, kiểm plugin khác đã apply Java ở plain hay chưa; custom plugin demo không áp Java. Nếu app không có `run`, kiểm Application plugin có được apply đúng project không.

### 14.2. Dry-run cho task graph, không cho behavior của task action

~~~bash
./gradlew :app:run --dry-run
./gradlew :lib:test --dry-run
./gradlew :plain:coordinationReport --dry-run
~~~

`--dry-run` chỉ lập task plan, không chạy Java main, JUnit tests hoặc `printReport()`. Vì vậy đừng chờ output `java=false,application=false` xuất hiện trong dry-run.

Muốn xem callback đem tác dụng vào task action, chạy:

~~~bash
./gradlew -q :app:run --args="Linh"
./gradlew -q :plain:coordinationReport
~~~

### 14.3. Stacktrace và thông tin thực thi

~~~bash
./gradlew :app:test --stacktrace
./gradlew :app:run --info
./gradlew -p build-logic test --stacktrace
~~~

Phân biệt:

- **Configuration/plugin application failure:** lỗi trong `CoordinationPlugin.apply`/listener.
- **Task provider error:** task `run` chưa được đăng ký hoặc sai task type.
- **Java compiler error:** Java source/toolchain/classpath.
- **JUnit runtime failure:** thiếu JUnit dependencies hoặc test framework config xung đột.
- **TestKit failure:** plugin ID/descriptor/classpath hoặc fixture script.
- **Configuration Cache failure:** task action đọc mutable Project/build configuration state thay vì typed inputs.

### 14.4. Configuration Cache

~~~bash
./gradlew :app:coordinationReport --configuration-cache
./gradlew :app:coordinationReport --configuration-cache
~~~

Lần đầu Gradle có thể lưu configuration state; lần sau có thể reuse nếu không có thay đổi hoặc incompatible build logic. `CoordinationReportTask` không đọc Project từ `@TaskAction` nên là mẫu rõ ràng hơn cho configuration-cache-aware code.

Không cam kết mọi Gradle invocation đều cache hit: Gradle version, JDK, scripts, plugin builds, input changes hoặc task incompatibilities có thể invalidate cache.

## 15. Troubleshooting — lỗi phổ biến khi dùng withPlugin

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Listener Java không chạy | Java plugin không được apply trong **project đó** | Kiểm plugin ID, project scope và task list |
| Callback chạy ngay dù đã đăng ký “muộn” | Plugin đã được apply trước | Đây là contract, không phải lỗi |
| Callback không bao giờ chạy trong plain | Java/Application không có | Đúng với optional integration |
| `hasPlugin('java')` false trước khi Java áp dụng | Snapshot được kiểm quá sớm | Dùng `withPlugin` |
| `Could not find method java()` | Extension chưa tồn tại hoặc DSL sai scope | Chờ Java và dùng typed `extensions.configure` |
| `Task with name run not found` | Không có Application plugin | Chờ `withPlugin('application')` |
| `UnknownPluginException` | Plugin ID/version không resolve | Kiểm `pluginManagement`, included build, plugin ID |
| `Plugin with id ... not found` | Plugin descriptor/classpath sai | Kiểm `gradlePlugin` registration |
| Project plain có compileJava ngoài ý muốn | Plugin khác ép Java | Dò plugin application chain |
| Toolchain value đổi theo plugin order | Hai policies cùng set property | Quy định owner/convention/precedence |
| `Test.useJUnitPlatform` đã set nhưng test fail | Thiếu JUnit engine/Launcher/runtime deps | Khai `testImplementation`/`testRuntimeOnly` |
| `withPlugin` callback type sai | Nhầm `Plugin` với `AppliedPlugin` | Dùng đúng API callback |
| `tasks.named('run')` không đúng type | Vendor/task khác với JavaExec | Dùng type đúng, kiểm task owner |
| Log callback mất khi Configuration Cache hit | Callback chạy ở configuration phase | Đặt hành động quan sát trong task action |
| Plugin types import không được | Build-logic classpath thiếu API | Khai dependency đúng scope |
| `NoClassDefFoundError` khi vendor plugin có | Vendor plugin ABI/runtime classpath sai | Test supported versions, tránh internal APIs |
| Plugin code đọc `mainClass.get()` quá sớm | Consumer chưa set property | Lazy Provider/task configuration |
| `:build-logic:test` không có | build-logic là included build | Dùng `./gradlew -p build-logic test` |
| TestKit không thấy plugin ID | Thiếu plugin-under-test classpath | `withPluginClasspath()` và plugin registration |
| `--dry-run` không in report marker | Task action không chạy trong dry-run | Chạy task thật |
| Task action Configuration Cache fail | Đọc Project mutable state ở execution | Typed `Property`/inputs/outputs |
| Java CLI ngoài Gradle không có `mode=coordinated` | Chỉ Gradle Application run nhận property | Truyền `-Ddemo.mode` nếu chạy thủ công |
| Plugin test chỉ kiểm thứ tự sau, không kiểm trước | Test coverage thiếu | Test before/after/absent |

## 16. Bài tập và đáp án

### Bài 1 — withPlugin có tự apply Java không?

Không. `withPlugin('java')` chỉ đăng ký callback. Project `:plain` không có Java plugin thì không tự tạo `compileJava`.

### Bài 2 — Plugin custom chạy trước Java Library?

`:lib` khai custom trước `java-library`. Java callback đợi cho đến khi Java được apply, rồi set report flag `true`. Kết quả `java=true,application=false`.

### Bài 3 — Plugin custom chạy sau Application?

`:app` khai Application trước custom. Java và Application đều đã được áp dụng, nên callbacks chạy ngay. Kết quả `java=true,application=true`.

### Bài 4 — Nếu đổi `withPlugin` thành `hasPlugin` một lần?

Plugin áp trước Java sẽ bỏ lỡ cấu hình. Cần listener để không phụ thuộc thứ tự.

### Bài 5 — Khi nào dùng `apply`?

Nếu plugin yêu cầu Java bắt buộc theo hợp đồng. Nếu Java chỉ là optional capability, `withPlugin` phù hợp hơn.

### Bài 6 — Callback nhận đối tượng gì?

`withPlugin` nhận `AppliedPlugin` metadata; `plugins.withId` nhận instance `Plugin`. Để sửa Java extension, dùng `extensions.configure(JavaPluginExtension)`.

### Bài 7 — Vì sao dùng `configureEach`?

Nó cấu hình JavaCompile/Test tasks lazy và áp dụng cả những tasks đăng ký sau. `withPlugin` không tự giải quyết task realization.

### Bài 8 — Vì sao Application callback có thể tìm task run?

Khi `withPlugin('application')` chạy, Application plugin đã apply, task `run` của plugin chuẩn đã được đăng ký. Sau đó `tasks.named('run', JavaExec).configure` là thích hợp.

### Bài 9 — Lệnh `java` thủ công khác `:app:run` thế nào?

`:app:run` có property `demo.mode=coordinated` do custom plugin set. `java -cp ... demo.app.Main Linh` thủ công không có property nên in `mode=absent`.

### Bài 10 — Khi nào report xuất hiện?

`coordinationReport` là task action; chỉ in khi task được thực thi. `--dry-run` không chạy action nên không có marker.

### Bài 11 — Plugin Java callback có tự thêm JUnit không?

Không. `useJUnitPlatform()` chọn framework, consumer vẫn cần `testImplementation` và `testRuntimeOnly`.

### Bài 12 — TestKit phải kiểm ba trường hợp nào?

Plugin custom **trước** Java, custom **sau** Application, và custom **không kèm** Java/Application. Sau đó thêm tests để kiểm toolchain/encoding/run thật.

### Bài 13 — Hai plugins cùng set Java toolchain?

`withPlugin` chỉ giải quyết availability, không giải quyết ownership. Cần policy owner rõ, dùng `convention` cho default hoặc `set` cho giá trị bắt buộc.

### Bài 14 — Tích hợp vendor task có đủ nếu vendor ID xuất hiện?

Không. Type/class phải có trong plugin classpath và version binary-compatible. Optional integration có thể dùng `compileOnly` cho vendor API nhưng cần setup runtime/TestKit đúng.

### Bài 15 — Java callback phải chạy sau project evaluation?

Không. Callback chạy sau **plugin application**, có thể trước user DSL phía dưới `plugins { }`. Đừng đọc final user configuration quá sớm.

### Bài 16 — Tại sao project plain vẫn có coordinationReport?

Task do custom plugin đăng ký **vô điều kiện**. Hai listeners Java/Application chỉ đổi task input flags khi plugin tùy chọn xuất hiện.

## 17. Checklist viết plugin phối hợp an toàn

1. Đã phân biệt capability bắt buộc và tùy chọn?
2. Với plugin tùy chọn, đã dùng `pluginManager.withPlugin` thay `hasPlugin` được kiểm quá sớm?
3. Callback hoạt động khi plugin đã apply **trước**?
4. Callback hoạt động khi plugin apply **sau**?
5. Callback không chạy khi plugin **vắng mặt**, và đó là trạng thái hợp lệ?
6. Listener được đăng ký trên đúng `Project.pluginManager`?
7. Plugin IDs phản ánh chính xác capability cần có (`java`/`application`/`java-library`)?
8. Callback chỉ cấu hình model sau plugin application, không đoán extension/task tồn tại trước?
9. Có dùng `tasks.register`, `tasks.named`, `configureEach` và typed extensions?
10. Có tránh `afterEvaluate` cho việc chờ plugin?
11. Có tránh đọc user `Property.get()` quá sớm?
12. Có phân định owner khi nhiều plugins cùng set Java toolchain/encoding/test framework?
13. Có tránh task dependency giả chỉ để ép thứ tự log?
14. External plugin API có dependency scope/version phù hợp?
15. Có tránh coi `withPlugin` là plugin resolver hoặc auto-apply?
16. Task action có typed inputs/outputs phù hợp Configuration Cache?
17. Functional tests bằng Gradle TestKit bao phủ before/after/absent?
18. Java 17/JUnit/Gradle Wrapper versions phù hợp dev/CI?
19. Lệnh `:app:run` và `java -cp` thủ công có stdout đúng theo nguồn system property?
20. Đã thử trên support matrix trước khi phát hành plugin cho nhiều projects?

## 18. Tài liệu chính thức

- [Gradle PluginManager API](https://docs.gradle.org/current/javadoc/org/gradle/api/plugins/PluginManager.html): `withPlugin`, `apply`, `hasPlugin`, `findPlugin`, `AppliedPlugin`.
- [Gradle PluginContainer API](https://docs.gradle.org/current/javadoc/org/gradle/api/plugins/PluginContainer.html): `withId` và `Plugin` callback.
- [Gradle General Best Practices](https://docs.gradle.org/current/userguide/best_practices_general.html): plugin-order independence và tránh `afterEvaluate`.
- [Gradle Binary Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_binary.html): `Plugin<Project>`, Gradle plugin development, external plugin integration.
- [Gradle Groovy Gradle Plugin](https://docs.gradle.org/current/userguide/groovy_gradle_plugin.html): cấu hình `groovy-gradle-plugin`.
- [Gradle TestKit](https://docs.gradle.org/current/userguide/test_kit.html): `GradleRunner`, `withPluginClasspath()`.
- [Gradle Testing Plugins](https://docs.gradle.org/current/userguide/testing_gradle_plugins.html): functional test patterns.
- [Gradle Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`/`named`/`configureEach`.
- [Gradle Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Property<T>`/`Provider<T>`/convention.
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): Java 17 toolchain.
- [Gradle Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): `Test.useJUnitPlatform` và JUnit runtime.
- [Gradle Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`/`JavaExec`.
- [Gradle Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration và task execution restrictions.
