# Core plugin, plugin ngoài và plugin tự xây dựng

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Sử dụng plugin

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **plugin là thành phần mở rộng mô hình build**: thêm task, dependency configuration, extension DSL, conventions và các tích hợp khác.
2. Phân biệt ba nguồn plugin: **core plugin** có sẵn trong bản phân phối Gradle, **plugin ngoài** từ Gradle Plugin Portal/Maven/Ivy repository, và **plugin tự xây dựng** ở buildSrc, included build hoặc repository riêng.
3. Áp dụng plugin đúng với **plugins { id ... }**, biết trường hợp nào cần **version**, trường hợp nào dùng **pluginManagement** và tại sao **repositories { mavenCentral() }** cho thư viện Java khác **pluginManagement.repositories** cho plugin.
4. Hiểu sự khác nhau giữa **script plugin**, **precompiled script/convention plugin** và **binary plugin** thực thi giao diện Plugin<Project>, cũng như phạm vi Plugin<Settings> và Plugin<Gradle>.
5. Tạo một dự án **Java 17 + Gradle Groovy DSL** chạy được: dùng core plugin application, plugin ngoài Spotless, và một binary plugin tự viết bằng Java trong **included build build-logic**.
6. Tạo **extension cấu hình**, dùng **managed Property<String>**, đăng ký task bằng **tasks.register**, liên kết giá trị theo Provider và nhìn thấy stdout dự đoán được khi chạy.
7. Biết khi nào nên dùng **buildSrc**, khi nào dùng **build-logic** và khi nào publish plugin thành artifact độc lập; cách kiểm thử, version hóa và cấu hình plugin trong CI.
8. Chẩn đoán lỗi thường gặp như **Plugin [id: ...] was not found**, không có task sau khi áp plugin, thiếu phiên bản/plugin marker, trùng plugin ID hoặc thiếu plugin dependency trong convention plugin.

**Thông điệp chính:** Một plugin được dùng bằng **ID** nhưng nguồn cung cấp rất khác nhau. Core plugin đã đi cùng Gradle; plugin ngoài cần được **resolve** từ nguồn plugin hợp lệ; plugin tự xây dựng phải được **biên dịch hoặc đưa lên plugin classpath** trước khi áp dụng. Plugin là code chạy trong quá trình cấu hình build, nên phải quản lý tương thích phiên bản và quyền thực thi cẩn thận, không coi nó như một JAR của ứng dụng Java.

## 1. Plugin là gì và nó thay đổi build như thế nào?

Gradle giữ một phần lớn hành vi xây dựng dự án trong các plugin có thể tái sử dụng. Chẳng hạn, một build.gradle rất ngắn:

~~~groovy
plugins {
    id 'java'
}
~~~

đã cung cấp một mô hình Java build gồm các nhiệm vụ và dependency configurations quen thuộc, thay vì bạn phải tự gọi javac, jar và viết task dependency thủ công.

Một plugin có thể:

- **Thêm tasks:** compileJava, test, jar, run, spotlessCheck hoặc task nội bộ tự đặt tên.
- **Thêm configurations:** implementation, compileOnly, runtimeOnly hoặc những cấu hình riêng.
- **Thêm extensions DSL:** java { }, application { }, publishing { }, greeting { }.
- **Đặt conventions:** mặc định toolchain Java, cấu trúc thư mục, kiểm tra chất lượng hoặc cấu hình compiler.
- **Phản ứng với plugin khác:** ví dụ plugin kiểm tra code chỉ đăng ký phần Java khi Java plugin đã được áp dụng.
- **Đăng ký artifact variants và tích hợp dependency resolution** khi một plugin có nhiệm vụ đó.

Plugin thường được **áp dụng trong configuration phase**. Khi apply, nó tạo/cấu hình mô hình build; task actions thực sự chạy ở execution phase. **Không nên** chạy một công cụ ngoài, tải dữ liệu tùy tiện hoặc đọc toàn bộ file outputs ngay trong Plugin.apply nếu có thể đăng ký task rồi để Gradle chạy đúng giai đoạn.

### 1.1. Ba nguồn plugin

| Tiêu chí | Core plugin | Plugin ngoài | Plugin tự xây dựng |
|---|---|---|---|
| Nguồn | Đi kèm Gradle distribution | Gradle Plugin Portal hoặc plugin repository | Code của nhóm: buildSrc, included build, JAR publish |
| Ví dụ ID | java, java-library, application, maven-publish | com.diffplug.spotless | edu.example.greeting |
| Có phải thêm version trong plugins block? | **Không** | Thường **có**, trừ khi version được quản lý tại nơi khác | **Không** nếu có sẵn từ included build/buildSrc; có nếu được publish và resolve như plugin ngoài |
| Plugin code ở đâu? | Trong bản Gradle đang chạy | JAR và dependencies resolve qua plugin repositories | Java/Groovy/Kotlin hoặc script được compile thành plugin |
| Có cần mạng lúc chạy build đầu tiên? | Không để tải chính core plugin | Thường có nếu cache chưa có | Local build không cần repository ngoài cho chính plugin; code plugin vẫn có thể có dependencies ngoài |
| Ai chịu trách nhiệm nâng cấp? | Nâng Gradle Wrapper/distribution | Chọn plugin version tương thích | Nhóm sở hữu code và chính sách release |
| Độ phù hợp | Nhu cầu chuẩn Java, application, publishing | Formatting, coverage, framework, static analysis | Chuẩn nội bộ, task/domain đặc thù, tái sử dụng build logic |

**Plugin ngoài không đồng nghĩa plugin kém an toàn**, còn plugin tự xây dựng không tự động đáng tin. Cả hai đều là code có thể đọc file, gọi mạng hoặc thực hiện hành động trong quyền hạn của Gradle process. Cần xác minh nguồn, version, license, maintenance, khả năng tương thích và quy trình nâng cấp.

## 2. Core plugin: có sẵn trong Gradle distribution

Một số core plugin thường dùng:

| Plugin ID | Công dụng |
|---|---|
| **java** | Biên dịch Java, chạy tests, tạo JAR, thiết lập Java source sets và dependency configurations |
| **java-library** | Mở rộng Java Plugin cho thư viện, cung cấp api/implementation separation |
| **application** | Mở rộng mô hình Java với application entry point, task run và distribution |
| **groovy** | Hỗ trợ nguồn Groovy, dựa trên mô hình Java |
| **maven-publish** | Định nghĩa publications, publish artifact và metadata lên Maven repository |
| **signing** | Ký artifacts khi quy trình publication yêu cầu |
| **checkstyle** | Tích hợp công cụ Checkstyle vào lifecycle kiểm tra Java |
| **jacoco** | Tích hợp Java code coverage qua JaCoCo |
| **java-gradle-plugin** | Công cụ dành cho tác giả binary Gradle plugin: descriptor, validation, TestKit, metadata |
| **groovy-gradle-plugin** | Công cụ biên dịch precompiled Groovy DSL script plugins |

Core plugin được áp dụng bằng ID ngắn, ví dụ:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.Main'
}
~~~

**Không viết**:

~~~groovy
// Sai ý tưởng: core plugin được version theo Gradle distribution,
// không chọn phiên bản độc lập kiểu external plugin.
plugins {
    id 'java' version '17.0'
}
~~~

Số 17 trong ngữ cảnh Java là **Java toolchain/target**, không phải version của Gradle Java Plugin. Dùng:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Cần phân biệt:
- **Gradle version:** chọn bằng Gradle Wrapper (ví dụ Gradle 9.x).
- **Java runtime để chạy Gradle:** JDK mà Gradle daemon sử dụng, phải thỏa Gradle compatibility matrix.
- **Java toolchain để compile/test:** cấu hình bằng JavaLanguageVersion.of(17).
- **External plugin version:** phiên bản của JAR plugin được yêu cầu qua plugins block.

Bốn version này **không phải cùng một thứ**.

