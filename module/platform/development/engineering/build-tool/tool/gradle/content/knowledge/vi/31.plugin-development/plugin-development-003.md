# Khai báo plugin id, implementationClass và metadata trong Gradle

## 1. Vấn đề: có class Plugin<Project> nhưng consumer không áp dụng được plugin

Một nhóm phát triển viết class Java triển khai `org.gradle.api.Plugin<Project>`, biên dịch thành JAR, nhưng khi project khác khai báo:

~~~kotlin
plugins {
    id("dev.example.hello") version "1.0.0"
}
~~~

Gradle có thể báo:

~~~text
Plugin [id: 'dev.example.hello', version: '1.0.0'] was not found
~~~

Hoặc tìm thấy plugin ID nhưng khi áp dụng lại gặp lỗi không nạp được implementation class. Nguyên nhân thường không phải code `apply(Project)`, mà do **ba lớp định danh và metadata chưa khớp**:

1. **Plugin ID** — tên logic consumer yêu cầu, ví dụ `dev.example.hello`.
2. **Implementation class** — tên Java class triển khai plugin, ví dụ `dev.example.gradle.HelloPlugin`.
3. **Metadata đóng gói và phát hành** — file descriptor `META-INF/gradle-plugins/<plugin-id>.properties` trong JAR, cùng **plugin marker module** nếu consumer resolve plugin bằng `plugins { id(...) version ... }` từ Maven/Plugin Portal.

Để một binary plugin có thể áp dụng ổn định trong build khác, cần hiểu và kiểm đúng **cả ba**, không chỉ copy class Java vào JAR.

Bài này thuộc chủ đề **Phát triển plugin** của module **Build Tool Gradle**, tập trung trực tiếp vào **khai báo plugin id, implementationClass và metadata**. Ví dụ xuyên suốt dùng Java 17, Gradle Kotlin DSL, `java-gradle-plugin`, `maven-publish`, một Maven repository local và một consumer build áp dụng plugin thật.

### 1.1. Sau bài học bạn sẽ làm được gì?

- Phân biệt tên declaration trong `gradlePlugin.plugins.create("hello")` với plugin ID, package Java, class name và Maven coordinates.
- Đăng ký `id` và `implementationClass` chính xác qua `java-gradle-plugin`.
- Hiểu `pluginDescriptors` sinh descriptor `META-INF/gradle-plugins/dev.example.hello.properties` và ý nghĩa key `implementation-class`.
- Phân biệt **plugin descriptor ở trong JAR** với **plugin marker artifact ở Maven repository**.
- Hiểu mối quan hệ giữa `pluginMaven` và `helloPluginMarkerMaven` do Gradle tạo khi dùng `maven-publish`.
- Thiết lập metadata bổ sung `displayName`, `description`, `tags` và trường website/VCS khi xuất bản.
- Biết thời điểm Gradle dùng `pluginManagement.repositories`, `pluginManagement.includeBuild` hay legacy `buildscript.classpath`.
- Tạo một binary plugin Java 17 runnable, publish vào file-based Maven repository, áp dụng bằng `plugins { ... }` từ consumer.
- Tự kiểm descriptor/class trong JAR bằng Java 17 thuần JDK (không cần thư viện ngoài).
- Chẩn đoán marker missing, implementationClass sai package, JAR thiếu class, duplicate plugin ID, Java version sai và metadata không khớp.
- Viết TestKit functional test và kiểm các file publication trước khi promote release.

**Phạm vi:** plugin binary triển khai `Plugin<Project>`. Plugin ở scope `Settings`/`Gradle`, precompiled script plugin và các cách phát hành khác được giải thích để phân biệt nhưng không thay thế bài thực hành chính.

## 2. Mô hình định danh: bốn cái tên khác nhau

Đầu tiên xem một ví dụ đăng ký plugin:

~~~kotlin
gradlePlugin {
    plugins {
        create("hello") {
            id = "dev.example.hello"
            implementationClass = "dev.example.gradle.HelloPlugin"
            displayName = "Example Hello Plugin"
            description = "Registers a simple greeting task"
        }
    }
}
~~~

Và ở đầu build script producer:

~~~kotlin
group = "dev.example"
version = "1.0.0"
~~~

Nếu project producer có `rootProject.name = "hello-plugin"`, ta có **những tên khác vai trò**:

| Giá trị | Ý nghĩa | Nơi xuất hiện |
| --- | --- | --- |
| `hello` | **Declaration name** nội bộ trong container `gradlePlugin.plugins` | Build script của producer |
| `dev.example.hello` | **Plugin ID** public mà consumer áp dụng | `plugins { id("dev.example.hello") }` |
| `dev.example.gradle.HelloPlugin` | **Fully qualified implementation class** | `implementationClass` và plugin descriptor |
| `dev.example:hello-plugin:1.0.0` | **Maven implementation module** mặc định của project producer | Repository chứa implementation JAR |
| `dev.example.hello:dev.example.hello.gradle.plugin:1.0.0` | **Plugin marker module** theo quy tắc `id:id.gradle.plugin:version` | Repository giúp resolve plugin ID |
| `Example Hello Plugin` | Tên hiển thị cho người tìm hiểu plugin | Metadata mô tả/Plugin Portal |
| `1.0.0` | Version của publication/plugin release | Consumer `version "1.0.0"` |

Đây là điểm cốt lõi: **plugin ID không phải Java class name; plugin ID cũng không phải Maven artifactId của implementation JAR**.

### 2.1. Tên create("hello") dùng để làm gì?

`create("hello")` đặt tên một phần tử trong container `gradlePlugin.plugins`. Tên này phải duy nhất **trong project plugin producer** và Gradle sử dụng nó khi tạo những task/publication names, ví dụ:

~~~text
helloPluginMarkerMaven
~~~

Nó **không** trở thành ID public mặc định nếu bạn đã khai:

~~~kotlin
id = "dev.example.hello"
~~~

Consumer sẽ viết `id("dev.example.hello")`, không phải `id("hello")` trừ khi một plugin khác thực sự có ID đó.

### 2.2. Plugin ID không phải Java package

Một plugin ID có thể trông giống package theo reverse-DNS convention, nhưng Gradle không lấy nó làm `package` của class implementation.

~~~text
Plugin ID:           dev.example.hello
Java package:        dev.example.gradle
Implementation type: dev.example.gradle.HelloPlugin
~~~

Ba chuỗi có thể không trùng nhau. **Điều bắt buộc là metadata khai đúng implementationClass thực sự có trong artifact**.

### 2.3. Plugin version lấy ở đâu?

Trong ví dụ:

~~~kotlin
group = "dev.example"
version = "1.0.0"
~~~

`project.version` tạo version của publication. Consumer dùng `version "1.0.0"` để resolve plugin marker cùng version. Bạn không đặt `version` riêng trong `create("hello")` như một trường public luôn độc lập; quy trình Maven publication/Plugin Portal lấy version từ project publication.

### 2.4. Quy tắc chọn plugin ID

Nên dùng ID rõ namespace, chẳng hạn:

~~~text
dev.example.hello
dev.example.java-quality
io.example.codegen
~~~

Quy ước:

- Dùng reverse-domain/namespace thuộc tổ chức để tránh xung đột.
- Dùng ký tự đơn giản, ổn định và có ý nghĩa; tránh tên dễ nhầm với core plugin.
- Không chiếm namespace dự trữ của Gradle hoặc tên thuộc sở hữu tổ chức khác.
- Không đưa version vào plugin ID như `dev.example.hello.v1` trừ khi chính sách sản phẩm thật sự yêu cầu hai plugin IDs tách biệt.
- Đổi plugin ID là **breaking change** cho người dùng `plugins { }`, cần kế hoạch deprecation/alias/migration nếu đã phát hành.

Không đoán quy tắc chính xác của mọi plugin repository từ cú pháp Java package: plugin ID phải đáp ứng validator/quy định của Gradle và nền tảng phát hành đang dùng.

## 3. Implementation class phải tuân thủ contract nào?

Một Java binary plugin tối thiểu có dạng:

~~~java
package dev.example.gradle;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class HelloPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getLogger().lifecycle("Hello plugin applied");
    }
}
~~~

Đây là **snippet minh họa**, chưa có task và không phải toàn bộ project của bài lab. Điều quan trọng:

1. Class là `public`, tên `HelloPlugin` phải đúng chữ hoa/thường.
2. Package được khai `dev.example.gradle`, nên fully qualified name là `dev.example.gradle.HelloPlugin`.
3. Class triển khai `Plugin<Project>`.
4. Gradle gọi `apply(Project)` khi plugin được **áp dụng**, thường trong configuration phase.
5. Class được Gradle load bằng plugin classloader, không phải bằng JVM application `main(String[])`.
6. Class có constructor thích hợp để Gradle tạo instance (ví dụ class đơn giản có public no-arg constructor mặc định).
7. Classfile phải tương thích **JVM đang chạy Gradle**, không chỉ JDK target của application.
8. Code nên cấu hình project một cách lazy, tránh eager task creation và không truy cập mutable state của project khác khi không cần.

### 3.1. implementationClass không chứa .java hay .class

Đúng:

~~~kotlin
implementationClass = "dev.example.gradle.HelloPlugin"
~~~

Sai:

~~~kotlin
implementationClass = "dev/example/gradle/HelloPlugin.class"
~~~

Sai:

~~~kotlin
implementationClass = "dev.example.gradle.HelloPlugin.java"
~~~

Đây là **các ví dụ cố ý sai**. Giá trị phải là **binary class name**, với dấu chấm ngăn package/class, không phải filesystem path.

### 3.2. Implementation class có thể triển khai Plugin<Settings> không?

Gradle cho phép plugins ở nhiều scopes, điển hình:

