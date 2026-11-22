# Khai báo include và ánh xạ projectDir trong settings của Gradle

Trong một **multi-project build**, Gradle phải biết những project nào thuộc cùng một build, tên/đường dẫn logic của từng project, và **thư mục vật lý** chứa build script cùng mã nguồn. Mọi thông tin này được khai báo ở **`settings.gradle`** (Groovy DSL) hoặc **`settings.gradle.kts`** (Kotlin DSL) trước khi Gradle đánh giá build script của các project.

Ở cấu trúc đơn giản, `include 'app'` vừa tạo project `:app` vừa mặc định trỏ tới thư mục `app/`. Nhưng trong một monorepo thật, nhóm có thể muốn project path là `:services:api` dù source nằm tại `components/backend/api-gateway/`, hoặc project `:core` dù source nằm tại `modules/domain-core/`. Khi ấy cần phân biệt rõ:

- **`include`** đăng ký **project identity và logical hierarchy** trong cùng một build.
- **`project(':path').projectDir = file('...')`** xác định **directory thực tế** của project đã được include.
- **`project(':path')` trong `dependencies {}`** yêu cầu một **project dependency**, không phải một đường dẫn filesystem.
- **`includeBuild`** gắn một **build độc lập** vào composite build; không đồng nghĩa `include`.

Bài học thuộc nhóm **Build nhiều dự án** của **Build Tool Gradle**, với chủ đề trực tiếp **“Khai báo include và ánh xạ projectDir trong settings”**. Nội dung trình bày từ cách Gradle dựng project graph, ánh xạ path, project cha, điều kiện directory ở Gradle 9+, đến ví dụ Java 17 hoàn chỉnh gồm ba module có directories không trùng với project paths, Groovy/Kotlin DSL, cách kiểm chứng bằng Wrapper và các lỗi thường gặp.

## 1. Những khái niệm cần phân biệt

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Build** | Root chứa `settings.gradle` và Wrapper | Đơn vị có settings, root project, task graph. |
| **Root project** | `:` | Project gốc luôn tồn tại; `rootProject.name` có thể đặt tên ổn định. |
| **Subproject** | `:core`, `:services:api` | Project được thêm bằng `Settings.include` vào cùng build. |
| **Project path** | `:services:api` | Địa chỉ logic trong cây project; dùng khi gọi task và project dependencies. |
| **Project name** | `api` | Phần tên cuối của path logic. |
| **Project descriptor** | `project(':services:api')` trong settings | Metadata project trước khi Project object được thiết lập. |
| **Project directory** | `components/api-gateway` | Directory vật lý của build script, sources, resources và default build output. |
| **Build directory** | `components/api-gateway/build` | Output của tasks; khác `projectDir`. |
| **Included build** | `includeBuild('build-logic')` | Một build riêng trong composite build, khác subproject. |

Một ví dụ ngắn:

```groovy
rootProject.name = 'learning-platform'
include ':core', ':services:api'

project(':core').projectDir = file('modules/domain-core')
project(':services:api').projectDir = file('components/api-gateway')
```

Kết quả logic:

```text
:
├── :core
└── :services
    └── :services:api
```

Kết quả filesystem:

```text
learning-platform/
├── settings.gradle
├── modules/domain-core/
├── services/
└── components/api-gateway/
```

Đường dẫn logic `:services:api` không bắt buộc nằm tại `services/api`. Tuy nhiên project cha `:services` được tạo theo hierarchy và có directory riêng, mặc định `services/`, trừ khi bạn map nó sang directory khác.

### Vì sao settings chạy trước build scripts?

Quá trình được giản lược thành:

```text
1. Gradle/Wrapper xác định root build và settings.
2. settings.gradle(.kts) đăng ký project descriptors bằng include.
3. Settings cập nhật projectDir và metadata của descriptors.
4. Gradle xây cây Project tương ứng.
5. Gradle cấu hình build.gradle(.kts) của các projects.
6. Gradle giải quyết task request và dependency/task graph.
7. Gradle chạy những task cần thiết.
```

Vì thế câu lệnh trong module:

```groovy
dependencies {
    implementation project(':core')
}
```

**không tự tạo project `:core`**. Nó chỉ dùng `:core` nếu project ấy đã được đăng ký trong cùng build (hoặc có cơ chế dependency substitution được định nghĩa rõ cho composite). Nếu không include, Gradle có thể báo **Project with path ':core' could not be found**.

## 2. Cú pháp `include`: dấu hai chấm là project hierarchy

Groovy DSL:

```groovy
rootProject.name = 'many-projects'
include 'core', 'app'
include ':services:api'
include ':tools:generator'
```

Kotlin DSL:

```kotlin
rootProject.name = "many-projects"
include("core", "app")
include(":services:api")
include(":tools:generator")
```

`include` nhận **project paths** với các segments phân cách bằng `:`, không phải paths dạng `services/api` hay `services\\api`.

| Include | Project path | Default directory (so với root) |
| --- | --- | --- |
| `include 'core'` | `:core` | `core/` |
| `include ':app'` | `:app` | `app/` |
| `include 'services:api'` | `:services:api` | `services/api/` |
| `include ':a:b:c'` | `:a:b:c` | `a/b/c/` |

Dấu `:` đầu nhấn mạnh path từ root; trong Settings, `'services:api'` và `':services:api'` thường cùng biểu diễn path này. Để tránh nhầm với đường dẫn filesystem, nên nhất quán dùng dấu `:` đầu trong project dependencies và task names.

**Không viết** `include 'services/api'` để yêu cầu một nested project. Đó là sai loại separator; khi muốn đặt source trong `services/api` mà project logic tên `:api`, viết:

```groovy
include ':api'
project(':api').projectDir = file('services/api')
```

Tức là **project path có thể phẳng trong khi directory có phân cấp**.

### `include` tự tạo descriptors cha

```groovy
include ':services:api'
```

có thể tạo cả project `:services` làm ancestor. Điều này có hậu quả:

- `:services` cũng là một project trong build, dù bạn không viết `include ':services'` riêng.
- Directory mặc định của nó là `<root>/services`.
- `:services` không mặc nhiên áp dụng Java plugin hoặc phụ thuộc vào `:services:api`.
- Bạn có thể đặt `services/build.gradle` chỉ chứa comment khi muốn project cha làm grouping.
- **Gradle 9.0+ yêu cầu directory của project được include phải tồn tại và writable**, nên parent descriptor tự sinh không nên bị bỏ qua.

Một cấu hình khác, không tạo parent `:services`:

```groovy
include ':api'
project(':api').projectDir = file('services/api')
```

Cách chọn phụ thuộc việc bạn muốn **project path phân tầng** hay chỉ muốn **filesystem được tổ chức phân tầng**.

## 3. `projectDir` xác định thư mục thật, không đổi project identity

```groovy
rootProject.name = 'example'
include ':api'
project(':api').projectDir = file('components/backend/api')
```

Đọc đúng semantics:

1. `include ':api'` tạo **ProjectDescriptor** tên/path `:api`.
2. `project(':api')` trong settings tìm descriptor **đã được include**.
3. `.projectDir` gán một `File` trỏ đến thư mục nguồn thực.
4. Gradle tìm `build.gradle(.kts)` tương ứng trong directory ấy.
5. Khi Java plugin được áp dụng, mặc định main Java source root là `components/backend/api/src/main/java`.
6. Lệnh task vẫn dùng **`./gradlew :api:build`**.
7. Project dependency vẫn dùng **`project(':api')`**.
8. Gradle không tự động move/copy một file nào khi bạn sửa `projectDir`.

**Thứ tự đúng:** luôn `include` project trước khi cấu hình descriptor của nó. Nếu gọi `project(':api')` trước include, Gradle không có descriptor để cấu hình và có thể báo lỗi.

### `file('...')` được tính từ đâu?

Trong `settings.gradle(.kts)`, `file('components/backend/api')` resolve tương đối theo **settings directory/root build** của ví dụ, không theo `projectDir` mà bạn chuẩn bị gán.

Trong `components/backend/api/build.gradle`, `file('config/schema.json')` lại thường resolve tương đối theo **physical projectDir** của chính project đó. Đây là hai ngữ cảnh khác nhau. Nếu module đã remap, đừng nhân đôi đường dẫn root trong một build script con:

```groovy
// Trong build.gradle của physical projectDir components/backend/api:
def correct = file('config/schema.json')

// Dễ sai nếu tưởng file() vẫn bắt đầu từ root:
def duplicated = file('components/backend/api/config/schema.json')
```

Cả hai chỉ là **snippet về đường dẫn**, không phải các file bảo đảm tồn tại. Với cấu trúc nguồn ở đường dẫn riêng, có thể dùng `rootProject.file('config/shared.json')` khi thực sự muốn file từ root.

Không hard-code `C:\\Users\\...` hoặc `/home/alice/...` vào settings dùng chung: người khác, CI và IDE có thể không có đường dẫn đó.

## 4. Gradle 9.0+: directory phải có thật và ghi được

Theo tài liệu Gradle, từ **Gradle 9.0.0**, directory của các included projects **phải tồn tại và có quyền ghi**; nếu không, build sẽ fail. Hành vi trước Gradle 9 ít chặt chẽ hơn và từng cho phép/dễ tạo empty project ngoài ý muốn.

Ví dụ có vấn đề:

```groovy
include ':missing'
```

Nếu `<root>/missing` không tồn tại, Gradle 9+ sẽ báo lỗi khi xây project hierarchy. Tương tự:

```groovy
include ':api'
project(':api').projectDir = file('components/not-created')
```

Mapping là hợp lệ về mặt cú pháp nhưng folder thật không hợp lệ.

Đặc biệt, nếu:

```groovy
include ':services:api'
project(':services:api').projectDir = file('components/api')
```

mà project cha `:services` còn trỏ tới directory mặc định `services/`, **cả** `services/` và `components/api/` phải tồn tại (và writable) khi dùng Gradle 9+.

Có hai hướng tốt:

- Tạo project cha `services/` thật và có file `services/build.gradle` để Git theo dõi nó.
- Map parent descriptor riêng sang một directory grouping có thật:
  ```groovy
  project(':services').projectDir = file('grouping/services')
  ```

Gradle docs còn đưa ví dụ `project(':missing').projectDir.mkdirs()` trong settings để tạo directory, nhưng **không nên dùng `mkdirs()` làm cách che typo của source module**. Trong repository production, file build/source cần được version control hoặc tạo theo một quy trình chuẩn, không dựa vào một thư mục rỗng tự xuất hiện.

Việc directory writable là yêu cầu riêng của Gradle 9. Đổi `layout.buildDirectory` sang thư mục ghi được có thể không giải quyết được lỗi nếu **chính projectDir** bị xem là read-only.

## 5. Lab Java 17 chạy được: logical paths khác physical folders

Ta xây một dự án gồm ba Java projects:

```text
Logical Gradle project graph
:
├── :core
├── :services
│   └── :services:api
└── :apps
    └── :apps:cli
```

Dependency graph (khác hierarchy):

```text
:apps:cli
   -> implementation project(':services:api')
                                   -> implementation project(':core')
```

Physical files:

```text
project-dir-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── services/
│   └── build.gradle
├── apps/
│   └── build.gradle
├── modules/
│   └── domain-core/
│       ├── build.gradle
│       └── src/main/java/sample/core/Greeting.java
├── components/
│   └── api-gateway/
│       ├── build.gradle
│       └── src/main/java/sample/api/GreetingService.java
└── products/
    └── console/
        ├── build.gradle
        └── src/main/java/sample/cli/Main.java
```

Có các directory `services/` và `apps/` ở root vì đó là **project cha logic dùng đường dẫn mặc định**. Chúng có `build.gradle` comment để Git checkout cũng tạo chúng. Không cần `services/api/` hay `apps/cli/`, vì các project con được ánh xạ sang `components/api-gateway/` và `products/console/`.

