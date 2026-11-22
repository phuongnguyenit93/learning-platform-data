# Phân biệt mã cấu hình task với hành động thực thi task trong Gradle

## 1. Vấn đề: cùng nằm trong một khối task nhưng chạy ở thời điểm khác nhau

Một câu hỏi phổ biến khi mới học Gradle: tại sao một dòng `println` trong `tasks.register { ... }` đôi khi xuất hiện ngay khi Gradle đang chuẩn bị build, còn dòng `println` trong `doLast { ... }` chỉ xuất hiện lúc chạy task? Hai đoạn này phục vụ **hai trách nhiệm khác nhau**:

- **Mã cấu hình task (task configuration)** mô tả task sẽ làm gì, nhận input/output gì, phụ thuộc task nào, có thuộc tính và quy tắc chạy ra sao. Nó thiết lập mô hình build để Gradle lập kế hoạch.
- **Hành động thực thi task (task execution action)** thực hiện công việc khi task thật sự được chọn và được phép chạy: tạo file, biên dịch, sao chép dữ liệu, chạy test, in thông báo phục vụ công việc, v.v.

Không thể kết luận “mọi dòng trong cặp ngoặc `tasks.register { ... }` đều là hành động task”. Cần xem đoạn mã nằm trực tiếp trong cấu hình hay bên trong một action như `doFirst { ... }` / `doLast { ... }`.

Ví dụ nhỏ với Kotlin DSL:

~~~kotlin
tasks.register("chao") {
    println("CONFIG: dang cau hinh task chao")

    doLast {
        println("ACTION: xin chao!")
    }
}
~~~

Dòng `CONFIG` được chạy khi Gradle **thực sự cấu hình/realize task `chao`**. Dòng `ACTION` thuộc hành động thực thi, chạy **khi task được thực thi** và không bị bỏ qua. Hai dòng không có cùng thời điểm và không có cùng bảo đảm sẽ chạy.

## 2. Liên hệ với ba giai đoạn vòng đời build

Trong một lần chạy thông thường, Gradle có ba giai đoạn khái niệm:

| Giai đoạn | Gradle làm gì? | Ví dụ mã liên quan |
| --- | --- | --- |
| **Initialization** | Xác định settings, những project tham gia build và môi trường ban đầu | `settings.gradle` / `settings.gradle.kts` |
| **Configuration** | Đánh giá build scripts, áp dụng plugin, đăng ký và cấu hình mô hình task, xác định đồ thị task cần chạy | `plugins { }`, `dependencies { }`, `tasks.register(...)`, giá trị `group`/`description`, `dependsOn(...)` |
| **Execution** | Thực hiện các task đã được chọn theo phụ thuộc và điều kiện; chạy các action khi cần | `doFirst { }`, `doLast { }`, action của loại task như `JavaCompile` hoặc `Copy` |

Trình tự khái quát:

~~~text
Chạy ./gradlew <ten-task>
        |
        v
[Initialization]
  đọc settings, xác định project
        |
        v
[Configuration]
  đọc build script, đăng ký task
  cấu hình các task được realize khi cần
  xác định dependencies/đồ thị thực thi
        |
        v
[Execution]
  task được chọn + điều kiện phù hợp?
       |             |
      Có            Không
       |             |
  thực thi action   UP-TO-DATE / FROM-CACHE /
       |            SKIPPED / NO-SOURCE ...
  ghi output
~~~

**Hai lưu ý để hiểu đúng sơ đồ:**

1. Với cơ chế *configuration avoidance*, `tasks.register` chỉ **đăng ký lười (lazy registration)**. Khối cấu hình truyền vào `register` không nhất thiết chạy ngay tại dòng đăng ký. Nó được chạy **khi Gradle realize task**, thường khi task cần tham gia đồ thị hoặc có mã yêu cầu nó sớm. Vì vậy, “mã cấu hình task” là tên **vai trò** của mã, không phải cam kết rằng khối này sẽ chạy ngay khi file script được đọc.
2. Khi **Configuration Cache** tái sử dụng được cấu hình của lần chạy trước, Gradle có thể không đánh giá lại build script như thường lệ. Bởi vậy, không phải cứ chạy Gradle là những dòng `println` ở thời điểm cấu hình đều được in lại. Trong thí nghiệm phía dưới, dùng `--no-configuration-cache` để quan sát rõ cơ chế bình thường.

