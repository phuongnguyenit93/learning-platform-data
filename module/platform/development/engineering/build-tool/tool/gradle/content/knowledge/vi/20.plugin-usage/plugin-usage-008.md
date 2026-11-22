# Quản lý plugin thống nhất qua Settings và Version Catalog trong Gradle

## 1. Bài toán: vì sao nhiều module dễ dùng lệch plugin?

Một Gradle multi-project thường có các subproject `:app`, `:lib`, `:integration-test`. Mỗi module có thể khai báo plugin Kotlin, Java, Android, formatter, code quality, publishing hoặc test tooling. Khi mỗi `build.gradle(.kts)` tự ghi plugin ID, version và repositories, những vấn đề sau dễ xuất hiện:

- `:app` dùng phiên bản plugin A khác `:lib`; build có thể lỗi API hoặc classloader khi plugin cùng loại được tải nhiều lần.
- Một developer thêm `mavenCentral()` vào project repositories rồi nghĩ nó cũng giúp Gradle tìm plugin trong `plugins { }`.
- Plugin vừa đổi version trong một module, các module khác không được nâng cùng, khiến CI và local có hành vi khác nhau.
- Một plugin nội bộ chỉ được publish ở Maven repository doanh nghiệp, nhưng `plugins { }` vẫn tìm trong Gradle Plugin Portal.
- Người dùng gọi `alias(libs.plugins.somePlugin)` trong `settings.gradle.kts` rồi gặp lỗi vì version catalog **không dùng trực tiếp để khai báo settings plugins**.
- Root project khai báo plugin với `apply false` nhưng ai đó cho rằng nó đã tự áp dụng cho mọi subproject.
- Build dùng đồng thời `pluginManagement.plugins` và version catalog cho cùng plugin mà không có chính sách “nguồn phiên bản chuẩn”.

Gradle có hai cơ chế bổ sung nhau:

1. **`pluginManagement { }` trong `settings.gradle(.kts)`**: quản lý **cách tìm plugin**, **phiên bản mặc định khi request chưa ghi version**, luật ánh xạ plugin marker/implementation và plugin build logic.
2. **`gradle/libs.versions.toml`** (version catalog): quản lý **alias + plugin ID + version** dùng lại trong `plugins { alias(libs.plugins...) }` của các **project build scripts**.

Bài học sẽ tạo một multi-project Gradle chạy trên Java 17, áp dụng plugin Spotless thống nhất tại hai project qua một version catalog, rồi chỉ ra cách viết thay thế bằng `pluginManagement.plugins`. Bạn sẽ biết chọn một nguồn version nhất quán thay vì cấu hình trùng lặp.

## 2. Mô hình tổng thể và ranh giới trách nhiệm

```text
                   settings.gradle.kts
                          |
          +---------------+----------------+
          |                                |
 pluginManagement { }          dependencyResolutionManagement { }
          |                                |
 plugin repositories                    library repositories
 plugin default versions               version catalogs
 plugin resolution rules               repositoriesMode
          |                                |
          v                                v
       plugins { }                     dependencies { }
  trong build.gradle.kts           trong build.gradle.kts
          |                                |
          v                                v
   id(...) hoặc alias(...)          implementation(libs.xxx)
          |                                |
          v                                v
  Gradle tải và áp dụng plugin      Gradle resolve thư viện
```

**Ba thứ không được nhầm:**

| Thành phần | Vai trò | Ví dụ | Không đảm nhiệm |
| --- | --- | --- | --- |
| `pluginManagement.repositories` | Nơi Gradle tìm **plugin markers và implementations** cho `plugins { }` | `gradlePluginPortal()`, Maven nội bộ | Không tự cấu hình repositories cho `implementation(...)` |
| `dependencyResolutionManagement.repositories` | Nơi Gradle tìm **project libraries/modules** | `mavenCentral()`, Maven nội bộ | Không thay thế plugin repositories |
| `gradle/libs.versions.toml`, `[plugins]` | Danh mục tên alias → plugin ID/version | `spotless = { id = "...", version.ref = "spotless" }` | Không tự download/apply plugin, không tự là policy bắt buộc mọi module |

Ngoài ra `buildscript.repositories` dành cho **legacy buildscript classpath**. Một build có thể có cả ba tập repositories trong các tình huống khác nhau; thêm dependency repository vào settings không đồng nghĩa đã cấu hình plugin portal, và ngược lại.

**Thứ tự pha:** Gradle xử lý settings sớm hơn project build scripts. `pluginManagement` phải là **block đầu tiên** trong `settings.gradle(.kts)`. Điều này giải thích vì sao nó có thể chi phối plugin resolution của các subprojects, nhưng không thể đơn giản sử dụng mọi accessor sinh sau khi settings/configuration đã tiến hành.

## 3. Hai chiến lược thống nhất version plugin

### Chiến lược A — Version catalog là nguồn version cho project plugins

Trong `gradle/libs.versions.toml`:

```toml
[versions]
spotless = "8.11.0"

[plugins]
spotless = { id = "com.diffplug.spotless", version.ref = "spotless" }
```

Trong `build.gradle.kts` của mỗi project:

```kotlin
plugins {
    alias(libs.plugins.spotless)
}
```

Các project có cùng accessors và cùng requested version. `settings.gradle.kts` chỉ cần cấu hình **plugin repositories**, không cần khai báo lại version `spotless` tại `pluginManagement.plugins`.

Ưu điểm: TOML rõ ràng, dễ review nâng version, tập trung danh sách plugin và library, IDE hỗ trợ type-safe accessors. Hạn chế: alias chỉ dùng ở **project build scripts** theo phạm vi version catalog, không dùng trực tiếp trong settings file hay settings plugin. Một included build hoặc `buildSrc` là build riêng, cần setup catalog riêng nếu muốn dùng lại.

