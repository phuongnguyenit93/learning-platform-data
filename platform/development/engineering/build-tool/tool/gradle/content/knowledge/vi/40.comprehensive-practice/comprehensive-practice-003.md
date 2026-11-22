# Tổ chức hệ thống nhiều module bằng Convention Plugin trong Gradle

## 1. Bối cảnh và mục tiêu thực hành

Khi một hệ thống Java phát triển từ một module thành nhiều module, mỗi module thường có `build.gradle.kts` riêng. Nếu cứ sao chép cấu hình Java toolchain, encoding, JUnit, compiler flags, repository, test reports và quality checks vào từng file, sẽ xuất hiện hiện tượng **configuration drift**: một module dùng Java 17, module khác âm thầm dùng Java 21; module này chạy JUnit Platform, module khác không; cảnh báo compiler hoặc dependency versions lệch nhau.

Gradle giải quyết bài toán bằng **Convention Plugin**: đóng gói những **quy ước dùng chung** thành một plugin có tên rõ ràng, rồi để từng module **chủ động áp dụng**. Đây là một phần quan trọng của kiến trúc build trong hệ thống đa module, khác với việc chỉ khai báo `include(":a", ":b")` hoặc di chuyển đoạn cấu hình vào một script chung.

Sau bài học, bạn có thể:

1. Phân biệt **root project**, **subproject**, **included build**, **buildSrc**, **convention plugin**, **binary plugin** và **project dependency**.
2. Thiết kế các convention plugins riêng cho Java common, Java library và Java application.
3. Tạo included build `build-logic` chứa **precompiled Kotlin DSL script plugins** có plugin ID suy từ filename.
4. Tổ chức dự án Java 17 gồm ba module `:catalog`, `:checkout` và `:app`; mỗi module có trách nhiệm và dependency boundary rõ.
5. Đặt JVM/toolchain/test configuration một lần, không sao chép vào từng module.
6. Chạy Gradle Wrapper, biên dịch và chạy Java trực tiếp với stdout xác định.
7. Phân biệt `api` với `implementation`, build dependency graph và task graph.
8. Hiểu tại sao Gradle khuyến nghị convention plugins thay cho cấu hình chéo bằng `subprojects { }`/`allprojects { }`.
9. Xử lý trường hợp version catalog và plugin resolution nằm ở **hai builds độc lập**.
10. Kiểm tra test coverage, dependency resolution, caching, CI và rủi ro bảo mật của build logic.

**Phạm vi:** Gradle 9.x/Kotlin DSL và Java 17+ (ví dụ không dùng Android/Kotlin application plugin). Các đoạn mã bên dưới được phân biệt rõ giữa **bộ dự án runnable hoàn chỉnh** và **mẫu mở rộng chỉ để giải thích API**. Nếu dùng Gradle version khác, kiểm tra Compatibility Matrix và API docs theo Wrapper của dự án.

## 2. Hình dung cấu trúc trước khi viết code

Ta muốn một ứng dụng xử lý giao dịch của một cửa hàng sách giả định:

~~~text
:catalog  ---provides---> Catalog.title(sku)
    |
    v
:checkout ---uses-------> Catalog.title(sku)
    |
    v
:app ------uses---------> CheckoutService.receipt(...)
~~~

Chiều **phụ thuộc khi build** là:

~~~text
:app  --implementation--> :checkout
:checkout --implementation--> :catalog
:catalog --no project dependencies-->
~~~

Bên cạnh đó, cả ba modules cần chung quy ước:

~~~text
                          Included build: build-logic
                  ┌───────────────────────────────────────┐
                  │ org.example.java-common              │
                  │   JDK 17, UTF-8, --release 17, JUnit │
                  │                                       │
                  │ org.example.java-library             │
                  │   java-library + java-common         │
                  │                                       │
                  │ org.example.java-application         │
                  │   application + java-common          │
                  └───────────────────────────────────────┘
                     |                  |              |
                     v                  v              v
                 :catalog           :checkout         :app
                  library            library       application
~~~

**Lưu ý mũi tên:** quan hệ **module dependency** là `project(":...")` và quyết định compile/runtime classpath. Quan hệ **plugin application** là `id("org.example....")` và quyết định cách cấu hình Gradle task. Hai cơ chế này độc lập; áp cùng convention plugin **không tự khiến modules phụ thuộc nhau**.

## 3. Các thuật ngữ phải hiểu đúng

| Thuật ngữ | Ý nghĩa | Vai trò trong ví dụ |
| --- | --- | --- |
| Root build/project | Build chính, có `settings.gradle.kts` tại gốc | `bookstore-multi` |
| Subproject/module | Project được root khai báo bằng `include(...)` | `:catalog`, `:checkout`, `:app` |
| Included build | **Một Gradle build khác** được composite/include | `build-logic` |
| `buildSrc` | Build đặc biệt được Gradle nhận diện tự động để chứa build logic | Phương án thay thế quy mô nhỏ |
| Convention plugin | Plugin đóng gói defaults và policy cho các loại module | `org.example.java-common` |
| Precompiled script plugin | Script `*.gradle.kts` được compile thành plugin | Ba scripts trong `build-logic/src/main/kotlin` |
| Binary plugin | Plugin triển khai qua `Plugin<Project>` trong Java/Kotlin | Phương án khi logic phức tạp |
| Core plugin | Plugin có sẵn từ Gradle distribution | `java`, `java-library`, `application` |
| Plugin ID | Tên để áp dụng một plugin trong `plugins { }` | `org.example.java-library` |
| Project dependency | Quan hệ dựa vào artifact của module khác | `implementation(project(":catalog"))` |
| Task dependency | Task cần output/kết quả của task khác | `compileJava` phụ thuộc compile/runtime classpath producer |
| Version catalog | Tên/phiên bản dependency/plugin cho một build | `gradle/libs.versions.toml` nếu dùng |
| Toolchain | JDK dùng cho compilation/testing/tool | Java 17 |
| Gradle Daemon JVM | JVM thực thi Gradle build engine | Java 17+ theo Gradle 9.x matrix |

**Không gọi `build-logic` là một subproject của root chỉ vì folder nằm bên dưới root.** `includeBuild("build-logic")` tạo composite relationship với **một build độc lập** có settings, repositories và plugin classpath riêng. Còn `include(":catalog")` tạo subproject trong cùng build.

## 4. Convention Plugin là gì, và không phải gì?

Convention Plugin là plugin mà trách nhiệm chủ yếu là **áp dụng các plugins đã có và thiết lập quy ước build**. Nó có thể:

- Áp `java`/`java-library`/`application` hoặc các quality plugins được duyệt.
- Chọn Java toolchain, compiler encoding, target Java release.
- Cấu hình `Test` dùng JUnit Platform và giới hạn heap.
- Khai báo những dependencies hoặc constraints thực sự chung.
- Đăng ký task/report theo API lazy nếu cần.
- Cấu hình test suites, lint/checkstyle/formatting, packaging/publishing theo đúng vai trò module.
- Thêm rule kiểm soát từ nơi dùng chung thay vì yêu cầu mỗi module tự sao chép.

Nó **không tự động**:

- Tạo project dependencies giữa các modules.
- Quyết định mọi module đều là Java application.
- Cho mọi subproject dùng chung một output directory.
- Biến một project thành microservice/deployment riêng.
- Đảm bảo CI nhanh hơn trong mọi workload.
- Xóa rủi ro plugin code thực thi với quyền Gradle process.
- Ghi đè mọi lựa chọn module bằng force nếu bạn thiết kế plugin như một convention tùy chỉnh được.

**Ví dụ khác biệt quan trọng:** Khi `:catalog` áp `org.example.java-library`, module nhận JDK 17/JUnit mặc định và Java library tasks. Nhưng `:checkout` vẫn phải khai báo `implementation(project(":catalog"))`; convention plugin không thể đoán ra dependency nghiệp vụ đó.

## 5. Ba cách chia sẻ build logic và khi nào dùng

| Cách | Mô tả | Đánh đổi |
| --- | --- | --- |
| Copy cấu hình ở mỗi module | Dễ bắt đầu, không cần plugin | Nhanh drift, trùng lặp, sửa hàng loạt |
| `subprojects { }`/`allprojects { }` | Root cấu hình chéo mọi module | Coupling khó nhìn, config order, cản isolated/parallel configuration |
| `buildSrc` | Folder special auto-discovered, chứa plugin/classes | Đơn giản khi học, nhưng thay đổi có thể invalidation rộng và classloader đặc thù |
| **Included `build-logic`** | Composite build độc lập, convention plugins | Setup ban đầu nhiều hơn, isolation/scalability rõ |
| Published binary plugin | Plugin trong artifact repo, versioned | Tốt cho nhiều repositories, cần quản lý publishing/version compatibility |

Gradle Best Practices bản 9.9 khuyến nghị **included build `build-logic`** cho build logic dùng chung trong multi-project vì giúp phân tách cấu hình, giảm coupling và có thể giảm invalidations so với `buildSrc`. `buildSrc` vẫn hợp lý khi thử nhanh hoặc repository nhỏ; không phải cách “bị cấm”.

**Chọn theo quy mô:** hai modules và một dòng setting có thể chưa cần nhiều plugin classes; còn 20–100 modules với chung JDK/tests/publishing policy sẽ có lợi rõ ràng. Không tạo convention plugin chỉ để giữ một giá trị mà không thực sự là convention.

## 6. Vì sao `subprojects { }`/`allprojects { }` thường là bước sai?

Một anti-pattern từng gặp:

~~~kotlin
// Root build.gradle.kts: VÍ DỤ KHÔNG KHUYẾN NGHỊ
subprojects {
    apply(plugin = "java")

    tasks.withType<JavaCompile>().configureEach {
        options.encoding = "UTF-8"
    }
}
~~~

Vấn đề:

1. Mọi module nhận logic **ẩn** từ root, dù `build.gradle.kts` của module không nói điều đó.
2. Có thể ép module không viết Java nhận Java plugin.
3. Cấu hình chéo các `Project` objects có nguy cơ coupling configuration phase.
4. Logic tập trung vào root trở thành “god build script”.
5. Test plugin riêng, reusable policy và plugin ownership khó hơn.
6. Khi cần module Java library khác application, xuất hiện nhiều `if (name == "...")`/`afterEvaluate` và ordering dependency.
7. Gradle Isolated Projects/Configuration Cache có yêu cầu nghiêm hơn với truy cập cross-project state.