| Target type | Scope áp dụng | Ví dụ use case |
| --- | --- | --- |
| `Plugin<Project>` | Một project | Tasks, extensions, dependencies, Java conventions |
| `Plugin<Settings>` | Settings | Repositories, include projects, plugin management |
| `Plugin<Gradle>` | Gradle object/init context | Global initialization/monitoring logic phù hợp |

Bài thực hành dùng `Plugin<Project>` và áp ở `consumer/build.gradle.kts`. Không đem class target `Project` áp vào settings plugin block rồi kết luận implementationClass sai; khi thiết kế settings plugin, dùng đúng generic target/interface/lifecycle.

### 3.3. implementationClass không cần cùng tên file script

Binary plugin `HelloPlugin.java` thường ở:

~~~text
src/main/java/dev/example/gradle/HelloPlugin.java
~~~

Còn precompiled script plugin có file `hello.gradle.kts` được Gradle biên dịch tự động thành plugin implementation khác. **Không trộn hai workflow**: ví dụ binary plugin ở đây cần `implementationClass` để đăng ký rõ, còn precompiled script plugins dùng cơ chế tạo ID và classes từ file script.

## 4. Plugin descriptor: metadata bên trong JAR

Gradle nhận biết implementation class thông qua một **plugin descriptor** có đường dẫn:

~~~text
META-INF/gradle-plugins/<plugin-id>.properties
~~~

Với ID `dev.example.hello`, descriptor nằm ở:

~~~text
META-INF/gradle-plugins/dev.example.hello.properties
~~~

Và nội dung chính:

~~~properties
implementation-class=dev.example.gradle.HelloPlugin
~~~

**Chú ý dấu gạch ngang:** key trong file descriptor là `implementation-class`, trong Kotlin DSL lại là `implementationClass`. Đây là hai biểu diễn của **cùng mapping**, không phải lỗi typo.

### 4.1. Descriptor không có nghĩa JAR đã publish

Khi `java-gradle-plugin` đăng ký plugin, nó tạo task `pluginDescriptors` và đưa descriptors vào JAR output. Đây là metadata **nằm bên trong implementation JAR**.

Bạn có thể kiểm tra:

~~~bash
gradle pluginDescriptors jar
jar --list --file build/libs/hello-plugin-1.0.0.jar
~~~

Tìm:

~~~text
META-INF/gradle-plugins/dev.example.hello.properties
dev/example/gradle/HelloPlugin.class
dev/example/gradle/HelloTask.class
~~~

Các directory entries khác có thể xuất hiện, thứ tự không phải hợp đồng. Nếu descriptor có nhưng class implementation không tồn tại, plugin vẫn không thể được load.

### 4.2. Vì sao không nên tự viết descriptor trong trường hợp bình thường?

Có thể tạo thủ công file `src/main/resources/META-INF/gradle-plugins/...properties` nếu không dùng plugin development plugin, nhưng rất dễ:

- Đặt tên file sai ID.
- Ghi sai `implementation-class`.
- Quên đóng class vào JAR.
- Tạo duplicate descriptor khi `java-gradle-plugin` cũng sinh file.
- Quên Maven plugin marker khi publish.
- Không có task validation/TestKit metadata tiêu chuẩn.

**Khuyến nghị:** dùng `java-gradle-plugin` để sinh descriptor từ **một nguồn khai báo chính** ở `gradlePlugin { plugins { ... } }`.

### 4.3. Descriptor có giữ displayName/description không?

Thông thường file `*.properties` của plugin descriptor cần mapping `implementation-class`. Những metadata để hiển thị trên Plugin Portal như `displayName`, `description`, `tags` **không phải** những property keys cần viết vào file này.

Điều đó giải thích vì sao có một JAR có descriptor chính xác nhưng thiếu thông tin mô tả khi publish, hoặc ngược lại publication có description tốt nhưng implementation class load lỗi.

## 5. Plugin marker artifact: metadata ở repository

Nếu consumer dùng:

~~~kotlin
plugins {
    id("dev.example.hello") version "1.0.0"
}
~~~

Gradle chỉ thấy **plugin ID + version**, không biết Maven coordinates của implementation JAR. Để resolve qua plugin repositories, Gradle tìm **plugin marker artifact** theo quy tắc:

~~~text
groupId    = plugin.id
artifactId = plugin.id.gradle.plugin
version    = requested version
~~~

Với ví dụ:

~~~text
dev.example.hello:dev.example.hello.gradle.plugin:1.0.0
~~~

Marker module (thường là Maven POM) khai dependency tới **implementation module**:

~~~text
dev.example:hello-plugin:1.0.0
~~~

Sau đó Gradle resolve implementation JAR và đọc descriptor để load class.

### 5.1. Sơ đồ đường đi từ consumer tới code

~~~text
consumer/build.gradle.kts
plugins {
  id("dev.example.hello") version "1.0.0"
}
           |
           v
pluginManagement repositories
           |
           v
Marker GAV:
dev.example.hello:dev.example.hello.gradle.plugin:1.0.0
           |
           v
Marker POM dependency:
dev.example:hello-plugin:1.0.0
           |
           v
Implementation JAR:
hello-plugin-1.0.0.jar
           |
           v
META-INF/gradle-plugins/dev.example.hello.properties
  implementation-class=dev.example.gradle.HelloPlugin
           |
           v
dev.example.gradle.HelloPlugin implements Plugin<Project>
           |
           v
apply(Project) -> register pluginHello task
~~~

**Plugin marker không phải descriptor:** Marker là **artifact/module metadata để resolution**, descriptor là **file trong implementation JAR để runtime load class**.

### 5.2. Marker coordinates khác implementation coordinates

| Thành phần | Ví dụ |
| --- | --- |
| Plugin ID | `dev.example.hello` |
| Plugin version | `1.0.0` |
| Marker group | `dev.example.hello` |
| Marker artifact | `dev.example.hello.gradle.plugin` |
| Marker module GAV | `dev.example.hello:dev.example.hello.gradle.plugin:1.0.0` |
| Implementation group | `dev.example` |
| Implementation artifact | `hello-plugin` |
| Implementation GAV | `dev.example:hello-plugin:1.0.0` |
| Runtime class | `dev.example.gradle.HelloPlugin` |

Nếu plugin project có name khác, implementation artifact có thể khác; marker dependency cần trỏ đúng publication. Không suy ra implementation artifactId từ plugin ID.

### 5.3. Plugin marker được tạo tự động như thế nào?

Khi kết hợp:

~~~kotlin
plugins {
    `java-gradle-plugin`
    `maven-publish`
}
~~~

Gradle tự cấu hình publications khi `gradlePlugin.automatedPublishing` mặc định vẫn bật:

- Một main publication tên `pluginMaven` chứa implementation component/JAR.
- Một marker publication cho **mỗi plugin declaration**, tên dạng `<declarationName>PluginMarkerMaven`. Với `create("hello")`, tên thường là `helloPluginMarkerMaven`.

Không cần tự viết marker POM bằng tay trong lab. Nếu chủ động set `automatedPublishing = false` hoặc tùy biến publications sâu, bạn phải tự quản lý những artifacts/markers tương ứng; đừng giả định plugin vẫn được resolve bằng `plugins { }`.

### 5.4. Nếu chỉ publish JAR mà quên marker?

Consumer dùng:

~~~kotlin
plugins {
    id("dev.example.hello") version "1.0.0"
}
~~~

có thể báo plugin not found dù file `hello-plugin-1.0.0.jar` đã nằm trong repository. Gradle không tự đoán `dev.example:hello-plugin` từ ID `dev.example.hello`.

Có thể dùng `pluginManagement.resolutionStrategy.eachPlugin { useModule(...) }` như một phương án mapping thủ công có kiểm soát; nhưng với plugin mới nên **publish marker đúng chuẩn** bằng `java-gradle-plugin`.

## 6. Metadata bổ sung trong gradlePlugin

Một declaration đầy đủ hơn:

~~~kotlin
gradlePlugin {
    plugins {
        create("hello") {
            id = "dev.example.hello"
            implementationClass = "dev.example.gradle.HelloPlugin"
            displayName = "Example Hello Plugin"
            description = "Registers a reproducible greeting task"
            tags = listOf("example", "build-logic", "verification")
        }
    }
}
~~~

### 6.1. Những field đó phục vụ gì?

| Trường | Bắt buộc để load plugin? | Vai trò |
| --- | --- | --- |
| `id` | Có | Public plugin identity |
| `implementationClass` | Có | Class Gradle cần instantiate/apply |
| `displayName` | Không phải mapping runtime | Human-readable name cho plugin listing |
| `description` | Không phải mapping runtime | Mô tả công năng, giúp discoverability |
| `tags` | Không phải mapping runtime | Chủ đề/categories cho Plugin Portal |
| Project `group`, `version` | Quan trọng khi publish | Maven implementation coordinates/release |
| `website`, `vcsUrl` | Metadata publish portal | Link dự án/source repository khi dùng Plugin Publish Plugin |

Trong bài lab publish **local Maven repo**, khai `displayName/description/tags` để minh họa. Nếu chỉ chạy plugin từ included build hoặc JAR local, sự có mặt của tags **không làm thay đổi behavior của `apply`**.

### 6.2. website và vcsUrl đặt ở đâu?

Với Plugin Publish Plugin trên những bản hỗ trợ, `gradlePlugin` có metadata cấp project:

~~~kotlin
gradlePlugin {
    website = providers.gradleProperty("pluginWebsite")
        .orElse("https://example.org/gradle-plugins")
        .get()
    vcsUrl = providers.gradleProperty("pluginVcsUrl")
        .orElse("https://example.org/gradle-plugins/source")
        .get()
}
~~~

Đoạn này **minh họa cấu hình**, không nằm trong project lab runnable. Các URL `example.org` là tên miền dành cho ví dụ, không phải trang công bố plugin thật. Khi xuất bản public, dùng website/VCS **thực của project**, đúng policy và xác minh links.

