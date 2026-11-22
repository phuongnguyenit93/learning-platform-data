# Chẩn đoán plugin không tìm thấy, xung đột classpath và sai phiên bản trong Gradle

## 1. Vì sao lỗi plugin thường xuất hiện trước cả khi biên dịch Java?

Plugin là thành phần mở rộng **chính Gradle build**: nó có thể tạo task, configuration, extension và quy tắc xử lý project. Trước khi thực hiện `compileJava` hoặc `test`, Gradle phải đọc settings/build scripts, **giải quyết plugin request**, đưa mã plugin vào classpath thích hợp rồi **áp dụng plugin**.

Vì vậy, một lỗi ở khối `plugins { ... }` có thể khiến build thất bại ngay khi chạy `./gradlew help`, dù mã Java hoàn toàn hợp lệ.

Ba nhóm lỗi cần phân biệt:

1. **Plugin không tìm thấy (not found / unknown plugin):** Gradle không xác định được plugin ID/phiên bản hoặc không tải được plugin marker/implementation ở các nguồn đã cấu hình.
2. **Xung đột plugin classpath:** plugin đã được đưa vào classpath từ một đường khác, nhưng build lại yêu cầu phiên bản không phù hợp hoặc Gradle không thể xác nhận phiên bản đã có; cũng có thể có xung đột các thư viện mà plugin sử dụng.
3. **Sai phiên bản/tương thích:** plugin tồn tại và được tải về, nhưng phiên bản plugin, phiên bản Gradle Wrapper, JVM chạy Gradle, API plugin hoặc môi trường thực thi không tương thích.

Các lỗi này **không đồng nghĩa** với dependency Java của ứng dụng bị thiếu. Thêm `implementation("...")` vào dependency của app sẽ không tự sửa việc Gradle chưa tải được một plugin được khai báo trong `plugins`.

Mô hình phân tích:

```text
settings.gradle(.kts)
    |
    +--> pluginManagement.repositories / resolutionStrategy / includeBuild
    |
    v
plugins { id("...") version "..." }
    |
    +-- 1. Có nhận ra plugin ID và nguồn không?
    |       Không -> lỗi plugin not found / missing version / marker
    |
    +-- 2. Có giải quyết được artifact và classpath không?
    |       Không -> lỗi network, credentials, artifact, xung đột version
    |
    +-- 3. Có áp dụng được plugin vào đúng target không?
    |       Không -> lỗi tương thích Gradle API/JVM/extension/loại plugin
    |
    v
Project model: tasks, configurations, extensions
    |
    v
compileJava / test / run / các task khác
```

Sơ đồ mô tả cách chẩn đoán; không phải mọi Gradle phiên bản đều in đúng những dòng log này. Trong thực tế cần đọc **lỗi đầu tiên có ý nghĩa**, phần `What went wrong` và `Caused by` trong stacktrace.

## 2. Phân biệt plugin Gradle và thư viện Java

| Đặc điểm | Plugin dùng trong build | Thư viện ứng dụng |
| --- | --- | --- |
| Mục đích | Mở rộng build logic của Gradle | Cung cấp class/API cho Java code |
| Ví dụ | `application`, `java-library`, `io.github.ben-manes.versions` | `org.apache.commons:commons-lang3:3.14.0` |
| Cách khai báo hiện đại | `plugins { id("...") version "..." }` | `dependencies { implementation("...") }` |
| Nguồn thường dùng | `pluginManagement.repositories` và included plugin builds | `dependencyResolutionManagement.repositories` hoặc `repositories` |
| Thời điểm có thể lỗi | Trong settings/build configuration, trước task | Khi configuration cần dependency được resolve hoặc task chạy |
| Cú pháp version | Plugin ID + version (với external plugin cần biết version) | Group + artifact + version hoặc version constraint |
| Dùng `dependencyInsight`? | Không phải công cụ chính để giải quyết plugin request | Rất hữu ích cho dependency graph của app |
| Dùng `buildEnvironment`? | Có thể xem buildscript classpath, đặc biệt với legacy plugin application | Không thay thế `dependencies --configuration ...` |

Hai câu sau khác nhau:

```kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.67.0"
}
```

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Khối thứ nhất yêu cầu **plugin để chạy build**. Khối thứ hai yêu cầu **thư viện trên classpath Java**. Chúng có thể sử dụng những repository khác nhau.

### 2.1. Core plugins không cần tải từ Plugin Portal

Plugin tích hợp của Gradle như `java`, `java-library`, `application`, `base` có thể được áp dụng trực tiếp:

```kotlin
plugins {
    application
}
```

Hoặc:

```kotlin
plugins {
    id("java")
}
```

**Không gắn phiên bản tùy ý cho core plugin.** Ví dụ `id("java") version "1.0"` là yêu cầu sai về ý nghĩa: core plugin đã đi kèm Gradle distribution, không cần một phiên bản độc lập trên Plugin Portal.

Nếu `application { ... }` hoặc `implementation(...)` báo không tồn tại, hãy xác nhận project đã áp dụng plugin tạo extension/configuration tương ứng, thay vì vội thêm Maven repository.

## 3. Plugin ID, version, marker artifact và implementation artifact

Trong DSL `plugins`:

```kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.67.0"
}
```

Gradle nhận **plugin ID** và **plugin version**, chứ không trực tiếp nhận tọa độ Maven của JAR thực thi. Với plugin bên ngoài được publish theo cơ chế chuẩn, nó có thể tìm **plugin marker artifact**. Theo quy ước Maven, marker có dạng:

```text
group    = <plugin-id>
artifact = <plugin-id>.gradle.plugin
version  = <plugin-version>
```

Với ví dụ trên:

```text
io.github.ben-manes.versions:
io.github.ben-manes.versions.gradle.plugin:
0.67.0
```

Marker thường là metadata/POM hướng tới artifact thực thi plugin và các dependency kèm theo; **marker không nhất thiết là JAR chứa lớp plugin**.

Điểm thực tế:

- Repository plugin phải phục vụ **marker và artifact triển khai**, hoặc build phải cung cấp mapping thích hợp qua `pluginManagement.resolutionStrategy`.
- Một kho Maven chỉ có JAR triển khai nhưng **không có marker đúng plugin ID/version** có thể khiến `plugins` báo không tìm thấy plugin.
- Nếu marker tìm được nhưng artifact triển khai/transitive dependency bị thiếu hoặc không tải được, lỗi có thể ở bước giải quyết classpath.
- Một ID Java package và Maven group trông giống nhau **không có nghĩa** chúng cùng một tọa độ.

