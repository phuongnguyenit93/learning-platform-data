# So sánh buildSrc, build-logic và plugin đã công bố trong Gradle

Khi một repository có nhiều Gradle subprojects, bạn thường cần dùng chung các quy ước: phiên bản Java, compiler flags, cách chạy tests, publishing policy, static analysis, nguồn dependency, hoặc các tasks riêng của công ty. Viết lại những cấu hình đó trong từng `build.gradle.kts` dễ gây lệch chuẩn; dùng `allprojects { ... }` để “cấu hình hộ” mọi project lại có thể tạo coupling, phá ranh giới project và làm khó configuration caching.

Gradle có ba hướng tổ chức thường được đem ra so sánh:

1. **`buildSrc`**: một build đặc biệt được Gradle tự phát hiện, tự build và đưa các classes/plugin từ nó vào classpath của main build.
2. **`build-logic`**: tên quy ước cho một **included build** chứa convention/binary plugins được main build khai báo qua `includeBuild` hoặc `pluginManagement { includeBuild(...) }`.
3. **Plugin đã công bố (published plugin)**: plugin được đóng gói và upload vào Gradle Plugin Portal hoặc Maven-compatible repository, rồi consumers áp dụng theo **plugin ID + version + repository**.

Cần làm rõ ngay: **“plugin đã công bố” không đồng nghĩa với “binary plugin”; “convention plugin” không đồng nghĩa với “buildSrc”.** Đây là hai chiều phân loại khác nhau:

- **Cách triển khai**: precompiled script plugin `*.gradle.kts`, binary plugin Java/Kotlin/Groovy triển khai `Plugin<Project>`, hoặc script plugin legacy.
- **Cách phân phối**: nằm trong `buildSrc`, trong included build `build-logic`, hoặc được publish thành versioned plugin artifact.

Cùng một convention plugin có thể bắt đầu trong `buildSrc`, chuyển sang `build-logic` và sau đó được đóng gói để chia sẻ giữa nhiều repositories. Bài này thuộc phần **Build logic dùng chung** của *Build Tool Gradle*: trình bày cơ chế, tiêu chí lựa chọn, ví dụ **Java 17 + Gradle Kotlin DSL**, cách publish/apply plugin thật, migration, hiệu năng, bảo mật, testing và chẩn đoán lỗi.

## 1. Vì sao cần tách build logic?

Giả sử có ba subprojects:

~~~text
company-app/
├── settings.gradle.kts
├── api/build.gradle.kts
├── domain/build.gradle.kts
└── storage/build.gradle.kts
~~~

Nếu cả ba đều phải sử dụng Java 17 và UTF-8, cách viết lặp:

~~~kotlin
// Mỗi build.gradle.kts đều có cùng đoạn này:
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

có thể hoạt động, nhưng khi công ty đổi version/toolchain hoặc bổ sung linter, phải tìm/sửa từng nơi. Nếu một project quên đổi, kết quả build khác nhau.

Một **convention plugin** cho phép consumers chỉ ghi:

~~~kotlin
plugins {
    id("java-library-conventions")
}
~~~

và đặt cấu hình Java 17/UTF-8 trong đúng một chỗ. Đây là **ý định** của build logic: tái sử dụng chính sách cấu hình, không phải tái sử dụng mã nghiệp vụ Java đang phát hành cho ứng dụng.

### Build logic khác application code

| Mã nguồn | Được chạy lúc nào? | Phụ thuộc vào API nào? |
| --- | --- | --- |
| `src/main/java` của ứng dụng | Khi compile/test/run ứng dụng | JDK + runtime libraries |
| `build.gradle.kts` | Gradle configuration phase | Gradle DSL + plugin APIs |
| Plugin trong `buildSrc` | Được build trước rồi áp dụng khi Gradle cấu hình | Gradle API/Kotlin DSL/plugin dependencies |
| Plugin trong `build-logic` | Được Gradle resolve/build thông qua included build | Gradle plugin APIs, independent build graph |
| Published Gradle plugin JAR | Được resolve theo ID/version và thực thi trong build | Gradle API + plugin implementation dependencies |

**Java toolchain để compile ứng dụng** không tự đồng nghĩa với JDK dùng chạy Gradle hay JDK dùng compile plugin; kiểm soát các ranh giới đó khi nâng Gradle/JDK.

## 2. Bảng so sánh nhanh

| Tiêu chí | `buildSrc` | Included build `build-logic` | Published plugin |
| --- | --- | --- | --- |
| Cách khai báo | Thư mục `buildSrc` đặc biệt ở build root | `includeBuild("build-logic")` hoặc `pluginManagement { includeBuild("build-logic") }` | `plugins { id("...") version "..." }` |
| Có build độc lập? | Gradle quản lý như một build riêng đặc biệt | Có settings/dependencies/tasks của included build | Plugin producer là build độc lập; consumer dùng artifact phiên bản |
| Có cần publish trước khi main build dùng? | Không | Không | Có, trừ khi phát triển bằng included-build substitution |
| Discovery | **Tự động** | **Tường minh** trong settings | Plugin repositories + marker/resolution strategy |
| Phạm vi thường dùng | Một main build và các subprojects của nó | Một workspace/monorepo, nhiều builds liên kết | Nhiều repositories/teams/sản phẩm độc lập |
| Classpath | Build logic được thêm vào classpath của main build rộng rãi | Plugin artifacts được resolve từ included build | Plugin artifacts được resolve từ repository và cache |
| Đổi logic | Có thể ảnh hưởng/invalidate phần lớn build configuration | Có thể cô lập ảnh hưởng tốt hơn theo project/plugin | Consumer dùng version cũ cho đến khi nâng hoặc đổi resolution |
| Versioning độc lập | Thường gắn cùng source revision của main build | Thường gắn cùng workspace revision | SemVer/release metadata rõ, consumers có thể pin version |
| Quản lý secrets để publish | Không cần | Không cần | Có thể cần publish credentials và signing/approval |
| Độ phức tạp ban đầu | Thấp | Trung bình | Cao hơn |
| Phù hợp | Prototype, build nhỏ, helpers nội bộ | **Khuyến nghị mặc định** cho shared logic trong build lớn | Plugin ổn định dùng chung nhiều builds/repos |

Theo [Gradle Best Practices](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html), đội ngũ thường nên ưu tiên **included build cho build logic** thay vì tích lũy mọi thứ trong `buildSrc`: ranh giới rõ hơn và có thể giảm phạm vi invalidation khi thay đổi. Tuy nhiên đây **không phải kết luận “buildSrc luôn sai”**: build nhỏ vẫn có thể dùng nó hợp lý.

## 3. Định nghĩa chuẩn: convention, precompiled script, binary, published

### Convention plugin là **vai trò**

Một convention plugin áp dụng cấu hình mặc định của tổ chức: apply `java-library`, đặt Java toolchain, compiler flags, test policy, publishing conventions… Nó **có thể được viết bằng script hoặc class**.

### Precompiled script plugin là **cách triển khai**

File:

~~~text
src/main/kotlin/java-library-conventions.gradle.kts
~~~

được Gradle biên dịch thành plugin và gán plugin ID từ tên file: `java-library-conventions`. Bạn không cần viết một class `implements Plugin<Project>`. Nó có thể nằm trong `buildSrc` hoặc `build-logic`; nếu được cấu hình publication đầy đủ, plugin đó cũng có thể được **publish**.

### Binary plugin là **cách triển khai khác**

Một class Java/Kotlin/Groovy triển khai plugin API:

~~~java
package demo.build;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class MyPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getPluginManager().apply("java-library");
    }
}
~~~

Đây là **mảnh class hoàn chỉnh**, nhưng để Gradle sử dụng bằng plugin ID cần thêm plugin declaration/descriptor qua `java-gradle-plugin` hoặc cơ chế đóng gói tương đương. Binary plugin có thể nằm **ngay trong build-logic**, chưa cần public release.

### Published plugin là **cách phân phối**

Một published plugin được đưa lên repository, có version và plugin marker phù hợp để consumers resolve qua `plugins { ... }`. Published plugin có thể là **binary plugin** hoặc **precompiled script plugin** được đóng gói thành artifact.

Bởi vậy **không hỏi “nên dùng precompiled hay build-logic?”** như thể là hai lựa chọn loại trừ: cách thường dùng là **precompiled convention plugin trong included build tên build-logic**.

## 4. Cơ chế `buildSrc` hoạt động

