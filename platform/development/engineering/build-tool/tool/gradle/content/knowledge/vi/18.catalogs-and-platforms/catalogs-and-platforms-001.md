# Version catalog giải quyết việc đặt tên và tập trung tọa độ trong Gradle

## 1. Vì sao dự án cần version catalog?

Khi một build Gradle có nhiều module, việc viết trực tiếp tọa độ dependency ở từng file `build.gradle` dẫn đến lặp và dễ nhầm:

```groovy
// build.gradle của :app
dependencies {
    implementation 'com.google.guava:guava:33.3.1-jre'
    testImplementation 'org.junit.jupiter:junit-jupiter-api:5.11.4'
}

// build.gradle của :service (minh họa file riêng)
dependencies {
    implementation 'com.google.guava:guava:33.3.1-jre'
    testImplementation 'org.junit.jupiter:junit-jupiter-api:5.11.4'
}
```

Nếu một nhóm cần đổi phiên bản Guava, việc tìm/sửa từng chuỗi có thể bỏ sót module, gây version drift hoặc typo. **Gradle Version Catalog** cung cấp một **danh mục alias có tên dễ đọc** trỏ đến tọa độ dependency và plugin, thường nằm trong `gradle/libs.versions.toml`. Các build scripts chỉ dùng alias:

```groovy
dependencies {
    implementation libs.guava
    testImplementation libs.junit.api
}
```

Hai dòng này có nghĩa: *“lấy khai báo dependency đã được đặt tên guava và junit-api trong catalog libs”*. Người đọc tập trung vào **vai trò thư viện**, không phải phải nhớ chuỗi `group:artifact:version` ở mọi file.

**Version catalog giải quyết hai việc cốt lõi**:

1. **Đặt tên tọa độ:** biến `com.google.guava:guava:33.3.1-jre` thành một alias có type-safe accessor như `libs.guava`.
2. **Tập trung khai báo:** gom version, libraries, bundles và plugin IDs/versions về một chỗ để giảm lặp, hỗ trợ autocomplete/kiểm tra alias trong IDE và review thay đổi phiên bản thuận lợi hơn.

**Giới hạn phải nhớ ngay:** catalog **không phải** repository, BOM/platform, dependency lockfile, hoặc một lệnh tự động ép phiên bản cuối. Giá trị version trong catalog là **requested version** khi alias được sử dụng; Gradle vẫn thực hiện conflict resolution, constraints, platforms và các rules như với dependency khai báo bằng chuỗi. Một alias xuất hiện trong TOML **không có nghĩa module đó đã được thêm** vào project: chỉ những alias được dùng trong `dependencies { }`, `plugins { }` hoặc API thích hợp mới có tác dụng.

## 2. Thuật ngữ: coordinate, alias, version reference, accessor

| Tên | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Tọa độ Maven/GAV** | Group + artifact/module name + version của một module dependency. | `com.google.guava:guava:33.3.1-jre` |
| **Library alias** | Tên ngắn do project đặt cho tọa độ thư viện. | `guava`, `junit-api` |
| **Version alias** | Tên phiên bản dùng lại cho một hoặc nhiều module. | `guava = "33.3.1-jre"`, `junit = "5.11.4"` |
| **Version reference** | Liên kết một library/plugin alias tới version alias. | `version.ref = "junit"` |
| **Generated accessor** | Cú pháp Gradle tạo từ alias để sử dụng trong build script. | `libs.guava`, `libs.junit.api` |
| **Bundle** | Một alias đại diện cho **nhóm library aliases**; dùng để khai báo nhiều dependency cùng lúc. | `libs.bundles.junit.runtime` |
| **Plugin alias** | Alias cho plugin ID và version. | `libs.plugins.versions` |
| **Catalog name** | Tên extension chứa một catalog trong build. | `libs` mặc định, hoặc `testLibs` được đăng ký riêng. |

Ví dụ:

```toml
[versions]
guava = "33.3.1-jre"

[libraries]
guava = { module = "com.google.guava:guava", version.ref = "guava" }
```

Ở đây tên `guava` xuất hiện trong **hai namespace khác nhau**: `[versions]` để mô tả phiên bản và `[libraries]` để mô tả module. `libs.guava` là provider cho library; `libs.versions.guava` là accessor của version. Khai báo dependency bằng `implementation libs.guava`, không bằng `implementation libs.versions.guava` vì cái sau chỉ là thông tin version, thiếu group/name.

## 3. File chuẩn gradle/libs.versions.toml

Gradle tự phát hiện và import file **`gradle/libs.versions.toml` ở root build** thành catalog có tên `libs`. Với file ở vị trí chuẩn, không phải đăng ký lại `libs` trong `settings.gradle`.

Cấu trúc TOML gồm bốn nhóm:

```toml
[versions]
# Các version đặt tên để tái sử dụng.
guava = "33.3.1-jre"
junit = "5.11.4"

[libraries]
# Library alias -> group:name + version.
guava = { module = "com.google.guava:guava", version.ref = "guava" }
junit-bom = { module = "org.junit:junit-bom", version.ref = "junit" }
junit-api = { module = "org.junit.jupiter:junit-jupiter-api" }
junit-engine = { module = "org.junit.jupiter:junit-jupiter-engine" }
junit-launcher = { module = "org.junit.platform:junit-platform-launcher" }

[bundles]
# Chỉ chứa tên các alias ở [libraries].
junit-runtime = ["junit-engine", "junit-launcher"]

[plugins]
# Không bắt buộc áp dụng plugin này trong bài lab.
versions = { id = "com.github.ben-manes.versions", version = "0.51.0" }
```

Bốn phần có vai trò riêng:

