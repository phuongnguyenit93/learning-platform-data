# Tác dụng phụ trong giai đoạn cấu hình và cách loại bỏ trong Gradle

## 1. Mục tiêu bài học

Gradle xử lý một build theo ba giai đoạn chính: **khởi tạo (initialization)**, **cấu hình (configuration)** và **thực thi (execution)**. Một lỗi thiết kế phổ biến là đặt công việc có tác dụng bên ngoài (ghi tệp, gửi yêu cầu HTTP, gọi chương trình hệ điều hành, xóa thư mục, thay đổi dữ liệu...) ngay trong mã cấu hình. Kết quả là công việc ấy có thể chạy ngay cả khi người dùng chỉ muốn xem trợ giúp hoặc liệt kê task, đồng thời hành vi thay đổi khó lường khi bật **Configuration Cache**.

Sau bài này, bạn cần:

- Xác định dòng mã nào thuộc configuration và dòng nào thuộc execution, kể cả khi dùng `tasks.register`.
- Phân biệt thay đổi mô hình Gradle **đúng chức năng cấu hình** với **tác dụng phụ không nên xảy ra trong cấu hình**.
- Tìm và di chuyển các tác dụng phụ sang **task action** có input/output khai báo rõ.
- Dùng `Provider` và `Property` để trì hoãn đọc giá trị; hiểu trường hợp đọc tệp/biến môi trường ở configuration vẫn được Gradle theo dõi nhưng không có lợi về hiệu năng.
- Kiểm chứng bằng `help`, `tasks`, `--dry-run`, `--configuration-cache`, kết quả task `UP-TO-DATE` và output file thực tế.

Tất cả ví dụ chính dùng **Gradle Kotlin DSL** (`build.gradle.kts`) và Gradle Wrapper. Các lệnh có dạng `./gradlew ...` dành cho Linux/macOS; trên Windows PowerShell dùng `.\gradlew.bat ...` với các tham số tương tự.

## 2. Ba giai đoạn: mã nào được phép làm gì?

| Giai đoạn | Gradle thực hiện | Ví dụ hoạt động hợp lý |
| --- | --- | --- |
| **Initialization** | Đọc `settings.gradle(.kts)`, xác định các project của build và tạo mô hình project. | `include("app", "lib")`, đặt `rootProject.name`. |
| **Configuration** | Áp dụng plugin, đánh giá build script, đăng ký/cấu hình task, thiết lập dependency và thuộc tính, tính task graph. | `tasks.register("generate")`, `tasks.named("test") { ... }`, kết nối input/output bằng provider, khai báo `dependsOn`. |
| **Execution** | Thực thi các task được chọn và các dependency cần thiết; task có thể bỏ qua action nếu `UP-TO-DATE`, `FROM-CACHE` hoặc `SKIPPED`. | Biên dịch Java, chạy test, sinh báo cáo, viết output, gọi công cụ ngoài thông qua task. |

**Cấu hình không có nghĩa là “không làm gì”**: Gradle cần tạo và thay đổi **mô hình build** để quyết định việc phải chạy. Đăng ký task, thêm dependency và đặt giá trị input là công việc cấu hình bình thường. Tác dụng phụ đáng loại bỏ ở đây là **hành động có tác động quan sát được ngoài mô hình build**, không thuộc trách nhiệm quyết định task graph: sửa file, ghi database, gọi API, gửi email, thực thi lệnh triển khai, tạo artifact thực tế hoặc gọi service từ build script.

Những tác động này nguy hiểm vì **configuration có thể chạy trước nhiều lệnh, bất kể task đích có sử dụng kết quả ấy hay không**. Chẳng hạn, `./gradlew help` không yêu cầu build application, nhưng vẫn cần chuẩn bị cấu hình (trừ khi được Configuration Cache tái sử dụng).

## 3. Thực hành nhận biết configuration và execution

Tạo hoặc dùng một dự án Gradle có Wrapper. Nếu mới tạo dự án, `settings.gradle.kts` có nội dung:

~~~kotlin
rootProject.name = "lifecycle-side-effects"
~~~

Trong `build.gradle.kts`, chỉ đặt mã sau:

~~~kotlin
println("CONFIG: đánh giá build script")

tasks.register("demo") {
    println("CONFIG: cấu hình task demo")

    doLast {
        println("EXEC: chạy task demo")
    }
}

tasks.register("other") {
    doLast {
        println("EXEC: chạy task other")
    }
}
~~~

Thử từ thư mục gốc của dự án:

~~~bash
./gradlew -q demo --no-configuration-cache
~~~

Phần stdout do **chính đoạn build logic ở trên** tạo ra, trong một build thông thường không có plugin/init script in thêm thông báo:

~~~text
CONFIG: đánh giá build script
CONFIG: cấu hình task demo
EXEC: chạy task demo
~~~

Giải thích:

1. `println` ở cấp cao nhất của `build.gradle.kts` chạy khi build script được đánh giá trong configuration.
2. `tasks.register("demo") { ... }` **đăng ký task theo cách lazy**. Khối cấu hình của task chạy khi Gradle cần hiện thực/cấu hình task đó; trong ví dụ yêu cầu `demo` nên có dòng `CONFIG: cấu hình task demo`. Việc đặt `println` trong `tasks.register { ... }` **không** biến nó thành task action.
3. `doLast { ... }` thêm một **task action**. Nội dung bên trong chạy ở execution nếu task được lên lịch và không bị skip.
4. Task `other` không được chọn nên action `EXEC: chạy task other` không chạy.

Bây giờ gọi:

~~~bash
./gradlew -q help --no-configuration-cache
~~~

Dòng `CONFIG: đánh giá build script` vẫn xuất hiện khi project được cấu hình; action của `demo` và `other` không chạy. Việc khối cấu hình lazy của `demo` có được thực hiện hay không phụ thuộc Gradle/task nào khiến task đó được hiện thực; **không dựa vào log của khối `tasks.register` để khẳng định đó là execution**.

Thử hai lần lệnh:

~~~bash
./gradlew -q demo --configuration-cache
./gradlew -q demo --configuration-cache
~~~

Lần đầu (cache miss) Gradle cấu hình và lưu kết quả nếu build tương thích. Ở lần sau, **nếu Configuration Cache hit**, Gradle có thể bỏ qua configuration: các dòng `CONFIG...` không lặp lại, nhưng action `EXEC: chạy task demo` vẫn chạy vì task demo không khai báo output để được đánh dấu up-to-date. Nếu có thay đổi input cấu hình hoặc cache không thể tái sử dụng, các dòng cấu hình có thể xuất hiện lại. **Đừng dùng `println` trong configuration như tín hiệu bắt buộc phải phát ra ở mỗi lần chạy.**

## 4. Anti-pattern: ghi file ngay khi cấu hình

Ví dụ sau là **mã có vấn đề**, chỉ dùng để quan sát:

~~~kotlin
// build.gradle.kts — ví dụ sai mục đích
val marker = layout.buildDirectory.file("generated/marker.txt").get().asFile
marker.parentFile.mkdirs()
marker.writeText("Hello Gradle\n", Charsets.UTF_8)

tasks.register("demo") {
    doLast {
        println("Demo action")
    }
}
~~~

Điều gì xảy ra?

- Dòng `marker.writeText(...)` chạy khi Gradle **đánh giá build script**, trước khi xác định task `demo` có cần chạy hay không.
- `./gradlew help` hoặc `./gradlew tasks` (trong lần cần configuration) vẫn có thể tạo/ghi đè `build/generated/marker.txt` dù không yêu cầu sinh file.
- `./gradlew demo --dry-run` bỏ qua task actions nhưng **vẫn có thể ghi file**, vì ghi file nằm trong configuration.
- File được ghi **không phải output đã khai báo của một task**: Gradle không có thông tin input/output để kiểm tra `UP-TO-DATE`, cache kết quả, xây dựng thứ tự dependency hoặc quản lý việc tạo file đúng lúc.
- Khi Configuration Cache hit, Gradle có thể **không chạy lại** khối ghi file. Nếu tệp bị xóa nhưng task graph vẫn được tái sử dụng, cấu hình không bảo đảm tạo lại tệp. Hành vi giữa cache hit và miss sẽ khác nhau.

Đây là lỗi **sai giai đoạn thực thi**, không chỉ là vấn đề tốc độ. Đơn giản đặt đoạn ghi file trong `afterEvaluate { ... }`, `tasks.configureEach { ... }` hay một plugin callback vẫn chưa chuyển nó sang execution; đó chỉ là các thời điểm khác trong **configuration**.

## 5. Sửa đúng: chuyển việc ghi file sang task có input/output

Thay **toàn bộ ví dụ sai ở mục 4** bằng đoạn Kotlin DSL độc lập dưới đây trong `build.gradle.kts`. Ví dụ định nghĩa một task riêng, khai báo chính xác dữ liệu đầu vào và tệp đầu ra:

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

