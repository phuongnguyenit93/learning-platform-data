# Đọc giá trị bằng providers.gradleProperty và providers.environmentVariable

## 1. Bài toán: cùng một build, nhiều môi trường

Một dự án Gradle thường cần cấu hình khác nhau giữa máy lập trình viên và CI: tên môi trường, tên artifact, mức log, đường dẫn SDK, địa chỉ dịch vụ kiểm thử hoặc thông tin xác thực. Những giá trị này không nên bị viết cố định trong `build.gradle(.kts)`.

Ví dụ, máy cá nhân muốn chạy task với `audience=developers` và `APP_CHANNEL=local`, còn CI truyền `audience=ci-team` và `APP_CHANNEL=ci`. Gradle cung cấp **Provider API** để mô tả nguồn giá trị, trì hoãn việc đọc và nối giá trị đó với cấu hình task:

~~~kotlin
// build.gradle.kts
val audience = providers.gradleProperty("audience").orElse("developers")
val channel = providers.environmentVariable("APP_CHANNEL").orElse("local")
~~~

Hai biến trên có kiểu `Provider<String>`. Chúng **không phải** hai chuỗi `String` đọc sẵn ngay khi khai báo.

Hãy ghi nhớ sự khác biệt nền tảng:

- `providers.gradleProperty("audience")` tìm **Gradle project property** tên `audience` từ các nguồn build-level mà Gradle hỗ trợ, ví dụ tham số `-Paudience=...` hoặc `gradle.properties`.
- `providers.environmentVariable("APP_CHANNEL")` tìm **biến môi trường của tiến trình Gradle** tên `APP_CHANNEL`. Nó không tự đọc file `.env`.
- Cả hai trả về một `Provider<String>`, giúp nối dữ liệu với task/property khác. Khi chưa có nguồn, provider **không có giá trị**; đối tượng Provider vẫn tồn tại.
- `orElse("...")` tạo provider có giá trị dự phòng khi nguồn không tồn tại; còn chuỗi rỗng thường vẫn là một giá trị **đang tồn tại**.

Bài học tập trung vào cách đọc hai nguồn trên, biến đổi và chuyển giá trị vào task đúng cách, cùng những lỗi thường xảy ra với configuration cache, CI và thông tin nhạy cảm.

## 2. Phân biệt bốn khái niệm dễ nhầm

| Khái niệm | Ví dụ | Dùng cách nào? |
| --- | --- | --- |
| Gradle project property | `-Paudience=team`, dòng `audience=team` trong `gradle.properties` | `providers.gradleProperty("audience")` |
| OS environment variable | `APP_CHANNEL=ci` được truyền từ shell/CI | `providers.environmentVariable("APP_CHANNEL")` |
| JVM system property | `-Ddemo.mode=preview` | `providers.systemProperty("demo.mode")` |
| Extra property gắn vào Project | `extra["customLabel"] = "x"` | API `extra`/`findProperty` khi thực sự cần, **không** coi là nguồn của `providers.gradleProperty` |

**Quan hệ đặt tên không tạo phép chuyển đổi tự động.** Nếu đặt `APP_CHANNEL=ci` trong shell, `providers.gradleProperty("APP_CHANNEL")` không đọc được biến đó chỉ vì trùng tên. Nếu đặt `audience=team` trong `gradle.properties`, `providers.environmentVariable("audience")` không đọc được dòng đó.

Có một **quy ước chuyển riêng**: biến môi trường có tiền tố `ORG_GRADLE_PROJECT_` có thể cung cấp **Gradle project property** tương ứng. Ví dụ `ORG_GRADLE_PROJECT_audience=team` giúp `providers.gradleProperty("audience")` tìm được `team`. Đây là tính năng dành riêng cho project properties; không có nghĩa mọi biến môi trường đều tự động trở thành project property.

Ngoài hai hàm chính của bài, `providers.systemProperty("demo.mode")` hữu ích khi muốn đọc một JVM system property. Đừng dùng `System.getenv(...)` để đọc JVM system property hoặc `System.getProperty(...)` để đọc OS environment variable: chúng là hai namespace khác nhau.

## 3. Cú pháp căn bản trong Groovy DSL và Kotlin DSL

### 3.1. Kotlin DSL (`build.gradle.kts`)

~~~kotlin
val targetProvider = providers.gradleProperty("target")
val regionProvider = providers.environmentVariable("APP_REGION")

val targetWithFallback = targetProvider.orElse("dev")
val regionWithFallback = regionProvider.orElse("local")
~~~

`val` khai báo tham chiếu Kotlin; không nhất thiết lấy giá trị thật. `providers` là `ProviderFactory` của Gradle trong ngữ cảnh build script.

Bảng kiểu:

| Biểu thức | Kiểu và ý nghĩa |
| --- | --- |
| `providers.gradleProperty("target")` | `Provider<String>`; có thể không có giá trị |
| `providers.environmentVariable("APP_REGION")` | `Provider<String>`; có thể không có giá trị |
| `provider.orElse("dev")` | `Provider<String>` mới, có giá trị dự phòng |
| `provider.get()` | `String` nếu có giá trị; ném lỗi nếu không có |
| `provider.orNull` | `String?`; bằng `null` nếu không có giá trị |
| `provider.isPresent` | `Boolean` cho biết provider có giá trị khi được truy vấn |
| `provider.getOrElse("dev")` | `String` đã được giải quyết tại thời điểm gọi |
| `provider.map { ... }` | Provider mới chứa giá trị được biến đổi lười khi nguồn tồn tại |

Ở Kotlin DSL, muốn giữ tính lười thì **giữ đối tượng Provider** hoặc nối nó tới `Property<T>` của Gradle. Gọi `get()`/`orNull`/`getOrElse(...)` là đọc giá trị ngay tại vị trí gọi; đặt các lời gọi ấy ở top-level của script sẽ yêu cầu dữ liệu trong configuration.

### 3.2. Groovy DSL (`build.gradle`)

~~~groovy
def targetProvider = providers.gradleProperty('target')
def regionProvider = providers.environmentVariable('APP_REGION')

def targetWithFallback = targetProvider.orElse('dev')
def regionWithFallback = regionProvider.orElse('local')
~~~

Hai DSL dùng cùng Provider API. Groovy dùng `def`, cho phép chuỗi nháy đơn; Kotlin dùng `val` và chuỗi nháy đôi. Tên `gradleProperty`, `environmentVariable`, `orElse` và ý nghĩa đều nhất quán.

### 3.3. Ví dụ hiển thị thông tin có sẵn

**Đoạn minh họa** sau có thể đặt vào một `build.gradle.kts` hợp lệ:

~~~kotlin
val mode = providers.gradleProperty("buildMode").orElse("development")

tasks.register("printBuildMode") {
    doLast {
        println("mode=" + mode.get())
    }
}
~~~