### Chiến lược B — `pluginManagement.plugins` cung cấp version mặc định

Trong `settings.gradle.kts`:

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
    plugins {
        id("com.diffplug.spotless") version "8.11.0"
    }
}
```

Trong `build.gradle.kts` của mỗi subproject:

```kotlin
plugins {
    id("com.diffplug.spotless")
}
```

Khi project request plugin ID **không ghi version**, `pluginManagement.plugins` cung cấp version mặc định. Gradle không áp dụng plugin vào project chỉ vì bạn khai báo default ở settings; từng project vẫn phải request/apply nó.

Ưu điểm: cấu hình version sớm ngay ở settings; có thể lấy version từ Gradle properties theo cơ chế settings; không cần catalog plugin alias. Hạn chế: không có type-safe catalog alias, và developer có thể vẫn khai báo version tường minh làm phát sinh nhiều nguồn version cần kiểm soát.

**Không nên phối hai chiến lược cho cùng plugin mà không có quy tắc.** `alias(libs.plugins.spotless)` mang version từ TOML; default ở `pluginManagement.plugins` dành cho **request không có version**. Chúng không tự “đồng bộ hai chiều”. Chọn một nguồn version rõ ràng cho từng loại plugin rồi review ngoại lệ.

### 3.1. Nếu chọn version từ `gradle.properties`

Ví dụ **thay thế riêng** cho chiến lược B, khi đội muốn thay version theo một Gradle property:

```properties
# gradle.properties ở root:
spotlessPluginVersion=8.11.0
```

```kotlin
// settings.gradle.kts — đây là toàn bộ block pluginManagement của phương án B.
pluginManagement {
    val spotlessVersion = providers.gradleProperty("spotlessPluginVersion").get()

    repositories {
        gradlePluginPortal()
    }
    plugins {
        id("com.diffplug.spotless") version spotlessVersion
    }
}
```

`pluginManagement.plugins` không có hạn chế cú pháp giống như `plugins { }` ở project. Do đó settings có thể tính ra version từ property và gán cho plugin default. Giá trị **phải tồn tại**; nếu thiếu `spotlessPluginVersion`, `get()` báo lỗi cấu hình sớm. Đây là lựa chọn có chủ đích, không phải cách tự động lấy `libs.versions.spotless` vào settings.

## 4. Demo hoàn chỉnh: multi-project Java 17 và một plugin catalog chung

Chúng ta dùng **Spotless** ID `com.diffplug.spotless`, phiên bản `8.11.0` có trên Gradle Plugin Portal, để minh họa một plugin **ngoài Gradle core**. Dự án gồm `:app` và `:lib`, mỗi project dùng cùng alias `libs.plugins.spotless`. Một external Java library nhỏ cho thấy catalog có thể quản lý cả dependencies.

**Yêu cầu:**

- Gradle Wrapper đủ mới để chạy Spotless 8.x và tương thích với JDK của project; kiểm tra compatibility của Gradle/Spotless khi tạo project thật.
- JDK 17 sẵn có để chạy Java toolchain 17; nếu thiếu cần cấu hình toolchain provisioning được hỗ trợ.
- Lần resolve đầu cần truy cập Gradle Plugin Portal và Maven Central hoặc mirror đã có đầy đủ artifacts/metadata.

Dùng Gradle Wrapper đã có trong repository, hoặc cài Gradle tạm để chạy `gradle wrapper` một lần rồi commit đủ các file Wrapper. Không thay `./gradlew` bằng bản Gradle global khi dự án đã pin Wrapper.

### 4.1. Cấu trúc

```text
central-plugins-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle/
│   ├── libs.versions.toml
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── app/
│   ├── build.gradle.kts
│   └── src/main/java/example/app/Main.java
└── lib/
    ├── build.gradle.kts
    └── src/main/java/example/lib/Greeting.java
```

Đây là một **Gradle multi-project build duy nhất**. Không tạo `settings.gradle.kts` riêng cho `app` hay `lib`. Root là nơi chứa `gradle/libs.versions.toml`, được Gradle import tự động thành catalog `libs`.

### 4.2. `settings.gradle.kts` — hai repository domains khác nhau

```kotlin
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

rootProject.name = "central-plugins-demo"
include(":app", ":lib")
```

**Giải thích:**

- `pluginManagement` là block đầu tiên. `gradlePluginPortal()` phục vụ **plugin ID → marker/implementation** của Spotless.
- `dependencyResolutionManagement` phục vụ dependencies của application/library, không phải plugin markers.
- `RepositoriesMode.FAIL_ON_PROJECT_REPOS` làm Gradle báo lỗi nếu build scripts/plugins cố khai báo project-level repository không được cho phép. Đây là cách **thực thi chính sách** repositories tập trung; ở cấu hình mặc định `PREFER_PROJECT`, project repositories có thể được ưu tiên.
- `include(":app", ":lib")` khai báo đúng hai subprojects.
- Trong demo không có block `pluginManagement.plugins` vì **version plugin do catalog** cung cấp; tránh khai báo trùng `8.11.0`.

Nếu tổ chức dùng mirror/plugin repository nội bộ, `pluginManagement.repositories` có thể đổi sang approved URL và credentials. **Chỉ thêm mirror nếu nó thật sự lưu plugin marker cùng implementation/artifacts**; project `mavenCentral()` không “cứu” plugin resolution thất bại.

### 4.3. `gradle/libs.versions.toml` — nguồn version/alias

```toml
[versions]
spotless = "8.11.0"
commonsLang3 = "3.17.0"

