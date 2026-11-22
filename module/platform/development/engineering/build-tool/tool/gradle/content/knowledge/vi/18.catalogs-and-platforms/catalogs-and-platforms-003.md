# Dùng alias trong dependencies và plugins với Gradle Version Catalog

## 1. Vì sao nên dùng alias?

Trong Gradle, một module Java có thể khai báo dependency bằng tọa độ Maven và plugin bằng ID cùng phiên bản:

~~~groovy
plugins {
    id 'io.github.ben-manes.versions' version '0.65.0'
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    testImplementation 'org.junit.jupiter:junit-jupiter-api:5.11.4'
}
~~~

Cách này hợp lệ, nhưng nếu nhiều subproject chép các chuỗi khác nhau, việc nâng phiên bản, rà soát dependency và giữ tính nhất quán trở nên khó khăn. **Version Catalog** cho phép định nghĩa tên gọi ngắn gọn — **alias** — cho thư viện, plugin, nhóm thư viện và các phiên bản, rồi dùng một cú pháp nhất quán ở các file **build.gradle** hoặc **build.gradle.kts**.

Chẳng hạn:

~~~groovy
plugins {
    alias(libs.plugins.versions)
}

dependencies {
    implementation(libs.commons.lang3)
    testImplementation(libs.junit.jupiter.api)
}
~~~

Alias giúp giảm chuỗi trùng lặp và cung cấp **type-safe accessors** để IDE gợi ý tên. Nó **không tự tải thư viện chỉ vì tên xuất hiện trong catalog**, không tự áp dụng plugin, và **không ép tuyệt đối phiên bản cuối cùng được chọn** khi Gradle giải quyết các ràng buộc phiên bản khác.

Bài học thuộc nhóm **Catalog và platform**, tập trung vào cách **sử dụng alias trong dependencies và plugins**. Sau khi học, bạn có thể:

1. Tạo **gradle/libs.versions.toml** với các bảng **[versions]**, **[libraries]**, **[bundles]** và **[plugins]**.
2. Dùng **libs.some.library** và **libs.bundles.some.group** trong dependencies của Groovy DSL và Kotlin DSL.
3. Dùng **alias(libs.plugins.somePlugin)** trong block plugins, kể cả **apply false** của multi-project build.
4. Phân biệt plugin alias, library alias, version alias và bundle alias.
5. Hiểu **pluginManagement.repositories** khác **dependencyResolutionManagement.repositories**, và vì sao catalog không thay thế chúng.
6. Chạy một ví dụ Gradle đa module có **Java 17**, Apache Commons Lang, JUnit Jupiter và một plugin ngoài được định nghĩa bằng alias.
7. Tránh lỗi accessors, tên alias trùng, catalog không hiện trong buildSrc, thiếu repository, plugin không resolve, nhầm scope hoặc xung đột phiên bản.
8. Biết cách kết hợp alias với platform/BOM, version constraints và dependency locking khi cần.

## 2. Bốn bảng của gradle/libs.versions.toml

Gradle tự phát hiện file catalog mặc định tại **gradle/libs.versions.toml** ở root của build và cung cấp đối tượng **libs** cho build scripts của các project trong build đó.

Ví dụ:

~~~toml
[versions]
commonsLang3 = "3.17.0"
junit = "5.11.4"
versionsPlugin = "0.65.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang3" }
junit-jupiter-api = { module = "org.junit.jupiter:junit-jupiter-api", version.ref = "junit" }
junit-jupiter-params = { module = "org.junit.jupiter:junit-jupiter-params", version.ref = "junit" }

[bundles]
junit-compile = ["junit-jupiter-api", "junit-jupiter-params"]

[plugins]
versions = { id = "io.github.ben-manes.versions", version.ref = "versionsPlugin" }
~~~

Ý nghĩa:

| Bảng | Định nghĩa | Dùng trong build script |
| --- | --- | --- |
| **[versions]** | Tên dùng lại cho phiên bản | **libs.versions.junit** là version accessor |
| **[libraries]** | Module Maven + phiên bản hoặc version reference | **libs.commons.lang3**, **libs.junit.jupiter.api** |
| **[bundles]** | Nhóm nhiều library aliases | **libs.bundles.junit.compile** |
| **[plugins]** | Plugin ID và phiên bản | **libs.plugins.versions** |

**Không phải mỗi bảng có cách sử dụng giống nhau.** Một library alias thường được truyền cho **implementation**, **api**, **compileOnly**, **testImplementation** hoặc một dependency configuration khác. Một plugin alias được truyền vào **alias(...)** trong block **plugins**. Một version alias mô tả phiên bản chứ không tự tạo dependency. Một bundle là tập các **library aliases**, không phải plugin bundle.

### 2.1. Cấu trúc TOML và version.ref

Với:

~~~toml
[versions]
junit = "5.11.4"

[libraries]
junit-jupiter-api = { module = "org.junit.jupiter:junit-jupiter-api", version.ref = "junit" }
~~~

**version.ref = "junit"** chỉ đến phiên bản đã khai báo trong **[versions]**. Khi nhóm nhiều artifact cùng release train, chỉ đổi một khóa là dễ đồng bộ hơn.

Một library cũng có thể viết tọa độ trực tiếp:

~~~toml
[libraries]
commons-lang3 = "org.apache.commons:commons-lang3:3.17.0"
~~~

Hoặc tách group và name:

~~~toml
[libraries]
commons-lang3 = { group = "org.apache.commons", name = "commons-lang3", version = "3.17.0" }
~~~

Các ví dụ đều là **cách định nghĩa thay thế nhau**, không nên khai báo cùng tên **commons-lang3** ba lần trong một file TOML. Với project nhiều module, cách dùng **module + version.ref** thường dễ chia sẻ version.

### 2.2. Vì sao có tên libs?

**libs** là tên của catalog mặc định. Nó không phải một biến do bạn phải tự tạo trong từng **build.gradle**. Với file ở vị trí chuẩn, Gradle tự nhập và tạo accessors như **libs.commons.lang3**.

Nếu đã có **gradle/libs.versions.toml**, **không tự đăng ký lại cùng catalog** bằng **versionCatalogs { create('libs') { from(files('gradle/libs.versions.toml')) } }**. Việc khai báo trùng catalog có thể gây lỗi hoặc khó hiểu. Chỉ cấu hình nhập catalog thủ công khi thực sự dùng tên hoặc đường dẫn tùy chỉnh.

Version catalog là metadata được đọc trong quá trình cấu hình; **một library alias chỉ được resolve thành artifact khi configuration tương ứng cần được giải quyết**.

## 3. Dùng library alias trong dependencies

### 3.1. Groovy DSL

Thay vì:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

viết:

~~~groovy
dependencies {
    implementation(libs.commons.lang3)
}
~~~

Groovy DSL cũng thường hỗ trợ dạng không ngoặc:

~~~groovy
dependencies {
    implementation libs.commons.lang3
}
~~~

Hai cách diễn đạt cùng một dependency. Dùng dấu ngoặc nhất quán sẽ dễ đối chiếu với Kotlin DSL và nested expressions hơn.

**Không viết**:

~~~groovy
dependencies {
    implementation 'libs.commons.lang3'
}
~~~