Cách thay thế trong subproject:

~~~kotlin
plugins {
    id("org.example.java-library")
}
~~~

Nhìn vào file đã biết module là Java library và nhận quy ước nào. Root chỉ khai báo topology và những workflow tổng hợp thực sự cần. **Convention Plugin là opt-in rõ ràng**, giúp phát hiện module sai loại ở code review.

## 7. Thiết kế trách nhiệm trước khi viết conventions

Trong demo, chia ba plugin:

**`org.example.java-common`**: dùng cho tất cả module Java; áp `java`, toolchain Java 17, compile UTF-8/`--release 17`, JUnit Jupiter, test launcher và cấu hình Test. Nó **không** chọn library hay application và không chứa module-specific dependencies.

**`org.example.java-library`**: áp `java-library` và common; dành cho `:catalog` và `:checkout`. Module vẫn tự khai báo `api`/`implementation` phù hợp public API.

**`org.example.java-application`**: áp `application` và common; dành cho `:app`. Module tự chỉ ra `mainClass` và module dependencies.

Tại sao không chỉ có một plugin `org.example.everything`? Vì nếu plugin luôn áp `application` vào mọi module, nó tạo tasks/phân phối không cần thiết, làm lẫn library và executable concerns. Tách theo **module type và responsibility** có ích hơn tách theo tên team.

### 7.1. Composition quan trọng hơn inheritance

Plugin library và application **áp dụng** common plugin. Đây là *plugin composition*, không phải subclass kế thừa Kotlin. Không có yêu cầu một Gradle plugin phải extends plugin khác; chỉ cần `plugins { id("...") }` và public Gradle plugin APIs.

### 7.2. Quy ước mặc định khác chính sách bắt buộc

- **Convention/default:** “Module Java thường dùng toolchain 17; override có kiểm soát khi module có yêu cầu khác.” 
- **Policy/enforcement:** “Mọi artifact phải target Java 17, không cho phép target khác.”

Hai mô hình có mức độ cứng khác nhau. Demo đặt `options.release.set(17)` rõ để có kết quả nhất quán. Một tổ chức có nhiều product compatibility levels có thể đưa `JavaLanguageVersion` vào extension typed để từng module được phép chọn giá trị hợp lệ. Không dùng reflection/chỉnh state muộn bằng `afterEvaluate` khi có Providers/Property APIs.

## 8. Bộ project hoàn chỉnh: Java 17, Kotlin DSL, ba module

Mô hình folder:

~~~text
bookstore-multi/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       ├── org.example.java-common.gradle.kts
│       ├── org.example.java-library.gradle.kts
│       └── org.example.java-application.gradle.kts
├── catalog/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/demo/catalog/Catalog.java
│       └── test/java/demo/catalog/CatalogTest.java
├── checkout/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/demo/checkout/CheckoutService.java
│       └── test/java/demo/checkout/CheckoutServiceTest.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
~~~

**Yêu cầu môi trường:** JDK 17 có thể được tìm thấy làm toolchain; Gradle Wrapper official bản tương thích JDK được sử dụng (ví dụ Gradle 9.x với JVM 17+); truy cập repository/mirror để tải JUnit khi chạy tests. Java application **không** có runtime dependency ngoài JDK và các modules nội bộ.

**Wrapper:** danh sách file trên minh họa cấu trúc chuẩn; phải dùng Wrapper thật, đã được tạo và xác minh theo Gradle docs. Không lấy đoạn text giả làm file `gradle-wrapper.jar`. Nếu repo chưa có Wrapper, dùng một bản Gradle đáng tin để chạy `gradle wrapper` và commit cả scripts/JAR/properties, rồi sử dụng `./gradlew` nhất quán.

## 9. Root settings.gradle.kts: khai báo topology và plugin resolution

Nội dung hoàn chỉnh:

~~~kotlin
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    // Làm các plugin ID từ included build có sẵn
    // cho plugins {} trong các subproject build scripts.
    includeBuild("build-logic")

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

rootProject.name = "bookstore-multi"

include(":catalog", ":checkout", ":app")
~~~

Giải thích:

- `include(":catalog", ...)` tạo ba subprojects thuộc root build, có project paths `:catalog`, `:checkout`, `:app`.
- `pluginManagement.includeBuild("build-logic")` cho Gradle tìm **plugin implementations** cung cấp bởi included build khi gặp `plugins { id("org.example.java-library") }`.
- Plugin Management repository phục vụ các plugin IDs bên ngoài cần resolve theo chính sách; core plugin như `java-library` vốn nằm trong Gradle.
- `dependencyResolutionManagement.repositories` áp cho Java library/test dependencies của **main build**; project files không tự khai báo repo riêng.
- `FAIL_ON_PROJECT_REPOS` giúp ngăn project-level dependency repository thêm trái policy.
- `build-logic` có settings riêng, **không tự dùng main build repositories**.

**Lưu ý phân biệt hai cấu hình thường thấy:** Để plugin được dùng trong `plugins { }` của subprojects, đặt `includeBuild("build-logic")` trong `pluginManagement` là cách trực tiếp, rõ ràng. Với composite build dùng để **substitute bình thường các project dependencies**, `includeBuild` đặt ở root settings ngoài `pluginManagement` cũng có vai trò khác. Không hoán đổi chúng tùy tiện rồi kết luận Gradle “không tìm thấy plugin”.

### 9.1. Vì sao file settings khác build.gradle.kts?

`settings.gradle.kts` định nghĩa project topology và các bước resolution sớm. `build.gradle.kts` cấu hình project/plugins/tasks/dependencies. Nếu đưa module `include(":catalog")` vào file build của module, Gradle không nhận như một settings-level declaration. Tách rõ trách nhiệm giúp root mỏng và dễ audit.

### 9.2. Repository policy không phải sandbox mã build

`FAIL_ON_PROJECT_REPOS` giúp build nhất quán, nhưng nếu một PR chưa tin cậy có thể sửa chính settings, nó có thể đổi rule. CI cần permissions/network/secrets isolation độc lập; build script không phải nơi duy nhất bảo vệ supply chain.

## 10. Root build.gradle.kts: chỉ workflow tổng hợp

Nội dung ví dụ:

~~~kotlin
plugins {
    base
}

tasks.register("allChecks") {
    group = "verification"
    description = "Run checks in all Java modules"
    dependsOn(
        ":catalog:check",
        ":checkout:check",
        ":app:check"
    )
}
~~~

Root không áp `java`/`application` vì không chứa Java source. Nó chỉ có task tổng hợp giúp developer chạy:

~~~bash
./gradlew allChecks
~~~

`dependsOn` trên các task paths là một cách dễ hiểu để tổng hợp lifecycle trong demo. Nó không đòi các subprojects được cấu hình bằng `subprojects { }` và không tạo module dependency. Nếu dự án lớn, có thể sử dụng test suites/report aggregation plugins để có báo cáo tập trung; đừng ép root project compile Java khi root không có code.

**Không lẫn “aggregate task phụ thuộc ba check tasks” với “app module phụ thuộc hai library modules”.** Hai quan hệ phục vụ mục đích khác nhau.

## 11. build-logic/settings.gradle.kts: included build có settings riêng

Nội dung hoàn chỉnh:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "build-logic"
~~~

Không thêm `include(":catalog")` ở đây. Nó là settings của build **chứa plugin implementations**, không phải chứa ứng dụng.

Trong một tổ chức có mirror nội bộ, hãy dùng những mirror được duyệt thay vì public URLs trong mỗi build. Điều quan trọng là hiểu main build và included build **không tự chia sẻ settings/repositories/version catalog**, dù thư mục nằm chung trong repository.

### 11.1. Không cần tạo mỗi convention một subproject trong demo

Ở quy mô nhỏ, một included build với một plugin project như ở ví dụ là đủ. Khi build-logic lớn, có thể tách `build-logic:java-conventions`, `build-logic:quality-conventions` hoặc `build-logic:publishing-conventions` để giảm invalidation/classpath footprint. Đây là cải tiến kiến trúc sau khi đã có nhu cầu, không phải requirement để tạo precompiled script plugin đầu tiên.

## 12. build-logic/build.gradle.kts: bật compilation của precompiled scripts

Nội dung hoàn chỉnh:

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
~~~

Giải thích:

- Plugin `kotlin-dsl` tạo môi trường build logic Kotlin DSL, compile `*.gradle.kts` trong `src/main/kotlin` thành Gradle plugin classes.
- Những precompiled scripts trong source set trở thành plugin implementations có ID dựa trên filename (và package declaration nếu có).
- `gradlePluginPortal()` cho phép giải quyết Gradle Kotlin DSL/plugin dependencies cần thiết. Có thể thay bằng enterprise mirror theo policy.
- Không cần tự viết class `Plugin<Project>` và `gradlePlugin { plugins { ... } }` cho từng precompiled script thông thường.

**Không đưa `kotlin-dsl` vào mọi Java subproject**. Nó dùng để **xây plugin implementations trong build-logic**, không để compile `Catalog.java` hay `Main.java`.

### 12.1. Vai trò của file name

Ba file:

~~~text
org.example.java-common.gradle.kts
org.example.java-library.gradle.kts
org.example.java-application.gradle.kts
~~~

tạo ba plugin IDs tương ứng (không có package declaration):

~~~text
org.example.java-common
org.example.java-library
org.example.java-application
~~~

Không đặt tên plugin file `org.example.java-common.gradle.kts.txt` hoặc để sai `src/main/kotlin`. Nếu đặt package declaration/đổi path theo convention khác, plugin ID có thể đổi: phải đối chiếu quy tắc chính thức. **Plugin ID không phải Kotlin class name** trong cách triển khai này.

## 13. Convention 1: org.example.java-common.gradle.kts

Tạo **`build-logic/src/main/kotlin/org.example.java-common.gradle.kts`**:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    maxHeapSize = "512m"
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}
~~~

Đây là **project-scoped precompiled script plugin**, không phải một file cho `settings.gradle.kts`. Áp vào project nào thì Java plugin/toolchain/Test conventions cấu hình cho project đó.

### 13.1. Giải thích từng khối

**`plugins { java }`:** thêm Java lifecycle tasks/configurations/source sets. Các module library/application có thể áp tiếp plugin chuyên biệt; việc apply core plugin nhiều lần trên cùng project không tạo hai JavaCompile tasks.

