# Chia sẻ version catalog giữa các project và các build trong Gradle

## 1. Mục tiêu và ranh giới cần nhớ

Một **version catalog** trong Gradle gom các alias cho thư viện, plugin, bundles và các phiên bản thường dùng. Ví dụ, thay vì viết đi viết lại `"org.apache.commons:commons-lang3:3.17.0"`, nhiều module có thể dùng `libs.commons.lang3` từ một file `gradle/libs.versions.toml`.

Tuy nhiên, từ “chia sẻ” mang hai nghĩa khác nhau:

- **Giữa các project cùng một Gradle build**: `:app`, `:lib`, `:api`... thuộc cùng một `settings.gradle(.kts)`. Chúng dùng chung catalog mà **Settings của build** đã đăng ký; file chuẩn `gradle/libs.versions.toml` được Gradle tự import thành `libs`.
- **Giữa các build khác nhau**: `buildSrc`, một included build như `build-logic`, hoặc hai repository Git độc lập. Chúng có **Settings riêng**, do đó **không tự kế thừa** version catalog của main build. Cần import cùng file TOML vào Settings của từng build, hoặc publish catalog thành Maven/Ivy artifact rồi import bằng tọa độ.
- **Giữa các hệ thống phát hành**: một organization-wide catalog có thể có version riêng như `com.acme.build:company-catalog:1.0.0`. Mỗi build consumer chọn catalog version và repository để tải nó; cập nhật bản catalog gốc không tự đổi version đã pin trong các consumer.

**Bản chất:** catalog là **nơi mô tả requested versions và dependency coordinates**, không phải cơ chế ép version cuối cùng được resolve. Dependency constraints, BOM/platform, locking, conflict resolution, repositories và Gradle Wrapper vẫn có vai trò riêng.

Bài học sẽ đi từ một multi-project build chạy được với Java 17 đến `buildSrc`, included build, phân phối catalog qua Maven, plugin aliases, hạn chế của TOML và checklist QA.

## 2. Cấu trúc và cách dùng một catalog

Một catalog TOML thông thường có bốn phần:

| Mục | Công dụng | Tham chiếu trong Gradle |
| --- | --- | --- |
| `[versions]` | Đặt tên cho phiên bản. | `libs.versions.commonsLang3` |
| `[libraries]` | Alias ánh xạ tới module `group:name:version`. | `libs.commons.lang3` |
| `[bundles]` | Nhóm nhiều library aliases. | `libs.bundles.text` |
| `[plugins]` | Plugin ID và requested plugin version. | `libs.plugins.versionsReport` |

**File TOML hợp lệ — `gradle/libs.versions.toml`:**

```toml
[versions]
commonsLang3 = "3.17.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang3" }

[bundles]
text = ["commons-lang3"]
```

TOML inline table ở `commons-lang3 = { ... }` được viết **trên một dòng**, đúng quy tắc cú pháp TOML. Dạng tách group/name cũng hợp lệ nếu thay đúng một entry:

```toml
[libraries]
commons-lang3 = { group = "org.apache.commons", name = "commons-lang3", version = "3.17.0" }
```

Hai đoạn này là hai **cách thay thế** cho cùng alias, không đặt cả hai trong một file. Gradle biến alias `commons-lang3` thành accessor thường có dạng `libs.commons.lang3`. Với alias camelCase như `commonsLang3`, accessor thường là `libs.commonsLang3`.

Tại build script Kotlin DSL, một project có plugin Java có thể viết:

```kotlin
dependencies {
    implementation(libs.commons.lang3)
}
```

Trong Groovy DSL:

```groovy
dependencies {
    implementation libs.commons.lang3
}
```

Cả hai là một yêu cầu dependency tới Commons Lang3. **Catalog không tự thêm `implementation` vào mọi module**: project nào cần dependency thì project đó phải khai báo. Và **catalog không tự tạo repository**: cần `mavenCentral()` hoặc kho phù hợp trong chính build để giải quyết module ngoài.

## 3. Phạm vi thứ nhất: một multi-project build, một catalog

Giả sử project:

```text
shared-catalog-lab/
├── settings.gradle.kts
├── gradle/
│   └── libs.versions.toml
├── lib/
│   ├── build.gradle.kts
│   └── src/main/java/demo/lib/Greeting.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
```

File `gradle/libs.versions.toml` nằm tại **root build**, không đặt bản sao riêng trong `app` hay `lib`. Nó có nội dung tại mục 2.

### 3.1. Settings định nghĩa các project

**`settings.gradle.kts`:**

```kotlin
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "shared-catalog-lab"
include(":lib", ":app")
```