Dấu nháy biến alias thành **chuỗi ký tự**. Đây không phải accessor được Gradle tạo và không phải tọa độ Maven hợp lệ theo ý bạn. Nếu thấy lỗi parse dependency notation, hãy kiểm tra có vô tình đặt **libs...** trong dấu nháy không.

### 3.2. Kotlin DSL

Với **build.gradle.kts**:

~~~kotlin
plugins {
    java
}

dependencies {
    implementation(libs.commons.lang3)
    testImplementation(libs.junit.jupiter.api)
}
~~~

**libs.commons.lang3** là accessor giống Groovy nhưng Kotlin DSL có type checking chặt hơn. Bạn không cần khai báo biến **val libs** trong file script.

### 3.3. Chọn configuration đúng vẫn là trách nhiệm của module

Library alias không quyết định dependency thuộc scope nào:

~~~groovy
dependencies {
    api(libs.public.contract)
    implementation(libs.internal.engine)
    compileOnly(libs.annotations.api)
    annotationProcessor(libs.annotations.compiler)
    testImplementation(libs.junit.jupiter.api)
    testRuntimeOnly(libs.junit.jupiter.engine)
}
~~~

Đoạn trên là **minh họa cách dùng**, giả định catalog có các aliases tương ứng. Để chạy thật, phải khai báo từng alias trong TOML.

Ý nghĩa vẫn do **api**, **implementation**, **compileOnly**, **annotationProcessor**, **testImplementation** và các Gradle configurations quyết định. Catalog không tự sửa dependency scope hoặc tạo plugin cung cấp configuration đó.

Ví dụ **implementation(libs.junit.jupiter.api)** không tự biến JUnit thành dependency chỉ dùng cho test; nó đưa library vào **main implementation**. Nên dùng **testImplementation** khi nó là test framework.

### 3.4. Project dependency không bắt buộc có library alias

Với multi-project build:

~~~groovy
dependencies {
    implementation(project(':core'))
    implementation(libs.commons.lang3)
}
~~~

**project(':core')** tham chiếu subproject nội bộ đã được **include** trong settings; **libs.commons.lang3** tham chiếu external module tọa độ Maven. Version catalog tập trung chủ yếu vào external coordinates. Không nên cố khai báo một project path đơn thuần như một module GAV trong **[libraries]** chỉ để dùng cùng cú pháp.

## 4. Alias với bundles và version references

### 4.1. Bundle dùng khi nhiều thư viện thường đi cùng nhau

Trong TOML:

~~~toml
[versions]
junit = "5.11.4"

[libraries]
junit-jupiter-api = { module = "org.junit.jupiter:junit-jupiter-api", version.ref = "junit" }
junit-jupiter-params = { module = "org.junit.jupiter:junit-jupiter-params", version.ref = "junit" }

[bundles]
junit-compile = ["junit-jupiter-api", "junit-jupiter-params"]
~~~

Trong Groovy DSL:

~~~groovy
dependencies {
    testImplementation(libs.bundles.junit.compile)
}
~~~

Trong Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation(libs.bundles.junit.compile)
}
~~~

Một bundle đại diện cho **nhiều library dependency declarations**. Nó không tự gộp các JAR thành một “fat JAR”, không tạo platform/BOM, không đảm bảo mọi version transitive luôn giống nhau, và không thể chứa plugin aliases.

Nếu bạn chỉ cần JUnit API mà không dùng parameterized tests, có thể khai báo trực tiếp **testImplementation(libs.junit.jupiter.api)** thay vì lấy cả bundle. Không tạo bundle quá lớn khiến mọi module mang những dependencies không cần thiết.

### 4.2. Một bundle không thể gán nhiều scopes cùng lúc

Ví dụ nếu một bundle chứa cả JUnit Jupiter API và JUnit Platform Launcher, rồi viết:

~~~groovy
testImplementation(libs.bundles.all.testing)
~~~

thì **tất cả thành viên bundle** được thêm vào **testImplementation**. Gradle không tự hiểu rằng một phần nên **testImplementation** còn phần khác nên **testRuntimeOnly**. Vì vậy ví dụ thực hành bên dưới chỉ bundle **junit-jupiter-api** và **junit-jupiter-params**, còn **junit-jupiter-engine** cùng **junit-platform-launcher** nằm riêng trong **testRuntimeOnly**.

Nếu một library cần nhiều scopes hoặc công cụ annotation processing có cấu trúc riêng, dùng aliases trực tiếp ở đúng từng configuration.

### 4.3. Version alias không ép kết quả resolution

Từ khóa **[versions]** giúp dùng chung phiên bản khai báo. Tuy nhiên, **version catalog chỉ mô tả requested versions**; nó không phải cơ chế bắt Gradle cuối cùng phải chọn đúng version đó nếu dependency graph có constraints khác.

Ví dụ:

~~~toml
[versions]
commonsLang3 = "3.17.0"
~~~

Điều đó không có nghĩa bất kỳ dependency graph nào cũng chắc chắn dùng commons-lang3 3.17.0. Platform/BOM, dependency constraints, rich versions, conflict resolution và locking có thể thay đổi hoặc chặn kết quả.

Khi cần kiểm chứng version đã chọn:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
~~~

Đừng lấy nội dung TOML làm bằng chứng duy nhất của resolved version.

## 5. Dùng plugin alias trong plugins

### 5.1. Khác library alias ở cú pháp và mục đích

Trong TOML:

~~~toml
[versions]
versionsPlugin = "0.65.0"

[plugins]
versions = { id = "io.github.ben-manes.versions", version.ref = "versionsPlugin" }
~~~

Trong **build.gradle**:

~~~groovy
plugins {
    alias(libs.plugins.versions)
}
~~~

Trong **build.gradle.kts**:

~~~kotlin
plugins {
    alias(libs.plugins.versions)
}
~~~

**alias(...)** là API chuyên dùng của **plugins block** để chuyển plugin dependency từ version catalog thành plugin request. Gradle giải quyết plugin ID **io.github.ben-manes.versions** ở phiên bản được chỉ định, rồi áp dụng plugin vào project chứa plugins block.

Plugin ở đây cung cấp task **dependencyUpdates** để kiểm tra phiên bản dependency mới hơn. **0.65.0** là một phiên bản ví dụ đã được phát hành trên Gradle Plugin Portal; khi dùng trong dự án thật, chọn bản tương thích với Gradle/JDK và chính sách nâng cấp của nhóm. Không tự động nâng plugin lên bản mới nhất chỉ vì có alias.

### 5.2. Dùng apply false ở root

Trong multi-project build, một plugin ngoài có thể chỉ cần áp dụng cho module cụ thể, không phải root:

~~~groovy
// root build.gradle
plugins {
    alias(libs.plugins.versions) apply false
}
~~~

Và trong **app/build.gradle**:

~~~groovy
plugins {
    id 'application'
    alias(libs.plugins.versions)
}
~~~

**apply false** cho phép khai báo plugin ở root mà **không áp dụng vào root**; subproject vẫn có thể áp dụng plugin khi cần. Root không tự có task **dependencyUpdates** chỉ vì dòng alias **apply false**. Task đó sẽ xuất hiện ở project thật sự áp dụng plugin, chẳng hạn **:app:dependencyUpdates**.

Trong Kotlin DSL:

~~~kotlin
plugins {
    alias(libs.plugins.versions) apply false
}
~~~

