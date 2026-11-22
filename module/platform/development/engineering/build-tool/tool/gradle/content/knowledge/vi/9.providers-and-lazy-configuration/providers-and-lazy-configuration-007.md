# Thời điểm `get()`, `finalizeValue()` và `disallowChanges()` có ý nghĩa trong Gradle

## 1. Mục tiêu: cấu hình lười nhưng giá trị phải nhất quán

Gradle sử dụng **Provider API** để mô tả dữ liệu chưa cần tính ngay và chuyển dữ liệu giữa extension, task, môi trường và output của các task khác. Trong Kotlin DSL (`build.gradle.kts`), ba thao tác rất dễ nhầm là:

- `get()`: **đọc giá trị hiện tại** từ `Provider<T>` hoặc `Property<T>`. Đọc có thể buộc nguồn dữ liệu được tính; riêng `get()` thông thường **không tự khóa** một `Property`.
- `finalizeValue()`: **tính giá trị cuối cùng ngay bây giờ**, cắt liên kết theo dõi nguồn `Provider`, rồi **cấm sửa** property.
- `disallowChanges()`: **cấm sửa trực tiếp property từ bây giờ**, nhưng **không tính ngay** giá trị; nguồn `Provider` còn có thể cung cấp giá trị thay đổi cho tới lúc property thực sự được final hóa.

Có hai phương thức liên quan cần hiểu để chọn thời điểm hợp lý:

- `finalizeValueOnRead()`: đánh dấu rằng **lần đọc giá trị tiếp theo** sẽ tính và khóa giá trị; trước lần đọc đó còn được cấu hình nếu chưa bị `disallowChanges()`.
- `disallowUnsafeRead()`: chặn truy xuất khi giá trị chưa an toàn trong giai đoạn cấu hình, cho phép các plugin hoàn tất cấu hình; khi đọc hợp lệ sau đó, giá trị cũng được final hóa.

Bài tập trọng tâm là: **đặt các lệnh này ở đâu trong vòng đời Gradle để không ép giá trị quá sớm, không khóa plugin khác khi chưa cấu hình xong, và không làm hai consumer thấy hai giá trị khác nhau?**

Bài dùng Kotlin DSL, Gradle Wrapper và ví dụ chạy được trên Gradle hiện đại. Mỗi chương trình minh họa độc lập có thể đặt trong `build.gradle.kts` của một dự án thử, cùng file `settings.gradle.kts` tối thiểu:

~~~kotlin
rootProject.name = "provider-lifecycle-lab"
~~~

Chạy ở root bằng `./gradlew` (Linux/macOS) hoặc `.\gradlew.bat` (Windows). Các dòng `println` ở mức build-script chỉ để **giải thích thời điểm cấu hình**; không nên coi đó là logging cần xuất hiện trong mọi build khi bật Configuration Cache.

## 2. Phân biệt `Provider<T>` và `Property<T>`

`Provider<T>` là giao diện **truy vấn** một giá trị kiểu `T`. Nó có thể mô tả giá trị tĩnh, dữ liệu từ biến môi trường/Gradle property, phép biến đổi `map`, `flatMap`, output task hoặc chuỗi phụ thuộc vào các provider khác. Provider không nhất thiết đã có giá trị tại thời điểm khai báo; có thể chưa biết tới khi một task thực thi.

`Property<T>` mở rộng `Provider<T>` và cho phép **cấu hình nguồn giá trị** qua `set(...)`, `convention(...)` hoặc các API liên quan. Chính các property có khả năng cấu hình mới có bộ điều khiển vòng đời `finalizeValue`, `finalizeValueOnRead` và `disallowChanges` thông qua `HasConfigurableValue`. Một `Provider<T>` thuần được dùng để đọc/biến đổi, không mặc định có `set` hoặc phương thức final hóa.

Ví dụ:

~~~kotlin
val source = objects.property(String::class.java)
source.convention("development")

val selected: org.gradle.api.provider.Provider<String> =
    source.map { it.uppercase() }

tasks.register("explainProvider") {
    doLast {
        println("VALUE=" + selected.get())
    }
}
~~~

Trong ví dụ này:

- `source` là `Property<String>`, có thể được thay bằng `source.set("production")` trong giai đoạn cấu hình.
- `selected` là `Provider<String>` được tạo bằng `map`, phụ thuộc vào `source`. Chỉ đăng ký provider **chưa đòi hỏi** thực hiện phép biến đổi ngay.
- `selected.get()` trong `doLast` đọc giá trị khi action chạy; nếu nguồn không thay đổi, dòng kết quả là `VALUE=DEVELOPMENT`.
- Đoạn ví dụ chỉ minh họa mô hình; để tạo task phù hợp Configuration Cache trong dự án thực, nên dùng **task input property có annotation** thay vì capture biến trong build script, như ví dụ hoàn chỉnh ở mục 8.

### Convention và giá trị tường minh

`convention(value)` là **giá trị mặc định**, thường do plugin thiết lập trước để người dùng có thể override. `set(value)` hoặc `set(provider)` đặt nguồn/giá trị tường minh cho property và có ưu tiên so với convention. Khi chưa có giá trị tường minh, convention được dùng; khi `set` thay đổi nguồn, lần truy vấn sau có thể thấy giá trị mới nếu chưa final hóa.

~~~kotlin
val mode = objects.property(String::class.java)
mode.convention("dev")
println(mode.get())      // dev

mode.set("prod")
println(mode.get())      // prod
~~~

Hai dòng `println` ở cấp script được thực hiện trong **configuration**, nếu build script được đánh giá. Với ví dụ học tập có thể chạy `./gradlew -q help --no-configuration-cache` để buộc đánh giá lại cấu hình; ngoài log của chính script, Gradle có thể in thông tin khác.

