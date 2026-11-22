# Vai trò của Settings, Project và Gradle trong từng giai đoạn của vòng đời build

Khi chạy `./gradlew build`, Gradle **không lập tức biên dịch mã Java**. Trước tiên, Gradle xác định build gồm những project nào; sau đó cấu hình từng project và tính những task cần thực hiện; cuối cùng mới chạy những task đã chọn. Ba giai đoạn này lần lượt là **Initialization**, **Configuration** và **Execution**.

Để hiểu đúng cơ chế, cần phân biệt ba đối tượng trong Gradle API:

- **`Settings`**: mô tả **cấu trúc của một build**, đặc biệt là root project, các subproject và included build.
- **`Project`**: mô hình của **mỗi project** trong build, chứa plugins, dependencies, tasks và các thuộc tính cấu hình.
- **`Gradle`**: đối tượng đại diện cho **một phiên thực hiện build của Gradle**, cung cấp ngữ cảnh điều phối và các điểm móc (*lifecycle hooks*) trong quá trình chạy.

Ba đối tượng có quan hệ chặt chẽ nhưng **không đồng nghĩa với ba giai đoạn**. `Gradle` tham gia điều phối toàn bộ build, `Settings` nổi bật ở Initialization, còn `Project` được tạo sau khi nạp settings và được cấu hình trong Configuration. Ở Execution, Gradle chạy **các task**, chứ không “chạy lại build.gradle”.

## 1. Bức tranh tổng quan: đối tượng nào làm việc gì?

| Đối tượng | Có bao nhiêu trong một build thông thường? | Nơi thường cấu hình/truy cập | Trách nhiệm chính |
| --- | --- | --- | --- |
| `Gradle` (`org.gradle.api.invocation.Gradle`) | Một đối tượng đại diện cho build hiện tại | Biến `gradle` trong settings/build scripts, init script hoặc plugin | Điều phối vòng đời, nắm tham số chạy (`startParameter`), root project sau khi được tạo, lifecycle callbacks |
| `Settings` (`org.gradle.api.initialization.Settings`) | Một cho mỗi settings script/build | `settings.gradle` hoặc `settings.gradle.kts` | Xác định tên root, `include` subprojects, `includeBuild`, plugin management, chính sách repositories |
| `Project` (`org.gradle.api.Project`) | Một cho **mỗi project** trong build: root và từng subproject | `build.gradle` hoặc `build.gradle.kts` của project đó; project plugins | Áp dụng plugins, khai báo dependencies, đăng ký/configure tasks, đặt group/version/Java toolchain và cấu hình riêng của project |

Ví dụ `settings.gradle` có `include 'app', 'lib'` thì build có **ba Project objects**: root `:`, `:app` và `:lib`. Nó không phải ba đối tượng `Settings`. Mỗi project có thể có `build.gradle` riêng, nhưng file này không bắt buộc phải tồn tại để Gradle tạo `Project`.

**Chú ý phạm vi:** ở một **composite build** sử dụng `includeBuild`, mỗi included build có settings và tập project riêng. Đừng cộng mọi project từ các included builds rồi hiểu rằng chúng cùng thuộc một `Settings` duy nhất.

### Sơ đồ dòng dữ liệu

```text
CLI / Gradle Wrapper: ./gradlew :app:run
              |
              v
        Gradle build invocation
              |
   [1] INITIALIZATION
        init scripts (nếu có)
        Settings: settings.gradle(.kts)
          - rootProject.name
          - include(':app', ':lib')
          - includeBuild(...) nếu có
              |
              v
        Project descriptors
              |
              v
        Project(:), Project(:app), Project(:lib)
              |
   [2] CONFIGURATION
        evaluate build.gradle(.kts) / apply plugins
        -> register/configure tasks, dependencies, extensions
        -> chọn task và xây task execution graph
              |
   [3] EXECUTION
        chạy task actions trong graph khi cần
        -> outputs, reports, artifacts, tests...
```

**Project graph** ở Initialization (cấu trúc `:`, `:app`, `:lib`) **khác task graph** ở Configuration (ví dụ `:lib:jar` phải trước `:app:compileJava` nếu có quan hệ phụ thuộc thích hợp). Đây là hai loại quan hệ khác nhau.