Nếu mọi module không cần plugin, đừng áp dụng đại trà rồi gây thêm thời gian cấu hình, nhiệm vụ và dependency classpath. Chỉ áp dụng ở nơi có nhu cầu.

### 5.3. Core plugins vẫn có thể khai báo bằng ID

Các plugin tích hợp Gradle như **java**, **java-library**, **application**, **base** thường được viết trực tiếp:

~~~groovy
plugins {
    id 'java-library'
}
~~~

Chúng không cần external plugin version trong catalog. Đừng cố đặt **version** ngoài cho một core plugin chỉ để toàn bộ plugins trông giống alias. Catalog đặc biệt hữu ích với plugin bên ngoài có ID/phiên bản phải quản lý, ví dụ plugin quality, Kotlin, code generation hoặc dependency reporting.

### 5.4. Không nhầm plugin alias với dependency của plugin

Một plugin alias:

~~~groovy
plugins {
    alias(libs.plugins.versions)
}
~~~

**không tương đương**:

~~~groovy
dependencies {
    implementation(libs.plugins.versions)
}
~~~

Dòng thứ hai không phải cách áp dụng Gradle plugin. **libs.plugins.versions** là provider của **PluginDependency**, không phải một Maven library alias dùng trực tiếp cho implementation.

Ngược lại, **alias(libs.commons.lang3)** trong plugins block cũng sai: **libs.commons.lang3** là provider của external module dependency, không phải plugin dependency.

## 6. Catalog và repository: hai lớp cấu hình riêng

Một alias có thể chỉ đúng tọa độ nhưng Gradle vẫn không tải được artifact nếu thiếu repository hoặc credentials phù hợp.

| Mục đích | Chỗ cấu hình | Ví dụ |
| --- | --- | --- |
| External Java libraries | **dependencyResolutionManagement.repositories** trong settings | **mavenCentral()** |
| External Gradle plugins dùng plugins block | **pluginManagement.repositories** trong settings | **gradlePluginPortal()** |
| Những tọa độ và phiên bản dùng lại | **gradle/libs.versions.toml** | **[libraries]** và **[plugins]** |
| Destination để publish artifact | **publishing.repositories** | Maven releases repository |

### 6.1. Cấu hình settings đúng

Trong **settings.gradle**:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'catalog-alias-lab'
include ':core', ':app'
~~~

**pluginManagement** được đặt trước những blocks khác trong settings. Nó hướng dẫn Gradle tìm plugin được yêu cầu bởi **plugins { ... }**. **dependencyResolutionManagement.repositories** cho phép Gradle resolve external libraries của project, chẳng hạn Apache Commons Lang và JUnit.

Version catalog **không thay thế** hai khối repositories. Việc tồn tại **libs.commons.lang3** trong catalog không tự bảo đảm rằng Gradle được phép truy cập Maven Central. Tương tự, plugin alias không tự thêm Gradle Plugin Portal.

**RepositoriesMode.FAIL_ON_PROJECT_REPOS** là lựa chọn có chủ đích: nếu root hoặc subproject/plugin cố thêm project-level repository, Gradle sẽ báo lỗi. Vì vậy ví dụ hoàn chỉnh không chứa **repositories { ... }** trong các file **build.gradle**. Nếu tổ chức dùng mirror nội bộ, thay repository đúng theo chính sách; không bỏ qua proxy/TLS/credentials để demo chạy.

### 6.2. Alias trong settings không giống alias trong project build script

Catalog mặc định được dùng trong build scripts, chẳng hạn **root/build.gradle**, **app/build.gradle**, **core/build.gradle**. Không giả định có thể gọi:

~~~groovy
pluginManagement {
    plugins {
        alias(libs.plugins.versions)
    }
}
~~~

**Đây là đoạn cố ý sai/không được hỗ trợ trong settings.** Khi settings đang chạy, plugin catalog accessors dành cho project scripts chưa được cung cấp theo cách đó. Tài liệu Gradle nêu rõ không dùng plugin alias từ version catalog trong **settings file hoặc settings plugin**.

Nếu cần đặt plugin version cho settings/pluginManagement, dùng API và dữ liệu được phép ở phase đó, ví dụ:

~~~groovy
pluginManagement {
    plugins {
        id 'io.github.ben-manes.versions' version '0.65.0'
    }
}
~~~

Đoạn này chỉ minh họa cấu hình plugin version ở settings, không tương đương với việc plugin đã được áp dụng vào một project. Không kết hợp nó một cách tùy ý với alias cùng phiên bản mà không xem xét nguồn quản lý version nào là chuẩn.

## 7. Ví dụ Java 17 hoàn chỉnh dùng aliases trong dependencies và plugins

Bài thực hành có **2 subproject**:

- **:core**: Java library cung cấp lời chào đơn giản.
- **:app**: Java application dùng **Apache Commons Lang** thông qua **library alias**, kiểm thử với JUnit thông qua **bundle alias** và dùng **plugin alias** để có task kiểm tra phiên bản.

Bài dùng **Gradle Groovy DSL**, Java 17 và các artifact có thật trên Maven Central/Gradle Plugin Portal. Khi chạy lần đầu cần Internet hoặc mirror/cache đã cấu hình đúng. **Đây là một ví dụ cấu hình hoàn chỉnh**, không phải tập hợp các đoạn copy thiếu file.

### 7.1. Cấu trúc thư mục

~~~text
catalog-alias-lab/
├── settings.gradle
├── build.gradle
├── gradle/
│   ├── libs.versions.toml
│   └── wrapper/...
├── gradlew
├── gradlew.bat
├── core/
│   ├── build.gradle
│   └── src/main/java/demo/core/Greeting.java
└── app/
    ├── build.gradle
    ├── src/main/java/demo/app/Main.java
    └── src/test/java/demo/app/MainTest.java
~~~

Các file Wrapper được tạo một lần bằng **gradle wrapper** nếu máy đã có Gradle CLI phù hợp, sau đó commit vào repository. Những lệnh dưới đây dùng **./gradlew** hoặc **.\gradlew.bat**. Cần JDK chạy được Gradle version được chọn và **Java 17 toolchain** có sẵn hoặc được cung cấp qua cơ chế provisioning thích hợp.

### 7.2. settings.gradle

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}

rootProject.name = 'catalog-alias-lab'
include ':core', ':app'
~~~

Không tự thêm **versionCatalogs** ở đây: Gradle tự nạp **gradle/libs.versions.toml** theo đường dẫn chuẩn. Chỉ dùng các repositories cần thiết cho plugin và external Java dependencies.

### 7.3. gradle/libs.versions.toml

~~~toml
[versions]
commonsLang3 = "3.17.0"
junit = "5.11.4"
junitPlatform = "1.11.4"
versionsPlugin = "0.65.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang3" }

junit-jupiter-api = { module = "org.junit.jupiter:junit-jupiter-api", version.ref = "junit" }
junit-jupiter-params = { module = "org.junit.jupiter:junit-jupiter-params", version.ref = "junit" }
junit-jupiter-engine = { module = "org.junit.jupiter:junit-jupiter-engine", version.ref = "junit" }
junit-platform-launcher = { module = "org.junit.platform:junit-platform-launcher", version.ref = "junitPlatform" }