- **`[versions]`**: định nghĩa version aliases. Có thể dùng `version.ref` từ nhiều libraries; sửa một dòng làm thay đổi **requested version** của mọi alias dùng cùng version reference.
- **`[libraries]`**: định nghĩa **tọa độ dependency**. Viết dạng `module = "group:name"` hoặc `group = "...", name = "..."`; gắn `version`, `version.ref`, hoặc chủ đích **bỏ version** khi platform/BOM cung cấp constraint ở nơi sử dụng.
- **`[bundles]`**: nhóm nhiều library aliases. Bundle không tự áp dụng ở mọi module, không tạo version alignment và không chứa plugin aliases.
- **`[plugins]`**: định nghĩa plugin ID và phiên bản của plugin bên ngoài để dùng bằng `alias(libs.plugins.versions)` trong `plugins { }` của project. Nó không làm plugin tự được áp dụng.

**Vì sao ba module JUnit ở trên không ghi version?** Bài lab sẽ đưa `org.junit:junit-bom:5.11.4` vào test dependency graph bằng `platform(libs.junit.bom)`. BOM cung cấp constraints để Gradle chọn phiên bản tương ứng cho Jupiter API/Engine và Platform Launcher. **Không thể** bỏ version một cách tùy tiện cho library thông thường mà không có một nguồn constraint/version khác.

### 3.1. Các cách khai báo library

Những cách sau đều là dạng TOML hợp lệ cho **một alias**, nhưng không nên khai báo đồng thời cùng tên:

```toml
[libraries]
# Đủ ba thành phần trên một chuỗi:
lang3 = "org.apache.commons:commons-lang3:3.17.0"

# Tách group, name và version:
commons-text = { group = "org.apache.commons", name = "commons-text", version = "1.13.0" }

# Nếu sử dụng version alias từ [versions]:
guava = { module = "com.google.guava:guava", version.ref = "guava" }

# Không ghi version khi build có platform/constraint phù hợp:
junit-api = { module = "org.junit.jupiter:junit-jupiter-api" }
```

Đoạn này **chỉ minh họa cú pháp** và cần đặt trong một catalog có `[versions] guava` nếu dùng `version.ref = "guava"`. Không copy thêm nó vào file lab mục 5 vì sẽ tạo alias `guava` và `junit-api` trùng lặp.

### 3.2. Version catalog có rich versions, nhưng vẫn không phải lockfile

Ví dụ độc lập:

```toml
[libraries]
sample = { module = "com.example:sample", version = { strictly = "[1.0, 2.0[", prefer = "1.5" } }
```

TOML có thể biểu diễn rich version requirement như `require`, `strictly`, `prefer`, `reject`, `rejectAll` (theo cú pháp Gradle). Tuy nhiên đó là **yêu cầu/constraint khi alias được dùng**, không khóa toàn bộ các transitive dependencies hay đảm bảo mọi configuration có cùng resolved graph. Khi yêu cầu không tương thích, resolution có thể fail. Không nhầm `strictly` của một dependency với một BOM hoặc lockfile quản lý toàn cây.

## 4. Generated accessors: quy tắc đặt tên alias

Với catalog ở mục 3, Gradle tạo các accessor dưới đây:

| Mục TOML | Alias | Cú pháp trong Groovy DSL |
| --- | --- | --- |
| `[libraries]` | `guava` | `libs.guava` |
| `[libraries]` | `junit-bom` | `libs.junit.bom` |
| `[libraries]` | `junit-api` | `libs.junit.api` |
| `[libraries]` | `junit-engine` | `libs.junit.engine` |
| `[libraries]` | `junit-launcher` | `libs.junit.launcher` |
| `[bundles]` | `junit-runtime` | `libs.bundles.junit.runtime` |
| `[plugins]` | `versions` | `libs.plugins.versions` |
| `[versions]` | `guava` | `libs.versions.guava` |

Gradle tách các phần của alias khi có dấu gạch nối `-` hoặc underscore `_ ` theo quy tắc chuẩn hóa tên; chẳng hạn `commons-lang3` dẫn đến `libs.commons.lang3`. Một alias dạng camelCase có thể giữ accessor phẳng: `commonsLang3` → `libs.commonsLang3`.

**Đặt tên có chủ đích:** alias nên ngắn, mô tả thư viện và ổn định, ví dụ `junit-api` thay vì `test-lib-1`. Tránh đặt hai alias tạo ra cấu trúc accessor xung đột, ví dụ vừa có alias `junit` vừa có `junit-api` trong cùng `[libraries]` vì `libs.junit` có thể trở thành subgroup thay vì direct dependency accessor. Nếu cần, dùng camelCase cho tên phẳng hoặc đổi prefix theo module.

Một số từ như `class`, `extensions`, `convention` là reserved; các subgroup đầu `bundles`, `versions`, `plugins` cũng bị hạn chế đối với library aliases. Nếu gặp lỗi tạo accessors, kiểm tra tên alias và chuẩn hóa trước khi suy đoán dependency hỏng.

### 4.1. Accessor trả Provider, không phải JAR

- `libs.guava`: `Provider<MinimalExternalModuleDependency>`.
- `libs.bundles.junit.runtime`: provider cho một bundle các external module dependencies.
- `libs.plugins.versions`: `Provider<PluginDependency>`.

Gradle `dependencies` chấp nhận trực tiếp providers, nên dùng:

```groovy
dependencies {
    implementation libs.guava
}
```

Thường không cần gọi `libs.guava.get()`. Điều quan trọng là **provider mô tả dependency notation**, chứ không có nghĩa JAR đã được resolve hoặc tải tại thời điểm đọc alias.

## 5. Lab hoàn chỉnh: một catalog, Java 17+, JUnit Platform

Bài lab này vừa minh họa **đặt tên tọa độ** (Guava), **version aliases** (Guava và JUnit BOM), **bundle** (engine + launcher), vừa phân biệt catalog với cơ chế đồng bộ version của **BOM**. Nó hoạt động với Gradle Wrapper, JDK phù hợp và Maven Central có kết nối mạng. Không cần áp dụng plugin bên ngoài ở `[plugins]`.