## 2. Giai đoạn 1 — Initialization: Settings khai báo “build này gồm những ai?”

Khi được khởi chạy, Gradle phân tích tham số CLI, tìm build/settings và chạy init scripts áp dụng (nếu có). Gradle tạo một `Settings` instance rồi đánh giá `settings.gradle` hoặc `settings.gradle.kts`. Các lệnh trong settings script khai báo cây project; Gradle dùng mô tả này để tạo các đối tượng `Project`.

Ví dụ Groovy DSL ở `settings.gradle`:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = 'shop'
include 'app', 'domain', 'infra'
```

Điều đó có nghĩa:

- `rootProject.name = 'shop'` đặt **tên** root project. **Đường dẫn Gradle** của root vẫn là `:`.
- `include 'app', 'domain', 'infra'` khai báo ba subproject với path `:app`, `:domain`, `:infra`. Theo mặc định, thư mục tương ứng là `app/`, `domain/`, `infra/`.
- `pluginManagement.repositories` cho Gradle biết nơi **tìm plugin**; nó không tương đương `repositories` để giải quyết dependencies thông thường cho code ứng dụng.

Tại thời điểm thực thi settings script, `Settings` có thể thao tác với `ProjectDescriptor` — **mô tả** project, gồm name, path, projectDir, buildFileName — nhưng **chưa phải một `Project` đã được cấu hình từ build script**.

Ví dụ sau đây hợp lệ trong `settings.gradle`:

```groovy
include 'app'
project(':app').projectDir = file('applications/mobile-app')
```

Ở đây `project(':app')` thuộc **API của Settings** nên trả về **`ProjectDescriptor`** và câu lệnh đặt vị trí thư mục cho project. Trong một `build.gradle`, lời gọi `project(':app')` lại nằm trong ngữ cảnh **Project API** và đề cập đến một project trong build. Cùng cú pháp bề ngoài, nhưng đối tượng và thời điểm sử dụng khác nhau.

Từ Gradle 9, project directory được khai báo bằng `include` cần tồn tại và ghi được; phiên bản cũ có thể xử lý thiếu directory khác. Hãy đảm bảo cấu trúc thư mục khớp với settings khi tạo multi-project build.

### Settings còn quản lý điều gì?

| Cấu hình trong settings | Tác dụng |
| --- | --- |
| `rootProject.name` | Đặt tên root project của build |
| `include('app', 'lib')` | Tạo các subproject **trong cùng build** |
| `project(':app').projectDir` | Chỉ định thư mục thực của một subproject |
| `includeBuild('build-logic')` | Gắn **một build khác** vào composite build; không tạo subproject bình thường trong build hiện tại |
| `pluginManagement { ... }` | Chọn nơi/tùy chọn phân giải plugins, kể cả plugin versions hoặc plugin build |
| `dependencyResolutionManagement { ... }` | Quản lý repositories và quy tắc resolution dành cho các project |

`Settings` **không phải nơi thích hợp để viết `tasks.register('compile')` cho `:app`**: task thuộc `Project`, được khai báo trong build script hoặc plugin áp dụng vào project. `Settings` có thể áp dụng *Settings plugins*, nhưng chúng khác với *Project plugins*.

**Một build luôn có root project.** Ngay cả khi không `include` project con, Gradle vẫn có root project `:`. Tên root có thể được suy ra từ tên thư mục nếu không được đặt rõ, nhưng đặt `rootProject.name` giúp cấu trúc build ổn định khi di chuyển thư mục.

## 3. Giai đoạn 2 — Configuration: Project xác định “mỗi project có thể làm gì?”

Sau Initialization, Gradle đã biết cây project và tạo các `Project` instances. Trong Configuration, Gradle đánh giá build script tương ứng (nếu có) và các plugin được áp dụng vào project, để xây **mô hình build**.

Ví dụ `app/build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':domain')
}

