# Các hook vòng đời Gradle và giới hạn khi can thiệp cấu hình

## 1. Mục tiêu của bài học

Gradle cho phép đăng ký **hook/callback** để phản ứng khi build đi qua một mốc trong vòng đời: trước và sau khi đọc settings, trước và sau khi cấu hình một project, sau khi cấu hình toàn bộ project, hoặc khi task thực thi. Hook có ích cho plugin, init script, công cụ quan sát và một số kiểm tra cấu hình; dùng sai thời điểm dễ gây **sai thứ tự cấu hình, ép tạo task quá sớm, phụ thuộc project khác, làm mất hiệu quả configuration cache** hoặc khiến build chỉ chạy đúng trên máy người viết.

Sau bài này, bạn có thể:

- Phân biệt **initialization, configuration, execution** và đặt hook đúng giai đoạn.
- Hiểu ý nghĩa của `beforeSettings`, `settingsEvaluated`, `projectsLoaded`, `lifecycle.beforeProject`, `lifecycle.afterProject`, `afterEvaluate`, `projectsEvaluated`, các callback task graph và task actions.
- Nhận ra giới hạn khi hook định thay đổi plugin, task, dependency, repository hoặc trạng thái của project.
- Chọn phương án hiện đại, có khả năng cấu hình trễ như `pluginManager.withPlugin`, `tasks.register`, `tasks.named`, `configureEach`, `Provider` và convention plugin.
- Kiểm tra kết quả bằng một ví dụ độc lập và hai lượt chạy `--configuration-cache`.

**Nguyên tắc xuyên suốt:** dùng hook để quan sát hoặc xử lý mốc vòng đời **khi có lý do cụ thể**, còn cấu hình bình thường hãy đặt trong plugin/DSL và mô hình lazy configuration. “Chạy muộn hơn” không bảo đảm dữ liệu sẽ ổn định hơn.

## 2. Ba giai đoạn và những gì mỗi hook thực sự nhìn thấy

| Giai đoạn | Gradle thực hiện | Dữ liệu sẵn có | Giới hạn quan trọng |
| --- | --- | --- | --- |
| **Initialization** | Đọc init script, `settings.gradle(.kts)`, xác định root, subproject và included build | `Settings`, project descriptor, danh sách project khi đã load | Chưa nên giả định task hoặc extension do project plugin tạo đã tồn tại |
| **Configuration** | Đọc build script, áp dụng plugin, tạo/đăng ký task, tính quan hệ task | `Project`, extensions, task providers, dependency declarations | Thứ tự plugin/project ảnh hưởng tính sẵn có; đọc dependency/task quá sớm gây eager configuration |
| **Execution** | Chạy task đã được chọn và dependency theo task graph | Task inputs/outputs và thông tin runtime được khai báo | Không sửa cấu trúc project/task graph tại đây; tránh truy cập `Project` từ task action khi dùng configuration cache |

Luồng điển hình **khi configuration cache không được tái sử dụng**:

```text
Initialization
  init script
      |
      +-- beforeSettings
      v
  settings.gradle(.kts) hoàn thành
      |
      +-- settingsEvaluated
      v
  Khởi tạo các Project
      |
      +-- projectsLoaded
      v
Configuration
  [beforeProject -> build.gradle(.kts) -> afterProject] cho từng project
      |
      +-- projectsEvaluated
      v
  Xác định task graph / các task được chọn
      |
Execution
  Task action (@TaskAction / doFirst / doLast) khi task thực sự chạy
```

Đây là **sơ đồ logic**. Project có thể được cấu hình song song, theo nhu cầu hoặc bị bỏ qua khi dùng tính năng tối ưu thích hợp; thứ tự giữa các project không nên là hợp đồng nghiệp vụ. Các mốc configuration có thể **không chạy lại** khi configuration cache hit. Một callback đăng ký **sau khi mốc tương ứng đã đi qua** thường không thể quay ngược thời gian để nhận lại sự kiện đó.

## 3. Bảng định vị các hook/callback thường gặp

