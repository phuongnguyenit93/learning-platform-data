# Đưa quy ước chung vào convention plugin thay cho cấu hình chéo trong Gradle

## 1. Bài toán: nhiều project Java có cùng cấu hình nhưng khó bảo trì

Giả sử một repository có nhiều Gradle subprojects:

~~~text
workspace/
├── api/
├── core/
├── app/
└── settings.gradle.kts
~~~

Mỗi module đều cần Java 17, encoding UTF-8, một số quy định cho `JavaCompile`, cấu hình test logging và có thể cả Checkstyle, JaCoCo hoặc Maven publishing. Nhóm phát triển thường bắt đầu bằng hai cách:

1. Sao chép cùng cấu hình vào `api/build.gradle.kts`, `core/build.gradle.kts`, `app/build.gradle.kts`.
2. Đặt một `subprojects { ... }` hoặc `allprojects { ... }` thật lớn trong **root** `build.gradle.kts` để tự cấu hình mọi module.

Cách 1 làm cấu hình trùng lặp. Cách 2 nhìn có vẻ tập trung hơn nhưng khiến **root project trực tiếp can thiệp vào mutable state của project khác**. Khi số module tăng, cấu hình chéo khó truy nguồn, tạo coupling lúc configuration và có thể xung đột với các tính năng như Configuration on Demand hoặc **Isolated Projects**.

**Giải pháp nên ưu tiên:** đóng các quy ước dùng chung vào **convention plugin**, rồi để **từng subproject tự áp dụng plugin** bằng `plugins { id("...") }`. Phần riêng của mỗi module vẫn ở build script của chính nó.

Bài học thuộc nhóm **Build nhiều dự án** của module Build Tool Gradle, tập trung vào cách **thay cấu hình chéo bằng convention plugin**, không chỉ hướng dẫn viết một plugin cho vui. Cuối bài có project Java 17 đa module chạy được, quy trình chuyển đổi từ `subprojects`, diagnostics và bài tập thực hành.

### 1.1. Kết quả học tập

Sau bài học, bạn sẽ có thể:

- Giải thích **cross-project configuration**, mutable Project state và vì sao `subprojects/allprojects` có thể gây hidden configuration.
- Phân biệt **một convention plugin** với Gradle core plugin, external plugin, version catalog, `buildSrc` và included build `build-logic`.
- Tạo một **precompiled Kotlin DSL script plugin** trong `build-logic/src/main/kotlin`.
- Đăng ký plugin để các modules tìm thấy bằng `pluginManagement { includeBuild("build-logic") }`.
- Áp dụng plugin trong **từng module** bằng `plugins { id("acme.java-conventions") }`.
- Đặt quy ước Java toolchain, compiler release, encoding và test task trong plugin, không cấu hình chéo từ root.
- Giữ `api`/`implementation`, application `mainClass` và dependencies riêng ở đúng project.
- Chạy project Java 17 gồm `:api`, `:core` và `:app` không có third-party runtime dependency; đọc stdout chính xác.
- Biết khi nào cần dùng `kotlin-dsl`, buildSrc, included build hoặc binary plugin.
- Phân biệt **Configuration Cache**, **Isolated Projects**, parallel execution và build performance.
- Kiểm tra plugin discovery, task configuration và hành vi sau khi migration.

## 2. Nắm khái niệm Gradle build và Project trước khi refactor

### 2.1. Một build có nhiều project

`settings.gradle.kts` là điểm khai báo cấu trúc của multi-project build:

~~~kotlin
rootProject.name = "multi-project-demo"

include(":api", ":core", ":app")
~~~

Sau đó Gradle có các project paths:

~~~text
:
:api
:core
:app
~~~

`:api:compileJava` là task `compileJava` trong project `:api`, khác `:core:compileJava` và `:app:compileJava`.

- **Project** có plugins, extensions, tasks, configurations, dependencies, repositories và properties riêng.
- **Root project** là một project trong cùng build, không phải “owner có quyền cấu hình tùy ý mọi project mà không gây coupling”.
- **Included build** là một build khác tham gia composite build; khác với subproject được đưa vào bằng `include(...)`.
- **Build logic** là code cấu hình Gradle, có thể nằm trong build scripts hoặc được đóng vào plugins.

Cấu hình của một project nên được thực hiện **trong project đó** thông qua plugin hoặc build script mà nó áp dụng.

### 2.2. Configuration phase là nơi cross-project coupling nảy sinh

Một build Gradle có initialization, configuration và execution. `subprojects { ... }` trong root build script được chạy lúc configuration để tác động các project con.

Nếu root script viết:

~~~kotlin
subprojects {
    tasks.withType<JavaCompile>().configureEach {
        options.encoding = "UTF-8"
    }
}
~~~

thì root build script đang cấu hình **tasks của các project khác**. Đoạn trên là **ví dụ anti-pattern**, có thể cần import `JavaCompile` và có thể vẫn hoạt động trong một số build thông thường. Vấn đề không chỉ là syntax, mà là **ai sửa state của ai**.

Một subproject mở file `core/build.gradle.kts` sẽ không nhìn thấy toàn bộ logic bị root “tiêm” vào. Cấu hình có thể phụ thuộc vào thứ tự áp plugin, callbacks và thông tin từ project khác.

## 3. Vì sao không tiếp tục dùng subprojects/allprojects cho quy ước?

### 3.1. Ví dụ trước khi migration

Một root `build.gradle.kts` cũ có thể trông như sau:

~~~kotlin
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

subprojects {
    apply(plugin = "java")

    extensions.configure<JavaPluginExtension> {
        toolchain.languageVersion.set(JavaLanguageVersion.of(17))
    }

    tasks.withType<JavaCompile>().configureEach {
        options.release.set(17)
        options.encoding = "UTF-8"
    }

    tasks.withType<Test>().configureEach {
        maxHeapSize = "512m"
    }
}
~~~

Đây là **mẫu cũ để phân tích và thay thế**, không phải cấu hình nên copy vào bài lab cuối. Nó đặt Java plugin và quy ước cho mọi subproject, kể cả module không phải Java trong tương lai.

### 3.2. Vấn đề thực tế

| Vấn đề | Hậu quả |
| --- | --- |
| **Hidden configuration** | Xem `core/build.gradle.kts` không biết cấu hình nào đến từ root |
| **Không có opt-in rõ** | Module mới có thể bị áp Java rules dù nó là docs/tooling/native project |
| **Coupling lúc configuration** | Root tham chiếu/đổi state project con, khó phân tách configuration |
| **Thứ tự apply/plugin** | Có thể cần `plugins.withId`/`afterEvaluate` để đợi plugin khác |
| **Khó tái sử dụng** | Copy block root sang repo khác vẫn phụ thuộc project structure |
| **Khó test độc lập** | Build logic không có plugin ID/điểm kiểm thử rõ ràng |
| **Khó quy định ownership** | Team module không biết mình đang bị root chỉnh những task nào |
| **Isolated Projects** | Cross-project mutable state access vi phạm constraints của chế độ này |
| **Configuration avoidance** | Eager lookups/callbacks không tốt có thể buộc cấu hình tasks sớm |

Không phải một `subprojects { }` nhỏ sẽ luôn làm build thông thường **fail**. Gradle vẫn hỗ trợ cú pháp đó. Khuyến nghị là **không dùng nó làm cơ chế chia sẻ quy ước**, bởi coupling tiềm ẩn và giới hạn khả năng tối ưu hóa.

### 3.3. allprojects khác subprojects thế nào?

- `allprojects { ... }` tác động root project **và** các subprojects.
- `subprojects { ... }` tác động các descendants mà callback áp dụng.
- Cả hai là cách cấu hình scope rộng từ một project owner.
- Không có nghĩa “dùng `allprojects` cho đồng nhất sẽ tự tốt hơn `subprojects`”.

Nếu root chính nó không có Java source, việc ép `java` cho root có thể tạo tasks không cần thiết, gây nhiễu `tasks`/`build`/`check`. Convention plugin cho phép **module nào cần thì tự apply**.

## 4. Convention plugin là gì?

Một **convention plugin** là Gradle plugin chứa các quyết định, defaults và quy ước dùng chung của tổ chức/build. Nó có thể:

- Áp dụng core plugin `java`, `java-library`, `application` hoặc plugin bên ngoài.
- Đặt Java toolchain/release/encoding.
- Cấu hình JUnit/Test, JaCoCo/Checkstyle, archives, compiler options.
- Cấu hình các default dependencies hay version constraints hợp lệ.
- Thêm tasks/checks/extensions phục vụ chính sách build.
- Kết nối các task outputs và verification logic vào lifecycle tasks.

