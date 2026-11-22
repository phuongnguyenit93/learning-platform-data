# Type-safe accessors và thời điểm chúng được tạo trong Gradle Kotlin DSL

## 1. Mục tiêu và bối cảnh

Trong Gradle Kotlin DSL, một file `build.gradle.kts` có thể gọi các khối cấu hình quen thuộc như `java {}`, `sourceSets {}`, `dependencies { implementation("...") }` hoặc `tasks.test {}`. Chúng trông giống những hàm Kotlin viết sẵn, nhưng một số tên thực tế được **Gradle sinh ra từ model do plugin đóng góp**. Nhóm này gọi là **type-safe model accessors**.

Điều quan trọng nhất là **thời điểm Gradle xác định model để sinh accessors**. Một plugin hoặc configuration có tồn tại vào lúc chạy build không tự động có nghĩa tên tương ứng đã có trong tập accessor khi Kotlin compiler biên dịch script.

Học xong bài, bạn cần:

1. Giải thích type-safe model accessor là gì, khác API Kotlin/Gradle thông thường thế nào.
2. Nắm đúng mốc sinh accessors **sau `plugins {}` và trước phần thân script**.
3. Dự đoán vì sao `plugins { java }` thường có `implementation(...)`, còn `apply(plugin = "java")` có thể không.
4. Xử lý extension, configuration, task tự khai báo trong phần thân script bằng API tường minh.
5. Hiểu phạm vi của project script, settings script, precompiled script plugin và binary plugin.
6. Phân biệt model accessors với **version catalog accessors** (`libs.*`) và **project accessors** (`projects.*`).
7. Chẩn đoán `Unresolved reference` bằng Gradle Wrapper, `kotlinDslAccessorsReport` và IDE sync.

Bài tập trung vào **Kotlin DSL**; không bàn về Kotlin reflection hay cách sinh getter/setter của compiler Kotlin ngoài Gradle.

## 2. Type-safe accessor là gì?

**Type-safe model accessor** là thành phần API Kotlin được tạo từ schema của Gradle model, giúp code truy cập đối tượng đã được đặt tên với thông tin kiểu mà Kotlin compiler và IDE hiểu được.

Ví dụ plugin `java-library` đóng góp vào project:

- Extension `java` (kiểu `JavaPluginExtension`) để cấu hình Java và toolchain.
- Extension `sourceSets`, chứa các source set `main`, `test`.
- Dependency configurations như `api`, `implementation`, `testImplementation`.
- Tasks thường có tên `compileJava`, `test` và nhiều task liên quan.

Khi các phần tử đó được biết vào đúng thời điểm, script Kotlin có thể viết:

~~~kotlin
plugins {
    `java-library`
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

sourceSets {
    named("main") {
        java.srcDir("src/main/java")
    }
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

Trong ví dụ:

- `java { ... }` dùng accessor cho một project extension.
- `sourceSets { ... }` dùng accessor cho extension dạng container; `named("main")` là API để truy cập phần tử của container.
- `implementation("...")` dùng accessor cho dependency configuration tên `implementation`.

Compiler có thể phát hiện sớm tên sai, gợi ý API dựa trên kiểu và hỗ trợ điều hướng trong IDE. Nếu không có accessor, code dùng tên đó có thể gặp `Unresolved reference` khi biên dịch Kotlin DSL.

**Không phải mọi tên gọi trong script đều là generated accessor.** `tasks.register(...)`, `tasks.named(...)`, `dependencies.add(...)`, `plugins.apply(...)`, `providers.gradleProperty(...)` là các API Gradle có sẵn. Một biến như `val myTask = tasks.register("myTask")` cũng là biến Kotlin do người viết khai báo, không phải accessor do Gradle sinh.

### 2.1. Vì sao Groovy DSL nhìn có vẻ linh hoạt hơn?

Groovy DSL hỗ trợ phân giải tên động trong runtime:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Trong Kotlin, `implementation(...)` cần được compiler nhận diện khi biên dịch phần thân. Gradle phải tính trước schema cần thiết và tạo mã truy cập tương ứng. Đây là lý do **mốc sinh accessor** rất quan trọng.

### 2.2. Được type-safe không có nghĩa build chắc chắn chạy

Tên `implementation` có thể biên dịch thành công nhưng artifact vẫn không tải được vì repository/mạng/phiên bản dependency. `java {}` có thể đúng kiểu nhưng JDK toolchain vẫn thiếu. Type-safe accessor chỉ giải quyết **truy cập model và kiểu lúc biên dịch**, không thay thế việc xác thực toàn bộ môi trường build.

## 3. Thời điểm Gradle tạo type-safe model accessors

Tài liệu Gradle Kotlin DSL xác định:

**Với project `build.gradle.kts`, tập type-safe model accessors được tính ngay sau block `plugins {}` và ngay trước khi phần thân script được đánh giá.**

Một mô hình xử lý theo thứ tự logic:

~~~text
Đọc build.gradle.kts
        |
        v
Xử lý và biên dịch phần plugins {}
        |
        v
Resolve và apply plugin trong plugins {}
        |
        v
Lấy schema: extensions, configurations, tasks,
các phần tử của container được plugin đóng góp
        |
        v
Sinh hoặc khôi phục type-safe model accessors
        |
        v
Biên dịch phần thân Kotlin DSL với các accessor đó
        |
        v
Đánh giá phần thân script và cấu hình project
        |
        v
Gradle lên task graph và thực thi task được chọn
~~~

Sơ đồ này thể hiện **thứ tự khái niệm**, không khẳng định Gradle luôn tạo file mã từ đầu mỗi lần chạy. Gradle có cache cho việc biên dịch script và sinh accessors; nếu cache hợp lệ, có thể tái sử dụng. Nhưng tập tên mà phần thân script có thể dùng vẫn phụ thuộc **schema ở thời điểm đã xác định**.

### 3.1. Hệ quả của mốc này

- **Plugin trong `plugins {}`:** được áp dụng đủ sớm để các model element của nó có thể sinh accessor.
- **Plugin qua `apply(plugin = "...")` trong phần thân:** được áp dụng quá muộn để cung cấp accessor mới cho chính phần thân script đã cần biên dịch.
- **Configuration/task/extension tạo trong phần thân:** không tự sinh accessor cho phần thân đó, dù dòng tạo nằm trước dòng dùng.
- **`apply(from = "other.gradle.kts")`:** script plugin thông thường không cung cấp generated model accessors cho script chính.
- **Mô hình được thêm qua cross-project configuration sau mốc sinh schema:** không bảo đảm có accessor trong script đang biên dịch.

Đây là khác biệt giữa **“đối tượng tồn tại khi cấu hình chạy”** và **“tên truy cập đã có khi Kotlin compiler kiểm tra script”**.

### 3.2. Accessor không được tạo ở execution phase

Khi chạy:

~~~bash
./gradlew test
~~~

Gradle phải xử lý script và cấu hình task đủ để lập kế hoạch trước khi thực thi các task. Accessor phục vụ **biên dịch script**; nó không được “sinh thêm” mỗi khi một task action (`doLast`, `@TaskAction`) chạy.

Tương tự, `tasks.register("audit")` trong script không khiến compiler phát sinh ngay thuộc tính `tasks.audit` cho đoạn code phía dưới. Nếu muốn dùng task vừa đăng ký, bạn có thể giữ **TaskProvider** hoặc dùng API `tasks.named("audit")`.

## 4. Ví dụ chạy được: plugin đóng góp accessor đúng thời điểm

Dự án thử nghiệm:

~~~text
accessor-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/wrapper/...
~~~

Giả định đã có **Gradle Wrapper** hợp lệ. Nếu khởi tạo project mới, hãy tạo Wrapper bằng lệnh Gradle theo quy trình của dự án.

**settings.gradle.kts**

~~~kotlin
rootProject.name = "accessor-demo"
~~~

**build.gradle.kts**

~~~kotlin
plugins {
    `java-library`
}

// Được sinh từ JavaPluginExtension:
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

// Được sinh từ SourceSetContainer:
sourceSets {
    named("main") {
        java.srcDir("src/main/java")
    }
}

// Được sinh từ dependency configuration "implementation":
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}

tasks.register("confirmAccessors") {
    doLast {
        println("Type-safe accessors OK")
    }
}
~~~

Lệnh macOS/Linux:

~~~bash
./gradlew -q confirmAccessors
~~~

Lệnh Windows PowerShell:

~~~powershell
.\gradlew.bat -q confirmAccessors
~~~

Dòng do task in ra khi cấu hình hợp lệ:

~~~text
Type-safe accessors OK
~~~

Lệnh `confirmAccessors` chỉ in một chuỗi. Không cần có file Java hay chạy task `compileJava`; dependency được khai báo nhưng không bị resolve nếu task không cần nó. Nếu sau này chạy biên dịch Java thực sự, JDK/toolchain 17 phải sẵn có hoặc dự án phải cấu hình cách cấp phát JDK phù hợp.

**Vì sao đoạn này hợp lệ?** Java Library plugin được áp dụng ngay trong `plugins {}`. Trước khi biên dịch phần thân, Gradle đã biết các extension/configuration mà plugin đóng góp, nên compiler có thể nhận diện `java`, `sourceSets`, `implementation`.

Nếu xóa `plugins { \`java-library\` }` mà vẫn giữ các accessor ấy, script có thể báo `Unresolved reference`. Nếu chỉ khai báo plugin bằng `apply false` mà chưa apply trên project, Gradle cũng không tự có các model element của plugin ở project đó.

## 5. Ví dụ cố ý sai: tạo configuration trong phần thân rồi gọi như accessor

Đây là đoạn **để phân tích lỗi**, không dùng nguyên vẹn để chạy:

~~~kotlin
plugins {
    base
}

configurations.create("customTools")

dependencies {
    customTools("org.apache.commons:commons-lang3:3.14.0") // Unresolved reference
}
~~~

`customTools` được tạo khi phần thân script thực thi, sau mốc Gradle xác định tập generated accessor. Dù `configurations.create(...)` nằm **trước** `dependencies {}`, nó không làm compiler sinh ra hàm `customTools(...)` mới.

**Đổi thứ tự dòng code trong cùng phần thân không giải quyết nguyên nhân.** Compiler cần tập tên của phần thân đã có sẵn trước khi chạy lệnh `create`.

### 5.1. Cách sửa bằng API tường minh — ví dụ chạy được

**settings.gradle.kts**

~~~kotlin
rootProject.name = "custom-configuration-demo"
~~~

**build.gradle.kts**

~~~kotlin
plugins {
    base
}

// Biến Kotlin "customTools" giữ object Configuration;
// đây không phải generated model accessor.
val customTools = configurations.create("customTools")

dependencies {
    add(customTools.name, "org.apache.commons:commons-lang3:3.14.0")
}

tasks.register("showCustomConfig") {
    doLast {
        println("Custom configuration declared")
    }
}
~~~

Chạy:

~~~bash
./gradlew -q showCustomConfig
~~~

Dòng do task in:

~~~text
Custom configuration declared
~~~

Phần `dependencies.add(...)` dùng API có sẵn, nhận tên configuration. Nó không cần accessor tên `customTools`. Lúc dependency được resolve, Gradle vẫn kiểm tra repository và tọa độ artifact theo cơ chế riêng; ở đây task minh họa không resolve configuration.

### 5.2. Dùng biến Kotlin khác gì accessor được sinh?

~~~kotlin
val auditTask = tasks.register("audit") {
    doLast {
        println("audit done")
    }
}

tasks.register("checkAll") {
    dependsOn(auditTask)
}
~~~

`auditTask` là **biến Kotlin** có kiểu TaskProvider, được compiler nhận diện ngay vì khai báo trong script. `checkAll` nhận TaskProvider để định nghĩa phụ thuộc. Không có generated accessor `tasks.audit` nào được tạo từ chính lệnh `register` trong phần thân.

Dùng TaskProvider và `tasks.named(...)` còn có lợi cho **configuration avoidance**, vì không buộc Gradle realize mọi task ngay khi đăng ký.

## 6. `plugins {}` khác gì `apply(plugin = "...")`?

### 6.1. Trường hợp dùng `plugins {}`

~~~kotlin
plugins {
    java
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

`java` plugin được áp dụng trước bước sinh schema, nên accessor cho configuration `implementation` có thể tồn tại trong phần thân.

### 6.2. Trường hợp `apply` ở phần thân

~~~kotlin
apply(plugin = "java")

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0") // Có thể Unresolved reference
}
~~~

**Đây là ví dụ có chủ đích minh họa lỗi accessor.** `apply(plugin = "java")` thực sự áp dụng plugin khi thân script chạy, nhưng phần thân đã được compiler phân tích trước đó. Nếu không có plugin khác cung cấp sẵn accessor, `implementation(...)` chưa được định nghĩa cho script này.

Nên chuyển plugin sang `plugins {}` khi phù hợp. Nếu vì lý do kỹ thuật phải dùng `apply`, dùng API Gradle theo tên/kiểu.

### 6.3. Trường hợp `apply` nhưng dùng API đúng — ví dụ hoàn chỉnh

**settings.gradle.kts**

~~~kotlin
rootProject.name = "imperative-plugin-demo"
~~~

**build.gradle.kts**

~~~kotlin
apply(plugin = "java-library")

dependencies {
    // Có configuration sau khi plugin đã được apply;
    // không cần generated accessor "implementation".
    add("implementation", "org.apache.commons:commons-lang3:3.14.0")
}

configure<org.gradle.api.plugins.JavaPluginExtension> {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.register("verifyAppliedPlugin") {
    doLast {
        println("Explicit API OK")
    }
}
~~~

Chạy:

~~~bash
./gradlew -q verifyAppliedPlugin
~~~

Dòng do task in:

~~~text
Explicit API OK
~~~

Ở đây `configure<JavaPluginExtension>` tìm extension theo **kiểu**, còn `add("implementation", ...)` tìm configuration theo **tên**. Đây là các API hợp lệ khi plugin đã được apply nhưng generated accessor của script không có. Nếu plugin chưa apply, việc tra cứu một extension/configuration không tồn tại vẫn báo lỗi — API tường minh không tự tạo model.

## 7. Các dạng accessor và API thay thế cần nhớ

| Loại phần tử trong Gradle model | Cách ngắn gọn nếu đã có accessor | Cách API tường minh |
| --- | --- | --- |
| Extension `java` | `java { ... }` | `configure<JavaPluginExtension> { ... }` |
| Extension `sourceSets` | `sourceSets { ... }` | `configure<SourceSetContainer> { ... }` |
| Configuration `implementation` | `implementation("g:a:v")` trong dependencies | `dependencies.add("implementation", "g:a:v")` |
| Configuration theo tên | `configurations.implementation` | `configurations.named("implementation")` |
| Task `test` | `tasks.test { ... }` | `tasks.named<Test>("test") { ... }` |
| Task tự tạo | Không trông chờ accessor sinh trong thân | `tasks.register("myTask")`, `tasks.named("myTask")` |
| Extension lấy object | Accessor theo tên | `extensions.getByType<JavaPluginExtension>()` |
| Source set `main` | Accessor theo schema nếu có | `sourceSets.named("main")` |

**Điều kiện cho API thay thế:** tên và type phải đúng, object phải được plugin hoặc script tạo ra thật sự. Khi dùng Kotlin generic API, import type tương ứng nếu chưa nằm trong danh sách default imports.

### 7.1. Khi cấu hình task test

~~~kotlin
plugins {
    java
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Ở đây `named<Test>("test")` dùng Gradle API. `<Test>` giúp compiler biết rằng task hỗ trợ các thuộc tính/phương thức của kiểu Test, chẳng hạn `testLogging`. Nếu chỉ dùng `tasks.named("test")`, kiểu có thể suy ra là `Task` chung và không thấy API riêng của `Test`.

Cấu hình `useJUnitPlatform()` không tự thêm JUnit engine vào dependency — muốn chạy test JUnit thật cần thêm thư viện test phù hợp. Đoạn trên chỉ minh họa cách truy cập task theo tên/type.

### 7.2. Configuration avoidance và generated task accessors

Accessor cho task đã tồn tại trong schema có thể trả **TaskProvider<T>** thay vì ép task được realize ngay. Cần phân biệt:

~~~kotlin
plugins {
    java
}

// Tìm task theo tên/kiểu, trả TaskProvider<Test>:
val testProvider = tasks.named<Test>("test")

// Đăng ký cấu hình được áp dụng khi cần:
testProvider.configure {
    testLogging.showExceptions = true
}

// Không gọi testProvider.get() chỉ để chứng minh task tồn tại:
// .get() có thể khiến task được realize sớm.
~~~

Type-safe accessor và API `named` có thể cùng hỗ trợ mô hình lazy. Được type-safe **không đồng nghĩa mọi task phải được tạo ngay khi biên dịch script**.

### 7.3. Các trường hợp tên không thành identifier Kotlin trực tiếp

Tên phần tử Gradle model có thể chứa ký tự đặc biệt; không nên giả định một chuỗi tên bất kỳ luôn biến thành lời gọi Kotlin như `myName(...)`. API nhận chuỗi (`named("...")`, `add("...", ...)`, `getByName("...")`) luôn là lựa chọn rõ ràng khi tên không có accessor tiện lợi hoặc do plugin tạo động.

## 8. Khi nào precompiled script plugin giúp có accessor?

Nhiều dự án cần chia sẻ cùng cấu hình Kotlin DSL. Nếu copy các đoạn `apply(from = "...")`, script được nạp là **script plugin thông thường**; nó không cung cấp generated model accessors cho file gọi theo cách một plugin khai báo trong `plugins {}` có thể làm.

**Precompiled script plugin** là file `.gradle.kts` trong nguồn plugin, được biên dịch thành plugin và áp dụng bằng plugin ID. Nó có thể tận dụng type-safe model accessors của **các plugin được áp dụng trong `plugins {}` của chính precompiled script**.

### 8.1. Ví dụ hoàn chỉnh với buildSrc

Cấu trúc:

~~~text
convention-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── jvm-conventions.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/wrapper/...
~~~

**settings.gradle.kts**

~~~kotlin
rootProject.name = "convention-demo"
~~~

**buildSrc/build.gradle.kts**

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
~~~

**buildSrc/src/main/kotlin/jvm-conventions.gradle.kts**

~~~kotlin
plugins {
    `java-library`
}

// Accessor cho extension Java được tạo cho precompiled
// project script plugin nhờ plugins {} phía trên.
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<org.gradle.api.tasks.compile.JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

**build.gradle.kts** của project chính:

~~~kotlin
plugins {
    id("jvm-conventions")
}

tasks.register("verifyConvention") {
    doLast {
        println("Convention plugin applied")
    }
}
~~~

Lệnh:

~~~bash
./gradlew -q verifyConvention
~~~

Dòng do task in ra khi môi trường và build logic hợp lệ:

~~~text
Convention plugin applied
~~~

**Cơ chế của ví dụ:**

1. Gradle tự xây dựng build logic trong `buildSrc` trước khi cấu hình build chính.
2. File `jvm-conventions.gradle.kts` được biên dịch thành plugin ID `jvm-conventions`.
3. Trong precompiled script, Java Library plugin ở `plugins {}` đóng góp schema cho accessor `java {}`.
4. Build chính apply `jvm-conventions` bằng `plugins { id("jvm-conventions") }`. Những model element mà convention plugin tạo ra kịp lúc có thể được Gradle cân nhắc khi sinh accessors của script tiêu thụ.

Đây là ví dụ plugin có một nguồn cấu hình chung. Nếu muốn đóng gói quy tắc phức tạp hơn, có thể dùng included build chuyên dụng (thường đặt tên `build-logic`) thay cho `buildSrc`.

### 8.2. Precompiled script plugin khác binary plugin Kotlin

Đừng nhầm ba khái niệm:

- **`apply(from = "shared.gradle.kts")`:** nạp một Kotlin script plugin thường; không có tập generated model accessors riêng theo cùng cơ chế như script chính.
- **Precompiled script plugin:** được biên dịch trước và hỗ trợ model accessors trong phạm vi của project/settings script plugin được tài liệu Gradle hỗ trợ.
- **Binary plugin viết bằng Kotlin:** class triển khai `Plugin<Project>` hoặc `Plugin<Settings>`; dùng Gradle API trực tiếp (`extensions.create`, `tasks.register`, `extensions.configure`, v.v.), **không dùng generated Kotlin DSL script accessors** như `java {}`.

Vì vậy khi viết binary plugin, không sửa lỗi bằng cách chèn các lời gọi DSL ngắn như trong `build.gradle.kts` nếu API đó không nằm trong classpath/scope plugin.

## 9. Scope khác nhau: project, settings, init script

### 9.1. Project build script

`build.gradle.kts` có receiver và model project. Đây là nơi thường thấy accessors cho `java`, `sourceSets`, các dependency configurations và tasks. Plugin được apply từ `plugins {}` quyết định phần đáng kể của schema.

### 9.2. Settings script

`settings.gradle.kts` có scope **Settings**, nơi định nghĩa build name, include projects, plugin management và dependency management. Tài liệu Gradle hiện hành mô tả type-safe model accessors trong **main settings script** và **precompiled settings script plugins** cho model elements phù hợp được Settings plugins cung cấp.

Không tự suy luận `settings.gradle.kts` có các accessor của project như `java {}` hoặc `tasks.test {}`: Settings và Project là **hai loại model khác nhau**. Nhiều cú pháp như `pluginManagement {}` là API/DSL của Settings, không chứng tỏ đó là accessor sinh từ plugin theo tên.

### 9.3. Initialization scripts và script plugins thường

Initialization scripts và script plugins thường có **giới hạn về type-safe model accessors**; theo tài liệu Kotlin DSL hiện hành chúng không có tập generated model accessors tương tự như các script chính/precompiled script plugins. Tại những vị trí này, nên dùng Gradle API tường minh và tham khảo tài liệu theo phiên bản Wrapper.

### 9.4. Multi-project configuration

Plugin áp dụng ở project cha có thể đóng góp model element sẵn sàng khi Gradle xác định schema cho script con, nhưng các phụ thuộc vào thứ tự cấu hình chéo thường khó bảo trì. Hướng thực tế là apply plugin rõ ràng ở project cần dùng hoặc tạo **convention plugin** để quản lý chung; hạn chế trông chờ một script khác cấu hình model muộn rồi tự sinh accessors cho project hiện tại.

## 10. Phân biệt model accessors, version catalogs và project accessors

Từ “accessor” xuất hiện trong nhiều tính năng của Gradle. Chúng có nguồn dữ liệu và điều kiện sinh khác nhau:

| Tên gọi | Ví dụ | Nguồn sinh |
| --- | --- | --- |
| Type-safe **model** accessor | `java {}`, `implementation(...)` | Schema của Project/Settings tại thời điểm xác định sau plugin block |
| **Version catalog** accessor | `libs.commons.lang` | Alias từ `gradle/libs.versions.toml` hoặc catalog được khai báo trong Settings |
| Type-safe **project** accessor | `projects.core` | Cây project được định nghĩa ở `settings.gradle.kts`, nếu tính năng được bật/hỗ trợ |
| Biến Kotlin thông thường | `val reportTask = tasks.register(...)` | Tên do người viết code khai báo; không phải mã do Gradle sinh |

### 10.1. Ví dụ version catalog

**gradle/libs.versions.toml**

~~~toml
[versions]
commons-lang = "3.14.0"

[libraries]
commons-lang = { module = "org.apache.commons:commons-lang3", version.ref = "commons-lang" }
~~~

**build.gradle.kts**

~~~kotlin
plugins {
    `java-library`
}

dependencies {
    implementation(libs.commons.lang)
}
~~~

Ở đây:

- `implementation(...)` là model accessor từ **Java Library plugin**.
- `libs.commons.lang` là generated accessor từ **version catalog**.

Nếu bỏ Java plugin, alias `libs.commons.lang` vẫn có thể hợp lệ nhưng `implementation(...)` không tự xuất hiện. Nếu xóa catalog alias `commons-lang`, tên `libs.commons.lang` không còn được sinh mặc dù Java plugin vẫn có `implementation`.

### 10.2. Ví dụ type-safe project accessor

**settings.gradle.kts**

~~~kotlin
rootProject.name = "multi-module-demo"
enableFeaturePreview("TYPESAFE_PROJECT_ACCESSORS")
include(":app", ":core")
~~~

**core/build.gradle.kts**

~~~kotlin
plugins {
    `java-library`
}
~~~

**app/build.gradle.kts**

~~~kotlin
plugins {
    java
}

dependencies {
    implementation(projects.core)
}
~~~

Khi feature được Gradle Wrapper hỗ trợ và bật thành công, `projects.core` đến từ project tree `:core` trong Settings, còn `implementation` đến từ Java plugin của `:app`.

**TYPESAFE_PROJECT_ACCESSORS** vẫn được tài liệu các bản Gradle hiện hành mô tả là tính năng **incubating**. Hãy kiểm tra phiên bản Wrapper và tài liệu tương ứng; đừng nhầm việc enable feature này với mốc sinh *model accessors* sau `plugins {}`.

## 11. Chẩn đoán khi IDE hoặc Gradle báo `Unresolved reference`

Một thứ tự kiểm tra hữu ích:

1. **Phân loại tên:** `implementation` là dependency configuration, `java` là extension, `tasks.test` là task accessor, `libs.*` là version catalog, `projects.*` là project accessor.
2. **Kiểm tra `plugins {}` trong đúng script:** plugin đã apply thật sự ở project này chưa, hay chỉ `apply false`?
3. **Xác định thời điểm tạo model:** plugin trong `plugins {}` hay gọi `apply(...)` ở phần thân? configuration/task mới được tạo trong thân hay do plugin đóng góp sớm?
4. **Kiểm tra code ở đúng scope:** Project, Settings, precompiled plugin hay binary plugin?
5. **Chạy Gradle Wrapper từ đúng project** để xem lỗi compiler thật. IDE từng gợi ý một tên không có nghĩa tên đó còn hợp lệ sau khi plugin thay đổi.
6. **Dùng API tường minh** nếu model tồn tại nhưng accessor không có: `add`, `named`, `configure<T>`, `getByType<T>`.
7. **Đối chiếu tài liệu plugin hoặc báo cáo accessors**; sau đó chạy lại task nhỏ để xác nhận script compile được.

### 11.1. Báo cáo generated model accessors

Trong build Kotlin DSL mà Gradle phiên bản hiện tại hỗ trợ task tương ứng:

~~~bash
./gradlew kotlinDslAccessorsReport
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat kotlinDslAccessorsReport
~~~

Task **`kotlinDslAccessorsReport`** cung cấp đoạn Kotlin code thể hiện các accessor tương ứng với model đã nhận diện, giúp khám phá tên và kiểu của extension/configuration/task. Để đọc dễ hơn:

~~~bash
./gradlew kotlinDslAccessorsReport --console=plain
~~~

Nếu task không tồn tại, xác nhận đúng Wrapper, Gradle phiên bản và build scope thay vì tự kết luận Gradle không hỗ trợ type safety. Với multi-project, có thể cần xác định đúng task path/project mục tiêu.

### 11.2. Một số lệnh hỗ trợ

~~~bash
./gradlew help
./gradlew tasks --all
./gradlew help --task test
./gradlew dependencies --configuration compileClasspath
~~~

- `help` là phép thử sớm để phát hiện script Kotlin DSL không biên dịch.
- `tasks --all` liệt kê task; không có nghĩa mọi task đều có generated accessor.
- `help --task test` cho biết thông tin về task test nếu nó tồn tại, giúp chọn type cho `tasks.named<T>`.
- `dependencies --configuration compileClasspath` quan sát một configuration cụ thể nếu build có nó.

Nếu lỗi nằm ngay ở giai đoạn **biên dịch script**, các lệnh trên cũng có thể thất bại trước khi task chạy. Hãy giải quyết **lỗi compiler đầu tiên** thay vì chỉ dựa vào log cuối cùng.

### 11.3. IDE sync và cache

IDE như IntelliJ IDEA cần sync/import Gradle để nhận script classpath và generated accessors. Khi thêm hoặc đổi plugin trong `plugins {}`, đồng bộ Gradle có thể cập nhật autocomplete và highlighting.

Phân biệt:

- **CLI Gradle chạy được, IDE vẫn gạch đỏ:** dữ liệu sync/index IDE có thể chưa cập nhật.
- **CLI Gradle cũng báo `Unresolved reference`:** thường là thiếu plugin/model/scope hoặc dùng accessor xuất hiện quá muộn. Sync đơn thuần không giải quyết được nguyên nhân này.

Gradle có thể cache mã/accessors để tăng tốc. **Không sửa trực tiếp các file generated/cache**, và không mặc định phải xoá toàn bộ `.gradle` mỗi khi thiếu một accessor. Cần sửa source-of-truth là script/plugin/settings hoặc dùng API thích hợp.

## 12. Các lỗi phổ biến cần tránh

| Triệu chứng | Nguyên nhân phổ biến | Cách sửa |
| --- | --- | --- |
| `Unresolved reference: implementation` | Chưa apply plugin tạo configuration vào đúng thời điểm | Dùng `plugins { java }`, hoặc `dependencies.add("implementation", "...")` sau khi plugin apply |
| `Unresolved reference: java` | Không có accessor cho Java extension | Apply plugin đúng scope; hoặc `configure<JavaPluginExtension>` khi extension đã tồn tại |
| `Unresolved reference: customTools` | Configuration mới tạo trong phần thân, sau snapshot | Giữ biến Kotlin; dùng `configurations.named`/`dependencies.add` |
| `tasks.myTask` không được nhận diện | Task được đăng ký trong script, không có generated accessor | Dùng `tasks.register`, `tasks.named`, TaskProvider |
| `apply(plugin="...")` không sinh tên ngắn | Plugin được áp dụng trong phần thân | Dùng API tên/kiểu hoặc đổi sang `plugins {}` |
| `apply(from="...")` không tạo accessor | Script plugin thường không có cơ chế sinh accessor cho script gọi | Chuyển logic dùng chung thành precompiled convention plugin nếu phù hợp |
| `libs.xxx` không tồn tại | Alias version catalog sai hoặc catalog chưa được cấu hình | Kiểm tra TOML/Settings, tên accessor theo alias |
| `projects.core` không tồn tại | Feature preview chưa bật, project chưa include, version không hỗ trợ | Kiểm tra Settings và Gradle Wrapper |
| IDE đỏ nhưng terminal build bình thường | IDE sync/index lỗi thời | Sync Gradle project |
| Binary Kotlin plugin không gọi được `java {}` | Generated script accessor không áp dụng cho class plugin | Dùng Project API và `extensions.configure<T>` |
| Sửa cache rồi lại mất | Generated cache không phải nguồn cấu hình chính | Sửa build script/plugin/settings |
| Coi mọi method Kotlin DSL là mã sinh | Nhầm API Gradle có sẵn với schema accessors | Phân biệt `register`/`named`/`add` với `java`/`implementation` |

Đặc biệt, việc tự khai báo configuration bằng `create("x")` trước `dependencies {}` **không tạo accessor `x("...")` ngay trong lượt biên dịch ấy**. Vấn đề nằm ở ranh giới biên dịch, không phải vị trí dòng khai báo.

## 13. Bài tập kiểm tra hiểu biết

**Bài 1 — plugin được áp dụng sớm**

~~~kotlin
plugins {
    java
}
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

**Đáp án:** Hợp lệ nếu Gradle Wrapper/plugin tương thích. Java plugin tạo configuration `implementation` trước khi schema được xác định.

**Bài 2 — plugin áp dụng trong thân**

~~~kotlin
apply(plugin = "java")
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

**Đáp án:** Có thể lỗi `Unresolved reference: implementation` vì plugin được apply sau khi tập accessors của script đã được xác định. Thay bằng `plugins { java }` hoặc `dependencies.add("implementation", "...")` khi configuration đã tồn tại.

**Bài 3 — configuration động**

~~~kotlin
plugins { base }
configurations.create("analysisTools")
dependencies {
    analysisTools("org.apache.commons:commons-lang3:3.14.0")
}
~~~

**Đáp án:** Sai vì `analysisTools` không có generated accessor cho chính script này. Sửa:

~~~kotlin
plugins { base }
val analysisTools = configurations.create("analysisTools")
dependencies {
    add(analysisTools.name, "org.apache.commons:commons-lang3:3.14.0")
}
~~~

**Bài 4 — task tự đăng ký**

~~~kotlin
tasks.register("verifyDocs") {
    doLast { println("docs verified") }
}
tasks.named("verifyDocs") {
    group = "verification"
}
~~~

**Đáp án:** Hợp lệ, vì `register` và `named` là API. Chạy:

~~~bash
./gradlew -q verifyDocs
~~~

Dòng task in ra:

~~~text
docs verified
~~~

Không cần generated accessor `tasks.verifyDocs`.

**Bài 5 — version catalog**

~~~kotlin
plugins { java }
dependencies {
    implementation(libs.commons.lang)
}
~~~

**Đáp án:** `implementation` cần configuration do Java plugin tạo; `libs.commons.lang` cần alias tương ứng trong version catalog. Đó là hai nguồn accessors khác nhau, dù đứng trong cùng một câu lệnh.

**Bài 6 — binary Kotlin plugin**

Hỏi: Class Kotlin triển khai `Plugin<Project>` có dùng trực tiếp `java { ... }` giống `build.gradle.kts` không?

**Đáp án:** Không theo cơ chế generated Kotlin DSL model accessors. Nên dùng Gradle Project API, chẳng hạn `project.extensions.configure(JavaPluginExtension::class.java) { ... }` sau khi bảo đảm plugin tạo extension đã được apply.

## 14. Quy trình thực hành nên áp dụng

Khi muốn sử dụng type-safe accessors đúng cách:

1. **Đặt plugin có thể khai báo tĩnh trong `plugins {}`** của đúng project.
2. **Tận dụng model accessors** cho extension/configuration mà plugin đã tạo kịp lúc.
3. **Dùng `TaskProvider` và Gradle API** cho task/configuration do script tự tạo hoặc được đăng ký động.
4. **Dùng `configure<T>`, `named`, `add`** nếu bắt buộc apply plugin muộn hoặc code chạy ở scope không có generated accessors.
5. **Đóng gói cấu hình lặp lại thành precompiled convention plugin** khi nhiều project cần model giống nhau.
6. **Phân biệt `libs.*` và `projects.*`** vì dữ liệu gốc là version catalog và Settings, không phải extension của Java plugin.
7. **Xác minh bằng CLI Gradle Wrapper** rồi sync IDE; không sửa tay mã trong Gradle cache.

Hãy nhớ mốc:

~~~text
plugins {} -> model schema -> generated accessors -> compile script body
~~~

Mọi lời giải thích về việc “vì sao chỗ này có cú pháp ngắn mà chỗ kia không có” nên bắt đầu từ **scope của script** và **thời điểm phần tử được đưa vào schema**.

## 15. Nguồn tham khảo chính thức

- Gradle Kotlin DSL Primer — Type-safe model accessors: https://docs.gradle.org/current/userguide/kotlin_dsl.html#type-safe-accessors
- Gradle Migrating from Groovy to Kotlin DSL: https://docs.gradle.org/current/userguide/migrating_from_groovy_to_kotlin_dsl.html
- Gradle Precompiled Script Plugins: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html
- Gradle Dependency Basics — Type-safe project dependencies: https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html
- Gradle Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html
- Gradle Kotlin DSL Reference: https://docs.gradle.org/current/kotlin-dsl/

Tài liệu `current` có thể thay đổi theo phiên bản Gradle mới nhất; trong dự án thực tế, ưu tiên đọc **tài liệu ứng với phiên bản Gradle Wrapper** và tính năng/plugin đang sử dụng.