Không nên thử đoán bừa Maven coordinates từ plugin ID rồi thêm `implementation(...)` vào ứng dụng. Đây là hai classpath phục vụ hai mục đích khác nhau.

### 3.1. Plugin request hợp lệ nhưng marker bị thiếu

Giả sử một kho công ty phát hành plugin thực thi `com.acme.gradle:build-rules-plugin:1.2.3`, nhưng không publish marker cho ID `com.acme.build.rules`. Khi đó, một giải pháp **có kiểm soát** là mapping plugin ID thành artifact:

```kotlin
// settings.gradle.kts: ví dụ riêng, URL/tọa độ là giả định.
pluginManagement {
    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-plugins")
        }
        gradlePluginPortal()
    }
    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "com.acme.build.rules") {
                useModule("com.acme.gradle:build-rules-plugin:1.2.3")
            }
        }
    }
}
```

Đoạn trên **không chạy độc lập nếu kho giả không tồn tại**. Nó minh họa nơi sửa lỗi marker; artifact đích vẫn phải chứa plugin descriptor/implementation phù hợp, server phải cho quyền truy cập và plugin phải tương thích với Gradle đang dùng.

Không sử dụng `useModule` như cách “bỏ qua bảo mật”: nó chỉ thay quy tắc ánh xạ từ ID sang artifact, không xác nhận nội dung artifact là đáng tin.

## 4. Hai tập repository dễ bị nhầm

Gradle có **luồng giải quyết plugin** riêng với **luồng giải quyết dependency của ứng dụng**.

**`settings.gradle.kts` đúng mục đích:**

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

rootProject.name = "plugin-diagnostic-lab"
include("app")
```

- `pluginManagement.repositories`: nơi Gradle tìm plugin bên ngoài cho khối `plugins`. Plugin Portal là nguồn phổ biến; có thể thêm Google Maven hoặc kho nội bộ nếu plugin yêu cầu.
- `dependencyResolutionManagement.repositories`: nơi Gradle tìm dependency thông thường của các project, ví dụ commons-lang3.
- `publishing.repositories`: nơi **đẩy artifact** khi publish; không tự biến thành plugin repository để tải dependency.
- `buildscript.repositories`: repository của buildscript classpath theo cách áp dụng plugin legacy; khác luồng `plugins` hiện đại.

**Sai lầm rất phổ biến:** thêm `mavenCentral()` vào `repositories` của `app/build.gradle.kts` rồi mong lỗi `Plugin not found` tự biến mất. Nếu plugin đang được resolve bằng `plugins`, cần kiểm tra `pluginManagement` và marker/implementation.

### 4.1. Gradle Plugin Portal có phải Maven Central không?

Không. Plugin Portal là dịch vụ/kho phục vụ plugin marker và các artifact liên quan. Maven Central là repository phổ biến cho thư viện JVM. Cùng một plugin có thể có artifact triển khai ở nơi khác marker, và cấu hình resolution có thể yêu cầu nhiều repository phù hợp.

Khi plugin của Android cần Google Maven, một cấu hình thường gặp trong build Android là:

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
```

Đây là **cấu hình minh họa cho Android build**, không phải yêu cầu cho project Java thuần ở mục 9. Chỉ thêm những kho bạn thực sự tin cậy/cần dùng và tuân thủ policy của tổ chức.

### 4.2. Thứ tự và policy repository có ý nghĩa

Khi nhiều plugin repositories được khai báo, thứ tự, khả năng truy cập và marker/implementation quyết định việc resolve. Không nên đưa kho lạ lên đầu danh sách chỉ để “thử xem có hết lỗi không”; Gradle plugin chạy code với quyền của build, nên nguồn plugin phải được đánh giá cẩn thận.

Với kho nội bộ, kiểm tra:

1. URL repository, HTTPS/TLS và proxy.
2. Quyền đọc marker artifact và implementation artifact.
3. Nếu kho là proxy, upstream Gradle Plugin Portal/Maven cần được cấu hình đúng.
4. Chính sách publish marker khi tạo plugin bằng `java-gradle-plugin`.
5. Xác thực qua secret/CI environment, không ghi token vào Git.

## 5. Lỗi plugin “not found”: phân loại trước khi sửa

Một số thông báo thường gặp (diễn đạt có thể thay đổi theo Gradle version):

```text
Plugin [id: 'com.example.missing', version: '1.0.0']
was not found in any of the following sources
```

Hoặc:

```text
Plugin [id: 'io.github.ben-manes.versions']
was not found ...
Plugin Repositories (plugin dependency must include a version number...)
```

Các nguyên nhân có thể khác nhau:

| Nguyên nhân | Dấu hiệu | Hướng khắc phục |
| --- | --- | --- |
| Viết sai plugin ID | Plugin Portal hoặc tài liệu plugin ghi ID khác | Kiểm tra ID chính xác và namespace của plugin |
| Bỏ version của external plugin | Request ID không có version và không có mặc định trong `pluginManagement`/classpath | Khai báo version một lần đúng nơi |
| Version chưa được publish | Plugin ID đúng nhưng marker/version không tìm thấy | Chọn version thật, đã công bố và tương thích |
| Repository plugin không đúng | Chỉ có Maven Central trong project repositories | Sửa `pluginManagement.repositories` |
| Kho không có plugin marker | Có JAR triển khai nhưng thiếu marker ID/version | Publish marker hoặc mapping `useModule` hợp lệ |
| Plugin nằm trong included build nhưng chưa include | ID convention plugin không được nhận diện | Dùng `pluginManagement.includeBuild("build-logic")` ở settings |
| Lỗi proxy/TLS/401/403 | Không tải được metadata/artifact | Kiểm tra mạng, chứng chỉ, quyền |
| Đang dùng `--offline` khi chưa cache | Gradle không có đủ marker/implementation trong cache | Chạy online hợp lệ hoặc chuẩn bị cache |
| Viết sai ngữ cảnh plugin | Settings plugin áp dụng ở project hoặc ngược lại | Dùng đúng loại target/settings/project |

**Thứ tự kiểm tra:** đọc plugin ID + version trong thông báo → xem ID/version có thật không → xem plugin repositories thực tế → xem mạng/credential/cache → chỉ sau đó mới nghi ngờ một lỗi của mã plugin.

### 5.1. Plugin version có thể lấy từ đâu?

Với plugin bên ngoài, version có thể được đặt ở chính request:

```kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.67.0"
}
```

Hoặc làm mặc định trong `pluginManagement`:

```kotlin
// settings.gradle.kts: cấu hình thay thế cho cách trên.
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
    plugins {
        id("io.github.ben-manes.versions") version "0.67.0"
    }
}
```

Khi đã khai báo default đúng theo `pluginManagement`, project có thể yêu cầu ID mà không ghi version:

```kotlin
plugins {
    id("io.github.ben-manes.versions")
}
```

Đây là **hai phương án khác nhau**, không phải ba mảnh code cần dán cùng lúc. Hãy chọn một nơi sở hữu version để tránh tình trạng một module xin `0.67.0`, module khác lại xin `0.65.0`.

### 5.2. Alias trong version catalog cũng tạo plugin request

TOML:

```toml
[plugins]
versions = { id = "io.github.ben-manes.versions", version = "0.67.0" }
```

Trong project:

```kotlin
plugins {
    alias(libs.plugins.versions)
}
```

Catalog giúp tên/version nhất quán, nhưng **không tự tải plugin** và không thay cấu hình plugin repositories. Khi lỗi, hãy đọc **ID/version thật mà alias trỏ tới**, không chỉ tên alias `versions`.

## 6. Xung đột plugin classpath: “đã có plugin với phiên bản khác”

Một lỗi điển hình khi nhiều module hoặc build logic cố khai báo phiên bản plugin riêng:

```text
The request for this plugin could not be satisfied because
the plugin is already on the classpath with a different version
```

Thông báo có thể cho biết phiên bản đã có, hoặc trong một tình huống khác:

```text
The plugin is already on the classpath with an unknown version,
so compatibility cannot be checked
```

Hai dạng trên **không** có nghĩa Java application đang có hai version commons-lang3. Đây là vấn đề plugin được nạp vào **build/plugin classpath**, trước khi lập runtime classpath cho Java app.

### 6.1. Tình huống root đã khai báo một version

**Root `build.gradle.kts`:**

```kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.67.0" apply false
}
```

**Child `app/build.gradle.kts` — ví dụ cố ý sai:**

```kotlin
plugins {
    application
    id("io.github.ben-manes.versions") version "0.65.0"
}
```

Root đã đưa plugin version `0.67.0` vào classpath chung theo cơ chế `apply false`, nhưng child yêu cầu version `0.65.0`. Gradle có thể từ chối ngay khi giải quyết plugin request vì **đã có plugin ở version khác trên classpath**.

**Child `app/build.gradle.kts` — phương án phù hợp:**

```kotlin
plugins {
    application
    id("io.github.ben-manes.versions")
}
```

Version được sở hữu ở root, child chỉ yêu cầu **áp dụng plugin đã có**, không xin một phiên bản khác. `apply false` nghĩa là root chưa áp dụng plugin vào chính root, không có nghĩa plugin đã được gỡ khỏi classpath.

**Không để hai đoạn child trên cùng tồn tại.** Đây là một thí nghiệm có chủ đích: thử bản sai trong bản sao project, quan sát lỗi rồi thay bằng phương án đúng.

### 6.2. Vì sao “unknown version” khó xử lý hơn?

Plugin có thể đã xuất hiện trên classpath do:

- `buildscript.dependencies.classpath` của cơ chế legacy;
- một plugin/convention plugin khác đưa mã plugin vào classpath;
- cấu hình build logic hoặc included build;
- settings/plugin đã nạp plugin từ một đường khác;
- nhiều nguồn nạp cùng implementation mà không có version metadata Gradle kiểm chứng được.

Nếu sau đó dùng `plugins { id("...") version "..." }`, Gradle có thể không xác nhận được phiên bản đang có trên classpath, nên từ chối versioned request.

**Quy trình xử lý:** tìm **nơi plugin được nạp lần đầu** → thống nhất version ở một nơi → tại nơi áp dụng lại, dùng request **không có version** nếu classpath đã cung cấp plugin đúng → bỏ đường nạp trùng hoặc tách build classpath có chủ đích.

Đừng vội “fix” bằng cách thêm một version thứ ba. Nếu không biết plugin nào đã tạo classpath, đọc root build, settings, convention plugin và legacy buildscript trước khi đổi version.

### 6.3. Phân biệt xung đột plugin với dependency của Java app

`dependencies { implementation("com.foo:lib:1.0") }` đóng góp vào compile/runtime classpath của **mã ứng dụng**. `buildscript { dependencies { classpath("...") } }` đóng góp vào **classpath chạy build logic**. Hai luồng này không tự thay thế nhau.

Vì vậy:

- Lỗi `plugin already on classpath`: xem plugin DSL, pluginManagement, buildscript và convention/build-logic.
- Lỗi Java `NoClassDefFoundError` ở `:app:run`: xem `runtimeClasspath` và packaging của app.
- Lỗi plugin `NoSuchMethodError` khi **áp dụng plugin**: xem Gradle/plugin API và thư viện plugin sử dụng; không chỉ xem dependency Java của app.

## 7. Plugin classpath và cách áp dụng legacy `buildscript`

Trước DSL `plugins` hiện đại, một plugin có thể được tải như dependency của buildscript rồi áp dụng bằng `apply`. Ví dụ riêng **không kết hợp với ví dụ `plugins` cùng plugin ID**:

```kotlin
// build.gradle.kts: phong cách legacy, chỉ dùng nếu dự án yêu cầu.
buildscript {
    repositories {
        gradlePluginPortal()
    }
    dependencies {
        classpath("io.github.ben-manes:gradle-versions-plugin:0.67.0")
    }
}

apply(plugin = "io.github.ben-manes.versions")
```

Nó có classpath riêng cho build logic. Nếu bạn vừa thêm artifact ở đây vừa yêu cầu cùng plugin trong `plugins` với một version, có thể tạo xung đột hoặc lỗi “unknown version”, tùy đường nạp.

**Khuyến nghị:** với build mới, ưu tiên `plugins` và quản lý version/repositories trong `pluginManagement` hoặc version catalog. Chỉ duy trì `buildscript` nếu cần tương thích với plugin/cấu trúc legacy hoặc có một lý do kỹ thuật cụ thể.

Lệnh giúp xem buildscript classpath:

```bash
./gradlew :app:buildEnvironment
```

Với plugin theo `plugins`, output `buildEnvironment` cũng có thể giúp quan sát những artifact trên classpath trong một số cấu trúc, nhưng **không phải lệnh duy nhất hoặc luôn đầy đủ** để giải thích plugin resolution. Kết hợp nó với `--info`, settings/build scripts và stacktrace.

## 8. Sai phiên bản: phân biệt bốn lớp tương thích

“Plugin sai phiên bản” không phải một lỗi duy nhất.