**`java.toolchain.languageVersion.set(17)`:** yêu cầu JDK 17 cho task compilation/test tooling phù hợp. Đây **không phải** cờ đặt JVM chạy Gradle Daemon. Với Gradle 9.x, JVM chạy Gradle có yêu cầu runtime riêng.

**`JavaCompile.options.release.set(17)`:** yêu cầu `javac` tuân thủ Java 17 language/API/bytecode target. Không vô tình phát bytecode Java 21 trên máy developer vì họ cài JDK mới.

**`options.encoding = "UTF-8"`:** thống nhất decoding Java sources. Nếu source có tiếng Việt hoặc emoji, encoding càng quan trọng; output ứng dụng còn phụ thuộc console encoding nếu in ký tự Unicode.

**`tasks.withType<JavaCompile>().configureEach`:** cấu hình lazily tất cả JavaCompile tasks thuộc project, kể cả tasks được plugin khác đăng ký sau. Không dùng `afterEvaluate` chỉ để chờ Java plugin.

**`tasks.withType<Test>().configureEach`:** chọn JUnit Platform và giới hạn heap cho các Test task. `512m` là **giá trị mẫu**, không có nghĩa mọi runner đủ RAM. Trong CI có nhiều Test JVMs/Gradle workers, cần cân đối.

**`testImplementation`:** JUnit Jupiter nằm trên test compile/runtime classpath, không bị đưa vào public API của library.

**`testRuntimeOnly`:** JUnit Platform Launcher có thể cần trên runtime classpath theo version Gradle/JUnit. Pin 1.11.4 cho demo, phù hợp JUnit 5.11.4 sample.

### 13.2. Một convention có nên chứa JUnit version cố định?

Ở demo, có để các modules chạy được mà không cần version catalog bổ sung. Với production mono-repo, nên quản lý dependency versions có policy: version catalog, platform/BOM hoặc constraints. **Convention plugin và version catalog không đối nghịch**: một cái quản lý **hành vi build**, một cái quản lý **tọa độ/versions**. Phần nâng cao bên dưới sẽ chỉ ra giới hạn giữa root build và included build khi dùng catalog.

### 13.3. Vì sao không bật maxParallelForks bằng số cores mặc định?

Demo không cần test forks song song. Nếu áp `maxParallelForks = availableProcessors()` cho tất cả modules, RAM có thể bị quá tải khi nhiều Test tasks cùng chạy. Tối ưu test concurrency phải dựa trên runner budget và test isolation, không lấy processor count làm công thức bắt buộc trong shared convention.

## 14. Convention 2: org.example.java-library.gradle.kts

Tạo **`build-logic/src/main/kotlin/org.example.java-library.gradle.kts`**:

~~~kotlin
plugins {
    `java-library`
    id("org.example.java-common")
}
~~~

Vì sao plugin nhỏ như vậy vẫn hữu ích?

- Nó tạo **module type rõ ràng**: Java library, không phải application.
- `java-library` cung cấp hai dependency buckets có semantics khác nhau: `api` và `implementation`.
- `org.example.java-common` mang toolchain, compiler và JUnit conventions.
- Một ngày cần library-specific Checkstyle, Javadoc, sources JAR hoặc publishing, bạn bổ sung ở **một nơi** thay vì sửa nhiều modules.
- Module vẫn sở hữu dependency coordinates riêng; không ép mọi library phụ thuộc cùng một module nghiệp vụ.

**Không nhất thiết phải thêm `java` riêng** trong file này vì `java-library` đã áp Java plugin, nhưng common plugin áp `java` cũng an toàn. Gradle plugin application là idempotent trong project context.

### 14.1. API vs implementation

Khi Java library B dùng library A:

~~~kotlin
dependencies {
    implementation(project(":catalog"))
}
~~~

Nếu `B` dùng các classes từ `catalog` chỉ trong **implementation**, không lộ `Catalog` types ở public signatures của B, thì `implementation` phù hợp. Nếu public API của B có tham số/return type là `demo.catalog.Catalog` hoặc một type từ A, consumer có thể cần A trên compile classpath, và `api(project(":catalog"))` phù hợp hơn.

Chọn scope dựa vào **public API exposure**, không dựa vào “module nào quan trọng hơn”. Scope đúng giúp compile avoidance và tránh rò rỉ transitive dependencies.

## 15. Convention 3: org.example.java-application.gradle.kts

Tạo **`build-logic/src/main/kotlin/org.example.java-application.gradle.kts`**:

~~~kotlin
plugins {
    application
    id("org.example.java-common")
}
~~~

`application` thêm `run`, distribution/start scripts và cấu hình `application.mainClass`. Chỉ các module có entry point mới cần nó. Không áp convention này vào `:catalog` hoặc `:checkout` chỉ vì chúng có Java code.

**Phân chia trách nhiệm:** convention quyết định “đây là một Java app có chuẩn build chung”; từng app module quyết định “main class của tôi là gì” và “tôi phụ thuộc library modules nào”.

### 15.1. Có thể đặt default main class vào convention không?

Có, nếu một repository thực sự có quy ước chung (ví dụ mọi app dùng cùng bootstrap class). Nhưng nếu mỗi module có entry point khác nhau, hardcode `mainClass` ở shared convention sẽ sai. Hãy để app tự cấu hình hoặc thiết kế typed extension nếu cần convention có thể tùy chỉnh.

## 16. catalog/build.gradle.kts: apply library convention

Nội dung hoàn chỉnh:

~~~kotlin
plugins {
    id("org.example.java-library")
}
~~~

Không cần viết `java { toolchain ... }`, `tasks.test { useJUnitPlatform() }` hay repository ở file này vì đã ở đúng nơi. Module `:catalog` không phụ thuộc module nội bộ nào.

**Một lợi ích kiến trúc:** nhìn file nhỏ là hiểu module dùng library convention và không có dependencies riêng; không phải dò root `subprojects` để biết JUnit/version/encoding được cấp ở đâu.

## 17. catalog Java sources và unit test

### 17.1. catalog/src/main/java/demo/catalog/Catalog.java

~~~java
package demo.catalog;

public final class Catalog {
    private Catalog() {
    }

    public static String title(String sku) {
        return switch (sku) {
            case "BK-101" -> "Java Handbook";
            case "BK-202" -> "Gradle Notes";
            default -> "Unknown";
        };
    }
}
~~~

`switch expression` hoạt động trên Java 17. Java source không import Gradle/JUnit, vì application code và build logic là hai concerns khác nhau.

### 17.2. catalog/src/test/java/demo/catalog/CatalogTest.java

~~~java
package demo.catalog;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CatalogTest {
    @Test
    void resolvesKnownBook() {
        assertEquals("Java Handbook", Catalog.title("BK-101"));
    }

    @Test
    void returnsUnknownForOtherSku() {
        assertEquals("Unknown", Catalog.title("OTHER"));
    }
}
~~~

Bạn không phải khai báo JUnit trong `catalog/build.gradle.kts`: plugin `org.example.java-common` đã thêm `testImplementation`, `testRuntimeOnly` và `useJUnitPlatform()`. Nếu quên áp convention, source JUnit có thể không compile — đó là dấu hiệu module chưa nhận quy ước.

### 17.3. Unit test bao nhiêu trường hợp?

Hai tests kiểm input có/không có mapping. Production có thể cần case sensitivity, null/empty validation, đọc metadata từ database, localization. Đây là demo đủ để chứng minh test framework được chia sẻ qua convention, không phải domain model hoàn chỉnh.

## 18. checkout/build.gradle.kts: khai báo dependency nghiệp vụ

Nội dung hoàn chỉnh:

~~~kotlin
plugins {
    id("org.example.java-library")
}

dependencies {
    implementation(project(":catalog"))
}
~~~

`:checkout` là Java library và dùng `Catalog.title(sku)` bên trong phương thức nhận SKU. Vì public `CheckoutService.receipt` trả `String` và chỉ nhận `String, int`, public API không lộ `Catalog` type nên chọn `implementation(project(":catalog"))`.

Khi consumer `:app` compile, nó cần public classes trong `:checkout`, còn Gradle sẽ lo runtime classpath đưa đủ internal implementation dependencies để chạy. Không hardcode relative JAR paths kiểu `../catalog/build/libs/catalog.jar`; làm vậy mất task dependency/provenance chính xác.

### 18.1. Dependency không phải task ordering tự phát

Khai báo project dependency khiến Gradle resolution chọn artifact producers phù hợp (compile/runtime variants) và tạo implicit task relationships đúng. Không cần viết `tasks.compileJava.dependsOn(":catalog:jar")` chỉ để sửa classpath trong Java application chuẩn.

## 19. checkout Java sources và unit tests

### 19.1. checkout/src/main/java/demo/checkout/CheckoutService.java

~~~java
package demo.checkout;

import demo.catalog.Catalog;

public final class CheckoutService {
    private CheckoutService() {
    }

    public static String receipt(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive"
            );
        }

        return "Receipt: "
            + Catalog.title(sku)
            + " x"
            + quantity;
    }
}
~~~

**Điểm quan trọng về module boundary:** `CheckoutService` gọi `Catalog` trong phần implementation, nhưng public signature không dùng type `Catalog`. Module `:app` sẽ gọi `CheckoutService.receipt`, không cần import `demo.catalog.Catalog`.

### 19.2. checkout/src/test/java/demo/checkout/CheckoutServiceTest.java

~~~java
package demo.checkout;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CheckoutServiceTest {
    @Test
    void createsReceiptForKnownBook() {
        assertEquals(
            "Receipt: Gradle Notes x3",
            CheckoutService.receipt("BK-202", 3)
        );
    }

    @Test
    void createsReceiptForUnknownSku() {
        assertEquals(
            "Receipt: Unknown x1",
            CheckoutService.receipt("UNKNOWN", 1)
        );
    }

    @Test
    void rejectsNonPositiveQuantity() {
        assertThrows(
            IllegalArgumentException.class,
            () -> CheckoutService.receipt("BK-101", 0)
        );
    }
}
~~~

Hai modules `:catalog` và `:checkout` đều dùng cùng convention Java/JUnit dù build files khác trách nhiệm. Đây là lợi ích dễ kiểm chứng của shared build logic. Nếu muốn thay JUnit policy, cập nhật common convention rồi chạy lại tests ở cả hai modules.

## 20. app/build.gradle.kts: chỉ mainClass và dependency

Nội dung hoàn chỉnh:

~~~kotlin
plugins {
    id("org.example.java-application")
}

dependencies {
    implementation(project(":checkout"))
}