### 5.1. Cấu trúc file

```text
catalog-lab/
├── gradlew
├── gradlew.bat
├── gradle/
│   ├── wrapper/...
│   └── libs.versions.toml
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/CatalogHello.java
    └── test/java/example/CatalogHelloTest.java
```

Wrapper được tạo bằng task `gradle wrapper` khi có Gradle thích hợp, hoặc từ một project được tạo sẵn. Nếu không có Wrapper, các lệnh `./gradlew` không tự chạy. Với Gradle 9, JVM Gradle cần Java 17 trở lên; đọc yêu cầu JDK của Gradle mà dự án đã pin.

### 5.2. settings.gradle

```groovy
rootProject.name = 'catalog-lab'
```

Không cần viết `dependencyResolutionManagement.versionCatalogs` cho file `gradle/libs.versions.toml` vì Gradle **tự import** catalog chuẩn `libs`.

### 5.3. gradle/libs.versions.toml

Đặt đúng nội dung sau vào file TOML:

```toml
[versions]
guava = "33.3.1-jre"
junit = "5.11.4"

[libraries]
guava = { module = "com.google.guava:guava", version.ref = "guava" }
junit-bom = { module = "org.junit:junit-bom", version.ref = "junit" }
junit-api = { module = "org.junit.jupiter:junit-jupiter-api" }
junit-engine = { module = "org.junit.jupiter:junit-jupiter-engine" }
junit-launcher = { module = "org.junit.platform:junit-platform-launcher" }

[bundles]
junit-runtime = ["junit-engine", "junit-launcher"]

[plugins]
versions = { id = "com.github.ben-manes.versions", version = "0.51.0" }
```

**Tự kiểm tra ý nghĩa:**

1. Alias `guava` trỏ đến dependency `com.google.guava:guava:33.3.1-jre`.
2. Alias `junit-bom` trỏ đến `org.junit:junit-bom:5.11.4`.
3. `junit-api`, `junit-engine`, `junit-launcher` không tự có version; chúng sẽ nhờ BOM trong test graph.
4. Bundle `junit-runtime` chỉ gom **hai module runtime**; nó không chứa `junit-api` vì API phục vụ compile test.
5. Plugin alias `versions` được định nghĩa nhưng **không được áp dụng** trong lab; không cần tải plugin để chạy `run`/`test`.

### 5.4. build.gradle (Groovy DSL)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    // Mã main dùng Guava qua alias, không ghi group:name:version tại đây.
    implementation libs.guava

    // Catalog đặt tên tọa độ BOM; chính platform() cung cấp constraints.
    testImplementation platform(libs.junit.bom)
    testImplementation libs.junit.api

    // Một bundle = hai thư viện chỉ cần khi thực thi test.
    testRuntimeOnly libs.bundles.junit.runtime
}