Khi một subproject ghi:

~~~kotlin
plugins {
    id("acme.java-conventions")
}
~~~

nó **tự yêu cầu** quy ước. Build script cho thấy rõ module đang áp policy nào. Plugin chỉ tác động state của **project đã apply nó**, không cần root tự gọi `project(":core").tasks...` để sửa module khác.

### 4.1. Convention không phải “bắt buộc không được override”

Từ “convention” thường diễn đạt **giá trị mặc định có thể điều chỉnh**. Tuy nhiên một plugin cũng có thể enforce policy nếu team cần, ví dụ bắt buộc tests chạy trên JDK17.

Phân biệt:

- **Default**: cung cấp fallback và cho phép module override qua `Property.convention(...)`.
- **Enforced rule**: cấu hình hoặc validation được thiết kế để từ chối override sai.
- **Per-module decision**: điều không dùng chung, ví dụ application main class hoặc dependency cụ thể, nên nằm tại module.

Không đưa mọi thứ vào convention plugin rồi khóa toàn bộ build. Mục tiêu là **giảm trùng lặp nhưng giữ kiến trúc dễ đọc**.

### 4.2. Convention plugin khác version catalog

`gradle/libs.versions.toml` lưu **aliases và versions** của libraries/plugins, ví dụ:

~~~toml
[versions]
junit = "5.11.4"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
~~~

Version catalog **không tự áp plugin hay dependencies vào mọi subproject**. Nó giúp build scripts nói “dependency nào và version nào”; convention plugin nói “khi module thuộc loại Java library, áp những cấu hình nào”.

Hai cơ chế bổ sung nhau:

~~~text
Version catalog: tên/version được công khai thống nhất
Convention plugin: cách project được cấu hình
Subproject: quyết định áp plugin gì + dependencies riêng
~~~

### 4.3. Convention plugin khác binary plugin

- **Precompiled script plugin**: file `*.gradle.kts` hoặc `*.gradle` được Gradle compile thành plugin, tốt cho quy ước DSL vừa phải.
- **Binary plugin**: class `Plugin<Project>` bằng Java/Kotlin/Groovy, hữu ích khi logic phức tạp, nhiều custom task types, APIs, test và publishing.
- **External plugin**: plugin từ plugin repository; có thể được áp **bên trong convention plugin** nếu có đúng dependency/classpath.
- **Core plugin**: `java`, `java-library`, `application` có sẵn trong Gradle distribution.

Bài lab dùng **precompiled Kotlin DSL script plugin** vì đây là cách ngắn, rõ và phổ biến để gom shared build logic.

## 5. Chọn buildSrc hay included build build-logic?

Có hai vị trí thường dùng để giữ convention plugins.

| Đặc điểm | `buildSrc` | Included build `build-logic` |
| --- | --- | --- |
| Cơ chế | Gradle tự nhận diện thư mục đặc biệt ở root | Root build đăng ký composite/included plugin build |
| Build file riêng | `buildSrc/build.gradle.kts` | `build-logic/build.gradle.kts` |
| Plugins source | `buildSrc/src/main/kotlin/*.gradle.kts` | `build-logic/src/main/kotlin/*.gradle.kts` |
| Thêm vào build chính | Tự động, không cần `includeBuild` | Dùng `pluginManagement { includeBuild("build-logic") }` để resolve plugin IDs |
| Classpath | Build logic classes rộng rãi có trên main buildscript classpath | Plugin được đưa vào khi resolution từ included plugin build |
| Tính modular | Dễ bắt đầu, ít setup | Boundary rõ hơn cho build logic riêng |
| Khi sửa build logic | Có thể invalidate configuration của nhiều scripts | Cũng có cost rebuild/cache invalidation; có thể modular hóa |
| Dùng khi | Project nhỏ/đang học | Multi-project lớn, nhiều convention plugins |

**Không có một lựa chọn tuyệt đối.** Một dự án nhỏ có thể dùng `buildSrc` hiệu quả. Với bài học “thay cấu hình chéo trong multi-project”, `build-logic` là ví dụ chính vì giúp thấy một build riêng, plugin ID rõ và không cần root chạm state subprojects.

### 5.1. Included build không phải subproject

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}
~~~

Lệnh này đăng ký build chứa plugins để Gradle **resolve plugin IDs** trong `plugins { }`. Nó **khác**:

~~~kotlin
include(":build-logic")
~~~

Dòng thứ hai biến build-logic thành subproject của main build, **không phải** cấu hình khuyến nghị để plugin compilation/publishing trong ví dụ này.

Với một build `build-logic` riêng, nó có `settings.gradle.kts`/`build.gradle.kts`, classpath và dependency resolution riêng. Không tự giả định catalog/repositories của root được chia sẻ hoàn toàn sang included build.

## 6. Kiến trúc mục tiêu của bài thực hành

Chúng ta sẽ tạo:

~~~text
convention-plugin-lab/
├── settings.gradle.kts
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/
│       └── main/
│           └── kotlin/
│               └── acme.java-conventions.gradle.kts
├── api/
│   ├── build.gradle.kts
│   └── src/main/java/demo/api/Message.java
├── core/
│   ├── build.gradle.kts
│   └── src/main/java/demo/core/Greeter.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
~~~

**Chủ ý của ví dụ:**

- `build-logic` là included build tạo một plugin **`acme.java-conventions`**.
- Cả `:api`, `:core` và `:app` tự apply plugin đó.
- `:api`, `:core` là Java libraries, áp riêng `java-library`.
- `:app` là application, áp riêng `application` và đặt `mainClass`.
- Cả ba modules dùng Java 17 toolchain, `options.release=17`, UTF-8, cùng Test-task defaults từ plugin.
- Chỉ dùng **project dependencies** trong main build; không cần Maven Central cho application runtime.
- `:core` khai báo `api(project(":api"))` vì return type công khai dùng `Message`.
- `:app` chỉ cần `implementation(project(":core"))`.
- Không có root `subprojects`/`allprojects` block.
- Có Java `main` chạy được và stdout chính xác.

## 7. settings.gradle.kts của root build

Tạo `settings.gradle.kts` ở root:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "convention-plugin-lab"

include(":api", ":core", ":app")
~~~

Giải thích:

1. `pluginManagement` được khai báo đầu settings để Gradle biết nguồn giải quyết plugins.
2. `includeBuild("build-logic")` đưa plugins từ included build vào plugin resolution.
3. `rootProject.name` đặt tên root.
4. `include(...)` tạo đúng ba **subprojects** của main build.
5. Không có lệnh `apply(plugin=...)` nào tự gán Java convention cho tất cả project; từng module sẽ opt-in.

Với plugins bên ngoài, `pluginManagement.repositories` có thể cần cấu hình `gradlePluginPortal()`/mirror doanh nghiệp. Trong bài lab, plugin `acme.java-conventions` đến từ included build và plugin Java là core plugin có sẵn.

### 7.1. Root build.gradle.kts có cần không?

Với bài lab này **không cần**. Root chỉ chịu trách nhiệm settings và cấu trúc; mỗi subproject tự áp plugin và dependencies. Có thể tạo `build.gradle.kts` rỗng nếu quy trình repository mong muốn, nhưng không cần ép root có logic cấu hình chéo.

Root không phải nơi duy nhất chứa “cấu hình chung”; **cấu hình chung nay nằm trong plugin code**, còn root settings là nơi quyết định topology.

## 8. Included build: build-logic/settings.gradle.kts

Tạo:

~~~kotlin
rootProject.name = "build-logic"
~~~

Tên build giúp nhận diện nó trong logs/tooling. Nó có lifecycle/configuration riêng và không biến `build-logic` thành `:build-logic` của main build.

### 8.1. Plugin repository của included build

Một included build có thể cần repository cho plugin/tooling dependencies của chính nó. Trong `build-logic/build.gradle.kts` sẽ có `gradlePluginPortal()`, ngay cả khi main application không có external runtime dependencies.

Nếu tổ chức chặn Internet, configure plugin repository mirror/caches ở môi trường nội bộ. Không mặc định “không có library dependency” nghĩa **Gradle distribution/Kotlin DSL tooling** không cần resolve hoặc đã được cache trên mọi máy.

## 9. build-logic/build.gradle.kts

Tạo file:

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
~~~

**Cú pháp đặc biệt:** ``kotlin-dsl`` ở đây là Kotlin DSL backtick plugin accessor. Trong nội dung Markdown, dòng hiển thị trong code block phải là backticks quanh tên `kotlin-dsl` (không phải quotes hay string `"kotlin-dsl"`).