[plugins]
spotless = { id = "com.diffplug.spotless", version.ref = "spotless" }

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang3" }
```

**Hai loại aliases khác nhau:**

- `libs.plugins.spotless` là **plugin alias**, chỉ dùng tại `plugins { alias(...) }` trong project build scripts. Nó chứa plugin ID và requested version `8.11.0`.
- `libs.commons.lang3` là **library alias**, dùng trong `dependencies { implementation(...) }`. Dấu gạch nối trong alias `commons-lang3` tạo accessor theo subgroup `commons.lang3`.

`libs.versions.toml` được tự động import nếu nằm đúng đường dẫn và tên trong root `gradle/`; **không cần tạo thêm** `versionCatalogs.create("libs").from(files("gradle/libs.versions.toml"))` cho đúng file mặc định. Nếu catalog nằm nơi khác hoặc từ published artifact thì phải cấu hình import rõ ràng.

**Phiên bản của catalog chỉ là requested version.** Nó không bảo đảm artifact bytes chính xác, không tự cố định transitive dependencies và không có nghĩa dependency locking/verification đã bật.

### 4.4. Root `build.gradle.kts` — `apply false`

```kotlin
plugins {
    alias(libs.plugins.spotless) apply false
}
```

Dòng này **đăng ký/yêu cầu plugin ở root plugin classpath nhưng không áp dụng Spotless vào root project**. `apply false` có ích cho multi-project dùng chung external plugin; root không tự có những task/mô hình do plugin đó tạo ra chỉ vì request `apply false`. Các subproject vẫn phải tự apply.

Điều quan trọng: root `apply false` là **tùy chọn** khi các subprojects đã dùng cùng catalog alias. Không phải có nó thì Gradle mới có thể đọc `libs.plugins.spotless` từ `app` và `lib`. Tránh thêm `apply false` cho core plugin `java`/`application` vì core plugins vốn có sẵn và không cần pin version như external plugins.

### 4.5. `lib/build.gradle.kts`

```kotlin
plugins {
    `java-library`
    alias(libs.plugins.spotless)
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(libs.commons.lang3)
}

spotless {
    java {
        target("src/**/*.java")
        trimTrailingWhitespace()
        endWithNewline()
    }
}
```

Plugin `java-library` là **Gradle core plugin**, nên không cần version catalog entry. `spotless` là external plugin, được áp dụng **thực sự** ở `:lib` qua alias.

`trimTrailingWhitespace()` và `endWithNewline()` là hai quy tắc formatting minh họa để `spotlessCheck` có gì để kiểm tra; project thật có thể chọn công cụ formatter thống nhất theo chính sách. `java.toolchain.languageVersion` chọn Java 17 cho compilation, không thay thế việc JVM chạy Gradle phải tương thích với Wrapper/Spotless.

### 4.6. `lib/src/main/java/example/lib/Greeting.java`

```java
package example.lib;

import org.apache.commons.lang3.StringUtils;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return StringUtils.capitalize("hello from centralized plugins");
    }
}
```

`Greeting` dùng Commons Lang 3 được khai báo qua library alias `libs.commons.lang3`. Phương thức `capitalize` biến chữ cái đầu thành chữ hoa mà không phụ thuộc vào locale mặc định của shell trong ví dụ này.

### 4.7. `app/build.gradle.kts`

```kotlin
plugins {
    application
    alias(libs.plugins.spotless)
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":lib"))
}

application {
    mainClass.set("example.app.Main")
}

spotless {
    java {
        target("src/**/*.java")
        trimTrailingWhitespace()
        endWithNewline()
    }
}
```

`:app` không viết trực tiếp Spotless ID hay version ở đây. Nó nhận cùng plugin alias đã dùng trong `:lib`. `application` là Gradle core plugin, tạo task `run`; `implementation(project(":lib"))` dùng project dependency, giúp Gradle nối Java compilation và runtime classpath qua producer/consumer variants.

### 4.8. `app/src/main/java/example/app/Main.java`

```java
package example.app;

import example.lib.Greeting;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

### 4.9. Chạy và kiểm chứng

Linux/macOS:

```bash
./gradlew --version
./gradlew -q :app:run
./gradlew :app:spotlessCheck :lib:spotlessCheck
./gradlew :app:tasks --all
./gradlew :lib:tasks --all
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat -q :app:run
.\gradlew.bat :app:spotlessCheck :lib:spotlessCheck
.\gradlew.bat :app:tasks --all
.\gradlew.bat :lib:tasks --all
```

Với đúng nội dung nguồn và dependencies đã resolve thành công, **stdout của chương trình Java** do `:app:run` in là:

```text
Hello from centralized plugins
```

Gradle có thể in cảnh báo hoặc tiến trình tải plugin/library ngoài đoạn trên, tùy console và môi trường. `spotlessCheck` ở cả hai project xác minh các quy tắc whitespace/newline đã cấu hình. Với các file Java trong demo có newline cuối dòng hợp lệ, task dự kiến thành công. Nếu bạn cố ý thêm trailing spaces hoặc bỏ newline cuối file, `spotlessCheck` có thể fail; dùng `./gradlew :app:spotlessApply :lib:spotlessApply` rồi chạy lại check (trên Windows thay script Wrapper tương ứng).

**Cách xác nhận version được quản lý tập trung:** mở duy nhất `gradle/libs.versions.toml` và xem `spotless = "8.11.0"`. Các subproject không chứa một bản version thứ hai. Khi update theo policy, đổi catalog rồi chạy hai task Spotless và Java build/test để phát hiện incompatibility.

**Giới hạn về runnable:** demo cần Plugin Portal/Maven Central hoặc approved mirror, Gradle Wrapper/JDK tương thích, và đúng các file đã nêu. Đây không phải ví dụ offline hoàn toàn khi chưa có artifacts trong cache.

