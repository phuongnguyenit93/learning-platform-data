# Khai báo dependency theo chuỗi tọa độ và dạng có cấu trúc trong Gradle

## 1. Khái niệm: một dependency có danh tính và phạm vi sử dụng

Gradle quản lý các thành phần mà project cần để **biên dịch**, **kiểm thử**, **chạy** hoặc **đóng gói** sản phẩm. Một *external module dependency* được xuất bản trên một kho như Maven Central thường có ba trường danh tính:

- **group:** namespace của bên xuất bản, chẳng hạn `org.apache.commons`.
- **name:** tên module/artifact, chẳng hạn `commons-lang3`.
- **version:** phiên bản được yêu cầu, chẳng hạn `3.17.0`.

Ba thành phần tạo ra **tọa độ GAV** (*group:artifact/version* hay *group:name:version*):

```text
org.apache.commons:commons-lang3:3.17.0
└────── group ─────┘ └── name ──┘ └version┘
```

Trong Gradle, có thể khai báo cùng một module bằng **chuỗi tọa độ** (string notation) hoặc kiểu **có cấu trúc** ghi group/name/version riêng. Tuy vậy, cần phân biệt **hai dạng có cấu trúc hoàn toàn khác nhau**:

1. **Map/named arguments đặt trực tiếp trong `implementation(...)`:** thường thấy ở build cũ, hiện **deprecated từ Gradle 9.1** và theo tài liệu Gradle 9.x sẽ **không được hỗ trợ trong Gradle 10**.
2. **Map cấu trúc của version catalog TOML:** vẫn là cơ chế hiện đại để quản lý group/name/version tập trung, **không chịu deprecation nói trên**.

Vì thế, với code mới hãy ưu tiên **một chuỗi GAV** hoặc **alias từ version catalog**; học dạng map cũ để đọc hiểu, chẩn đoán và chuyển đổi an toàn.

### Mục tiêu học tập

Sau khi học xong, bạn cần phân biệt được notation, xác định đúng configuration/repository, chuyển Groovy DSL ↔ Kotlin DSL, hiểu vì sao version yêu cầu khác version đã được chọn, sử dụng catalog/constraints và tự kiểm chứng dependency bằng lệnh Gradle.

## 2. Configuration đứng ngoài chuỗi GAV

Xét:

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

`implementation` là **dependency configuration** — bucket cho biết dependency được dùng trong hoàn cảnh nào. Nó **không nằm trong GAV**; chuỗi GAV chỉ mô tả module và version cần tìm.

| Phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Configuration | `implementation` | Đặt thư viện vào classpath/biến thể tương ứng của project. |
| Group | `org.apache.commons` | Namespace xuất bản. |
| Module name | `commons-lang3` | Tên module trong repository. |
| Version | `3.17.0` | Version được yêu cầu; có thể chịu conflict resolution. |
| Repository | `mavenCentral()` | Nơi tìm metadata và artifact. |
| Plugin | `java` hoặc `application` | Tạo các configuration như `implementation`. |

`group = "com.myproject"` trên `Project` nói về danh tính artifact **do project xuất bản**, không thay đổi group của module Commons Lang3 mà ứng dụng đang dùng.

Các configuration thường gặp:

- `implementation`: code triển khai cần dependency cho compile/runtime tương ứng.
- `compileOnly`: chỉ cần khi compile, không tự bổ sung vào runtime classpath.
- `runtimeOnly`: cần khi chạy nhưng không cần ở compile classpath.
- `testImplementation`: thư viện dùng để biên dịch/chạy test, không phải runtime ứng dụng.
- `testRuntimeOnly`: thư viện chỉ cần khi test runtime.
- `api`: dùng với plugin `java-library` hoặc plugin cung cấp API configuration, cho những dependency thuộc public API của thư viện.

Thay `implementation` bằng `runtimeOnly` trong khi giữ nguyên GAV **có thể làm source Java biên dịch lỗi**. Khi chuyển notation, phải bảo toàn cả configuration.

