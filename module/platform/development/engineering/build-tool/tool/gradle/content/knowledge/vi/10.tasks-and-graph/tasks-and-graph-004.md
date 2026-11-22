# Thêm hành động bằng doFirst, doLast và kiểm soát thứ tự task trong Gradle

## 1. Mục tiêu bài học

Gradle tổ chức công việc thành các **task**. Mỗi task có thể gồm một hay nhiều **action**; Gradle dùng **task graph** để quyết định các task cần chạy và những ràng buộc thứ tự giữa chúng. Hai lớp thứ tự này dễ bị nhầm:

1. **Bên trong một task:** `doFirst { ... }` thêm action vào **đầu** danh sách action; `doLast { ... }` thêm action vào **cuối** danh sách.
2. **Giữa các task:** `dependsOn(...)`, `mustRunAfter(...)`, `shouldRunAfter(...)` và `finalizedBy(...)` mô tả các quan hệ khác nhau trong task graph.

Ví dụ: task `:app:run` có thể cần `:app:classes` chạy trước do dependency graph, và bản thân task `:app:run` lại có action `doFirst`, action chạy Java rồi action `doLast`. Vì vậy **thứ tự task** và **thứ tự action** là hai vấn đề khác nhau.

Sau bài này, bạn sẽ:

- Hiểu cấu trúc task, action, configuration và execution.
- Thêm `doFirst`, `doLast` đúng vị trí, dự đoán được thứ tự output của nhiều action.
- Đăng ký/cấu hình task bằng Kotlin DSL và Groovy DSL, không vô tình thực hiện code trong configuration.
- Chọn đúng quan hệ `dependsOn`, `mustRunAfter`, `shouldRunAfter` hoặc `finalizedBy`.
- Biết lúc nào không thể dự đoán thứ tự giữa các task độc lập.
- Thực hành dự án Java 17 chạy được, xem kết quả và khắc phục lỗi thường gặp.

## 2. Task, task action và task graph là gì?

### 2.1. Task là đơn vị công việc trong Gradle

Một task có **tên**, có thể có **mô tả**, **đầu vào**, **đầu ra**, các **task dependencies**, **ordering rules**, và **danh sách action**. Ví dụ plugin Java cung cấp `compileJava`, `test`, `jar`, `build`; plugin Application bổ sung `run`. Không phải task nào cũng có action: task vòng đời (*lifecycle task*) như `build` thường chủ yếu phụ thuộc vào các task làm việc thật.

Trong `build.gradle.kts`:

~~~kotlin
tasks.register("hello") {
    group = "learning"
    description = "In lời chào"

    doLast {
        println("Hello from Gradle")
    }
}
~~~

Chạy `gradle --quiet hello`, stdout do action tạo ra:

~~~text
Hello from Gradle
~~~

**Điều này không có nghĩa** dòng `println` được chạy ngay khi Gradle đánh giá `build.gradle.kts`. Lời gọi `tasks.register(...)` khai báo task; action trong `doLast` chỉ có cơ hội chạy ở **execution phase** khi task được chọn và không bị bỏ qua.

### 2.2. Một task có thể chứa nhiều action

Ví dụ task làm ba thao tác:

~~~kotlin
tasks.register("threeSteps") {
    doLast { println("Step A") }
    doLast { println("Step B") }
    doLast { println("Step C") }
}
~~~

Lệnh `gradle --quiet threeSteps` in:

~~~text
Step A
Step B
Step C
~~~

Đây là **ba action của cùng một task**, không phải ba task độc lập. Gradle thực thi tuần tự action của một task theo danh sách action; không tự tạo task graph riêng cho từng `doLast`.

### 2.3. Task graph là quan hệ giữa các task

Giả sử:

~~~text
:prepare  --->  :verify  --->  :publish
~~~

Mũi tên ở đây biểu diễn công việc phía sau phụ thuộc công việc phía trước. Khi yêu cầu `:publish`, Gradle phải xét và xử lý `:prepare`, `:verify` trước `:publish` theo quan hệ `dependsOn`. Trong mỗi task, Gradle tiếp tục chạy danh sách action riêng của task đó.

**Nhớ ba kiểu định danh:**

- `publish`: task name trong một project.
- `:publish`: task path tuyệt đối thuộc root project.
- `:app:publish`: task path tuyệt đối thuộc project `:app`; `:app` là project path.

Task path dùng dấu `:`, không phải đường dẫn file. Nhiều project có thể có task cùng tên `test` nhưng path khác nhau, chẳng hạn `:app:test` và `:library:test`.

## 3. Cú pháp và cơ chế chính xác của doFirst, doLast

### 3.1. `doFirst` chèn vào đầu, `doLast` thêm vào cuối

Khi cấu hình task:

~~~kotlin
tasks.register("actionOrder") {
    doLast  { println("last-1") }
    doFirst { println("first-1") }
    doLast  { println("last-2") }
    doFirst { println("first-2") }
}
~~~

Chạy:

~~~bash
gradle --quiet actionOrder
~~~

Stdout chính xác:

~~~text
first-2
first-1
last-1
last-2
~~~

Giải thích từng lần thêm:

| Lời gọi | Danh sách action sau khi thêm |
| --- | --- |
| `doLast { last-1 }` | `last-1` |
| `doFirst { first-1 }` | `first-1 → last-1` |
| `doLast { last-2 }` | `first-1 → last-1 → last-2` |
| `doFirst { first-2 }` | `first-2 → first-1 → last-1 → last-2` |

**Bẫy quan trọng:** Nếu gọi `doFirst` nhiều lần, action được thêm **sau** có thể chạy **trước** action được thêm trước. Nhiều `doLast` thì được nối tiếp theo thứ tự thêm vào. Cơ chế này áp dụng cho **danh sách action của chính một task**.

### 3.2. Có thể thêm action sau khi đăng ký

~~~kotlin
tasks.register("welcome") {
    doLast {
        println("Hello Earth")
    }
}

tasks.named("welcome") {
    doFirst {
        println("Hello Venus")
    }
}

tasks.named("welcome") {
    doLast {
        println("Hello Mars")
    }
}
~~~

Chạy `gradle --quiet welcome`:

~~~text
Hello Venus
Hello Earth
Hello Mars
~~~