## 5. Điểm khác nhau giữa Version Catalog và `pluginManagement.plugins`

| Câu hỏi | Version Catalog `[plugins]` | `pluginManagement.plugins` |
| --- | --- | --- |
| Được khai báo ở đâu? | `gradle/libs.versions.toml` hoặc catalog khác đã import | `settings.gradle(.kts)` |
| Tác dụng chính | Cấp plugin alias với ID và version cho build scripts | Cấp default version cho plugin request theo ID |
| Cú pháp ở subproject | `alias(libs.plugins.spotless)` | `id("com.diffplug.spotless")` |
| Có tự áp dụng plugin không? | **Không** — cần project request | **Không** — cần project request |
| Dùng được để chọn plugin repository không? | **Không** | Có, trong `pluginManagement.repositories` |
| Dùng trực tiếp để apply settings plugin không? | **Không** | Settings `plugins { id(...) version ... }` sử dụng cơ chế riêng |
| Có tự khóa toàn bộ transitive plugin deps không? | Không | Không |
| Có tự ép toàn bộ build phải dùng cùng version bất kể khai báo khác? | Không | Không; là default cho requests chưa ghi version |
| Hợp nhất code/behavior giữa modules? | Không, chỉ version/ID aliases | Không; cần convention plugins để chia sẻ logic |

Trong project `build.gradle.kts`, nếu dùng catalog alias mà lại ghi:

```kotlin
plugins {
    alias(libs.plugins.spotless) version "8.11.0"
}
```

Đây **không phải cách được khuyên dùng**. Alias đã chứa version; không cần khai báo trùng version tại chỗ. Hãy giữ `alias(libs.plugins.spotless)` thuần, hoặc dùng `id(...) version "..."` khi không có catalog — nhưng đừng trộn để người đọc không biết nguồn nào mới là chuẩn.

### 5.1. Plugin core và plugin ngoài Gradle core

`java`, `application`, `java-library`, `maven-publish` là **core plugins** được phát hành cùng Gradle. Chúng không cần tìm trên Plugin Portal và không có version độc lập cần đặt trong TOML. Đừng khai báo:

```toml
# Không nên: core plugin không cần external version.
[plugins]
java = { id = "java", version = "8.11.0" }
```

Điều đó nhầm **Gradle distribution version** với **plugin version**. Đối với core plugins, pin **Gradle Wrapper version** và dùng `plugins { java }` hoặc `plugins { id("java") }`. Đối với external plugin, pin version qua catalog hoặc `pluginManagement`.

## 6. Alias names, accessors và TOML hợp lệ

Cấu trúc Version Catalog:

```toml
[versions]
spotless = "8.11.0"
kotlin = "2.2.20"

[plugins]
spotless = { id = "com.diffplug.spotless", version.ref = "spotless" }
kotlin-jvm = { id = "org.jetbrains.kotlin.jvm", version.ref = "kotlin" }

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version = "3.17.0" }
```

Trong project build script:

```kotlin
plugins {
    alias(libs.plugins.spotless)
    alias(libs.plugins.kotlin.jvm)
}
```

**Ví dụ này chỉ minh họa accessors**, không phải đoạn thay thế cho demo Java ở phần 4. Nếu thêm Kotlin JVM plugin vào Java project thật, cần kiểm tra compatibility với Gradle Wrapper, Java toolchain và cách cấu hình compiler; không tự gắn plugin chỉ để có một alias.

Alias có dấu `-` sẽ tạo subgroup accessors; ví dụ `kotlin-jvm` → `libs.plugins.kotlin.jvm`. Nếu nhiều aliases tạo xung đột giữa tên nhóm và tên lá (chẳng hạn `foo` và `foo-bar`), Gradle có thể báo type-safe accessor collision. Dùng tên đủ tách biệt hoặc camelCase như `kotlinJvm` để có `libs.plugins.kotlinJvm`.

Một số tên dành riêng và quy tắc đặt alias được Gradle kiểm soát. Không đặt alias tùy tiện như `versions`, `plugins` hoặc `bundles` theo cách tạo ra reserved accessor names. Nếu build báo invalid catalog alias, sửa key TOML — không chỉnh file type-safe accessor do Gradle tự sinh.

**Version catalogs của plugins dùng required version.** Không dựa vào `strictly`, `prefer` hay `reject` ở plugin aliases như các rich version constraints cho module libraries; Gradle đã deprecate các dạng plugin version rich constraints.

## 7. Một bẫy quan trọng: `libs.plugins` không dùng trực tiếp trong `settings.gradle.kts`

Đây là giới hạn chính thức của Gradle: **plugin được khai báo trong version catalog không thể dùng làm plugin alias trong settings file hoặc settings plugin**.

Ví dụ **sai**:

```kotlin
// settings.gradle.kts — KHÔNG hợp lệ:
plugins {
    alias(libs.plugins.spotless)
}
```

Hai lý do:

1. Catalog `libs` được dùng như accessor ở project build script, không tự khả dụng trong settings `plugins { }` ở thời điểm và context tương ứng.
2. Spotless là **project plugin** trong demo, không phải plugin thiết kế để áp dụng lên Settings object.

Nếu cần **settings plugin thực sự**, hãy áp dụng nó bằng ID + version tường minh trong settings `plugins { }`, với `pluginManagement.repositories` khai báo đúng plugin repository. Ví dụ **mẫu cú pháp**, không dùng plugin Spotless ở Settings:

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