tasks.register('sayHello') {
    doLast {
        println 'Hello from :app:sayHello'
    }
}
```

Tại Configuration:

1. Gradle đánh giá plugin declaration và áp dụng Java plugin lên **Project `:app`**; plugin có thể đăng ký thêm task như `compileJava`, `test`, `jar`.
2. Các thuộc tính của project được thiết lập (`group`, `version`); dependencies và repositories được khai báo.
3. `tasks.register('sayHello')` **đăng ký** task một cách lazy qua `TaskProvider`.
4. Closure `doLast { ... }` chỉ mô tả **hành động chạy sau này**, không làm câu `println` bên trong thực thi ngay trong lúc đọc build script.

Một chi tiết quan trọng: closure truyền cho `tasks.register('sayHello')` là **closure cấu hình task**, có thể chỉ chạy khi Gradle cần *realize* task, chứ không nhất thiết ngay tại dòng đăng ký. Ngược lại, closure `doLast` là **task action**, chạy ở Execution nếu task được lên lịch và thực sự thực hiện hành động.

### Những thứ thuộc Project

- **`project.path`**: định danh trong cây build, ví dụ `:`, `:app`, `:domain`.
- **`project.name`**, **`project.projectDir`**, **`project.rootProject`**, **`project.parent`**: tên, thư mục, root và cha của project.
- **`project.plugins`**, **`project.extensions`**: plugin và các DSL extension, chẳng hạn `java { ... }`.
- **`project.configurations`**, **`project.dependencies`**: cấu hình và dependency model.
- **`project.tasks`**: task container của **project đó**.

Các thành phần này là **mô hình cấu hình**. Ví dụ `implementation project(':domain')` khai báo dependency giữa projects; từ đó Gradle hoặc các plugins xây quan hệ artifact/classpath/task cần thiết. Nó không có nghĩa câu lệnh này lập tức compile `:domain`.

### Project cấu hình trước, task thực thi sau

```groovy
// build.gradle — bản minh họa ngắn
println '[CONFIG] evaluating root project'

tasks.register('demo') {
    println '[TASK CONFIG] configuring demo'

    doLast {
        println '[EXEC] running demo'
    }
}
```

Nếu chạy `./gradlew demo --no-configuration-cache -q`, ba dòng tương ứng xuất hiện: dòng đầu khi build script được đánh giá; dòng thứ hai khi task `demo` được realized/configured; dòng thứ ba khi `demo` được thực thi. Với `./gradlew help --no-configuration-cache -q`, dòng `[CONFIG]` xuất hiện, nhưng **không nhất thiết xuất hiện `[TASK CONFIG]`** vì task `demo` không được yêu cầu, và **không có `[EXEC] running demo`**.

Đây chính là lý do nên ưu tiên `tasks.register` và tránh ép task được tạo/configure sớm khi không cần. Cấu hình nhiều việc nặng ở build script khiến cả `help` hoặc `tasks` cũng chậm.

### Ai chọn task?

Yêu cầu CLI như `./gradlew :app:build` xác định task mục tiêu. Gradle kết hợp yêu cầu đó với task definitions, dependencies (`dependsOn`, plugin wiring, implicit input/output dependencies, v.v.) để tính **task execution graph**.

```text
Project :domain    -> task :domain:compileJava
                                      |
                                      v
Project :app       -> task :app:compileJava
                                      |
                                      v
                         task :app:classes
                                      |
                                      v
                         task :app:jar  (nếu nằm trong graph)
```

Sơ đồ minh họa mối quan hệ có thể phát sinh; task graph thực tế phụ thuộc plugins, task được yêu cầu và dependency/artifact wiring của project. **Không suy ra rằng mọi task trong mọi project đều chạy** chỉ vì chúng được đăng ký.

## 4. Giai đoạn 3 — Execution: Gradle điều phối task actions

Ở Execution, Gradle lấy task graph đã tính và xử lý các task cần thiết theo quan hệ phụ thuộc và điều kiện thực tế.

Một task có thể:

- Chạy action `doFirst`, `doLast`, hoặc action do plugin cung cấp (ví dụ `JavaCompile`).
- Được đánh dấu **`UP-TO-DATE`** nếu inputs/outputs đã phù hợp.
- Lấy output từ **build cache** (`FROM-CACHE`) khi được cấu hình và đủ điều kiện.
- Được bỏ qua (`SKIPPED`, `NO-SOURCE`) tùy điều kiện và loại task.
- Thất bại, làm build thất bại (trừ các chính sách xử lý lỗi phù hợp).

`Project` vẫn là mô hình sở hữu task, nhưng nó **không chạy toàn bộ source code trong project như một chương trình**. Một task như `compileJava` gọi compiler; `test` chạy tests; task tự định nghĩa thực hiện logic trong task action.

**Quan hệ phụ thuộc đảm bảo thứ tự cần thiết**, không bảo đảm mọi task có thứ tự tuyến tính toàn cục. Hai task độc lập có thể được thực thi song song theo khả năng và cấu hình Gradle. Nếu kết quả build đòi hỏi thứ tự, cần biểu diễn bằng dependency hoặc quan hệ task thích hợp, không dựa vào “lệnh nào được khai báo trước trong build.gradle”.

### Phân biệt việc đăng ký task với thực thi task

```groovy
tasks.register('prepare') {
    doLast {
        println 'prepare executed'
    }
}