@CacheableTask
abstract class WriteMarker : DefaultTask() {

    @get:Input
    abstract val message: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun write() {
        val target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText(message.get() + "\n", Charsets.UTF_8)
        println("GENERATED: " + target.name)
    }
}

tasks.register<WriteMarker>("writeMarker") {
    message.set(providers.gradleProperty("message").orElse("Hello Gradle"))
    outputFile.set(layout.buildDirectory.file("generated/marker.txt"))
}
~~~

Vai trò từng phần:

- `tasks.register<WriteMarker>(...)` đăng ký task theo cách lazy; chỉ cấu hình đường dẫn và kết nối provider, **không tạo file**.
- `Property<String>` là input mang giá trị; `RegularFileProperty` là tham chiếu tới file output. Các giá trị được set ở configuration, nhưng việc ghi file chờ tới action.
- `@Input` và `@OutputFile` khai báo dữ liệu đầu vào/đầu ra để Gradle biết khi nào phải chạy lại task.
- `@TaskAction` đánh dấu mã chạy ở execution. Không truy cập trực tiếp `Project`, `Gradle` hoặc `Settings` trong action, giúp tương thích Configuration Cache.
- `@CacheableTask` cho phép task đủ điều kiện sử dụng Gradle Build Cache khi đáp ứng các điều kiện khác; **không** khiến task chạy trong configuration. Output được tạo ổn định theo input.
- `providers.gradleProperty("message").orElse("Hello Gradle")` lấy giá trị từ Gradle property theo mô hình provider; không cần tự gọi `System.getenv` hoặc đọc thủ công các file cấu hình trong lúc tạo task.

Kiểm thử:

~~~bash
# Chỉ cấu hình và hiển thị thông tin; không được tạo marker.txt
./gradlew help --no-configuration-cache

# Chạy task thực sự
./gradlew -q writeMarker --no-configuration-cache

# Chạy lại với cùng input: Gradle có thể xác định UP-TO-DATE
./gradlew writeMarker --no-configuration-cache

# Thay đổi input, buộc task tính lại output
./gradlew -q writeMarker -Pmessage="Hello Team" --no-configuration-cache
~~~

Lần đầu task action chạy, đoạn `println` của action in:

~~~text
GENERATED: marker.txt
~~~

Và file `build/generated/marker.txt` chứa nguyên văn:

~~~text
Hello Gradle
~~~

Sau lệnh truyền `-Pmessage="Hello Team"`, file chứa `Hello Team` cùng một ký tự xuống dòng. Trên lần chạy không có thay đổi input/output, Gradle có thể đánh dấu task `UP-TO-DATE` và **không in** `GENERATED: marker.txt` vì action không được gọi. Nếu bật Build Cache và có entry phù hợp, Gradle cũng có thể khôi phục output với trạng thái `FROM-CACHE` mà không chạy action.

**Điều kiện thực hành:** làm sạch tệp `build/generated/marker.txt` còn sót từ ví dụ sai trước khi kiểm tra `./gradlew help`; ví dụ dùng một dự án mới hoặc xóa riêng tệp thử nghiệm đó. Không xóa dữ liệu thực của dự án. Nội dung hiển thị ngoài log của action (ví dụ thông tin Gradle) có thể thay đổi tùy phiên bản.

### Dạng ngắn cho tác vụ đơn giản

Nếu một công việc rất nhỏ và không cần một class riêng, có thể dùng `doLast`. Ví dụ sau là **phương án thay thế độc lập**, không đặt đồng thời cùng task `writeMarker` với class ở trên:

~~~kotlin
tasks.register("writeMarker") {
    val targetFile = layout.buildDirectory.file("generated/marker.txt")

    inputs.property("message", "Hello Gradle")
    outputs.file(targetFile)

    doLast {
        val target = targetFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText("Hello Gradle\n", Charsets.UTF_8)
    }
}
~~~

Tác vụ này khai báo input và output, và ghi file tại execution. Tuy nhiên, khi logic trở nên phức tạp, **custom task type + `@TaskAction` + các typed properties** giúp xác định rõ vòng đời, giảm khả năng vô ý capture mô hình Project trong action và dễ tái sử dụng/test hơn. Không gọi `project.file(...)` hoặc tham chiếu `project` trong `doLast` khi hướng đến Configuration Cache; hãy tính/cấp provider tại configuration và chỉ sử dụng dữ liệu task hợp lệ trong action.