## 3. Điều kiện để declaration hoạt động

Một external module dependency cần:

1. **Plugin** tạo configuration tương ứng, như `java`, `java-library`, `application`.
2. **Repository** chứa module/version, thường khai báo bằng `repositories { mavenCentral() }` trong project hoặc `dependencyResolutionManagement.repositories` ở settings.
3. **Tọa độ hợp lệ**, và mạng, proxy, chứng thực, metadata tương thích với môi trường.

Ví dụ Kotlin DSL:

```kotlin
// build.gradle.kts
plugins {
    id("java")
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Groovy DSL:

```groovy
// build.gradle
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Hai đoạn cùng biểu diễn một dependency. **Không nhầm kho tải module với kho tải plugin**: `pluginManagement.repositories` dùng cho plugin DSL, trong khi `repositories` ở đây dùng cho module của `implementation`.

`file("...")` và `project(":core")` thuộc những loại dependency khác; không phải module tọa độ GAV. Chúng sẽ được phân biệt ở phần sau.

## 4. Cách 1: khai báo bằng chuỗi tọa độ GAV

### 4.1. Groovy DSL

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.17'
    testImplementation 'org.junit.jupiter:junit-jupiter-api:5.11.4'
}
```

Groovy cho phép bỏ ngoặc khi gọi method: `implementation 'g:n:v'` tương đương `implementation('g:n:v')`. Nháy đơn hoặc nháy kép đều có thể dùng với chuỗi tĩnh, nhưng Groovy GString trong dấu nháy kép có thể thực hiện nội suy biến.

### 4.2. Kotlin DSL

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
    runtimeOnly("org.slf4j:slf4j-simple:2.0.17")
    testImplementation("org.junit.jupiter:junit-jupiter-api:5.11.4")
}
```

Kotlin yêu cầu dấu ngoặc và String `"..."`; `'a'` là ký tự `Char`, không phải String. Các ví dụ ở mục này chủ yếu minh họa notation: cấu hình JUnit thực tế còn cần test engine phù hợp và Test task sử dụng JUnit Platform.

**Ưu điểm của GAV string:** ngắn, nhất quán giữa Groovy và Kotlin, dễ so sánh với tọa độ Maven Central, và hiện được Gradle ưu tiên cho dependency trực tiếp.

### 4.3. Đừng đảo group/name

```text
Đúng:
org.apache.commons:commons-lang3:3.17.0

Sai về ý định:
commons-lang3:org.apache.commons:3.17.0
```

Gradle không tự đoán lại thứ tự. Tọa độ có nghĩa theo dữ liệu đã publish, không dựa vào package Java của class được import.

## 5. Cách 2: dạng map hoặc named arguments trong build cũ

### 5.1. Groovy dạng có cấu trúc

```groovy
// Legacy notation — không khuyến nghị cho code mới.
dependencies {
    implementation group: 'org.apache.commons',
                   name: 'commons-lang3',
                   version: '3.17.0'
}
```

Một cách viết tương đương có ngoặc:

```groovy
dependencies {
    implementation(
        group: 'org.apache.commons',
        name: 'commons-lang3',
        version: '3.17.0'
    )
}
```

Trong Groovy, `group: ...`, `name: ...` và `version: ...` là các entry của Map. Đây là một external module dependency, **không phải ba dependency riêng**.

### 5.2. Kotlin named arguments

```kotlin
// Legacy notation — chỉ để đọc hiểu hoặc migrate.
dependencies {
    implementation(
        group = "org.apache.commons",
        name = "commons-lang3",
        version = "3.17.0"
    )
}
```

Kotlin sử dụng `=` trong dạng named arguments. Không copy cú pháp `group: '...'` của Groovy vào Kotlin. Ngược lại, đừng dùng `group = "..."` theo kiểu Kotlin trong một Map Groovy rồi cho rằng ý nghĩa giống nhau.

