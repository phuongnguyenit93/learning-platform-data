# Plugin management, plugin marker và nơi phân giải plugin trong Gradle

## 1. Plugin ID không phải là tên một file JAR

Gradle plugin bổ sung khả năng cho build: tạo task, extension, conventions, kiểm thử, đóng gói, xuất bản hoặc tích hợp công cụ ngoài. Câu lệnh:

```kotlin
plugins {
    id("com.example.greeting") version "1.0.0"
}
```

chỉ khai báo **plugin ID** và **version**. Nó không chỉ rõ Maven group, artifact name hay đường dẫn JAR chứa implementation. Vì vậy Gradle phải xác định plugin đến từ đâu và ánh xạ ID sang module thực sự chứa mã plugin.

Ba khái niệm gắn liền với nhau:

1. **Plugin management**: cấu hình trung tâm `pluginManagement { ... }`, thông thường nằm đầu `settings.gradle(.kts)`, cho biết nơi tìm plugin, version mặc định và quy tắc resolution.
2. **Plugin marker artifact**: metadata/POM giúp ánh xạ `plugin ID + plugin version` sang **implementation module** khi giải quyết plugin từ Maven/Ivy plugin repository.
3. **Plugin resolution sources**: core plugins của Gradle, Gradle Plugin Portal, private Maven/Ivy repositories, included plugin builds, hoặc plugin classes đã có trên build classpath.

Nguyên tắc quan trọng: **plugin repository và dependency repository của ứng dụng là hai ngữ cảnh khác nhau**. Thêm `mavenCentral()` vào `Project.repositories` không tự khiến một external Gradle plugin tìm được; tương tự `gradlePluginPortal()` trong `pluginManagement` không tự cung cấp dependency cho `implementation(...)`.

Mục tiêu của bài: đọc và viết `pluginManagement` bằng Kotlin/Groovy DSL, hiểu marker GAV, tự làm một plugin Java 17 chạy được qua included build, publish plugin kèm marker ra local Maven repository, hiểu `useModule`/`useVersion` và chẩn đoán các lỗi plugin resolution.

## 2. Phân biệt core plugin, external plugin và local plugin

| Nhóm | Ví dụ | Cơ chế chính |
| --- | --- | --- |
| **Core plugin** | `java`, `java-library`, `application`, `maven-publish`, `java-gradle-plugin` | Có sẵn trong Gradle distribution, không cần download từ Plugin Portal khi apply. |
| **External/community plugin** | `com.gradleup.shadow` (plugin ngoài, tùy version) | Yêu cầu ID/version, plugin repositories và metadata/implementation hợp lệ. |
| **Private published plugin** | `com.acme.quality` (plugin minh họa) | Maven/Ivy nội bộ có marker và implementation, hoặc rule ánh xạ implementation. |
| **Included plugin build** | `com.example.greeting` tự viết trong `plugin-build` | `pluginManagement.includeBuild(...)` đưa build cung cấp plugin vào quá trình resolution. |
| **Plugin trên classpath khác** | buildscript/plugin từ build logic | Có thể apply theo ID/class nếu implementation đã ở classpath thích hợp; khác plugin DSL resolution thường. |

**Core plugin:**

```kotlin
plugins {
    id("java")
}
```

Groovy:

```groovy
plugins {
    id 'java'
}
```

Vì plugin `java` đi kèm Gradle, việc đoạn này hoạt động khi offline **không chứng minh** plugin repositories đã cấu hình đúng cho third-party plugins.

Một ví dụ plugin ngoài từ tài liệu Gradle:

```kotlin
plugins {
    id("com.gradleup.shadow") version "8.3.4"
}
```

Đây là minh họa riêng; hãy kiểm tra plugin version tương thích với Gradle Wrapper/JDK của repository trước khi sử dụng trong sản phẩm. Bài tập plugin nội bộ ở phần sau **không cần tải plugin này**.

## 3. Bốn loại repository dễ bị đánh đồng

| Nơi cấu hình | Dùng cho | Không phải |
| --- | --- | --- |
| `pluginManagement.repositories` trong Settings | Tìm plugin requests từ `plugins { id(...) version ... }`, plugin markers và implementation. | Repository cho `implementation("g:n:v")` của project. |
| `repositories` trong Project hoặc `dependencyResolutionManagement.repositories` trong Settings | External dependencies của project như `implementation`, `testImplementation`. | Nguồn mặc định cho plugin DSL. |
| `buildscript.repositories` | Dependency `classpath(...)` của chính build script; gặp trong legacy `apply(plugin=...)`. | Repository runtime/compile của mã ứng dụng. |
| `publishing.repositories` | Đích **upload** artifact/plugin/marker khi publish. | Nơi download plugin hay project dependency. |

Ví dụ Kotlin có hai ngữ cảnh riêng:

**`settings.gradle.kts`:**

```kotlin
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

rootProject.name = "example"
```

**`build.gradle.kts`:**