## 3. Bảng so sánh năm thao tác quan trọng

| Thao tác | Có tính/truy vấn nguồn ngay? | Có khóa việc `set`/`convention`? | Có tiếp tục theo dõi upstream `Provider`? |
| --- | --- | --- | --- |
| `property.get()` | **Có**, tại thời điểm đọc, nếu cần. | **Không**, với property thông thường chưa có cơ chế khóa khác. | **Có thể có** ở các lần đọc kế tiếp; không hiểu `get` là chụp giá trị bất biến. |
| `property.finalizeValue()` | **Có**, ngay khi gọi. | **Có**, từ thời điểm gọi. | **Không**; nguồn được thay bằng giá trị đã tính. |
| `property.disallowChanges()` | **Không** chỉ vì gọi phương thức này. | **Có**, cấm thay đổi trực tiếp property. | **Có**, tới khi property được final hóa. |
| `property.finalizeValueOnRead()` | **Chưa**, chờ lần đọc giá trị tiếp theo. | **Sau lần đọc final hóa**; trước đó có thể cấu hình nếu chưa bị khóa riêng. | **Có trước lần đọc**, **không sau khi final hóa**. |
| `property.disallowUnsafeRead()` | **Chưa**, chặn đọc sớm khi chưa an toàn. | Việc đọc hợp lệ sau giai đoạn cấu hình sẽ final hóa. | Không dựa vào việc đọc sớm để chốt nguồn; bảo vệ việc hoàn tất cấu hình. |

Bảng mô tả hành vi của **Property/HasConfigurableValue** theo Gradle API. Không suy rộng rằng mọi Java/Kotlin object hoặc `Provider` custom đều được hỗ trợ gọi các phương thức khóa. Cũng không suy ra một `finalizeValue` sẽ “đóng băng sâu” mọi object: nếu giá trị là **một mutable object**, tham chiếu của property đã cố định nhưng nội dung object đó vẫn có thể bị thay đổi từ nơi khác.

Điểm rất quan trọng: **`get()` là phép đọc, `disallowChanges()` là khóa cửa ghi, `finalizeValue()` vừa lấy snapshot vừa khóa cửa ghi.** Nắm rõ ba ý nghĩa này sẽ giải quyết đa số lỗi về giá trị bị chốt quá sớm.

## 4. `get()`: cần giá trị khi nào thì đọc khi ấy

`get()` truy vấn giá trị của một provider tại **thời điểm lời gọi diễn ra**. Nếu provider chưa có giá trị, `get()` ném `IllegalStateException`; nó không tự chế tạo một default value. Nếu nguồn là phép tính lazy (`map`, `flatMap`), lấy giá trị có thể khởi động phép tính đó. Cách provider cache/memoize kết quả tùy implementation và cơ chế Configuration Cache; đừng mặc định mọi `get()` đều đọc file/network một lần, hoặc luôn tính lại.

**Ví dụ `get()` không tự final hóa** — toàn bộ đoạn sau là một file `build.gradle.kts` độc lập:

~~~kotlin
val upstream = objects.property(String::class.java)
upstream.set("version-1")

val downstream = objects.property(String::class.java)
downstream.set(upstream)

println("A=" + downstream.get())

upstream.set("version-2")
println("B=" + downstream.get())

downstream.set("manual")
println("C=" + downstream.get())
~~~

Chạy:

~~~bash
./gradlew -q help --no-configuration-cache
~~~

Các dòng do script in ra là:

~~~text
A=version-1
B=version-2
C=manual
~~~

Giải thích: `downstream.set(upstream)` tạo liên kết theo nguồn. Đọc `downstream.get()` tại A không khiến `downstream` bị khóa; khi `upstream.set(...)` đổi thành `version-2`, lần đọc B phản ánh nguồn mới. Sau `downstream.set("manual")`, nguồn upstream được thay bằng giá trị trực tiếp; C đọc `manual`. Với các provider có tính toán/nguồn ngoài, chính xác khi nào dữ liệu được tính có thể khác, nhưng ý nghĩa cốt lõi **`get` không phải `finalizeValue`** vẫn giữ nguyên.

**Vì sao không nên gọi `get()` quá sớm trong cấu hình?**

~~~kotlin
val selectedMode: String =
    providers.gradleProperty("mode").orElse("dev").get()
~~~

Dòng trên lấy `mode` **ngay khi script được cấu hình**. Nếu một task mới cần `mode`, việc đọc sớm này có thể:

- Làm một nguồn dữ liệu/pipeline provider được tính khi task thậm chí không được chạy.
- Khiến dữ liệu chỉ liên quan một task trở thành **configuration input** và góp phần làm Configuration Cache bị vô hiệu hóa khi giá trị đổi.
- Thất bại khi nguồn chỉ có thể cung cấp giá trị ở execution, chẳng hạn phụ thuộc output của task khác.
- Lấy snapshot vào biến `String` trong script; biến này không còn là provider theo dõi nguồn khi nguồn thay đổi trong cùng quá trình cấu hình.

Thay vào đó, giữ provider:

~~~kotlin
val selectedMode = providers.gradleProperty("mode").orElse("dev")
~~~

Rồi gắn provider vào một `Property<String>` của task cần nó. Trong task action, đọc input đã được khai báo. Đây mới là tối ưu cả **tính đúng** lẫn **hiệu năng**; `get()` bản thân không sai, sai là **đọc trước khi thực sự cần**.

## 5. `finalizeValue()`: chốt giá trị ngay và cắt theo dõi nguồn

`finalizeValue()` làm hai việc trong cùng một thời điểm:

1. **Truy vấn** giá trị hiện tại của property (bao gồm provider upstream nếu property lấy từ một provider).
2. **Giữ giá trị ấy làm giá trị cuối**; nguồn provider cũ không còn được theo dõi, và mọi lời gọi thay đổi trực tiếp property như `set(...)`/`convention(...)` sẽ bị từ chối.

Ví dụ độc lập:

~~~kotlin
val upstream = objects.property(String::class.java)
upstream.set("v1")

val frozen = objects.property(String::class.java)
frozen.set(upstream)

upstream.set("v2")
frozen.finalizeValue()

println("BEFORE=" + frozen.get())

upstream.set("v3")
println("AFTER=" + frozen.get())
~~~

Khi chạy `./gradlew -q help --no-configuration-cache`, các dòng của script:

~~~text
BEFORE=v2
AFTER=v2
~~~

Tại `frozen.finalizeValue()`, `frozen` lấy `v2` và **ngừng theo dõi upstream**. Việc `upstream.set("v3")` sau đó vẫn hợp lệ vì upstream chưa khóa, nhưng không đổi `frozen`.

Thử đưa vào script một dòng **sau khi đã finalize**:

~~~kotlin
frozen.set("v4") // Lỗi IllegalStateException: property đã bị khóa.
~~~

Đây là **đoạn cố ý gây lỗi**, không thêm vào ví dụ muốn chạy thành công. Gradle ném lỗi khi cấu hình vì property đã final. Khi debug, điều quan trọng là xác định **ai gọi finalize sớm** và lệnh `set`/`convention` nào xảy ra sau đó.

### Khi nào thực sự cần `finalizeValue()`?

- Plugin đã nhận đủ cấu hình và cần bảo đảm mọi consumer từ đây thấy **một snapshot ổn định**, tránh thay đổi giữa tính input/output và action.
- Một giá trị/đường dẫn sẽ được dùng để cấu trúc task hoặc output và không thể chấp nhận source đổi sau điểm đó.
- Trong một API plugin, tác giả xác định một **ranh giới rõ**: sau bước này không cho cấu hình bổ sung nữa.

Tuy nhiên **đừng finalize trong khối plugin `apply` hoặc ngay khi tạo extension** nếu người dùng hoặc plugin khác còn cần cấu hình. Chốt quá sớm dẫn đến `Cannot change value of a finalized property`. Với input property của task, Gradle **tự final hóa khi task bắt đầu thực thi** trong cơ chế thông thường; nhiều tình huống không cần tác giả build script gọi `finalizeValue` thủ công.

### Final không đồng nghĩa immutable sâu

Ví dụ `Property<MutableList<String>>` chứa một list mutable: `finalizeValue()` khóa **tham chiếu giá trị property**, nhưng không nhất thiết chặn mã khác sửa **các phần tử trong list**. Để mô hình Gradle đúng và có thể cache, ưu tiên `ListProperty<String>`, `SetProperty<String>`, `MapProperty<K,V>` với API theo phần tử và dữ liệu đầu vào bất biến về mặt ý nghĩa, không chia sẻ object mutable không được theo dõi.

## 6. `disallowChanges()`: ngừng sửa trực tiếp, vẫn giữ provider lazy

`disallowChanges()` **không gọi upstream để lấy giá trị** và **không cắt liên kết đến provider**. Nó chỉ khóa API thay đổi trực tiếp **property đang gọi**. Nguồn provider vẫn có thể cung cấp giá trị mới trước lúc property được final hóa.

Ví dụ độc lập:

~~~kotlin
val upstream = objects.property(String::class.java)
upstream.set("alpha")

val downstream = objects.property(String::class.java)
downstream.set(upstream)
downstream.disallowChanges()

println("A=" + downstream.get())

upstream.set("beta")
println("B=" + downstream.get())

downstream.finalizeValue()
upstream.set("gamma")
println("C=" + downstream.get())
~~~

Khi chạy `./gradlew -q help --no-configuration-cache`, các dòng của script:

~~~text
A=alpha
B=beta
C=beta
~~~

Giải thích:

- `downstream.disallowChanges()` chặn `downstream.set("...")` ngay từ lúc gọi, nhưng `upstream` là **property riêng**, chưa bị khóa.
- Dòng B thấy `beta` vì downstream vẫn theo dõi upstream.
- Chỉ tại `downstream.finalizeValue()` nó mới lấy snapshot `beta`. Dòng C giữ `beta` dù upstream thành `gamma`.

Nếu chèn dòng sau **sau `disallowChanges()`**:

~~~kotlin
downstream.set("other") // IllegalStateException; chỉ minh họa lệnh sai.
~~~

lệnh sẽ bị từ chối. Việc nguồn upstream đổi được **không phải cách lách khóa** để chỉnh downstream bằng `set`; đó là đặc điểm dataflow của provider. Không lạm dụng mutable upstream nếu build cần giá trị cố định: hãy chốt đúng thời điểm bằng `finalizeValue` hoặc `finalizeValueOnRead`.

**Khi nào dùng `disallowChanges()`?** Khi một plugin đã thiết lập xong **nguồn dữ liệu** (ví dụ một provider cho file output, biến môi trường hoặc kết quả task khác) và muốn cấm người khác đổi sang một nguồn khác, nhưng không muốn/không thể lấy giá trị ngay. Đây cũng là lựa chọn hữu ích cho nguồn có chi phí tính toán cao hoặc chỉ sẵn có về sau.

## 7. `finalizeValueOnRead()`: chốt ở lần đọc đầu tiên