Plugin `kotlin-dsl` thêm hỗ trợ biên dịch **precompiled Kotlin script plugins** từ `src/main/kotlin`. Gradle compile các script đó thành plugin classes và tạo plugin IDs từ filename.

**Không dùng** `id("org.jetbrains.kotlin.jvm")` chỉ để tạo Java convention plugin; `kotlin-dsl` là plugin phù hợp cho build logic Kotlin DSL của Gradle.

### 9.1. Có cần gradlePlugin block không?

**Không** cho ví dụ precompiled script plugin này. Khi dùng `kotlin-dsl`, Gradle tạo plugin implementation và ID từ file `acme.java-conventions.gradle.kts`. Với binary plugin tự viết, có thể cần khai báo `gradlePlugin { plugins { ... } }` hoặc cơ chế đăng ký tương ứng; đó là workflow khác.

### 9.2. Vì sao chưa có dependency ngoài?

Convention plugin của bài chỉ áp dụng **core Java plugin** và APIs Gradle chuẩn, nên không cần `implementation("some.external.plugin:...")`. Nếu sau này thêm một external Gradle plugin trong precompiled script, phải đặt artifact plugin implementation lên classpath của `build-logic`; xem mục 17.

## 10. Convention plugin: acme.java-conventions.gradle.kts

Đường file phải chính xác:

~~~text
build-logic/src/main/kotlin/acme.java-conventions.gradle.kts
~~~

Nội dung **đầy đủ**:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.api.tasks.testing.logging.TestExceptionFormat
import org.gradle.api.tasks.testing.logging.TestLogEvent

plugins {
    id("java")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

tasks.withType<Test>().configureEach {
    maxHeapSize = "512m"

    testLogging {
        events(TestLogEvent.FAILED, TestLogEvent.SKIPPED)
        exceptionFormat = TestExceptionFormat.FULL
    }
}
~~~

Đây là một **precompiled script plugin** áp dụng cho **Project** (file suffix `.gradle.kts`, không phải `.settings.gradle.kts`). Nó đã:

1. Áp dụng Gradle core plugin `java` vào **project đang apply convention**.
2. Thiết lập Java toolchain 17.
3. Thiết lập `JavaCompile.options.release` 17 để kiểm soát Java source/JDK API target và class.major=61.
4. Thiết lập source encoding UTF-8 cho JavaCompile.
5. Cấu hình mọi `Test` task trong project với heap 512 MiB và chỉ in FAILED/SKIPPED events cùng full stacktrace format.
6. Sử dụng `tasks.withType<...>().configureEach` để tránh eager iteration và bao gồm Test tasks được thêm sau.
7. Không tham chiếu root/subproject khác.
8. Không tự thêm test framework/dependencies vào mọi project; phần nào thật sự có JUnit tests sẽ khai báo JUnit và `useJUnitPlatform()` đúng nơi hoặc tách một test convention plugin.

### 10.1. Plugin ID đến từ filename

Vì file mang tên:

~~~text
acme.java-conventions.gradle.kts
~~~

và **không có `package` declaration**, Gradle cung cấp plugin ID:

~~~text
acme.java-conventions
~~~

Nếu file chỉ mang tên `java-conventions.gradle.kts`, plugin ID tương ứng là `java-conventions`. Nếu dùng package declaration, prefix ID có thể thay theo package. Trong bài lab, luôn thống nhất filename và plugin ID ở cả ba modules.

### 10.2. Plugin áp dụng cho project nào?

Khi `:core` có:

~~~kotlin
plugins {
    id("acme.java-conventions")
}
~~~

script được execute với **Project `:core` làm target**; `tasks`/`java`/`plugins` bên trong là của `:core`. Cùng plugin apply ở `:api` thì chạy với Project `:api`. Đây là khác biệt cốt lõi so với root duyệt toàn bộ subprojects và chỉnh state từ ngoài.

### 10.3. Vì sao apply core Java plugin ở đây?

Convention đặt toolchain và tasks cho Java projects nên chủ động `plugins { id("java") }`. Sau đó module có thể áp plugin chuyên biệt:

- `java-library` khi có API consumers.
- `application` khi có `mainClass`/distribution.
- Có thể chỉ dùng Java plugin nếu module là Java project không cần library/application features.

Những plugin chuyên biệt áp Java support theo chính sách Gradle, việc áp `java` thêm một lần không tạo hai hệ Java tasks. Tuy nhiên điều quan trọng là **các modules tự nói rõ vai trò** qua chính plugin block.

### 10.4. Không áp Java convention cho thư mục build-logic

`build-logic` là một build chứa plugins, dùng `kotlin-dsl`. Không dùng `allprojects { apply(plugin="acme.java-conventions") }` để tự gán Java convention cho nó. Build-logic có toolchain/requirements riêng của Gradle plugin compilation.

## 11. api/build.gradle.kts và Java record

Tạo `api/build.gradle.kts`:

~~~kotlin
plugins {
    id("acme.java-conventions")
    id("java-library")
}
~~~

Không còn lặp lại `java.toolchain`, `options.release`, `options.encoding` hoặc Test logging.

Tạo `api/src/main/java/demo/api/Message.java`:

~~~java
package demo.api;

public record Message(String value) {
}
~~~

`record` là Java feature phù hợp JDK17. Project `:api` là một thư viện đơn giản công bố public type `Message`.

**Không cần external dependency** nên `api/build.gradle.kts` không có `repositories` và `dependencies`. Nếu library có dependencies thật, chỉ khai báo các dependency đặc thù của module tại đây.

### 11.1. Vì sao có cả java-library và convention?

`java-library` nói **module này là Java library** với `api` và `implementation` scopes, outgoing compile/runtime variants. `acme.java-conventions` nói **mọi Java module áp convention dùng các defaults của team**. Không nên buộc application module thành `java-library` chỉ vì muốn chia sẻ compiler options.

## 12. core/build.gradle.kts và Java code

Tạo `core/build.gradle.kts`:

~~~kotlin
plugins {
    id("acme.java-conventions")
    id("java-library")
}

dependencies {
    api(project(":api"))
}
~~~

`api(project(":api"))` thể hiện `:core` công bố public API có kiểu `Message` thuộc `:api`. Không phải dùng `implementation` chỉ để giữ mọi dependency “ẩn”; consumer compile phải biết public type đó.

Tạo `core/src/main/java/demo/core/Greeter.java`:

~~~java
package demo.core;

import demo.api.Message;

public final class Greeter {
    private Greeter() {
    }

    public static Message greetingFor(String name) {
        return new Message("Hello, " + name + "!");
    }
}
~~~

Cấu hình này:

- `:core:compileJava` dùng Java17 toolchain và `--release 17` từ convention.
- Compile classpath của `:core` chứa `:api` vì đã khai báo dependency.
- Public return type `Message` khiến `api(project(":api"))` phù hợp.
- Không cần root build script can thiệp vào `:core`.

### 12.1. Nếu sửa core thành implementation?

Nếu thay:

~~~kotlin
dependencies {
    implementation(project(":api"))
}
~~~

core vẫn compile được, nhưng consumer `:app` có thể không thấy `Message` trên compile classpath dù dùng public API của `Greeter`. Đây là lỗi **dependency graph/contract**, không phải lỗi convention plugin. Convention plugin không nên tự suy đoán mọi project dependencies thành `api`.

## 13. app/build.gradle.kts và Main.java

Tạo `app/build.gradle.kts`:

~~~kotlin
plugins {
    id("acme.java-conventions")
    id("application")
}

dependencies {
    implementation(project(":core"))
}

application {
    mainClass.set("demo.app.Main")
}
~~~

Những phần riêng của `:app` vẫn ở chính module:

- Nó là ứng dụng, không phải library.
- Nó có dependency tới `:core`.
- Nó định nghĩa entry point `demo.app.Main`.
- Nó tự apply convention Java17; không cần root cấu hình thay.

Tạo `app/src/main/java/demo/app/Main.java`:

~~~java
package demo.app;

import demo.api.Message;
import demo.core.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        Message message = Greeter.greetingFor("Gradle");
        System.out.println(message.value());
    }
}
~~~

`Message` đến từ `:api` nhưng app chỉ khai báo `implementation(project(":core"))`: compile của app nhận API dependency qua `:core` vì core dùng `api(project(":api"))`.

### 13.1. Không cần version catalog hay Maven Central cho demo

