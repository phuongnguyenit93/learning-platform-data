# Phân biệt phạm vi `plugins`, `buildscript` và phần thân script trong Gradle Kotlin DSL

## 1. Vì sao ba phạm vi này dễ nhầm lẫn?

Một file `build.gradle.kts` trông như một chương trình Kotlin thống nhất, nhưng Gradle xử lý một số phần của nó ở **các thời điểm và ngữ cảnh khác nhau**. Đặc biệt, ba phạm vi thường bị nhầm là:

1. **`plugins { ... }`** — khai báo những Gradle plugin cần **resolve và apply** cho đối tượng đang cấu hình (thông thường là `Project`).
2. **`buildscript { ... }`** — cấu hình **classpath của chính build script**, bao gồm repository và thư viện/plugin implementation mà mã build script muốn sử dụng. Đây là cơ chế cũ cho plugin và đôi khi vẫn cần cho thư viện hỗ trợ đặc biệt.
3. **Phần thân script** — các câu lệnh Kotlin DSL cấu hình `Project`: `repositories`, `dependencies`, `java`, `tasks`, `group`, `version` và logic tùy chỉnh. Nó được xử lý trong **configuration phase**, chứ không phải là code Java/Kotlin của ứng dụng.

Sự khác biệt quyết định: **classpath chứa code để chạy Gradle build** không phải **classpath chứa thư viện biên dịch/chạy ứng dụng**. Thêm một JAR vào `buildscript.dependencies.classpath` không tự khiến ứng dụng có JAR đó; thêm một JAR vào `implementation` cũng không tự cho phép script import lớp của JAR trong configuration.

Mục tiêu bài học là hiểu **đặt gì ở đâu, chạy khi nào, ai nhìn thấy và cách kiểm chứng**, chứ không chỉ nhớ cú pháp các block.

## 2. Sơ đồ giai đoạn và phạm vi

```text
settings.gradle.kts  (Settings)
  |
  +-- pluginManagement { repositories / plugin versions }
  |       dùng để resolve plugin khai báo qua plugins {}
  |
  +-- dependencyResolutionManagement { repositories }
  |       có thể quản lý repository của project dependencies
  |
  +-- include("app"), rootProject.name = ...
          |
          v
build.gradle.kts  (Project)
  |
  +-- buildscript { repositories / dependencies.classpath }
  |       chuẩn bị classpath dùng để biên dịch/chạy script
  |
  +-- plugins { id(...) version ... }
  |       yêu cầu Gradle resolve/apply plugin trước phần thân
  |       -> plugin đóng góp extension/configuration/task
  |       -> Kotlin DSL tạo type-safe accessors khả dụng
  |
  +-- phần thân script:
          group = ...
          repositories { ... }
          dependencies { implementation(...) }
          java { ... }
          tasks.register(...) { ... }
          |
          v
      Task graph -> task actions khi execution
```

Sơ đồ thể hiện **quan hệ logic**. Gradle biên dịch Kotlin DSL theo những bước phù hợp để các plugin trong `plugins` có thể ảnh hưởng đến tập accessor của phần thân; không nên hiểu mỗi dòng trong sơ đồ là một process/JVM riêng. Thứ tự cấp file có quy tắc:

- `import` có thể đặt đầu file như Kotlin thông thường.
- Nếu cần `buildscript { ... }`, block này được đặt **trước `plugins { ... }`**.
- `plugins { ... }` phải ở **top level và trước phần logic thông thường** trong project build script. Không bọc nó trong `if`, `forEach` hay trong `subprojects { ... }`.
- Sau đó mới đặt `group`, `version`, `repositories`, `dependencies`, `tasks` và các lời gọi cấu hình khác.
- Trong `settings.gradle.kts`, `pluginManagement { ... }` phải đặt ở đầu script theo quy định riêng của settings.

Không thể dùng một biến `val pluginVersion = ...` tự tạo ở phần thân script rồi đưa ngược lên `plugins` vì phần thân được đánh giá **sau bước quyết định plugin**. Plugin DSL yêu cầu cú pháp tĩnh/được Gradle hỗ trợ; catalog alias và một số cách lấy version từ Gradle properties là ngoại lệ có quy tắc, không có nghĩa được chạy Kotlin tùy ý bên trong `plugins`.

## 3. So sánh trực tiếp