application {
    mainClass.set("demo.app.Main")
    applicationName = "bookstore"
}
~~~

**Chủ động tách hai loại cấu hình:**

- `id("org.example.java-application")`: loại module và các tiêu chuẩn Java/test.
- `implementation(project(":checkout"))`: dependency nghiệp vụ cụ thể.
- `mainClass.set(...)`: entry point cụ thể của app.
- `applicationName`: tên application distribution/start script; là phần module-specific, không cần đặt ở common convention.

Một Gradle project là Java Application **không cần** cũng khai báo `java-library`. `application` đã áp Java plugin; library/app conventions chỉ nên chọn đúng module type.

## 21. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.checkout.CheckoutService;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String sku = args.length > 0 ? args[0] : "BK-101";
        int quantity = args.length > 1
            ? Integer.parseInt(args[1])
            : 2;

        System.out.println(
            CheckoutService.receipt(sku, quantity)
        );
    }
}
~~~

Java Main dùng **duy nhất** `CheckoutService`. Module `:app` không import `Catalog`. Đây là cách minh họa compile boundary khi `:checkout` dùng `implementation(project(":catalog"))`.

Không dùng `System.exit(0)` vì ứng dụng demo không có vòng đời server. `Integer.parseInt` sẽ ném `NumberFormatException` nếu quantity argument không phải số; đó là behavior Java chuẩn. Production có thể bổ sung validation/CLI library nhưng không cần để chứng minh convention plugin.

## 22. Chạy từ Gradle Wrapper và kết quả chính xác

Trên Linux/macOS từ root `bookstore-multi`:

~~~bash
./gradlew :app:run --quiet
~~~

Stdout do Java Main tạo, chính xác:

~~~text
Receipt: Java Handbook x2
~~~

Truyền SKU và quantity:

~~~bash
./gradlew :app:run --args="BK-202 3" --quiet
~~~

Stdout Java Main:

~~~text
Receipt: Gradle Notes x3
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run --quiet
.\gradlew.bat :app:run --args="BK-202 3" --quiet
~~~

Stdout từ Java code tương ứng giữ nguyên. Có thể có Gradle/Java warning trên stderr tùy máy, toolchain resolution và repository network; **đừng coi hai dòng trên là toàn bộ console log của Gradle**.

**Bộ test:**

~~~bash
./gradlew :catalog:test :checkout:test
./gradlew allChecks
./gradlew build
~~~

Các Test tasks có 2 tests ở `:catalog` và 3 tests ở `:checkout`; `:app` có thể hiển thị `NO-SOURCE` cho test nếu chưa tạo tests ở đó. Gradle không bắt buộc in “5 tests passed” ra console ở mọi version; xem XML/HTML reports để xác minh số tests.

### 22.1. Lượt đầu làm nhiều việc hơn

Ở lần đầu tiên, Gradle có thể compile `build-logic` Kotlin scripts, resolve JUnit dependencies, compile Java sources và chạy tests. Lượt sau, nhiều tasks có thể `UP-TO-DATE` hoặc `FROM-CACHE` nếu cấu hình/cache cho phép. Đừng nhầm việc plugin build-logic xuất hiện trong task log là một application module mới.

## 23. Chạy Java 17 bằng javac/java để kiểm ứng dụng độc lập

Muốn xác minh Java source **không phụ thuộc Gradle**, compile các modules theo thứ tự dependency. Từ root project:

Linux/macOS:

~~~bash
mkdir -p out/catalog out/checkout out/app

javac --release 17 -encoding UTF-8 \
    -d out/catalog \
    catalog/src/main/java/demo/catalog/Catalog.java

javac --release 17 -encoding UTF-8 \
    -cp out/catalog \
    -d out/checkout \
    checkout/src/main/java/demo/checkout/CheckoutService.java

javac --release 17 -encoding UTF-8 \
    -cp "out/catalog:out/checkout" \
    -d out/app \
    app/src/main/java/demo/app/Main.java

java -cp "out/catalog:out/checkout:out/app" \
    demo.app.Main BK-202 3
~~~

**Stdout chính xác:**

~~~text
Receipt: Gradle Notes x3
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out\catalog,out\checkout,out\app | Out-Null

javac --release 17 -encoding UTF-8 -d out\catalog catalog\src\main\java\demo\catalog\Catalog.java

javac --release 17 -encoding UTF-8 -cp out\catalog -d out\checkout checkout\src\main\java\demo\checkout\CheckoutService.java

javac --release 17 -encoding UTF-8 -cp "out\catalog;out\checkout" -d out\app app\src\main\java\demo\app\Main.java

java -cp "out\catalog;out\checkout;out\app" demo.app.Main BK-202 3
~~~

**Stdout Java Main vẫn là:**

~~~text
Receipt: Gradle Notes x3
~~~

Khác biệt platform: `:` là classpath separator của Linux/macOS, `;` là separator của Windows. Mỗi lệnh javac nhận đúng modules producer trên classpath. Không cần JUnit để compile chỉ main sources, nhưng phải có JUnit/Gradle dependency khi compile/test các test sources.

**Giới hạn kiểm chứng:** `javac/java` không compile `build-logic`, không chứng minh Kotlin DSL convention scripts hợp lệ và không chạy Gradle task graph. Nó chỉ là baseline tách lỗi Java logic khỏi lỗi build system.

## 24. Vì sao main build có thể tìm thấy plugin không publish?

`build-logic` là **included plugin build** được đăng ký trong `pluginManagement.includeBuild`. Gradle dùng plugin marker/implementation sản xuất từ included build để giải quyết plugin IDs trong root/subprojects. Vì vậy không cần publish `org.example.java-library` lên Plugin Portal hoặc Maven Local cho demo.

Quá trình khái quát:

~~~text
Root settings.gradle.kts
      |
      +--> pluginManagement.includeBuild("build-logic")
      |           |
      |           +--> build-logic builds plugin classes/markers
      |           |
      |           +--> exposes org.example.java-common
      |           +--> exposes org.example.java-library
      |           +--> exposes org.example.java-application
      |
      +--> include(":catalog", ":checkout", ":app")
                      |
                      v
              Each module plugins { id(...) }
                      |
                      v
                Gradle applies conventions
~~~

Điểm quan trọng không phải “Gradle quét mọi file `*.gradle.kts` của root”. Chỉ khi build-logic có đúng plugin build setup và được include đúng plugin resolution scope thì scripts mới trở thành plugin implementations có thể áp.

### 24.1. Không cần `version` cho local convention plugin

Subproject dùng:

~~~kotlin
plugins {
    id("org.example.java-library")
}
~~~

không cần `version "1.0.0"` trong ví dụ vì plugin implementation lấy từ included build được pin theo chính repo/commit. Khi tổ chức **publish** binary convention plugin ra Maven/Plugin Portal để reuse giữa repositories, cần plugin artifact versioning và quản trị dependency compatibility riêng.

## 25. Plugin API, plugin marker và plugin implementation

Một precompiled plugin phải có hai thứ đủ rõ:

- **Plugin ID**: tên module sử dụng trong `plugins { id(...) }`.
- **Plugin implementation**: Gradle class/JAR được build từ script và các dependencies trong build-logic.

Khi thêm plugin ngoài như Spotless hoặc Kotlin JVM **vào bên trong** convention plugin, có thêm ranh giới classpath:

1. Plugin implementation dependency phải nằm trên **build-logic plugin build classpath**.
2. Precompiled script plugin áp plugin ngoài bằng `id("plugin.id")` không thêm version trong `plugins` block của precompiled script.
3. Phiên bản được xác định bởi dependency trong `build-logic/build.gradle.kts`.
4. Repository để resolve dependency đó thuộc included build, không phải mặc định từ main build.

**Không dùng**:

~~~kotlin
// Bên trong precompiled script plugin: KHÔNG KHUYẾN NGHỊ
plugins {
    id("com.example.external") version "1.2.3"
}
~~~

Vì theo Gradle precompiled script plugin docs, `version "..."` và `apply false` không được hỗ trợ trong `plugins` block của precompiled scripts. Cần add plugin artifact vào `implementation` của plugin build, rồi apply không version. Ví dụ trên dùng plugin ID giả định để minh họa cấu trúc, không phải dependency runnable của demo.

### 25.1. Không vô tình biến common plugin thành “plugin classpath tổng hợp”

Nếu thêm 20 third-party plugins vào một shared convention plugin, mọi module dùng nó có thể chịu footprint/resolution/compatibility không cần thiết. Tách `java-common`, `quality`, `publishing` theo trách nhiệm. Module nào cần static analysis thì opt-in tương ứng; release/publishing secrets không được có trong mọi local build.

## 26. Version Catalog trong main build không tự có ở build-logic

Một điểm rất dễ nhầm: main build tự nhận catalog từ `gradle/libs.versions.toml`, nhưng `build-logic` là **included build có settings riêng**. Nó không tự kế thừa catalog generated accessors từ root.

Ví dụ khi main build có:

~~~text
gradle/libs.versions.toml
~~~

Và nội dung **chỉ minh họa hướng quản lý dependencies, không phải file cần thêm cho demo ở mục 8–23**:

~~~toml
[versions]
junit = "5.11.4"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
~~~

Trong main subproject, `libs.junit.jupiter` có thể dùng theo Gradle catalog accessors nếu build cấu hình đúng. Nhưng trong `build-logic`, gọi `libs` từ included build khi không import catalog có thể báo unresolved reference hoặc thiếu named catalog.

### 26.1. Import catalog rõ trong build-logic settings (tùy chọn)

Thêm vào **`build-logic/settings.gradle.kts`** khi thực sự cần catalog chung:

~~~kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}
~~~

Đây là **đoạn bổ sung có điều kiện**, không cần cho demo runnable chính. Nếu đã có `dependencyResolutionManagement` trong included build, hãy hợp nhất vào đúng block, không tạo nhiều block mâu thuẫn. Path tương đối ở đây tính từ `build-logic` tới root catalog.

**Lưu ý:** `from()` chỉ được gọi một lần cho mỗi catalog; không thể gộp hai TOML trong cùng catalog bằng hai lệnh `from`. Một included build có thể cần catalog riêng nếu dependencies của build logic khác đáng kể application.

### 26.2. Version catalog trong precompiled scripts có giới hạn

Không mặc định dùng:

~~~kotlin
// Đây là ANTI-PATTERN trong precompiled plugins { }:
plugins {
    alias(libs.plugins.someExternalPlugin)
}
~~~