`:app`, `:core` và `:api` chỉ có project dependencies. Vì vậy main build **không** cần `mavenCentral()` để resolve Java library jars. Tuy nhiên lần đầu thực thi `kotlin-dsl` build logic có thể cần Gradle distribution/tooling dependencies từ plugin portal hoặc cache.

### 13.2. Java source names và packages phải trùng

Project không compile nếu đặt `Main.java` vào `demo/main/Main.java` nhưng khai báo `package demo.app` rồi cấu hình wrong path/script convention. Java file path convention trong ví dụ đúng `src/main/java/demo/app/Main.java`; `application.mainClass` đúng `demo.app.Main`.

## 14. Chạy dự án hoàn chỉnh

Đứng tại root `convention-plugin-lab` và dùng Gradle **tương thích JDK17 và Kotlin DSL**.

Nếu project mới **chưa có Wrapper**, dùng Gradle đã cài:

~~~bash
gradle :app:run --quiet
~~~

**Stdout chính xác của Java application:**

~~~text
Hello, Gradle!
~~~

Đây là output của `demo.app.Main`, không bao gồm task logs. Plugin `application` tự cấu hình `run` với main runtime classpath, chứa classes của `:app`, `:core` và `:api`.

### 14.1. Các lệnh hữu ích

~~~bash
gradle :api:compileJava
gradle :core:compileJava
gradle :app:compileJava
gradle :app:run
gradle :app:build
~~~

`:app:compileJava` không cần bạn chạy thủ công `:core:compileJava` trước: Gradle xác định task dependencies qua project dependency graph.

`:app:build` có thể chạy tasks `jar`/`test`/`check` phù hợp; vì demo **không tạo `src/test`**, Test task có thể báo `NO-SOURCE`. Đó không phải “đã kiểm thử logic bằng JUnit”.

### 14.2. Dùng Wrapper nếu repo đã có

Linux/macOS:

~~~bash
./gradlew --version
./gradlew :app:run --quiet
~~~

Windows:

~~~bat
gradlew.bat --version
gradlew.bat :app:run --quiet
~~~

Nếu repo **chưa có `gradlew`/`gradlew.bat`**, cần tạo Wrapper bằng Gradle đã cài và commit đúng files. Đừng chạy `./gradlew` rồi kết luận plugin lỗi chỉ vì script chưa tồn tại.

### 14.3. Kiểm tra Gradle configuration thực tế

~~~bash
gradle :api:tasks --all
gradle :core:tasks --all
gradle :app:tasks --all
gradle -q javaToolchains
~~~

Task `javaToolchains` mô tả các JDK Gradle tìm thấy. Nếu `java.toolchain.languageVersion=17` không có JDK phù hợp và chưa cấu hình provisioning, Gradle sẽ báo **không tìm được toolchain**, không phải plugin ID sai.

### 14.4. Kiểm tra bytecode

~~~bash
gradle :app:classes
javap -verbose -classpath app/build/classes/java/main demo.app.Main
~~~

Tìm:

~~~text
minor version: 0
major version: 61
~~~

`options.release.set(17)` từ convention plugin yêu cầu javac tạo class.major61. `javap -verbose` còn in nhiều metadata, nên trích đoạn trên **không phải toàn bộ stdout**. Hãy kiểm tra bản javac/JDK và tasks nếu bytecode không phải61.

### 14.5. Kiểm tra dependency graph

~~~bash
gradle :core:dependencies --configuration compileClasspath
gradle :app:dependencies --configuration compileClasspath
gradle :app:dependencies --configuration runtimeClasspath
~~~

Bạn nên thấy về mặt logic:

~~~text
:core compileClasspath
    project :api

:app compileClasspath
    project :core
       project :api (transitive API dependency)

:app runtimeClasspath
    project :core
       project :api
~~~

Đây là **sơ đồ diễn giải**, không phải output Gradle từng ký tự. Ý chính: dependency graph vẫn được mô hình qua `project(":...")`, **không** bằng cách đọc tasks/configurations của project khác để tự nối classpaths.

## 15. Chạy Java 17 độc lập bằng javac và java

Các lệnh sau kiểm tra mã nguồn Java không phụ thuộc Gradle. Chúng **không chứng minh Gradle convention plugin được áp đúng**; để xác minh plugin cần chạy `gradle :app:run` và Gradle diagnostics.

### 15.1. Linux/macOS

~~~bash
mkdir -p out/api out/core out/app

javac --release 17 -d out/api \
  api/src/main/java/demo/api/Message.java

javac --release 17 -cp out/api -d out/core \
  core/src/main/java/demo/core/Greeter.java

javac --release 17 -cp out/api:out/core -d out/app \
  app/src/main/java/demo/app/Main.java

java -cp out/api:out/core:out/app demo.app.Main
~~~

Stdout chính xác:

~~~text
Hello, Gradle!
~~~

### 15.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force -Path out\api,out\core,out\app |
    Out-Null

javac --release 17 -d out\api api\src\main\java\demo\api\Message.java

javac --release 17 -cp out\api -d out\core core\src\main\java\demo\core\Greeter.java

javac --release 17 -cp "out\api;out\core" -d out\app app\src\main\java\demo\app\Main.java

java -cp "out\api;out\core;out\app" demo.app.Main
~~~

Stdout tương ứng:

~~~text
Hello, Gradle!
~~~

`javac --release 17` yêu cầu compiler JDK17 trở lên có hỗ trợ release17. Windows classpath separator là `;`, trong khi Linux/macOS là `:`.

### 15.3. Vì sao không dùng java -jar của app ngay?

Plugin `application` có task `run` và distribution tasks. `jar` thông thường không tự tạo executable manifest Main-Class và không gói mọi runtime dependencies vào một JAR. Nếu muốn test binary distribution, dùng `installDist`/`distZip` rồi chạy script từ distribution:

~~~bash
gradle :app:installDist
./app/build/install/app/bin/app
~~~

Đường dẫn minh họa theo application distribution default. Nếu module đổi application name hoặc paths, inspect output thật trước khi chạy. `java -jar app/build/libs/app.jar` **không nhất thiết chạy** như `:app:run`, đó là khác biệt packaging chứ không phải convention plugin sai.

## 16. Before/after: điều gì thực sự thay đổi?

### 16.1. Trước migration

~~~text
root/build.gradle.kts
   |
   +-- subprojects { apply java; set toolchain17; configure Test... }
           |
           +-- changes :api project
           +-- changes :core project
           +-- changes :app project
~~~

Module scripts không nói rõ policy được áp như thế nào.

### 16.2. Sau migration

~~~text
root/settings.gradle.kts
       |
       +-- pluginManagement.includeBuild("build-logic")
                       |
                       +-- acme.java-conventions plugin
                               |
                  +------------+------------+
                  |            |            |
             :api apply    :core apply   :app apply
                  |            |            |
            java-library  java-library  application
                  |            |            |
             API source   core source    mainClass
~~~

Plugin code **không** chạy một lần để cấu hình cả ba project. Nó được áp dụng cho **mỗi project tự chọn**, trong target context của project đó.

### 16.3. Bảng đối chiếu

| Khía cạnh | Cross-project config từ root | Convention plugin |
| --- | --- | --- |
| Nơi định nghĩa logic chung | Root `build.gradle.kts` | `build-logic/src/main/kotlin/*.gradle.kts` |
| Nơi quyết định module opt-in | Root duyệt project collection | `plugins { id("...") }` ở module |
| Target Project được sửa | Project con, từ script của root | Project đã tự apply plugin |
| Nhìn vào module script | Có thể không thấy policy | Thấy plugin ID rõ |
| Kiểm thử logic | Root build integration | Plugin/consumer functional tests |
| Reuse giữa builds | Copy root block hoặc script plugin | Included build hoặc published plugin |
| Isolated Projects | Cross-project mutations có thể vi phạm | Local target plugin thích hợp hơn |
| Customizations | Nhiều if/path conditions ở root | Module-specific config cạnh plugin application |

### 16.4. Đưa gì vào convention?

Nên đưa:

- Java toolchain/release/encoding policy dùng chung.
- Test JVM options, logging defaults, JUnit setup nếu cùng test framework.
- Checkstyle/SpotBugs/JaCoCo, license/formatting conventions (khi có plugin/deps đúng).
- Archive reproducibility/copy defaults phù hợp.
- Shared task types và verification hooks.

Không nên đưa:

- `application.mainClass` chung cho mọi Java module.
- Module-specific project dependencies không liên quan mọi module.
- API dependencies của chỉ một library.
- Secret credentials hard-code.
- Đường dẫn thư mục local của một developer.
- Logic lấy mutable state của `project(":other")` để chỉnh task của other project.