| Tiêu chí | `plugins { }` | `buildscript { }` | Phần thân `build.gradle.kts` |
| --- | --- | --- | --- |
| Đối tượng/DSL | `PluginDependenciesSpec` | `ScriptHandler` / script classpath | Chủ yếu `Project` cùng API/extension của plugin |
| Mục đích | Khai báo ID, version, apply plugin | Đưa thư viện hoặc implementation plugin lên classpath của **script** | Cấu hình project, dependencies ứng dụng, task, extension |
| Repository liên quan | `pluginManagement.repositories` tại settings (mặc định Gradle Plugin Portal nếu không tùy biến) | `buildscript.repositories` trong script | `repositories` của project hoặc `dependencyResolutionManagement.repositories` ở settings |
| Dependency thường thấy | `id("...") version "..."`, `alias(...)` | `classpath("group:module:version")` | `implementation(...)`, `testImplementation(...)`, `api(...)` tùy plugin |
| Thời điểm | Được Gradle phân giải/áp dụng sớm trước thân script | Chuẩn bị classpath của script | Khi configuration; task action chỉ chạy ở execution |
| Tạo type-safe accessors? | Có, cho mô hình do plugin được áp dụng đủ sớm | Không chỉ vì JAR đã nằm trên script classpath | Mô hình tạo muộn thường không sinh accessor dùng ngay trong cùng script |
| Khác biệt đáng nhớ | **Khai báo plugin** | **Thư viện cho mã build** | **Cấu hình dự án và task** |

**Cùng tên hàm, khác receiver:** `repositories { mavenCentral() }` bên trong `buildscript` không giống `repositories { mavenCentral() }` ở cấp project. Tương tự, `dependencies { classpath(...) }` bên trong `buildscript` và `dependencies { implementation(...) }` của project đi vào **hai bộ dependencies khác nhau**.

## 4. `plugins { }` — khai báo plugin trước khi cấu hình project

### 4.1. Plugin Gradle tích hợp sẵn

```kotlin
// build.gradle.kts
plugins {
    id("java")
}
```

Plugin `java` đi cùng Gradle nên không cần version hoặc tải implementation từ Plugin Portal. Nó tạo các task như `compileJava`, `test`, các configurations như `implementation`, `testImplementation`, và extension `java`. Vì plugin được áp dụng trong `plugins`, phần thân có thể viết:

```kotlin
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    id("java")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Đây là **một file `build.gradle.kts` hoàn chỉnh** cho Java project tối giản. `java { ... }` và `implementation(...)` là các accessor có kiểu nhờ `java` plugin. File không có source Java vẫn có thể chạy `help`/`tasks`; để thực sự compile Java cần đưa source vào `src/main/java` và JDK/toolchain thích hợp.

### 4.2. Plugin bên ngoài Gradle

Một plugin cộng đồng thường được xác định bằng **ID và version**:

```kotlin
// Đoạn cấu hình minh họa trong build.gradle.kts
plugins {
    id("com.github.ben-manes.versions") version "0.51.0"
}
```

Gradle tìm plugin theo hệ thống **plugin resolution**, thông thường qua plugin marker và các repositories khai báo tại `pluginManagement`; nó không lấy plugin chỉ vì project có `repositories { mavenCentral() }`. Phiên bản `0.51.0` ở đây chỉ là một ví dụ cố định để minh họa cú pháp; khi áp dụng thực tế cần kiểm tra tương thích với Gradle Wrapper và Java của dự án.

**Lưu ý giới hạn:** không đặt vòng lặp, câu điều kiện hay gọi tùy ý đến hàm trong `plugins`. Một số cú pháp được Gradle hỗ trợ, ví dụ `id("...") version "..." apply false` hoặc `alias(libs.plugins.someAlias)`, vẫn thuộc cơ chế plugin DSL tĩnh. Đừng coi `plugins` là block Kotlin thông thường.

### 4.3. `apply false` trong build nhiều project

Giả sử root project cần **cấp version plugin**, nhưng chỉ subproject `app` thực sự áp dụng plugin:

```kotlin
// Root build.gradle.kts
plugins {
    id("com.github.ben-manes.versions") version "0.51.0" apply false
}
```

```kotlin
// app/build.gradle.kts
plugins {
    id("com.github.ben-manes.versions")
}
```

`apply false` có nghĩa là khai báo/đưa plugin vào cơ chế quản lý classpath của build **nhưng không apply cho project khai báo**. Subproject có thể apply theo ID mà không lặp version, khi plugin đã có sẵn trong build theo cấu trúc này. Plugin không tự áp dụng cho mọi subproject chỉ vì root khai báo nó.

Với **core plugins**, không cần khai báo kiểu `id("java") apply false` ở root để subproject sử dụng: bản thân Gradle đã có plugin `java`. Từng project tự khai báo `plugins { id("java") }` khi cần.

### 4.4. Version catalog chỉ là cách đặt tên các plugin requests

Nếu file `gradle/libs.versions.toml` định nghĩa:

```toml
[versions]
versions-plugin = "0.51.0"

