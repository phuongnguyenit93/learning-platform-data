# Plugin<Project>, Plugin<Settings> và phạm vi áp dụng trong Gradle

## Mục tiêu bài học

Một **Gradle plugin** là mã build logic tái sử dụng được. Điểm quan trọng khi phát triển plugin không chỉ là **plugin ID** hoặc file JAR, mà còn là **đối tượng Gradle mà plugin được áp dụng lên**. Hai loại plugin thường gặp là:

- **Plugin<Project>**: nhận một **Project**, cấu hình task, source sets, dependencies, extensions, Java toolchain và conventions **của project đó**.
- **Plugin<Settings>**: nhận một **Settings**, cấu hình **cấu trúc build** và những thiết lập thuộc giai đoạn initialization, như include project, quản lý repository/dependency resolution, plugin resolution và các chính sách ở mức settings.

Cả hai cùng triển khai interface **org.gradle.api.Plugin<T>** và method **void apply(T target)**, nhưng **T khác nhau dẫn đến phạm vi và thời điểm áp dụng khác nhau**. Một Project plugin không trở thành Settings plugin chỉ vì người dùng đặt plugin ID ấy trong settings.gradle; và Settings plugin không có task container của một Project để tự đăng ký task.

Sau bài học, bạn có thể:

1. Phân biệt **Project**, **Settings** và **Gradle** là ba plugin targets có vòng đời khác nhau.
2. Giải thích **settings.gradle(.kts)** khác **build.gradle(.kts)** về đối tượng nhận plugin.
3. Chọn **Plugin<Project>** cho cấu hình project và **Plugin<Settings>** cho cấu hình build-wide sớm.
4. Tạo **hai binary Gradle plugins bằng Java 17**, đăng ký chúng với **java-gradle-plugin**, và áp dụng từng plugin vào đúng target.
5. Dùng **pluginManagement { includeBuild('plugin-build') }** để settings plugin local có mặt đủ sớm.
6. Hiểu **Plugin ID**, **implementationClass**, **plugin descriptors**, **plugin marker artifacts** và khi nào cần publish.
7. Chạy một lab độc lập, có task type an toàn với Gradle Provider API và stdout dự đoán được.
8. Phân biệt hành động trong **apply()** ở configuration phase với **@TaskAction** ở execution phase.
9. Biết project plugin chỉ ảnh hưởng project được áp, không tự lan sang subprojects hoặc included builds.
10. Thử các tình huống áp plugin sai target, sai plugin path hoặc thiếu repository/marker và chẩn đoán chính xác.
11. Viết một functional test bằng **Gradle TestKit** cho cả Settings plugin và Project plugin.
12. Hiểu lựa chọn **precompiled script plugin**, **binary plugin**, và giới hạn của việc trộn hai scopes vào một plugin.
13. Áp dụng policy thiết kế plugin an toàn cho CI, configuration cache, isolated projects và nâng cấp Gradle.

Bài thực hành dùng **Java 17+** và **Groovy DSL**, kèm Kotlin DSL tương đương. Cần Gradle Wrapper tương thích với JDK đang chạy; dùng Gradle 8.5+ hoặc Gradle 9.x phù hợp chính sách dự án. Lab chính chỉ dùng core plugin **java-gradle-plugin**, không tải thư viện Java bên ngoài. Phần TestKit/JUnit là mở rộng và cần dependency repository như Maven Central hoặc mirror/cache.

---

## 1. Plugin<T> là hợp đồng chung

Trong Java, interface gốc có dạng khái niệm:

~~~java
package org.gradle.api;

public interface Plugin<T> {
    void apply(T target);
}
~~~

Đây là **chữ ký khái niệm**, không phải file bạn phải tạo trong project. Interface thật đã có trong Gradle API. Kiểu **T** quyết định loại target được truyền cho method apply.

Ví dụ Project plugin:

~~~java
import org.gradle.api.Plugin;
import org.gradle.api.Project;

public class ExampleProjectPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        // Build logic dành cho Project được áp plugin.
    }
}
~~~

Ví dụ Settings plugin:

~~~java
import org.gradle.api.Plugin;
import org.gradle.api.initialization.Settings;

public class ExampleSettingsPlugin implements Plugin<Settings> {
    @Override
    public void apply(Settings settings) {
        // Build logic dành cho Settings đang được cấu hình.
    }
}
~~~

Hai đoạn trên chỉ minh họa chữ ký, không phải những Java source files đầy đủ trong lab vì thiếu package và chưa có hành vi hữu ích. Lab hoàn chỉnh nằm ở mục 6.

### 1.1. Gradle có ba plugin scopes chính

| Plugin target | Java interface | Điểm áp dụng điển hình | Công việc phù hợp |
| --- | --- | --- | --- |
| **Project** | Plugin<Project> | **build.gradle(.kts)** | Task, extensions, dependency configurations, source sets, Java compilation, reporting |
| **Settings** | Plugin<Settings> | **settings.gradle(.kts)** | include project/build, plugin management, repository management, build structure |
| **Gradle** | Plugin<Gradle> | Init script / Gradle runtime | Initialization/global tooling, build-wide hooks cần đặc biệt cân nhắc |

**Plugin<Gradle>** được nhắc để hiểu toàn cảnh, nhưng bài này chỉ thực hành Project và Settings plugins. Một plugin dùng target Gradle không đương nhiên thay thế Settings hoặc Project plugin.

### 1.2. Plugin<Project> có quyền gì?

Đối tượng **Project** cho plugin tiếp cận:

- **project.getTasks()**: TaskContainer; đăng ký task bằng **tasks.register(...)**.
- **project.getConfigurations()**: dependency configurations.
- **project.getDependencies()**: khai báo dependencies.
- **project.getExtensions()**: tạo extension DSL.
- **project.getPlugins() / getPluginManager()**: phối hợp với plugins khác.
- **project.getLayout()**, **project.getProviders()**: lazy locations/providers.
- **project.getPath()**, **getName()**, **getProjectDir()**: identity và vị trí project.

Ví dụ phù hợp:

~~~groovy
plugins {
    id 'java'
    id 'dev.example.project-greeting'
}
~~~

Dòng này nằm trong **build.gradle**, nên Gradle áp project plugin vào **Project tương ứng**. Nếu được khai báo ở root build.gradle, scope mặc định là root project, không tự động vào mọi subproject.

### 1.3. Plugin<Settings> có quyền gì?

Đối tượng **Settings** cho plugin tiếp cận:

- **settings.include(...)** để định nghĩa subprojects.
- **settings.includeBuild(...)** để định nghĩa included builds.
- **settings.getRootProject()** trả **ProjectDescriptor**, không phải Project object đã cấu hình.
- **settings.getPluginManagement()** và **getDependencyResolutionManagement()** cho những chính sách phù hợp ở settings.
- **settings.getExtensions()** để tạo extensions/properties của Settings.
- **settings.getSettingsDir()**, **getRootDir()** và settings-level providers.
- **settings.getGradle()** nếu cần truy cập Gradle build invocation theo API được hỗ trợ.

Ví dụ trong **settings.gradle**:

~~~groovy
pluginManagement {
    includeBuild('plugin-build')
}

plugins {
    id 'dev.example.settings-greeting'
}

rootProject.name = 'hello-app'
~~~

Plugin trong block **plugins** của settings được áp vào **Settings**. Nó không tạo một Project task bằng cú pháp project.getTasks(), vì đối tượng Project chưa phải target đang được cung cấp cho apply.

### 1.4. Không đánh đồng scope với nơi lưu mã plugin

Một plugin implementation ở **plugin-build/src/main/java** có thể là Project plugin hoặc Settings plugin tùy generic type và cách áp dụng. Cùng một JAR có thể công bố **hai plugin IDs** với hai implementation classes khác target.

Vị trí mã ở included build, buildSrc hoặc repository chỉ quyết định **plugin được tìm thấy bằng cách nào**. Nó không tự đổi target type.

---

## 2. Vòng đời Gradle: Settings chạy trước Project

Gradle có các pha chính:

1. **Initialization**: tìm settings.gradle(.kts), tạo Settings, xử lý plugin management, áp settings plugins, xác định danh sách projects và included builds.
2. **Configuration**: tạo và cấu hình Project objects, đọc build.gradle(.kts), áp project plugins, đăng ký tasks/configurations/extensions.
3. **Execution**: xây task graph theo yêu cầu và thực thi các tasks cần thiết.

### 2.1. Dòng thời gian rút gọn

~~~text
Gradle invocation
       |
       v
Initialization
  settings.gradle
    pluginManagement {...}
    plugins {...}  ---> Plugin<Settings>.apply(settings)
    rootProject.name
    include(...)
       |
       v
Configuration
  root build.gradle   ---> Plugin<Project>.apply(rootProject)
  module build.gradle ---> Plugin<Project>.apply(moduleProject)
  tasks.register(...)
       |
       v
Execution
  tasks selected by CLI/task graph
  @TaskAction, doLast, compiler/Test actions
~~~

Gradle có thể thực hiện lazy configuration và configuration cache; sơ đồ này diễn tả **phạm vi trách nhiệm** chứ không cam kết từng task được realized theo thứ tự nhất định.

### 2.2. Plugin.apply không phải task action

Khi Project plugin có:

~~~java
@Override
public void apply(Project project) {
    project.getTasks().register("helloProject", GreetingTask.class);
}
~~~

