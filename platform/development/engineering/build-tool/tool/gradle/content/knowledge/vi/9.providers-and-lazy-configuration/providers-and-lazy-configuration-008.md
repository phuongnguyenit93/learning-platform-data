# Tránh đọc Provider sớm và nhận diện tác dụng phụ khi cấu hình Gradle

## 1. Vấn đề cần giải quyết

Gradle sử dụng **Provider API** và **cấu hình lười (lazy configuration)** để trì hoãn việc tìm giá trị, tạo task và thực hiện công việc cho đến khi thực sự cần. Cách này đặc biệt hữu ích trong build nhiều module, có nhiều plugin, task tùy chọn hoặc CI phải chạy những lệnh rất nhỏ như `help`, `tasks` hay `:app:test`.

Tuy nhiên, code có thể tạo ra một `Provider` rồi lập tức gọi `get()`, đọc file, chạy lệnh hệ điều hành hoặc ghi file ngay khi Gradle đang đọc `build.gradle`. Khi đó, chi phí và tác dụng phụ đã diễn ra trong **configuration phase**, dù task liên quan có thể không hề được yêu cầu. Configuration Cache cũng có thể phải cấu hình lại nhiều hơn cần thiết khi các giá trị bị đọc quá sớm.

Bài học tập trung vào bốn kỹ năng:

1. Phân biệt **tham chiếu tới giá trị** với **việc yêu cầu giá trị ngay lập tức**.
2. Nhận ra nơi `Provider.get()`, `TaskProvider.get()` hoặc một API eager gây ra công việc trước thời điểm mong muốn.
3. Phân loại **tác dụng phụ của quá trình cấu hình**: in log, ghi/xóa file, truy cập mạng, chạy chương trình bên ngoài, phân giải dependency, thay đổi trạng thái toàn cục.
4. Chuyển build logic sang **Provider/Property được nối trực tiếp vào task input/output**, dùng task registration và task action phù hợp, rồi kiểm chứng bằng Configuration Cache và kết quả thực thi.

Ví dụ sử dụng **Gradle Groovy DSL**, các tệp `settings.gradle` và `build.gradle`, cùng Gradle Wrapper (`./gradlew` trên Linux/macOS hoặc `.\gradlew.bat` trong PowerShell Windows). Không cần mã nguồn Java cho các bài demo, nhưng máy vẫn phải có Java/JDK tương thích bản Gradle của dự án; Java 17+ là lựa chọn thích hợp khi phiên bản Gradle đang chạy hỗ trợ.

## 2. Ba giai đoạn của Gradle và nghĩa của “đọc sớm”

Một build thường đi qua:

~~~text
INITIALIZATION
    Xác định settings, các project và cấu trúc build
            |
            v
CONFIGURATION
    Đọc build.gradle, áp dụng plugin, đăng ký/cấu hình task,
    tạo đồ thị Provider/Property và task graph cần thiết
            |
            v
EXECUTION
    Chạy các task đã chọn: đọc/ghi đầu vào-đầu ra,
    biên dịch, chạy test, tạo artifact, ...
~~~

Nếu **Configuration Cache** được bật và có cache hit hợp lệ, Gradle có thể **bỏ qua việc cấu hình lại project**, khôi phục task graph đã ghi và tiếp tục thực thi. Do đó, một đoạn ghi file hoặc gọi API bên ngoài trong configuration sẽ có tần suất thực thi khác nhau giữa cache miss và cache hit.

“Đọc Provider sớm” nghĩa là **yêu cầu giá trị khi đang cấu hình và chưa cần giá trị cụ thể để xây dựng model**. Ví dụ:

~~~groovy
// build.gradle — minh họa anti-pattern
def targetEnv = providers.gradleProperty('targetEnv').orElse('dev')
def targetEnvNow = targetEnv.get()   // Ép đọc ngay khi script được đánh giá.

println('Đang cấu hình cho: ' + targetEnvNow)
~~~

`providers.gradleProperty(...)` tạo một mô tả nguồn giá trị. `orElse('dev')` tạo Provider có fallback. Nhưng `get()` buộc Gradle lấy giá trị ở **configuration time**. Nếu giá trị chỉ phục vụ cho một task được chạy sau này, việc ép đọc này không cần thiết. `println` chạy mỗi lần script được đánh giá, ngay cả với lệnh không dùng `targetEnv`.

**Không có quy tắc cấm tuyệt đối `get()` trong configuration.** Có API bắt buộc nhận giá trị cụ thể để xây dựng cấu hình, hoặc giá trị thực sự quyết định plugin/repository/task graph; khi đó đọc sớm là có chủ đích và cần coi nó là **configuration input**. Vấn đề là đọc một giá trị không cần thiết hoặc làm tác dụng phụ xảy ra ngoài task.

## 3. Phân biệt `Provider<T>`, `Property<T>` và `TaskProvider<T>`

| API | Đại diện cho | Điều nên làm |
| --- | --- | --- |
| `Provider<T>` | Một giá trị có thể được tính/tra cứu sau | Chuyển Provider sang nơi dùng; `map`, `flatMap`, `orElse` để xây chuỗi |
| `Property<T>` | Property có thể cấu hình, cũng là Provider | `set(provider)` hoặc `convention(provider)` để nối đầu vào mà không tự mở giá trị |
| `RegularFileProperty`/`DirectoryProperty` | Tệp/thư mục có thể được cung cấp lười | Truyền vào `@InputFile`, `@OutputFile`, `@OutputDirectory`... |
| `ListProperty<T>`/`MapProperty<K,V>` | Tập giá trị cấu hình lười, có kiểu | Nối Provider cho danh sách/Map thay vì tự kết hợp eager |
| `TaskProvider<T>` | Tham chiếu đến task có thể chưa được tạo/cấu hình | Dùng `tasks.register`, `tasks.named` và chuyển TaskProvider vào `dependsOn` |
| `ProviderFactory` qua `providers` | Tạo Provider cho Gradle property, env, system property, file contents... | Ưu tiên nguồn có theo dõi input rõ như `gradleProperty` và `environmentVariable` |

**Đọc `Provider.get()`** là yêu cầu lấy giá trị. Tùy Provider và thời điểm, nó có thể thực thi supplier/transformer, truy cập file/biến môi trường hoặc đưa giá trị vào model. Gradle **không hứa một transformer được chạy đúng một lần**: nó có thể được yêu cầu lại khi cần.