[plugins]
versions = { id = "com.github.ben-manes.versions", version.ref = "versions-plugin" }
```

Thì project có thể viết:

```kotlin
plugins {
    alias(libs.plugins.versions)
}
```

`alias(...)` vẫn thuộc **`plugins` scope** và vẫn resolve/apply Gradle plugin. Nó **không phải** khai báo một dependency kiểu `implementation(libs...)`. Type-safe accessor `libs.plugins.versions` chỉ tồn tại khi catalog `libs` được cấu hình và alias tương ứng hợp lệ; tên alias trong TOML không phải class Kotlin tự tồn tại ở mọi build.

## 5. `buildscript { }` — classpath dành cho build script

Dùng `buildscript` khi **chính mã cấu hình Gradle** cần một thư viện, hoặc phải tải một implementation plugin theo cơ chế legacy. Ví dụ độc lập với ứng dụng Java:

```kotlin
// build.gradle.kts — ví dụ riêng, cần kết nối Maven Central lần đầu
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath("org.apache.commons:commons-lang3:3.14.0")
    }
}

plugins {
    id("base")
}

println(
    "Script helper: " +
        org.apache.commons.lang3.StringUtils.reverse("Gradle")
)
```

**Cách chạy** (đã có Gradle Wrapper trong thư mục):

```bash
./gradlew -q help
```

Đoạn stdout do chính dòng `println` trong script tạo ra:

```text
Script helper: eldarG
```

Lệnh `help` còn in trợ giúp của Gradle; khối trên **chỉ trích dòng do build script in**, không phải toàn bộ stdout. Khi project được configuration, `buildscript` đưa JAR `commons-lang3` lên script classpath để Kotlin DSL biên dịch/nhận diện `StringUtils` trong phần thân. `plugins { id("base") }` vẫn áp dụng core plugin theo cơ chế riêng; không cần `commons-lang3` cho plugin `base`.

**Giới hạn của ví dụ:** `commons-lang3` nằm trên **script classpath**. Nếu muốn code ứng dụng sử dụng `org.apache.commons.lang3.StringUtils`, dự án vẫn cần thêm dependency thích hợp, ví dụ `implementation("org.apache.commons:commons-lang3:3.14.0")` sau khi áp dụng `java` plugin. Việc thêm vào `classpath` không đồng nghĩa tạo `implementation` hoặc copy JAR vào sản phẩm build.

### 5.1. Dùng `buildscript` để load plugin legacy

Một dạng cũ còn gặp trong repository:

```kotlin
// build.gradle.kts — cơ chế legacy, ví dụ plugin cộng đồng
buildscript {
    repositories {
        gradlePluginPortal()
    }
    dependencies {
        classpath("com.github.ben-manes:gradle-versions-plugin:0.51.0")
    }
}

apply(plugin = "com.github.ben-manes.versions")
```

Ở đây **module Maven/JAR** trên classpath và **plugin ID** khi `apply` là hai định danh khác nhau. Không nhầm `classpath("com.github...:gradle-versions-plugin:...")` với `id("com.github.ben-manes.versions") version ...`. Kinh nghiệm nên ưu tiên `plugins` DSL khi plugin hỗ trợ plugin marker và môi trường giải quyết plugin phù hợp; `buildscript` thường dùng để duy trì mã legacy hoặc tích hợp đặc thù.

### 5.2. `buildscript.repositories` và `repositories` ở project không thay thế nhau

```kotlin
buildscript {
    repositories {
        mavenCentral() // Tìm JAR dành cho script classpath
    }
    dependencies {
        classpath("org.apache.commons:commons-lang3:3.14.0")
    }
}