Không cần khai báo `create("libs") { from(files("gradle/libs.versions.toml")) }`. Gradle **tự nhận** file `gradle/libs.versions.toml` của root build thành catalog `libs`. Việc import lại `libs` thủ công trong cùng Settings có thể tạo trùng tên.

**Maven Central ở đây phục vụ module dependency**, không phải kho plugin ngoài. Vì ví dụ chỉ áp dụng core plugins Java/Application nên không cần tải external Gradle plugin.

### 3.2. Project thư viện dùng một alias từ catalog

**`lib/build.gradle.kts`:**

```kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(libs.commons.lang3)
}
```

Plugin `java-library` tạo `implementation` và cho Gradle biết artifact/variants mà thư viện công bố. Mã trong `:lib` dùng Commons Lang3 bên trong implementation; API public của ví dụ chỉ trả String nên không cần đưa Commons Lang3 sang `api`.

**`lib/src/main/java/demo/lib/Greeting.java`:**

```java
package demo.lib;

import org.apache.commons.lang3.StringUtils;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return StringUtils.capitalize("shared") + " catalog";
    }
}
```

### 3.3. Project ứng dụng dùng project dependency

**`app/build.gradle.kts`:**

```kotlin
plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.app.Main")
}

dependencies {
    implementation(project(":lib"))
}
```

**`app/src/main/java/demo/app/Main.java`:**

```java
package demo.app;

import demo.lib.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

`implementation(project(":lib"))` là **project dependency**, không phải GAV lấy từ catalog. Nó kết nối app tới variants/artifact của lib trong cùng build. Commons Lang3 là dependency runtime của lib, vì vậy có thể tham gia runtime graph của app theo metadata phù hợp.

Nếu app cũng trực tiếp dùng `StringUtils` trong code của nó, có thể khai báo thêm `implementation(libs.commons.lang3)` ở app. Đây vẫn là cùng một alias chia sẻ, nhưng dependency sẽ chỉ được thêm cho app khi app khai báo rõ.

### 3.4. Chạy và kết quả chính xác

Từ root có Gradle Wrapper và môi trường Gradle/JDK phù hợp với Java 17:

```bash
./gradlew projects
./gradlew :lib:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:compileJava
./gradlew -q :app:run
```

**Stdout của chương trình Java ở `:app:run`:**

```text
Shared catalog
```

`StringUtils.capitalize("shared")` trả `"Shared"`. Nếu chưa có Gradle Wrapper nhưng máy có Gradle cài sẵn, có thể tạo bằng `gradle wrapper` rồi dùng Wrapper; trên Windows thay `./gradlew` bằng `gradlew.bat`.

Lần đầu cần Internet để lấy Commons Lang3 ở Maven Central hoặc artifact phải có trong Gradle cache; `./gradlew -q` giảm log nhưng không thay đổi code Java.

### 3.5. Kotlin DSL và Groovy DSL dùng được cùng TOML

Thay settings bằng **`settings.gradle`**:

```groovy
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
rootProject.name = 'shared-catalog-lab'
include 'lib', 'app'
```

**`lib/build.gradle`:**

```groovy
plugins {
    id 'java-library'
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
dependencies {
    implementation libs.commons.lang3
}
```

**`app/build.gradle`:**

```groovy
plugins {
    id 'application'
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
application {
    mainClass = 'demo.app.Main'
}
dependencies {
    implementation project(':lib')
}
```

TOML và hai file Java **giữ nguyên**. Khi thực hành, chỉ chọn một kiểu build script cho mỗi vị trí; không trộn Groovy syntax vào Kotlin DSL.

### 3.6. Ý nghĩa thực sự của “chia sẻ” trong multi-project

Khi thay version Commons Lang3 trong catalog:

- Các module **dùng alias tương ứng** sẽ yêu cầu version mới khi Gradle cấu hình lại.
- Module khai báo bằng chuỗi GAV literal hoặc catalog khác **không tự thay đổi**.
- Catalog không tự thêm thư viện vào project vốn không có `implementation(libs.x)`.
- Selected version có thể khác requested version do transitive dependencies/constraints trong graph.
- Tất cả projects thuộc **cùng một build** cùng nhìn thấy các aliases của catalog được Settings import.

## 4. Phạm vi thứ hai: buildSrc không tự kế thừa catalog

`buildSrc` là build đặc biệt chứa logic xây dựng được Gradle tự biên dịch và đưa lên buildscript classpath của main build. Nó nằm dưới root về mặt thư mục, nhưng **có Settings/configuration của riêng nó**.

Cây thư mục:

```text
shared-catalog-lab/
├── gradle/libs.versions.toml
├── settings.gradle.kts
└── buildSrc/
    ├── settings.gradle.kts
    └── build.gradle.kts
```

Không có import thì `libs.commons.lang3` trong `buildSrc/build.gradle.kts` có thể là unresolved reference: phiên bản catalog của main build **không tự xuất hiện** ở buildSrc.

### 4.1. Import TOML vào Settings của buildSrc

**`buildSrc/settings.gradle.kts`:**

```kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }

    repositories {
        mavenCentral()
    }
}
```

Tham chiếu `../gradle/libs.versions.toml` được tính theo **Settings của buildSrc**, nên đi lên một cấp từ `buildSrc` rồi vào thư mục `gradle` của main build. `create("libs")` ở đây là hợp lệ vì đó là **một build riêng**, không phải khai báo trùng vào main Settings.

**`buildSrc/build.gradle.kts` — minh họa riêng:**

```kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation(libs.commons.lang3)
}
```

Cấu hình này cho thấy catalog có mặt trong buildSrc sau import. Trong dự án thực, buildSrc thường dùng `kotlin-dsl`, `groovy-gradle-plugin` hoặc code convention plugins; đó là chủ đề build logic riêng. Nếu buildSrc cần tải external Gradle plugins, nó còn cần plugin repositories của **chính buildSrc**.

**Groovy tương đương — `buildSrc/settings.gradle`:**

```groovy
dependencyResolutionManagement {
    versionCatalogs {
        create('libs') {
            from(files('../gradle/libs.versions.toml'))
        }
    }
    repositories {
        mavenCentral()
    }
}
```

**`buildSrc/build.gradle`:**

```groovy
plugins {
    id 'java-library'
}
dependencies {
    implementation libs.commons.lang3
}
```

### 4.2. Precompiled script plugin có hạn chế riêng

Một precompiled script plugin trong `buildSrc/src/main/kotlin/my-convention.gradle.kts` không dùng `plugins { alias(libs.plugins.somePlugin) }` như build script project bình thường. Plugin đó phải có implementation trên build-logic classpath và được áp dụng bằng plugin ID phù hợp trong `plugins` block.

Ở thân build logic, có thể truy cập catalog qua `VersionCatalogsExtension` của target Project khi cần:

```kotlin
// Đoạn minh họa đặt trong thân convention plugin Kotlin;
// không phải một project build script độc lập.
import org.gradle.api.artifacts.VersionCatalogsExtension