`tasks.named("welcome") { ... }` **cấu hình một task đã tồn tại**; nó không tạo task mới. Nếu chưa có task `welcome`, cần `tasks.register("welcome")` hoặc plugin đăng ký task trước.

Việc sử dụng `tasks.register` và `tasks.named` giúp Gradle trì hoãn cấu hình task chưa cần thiết. Đừng dùng `tasks.create` một cách mặc định khi không cần hiện thực hóa task ngay.

### 3.3. Task có action do plugin hoặc task type định nghĩa

Với task của Java/Application plugin, phần công việc cốt lõi (biên dịch, chạy Java, kiểm thử) thường đến từ task type hoặc plugin. Khi bạn thêm:

~~~kotlin
tasks.named("run") {
    doFirst {
        println("Before running the application")
    }
    doLast {
        println("After running the application")
    }
}
~~~

thì `doFirst` được chèn trước những action đã có, còn `doLast` được nối sau những action đó. Nếu project đã áp dụng `application` plugin và cấu hình `mainClass` hợp lệ, task `run` có hành động chạy Java nằm giữa hai phần bổ sung.

Đoạn này **không chạy độc lập** nếu chưa có Application plugin và class main; mục 8 cung cấp một project hoàn chỉnh có thể chạy.

Lưu ý: các plugin cũng có thể thêm nhiều action hoặc cấu hình lại task. Khi nhiều plugin chỉnh sửa cùng một danh sách action, hãy xác minh thứ tự thật bằng ví dụ và tài liệu plugin, thay vì giả định mọi plugin chỉ có đúng một action.

## 4. Configuration code khác execution action

Trong ba giai đoạn initialization, configuration, execution của Gradle:

1. Initialization đọc settings và xác định các project.
2. Configuration áp dụng plugin, đăng ký/cấu hình task và tính quan hệ graph.
3. Execution chạy những task/action được yêu cầu cùng các dependencies.

Hãy xem:

~~~kotlin
println("[CONFIG] build script")

tasks.register("demo") {
    println("[CONFIG TASK] configuring demo")

    doFirst {
        println("[ACTION] first")
    }

    doLast {
        println("[ACTION] last")
    }
}
~~~

Khi chạy `gradle --no-configuration-cache --quiet demo` trong project mới, những dòng do đoạn code tạo ra là:

~~~text
[CONFIG] build script
[CONFIG TASK] configuring demo
[ACTION] first
[ACTION] last
~~~

Hai dòng đầu đến từ **configuration**, hai dòng sau đến từ **execution**. Closure nằm trực tiếp trong `tasks.register { ... }` là logic cấu hình task; closure trong `doFirst`/`doLast` mới tạo action. Với đăng ký task lười, dòng `CONFIG TASK` có thể **không** xuất hiện khi bạn chạy một task không liên quan, bởi vì `demo` không cần được hiện thực hóa.

Nếu bật Configuration Cache và có lần chạy dùng lại trạng thái cấu hình, một số dòng log cấu hình có thể không xuất hiện nữa. Dùng `--no-configuration-cache` để dễ quan sát trong thí nghiệm; không suy ra mỗi lần build thực tế đều đọc lại toàn bộ script từ đầu.

**Không đặt công việc tạo artifact tại top-level của build script** chỉ vì muốn nó “chạy trước”; đó là side effect trong configuration, có thể xảy ra ngay cả khi gọi `gradle help`. Hãy đặt công việc thật vào action của task có input/output phù hợp.

## 5. Bốn cách điều khiển quan hệ task cần phân biệt

| API | Có thêm task liên quan vào graph không? | Ý nghĩa thực tế | Trường hợp điển hình |
| --- | --- | --- | --- |
| `dependsOn(other)` | **Có**, khi task hiện tại được yêu cầu và dependency hợp lệ | Task hiện tại cần task `other` hoàn thành trước | Tạo source rồi mới compile, chuẩn bị artifact rồi publish |
| `mustRunAfter(other)` | **Không** | Nếu cả hai cùng được lên lịch thì task hiện tại **bắt buộc** chạy sau `other` | Ép thứ tự hai task có thể gọi độc lập |
| `shouldRunAfter(other)` | **Không** | Nếu cả hai cùng có mặt thì **ưu tiên** task hiện tại chạy sau `other`; ràng buộc mềm có thể được bỏ qua trong một số tình huống | Gợi ý thứ tự khi không muốn tạo dependency cứng |
| `finalizedBy(other)` | **Có**, khi task hiện tại được lên lịch và finalizer áp dụng | Thêm task dọn dẹp/kết thúc sau task hiện tại, kể cả nhiều trường hợp task chính lỗi | Giải phóng tài nguyên, đóng phiên/tạm dọn dẹp |

Đây là quan hệ **giữa hai task**, không phải vị trí của action trong danh sách action. `doFirst`/`doLast` không tự khiến task khác chạy. Ngược lại, `dependsOn` không tự thêm logging trước/sau từng action của một task.

Các quy tắc `mustRunAfter` và `shouldRunAfter` **chỉ ảnh hưởng thứ tự nếu cả hai task đã được chọn**. Chúng không kéo task còn lại vào graph và không chứng minh rằng output mà một task cần đã được xây dựng.

## 6. `dependsOn`: bảo đảm task tiền đề

### 6.1. Ví dụ tuyến tính có stdout xác định

~~~kotlin
val prepare = tasks.register("prepare") {
    doLast { println("1. prepare") }
}

val verify = tasks.register("verify") {
    dependsOn(prepare)
    doLast { println("2. verify") }
}

tasks.register("deliver") {
    dependsOn(verify)
    doLast { println("3. deliver") }
}
~~~

Lệnh:

~~~bash
gradle --quiet deliver
~~~

Stdout:

~~~text
1. prepare
2. verify
3. deliver
~~~

Vì `deliver → verify → prepare` là các quan hệ `dependsOn`, Gradle sắp xếp **prepare trước verify trước deliver**.

Chạy riêng `gradle --quiet prepare` chỉ chạy task `prepare` và không kéo ngược `verify` hay `deliver` vào graph.

### 6.2. Dùng TaskProvider thay vì hiện thực hóa task sớm