plugins {
    id("java")
}

repositories {
    mavenCentral() // Tìm thư viện cho application/project dependencies
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Cùng một artifact được khai báo **hai lần vào hai cấu hình có mục đích khác nhau** để minh họa sự phân tách. Trong dự án thật chỉ khai báo ở nơi cần thiết, tránh đưa thư viện ứng dụng vào script classpath khi build script không sử dụng nó.

Một trường hợp gây nhầm: đã có `buildscript.repositories { mavenCentral() }` nên tin rằng `implementation("...")` cũng resolve được. Không đúng: nó phải dùng **project repositories** hoặc policy `dependencyResolutionManagement.repositories`. Ngược lại, có `repositories { mavenCentral() }` ở project không đảm bảo `buildscript.classpath` tìm được thư viện của script.

## 6. Phần thân `build.gradle.kts` — cấu hình Project

Sau `plugins`, mã Kotlin DSL được thực thi trong **configuration phase** để chuẩn bị mô hình build. Các khối thường gặp là:

| Cú pháp | Tác động thực tế |
| --- | --- |
| `group = "com.example"`, `version = "1.0"` | Thông tin định danh artifact/project |
| `repositories { mavenCentral() }` | Nơi resolve project dependencies, trừ khi settings policy ghi đè/hạn chế |
| `dependencies { implementation(...) }` | Gắn thư viện vào configuration do plugin cung cấp |
| `java { toolchain { ... } }` | Cấu hình extension do Java plugin cung cấp |
| `tasks.register("name") { ... }` | Đăng ký task theo cơ chế lazy configuration |
| `tasks.named("test") { ... }` | Cấu hình task đã đăng ký mà chưa buộc realize ngay |
| `plugins.withId("java") { ... }` | Trong phần thân, đây là **PluginContainer callback**, khác `plugins { ... }` DSL ở đầu file |
| `apply(plugin = "...")` | Cách apply plugin legacy ở thời điểm thân script, có hạn chế accessor |

Khi phần thân chạy, **task actions** bên trong `doLast { ... }` chưa được thực thi, trừ khi task thực sự nằm trong graph và được chạy sau configuration. Ngược lại, `println("Configuring")` đặt ngay ở top level có thể in ra trong lúc configuration và **không in lại khi configuration cache được tái sử dụng**.

Ví dụ phân biệt hai thời điểm:

```kotlin
// build.gradle.kts
plugins {
    id("base")
}

println("[configuration] configuring the project")

tasks.register("helloScope") {
    group = "learning"
    doLast {
        println("[execution] helloScope task ran")
    }
}
```

```bash
./gradlew -q helloScope
```

Khi configuration thực sự chạy, stdout liên quan là:

```text
[configuration] configuring the project
[execution] helloScope task ran
```

Nếu **configuration cache hit**, Gradle có thể không đánh giá lại script: dòng `[configuration]` biến mất, còn task action vẫn chạy nếu task được chọn. Không đặt hành động bắt buộc thực hiện **mỗi lượt build** vào một `println`/side effect ở thân configuration.

## 7. Ví dụ A — project Kotlin DSL hoàn chỉnh dùng `plugins` đúng mục đích

Đây là ví dụ **tự chạy được** trên một Gradle build có Wrapper và JDK tương thích, không cần plugin bên ngoài Gradle. Tạo cấu trúc:

```text
scope-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── app/
│   └── build.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
```

`settings.gradle.kts`:

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "scope-demo"
include("app")
```

Root `build.gradle.kts`:

```kotlin
plugins {
    id("base")
}
```

`app/build.gradle.kts`:

```kotlin
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    id("java")
}