**Đọc `TaskProvider.get()`** thì có thêm ý nghĩa đặc biệt: nó khiến một task được **realize**, tức là tạo và cấu hình task sớm hơn. Tạo TaskProvider bằng `tasks.register` chưa đồng nghĩa task đã được tạo thực tế.

### 3.1. Những lời gọi đọc giá trị cần rà soát

~~~groovy
def p = providers.gradleProperty('releaseTag')

// Mỗi lời gọi dưới đây là một cách hỏi về giá trị/trạng thái p:
p.get()                    // Nếu không có giá trị, ném lỗi.
p.getOrElse('snapshot')     // Yêu cầu giá trị, nếu thiếu dùng fallback cụ thể.
p.orNull                   // Đọc hoặc trả null khi thiếu.
p.isPresent()              // Kiểm tra có giá trị, có thể phải truy vấn nguồn.

// Còn những cách dưới đây tạo Provider mới để sử dụng về sau:
def defaulted = p.orElse('snapshot')
def normalized = defaulted.map { tag -> tag.trim() }
~~~

Ở Groovy, `p.orNull` tương ứng `getOrNull()`; `p.isPresent()` cũng là truy vấn có thể buộc provider xác định trạng thái. Không dùng `isPresent` như một cách “kiểm tra miễn phí” mọi lúc. `orElse('snapshot')` **khác** `getOrElse('snapshot')`: cách đầu tạo Provider vẫn trì hoãn, cách sau lấy giá trị ngay tại chỗ gọi.

Các phép `map` và `flatMap` **khai báo phép biến đổi**; bản thân việc nối chúng không có nghĩa lambda đã chạy. Tuy vậy, khi một consumer lấy giá trị, lambda có thể chạy trong configuration, khi xác định input task hoặc ở execution tùy loại provider và cơ chế Gradle. Vì thế lambda phải **thuần, nhanh, dự đoán được**, không dựa vào tác dụng phụ hoặc số lần được gọi.

### 3.2. Provider “có giá trị” không phải “đã được đánh giá”

Một `Provider<String>` có thể được tạo từ `-P`/`gradle.properties`, hoặc một `Property<String>` được thiết lập bằng Provider khác. Điều đó chỉ nói rằng model biết **cách tìm giá trị**. Để kiểm tra đúng thời điểm, phải xem dòng gọi `get()`, API consumer có đòi giá trị cụ thể không và task nào được Gradle yêu cầu.

Đừng đồng nhất “lazy” với “chỉ chạy đúng lúc `@TaskAction`”. Gradle có thể đọc task inputs trước action để tính fingerprint/up-to-date, hoặc tính toán provider khi lưu Configuration Cache. Mục đích chính của lazy wiring là **tránh đọc quá sớm do build script tự ép** và cho Gradle biết quan hệ dữ liệu cần tính.

## 4. Anti-pattern: tạo Provider nhưng lập tức ép thành giá trị

Giả sử script cần tên môi trường để một task in thông tin:

~~~groovy
// build.gradle — không nên khi chỉ task reportEnv cần giá trị
def envProvider = providers.gradleProperty('environment').orElse('local')
def envName = envProvider.get()

tasks.register('reportEnv') {
    doLast {
        println('environment=' + envName)
    }
}
~~~

Vấn đề:

- `envName` được tính ngay cả khi gọi `./gradlew help` hoặc task không liên quan.
- Nếu nguồn là file hoặc chương trình ngoài, chi phí đó có thể diễn ra ở mọi cấu hình.
- `envName` là một String được chụp sớm; việc chọn nguồn theo execution/task input trở nên kém rõ.
- Nếu closure task vô tình giữ tham chiếu tới Project/Script hoặc object không serializable, Configuration Cache có thể báo lỗi. Chỉ đổi biến thành Provider không đủ nếu task action vẫn truy cập model Gradle bị cấm.

Một cách an toàn và dễ bảo trì là **khai báo task type có Property riêng**, sau đó nối Provider vào Property.

## 5. Ví dụ hoàn chỉnh: nối Gradle property vào task input

Đây là ví dụ độc lập, **chạy được trên một Gradle project có Wrapper**. Tệp `build.gradle` định nghĩa một custom task theo Groovy, không yêu cầu plugin ngoài.

### 5.1. Cấu trúc dự án

~~~text
provider-lazy-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Bốn tệp Wrapper đã có sẵn từ project Gradle; khi dùng lại ví dụ, cần chạy tại root project. Không phải điền mã nguồn Java vào thư mục `src/`.

### 5.2. `settings.gradle`

~~~groovy
rootProject.name = 'provider-lazy-demo'
~~~

### 5.3. `build.gradle`

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

plugins {
    id 'base'
}

abstract class PrintGreeting extends DefaultTask {
    @Input
    abstract Property<String> getGreeting()

    @TaskAction
    void printGreeting() {
        println('greeting=' + greeting.get())
    }
}

// Đây là đồ thị Provider; chưa cần gọi get() trong build script.
def greetingProvider = providers.gradleProperty('greeting')
    .orElse('Xin chào')

tasks.register('showGreeting', PrintGreeting) {
    // Property.set(Provider) nối nguồn với input của task.
    greeting.set(greetingProvider)
}
~~~

Cần chú ý:

1. `@Input Property<String>` nêu rõ dữ liệu đầu vào ảnh hưởng hành vi task; nó có kiểu và được Gradle quản lý.
2. `greeting.set(greetingProvider)` giữ **mối liên hệ Provider**. Không viết `greeting.set(greetingProvider.get())` nếu chưa có lý do bắt buộc tính cụ thể ngay.
3. `get()` trong `@TaskAction` chỉ đọc **property thuộc chính task**, khi task thực thi. Task không gọi `project` hoặc đọc `ext` tại execution.
4. Gradle có thể truy vấn input khi chuẩn bị chạy task/kiểm tra trạng thái trước action, nhưng input này không bị ép bởi script trong configuration.
5. `tasks.register` giữ task chưa được realize cho đến khi nó thực sự cần, thay vì tạo eager bằng `tasks.create`.

### 5.4. Chạy và kết quả

Linux/macOS:

~~~bash
./gradlew -q showGreeting
./gradlew -q showGreeting -Pgreeting=Hello-Team
~~~

Với build không có một cấu hình `greeting` khác ghi đè, stdout do `PrintGreeting` in lần lượt là:

~~~text
greeting=Xin chào
~~~

và:

~~~text
greeting=Hello-Team
~~~

PowerShell Windows:

~~~powershell
.\gradlew.bat -q showGreeting
.\gradlew.bat -q showGreeting -Pgreeting=Hello-Team
~~~

`-P` truyền **Gradle project property**; `providers.gradleProperty('greeting')` đọc nguồn này. Nếu không có `-P` hoặc `gradle.properties` tương ứng, `orElse` cung cấp giá trị mặc định. Trên CI/plugin đặc biệt, có thể có log riêng ngoài stdout của task; `-q` giảm log Gradle nhưng không loại trừ mọi cảnh báo môi trường.

### 5.5. Kiểm tra Configuration Cache

~~~bash
./gradlew showGreeting --configuration-cache
./gradlew showGreeting --configuration-cache
./gradlew showGreeting --configuration-cache -Pgreeting=Hello-Team
~~~

- Lần đầu thường cần tạo/lưu cấu hình của task graph, tùy cache sẵn có.
- Lần hai với **cùng task và cùng các configuration inputs** có thể reuse Configuration Cache; log Gradle cho biết việc reuse.
- Khi đổi `-Pgreeting`, dữ liệu task phải phản ánh giá trị mới. Tùy mô hình input và việc Gradle xét khóa/cache, lần chạy có thể cần cấu hình lại hoặc dùng cơ chế invalidation phù hợp. **Không khẳng định mọi thay đổi của `-P` bắt buộc cache miss hoặc bắt buộc cache hit trong mọi trường hợp**.
- Vì `PrintGreeting` không khai báo output file, đây là task minh họa Provider/Configuration Cache, **không phải bài kiểm thử cho Build Cache của output**.

Để kiểm tra đúng, hãy xem log `--configuration-cache` thay vì kết luận chỉ từ dòng `greeting=...`. Nếu Gradle báo lỗi serialize state hay vi phạm ở task execution, sửa theo báo cáo trước khi coi bài là tương thích.

## 6. Hệ quả của `TaskProvider.get()`: task bị realize

Provider của **giá trị** và Provider của **task** cùng có phương thức `get()`, nhưng hệ quả cần chú ý khác nhau. Xem ví dụ:

~~~groovy
// build.gradle — minh họa, có thể đặt trong project thử nghiệm
def report = tasks.register('report') {
    println('CONFIGURE: report')
    doLast {
        println('EXECUTE: report')
    }
}

// Anti-pattern: ép tạo/cấu hình report ngay tại cấu hình script.
def reportTask = report.get()
~~~

Dù chỉ chạy `./gradlew help`, việc gọi `report.get()` khiến Gradle phải realize `report` và thực thi closure cấu hình của nó. Dòng `CONFIGURE: report` được in trong configuration, nhưng `EXECUTE: report` **không được in** khi task `report` không chạy. Mục đích ví dụ là phân biệt thời điểm, không khuyến khích giữ `println` trong configuration.

Nếu cần một task khác phụ thuộc vào nó, **chuyển TaskProvider**:

~~~groovy
def report = tasks.register('report') {
    doLast {
        println('EXECUTE: report')
    }
}

tasks.register('allReports') {
    dependsOn(report)  // Không cần report.get().
    doLast {
        println('EXECUTE: allReports')
    }
}
~~~

Lệnh `./gradlew -q allReports` chạy hai task theo quan hệ phụ thuộc. Phần stdout do task in ra theo thứ tự:

~~~text
EXECUTE: report
EXECUTE: allReports
~~~

Gradle hỗ trợ dùng `TaskProvider` trực tiếp trong `dependsOn`. Khi task `allReports` không được chạy, dependency đó không mặc nhiên buộc `report` tạo/configure ngay. So sánh:

| API | Mục đích | Rủi ro eager |
| --- | --- | --- |
| `tasks.register('name', Type)` | Đăng ký task lazily | Thấp |
| `tasks.named('name')` | Lấy `TaskProvider` của task đã đăng ký | Thấp; báo lỗi nếu task không tồn tại |
| `tasks.named('name') { ... }` | Thêm action cấu hình task lazily | Thấp |
| `tasks.withType(Type).configureEach { ... }` | Cấu hình mọi task đúng kiểu khi chúng cần | Thấp |
| `tasks.create('name')` | Tạo task ngay | Cao |
| `tasks.getByName('name')` | Lấy Task instance và realize | Cao |
| `taskProvider.get()` | Ép realize task | Cao |
| `tasks.all { ... }` / `tasks.withType(Type) { ... }` | Action eager theo collection | Cao với nhiều task |

**Lưu ý:** `tasks.register` không tự bảo đảm toàn build lazy. Một plugin khác có thể dùng `getByName`, lặp qua toàn bộ task collection hoặc gọi `get()` trên TaskProvider, làm task bị realize ngoài ý muốn.

## 7. Tác dụng phụ trong configuration: nhận diện bằng mắt

**Tác dụng phụ** là hành động tạo hiệu ứng bên ngoài giá trị trả về: viết tệp, gửi request, sửa database, xuất log có ý nghĩa vận hành, tạo tiến trình, thay đổi trạng thái hệ thống. Những hành động đó nguy hiểm khi đặt trong build script/transformer chạy configuration nếu người viết nghĩ chúng chỉ xảy ra khi task được chọn.

| Dấu hiệu trong build logic | Điều có thể xảy ra ngay ở configuration | Hướng đặt đúng |
| --- | --- | --- |
| `println(...)`, `logger.lifecycle(...)` ngoài task | Log ngay cả khi chạy `help`; cache hit có thể bỏ qua | Log chẩn đoán hoặc task action phù hợp |
| `new File(...).text = ...`, `Files.write(...)` | Ghi output khi không có task nào cần | `@OutputFile`/`@OutputDirectory` và `@TaskAction` |
| `delete(...)`, `mkdir(...)` ở top level | Thay đổi filesystem trước task execution | Task có đầu ra/tác vụ dọn phù hợp |
| `"git".execute()`, `ProcessBuilder.start()` | Spawn process dù task không được yêu cầu | Task `Exec` hoặc Provider API chuyên biệt cho giá trị process |
| HTTP client/request trực tiếp | Gọi mạng khi cấu hình, có thể tốn thời gian và khó tái lập | Task có inputs/outputs, timeout và retry hợp lý |
| `System.currentTimeMillis()`, `Math.random()` | Giá trị thay đổi giữa lần cấu hình; khó làm cache đúng | Định nghĩa đầu vào build rõ ràng; nếu cần thời gian thực, dùng task |
| `configuration.files`, `resolvedConfiguration` | Kích hoạt resolution dependency sớm | Dùng `FileCollection`/Provider và truyền vào task input |
| `tasks.create` / `tasks.getByName` / duyệt task collection | Realize task không cần | `register`, `named`, `configureEach` |
| `System.getenv(...)`, `System.getProperty(...)`, `file(...).text` | Đọc input tại configuration | Cân nhắc các Provider built-in; không mặc nhiên là lỗi cache |