## 3. Cách nhận diện mã cấu hình và action ngay trong build script

Ví dụ hoàn chỉnh bằng Groovy DSL, file `build.gradle`:

~~~groovy
println 'CONFIG SCRIPT: dang danh gia build.gradle'

tasks.register('chao') {
    group = 'learning'
    description = 'Minh hoa config va action'

    println 'CONFIG TASK: dang cau hinh chao'

    doFirst {
        println 'ACTION FIRST: truoc cac action tiep theo'
    }

    doLast {
        println 'ACTION LAST: xin chao Gradle'
    }
}
~~~

Bản tương đương bằng Kotlin DSL, file `build.gradle.kts`:

~~~kotlin
println("CONFIG SCRIPT: dang danh gia build.gradle.kts")

tasks.register("chao") {
    group = "learning"
    description = "Minh hoa config va action"

    println("CONFIG TASK: dang cau hinh chao")

    doFirst {
        println("ACTION FIRST: truoc cac action tiep theo")
    }

    doLast {
        println("ACTION LAST: xin chao Gradle")
    }
}
~~~

**Chỉ chọn một trong hai file** để chạy thí nghiệm trong một project Gradle có Wrapper; ví dụ này không cần source Java, không phụ thuộc repository bên ngoài và tương thích với cách sử dụng task phổ biến của Gradle hiện đại.

Phân tích từng vị trí:

| Dòng / khối | Phân loại | Khi nào chạy hoặc có tác dụng? |
| --- | --- | --- |
| `println` ở đầu build script | Mã cấu hình ở cấp build script | Khi script thực sự được đánh giá; không phải action của `chao` |
| `tasks.register("chao")` | Đăng ký task | Khi script được đánh giá, trả về `TaskProvider`; không tự thực thi task |
| `group = ...`, `description = ...` | Cấu hình thuộc tính task | Khi task được realize và khối cấu hình được áp dụng |
| `println("CONFIG TASK...")` | Mã cấu hình task | Chạy khi khối cấu hình được áp dụng; **không phải** action |
| `doFirst { ... }` | Khai báo/thêm action ở đầu danh sách action | Phần thân closure/lambda chạy khi task thật sự được thực thi |
| `doLast { ... }` | Khai báo/thêm action ở cuối danh sách action | Phần thân chạy sau các action đứng trước khi task được thực thi |
| Nội dung của `println` trong `doFirst` / `doLast` | Công việc của action | Không chạy đơn thuần vì Gradle đang tạo task graph |

**Điểm dễ gây nhầm:** khi thực hiện lời gọi `doLast { ... }` trong lúc cấu hình, Gradle chỉ **gắn một action** vào task. Nó không thực thi ngay những câu lệnh nằm **bên trong** closure/lambda đó.

## 4. Thử nghiệm từng lệnh và quan sát kết quả

Đứng tại thư mục chứa Wrapper: dùng `./gradlew` trên Linux/macOS hoặc `.\gradlew.bat` trên Windows. Nếu project sử dụng script Groovy hay Kotlin ở mục 3, chạy:

~~~bash
# Linux/macOS
./gradlew -q help --no-configuration-cache
./gradlew -q chao --no-configuration-cache
./gradlew chao --dry-run --no-configuration-cache --console=plain
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat -q help --no-configuration-cache
.\gradlew.bat -q chao --no-configuration-cache
.\gradlew.bat chao --dry-run --no-configuration-cache --console=plain
~~~

### 4.1. Chạy `help`: có cấu hình build nhưng không chạy action của `chao`