## 6. Những tác dụng phụ thường gặp và cách thay thế

| Dấu hiệu trong build logic | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| `File.writeText`, `mkdirs`, `copy`, xóa thư mục ở cấp top-level hoặc trong callback cấu hình | Viết/xóa file ngay cả với `help`/`tasks`, đầu ra không được theo dõi. | Chuyển sang `@TaskAction`, `Copy`, `Sync`, `Delete` task phù hợp; khai báo input/output cho task tạo artifact. |
| Gọi process bằng `ProcessBuilder`, `Runtime.exec` khi cấu hình | Công cụ ngoài được kích hoạt cho cả lệnh không liên quan; kết quả có thể khó tái tạo. | Dùng task `Exec`/`JavaExec` nếu mục đích chính là chạy process, hoặc một task type cụ thể; quản lý tham số, dữ liệu và output. |
| Gọi API/network hoặc cập nhật database lúc áp dụng plugin hay đánh giá build script | Side effect có thể xảy ra nhiều lần, hoặc không xảy ra khi Configuration Cache hit. | Đưa thao tác triển khai/tải dữ liệu chủ động vào task chạy theo yêu cầu; không tự phát thực thi khi cấu hình. |
| `println`, ghi log, gửi metric trong configuration mà kỳ vọng mỗi build đều phát sự kiện | Log/metric biến mất khi cache hit và không phản ánh việc task chạy. | Log tại task action nếu liên quan việc chạy task; với quan sát toàn build cần cơ chế lifecycle tương thích Configuration Cache. |
| `System.getenv(...)`, `System.getProperty(...)`, `file(...).readText()` được gọi dày đặc tại configuration | Có thể tăng thời gian cấu hình và khiến cache bị vô hiệu hóa khi input thường xuyên đổi. | Ưu tiên `Provider` và truyền giá trị vào task input; chỉ đánh giá ở configuration khi giá trị thực sự quyết định task graph. |
| Tính git commit bằng chạy `git` tại configuration cho mọi lệnh | Tốn process, có thể đổi giữa các lần, tăng input fingerprint. | Nếu commit chỉ cần để tạo artifact, truyền vào task qua provider hoặc ValueSource phù hợp; cân nhắc `providers.exec` khi output process thật sự là configuration input. |
| `tasks.create`, hiện thực mọi task bằng `getByName`, các callback `all { ... }` chạy công việc nặng | Eager configuration, làm nhiều việc cho task không chạy. | Ưu tiên `tasks.register`, `tasks.named`, `configureEach`; **khối cấu hình trong các API này vẫn là configuration** nên chỉ thiết lập model. |
| Đọc/ghi một thư mục chung từ nhiều task không khai báo quan hệ | Tác vụ tranh chấp output, nondeterministic, đặc biệt khi chạy song song. | Mỗi task có output riêng; nối producer–consumer bằng provider/`dependsOn` thích hợp; dùng Build Service để điều phối tài nguyên chia sẻ khi cần. |

Không phải **mọi** hoạt động I/O trong configuration đều bị cấm. Chẳng hạn, Gradle có thể theo dõi trực tiếp việc đọc file, biến môi trường, system property hoặc kiểm tra sự tồn tại của file khi cấu hình và ghi chúng như **configuration inputs** để vô hiệu hóa Configuration Cache đúng lúc. Vấn đề cần đánh giá là: **có phải thực sự cần giá trị đó để quyết định cấu hình không**, hay chỉ cần khi một task thực thi? Nếu chỉ task dùng, nên đưa việc đọc vào task để thay đổi input không làm cấu hình cả build bị tính lại.

Một ví dụ ngoại lệ hợp lệ: giá trị có thể phải được lấy sớm để quyết định plugin, project hoặc task graph. Khi đó không “chuyển hết sang `doLast`” một cách máy móc; hãy dùng cách cung cấp **configuration input có thể theo dõi** (chẳng hạn `ProviderFactory`/`ValueSource` phù hợp) và giữ bước cấu hình thuần túy.

## 7. Lazy configuration không tự động xóa side effect

Nhiều người nhầm `tasks.register` với “bên trong khối chỉ chạy tại execution”. Đây là hai đoạn hoàn toàn khác nhau:

~~~kotlin
tasks.register("example") {
    // Đây là task configuration, chạy khi task được hiện thực.
    println("CONFIGURE example")

    doLast {
        // Đây mới là task action, chạy trong execution khi cần.
        println("EXECUTE example")
    }
}
~~~