tasks.register('publishLocal') {
    dependsOn 'prepare'
    doLast {
        println 'publishLocal executed'
    }
}
```

Chạy:

```bash
./gradlew publishLocal --no-configuration-cache -q
```

Trong project ví dụ chỉ có hai task này và không có logic in bổ sung, stdout của **task actions** là:

```text
prepare executed
publishLocal executed
```

Nếu chạy `./gradlew prepare --no-configuration-cache -q`, task `publishLocal` không thực thi, dù nó đã được đăng ký. Chạy `./gradlew publishLocal --dry-run` giúp xem tasks được chọn và thứ tự dự kiến mà không thực thi actions; kết quả của `--dry-run` có thể kèm trạng thái console khác theo Gradle version.

## 5. Vai trò riêng của đối tượng Gradle xuyên suốt các giai đoạn

`Gradle` không phải **JDK**, **Gradle distribution** hay **Gradle Daemon** (tiến trình JVM chạy engine). Nó là **đối tượng API** `org.gradle.api.invocation.Gradle` đại diện cho **build đang được thực hiện**.

Một số thông tin và sự kiện thông dụng:

| API/điểm móc | Gắn với thời điểm nào? | Dùng để làm gì? |
| --- | --- | --- |
| `gradle.startParameter.taskNames` | Tham số đầu vào của lời gọi build | Biết task names người dùng yêu cầu qua CLI; **chưa phải** toàn bộ task graph |
| `gradle.gradleVersion` | Ngữ cảnh build | Biết Gradle version đang thực thi |
| `gradle.settingsEvaluated { ... }` | Sau khi settings được đánh giá | Quan sát/cấu hình bổ sung lúc đã có Settings hoàn chỉnh |
| `gradle.projectsLoaded { ... }` | Sau khi tạo hierarchy của các `Project` | Lúc các Project instances tồn tại nhưng chưa được đánh giá build scripts |
| `gradle.projectsEvaluated { ... }` | Sau khi các project scripts đã được đánh giá | Quan sát cấu hình trước khi graph được hoàn thiện |
| `gradle.rootProject` | Sau khi project hierarchy đã được tạo | Tham chiếu root Project của build hiện tại |
| `gradle.lifecycle.beforeProject { ... }` và `afterProject { ... }` | Trước/sau việc đánh giá một project, trên phiên bản Gradle hỗ trợ API này | Hook cấu hình; áp dụng thận trọng với compatibility/performance |

Các callback là điểm móc theo thời điểm, **không thay thế** việc khai báo source of truth trong settings và project build scripts. Trong build hiện đại, có thể tránh hooks toàn cục khi chỉ cần triển khai convention plugin hoặc dùng task configuration avoidance.

### Ví dụ ghi dấu một số sự kiện, chỉ dành cho chẩn đoán

Tạo file `observe.init.gradle` ở một thư mục thử nghiệm (Groovy DSL):

```groovy
gradle.settingsEvaluated { settings ->
    println '[HOOK] settingsEvaluated: ' + settings.rootProject.name
}

gradle.projectsLoaded { currentBuild ->
    println '[HOOK] projectsLoaded: ' + currentBuild.rootProject.path
}

