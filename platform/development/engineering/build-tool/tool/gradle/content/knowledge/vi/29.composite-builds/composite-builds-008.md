# Tránh vòng lặp include, trùng tọa độ và hiểu nhầm phạm vi task trong Gradle Composite Build

**Composite Build** cho phép một Gradle build bao gồm những Gradle builds khác bằng `includeBuild(...)`, nhưng mỗi build vẫn có `settings.gradle.kts`, tập projects, configurations, repositories và nhiều thiết lập riêng. Đây là kỹ thuật hữu ích để cùng phát triển ứng dụng và thư viện mà **không publish thư viện lên Maven repository trước**, hoặc để tách build logic thành một build độc lập.

Ba nhóm sự cố thường gặp:

1. **Vòng include và vòng dependency/task**: cùng một build được bao gồm qua nhiều nhánh, hai builds include lẫn nhau, hoặc các modules/subtasks phụ thuộc trở lại chính chúng. Không được đồng nhất “vòng trong đồ thị include” với “chu trình task dependency bị cấm”.
2. **Trùng danh tính**: hai included builds có cùng **build-tree path**, build path đè lên project path của main build, hoặc hai projects xuất hiện như cùng một Maven module `group:name` và khiến substitution khó kiểm soát.
3. **Nhầm phạm vi task**: tưởng `includeBuild` tạo ra một subproject có thể gọi `project(":other")`; tưởng chạy `./gradlew build` ở composite root sẽ gọi `build` của **mọi** included build; hoặc nhầm `:app:run` với `:included-build:app:run`.

Bài học thuộc phần **Composite build** của *Build Tool Gradle*. Sau bài, bạn sẽ phân biệt root build, included build, subproject, build-tree path, dependency substitution và task path; chạy một ví dụ **Java 17 + Gradle Kotlin DSL** có app và thư viện ở **hai builds riêng**; cấu hình `includeBuild` đúng, kiểm soát tọa độ, chẩn đoán xung đột, hiểu nested/self-inclusion và áp dụng checklist CI.

## 1. Multi-project build khác composite build ở đâu?

### Multi-project: một settings, nhiều subprojects

~~~text
monolith/
├── settings.gradle.kts
├── app/build.gradle.kts
└── library/build.gradle.kts
~~~

~~~kotlin
// monolith/settings.gradle.kts
rootProject.name = "monolith"
include("app", "library")
~~~

`:app` và `:library` là hai projects trong **cùng một Gradle build**. `:app` có thể phụ thuộc:

~~~kotlin
dependencies {
    implementation(project(":library"))
}
~~~

Task được gọi bằng project path:

~~~bash
./gradlew :library:build
./gradlew :app:run
~~~

### Composite: nhiều builds có settings riêng

~~~text
workspace/
├── settings.gradle.kts
├── app/build.gradle.kts
└── libraries/
    └── number-utils/
        ├── settings.gradle.kts
        ├── build.gradle.kts
        └── src/main/java/...
~~~

Root settings:

~~~kotlin
rootProject.name = "workspace"
include("app")
includeBuild("libraries/number-utils")
~~~

Ở đây:

- `:app` là **subproject của main build**.
- `libraries/number-utils` là **một included build**, không phải subproject.
- Included build có root project riêng, repositories, plugins, properties và tasks của nó.
- `project(":number-utils")` trong build script của root **không** tìm project từ included build; đó không phải project path nội bộ main build.
- Khi muốn dùng thư viện bên trong included build, consumer thường khai báo external module coordinates như `implementation("org.demo:number-utils:1.0.0")`; Gradle có thể tự **substitute module → local project**.

**Quy tắc đầu tiên:** `include("x")` thêm **subproject**, còn `includeBuild("x")` thêm **một build độc lập**. Hai APIs không thể thay thế cho nhau chỉ vì cùng trỏ đến folder.

## 2. Một composite build có những loại đường dẫn nào?

Hãy phân biệt bốn định danh:

| Loại | Ví dụ | Dùng làm gì? |
| --- | --- | --- |
| File system location | `libraries/number-utils` | Thư mục chứa `settings.gradle.kts` của build được include |
| Included build name/build path | `number-utils` / `:number-utils` | Định danh build trong **build tree**, thường phát sinh từ directory name |
| Project path **bên trong included build** | `:`, `:core`, `:api` | Nhắm đến project của build đó, tính từ root của included build |
| Maven module coordinates | `org.demo:number-utils:1.0.0` | Tên external module mà Gradle có thể thay bằng local project |

Còn một đường dẫn khác là **task path**:

~~~text
Main build subproject task:
    :app:run

Root task inside an included build named number-utils:
    :number-utils:build

Subproject task inside an included build named number-utils:
    :number-utils:core:test
~~~

Trong câu `gradle.includedBuild("number-utils").task(":core:test")`:

- `number-utils` là **included build name**.
- `:core:test` là **task path tính từ root của chính included build**.
- Hai phần kết hợp thành build-tree task path `:number-utils:core:test`.

**Đừng tự động suy rằng thư mục `libraries/number-utils` biến thành project path `:libraries:number-utils` trong root build**. Build path của included build mặc định được lấy từ tên directory chứa build, không phải nguyên văn filesystem path.

## 3. Composite Build hình thành theo settings như thế nào?

Hai cách thêm build thường dùng:

~~~kotlin
// settings.gradle.kts
includeBuild("../shared-library")
~~~

hoặc:

~~~bash
./gradlew --include-build ../shared-library :app:run
~~~

- `includeBuild` ở settings là cách **lâu dài/được version-control** cùng repo.
- CLI `--include-build` phù hợp thử co-development **tạm thời** mà không sửa settings.
- Relative include path trong settings được tính từ **thư mục chứa settings file**.
- Đích nên là **root directory của một Gradle build**, tức có `settings.gradle.kts` hoặc `settings.gradle` thích hợp.
- Hạn chế absolute machine-specific paths như `C:\Users\...` hoặc `/home/user/...` trong settings do CI/người khác không có path giống nhau.

Lệnh `--include-build` làm build được chạy tham gia một composite, cho phép automatic dependency substitution theo cơ chế của Gradle. Với **included builds cung cấp plugins** dùng trong `plugins { }`, hướng cấu hình thường tin cậy hơn là đặt `includeBuild` đúng nơi trong settings thay vì phụ thuộc hoàn toàn vào CLI.

## 4. Ví dụ đầy đủ: một main build và một included library build (Java 17)

Ví dụ này tối giản nhưng **có đủ source và Gradle scripts**:

- Main build có `:app`, plugin `application` và Java `Main`.
- Included build `number-utils` có thư viện Java `NumberUtils`.
- Consumer khai báo **Maven-style coordinate** thay vì `project(...)`.
- Gradle composite substitute dependency bằng local project không cần publish ra Maven Central.
- Chạy task của included build trực tiếp từ composite root.
- Có root aggregator task để phân biệt **task dependency** và **dependency substitution**.

### 4.1. Sơ đồ tệp

~~~text
composite-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── app/
│   ├── build.gradle.kts
│   └── src/main/java/demo/app/Main.java
└── libraries/
    └── number-utils/
        ├── settings.gradle.kts
        ├── build.gradle.kts
        └── src/main/java/demo/numbers/NumberUtils.java
~~~

Yêu cầu: Gradle Wrapper phù hợp với JDK toolchain Java 17; JDK 17 cài sẵn hoặc provisioning đã được cấu hình. Project không cần dependencies từ Maven Central. Không tự viết Gradle Wrapper JAR bằng tay; nếu chưa có Wrapper, tạo bằng một Gradle installation phù hợp và commit wrapper files đúng chuẩn.

