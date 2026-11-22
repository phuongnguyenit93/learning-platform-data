# Ba giai đoạn khởi tạo, cấu hình và thực thi trong Gradle

## 1. Vì sao cần hiểu vòng đời build?

Khi chạy lệnh như `gradle build` hoặc `./gradlew :app:test`, Gradle không đơn thuần thực thi lần lượt các dòng trong tệp `build.gradle`. Nó phải **xác định những project tham gia**, **cấu hình mô hình build và chọn đồ thị task**, rồi **thực hiện những task cần thiết**.

Ba giai đoạn (*build phases*) chính:

1. **Initialization – khởi tạo:** xác định build, root project, subproject và các included build.
2. **Configuration – cấu hình:** áp dụng plugin, đánh giá build script cần thiết, cấu hình các project/task và hình thành đồ thị công việc.
3. **Execution – thực thi:** chạy task action trong đồ thị đã chọn theo quan hệ phụ thuộc, với các cơ chế bỏ qua/khôi phục kết quả khi hợp lệ.

Mô hình tư duy:

~~~text
Lệnh: gradle :app:build
         |
         v
+-----------------------------------------+
| 1. INITIALIZATION                        |
| Tìm/đánh giá settings.gradle(.kts)       |
| Xác định root, subproject, included build|
+-----------------------------------------+
         |
         v
+-----------------------------------------+
| 2. CONFIGURATION                         |
| Đánh giá build.gradle(.kts), áp dụng     |
| plugin, đăng ký/cấu hình task, dựng DAG  |
+-----------------------------------------+
         |
         v
+-----------------------------------------+
| 3. EXECUTION                             |
| Chọn task + phụ thuộc, kiểm tra trạng    |
| thái, thực thi action cần chạy           |
+-----------------------------------------+
         |
         v
  Kết quả build, báo cáo, artifact
~~~

**Đặc biệt quan trọng:** Trong build script, lệnh cấu hình task và mã nằm trong `doLast { ... }` không thuộc cùng một thời điểm. Code cấu hình tạo ra *kế hoạch*; task action là phần thực hiện công việc.

## 2. So sánh ba giai đoạn

| Giai đoạn | Câu hỏi cần trả lời | Thành phần thường liên quan | Kết quả chính |
| --- | --- | --- | --- |
| Initialization | “Build này có các project nào?” | Init scripts (nếu có), `settings.gradle` / `settings.gradle.kts`, `include(...)`, `includeBuild(...)` | Danh tính build, root project và các Project/Settings tương ứng |
| Configuration | “Các project và task được cấu hình thế nào, phải chạy task nào?” | `build.gradle` / `build.gradle.kts`, `plugins`, `dependencies`, `tasks.register(...)`, task relationships | Mô hình project/task và task execution graph |
| Execution | “Task nào thật sự phải làm việc và theo thứ tự ràng buộc nào?” | Task action (`doFirst`, `doLast`, `@TaskAction`), inputs/outputs, up-to-date checks, build cache | File biên dịch, test results, JAR, báo cáo và trạng thái build |

**Phân biệt tên gọi:** “Build lifecycle” ở đây là vòng đời **của một lần chạy Gradle**. Nó không phải chuỗi phase cố định `compile → test → package` như Maven. Trong Gradle, `compileJava`, `test`, `jar`, `build` là những task do plugin cung cấp; thứ tự thực tế hình thành từ task graph.

Đường lối ba giai đoạn là mô hình khái niệm. Các cơ chế tối ưu như **Configuration Cache** có thể tái sử dụng kết quả cấu hình, làm thay đổi phần mã được đánh giá lại trong những lần chạy sau. Vì thế không nên khẳng định rằng mọi file cấu hình sẽ được thực thi lại trong **mọi** lần gọi Gradle.

## 3. Giai đoạn 1 — Initialization (khởi tạo)

### 3.1. Gradle xác định phạm vi build

Gradle xác định build đang được yêu cầu và xử lý tệp settings ở gốc, thường là:

- `settings.gradle`: Groovy DSL.
- `settings.gradle.kts`: Kotlin DSL.

Ví dụ một cấu trúc:

~~~text
online-store/
├── settings.gradle
├── build.gradle
├── app/
│   └── build.gradle
└── library/
    └── build.gradle
~~~

Nội dung `settings.gradle`:

~~~groovy
rootProject.name = 'online-store'
include(':app', ':library')
~~~

Trong initialization, Gradle hiểu rằng root project có project path `:` và có hai subproject `:app`, `:library`. Đây là danh sách *thành viên* của build, chưa phải lệnh biên dịch các project đó.

Tệp `settings.gradle` có thể cấu hình thêm `pluginManagement { ... }`, `dependencyResolutionManagement { ... }` hoặc `includeBuild(...)` để tổ chức build. Chúng được dùng trong việc thiết lập cấu trúc/cấu hình xây dựng; không nên nhầm `includeBuild` (ghép một build độc lập) với `include` (khai báo subproject của cùng build).