gradle.projectsEvaluated { currentBuild ->
    println '[HOOK] projectsEvaluated: ' + currentBuild.rootProject.path
}
```

Chạy từ root một Gradle project đã có Wrapper:

```bash
./gradlew -I observe.init.gradle help --no-configuration-cache -q
```

Các dòng do callback sinh ra sẽ có thứ tự logic:

```text
[HOOK] settingsEvaluated: <ten-root-project>
[HOOK] projectsLoaded: :
[HOOK] projectsEvaluated: :
```

`<ten-root-project>` là ký hiệu cần thay bằng tên thật (không phải stdout nguyên văn). Trong nhiều project, `projectsLoaded` chỉ cho biết **các Project objects đã tồn tại**, không có nghĩa `build.gradle` của từng project đã được đánh giá. `projectsEvaluated` chạy sau các bước cấu hình tương ứng, **trước Execution**.

Đây là kỹ thuật quan sát trong môi trường thử nghiệm; không nên áp dụng vô điều kiện các callbacks/listeners vào build production. Một số hook có hạn chế hoặc không chạy lại khi dùng **Configuration Cache**; khi cần phát triển plugin phải đối chiếu tài liệu API và compatibility requirements của phiên bản Gradle cụ thể. Ví dụ trên chủ động dùng `--no-configuration-cache` để minh họa đường đi cấu hình thông thường.

## 6. Ví dụ hoàn chỉnh: một Gradle build có root, core và app

Ví dụ này chỉ dùng Gradle Groovy DSL, không cần plugin ngoài hay mã Java. Mục đích là quan sát **Settings → Project → Task Execution** với các task do chính ta định nghĩa.

### 6.1. Cấu trúc thư mục

```text
lifecycle-demo/
├── settings.gradle
├── build.gradle
├── core/
│   └── build.gradle
├── app/
│   └── build.gradle
├── gradlew                       # sử dụng Wrapper nếu đã tạo
├── gradlew.bat
└── gradle/wrapper/...            # các tệp Wrapper
```

Dùng một project đã có Gradle Wrapper hoặc tạo Wrapper hợp lệ theo tài liệu chính thức. Nếu cấu trúc thiếu Wrapper, có thể chạy các lệnh tương ứng bằng bản `gradle` đã cài sẵn, nhưng trong repository thực tế nên quản lý Wrapper.

### 6.2. `settings.gradle` — cấu trúc build

```groovy
rootProject.name = 'lifecycle-demo'
include 'core', 'app'

println '[INIT] Settings declared root/core/app'
println '[INIT] Gradle requested tasks: ' + gradle.startParameter.taskNames
```

Đây là **Settings script**. Lời gọi `include` đăng ký hai subprojects. Trong settings script, biến `gradle` cho phép quan sát ngữ cảnh build và task được yêu cầu; nó **không nói rằng task đó đã được chạy**.

### 6.3. `build.gradle` của root — cấu hình root Project

```groovy
println '[CONFIG] Project ' + project.path
```

`project.path` của root là `:`. Dòng `println` nằm ở cấp trên cùng của build script nên chạy khi Gradle **đánh giá root Project** trong Configuration.

### 6.4. `core/build.gradle` — task của core Project

```groovy
println '[CONFIG] Project ' + project.path

tasks.register('hello') {
    doLast {
        println '[EXEC] :core:hello'
    }
}
```

`:core:hello` được đăng ký trong Project `:core`; `println` bên trong `doLast` chỉ chạy khi task thực thi.

### 6.5. `app/build.gradle` — task phụ thuộc task ở core

```groovy
println '[CONFIG] Project ' + project.path