### 6.3. Metadata không sửa được code sai

Nếu description là “Java 17 support” nhưng JAR được compile major 65, plugin vẫn không chạy trên Gradle JVM Java17. Nếu `implementationClass` sai, `displayName` hay `tags` đẹp cũng không giúp load class. Build pipeline cần kiểm **runtime descriptor**, classfile, marker POM và consumer behavior riêng.

## 7. Project Java 17 đầy đủ: plugin producer và consumer

Mục này tạo **một Gradle binary plugin thật**, publish local, rồi consumer apply bằng ID. Không có thư viện third-party ngoài Gradle core APIs; Maven repository dùng file path trong workspace, không yêu cầu tài khoản public.

### 7.1. Cây thư mục

~~~text
plugin-id-metadata-lab/
├── plugin/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/
│       └── main/
│           └── java/
│               └── dev/
│                   └── example/
│                       └── gradle/
│                           ├── HelloPlugin.java
│                           └── HelloTask.java
├── consumer/
│   ├── settings.gradle.kts
│   └── build.gradle.kts
└── verifier/
    └── PluginDescriptorCheck.java
~~~

Khi publish sẽ xuất hiện thêm:

~~~text
plugin/build/
├── libs/hello-plugin-1.0.0.jar
└── repo/
    └── (Maven implementation + marker modules)
~~~

**Yêu cầu:** JDK 17, Gradle release tương thích với JVM/Gradle Java plugin APIs và kết nối/caches cho Gradle distribution nếu cần. Mọi code Java dùng Java 17-compatible APIs. Nếu project chưa có Wrapper, lệnh ví dụ `gradle -p ...` giả định Gradle được cài trong PATH; sau đó nên tạo Wrapper, pin và commit cho dự án thực tế.

### 7.2. plugin/settings.gradle.kts

~~~kotlin
rootProject.name = "hello-plugin"
~~~

`rootProject.name` là cơ sở tên implementation artifact mặc định (`hello-plugin`). Nó **không** xác định plugin ID; ID được đặt riêng trong `gradlePlugin`.

### 7.3. plugin/build.gradle.kts — bản đầy đủ

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    `java-gradle-plugin`
    `maven-publish`
}

group = "dev.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

gradlePlugin {
    plugins {
        create("hello") {
            id = "dev.example.hello"
            implementationClass = "dev.example.gradle.HelloPlugin"
            displayName = "Example Hello Plugin"
            description = "Adds a greeting task to a Gradle project"
            tags = listOf("example", "build-logic", "verification")
        }
    }
}

publishing {
    repositories {
        maven {
            name = "lab"
            url = uri(layout.buildDirectory.dir("repo"))
        }
    }
}
~~~

Giải thích:

- `java-gradle-plugin` là core plugin hỗ trợ phát triển binary Gradle plugins: thêm Java/Gradle API support, đăng ký descriptor/validation/testing tasks.
- `maven-publish` đăng ký publish tasks và phối hợp với `java-gradle-plugin` tạo **implementation publication + marker publication**.
- `group/version` xác định release identity.
- `toolchain=17`/`options.release=17` kiểm soát bytecode; plugin class phải chạy được trong Gradle daemon JVM được support.
- `create("hello")` là **declaration name**.
- `id="dev.example.hello"` là public plugin ID.
- `implementationClass="dev.example.gradle.HelloPlugin"` khớp với Java source ở mục 7.4.
- `displayName/description/tags` là human-facing metadata, không nằm trong descriptor key `implementation-class`.
- `publishing.repositories.maven` trỏ tới `plugin/build/repo`, không upload Internet.
- Không cần tự tạo `MavenPublication`/marker POM cho lab; Gradle tự làm khi automated publishing bật.

**Tính runnable:** Code trên là **toàn bộ** `plugin/build.gradle.kts`. Không ghép thêm một `plugins { }` thứ hai cùng chức năng vào file này.

### 7.4. plugin/src/main/java/dev/example/gradle/HelloPlugin.java

~~~java
package dev.example.gradle;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class HelloPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getTasks().register(
                "pluginHello",
                HelloTask.class,
                task -> {
                    task.setGroup("verification");
                    task.setDescription(
                            "Prints a deterministic plugin greeting");
                    task.getRecipient().convention("Gradle");
                }
        );
    }
}
~~~

Đây là implementation class được khai `implementationClass`. Nó:

1. Triển khai đúng `Plugin<Project>`.
2. Có constructor mặc định phù hợp.
3. Chỉ tác động **Project đã apply plugin**.
4. Đăng ký `pluginHello` một cách lazy bằng `TaskContainer.register(...)`, không dùng eager `create(...)`.
5. Chuyển input mặc định cho task qua Gradle `Property<String>`.
6. Không capture `Project` trong `@TaskAction`.
7. Không tạo task chạy ngay tại `apply`; task action chỉ chạy khi được yêu cầu.

### 7.5. plugin/src/main/java/dev/example/gradle/HelloTask.java

~~~java
package dev.example.gradle;

import org.gradle.api.DefaultTask;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.TaskAction;

public abstract class HelloTask extends DefaultTask {
    @Input
    public abstract Property<String> getRecipient();

    @TaskAction
    public void sayHello() {
        String recipient = getRecipient().get();
        getLogger().quiet("PLUGIN_HELLO=Hello, " + recipient + "!");
    }
}
~~~

Tại sao dùng một task type thay vì `doLast { ... }` capture project?

- `@Input` khai dữ liệu task tiêu thụ, Gradle có thể theo dõi.
- `Property<String>` cung cấp cách cấu hình lazy và default qua `convention("Gradle")`.
- `@TaskAction` đọc input từ chính task, không truy Gradle Project API runtime.
- `getLogger().quiet(...)` in message ở mức QUIET, nên vẫn thấy khi chạy với `--quiet`.
- Không khai output vì task chỉ in log; nó không phải cacheable artifact-producing task.
- TestKit/`validatePlugins` có thể kiểm metadata task class ở mức phù hợp.

### 7.6. Build plugin và chạy validation

Từ thư mục `plugin-id-metadata-lab`:

~~~bash
gradle -p plugin clean build
gradle -p plugin pluginDescriptors
gradle -p plugin validatePlugins
~~~

Giải thích:

- `build` compile Java plugin classes và tạo JAR theo graph task của Java Gradle Plugin Development.
- `pluginDescriptors` sinh descriptors từ `gradlePlugin.plugins`.
- `validatePlugins` kiểm một số quy tắc triển khai plugin/task types, chẳng hạn annotations dùng với task properties; nó không tự chạy full consumer integration tests.
- Nếu `validatePlugins` báo lỗi, sửa code/annotations; không bỏ validator chỉ để publish.
- Không chạy `pluginDescriptors` trước mỗi `build` bằng tay nếu task graph đã bao gồm nó; liệt kê riêng để học/điều tra.

### 7.7. Kiểm tra output JAR

~~~bash
jar --list --file plugin/build/libs/hello-plugin-1.0.0.jar
~~~

Tìm:

~~~text
META-INF/gradle-plugins/dev.example.hello.properties
dev/example/gradle/HelloPlugin.class
dev/example/gradle/HelloTask.class
~~~

File descriptor phải có **chính key**:

~~~properties
implementation-class=dev.example.gradle.HelloPlugin
~~~

Nếu có `unzip`:

~~~bash
unzip -p plugin/build/libs/hello-plugin-1.0.0.jar \
  META-INF/gradle-plugins/dev.example.hello.properties
~~~

Một số JAR có thêm manifest, directory entries, compiled metadata; chúng không ảnh hưởng logic kiểm ba paths chính này.

## 8. Verifier Java 17 đọc descriptor mà không chạy Gradle

Đây là **một Java program độc lập dùng JDK standard library** để inspect plugin JAR. Nó không phụ thuộc Gradle API và giúp xác nhận plugin ID mapping **trước khi chạy consumer**.

Tạo `verifier/PluginDescriptorCheck.java`:

~~~java
import java.io.InputStream;
import java.util.Properties;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class PluginDescriptorCheck {
    private PluginDescriptorCheck() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: PluginDescriptorCheck <jar> <plugin-id>");
        }

        String jarPath = args[0];
        String pluginId = args[1];
        String descriptorName =
                "META-INF/gradle-plugins/" + pluginId + ".properties";

        try (JarFile jar = new JarFile(jarPath)) {
            JarEntry descriptor = jar.getJarEntry(descriptorName);
            if (descriptor == null) {
                throw new IllegalStateException(
                        "Missing descriptor: " + descriptorName);
            }

            Properties metadata = new Properties();
            try (InputStream stream = jar.getInputStream(descriptor)) {
                metadata.load(stream);
            }

            String impl = metadata.getProperty("implementation-class");
            if (impl == null || impl.isBlank()) {
                throw new IllegalStateException(
                        "Missing implementation-class value");
            }

            String classEntryName =
                    impl.replace('.', '/') + ".class";
            if (jar.getJarEntry(classEntryName) == null) {
                throw new IllegalStateException(
                        "Missing implementation class: " + classEntryName);
            }

            System.out.println("PLUGIN_ID=" + pluginId);
            System.out.println("IMPLEMENTATION_CLASS=" + impl);
            System.out.println("DESCRIPTOR_AND_CLASS=OK");
        }
    }
}
~~~

Chương trình kiểm:

1. JAR tồn tại/đọc được (nếu không, `JarFile` ném exception).
2. Có descriptor với đúng plugin ID.
3. Descriptor có key `implementation-class` không rỗng.
4. Class tương ứng tồn tại trong JAR.
5. Exit code khác 0 khi điều kiện không đạt, để dùng trong CI.

**Giới hạn:** Có class entry không chứng minh class triển khai đúng `Plugin<Project>`, bytecode compatible hay class load thành công với Gradle API. Vẫn cần `validatePlugins`, consumer build và TestKit.