**Điểm cuối rất quan trọng:** Trong Gradle hiện đại, việc đọc trực tiếp **environment variable, system property, file hoặc trạng thái filesystem** ở configuration thường **được Configuration Cache theo dõi như configuration input**. Vì thế không nên nói mọi lần gọi `System.getenv` đều “không được track”. Vấn đề chính của đọc sớm là **biến một thay đổi chỉ liên quan tới task thành lý do phải reconfigure cả build**, hoặc làm tác dụng phụ không tương ứng với task. Với nguồn phức tạp/tùy biến, cần kiểm tra khả năng theo dõi thực tế.

### 7.1. Ví dụ nguy hiểm: ghi file trước khi task chạy

~~~groovy
// build.gradle — phản ví dụ; không chạy trên repository thật.
def reportFile = layout.buildDirectory.file('reports/status.txt').get().asFile
reportFile.parentFile.mkdirs()
reportFile.text = 'Đã cấu hình Gradle'

tasks.register('writeStatus') {
    doLast {
        println('Task writeStatus được thực thi')
    }
}
~~~

Vì lệnh `mkdirs()` và gán `text` chạy **ngay khi đánh giá build.gradle**, `./gradlew help` cũng có thể tạo `build/reports/status.txt`. File xuất hiện **không chứng minh** task `writeStatus` đã được thực thi.

Với Configuration Cache, một cache hit có thể bỏ qua configuration nên lần sau file **không được tạo lại** theo cùng cách. Nếu output đã bị xóa ở giữa, việc dựa vào tác dụng phụ configuration sẽ dẫn đến trạng thái khó dự đoán. Các thao tác sinh artifact phải thuộc task có output được khai báo.

### 7.2. Ví dụ nguy hiểm: đưa tác dụng phụ vào `map`

~~~groovy
// build.gradle — phản ví dụ
def configProvider = providers.gradleProperty('stage').orElse('dev')

def transformed = configProvider.map { value ->
    println('CALL REMOTE SERVICE for ' + value)
    // Không thực sự gọi mạng trong ví dụ này.
    return value.toUpperCase()
}
~~~

Đoạn `map` thường **chưa chạy ngay** khi được khai báo. Nhưng nếu Provider này được query trong configuration, trong lúc xác định task input hoặc ở nơi khác, đoạn `println` sẽ chạy **theo thời điểm Gradle yêu cầu giá trị**. Không được dựa vào việc closure chạy đúng một lần, đúng thứ tự hoặc chỉ khi một task cụ thể chạy.

Đúng hơn: để `map` chỉ **biến đổi giá trị thuần**:

~~~groovy
def transformed = providers.gradleProperty('stage')
    .orElse('dev')
    .map { value -> value.toUpperCase(java.util.Locale.ROOT) }
~~~

Nếu cần gọi dịch vụ bên ngoài, hãy xây dựng **task riêng** với dữ liệu đầu vào, output và chiến lược lỗi rõ ràng; đừng nhét network call hoặc file write vào transformer.

## 8. Nguồn Provider: Gradle property, environment, system property và file

Gradle cung cấp các nguồn phù hợp để mô hình hóa dữ liệu cấu hình mà không tự mở giá trị quá sớm:

~~~groovy
// build.gradle — các dòng minh họa nguồn, không tự tạo task
def region = providers.gradleProperty('region').orElse('local')
def buildNumber = providers.environmentVariable('BUILD_NUMBER')
    .orElse('developer')
def platform = providers.systemProperty('os.name')
def banner = providers.fileContents(
    layout.projectDirectory.file('config/banner.txt')
).asText
~~~

| Nguồn | Khởi tạo Provider | Điểm cần chú ý |
| --- | --- | --- |
| `-Pfoo=bar` / `gradle.properties` | `providers.gradleProperty('foo')` | Phù hợp với project property |
| Biến môi trường | `providers.environmentVariable('FOO')` | Đừng in secret; tránh đọc eager nếu chỉ task cần |
| Java system property | `providers.systemProperty('foo')` | Không tự giống project property `-Pfoo` |
| Nội dung một tệp | `providers.fileContents(regularFile).asText` | Giá trị phụ thuộc nội dung file; phù hợp để wire vào task |
| Giá trị tùy chỉnh | `providers.provider { ... }` | Supplier phải thuần/được kiểm soát; cẩn thận việc theo dõi input và Configuration Cache |
| Lệnh bên ngoài | `providers.exec { ... }.standardOutput.asText` | Dùng API chuyên dụng nếu cần output process; tránh chạy trong config trừ khi bắt buộc |

### 8.1. Đọc sớm một file làm thay đổi phạm vi invalidation

~~~groovy
// build.gradle — anti-pattern khi file chỉ dành cho một task
def readmeTextProvider = providers.fileContents(
    layout.projectDirectory.file('config/banner.txt')
).asText

def bannerNow = readmeTextProvider.get()
~~~

Khi `get()` được gọi trong configuration, nội dung `config/banner.txt` trở thành đầu vào được dùng **để cấu hình build**. Gradle có thể phải invalid Configuration Cache và đánh giá lại build khi file thay đổi, ngay cả khi chỉ một task sử dụng file.

Nếu chỉ task `createBanner` cần giá trị, hãy nối Provider/file property vào input của task, để Gradle xử lý thay đổi ở phạm vi task. Việc truy cập file cần nằm trong task action hoặc trong provider input/task fingerprint theo cơ chế được Gradle hỗ trợ.

### 8.2. Environment đọc sớm vẫn có thể được track

~~~groovy
// build.gradle — chỉ minh họa đọc eager
def stageNow = System.getenv('DEPLOY_STAGE') ?: 'local'
~~~