`tasks.register` làm **lười thời điểm hiện thực task**, nhưng vẫn tạo **khối cấu hình**. Nếu trong khối `tasks.register { ... }` gọi database, ghi file hoặc gọi process, đó vẫn là tác dụng phụ khi **task được cấu hình**, không phải task action. Lệnh `./gradlew :example --dry-run` có thể kích hoạt khối cấu hình để lập graph, dù bỏ qua mọi `doLast`.

Tương tự, các cơ chế `afterEvaluate` và callback cấu hình không phải phương án sửa tác dụng phụ. Di chuyển một lệnh viết file từ top-level sang `afterEvaluate` chỉ trì hoãn nó đến một thời điểm muộn hơn trong configuration. Nếu muốn tạo artifact, hãy lập một task với output thực sự; nếu cần dữ liệu trong configuration, hãy cung cấp dữ liệu một cách có kiểm soát và tránh ghi output từ đó.

### Không thay thế dữ liệu task bằng trạng thái toàn cục

Một anti-pattern khác là đặt biến mutable bên ngoài task rồi để nhiều task đọc/ghi biến đó:

~~~kotlin
// Minh họa lỗi thiết kế: chia sẻ mutable state giữa các task
var generatedName = "default"

tasks.register("setName") {
    doLast { generatedName = "custom" }
}

tasks.register("useName") {
    doLast { println(generatedName) }
}
~~~

Task graph không được khai báo phụ thuộc `useName` vào `setName`; thứ tự hành động không đảm bảo, và mutable state trong build script gây khó cho Configuration Cache/task isolation. Với dữ liệu được tạo ra bởi một task, tốt hơn là xuất ra **tệp có `@OutputFile`** rồi để task tiêu thụ khai báo **`@InputFile`** và phụ thuộc vào output provider. Nếu thực sự cần dùng tài nguyên dùng chung (như pool kết nối hoặc giới hạn tác vụ đồng thời), nghiên cứu **Shared Build Services**, không dựa vào biến mutable trong script.

## 8. Đọc file, biến môi trường và Provider API đúng thời điểm

**Đọc file ngay khi cấu hình:**

~~~kotlin
// Nếu config.txt thường xuyên đổi, lần đọc này trở thành configuration input.
val text = layout.projectDirectory.file("config.txt").asFile.readText()
~~~

Đọc trực tiếp này **có thể được Gradle theo dõi** khi Configuration Cache hoạt động; không nên mô tả nó là hành vi luôn sai hoặc luôn không tương thích. Tuy nhiên, nếu thay đổi nội dung tệp chỉ ảnh hưởng một task, thực hiện việc đọc khi task chạy với `@InputFile` giúp thay đổi đó chỉ ảnh hưởng task liên quan, thay vì buộc cấu hình của toàn build bị đánh giá lại.

**Lấy provider thay vì lập tức truy xuất giá trị:**

~~~kotlin
val configText = providers.fileContents(
    layout.projectDirectory.file("config.txt")
).asText

val buildLabel = providers.gradleProperty("label").orElse("local")
val buildId = providers.environmentVariable("BUILD_ID")
~~~

Các dòng này mô tả nguồn dữ liệu mà chưa chủ động gọi `get()` ở cấp top-level. Truyền provider cho `Property`/`RegularFileProperty` hoặc task input của task cần dữ liệu. Nếu viết `configText.get()` hoặc `buildId.get()` ngay trong configuration, việc đọc vẫn xảy ra sớm và có thể trở thành configuration input. Với Configuration Cache, một số chuỗi provider cũng có thể được Gradle tính trước khi lưu task graph; vì vậy **deferred API không có nghĩa mọi phép tính chắc chắn chỉ xảy ra trong action**. Hãy kiểm tra theo loại provider, nơi giá trị được truy cập và bài toán thực tế.

Nguyên tắc chọn API:

- Dữ liệu là **đầu vào cho một task tạo output**: ưu tiên `@InputFile`/`@Input` và đọc từ `@TaskAction`; task cache/up-to-date có thể xác định chính xác.
- Dữ liệu **quyết định cách cấu hình build**: dùng provider/`ValueSource` hoặc cơ chế Gradle hỗ trợ và cho phép Gradle theo dõi như configuration input.
- Bí mật (token/password): không in ra log và không đưa vào file đã commit. Tùy mục đích, dùng Gradle credentials API hoặc provider từ Gradle property/environment; chú ý rằng giá trị được truy xuất lúc cấu hình có thể tham gia fingerprint/cache state. 
- Không gọi `get()` sớm chỉ để “kiểm tra cho chắc”; thay vào đó, gắn provider vào thuộc tính của task và để Gradle quản lý thời điểm truy xuất khi có thể.