`finalizeValueOnRead()` đặt **chế độ “final hóa khi đọc”**. Nó khác với `finalizeValue()` ở chỗ **chưa tính giá trị tại lúc gọi**. Trước lần đọc đầu tiên, property vẫn theo dõi nguồn và có thể được cấu hình nếu chưa bị khóa riêng; khi đọc, Gradle tính snapshot rồi khóa.

Ví dụ độc lập:

~~~kotlin
val upstream = objects.property(String::class.java)
upstream.set("one")

val target = objects.property(String::class.java)
target.set(upstream)
target.finalizeValueOnRead()

upstream.set("two")
println("FIRST=" + target.get())

upstream.set("three")
println("SECOND=" + target.get())
~~~

Các dòng script khi chạy `./gradlew -q help --no-configuration-cache`:

~~~text
FIRST=two
SECOND=two
~~~

Vì lần đọc `target.get()` tại FIRST đã chốt `two`, thay đổi upstream sau đó không làm SECOND đổi. Nếu gọi `target.set("other")` sau lần đọc, Gradle báo lỗi property đã final.

Một tổ hợp có ích trong plugin:

~~~kotlin
someProperty.disallowChanges()
someProperty.finalizeValueOnRead()
~~~

Đoạn này là **mảnh mã phải đặt trong ngữ cảnh đã khai báo `someProperty`**. Nó thể hiện ý định: đã lựa chọn **nguồn** cuối cùng, cấm thay nguồn ngay, nhưng chỉ tính **giá trị** khi consumer thực sự cần. Đây là phương án thay `finalizeValue()` khi giá trị đắt hoặc chỉ có khi task chạy.

**Cảnh báo thời điểm:** nếu sau `finalizeValueOnRead()` vẫn vô tình gọi `get()` ở configuration, bạn sẽ kích hoạt final hóa **ngay lúc đó**. Bản thân flag “OnRead” không đẩy việc đọc sang execution. Tương tự, một consumer gọi `getOrNull()` hoặc cơ chế Gradle cần truy vấn giá trị có thể buộc provider được đánh giá; không dùng các phép đọc thử một cách vô tư khi muốn giữ nguồn lazy.

## 8. Ví dụ task hoàn chỉnh: đặt `get()` trong `@TaskAction`

Cách ứng dụng phổ biến là định nghĩa task với **input property**, kết nối provider ở configuration, và đọc giá trị từ task action. Đoạn sau là **toàn bộ `build.gradle.kts` độc lập** trên Gradle có Kotlin DSL:

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class PrintMode : DefaultTask() {
    @get:Input
    abstract val mode: Property<String>

    @TaskAction
    fun printMode() {
        println("MODE=" + mode.get())
    }
}

tasks.register<PrintMode>("printMode") {
    mode.convention(
        providers.gradleProperty("mode").orElse("dev")
    )
}
~~~

Thực thi:

~~~bash
./gradlew -q printMode --no-configuration-cache
./gradlew -q printMode -Pmode=production --no-configuration-cache
~~~

Hai dòng của task action lần lượt là:

~~~text
MODE=dev
MODE=production
~~~

Giải thích:

1. `providers.gradleProperty("mode")` cung cấp giá trị từ `-Pmode=...` mà không cần `get()` trong khối `tasks.register`.
2. `orElse("dev")` giữ một **provider fallback** nếu người dùng không đặt `mode`.
3. `mode.convention(provider)` chỉ định default value. Build script/plugin khác có thể dùng `mode.set(...)` để override trước khi Gradle final hóa.
4. `@get:Input` khai báo `mode` là dữ liệu đầu vào của task để Gradle biết khi nào giá trị thay đổi.
5. `@TaskAction` chỉ đọc `mode.get()` khi task thực thi. Trong quá trình xử lý task, Gradle thường đã khóa input property để tránh việc các consumer khác nhận giá trị không nhất quán.

Ở đây không cần ép `mode.finalizeValue()` trong `tasks.register`. Việc đó dễ khóa property quá sớm khi plugin khác hoặc người dùng còn muốn tùy chỉnh task. Với tác vụ có output, nên khai báo thêm `@OutputFile`/`@OutputDirectory` nếu task thực sự sinh file; task in màn hình như ví dụ không có output để kiểm tra up-to-date, nên action có thể chạy trên mỗi lần yêu cầu. Dùng `./gradlew -q printMode --configuration-cache` hai lần để quan sát Configuration Cache mà không đưa tham chiếu `project` vào action.

Đây là **cách chuẩn cho dữ liệu dùng tại execution**. Một số dữ liệu phải dùng để quyết định task graph tại configuration; khi ấy có thể cần đọc sớm một cách chủ đích và bảo đảm nguồn input được Gradle theo dõi. Không áp dụng quy tắc “mọi `get()` đều phải ở task action” một cách máy móc.

## 9. Tại sao `get()` trong `tasks.register { }` vẫn là đọc sớm?

~~~kotlin
tasks.register<PrintMode>("printMode") {
    val chosen = providers.gradleProperty("mode").orElse("dev").get()
    mode.set(chosen)
}
~~~

Đây là **biến thể minh họa cách không tối ưu**, giả sử class `PrintMode` đã định nghĩa như mục 8. Khối `tasks.register { ... }` là **task configuration action** chạy khi Gradle cần cấu hình task, **không phải** task execution. Lời gọi `get()` ở đây tính giá trị khi task được cấu hình, thay vì giữ provider. Nếu `mode` là giá trị được plugin khác thiết lập sau đó hoặc là kết quả của task khác, việc đọc ở đây có thể sớm hơn dự định.

Nên viết:

~~~kotlin
tasks.register<PrintMode>("printMode") {
    mode.set(providers.gradleProperty("mode").orElse("dev"))
}
~~~