### 2.1. Một core plugin có thể áp dụng plugin khác

Ví dụ:
- application cung cấp tính năng Java và application.
- java-library thêm mô hình Java library trên nền Java.
- java-gradle-plugin giúp xây plugin và tự áp dụng các mô hình Java cần thiết.

Bạn không cần gọi id 'java' thêm lần nữa chỉ vì application đã cung cấp mô hình Java. Nếu một plugin được áp dụng từ hai đường, Gradle không tự tạo hai bản độc lập của cùng ID trên cùng project; nhưng việc cấu hình chồng chéo nhiều lần vẫn có thể gây khó hiểu.

### 2.2. Core plugin không bắt buộc có ID "org.gradle.*"

Core plugin phổ biến dùng ID ngắn như java, application, base, jacoco. Một số plugin Gradle có tên giàu namespace, nhưng đừng dùng tiền tố org.gradle cho **plugin ID tự tạo**: namespace đó thuộc Gradle và có quy tắc reserved. Nên đặt ID plugin của tổ chức theo dạng reverse-domain như com.company.java-conventions hoặc edu.example.greeting.

## 3. Plugin ngoài: plugin được publish và cần resolution

### 3.1. plugins block với phiên bản cụ thể

Một plugin ngoài tiêu biểu là Spotless để kiểm tra/định dạng mã. Cú pháp Groovy DSL:

~~~groovy
plugins {
    id 'com.diffplug.spotless' version '8.11.0'
}
~~~

Phiên bản 8.11.0 là bản Spotless được đăng trên Gradle Plugin Portal vào tháng 11/2026. Không nên viết version 'latest' rồi kỳ vọng mọi build luôn tái lập. Đối với dự án thật, hãy pin một version đã kiểm thử cùng Gradle Wrapper/JDK của nhóm.

Sau khi plugin được áp dụng:

~~~groovy
spotless {
    java {
        target 'src/main/java/**/*.java'
        trimTrailingWhitespace()
        endWithNewline()
    }
}
~~~

Bạn có thể thấy tasks như spotlessCheck và spotlessApply. Ví dụ này chỉ dùng hai formatter steps phổ biến, không cần tải formatter Java bên thứ ba. Trong dự án thật, có thể bổ sung Google Java Format/Eclipse/Prettier theo khả năng của phiên bản plugin và cấu hình công cụ formatter riêng.

**Khác với dependency của ứng dụng:** Spotless plugin code được tải và chạy **trong Gradle build process**. Nó không đồng nghĩa application runtime có một library com.diffplug.spotless trong runtimeClasspath; application dependency nên khai báo riêng trong dependencies { implementation ... } khi mã ứng dụng cần.

### 3.2. Plugin repository khác dependency repository

Hai khối nhìn tương tự nhưng làm việc khác:

**settings.gradle:**

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}
~~~

Dùng để Gradle tìm **plugin implementation và marker artifacts** khi xử lý plugins { id ... version ... }. Gradle Plugin Portal là nguồn mặc định của plugins DSL nếu không tùy chỉnh nguồn; khi bạn tự định nghĩa pluginManagement.repositories, hãy thêm rõ gradlePluginPortal() nếu muốn dùng nó.

**build.gradle:**

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Dùng để tìm **library modules của ứng dụng**. Đặt mavenCentral() trong repositories của project **không tự làm** external plugin ID resolve được nếu plugin repository/marker cần thiết không được cấu hình.

Nếu plugin được publish vào Maven repository nội bộ, có thể cấu hình:

~~~groovy
// settings.gradle (mẫu, repository URL cần là nơi thực tế).
pluginManagement {
    repositories {
        maven {
            url = uri('https://repo.example.org/gradle-plugins')
        }
        gradlePluginPortal()
    }
}
~~~

Đây chỉ là **mẫu minh họa**, tên miền example.org không đại diện cho một repository thực tế có plugin. Với repository riêng cần quản lý credentials/token an toàn; không commit mật khẩu trong script.

### 3.3. Plugin marker artifact là gì?

plugins DSL nhận **plugin ID + version**, trong khi Maven/Ivy repositories lưu **module coordinates**. Gradle thường tìm một **plugin marker artifact** nối ID tới JAR plugin:

~~~text
Plugin request:
  id      = com.diffplug.spotless
  version = 8.11.0

Plugin marker coordinates theo quy tắc:
  com.diffplug.spotless:com.diffplug.spotless.gradle.plugin:8.11.0

Marker metadata --> module chứa plugin implementation
                   --> JAR và các dependencies của plugin
~~~

Không phải mọi JAR có chứa Plugin<Project> đều tự có marker để Gradle tìm bằng plugins DSL. Khi bạn publish plugin bằng **java-gradle-plugin + maven-publish**, Gradle có thể tạo plugin descriptors và plugin marker publications. Nếu tổ chức publish JAR thủ công nhưng quên marker, plugins { id ... version ... } có thể báo plugin không tìm thấy dù JAR tồn tại ở một Maven repository.

**Không nhầm marker module với application library:** Plugin marker và implementation nằm trên **plugin classpath**; không phải tự động ở implementation/runtimeOnly của mã Java ứng dụng.

### 3.4. Quản lý version trong settings

Bạn có thể đặt default plugin version trong pluginManagement:

~~~groovy
// settings.gradle
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
    plugins {
        id 'com.diffplug.spotless' version '8.11.0'
    }
}
~~~

Khi đó project có thể dùng:

~~~groovy
// app/build.gradle
plugins {
    id 'com.diffplug.spotless'
}
~~~

Plugin vẫn được resolve từ repository, nhưng version được quản lý tập trung. Tương tự, version catalog cho phép dùng alias(libs.plugins.spotless) khi có [plugins] entry trong libs.versions.toml.

### 3.5. apply false trong multi-project build

Nếu có nhiều subprojects, root build.gradle có thể khai báo plugin ngoài một lần mà **chưa áp vào root**:

~~~groovy
// root build.gradle
plugins {
    id 'com.diffplug.spotless' version '8.11.0' apply false
}
~~~

Một subproject có thể yêu cầu:

~~~groovy
// app/build.gradle
plugins {
    id 'com.diffplug.spotless'
}
~~~

Ý nghĩa:
- **apply false** đưa plugin request/version vào classpath/scope thích hợp nhưng **không áp plugin cho root project**.
- Project muốn dùng vẫn phải áp dụng rõ ràng.
- Không suy rằng root áp plugin thì mọi subprojects đã có spotless tasks.
- Một core plugin không cần chọn version độc lập; không dùng apply false cho core plugin chỉ để “dự trữ” một JAR đã có sẵn.

Khi tổ chức đã dùng pluginManagement hoặc convention plugin để quản lý version/application, không nhất thiết thêm apply false ở root nữa. Chọn một chiến lược nhất quán.

## 4. Plugin tự xây dựng có những hình thức nào?

**“Tự xây dựng” là nguồn sở hữu code**, còn **“script / precompiled / binary” là hình thức triển khai**. Đừng dùng hai cách phân loại như những nhóm hoàn toàn loại trừ nhau.