Đây không tự động là lỗi Configuration Cache. Gradle có cơ chế ghi nhận environment variable đọc trong configuration; khi giá trị thay đổi, cache có thể invalid để đảm bảo cấu hình đúng. Nhưng nếu `DEPLOY_STAGE` chỉ ảnh hưởng tới một task, đọc sớm làm cả configuration phụ thuộc nó. Khi đó nên nối:

~~~groovy
def stageProvider = providers.environmentVariable('DEPLOY_STAGE')
    .orElse('local')
~~~

vào property input riêng của task. **Không đọc secret rồi chèn vào logger hoặc text file output công khai**. Gradle có cơ chế bảo vệ Configuration Cache, nhưng vẫn cần quản lý quyền truy cập vào thư mục cache và các input nhạy cảm.

### 8.3. Provider cho process ngoài có giới hạn

Nếu thực sự cần output của một lệnh làm giá trị build:

~~~groovy
// Chỉ minh họa cách khai báo một process-backed provider
def gitRevision = providers.exec {
    commandLine 'git', 'rev-parse', '--short', 'HEAD'
}.standardOutput.asText.map { value -> value.trim() }
~~~

Không được gọi `gitRevision.get()` ở configuration nếu một task riêng mới là consumer. Lưu ý: công cụ `git` phải có trong môi trường, lệnh cần chạy trong repository Git hợp lệ, output và khả năng cache phụ thuộc Gradle và inputs mà cơ chế process provider theo dõi. Provider-backed external process có thể được thực thi khi Gradle xác nhận Configuration Cache còn hợp lệ nếu giá trị đã trở thành **configuration input**, nên **không dùng lệnh tốn kém hoặc có tác dụng phụ** như một nguồn Provider configuration.

Đối với thao tác có trạng thái (gọi API cập nhật dữ liệu, deploy, publish), một **Task** có input/output/quyền thực thi riêng vẫn phù hợp hơn việc ẩn tác dụng phụ trong Provider. `providers.exec` thích hợp cho **đọc output** một công cụ, không phải cơ chế thay cho deployment task.

## 9. Ví dụ đầy đủ về xử lý file: chuyển tác dụng phụ sang task action

Trong một project thử nghiệm, muốn đọc `config/message.txt`, chuyển nội dung sang chữ hoa và tạo `build/generated/message.txt`. Cách đúng là mô hình hóa **file input và output**. Đây là ví dụ khác, độc lập với `PrintGreeting` ở mục 5.

### 9.1. Các file cần tạo

~~~text
file-task-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── config/
    └── message.txt
~~~

Nội dung `settings.gradle`:

~~~groovy
rootProject.name = 'file-task-demo'
~~~

Nội dung `config/message.txt` (một dòng có newline cuối):

~~~text
hello gradle
~~~

### 9.2. `build.gradle` hoàn chỉnh

~~~groovy
import java.util.Locale
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id 'base'
}

abstract class NormalizeMessage extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getSourceFile()

    @OutputFile
    abstract RegularFileProperty getTargetFile()

    @TaskAction
    void normalize() {
        File input = sourceFile.get().asFile
        File output = targetFile.get().asFile

        output.parentFile.mkdirs()
        String content = input.getText('UTF-8')
        output.setText(content.toUpperCase(Locale.ROOT), 'UTF-8')
    }
}

tasks.register('normalizeMessage', NormalizeMessage) {
    sourceFile.set(layout.projectDirectory.file('config/message.txt'))
    targetFile.set(layout.buildDirectory.file('generated/message.txt'))
}
~~~

Chức năng mỗi phần:

- `@InputFile` khai báo file mà task đọc; `@PathSensitive(PathSensitivity.RELATIVE)` làm rõ cách Gradle xét đường dẫn input khi tính fingerprint.
- `@OutputFile` khai báo file task tạo; Gradle có cơ sở để quyết định task `UP-TO-DATE` khi input và output phù hợp.
- `sourceFile.set(layout.projectDirectory.file(...))` truyền **file location bằng Provider-compatible API**, không tự đọc nội dung.
- `targetFile.set(layout.buildDirectory.file(...))` định vị output theo build directory, không tạo file ngay.
- `get()` trong `@TaskAction` lấy file input/output thuộc chính task **khi task cần thao tác thật**.
- `mkdirs()` và `setText(...)` là tác dụng phụ **ở execution**, gắn với task đã đăng ký, thay vì top level trong build script.

### 9.3. Chạy và xác minh

~~~bash
./gradlew normalizeMessage
cat build/generated/message.txt
./gradlew normalizeMessage
~~~

Nội dung file sau lần chạy đầu (không phải toàn bộ log Gradle):

~~~text
HELLO GRADLE
~~~

Lần hai, nếu không thay đổi input/output, Gradle thường báo task `UP-TO-DATE` trong log. Nếu sửa `config/message.txt`, task sẽ được xem xét chạy lại. Đây là **up-to-date checking**; task không tự động lấy kết quả từ remote Build Cache nếu chưa được thiết kế/đánh dấu và cấu hình để cache output.

Trên Windows PowerShell, chạy `.\gradlew.bat normalizeMessage` và dùng `Get-Content build\generated\message.txt` để xem nội dung. File path trên từng hệ điều hành có thể khác, nhưng nội dung chữ hoa đầu ra vẫn như trên.

Với task sản xuất, còn cần xét encoding, newline policy, xử lý lỗi IO và việc output có deterministic hay không. Trong ví dụ, chữ hoa dùng `Locale.ROOT` để tránh thay đổi bất ngờ theo locale máy.

## 10. Phân biệt ba cơ chế thường bị gộp làm một

| Cơ chế | Tác dụng chính | Nó không làm gì? |
| --- | --- | --- |
| **Provider API / Property API** | Biểu diễn và nối nguồn giá trị, hỗ trợ cấu hình lười | Không tự biến hàm có tác dụng phụ thành thuần; không tự đảm bảo mọi supplier chỉ chạy lúc task action |
| **Task configuration avoidance** | Tránh tạo/cấu hình task không cần cho lần build | Không ngăn mã top level trong `build.gradle` chạy khi cấu hình |
| **Configuration Cache** | Lưu/khôi phục kết quả configuration, có thể bỏ qua bước cấu hình trên cache hit | Không cache output task giống Build Cache; không biến logic không tương thích thành an toàn |