`tasks.register("prepare")` trả về `TaskProvider<Task>`. Dòng `dependsOn(prepare)` dùng provider này trực tiếp; không cần `prepare.get()` chỉ để lấy đối tượng task. Thói quen dùng provider giúp Gradle tránh cấu hình những task chưa cần thiết.

Trong Groovy DSL:

~~~groovy
def prepare = tasks.register('prepare') {
    doLast { println 'prepare' }
}

tasks.register('deliver') {
    dependsOn(prepare)
    doLast { println 'deliver' }
}
~~~

Hai DSL có cùng ý nghĩa. Kotlin dùng `val`, dấu nháy đôi và lời gọi `dependsOn(...)`; Groovy thường dùng `def` và có thể viết ngắn hơn.

### 6.3. Một task phụ thuộc hai task độc lập

~~~kotlin
val compileDocs = tasks.register("compileDocs") {
    doLast { println("Compile docs") }
}

val compileAssets = tasks.register("compileAssets") {
    doLast { println("Compile assets") }
}

tasks.register("assembleSite") {
    dependsOn(compileDocs, compileAssets)
    doLast { println("Assemble site") }
}
~~~

Chạy `gradle --quiet assembleSite` bảo đảm **cả hai compile task đều được xử lý trước `assembleSite`**. Nhưng **không có bảo đảm** `compileDocs` luôn chạy trước `compileAssets`, hoặc ngược lại, vì chúng độc lập. Gradle có thể chọn thứ tự khác tùy graph và tính năng song song.

**Đừng viết test chỉ chấp nhận một thứ tự log của hai nhánh độc lập.** Nếu thực sự cần chúng tuần tự, hãy thêm quan hệ tương ứng, và nếu một task cần kết quả của task kia thì dùng dependency thật.

## 7. `mustRunAfter`: thứ tự bắt buộc, nhưng không tạo dependency

~~~kotlin
val audit = tasks.register("audit") {
    doLast { println("audit") }
}

tasks.register("publish") {
    mustRunAfter(audit)
    doLast { println("publish") }
}
~~~

Chạy **chỉ**:

~~~bash
gradle --quiet publish
~~~

Stdout:

~~~text
publish
~~~

Task `audit` **không chạy**, vì `mustRunAfter(audit)` không tự thêm nó vào graph.

Khi yêu cầu **cả hai**:

~~~bash
gradle --quiet publish audit
~~~

Stdout của hai action là:

~~~text
audit
publish
~~~

Dù tên task `publish` được nêu trước trên command line, ràng buộc `mustRunAfter` đặt `audit` trước `publish` khi cả hai xuất hiện.

Nếu ý định nghiệp vụ là “mỗi lần publish **phải chạy audit**”, hãy dùng:

~~~kotlin
tasks.named("publish") {
    dependsOn(audit)
}
~~~

thay vì chỉ `mustRunAfter`. Sửa này tạo dependency thực sự; ví dụ là **đoạn bổ sung** cho cấu hình ở trên, không nên dùng để chứng minh `mustRunAfter` không kéo task vào graph sau khi đã thêm `dependsOn`.

Một trường hợp hữu ích cho `mustRunAfter` là muốn quản lý thứ tự khi người dùng tự chọn hai task độc lập, nhưng vẫn có thể chạy riêng từng task mà không kéo task còn lại vào.

## 8. `shouldRunAfter`: ưu tiên mềm, không phải cam kết cứng

~~~kotlin
val lint = tasks.register("lint") {
    doLast { println("lint") }
}

tasks.register("inspect") {
    shouldRunAfter(lint)
    doLast { println("inspect") }
}
~~~

Khi cả hai task được yêu cầu, Gradle **cố gắng** cho `lint` trước `inspect`. Nếu chỉ yêu cầu `inspect`, `lint` không tự chạy.

Đặc biệt, `shouldRunAfter` là **soft ordering constraint**. Gradle có thể bỏ qua ràng buộc mềm trong trường hợp nó tạo chu trình hoặc gây bế tắc trong graph; không nên thiết kế thuật toán dựa vào một thứ tự mà `shouldRunAfter` chỉ gợi ý.

So sánh nhanh:

- **Task cần dữ liệu từ task khác:** `dependsOn` hoặc liên kết input/output để Gradle suy ra dependency.
- **Hai task đều sẽ chạy và phải tuân thứ tự:** `mustRunAfter`.
- **Thứ tự chỉ mang tính ưu tiên:** `shouldRunAfter`.
- **Cần chạy tác vụ hậu xử lý/dọn dẹp:** `finalizedBy`.

Một ví dụ **không nên làm** là dùng `shouldRunAfter` để mong file do `lint` tạo đã tồn tại trước `inspect`. Nếu `inspect` đọc file đó, hãy biểu diễn file như một dependency/output rõ ràng và dùng `dependsOn` nếu cần.

## 9. `finalizedBy`: tác vụ kết thúc/dọn dẹp

Trong Gradle, `finalizedBy` tạo quan hệ “task chính có finalizer”. Nó khác với `doLast`:

- `doLast` thêm **action** vào cuối danh sách action của **cùng task**. Nếu một action trước đó thất bại, các action sau trong cùng task có thể không được chạy.
- `finalizedBy` đăng ký **task riêng** để xử lý hậu kỳ. Finalizer thường vẫn được chạy khi task chính thất bại trong quá trình thực thi, miễn Gradle đã lên lịch và còn đủ điều kiện để thực hiện finalizer.

Ví dụ:

~~~kotlin
val cleanup = tasks.register("cleanup") {
    doLast {
        println("[cleanup] release temporary resources")
    }
}

tasks.register("temporaryWork") {
    finalizedBy(cleanup)

    doLast {
        println("[work] temporary operation")
    }
}
~~~

Lệnh:

~~~bash
gradle --quiet temporaryWork
~~~

Stdout:

~~~text
[work] temporary operation
[cleanup] release temporary resources
~~~

Chạy riêng `gradle --quiet cleanup` thì chỉ chạy cleanup. Chạy task không liên quan cũng không tự kích hoạt `temporaryWork` hoặc `cleanup`.

### 9.1. Nếu action chính ném lỗi thì sao?

Ví dụ **minh họa lỗi có chủ đích**, không nên thêm vào dự án production:

~~~kotlin
tasks.register("failingWork") {
    finalizedBy(cleanup)
    doLast {
        println("[work] failing")
        throw GradleException("Simulated failure")
    }
}
~~~