// Đây là phần thân script của Project :app.
group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.register("identifyScope") {
    group = "learning"
    description = "Kiểm tra task do phần thân script đăng ký"
    doLast {
        println("App project body task")
    }
}
```

**Giải thích đúng thứ tự:**

1. `settings.gradle.kts` có `pluginManagement` ở đầu để quản lý nơi tìm **external plugins**. `java` và `base` là core plugins nên ví dụ không cần tải từ Plugin Portal.
2. Root áp dụng `base` cho root **chứ không tự động áp dụng `java` cho app**.
3. `app` áp dụng `java` trong `plugins`, do đó `java { }` và `implementation(...)` ở thân có accessor hợp lệ.
4. `repositories { mavenCentral() }` trong `app` là repository cho `implementation`, không phải cho `plugins`.
5. `identifyScope` được đăng ký trong phần thân project `:app`; action `doLast` chỉ chạy khi gọi task tương ứng. Không khai báo artifact đầu ra nên task demo chỉ in stdout, không thể dùng làm ví dụ build cache output.

Chạy từ root (Linux/macOS):

```bash
./gradlew :app:tasks --all
./gradlew -q :app:identifyScope
```

Trong PowerShell:

```powershell
.\gradlew.bat :app:tasks --all
.\gradlew.bat -q :app:identifyScope
```

**Stdout của task trong lệnh thứ hai**:

```text
App project body task
```

Nếu muốn khảo sát dependencies ứng dụng (cần mạng/cache khi thực sự resolve artifact):

```bash
./gradlew :app:dependencies --configuration compileClasspath
```

Lệnh này báo dependency graph liên quan đến project `:app`, không phải toàn bộ classpath của build script.

## 8. Ví dụ B — vì sao `apply(plugin = "...")` làm thiếu type-safe accessors?

Hai file sau đều áp dụng Java plugin nhưng khác **thời điểm áp dụng**.

**Cách khuyến nghị — plugin được apply sớm:**

```kotlin
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    id("java")
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

**Cách legacy — plugin được apply trong phần thân:**

```kotlin
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.jvm.toolchain.JavaLanguageVersion

apply(plugin = "java")

extensions.configure<JavaPluginExtension> {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

dependencies {
    add("implementation", "org.apache.commons:commons-lang3:3.14.0")
}
```

Mỗi khối là **một `build.gradle.kts` thay thế**, không dán cả hai vào một file. Trong ví dụ legacy, Java plugin có thể được apply thành công, nhưng Kotlin DSL **không sinh accessor `java { ... }` hay `implementation("...")` từ plugin apply ở phần thân cùng script**. Vì vậy code gọi API theo type/name: `extensions.configure<JavaPluginExtension> { ... }` và `dependencies.add("implementation", ...)`. Nếu task cần tạo, cũng có thể dùng `tasks.named("compileJava") { ... }` hoặc typed task API phù hợp.

Tính chất này bắt nguồn từ cơ chế Gradle lấy **snapshot mô hình để sinh type-safe accessors ngay sau `plugins` block**, trước khi đánh giá thân script. Nó cũng ảnh hưởng các extension/configuration **được tạo muộn trong chính body**, các script plugin `apply(from = ...)` và một số cross-project configuration. Không thể sửa bằng cách đặt `apply(plugin = "java")` trên một dòng sớm hơn trong body rồi mong Kotlin compiler sinh lại accessors.

**Bẫy thường thấy:**

