# Dependency substitution tự động và trường hợp cần cấu hình rõ trong Gradle Composite Build

## 1. Mục tiêu: phát triển một thư viện ở local mà consumer không cần publish trước

Bạn đang phát triển ứng dụng Java phụ thuộc vào thư viện Maven:

```kotlin
dependencies {
    implementation("org.example.math:number-utils:1.0.0")
}
```

Bình thường Gradle tìm module đó trong Maven/Ivy repositories và tải artifacts đã publish. Nhưng bạn vừa sửa source của `number-utils` trên máy, muốn chạy `app` với thư viện mới **ngay lập tức**, không cần mỗi lần đều chạy `publishToMavenLocal` rồi refresh dependencies.

**Composite build** giải quyết tình huống này bằng `includeBuild(...)`. Một Gradle build có thể **bao gồm cả Gradle build độc lập khác**; Gradle sẽ tự thay module dependency phù hợp bằng một **project component của included build** và xây output từ source local. Cơ chế đó được gọi là **dependency substitution**.

Bài này tập trung vào hai câu hỏi:

1. **Khi nào Gradle substitution hoàn toàn tự động?** Khi tọa độ module consumer yêu cầu trùng với `group:name` của một project trong included build.
2. **Khi nào phải khai báo rõ `dependencySubstitution`?** Khi group/name không trùng tọa độ published module, project không có group đúng, tên artifact được đổi khi publish, có nhiều publications hoặc cần điều khiển chính xác module nào ánh xạ tới project nào.

Sau bài học, bạn sẽ:

- Phân biệt `include(...)` (multi-project) và `includeBuild(...)` (composite).
- Hiểu thuật toán nhận diện **`project.group` + `project.name`** và sự khác nhau với Maven `artifactId`.
- Tạo demo hoàn chỉnh **Java 17, Gradle Kotlin DSL, không cần Maven publication** để thấy substitution tự động hoạt động.
- Chuyển demo sang mapping tường minh bằng `includeBuild { dependencySubstitution { substitute(module(...)).using(project(...)) } }`.
- Hiểu vì sao một version consumer yêu cầu không nhất thiết bằng `project.version` nhưng vẫn nhận code local.
- Kiểm chứng bằng `dependencies`, `dependencyInsight`, Gradle task graph và stdout ứng dụng.
- Biết cách cố ý **tắt global substitutions cho một configuration riêng** để so sánh artifact đã publish với source local.
- Nhận diện giới hạn của default configuration, custom publications, variants/capabilities, nhiều included builds và CI.
- Tránh các lỗi `UnknownProjectException`, thiếu group, naming mismatch, rules không áp dụng trong build khác, plugin resolution bị nhầm với dependency substitution.

**Kết luận cần nhớ:** `includeBuild` không “chép code” vào một subproject. Nó **giữ hai Gradle builds độc lập**, rồi nối dependency resolution và những tasks cần xây artifacts giữa các builds.

## 2. Khái niệm chính: included build là một build, không phải một subproject

So sánh hai cấu trúc:

```text
MULTI-PROJECT BUILD
root/settings.gradle.kts
    include(":app", ":lib")
root/app/build.gradle.kts
root/lib/build.gradle.kts

    :app có thể dùng implementation(project(":lib"))


COMPOSITE BUILD
workspace/
    consumer-app/settings.gradle.kts
    consumer-app/build.gradle.kts
    number-utils/settings.gradle.kts
    number-utils/build.gradle.kts

consumer-app/settings.gradle.kts:
    includeBuild("../number-utils")

    consumer-app yêu cầu "org.example.math:number-utils:1.0.0"
    Gradle tự tìm project khớp trong included build
```

**Multi-project:** các subprojects dùng chung **một settings/build hierarchy**. `project(":lib")` là reference hợp lệ khi `:lib` đã được `include` trong chính settings đó.

**Composite:** mỗi included build có **settings, project graph, repositories, plugin versions, lifecycle và logic** riêng. Không thể viết `implementation(project(":number-utils"))` trong consumer để trỏ sang **root project thuộc included build**, vì nó không tồn tại trong project hierarchy của consumer.

Gradle hỗ trợ hai kiểu `includeBuild`:

```kotlin
// settings.gradle.kts
includeBuild("../number-utils")
```

hoặc tạm thời qua CLI:

```bash
./gradlew run --include-build ../number-utils
```

Cả hai có thể kích hoạt substitutions tương ứng khi đủ điều kiện. Với dự án lâu dài, khai báo trong **settings** thường rõ ràng/reproducible hơn vì mọi developer và CI dùng cùng graph.

Một composite có thể có nhiều included builds. Các included builds được cấu hình độc lập: **không tự kế thừa** repositories, custom `gradle.properties`, plugins hoặc version catalogs của consumer. Khi build con có external dependencies, chính build con cần repositories/toolchains phù hợp.

## 3. Dependency substitution tự động diễn ra như thế nào?

Theo tài liệu Gradle Composite Builds, Gradle kiểm tra các projects trong included build và tạo mapping mặc định dựa vào:

```text
external module selector:  project.group : project.name
                              |               |
                              v               v
org.example.math:number-utils  ->  included build project ":"
```

Nói cách khác, thuật toán mặc định là:

```text
đối với một project P trong included build:
    module identity = P.group + ":" + P.name
    thay module dependencies có group/name khớp
    bằng project component P
```

**Ba điều cần phân biệt rõ:**

- `project.group` là group được cấu hình trong `build.gradle(.kts)` hoặc conventions.
- `project.name` là project name từ settings. Với single-project included build, nó thường là `rootProject.name`; với multi-project included build, nó là tên từng subproject.
- `project.version` không phải khóa tra mặc định để nhận diện substitution. Gradle có thể thay một module version consumer yêu cầu bằng **local project** mang version khác.

Ví dụ:

```kotlin
// number-utils/build.gradle.kts
group = "org.example.math"
version = "1.1.0-SNAPSHOT"
```

```kotlin
// number-utils/settings.gradle.kts
rootProject.name = "number-utils"
```

Consumer đang yêu cầu:

```kotlin
dependencies {
    implementation("org.example.math:number-utils:1.0.0")
}
```

Gradle nhận `group:name` trùng, nên resolve dependency thành project local (nếu đang include build), không bắt buộc tải `1.0.0` từ Maven.

**Đây là lợi ích nhưng cũng là rủi ro:** build ở composite có thể đang chạy với code local mới nhất, **không phải binary của phiên bản đã publish**. Nếu cần kiểm thử bản thật sự phát hành, hãy dùng configuration tắt substitution ở phần 9 hoặc chạy build độc lập không bao gồm local build.

### 3.1. Substitution không phải là việc thay chuỗi version trong file

`implementation("org.example.math:number-utils:1.0.0")` vẫn tồn tại nguyên trong build script. Gradle thay **component được chọn khi dependency resolution**. Bạn không cần đổi dòng dependency thành `project(":number-utils")` hay đổi version thành `1.1.0-SNAPSHOT` mỗi lần phát triển local.

Những tác động cần hiểu:

1. Classpath sử dụng outputs/variants của local project thay vì JAR từ remote repository.
2. Gradle sẽ xây những outputs cần thiết từ included build để tiêu thụ, nối task dependencies khi phù hợp.
3. Module version đã khai báo không còn chứng minh classpath dùng đúng release đó.
4. Local project có thể có code chưa commit; kết quả chạy không tương đương release reproducibility.
5. Không có việc Gradle **tự publish local project vào Maven**; substitution đi qua Gradle dependency graph.
6. Artifacts và metadata của local project phải đáp ứng đúng variant/capability requirements của consumer.

### 3.2. Áp dụng tới cả transitive dependencies?

Một external library được kéo **bắc cầu** có thể bị thay bởi local project nếu selector trùng và rules có hiệu lực trong graph consumer. Nhưng **cấu hình substitution được định nghĩa trong build này không mặc nhiên trở thành quy tắc trong một build độc lập khác**.

Tài liệu Gradle phân biệt hai điều:

- **Dependencies trong một graph đã áp dụng rules:** module được chọn có thể là direct hoặc transitive và phù hợp selector.
- **Rules giữa các builds:** explicit substitutions **không tự truyền/lan** sang mọi included build khác chạy độc lập. Một included build riêng phải có cấu hình tương ứng nếu bản thân nó cần mapping đó trong context riêng.