## 9. Phân biệt Configuration Cache, Build Cache và tính đúng đắn

| Cơ chế | Lưu cái gì? | Tác dụng phụ trong configuration gây vấn đề gì? |
| --- | --- | --- |
| **Configuration Cache** | Kết quả cấu hình (task graph/trạng thái task và các dependency cấu hình) để bỏ qua cấu hình khi input cấu hình chưa đổi. | Hành động tạo file/gọi API ở configuration **không chạy trên cache hit**; dựa vào nó là không đáng tin. |
| **Build Cache** | Output của task có khai báo đầu vào, đầu ra và đủ điều kiện cache. | File được ghi ở configuration không phải output do task quản lý nên không được cache đúng cách. |
| **Up-to-date checks** | So sánh input/output của task với lần chạy trước. | Không thể suy ra chính xác việc có cần sinh lại file nếu code tạo file nằm ngoài action/task model. |

Ví dụ: nếu build script viết `build/generated/marker.txt` mỗi lần configuration, rồi task compile dùng file đó mà không khai báo phụ thuộc, cache và up-to-date checks có thể thấy nguồn đầu vào không nhất quán. Nếu bỏ đoạn ghi file khỏi configuration và giao cho task `writeMarker` có `@Input`/`@OutputFile`, Gradle có đủ thông tin để lên lịch task, kiểm tra thay đổi và dùng cache.

**Quan trọng:** bật Configuration Cache không tự động sửa tác dụng phụ. Nó chỉ khiến sự khác biệt giữa cache miss và cache hit dễ bộc lộ hơn. Một build đúng phải không dựa vào side effect của configuration để hoàn thành task execution.

Cũng cần phân biệt hai cách tránh việc chạy:

- `--dry-run` tạo task graph và bỏ qua **task actions**; configuration có thể vẫn được chạy, vì vậy không bảo vệ khỏi side effect đặt ở configuration.
- `--no-configuration-cache` buộc chạy configuration thay vì tái sử dụng cache; dùng cho thí nghiệm tái lập sự cố, **không phải sửa thiết kế**. `--rerun-tasks` yêu cầu thực thi lại task actions (thay vì dùng trạng thái up-to-date), nhưng không đồng nghĩa buộc Configuration Cache miss.

## 10. Quy trình dò và loại bỏ tác dụng phụ

Thực hiện theo thứ tự sau trên một nhánh hoặc thư mục thử nghiệm phù hợp; với task có ảnh hưởng bên ngoài, không chạy thử trên môi trường production khi chưa hiểu tác động của nó.

1. **Xác định dấu hiệu:** file bị ghi khi gọi `help`; lệnh triển khai chạy khi gọi `tasks`; build chậm trước khi task thực thi; log cấu hình biến mất ở lần build thứ hai; kết quả khác nhau giữa cache hit và miss.
2. **Tìm nơi phát sinh:** rà soát cấp top-level trong `settings.gradle(.kts)`/`build.gradle(.kts)`, mã plugin, `buildSrc`/included build logic, `tasks.register { }`/`configureEach { }`/`afterEvaluate { }`. Tìm các lời gọi I/O, process, network, mutable state và `get()` trên provider.
3. **Phân loại:** thao tác này cần **quyết định mô hình cấu hình** hay tạo **artifact/tác động tại lúc thực thi**? Nếu loại thứ hai, chuyển vào task action.
4. **Thiết kế task:** chọn task built-in (`Copy`, `Sync`, `Delete`, `Exec`, `JavaExec`) hoặc custom task type. Khai báo `@Input`, `@InputFile`, `@OutputFile`, `@OutputDirectory` đúng theo hành vi; file output nên nằm trong `layout.buildDirectory`.
5. **Nối dependency:** task cần kết quả phải sử dụng provider output của task tạo dữ liệu, hoặc khai báo `dependsOn` tường minh. Không trông chờ thứ tự ngẫu nhiên hoặc side effect từ bước cấu hình.
6. **Kiểm thử nhiệm vụ không liên quan:** gọi `./gradlew help --no-configuration-cache` và `./gradlew tasks --no-configuration-cache`, xác nhận artifact/task action ngoài dự kiến **không** xảy ra.
7. **Kiểm thử task thực sự:** chạy task sinh output, xác minh nội dung file; chạy lại không đổi để quan sát `UP-TO-DATE`; thay đổi input để xác nhận file được cập nhật.
8. **Kiểm thử Configuration Cache:** chạy cùng tập task hai lần với `--configuration-cache`; xem thông báo đã lưu/tái sử dụng cache hay các vấn đề không tương thích; xác nhận output và ý nghĩa của build không đổi.
9. **Kiểm tra task graph:** dùng `--dry-run` để xác nhận task producer được đưa vào graph khi consumer cần. Nếu side effect vẫn xuất hiện ở dry-run, tìm lại mã thực thi trong configuration.