Type-safe catalog accessors cho `plugins` block của precompiled script plugins **không được dùng như ở regular project build scripts**. Với external plugin, thêm tọa độ plugin implementation vào `build-logic` dependencies và dùng `id("...")` không version, hoặc dùng typed/binary plugin patterns thích hợp.

### 26.3. Catalog không giải quyết project dependency architecture

Catalog quản lý dependency coordinates/versions; nó không thay `implementation(project(":catalog"))`. Đừng publish nội bộ modules của cùng root multi-project lên Maven chỉ để version catalog “nhìn thấy”; project dependencies giúp Gradle phát hiện task producers/variants và recompile đúng. Với modules được phát hành độc lập, mới cân nhắc published dependency coordinates.

## 27. Nguồn repository cho hai builds phải phân biệt

Main root settings đã khai báo `mavenCentral()`. Nhưng `build-logic/build.gradle.kts` có `repositories { gradlePluginPortal() }` riêng.

Điều này là **thiết kế đúng** vì hai builds có classpaths độc lập:

| Build | Dùng repository để resolve gì? | Cấu hình trong demo |
| --- | --- | --- |
| Main build | JUnit Jupiter/Launcher cho Java tests | `dependencyResolutionManagement.repositories { mavenCentral() }` |
| Included build-logic | Gradle Kotlin DSL plugin/build logic compilation | `build-logic/build.gradle.kts { repositories { gradlePluginPortal() } }` |
| Plugin resolution của main | Plugin IDs trong subprojects | `pluginManagement.includeBuild("build-logic")` |
| Plugin resolution của build-logic | `kotlin-dsl` và plugin build prerequisites | `build-logic/settings.gradle.kts` |
| Internal artifact repo | Chỉ cần khi có private dependencies | Không dùng trong demo |

Nếu tổ chức có repository mirror/credential policy, đặt settings/repos đúng cho **cả hai builds**. Mất network trong build-logic có thể làm build fail ngay trước khi root tests được chọn; đừng đổ lỗi JUnit nếu plugin build chưa compile.

### 27.1. `FAIL_ON_PROJECT_REPOS` có bao trùm build-logic không?

Đó là repository policy của **main build settings**. Vì build-logic là included build, nó có settings/repository policy riêng. Không suy một `FAIL_ON_PROJECT_REPOS` ở root tự chặn mọi repository trong included build. Muốn nhất quán toàn tổ chức, xây policy ở các builds liên quan hoặc qua trusted enterprise infrastructure.

## 28. API vs implementation và khả năng compile avoidance

Trong `:checkout`:

~~~kotlin
dependencies {
    implementation(project(":catalog"))
}
~~~

Tại sao không dùng `api(project(":catalog"))`? Vì public `CheckoutService.receipt(String, int): String` không lộ type từ catalog. Nhờ Java Library plugin phân biệt API và implementation, Gradle có thể tránh một số downstream recompile khi thay đổi implementation không làm thay public ABI.

Nếu sau này public method trở thành:

~~~java
// Minh họa API exposure, KHÔNG phải bản sửa runnable
public static demo.catalog.BookDetails receiptDetails(String sku);
~~~

khi đó `BookDetails` nằm trong public method signature. Nếu thật sự dùng type ấy, cần khai báo dependency scope phù hợp (thường `api(project(":catalog"))`). Không chỉ thay `implementation` thành `api` vì một module khác “cần nhìn thấy mọi class” — điều đó làm tăng coupling và compile classpath.

### 28.1. Gradle không tự tách source code thành module boundaries

Một file Java nằm trong `checkout/src/main/java` không thể compile trực tiếp với `Catalog` nếu thiếu project dependency. Convention plugin đặt JDK/test default, nhưng không tự tìm imports Java để tạo dependencies. Đây là feature: module dependencies phải được khai báo có chủ đích.

## 29. Dùng cùng convention cho tests và reports mà không tăng flaky tests

Common plugin hiện cấu hình:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    maxHeapSize = "512m"
}
~~~

Nó đồng nhất test engine/heap. Nhưng **không** bảo đảm tests tự cô lập khi chạy song song. Nếu nhiều modules dùng database chung, ports cố định hoặc temp files dùng chung, bật `--parallel` có thể tạo race.

Khuyến nghị:
- Unit tests không dùng shared external state nếu không cần.
- Dùng unique temp directories/ports/fixtures cho integration tests.
- Tách `integrationTest` suite và giới hạn concurrency đúng tài nguyên.
- Không tự tăng `maxParallelForks` ở convention khi chưa đo CI RAM/CPU.
- Cấu hình test reports đáng tin, so test counts giữa modules.
- Trên CI, đặt memory/worker limits dựa runner, không dựa duy nhất processors của host.

### 29.1. Nếu một module cần Test policy khác

Có thể cấu hình module-specific `tasks.test { ... }` khi đó là exception được duyệt; nhưng nên cân nhắc policy override hợp lệ, tránh tăng complexity. Khi exceptions nhiều, tách thành convention plugin mới (ví dụ integration-test convention) thay vì đặt điều kiện theo module name trong common plugin.

## 30. Kết quả task graph và parallelism

Chạy:

~~~bash
./gradlew :app:run --dry-run
~~~

Lệnh `--dry-run` có thể cho thấy tasks cần để build/run app, nhưng không thực thi Java Main. Task log cụ thể, thứ tự và tên prerequisite phụ thuộc Gradle/plugin version; **không nên bịa một transcript stdout cố định**. Khi chạy thật, Java project dependency giúp Gradle biên dịch catalog rồi checkout rồi app theo graph.

Chạy song song khi đủ tài nguyên:

~~~bash
./gradlew allChecks --parallel --max-workers=2
~~~

Các modules có tests đủ điều kiện có thể chạy concurrently theo graph, nhưng chuỗi `app→checkout→catalog` vẫn ràng buộc compilation. Gradle 9.x với Configuration Cache có một số thay đổi về task parallelism cùng project; không dựa vào thứ tự task để ghi chung một file.

### 30.1. Convention plugin không phải task aggregator

Common convention chỉ cấu hình một project tại thời điểm được áp. Root task `allChecks` tổng hợp các module checks. Nếu cần test report aggregation, nên dùng plugin chuyên trách hoặc outgoing variants; không sửa từng subproject từ root chỉ để kéo reports.

### 30.2. Khi chạy allChecks hai lần

Lần đầu cần compile plugin build logic và Java/test classes; lần sau có thể thấy `UP-TO-DATE`/`FROM-CACHE`. Đừng coi việc Gradle skip là “test không được khai báo”; inspect task outcome và HTML/XML reports. Với logic kiểm thử thay đổi, chạy `--rerun-tasks` có kiểm soát hoặc clean state khi cần.

## 31. Configuration Cache và lazy APIs

Gradle có Configuration Cache giúp lưu/tái sử dụng configuration state. Convention plugin tốt nên:

1. Áp plugin rõ trong `plugins { }`.
2. Dùng `tasks.register` cho custom task thay eager `tasks.create`.
3. Dùng `tasks.withType<...>().configureEach` thay eagerly iterate all tasks.
4. Dùng `Property<T>`/`Provider<T>` khi cấu hình deferred inputs/outputs.
5. Không đọc `Project` hoặc `Configuration` bừa trong task action.
6. Không dùng `afterEvaluate` tràn lan để che order dependency.
7. Không truy cập state của subprojects khác trong configuration phase.
8. Khai báo inputs/outputs cho custom tasks theo Gradle APIs.
9. Tránh chạy arbitrary external process trong configuration phase.
10. Test config cache sau khi plugin/build logic thay đổi.

Chạy hai lượt:

~~~bash
./gradlew allChecks --configuration-cache
./gradlew allChecks --configuration-cache
~~~

Nếu xảy ra lỗi, xem Configuration Cache report và API lifecycle của plugin cần sửa. Không mặc định plugin từ `build-logic` tự compatible chỉ vì nó là precompiled script.

### 31.1. `afterEvaluate` là dấu hiệu cần xem lại

Trong nhiều trường hợp, plugin owner dùng `afterEvaluate` chỉ vì chưa biết lifecycle của extension/property/plugin application. Hãy dùng `pluginManager.withPlugin("java") { ... }`, typed extensions và lazy task providers khi cần. `afterEvaluate` không phải luôn bị cấm, nhưng thường làm coupling/order khó đoán.

## 32. Build Cache và phạm vi invalidation của build-logic

Included build cho build logic có thể cải thiện khả năng cô lập và hiệu năng so với `buildSrc`, nhất là khi tách build-logic thành các subprojects. Tuy nhiên:

- Thay đổi common convention ảnh hưởng các modules áp dụng nó.
- Thay đổi convention chỉ dùng ở app không nhất thiết phải invalidation mọi library modules trong kiến trúc tách classpaths tốt.
- Một build-logic included build chứa **tất cả plugins trong một project** vẫn có coupling classpath lớn; đừng hứa “đổi một file plugin không ảnh hưởng module khác” tuyệt đối.
- Build Cache lưu task outputs, không tự đảm bảo logic mới không làm thay plugin behavior.
- Configuration Cache có thể bị invalidated khi build logic classpath/configuration inputs đổi.
- Gradle Kotlin DSL script compilation có thể có incremental behavior mới tùy version, nhưng thời gian thực phụ thuộc workload.

**Đo chứ không suy:** dùng `--profile` hoặc công cụ được policy cho phép; theo dõi configuration time, Kotlin DSL compilation, cache misses, elapsed wall time và số modules bị ảnh hưởng. Không dùng một lần warm build so với clean build rồi kết luận conventionalization làm build nhanh x lần.

### 32.1. Khi nào tách build-logic thành nhiều projects?

Khi plugin set lớn, có lifecycle khác nhau, owner khác nhau hoặc plugin dependency classpath nặng. Có thể tách:
- `build-logic:java`
- `build-logic:quality`
- `build-logic:publishing`

Một module chỉ apply plugin cần thiết; có thể giảm invalidation và quyền/hệ dependency không cần thiết. Nhưng tách quá sớm tạo thêm cấu trúc phức tạp và module overhead. Bắt đầu với ba conventions đơn giản trong một build-logic project là hợp lý để học.

## 33. buildSrc và included build-logic: so sánh có điều kiện