[bundles]
junit-compile = ["junit-jupiter-api", "junit-jupiter-params"]

[plugins]
versions = { id = "io.github.ben-manes.versions", version.ref = "versionsPlugin" }
~~~

Từ TOML này, Gradle tạo các accessors:

| TOML alias | Accessor trong build.gradle |
| --- | --- |
| **commons-lang3** | **libs.commons.lang3** |
| **junit-jupiter-api** | **libs.junit.jupiter.api** |
| **junit-jupiter-params** | **libs.junit.jupiter.params** |
| **junit-jupiter-engine** | **libs.junit.jupiter.engine** |
| **junit-platform-launcher** | **libs.junit.platform.launcher** |
| Bundle **junit-compile** | **libs.bundles.junit.compile** |
| Plugin **versions** | **libs.plugins.versions** |
| Version **junit** | **libs.versions.junit** |

**Lưu ý:** các phiên bản trong demo được ghim để tái lập nội dung, không khẳng định chúng là versions mới nhất tại mọi thời điểm. Không bắt buộc dùng cùng phiên bản JUnit Jupiter và JUnit Platform khi release trains được thiết kế khác nhau; ở đây các giá trị tương thích theo mục đích demo.

### 7.4. build.gradle ở root

~~~groovy
plugins {
    alias(libs.plugins.versions) apply false
}
~~~

Root **không áp dụng** plugin kiểm tra dependency update, chỉ khai báo nó cho các project khác có thể dùng. Chúng ta sẽ áp dụng plugin thật vào **:app**, nên task **dependencyUpdates** được tạo ở :app.

### 7.5. core/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Module core chỉ dùng Java standard library, không cần external dependency. Vì thế không có **dependencies { ... }** cũng hợp lệ.

### 7.6. core/src/main/java/demo/core/Greeting.java

~~~java
package demo.core;

public final class Greeting {
    private Greeting() {
    }