### 5.3. Cảnh báo Gradle 9.1 và Gradle 10

Tài liệu Gradle hiện hành ghi rõ: **map/named-argument notation của external module dependency đã deprecated từ Gradle 9.1 và sẽ bị loại bỏ trong Gradle 10**. Vì vậy:

- Cần **hiểu** để đọc build lịch sử, nhưng **không chọn** cho module mới.
- Khi nâng Gradle, hãy chuyển sang GAV string hoặc version catalog trước.
- Bật `--warning-mode all` trên Gradle Wrapper hiện có để phát hiện những deprecation trong build.
- **Không nhầm** cảnh báo này với mọi method có named arguments. Ví dụ `exclude(group = "...", module = "...")` là cấu hình loại trừ và không thuộc loại **module declaration map notation** đang bị loại bỏ.
- Đừng cùng lúc thay version, chuyển plugin, đổi repository và sửa notation nếu chỉ muốn migration an toàn.

### 5.4. Migration sang chuỗi GAV

Groovy trước và sau (**chọn một**, không để cùng lúc):

```groovy
// Trước: legacy
dependencies {
    implementation group: 'org.apache.commons',
                   name: 'commons-lang3',
                   version: '3.17.0'
}

// Sau: chỉ giữ block này khi đã chuyển
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Kotlin trước và sau (**chọn một**):

```kotlin
// Trước: legacy
dependencies {
    implementation(
        group = "org.apache.commons",
        name = "commons-lang3",
        version = "3.17.0"
    )
}

// Sau: chỉ giữ block này
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Phần `group/name/version` được giữ nguyên giá trị và thứ tự. Nếu bản cũ có `exclude`, `transitive`, `because` hoặc `version { ... }`, cần giữ những modifier đó đúng nghĩa khi đổi sang GAV.

## 6. Dạng có cấu trúc hiện đại: Version Catalog TOML

Ở build nhiều module, việc lặp phiên bản trong hàng chục build script gây khó bảo trì. Gradle cho phép đặt catalog tại `gradle/libs.versions.toml`. Dạng `group/name/version` ở **TOML** không phải map-notation deprecation của mục 5.

### 6.1. TOML tách group, name, version.ref

**`gradle/libs.versions.toml`:**

```toml
[versions]
commonsLang3 = "3.17.0"

[libraries]
commons-lang3 = { group = "org.apache.commons", name = "commons-lang3", version.ref = "commonsLang3" }
```

Gradle tự tạo `libs` catalog từ tên tệp quy ước này với những phiên bản Gradle hỗ trợ version catalogs. Alias `commons-lang3` thường sinh accessor `libs.commons.lang3`.

Trong Kotlin DSL:

```kotlin
plugins {
    id("java")
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(libs.commons.lang3)
}
```

Trong Groovy DSL:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation libs.commons.lang3
}
```

### 6.2. Những dạng khác của cùng TOML alias

Dùng một trong ba cách sau, **không khai báo trùng alias**:

**Dạng module + version reference:**

```toml
[versions]
commonsLang3 = "3.17.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang3" }
```

**Dạng chuỗi GAV trong TOML:**

```toml
[libraries]
commons-lang3 = "org.apache.commons:commons-lang3:3.17.0"
```

**Dạng group/name/version tường minh:**

```toml
[libraries]
commons-lang3 = { group = "org.apache.commons", name = "commons-lang3", version = "3.17.0" }
```

Cả ba có thể đại diện cho cùng module; chọn một kiểu phù hợp tổ chức. Catalog cho phép quản lý version tập trung, dùng alias trong code và IDE hỗ trợ completion.

### 6.3. Catalog không đóng đinh resolved version

Catalog quản lý **requested version**, nhưng Gradle vẫn áp dụng conflict resolution, platforms/constraints và variant matching khi resolve. Nếu cần **enforce** phiên bản, sử dụng rich version constraints, platform hoặc dependency locking theo chính sách dự án, chứ không dựa riêng vào cấu trúc TOML.

Version catalog thông thường không phải nơi đặt trực tiếp `exclude`, classifier hay `@zip` của một dependency. Các modifier này phải được cấu hình tại chỗ dùng hoặc thông qua mô hình dependency phù hợp.

## 7. GAV string + configuration block: cấu trúc hành vi, không dùng map notation cũ

Nếu dependency cần lý do sử dụng, exclusion hoặc chính sách version, bạn vẫn giữ dạng string hiện đại và thêm closure/lambda.

### 7.1. because: ghi lý do

Kotlin:

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0") {
        because("Cần các hàm xử lý chuỗi đã chuẩn hóa")
    }
}
```