### 3.2. Init script khác settings script

Gradle cũng hỗ trợ **init scripts** — ví dụ script cấu hình môi trường doanh nghiệp dùng chung cho nhiều build. Khi có init script, nó có thể được xử lý trước settings. Tuy vậy, **một dự án Gradle bình thường không buộc bạn tự tạo init script**; điểm bắt đầu dễ quan sát nhất vẫn là `settings.gradle(.kts)`.

Ở mức đơn giản:

~~~text
Init script (nếu có)
          |
          v
Đánh giá settings.gradle(.kts)
          |
          v
Xác định root / subproject / included build
          |
          v
Sẵn sàng cấu hình các project
~~~

### 3.3. Điều initialization không thực hiện

Initialization **không đồng nghĩa** với việc Gradle đã biên dịch `.java`, chạy JUnit hay tạo `.jar`. Nó trả lời câu hỏi về cấu trúc build. Nếu bạn chỉ tạo một thư mục và `build.gradle` nhưng chưa khai báo subproject trong settings của root, thư mục đó không tự động trở thành một subproject của build.

Đây cũng là lý do lỗi `Project with path ':library' could not be found` thường cần kiểm tra `settings.gradle` và project path trước, chứ không bắt đầu bằng sửa `javac` hoặc classpath.

## 4. Giai đoạn 2 — Configuration (cấu hình)

### 4.1. Xây dựng mô hình project và task

Sau khi xác định các project, Gradle đánh giá cấu hình build tương ứng. Tệp `build.gradle` hoặc `build.gradle.kts` là nơi bạn thường:

- Áp dụng plugin, ví dụ `id 'java'`, `id 'java-library'`, `id 'application'`.
- Khai báo `repositories`, `dependencies`, Java toolchain, test framework và tùy chọn artifact.
- Đăng ký hoặc cấu hình task, xác định task nào phụ thuộc task nào.
- Cung cấp cấu hình cho việc tính task graph, lựa chọn các task được yêu cầu và các task phụ thuộc.