val catalog = extensions.getByType(VersionCatalogsExtension::class.java)
    .named("libs")

dependencies {
    add("implementation", catalog.findLibrary("commons-lang3").get())
}
```

`findLibrary("commons-lang3")` là API tra cứu alias; `.get()` ở đây lấy Provider từ Optional của catalog. Target project phải có configuration `implementation` (ví dụ đã apply `java` hoặc `java-library`), không thể áp dụng tùy tiện vào project bất kỳ.

**Quan trọng:** “buildSrc đã import catalog” và “precompiled script plugin được phép dùng alias trong `plugins` block” là **hai chuyện khác nhau**.

## 5. Phạm vi thứ ba: included build / composite build

Một included build được khai báo bằng `includeBuild("build-logic")` có Settings, repositories và version catalog **độc lập** với main build. Dù main build có `gradle/libs.versions.toml`, included build không tự kế thừa nó.

Ví dụ:

```text
shared-catalog-lab/
├── settings.gradle.kts
├── gradle/libs.versions.toml
└── build-logic/
    ├── settings.gradle.kts
    └── build.gradle.kts
```

Ở **main settings.gradle.kts**, bên cạnh các cấu hình chính, thêm:

```kotlin
includeBuild("build-logic")
```

**`build-logic/settings.gradle.kts`:**

```kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
    repositories {
        mavenCentral()
    }
}