Với script độc lập ở mục 3, việc chạy `help` thông thường đánh giá script cấp project nên sẽ in dòng `CONFIG SCRIPT`, ngoài nội dung của task `help`. Do `chao` được đăng ký lazy và không cần để thực thi `help`, khối `CONFIG TASK` thường **không được realize**, và chắc chắn **không có dòng ACTION của `chao`**.

Lưu ý các công cụ, plugin hoặc cách tra cứu task khác có thể chủ động realize task, làm khối `CONFIG TASK` chạy dù task không được thực thi. Vì vậy, đừng dùng sự xuất hiện của dòng config để chứng minh task action đã chạy.

### 4.2. Chạy `chao`: cấu hình trước, action sau

Với script Groovy ở mục 3, khi chạy lệnh `./gradlew -q chao --no-configuration-cache` trong project đơn giản không có plugin hoặc script phụ, các dòng do **chính mã ví dụ** in ra theo thứ tự:

~~~text
CONFIG SCRIPT: dang danh gia build.gradle
CONFIG TASK: dang cau hinh chao
ACTION FIRST: truoc cac action tiep theo
ACTION LAST: xin chao Gradle
~~~

Với bản Kotlin, thứ tự và nội dung các dòng giống trên, ngoại trừ dòng đầu có tên `build.gradle.kts`:

~~~text
CONFIG SCRIPT: dang danh gia build.gradle.kts
CONFIG TASK: dang cau hinh chao
ACTION FIRST: truoc cac action tiep theo
ACTION LAST: xin chao Gradle
~~~

`-q` (quiet) giúp giảm log của Gradle; Gradle/Wrapper vẫn có thể hiển thị thông tin môi trường hoặc cảnh báo riêng. Thứ tự cần ghi nhớ là: script được đánh giá → cấu hình task khi task được realize → thực hiện các action theo thứ tự đã đăng ký.

### 4.3. Chạy `--dry-run`: tạo kế hoạch mà không thực hiện action

Lệnh `./gradlew chao --dry-run --no-configuration-cache` vẫn cần chuẩn bị đồ thị task; mã cấu hình có thể chạy. Nhưng Gradle **không thực thi action của task**. Vì vậy, các dòng `ACTION FIRST` và `ACTION LAST` từ ví dụ không xuất hiện. Output có thể có dòng mô tả task và dấu `SKIPPED` do Gradle in ra.

Đây là cách đơn giản để kiểm tra xem một câu `println` hoặc lời gọi API nằm ở phần cấu hình hay phần action: nếu nó vẫn xảy ra khi `--dry-run`, nhiều khả năng đó là hành vi trong cấu hình/khởi tạo (hoặc từ plugin khác), không phải action task được Gradle thực thi.

## 5. Task được đăng ký, được realize và được thực thi là ba trạng thái khác nhau

Ba khái niệm có liên hệ nhưng không đồng nhất:

1. **Registered:** Gradle biết một task có tên và cách tạo/cấu hình nó khi cần. `tasks.register("a") { ... }` trả về `TaskProvider`; chỉ đăng ký **không tự chạy task**.
2. **Realized/configured:** đối tượng task đã được tạo và cấu hình tương ứng được áp dụng. Lúc này `println` nằm trực tiếp trong cấu hình task có thể chạy, ngay cả khi sau đó task không được chọn thực thi.
3. **Executed:** task thuộc đồ thị thực thi và Gradle thực sự chạy các action cần thiết của nó. Nếu bị skip/up-to-date/cache hit, hành động có thể không chạy.

Ví dụ Kotlin DSL:

~~~kotlin
val taskA = tasks.register("taskA") {
    println("CONFIG: taskA was realized")
    doLast {
        println("ACTION: taskA")
    }
}

tasks.named("taskA") {
    description = "Dang ky va cau hinh lazy"
}
~~~