Groovy:

```groovy
dependencies {
    implementation('org.apache.commons:commons-lang3:3.17.0') {
        because 'Cần các hàm xử lý chuỗi đã chuẩn hóa'
    }
}
```

`because` cung cấp thông tin giải thích khi quản trị dependency; nó không biến thư viện thành plugin.

### 7.2. Version constraint: strictly

Kotlin:

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3") {
        version {
            strictly("3.17.0")
        }
    }
}
```

Groovy:

```groovy
dependencies {
    implementation('org.apache.commons:commons-lang3') {
        version {
            strictly '3.17.0'
        }
    }
}
```

`strictly("3.17.0")` thể hiện yêu cầu phiên bản chặt hơn một GAV thông thường. Nếu những constraints khác trong graph xung đột không thể giải quyết, Gradle có thể báo lỗi thay vì âm thầm chọn version không phù hợp. Không dùng `strictly` cho mọi module nếu chưa có chính sách tương thích rõ ràng; `require`, `prefer` và `reject` cũng là các công cụ rich versions hữu ích.

**Chú ý:** GAV `"g:n:1.0"` bình thường mô tả một *requested version*, không nhất thiết là phiên bản cuối cùng khi có dependency khác yêu cầu version cao hơn. Hãy kiểm tra `dependencyInsight`.

### 7.3. Exclude transitive dependency

Kotlin:

```kotlin
dependencies {
    implementation("org.example:feature:1.0") {
        exclude(group = "org.slf4j", module = "slf4j-simple")
    }
}
```

Groovy:

```groovy
dependencies {
    implementation('org.example:feature:1.0') {
        exclude group: 'org.slf4j', module: 'slf4j-simple'
    }
}
```

`org.example:feature:1.0` là tọa độ **giả định để minh họa**, không bảo đảm artifact tồn tại. Exclude ở một đường phụ thuộc chưa chắc loại module khỏi toàn bộ graph nếu một dependency khác vẫn kéo nó vào. **Named parameters của exclude không bị nhầm với legacy map declaration**.

### 7.4. Tắt transitivity khi có lý do

Kotlin:

```kotlin
dependencies {
    implementation("org.example:legacy-lib:1.0") {
        isTransitive = false
    }
}
```

Groovy:

```groovy
dependencies {
    implementation('org.example:legacy-lib:1.0') {
        transitive = false
    }
}
```

`isTransitive = false`/`transitive = false` làm Gradle không tự lấy các dependency transitively công bố bởi module trên đường này. Nếu module cần thư viện khác khi runtime, có thể phát sinh `ClassNotFoundException`. Không tắt transitive chỉ để “làm classpath gọn” khi chưa biết nhu cầu thực tế.

## 8. Classifier và extension: chuỗi tọa độ có thể mở rộng

Ngoài ba phần GAV, Gradle hỗ trợ các ký pháp chuyên biệt:

```text
group:name:version
group:name:version:classifier
group:name:version@extension
group:name:version:classifier@extension
```

Ví dụ minh họa:

```kotlin
dependencies {
    runtimeOnly("org.example:sample:1.0:resources")
    runtimeOnly("org.example:sample:1.0@zip")
    runtimeOnly("org.example:sample:1.0:resources@zip")
}
```

Các tọa độ `org.example` này **không được bảo đảm tồn tại**, và ba dòng là ba *trường hợp tùy chọn*, không nên copy cùng lúc.

- **Classifier** dùng khi publisher thực sự có artifact với classifier tương ứng; ví dụ sources, javadoc hoặc resources.
- **`@extension` là artifact-only notation**: Gradle yêu cầu artifact có phần mở rộng đó và **bỏ qua metadata-based resolution**; theo tài liệu hiện hành, nó không giữ cách xử lý variant/transitive thông thường.
- Việc thêm `@jar` vào mọi dependency **không** có nghĩa “rõ ràng hơn”: nó có thể làm thay đổi semantics. Ưu tiên GAV thường và để Gradle dùng variant-aware metadata trừ khi thật sự cần một artifact đặc biệt.

Version catalog TOML chỉ nắm group/name/version; nhu cầu classifier/extension chuyên biệt nên được diễn đạt bằng API thích hợp bên ngoài alias khi cần.

## 9. Những dependency không dùng GAV external module

Không phải mọi dependency ở Gradle đều là `group:name:version`.

### 9.1. ProjectDependency

Một project khác trong cùng multi-project build:

```kotlin
// build.gradle.kts
dependencies {
    implementation(project(":core"))
}
```

Groovy:

```groovy
dependencies {
    implementation project(':core')
}
```

`:core` phải được khai báo ở settings (ví dụ `include(":core", ":app")`). Gradle dùng model và các variants của `ProjectDependency`, **không** tìm `:core` như một tọa độ Maven trên Internet. Task producing artifact được nối theo dependency model thích hợp.

### 9.2. FileCollectionDependency

Một file JAR local:

```kotlin
dependencies {
    implementation(files("libs/manual.jar"))
}
```

Groovy:

```groovy
dependencies {
    implementation files('libs/manual.jar')
}
```

`libs/manual.jar` được giải quyết tương đối theo project hiện tại; file phải tồn tại. `FileCollectionDependency` không có metadata transitive giống một external module published. Khi có thể, dùng module dependency có nguồn và metadata rõ hơn.

### 9.3. Plugin không phải implementation dependency

```kotlin
plugins {
    id("java")
}
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