rootProject.name = "build-logic"
```

**`build-logic/build.gradle.kts` — demo độc lập:**

```kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation(libs.commons.lang3)
}
```

Đây mới là một Java library build nhỏ để kiểm tra import, **chưa phải plugin build**. Nếu muốn `build-logic` cung cấp convention plugins, cần cấu hình plugin development/registrations tương ứng.

Groovy Settings của included build:

```groovy
dependencyResolutionManagement {
    versionCatalogs {
        create('libs') {
            from(files('../gradle/libs.versions.toml'))
        }
    }
    repositories {
        mavenCentral()
    }
}
rootProject.name = 'build-logic'
```

Các included builds **không tự chia sẻ** catalog, pluginManagement, repositories hoặc dependency versions với main build. `includeBuild` kết hợp các builds để Gradle có thể phối hợp dependency substitution/plugins/task relationships, **không** hợp nhất Settings của chúng.

Khi cấu trúc thực tế đặt `build-logic` ở thư mục khác, phải điều chỉnh relative path để nó trỏ chính xác tới TOML. Tránh hard-code các absolute paths cá nhân.

## 6. Hai cách chia sẻ giữa các repository độc lập

### 6.1. Chia sẻ file qua source control

Với một monorepo có nhiều builds, có thể dùng một TOML đặt ở nơi ổn định rồi cho từng build `from(files("relative/path"))` trong Settings của chính nó. Với các Git repository độc lập, có thể đồng bộ file bằng quy trình Git/submodule hoặc CI được kiểm soát.

Ưu điểm là đơn giản, không cần artifact registry; nhược điểm là **cập nhật file ở repository A không tự cập nhật repository B**. Các path `../shared-catalog` chỉ chạy khi môi trường/CI thực sự bảo đảm checkout tương ứng.

### 6.2. Publish catalog thành Maven/Ivy artifact

Với nhiều repository độc lập, một pattern phổ biến hơn là build chuyên quản lý version catalog, publish artifact `.toml` có GAV ổn định, rồi consumer import trong Settings. Mỗi consumer pin catalog version để nâng theo nhịp kiểm thử và phát hành của mình.

Đây là **cách phân phối một catalog**, không phải thay thế repository chứa thư viện Java: catalog artifact cần nơi tải riêng, còn từng module vẫn cần repository để tải actual dependencies.

## 7. Tạo và publish catalog bằng version-catalog plugin

Một repository chuyên catalog có cấu trúc:

```text
company-catalog/
├── settings.gradle.kts
├── build.gradle.kts
└── gradle/
    └── libs.versions.toml
```

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "company-catalog"
```

**`gradle/libs.versions.toml`:**

```toml
[versions]
commonsLang3 = "3.17.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang3" }

[bundles]
text = ["commons-lang3"]
```

### 7.1. Producer Kotlin DSL

**`build.gradle.kts`:**

```kotlin
plugins {
    id("version-catalog")
    id("maven-publish")
}

group = "com.acme.build"
version = "1.0.0"

catalog {
    versionCatalog {
        from(files("gradle/libs.versions.toml"))
    }
}

publishing {
    publications {
        create<MavenPublication>("catalog") {
            from(components["versionCatalog"])
        }
    }
    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-catalogs")
        }
    }
}
```

URL ở trên là **địa chỉ minh họa**, không phải endpoint thật; chỉ chạy publish sau khi thay bằng repository có quyền truy cập và cấu hình credential/CI secret an toàn.

- `version-catalog` cung cấp `catalog { versionCatalog { ... } }` và component `versionCatalog`.
- `maven-publish` cung cấp `MavenPublication` và task publish.
- `from(files(...))` đưa TOML vào **catalog extension của plugin publish**, không phải đăng ký lại catalog ở Settings của main build.
- `group` + tên project `company-catalog` + `version` cho GAV mặc định `com.acme.build:company-catalog:1.0.0`, nếu không sửa artifactId của publication.
- `publishing.repositories` xác định **đích upload**; consumer cần `dependencyResolutionManagement.repositories` để **tải** artifact.

Các lệnh:

```bash
./gradlew generateCatalogAsToml
./gradlew publish
```

`generateCatalogAsToml` sinh/catalog TOML output do plugin quản lý; `publish` đưa publication lên repository được cấu hình. Phải kiểm tra repository thật, version và credentials; không có server hợp lệ thì ví dụ publish này **không thể chạy hoàn chỉnh**. Ở đây phần quan trọng là **cách cấu hình** và artifact mà nó tạo.

### 7.2. Producer Groovy DSL

**`settings.gradle`:**

```groovy
rootProject.name = 'company-catalog'
```

**`build.gradle`:**

```groovy
plugins {
    id 'version-catalog'
    id 'maven-publish'
}

group = 'com.acme.build'
version = '1.0.0'

catalog {
    versionCatalog {
        from(files('gradle/libs.versions.toml'))
    }
}

publishing {
    publications {
        catalog(MavenPublication) {
            from components.versionCatalog
        }
    }
    repositories {
        maven {
            url = uri('https://repo.example.org/gradle-catalogs')
        }
    }
}
```

Một cách khác là định nghĩa aliases bằng code bên trong `catalog.versionCatalog` của plugin publish. Tuy nhiên, nếu muốn vừa dùng catalog cho main build vừa publish, **giữ TOML là một nguồn dữ liệu** thường dễ kiểm tra thay vì khai báo cùng aliases ở hai nơi.

