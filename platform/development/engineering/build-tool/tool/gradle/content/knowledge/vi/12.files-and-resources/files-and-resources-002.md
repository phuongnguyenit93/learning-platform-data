# Giải quyết đường dẫn tương đối theo Project và layout trong Gradle

## 1. Vì sao cùng một đường dẫn lại trỏ tới file khác nhau?

Trong Gradle, chuỗi `"src/main/resources/config.yml"` hoặc `"data/input.txt"` không tự mang thông tin về vị trí tuyệt đối. Bạn phải biết **đối tượng Gradle nào giải quyết đường dẫn** và **thư mục gốc nào được sử dụng**. Điều này đặc biệt quan trọng trong multi-project build: một project con thường có thư mục riêng, khác với root project và khác với thư mục terminal đang đứng.

Các ý chính cần nắm:

- `Project.file("relative/path")` giải quyết đường dẫn **tương đối với `projectDir` của Project hiện tại**.
- `layout.projectDirectory.file(...)` và `.dir(...)` mô tả file/thư mục **thuộc Project hiện tại** qua API `ProjectLayout`.
- `layout.buildDirectory.file(...)` / `.dir(...)` tạo các Provider cho **đường dẫn output theo build directory**, tránh viết cứng `build/...`.
- `rootProject.file(...)` dùng project root làm gốc. `layout.settingsDirectory` (ở phiên bản Gradle hỗ trợ) chỉ rõ gốc settings.
- `new File("...")` trong Groovy hoặc `File("...")` trong Kotlin/Java **không giống** `Project.file("...")`: chúng dựa vào CWD của JVM khi làm việc với đường dẫn tương đối.
- Với output sinh bởi task khác, nên truyền **output Provider của producer** hoặc khai báo task dependency, không chỉ đoán tên file.

Mục tiêu sau bài học: chọn đúng API cho file nguồn và output, đọc script Groovy/Kotlin DSL, giải thích lỗi file-not-found, và xây một ví dụ multi-project có thể chạy mà không phụ thuộc CWD.

## 2. Bốn “gốc đường dẫn” khác nhau trong Gradle

| Thư mục | Cách tham chiếu | Ý nghĩa |
| --- | --- | --- |
| Project hiện tại | `project.projectDir` hoặc `layout.projectDirectory` | Thư mục của `:app` khi script thuộc project `:app`. |
| Root project | `rootProject.projectDir` hoặc `rootProject.layout.projectDirectory` | Thư mục project `:` trong build. |
| Settings directory | `settingsDir` trong Settings; `layout.settingsDirectory` nếu Gradle version hỗ trợ | Nơi chứa script settings; thường trùng thư mục root trong build thông thường. |
| CWD của JVM/terminal | `System.getProperty("user.dir")`, `File("relative")` dùng trực tiếp | Không được Gradle cam kết luôn là root hay projectDir. |

Ví dụ:

```text
workspace/
└── my-build/
    ├── settings.gradle.kts
    ├── shared/
    │   └── config.txt
    ├── app/
    │   ├── build.gradle.kts
    │   └── data/
    │       └── input.txt
    └── lib/
        ├── build.gradle.kts
        └── data/
            └── input.txt
```

Trong `settings.gradle.kts`:

```kotlin
rootProject.name = "my-build"
include(":app", ":lib")
```

Ở `app/build.gradle.kts`, ba lời gọi sau giải quyết tới **ba vị trí khác nhau**:

```kotlin
val local = file("data/input.txt")                   // my-build/app/data/input.txt
val shared = rootProject.file("shared/config.txt")   // my-build/shared/config.txt
val wrong = file("shared/config.txt")                // my-build/app/shared/config.txt
```

Cùng chuỗi `"data/input.txt"` trong `lib/build.gradle.kts` sẽ trỏ `my-build/lib/data/input.txt`. Do đó hãy xác định project path (`:`, `:app`, `:lib`) trước khi sửa đường dẫn.

**Chú ý:** settings script là ngữ cảnh `Settings`, build script là ngữ cảnh `Project`. Không giả định một API như `project.file` có mặt và hoạt động giống hệt trong tất cả loại script.

## 3. Project.file(): giải quyết một file theo Project

`file(Object)` của `Project` trả về một `java.io.File` đã được giải quyết. Đối số có thể là chuỗi, File, Path hoặc các dạng mà Gradle hỗ trợ. Quy tắc cốt lõi:

- Đường dẫn **tương đối** → theo `project.projectDir` của project sở hữu lời gọi.
- Đường dẫn **tuyệt đối** → giữ vị trí tuyệt đối theo semantics của resolver.
- API **không tạo file** chỉ vì bạn tham chiếu đến nó. Một `File` có thể biểu diễn path không tồn tại.

### Groovy DSL — build.gradle

```groovy
def sourceFile = file('src/main/resources/app.properties')
def sourceDir = file('src/main/resources')
def rootConfig = rootProject.file('shared/config.txt')

println sourceFile.name
println sourceDir.isDirectory()
println rootConfig.absolutePath
```

### Kotlin DSL — build.gradle.kts

```kotlin
val sourceFile = file("src/main/resources/app.properties")
val sourceDir = file("src/main/resources")
val rootConfig = rootProject.file("shared/config.txt")

println(sourceFile.name)
println(sourceDir.isDirectory)
println(rootConfig.absolutePath)
```

Đây là các **đoạn minh họa cách lấy path**, không phải chương trình yêu cầu những file đó phải tồn tại. `sourceDir.isDirectory()` đọc trạng thái filesystem lúc được gọi; nếu ở cấp script thì thao tác xảy ra ở giai đoạn configuration. Đừng dùng `exists()`/`isDirectory()` để tạo side effect hoặc quyết định phụ thuộc của task mà không hiểu thời điểm chạy.

### Vì sao new File("...") gây lỗi?

```groovy
// Cách không nên dùng để định vị input của Project:
def unsafe = new File('src/main/resources/app.properties')

// Cách dùng Gradle resolver:
def safe = file('src/main/resources/app.properties')
```

```kotlin
// Không nên dùng làm đường dẫn input của Project:
val unsafe = java.io.File("src/main/resources/app.properties")

// Relative path được Gradle giải quyết theo projectDir:
val safe = file("src/main/resources/app.properties")
```

Đối tượng `unsafe` còn là đường dẫn tương đối theo CWD khi bạn dùng API Java để đọc. CWD không phải một quy ước ổn định của Gradle build. Ngược lại, `safe` được giải quyết theo projectDir. Bạn cũng có thể truyền một `File` tương đối *vào* `Project.file(...)` để Gradle giải quyết, nhưng đừng dùng `File("...").readText()` trực tiếp với giả định CWD sẽ luôn đúng.

## 4. Project.files() và FileCollection cho nhiều nguồn

Khi cần nhiều file, `files(...)` hoặc `layout.files(...)` trả về một `FileCollection`. Các đường dẫn tương đối của những API này cũng được giải quyết theo project hiện tại.

**Groovy:**

```groovy
def configs = files('config/app.yml', 'config/logger.yml')
```

**Kotlin:**

```kotlin
val configs = files("config/app.yml", "config/logger.yml")
```

FileCollection hữu ích khi cấu hình `inputs.files(configs)` hoặc truyền tập file vào task. Nó biểu diễn **tập vị trí file**, không bảo đảm chúng tồn tại.

Với mẫu đệ quy, dùng `fileTree(...)`:

**Groovy:**

```groovy
def documentation = fileTree('docs') {
    include '**/*.md'
    exclude '**/draft/**'
}
```

**Kotlin:**

```kotlin
val documentation = fileTree("docs") {
    include("**/*.md")
    exclude("**/draft/**")
}
```

`docs` là thư mục trong project hiện tại. FileTree khác File đơn: nó có thể khớp nhiều file theo include/exclude. Nội dung file thực tế còn phụ thuộc filesystem tại thời điểm Gradle duyệt tập tin.

## 5. ProjectLayout: projectDirectory và buildDirectory

`layout` trong build script là `ProjectLayout`. Nó cho phép mô tả những vị trí thường gặp bằng đối tượng/Provider của Gradle, thay vì tự ghép các chuỗi path.

**Kotlin:**

```kotlin
// Các đường dẫn nguồn trong thư mục project hiện tại.
val input = layout.projectDirectory.file("data/input.txt")
val sourceFolder = layout.projectDirectory.dir("data")

// Đường dẫn output theo cấu hình build directory hiện hành.
val report = layout.buildDirectory.file("reports/summary.txt")
val reportFolder = layout.buildDirectory.dir("reports")
```

**Groovy:**