| Chủ đề | `buildSrc` | Included `build-logic` |
| --- | --- | --- |
| Được Gradle phát hiện | Tự động qua special folder | Phải `includeBuild(...)` |
| Độc lập settings/build | Có build riêng theo semantics của buildSrc | Có build riêng rõ ràng |
| Classpath | BuildSrc classes có thể tự động hiện trên build classpath | Plugin implementations được resolve qua included build |
| Plugin IDs | Precompiled scripts theo filenames | Precompiled scripts theo filenames |
| Reuse ngoài repo | Hạn chế tự nhiên | Dễ tổ chức publish/consumption hơn |
| Invalidation | Thay đổi buildSrc có thể tác động nhiều modules | Có thể granular hơn khi chia build-logic |
| Cấu hình ban đầu | Ít bước hơn | Cần settings/root resolution setup |
| Phù hợp | Prototype, repo nhỏ | Multi-project lớn/long-lived build logic |

Không cần **cả hai** cho demo. Nếu có `buildSrc` cũ, không nhất thiết xóa nó ngay để tạo `build-logic`; di chuyển theo PR từng bước và kiểm plugin IDs/classpaths. Tránh giữ hai nguồn với cùng plugin ID nhưng implementation khác gây khó chẩn đoán.

## 34. Kotlin DSL precompiled plugin và package declaration

Một plugin filename không package ở `src/main/kotlin/org.example.java-library.gradle.kts` có ID `org.example.java-library`. Nếu muốn tổ chức plugins bằng package declaration hoặc nested namespace, phải tuân theo naming rules của Gradle; không tự suy plugin ID đơn giản từ folder.

Những lỗi thường gặp:
- File tạo ở `build-logic/src/main/java` nhưng nội dung `*.gradle.kts`, không thuộc source set precompiled scripts mong đợi.
- File tên `java-library.gradle.kts` nhưng consumer dùng `id("org.example.java-library")`.
- Filename thêm `.txt`, case mismatch hoặc dùng dấu gạch dưới không khớp.
- Kotlin DSL code có imports/classpath chưa chuẩn trong build-logic.
- Plugin được tạo trong main project thay vì plugin build.
- `pluginManagement.includeBuild` đặt sai/không được đọc.
- Added external plugin nhưng quên implementation classpath trong build-logic.

**Cách debug:** đọc compile error từ `build-logic` và so filesystem path, plugin ID, plugin build setup, version catalog scope, repositories. Đừng sửa bằng cách copy plugin configuration trở lại mọi module rồi đánh mất kiến trúc.

## 35. Cách mở rộng convention thành typed binary plugin khi cần

Khi convention chỉ áp Java/JUnit/toolchain và vài tasks, precompiled Kotlin DSL plugin thường đủ. Khi cần complex extension object, nhiều custom task types, Worker API, BuildService, output Provider wiring hoặc kiểm thử plugin logic chi tiết, có thể dùng **binary plugin**:

~~~kotlin
// Khung ý tưởng, KHÔNG phải file runnable độc lập:
class MyCompanyJavaPlugin : Plugin<Project> {
    override fun apply(target: Project) {
        target.pluginManager.apply("java")
        // Configure typed extensions/tasks with Gradle APIs.
    }
}
~~~

Một binary plugin thực sự cần Gradle plugin build setup, imports, registered plugin ID/implementation class, tests. Không trộn snippet này vào demo precompiled scripts như thể nó thay thế được ba file đã tạo; đây là hướng nâng cấp kiến trúc khi logic phức tạp.

### 35.1. Tránh Java/Kotlin code gọi Project ở task execution

Nếu viết custom task type trong binary plugin, dùng `@Input`/`@OutputFile`/`Property`/`RegularFileProperty` và `TaskAction`. Đừng truy cập project model không an toàn từ task actions khi cần Configuration Cache. Convention plugin nên cấu hình tasks, không để tasks tự dò project state lúc chạy.

## 36. Testing convention plugin: kiểm cái gì?

Không chỉ test Java business code. Với một convention plugin, cần kiểm **hành vi Gradle**:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Plugin ID hợp lệ | `:catalog` resolve `org.example.java-library` |
| Java toolchain | JavaCompile chọn Java 17 |
| Compiler encoding | `UTF-8` |
| Bytecode target | `options.release` là 17 |
| Test engine | JUnit Jupiter tests được discover/run |
| Test dependencies | Jupiter/Launcher có trên test classpath |
| Module type | Libraries có `api`/`implementation`; app có `run` |
| Project dependencies | `:checkout` thấy `:catalog`; `:app` thấy `:checkout` |
| Entry point | `:app:run` in đúng receipt |
| Scope isolation | `:catalog` không có application distribution tasks |
| Plugin code reuse | Không cấu hình JDK/JUnit lặp ở modules |
| Configuration Cache | Lượt 2 không có compatibility errors |
| Build Cache | Task outputs đúng khi tăng/giảm cache |
| CI | Linux/JDK 17 và runner policy hợp lệ |

### 36.1. Gradle TestKit cho plugin logic

Nếu phát triển convention trong build-logic lâu dài, **Gradle TestKit** cho phép tạo test Gradle project tạm, áp plugin ID rồi chạy tasks/assert outcomes. TestKit `GradleRunner.withGradleVersion("9.9.0")` có thể test cùng plugin trên target Gradle version phù hợp; plugin-under-test classpath phải được setup qua plugin test mechanisms.

Đây là **mẫu chiến lược**, không một đoạn Java class chưa có imports/fixtures rồi gọi runnable. TestKit đặc biệt quan trọng khi nâng Gradle major, refactor plugin API hoặc publish binary plugin cho các repos khác.

### 36.2. Manual smoke test phù hợp demo

Từ root:

~~~bash
./gradlew :catalog:tasks
./gradlew :checkout:dependencies --configuration runtimeClasspath
./gradlew :app:tasks
./gradlew allChecks --warning-mode=all
./gradlew :app:run --args="BK-202 3" --quiet
~~~

Quan sát:
- `:catalog:tasks` có Java library tasks.
- `:app:tasks` có `run` và application distribution tasks.
- Dependency report ở checkout có project `:catalog` trong runtime graph.
- `allChecks` kiểm cả ba modules.
- `:app:run` in `Receipt: Gradle Notes x3`.

Đừng chốt toàn bộ Gradle console stdout vì thứ tự/tên tasks/cache outcome khác phiên bản và trạng thái filesystem.

## 37. Tránh hard-code project paths trong conventions chung

Không viết trong `org.example.java-common`:

~~~kotlin
// KHÔNG làm trong convention chung của mọi module:
dependencies {
    implementation(project(":catalog"))
}
~~~

Vì `:catalog` mà tự áp common plugin sẽ phụ thuộc chính nó hoặc ép mọi module phụ thuộc catalog, tạo coupling không mong muốn. Common convention chỉ chứa **hành vi cross-cutting**; project dependencies nghiệp vụ thuộc nơi sử dụng (`checkout`/`app`) hoặc module-specific architecture plugin có hợp đồng rất rõ.

Nếu có một platform/BOM nội bộ thực sự được mọi Java module dùng, có thể áp common constraint phù hợp, nhưng không biến mọi module dependency thành global mặc định.

## 38. Không dùng chung output directory giữa các modules

Một anti-pattern khác:

~~~kotlin
// Anti-pattern: tất cả subprojects cùng ghi một output.
layout.buildDirectory.set(rootProject.layout.buildDirectory)
~~~

Nếu các modules cùng ghi `classes/java/main` hoặc reports trong một directory chung, có nguy cơ collisions, cache invalidation sai và flaky builds. Gradle đã đặt output riêng theo project build directory. Không sửa build directory để “gom build outputs” nếu chưa có design sở hữu đường dẫn rõ.

Nếu muốn một folder tổng hợp artifacts cho CI, nên tạo task `Sync`/`Copy` ở root có declared inputs từ producer tasks (hoặc dùng distribution/report aggregation plugins), không cho mỗi module tự ghi vào cùng path ngoài build root.

## 39. Repository, credentials và plugin code là ranh giới tin cậy

Included `build-logic` chứa **executable Gradle plugin code**. Khi một Pull Request sửa convention plugin, nó có thể chạy ngay ở configuration time của mọi module áp dụng.

Bảo vệ:

1. Review build-logic scripts và Wrapper như production code.
2. Dùng repository URLs HTTPS/mirror tin cậy.
3. Pin plugin/dependency versions trong các builds, không sử dụng dynamic versions tùy tiện.
4. Dùng dependency verification/checksum và supply-chain scan theo policy.
5. Không cấp publish/deploy/secrets cho untrusted PR runner.
6. Không log repository password hoặc env secrets từ convention plugin.
7. Tách publishing/signing convention khỏi common Java convention.
8. Bảo đảm included build repositories cũng theo corporate policy.
9. Dùng CODEOWNERS/review khi thay toolchain/quality gates cho nhiều modules.
10. Không tự load remote script/JAR chỉ để có một “configuration helper”.

**Không nghĩ vì plugin nằm trong repo nên luôn trusted**: mã PR chưa review vẫn có thể thay nó. Run PR builds trong isolated runner không có release credentials.

## 40. CI mẫu cho hệ thống nhiều module

Ví dụ GitHub Actions `.github/workflows/java-checks.yml`:

~~~yaml
name: Java modules verification

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  checks:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Install JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Setup Gradle and validate Wrapper
        uses: gradle/actions/setup-gradle@v4
        with:
          cache-read-only: true

      - name: Inspect Gradle runtime
        run: ./gradlew --version

      - name: Run all module checks
        run: ./gradlew allChecks --warning-mode=all --stacktrace

      - name: Smoke run application
        run: ./gradlew :app:run --args="BK-202 3" --quiet
~~~

**Lưu ý:** các action version tags là mẫu; production workflow nên pin reviewed immutable commit SHAs theo security policy. GitHub Actions `GITHUB_TOKEN` được giới hạn `contents: read`; workflow không cấp signing/publishing secrets cho untrusted PR code. CI thật cần kiểm policy lưu test reports/artifacts, license/secret/network access và runner quotas.

### 40.1. Tại sao không chỉ chạy :app:build?

Gradle sẽ build project dependencies cần cho `:app`, nhưng nó không nhất thiết chạy **mọi unit test** ở những library modules, tùy task graph. Root `allChecks` tổng hợp `:catalog:check`, `:checkout:check` và `:app:check` để có quality gate rõ. Đừng coi `:app:run` thành đủ để chứng minh toàn bộ modules test PASS.

### 40.2. Linux và Windows