tasks.register('hello') {
    dependsOn ':core:hello'

    doLast {
        println '[EXEC] :app:hello'
    }
}
```

`dependsOn ':core:hello'` tạo dependency **task-to-task** trong ví dụ học tập. Điều này khác với khai báo `implementation project(':core')` để ứng dụng sử dụng Java API/artefact của core.

### 6.6. Chạy ví dụ

Trên Linux/macOS:

```bash
./gradlew :app:hello --no-configuration-cache --console=plain -q
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat :app:hello --no-configuration-cache --console=plain -q
```

Trong cấu hình thông thường không bật configuration on demand hoặc isolated-project optimizations, những nhóm dòng sau sẽ xuất hiện:

```text
[INIT] Settings declared root/core/app
[INIT] Gradle requested tasks: [:app:hello]
[CONFIG] Project :
[CONFIG] Project :core
[CONFIG] Project :app
[EXEC] :core:hello
[EXEC] :app:hello
```

Đây là **output minh họa cho cách chạy nêu trên**. Các dòng `[CONFIG]` và thứ tự/tập project được cấu hình có thể chịu ảnh hưởng của phiên bản và các tùy chọn tối ưu configuration; thứ tự quan trọng được bảo đảm bởi ví dụ là `[EXEC] :core:hello` **trước** `[EXEC] :app:hello` nhờ `dependsOn`. Dòng `[INIT] Gradle requested tasks: [:app:hello]` chỉ phản ánh **task người dùng yêu cầu**, nên không liệt kê `:core:hello` dù Gradle sẽ chạy task này.

Có thể đổi lệnh thành:

```bash
./gradlew :core:hello --no-configuration-cache --console=plain -q
```

Khi đó **chỉ action** `[EXEC] :core:hello` được chạy; task `:app:hello` không chạy. Gradle vẫn trải qua Initialization và Configuration cần thiết. Nếu mục tiêu là quan sát sự kiện của Gradle độc lập với task tự tạo, có thể dùng `help` nhưng cần nhớ các plugin và cache có thể làm output khác.

### Kết luận từ ví dụ

- **Settings** nhận lời gọi `include` và xây cấu trúc root/core/app.
- **Gradle** biết CLI đã yêu cầu `:app:hello` và điều phối quá trình từ cấu hình sang task graph.
- **Project :core** đăng ký task `:core:hello`, còn **Project :app** đăng ký task `:app:hello` và quan hệ phụ thuộc.
- **Execution** chạy `:core:hello` trước `:app:hello`. Không có nhiệm vụ nào trong ví dụ đòi hỏi biên dịch Java, vì không áp dụng Java plugin.

## 7. So sánh câu lệnh theo thời điểm thực thi

| Đoạn mã | Đặt trong file nào? | Pha thường tác động? | Hiểu đúng |
| --- | --- | --- | --- |
| `rootProject.name = 'shop'` | `settings.gradle` | Initialization | Thay đổi tên root project descriptor |
| `include 'app'` | `settings.gradle` | Initialization | Đưa `:app` vào project hierarchy |
| `println 'settings'` ở top-level Settings script | `settings.gradle` | Initialization | In khi đánh giá Settings |
| `println 'build'` ở top-level build script | `build.gradle` | Configuration | In khi đánh giá Project đó |
| `plugins { id 'java' }` | `build.gradle` | Configuration | Áp dụng plugin, bổ sung model/task conventions |
| `tasks.register('x')` | `build.gradle` | Configuration | Đăng ký task lazily; không thực thi task |
| `println` trong closure cấu hình task | `tasks.register('x') { ... }` | Configuration, khi task được realized | Có thể không chạy nếu task không cần được cấu hình |
| `doLast { println 'x' }` | Định nghĩa task | Execution | In khi task action thật sự chạy |
| `dependsOn ':core:x'` | Định nghĩa task | Được khai báo lúc configuration; ảnh hưởng task graph | Khai báo task upstream, không thực thi ngay |
| `gradle.projectsLoaded { ... }` | Init/settings script hoặc plugin phù hợp | Sau project hierarchy được tạo | Quan sát sự kiện; project scripts chưa chắc đã được đánh giá |

**Đừng dựa vào tên script để suy ra tác động.** Một build script được **đánh giá** trong Configuration nhưng có thể **đăng ký hành động** chạy sau này ở Execution. Ngược lại, cấu hình task ngay trong vòng lặp top-level là công việc Configuration và có thể làm chậm build ngay cả khi task không được chọn.

## 8. Configuration Cache làm thay đổi điều gì?

Cách nói “Gradle luôn đánh giá settings rồi build.gradle ở mọi lần chạy” là **không chính xác khi Configuration Cache có cache hit**.

Về mặt mô hình, build vẫn có ba phần Initialization → Configuration → Execution, nhưng khi bật **Configuration Cache**:

1. **Cache miss:** Gradle đánh giá các script và tính cấu hình/task graph cần thiết; dữ liệu cấu hình được lưu để sử dụng sau.
2. **Cache hit:** Gradle có thể nạp lại task graph từ cache, **bỏ qua việc đánh giá lại settings/build scripts và các callbacks cấu hình** trong lần chạy đó.
3. Các task đã chọn vẫn được thực hiện hoặc được bỏ qua/reuse output theo up-to-date checks và build cache. Configuration Cache **khác** Build Cache: một cái lưu **cấu hình và task graph**, cái kia lưu **task outputs**.

Trong bài học, các `println` ở top-level settings/build scripts phục vụ quan sát thời điểm, **không phải thiết kế logging có thể tin cậy trên cache hit**. Dùng `--no-configuration-cache` để thực hành đường đi thông thường như phần ví dụ, sau đó thử bật cache trên project tương thích để thấy khác biệt.

Một lỗi thường gặp với Configuration Cache là task action tham chiếu `Project` đang sống ở Execution:

```groovy
// Không khuyến nghị cho task action tương thích Configuration Cache
tasks.register('badExample') {
    doLast {
        println project.name
    }
}
```

Task action có thể không được serialize đúng vì bắt giữ `Project` trong execution-time closure. Với nhu cầu đơn giản có thể cấu hình trước một giá trị plain string rồi dùng giá trị đó trong action, hoặc viết custom task với `@Input` và `Property<String>` theo API để Gradle theo dõi trạng thái một cách an toàn. Đây là lý do ví dụ đầy đủ phía trên in chuỗi cố định trong `doLast`.

Bên cạnh đó, **Configuration on Demand** và **Isolated Projects** có thể điều chỉnh project nào được cấu hình và cách cấu hình. Vì vậy chỉ nên dựa vào **task dependencies, input/output và contracts của Gradle**, không dựa vào việc `:core` chắc chắn luôn được cấu hình trước `:app` trong mọi chế độ.

## 9. Lỗi hay gặp khi phân biệt Settings, Project và Gradle

| Hiện tượng hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| “`settings.gradle` có thể thêm `tasks.register` cho `:app`” | Nhầm `Settings` với `Project` | Khai báo task trong `app/build.gradle` hoặc plugin áp dụng cho `:app` |
| Thêm `include 'app'` vào `build.gradle` | Nhầm giai đoạn khai báo project tree với cấu hình project | Di chuyển `include` vào `settings.gradle` |
| `project(':app')` trong Settings được xem là `Project` đã có tasks | Ở đây đối tượng là `ProjectDescriptor` | Chỉ chỉnh descriptor (name/projectDir/buildFileName); thao tác tasks sau khi tạo `Project` |
| `println` ở top-level build script xuất hiện dù task tùy chỉnh không chạy | Build script chạy ở Configuration | Đưa logic cần chạy cùng task vào task action |
| `doLast` không in dòng nào khi chạy `help` | Task có action đó không nằm trong task execution graph | Yêu cầu task trực tiếp hoặc từ dependencies |
| Muốn mọi subproject task chạy theo thứ tự viết trong settings | `include` quyết định cây projects, không quyết định task ordering | Mô hình hóa task/dependency graph rõ ràng |
| Thấy `:app:hello` chạy sau `:core:hello` nhưng CLI chỉ ghi `:app:hello` | Task graph tự mở rộng dependencies | Kiểm tra `dependsOn`, `--dry-run` và task information |
| Hook `projectsEvaluated` không chạy ở lần build tiếp theo | Configuration Cache hit có thể bỏ qua configuration callbacks | Không dùng callback này cho hành vi cần xảy ra ở mỗi execution |
| Build gặp lỗi do truy cập `project` trong task action khi bật cache | Task action giữ tham chiếu `Project`/state không hỗ trợ serialization | Chuyển thông tin cần dùng thành task inputs/properties được Gradle quản lý |
| `includeBuild` bị hiểu là tạo subproject | Composite build có lifecycle/Settings riêng | Phân biệt `include` (subproject) và `includeBuild` (build riêng) |

## 10. Cách tự quan sát vòng đời bằng CLI

Từ root project có Wrapper, một số lệnh hữu ích:

```bash
./gradlew projects
./gradlew :app:tasks --all
./gradlew help --task :app:hello
./gradlew :app:hello --dry-run
./gradlew :app:hello --no-configuration-cache --info
```

- **`projects`**: xem cây project đã được Settings khai báo, kèm thông tin build phù hợp. Dùng để xác nhận `:app` đã xuất hiện trong build hay chưa.
- **`:app:tasks --all`**: xem các task mà `:app` biết đến. Task được hiển thị chưa có nghĩa nó đã chạy.
- **`help --task :app:hello`**: xem mô tả và thông tin task nếu tồn tại; cú pháp và thông tin chi tiết có thể thay đổi theo Gradle version.
- **`--dry-run`**: tính task graph nhưng bỏ qua task actions; hữu ích khi kiểm tra quan hệ phụ thuộc.
- **`--info`**: cho log chi tiết hơn, giúp phân biệt việc cấu hình project, lựa chọn task và thực hiện task.

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`.