// Đoạn dưới chỉ minh họa dạng cú pháp settings plugin.
// Plugin ID/version phải thay bằng settings plugin THỰC TẾ của tổ chức.
plugins {
    id("com.example.settings-policy") version "1.0.0"
}
```

Đoạn trên **không chạy độc lập** nếu chưa publish `com.example.settings-policy:1.0.0` với implementation hỗ trợ `Plugin<Settings>`. Không suy rằng vì dự án đã có alias plugin, nó áp dụng được trong Settings. Nếu plugin cần nhất quán giữa settings và project context, phải thiết kế nguồn version chia sẻ được ở cả hai pha (ví dụ Gradle property và quản trị update), hoặc dùng settings convention plugin để tạo catalog theo policy.

Không viết `alias(libs.plugins...)` bên trong `pluginManagement.plugins { }`: catalog không được thiết kế để làm input trực tiếp của block này.

## 8. Plugin marker artifacts và repository giải quyết plugin

Khi build script có:

```kotlin
plugins {
    id("com.diffplug.spotless") version "8.11.0"
}
```

Gradle cần tìm **plugin marker artifact** để ánh xạ plugin ID/version thành implementation JAR. Với plugin ID `com.diffplug.spotless`, plugin marker thường theo dạng:

```text
group    = com.diffplug.spotless
name     = com.diffplug.spotless.gradle.plugin
version  = 8.11.0
```

Marker trỏ tới implementation artifact và các dependencies của nó. Chính vì vậy một Maven repository nội bộ chỉ mirror implementation JAR mà không mirror marker/artifacts liên quan có thể khiến `plugins { }` báo `Plugin ... was not found`, dù cùng implementation có trong local cache.

**Không nhầm Plugin Portal với Maven Central:**

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
```

- `gradlePluginPortal()` là plugin resolution source cho `plugins { }`.
- `mavenCentral()` là project module source cho `dependencies { implementation(...) }`.
- Nhiều plugin implementations có dependencies nằm ở các Maven repositories khác; khi xây mirror cần cấp đủ marker/implementation/transitive artifacts theo cấu hình plugin resolution.

### 8.1. Khi dùng repository riêng

Trong `settings.gradle.kts`:

```kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("https://repo.example.invalid/gradle-plugins")
        }
        gradlePluginPortal()
    }
}
```

`example.invalid` là **địa chỉ minh họa không có thật**. Gradle sẽ thử theo repository policy/order; một repository doanh nghiệp thật phải cấu hình URL/credentials và plugin marker/implementation đúng. Nếu chỉ cho phép internal plugins, có thể bỏ Portal theo security policy; không để public fallback ngoài ý muốn.

Không nhúng token vào source:

```kotlin
// Không nên:
credentials {
    username = "developer"
    password = "secret-literal"
}
```

Thay vào đó dùng Gradle Providers/secret manager, hệ thống CI credentials và policy giới hạn quyền. Với tổ chức yêu cầu plugin mirror duy nhất, khai báo rõ trong settings/approved init scripts và kiểm thử runner sạch.

## 9. `pluginManagement.resolutionStrategy`: ánh xạ ID sang module khác

Khi một plugin custom được publish **không có marker** hoặc có yêu cầu chuyển implementation, Gradle cho phép viết rule:

```kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("https://repo.example.invalid/gradle-plugins")
        }
    }
    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "com.example.quality") {
                useModule("com.example.build:quality-plugin:1.3.0")
            }
        }
    }
}
```

Đây là **mẫu cơ chế**, chưa chạy vì repository/plugin ID được dùng làm ví dụ không tồn tại. `useModule(...)` trực tiếp chỉ tọa độ plugin implementation thay vì dùng marker mặc định. Quy tắc này phải đưa đúng module thật chứa descriptor plugin, tương thích Gradle API, classpath và implementation dependencies.

Một rule khác có thể thay requested version:

```kotlin
resolutionStrategy {
    eachPlugin {
        if (requested.id.id == "com.example.quality") {
            useVersion("1.3.0")
        }
    }
}
```

Đây là **đoạn đặt bên trong `pluginManagement`**, không phải một block `resolutionStrategy` tự do đặt tại root `build.gradle.kts`. Nó có thể giúp migration version nhưng không phải công cụ bắt buộc đối với catalog. Dùng resolution rules khi có một chính sách ánh xạ đặc biệt, không dùng để âm thầm override versions của catalog mà không giải thích.

**Lưu ý security:** rules có thể đổi cả implementation module hoặc version của plugin mà build scripts yêu cầu. Review chúng như code quyết định những binary được thực thi trong configuration phase.

## 10. `apply false` và việc apply ở subproject

Root `build.gradle.kts`:

```kotlin
plugins {
    alias(libs.plugins.spotless) apply false
}
```

Subproject `app/build.gradle.kts`:

```kotlin
plugins {
    alias(libs.plugins.spotless)
}
```

Khác nhau:

- **Root request `apply false`:** plugin được resolve/đưa lên buildscript classpath phù hợp, nhưng **không apply vào root**.
- **Subproject request không `apply false`:** plugin được apply vào chính subproject ấy; task/extensions của plugin xuất hiện tại đó.
- Không có bất kỳ lời hứa nào rằng root khai báo `apply false` khiến plugin được **tự động áp dụng** vào mọi subproject.
- Root có thể không cần `apply false` nếu mỗi subproject đã request plugin đúng qua catalog.
- `apply false` không làm root project thành một “plugin repository”, cũng không tự đổi version cho những build tách biệt như `buildSrc` hoặc included build.

**Tại sao tránh `subprojects { apply(plugin = "...") }` làm mặc định?** Cách áp dụng imperative từ root có thể làm tăng cross-project configuration, khó dùng Kotlin DSL type-safe accessors và hạn chế Isolated Projects/configuration avoidance. Với nhiều module, nên để plugins block của module hoặc convention plugin quyết định plugin nào cần apply. Không phải mọi module đều cần Spotless, Android, publishing hay Kotlin compiler.