Ví dụ `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn minh họa cấu hình**, không phải một chương trình Java riêng biệt. Plugin `java` cung cấp các task như `compileJava`, `processResources`, `classes`, `jar`, `test`, `build`; khối `java` và `tasks.named('test')` cấu hình hành vi. `useJUnitPlatform()` chỉ định cách chạy bài test nếu dự án có engine JUnit tương ứng trong dependencies; chỉ gọi nó không tự tải JUnit.

**Một bẫy hay gặp:** Những dòng cấp cao nhất (*top-level*) trong `build.gradle` là code chạy khi đánh giá script cấu hình. Ví dụ `println("Configuring project")` có thể chạy dù bạn chỉ gọi `gradle help`, vì nó không nằm bên trong task action.

### 4.2. Đăng ký task không có nghĩa chạy task

Ví dụ:

~~~groovy
tasks.register('hello') {
    doLast {
        println 'Hello from task'
    }
}
~~~

`tasks.register('hello')` đăng ký một task với Gradle. Còn `println` trong `doLast` là **task action**, chỉ có cơ hội được gọi trong execution khi task nằm trong graph và không bị bỏ qua.

Nếu không yêu cầu task `hello` và cũng không có task được yêu cầu phụ thuộc vào nó, dòng `println 'Hello from task'` không chạy.

### 4.3. “Lười” (*lazy*) trong task registration

`tasks.register('hello')` trả về một `TaskProvider`, giúp Gradle trì hoãn việc **tạo và cấu hình đầy đủ đối tượng task** cho đến khi cần. Điều này khác với API eager như `tasks.create('hello')`: khi tạo eager, Gradle phải hiện thực hóa task ngay.

Ví dụ:

~~~groovy
tasks.register('lazyTask') {
    println '[CONFIG TASK] lazyTask được hiện thực hóa'
    doLast {
        println '[EXEC] lazyTask chạy'
    }
}
~~~

Hai câu `println` ở đây thuộc hai thời điểm khác nhau:

- `println` trực tiếp trong closure của `register` là **logic cấu hình task**. Closure này có thể được đánh giá muộn khi task được *realize* để dựng graph, hoặc không được đánh giá nếu task không cần.
- `println` trong `doLast` là **logic thực thi**, chỉ chạy khi task thực sự được thực thi.

Vì vậy, đừng đồng nhất “closure nằm trong `tasks.register { ... }`” với “toàn bộ closure chạy ở execution”. Chỉ task action (hoặc phần việc thực thi tương đương của task type) mới đại diện cho công việc runtime.

Các API nên ưu tiên:

~~~groovy
def prepare = tasks.register('prepare') {
    doLast {
        println 'Prepare'
    }
}

tasks.register('deliver') {
    dependsOn(prepare)
    doLast {
        println 'Deliver'
    }
}
~~~

`dependsOn(prepare)` nhận `TaskProvider` trực tiếp. Không cần gọi `prepare.get()` chỉ để tạo dependency; `get()` có thể khiến task bị hiện thực hóa sớm.

Đối với task do plugin đăng ký, dùng `tasks.named('test') { ... }` để cấu hình theo tên, hoặc `tasks.withType(JavaCompile).configureEach { ... }` cho nhiều task cùng kiểu. Tránh duyệt toàn bộ task hoặc dùng `tasks.all { ... }` một cách không cần thiết, vì có thể phá lợi ích của cấu hình trì hoãn.

### 4.4. Task graph được quyết định từ quan hệ

Gradle xem xét task được yêu cầu, các quan hệ phụ thuộc mạnh như `dependsOn`, và các ràng buộc thứ tự để tạo **directed acyclic graph (DAG)** — đồ thị có hướng không chu trình.

Ví dụ:

~~~text
:compileJava ----+
                 |
:processResources+--> :classes --> :jar --> :assemble
~~~

Đây là sơ đồ khái niệm của các quan hệ task do Java plugin cung cấp; đường nối cụ thể còn phụ thuộc plugin và cấu hình. Task `:jar` không phải “dòng code tiếp theo” ngay sau `:classes` trong build script; nó có quan hệ phụ thuộc thể hiện qua graph.

Gradle phải phát hiện chu trình không thể lập lịch, ví dụ A phụ thuộc B và B phụ thuộc A. Hệ quả là thêm `dependsOn` bừa bãi có thể làm build thất bại ngay từ việc dựng graph.

## 5. Giai đoạn 3 — Execution (thực thi)

Execution là lúc Gradle thực thi các **task action** trong graph đã tính. Tùy plugin, đó có thể là công việc biên dịch Java, kiểm thử, copy resource, đóng JAR, sinh báo cáo hoặc tác vụ tùy chỉnh.

Trong Groovy DSL, task tự viết thường có `doFirst { ... }` và `doLast { ... }`. Với task type tự tạo bằng Java/Kotlin, công việc có thể nằm trong phương thức chú thích `@TaskAction`.

Ví dụ:

~~~groovy
tasks.register('sayHello') {
    doLast {
        println 'Hello, execution phase!'
    }
}
~~~

Nếu chạy `gradle sayHello`, action có thể được thực thi. Nếu chạy `gradle help`, action của `sayHello` không chạy. Nếu chạy `gradle sayHello --dry-run`, Gradle lập kế hoạch task nhưng bỏ qua việc thực thi task action.

### 5.1. Task được chọn chưa chắc cần làm lại mọi việc

Một task trong graph không mặc nhiên được thực thi lại toàn bộ action:

- Nếu có **inputs/outputs** được khai báo đúng và không thay đổi, Gradle có thể báo `UP-TO-DATE`.
- Với **build cache** được bật, task cacheable đủ điều kiện có thể lấy kết quả từ cache (`FROM-CACHE`), tùy trạng thái và chính sách cache.
- Task có thể bị bỏ qua bởi điều kiện `onlyIf` hoặc do tác vụ không có nguồn để xử lý (`NO-SOURCE`), tùy loại task.
- Task đơn giản chỉ có `doLast { println(...) }` nhưng không khai báo output thường sẽ chạy lại khi được yêu cầu; đừng dùng nó để chứng minh cơ chế up-to-date.

Các trạng thái này là **kết quả quyết định ở execution**, không có nghĩa công cụ đã bỏ qua toàn bộ giai đoạn initialization/configuration trong mọi lần build.

### 5.2. Quan hệ phụ thuộc không giống quan hệ thứ tự

| Cấu hình | Ý nghĩa |
| --- | --- |
| `taskA.dependsOn(taskB)` | Khi chạy A, Gradle phải bảo đảm B được đưa vào graph và thực hiện theo nhu cầu trước A |
| `taskA.mustRunAfter(taskB)` | Nếu cả A lẫn B cùng được chọn, A phải sau B; không tự kéo B vào graph |
| `taskA.shouldRunAfter(taskB)` | Gợi ý thứ tự mềm khi cả hai có mặt; có thể không được bảo toàn trong một số trường hợp |
| `taskA.finalizedBy(taskB)` | Khi A được thực thi, B là task dọn dẹp/kết thúc liên quan theo cơ chế finalizer |

Không dùng `mustRunAfter` để thay `dependsOn` khi A **cần artifact** do B tạo. Ngược lại, không dùng `dependsOn` chỉ để ép thứ tự giữa hai việc vốn độc lập nếu muốn cho phép chạy riêng từng task.

Gradle có thể chạy song song những task đủ điều kiện **không phụ thuộc nhau**, khi parallel execution và môi trường cho phép. Vì thế đầu ra log từ các nhánh độc lập có thể xen kẽ; thứ tự ổn định chỉ nên suy ra từ các quan hệ ràng buộc thực sự.

## 6. Thí nghiệm chạy được: quan sát ba giai đoạn bằng stdout

Thí nghiệm này dùng **Groovy DSL** và không cần plugin bên ngoài, mã Java, repository mạng hoặc JUnit. Bạn cần bản Gradle tương thích được cài đặt, hoặc Gradle Wrapper được chuẩn bị trước cho project. Dùng thư mục mới:

~~~text
gradle-phase-lab/
├── settings.gradle
└── build.gradle
~~~

### 6.1. Tệp settings.gradle — thông điệp initialization

~~~groovy
rootProject.name = 'gradle-phase-lab'
println '[INIT] settings.gradle'
~~~

Thông điệp `[INIT]` được in khi Gradle đánh giá settings script trong initialization, ở lần chạy không tái sử dụng cấu hình đã cache.

### 6.2. Tệp build.gradle — tách cấu hình và thực thi

~~~groovy
println '[CONFIG] build.gradle'

def prepareTask = tasks.register('prepare') {
    doLast {
        println '[EXEC] prepare'
    }
}

tasks.register('finish') {
    dependsOn(prepareTask)

    doLast {
        println '[EXEC] finish'
    }
}
~~~

Hãy quan sát:

- `println '[CONFIG] build.gradle'` nằm ngay trong script, nên chạy khi đánh giá cấu hình project.
- `tasks.register` khai báo hai task; task `finish` có dependency tới `prepare`.
- `doLast` không được thực thi chỉ vì Gradle đọc file. Chúng chạy trong execution khi task thực sự được chọn.

### 6.3. Chạy lệnh và dự đoán stdout

Từ thư mục `gradle-phase-lab`:

~~~bash
gradle --no-configuration-cache --console=plain --quiet finish
~~~

Stdout từ các câu `println` của ví dụ này là:

~~~text
[INIT] settings.gradle
[CONFIG] build.gradle
[EXEC] prepare
[EXEC] finish
~~~

Giải thích đúng thứ tự:

1. Gradle xử lý `settings.gradle`, in dòng `INIT`.
2. Gradle đánh giá `build.gradle`, in dòng `CONFIG`.
3. Graph của `finish` cần task `prepare`, nên action của `prepare` chạy trước và in dòng `EXEC` đầu tiên.
4. Action của `finish` chạy sau và in dòng `EXEC` cuối cùng.

Trong ví dụ này, `--quiet` giúp ẩn phần lớn log Gradle để nhìn rõ các dòng `println`. `--no-configuration-cache` giúp loại bỏ sự khác biệt do Configuration Cache đã lưu. Nếu có các init script/logic môi trường chủ động in thêm thông tin, terminal vẫn có thể có những dòng khác; bốn dòng trên là **stdout do chính ví dụ tạo ra**.

### 6.4. Đổi task được yêu cầu

Chạy:

~~~bash
gradle --no-configuration-cache --console=plain --quiet prepare
~~~

Các câu `println` của ví dụ tạo ra:

~~~text
[INIT] settings.gradle
[CONFIG] build.gradle
[EXEC] prepare
~~~

Không có `[EXEC] finish` vì `prepare` không phụ thuộc `finish`. Chiều của `dependsOn` rất quan trọng: chạy `finish` yêu cầu `prepare`, nhưng chạy `prepare` không yêu cầu `finish`.

### 6.5. Xem kế hoạch mà không thực hiện action

~~~bash
gradle --no-configuration-cache --console=plain --dry-run finish
~~~

Gradle vẫn xử lý phần cần thiết để xây dựng kế hoạch. Trong output, các task tương ứng sẽ được hiển thị là bị bỏ qua thực thi (thường như `:prepare SKIPPED` và `:finish SKIPPED` khi dùng dry-run), còn các câu `println` bên trong `doLast` **không xuất hiện**. Đừng coi `--dry-run` là một lần kiểm thử tính đúng đắn của kết quả file/test; nó chỉ giúp quan sát những task dự kiến chạy.

### 6.6. Thử một task không được yêu cầu

Thêm vào cuối `build.gradle`:

~~~groovy
tasks.register('unused') {
    println '[CONFIG TASK] unused'
    doLast {
        println '[EXEC] unused'
    }
}
~~~

Với lệnh `gradle --no-configuration-cache --console=plain --quiet finish` và không có code nào hiện thực hóa `unused`, cả hai dòng của `unused` **không xuất hiện**. Gradle chỉ đăng ký task và tránh cấu hình chi tiết cho task chưa cần. Nếu đổi thành `gradle --no-configuration-cache --console=plain --quiet unused`, bạn sẽ thấy:

~~~text
[INIT] settings.gradle
[CONFIG] build.gradle
[CONFIG TASK] unused
[EXEC] unused
~~~

Điều này cho thấy **cấu hình của một task được trì hoãn** vẫn là configuration, không phải execution. Dòng `CONFIG TASK` nằm trong closure của `tasks.register` nhưng ở ngoài `doLast`. Khi task được hiện thực hóa để dựng graph, closure cấu hình chạy trước action.

## 7. Mở rộng: ba giai đoạn trong một multi-project build

Khi có nhiều project, ba giai đoạn vẫn là **vòng đời của build**, không phải ba vòng đời buộc phải chạy độc lập cho từng project.

Ví dụ:

~~~text
workspace/
├── settings.gradle
├── build.gradle
└── app/
    └── build.gradle
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'workspace'
include(':app')
println '[INIT] discovered root and app'
~~~

`build.gradle` ở root:

~~~groovy
println '[CONFIG] root'

tasks.register('rootInfo') {
    doLast {
        println '[EXEC] rootInfo'
    }
}
~~~

`app/build.gradle`:

~~~groovy
println '[CONFIG] app'

tasks.register('appInfo') {
    doLast {
        println '[EXEC] appInfo'
    }
}
~~~

Chạy:

~~~bash
gradle --no-configuration-cache --console=plain --quiet :app:appInfo
~~~

Trong một build thông thường không bật tối ưu chỉ cấu hình một tập project, các thông điệp chính là:

~~~text
[INIT] discovered root and app
[CONFIG] root
[CONFIG] app
[EXEC] appInfo
~~~

**Đọc đúng kết quả:** Settings đánh giá cây build trước; hai build script cấu hình các project; action của `:app:appInfo` chạy sau. Task `:rootInfo` không được chọn nên action của nó không chạy. Với các cơ chế như configuration-on-demand, isolated projects hoặc configuration cache, phạm vi/file được đánh giá lại có thể khác; vì vậy không dùng số dòng `CONFIG` để suy ra chắc chắn số project tồn tại.

Project path `:app` ở đây chỉ là địa chỉ logic của project. `:app:appInfo` là **task path** cụ thể. Khi chạy từ root, dùng task path tuyệt đối giúp tránh nhầm task tên giống nhau ở nhiều subproject.

## 8. Ví dụ Java 17: tác vụ compile/test thực sự nằm ở đâu?

Đối với ứng dụng Java, sự khác biệt giữa các giai đoạn vẫn như thí nghiệm `println`. Ví dụ Java 17 tối thiểu:

~~~text
java-phase-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── example/
                └── Main.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'java-phase-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.Main'
}
~~~

`src/main/java/example/Main.java`:

~~~java
package example;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Java 17 application");
    }
}
~~~

Chạy từ root bằng bản Gradle tương thích và JDK 17 sẵn có:

~~~bash
gradle --no-configuration-cache --console=plain --quiet run
~~~

Stdout **của chương trình Java**:

~~~text
Java 17 application
~~~

Mapping theo vòng đời:

- **Initialization:** Gradle xác định root project `java-phase-demo` từ settings.
- **Configuration:** plugin `application` được áp dụng; plugin Java liên quan cung cấp task `compileJava`, `processResources`, `classes` và `run`; `mainClass` và toolchain được cấu hình.
- **Execution:** khi yêu cầu `run`, các task phụ thuộc cần thiết được xử lý, chẳng hạn compile nguồn trước khi chạy ứng dụng; cuối cùng Java main được gọi và in dòng trên.

Nếu chạy `gradle --no-configuration-cache --console=plain --quiet classes`, Gradle chuẩn bị class/resource nhưng **không chạy `Main.main(...)`** vì `classes` và `run` là hai task khác nhau. Nếu chạy `gradle tasks`, Gradle có thể liệt kê `run` mà chưa hề chạy chương trình.

Ví dụ Java này hoàn chỉnh và có thể chạy được. Nếu Gradle báo không tìm được toolchain Java 17, hãy cài JDK 17 hoặc cấu hình cơ chế cung cấp toolchain; không suy ra đó là lỗi của phase execution hay của cú pháp `mainClass`.

## 9. Phân biệt build lifecycle với task lifecycle

Một task có đời sống riêng: được **đăng ký**, được **cấu hình khi cần**, được **chọn vào task graph**, rồi có thể **chạy action**, hoặc bị bỏ qua.

~~~text
tasks.register('example')
         |
         v
TaskProvider (chưa cần tạo Task instance)
         |
         v
Task được realize/configure nếu cần
         |
         v
Task được chọn vào graph (được yêu cầu / phụ thuộc)
         |
         v
Kiểm tra điều kiện, cache, inputs/outputs
         |
         +--> EXECUTE action
         |
         +--> UP-TO-DATE / FROM-CACHE / SKIPPED / NO-SOURCE
~~~

Không nên suy luận “task không xuất hiện trong output = Gradle không biết task đó”: một task có thể đã đăng ký nhưng không được hiện thực hóa hoặc không được chọn để chạy.

Ngược lại, một task **có mặt** trong graph mà được đánh dấu `UP-TO-DATE` không có nghĩa Gradle đã bỏ qua khởi tạo và cấu hình của toàn bộ build. Tình trạng thực thi của task và cache cấu hình thuộc hai lớp cơ chế khác nhau.

## 10. Configuration Cache, build cache và up-to-date checks

Ba tính năng dễ bị trộn lẫn:

| Cơ chế | Đối tượng được tối ưu | Lợi ích và điều kiện |
| --- | --- | --- |
| **Configuration Cache** | Kết quả mô hình cấu hình/task graph và dữ liệu cần thiết | Khi cache hit hợp lệ, Gradle có thể tránh đánh giá lại cấu hình và dùng lại task graph; yêu cầu build logic/plugin tuân thủ các ràng buộc tương thích |
| **Build Cache** | Kết quả của task cacheable | Có thể sử dụng output tính toán trước khi đầu vào, cấu hình và điều kiện cache tương thích; hỗ trợ local/remote cache |
| **Up-to-date checks** | Task và output hiện có | Khi inputs/outputs và trạng thái phù hợp, task có thể không cần chạy lại action |

Ví dụ hai lần gọi cùng `gradle build` có thể có khác biệt lớn: lần đầu cấu hình toàn bộ và chạy task, lần sau có thể dùng configuration cache để giảm việc cấu hình; một số task có thể `UP-TO-DATE` hoặc `FROM-CACHE`. Các hiện tượng đó không được xem là một loại cache duy nhất.

**Quan trọng khi học và debug:** Với bài quan sát `println` ở mục 6, dùng `--no-configuration-cache` giúp dễ thấy giai đoạn bằng log. Trong hệ thống thật, giữ configuration cache khi phù hợp là tối ưu có giá trị; chỉ tắt tạm trong thí nghiệm hoặc để chẩn đoán.

Không nên viết logic phụ thuộc vào việc file `build.gradle` được đánh giá lại trong mọi lần build. Nếu dùng Configuration Cache, Gradle có thể dùng kết quả cấu hình được lưu thay vì gọi lại một số mã cấu hình.

## 11. Điều gì nên đặt ở configuration và điều gì nên đặt ở execution?

Hãy hỏi: **“Câu lệnh này mô tả build hay đang tạo ra kết quả build?”**

| Công việc | Nơi phù hợp hơn | Vì sao |
| --- | --- | --- |
| Áp dụng `java`/`application` plugin | Configuration | Xác định khả năng và task của project |
| Khai báo repository, dependency, toolchain | Configuration | Cung cấp thông tin cho Gradle giải quyết mô hình build |
| Đăng ký task, khai báo `dependsOn` | Configuration | Cung cấp cấu trúc graph |
| Đặt `inputs.file(...)`, `outputs.file(...)` | Configuration | Giúp Gradle theo dõi đầu vào/đầu ra của task |
| Viết file code được sinh ra | Task execution | Có output kiểm soát được, chỉ chạy khi task cần |
| Biên dịch Java, chạy test, tạo JAR | Task execution | Là công việc thực sự tạo kết quả |
| In thông điệp nhằm minh họa phase | Có thể ở script hoặc action, tùy mục tiêu học | Cần phân biệt log lúc cấu hình và log lúc thực thi |

### 11.1. Ví dụ không nên làm: tạo file ngay trong build script

~~~groovy
// KHÔNG NÊN: chạy thao tác I/O khi cấu hình project.
def output = file("$buildDir/generated/message.txt")
output.parentFile.mkdirs()
output.text = 'hello'
~~~

Đoạn này ghi file **ngay khi build script được đánh giá**, kể cả nếu bạn chỉ chạy `gradle help` hoặc `gradle tasks`. Nó làm build khó dự đoán, có side effect ở configuration và khó phối hợp với các tối ưu build. Trong thực tế, bạn còn nên tránh dùng API `buildDir` cũ khi đã có Provider API phù hợp.

### 11.2. Cách đúng hơn: khai báo output và viết ở task action

~~~groovy
def generatedMessage = layout.buildDirectory.file('generated/message.txt')

tasks.register('generateMessage') {
    outputs.file(generatedMessage)

    doLast {
        def target = generatedMessage.get().asFile
        target.parentFile.mkdirs()
        target.setText('hello', 'UTF-8')
    }
}
~~~

Đây là ví dụ **task trong build script Groovy**, không phải file Java. Nó dùng `layout.buildDirectory.file(...)` tạo provider cho output, khai báo `outputs.file(...)` để Gradle biết artifact mà task tạo, rồi chỉ ghi file trong `doLast`. Lần chạy đầu:

~~~bash
gradle --console=plain generateMessage
~~~

Task tạo file `build/generated/message.txt` chứa chính xác chuỗi `hello`. Lần chạy tiếp theo, nếu output còn nguyên và các điều kiện khác không đổi, Gradle có thể đánh dấu task `UP-TO-DATE` thay vì chạy lại action. Ví dụ có nội dung cố định và không có input biến đổi; trong task thật, hãy khai báo input rõ ràng để Gradle phát hiện thay đổi hợp lệ.

Với logic tùy biến lâu dài, ưu tiên **typed task** với `@Input`/`@OutputFile` và `@TaskAction` thay vì dựa nhiều vào closure trong build script; cách này giúp kiểm thử và làm rõ tương thích configuration cache.

## 12. Cách quan sát và debug chính xác

### 12.1. Các lệnh hữu ích

~~~bash
# Xem nhiệm vụ được chọn, không chạy action của task.
gradle --dry-run build

# Xem nhiều thông tin hơn về cấu hình / lựa chọn task.
gradle --info build

# Khi cần phân tích lỗi chi tiết.
gradle --stacktrace build

# Liệt kê task hiện có trong project.
gradle tasks --all

# Xem các project trong build.
gradle projects

# Quan sát thí nghiệm phase mà không tái dùng Configuration Cache.
gradle --no-configuration-cache --quiet finish
~~~

Trong project thật có Gradle Wrapper, thay `gradle` bằng `./gradlew` trên macOS/Linux hoặc `gradlew.bat` trên Windows. Wrapper giúp nhất quán bản Gradle giữa máy cá nhân và CI.

### 12.2. Dấu hiệu nhận biết lỗi theo giai đoạn

| Triệu chứng | Cần kiểm tra trước |
| --- | --- |
| Không tìm được `settings.gradle` hoặc root/subproject không đúng | Initialization: thư mục làm việc, settings, `include`, project path |
| Plugin không được tìm thấy/không áp dụng được | Configuration hoặc phần plugin resolution liên quan: plugin repositories, phiên bản, cấu trúc `plugins` |
| Lỗi cú pháp Groovy/Kotlin DSL trong `build.gradle` | Configuration: script và vị trí closure |
| `Task 'run' not found` | Configuration/task selection: plugin nào tạo task, project/task path có đúng không |
| `Circular dependency between the following tasks` | Cấu hình quan hệ và lúc dựng task graph |
| `compileJava FAILED` do lỗi cú pháp Java | Execution: source Java, toolchain, classpath |
| `test FAILED` do assertion sai | Execution: test code và report |
| Task báo `UP-TO-DATE` hoặc `FROM-CACHE` | Execution/optimization: trạng thái input/output và cache |
| Task action không in gì khi dùng `--dry-run` | Kỳ vọng: action bị bỏ qua vì đang dry-run |
| `println` top-level chạy dù chỉ gọi `help` | Kỳ vọng khi script cấu hình được đánh giá |

Bảng chỉ hướng chẩn đoán ban đầu, không khẳng định mọi lỗi chỉ thuộc một phase. Chẳng hạn dependency resolution có thể bị kích hoạt sớm trong configuration do code build ép đọc artifact, hoặc được thực hiện trong thời điểm khác khi Configuration Cache hoạt động.

### 12.3. Một số điểm cần tránh khi quan sát

- **Không dùng thời điểm in log làm mô hình tuyệt đối về mọi task:** giữa các subproject và các task độc lập, Gradle có thể thực hiện hoặc cấu hình theo cách được tối ưu và thay đổi theo phiên bản.
- **Đừng ép task bằng `tasks.getByName(...)` nếu chỉ cần tham chiếu:** API này có thể hiện thực hóa task sớm. Dùng `tasks.named(...)` hoặc lưu `TaskProvider`.
- **Đừng đưa công việc tốn thời gian vào top-level script:** file access, network call, process execution hoặc tạo artifact trong configuration ảnh hưởng cả lệnh chỉ cần `help`.
- **Đừng coi `--dry-run` là build thành công:** nó bỏ qua action, nên không chứng minh mã Java biên dịch hoặc test chạy đúng.
- **Đừng đồng nhất `doLast` với toàn bộ execution:** plugin có thể định nghĩa công việc trong custom task type; `doLast` chỉ là một cách gắn action.
- **Đừng suy “sau initialization là cấu hình mọi project vô điều kiện”:** tối ưu cấu hình, included builds, task selection, cache và các cài đặt chuyên biệt có thể thay đổi phạm vi được đánh giá.

## 13. Những hiểu lầm phổ biến

1. **“Gradle chạy từ trên xuống dưới toàn bộ `build.gradle` để build.”** Không chính xác. Build script được đánh giá để cấu hình; các task action được lên lịch riêng theo graph.
2. **“`tasks.register` sẽ chạy task ngay.”** Sai. Registration chỉ đưa task vào mô hình; action chạy khi task được chọn và cần thực thi.
3. **“Mọi code trong `tasks.register { ... }` đều thuộc execution.”** Sai. Closure cấu hình task là configuration, còn `doFirst`/`doLast` là task action.
4. **“`settings.gradle` là nơi định nghĩa các bước biên dịch.”** Thường không. Settings tổ chức build; task/plugin làm việc ở model project.
5. **“Gọi `:app:build` chỉ chạy đúng một task duy nhất.”** Sai. Task đó có thể cần compile, test, packaging và dependency task ở project khác.
6. **“Task đã lên graph thì chắc chắn luôn chạy action.”** Sai. Up-to-date check, cache và điều kiện skip có thể khiến action không chạy.
7. **“Configuration Cache và Build Cache là một.”** Sai. Một cơ chế tối ưu cấu hình/task graph; cơ chế kia tối ưu việc tái sử dụng output của task.
8. **“`mustRunAfter` giống `dependsOn`.”** Sai. Ràng buộc thứ tự không tự bổ sung task còn thiếu vào graph.
9. **“In thông điệp tại configuration để biết task có chạy hay không.”** Không đủ. Hãy quan sát action/trạng thái task; log cấu hình chỉ cho biết phần cấu hình đã được đánh giá.

## 14. Bài tập tự kiểm tra

### Bài 1 — Dự đoán thứ tự

`settings.gradle`:

~~~groovy
rootProject.name = 'quiz'
println 'S'
~~~

`build.gradle`:

~~~groovy
println 'C'

def first = tasks.register('first') {
    doLast { println 'A' }
}

tasks.register('second') {
    dependsOn(first)
    doLast { println 'B' }
}
~~~

Chạy `gradle --no-configuration-cache --quiet second`. Những dòng do ví dụ tạo ra xuất hiện theo thứ tự nào?

**Đáp án:** `S`, `C`, `A`, `B`. `S` thuộc initialization, `C` thuộc configuration, task `first` là dependency của `second` nên action A trước B.

### Bài 2 — Vì sao không in?

Bạn chỉ chạy `gradle help` trong một build có đoạn:

~~~groovy
tasks.register('special') {
    doLast {
        println 'SPECIAL'
    }
}
~~~

Vì sao không thấy `SPECIAL`?

**Đáp án:** Task `special` không được yêu cầu và task `help` không cần nó. Gradle không chạy action của `special` chỉ vì task được khai báo.

### Bài 3 — Nhận diện side effect

Đoạn nào nên nằm trong execution khi tạo artifact?

~~~groovy
// A
file('result.txt').text = 'done'

// B
tasks.register('writeResult') {
    doLast {
        file('result.txt').text = 'done'
    }
}
~~~

**Đáp án:** Về thời điểm ghi file, B đưa tác động vào task action, còn A ghi file ngay lúc đánh giá script. Trong build thực tế, nên cải thiện B bằng provider và khai báo `outputs.file(...)` để kiểm soát đường dẫn/input/output, nhất là khi dùng configuration cache.

### Bài 4 — Task graph

Task `publish` phụ thuộc `packageApp`, task `packageApp` phụ thuộc `compileJava`. Nếu yêu cầu `publish`, có thể cho `publish` chạy trước `compileJava` không?

**Đáp án:** Không, vì dependency graph yêu cầu `compileJava` trước `packageApp` trước `publish`. Tuy nhiên từng task có thể được đánh dấu bỏ qua action hoặc lấy kết quả từ cache nếu hợp lệ.

### Bài 5 — Nhận diện cache

Lần thứ hai chạy build, không thấy `println` top-level trong `build.gradle`, nhưng task trong build vẫn được xử lý. Khả năng nào cần kiểm tra?

**Đáp án:** Configuration Cache có thể đã tái sử dụng mô hình/task graph. Kiểm tra log cache hoặc chạy thí nghiệm với `--no-configuration-cache`. Đừng suy rằng Gradle không có giai đoạn configuration ở mức khái niệm.

## 15. Tổng kết

Hiểu ba giai đoạn theo câu hỏi:

- **Initialization — “CÓ NHỮNG PROJECT NÀO?”** Gradle xác định build và project tree dựa trên settings.
- **Configuration — “CẦN LÀM NHỮNG TASK NÀO VÀ CHÚNG LIÊN HỆ RA SAO?”** Gradle đánh giá cấu hình, plugin và xây dựng task graph.
- **Execution — “THỰC HIỆN CÔNG VIỆC NÀO?”** Gradle xử lý task action, theo dõi đầu vào/đầu ra và áp dụng cơ chế tránh làm lại khi đủ điều kiện.

Khi tự tạo task Gradle, hãy **đăng ký và khai báo dependencies/inputs/outputs trong configuration**, sau đó **đặt tác động tạo kết quả vào task execution**. Kết hợp `tasks.register`/`tasks.named`, graph rõ ràng và cơ chế cache phù hợp sẽ giúp build dễ hiểu, dễ debug và mở rộng an toàn.

Tài liệu tham khảo chính thức:

- [Gradle User Manual — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html)
- [Gradle User Manual — Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Gradle User Manual — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle User Manual — Task Basics](https://docs.gradle.org/current/userguide/task_basics.html)