Chạy:

~~~bash
gradle --quiet printBuildMode
gradle -PbuildMode=production --quiet printBuildMode
~~~

Giả sử không có `buildMode` từ nguồn nào khác, stdout hai lần chạy lần lượt là:

~~~text
mode=development
~~~

~~~text
mode=production
~~~

Ví dụ dùng `get()` trong action để người học thấy thời điểm dữ liệu được yêu cầu; với task dùng lâu dài và Configuration Cache, **cách chặt chẽ hơn là nối Provider vào thuộc tính `@Input Property<String>` của task**, như ví dụ hoàn chỉnh ở mục 8. Không sử dụng `println` tương tự để lộ token hoặc mật khẩu.

## 4. `providers.gradleProperty` đọc giá trị từ đâu?

### 4.1. Các nguồn được Gradle tìm kiếm

Theo Gradle ProviderFactory API, `providers.gradleProperty("key")` giải quyết một **build-level Gradle project property** từ các nguồn theo mức ưu tiên:

| Ưu tiên | Nguồn | Ví dụ |
| --- | --- | --- |
| 1 — cao nhất | CLI project property | `gradle -Ptarget=cli build` |
| 2 | JVM system property với tiền tố `org.gradle.project.` | `gradle -Dorg.gradle.project.target=jvm build` |
| 3 | Environment variable với tiền tố `ORG_GRADLE_PROJECT_` | `ORG_GRADLE_PROJECT_target=env` |
| 4 | `gradle.properties` trong Gradle User Home | `~/.gradle/gradle.properties` |
| 5 | `gradle.properties` ở build root | `<root>/gradle.properties` |
| 6 | `gradle.properties` trong Gradle installation | Tệp cấu hình phân phối Gradle |

**Dòng có ưu tiên cao hơn thắng** khi cùng một key tồn tại từ nhiều nguồn. Ví dụ file root chứa `target=root`, nhưng CLI truyền `-Ptarget=cli`, thì provider trả về `cli`.

Lưu ý: `GRADLE_USER_HOME` có thể được cấu hình sang thư mục khác; `~/.gradle` chỉ là vị trí mặc định thường gặp. Nguồn và thứ tự là quy tắc của **`providers.gradleProperty`**; không suy luận rằng mọi API truy cập Project property đều tra cứu cùng bộ nguồn.

### 4.2. Khai báo trong gradle.properties

Ví dụ tại build root:

~~~properties
# gradle.properties
target=developers
releaseChannel=preview
maxWorkersForDemo=4
~~~

Đọc trong `build.gradle.kts`:

~~~kotlin
val target = providers.gradleProperty("target")
val channel = providers.gradleProperty("releaseChannel").orElse("local")
val workerCount = providers.gradleProperty("maxWorkersForDemo")
    .map { it.toInt() }
    .orElse(2)
~~~

Tệp `gradle.properties` lưu **chuỗi văn bản**. Vì vậy `providers.gradleProperty("maxWorkersForDemo")` trả về `Provider<String>`; muốn dùng như số nguyên thì phải chuyển kiểu bằng `map { it.toInt() }`, có kiểm tra lỗi nếu người dùng nhập sai.

Giá trị trong ví dụ `gradle.properties` là dữ liệu minh họa, không phải các cài đặt mặc định toàn hệ thống. Chỉ những key Gradle nhận diện làm thuộc tính đặc biệt (ví dụ `org.gradle.jvmargs`) mới có tác động đặc thù; một key tùy ý như `target` không tự đổi tính năng build trừ khi build logic sử dụng.

### 4.3. Truyền từ CLI với -P

~~~bash
gradle -Ptarget=backend printBuildMode
~~~

`-Pkey=value` là cú pháp truyền **project property**. Với ví dụ trên, nếu task đọc key `buildMode` thì tham số `-Ptarget` sẽ **không** ảnh hưởng; tên key phải khớp.

Lệnh đúng cho task ở mục 3.3 là:

~~~bash
gradle -PbuildMode=backend --quiet printBuildMode
~~~

Stdout:

~~~text
mode=backend
~~~

Nhiều project properties có thể được truyền bằng nhiều tham số `-P`:

~~~bash
gradle -PbuildMode=release -Ptarget=backend tasks
~~~

CLI `-P` được dùng nhiều trong CI để đưa vào các giá trị thông thường có mức ưu tiên rõ. Với bí mật, cân nhắc môi trường bí mật của CI hoặc Gradle credentials API để tránh lộ giá trị trong lịch sử shell, command-line/process listings và log.

### 4.4. Gradle property qua biến môi trường có tiền tố

Trên bash:

~~~bash
export ORG_GRADLE_PROJECT_target=ci
gradle --quiet printTarget
~~~

Lệnh `printTarget` ở trên chỉ là **một task giả định** đọc `providers.gradleProperty("target")`; nó không tự tồn tại trong Gradle. Bạn có thể chạy task `showConfig` hoàn chỉnh ở mục 8 để thử cơ chế này.

Nếu có cả `ORG_GRADLE_PROJECT_target=ci` và `-Ptarget=cli`, `gradleProperty("target")` sẽ dùng `cli` vì tham số `-P` có ưu tiên cao hơn.

**Cẩn thận với tên và chữ hoa:** `ORG_GRADLE_PROJECT_target` có hậu tố `target`; không tùy tiện viết thành `ORG_GRADLE_PROJECT_TARGET` nếu build đọc tên `target` và môi trường/Gradle phân biệt key. Tên biến môi trường có thể bị hệ điều hành xử lý khác nhau về chữ hoa/chữ thường, nên giữ đúng tên được ghi trong cấu hình.

### 4.5. Không phải mọi Project property đều là Gradle build-level property

`providers.gradleProperty("key")` **không** bao gồm các extra properties tự gán bằng `extra["key"] = ...` và các giá trị động gắn vào từng đối tượng `Project`. API này cũng không tìm `gradle.properties` nằm tùy ý bên trong các thư mục subproject. Nó đọc các nguồn **cấp build** được Gradle định nghĩa.

Nếu một build cũ dùng `project.findProperty("key")` hoặc `project.property("key")`, đừng mặc định rằng thay máy móc bằng `providers.gradleProperty("key")` vẫn bao phủ mọi nguồn. Đối chiếu xem key hiện đến từ CLI/file Gradle hay từ plugin/extra property bên trong một project.

## 5. `providers.environmentVariable` đọc môi trường nào?

### 5.1. Biến môi trường của tiến trình Gradle

~~~kotlin
val channel = providers.environmentVariable("APP_CHANNEL").orElse("local")
~~~

Hàm tìm biến tên **APP_CHANNEL** trong môi trường của tiến trình đang thực thi Gradle, ví dụ các biến được terminal hoặc CI runner truyền vào khi khởi chạy build.