| Hook / API | Đăng ký ở đâu | Kích hoạt khi nào | Mục đích và lưu ý |
| --- | --- | --- | --- |
| `gradle.beforeSettings { ... }` | **Init script**, trước settings | Trước khi đánh giá `settings.gradle(.kts)` | Can thiệp sớm vào Settings. Đặt trong settings script thì đã quá muộn cho chính build đó. |
| `gradle.settingsEvaluated { ... }` | Init script hoặc settings script, trước khi settings kết thúc | Sau khi đánh giá settings | Đọc/xác minh kết quả cấu hình settings; không nên dùng để sửa ngược cấu hình plugin đã được phân giải |
| `gradle.projectsLoaded { ... }` | Init script hoặc settings script | Project instances đã được tạo, trước build scripts | Biết cấu trúc project nhưng chưa thể giả định plugin/tasks đã cấu hình |
| `gradle.lifecycle.beforeProject { ... }` | Đăng ký đủ sớm, thường từ init script/settings/plugin | Ngay trước khi một project được đánh giá | Quan sát hoặc thiết lập mặc định sớm; API mới cần phiên bản Gradle Wrapper có hỗ trợ |
| `gradle.lifecycle.afterProject { ... }` | Đăng ký đủ sớm | Sau khi một project hoàn tất đánh giá | Kiểm tra cấu hình project; tránh thao tác khiến project khác phải cấu hình đồng bộ |
| `project.beforeEvaluate { ... }` | Nơi khác có quyền đăng ký trước lúc project được đánh giá | Trước khi project cụ thể được đánh giá | Đăng ký ngay **trong build script của chính project** thường là quá muộn; ít khi cần |
| `project.afterEvaluate { ... }` | Build script hoặc plugin, trước khi project hoàn tất đánh giá | Sau khi đánh giá **một** project | API legacy, dễ tạo phụ thuộc thứ tự; **không khuyến nghị cho wiring task/property/plugin** |
| `gradle.projectsEvaluated { ... }` | Đăng ký trong giai đoạn sớm | Sau khi các project hoàn tất đánh giá | Từng dùng để tổng hợp/validate; callback legacy gây trở ngại với configuration cache |
| `gradle.taskGraph.whenReady { ... }` | Build logic cũ | Khi task graph đã được tính | Chỉ quan sát graph là một nhu cầu đặc biệt; đừng sửa task dependencies/mô hình quá muộn; không tương thích configuration cache |
| `doFirst { ... }`, `doLast { ... }`, `@TaskAction` | Cấu hình/khai báo task | Khi **task được thực thi** | Là task actions, **không phải hook cấu hình toàn build**; phải khai báo inputs/outputs, tránh chụp `Project` |
| `gradle.buildFinished { ... }` | Build logic cũ | Cuối build | Deprecated/không phù hợp configuration cache; cân nhắc Flow API hoặc build service/CI result |

**Lưu ý phiên bản:** các lifecycle API và trạng thái deprecated thay đổi theo Gradle. Tra phiên bản thật bằng `./gradlew --version` và đọc tài liệu **đúng phiên bản Wrapper**; không mặc định mọi hook của Gradle mới có mặt trong một build Gradle cũ. Đặc biệt, API `gradle.lifecycle` không nên copy vào repository cũ trước khi kiểm tra phiên bản.

## 4. Thực hành A — quan sát thứ tự vòng đời bằng init script

Thực hành này cố ý dùng hook để **ghi log minh họa**, không dùng hook để thay đổi logic build. Nó yêu cầu bản Gradle có `gradle.lifecycle.beforeProject/afterProject` và chạy **không dùng configuration cache** để nhìn đủ callback.

### 4.1. Cấu trúc demo

Tạo thư mục Gradle build có Wrapper hoặc sử dụng một bản Gradle cài tạm để khởi tạo Wrapper lần đầu:

```text
lifecycle-hooks-demo/
├── settings.gradle
├── build.gradle
├── app/
│   └── build.gradle
├── trace.init.gradle
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'lifecycle-hooks-demo'
include 'app'
```

`build.gradle` tại root:

```groovy
println "[configure] ${project.path}"
```

`app/build.gradle`:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.tasks.TaskAction

abstract class HelloTask extends DefaultTask {
    @TaskAction
    void sayHello() {
        println '[execute] Hello from :app:hello'
    }
}

println "[configure] ${project.path}"