Yêu cầu:

- JDK 17 có sẵn hoặc Java toolchain 17 được provision phù hợp.
- Gradle Wrapper 8.10.2 hoặc phiên bản tương thích.
- Không cần Maven Central hoặc external plugin: chỉ dùng `java-library` và `application` là Gradle core plugins.
- Chạy các lệnh trong root `project-dir-lab/`.

### 5.1. `settings.gradle`: khai báo project graph và mapping

```groovy
rootProject.name = 'project-dir-lab'

include ':core', ':services:api', ':apps:cli'

project(':core').projectDir = file('modules/domain-core')
project(':services:api').projectDir = file('components/api-gateway')
project(':apps:cli').projectDir = file('products/console')
```

Đoạn này có thể hiểu thành bảng:

| Logical path | Tên project | Physical directory | Vai trò |
| --- | --- | --- | --- |
| `:` | `project-dir-lab` | root | Root project. |
| `:core` | `core` | `modules/domain-core` | Java library. |
| `:services` | `services` | `services` | Ancestor/grouping project. |
| `:services:api` | `api` | `components/api-gateway` | Java library. |
| `:apps` | `apps` | `apps` | Ancestor/grouping project. |
| `:apps:cli` | `cli` | `products/console` | Java application. |

Không đưa physical paths vào `include`. Cũng không cần `include ':services'` và `include ':apps'` lần nữa, vì nested include đã tạo ancestors. Những project cha không phải Java projects trừ khi bạn áp dụng plugins cho chúng.

### 5.2. Root `build.gradle`

```groovy
// Root chỉ điều phối multi-project build.
// Không cần Java plugin ở root cho lab.
```

Root không bắt buộc phải chứa Java code. Đừng áp dụng plugin Java hàng loạt vào tất cả projects chỉ vì chúng thuộc cùng một build.

### 5.3. `services/build.gradle` và `apps/build.gradle`

Nội dung **cả hai** có thể là:

```groovy
// Logical grouping project; không áp dụng Java plugin.
```

Chúng là file hợp lệ. Vì có mặt trong Git, các directories trung gian được tạo thật khi checkout trên CI.

### 5.4. `modules/domain-core/build.gradle`

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

### 5.5. `modules/domain-core/src/main/java/sample/core/Greeting.java`

```java
package sample.core;

public record Greeting(String name) {
    public String render() {
        return "Hello, " + name + "!";
    }
}
```

Đây là **Java record**, hợp lệ với Java 17. Nó cho phép nhận ra ngay nếu một compiler cũ không hỗ trợ Java 17 language level.

### 5.6. `components/api-gateway/build.gradle`

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
    implementation project(':core')
}
```

`implementation project(':core')` tham chiếu **project path**, không phải `modules/domain-core` trên filesystem.

### 5.7. `components/api-gateway/src/main/java/sample/api/GreetingService.java`

```java
package sample.api;

import sample.core.Greeting;

public final class GreetingService {
    public String messageFor(String name) {
        return new Greeting(name).render();
    }
}
```

Dùng `implementation` phù hợp vì public method chỉ trả về `String`; kiểu `Greeting` không xuất hiện trong public method signature. Nếu library công khai type `Greeting`, bạn cần cân nhắc `api project(':core')` cho consumer compile classpath.

### 5.8. `products/console/build.gradle`

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':services:api')
}

application {
    mainClass = 'sample.cli.Main'
}
```

Application plugin cung cấp task `run`; project dependency được trỏ đúng path `:services:api`, dù source của API nằm ở `components/api-gateway`.

### 5.9. `products/console/src/main/java/sample/cli/Main.java`

```java
package sample.cli;

import sample.api.GreetingService;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.messageFor("Gradle"));
        System.out.println("Modules=core,api,cli");
    }
}
```

Dòng `Modules=core,api,cli` là chuỗi minh họa được **Java in tường minh**, không phải Gradle tự động truyền thông tin project graph vào main method.

### 5.10. Tạo Wrapper và chạy Java

Nếu đây là project mới và máy có Gradle phù hợp, tạo Wrapper một lần:

```bash
gradle wrapper --gradle-version 8.10.2 --distribution-type bin
```

Các file `gradlew`, `gradlew.bat`, `gradle-wrapper.jar`, `gradle-wrapper.properties` phải được tạo thật, không thay jar bằng file rỗng.

Linux/macOS:

```bash
./gradlew --version
./gradlew projects
./gradlew :core:build :services:api:build :apps:cli:build
./gradlew -q :apps:cli:run
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :core:build :services:api:build :apps:cli:build
.\gradlew.bat -q :apps:cli:run
```

Stdout **chính xác từ Java `Main.main`** khi chạy `:apps:cli:run`:

```text
Hello, Gradle!
Modules=core,api,cli
```

Đây không phải toàn bộ Gradle log. `--version`, `projects` và `build` in các thông tin khác theo Gradle/JDK/cache; `-q` giúp tập trung xem stdout chương trình Java.

### 5.11. `run` biết tìm các modules bằng cách nào?

Khi chạy `./gradlew :apps:cli:run`:

1. Settings đã đăng ký `:apps:cli`, `:services:api`, `:core`.
2. `:apps:cli` được đánh giá tại `products/console/build.gradle`.
3. Application plugin tạo task `:apps:cli:run`.
4. Dependency `project(':services:api')` được Gradle resolve bằng logical path.
5. Project API thực nằm tại `components/api-gateway`, có `implementation project(':core')`.
6. `:core` có source ở `modules/domain-core`; Gradle chuẩn bị build outputs/classes theo task dependencies.
7. Gradle tạo runtime classpath cho app với project variants cần thiết và chạy `sample.cli.Main`.

**Project hierarchy** `:services → :services:api` khác với **Java dependency graph** `:apps:cli → :services:api → :core`. Quan hệ cha–con không tự thêm một project vào classpath; điều đó do `dependencies {}` quyết định.