Nó **không** tìm một dòng `APP_CHANNEL=...` trong `gradle.properties`, và Gradle **không mặc định** tải file `.env` của ứng dụng. Muốn dùng `.env`, phải có cơ chế nạp cụ thể bên ngoài Gradle hoặc plugin được cấu hình rõ, nhưng thường không cần làm vậy khi CI đã cung cấp biến môi trường trực tiếp.

### 5.2. Truyền giá trị từ các shell

**macOS/Linux (bash hoặc shell tương tự):**

~~~bash
export APP_CHANNEL=ci
./gradlew --quiet showConfig
~~~

Hoặc truyền trong đúng một lệnh:

~~~bash
APP_CHANNEL=ci ./gradlew --quiet showConfig
~~~

**Windows PowerShell:**

~~~powershell
$env:APP_CHANNEL = "ci"
.\gradlew.bat --quiet showConfig
~~~

**Windows Command Prompt (cmd):**

~~~bat
set APP_CHANNEL=ci
gradlew.bat --quiet showConfig
~~~

Các lệnh giả định project có Gradle Wrapper và task `showConfig` từ ví dụ hoàn chỉnh ở mục 8. Nếu chưa tạo Wrapper, dùng `gradle` đã cài tương thích. Lệnh đặt biến môi trường trong shell có thể ảnh hưởng tới các lệnh chạy sau trong cùng phiên làm việc; hãy xóa hoặc thay đổi khi chuyển môi trường.

### 5.3. Điều gì xảy ra khi biến chưa tồn tại?

~~~kotlin
val raw = providers.environmentVariable("APP_CHANNEL")
val safe = raw.orElse("local")
~~~

Nếu không có `APP_CHANNEL`:

- `raw.isPresent` là `false` khi truy vấn;
- `raw.orNull` là `null`;
- `raw.get()` phát sinh lỗi thiếu giá trị;
- `safe.get()` trả về `local`.

Nếu `APP_CHANNEL` **được định nghĩa nhưng rỗng**, provider thường trả về chuỗi rỗng `""`; `orElse("local")` không thay thế chuỗi rỗng vì đó vẫn là một giá trị được cung cấp. Để coi giá trị trắng/rỗng là không hợp lệ hoặc cần dự phòng, hãy chuẩn hóa ở bước `map` (mục 7).

### 5.4. Giá trị môi trường trong Gradle và ứng dụng Java

Environment variable mà tiến trình Gradle nhận được thường cũng nằm trong môi trường được truyền cho process con nếu không bị thay đổi, nhưng không nên nhầm việc **đọc biến trong build script** với **cấu hình đầu vào riêng cho ứng dụng đang chạy**.

Đặc biệt, `-PappMode=demo` chỉ đặt Gradle project property; nó **không tự tạo** biến môi trường `APP_MODE` hoặc JVM system property `appMode` bên trong ứng dụng Java. Muốn truyền một giá trị có chủ ý sang JavaExec/test process, hãy cấu hình task của process đó với API thích hợp như `environment(...)`/`systemProperty(...)` và cân nhắc thời điểm đọc provider.

## 6. Provider là một mô tả giá trị, không chỉ là một String

Provider API hỗ trợ lập trình khai báo, cấu hình lười và việc Gradle theo dõi nguồn đầu vào.

### 6.1. Không có giá trị, giá trị rỗng và giá trị mặc định

~~~kotlin
val optionalLabel = providers.gradleProperty("artifactLabel")

// Chỉ đọc khi thật sự cần một chuỗi:
val fallbackNow: String = optionalLabel.getOrElse("sample")

// Giữ dạng provider cho task:
val fallbackLater: Provider<String> = optionalLabel.orElse("sample")
~~~

Trong `build.gradle.kts`, Gradle có thể cung cấp kiểu `Provider` qua implicit imports; nếu muốn tường minh:

~~~kotlin
import org.gradle.api.provider.Provider
~~~

Phân biệt:

- `get()`: yêu cầu giá trị hiện tại; lỗi nếu không có.
- `orNull`: trả về nullable value khi được gọi.
- `isPresent`: cho biết trạng thái hiện tại khi được gọi, không thay thế việc kiểm tra hợp lệ nghiệp vụ.
- `getOrElse(default)`: trả về **giá trị cụ thể ngay tại chỗ**.
- `orElse(default)`: trả về **Provider mới**, thường phù hợp hơn để nối vào task property.

Đọc `get()` trong phần top-level của script có thể khiến một giá trị môi trường trở thành **configuration input**. Đây không phải lỗi cú pháp nhưng có thể khiến configuration cache phải đánh giá lại cấu hình khi giá trị đổi. Nếu task mới là nơi dùng giá trị, truyền Provider vào task property và để Gradle đọc khi task chạy thường tốt hơn.

### 6.2. Thực hành: so sánh missing và empty

Giả sử:

~~~kotlin
val label = providers.gradleProperty("label").orElse("default-label")
~~~

| Cách gọi | `label.get()` | Tại sao |
| --- | --- | --- |
| Không có thuộc tính `label` ở bất cứ nguồn nào | `default-label` | Giá trị dự phòng được dùng khi missing |
| `-Plabel=blue` | `blue` | Giá trị được cung cấp |
| `-Plabel=` | Chuỗi rỗng | Thuộc tính có mặt nhưng rỗng |
| `gradle.properties` chứa `label=green`, CLI `-Plabel=blue` | `blue` | CLI ưu tiên cao hơn file |

Nếu cần từ chối giá trị trống hoặc có ký tự không hợp lệ, đừng chỉ dựa vào `orElse`.

### 6.3. Chuyển đổi kiểu dữ liệu

Gradle property và environment variable đều cung cấp **chuỗi**. Ví dụ đọc cờ boolean:

~~~kotlin
val enabled = providers.gradleProperty("featureEnabled")
    .map { raw -> raw.equals("true", ignoreCase = true) }
    .orElse(false)
~~~

`enabled` là một `Provider<Boolean>`. Nếu chuỗi là `"true"` hoặc `"TRUE"` thì kết quả là `true`; `"false"` hoặc giá trị bất kỳ khác thành `false`. Nếu cần từ chối typo như `"tru"`, hãy viết validation chặt chẽ thay vì âm thầm biến nó thành false.

Một cách kiểm tra số nguyên:

~~~kotlin
val retryCount = providers.gradleProperty("retryCount")
    .map { raw ->
        val parsed = raw.toIntOrNull()
            ?: error("retryCount phải là số nguyên: '$raw'")
        require(parsed in 0..10) {
            "retryCount phải nằm trong khoảng 0..10"
        }
        parsed
    }
    .orElse(3)
~~~

Provider này chỉ ném lỗi khi giá trị được yêu cầu và đầu vào không hợp lệ. Ví dụ trên là **đoạn khai báo** đặt trong `build.gradle.kts`, không phải chương trình độc lập. Khi nối provider vào typed task input, việc kiểm tra chỉ phát sinh khi Gradle cần giá trị.