### 8.1. Chạy verifier trên Linux/macOS

~~~bash
mkdir -p verifier/out

javac --release 17 -d verifier/out \
  verifier/PluginDescriptorCheck.java

java -cp verifier/out PluginDescriptorCheck \
  plugin/build/libs/hello-plugin-1.0.0.jar \
  dev.example.hello
~~~

Nếu plugin JAR được tạo đúng như mục 7, **stdout của Java program**:

~~~text
PLUGIN_ID=dev.example.hello
IMPLEMENTATION_CLASS=dev.example.gradle.HelloPlugin
DESCRIPTOR_AND_CLASS=OK
~~~

### 8.2. Chạy verifier trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force verifier\out | Out-Null

javac --release 17 -d verifier\out verifier\PluginDescriptorCheck.java

java -cp verifier\out PluginDescriptorCheck plugin\build\libs\hello-plugin-1.0.0.jar dev.example.hello
~~~

Expected stdout giống mục 8.1.

### 8.3. Kiểm bytecode plugin bằng javap

~~~bash
javap -verbose \
  -classpath plugin/build/libs/hello-plugin-1.0.0.jar \
  dev.example.gradle.HelloPlugin
~~~

Tìm:

~~~text
minor version: 0
major version: 61
~~~

Java 17 tạo class major 61 thông thường. Java 21 là major 65; một plugin compile target21 **không chạy** trong Gradle daemon JVM Java17. Không lầm plugin bytecode target với Java application runtime/toolchain của project consumer.

## 9. Publish plugin và marker vào Maven repository local

### 9.1. Publish cả implementation lẫn marker

~~~bash
gradle -p plugin publish
~~~

Vì producer có `maven-publish` và `publishing.repositories.maven { name = "lab" }`, aggregate task `publish` publish các Maven publications được cấu hình vào `plugin/build/repo`.

Kỳ vọng có hai nhóm artifact chính:

~~~text
plugin/build/repo/
├── dev/example/hello-plugin/1.0.0/
│   ├── hello-plugin-1.0.0.jar
│   ├── hello-plugin-1.0.0.pom
│   └── hello-plugin-1.0.0.module
└── dev/example/hello/
    └── dev.example.hello.gradle.plugin/1.0.0/
        └── dev.example.hello.gradle.plugin-1.0.0.pom
~~~

Có thể có checksums, sources/docs JAR và Maven metadata. Đường path dưới `dev/example/hello` xuất phát từ **marker group `dev.example.hello`**. Cây trên là danh mục minh họa các artifact quan trọng, không phải toàn bộ files bắt buộc có trên mọi Gradle release.

### 9.2. Publication names và task names

Với `create("hello")`, Gradle development plugin + Maven Publish tự tạo:

~~~text
pluginMaven
helloPluginMarkerMaven
~~~

Những task hữu ích, theo naming conventions:

~~~bash
gradle -p plugin tasks --all
gradle -p plugin generatePomFileForPluginMavenPublication
gradle -p plugin generatePomFileForHelloPluginMarkerMavenPublication
~~~

Tên task có thể thay khi đổi declaration name hoặc Gradle/publishing configuration. `tasks --all` là cách kiểm thực tế.

Một cách publish riêng từng publication trong repository tên `lab`:

~~~bash
gradle -p plugin publishPluginMavenPublicationToLabRepository
gradle -p plugin publishHelloPluginMarkerMavenPublicationToLabRepository
~~~

Nếu chỉ publish **implementation publication** mà quên marker, consumer `plugins { }` chưa chắc tìm được plugin. Với bài lab nên dùng `publish` để có cả hai rồi kiểm repository.

### 9.3. Đọc POM của marker

~~~bash
cat plugin/build/repo/dev/example/hello/dev.example.hello.gradle.plugin/1.0.0/dev.example.hello.gradle.plugin-1.0.0.pom
~~~

Nội dung cụ thể có XML namespace, metadata và wrapper comments thay theo Gradle. Điều bạn cần xác nhận là marker có dependency hướng tới:

~~~text
dev.example:hello-plugin:1.0.0
~~~

Maven marker không cần chứa compiled HelloPlugin.class; class nằm ở implementation JAR được resolution kéo theo.

### 9.4. Kiểm Gradle Module Metadata

`hello-plugin-1.0.0.module` có thể mô tả variants và attributes của implementation module. Đọc nó nếu Gradle consumer không tìm được variant tương thích hoặc JVM/Gradle attributes conflict.

Một POM marker hiện diện **không thay thế** việc kiểm implementation JAR chứa descriptor/class và tương thích với JVM consumer.

## 10. Consumer apply plugin bằng plugins DSL

### 10.1. consumer/settings.gradle.kts

~~~kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("../plugin/build/repo")
        }
        gradlePluginPortal()
    }
}

rootProject.name = "hello-consumer"
~~~

Giải thích:

- `pluginManagement.repositories` được dùng cho **plugin resolution** trong `plugins { }`.
- Repository local chứa **marker POM và implementation JAR** từ bước publish.
- `gradlePluginPortal()` được liệt kê như fallback trong ví dụ; không cần truy cập Internet nếu plugin được resolve đầy đủ từ local repo.
- Root consumer không nhất thiết cần `repositories { mavenCentral() }`, bởi plugin resolution và application/library dependency resolution là **hai đường khác nhau**.
- `pluginManagement { }` phải nằm vị trí hợp lệ đầu settings script theo Gradle syntax.
- Đường `../plugin/build/repo` ở đây là path tương đối với `consumer`.

### 10.2. consumer/build.gradle.kts

~~~kotlin
plugins {
    id("dev.example.hello") version "1.0.0"
}
~~~

**Đây là toàn bộ build script của consumer tối thiểu.** Nó không cần source Java hoặc external library để chạy task `pluginHello`. Khi Gradle evaluate consumer project, plugin marker giúp resolve implementation JAR, descriptor xác định implementation class, Gradle gọi `apply(Project)` và đăng ký task.

### 10.3. Chạy consumer

Từ thư mục `plugin-id-metadata-lab`:

~~~bash
gradle -p consumer pluginHello --quiet
~~~

Với code lab không đổi, **stdout theo logger QUIET**:

~~~text
PLUGIN_HELLO=Hello, Gradle!
~~~

Nếu bỏ `--quiet`, Gradle có thể thêm task labels/build summary; dòng chính vẫn do `HelloTask.sayHello` phát.

### 10.4. Kiểm task đã được đăng ký

~~~bash
gradle -p consumer tasks --all
~~~

Bạn phải thấy task `pluginHello` trong project consumer sau khi plugin apply. Nếu `plugins{ }` resolve thành công nhưng không có task:

- Kiểm `HelloPlugin.apply` có register task không.
- Kiểm task name/case.
- Có điều kiện nào trong plugin khiến task chỉ được đăng ký với một core plugin khác?
- Có áp plugin vào project khác chứ không phải consumer root?
- Có task collision hoặc errors trong configuration?

## 11. Kiểm thử plugin local không cần publish: composite build

Khi đang phát triển plugin source, có thể dùng **included plugin build** thay vì publish Maven mỗi lần sửa.

Trong consumer settings, **thay thế** `pluginManagement.repositories` của mục 10.1 bằng:

~~~kotlin
pluginManagement {
    includeBuild("../plugin")
}

rootProject.name = "hello-consumer"
~~~

Consumer build script khi dùng included plugin build có thể viết:

~~~kotlin
plugins {
    id("dev.example.hello")
}
~~~

Gradle tìm plugin được đăng ký bởi included build. Với cách này **không bắt buộc có marker publication trong Maven repository**, bởi plugin resolution lấy từ source plugin build.

**Cảnh báo quan trọng:** Consumer chạy được với `includeBuild` chỉ chứng minh plugin build/source có thể được áp trong composite. Nó **không chứng minh marker artifact và POM xuất bản chính xác**. Để release, vẫn chạy binary consumer từ repository như mục 9–10.

### 11.1. Hai mode giải quyết vấn đề khác nhau

| Chế độ | Cần có gì? | Kiểm chứng |
| --- | --- | --- |
| Included plugin build | `pluginManagement.includeBuild("../plugin")` | Source plugin đăng ký/apply được |
| Published plugin repository | Marker POM + implementation module/JAR/descriptor | Plugin ID/version được external consumer resolve |
| Legacy buildscript classpath | Implementation JAR và descriptor, explicit dependency | Apply class/ID theo cơ chế cũ, không nhất thiết dùng marker |
| Plugin Portal | Plugin Publish Plugin, metadata/approval/credentials | Public users resolve plugin qua Portal |

Không dùng source mode để kết luận release marker đã phát hành.

### 11.2. Tránh hai định nghĩa xung đột

Nếu cùng lúc include source build và resolve version đã publish, Gradle có thể ưu tiên included build theo plugin resolution rules. Với bài lab, giữ hai consumer settings **thay thế nhau**, hoặc dùng hai consumer test jobs/settings variants để kiểm độc lập.

## 12. Legacy apply(plugin=...) và buildscript classpath

Một consumer **không dùng plugins DSL** có thể khai implementation artifact trực tiếp:

~~~kotlin
buildscript {
    repositories {
        maven {
            url = uri("../plugin/build/repo")
        }
    }
    dependencies {
        classpath("dev.example:hello-plugin:1.0.0")
    }
}

apply(plugin = "dev.example.hello")
~~~

Đây là phương án Kotlin DSL **thay thế consumer/build.gradle.kts**, không dùng chung với `plugins { id(...) version ... }` ở mục 10.

Khác biệt:

- `buildscript.dependencies.classpath` yêu cầu Maven implementation coordinates trực tiếp.
- `apply(plugin = "...")` cần descriptor trong implementation JAR để map ID tới class.
- Consumer không nhất thiết resolve plugin marker module theo đường `plugins DSL`.
- `pluginManagement.repositories` không thay thế `buildscript.repositories`.
- Gradle khuyến nghị `plugins { }` cho đa số trường hợp hiện đại vì khai báo rõ ID/version và plugin resolution.