### 5.12. Outputs nằm dưới physical directories

Output mặc định của Java plugin nằm trong `<projectDir>/build/`:

```text
modules/domain-core/build/classes/java/main/sample/core/Greeting.class
components/api-gateway/build/classes/java/main/sample/api/GreetingService.class
products/console/build/classes/java/main/sample/cli/Main.class
```

Ví dụ thư mục JAR của `:services:api` là `components/api-gateway/build/libs/`, **không** phải `services/api/build/libs/`.

Nếu project tùy chỉnh `layout.buildDirectory`, output có thể khác. Đừng suy ra physical output path từ logical `:services:api` khi đã có custom `projectDir`.

### 5.13. Chạy Java 17 bằng `javac`/`java` độc lập với Gradle

Vì lab không có external dependencies, có thể compile cả ba source files bằng JDK 17 trên PATH.

Linux/macOS:

```bash
mkdir -p manual-classes
javac --release 17 -d manual-classes \
    modules/domain-core/src/main/java/sample/core/Greeting.java \
    components/api-gateway/src/main/java/sample/api/GreetingService.java \
    products/console/src/main/java/sample/cli/Main.java
java -cp manual-classes sample.cli.Main
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force manual-classes | Out-Null
javac --release 17 -d manual-classes modules/domain-core/src/main/java/sample/core/Greeting.java components/api-gateway/src/main/java/sample/api/GreetingService.java products/console/src/main/java/sample/cli/Main.java
java -cp manual-classes sample.cli.Main
```

Stdout:

```text
Hello, Gradle!
Modules=core,api,cli
```

Các lệnh thủ công **không đọc `settings.gradle`**, không tạo Gradle project hierarchy hay task graph; `javac` chỉ thấy danh sách file Java được truyền. Điều đó minh họa project identity của Gradle và Java package/classpath là hai tầng khác nhau.

## 6. Kotlin DSL đầy đủ cho cùng lab

Có thể chuyển sang Kotlin DSL bằng cách dùng `settings.gradle.kts` và đổi các `build.gradle` thành `build.gradle.kts`, giữ nguyên source Java.

### `settings.gradle.kts`

```kotlin
rootProject.name = "project-dir-lab"

include(":core", ":services:api", ":apps:cli")

project(":core").projectDir = file("modules/domain-core")
project(":services:api").projectDir = file("components/api-gateway")
project(":apps:cli").projectDir = file("products/console")
```

### Root và hai project cha

Các file `build.gradle.kts` tại root, `services` và `apps` có thể chỉ gồm:

```kotlin
// Root/grouping project, không cần Java plugin.
```

### `modules/domain-core/build.gradle.kts`

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

### `components/api-gateway/build.gradle.kts`

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":core"))
}
```

### `products/console/build.gradle.kts`

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
    implementation(project(":services:api"))
}

application {
    mainClass.set("sample.cli.Main")
}
```

Sự khác nhau chỉ nằm ở cú pháp DSL:

- Groovy `include ':core'`, Kotlin `include(":core")`.
- Groovy `project(':core').projectDir = file('...')`, Kotlin `project(":core").projectDir = file("...")`.
- Groovy `implementation project(':core')`, Kotlin `implementation(project(":core"))`.
- Groovy `mainClass = 'sample.cli.Main'`, Kotlin `mainClass.set("sample.cli.Main")`.

**Không giữ đồng thời hai bộ build scripts ở cùng vị trí với kỳ vọng Gradle trộn chúng**. Chọn một DSL nhất quán cho từng project.

## 7. Cách kiểm chứng mapping một cách khách quan

### 7.1. `projects` task

```bash
./gradlew projects
```

Bạn kỳ vọng Gradle có các project paths:

```text
:core
:services
:services:api
:apps
:apps:cli
```

Đây là **danh sách kỳ vọng**, không phải stdout đầy đủ của `projects` vì Gradle có banner, tree view và thông tin tùy phiên bản.

### 7.2. `properties` task

```bash
./gradlew :core:properties
./gradlew :services:api:properties
./gradlew :apps:cli:properties
```

Trong kết quả, tìm `path`, `name` và `projectDir`:

- `:core` có `projectDir` kết thúc bằng `modules/domain-core`.
- `:services:api` có `projectDir` kết thúc bằng `components/api-gateway`.
- `:apps:cli` có `projectDir` kết thúc bằng `products/console`.

Full path thay đổi theo máy/OS. Đừng chia sẻ toàn bộ `properties` log nếu có giá trị nhạy cảm từ Gradle project/user properties.

### 7.3. Một task chẩn đoán tên và directory

Thêm **snippet sau** vào `products/console/build.gradle` nếu muốn kiểm tra mapping ngay tại project `:apps:cli`:

```groovy
tasks.register('showIdentity') {
    def logicalPath = project.path
    def logicalName = project.name
    def directoryName = project.projectDir.name

    doLast {
        println "path=" + logicalPath
        println "name=" + logicalName
        println "dirName=" + directoryName
    }
}
```

Chạy:

```bash
./gradlew -q :apps:cli:showIdentity
```

Stdout:

```text
path=:apps:cli
name=cli
dirName=console
```

Ở đây `name=cli` là tên **logical project**, còn `dirName=console` là tên **physical directory cuối**. Những giá trị được lấy ở configuration time, action chỉ in các chuỗi đã có; không yêu cầu truy cập Project model từ task action.

### 7.4. Kiểm tra task path chứ không đoán theo folder

```bash
./gradlew :core:tasks
./gradlew :services:api:build
./gradlew :apps:cli:run --dry-run
```

`--dry-run` chỉ hiển thị task graph dự kiến, **không chứng minh Java chạy được**. Khi chạy thật dùng `./gradlew -q :apps:cli:run`.

Câu lệnh sai trong lab:

```bash
./gradlew :components:api-gateway:build
```