## 11. Convention plugins: chia sẻ hành vi, không chỉ version

Một catalog chỉ mô tả **tọa độ**:

```text
Spotless plugin ID = com.diffplug.spotless
Requested version  = 8.11.0
```

Nó **không tự cấu hình** `spotless { java { ... } }` giống nhau ở hai module. Trong demo ta cố ý lặp một ít cấu hình để minh họa trách nhiệm. Với nhiều module, dùng **convention plugin** để quản lý:

- Plugin nào được apply cho một loại module (Java library/application/Android).
- Java toolchain, test/report tasks, formatter conventions.
- Plugin extension defaults.
- Đường output, API/JVM compatibility, quy trình quality checks.

Kiến trúc thường dùng:

```text
main-build/
├── settings.gradle.kts
├── gradle/libs.versions.toml
├── app/build.gradle.kts
├── lib/build.gradle.kts
└── build-logic/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/kotlin/
        └── company.java-library.gradle.kts
```

Ở main `settings.gradle.kts` có thể dùng:

```kotlin
pluginManagement {
    includeBuild("build-logic")
    repositories {
        gradlePluginPortal()
    }
}
```

Đây chỉ là **trích đoạn kiến trúc**, chưa phải demo độc lập: `build-logic` phải có build script và precompiled convention plugin được khai báo đúng trước khi `plugins { id("company.java-library") }` hoạt động.

### 11.1. Giới hạn của included builds và `buildSrc`

`buildSrc` và `build-logic` included build là **những builds riêng**, không tự nhận catalog của main build. Nếu muốn dùng chung catalog tại `buildSrc`, có thể import trong `buildSrc/settings.gradle.kts`:

```kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}
```

Tương tự, một `build-logic/settings.gradle.kts` có thể import file theo relative path đúng với cấu trúc. Cần tránh import cùng catalog hai lần vào một build đã tự load từ file mặc định, và không tạo vòng giữa included builds.

**Với precompiled script plugins**, không thể tùy ý viết `alias(libs.plugins.someExternalPlugin)` trong chính plugin source file. External plugin implementation phải nằm trên classpath của **build logic build**, còn plugin source apply bằng `id("...")` khi các yêu cầu được đáp ứng. Đây là cơ chế khác so với `build.gradle.kts` của project bình thường.

**Nhắc lại:** chia sẻ catalog giúp giảm trùng tọa độ, nhưng **mỗi build vẫn có lifecycle, plugin repositories và resolution context của nó**. Một catalog không biến mọi included builds thành một build duy nhất.

## 12. Plugin version management không thay thế bảo mật

Version catalog và `pluginManagement` giúp quản trị **ID, version, repositories**, nhưng không tự xác minh bytes hay danh tính publisher.

Các rủi ro cần quản lý:

1. **Plugin namespace/capability nhầm:** plugin ID gần giống tên thật có thể được publish bởi người khác. Kiểm tra trang Plugin Portal, owner, source và release notes.
2. **Repository confusion:** nếu plugin nội bộ được hỏi ở Plugin Portal công khai, có thể resolve nhầm cùng ID/artifact theo chính sách không đủ chặt.
3. **Marker và implementation khác nguồn/không đầy đủ:** custom mirror phải có metadata và dependencies đúng, không chỉ JAR implementation.
4. **Gradle Wrapper thay đổi:** một plugin version có thể yêu cầu Gradle/JDK API mới; catalog pin plugin nhưng không bảo đảm compatibility với Wrapper.
5. **Credentials lộ:** tránh URL chứa token, secret trong TOML, build scripts hoặc logs.
6. **Supply chain:** plugin chạy trong configuration phase và có quyền thao tác build; cần nguồn đáng tin, code review và dependency verification.

**Biện pháp thực hành:**

- Pin Gradle Wrapper và plugin versions cố định được review.
- Dùng approved plugin repositories, filter internal groups khi phù hợp.
- Bật Gradle dependency verification strict với `verification-metadata.xml` cho các external dependencies/plugin artifacts được resolve trong phạm vi.
- Tách credentials/keys ra khỏi repository, giữ trong CI secret store hoặc user-home configuration an toàn.
- Dùng PR nâng plugin có test và so Git diff của TOML, plugin configuration và verification metadata.
- Không tự cho CI chạy `--refresh-dependencies` rồi chấp thuận mọi bytes mới nếu verification mismatch.

Version catalog không phải lockfile và không tự động khóa transitive dependencies của chính plugin implementation. Với build cần reproducibility, phải kiểm soát toàn bộ resolution graph, artifacts và repositories.

## 13. Một quy trình nâng version plugin an toàn

**Bước 1 — xác định nguồn version.** Nếu dùng catalog, tìm alias trong `gradle/libs.versions.toml`. Nếu dùng `pluginManagement.plugins`, xem settings và `gradle.properties`. Nếu có cả hai, document bên nào là chuẩn trước khi nâng.

**Bước 2 — xác minh plugin version tồn tại.** Đọc release notes, Gradle Plugin Portal và compatibility matrix với Gradle Wrapper/JDK/Android/Kotlin version thật của dự án. Không chọn một version chỉ vì được IDE autocomplete.

**Bước 3 — nâng một nơi duy nhất.** Với demo, đổi:

```toml
[versions]
spotless = "8.11.0"
```

thành version đã được tổ chức chấp thuận (giá trị ở đây chỉ biểu thị vị trí cần sửa, không đề xuất một version chưa xác minh).

**Bước 4 — chạy kiểm chứng:**

```bash
./gradlew :app:tasks --all
./gradlew :lib:tasks --all
./gradlew :app:spotlessCheck :lib:spotlessCheck
./gradlew :app:build :lib:build
./gradlew -q :app:run
```