### 6.4. Tách trách nhiệm: biến đổi dữ liệu ở Provider, công việc ở task

~~~kotlin
val audience = providers.gradleProperty("audience")
    .map { it.trim().ifEmpty { "developers" } }
    .orElse("developers")

val channel = providers.environmentVariable("APP_CHANNEL")
    .map { it.trim().lowercase() }
    .orElse("local")
~~~

`map { ... }` tạo **derived provider**. Nếu source không có giá trị, mapper không được gọi; `orElse` cung cấp dự phòng. Nếu source là chuỗi rỗng hoặc toàn dấu cách, cách viết ở trên chuẩn hóa `audience` thành `developers`. Với `channel`, nếu bạn muốn chuỗi trống cũng thành `local`, cần thêm `ifEmpty { "local" }` sau `trim()`.

Không gọi `.get()` ở giữa một chuỗi biến đổi chỉ để nhận `String` rồi tạo Provider khác. Cách đó dễ làm mất lợi ích của cấu hình lười.

## 7. Biến đổi Provider: map, flatMap, orElse và chọn nguồn

### 7.1. `map`: đổi giá trị mà chưa cần đọc ngay

~~~kotlin
val releaseName = providers.gradleProperty("releaseName")
    .map { raw -> raw.trim().uppercase() }
    .orElse("SNAPSHOT")
~~~

Nếu truyền `-PreleaseName=beta`, provider cho `BETA`; nếu thiếu key thì dùng `SNAPSHOT`.

### 7.2. `flatMap`: đầu ra là một Provider khác

`map` phù hợp khi lambda trả về giá trị thông thường. `flatMap` phù hợp khi lambda trả về **một Provider**, tránh tạo `Provider<Provider<T>>`:

~~~kotlin
val source = providers.gradleProperty("channelSource")
    .orElse("APP_CHANNEL")

val selectedChannel = source.flatMap { envName ->
    providers.environmentVariable(envName)
}.orElse("local")
~~~

Ví dụ:

- Không có `channelSource`: Gradle tìm biến `APP_CHANNEL`.
- `-PchannelSource=ALT_CHANNEL`: Gradle tìm biến `ALT_CHANNEL`.
- Nếu biến môi trường được chọn không tồn tại: dùng `local`.

Cú pháp này là **một đoạn minh họa** sử dụng trong project build script; nó không tự tạo task. API `ProviderFactory.environmentVariable` còn có overload nhận một `Provider<String>` làm tên biến, nên cũng có thể dùng `providers.environmentVariable(source)` khi phù hợp.

Nên giữ logic chọn nguồn dễ hiểu. Đừng dùng việc dò toàn bộ biến môi trường khi chỉ cần một hoặc vài tên cụ thể.

### 7.3. `orElse` lấy nguồn dự phòng, không thay thế chuỗi rỗng

Ví dụ chọn từ hai nguồn theo thứ tự bạn tự định nghĩa:

~~~kotlin
val publishChannel = providers.gradleProperty("publishChannel")
    .orElse(providers.environmentVariable("PUBLISH_CHANNEL"))
    .orElse("local")
~~~

Cách hiểu: nếu có Gradle property `publishChannel` thì lấy nó; nếu không, xem biến môi trường `PUBLISH_CHANNEL`; nếu cả hai đều thiếu, lấy `local`. Đây là **thứ tự do chính script định nghĩa**, độc lập với thứ tự nguồn nội bộ của `gradleProperty`.

Nếu `-PpublishChannel=` (rỗng), provider có giá trị rỗng và các nguồn dự phòng phía sau sẽ không được chọn. Hãy chuẩn hóa hoặc validate nếu yêu cầu input không rỗng.

### 7.4. Tham chiếu vào Property<T> của task

Các kiểu Gradle phổ biến gồm:

- `Property<String>`: giá trị String có thể được cung cấp trực tiếp hoặc từ `Provider<String>`.
- `Property<Int>` / `Property<Boolean>`: giá trị đã chuyển kiểu.
- `RegularFileProperty` và `DirectoryProperty`: vị trí file/thư mục theo Provider API.
- `ListProperty<T>`, `MapProperty<K,V>`: collections do Gradle quản lý.

Ví dụ hình thức:

~~~kotlin
// Trong block cấu hình một task có thuộc tính "channel":
channel.set(providers.environmentVariable("APP_CHANNEL").orElse("local"))
~~~

Dòng `channel.set(...)` chỉ hợp lệ nếu `channel` thực sự là `Property<String>` trong receiver tương ứng. Không thể đặt tự do một dòng này ở top-level rồi mong Gradle tự hiểu đó là thuộc tính của task nào.

## 8. Dự án hoàn chỉnh chạy được: Gradle Kotlin DSL + Java 17

Thí nghiệm này là bài tập chính. Nó dùng **JDK 17** và Gradle tương thích; không cần plugin ngoài hay dependency repository để in giá trị. Trong dự án thực tế, ưu tiên Gradle Wrapper đã được lưu trong repository.

### 8.1. Cấu trúc thư mục

~~~text
provider-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
~~~

### 8.2. Tệp settings.gradle.kts

~~~kotlin
rootProject.name = "provider-lab"
~~~

### 8.3. Tệp build.gradle.kts

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

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

// Lớp task có input rõ ràng. Không truy cập Project trong @TaskAction.
abstract class ShowConfigTask : DefaultTask() {
    @get:Input
    abstract val audience: Property<String>

    @get:Input
    abstract val channel: Property<String>

    @TaskAction
    fun show() {
        println("Audience=" + audience.get())
        println("Channel=" + channel.get())
    }
}

// Hai Provider giữ giá trị ở dạng lười.
val audienceSource = providers.gradleProperty("audience")
    .map { it.trim().ifEmpty { "developers" } }
    .orElse("developers")

val channelSource = providers.environmentVariable("APP_CHANNEL")
    .map { it.trim().ifEmpty { "local" } }
    .orElse("local")

tasks.register<ShowConfigTask>("showConfig") {
    group = "learning"
    description = "Đọc Gradle property và environment variable"
    audience.set(audienceSource)
    channel.set(channelSource)
}
~~~

**Giải thích quan trọng:**

1. `providers.gradleProperty("audience")` giữ nguồn build-level property dạng `Provider<String>`. Mặc định `developers`.
2. `providers.environmentVariable("APP_CHANNEL")` giữ nguồn từ OS environment. Mặc định `local`.
3. `map { ... }` xử lý trường hợp chuỗi trống/toàn dấu cách để bài học không lẫn missing với empty.
4. `ShowConfigTask` khai báo hai input bằng `@get:Input` và `Property<String>`. Gradle biết giá trị nào ảnh hưởng đến task.
5. Trong block `tasks.register<ShowConfigTask>`, `set(provider)` nối nguồn đầu vào, **không lấy chuỗi tại thời điểm cấu hình**.
6. Trong `@TaskAction`, gọi `get()` để dùng giá trị mà Gradle đã chuẩn bị. Đây là cách giữ giá trị gắn với task execution và phù hợp hơn với Configuration Cache so với việc gọi `System.getenv(...)` ở top-level rồi nhét chuỗi đã đọc sẵn vào task.