Không nhầm `transitive dependency` với `transitivity of substitution configuration across builds`.

## 4. Demo độc lập: hai Gradle builds và substitution tự động

Đây là ví dụ **Java 17 + Gradle Kotlin DSL** với **hai builds hoàn toàn độc lập**:

- `number-utils`: Java library có group/name được khai báo phù hợp.
- `consumer-app`: Java application yêu cầu tọa độ Maven của library, nhưng chỉ vào local source qua `includeBuild`.

Demo không cần deploy một Maven artifact trước và không cần tải một third-party Java library. Các Gradle core plugins vẫn có sẵn trong distribution; yêu cầu Gradle Wrapper và JDK 17 đã cài hoặc được provision phù hợp.

### 4.1. Cấu trúc file

```text
composite-playground/
├── consumer-app/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   ├── gradlew
│   ├── gradlew.bat
│   ├── gradle/wrapper/
│   │   ├── gradle-wrapper.jar
│   │   └── gradle-wrapper.properties
│   └── src/main/java/example/app/App.java
└── number-utils/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/java/example/numbers/Numbers.java
```

Bạn chạy lệnh Gradle **từ `consumer-app/`**, nơi có Wrapper. Nếu mới tạo sandbox chưa có Wrapper, dùng Gradle cài sẵn một lần để tạo bằng `gradle wrapper`, rồi dùng Wrapper. Cần chọn phiên bản Gradle hỗ trợ JDK 17 và Java toolchains; không tự tạo `gradle-wrapper.jar` giả.

### 4.2. Included build: `number-utils/settings.gradle.kts`

```kotlin
rootProject.name = "number-utils"
```

Tên này rất quan trọng: nó là `project.name` của root project trong included build. Gradle sẽ xem project này là nguồn cung cấp module `org.example.math:number-utils` sau khi `group` được cấu hình.

### 4.3. Included build: `number-utils/build.gradle.kts`

```kotlin
plugins {
    `java-library`
}

group = "org.example.math"
version = "1.1.0-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

**Giải thích:**

- `java-library` tạo Java compilation và consumable variants dùng được qua dependency substitution.
- `group = "org.example.math"` là group trong **module identity**.
- `rootProject.name = "number-utils"` cung cấp tên module trong auto substitution.
- `version = "1.1.0-SNAPSHOT"` cho biết phiên bản local project, nhưng nó không bắt consumer phải request đúng version để khớp.
- Java toolchain 17 bảo đảm compiler phù hợp; Java chạy Gradle Daemon có thể là một JDK khác nằm trong Gradle compatibility matrix.
- Không cần `maven-publish` để composite substitution hoạt động. Publishing là một workflow khác.

### 4.4. Included build: `Numbers.java`

Tạo `number-utils/src/main/java/example/numbers/Numbers.java`:

```java
package example.numbers;

public final class Numbers {
    private Numbers() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static String origin() {
        return "LOCAL_SOURCE";
    }
}
```

`Math.addExact` là API Java chuẩn, không có external dependency. `origin()` giúp quan sát chắc chắn app đang chạy local implementation trong demo, không phải một published module có cùng public API.

### 4.5. Consumer build: `consumer-app/settings.gradle.kts`

```kotlin
rootProject.name = "consumer-app"

includeBuild("../number-utils")
```

Đường `../number-utils` được Gradle hiểu **tương đối từ thư mục chứa settings file**. Nó phải trỏ tới thư mục root có `number-utils/settings.gradle.kts`.

Đây là toàn bộ cấu hình cần có cho trường hợp **auto substitution**: không cần block `dependencySubstitution` vì `group:name` khớp.

### 4.6. Consumer build: `consumer-app/build.gradle.kts`

```kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    // Version cố ý KHÁC local project version.
    // Không có Maven repository và không có published 99.99.99.
    implementation("org.example.math:number-utils:99.99.99")
}

application {
    mainClass.set("example.app.App")
}
```

Một điểm có chủ đích: dependency yêu cầu `99.99.99`, nhưng local `number-utils.version` lại là `1.1.0-SNAPSHOT`. Khi `includeBuild` và `group:name` khớp, Gradle thay module bằng **project local**. Nếu bỏ includeBuild, vì demo không khai báo Maven repository và không có published `99.99.99`, resolution sẽ fail. Điều đó minh họa rằng app hoạt động nhờ substitution chứ không phải tải từ network.

Đây là **demo về semantics**, không phải gợi ý dùng `99.99.99` trong product thật. Trong production, dependency version nên có ý nghĩa thực tế; composite chỉ thay source trong local/CI co-development.

### 4.7. Consumer source: `App.java`

Tạo `consumer-app/src/main/java/example/app/App.java`:

```java
package example.app;

import example.numbers.Numbers;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("ORIGIN=" + Numbers.origin());
        System.out.println("SUM=" + Numbers.add(2, 3));
    }
}
```

### 4.8. Chạy demo

Trong thư mục `composite-playground/consumer-app`, Linux/macOS:

```bash
./gradlew --version
./gradlew -q run
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency number-utils --configuration runtimeClasspath
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat -q run
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency number-utils --configuration runtimeClasspath
```

**Stdout chính xác do `App.main` tạo ra:**

```text
ORIGIN=LOCAL_SOURCE
SUM=5
```

Gradle có thể in thêm task information, warnings hoặc báo cáo dependency khi chạy các lệnh khác. Dòng `ORIGIN=LOCAL_SOURCE` xác minh code từ `Numbers` được dùng, trong trường hợp demo không có dependency bên ngoài nào có cùng implementation.

**Khi xem `dependencies`/`dependencyInsight`:** bạn sẽ thấy một request dạng `org.example.math:number-utils:99.99.99` được resolve sang project component của included build `number-utils`. Cú pháp dòng mũi tên và build-tree path cụ thể có thể khác theo Gradle version; **không coi một transcript minh họa là format cố định**. Điều cần kiểm chứng là selected component thuộc **project/included build**, không phải một external module JAR.

### 4.9. Task execution và output trong included build

`./gradlew -q run` cần classes cho `App`; khi Gradle nhận dependency project local, nó cũng xây classes/variant của `number-utils` theo task graph. Trong included build, outputs thường ở:

```text
number-utils/build/classes/java/main/example/numbers/Numbers.class
```

Consumer outputs thường ở:

```text
consumer-app/build/classes/java/main/example/app/App.class
```

Bạn có thể xem một included-build task được chỉ rõ bằng build-tree path, thường là:

```bash
./gradlew :number-utils:compileJava
```

Tên namespace thực tế phải kiểm tra nếu một composite có collision hoặc được đổi `includeBuild { name = ... }`. Ở demo, root included build tên `number-utils`, nên path như trên là cách gọi phù hợp.

### 4.10. Thử nghiệm loại bỏ substitution

Để hiểu sự khác biệt, **trên một bản copy thử nghiệm** có thể bỏ dòng `includeBuild("../number-utils")` khỏi consumer settings rồi chạy:

```bash
./gradlew -q run
```

Kỳ vọng Gradle không thể resolve `org.example.math:number-utils:99.99.99` do không có repository/artifact. Đây là **một thực nghiệm thay đổi settings**, không phải bước bắt buộc trong baseline. Hãy khôi phục `includeBuild` để trở lại demo working.

**Đừng dùng `publishToMavenLocal` để “chữa” demo này**; mục tiêu là xác minh source substitution **không cần publish**.

## 5. Khi auto substitution không xảy ra: nhóm nguyên nhân

Auto mapping dựa vào đúng **`project.group:project.name`** của mỗi project trong included build. Vì vậy các trường hợp sau cần điều tra:

| Trường hợp | Ví dụ | Vì sao tự động không khớp? |
| --- | --- | --- |
| `group` để mặc định | local `undefined:number-utils` | Consumer yêu cầu `org.example.math:number-utils` |
| `project.name` khác Maven artifactId | project name `number-utils`, published artifactId `arithmetic-core` | Mặc định Gradle chỉ thấy `group:number-utils` |
| `groupId` xuất bản khác `project.group` | publication groupId `com.vendor` | Auto rule không đọc tùy chỉnh GAV như một identity mặc định |
| `artifactId` publication khác name | `artifactId="math-api"` | Tọa độ publish khác `project.group:project.name` |
| Nhiều publications từ một project | `math-api`, `math-extensions` | Một default project identity không biểu đạt đầy đủ publications |
| Published configuration không phải default | chỉ công bố custom artifact/variant | Local project target không giống published consumer contract |
| Custom POM/Gradle metadata | relocation, extra capability, POM deps sửa riêng | Substituted project không giống artifact metadata thật |
| Nhầm included project path | target root `":"` vs `":core"` | Rule explicit map sai project cần build |
| Nhầm `include` với `includeBuild` | `include(":number-utils")` ở consumer | Gradle cố tìm subproject trong cùng build, không tự include build độc lập |
| Trong build con chạy độc lập | substitution chỉ khai báo ở consumer settings | Build con không tự biết rule do consumer khai báo |
| Build không nằm trong composite graph | quên `includeBuild` hoặc dùng directory sai | Gradle không inspect local project |
| Plugin ID được request | `plugins { id("...") }` | Plugin resolution và module dependency substitution có cơ chế khác |

### 5.1. Dấu hiệu tên artifact không khớp

Giả sử included project:

```kotlin
// build.gradle.kts
group = "org.example.math"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            artifactId = "arithmetic-api"
            from(components["java"])
        }
    }
}
```

Đây là **đoạn publication minh họa**, chưa phải build script độc lập: cần `java`/`java-library` và `maven-publish`, import `MavenPublication` và repository nếu publish thật.

Published GAV có thể là `org.example.math:arithmetic-api:1.0.0`. Nhưng project vẫn tên `number-utils` nên **auto mapping là `org.example.math:number-utils`**. Muốn consumer yêu cầu `arithmetic-api` mà lấy code local `number-utils`, khai báo explicit substitution trong **including build**.

## 6. Trường hợp cần `dependencySubstitution` tường minh

### 6.1. Cú pháp chính thức trong `settings.gradle.kts`

```kotlin
includeBuild("../number-utils") {
    dependencySubstitution {
        substitute(module("com.vendor:arithmetic-api")).using(project(":"))
    }
}
```

Ở đây:

- `includeBuild("../number-utils")` chọn **included build**.
- `dependencySubstitution` là block thiết lập rules cho build được include.
- `module("com.vendor:arithmetic-api")` là **external module selector** cần thay.
- `using(project(":"))` trỏ đến **root project của chính included build đó**, không phải consumer root project.
- Rule có hiệu lực trong composite do consumer settings định nghĩa, không tự sửa settings của `number-utils`.
- Với selector không kèm version, rule áp dụng cho requests cùng group:name ở những versions phù hợp rule matching; trong demo ta cố ý dùng mapping version-agnostic.

**Khác với dependency substitution trong project build script:**

```kotlin
// Dùng trong build.gradle.kts của MỘT multi-project build,
// không phải thay thế cho cách chỉ project ở included build.
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute(module("org.tools:util")).using(project(":util"))
    }
}
```

Ở ví dụ thứ hai, `project(":util")` chỉ hợp lệ nếu `:util` đã được `include` trong **cùng build**. Nó không thể “nhảy” qua boundary sang project của included build chỉ nhờ cùng tên. Dùng `includeBuild { dependencySubstitution { ... } }` khi target project nằm ở build riêng.

### 6.2. Chuyển demo tự động sang explicit, từng bước

Giữ nguyên **hai build** và Java source `Numbers.java`/`App.java` ở phần 4. Thay đúng hai file:

**Bước A — thay nội dung `consumer-app/settings.gradle.kts`:**

```kotlin
rootProject.name = "consumer-app"