### 4.2. Root `composite-demo/settings.gradle.kts`

~~~kotlin
rootProject.name = "composite-demo"

// Một subproject trong main build.
include("app")

// Một Gradle build KHÁC với settings riêng.
includeBuild("libraries/number-utils")
~~~

Trong cây thư mục này, `libraries/number-utils` tồn tại thật và có settings riêng. Included build name mặc định là `number-utils`, không trùng main build `composite-demo` hay root subproject `app`.

### 4.3. Root `composite-demo/build.gradle.kts`

~~~kotlin
// Task aggregator CHỈ tồn tại trong main build root.
tasks.register("checkIncludedLibrary") {
    dependsOn(gradle.includedBuild("number-utils").task(":check"))
}
~~~

Đây là full root build script cho demo. Nó tạo một root task để yêu cầu `check` từ root project trong included build. Điều này khác với `:app` khai báo dependency vào thư viện.

**`gradle.includedBuild("number-utils")` trả về IncludedBuild**, không phải `Project`. `task(":check")` tạo task reference tới nhiệm vụ của included build, nên không cần `project(":number-utils").tasks...`.

Nếu bỏ hoàn toàn root `build.gradle.kts`, composite vẫn có thể include thư viện và app chạy. Root aggregator là tùy chọn để học cách gọi task xuyên build boundary.

### 4.4. Included `libraries/number-utils/settings.gradle.kts`

~~~kotlin
rootProject.name = "number-utils"
~~~

Tên root project của included build trở thành **project name** dùng để tạo default substitution coordinate khi kết hợp với `group`. Không thêm `includeBuild("../..")` quay về main build; demo không cần inclusion vòng.

### 4.5. Included `libraries/number-utils/build.gradle.kts`

~~~kotlin
plugins {
    id("java-library")
}

group = "org.demo"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Đây là file đầy đủ. Plugin `java-library` cung cấp JAR/component phù hợp, `group` và project name tạo **`org.demo:number-utils`** cho automatic substitution. `version` xác định module version của local library, nhưng **không phải khóa kiểm tra version requested** của composite substitution.

### 4.6. Included Java source

`libraries/number-utils/src/main/java/demo/numbers/NumberUtils.java`:

~~~java
package demo.numbers;

public final class NumberUtils {
    private NumberUtils() {
    }

    public static int answer() {
        return 42;
    }
}
~~~

Java 17 không cần external dependencies để compile. `answer()` luôn trả `42` nên stdout trong bài có thể được dự đoán chính xác.

### 4.7. Main `app/build.gradle.kts`

~~~kotlin
plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    // External module notation, không phải project(":number-utils").
    // Composite root sẽ thay thế bằng project ở included build.
    implementation("org.demo:number-utils:1.0.0")
}

application {
    mainClass.set("demo.app.Main")
}
~~~

Consumer **không cần Maven repository** vì dependency có local provider trong composite và không có external transitive dependencies. Nếu bỏ `includeBuild("libraries/number-utils")` khỏi root settings mà giữ dependency này, Gradle cần một repository cung cấp GAV tương ứng (hoặc dependency resolution sẽ thất bại). Điều đó là **thay đổi dependency resolution source**, không phải Java source code.

### 4.8. Main `app/src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.numbers.NumberUtils;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Answer: " + NumberUtils.answer());
    }
}
~~~

### 4.9. Lệnh và output

Linux/macOS, từ `composite-demo` root:

~~~bash
./gradlew :app:run --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run --quiet
~~~

**Stdout do Java Main in ra**:

~~~text
Answer: 42
~~~

Gradle có thể in log khác ngoài stdout của Java tùy môi trường/flags. Cách Gradle xử lý:

1. Root settings include project `app` và build `number-utils`.
2. Consumer declared `org.demo:number-utils:1.0.0`.
3. Included build có root project `group=org.demo`, `name=number-utils`.
4. Auto substitution đổi external module request thành project dependency trong included build.
5. Tasks của included library biên dịch/đóng gói outputs cần thiết cho consumer compile/runtime.
6. Java app chạy và in `Answer: 42`.

Nếu code trong `NumberUtils.answer()` đổi từ 42 thành 43, chạy lại từ composite root sẽ dùng **local source** đã sửa, không đợi bạn publish một JAR mới.

### 4.10. Chạy task trực tiếp trong included build

~~~bash
./gradlew :number-utils:build
./gradlew :number-utils:check
./gradlew checkIncludedLibrary
~~~

Ba lệnh có ý nghĩa khác nhau:

- `:number-utils:build`: chạy lifecycle `build` của root project trong included build `number-utils`.
- `:number-utils:check`: chạy `check` của root project trong included build.
- `checkIncludedLibrary`: chạy root aggregator mà ta tạo, có dependency vào included `:check`.

`:number-utils:build` **không phải** task `:app:build` và không phải task của một subproject `:number-utils` trong main build. Với một included build có subproject `:core`, build-tree task path sẽ có dạng `:number-utils:core:build`.

### 4.11. Kiểm chứng substitution

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencyInsight \
    --configuration runtimeClasspath \
    --dependency number-utils
~~~