```kotlin
plugins {
    id("java")
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

`mavenCentral()` giải quyết Commons Lang3, còn `gradlePluginPortal()` dành cho plugin request ngoài. Dù cùng một Maven server có thể chứa cả plugin marker lẫn thư viện, Gradle **không tự gộp** các lists này.

Trong `build.gradle.kts`, `plugins` còn có cú pháp ràng buộc: nó phải ở đầu phần khai báo project, không thể tùy tiện đặt sau logic arbitrary. Việc đặt `repositories` của project trước `plugins` thường sai với constrained plugins block của Kotlin DSL.

## 4. pluginManagement phải xuất hiện sớm trong Settings

Với build thông thường, viết `pluginManagement` **đầu tiên** trong `settings.gradle.kts` hoặc `settings.gradle`. Gradle phải biết plugin repositories/rules trước khi xử lý các plugin requests trong Settings và Project scripts.

**Kotlin:**

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }

    plugins {
        // Plugin versions mặc định nếu cần.
    }

    resolutionStrategy {
        // Quy tắc cho từng request.
    }
}

rootProject.name = "plugin-management-demo"
include(":app")
```

**Groovy:**

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }

    plugins {
        // Plugin versions mặc định nếu cần.
    }

    resolutionStrategy {
        // Resolution rules.
    }
}

rootProject.name = 'plugin-management-demo'
include 'app'
```

`pluginManagement` là **ngữ cảnh của Settings**, không phải một khối `repositories`/`dependencies` được phép đặt tùy ý vào từng Project. Với các included builds hoặc `buildSrc`, mỗi build có Settings riêng và có thể cần plugin management của chính nó.

**Settings plugins block khác Project plugins block:** `plugins { ... }` trong Settings áp dụng `Plugin<Settings>` phù hợp, còn trong `build.gradle(.kts)` áp dụng `Plugin<Project>`. Một plugin chỉ hỗ trợ Project không tự chuyển sang Settings chỉ vì bạn đổi vị trí đặt `plugins`.

## 5. Custom plugin repositories và Plugin Portal mặc định

Gradle mặc định tìm plugins DSL ở **Gradle Plugin Portal** khi không có cấu hình custom thích hợp. Nhưng khi bạn **khai báo `pluginManagement.repositories`**, đừng mặc định Plugin Portal vẫn được tự động nối thêm. Nếu muốn dùng nó, thêm `gradlePluginPortal()` rõ ràng.

Kotlin Settings:

```kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-plugins")
        }
        gradlePluginPortal()
    }
}
```

Groovy:

```groovy
pluginManagement {
    repositories {
        maven {
            url = uri('https://repo.example.org/gradle-plugins')
        }
        gradlePluginPortal()
    }
}
```

`https://repo.example.org/gradle-plugins` là URL **giả định**, không phải repository thật. Cấu hình thường ưu tiên kho nội bộ rồi mới tới Plugin Portal. Plugin version/ID phải thực sự tồn tại và metadata phải đúng; thêm repo không thể tạo artifact chưa publish.

Có thể cấu hình Maven/Ivy hoặc file-based repo:

```kotlin
pluginManagement {
    repositories {
        maven { url = uri("./local-plugin-repo") }
        ivy { url = uri("./local-ivy-repo") }
        gradlePluginPortal()
    }
}
```

Trong settings, path tương đối ở đây phải trỏ đúng nơi kho Maven/Ivy với layout metadata thực. Không thể bỏ một JAR tùy ý vào một thư mục và coi nó là plugin repository hoàn chỉnh.

### 5.1. Thứ tự, nội dung và bảo mật

- Repository thứ tự cao hơn thường được kiểm tra trước; Gradle có quy tắc metadata/nguồn artifact cụ thể. Không đoán kho tải thực tế chỉ từ việc build có cache.
- Có thể dùng content filters, `exclusiveContent` hoặc mirror nội bộ nếu cần kiểm soát nguồn group/module.
- Hạn chế `mavenLocal()` trong các build cần CI tái lập: máy dev có thể có artifact khác với máy CI.
- Dùng HTTPS và credentials API/Gradle properties/CI secrets; không commit token vào `settings.gradle.kts`.
- Chỉ áp dụng plugin từ nguồn được phê duyệt: code plugin chạy trong Gradle process với quyền của người dùng/CI.
- Không thêm mọi kho công khai vào mọi Settings để “fix” nhanh một lỗi not-found; hãy xác định plugin ID, marker và nơi publisher thật.

## 6. Plugin marker: ID và Maven module là hai thứ khác nhau

Khi project viết:

```kotlin
plugins {
    id("com.example.greeting") version "1.0.0"
}
```

Gradle dùng cơ chế marker mặc định cho external plugins trên Maven/Ivy. **Plugin marker artifact** có GAV:

```text
<plugin-id>:<plugin-id>.gradle.plugin:<plugin-version>
```

Với ví dụ:

```text
group   = com.example.greeting
name    = com.example.greeting.gradle.plugin
version = 1.0.0
```

Tọa độ hoàn chỉnh:

```text
com.example.greeting:com.example.greeting.gradle.plugin:1.0.0
```

**Marker thường là POM/metadata**, chứa dependency trỏ đến module thực sự có JAR implementation. Giả sử producer được xuất bản thành:

```text
com.example.build:greeting-gradle-plugin:1.0.0
```

thì plugin resolution về cơ bản đi qua:

```text
plugins { id("com.example.greeting") version "1.0.0" }
                     |
                     v
            pluginManagement.repositories
                     |
                     v
     com.example.greeting:
     com.example.greeting.gradle.plugin:1.0.0
             (marker metadata)
                     |
                dependency
                     v
     com.example.build:
     greeting-gradle-plugin:1.0.0
            (implementation JAR)
                     |
                     v
         Plugin descriptor + class
                     |
                     v
              Plugin.apply(...)
```