includeBuild("../number-utils") {
    dependencySubstitution {
        substitute(module("com.vendor:arithmetic-api")).using(project(":"))
    }
}
```

**Bước B — thay `dependencies` trong `consumer-app/build.gradle.kts`:**

```kotlin
dependencies {
    // GAV cố ý KHÁC group/name của local project.
    implementation("com.vendor:arithmetic-api:2.0.0")
}
```

Các phần còn lại của `consumer-app/build.gradle.kts` vẫn dùng `application`, Java toolchain 17 và `mainClass="example.app.App"` như phần 4.

**Bước C — chạy lại:**

```bash
./gradlew -q run
./gradlew dependencyInsight --dependency arithmetic-api --configuration runtimeClasspath
```

**Stdout của chương trình Java vẫn là:**

```text
ORIGIN=LOCAL_SOURCE
SUM=5
```

Bởi vì `com.vendor:arithmetic-api` đã được map tường minh sang project `":"` của build `number-utils`. Nếu bỏ rule explicit trong phiên bản này, auto mapping `org.example.math:number-utils` không giúp gì cho dependency `com.vendor:arithmetic-api`.

**Không dán chồng** `includeBuild("../number-utils")` và một includeBuild thứ hai cho cùng directory trong cùng settings: hãy **thay block cũ** bằng block mới. Tương tự chỉ giữ một dependency `implementation(...)` tương ứng khi muốn demo rõ ràng.

### 6.3. Groovy DSL tương đương

Với `settings.gradle` (Groovy DSL):

```groovy
rootProject.name = 'consumer-app'

includeBuild('../number-utils') {
    dependencySubstitution {
        substitute module('com.vendor:arithmetic-api') using project(':')
    }
}
```

Với `build.gradle` ở consumer:

```groovy
dependencies {
    implementation 'com.vendor:arithmetic-api:2.0.0'
}
```

Đoạn này chỉ **minh họa phần cần thay** khi project đã có Java/application plugin. Không đổi từ Kotlin sang Groovy DSL bằng cách đặt thêm `build.gradle` song song với `build.gradle.kts` mà không xác định file Gradle đang dùng.

## 7. Multi-project included build: mỗi module cần map đúng project path

Composite có thể include **cả một multi-project build**, không chỉ một root Java library:

```text
workspace/
├── consumer-app/
│   └── settings.gradle.kts
└── library-suite/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    ├── core/build.gradle.kts
    └── formats/build.gradle.kts
```

Trong `library-suite/settings.gradle.kts`:

```kotlin
rootProject.name = "library-suite"
include(":core", ":formats")
```

Giả sử `:core` và `:formats` đều là Java library projects nhưng các published Maven coordinates khác project names:

- `com.vendor:arithmetic-api` → `:core`.
- `com.vendor:text-formats` → `:formats`.

Trong **consumer-app/settings.gradle.kts**:

```kotlin
rootProject.name = "consumer-app"