## 8. Consumer import published catalog trong Settings

Giả sử repository `service-app` không có file `gradle/libs.versions.toml`. Có thể dùng published catalog với tên `libs`.

**`settings.gradle.kts`:**

```kotlin
dependencyResolutionManagement {
    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-catalogs")
        }
        mavenCentral()
    }
    versionCatalogs {
        create("libs") {
            from("com.acme.build:company-catalog:1.0.0")
        }
    }
}

rootProject.name = "service-app"
```

`from("com.acme.build:company-catalog:1.0.0")` yêu cầu Gradle lấy **catalog artifact** từ kho trong dependencyResolutionManagement và tạo accessors cho build này. Sau import:

```kotlin
// build.gradle.kts
plugins {
    id("java")
}

dependencies {
    implementation(libs.commons.lang3)
}
```

Nếu artifact catalog không được publish, sai GAV, thiếu credential hoặc thiếu repository, consumer sẽ lỗi khi import; cần chẩn đoán đúng nguồn, không sửa `implementation` bằng cách thêm GAV giả.

**`settings.gradle` Groovy:**

```groovy
dependencyResolutionManagement {
    repositories {
        maven {
            url = uri('https://repo.example.org/gradle-catalogs')
        }
        mavenCentral()
    }
    versionCatalogs {
        create('libs') {
            from('com.acme.build:company-catalog:1.0.0')
        }
    }
}
rootProject.name = 'service-app'
```

Build script Groovy:

```groovy
plugins {
    id 'java'
}
dependencies {
    implementation libs.commons.lang3
}
```

### 8.1. Nếu consumer đã có libs.versions.toml local

Khi consumer có `gradle/libs.versions.toml`, Gradle **đã tạo** catalog `libs`. Không tạo thêm `create("libs")` cho published catalog. Đặt tên khác, ví dụ `orgLibs`:

```kotlin
dependencyResolutionManagement {
    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-catalogs")
        }
        mavenCentral()
    }

    versionCatalogs {
        create("orgLibs") {
            from("com.acme.build:company-catalog:1.0.0")
        }
    }
}
```

Sau đó:

```kotlin
dependencies {
    implementation(orgLibs.commons.lang3)
}
```

Cách này cho phép **catalog local** (`libs`) và **catalog tổ chức** (`orgLibs`) sống cạnh nhau. Nhưng hai catalog **không tự chia sẻ `version.ref`** hay requested versions: phải quản trị trùng lặp có chủ đích.

## 9. Import TOML từ một file ngoài thư mục chuẩn

Nếu một build không có `gradle/libs.versions.toml` hoặc muốn thêm một catalog có tên mới, khai báo tại Settings:

**Kotlin:**

```kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("toolsLibs") {
            from(files("gradle/tools.versions.toml"))
        }
    }
}
```

**Groovy:**

```groovy
dependencyResolutionManagement {
    versionCatalogs {
        create('toolsLibs') {
            from(files('gradle/tools.versions.toml'))
        }
    }
}
```

Đường dẫn tệp ở đây là path theo ngữ cảnh Settings của **build hiện tại**. Một build khác muốn import file này phải có path đúng của chính nó. Không tự suy ra rằng `../gradle` luôn là main root nếu build được checkout ở vị trí khác.

### 9.1. Quy tắc “một from, một file”

Theo Gradle, một builder catalog chỉ được gọi `from(...)` **một lần**. Khi dùng `files(...)`, nó phải chỉ tới **một file duy nhất**.

**Sai — không dùng trong build thật:**

```kotlin
versionCatalogs {
    create("combinedLibs") {
        from(files("gradle/a.versions.toml"))
        from(files("gradle/b.versions.toml"))
    }
}
```

Cách đúng: dùng **hai catalogs khác tên** hoặc **gộp vào một TOML** trước khi import, hoặc dùng builder API bổ sung entries sau lần import đã có.

**Hai catalogs cùng build:**

```kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("toolsLibs") {
            from(files("gradle/tools.versions.toml"))
        }
        create("testLibs") {
            from(files("gradle/test.versions.toml"))
        }
    }
}
```

Catalog `libs` chuẩn ở root vẫn có thể tồn tại đồng thời. Để tránh tên xung đột, dùng các tên rõ phạm vi như `toolsLibs`, `testLibs`, `orgLibs`.

### 9.2. Không có cross-catalog include trong TOML

Không thể viết một `version.ref` trong `tools.versions.toml` mà nó tự trỏ vào `[versions]` của `libs.versions.toml`. Các catalogs **độc lập**.