| Hình thức | Code nằm ở đâu? | Cách áp dụng | Khi nào dùng? |
|---|---|---|---|
| **Script plugin** | Một file .gradle riêng | apply from: 'gradle/common.gradle' | Script rất nhỏ, ngắn hạn hoặc cần duy trì hệ thống cũ |
| **Precompiled script plugin** | buildSrc/src/main/groovy/*.gradle hoặc included build | plugins { id 'java-conventions' } | Quy ước dùng chung, ít code Java/Groovy phức tạp |
| **Binary plugin** | Class implement Plugin<Project> biên dịch thành JAR | plugins { id 'edu.example.greeting' } | Task/extension phức tạp, cần test và tái sử dụng giữa nhiều builds |
| **Binary plugin publish** | JAR và marker trên Maven/Ivy/Plugin Portal | plugins { id 'com.company.plugin' version 'x.y.z' } | Dùng nội bộ nhiều repository hoặc chia sẻ bên ngoài |

### 4.1. Script plugin truyền thống

Ví dụ một file:

~~~groovy
// gradle/java-conventions.gradle
apply plugin: 'java'

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Áp dụng trong project build.gradle:

~~~groovy
apply from: "$rootDir/gradle/java-conventions.gradle"
~~~

Đây là cơ chế **legacy script plugin**. Ưu điểm: dễ viết. Nhược điểm: khó test/tái sử dụng/kiểm soát dependencies, ít type safety, có thể khó tối ưu cấu hình.

**Quan trọng:** Một script được áp qua apply from không phải một build.gradle project thông thường. Bạn không được đặt plugins { ... } block vào script plugin legacy rồi mong cơ chế plugins DSL hoạt động như file build.gradle chính. Dùng apply plugin: ... trong script hoặc chuyển sang precompiled convention plugin.

### 4.2. Precompiled script plugin (convention plugin)

Gradle có thể compile một script .gradle thành plugin có ID riêng. Ví dụ trong buildSrc:

~~~text
buildSrc/
├── build.gradle
└── src/main/groovy/java-conventions.gradle
~~~

**buildSrc/build.gradle:**

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}
~~~

**buildSrc/src/main/groovy/java-conventions.gradle:**

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
    options.encoding = 'UTF-8'
}
~~~

**build.gradle của subproject:**

~~~groovy
plugins {
    id 'java-conventions'
}
~~~

ID **java-conventions** lấy từ tên file java-conventions.gradle. Đây là **ví dụ thay thế** cho cách tự xây dựng binary plugin ở bài lab chính; không đặt đồng thời vào cùng project rồi tự suy luận thứ tự apply.

Ưu điểm:
- Gọn với quy ước ứng dụng plugin khác, cấu hình toolchain và compiler.
- Có thể kiểm thử build logic.
- Dùng cùng cú pháp plugins { id '...' } mà các subprojects quen thuộc.
- Nói rõ “project này chọn quy ước Java” thay vì root âm thầm cấu hình bằng subprojects { ... }.

**buildSrc** được Gradle biên dịch trước main build và đưa vào classpath của các project build scripts. Nó tiện cho project nhỏ, nhưng thay đổi buildSrc có thể làm nhiều project phải cấu hình lại. Included build **build-logic** giúp tách biệt rõ hơn và thường dễ mở rộng trong multi-project builds.

### 4.3. Binary plugin và Plugin<Project>

Một plugin Java thường là class:

~~~java
import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class ExamplePlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getPluginManager().apply("java");
    }
}
~~~

Đây là **class minh họa**, không phải cả dự án chạy độc lập. Gradle gọi apply(...) khi plugin được áp dụng. Trong đó bạn có thể:
- Áp dụng core/community plugins phụ thuộc.
- Tạo extensions và managed configuration properties.
- Đăng ký tasks bằng project.getTasks().register(...).
- Đặt conventions thay vì hardcode vào task actions.
- Đăng ký dependencies, configurations, artifacts hoặc plugin callbacks.

Với plugin nhắm **Settings** hoặc toàn Gradle build, các interface tương ứng là Plugin<Settings> và Plugin<Gradle>. Không coi mọi plugin đều áp trên Project; plugin ID phải được áp tại đúng scope mà implementation hỗ trợ.

## 5. Bài lab hoàn chỉnh: core + external + binary plugin tự xây dựng

Bài lab dưới đây dùng **Gradle Groovy DSL**, **Java 17**, một **included build build-logic** cung cấp binary plugin Java, một **application subproject** và một plugin ngoài **Spotless**.

Ba plugin sources thực sự xuất hiện:

- **Core:** id 'application' trong app/build.gradle; build-logic còn dùng core id 'java-gradle-plugin'.
- **External:** id 'com.diffplug.spotless' version '8.11.0', lấy từ Gradle Plugin Portal khi chưa có cache.
- **Custom:** id 'edu.example.greeting', do Java class GreetingPlugin trong **build-logic** cung cấp.

Code plugin tự xây dựng **không phải Java application**. Nó được compile để chạy trong Gradle build process, tạo task/extension cho project app. Main.java là ứng dụng độc lập dùng để xác nhận Java 17.

### 5.1. Môi trường và cấu trúc

Cần:
- JDK 17 hoặc mới hơn **để chạy phiên bản Gradle phù hợp**; toolchain Java 17 phải có hoặc được provision.
- Gradle Wrapper được tạo bằng Gradle tương thích với plugin ngoài đã chọn.
- Network/Plugin Portal khả dụng lần đầu để resolve **Spotless**.
- Không cần Maven Central cho application sources của bài lab, vì mã app không có external library dependencies.

Cấu trúc:

~~~text
plugin-types-lab/
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/java/edu/example/
│       ├── GreetingExtension.java
│       ├── GreetingTask.java
│       └── GreetingPlugin.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
~~~

Ban đầu bạn cần tạo hai settings.gradle, hai build.gradle và bốn file Java. Nếu chưa có Wrapper, dùng một Gradle đã cài chạy **gradle wrapper** từ root rồi commit các tệp Wrapper được sinh. Không tự chép một gradle-wrapper.jar không rõ nguồn.

### 5.2. Root settings.gradle: cấu hình plugin resolution

~~~groovy
pluginManagement {
    // Plugin tự viết được build từ included build này.
    includeBuild('build-logic')

    repositories {
        // Plugin ngoài như Spotless được resolve ở đây.
        gradlePluginPortal()
    }
}

rootProject.name = 'plugin-types-lab'
include('app')
~~~

**Giải thích:**
- pluginManagement là cấu hình **sớm**, đặt trước các phần khác của settings.gradle.
- includeBuild('build-logic') làm Gradle biết một **included plugin build** có thể cung cấp ID custom.
- gradlePluginPortal() giải quyết external plugin Spotless.
- include('app') đăng ký subproject ứng dụng.
- build-logic **không phải** project path :build-logic trong main build; nó là một **included build riêng**.
- Không bắt buộc phải có root build.gradle trong ví dụ này; root settings.gradle và app/build.gradle đủ để cấu hình main build.

### 5.3. build-logic/settings.gradle

~~~groovy
rootProject.name = 'build-logic'
~~~

Đây là **settings của included build**, không cùng file với settings.gradle của main build. Included build có classpath/dependency resolution riêng. Khi custom plugin cần thư viện ngoài, thêm repositories/dependencies vào **build-logic** đúng nơi, không nhầm với app dependencies.

### 5.4. build-logic/build.gradle: đăng ký plugin ID

~~~groovy
plugins {
    id 'java-gradle-plugin'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

gradlePlugin {
    plugins {
        register('greeting') {
            id = 'edu.example.greeting'
            implementationClass = 'edu.example.GreetingPlugin'
        }
    }
}
~~~

**Cơ chế:**
- java-gradle-plugin là **core plugin** hỗ trợ xây plugin.
- Nó cung cấp compile dependency Gradle API và task sinh **plugin descriptors**, validation, TestKit integration.
- gradlePlugin.plugins.register(...) tạo định nghĩa plugin với **ID** và **implementation class**.
- Gradle tạo metadata trong META-INF/gradle-plugins khi đóng gói plugin.
- Với included build dùng ngay trong main build, **không phải publish plugin ra Plugin Portal** và app **không khai báo version** cho edu.example.greeting.
- Nếu bạn chuyển sang publish binary plugin như một release độc lập, cần thêm bước publish và version (xem mục 9).

### 5.5. GreetingExtension.java: extension cấu hình có managed Property

**build-logic/src/main/java/edu/example/GreetingExtension.java**

~~~java
package edu.example;

import org.gradle.api.provider.Property;

public abstract class GreetingExtension {
    public abstract Property<String> getRecipient();
}
~~~

Đây là **managed abstract property**. Gradle cấp triển khai cho property, nên không phải tự new Property<String>. Khi plugin tạo extension tên greeting, build script sẽ có DSL:

~~~groovy
greeting {
    recipient.set('Java 17')
}
~~~

Plugin đặt default recipient bằng convention; người dùng có thể override bằng set. Extension thể hiện **cấu hình ở cấp project**, task tiêu thụ qua Property/Provider.

### 5.6. GreetingTask.java: task có đầu vào đúng mô hình Gradle

**build-logic/src/main/java/edu/example/GreetingTask.java**

~~~java
package edu.example;

import org.gradle.api.DefaultTask;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.TaskAction;

public abstract class GreetingTask extends DefaultTask {
    @Input
    public abstract Property<String> getRecipient();

    @TaskAction
    public void greet() {
        getLogger().quiet(
            "plugin=local; hello=" + getRecipient().get()
        );
    }
}
~~~

Giải thích:
- Getter getRecipient() là Property<String> được quản lý.
- @Input báo Gradle giá trị nào task sử dụng.
- @TaskAction chạy **khi task được thực thi**, không phải khi plugin apply.
- getLogger().quiet(...) phát thông điệp có thể thấy với --quiet.
- Task này **không khai báo output file**, nên không chứng minh up-to-date caching. Đó là chủ ý: nhiệm vụ chỉ in thông báo; nếu sau này task sinh file, cần khai báo @OutputFile/@OutputDirectory phù hợp.

### 5.7. GreetingPlugin.java: áp core plugin, tạo extension, đăng ký task

**build-logic/src/main/java/edu/example/GreetingPlugin.java**

~~~java
package edu.example;

import org.gradle.api.Plugin;
import org.gradle.api.Project;
import org.gradle.api.JavaVersion;
import org.gradle.api.plugins.JavaPluginExtension;
import org.gradle.jvm.toolchain.JavaLanguageVersion;

public final class GreetingPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        // Cho project có Java model.
        project.getPluginManager().apply("java");

        // Đặt Java 17 như convention, người dùng có thể override.
        JavaPluginExtension javaExtension =
                project.getExtensions()
                        .getByType(JavaPluginExtension.class);

        javaExtension.getToolchain().getLanguageVersion()
                .convention(JavaLanguageVersion.of(17));

        // DSL: greeting { recipient.set(...) }
        GreetingExtension greeting =
                project.getExtensions()
                        .create("greeting", GreetingExtension.class);

        greeting.getRecipient().convention("Gradle");

        // Đăng ký lazy task; không gọi task action ngay.
        project.getTasks().register(
                "greetFromPlugin",
                GreetingTask.class,
                task -> {
                    task.setGroup("verification");
                    task.setDescription("Greet using a custom plugin");
                    task.getRecipient()
                            .convention(greeting.getRecipient());
                }
        );
    }
}
~~~

**Chi tiết quan trọng:**
- Plugin<Project> đại diện một plugin được áp cho **Project**.
- project.getPluginManager().apply("java") áp core Java plugin bằng API, có thể kết hợp với application plugin mà không cần người dùng tự lo thứ tự.
- JavaPluginExtension cung cấp Java toolchain convention; không lấy Gradle daemon JDK bằng cách gọi System.setProperty.
- getExtensions().create(...) tạo extension greeting với Property có default "Gradle".
- tasks.register(...) đăng ký task **lazy**, và task recipient **lấy convention từ Provider extension**. Nếu build.gradle set recipient sau đó, task sẽ lấy giá trị phù hợp khi thực thi.
- Không nên gọi greeting.getRecipient().get() ngay trong apply chỉ để tính một String; như vậy mất quan hệ cấu hình lười.
- import org.gradle.api.JavaVersion ở trên không cần dùng cho ví dụ; có thể bỏ đi để file sạch imports. Tác giả plugin thực tế nên chạy compileJava và test để kiểm tra các imports thừa, compatibility.

### 5.8. app/build.gradle: áp đủ ba loại plugin

~~~groovy
plugins {
    // Core plugin từ Gradle distribution.
    id 'application'

    // Plugin tự xây từ included build trong pluginManagement.
    id 'edu.example.greeting'

    // Plugin ngoài có ID và version từ Gradle Plugin Portal.
    id 'com.diffplug.spotless' version '8.11.0'
}

application {
    mainClass = 'demo.app.Main'
}

greeting {
    recipient.set('Java 17')
}

spotless {
    java {
        target 'src/main/java/**/*.java'
        trimTrailingWhitespace()
        endWithNewline()
    }
}
~~~