Giả sử `cleanup` được khai báo như ví dụ trên và Gradle đã lên lịch `failingWork`, finalizer `cleanup` thông thường vẫn có cơ hội chạy dù `failingWork` báo lỗi. Build vẫn **thất bại**; finalizer không biến task thất bại thành thành công. Không dự đoán toàn bộ stdout/stderr của lệnh này vì log và stacktrace phụ thuộc Gradle/flags.

**Giới hạn:** `finalizedBy` không bảo đảm “cleanup luôn chạy trong mọi hoàn cảnh”: nếu Gradle không khởi động được, lỗi xảy ra trước khi lập task graph, process bị kill hoặc máy ngắt điện, finalizer không thể thực thi. Với tài nguyên quan trọng, cần thiết kế thêm cơ chế thu hồi an toàn của hệ thống.

### 9.2. Finalizer không phải cách che giấu dependency

`finalizedBy` dùng cho hậu kỳ; không dùng nó để đảm bảo chuẩn bị tài nguyên **trước** task chính. Trường hợp cần chuẩn bị, hãy dùng `dependsOn`; trường hợp muốn dọn dẹp sau, cân nhắc `finalizedBy`.

## 10. Bài thực hành đầy đủ Java 17: task graph và action order

Project sau dùng **Gradle Kotlin DSL** để cấu hình một ứng dụng **Java 17**. Nó chứa task tự tạo, task `run` do Application plugin cung cấp, các quan hệ graph và hai action bao quanh action chạy ứng dụng.

### 10.1. Yêu cầu và cấu trúc

Cần có JDK 17 và bản Gradle tương thích; hoặc Gradle Wrapper của dự án đã được chuẩn bị. Tạo:

~~~text
task-order-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
~~~

Các lệnh dưới đây giả định bạn đứng trong thư mục `task-order-lab`. Nếu dùng wrapper, thay `gradle` bằng `./gradlew` trên macOS/Linux hoặc `gradlew.bat` trên Windows.

### 10.2. settings.gradle.kts

~~~kotlin
rootProject.name = "task-order-lab"
~~~

### 10.3. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.tasks.JavaExec

plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

val prepare = tasks.register("prepare") {
    group = "learning"
    doLast {
        println("[prepare] ready")
    }
}

val verify = tasks.register("verify") {
    group = "learning"
    dependsOn(prepare)
    doLast {
        println("[verify] passed")
    }
}

val audit = tasks.register("audit") {
    group = "learning"
    doLast {
        println("[audit] inspected")
    }
}

tasks.named<JavaExec>("run") {
    dependsOn(verify)
    mustRunAfter(audit)

    doFirst {
        println("[run:doFirst] before JavaExec")
    }

    doLast {
        println("[run:doLast] after JavaExec")
    }
}

tasks.register("actionOrder") {
    group = "learning"

    doLast  { println("last-1") }
    doFirst { println("first-1") }
    doLast  { println("last-2") }
    doFirst { println("first-2") }
}

val cleanup = tasks.register("cleanup") {
    group = "learning"
    doLast {
        println("[cleanup] finished")
    }
}

tasks.register("temporaryWork") {
    group = "learning"
    finalizedBy(cleanup)
    doLast {
        println("[work] temporary")
    }
}
~~~

Cách đọc:

- `application` plugin tạo task `run` kiểu `JavaExec`.
- `prepare`, `verify`, `audit`, `actionOrder`, `cleanup`, `temporaryWork` được đăng ký bằng API lười `tasks.register`.
- `verify` phụ thuộc `prepare`; `run` phụ thuộc `verify` nên có chuỗi `prepare → verify → run`.
- `run.mustRunAfter(audit)` chỉ có tác dụng khi `audit` cũng được chọn. Chạy `run` một mình **không** tự gọi `audit`.
- `doFirst` và `doLast` của `run` bao quanh action chạy Java do plugin/task type cung cấp.
- `actionOrder` độc lập để thử nhiều `doFirst`/`doLast`.
- `temporaryWork.finalizedBy(cleanup)` tạo hậu xử lý riêng.

### 10.4. Main.java chạy được với Java 17

Tệp `src/main/java/demo/Main.java`:

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from Java 17");
    }
}
~~~

Package `demo` và tên class `Main` tạo tên đầy đủ `demo.Main`, đúng với `application.mainClass`. Đây là mã Java độc lập hợp lệ; các task graph được cấu hình trong Kotlin DSL.

### 10.5. Chạy task run và đọc từng dòng

~~~bash
gradle --console=plain --quiet run
~~~

Stdout **do các action của ví dụ và chương trình Java tạo ra**, trong môi trường bình thường không có log phát sinh khác:

~~~text
[prepare] ready
[verify] passed
[run:doFirst] before JavaExec
Hello from Java 17
[run:doLast] after JavaExec
~~~

Tại sao đúng thứ tự?

1. `run` cần `verify`; `verify` cần `prepare`, nên Gradle thực hiện `prepare` rồi `verify`.
2. Task `run` bắt đầu: action `doFirst` được chèn trước action `JavaExec`.
3. Action `JavaExec` khởi chạy `demo.Main` và in `Hello from Java 17`.
4. Nếu chạy thành công, action `doLast` của `run` chạy sau và in thông điệp cuối.
5. `audit` không xuất hiện vì `mustRunAfter` không tự kéo audit vào graph.

Vì action in log của `run` được đặt trước và sau JavaExec, ví dụ không đòi bạn sửa `Main.java` để kiểm tra thứ tự action.

### 10.6. Gọi task verify một mình

~~~bash
gradle --console=plain --quiet verify
~~~

Stdout:

~~~text
[prepare] ready
[verify] passed
~~~

Task `run` không được chọn vì `verify` không phụ thuộc ngược vào `run`. Điều này minh họa sự khác biệt giữa dependency graph và chỉ việc tạo task trong cùng build script.

### 10.7. Thử nhiều doFirst và doLast

~~~bash
gradle --console=plain --quiet actionOrder
~~~

Stdout:

~~~text
first-2
first-1
last-1
last-2
~~~