application {
    mainClass = 'example.CatalogHello'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

Giải thích:

- `id 'application'` áp dụng plugin Gradle tích hợp. Nó cung cấp hỗ trợ Java, `run` và `test`; không cần định nghĩa alias plugin này.
- `repositories { mavenCentral() }` quyết định **nơi** Gradle tìm modules. Catalog không khai báo repository thay bạn.
- `implementation libs.guava` tương đương một yêu cầu `implementation 'com.google.guava:guava:33.3.1-jre'`, với lợi ích có tên và được gom tọa độ.
- `platform(libs.junit.bom)` dùng **BOM** để cung cấp constraints cho test modules. Catalog chỉ giúp tham chiếu BOM qua alias.
- `testImplementation libs.junit.api` đưa JUnit annotations/assertions vào test compile/runtime.
- `testRuntimeOnly libs.bundles.junit.runtime` thêm Jupiter Engine và JUnit Platform Launcher ở runtime của test. Khi dùng JUnit 5 với Gradle hiện đại, khai báo launcher tường minh là cách đáng tin cậy.
- `useJUnitPlatform()` chọn test runner, **không tự thêm dependencies**.

**BOM quyết định version:** JUnit BOM `5.11.4` quản lý Jupiter `5.11.4` và các module JUnit Platform tương ứng `1.11.4`. Do BOM đã tham gia `testImplementation`, constraints có hiệu lực trong test runtime graph. Nếu bỏ `platform(libs.junit.bom)` khỏi script mà không thêm version/constraint khác, các thư viện JUnit không có version trong TOML có thể không resolve được.

### 5.5. Mã Java sản phẩm

**`src/main/java/example/CatalogHello.java`:**

```java
package example;

import com.google.common.base.Joiner;
import java.util.List;

public final class CatalogHello {
    private CatalogHello() {
    }

    public static String message() {
        return Joiner.on("-").join(List.of("gradle", "catalog", "ok"));
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

`Joiner` đến từ Guava được khai báo bằng `libs.guava`. `List.of(...)` có trong Java 9+, nên Java 17+ phù hợp. Đoạn này không dùng reflection, không phụ thuộc locale và có output ổn định.

### 5.6. Mã Java kiểm thử

**`src/test/java/example/CatalogHelloTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CatalogHelloTest {
    @Test
    void joinsWordsWithDashes() {
        assertEquals("gradle-catalog-ok", CatalogHello.message());
    }
}
```

Test source **import JUnit Jupiter API**, vì thế alias `libs.junit.api` nằm ở `testImplementation`. Test engine/launcher được load lúc chạy qua `testRuntimeOnly`. Đây là ví dụ cho thấy **alias và scope là hai khái niệm độc lập**: catalog đặt tên dependency, còn `implementation`/`testImplementation`/`testRuntimeOnly` diễn đạt thời điểm dùng nó.

### 5.7. Chạy chương trình

Linux/macOS:

```bash
./gradlew -q run --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat -q run --console=plain
```

**Stdout của chương trình** (không tính thông điệp khác của Gradle/JVM):

```text
gradle-catalog-ok
```

Giải thích chính xác: `List.of("gradle", "catalog", "ok")` tạo ba chuỗi, `Joiner.on("-")` nối chúng với dấu gạch ngang; `System.out.println` in một dòng cùng newline cuối. Nếu Gradle không truy cập được Maven Central và Guava chưa có trong cache, task có thể **thất bại trước khi chạy Java**; đó là lỗi mạng/repository, không phải lỗi alias tự thân.

### 5.8. Chạy kiểm thử

Linux/macOS:

```bash
./gradlew clean test --console=plain
```

PowerShell:

```powershell
.\gradlew.bat clean test --console=plain
```

Với các file và dependency đã tải đúng, JUnit thực thi **một** bài test `joinsWordsWithDashes` và kết quả **PASS**. Phần log test có thể tương tự:

```text
CatalogHelloTest > joinsWordsWithDashes() PASSED
BUILD SUCCESSFUL
```

Đây là **trích đoạn minh họa**, không phải toàn bộ stdout. Gradle có thể in tên task, daemon, thời gian hoặc thông tin `UP-TO-DATE` tùy môi trường. Report HTML test thường ở `build/reports/tests/test/index.html`, XML ở `build/test-results/test/`.

### 5.9. Xem tọa độ thực đã resolve

```bash
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencies --configuration testRuntimeClasspath
./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency com.google.guava:guava
```

Trong `runtimeClasspath` của main, cần tìm `com.google.guava:guava:33.3.1-jre` và các transitive modules Guava yêu cầu. Không suy đoán báo cáo chỉ có một dòng, vì transitive dependencies phụ thuộc metadata.

Trong `testRuntimeClasspath`, cần tìm `org.junit.jupiter:junit-jupiter-api`, `junit-jupiter-engine` và `org.junit.platform:junit-platform-launcher` với versions được BOM chọn. Báo cáo có thể hiển thị dấu `(c)` cho constraints của BOM. Dùng `dependencyInsight` khi muốn biết **requested** và **selected** versions cùng lý do lựa chọn.

## 6. Catalog đặt tên và tập trung tọa độ — không áp đặt resolved version

Đây là điểm rất quan trọng khi sử dụng catalog trong nhiều subproject.

### 6.1. Catalog chỉ tạo yêu cầu khi một alias được dùng

```toml
[versions]
guava = "33.3.1-jre"

[libraries]
guava = { module = "com.google.guava:guava", version.ref = "guava" }
```

Nếu `:app` khai báo `implementation libs.guava`, Gradle nhận yêu cầu Guava 33.3.1-jre **ở configuration tương ứng của :app**. Nếu `:service` không sử dụng alias này, chỉ vì TOML có `guava` mà `:service` **không tự có Guava**.

Version catalog **không phải** một lệnh khai báo toàn bộ dependencies cho mọi project. Nó là **bảng danh mục có thể chọn dùng**.

### 6.2. Conflicts có thể chọn phiên bản khác catalog

Giả sử `:app` đang dùng `libs.guava`, và một dependency khác trong **cùng resolved configuration** yêu cầu Guava mới hơn; ví dụ bên dưới chỉ dùng để quan sát conflict:

```groovy
dependencies {
    implementation libs.guava
    implementation 'com.google.guava:guava:33.4.0-jre'
}
```

Nếu không có `strictly`, rule hay constraint khác, Gradle thông thường chọn `33.4.0-jre` theo conflict resolution. Báo cáo có thể có dạng:

```text
com.google.guava:guava:33.3.1-jre -> 33.4.0-jre
```

Điều này **không có nghĩa catalog bị bỏ qua**: nó đã cung cấp yêu cầu 33.3.1-jre, sau đó **dependency resolution** chọn một version khác khi tổng hợp graph. Đọc:

```bash
./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency com.google.guava:guava
```

Để xác định thực tế hãy đọc `Selection reasons` như `By conflict resolution`, `By constraint`, `Forced`, hoặc `Selected by rule`. Đoạn thêm direct dependency 33.4.0-jre là **thử nghiệm độc lập**, không đưa vào file lab chuẩn mục 5.

**Sửa `gradle/libs.versions.toml` chỉ thay yêu cầu của các alias phụ thuộc version đó; chưa chắc đổi selected version.** Để thay đổi kết quả giải quyết thật sự, phải xét platform/constraints, transitive dependencies, lockfiles và rules.

### 6.3. Catalog và platform/BOM khác mục đích

| Công cụ | Trả lời câu hỏi | Tác động lên graph |
| --- | --- | --- |
| **Version catalog** | “Tên ngắn của thư viện/plugin là gì, tọa độ/version yêu cầu nào được dùng?” | Khi được tham chiếu, thêm yêu cầu dependency hoặc plugin vào đúng scope; **không tự đồng bộ tất cả versions**. |
| **Platform / Maven BOM** | “Các module liên quan nên dùng versions tương thích nào?” | Thêm constraints để **điều phối việc chọn version** trên graph tiêu thụ platform. |
| **Dependency constraints** | “Khi module hiện diện, version nào được yêu cầu/ưu tiên/giới hạn?” | Tham gia trực tiếp vào version selection. |
| **Dependency locking** | “Version đã giải quyết nào cần được cố định để build tái lập?” | Ghi/truy xét trạng thái resolved versions theo configurations được lock. |
| **Repository** | “Metadata/artifacts được tìm ở đâu?” | Cung cấp nguồn tải; không do catalog tự tạo. |

Trong lab, `libs.junit.bom` là **catalog alias trỏ đến tọa độ BOM**, nhưng `platform(libs.junit.bom)` mới là lời yêu cầu **tiêu thụ BOM như platform**. Nếu chỉ khai báo tên JUnit BOM trong TOML mà không dùng platform, chẳng có constraint nào được thêm vì riêng hành động định nghĩa alias.

### 6.4. Catalog không thay thế scope

Cùng một alias có thể được dùng khác nhau:

```groovy
dependencies {
    implementation libs.guava

    // Chỉ là ví dụ: thư viện nào được test source import thì khai báo ở test scope.
    testImplementation libs.junit.api
}
```

`implementation` và `testImplementation` quyết định **classpath**. `libs.guava`/`libs.junit.api` chỉ cung cấp **tọa độ**. Catalog không tự hiểu thư viện là compile, runtime, test hay annotation processor.

## 7. Plugin alias: cùng cách đặt tên, nhưng API dùng khác

Section `[plugins]` trong lab:

```toml
[plugins]
versions = { id = "com.github.ben-manes.versions", version = "0.51.0" }
```

Tương ứng với cú pháp trong `build.gradle` của **một project muốn áp dụng plugin**:

```groovy
plugins {
    id 'java'
    alias(libs.plugins.versions)
}
```

Đoạn trên là **một build script thay thế**, không thêm nó vào lab ở mục 5 nếu không có nhu cầu chạy plugin hoặc truy cập Gradle Plugin Portal. `libs.plugins.versions` là alias cho **plugin marker/ID và version**, không phải một library như `libs.guava`. Plugin resolution sử dụng repository/cơ chế riêng, thường qua `pluginManagement.repositories` trong `settings.gradle`, không đồng nhất với `repositories { mavenCentral() }` dành cho project dependencies.

Các plugin core như `java`, `application`, `java-library` có thể áp dụng trực tiếp bằng `id 'java'` mà không cần version alias. Bạn **không thể** dùng plugin alias từ version catalog trong `plugins { }` của chính `settings.gradle` hoặc settings plugin theo cơ chế thông thường, vì catalog chưa sẵn có ở thời điểm đó.

**Không lạm dụng plugin alias để giải quyết vấn đề dependency:** Một plugin được áp dụng có thể thêm tasks/configurations, nhưng việc tập trung tên plugin trong TOML không tự đồng bộ runtime dependencies của ứng dụng.

## 8. Bundle là shortcut khai báo, không phải platform

Bundle trong lab:

```toml
[bundles]
junit-runtime = ["junit-engine", "junit-launcher"]
```

Khi `testRuntimeOnly libs.bundles.junit.runtime`, Gradle thêm **hai yêu cầu thư viện** vào test runtime configuration. Bundle:

- Không quy định rằng cả hai phiên bản bắt buộc đồng nhất.
- Không giải quyết xung đột thay BOM/constraints.
- Không tạo source set hoặc dependency configuration mới.
- Không tự kích hoạt nếu không có dòng `testRuntimeOnly`.
- Không nhận tên plugin alias; entries của bundle phải là alias trong `[libraries]`.

**Thiết kế bundle theo nhóm thường đi cùng nhau**: ví dụ JUnit engine/launcher runtime, Groovy core/json modules, HTTP client/serialization helpers. Không gom các dependencies có **scope khác nhau** vào một bundle rồi dùng một configuration để khai báo tất cả nếu sẽ làm rò rỉ runtime-only vào compile.

Nếu nhóm có bundle `logging` gồm API và runtime binding, hãy cân nhắc tách `logging-api` và `logging-runtime` để modules lựa chọn chính xác. Shortcut tốt làm rõ mục đích, không che scope.

## 9. Đổi phiên bản ở một nơi: quy trình nâng cấp an toàn

Giả sử nhóm muốn nâng Guava sau khi đánh giá changelog, CVE và compatibility:

**Trước** trong `gradle/libs.versions.toml`:

```toml
[versions]
guava = "33.3.1-jre"
```

**Sau** (ví dụ một version cố định khác đã phát hành):

```toml
[versions]
guava = "33.4.0-jre"
```

Nếu mọi alias Guava dùng `version.ref = "guava"`, đây là nơi cần chỉnh **requested version** cho các modules tham chiếu alias đó. Nhưng **không kết luận đã nâng cấp thành công** chỉ vì sửa TOML.

Quy trình:

1. Ghi baseline: `./gradlew -q dependencies --configuration runtimeClasspath` và `dependencyInsight` cho module bị tác động.
2. Kiểm tra version mới có thực ở repository được cấu hình, chính sách license và bảo mật.
3. Thay version alias trong TOML, không sửa tùy tiện các scope/constraints khác.
4. Chạy lại báo cáo với **đúng project/configuration** (compile, runtime, test, Android variant nếu có).
5. Đọc selected version và selection reasons để xem BOM, constraints, force hay lockfile có ảnh hưởng.
6. Chạy `./gradlew clean test` hoặc task kiểm thử thích hợp; với thư viện runtime, chạy smoke/integration tests.
7. Review dependency lockfiles và verification metadata nếu build dùng các cơ chế này; không tự chạy `--write-locks` chỉ để “xem” vì cờ có thể cập nhật lock state.
8. Lập PR với lý do thay đổi và kết quả kiểm thử, không chỉ con số version mới.

**Một thay đổi có thể tác động nhiều subprojects**: đó là lợi ích của tập trung khai báo, đồng thời là lý do nên review phạm vi ảnh hưởng. Nếu hai subprojects cần hai phiên bản vì policy/compatibility khác nhau, đặt hai version aliases có chủ đích hoặc dùng platform/constraints theo kiến trúc phù hợp; không ép mọi thứ về một version alias nếu làm sai nhu cầu.

## 10. Dùng catalog trong multi-project builds

Giả sử một build có cấu trúc:

```text
large-build/
├── settings.gradle
├── gradle/libs.versions.toml
├── app/build.gradle
└── shared/build.gradle
```

Trong `settings.gradle`, dự án được include:

```groovy
rootProject.name = 'large-build'
include 'app', 'shared'
```

Cả `app/build.gradle` và `shared/build.gradle` đều có thể dùng **cùng** accessor `libs.guava`:

```groovy
// app/build.gradle — giả sử plugin Java đã được áp dụng ở app
dependencies {
    implementation libs.guava
}
```

```groovy
// shared/build.gradle — giả sử plugin Java đã được áp dụng ở shared
dependencies {
    implementation libs.guava
}
```

Hai đoạn trên thuộc **hai file khác nhau** và đều giả định project có configuration `implementation`. Catalog được tạo cho build và có thể dùng trong các subprojects, nhưng **mỗi project vẫn có dependency graph và các configurations riêng**. Điều này không có nghĩa Gradle tự thêm Guava vào những project không dùng alias.

### 10.1. buildSrc và included builds là build khác

`buildSrc` có build logic và lifecycle riêng, **không tự thừa hưởng** version catalog của root build. Nếu muốn sử dụng cùng TOML trong `buildSrc`, cần import tường minh trong `buildSrc/settings.gradle`:

```groovy
dependencyResolutionManagement {
    versionCatalogs {
        create('libs') {
            from(files('../gradle/libs.versions.toml'))
        }
    }
}
```

Đoạn này phải được đặt trong **`buildSrc/settings.gradle`**, không thay thế `settings.gradle` của project root. Khi import, buildSrc có thể tham chiếu catalog của chính buildSrc theo API Gradle phù hợp; cách dùng plugin aliases trong precompiled script plugins có những giới hạn riêng, không được giả định y hệt `plugins { alias(...) }` ở module application.

Các **included builds** dùng cho composite/convention plugins cũng là những builds có settings và catalog riêng; việc root có `libs` **không tự động** chia sẻ catalog. Cần thiết kế import hoặc công bố catalog có chủ đích cho mỗi build.

## 11. Nhiều catalogs, import từ file khác và publish catalog

### 11.1. Đăng ký thêm catalog có tên khác

Ngoài `gradle/libs.versions.toml` auto-import, có thể tạo `gradle/tools.versions.toml` và đăng ký trong **`settings.gradle`**:

```groovy
dependencyResolutionManagement {
    versionCatalogs {
        create('tools') {
            from(files('gradle/tools.versions.toml'))
        }
    }
}
```

Từ đó, nếu `tools.versions.toml` có library alias `errorprone-annotations`, build script dùng `tools.errorprone.annotations` thay vì `libs.errorprone.annotations`. Đừng dùng tên catalog trùng extension của plugin hoặc tên hệ thống. Với hầu hết builds, **một `libs.versions.toml` đặt alias theo prefix rõ ràng là đủ**; chỉ tách catalog khi có nhu cầu cụ thể như tách toolchain, runtime, test hay chia sẻ giữa builds.

**Giới hạn `from()`:** đối với một catalog builder, chỉ import **một file/nguồn** bằng `from(...)`. Không thể gọi `from(files('a.toml'))` rồi `from(files('b.toml'))` liên tiếp để tự gộp hai TOML. Các file catalogs là độc lập; `version.ref` không tham chiếu trực tiếp version alias trong một catalog khác.

### 11.2. Dùng catalog được publish

Tổ chức có nhiều repositories có thể publish catalog như artifact và import trong settings:

```groovy
dependencyResolutionManagement {
    repositories {
        mavenCentral() // Thay bằng repository chứa catalog do tổ chức công bố.
    }
    versionCatalogs {
        create('orgLibs') {
            from('com.example.build:company-catalog:1.0')
        }
    }
}
```

Đoạn này **minh họa cách import**, tọa độ `com.example.build:company-catalog:1.0` không phải artifact công khai bảo đảm có thật. Ở project dùng `orgLibs.some.alias` theo những aliases đã được tổ chức publish.

Gradle hỗ trợ plugin `version-catalog` kết hợp `maven-publish` để xuất bản catalog từ TOML hoặc catalog extension. Đó là **một versioned artifact giúp các builds chia sẻ danh mục tọa độ**, không phải BOM; consumer vẫn quyết định scope và Gradle vẫn resolve dependency graph theo rules/constraints của build. Quản lý version catalog artifact như dependency build-logic quan trọng: review, pin version, cập nhật có kiểm soát.

## 12. Những điều catalog không biểu diễn trực tiếp

TOML version catalog chủ yếu lưu **group, name, version**, plugin ID và versions, bundle names. Nó **không** hỗ trợ khai báo trực tiếp trong entry TOML:

- Classifier (ví dụ `sources`/`tests`) và loại artifact/extension như `@zip`.
- Exclusion rules `exclude group: ..., module: ...`.
- Capability requirements hoặc variant-specific attributes.
- Repository URL, credentials, content filters.
- Mọi dependency scope của project như `implementation`/`runtimeOnly`/`testImplementation`.

Với dependency cần loại một transitive module, có thể cấu hình **tại nơi sử dụng alias**:

```groovy
dependencies {
    implementation(libs.guava) {
        exclude group: 'com.google.code.findbugs', module: 'jsr305'
    }
}
```

Đây là **ví dụ cú pháp không áp dụng vào lab**, không phải lời khuyên bỏ `jsr305` trong ứng dụng thật. Exclusion phải dựa trên báo cáo graph và runtime tests, vì module có thể vẫn được dependency khác kéo vào hoặc thật sự cần thiết. Nếu muốn yêu cầu capability/variant riêng, dùng API dependency declaration tương ứng của Gradle và tra metadata nhà xuất bản; không cố nhét thuộc tính không được hỗ trợ vào TOML.

Nếu một project cần khai báo `files('libs/local.jar')`, catalog cũng không tự biến file cục bộ thành module tọa độ Maven. Chỉ library từ repository được công bố đúng metadata mới đạt đầy đủ lợi ích quản lý dependency bằng tọa độ.

## 13. Lỗi phổ biến khi bắt đầu dùng version catalog

| Triệu chứng | Vì sao xảy ra | Cách xác minh và sửa |
| --- | --- | --- |
| `Could not get unknown property 'libs'` hoặc không nhận `libs` | File sai vị trí/tên; buildSrc/included build không có catalog; trùng tên extension. | Đặt đúng `gradle/libs.versions.toml` ở root build; import riêng cho buildSrc; xem settings. |
| `libs.junitApi` không tồn tại | TOML có alias `junit-api`, sinh ra accessor `libs.junit.api`, không phải `libs.junitApi`. | Dùng đúng accessor hay đổi alias sang camelCase rồi cập nhật tất cả nơi dùng. |
| Alias có từ khóa reserved hoặc collision | `class`, `extensions` hoặc tên dẫn đến subgroup xung đột. | Đổi alias, dùng prefix hoặc camelCase hợp lý. |
| TOML parse fail | Trùng key, sai dấu quote, cú pháp table/inline object sai, tham chiếu version alias không tồn tại. | Validate cú pháp TOML và từng `version.ref`; đọc lỗi Gradle tại dòng liên quan. |
| Module không tìm thấy dù alias đúng | Catalog không khai báo repository hoặc tọa độ/module/version thực sự không tồn tại. | Đọc repository và `dependencies`/log `Could not find`; kiểm tra Maven Central/private repo. |
| Selected version khác `[versions]` | Conflict, constraint, BOM, enforced platform, rule hoặc lockfile tác động. | Chạy `dependencyInsight` trên đúng resolvable configuration. |
| Thay catalog nhưng phiên bản không đổi | Module được chọn bởi source khác hoặc alias không được sử dụng ở configuration đang xem. | Truy mọi paths; xác nhận build script dùng alias và report before/after. |
| Đặt library chỉ trong TOML nhưng classpath rỗng | Định nghĩa alias **không tự thêm dependency**. | Thêm `implementation libs.x` hoặc scope đúng vào project. |
| Viết `alias(libs.guava)` trong `plugins { }` | Library accessor khác plugin accessor. | Dùng `alias(libs.plugins.xxx)` cho plugin, `implementation libs.guava` cho library. |
| Viết `implementation libs.plugins.versions` | Plugin alias không phải module dependency runtime của ứng dụng. | Phân biệt `[plugins]` và `[libraries]`. |
| Bundle làm compile classpath có runtime-only libs | Đã gom API + engine/driver vào một bundle rồi gọi `testImplementation`. | Tách bundle theo nhu cầu compile/runtime, dùng đúng configurations. |
| JUnit versionless modules không resolve | Bỏ `platform(libs.junit.bom)` nhưng giữ entries không version. | Khôi phục BOM hoặc thêm version/constraint tương thích. |
| BuildSrc không nhận catalog root | BuildSrc là build riêng. | Import TOML trong `buildSrc/settings.gradle`, dùng API hợp lệ cho build logic. |
| Plugin alias không dùng được ở `settings.gradle` | Catalog chưa được tạo tại thời điểm settings plugins block. | Khai báo plugin resolution trong `pluginManagement` hoặc cơ chế settings hỗ trợ. |
| Chia TOML thành hai file rồi `from()` hai lần | Một catalog builder chỉ chấp nhận một import `from`. | Tạo hai catalog có tên khác hoặc thống nhất nội dung; không gộp bằng hai `from()`. |
| Muốn `@zip`, classifier, exclude trong TOML | Catalog format không hỗ trợ đầy đủ thông tin đó. | Cấu hình tại dependency declaration hoặc API Gradle phù hợp. |
| `--refresh-dependencies` không đổi version | Cờ refresh kiểm tra cache, không viết lại constraints/selection rules. | Phân tích graph, lock và rules; sửa nguyên nhân thay vì xóa cache. |

### 13.1. Chẩn đoán đúng sai biệt requested → selected

Nếu version bạn thấy trong `gradle/libs.versions.toml` khác version trên classpath:

```bash
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency com.google.guava:guava
```

Đọc `requested -> selected` và `Selection reasons`. Nếu configuration thuộc subproject `:app` thì thêm prefix `:app:dependencies` và `:app:dependencyInsight` đúng nơi. Đừng chạy `dependencies` trên root rồi suy ra tất cả subprojects có graph giống nhau.

## 14. Mẫu quy ước đặt tên alias cho nhóm

Version catalog càng lớn càng cần tên có tổ chức:

| Loại | Alias gợi ý | Accessor | Giải thích |
| --- | --- | --- | --- |
| Library production đơn | `guava` | `libs.guava` | Tên module ngắn, quen thuộc. |
| Library có nhiều artifacts | `jackson-databind` | `libs.jackson.databind` | Prefix theo hệ sinh thái. |
| Version dùng chung | `junit` trong `[versions]` | `libs.versions.junit` | Một nơi quản lý requested version. |
| JUnit API | `junit-api` | `libs.junit.api` | Tách rõ compile-time API. |
| JUnit Engine | `junit-engine` | `libs.junit.engine` | Runtime component. |
| Test runtime bundle | `junit-runtime` | `libs.bundles.junit.runtime` | Nhóm module cùng scope. |
| Plugin version report | `versions` trong `[plugins]` | `libs.plugins.versions` | Plugin alias, không phải library. |

**Quy tắc thực dụng:** đặt tên theo sản phẩm/hệ sinh thái (Guava, JUnit, Jackson...) hơn là theo phiên bản hoặc dự án tiêu thụ. Tránh alias quá chung như `core` nếu trong tổ chức có nhiều “core”. Với alias được dùng rộng rãi, đổi tên gây lỗi build ở nhiều file dù tọa độ không đổi; coi alias như một phần API nội bộ của build logic.

Không cần tạo hai catalog chỉ để phân biệt production/test khi một catalog với prefix rõ ràng đã đủ. Việc các alias nằm cùng TOML **không khiến test libraries bị kéo vào production**: phạm vi vẫn được quyết định tại nơi sử dụng.

## 15. Bài tập tự luyện

**Bài 1 — Từ tọa độ sang alias.** Với dependency `org.apache.commons:commons-lang3:3.17.0`, tạo version alias `commons = "3.17.0"`, library alias `commons-lang3` dùng `version.ref`. Viết dependency khai báo trong Groovy DSL. Đáp án cốt lõi: `implementation libs.commons.lang3`.

**Bài 2 — Đọc bốn section.** Với catalog lab mục 5, giải thích `[versions]`, `[libraries]`, `[bundles]`, `[plugins]`. Vì sao `junit-runtime` không thể chứa plugin alias `versions`?

**Bài 3 — Đặt tên.** Alias `junit-jupiter-api` sinh ra accessor nào? Đáp án: `libs.junit.jupiter.api`. Nếu muốn `libs.junitJupiterApi`, cần đặt alias theo camelCase tương ứng và thay các nơi tham chiếu.

**Bài 4 — Catalog không tải thư viện.** Xóa dòng `implementation libs.guava` khỏi lab nhưng giữ `[libraries] guava`. Dự đoán `compileJava` gặp lỗi gì và vì sao? Cần khai báo ở configuration để library thực sự tham gia classpath.

**Bài 5 — BOM và versionless entries.** Bỏ `testImplementation platform(libs.junit.bom)` trong lab, giữ ba aliases JUnit không version. Giải thích vì sao catalog không tự giải quyết phiên bản thích hợp. Khôi phục BOM sau khi thử.

**Bài 6 — Selected version.** Thêm trong bản sao lab một yêu cầu trực tiếp `com.google.guava:guava:33.4.0-jre` bên cạnh `libs.guava`. Chạy `dependencyInsight`, ghi requested và selected. Vì sao version catalog không ép `33.3.1-jre`?

**Bài 7 — Plugin alias.** Alias `[plugins] versions` được gọi ở đâu? Có hợp lệ trong `settings.gradle plugins { }` không? Có nên khai báo ở `dependencies { implementation ... }` không?

**Bài 8 — buildSrc.** Một project dùng `gradle/libs.versions.toml`, nhưng `buildSrc` báo không thấy `libs`. Tạo `buildSrc/settings.gradle` để import TOML từ root. Nêu lý do `from(files('../gradle/libs.versions.toml'))` chỉ được gọi một lần.

**Bài 9 — Scope.** Có ba libraries: API assertion được test import, test engine runtime, và Guava được main import. Chọn `testImplementation`, `testRuntimeOnly`, `implementation` và giải thích vì sao alias không quyết định scope.

**Bài 10 — Quy trình upgrade.** Đề xuất checklist khi nâng version alias ảnh hưởng năm subprojects: report before/after, constraints/BOM, locked versions, test, runtime compatibility và review bảo mật.

### Tự kiểm tra nhanh

1. **Định nghĩa `guava` trong catalog có tự thêm Guava vào mọi module?** Không.
2. **`libs.guava` biểu diễn gì?** Một provider cho tọa độ thư viện theo alias.
3. **Một version catalog có tự áp đặt resolved version không?** Không; Gradle vẫn giải quyết toàn graph.
4. **Bundle có thay thế BOM không?** Không; bundle nhóm dependency aliases, BOM đóng góp constraints.
5. **File chuẩn nào tự được Gradle import?** `gradle/libs.versions.toml` của root build.
6. **Library alias `junit-api` có accessor nào?** `libs.junit.api`.
7. **`libs.plugins.versions` dùng ở đâu?** `alias(...)` trong `plugins { }` của project.
8. **Catalog có lưu repository credentials không?** Không.
9. **buildSrc có tự dùng được root libs không?** Không; cần import riêng nếu muốn chia sẻ.
10. **Muốn biết version JAR cuối cùng, xem gì?** `dependencies`/`dependencyInsight` trên đúng resolvable configuration.

## 16. Tài liệu chính thức

- **Gradle — Version Catalogs:** TOML, generated accessors, libraries, bundles, plugins, reserved names và limitations: https://docs.gradle.org/current/userguide/version_catalogs.html
- **Gradle — Using Catalogs with Platforms:** phân biệt alias tập trung tọa độ với platform điều phối versions: https://docs.gradle.org/current/userguide/centralizing_catalog_platform.html
- **Gradle — Platforms:** `platform(...)` và BOM constraints: https://docs.gradle.org/current/userguide/platforms.html
- **Gradle — Declaring Dependencies:** sử dụng dependencies trong các configurations: https://docs.gradle.org/current/userguide/declaring_dependencies.html
- **Gradle — Declaring Configurations:** declarable/resolvable/consumable và scopes: https://docs.gradle.org/current/userguide/declaring_configurations.html
- **Gradle — Viewing and Debugging Dependencies:** `dependencies`, `dependencyInsight` và selection reasons: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- **Gradle — Dependency Constraints:** `strictly`, `prefer`, version alignment: https://docs.gradle.org/current/userguide/dependency_constraints.html
- **Gradle — Dependency Locking:** cố định resolved versions để tái lập builds: https://docs.gradle.org/current/userguide/dependency_locking.html
- **Gradle — JVM Testing:** JUnit Jupiter Engine và Platform Launcher trong test runtime: https://docs.gradle.org/current/userguide/java_testing.html
- **Gradle — Publishing a Version Catalog:** https://docs.gradle.org/current/userguide/version_catalog_plugin.html

**Kết luận:** Version catalog tạo **ngôn ngữ đặt tên chung** cho tọa độ và phiên bản được yêu cầu: `libs.guava`, `libs.junit.api`, `libs.bundles.junit.runtime`, `libs.plugins.versions`. Nó giảm lặp và giúp bảo trì tập trung, nhưng **không tự thêm dependency, không chọn scope, không khai báo repository, không ép version hoặc thay thế BOM/lockfile**. Dùng đúng alias trong configuration thích hợp, rồi kiểm tra resolved graph và test trước khi kết luận nâng cấp thành công.