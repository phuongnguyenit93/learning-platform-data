# Lambda có receiver và cách đọc khối cấu hình có kiểu trong Gradle Kotlin DSL

## 1. Mục tiêu và bức tranh chung

Trong Gradle Kotlin DSL (các file `build.gradle.kts`, `settings.gradle.kts`), ta thường đọc những khối như:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.register("hello") {
    group = "learning"
    doLast {
        println("Xin chao Gradle")
    }
}
~~~

Những dấu ngoặc nhọn trên là cú pháp **lambda của Kotlin** được Gradle sử dụng làm ngôn ngữ cấu hình. Điểm đặc biệt là trong nhiều khối, ta viết `group = ...` hoặc `languageVersion.set(...)` mà không cần ghi tên đối tượng ở đầu câu lệnh. Kotlin cho phép như vậy nhờ **lambda có receiver** (lambda with receiver) và hệ thống API có kiểu của Gradle.

Sau bài học, bạn cần giải thích được: lambda thường khác lambda có receiver ở đâu; `this` trong từng khối ám chỉ đối tượng nào; vì sao `tasks.register<Copy>` cho phép gọi `from`/`into`; `java { }` hay `implementation(...)` từ đâu xuất hiện; cách lần theo chữ ký của khối lồng nhau; và cách phân biệt cấu hình task với hành động chạy task.

## 2. Lambda thường: nhận tham số qua tên hoặc `it`

Lambda là một giá trị hàm. Ví dụ Kotlin thông thường:

~~~kotlin
val upper: (String) -> String = { input ->
    input.uppercase()
}

fun main() {
    println(upper("gradle"))
}
~~~

Hàm có kiểu `(String) -> String`: nhận một chuỗi, trả một chuỗi. Khi chạy, chương trình in:

~~~text
GRADLE
~~~

Với một tham số duy nhất, Kotlin thường cho phép dùng `it`:

~~~kotlin
val upper: (String) -> String = { it.uppercase() }
~~~

Ở đây, `it` là **tham số lambda**. Nó không phải `this`, và kiểu `(String) -> String` không nói rằng chuỗi truyền vào là receiver.

Các biểu thức sau cũng thường sử dụng tham số `it`:

~~~kotlin
val doubled = listOf(1, 2, 3).map { it * 2 }
val length = "Gradle".let { it.length }
~~~

`map` nhận lambda xử lý phần tử, `let` truyền đối tượng làm tham số. Khi đọc DSL cần nhận ra kiểu lambda thực tế, không suy từ việc nhìn thấy dấu `{ ... }`.

## 3. Lambda có receiver: cú pháp `T.() -> R`

Một lambda có receiver hoạt động như hàm mở rộng trên đối tượng có kiểu `T`:

~~~kotlin
val upper: String.() -> String = {
    uppercase()
}

fun main() {
    println("gradle".upper())
}
~~~

Dòng in là `GRADLE`. Kiểu `String.() -> String` nghĩa là:

- `String` ở bên trái dấu chấm là kiểu của **receiver**;
- trong thân lambda, `this` chính là chuỗi làm receiver;
- `uppercase()` có thể viết gọn vì tương đương `this.uppercase()`;
- `String` sau mũi tên là kiểu kết quả.

Tổng quát, `T.() -> Unit` rất hay gặp trong DSL: receiver là đối tượng kiểu `T` đang được cấu hình; lambda không cần trả về giá trị có ý nghĩa. `Unit` là kiểu kết quả dành cho trường hợp đó.

### 3.1. Tự viết một DSL builder bằng Kotlin

Một file độc lập tên **`ReceiverDemo.kt`**:

~~~kotlin
class Endpoint {
    var host: String = "127.0.0.1"
    var port: Int = 80
}

fun endpoint(configure: Endpoint.() -> Unit): Endpoint {
    return Endpoint().apply(configure)
}

fun main() {
    val api = endpoint {
        host = "api.local"
        port = 9090
    }
    println(api.host + ":" + api.port)
}
~~~

Hàm `endpoint` tạo `Endpoint`, gọi lambda với đối tượng ấy làm receiver thông qua `apply`, rồi trả lại đối tượng đã được cấu hình. Vì vậy, `host = "api.local"` tương đương `this.host = "api.local"` bên trong lambda.