includeBuild("../library-suite") {
    dependencySubstitution {
        substitute(module("com.vendor:arithmetic-api"))
            .using(project(":core"))
        substitute(module("com.vendor:text-formats"))
            .using(project(":formats"))
    }
}
```

Đây là **một phương án kiến trúc**, không phải full runnable setup vì `library-suite/core` và `formats` cần actual source, group, plugins và variants. Điểm cốt lõi: `project(":core")`/**`project(":formats")`** ở đây được giải quyết **trong included build `library-suite`**, không phải trong consumer.

Nếu muốn substitution tự động thay vì explicit, đặt group/name của từng included project đúng published coordinates:

```kotlin
// library-suite/core/build.gradle.kts
plugins { `java-library` }
group = "com.vendor"
```

Nhưng tên project hiện là `core`, nên auto mapping vẫn là `com.vendor:core`, **không phải `com.vendor:arithmetic-api`**. Muốn alias bằng tên khác mà không thêm rule, có thể điều chỉnh project names tại settings nếu phù hợp kiến trúc; hoặc duy trì explicit mapping.

### 7.1. Nhiều publications từ cùng một project

Một project đôi khi publish:

```text
com.vendor:arithmetic-api
com.vendor:arithmetic-compat
```

Trong composite, một project có thể được map từ nhiều module selectors:

```kotlin
includeBuild("../number-utils") {
    dependencySubstitution {
        substitute(module("com.vendor:arithmetic-api")).using(project(":"))
        substitute(module("com.vendor:arithmetic-compat")).using(project(":"))
    }
}
```

**Không vội dùng cách này trong production.** Nếu hai publications khác nhau về JAR/classifier/POM/dependencies/capabilities, cùng một default project target **có thể không biểu đạt đúng cả hai**. Explicit substitution giải quyết **identity mapping**, không biến một Java project thành hai published variants với binary semantics giống nhau.

Nên thiết kế tách project/variants đúng hoặc kiểm thử **bản published** độc lập nếu publications khác về nội dung. Tài liệu Gradle cảnh báo rõ các trường hợp published metadata khác project default configuration có thể cho hành vi composite khác remote.

## 8. Trường hợp thiếu `group`: tại sao xuất hiện `undefined:...`?

Nếu included build chỉ có:

```kotlin
plugins {
    java
}
```

và `settings.gradle.kts`:

```kotlin
rootProject.name = "number-utils"
```

thì `project.group` có thể nhận giá trị mặc định `undefined`. Auto identity trở thành `undefined:number-utils`, không khớp với consumer yêu cầu `org.example.math:number-utils`.

**Hai hướng sửa:**

**Hướng A — ưu tiên nếu bạn sở hữu build:** cấu hình đúng group trong included build:

```kotlin
group = "org.example.math"
```

Từ đó auto substitution hoạt động cho group/name khớp cả khi build được dùng ở composites khác; ít cấu hình riêng và dễ hiểu hơn.

**Hướng B — khi không sửa được build:** khai báo mapping tường minh trong consumer settings:

```kotlin
includeBuild("../number-utils") {
    dependencySubstitution {
        substitute(module("org.example.math:number-utils")).using(project(":"))
    }
}
```

Cách này hợp lý khi bạn đang thử một fork/library chưa publish hoặc cần mapping tạm. Nhưng rules đó chỉ thuộc composite của consumer hiện tại; người khác build `number-utils` độc lập **không tự nhận** một group để publish hay resolve dependencies.

**Đừng sửa group chỉ để trùng một dependency alias tạm** nếu điều đó làm đổi chính GAV của thư viện đang publish cho các consumers khác. Tách **identity công bố** khỏi **mapping local tạm thời** có chủ đích.

## 9. Cần dùng binary published thay vì local: tắt global substitution cho một configuration

Composite rất hữu ích khi co-development, nhưng đôi khi bạn muốn so sánh **source local** với **artifact đã publish**.

Ví dụ:

- `runtimeClasspath` phải dùng local `number-utils` để bạn chạy app với thay đổi mới nhất.
- Một `publishedRuntimeClasspath` khác phải resolve đúng version `1.0.0` từ Maven để so sánh ABI/class files hoặc dùng test compatibility.

Theo Gradle, có thể tắt **global dependency substitution rules** trên **một configuration cụ thể**:

```kotlin
// Trong consumer build.gradle.kts.
// Cần repository chứa bản published 1.0.0 để cấu hình này resolve thật.
import org.gradle.api.attributes.Usage

val publishedRuntimeClasspath by configurations.creating {
    isCanBeConsumed = false
    isCanBeResolved = true

    extendsFrom(configurations.runtimeClasspath.get())

    resolutionStrategy.useGlobalDependencySubstitutionRules = false

    attributes.attribute(
        Usage.USAGE_ATTRIBUTE,
        objects.named(Usage.JAVA_RUNTIME)
    )
}
```

**Đoạn trên là một phần mở rộng tùy chọn**, không tự đủ chạy từ số 0 nếu bạn chưa khai báo plugin Java/application, repository và published module. Khi đã có Maven repository chứa dependency, có thể kiểm:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration publishedRuntimeClasspath
./gradlew dependencyInsight --dependency number-utils \
  --configuration publishedRuntimeClasspath
```

Ở `runtimeClasspath`, local included build substitution vẫn hoạt động. Ở `publishedRuntimeClasspath`, global substitution bị tắt nên Gradle có thể resolve published artifact theo module coordinates trong repository đã khai báo.

**Đừng hiểu sai:** `useGlobalDependencySubstitutionRules = false` là lựa chọn **cho một configuration**, không loại bỏ included build khỏi composite, không tự đổi `dependencies` toàn project, cũng không chặn mọi rule explicit tự viết ở nơi khác trong tất cả contexts. Bạn phải kiểm dependency graph đã resolved thực sự.

**Quan trọng cho demo phần 4:** dependency version được cố ý đặt là `99.99.99` và project **không có Maven repository**. Vì vậy configuration published sẽ **không resolve được** cho tới khi bạn dùng version thực sự được publish (ví dụ `1.0.0`) và khai báo Maven repository chứa module đó. Đây là hành vi dự kiến, không phải bug của tùy chọn tắt substitution.

### 9.1. Khi cần kiểm thử đúng bản phát hành

Một lựa chọn đơn giản hơn so với tạo configuration riêng là chạy **một clean CI job không khai báo included build** (hoặc một consumer build độc lập chỉ dùng Maven repository). Khi đó:

1. Consumer yêu cầu đúng GAV release.
2. Maven repository manager cấp POM/Gradle Module Metadata và JAR thực.
3. Dependency verification/locking có thể kiểm soát bytes và versions.
4. Test chạy trên **artifact đã phát hành**, không có local source thay ngầm.
5. Kết quả giúp phát hiện sự khác nhau giữa project default variants và published metadata.

Bài học muốn bạn nhớ cả hai kiểu test: **local source integration** và **published binary compatibility**. Một kiểu không thay thế kiểu kia.

## 10. Tự động và tường minh: thứ tự cân nhắc thiết kế

Khi consumer phụ thuộc một local included project, hãy hỏi theo thứ tự:

1. **Included build đã có `settings.gradle(.kts)` hợp lệ?** `includeBuild` trỏ đúng directory?
2. **Project target có group/name đúng external GAV?** Nếu có, thử auto substitution trước.
3. **Version đang yêu cầu có khác local version?** Điều đó thường **không ngăn** auto mapping theo group/name.
4. **Tên artifact đã tùy chỉnh khi publish?** Nếu published artifactId khác project name, cần explicit mapping.
5. **Có nhiều publications hoặc non-default variants?** Explicit mapping có thể chỉ giải quyết identity, chưa đủ đảm bảo behavior.
6. **Có nhiều project trong included build?** Map đúng `project(":path")` của included build.
7. **Consumer cần bản Maven published?** Dùng configuration không áp global rules hoặc separate non-composite build.
8. **Build cần chạy độc lập?** Đảm bảo included build tự có repositories/Gradle properties/toolchains; không giả định composite settings lan vào nó.
9. **Là Gradle plugin chứ không phải Java library?** Kiểm `pluginManagement.includeBuild`/plugin resolution thay vì chỉ dependency substitution.
10. **Có nguy cơ namespace collision?** Giữ build-tree paths duy nhất và kiểm tên included builds.

### 10.1. Bảng quyết định nhanh

| Tình huống | Cơ chế nên dùng | Lý do |
| --- | --- | --- |
| Included project `group:name` đúng module GAV | `includeBuild("../lib")` | Auto substitution là đủ |
| Project không có group | Đặt group đúng, hoặc explicit substitute | Tránh identity `undefined:name` |
| `artifactId` khi publish khác project name | `includeBuild { dependencySubstitution { ... } }` | Default mapping không biết alias phát hành |
| Maven publication groupId đổi riêng | Explicit substitute hoặc đồng bộ group | GAV khác mặc định |
| Multi-project included build | Auto cho từng project đúng group/name; explicit cho aliases | Target `project(":sub")` |
| Nhiều publications từ một project | Cân nhắc tách project/variants; explicit map khi phù hợp | Default project target có giới hạn |
| So sánh published JAR và local classes | `useGlobalDependencySubstitutionRules=false` trên config riêng | Không muốn global rule thay GAV |
| Chạy một included task không phải dependency | `gradle.includedBuild("...").task(":task")` | Task reference khác project dependency |
| Dùng Gradle plugin từ local build | `pluginManagement { includeBuild("build-logic") }` | Plugin marker/ID resolution |
| Tạm thử local fork | `--include-build ../fork` hoặc includeBuild trong settings | Không cần publish fork |
| Muốn build độc lập để release | Bỏ composite dependency override, resolve Maven GAV thật | Kiểm published artifact |

## 11. Substitution của composite và `resolutionStrategy.dependencySubstitution` khác nhau thế nào?

Bạn có thể gặp API cùng tên trong **hai vị trí**.

### 11.1. Cấp includeBuild (settings) — target ở build khác

```kotlin
// consumer/settings.gradle.kts
includeBuild("../number-utils") {
    dependencySubstitution {
        substitute(module("com.vendor:arithmetic-api")).using(project(":"))
    }
}
```