**Tại sao không cần id 'java' trong app?** application đã mang mô hình Java và plugin tự viết cũng apply "java". Gradle xử lý việc áp cùng plugin mà không đòi khai báo lặp cho mỗi nguồn.

**Tại sao custom plugin không có version?** ID edu.example.greeting được cung cấp bởi **pluginManagement.includeBuild('build-logic')** ngay trong build này. Nó không phải module publish từ Portal cần version.

**Tại sao external plugin có version?** Gradle phải biết phiên bản Spotless cần resolve. Bạn có thể đặt version ở pluginManagement hoặc version catalog thay vì lặp ở nhiều build scripts, nhưng **không nên vừa ghim version ở nhiều nơi có giá trị mâu thuẫn**.

### 5.9. Java 17 application source

**app/src/main/java/demo/app/Main.java**

~~~java
package demo.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("app=Java 17");
    }
}
~~~

Lớp này không import trực tiếp GreetingPlugin hay Spotless. **Build plugin** là công cụ cấu hình build; **Java app** là chương trình chạy do build tạo. Hai classpaths và hai vòng đời khác nhau.

### 5.10. Các lệnh chạy và stdout kỳ vọng

Linux/macOS, từ thư mục root **plugin-types-lab**:

~~~bash
./gradlew :app:greetFromPlugin --quiet
./gradlew :app:run --quiet
./gradlew :app:spotlessCheck
./gradlew :app:tasks --all
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:greetFromPlugin --quiet
.\gradlew.bat :app:run --quiet
.\gradlew.bat :app:spotlessCheck
.\gradlew.bat :app:tasks --all
~~~

**Lệnh 1** chạy task của **custom plugin**. Đầu ra do task action phát:

~~~text
plugin=local; hello=Java 17
~~~

**Lệnh 2** chạy chương trình Java qua **core application plugin**. Dòng stdout do Main.main in:

~~~text
app=Java 17
~~~

**Lệnh 3** dùng **Spotless external plugin**. Nếu file Main.java không có trailing whitespace và có newline cuối theo config, task kiểm tra phải hoàn thành thành công. Log Gradle phụ thuộc cờ console/phiên bản; không cố định một đoạn stdout giả.

**Lệnh 4** liệt kê các task được đăng ký. Bạn có thể tìm:
- greetFromPlugin (custom plugin),
- run và các task Java (core application),
- spotlessCheck / spotlessApply (Spotless plugin).

Nếu phiên bản Spotless không tương thích với Gradle Wrapper/JVM đang dùng, build có thể thất bại trước khi vào task action; kiểm tra tương thích/version theo tài liệu plugin. Bản 8.11.0 là phiên bản được chọn cho ví dụ, không phải bảo đảm mọi cài đặt Gradle cũ đều chạy được.

### 5.11. Đổi cấu hình extension mà không sửa plugin

Đổi trong app/build.gradle:

~~~groovy
greeting {
    recipient.set('Nam')
}
~~~

Chạy lại:

~~~bash
./gradlew :app:greetFromPlugin --quiet
~~~

Dòng output:

~~~text
plugin=local; hello=Nam
~~~

Nếu xóa cả block greeting khỏi app/build.gradle, extension sẽ dùng convention("Gradle"), nên task in:

~~~text
plugin=local; hello=Gradle
~~~