- `tasks.register` tạo một *provider* để Gradle có thể trì hoãn việc tạo task.
- `tasks.named("taskA") { ... }` bổ sung cấu hình **cho task đã đăng ký**, nhìn chung vẫn giữ cách làm lazy; không nhất thiết thực thi khối cấu hình ngay.
- `taskA.get()` nếu được gọi ở nơi khác sẽ buộc provider cung cấp đối tượng task và có thể làm task được realize sớm. Trong build script thực tế, chỉ gọi `get()` khi có nhu cầu rõ ràng.
- `tasks.create(...)` và nhiều cách lấy task trực tiếp kiểu `tasks.getByName(...)` có tính eager hơn; tránh dùng chỉ để cấu hình một task có thể cấu hình qua provider.

Cần nhớ: **configuration avoidance** tối ưu việc cấu hình những task không liên quan. Nó làm thời điểm `CONFIG TASK` có thể thay đổi. Nhưng khi action của một task được thực thi, task đó đã được realize/cấu hình phù hợp trước khi hành động bắt đầu.

## 6. Cấu hình task không chỉ có group và description

Cấu hình còn xác định quan hệ phụ thuộc, input/output, điều kiện thực thi, các giá trị mà action sẽ sử dụng. Ví dụ đầy đủ bằng Kotlin DSL:

~~~kotlin
tasks.register("chuanBi") {
    group = "learning"
    doLast {
        println("ACTION: chuanBi")
    }
}

tasks.register("dongGoi") {
    group = "learning"
    dependsOn("chuanBi")

    println("CONFIG: dongGoi depends on chuanBi")

    doLast {
        println("ACTION: dongGoi")
    }
}
~~~

Bản Groovy DSL:

~~~groovy
tasks.register('chuanBi') {
    group = 'learning'
    doLast {
        println 'ACTION: chuanBi'
    }
}

tasks.register('dongGoi') {
    group = 'learning'
    dependsOn 'chuanBi'

    println 'CONFIG: dongGoi depends on chuanBi'

    doLast {
        println 'ACTION: dongGoi'
    }
}
~~~

Chạy `./gradlew -q dongGoi --no-configuration-cache` trong project thử nghiệm. Dòng `CONFIG: dongGoi depends on chuanBi` thuộc cấu hình; Gradle dùng `dependsOn` để đưa `chuanBi` vào đồ thị trước `dongGoi`. Khi cả hai được phép thực thi, hai dòng action xuất hiện theo thứ tự:

~~~text
ACTION: chuanBi
ACTION: dongGoi
~~~

Dòng cấu hình của `dongGoi` có thể được in trước hai dòng trên; không thể suy thứ tự cấu hình giữa các task khác nhau chỉ từ thứ tự các action. `dependsOn` xác định **thứ tự thực thi** theo dependency, không phải bảo đảm thứ tự realize/configure các task.

### 6.1. Task có action “ẩn” trong loại task

Không phải mọi task có thể nhìn thấy công việc chính trong `doFirst` hay `doLast` của build script. Plugin và loại task Gradle có thể định nghĩa action sẵn, ví dụ `JavaCompile` biên dịch Java, `Test` chạy kiểm thử và `Copy` sao chép file. Khi bạn cấu hình:

~~~kotlin
tasks.register<Copy>("saoChep") {
    from("src/docs")
    into(layout.buildDirectory.dir("copied-docs"))
}
~~~

các lời gọi `from(...)` và `into(...)` thiết lập nguồn/đích **trong cấu hình**. Công việc sao chép thật sự do action mà loại task `Copy` định nghĩa và sẽ được thực hiện khi task `saoChep` chạy. Nếu thư mục nguồn không có file, kết quả có thể là `NO-SOURCE` hoặc không có output cần tạo, tùy cách task được định nghĩa và trạng thái thực tế.

Điều tương tự áp dụng với Groovy DSL:

~~~groovy
tasks.register('saoChep', Copy) {
    from 'src/docs'
    into layout.buildDirectory.dir('copied-docs')
}
~~~

Vậy câu hỏi đúng để phân loại là: **“Dòng này đang cấu hình mô hình task, hay đang nằm trong một action được Gradle gọi khi thực thi?”** Không nên chỉ xét tên hàm có mang nghĩa hành động (như `from`, `into`) hay không.