### 8.4. Tệp Java 17

`src/main/java/demo/Main.java`:

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Java 17 application is ready");
    }
}
~~~

Java class này độc lập, có thể biên dịch và chạy bằng JDK 17. Nó không phụ thuộc vào Gradle property; mục đích là minh họa cùng một build sử dụng Kotlin DSL để điều khiển task và ứng dụng Java bình thường.

### 8.5. Trường hợp A: không truyền property và biến môi trường

Đứng trong thư mục `provider-lab`, **giả sử không có** `audience` trong các nguồn Gradle project property và không có `APP_CHANNEL` trong môi trường:

~~~bash
gradle --quiet showConfig
~~~

Stdout do task tạo ra chính xác:

~~~text
Audience=developers
Channel=local
~~~

Vì hai source đều thiếu, Gradle dùng giá trị `orElse`.

### 8.6. Trường hợp B: truyền cả hai nguồn trên macOS/Linux

~~~bash
APP_CHANNEL=ci gradle -Paudience=backend --quiet showConfig
~~~

Stdout do task tạo ra:

~~~text
Audience=backend
Channel=ci
~~~

Nếu dùng Gradle Wrapper, thay `gradle` bằng `./gradlew`:

~~~bash
APP_CHANNEL=ci ./gradlew -Paudience=backend --quiet showConfig
~~~

Khi dùng bash, cách gán biến trước lệnh chỉ tác động đến **lần chạy đó**, không phải sửa nội dung tệp `gradle.properties`.

### 8.7. Trường hợp C: chạy trên Windows

PowerShell:

~~~powershell
$env:APP_CHANNEL = "ci"
.\gradlew.bat -Paudience=backend --quiet showConfig
~~~

Command Prompt:

~~~bat
set APP_CHANNEL=ci
gradlew.bat -Paudience=backend --quiet showConfig
~~~

Stdout task trong cả hai trường hợp là:

~~~text
Audience=backend
Channel=ci
~~~

Nếu không có Wrapper, thay `gradlew.bat` bằng lệnh `gradle` đã được cài. Nếu môi trường có sẵn `audience` từ nguồn ưu tiên cao hơn hoặc `APP_CHANNEL` khác, hãy kiểm tra và xác định nguồn giá trị trước khi suy luận stdout.

### 8.8. Trường hợp D: cung cấp property qua gradle.properties

Tạo thêm file `provider-lab/gradle.properties` với nội dung:

~~~properties
audience=course
~~~

Khi không có nguồn `audience` ưu tiên cao hơn và biến `APP_CHANNEL` không tồn tại:

~~~bash
gradle --quiet showConfig
~~~

Stdout:

~~~text
Audience=course
Channel=local
~~~

Nếu tiếp tục chạy `gradle -Paudience=backend --quiet showConfig` thì `Audience=backend` vì CLI override file.

### 8.9. Trường hợp E: Java app chạy độc lập với cấu hình task

~~~bash
gradle --quiet run
~~~

Stdout của **chương trình Java**:

~~~text
Java 17 application is ready
~~~

Lệnh `run` do Application plugin cung cấp. Nó không tự thực thi `showConfig`, vì ví dụ **không** khai báo dependency giữa hai task. Dòng `-Paudience` không tự biến thành Java `System.getProperty("audience")` hoặc giá trị `APP_CHANNEL` trong chương trình.

Nếu muốn kiểm tra riêng mã Java mà không dùng Gradle:

~~~bash
javac -d out src/main/java/demo/Main.java
java -cp out demo.Main
~~~

Stdout:

~~~text
Java 17 application is ready
~~~

Hai lệnh `javac`/`java` chỉ kiểm tra phần Java, không kiểm tra cú pháp Gradle Kotlin DSL.

### 8.10. Vì sao ví dụ dùng custom task type?

Task giản lược sau có thể minh họa cách đọc, nhưng không phải mẫu tốt nhất cho công việc lâu dài:

~~~kotlin
val source = providers.environmentVariable("APP_CHANNEL").orElse("local")

tasks.register("quickPrint") {
    doLast {
        println(source.get())
    }
}
~~~

Đây chỉ là **đoạn thay thế để giải thích**, không cần thêm vào dự án hoàn chỉnh. Nó không khai báo giá trị môi trường như một task input rõ ràng. Với task cần tái sử dụng, cache và Configuration Cache, nên thiết kế custom task type có `@Input Property<String>` như `ShowConfigTask`, rồi nối Provider ở bước cấu hình.

## 9. Khi nào giá trị thật được đọc? Vai trò của configuration cache

### 9.1. Trì hoãn đọc thay vì ép lấy ở configuration

So sánh:

~~~kotlin
// Eager: yêu cầu giá trị ngay khi script được đánh giá.
val channelNow = providers.environmentVariable("APP_CHANNEL").orElse("local").get()

// Lazy: giữ Provider để cấu hình task.
val channelLater = providers.environmentVariable("APP_CHANNEL").orElse("local")
~~~

Nếu `channelNow` được đánh giá ở configuration, biến môi trường trở thành **đầu vào cấu hình**. Khi thay đổi, Gradle có thể phải đánh giá lại cấu hình cached. Với `channelLater`, nếu nối vào task `Property<String>` và chỉ yêu cầu giá trị ở execution, môi trường có thể trở thành **task input**; task cần dùng nó sẽ đánh giá lại công việc, mà không cần mất lợi ích tái sử dụng toàn bộ task graph chỉ vì biến đó thay đổi.

Cơ chế tương tự áp dụng cho project property: điều quan trọng là **đọc ở thời điểm nào** và **kết nối giá trị vào đâu**.

### 9.2. `System.getenv("NAME")` có luôn sai không?

**Không.** Gradle có thể theo dõi việc đọc một biến môi trường cụ thể bằng API tiêu chuẩn như `System.getenv("APP_CHANNEL")` ở configuration và ghi nhận nó làm configuration input. Tuy nhiên, đọc trực tiếp ngay ở configuration làm giá trị được giải quyết sớm, giảm khả năng truyền lazy provider vào task. Mẫu `providers.environmentVariable("APP_CHANNEL")` thường rõ ràng hơn khi dữ liệu được sử dụng bởi task.

Không nên viết:

~~~kotlin
// Dễ gây phụ thuộc cấu hình vào môi trường và ghi log ngoài ý muốn.
val channel = System.getenv("APP_CHANNEL") ?: "local"
println("Channel: $channel")
~~~