Hai fragment trên **không đặt đồng thời** trong một file nếu cùng đăng ký task `printMode`. `tasks.register` giúp **trì hoãn việc hiện thực/cấu hình task**; bên trong action cấu hình vẫn chỉ nên thiết lập model, không dùng `get()` khi giá trị không thật sự cần để xây dựng model. Tương tự, chuyển `get()` từ top-level sang `afterEvaluate` không tự biến nó thành đọc tại execution.

### Kết nối giá trị từ task tạo output

Với đầu ra của task A, đừng viết `val file = producerTask.get().outputFile.get().asFile` ở configuration chỉ để chuyển cho task B. Cách này hiện thực task và giải quyết giá trị sớm, có thể đọc output trước khi được tạo.

Hãy dùng provider từ task A làm **input** của task B (`RegularFileProperty` hoặc `ConfigurableFileCollection` phù hợp). Gradle có thể mang theo thông tin task dependency qua provider để sắp xếp producer trước consumer. Nếu API không suy ra phụ thuộc được, dùng `dependsOn` có chủ đích. Chỉ truy xuất file trong `@TaskAction` sau khi task graph được thiết lập. Cơ chế này khác với việc chốt sớm bằng `finalizeValue()`: final hóa không tự tạo file, không tự chạy producer task và không thay cho dependency.

## 10. `disallowUnsafeRead()`: khi đọc cấu hình là quá sớm

`disallowUnsafeRead()` dành cho property mà giá trị **không nên được đọc trước khi cấu hình project kết thúc**, để các plugin khác có cơ hội hoàn tất cấu hình. Sau giai đoạn đó, truy vấn hợp lệ sẽ final hóa giá trị trên lần đọc. Một plugin có thể dùng API này để bảo vệ extension khi cấu hình trải qua nhiều plugin khác nhau.

Ví dụ **mảnh mã minh họa trong plugin**, không phải một build script đầy đủ:

~~~kotlin
val configuredPath = objects.property(String::class.java)
configuredPath.convention("default")
configuredPath.disallowUnsafeRead()
~~~

Nếu thêm `configuredPath.get()` ngay khi **project vẫn đang được cấu hình**, Gradle có thể ném lỗi đọc không an toàn. Lời gọi này không bảo đảm giá trị có thể đọc trong tất cả callbacks của configuration; người dùng nên nối provider tới task input thay vì cố đọc ở đây.

Phân biệt:
- `disallowChanges`: **cấm chỉnh nguồn trực tiếp**, nhưng không chủ động cấm đọc trong configuration.
- `disallowUnsafeRead`: **cấm đọc khi giá trị còn có thể chưa ổn định trong configuration**, và final hóa khi được đọc hợp lệ.
- `finalizeValueOnRead`: đánh dấu **đọc đầu tiên sẽ final hóa**, nhưng không đặt mục tiêu tự chặn mọi cách đọc sớm như `disallowUnsafeRead`.
- `finalizeValue`: chốt ngay, có thể là quá sớm nếu người dùng/plugin khác còn cấu hình.

Một plugin thông thường chỉ cần `Property`, `convention` và task input là đủ; không phải extension nào cũng cần gọi `disallowUnsafeRead()` thủ công.

## 11. Thời điểm trong vòng đời build: trước và sau khi cấu hình

| Thời điểm | Hành động thường hợp lý | Hành động cần cân nhắc |
| --- | --- | --- |
| Plugin được apply | Tạo extension; đặt `convention(provider)` cho defaults. | `get()` để tính dữ liệu chưa cần; `finalizeValue()` làm người dùng không override được. |
| `build.gradle.kts` đang cấu hình task | `tasks.register`, `mode.set(provider)`, nối outputs/inputs. | Gọi `get()` của output task hoặc `finalizeValue()` trong callback còn có plugin khác tham gia. |
| Sau khi tất cả bên tham gia đã chọn nguồn | Có thể `disallowChanges()` nếu API plugin cần cấm đổi nguồn. | Chốt ngay nếu upstream chưa có giá trị hoặc tính toán còn đắt. |
| Thời điểm consumer thực sự cần giá trị | Đọc provider; dùng `finalizeValueOnRead()` nếu cần một snapshot ổn định sau lần đọc đầu tiên. | Tin rằng `get` tự đóng băng property hoặc gọi lại source sẽ luôn cho cùng một kết quả. |
| Task sắp/bắt đầu execution | Gradle quản lý final hóa task properties; task action dùng `get()` trên input. | Sửa input trong task action sau khi Gradle đã dùng input để lập fingerprint/cache. |

Điểm quan trọng: ranh giới configuration/execution của Gradle không phải lúc nào cũng trùng chính xác với ranh giới final hóa **mọi** property do bạn tạo. Một property trên extension có thể tồn tại qua configuration và được plugin giữ đến khi cần; task input property thường được Gradle quản lý chặt hơn khi bắt đầu execution.

Khi cùng một extension được nhiều plugin cấu hình, thứ tự rất quan trọng. Ví dụ plugin A tạo default, plugin B có thể override, build script người dùng tùy chỉnh lần cuối; nếu plugin A `finalizeValue()` ngay khi apply, cả B và người dùng có thể gặp lỗi dù cấu hình của họ hợp lệ. Nên thiết kế public extension theo hướng **cho phép cấu hình trước, chốt khi sắp dùng**, hoặc dựa vào task input finalization tự nhiên.

## 12. Đọc giá trị bị thiếu: `getOrNull`, `getOrElse`, `isPresent`

`get()` yêu cầu provider có giá trị:

~~~kotlin
val missing = objects.property(String::class.java)
println(missing.get()) // Có thể ném IllegalStateException vì chưa có giá trị.
~~~