**apply() chạy khi plugin được áp trong configuration**; nó đăng ký task. Nội dung **@TaskAction** chỉ chạy khi Gradle quyết định task ấy nằm trong execution graph, và không bị SKIPPED/UP-TO-DATE theo logic thực tế.

Vì vậy chạy **./gradlew help** có thể áp Project plugin nhưng **không chạy helloProject**. Một plugin không nên tạo file build output hoặc gọi process bên ngoài ngay trong apply() chỉ để mô phỏng task execution.

### 2.3. Settings plugin hoạt động sớm

Settings plugin được áp trong giai đoạn initialization, khi Gradle đang quyết định có những projects nào trong build. Vì vậy nó là nơi tự nhiên để thực hiện:

~~~groovy
include 'app', 'domain'
~~~

hoặc thiết lập dependency repositories ở cấp settings.

**Project plugin không thể giả định nó còn đủ sớm để thay đổi danh sách projects**. Khi build.gradle được đọc, danh sách project hierarchy đã được xác định.

### 2.4. Không đọc Project từ Settings khi chưa đến lúc

Trong Settings phase, **settings.rootProject** là **ProjectDescriptor** của root project; nó mô tả tên/path/projectDir, không phải Project instance với TaskContainer.

Không viết:

~~~java
// SAI VỀ KIẾN TRÚC:
settings.getRootProject().getTasks().register("hello");
~~~

**ProjectDescriptor** không có getTasks() như Project. Muốn đăng ký project tasks, hãy tạo Plugin<Project> riêng và áp nó ở project phase.

### 2.5. Không tự động chia sẻ scope giữa included builds

Mỗi included build có settings và projects riêng. Settings plugin đã được áp cho including build **không có nghĩa** nó tự áp cho tất cả included builds. Muốn chính sách giống nhau, cần distribution/convention rõ cho từng build.

---

## 3. Các file được áp plugin và cú pháp plugins DSL

### 3.1. Settings plugin tại settings.gradle

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

plugins {
    id 'dev.example.settings-greeting' version '1.0.0'
}
~~~

Đây là ví dụ **khi plugin đã publish và có plugin marker trong repository được cấu hình**. Plugin ID/version là ví dụ, không khẳng định artifact này đã tồn tại trên Plugin Portal.

### 3.2. Project plugin tại build.gradle

~~~groovy
plugins {
    id 'dev.example.project-greeting' version '1.0.0'
}
~~~

Project plugin nhận **Project của script này**, không nhận Settings, và không tự bao phủ tất cả các project khác.

### 3.3. pluginManagement phải đặt đúng giai đoạn

**pluginManagement** trong settings phải xuất hiện đủ sớm, trước plugins block cần resolve plugin. Trong lab local:

~~~groovy
pluginManagement {
    includeBuild('plugin-build')
}

plugins {
    id 'dev.example.settings-greeting'
}
~~~

Gradle biết plugin build local ngay tại plugin resolution. Nếu chỉ đưa **includeBuild 'plugin-build'** xuống cuối settings.gradle sau khi **plugins { ... }** đã resolve settings plugin, có thể là **quá muộn để tìm plugin đó**.

Đây là lý do Gradle docs yêu cầu **pluginManagement.includeBuild** đối với Settings plugins từ included plugin builds.

### 3.4. pluginManagement.repositories khác dependencyResolutionManagement.repositories

Trong settings:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

Hai repository groups khác nhau:
- **pluginManagement.repositories** phục vụ phân giải plugins theo plugin IDs/markers.
- **dependencyResolutionManagement.repositories** phục vụ phân giải các module dependencies của projects.

Nếu thêm Maven Central chỉ ở dependencyResolutionManagement, điều đó **không bảo đảm** một custom Settings plugin được tìm thấy theo plugins DSL. Ngược lại, gradlePluginPortal không tự là repository của toàn bộ project libraries.

### 3.5. apply plugin: ... khác plugins DSL

Trong Groovy, cú pháp cũ:

~~~groovy
apply plugin: 'dev.example.project-greeting'
~~~

có thể áp plugin khi implementation đã có trên script classpath hoặc được resolve phù hợp. Tuy nhiên, trong project mới, **plugins { id '...' }** thường rõ ràng và dễ quản lý plugin resolution/versioning hơn.

Trong settings plugin tương tự cần đảm bảo target đúng. Không dùng legacy apply để cố né lỗi target mismatch: một implementation của Plugin<Project> vẫn không phù hợp với Settings.

---

## 4. Bảng so sánh Project plugin và Settings plugin

| Câu hỏi | Plugin<Project> | Plugin<Settings> |
| --- | --- | --- |
| Generic type | **Project** | **Settings** |
| Method apply | **apply(Project project)** | **apply(Settings settings)** |
| Vị trí áp dụng thông thường | **build.gradle(.kts)** | **settings.gradle(.kts)** |
| Thời điểm chính | Configuration | Initialization |
| TaskContainer của project | Truy cập trực tiếp qua project.tasks | Không có TaskContainer trực tiếp trên Settings |
| Đăng ký JavaCompile/Test tasks | Phù hợp | Không phải nhiệm vụ trực tiếp |
| Tạo extension DSL | Có, trên Project | Có, trên Settings |
| include subprojects | Không phải scope chính | Có, **settings.include** |
| includeBuild composite | Không phải scope chính | Có, **settings.includeBuild** |
| Plugin repository policy | Thông thường do settings quy định | Có thể cấu hình ở Settings |
| Project dependency declarations | Có, qua Project | Không trực tiếp thay dependencies của mọi project |
| Áp dụng rộng tới nhiều modules | Cần áp plugin ở từng Project | Một Settings plugin cho một build |
| Tự chạy tasks khi apply | Không | Không |
| Áp từ plugin JAR | Có | Có |
| Có thể cùng nằm trong một JAR | Có | Có |
| Nhận sai target type | Lỗi plugin application | Lỗi plugin application |

Điểm then chốt: **Một Settings plugin dùng cho toàn build không đồng nghĩa nó trực tiếp cấu hình mọi Project**. Nó cấu hình Settings và những policies/build layout thuộc Settings. Các task/dependency settings của từng Project nên để Project plugins xử lý.

---

## 5. Thiết kế lab: hai plugin IDs, hai target types

Chúng ta tạo hai Java binary plugins trong một included build **plugin-build**:

1. **dev.example.settings-greeting** → **SettingsGreetingPlugin implements Plugin<Settings>**.
2. **dev.example.project-greeting** → **ProjectGreetingPlugin implements Plugin<Project>**.

Settings plugin đặt một extra property tên **dev.example.scope** trên Settings. Sau khi áp nó, settings.gradle sẽ in marker.

Project plugin đăng ký một task **helloProject** kiểu **GreetingTask** (DefaultTask subclass), dùng Gradle Property<String> và @TaskAction để in tên project path.

Khi chạy từ root lab:

~~~bash
./gradlew -q helloProject
~~~

stdout đáng tin là:

~~~text
SETTINGS_PLUGIN_MARKER=settings
PROJECT_PLUGIN_OK path=:
~~~

**Hai dòng là output do settings script và task action in**. Dòng đầu xuất hiện trong initialization; dòng sau trong task execution. Điều kiện: đã tạo đúng các files bên dưới, Gradle Wrapper và JDK tương thích, không có plugin khác thêm output hoặc lỗi trước execution.

### 5.1. Cấu trúc thư mục đầy đủ

~~~text
gradle-plugin-scope-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── plugin-build/
    ├── settings.gradle
    ├── build.gradle
    └── src/main/java/dev/example/plugins/
        ├── GreetingTask.java
        ├── ProjectGreetingPlugin.java
        └── SettingsGreetingPlugin.java
~~~

**Wrapper** phải được Gradle tạo hoặc lấy từ nguồn tin cậy; đoạn văn này không tạo file JAR bằng tay. Java source phải lưu đúng tên file và package để compiler tìm được class.

### 5.2. plugin-build/settings.gradle

~~~groovy
rootProject.name = 'plugin-build'
~~~

Đây là **settings của included plugin build**, khác settings của consuming build. Nó độc lập và có thể compile riêng khi dùng Gradle Wrapper/cài đặt Gradle phù hợp.

### 5.3. plugin-build/build.gradle

~~~groovy
plugins {
    id 'java-gradle-plugin'
}

group = 'dev.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

gradlePlugin {
    plugins {
        projectGreeting {
            id = 'dev.example.project-greeting'
            implementationClass =
                    'dev.example.plugins.ProjectGreetingPlugin'
        }

        settingsGreeting {
            id = 'dev.example.settings-greeting'
            implementationClass =
                    'dev.example.plugins.SettingsGreetingPlugin'
        }
    }
}
~~~

**java-gradle-plugin** là core Gradle Plugin Development Plugin. Nó:
- Áp Java Library conventions cho plugin implementation.
- Thêm Gradle API dependency cần thiết để compile **Plugin**, **Project**, **Settings**, **DefaultTask**.
- Tạo plugin descriptors trong plugin JAR theo **gradlePlugin.plugins**.
- Cung cấp **validatePlugins** và TestKit integration.
- Khi kết hợp publishing plugins, hỗ trợ plugin marker publications.

Bạn **không phải** tự viết implementation artifact coordinates hoặc META-INF plugin descriptors trong lab. **gradlePlugin** đăng ký cả hai plugin IDs và implementationClass tương ứng.

### 5.4. plugin-build/src/main/java/dev/example/plugins/GreetingTask.java