như một thói quen ở đầu mọi script. Đặc biệt, **không in giá trị nhạy cảm**.

Ngoài ra, việc duyệt toàn bộ `System.getenv()` hoặc lọc tùy ý mọi biến có thể khiến Gradle xem **rất nhiều** environment variables là configuration inputs. Nếu chỉ cần một key, hãy đọc theo tên cụ thể. Khi cần một nhóm có tiền tố, Gradle còn có `providers.environmentVariablesPrefixedBy("PREFIX_")`.

### 9.3. Configuration Cache khác Build Cache

| Cơ chế | Cache cái gì? | Giá trị môi trường thay đổi có thể dẫn đến gì? |
| --- | --- | --- |
| Configuration Cache | Trạng thái cấu hình/task graph có thể tái sử dụng | Nếu biến được đọc khi cấu hình, cache cấu hình có thể bị invalidated |
| Up-to-date checks | Trạng thái input/output của task đã chạy | Đổi input của task khiến task cần kiểm tra/chạy lại |
| Build Cache | Output của task cacheable theo fingerprint hợp lệ | Task có thể chạy, bị bỏ qua hoặc tái sử dụng output từ cache tùy điều kiện |

Task `ShowConfigTask` của ví dụ chỉ in stdout, không khai báo output, nên bạn **không nên kỳ vọng** nó trở thành `UP-TO-DATE` chỉ vì hai input giống nhau. Mục đích ở đây là làm rõ cách Gradle theo dõi input, không khẳng định task in log sẽ được cache.

### 9.4. Đừng capture Project trong task action

Tránh kiểu:

~~~kotlin
tasks.register("badPattern") {
    doLast {
        // Không nên trong task action: truy cập Project API tại execution.
        println(project.findProperty("audience"))
    }
}
~~~

Trong Configuration Cache, truy cập `Project`/plugin extensions từ task action có thể không được hỗ trợ. Hãy chuyển giá trị thành task property trong configuration rồi đọc chính property đó ở action. Đây là lý do custom task có `@get:Input abstract val audience: Property<String>` là một mẫu có ích để học.

## 10. An toàn thông tin: credential không giống cấu hình hiển thị

Những ví dụ `audience` và `APP_CHANNEL` không chứa bí mật; có thể in ra để xác minh. **Không áp dụng cách in đó cho token, password, API key hoặc khóa ký.**

Quy tắc:

1. **Không hardcode bí mật** trong `build.gradle(.kts)`, code Java hoặc `gradle.properties` được commit vào Git.
2. **Không in token** bằng `println(provider.get())`, `logger.lifecycle(...)` hoặc `--info`.
3. Có thể truyền bí mật bằng CI secret environment variables hoặc `GRADLE_USER_HOME/gradle.properties` được bảo vệ; chọn nguồn theo mục đích và quy định tổ chức.
4. Với repository authentication, ưu tiên **Gradle Credentials API** và cơ chế credentials dựa trên property được Gradle hỗ trợ, để tránh tự xử lý lộ secret trong log.
5. Với task dùng secret ở runtime, nên giữ giá trị lười qua `providers.environmentVariable(...)` và nối vào task property. Không tính sẵn secret ở configuration rồi capture nó trong action.
6. Giới hạn quyền truy cập cache và log. Configuration Cache có thể chứa trạng thái được tuần tự hóa; Gradle có cơ chế mã hóa cache nhưng không biến việc in/nhúng secret thành an toàn.

Ví dụ chỉ minh họa cách giữ nguồn bí mật lười (không in, không tự thực hiện publish):

~~~kotlin
val publishingToken = providers.environmentVariable("PUBLISH_TOKEN")
~~~

Nếu một task publish thật sự cần token, hãy cấu hình task/plugin có API credential phù hợp. Nếu token thiếu, build có thể cần từ chối **chỉ khi chạy tác vụ yêu cầu nó**, thay vì chặn mọi lệnh `help` hoặc `test`.

Mặc dù `ORG_GRADLE_PROJECT_secretName` có thể được Gradle nhận như project property, điều đó không tự đảm bảo bí mật an toàn hơn một env var thông thường. Tránh đặt secret dưới dạng `-Psecret=value` trên dòng lệnh nếu môi trường có khả năng ghi/hiển thị command line.

## 11. Nơi dùng Provider: build script, task, CI và plugin

### 11.1. Chọn đúng phạm vi

- **Build script:** dùng `providers.gradleProperty` để quyết định metadata, cấu hình dependency/plugin hoặc đầu vào task, khi cần giá trị do người dùng/CI cấp.
- **Task có input rõ ràng:** nối Provider vào `Property<T>`; để Gradle xác định ảnh hưởng của giá trị tới execution.
- **CI:** ưu tiên cấp tham số từ cấu hình job; không tạo file chứa bí mật chỉ để script có thể đọc.
- **Plugin/convention plugin:** dùng `ProviderFactory` được inject hoặc API được Gradle cung cấp trong ngữ cảnh plugin, tránh phụ thuộc vào một project cụ thể khi reusable logic cần hoạt động ở nhiều nơi.

### 11.2. Không đọc giá trị chỉ để quyết định mọi thứ ở configuration

Có những quyết định buộc phải giải quyết giá trị ở configuration, ví dụ chọn một plugin hoặc dependency condition dựa trên input. Trong trường hợp đó đọc giá trị là hợp lệ, nhưng cần nhận ra nó là **configuration input**.

Ngược lại, các giá trị dùng để tạo file, chạy test, đóng gói hoặc gọi dịch vụ trong task nên được nối lazy vào inputs khi có thể. Mục tiêu không phải cấm gọi `get()` ở mọi nơi; mục tiêu là gọi đúng thời điểm và khai báo các input mà kết quả phụ thuộc.

### 11.3. Khi dùng biến môi trường trong JavaExec/test

Ví dụ minh họa cấu hình cố định (không phải dùng Provider), nếu cần đặt một env var khi chạy ứng dụng:

~~~kotlin
tasks.named<JavaExec>("run") {
    environment("APP_CHANNEL", "test")
}
~~~

Đây là **đoạn bổ sung**, chỉ hợp lệ khi project đã áp dụng `application` plugin để có task `run`; kiểu `JavaExec` thuộc API Gradle. Một cấu hình cố định như vậy phù hợp để minh họa ranh giới giữa **môi trường Gradle** và **môi trường process JavaExec**.

Khi giá trị đến từ Provider và cần giữ lazy trong cấu hình phức tạp, hãy dùng API của task/plugin hoặc thiết kế task type hỗ trợ Provider; đừng gọi `.get()` ở top-level chỉ để lấp một tham số chuỗi. Với plugin của bên thứ ba, kiểm tra API tương ứng trước khi kết luận có overload nhận Provider.