tasks.register('hello', HelloTask) {
    group = 'learning'
    description = 'Minh họa execution sau configuration'
}
```

Task `HelloTask` in một dòng khi chạy; nó **không cần tham chiếu Project trong `@TaskAction`**. Task không khai báo output vì chỉ minh họa stdout và sẽ thực thi lại; đây không phải task tạo artifact để cache đầu ra.

`trace.init.gradle`:

```groovy
gradle.beforeSettings { settings ->
    println '[beforeSettings]'
}

gradle.settingsEvaluated { settings ->
    println "[settingsEvaluated] ${settings.rootProject.name}"
}

gradle.projectsLoaded { controller ->
    println "[projectsLoaded] ${controller.rootProject.path}"
}

gradle.lifecycle.beforeProject {
    println "[beforeProject] ${path}"
}

gradle.lifecycle.afterProject {
    println "[afterProject] ${path}"
}

gradle.projectsEvaluated {
    println '[projectsEvaluated]'
}
```

Vì init script được nạp **trước settings**, nó có thể đăng ký `beforeSettings` đúng lúc. `lifecycle.beforeProject` và `lifecycle.afterProject` dùng receiver của project đang được cấu hình, nên đọc `path` trực tiếp như ví dụ trong tài liệu Gradle. Các callback chỉ in log, không chỉnh project/task.

### 4.2. Chạy và đối chiếu

```bash
# Linux/macOS
./gradlew --no-configuration-cache --init-script trace.init.gradle -q :app:hello
```

```powershell
# Windows PowerShell
.\gradlew.bat --no-configuration-cache --init-script trace.init.gradle -q :app:hello
```

Với **build demo này ở chế độ cấu hình thông thường, không cấu hình song song**, phần stdout liên quan có dạng:

```text
[beforeSettings]
[settingsEvaluated] lifecycle-hooks-demo
[projectsLoaded] :
[beforeProject] :
[configure] :
[afterProject] :
[beforeProject] :app
[configure] :app
[afterProject] :app
[projectsEvaluated]
[execute] Hello from :app:hello
```

Đây là **dạng kết quả kỳ vọng** khi cả root và app được cấu hình tuần tự. Các thông báo Gradle ngoài ví dụ (ví dụ cảnh báo deprecation, download, daemon) tùy môi trường. Nếu bật cấu hình song song hoặc configuration-on-demand, thứ tự liên project/số project cần cấu hình có thể thay đổi. Bất biến đáng học là: `beforeSettings` trước settings; `projectsLoaded` trước đánh giá project; với từng project, `beforeProject` trước thân build script, `afterProject` sau; `projectsEvaluated` trước task action.

Nếu dùng Gradle cũ thiếu `gradle.lifecycle`, ví dụ không biên dịch/chạy được nguyên văn: hãy xem tài liệu API đúng phiên bản và nâng Wrapper theo quy trình dự án nếu cần. Đừng thay ngầm các callback bằng listener legacy rồi tuyên bố chúng có khả năng configuration cache tương đương.

### 4.3. Không lẫn hook với task action

`println` ở `build.gradle` chạy trong **configuration**; `@TaskAction` trong `HelloTask` chạy trong **execution** khi task được chọn và không bị skip. Gọi một task khác sẽ không mặc định chạy `:app:hello` dù callback cấu hình vẫn có thể xuất hiện. Khi configuration cache hit, dòng `[configure]` cũng có thể biến mất, nhưng task action vẫn phải chạy bình thường theo kế hoạch thực thi.

## 5. Hook được đăng ký ở đâu quyết định nó có chạy hay không

### 5.1. Init script: điểm vào sớm nhất

Init script chạy bằng `--init-script` hoặc từ vị trí init script của Gradle User Home, trước khi đánh giá settings. Nó phù hợp với quan sát/quy định áp dụng cho nhiều build (ví dụ logging có kiểm soát), nhưng tác động rất rộng, dễ làm một build đang chạy ở CI khác hành vi so với máy developer.

- Muốn nghe `beforeSettings`: đăng ký trong init script.
- Muốn nghe `settingsEvaluated` hay `projectsLoaded`: init script hoặc nơi trước sự kiện.
- Muốn nghe `lifecycle.beforeProject` toàn bộ project: đăng ký trước khi project tương ứng bắt đầu đánh giá.

### 5.2. Settings script: có giới hạn thời gian

`settings.gradle(.kts)` đã được nạp khi phần thân script chạy. Vì vậy viết `gradle.beforeSettings { ... }` **bên trong settings** không thể nhận mốc `beforeSettings` đã xảy ra cho chính build ấy. Những block đặc biệt như `pluginManagement { ... }` phải đặt theo cú pháp/quy định của Gradle để điều khiển plugin resolution **trước** khi plugin được nạp. Không chờ `settingsEvaluated` rồi mới cố sửa ngược repository đã dùng để phân giải settings plugins.

Nếu cần chuẩn hóa cấu hình settings lâu dài, hãy cân nhắc **Settings plugin**; nếu cần quy ước project, dùng **convention plugin** thay vì init callback tùy tiện.

### 5.3. Trong project build script: một số mốc đã đi qua

Đến lúc `build.gradle(.kts)` của project đang chạy, `beforeEvaluate` của **chính project** đã không còn là mốc tương lai. Đăng ký `project.beforeEvaluate` tại đây thường vô dụng. `afterEvaluate` vẫn có thể chạy, nhưng điều đó không khiến nó thành phương án mặc định tốt. Với subproject, khi root project hoặc plugin phụ huynh đăng ký callback cho project khác, kết quả còn phụ thuộc trình tự cấu hình.

**Không có cam kết rằng `afterEvaluate` đã thấy “mọi project hoàn toàn xong”**: nó chỉ có nghĩa **một project** vừa được đánh giá, các action đăng ký sau hoặc plugin khác có thể làm thay đổi thêm mô hình cấu hình.

## 6. Vì sao `afterEvaluate` thường là anti-pattern?

Ví dụ tình huống: một plugin muốn cấu hình task `test` do plugin `java` cung cấp. Cách legacy thường là:

```groovy
// Ví dụ minh họa anti-pattern; không khuyến nghị sao chép.
afterEvaluate {
    tasks.getByName('test').maxParallelForks = 2
}
```

Nhược điểm:

1. Nếu plugin `java` không được áp dụng, `test` không tồn tại.
2. `getByName` buộc lấy/realize task sớm; với build lớn điều này tăng configuration work.
3. Thứ tự các callback `afterEvaluate` phụ thuộc lúc đăng ký; plugin khác có thể đọc/mutate giá trị sau đó.
4. Một cấu hình task lazy do plugin khác đăng ký muộn có thể không được xử lý theo kỳ vọng.
5. Những hành vi dựa vào callback configuration có thể khác đi khi configuration cache tái sử dụng task graph.

Cách đề xuất cho một project **có thể áp dụng Java plugin**:

```groovy
import org.gradle.api.tasks.testing.Test