    public static String welcome(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Mã Java này tạo lời chào theo một tên đã được chuẩn hóa. Nó không cần biết Gradle Version Catalog tồn tại.

### 7.7. app/build.gradle

~~~groovy
plugins {
    id 'application'
    alias(libs.plugins.versions)
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation(project(':core'))
    implementation(libs.commons.lang3)

    testImplementation(libs.bundles.junit.compile)
    testRuntimeOnly(libs.junit.jupiter.engine)
    testRuntimeOnly(libs.junit.platform.launcher)
}

application {
    mainClass = 'demo.app.Main'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.register('exportRuntimeLibraries', Copy) {
    group = 'help'
    description = 'Sao chép runtime JARs để thử javac/java ngoài Gradle'
    from(configurations.runtimeClasspath)
    into(layout.buildDirectory.dir('manual-libs'))
}
~~~

Giải thích theo thứ tự:

1. **id 'application'** là core plugin, cung cấp **run** và Java tasks.
2. **alias(libs.plugins.versions)** áp dụng plugin ngoài đã khai báo trong TOML; vì vậy :app có task **dependencyUpdates**.
3. **implementation(project(':core'))** yêu cầu mã thư viện nội bộ.
4. **implementation(libs.commons.lang3)** lấy Apache Commons Lang qua catalog, dùng trong Java source của app.
5. **testImplementation(libs.bundles.junit.compile)** đưa hai dependencies API + Params của JUnit vào test compile/runtime classpaths.
6. **testRuntimeOnly** cung cấp JUnit Jupiter Engine và JUnit Platform Launcher cho execution của test task.
7. **useJUnitPlatform()** cho Gradle Test task chạy JUnit 5.
8. **exportRuntimeLibraries** là task phụ chỉ để minh họa cách cung cấp JARs cho lệnh javac/java thủ công; **không phải yêu cầu của Version Catalog**.

Không đặt **repositories** trong app vì settings đã chọn chính sách **FAIL_ON_PROJECT_REPOS**.

### 7.8. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.core.Greeting;
import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static String render(String raw) {
        return Greeting.welcome(StringUtils.capitalize(raw));
    }

    public static void main(String[] args) {
        System.out.println(render("gradle"));
    }
}
~~~

**StringUtils.capitalize("gradle")** trả về **"Gradle"**. Sau đó **Greeting.welcome(...)** tạo **"Xin chào, Gradle!"**. Tên class, package và đường dẫn source khớp chính xác.

### 7.9. app/src/test/java/demo/app/MainTest.java

~~~java
package demo.app;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {
    @Test
    void greetsGradle() {
        assertEquals("Xin chào, Gradle!", Main.render("gradle"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"gradle", "java"})
    void capitalizesName(String input) {
        String expected = "Xin chào, "
                + Character.toUpperCase(input.charAt(0))
                + input.substring(1)
                + "!";
        assertEquals(expected, Main.render(input));
    }
}
~~~

JUnit **@Test** thuộc **junit-jupiter-api** và **@ParameterizedTest/@ValueSource** thuộc **junit-jupiter-params**. Việc dùng cả hai xác minh bundle **junit-compile** thực sự phục vụ hai API riêng. Với hai giá trị parameterized, đây là **3 lượt kiểm tra**: 1 test method thông thường + 2 invocations của parameterized test, khi Gradle test task chạy với JUnit Platform.

Test chủ động tự tính expected string cho dữ liệu đơn giản, không gọi lại StringUtils.capitalize để tạo expected, nhằm tránh việc so sánh implementation với chính nó.

### 7.10. Lệnh kiểm chứng trên Linux/macOS

~~~bash
./gradlew --version
./gradlew projects
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:test
./gradlew -q :app:run
./gradlew :app:build
./gradlew :app:tasks --all
~~~

**Dòng stdout chính xác do Java Main in khi chạy :app:run:**

~~~text
Xin chào, Gradle!
~~~

Gradle có thể in thêm task logs hoặc warnings. Không giả định toàn bộ console output chỉ có một dòng nói trên.

Với cấu hình này, **:app:test** phải biên dịch và chạy được các kiểm tra khi dependencies resolve thành công. Task **:app:tasks --all** có thể dùng để kiểm tra **dependencyUpdates** do plugin alias cung cấp.

Có thể thử thêm:

~~~bash
./gradlew :app:dependencyUpdates
~~~

Đây là **lệnh kiểm tra cập nhật dependency**, có thể cần truy cập các metadata repositories và tạo report khác nhau theo thời điểm chạy. Không có stdout cố định để so khớp, và không phải chạy lệnh này để hoàn thành ứng dụng Java.

### 7.11. Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :app:dependencies --configuration compileClasspath
.\gradlew.bat :app:dependencies --configuration testRuntimeClasspath
.\gradlew.bat :app:test
.\gradlew.bat -q :app:run
.\gradlew.bat :app:build
.\gradlew.bat :app:tasks --all
.\gradlew.bat :app:dependencyUpdates
~~~

Trên Windows, dùng **gradlew.bat** thay script Unix. Nếu báo lỗi Java toolchain, kiểm tra JDK 17 đã cài, Gradle version và cấu hình provisioning của môi trường; việc alias đúng không tự cài JDK.

### 7.12. Biên dịch và chạy Java bằng javac/java độc lập

Vì Main.java có phụ thuộc **Apache Commons Lang** và **:core**, lệnh **javac** thủ công cần classpath chứa JARs tương ứng. Đừng chạy **javac Main.java** rồi coi lỗi **package org.apache.commons.lang3 does not exist** là lỗi Version Catalog: javac bên ngoài Gradle không biết đối tượng **libs**.

Ta đã khai báo task **exportRuntimeLibraries** để copy external JAR và project JAR theo runtimeClasspath:

~~~bash
./gradlew :app:exportRuntimeLibraries
mkdir -p out

javac --release 17 -d out \
  core/src/main/java/demo/core/Greeting.java

javac --release 17 \
  -cp "out:app/build/manual-libs/*" \
  -d out app/src/main/java/demo/app/Main.java

java -cp "out:app/build/manual-libs/*" demo.app.Main
~~~

Dòng stdout của lệnh Java cuối:

~~~text
Xin chào, Gradle!
~~~

Trong PowerShell:

~~~powershell
.\gradlew.bat :app:exportRuntimeLibraries
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -d out core\src\main\java\demo\core\Greeting.java
javac --release 17 -cp "out;app\build\manual-libs\*" -d out app\src\main\java\demo\app\Main.java
java -cp "out;app\build\manual-libs\*" demo.app.Main
~~~

Trên Windows, dấu phân tách classpath là **;**, còn Linux/macOS là **:**. Java launcher hỗ trợ wildcard **\*** trong classpath để chọn JARs trong thư mục. Lệnh **exportRuntimeLibraries** lấy artifact từ configuration runtimeClasspath; nếu một dependency không có artifact JAR hoặc bị thay đổi bởi plugin khác, phải điều chỉnh cách xuất classpath cho phù hợp.

Lệnh **javac/java** xác minh Java source và jars đã được chuẩn bị; lệnh **Gradle :app:run và :app:test** xác minh đồng thời Version Catalog accessors, repositories, plugin alias, project dependencies và task configuration.

## 8. Cú pháp alias trong Groovy DSL và Kotlin DSL

### 8.1. Bảng tương đương ngắn

| Ý định | Groovy DSL | Kotlin DSL |
| --- | --- | --- |
| Thêm library alias | **implementation(libs.commons.lang3)** | **implementation(libs.commons.lang3)** |
| Thêm test library | **testImplementation(libs.junit.jupiter.api)** | **testImplementation(libs.junit.jupiter.api)** |
| Thêm bundle | **testImplementation(libs.bundles.junit.compile)** | **testImplementation(libs.bundles.junit.compile)** |
| Áp dụng plugin alias | **alias(libs.plugins.versions)** | **alias(libs.plugins.versions)** |
| Khai báo plugin không áp dụng | **alias(libs.plugins.versions) apply false** | **alias(libs.plugins.versions) apply false** |
| Project nội bộ | **implementation(project(':core'))** | **implementation(project(":core"))** |
| BOM từ library alias | **implementation(platform(libs.some.bom))** | **implementation(platform(libs.some.bom))** |

Đối với các ví dụ có **libs.some.bom**, catalog phải khai báo library alias đó. Không tồn tại phép màu tự tạo alias chỉ vì có hàm **platform(...)**.

### 8.2. Khi dùng Kotlin DSL cho plugins

~~~kotlin
plugins {
    application
    alias(libs.plugins.versions)
}
~~~

Các accessor như **application** đối với core plugins có cú pháp Kotlin đặc trưng. Trong Groovy DSL, dùng **id 'application'** dễ hiểu hơn. Chỉ nên trộn syntax khi người viết thực sự biết mình đang ở file **.gradle** hay **.gradle.kts**.

### 8.3. Định dạng dependency không phụ thuộc alias

Plugin có thể tạo configuration riêng, ví dụ **kapt**, **ksp**, **annotationProcessor**, **integrationTestImplementation**. Bạn vẫn có thể truyền library alias vào configuration khi nó tồn tại:

~~~groovy
dependencies {
    annotationProcessor(libs.codegen.processor)
}
~~~

Đây là **đoạn minh họa chưa chạy độc lập**: cần có alias **codegen-processor**, plugin cung cấp Java annotation processor configuration và artifact phù hợp. Alias không tự làm một library trở thành compiler plugin hoặc tự kích hoạt configuration.

## 9. Quy tắc tạo tên alias và type-safe accessors

Gradle chuẩn hóa dấu gạch ngang và dấu gạch dưới thành các phần truy cập phân cấp. Với:

~~~toml
[libraries]
commons-lang3 = "org.apache.commons:commons-lang3:3.17.0"
junit-jupiter-api = "org.junit.jupiter:junit-jupiter-api:5.11.4"
junit-jupiter-params = "org.junit.jupiter:junit-jupiter-params:5.11.4"
~~~

Bạn sẽ dùng:

~~~groovy
implementation(libs.commons.lang3)
testImplementation(libs.junit.jupiter.api)
testImplementation(libs.junit.jupiter.params)
~~~

**Không dùng** **libs.commons-lang3**: trong Groovy, dấu **-** là toán tử trừ và đây không phải accessor được Gradle tạo. Cũng không tự động suy rằng **libs.commons_lang3** là accessor nếu alias được chuẩn hóa khác.

### 9.1. Khi muốn accessor phẳng

TOML có thể dùng camelCase:

~~~toml
[libraries]
commonsLang3 = "org.apache.commons:commons-lang3:3.17.0"
~~~

Lúc đó accessor có thể là:

~~~groovy
implementation(libs.commonsLang3)
~~~

**Đây là một lựa chọn đặt tên thay thế**, không khai báo đồng thời alias **commons-lang3** và **commonsLang3** trong một catalog rồi mong Gradle tự hợp nhất. Chọn quy ước của nhóm trước khi tạo hàng trăm aliases.

### 9.2. Va chạm giữa alias cha và alias con

Giả sử khai báo:

~~~toml
[libraries]
junit = "junit:junit:4.13.2"
junit-jupiter-api = "org.junit.jupiter:junit-jupiter-api:5.11.4"
~~~

Gradle có thể cần tạo cả accessor cha **libs.junit** và subgroup **libs.junit.jupiter.api**, dẫn đến chuyện **libs.junit** không còn là provider thư viện trực tiếp theo cách bạn mong đợi. Tránh đặt tên alias vừa là leaf vừa là prefix của nhiều aliases khác.

Nên chọn các tên dễ đọc, không mâu thuẫn: **junit4** và **junit-jupiter-api**, hoặc **junit4-core** và **junit5-api** tùy quy ước. Nếu buộc phải dùng catalog xuất bản có tên cha/con trùng, tra API **asProvider()** dành cho subgroup accessor trong tài liệu Gradle.

### 9.3. Tên dành riêng

Một số tên như **extensions**, **class**, **convention** không được dùng làm aliases; các phần đầu của library aliases như **versions**, **bundles**, **plugins** cũng có ràng buộc vì được Gradle dùng cho các namespace hệ thống. Tránh tên quá ngắn, mơ hồ, khác nhau chỉ ở dấu phân tách hoặc chữ hoa/chữ thường.

Khi sửa alias, nhớ **IDE/code completion có thể cập nhật sau khi Gradle sync lại**. Lỗi **Could not get unknown property 'x'** hoặc không tìm thấy accessor thường do TOML alias không khớp, TOML parse lỗi, hoặc catalog không được import trong build scope đó.

## 10. Provider và khi nào Gradle resolve alias?

Version Catalog type-safe accessors trả về **providers**:

| Accessor | Loại dữ liệu khái quát |
| --- | --- |
| **libs.commons.lang3** | **Provider<MinimalExternalModuleDependency>** |
| **libs.bundles.junit.compile** | **Provider<ExternalModuleDependencyBundle>** |
| **libs.plugins.versions** | **Provider<PluginDependency>** |
| **libs.versions.junit** | Version accessor/provider phù hợp |

Điều này giải thích vì sao **implementation(libs.commons.lang3)** có thể truyền thẳng provider cho Gradle thay vì tự lấy một chuỗi version rồi ghép **group:name:version**.

Trong những trường hợp đặc biệt, API khác có thể cần lấy giá trị từ provider bằng **get()**. Nhưng khi khai báo dependencies bình thường, **không cần** viết **implementation(libs.commons.lang3.get())**. Truyền provider giúp Gradle giữ luồng cấu hình rõ ràng và tránh yêu cầu giá trị sớm không cần thiết.

**Plugin request** lại có vòng đời riêng: **plugins { alias(...) }** được xử lý sớm để áp dụng plugin, khác với dependency configuration có thể được resolve khi task cần classpath. Đừng suy ra mọi alias đều trì hoãn tới execution phase.

### 10.1. Catalog không phải danh sách dependency tự động

Có 100 entries trong **[libraries]** không có nghĩa project sử dụng 100 artifacts. Chỉ những entries được đưa vào dependency declarations/configurations được yêu cầu mới trở thành dependencies của project.

Tương tự, có 10 entries trong **[plugins]** không có nghĩa Gradle áp dụng cả 10 plugins. Plugin chỉ được áp dụng khi có **plugins { alias(...) }**, **id(...)** hoặc một cơ chế plugin application hợp lệ khác.

## 11. Aliases kết hợp platform/BOM

Vì catalog nằm trong chủ đề **Catalog và platform**, cần nắm khác biệt: **alias xác định tọa độ**, còn **platform/BOM đặt constraints để căn chỉnh versions**.

Trong TOML có thể khai báo một BOM:

~~~toml
[versions]
junit = "5.11.4"

[libraries]
junit-bom = { module = "org.junit:junit-bom", version.ref = "junit" }
junit-jupiter-api = { module = "org.junit.jupiter:junit-jupiter-api" }
~~~

Đây là **một phương án BOM thay thế**, không ghép máy móc vào bài lab đã ghim version trực tiếp. Trong dependencies:

~~~groovy
dependencies {
    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter.api)
}
~~~

**platform(...)** mới truyền yêu cầu platform vào dependency graph; **libs.junit.bom** chỉ là alias tọa độ BOM. Thư viện JUnit Jupiter API trong ví dụ TOML này không khai báo version, nên BOM cung cấp constraint chọn version phù hợp. Nếu bỏ platform mà không có constraint/version khác, resolution có thể thất bại vì thiếu version yêu cầu.

Tương tự, **enforcedPlatform(...)** là cơ chế mạnh hơn để buộc constraints theo quy tắc Gradle; không bật chỉ vì muốn “dùng catalog”. Trong library được publish, việc áp đặt version bắt buộc lên consumers cần cân nhắc kỹ.

**Một alias version trong [versions] không phải BOM.** BOM có thể căn chỉnh nhiều modules trong dependency graph; alias version chỉ giúp tái sử dụng một version declaration trong catalog.

## 12. Rich versions, conflicts và điều gì vẫn có thể thay đổi

### 12.1. Rich versions cho libraries

Một library version có thể được khai báo với ràng buộc:

~~~toml
[libraries]
some-tool = { module = "com.example:tool", version = { strictly = "[1.0,2.0[", prefer = "1.5" } }
~~~

Đây là **cú pháp minh họa**, tọa độ giả không nên chạy trực tiếp. **strictly** giới hạn phiên bản được phép, **prefer** diễn đạt lựa chọn ưu tiên, và các thuộc tính khác như **require/reject** có ngữ nghĩa theo Gradle VersionConstraint.

### 12.2. Plugin versions khác library rich versions

Trong **[plugins]**, chỉ phần **required version** được sử dụng để resolve plugin. Đừng dùng một rich version với **prefer/strictly/reject** cho plugin alias rồi kỳ vọng Gradle dùng toàn bộ quy tắc như library; cách đó đã bị deprecate theo tài liệu Gradle hiện hành.

### 12.3. Kiểm soát phát hành

Nếu tổ chức cần kết quả dependency ổn định:

- Dùng **version catalog** để chuẩn hóa tọa độ/phiên bản được yêu cầu.
- Dùng **platform/BOM**, constraints hoặc locking để kiểm soát resolved dependency graph.
- Dùng **dependency verification** để kiểm tra artifact integrity.
- Dùng **repository policy/content filters** để kiểm soát nguồn tải.
- Dùng **Gradle Wrapper** để pin Gradle runtime.
- Review version updates trước khi thay đổi TOML; không tin mọi gợi ý “latest” đều tương thích và an toàn.

Mỗi cơ chế giải quyết một lớp khác nhau. Version catalog là **convention và source of truth cho declarations**, không tự thay thế toàn bộ dependency management.

## 13. buildSrc, included builds và multiple catalogs

### 13.1. libs không tự có trong mọi build khác

Một Gradle multi-project build dùng chung default catalog cho các project của **chính build đó**. Nhưng **buildSrc** và một included build như **build-logic** có settings/build logic độc lập. Đừng giả định catalog của main build tự xuất hiện ở mọi nơi.

Nếu **buildSrc** cần catalog của root, bạn có thể nhập nó ở **buildSrc/settings.gradle**:

~~~groovy
dependencyResolutionManagement {
    versionCatalogs {
        libs {
            from(files('../gradle/libs.versions.toml'))
        }
    }
}
~~~

Đây là **snippet tùy chọn** chỉ dùng nếu có buildSrc và cần catalog; không thuộc project demo ở mục 7. Nếu **buildSrc** cần plugin alias, vẫn phải kiểm tra plugin classpath và cơ chế dùng trong build logic; không mặc định mọi context precompiled script plugin chấp nhận **alias(libs.plugins...)** trong plugins block.

Với included build **build-logic**, cấu hình tương tự nằm trong **build-logic/settings.gradle(.kts)** nếu muốn import một TOML dùng chung. Relative path phải được tính từ vị trí settings của included build.

### 13.2. Precompiled script plugins cần lưu ý riêng

Một precompiled convention plugin thường áp dụng plugin bằng ID trong **plugins { ... }**, và build chứa convention plugin phải khai báo dependency cho các external plugins mà nó dùng. Không lấy ví dụ **alias(libs.plugins.versions)** từ project build script rồi dán nguyên vào mọi **precompiled script plugin** mà không xem quy tắc giới hạn của Gradle.

Có thể dùng catalog để lấy **plugin coordinates** khi cấu hình dependency của build-logic qua API thích hợp; đó là một workflow khác với cách áp dụng alias trực tiếp từ app/build.gradle.

### 13.3. Nhiều catalogs

Nếu cần nhiều catalog tách quyền sở hữu, trong settings:

~~~groovy
dependencyResolutionManagement {
    versionCatalogs {
        toolsLibs {
            from(files('gradle/tools.versions.toml'))
        }
    }
}
~~~

Khi đó build scripts có thể dùng **toolsLibs.some.alias** theo các entries trong file **tools.versions.toml**. Không tự xem **toolsLibs** là alias library; nó là **tên cả catalog**.

Gradle cho phép nhiều catalogs, nhưng mỗi catalog tạo một extension/accessors và có ranh giới riêng. **Một file TOML không tự tham chiếu version.ref ở file catalog khác.** Việc chia catalog chỉ có ích khi có lý do thực, như dependency scope độc lập hoặc catalog cấp tổ chức.

### 13.4. Không merge nhiều TOML bằng from() nhiều lần

Trong cùng một catalog builder, **from()** chỉ được dùng một lần. Nếu cố import nhiều TOML vào một catalog bằng hai lời gọi **from()**, Gradle có thể báo lỗi. Khi cần chia catalog hãy tạo nhiều catalogs riêng, hoặc quản lý version overrides bằng API được hỗ trợ.

## 14. Các lỗi thường gặp khi dùng aliases

| Triệu chứng | Nguyên nhân phổ biến | Cách khắc phục |
| --- | --- | --- |
| **Could not get unknown property 'libs'** | File TOML đặt sai chỗ, build scope khác, chưa import catalog | Kiểm tra **gradle/libs.versions.toml**, settings của build đang chạy |
| **Unresolved reference: libs** trong IDE | Gradle sync chưa chạy hoặc build logic khác | Reimport Gradle project; kiểm tra script scope |
| **No such property: commons** | Alias normalization khác tên đang gọi | Đối chiếu TOML **commons-lang3** và accessor **libs.commons.lang3** |
| **No such property: plugins...** | Plugin alias thiếu trong **[plugins]** hoặc sai tên | Kiểm tra bảng [plugins] và accessors được tạo |
| **Invalid catalog definition** | TOML trùng key, version.ref thiếu, syntax sai | Kiểm tra file TOML và error location |
| **Alias conflict / accessor cannot be generated** | Alias cha/con hoặc reserved name va nhau | Đổi tên alias rõ ràng, ví dụ junit4 và junit-jupiter-api |
| **Plugin not found** | Sai plugin ID/version hoặc thiếu Plugin Portal/repo | Kiểm tra **pluginManagement.repositories**, plugin portal và marker |
| **Dependency not found** | Sai GAV/version, repository hoặc filter | Kiểm tra **dependencyResolutionManagement.repositories** và Maven metadata |
| **Alias trong settings plugins block lỗi** | Catalog plugin alias không hỗ trợ ở settings plugin | Dùng pluginManagement.plugins API phù hợp |
| **implementation 'libs.foo' không chạy** | Đặt accessor trong dấu nháy | Dùng **implementation(libs.foo)** |
| **alias(libs.foo) báo sai type** | Lấy library alias thay vì plugin alias | Chuyển sang **libs.plugins.foo** |
| **implementation(libs.plugins.foo) lỗi** | Dùng PluginDependency làm ExternalModuleDependency | Áp dụng plugin bằng **alias(...)** |
| **Plugin không tạo task như mong đợi** | Dùng **apply false** hoặc plugin ở project khác | Kiểm tra **plugins { ... }** tại đúng project, task path |
| **api / implementation không tồn tại** | Chưa áp dụng plugin tạo configuration đó | Thêm **java-library/java/application** phù hợp |
| **Bundle chứa thư viện không cần** | Bundle quá rộng và cùng scope | Tách bundle hoặc dùng library aliases trực tiếp |
| **Selected version khác TOML** | Conflict/platform/constraints/locking | Dùng **dependencyInsight** và kiểm tra graph |
| **buildSrc không thấy libs** | Catalog không tự import vào buildSrc | Thêm import trong **buildSrc/settings.gradle** |
| **No matching variant** | Producer attributes/capability không tương thích | Kiểm tra variant resolution; không đổ lỗi cho alias |
| **Credentials/HTTP 401/403** | Maven/plugin repo yêu cầu xác thực hoặc không có quyền | Cấu hình credential an toàn đúng repository |
| **Offline không tải được artifact** | Alias đúng nhưng cache chưa có JAR/plugin | Sử dụng mạng/mirror đã phê duyệt để tải lần đầu |

### 14.1. Quy trình chẩn đoán theo hai nhánh

~~~text
Một alias gây lỗi?
      |
      v
1. Xác định alias thuộc [libraries], [bundles], [versions], [plugins]
      |
      +-- Library/bundle/version ---------------------------+
      |                                                      |
      |    Kiểm tra libs.* accessor và dependency scope       |
      |    Kiểm tra dependencyResolutionManagement repos      |
      |    Dùng dependencies / dependencyInsight              |
      |                                                      |
      +-- Plugin --------------------------------------------+
           Kiểm tra libs.plugins.* trong plugins block
           Kiểm tra apply false / đúng project
           Kiểm tra pluginManagement repositories/marker
           Dùng tasks --all để xác minh plugin có hiệu lực
      |
      v
2. TOML hợp lệ và import vào đúng build scope?
      |
      v
3. Version, plugin ID hoặc GAV thực sự tồn tại?
      |
      v
4. Có proxy/TLS/credential/network/Gradle compatibility?
      |
      v
5. Chạy đúng task, kiểm tra selected dependencies và output
~~~

Các lệnh mẫu:

~~~bash
./gradlew --version
./gradlew projects
./gradlew :app:tasks --all
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
./gradlew :app:build --stacktrace
./gradlew :app:build --warning-mode all
~~~

Không sử dụng **--refresh-dependencies** hoặc xóa **~/.gradle** như biện pháp đầu tiên khi chỉ sai alias trong TOML: cache không thể tự sửa tên accessor hoặc plugin ID sai.

## 15. Dùng aliases trong dự án có nhiều modules: quy ước đề xuất

Một vài nguyên tắc giúp tránh catalogs khó bảo trì:

1. **Đặt alias theo artifact/chức năng**, ví dụ **junit-jupiter-api**, **commons-lang3**. Đừng chỉ đặt **lib1** hoặc tên thay đổi theo từng module.
2. **Dùng version.ref** khi nhiều artifact cần cùng một phiên bản, ví dụ JUnit modules.
3. **Tách plugin aliases** và library aliases đúng bảng TOML, không trộn ID plugin với Maven GAV.
4. **Chỉ tạo bundle** cho nhóm dependencies thường được dùng cùng nhau ở **cùng scope**.
5. **Không tạo bundles chứa mọi test dependency** nếu các module có nhu cầu khác nhau.
6. **Chọn một quy ước dấu gạch ngang/camelCase**, tránh alias cha/con và reserved names.
7. **Đưa repositories vào settings** theo chính sách, không giả định catalog là repository.
8. **Pin Gradle Wrapper** và version plugin tương thích; plugin resolution khác library resolution.
9. **Đánh giá nâng version bằng dependencyInsight/tests**, không chỉ sửa mỗi dòng TOML và nhìn build thành công.
10. **Giữ buildSrc/convention plugin độc lập rõ ràng**, import catalog khi cần thay vì trông đợi kế thừa.
11. **Không đặt credentials trong TOML** vì catalog không phải nơi lưu secret.
12. **Kiểm tra test/runtime scopes** của các aliases để giữ production artifact gọn.

## 16. Bài tập tự luyện

### Bài 1 — Đổi tọa độ thành alias

Cho:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    testImplementation 'org.junit.jupiter:junit-jupiter-api:5.11.4'
}
~~~

Hãy viết **gradle/libs.versions.toml** với **[versions]** và **[libraries]**, rồi đổi code thành **implementation(libs.commons.lang3)** và **testImplementation(libs.junit.jupiter.api)**. Chạy **:app:dependencies** để kiểm tra.

### Bài 2 — Dùng plugin alias

Định nghĩa plugin **io.github.ben-manes.versions** trong **[plugins]** rồi dùng **alias(libs.plugins.versions)** ở **:app**. So sánh với dùng **alias(...) apply false** ở root. Task **dependencyUpdates** xuất hiện ở project nào? Vì sao?

### Bài 3 — Bundle đúng scope

Dùng **junit-jupiter-api** và **junit-jupiter-params** để tạo **junit-compile**. Thêm bundle vào **testImplementation** nhưng để JUnit Engine và Platform Launcher ở **testRuntimeOnly**. Vì sao cách này tốt hơn đặt mọi thứ vào một bundle có cùng testImplementation scope?

### Bài 4 — Chuẩn hóa alias

Đổi **commons-lang3** thành **commonsLang3** trong TOML. Cập nhật build script từ **libs.commons.lang3** thành **libs.commonsLang3**, chạy Gradle sync và build. Vì sao cách gọi cũ không tự hoạt động sau khi đổi tên?

### Bài 5 — Nhầm plugin/library

Cố ý dùng **implementation(libs.plugins.versions)** hoặc **alias(libs.commons.lang3)** và ghi nhận lỗi kiểu dữ liệu/API. Hoàn tác sau khi hiểu rằng plugin alias và library alias là hai kiểu provider khác nhau.

### Bài 6 — Thiếu repository

Giữ catalog hợp lệ nhưng bỏ **mavenCentral()** khỏi **dependencyResolutionManagement.repositories**. Trên môi trường không có artifact trong cache, Gradle không resolve được Commons/JUnit. Vì sao thêm tọa độ vào TOML không tự cung cấp một repository?

### Bài 7 — Giải quyết xung đột phiên bản

Giả sử một dependency transitive yêu cầu phiên bản Commons Lang khác. Chạy **dependencyInsight** để xác nhận phiên bản cuối cùng được chọn và giải thích vì sao **[versions]** chỉ là điểm xuất phát, không tự ép kết quả.

### Bài 8 — buildSrc

Thêm một project **buildSrc** giả định cần dùng **libs**. Đặt import catalog phù hợp trong **buildSrc/settings.gradle**; giải thích vì sao main build có libs mà buildSrc có thể không thấy.

## 17. Câu hỏi kiểm tra kiến thức

1. Bốn bảng chính trong một Version Catalog TOML là gì?
2. Tên **libs** bắt nguồn từ đâu?
3. Khi nào dùng **implementation(libs.foo)**, khi nào dùng **alias(libs.plugins.bar)**?
4. **libs.commons.lang3** khác chuỗi **'libs.commons.lang3'** ở điểm nào?
5. Vì sao **libs.bundles.junit.compile** không phải một artifact mới?
6. **version.ref** giúp ích gì khi có nhiều JUnit modules?
7. Có thể dùng plugin alias trong **settings.gradle pluginManagement** theo đúng cú pháp ở project build.gradle không?
8. **apply false** có nghĩa gì? Nó có tạo task plugin ở root không?
9. Library alias có tự chọn **api**, **implementation** hoặc **testImplementation** không?
10. Vì sao default catalog có thể tồn tại trong main build nhưng không có ở buildSrc?
11. Nếu Gradle chọn version khác trong TOML, nên dùng lệnh nào để xem lý do?
12. Khi dùng **platform(libs.junit.bom)**, phần nào tạo BOM constraint?
13. Tại sao **pluginManagement.repositories** và **dependencyResolutionManagement.repositories** phải phân biệt?
14. Vì sao type-safe accessor có thể thay đổi từ **libs.commons.lang3** sang **libs.commonsLang3** khi đổi tên TOML alias?
15. Có nên dùng catalog để lưu username/password của Maven repository không?

**Đáp án tóm tắt:** (1) versions, libraries, bundles, plugins; (2) catalog mặc định từ gradle/libs.versions.toml; (3) library provider trong dependencies, plugin provider trong plugins; (4) accessor so với literal string; (5) bundle là danh sách library aliases; (6) dùng chung version; (7) không; (8) khai báo nhưng không áp dụng ở project đó; (9) không, configuration mới quyết định scope; (10) build scope khác; (11) dependencyInsight; (12) lời gọi platform cùng metadata BOM; (13) hai cơ chế resolution; (14) normalize alias thành accessors; (15) không.

## 18. Checklist và tài liệu chính thức

Trước khi hoàn thành một thay đổi dùng Version Catalog:

- [ ] Đường dẫn file là **gradle/libs.versions.toml** của đúng build.
- [ ] TOML không trùng key, thiếu version.ref hay chứa alias reserved/collision.
- [ ] Alias library được gọi bằng **libs...**, không đặt trong chuỗi.
- [ ] Alias plugin được gọi bằng **alias(libs.plugins...)** trong project plugins block.
- [ ] Plugin được áp dụng đúng project; **apply false** không được hiểu là đã áp dụng.
- [ ] External plugin có ID/version hợp lệ và plugin repository phù hợp.
- [ ] External library có GAV/version hợp lệ và library repository phù hợp.
- [ ] Mỗi alias được đặt đúng dependency configuration (main/test/runtime/processor).
- [ ] Bundles được dùng cho nhóm dependencies thật sự cùng scope.
- [ ] Nếu dùng platform/BOM, gọi **platform(...)** rõ ràng; không hiểu catalog là platform.
- [ ] Nếu có buildSrc/included build, catalog đã được import ở build scope đó khi cần.
- [ ] Đã chạy **projects**, **dependencies**, **dependencyInsight**, **test/build** phù hợp.
- [ ] Không để credential trong TOML, và đã xem xét dependency verification/locking theo chính sách.

### Tài liệu tham khảo

- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html)
- [Gradle — Dependencies and Dependency Management Basics](https://docs.gradle.org/current/userguide/dependency_management_basics.html)
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html)
- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html)
- [Gradle — Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html)
- [Gradle — Platforms and BOMs](https://docs.gradle.org/current/userguide/platforms.html)
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle Plugin Portal — io.github.ben-manes.versions](https://plugins.gradle.org/plugin/io.github.ben-manes.versions)
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)

**Kết luận:** Version Catalog làm cho dependency và plugin declarations **ngắn gọn, tập trung và dễ kiểm tra**. Dùng **libs.library** và **libs.bundles...** trong **dependencies**, dùng **alias(libs.plugins...)** trong **plugins**, dùng **version.ref** cho các phiên bản liên quan, và giữ repositories ở phạm vi đúng. Alias không tự quyết định dependency scope, plugin application, version cuối cùng hoặc nguồn tải. Hiểu các ranh giới đó giúp bạn dùng catalog hiệu quả trong build Java 17 đa module mà không vô tình làm sai dependency graph.