Bạn có thể đổi thứ tự các lời gọi `doFirst`/`doLast` trong script rồi chạy lại để quan sát: `doFirst` chèn đầu, `doLast` nối cuối **tại thời điểm action được thêm vào**.

### 10.8. Chạy audit riêng và chạy cùng run

~~~bash
gradle --console=plain --quiet audit
~~~

Stdout:

~~~text
[audit] inspected
~~~

Tiếp theo:

~~~bash
gradle --console=plain --quiet run audit
~~~

Khi cả hai task được chọn, **`audit` phải được thực hiện trước `run`** vì `run.mustRunAfter(audit)`. Đồng thời `prepare` trước `verify` và `verify` trước `run`. Tuy vậy, **không có ràng buộc trực tiếp giữa `audit` và `prepare`**, nên không nên tuyên bố một chuỗi stdout hoàn toàn cố định cho cả lệnh này khi Gradle có nhiều lựa chọn sắp xếp hợp lệ.

Nếu cần audit bắt buộc chạy trong mọi lần `run`, thay `mustRunAfter(audit)` bằng `dependsOn(audit)` (hoặc thêm dependency thật phù hợp); lúc đó ngữ nghĩa đã khác: audit trở thành công việc được yêu cầu ngay cả khi CLI chỉ chọn run.

### 10.9. Thử finalizedBy

~~~bash
gradle --console=plain --quiet temporaryWork
~~~

Stdout:

~~~text
[work] temporary
[cleanup] finished
~~~

Task `cleanup` là một task riêng được kích hoạt bởi quan hệ finalizer, không phải một `doLast` của `temporaryWork`.

### 10.10. Xác minh riêng Java khi không có Gradle

Từ thư mục project, dùng JDK 17:

~~~bash
javac -d out src/main/java/demo/Main.java
java -cp out demo.Main
~~~

Stdout chính xác:

~~~text
Hello from Java 17
~~~

Hai lệnh này kiểm tra tính hợp lệ của **mã Java**, nhưng không kiểm tra `build.gradle.kts` hoặc task graph. Muốn kiểm tra Gradle build, vẫn phải chạy các task tương ứng qua Gradle.

## 11. Cú pháp tương đương trong Groovy DSL

Nếu sử dụng `build.gradle` thay vì `build.gradle.kts`, cùng API được viết theo phong cách Groovy. Ví dụ nhỏ độc lập chỉ dùng Gradle, không cần Java plugin:

~~~groovy
def prepare = tasks.register('prepare') {
    doLast {
        println 'Prepare'
    }
}

def audit = tasks.register('audit') {
    doLast {
        println 'Audit'
    }
}

tasks.register('deliver') {
    dependsOn(prepare)
    mustRunAfter(audit)

    doFirst {
        println 'Before deliver'
    }

    doLast {
        println 'Deliver'
    }
}
~~~

Chạy chỉ `gradle --quiet deliver`:

~~~text
Prepare
Before deliver
Deliver
~~~

`Audit` không in vì `mustRunAfter` không đưa audit vào graph. Khi gọi cả `audit` và `deliver`, audit phải chạy trước deliver; `prepare` vẫn phải chạy trước deliver, nhưng hai task `audit` và `prepare` không bị ràng buộc thứ tự với nhau.

Bảng so sánh:

| Mục đích | Kotlin DSL (`build.gradle.kts`) | Groovy DSL (`build.gradle`) |
| --- | --- | --- |
| Đăng ký task | `tasks.register("x") { ... }` | `tasks.register('x') { ... }` |
| Cấu hình task đã có | `tasks.named("x") { ... }` | `tasks.named('x') { ... }` |
| Thêm action đầu | `doFirst { println("A") }` | `doFirst { println 'A' }` |
| Thêm action cuối | `doLast { println("B") }` | `doLast { println 'B' }` |
| Task dependency | `dependsOn(other)` | `dependsOn(other)` |
| Thứ tự cứng | `mustRunAfter(other)` | `mustRunAfter(other)` |
| Thứ tự mềm | `shouldRunAfter(other)` | `shouldRunAfter(other)` |
| Finalizer | `finalizedBy(cleanup)` | `finalizedBy(cleanup)` |

Đừng chép cú pháp Groovy `println 'A'` nguyên xi vào Kotlin DSL; Kotlin yêu cầu `println("A")`. Các quan hệ task có cùng ý nghĩa trong hai DSL dù cách diễn đạt chuỗi/lambda khác nhau.

## 12. Thứ tự không phải lúc nào cũng tuyến tính

### 12.1. Đồ thị DAG và các nhánh song song

Xét:

~~~text
             +--> :compileJava -----+
:prepare ----|                      +--> :assemble
             +--> :processResources +
~~~

Gradle buộc `:prepare` trước những task cần nó và hai nhánh trước `:assemble` nếu graph được khai báo đúng. Nhưng **không nhất thiết** có thứ tự giữa `:compileJava` và `:processResources` khi chúng độc lập.

Gradle xây dựng **directed acyclic graph (DAG)**, không phải danh sách tuần tự dựa trên vị trí xuất hiện trong `build.gradle`. Khi cơ chế parallel execution được hỗ trợ và bật (đặc biệt giữa các project), task độc lập có thể được chạy đồng thời. Khi test output/CI, chỉ nên phụ thuộc các thứ tự được ràng buộc rõ ràng.

### 12.2. Đừng dựa vào thứ tự khai báo trong file

~~~kotlin
tasks.register("first") {
    doLast { println("first") }
}

tasks.register("second") {
    doLast { println("second") }
}
~~~

Chỉ vì `first` được khai báo trước `second` không có nghĩa mọi lệnh build sẽ chạy `first` trước `second`. Cần có một task yêu cầu hoặc phụ thuộc chúng, và nếu cần thứ tự phải khai báo đúng quan hệ.

Tương tự, thứ tự dòng của hai lời gọi `dependsOn(a)` và `dependsOn(b)` **không bảo đảm** a phải trước b. Nó chỉ nói task hiện tại cần cả a và b.

### 12.3. Quan hệ thứ tự không giải quyết vấn đề file chưa sẵn sàng

Ví dụ task `packageArtifact` **đọc file** do `generateArtifact` tạo. Không nên dùng:

~~~kotlin
tasks.named("packageArtifact") {
    mustRunAfter("generateArtifact")
}
~~~