Điều này minh họa giá trị của plugin tự xây: nó định nghĩa **hành vi dùng chung**, còn từng project cấu hình **dữ liệu riêng** qua extension/Provider, không phải copy/paste task code.

## 6. Precompiled convention plugin trong build-logic: lựa chọn ngắn hơn

Ví dụ binary Java ở mục 5 phù hợp khi bạn cần custom task type, extension và logic API. Nếu chỉ muốn mọi thư viện Java dùng chung toolchain17, compiler encoding và test conventions, một **precompiled Groovy DSL script plugin** có thể gọn hơn.

Đây là **một phương án độc lập**, không thay thế trực tiếp cấu trúc Java binary plugin của mục 5 khi copy từng file. Tạo included build riêng với:

~~~text
build-logic/
├── settings.gradle
├── build.gradle
└── src/main/groovy/java17-library-conventions.gradle
~~~

**build-logic/settings.gradle:**

~~~groovy
rootProject.name = 'build-logic'
~~~

**build-logic/build.gradle:**

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}
~~~

**build-logic/src/main/groovy/java17-library-conventions.gradle:**

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
    options.encoding = 'UTF-8'
}
~~~

Main settings.gradle vẫn có:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}
~~~

Consumer subproject:

~~~groovy
plugins {
    id 'java17-library-conventions'
}
~~~

- File .gradle được compile thành plugin có ID dựa trên tên file: java17-library-conventions.
- Plugin này áp dụng core java-library và đặt quy ước Java 17.
- Không bắt buộc viết class implements Plugin<Project> bằng tay.
- Nên dùng khi behavior chủ yếu là **áp plugin khác và cấu hình defaults**.
- Nếu convention plugin muốn áp **external plugin**, project build-logic cần khai báo plugin đó như dependency ở **build logic build**, không chỉ để pluginManagement của main build tìm hộ.

### 6.1. Kết hợp một external plugin trong convention plugin

Đối với Spotless được áp bên trong precompiled script plugin:

**build-logic/build.gradle — đoạn bổ sung nếu đang dùng groovy-gradle-plugin:**

~~~groovy
repositories {
    gradlePluginPortal()
}

dependencies {
    implementation 'com.diffplug.spotless:com.diffplug.spotless.gradle.plugin:8.11.0'
}
~~~

**java17-library-conventions.gradle — ở plugins block của precompiled script:**

~~~groovy
plugins {
    id 'java-library'
    id 'com.diffplug.spotless'
}
~~~

**Không thêm version trực tiếp** vào plugins block của precompiled script plugin ở đây; plugin implementation được đưa vào **classpath của build-logic** qua dependency. Đây là một khác biệt rất hay gặp so với plugins block trong build.gradle của consumer.

Khi consumer áp java17-library-conventions, plugin ấy sẽ áp Spotless theo cấu hình đã đóng gói. Tùy nhu cầu, convention plugin có thể bổ sung spotless { java { ... } } ở cùng script.

**Đừng chèn hai mẫu plugin development khác nhau vào cùng một build-logic mà không tổ chức source/plugin dependencies rõ ràng.** Mục 5 dùng java-gradle-plugin + Java class; mục 6 minh họa một **lựa chọn thay thế** dùng groovy-gradle-plugin + precompiled Groovy script.

## 7. buildSrc và included build build-logic: chọn cách nào?

### 7.1. buildSrc hoạt động ra sao?

Khi root build có thư mục buildSrc hợp lệ, Gradle tự nhận diện và **compile build logic** trong đó, đưa output lên classpath của các project build scripts trong build đó.

Ưu điểm:
- Dễ bắt đầu, không cần includeBuild thủ công.
- Tốt cho thí nghiệm, dự án nhỏ hoặc build logic vừa phải.
- Cho phép custom classes, tasks và convention plugins.

Giới hạn:
- Thay đổi buildSrc có thể làm main build phải cấu hình lại ở phạm vi rộng.
- BuildSrc được đưa vào classpath của nhiều project dù không phải project nào cũng cần logic ấy.
- Khả năng tách boundaries, cache và phân phối build logic kém linh hoạt hơn included build có tổ chức.

### 7.2. included build build-logic

Một included build có **settings.gradle/build.gradle riêng**; main settings.gradle kết nối nó qua:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}
~~~

Ưu điểm:
- Tách build logic khỏi application/libraries rõ ràng.
- Có thể chia nhỏ build logic thành nhiều modules và publish khi cần.
- Một thay đổi có thể ảnh hưởng đến các projects sử dụng plugin tương ứng, thay vì mọi project mặc định thấy mọi class từ buildSrc.
- Phù hợp với convention plugins dùng nhiều trong multi-project builds.

Nhược điểm:
- Cần hiểu composite build, plugin resolution và classpath riêng.
- Nếu có plugin bên thứ ba áp trong build logic, phải quản lý dependencies của chính build-logic.
- Có thể thêm một số file cấu hình lúc bắt đầu.

### 7.3. Nên dùng cách nào?

| Bối cảnh | Lựa chọn gợi ý |
|---|---|
| Một script nhỏ không tái sử dụng | Build script trực tiếp; hạn chế legacy apply from |
| Một dự án nhỏ có vài quy ước | buildSrc + precompiled script plugin |
| Multi-project build lớn, nhiều convention plugins | included build build-logic |
| Plugin phức tạp có custom task type/extension | Binary plugin Java/Kotlin trong build-logic hoặc project riêng |
| Plugin phải dùng ở nhiều repositories | Binary plugin publish lên Maven/Ivy/Plugin Portal |
| Nhiều projects có cùng quy ước Java/toolchain | Convention plugin, tránh root subprojects/allprojects âm thầm cấu hình chéo |

**Không biến subprojects { apply plugin: ... } thành chiến lược chia sẻ build logic mặc định.** Convention plugins diễn đạt ý định ngay trong từng project, giảm coupling và thuận lợi hơn cho isolated projects/configuration cache.

## 8. Scope và thứ tự áp dụng plugin

### 8.1. Áp plugin vào project nào?

Trong multi-project build:

~~~text
root
├── app/
├── core/
└── web/
~~~

Nếu app/build.gradle có:

~~~groovy
plugins {
    id 'application'
}
~~~

chỉ app nhận task run và application DSL. :core không tự có run. Root build.gradle áp Spotless cũng không mặc nhiên tạo spotlessCheck trong tất cả subprojects.

Nếu một plugin cần được dùng ở core và app, mỗi project phải **áp plugin theo ý định** (trực tiếp hoặc thông qua convention plugin). Áp plugin tại root không tự tương đương áp cho toàn bộ project tree.

### 8.2. Plugin có thể áp plugin khác

Trong Java binary plugin:

~~~java
@Override
public void apply(Project project) {
    project.getPluginManager().apply("java");
}
~~~

Plugin tự viết có thể thiết lập preconditions bằng cách áp core Java plugin, thay vì đòi người dùng áp thủ công trong một thứ tự mong manh.

Khi plugin chỉ muốn làm việc **nếu Java plugin hiện diện**, dùng callback:

~~~java
project.getPluginManager().withPlugin("java", applied -> {
    // Code cấu hình Java-specific logic.
});
~~~

Đây là **snippet minh họa**, không phải toàn bộ class Java. withPlugin(...) cho phép đăng ký logic khi plugin kia đã có hoặc sẽ được áp sau, giúp tránh phụ thuộc vào thứ tự text của plugins blocks.

### 8.3. plugins block có những giới hạn cú pháp

plugins { ... } dùng constrained DSL để Gradle biết plugin requests sớm. Trong build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'com.diffplug.spotless' version '8.11.0'
}
~~~

Không viết:

~~~groovy
// Mẫu sai: plugins block không phải nơi chạy một vòng for tuỳ ý.
plugins {
    ['java', 'application'].each { pluginId ->
        id pluginId
    }
}
~~~