Với source included build, legacy buildscript path không tự biến thành source mode; cần custom dependency/classpath wiring phù hợp.

## 13. Groovy DSL tương đương cho producer và consumer

### 13.1. Producer build.gradle (Groovy)

~~~groovy
plugins {
    id 'java-gradle-plugin'
    id 'maven-publish'
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
        hello {
            id = 'dev.example.hello'
            implementationClass = 'dev.example.gradle.HelloPlugin'
            displayName = 'Example Hello Plugin'
            description = 'Adds a greeting task to a Gradle project'
            tags.addAll('example', 'build-logic', 'verification')
        }
    }
}

publishing {
    repositories {
        maven {
            name = 'lab'
            url = uri(layout.buildDirectory.dir('repo'))
        }
    }
}
~~~

Producer `settings.gradle`:

~~~groovy
rootProject.name = 'hello-plugin'
~~~

Java `HelloPlugin.java` và `HelloTask.java` giữ nguyên; Groovy chỉ là **DSL thay thế** cho build script, không thay implementation language.

### 13.2. Consumer settings.gradle (Groovy)

~~~groovy
pluginManagement {
    repositories {
        maven {
            url = uri('../plugin/build/repo')
        }
        gradlePluginPortal()
    }
}

rootProject.name = 'hello-consumer'
~~~

Consumer `build.gradle`:

~~~groovy
plugins {
    id 'dev.example.hello' version '1.0.0'
}
~~~

Chạy:

~~~bash
gradle -p plugin publish
gradle -p consumer pluginHello --quiet
~~~

Dòng plugin task in:

~~~text
PLUGIN_HELLO=Hello, Gradle!
~~~

### 13.3. Groovy DSL khác Kotlin DSL ở những điểm nào?

| Mục | Kotlin DSL | Groovy DSL |
| --- | --- | --- |
| Apply core plugin | ``java-gradle-plugin`` | `id 'java-gradle-plugin'` |
| Declaration | `create("hello") { ... }` | `hello { ... }` |
| Plugin ID | `id = "dev.example.hello"` | `id = 'dev.example.hello'` |
| Implementation class | `implementationClass = "..."` | `implementationClass = '...'` |
| Tags | `tags = listOf(...)` | `tags.addAll(...)` |
| Consumer | `id("dev.example.hello") version "1.0.0"` | `id 'dev.example.hello' version '1.0.0'` |

Chọn **một** DSL cho từng build script; không để `build.gradle` và `build.gradle.kts` cùng là hai nguồn cấu hình mâu thuẫn trong project mẫu.

## 14. Plugin Portal: metadata dành cho người dùng công khai

Nếu muốn phát hành lên **Gradle Plugin Portal**, ngoài `java-gradle-plugin` và Maven publishing cần làm theo workflow của Plugin Publish Plugin.

Theo tài liệu Gradle Plugin Portal hiện hành, có thể dùng:

~~~kotlin
plugins {
    id("com.gradle.plugin-publish") version "2.2.1"
}
~~~

Từ phiên bản 1.0.0 của Plugin Publish Plugin, plugin này tự áp `java-gradle-plugin` và `maven-publish`. Vì thế đoạn trên là **cấu hình lựa chọn thay thế cho producer plugins block** khi chuyển sang public publishing, không phải yêu cầu thêm plugin publish cho local example đã chạy.

### 14.1. Metadata dùng cho Portal

Plugin Portal thường cần:

- Plugin ID hợp lệ và unique.
- Implementation class được publish thành công.
- Display name/description/tags rõ ràng.
- Website/VCS URL thật, truy cập được.
- Group/version/publication identity nhất quán.
- Tác giả/tổ chức sở hữu namespace phù hợp.
- Plugin license, security/compliance theo policy.
- Tương thích Gradle/JDK phiên bản công bố.

Bài lab không gắn URLs thật và **không tự publish Portal**, nên không cần login hay token.

### 14.2. Validation-only và publish thật

Theo tài liệu Plugin Publish Plugin:

~~~bash
./gradlew publishPlugins --validate-only
~~~

Chạy validation không upload plugin. Lệnh publish thật:

~~~bash
./gradlew publishPlugins
~~~

Chỉ chạy sau khi có tài khoản, metadata và credentials hợp lệ; đó là hành động phát hành công khai, **không** phải bước mặc định khi học local lab.

### 14.3. Credentials không lưu trong source control

Portal có thể đọc `gradle.publish.key` và `gradle.publish.secret` trong user-home Gradle properties hoặc environment variables `GRADLE_PUBLISH_KEY`, `GRADLE_PUBLISH_SECRET`, theo chính sách hiện hành của Portal. Không commit key/secret trong repository và không copy toàn bộ Gradle/HTTP debug logs công khai nếu chúng có thể chứa thông tin nhạy cảm.

### 14.4. Portal publication và Maven publication khác phạm vi

Local Maven repository đủ để minh họa marker resolution. Portal publication bổ sung account/approval/search metadata và policy. Dùng Maven `maven-publish` không tự làm plugin xuất hiện ở Plugin Portal công cộng; ngược lại phát hành Portal không nên khiến bạn bỏ kiểm implementation JAR/marker metadata.

## 15. Gradle tasks liên quan đến metadata

Với `java-gradle-plugin`, những tasks quan trọng:

| Task | Vai trò |
| --- | --- |
| `compileJava` | Biên dịch Java implementation/task classes |
| `pluginDescriptors` | Sinh plugin ID -> implementation-class descriptors |
| `processResources` | Đưa resources/descriptors vào output resources theo task graph |
| `jar` | Đóng classes và descriptor vào implementation JAR |
| `validatePlugins` | Kiểm nhiều rule của Gradle plugin/task API usage |
| `pluginUnderTestMetadata` | Sinh metadata classpath cho Gradle TestKit functional tests |
| `generatePomFileForPluginMavenPublication` | Sinh POM implementation module |
| `generatePomFileForHelloPluginMarkerMavenPublication` | Sinh marker POM |
| `publish` | Publish các Maven publications tới repositories đã khai |
| `publishPlugins` | Publish Plugin Portal khi có Plugin Publish Plugin |

Không phải mọi task được tạo trong mọi project: `pluginUnderTestMetadata` và `validatePlugins` do plugin development hỗ trợ; `generatePom...` và `publish` cần Maven Publish; `publishPlugins` cần Plugin Publish Plugin.

### 15.1. Kiểm tasks đúng build

~~~bash
gradle -p plugin tasks --all
~~~

Khi có lỗi “Task not found”, hãy xác nhận plugin đã được apply vào **producer** và publication declaration names. Đừng gọi publication task ở consumer hoặc giả định mọi project có `publishPlugins`.

### 15.2. Debug descriptor generation

~~~bash
gradle -p plugin clean pluginDescriptors --info
gradle -p plugin jar --stacktrace
~~~

`pluginDescriptors` có thể thành công khi `compileJava` fail riêng; descriptor generation và implementation compilation là hai bước khác nhau. `jar` của producer cần chứa cả generated descriptor và compiled class để consumer load được.

### 15.3. Readback artifacts theo đường thực tế

Thay vì chỉ thấy `BUILD SUCCESSFUL`, kiểm:

~~~bash
jar tf plugin/build/libs/hello-plugin-1.0.0.jar
~~~

và Maven repository tree. Nếu publication module name thay do `rootProject.name`, file path khác nhưng plugin ID/descriptor vẫn có thể giữ nguyên. Đọc producer `group/version/name` trước khi debug.

## 16. Tự động kiểm bằng Gradle TestKit

Cần kiểm không chỉ descriptors, mà cả **behavior khi consumer apply plugin**. Gradle TestKit tạo một temporary Gradle build và gọi GradleRunner.

### 16.1. Bổ sung test dependencies vào plugin project

Trong `plugin/build.gradle.kts` của mục 7, nếu bạn muốn thêm functional test bằng JUnit Jupiter, **bổ sung**:

~~~kotlin
repositories {
    mavenCentral()
}