Đây là cách đặt rule cho **included build**. `project(":")` được hiểu trong **context của included build**.

### 11.2. Cấp configuration (project build script) — target cùng build

```kotlin
// Trong một multi-project build có include(":app", ":util").
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute(module("com.vendor:util"))
            .using(project(":util"))
            .because("Use an unpublished local util project")
    }
}
```

Đây là rule **trong configurations của build hiện tại**. `project(":util")` phải hiện diện trong project hierarchy hiện tại. Nó **không tự include** một external build hoặc thay một project path nằm ngoài settings.

### 11.3. Có thể đổi project dependency thành module không?

Trong một multi-project build, Gradle cũng hỗ trợ:

```kotlin
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute(project(":util"))
            .using(module("com.vendor:util:1.3.0"))
    }
}
```

Đây là **mẫu khác**, dùng khi một project trong cùng build được thay bằng binary remote để tăng tốc hoặc so sánh. Phải có module version thực và repository phù hợp. Đừng áp dụng nó để “tắt” included-build global substitution nếu mục tiêu chỉ là kiểm published artifact: khi đó thường dùng `useGlobalDependencySubstitutionRules=false` theo configuration.

## 12. Không được dùng `project(":included-build")` qua ranh giới build

Một anti-pattern phổ biến:

```kotlin
// consumer-app/build.gradle.kts
dependencies {
    // SAI nếu number-utils là root project của included build,
    // không phải subproject của consumer-app:
    implementation(project(":number-utils"))
}
```

Gradle có thể báo `UnknownProjectException` hoặc `Project with path ... could not be found`. Lỗi này **không giải quyết** bằng cách đổi tên artifact file hoặc project version.

Thay đúng:

```kotlin
dependencies {
    implementation("org.example.math:number-utils:1.0.0")
}
```

và:

```kotlin
// consumer-app/settings.gradle.kts
includeBuild("../number-utils")
```

Sau đó Gradle tự mapping nếu group/name phù hợp. Nếu không, khai báo explicit substitution trong `includeBuild` như phần 6.

**Tại sao Gradle thiết kế vậy?** Included build là một **build độc lập** có settings graph riêng. Module coordinates là hợp đồng mà các builds dùng để tham chiếu nhau, tương tự cách consumers bên ngoài yêu cầu artifacts trong Maven repository.

## 13. Included builds không chia sẻ cấu hình ngầm

Ví dụ consumer có:

```kotlin
// consumer-app/build.gradle.kts
repositories {
    mavenCentral()
}
```

Không có nghĩa build `number-utils` tự nhận cùng `mavenCentral()`. Nếu `number-utils` có dependency bên ngoài, cần khai báo repositories **trong chính build đó** hoặc theo cơ chế cấu hình chung được hỗ trợ.

Tương tự:

- `gradle/libs.versions.toml` của consumer không tự sinh `libs` accessors trong included build.
- `gradle.properties` ở root consumer chứa user-defined property không tự thành property riêng trong included build.
- `pluginManagement.repositories` của consumer không tự cấu hình plugin repositories cho mọi included build.
- `java.toolchain=17` trong consumer không buộc compiler của library build cũng dùng 17.
- Chỉ có cùng parent directory trên filesystem không biến hai builds thành một multi-project.
- Build logic plugins trong `build-logic` phải được setup theo included build/plugin management semantics riêng.

**Cách quản lý:** mỗi build nên tự chạy `./gradlew build` hoặc chạy bằng Wrapper tương thích của workspace/CI; xác định shared conventions/versions một cách có chủ đích. Với credentials, dùng CI secret injection/environment hoặc user-home config theo policy, không copy token vào nhiều Gradle files.

### 13.1. Lệnh kiểm tra included build độc lập

Từ `composite-playground/number-utils`, có thể dùng Gradle Wrapper tương thích được chuẩn bị riêng hoặc đi đường từ consumer:

```bash
cd ../consumer-app
./gradlew :number-utils:build
```

Task path ở ví dụ này dùng build-tree name `number-utils`. Nó cho phép chạy task của included build từ composite root, **không có nghĩa `number-utils` là subproject**. Nếu build con có Wrapper riêng, cũng có thể `cd ../number-utils && ./gradlew build` để xác nhận isolation.

### 13.2. Build tree paths phải duy nhất

Khi nhiều included builds có tên thư mục giống nhau hoặc trùng path với root subproject, Gradle có thể báo collision. Có thể đổi build identity tại include:

```kotlin
includeBuild("../number-utils") {
    name = "local-number-utils"
}
```

Đây là **một phương án thay thế** cho auto include trong demo nếu thực sự cần tránh namespace clash. Nó thay đổi **build-tree path để gọi task**, không tự đổi Java `project.group` hoặc Maven `artifactId`, và không tự chữa sai group/name.

Để khớp module, vẫn phải đảm bảo `project.group:project.name` hoặc explicit mapping.

## 14. Plugin build logic: đừng nhầm plugin resolution với library substitution

Composite builds cũng thường dùng để phát triển Gradle plugins/convention plugins, ví dụ:

```text
my-app/
├── settings.gradle.kts
├── build.gradle.kts
└── build-logic/
    ├── settings.gradle.kts
    └── build.gradle.kts
```

Nếu muốn **settings plugin** hoặc Gradle plugin dùng trong `plugins { }`, Gradle hướng dẫn:

```kotlin
// settings.gradle.kts
pluginManagement {
    includeBuild("build-logic")
    repositories {
        gradlePluginPortal()
    }
}
```

Sau đó application project có thể:

```kotlin
plugins {
    id("company.java-conventions")
}
```

Đây là **mẫu kiến trúc**, chưa runnable vì bạn còn phải định nghĩa một Gradle plugin với ID `company.java-conventions` trong `build-logic` và publish/setup plugin declaration đúng.

**Sự khác nhau:**

- `implementation("org.example.math:number-utils:...")` cần **module dependency substitution**.
- `plugins { id("company.java-conventions") }` cần **plugin resolution**, có thể qua `pluginManagement.includeBuild`.
- `includeBuild("build-logic")` ở settings thường dùng cho project build logic; với settings plugins phải dùng `pluginManagement.includeBuild`.
- Không suy rằng một build được include để resolve Gradle plugin cũng là Java library dependency mà mọi `implementation(...)` tự động thấy theo plugin ID.
- Đừng dùng `project(":build-logic")` để cross-build apply plugin.

Bài này ưu tiên **module substitution** cho Java libraries. Plugin resolution nên được xử lý theo đúng Gradle plugin development workflow.

## 15. Case study: fork của một thư viện đã publish với tọa độ không tương thích

Giả sử công ty sử dụng:

```text
com.partner:validation-core:3.2.0
```

Bạn clone source fork thành Gradle build:

```text
../validation-fork/
  settings.gradle.kts  -> rootProject.name = "validation-fork"
  build.gradle.kts     -> group = "com.myteam"
```

Auto identity thành `com.myteam:validation-fork`, không trùng Maven GAV cũ. Nhưng bạn muốn test app với patched source **mà không sửa dependencies** ở hàng chục modules.

Trong consumer settings:

```kotlin
includeBuild("../validation-fork") {
    dependencySubstitution {
        substitute(module("com.partner:validation-core"))
            .using(project(":"))
    }
}
```

Giữ nguyên dependency ở các project consumer:

```kotlin
dependencies {
    implementation("com.partner:validation-core:3.2.0")
}
```

Nếu fork vẫn công bố một Java-consumable project variant tương thích, Gradle sẽ chọn patched local source. Tất cả project trong **composite context** request module khớp có thể được ảnh hưởng — vì thế đây là cơ chế mạnh, cần review phạm vi.

**Quan trọng:** không nên commit local absolute paths hoặc mapping fork vào production release settings khi chỉ nhằm thử cá nhân. Dùng một checkout layout có thể tái lập hoặc bật mapping qua branch/dev-only policy rõ ràng. CI release cần kiểm published binary thật khi mục tiêu là tái hiện Maven artifact.

### 15.1. “Đổi dependency version sang fork version” không đủ

Nếu consumer đổi:

```kotlin
implementation("com.partner:validation-core:3.2.1-SNAPSHOT")
```

nhưng fork vẫn `group=com.myteam` và `name=validation-fork`, **auto substitution không xảy ra**. Version mới không giúp group/name match. Cần thay đúng identity của included project hoặc explicit mapping.