Đây là **đoạn cố ý gây lỗi**, không chạy cùng ví dụ muốn thành công. Với nguồn tùy chọn, có các API:

~~~kotlin
val optional = providers.gradleProperty("optionalLabel")

val valueOrNull: String? = optional.orNull
val valueOrDefault: String = optional.getOrElse("unknown")
val present: Boolean = optional.isPresent

val lazyFallback: org.gradle.api.provider.Provider<String> =
    optional.orElse("unknown")
~~~

Ở Kotlin DSL, `orNull` là property-style access đến `getOrNull()`. `getOrElse("unknown")` **đọc ngay** để trả về `String`, trong khi `orElse("unknown")` trả về **một Provider mới** có fallback để nối tiếp vào task input. `isPresent` kiểm tra có giá trị hay không, nhưng với một số provider, kiểm tra này cũng có thể cần đánh giá nguồn: đừng xem nó là phép “peek” luôn miễn phí và không ảnh hưởng tính lazy.

Nếu một `Property` đã gọi `finalizeValueOnRead()`, các truy vấn để lấy/kiểm tra giá trị có thể tham gia cơ chế final hóa tùy API và nguồn, nên tránh “thử đọc” trước khi muốn khóa. Nếu property bắt buộc mà thiếu, tốt hơn là báo lỗi rõ tại điểm cần giá trị hoặc khai báo convention thích hợp; không chữa bằng `getOrNull() ?: ""` rồi âm thầm tạo cấu hình rỗng không hợp lệ.

## 13. Configuration Cache và Build Cache: hệ quả của đọc sớm

### Configuration Cache

Configuration Cache có thể lưu mô hình cấu hình để lần chạy sau **bỏ qua configuration** khi các input liên quan không đổi. Gradle có thể lưu provider theo **giá trị** hoặc **phép tính**, tùy nguồn và bối cảnh; một số provider từ môi trường/file được theo dõi làm configuration inputs.

- `get()` khi cấu hình có thể làm nguồn được tính sớm, tạo công việc không cần cho task chưa chạy, hoặc đưa giá trị nguồn vào tập input của configuration.
- `finalizeValue()` khi cấu hình chụp một giá trị ở thời điểm đó. Nếu chỉ có task execution mới cần, đây thường là quá sớm.
- `disallowChanges()` khóa source assignment mà **không** tính upstream; giúp giữ mô hình lazy khi plugin đã quyết định nguồn.
- `finalizeValueOnRead()` giữ phép tính lazy đến lần consumer đọc. Cần tránh một consumer vô tình truy vấn trong configuration.
- Nếu nguồn từ `providers.gradleProperty`/`environmentVariable` hoặc các API được Gradle hỗ trợ, Gradle có thể theo dõi thay đổi đúng cách. Không tự đọc `System.getenv` trong một `providers.provider { ... }` tùy ý rồi giả định luôn tương thích Configuration Cache; loại provider/captured state quyết định hành vi.

### Build Cache và up-to-date checks

Build Cache lưu output của task có đầu vào/đầu ra khai báo và đủ điều kiện. Input `@Input` từ `Property<String>` là dữ liệu được Gradle đưa vào fingerprint. Nếu task action làm `mode.set("new")` rồi mới `mode.get()`, nó vừa có thể gặp lỗi vì input đã final, vừa tạo khác biệt với dữ liệu Gradle đã dùng để tính cache key. **Không chỉnh input trong task action**; xử lý input đã được chốt thành kết quả đầu ra.

Ngược lại, `get()` của task input trong action là điều bình thường và đúng. Đừng nghĩ phải tự `finalizeValue()` mỗi khi gọi `get()`. Việc khai báo input/output và gắn provider đúng quan trọng hơn thủ thuật khóa property sớm.

## 14. Ví dụ trong plugin: convention, override, lock

Giả sử plugin tạo extension `releaseSettings` và người dùng muốn override giá trị:

~~~kotlin
// Ví dụ logic cấu hình, không phải đoạn file build độc lập.
val channel = objects.property(String::class.java)
channel.convention("snapshot")

// Người dùng hoặc plugin khác vẫn có thể override:
channel.set("release")

// Chỉ sau khi đã thống nhất không cho thay nguồn:
channel.disallowChanges()

// Nếu cần snapshot về sau:
channel.finalizeValueOnRead()
~~~

Trong ví dụ này, `channel` không bị tính khi gọi `disallowChanges()`. Nếu upstream là provider thay vì chuỗi trực tiếp, nó tiếp tục được tính khi cần cho đến lần đọc final hóa. Nếu dùng `channel.finalizeValue()` thay dòng cuối, snapshot xảy ra **ngay tại cấu hình**, và một provider chỉ có giá trị ở execution có thể chưa sẵn sàng.

**Không thêm mặc định các lệnh khóa vào mọi `Property`.** Public extension API cần cho người dùng tùy chỉnh; một plugin nên chốt input ở ranh giới sử dụng thực sự. Đối với task input, Gradle thường tự thực hiện điều đó khi task bắt đầu thực thi. Trong một plugin có nhiều task tiêu thụ cùng extension, có thể kết nối bằng `mode.set(extension.channel)`, rồi để mỗi task nhận giá trị theo provider thay vì copy `extension.channel.get()` lúc cấu hình.

## 15. Tác dụng khi dùng `ListProperty`, `MapProperty` và file properties

Bộ `finalizeValue`/`finalizeValueOnRead`/`disallowChanges` không chỉ có trên `Property<String>`. Nó cũng hiện diện trên các property cấu hình được như `ListProperty<T>`, `SetProperty<T>`, `MapProperty<K,V>`, `RegularFileProperty` và `DirectoryProperty`.