Nếu phải dùng một version chung ở nhiều catalogs, có thể:

- Dùng chung **một catalog TOML** khi không có ranh giới bắt buộc.
- Giữ mỗi catalog tự đầy đủ và kiểm tra consistency bằng CI.
- Import published catalog rồi bổ sung/override entries có chủ đích bằng builder API.
- Đọc shared properties và gọi `version(...)` vào từng catalog trong Settings nếu có quy trình quản trị dữ liệu.

Tránh tưởng rằng gọi `from` hai lần sẽ merge hai file: Gradle cố ý không cho một builder import nhiều nguồn bằng cách đó.

## 10. Override version trong build consumer

Một build dùng published catalog có thể đổi một version alias **chỉ trong bản catalog của mình**:

```kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("orgLibs") {
            from("com.acme.build:company-catalog:1.0.0")
            version("commonsLang3", "3.17.0")
        }
    }
}
```

Đoạn này là phần `versionCatalogs` trong Settings; khi thật sự import Maven artifact cần `repositories` thích hợp như mục 8.

`commonsLang3` là **version alias**; nó không phải library alias `commons-lang3`. Những library entries có `version.ref = "commonsLang3"` sẽ dùng requested version override. Entries ghi phiên bản trực tiếp không tự được thay đổi.

Groovy:

```groovy
dependencyResolutionManagement {
    versionCatalogs {
        create('orgLibs') {
            from('com.acme.build:company-catalog:1.0.0')
            version('commonsLang3', '3.17.0')
        }
    }
}
```

Override **không sửa** artifact đã publish, và **không ép** final resolved version khi graph còn constraints/conflicts. Trong team, mỗi override nên có lý do, kiểm thử và kế hoạch quay lại standard version.

## 11. Plugin aliases: chia sẻ thông tin nhưng không chia sẻ plugin repositories

Bên cạnh libraries, TOML có thể chứa plugin aliases:

```toml
[versions]
versionsPlugin = "0.52.0"

[plugins]
versionsReport = { id = "com.github.ben-manes.versions", version.ref = "versionsPlugin" }
```

**Kotlin build.gradle.kts:**

```kotlin
plugins {
    alias(libs.plugins.versionsReport)
}
```

**Groovy build.gradle:**

```groovy
plugins {
    alias(libs.plugins.versionsReport)
}
```

Đây là **đoạn minh họa plugin bên ngoài**, không thuộc phần runnable Java 17 ở mục 3. Cần plugin ID/version được publish, Gradle Wrapper tương thích và plugin repository hợp lệ.

Ghi nhớ:

- Catalog `[plugins]` lưu **plugin ID/version**, **không** lưu repository mà Gradle dùng tải plugin.
- `pluginManagement.repositories` phải được cấu hình đúng cho external plugins.
- Plugin aliases của catalog **không sử dụng trực tiếp trong Settings plugins block/settings plugin**.
- Trong `plugins` block của **precompiled script plugins**, không thể áp dụng `alias(libs.plugins...)` hệt như project bình thường. Cần đưa plugin implementation lên build-logic classpath rồi apply ID.
- Core plugins như `java`, `application` có thể dùng trực tiếp `id("java")`, không cần external plugin version.

## 12. Catalog khác dependency platform/BOM ở đâu?

Khi team cần thống nhất dependency, nhiều người nhầm version catalog với Maven BOM hoặc Gradle Java platform.

| Version catalog | Platform/BOM |
| --- | --- |
| Quản lý aliases và **requested** versions trong Settings/TOML. | Công bố **dependency constraints** cho dependency graph. |
| Giúp các project cùng viết dependency coordinates dễ hiểu. | Có thể align/giới hạn resolved versions trong graph khi được khai báo. |
| Không tự thêm thư viện vào project không khai báo. | Project cần khai báo `platform(...)` hoặc dependency platform tương ứng. |
| Không bảo đảm phiên bản cuối cùng luôn đúng TOML. | Mức độ ràng buộc phụ thuộc loại platform/constraints, ví dụ enforced vs ordinary. |
| Có thể publish catalog dưới dạng TOML artifact. | Có thể publish platform component bằng plugin/mô hình platform. |

Ví dụ cấu hình tham chiếu một platform giả định:

```kotlin
dependencies {
    implementation(platform("com.acme:java-platform:1.0.0"))
    implementation(libs.commons.lang3)
}
```

`com.acme:java-platform:1.0.0` chỉ là **tọa độ minh họa**, không được bảo đảm tồn tại. Không copy lệnh này vào demo Java trước khi thực sự có artifact platform.