### 15.2. Kiểm chứng có đang chạy fork không

Có thể:

- Chạy `dependencyInsight` cho module để thấy project selected.
- Thêm unit test của bug đã sửa chỉ pass trên fork.
- Dùng một API hoặc behavior kiểm chứng sự thay đổi cụ thể, không thêm code “print fork” vào production tùy tiện.
- So task graph để chắc included build compile task có chạy.
- Chạy kiểm thử với **published module không substitution** để đối chiếu; nếu kết quả giống nhau, xem lại case có thực sự exercise code đã sửa.

Không kết luận chỉ bằng `BUILD SUCCESSFUL`, vì module fork có thể không được chọn hoặc app không đi vào code path cần test.

## 16. Composite substitution và version catalogs / dependency locking

### 16.1. Version catalog alias vẫn chỉ là module selector

Trong `gradle/libs.versions.toml`:

```toml
[versions]
numberUtils = "1.0.0"

[libraries]
number-utils = {
    module = "org.example.math:number-utils",
    version.ref = "numberUtils"
}
```

Trong Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation(libs.number.utils)
}
```

**Chú ý về TOML:** nếu muốn đặt inline table qua nhiều dòng, TOML phải tuân đúng cú pháp. Để dùng luôn trong build thật, viết một dòng:

```toml
[libraries]
number-utils = { module = "org.example.math:number-utils", version.ref = "numberUtils" }
```

Version catalog làm các aliases và requested coordinates nhất quán, nhưng **không chặn substitution**. Alias vẫn là một external module dependency; khi group/name khớp included project, Gradle có thể thay component bằng source local.

### 16.2. Dependency locking có đủ chặn substitution không?

Dependency locking giúp cố định selected **external module versions** theo configurations. Composite substitution lại thay external module selection thành **project component**. Vì vậy lock state không nên được coi là bằng chứng bạn đang chạy đúng published binary; phải nhìn resolved graph và kiểm CI không include local build khi cần kiểm release.

Không chỉnh lockfiles tùy tiện chỉ để “chữa” composite mismatch; xác định có đang tiêu thụ local project hay external module trước.

### 16.3. Dependency verification

Gradle dependency verification dùng checksum/PGP metadata để kiểm artifacts **được tải từ repositories**. Một local project được build từ source không giống tải binary JAR đã được review/checksum từ Maven. Substitution có thể chuyển nguồn code được thực thi mà không đi qua cùng kiểm tra external artifact ấy.

Để an toàn:

1. Chỉ include trusted source builds.
2. Review fork/commit và Gradle scripts/plugins của included build.
3. Chạy tests trên composite **và** published release binary.
4. Dùng dependency verification với external artifacts khi appropriate.
5. Pin Gradle Wrapper/toolchains và CI environment.

## 17. Giới hạn quan trọng: publication metadata và project default configuration có thể khác nhau

Tài liệu Gradle nêu rằng **substituted project dependency** tham chiếu **default configuration** của project target theo model composite; nếu artifacts/dependencies/capabilities được publish khác nội dung default, hai cách resolve có thể tạo kết quả khác nhau.

Ví dụ:

- `maven-publish` custom POM dependencies khác project dependencies thực.
- Publication thêm một artifact đặc biệt nhưng project default target không mang artifact đó.
- Một project có nhiều publications với các coordinates/capabilities khác nhau.
- Published module chỉ export custom variant hoặc custom classifier.
- Metadata `.module` công bố capability/feature variant không có ở project target.
- Một plugin publish relocation hoặc sửa POM dependency scopes riêng.
- JAR phát hành đã được shade/relocate nhưng local Java project output chưa shade.

**Explicit substitution chỉ sửa module identity**, không tự sao chép toàn bộ Maven POM, Gradle Module Metadata hay custom publication semantics vào project. Điều này có thể dẫn đến:

- Consumer biên dịch với local project nhưng release JAR có ABI khác.
- Local compilation thành công nhưng published binary thiếu class hoặc khác dependencies.
- Một capability/variant được yêu cầu trên published module không được local project cung cấp.
- Local tests xanh nhưng dependency graph trên clean CI release khác.

**Cách xử lý:** đảm bảo Java components/variants thực sự tương thích, không chỉ group/name; test `publishToMavenLocal`/file-based repository rồi chạy consumer độc lập; nếu cần hoàn toàn giống binary release thì tắt substitution cho configuration/job tương ứng.

### 17.1. Vì sao custom `archiveBaseName` cũng đáng chú ý?

Nếu Java JAR tên `arithmetic-api-1.0.0.jar` nhưng project name là `number-utils`, không thể suy default mapping dựa vào file name. Tùy build, archive naming có thể gắn với publication artifact coordinates. Tài liệu Gradle liệt kê customized archive name và publication name mismatch là những tình huống có thể cần explicit substitutions.

Tuy nhiên đổi `archiveBaseName` **không tự thay `project.name`**. Hãy xét đúng `MavenPublication.groupId/artifactId` và `project.group/name`, không chỉ nhìn tên file trong `build/libs`.

## 18. Composite builds không tự tạo một “super-project” chung

Một composite root có thể có nhiều builds:

```text
workspace/
├── root/settings.gradle.kts
├── api/settings.gradle.kts
├── core/settings.gradle.kts
└── app/settings.gradle.kts
```

Bạn có thể include các builds:

```kotlin
rootProject.name = "composite-root"