Quan trọng:

1. **Plugin marker không phải implementation JAR**. Marker chỉ cho Gradle biết module nào mang plugin code.
2. Plugin ID không phải lúc nào cũng trùng Maven implementation `group:name`.
3. Plugin marker và implementation phải cùng được resolve từ plugin repositories có metadata/credentials phù hợp.
4. Nếu kho có JAR implementation nhưng **không có marker**, `plugins { id(...) version ... }` có thể báo `Plugin ... was not found` dù implementation module tồn tại.
5. Có hai giải pháp: **publish marker đúng chuẩn**, hoặc ánh xạ request sang module bằng `pluginManagement.resolutionStrategy.useModule(...)`.
6. Core plugin hoặc plugin do `pluginManagement.includeBuild(...)` cung cấp không cần marker Maven để apply theo cơ chế riêng của chúng.

### 6.1. Hình dung cấu trúc file trong Maven repository

Marker POM theo Maven layout chuẩn:

```text
com/example/greeting/
  com.example.greeting.gradle.plugin/
    1.0.0/
      com.example.greeting.gradle.plugin-1.0.0.pom
```

Implementation JAR/POM ở cây khác:

```text
com/example/build/
  greeting-gradle-plugin/
    1.0.0/
      greeting-gradle-plugin-1.0.0.jar
      greeting-gradle-plugin-1.0.0.pom
```

Không nhầm file JAR implementation với file POM marker. Khi chẩn đoán mirror riêng, cần đối chiếu **cả hai publication**; việc chỉ tìm thấy JAR chưa đủ xác nhận plugin DSL hoạt động.

### 6.2. Ai tạo marker?

`java-gradle-plugin` kết hợp với `maven-publish` thường tự cấu hình:

- Publication chính `pluginMaven` cho implementation.
- Marker publications, một cho mỗi plugin đăng ký qua `gradlePlugin.plugins`; tên kiểu `greetingPluginMarkerMaven` khi declaration name là `greeting`.

Plugin development plugin cũng sinh descriptor để Gradle biết Plugin ID/implementation class. Nếu tắt automated publishing hoặc viết lại publication thủ công, hãy xác minh marker còn được tạo đầy đủ.

## 7. Không phải mọi nguồn plugin đi qua marker theo cùng một đường

Các trường hợp cần phân biệt:

| Nguồn plugin | Ví dụ | Cần tải plugin marker trên Maven? |
| --- | --- | --- |
| Core plugin của Gradle | `id("java")` | Không. |
| External plugin qua plugin repository mặc định | `id("x.y") version "1.0"` | Thường có marker, trừ khi resolution rule khác. |
| Local plugin build do Settings include | `pluginManagement.includeBuild("plugin-build")` | Không cần Maven marker để dùng plugin local. |
| Plugin đã có trên buildscript classpath | Legacy `buildscript.classpath` + `apply(plugin=...)` | Không phải cơ chế marker mặc định của plugins DSL. |
| Private plugin chỉ có implementation module | `useModule("g:n:v")` | Bỏ mapping marker mặc định, nhưng phải tải được implementation. |

Đây là **mô hình khái niệm**, không phải thứ tự tuyến tính bắt buộc cho mọi Gradle version. Gradle cũng kiểm tra plugin request, version, classpath, included builds và đúng plugin type. Khi có lỗi, hãy xác định **ngữ cảnh request** và **nguồn plugin mà build thực tế đã cấu hình**.

## 8. Đặt version mặc định qua pluginManagement.plugins

Thay vì lặp plugin version ở hàng chục modules, có thể khai báo version trong Settings.

**`gradle.properties`:**

```properties
greetingPluginVersion=1.0.0
```

**`settings.gradle.kts`:**

```kotlin
pluginManagement {
    val pluginVersion =
        providers.gradleProperty("greetingPluginVersion").get()

    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-plugins")
        }
        gradlePluginPortal()
    }

    plugins {
        id("com.example.greeting") version pluginVersion
    }
}
```

**`app/build.gradle.kts`:**

```kotlin
plugins {
    id("com.example.greeting")
}
```

Với Groovy Settings:

```groovy
pluginManagement {
    def pluginVersion =
        providers.gradleProperty('greetingPluginVersion').get()

    repositories {
        maven {
            url = uri('https://repo.example.org/gradle-plugins')
        }
        gradlePluginPortal()
    }

    plugins {
        id 'com.example.greeting' version pluginVersion
    }
}
```

**`app/build.gradle`:**

```groovy
plugins {
    id 'com.example.greeting'
}
```

Ở đây plugin ID/version **chỉ là ví dụ về một plugin đã publish**, repository giả định nên không thể chạy ngay khi chưa xuất bản plugin. `pluginManagement.plugins` định nghĩa version mặc định, **không tự apply plugin** vào mọi project. Nếu property không tồn tại, `.get()` có thể báo lỗi ngay khi xử lý Settings.

So sánh: root Project cũng có thể dùng `plugins { id("x.y") version "1.0" apply false }`, rồi module dùng `id("x.y")` không version. Nhưng đây là cách chia sẻ classpath/plugin version từ root, không đồng nghĩa `pluginManagement.plugins` và không thay thế việc cấu hình repository.

## 9. apply false và version catalog cho plugin ID/version