```groovy
def input = layout.projectDirectory.file('data/input.txt')
def sourceFolder = layout.projectDirectory.dir('data')

def report = layout.buildDirectory.file('reports/summary.txt')
def reportFolder = layout.buildDirectory.dir('reports')
```

### Kiểu trả về và điều phải nhớ

| Biểu thức | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `file("data/input.txt")` | `File` | File path đã giải quyết theo projectDir. |
| `layout.projectDirectory` | `Directory` | Vị trí thư mục Project. |
| `layout.projectDirectory.file("data/input.txt")` | `RegularFile` | Vị trí file thuộc project. |
| `layout.projectDirectory.dir("data")` | `Directory` | Vị trí thư mục thuộc project. |
| `layout.buildDirectory` | `DirectoryProperty` | Property cấu hình vị trí output build. |
| `layout.buildDirectory.file("reports/x.txt")` | `Provider<RegularFile>` | File output dựa trên vị trí buildDirectory. |
| `layout.buildDirectory.dir("reports")` | `Provider<Directory>` | Thư mục output dựa trên buildDirectory. |

Khi cần đối tượng `File`, `RegularFile.asFile` trả về file path Java; với `Provider<RegularFile>`, `provider.get().asFile` lấy giá trị tại lúc yêu cầu. Tuy nhiên, **nếu API Gradle nhận Provider thì hãy truyền Provider trực tiếp**, đừng gọi `get()` sớm chỉ để đổi thành `File`.

### Location không có nghĩa là file đã tồn tại

`layout.projectDirectory.file("data/input.txt")` không tự tạo `data/input.txt`. Tương tự, `layout.buildDirectory.file("reports/x.txt")` không tự sinh báo cáo. Phải có file nguồn thật hoặc task producer tạo output thì việc đọc/copy mới có nội dung.

## 6. Vì sao output nên theo layout.buildDirectory?

Giả sử `:app` có build directory mặc định là `app/build`. Hai biểu thức này *có thể* cho cùng vị trí ban đầu:

```kotlin
val hardcoded = file("build/reports/summary.txt")
val managed = layout.buildDirectory.file("reports/summary.txt")
```

Nhưng khi đổi build directory thành `app/out`, `hardcoded` vẫn trỏ `app/build/reports/summary.txt`; `managed` theo cấu hình `app/out/reports/summary.txt`.

Trong Kotlin DSL:

```kotlin
layout.buildDirectory.set(layout.projectDirectory.dir("out"))
val managed = layout.buildDirectory.file("reports/summary.txt")
```

Trong Groovy DSL:

```groovy
layout.buildDirectory.set(layout.projectDirectory.dir('out'))
def managed = layout.buildDirectory.file('reports/summary.txt')
```

Cả hai dùng `DirectoryProperty.set(...)` của Gradle. Nếu task producer cũng viết vào `layout.buildDirectory.dir("reports")`, consumer dùng `managed` sẽ tìm cùng vị trí khi build directory thay đổi.

**Khuyến nghị thực tế:** ưu tiên *output property của task tạo file* (ví dụ `RegularFileProperty`/`DirectoryProperty`) để xác định đường dẫn đầu ra, bởi nó có thể mang cả thông tin quan hệ producer → consumer. `layout.buildDirectory.file(...)` tự nó chỉ cho **vị trí**, không tự biết task nào sẽ ghi file đó.

## 7. Ví dụ runnable đa project: root, module và output task

Ví dụ này không cần dependency ngoài: chỉ dùng Gradle built-in `Copy` task. Chọn **một DSL** cho mỗi script: Groovy `*.gradle` hoặc Kotlin `*.gradle.kts`. Dùng Gradle Wrapper/JDK tương thích.

### 7.1. Cấu trúc thư mục

Tạo cây sau:

```text
path-layout-lab/
├── settings.gradle[.kts]
├── shared/
│   └── banner.txt
└── app/
    ├── build.gradle[.kts]
    └── data/
        └── message.txt
```

Tạo file `shared/banner.txt` ở **root**, chứa đúng dòng:

```text
Chào từ root!
```

Tạo file `app/data/message.txt` ở **module :app**, chứa đúng dòng:

```text
Xin chào từ app!
```

Lưu UTF-8; có hoặc không có dấu xuống dòng cuối file đều được vì mã đọc dùng `trim()`.

### 7.2. Groovy DSL — hai build script

**`settings.gradle`:**

```groovy
rootProject.name = 'path-layout-lab'
include 'app'
```

**`app/build.gradle`:**