Ví dụ list:

~~~kotlin
val flags = objects.listProperty(String::class.java)
flags.add("a")
flags.add("b")
flags.disallowChanges()

// flags.add("c") sẽ bị từ chối vì flags đã disallowChanges().
println(flags.get()) // [a, b]
~~~

Lưu ý:
- `disallowChanges` khóa thao tác chỉnh property/collection như `add`, `addAll`, `put`... (tùy loại); nhưng nếu nguồn là provider của collection thì nguồn đó có thể thay đổi trước final hóa.
- `finalizeValue` của `ListProperty` truy vấn các provider phần tử đã gắn và ngừng theo dõi chúng; nó không nhất thiết biến mọi phần tử mutable thành bất biến.
- `RegularFileProperty.get()` trả object vị trí tệp; **đọc giá trị file property không giống đọc nội dung file** và không tự tạo file. Cần tách provider của đường dẫn, provider nội dung file và output của task.
- Nếu file là output của task A, dùng output provider để nối vào task B; **không** cố `finalizeValue()` đường dẫn rồi kỳ vọng Gradle tự chạy A hoặc file đã tồn tại.

## 16. Lỗi thường gặp và cách khắc phục

| Lỗi/triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Cannot change value of a finalized property` | Đã gọi `finalizeValue` hoặc `finalizeValueOnRead` rồi có một lần đọc khóa trước khi code `set` chạy. | Tìm chỗ final hóa/đọc đầu tiên; sắp xếp lại cấu hình, chỉ khóa tại ranh giới sử dụng. |
| `The value for this property is final and cannot be changed` | Task input đã được Gradle chốt trước execution hoặc plugin khóa sớm. | Không thay input trong `@TaskAction`; cấu hình qua provider trước execution. |
| `Cannot change the value of a property that has been disallowed changes` | `disallowChanges` đã được gọi trước `set`/`convention`. | Cấu hình nguồn xong mới khóa; nếu còn các plugin khác cần override, chưa nên khóa. |
| `get()` ném lỗi khi provider chưa có giá trị | Chưa `set`/`convention`, biến môi trường thiếu, output chưa sẵn có. | Đặt default bằng `convention` hoặc `orElse`; với output task, gắn provider và dependency đúng. |
| Giá trị upstream đổi nhưng downstream không đổi | Downstream đã `finalizeValue` hoặc được final hóa ở lần đọc đầu. | Kiểm tra thời điểm chốt; nếu muốn theo dõi thay đổi trước execution, đừng chốt sớm. |
| `disallowChanges()` đã gọi mà downstream vẫn đổi | Nó chỉ khóa sửa trực tiếp, **không** snapshot upstream. | Nếu cần giá trị bất biến, dùng `finalizeValue` hoặc `finalizeValueOnRead` khi thích hợp. |
| `finalizeValueOnRead()` vẫn tính giá trị trong configuration | Có code `get()`/truy vấn giá trị trước execution. | Loại read sớm; nối provider vào task input hoặc dùng API an toàn theo vòng đời. |
| `get()` trong `tasks.register { }` làm chậm build | Action trong `register` vẫn là cấu hình task, có thể hiện thực provider sớm. | Thay `mode.set(provider.get())` bằng `mode.set(provider)`. |
| Task action dùng `project` để tìm property | Truy cập mô hình Project tại execution có thể không tương thích Configuration Cache. | Truyền dữ liệu từ configuration qua `Property<T>` được annotation `@Input`, rồi `get` trong action. |
| Cache hit/miss khiến log cấu hình xuất hiện khác nhau | Configuration Cache bỏ qua việc đánh giá script ở cache hit. | Đừng dùng `println` trong configuration làm tín hiệu bắt buộc của task; log trong task action. |
| Output được sinh trước task do `get`/code cấu hình | Side effect đặt trong provider transformer hoặc code configuration. | Giữ transformer thuần, không viết file/network ngoài task action có input/output. |
| Có `finalizeValue()` nhưng mutable object vẫn bị chỉnh | Final khóa tham chiếu property, không deep-freeze object. | Tránh chia sẻ mutable object; dùng typed collection properties và mô hình dữ liệu bất biến. |

Tên thông báo lỗi cụ thể thay đổi theo Gradle version và context; ưu tiên xác định **lệnh lock nào chạy trước lệnh sửa**, cùng thời điểm provider bị đọc.

## 17. Quy trình debug thời điểm khóa giá trị

1. **Xác định property** bị lỗi: tên extension/task input, kiểu `Property`/`RegularFileProperty` và nơi được tạo.
2. **Tìm tất cả nguồn cấu hình**: `convention`, `set`, `value`, `add`/`put`, các plugin và build script khác đang đụng cùng property.
3. **Tìm lệnh đọc**: `get`, `getOrNull`, `getOrElse`, `isPresent`, `map` transformation bị truy vấn gián tiếp, hoặc Gradle đọc input để xử lý task.
4. **Tìm lệnh khóa**: `finalizeValue`, `finalizeValueOnRead`, `disallowChanges`, `disallowUnsafeRead` và thời điểm task execution bắt đầu.
5. **Sắp xếp timeline**: “set nguồn → plugin khác override → disallowChanges nếu cần → consumer đọc/finalize”. Tránh khóa trước bước override hợp lệ.
6. **Thử từng ví dụ độc lập** bằng `./gradlew -q help --no-configuration-cache` khi đang chứng minh mã cấp script; tách ví dụ cố ý lỗi để biết chính xác lỗi nào được kích hoạt.
7. **Thử task thực** bằng `./gradlew printMode -Pmode=production --configuration-cache` hai lần, kiểm tra action đọc đúng input và Gradle không báo vấn đề tương thích.
8. **Kiểm tra tính cần thiết**: nếu task input đã được Gradle tự final hóa, có thật sự cần tự gọi lock trong plugin không? Nếu chỉ cần ngăn đổi **nguồn** nhưng dữ liệu còn tính muộn, dùng `disallowChanges`.
9. **Tránh sửa bừa**: không thay `get` thành `getOrNull` chỉ để giấu thiếu dữ liệu, không bỏ annotation `@Input` để né lỗi, và không bật/tắt Configuration Cache như giải pháp cho sai vòng đời.

Lệnh kiểm tra:

~~~bash
./gradlew -q help --no-configuration-cache
./gradlew -q printMode --no-configuration-cache
./gradlew -q printMode -Pmode=production --no-configuration-cache
./gradlew printMode -Pmode=production --configuration-cache
./gradlew printMode -Pmode=production --configuration-cache
~~~

Trong ví dụ `PrintMode`, hai lệnh chạy với cùng giá trị `-Pmode=production` được kỳ vọng in `MODE=production` khi action thực thi. Thông báo Configuration Cache tái sử dụng hay bị vô hiệu hóa phụ thuộc build và môi trường; không suy từ việc output giống nhau rằng chắc chắn cache hit.

## 18. Checklist áp dụng trong code review

- [ ] Property có kiểu chính xác và `convention` hợp lý; user/plugin khác còn cơ hội override trước khi lock.
- [ ] `get()` chỉ dùng khi thực sự cần giá trị; với task input thì nối provider ở configuration và đọc trong task action.
- [ ] Không đồng nhất `get` với final hóa; không đồng nhất `disallowChanges` với snapshot.
- [ ] `finalizeValue()` chỉ được gọi khi mọi cấu hình hợp lệ đã xong và muốn chốt giá trị **ngay**.
- [ ] `finalizeValueOnRead()` được dùng khi muốn chốt **lúc đọc**, nhưng đã kiểm soát không có read sớm bất ngờ.
- [ ] `disallowChanges()` được dùng khi phải khóa **nguồn** mà vẫn cho provider upstream hoạt động.
- [ ] Không tự lock task input quá sớm; Gradle thường tự final hóa khi task bắt đầu execution.
- [ ] `@Input`, `@InputFile`, `@OutputFile`... phản ánh đúng dữ liệu dùng/sinh ở task.
- [ ] Không truy vấn task output trước khi producer chạy, không dùng finalize làm thay nhiệm vụ của task dependency.
- [ ] Không gửi mutable object được chia sẻ qua provider rồi tin rằng property final sẽ deep-freeze object.
- [ ] Kiểm tra cả cache hit/miss, nguồn absent và input thay đổi, thay vì chỉ chạy một lần với giá trị mặc định.

## 19. Câu hỏi tự kiểm tra

1. **`p.get()` có khiến `p.set(...)` sau đó tự động bị cấm không?** Không, nếu `p` là property bình thường chưa có cơ chế final hóa/khóa khác. `get` đọc giá trị tại lúc gọi.
2. **`p.finalizeValue()` có tiếp tục theo dõi nguồn provider không?** Không. Nó lấy snapshot và bỏ nguồn, đồng thời cấm sửa property.
3. **`p.disallowChanges()` có tự tính giá trị provider tốn kém không?** Không. Nó chặn thay đổi trực tiếp nhưng để upstream cung cấp giá trị khi cần.
4. **Khi `p` đã disallowChanges mà nguồn upstream đổi, `p.get()` có thể đổi theo không?** Có, trước khi property được final hóa và nếu provider nguồn thực sự thay đổi.
5. **`p.finalizeValueOnRead()` có bảo đảm không final hóa ở configuration không?** Không. Nếu ai đó đọc trong configuration, lần đọc đó có thể chốt giá trị ngay.
6. **`get()` trên provider absent làm gì?** Ném ngoại lệ; muốn default thì dùng `orElse`/`convention` theo trường hợp.
7. **Gọi `get()` trong `tasks.register { }` là execution hay configuration?** Nó diễn ra khi task được cấu hình/hiện thực, chưa phải `@TaskAction`/`doLast`.
8. **Task input property có nên sửa trong `@TaskAction` sau khi Gradle tính cache fingerprint?** Không. Task action đọc input đã khai báo và tạo output, không thay đổi input.
9. **`finalizeValue()` có biến mọi object mutable thành immutable không?** Không. Nó chốt giá trị property nhưng không tự deep-freeze mọi object bên trong.
10. **Muốn khóa nguồn ngay nhưng tránh tính giá trị đến khi cần, dùng gì?** `disallowChanges()`; có thể kết hợp `finalizeValueOnRead()` nếu muốn snapshot ở lần đọc đầu tiên.

## Tài liệu chính thức

- [Gradle — Configuring Tasks Lazily / Provider API](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Property`, `Provider`, `set`, `convention`, lazy evaluation và khóa giá trị.
- [Gradle Java API — Provider](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/Provider.html): `get`, `getOrNull`, `getOrElse`, `isPresent`, `map`, `flatMap` và semantics.
- [Gradle Java API — Property](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/Property.html): `set`, `convention`, `finalizeValue`.
- [Gradle Java API — HasConfigurableValue](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/HasConfigurableValue.html): `finalizeValue`, `finalizeValueOnRead`, `disallowChanges`, `disallowUnsafeRead` và lý do chốt tại execution.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): cấu hình được lưu/tái sử dụng, input và tính tương thích của build logic.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): `@TaskAction`, input/output annotations, task caching.