### 9.1. Dùng apply false ở root

**Root `build.gradle.kts`:**

```kotlin
plugins {
    id("com.example.greeting") version "1.0.0" apply false
}
```

**`app/build.gradle.kts`:**

```kotlin
plugins {
    id("com.example.greeting")
}
```

`apply false` giúp root **không áp dụng** plugin vào root Project, dù plugin đã được yêu cầu trong phạm vi build. Module con có thể apply plugin phù hợp. Đây là **đoạn minh họa bổ sung**, dùng khi plugin đã publish và có repository đúng; không cần kết hợp với demo included build ở mục 11.

Groovy:

```groovy
// Root build.gradle
plugins {
    id 'com.example.greeting' version '1.0.0' apply false
}
```

```groovy
// app/build.gradle
plugins {
    id 'com.example.greeting'
}
```

### 9.2. Alias từ version catalog

**`gradle/libs.versions.toml`:**

```toml
[versions]
greetingPlugin = "1.0.0"

[plugins]
greeting = { id = "com.example.greeting", version.ref = "greetingPlugin" }
```

Kotlin Project build:

```kotlin
plugins {
    alias(libs.plugins.greeting)
}
```

Groovy Project build:

```groovy
plugins {
    alias(libs.plugins.greeting)
}
```

Catalog chỉ quản lý ID/version/alias, **không chứa repository**. Gradle vẫn dùng `pluginManagement.repositories` hoặc một nguồn plugin hợp lệ khác. `alias(libs.plugins...)` ở Project build script không áp dụng nguyên xi cho `plugins` block trong Settings hoặc precompiled script plugin do khác thời điểm/catalog/classpath.

## 10. pluginManagement.resolutionStrategy — sửa plugin request

`pluginManagement.resolutionStrategy.eachPlugin` can thiệp vào từng request. Hai thao tác khác nhau:

- `useVersion("...")`: thay version sẽ dùng cho plugin ID, nhưng vẫn cần nguồn plugin/marker phù hợp.
- `useModule("group:name:version")`: chỉ định **module implementation**, bỏ bước ánh xạ mặc định từ plugin ID sang marker coordinates; hữu ích với private/legacy plugin không có marker.

### 10.1. useVersion

**Kotlin Settings:**

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }

    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "com.acme.quality") {
                useVersion("2.1.0")
            }
        }
    }
}
```

**Groovy Settings:**

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }

    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == 'com.acme.quality') {
                useVersion('2.1.0')
            }
        }
    }
}
```

Plugin `com.acme.quality` là ví dụ giả định. Nếu plugin ID/marker không có trong Plugin Portal, `useVersion` **không tự sửa** lỗi tìm plugin.

### 10.2. useModule với plugin implementation nội bộ

Giả sử kho Maven nội bộ chứa module:

```text
com.acme.build:quality-gradle-plugin:2.1.0
```

nhưng chưa publish marker cho `com.acme.quality`. Trong Settings:

**Kotlin:**

```kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-plugins")
        }
    }

    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "com.acme.quality") {
                useModule("com.acme.build:quality-gradle-plugin:2.1.0")
            }
        }
    }
}
```

**Groovy:**

```groovy
pluginManagement {
    repositories {
        maven {
            url = uri('https://repo.example.org/gradle-plugins')
        }
    }

    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == 'com.acme.quality') {
                useModule('com.acme.build:quality-gradle-plugin:2.1.0')
            }
        }
    }
}
```

Project có thể khai báo request:

```kotlin
plugins {
    id("com.acme.quality") version "2.1.0"
}
```

**Giải thích giới hạn:**

1. Gradle resolve module `com.acme.build:quality-gradle-plugin:2.1.0` thay cho marker mặc định.
2. Kho phải chứa module và dependencies của implementation.
3. JAR phải thực sự chứa plugin ID descriptor/code phù hợp; `useModule` không biến JAR Java thông thường thành Gradle plugin.
4. Version của mapping ở đây cố định có chủ đích; nếu muốn bám request, bạn có thể đọc `requested.version` và kiểm tra trường hợp không có version.
5. Mapping này chỉ thuộc **plugin resolution**, không điều chỉnh module dependencies của `implementation(...)`.

Nếu kiểm soát publisher, **ưu tiên xuất bản marker chuẩn** thay vì dùng mapping đặc biệt cho mọi plugin.

## 11. Bài thực hành A — plugin Java 17 local qua includeBuild

Bài tập này là **một build chạy được**, không cần external Gradle plugins hoặc Maven server. Plugin viết bằng Java, Gradle biên dịch plugin nhờ core plugin `java-gradle-plugin`, rồi Project `:app` áp dụng plugin bằng ID.

### 11.1. Cấu trúc

```text
plugin-resolution-lab/
├── settings.gradle.kts
├── plugin-build/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/java/demo/gradle/GreetingPlugin.java
└── app/
    └── build.gradle.kts
```

**Main `settings.gradle.kts`:**

```kotlin
pluginManagement {
    includeBuild("plugin-build")
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "plugin-resolution-lab"
include(":app")
```

`includeBuild("plugin-build")` nằm trong `pluginManagement`, đăng ký included build là **nguồn cung cấp plugin** cho plugins DSL.

**`plugin-build/settings.gradle.kts`:**

```kotlin
rootProject.name = "greeting-gradle-plugin"
```