`id("java")` yêu cầu plugin Gradle, còn `implementation(...)` yêu cầu module cho project. Không thêm plugin ID như library dependency rồi mong Gradle tự áp dụng plugin.

## 10. Bài thực hành Java 17 hoàn chỉnh: GAV string

Ví dụ sau chạy được trên JDK 17 và Gradle Wrapper hỗ trợ JDK/Java toolchain 17, với mạng truy cập Maven Central hoặc artifact đã cache. Nó minh họa **một external module thực** và việc Gradle đưa thư viện lên compile/runtime classpath.

### 10.1. Cây thư mục

```text
gradle-dependency-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
```

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "gradle-dependency-lab"
```

**`build.gradle.kts`:**

```kotlin
plugins {
    id("application")
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Plugin `application` cung cấp Java support, `implementation` và task `run`. Gradle tải/đọc metadata và artifact Commons Lang3 theo repository khi configuration cần resolve.

**`src/main/java/demo/Main.java`:**

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String result = StringUtils.capitalize("gradle");
        System.out.println("Result=" + result);
    }
}
```

Ở đây class Java thuộc package `demo` và có cùng tên `Main` như tên file `Main.java`, đúng với `application.mainClass = "demo.Main"`.

### 10.2. Chạy và xem kết quả

Từ root project có Gradle Wrapper:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew compileJava
./gradlew -q run
./gradlew build
```

Trên Windows, dùng `gradlew.bat` thay `./gradlew`. Nếu khởi tạo project mới chưa có Wrapper nhưng máy đã cài Gradle, có thể tạo Wrapper bằng `gradle wrapper` rồi dùng Wrapper cho mọi lệnh sau.

**Stdout do chương trình Java in ra:**

```text
Result=Gradle
```