**Quy tắc:** catalog làm rõ “muốn dùng gì và yêu cầu version nào”; dependency resolution, constraints, locking, verification, repositories và platform mới quyết định “thực sự lấy gì, từ đâu, có được chấp nhận không”.

## 13. Chẩn đoán bằng các lệnh Gradle

### 13.1. Multi-project demo

```bash
./gradlew --version
./gradlew projects
./gradlew :lib:dependencies --configuration compileClasspath
./gradlew :lib:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew -q :app:run
```

Kỳ vọng:

1. `projects` liệt kê `:lib` và `:app`.
2. Commons Lang3 xuất hiện trong dependency graph của `:lib` theo alias.
3. `:app` có project dependency `:lib`, và runtime graph có thể kéo theo Commons Lang3.
4. `:app:run` in đúng `Shared catalog`.
5. `dependencyInsight` giải thích requested/selected version nếu có conflicts, không phải công cụ duy nhất xác định repository URL.

Với Java 17, để biên dịch thủ công **khi đã có JAR hợp lệ** ở `third-party/commons-lang3-3.17.0.jar`:

```bash
mkdir -p out
javac -cp third-party/commons-lang3-3.17.0.jar -d out lib/src/main/java/demo/lib/Greeting.java
javac -cp out -d out app/src/main/java/demo/app/Main.java
java -cp "out:third-party/commons-lang3-3.17.0.jar" demo.app.Main
```

Trên Windows, dùng `;` thay `:` trong classpath của `java -cp`. Stdout:

```text
Shared catalog
```

Các lệnh `javac` trên không tải thư viện: chúng chỉ chạy khi JAR đã được chuẩn bị trước. Đây là minh họa phân biệt **catalog là metadata của Gradle** với **classpath file thật của javac/java**.

### 13.2. buildSrc/included build

Trong main build, `./gradlew help` có thể kích hoạt buildSrc. Nếu muốn xem dependency của included build độc lập:

```bash
./gradlew -p build-logic dependencies --configuration runtimeClasspath
```

Điều kiện: cấu trúc `build-logic` phù hợp ví dụ ở mục 5 và Gradle nhận nó như build riêng; dùng `build-logic/settings.gradle.kts` để xác định cách import catalog của chính nó.

Không gõ `./gradlew :buildSrc:dependencies` như thể `buildSrc` là project `:buildSrc` của main build. `buildSrc` là một build đặc biệt, không được tự động thêm vào danh sách `include(":...")`.

### 13.3. Published catalog

Trước khi khai báo hoàn tất release, kiểm tra producer publication GAV, TOML, và repository đã upload. Ở consumer, kiểm tra `settings.gradle(.kts)` đang import đúng tọa độ, dùng repository có quyền read, không tạo duplicate `libs` và các aliases được tạo.

Để so sánh hai builds đang dùng version catalog giống nhau hay không, đọc **catalog version coordinates** hoặc TOML source và kiểm tra **resolved dependency graph**; đừng chỉ so sánh tên accessor `libs.x`.

## 14. Bảng lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `Unresolved reference: libs` trong buildSrc | buildSrc không tự import main catalog. | Thêm import trong `buildSrc/settings.gradle.kts`. |
| `Unresolved reference: libs` trong included build | Included build có Settings riêng. | Import TOML hoặc published catalog trong Settings của included build. |
| Tạo `libs` trùng trong main build | Có file mặc định `gradle/libs.versions.toml` và gọi thêm `create("libs")`. | Bỏ khai báo trùng hoặc đặt catalog mới thành `orgLibs`. |
| `from(...)` báo gọi hai lần | Một builder import nhiều nguồn. | Mỗi builder chỉ một `from`; tách catalogs hoặc gộp TOML. |
| Catalog file path không tồn tại | Relative path sai từ Settings của build đang cấu hình. | Kiểm tra chính xác cấu trúc thư mục/checkout. |
| Import catalog published bị lỗi not found | Chưa publish, sai GAV, repo hoặc credentials. | Kiểm tra publication và `dependencyResolutionManagement.repositories`. |
| Alias có nhưng library vẫn not found | Catalog chỉ định coordinates, không tự thêm repo chứa thư viện. | Thêm repository module phù hợp, kiểm tra version thực. |
| Plugin alias không tìm được | Plugin repository/mapping/version sai. | Kiểm tra `pluginManagement.repositories` và plugin ID/version. |
| Plugins block của precompiled script plugin báo lỗi alias | Hạn chế của precompiled script plugin DSL. | Dùng plugin ID và build-logic dependency classpath. |
| `version.ref` trong catalog thứ hai không nhận | Catalogs độc lập, không cross-reference. | Cung cấp alias version trong chính catalog đó hoặc dùng builder injection. |
| Hai project cùng catalog nhưng chọn version khác | Khác dependency graph, constraints hoặc platform. | Dùng `dependencyInsight` và kiểm tra graph. |
| TOML báo lỗi parse | Inline table nhiều dòng/sai dấu ngoặc, alias trùng. | Viết đúng TOML, mỗi inline table một dòng. |
| Catalog publish thành công nhưng consumer cũ không thay đổi | Consumer vẫn pin catalog version cũ. | Phát hành version mới và cập nhật GAV ở consumer. |
| CI khác laptop | Khác Gradle Wrapper, credentials, network, checkout hoặc cache. | Cố định Wrapper, kiểm tra permission và chạy clean CI. |