Nếu root build có thư mục đặc biệt:

~~~text
my-project/
├── settings.gradle.kts
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/kotlin/...
└── app/build.gradle.kts
~~~

Gradle tự nhận `buildSrc`, build code trong đó và đưa outputs vào classpath dùng cho build scripts của main build. Không cần `include("buildSrc")` hoặc `includeBuild("buildSrc")` trong settings.

Những gì có thể đặt trong `buildSrc`:

- Kotlin/Java/Groovy helpers cho build scripts.
- Custom task classes.
- Precompiled script convention plugins.
- Binary plugins và plugin implementation dependencies.
- Extensions giúp config chung.

Vấn đề lớn ở repository nhiều projects là **classpath/invalidation scope**: do `buildSrc` tự động nằm trên classpath chung của build, thay đổi ở đây có thể khiến **nhiều hoặc toàn bộ build scripts phải được cấu hình lại**, làm giảm lợi ích của incremental configuration/caching. Theo Gradle Best Practices, ảnh hưởng thường rộng hơn so với một included build có các subprojects/plugins được cô lập.

**Không khẳng định mỗi lần sửa `buildSrc` sẽ làm mọi JavaCompile task thực thi lại**. Việc build scripts cần được cập nhật không đồng nghĩa mọi task outputs tự động trở nên out-of-date. Hãy phân biệt **configuration invalidation**, **task up-to-date checks** và **build cache hits**.

## 5. Cơ chế included build `build-logic`

Một included build điển hình:

~~~text
my-project/
├── settings.gradle.kts
├── app/build.gradle.kts
└── build-logic/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/kotlin/java-library-conventions.gradle.kts
~~~

Main settings khai báo rõ:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "my-project"
include("app")
~~~

Khác `buildSrc`, thư mục này **không có tên đặc biệt về mặt Gradle**; bạn có thể đặt tên khác, để bên ngoài main project, hoặc chia thành nhiều included builds. Điều quan trọng là có **settings riêng** và được include tường minh.

### Vì sao cần `pluginManagement { includeBuild(...) }`?

Nếu build logic cung cấp plugin để các subprojects dùng trong `plugins { id("...") }`, khai báo included plugin build **sớm trong plugin-management scope** là cách rõ ràng để Gradle tìm plugin ID. Nó hữu ích đặc biệt khi cung cấp plugin cho settings hoặc plugin resolution ban đầu.

Một cấu hình khác đôi khi thấy trong Gradle docs:

~~~kotlin
includeBuild("build-logic")
~~~

Cũng là composite-build inclusion và có thể cung cấp plugin resolution/dependency substitution trong bối cảnh tương ứng. Tuy nhiên nếu mục đích chính là local plugin dùng trong `plugins` DSL, ví dụ học tập dưới đây chọn `pluginManagement { includeBuild(...) }` để làm rõ **plugin resolution**.

### Included build có môi trường cấu hình riêng

`build-logic` có:

- `settings.gradle.kts` riêng.
- `build.gradle.kts` riêng.
- `repositories` để resolve những thư viện/plugin dependencies mà bản thân build logic cần.
- Version Catalog riêng trừ khi import TOML từ nơi khác.
- Tasks để compile, test plugin và đóng gói outputs.

Không suy rằng main build `repositories { mavenCentral() }`, `libs.versions.toml`, `pluginManagement.repositories` hoặc `gradle.properties` đều được tự động “merge” sang included build. Gradle Composite Build có ranh giới isolation; những cấu hình đó cần đặt đúng scope.

## 6. Ví dụ chạy được: convention plugin trong `build-logic`, app Java 17

Ví dụ đầy đủ gồm main build có hai subprojects `:library` và `:app`. Build logic riêng cung cấp convention plugin `java-library-conventions`: áp dụng Java Library plugin, chọn Java 17 và UTF-8. `:library` áp dụng plugin này. `:app` dùng built-in Application plugin, phụ thuộc `project(":library")` và in một dòng. Không dùng third-party application dependencies.

### 6.1. Cây thư mục

~~~text
build-logic-demo/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── java-library-conventions.gradle.kts
├── library/
│   ├── build.gradle.kts
│   └── src/main/java/demo/library/Greeting.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
~~~

Để thực hành: dùng một Gradle Wrapper hợp lệ, Gradle tương thích JDK/toolchain Java 17, và Maven/plugin repositories có thể truy cập hoặc dependencies được cache. `kotlin-dsl` plugin có thể cần resolve compiler/tooling dependencies trong lần chạy đầu; vì vậy không coi ví dụ “offline tuyệt đối” nếu cache trống.

### 6.2. Main `settings.gradle.kts`

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "build-logic-demo"

include("library", "app")
~~~

`pluginManagement` được đặt **đầu settings file**, đúng thứ tự Gradle yêu cầu cho plugin resolution. `build-logic` là **included build**, không được thêm bằng `include("build-logic")` như một Java subproject.

### 6.3. `build-logic/settings.gradle.kts`

~~~kotlin
rootProject.name = "build-logic"
~~~

Đây là settings file của **chính included build**. Nó không được include ngược main build để tránh topology vòng không cần thiết.

### 6.4. `build-logic/build.gradle.kts`

~~~kotlin
plugins {
    id("kotlin-dsl")
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

`kotlin-dsl` là Gradle Kotlin DSL Plugin được Gradle cung cấp tương thích với phiên bản Gradle Wrapper, giúp compile precompiled script plugins và sử dụng type-safe accessors. **Không tự thêm version `org.jetbrains.kotlin.jvm` ngẫu nhiên** để thay `kotlin-dsl` trong bài này: Kotlin DSL plugin đã quản lý Kotlin compatibility theo Gradle distribution.

`repositories` tại đây phục vụ **build-logic build**. Nó không đặt repositories cho `:library`/`:app` một cách tự động.

### 6.5. `build-logic/src/main/kotlin/java-library-conventions.gradle.kts`

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

Đây là **toàn bộ precompiled script plugin**. Plugin ID được suy từ tên file: `java-library-conventions`, không phải `build-logic`.

Giải thích:

1. Gradle compile script plugin thành plugin implementation trước khi dùng.
2. `id("java-library")` áp dụng core Java Library plugin vào project **nhận convention**.
3. `java.toolchain...` dùng Java compiler/toolchain version 17 cho Java tasks thích hợp.
4. `tasks.withType<JavaCompile>().configureEach` đặt encoding UTF-8 theo cách lazy cho JavaCompile tasks.
5. Không có một external plugin dependency nên chưa cần `dependencies.implementation("plugin artifact")` trong build-logic.

**Precompiled script plugin này không được áp dụng tự động cho tất cả subprojects.** Chỉ project có `plugins { id("java-library-conventions") }` mới nhận cấu hình. Đó là một ưu điểm của explicit opt-in.

### 6.6. `library/build.gradle.kts`

~~~kotlin
plugins {
    id("java-library-conventions")
}
~~~

Library không cần lặp Java 17, UTF-8 và Java Library plugin trong file riêng nữa. Nếu library có các dependencies hoặc publishing settings đặc thù, chúng vẫn được khai báo tại đây hoặc trong convention plugins phù hợp.

### 6.7. `library/src/main/java/demo/library/Greeting.java`

~~~java
package demo.library;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Mã Java 17 này không cần third-party library. Không có static mutable state hoặc network call; output xác định.

### 6.8. `app/build.gradle.kts`

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":library"))
}

application {
    mainClass.set("demo.app.Main")
}
~~~

`application` là Gradle core plugin; nó cũng áp dụng Java plugin, tạo `run` task. Trong demo, app **không áp dụng library convention plugin** vì app cần Application plugin, còn convention đó được thiết kế cho Java libraries. Nếu app cũng cần Java 17/UTF-8 policy từ chung một nơi, hãy tạo plugin khác `java-application-conventions` hoặc một plugin nền `java-base-conventions` được cả hai cùng áp dụng.

### 6.9. `app/src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.library.Greeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message("Gradle"));
    }
}
~~~

### 6.10. Lệnh chạy và stdout

Linux/macOS, từ main build root:

~~~bash
./gradlew :app:run --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run --quiet
~~~

**Stdout của Java Main**:

~~~text
Hello, Gradle!
~~~

Đây là chuỗi đúng theo code Java. Gradle có thể in warnings/console messages ngoài ứng dụng theo version và môi trường. Nếu build chạy lần đầu, việc download Gradle Kotlin DSL compiler/tooling artifacts và Java toolchain có thể cần network/cache.