## 7. Kết quả build và các cơ chế skip ảnh hưởng action thế nào?

Một task **đã được cấu hình** vẫn có thể không chạy action nếu Gradle quyết định công việc không cần thiết hoặc không hợp lệ để chạy:

| Trạng thái/kịch bản | Cấu hình task | Hành động thực thi |
| --- | --- | --- |
| Task được chọn, cần chạy bình thường | Cấu hình khi cần | Chạy |
| Task được Gradle xác định `UP-TO-DATE` | Task đã có đủ mô hình để đánh giá trạng thái | Action thường bị bỏ qua |
| Task được phục hồi `FROM-CACHE` | Cấu hình cần thiết đã có | Không chạy action để tính lại output; output được phục hồi từ Build Cache |
| Task `SKIPPED` do `onlyIf` trả về false hoặc task bị disabled | Có thể đã cấu hình | Không chạy |
| Task `NO-SOURCE` | Có thể đã cấu hình | Công việc chính được bỏ qua vì không có nguồn |
| `--dry-run` | Vẫn xác định task graph | Action không được thực thi |
| Configuration Cache được tái sử dụng | Phần đánh giá/cấu hình có thể được bỏ qua nhờ state đã lưu | Action của task vẫn được chạy nếu task thực sự cần thực thi |

Những nhãn trên là kết quả thường thấy nhưng không phải mọi loại task đều có cơ chế input/output hoặc caching như nhau. Một task không khai báo đầu ra (ví dụ tác vụ chỉ `println`) thường tiếp tục chạy action mỗi lần được yêu cầu, trừ khi có điều kiện skip khác. Vì thế, thử nghiệm với `chao` ở mục 3 phù hợp hơn để quan sát action so với chọn một task đã có output `UP-TO-DATE`.

Cũng cần phân biệt:

- **Build Cache** tái sử dụng *kết quả task* khi task được cacheable, inputs và điều kiện đủ hợp lệ.
- **Configuration Cache** tái sử dụng *mô hình cấu hình build* và một phần trạng thái liên quan, giảm việc chạy lại mã cấu hình.
- **Incremental build / up-to-date checks** dùng thông tin input/output để quyết định có cần thực thi một task hay không.

Ba cơ chế khác nhau. Đặc biệt, **không in dòng CONFIG** ở một lượt chạy có Configuration Cache không có nghĩa task action không chạy; và **không in dòng ACTION** có thể do task không nằm trong graph, do skip, do cache hit hoặc do dry-run.

## 8. Đặt I/O, tác dụng phụ và logic nặng vào đâu?

Phần cấu hình cần chủ yếu **mô tả** công việc, không thực hiện công việc đó. Ví dụ phản diện trong Kotlin DSL:

~~~kotlin
tasks.register("taoBaoCao") {
    // KHÔNG NÊN: chạy I/O trong cấu hình task.
    val inputText = file("data/source.txt").readText()
    println("Da doc du lieu: " + inputText.length)

    doLast {
        println("Xu ly: " + inputText)
    }
}
~~~

Vấn đề là file đã bị đọc ngay khi task được realize, không đợi đến lúc action thực thi. Nó có thể bị đọc khi chỉ tra cứu task, làm configuration chậm, tạo phụ thuộc ngầm, gây lỗi nếu file chưa được tạo hoặc làm Configuration Cache khó theo dõi. Dữ liệu đầu vào chỉ được đọc một lần ở thời điểm cấu hình, trong khi điều người học thường muốn là đọc dữ liệu tại thời điểm thực thi.

Một minh họa gọn hơn, dùng action để xử lý dữ liệu trong dự án (Kotlin DSL):

~~~kotlin
val inputFile = layout.projectDirectory.file("data/source.txt")

tasks.register("taoBaoCao") {
    group = "learning"
    description = "Doc noi dung cua mot file khi task thuc thi"

    inputs.file(inputFile)

    doLast {
        val text = inputFile.asFile.readText()
        println("Noi dung dau vao: " + text.trim())
    }
}
~~~