~~~java
package dev.example.plugins;

import org.gradle.api.DefaultTask;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.TaskAction;

public abstract class GreetingTask extends DefaultTask {
    @Input
    public abstract Property<String> getGreeting();

    @TaskAction
    public void sayGreeting() {
        System.out.println(getGreeting().get());
    }
}
~~~

Đây là Java 17 hợp lệ sử dụng **Gradle-managed abstract Property<String>**. **@Input** giúp Gradle biết task input; **@TaskAction** đánh dấu method execution.

**GreetingTask không cần tự có constructor**. Gradle tạo managed task type, cung cấp implementation của abstract property. Đặt input bằng Provider API trong plugin giúp tách configuration và execution rõ ràng.

### 5.5. plugin-build/src/main/java/dev/example/plugins/ProjectGreetingPlugin.java

~~~java
package dev.example.plugins;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class ProjectGreetingPlugin
        implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        String projectPath = project.getPath();

        project.getTasks().register(
                "helloProject",
                GreetingTask.class,
                task -> {
                    task.setGroup("verification");
                    task.setDescription(
                            "Print a greeting for this Gradle Project"
                    );
                    task.getGreeting().set(
                            "PROJECT_PLUGIN_OK path=" + projectPath
                    );
                }
        );
    }
}
~~~

**projectPath** được lấy khi plugin apply trong configuration phase và ghi thành input string. Task action ở GreetingTask chỉ đọc Property, không truy cập Project object lúc execution, tốt hơn cho configuration cache và isolated task logic so với closure bắt giữ Project rồi đọc tùy ý trong doLast.

Vì plugin áp ở root project, **project.getPath() = ":"**. Nếu áp ở subproject :app, path sẽ là **:app** và task được đăng ký trong subproject đó.

### 5.6. plugin-build/src/main/java/dev/example/plugins/SettingsGreetingPlugin.java

~~~java
package dev.example.plugins;

import org.gradle.api.Plugin;
import org.gradle.api.initialization.Settings;

public final class SettingsGreetingPlugin
        implements Plugin<Settings> {

    @Override
    public void apply(Settings settings) {
        settings.getExtensions()
                .getExtraProperties()
                .set("dev.example.scope", "settings");
    }
}
~~~

**Settings extends ExtensionAware**, nên có **getExtensions()**. Ở đây plugin chỉ đặt một property trên **Settings** để chứng minh target đúng. Nó **không đăng ký Task** và không giả định đã có một Project object cấu hình xong.

Ở dự án thực, Settings plugin có thể thay hành vi này bằng policies ở settings, cấu trúc projects, repositories hoặc plugin resolution theo APIs tương ứng.

### 5.7. gradle-plugin-scope-lab/settings.gradle

~~~groovy
pluginManagement {
    includeBuild('plugin-build')
}

plugins {
    id 'dev.example.settings-greeting'
}

rootProject.name = 'gradle-plugin-scope-lab'

println 'SETTINGS_PLUGIN_MARKER=' +
        extensions.extraProperties.get('dev.example.scope')
~~~

Chú ý **thứ tự**:

1. **pluginManagement.includeBuild** làm plugin implementations khả dụng trong quá trình plugin resolution.
2. **plugins** yêu cầu settings plugin ID, Gradle gọi **apply(Settings)**.
3. **rootProject.name** đặt tên root project.
4. **println** đọc extra property đã được Settings plugin đặt.

Chúng ta cố ý in trong settings script thay vì trong apply() để dễ xác nhận plugin thực sự ảnh hưởng **Settings object**.

### 5.8. gradle-plugin-scope-lab/build.gradle

~~~groovy
plugins {
    id 'dev.example.project-greeting'
}
~~~

Đây là root **Project** build script. Plugin ID thứ hai nhận target Project và đăng ký task **helloProject**. Không cần thêm buildscript classpath hoặc version khi local plugin build đã được đưa vào pluginManagement.

### 5.9. Chạy lab trên Linux/macOS

~~~bash
./gradlew -q helloProject
~~~

Stdout:

~~~text
SETTINGS_PLUGIN_MARKER=settings
PROJECT_PLUGIN_OK path=:
~~~

Chạy chỉ **help**:

~~~bash
./gradlew -q help
~~~

Stdout do lab in:

~~~text
SETTINGS_PLUGIN_MARKER=settings
~~~

**helloProject không tự chạy khi gọi help**. Settings plugin vẫn áp vào mỗi configuration invocation thông thường; task do Project plugin đăng ký không phải lúc nào cũng được chọn để execute.

### 5.10. Chạy lab trên Windows PowerShell

~~~powershell
.\gradlew.bat -q helloProject
.\gradlew.bat -q help
~~~

Hai lệnh dùng cùng Gradle scripts và Java code. Nếu báo không tìm thấy Java 17 toolchain, kiểm tra:

~~~powershell
.\gradlew.bat -q javaToolchains
~~~

**Lưu ý:** tại build chưa có task javaToolchains từ Java toolchain configuration plugin, lệnh có thể khác theo Gradle; cách phổ biến được tài liệu Gradle nêu là **./gradlew -q javaToolchains** khi toolchain tooling được áp. Nếu task không tồn tại, dùng **java -version**, **./gradlew --version** và kiểm tra JDK installation trong Gradle settings.

### 5.11. Quan sát task và plugin metadata

~~~bash
./gradlew tasks --all
./gradlew :plugin-build:validatePlugins
./gradlew :plugin-build:pluginDescriptors
./gradlew :plugin-build:jar
~~~

**plugin-build** là included plugin build, nên từ composite root có thể gọi những tasks của nó qua build-tree paths. Tên build path phụ thuộc included build identity; lab dùng plugin-build.

Plugin JAR có thể chứa descriptors kiểu:

~~~text
META-INF/gradle-plugins/dev.example.project-greeting.properties
META-INF/gradle-plugins/dev.example.settings-greeting.properties
~~~

Các descriptors liên kết plugin ID với implementationClass. Đó là metadata giúp Gradle gọi đúng class khi plugin được apply.

### 5.12. Mã Java 17 tối giản để hiểu type safety ngoài Gradle

Đây là **chương trình Java độc lập**, không cần Gradle API, minh họa generic Plugin<T> bằng interface tự định nghĩa khác tên:

File **ScopeDemo.java**:

~~~java
public final class ScopeDemo {
    interface Action<T> {
        void apply(T target);
    }

    static final class ProjectScope {
        String name() {
            return "project";
        }
    }

    static final class SettingsScope {
        String name() {
            return "settings";
        }
    }