| Lớp | Vấn đề | Biểu hiện thường gặp |
| --- | --- | --- |
| Plugin ID/version publication | Version yêu cầu chưa được phát hành | `Plugin ... was not found`, marker/version không tồn tại |
| Plugin ↔ Gradle API | Plugin dùng API không có ở Gradle Wrapper hiện tại | Lỗi apply plugin, `NoSuchMethodError`, incompatibility message |
| Plugin ↔ JVM chạy Gradle | Class plugin được biên dịch cho Java mới hơn runtime JVM | `UnsupportedClassVersionError` / class file major version |
| Plugin ↔ plugin dependencies | Hai plugin kéo version thư viện build logic không tương thích | `ClassNotFoundException`, `NoSuchMethodError`, linkage errors |
| Plugin ↔ loại target | Settings plugin bị áp dụng ở project hoặc ngược lại | “must be applied in the settings script” hoặc lỗi khi apply |
| Plugin ↔ project DSL/model | Plugin áp dụng được nhưng extension/task không có như code kỳ vọng | `Unresolved reference`, unknown extension/task, cấu hình sai |

### 8.1. Gradle Wrapper khác Java toolchain

Hai khái niệm:

- **JVM chạy Gradle:** Java runtime dùng để khởi động Gradle daemon và chạy build logic/plugin.
- **Java toolchain:** JDK được chọn để biên dịch/test/chạy code Java theo những task đã cấu hình.

Ví dụ:

```kotlin
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}
```

Cấu hình này chọn Java 17 **cho task Java**, không bảo đảm plugin được chạy bởi Java 17 nếu Gradle daemon thực tế đang dùng JVM khác. Nếu plugin yêu cầu một JVM tối thiểu, cần kiểm tra JVM đang chạy Gradle.

Lệnh:

```bash
./gradlew --version
java -version
```

`./gradlew --version` là nguồn quan trọng để xem **Gradle version, JVM được dùng và môi trường launcher/daemon được báo cáo**. `java -version` ở terminal giúp biết Java trong PATH, nhưng IDE hoặc Gradle daemon có thể dùng JDK khác. Đừng suy ra JVM của Gradle chỉ từ lệnh `java -version`.

### 8.2. Class file major version

Nếu log có:

```text
UnsupportedClassVersionError
Unsupported class file major version ...
```

có thể JVM đang chạy Gradle không đọc được bytecode mà plugin hoặc một dependency plugin đã biên dịch. Ví dụ class file major version `61` là Java 17; major version `65` là Java 21. Đây là dấu hiệu để đối chiếu phiên bản Java, không phải lệnh sửa bằng cách thay `sourceCompatibility` của ứng dụng.

Cách xử lý: kiểm tra yêu cầu Java tối thiểu của plugin và ma trận Gradle↔JDK; nâng **JVM chạy Gradle** hoặc chọn plugin/Gradle tương thích theo chính sách của dự án. Đừng nâng bừa Gradle/JDK trên CI mà chưa thử build.

### 8.3. Plugin dùng API Gradle mới hơn Wrapper

Một plugin được publish hợp lệ có thể được tải thành công nhưng thất bại khi apply vì dùng API chỉ tồn tại ở phiên bản Gradle mới hơn. Biểu hiện có thể là `NoSuchMethodError`, `NoClassDefFoundError` hoặc thông báo rõ về minimum Gradle version.

Đó **không phải lỗi repository**. Thêm `gradlePluginPortal()` lần nữa hoặc `--refresh-dependencies` không tạo API mà Wrapper hiện tại chưa có.

**Đối chiếu ba nguồn:** phiên bản Gradle Wrapper của repo, release notes/compatibility matrix của plugin, và JDK dùng để chạy Gradle. Sau đó chọn một cặp phiên bản tương thích đã được kiểm thử.

### 8.4. Không suy ra version “mới nhất” luôn đúng

Một plugin mới hơn có thể yêu cầu Gradle/JVM mới hơn hoặc thay đổi plugin ID, API, task name. Trước khi nâng version:

1. Đọc release notes và yêu cầu minimum Gradle/JDK.
2. Kiểm tra ID có đổi tên/deprecate không.
3. Nâng Gradle Wrapper khi có lý do và theo ma trận tương thích.
4. Thử build và tasks trong một nhánh riêng.
5. Chạy test và CI tương tự môi trường production.
6. Review những plugin dependencies và quyền truy cập nếu plugin nhận thêm repository.

Không dùng version động như `latest.release` cho một plugin build quan trọng chỉ vì muốn tránh thao tác cập nhật. Plugin là mã được thực thi trong build và có ảnh hưởng sâu tới công cụ.

## 9. Dự án Java 17 có thể chạy: kiểm chứng plugin resolution thành công

Ví dụ sau dùng Gradle Kotlin DSL và **hai plugin**:

- `application`: core plugin đi kèm Gradle, không cần version ngoài.
- `io.github.ben-manes.versions` version `0.67.0`: external plugin được phát hành trên Gradle Plugin Portal, cung cấp task `dependencyUpdates`.

Plugin thứ hai chỉ là một **plugin ví dụ có ID/version cụ thể**, không bắt buộc trong mọi ứng dụng Java. Ở thời điểm viết bài, có phiên bản này trên Plugin Portal; khi tái sử dụng cần đối chiếu phiên bản tương thích với Gradle Wrapper đang dùng.

### 9.1. Cây thư mục

```text
plugin-diagnostic-lab/
├── settings.gradle.kts
├── app/
│   ├── build.gradle.kts
│   └── src/
│       └── main/
│           └── java/
│               └── demo/
│                   └── Main.java
└── gradle/wrapper/...  (được tạo khi có Wrapper)
```

**File `settings.gradle.kts`:**

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