**`plugin-build/build.gradle.kts`:**

```kotlin
plugins {
    `java-gradle-plugin`
}

group = "com.example.build"
version = "1.0.0"

gradlePlugin {
    plugins {
        create("greeting") {
            id = "com.example.greeting"
            implementationClass = "demo.gradle.GreetingPlugin"
        }
    }
}
```

`java-gradle-plugin` thiết lập mã nguồn Gradle plugin, Gradle API classpath và descriptor. Plugin ID `com.example.greeting` khác tọa độ module implementation của project `greeting-gradle-plugin`; đây là điều chúng ta muốn quan sát.

**`plugin-build/src/main/java/demo/gradle/GreetingPlugin.java`:**

```java
package demo.gradle;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class GreetingPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getTasks().register("greet", task -> {
            task.setGroup("demo");
            task.setDescription("Print a greeting from a local plugin");
            task.doLast(ignored ->
                System.out.println("Hello from custom Gradle plugin")
            );
        });
    }
}
```

Đây là class Java 17 triển khai `Plugin<Project>`, **không** phải chương trình Java độc lập có `main`. Nó được Gradle biên dịch thành plugin và gọi `apply` ở Project. Do đó không chạy bằng `java demo.gradle.GreetingPlugin`; để kiểm tra, hãy dùng Gradle task.

**`app/build.gradle.kts`:**

```kotlin
plugins {
    id("com.example.greeting")
}
```

Vì plugin ID đã có ở included plugin build, app không cần viết version trong request. Gradle tìm plugin registration từ included build và cung cấp mã plugin mà không cần marker Maven.

### 11.2. Chạy và stdout chính xác

Từ `plugin-resolution-lab` có Gradle Wrapper tương thích với JDK 17:

```bash
./gradlew -q :app:greet
```

Kết quả do task in:

```text
Hello from custom Gradle plugin
```

Có thể kiểm tra task đã được đăng ký:

```bash
./gradlew :app:tasks --all
./gradlew :app:greet --info
```

`--info` cho thêm log Gradle phụ thuộc version/cache; dòng output do action in vẫn cố định. Windows dùng `gradlew.bat`. Nếu project mới chưa có Gradle Wrapper nhưng máy đã cài Gradle, chạy `gradle wrapper` ở root để tạo wrapper, rồi dùng wrapper.

### 11.3. Cùng demo dưới Groovy DSL

Dùng **`settings.gradle`** thay cho Settings Kotlin:

```groovy
pluginManagement {
    includeBuild('plugin-build')
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'plugin-resolution-lab'
include 'app'
```

`plugin-build/settings.gradle`:

```groovy
rootProject.name = 'greeting-gradle-plugin'
```

`plugin-build/build.gradle`:

```groovy
plugins {
    id 'java-gradle-plugin'
}

group = 'com.example.build'
version = '1.0.0'

gradlePlugin {
    plugins {
        greeting {
            id = 'com.example.greeting'
            implementationClass = 'demo.gradle.GreetingPlugin'
        }
    }
}
```

`app/build.gradle`:

```groovy
plugins {
    id 'com.example.greeting'
}
```

Java class `GreetingPlugin.java` giữ nguyên. Dùng **một** DSL cho mỗi script; không giữ cả `settings.gradle` và `settings.gradle.kts` rồi dựa vào Gradle tự chọn bản nào. Kết quả `:app:greet` vẫn là `Hello from custom Gradle plugin`.

### 11.4. Tại sao không cần plugin marker trong demo A?

`pluginManagement.includeBuild("plugin-build")` cho Gradle biết build này có plugin registrations. Nó có thể biên dịch plugin code từ source và nạp implementation trực tiếp. Plugin này **không cần xuất bản lên Maven repository**, không cần marker POM để cung cấp ID `com.example.greeting` trong composite. Nhưng nếu một Project ở repository độc lập muốn tải plugin từ Maven, ta cần mô hình published plugin của mục 12.

## 12. Bài thực hành B — publish plugin marker và implementation vào local Maven

Tiếp tục từ demo A. Thay vì dùng included build cho consumer, chúng ta xuất bản plugin vào **file-based Maven repository**, rồi tạo consumer build khác chỉ biết plugin ID/version và repository. Như vậy hai phần đều có thể chạy mà không cần Maven server hay thư viện bên ngoài (ngoài Gradle distribution/JDK phù hợp).

### 12.1. Thêm maven-publish vào plugin publisher

Thay toàn bộ `plugin-build/build.gradle.kts` bằng:

```kotlin
plugins {
    `java-gradle-plugin`
    `maven-publish`
}

group = "com.example.build"
version = "1.0.0"

gradlePlugin {
    plugins {
        create("greeting") {
            id = "com.example.greeting"
            implementationClass = "demo.gradle.GreetingPlugin"
        }
    }
}

publishing {
    repositories {
        maven {
            url = uri(layout.buildDirectory.dir("plugin-repo"))
        }
    }
}
```

Publisher Groovy tương đương:

```groovy
plugins {
    id 'java-gradle-plugin'
    id 'maven-publish'
}

group = 'com.example.build'
version = '1.0.0'

gradlePlugin {
    plugins {
        greeting {
            id = 'com.example.greeting'
            implementationClass = 'demo.gradle.GreetingPlugin'
        }
    }
}

publishing {
    repositories {
        maven {
            url = layout.buildDirectory.dir('plugin-repo')
        }
    }
}
```