Nếu có sẵn Kotlin command-line compiler:

~~~bash
kotlinc ReceiverDemo.kt -include-runtime -d receiver-demo.jar
java -jar receiver-demo.jar
~~~

Output chính xác:

~~~text
api.local:9090
~~~

Đây là ví dụ Kotlin độc lập, yêu cầu cài `kotlinc` để chạy bằng lệnh trên. Build script Gradle Kotlin DSL dùng cơ chế ngôn ngữ tương tự nhưng được Gradle biên dịch và chạy; **dự án ứng dụng Java hoàn toàn có thể sử dụng `build.gradle.kts`**, không cần chuyển mã Java sang Kotlin.

## 4. `this` và `it`: khác nhau cả về đối tượng lẫn cách đọc

So sánh những hàm scope thông dụng của Kotlin:

| Cú pháp | Cách đối tượng được đưa vào lambda | Cách truy cập |
| --- | --- | --- |
| `obj.let { ... }` | Tham số | `it` hoặc tên tự đặt |
| `obj.also { ... }` | Tham số | `it` |
| `obj.apply { ... }` | Receiver | `this` hoặc gọi thành viên trực tiếp |
| `obj.run { ... }` | Receiver | `this` |
| `with(obj) { ... }` | Receiver | `this` |
| `buildString { ... }` | Receiver `StringBuilder` | `append(...)` |
| `endpoint { ... }` ở ví dụ trên | Receiver `Endpoint` | `host`, `port` |

Ví dụ:

~~~kotlin
val text = buildString {
    append("Gradle")
    append(" Kotlin DSL")
}
println(text)
~~~

`append` là thành viên của `StringBuilder`. Đây là lambda có receiver: không cần biến `builder.append(...)` trong khối. Kết quả in: `Gradle Kotlin DSL`.

Cần lưu ý: **không phải bất kỳ lambda có dấu ngoặc nhọn đều nhận receiver**. Khi một đoạn tài liệu không rõ, hãy xem chữ ký hàm hoặc dùng IDE để xác định nó nhận `(T) -> Unit`, `T.() -> Unit`, một `Action<T>` của Gradle hay overload khác. Với Gradle Kotlin DSL, các API `Action<T>` thường được dùng qua cú pháp lambda có receiver hoặc các hàm hỗ trợ Kotlin DSL; phải hiểu ý nghĩa ở call site và kiểu tương ứng.

## 5. Trong `tasks.register { }`, receiver là task nào?

Tạo một Gradle project có Wrapper và đặt toàn bộ đoạn sau vào **`build.gradle.kts`**:

~~~kotlin
tasks.register("chao") {
    group = "learning"
    description = "Vi du receiver Task"

    val taskName: String = name

    doLast {
        println("Xin chao tu task " + taskName)
    }
}
~~~

Lệnh chạy từ thư mục project root:

~~~bash
# Linux/macOS
./gradlew -q chao --no-configuration-cache
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat -q chao --no-configuration-cache
~~~

Dòng được action của ví dụ in ra:

~~~text
Xin chao tu task chao
~~~

Phân tích:

1. `tasks` là `TaskContainer` của project.
2. `register("chao")` **đăng ký task lazy** tên `chao`, trả về một `TaskProvider<Task>`; chỉ đăng ký không tự thực thi task.
3. Lambda đi kèm cấu hình task; trong khối này, receiver là đối tượng `Task` được Gradle cung cấp khi task được realize/cấu hình.
4. `group`, `description` và `name` là các thành viên của `Task`, nên không cần ghi `this.group` hoặc `this.name`.
5. `val taskName = name` đọc tên task trong lúc cấu hình.
6. `doLast { ... }` **thêm một action** để chạy khi task được thực thi. Mã trong action không chạy chỉ vì Gradle cấu hình task.

`--no-configuration-cache` làm thí nghiệm dễ quan sát thời điểm cấu hình; với Configuration Cache đang được tái sử dụng, Gradle có thể không đánh giá lại script như lần chạy ban đầu.

**Bẫy thường gặp:** cả lambda cấu hình và lambda action đều có thể dùng cú pháp receiver, nhưng **API nhận lambda quyết định ý nghĩa và thời điểm chạy**. Không thể kết luận rằng mọi `println` nằm trong `tasks.register { ... }` đều chạy lúc task execute.