includeBuild("../api")
includeBuild("../core")
includeBuild("../app")
```

Đây là **mẫu bố cục**, cần điều chỉnh các relative paths theo nơi `root/settings.gradle.kts` nằm. Các builds vẫn có settings/repositories/properties và tasks riêng.

Không thể tự coi project `api` trong included build như `project(":api")` của root. Khi cần chỉ định một task ở included build, dùng:

```kotlin
tasks.register("verifyApi") {
    dependsOn(gradle.includedBuild("api").task(":check"))
}
```

Đây là **cross-build task dependency**, không phải module substitution. Nó cho biết task nào chạy, nhưng không tự thêm `api` vào `runtimeClasspath` của ứng dụng. Muốn consume Java API, phải có `implementation("group:name:version")` và mapping/variants phù hợp.

### 18.1. Tên included build và namespace collisions

Gradle đòi hỏi các build-tree project identities duy nhất. Hai included builds có cùng build path hoặc trùng với path của project root có thể fail. Trong settings, có thể đặt:

```kotlin
includeBuild("../api") {
    name = "local-api-source"
}
```

Đây là alias build-tree path cho included build, **không** phải một Maven module alias tự động. Với composite lớn, đặt tên rõ và kiểm `./gradlew projects`/task graph thay vì sửa group/module identity chỉ để né collision.

### 18.2. Self-inclusion của main build

Mặc định, Gradle tạo auto substitutions cho **included builds**, không tự coi main build là một included build cung cấp mọi projects của nó cho các included builds khác. Theo Gradle, có thể dùng **self-inclusion**:

```kotlin
// settings.gradle.kts của main build, khi có nhu cầu thực sự:
includeBuild(".")
```

Khi đó main build có thể tham gia substitution identity bằng chính group/name projects của nó. Đây là **tính năng nâng cao**, có thể gây ambiguity nếu names trùng. Không thêm `includeBuild(".")` vào demo tự động phần 4; consumer không cần self-inclusion để thấy `number-utils`.

## 19. Performance và configuration-on-demand

Để tạo auto substitution rules, Gradle cần xác định group/name các projects của included build. Với included build nhiều modules, Gradle có thể phải **configure toàn bộ projects** để khám phá chúng. Khi dùng explicit rules, Gradle có thể biết mapping mà không cần inspect mọi project ngay từ đầu.

Theo tài liệu Gradle, với **Configuration-on-Demand** (tính năng có giới hạn cần cân nhắc):

- Default substitutions đòi Gradle inspect projects để nhận diện coordinates, thường gây configuration cost cao.
- Explicit substitutions có thể giảm cấu hình không cần thiết, nhưng bạn **phải khai báo tất cả mappings muốn sử dụng** trong context đó.
- Project không được mapping tường minh có thể bị xem như external dependency khi relying vào this mode.
- Đây không phải lý do để mặc định bật Configuration-on-Demand cho mọi dự án; tương tác với composite và correctness phải được test.

Một bảng cân nhắc:

| Mô hình | Chi phí cấu hình | Rủi ro |
| --- | --- | --- |
| Single included build với 1–2 projects, auto match | Thường đơn giản | Dễ bỏ sót name/group mismatch |
| Included build hàng chục modules, auto discovery | Có thể cấu hình nhiều projects | Startup/configuration time |
| Explicit mappings cho các modules cần dùng | Có thể giảm discover cost | Dễ thiếu mapping khi thêm module mới |
| Composite với nhiều fork aliases | Mappings cần review kỹ | Thay nhầm module trên classpath |
| Composite trùng publication variants | Không chỉ performance | Semantic mismatch giữa local và published |

Tối ưu theo **đo lường Gradle build performance/profile** và kết quả dependency graphs. Đừng sửa rules chỉ để giảm thời gian cấu hình rồi làm CI âm thầm dùng external artifact thay local source.

## 20. Những lỗi thường gặp và hướng khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Consumer vẫn tải Maven JAR thay vì local | `group:name` không khớp hoặc chưa include đúng build | Đọc project.group/name, includeBuild path, dependencyInsight |
| `Could not find org.example.math:number-utils:...` | Không có substitution phù hợp và repository không có module | Sửa group/name hoặc explicit mapping; kiểm source path |
| `UnknownProjectException` tại `project(":number-utils")` | Dùng project path của included build trong consumer | Dùng module notation + includeBuild |
| `Project with path ':' not found` trong explicit mapping | Target included project path không đúng hoặc build không có root Java component | Kiểm `includeBuild { project(":") }` và included settings |
| `No matching variant of project ... was found` | Local project không cung cấp Java variant consumer yêu cầu | Áp Java Library/Java plugin; kiểm attributes/capabilities |
| Local module group là `undefined` | Quên cấu hình `group` | Đặt group đúng hoặc explicit mapping |
| Đổi version nhưng local project vẫn được chọn | Auto substitution match group/name, không dựa version | Đây là expected behavior; tắt substitution nếu cần binary |
| Đổi `artifactId` ở `maven-publish`, auto không chạy | Project name khác published artifactId | Explicit module→project mapping |
| Có nhiều publications, app nhận sai variant | Một default project target không mô phỏng publication metadata | Chỉnh variants, tách projects hoặc test published binary |
| Config substitution chỉ có ở consumer, included build test riêng fail | Rules không tự lan giữa builds | Cấu hình từng build cần thiết hoặc align group/name |
| Included build thiếu Maven Central | Repositories không chia sẻ ngầm | Khai báo trong included build |
| Included build không thấy `libs.xxx` catalog | Catalog của consumer không tự thừa kế | Import/define catalog cho included build riêng |
| `implementation(project(":lib"))` fail khi lib là included build | Cross-build project notation sai | Dùng GAV + includeBuild |
| `plugins { id("company.foo") }` không tìm thấy | Plugin resolution khác module substitution | `pluginManagement { includeBuild("build-logic") }` nếu là local plugin build |
| `dependencyInsight` không thấy module GAV như mong đợi | Có conflict/other mapping/variant hoặc query sai | Kiểm full `dependencies` và configuration chính xác |
| `runtimeClasspath` local, `publishedRuntimeClasspath` fail | Chưa có Maven repository/version thật, đã tắt global rules | Cấp repository + valid published GAV |
| `run` pass trong composite, CI release fail | Local source khác released JAR/POM | Test external consumer không includeBuild |
| Build-tree path collision | Hai builds/projects cùng namespace | `includeBuild { name = ... }` hoặc đổi project layout |
| `--include-build` works CLI nhưng IDE không nhất quán | CLI flag không nằm trong checked-in settings | Đưa includeBuild vào settings khi cần stable setup |
| Compilation chậm với nhiều included projects | Auto discovery/configuration overhead | Profile; explicit mappings khi có lợi |
| Task executed lại dù source không đổi | Cache/inputs/tasks khác nhau hoặc build contexts | Kiểm Gradle task outcomes, build cache, configuration cache |
| Checksum verification không báo cho local source | Không tải external artifact vì substitution | Review source/build logic, kiểm published artifact riêng |

### 20.1. Quy trình debug sáu bước

1. **Xác nhận build tree:** settings của consumer có `includeBuild("../number-utils")`, path tồn tại, included settings hợp lệ.
2. **Kiểm mapping identity:** `project.group` và `project.name` của target, Maven GAV consumer yêu cầu.
3. **Kiểm selected component:** chạy `./gradlew dependencies --configuration runtimeClasspath` và `dependencyInsight`.
4. **Kiểm compilation/task graph:** chạy `./gradlew run --info` hoặc `./gradlew :number-utils:compileJava`, xem local build có task thực thi không.
5. **Nếu explicit:** kiểm `module("group:name")` và `using(project(":path"))` bên trong đúng `includeBuild`; target path là path của included build.
6. **Nếu published metadata khác:** thử tắt global rule trên configuration riêng hoặc chạy external consumer clean, so ABI/classpath/artifacts.

Không chỉ dùng `--refresh-dependencies` để sửa một lỗi **mapping group/name**. Refresh repo metadata không giúp Gradle nhận diện một local project có identity sai.

## 21. CI và release: khi nào nên bật/tắt composite?

### 21.1. Co-development CI

Một CI job tích hợp nhiều repositories có thể:

```text
Checkout consumer-app và number-utils cùng workspace layout
      |
Dùng Gradle Wrapper/Java 17 tương thích
      |
consumer-app/settings.gradle.kts includeBuild("../number-utils")
      |
Gradle resolves org.example.math:number-utils -> local project
      |
compile/test application và library outputs
      |