pluginManager.withPlugin('java') {
    tasks.withType(Test).configureEach {
        maxParallelForks = 2
    }
}
```

- `pluginManager.withPlugin('java')` chạy action khi plugin được áp dụng; nếu plugin **đã** áp dụng, action cũng được thực thi để cấu hình phù hợp.
- `withType(Test).configureEach` chỉ cấu hình các task kiểu `Test` **khi task đó được realize**, tránh duyệt/realize tất cả task ngay lúc đăng ký action.
- Không cần đợi `afterEvaluate` để đoán xem task hoặc plugin đã xuất hiện chưa.
- Đây là **đoạn cấu hình có thể chèn trong build script Groovy**; không có plugin `java` thì callback không chạy và không lỗi `test` do cố lấy task chưa tồn tại.

Nếu đã chắc plugin Java được áp dụng ngay trong cùng build script, có thể dùng `tasks.named('test', Test) { ... }` để cấu hình chính xác task tên `test`. Với nhiều task kiểm thử, `withType(Test).configureEach` tác động lên tất cả task cùng kiểu; chọn đúng API theo phạm vi muốn cấu hình.

## 7. Khi can thiệp cấu hình, hãy tuân thủ các ranh giới

### 7.1. Không “sửa task graph” vào phút cuối

Các callback `gradle.taskGraph.whenReady` và `TaskExecutionGraphListener` đến khi graph đã được tính. Đổi `dependsOn`, tạo task mới, thay output hoặc chỉnh cấu trúc dependency ở thời điểm đó có thể bị bỏ qua, thiếu tính xác định hoặc không tương thích configuration cache. Nên khai báo quan hệ task bằng **`dependsOn`, `mustRunAfter`, `shouldRunAfter`, `finalizedBy`** khi cấu hình mô hình.

- `dependsOn`: quan hệ phụ thuộc, task được kéo vào graph và thực hiện trước task phụ thuộc.
- `mustRunAfter`: ràng buộc thứ tự nếu cả hai task đã có mặt, **không tự kéo task vào graph**.
- `shouldRunAfter`: ưu tiên thứ tự mềm, Gradle có thể không tuân khi có lý do lập lịch hợp lệ.
- `finalizedBy`: khai báo task finalizer theo quy tắc Gradle, không thay cho “callback toàn build”.

Ví dụ task graph **được khai báo ngay trong configuration**:

```groovy
tasks.register('checkData') {
    doLast {
        println 'Data checked'
    }
}