## 15. Quy trình triển khai cho team

1. Xác định phạm vi: **một multi-project build** chỉ cần file `gradle/libs.versions.toml`; **nhiều builds** cần import riêng hoặc publish.
2. Chọn nguồn gốc duy nhất của entries, ưu tiên TOML có lịch sử Git rõ ràng.
3. Đặt aliases có ý nghĩa; tránh tên tạo accessor mơ hồ, tên trùng hoặc quá nhiều catalogs không cần thiết.
4. Với `buildSrc` và `build-logic`, import file TOML trong **Settings riêng** của mỗi build; không cho rằng main Settings tự truyền dữ liệu.
5. Nếu nhiều repository độc lập, sử dụng một producer áp dụng `version-catalog`/`maven-publish`, phát hành version không thay đổi ngầm.
6. Mỗi consumer import GAV rõ ràng và cấu hình repository/credentials; không hard-code secrets.
7. Nếu consumer có local `libs`, thêm `orgLibs` thay vì khai báo cùng tên.
8. Review version overrides, không để “chia sẻ” che giấu những lệch version không có lý do.
9. Chạy các task `dependencies`, `dependencyInsight`, compile/test/run, dùng CI và Gradle Wrapper.
10. Tách biệt mục đích: catalog quản lý notation; platform/locking/verification/repository policy quản lý hành vi resolution và provenance.

## 16. Tra nhanh

| Mục tiêu | Cách làm |
| --- | --- |
| `:app` và `:lib` cùng build dùng một catalog | Đặt `gradle/libs.versions.toml` ở root; truy cập `libs.x` trong cả hai project. |
| buildSrc dùng catalog của main build | Trong `buildSrc/settings.gradle(.kts)`: `from(files("../gradle/libs.versions.toml"))`. |
| Included build dùng catalog của main build | Trong `build-logic/settings.gradle(.kts)`: import tường minh TOML hoặc published catalog. |
| Nhiều Git repositories chia sẻ catalog có version rõ ràng | Publish artifact với `version-catalog` và `maven-publish`. |
| Consumer lấy published catalog | Settings `dependencyResolutionManagement.versionCatalogs { create(...) { from("g:a:v") } }`. |
| Consumer đã có local `libs` | Tạo catalog `orgLibs`, không tạo `libs` lần hai. |
| Tách tools/test thành catalogs riêng | Mỗi catalog một tên và một file TOML. |
| Gộp hai TOML bằng hai lần `from` | Không hỗ trợ; gộp file hoặc dùng catalogs/builder riêng. |
| Cần ép resolved version | Dùng constraints, platform/BOM hoặc locking, không dựa riêng vào catalog. |
| Cần cùng plugin versions ở các project | Dùng plugin aliases ở project build script, cấu hình plugin repositories độc lập. |

**Kết luận:** Các **project cùng build** chia sẻ catalog từ Settings của build; các **build khác nhau** (kể cả buildSrc và included builds) **không tự kế thừa** catalog. Hai cách chia sẻ bền vững là import cùng TOML vào từng build hoặc phân phối catalog dạng Maven artifact có version. Dù dùng cách nào, hãy nhớ catalog chỉ biểu diễn yêu cầu dependency/plugin; nơi tải artifact, việc chọn version thực tế và chất lượng build vẫn cần kiểm chứng riêng.

### Tài liệu Gradle chính thức

- [Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html) — alias, TOML, imports, buildSrc và publication.
- [Dependency Management Basics](https://docs.gradle.org/current/userguide/dependency_management_basics.html) — quản lý dependencies trong multi-project build.
- [Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html) — phạm vi độc lập của included builds.
- [Sharing Build Logic Using buildSrc](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html) — vai trò buildSrc.
- [Version Catalog Plugin](https://docs.gradle.org/current/userguide/version_catalog_plugin.html) — plugin, component và tasks publish catalog.