rootProject.name = "plugin-diagnostic-lab"
include("app")
```

**File `app/build.gradle.kts`:**

```kotlin
plugins {
    application
    id("io.github.ben-manes.versions") version "0.67.0"
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

application {
    mainClass.set("demo.Main")
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

**File `app/src/main/java/demo/Main.java`:**

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String text = StringUtils.capitalize("plugin diagnosis works");
        System.out.println(text);
    }
}
```

### 9.2. Kiểm tra điều kiện chạy

Cần có Gradle Wrapper phù hợp, JDK/toolchain 17 và kết nối Internet khi plugin/artifact chưa được cache. Với thư mục mới chưa có Wrapper, một bản Gradle tương thích đã được cài trên máy có thể tạo Wrapper lần đầu:

```bash
gradle wrapper
```

Nếu bản Gradle cài đặt quá cũ để áp dụng plugin trước khi tạo Wrapper, cần tạo Wrapper từ một cấu hình tối thiểu tương thích hoặc nâng Gradle cài đặt trước khi thêm plugin bên ngoài. Không nên lặp vô hạn `gradle wrapper` với cùng một tổ hợp version không tương thích.

Chạy trên Linux/macOS:

```bash
./gradlew --version
./gradlew :app:tasks --all
./gradlew :app:run --quiet
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat :app:tasks --all
.\gradlew.bat :app:run --quiet
```

Stdout do chương trình Java in ra, nếu build thành công:

```text
Plugin diagnosis works
```

`StringUtils.capitalize` chỉ viết hoa ký tự đầu của chuỗi, nên output **không** phải `Plugin Diagnosis Works`. Lệnh `--quiet` giảm log Gradle, nhưng môi trường có thể còn thông báo ngoài stdout ứng dụng.

Với `:app:tasks --all`, bạn có thể tìm task `dependencyUpdates` do plugin bên ngoài cung cấp. Task `run` đến từ `application`. Dùng thêm:

```bash
./gradlew :app:dependencyUpdates --console=plain
```

Báo cáo của `dependencyUpdates` phụ thuộc những phiên bản hiện có trong repositories và metadata tại thời điểm chạy, **không có một stdout cố định** để học thuộc. Việc task tồn tại chứng minh plugin đã được áp dụng và cung cấp task; nó không có nghĩa mọi dependency của ứng dụng đều cần nâng cấp.

### 9.3. Kiểm chứng ba lớp độc lập

| Phép kiểm tra | Điều chứng minh |
| --- | --- |
| `./gradlew --version` | Wrapper/Gradle/JVM thực tế đang dùng |
| `:app:tasks --all` có `dependencyUpdates` | External plugin đã được nạp và áp dụng vào `:app` |
| `:app:tasks --all` có `run` | Core application plugin đã được áp dụng |
| `:app:run` in `Plugin diagnosis works` | Java code đã compile, dependency commons-lang3 resolve và runtime hoạt động |
| `:app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath` | Version thư viện Java được chọn trong runtime graph |
| `:app:buildEnvironment` | Một góc nhìn buildscript classpath, có thể hỗ trợ điều tra plugin loading |

Nếu `dependencyUpdates` tồn tại nhưng `:app:run` lỗi thiếu commons-lang3, plugin resolution có thể **đã thành công**, còn vấn đề nằm ở project dependency repositories hoặc Java runtime. Đừng trộn hai loại lỗi.

## 10. Ba thí nghiệm lỗi có chủ đích — mỗi lần chỉ đổi một yếu tố

Các ví dụ dưới đây dùng **bản sao** project mục 9. Những đoạn “sai” **không phải cấu hình để dùng lâu dài**. Mỗi lần hãy quan sát log rồi khôi phục bản chạy thành công trước khi chuyển thí nghiệm.

### 10.1. Thí nghiệm 1: sai plugin ID

Thay trong `app/build.gradle.kts`:

```kotlin
plugins {
    application
    id("com.example.plugin-does-not-exist") version "1.0.0"
}
```

Plugin giả định không được phát hành; Gradle sẽ cố resolve ở các nguồn đã cấu hình và dự kiến báo **plugin not found**, không chạy tới `Main.main`.

Cần kiểm tra: ID viết đúng chưa, plugin thực sự đã publish không, repository nào chứa marker, mạng/credential có hoạt động không. **Không chữa lỗi bằng cách thêm một JAR vào `implementation`**.

Khôi phục `id("io.github.ben-manes.versions") version "0.67.0"` sau thử nghiệm.

### 10.2. Thí nghiệm 2: thiếu version của external plugin

Thay bằng:

```kotlin
plugins {
    application
    id("io.github.ben-manes.versions")
}
```

Trong **project mẫu không có version default hoặc plugin đã nạp từ root**, Gradle có thể báo plugin repository request thiếu version hoặc plugin không tìm thấy. **Không được tổng quát hóa rằng plugin bên ngoài luôn phải ghi version ngay ở child:** khi đã có version default ở `pluginManagement` hoặc plugin đã được nạp qua root/apply false, child **có thể và nên** chỉ ghi ID.

Khôi phục version trực tiếp, hoặc chuyển sang một trong những phương án sở hữu version tập trung ở mục 11.

### 10.3. Thí nghiệm 3: version plugin không được publish

Thay bằng:

```kotlin
plugins {
    application
    id("io.github.ben-manes.versions") version "0.0.0-not-published"
}
```

Gradle có thể tìm đúng ID/repository nhưng không có marker/artifact tương ứng version này. Nó sẽ báo lỗi resolution, thường gần với `Plugin ... was not found`.

Bước sửa là chọn một version **thực sự tồn tại**, đồng thời xem yêu cầu tương thích Gradle/JVM. Nếu repository không kết nối được, chọn đúng version vẫn chưa đủ.

## 11. Thí nghiệm xung đột phiên bản giữa root và child

Thay đổi **cách quản lý version của project mẫu** như sau; đây là **phương án thay thế**, không sử dụng đồng thời với cách child tự ghi version trong mục 9.

**Root `build.gradle.kts`:**

```kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.67.0" apply false
}
```

**Child `app/build.gradle.kts` — phần `plugins` đúng:**

```kotlin
plugins {
    application
    id("io.github.ben-manes.versions")
}
```

Những phần còn lại của `app/build.gradle.kts` (toolchain, application, dependencies) giữ nguyên như mục 9. Khi root đã sở hữu version, child chỉ cần ID. Đây là một cấu trúc thường dùng trong multi-project builds.

**Child — cấu hình cố ý sai để xem xung đột:**

```kotlin
plugins {
    application
    id("io.github.ben-manes.versions") version "0.65.0"
}
```

Lúc này root đã đưa version `0.67.0` vào classpath, nhưng child yêu cầu `0.65.0`. Gradle thường báo plugin đã có trên classpath với **different version**, trước khi chạy Java.

**Cách sửa:** trở lại khối child **không có version**, hoặc loại bỏ chiến lược root apply-false và chọn một chiến lược khai báo version nhất quán khác. Không sử dụng hai version cùng lúc rồi cho rằng Gradle sẽ thực hiện version conflict resolution như các dependency của ứng dụng.

### 11.1. Cách khác: dùng version catalog

Tạo `gradle/libs.versions.toml`:

```toml
[plugins]
versions = { id = "io.github.ben-manes.versions", version = "0.67.0" }
```

Trong project, dùng:

```kotlin
plugins {
    application
    alias(libs.plugins.versions)
}
```

Đây là lựa chọn **thay cho** `id(...) version ...` trong child. Với root apply-false hoặc settings plugin đã nạp cùng plugin, hãy đánh giá việc alias có đưa version vào request lần nữa hay không; trong môi trường có plugin classpath/version conflict, cú pháp ID **không version** thường rõ ràng hơn tại nơi áp dụng lại.

Catalog không biến plugin ID thành alias Maven và không tự cung cấp plugin marker; repository vẫn do `pluginManagement` giải quyết.

## 12. Convention plugin hoặc included build báo “not found”

Một công ty có thể tự xây plugin `acme.java-conventions` trong included build tên `build-logic`. Khi project viết:

```kotlin
plugins {
    id("acme.java-conventions")
}
```

mà Gradle báo không tìm thấy, **đừng mặc định plugin này nằm trên Plugin Portal**. Nó có thể chỉ tồn tại trong source của repository.

**`settings.gradle.kts` có thể cần:**

```kotlin
pluginManagement {
    includeBuild("build-logic")
    repositories {
        gradlePluginPortal()
    }
}
```

Precompiled script plugin `build-logic/src/main/kotlin/acme.java-conventions.gradle.kts` sẽ cung cấp ID tương ứng khi build-logic áp dụng cấu hình plugin phát triển thích hợp, ví dụ plugin `kotlin-dsl`. Đây là **đoạn minh họa về cấu trúc**, không phải toàn bộ included build runnable.

Checklist:

1. Đường dẫn `build-logic` có tồn tại và được include đúng không?
2. Build-logic có settings/build.gradle phù hợp, có thể build không?
3. Plugin ID có khớp tên precompiled script hoặc ID được đăng ký trong `gradlePlugin { plugins { ... } }` không?
4. Plugin là project plugin hay settings plugin? Có áp dụng ở đúng target không?
5. Build-logic có các plugin dependencies/Gradle version phù hợp không?
6. Log cho thấy “plugin không tìm thấy” hay “compile build-logic thất bại”? Đây là hai lỗi khác nhau.

Nếu compile build-logic báo Kotlin compilation error, sửa source/plugin dependencies ở build-logic; thêm Plugin Portal ở project app không tự chữa mã Kotlin bị lỗi.

## 13. Nhìn đúng chỗ khi có lỗi classloader hoặc plugin dependency

Một plugin Java/Kotlin có thể dùng thư viện nội bộ của chính nó. Các implementation dependencies này nằm trên **classpath phục vụ plugin**, không phải classpath runtime của ứng dụng.

Dấu hiệu có thể gồm:

```text
java.lang.NoSuchMethodError: ...
java.lang.NoClassDefFoundError: ...
java.lang.ClassCastException: ...
java.util.ServiceConfigurationError: ...
```

Không phải mọi lỗi trên đều do version conflict; chúng cũng có thể xuất phát từ plugin bug, Java binary incompatibility hoặc cấu hình sai. Chẩn đoán bằng cách:

1. Xem stacktrace xác định class thuộc **plugin nào** và lỗi xảy ra trong configuration hay task execution.
2. Kiểm tra plugin versions đang được yêu cầu, đã có trên classpath và được convention plugin đưa vào.
3. Kiểm tra legacy `buildscript` và plugin dependencies của build-logic.
4. So sánh với phiên bản Gradle Wrapper và JVM.
5. Thử bản plugin được nhà phát hành xác nhận tương thích trên môi trường kiểm soát.
6. Giữ thay đổi nhỏ, chỉ sửa một đường nạp/version mỗi lần.

**Đừng vội thêm `implementation("...")` của app** để vá một class bị thiếu khi chính Gradle đang áp dụng plugin. Library app thường không nằm trên buildscript classpath của plugin.

### 13.1. `NoSuchMethodError` từ plugin khác `NoSuchMethodError` từ Java app

| Thời điểm lỗi | Nơi cần xem trước |
| --- | --- |
| Đang evaluate `settings.gradle.kts` | Settings plugin/pluginManagement và Gradle API |
| Đang evaluate `build.gradle.kts` | Project plugin/classpath/extension, phiên bản Gradle |
| Trong task do plugin cung cấp | Implementation dependencies/plugin version, task inputs, Gradle API |
| Khi chạy `java`/`run` của app | Java runtimeClasspath, version và JAR đóng gói |

Đọc stacktrace để biết **lệnh gọi nào và class nào** phát sinh lỗi. Cùng một tên exception chưa đủ để kết luận đây là “plugin classpath conflict”.

## 14. Công cụ chẩn đoán theo đúng thứ tự

Trên Linux/macOS:

```bash
./gradlew --version
./gradlew help --stacktrace --info --console=plain
./gradlew :app:tasks --all
./gradlew :app:buildEnvironment
./gradlew :app:dependencies --configuration runtimeClasspath
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat help --stacktrace --info --console=plain
.\gradlew.bat :app:tasks --all
.\gradlew.bat :app:buildEnvironment
.\gradlew.bat :app:dependencies --configuration runtimeClasspath
```

**Đọc kết quả đúng chức năng:**

- `--version`: biết Gradle Wrapper/JVM thực tế.
- `help --stacktrace --info`: chạy một task gần như tối thiểu, nhưng vẫn thực hiện cấu hình build nên bộc lộ lỗi plugin sớm.
- `:app:tasks --all`: sau khi plugin được áp dụng, kiểm tra task nó tạo có xuất hiện trong đúng project không.
- `:app:buildEnvironment`: góc nhìn buildscript classpath, có giá trị đặc biệt với legacy `buildscript` và một số đường nạp plugin.
- `:app:dependencies --configuration runtimeClasspath`: **Java app dependencies**, không phải một lệnh đọc tất cả plugin markers.
- `dependencyInsight`: dùng cho module trên app compile/runtime graph, **không phải công cụ đầu tiên cho lỗi plugin not found**.

### 14.1. Dùng `--debug` khi cần, nhưng bảo vệ secret

`--debug` có thể rất dài và có nhiều thông tin về URLs, request, môi trường, classloader hoặc cache. Chỉ dùng khi `--info`/`--stacktrace` không đủ, và **xóa/redact token, user names, private URLs nếu cần trước khi gửi log cho người khác**.

Không khẳng định debug log luôn an toàn để dán công khai. Với kho plugin nội bộ, thông tin endpoint và error response có thể nhạy cảm.

### 14.2. Kiểm tra offline/cache đúng phạm vi

```bash
./gradlew :app:help --offline --console=plain
./gradlew :app:help --refresh-dependencies --info --console=plain
```

- `--offline`: không gọi remote repos; nếu marker/implementation/plugin dependencies chưa có đủ cache, build có thể fail. Nó **không tự chuyển sang `mavenLocal()`**.
- `--refresh-dependencies`: kiểm tra lại dependency metadata/cache theo cơ chế Gradle; nó không tự sửa plugin ID sai, version chưa publish, kho bị 403 hoặc plugin không tương thích JVM.
- `clean`: dọn output project, không phải cơ chế xóa toàn bộ plugin cache hay sửa classloader conflict.

Không xóa `~/.gradle/caches` như bước đầu tiên. Việc xóa cache có thể khiến CI/laptop mất khả năng chạy offline mà chưa giải quyết nguyên nhân thật.

## 15. Checklist quyết định: lỗi thuộc bước nào?

```text
./gradlew help THẤT BẠI
          |
          v