dependencies {
    testImplementation(gradleTestKit())
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đây là **phần mở rộng tùy chọn**. Cần network/cached JUnit dependency; không nằm trong bản runnable tối thiểu, vốn không dùng external libraries. Với version JUnit khác, pin coherent Jupiter/Platform modules theo BOM được team kiểm chứng.

### 16.2. TestKit test Java 17

Tạo `plugin/src/test/java/dev/example/gradle/HelloPluginFunctionalTest.java`:

~~~java
package dev.example.gradle;

import java.nio.file.Files;
import java.nio.file.Path;
import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertTrue;

public final class HelloPluginFunctionalTest {
    @TempDir
    Path temporaryProject;

    @Test
    void appliesByPluginIdAndRunsTask() throws Exception {
        Files.writeString(
                temporaryProject.resolve("settings.gradle.kts"),
                "rootProject.name = \"test-consumer\"\n"
        );
        Files.writeString(
                temporaryProject.resolve("build.gradle.kts"),
                "plugins { id(\"dev.example.hello\") }\n"
        );

        BuildResult result = GradleRunner.create()
                .withProjectDir(temporaryProject.toFile())
                .withArguments("pluginHello", "--quiet", "--stacktrace")
                .withPluginClasspath()
                .build();

        assertTrue(
                result.getOutput().contains(
                        "PLUGIN_HELLO=Hello, Gradle!"
                )
        );
    }
}
~~~

**Vì sao không ghi version trong temporary consumer?** `withPluginClasspath()` cho TestKit biết classpath plugin-under-test qua metadata Gradle sinh; functional test này không cần truy plugin marker từ remote Maven repository. Nó kiểm **plugin ID/descriptor/class/task behavior ở source build**, không kiểm chính artifact đã publish.

### 16.3. Chạy TestKit

~~~bash
gradle -p plugin test --stacktrace
~~~

Nếu plugin development plugin đã cấu hình plugin-under-test classpath theo Gradle TestKit, `GradleRunner.withPluginClasspath()` sử dụng nó. Nếu test không tìm được classpath metadata, kiểm task `pluginUnderTestMetadata`, dependencies và test runner setup; đừng sửa plugin ID một cách ngẫu nhiên.

### 16.4. TestKit không thay external consumer test

Bởi TestKit đưa plugin-under-test lên classpath, test này có thể pass ngay cả khi Maven marker POM bị thiếu. **Để kiểm release**, phải chạy `gradle -p plugin publish` rồi `gradle -p consumer pluginHello --quiet` với `pluginManagement.repositories` trỏ repository binary thật. Cả hai là hai lớp QA bổ sung nhau.

## 17. Validation và Configuration Cache

### 17.1. Plugin metadata validation

`validatePlugins` kiểm nhiều điều về task properties, nested inputs và artifact transforms trong plugin. Với `HelloTask`:

~~~java
@Input
public abstract Property<String> getRecipient();
~~~

Gradle biết task input là một managed property. Nếu task định nghĩa một file property không có annotation cần thiết hoặc dùng annotation sai, validation có thể báo warning/failure theo Gradle version và task type.

### 17.2. Tại sao không capture Project trong @TaskAction?

Mẫu không tốt:

~~~java
@Override
public void apply(Project project) {
    project.getTasks().register("badGreeting", task -> {
        task.doLast(ignored ->
                System.out.println(project.getName()));
    });
}
~~~

Đây là **anti-pattern minh họa**, không thuộc project runnable. Task action capture `Project` từ configuration code, có thể không phù hợp Configuration Cache requirements và làm execution phụ thuộc mutable Gradle model.

Mẫu tốt trong lab:

~~~java
task.getRecipient().convention("Gradle");
~~~

và `@TaskAction` đọc `getRecipient().get()`. Plugin cấu hình target project lúc `apply`, còn task action chạy dựa trên inputs được khai báo.

### 17.3. Smoke-test Configuration Cache

Consumer từ repository:

~~~bash
gradle -p consumer pluginHello --configuration-cache
gradle -p consumer pluginHello --configuration-cache
~~~

Kiểm log xem lần sau có reuse configuration nếu inputs ổn định và Gradle version hỗ trợ. Không khẳng định “có `Property` nên Configuration Cache chắc chắn pass” nếu plugin còn custom tasks/third-party dependencies.

### 17.4. Gradle daemon JVM và plugin bytecode

Plugin JAR được nạp vào JVM của Gradle. `java.toolchain=17` ở **plugin build** chọn compiler Java17, nhưng JVM chạy Gradle consumer phải tương thích với plugin class major61 và với chính Gradle version. Khi plugin code cần Java21 APIs/classfile major65, chạy Gradle consumer trên Java17 sẽ fail, dù app project toolchain Java21 đã được khai.

**Không sửa lỗi plugin bytecode bằng cách đặt `sourceCompatibility` cho application project**. Phải build plugin đúng target hoặc dùng Gradle runtime JVM được support.

## 18. Một producer JAR có thể chứa nhiều plugin IDs

Một implementation artifact không nhất thiết chỉ có một plugin. Ví dụ cùng project:

~~~kotlin
gradlePlugin {
    plugins {
        create("hello") {
            id = "dev.example.hello"
            implementationClass = "dev.example.gradle.HelloPlugin"
        }

        create("quality") {
            id = "dev.example.quality"
            implementationClass = "dev.example.gradle.QualityPlugin"
        }
    }
}
~~~

**Đây là snippet mở rộng, không độc lập**: muốn chạy phải tự tạo `QualityPlugin` Java class. Khi đầy đủ, Gradle có thể sinh:

~~~text
META-INF/gradle-plugins/dev.example.hello.properties
META-INF/gradle-plugins/dev.example.quality.properties
~~~

Và Maven Publish tạo **hai marker publications**, trỏ tới cùng implementation module nếu cùng producer JAR.

### 18.1. Một class cho hai IDs có được không?

Có thể khai nhiều plugin IDs trỏ tới cùng một implementation class nếu có lý do tương thích/migration và Gradle/plugin validation chấp nhận, nhưng **không nên** tạo alias mơ hồ không có tài liệu. Người dùng cần biết ID canonical và khi nào ID cũ bị deprecate.

### 18.2. Không tạo duplicate IDs trong một publication

Hai declarations:

~~~kotlin
create("first") {
    id = "dev.example.hello"
    implementationClass = "dev.example.gradle.HelloPlugin"
}
create("second") {
    id = "dev.example.hello"
    implementationClass = "dev.example.gradle.HelloPlugin"
}
~~~

là **mẫu cố ý sai**: cùng ID có thể tạo marker/descriptor conflict. Chỉ một declaration canonical cho một plugin ID trong producer; nếu cần alias migration, cân nhắc thiết kế/version policy rõ thay vì nhân đôi vô ý.

## 19. Publication metadata không phải manifest của JAR

Có ba lớp thường cùng xuất hiện:

| File/metadata | Ý nghĩa |
| --- | --- |
| `META-INF/MANIFEST.MF` | JAR manifest (Implementation-Version, Automatic-Module-Name...) |
| `META-INF/gradle-plugins/<id>.properties` | **Gradle plugin descriptor** trỏ tới implementation class |
| Maven marker POM | Map plugin ID/version sang implementation dependency |
| Maven implementation POM | Maven module coordinates và transitive dependencies |
| Gradle Module Metadata `.module` | Variants/attributes/capabilities cho Gradle consumers |
| Plugin Portal metadata | Display name, description, tags, website, VCS và portal listing |

Ví dụ file JAR manifest có:

~~~text
Implementation-Version: 1.0.0
~~~

không tự định nghĩa plugin ID. Gradle phải thấy descriptor `META-INF/gradle-plugins/dev.example.hello.properties` để apply ID từ classpath.

Ngược lại, marker POM chỉ ra implementation dependency; nó không phải “một file Java properties” nằm trong JAR.

### 19.1. Metadata GAV và implementation class phải cùng release

Nếu plugin marker `1.0.1` trỏ tới JAR implementation `1.0.0` do custom POM sai, consumer có thể tải code cũ. Nếu JAR mới không còn class cũ nhưng descriptor vẫn trỏ tên cũ, Gradle fail khi apply.

Mỗi release QA cần kiểm chain:

~~~text
plugin ID + version
       -> marker publication
       -> implementation group:artifact:version
       -> implementation JAR
       -> descriptor
       -> actual Java class
       -> apply behavior
~~~

### 19.2. Đổi group/name khác đổi plugin ID

Nếu implementation GAV chuyển từ `dev.example:hello-plugin` sang `dev.example.gradle:plugin-core`, plugin ID `dev.example.hello` **có thể vẫn giữ nguyên** nếu marker publication mới trỏ implementation GAV mới. Tuy nhiên thay metadata cần plan migration, kiểm repository caching và consumers pinned versions.

### 19.3. Checksums và signatures

Kiểm SHA-256 của JAR/marker POM sau build/publish. Chữ ký artifact chỉ có giá trị khi consumer xác minh bằng trust key/identity phù hợp. Plugin có quyền chạy code trong Gradle build, nên cần quản lý trust và supply-chain cẩn thận hơn một thư viện chỉ chứa data.

Không lưu publishing credentials/keys trong source control hoặc in nguyên trong debug logs.

## 20. Các lỗi thường gặp: nhìn triệu chứng để tìm đúng tầng

### 20.1. Plugin not found ngay khi parse plugins block

~~~text
Plugin [id: 'dev.example.hello', version: '1.0.0'] was not found
~~~

**Kiểm đầu tiên:**

1. Consumer `pluginManagement.repositories` có repository chứa marker không?
2. `plugin/build/repo` đã được tạo bằng `publish` hay chưa?
3. Marker đúng GAV `dev.example.hello:dev.example.hello.gradle.plugin:1.0.0` chưa?
4. Group/version trong producer và consumer có khớp?
5. Consumer có đang gọi version chưa publish?
6. Repository có policy/credentials/offline issue?
7. Đang dùng `pluginManagement.includeBuild` source mode hay published mode?

**Không** sửa `HelloPlugin.apply` trước khi Gradle thật sự resolve được plugin metadata.

### 20.2. Marker có nhưng dependency tới implementation JAR sai

Symptom có thể là:

~~~text
Could not find dev.example:hello-plugin:1.0.0
~~~

Kiểm marker POM dependencies, main publication `pluginMaven`, repository contents, `group/version` và custom artifactId. Không chỉ copy một JAR vào đúng thư mục mà không tạo POM/module metadata tương ứng.

### 20.3. Descriptor thiếu trong JAR

Maven resolution thành công nhưng Gradle báo không tìm thấy plugin ID trên classpath.

Kiểm:

~~~bash
jar tf plugin/build/libs/hello-plugin-1.0.0.jar
~~~

Nếu thiếu `META-INF/gradle-plugins/dev.example.hello.properties`, kiểm đã apply `java-gradle-plugin`, đã chạy `pluginDescriptors/jar`, hay custom `Jar.exclude`/copy specs loại `META-INF/gradle-plugins/**`.

### 20.4. Descriptor có nhưng implementationClass sai

Ví dụ descriptor:

~~~properties
implementation-class=dev.example.gradle.HelloPlugIn
~~~

Trong JAR chỉ có `dev/example/gradle/HelloPlugin.class`. Java class names case-sensitive; Gradle load thất bại. Sửa **`gradlePlugin.implementationClass`** (nguồn khai chính) thành fully qualified name đúng rồi build lại.

### 20.5. Class có nhưng không implements Plugin đúng target

Nếu class là một POJO bình thường hoặc triển khai `Plugin<Settings>` nhưng được áp vào project, Gradle có thể fail khi tạo/apply plugin. Class path tồn tại **không chứng minh** type/lifecycle đúng.

### 20.6. Plugin file mới nhưng consumer vẫn dùng version cũ

Consumer có `version "1.0.0"`, bạn publish `1.0.1` nhưng không đổi consumer version; runtime tiếp tục dùng release cũ. Không sửa bằng cách overwrite immutable `1.0.0`; nâng consumer pin lên `1.0.1` hoặc dùng staging candidate version theo chính sách.

### 20.7. Plugin Java 21 bytecode, daemon Java 17

~~~text
java.lang.UnsupportedClassVersionError
~~~

Kiểm `javap -verbose` trên implementation JAR, `gradle --version` của consumer và Gradle/JDK compatibility matrix. Không lấy JDK toolchain của application để suy ra plugin runtime.

### 20.8. version trong plugin DSL khác Maven marker version

Consumer `version("2.0")` nhưng producer chỉ publish `1.0.0`. Gradle tìm marker GAV theo version consumer yêu cầu; sai version dẫn tới not found. Không có cơ chế tự chọn newest version chỉ vì có một implementation JAR trong repository.

### 20.9. Gradle Plugin Portal không tìm thấy plugin mới

Có thể chưa publish `publishPlugins`, account/credentials/metadata chưa đầy đủ, đang chờ approval hoặc namespace policy không đạt. `gradle -p plugin publish` vào file repo **không** tương đương Portal publication.

### 20.10. buildscript classpath có JAR nhưng plugins DSL không resolve

`buildscript.dependencies.classpath(...)` là cơ chế legacy; `plugins { id... version... }` dùng `pluginManagement` và marker mapping. Đừng dùng một repository declaration không đúng scope rồi kỳ vọng cả hai tự nhận.

### 20.11. Plugin ID giống core plugin

Tránh IDs như `java` hoặc namespace dành riêng để ngăn collision. Custom plugin nên có namespace thuộc team/công ty và được đăng ký trong Gradle Plugin Portal theo rules.

### 20.12. Descriptor bị duplicate khi copy resources

Đã dùng `java-gradle-plugin` sinh descriptor, nhưng cũng thêm thủ công `src/main/resources/META-INF/gradle-plugins/dev.example.hello.properties`. Task `processResources` hoặc `jar` có thể gặp duplicate/conflict hoặc chọn bản không mong muốn. Chỉ dùng **một nguồn sự thật**, tốt nhất `gradlePlugin`.

### 20.13. Task không hiện sau khi plugin apply

Resolution/descriptor/class thành công nhưng `pluginHello` không có. Kiểm `apply(Project)` và task registration; có thể code plugin chỉ register khi core plugin khác được apply hoặc task name khác.

### 20.14. Task behavior sai nhưng plugin id đúng

`displayName`/`description` không điều khiển runtime logic. Cần test `@TaskAction` và inputs/extensions. Một plugin có metadata tuyệt vời vẫn có thể có bug.

### 20.15. Chỉ test includeBuild, không test marker

Source plugin test pass nhưng artifact consumer từ Maven không apply được vì marker thiếu. Cần hai test lanes: included plugin build/TestKit và published binary consumer.

### 20.16. Tự tạo marker POM sai dependency scope

Nếu marker trỏ sai implementation module hoặc thiếu dependency, `plugins DSL` resolve fail. Dùng automated publishing của `java-gradle-plugin` trừ khi có lý do cần customize, và đọc generated POM trước release.

### 20.17. Public ID/description không thống nhất

Plugin ID `dev.example.hello` nhưng displayName mô tả một codegen plugin hoàn toàn khác; user khó tìm và hiểu chức năng. Giữ docs/metadata mô tả behavior thật, release notes cho breaking changes.

### 20.18. Plugin tests fail vì thiếu repositories của TestKit fixture

TestKit với `withPluginClasspath` không cần Maven marker cho plugin-under-test, nhưng fixture có external dependencies vẫn cần repositories. Phân biệt lỗi fixture dependency resolution với plugin descriptor resolution.

### 20.19. publish task tên không đúng

Bạn đoán `publishHelloPublicationToMavenRepository` nhưng Gradle tạo `helloPluginMarkerMaven` và `pluginMaven`. Dùng `tasks --all` đọc task names thật thay vì tự đặt.

### 20.20. Tắt automatedPublishing rồi quên marker

Khi tùy biến `gradlePlugin { automatedPublishing = false }`, Gradle không sinh publications tự động như trước. Nếu muốn `plugins DSL` hoạt động từ Maven, phải tự publish marker đúng chain. Đừng tắt tùy tiện.

## 21. Quy trình QA trước khi phát hành một plugin

Một checklist theo đúng thứ tự quan sát:

### Bước 1 — Source/class compile

~~~bash
gradle -p plugin clean compileJava
~~~

Kiểm class `dev/example/gradle/HelloPlugin.class` và `HelloTask.class`. Java 17 bytecode major61.

### Bước 2 — Descriptor generation

~~~bash
gradle -p plugin pluginDescriptors jar
~~~

Kiểm `META-INF/gradle-plugins/dev.example.hello.properties` trong JAR có `implementation-class=dev.example.gradle.HelloPlugin` và class thực sự tồn tại.

### Bước 3 — Plugin API validation

~~~bash
gradle -p plugin validatePlugins
~~~

Xử lý warnings/errors có ý nghĩa về task inputs/annotations/implementation.

### Bước 4 — TestKit behavior

Nếu có functional tests tùy chọn ở mục 16:

~~~bash
gradle -p plugin test
~~~

Kiểm consumer fixture có thể apply by ID và chạy task. Chú ý TestKit source test chưa xác minh Maven marker.

### Bước 5 — Maven publish local

~~~bash
gradle -p plugin publish
~~~

Kiểm implementation publication `pluginMaven` và marker publication `helloPluginMarkerMaven`; đọc generated POM/module metadata.

### Bước 6 — Binary consumer

~~~bash
gradle -p consumer pluginHello --quiet
~~~

Kỳ vọng:

~~~text
PLUGIN_HELLO=Hello, Gradle!
~~~

Đây là lớp xác nhận plugin resolution **qua marker + implementation JAR từ repository**.

### Bước 7 — Java descriptor verifier

~~~bash
java -cp verifier/out PluginDescriptorCheck \
  plugin/build/libs/hello-plugin-1.0.0.jar \
  dev.example.hello
~~~

Chỉ chạy sau khi compile verifier ở mục 8. Kiểm exact mapping trong JAR; không nhầm với marker resolution.

### Bước 8 — Security, compatibility và release

- Gradle Wrapper/JDK matrix phù hợp.
- Plugin JAR target bytecode hỗ trợ Gradle JVM thấp nhất đã cam kết.
- Unit/functional tests pass, Configuration Cache test khi cần.
- API compatibility/semantic behavior được kiểm khi nâng version.
- Marker POM dependencies/implementation version đúng.
- No secrets, license/NOTICE theo policy.
- SHA-256/signature/provenance của **artifact được publish thật**.
- Kiểm consumer từ staging repository mới rồi mới promote public release.

## 22. Những câu hỏi thường gặp (FAQ)

### Q1. Có thể dùng một implementation class cho nhiều plugin IDs không?

Có thể thiết kế alias IDs nhưng nên giới hạn rõ; mỗi ID phải có descriptor/marker tương ứng. Cần tránh duplicates cùng ID và có migration policy cho ID cũ.

### Q2. Có bắt buộc tên create("hello") giống đuôi .hello của plugin ID không?

Không. Declaration name là tên local của object trong plugin development extension. Nên đặt gần nghĩa để dễ đọc task/publication names.

### Q3. Nếu consumer đã có implementation JAR trên classpath, cần marker không?

Với legacy `buildscript.classpath` + `apply(plugin=...)`, JAR có descriptor đủ cho ID mapping; marker phục vụ resolution của `plugins DSL` từ repository. Với included plugin build, Gradle có cơ chế plugin resolution từ source build khác.

### Q4. Nếu không khai displayName/description/tags thì plugin runtime có chạy?

Runtime mapping dựa trên id/implementationClass/descriptor. Tuy nhiên public Plugin Portal có metadata quality/acceptance requirements; khi publish công khai hãy cung cấp đầy đủ metadata theo tài liệu và policy.

### Q5. `implementationClass` có phải chứa tên method apply không?

Không. Nó chỉ tên Java class triển khai Plugin interface; Gradle gọi `apply` theo interface contract. Không viết `HelloPlugin.apply`.

### Q6. Có cần tự thêm gradleApi() khi dùng java-gradle-plugin không?

Plugin development plugin cấu hình Gradle API dependency cần cho việc biên dịch plugin. Không tự khai dependency Gradle API tùy version chỉ để chữa import lỗi khi chưa hiểu plugin đã được apply hay chưa.

### Q7. Vì sao descriptor trong JAR chỉ có implementation-class?

Nó là mapping plugin ID → class. Những metadata khác thuộc Maven/Portal publication layer hoặc JAR manifest, không phải key bắt buộc của descriptor.

### Q8. Plugin ID có trùng Maven group không?

Không bắt buộc. Marker group được derive từ plugin ID; implementation module group được derive từ project group. Hai coordinates có thể khác, như bài lab.

### Q9. Maven publisher tự sinh marker cho mọi Java library không?

Không. Tự động marker cho Gradle plugin là tính năng phối hợp `java-gradle-plugin` + publishing plugin khi automated publishing bật. Thư viện Java thông thường với chỉ `java-library` + `maven-publish` không có plugin ID mapping.

### Q10. Một plugin ID đổi class implementation thì consumer phải đổi ID không?

Không nhất thiết. Giữ public plugin ID và publish version mới có thể trỏ tới class mới, miễn descriptor/behavior contract và compatibility được quản lý. Đổi implementationClass có thể là refactor nội bộ.

### Q11. Có thể publish private plugin mà không lên Portal?

Có. Dùng file-based Maven repo, Nexus/Artifactory hoặc repository nội bộ có marker/implementation module đầy đủ. Consumer phải cấu hình pluginManagement repositories và credentials đúng.

### Q12. Vì sao source build áp được nhưng published version không áp?

Source included build bypass Maven marker lookup; public binary consumer cần marker POM/JAR/descriptor/implementation dependencies đúng. So hai workflows riêng.

## 23. Bài tập thực hành có đáp án

### Bài 1 — Phân biệt ID và class

~~~kotlin
create("hello") {
    id = "dev.example.hello"
    implementationClass = "dev.example.gradle.HelloPlugin"
}
~~~

**Hỏi:** Consumer áp ID nào?

**Đáp án:** `id("dev.example.hello")`. `hello` chỉ là declaration name.

### Bài 2 — Descriptor filename

Plugin ID `dev.example.hello`. Tên descriptor đúng?

**Đáp án:** `META-INF/gradle-plugins/dev.example.hello.properties`.

### Bài 3 — Descriptor property key

Nội dung descriptor đúng?

**Đáp án:**

~~~properties
implementation-class=dev.example.gradle.HelloPlugin
~~~

Không dùng `implementationClass=...` trong file properties.

### Bài 4 — Plugin marker GAV

Plugin ID `dev.example.hello` version1.0.0.

**Đáp án:** `dev.example.hello:dev.example.hello.gradle.plugin:1.0.0`.

### Bài 5 — Implementation GAV

Producer group `dev.example`, project name `hello-plugin`, version1.0.0.

**Đáp án:** `dev.example:hello-plugin:1.0.0` theo defaults của Java/Maven publication trong lab.

### Bài 6 — Consumer plugin DSL

Code đúng:

~~~kotlin
plugins {
    id("dev.example.hello") version "1.0.0"
}
~~~

**Giải thích:** Gradle tìm marker module rồi implementation JAR và descriptor.

### Bài 7 — Chỉ có JAR, không có marker

Consumer `plugins DSL` có tự tìm `dev.example:hello-plugin:1.0.0` không?

**Đáp án:** Không. Marker hoặc explicit plugin resolution strategy là cần thiết khi dùng remote plugin repository.

### Bài 8 — Publish tasks

Dùng `java-gradle-plugin` + `maven-publish` với `create("hello")`.

**Đáp án:** Gradle thường có `pluginMaven` và `helloPluginMarkerMaven` publications; `publish` đưa cả hai lên configured Maven repos.

### Bài 9 — Sai Java class package

Source package `dev.example.gradle` nhưng implementationClass `dev.example.HelloPlugin`.

**Đáp án:** Metadata sai FQCN; sửa implementationClass thành `dev.example.gradle.HelloPlugin` và build lại.

### Bài 10 — Class bytecode

JAR HelloPlugin.class major61 được compile cho Java release nào?

**Đáp án:** Java17.

### Bài 11 — Plugin JVM vs application JVM

Consumer app toolchain21 nhưng Gradle daemon Java17, plugin class major65. Có chạy plugin không?

**Đáp án:** Không, Gradle JVM phải load plugin class và Java17 không hiểu major65. Sửa plugin target hoặc Gradle JVM/Wrapper hợp lệ.

### Bài 12 — Task stdout

Consumer đúng như lab, chạy:

~~~bash
gradle -p consumer pluginHello --quiet
~~~

**Đáp án:**

~~~text
PLUGIN_HELLO=Hello, Gradle!
~~~

### Bài 13 — Java verifier stdout

Sau khi build plugin/compile verifier:

~~~bash
java -cp verifier/out PluginDescriptorCheck \
  plugin/build/libs/hello-plugin-1.0.0.jar \
  dev.example.hello
~~~

**Đáp án:**

~~~text
PLUGIN_ID=dev.example.hello
IMPLEMENTATION_CLASS=dev.example.gradle.HelloPlugin
DESCRIPTOR_AND_CLASS=OK
~~~

### Bài 14 — Marker missing nhưng TestKit pass

Vì sao?

**Đáp án:** `withPluginClasspath()` đưa implementation của plugin-under-test vào fixture, không dùng remote Maven marker. Cần published binary consumer test.

### Bài 15 — Metadata displayName sai

`displayName="Some Other Plugin"` có làm Gradle load sai class?

**Đáp án:** Không trực tiếp. Load dựa trên descriptor mapping; displayName là public/human metadata, nhưng phải sửa để không gây hiểu lầm.

### Bài 16 — includeBuild vs pluginManagement.repositories

Muốn test local source plugin chưa publish, chọn gì?

**Đáp án:** `pluginManagement { includeBuild("../plugin") }` trong consumer settings; consumer áp ID không cần version theo source mode sample.

### Bài 17 — Legacy apply

Plugin JAR có descriptor, consumer dùng buildscript classpath thay vì plugins DSL.

**Đáp án:** Khai implementation JAR qua `buildscript.dependencies.classpath`, rồi `apply(plugin="dev.example.hello")`; không cần marker lookup theo đường plugins DSL.

### Bài 18 — Gradle Portal

`gradle -p plugin publish` vào file repo có làm plugin xuất hiện ở Plugin Portal không?

**Đáp án:** Không. Cần Plugin Publish Plugin, portal metadata/credentials và `publishPlugins`, theo quy trình approval.

### Bài 19 — Duplicate IDs

Hai plugin declarations có cùng `id="dev.example.hello"`.

**Đáp án:** Sai thiết kế/metadata conflict. Dùng một canonical declaration; alias khác ID nếu thật sự cần và được quản lý.

### Bài 20 — Q/A thứ tự release

Team chỉ chạy `gradle compileJava` rồi publish. Thiếu điều gì?

**Đáp án:** Descriptor/JAR validation, marker POM, functional TestKit, published consumer apply, JVM compatibility và artifact checksum/security checks.

## 24. Checklist dành cho người review pull request

| Kiểm tra | Câu hỏi |
| --- | --- |
| ID | `id` có namespace rõ, stable, hợp lệ và không xung đột? |
| Declaration name | `create("hello")` có unique và giải thích được? |
| Implementation | `implementationClass` là FQCN đúng của public `Plugin<Project>`? |
| Source file | Package/file/class khớp literal implementationClass? |
| Descriptor | JAR có đúng `META-INF/gradle-plugins/<id>.properties`? |
| Property | Có key `implementation-class` đúng FQCN? |
| Compiled class | JAR có classfile và Gradle JVM đọc được major version? |
| java-gradle-plugin | Có apply để sinh descriptors/validation/marker? |
| maven-publish | Main `pluginMaven` + marker `helloPluginMarkerMaven` được publish? |
| Marker | `id:id.gradle.plugin:version` trỏ implementation GAV đúng? |
| Consumer | `pluginManagement.repositories` và `plugins DSL` resolve thực tế? |
| Included mode | Source plugin có apply và hoạt động bằng includeBuild/TestKit? |
| TestKit | Functional test assert task behavior, không thay binary consumer test? |
| Metadata công khai | displayName, description, tags, website/VCS đúng chức năng và ownership? |
| Version | Producer group/name/version và consumer requested version khớp release? |
| Configuration Cache | Task actions dựa trên inputs, không capture Project runtime? |
| Security | Không publish token/secrets, kiểm dependency trust và signing policy? |
| Release artifacts | JAR, POM, module metadata, marker, checksums nằm đúng staging repo? |
| QA | Fail khi missing/mismatch, không chỉ in warning? |

**Kết luận:** Để một Gradle binary plugin được áp dụng đáng tin cậy, phải hiểu đúng đường đi **plugin ID → plugin marker module → implementation JAR → descriptor `implementation-class` → Java class implements `Plugin<Project>` → `apply(Project)`**. `java-gradle-plugin` giúp sinh descriptor/validation/marker, còn `maven-publish`/Plugin Publish Plugin đưa artifacts và metadata tới đúng repository. Cần kiểm cả **metadata bên trong JAR** lẫn **metadata phục vụ resolution tại repository**, và chạy consumer thật ở Java/Gradle versions được hỗ trợ trước khi phát hành.

## 25. Tài liệu chính thức

- [Gradle — Introduction to Plugins](https://docs.gradle.org/current/userguide/custom_plugins.html) — core, custom, script/precompiled/binary plugins và scope.
- [Gradle — Binary Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_binary.html) — `Plugin<Project>`, class implementation và plugin development project.
- [Gradle — Java Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html) — `gradlePlugin { plugins { ... } }`, `pluginDescriptors`, `validatePlugins`, `pluginUnderTestMetadata`.
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html) — pluginManagement, plugin marker coordinates và resolution.
- [Gradle — Preparing to Publish Plugins](https://docs.gradle.org/current/userguide/preparing_to_publish.html) — Maven plugin markers, implementation artifacts và local consumer.
- [Gradle — Publishing Plugins to the Gradle Plugin Portal](https://docs.gradle.org/current/userguide/publishing_gradle_plugins.html) — displayName, description, tags, website/VCS, publishPlugins.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html) — publication tasks, POM, repository settings và version.
- [Gradle — Testing Gradle Plugins](https://docs.gradle.org/current/userguide/testing_gradle_plugins.html) — TestKit, GradleRunner và functional tests.
- [Gradle — Configuring Plugin Management](https://docs.gradle.org/current/userguide/plugins_intermediate.html#sec:plugin_management) — plugin repositories và resolution strategy.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html) — JDK compiler/launcher và `--release`.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html) — yêu cầu của tasks/plugins.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — JDK chạy Gradle và support toolchain theo release.