Kiểm tra các tasks:

~~~bash
./gradlew :library:compileJava
./gradlew :app:compileJava
./gradlew :library:tasks --all
./gradlew tasks --all
~~~

Build logic là một included build. Gradle phải build plugin khi consumer project dùng plugin ID; bạn **không cần tự gọi `:build-logic:jar` trước rồi sửa classpath thủ công**.

### 6.11. Kiểm tra nó không phải dependency của Java application

Convention plugin tác động đến **Gradle configuration**. Nó **không** tự làm JAR của build-logic trở thành:

~~~kotlin
implementation("company:build-logic:...")
~~~

trong application runtimeClasspath. Khi ứng dụng chạy, Java source chỉ cần `:library` và runtime dependencies của nó. Đó là ranh giới **build-time code vs application runtime code**.

## 7. Chuyển cùng plugin sang `buildSrc`: khác gì?

Để so sánh trên cùng bài toán, tạo **một bản copy** của project phần 6. Không cùng lúc giữ hai plugins trùng ID trong `buildSrc` và `build-logic` của cùng một build, vì dễ tạo conflict hoặc khiến không rõ plugin implementation nào được áp dụng.

Cấu trúc biến thể:

~~~text
buildsrc-demo/
├── settings.gradle.kts
├── gradlew
├── gradle/wrapper/...
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── java-library-conventions.gradle.kts
├── library/
│   ├── build.gradle.kts
│   └── src/main/java/demo/library/Greeting.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
~~~

### 7.1. Main settings không cần `includeBuild("buildSrc")`

~~~kotlin
rootProject.name = "buildsrc-demo"
include("library", "app")
~~~

Gradle tự phát hiện `buildSrc` ở build root nếu nó là build hợp lệ. **Không viết `include("buildSrc")`**; làm vậy biến buildSrc thành một project thông thường trong main build, không thể hiện cơ chế đặc biệt đúng.

### 7.2. `buildSrc/build.gradle.kts`

~~~kotlin
plugins {
    id("kotlin-dsl")
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

### 7.3. `buildSrc/src/main/kotlin/java-library-conventions.gradle.kts`

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

### 7.4. Library và app code

Giữ nguyên `library/build.gradle.kts` và các Java source ở phần 6. Với app vẫn dùng `application` và `implementation(project(":library"))`. Gradle tự build plugin từ buildSrc và `:library` có thể áp dụng:

~~~kotlin
plugins {
    id("java-library-conventions")
}
~~~

Chạy:

~~~bash
./gradlew :app:run --quiet
~~~

Stdout Java vẫn là:

~~~text
Hello, Gradle!
~~~

**Chức năng của convention plugin không đổi; cơ chế discover/classpath thay đổi**:

- `buildSrc`: tự phát hiện, classpath rộng của main build.
- `build-logic`: main settings include rõ, plugin resolution từ included build, ranh giới cô lập tốt hơn.

### 7.5. Cách Gradle nhìn phiên bản của plugin nội bộ

Với buildSrc và build-logic, consumer thường áp dụng plugin ID **không ghi version**:

~~~kotlin
plugins {
    id("java-library-conventions")
}
~~~

Vì plugin implementation nằm trong **source checkout đang được build**, không phải một released version được tải từ Plugin Portal. Bạn quản lý thay đổi bằng Git commit/branch của workspace, Gradle task inputs/cache và convention code review.

Đừng thêm `version "1.0.0"` vào một buildSrc plugin chỉ vì published plugins thường có version. Không có một module published marker mang `1.0.0` tương ứng trừ khi bạn thật sự thiết kế một publication/resolution workflow.

## 8. Published plugin: source ở build riêng, consumer lấy ID + version

Khi nhiều repositories độc lập cần cùng Gradle policy, `build-logic` copy trong mỗi repo có thể drift. Một **published plugin** giúp quản lý:

- Plugin ID ổn định, ví dụ `org.example.java-conventions`.
- Plugin implementation artifact cùng transitive dependencies.
- Version `1.0.0`, `1.1.0`… theo release lifecycle.
- Plugin marker metadata để `plugins { id(...) version ... }` tìm implementation.
- Phân quyền publish/consume qua Gradle Plugin Portal hoặc Maven-compatible registry.

Plugin được publish **không nhất thiết là Java binary plugin**. Để nhìn rõ plugin marker và `java-gradle-plugin`, ví dụ dưới đây dùng một **Java binary plugin**. Precompiled script plugin cũng có thể được publish nếu cấu hình plugin publications phù hợp.

## 9. Ví dụ đầy đủ: Java binary plugin xuất bản vào Maven file repository

Ví dụ dùng hai **Gradle builds riêng**, một plugin producer và một consumer. Không cần public Plugin Portal account vì publish vào file-backed Maven repository. Sau publish, consumer dùng `plugins` DSL với ID + version, không dùng `includeBuild` và không dùng `buildSrc`.

### 9.1. Cây thư mục

~~~text
published-plugin-demo/
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── plugin-project/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/java/org/example/build/JavaConventionsPlugin.java
└── plugin-consumer/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/java/demo/consumer/Main.java
~~~

Root directory chỉ chứa Wrapper để gọi hai builds bằng `-p`; từng thư mục con có settings riêng. Nếu phát triển hai repositories thật, sẽ có Gradle Wrapper riêng hoặc một Gradle installation cho mỗi. Đây là local workspace demo, không dùng plugin secrets/signing.

### 9.2. `plugin-project/settings.gradle.kts`

~~~kotlin
rootProject.name = "published-conventions-plugin"
~~~

Tên project `published-conventions-plugin` có thể trở thành phần artifactId của **plugin implementation module**. Đừng nhầm với **plugin ID** mà consumers sẽ áp dụng.

### 9.3. `plugin-project/build.gradle.kts` — file đầy đủ

~~~kotlin
plugins {
    id("java-gradle-plugin")
    id("maven-publish")
}

group = "org.example.build"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

gradlePlugin {
    plugins {
        create("javaConventions") {
            id = "org.example.java-conventions"
            implementationClass =
                "org.example.build.JavaConventionsPlugin"
        }
    }
}

publishing {
    repositories {
        maven {
            name = "demoLocal"
            url = uri(layout.buildDirectory.dir("local-repo"))
        }
    }
}
~~~

Giải thích:

1. `java-gradle-plugin` hỗ trợ phát triển Gradle plugin, Java Library component, Gradle API dependency và plugin descriptor generation.
2. `maven-publish` hỗ trợ các Maven publications cho plugin implementation và plugin marker.
3. `group`, project name, `version` tạo identity cho implementation artifact.
4. `gradlePlugin.plugins.create("javaConventions")` đăng ký một plugin ID.
5. `implementationClass` là fully qualified name của Java class implementing `Plugin<Project>`.
6. `publishing.repositories` chỉ tới file repository `plugin-project/build/local-repo`, không cần credentials.
7. Với hai plugins kết hợp, Gradle tự cấu hình **`pluginMaven` publication và plugin marker publication** theo `java-gradle-plugin` conventions, trừ khi tự tắt auto publishing.

**Không cần tự tạo `MavenPublication("pluginMaven")` và marker POM bằng tay** trong ví dụ cơ bản. Để biết task names thực tế, dùng `./gradlew tasks --all` hoặc task report trong plugin-project.

### 9.4. `JavaConventionsPlugin.java` — file đầy đủ

~~~java
package org.example.build;

import org.gradle.api.Plugin;
import org.gradle.api.Project;
import org.gradle.api.plugins.JavaPluginExtension;
import org.gradle.api.tasks.compile.JavaCompile;
import org.gradle.jvm.toolchain.JavaLanguageVersion;

public final class JavaConventionsPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getPluginManager().apply("java-library");

        project.getExtensions().configure(
            JavaPluginExtension.class,
            extension -> extension.getToolchain()
                .getLanguageVersion()
                .set(JavaLanguageVersion.of(17))
        );

        project.getTasks().withType(JavaCompile.class)
            .configureEach(task ->
                task.getOptions().setEncoding("UTF-8")
            );
    }
}
~~~

Đây là **Java class hoàn chỉnh** dùng Gradle API, được compile bằng Java 17 toolchain theo build script. Nó không có `main(String[])` vì Gradle gọi `apply(Project)` khi consumer áp dụng plugin.

Hành vi tương tự precompiled script plugin:

- Apply `java-library` vào consumer.
- Đặt Java toolchain version 17.
- Đặt UTF-8 cho JavaCompile tasks.

**Đừng dùng `project.afterEvaluate` để đổi Java toolchain hay task options nếu không có yêu cầu thực sự.** Cấu hình trực tiếp extensions và `configureEach` là hướng dễ bảo trì hơn, phù hợp lazy task configuration.

### 9.5. Publish plugin và marker artifacts

Từ workspace `published-plugin-demo`:

~~~bash
./gradlew -p plugin-project clean publish --console=plain
~~~

Windows:

~~~powershell
.\gradlew.bat -p plugin-project clean publish --console=plain
~~~

Khi thành công, file Maven repository dưới:

~~~text
plugin-project/build/local-repo/
~~~

sẽ có ít nhất hai nhóm module:

~~~text
Plugin implementation (ví dụ):
  org/example/build/published-conventions-plugin/1.0.0/...

Plugin marker (plugin ID được ánh xạ thành marker coordinates):
  org/example/java-conventions/
    org.example.java-conventions.gradle.plugin/
      1.0.0/...
~~~

**Cây trên là định hướng layout**, không phải danh sách file thực tế byte-for-byte. Plugin marker coordinates được sinh từ **toàn bộ plugin ID**: với ID `org.example.java-conventions`, marker group là `org.example.java-conventions` và marker artifact là `org.example.java-conventions.gradle.plugin`. Dấu chấm trong group thành các thư mục Maven path; ở ví dụ cây, `org/example/java-conventions` là cách chuyển group sang Maven path.

Marker POM trỏ tới implementation artifact. Consumers dùng `plugins { id("org.example.java-conventions") version "1.0.0" }` để Gradle tìm marker và tải implementation; không cần tự biết main plugin JAR coordinates.

Nếu publish vào Gradle Plugin Portal thực, dùng plugin/workflow dành cho Plugin Portal, account/API credentials và các bước validation/approval theo chính sách hiện hành. `maven-publish` tới file repository **không phải** publish lên public Plugin Portal.

### 9.6. Consumer `plugin-consumer/settings.gradle.kts`

~~~kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("../plugin-project/build/local-repo")
        }
        gradlePluginPortal()
    }
}

rootProject.name = "published-plugin-consumer"
~~~

`pluginManagement.repositories` là nơi Gradle tìm **plugin markers**. Đây không phải `repositories` để resolve `implementation`/`testImplementation` của Java application.

Đường dẫn `../plugin-project/build/local-repo` tương đối so với consumer build settings directory; phải publish producer **trước** khi consumer resolve plugin. Plugin Portal là fallback cho public third-party plugins nếu consumer cần, nhưng custom plugin demo tồn tại trong file Maven repo.

### 9.7. Consumer `plugin-consumer/build.gradle.kts`

~~~kotlin
plugins {
    id("org.example.java-conventions") version "1.0.0"
}
~~~

Không khai báo `java-library` hoặc toolchain ở consumer: published plugin sẽ apply `java-library` và Java 17. Đây là file **đầy đủ** cho demo. Nếu consumer có dependencies/business-specific tasks, thêm sau `plugins` block theo nhu cầu.

### 9.8. Consumer Java class

`plugin-consumer/src/main/java/demo/consumer/Main.java`:

~~~java
package demo.consumer;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Published plugin configured Java 17");
    }
}
~~~

### 9.9. Compile consumer rồi chạy Java

Từ workspace root:

~~~bash
./gradlew -p plugin-consumer compileJava --console=plain
java -cp plugin-consumer/build/classes/java/main demo.consumer.Main
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -p plugin-consumer compileJava --console=plain
java -cp plugin-consumer/build/classes/java/main demo.consumer.Main
~~~

**Stdout chính xác của Java Main**:

~~~text
Published plugin configured Java 17
~~~

`java-library` không tự tạo `run` task, vì đó là nhiệm vụ của `application` plugin. Do vậy ví dụ compile bằng `compileJava` rồi dùng `java -cp` thủ công để chạy Main; không gọi sai `./gradlew run` khi consumer chỉ có Java Library plugin.

Để kiểm tra toolchain version:

~~~bash
./gradlew -p plugin-consumer javaToolchains
./gradlew -p plugin-consumer tasks --all
~~~

`javaToolchains` là report task hữu ích trong Gradle, nhưng danh sách JDK thực tế phụ thuộc máy/Gradle configuration. Không cam kết một JDK nào ngoài toolchain yêu cầu sẽ được tìm nếu developer chưa cài/provision.

### 9.10. Thử nâng plugin version

Nếu producer tăng:

~~~kotlin
version = "1.1.0"
~~~

rồi publish lại, consumer **chưa tự dùng phiên bản mới** nếu vẫn khai báo:

~~~kotlin
id("org.example.java-conventions") version "1.0.0"
~~~

Phải cập nhật consumer plugin version (hoặc version catalog/pluginManagement policy) và kiểm thử. Đây là lợi ích của **released/pinned plugin**: nhiều repositories không tự thay đổi build behavior mỗi lần một source file của đội build logic được sửa.

## 10. Plugin marker artifact: vì sao publish JAR chưa đủ?

Gradle `plugins` DSL thường resolve **plugin ID + version** qua marker module. Ví dụ:

~~~kotlin
plugins {
    id("org.example.java-conventions") version "1.0.0"
}
~~~

Plugin marker coordinates theo convention:

~~~text
org.example.java-conventions:
org.example.java-conventions.gradle.plugin:
1.0.0
~~~

Marker POM dẫn tới **implementation module**, nơi chứa Java class và `META-INF/gradle-plugins/org.example.java-conventions.properties` với `implementation-class`.

`java-gradle-plugin` tự tạo descriptor; khi kết hợp `maven-publish`, Gradle có thể tạo marker publication tương ứng. Nếu chỉ tự upload một JAR do `jar` task sinh ra mà không có marker, `plugins` DSL có thể báo `Plugin ... was not found` dù implementation JAR thực sự tồn tại trên server.

Các cách khi plugin marker không có:

1. Tạo marker đúng bằng plugin development/publishing tooling — hướng nên dùng.
2. Hoặc trong consumer `pluginManagement.resolutionStrategy.eachPlugin` ánh xạ plugin ID sang implementation Maven module bằng `useModule(...)`, khi có lý do tương thích legacy publication.
3. Hoặc sử dụng `buildscript.dependencies.classpath` + `apply(plugin = "...")`, nhưng đó là đường legacy kém rõ phiên bản/phân tách hơn so với `plugins` DSL.

**Không nhầm:** plugin ID `org.example.java-conventions`, Java package `org.example.build` và Maven implementation module `org.example.build:published-conventions-plugin:1.0.0` là ba định danh khác nhau.

## 11. Một plugin có thể được phân phối bằng ba cách

Cùng policy Java 17/UTF-8:

~~~text
Cùng hành vi:
  apply java-library
  java toolchain = 17
  JavaCompile encoding = UTF-8

Cách 1: buildSrc
  source: buildSrc/src/main/kotlin/...gradle.kts
  availability: automatic buildscript classpath
  consumer: plugins { id("java-library-conventions") }

Cách 2: build-logic
  source: build-logic/src/main/kotlin/...gradle.kts
  settings: pluginManagement { includeBuild("build-logic") }
  consumer: plugins { id("java-library-conventions") }

Cách 3: published
  source: plugin project binary/precompiled source
  distribution: plugin marker + implementation artifact
  settings: pluginManagement.repositories
  consumer: plugins { id("org.example.java-conventions") version "1.0.0" }
~~~

Có thể phát triển một binary plugin **ngay trong `build-logic`** trước khi publish. Có thể phát hành một **precompiled script plugin** từ một plugin project để consumer dùng versioned ID. “Viết bằng Java hay Kotlin DSL” là chuyện implementation style; “tự động hay versioned repository” là chuyện distribution architecture.

## 12. Classloader, dependency visibility và version collision

### `buildSrc` được đưa lên buildscript classpath rộng

Điều này giúp tiện import helper types vào build scripts:

~~~kotlin
// Ví dụ nếu buildSrc định nghĩa class demo.build.VersionPolicy:
val policy = demo.build.VersionPolicy()
~~~

Đây là **mảnh minh họa**, class `VersionPolicy` chưa có trong demo. Nhưng cùng sự tiện lợi là một ràng buộc: dependencies của buildSrc có thể tác động classloader/buildscript environment; Gradle docs nhắc classloader differences so với included build.