Nên sử dụng **literal IDs/versions** hoặc cơ chế chuẩn như pluginManagement hoặc alias(libs.plugins...). Không tính plugin IDs động từ một vòng lặp ngẫu nhiên trong plugins block.

Trong Groovy build script thông thường, plugins block phải xuất hiện ở phần đầu theo constraints của Gradle (sau những khối được Gradle cho phép như pluginManagement ở settings hoặc buildscript/plugins khi phù hợp). Không đặt một plugins { ... } bên trong task action hay method rồi kỳ vọng Gradle resolve như top-level plugin request.

### 8.4. Plugin<Project>, Plugin<Settings>, Plugin<Gradle>

Ba scope API:

| Generic plugin type | Áp cho đối tượng | Thích hợp khi |
|---|---|---|
| Plugin<Project> | Project, tasks/extensions/configurations của project | Java conventions, code quality, packaging |
| Plugin<Settings> | Settings, include builds/projects, plugin/dependency management | Quy tắc project structure hoặc global settings |
| Plugin<Gradle> | Gradle invocation/lifecycle | Init plugin, các hook build-wide phù hợp |

Bài lab implement **Plugin<Project>**. Không lấy class đó áp vào Settings rồi mong getTasks() hoạt động: Settings không có cùng project task model.

## 9. Publish plugin tự viết ra repository

Khi plugin đã cần dùng ở nhiều repositories, không nhất thiết copy thư mục build-logic vào tất cả codebases. Có thể publish một **binary plugin artifact**.

**plugin project/build.gradle — snippet:**

~~~groovy
plugins {
    id 'java-gradle-plugin'
    id 'maven-publish'
}

group = 'edu.example'
version = '1.0.0'

gradlePlugin {
    plugins {
        register('greeting') {
            id = 'edu.example.greeting'
            implementationClass = 'edu.example.GreetingPlugin'
        }
    }
}

publishing {
    repositories {
        maven {
            url = uri(layout.buildDirectory.dir('local-plugin-repo'))
        }
    }
}
~~~

Đây là mô hình publish plugin trong **project chứa GreetingPlugin.java**; không phải đoạn bổ sung cần thiết cho bài lab local included build ở mục 5.

Khi có java-gradle-plugin và maven-publish, Gradle có thể tạo:
- **Plugin implementation JAR** chứa code và descriptor.
- **Plugin marker publication** có tọa độ theo ID để plugins DSL tìm implementation.
- Maven metadata/POM cần thiết cho consumer.

Khi publish plugin lên Gradle Plugin Portal, cần quy trình riêng theo tài liệu Gradle Plugin Publish Plugin, tài khoản và quyền phát hành; không tự coi maven-publish vào local repo là đã có mặt trên Portal.

### 9.1. Consumer áp plugin được publish

**settings.gradle của consumer:**

~~~groovy
pluginManagement {
    repositories {
        maven {
            url = uri('../plugin-repo')
        }
        gradlePluginPortal()
    }
}
~~~

**build.gradle của consumer:**

~~~groovy
plugins {
    id 'edu.example.greeting' version '1.0.0'
}
~~~

Ở đây plugin **đã trở thành external published plugin đối với consumer**, dù do chính tổ chức viết. Phân loại “plugin ngoài” là theo **cách tiêu thụ/nguồn resolve**, còn “plugin tự xây dựng” là theo **ai sở hữu source**; hai cách nhìn có thể trùng nhau.

Mẫu path plugin-repo là ví dụ minh họa; phải trỏ tới nơi plugin implementation JAR và marker đã được publish thật. Nếu path không khớp repository output, Gradle sẽ không tìm thấy plugin.

### 9.2. TestKit và test plugin

Với java-gradle-plugin, Gradle TestKit có thể giúp chạy **functional test** trên một build sample rồi kiểm tra task output. Kiểm thử plugin không chỉ là test Java method apply; nên kiểm tra:

1. Plugin ID resolve và apply thành công.
2. Tasks/extensions được thêm đúng.
3. Task input/output annotations hợp lệ.
4. Behavior với cấu hình mặc định và người dùng override.
5. Plugin phối hợp đúng với core/community plugins.
6. Configuration cache, parallel execution, Gradle versions/JDKs được hỗ trợ.
7. Error messages có ích khi thiếu cấu hình.
8. Published plugin consumer có thể resolve marker và implementation.

**Không gọi task action trực tiếp trong unit test rồi nghĩ đã kiểm tra plugin wiring.** Một functional test tạo build tạm, chạy GradleRunner với tasks tương ứng và kiểm tra output/metadata là cách thực tế hơn.

## 10. Tổ chức plugin version và tính tái lập

### 10.1. Gradle Wrapper quyết định core plugin version

Core Java/Application Plugin có code gắn với Gradle distribution. Khi nâng Gradle Wrapper, behavior của core plugin có thể thay đổi (kể cả cảnh báo deprecation). Vì vậy một plugin đã tồn tại sẵn không có nghĩa API bất biến qua mọi Gradle version.

### 10.2. External plugin cần version có chủ đích

Pin version ở:
- app/build.gradle plugins block,
- settings.gradle pluginManagement.plugins,
- hoặc version catalog trong gradle/libs.versions.toml.

Chọn **một cơ chế quản trị** rõ ràng. Với phiên bản mới, kiểm tra compatibility matrix, release notes và các breaking changes. Một external plugin có thể thay API/task names khi nâng major version.

### 10.3. Custom plugin cần release lifecycle

Plugin tự xây dựng cũng cần:
- Plugin ID ổn định, không trùng core IDs.
- SemVer hoặc quy ước version nhất quán khi publish.
- Tài liệu về extensions/tasks.
- Binary compatibility nếu public Gradle API của plugin được project khác sử dụng.
- Migration notes khi đổi plugin ID hoặc cấu hình.
- Functional tests chạy trên những Gradle/JDK versions được hỗ trợ.

### 10.4. Plugin repositories có chính sách bảo mật riêng

pluginManagement.repositories và buildscript.repositories có thể tải executable build logic từ Internet. Tổ chức nên quản lý:
- Repository allowlist và trust boundaries.
- Credentials qua environment/Gradle properties an toàn, không hardcode.
- Các plugin IDs/versions được duyệt.
- Dependency verification và checksum policy khi áp dụng.
- Quy trình nâng phiên bản và roll back.
- Tư cách publisher/độ tin cậy của community plugin.

**Không đánh đồng dependency locking của app/runtimeClasspath với plugin classpath locking.** Plugin resolution có lifecycle và repository khác. Một gradle.lockfile của ứng dụng Java không tự pin bytecode của mọi plugin được Gradle chạy.

## 11. Các lỗi thường gặp và cách chẩn đoán

### Lỗi 1 — Plugin [id: 'com.example...'] was not found

**Nguyên nhân có thể:** ID sai, version không tồn tại, thiếu plugin repository, thiếu plugin marker artifact, offline cache chưa có plugin hoặc private credentials sai.

**Cách sửa:**
1. Kiểm tra ID/version tại nguồn publish đáng tin.
2. Kiểm tra pluginManagement.repositories trong settings.gradle.
3. Nếu plugin local, kiểm tra includeBuild hoặc buildSrc có đăng ký đúng ID.
4. Nếu plugin publish vào Maven, kiểm tra marker publication và implementation JAR.
5. Đọc nguyên nhân resolution, không thêm mavenCentral() vào dependencies rồi cho rằng plugin DSL sẽ tự sửa.

### Lỗi 2 — Core plugin bị yêu cầu version

**Nguyên nhân:** Tưởng Java language version là plugin version.

**Cách sửa:** Core plugin áp bằng id 'java' hoặc id 'application' **không có version**; Java toolchain đặt trong java { toolchain { ... } }. Gradle Wrapper chọn Gradle distribution có core plugin.

### Lỗi 3 — spotless { } không được nhận diện