## 6. Generic type quyết định thành viên trong khối: `register<Copy>`

Từ `Task` tổng quát đến task type cụ thể:

~~~kotlin
import org.gradle.api.tasks.Copy

tasks.register<Copy>("copyDocs") {
    group = "documentation"
    description = "Copy docs into the build directory"

    from("docs")
    into(layout.buildDirectory.dir("docs-copy"))
}
~~~

Đây là nội dung một file **`build.gradle.kts` độc lập**. Đọc như sau:

- `tasks.register<Copy>("copyDocs")` đăng ký task tên `copyDocs` với kiểu `Copy`; kết quả là `TaskProvider<Copy>`.
- `<Copy>` là **generic type argument** của Kotlin, giúp Gradle Kotlin DSL biết kiểu đối tượng task mà lambda đang cấu hình.
- Receiver trong khối cấu hình được hiểu theo kiểu `Copy`, nên `from(...)` và `into(...)` được phép gọi trực tiếp. Chúng thuộc API cấu hình việc sao chép.
- `from("docs")` thiết lập nguồn, `into(...)` thiết lập đích là một thư mục con trong build directory.
- Hai phương thức này **chưa sao chép file**. Công việc copy là action đã có của task type `Copy`, xảy ra khi Gradle thực thi task.

Khi tạo `docs/readme.txt`, chạy:

~~~bash
./gradlew copyDocs
~~~

Thông thường file được sao chép sang `build/docs-copy/readme.txt` nếu build directory giữ mặc định. Nếu nguồn không có file, task có thể có trạng thái không có nguồn và không tạo output.

Nếu thay `tasks.register<Copy>` bằng:

~~~kotlin
tasks.register("copyDocs") {
    from("docs")
}
~~~

thì code trên có thể lỗi `Unresolved reference: from`, vì receiver giờ là `Task` thông thường, không cung cấp API `CopySpec.from`. Đây là ví dụ điển hình cho việc **phải biết type của receiver trước khi đọc thành viên của một khối**.

## 7. `tasks.named<Test>` và `configureEach`: cấu hình có kiểu, vẫn lazy

Plugin Java cung cấp task `test` thuộc loại `Test`. Cấu hình có kiểu:

~~~kotlin
import org.gradle.api.tasks.testing.Test

plugins {
    java
}

tasks.named<Test>("test") {
    useJUnitPlatform()
    description = "Run tests on JUnit Platform"
}
~~~

Ý nghĩa:

- `plugins { java }` áp dụng Java plugin, tạo task `test`, extension Java và nhiều configuration.
- `tasks.named<Test>("test")` tham chiếu một task **đã được đăng ký** bằng tên và kiểu, giữ cách cấu hình theo provider.
- Trong lambda, receiver được biết là `Test`, do đó `useJUnitPlatform()` là lệnh hợp lệ để **cấu hình** task test.
- Lệnh `useJUnitPlatform()` không tự cài JUnit và không chạy test ngay lúc cấu hình. Muốn chạy test thực, cần dependency/test classes phù hợp.

Nếu muốn cấu hình mọi task có type `Test` (bao gồm task do plugin tạo thêm về sau):

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

`configureEach` giúp cấu hình lazy cho các phần tử kiểu `Test`. Không nên dùng `tasks.getByName("test")` hay `tasks.create(...)` chỉ để cấu hình khi có API provider/lazy phù hợp.

| API | Phạm vi | Điều cần chú ý |
| --- | --- | --- |
| `tasks.register("x")` | Đăng ký task mới | Receiver là task type mặc định nếu không chỉ rõ generic |
| `tasks.register<Copy>("x")` | Đăng ký task mới có kiểu `Copy` | Có API riêng của `Copy` |
| `tasks.named<Test>("test")` | Cấu hình task đã đăng ký tên `test` | Tên và type phải phù hợp |
| `tasks.withType<Test>().configureEach` | Cấu hình các task type `Test` | Dùng khi cần quy tắc chung, vẫn giữ lazy |
| `TaskProvider<T>` | Handle cho task `T` | Hỗ trợ cấu hình mà không cần lấy đối tượng task ngay |

**Registered khác realized khác executed:** một task có thể đã được đăng ký nhưng chưa được tạo/cấu hình thực sự; có thể đã được realize/cấu hình nhưng không được chọn để chạy action. Không gộp ba trạng thái thành một.