`StringUtils.capitalize("gradle")` trả `"Gradle"`; `-q` làm gọn log Gradle. Ngoài stdout chương trình, Gradle có thể có thông tin tải module hoặc trạng thái task tùy mức log/cache.

### 10.3. Bản Groovy DSL tương đương

Thay settings bằng **`settings.gradle`**:

```groovy
rootProject.name = 'gradle-dependency-lab'
```

Thay build script bằng **`build.gradle`**:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Mã `src/main/java/demo/Main.java` **không thay đổi**. Hai file script này là **phiên bản thay thế cho các file Kotlin**; đừng để cả hai build script cùng active cho cùng một project khi làm bài tập.

### 10.4. Chuyển bài tập sang catalog có cấu trúc

Thêm `gradle/libs.versions.toml`:

```toml
[versions]
commonsLang3 = "3.17.0"

[libraries]
commons-lang3 = { group = "org.apache.commons", name = "commons-lang3", version.ref = "commonsLang3" }
```

Chỉ **thay** một dòng dependency trong Kotlin:

```kotlin
dependencies {
    implementation(libs.commons.lang3)
}
```

Hoặc Groovy:

```groovy
dependencies {
    implementation libs.commons.lang3
}
```

Chạy lại `./gradlew -q run` và `./gradlew dependencies --configuration runtimeClasspath`. Khi alias trỏ đến cùng tọa độ/version, output Java vẫn là `Result=Gradle`. Không thêm cả GAV string và alias song song trong cùng dependency block.

### 10.5. Kiểm tra với javac bên ngoài Gradle

Nếu có JAR Commons Lang3 phiên bản 3.17.0 thật trong thư mục `lib`, Java 17 cũng có thể compile trực tiếp:

```bash
mkdir -p out
javac -cp lib/commons-lang3-3.17.0.jar -d out src/main/java/demo/Main.java
java -cp "out:lib/commons-lang3-3.17.0.jar" demo.Main
```

Stdout:

```text
Result=Gradle
```

Trên Windows, dấu phân tách classpath là `;` (không phải `:`) và có thể dùng `mkdir out`. Các lệnh `javac` trên **yêu cầu JAR đã có ở `lib`**; khác với Gradle, `javac` không tự tìm/tải external module qua repository.

## 11. Kiểm tra dependency được resolve

Từ bài tập:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew --warning-mode all help
```

- `dependencies` in dependency graph của configuration. Nếu module xuất hiện ở runtimeClasspath, nó đã tham gia scope tương ứng.
- `dependencyInsight` giúp xác định dependency nào yêu cầu module, lý do chọn một version và ảnh hưởng của constraints/conflicts.
- `--warning-mode all` đặc biệt hữu ích khi chuyển từ map notation cũ; các cảnh báo thực tế phụ thuộc Gradle version và những API project đang dùng.
- Các lệnh phân tích dependency **không tự chứng minh** chương trình Java có hành vi đúng; vẫn cần `compileJava`, `test` nếu có và `run` khi dùng Application plugin.

**Không đồng nhất version được khai báo với version đã được chọn.** Nếu `A` yêu cầu `g:n:1.0`, `B` yêu cầu `g:n:1.2`, conflict resolution và constraints/platform có thể dẫn đến một version chung. Một chuỗi GAV thường là *version request*. Nếu muốn enforce chính xác hoặc tái lập build lâu dài, cân nhắc rich versions, dependency locking và platform/BOM theo chính sách.

## 12. Migration an toàn từ map notation sang GAV string

Một quy trình cụ thể để không làm sai behavior:

1. Xác định **đúng configuration** (`implementation`, `api`, `testImplementation`...).
2. Đọc đủ `group`, `name`, `version`; ghi lại qualifier như `-jre`, `-RC`, `-SNAPSHOT` nếu có.
3. Kiểm tra có `classifier`, `extension`, `exclude`, `transitive`, `because` hay `version { ... }` không.
4. Ghép `group:name:version` thành một chuỗi GAV; giữ nguyên configuration.
5. Đưa các modifier hợp lệ sang configuration closure tương ứng, **không bỏ qua** exclusions hoặc chính sách version.
6. Chỉ giữ **một declaration** sau migration.
7. Đối chiếu `dependencies` và `dependencyInsight` trước/sau; chạy compile/test/run.
8. Bật cảnh báo Gradle version hiện hành, kiểm tra khả năng tương thích trước Gradle 10.

**Kotlin — trước/sau (chỉ chọn một block):**

```kotlin
// Trước: legacy map/named arguments
dependencies {
    implementation(
        group = "org.example",
        name = "feature",
        version = "2.0"
    ) {
        exclude(group = "org.slf4j", module = "slf4j-simple")
        isTransitive = true
    }
}