```groovy
// Nguồn trong project :app.
def sourceFile = layout.projectDirectory.file('data/message.txt')

// Nguồn trong root project, không nằm trong app.
def sharedFile = rootProject.layout.projectDirectory.file('shared/banner.txt')

// Provider chỉ vị trí output của project :app.
def copiedFile = layout.buildDirectory.file('staged/message.txt')

// Task Copy sử dụng location từ ProjectLayout.
def stageMessage = tasks.register('stageMessage', Copy) {
    group = 'learning'
    from(sourceFile)
    into(layout.buildDirectory.dir('staged'))
}

// Đọc hai nguồn riêng; task này không sinh output.
tasks.register('readSources') {
    group = 'learning'
    inputs.files(sourceFile, sharedFile)

    doLast {
        println "local=${sourceFile.asFile.getText('UTF-8').trim()}"
        println "shared=${sharedFile.asFile.getText('UTF-8').trim()}"
    }
}

// Đọc file sau khi producer task Copy hoàn thành.
tasks.register('showStagedMessage') {
    group = 'learning'
    dependsOn(stageMessage)
    inputs.file(copiedFile)

    doLast {
        def content = copiedFile.get().asFile.getText('UTF-8').trim()
        println "copied=${content}"
    }
}
```

### 7.3. Kotlin DSL tương đương

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "path-layout-lab"
include(":app")
```

**`app/build.gradle.kts`:**

```kotlin
val sourceFile = layout.projectDirectory.file("data/message.txt")
val sharedFile = rootProject.layout.projectDirectory.file("shared/banner.txt")
val copiedFile = layout.buildDirectory.file("staged/message.txt")

val stageMessage = tasks.register<Copy>("stageMessage") {
    group = "learning"
    from(sourceFile)
    into(layout.buildDirectory.dir("staged"))
}

tasks.register("readSources") {
    group = "learning"
    inputs.files(sourceFile, sharedFile)

    doLast {
        println("local=${sourceFile.asFile.readText(Charsets.UTF_8).trim()}")
        println("shared=${sharedFile.asFile.readText(Charsets.UTF_8).trim()}")
    }
}