Nếu một lệnh báo không tìm thấy project/task, hãy kiểm tra **đúng root build** đang chạy, `settings.gradle(.kts)` có khai báo project tương ứng hay không, và task có được plugin/build script đăng ký hay không. Đừng suy luận task sẽ xuất hiện chỉ vì có thư mục cùng tên.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Trong `settings.gradle`, `include 'api'` có lập tức compile Java ở `:api` không?

**Đáp:** Không. Nó khai báo subproject `:api`. Sau đó Gradle tạo `Project`, áp dụng build logic, rồi compile chỉ xảy ra nếu task tương ứng thuộc task graph và cần thực thi.

**Câu 2.** `Settings.project(':api')` và `Project.project(':api')` có phải một kiểu trả về?

**Đáp:** Không. Trong Settings, lời gọi dùng `ProjectDescriptor` để mô tả project. Trong Project API, lời gọi nhắm `Project` thuộc build.

**Câu 3.** Vì sao lệnh `./gradlew help` vẫn có thể in log trong `build.gradle`?

**Đáp:** Build scripts được đánh giá ở Configuration, trước khi chạy task `help`. Nhưng với Configuration Cache hit, Gradle có thể bỏ qua đánh giá script, nên log cấu hình không bắt buộc xuất hiện.

**Câu 4.** `gradle.startParameter.taskNames` đã là toàn bộ task graph chưa?