vì không có project path logic đó; chỉ có physical directory `components/api-gateway`.

## 8. Phân biệt `projectDir`, `layout.buildDirectory` và sourceSets

| Cấp | Giá trị thường gặp | Tác dụng |
| --- | --- | --- |
| `projectDir` | `components/api-gateway/` | Nơi Gradle tìm build script và project-relative files. |
| `layout.buildDirectory` | `components/api-gateway/build/` | Đầu ra mặc định của tasks. |
| `sourceSets.main.java` | `components/api-gateway/src/main/java` | Nơi Java plugin tìm source Java. |
| `rootDir` | `project-dir-lab/` | Root filesystem của build. |
| `project.path` | `:services:api` | Project identity/task path; không phải filesystem path. |

Khi map `:services:api` sang `components/api-gateway`, bạn **không cần** cấu hình lại `sourceSets.main.java.srcDirs` nếu code tuân theo layout chuẩn `src/main/java` **bên trong physical projectDir**.

Một lỗi thường gặp là đặt trong `components/api-gateway/build.gradle`:

```groovy
sourceSets {
    main {
        java.srcDir 'components/api-gateway/src/main/java'
    }
}
```

Đoạn này có thể resolve sai thành `components/api-gateway/components/api-gateway/src/main/java`, vì path trong module build script được tính từ **projectDir**.

Chỉ thêm `sourceSets` khi source thật nằm ngoài conventions của project, và phải ghi rõ path scope. Đừng dùng `projectDir` chỉ để đổi thư mục output; `layout.buildDirectory` là một khái niệm riêng.

## 9. includeFlat, includeBuild và include khác nhau ra sao?

| API ở Settings | Ý nghĩa | Directory mặc định |
| --- | --- | --- |
| `include(':api')` | Thêm subproject `:api` cùng build | Root `api/`. |
| `include(':services:api')` | Thêm nested subproject và ancestors | Root `services/api/`. |
| `includeFlat('shared')` | Thêm sibling project theo layout ngang cấp | Thường là `../shared/`. |
| `includeBuild('build-logic')` | Thêm một build độc lập vào composite | Directory build được nêu. |

### includeFlat

```groovy
includeFlat 'shared-library'
```

có ích khi workspace cũ có:

```text
workspace/
├── application-root/       # settings.gradle ở đây
└── shared-library/         # sibling folder
```

Nó dùng convention một directory sibling của root, không giống `include ':shared-library'` mặc định tìm `application-root/shared-library/`.

**Nhược điểm:** phụ thuộc cấu trúc checkout ngoài root; CI hoặc đồng đội có thể không có sibling cùng phiên bản. Với mono-repo mới, nên ưu tiên source trong repo cùng `include`/`projectDir`. Nếu dùng includeFlat, cần tài liệu rõ nguồn và vị trí của sibling.

### includeBuild

```groovy
includeBuild('build-logic')
```

tạo quan hệ **composite build** với một build độc lập, không phải `:build-logic` subproject của root. Included build có thể có settings riêng, plugins, dependencies và version catalogs riêng. Một use case là build logic được chia riêng để cung cấp Gradle convention plugins.

Không thay `include(':api')` bằng `includeBuild('components/api-gateway')` chỉ vì muốn thay location. Nếu một source project cần là **subproject cùng build**, chỉ dùng `projectDir` mapping. Nếu nó thật sự là **build độc lập**, dùng composite/published dependency theo kiến trúc.

### ProjectDescriptor trong settings khác Project trong build.gradle

Trong `settings.gradle`:

```groovy
include ':core'
project(':core').projectDir = file('modules/domain-core')
```

`project(':core')` trả **ProjectDescriptor** để thay path/directory metadata trước khi build projects được tạo.

Trong `build.gradle`:

```groovy
dependencies {
    implementation project(':core')
}
```

`project(':core')` tham gia DSL để tạo **project dependency**. Tên method gần giống nhưng scope và trách nhiệm khác nhau.

## 10. buildFileName và tên project khác projectDir

Ngoài `projectDir`, ProjectDescriptor còn cho phép thay `buildFileName`:

```groovy
// Chỉ là snippet thay thế, không dùng trong lab đầy đủ.
include ':core'
project(':core').projectDir = file('modules/domain-core')
project(':core').buildFileName = 'core.gradle'
```

Khi đó bạn phải thật sự có file `modules/domain-core/core.gradle`. Đoạn cấu hình **không tự rename** `build.gradle` cũ.

Kotlin DSL:

```kotlin
include(":core")
project(":core").projectDir = file("modules/domain-core")
project(":core").buildFileName = "core.gradle.kts"
```

Với dự án mới, thường nên giữ tên `build.gradle(.kts)` mặc định vì dễ đọc và dễ tích hợp IDE. Tùy chỉnh `buildFileName` chỉ khi có lý do thật.

**Tên project không phải tên directory:** trong lab `:apps:cli` có logical `name='cli'` trong khi thư mục thật tên `console`. Nếu đóng gói JAR, archive base name mặc định có thể dựa vào project name `cli`, còn output directory nằm dưới `products/console/build/`. Maven artifact coordinates lại có chính sách `group`/`version`/`publication` riêng, không tự là đường dẫn filesystem.

## 11. Di chuyển source mà vẫn giữ project path ổn định

Giả sử ban đầu:

```text
repo/
├── settings.gradle       # include ':api'
└── api/
    ├── build.gradle
    └── src/main/java/...
```

Bạn muốn chuyển source thành:

```text
repo/
├── settings.gradle
└── components/backend/api-service/
    ├── build.gradle
    └── src/main/java/...
```

Chỉ cần giữ logical path và map lại:

```groovy
include ':api'
project(':api').projectDir = file('components/backend/api-service')
```

Lúc đó:

- Gradle task vẫn là `./gradlew :api:build`.
- Module khác vẫn dùng `implementation project(':api')`.
- Physical output mặc định chuyển sang `components/backend/api-service/build`.
- Java packages không đổi nếu bạn không sửa `package` declarations.
- CI scripts có `cd api` hoặc lấy artifact từ `api/build/libs` **phải cập nhật**, vì chúng dùng filesystem path.
- IDE phải reload Gradle project model.