tasks.register("showStagedMessage") {
    group = "learning"
    dependsOn(stageMessage)
    inputs.file(copiedFile)

    doLast {
        val content = copiedFile.get().asFile.readText(Charsets.UTF_8).trim()
        println("copied=$content")
    }
}
```

**Tại sao ví dụ đúng?**

1. `sourceFile` có gốc `layout.projectDirectory` của `:app` → `path-layout-lab/app/data/message.txt`.
2. `sharedFile` được lấy từ `rootProject.layout.projectDirectory` → `path-layout-lab/shared/banner.txt`.
3. `copiedFile` dựa trên `layout.buildDirectory` của `:app` → mặc định `path-layout-lab/app/build/staged/message.txt`.
4. `stageMessage` dùng `Copy.from(sourceFile)` và `into(layout.buildDirectory.dir("staged"))` nên viết đúng nơi `showStagedMessage` sẽ đọc.
5. `showStagedMessage` khai báo `dependsOn(stageMessage)` để Gradle thực thi producer trước; khai báo `inputs.file(copiedFile)` để mô tả input. Một Provider path **không tự chứng minh** quan hệ dependency với producer.

### 7.4. Chạy và đối chiếu stdout

Từ root `path-layout-lab`, khi có Gradle Wrapper:

```bash
./gradlew -q :app:readSources
./gradlew -q :app:showStagedMessage
```

Trên Windows, dùng `gradlew.bat`. Nếu thư mục học tập chưa có Wrapper mà bạn đã cài Gradle, có thể chạy `gradle wrapper` tại root để tạo wrapper trước khi dùng các lệnh trên.

**Stdout của `:app:readSources`:**

```text
local=Xin chào từ app!
shared=Chào từ root!
```

**Stdout của `:app:showStagedMessage`:**

```text
copied=Xin chào từ app!
```

Task `Copy` không có `println` nên với `-q` nó không tạo thêm dòng stdout của ví dụ. Nếu cache/task state khác nhau, Gradle có thể hiển thị thông tin riêng khi đổi mức log, nhưng nội dung do script in phải đúng như trên.

**Thử nghiệm đổi build directory:** trong `app/build.gradle.kts` có thể thêm `layout.buildDirectory.set(layout.projectDirectory.dir("out"))` ở đầu script; với Groovy dùng dòng tương ứng từ mục 6. Chạy lại `:app:showStagedMessage`, file được copy vào `app/out/staged/message.txt` và consumer vẫn đọc được, không cần sửa path `staged/message.txt`. Sau khi quan sát, bỏ dòng thay đổi để quay về mặc định nếu muốn.

## 8. Nơi chứa settings và cách chọn nguồn chung

Trong build tiêu chuẩn, settings file thường ở root. Nhưng **settings directory** và **root project directory** vẫn là hai khái niệm khác nhau, đặc biệt với tùy chỉnh cấu trúc và included builds.

Nếu Gradle Wrapper hỗ trợ `ProjectLayout.settingsDirectory`, bạn có thể biểu thị đường dẫn theo settings:

**Kotlin:**

```kotlin
val shared = layout.settingsDirectory.file("shared/banner.txt")
```

**Groovy:**

```groovy
def shared = layout.settingsDirectory.file('shared/banner.txt')
```

Như vậy bạn không cần dựa vào `"../shared/banner.txt"` của module. Tuy nhiên, đừng sao chép API từ trang tài liệu Gradle phiên bản mới mà không đối chiếu Wrapper version của build cũ. Nếu đang dùng cách qua `rootProject`, hãy đảm bảo file đó thật sự thuộc root project; với **Isolated Projects**, truy cập model của project khác có thể bị hạn chế và cần thay bằng API phù hợp.

Trường hợp nguồn do **project khác sản xuất**, ví dụ `:core` tạo JAR để `:app` dùng, không nên tự đọc `../core/build/libs/...`. Hãy khai báo `implementation(project(":core"))` hoặc API artifact/task output phù hợp; Gradle mới có đủ thông tin về variant, dependency graph và producer task.

## 9. Copy và child CopySpec: không phải chuỗi relative nào cũng cùng gốc

Một `Copy` task có `from` xác định nguồn và `into` ở cấp task xác định **root destination**:

```kotlin
tasks.register<Copy>("copyDocs") {
    from(layout.projectDirectory.dir("docs"))
    include("**/*.md")
    into(layout.buildDirectory.dir("copied-docs"))
}
```

Đoạn Groovy tương đương:

```groovy
tasks.register('copyDocs', Copy) {
    from layout.projectDirectory.dir('docs')
    include '**/*.md'
    into layout.buildDirectory.dir('copied-docs')
}
```

Cần có file thật ở `docs` thì task mới có nội dung để copy. Dùng `layout.buildDirectory` cho đích giúp output đi theo project configuration.

**Nhưng** có một điểm tinh tế: `into("css")` khi nằm trong một **child CopySpec** là đường dẫn tương đối với **root destination của Copy**, không phải `projectDir`.

```kotlin
tasks.register<Copy>("copyWebAssets") {
    from("src/web") {
        include("**/*.css")
        into("css")
    }
    into(layout.buildDirectory.dir("site"))
}
```

Ở đây `from("src/web")` chỉ nguồn của project, còn `into("css")` lồng bên trong tạo **nhánh `css` dưới `site`**. Đừng đánh đồng mọi tham số chuỗi của các API trong Gradle với một quy tắc duy nhất; phải đọc **ngữ nghĩa cụ thể của method**.

### Copy khác Sync

`Sync` là task đồng bộ: ngoài copy, nó có thể **xóa file thừa** trong thư mục đích. Nếu dùng `Sync`, chỉ hướng đến thư mục output dành riêng cho task:

```kotlin
tasks.register<Sync>("syncAssets") {
    from(layout.projectDirectory.dir("assets"))
    into(layout.buildDirectory.dir("synced-assets"))
}
```

Không dùng `Sync` vào thư mục source hay thư mục có file không do task quản lý, vì quá trình đồng bộ có thể làm mất các file khác.

## 10. Provider và thời điểm đọc file

`layout.projectDirectory.file(...)` mô tả vị trí source; `layout.buildDirectory.file(...)` trả Provider của vị trí output. Không nên đọc file output ngay ở giai đoạn Gradle **configuration**:

```kotlin
// Không nên đọc output sẽ được tạo trong build ở cấp script:
val generated = layout.buildDirectory.file("generated/data.txt")
val text = generated.get().asFile.readText()
```

Tại thời điểm này producer task chưa chắc đã chạy; file có thể thiếu hoặc chứa dữ liệu từ build trước. Ngoài ra việc đọc filesystem không cần thiết trong configuration có thể làm build khó tối ưu với configuration cache.

Thay vào đó, hãy cấu hình task consumer nhận Provider output và phụ thuộc task producer khi cần. Với custom task có type, ưu tiên:

- `RegularFileProperty` cùng `@InputFile` / `@OutputFile` cho một file.
- `DirectoryProperty` cùng `@InputDirectory` / `@OutputDirectory` cho thư mục.
- `ConfigurableFileCollection` cùng `@InputFiles` cho nhiều nguồn.
- `Provider.map`/`flatMap` để nối giá trị mà không cần ép `get()` quá sớm.

**Lưu ý:** chỉ dựng `layout.buildDirectory.file("x")` không làm Gradle biết ai tạo `x`. Provider xuất phát từ **output property của producer task** có thể mang theo dependency thông qua task wiring, tùy cách API được sử dụng. Nếu không có quan hệ đó, khai báo `dependsOn(producerTask)` tường minh như ví dụ mục 7.

## 11. CWD, Java Path và tính portable giữa các máy

Một Gradle task có thể được gọi từ terminal, IDE, CI hoặc daemon. Vì thế:

- Đừng dùng `System.getProperty("user.dir")` làm root path của source thuộc project.
- `java.nio.file.Path.of("data/input.txt")` cũng tạo path tương đối nếu bạn truyền chuỗi tương đối. Hãy lấy `File` qua Gradle rồi mới chuyển sang NIO `Path` khi cần.
- Tránh hard-code đường dẫn tuyệt đối của một máy, ví dụ đường dẫn dưới ổ người dùng trên Windows hay thư mục home Linux.
- Có thể dùng dấu `/` trong Gradle path literal như `"src/main/java"`; Java/Gradle xử lý separator cho platform.
- Đường dẫn có khoảng trắng/Unicode cần được API xử lý thay vì nối thành shell command thiếu quoting.
- Trên Linux, tên file thường phân biệt chữ hoa/thường; đừng dựa vào việc Windows tình cờ đọc được `Config.txt` khi tên thật là `config.txt`.

Ví dụ chuyển từ Gradle location sang Java NIO:

```kotlin
val gradleFile = layout.projectDirectory.file("data/input.txt")
val nioPath = gradleFile.asFile.toPath()
```

`nioPath` bây giờ đã có gốc project đúng. Mục đích là dùng API filesystem Java/NIO cho thao tác cần thiết, chứ không dùng API Java thay thế vai trò giải quyết relative path của Gradle.

### Cẩn trọng với ../ và symlink

`file("../shared/config.txt")` có thể tình cờ tới file root khi module nằm ngay dưới root. Nhưng nếu projectDir được chuyển vị trí, thêm cấp thư mục, dùng included builds hoặc symlink, `../` không còn thể hiện đúng ý nghĩa. `Project.file(...)` **không tự biến filesystem thành sandbox**: một path absolute, traversal hoặc symlink vẫn có thể trỏ ra ngoài thư mục dự án.

Nếu đường dẫn đến từ input không tin cậy, validate phạm vi và quyền truy cập trước khi đọc/ghi. Nếu file là output task, đặt nó trong buildDirectory hoặc nơi được quản lý rõ ràng, tránh ghi đè source.

## 12. Khác biệt khi chạy từ root, subproject hoặc CI

Nếu Gradle vẫn nhận diện **cùng một Project `:app`**, thì `file("data/input.txt")` trong script của `:app` tiếp tục dùng **`:app.projectDir`**, không tự đổi sang root vì bạn chạy `./gradlew :app:task` từ root.

Các yếu tố có thể khác giữa môi trường:

- JVM CWD, nên `File("...")` trực tiếp có thể thay đổi.
- Project được chọn bởi settings, `-p` và đường dẫn tham chiếu build.
- Vị trí checkout repository, khiến absolute path thay đổi.
- Gradle Wrapper version/JDK/toolchain, plugin và cách IDE/CI tải project.
- Custom `projectDir` trong settings: project logical path không nhất thiết giống cây thư mục thông thường.

Vì vậy khi test script, dùng Gradle Wrapper của repository và task path rõ ràng:

```bash
./gradlew projects
./gradlew :app:tasks --all
./gradlew -q :app:readSources
./gradlew -q :app:showStagedMessage
./gradlew :app:stageMessage --info
```

`projects` cho biết project paths; `tasks --all` giúp nhận diện task; `--info` bổ sung log để chẩn đoán. Đừng so sánh nguyên văn absolute path giữa hai máy làm tiêu chí đúng/sai của build.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `FileNotFoundException` khi CI chạy | Dùng `new File("relative")`/`Path.of("relative")` theo CWD. | Dùng `project.file(...)` hoặc `layout.projectDirectory.file(...)`. |
| Script ở `:app` đọc file root không thấy | `file("shared/config.txt")` trỏ vào `app/shared`. | Dùng API root/settings đúng nơi. |
| Đổi buildDirectory sang `out` nhưng task vẫn dùng `build` | Hard-code `file("build/...")`. | Dùng `layout.buildDirectory.file/dir(...)` hoặc output property. |
| Output được đọc trước khi producer chạy | Đọc trong configuration, thiếu dependency hoặc chỉ biết path. | Nối producer → consumer qua output Provider hoặc `dependsOn`. |
| `Copy` không tạo file | `from` trỏ sai module, file không tồn tại hoặc include pattern loại hết. | Kiểm tra projectDir, source thật và pattern. |
| Output Copy vào thư mục không mong muốn | Nhầm root `into` và child CopySpec `into`. | Xác định đúng root destination và nhánh relative bên dưới. |
| `Sync` xóa những file không mong muốn | Đồng bộ vào thư mục dùng chung. | Dùng thư mục output riêng và không Sync vào source. |
| Đường dẫn `../module/build` không ổn định | Phụ thuộc cấu trúc thư mục/đường dẫn output mặc định của module khác. | Dùng project dependency, artifact hoặc task output wiring. |
| Gradle version cũ không thấy `layout.settingsDirectory` | API chưa hỗ trợ trong Wrapper đang dùng. | Đối chiếu API của đúng Gradle version. |
| Build chạy ở Windows nhưng lỗi trên Linux | Sai chữ hoa/thường hoặc path separator/absolute path. | Kiểm tra tên file thật, dùng path tương đối project và Gradle API. |
| Đã lấy Provider nhưng vẫn có lỗi file thiếu | Provider mô tả vị trí, không tạo file hoặc producer dependency tự động. | Khai báo producer output và task dependency đúng. |

## 14. Quy trình tự kiểm tra một đường dẫn

1. **Xác định Project đang cấu hình**: root hay `:app`? Script nào chứa lời gọi?
2. **Xác định file thuộc đâu**: source của project, nguồn chung root/settings, file do task tạo, hay file external?
3. **Chọn resolver**: `Project.file` cho path đơn; `layout.projectDirectory` cho nguồn; `layout.buildDirectory` cho output; root/settings API khi cần.
4. **Xác định lúc file được tạo và lúc bị đọc**: file hiện có từ repository hay producer task chỉ tạo ở execution?
5. **Kiểm tra quan hệ task**: nếu có producer thì consumer đã nhận output Provider hoặc `dependsOn` đúng chưa?
6. **Quan sát kết quả trong đúng Project**: chạy task path rõ ràng, so sánh source/output và thay buildDirectory nếu cần thử.
7. **Kiểm tra tính portable**: Wrapper/CI, tên file, Unicode, separator, không lệ thuộc CWD/absolute path máy cá nhân.

**Công thức nhớ nhanh:** `file("x")` → `projectDir/x`; `layout.projectDirectory.file("x")` → file nguồn có gốc Project; `layout.buildDirectory.file("x")` → Provider đường dẫn output theo buildDirectory; `rootProject.file("x")` → gốc root project. Không gọi `File("x")` trực tiếp thay `file("x")` khi ý định là file thuộc Gradle Project.

## 15. Tài liệu chính thức

- [Gradle — Working With Files](https://docs.gradle.org/current/userguide/working_with_files.html): `Project.file`, relative path, `FileCollection`, `ProjectLayout`, `Copy` và `Sync`.
- [Gradle — Project API](https://docs.gradle.org/current/dsl/org.gradle.api.Project.html): quy tắc giải quyết path theo projectDir.
- [Gradle — ProjectLayout API](https://docs.gradle.org/current/javadoc/org/gradle/api/file/ProjectLayout.html): `projectDirectory`, `buildDirectory`, và các API layout phù hợp version.
- [Gradle — Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): Provider, Property, lazy evaluation và task input/output wiring.
- [Gradle — Writing Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html): task action, inputs/outputs và relation.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): project paths, settings và module.