// Sau: GAV string, giữ modifiers
dependencies {
    implementation("org.example:feature:2.0") {
        exclude(group = "org.slf4j", module = "slf4j-simple")
        isTransitive = true
    }
}
```

`org.example:feature:2.0` là module **giả định**, chỉ để minh họa. Đây là hai phiên bản thay thế, không phải hai dependency cùng tồn tại.

## 13. Những lỗi và hiểu lầm phổ biến

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Could not find group:name:version` | Sai group/name/version, repository không chứa module, lỗi mạng hoặc quyền. | Đối chiếu GAV với publisher; kiểm tra project/settings repositories. |
| `Unresolved reference: implementation` trong Kotlin | Chưa áp dụng plugin cung cấp configuration trước khi biên dịch script. | Áp dụng `java`/`application`/plugin thích hợp trong `plugins`. |
| `Too many characters in a character literal` | Dùng `'g:n:v'` trong Kotlin. | Dùng `"g:n:v"`. |
| Deprecation warning trong Gradle 9.1+ | Dùng map/named arguments trực tiếp trong dependency declaration. | Migrate sang GAV string hoặc version catalog. |
| Nâng Gradle rồi build fail | Script vẫn dùng notation sẽ bị loại bỏ trong Gradle 10. | Chuyển cú pháp trước khi nâng; đối chiếu Wrapper/version. |
| `libs.commons.lang3` không nhận diện | Thiếu catalog đúng tên hoặc alias sai. | Kiểm tra `gradle/libs.versions.toml`, `[libraries]` và sync Gradle. |
| Version resolve không giống version trong TOML | Conflict resolution, constraints hoặc platform khác. | Dùng `dependencyInsight` xem selected version và lý do. |
| `No matching variant` | Variant attributes không tương thích, không chỉ là vấn đề chuỗi GAV. | Kiểm tra Java target, plugin, metadata và yêu cầu variant. |
| File JAR local không tìm thấy | `files("libs/x.jar")` trỏ sai project hoặc file không tồn tại. | Kiểm tra đường dẫn theo projectDir và file thật. |
| Build chạy nhưng runtime `ClassNotFoundException` | Scope sai hoặc thiếu transitive dependency. | Kiểm tra `runtimeClasspath`, exclusions và `transitive`. |
| Copy string và catalog alias cùng lúc | Duplicate declaration cùng module. | Chỉ giữ một notation cho dependency đó. |
| Thêm `@jar` tùy tiện | Kích hoạt artifact-only, bỏ qua metadata-based resolution. | Dùng GAV thường; chỉ `@ext` khi thật sự cần artifact đặc biệt. |
| Project dependency không tìm thấy | `:core` không được include hoặc project path sai. | Kiểm tra `settings.gradle(.kts)` và `./gradlew projects`. |

### Trường hợp dễ nhầm: cấu trúc TOML không bị deprecated

```toml
[libraries]
commons-lang3 = { group = "org.apache.commons", name = "commons-lang3", version = "3.17.0" }
```

Đây là **cấu trúc của version catalog**, không phải gọi `implementation(group=..., name=..., version=...)` trong Kotlin/Groovy. Không xóa catalog có cấu trúc chỉ vì đọc cảnh báo về *dependency map notation*.