## 17. Quy trình migration từng bước, tránh làm hỏng build lớn

### 17.1. Bước 1: kiểm kê, không copy nguyên root block

Xem root `subprojects { }`/`allprojects { }` và phân loại từng thao tác:

| Loại thao tác | Đưa về đâu? |
| --- | --- |
| Java compile/test policy chung | `java-conventions` plugin |
| Library API/publish policy | `java-library-conventions` plugin |
| Application runtime/distribution policy | `application-conventions` plugin |
| Repository resolution policy | `settings.gradle.kts`/`dependencyResolutionManagement` |
| Version aliases | Version catalog |
| Dependency giữa modules | `dependencies { api/implementation(project(":...")) }` ở consumer |
| Metadata aggregate/reports | Root aggregate task/variant artifact collection được mô hình rõ |
| Secret CI credentials | CI secrets + Providers, không hard-code |
| Chỉ một module cần khác | Trong module build script/extension |

Không đưa tất cả logic vào một plugin duy nhất nếu có nhiều loại module. Hãy **cắt theo trách nhiệm** thay vì chỉ đổi chỗ của giant block.

### 17.2. Bước 2: tạo included build

Tạo `build-logic/settings.gradle.kts`, `build-logic/build.gradle.kts` và `src/main/kotlin/...gradle.kts`.

### 17.3. Bước 3: đăng ký plugin resolution

Trong root `settings.gradle.kts`, thêm `pluginManagement { includeBuild("build-logic") }`. Không dùng `include(":build-logic")` để thay thế.

### 17.4. Bước 4: áp plugin ở một module thử nghiệm

Chuyển một module nhỏ như `:api` sang:

~~~kotlin
plugins {
    id("acme.java-conventions")
    id("java-library")
}
~~~

Kiểm:

~~~bash
gradle :api:compileJava --stacktrace
gradle :api:tasks --all
~~~

Rồi so compiler target, Java toolchain, Test task defaults với trước migration. Không đổi đồng thời Gradle Wrapper, JDK, plugin versions nếu không cần.

### 17.5. Bước 5: chuyển các modules còn lại

Chuyển `:core`, `:app`. Sau mỗi bước compile/run task của module; nếu app dùng APIs từ library, kiểm consumer compilation.

### 17.6. Bước 6: xóa cấu hình chéo cũ

**Chỉ sau khi modules đã áp plugin**, xóa root `subprojects`/`allprojects` rules tương đương. Nếu giữ cả hai, plugin có thể bị root override hoặc task options được cấu hình hai lần, làm debug rất khó.

Không dùng một `allprojects` khác để “tự động áp convention plugin” rồi tuyên bố đã tách coupling. Quyết định apply cần chuyển về từng module hoặc một cơ chế isolated lifecycle được thiết kế rõ và hỗ trợ plugin resolution.

### 17.7. Bước 7: chạy regression build

~~~bash
gradle clean :app:build
gradle :app:run --quiet
gradle :app:dependencies --configuration compileClasspath
~~~

So những điều quan trọng trước/sau: Java release, dependencies, tasks, artifact contents, smoke tests, test reports và build warnings. Build thành công **không chứng minh** policy không thay đổi; cần kiểm chính output.

### 17.8. Bước 8: kiểm Configuration Cache và Isolated Projects nếu phù hợp

~~~bash
gradle :app:run --configuration-cache
gradle :app:run --configuration-cache
~~~

Lần thứ hai có thể reuse configuration nếu inputs không đổi, plugins/tasks đáp ứng constraints và Gradle version hỗ trợ. **Không bảo đảm** mọi build tự cache được chỉ vì đã chuyển thành convention plugin.

Với Gradle release có hỗ trợ Isolated Projects:

~~~bash
gradle help --isolated-projects
~~~

Chế độ **Isolated Projects** vẫn đang ở giai đoạn incubating trên các bản Gradle hiện đại; cần đọc tài liệu/limitations của **đúng version**. Nếu lỗi còn từ plugin bên ngoài hay code ở module, xem report rồi sửa từng vi phạm. Không bật flag không được bản Gradle đang dùng hỗ trợ.

## 18. Configuration Cache và Isolated Projects khác nhau thế nào?

### 18.1. Configuration Cache

**Configuration Cache** lưu kết quả cấu hình/task graph khi inputs phù hợp để tái sử dụng ở lần build sau, tránh lặp configuration work.

Một convention plugin có thể thân thiện với Configuration Cache nếu:

- Task properties dùng Providers/typed properties đúng.
- Không đọc `Project`/`Gradle`/script objects trái phép trong task execution.
- Không capture mutable configuration state trong task actions.
- Inputs và outputs được khai báo rõ.

Nhưng **chỉ đóng code vào plugin không tự làm mọi custom task cache-compatible**. Nếu plugin vẫn dùng `doLast { project... }` sai cách, lỗi vẫn còn.

### 18.2. Isolated Projects

**Isolated Projects** nhằm tách mutable configuration state giữa các Project để cho phép song song hóa configuration và tối ưu caching ở quy mô lớn. Những truy cập như:

~~~kotlin
project(":core").tasks.named("compileJava") {
    // Root đang sửa tasks của :core từ context khác.
}
~~~

là ví dụ cross-project mutable state access nên tránh. Trong mô hình plugin local, logic được thực thi trên project apply plugin, không cần truy cập Project objects của siblings.

Lưu ý: Isolated Projects khác Configuration Cache. Một build có thể reuse Configuration Cache trong những điều kiện nhất định mà chưa vượt qua các ràng buộc isolation chặt hơn. Gradle documentation và API có thể thay đổi theo release khi tính năng incubating.

### 18.3. Quan hệ dependency không phải cross-project mutation

Cấu hình:

~~~kotlin
dependencies {
    implementation(project(":core"))
}
~~~

là **khai báo dependency hợp lệ**. Nó khác việc đọc/sửa:

~~~kotlin
project(":core").tasks.configureEach {
    // Chỉnh mutable tasks của project khác.
}
~~~

Đừng loại bỏ project dependencies để “đạt isolation”; mục tiêu là dùng Gradle's dependency/variant model thay cho mutation trực tiếp qua Project references.

### 18.4. Ưu tiên Provider và task outputs

Thay vì một project lấy absolute path từ `otherProject.buildDir`, hãy:

- Dùng project dependency với outgoing variant/artifact nếu cần tiêu thụ binary.
- Dùng typed task input nối với output provider nếu trong cùng target project.
- Với shared data/aggregate reports, thiết kế artifact variant hoặc dedicated aggregation task thay vì chọc vào internal tasks của siblings.
- Nếu cần shared external state, xem Build Services và providers đúng phạm vi.

Không tự lấy `rootProject.version` từ subproject chỉ để gom version policy nếu Isolated Projects constraints cấm đọc mutable Project state. Nên dùng version catalog, gradle.properties/provider hoặc file input được định nghĩa từ scope phù hợp.

## 19. Dùng convention cho cả library, application và tests

### 19.1. Một plugin chung không đủ cho mọi vai trò

Bài lab dùng một `acme.java-conventions` làm **base**. Trong repository thật, có thể tạo ba plugins:

~~~text
build-logic/src/main/kotlin/
├── acme.java-conventions.gradle.kts
├── acme.java-library-conventions.gradle.kts
└── acme.java-application-conventions.gradle.kts
~~~

Vai trò:

- `acme.java-conventions`: Java toolchain, compile/release, Test defaults.
- `acme.java-library-conventions`: áp `java-library`, library publication/ABI policy.
- `acme.java-application-conventions`: áp `application`, distribution/runnable app defaults.

Precompiled script plugins có thể được **compose**. Thiết kế composition nên được kiểm bằng một consumer build, đặc biệt nếu mix external plugins.

### 19.2. Ví dụ plugin library (fragment minh họa)

Tạo file `acme.java-library-conventions.gradle.kts` trong `build-logic/src/main/kotlin`:

~~~kotlin
plugins {
    id("acme.java-conventions")
    id("java-library")
}
~~~

Khi plugin IDs nằm trong cùng plugin build, composition cho phép mỗi module chỉ apply library convention:

~~~kotlin
plugins {
    id("acme.java-library-conventions")
}
~~~

**Chú ý về phạm vi:** Đây là ví dụ mở rộng **thay thế cách apply hai plugins riêng** ở project lab. Đừng vừa đổi `:api` sang library convention vừa giữ một root cross-project block nữa; khi migrate, chỉ một nguồn chịu trách nhiệm chung.