**Bước 5 — kiểm tra thay đổi metadata và artifacts.** Nếu dependency verification/lockfiles báo khác, review nguồn và checksums, không tắt verification để tránh lỗi.

**Bước 6 — thử clean CI.** Kiểm tra repository access, Gradle Wrapper distribution, JDK toolchains và caches trên runner mới; lệnh chạy trên máy đã có cache không đủ chứng minh reproducibility.

**Bước 7 — rollout.** Review PR, changelog, breaking changes của plugin extension/task APIs, và theo dõi CI. Nếu thay đổi thuộc build-logic included build, nâng và test build đó riêng theo policy.

## 14. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `Unresolved reference: libs` trong settings | Version catalog alias không khả dụng trong settings plugins block | Dùng plugin ID/version tường minh cho Settings plugin, không `alias(libs.plugins...)` |
| `Plugin ... was not found` | Plugin repo thiếu marker/implementation hoặc ID/version sai | Kiểm tra `pluginManagement.repositories`, Plugin Portal và marker coordinates |
| Có `mavenCentral()` nhưng plugin không tìm được | Project libraries dùng tập repos riêng | Khai báo Plugin Portal/mirror trong `pluginManagement.repositories` |
| Subproject không có task `spotlessCheck` | Root chỉ khai báo `apply false` hoặc subproject chưa apply | Đặt `alias(libs.plugins.spotless)` trong đúng subproject |
| Hai modules chạy formatter khác phiên bản | Có plugin version hardcode ở module khác hoặc included build riêng | Thống nhất catalog/policy, rà soát mọi build riêng |
| `Plugin already on the classpath must not include a version` | Plugin đã xuất hiện trên buildscript classpath nhưng request version lại | Xem root `apply false`, legacy `buildscript`, pluginManagement và plugin ID |
| `Cannot access version catalog libs` trong `buildSrc` | BuildSrc không tự kế thừa main catalog | Import trong `buildSrc/settings.gradle.kts` với đúng relative path |
| `alias(libs.plugins.x)` fail trong precompiled script plugin | Plugin source không có accessor/apply semantics như project script | Thêm external plugin marker/implementation dependency vào build-logic classpath; apply ID |
| Gradle báo invalid TOML hoặc alias clash | TOML syntax sai, reserved alias, subgroup collision | Sửa `libs.versions.toml`, dùng alias rõ ràng/camelCase |
| Đổi TOML mà plugin không đổi | Module không dùng alias, hoặc default version ở settings bị dùng ở nơi khác | Tìm mọi `plugins { }` và nguồn version, không cho rằng alias áp dụng tự động |
| `FAIL_ON_PROJECT_REPOS` báo lỗi | Một project/plugin thêm project repository | Chuyển project dependency repos vào settings, xét exception theo policy |
| Plugin chạy trên laptop nhưng CI fail | Wrapper/JDK/proxy/credentials/cached plugin khác | Pin Wrapper, kiểm tra Plugin Portal/mirror và clean CI |
| Plugin chạy nhưng dependencies ứng dụng không resolve | Chỉ cấu hình plugin repositories, thiếu project repositories | Thêm `dependencyResolutionManagement.repositories` |
| Dependency verification fail sau nâng plugin | Plugin marker/implementation/transitives mới chưa có checksum/keys | Review artifacts rồi cập nhật verification metadata, giữ strict |
| Plugin nội bộ có binary nhưng không có marker | Publisher chưa tạo marker artifact | Dùng `java-gradle-plugin` publishing hoặc `resolutionStrategy.useModule(...)` khi cần |
| Dùng `apply false` cho core `java`/`application` | Không cần thiết, có thể dẫn tới lỗi hoặc cấu hình khó hiểu | Apply core plugin trực tiếp tại module cần nó |
| Nhiều settings/included builds dùng catalog khác nhau | Version catalogs có phạm vi theo build | Chia sẻ catalog có chủ đích và test từng included build |
| `spotlessCheck` thất bại khi có trailing whitespace | Format policy đang phát hiện vi phạm | Chạy `spotlessApply` nếu muốn sửa file, review diff rồi kiểm tra lại |

### 14.1. Quy trình debug ngắn

1. Xác nhận Gradle Wrapper/JVM bằng `./gradlew --version`.
2. Xác nhận plugin ID/version là external hay core, có thật trên Plugin Portal hoặc repository nội bộ.
3. Mở settings, kiểm tra **plugin repositories** không bị nhầm với **dependency repositories**.
4. Xem `gradle/libs.versions.toml` và những project `plugins { }` có dùng alias hay không.
5. Chạy `./gradlew :module:tasks --all` để xem plugin đã tạo các task dự kiến hay chưa.
6. Nếu plugin not found, dùng `--info`/`--stacktrace`, kiểm tra marker, credentials, mirror và firewall.
7. Nếu fail sau nâng version, xem compatibility, classpath conflict và verification metadata.
8. Với build logic riêng, kiểm tra `buildSrc`/included build catalogs/repositories.
9. Sau sửa, chạy lại một task cụ thể của plugin **và** compile/test/runtime của module thật.

## 15. Checklist nghiệm thu một cấu hình plugin tập trung