**Không nhầm “giữ project path” với “không cần thay đổi gì”.** Mapping không tự move source/build script, sửa relative file references hoặc thay đường dẫn build artifacts trong CI.

### Quy trình migration an toàn

1. Ghi lại `./gradlew :api:build` ở commit trước.
2. Di chuyển cả build script, sources, resources và test fixtures bằng version control.
3. Thêm `projectDir` mapping trong settings.
4. Bảo đảm directory mới tồn tại/writable ở checkout sạch, kể cả Gradle 9.
5. Kiểm tra `./gradlew projects` và `:api:properties`.
6. Chạy `:api:build` và các consumer/integration tests.
7. Sửa CI artifact paths, working directories, codeowners/formatter config.
8. Reload IntelliJ IDEA/Eclipse/VS Code Gradle model.
9. Commit move và settings/CI changes cùng một PR.
10. Thử trên checkout sạch, không phụ thuộc file không được commit ở folder cũ.

## 12. Tự động phát hiện projects từ directory: nên thận trọng

Gradle Settings có thể duyệt thư mục rồi include:

```groovy
// Snippet chỉ dùng khi modules/ tồn tại và mỗi directory con là một project.
file('modules').eachDir { directory ->
    def logicalName = directory.name
    include ':' + logicalName
    project(':' + logicalName).projectDir = directory
}
```

Đoạn này không chứa bất kỳ placeholder thực thi nào, nhưng chỉ có ý nghĩa nếu thư mục `modules/` của repository thực sự gồm các Gradle projects hợp lệ.

Rủi ro của dynamic include:

- Một directory `build`, `.gradle`, cache, generated output xuất hiện bất ngờ có thể bị include thành project.
- Danh sách projects local/CI có thể khác vì một máy có untracked folder.
- Tên directory có chữ hoa/dấu cách/định danh trùng không phù hợp conventions.
- Thứ tự iteration filesystem không nên được dùng làm chính sách business logic.
- Một folder chưa có `build.gradle` có thể vô tình trở thành empty project.
- Dễ bỏ qua các project tồn tại nhưng không nằm dưới một `modules/` duy nhất.

Cách rõ hơn với mapping nhiều module là danh sách có chủ đích:

```groovy
def moduleLocations = [
    core: 'modules/domain-core',
    api:  'components/api-gateway',
    cli:  'products/console'
]

moduleLocations.each { key, location ->
    include ':' + key
    project(':' + key).projectDir = file(location)
}
```

**Đây là một thiết kế khác lab**, vì nó tạo flat paths `:core`, `:api`, `:cli`, chứ không tạo `:services:api` và `:apps:cli`. Danh sách explicit dễ review hơn việc quét mọi thư mục, nhưng hãy chọn cấu trúc paths phù hợp với kiến trúc thật.

Kotlin DSL có thể dùng:

```kotlin
// Snippet, chỉ dùng khi modules/ có thật.
file("modules").listFiles()
    ?.filter { it.isDirectory }
    ?.sortedBy { it.name }
    ?.forEach { directory ->
        val name = directory.name
        include(":" + name)
        project(":" + name).projectDir = directory
    }
```

Sort giúp việc đọc/đăng ký predictable, nhưng không giải quyết được việc danh sách folders bị thay đổi ngoài ý muốn. Đừng đánh đồng dynamic discovery với nguồn sự thật về kiến trúc modules.

## 13. Paths bên ngoài root và bảo mật

`projectDir` có thể được đặt thành một `File` nằm ngoài root, nhưng điều đó tạo thêm trách nhiệm:

- CI checkout có thể không tạo directory ngoài root.
- Hai developer có thể có **hai phiên bản source khác nhau** ở sibling folder.
- Build có thể chạy code chưa qua review cùng repository.
- Plugin/Gradle tasks có quyền truy cập filesystem của người chạy.
- IDE/CI portability kém vì absolute paths/permissions khác.
- Cách xác định provenance từ Git commit khó hơn.

Nếu thực sự cần source từ independent build, cân nhắc `includeBuild` hoặc artifact đã publish với version xác định. Không dùng `projectDir` để trỏ tới một thư mục cá nhân không được kiểm soát chỉ vì build chạy trên laptop.

Tương tự, **không map hai ProjectDescriptor vào cùng một physical directory** nếu không có lý do và kiểm thử rõ: chúng có thể dùng cùng `build.gradle` và ghi đè outputs dưới `build/`, khiến task/cache state khó kiểm soát.

## 14. Settings còn quản lý repositories và plugin resolution

Một settings file có thể mở rộng:

```groovy
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

rootProject.name = 'project-dir-lab'
include ':core', ':services:api', ':apps:cli'

project(':core').projectDir = file('modules/domain-core')
project(':services:api').projectDir = file('components/api-gateway')
project(':apps:cli').projectDir = file('products/console')
```

Đây là **snippet mở rộng**, không phải thay đổi bắt buộc cho lab dùng core plugins. Phân biệt:

- `pluginManagement.repositories` tìm **plugin dependencies** cho plugins DSL.
- `dependencyResolutionManagement.repositories` tìm **external library dependencies**.
- `include` quyết định **project graph**.
- `projectDir` quyết định **project locations**.

Chúng là các trách nhiệm khác nhau dù cùng nằm trong settings. Không chữa lỗi `Project path not found` bằng cách thêm `mavenCentral()`; cũng không chữa `Plugin was not found` bằng việc đổi `projectDir` khi mapping đã đúng.

`pluginManagement {}` là block đặc biệt trong settings cần đặt ở vị trí hợp lệ (thường đầu script) theo Gradle DSL; tránh đưa nó vào một vị trí ngẫu nhiên khi copy/paste.

## 15. IDE và CI: cùng project graph mới đối chiếu được build