tasks.register('publishData') {
    dependsOn(tasks.named('checkData'))
    doLast {
        println 'Data published'
    }
}
```

```bash
./gradlew -q publishData
```

Stdout của hai task trong ví dụ này theo thứ tự:

```text
Data checked
Data published
```

Đây là ví dụ minh họa quan hệ task. Với tác vụ production tạo file/tải artifact, còn cần khai báo inputs/outputs, validate và xử lý lỗi; không biến các task này thành pipeline phát hành thực tế chỉ bằng hai lệnh `println`.

### 7.2. Không đọc dependency và realize task quá sớm

Trong configuration, các thao tác như `configurations.runtimeClasspath.files`, `resolvedConfiguration`, `tasks.getByName`, `tasks.all` hoặc gọi `TaskProvider.get()` có thể kéo công việc lẽ ra nên để sau lên sớm, làm chậm build hay phá cacheability.

Ưu tiên:

- `tasks.register('name', Type) { ... }` thay `tasks.create`.
- `tasks.named('name') { ... }` để cấu hình task đã được biết tên.
- `tasks.withType(Type).configureEach { ... }` cho nhiều task kiểu giống nhau.
- `configurations.configureEach { ... }` hoặc `configurations.named(...) { ... }` để cấu hình dependency configurations lazy.
- `Provider.map/flatMap` và `Property.set(provider)` để nối giá trị mà chưa bắt chúng tính ngay.

**Đúng thời điểm** để resolve artifact là khi Gradle cần sử dụng dependency hợp lệ cho task; không giải quyết vấn đề thứ tự cấu hình bằng một lệnh `.files` trong `afterEvaluate`. Với configuration cache, Gradle có thể tính một số trạng thái dependency trong giai đoạn lưu graph, nhưng đó là việc của engine, không phải lời mời gọi build script resolve sớm.

### 7.3. Không truy cập project khác như một biến toàn cục

Trong multi-project build, mẫu `subprojects { ... }`, `allprojects { ... }` hoặc truy cập `project(':other')` để chỉnh sửa một project khác tạo quan hệ cấu hình chéo. Điều đó cản trở **Isolated Projects**, cấu hình song song và khả năng tái sử dụng cache. Với logic chia sẻ, ưu tiên convention plugin được **mỗi project tự áp dụng**; trao đổi dữ liệu qua dependency/task input/output hoặc model/provider hỗ trợ, thay vì tự sửa Project khác bên trong callback.

Nếu bắt buộc có logic chạy trước/sau mỗi project, xem API `gradle.lifecycle.beforeProject/afterProject` ở phiên bản Gradle đang dùng và hạn chế action chỉ chạm tới project được truyền vào. Kể cả API lifecycle mới cũng không khiến mọi thao tác cross-project trở nên an toàn.

### 7.4. Không để configuration quyết định dữ liệu runtime theo cách khó theo dõi

Gọi `System.getenv('TOKEN')`, đọc file tùy ý hoặc chạy subprocess ngay trong configuration có thể khiến build khó tái lập, khó cache hoặc vô tình lộ dữ liệu. Ưu tiên `providers.gradleProperty(...)`, `providers.environmentVariable(...)` và `providers.fileContents(...)` khi cần đầu vào; khai báo chúng thành inputs cho task phù hợp. Không in secrets vào log từ hook.

Đầu vào runtime thuộc task action. Chỉ đăng ký các hooks để đọc thông tin thiết yếu của cấu hình, không làm tác vụ có side effect như ghi/đổi file, tạo kết nối mạng hoặc cập nhật trạng thái bên ngoài ở mỗi lần configuration.

## 8. Thực hành B — chuyển logic sang Provider và typed task

Nếu task cần một giá trị cấu hình có thể được người dùng thay đổi, hãy dùng `Property<T>` / `Provider<T>` để truyền giá trị **từ configuration sang execution**; task tự sở hữu input của nó. Ví dụ là một `build.gradle` Groovy DSL **độc lập** (dùng trong project demo riêng hoặc thay đổi có kiểm soát):

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class PrintNotice extends DefaultTask {
    @Input
    abstract Property<String> getNotice()

    @TaskAction
    void printNotice() {
        println notice.get()
    }
}

tasks.register('printNotice', PrintNotice) {
    notice.set(
        providers.gradleProperty('notice').orElse('Xin chào Gradle')
    )
}
```