Lệnh tham khảo:

~~~bash
./gradlew help --no-configuration-cache
./gradlew tasks --no-configuration-cache
./gradlew writeMarker --dry-run --no-configuration-cache
./gradlew writeMarker --configuration-cache
./gradlew writeMarker --configuration-cache
./gradlew writeMarker -Pmessage="Updated" --configuration-cache
~~~

Gradle có thể tạo những file **nội bộ** như cache/log phục vụ chính công cụ; bài toán ở đây là ngăn **artifact nghiệp vụ, tác vụ bên ngoài và mutation không khai báo của build logic** khi chỉ đang cấu hình. Đừng kết luận build sai chỉ vì thư mục `.gradle` hoặc log của daemon thay đổi.

## 11. Lưu ý nâng cao: task graph, dependency và tài nguyên dùng chung

Một số tác dụng phụ ở configuration xuất phát từ việc dùng nó làm “bộ điều phối thủ công”:

~~~kotlin
// Không nên: sinh dữ liệu lúc cấu hình với mong muốn task khác tự dùng.
val output = layout.buildDirectory.file("generated/data.txt").get().asFile
output.parentFile.mkdirs()
output.writeText("data")
~~~

Thay vì vậy, cần cho **producer task** sở hữu `@OutputFile`, **consumer task** khai báo `@InputFile` và trỏ đến output của producer. Một file property được set từ task output provider có thể mang thông tin dependency để Gradle sắp xếp thứ tự; với trường hợp không tự suy luận được, thiết lập `dependsOn` rõ ràng. Việc này làm task graph thể hiện chính xác công việc bắt buộc và tránh kết quả tình cờ từ thứ tự cấu hình.

Khi nhiều task cần dùng tài nguyên chung như cổng mạng, service hoặc pool kết nối, đừng tạo kết nối trong mỗi build script hay giữ biến static/mutable toàn cục rồi phụ thuộc vào thứ tự task. **Shared Build Service** là cơ chế Gradle hỗ trợ để chia sẻ và quản lý tài nguyên trong execution, kể cả giới hạn số task đồng thời khi cần. Task phải mô tả input/output và quan hệ phụ thuộc đủ rõ để Gradle có thể chạy song song an toàn.

Nếu cần giám sát sự kiện hoàn thành task, tránh phụ thuộc các callback lifecycle cũ vốn không chạy lại khi Configuration Cache được tái sử dụng. Với plugin có nhu cầu loại này, xem cơ chế Build Service gắn `OperationCompletionListener` theo tài liệu Configuration Cache chính thức.

## 12. Những hiểu nhầm thường gặp

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “`tasks.register { }` là execution.” | Chỉ các `doFirst`/`doLast` hoặc `@TaskAction` là task actions. Khối configure của `tasks.register` vẫn thuộc configuration khi được hiện thực. |
| “Chuyển I/O vào `afterEvaluate` là hết side effect.” | `afterEvaluate` vẫn là configuration; phải chuyển công việc tạo artifact sang task. |
| “`./gradlew help` không làm gì ngoài in trợ giúp.” | Khi không tái sử dụng Configuration Cache, Gradle vẫn đánh giá build logic; side effect trong cấu hình có thể xuất hiện. |
| “`--dry-run` sẽ ngăn mọi đoạn mã tự chạy.” | Nó bỏ qua task actions nhưng configuration vẫn có thể diễn ra. |
| “Mọi đọc tệp/biến môi trường tại configuration đều không tương thích Configuration Cache.” | Gradle có cơ chế theo dõi nhiều loại configuration input này; tác động chính là chi phí/invalidation và đúng thời điểm sử dụng. |
| “Có `@TaskAction` là Gradle tự biết mọi input/output.” | Cần khai báo `@Input`/`@InputFile`/`@OutputFile` hoặc API tương ứng; side effect ngoài output khai báo vẫn khó cache. |
| “Cache hit sẽ chạy lại đoạn ghi file trong build script.” | Configuration Cache hit bỏ qua việc đánh giá build script, nên không thể dựa vào việc ghi file trong giai đoạn cấu hình. |
| “Task chạy thêm file ở một module khác chắc do configuration.” | Có thể do task dependency graph. Kiểm tra `--dry-run` và input/output dependency, không suy luận từ log riêng lẻ. |
| “Cứ bật `--rerun-tasks` là configuration chắc chắn chạy lại.” | `--rerun-tasks` chủ yếu điều khiển thực thi task; cần `--no-configuration-cache` để loại việc tái sử dụng Configuration Cache khỏi thử nghiệm. |