`publishing.repositories` là **đích xuất bản**, không phải repository để consumer resolve plugin. `java-gradle-plugin` kết hợp `maven-publish` sẽ tạo publication implementation và marker. Không cần viết file marker POM bằng tay.

Từ root có Wrapper:

```bash
./gradlew -p plugin-build publish
```

Repository được tạo trong:

```text
plugin-build/build/plugin-repo/
```

Mong đợi metadata ở hai tọa độ:

```text
Marker:
com.example.greeting:com.example.greeting.gradle.plugin:1.0.0

Implementation:
com.example.build:greeting-gradle-plugin:1.0.0
```

Artifact thực tế có thể thêm Gradle module metadata và checksums. Tên `greeting-gradle-plugin` trong module GAV dựa trên tên project của publisher ở `plugin-build/settings.gradle.kts`, nếu không override artifactId.

### 12.2. Tạo consumer riêng không dùng includeBuild

Cấu trúc bổ sung (bên cạnh publisher):

```text
plugin-resolution-lab/
├── plugin-build/
│   └── build/plugin-repo/...
└── consumer-marker/
    ├── settings.gradle.kts
    └── app/
        └── build.gradle.kts
```

**`consumer-marker/settings.gradle.kts`:**

```kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("../plugin-build/build/plugin-repo")
        }
    }
}

rootProject.name = "consumer-marker"
include(":app")
```

**`consumer-marker/app/build.gradle.kts`:**

```kotlin
plugins {
    id("com.example.greeting") version "1.0.0"
}
```

Đây là một **build độc lập**. Nó không có `pluginManagement.includeBuild("plugin-build")`, nên plugin request phải được resolve qua marker trong Maven repository.

Chạy từ root của repository lab sau khi đã publish:

```bash
./gradlew -p consumer-marker -q :app:greet
```

Stdout:

```text
Hello from custom Gradle plugin
```

Dạng Groovy của consumer:

```groovy
// consumer-marker/settings.gradle
pluginManagement {
    repositories {
        maven {
            url = uri('../plugin-build/build/plugin-repo')
        }
    }
}

rootProject.name = 'consumer-marker'
include 'app'
```

```groovy
// consumer-marker/app/build.gradle
plugins {
    id 'com.example.greeting' version '1.0.0'
}
```

Nếu chưa publish đủ marker/implementation hoặc path Settings trỏ sai, consumer sẽ lỗi. Nhờ vậy bài demo giúp thấy **sự khác nhau giữa local included plugin và published marker resolution**.

### 12.3. Marker và implementation là hai publications

`java-gradle-plugin` + `maven-publish` thường tạo:

- `pluginMaven`: publication cho implementation JAR/POM.
- `greetingPluginMarkerMaven`: marker POM cho ID `com.example.greeting`.

Ví dụ đoạn XML minh họa **quan hệ** (không phải file POM đầy đủ để tự publish):

```xml
<project>
  <groupId>com.example.greeting</groupId>
  <artifactId>com.example.greeting.gradle.plugin</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>com.example.build</groupId>
      <artifactId>greeting-gradle-plugin</artifactId>
      <version>1.0.0</version>
    </dependency>
  </dependencies>
</project>
```

POM Maven thật còn có schema, modelVersion và metadata hợp lệ; ở đây chỉ cần hiểu marker chỉ dẫn Gradle đến artifact implementation.

| Included build A | Published plugin B |
| --- | --- |
| `pluginManagement.includeBuild("plugin-build")` | `pluginManagement.repositories.maven` |
| Plugin request `id("com.example.greeting")` không version | `id("com.example.greeting") version "1.0.0"` |
| Gradle build/plugin source trực tiếp | Gradle tìm marker POM và JAR implementation |
| Không cần publish | Phải publish đủ implementation và marker |
| Phù hợp monorepo/convention plugin local | Phù hợp nhiều Git repos/builds độc lập |

## 13. Khi dùng buildSrc hoặc precompiled script plugin

`buildSrc` và included `build-logic` là những build chứa logic tùy biến. Chúng **không tự kế thừa** tất cả plugin repositories/settings của main build.

Với precompiled script plugin, external plugin muốn áp dụng trong `plugins` block của script đó phải có **implementation JAR trên build-logic classpath**. Tài liệu Gradle lưu ý rằng cú pháp `version "..."` và `apply false` trong precompiled script plugin `plugins` block **không hỗ trợ như project build script thông thường**.

Ví dụ minh họa ý nghĩa (không phải plugin hoàn chỉnh; tọa độ chỉ giả định):

**`build-logic/build.gradle.kts`:**

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}

dependencies {
    implementation("com.acme.build:quality-gradle-plugin:2.1.0")
}
```

**`build-logic/src/main/kotlin/quality-conventions.gradle.kts`:**

```kotlin
plugins {
    id("com.acme.quality")
}
```

Cơ chế này khác việc `pluginManagement.repositories` tìm marker từ `plugins` request thông thường trong Project. Build logic phải tự resolve module implementation theo repositories của nó; plugin ID phải tồn tại trong metadata.

**Không giả định `alias(libs.plugins.somePlugin)` được hỗ trợ ở precompiled script plugin `plugins` block** như ở `build.gradle.kts` của một Project. Khi cần áp plugin ngoài, khai báo plugin implementation trên build-logic classpath rồi apply bằng plugin ID phù hợp.

## 14. Legacy buildscript.repositories + apply(plugin)

Build Gradle cũ có thể dùng:

**Groovy:**

```groovy
buildscript {
    repositories {
        maven {
            url = uri('https://repo.example.org/gradle-plugins')
        }
    }
    dependencies {
        classpath 'com.acme.build:quality-gradle-plugin:2.1.0'
    }
}

