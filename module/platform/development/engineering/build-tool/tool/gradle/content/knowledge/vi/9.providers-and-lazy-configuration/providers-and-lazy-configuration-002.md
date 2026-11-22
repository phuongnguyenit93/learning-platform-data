# Provider, Property và mô hình giá trị chưa được tính ngay trong Gradle

## 1. Vấn đề: khai báo giá trị trước, sử dụng khi cần

Một bản build có nhiều giá trị chưa thể hoặc chưa cần tính ngay lúc đọc `build.gradle.kts`: đường dẫn file sẽ được task khác sinh ra, tên phiên bản nhận từ tham số dòng lệnh, thư mục đầu ra do cấu hình quyết định, hay dữ liệu chỉ cần khi task thực thi. Nếu tính tất cả ngay, cấu hình build chậm, khó liên kết task với nhau và dễ sử dụng nhầm dữ liệu chưa tồn tại.

Gradle giải quyết bằng mô hình **giá trị được cung cấp theo nhu cầu** (lazy value). Hai giao diện trung tâm là:

- **`Provider<T>`:** biểu diễn một giá trị thuộc kiểu `T` mà nơi sử dụng có thể đọc khi cần. Giá trị có thể đến từ cấu hình, một phép biến đổi hoặc output của task.
- **`Property<T>`:** một loại `Provider<T>` cho phép **bên cấu hình** chỉ định nguồn giá trị bằng `set`, giá trị mặc định bằng `convention` và kiểm soát trạng thái hoàn thiện của giá trị.

Dấu `T` là tham số kiểu: `Provider<String>` cung cấp chuỗi, `Provider<Int>` cung cấp số nguyên; `RegularFileProperty` là một loại property chuyên biệt mô tả file, không phải chuỗi đường dẫn.

Nhìn tổng thể:

```text
Tham số build / Gradle property / môi trường / task output
                     |
                     v
              Provider<T> nguồn
                     |
              map / flatMap / zip
                     |
                     v
             Provider<U> kết quả
                     |
              Property<U>.set(...)
                     |
                     v
              Input của task nhận U
                     |
                     v
              @TaskAction sử dụng U
                     |
                     v
           Output được khai báo rõ ràng
```

Tư duy quan trọng là **mô tả nguồn và quan hệ của dữ liệu trước khi yêu cầu giá trị cụ thể**. Trì hoãn không có nghĩa Gradle cam kết giá trị chỉ được tính trong `@TaskAction`: khi một thành phần thực sự cần đọc giá trị, Gradle có thể phải tính sớm hơn. Không nên xem một provider là bộ nhớ đệm bảo đảm chỉ tính đúng một lần.

## 2. Phân biệt ba ý tưởng “lười” thường bị trộn lẫn

Trong Gradle có nhiều cơ chế trì hoãn, nhưng chúng giải những bài toán khác nhau:

| Cơ chế | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Lazy value (Provider API)** | Lấy giá trị này từ đâu, khi nào mới cần biết nó? | `providers.gradleProperty("message")`, `provider.map { ... }` |
| **Configuration avoidance** | Có cần hiện thực hóa/cấu hình đối tượng task này ngay không? | `tasks.register<Copy>(...)`, `tasks.named<Copy>(...)` |
| **Up-to-date check/build cache** | Có cần làm lại công việc hoặc khôi phục output không? | Input/output của task so với kết quả đã có |

Một task được đăng ký theo nhu cầu vẫn có thể chứa một property có giá trị đã biết. Ngược lại, một task đã được cấu hình có thể giữ provider mà giá trị chưa được truy xuất. Khi task thực thi, nó có thể bị bỏ qua nếu đầu vào/đầu ra cho thấy không cần chạy. **Ba khái niệm liên quan nhưng không thay thế nhau**.

Ví dụ:

```kotlin
val messageSource = providers.gradleProperty("message")
val formattedMessage = messageSource.map { it.uppercase() }

tasks.register("showMessage") {
    doLast {
        println(formattedMessage.getOrElse("CHƯA CÓ MESSAGE"))
    }
}
```

- `providers.gradleProperty` tạo nguồn dữ liệu cho thuộc tính có tên `message`.
- `map` mô tả phép biến đổi, không phải lời gọi lập tức cần kết quả.
- `tasks.register` đăng ký task `showMessage` theo nhu cầu.
- `getOrElse` xuất hiện trong hành động task, nên chỉ ở đó ví dụ mới yêu cầu chuỗi để in.

Đoạn mã trên có thể đặt vào `build.gradle.kts` độc lập với các plugin ngoài; ta sẽ xây dựng một bài thực hành đầy đủ hơn ở mục 9. `getOrElse` là cách đọc có giá trị dự phòng, nhưng nếu thiếu giá trị là lỗi cấu hình, nên dùng `get()` và báo lỗi rõ ràng.

## 3. `Provider<T>` thực chất hứa điều gì?

Một `Provider<T>` cung cấp giao diện **đọc** một giá trị có kiểu. Nó có thể đại diện cho:

- Một giá trị đã có: `providers.provider { "Xin chào" }`.
- Một thuộc tính dự án: `providers.gradleProperty("course")`.
- Một biến môi trường: `providers.environmentVariable("COURSE_NAME")`.
- Một thư mục/file do Gradle cung cấp: `layout.buildDirectory.dir("generated")`.
- Một giá trị sinh từ provider khác qua `map`, `flatMap` hoặc `zip`.
- Một thuộc tính đầu ra trên task, được truy cập thông qua `TaskProvider`.

`Provider<T>` không có `set` vì đối tượng tiêu thụ không được sửa nguồn của nó. Đây là sự phân tách trách nhiệm hữu ích: **người tạo dữ liệu** định nghĩa giá trị; **người dùng dữ liệu** nhận provider và đọc/kết nối nó.

Trong Kotlin DSL:

```kotlin
import org.gradle.api.provider.Provider

val course: Provider<String> =
    providers.gradleProperty("course").orElse("Gradle")

val title: Provider<String> =
    course.map { name -> "Hoc $name" }
```