### Included build có ranh giới được biểu đạt tường minh

Consumer apply một plugin ID được build trong included build. Build logic project tự quản lý implementation dependencies. Sự cô lập này giúp hiểu “đội nào sở hữu classpath của plugin nào”, đồng thời giảm nguy cơ toàn bộ source build logic trở thành global implicit classpath.

### Published plugin là versioned input của build

Consumer khai báo:

~~~kotlin
plugins {
    id("org.example.java-conventions") version "1.0.0"
}
~~~

Gradle resolve marker/implementation từ plugin repositories. Khi plugin nhiều versions hoặc external plugins có transitive dependencies, cần kiểm soát version/classloader conflicts như với các plugin dependencies khác.

**Không trộn một plugin đã có sẵn qua `buildSrc` classpath với một plugin cùng ID nhưng chỉ định version từ repository trong `plugins` block**, vì Gradle có thể báo plugin đã nằm trên classpath hoặc không xác định version để kiểm tra compatibility. Khi migrate, hãy chọn một nguồn áp dụng plugin ID tại một thời điểm.

## 13. Repository cho build logic khác repository cho app dependencies

Ba vị trí dễ nhầm:

~~~kotlin
// Main settings.gradle.kts:
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}
~~~

phục vụ **plugin resolution trong main build**. Trong khi:

~~~kotlin
// build-logic/build.gradle.kts:
repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

phục vụ **dependencies mà build-logic cần compile hoặc execute**. Và:

~~~kotlin
// app/build.gradle.kts:
repositories {
    mavenCentral()
}
~~~

phục vụ **Java application/library dependencies**.

Ba scope này không tự hợp nhất. Nếu một custom plugin apply external Gradle plugin (chẳng hạn formatting/codegen), included build cần **artifact của external plugin trên plugin implementation classpath** theo tài liệu precompiled script plugin; không chỉ ghi ID vào convention plugin rồi tưởng main build repositories giải quyết tất cả.

### Precompiled script plugin áp dụng external plugin

Sơ đồ phụ thuộc:

~~~text
build-logic/build.gradle.kts:
  dependencies {
      implementation("publisher:external-gradle-plugin-artifact:version")
  }

build-logic/src/main/kotlin/org-conventions.gradle.kts:
  plugins {
      id("external.plugin.id")
  }
~~~

Đây là **mẫu khái niệm**, các tọa độ publisher/external plugin artifact cần lấy từ tài liệu plugin thật, không phải lệnh copy-run. Trong precompiled script plugin, version của external plugin thường được quản lý trong **build-logic implementation dependency**, không đặt trực tiếp `version "..."` trong `plugins` block của precompiled script như một consumer build thông thường.

## 14. Version Catalog và settings isolation

Nếu main build có:

~~~text
gradle/libs.versions.toml
~~~

Gradle tự import catalog đó cho **main build**. Nhưng `buildSrc` và `build-logic` là builds riêng, **không tự thừa hưởng catalog** chỉ vì nằm trong cùng filesystem folder.

Có thể import rõ ở `build-logic/settings.gradle.kts`:

~~~kotlin
rootProject.name = "build-logic"

dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}
~~~

Đây là **mảnh mở rộng** cho demo đã có `gradle/libs.versions.toml`. Nếu folder TOML chưa tồn tại, không dùng snippet này vì sẽ fail settings evaluation. Bài demo runnable ở phần 6 không cần version catalog.

Tương tự trong `buildSrc/settings.gradle.kts`:

~~~kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}
~~~

Không gọi `from` nhiều lần trên cùng một catalog như cách merge nhiều TOMLs, vì Gradle chỉ cho phép một nguồn import qua builder `from(...)` trong một catalog. Khi quy mô lớn, có thể publish company-wide version catalog hoặc tạo source-of-truth rõ.

**Một version catalog không tự thực thi policy**. Nó quản lý aliases/phiên bản được yêu cầu, còn convention plugin quyết định **cấu hình và behavior**: apply plugin, compiler flags, test/release standards. Dùng chúng bổ trợ, không coi chúng là thay thế hoàn toàn cho nhau.

## 15. Performance: buildSrc vs build-logic vs published plugin

Chi phí cần nhìn riêng theo **cold start**, **thay đổi build logic** và **tác động đến các dự án khác**.

| Tình huống | `buildSrc` | `build-logic` | Published plugin |
| --- | --- | --- | --- |
| Lần đầu chưa có cache | Compile buildSrc | Compile included plugin build | Tải marker/JAR và dependencies nếu chưa cache |
| Không đổi gì, cache phù hợp | Có thể reuse compiled outputs | Có thể reuse compiled outputs | Reuse resolved plugin modules/cache |
| Đổi một helper/plugin nội bộ | Có thể invalidate nhiều/all main build scripts | Thường scope hẹp hơn theo plugins/subprojects sử dụng | Consumers vẫn pinned version cũ |
| Multi-repository reuse | Copy code hoặc gắn buildSrc vào từng repo | Include shared local build/repo checkout | Pin một version artifact dùng chung |
| Muốn rollback policy | Git revert/change source | Git revert/include different revision | Pin lại plugin version cũ |
| Muốn thử source mới ngay | Có | Có | Phải publish local/staging hoặc dùng composite substitution khi phát triển |

**Không khẳng định published plugin lúc nào chạy nhanh hơn build-logic**: tải dependencies/cold caches, plugin implementation complexity, Gradle configuration strategy và CI network đều ảnh hưởng. Included build có thể thêm setup/compilation overhead; khi ổn định và cache ấm, sự khác biệt phụ thuộc thực tế.

Gradle chính thức nhấn mạnh:
- `buildSrc` tiện prototyping nhưng có classloader/invalidation disadvantages.
- Included builds giúp cô lập build logic và có thể giảm task/config invalidations khi chỉ một plugin subproject thay đổi.
- Convention plugins giúp tránh cross-project `allprojects`/`subprojects` configuration, từ đó thuận với lazy configuration/configuration cache hơn.

### Cách đo

Chạy các lệnh có mục đích tương đồng trên cùng Wrapper/JDK/workspace:

~~~bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
./gradlew :app:build --configuration-cache
~~~

Trước/sau một thay đổi plugin nhỏ, quan sát:
- Configuration Cache stored/reused/invalidated?
- Tác động tới subprojects **không áp dụng plugin**?
- Build logic compilation tasks có UP-TO-DATE/FROM-CACHE không?
- Tổng build wall-clock/CI cost?
- Lỗi Configuration Cache/isolated projects có phát sinh từ code dùng `project.subprojects` hoặc task actions không?

Các flags và thông báo phụ thuộc Gradle version. **Không dùng `clean` liên tục khi đo incremental benefit**, vì nó biến thành một thí nghiệm khác.

## 16. Tránh `subprojects { ... }` để “thay thế” convention plugin

Một pattern cũ:

~~~kotlin
// Root build.gradle.kts, mảnh anti-pattern:
subprojects {
    apply(plugin = "java-library")

    tasks.withType<JavaCompile>().configureEach {
        options.encoding = "UTF-8"
    }
}
~~~

Có thể hoạt động trong build nhỏ nhưng root build đang **điều khiển cấu hình của các project khác**. Điều này làm khó ownership, IDE modeling, parallel project configuration và các Gradle features như isolated projects.

Cách rõ hơn:

~~~kotlin
// library/build.gradle.kts:
plugins {
    id("java-library-conventions")
}
~~~

Root không cần biết library có bao nhiêu JavaCompile tasks. Library chủ động apply plugin và plugin áp dụng convention ở **current project**, giảm cross-project model access.

Một convention plugin **không nên tự động đọc hoặc sửa `rootProject.subprojects`** nếu không có yêu cầu thực sự; như vậy chỉ di chuyển anti-pattern từ root build vào plugin, chưa cải thiện kiến trúc.

## 17. Convention plugin không nên khóa chết mọi lựa chọn

Một convention tốt tạo defaults mà project có thể tùy biến khi cần, ví dụ đặt Java toolchain thông qua Gradle `Property` API.

Trong precompiled plugin:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

đây là **default configuration hành vi** của plugin. Consumer có thể có quy trình override toolchain phù hợp trước khi task configuration finalized. Đừng ép `finalizeValue()` vô điều kiện cho mọi property hoặc dùng `afterEvaluate` chồng chéo chỉ để ngăn team sửa cấu hình.