**Đáp:** Chưa. Đây chỉ là danh sách task được yêu cầu (hoặc tham số tương ứng); Gradle sẽ còn thêm task prerequisites thông qua dependencies và wiring của plugins.

**Câu 5.** Có hai project `:app` và `:lib`. Điều gì quyết định task biên dịch thư viện phải chạy trước task biên dịch app?

**Đáp:** Quan hệ phụ thuộc giữa project artifacts/compile classpath và task dependencies mà Gradle/plugin xây dựng từ cấu hình; **không phải** thứ tự hai tên nằm trong `include`.

**Câu 6.** Khi `doLast` có code `println`, code này chạy khi Gradle đọc file `build.gradle` phải không?

**Đáp:** Không. Nó chỉ được thực hiện trong Execution khi task thuộc graph và task action được chạy. Closure dùng để **cấu hình** task có thể chạy sớm hơn, nhưng task action là bước riêng biệt.

## Tài liệu chính thức để đào sâu

- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): ba giai đoạn, task graph và lifecycle callbacks.
- [Gradle — Settings API](https://docs.gradle.org/current/dsl/org.gradle.api.initialization.Settings.html): `Settings`, `ProjectDescriptor`, `include`, cấu trúc multi-project.
- [Gradle — Project API](https://docs.gradle.org/current/dsl/org.gradle.api.Project.html): mô hình và vòng đời `Project`.
- [Gradle — Gradle API](https://docs.gradle.org/current/dsl/org.gradle.api.invocation.Gradle.html): `Gradle` instance, `projectsLoaded`, `projectsEvaluated`.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): root/subprojects và project dependencies.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): cache hit/miss và lý do configuration callbacks có thể không chạy.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): hạn chế khi task actions giữ `Project` hoặc đăng ký listeners.