Nếu chạy Gradle với `-Pcourse=Java`, provider `title` có thể cung cấp `Hoc Java`; nếu thiếu `course`, nó cung cấp `Hoc Gradle`.

**Những thao tác thường gặp:**

| API | Ý nghĩa |
| --- | --- |
| `get()` | Yêu cầu giá trị. Nếu provider không có giá trị, thường gây lỗi |
| `getOrNull()` | Trả giá trị hoặc `null` nếu không có |
| `getOrElse(fallback)` | Đọc giá trị hoặc trả giá trị dự phòng |
| `isPresent` | Kiểm tra provider hiện có giá trị hay không |
| `orElse(fallback)` | Tạo **provider khác** có phương án dự phòng nếu nguồn vắng |
| `map { value -> ... }` | Tạo provider mới từ phép biến đổi giá trị |
| `flatMap { value -> anotherProvider }` | Tạo provider mới khi phép biến đổi trả về provider |
| `zip(other) { a, b -> ... }` | Kết hợp hai provider thành một provider khác |

Lưu ý sự khác nhau giữa `getOrElse` và `orElse`:

- `messageProvider.getOrElse("mặc định")` **đọc ngay tại điểm gọi** và trả về `String`.
- `messageProvider.orElse("mặc định")` trả về **`Provider<String>` mới**, giữ cách biểu diễn dữ liệu theo nhu cầu.

Trường hợp “vắng giá trị” không đồng nghĩa chuỗi trống. Nếu `-Pcourse=` được truyền với giá trị rỗng, đó vẫn là một chuỗi có giá trị; `orElse("Gradle")` không tự biến chuỗi rỗng thành chữ “Gradle”. Nếu muốn xử lý chuỗi rỗng hoặc toàn khoảng trắng, phải biểu đạt điều kiện tương ứng bằng phép biến đổi riêng.

## 4. `Property<T>`: nguồn giá trị có thể được cấu hình

`Property<T>` kế thừa giao diện `Provider<T>` và thêm cơ chế **gán/cấu hình**. Đây là lý do các kiểu task và extension trong Gradle thường công bố property thay vì một biến Java/Kotlin thông thường.

Ví dụ về khái niệm với một đối tượng extension:

```kotlin
import org.gradle.api.provider.Property

abstract class LessonOptions {
    abstract val title: Property<String>
}

val options = extensions.create("lessonOptions", LessonOptions::class.java)

options.title.convention("Khoa hoc Gradle")
options.title.set("Provider va Property")
```

Ở đây, Gradle có thể tạo thực thể cho lớp trừu tượng và quản lý property. `convention` biểu thị **mặc định**, còn `set` biểu thị lựa chọn tường minh. Khi cả hai tồn tại, giá trị được `set` tường minh có ưu tiên cao hơn `convention`.

Phân biệt chính xác:

| API trên Property | Tác dụng |
| --- | --- |
| `set(value)` | Cấu hình giá trị trực tiếp hoặc nguồn provider |
| `convention(value)` | Cung cấp giá trị mặc định khi chưa có giá trị tường minh |
| `unset()` | Bỏ giá trị tường minh đã gán; nếu có convention, nó có thể được sử dụng |
| `get()` | Đọc giá trị theo hợp đồng `Provider<T>` |
| `finalizeValue()` | Chốt giá trị hiện tại và không cho thay đổi property về sau |
| `finalizeValueOnRead()` | Yêu cầu chốt giá trị khi nó được đọc lần đầu |
| `disallowChanges()` | Ngăn thay đổi thêm cấu hình property; không đồng nghĩa với việc tính/chốt ngay giá trị nguồn |

Những phương thức chốt cấu hình cần dùng **có chủ ý**: nếu chốt quá sớm, đoạn cấu hình chạy sau đó có thể gặp lỗi vì không còn được thay đổi property. Trong plugin, thời điểm chốt nên phù hợp với lúc hợp đồng cấu hình đã hoàn tất.

### 4.1. `set` với giá trị và với provider

Hai cách có nghĩa khác nhau về dòng dữ liệu:

```kotlin
// Cách 1: gán trực tiếp.
options.title.set("Java 17")

// Cách 2: lấy nguồn từ cấu hình bên ngoài.
options.title.set(
    providers.gradleProperty("lessonTitle").orElse("Java 17")
)
```

Cách 1 gán trực tiếp chuỗi. Cách 2 thiết lập **quan hệ giữa Property và Provider**: giá trị được đọc từ nguồn theo hợp đồng provider. Không cần gọi `get()` để chuyển nó thành chuỗi ngay trong lúc cấu hình.

Nếu `options.title.convention(...)` đã được áp dụng, `set(provider)` vẫn là giá trị tường minh và có ưu tiên theo quy tắc property. Đây là kỹ thuật phổ biến để plugin đặt mặc định, còn project tiêu thụ có quyền ghi đè.

### 4.2. `convention` không phải là một lần gán bắt buộc

Giả sử task có property:

```kotlin
abstract class SayHello : org.gradle.api.DefaultTask() {
    @get:org.gradle.api.tasks.Input
    abstract val name: Property<String>

    @org.gradle.api.tasks.TaskAction
    fun sayHello() {
        println("Hello, " + name.get())
    }
}
```

Trong `build.gradle.kts`, sau khi có import `Property` như ở trên:

```kotlin
tasks.register<SayHello>("sayHello") {
    name.convention("Gradle")
}
```

Nếu chạy `./gradlew -q sayHello`, action in:

```text
Hello, Gradle
```

Nếu sau đó một cấu hình tường minh gọi `name.set("Java")` trước khi property bị chốt, cùng task sẽ in `Hello, Java`. **Không nên đặt `name.get()` ở phần cấu hình chỉ để “xác nhận” tên**: việc đọc sớm có thể ảnh hưởng tính trì hoãn hoặc dẫn tới ràng buộc sai khi build còn chưa cấu hình xong.

## 5. Các Property chuyên biệt cho dữ liệu build

Thay vì coi mọi thứ là `Property<String>`, Gradle có các biến thể diễn tả chính xác loại dữ liệu:

| Kiểu | Giá trị biểu diễn | Dùng khi |
| --- | --- | --- |
| `Property<String>` | Chuỗi | Tên module, thông điệp, tùy chọn |
| `Property<Boolean>` | Boolean | Công tắc hành vi của task |
| `Property<Int>` | Số nguyên Kotlin | Số lần thử, số lượng, phiên bản dạng số khi phù hợp |
| `ListProperty<String>` | Danh sách chuỗi | Danh sách tham số hoặc tên mục tiêu |
| `SetProperty<String>` | Tập hợp không trùng lặp | Các nhãn/tính năng |
| `MapProperty<String, String>` | Bản đồ khóa–giá trị | Metadata có cấu trúc |
| `DirectoryProperty` | Một thư mục theo mô hình file của Gradle | Thư mục đầu vào/đầu ra |
| `RegularFileProperty` | Một file theo mô hình file của Gradle | File cấu hình, artifact, file kết quả |
| `ConfigurableFileCollection` | Tập hợp file có thể cấu hình | Nhiều file nguồn/đầu vào |

`DirectoryProperty` và `RegularFileProperty` không phải chỉ là cách viết đẹp hơn cho chuỗi đường dẫn. Chúng cho Gradle biết giá trị mang ý nghĩa file hoặc directory và có thể kết hợp với `ProjectLayout`/provider, tạo điều kiện tốt hơn cho kết nối dữ liệu và task input/output.

Ví dụ trong một lớp task tùy chỉnh:

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class WriteNote : DefaultTask() {
    @get:Input
    abstract val note: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun writeNote() {
        val target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText(note.get() + "\n", Charsets.UTF_8)
    }
}
```

Đây là **định nghĩa kiểu task**, chưa tự đăng ký task nào. Khối `@TaskAction` là nơi hợp lý để gọi `get()` và thao tác file. Khi đăng ký task, có thể cấu hình:

```kotlin
tasks.register<WriteNote>("writeNote") {
    note.convention("Provider API")
    outputFile.set(layout.buildDirectory.file("notes/note.txt"))
}
```

Đây là hai đoạn được ghép vào `build.gradle.kts` cùng phạm vi với nhau (các import xuất hiện trước `plugins` nếu script có). Khi chạy `writeNote`, file thường nằm trong `build/notes/note.txt`. Output được đánh dấu `@OutputFile`, giúp Gradle biết đây là kết quả task quản lý. Phần thực hành đầy đủ mục 9 phát triển ý tưởng này thành hai task kết nối với nhau.

## 6. Biến đổi provider bằng `map`, `flatMap` và `zip`

Hãy xem provider như một **đồ thị dữ liệu**: một giá trị có thể phụ thuộc vào giá trị khác, nhưng mã dùng nó không cần tự tính mọi thành phần ngay tại thời điểm cấu hình.

### 6.1. `map`: biến đổi một giá trị

```kotlin
val baseName = providers.gradleProperty("artifactName")
    .orElse("lesson")

val upperName = baseName.map { it.uppercase() }
val fileName = baseName.map { it + ".txt" }
```

Các biến `upperName` và `fileName` vẫn là provider. Việc viết `map` thường mô tả hàm biến đổi sẽ dùng khi giá trị được yêu cầu; nó không biến kết quả thành `String` ngay.

Nếu chạy với `-PartifactName=guide` thì `upperName` có thể cho `GUIDE` và `fileName` cho `guide.txt`. Khi chạy không có thuộc tính, giá trị dự phòng `lesson` được dùng.

**Tránh tác dụng phụ bên trong `map`** như ghi file, gửi HTTP hay thay đổi dữ liệu. Gradle có quyền yêu cầu giá trị khi cần và có thể yêu cầu nhiều lần; `map` phù hợp cho phép biến đổi dữ liệu thuần.

### 6.2. `flatMap`: đi từ giá trị đến một provider khác

`map` phù hợp khi hàm trả một giá trị thường; `flatMap` phù hợp khi hàm trả về một **`Provider<U>`**.

```kotlin
val outputDirectory = layout.buildDirectory.dir("generated")

val outputFile =
    outputDirectory.map { dir -> dir.file("message.txt") }
```

Ở đoạn này `map` là đủ vì `dir.file(...)` tạo một `RegularFile`, không phải một provider khác.

Tình huống cần `flatMap` xuất hiện khi đọc property của một task được cung cấp theo nhu cầu:

```kotlin
val producer = tasks.named<WriteNote>("writeNote")
val noteFile = producer.flatMap { it.outputFile }
```

`producer` là `TaskProvider<WriteNote>`, còn `it.outputFile` là `RegularFileProperty`, tức một provider của file. `flatMap` tạo một `Provider<RegularFile>` mới mà không ép lấy đối tượng task ngay bằng `producer.get()`.

Quan hệ từ task provider đến property output có thể mang thông tin phụ thuộc task, giúp Gradle biết task nào tạo file. Xem ví dụ producer–consumer đầy đủ ở mục 9.

### 6.3. `zip`: kết hợp hai nguồn

```kotlin
val first = providers.gradleProperty("first").orElse("Hello")
val second = providers.gradleProperty("second").orElse("Gradle")