IntelliJ IDEA, Eclipse Buildship và VS Code Gradle for Java thường import Gradle model. Một directory tên `components/api-gateway` không có nghĩa IDE chắc chắn tạo project tên `:components:api-gateway`; IDE nên đọc settings để biết project `:services:api`.

Khi sửa mapping:

1. Mở **root chứa settings** trong IDE.
2. Chọn **Gradle Wrapper** của repository.
3. Reload/Sync Gradle model.
4. Xác minh `:core`, `:services:api`, `:apps:cli` được phát hiện đúng.
5. Dùng Gradle task `:apps:cli:run` để so với terminal; IDE native Java Run configuration có thể có classpath/JDK/working directory khác.
6. Kiểm tra CI command dùng **logical task paths**, nhưng artifact upload lấy từ **physical output paths**.
7. Xác nhận CI checkout tạo mọi project directory có thật, đặc biệt ancestors ở Gradle 9+.

Ví dụ CI nên chạy:

```bash
./gradlew --version
./gradlew :core:build :services:api:build :apps:cli:build
```

Lệnh không phụ thuộc shell đang `cd` vào `products/console`. Nếu muốn chạy một task cụ thể:

```bash
./gradlew :apps:cli:run
```

Không dùng `gradle build` toàn cục của máy để thay Wrapper nếu nhóm muốn cùng Gradle distribution version.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Sửa theo bằng chứng |
| --- | --- | --- |
| `Project with path ':api' could not be found` | Quên include, hoặc include `:services:api` nhưng lại gọi `:api` | Dùng đúng path đã đăng ký. |
| `Project with path ':components:api-gateway' could not be found` | Nhầm physical folder với logical path | Gọi `:services:api`. |
| `Project directory ... does not exist` | Mapping trỏ directory chưa tạo/commit, ancestor thiếu | Tạo/remap directory có thật; kiểm tra Gradle 9. |
| `project(':api')` trong settings lỗi | Cấu hình descriptor trước khi include | Include trước. |
| Build script không được đọc | `projectDir` sai hoặc `buildFileName` tùy chỉnh sai | Kiểm tra directory và tên file thật. |
| Gradle thấy module nhưng không có `compileJava` | Module không áp dụng Java plugin hoặc trỏ nhầm folder | Kiểm tra build script trong physical projectDir. |
| `:apps:cli:run` không tồn tại | Không áp dụng Application plugin cho `:apps:cli` | Áp dụng `application`, xem `:apps:cli:tasks`. |
| `NoClassDefFoundError` | Thiếu project dependency hoặc runtime classpath sai | Kiểm tra `implementation project(':path')` và Java packages. |
| Output không xuất hiện dưới `services/api/build` | Build output ở mapped projectDir | Xem `components/api-gateway/build`. |
| Local chạy, CI thiếu module | Absolute path/sibling folder không có trên runner | Dùng relative paths thuộc repo và checkout sạch. |
| IDE import thiếu modules | Mở physical folder thay vì root settings | Mở root Gradle build, Reload Gradle Project. |
| Java source nằm sai `src/main/java` | Relative path tính từ projectDir mới | Đặt đúng source root hoặc cấu hình sourceSets có chủ đích. |
| Dynamic include thêm project lạ | Quét cả temp/cache directories | Dùng danh sách explicit hoặc whitelist. |
| Grouping parent thiếu trong Gradle 9 | Nested include tự tạo ancestor descriptor | Tạo/remap parent project directory. |
| `includeBuild` không cho path `:foo` như mong đợi | Included build là build độc lập | Phân biệt composite vs subproject. |
| Trùng `projectDir` giữa hai projects | Đọc cùng build script, output collision | Tách physical directories. |
| Windows chạy được, Linux fail | Chữ hoa/thường hoặc separator khác | Chuẩn hóa case và dùng File APIs. |
| Đổi `projectDir` rồi Maven artifactId khác dự kiến | Nhầm project name với publication coordinates | Cấu hình `group`/`artifactId`/publishing riêng. |

### Quy trình debug từng bước

```bash
./gradlew --version
./gradlew projects
./gradlew :services:api:properties
./gradlew :apps:cli:tasks --all
./gradlew :apps:cli:run --dry-run
./gradlew -q :apps:cli:run
```

Xem:

1. Bạn đang dùng đúng Wrapper/build root không?
2. `:services:api` có xuất hiện trong `projects` không?
3. `projectDir` của nó có đúng directory thật không?
4. File `build.gradle(.kts)` ở đó có áp dụng plugin phù hợp không?
5. Task `run` có tồn tại trên `:apps:cli` không?
6. Source Java 17 có compile được không?
7. Có dependency `:apps:cli → :services:api → :core` không?
8. Có lỗi JDK/toolchain hoặc environment riêng không?

Tránh xóa toàn bộ `~/.gradle` để chữa một lỗi include/projectDir thuần túy: cache không tạo ra project descriptor chưa được khai báo và không sửa relative path bị viết sai.

## 17. Bài tập tự kiểm tra và đáp án

**Câu 1.** `include ':core'` và `project(':core').projectDir=file('modules/domain-core')` khác nhau ở đâu?

**Đáp án:** `include` tạo logical project `:core`; `projectDir` cho biết source/build script thực của project ấy nằm ở đâu.

**Câu 2.** Muốn include nested `:services:api`, dùng `include 'services/api'` đúng không?

**Đáp án:** Không. Settings.include dùng dấu `:`: `include ':services:api'`.

**Câu 3.** Project path `:apps:cli` có buộc thư mục thật tên `apps/cli` không?

**Đáp án:** Không, nếu mapping `project(':apps:cli').projectDir` đã trỏ tới directory hợp lệ khác.

**Câu 4.** Trong lab, `:services:api` có physical folder nào?

**Đáp án:** `components/api-gateway`.

**Câu 5.** `include ':services:api'` có thể tạo thêm project `:services` không?