Báo cáo dependency graph + tests, không cần publish local JAR
```

**Ưu điểm:** test code mới nhất của hai repositories cùng nhau, phát hiện API breaking change trước publication.

**Điều cần ghi lại:** commit SHA của **cả hai** builds. Nếu chỉ ghi SHA consumer rồi included build lấy branch HEAD khác, không thể tái tạo kết quả CI một cách đáng tin.

### 21.2. Release/consumer compatibility CI

Một job khác nên:

1. Build/publish candidate artifact vào sandbox Maven repository hoặc dùng approved release staging repository.
2. Chạy **consumer độc lập**, không include source build cho module đó.
3. Resolve đúng GAV/version từ repository.
4. Dùng dependency verification/locking theo policy.
5. Chạy tests/compatibility checks với binary/metadata thực tế.
6. Xác minh artifact bytes, POM, Gradle Module Metadata và transitive deps.
7. Chỉ promote/publish release sau approval và checks đầy đủ.

Điều này tránh vấn đề “composite chạy tốt nên chắc Maven artifact cũng tốt” khi custom publication và default project variants khác nhau.

### 21.3. Đừng để local substitution lén bật trong production

- Không để `includeBuild("../my-personal-fork")` cố định vào production settings nếu đường path là riêng máy developer.
- Không dùng absolute paths như `C:\Users\someone\workspace\...` hoặc `/Users/someone/...` trong repository.
- Nếu cần opt-in local fork, dùng Gradle property/environment với policy rõ, validate path và review CI.
- Release pipeline nên có artifact provenance và kiểm selected components thật.
- Nếu direct CLI `--include-build` dùng cho dev, document rằng nó thay dependency resolution khi chạy.
- Không thay composite binary check bằng `publishToMavenLocal` không kiểm metadata production.

## 22. Bài tập thực hành thêm

### Bài 1 — Sửa source để thấy local substitution

Từ demo baseline, đổi:

```java
public static String origin() {
    return "LOCAL_PATCH";
}
```

Chạy `./gradlew -q run` trong consumer. Kỳ vọng:

```text
ORIGIN=LOCAL_PATCH
SUM=5
```

Không cần publish Maven JAR. Điều này là bằng chứng trực tiếp code local thay đổi được consume qua composite.

### Bài 2 — Sửa group cho sai

Đổi `number-utils`:

```kotlin
group = "org.different"
```

Consumer vẫn request `org.example.math:number-utils:99.99.99`. Không có explicit mapping/repository, resolution sẽ fail. Khôi phục `group` hoặc khai báo correct explicit substitute. Đừng sửa version để cứu group mismatch.

### Bài 3 — Đổi published artifactId nhưng giữ project name

Dùng `maven-publish` để publish `org.example.math:arithmetic-api` từ project vẫn tên `number-utils`. Consumer yêu cầu `arithmetic-api`. Quan sát auto substitution không nhận dạng alias đó; thêm rule explicit tới `project(":")`. Phân biệt publication coordinates và project identity.

### Bài 4 — Thử published binary

Publish hoặc có sẵn `org.example.math:number-utils:1.0.0` trong một Maven repository, rồi tạo `publishedRuntimeClasspath` tắt global rules như phần 9. Chạy `dependencies` trên hai configurations; xác nhận một bên project local, một bên external module. Không dùng version giả `99.99.99` khi muốn thử published artifact.

### Bài 5 — Multi-project mapping

Tạo included build với subprojects `:core` và `:formats`. Đặt explicit rules tới hai target project paths tương ứng. Thêm unit tests cho hai APIs trong consumer. Kiểm `dependencyInsight` và tasks thuộc included builds. Đừng dùng `project(":core")` trực tiếp ở consumer dependencies khi `core` không nằm trong consumer build.

## 23. Câu hỏi tự kiểm tra

1. **`include` và `includeBuild` khác nhau ở đâu?** `include` tạo subprojects trong cùng build; `includeBuild` thêm một build độc lập vào composite.
2. **Auto substitution dựa vào thông tin nào?** `project.group:project.name` của projects trong included build.
3. **Version local `1.1.0-SNAPSHOT` có phải bằng consumer request `1.0.0`?** Không bắt buộc để auto mapping theo group/name.
4. **Khi nào `MavenPublication.artifactId` khiến cần explicit mapping?** Khi artifactId được publish không bằng `project.name`.
5. **Không đặt group thì auto identity thế nào?** Thường là `undefined:project-name`, không khớp GAV mong đợi.
6. **Tại sao `implementation(project(":number-utils"))` sai với included build?** Project path không đi qua build boundary; cần module dependency rồi substitution.
7. **`substitute(module("com.vendor:arithmetic-api")).using(project(":"))` trỏ tới root nào?** Root project **của included build** trong settings block đó.
8. **Có cần publish vào Maven local trước khi auto substitution?** Không.
9. **Explicit substitutions có tự áp dụng cho build con chạy độc lập không?** Không; rules được khai báo trong composite context không tự lan sang mọi build khác.
10. **Tắt global substitution ở đâu để vẫn giữ local cho runtimeClasspath khác?** Trên `resolutionStrategy.useGlobalDependencySubstitutionRules=false` của một configuration riêng.
11. **Tắt substitution có khiến Gradle tự tải binary `99.99.99` không?** Chỉ nếu module/version thật tồn tại trong repository được cấu hình.
12. **Cùng một project publish hai JAR khác nhau, explicit mapping hai GAV tới một project là đủ chưa?** Không chắc; default target có thể không khớp từng publication metadata/artifact.
13. **Build con có tự dùng repositories của consumer không?** Không; mỗi build có cấu hình độc lập.
14. **Dùng `pluginManagement.includeBuild` cho gì?** Resolve Gradle plugins được cung cấp từ local plugin build.
15. **`dependencyInsight` giúp xác nhận điều gì?** Module selector đã resolve tới project component hay external artifact trong một configuration.
16. **Vì sao phải test published binary riêng?** Vì local project variants/classpath có thể khác POM/module metadata và packaged artifacts đã publish.
17. **`includeBuild(".")` dùng khi nào?** Khi muốn main build tự tham gia substitution identity như một included build; không cần trong demo thông thường.
18. **Có thể có nhiều included builds trùng build path không?** Không; composite cần identities duy nhất.
19. **Dùng configuration-on-demand với auto discovery luôn nhanh hơn explicit rules?** Không; auto discovery có thể cần cấu hình nhiều projects.
20. **Nếu build local sửa code nhưng app vẫn in kết quả cũ, kiểm gì trước?** Selected component trong `dependencyInsight`, task outcomes, classpath, code path và includeBuild/group/name.

## 24. Checklist trước khi merge composite configuration

- [ ] `includeBuild` trỏ đúng **root directory của included build**, không phải một subproject folder không có settings.
- [ ] Biết chính xác module coordinates consumer đang request.
- [ ] `project.group` và `project.name` của included project khớp khi dùng auto substitution.
- [ ] Nếu publication groupId/artifactId khác default identity, đã viết explicit mapping đúng.
- [ ] Nếu nhiều included subprojects, `project(":path")` target ở đúng included build.
- [ ] Không dùng `implementation(project(":external-build"))` qua build boundary.
- [ ] Không trông đợi phiên bản Maven request khớp local project version để substitution xảy ra.
- [ ] Test `dependencyInsight` xác nhận project local khi cần co-development.
- [ ] Có test/CI riêng dùng **published binary** khi release metadata quan trọng.
- [ ] External repositories và toolchains của mỗi included build được cấu hình độc lập.
- [ ] Với build logic/plugins, xử lý `pluginManagement.includeBuild` đúng mục đích.
- [ ] Với multiple publications/custom capabilities/variants, đánh giá khả năng default project target không tương đương published module.
- [ ] Không dùng `--refresh-dependencies` thay cho sửa group/name mapping.
- [ ] Đảm bảo build-tree paths unique, tránh collisions.
- [ ] Nếu dùng Configuration-on-Demand, đánh giá chi phí auto discovery và mapping coverage.
- [ ] Ghi lại commit SHA của mọi included source builds trong CI.
- [ ] Không commit đường dẫn tuyệt đối hoặc local fork không tin cậy vào release settings.
- [ ] Có Gradle Wrapper/JDK tương thích, test trên môi trường sạch.
- [ ] Khi cần tắt substitutions để so artifact, chỉ tắt trên configuration/job chủ đích.
- [ ] Không coi một lần `BUILD SUCCESSFUL` trong composite là bằng chứng publication Maven hoàn toàn tương đương.

## 25. Ghi nhớ

- **Composite build gồm các Gradle builds độc lập**. `includeBuild` khác `include`, và `project()` không vượt ranh giới build.
- **Auto substitution dựa vào `group:name` của project**, không tự lấy GAV đặc biệt trong `maven-publish` và không yêu cầu phiên bản consumer giống `project.version`.
- **Khi group/name lệch, dùng explicit mapping** trong `includeBuild { dependencySubstitution { substitute(module("g:a")).using(project(":path")) } }`.
- **Tên file JAR, archiveBaseName, Maven artifactId và project.name không phải một giá trị bắt buộc trùng nhau**.
- **Rules không tự lan tới mọi build context**, và các included builds không tự kế thừa repositories/version catalogs/Gradle properties của consumer.
- **Local project substitution không bảo đảm giống published artifact** nếu publications/variants/POM/capabilities khác default configuration.
- **`useGlobalDependencySubstitutionRules=false`** trên configuration riêng cho phép kiểm external binary mà không xóa toàn composite.
- **`dependencyInsight` + task graph + integration tests** là bộ công cụ xác minh substitution thực sự.
- **CI cần cả test source integration và test Maven publication** khi phát hành artifact.
- **Plugin resolution là câu chuyện khác**: `pluginManagement.includeBuild` cho Gradle plugins.

## Tài liệu chính thức

- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): `includeBuild`, automatic substitutions từ `group:name`, explicit mappings, self-inclusion, disabling substitutions, publication limitations, build-tree paths.
- [Gradle — Dependency Resolution Rules](https://docs.gradle.org/current/userguide/dependency_management.html): `resolutionStrategy.dependencySubstitution` trong configurations, module→project và project→module.
- [Gradle — ConfigurableIncludedBuild.dependencySubstitution API](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.initialization/-configurable-included-build/dependency-substitution.html): Kotlin DSL API dành cho included build substitutions.
- [Gradle — Settings.includeBuild API](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.initialization/-settings/include-build.html): included build root directory và configuration action.
- [Gradle — Structuring and Organizing Gradle Projects](https://docs.gradle.org/current/userguide/organizing_build_logic.html): multi-project vs composite và build logic separation.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): GAV, custom artifactId, POM/Gradle Module Metadata, publications.
- [Gradle — Viewing/Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependency report/`dependencyInsight`.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): Java variants, consumable configurations và binary API/runtime dependencies.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): included build build logic, isolation, buildSrc differences.