val greeting = first.zip(second) { a, b -> "$a $b" }
```

`greeting` là provider của chuỗi tổng hợp. Đây là cách tốt để cấu trúc kết quả phụ thuộc hai thông số mà không gọi `first.get()` và `second.get()` khi cấu hình.

Lưu ý: nếu một trong hai provider nguồn vắng giá trị và không có phương án dự phòng, provider kết quả có thể không có giá trị tùy phép biến đổi; dùng `orElse` đúng nơi cần mặc định. Nếu việc thiếu nguồn là lỗi nghiệp vụ, đừng che giấu bằng giá trị dự phòng không có ý nghĩa.

### 6.4. Khi nào truy xuất thực sự diễn ra?

`Provider` mô tả **cách lấy** và **nguồn của** giá trị. Giá trị có thể cần để:

- Gradle xác định input/output và trạng thái task;
- Gradle cấu hình một phần mô hình build có yêu cầu giá trị cụ thể;
- Hành động `@TaskAction` thực thi;
- Một đoạn mã build chủ động gọi `get()`, `getOrNull()` hoặc `getOrElse()`.

Vì vậy phát biểu “`map` chỉ chạy trong execution” là **không chính xác**. Nó chạy khi giá trị được yêu cầu, và thời điểm đó phụ thuộc người tiêu thụ và cách Gradle xây dựng kế hoạch.

## 7. Nguồn provider từ Gradle: tham số, biến môi trường và đường dẫn

### 7.1. Tham số project

`providers.gradleProperty("message")` tìm project property có tên `message`, ví dụ truyền qua dòng lệnh:

```bash
./gradlew showGreeting -Pmessage="Xin chao"
```

Một file `gradle.properties` phù hợp cũng có thể cung cấp giá trị, tùy cách cấu hình và độ ưu tiên nguồn thuộc tính. Ưu điểm là build script không cần cố định thông điệp trong mã.

```kotlin
val messageFromCommandLine =
    providers.gradleProperty("message").orElse("Xin chào từ Provider!")
```

Đây vẫn là `Provider<String>`. Khi tham số thay đổi, task dùng giá trị đó như một `@Input` có thể nhận diện sự khác biệt đầu vào và thực hiện lại công việc.

### 7.2. Biến môi trường

```kotlin
val localeName =
    providers.environmentVariable("COURSE_LOCALE").orElse("vi")
```

Đây là một nguồn cấu hình có thể tái sử dụng với cơ chế tracking tương thích trong Gradle. Không ghi giá trị bí mật ra console hoặc file output chỉ để kiểm tra provider; nếu một token đi vào output hoặc report build, nó có thể bị lộ cho người đọc artifact/log.

### 7.3. Đường dẫn qua `ProjectLayout`

```kotlin
val destinationDirectory =
    layout.buildDirectory.dir("generated")
val destinationFile =
    layout.buildDirectory.file("generated/message.txt")
val sourceFile =
    layout.projectDirectory.file("docs/guide.txt")
```

Các loại không giống nhau:

- `destinationDirectory` là `Provider<Directory>`.
- `destinationFile` là `Provider<RegularFile>`.
- `sourceFile` là `RegularFile` tham chiếu một file dưới project directory.

Khi task nhận `RegularFileProperty`, dùng `outputFile.set(destinationFile)`. Khi API nhận file collection hoặc path provider, đưa đúng loại mà API yêu cầu. Việc truy cập đường dẫn trong task nên dùng `.get().asFile` lúc thực sự thao tác trên file.

**Tránh hard-code** thư mục `build` bằng nối chuỗi như `"$projectDir/build/..."`. Khi project tùy biến `layout.buildDirectory`, dùng API layout giúp output đi theo cấu hình đó.

## 8. `TaskProvider<T>`: giá trị tham chiếu đến một task được đăng ký

`TaskProvider<T>` là một dạng `Provider<T>` dành cho task. Nó cho phép viết:

```kotlin
val copyDocs = tasks.register<Copy>("copyDocs") {
    from(layout.projectDirectory.file("docs/guide.txt"))
    into(layout.buildDirectory.dir("docs"))
}
```

`copyDocs` chưa phải việc sao chép đã xảy ra; nó là **tham chiếu đến task có tên `copyDocs` và kiểu `Copy`**. Gradle có thể trì hoãn việc hiện thực hóa task đến khi nó cần được cấu hình/thực thi.

Để một task khác cần `copyDocs`:

```kotlin
tasks.register("prepareDocs") {
    dependsOn(copyDocs)
}
```

`dependsOn` biểu diễn quan hệ **công việc phải được xử lý trước**. Trong khi đó, `flatMap { it.outputFile }` trong ví dụ producer–consumer biểu diễn **giá trị file mà task trước cung cấp cho task sau**. Nếu liên kết bằng output provider mang thông tin task producer, Gradle có thể suy ra phụ thuộc thực thi thay vì phải khai báo `dependsOn` thủ công.

Phân biệt API:

| API | Khi nào dùng |
| --- | --- |
| `tasks.register<MyTask>("name")` | Tạo task mới theo nhu cầu |
| `tasks.named<MyTask>("name")` | Lấy provider của task đã đăng ký |
| `tasks.withType<MyTask>().configureEach { ... }` | Cấu hình quy tắc cho các task có kiểu phù hợp |
| `taskProvider.configure { ... }` | Cấu hình task qua provider |
| `taskProvider.get()` | Lấy đối tượng task thật khi thực sự cần; tránh dùng sớm |
| `taskProvider.flatMap { it.outputFile }` | Nối task với một property/output có kiểu |

**Trì hoãn cấu hình task và trì hoãn tính giá trị là hai tầng khác nhau.** Tham chiếu `TaskProvider` không bắt buộc hiện thực hóa task. Tham chiếu `Property<T>` không bắt buộc đọc ngay giá trị. Kết hợp hai cơ chế giúp dự án lớn tránh cấu hình công việc không liên quan và giúp Gradle hiểu luồng dữ liệu.

## 9. Bài thực hành hoàn chỉnh: hai task trao đổi file bằng Provider API

Đây là ví dụ **Gradle Kotlin DSL độc lập**. Nó chứng minh năm việc: một property có giá trị mặc định; truyền tham số `-P`; dùng `@Input` và `@OutputFile`; truyền output file từ task producer sang consumer bằng `flatMap`; và đọc giá trị đúng thời điểm.

### 9.1. Cây thư mục

```text
provider-demo/
├── settings.gradle.kts
└── build.gradle.kts
```

Không cần tạo sẵn thư mục `build` hay file đầu ra. Cần một phiên bản Gradle tương thích với Kotlin DSL hiện đại (ví dụ Gradle 8.5+) và JDK mà phiên bản Gradle đó hỗ trợ chạy. Nếu đã có Wrapper của dự án, dùng Wrapper; nếu thư mục mới chưa có, máy phải có Gradle cài sẵn để chạy `gradle wrapper` một lần.

**File `settings.gradle.kts`:**

```kotlin
rootProject.name = "provider-demo"
```

**File `build.gradle.kts` (toàn bộ):**

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    base
}

abstract class GenerateGreeting : DefaultTask() {
    @get:Input
    abstract val greeting: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText(greeting.get() + "\n", Charsets.UTF_8)
        println("[GENERATE] " + target.name)
    }
}

abstract class ShowGreeting : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val inputFile: RegularFileProperty

    @TaskAction
    fun show() {
        val text = inputFile.get().asFile.readText(Charsets.UTF_8).trim()
        println("[SHOW] " + text)
    }
}

val generateGreeting = tasks.register<GenerateGreeting>("generateGreeting") {
    group = "learning"
    description = "Ghi loi chao vao file sinh ra boi Gradle"

    greeting.convention(
        providers.gradleProperty("message").orElse("Xin chào từ Provider!")
    )
    outputFile.convention(
        layout.buildDirectory.file("generated/greeting.txt")
    )
}

tasks.register<ShowGreeting>("showGreeting") {
    group = "learning"
    description = "Doc loi chao tu output cua task truoc"

    inputFile.set(generateGreeting.flatMap { it.outputFile })
}
```