Khi policy cần bắt buộc (ví dụ release phải dùng JDK approved), tách rõ:
- **Convention**: giá trị mặc định cho dev.
- **Validation**: kiểm tra không đúng chuẩn và báo lỗi rõ.
- **Enforcement**: hạn chế overrides khi được tổ chức phê duyệt.

Không dựa vào việc “dùng chung buildSrc” để bảo đảm mọi subproject đã tuân thủ; chỉ project áp dụng convention plugin đúng ID và task graph phù hợp mới nhận những cấu hình nó áp dụng.

## 18. Phát triển plugin đã công bố mà không phải publish mỗi lần

Khi plugin được phát hành ở repository nhưng bạn cần sửa nhanh một issue trước release, có thể dùng **composite build** tại consumer để substitute local plugin build trong `pluginManagement`:

~~~kotlin
// Consumer settings.gradle.kts, mảnh local co-development:
pluginManagement {
    includeBuild("../plugin-project")

    repositories {
        gradlePluginPortal()
    }
}
~~~

Sau đó consumer có thể áp dụng plugin ID local, thường không cần released version trong `plugins` block tùy setup/resolution strategy. Hãy cấu hình thống nhất và tránh vừa yêu cầu một published marker version, vừa mong local substitution thắng mà chưa kiểm chứng.

**Tách hai chế độ kiểm thử:**

1. Local plugin development: resolve source từ included build, nhanh để thay đổi code.
2. Published-plugin acceptance: **không include** local provider, resolve từ file/staging/production repository bằng ID + pinned version, xác minh marker/JAR đã publish.

Nếu chỉ test bằng composite local, bạn chưa chứng minh một Maven consumer độc lập tìm được plugin marker artifact. Ngược lại, chỉ test published artifact không đủ để kiểm tra code chưa release.

## 19. Plugin ID, version và compatibility policy

Một tổ chức có thể đặt tên plugin:

~~~text
com.company.java-library-conventions
com.company.java-application-conventions
com.company.publication-conventions
~~~

Nguyên tắc:
- ID ổn định, có namespace organization để tránh conflict.
- Một plugin làm một vai trò rõ, có thể apply các plugin nền khác.
- Không dùng một plugin “mega-conventions” chứa tất cả publishing, Docker, Spring, Android, codegen cho mọi project nếu không cần.
- Pin external plugin versions và test compatibility với các Gradle Wrapper versions được hỗ trợ.
- Plugin compile với Java 17 không đảm bảo tương thích mọi Gradle release: Gradle API, Kotlin DSL plugin version, task APIs và deprecations cũng thay đổi.
- Khi breaking changes về public extension/task names/behavior, phát hành major version/plugin ID migration theo policy.
- Giữ automated tests trên nhiều Gradle/JDK combinations nếu plugin dùng cho nhiều repositories.

**Không dùng dynamic plugin version** chỉ để “luôn có bản mới nhất” trong production CI. Một upgrade plugin có thể thay đổi compiler flags/dependency resolution và gây build break dù Java code không đổi.

### Plugin marker/version catalog

Consumer có thể quản lý plugin version bằng plugin alias trong `gradle/libs.versions.toml` (nếu có catalog):

~~~toml
[versions]
companyPlugin = "1.0.0"

[plugins]
companyJavaConventions = {
    id = "org.example.java-conventions",
    version.ref = "companyPlugin"
}
~~~

Ví dụ file TOML trên là **mảnh cấu hình**; nếu dùng version catalog thật, đặt đúng cú pháp alias. Consumer:

~~~kotlin
plugins {
    alias(libs.plugins.companyJavaConventions)
}
~~~

**Alias chỉ khai báo ID/version**; plugin artifact vẫn phải được resolve từ `pluginManagement.repositories` hoặc nguồn được Gradle cấu hình. Version catalog không tự publish plugin.

## 20. Plugin testing: chỉ chạy `help` là chưa đủ

Build logic chứa code thực thi trong build. Một thay đổi có thể làm:
- Không tạo JavaCompile task đúng.
- Sai Java toolchain, artifact classifier hoặc JUnit engine.
- Đọc system property/Project model ở task action và hỏng Configuration Cache.
- Register task quá sớm hoặc resolve configuration trong configuration phase.
- Áp dụng nhầm plugin/cấu hình task ở root thay vì current project.
- Không hoạt động trên Gradle Wrapper mới dù compile code Java thành công.

Nên kiểm tra theo nhiều tầng:

### Tầng A — compile/plugin descriptor

~~~bash
./gradlew -p plugin-project build
./gradlew -p plugin-project validatePlugins
~~~

`java-gradle-plugin` có `validatePlugins` để kiểm tra task/transform property annotations và plugin metadata theo API Gradle. `build` đảm bảo plugin Java code được compile và tests của plugin project chạy nếu đã khai báo.

### Tầng B — functional tests với Gradle TestKit

Gradle cung cấp `GradleRunner` để chạy một Gradle build nhỏ trong tests, áp dụng plugin và kiểm tra task outcomes/console output. Với `java-gradle-plugin`, TestKit dependencies/classpath integration được hỗ trợ.

Mẫu test ý tưởng:

~~~java
// Mảnh functional test trong Java plugin project.
// Cần JUnit 5, @TempDir và test setup đúng Gradle TestKit.
GradleRunner.create()
    .withProjectDir(testProjectDir.toFile())
    .withArguments("help", "--stacktrace")
    .withPluginClasspath()
    .build();
~~~

Đây **không phải Java test file độc lập**, vì `testProjectDir` và fixture build files chưa được khai báo. Nó chỉ mô tả TestKit API; nên viết tests thật cho behavior, bao gồm Java toolchain, UTF-8 và custom tasks.

### Tầng C — consumer smoke test

Ví dụ phần 6/9 kiểm chứng:
- `:library` apply convention và compile được `Greeting.java`.
- `:app` consume library, in `Hello, Gradle!`.
- Published binary plugin consumer resolve ID + version từ Maven marker và compile Java.
- Chạy cùng tests với Configuration Cache và ít nhất một Gradle version mà tổ chức hỗ trợ.

### Tầng D — published artifact integrity

Kiểm tra plugin marker POM, plugin implementation JAR/class descriptor, transitive dependencies, repository credentials, signatures/checksums khi cần, rồi chạy một consumer **không sử dụng buildSrc hoặc includeBuild local**.

## 21. Migration từ `buildSrc` sang `build-logic`

Nếu repository lớn đang có nhiều code trong buildSrc, một migration có thể làm theo từng bước thay vì rewrite tất cả:

1. **Kiểm kê** classes, precompiled script plugins, custom task types và external plugin dependencies trong buildSrc.
2. **Nhóm theo trách nhiệm**, ví dụ `java-conventions`, `quality-conventions`, `publishing-conventions`; không chuyển mọi logic vào một file khổng lồ.
3. Tạo build riêng `build-logic/settings.gradle.kts` và `build-logic/build.gradle.kts`, áp dụng `kotlin-dsl` hoặc `java-gradle-plugin` tùy implementation style.
4. Chuyển precompiled scripts vào `build-logic/src/main/kotlin` và Kotlin/Java task classes vào source set phù hợp.
5. Cấu hình repositories và plugin implementation dependencies **trong build-logic**, vì nó không kế thừa main build config.
6. Nếu cần catalog chung, import rõ vào `build-logic/settings.gradle.kts`.
7. Ở main settings, thêm `pluginManagement { includeBuild("build-logic") }`.
8. Tại từng subproject, áp dụng plugin ID; ưu tiên **explicit opt-in** thay vì root `subprojects` cross-configuration.
9. Chạy Gradle compile/test, compare task graph, compiler flags, JDK, generated outputs và reports trước/sau.
10. Xóa/để trống buildSrc cũ khi mọi imports/IDs đã được migrate, tránh **hai nguồn plugin trùng ID**.
11. Kiểm tra Configuration Cache, IDE Gradle sync và thời gian cold/warm builds.
12. Commit migration có release note nội bộ để teams biết plugin IDs/ownership.

**Có thể giữ một `buildSrc` nhỏ để prototype hoặc code migration tạm thời**, nhưng phải tránh dependency cycles: `build-logic` cần tự compile và không nên phụ thuộc ngược vào main build application projects.

### Cần xử lý helper imports khác plugin IDs

Nếu buildSrc có:

~~~kotlin
// Dùng trực tiếp trong build.gradle.kts:
import com.company.build.MyUtility
~~~