```bash
./gradlew -q printNotice
./gradlew -q printNotice -Pnotice="Chao tu CI"
```

Kết quả stdout lần 1:

```text
Xin chào Gradle
```

Kết quả stdout lần 2:

```text
Chao tu CI
```

Đối với task này, `notice` là **input có annotation `@Input`** và action chỉ đọc thuộc tính của chính task. `providers.gradleProperty` để Gradle quản lý nguồn giá trị; khi property thay đổi, đầu vào cấu hình được theo dõi theo cơ chế của Gradle. Không cần `afterEvaluate` để “đợi người dùng cấu hình xong”.

Đừng nhầm `Property<T>` của Gradle Provider API với `ext.someKey` hay `gradle.properties`: chúng có thể liên hệ về giá trị nhưng cách khai báo, trì hoãn tính toán và kiểm tra đầu vào khác nhau. Với task tạo file, còn phải khai báo `@OutputFile`/`@OutputDirectory`, đầu vào file tương ứng và cách xử lý deterministic.

## 9. Configuration Cache thay đổi hợp đồng của lifecycle hooks

**Configuration cache** lưu trạng thái cấu hình/task graph; lần chạy sau với cùng requested tasks và đầu vào cấu hình không đổi có thể **bỏ qua configuration**. Nó độc lập với **build cache** dành cho outputs của task.

| Lúc chạy | Initialization / configuration | Task execution |
| --- | --- | --- |
| Không bật configuration cache | Cấu hình build theo cơ chế bình thường mỗi lượt | Các task được chọn thực thi hoặc bị skip theo quy tắc task |
| Bật, **cache miss** | Tính lại cấu hình, kiểm tra khả năng lưu graph; các callback cấu hình có thể chạy | Gradle dùng graph đã tính/lưu rồi chạy tasks |
| Bật, **cache hit** | Nạp lại graph đã lưu; **không chạy lại** các callback configuration tương ứng | Task actions của task cần chạy vẫn được gọi |

Hệ quả: **không đặt hành động bắt buộc xảy ra mỗi lần build vào `afterEvaluate`, `projectsEvaluated`, `taskGraph.whenReady` hay các build listeners**. Với configuration cache, nhóm listener legacy như `BuildListener`, `gradle.buildFinished`, `gradle.projectsEvaluated` hoặc `TaskExecutionListener` có thể bị báo lỗi không hỗ trợ hoặc không được gọi khi cache được tái sử dụng. Một hook mới hơn chỉ được dùng khi **tài liệu phiên bản Gradle xác nhận** phù hợp; không tự suy từ tên method.

Để bắt lỗi thật, trên **build có logic muốn kiểm tra và không nạp `trace.init.gradle` của thực hành A**, chạy hai lần:

```bash
./gradlew --configuration-cache :app:hello
./gradlew --configuration-cache :app:hello
```

Ở lần đầu có thể thấy Gradle tạo cache entry. Lần hai, nếu input không đổi và build tương thích, Gradle thông báo tái sử dụng entry; dòng `[configure]` của root/app từ ví dụ có thể không còn xuất hiện vì build scripts không được đánh giá lại, nhưng `[execute] Hello from :app:hello` vẫn được in khi task thực thi. Nếu Gradle không tái sử dụng, đọc lý do invalidation.

Có thể chạy riêng:

```bash
./gradlew help --configuration-cache --warning-mode all
```