## 12. Lỗi thường gặp và cách sửa

### Lỗi 1. Nhầm project property với environment variable

Sai về mặt ý định:

~~~kotlin
// CI chỉ cấp APP_CHANNEL=ci, nhưng lại tìm Gradle property.
val channel = providers.gradleProperty("APP_CHANNEL")
~~~

Đúng nếu nguồn là OS env:

~~~kotlin
val channel = providers.environmentVariable("APP_CHANNEL").orElse("local")
~~~

Nếu muốn dùng `gradleProperty("channel")`, hãy truyền `-Pchannel=ci` hoặc `ORG_GRADLE_PROJECT_channel=ci`, hoặc khai báo key trong `gradle.properties`.

### Lỗi 2. Gọi `get()` trên provider không có giá trị

~~~kotlin
val value = providers.gradleProperty("unconfiguredKey").get()
~~~

Lệnh trên có thể fail nếu key chưa được cung cấp. Nếu optional, dùng `orElse(...)` hoặc `getOrElse(...)`; nếu bắt buộc, hãy để task cần nó báo lỗi rõ ràng khi truy vấn, và tài liệu hóa cách cung cấp giá trị.

### Lỗi 3. Nghĩ rằng chuỗi rỗng là “missing”

~~~kotlin
val label = providers.gradleProperty("label").orElse("default")
~~~

`-Plabel=` trả về chuỗi rỗng, không dùng `default`. Cần `map { it.trim().ifEmpty { "default" } }` nếu business rule xem rỗng là mặc định.

### Lỗi 4. Quên chuyển kiểu

~~~kotlin
val port = providers.gradleProperty("serverPort")
// port là Provider<String>, không phải Provider<Int>.
~~~

Nếu cần số:

~~~kotlin
val portNumber = port.map { it.toInt() }.orElse(8080)
~~~

Khi dùng input không đáng tin, nên sử dụng `toIntOrNull()` và `require(...)` với thông báo lỗi rõ ràng để tránh NumberFormatException khó hiểu.

### Lỗi 5. Hiểu sai thứ tự ưu tiên

File root ghi `audience=local` nhưng CLI `-Paudience=ci`: kết quả là `ci`. Không kết luận Gradle “không đọc file” khi thực ra file bị một nguồn ưu tiên cao hơn ghi đè.

### Lỗi 6. Tưởng `System.getenv("APP_CHANNEL")` và `providers.environmentVariable(...)` khác nội dung

Cả hai có thể đọc cùng OS env var, nhưng khác cách API biểu diễn thời điểm tiêu thụ và khả năng nối giá trị vào mô hình Gradle. Đọc trực tiếp ở configuration có thể được Gradle theo dõi; Provider phù hợp hơn khi muốn chuyển đầu vào sang task một cách khai báo/lười.

### Lỗi 7. Đặt file `.env` nhưng provider vẫn missing

Gradle không mặc định parse `.env`. Hãy cấu hình shell/CI xuất biến hoặc dùng plugin/cơ chế nạp cụ thể khi dự án thực sự yêu cầu. Không nói rằng `providers.environmentVariable` sẽ tự tìm mọi file chứa tên biến.

### Lỗi 8. Lạm dụng `Project.findProperty` trong `doLast`

Truy cập Project từ task action có thể gây vấn đề với Configuration Cache. Dùng typed task property, khai báo `@Input`/`@OutputFile` và nối Provider ở configuration.

### Lỗi 9. Đánh giá toàn bộ môi trường bằng `System.getenv()`

Duyệt mọi env var hoặc lọc tên tùy ý trong configuration có thể khiến cache phụ thuộc vào nhiều biến không cần thiết. Dùng `providers.environmentVariable("KEY")` cho key cố định hoặc API prefix khi cần nhóm.

### Lỗi 10. Đưa bí mật vào output/log

Không in credentials để “debug nhanh”. Kiểm tra **có/không có nguồn** hoặc tên biến không nhạy cảm, và dùng credentials API thích hợp. Tránh hiển thị token ngay cả trong failure message hoặc stacktrace do custom task tạo.

## 13. Kịch bản quyết định chọn API

| Nhu cầu | API/cách làm phù hợp | Ví dụ |
| --- | --- | --- |
| Người dùng truyền tên artifact qua CLI `-P` | `providers.gradleProperty` | `providers.gradleProperty("artifactName")` |
| Đọc cấu hình từ root/user Gradle properties | `providers.gradleProperty` | `providers.gradleProperty("releaseChannel")` |
| CI truyền môi trường triển khai | `providers.environmentVariable` | `providers.environmentVariable("DEPLOY_ENV")` |
| Gradle plugin cần JVM system property | `providers.systemProperty` | `providers.systemProperty("demo.mode")` |
| Muốn giá trị mặc định nếu không có nguồn | `orElse(...)` | `provider.orElse("local")` |
| Muốn chuẩn hóa/thẩm định input | `map { ... }` | `provider.map { it.trim() }` |
| Nguồn kế tiếp là một Provider | `orElse(provider)`/`flatMap` | `gradleProperty(...).orElse(environmentVariable(...))` |
| Task cần giá trị môi trường thường xuyên thay đổi | `Property<T>` + `@Input` nối từ Provider | `channel.set(channelProvider)` |
| Muốn dùng credential để tải artifact | Credentials API / nguồn secret phù hợp | Không hardcode trong build script |
| Cần đọc nhiều env var có cùng tiền tố | `environmentVariablesPrefixedBy(...)` | `providers.environmentVariablesPrefixedBy("JDK_")` |

## 14. Các bài tập tự kiểm tra có đáp án

### Bài tập 1. Dự đoán giá trị theo nguồn

Root `gradle.properties` có `audience=root`. Shell có `ORG_GRADLE_PROJECT_audience=env`. Chạy:

~~~bash
gradle -Paudience=cli --quiet showConfig
~~~

`providers.gradleProperty("audience")` trả về gì?

**Đáp án:** `cli`, vì `-P` ưu tiên cao hơn biến môi trường đặc biệt và root `gradle.properties`. Các nguồn này đều có thể cung cấp project property; chúng không phải biến môi trường tùy ý đọc bởi `environmentVariable("audience")`.

### Bài tập 2. Phân biệt hai namespace

Shell chứa `APP_CHANNEL=ci`; không có Gradle property tên `APP_CHANNEL`. Kết quả hai provider?

~~~kotlin
val a = providers.gradleProperty("APP_CHANNEL")
val b = providers.environmentVariable("APP_CHANNEL")
~~~

**Đáp án:** `a` không có giá trị từ biến môi trường thông thường; `b` có giá trị `ci`. Để biến môi trường trở thành project property, phải dùng tiền tố đặc biệt `ORG_GRADLE_PROJECT_` đúng tên key.

### Bài tập 3. Sửa lỗi missing