**Build Cache** là cơ chế khác: lưu kết quả task dựa trên inputs, implementation và outputs để tái sử dụng. Một build có thể có Configuration Cache hit nhưng vẫn phải chạy task; hoặc task có kết quả `UP-TO-DATE`/`FROM-CACHE` mà configuration vẫn diễn ra. Đừng dùng một dòng log làm kết luận cho cả ba cơ chế.

### 10.1. Side effect configuration rất dễ tạo kết quả lệch với task

~~~groovy
// Phản ví dụ: không dùng cho sinh artifact thật
println('CONFIGURATION: chạy build script')

tasks.register('printExecution') {
    doLast {
        println('EXECUTION: chạy task')
    }
}
~~~

Chạy `./gradlew -q help` có thể in dòng `CONFIGURATION` nhưng không in `EXECUTION` vì task không chạy. Chạy `./gradlew -q printExecution` khi cấu hình bình thường sẽ in cả hai. Với Configuration Cache hit, dòng configuration có thể không xuất hiện do script không được đánh giá lại; task action vẫn chạy khi task được chọn. **Không phụ thuộc vào chính các dòng log configuration để triển khai side effect hay đánh dấu trạng thái “đã hoàn thành”.**

### 10.2. Dùng `afterEvaluate` để ép thứ tự không chữa gốc bệnh

Một dự án cũ có thể dùng:

~~~groovy
afterEvaluate {
    println('Thực hiện công việc cấu hình muộn')
}
~~~

`afterEvaluate` chỉ dời callback tới **cuối quá trình evaluate Project**, không tự chuyển nó sang execution hoặc làm build compatible với Configuration Cache. Nếu callback thực hiện IO, gọi HTTP, truy cập task khác bằng `getByName` hoặc mutate module khác, các vấn đề vẫn còn.

Khi cần chờ plugin để cấu hình task phù hợp:

~~~groovy
plugins.withId('java') {
    tasks.named('compileJava') {
        options.encoding = 'UTF-8'
    }
}
~~~

Đây là **đoạn cấu hình bổ sung** cho một project có Java plugin. `plugins.withId` chạy khi plugin có ID `java` được áp dụng, còn `tasks.named` dùng API configuration avoidance. Không cần `afterEvaluate` chỉ để chờ task được plugin tạo. Nếu build **không áp dụng** Java plugin, callback không chạy, tránh lỗi truy cập task không tồn tại.

## 11. Nhận diện và gỡ eager dependency resolution

Một sai lầm hay gặp là gọi API đòi toàn bộ file đã được phân giải:

~~~groovy
// Phản ví dụ, giả định project đã tạo configuration 'runtimeClasspath'
def dependencyJars = configurations.runtimeClasspath.files
println('Số file runtime: ' + dependencyJars.size())
~~~

Đặt ở top level, đoạn này có thể khiến Gradle phân giải dependency ngay trong configuration, bao gồm tải metadata/artifact cần thiết, dù lần build chỉ cần `help`. Chi phí mạng/đĩa và lỗi resolution không còn được giới hạn ở task cần dependency.

Hướng tốt hơn là để task nhận **FileCollection** hoặc Provider tương ứng:

~~~groovy
// Đoạn cấu hình cho project đã áp dụng plugin 'java'
tasks.register('listRuntimeFiles') {
    def runtimeFiles = configurations.named('runtimeClasspath')

    doLast {
        // Đây chỉ là minh họa ý tưởng, không phải công thức
        // để lưu Configuration trong task action sản xuất.
        println('runtimeClasspath configuration was selected')
    }
}
~~~

Để viết **task thực sự sử dụng classpath**, khai báo `@Classpath ConfigurableFileCollection` trong một typed task, rồi nối `sourceSets.main.runtimeClasspath` hoặc FileCollection vào property từ configuration. Gradle có thể quản lý dependency inference, fingerprint và execution đúng hơn.

Một cách minh họa task input **không truy cập configuration từ action**:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.tasks.Classpath
import org.gradle.api.tasks.TaskAction

plugins {
    id 'java'
}

abstract class CountRuntimeFiles extends DefaultTask {
    @Classpath
    abstract ConfigurableFileCollection getRuntimeFiles()

    @TaskAction
    void count() {
        println('runtime-file-count=' + runtimeFiles.files.size())
    }
}

tasks.register('countRuntimeFiles', CountRuntimeFiles) {
    runtimeFiles.from(sourceSets.main.runtimeClasspath)
}
~~~

Đoạn `build.gradle` này **độc lập**, có thể chạy trên dự án Java hợp lệ bằng `./gradlew -q countRuntimeFiles`, nhưng giá trị số file phụ thuộc dependency và output của dự án nên **không có một stdout số cố định**. Đọc `runtimeFiles.files` trong task action là hành vi của task input thuộc chính task, khác việc đọc `configurations.runtimeClasspath.files` ở top level. Với Configuration Cache, Gradle có thể thực hiện resolution của các configuration trước execution khi serialize task graph; đó là chi tiết của cơ chế cache, không phải lý do để build script chủ động resolve eager.

## 12. Những điểm kiểm tra thực tế khi review code

Khi review một `build.gradle`, plugin Groovy/Java/Kotlin hoặc build logic trong `buildSrc`/`build-logic`, dùng chuỗi câu hỏi:

1. **Mã này chạy khi nào?** Top level của script, closure `map`, action cấu hình task, `@TaskAction`, hay process fork?
2. **Có cần lấy giá trị bây giờ không?** Nếu code chỉ chuyển input cho task, có thể dùng `Property.set(provider)` thay `provider.get()` không?
3. **Có ép realize task không?** Có `TaskProvider.get()`, `getByName`, `tasks.all`, `tasks.create`, hoặc việc duyệt toàn bộ tasks không?
4. **Có tác dụng phụ không?** Có thao tác file/mạng/tiến trình/mutable global state/log với ý nghĩa vận hành không?
5. **Nguồn giá trị có được theo dõi đúng không?** Là Gradle property, environment, system property, file content, command output hay thời gian/giá trị ngẫu nhiên?
6. **Task có khai báo input/output đúng không?** Có `@Input`, `@InputFile`, `@Classpath`, `@OutputFile` và `PathSensitivity` thích hợp không?
7. **Task action có giữ Project/Gradle/Settings không?** Nếu có, cần chuyển dữ liệu cần dùng vào Property/Provider hoặc service phù hợp trước khi execution.
8. **Thay đổi input nào làm Configuration Cache miss, input nào chỉ khiến task chạy lại?** Hãy kiểm tra bằng log và báo cáo, không phỏng đoán.
9. **Có phải hành vi cần thiết ở configuration?** Một số plugin cần đọc version hoặc repository URL để tạo model; nếu có, hãy khai báo nguồn rõ và giữ việc đọc nhanh, xác định được.
10. **Có thể bỏ tác dụng phụ khỏi transformer không?** `map`, `flatMap`, `zip` nên kết hợp giá trị; HTTP/deploy/upload nên là task/operation tường minh.