```kotlin
// Không hoạt động như kỳ vọng: không có accessor Java từ apply ở body.
apply(plugin = "java")

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Kotlin DSL có thể báo `Unresolved reference: implementation`. Hãy chuyển plugin declaration vào `plugins` hoặc dùng `add("implementation", ...)` như ví dụ trên.

## 9. Định tuyến repositories đúng phạm vi

Trong một Gradle build, tối thiểu có **ba đường resolve** cần phân biệt:

| Bạn đang resolve gì? | Đặt repository ở đâu? | Ví dụ |
| --- | --- | --- |
| **Plugin qua `plugins`** | `pluginManagement.repositories` trong `settings.gradle.kts`; mặc định Gradle Plugin Portal khi không tùy biến | `gradlePluginPortal()`, internal plugin Maven repo |
| **Thư viện/plugin implementation cho script qua `buildscript`** | `buildscript.repositories` trong `build.gradle.kts` hoặc init logic tương ứng | `mavenCentral()` hoặc repo nội bộ |
| **Thư viện của ứng dụng/module** | `repositories` của project hoặc `dependencyResolutionManagement.repositories` của settings theo policy | `mavenCentral()`, internal artifact repository |

Ví dụ settings tập trung policy cho application dependencies:

```kotlin
// settings.gradle.kts
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "centralized-repositories"
```

Với `FAIL_ON_PROJECT_REPOS`, project **không được khai báo `repositories { ... }` riêng**. Khi dùng mẫu này, đừng copy lại `repositories { mavenCentral() }` từ ví dụ A vào `build.gradle.kts`; thay vào đó dựa vào `dependencyResolutionManagement.repositories`. Mẫu settings này minh họa **một cách cấu hình thay thế** cho project repository ở phần 7, không phải phần cần ghép chung vào cùng build.

**Tình huống kiểm tra:** nếu `Plugin [id: '...'] was not found`, kiểm tra `plugins` request, plugin ID/version và `pluginManagement`. Nếu `Could not resolve ...` trong `buildscript classpath`, kiểm tra `buildscript.repositories` và tọa độ artifact. Nếu lỗi resolve `implementation`, kiểm tra project/settings repositories và dependency coordinates. Thêm `mavenCentral()` vào nhầm một block sẽ không giải quyết đúng vấn đề.

## 10. Phạm vi script khác nhau theo file và project

`settings.gradle.kts` không có cùng receiver với `build.gradle.kts`:

- Trong **settings**: object chính là `Settings`; `pluginManagement`, `dependencyResolutionManagement`, `rootProject.name` và `include("app")` điều khiển quá trình thiết lập build. `plugins { ... }` ở settings nếu dùng sẽ áp dụng **settings plugin**, không tự động là project plugin.
- Trong **project build script**: object chính là `Project`; `plugins` áp dụng plugin vào project tương ứng, rồi phần thân cấu hình repository, dependencies, extension, tasks của project đó.
- Trong **init script**: ngữ cảnh và thời điểm khác, không dùng `plugins { ... }` theo cú pháp restricted của project build script.
- Trong **precompiled script plugin** và **binary plugin**: các API có quy tắc riêng. Khi logic dự án trở nên lớn, nên chuyển từ các đoạn `apply(from = ...)` lặp lại sang convention plugin thích hợp thay vì sao chép build script giữa nhiều module.

Một project `:app` có `plugins { id("java") }` **không suy ra** project `:lib` cũng có Java plugin. Root có cấu hình plugin với `apply false` cũng **không** khiến extension Java xuất hiện tại root. Khi lỗi `Unresolved reference: java`, hãy kiểm tra **file đang viết, project đích và plugin đã apply đủ sớm hay chưa**.

Trong cùng một build Kotlin DSL, các `val` ở **top-level của build script** là biến của đoạn mã cấu hình hiện tại, không tự thành biến dùng được trong build script subproject. Với giá trị chia sẻ, dùng `gradle.properties`, version catalog, extension/convention plugin hoặc cơ chế Gradle Providers phù hợp; không phụ thuộc biến top-level của file khác.

## 11. Phân biệt ba loại “dependencies”

### 11.1. `plugins { id(...) }` — plugin request

```kotlin
plugins {
    id("java")
}
```

Đây là **Gradle plugin**, không phải dependency được Java compiler import vào application. Plugin thêm quy tắc build, task, extension, configuration.

### 11.2. `buildscript { dependencies { classpath(...) } }` — script classpath

```kotlin
buildscript {
    repositories { mavenCentral() }
    dependencies {
        classpath("org.apache.commons:commons-lang3:3.14.0")
    }
}
```

JAR phục vụ code **trong script Gradle** và các class/plugin implementation được nạp để cấu hình build. Điều này có thể khiến configuration nặng hơn; nên hạn chế cho trường hợp cần thiết.

### 11.3. `dependencies { implementation(...) }` — application classpath

```kotlin
plugins {
    id("java")
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
}
```

Hai thư viện này được khai báo vào các dependency configurations của **project Java**. `testImplementation` dùng cho biên dịch/chạy test theo cách Gradle Java plugin quy định; `implementation` dùng cho compile/runtime phù hợp mô hình Java. Chúng **không trở thành import có sẵn cho Kotlin code của build script**, trừ khi được cung cấp cho chính script qua cơ chế riêng.

Nếu đang dùng plugin `java-library`, còn có configuration `api`; nếu dự án không apply plugin tạo `implementation`/`testImplementation` thì những tên này không tự tồn tại. Trước khi thêm dependency, kiểm tra đúng plugin và project.

## 12. Cách kiểm chứng trong Gradle thực tế

Sau khi sửa `plugins`, `buildscript` hoặc phần thân Kotlin DSL, thực hiện các phép thử tương ứng:

```bash
# 1. Gradle đọc/compile được script và áp dụng plugin chưa?
./gradlew help