## 8. Lambda lồng nhau: receiver thay đổi theo cấp

Xét đoạn Kotlin DSL (file `build.gradle.kts`):

~~~kotlin
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Có ba tầng quan trọng:

~~~text
Build script
  java { ... }                      receiver: JavaPluginExtension
    toolchain { ... }               receiver: JavaToolchainSpec
      languageVersion.set(...)      Property<JavaLanguageVersion>
~~~

Khối `java { ... }` cấu hình **Java extension** do plugin Java cung cấp. Khối `toolchain { ... }` cấu hình đối tượng toolchain với type `JavaToolchainSpec`. Thuộc tính `languageVersion` nằm trên receiver toolchain; lời gọi `set(...)` cấu hình một `Property<JavaLanguageVersion>`.

Khi nhìn một tên không có tiền tố, Kotlin tìm theo kiểu và scope có sẵn, thường ưu tiên ngữ cảnh gần nhất phù hợp. Trong lambda lồng nhau có thể có **nhiều receiver ngầm**; DSL có thể áp dụng `@DslMarker` để giới hạn cách truy cập các receiver ngoài. Không nên đoán `this` luôn là Project, Java extension hoặc Task: cần xác định *khối nào đã tạo lambda đang đọc*.

Chẳng hạn `group` ở script cấp project có thể là thuộc tính `Project`, nhưng `group` trong một khối cấu hình task là thuộc tính `Task`. Tên giống nhau **không đảm bảo cùng đối tượng**.

### 8.1. Kết hợp receiver với lambda tham số

~~~kotlin
tasks.register("phanBiet") {
    val currentName = name               // Receiver Task
    val numbers = listOf(1, 2, 3)
    val doubled = numbers.map { it * 2 }  // it la tham so cua map

    doLast {
        println(currentName)
        println(doubled.joinToString(","))
    }
}
~~~

Nếu chạy `./gradlew -q phanBiet --no-configuration-cache`, các dòng do action in lần lượt:

~~~text
phanBiet
2,4,6
~~~

Trong `map { it * 2 }`, `it` là phần tử danh sách, không phải task. `name` trong khối ngoài đến từ receiver Task. Nếu muốn tránh nhập nhằng khi lồng nhiều receiver, lưu giá trị cần thiết vào biến đặt tên rõ ràng như `currentName`.

Khi viết build logic lớn, tránh capture `Project`/script state trong action `doLast` vì có thể không tương thích Configuration Cache. Nên dùng property/provider và custom task type có input/output rõ ràng.

## 9. Type-safe accessor: nguồn gốc của `java { }` và `implementation(...)`

Một đặc điểm khác của Gradle Kotlin DSL là **type-safe model accessors**: Gradle có thể tạo các hàm/thuộc tính có kiểu để truy cập thành phần model do plugin cung cấp.

Ví dụ:

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}
~~~

- `java` trong `plugins` là cách áp dụng Java plugin qua Kotlin DSL.
- `testImplementation(...)` là accessor dành cho dependency configuration mà Java plugin cung cấp.
- `java { ... }` ở mục trước là accessor truy cập Java extension.
- `mavenCentral()` là API của repository handler, không phải một keyword của Kotlin.

Những tên đó **không tự tồn tại trong mọi script**. Kotlin DSL sinh nhiều accessor dựa trên các phần tử mô hình đã được biết **sau khối `plugins { ... }`**. Nếu plugin được áp dụng muộn bằng `apply(plugin = "java")` hoặc một phần tử được tạo động sau thời điểm sinh accessor, accessor ngắn gọn có thể chưa sẵn sàng.

Ví dụ dùng API dependency container tường minh:

~~~kotlin
dependencies {
    add("testImplementation", "org.junit.jupiter:junit-jupiter:5.11.4")
}
~~~

Đây là snippet: nó chỉ hoạt động khi configuration `testImplementation` **đã tồn tại**. `add` không thay thế việc áp dụng plugin tạo configuration tương ứng.

Nếu extension Java đã tồn tại nhưng accessor `java { ... }` không khả dụng ở ngữ cảnh script hiện tại, API có kiểu có thể dùng:

~~~kotlin
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.jvm.toolchain.JavaLanguageVersion