apply plugin: 'com.acme.quality'
```

**Kotlin:**

```kotlin
buildscript {
    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-plugins")
        }
    }
    dependencies {
        classpath("com.acme.build:quality-gradle-plugin:2.1.0")
    }
}

apply(plugin = "com.acme.quality")
```

Đây là **buildscript classpath resolution**. Khi implementation có trên classpath đúng cách, Gradle có thể apply plugin bằng ID mà không cần marker POM của `plugins` DSL theo cơ chế mặc định.

Tọa độ `com.acme.build:quality-gradle-plugin:2.1.0` và repo.example.org chỉ là ví dụ; phải có artifact thực mới chạy được. Không dùng `buildscript.repositories` để “chữa” lỗi `plugins { id(...) version ... }` một cách không có cơ sở. Nếu plugin đã hỗ trợ DSL hiện đại, ưu tiên `plugins` + `pluginManagement`.

## 15. Chẩn đoán lỗi Plugin ... was not found

Thông báo thường gặp:

```text
Plugin [id: 'com.acme.quality', version: '2.1.0'] was not found
```

Đây là **thông báo minh họa**; chi tiết lỗi thực tế phụ thuộc Gradle version và các nguồn resolution đã được kiểm tra.

### 15.1. Trình tự điều tra

1. **Đúng plugin ID không?** Publisher phải đăng ký đúng ID; Maven group/name implementation có thể khác.
2. **Version có tồn tại không?** Đừng dùng version catalog hoặc `useVersion` với một version chưa publish.
3. **Nguồn plugin nằm ở đâu?** Plugin Portal, internal Maven/Ivy, included plugin build hay classpath?
4. **`pluginManagement.repositories` có chứa nguồn đó không?** Đừng nhìn nhầm `Project.repositories`.
5. **Marker POM có tồn tại?** Kiểm tra GAV `id:id.gradle.plugin:version`, không chỉ implementation JAR.
6. **Implementation/module dependency có tải được không?** Marker POM có thể tồn tại nhưng trỏ vào JAR/phiên bản chưa publish.
7. **Plugin descriptor/class đã đúng chưa?** Nếu resolve được nhưng apply lỗi, kiểm tra ID, implementation class, Gradle API/JDK compatibility.
8. **Cache, proxy, credentials, offline mode?** Cache dev có thể làm plugin chạy dù CI fresh không truy cập được.
9. **Bị trùng classpath/version?** Plugin đã có trên classpath có thể không chấp nhận thêm một version request khác.

### 15.2. Những lỗi tiêu biểu

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Có `mavenCentral()` trong project nhưng plugin ngoài not found | Project repository không phải plugin repository. | Kiểm tra `settings.pluginManagement.repositories`. |
| Public plugin biến mất khi thêm kho private | Không khai báo `gradlePluginPortal()` trong custom plugin repo list. | Thêm portal nếu muốn tìm public plugins. |
| Implementation JAR có nhưng marker thiếu | Chưa publish marker hoặc publisher không bật publication phù hợp. | `java-gradle-plugin` + `maven-publish` hoặc `useModule`. |
| Marker POM có nhưng JAR không tải | POM marker trỏ module/version sai hoặc repo/quyền thiếu. | Kiểm tra POM, implementation GAV, authentication. |
| `useVersion` không làm plugin xuất hiện | Version override không tạo repository/marker. | Kiểm tra nguồn thực, hoặc mapping `useModule`. |
| Lỗi `Plugin already on classpath with an unknown version` | Plugin classpath được cung cấp từ nơi khác rồi yêu cầu version không phù hợp. | Rà root apply false, buildscript và convention plugins. |
| Core `java` chạy offline nhưng plugin ngoài fail | Core plugin đi kèm Gradle, external plugin cần tải. | Kiểm tra portal/private repo và cache. |
| Included build không cung cấp plugin ID | Sai `includeBuild` path, chưa đăng ký plugin ID hoặc implementation class sai. | Kiểm tra `pluginManagement.includeBuild` và `gradlePlugin.plugins`. |
| `buildSrc` dùng được còn main build không, hoặc ngược lại | Hai build có Settings/classpath khác. | Cấu hình plugin resolution phù hợp tại từng build. |
| Plugin được tải nhưng task không xuất hiện | Plugin có điều kiện apply/plugin ID khác hoặc task name khác. | Kiểm tra `tasks --all`, plugin docs và code `apply`. |
| 401/403 khi CI tải plugin | Chưa có credentials hoặc không đủ quyền. | Dùng CI secrets và quyền đọc repo; không commit token. |
| Plugin lỗi JVM/Gradle API | Plugin release không phù hợp Gradle Wrapper/JDK. | Đối chiếu compatibility/release notes và stacktrace. |
| `--offline` lỗi nhưng online được | Artifact chưa có trong cache. | Cho môi trường được phép truy cập repository để populate cache. |

### 15.3. Công cụ dòng lệnh

Với demo A/B:

```bash
./gradlew --version
./gradlew :app:tasks --all
./gradlew -q :app:greet
./gradlew :app:greet --info
./gradlew :app:greet --stacktrace