    public static void main(String[] args) {
        Action<ProjectScope> projectAction =
                target -> System.out.println(
                        "PROJECT " + target.name()
                );

        Action<SettingsScope> settingsAction =
                target -> System.out.println(
                        "SETTINGS " + target.name()
                );

        projectAction.apply(new ProjectScope());
        settingsAction.apply(new SettingsScope());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 ScopeDemo.java
java ScopeDemo
~~~

Stdout chính xác:

~~~text
PROJECT project
SETTINGS settings
~~~

Đây **không phải implementation Gradle plugin**, chỉ minh họa type parameter. Bạn không thể truyền SettingsScope cho projectAction ở compile-time nếu dùng types đúng, tương tự lý do nên chọn đúng Plugin<Project> hoặc Plugin<Settings>.

---

## 6. Vì sao một JAR có thể chứa hai plugin?

Gradle **plugin artifact** và **plugin application** là hai khái niệm:

- Artifact: JAR chứa classes, plugin descriptors và resources.
- Plugin ID: tên định danh logic để người tiêu thụ yêu cầu plugin.
- Implementation class: class thực hiện một Plugin<T> cụ thể.
- Application target: đối tượng thật mà Gradle truyền vào apply().

Trong lab:

~~~text
plugin-build.jar
  ├── dev/example/plugins/GreetingTask.class
  ├── dev/example/plugins/ProjectGreetingPlugin.class
  ├── dev/example/plugins/SettingsGreetingPlugin.class
  └── META-INF/gradle-plugins/
       ├── dev.example.project-greeting.properties
       └── dev.example.settings-greeting.properties
~~~

**Một JAR** nhưng **hai IDs**:

| ID | Implementation | Target |
| --- | --- | --- |
| dev.example.project-greeting | ProjectGreetingPlugin | Project |
| dev.example.settings-greeting | SettingsGreetingPlugin | Settings |

Khi settings.gradle yêu cầu settings-greeting, Gradle không tự chạy project-greeting dù chúng ở cùng JAR. Muốn dùng cả hai, áp rõ chúng ở đúng script contexts.

### 6.1. Tại sao không dùng một Plugin<Object> cho cả hai?

Bạn có thể cố viết một plugin nhận **Object** rồi kiểm tra instanceof Settings/Project. Nhưng cách này:
- Mất kiểu target rõ và IDE/static type safety.
- Tăng branch logic cho hai lifecycle khác nhau.
- Dễ gọi API khi target chưa sẵn sàng.
- Làm plugin contract khó hiểu cho người dùng.
- Gây khó khăn khi viết functional tests và error messages.

Khi thật sự cần hai scopes, **hai plugin implementation classes** có thể chia sẻ utility classes nội bộ mà vẫn giữ target types đúng.

### 6.2. Có thể implement cả Plugin<Project> và Plugin<Settings> trên một class?

Java không cho một class trực tiếp implement hai instantiations khác nhau của cùng generic interface theo cách đơn giản vì **type erasure** và xung đột inherited interfaces. Đừng tìm workaround bằng raw Plugin hoặc reflection chỉ để dùng một plugin ID. Tách classes theo mục đích.

### 6.3. Phân biệt plugin ID và tên class

~~~groovy
gradlePlugin {
    plugins {
        settingsGreeting {
            id = 'dev.example.settings-greeting'
            implementationClass =
                    'dev.example.plugins.SettingsGreetingPlugin'
        }
    }
}
~~~

**settingsGreeting** là tên entry trong container gradlePlugin.plugins. **dev.example.settings-greeting** là ID consumer áp. **dev.example.plugins.SettingsGreetingPlugin** là fully qualified Java class name phải tồn tại trong compiled artifact. Không hoán đổi ba khái niệm.

---

## 7. Áp sai target và lỗi thường gặp

### 7.1. Sai: Project plugin trong settings.gradle

~~~groovy
plugins {
    id 'dev.example.project-greeting'
}
~~~

Nếu đặt block này trong **settings.gradle**, plugin implementation cần **Plugin<Project>** nhưng Gradle cung cấp **Settings**. Kết quả là **plugin application failure**; thông điệp có thể biểu hiện ClassCastException hoặc lỗi target-type tương ứng tùy Gradle version.

**Không chữa bằng cách thêm project('...') vào settings.** Chuyển plugin ID sang **build.gradle** của Project cần áp.

### 7.2. Sai: Settings plugin trong build.gradle

~~~groovy
plugins {
    id 'dev.example.settings-greeting'
}
~~~

Nếu đặt trong **build.gradle**, Gradle áp vào **Project** nhưng implementation yêu cầu **Settings**. Chuyển vào settings.gradle, hoặc tạo Project plugin riêng nếu công việc thật sự thuộc Project.

### 7.3. Sai: Dùng apply để giải quyết target mismatch

~~~groovy
apply plugin: 'dev.example.settings-greeting'
~~~

đặt trong build.gradle vẫn là apply vào Project. **apply plugin:** không phải lệnh ép target thành Settings.

### 7.4. Sai: Project plugin muốn include subproject muộn

~~~java
// Concept sai về phạm vi:
public void apply(Project project) {
    // Không có project.include(...) như Settings.
}
~~~

Hãy dùng Settings plugin hoặc chính settings.gradle để **include(...)** khi định nghĩa build layout. Đừng dùng callbacks cấu hình chéo để cố thay cấu trúc sau khi projects đã tạo.

### 7.5. Sai: Settings plugin muốn đăng ký tasks trực tiếp

~~~java
// Không hợp lệ:
settings.getTasks().register("hello");
~~~

Settings không cung cấp **TaskContainer** của Project như vậy. Tạo Project plugin cho task.

### 7.6. Sai: plugin class đúng nhưng descriptor khai báo nhầm implementation

Nếu **settingsGreeting** trỏ tới **ProjectGreetingPlugin**, settings application sẽ nhận sai target. Vì vậy test cả **plugin ID → implementation class → target type**. Plugin class compile được không có nghĩa runtime application đúng.

---

## 8. Project plugin chỉ có scope của Project được áp

### 8.1. Root project không đồng nghĩa mọi subproject

Root settings:

~~~groovy
rootProject.name = 'company-app'
include 'api', 'service'
~~~

Root build.gradle:

~~~groovy
plugins {
    id 'dev.example.project-greeting'
}
~~~

Điều này đăng ký **:helloProject** trên root, **không tự tạo :api:helloProject** và **:service:helloProject**.

Nếu muốn **api** cũng có task, áp plugin trong **api/build.gradle**:

~~~groovy
plugins {
    id 'dev.example.project-greeting'
}
~~~

### 8.2. Convention plugin có thể áp vào từng module

Với đa module, một cách rõ là khai báo plugin ID trong build.gradle của mỗi module tương ứng. Nếu cùng muốn Java rules, plugin<Project> có thể:

~~~java
@Override
public void apply(Project project) {
    project.getPluginManager().apply("java-library");
    // Cấu hình convention Java trong Project này.
}
~~~

Đây chỉ là fragment, chưa phải Java source độc lập. Nó thể hiện **Project plugin** có thể apply core Java plugin cho chính Project của nó.

Không cần root dùng **subprojects { ... }** để áp plugin khắp nơi nếu mỗi module có build.gradle rõ ràng. Các patterns cấu hình chéo có thể làm configuration cache/isolated projects khó xử lý.

### 8.3. Khi muốn áp ở mọi project

Có những cách:
- Mỗi project khai báo convention plugin ID của mình.
- Convention plugin được gói trong build-logic included build.
- Repository scaffold/module generator tạo build scripts nhất quán.

Chọn cách mang tính **opt-in/ownership** phù hợp. Đừng nói rằng một Plugin<Settings> là giải pháp để tự thêm tất cả Java tasks vào mọi project; Settings plugin không quản lý TaskContainer trực tiếp.

### 8.4. Plugin.apply không tự chạy tasks của subproject

Ngay cả khi áp plugin vào ba projects, task **helloProject** được đăng ký tại ba TaskContainers khác nhau. Lệnh **./gradlew :api:helloProject** chạy riêng task của :api. Với root **:helloProject**, Gradle chỉ chạy task root trừ khi task graph được cấu hình phụ thuộc các tasks khác.

### 8.5. Configuration avoidance

Ưu tiên:

~~~java
project.getTasks().register(
        "helloProject",
        GreetingTask.class,
        task -> task.getGreeting().set("Hello")
);
~~~

hơn việc eager **create(...)** và cấu hình sớm mọi task. **tasks.register** trả TaskProvider; task được realized khi cần. Đây là thói quen tốt cho plugin performance, especially multi-project builds.

---

## 9. Settings plugin dùng để quản lý cấu trúc và chính sách

### 9.1. Include project theo cấu hình

Ví dụ Settings plugin muốn thêm một module đã có thư mục nguồn:

~~~java
@Override
public void apply(Settings settings) {
    settings.include("shared");
}
~~~

Đây là fragment mang tính mô hình; chỉ chạy khi thư mục **shared/** thật sự tồn tại và có cấu hình hợp lệ. Nó minh họa công việc phù hợp với Settings target.

**Không** làm việc này trong Project plugin rồi kỳ vọng build layout thay đổi.

### 9.2. Settings.getRootProject là ProjectDescriptor

Ví dụ:

~~~java
settings.getRootProject().setName("company-platform");
~~~

Dòng này cấu hình tên root project descriptor; nó không tương đương **Project.setName** trên một Project đã cấu hình. Settings quản lý project hierarchy trước khi Project objects được cấu hình.

### 9.3. Repository policy ở Settings

Trong **settings.gradle**:

~~~groovy
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

Tương tự, Settings plugin có thể sử dụng typed Settings API để thiết lập repository policy và rules khi thời điểm phù hợp. Trong tổ chức có dependency governance, nên centralize và review policies.

**Phân biệt:** pluginManagement repositories tìm plugin implementations; dependencyResolutionManagement repositories tìm project module dependencies.

### 9.4. Đừng ép pluginManagement muộn

Plugin resolution phải biết repositories/versions/build-logic đủ sớm. Một Settings plugin đã được resolve không thể “quay ngược thời gian” để giúp bản thân nó được tìm thấy bằng repository vừa cấu hình ở cuối settings.

Với plugin local dùng trong chính settings script, pattern rõ nhất là:

~~~groovy
pluginManagement {
    includeBuild('plugin-build')
}

plugins {
    id 'dev.example.settings-greeting'
}
~~~

### 9.5. Cân nhắc hiệu suất của early build logic

Settings plugin build cần sẵn sàng trước khi Settings được đánh giá. Nếu nhét tất cả các Project convention plugins nặng vào cùng một included build dùng cho Settings, Gradle có thể phải chuẩn bị nhiều build logic hơn từ rất sớm. Gradle best practices khuyến nghị cân nhắc **một minimal included build cho Settings plugins**, tách khỏi những project convention plugins phức tạp nếu performance đáng kể.

Lab gói chung hai plugins để dễ học, nhưng repository lớn có thể chọn:

~~~text
build-logic-settings/    # Plugin<Settings>, nhỏ và khởi động sớm
build-logic-projects/    # Plugin<Project> / convention plugins
~~~

Đây là khuyến nghị kiến trúc theo nhu cầu, không phải bắt buộc mọi build phải chia đôi.

---

## 10. Binary plugins, precompiled script plugins và script plugins

### 10.1. Binary plugin bằng Java

Lab đang dùng Java class:

~~~java
public final class ProjectGreetingPlugin
        implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        // ...
    }
}
~~~

Ưu điểm:
- Target type rõ.
- Compiler kiểm tra API.
- Có thể đóng JAR/publish.
- Unit/functional tests thuận tiện.
- Phù hợp build logic có xử lý phức tạp.

### 10.2. Precompiled script plugin

Gradle cho phép precompiled script plugins trong **buildSrc** hoặc included build. File suffix quyết định target:

| File precompiled script | Plugin scope |
| --- | --- |
| **name.gradle(.kts)** | Project plugin |
| **name.settings.gradle(.kts)** | Settings plugin |
| **name.init.gradle(.kts)** | Gradle/init plugin |

Ví dụ Kotlin DSL files:

~~~text
src/main/kotlin/company-java.gradle.kts
src/main/kotlin/company-settings.settings.gradle.kts
~~~

Chúng phải nằm trong plugin build được cấu hình bằng plugin phát triển precompiled scripts phù hợp. **File suffix quan trọng**: một file **company-java.gradle.kts** không tự trở thành Settings plugin chỉ vì bạn đưa ID của nó vào settings.plugins.

Tên plugin ID phát sinh còn liên quan package/name convention; xem tài liệu Gradle của đúng plugin build version khi dùng precompiled script plugins.

### 10.3. Script plugin

Script plugins đơn giản có thể dùng **apply from:**:

~~~groovy
apply from: 'gradle/legacy-conventions.gradle'
~~~

Nhưng chúng thường khó tái sử dụng/test/kiểm soát API hơn. Gradle docs khuyến khích dùng precompiled script hoặc binary plugins cho build logic production. Script plugin không phải giải pháp thay target type mismatch.

### 10.4. Lựa chọn theo độ phức tạp

| Nhu cầu | Phương án thích hợp |
| --- | --- |
| Một đoạn cấu hình thử nghiệm ngắn | Inline script trong build/settings |
| Bộ conventions Java lặp giữa modules | Precompiled Project convention plugin |
| Build initialization/repository policy chung | Precompiled Settings plugin hoặc Plugin<Settings> |
| Logic Java phức tạp, custom task type | Binary Plugin<Project> |
| Cấu trúc settings đặc biệt, plugin resolution logic | Binary Plugin<Settings> |
| Tooling toàn máy, init scripts | Plugin<Gradle> khi thật sự cần |

Đừng cố ép mọi công việc vào **Plugin<Settings>** chỉ vì muốn “áp một lần cho cả build”. Một Plugin<Project> được áp có chủ đích ở từng module thường là thiết kế rõ hơn.

---

## 11. Thêm khả năng cấu hình bằng extension đúng scope

### 11.1. Project extension

Một Project plugin có thể đăng ký extension:

~~~java
project.getExtensions().create(
        "greeting",
        GreetingExtension.class
);
~~~

Sau đó consumer cấu hình:

~~~groovy
greeting {
    // Các properties của Project extension.
}
~~~

Đây là fragment; để runnable cần class **GreetingExtension** với managed properties phù hợp. Nếu muốn task dùng configuration ấy, task nên đọc **Provider** thay vì giá trị tùy tiện tại execution.

### 11.2. Settings extension

Một Settings plugin cũng có **settings.getExtensions()**. Extension được thêm vào **Settings object**, nên người dùng cấu hình trong **settings.gradle**, không phải **build.gradle**:

~~~groovy
settingsGreetingPolicy {
    // Cấu hình extension nếu Settings plugin công bố nó.
}
~~~

Đoạn trên minh họa vị trí cấu hình, không phải phần của lab vì lab chỉ đặt một ExtraProperty marker thay vì định nghĩa settingsGreetingPolicy.

### 11.3. Tên extension giống nhau không làm chia sẻ trạng thái

Nếu Settings và Project đều có extension tên **greeting**, chúng vẫn là hai objects khác nhau trên hai plugin targets khác nhau. Một value đặt ở Settings extension không tự xuất hiện trong Project extension.

Nếu project build logic cần một policy thiết lập từ Settings, hãy thiết kế một hợp đồng rõ hoặc convention distribution phù hợp, tránh đọc ngầm Settings.extraProperties từ Project task actions.

### 11.4. Provider API

Trên Task:

~~~java
@Input
public abstract Property<String> getGreeting();
~~~

và ở plugin:

~~~java
task.getGreeting().set("PROJECT_PLUGIN_OK path=" + projectPath);
~~~

Đây là cách biểu diễn input rõ, có thể được Gradle snapshot để hỗ trợ up-to-date checks/configuration cache. Không lưu global mutable static settings rồi đọc từ TaskAction nếu muốn build cô lập/tái lập.

---

## 12. Publishing và plugin marker artifacts

### 12.1. Plugin ID và binary coordinates

Với plugins DSL, Gradle có thể tìm **plugin marker artifact** theo convention:

~~~text
plugin.id : plugin.id.gradle.plugin : plugin.version
~~~

Marker artifact dẫn Gradle tới implementation artifact. **java-gradle-plugin** tự sinh descriptors và hỗ trợ cấu hình marker publications khi áp publishing plugins phù hợp.

Trong lab, **pluginManagement.includeBuild('plugin-build')** dùng plugin implementation từ included build local. Bạn không cần publish marker lên remote repository.

### 12.2. Khi publish ra Maven repository

Trong plugin-build/build.gradle có thể thêm plugin:

~~~groovy
plugins {
    id 'java-gradle-plugin'
    id 'maven-publish'
}
~~~

Và cấu hình:

~~~groovy
publishing {
    repositories {
        maven {
            url = layout.buildDirectory.dir('published-repo')
        }
    }
}
~~~

Đây là **fragment** cần ghép với full gradlePlugin/group/version từ lab. Nó cho phép publish metadata vào repository local để kiểm nghiệm. Không tự upload lên Plugin Portal; muốn publish Portal cần plugin/cấu hình/credentials và quy trình duyệt tương ứng.

### 12.3. Plugin marker thiếu thì chuyện gì xảy ra?

Nếu tự publish chỉ implementation JAR mà không có marker cho ID, consumer dùng **plugins { id ... version ... }** có thể không resolve theo plugin ID. Cách sửa là publish marker qua java-gradle-plugin/maven-publish hoặc cấu hình **pluginManagement.resolutionStrategy** tương ứng khi có lý do.

Không đổi target type để chữa missing marker. Đây là hai lỗi khác nhau: plugin resolution và plugin application.

### 12.4. Version trong local included build

Khi apply plugin local qua **includeBuild trong pluginManagement**, plugin IDs được tìm trong included build mà không cần version trong consumer plugins block:

~~~groovy
plugins {
    id 'dev.example.settings-greeting'
}
~~~

Nếu plugin được publish vào repository, người dùng thường pin version:

~~~groovy
plugins {
    id 'dev.example.settings-greeting' version '1.0.0'
}
~~~

Ví dụ version này chỉ minh họa cách viết, không ngụ ý plugin công khai tồn tại. Với production, dùng plugin version catalog/policy hoặc pluginManagement versions theo tiêu chuẩn team.

---

## 13. Functional testing với Gradle TestKit

Lý tưởng nhất, plugin cần tests không chỉ kiểm tra apply() trả về, mà còn phải chạy một Gradle build thật để xác nhận đúng target và plugin resolution.

### 13.1. Vì sao cần TestKit?

**ProjectBuilder** có thể hỗ trợ một số tests tại configuration level nhưng không mô phỏng trọn đời thực Gradle build. **GradleRunner** của **Gradle TestKit** chạy một build thực trong thư mục tạm, có thể:

- Tạo settings.gradle và build.gradle fixtures.
- Áp Settings plugin trong Settings phase.
- Áp Project plugin trong Project phase.
- Chạy helloProject.
- Assert đúng output và task result.
- Kiểm tra trường hợp apply sai target có build failure đúng.

### 13.2. Thêm JUnit Jupiter cho plugin-build tests

Trong **plugin-build/build.gradle**, thêm:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**java-gradle-plugin** tự thêm dependency TestKit cho test source set mặc định; JUnit framework vẫn cần khai báo. Fragment này cần được chèn vào file plugin-build/build.gradle ở lab, không phải file standalone.

### 13.3. Test Java 17 đầy đủ: PluginScopeFunctionalTest.java

Tạo **plugin-build/src/test/java/dev/example/plugins/PluginScopeFunctionalTest.java**:

~~~java
package dev.example.plugins;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertTrue;

public final class PluginScopeFunctionalTest {
    @TempDir
    Path projectDirectory;

    @Test
    void settingsAndProjectPluginsApplyToCorrectTargets()
            throws IOException {

        Files.writeString(
                projectDirectory.resolve("settings.gradle"),
                "plugins { id 'dev.example.settings-greeting' }\n" +
                "rootProject.name = 'test-consumer'\n" +
                "println 'SETTINGS_PLUGIN_MARKER=' + " +
                "extensions.extraProperties.get('dev.example.scope')\n",
                StandardCharsets.UTF_8
        );

        Files.writeString(
                projectDirectory.resolve("build.gradle"),
                "plugins { id 'dev.example.project-greeting' }\n",
                StandardCharsets.UTF_8
        );

        BuildResult result = GradleRunner.create()
                .withProjectDir(projectDirectory.toFile())
                .withArguments("--quiet", "helloProject")
                .withPluginClasspath()
                .build();

        assertTrue(
                result.getOutput()
                        .contains("SETTINGS_PLUGIN_MARKER=settings")
        );
        assertTrue(
                result.getOutput()
                        .contains("PROJECT_PLUGIN_OK path=:")
        );
    }
}
~~~

**Vì sao runnable?**
- JUnit Jupiter được khai báo ở testImplementation.
- Gradle TestKit classpath được Plugin Development Plugin tích hợp.
- **withPluginClasspath()** thêm plugin under test vào build fixture.
- Fixture settings.gradle áp đúng Settings plugin.
- Fixture build.gradle áp đúng Project plugin.
- Task **helloProject** in marker từ Java task class.
- Test kiểm tra các markers nhưng không phụ thuộc toàn bộ Gradle console logs.

**Lưu ý:** GradleRunner là một build riêng chạy qua Gradle Tooling API. Nó không tự dùng settings.gradle của plugin-build hay root composite lab. Với TestKit automatic classpath injection, cách áp plugin ở fixture dùng plugins DSL như ví dụ. Nếu plugin under test có compileOnly dependency vào API của plugin ngoài, TestKit classpath có thể thiếu; khi đó cần test fixture repository/publishing setup riêng theo docs.

### 13.4. Chạy test

Linux/macOS, từ root lab:

~~~bash
./gradlew :plugin-build:test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :plugin-build:test
~~~

**Kết quả kỳ vọng:** Gradle TestKit test không fail assertion, task :plugin-build:test thành công. Log task Test có thể ghi XML/HTML report trong plugin-build/build/reports/tests/test/ tùy Gradle version.

### 13.5. Test trường hợp sai target

Một functional test bổ sung có thể tạo fixture:

~~~groovy
// settings.gradle - CỐ Ý SAI:
plugins {
    id 'dev.example.project-greeting'
}
~~~

và gọi **GradleRunner.buildAndFail()** để xác nhận plugin application thất bại. Tương tự áp settings plugin trong build.gradle để kiểm tra lỗi sai target. Không assert nguyên văn stacktrace vì thông điệp có thể thay đổi theo Gradle version; assert dấu hiệu lỗi target và plugin ID/class khi có thể.

### 13.6. Kiểm tra validatePlugins

~~~bash
./gradlew :plugin-build:validatePlugins
~~~

Task này kiểm tra task property annotations/Gradle API patterns như **@Input**, **@OutputFile**, **@Internal** khi thích hợp. **validatePlugins PASS không thay thế TestKit**: plugin descriptor có thể hợp lệ nhưng người dùng vẫn áp sai target.

### 13.7. Tách test fixtures giữa hai scope

Với dự án plugin lớn, tạo hai nhóm tests:
- **SettingsPluginFunctionalTest**: fixture settings.gradle, include/repository policy, plugin resolution.
- **ProjectPluginFunctionalTest**: fixture build.gradle, task registration, Provider inputs, Java task graph.

Mỗi nhóm kiểm tra đúng lifecycle mình sở hữu. Một test chạy mọi thứ có thể che lỗi nhờ fixtures tình cờ cấu hình sẵn.

---

## 14. Những tình huống kiến trúc thực tế

### 14.1. Thiết lập Java toolchain mặc định cho một module

**Plugin<Project>** phù hợp:

~~~java
@Override
public void apply(Project project) {
    project.getPluginManager().apply("java");
    // Cấu hình JavaPluginExtension của Project này.
}
~~~

Fragment này cho thấy plugin tự áp Java plugin rồi cấu hình toolchain/compile tasks của Project. Nó không phù hợp với Plugin<Settings> vì Settings không phải Project target và không có JavaPluginExtension của mọi subproject.

### 14.2. Tự include các module theo cấu trúc repository

**Plugin<Settings>** phù hợp:

~~~java
@Override
public void apply(Settings settings) {
    settings.include("app", "shared");
}
~~~

Cần có đúng project directories. Nếu repository thay cấu trúc, Settings plugin phải quản lý project descriptors minh bạch. Không tự scan filesystem không kiểm soát rồi thay build layout mà team không biết.

### 14.3. Cấu hình repository policy tập trung

**Plugin<Settings>** phù hợp để cấu hình dependencyResolutionManagement, pluginManagement hoặc repositoriesMode theo Settings API và policy tổ chức.

Một Project plugin có thể cấu hình repositories của Project, nhưng không thể thay thế hoàn toàn repository policy tại initialization, đặc biệt khi team dùng FAIL_ON_PROJECT_REPOS để ngăn repository khai báo rải rác.

### 14.4. Tạo task kiểm tra kiến trúc dependency

**Plugin<Project>** có thể đăng ký custom verification task, lấy project dependency metadata qua providers/tasks khi cần, và nối vào check lifecycle nếu Java/base plugin hiện hữu. Settings plugin có thể chọn các projects nào xuất hiện, nhưng task logic nên nằm trong Project plugin.

### 14.5. Cấu hình composite build

**Settings** có API includeBuild và pluginManagement.includeBuild. Plugin<Project> trong app/build.gradle không thích hợp để “lúc này mới add included build rồi resolve plugin trong settings”.

### 14.6. Build scans và enterprise policies

Plugin dùng cho tooling toàn build có thể có target Settings hoặc Gradle tùy API và giai đoạn cần hook, không mặc nhiên là Project. Đọc interface plugin thực tế thay vì đoán chỉ từ tên “enterprise” hay “build”.

### 14.7. Plugin cần áp cả settings và project behavior

Một thiết kế tốt có thể dùng **hai IDs**:
- **company.settings-policy**: Plugin<Settings>, đặt repositories/project include policy.
- **company.java-conventions**: Plugin<Project>, đặt Java toolchain, tasks, dependencies.

Cả hai có thể publish chung hoặc riêng, nhưng consumer cần áp đúng nơi. Không cố làm Plugin<Settings> gọi Project tasks trực tiếp ở initialization.

---

## 15. Kotlin DSL áp dụng tương đương

Java implementation classes **không thay đổi** khi consuming build chuyển từ Groovy sang Kotlin DSL. Chỉ cú pháp các Gradle script files thay đổi.

### 15.1. plugin-build/build.gradle.kts

~~~kotlin
plugins {
    id("java-gradle-plugin")
}

group = "dev.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}

gradlePlugin {
    plugins {
        create("projectGreeting") {
            id = "dev.example.project-greeting"
            implementationClass =
                "dev.example.plugins.ProjectGreetingPlugin"
        }

        create("settingsGreeting") {
            id = "dev.example.settings-greeting"
            implementationClass =
                "dev.example.plugins.SettingsGreetingPlugin"
        }
    }
}
~~~

### 15.2. Consumer settings.gradle.kts

~~~kotlin
pluginManagement {
    includeBuild("plugin-build")
}

plugins {
    id("dev.example.settings-greeting")
}

rootProject.name = "gradle-plugin-scope-lab"

println(
    "SETTINGS_PLUGIN_MARKER=" +
        extensions.extraProperties.get("dev.example.scope")
)
~~~

### 15.3. Consumer build.gradle.kts

~~~kotlin
plugins {
    id("dev.example.project-greeting")
}
~~~

Lệnh chạy:

~~~bash
./gradlew -q helloProject
~~~

Stdout như Groovy lab:

~~~text
SETTINGS_PLUGIN_MARKER=settings
PROJECT_PLUGIN_OK path=:
~~~

### 15.4. Kotlin với subprojects

Trong **api/build.gradle.kts**:

~~~kotlin
plugins {
    id("dev.example.project-greeting")
}
~~~

Project path của task là **:api** nếu settings đã include api; khi chạy:

~~~bash
./gradlew -q :api:helloProject
~~~

Task line:

~~~text
PROJECT_PLUGIN_OK path=:api
~~~

Nếu settings vẫn có println marker, console còn có SETTINGS_PLUGIN_MARKER=settings trước đó; đây là một biến thể mở rộng, không phải file layout cơ bản của mục 5.

### 15.5. Kotlin plugin scope không thay đổi

Cú pháp:

~~~kotlin
plugins {
    id("dev.example.settings-greeting")
}
~~~

**vẫn sai** nếu đặt trong build.gradle.kts. Kotlin DSL có type-safe accessors nhưng plugin application target được quyết định bởi script context, không phải bởi kiểu chuỗi id.

---

## 16. Configuration cache và hiệu năng

### 16.1. Không làm việc nặng trong apply()

Tránh:
- Ghi output file vào buildDirectory trong apply.
- Chạy Java compiler hoặc process bên ngoài trong apply.
- Duyệt toàn bộ file tree rồi tự load nội dung vào global mutable state.
- Kết nối network mỗi khi plugin được apply.
- Cấu hình eager hàng ngàn tasks mà không cần.

Thay vào đó, đăng ký tasks/Providers ở configuration, để task actions thực hiện công việc khi được Gradle chọn.

### 16.2. Task type với Property và @Input

Lab dùng:

~~~java
@Input
public abstract Property<String> getGreeting();
~~~

và:

~~~java
@TaskAction
public void sayGreeting() {
    System.out.println(getGreeting().get());
}
~~~

TaskAction đọc một Gradle-managed Property thay vì đọc Project mutable model. Đây là pattern phù hợp với configuration cache hơn kiểu closure doLast bắt giữ Project/Gradle. Muốn cacheable task outputs, cần khai báo output properties và bảo đảm reproducibility, chứ không chỉ có @Input là auto cacheable.

### 16.3. Project plugin chỉ đăng ký task cần thiết

~~~java
project.getTasks().register("helloProject", GreetingTask.class, ...);
~~~

**register** là lazy API. Đừng gọi **get()** hoặc **tasks.all** sớm chỉ vì muốn đảm bảo task xuất hiện trong danh sách. Với nhiều modules, eager configuration có thể làm chậm configuration phase.

### 16.4. Settings plugin tối giản

Settings plugin chạy rất sớm. Một Settings plugin phụ thuộc nhiều project convention plugins nặng có thể tăng chi phí startup/build logic. Tách minimal settings plugin build khi cần và kiểm tra hiệu năng bằng profiler/build scans theo policy.

### 16.5. Không truy cập rootProject mutable model từ TaskAction

Trong Project plugin, đọc **project.getPath()** trong apply và set thành input như lab. Không nên:

~~~java
// ANTI-PATTERN - chỉ minh họa:
task.doLast(t ->
        System.out.println(project.getPath())
);
~~~

khi mục tiêu là task có thể cô lập và cache configuration; nó bắt giữ Project trong execution action và dễ vi phạm configuration cache requirements.

### 16.6. Plugin.apply nhiều lần?

Gradle PluginManager thường tránh apply lại cùng plugin ID vào cùng target sau khi nó đã được áp. Tuy nhiên, **mỗi Project** là một target riêng; plugin có thể chạy apply cho :api và :service riêng biệt. Đừng dùng static flag để chặn toàn bộ các Project cùng dùng plugin.

### 16.7. Cấu hình chéo và isolated projects

Modern Gradle hướng tới project isolation, tránh code từ plugin<Project> của root trực tiếp cấu hình các Project objects khác theo cách không hỗ trợ. Dùng convention plugins áp tại từng project và APIs với lifecycle rõ.

Settings plugin là nơi sở hữu build layout/policies chứ không phải nơi chứa một loạt Project object mutations không kiểm soát.

---

## 17. Bảo mật, publishing và version compatibility

### 17.1. Plugin là mã thực thi trong build

Một custom plugin có thể đăng ký tasks, đọc environment/repositories, thay compiler flags và thực thi code trong build process. **Plugin resolution không phải sandbox bảo mật**.

Chỉ include plugin builds tin cậy, kiểm tra source/commit và pin plugin versions khi lấy từ bên ngoài. Không đưa secrets vào stdout của settings hoặc project plugins.

### 17.2. Settings plugin có ảnh hưởng lớn

Settings plugin có thể thay:
- Các modules được include.
- Repositories và resolution rules.
- Plugin resolution policies.
- Build cache/settings governance (khi sử dụng APIs phù hợp).

Sai sót ở Settings plugin có thể khiến toàn build không cấu hình được, khác với một Project plugin chỉ gây lỗi ở module được áp. Vì thế settings plugin cần tests cho clean setup và khả năng recovery.

### 17.3. Plugin binary compatibility với Gradle API

Một plugin compile theo Gradle API version cũ có thể dùng APIs deprecated/removed trong Gradle mới. Một plugin compile thành bytecode Java21 không chạy được nếu Gradle daemon đang chạy trên Java17.

Dùng Gradle Wrapper, compatibility matrix, Java toolchain/release policy và TestKit matrix nếu tổ chức hỗ trợ nhiều Gradle versions.

### 17.4. Plugin IDs phải duy nhất

Plugin ID là hợp đồng cho consumers. Tránh tên mơ hồ hoặc xung đột với core plugins. Đặt namespace tổ chức, ví dụ **dev.example.settings-greeting** và **dev.example.project-greeting** trong lab.

Nếu đổi implementationClass, giữ plugin ID có thể là một thay đổi nội bộ; nhưng nếu đổi target type từ Project sang Settings dưới cùng ID, đó thường là **breaking change** vì người dùng phải đổi script áp plugin.

### 17.5. Publishing không tự bằng việc khai báo gradlePlugin

Block **gradlePlugin.plugins** tạo metadata/descriptors và publication support. Nó không tự đẩy JAR lên Plugin Portal hoặc Maven registry. Publishing cần plugin, repository, credentials và task invocation phù hợp, ví dụ **publish** hoặc **publishPlugins** theo cơ chế được chọn.

---

## 18. Troubleshooting các lỗi điển hình

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **Plugin not found** trong settings | pluginManagement thiếu includeBuild hoặc repo/marker | Đưa includeBuild vào pluginManagement, kiểm tra plugin ID |
| **Plugin not found** trong build.gradle | Plugin build chưa được resolve/publish | Kiểm tra pluginManagement và marker/version |
| **Failed to apply plugin** kèm target mismatch | Plugin<Project> áp vào Settings hoặc ngược lại | Áp đúng script target |
| **ClassCastException** trong apply | Implementation type không khớp target | Kiểm tra Plugin<T> và gradlePlugin.implementationClass |
| **UnknownPluginException** | Plugin ID sai hoặc marker không có | Kiểm tra gradlePlugin.plugins IDs và repositories |
| **ClassNotFoundException implementationClass** | Sai package/class hoặc descriptor | Kiểm tra Java source file path và pluginDescriptors/JAR |
| Settings extra property không tìm thấy | Settings plugin chưa áp hoặc key sai | Kiểm tra plugins block trong settings và property key |
| Task **helloProject** không tồn tại | Project plugin chưa áp vào Project cần gọi | Kiểm tra build.gradle đúng module |
| Task chỉ có ở root, không có ở subprojects | Project scope không tự lan | Áp plugin ở từng subproject |
| Settings plugin không tạo helloProject | Settings không có TaskContainer như Project | Tách Project plugin |
| Project plugin không tạo module mới | Include project thuộc Settings phase | Dùng Settings.include trong settings plugin |
| **pluginManagement not first** | Có logic/block đứng trước pluginManagement | Đưa pluginManagement lên đầu settings |
| Settings plugin includeBuild quá muộn | includeBuild đặt ngoài pluginManagement | Chuyển vào pluginManagement |
| Plugin class build được nhưng apply fail | gradlePlugin entry trỏ class target sai | Sửa implementationClass mapping |
| JDK toolchain missing | Plugin build yêu cầu Java17 nhưng máy không có | Cài JDK hoặc cấu hình provisioning phù hợp |
| Java class file version error | Java bytecode mới hơn JVM chạy Gradle | Align release/JDK theo compatibility matrix |
| validatePlugins PASS nhưng runtime fail | Validation không kiểm thử target application | Thêm TestKit functional tests |
| TestKit Plugin not found | withPluginClasspath hoặc manifest thiếu | Dùng java-gradle-plugin và withPluginClasspath |
| TestKit JUnit lỗi | Chưa khai báo JUnit Jupiter engine/launcher | Thêm dependencies và useJUnitPlatform |
| TestKit compileOnly plugin API thiếu | Plugin TestKit classpath không có external plugin | Dùng publication/repository fixture theo docs |
| Project plugin gọi Project trong TaskAction, config cache fail | Task action bắt giữ mutable Project | Dùng Property inputs/Providers và custom Task type |
| Settings policy không tác động included build | Included builds có settings độc lập | Áp policy ở từng build hoặc chia sẻ settings plugin |
| Settings plugin quá chậm | Early build logic quá nặng | Tách minimal settings plugin build |
| Plugin ID có nhưng task không chạy khi gọi help | apply đăng ký task chứ không execute | Gọi task helloProject |
| build.gradle plugins block đặt settings-greeting | Sai application target | Chuyển vào settings.gradle |
| settings.gradle plugins block đặt project-greeting | Sai application target | Chuyển vào build.gradle |

### 18.1. Lệnh debug hữu ích

~~~bash
./gradlew projects
./gradlew tasks --all
./gradlew help --task helloProject
./gradlew -q helloProject
./gradlew :plugin-build:pluginDescriptors
./gradlew :plugin-build:validatePlugins
./gradlew :plugin-build:jar
./gradlew :plugin-build:test
~~~

**projects** cho biết build structure, **tasks --all** cho biết task được đăng ký, **pluginDescriptors** xác minh plugin ID mapping, **validatePlugins** kiểm tra metadata/task property annotations, **test** thực thi TestKit nếu đã thêm JUnit tests.

### 18.2. Phân biệt failure stages

- **Plugin resolution failure**: không tìm được plugin ID/version/implementation artifact.
- **Plugin application failure**: đã tìm thấy nhưng apply target sai hoặc code trong apply ném exception.
- **Project configuration failure**: plugin apply được nhưng task/configuration thiết lập sai.
- **Task execution failure**: plugin được cấu hình hợp lệ, task action thực thi bị lỗi.
- **Functional test failure**: fixture/GradleRunner/assertions sai hoặc plugin thực sự hoạt động sai.

Phân tầng lỗi giúp tránh chữa nhầm: một project plugin không chạy task không phải vì Settings plugin tự động nhận wrong type; một missing plugin marker cũng không phải vì Java task @TaskAction chưa có.

---

## 19. Bài tập tự kiểm tra có đáp án

### Bài 1 — Plugin<Project> nhận gì?

**Đáp án:** nhận **Project** qua apply(Project project), dùng để cấu hình tasks, configurations và conventions của Project đó.

### Bài 2 — Plugin<Settings> nhận gì?

**Đáp án:** nhận **Settings** qua apply(Settings settings), dùng để cấu hình build layout, include subprojects, repository/plugin policies thuộc Settings.

### Bài 3 — Plugin<Project> ở root có tự áp vào :api?

**Đáp án:** không. Cần áp plugin vào **:api** hoặc một convention apply có chủ đích đúng scope.

### Bài 4 — Vì sao Settings plugin không thể gọi settings.getTasks()?

**Đáp án:** Settings không có TaskContainer như Project. Task creation thuộc Project/Task API; nên tách Project plugin.

### Bài 5 — settings.rootProject là gì?

**Đáp án:** ProjectDescriptor, không phải Project object đã cấu hình xong.

### Bài 6 — Khi nào Plugin.apply được gọi?

**Đáp án:** khi plugin được apply vào target trong phase phù hợp; Project plugin thường trong configuration, Settings plugin trong initialization. Nó không chờ task được chọn mới chạy.

### Bài 7 — @TaskAction chạy khi nào?

**Đáp án:** trong execution phase khi task có trong graph và cần execute. Không đồng nghĩa với apply().

### Bài 8 — Hai plugins có cùng JAR nhưng khác target được không?

**Đáp án:** được. Đăng ký hai plugin IDs/implementationClass khác nhau trong gradlePlugin.plugins. Mỗi ID được apply riêng trên target tương ứng.

### Bài 9 — Plugin ID lấy từ tên Java class?

**Đáp án:** không nhất thiết. Plugin ID là giá trị id trong gradlePlugin entry, implementationClass là Java fully qualified name; container registration name cũng khác.

### Bài 10 — pluginManagement.includeBuild dùng khi nào?

**Đáp án:** khi cần resolve plugin từ local included plugin build đủ sớm, nhất là một Settings plugin được áp trong chính settings.gradle.

### Bài 11 — Settings plugin từ plugin-build áp vào đâu?

**Đáp án:** trong settings.gradle(.kts) plugins block, không phải build.gradle của root.

### Bài 12 — Project plugin áp vào đâu?

**Đáp án:** build.gradle(.kts) của Project tương ứng.

### Bài 13 — Thêm apply plugin vào build.gradle để dùng Settings plugin?

**Đáp án:** không giải quyết target mismatch; build script vẫn có Project target.

### Bài 14 — Vì sao dùng tasks.register thay tasks.create?

**Đáp án:** lazy task registration giảm eager realization và hỗ trợ configuration avoidance trong build lớn.

### Bài 15 — Lab helloProject chạy root trả gì?

**Đáp án:** stdout task **PROJECT_PLUGIN_OK path=:**, và settings script in **SETTINGS_PLUGIN_MARKER=settings** trước đó.

### Bài 16 — Chạy help có execute helloProject không?

**Đáp án:** không. Plugin Project được apply, task được đăng ký nhưng không được chọn. Settings marker vẫn có thể in vì nằm trong settings script body.

### Bài 17 — Java property nào được task sử dụng?

**Đáp án:** **Property<String> getGreeting()** annotated @Input; @TaskAction đọc getGreeting().get().

### Bài 18 — Vì sao không đọc Project object trong doLast?

**Đáp án:** capture mutable model có thể gây lỗi configuration cache/isolated project behavior; dùng Providers/typed task properties sẽ rõ inputs và dễ tái lập hơn.

### Bài 19 — Làm sao test Settings plugin thật?

**Đáp án:** dùng TestKit GradleRunner với fixture settings.gradle áp Settings plugin, assert settings behavior, ví dụ extra property marker/include/selected repositories.

### Bài 20 — java-gradle-plugin tạo gì?

**Đáp án:** Java library convention, Gradle API compile dependency, plugin descriptors, plugin validation và TestKit integration; phối hợp publishing plugins tạo marker artifacts.

### Bài 21 — Plugin marker dùng để làm gì?

**Đáp án:** liên kết plugin ID/version trong plugins DSL với plugin implementation artifact, hỗ trợ resolution từ repositories.

### Bài 22 — Plugin<Project> có thể đổi project hierarchy sau settings phase?

**Đáp án:** không phải nhiệm vụ của Project plugin. Include belongs to Settings initialization; thiết kế plugin Settings nếu cần thay build layout.

### Bài 23 — Settings plugin có tự lan sang included builds không?

**Đáp án:** không. Mỗi included build có Settings và lifecycle riêng, cần policy áp dụng riêng nếu muốn thống nhất.

### Bài 24 — Suffix .settings.gradle.kts trong precompiled plugin nói lên điều gì?

**Đáp án:** xác định đó là precompiled **Settings** script plugin, khác precompiled Project script plugin có suffix .gradle.kts.

### Bài 25 — Có thể dùng Plugin<Object> cho cả hai scopes?

**Đáp án:** có thể thử nhưng không nên vì target contract mơ hồ, dễ lỗi lifecycle và mất type safety. Dùng hai plugin IDs/classes rõ ràng.

### Bài 26 — Kết quả validatePlugins PASS có chắc plugin apply đúng target không?

**Đáp án:** không. Cần functional tests apply plugin vào đúng Settings/Project contexts và chạy tasks thật.

### Bài 27 — Khi plugin build compile bằng Java21 nhưng Gradle daemon chạy Java17?

**Đáp án:** có thể lỗi UnsupportedClassVersionError hoặc class file version mismatch. Chọn release/JDK tương thích với supported Gradle runtimes.

### Bài 28 — Nếu phải publish cả Settings và Project plugins?

**Đáp án:** có thể publish chung artifact với hai markers/IDs, hoặc tách artifacts; version/support policy rõ, kiểm tra cả hai targets trong TestKit.

---

## 20. Checklist triển khai plugin trong dự án thực tế

- [ ] Đã xác định plugin giải quyết vấn đề thuộc **Project** hay **Settings**?
- [ ] Target generic type của implementation khớp script áp plugin?
- [ ] Plugin<Project> chỉ đăng ký/configure tasks/dependencies của Project được áp?
- [ ] Plugin<Settings> không gọi TaskContainer hoặc Project objects quá sớm?
- [ ] Dùng **pluginManagement** ở đầu settings khi cần settings plugin local?
- [ ] Phân biệt **pluginManagement.repositories** với **dependencyResolutionManagement.repositories**?
- [ ] Included plugin build có settings.gradle/build.gradle riêng và build được?
- [ ] **java-gradle-plugin** khai báo plugin IDs/implementationClass chính xác?
- [ ] Java source files/package names khớp implementationClass?
- [ ] Đã kiểm tra **pluginDescriptors**, **validatePlugins**, **jar**?
- [ ] Gradle Wrapper/JDK phù hợp bytecode target của plugin?
- [ ] Project tasks dùng **tasks.register** và Provider API khi phù hợp?
- [ ] @Input/@OutputFile/@Internal annotations đúng cho custom task properties?
- [ ] @TaskAction không phụ thuộc Project mutable model bị capture?
- [ ] Task execution không bị thực hiện ngay trong apply()?
- [ ] Settings plugin chạy sớm và đủ tối giản cho initialization performance?
- [ ] Plugin áp ở root không bị hiểu nhầm đã áp vào mọi subproject?
- [ ] Included builds không bị giả định chia sẻ Settings policy tự động?
- [ ] Thay đổi build layout sử dụng Settings APIs trong phase phù hợp?
- [ ] Các extensions được định nghĩa trên đúng target object?
- [ ] Java/toolchain conventions nằm trong Project plugin khi phù hợp?
- [ ] Plugin ID/version/repository policy minh bạch cho consumer?
- [ ] Plugin publish có marker artifacts khi dùng plugins DSL từ remote repository?
- [ ] TestKit có ít nhất một fixture Settings plugin và một fixture Project plugin?
- [ ] Thử failure do áp sai target để phát hiện regression?
- [ ] Khi nâng Gradle/JDK, chạy validatePlugins và functional tests theo matrix?
- [ ] Không in secrets/credentials từ Settings/Project plugin?
- [ ] Không dựa vào root build.gradle để quyết định plugin resolution quá muộn?
- [ ] Code review xác nhận không cấu hình chéo projects hoặc thực hiện I/O nặng trong apply()?

## Tài liệu tham khảo chính thức

- [Gradle — Introduction to Plugins](https://docs.gradle.org/current/userguide/plugins.html): plugin interface, types Project/Settings/Gradle, scope và precompiled script plugin suffix.
- [Gradle — Custom Plugins](https://docs.gradle.org/current/userguide/custom_plugins.html): script, precompiled script, binary plugin, plugin IDs và implementation patterns.
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): pluginManagement, settings plugins, initialization/configuration/execution.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): pluginManagement.includeBuild, đặc biệt cho Settings plugins.
- [Gradle — Java Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): gradlePlugin DSL, descriptors, validation và TestKit integration.
- [Gradle — Testing Plugins](https://docs.gradle.org/current/userguide/testing_gradle_plugins.html): functional testing và GradleRunner.
- [Gradle — TestKit](https://docs.gradle.org/current/userguide/test_kit.html): withPluginClasspath, GradleRunner, plugin functional tests.
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): plugin marker artifacts, plugin resolution và publishing.
- [Gradle — Settings API](https://docs.gradle.org/current/javadoc/org/gradle/api/initialization/Settings.html): include, includeBuild, Settings extensions và ProjectDescriptor.
- [Gradle — Plugin API](https://docs.gradle.org/current/javadoc/org/gradle/api/Plugin.html): generic apply(T target).
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): included build build-logic, Settings plugin early build-logic costs.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): Gradle daemon JDK và toolchain support.

**Kết luận:** **Plugin<Project>** và **Plugin<Settings>** cùng tuân theo **Plugin<T>**, nhưng giải quyết hai vấn đề khác thời điểm và khác phạm vi. Project plugin cấu hình **một Project** (task, dependency, Java convention), còn Settings plugin cấu hình **build structure và policies ở initialization**. Java plugin implementation có thể đóng chung JAR, nhưng mỗi plugin ID phải trỏ đúng implementation class và được áp vào đúng target. Dùng **pluginManagement.includeBuild** khi settings plugin local cần khả dụng sớm, **java-gradle-plugin** để quản lý descriptors/TestKit, và kiểm tra cả configuration lẫn task execution thay vì coi việc plugin compile thành công là đủ.