// Chi dung sau khi Java plugin da duoc ap dung.
extensions.configure<JavaPluginExtension> {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}
~~~

Đây là snippet phụ thuộc context, không phải toàn bộ script độc lập.

**Cách sửa lỗi `Unresolved reference`:** kiểm tra đúng plugin, file `build.gradle.kts` hay `settings.gradle.kts`, model đã tạo ra extension/configuration chưa, tên và type, phiên bản Gradle Wrapper, import và overload. Chuyển cơ học từ Groovy sang Kotlin bằng cách thêm dấu ngoặc thường chưa đủ.

## 10. Receiver, extension, task type, provider: đừng đánh đồng

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Receiver | `Task` trong `tasks.register("x") { ... }` | Đối tượng mà lambda thao tác trực tiếp |
| Extension | Java extension trong `java { ... }` | Đối tượng cấu hình do plugin gắn vào project |
| Task type | `Copy`, `Test` | Kiểu cung cấp thuộc tính, hành vi/task actions |
| `TaskProvider<T>` | Giá trị trả về từ `tasks.register<Copy>` | Tham chiếu cấu hình/lấy task theo cơ chế lazy |
| `Property<T>` | `languageVersion` | Giá trị managed, có thể thiết lập bằng `set` |
| `Provider<T>` | `layout.buildDirectory.dir("x")` | Nguồn giá trị được cung cấp/tính khi cần |
| Type-safe accessor | `java { }`, `testImplementation(...)` | Cú pháp có kiểu để truy cập model Gradle |

Ví dụ:

~~~kotlin
import org.gradle.api.tasks.Copy

val outputDir = layout.buildDirectory.dir("generated-docs")

tasks.register<Copy>("copyDocs") {
    from("docs")
    into(outputDir)
}
~~~

`outputDir` là provider trỏ tới directory trong build output. Receiver `Copy` có API `from` và `into`. Lệnh `into(outputDir)` cấu hình đích từ provider, không có nghĩa đã đọc hay tạo ngay mọi giá trị.

Nhiều API Gradle cung cấp `Property<T>` để cho phép cấu hình lazy. Khi thấy `someProperty.set(provider)`, hãy giữ cách truyền provider nếu API hỗ trợ, thay vì lấy sớm `provider.get()`. Việc gọi `get()` không đúng thời điểm có thể làm hỏng tính lazy hoặc làm build phụ thuộc thứ tự cấu hình.

## 11. Phân biệt cấu hình và thực thi dù đều dùng lambda

~~~kotlin
tasks.register("demo") {
    println("CONFIG: cau hinh task")

    doLast {
        println("ACTION: thuc thi task")
    }
}
~~~

Dòng đầu tiên nằm trực tiếp trong lambda **cấu hình** và có thể chạy khi task được realize. Dòng thứ hai nằm trong action được `doLast` đăng ký, chỉ chạy lúc thực thi task và nếu task không bị bỏ qua bởi điều kiện của Gradle.

Dùng các lệnh:

~~~bash
./gradlew -q help --no-configuration-cache
./gradlew -q demo --no-configuration-cache
./gradlew demo --dry-run --no-configuration-cache
~~~

- Với `help`, task `demo` thường không được realize nếu project đơn giản và không có plugin khác đụng đến task. Vì vậy có thể không thấy dòng `CONFIG` của task và sẽ không thấy action.
- Với `demo`, Gradle sẽ cần cấu hình task và nếu thực thi bình thường sẽ in cả hai dòng.
- Với `--dry-run`, Gradle vẫn chuẩn bị graph và có thể chạy code cấu hình, nhưng không chạy action của task; dòng `ACTION` sẽ không được in bởi ví dụ.

`UP-TO-DATE`, `FROM-CACHE`, `SKIPPED`, `NO-SOURCE` hoặc Configuration Cache có thể thay đổi việc code nào được chạy/lặp lại. Cần phân biệt **thời điểm cấu hình task** với **thời điểm action thực thi**, không lấy một lượt log làm quy luật tuyệt đối cho mọi build.

## 12. So sánh với Groovy DSL để đọc tài liệu song ngữ