Đoạn thứ hai giả định đã có `data/source.txt`, và vì khai báo `inputs.file(inputFile)`, Gradle biết file là một input của task. Nếu file không tồn tại, Gradle có thể báo lỗi xác thực input; cần tạo file trước khi chạy hoặc điều chỉnh khai báo nếu việc thiếu file là hợp lệ. Với tác vụ có đầu ra thật, cũng cần khai báo `outputs.file(...)`/`outputs.dir(...)` (hoặc dùng custom task type với annotation input/output) để việc up-to-date/cache hoạt động chính xác.

**Cần thận trọng với Configuration Cache:** dùng `doLast` giúp đặt công việc vào execution, nhưng bản thân vị trí `doLast` **không tự bảo đảm** action tương thích Configuration Cache. Action không nên phụ thuộc đối tượng `Project`, script instance, dịch vụ nội bộ chưa khai báo hoặc trạng thái không serialize được trong execution. Với build logic lớn, nên định nghĩa **custom task type** dùng các thuộc tính dạng `Property`/`RegularFileProperty`/`DirectoryProperty`, khai báo `@Input`/`@InputFile`/`@OutputFile` và đặt công việc trong một phương thức `@TaskAction`.

### 8.1. Mẫu custom task type để thấy ranh giới rõ ràng

Ví dụ Kotlin DSL trong `build.gradle.kts`, thể hiện một task type tối thiểu, hoạt động với Gradle Kotlin DSL thông thường:

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction
import org.gradle.api.provider.Property

abstract class BaoTinTask : DefaultTask() {
    @get:Input
    abstract val loiChao: Property<String>

    @TaskAction
    fun thucHien() {
        println("ACTION: " + loiChao.get())
    }
}

tasks.register<BaoTinTask>("baoTin") {
    group = "learning"
    description = "Task type co @TaskAction"
    loiChao.set("Xin chao tu custom task")
}
~~~

Phần `loiChao.set(...)` là **cấu hình giá trị input**. Phương thức `thucHien()` có `@TaskAction` mới là **hành động thực thi**. Đây là một cách tổ chức rõ ràng hơn cho task phức tạp so với nhồi nhiều I/O vào closure cấu hình. Ví dụ chỉ in thông báo và không có output file nên không minh họa việc cache lại output; muốn cache kết quả cần thiết kế output và khai báo tính cacheability phù hợp.

## 9. Cách đọc code build.gradle và build.gradle.kts của một project thật

Khi gặp một task, hãy đọc theo trình tự:

1. **Task được khai báo ở đâu?** `tasks.register(...)`, `tasks.named(...)`, `tasks.create(...)` hay do plugin tự đăng ký? Đọc plugin liên quan nếu chưa thấy định nghĩa task.
2. **Task type là gì?** `DefaultTask`, `Copy`, `JavaCompile`, `Test`, custom class... Loại task cho biết Gradle đã có action tích hợp sẵn hay chưa.
3. **Những dòng nào đặt thuộc tính?** `group`, `description`, `dependsOn`, `enabled`, `inputs`, `outputs`, `onlyIf`, thuộc tính extension/task type... Chúng là phần thiết lập.
4. **Những action nào chạy?** Tìm `doFirst`, `doLast` và `@TaskAction` trong loại task/plugin. `doFirst`/`doLast` có thể xuất hiện trong plugin hoặc phần cấu hình khác, không nhất thiết nằm trong cùng đoạn code bạn đang nhìn.
5. **Có lazy provider không?** `TaskProvider`, `Provider`, `Property` và `tasks.named` giúp hoãn việc lấy giá trị/cấu hình. Đừng gọi `get()` sớm chỉ để “xem cho chắc”.
6. **Task có thực sự được chọn không?** Xem tên task CLI, `dependsOn` và đồ thị execution. Task được định nghĩa nhưng không được chọn sẽ không chạy action.
7. **Điều gì có thể khiến action bị skip?** Up-to-date state, Build Cache, `onlyIf`, `enabled`, `NO-SOURCE`, `--dry-run` hoặc một điều kiện custom của task.