### 9.2. Giải thích từng quan hệ

Trong `GenerateGreeting`:

- `@get:Input` đánh dấu `greeting: Property<String>` là **đầu vào** của task. Khi giá trị chuỗi thay đổi, Gradle có dữ liệu để kiểm tra task cần chạy lại.
- `@get:OutputFile` đánh dấu `outputFile: RegularFileProperty` là **file đầu ra**. Task tạo file khi action `generate` chạy.
- `@TaskAction` đặt công việc ghi file ở **giai đoạn thực thi**, không ghi file lúc cấu hình.
- `greeting.convention(...)` đặt nguồn mặc định. `providers.gradleProperty("message")` có thể lấy từ tham số `-Pmessage=...`; nếu vắng, `orElse` cung cấp lời chào dự phòng.
- `layout.buildDirectory.file(...)` tạo provider của vị trí đầu ra tương ứng với build directory được cấu hình.

Trong `ShowGreeting`:

- `@get:InputFile` mô tả file cần đọc.
- `@get:PathSensitive(PathSensitivity.RELATIVE)` cho Gradle biết cách xét đường dẫn tương đối của input khi tính trạng thái đầu vào. Đây là một lựa chọn phù hợp khi tính di động của đường dẫn quan trọng; lựa chọn thật trong plugin phải phù hợp bản chất dữ liệu.
- `inputFile.set(generateGreeting.flatMap { it.outputFile })` kết nối provider của **file do producer tạo** với property đầu vào của consumer.
- Task consumer không cần tự đi tìm một chuỗi đường dẫn hard-code hoặc gọi `generateGreeting.get()` khi cấu hình.

Dòng kết nối quan trọng nhất:

```kotlin
inputFile.set(generateGreeting.flatMap { it.outputFile })
```

Nó nói: “File đầu vào của `showGreeting` là file đầu ra được công bố bởi `generateGreeting`”. Khi Gradle xử lý task consumer, thông tin task producer được gắn với output provider cho phép Gradle suy ra quan hệ thực thi cần thiết.

### 9.3. Chạy lệnh và kết quả

Nếu chưa có Wrapper, có thể chạy `gradle wrapper` bằng một bản Gradle cài sẵn tương thích, rồi dùng script Wrapper vừa sinh. Trên Linux/macOS:

```bash
./gradlew -q showGreeting
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat -q showGreeting
```

Khi chưa có output và không truyền property `message`, các dòng do hai task in ra theo thứ tự là:

```text
[GENERATE] greeting.txt
[SHOW] Xin chào từ Provider!
```

Sau đó tồn tại file `build/generated/greeting.txt` với nội dung lời chào và một ký tự xuống dòng cuối. Output từ Gradle/Daemon khi chạy lần đầu có thể thêm thông báo môi trường; các dòng trên là output do **action trong ví dụ** in ra khi cả hai action chạy.

Nếu chạy **lần thứ hai** với đầu vào/đầu ra không đổi, `generateGreeting` thường được đánh dấu `UP-TO-DATE` và không in `[GENERATE]`. `showGreeting` không khai báo output và có hành động in console, nên vẫn in dòng `[SHOW]` khi được thực thi. Chạy không có `-q` để quan sát trạng thái task:

```bash
./gradlew showGreeting --console=plain
```

Đổi giá trị lời chào:

```bash
./gradlew -q showGreeting -Pmessage="Chao Gradle"
```

Ở Windows PowerShell:

```powershell
.\gradlew.bat -q showGreeting -Pmessage="Chao Gradle"
```

Vì giá trị `@Input` thay đổi so với kết quả trước đó, producer cần cập nhật nội dung. Khi producer thực thi, phần output do action in là:

```text
[GENERATE] greeting.txt
[SHOW] Chao Gradle
```

Thay đổi này không cần sửa mã Kotlin DSL: nguồn property của task đã được kết nối với project property thông qua provider.

### 9.4. Kiểm chứng thứ tự và file

```bash
./gradlew showGreeting --dry-run --console=plain
```

Ở chế độ dry-run, Gradle dự kiến hiển thị `:generateGreeting` trước `:showGreeting`. Hai action sẽ không chạy, nên không có output `[GENERATE]`/`[SHOW]` từ ví dụ. Dòng `SKIPPED` trong dry-run do **chế độ mô phỏng**, không chứng minh task thật đã `UP-TO-DATE`.

Đọc file output thực sự sau khi chạy không ở chế độ dry-run:

- Linux/macOS: `cat build/generated/greeting.txt`.
- PowerShell: `Get-Content build/generated/greeting.txt`.

Muốn chắc chắn tạo lại output từ đầu trong ví dụ có plugin `base`:

```bash
./gradlew clean showGreeting --console=plain
```

Task `clean` xóa thư mục đầu ra build được quản lý; `showGreeting` có đầu vào nối với producer, nên file được sinh lại trước khi consumer đọc.