## 13. Checklist trước khi chốt thay đổi

- [ ] Chức năng của `settings.gradle(.kts)`/`build.gradle(.kts)` ở configuration là thiết lập **mô hình**, không tự sinh artifact nghiệp vụ.
- [ ] Việc ghi file, gọi process, gọi API và cập nhật dữ liệu được đặt trong task action phù hợp.
- [ ] Các task tạo output khai báo input và output, không phụ thuộc mutable state của build script.
- [ ] `tasks.register`/`configureEach` được dùng lazy, nhưng các khối cấu hình không chứa tác dụng phụ bất ngờ.
- [ ] Không dùng `Project`/`Settings`/`Gradle` từ task action khi cần tương thích Configuration Cache; dữ liệu được chuyển qua typed properties/provider.
- [ ] Đọc file và biến môi trường đúng lúc; nếu chỉ một task cần thì biến thành input của task.
- [ ] `help`, `tasks` và `--dry-run` không kích hoạt tạo/sửa artifact nghiệp vụ.
- [ ] Chạy task lần đầu tạo kết quả đúng; chạy lại không đổi có thể `UP-TO-DATE`; thay đổi input khiến kết quả được tái tạo.
- [ ] Chạy cùng task hai lần với Configuration Cache không thay đổi ý nghĩa build; không phụ thuộc log hay side effect configuration.
- [ ] Các task cùng đọc/ghi dữ liệu có dependency và đường dẫn output đúng; tránh xung đột khi chạy song song.

## 14. Tự kiểm tra

1. Tại sao `file("x.txt").writeText("...")` ở top-level `build.gradle.kts` nguy hiểm? **Vì chạy ở configuration**, kể cả khi task đích không cần file, và có thể không chạy khi Configuration Cache hit.
2. Có an toàn hơn nếu chuyển lời gọi trên vào `tasks.register("x") { ... }` nhưng đặt ngoài `doLast`? **Chưa**: khi task được cấu hình, lời gọi vẫn là configuration.
3. Cần đặt chỗ ghi file ở đâu? **`@TaskAction` hoặc `doLast`**, với input/output được khai báo và task chỉ chạy khi cần.
4. Vì sao `@OutputFile` quan trọng? Nó cho Gradle biết output thuộc task, hỗ trợ up-to-date checking, caching và quản lý dependency.
5. `./gradlew help --dry-run` có bảo đảm không xảy ra side effect ở configuration? **Không**: dry-run bỏ qua task actions, không ngăn mã cấu hình.
6. Đọc biến môi trường tại configuration có luôn làm Configuration Cache báo lỗi không? **Không**: Gradle có thể theo dõi biến này là configuration input; vẫn nên trì hoãn nếu chỉ task dùng.
7. Nếu cần sinh file A trước khi task B đọc, làm cách nào? **Tạo A bằng producer task có output khai báo, khai báo input tương ứng cho consumer B và nối task dependency**, thay vì viết file A từ build script khi cấu hình.
8. Vì sao một build có thể chạy đúng khi Configuration Cache miss nhưng sai khi hit? Vì logic phụ thuộc **tác dụng phụ configuration** đã không được chạy lại trên cache hit.

## Tài liệu Gradle chính thức

- [Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization, configuration, execution, task graph.
- [Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): `@TaskAction`, `doLast`, typed inputs/outputs và incremental behavior.
- [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): bỏ qua configuration trên cache hit, inputs cấu hình, task isolation, giới hạn và tối ưu.
- [Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): đọc file ở configuration, provider, API không được truy cập từ task action và các vấn đề tương thích.
- [Best Practices for Performance](https://docs.gradle.org/current/userguide/best_practices_performance.html): lazy configuration, tối ưu hóa task và cache.
- [Lazy Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `tasks.named` và cấu hình task khi cần.