### 12.1. Dấu hiệu “lazy trên danh nghĩa”

Những dòng này nên kiểm tra kỹ:

~~~groovy
// 1. Tạo Provider rồi mở ngay
def p = providers.gradleProperty('region').orElse('local')
def region = p.get()

// 2. TaskProvider bị ép realize
def compileTask = tasks.named('compileJava').get()

// 3. Cấu hình tất cả task eager
tasks.all {
    println('Configuring ' + name)
}

// 4. Provider transformer có tác dụng phụ
def uppercase = p.map {
    println('Transform ' + it)
    it.toUpperCase()
}

// 5. Truy cập filesystem ngay trong configuration
def appConfig = file('config/app.txt').text

// 6. Gọi lệnh ngay từ build script
def commitText = ['git', 'rev-parse', 'HEAD'].execute().text
~~~

Đây là **các ví dụ nhận diện từng vấn đề**, không phải một build script hoàn chỉnh để dán cùng lúc. Dòng 2 còn yêu cầu task `compileJava` tồn tại (thường do Java plugin), dòng 5 yêu cầu file tồn tại và dòng 6 yêu cầu có Git. Đừng chạy các phản ví dụ trên hệ thống CI/production để “kiểm tra”.

Cách thay thường là: giữ `p`, dùng `map` thuần và `Property.set(p)`; dùng `TaskProvider` nguyên vẹn; chuyển sang `tasks.withType(...).configureEach`; dùng `providers.fileContents(...)` cho dữ liệu file; cấu hình typed task và để thực thi nằm trong action.

## 13. Phân tích các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng chẩn đoán và sửa |
| --- | --- | --- |
| Chạy `./gradlew help` vẫn tải dữ liệu/gọi API | IO hoặc `get()` ở top level/configure callback | Xác định call site, chuyển sang task input + action |
| Task không chạy nhưng file đã được tạo | `Files.write`/`File.text` ở configuration | Khai báo `@OutputFile`, chỉ ghi file trong task action |
| Đổi biến môi trường khiến cấu hình lại toàn build | Đọc env ở configuration và coi nó là configuration input | Dùng `providers.environmentVariable` đưa vào task property |
| Gọi task nhẹ mà rất nhiều task khác được configure | `tasks.create`, `getByName`, `TaskProvider.get()`, `all` | Dùng `register`, `named`, `configureEach`, tìm plugin eager |
| Có `Provider.map` nhưng hành vi không nhất quán | Transformer có IO, side effect, phụ thuộc thời gian | Làm transformer thuần; dữ liệu bất ổn chuyển thành input task |
| `Provider.get()` báo không có giá trị | Property chưa được cung cấp, supplier trả absent/null | Xem nguồn, dùng `orElse` khi có default hợp lệ; validate input bắt buộc |
| Lỗi Configuration Cache về Project ở task execution | Action/chữ ký closure capture `project` hoặc script instance | Typed task với `@Input Property`, tránh `project`/`Gradle` trong `@TaskAction` |
| Cache hit khiến callback tạo file không chạy | Side effect đặt ở configuration bị bỏ qua | Chuyển việc sinh file vào task có output |
| Build chậm do phân giải dependency khi chưa cần | `configurations.foo.files` ở configuration | Đưa classpath/FileCollection vào input task |
| Task chạy lại dù input “không đổi” | Input chưa được khai báo đầy đủ, biến ngoài/clock/random, output bị sửa | Kiểm tra task input/output, log up-to-date và nguồn dữ liệu |
| `--configuration-cache` báo problem khi lưu | Task giữ model object không serialize hoặc callback không được hỗ trợ | Đọc report, sửa logic rồi chạy lại, không chỉ tắt cảnh báo |
| Provider chứa password in ra log | Logging `get()` hoặc map có println; credential nằm trong task state | Không log secret; xử lý credential qua provider/credential API và quyền cache phù hợp |

### 13.1. Đừng “chữa” bằng cách tắt mọi cache

Câu lệnh `--no-configuration-cache` có thể giúp **khoanh vùng** lỗi nhưng không giải quyết gốc vấn đề. Nếu output task được tạo trong configuration, tắt cache khiến nó có vẻ chạy “đúng” mỗi lần nhưng vẫn bị sinh khi người dùng chạy task khác. Chuyển trách nhiệm vào task và khai báo đầu vào/đầu ra mới là sửa đúng.

Tương tự, tăng `org.gradle.jvmargs` hoặc `--max-workers` không sửa được build mất thời gian vì HTTP call ở configuration. Cần đo chính xác thời điểm chậm và đặt operation đúng vòng đời.

## 14. Quy trình kiểm chứng từng bước

### Bước 1 — tạo baseline

Trong demo dùng `PrintGreeting` và/hoặc `NormalizeMessage`:

~~~bash
./gradlew help --info
./gradlew showGreeting --info
~~~

Quan sát lệnh `help` không cần input/output của các task demo; nếu nó vẫn gây HTTP call/file write/tải dữ liệu cho task không liên quan, tìm các side effect ở configuration.

### Bước 2 — chạy Configuration Cache

~~~bash
./gradlew showGreeting --configuration-cache
./gradlew showGreeting --configuration-cache
~~~

Kiểm tra log cache store/reuse. Với plugin/script lớn, đọc **báo cáo Configuration Cache** nếu Gradle chỉ ra issue. Một lần chạy thành công không chứng minh mọi task hoặc mọi cấu hình build đều tương thích; cần thử các task path đại diện.

### Bước 3 — thay đổi một input có chủ đích

~~~bash
./gradlew showGreeting --configuration-cache -Pgreeting=first
./gradlew showGreeting --configuration-cache -Pgreeting=second
~~~