Gradle hỗ trợ cả Groovy DSL và Kotlin DSL. Groovy DSL thường dùng closure với cơ chế delegate linh hoạt; Kotlin DSL dựa trên kiểu Kotlin, receiver lambda và API Gradle. Hai cách viết cùng cấu hình mô hình build nhưng có quy tắc cú pháp/kiểm tra kiểu khác nhau.

**Groovy DSL – `build.gradle`:**

~~~groovy
plugins {
    id 'java'
}

tasks.register('copyDocs', Copy) {
    from 'docs'
    into layout.buildDirectory.dir('docs-copy')
}
~~~

**Kotlin DSL – `build.gradle.kts`:**

~~~kotlin
import org.gradle.api.tasks.Copy

plugins {
    java
}

tasks.register<Copy>("copyDocs") {
    from("docs")
    into(layout.buildDirectory.dir("docs-copy"))
}
~~~

Trong ví dụ Kotlin, `<Copy>` là generic type; các lời gọi `from` và `into` được phân giải theo API có kiểu. Groovy thường có cú pháp lược dấu ngoặc và khả năng phân giải động; không nên coi closure delegate của Groovy là hoàn toàn giống receiver của Kotlin.

Khi chuyển snippet Groovy sang Kotlin cần kiểm tra: chuỗi nháy kép, dấu ngoặc, generic type, method overload, cách cấu hình `Property<T>` và thứ tự áp dụng plugin. Không chỉ thay `'... '` bằng `"..."`.

## 13. Cách đọc khối cấu hình lạ từ tài liệu Gradle

Gặp ví dụ chưa từng thấy:

~~~kotlin
tasks.register<Copy>("backup") {
    from("docs")
    into(layout.buildDirectory.dir("backup"))
}
~~~

Áp dụng chuỗi sáu bước:

1. **Xác định object ngoài cùng:** `tasks` là `TaskContainer`; `register` là một thao tác trên container.
2. **Đọc tham số và generic:** `"backup"` là tên task, `Copy` là type.
3. **Xác định receiver của lambda:** task thuộc type `Copy`, nên tìm thành viên ở type này hoặc các interface/supertype của nó.
4. **Tra method/member:** `from` và `into` thuộc logic cấu hình `CopySpec`, nhận nguồn và đích; không thực hiện copy ngay.
5. **Xem giá trị trả về:** `register` cung cấp `TaskProvider<Copy>` cho cấu hình lazy.
6. **Xác định thời điểm chạy:** khối `register` cấu hình task khi được realize; action `Copy` làm công việc khi Gradle thực thi.

Trong IDE, dùng *Go to Definition*, *Quick Documentation* và gợi ý type để xem chữ ký của `register`, `named`, `configureEach` và các property. Khi API có nhiều overload, hãy chọn đúng phiên bản và type đang dùng.

Cần hỏi thêm: plugin nào tạo task/extension? Khối đang nằm trong `build.gradle.kts`, `settings.gradle.kts` hay precompiled script plugin? Acccessor có được sinh ở ngữ cảnh đó không? Các câu hỏi này thường giải thích phần lớn lỗi `Unresolved reference`.

## 14. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân điển hình | Giải pháp |
| --- | --- | --- |
| `Unresolved reference: from` | Receiver là `Task` thay vì `Copy` | Dùng `register<Copy>` hoặc `named<Copy>` phù hợp |
| `Unresolved reference: useJUnitPlatform` | Receiver không có kiểu `Test` | Kiểm tra Java plugin và cấu hình `named<Test>` / `withType<Test>` |
| `Unresolved reference: java` | Java extension chưa được áp dụng hoặc accessor không được sinh | Kiểm tra `plugins { java }`; cân nhắc `extensions.configure<JavaPluginExtension>` |
| `Unresolved reference: testImplementation` | Configuration/accessor chưa tồn tại ở ngữ cảnh đó | Kiểm tra plugin, cách áp dụng và configuration thật |
| Mong có `it` trong `java { ... }` | Nhầm receiver lambda với lambda nhận tham số | Xem chữ ký và dùng `this` hoặc thành viên trực tiếp |
| `this` truy cập nhầm thành viên | Nhiều receiver lồng nhau, tên bị shadow | Xem receiver gần nhất và dùng biến tường minh |
| Gán trực tiếp vào `Property<T>` bị lỗi type | API nhận property/provider chứ không phải kiểu primitive đơn thuần | Dùng `.set(...)` với đúng kiểu, ưu tiên truyền provider nếu có |
| Task được cấu hình dù không chạy action | Task được realize do graph hoặc plugin | Phân biệt code cấu hình với `doLast` và kiểm tra `--dry-run` |
| Script cấu hình nặng/chậm | Thực hiện I/O trong khối cấu hình, ép task eager | Đặt công việc vào task action/custom task, dùng provider/lazy APIs |
| Configuration Cache không hoạt động | Action capture đối tượng Project/script hoặc truy cập state không phù hợp | Sử dụng input/output managed properties, tham khảo quy tắc cache |
| Copy snippet Groovy báo `Unexpected tokens` | Sai dấu ngoặc, chuỗi hoặc kiểu API Kotlin | Đọc Kotlin tab của tài liệu và kiểm tra overload |