Đoạn này fail khi không có `audience`:

~~~kotlin
val value = providers.gradleProperty("audience").get()
~~~

Hãy sửa để mặc định `developers` mà vẫn giữ Provider.

**Đáp án:**

~~~kotlin
val value = providers.gradleProperty("audience").orElse("developers")
~~~

Biến `value` là `Provider<String>`; để đọc trong task action, có thể gọi `value.get()` hoặc tốt hơn nối vào task property và đọc ở `@TaskAction`.

### Bài tập 4. Nhận diện chuỗi rỗng

~~~kotlin
val label = providers.gradleProperty("label").orElse("default")
~~~

Người dùng chạy `-Plabel=`. `label.get()` có phải `default` không?

**Đáp án:** Không. Nó là chuỗi rỗng. Có thể dùng:

~~~kotlin
val label = providers.gradleProperty("label")
    .map { it.trim().ifEmpty { "default" } }
    .orElse("default")
~~~

### Bài tập 5. Chuyển từ Provider<String> sang Provider<Int>

Muốn đọc `-PretryCount=5`, mặc định 2 và từ chối số âm:

~~~kotlin
val retries = providers.gradleProperty("retryCount")
    .map { raw ->
        val n = raw.toIntOrNull()
            ?: error("retryCount phải là số nguyên")
        require(n >= 0) { "retryCount phải >= 0" }
        n
    }
    .orElse(2)
~~~

**Đáp án:** `retries` có kiểu `Provider<Int>`, khi được yêu cầu sẽ trả về `5`. Nếu thiếu key thì trả về `2`, nếu giá trị là `-1` hoặc `abc` thì báo lỗi khi Gradle giải quyết provider.

### Bài tập 6. Tại sao Configuration Cache bị đánh giá lại?

Script gọi `System.getenv("APP_CHANNEL")` ở top-level để tính một chuỗi. CI đổi `APP_CHANNEL` ở build tiếp theo. Vì sao cache cấu hình có thể invalidated?

**Đáp án:** Gradle theo dõi giá trị biến môi trường được đọc trong configuration như một configuration input. Khi giá trị thay đổi, trạng thái cấu hình không còn giống trước. Nếu task mới là nơi sử dụng, nối `providers.environmentVariable("APP_CHANNEL")` vào task `Property<String>` để giá trị có thể được đọc khi execution, giúp tránh đánh giá lại toàn bộ cấu hình chỉ bởi một input task thay đổi.

### Bài tập 7. Không in secret

Bạn cần token để task publish hoạt động, nhưng cũng muốn `gradle help` chạy được khi máy lập trình viên chưa có token. Nên làm gì?

**Đáp án:** Giữ token ở nguồn bên ngoài như CI secret environment variable hoặc Gradle user home cấu hình quyền phù hợp; nối provider vào API credential/task phù hợp; chỉ yêu cầu giá trị khi chạy publish; không in token và không bắt mọi task phải có token ngay trong phần cấu hình chung.

## 15. Quy trình chẩn đoán thực tế

Khi provider trả về giá trị bất ngờ, kiểm tra theo thứ tự:

1. **Xác nhận key chính xác:** `audience` khác `Audience`; `APP_CHANNEL` khác `ORG_GRADLE_PROJECT_APP_CHANNEL`.
2. **Xác nhận loại nguồn:** Gradle property, OS env hay JVM system property? Chọn đúng factory method.
3. **Xác nhận thứ tự ưu tiên:** `-P` có thể override `gradle.properties`; `ORG_GRADLE_PROJECT_...` có thể override file.
4. **Kiểm tra môi trường tiến trình Gradle:** biến có được xuất ra từ đúng shell, terminal, IDE hoặc CI job đang chạy Gradle không?
5. **Phân biệt missing và empty:** `isPresent` và `orNull` giúp debug trạng thái, nhưng đừng in giá trị nhạy cảm.
6. **Kiểm tra thời điểm đọc:** `.get()` ở configuration hay nối provider tới task input? Điều này ảnh hưởng caching.
7. **Chạy Gradle với log phù hợp:** `--info` hoặc `--stacktrace` giúp xem lỗi task/plugin; đừng bật log gây lộ credentials.
8. **Sử dụng Wrapper** khi dự án đã có, nhằm thống nhất bản Gradle trên máy cá nhân và CI.

Lệnh hỗ trợ:

~~~bash
# Xác minh script và task không cần chạy app.
gradle --console=plain tasks

# Chạy ví dụ với property từ CLI.
gradle -Paudience=backend --quiet showConfig

# Kiểm tra nếu có lỗi, không log secret.
gradle --stacktrace showConfig

# Quan sát Configuration Cache khi build hỗ trợ.
gradle --configuration-cache showConfig
~~~

Lệnh `--configuration-cache` chỉ cho biết Gradle có thể lưu/tái sử dụng cấu hình khi build logic và task phù hợp; nó không tự xác nhận mọi biến được dùng là an toàn hoặc mọi task có output cacheable.

## 16. Tóm tắt cần nhớ

- `providers.gradleProperty("key")` lấy Gradle project property cấp build từ những nguồn như `-P`, `org.gradle.project.*`, `ORG_GRADLE_PROJECT_*` và `gradle.properties` theo thứ tự ưu tiên.
- `providers.environmentVariable("NAME")` lấy OS environment variable của tiến trình Gradle. Nó không tự đọc Gradle property hoặc file `.env`.
- Hai hàm trả về `Provider<String>`; missing khác rỗng. `orElse(...)` là fallback cho **missing**.
- Dùng `map` để chuyển kiểu và validate, `flatMap` khi cần lồng nguồn provider, `orElse(provider)` khi cần dự phòng theo thứ tự tùy chọn.
- Giữ giá trị dạng Provider và nối vào `Property<T>` có `@Input` khi một task sử dụng nó. Đọc bằng `get()` khi cần thực sự xử lý.
- Cách đọc giá trị **ở configuration hay execution** ảnh hưởng đến Configuration Cache. Đọc trực tiếp bằng `System.getenv("NAME")` ở configuration có thể được Gradle theo dõi, nhưng thường không tối ưu bằng lazy wiring nếu giá trị chỉ phục vụ task.
- Không đưa secret vào script, console log, command line hoặc cache một cách không kiểm soát. Với repository, ưu tiên Credentials API.

**Tài liệu chính thức của Gradle**:

- [Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html) — nguồn và thứ tự Gradle project properties.
- [ProviderFactory API](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/ProviderFactory.html) — `gradleProperty`, `environmentVariable` và các overload.
- [Understanding Providers and Properties](https://docs.gradle.org/current/userguide/properties_providers.html) — mô hình Provider/Property.
- [Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html) — đọc môi trường và system properties.
- [Configuration Cache Security Considerations](https://docs.gradle.org/current/userguide/configuration_cache.html) — xử lý credentials và cache.