- [ ] `pluginManagement` là block đầu tiên trong `settings.gradle(.kts)`.
- [ ] Plugin repositories được khai báo rõ và đủ marker/implementation artifacts.
- [ ] Project library repositories nằm trong `dependencyResolutionManagement.repositories` nếu áp dụng mô hình tập trung.
- [ ] `repositoriesMode` được chọn có chủ đích (ví dụ `FAIL_ON_PROJECT_REPOS` cho tổ chức cần enforcement).
- [ ] External plugins có một nguồn version chuẩn: catalog `[plugins]` hoặc settings `pluginManagement.plugins`.
- [ ] Không lặp version hardcode ở từng subproject.
- [ ] Các subprojects thực sự **apply** plugin cần dùng; `apply false` ở root không thay thế điều đó.
- [ ] Core plugins không gán version external tùy ý.
- [ ] `libs.plugins.*` chỉ dùng tại project build script phù hợp; không đưa alias vào settings plugin.
- [ ] Catalog TOML có aliases rõ, không trùng reserved accessors; `libs` được auto-import đúng vị trí.
- [ ] Nếu có `buildSrc` hoặc included build, catalog và plugin repositories của build đó được cấu hình riêng khi cần.
- [ ] Plugin behavior chung dùng convention plugins thay vì quá nhiều `subprojects { apply(...) }` hoặc copy-paste extension configuration.
- [ ] Secrets không nằm trong TOML/build scripts; internal plugins có repository allowlist phù hợp.
- [ ] Gradle Wrapper/JDK/plugin compatibility và verification metadata được kiểm tra.
- [ ] Nâng plugin qua PR có test/rollback, không tự động chấp nhận artifacts mới trong CI.

## 16. Bài tập tự kiểm tra

1. **Tại sao `pluginManagement.repositories { gradlePluginPortal() }` không đủ để tải `implementation("com.google.guava:guava:...")`?** Vì project dependency repositories dùng `dependencyResolutionManagement.repositories`/`repositories` riêng.
2. **Thêm `alias(libs.plugins.spotless) apply false` ở root có làm Spotless tự apply ở `:lib` không?** Không. `:lib` phải tự request/apply hoặc dùng convention plugin phù hợp.
3. **Vì sao `alias(libs.plugins.spotless)` trong `settings.gradle.kts` sai?** Vì Gradle không cho dùng version-catalog plugin aliases trực tiếp trong settings file/settings plugin.
4. **`pluginManagement.plugins` dùng khi nào?** Khi project request plugin theo ID mà không nêu version, settings cung cấp version mặc định.
5. **TOML có `[plugins] spotless = ...` đã bảo đảm plugin có thể tải chưa?** Chưa; phải có plugin repository/marker/implementation tương ứng và quyền truy cập.
6. **Vì sao `libs.plugins.spotless` và `libs.commons.lang3` không hoán đổi?** Một là plugin ID/version alias trong `plugins`, một là module library alias trong `dependencies`.
7. **Version catalog có tự ép mọi subproject dùng Spotless không?** Không; nó cung cấp alias, mỗi project quyết định apply plugin.
8. **Một included build có tự thấy root catalog không?** Không; đó là build riêng, phải cấu hình catalog riêng hoặc import nguồn chung.
9. **Tại sao `apply false` thường không cần cho core `java`?** Core plugin có trong Gradle distribution, không cần đặt version/resolve classpath như external plugin.
10. **Bị `Plugin ... was not found` nhưng library dependencies đều tải được: tra đâu?** `pluginManagement.repositories`, plugin marker và implementation, không chỉ Maven Central của project.
11. **Dùng `resolutionStrategy.useModule(...)` có lợi nhưng nguy hiểm ở đâu?** Nó có thể đổi binary plugin implementation được tải; cần chính sách và review.
12. **Làm sao bảo đảm các module thật có cùng quy tắc formatter, không chỉ cùng version?** Dùng convention plugin chung để apply/configure Spotless thay vì chỉ có alias.

## 17. Tóm tắt

- **Settings quản lý nơi plugin được tìm và cách resolve**; `pluginManagement` phải đứng đầu settings.
- **Version catalog quản lý plugin ID/version aliases** cho `plugins { alias(libs.plugins...) }` của **project scripts**, không dùng trực tiếp trong Settings plugins block.
- **`pluginManagement.plugins` là nguồn version mặc định cho requests không nêu version**, là một chiến lược thay thế hoặc bổ sung có kiểm soát cho catalog.
- **Plugin repositories và library repositories độc lập**; `gradlePluginPortal()` không thay thế `mavenCentral()`.
- **`apply false` không apply plugin**, và root apply false không tự áp dụng cho subprojects.
- **`buildSrc` và included builds có catalog/repository context riêng**; chia sẻ catalog là thao tác cần cấu hình tường minh.
- **Convention plugins chia sẻ cấu hình và hành vi**, trong khi version catalogs chỉ chia sẻ các tọa độ.
- **Pin Wrapper + plugin versions, review metadata/keys, chạy clean CI** để vận hành tập trung an toàn.

## Tài liệu chính thức và plugin được dùng trong ví dụ

- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): `plugins { }`, `pluginManagement`, plugin version defaults, marker, resolution rules, `apply false`.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): `libs.versions.toml`, plugin aliases, giới hạn ở Settings, `buildSrc`, included builds.
- [Gradle — Centralizing Repositories](https://docs.gradle.org/current/userguide/centralizing_repositories.html): `dependencyResolutionManagement`, `repositoriesMode`.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): Plugin Portal, internal repos, content filtering và dependency confusion.
- [Gradle — Best Practices for Dependencies](https://docs.gradle.org/current/userguide/best_practices_dependencies.html): tách repos ở settings, tránh cấu hình lặp.
- [Gradle — Plugins: Introduction](https://docs.gradle.org/current/userguide/plugins.html): project/settings/init plugins và scopes.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): included builds/build logic.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): kiểm tra checksum và chữ ký của external artifacts.
- [Gradle Plugin Portal — Spotless 8.11.0](https://plugins.gradle.org/plugin/com.diffplug.spotless/8.11.0): plugin ID/version dùng trong demo.