## 15. Bài tập tự kiểm tra

**Bài A.** Đoạn `listOf(1, 2).map { it + 1 }` có receiver kiểu `Int` không?  
**Đáp án:** không. `it` là tham số của lambda cho từng phần tử.

**Bài B.** Vì sao trong `endpoint { host = "x" }` ta không cần biến `endpoint.host`?  
**Đáp án:** hàm nhận `Endpoint.() -> Unit` nên `this` trong khối là đối tượng `Endpoint`.

**Bài C.** Trong `tasks.register<Copy>("copyDocs") { from("docs") }`, `from` thuộc kiểu nào?  
**Đáp án:** `Copy` cung cấp API cấu hình thông qua `CopySpec`; generic `Copy` xác định receiver task có các thành viên đó.

**Bài D.** Trong `java { toolchain { languageVersion.set(...) } }`, receiver gần nhất của `languageVersion` là gì?  
**Đáp án:** `JavaToolchainSpec`.

**Bài E.** Có `tasks.register("x") { println("A"); doLast { println("B") } }`. Dòng `A` có bắt buộc đợi tới lúc action chạy không?  
**Đáp án:** không; nó nằm trong code cấu hình task và chạy khi task được realize. Dòng `B` là action và cần task được thực thi.

**Bài F.** Dùng `tasks.named<Test>("test")` và `tasks.withType<Test>().configureEach` khác gì?  
**Đáp án:** một cách cấu hình task `test` theo tên; cách kia cấu hình các task thuộc type `Test` trong container.

**Bài G.** Vì sao `testImplementation(...)` hợp lệ khi áp dụng Java plugin trong `plugins { }`, nhưng có thể lỗi ở script khác?  
**Đáp án:** accessor được tạo theo model/plugin có sẵn và ngữ cảnh của từng script; cần kiểm tra plugin/timing.

**Bài H.** Muốn tự xác nhận một khối dùng receiver gì thì nên làm gì trước?  
**Đáp án:** đọc chữ ký hàm/overload trong Gradle Kotlin DSL API hoặc IDE, rồi xác định generic type, extension/task type và plugin cung cấp nó.

## 16. Tài liệu chính thức và hướng đọc tiếp

- [Gradle Kotlin DSL Primer](https://docs.gradle.org/current/userguide/kotlin_dsl.html): nền tảng Kotlin DSL, model accessors và các lưu ý về DSL có kiểu.
- [Gradle Kotlin DSL API](https://docs.gradle.org/current/kotlin-dsl/): tra overload, kiểu receiver, các hàm hỗ trợ và signature chính xác.
- [Gradle Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): phân biệt configuration và execution.
- [Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named`, `TaskProvider`, `configureEach`.
- [Gradle Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html): task types, actions, quan hệ phụ thuộc và cấu hình.
- [Kotlin: Lambdas](https://kotlinlang.org/docs/lambdas.html): function types và function types with receiver.
- [Kotlin: Scope Functions](https://kotlinlang.org/docs/scope-functions.html): khác nhau giữa `this` và `it`, `apply`/`run`/`with`/`let`/`also`.

**Điểm cần nhớ:** nhìn một khối cấu hình Kotlin DSL, hãy tìm **kiểu receiver**, **API nhận lambda**, **plugin hoặc task type tạo ra đối tượng**, **nguồn gốc type-safe accessor**, và **thời điểm code chạy**. Hiểu những điều này giúp đọc đúng tài liệu Gradle và tự phát hiện lỗi mà không cần chép nguyên mẫu.