**Nguyên nhân:** Spotless plugin chưa được áp vào project có spotless block, plugin resolution thất bại hoặc code đang đặt block vào root trong khi Spotless chỉ có ở subproject.

**Cách sửa:** Kiểm tra plugins { id 'com.diffplug.spotless' ... } tại đúng project, chạy :app:tasks --all để xem tasks, kiểm tra Gradle/plugin versions và extension DSL.

### Lỗi 4 — Không thấy greetFromPlugin

**Nguyên nhân:** Custom plugin chưa được áp vào :app; ID chưa đăng ký; included build chưa được include trong pluginManagement; tên task khác trong code.

**Cách sửa:** Kiểm tra :app:tasks --all, settings.gradle includeBuild('build-logic'), build-logic/build.gradle gradlePlugin ID/class, app/build.gradle plugins block và compile errors của Java plugin code.

### Lỗi 5 — Gradle báo không thấy implementation class

**Nguyên nhân:** Tên package/class trong implementationClass sai, file Java đặt sai thư mục package, plugin JAR thiếu compiled class hoặc descriptor không chính xác.

**Cách sửa:** Đối chiếu implementationClass = 'edu.example.GreetingPlugin' với package edu.example và đúng đường dẫn file. Dùng task pluginDescriptors/validatePlugins, kiểm tra output JAR khi publish.

### Lỗi 6 — Plugin local bị áp như external có version

**Nguyên nhân:** Plugin build-logic được include, nhưng consumer lại khai báo id 'edu.example.greeting' version '1.0.0' trong khi không có marker published tương ứng.

**Cách sửa:** Với included build, consumer thông thường chỉ dùng id 'edu.example.greeting' không có version. Nếu muốn publish và resolve theo version, hoàn thành quy trình publish marker/artifact trước.

### Lỗi 7 — Dùng repositories { mavenCentral() } nhưng plugin không resolve

**Nguyên nhân:** Project dependency repositories không phải plugin resolution repositories.

**Cách sửa:** Cấu hình pluginManagement.repositories trong settings.gradle, hoặc buildscript repositories trong tình huống legacy; bảo đảm portal/private repo đúng.

### Lỗi 8 — Build có plugin ngoài nhưng không có network

**Nguyên nhân:** Plugin JAR hoặc transitive dependencies chưa có trong cache; hoặc offline mode được bật.

**Cách sửa:** Cho phép đúng repository/proxy hoặc chuẩn bị cache artifact hợp lệ, dùng Gradle Wrapper/version cố định. --offline không tạo JAR Spotless chưa từng tải. Không copy plugin JAR không kiểm chứng vào Gradle cache.

### Lỗi 9 — Không hiểu vì sao plugin được áp hai lần

**Nguyên nhân:** Một convention plugin áp Java, còn project trực tiếp khai báo Java; nhiều build logic pieces cấu hình cùng extension/toolchain.

**Cách sửa:** Xem plugin ownership, thiết kế một convention plugin có trách nhiệm rõ. Gradle nhận diện plugin ID đã áp nhưng **configuration code của nhiều plugin khác nhau** vẫn có thể ghi đè conventions/set values.

### Lỗi 10 — Một plugin chỉ hoạt động trong root chứ không có ở subproject

**Nguyên nhân:** Plugin được apply ở root project, trong khi task cần chạy ở :app.

**Cách sửa:** Áp plugin ở subproject tương ứng. Root apply false chỉ khai báo version/classpath, không áp task sang subprojects. Convention plugin giúp kiểm soát tập project sử dụng.

### Lỗi 11 — plugins block chứa biến động hoặc vòng lặp

**Nguyên nhân:** plugins DSL có constrained syntax; ID/version trong project plugins block không được tự tính bằng code tùy ý.

**Cách sửa:** Dùng literal, pluginManagement phiên bản tập trung hoặc version catalog alias. Nếu cần logic plugin resolution động, dùng đúng pluginManagement.resolutionStrategy ở settings thay vì đặt if/for trong plugins block.

### Lỗi 12 — Precompiled plugin không tìm thấy community plugin

**Nguyên nhân:** Precompiled script áp id của community plugin nhưng **build-logic chưa khai báo dependency tới plugin implementation**.

**Cách sửa:** Thêm repository gradlePluginPortal và dependency implementation 'plugin.id:plugin.id.gradle.plugin:version' trong build logic build theo tài liệu plugin; trong precompiled script plugins block dùng ID không kèm version.

### Lỗi 13 — Lỗi cấu hình Java toolchain do thiếu JDK 17

**Nguyên nhân:** Gradle có Java toolchain languageVersion=17 nhưng máy không có JDK phù hợp và chưa cấu hình mechanism provision.

**Cách sửa:** Cài JDK17 hoặc cấu hình toolchain resolver/provisioning. Không sửa Java plugin version để “có JDK17”; đây là hai vấn đề khác.

### Lỗi 14 — Đặt code tốn thời gian trong Plugin.apply

**Nguyên nhân:** Plugin scan file, truy cập network, chạy ProcessBuilder hoặc truy vấn task outputs ngay lúc cấu hình.

**Cách sửa:** Đăng ký tasks lazily, khai báo inputs/outputs và chuyển công việc vào @TaskAction, Worker API hoặc build services khi thích hợp. Điều này giúp configuration cache và performance tốt hơn.

### Lỗi 15 — Plugin tự viết vi phạm Gradle API khi nâng version

**Nguyên nhân:** Plugin dùng API deprecated/removed, buildscript internal API hoặc classpath conflict khi Gradle major version đổi.

**Cách sửa:** Chạy validatePlugins, TestKit functional tests trên các Gradle versions được hỗ trợ, dùng public Gradle API, đọc upgrade guides. Không chỉ tăng plugin version rồi tin mọi behavior giữ nguyên.

### Lỗi 16 — Duplicate ID / namespace không hợp lệ

**Nguyên nhân:** Plugin tự xây dùng tên trùng core plugin hoặc ID trong namespace reserved như org.gradle.

**Cách sửa:** Chọn reverse-domain ID thuộc tổ chức, ví dụ edu.example.greeting, kiểm tra plugin ID restrictions và marker publication. Không publish plugin ID mà tổ chức không sở hữu.

## 12. Quy tắc chọn plugin phù hợp

| Nhu cầu | Lựa chọn nên cân nhắc |
|---|---|
| Build Java JAR | Core java hoặc java-library |
| Chạy Java application | Core application |
| Publish library Maven | Core maven-publish |
| Format/kiểm tra source | External Spotless hoặc công cụ đã chuẩn hóa của tổ chức |
| Mặc định Java 17, compiler encoding chung | Precompiled convention plugin |
| Task tạo artifact đặc thù, có input/output và extension phức tạp | Binary custom plugin |
| Shared build logic trong một repo lớn | Included build build-logic |
| Plugin dùng ở nhiều repositories | Publish binary plugin, có ID/version/marker |
| Thử nghiệm ngắn | Build script task hoặc buildSrc prototype |
| Version policy cho external plugins | pluginManagement hoặc version catalog |
| Logic chỉ áp khi plugin khác hiện diện | pluginManager.withPlugin hoặc plugins.withId |
| Bảo đảm plugin không tự ảnh hưởng toàn build | Áp ở từng subproject, không cross-project config tùy tiện |

**Quy tắc thực dụng:** Dùng core plugin khi nó đáp ứng bài toán, chọn external plugin được duy trì tốt khi có năng lực chuyên biệt, và tự viết plugin khi cần **chuẩn hóa hoặc nghiệp vụ build** không có giải pháp phù hợp. Tránh tự tạo lại JavaPlugin/Spotless từ đầu chỉ vì có thể viết Plugin<Project>.

## 13. Checklist triển khai và review plugin