A. Có "Plugin ... was not found"?
    | Có -> kiểm ID, version, pluginManagement.repositories,
    |         marker/implementation, credentials, network, offline.
    |
    | Không
    v
B. Có "already on the classpath"?
    | Có -> tìm nơi đã nạp plugin, phiên bản root/settings,
    |         buildscript/build-logic, bỏ version trùng ở child.
    |
    | Không
    v
C. Có lỗi khi áp dụng plugin?
    | Có -> xem plugin↔Gradle API, JVM, target plugin,
    |         stacktrace và plugin implementation dependencies.
    |
    | Không
    v
D. Chỉ lỗi khi task Java/test/run?
    | Có -> xem project dependencies/classpath/task-specific config;
    |         không nhất thiết là plugin resolution.
    |
    v
Xác minh sau sửa:
  help -> tasks -> compile/test/run -> CI
```

Cây quyết định dùng để khoanh vùng, không thay thế đọc error đầy đủ. Đôi khi một lỗi network xuất hiện ngay dưới thông báo plugin not found; đôi khi root cause sâu hơn là lỗi xác thực hoặc thiếu artifact implementation. Hãy phân tích `Caused by` thay vì chỉ copy dòng đầu.

## 16. Ma trận lỗi thường gặp và cách sửa

| Triệu chứng | Vấn đề có thể | Hành động phù hợp |
| --- | --- | --- |
| `Plugin ... was not found` | ID/phiên bản/repository/marker không đúng | Kiểm tra Portal hoặc kho nội bộ; đọc pluginManagement |
| `plugin dependency must include a version number` | External plugin request thiếu version | Khai báo version một nơi hoặc default trong pluginManagement |
| `already on the classpath with a different version` | Root đã nạp X, child yêu cầu Y | Bỏ version ở child hoặc thống nhất nơi sở hữu version |
| `already on the classpath with an unknown version` | Plugin được nạp qua nguồn không có version metadata kiểm chứng | Tìm buildscript/convention/settings classpath; tránh request version lần hai |
| `UnsupportedClassVersionError` | JVM chạy Gradle quá cũ so với bytecode plugin | Đối chiếu Java runtime, Gradle và minimum Java của plugin |
| `NoSuchMethodError` khi apply plugin | Plugin dùng Gradle API hoặc transitive dependency không tương thích | Xem stacktrace, plugin release notes, wrapper |
| Plugin ID đúng nhưng không có task mong muốn | Plugin áp dụng sai project/target hoặc task name đã đổi | Chạy `:project:tasks --all`, xem tài liệu đúng version |
| `Unresolved reference` tới extension của plugin | Plugin chưa được áp dụng hoặc Kotlin DSL scope sai | Kiểm tra `plugins` và accessor/model |
| Task bị báo not found ở root | Plugin chỉ áp dụng ở `:app` | Chạy `:app:taskName` thay cho `:taskName` |
| `401 Unauthorized` / `403 Forbidden` | Kho nội bộ yêu cầu xác thực/quyền | Cấp secret/permissions đúng, không hardcode token |
| TLS/PKIX/SSL handshake | Chứng chỉ/proxy/JDK truststore | Kiểm tra mạng, certificate và JDK của Gradle |
| `Could not resolve plugin artifact` | Marker có nhưng implementation/transitive dependency lỗi | Kiểm tra artifact, marker POM, proxy/upstream |
| Chạy online được, offline lỗi | Cache plugin/dependency chưa đủ | Dùng online build hợp lệ và cache phù hợp |
| IDE Sync lỗi, CLI Wrapper chạy | IDE dùng Gradle JVM/version hoặc settings khác | So sánh Gradle JVM, Wrapper và environment |
| Plugin cập nhật rồi build vỡ | Plugin version mới đổi API/minimum Gradle/JDK | Kiểm tra release notes, phục hồi version đã biết tốt |
| Android plugin not found | Thiếu `google()`/version/AGP compatibility | Cấu hình pluginManagement đúng và xem ma trận AGP |
| Convention plugin not found | Thiếu `includeBuild`, sai ID hoặc build-logic không compile | Kiểm tra settings và precompiled plugin |
| Lỗi `implementation(...)`/`application { ... }` | Plugin tạo configuration/extension chưa được áp dụng | Thêm core plugin phù hợp, không thêm kho bừa |
| `NoClassDefFoundError` chỉ trong `:app:run` | Thiếu thư viện runtime của app | Xem `runtimeClasspath` thay vì plugin marker |

## 17. Quy trình sửa lỗi thực tế cho nhóm phát triển

Một quy trình ngắn, có thể dùng trong PR:

**Bước 1 — giữ nguyên bằng chứng.** Lưu Gradle Wrapper version, JVM, plugin ID/version, command gây lỗi và phần stacktrace có `Caused by`. Không xóa cache hoặc nâng nhiều version trước khi đọc thông báo.

**Bước 2 — đặt lỗi vào đúng pha.** Plugin resolution, plugin application, script compilation, task configuration hay task execution? Nếu `help` cũng fail, lỗi nhiều khả năng nằm trước logic Java.

**Bước 3 — kiểm tra nguồn plugin.** Khối `pluginManagement` ở settings; plugin ID/version; marker; implementation; plugin nội bộ/included build nếu có. Nếu server báo 403, xác thực quyền trước khi thử sửa mã.

**Bước 4 — xác định chủ sở hữu version.** Version đặt trong child, root `apply false`, `pluginManagement.plugins`, version catalog hay legacy `buildscript`? Tránh để hai đường nạp cùng plugin với hai versions khác nhau.

**Bước 5 — kiểm tra ma trận tương thích.** Wrapper Gradle, Java chạy Gradle, plugin minimum requirements và dependencies plugin. Java toolchain 17 trong app không thay cho JVM chạy Gradle.

**Bước 6 — sửa một nguyên nhân.** Ví dụ đổi plugin ID sai, thêm repo đúng, bỏ version ở child, nâng Wrapper có kiểm thử hoặc sửa includeBuild. Không thêm cả ba repositories và nâng mọi plugin cùng lúc nếu không biết thao tác nào có tác dụng.

**Bước 7 — xác minh từ đơn giản đến đầy đủ.** Chạy `help`, `tasks --all`, sau đó `compileJava`/`test`/`run`. Với plugin cung cấp task riêng, chạy đúng task đó ở project phù hợp.

**Bước 8 — CI/IDE.** Nếu CLI chạy nhưng CI/IDE lỗi, đối chiếu Wrapper, Gradle JVM, environment variables, proxy/credentials và policy. Bảo đảm bản sửa không chỉ hoạt động trên máy có cache hoặc `mavenLocal()` cá nhân.

### 17.1. Không vô tình làm giảm bảo mật để sửa nhanh

Plugin có thể chạy mã trong build, đọc file và môi trường tùy quyền process. Khi một repository plugin không hoạt động, **không nên**:

- Thêm URL HTTP không bảo mật chỉ để vượt lỗi TLS.
- Hardcode token/password vào build script hoặc commit `gradle.properties` chứa secret.
- Tải một JAR không rõ nguồn rồi nạp bằng `buildscript.classpath`.
- Tắt kiểm tra chứng chỉ mà chưa điều tra CA/proxy đúng cách.
- Dùng một version động chưa kiểm chứng trên CI chỉ vì version cố định không tìm được.

Ưu tiên repository được tổ chức phê duyệt, xác thực và quyền tối thiểu; review việc nâng cấp plugin như một thay đổi build logic có khả năng ảnh hưởng toàn dự án.

## 18. Bài tập thực hành

**Bài tập A — nhận diện luồng repository.** Từ settings ở mục 9, chỉ ra plugin external được tìm ở đâu và commons-lang3 được tìm ở đâu. Nếu bỏ `gradlePluginPortal()` nhưng giữ `mavenCentral()` trong dependencyResolutionManagement, vì sao plugin có thể lỗi ngay cả khi Maven Central hoạt động?

**Bài tập B — plugin ID sai.** Thử `com.example.plugin-does-not-exist` ở mục 10.1, đọc `What went wrong`. Lỗi ở plugin resolution hay Java compilation? Khôi phục ID/version chính xác.

**Bài tập C — thiếu version.** Xóa version của external plugin khi project không có default/root classpath. Quan sát lỗi, rồi đưa version vào `pluginManagement.plugins` thay vì child và thử lại.

**Bài tập D — classpath conflict.** Chuyển project sang root `apply false` ở mục 11, thử child request version `0.65.0`, đọc lỗi và sửa bằng ID không có version. Vì sao `apply false` vẫn liên quan đến classpath?

**Bài tập E — Java và plugin classpath.** Bỏ `implementation("org.apache.commons:commons-lang3:3.14.0")` của app nhưng giữ plugin. Xem sự khác biệt giữa lỗi biên dịch thiếu `StringUtils` và lỗi plugin not found.

**Bài tập F — JVM vs toolchain.** Dùng `./gradlew --version` và `java -version` ghi lại Java runtime thực tế. Giải thích vì sao `toolchain.languageVersion.set(JavaLanguageVersion.of(17))` không phải bằng chứng plugin được chạy bằng Java 17.

**Bài tập G — phiên bản plugin không tương thích.** Trong một nhánh thử nghiệm, chọn một plugin/Gradle version pair mà tài liệu công bố rõ không tương thích, quan sát thông báo apply failure và khôi phục bản tốt. Không cố hạ JVM đến môi trường mất an toàn hoặc làm hỏng project chính.

**Bài tập H — convention plugin.** Mô tả một included build cung cấp plugin `acme.java-conventions`. Nếu Gradle không tìm thấy nó, cần kiểm tra `includeBuild`, plugin ID và build-logic compilation như thế nào?

**Bài tập I — offline.** Sau khi resolve plugin và dependency thành công online, chạy `--offline`. Nếu nó fail trên môi trường mới, giải thích vì sao lockfile hoặc Gradle Wrapper không tự chứa plugin artifacts.

**Bài tập J — log và bảo mật.** Giả định kho plugin riêng báo `401 Unauthorized`. Đề xuất cách kiểm tra token/quyền mà không in secret vào log; nêu vì sao thêm một plugin repository công khai không phải câu trả lời đúng cho plugin nội bộ.

### Câu hỏi tự kiểm tra

1. Plugin Gradle khác dependency Java ứng dụng ở điểm nào?
2. Plugin marker artifact có phải JAR thực thi của plugin không?
3. Tọa độ marker Maven được suy ra từ plugin ID/version thế nào?
4. Kho nào phục vụ `plugins`, kho nào phục vụ `implementation`?
5. Khi nào external plugin có thể được khai báo không version ở project?
6. `apply false` có nghĩa là plugin chưa nằm trên classpath không?
7. Vì sao child request version `0.65.0` có thể xung đột với root `0.67.0`?
8. Lỗi “unknown version” khác “different version” về bằng chứng nào?
9. `buildscript.dependencies.classpath` khác `implementation` ra sao?
10. Khi nào dùng `pluginManagement.resolutionStrategy.useModule`?
11. Vì sao Java toolchain 17 không tự bảo đảm JVM chạy Gradle là Java 17?
12. Lỗi `NoSuchMethodError` khi apply plugin gợi ý kiểm tra gì?
13. `dependencyInsight` có phải lệnh chính để tìm plugin marker không?
14. `:app:tasks --all` có thể chứng minh điều gì sau khi plugin áp dụng thành công?
15. Vì sao plugin có thể not found khi project dependency repositories đúng?
16. Có thể áp dụng settings plugin trong `app/build.gradle.kts` tùy ý không?
17. `--refresh-dependencies` có chữa được plugin ID sai hoặc API không tương thích không?
18. Vì sao cần xác minh cả CLI, IDE và CI sau khi sửa plugin?
19. Tại sao không nên tắt TLS verification hoặc dùng repository lạ để sửa nhanh?
20. Nếu lỗi xảy ra trước `compileJava`, ưu tiên chẩn đoán pha nào?

**Tài liệu chính thức để đối chiếu:** [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html), [Gradle — Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html), [Gradle Plugin Portal](https://plugins.gradle.org/), [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html).

**Ghi nhớ:** Khi Gradle báo lỗi plugin, trước tiên hãy **xác định pha thất bại**. “Not found” thường liên quan ID/version/marker/repository; “already on classpath” gợi ý plugin đã được nạp và có vấn đề khai báo phiên bản; lỗi apply/runtime plugin gợi ý Gradle API/JVM/plugin dependencies không tương thích. Dùng đúng nơi cấu hình plugin, sở hữu version ở một chỗ, đọc stacktrace và đối chiếu Wrapper/JVM trước khi sửa; đừng nhầm classpath plugin với classpath Java app.