rồi tin rằng `generateArtifact` sẽ luôn chạy trước. Nếu chỉ chọn `packageArtifact`, Gradle sẽ không tự chạy `generateArtifact`. Cần khai báo dependency thật hoặc nối input trực tiếp tới output provider của task sinh file để Gradle có thể suy ra dependency.

### 12.4. Circular dependency

Nếu A phụ thuộc B và B phụ thuộc A:

~~~kotlin
tasks.register("a") {
    dependsOn("b")
}

tasks.register("b") {
    dependsOn("a")
}
~~~

Gradle không thể tạo thứ tự thực thi hợp lệ vì tạo chu trình. Khi yêu cầu một trong hai task, build bị lỗi về circular dependency. Đây là **đoạn minh họa lỗi**; không đưa vào project thực hành thành công ở mục 10.

Với ràng buộc mềm `shouldRunAfter`, Gradle có thể bỏ qua quy tắc để tránh chu trình; nhưng với `dependsOn`, bạn cần sửa mô hình nhiệm vụ.

## 13. Task action có chạy khi task bị skip hay up-to-date không?

**Task được chọn vào graph không đồng nghĩa mọi action đều chạy.** Một số trường hợp:

- `--dry-run`: Gradle tính/lên kế hoạch task nhưng bỏ qua task actions.
- Task được đánh dấu `UP-TO-DATE`: inputs/outputs không đổi, Gradle có thể không chạy action.
- Task được khôi phục từ build cache (`FROM-CACHE`): task action không cần chạy để tạo lại output trong lần này.
- Điều kiện `onlyIf { ... }` trả về false hoặc task bị disabled: Gradle có thể skip task actions.
- Task không có nguồn cần xử lý (`NO-SOURCE`) tùy task type: có thể không chạy phần công việc.
- Khi một action ném lỗi: các action tiếp theo **trong cùng task** thường không được chạy; không nên coi `doLast` như một finally block luôn được thực hiện.

Ví dụ task có điều kiện:

~~~kotlin
tasks.register("optional") {
    onlyIf {
        providers.gradleProperty("runOptional")
            .map { it.equals("true", ignoreCase = true) }
            .orElse(false)
            .get()
    }

    doFirst {
        println("optional: first")
    }

    doLast {
        println("optional: last")
    }
}
~~~

Không có `-PrunOptional=true`, task này sẽ bị bỏ qua, không in hai dòng action. Khi chạy:

~~~bash
gradle -PrunOptional=true --quiet optional
~~~

Stdout:

~~~text
optional: first
optional: last
~~~

Lời gọi `onlyIf` được Gradle dùng để quyết định task có được thực thi hay không; nó khác `doFirst` vì không thêm một action bình thường vào danh sách công việc. Trong build production, nếu logic phức tạp, hãy khai báo inputs rõ và cân nhắc custom task type; tránh gọi API của `Project` trong task action khi sử dụng Configuration Cache.

## 14. doFirst/doLast với task có inputs và outputs

Với ví dụ chỉ in `println`, không có output file nên Gradle thường chạy action mỗi khi task được yêu cầu. Với task tạo artifact, cần khai báo output để Gradle đánh giá up-to-date/cache và dependency đúng cách.

Một task minh họa đơn giản trong `build.gradle.kts`:

~~~kotlin
val outputFile = layout.buildDirectory.file("generated/message.txt")

val generateMessage = tasks.register("generateMessage") {
    outputs.file(outputFile)

    doFirst {
        println("[generate] start")
    }

    doLast {
        val target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText("hello", Charsets.UTF_8)
        println("[generate] wrote message")
    }
}

tasks.register("readMessage") {
    dependsOn(generateMessage)
    inputs.file(outputFile)

    doLast {
        println(outputFile.get().asFile.readText(Charsets.UTF_8))
    }
}
~~~

Giả định đầu ra chưa tồn tại và không có cache được dùng, chạy:

~~~bash
gradle --quiet readMessage
~~~

Stdout:

~~~text
[generate] start
[generate] wrote message
hello
~~~

Tệp `build/generated/message.txt` chứa chính xác chuỗi `hello` (không có newline). Các giải thích:

- `outputs.file(outputFile)` cho Gradle biết task `generateMessage` tạo file nào.
- `dependsOn(generateMessage)` bảo đảm producer được xử lý trước consumer.
- `inputs.file(outputFile)` cho Gradle biết `readMessage` sử dụng file làm input.
- `doFirst` dùng log trước công việc; `doLast` thực hiện tạo file và in log sau.
- Lần chạy sau, `generateMessage` có thể được đánh dấu `UP-TO-DATE` nếu output và trạng thái phù hợp; khi đó hai câu log của task producer có thể **không** xuất hiện. Task consumer trong ví dụ không có output để theo dõi, nên thường vẫn in `hello`.

Ví dụ này dùng cách khai báo đơn giản để thấy quan hệ. Với build logic lâu dài, nên dùng typed task với `@Input`, `@OutputFile`, `@TaskAction` và các Property/Provider phù hợp; có thể nối output của producer sang input của consumer để Gradle tự suy ra task dependency. Không dùng `doFirst` hoặc `doLast` như cách “né” việc khai báo task inputs/outputs.

## 15. doFirst/doLast và @TaskAction khác nhau thế nào?

`doFirst` và `doLast` là **cách gắn action động** lên đối tượng `Task`. Với logic tùy biến có input/output rõ ràng, Gradle còn hỗ trợ tạo **custom task type** với phương thức được chú thích `@TaskAction`.

Ví dụ trong Kotlin DSL:

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class GreetingTask : DefaultTask() {
    @get:Input
    abstract val name: Property<String>

    @TaskAction
    fun greet() {
        println("Hello, " + name.get())
    }
}

tasks.register<GreetingTask>("typedGreeting") {
    name.set("Gradle")

    doFirst {
        println("Before typed action")
    }

    doLast {
        println("After typed action")
    }
}
~~~

Chạy `gradle --quiet typedGreeting`:

~~~text
Before typed action
Hello, Gradle
After typed action
~~~

Trong ví dụ này:

1. `@TaskAction` mô tả công việc chính của task type.
2. `doFirst` bổ sung action trước công việc chính.
3. `doLast` bổ sung action sau công việc chính.
4. `@get:Input` khai báo dữ liệu ảnh hưởng kết quả, giúp Gradle theo dõi input của task.
5. Task này vẫn chỉ in stdout và không khai báo output nên không nên kỳ vọng up-to-date chỉ bởi `name` giữ nguyên.

**Nên chọn gì?** Với task trình diễn hoặc bổ sung log rất ngắn, `doFirst`/`doLast` dễ hiểu. Với công việc sản xuất có nhiều logic, cần test, cache và tái sử dụng, nên tạo custom task type hoặc plugin để định nghĩa rõ action, input, output và hành vi.

Không tự viết lệnh `task.actions.execute(...)` hoặc gọi trực tiếp phương thức task action để ép thứ tự: hãy để Gradle điều phối graph và lifecycle.

## 16. Những điểm cần chú ý trong multi-project build

Trong multi-project build, hai project có thể cùng có task `test` hoặc `jar`. Ví dụ:

~~~text
:
├── :app
└── :library
~~~

Các task path có thể là:

~~~text
:app:compileJava
:app:test
:app:run
:library:compileJava
:library:jar
~~~

Lệnh `gradle :app:run` chọn task của `:app`. Nhưng Gradle vẫn có thể cần các task bên `:library` nếu `:app` sử dụng project dependency của thư viện.

Nếu muốn thêm một log vào task `test` của project `:app`, đặt cấu hình ở `app/build.gradle.kts`:

~~~kotlin
tasks.named("test") {
    doFirst {
        println("Test starts in app")
    }
}
~~~

Đoạn này chỉ hợp lệ khi Java/Testing plugin đã đăng ký task `test` của `:app`. Nó không thay đổi task `:library:test`.

Khi cần điều phối xuyên project, hãy dùng quan hệ task path chính xác hoặc (nếu liên quan tới mã/artifact) khai báo **project dependency** và wiring từ output thay vì tự thêm chuỗi `dependsOn(":library:jar")` không cần thiết vào mọi project. Cấu hình chéo bằng `allprojects { ... }` lớn ở root có thể làm việc cấu hình, cache và bảo trì khó hơn.

Sự tồn tại của project `:library` không có nghĩa `:library:jar` tồn tại: task đó phải do plugin hoặc build script tạo ra. Sự tồn tại của `:app:run` cũng phụ thuộc Application plugin và cấu hình phù hợp.

## 17. Kiểm tra đồ thị task và xử lý lỗi

### 17.1. Các lệnh thường dùng

~~~bash
# Liệt kê task đã có.
gradle tasks --all

# Chọn task nhưng không chạy action.
gradle --dry-run run

# Chạy task với log chi tiết hơn.
gradle --info run

# Xem stacktrace khi lỗi.
gradle --stacktrace run

# Chọn đúng task path trong multi-project build.
gradle :app:run

# Quan sát ví dụ mà không tái dùng Configuration Cache.
gradle --no-configuration-cache --console=plain --quiet actionOrder
~~~

Dùng `./gradlew` hoặc `gradlew.bat` thay cho `gradle` khi dự án đã có Gradle Wrapper. `--dry-run` rất hữu ích để xem task graph dự kiến, nhưng nó **không xác nhận code Java đã biên dịch hoặc test đã chạy**, vì task action không được thực thi.

### 17.2. Chẩn đoán theo biểu hiện