Trong Groovy DSL:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    doFirst {
        println 'ACTION: test sap chay'
    }
}
~~~

Trong Kotlin DSL:

~~~kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
    doFirst {
        println("ACTION: test sap chay")
    }
}
~~~

**Hai đoạn trên chỉ là snippet cấu hình**, không phải chương trình độc lập: cần áp dụng plugin `java` (hoặc plugin khác tạo task `test`), có kiểu `Test` phù hợp và các dependency kiểm thử cần thiết. `useJUnitPlatform()` cấu hình cách task `test` chạy, còn `println` trong `doFirst` là action. Nếu task `test` được Gradle bỏ qua vì không có test/không cần chạy, dòng action có thể không xuất hiện.

## 10. Gỡ lỗi: chứng minh một dòng chạy khi nào

Khi nghi ngờ code nằm sai pha, dùng quy trình nhỏ, có thể lặp lại:

**Bước 1.** Đặt các dòng thông báo phân biệt rõ chỗ chạy; dùng các tiền tố `CONFIG SCRIPT`, `CONFIG TASK` và `ACTION` như mục 3. Tránh logging ồ ạt trong mọi task của project.

**Bước 2.** Chạy task `help` và task đích, tắt Configuration Cache trong thí nghiệm:

~~~bash
./gradlew -q help --no-configuration-cache
./gradlew -q chao --no-configuration-cache
~~~

**Bước 3.** Thử `--dry-run`. Nếu dòng action không xuất hiện nhưng dòng config vẫn có, điều đó phù hợp với phân chia hai vai trò. Lưu ý plugin có thể log ở nơi khác nên cần nhận diện chính xác dòng của chính mình.

**Bước 4.** Nếu task có output và bị `UP-TO-DATE`/`FROM-CACHE`, kiểm tra log trạng thái:

~~~bash
./gradlew chao --info --console=plain --no-configuration-cache
~~~

Với task thực tế có output, có thể chẩn đoán một lượt bằng `--rerun-tasks --no-build-cache --no-configuration-cache` khi cần xác minh action chạy trong điều kiện input hợp lệ. `--rerun-tasks` bỏ qua kiểm tra up-to-date thông thường; nó không ép action của task disabled, bị skip bằng `onlyIf`, không có source hoặc có lỗi validation.

**Bước 5.** Nếu Configuration Cache được bật trong project thật, chạy lại cùng yêu cầu và quan sát thông báo về reuse của cache. Sự khác biệt trong số lần in `CONFIG` không nhất thiết là lỗi; cần xem cơ chế cache đang có hiệu lực hay không.

**Bước 6.** Nếu dòng `println` đặt ngoài `doLast` làm việc nặng (ghi file/gọi mạng/xử lý dữ liệu) ngay từ pha cấu hình, chuyển logic thực tế sang action của task hoặc custom task type. Đồng thời khai báo inputs/outputs thích hợp và xem lại tương thích Configuration Cache.

### Các lỗi nhận thức thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Viết code bên trong `tasks.register { }` thì code đó chỉ chạy khi gọi task.” | Dòng cấu hình chạy lúc task được realize; **chỉ thân action** mới là công việc execution. |
| “`tasks.register` lập tức tạo và cấu hình toàn bộ task.” | `register` đăng ký lazy; Gradle realize/configure theo nhu cầu. |
| “Có dòng `CONFIG` nghĩa là task đã chạy.” | Task có thể được cấu hình do tra cứu/thiết lập graph dù không được thực thi. |
| “Có `doLast` nghĩa là action luôn chạy mỗi lần gọi Gradle.” | Action có thể bị bỏ qua do task không thuộc graph, skip, up-to-date, cache hit, dry-run... |
| “`--dry-run` bỏ qua toàn bộ Gradle lifecycle.” | Gradle vẫn xác định mô hình và đồ thị task; chỉ không chạy actions. |
| “`--no-build-cache` tắt luôn Configuration Cache.” | Đây là hai cơ chế khác nhau, có hai cờ bật/tắt riêng. |
| “`from`/`into` trong task `Copy` đã thực hiện sao chép.” | Chúng cấu hình nguồn/đích; action của task type mới thực hiện sao chép. |
| “Chỉ cần đưa code vào `doLast` là tối ưu và cache-safe.” | Cần khai báo input/output, tránh truy cập project state lúc execution và tuân thủ quy tắc tương thích. |