### 19.3. Application convention (fragment minh họa)

~~~kotlin
plugins {
    id("acme.java-conventions")
    id("application")
}
~~~

File `acme.java-application-conventions.gradle.kts` sẽ tạo plugin ID tương ứng. App vẫn nên giữ:

~~~kotlin
application {
    mainClass.set("demo.app.Main")
}
~~~

trong `app/build.gradle.kts` trừ khi tất cả apps cùng entry point — trường hợp hiếm.

### 19.4. Test convention không nên ép mọi module thêm JUnit

Nếu cùng team đều dùng JUnit Jupiter, có thể tạo riêng `acme.java-test-conventions` áp `useJUnitPlatform()`, thêm JUnit dependencies/version platform theo chính sách. Nhưng nếu có module không chứa tests hoặc dùng TestNG/JUnit4, ép JUnit Platform cho tất cả có thể tạo lỗi discovery/engine.

Thực hành tốt:

- Base plugin thiết lập JDK/compiler.
- Test plugin thiết lập JUnit/coverage khi cần.
- Library plugin định nghĩa API/publishing.
- Application plugin định nghĩa distribution/run.
- Mỗi subproject áp những convention plugins **phù hợp vai trò**.

### 19.5. Hãy giữ per-project dependency riêng

Không nên đưa:

~~~kotlin
dependencies {
    api(project(":api"))
}
~~~

vào một base convention plugin áp mọi module. Plugin sẽ buộc mọi project phụ thuộc `:api`, có thể tạo circular dependencies hoặc khiến app phải có `java-library` để nhận `api` bucket.

Dependency modules nên được đặt tại nơi **người tiêu thụ thật sự** cần chúng.

## 20. External plugin trong precompiled script plugin

Giả sử muốn đưa Checkstyle/SpotBugs/Shadow vào convention.

### 20.1. Core plugin không cần implementation dependency ngoài

`java`, `java-library`, `application`, `checkstyle` và `jacoco` là core Gradle plugins. Trong precompiled script plugin:

~~~kotlin
plugins {
    id("java-library")
    id("jacoco")
}
~~~

Không cần khai báo một version riêng cho core plugins.

### 20.2. External plugin cần dependency trong plugin build

Với external plugin, ví dụ minh họa plugin `com.example.quality` (tên **giả**, không khẳng định có artifact thật), **đừng** viết trực tiếp:

~~~kotlin
plugins {
    id("com.example.quality") version "1.2.3"
}
~~~

trong precompiled script plugin. Precompiled script plugins không hỗ trợ cú pháp `version` trong `plugins { }`; version phải đến từ dependency classpath của **build-logic**.

Dạng thiết kế đúng:

~~~kotlin
// build-logic/build.gradle.kts — minh họa cú pháp
dependencies {
    implementation("com.example:quality-gradle-plugin:1.2.3")
}
~~~

Và trong precompiled script plugin:

~~~kotlin
plugins {
    id("com.example.quality")
}
~~~

**Hai tọa độ trên là placeholders mang ý nghĩa học thuật?** Không sử dụng để chạy: chúng chỉ minh họa pattern, không phải artifact thật của bài lab. Khi áp dụng production, cần thay bằng plugin artifact/ID chính xác từ official documentation, pin version và kiểm plugin's Gradle compatibility.

### 20.3. Tại sao cần phân biệt pluginMarker và implementation artifact?

Plugin Portal có thể resolve plugin marker module, trong khi `build-logic dependencies { implementation(...) }` thường dùng **implementation artifact coordinates** thực tế của plugin. Không giả định marker coordinates và implementation coordinates luôn giống nhau.

Gradle có thể báo:

~~~text
Plugin [id: 'com.example.quality'] was not found
~~~

ngay cả khi plugin dependency bạn thêm có vẻ đúng tên. Kiểm tra JAR/plugin descriptors và plugin documentation.

## 21. Version catalog trong included build: lưu ý scope riêng

Một cấu trúc có:

~~~text
gradle/libs.versions.toml
build-logic/settings.gradle.kts
build-logic/build.gradle.kts
~~~

không có nghĩa included build `build-logic` **tự nhìn thấy** version catalog `libs` của root build. Nó là một build riêng.

Nếu muốn dùng chung catalog file, có thể đăng ký **tường minh** trong `build-logic/settings.gradle.kts`:

~~~kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}
~~~

Đây là **snippet nâng cao**, chỉ áp dụng khi file TOML thật sự tồn tại; không có trong project runnable của mục 6–14.

### 21.1. Precompiled plugin và plugin alias

Không nên giả định `alias(libs.plugins.somePlugin)` hoạt động trực tiếp trong `plugins { }` của một precompiled script plugin y hệt build script consumer. Plugin IDs trong precompiled script cần có implementation classpath và cơ chế resolution phù hợp.

Nếu muốn sử dụng versions từ catalog cho external Gradle plugin dependencies, có thể xử lý trong `build-logic/build.gradle.kts` hoặc custom plugin registration theo tài liệu Gradle/Kotlin DSL. Đừng đặt version trong `plugins { }` của precompiled script plugin.

### 21.2. Central repository policy

`dependencyResolutionManagement.repositories` của main settings dùng để quản lý **module dependencies của main build**. Included build `build-logic` có repositories của riêng nó để tải plugin implementation dependencies. Nếu CI chặn network, phải cấu hình cả hai scopes/mirrors phù hợp.

Tránh cấu hình mâu thuẫn vừa `dependencyResolutionManagement.repositoriesMode=FAIL_ON_PROJECT_REPOS` vừa để convention plugin tự thêm `repositories { mavenCentral() }` trong từng subproject. Nếu repos được quản lý tập trung ở settings, convention không nên tự thêm project repos.

## 22. Defaults, overrides và policy rõ ràng

### 22.1. Vì sao set(17) có thể được module override?

Trong bài lab:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Đây là cấu hình tường minh. Một module khác có thể thay đổi Java toolchain bằng script chạy sau, tùy cách extensions/properties được configure. Nếu **team bắt buộc** mọi module target17, cần cân nhắc kiểm tra policy/validation chứ không chỉ tin vào một assignment.

### 22.2. Cho phép custom values qua extension

Trong precompiled script plugin, có thể khai báo managed extension:

~~~kotlin
import org.gradle.api.provider.Property

interface TeamQualityExtension {
    val testHeap: Property<String>
}

val teamQuality = extensions.create<TeamQualityExtension>(
    "teamQuality"
)
teamQuality.testHeap.convention("512m")

tasks.withType<Test>().configureEach {
    maxHeapSize = teamQuality.testHeap.get()
}
~~~

**Đây là fragment nâng cao**, không phải một project độc lập. Giả định Java plugin đã tạo `Test` tasks và type `Test` import phù hợp.

Module có thể override:

~~~kotlin
teamQuality {
    testHeap.set("768m")
}
~~~

Cách này tốt hơn hard-code `if (project.name=="integration") ...` trong plugin cho mọi project. Mặc dù dùng `Property.convention(...)` đem đến default rõ ràng, chú ý khi nào `get()` được gọi; tránh snapshot giá trị quá sớm trước khi consumer có cơ hội cấu hình.

### 22.3. Không biến convention thành “bảng ngoại lệ theo tên project”

Anti-pattern:

~~~kotlin
when (project.name) {
    "api" -> { /* policy A */ }
    "app" -> { /* policy B */ }
    else -> { /* policy C */ }
}
~~~

Đây là đoạn minh họa không độc lập. Nếu số nhánh tăng, hãy tạo **role-specific plugins** hoặc exposed extension phù hợp. Điều kiện theo tên project cứng khiến plugin khó tái sử dụng khi rename module.

## 23. Testing convention plugins: unit, functional, consumer

### 23.1. Kiểm qua một consumer project thật

Dự án mẫu của mục 6–14 đã là consumer integration test tự nhiên:

~~~bash
gradle :api:compileJava
gradle :core:compileJava
gradle :app:run --quiet
~~~

Nếu `:app:run` in `Hello, Gradle!` và `javap` cho major61, ta đã kiểm được:

- Plugin ID resolve qua included build.
- Convention áp dụng Java toolchain/compiler release cho module.
- Module-specific Java library/application plugins vẫn hoạt động.
- Project dependencies compile/runtime đúng.
- Source Java 17 chạy được.

### 23.2. Test plugin “có được apply đúng chỗ không”

Kiểm source scripts:

~~~text
api/build.gradle.kts  -> acme.java-conventions + java-library
core/build.gradle.kts -> acme.java-conventions + java-library
app/build.gradle.kts  -> acme.java-conventions + application
~~~

Đây là **bằng chứng opt-in** rõ ràng; module khác không apply plugin thì không bị “root tiêm” cấu hình.

### 23.3. Gradle TestKit

Với convention plugin phát triển lâu dài, có thể viết **functional tests bằng Gradle TestKit**:

1. Tạo một temporary consumer build.
2. Viết `settings.gradle.kts`/`build.gradle.kts` áp plugin.
3. Chạy `GradleRunner` để test plugin resolution/configuration.
4. Kiểm task output/compiler settings/expected failures.
5. Chạy test với Configuration Cache khi plugin hỗ trợ.
6. Test cả module áp convention và module không áp.
7. Với external plugin integration, pin các Gradle/JDK versions được hỗ trợ.

TestKit tests của plugin build không thay thế integration tests của application, nhưng phát hiện regressions khi plugin logic đổi.

### 23.4. Bài kiểm tra negative case

Cố ý tạo một module `docs` không apply `acme.java-conventions`, hoặc thêm một `customTask` không liên quan Java. Nó không nên tự có `compileJava` từ root cross-project rules.

Nếu vẫn có, tìm root script, init scripts hoặc plugin khác đang apply Java trên module; chưa chắc refactor đã hoàn tất.

## 24. Hiệu năng: không hứa “chuyển plugin là build nhanh ngay”

### 24.1. Có thể cải thiện gì?

- Module scripts ít trùng lặp và trách nhiệm rõ hơn.
- Không còn root cần sửa Project objects của tất cả modules lúc configuration.
- Dễ dùng lazy task configuration (như `configureEach`).
- Phù hợp hơn với Isolated Projects và các tối ưu configuration theo khả năng Gradle release.
- Có một nơi review shared defaults.
- Build logic có thể được test/version hóa riêng.

### 24.2. Những chi phí vẫn tồn tại

- Precompiled script plugins cần được **compile** trong `build-logic`.
- Khi build logic thay đổi, nhiều consumers có thể phải reconfigure/recompile scripts.
- External plugin classpath có thể làm plugin build lớn hơn.
- Plugin dùng `tasks.all`/`afterEvaluate`/Project accesses sai vẫn gây configuration overhead.
- Configuration Cache invalidation không biến mất chỉ vì đổi tên từ block sang plugin.

Vì vậy benchmark với cùng Gradle Wrapper, JDK, tasks và caches. Đừng chỉ so hai lần đầu tiên khi build logic compilation đang warming up.

### 24.3. configureEach vs all

Nên ưu tiên:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

thay vì eager API:

~~~kotlin
tasks.withType<JavaCompile>().all {
    options.encoding = "UTF-8"
}
~~~

`configureEach` trì hoãn configuration đến khi task được realized, có ích cho task configuration avoidance. Cần tránh các calls như `tasks.getByName(...)`/`tasks.create(...)` ở những nơi không cần eager behavior.

## 25. Những lỗi thường gặp và cách sửa

### Lỗi 1. Plugin ID không tìm thấy

~~~text
Plugin [id: 'acme.java-conventions'] was not found
~~~

Kiểm `pluginManagement { includeBuild("build-logic") }`, file path `src/main/kotlin`, filename/plugin ID và build-logic compilation logs. Đừng tự thêm `version "1.0"` vào plugin ID của included build khi không cần.

### Lỗi 2. Viết include(":build-logic")

Sai mô hình included plugin build.

**Sửa:** `pluginManagement.includeBuild("build-logic")`; giữ `include(":api", ":core", ":app")` cho main subprojects.

### Lỗi 3. Quên kotlin-dsl

`build-logic` có file `*.gradle.kts` trong `src/main/kotlin` nhưng không cấu hình plugin development build.

**Sửa:** Apply ``kotlin-dsl`` trong `build-logic/build.gradle.kts`.

### Lỗi 4. Dùng plugin ID khác filename

File `acme.java-conventions.gradle.kts` nhưng consumer ghi `id("company.java-conventions")`.

**Sửa:** Thống nhất ID theo filename/package.

### Lỗi 5. External plugin không có trên classpath

Precompiled plugin gọi `id("com.vendor.plugin")` nhưng `build-logic.dependencies` không có artifact plugin implementation.

**Sửa:** Xác minh tọa độ artifact và thêm `implementation(...)` vào plugin build đúng version; không nhét version vào `plugins` của precompiled script.

### Lỗi 6. Toolchain 17 không có

~~~text
No matching toolchains found for languageVersion=17
~~~

**Sửa:** Cài JDK17 phù hợp, cấu hình detection/provisioning đúng hoặc kiểm `javaToolchains`. Không phải lỗi do root không có `subprojects`.

### Lỗi 7. App không có task run

`app/build.gradle.kts` chỉ có Java convention mà không áp `application`.

**Sửa:** Apply `id("application")` và đặt `application.mainClass` tại app.

### Lỗi 8. Library không nhận api(...)

`:core` chỉ apply Java core/convention, không apply `java-library`.

**Sửa:** Apply `id("java-library")` ở module library hoặc role-specific library convention.

### Lỗi 9. Core compile nhưng app không tìm Message

`:core` khai báo `implementation(project(":api"))` dù public return type là `Message`.

**Sửa:** Dùng `api(project(":api"))` để xuất đúng compile contract.

### Lỗi 10. Giữ root subprojects block

Sau migration, root vẫn cấu hình `options.release`/Test/Java plugin cho các modules.

**Sửa:** Xóa những rules trùng sau khi xác minh plugin áp đúng; tránh hai nguồn config ghi đè nhau.

### Lỗi 11. Convention tự tham chiếu project(":other").tasks

Nó lại gây cross-project mutable state access.

**Sửa:** Chỉ config target project, dùng dependencies/variants/providers để truyền artifact/data.

### Lỗi 12. rootProject.version bị đọc từ subproject

Có thể vi phạm Isolated Projects khi đọc mutable state.

**Sửa:** Dùng Gradle property/provider/file hoặc cơ chế metadata phù hợp thay vì truy Project khác.

### Lỗi 13. included build không thấy libs catalog

`build-logic` là build riêng nên root `libs` không tự có mặt.

**Sửa:** Import catalog rõ trong build-logic settings nếu cần, và đọc giới hạn của precompiled script plugin accessors.

### Lỗi 14. RepositoriesMode.FAIL_ON_PROJECT_REPOS xung đột

Root settings quản lý repositories, nhưng convention plugin thêm `mavenCentral()` vào từng project.

**Sửa:** Đưa repository policy vào settings và tránh project-level repos trong plugin.

### Lỗi 15. Bật Isolated Projects mà build fail

Plugin khác hoặc module script vẫn truy mutable state của project khác; hoặc Gradle version chưa hỗ trợ flag.

**Sửa:** Đọc error report theo version, sửa các cross-project accesses; convention không tự bảo đảm toàn build tương thích.

### Lỗi 16. Dùng afterEvaluate cho mọi thứ

Plugin đợi đến cuối configuration mới sửa tasks, gây ordering khó hiểu và có thể cản task avoidance.

**Sửa:** Dùng `plugins.withId(...)` khi cần phản ứng plugin khác, và `tasks.named`/`configureEach`/Provider APIs.

### Lỗi 17. Dùng apply(from="...") và nghĩ giống precompiled plugin

Script plugin thường có phạm vi/cache/test khác, không có cùng plugin ID/type safety/classpath workflow.

**Sửa:** Khi logic dùng chung dài hạn, ưu tiên convention precompiled/binary plugin.

### Lỗi 18. Áp một library convention cho application

Làm app có các publishing/library scopes không cần thiết, khó phân vai.

**Sửa:** Base Java convention + role-specific plugins.

### Lỗi 19. Đưa mọi dependencies vào base plugin

Mọi module tự nhận `implementation(project(":api"))` hoặc JUnit dù không cần, có nguy cơ circular deps.

**Sửa:** Chỉ đưa dependencies thật sự chung và giữ module-specific deps trong module.

### Lỗi 20. Kết luận plugin pass vì Gradle help pass

`gradle help` không chứng minh compile/test/run behavior.

**Sửa:** Build consumer modules, javap bytecode, đọc dependency graph, chạy smoke test.

### Lỗi 21. So thời gian build lần đầu rồi kết luận chậm hơn

Included plugin build chưa có caches.

**Sửa:** Tách cold build và warm build, benchmark trên cùng điều kiện.