JDK/canonical encoding/classpath của Java source có thể nhất quán, nhưng CI scripts có khác biệt shell, filesystem paths/case sensitivity, process semantics. Khi sản phẩm hỗ trợ Windows, thêm một job Windows thực thay vì giả định Linux pass thì Windows chắc chắn pass.

## 41. Tình huống refactor từ build.gradle.kts copy-paste

**Trước refactor**, hai library modules đều chứa:

~~~kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.test {
    useJUnitPlatform()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}
~~~

**Sau refactor**, mỗi library còn:

~~~kotlin
plugins {
    id("org.example.java-library")
}
~~~

Còn những dependencies **chỉ dành cho module đó** vẫn ở module:

~~~kotlin
dependencies {
    implementation(project(":catalog"))
}
~~~

**Phương pháp migration:**
1. Chọn một library đơn giản làm pilot.
2. Viết common/library conventions.
3. Áp plugin cho pilot, bỏ cấu hình bị trùng.
4. Chạy tests và so bytecode/toolchain/dependency graph.
5. Tiếp tục chuyển từng module.
6. Tạo application convention riêng, không dùng library convention cho app.
7. Dọn root `subprojects { }` sau khi module owners hoàn tất.
8. Chạy allChecks và CI fresh build.
9. Review kết quả/rollback nếu plugin ID hoặc classpath lỗi.

Tránh chuyển hết 30 modules và đổi major Gradle/dependency versions cùng một commit; nếu lỗi, khó cô lập nguyên nhân.

## 42. Đổi Java version cho mọi modules có cần sửa nhiều file?

Trong demo, quy ước Java nằm trong `org.example.java-common.gradle.kts`:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Muốn chuyển một product sang Java 21 phải:
- Xác minh Gradle version hỗ trợ Java 21 để compile và JVM chạy Gradle riêng.
- Xác định consumer/runtime bytecode requirement và dependencies/plugin compatibility.
- Cập nhật `languageVersion` và `options.release` theo target product, không chỉ một dòng.
- Chạy allChecks/integration/CI across supported JDKs.
- Kiểm bytecode/module API và artifacts.

Một thay đổi common convention ảnh hưởng tất cả modules áp nó — là **lợi ích centralization** nhưng cũng là **blast radius** cần review. Nếu một module cần Java 17 và một module cần Java 21, đừng ép cả hai bằng một rule cứng; thiết kế variants/conventions hoặc typed extension có contract rõ.

## 43. Những lỗi thường gặp khi triển khai

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `Plugin with id 'org.example.java-library' not found` | Không include build-logic trong pluginManagement, sai plugin ID/filename | Kiểm root settings và plugin source path |
| `Unresolved reference: kotlin-dsl` | Plugin build cấu hình sai hoặc repository/plugin resolution không phù hợp | Kiểm `build-logic/build.gradle.kts`/settings |
| Không có accessor `testImplementation` | Không apply Java plugin trong đúng precompiled script, scope sai | Kiểm `plugins { java }` và script target |
| `Unresolved reference: libs` trong build-logic | Catalog của root không tự có trong included build | Import catalog ở build-logic settings hoặc dùng policy khác |
| `alias(libs.plugins...)` không compile trong precompiled plugin | Catalog plugin alias accessor không hỗ trợ ở đó | Build-logic implementation dependency + `id` không version |
| `:checkout:compileJava` không tìm thấy `Catalog` | Thiếu `implementation(project(":catalog"))` | Khai báo project dependency |
| App báo `Could not find or load main class` | Sai package/class `mainClass` hoặc compile/runtime classpath | `demo.app.Main` và app plugin |
| JUnit tests không tìm thấy | Chưa áp common convention hoặc JUnit engine thiếu | `useJUnitPlatform()` + test deps |
| `No matching toolchains found` | JDK 17 chưa cài hoặc resolver chưa cấu hình | Cài/provision JDK 17 |
| `Unsupported class file major version` | Gradle/plugin/JDK runtime/bytecode mismatch | Kiểm Daemon JVM, toolchain, target |
| Duplicate class/task errors | Convention plugin chồng classpath/đăng ký task cùng tên | Tách plugin ownership, dùng lazy registration |
| Two modules ghi cùng build dir | Overlapping outputs | Tách output ownership |
| `--parallel` tạo flaky tests | Shared DB/ports/temp dirs | Test isolation hoặc giới hạn resource |
| Plugin build thay đổi làm mọi modules invalidated | Một included build chứa mọi convention có shared classpath | Tách build-logic subprojects khi hợp lý |
| Root tests PASS nhưng library tests không chạy | Chỉ gọi `:app:test` hoặc thiếu aggregate | `allChecks` |
| `:app:run` báo lỗi `args` | Sai cách truyền CLI/quantity | `--args="BK-202 3"` |
| Internal Maven repo không resolve trong build-logic | Included build có settings riêng | Cấu hình repo/credentials tại đúng build |
| Plugin ngoài báo class not found | Chưa add artifact vào implementation classpath build-logic | Theo precompiled plugin docs |
| Plugin config đọc Project ở task execution | Configuration Cache incompatibility | Provider-based task inputs/outputs |
| Gradle sync IDE fail | Wrapper/plugin/JVM hoặc classpath mismatch | Kiểm --version, IDE support matrix |
| Gradle builds chậm hơn sau refactor | Compilation/config cache invalidations hoặc classpath tăng | Profile, tách plugins hoặc giảm dependency |

### 43.1. Quy trình debug có thứ tự

1. Kiểm `./gradlew --version` và JDK thực.
2. Kiểm root `settings.gradle.kts` có `pluginManagement.includeBuild("build-logic")`.
3. Kiểm `build-logic/settings.gradle.kts` và `build-logic/build.gradle.kts`.
4. Kiểm filenames/IDs của ba precompiled scripts.
5. Chạy `./gradlew :catalog:tasks --stacktrace` để cô lập plugin application.
6. Chạy `./gradlew :checkout:dependencies --configuration runtimeClasspath`.
7. Chạy Java direct `javac/java` để tách lỗi source khỏi Gradle build.
8. Kiểm Test reports và JUnit engine nếu test 0/NO-SOURCE.
9. Chạy allChecks và Configuration Cache diagnostics.
10. Đánh giá CI permissions/caches/runner trước khi merge.

## 44. Các anti-patterns cần tránh

**A — Tạo một global root `subprojects { }` cho mọi module.** Che khuất logic và tạo cross-project coupling.

**B — Áp `application` cho tất cả libraries.** Làm lẫn module roles.

**C — Copy test config vào mỗi `build.gradle.kts`.** Configuration drift sau vài lần update.

**D — Convention tự thêm dependencies nghiệp vụ như `project(":catalog")` vào mọi module.** Ép coupling và có thể tạo self dependency.

**E — Dùng một build output directory chung.** Overlapping outputs phá correctness/cache.

**F — Nghĩ included build tự kế thừa mọi repository/catalog của root.** Mỗi build có settings riêng.

**G — Đặt version ở `plugins` block của precompiled script để áp external plugin.** Không đúng contract; dùng build-logic implementation classpath.

**H — Publish local convention plugin lên Plugin Portal chỉ để dùng trong cùng repo.** Không cần; pluginManagement.includeBuild đủ.

**I — Tự thêm JDK/toolchain download không có policy.** Version/provisioning cần quản lý.

**J — Dùng `afterEvaluate` để chữa mọi unresolved plugin order.** Cần public lazy Gradle APIs.

**K — Chạy only `:app:build` rồi coi library tests đã chạy đủ.** Dùng aggregate quality gate/check riêng.

**L — Dùng `maxParallelForks` lớn cho mọi modules.** Có thể gây memory contention/flaky integration tests.

**M — Hardcode Gradle Wrapper JAR giả hoặc không kiểm source.** Wrapper là executable code cần integrity.

**N — Mặc định `build-logic` nhanh hơn `buildSrc` trong mọi trường hợp.** Cần đo và xem graph/classpath.

**O — Nâng Gradle major và đổi conventions/dependencies cùng lúc không có tests.** Khó isolate regressions.

**P — Dùng `api` cho mọi project dependencies.** Làm rò rỉ implementation types và mở compile classpath.

**Q — Plugin common tự publish artifacts với secrets trong PR builds.** Tách release stage, least privilege.

**R — Không xác minh output Java vì build reports SUCCESSFUL.** Kiểm Main stdout/units/integration.

## 45. Bài tập có đáp án

**Câu 1.** `include(":catalog")` tạo gì?  
**Đáp án:** một subproject thuộc main build, path `:catalog`.

**Câu 2.** `pluginManagement.includeBuild("build-logic")` làm gì?  
**Đáp án:** cho plugin resolution trong main build tìm plugin implementations từ included build-logic.

**Câu 3.** `build-logic` là subproject `:build-logic` mặc định không?  
**Đáp án:** không; nó là included build riêng khi dùng `includeBuild`.

**Câu 4.** Convention plugin khác project dependency như thế nào?  
**Đáp án:** convention cấu hình build behavior, project dependency kết nối artifacts/classpath giữa modules.

**Câu 5.** File `org.example.java-library.gradle.kts` không package tạo plugin ID nào?  
**Đáp án:** `org.example.java-library`.

**Câu 6.** `kotlin-dsl` đặt ở module Java app hay plugin build?  
**Đáp án:** ở `build-logic/build.gradle.kts` để compile Kotlin DSL plugin sources.

**Câu 7.** `:catalog` nên áp plugin nào?  
**Đáp án:** `org.example.java-library`.

**Câu 8.** `:app` nên áp plugin nào?  
**Đáp án:** `org.example.java-application`.

**Câu 9.** `:checkout` dùng `Catalog` trong implementation, không lộ types ở public API; dùng `api` hay `implementation`?  
**Đáp án:** `implementation(project(":catalog"))`.

**Câu 10.** Plugin library áp common plugin có tự tạo dependency tới app không?  
**Đáp án:** không.

**Câu 11.** JDK dùng compile Java được chọn ở đâu?  
**Đáp án:** `java.toolchain.languageVersion` trong common convention.

**Câu 12.** `options.release.set(17)` có nghĩa Gradle Daemon tự chạy Java 17 không?  
**Đáp án:** không; nó ràng buộc Java compiler target.

**Câu 13.** JUnit dependencies được khai báo ở đâu trong demo?  
**Đáp án:** `org.example.java-common.gradle.kts`.

**Câu 14.** Chạy `./gradlew :app:run --quiet` in gì?  
**Đáp án:** `Receipt: Java Handbook x2`.