### 9.5. Không có `dependsOn` tường minh mà vẫn đúng thứ tự vì sao?

Nếu consumer chỉ khai báo:

```kotlin
inputFile.set(
    layout.buildDirectory.file("generated/greeting.txt")
)
```

nó **chỉ biết đường dẫn file**, không còn tham chiếu đến output của producer. Khi đó Gradle không có đầy đủ thông tin để suy ra producer phải được xử lý trước consumer. File có thể không tồn tại hoặc vô tình còn lại từ build trước.

Dòng chuẩn trong bài thực hành:

```kotlin
inputFile.set(generateGreeting.flatMap { it.outputFile })
```

giữ quan hệ producer–output–consumer. Trong các trường hợp không thể nối qua provider có thông tin task, ta có thể phải khai báo `dependsOn(generateGreeting)` riêng. Nhưng **thứ tự task một mình chưa mô tả đầy đủ dữ liệu**: consumer vẫn nên có input được đánh dấu đúng, còn producer vẫn nên công bố output.

## 10. Kết nối Property API với Java plugin và Java 17

Provider API không chỉ dành cho task tự viết. Plugin Java của Gradle cũng dùng mô hình property để cấu hình toolchain và task.

Ví dụ `build.gradle.kts` trong **một project Java riêng**:

```kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}
```

Các điểm cần hiểu:

- `java.toolchain.languageVersion` là một property có kiểu liên quan phiên bản Java, và `set(JavaLanguageVersion.of(17))` cấu hình giá trị tường minh.
- `options.release` trên `JavaCompile` là một property phục vụ lựa chọn API/bytecode Java khi compiler hỗ trợ. Khác với việc chỉ đặt chuỗi `"17"` không có ngữ nghĩa.
- `tasks.withType<JavaCompile>().configureEach` cấu hình theo nhu cầu cho các task biên dịch Java thuộc kiểu đó; không tự thực thi chúng.
- Project cần toolchain JDK 17 có sẵn hoặc cơ chế cấp phát toolchain được cấu hình phù hợp. File Java 17 chỉ được biên dịch khi task thích hợp được yêu cầu.

Nếu đặt `src/main/java/demo/Main.java`:

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Provider khong thay the Java source");
    }
}
```

thì trên môi trường có JDK phù hợp, chạy:

```bash
./gradlew compileJava
java -cp build/classes/java/main demo.Main
```

Output do lệnh `java` chạy lớp `Main` in ra là:

```text
Provider khong thay the Java source
```

Ví dụ này cho thấy Property API cấu hình các **lựa chọn của quy trình build**. Nội dung Java nằm trong mã nguồn thực tế; nó không bị thay thế bởi provider. Provider giúp Gradle quản lý giá trị cấu hình, còn task vẫn thực hiện công việc biên dịch đã được khai báo.

## 11. Input/output, kiểm tra cập nhật và build cache

Một task muốn được Gradle theo dõi hiệu quả cần mô tả đầy đủ những thứ ảnh hưởng đến kết quả:

- **Input:** chuỗi, số, file, thư mục, danh sách hoặc dữ liệu khác mà action đọc để tạo kết quả.
- **Output:** file hoặc thư mục mà action tạo ra và Gradle có thể kiểm tra.
- **Quan hệ:** task sản xuất output nào, task khác tiêu thụ input nào.
- **Hành vi ổn định:** với cùng input và môi trường được khai báo, task nên tạo output tương đương.

Trong bài thực hành:

```text
-Pmessage="Chao Gradle"
          |
          v
providers.gradleProperty("message")
          |
          v
GenerateGreeting.greeting  (@Input)
          |
          v
GenerateGreeting.outputFile (@OutputFile)
          |
          v
ShowGreeting.inputFile      (@InputFile)
          |
          v
          [SHOW] Chao Gradle
```

**Up-to-date check:** khi input/output vẫn phù hợp, Gradle có thể bỏ qua action producer và hiển thị `UP-TO-DATE`. Nếu `@Input` thay đổi, file output bị xóa hoặc bị thay đổi so với trạng thái được theo dõi, Gradle có thể cần chạy lại task.

**Build cache:** có thể khôi phục output của các task đủ điều kiện nếu cache được bật và có kết quả tương ứng. Chỉ dùng `Provider`, `Property`, `@Input` và `@OutputFile` **không tự đảm bảo task tùy chỉnh được cache từ xa**; muốn khai báo task có thể cache còn phải xem xét `@CacheableTask`, tính đúng đắn của input/output và tính tái lập kết quả.

**Configuration cache:** lưu và tái sử dụng thông tin cấu hình tương thích, khác với build cache của output. Provider API giúp biểu diễn giá trị đầu vào cấu hình có cấu trúc, nhưng **không bảo đảm mọi task/plugin tương thích configuration cache**; ví dụ action truy cập đối tượng `Project` một cách không được hỗ trợ có thể gây vấn đề.

**Task không có output:** `ShowGreeting` in ra console và không khai báo output, nên không có một file output để Gradle xác nhận đã cập nhật theo cơ chế thông thường. Không cần thêm output giả chỉ để có trạng thái đẹp; nếu task thực sự chỉ in thông tin, đó là hành vi hợp lý. Với task sinh file, phải công bố output thật.

## 12. Khi nào nên gọi `get()`?

`get()` không phải API bị cấm. Nó cần thiết tại thời điểm thực sự tiêu thụ giá trị. Điều quan trọng là **đọc đúng thời điểm**.

Ví dụ phù hợp trong action:

```kotlin
@TaskAction
fun generate() {
    val destination = outputFile.get().asFile
    val text = greeting.get()
    destination.parentFile.mkdirs()
    destination.writeText(text, Charsets.UTF_8)
}
```

Đây là **một phương thức minh họa thuộc task có các property `outputFile` và `greeting`**, không phải file Kotlin độc lập. Nó dùng `get()` lúc action cần file và chuỗi để ghi.

Ví dụ cần cân nhắc ở cấp cấu hình:

```kotlin
val outputPath = layout.buildDirectory.file("generated/a.txt").get().asFile
```

Lệnh này ép lấy đối tượng `RegularFile` rồi `File` tại điểm cấu hình. Với một đường dẫn cố định, nó có thể vẫn chạy đúng; nhưng nếu nhiệm vụ là truyền đầu ra cho task, **giữ provider** cho đến khi task cần thường rõ ràng hơn:

```kotlin
val outputPath = layout.buildDirectory.file("generated/a.txt")
```

Không nên áp dụng một quy tắc tuyệt đối “mọi `get()` ở configuration đều lỗi”. Có lúc Gradle cần giá trị để quyết định cấu hình, và các API tài nguyên khác nhau có hợp đồng khác nhau. Hãy tự hỏi: “Ở dòng này, mình **cần giá trị thực** hay chỉ muốn **chuyển quan hệ giá trị** cho đối tượng khác?”. Nếu chỉ muốn kết nối dữ liệu, truyền provider.

Một lỗi khác là lạm dụng `providers.provider { ... }` để giấu thao tác có tác dụng phụ:

```kotlin
// Minh họa điều nên tránh: provider dùng để tạo file.
val unsafe = providers.provider {
    file("build/generated.txt").writeText("side effect")
    "done"
}
```

Provider nên mô tả giá trị và phép tính dữ liệu. Việc sinh file nên thuộc về task có `@TaskAction`, input/output được đánh dấu rõ, để Gradle điều phối và kiểm tra trạng thái được. Nếu cần chạy công cụ ngoài, hãy cân nhắc task hoặc API provider được Gradle thiết kế riêng, không tự đưa tác dụng phụ khó theo dõi vào hàm biến đổi.

## 13. Quản lý vòng đời của property: mặc định, ghi đè và chốt

Khi thiết kế một plugin, thứ tự cấu hình có thể như sau:

```text
Plugin tạo task/extension
       |
       v