Khi có lỗi configuration cache, đọc report do Gradle dẫn tới trong output (thường dưới `build/reports/configuration-cache/`), xác định plugin/script/callback gốc, sửa rồi chạy lại. Tránh bật chế độ “ignore/warn problems” vĩnh viễn để vượt qua lỗi; nó có thể làm cache lưu trạng thái không đúng. `--dry-run` cũng không thay thế phép thử compatibility với execution thật.

Nếu cần log sau mỗi lần task hoàn tất, Gradle khuyên cân nhắc **Build Service** kết hợp `OperationCompletionListener`. Nếu cần phản ứng ở cuối toàn build, có **FlowAction/FlowScope** trong Gradle hiện đại (một số API còn ở trạng thái incubating), hoặc để hệ thống CI đọc exit code và báo cáo kiểm thử. Đây là phần triển khai plugin chuyên sâu, không thay được bằng cách đổi tên `buildFinished`.

## 10. So sánh lựa chọn hook với giải pháp cấu hình chuẩn

| Bài toán | Cách dễ gây lỗi | Cách phù hợp hơn |
| --- | --- | --- |
| Chờ Java plugin rồi cấu hình Test tasks | `afterEvaluate { tasks.getByName('test') ... }` | `pluginManager.withPlugin('java')` + `withType(Test).configureEach` |
| Tạo task chỉ khi cần | `tasks.create`, duyệt `tasks.all` | `tasks.register` và `TaskProvider` |
| Lấy thuộc tính sau khi script chạy | Đọc `ext`/biến mutable trong `afterEvaluate` | `Property<T>` / `Provider<T>`, wire giá trị từ configuration |
| Thêm thứ tự build/publish | Sửa `dependsOn` trong `taskGraph.whenReady` | Khai báo `dependsOn`/`finalizedBy` lúc configuration |
| Chia sẻ cấu hình giữa nhiều project | Root tùy ý mutate `subprojects` | Convention plugin được từng project áp dụng |
| Đọc biến môi trường | `System.getenv` từ nhiều callback | `providers.environmentVariable`, task input có khai báo |
| Muốn một action ở cuối build | `buildFinished` listener legacy | Flow action/build service hoặc CI orchestration |
| Muốn khảo sát mốc setup/config | Log hook trong production build | Init script tạm dùng cho chẩn đoán, chạy không cache |
| Muốn phát hiện thiếu cấu hình | Nhiều `afterEvaluate` sửa mô hình | Validate sớm, khai báo yêu cầu rõ ràng, dùng provider; chỉ dùng validation hook tối thiểu khi bắt buộc |

## 11. Lỗi phổ biến và cách điều tra

### Lỗi 1 — “Đã đăng ký `beforeEvaluate` nhưng callback không chạy”

Thường do đăng ký ngay trong build script của chính project, khi sự kiện “trước evaluate” đã qua. Đặt callback **ở chỗ được chạy sớm hơn**, nhưng cân nhắc xem có thực sự cần hook hay có thể đặt cấu hình trực tiếp vào plugin/build script.

### Lỗi 2 — `afterEvaluate` báo task chưa tồn tại

Plugin chưa áp dụng, task chưa được register, hoặc callback chạy ở thứ tự không mong muốn. Không giải quyết bằng thêm nhiều tầng `afterEvaluate`. Chuyển sang `pluginManager.withPlugin`, `tasks.named` hoặc `configureEach`; xác nhận task path bằng `./gradlew tasks --all`.

### Lỗi 3 — Log hook biến mất ở lần chạy thứ hai

Configuration cache hit đã tái sử dụng graph: không có configuration callback cần chạy lại. Đây có thể là hành vi **đúng**. Nếu logic phải chạy mọi lượt, đặt vào mô hình task, Build Service/Flow API phù hợp, hoặc CI thay vì hook configuration.

### Lỗi 4 — Build hỏng khi bật `--configuration-cache`

Một trong các nguyên nhân là legacy listener không được hỗ trợ, task action chụp `Project`/`Gradle`, hoặc đọc trạng thái runtime/ngoài Gradle trái contract. Xem report Gradle, đối chiếu API bị chỉ ra; di chuyển logic sang task inputs/providers hoặc listener được hỗ trợ.

### Lỗi 5 — Trình tự cấu hình khác giữa local và CI