# 2. Plugin đã tạo đúng tasks chưa?
./gradlew :app:tasks --all

# 3. Dependencies ứng dụng trong Java project:
./gradlew :app:dependencies --configuration compileClasspath

# 4. Classpath của build script trong project tương ứng:
./gradlew :app:buildEnvironment

# 5. Cảnh báo cấu hình và khả năng tái sử dụng configuration:
./gradlew help --warning-mode all
./gradlew help --configuration-cache
./gradlew help --configuration-cache
```

Các lệnh ví dụ trên giả định build có project `:app` như phần 7. Nếu build là single-project, bỏ `:app:`. `buildEnvironment` cho thấy **script classpath** để kiểm tra `buildscript.dependencies.classpath`; `dependencies --configuration compileClasspath` cho thấy **project configuration**, không phải cùng bảng. Nếu `--configuration-cache` không thể tái sử dụng, xem lý do Gradle báo trong log/report; lỗi plugin hoặc script vẫn cần giải quyết ở đúng phạm vi.

Trên Windows PowerShell đổi `./gradlew` thành `.\gradlew.bat`; trên Command Prompt dùng `gradlew.bat`. Luôn ưu tiên Wrapper có sẵn và Java version được dự án hỗ trợ.

**Quan sát về output:** `./gradlew -q :app:identifyScope` từ ví dụ A phải in `App project body task` do action của task; `./gradlew :app:buildEnvironment` có thể hiển thị nhiều dòng phụ thuộc, phụ thuộc phiên bản Gradle và plugin nên không giả định output cụ thể.

## 13. Các lỗi phổ biến và nguyên nhân gốc

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `only buildscript {}, pluginManagement {} and other plugins {} script blocks are allowed before plugins {}` hoặc lỗi thứ tự tương tự | Đã đặt logic thường (`val`, `repositories`, `tasks`) trước `plugins` | Chuyển `plugins` lên sau `buildscript` (nếu có) và trước mọi cấu hình project; nhớ `import` vẫn hợp lệ |
| `Unresolved reference: implementation` | Chưa apply plugin Java, hoặc Java được `apply(plugin = ...)` trong thân nên không có accessor | Dùng `plugins { id("java") }`, hoặc `dependencies.add("implementation", ...)` nếu buộc dùng legacy apply |
| `Unresolved reference: java` | Extension Java không có type-safe accessor trong script | Kiểm tra plugin `java` ở `plugins`; với legacy apply dùng `extensions.configure<JavaPluginExtension>` |
| `Plugin [id: '...'] was not found` | ID/version/repository cho plugin DSL sai | Kiểm tra `pluginManagement.repositories`, ID, version, marker và quyền vào repo |
| Plugin đã nằm ở `buildscript.classpath` nhưng chưa tạo task | Chỉ thêm thư viện vào classpath, chưa apply plugin | Dùng `plugins` DSL hoặc `apply(plugin = "id")` đúng cơ chế/phiên bản |
| Không resolve được `classpath(...)` | `buildscript.repositories` chưa có repo phù hợp hoặc tọa độ JAR sai | Sửa `buildscript.repositories`/artifact, không sửa project `repositories` theo thói quen |
| Không resolve được `implementation(...)` | Thiếu project repository hoặc policy settings không phù hợp | Kiểm tra `repositories`/`dependencyResolutionManagement` và dependency coordinates |
| `FAIL_ON_PROJECT_REPOS` báo lỗi | Settings cấm khai báo repo tại project, nhưng body có `repositories` | Đặt repositories tại settings theo policy, xóa khai báo repo không phù hợp trong project |
| `plugins { ... }` không dùng được trong `if` | Plugin DSL bị giới hạn cú pháp top-level | Dùng plugin declaration tĩnh; với nhu cầu tùy biến nên dùng settings plugin management hoặc convention plugin |
| `libs.plugins.someAlias` không tồn tại | Thiếu version catalog hoặc alias khác tên | Kiểm tra `gradle/libs.versions.toml` và tên accessor do Gradle tạo |
| Root có plugin nhưng subproject thiếu extension | `apply false` chỉ khai báo, hoặc plugin chỉ apply cho root | Apply plugin trong build script của project đích |
| Script logic chạy khi `help` nhưng không chạy lại ở cache hit | Cấu hình được cache, body không đánh giá lại | Chuyển công việc phải thực thi mỗi lần vào task action với input/output đã khai báo |
| Build chạy local nhưng CI lỗi mạng | Plugin Portal, Maven Central hoặc private repo không truy cập được | Kiểm tra URL, chứng chỉ/proxy/credentials theo môi trường, không hardcode secrets vào script |

## 14. Quy tắc chọn nơi đặt logic

Khi muốn thêm một cấu hình mới, đặt các câu hỏi theo thứ tự:

1. **Đây có phải plugin Gradle?** Nếu có và plugin hỗ trợ plugin DSL, đưa vào `plugins { id(...) version ... }`, quản lý repository/version bằng `pluginManagement` hoặc version catalog.
2. **Đây là JAR chỉ phục vụ logic build script?** Nếu đúng, cân nhắc `buildscript.dependencies.classpath`, nhưng trước hết xem có cách viết convention plugin hoặc dùng API Gradle sẵn có không.
3. **Đây là thư viện của ứng dụng/test?** Đưa vào `dependencies { implementation(...) / testImplementation(...) }` và bảo đảm project/settings repositories đúng.
4. **Đây là thao tác cấu hình task/extension?** Đặt trong phần thân build script, ưu tiên `tasks.register`, `tasks.named`, `configureEach` và Provider API thay vì tạo/resolve ngay.
5. **Có cần áp dụng cho nhiều module?** Dùng convention plugin được từng project apply hoặc `apply false` kết hợp declaration của subproject; không kỳ vọng biến/script của root tự điều khiển tất cả project.
6. **Có thay đổi plugin ID/version/repository?** Kiểm tra cơ chế plugin resolution trước, vì task execution và project repositories không sửa được lỗi resolve plugin đã xảy ra sớm hơn.
7. **Có thông tin nhạy cảm?** Đừng in token/mật khẩu từ script, đừng nhúng credentials vào repo URL; ưu tiên Gradle Providers và cơ chế bảo quản secrets của CI.

## 15. Kiến thức cần nhớ

- `plugins { }` = **yêu cầu Gradle apply plugin**, từ đó plugin tạo task/extension/configuration đủ sớm để Kotlin DSL sinh type-safe accessors.
- `buildscript { }` = **classpath riêng cho mã chạy build script**, gồm `repositories` và `dependencies.classpath`; đây không phải nơi khai báo thư viện ứng dụng.
- **Phần thân `build.gradle.kts`** = cấu hình `Project` bằng những API/extension đã sẵn có; task actions trong `doLast` chạy khi task được thực thi, khác với việc evaluate script.
- **Thứ tự:** `import` → `buildscript` (nếu cần) → `plugins` → thân script; `pluginManagement` đầu `settings.gradle.kts`.
- **Ba repository scope:** `pluginManagement.repositories` cho plugin DSL, `buildscript.repositories` cho script classpath, project/settings `repositories` cho application dependencies.
- `apply(plugin = "...")` từ phần thân **không tạo type-safe accessors trong cùng script**; khi cần legacy apply, dùng `extensions.configure<Type>`, `dependencies.add(...)` và task APIs theo tên/kiểu.
- Nếu sửa một khối mà lỗi vẫn còn, trước hết xác định Gradle đang resolve **plugin**, **script classpath** hay **project dependency**.

## Tài liệu chính thức

- [Gradle Kotlin DSL Primer — scripts và type-safe accessors](https://docs.gradle.org/current/userguide/kotlin_dsl.html)
- [Gradle Working with Plugins — plugins DSL, buildscript, apply false, pluginManagement](https://docs.gradle.org/current/userguide/plugins_intermediate.html)
- [Gradle PluginDependenciesSpec — giới hạn cú pháp và thứ tự block](https://docs.gradle.org/current/javadoc/org/gradle/plugin/use/PluginDependenciesSpec.html)
- [Gradle Declaring Repositories Basics — plugin repository và project repository](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html)
- [Gradle Declaring Dependencies — dependency configurations của project](https://docs.gradle.org/current/userguide/declaring_dependencies.html)
- [Gradle Configuration Cache — khác nhau giữa configuration và execution](https://docs.gradle.org/current/userguide/configuration_cache.html)