### Lỗi 22. Thay Gradle, JDK, plugins cùng lúc

Khó biết regression đến từ migration hay version compatibility.

**Sửa:** Refactor cấu trúc trước, pin versions, kiểm regression; upgrade có bước riêng.

## 26. Mười tám bài tập thực hành có đáp án

### Bài 1. Chỉ ra cấu hình chéo

~~~kotlin
subprojects {
    tasks.withType<JavaCompile>().configureEach {
        options.release.set(17)
    }
}
~~~

**Đáp án:** Root script đang cấu hình mutable tasks của subprojects. Mẫu được khuyên thay bằng convention plugin được mỗi module apply.

### Bài 2. Mục tiêu của convention

Team muốn Java17 cho `:api` và `:core`, nhưng không muốn áp Java plugin cho `:docs`.

**Đáp án:** Chỉ `:api` và `:core` apply `acme.java-conventions`; `:docs` không apply nếu không cần.

### Bài 3. Plugin ID từ filename

File là `build-logic/src/main/kotlin/acme.java-conventions.gradle.kts`, không có package. ID là gì?

**Đáp án:** `acme.java-conventions`.

### Bài 4. includeBuild hay include?

Cần cho Gradle resolve plugin `acme.java-conventions` của build-logic.

**Đáp án:** `pluginManagement { includeBuild("build-logic") }` ở root settings, không phải `include(":build-logic")`.

### Bài 5. build-logic plugin gì?

`build-logic/build.gradle.kts` phải apply plugin gì để biên dịch precompiled Kotlin DSL scripts?

**Đáp án:** ``kotlin-dsl``.

### Bài 6. API và implementation

`:core` public method trả `demo.api.Message`. Nó nên dùng dependency scope nào tới `:api`?

**Đáp án:** `api(project(":api"))` trong Java Library module.

### Bài 7. Application plugin

`:app` áp Java convention và có Main.java nhưng không có `:app:run`.

**Đáp án:** Apply `id("application")` và cấu hình `mainClass.set("demo.app.Main")`.

### Bài 8. Java17 compile target

Plugin có `JavaCompile.options.release.set(17)`. Class file major thông thường của Java17 là gì?

**Đáp án:** 61.

### Bài 9. App stdout

Với project runnable giữ nguyên, chạy:

~~~bash
gradle :app:run --quiet
~~~

**Đáp án:**

~~~text
Hello, Gradle!
~~~

### Bài 10. Có cần internet cho Java source của demo?

**Đáp án:** Main build chỉ có project dependencies nên không cần download application library. Nhưng Gradle distribution và Kotlin DSL/plugin build có thể cần repositories/cache trong lần chuẩn bị đầu.

### Bài 11. Cấu hình chung nhưng có override

Team muốn heap test 512m mặc định, app integration test cần 768m.

**Đáp án:** Convention plugin có thể expose `Property<String>` với `convention("512m")`, app override qua extension; hoặc module config đúng task sau khi apply, tùy policy.

### Bài 12. Caching

Chuyển root block vào convention plugin có tự đảm bảo Configuration Cache pass không?

**Đáp án:** Không. Custom tasks/actions phải đáp ứng Configuration Cache constraints và inputs/outputs; test bằng `--configuration-cache`.

### Bài 13. Isolated Projects

Một plugin áp ở `:app` gọi `project(":core").tasks.named(...)` để đổi compiler options. Có tốt không?

**Đáp án:** Không. Nó truy cập mutable state của project khác; dùng convention plugin apply ở `:core` hoặc mô hình dependency/variant thay thế.

### Bài 14. buildSrc hay build-logic?

Một repo nhỏ chỉ có vài custom build helpers, muốn setup nhanh.

**Đáp án:** `buildSrc` có thể đủ. Repo nhiều modules có thể chọn included build `build-logic` cho boundary plugin rõ; kiểm build cost thực tế.

### Bài 15. Version catalog

`libs.versions.toml` có tự áp Java plugin và Test logging cho mọi module?

**Đáp án:** Không. Version catalog quản lý aliases/versions; convention plugin thực hiện cấu hình.

### Bài 16. Repositories

Root settings đang `FAIL_ON_PROJECT_REPOS`, convention plugin thêm `mavenCentral()` vào project.

**Đáp án:** Sẽ xung đột policy; giữ module repositories trong `dependencyResolutionManagement` settings khi muốn centralized control.

### Bài 17. External plugin

Precompiled script plugin viết `id("com.vendor.quality") version "1.0"`. Vấn đề gì?

**Đáp án:** Version syntax không được hỗ trợ ở plugins block của precompiled script plugin; đưa đúng implementation artifact version vào `build-logic.dependencies` và áp ID không kèm version.

### Bài 18. Migration hoàn tất chưa?

Subprojects đã apply `acme.java-conventions` nhưng root vẫn có `subprojects { apply(plugin="java"); ... }`.

**Đáp án:** Chưa. Hai nguồn cấu hình còn chồng lên nhau; cần xóa cấu hình chéo cũ sau khi kiểm regressions.

## 27. Checklist kiến trúc và release quality

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Subproject ownership | Mỗi module tự apply plugins và khai dependencies riêng |
| Cấu hình chung | Có convention plugin thay root `subprojects/allprojects` để chỉnh state |
| Plugin discovery | `pluginManagement.includeBuild("build-logic")` đúng và plugin ID resolve |
| Build logic layout | `build-logic/settings.gradle.kts`, `build.gradle.kts`, `src/main/kotlin/*.gradle.kts` |
| Precompiled support | `kotlin-dsl` applied và repositories phù hợp |
| Java17 | Toolchain/release/encoding đặt trong convention và được kiểm thật |
| Project roles | Library dùng `java-library`, app dùng `application` |
| Compile API | `api(project(":api"))` xuất type công khai đúng |
| Dependency graph | `:app` dùng `implementation(project(":core"))` và transitive API |
| Source/run test | `:app:run --quiet` có stdout chính xác |
| Task laziness | `tasks.withType.configureEach`, không eager mutation không cần thiết |
| Configuration Cache | Kiểm thử riêng bằng `--configuration-cache` |
| Isolated Projects | Không truy mutable Project state của modules khác, xét version limitations |
| Plugin external deps | Pin implementation artifacts trong build-logic nếu dùng plugins bên ngoài |
| Version catalog | Có chính sách import riêng cho included build nếu cần |
| Repositories | Không thêm project repos trái settings policy |
| Migration | Xóa rules cũ sau khi chuyển từng module và kiểm regressions |
| Tests | Có consumer integration/functional tests cho convention |
| Dự án lớn | Chia base/library/app/test conventions theo vai trò, tránh giant plugin |

**Kết luận:** Trong **Gradle multi-project build**, `subprojects { }`/`allprojects { }` để áp quy ước chung có thể tạo hidden configuration và cross-project coupling. Chuyển logic dùng chung vào **convention plugin** cho phép mỗi project tự opt-in, vẫn có một nguồn cấu hình Java toolchain/compile/test thống nhất, đồng thời mở đường cho testability, lazy configuration và khả năng tương thích tốt hơn với **Isolated Projects**. Mô hình đầy đủ: **root settings khai báo topology và plugin resolution; build-logic định nghĩa convention; từng module tự áp plugin và khai dependency/role của mình**.

## 28. Tài liệu tham khảo chính thức

- [Gradle — Sharing Build Logic Between Subprojects](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html) — `buildSrc`/`build-logic` và khuyến nghị tránh `subprojects/allprojects`.
- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html) — mục đích và cách triển khai conventions.
- [Gradle — Precompiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html) — `kotlin-dsl`, plugin ID từ filename, external plugin classpath.
- [Gradle — Isolated Projects](https://docs.gradle.org/current/userguide/isolated_projects.html) — constraints, caveats và migration từ cross-project access.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html) — yêu cầu cho task/plugin và kiểm cache reuse.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html) — settings `include`, project paths và dependencies.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html) — included builds và build logic boundaries.
- [Gradle — Plugins](https://docs.gradle.org/current/userguide/plugins.html) — core vs community vs custom plugins, plugin resolution.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html) — `configureEach` và lazy tasks.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html) — API/implementation scopes và consumer variants.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html) — `run`, `mainClass`, distribution tasks.
- [Gradle — Toolchains](https://docs.gradle.org/current/userguide/toolchains.html) — Java languageVersion và compiler release.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html) — cấu trúc TOML và catalog scopes.
- [Gradle — Testing Plugins](https://docs.gradle.org/current/userguide/testing_gradle_plugins.html) — Gradle TestKit/functional tests.