./gradlew -p plugin-build publish
./gradlew -p consumer-marker :app:greet --info
```

`--info` cho thêm logs, `--stacktrace` giúp khi plugin classloading/apply lỗi. `--debug` chỉ nên dùng khi cần vì logs có thể chứa URL nội bộ/metadata nhạy cảm. `--refresh-dependencies` có thể làm Gradle kiểm tra lại metadata/cache, **không tạo ra marker/JAR chưa publish**. `--offline` chỉ cho phép dùng dữ liệu đã cache.

`dependencyInsight` trên `runtimeClasspath` của Java project phục vụ **module dependency graph**, không phải công cụ chuẩn duy nhất để xác nhận nơi plugin DSL đã tải marker. Khi điều tra plugin repository, dùng Settings, POM/marker GAV, log của Gradle và dữ liệu publisher.

## 16. Checklist dùng plugin an toàn, tái lập

- **Chốt phiên bản plugin** qua Settings `pluginManagement.plugins`, root `apply false`, project `plugins` hoặc alias catalog; tránh quản trị trùng nhiều nơi.
- **Kiểm soát plugin repositories**, nội bộ mirror/Plugin Portal theo policy, không thêm kho không tin cậy.
- **Không lộ secrets** trong script; dùng Gradle credentials/Gradle properties/CI secret store.
- **Dùng HTTPS** khi phù hợp, kiểm soát token, review nguồn code/plugin publisher.
- **Kiểm tra Gradle Wrapper và Java compatibility** của plugin, đặc biệt khi nâng major version.
- **Không nhầm nơi publish và nơi resolve**; publisher `publishing.repositories`, consumer `pluginManagement.repositories`.
- **Đảm bảo marker và implementation được publish cùng version**, và có test apply plugin từ repository thật.
- **Không dựa vào cache cá nhân** để kiểm chứng permission trong CI; nên có bài kiểm tra từ môi trường sạch có kiểm soát.
- **Phân biệt scope** main build, `buildSrc`, included builds; một Settings không tự điều khiển mọi build khác.
- **Dùng `includeBuild` cho convention plugin nội bộ** khi cùng source tree và vòng đời phát triển; dùng publication marker khi chia sẻ giữa repositories độc lập.
- **Không áp một plugin chỉ vì nó có tên quen thuộc**: Gradle plugin được chạy như code build logic với quyền truy cập môi trường build.

## 17. Bảng quyết định nhanh

| Nhu cầu | Cơ chế |
| --- | --- |
| Áp dụng core Java plugin | `plugins { id("java") }`, không cần external plugin repo. |
| External plugin bằng ID/version | `plugins { id("x.y") version "1.0" }` với nguồn plugin phù hợp. |
| Nơi tìm plugin ngoài | `settings.pluginManagement.repositories`. |
| Muốn giữ Plugin Portal khi đã thêm custom repos | Viết `gradlePluginPortal()` rõ ràng. |
| Quản lý plugin version cho nhiều modules | `pluginManagement.plugins`, alias catalog hoặc root apply false. |
| Đổi version request | `resolutionStrategy.eachPlugin { useVersion(...) }`. |
| Không có plugin marker nhưng có implementation module | `resolutionStrategy.eachPlugin { useModule("g:n:v") }` hoặc publish marker. |
| Plugin marker GAV | `plugin.id:plugin.id.gradle.plugin:plugin.version`. |
| Tạo marker publications tự động | `java-gradle-plugin` + `maven-publish` + `gradlePlugin.plugins`. |
| Plugin local trong monorepo | `pluginManagement { includeBuild("plugin-build") }`. |
| Legacy classpath plugin | `buildscript.repositories` + `classpath(...)` + `apply(plugin=...)`. |
| Thư viện Java của project | `Project.repositories` / `dependencyResolutionManagement.repositories`, không phải plugin repos. |
| Đích upload plugin | `publishing.repositories`. |
| Chẩn đoán plugin not found | Kiểm tra ID/version, Settings, marker, implementation, repo/quyền/cache và logs. |

**Kết luận:** `pluginManagement` giải quyết **plugin requests**, còn **plugin marker** nối ID/version với implementation module khi tìm plugin trên Maven/Ivy. Core plugins và plugin từ included build không cần marker Maven; private published plugins cần marker hoặc mapping khác. Nắm vững ranh giới plugin repositories, dependency repositories, legacy classpath repositories và publishing destinations giúp build đáng tin cậy, dễ chẩn đoán và an toàn hơn.

### Tài liệu Gradle chính thức

- [Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html) — plugin DSL, pluginManagement, versions, repositories, resolution rules và marker.
- [Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html) — phát triển plugin, marker publication, Maven/Ivy publishing.
- [Precompiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html) — buildSrc/build-logic và plugin classpath.
- [Declaring Plugin Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_adv.html) — plugin repositories khác project dependency repositories.
- [Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html) — Settings/plugin resolution và Project configuration.
- [PluginManagementSpec API](https://docs.gradle.org/current/javadoc/org/gradle/plugin/management/PluginManagementSpec.html) — pluginManagement repositories, plugins, resolutionStrategy, includeBuild.