## 11. Bài tập tự kiểm tra

**Bài 1 — Phân loại các dòng.** Cho đoạn Kotlin DSL:

~~~kotlin
tasks.register("kiemTra") {
    group = "learning"
    println("A")
    doLast {
        println("B")
    }
}
~~~

Trả lời: `group = ...` và `println("A")` thuộc **cấu hình task**. `println("B")` là **action**. Nếu gọi `./gradlew help` và task `kiemTra` không bị realize, không có A hoặc B; nếu task được realize nhưng không thực thi, có thể có A mà không có B.

**Bài 2 — Chọn lệnh kiểm chứng.** Muốn xem cấu hình chạy ra sao trong khi chắc chắn không thực hiện action của task, dùng lệnh nào? **`./gradlew kiemTra --dry-run --no-configuration-cache`**. Lệnh cho phép quan sát pha lập kế hoạch, song không chạy action.

**Bài 3 — Hai task có dependency.** Task `kiemTra` khai báo `dependsOn("chuanBi")`. Vì sao lúc gọi `kiemTra` lại thấy action của `chuanBi` trước? Bởi vì **task dependency graph** yêu cầu `chuanBi` chạy trước `kiemTra`; quan hệ đó được khai báo trong cấu hình, không có nghĩa khối cấu hình `chuanBi` phải chạy trước mọi mã cấu hình của `kiemTra`.

**Bài 4 — Configuration Cache.** Sau khi chạy task lần hai, không còn thấy dòng `CONFIG SCRIPT` nhưng vẫn thấy `ACTION`. Có hợp lý không? **Có**, nếu Gradle reuse Configuration Cache và task cần chạy action; cần kiểm tra thông báo thực tế để xác nhận.

**Bài 5 — Kiểm tra task loại Copy.** Script chỉ có `from` và `into` trong `tasks.register<Copy>`, không có `doLast`. Task có thể sao chép file không? **Có**; loại task `Copy` có action của riêng nó.

**Bài 6 — Đề xuất sửa.** Một script đọc file lớn và gửi HTTP request trong khối cấu hình task. Cần làm gì? Tách code thực hiện sang task action/custom task type, khai báo input/output khi phù hợp, xem lại API tương thích Configuration Cache. Không làm I/O tốn kém chỉ vì Gradle đang lập kế hoạch build.

## 12. Tài liệu chính thức

- [Gradle Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization, configuration, execution.
- [Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named`, `TaskProvider`, realization và lợi ích của lazy configuration.
- [More About Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html): task actions, `doFirst`, `doLast`, phụ thuộc và mô hình task.
- [Incremental Builds and Build Caching](https://docs.gradle.org/current/userguide/incremental_build.html): input/output, up-to-date và điều kiện chạy.
- [Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): khi nào kết quả task có thể được dùng lại.
- [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): state cấu hình, reuse và yêu cầu tương thích.
- [Developing Custom Gradle Task Types](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): task class, input/output properties và `@TaskAction`.

**Kết quả học tập cần đạt:** đọc được một build script và phân loại đúng phần đăng ký/cấu hình task so với hành động của task; giải thích được vì sao mã cấu hình có thể chạy khi task không chạy; hiểu tác dụng của `tasks.register` và lazy realization; dự đoán được ảnh hưởng của `--dry-run`, up-to-date checks, Build Cache và Configuration Cache; cuối cùng biết đặt I/O và nghiệp vụ ở nơi phù hợp trong custom task.