Build có thể cấu hình project song song hoặc dùng Isolated Projects; callback mutates trạng thái project khác gây race/vi phạm isolation. Thay bằng per-project convention plugin và task dependencies có khai báo rõ.

### Lỗi 6 — Hook làm build rất chậm

Trong callback có `tasks.all`, `getByName`, resolve configurations hoặc truy cập tất cả project khiến hàng loạt object/graph bị realize. Đo bằng build profiling/scan theo chính sách dự án, giảm eager API, dùng `configureEach`/`Provider` và kiểm tra cache hit rate.

### Lỗi 7 — Cấu hình “thành công” nhưng task có kết quả sai

Task đọc input không khai báo, dựa vào giá trị do hook vô tình cập nhật, hoặc action có side effect ngoài kiểm soát. Khai báo `@Input`, `@InputFiles`, `@OutputFile`, định nghĩa dependency giữa task, test cache hit và chạy từ thư mục sạch của demo để xác nhận tính tái lập.

## 12. Checklist trước khi thêm một lifecycle hook vào codebase

1. **Tôi đang muốn quan sát hay thay đổi?** Nếu thay đổi task/plugin/property thông thường, tìm API cấu hình trực tiếp trước.
2. **Hook xảy ra lúc nào?** Đã qua mốc đó khi đoạn code đăng ký chạy chưa?
3. **Callback có quyền nhìn đúng object chưa?** `Settings`, `Project`, `TaskProvider` và `Task` không hoán đổi cho nhau.
4. **Có project khác bị truy cập/mutate không?** Có thể thay bằng convention plugin hoặc task dependency không?
5. **Có eager task realization, dependency resolution, network/file I/O trong configuration không?**
6. **Nếu configuration cache hit, hành vi còn đúng không?** Có tác vụ cần chạy mỗi invocation bị đặt trong callback configuration không?
7. **Nếu dùng plugin hoặc Gradle version khác, API có còn tồn tại và hoạt động không?** Kiểm tra theo Gradle Wrapper.
8. **Nếu chạy song song/CI, logic có deterministic và không làm lộ secret không?**
9. **Có thể kiểm chứng bằng một test nhỏ và lệnh `--configuration-cache` hai lượt không?** Đừng chỉ nhìn “BUILD SUCCESSFUL” của lượt đầu.
10. **Hook có thật sự mang lại giá trị ngoài độ phức tạp mà nó tạo ra không?** Giữ số điểm can thiệp nhỏ và mô tả rõ lý do.

## 13. Ghi nhớ

- Lifecycle hook **khác** task dependency và task action: hook phản ứng với mốc của build; task model quyết định công việc phải làm, quan hệ và dữ liệu.
- **`beforeSettings` cần đăng ký trước settings**; `beforeProject` trước đánh giá project; `afterProject` sau đánh giá project; `projectsEvaluated` sau đánh giá các project nhưng trước execution.
- **`afterEvaluate` là lựa chọn ngoại lệ**, không phải công cụ “chữa” mọi lỗi thứ tự. Với plugin và task, dùng `withPlugin`, `register`, `named`, `configureEach` và `Provider`.
- **Configuration cache có thể bỏ qua toàn bộ configuration** trên cache hit; listener legacy có thể không được hỗ trợ.
- Với multi-project build và Isolated Projects, hạn chế callback can thiệp project khác; cấu hình chia sẻ thuộc convention plugin.
- Với hành vi tại execution/hoàn tất build, khai báo task và inputs/outputs hoặc dùng cơ chế quan sát hỗ trợ như Build Service, Flow API và CI.

## Tài liệu chính thức

- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): ba giai đoạn, timeline, lifecycle API, listeners, build services, flow actions.
- [Gradle — General Best Practices](https://docs.gradle.org/current/userguide/best_practices_general.html): lý do tránh `afterEvaluate`, ưu tiên lazy properties và `pluginManager.withPlugin`.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named`, `configureEach`.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): cache miss/hit và thay đổi lifecycle.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): API/callback không tương thích và mô hình task input.
- [Gradle — Adopting the Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_adoption.html): thay listener không hỗ trợ, mở report để sửa.
- [Gradle — Isolated Projects](https://docs.gradle.org/current/userguide/isolated_projects.html): ranh giới truy cập giữa project.