Xem task output có phản ánh từng giá trị không. Với file task, sửa `config/message.txt` rồi chạy lại `normalizeMessage`; nội dung output phải thay đổi theo input, và Gradle phải có lý do chính đáng để thực thi lại.

### Bước 4 — phân biệt cache và up-to-date

~~~bash
./gradlew normalizeMessage
./gradlew normalizeMessage
./gradlew normalizeMessage --rerun-tasks
~~~

`--rerun-tasks` ép Gradle chạy lại task thay vì bỏ qua do trạng thái up-to-date; nó không thay thế việc khai báo input/output. Khi dùng Configuration Cache đồng thời, xem thông báo của từng cơ chế để phân biệt chúng.

### Bước 5 — tìm nơi eager xảy ra

- Tìm `get()`/`getOrNull()`/`isPresent()` trong top-level script, plugin `apply(...)`, action cấu hình task và provider transformer.
- Tìm `tasks.create`, `tasks.getByName`, `tasks.all`, `withType(Type) { ... }` và `TaskProvider.get()`.
- Tìm `File.write`, `Files.write`, `delete`, `mkdir`, `ProcessBuilder`, `execute()`, HTTP client và static mutable state.
- Đối chiếu stack trace, `--info` hoặc Build Scan/profile khi cần xác định task được realize và chi phí configuration.
- Xem code của plugin bên thứ ba nếu có side effect mà `build.gradle` không chứa.

Không kết luận rằng mọi dòng `get()` đều xấu chỉ dựa vào tìm kiếm chuỗi; xem **thời điểm, tác nhân, lý do cần giá trị và API nhận**.

## 15. Bài tập thực hành

**Bài 1 — đọc sớm hay nối lười?** Cho ba đoạn:

~~~groovy
def source = providers.gradleProperty('branch').orElse('main')
def a = source.map { it.toUpperCase(java.util.Locale.ROOT) }
def b = a.get()
~~~

Hãy chỉ ra bước nào tạo Provider mới và bước nào buộc tra cứu giá trị. Trả lời: `source` và `a` là Provider; `a.get()` đọc giá trị và chạy transformer khi cần.

**Bài 2 — tìm tác dụng phụ.** Trong phản ví dụ `reportFile.text = '...'` ở mục 7, thử tưởng tượng lệnh `help`. File output có thể xuất hiện không? Trả lời: có, vì thao tác ghi file đang ở configuration. Hãy chuyển thành task như `NormalizeMessage`.

**Bài 3 — task bị realize.** Một plugin gọi `tasks.named('report').get()` ngay sau `register`. Khi chạy task khác, action cấu hình `report` có thể được thực thi không? Trả lời: có. Loại bỏ `get()` và truyền TaskProvider vào nơi cần.

**Bài 4 — thay input file.** Trong `NormalizeMessage`, đổi `hello gradle` thành `good morning` và chạy lại. Nội dung đầu ra dự kiến là `GOOD MORNING` (giữ newline cuối nếu file đầu vào có). Giải thích tại sao Gradle có thể nhận biết thay đổi nhờ `@InputFile`.

**Bài 5 — kiểm tra cache.** Chạy một task hai lần với `--configuration-cache`, sau đó thay `-P`. Ghi lại cache hit/miss và task output thực tế. Giải thích kết quả dựa trên việc giá trị được đọc ở **configuration** hay được nối vào **task input**; không khẳng định một kết quả cố định cho mọi phiên bản/plugin.

**Bài 6 — transformer thuần.** Thay một `Provider.map { ... }` có lệnh `println` và HTTP request bằng một hàm chỉ biến đổi String. Chuyển HTTP request thành task có input xác định, timeout, kiểm soát lỗi và output rõ ràng. Chỉ gọi endpoint bạn có quyền dùng, trong môi trường thử nghiệm.

## 16. Ghi nhớ khi viết build logic

1. `Provider` là một **nguồn giá trị**; `Property.set(provider)` nối dữ liệu mà không bắt buộc tự đọc ở configuration.
2. `get()`, `getOrElse`, `orNull` và `isPresent` đều có thể buộc tra cứu giá trị. Hãy xem **lúc gọi** và **mục đích**.
3. `map`, `flatMap`, `zip` và `orElse` giúp dựng chuỗi lazy. Transformer nên **thuần, không có tác dụng phụ**.
4. `TaskProvider.get()` có thể realize task; ưu tiên `tasks.register`, `tasks.named` và `configureEach`.
5. File write, network request, process spawn, deploy và xuất artifact thuộc trách nhiệm **task action**, với input/output và lỗi được định nghĩa rõ.
6. Environment/file reads ở configuration **có thể được Gradle theo dõi**; đọc sớm vẫn làm phạm vi invalidation lớn hơn. Không gọi chúng luôn “không track”.
7. **Configuration Cache**, **Build Cache** và **task configuration avoidance** giải quyết các vấn đề khác nhau; dùng đúng log và thử nghiệm để đánh giá.
8. Với task production, ưu tiên **typed task, Provider/Property input, file output và API Gradle managed state**; tránh giữ `Project` hoặc script instance trong task action.
9. Đọc Provider ở configuration là chấp nhận được nếu API thực sự cần giá trị để xây model, nhưng phải hiểu chi phí và tính cacheable của nguồn.
10. Mục tiêu không phải “không bao giờ gọi `get()`”, mà là **đọc giá trị đúng lúc, ở đúng đối tượng chịu trách nhiệm, không làm thêm công việc ngoài yêu cầu của build**.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): `Provider`, `Property`, `map`, `flatMap`, `orElse` và lazy wiring.
- [Gradle User Manual — Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `TaskProvider`, `register`, `named`, `configureEach` và eager API cần tránh.
- [Gradle User Manual — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): typed task, `@Input`, `Property`, `@TaskAction` và input/output.
- [Gradle User Manual — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): vòng đời build, cache hit/miss, configuration inputs và phân biệt với Build Cache.
- [Gradle User Manual — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): đọc file/env ở configuration, Provider input, Project access trong execution.
- [Gradle User Manual — Enabling and Configuring Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_enabling.html): bật `--configuration-cache` và kiểm tra báo cáo.
- [Gradle User Manual — Worker API](https://docs.gradle.org/current/userguide/worker_api.html): mô hình tác vụ/process khi viết plugin và task nâng cao.