chuyển class sang included build **không tự làm import đó vẫn còn trên mọi buildscript classpath**. Cần:
- Đưa logic vào convention/binary plugin cung cấp behavior,
- hoặc thêm plugin/artifact classpath phù hợp một cách tường minh,
- hoặc tách utility package thành module được build logic project phụ thuộc.

Đây là một khác biệt thực chất giữa buildSrc implicit classpath và included build plugin isolation. Chỉ copy thư mục rồi thêm `includeBuild` có thể khiến script compile fail dù code class không thay đổi.

## 22. Khi nào nên nâng `build-logic` thành published plugin?

Nên cân nhắc publishing khi:

- Nhiều codebases có Git repositories độc lập muốn cùng một policy.
- Muốn quản lý plugin release lifecycle/version pin rõ và rollback dễ.
- Plugin có public extensions/tasks API tương đối ổn định.
- Team có thể duy trì TestKit tests, compatibility matrix, documentation và release process.
- Muốn phân quyền build-logic owner, CI publish rights, repository signatures/dependency verification.
- Cần dùng plugin từ environment không thể include shared source checkout.

**Chưa nhất thiết publish** nếu policy thay đổi hằng ngày, chỉ có một monorepo và co-development build logic rất sát với application source. Lúc đó `build-logic` có thể đủ, ít chi phí quản trị artifact version.

### Lộ trình có kiểm soát

~~~text
Bắt đầu:
  buildSrc prototype

Trưởng thành:
  included build-logic
    - convention plugins
    - tests
    - independent dependencies

Dùng chung liên repository:
  published plugin artifact
    - stable plugin ID
    - semantic version
    - plugin marker
    - repository and credentials
    - backward compatibility policy
~~~

Đây là **lộ trình khả dĩ**, không phải yêu cầu dự án nào cũng phải trải qua đủ ba bước. Một đội có thể bắt đầu trực tiếp bằng `build-logic` hoặc published plugin tùy quy mô.

## 23. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| `Plugin [id: 'java-library-conventions'] was not found` | Quên `pluginManagement.includeBuild` hoặc plugin file/ID sai | So main settings và filename `*.gradle.kts` |
| `Unresolved reference: java` trong precompiled script | Chưa apply Java/Java Library plugin hoặc type-safe accessors không có | Áp dụng `id("java-library")` trong script plugin và kiểm tra Kotlin DSL plugin |
| `buildSrc` plugin không được tìm thấy | Directory sai cấp, Gradle buildSrc build fail hoặc ID mismatch | Đặt buildSrc đúng root, build.gradle.kts hợp lệ |
| `java-gradle-plugin` binary plugin báo missing implementation class | `gradlePlugin.implementationClass` khác FQCN thực | Kiểm tra package/classfile và plugin descriptor |
| Published `plugins` DSL không tìm ID | Marker artifact không có hoặc `pluginManagement.repositories` sai | Dùng `java-gradle-plugin` + `maven-publish` và kiểm tra marker POM |
| Có plugin JAR nhưng vẫn `Plugin not found` | Chỉ upload implementation JAR, không có marker | Publish marker hoặc resolutionStrategy.useModule |
| Plugin được apply nhưng JavaCompile không thay đổi | Plugin không apply `java-library` hoặc cấu hình nhầm project/task | Inspect plugin code, `tasks --all`, toolchains |
| Consumer dùng version 1.0 dù đã publish 1.1 | Plugin version pinned | Nâng `plugins` version/version catalog |
| Plugin build không thấy libs catalog | Build-logic/buildSrc không kế thừa catalog main | Import catalog vào settings của build logic |
| External plugin ID trong precompiled script không resolve | Thiếu implementation artifact của external plugin trong build-logic | Thêm đúng plugin implementation dependency |
| Gradle cảnh báo Kotlin DSL plugin version không phù hợp | Tự ghép Kotlin DSL plugin version trái Gradle Wrapper | Dùng `id("kotlin-dsl")` do Gradle cung cấp |
| `buildSrc` thay một file làm nhiều scripts reconfigure | Implicit broad classpath/invalidation | Tách convention plugins vào included build, đo cải thiện |
| Plugin trong build-logic không hoạt động khi main repo offline | Build-logic cần resolve compiler/dependencies | Kiểm tra local Gradle cache/repositories |
| App `run` task không có trong published plugin demo | Plugin chỉ apply `java-library` | Dùng `compileJava` + `java -cp` hoặc apply `application` khi cần |
| Consumer đọc source bằng `implementation(project(":build-logic"))` | Nhầm build-time plugin với runtime library | Apply plugin bằng ID, không coi nó là Java application dependency |
| `build-logic` không thấy repositories main build | Included builds isolated | Cấu hình repositories trong build-logic |
| Plugin ID trùng giữa buildSrc và included build | Hai implementations cạnh tranh | Chỉ giữ một nguồn plugin ID trong migration |
| Main Gradle Wrapper đổi khiến plugin lỗi | Gradle API/Kotlin DSL compatibility | Test plugin trên Gradle versions hỗ trợ |
| `subprojects` mutation bị cảnh báo hoặc không tương thích isolation | Cross-project configuration | Chuyển sang opt-in convention plugin tại từng project |
| CI publish plugin fail 401/403 | Credentials/quyền upload sai | Secret store, repository-specific permissions |
| Consumer local PASS nhưng published plugin FAIL | Chưa kiểm tra marker/dependency metadata | Smoke test bằng repository artifact, không includeBuild |
| Configuration Cache fail từ custom plugin | Đọc Project/Gradle model trong task action hoặc eager resolution | Dùng task inputs/Providers và lazy config |
| Java 17 app compile sai JDK | Toolchain chưa cài hoặc plugin không applied | Kiểm tra `javaToolchains`, plugin ID, JavaCompile options |

## 24. Quy trình chẩn đoán theo câu hỏi

**Vấn đề 1 — Plugin đến từ đâu?** Xác định đó là `buildSrc`, `pluginManagement.includeBuild`, top-level `includeBuild`, hoặc published repository. Không sửa plugin marker khi plugin thực tế chỉ nằm trong buildSrc.

**Vấn đề 2 — ID có đúng không?** Với precompiled script `java-library-conventions.gradle.kts`, ID là `java-library-conventions` nếu không có package prefix. Với binary plugin, ID là `gradlePlugin.plugins...id`, không nhất thiết cùng Java class name.

**Vấn đề 3 — Plugin classpath có thiếu không?** Precompiled script dùng external plugin phải có implementation artifact trên chính build-logic/buildSrc classpath. Published plugin phải upload marker và implementation artifact dependencies.

**Vấn đề 4 — Plugin đã được áp dụng vào project nào?** Chỉ `plugins { id("...") }` trong project đó mới áp dụng convention. Root settings include build-logic không tự apply mọi conventions.

**Vấn đề 5 — Build logic thuộc repository nào?** Main build repositories và pluginManagement repositories không có cùng vai trò. Included build có settings riêng. Consumer published plugin cần pluginManagement.repositories.

**Vấn đề 6 — Có đang dùng đúng phiên bản không?** Với local source, Git revision quyết định. Với published plugin, `version "x.y.z"` quyết định yêu cầu; dependency caches và repository order có thể ảnh hưởng khi reuse mutable versions.

**Vấn đề 7 — Có nhầm build-time vs runtime dependency?** Plugin JAR không cần hiện diện trên Java application runtimeClasspath chỉ vì nó cấu hình JavaCompile tasks.

**Vấn đề 8 — Có so được cold vs warm cache không?** Đừng kết luận performance từ duy nhất một invocation; quan sát configuration cache và task reruns.

## 25. Hướng dẫn lựa chọn thực tế

| Hoàn cảnh | Ưu tiên | Lý do |
| --- | --- | --- |
| Một project học Gradle, chỉ một helper ngắn | `buildSrc` hoặc script trực tiếp nếu thật nhỏ | Ít setup, dễ thử nghiệm |
| Một monorepo > nhiều Java subprojects | `build-logic` + convention plugins | Ranh giới rõ, explicit opt-in, cô lập thay đổi tốt |
| Dự án có cả Java/Android/Kotlin với conventions phức tạp | Nhiều plugins nhỏ trong `build-logic` | Tránh mega-plugin, dễ test/ownership |
| Nhiều repos độc lập cần một Java build policy ổn định | Published plugin versioned | Reuse xuyên repo, pin version, rollback |
| Muốn thử plugin patch trước khi phát hành | `pluginManagement.includeBuild` co-development | Dùng local source không publish mỗi lần |
| Cần consumer verify plugin phát hành thực sự | Published artifact từ staging/file/remote repo | Kiểm tra plugin marker, POM, dependencies |
| Chỉ muốn chia sẻ version numbers | Version Catalog | Không cần plugin nếu không có behavior/task configuration |
| Muốn chia sẻ task type phức tạp có inputs/outputs | Binary plugin + custom task classes | API/type-safety và testing tốt hơn một script dài |
| Nhiều builds cần dùng chung plugin nhưng không muốn registry | Included build source checkout (nếu workflow cho phép) | Cấu hình cục bộ được version-control |
| Công ty cần supply-chain controls/approval | Published plugin private registry + signing/verification | Quản trị lifecycle và quyền upload tập trung |