**Câu 15.** Truyền `--args="BK-202 3"` in gì?  
**Đáp án:** `Receipt: Gradle Notes x3`.

**Câu 16.** Chạy `javac/java` trực tiếp có compile build-logic không?  
**Đáp án:** không; chỉ Java application modules.

**Câu 17.** Vì sao `checkout` cần compile classpath catalog khi dùng javac?  
**Đáp án:** `CheckoutService` import `demo.catalog.Catalog`.

**Câu 18.** Vì sao `app` runtime classpath cần cả catalog và checkout?  
**Đáp án:** CheckoutService gọi Catalog ở runtime.

**Câu 19.** `buildSrc` có được tự động nhận diện không?  
**Đáp án:** có, khác included build-logic phải include.

**Câu 20.** Trong repo lớn, cách Gradle khuyến nghị để tách build logic thường là gì?  
**Đáp án:** included `build-logic` composite build với convention plugins.

**Câu 21.** `subprojects { }` có thể gây vấn đề gì?  
**Đáp án:** cấu hình chéo/hidden coupling, làm khó isolated/parallel configuration.

**Câu 22.** Version catalog của root tự xuất hiện trong build-logic không?  
**Đáp án:** không, cần import/configure riêng.

**Câu 23.** Precompiled script plugin có nên dùng `alias(libs.plugins.external)` trực tiếp không?  
**Đáp án:** không dựa vào generated catalog plugin accessors ở đây; dùng external plugin implementation dependency và id không version.

**Câu 24.** Nếu plugin ngoài cần version, đặt nó ở đâu?  
**Đáp án:** implementation dependency của `build-logic` plugin project theo Gradle plugin docs.

**Câu 25.** `allChecks` có ý nghĩa gì?  
**Đáp án:** aggregate `check` tasks của cả ba modules.

**Câu 26.** `:app:run` có đảm bảo chạy tất cả library unit tests không?  
**Đáp án:** không; cần quality gate riêng.

**Câu 27.** Hai modules cùng ghi `build/generated/config.json` có an toàn không?  
**Đáp án:** không, phải sửa output ownership.

**Câu 28.** Vì sao compiler options nên đặt vào `withType<JavaCompile>().configureEach`?  
**Đáp án:** cấu hình lazy các tasks phù hợp, không phụ thuộc thứ tự đăng ký.

**Câu 29.** Một module cần JDK 21 khác JDK 17 common, xử lý?  
**Đáp án:** thiết kế ngoại lệ/typed extension hoặc convention riêng có policy, không ép sai target toàn repo.

**Câu 30.** Convention plugin có tự ràng buộc third-party dependency graph không?  
**Đáp án:** chỉ trong phạm vi dependencies/constraints mà nó khai báo; project modules vẫn có responsibilities riêng.

**Câu 31.** `FAIL_ON_PROJECT_REPOS` main build có tự áp lên included build-logic không?  
**Đáp án:** không; included build có settings policy riêng.

**Câu 32.** Nếu Gradle báo plugin ID not found, kiểm thứ gì đầu tiên?  
**Đáp án:** pluginManagement.includeBuild, source filename/ID, build-logic setup và plugin repositories.

**Câu 33.** `java-library` khác `java` ở điểm phụ thuộc nào?  
**Đáp án:** cung cấp API/implementation separation cho library consumers.

**Câu 34.** Khi chuyển từ copy-paste sang conventions, nên bắt đầu từ đâu?  
**Đáp án:** một module pilot, tests/outputs đối chiếu, rồi rollout từng loại module.

**Câu 35.** `build-logic` có thể ảnh hưởng Configuration Cache không?  
**Đáp án:** có; đây là build logic executable, phải tuân thủ API/configuration constraints.

**Câu 36.** Plugin source được PR sửa thì có thể chạy trên CI chưa?  
**Đáp án:** có khi PR Gradle build được thực thi; cần low-privilege isolated CI.

**Câu 37.** Một plugin dùng trong nhiều repos cần giải pháp gì?  
**Đáp án:** cân nhắc published/versioned binary plugin và compatibility tests.

**Câu 38.** Muốn kiểm plugin trên nhiều Gradle versions, dùng công cụ nào?  
**Đáp án:** Gradle TestKit/GradleRunner với target distributions đã hỗ trợ.

**Câu 39.** Root project không chứa Java sources có nhất thiết áp Java plugin không?  
**Đáp án:** không; root có thể chỉ áp base và aggregate tasks.

**Câu 40.** Tại sao phụ thuộc vào file JAR bằng path không tốt bằng project dependency?  
**Đáp án:** Gradle mất implicit artifact producer relationship/variant-aware resolution rõ ràng.

## 46. Checklist thực hiện dự án multi-module

- [ ] Root `settings.gradle.kts` khai báo đủ module paths?
- [ ] Included build `build-logic` được đăng ký trong `pluginManagement`?
- [ ] `build-logic` có `settings.gradle.kts` riêng?
- [ ] `build-logic/build.gradle.kts` áp `kotlin-dsl`?
- [ ] Precompiled scripts ở `src/main/kotlin`, filenames/IDs đúng?
- [ ] Common convention có Java toolchain/encoding/release đúng?
- [ ] Test convention có JUnit/Launcher và `useJUnitPlatform()`?
- [ ] Library convention áp `java-library` và common?
- [ ] Application convention áp `application` và common?
- [ ] Module files chỉ chứa module-specific dependencies/entry points?
- [ ] `:catalog` không phụ thuộc `:checkout` hoặc `:app`?
- [ ] `:checkout` dùng `implementation(project(":catalog"))`?
- [ ] `:app` dùng `implementation(project(":checkout"))`?
- [ ] Public API exposures được xem xét trước khi dùng `api`?
- [ ] Mỗi module có output directory riêng?
- [ ] Không còn cấu hình chéo `subprojects { }` trùng conventions?
- [ ] Repositories của root và included build đều có policy?
- [ ] Version catalog có được cấu hình đúng build scope nếu dùng?
- [ ] Không dùng plugin alias/version sai trong precompiled script?
- [ ] External plugin classpath được khai báo tại build-logic nếu cần?
- [ ] Không hardcode module business dependencies ở common convention?
- [ ] `./gradlew :app:run` in đúng expected receipt?
- [ ] `./gradlew allChecks` chạy unit tests các modules?
- [ ] Java direct `javac/java` chạy được trên JDK 17?
- [ ] IDE sync nhận đúng module graph và code completion?
- [ ] Configuration Cache/incremental/caching diagnostics không có lỗi?
- [ ] Parallel tasks không đụng shared DB/ports/outputs?
- [ ] CI có read-only PR permissions, JDK17/Wrapper validation?
- [ ] Included build-logic changes được review như executable code?
- [ ] Có regression tests cho convention/plugin khi đổi Gradle version?
- [ ] Không hứa performance gains khi chưa benchmark?
- [ ] Có migration plan nếu chuyển từ `buildSrc` hoặc root script?
- [ ] Có ownership cho common conventions và module-specific exceptions?

## 47. Tài liệu chính thức

- [Gradle — Convention Plugins](https://docs.gradle.org/9.9.0/userguide/implementing_gradle_plugins_convention.html): khái niệm, lý do và cách tạo.
- [Gradle — Precompiled Script Plugins](https://docs.gradle.org/9.9.0/userguide/implementing_gradle_plugins_precompiled.html): plugin ID, source layout, plugin classpath, application.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/9.9.0/userguide/best_practices_structuring_builds.html): ưu tiên composite `build-logic` và convention plugins thay cross-project configuration.
- [Gradle — Sharing Build Logic Between Subprojects](https://docs.gradle.org/9.9.0/userguide/sharing_build_logic_between_subprojects.html): `buildSrc`, included build và cross-project concerns.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/9.9.0/userguide/multi_project_builds.html): module topology/paths/dependencies.
- [Gradle — Composite Builds](https://docs.gradle.org/9.9.0/userguide/composite_builds.html): included build semantics và plugin resolution.
- [Gradle — Organizing Projects](https://docs.gradle.org/9.9.0/userguide/organizing_build_logic.html): build logic structure.
- [Gradle — Java Library Plugin](https://docs.gradle.org/9.9.0/userguide/java_library_plugin.html): `api`/`implementation` và compile avoidance.
- [Gradle — Application Plugin](https://docs.gradle.org/9.9.0/userguide/application_plugin.html): `mainClass`, `run`, distributions.
- [Gradle — Java Toolchains](https://docs.gradle.org/9.9.0/userguide/toolchains.html): JDK17 compile/test khác Daemon runtime.
- [Gradle — Testing JVM Projects](https://docs.gradle.org/9.9.0/userguide/java_testing.html): Test tasks, JUnit Platform/reports.
- [Gradle — Version Catalogs](https://docs.gradle.org/9.9.0/userguide/version_catalogs.html): catalogs trong included builds và plugin accessor limits.
- [Gradle — Dependency Management](https://docs.gradle.org/9.9.0/userguide/dependency_management.html): module/project dependency resolution.
- [Gradle — Configuration Cache](https://docs.gradle.org/9.9.0/userguide/configuration_cache.html): constraints cho build logic/task execution.
- [Gradle — Build Cache](https://docs.gradle.org/9.9.0/userguide/build_cache.html): caching đúng inputs/outputs.
- [Gradle — Gradle TestKit](https://docs.gradle.org/9.9.0/userguide/test_kit.html): functional testing plugins trên nhiều distributions.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/9.9.0/userguide/gradle_wrapper.html): Wrapper files và scripts.
- [Gradle — Best Practices Security](https://docs.gradle.org/9.9.0/userguide/best_practices_security.html): plugin source trust, Wrapper/repository verification.

**Kết luận:** Convention Plugin giúp tổ chức **những quy ước build được tái sử dụng** theo loại module, còn module `build.gradle.kts` tập trung vào **trách nhiệm nghiệp vụ và project dependencies**. Với Java multi-module, một included `build-logic` chứa precompiled Kotlin DSL plugins `java-common`, `java-library` và `java-application` là cấu trúc đủ rõ để tránh copy-paste và root `subprojects { }` coupling. Root settings quản lý topology/plugin resolution, included build quản lý plugin implementations, từng module quản lý dependencies của nó. Hãy xác minh đầy đủ **plugin IDs, JVM/toolchains, JUnit, dependency graph, Java stdout, CI/security, caching và tests** — sự nhất quán quan trọng hơn số lượng module hoặc số dòng configuration được rút gọn.