1. Xác định **plugin ID** và **plugin source** rõ ràng: Gradle core, community repository, buildSrc/included build hay published internal.
2. Plugin có áp đúng **Project/Settings/Gradle** scope không?
3. Core plugin có đang bị gán version sai không?
4. External plugin có version đã kiểm thử, phù hợp Gradle Wrapper/JDK không?
5. settings.gradle pluginManagement.repositories có cho phép plugin được resolve không?
6. Custom plugin ID có được đăng ký và mapping implementationClass đúng không?
7. Nếu dùng included build, đã includeBuild('build-logic') trong pluginManagement khi cần chưa?
8. Nếu dùng precompiled plugin, plugin dependency của external ID đã có trong build-logic chưa?
9. Plugin có tạo task bằng tasks.register và quản lý inputs/outputs theo API không?
10. Extension có dùng managed Property với convention/set rõ ràng không?
11. Có xem plugin tasks/extensions **trong đúng subproject** không?
12. Có giữ plugin code không can thiệp ngẫu nhiên vào root hoặc subprojects ngoài scope không?
13. Có tránh network/file IO bất ngờ trong configuration phase không?
14. Có functional tests bằng TestKit hoặc build sample chạy trên Gradle/JDK tương thích không?
15. Plugin đã publish có marker metadata và artifact implementation hợp lệ không?
16. Plugin version, repository, license và supply-chain policy có được kiểm soát không?
17. Có hướng dẫn migration khi upgrade Gradle/plugin major version không?
18. CI có chạy từ clean checkout để không phụ thuộc vào plugin cache sẵn có trên một máy không?

## 14. Bài tập tự kiểm tra

**Bài 1.** id 'java' thuộc loại plugin nào? Có nên viết id 'java' version '17' không?

**Bài 2.** Spotless được thêm qua id 'com.diffplug.spotless' version '8.11.0'. Đây là dependency application runtime hay plugin chạy trong Gradle build process?

**Bài 3.** Vì sao repositories { mavenCentral() } trong app/build.gradle không tự bảo đảm mọi community plugin đều resolve được?

**Bài 4.** Trong main settings.gradle, pluginManagement { includeBuild('build-logic') } có vai trò gì?

**Bài 5.** Vì sao app có thể dùng id 'edu.example.greeting' mà không ghi version trong bài lab?

**Bài 6.** GreetingPlugin được đăng ký implementationClass='edu.example.GreetingPlugin', nhưng source file Java có package demo.plugin. Điều gì có thể xảy ra?

**Bài 7.** Vì sao plugin không nên gọi GreetingTask.greet() ngay trong apply(Project), mà nên tasks.register(...)?

**Bài 8.** greeting { recipient.set('Nam') } khác gì khi bỏ cả block, nếu plugin đặt convention('Gradle')?

**Bài 9.** Một subproject chưa apply plugin Spotless nhưng root đã có id 'com.diffplug.spotless' version '8.11.0' apply false. Subproject có task spotlessCheck chưa?

**Bài 10.** Một convention plugin áp java-library và đặt toolchain17 dùng chung ở nhiều modules. Nên viết bằng precompiled script plugin hay copy-paste logic vào mọi build.gradle?

**Bài 11.** Plugin Java tự viết muốn được dùng ở năm repositories khác nhau. Nên copy class Java vào từng project hay publish versioned binary plugin với marker?

**Bài 12.** Plugin marker artifact dùng làm gì trong plugins DSL?

**Bài 13.** Muốn áp external plugin từ precompiled script plugin mà Gradle không tìm thấy class implementation, nên kiểm tra dependency ở đâu?

**Bài 14.** Plugin<Project> và Plugin<Settings> có cùng phạm vi và cùng API tasks không?

**Bài 15.** Nếu nâng Gradle Wrapper mà core Java Plugin thay đổi behavior, cách nào kiểm tra compatibility an toàn?

**Bài 16.** Vì sao plugin version 8.11.0 cần được pin có chủ đích thay vì trông vào latest mỗi lần build?

**Bài 17.** Khi chỉ biết một plugin bị báo not found, nên kiểm tra ID, version, marker, repositories hay đổi ngay dependencies implementation?

**Bài 18.** Vì sao buildSrc và build-logic đều là nguồn local plugin nhưng có đặc tính classpath/configuration performance khác nhau?

### Đáp án gợi ý

1. **Core plugin** đi kèm Gradle; **không** gắn version '17' cho id 'java'. Java version đặt ở toolchain.
2. **Plugin code của Gradle build**, không phải dependency runtime của Main.java.
3. pluginManagement.repositories giải quyết plugins DSL; repositories của project chủ yếu resolve application/library dependencies.
4. Đăng ký included plugin build để custom plugin ID được Gradle tìm, compile và áp vào main build.
5. ID được cung cấp từ included build, không cần resolve một published version từ Portal.
6. Gradle có thể không tìm thấy implementation class/descriptor; tên package/class phải khớp.
7. Task action cần chạy ở execution phase; tasks.register là lazy wiring đúng mô hình.
8. set('Nam') override default, output Nam; nếu bỏ block thì default Gradle được sử dụng.
9. **Chưa**. apply false không áp plugin vào root hay subproject; subproject phải apply rõ.
10. **Precompiled convention plugin** hoặc binary plugin phù hợp; tránh copy/paste và cross-project configuration thiếu kiểm soát.
11. **Publish binary plugin** có ID/version/marker, kiểm thử và quản lý release.
12. Nối yêu cầu plugin ID + version tới tọa độ implementation JAR trong repository.
13. Trong **build logic build**: repositories và implementation dependency tới plugin marker/implementation, không chỉ project dependency repositories.
14. **Không**. Project plugin cấu hình tasks/extensions của project; Settings plugin dùng Settings lifecycle/API.
15. TestKit/functional tests, validatePlugins, kiểm tra Gradle/JDK compatibility matrix và upgrade notes.
16. Pin version giúp build tái lập và kiểm soát breaking changes/supply chain.
17. Kiểm tra ID/version, pluginManagement.repositories, marker, includeBuild/buildSrc, credentials và Gradle logs.
18. buildSrc tự đưa code vào classpath nhiều projects; included build tách build logic, giảm coupling và dễ mở rộng/testing/publishing.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — Introduction to Plugins](https://docs.gradle.org/current/userguide/plugins.html): ba nguồn core/community/local và ba cách viết script/precompiled/binary plugins.
- [Gradle User Manual — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): plugins DSL, pluginManagement, plugin repositories, plugin markers, apply false và legacy apply.
- [Gradle User Manual — Plugin Basics](https://docs.gradle.org/current/userguide/plugin_basics.html): tasks, extensions, configurations được plugin đóng góp.
- [Gradle User Manual — Binary Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_binary.html): Plugin<Project>, plugin ID, implementation class và artifact.
- [Gradle User Manual — Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): java-gradle-plugin, descriptor, validation và TestKit integration.
- [Gradle User Manual — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html): convention plugins với buildSrc/included build.
- [Gradle User Manual — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): buildSrc, build-logic và tách cấu hình giữa các projects.
- [Gradle User Manual — Groovy Gradle Plugin](https://docs.gradle.org/current/userguide/groovy_gradle_plugin.html): precompiled Groovy DSL script plugins.
- [Gradle Plugin Portal — Spotless](https://plugins.gradle.org/plugin/com.diffplug.spotless): plugin ID, phiên bản, cách áp dụng và dependencies.
- [Gradle User Manual — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): convention plugins, included build và tránh cross-project configuration.
- [Gradle User Manual — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): JDK/Gradle compatibility.

**Ghi nhớ:** **Core plugins** đi kèm Gradle, không cần version riêng. **External plugins** cần plugin ID, version/source phù hợp và được resolve trên plugin classpath. **Custom plugins** là build logic do bạn sở hữu: script, precompiled convention hay binary Plugin<Project>. Dùng plugins DSL, tổ chức version bằng pluginManagement/catalog, ưu tiên included build cho build logic tái sử dụng, đăng ký task lazily, kiểm tra scope từng project và kiểm thử plugin trước khi dùng rộng rãi.