Windows PowerShell có thể chạy mỗi lệnh trên một dòng, không dùng dấu `\` line-continuation của Bash.

Kỳ vọng dependency report chỉ ra GAV `org.demo:number-utils:1.0.0` **được thay thế bằng project** của included build. Dòng cụ thể có thể có nhãn `by composite build`, `project :number-utils` hoặc notation khác tùy phiên bản Gradle/định dạng report. **Đừng so sánh toàn bộ report byte-for-byte.**

Khi muốn xem task graph:

~~~bash
./gradlew :app:run --dry-run
~~~

`--dry-run` **không compile hoặc chạy Java**, nhưng có thể quan sát các tasks được chọn, bao gồm tasks của included build cần tạo artifact.

## 5. “Vòng include” và “chu trình dependency” không cùng một điều

Đây là phần quan trọng nhất của bài. Ba đồ thị khác nhau:

| Đồ thị | Các nodes/edges | Ví dụ |
| --- | --- | --- |
| **Inclusion graph** | Build A include Build B | `A/settings.gradle.kts` gọi `includeBuild("../B")` |
| **Dependency graph** | Module/project A cần module B | `implementation("org.demo:b:1.0")` |
| **Task execution graph** | Task A phải chạy sau task B do dependency | `:app:compileJava` cần artifact do `:lib:jar` tạo |

Chúng **có liên hệ**, nhưng không được đánh đồng.

### 5.1. Vòng include A → B → A: có tự động là task cycle không?

Không. Theo Gradle Tooling API, inclusion graph **có thể chứa cycles**, và Gradle có trường hợp **self-inclusion được tài liệu hóa**. Vì vậy câu “Gradle luôn từ chối mọi `includeBuild` quay về build hiện tại” là **không chính xác**.

Nhưng thiết kế một build graph A include B, B include A mà không có lý do rõ ràng vẫn có thể gây:

- Khó biết build nào chịu trách nhiệm định nghĩa substitutions.
- Cấu trúc nested includes bị flatten thành một composite build tree.
- Trùng build-tree paths/names sau flatten.
- Người đọc tưởng B trở thành subproject của A hoặc ngược lại.
- Dependency resolution có unintended substitution qua nhiều builds.
- Task execution cycles thực sự khi modules/tasks tham chiếu qua lại.

**Khuyến nghị kiến trúc:** ở workspace tích hợp, để **một aggregator/main settings** include những independent builds theo một hướng rõ ràng. Chỉ dùng include vòng/self-include khi hiểu đúng cơ chế và có bài kiểm chứng.

### 5.2. Ví dụ inclusion dư thừa cần tránh

~~~text
workspace/
├── settings.gradle.kts     A includes B
├── B/
│   └── settings.gradle.kts B includes A
└── ...
~~~

Ví dụ minh họa *không khuyến nghị*:

~~~kotlin
// A/settings.gradle.kts
includeBuild("B")
~~~

~~~kotlin
// A/B/settings.gradle.kts
includeBuild("..")
~~~

Đừng đưa mẫu này vào project chỉ để khiến cả hai builds “nhìn thấy” nhau. Một build không tự nhận mọi configuration của build kia chỉ nhờ include lẫn nhau. Hãy xác định **dependency direction**, group/name và namespace cần thiết.

Thiết kế dễ quản lý hơn:

~~~kotlin
// A/settings.gradle.kts
includeBuild("B")
~~~

và trong B không include A trừ khi có một use case độc lập, được kiểm thử và tài liệu hóa.

### 5.3. Dependency cycle là lỗi khác

Giả sử:

~~~text
org.demo:alpha -> requires org.demo:beta
org.demo:beta  -> requires org.demo:alpha
~~~

Nếu composite substitution đưa cả hai về local project components, compiler/task graph có thể xuất hiện vòng tương tự:

~~~text
:alpha:compileJava
    requires :beta Java output
        requires :beta:compileJava
            requires :alpha Java output
                -> cycle
~~~

Đó là **chu trình dependency cần thiết để compile** và Gradle có thể báo circular task dependency hoặc dependency resolution problem. Cách giải quyết thực sự là **phá vòng module contract**, không phải đổi include order, tăng `--max-workers` hay thêm `mustRunAfter`.

Ví dụ tổ chức lại:

~~~text
Trước:
  :alpha depends on :beta
  :beta depends on :alpha

Sau:
  :contracts   <- chỉ chứa API/interfaces/data contracts
  :alpha       -> depends on :contracts
  :beta        -> depends on :contracts
  :app         -> composes :alpha và :beta
~~~

Khi hai components buộc phải gọi nhau ở runtime, dùng interfaces/ports + dependency inversion hoặc event callbacks. Quan trọng là module compile dependencies tạo **DAG** thay vì vòng.

### 5.4. Task cycle không chữa bằng `--dry-run`

`--dry-run` vẫn cần Gradle dựng task graph. Nếu graph có chu trình, dry-run không bỏ qua việc phát hiện cycle; nó chỉ không thực thi task actions. Không dùng `-x task` như biện pháp sửa kiến trúc lâu dài: có thể che nhiệm vụ quan trọng nhưng không loại bỏ dependency cycle thực sự.

## 6. Trường hợp đặc biệt: `includeBuild(".")` là self-include hợp lệ

Tài liệu Gradle nêu rằng **main build mặc định không đăng ký module substitution cho chính các projects của nó** theo cùng cách included build. Khi cần cho các builds khác nhìn thấy main build như một provider module dựa trên `group:name`, có một kỹ thuật được hỗ trợ:

~~~kotlin
// settings.gradle.kts của main build, ví dụ minh họa.
includeBuild(".")
~~~

Đây là **self-inclusion có mục đích**, không phải một accidental task cycle. Nó **không** có nghĩa cần thêm `includeBuild(".")` vào mọi composite build, và không làm project trở thành một subproject mới.

Sự khác biệt:

- `includeBuild(".")`: tình huống đặc biệt để đăng ký main build cho dependency substitution theo module identity.
- `A includes B, B includes A`: topology inclusion nhiều builds, dễ tạo coupling hoặc trùng namespace nếu không quản lý.
- `A depends on B, B depends on A`: vòng **dependency/task** có thể gây fail thực sự.

Chỉ dùng self-include khi có yêu cầu rõ về module substitution và đã kiểm chứng behavior với Gradle Wrapper phiên bản của dự án. Đừng thấy “include quay về chính mình” là luôn sai, nhưng cũng không biến nó thành quy ước vô điều kiện.

## 7. Nested composite được flatten: A → B → C không tạo “subbuild namespace” vô hạn

Giả sử:

~~~text
aggregator A
   includes B
      B includes C
~~~

Gradle hiện đại **flatten** nested composite structure: C tham gia cùng build tree với B và A. Không có một task path `:B:C:task` chỉ vì C được B include.

Thông thường, khi included builds có names `B` và `C`:

~~~text
:B:build
:C:build
~~~

thay vì:

~~~text
:B:C:build  (không tự xuất hiện từ include nesting)
~~~

Đây là **mô hình minh họa**; task paths chính xác phụ thuộc tên build, project path và root/subproject tasks thực tế. `:B:C:build` chỉ có ý nghĩa nếu **trong build B** thực sự có subproject `:C` theo cấu trúc của B, không phải do B include build C.

**Hệ quả:** khi A include B, B include C, rồi A lại include C qua đường khác, hãy xem đó là một **build-tree topology cần kiểm tra uniqueness**, không coi C là một “private child” của B được namespace cách ly.

### Về build-name uniqueness

Mọi included build phải có **build path duy nhất** trên toàn build tree. Build path cũng không được trùng **project path** của main build. Nếu tên thư mục/path gây collision, dùng:

~~~kotlin
includeBuild("libs/core") {
    name = "core-lib-build"
}
~~~

Tên `core-lib-build` ở đây đổi **build identity/path** cho included build trong composite, **không tự đổi Maven `group:name` của project** và không tự sửa dependencies của consumer.

## 8. Xung đột build-tree path: giống tên directory dù không cùng nội dung

Ví dụ:

~~~text
workspace/
├── settings.gradle.kts
├── libraries-v1/
│   └── utils/settings.gradle.kts
└── libraries-v2/
    └── utils/settings.gradle.kts
~~~

Settings:

~~~kotlin
rootProject.name = "workspace"

includeBuild("libraries-v1/utils")
includeBuild("libraries-v2/utils")
~~~

Mỗi included build mặc định có build path dựa vào directory name `utils`. Vì **cùng build path `:utils`**, Gradle có thể báo namespace collision. Hai folders khác nhau **không bảo đảm tên build-tree path khác nhau**.

Sửa **build path collision**:

~~~kotlin
rootProject.name = "workspace"

includeBuild("libraries-v1/utils") {
    name = "utils-v1-build"
}

includeBuild("libraries-v2/utils") {
    name = "utils-v2-build"
}
~~~

Lúc này task paths tương ứng có thể là:

~~~text
:utils-v1-build:build
:utils-v2-build:build
~~~

**Nhưng** đây mới là sửa **build-tree path collision**. Nếu hai included builds đều cung cấp **cùng Maven coordinates** `org.demo:utils`, auto substitution có thể vẫn mơ hồ/xung đột về module identity. **Đổi `name` của included build không đồng nghĩa đổi `project.name` hoặc `project.group`.**

### Đè lên main build subproject path

Main settings:

~~~kotlin
include("tools")
includeBuild("external/tools")
~~~

Có thể tạo cả project path `:tools` và included build path `:tools`. Đó là **namespace overlap**, không được giải quyết bằng cách thêm project dependency. Sửa:

~~~kotlin
include("tools")
includeBuild("external/tools") {
    name = "external-tools-build"
}
~~~

Đặt tên included build distinct khỏi root project/subproject paths trên toàn build tree.

## 9. Trùng tọa độ `group:name`: xung đột khác với build-tree path

Automatic substitution trong composite được Gradle xác định bằng **`project.group` và `project.name`**, không cần `project.version` phải bằng version consumer yêu cầu.

Ví dụ:

~~~text
Included build A:
    project.group = "org.demo"
    project.name  = "string-kit"
    project.version = "1.1.0"

Included build B:
    project.group = "org.demo"
    project.name  = "string-kit"
    project.version = "2.0.0"

Consumer:
    implementation("org.demo:string-kit:1.5.0")
~~~

Hai builds có thể có build-tree paths khác nhau, nhưng đều claim **`org.demo:string-kit`**. Đây là **collision về module identity cho substitution**, không phải build path collision.

Hệ quả: resolver không có một provider mang nghĩa duy nhất để thể hiện “`string-kit` của local source nào”; hành vi cụ thể có thể là conflict/error hoặc selection không như mong muốn tùy topology/rules/Gradle version. **Không dựa vào include order để chọn local provider.** Rủi ro đặc biệt cao nếu một bản thực sự là production library, bản kia chỉ là prototype.

Cách an toàn:

1. **Mỗi Maven module identity chỉ có một local provider** trong composite đang chạy, trừ khi bạn chủ đích xây một resolution policy có test rõ.
2. Nếu thực chất là hai **modules khác nhau**, gán group/name khác nhau hoặc đổi rootProject.name/project.name đúng kiến trúc.
3. Nếu là hai versions của **cùng library**, chọn một checkout để include trong một invocation; không coi `project.version` làm bộ chọn auto substitution giữa hai builds cùng group/name.
4. Nếu publisher artifactId khác project.name, thêm **explicit dependency substitution** tương ứng (phần 11), không đổi build path bừa bãi.
5. Luôn kiểm tra `dependencyInsight` xem dependency thực sự được thay bằng project nào.

### Version trong GAV có chọn được local checkout A hay B không?

**Không** theo default auto-substitution matching. Tài liệu Gradle mô tả key dựa trên `group:name`. Vì vậy `implementation("org.demo:string-kit:1.1.0")` **không hứa** Gradle sẽ chọn checkout có `version="1.1.0"` nếu bạn include nhiều providers. Muốn so phiên bản phát hành và local source, quản lý một provider duy nhất hoặc tắt substitution trên configuration thử nghiệm.

## 10. Quên `group` dẫn đến substitution sai

Một project mới có:

~~~kotlin
plugins {
    id("java-library")
}
~~~

nhưng không đặt `group`. Default Gradle group có thể là `unspecified` hoặc giá trị không phải group module mong muốn; Gradle docs minh họa default group là `undefined` trong một ví dụ. Điều cần nhớ **không phải chuỗi mặc định chính xác**, mà là **đừng kỳ vọng library tự cung cấp `org.demo:number-utils` khi chưa đặt group phù hợp**.

Trong included build:

~~~kotlin
group = "org.demo"
version = "1.0.0"
~~~

và trong settings:

~~~kotlin
rootProject.name = "number-utils"
~~~

giúp auto substitution ánh xạ `org.demo:number-utils`.

Nếu include một **multi-project build**, mỗi subproject có `project.group` và `project.name` riêng. Kiểm tra từng project: root group assignment không nhất thiết tự thay đổi group của mọi subproject tùy cách cấu hình. Không mặc định một câu `group = "org.demo"` ở root sẽ làm các subprojects nhất loạt có cùng group trong mọi script/setup.

## 11. Published `artifactId` không giống project.name: explicit substitution

Giả sử included build:

~~~kotlin
// Included build settings.gradle.kts
rootProject.name = "legacy-utility"
~~~

~~~kotlin
// Included build build.gradle.kts
plugins {
    id("java-library")
    id("maven-publish")
}

group = "org.sample"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            artifactId = "number-utils"
            from(components["java"])
        }
    }
}
~~~

Khi publish, Maven coordinates có thể là `org.sample:number-utils:1.0.0`, nhưng **default composite substitution** dựa vào project `group:name` sẽ tìm `org.sample:legacy-utility`. Vì vậy consumer dependency `org.sample:number-utils:1.0.0` có thể không được thay tự động.

Sửa tại **including build settings**:

~~~kotlin
// Main settings.gradle.kts (mảnh ví dụ).
includeBuild("../legacy-utility") {
    dependencySubstitution {
        substitute(module("org.sample:number-utils"))
            .using(project(":"))
    }
}
~~~

`project(":")` **ở đây là root project của included build đang được cấu hình substitution**, không phải root project của main build. Nếu library nằm trong subproject `:api` của included build, dùng `project(":api")`.

**Đừng viết `project(":legacy-utility")` trong consumer buildscript** rồi coi đó là project dependency: included build không phải subproject của main build.

### Tại sao substitution explicit có thể khác behavior với published module?

Composite project substitution thay external module bằng local project’s **default/outgoing component model**. Nếu Maven publication tùy biến sâu — POM chỉnh dependencies, multiple publications, classifier riêng, feature variant chỉ tồn tại trong published metadata — local project variant có thể không giống artifact khi xuất bản thật. Gradle docs nhấn mạnh giới hạn này. Hãy kiểm thử consumer với **published artifact thật** ở CI/release, không chỉ bằng composite.

## 12. Substitution rules không tự truyền qua mọi build boundary

Giả sử A include B với:

~~~kotlin
// A/settings.gradle.kts
includeBuild("../B") {
    dependencySubstitution {
        substitute(module("org.demo:shared"))
            .using(project(":"))
    }
}
~~~

Rule explicit đó chỉ được xác định trong phạm vi build nơi nó được khai báo. Theo Gradle docs, **substitutions không “transitive” giữa các builds** theo nghĩa tự động mang theo mọi explicit mapping sang B như một cấu hình chung cho khi B được chạy độc lập.

Do đó:

- Khi chạy từ A, resolution có thể chọn local project B theo mapping của A.
- Khi chạy `./gradlew` **bên trong thư mục B riêng**, B không tự có rule khai báo trong A.
- Khi một build khác C include B, C phải có own settings/selection context hoặc dùng auto mapping `group:name` phù hợp.

**Giải pháp ưu tiên:** align `project.group` + `project.name` với published module coordinates để auto substitution hoạt động tự nhiên, giảm nhu cầu explicit overrides khác nhau giữa các roots. Chỉ khai báo explicit rules ở aggregator khi thật sự cần và kiểm thử từng invocation context.

## 13. Giữ bản published song song với local source mà không trộn

Trong composite root, dependency `org.demo:number-utils:1.0.0` mặc định có thể bị thay bằng local project, kể cả khi Maven repository cũng có artifact cùng coordinates. Nếu muốn **đối chiếu published JAR với local source**, cần tắt global composite substitution cho configuration được dùng để resolve published binary:

~~~kotlin
// Snippet bổ sung trong một project có Java plugin.
// Không áp dụng cho demo không có repository remote published.
val publishedRuntimeClasspath =
    configurations.create("publishedRuntimeClasspath") {
        isCanBeConsumed = false
        isCanBeResolved = true

        extendsFrom(configurations.runtimeClasspath.get())

        resolutionStrategy.useGlobalDependencySubstitutionRules = false

        attributes {
            attribute(
                Usage.USAGE_ATTRIBUTE,
                objects.named(Usage.JAVA_RUNTIME)
            )
        }
    }
~~~

Snippet cần Gradle API `Usage` được import:

~~~kotlin
import org.gradle.api.attributes.Usage
~~~

Và **consumer phải có repository thực sự chứa bản published**. `useGlobalDependencySubstitutionRules=false` chỉ thay rule resolution cho configuration này, **không tạo artifact trên Maven repository**, cũng không nên áp vô điều kiện lên toàn bộ `runtimeClasspath` của ứng dụng khi bạn đang muốn co-development với local code.

Lưu ý: cấu hình tùy biến có thể cần attributes khác tương ứng với use case, và không nhất thiết giống toàn bộ behavior của `runtimeClasspath`. Hãy kiểm tra bằng `dependencyInsight` và artifact content.

## 14. Phạm vi task: `./gradlew build` có gọi mọi included build không?

**Không mặc định**. Trong multi-project build, unqualified task selector `build` ở root có thể tìm các `build` tasks trong root/subprojects của main build. Nhưng **included builds là các builds riêng**, không tự trở thành subprojects chỉ vì `includeBuild`.

Khi chạy:

~~~bash
./gradlew build
~~~

Gradle có thể thực thi tasks của included library **nếu một main-build task cần dependency artifact từ nó**. Nhưng không có nguyên tắc “mọi `build` tasks của tất cả included builds sẽ chạy”. Nếu bạn cần check/test toàn bộ included builds, hãy gọi chúng rõ ràng hoặc tạo root aggregator.

Ví dụ:

~~~bash
./gradlew :number-utils:build
./gradlew :app:build
~~~

Từng lệnh nhắm task khác nhau. Còn:

~~~bash
./gradlew :app:run
~~~

chạy Java app và chỉ những included-build tasks **cần thiết cho dependency artifact**, không tự gọi `:number-utils:check` hay mọi unit tests của included library chỉ vì nó được include.

### Build root aggregator

Trong composite root:

~~~kotlin
tasks.register("verifyWholeWorkspace") {
    dependsOn(
        gradle.includedBuild("number-utils").task(":check"),
        ":app:check"
    )
}
~~~

Đây là **mảnh bổ sung/thay thế** của root build script demo. `:app:check` thuộc main build; `gradle.includedBuild("number-utils").task(":check")` thuộc included build.

~~~bash
./gradlew verifyWholeWorkspace
~~~

mới diễn đạt cụ thể rằng muốn kiểm tra **cả app và included library** trong một task. Đừng cho rằng `check` của composite root tự làm vậy nếu không có wiring.

## 15. Task CLI: included build và subproject được gọi khác nhau

| Ý định | Cách gọi |
| --- | --- |
| Chạy main build `:app:run` | `./gradlew :app:run` |
| Chạy root project `build` của included build number-utils | `./gradlew :number-utils:build` |
| Chạy `:core:test` trong included build number-utils (nếu có subproject core) | `./gradlew :number-utils:core:test` |
| Chạy root aggregator gọi included task | `./gradlew checkIncludedLibrary` |
| Chạy riêng included build từ thư mục của nó | `cd libraries/number-utils`, rồi `./gradlew build` nếu build có Wrapper riêng, hoặc dùng Gradle installation phù hợp |
| Tạm include một build qua CLI | `./gradlew --include-build ../library :app:run` nếu paths/contexts phù hợp |

**Các task path có dấu `:` đầu tiên thường nhắm vào build-tree root**. Khi đã có nhiều builds, đường dẫn qualified rõ ràng giúp tránh task-name ambiguity.

### API task reference

~~~kotlin
tasks.register("allIncludedChecks") {
    dependsOn(
        gradle.includedBuild("number-utils").task(":check")
    )
}
~~~

`gradle.includedBuild("number-utils")` cần đúng **included build name** hiện hành. Nếu settings đã đổi:

~~~kotlin
includeBuild("libraries/number-utils") {
    name = "local-number-utils"
}
~~~

thì API reference phù hợp là:

~~~kotlin
gradle.includedBuild("local-number-utils").task(":check")
~~~

**Đổi build name sẽ đổi build-tree task path và IncludedBuild lookup**, nhưng không nhất thiết đổi Maven module identity.

## 16. `project(":included:subproject")` không truy cập được included project

Một sai lầm:

~~~kotlin
// Trong main build:
dependencies {
    implementation(project(":number-utils"))
}
~~~

Nếu `number-utils` là **included build** chứ không phải main subproject, Gradle có thể báo `UnknownProjectException` hoặc project path not found. Nó không phải lỗi Gradle chưa "nhìn thấy folder"; là **sai loại reference**.

Cách đúng:

~~~kotlin
dependencies {
    implementation("org.demo:number-utils:1.0.0")
}
~~~

với included library `group="org.demo"`, `rootProject.name="number-utils"` và includeBuild đúng. Gradle tự thay thành local project dependency cho resolution khi GAV khớp.

Một **task** có thể được tham chiếu qua `gradle.includedBuild(...).task(...)`. Một **module dependency** cần notation theo `group:name:version` hoặc explicit substitution policy. Hai loại reference này không thay thế nhau.

## 17. Build tree uniqueness và coordinates uniqueness: hai trục hoàn toàn khác

| Tình huống | Loại xung đột | Sửa bằng |
| --- | --- | --- |
| Hai included builds cùng build path `:utils` | **Build-tree path collision** | `includeBuild(path) { name="..." }` |
| Included build path `:tools` đè main subproject `:tools` | **Namespace overlap** | Rename included build path hoặc project path |
| Hai projects ở hai builds có cùng `org.demo:utils` | **Module substitution identity collision** | Unique group/name hoặc chỉ include một provider |
| Consumer GAV `org.demo:utils` nhưng included project group `unspecified` | **Mismatched coordinates** | Khai báo group/name đúng hoặc explicit substitution |
| Publication artifactId khác project name | **Published vs local identity mismatch** | Explicit `dependencySubstitution` |
| Task `:utils:build` nhắm sai project do hiểu nhầm scope | **Task path ambiguity** | Dùng fully qualified build-tree path, inspect projects/tasks |
| A depends on B, B depends on A | **Module/task dependency cycle** | Phá vòng bằng shared contracts hoặc dependency inversion |
| A includes B, B includes A | **Inclusion topology vòng/khó quản lý** | Tập trung include tại aggregator, không khẳng định luôn bị cấm |

**Không áp dụng một fix cho mọi lỗi tên trùng.** Đổi `includeBuild { name = ... }` có thể chữa build path collision nhưng **không sửa `group:name`**. Đổi `artifactId` Maven publication có thể sửa release identity nhưng **không tự đổi auto substitution key**. Thay `project(":x")` bằng `implementation("g:x:v")` giải quyết đúng build boundary nhưng vẫn cần provider coordinates hợp lệ.

## 18. Kiểm tra project/group/name trong included build

Dùng ở root composite:

~~~bash
./gradlew projects
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency number-utils
./gradlew :number-utils:tasks --all
~~~

Nếu muốn xem metadata group/name của included root, có thể cấu hình một diagnostic task **trong included build**:

~~~kotlin
// Snippet đặt trong libraries/number-utils/build.gradle.kts.
tasks.register("showModuleIdentity") {
    val moduleGroup = project.group.toString()
    val moduleName = project.name
    val moduleVersion = project.version.toString()

    doLast {
        println(
            "module=" + moduleGroup + ":" +
            moduleName + ":" + moduleVersion
        )
    }
}
~~~

Sau khi thêm snippet:

~~~bash
./gradlew :number-utils:showModuleIdentity --quiet
~~~

Stdout theo demo:

~~~text
module=org.demo:number-utils:1.0.0
~~~

Đoạn trên **lấy giá trị identity ở configuration time**, chỉ truyền captured primitive strings vào `doLast`. Đây là diagnostic task bổ sung, không cần để demo chính chạy được. Nếu dùng Configuration Cache nghiêm ngặt, tránh đọc `project` model từ chính task action; việc lấy dữ liệu vào strings trước action minh họa một hướng an toàn hơn.

Từ `:app`, `dependencyInsight` kiểm tra **selected component** (local project vs external module) tốt hơn chỉ nhìn tên JAR trong `build/libs`.

## 19. Không lẫn repositories, properties và settings giữa các builds

Mỗi included build là một build **cấu hình cô lập**. Vì vậy:

- `repositories { ... }` trong main build không tự xuất hiện trong included build.
- `pluginManagement.repositories` của root không tự được mọi included build dùng như một global block.
- `libs.versions.toml` của main build không tự áp dụng cho mọi included build.
- User-defined Gradle properties trong root `gradle.properties` không tự có mặt trong included build settings, theo hướng dẫn Gradle.
- CLI `-Pname=value` và system properties có cơ chế truyền qua invocation riêng; đừng nhầm chúng với file properties của từng build.
- Gradle runtime properties như `org.gradle.configuration-cache` là trường hợp có quy tắc riêng, thường được đọc từ root build cho toàn invocation.

**Include không phải merge settings.** Khi một included library chạy độc lập, nó cần plugin/repository/toolchain versions đủ để tự build. Nếu một build chỉ hoạt động khi được include bởi root có configuration toàn cục, nó chưa thật sự độc lập theo mục đích composite.

### Cách chia sẻ build logic hợp lý

Một included build `build-logic` thường chứa **convention plugins** áp dụng các quy ước code style, Java toolchain, repositories policy... Khi plugins cần dùng trong `plugins { }`, Gradle cho phép plugin build được include qua `pluginManagement { includeBuild(...) }` theo đúng use case.

Ví dụ:

~~~kotlin
// settings.gradle.kts của main build:
pluginManagement {
    includeBuild("build-logic")
}

plugins {
    // Plugin settings nếu build-logic cung cấp, tùy dự án.
}
~~~

Mảnh này chỉ minh họa vị trí include plugin build; chưa có plugin implementation nên không là demo chạy độc lập. Đừng lặp `includeBuild("build-logic")` trong chính `build-logic/settings.gradle.kts` chỉ để plugin build thấy lại chính nó.

## 20. Plugin build include và library build include có mục đích khác

Có hai tình huống:

1. **Local library co-development:** `includeBuild("../number-utils")` ở main settings, consumer dùng `implementation("org.demo:number-utils:1.0.0")` và Gradle module substitution.
2. **Local Gradle plugin resolution:** `pluginManagement { includeBuild("build-logic") }` cho các plugin IDs được định nghĩa trong included plugin build.

Nếu plugin áp dụng trong chính **settings file**, include plugin build trong `pluginManagement` trước `plugins` thường là cách chính thức. Dùng `--include-build` trên CLI cho một plugin chưa publish không luôn hoạt động tin cậy với modern `plugins { }` syntax.

**Tránh vòng plugin dependency:** một build logic plugin không nên đòi một plugin khác mà để build được plugin đó lại phụ thuộc chính build logic ban đầu. Đây là vòng **bootstrap/dependency** khác với việc root settings vô tình include trùng folder. Phá vòng bằng một build logic layer nền tảng nhỏ, dùng plugin version đã publish cho bootstrap hoặc tách shared interfaces ra module không phụ thuộc ngược.

## 21. Parallel Gradle invocations dùng cùng included directory

Tài liệu Gradle nêu một hạn chế: **nhiều composite builds chạy trong các Gradle invocations khác nhau và cùng include một build directory có thể xung đột**, vì không có bảo đảm chia sẻ project lock trên mọi invocations của shared included build.

Ví dụ CI khởi chạy song song:

~~~text
Job A: workspace-A/settings.gradle.kts includeBuild("../shared-number-utils")
Job B: workspace-B/settings.gradle.kts includeBuild("../shared-number-utils")
~~~

Nếu hai jobs thực sự dùng **cùng filesystem checkout** của `shared-number-utils` và cùng output `build/`, một bên có thể xóa/ghi output khi bên kia đang compile. `--parallel` của một Gradle invocation **không** tự giải quyết cross-invocation synchronization.

Chiến lược:

- Mỗi CI job dùng **checkout/work directory riêng**.
- Không cho nhiều invocations chạy `clean`/`build` đồng thời vào cùng included build directory.
- Nếu buộc dùng chung một checkout, có cấp độ serialization/locking từ CI/orchestration.
- Phân biệt Gradle Build Cache (chia sẻ artifacts cache đã được tính đúng) với việc nhiều jobs cùng ghi trực tiếp **build output directory**; đây là hai bài toán khác nhau.

## 22. Cách điều tra một lỗi “circular dependency” thực tế

Lỗi được báo có thể tương tự:

~~~text
Circular dependency between the following tasks:
    :alpha:compileJava
    ...
    :beta:compileJava
    ...
~~~

Đây là **mẫu mô tả**, không phải output từ bản demo hoàn chỉnh. Khi gặp, đi từ task graph về dependency graph:

1. Xác định **task đầu tiên lặp lại** trong cycle report.
2. Nhận ra task thuộc **build nào** theo qualified path.
3. Xác định dependency nào kéo output của build/project còn lại vào compile/runtime.
4. Dùng `dependencies` và `dependencyInsight` tại configuration đã resolve.
5. Kiểm tra auto substitution: module nào được thay bằng local project?
6. Nếu hai builds include lẫn nhau, **không tự kết luận include cycle là nguyên nhân**; phải kiểm tra module/task edges tạo vòng thực sự.
7. Sửa dependency direction/API contracts; không dùng `mustRunAfter` để thay `dependsOn` khi task B cung cấp input bắt buộc của A.
8. Chạy lại task nhỏ nhất và regression test ở composite root.

Một vòng dependency thường phải sửa bằng **tách interface/contracts**, service boundary hoặc thay đổi layer architecture. Đổi tên included build path chỉ làm task path khác, không giải quyết vòng bytecode compilation.

## 23. Cách điều tra một lỗi tên trùng

Nếu Gradle báo included build/path collision:

~~~text
Hai included builds có tên utils
hoặc included build :tools trùng project path :tools
~~~

Đây là **tình huống ví dụ**, không khẳng định thông báo lỗi chính xác. Quy trình:

1. Liệt kê mọi `includeBuild(...)` trong **settings files có tham gia** (đọc source của chính dự án thực tế).
2. Ghi build paths mặc định theo **directory names**, không theo toàn bộ relative path.
3. Ghi main build project paths từ `include(...)`.
4. So sánh mọi build-tree paths sau khi tính cả nested includes (vì chúng được flatten).
5. Gán unique included build names bằng `includeBuild(path) { name = "..." }` khi phù hợp.
6. Chạy `./gradlew projects` hoặc qualified task `help` để kiểm tra identity rõ.
7. Sau đó **kiểm tra độc lập `group:name`** để tránh nhầm build path fix với module substitution fix.

Nếu gặp dependency substitution sai provider:

1. Dùng `:app:dependencyInsight` để xác nhận actual selected component.
2. Kiểm tra `group`/`name` của tất cả projects trong included builds.
3. Có duplicate `group:name` không? Nếu có, chỉ include provider thực sự mong muốn.
4. Có Maven published artifactId khác `project.name` không? Nếu có, dùng explicit substitution mapping.
5. Có đang cần published binary, không phải local source không? Hãy tắt composite substitution cho **configuration cần so sánh**, không dọn toàn bộ builds một cách mù quáng.

## 24. CLI task name selector: đừng suy ra scope chỉ từ tên trần

Ở multi-project build, lệnh:

~~~bash
./gradlew test
~~~

từ root có thể chọn task tên `test` ở các subprojects thích hợp trong **main build hierarchy**. Nhưng included builds **không trở thành root subprojects** của main build. Vì vậy không suy luận `test` sẽ tự chạy tất cả tests của mọi included build.

Để chỉ định rõ:

~~~bash
./gradlew :app:test
./gradlew :number-utils:test
~~~

Hoặc:

~~~bash
./gradlew :number-utils:check
~~~

Nếu một included build có root project tên `number-utils` nhưng chứa subproject `:math`:

~~~bash
./gradlew :number-utils:math:test
~~~

**Không dựa vào shorthand/abbreviation** trong CI khi tên task/build có thể thêm mới và trở nên ambiguous. Dùng fully qualified build-tree task path để log và release pipelines dễ hiểu.

### Khi root không có `build` task

Trong demo, root `build.gradle.kts` chỉ đăng ký `checkIncludedLibrary`; nó không áp dụng Java plugin ở root. Khi gọi bare `./gradlew build`, Gradle có thể chọn `build` của `:app` trong main build theo task selector, nhưng không có root `:build` nếu root không có plugin tạo lifecycle task đó. Đừng mô tả sai rằng root `:build` lúc nào cũng tồn tại.

## 25. Trường hợp dependency substitution làm thay đổi version thực dùng

Giả sử consumer:

~~~kotlin
dependencies {
    implementation("org.demo:number-utils:9.9.9")
}
~~~

Included local library:

~~~kotlin
group = "org.demo"
version = "1.0.0"
~~~

**Default composite substitution** dựa vào `group:name`, không so khớp version như một ràng buộc chọn local checkout. Do đó local project có thể được chọn **ngay khi consumer yêu cầu một version rất khác**.

Điều này hữu ích khi đang phát triển fix chưa publish, nhưng nguy hiểm nếu CI release cần kiểm tra exact published artifact version. Cách kiểm soát:

- Phân tách **co-development composite tests** với **published artifact compatibility tests**.
- Dùng dependency reports để nhận ra substitution.
- Với published smoke test, chạy build **không include** local provider hoặc tắt substitution trên configuration phù hợp.
- Khi cố định published versions, dùng dependency locking/verification như nhu cầu project và test từ registry thật.
- Không ghi “đã xác minh external version 9.9.9” khi thực tế build đã dùng local version 1.0.0.

## 26. Dùng `--include-build` tạm thời mà không tạo include vòng dư

Khi repository chính không muốn commit quan hệ include dài hạn:

~~~bash
./gradlew --include-build ../number-utils :app:run
~~~

Lệnh này phù hợp khi `../number-utils` là checkout Gradle build hợp lệ và main build đã khai báo dependency GAV phù hợp. Cách này tránh sửa main settings cho một thử nghiệm ngắn.

Nhưng chú ý:

- Nếu main settings **đã include cùng build**, thường không cần `--include-build` nữa.
- CLI include không phải giải pháp sửa group/name mismatch.
- Nếu có hai local checkouts cùng coordinate, đừng include cả hai chỉ vì “thử version”.
- Với plugin resolution qua modern `plugins { }`, ưu tiên settings/pluginManagement include đúng cách.
- Trong CI, dùng settings topology rõ ràng hơn là chuỗi flags tùy hứng khiến các jobs khó tái lập.

## 27. Những anti-pattern cần nhận diện

| Anti-pattern | Vì sao sai hoặc rủi ro | Thay bằng |
| --- | --- | --- |
| `include("number-utils")` khi ý định là include cả Gradle build độc lập | Trộn một project với một build có settings riêng | `includeBuild("libraries/number-utils")` |
| `project(":number-utils")` từ app để tham chiếu included library | Included build không thuộc project hierarchy main build | `implementation("group:name:version")` + substitution |
| `implementation("group:name:version")` nhưng quên group/name ở included build | Auto substitution không match | Đặt `group` và `rootProject.name`/`project.name` hoặc explicit mapping |
| Hai included builds cùng directory name `utils` | Build-tree path conflict | Đặt unique `includeBuild { name = ... }` |
| Đổi build path rồi tưởng đã sửa duplicate GAV | Hai namespace khác nhau | Đặt unique group/name/chỉ include một provider |
| A include B và B include A vô điều kiện | Topology khó quản lý, dễ trùng/implicit substitution | Aggregator root include builds theo hướng rõ |
| Coi mọi inclusion cycle là task cycle | Không đúng Gradle semantics, self-include được hỗ trợ | Xem graph riêng, đọc task cycle report |
| Chạy `./gradlew build` rồi tưởng toàn bộ included builds đều `build` | Root task selector không tự traverse mọi builds | Explicit qualified tasks/aggregator |
| `:app:run` và `:included:app:run` bị coi là một | Task thuộc build khác nhau | Fully qualified build-tree paths |
| `dependsOn(project(":included").tasks...)` | Cross-build Project access không phù hợp | `gradle.includedBuild("...").task(":...")` |
| Tạo task circular dependency giữa included builds | Task graph không có thứ tự topo hợp lệ | Phá vòng kiến trúc/API contracts |
| Dùng `mustRunAfter` để “sửa” vòng phụ thuộc dữ liệu | Ordering rule không cung cấp dữ liệu/task selection | Giữ dependency đúng và refactor |
| Gộp root `gradle.properties` vào included build bằng suy đoán | Included build properties/config cô lập | CLI properties, environment hoặc convention plugin |
| Test published artifact khi composite substitution vẫn bật | Thực tế đang dùng local project | Tắt substitution cho config/test build phù hợp |
| Hai CI jobs ghi chung một included build output | Race giữa Gradle invocations | Isolated workspaces hoặc CI-level locking |

## 28. Bài tập tự kiểm tra

**Câu 1.** `include("lib")` và `includeBuild("lib")` khác nhau gì?

**Đáp:** `include` thêm subproject vào project hierarchy **của cùng build**; `includeBuild` thêm một **build riêng**, có settings và projects độc lập.

**Câu 2.** Included build có group `org.demo` và rootProject.name `number-utils`. App dùng notation nào?

**Đáp:** `implementation("org.demo:number-utils:1.0.0")` hoặc version phù hợp theo contract. Không dùng `project(":number-utils")` nếu nó không phải main subproject.

**Câu 3.** Consumer yêu cầu version 2.0, local included build có version 1.0. Auto substitution có đòi versions bằng nhau không?

**Đáp:** Không theo default `group:name` matching. Phải kiểm tra dependency report, tránh tưởng đã tải published 2.0.

**Câu 4.** Hai included builds đều có directory name cuối `utils` nhưng path khác nhau, vì sao vẫn nguy hiểm?

**Đáp:** Included build path mặc định dựa vào directory name, nên có thể cùng `:utils` và gây build-tree path collision. Đặt unique included build names.

**Câu 5.** Rename `includeBuild("...") { name="utils-v2" }` đã giải quyết hai library cùng `org.demo:utils` chưa?

**Đáp:** Chưa. Đổi build path không đồng nghĩa đổi Maven `group:name`. Cần giải quyết provider identity/substitution riêng.

**Câu 6.** A includes B, B includes A có phải lúc nào Gradle đều báo task cycle không?

**Đáp:** Không. Inclusion graph và task dependency graph khác nhau, Gradle có trường hợp cyclic inclusion/self-inclusion được hỗ trợ. Chỉ dependency/task cycle thực mới cần refactor edges.

**Câu 7.** `includeBuild(".")` có phải luôn sai?

**Đáp:** Không. Gradle tài liệu hóa self-inclusion để main build tham gia substitution. Chỉ dùng khi có mục đích rõ.

**Câu 8.** A includes B, B includes C. Task C được gọi bằng `:B:C:build` hay `:C:build`?

**Đáp:** Nested composite được flatten; nếu C là một **included build riêng tên C**, build-tree path thường là `:C:build`. `:B:C:build` chỉ dùng nếu B có subproject `:C` tương ứng.

**Câu 9.** `./gradlew build` có tự build/test mọi included build không?

**Đáp:** Không. Included build tasks được chạy khi dependency cần hoặc khi được gọi explicitly qua qualified paths/aggregator.

**Câu 10.** Cú pháp nào tạo task dependency tới `:check` của included build `number-utils`?

**Đáp:** `dependsOn(gradle.includedBuild("number-utils").task(":check"))` trong một task main build.

**Câu 11.** Vì sao `project(":number-utils")` từ main build không chỉ tới root project of included build?

**Đáp:** Mỗi build có project hierarchy độc lập. Included build không phải root subproject, cần external coordinates cho module dependency hoặc IncludedBuild task reference cho task dependency.

**Câu 12.** Khi published artifactId khác project.name, auto substitution có tự hiểu artifactId không?

**Đáp:** Không mặc định. Dùng `includeBuild(path) { dependencySubstitution { substitute(module("g:a")).using(project(":")) } }` đúng project target.

**Câu 13.** Vì sao cần giữ test co-development và published-binary test tách nhau?

**Đáp:** Composite có thể thay Maven dependency thành local project dù version khác, khiến bạn tưởng đang test published artifact khi thực tế test local source.

**Câu 14.** Hai CI jobs include cùng filesystem checkout, có thể xung đột không?

**Đáp:** Có. Gradle docs cảnh báo không có bảo đảm shared included-build project lock xuyên các invocations. Dùng workspaces riêng hoặc khóa CI-level.

**Câu 15.** Root settings có `includeBuild` thư viện nhưng root `build.gradle.kts` không có Java plugin. `:build` chắc chắn tồn tại không?

**Đáp:** Không. Task selector `build` có thể chạy subprojects có task này, nhưng root `:build` chỉ tồn tại nếu plugin/task được đăng ký tại root.

## 29. Quy trình sửa sự cố trong thực tế

### Trường hợp A — Gradle báo trùng build path

1. Xác định mọi included build directory names trong settings của composite tree.
2. Tính build-tree paths sau khi flatten nested builds.
3. So sánh với main root/subproject paths.
4. Đặt unique `includeBuild { name = ... }`.
5. Rerun `projects`/qualified task.
6. Sau đó kiểm tra `group:name` riêng, vì build path fix không giải quyết substitution identity collision.

### Trường hợp B — Library local không được thay thế

1. Xác nhận included build có settings hợp lệ.
2. Kiểm tra `group` và `project.name`.
3. So với GAV consumer.
4. Dùng `dependencyInsight` để xem selected component.
5. Nếu published artifactId khác project name, dùng explicit substitution.
6. Kiểm tra variant metadata/default component tương thích published artifact.

### Trường hợp C — Circular task dependency

1. Đọc danh sách tasks trong error để xác định exact cycle.
2. Tìm dependency edges từ Java compile classpaths/task inputs.
3. Kiểm tra composite substitution có đưa modules vào graph như dự kiến không.
4. Không mặc định quy cho `includeBuild` loop.
5. Phá vòng bằng common API/contracts module hoặc refactor layer direction.
6. Chạy lại task cụ thể, sau đó integration build.

### Trường hợp D — Task không chạy như mong đợi

1. Phân biệt task thuộc main build hay included build.
2. Dùng fully qualified path.
3. Nếu cần nhiều included-build checks, tạo aggregator với `gradle.includedBuild(...).task(...)`.
4. Dùng `--dry-run` để xem graph, không coi đó là xác minh test đã chạy.
5. Tránh `--parallel`/`-x` như “cách sửa” selection bug.

### Trường hợp E — CI đang lấy nhầm phiên bản

1. Dùng `dependencyInsight` xác nhận substitution reason.
2. Kiểm tra có duplicate local providers không.
3. Tách published smoke test khỏi composite test.
4. Dùng repository thực và tắt substitution ở configuration kiểm thử khi cần.
5. Khóa verified versions/metadata theo release policy.

## 30. Checklist trước khi merge thay đổi Composite Build

- [ ] Phân biệt `include` subprojects và `includeBuild` independent builds.
- [ ] Mỗi included build có settings file/root project identity rõ.
- [ ] Không include vòng vô điều kiện; topology được giữ tối giản và tài liệu hóa.
- [ ] Không nhầm inclusion graph với dependency/task graph.
- [ ] Build-tree paths của included builds duy nhất sau nested flatten.
- [ ] Không có included build path trùng main subproject path.
- [ ] Mọi local provider có unique `group:name` theo mục đích.
- [ ] Không dựa vào `version` để chọn giữa hai local checkouts cùng group/name.
- [ ] Khi published artifactId khác project.name, explicit substitution chính xác.
- [ ] Included builds không cần đọc Project model từ main build để hoạt động.
- [ ] Main build không tham chiếu `project(":included")` trái build boundary.
- [ ] Task paths trong CI fully qualified, không suy rằng bare `build` gọi mọi included build.
- [ ] Cross-build task dependencies dùng `gradle.includedBuild(name).task(path)`.
- [ ] Main và included builds có repositories/plugin management/properties đúng phạm vi.
- [ ] Có consumer test chứng minh auto substitution dùng local source đúng.
- [ ] Có published-binary test để tránh hiểu nhầm version do substitution.
- [ ] Không chạy nhiều CI jobs ghi chung included build output directory.
- [ ] Dùng Gradle Wrapper version được hỗ trợ, kiểm tra trước khi nâng.
- [ ] Đã chạy `dependencies`/`dependencyInsight` với đúng configuration.
- [ ] Đã chạy test của từng included build nếu release policy yêu cầu.
- [ ] Không áp dụng `mustRunAfter` hoặc `-x` để che dependency cycle.

## 31. Tài liệu Gradle chính thức

- [Gradle — Composite Builds (Included Builds)](https://docs.gradle.org/current/userguide/composite_builds.html): `includeBuild`, nested builds, task paths, substitutions, self-include, uniqueness requirements, limitations và composite isolation.
- [Gradle — Structuring and Organizing Gradle Projects](https://docs.gradle.org/current/userguide/organizing_gradle_projects.html): phân biệt multi-project và composite build.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds_intermediate.html): project paths và task selectors.
- [Gradle — Using Resolution Rules](https://docs.gradle.org/current/userguide/dependency_management.html): module/project substitution và dependency graph.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight`.
- [Gradle — Dependency Graph Resolution](https://docs.gradle.org/current/userguide/dependency_graph_resolution.html): dependency graph, conflicts, artifact selection.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): convention plugin build logic và cấu trúc project.
- [Gradle — IncludedBuild API](https://docs.gradle.org/current/javadoc/org/gradle/api/initialization/IncludedBuild.html): `getName()` và `task(String)`.
- [Gradle Tooling API — GradleBuild.getIncludedBuilds](https://docs.gradle.org/current/javadoc/org/gradle/tooling/model/gradle/GradleBuild.html): inclusion graph có thể chứa cycles; không tự đồng nhất với task cycle.