Plugin đặt convention (mặc định)
       |
       v
Project tiêu thụ set(...) để ghi đè nếu muốn
       |
       v
Gradle đọc property để tính input hoặc thực thi
       |
       v
Property có thể được chốt theo chính sách phù hợp
```

Ví dụ:

```kotlin
val message =
    objects.property(String::class.java)

message.convention("mac dinh")
message.set(providers.gradleProperty("message").orElse("gia tri tuy chon"))
```

`objects.property(String::class.java)` là một cách lấy `Property<String>` từ `ObjectFactory` trong build logic. Khi đã dùng `set(provider)`, nó cung cấp nguồn tường minh; `convention` không tự ghi đè nguồn này. Nên đặt convention ở plugin, để project sử dụng plugin có cơ hội `set` giá trị của riêng mình.

Các API đóng băng giá trị thường có mục đích khác nhau:

- `finalizeValue()`: kết thúc cấu hình và chốt giá trị hiện có.
- `finalizeValueOnRead()`: đặt yêu cầu chốt khi property được đọc lần đầu.
- `disallowChanges()`: chặn cấu hình thay đổi thêm mà không buộc tính/chốt ngay nguồn giá trị giống `finalizeValue`.

Khi task hoặc plugin muốn đảm bảo không có cấu hình muộn làm thay đổi kết quả, các API này có thể hữu ích. Nhưng áp dụng không đúng thời điểm sẽ tạo lỗi kiểu “giá trị không thể thay đổi nữa”. Đừng dùng chúng như cách chữa chung cho lỗi provider chưa được cấu hình.

## 14. Những lỗi thường gặp và cách tìm đúng nguyên nhân

| Hiện tượng | Vì sao xảy ra | Hướng xử lý |
| --- | --- | --- |
| `Provider.get()` báo không có giá trị | Nguồn vắng, không có mặc định | Dùng `orElse`/`convention` nếu giá trị mặc định hợp lý; ngược lại báo lỗi cấu hình rõ ràng |
| `Property` báo chưa được thiết lập | Plugin/task chưa `set` hoặc `convention` | Cấu hình nguồn property trước khi task cần đọc |
| `set` sau khi property bị chốt gây lỗi | `finalizeValue`, `finalizeValueOnRead` hoặc `disallowChanges` đã áp dụng | Sửa thời điểm cấu hình hoặc chính sách chốt |
| `orElse("x")` không thay chuỗi rỗng | Nguồn có giá trị `""`, không phải vắng | Xử lý chuỗi trống bằng logic riêng |
| Build cấu hình chậm | Gọi `TaskProvider.get()` hoặc đọc provider quá sớm; logic khác tốn công | Truyền provider, dùng `register`/`named`/`configureEach`, đo lại |
| Consumer chạy trước khi producer tạo file | Chỉ truyền một đường dẫn thuần, không có phụ thuộc task | Liên kết input với output provider của task producer hoặc khai báo phụ thuộc đúng |
| Task sinh file không được `UP-TO-DATE` | Thiếu khai báo input/output, output thay đổi ngoài dự kiến | Dùng `@Input`, `@InputFile`, `@OutputFile` phù hợp, kiểm tra action |
| File bị ghi ra ngoài build directory mong muốn | Hard-code đường dẫn và bỏ qua `layout.buildDirectory` | Dùng `ProjectLayout` và property file có kiểu |
| Configuration cache không dùng được | Có logic không tương thích, ví dụ task action truy cập trạng thái project không được hỗ trợ | Tách cấu hình khỏi thực thi; đưa dữ liệu cần thiết vào task properties |
| `flatMap` bị khó hiểu | Hàm trả về `Provider` nhưng dùng `map`, tạo provider lồng nhau | Dùng `flatMap` khi hàm trả provider, `map` khi trả giá trị |
| Giá trị không thay đổi như mong muốn | Đã dùng `set` tường minh hoặc chốt property nên convention mới không có tác dụng | Xem nguồn đang có ưu tiên và thời điểm cấu hình |
| Thấy output cũ dù đổi tham số | Task không khai báo tham số làm input hoặc đang đọc file cũ | Đánh dấu input, kết nối nguồn qua provider, kiểm tra file output thật |
| In log nhiều lần từ phép biến đổi | Đặt `println`/tác dụng phụ trong `map`/provider | Để phép biến đổi thuần; in ở task action nếu cần thông báo |
| Nhầm `build cache` và `configuration cache` | Hai cache lưu những loại kết quả khác nhau | Phân biệt cache của cấu hình với cache output task |

### Cách điều tra theo từng bước

1. **Xác định nguồn:** giá trị đến từ `gradleProperty`, `environmentVariable`, `layout`, provider khác hay output của task?
2. **Xác định kiểu:** `Provider<String>`, `Property<String>`, `RegularFileProperty` hay `TaskProvider<T>`? Tránh chuyển mọi thứ thành `String` quá sớm.
3. **Xác định nơi đọc:** mã cấu hình đang `get()` hay task action đang tiêu thụ? Lời gọi sớm có thật sự cần không?
4. **Xác định quan hệ task:** input của consumer có nhận provider output của producer không? Có quan hệ bắt buộc nào chưa được khai báo không?
5. **Xác định input/output:** dữ liệu ảnh hưởng kết quả đã được đánh dấu chưa? File output có đúng vị trí không?
6. **Chạy lệnh kiểm chứng:** dùng `--dry-run` xem kế hoạch và `--info` xem lý do task chạy/bỏ qua; cuối cùng đọc file output thật.

Các lệnh minh họa với bài thực hành:

```bash
./gradlew tasks --all
./gradlew showGreeting --dry-run
./gradlew showGreeting --info --console=plain
./gradlew clean showGreeting
```

Lưu ý: `--dry-run` không chạy action, nên không xác nhận file đã tạo thành công; cần chạy thật để kết luận.

## 15. Thực hành bổ sung: tự thay đổi đồ thị dữ liệu

**Bài tập A — giá trị mặc định và giá trị tường minh.** Trong ví dụ mục 9, chạy `showGreeting` không có `-Pmessage`, rồi chạy với `-Pmessage="Hello"`. Chỉ ra thứ tự ưu tiên giữa `providers.gradleProperty` và `orElse`; vì sao thay đổi tham số khiến producer cần làm mới output?

**Bài tập B — thử một phép biến đổi.** Thay phần cấu hình `greeting` trong task producer thành:

```kotlin
greeting.convention(
    providers.gradleProperty("message")
        .orElse("Xin chào từ Provider!")
        .map { it.uppercase() }
)
```

Chạy `showGreeting` rồi so sánh nội dung file với bài gốc. `map` tạo một provider mới và phép chuyển chữ hoa trở thành một phần của dòng dữ liệu.

**Bài tập C — xem phụ thuộc ngầm.** Chạy `./gradlew showGreeting --dry-run`, ghi lại hai task. Sau đó thử thay dòng `inputFile.set(generateGreeting.flatMap { it.outputFile })` bằng đường dẫn `layout.buildDirectory.file("generated/greeting.txt")` trong **bản sao dự án**. So sánh kế hoạch: vì sao task `generateGreeting` không còn được Gradle tự suy ra?

**Bài tập D — kiểm tra việc đọc giá trị.** Chuyển `greeting.get()` ra ngoài `@TaskAction`, đặt vào cấu hình chỉ để in. Dự đoán khác biệt và giải thích tại sao đây không phải cách truyền giá trị đến task. Khôi phục cách dùng provider và chỉ đọc trong action.

**Bài tập E — thử chốt property.** Tạo một `Property<String>` bằng `objects.property(String::class.java)`, đặt `convention` rồi `set`, quan sát giá trị; sau đó dùng `finalizeValue()` và thử `set` lại trong một bản thử nghiệm. Giải thích lỗi thay đổi sau khi chốt. Không chèn thí nghiệm này vào một build quan trọng.

**Bài tập F — phân biệt các loại cache.** Chạy lặp lại `showGreeting` và quan sát producer `UP-TO-DATE`. Giải thích vì sao trạng thái đó không phải bằng chứng đã có output được lấy từ build cache, càng không chứng minh configuration cache đang bật.

### Câu hỏi tự kiểm tra

1. Vì sao `Provider<T>` chỉ công bố API đọc, còn `Property<T>` có thêm `set` và `convention`?
2. `getOrElse` khác `orElse` về kiểu trả về và thời điểm đọc ở đâu?
3. Tại sao `map` phù hợp cho phép biến đổi thuần, còn tạo file trong `map` là thiết kế kém?
4. Khi nào phải dùng `flatMap` thay cho `map`?
5. `TaskProvider<GenerateGreeting>` giúp tránh điều gì nếu ta không gọi `get()`?
6. Vì sao một `Property<String>` được đánh dấu `@Input` có ích cho up-to-date check?
7. Làm sao Gradle suy ra task tạo file từ dòng `inputFile.set(generateGreeting.flatMap { it.outputFile })`?
8. `DirectoryProperty` và `RegularFileProperty` cung cấp thông tin gì hơn một chuỗi đường dẫn?
9. Khi `-Pmessage=` truyền chuỗi trống, `orElse("default")` có thay nó không?
10. `finalizeValueOnRead` và `disallowChanges` khác nhau theo ý nghĩa cấu hình như thế nào?
11. Trì hoãn provider có bảo đảm hàm `map` chỉ chạy trong task action không?
12. Task được đăng ký theo nhu cầu, provider lazy và task `UP-TO-DATE` giải quyết những vấn đề khác nhau thế nào?

**Ghi nhớ:** `Provider<T>` diễn tả **giá trị đến từ đâu**, `Property<T>` cho phép **cấu hình nguồn hoặc giá trị mặc định**, `map`/`flatMap`/`zip` tạo **quan hệ giữa các giá trị**, còn `TaskProvider` và thuộc tính file có kiểu có thể nối **task tạo kết quả** với **task sử dụng kết quả**. Hãy giữ các quan hệ đó dưới dạng provider cho đến khi thực sự cần giá trị, khai báo đầy đủ input/output, và dùng `get()` ở đúng thời điểm để Gradle điều phối build có thể kiểm tra và tái sử dụng kết quả.