## 14. Nguyên tắc bảo trì và bảo mật

- Dùng **GAV string** để khai báo trực tiếp ngắn gọn; dùng **catalog** khi có nhiều project và cần đồng bộ version.
- Không thay phiên bản hoặc scope trong cùng thao tác đổi notation trừ khi có yêu cầu cụ thể.
- Chỉ tin những repository được kiểm soát; đừng thêm kho lạ để “chữa” dependency not found.
- Không hard-code token/mật khẩu repository vào build script; dùng Gradle properties/credentials và hệ thống secret CI.
- Tránh dùng dynamic version như `1.+` nếu build cần kết quả tái lập; xem xét dependency locking và constraints.
- Không ép classifier/extension khi metadata/variant-aware resolution thông thường đã chọn đúng artifact.
- Đặt dependency của test đúng test configuration; cân nhắc `api` khi thư viện khác xuất hiện trong public API của `java-library`.
- Dùng Gradle Wrapper để mọi thành viên chạy cùng phiên bản; đọc tài liệu deprecation theo phiên bản Wrapper thực tế.
- Dùng `dependencyInsight` khi version hoặc transitive graph không như kỳ vọng, thay vì thêm nhiều declaration trùng nhau.

## 15. Bảng tra nhanh

| Nhu cầu | Viết thế nào | Trạng thái |
| --- | --- | --- |
| Module trong Kotlin | `implementation("g:n:v")` | **Khuyến nghị.** |
| Module trong Groovy | `implementation 'g:n:v'` | **Khuyến nghị.** |
| Legacy map Kotlin | `implementation(group = "g", name = "n", version = "v")` | **Deprecated từ Gradle 9.1.** |
| Legacy map Groovy | `implementation group: 'g', name: 'n', version: 'v'` | **Deprecated từ Gradle 9.1.** |
| Version catalog cấu trúc | `{ group = "g", name = "n", version = "v" }` trong TOML | Hợp lệ cho catalog. |
| Version catalog alias | `implementation(libs.commons.lang3)` | Phù hợp cho multi-project. |
| Rich version | `implementation("g:n") { version { strictly("v") } }` | Dùng khi cần policy version. |
| Loại trừ transitive | `implementation("g:n:v") { exclude(group = "...", module = "...") }` | Modifier hợp lệ, khác legacy map. |
| Project nội bộ | `implementation(project(":core"))` | `ProjectDependency`, không tải Maven. |
| JAR local | `implementation(files("libs/x.jar"))` | `FileCollectionDependency`, file phải tồn tại. |
| Artifact đặc biệt | `runtimeOnly("g:n:v@zip")` | Artifact-only, bỏ qua metadata. |

**Tóm tắt cuối cùng:** `group:name:version` là một cách viết *danh tính module*, còn `implementation`/`testImplementation` là *phạm vi sử dụng*. Dạng map/named arguments cũ giúp người học đọc build lịch sử nhưng không nên dùng cho code mới; version catalog TOML với `group`, `name`, `version` là lựa chọn có cấu trúc hiện đại. Kiểm chứng bằng repository, resolved dependency graph và kết quả build thật thay vì chỉ nhìn cú pháp.

### Nguồn tham khảo chính thức

- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html): các loại dependency, GAV, map deprecation.
- [Gradle — Best Practices for Dependencies](https://docs.gradle.org/current/userguide/best_practices_dependencies.html): ưu tiên string GAV, migration.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): alias và TOML cấu trúc.
- [Gradle — DependencyHandler API](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.artifacts.dsl/-dependency-handler/index.html): module/project/file dependencies.
- [Gradle — Resolving Specific Artifacts](https://docs.gradle.org/current/userguide/resolving_specific_artifacts.html): classifier và artifact-only.
- [Gradle — Rich Versions](https://docs.gradle.org/current/userguide/rich_versions.html): strictly, require, prefer, reject.