**Đáp án:** Có. Đó là ancestor logic; Gradle 9+ còn yêu cầu directory thật hợp lệ.

**Câu 6.** Có cần thư mục `services/api` trong lab không?

**Đáp án:** Không, vì child `:services:api` được remap. Nhưng `services/` của parent `:services` có thật và là directory mặc định.

**Câu 7.** Trong `products/console/build.gradle`, dependency tới API được ghi như thế nào?

**Đáp án:** `implementation project(':services:api')`, không phải `project('components/api-gateway')`.

**Câu 8.** `./gradlew :apps:cli:run` sẽ chạy chương trình Java ở đâu?

**Đáp án:** Chạy task Application plugin của project logic `:apps:cli`, có source tại `products/console` theo mapping.

**Câu 9.** Trong lab, stdout Java chính xác là gì?

**Đáp án:**

```text
Hello, Gradle!
Modules=core,api,cli
```

**Câu 10.** `project(':apps:cli').name` và `projectDir.name` có giống nhau không?

**Đáp án:** Không: `name=cli`, còn physical directory name là `console`.

**Câu 11.** Tại sao Gradle 9+ có thể fail khi chỉ parent `services/` còn thiếu?

**Đáp án:** Nested include tạo descriptor `:services`; directory tương ứng phải tồn tại và writable.

**Câu 12.** `projectDir` có tự move `src/main/java` hoặc build.gradle sang folder mới không?

**Đáp án:** Không. Nó chỉ thay descriptor metadata; người dùng phải di chuyển files thật.

**Câu 13.** Dùng `includeFlat` là giải pháp giống `includeBuild` không?

**Đáp án:** Không. `includeFlat` tạo sibling project trong cùng build theo directory convention; `includeBuild` gắn một independent build.

**Câu 14.** `buildDir` mặc định nằm ở đâu sau khi remap `:core` sang `modules/domain-core`?

**Đáp án:** Thường tại `modules/domain-core/build/`, trừ khi project đổi `layout.buildDirectory`.

**Câu 15.** Java package `sample.api` có phụ thuộc tên projectDir `api-gateway` không?

**Đáp án:** Không. Java package name, Gradle project path và physical directory name có thể khác nhau.

**Câu 16.** Đổi `buildFileName='core.gradle'` có tự rename `build.gradle` không?

**Đáp án:** Không. File có tên mới phải được cung cấp trong physical projectDir.

**Câu 17.** Tại sao dynamic include mọi folder không an toàn trong monorepo lớn?

**Đáp án:** Cache/temp/untracked folder có thể xuất hiện và bị đăng ký thành project, khiến graph khác giữa local/CI.

**Câu 18.** Để kiểm tra projectDir thực của `:services:api`, dùng lệnh nào?

**Đáp án:** `./gradlew :services:api:properties` và xem `projectDir`, kết hợp `./gradlew projects`.

**Câu 19.** `project(':services:api')` trong settings và trong `dependencies {}` có giống vai trò không?

**Đáp án:** Không. Trong settings đó là ProjectDescriptor để cấu hình location; trong dependencies nó tạo project dependency.

**Câu 20.** Một child project có tự phụ thuộc vào parent chỉ vì project hierarchy không?

**Đáp án:** Không. Project dependency graph phải được khai báo trong `dependencies {}`.

**Câu 21.** Khi chuyển `:api` sang `components/api` mà vẫn giữ logical path `:api`, cần đổi gì?

**Đáp án:** Di chuyển source/build script thật, cập nhật `projectDir`, các file paths/CI artifact paths, reload IDE; dependency paths `project(':api')` có thể giữ nguyên.

**Câu 22.** `includeBuild('build-logic')` có tự tạo subproject `:build-logic` của root không?

**Đáp án:** Không. Nó tạo composite relationship với build có settings scope riêng.

**Câu 23.** Nếu cả `:core` và `:api` dùng cùng `projectDir`, có rủi ro gì?

**Đáp án:** Xung đột build scripts, source roots, output directories và task/cache state; thông thường phải tách directory mỗi project.

**Câu 24.** Tại sao dùng `javac` thủ công cho ba Java files không thể chứng minh settings mapping đúng?

**Đáp án:** `javac` không đọc Gradle settings; nó chỉ compile các file được truyền. Cần thêm `./gradlew projects` và task CLI để xác minh project descriptors.

**Câu 25.** `include ':api'` có tự xuất hiện dependency `api` trên mọi project khác không?

**Đáp án:** Không. Include đăng ký project trong build, không thêm library vào classpath.

## 18. Tài liệu chính thức

- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): cú pháp include, đường dẫn mặc định, project descriptors, mapping `projectDir`, yêu cầu directory tồn tại của Gradle 9.
- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html): root/subproject hierarchy, path và cách tổ chức.
- [Gradle — Settings DSL](https://docs.gradle.org/current/dsl/org.gradle.api.initialization.Settings.html): `include`, `includeFlat`, `includeBuild`, `project(path)`.
- [Gradle — ProjectDescriptor API](https://docs.gradle.org/current/javadoc/org/gradle/api/initialization/ProjectDescriptor.html): `projectDir`, `buildFileName` và tên project.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): tránh empty projects ngoài ý muốn, project naming và hierarchy.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): cách phân biệt included builds với subprojects.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `implementation`, `api` và project dependency variants.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): task `run`, mainClass.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): biên dịch Java 17.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): dùng cùng Gradle version trong terminal, IDE, CI.

**Ghi nhớ:** `include` tạo **logical project graph** (ví dụ `:services:api`), còn `project(':services:api').projectDir` trỏ tới **physical directory** (ví dụ `components/api-gateway/`). Những dependencies và task paths vẫn dùng logical paths; output file paths thường đi theo physical projectDir. Với nested includes, Gradle có project cha tự sinh; từ Gradle 9, **mọi included project directory phải tồn tại và writable**. Sử dụng Wrapper, `projects`, `properties` và task Java thật để xác minh, không suy đoán từ tên folder trong IDE.