| Biểu hiện | Nguyên nhân phổ biến | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Task 'x' not found` | Task chưa được plugin đăng ký hoặc tên/path sai | `gradle tasks --all`, kiểm tra plugin và `tasks.register("x")` |
| `doLast` không in gì | Task không được yêu cầu, bị skip/up-to-date/cache/dry-run hoặc action trước lỗi | Xem task graph, trạng thái task, log `--info` |
| `doFirst` xuất hiện theo thứ tự ngược | Mỗi lời gọi chèn vào **đầu** action list | Xem thứ tự gọi `doFirst`, cân nhắc gộp action |
| Chạy một task không gọi task khác | Chỉ dùng `mustRunAfter`/`shouldRunAfter` | Nếu task thật sự cần task kia, dùng `dependsOn` |
| Hai task độc lập in log không ổn định | Không có ordering relationship | Không dựa vào thứ tự tình cờ; khai báo quan hệ thực sự |
| `Circular dependency` | A phụ thuộc B, B phụ thuộc A hoặc chain tạo vòng | Thiết kế lại graph thành DAG |
| Cleanup không chạy sau task lỗi | Dùng `doLast` trong cùng task rồi action trước ném lỗi | Cân nhắc `finalizedBy` và cơ chế cleanup dự phòng |
| Task hiện `UP-TO-DATE` | Inputs/outputs không đổi | Đây có thể là tối ưu đúng; không dùng stdout action làm bằng chứng bắt buộc |
| Configuration log xuất hiện nhưng action không | Code cấp cao nhất trong build script được cấu hình | Chuyển công việc thật vào task action |
| Build chạy lâu do task được cấu hình quá nhiều | Dùng API eager hoặc cấu hình chéo rộng | Ưu tiên `register`, `named`, `configureEach` |

### 17.3. Không nên dùng cách nào để ép thứ tự?

- Không dùng `Thread.sleep(...)` để “chờ task khác”: không tạo dependency và dễ gây lỗi race condition.
- Không dựa vào thứ tự dòng trong build script: configuration order không phải execution order.
- Không phụ thuộc vào tên task theo alphabet: Gradle dùng graph.
- Không dùng `mustRunAfter` thay `dependsOn` khi cần output của task khác.
- Không lạm dụng hook dạng `gradle.taskGraph.whenReady { ... }` để vá thứ tự ở phút cuối: có thể tương tác kém với cấu hình lười/Configuration Cache và khó bảo trì. Dùng quan hệ task ngay khi cấu hình.
- Không thêm `doLast` vào lifecycle task `build` để cài đặt công việc không khai báo input/output; việc đó có thể gây side effect khó nhìn thấy.
- Không in thông tin nhạy cảm trong `doFirst`/`doLast` khi debug; log có thể được lưu trong CI.

## 18. Bài tập luyện tập và đáp án

### Bài 1 — Dự đoán thứ tự nhiều action

~~~kotlin
tasks.register("quizA") {
    doLast { println("L1") }
    doFirst { println("F1") }
    doLast { println("L2") }
    doFirst { println("F2") }
}
~~~

Lệnh `gradle --quiet quizA` in gì?

**Đáp án:**

~~~text
F2
F1
L1
L2
~~~

Vì `doFirst` chèn đầu danh sách action, còn `doLast` nối cuối.

### Bài 2 — Đúng lựa chọn quan hệ task?

Task `packageApp` cần file được tạo bởi `generateConfig`. Bạn chỉ viết `packageApp.mustRunAfter(generateConfig)`. Có đủ không?

**Đáp án:** **Không.** Nếu chỉ yêu cầu `packageApp`, `generateConfig` không được tự đưa vào graph. Dùng `dependsOn(generateConfig)` hoặc liên kết output của `generateConfig` làm input của `packageApp` để Gradle hiểu dependency.

### Bài 3 — Task độc lập

~~~kotlin
val a = tasks.register("a") {
    doLast { println("A") }
}
val b = tasks.register("b") {
    doLast { println("B") }
}
tasks.register("allWork") {
    dependsOn(a, b)
    doLast { println("ALL") }
}
~~~

Chạy `allWork`. Có chắc output là `A` rồi `B` rồi `ALL`?

**Đáp án:** Không. `ALL` phải sau cả A và B, nhưng giữa A và B không có ràng buộc thứ tự. Nếu chỉ muốn gợi ý thì dùng `shouldRunAfter`; nếu cần bắt buộc thì `mustRunAfter`; nếu B thật sự cần kết quả A thì dùng `dependsOn(a)` ở B.

### Bài 4 — mustRunAfter có kích hoạt task không?

~~~kotlin
val audit = tasks.register("audit") {
    doLast { println("AUDIT") }
}
tasks.register("deploy") {
    mustRunAfter(audit)
    doLast { println("DEPLOY") }
}
~~~

Chạy chỉ `gradle --quiet deploy`, có in `AUDIT` không?

**Đáp án:** Không. Chỉ `DEPLOY`; `mustRunAfter` không đưa audit vào graph. Nếu muốn mỗi lần deploy đều cần audit, thêm dependency thật.

### Bài 5 — Dùng finalizer cho cleanup

Task `testService` mở tài nguyên tạm, phải cố gắng dọn sau khi task chạy dù test fail. Nên dùng `doLast` trong cùng task hay `finalizedBy(cleanup)`?

**Đáp án:** **`finalizedBy(cleanup)`** hợp mục đích hơn vì cleanup là task riêng được Gradle lên lịch hậu kỳ, có thể chạy ngay cả khi action của task chính thất bại. Không nên coi nó là bảo đảm trước các lỗi ngoài quy trình Gradle như process kill.

### Bài 6 — Configuration hay execution?

~~~kotlin
println("A")

tasks.register("quizF") {
    println("B")
    doFirst { println("C") }
    doLast { println("D") }
}
~~~

Khi chạy `gradle --no-configuration-cache --quiet quizF`, thứ tự là gì?

**Đáp án:** `A`, `B`, `C`, `D`. A là script configuration, B là task configuration khi task được hiện thực hóa, C và D là task actions. Nếu chỉ chạy task không liên quan, B có thể không xuất hiện và C, D không chạy.

### Bài 7 — Bỏ qua task

Task có `onlyIf { false }` và cả `doFirst` lẫn `doLast` in log. Task được yêu cầu thì hai action có in không?

**Đáp án:** Không, vì task bị skip trước khi thực hiện action. Trong build thật còn có nhiều nguyên nhân tương tự như `UP-TO-DATE` hoặc `FROM-CACHE` khiến action không chạy.

### Bài 8 — Nhận biết task path

Có root project `:` và subproject `:app`. Muốn chạy task `deploy` chỉ ở `:app`, nên gọi gì?

**Đáp án:** `gradle :app:deploy`, giả sử task được đăng ký trong project `:app`. Không nhầm `:app:deploy` với đường dẫn thư mục hay project path của một project con `deploy`.

## 19. Tờ ghi nhớ nhanh

| Bạn muốn... | API phù hợp |
| --- | --- |
| Thêm action vào **đầu** một task | `doFirst { ... }` |
| Thêm action vào **cuối** một task | `doLast { ... }` |
| Khai báo một task theo cách lười | `tasks.register("x") { ... }` |
| Cấu hình task hiện có theo cách lười | `tasks.named("x") { ... }` |
| Đảm bảo B được chọn và chạy trước A khi A cần B | `A.dependsOn(B)` |
| Cho A sau B **nếu cả hai đều được chọn** | `A.mustRunAfter(B)` |
| Ưu tiên A sau B, không bảo đảm cứng | `A.shouldRunAfter(B)` |
| Thêm task cleanup sau A | `A.finalizedBy(cleanup)` |
| Mô tả công việc chính trong custom task type | `@TaskAction` |
| Cho Gradle theo dõi đầu vào/đầu ra | `@Input`, `@OutputFile` hoặc `inputs`/`outputs` |
| Xem kế hoạch task mà không chạy action | `gradle --dry-run <task>` |
| Chạy task của subproject cụ thể | `gradle :project:task` |

**Kết luận:** `doFirst`/`doLast` là **thứ tự action trong một task**; `dependsOn`/`mustRunAfter`/`shouldRunAfter`/`finalizedBy` là **quan hệ giữa các task**. Chỉ `dependsOn` (hoặc dependency suy ra từ input/output) bảo đảm task tiền đề được đưa vào graph khi task hiện tại cần kết quả. Để build rõ ràng và ổn định, hãy khai báo quan hệ đúng ngữ nghĩa, giữ các task độc lập khi có thể, khai báo input/output và tránh dựa vào thứ tự log tình cờ.

## Tài liệu chính thức

- [Gradle — Creating and Registering Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html) — task action, `doFirst`, `doLast` và cấu hình task.
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html) — `dependsOn`, `mustRunAfter`, `shouldRunAfter`, `finalizedBy`, skipping.
- [Gradle — Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html) — TaskProvider và quan hệ task mạnh/yếu.
- [Gradle — Task API](https://docs.gradle.org/current/javadoc/org/gradle/api/Task.html) — danh sách action và các phương thức quản lý task.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html) — `@TaskAction`, inputs và outputs.