**Khuyến nghị mặc định cho Gradle multi-project build đang phát triển:** precompiled convention plugins trong một included build `build-logic`. Chỉ dùng `buildSrc` khi độ đơn giản quan trọng hơn isolation; chỉ publish khi tính độc lập giữa repositories/versioning có lợi rõ ràng.

## 26. Bài tập tự kiểm tra

**Câu 1.** `buildSrc` và `build-logic` khác nhau về discovery?

**Đáp:** Gradle tự tìm `buildSrc` ở root. `build-logic` là một included build cần khai báo `includeBuild`/`pluginManagement.includeBuild` trong settings.

**Câu 2.** “Conventions plugin” có bắt buộc là một file `.gradle.kts` không?

**Đáp:** Không. Đây là vai trò chung; có thể triển khai bằng precompiled script hoặc binary plugin.

**Câu 3.** Published plugin có bắt buộc phải viết bằng Java class không?

**Đáp:** Không. Published plugin có thể là precompiled script hoặc binary plugin được đóng gói và publish đúng metadata.

**Câu 4.** Thay một file trong buildSrc có chắc mọi `compileJava` task sẽ chạy lại không?

**Đáp:** Không chắc. Build configuration có thể invalidated rộng, nhưng task outputs/up-to-date/build cache phải được xét riêng.

**Câu 5.** `include("build-logic")` có tương đương `pluginManagement { includeBuild("build-logic") }` không?

**Đáp:** Không. `include` thêm subproject main build, còn `includeBuild` thêm build độc lập. `pluginManagement` định hướng plugin resolution sớm.

**Câu 6.** `java-library-conventions.gradle.kts` không có package sẽ có plugin ID gì?

**Đáp:** `java-library-conventions`.

**Câu 7.** Có thể áp dụng plugin trong build-logic bằng `implementation(project(":build-logic"))` ở Java app không?

**Đáp:** Không đúng mục đích. Plugin thuộc build-time; cần apply plugin ID trong `plugins` block.

**Câu 8.** Một published plugin có ID `org.example.java-conventions` và version `1.0.0` cần gì để `plugins` DSL tìm?

**Đáp:** Plugin marker artifact trỏ tới implementation JAR và `pluginManagement.repositories` phù hợp; plugin API descriptor/class phải tồn tại.

**Câu 9.** Tại sao published binary plugin demo không có task `run`?

**Đáp:** Plugin áp dụng `java-library`, không phải `application`. Nó có `compileJava`; để run cần Application plugin hoặc dùng `java -cp` sau compile.

**Câu 10.** Main build có `gradle/libs.versions.toml`. Build-logic có tự dùng `libs` chưa?

**Đáp:** Không mặc nhiên. Included build có settings độc lập, cần import catalog hoặc dependency declaration riêng.

**Câu 11.** External plugin trong precompiled script chỉ cần ghi `id("external.plugin")` là đủ?

**Đáp:** Không nhất thiết. External plugin implementation artifact phải được thêm vào dependency classpath của build-logic, theo plugin docs.

**Câu 12.** Với published plugin, consumer ở version 1.0 có tự nhận behavior của bản 1.1 mới publish không?

**Đáp:** Không nếu version pinned là 1.0. Cần nâng yêu cầu version và test.

**Câu 13.** Tại sao local composite plugin test chưa chứng minh published plugin hoạt động?

**Đáp:** Local include có thể bỏ qua plugin marker/repository resolution; cần một consumer tải released artifact thật.

**Câu 14.** Vì sao root `subprojects { ... }` không phải giải pháp tốt cho quy ước lớn?

**Đáp:** Nó cấu hình cross-project, làm tăng coupling và khó tận dụng isolated/lazy configuration. Convention plugin cho phép từng project tự opt-in.

**Câu 15.** Plugin JAR chạy ở compile-time có phải runtime dependency của ứng dụng Java không?

**Đáp:** Không. Nó cấu hình build; chỉ app/library dependencies thật mới thuộc runtimeClasspath của ứng dụng.

## 27. Checklist áp dụng và review

- [ ] Đã phân biệt implementation style (precompiled/binary) với distribution (buildSrc/included/published).
- [ ] Dự án nhiều subprojects ưu tiên convention plugins thay vì copy-paste hoặc `subprojects` mutation.
- [ ] BuildSrc nằm đúng root, không thêm `include("buildSrc")`.
- [ ] Build-logic được include rõ, có settings/repositories riêng.
- [ ] `pluginManagement { includeBuild(...) }` đặt đúng scope/thứ tự khi cần plugin resolution.
- [ ] Precompiled script plugin filename/ID chính xác; Gradle Kotlin DSL plugin phù hợp Wrapper.
- [ ] Core/third-party plugins và dependencies được khai báo trên đúng plugin classpath.
- [ ] Chỉ apply convention vào projects cần, không ép toàn bộ root/subprojects.
- [ ] Java toolchain, compiler encoding, tests/publishing policy được kiểm chứng.
- [ ] Build-logic version catalog được import rõ nếu cần, không suy rằng kế thừa root.
- [ ] Published plugin có stable ID + version, plugin marker và implementation artifact.
- [ ] Consumer `pluginManagement.repositories` chứa registry thật.
- [ ] CI pin plugin version, không dùng dynamic release trong production.
- [ ] Không lưu publish credentials/signing keys plaintext trong Git.
- [ ] Published plugin được kiểm tra bằng consumer độc lập, không chỉ local include.
- [ ] Đã kiểm tra Configuration Cache, lazy task registration và build performance.
- [ ] Plugin changes có tests, changelog/migration notes và version compatibility policy.
- [ ] Khi migrate, không giữ hai implementations cùng plugin ID.
- [ ] Không coi build-time plugin JAR là Java application dependency.
- [ ] Có kế hoạch rollback khi plugin release mới gây sự cố.

## 28. Tài liệu chính thức

- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): vì sao ưu tiên included build `build-logic` và convention plugins thay `buildSrc` ở dự án lớn.
- [Gradle — Sharing Build Logic Using buildSrc](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): cơ chế buildSrc và các convention plugins.
- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds_intermediate.html): included `build-logic`, build boundaries và modules.
- [Gradle — Precompiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html): tên file → plugin ID, Kotlin DSL implementation, external plugin classpath.
- [Gradle — Precompiled Script Plugins Advanced](https://docs.gradle.org/current/userguide/pre_compiled_script_plugin_advanced.html): buildSrc/composite placement, plugin development, publishing.
- [Gradle — Introduction to Plugins](https://docs.gradle.org/current/userguide/plugins.html): core, local/community plugins; script/precompiled/binary plugin distinctions.
- [Gradle — Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): `java-gradle-plugin`, plugin descriptors, `gradlePlugin`, TestKit và marker Maven publications.
- [Gradle — Preparing to Publish Plugins](https://docs.gradle.org/current/userguide/preparing_to_publish.html): plugin implementation/marker artifacts, local repository testing, publishing.
- [Gradle — Publishing to Gradle Plugin Portal](https://docs.gradle.org/current/userguide/publishing_gradle_plugins.html): plugin publication validation, credentials, approvals và Portal.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): import catalog vào buildSrc/included builds, khác biệt scopes.
- [Gradle — Gradle Kotlin DSL Primer](https://docs.gradle.org/current/userguide/kotlin_dsl.html): Kotlin DSL plugin, Gradle compatibility và compiler integrations.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): included build isolation, dependency substitution và task graph.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): reuse configuration và những hạn chế khi plugin đọc build model trong task actions.
- [Gradle — Gradle TestKit](https://docs.gradle.org/current/userguide/test_kit.html): functional testing cho Gradle plugins bằng GradleRunner.
