# Chuỗi, nội suy, collection và giá trị nullable trong Gradle Kotlin DSL

Một file `build.gradle.kts` là **mã Kotlin được Gradle biên dịch và đánh giá để cấu hình build**. Vì vậy, khi viết tên task, tọa độ dependency, đường dẫn, danh sách module hoặc giá trị lấy từ `gradle.properties`, bạn dùng chính các quy tắc của Kotlin về `String`, **string templates**, **collections** và **null safety**. Phần khó là kết hợp cú pháp Kotlin với thời điểm Gradle cấu hình hoặc thực thi task.

Sau bài này, bạn sẽ biết cách viết chuỗi và nội suy biến cho đúng; thao tác `List`/`Set`/`Map`; xử lý cấu hình tùy chọn có thể `null`; phân biệt `String?` với `Provider<String>`; và dùng các kỹ thuật đó trong build script có thể chạy được.

## 1. Bối cảnh: Kotlin DSL là Kotlin, nhưng đối tượng đến từ Gradle

Gradle hỗ trợ cả Groovy DSL (`build.gradle`, `settings.gradle`) và Kotlin DSL (`build.gradle.kts`, `settings.gradle.kts`). Trong Kotlin DSL, biểu thức được kiểm tra kiểu tĩnh, có IDE completion và sử dụng cú pháp Kotlin:

```kotlin
// build.gradle.kts
plugins {
    id("java")
}

val moduleLabel: String = "catalog"
val targets = listOf("dev", "qa")

tasks.register("printLabel") {
    val message = "Module $moduleLabel; targets: ${targets.joinToString(", ")}"
    doLast {
        println(message)
    }
}
```

Đoạn này là `build.gradle.kts` độc lập cho việc đăng ký task `printLabel`, giả sử chạy trong Gradle build hợp lệ. Khi chạy `./gradlew printLabel -q`, action của task in:

```text
Module catalog; targets: dev, qa
```

Trong ví dụ, `val`, `listOf`, `joinToString` và `"$moduleLabel"` là **Kotlin**. Còn `plugins`, `tasks.register`, `doLast` là **Gradle API/Kotlin DSL**.

Ở đầu build script, `val moduleLabel = ...` được tính khi **Configuration** chạy. Bên trong `doLast { ... }`, lệnh `println` là **task action** và chỉ chạy ở **Execution** nếu task được thực thi. Ví dụ lưu một chuỗi `message` đã tính trước vào action để không phải truy cập `project` trực tiếp trong action, thuận lợi hơn cho Configuration Cache.

### Kotlin DSL khác Groovy DSL ở những điểm dễ nhầm

| Ý định | Groovy DSL | Kotlin DSL |
| --- | --- | --- |
| Áp dụng plugin | `id 'java'` | `id("java")` |
| Gọi hàm | `include 'app'` | `include("app")` |
| Chuỗi | `'hello'` hoặc `"hello"` | `"hello"` |
| Khai báo biến | `def name = 'app'` | `val name = "app"` hoặc `var name = "app"` |
| Phụ thuộc | `implementation 'g:a:v'` | `implementation("g:a:v")` khi accessor được cung cấp |
| Optional value | Groovy dùng dynamic/null/truthy | Kotlin có kiểu `T?`, `?.` và `?:` |
| Collection literal | `['a', 'b']` | `listOf("a", "b")` |

**Cần nhớ:** Kotlin dùng dấu nháy đơn cho **`Char`**, chẳng hạn `'a'`; `'hello'` không phải chuỗi Kotlin hợp lệ. Sửa thành `"hello"`. Không sao chép trực tiếp cú pháp ví dụ Groovy vào file `.gradle.kts`.

## 2. Chuỗi `String`: literal, escape và tính bất biến

Kotlin `String` là kiểu chuỗi không thể thay đổi trực tiếp (*immutable*). Có hai dạng viết thường dùng.

### 2.1. Chuỗi thường: `"..."`

```kotlin
val module = "order-service"
val separator = ":"
val path = "src/main/java"
val message = "Line 1\nLine 2"
val quoted = "Dependency \"group:artifact:version\""
val literalDollar = "Amount: \$100"
```

- `\n` biểu diễn xuống dòng.
- `\t` biểu diễn tab.
- `\\"` biểu diễn dấu nháy kép bên trong chuỗi.
- `\\` biểu diễn dấu backslash.
- `\$` biểu diễn dấu dollar **theo nghĩa ký tự** thay vì bắt đầu nội suy.

Ví dụ `"Amount: \$100"` tạo chuỗi `Amount: $100`, không tìm biến Kotlin tên `100`.

Kotlin `String` không thay đổi tại chỗ. Các lời gọi `trim()`, `replace(...)`, `uppercase()`, `lowercase()` trả về chuỗi mới:

```kotlin
val original = "  Gradle  "
val clean = original.trim()
val upper = clean.uppercase()

// original == "  Gradle  "
// clean    == "Gradle"
// upper    == "GRADLE"
```

`val` ngăn **gán lại biến**; nó không có nghĩa mọi đối tượng được gán cho `val` đều bất biến. Với `String`, bản thân kiểu chuỗi cũng immutable. Về collections thì cần phân biệt thêm ở mục 5.

### 2.2. Chuỗi nhiều dòng: `"""..."""`

Raw/triple-quoted strings rất tiện cho đoạn text, JSON mẫu hoặc nhiều dòng:

```kotlin
val helpText = """
    Build options:
      -Pstage=dev
      -Pstage=qa
""".trimIndent()
```

`trimIndent()` loại bỏ phần thụt đầu chung, giúp giữ file Kotlin DSL dễ đọc. `trimMargin()` là lựa chọn khác khi muốn đánh dấu lề bằng `|`:

```kotlin
val instructions = """
    |Step 1: configure
    |Step 2: execute
""".trimMargin()
```

**Raw string không xử lý escape kiểu `\n` hoặc `\t`**: hai ký tự backslash và `n` sẽ được giữ nguyên. Tuy nhiên, **nội suy bằng `$` vẫn hoạt động trong raw string**. Ví dụ:

```kotlin
val toolName = "Gradle"
val detail = """Build tool: $toolName"""
// detail == "Build tool: Gradle"
```

Nếu cần dấu dollar literal trong raw string, cách tương thích với Kotlin thông dụng là dùng biểu thức ký tự dollar:

```kotlin
val shellHint = """HOME variable: ${'$'}HOME"""
// Kết quả: HOME variable: $HOME
```

Đừng nghĩ chỉ cần đổi `"..."` thành `"""..."""` thì mọi `$variable` sẽ tự trở thành văn bản nguyên nghĩa.

## 3. String templates: `$name` và `${expression}`

*Nội suy chuỗi* chèn giá trị vào text tại thời điểm biểu thức được đánh giá:

```kotlin
val artifact = "payments"
val release = "1.2.0"

val label = "Building $artifact"
val coordinate = "com.example:$artifact:$release"
val taskName = "build${artifact.replaceFirstChar { it.uppercase() }}"
```

Giá trị tương ứng:

```text
Building payments
com.example:payments:1.2.0
buildPayments
```

Quy tắc:

- `$name`: dùng cho **tên biến hoặc thuộc tính đơn giản**.
- `${expression}`: dùng cho **biểu thức đầy đủ**, truy cập thuộc tính, gọi hàm hoặc khi cần xác định ranh giới tên biến.
- `"deploy${moduleName}Now"`: bao tên biến trong `${...}` nếu ngay sau đó là ký tự tạo thành tên định danh Kotlin, để tránh hiểu nhầm thành `moduleNameNow`.
- `"\$CI_JOB_ID"`: biểu diễn chuỗi `$CI_JOB_ID` nguyên văn trong một chuỗi thường.

Ví dụ có dấu ngoặc kép trong biểu thức:

```kotlin
val parts = listOf("api", "worker")
val formatted = "Modules: ${parts.joinToString(separator = ", ")}"
// Modules: api, worker
```

Kotlin cho phép chuỗi `", "` nằm bên trong `${...}` mà không cần escape các dấu nháy đó như thể đang viết trực tiếp trong phần text bên ngoài.

### Nội suy trong tọa độ dependency

Đây là **đoạn trích minh họa** dùng trong `build.gradle.kts` đã áp dụng plugin `java`:

```kotlin
plugins {
    id("java")
}

val groupId = "org.slf4j"
val artifactId = "slf4j-api"
val libraryVersion = "2.0.17"

dependencies {
    implementation("$groupId:$artifactId:$libraryVersion")
}
```

Sau khi nội suy, Gradle nhận notation `org.slf4j:slf4j-api:2.0.17`. Nội suy **chỉ tạo chuỗi**, không tự kiểm tra version có tồn tại hoặc tự tải dependency. Gradle sẽ xử lý resolution qua repository khi build cần dependency. Nếu dùng file `gradle/libs.versions.toml`, thường nên ưu tiên version catalog với accessor `libs...` thay vì tự ghép hàng loạt tọa độ và version thủ công.

### Nội suy và thời điểm của Gradle

```kotlin
val label = "Build started: ${project.name}"

tasks.register("showLabel") {
    doLast {
        println(label)
    }
}
```

Biến `label` được tính **khi cấu hình project**. Action in giá trị đó lúc task chạy. Nếu dữ liệu cần đọc **tại execution time**, việc chụp một chuỗi sớm có thể không đúng mục đích; dùng Gradle `Provider`/`Property` làm đầu vào task hoặc API execution phù hợp. Ngược lại, truy cập `project.name` trực tiếp trong `doLast` thường không phù hợp yêu cầu của Configuration Cache.

## 4. Chuỗi trong đường dẫn và log: khi nào dùng nội suy?

Trong build script, các chuỗi như `"src/main/resources"`, `"reports"`, `"myTask"` chỉ là text. Khi dùng làm đường dẫn, nên ưu tiên **Gradle file/location API** thay vì nối chuỗi chứa separator của hệ điều hành.

Ví dụ:

```kotlin
val outputFile = layout.buildDirectory.file("reports/check.txt")
val inputDir = layout.projectDirectory.dir("src/main/resources")
```

Hai giá trị trên là **providers/locations của Gradle**, không phải `String` đường dẫn tuyệt đối. API này hiểu layout của project và liên kết tốt hơn với hệ thống input/output của task.

Nếu chỉ muốn hiển thị tên module, có thể dùng `"Project: ${project.name}"` trong giai đoạn Configuration. Nhưng không nên làm:

```kotlin
// Không khuyến nghị: tự ghép absolute path dựa trên máy chạy
val platformPath = "C:\\users\\me\\work\\project\\build"
```

Đường dẫn cố định theo một máy dễ sai trên CI hoặc Linux/macOS. Với task tạo file, cần khai báo output property và cung cấp `layout.buildDirectory.file(...)`.

## 5. Collections cơ bản: `List`, `Set`, `Map`

Kotlin phân biệt kiểu collection **chỉ đọc** với collection **có thể thay đổi**. Trong build scripts, collections thường mô tả danh sách flavors/environments, danh sách cấu hình, map nhãn, hoặc nhiều dependency được cấu hình theo một quy tắc.

| Loại | Khởi tạo | Khi nào dùng | Điểm cần nhớ |
| --- | --- | --- | --- |
| `List<T>` | `listOf("dev", "qa")` | Dữ liệu **có thứ tự**, có thể lặp phần tử | Truy cập bằng chỉ số, `first()`, `map()`, `filter()` |
| `Set<T>` | `setOf("api", "web")` | Tập phần tử **không trùng nhau** | Hữu ích để loại bản sao; đừng dựa tùy tiện vào thứ tự |
| `Map<K,V>` | `mapOf("dev" to 8080)` | Ánh xạ khóa → giá trị | `map[key]` trả về kiểu **nullable** `V?` |
| `MutableList<T>` | `mutableListOf("dev")` | Cần thêm/xóa phần tử khi chuẩn bị cấu hình | `add`, `remove`; hạn chế mutation không cần thiết |
| `MutableMap<K,V>` | `mutableMapOf("dev" to 8080)` | Cần cập nhật mapping có chủ đích | Tránh thay đổi trạng thái từ task action/đa luồng |

Ví dụ Kotlin thuần có thể đặt ở phần cấu hình:

```kotlin
val modules: List<String> = listOf("api", "core", "api", "worker")
val uniqueModules: Set<String> = modules.toSet()
val publicModules = modules
    .distinct()
    .filter { it != "core" }
    .map { it.uppercase() }

val ports: Map<String, Int> = mapOf(
    "dev" to 8080,
    "qa" to 9090
)
```

Kết quả:

```text
modules       = [api, core, api, worker]
uniqueModules = tập gồm api, core, worker
publicModules = [API, WORKER]
ports["dev"]  = 8080
ports["prod"] = null
```

`Set` biểu diễn tập không trùng; không nên để thứ tự của một tập là một phần của build contract trừ khi loại collection/cách tạo của bạn có hợp đồng thứ tự rõ ràng.

### Các phép biến đổi hay gặp

```kotlin
val names = listOf(" app ", "api", "app", "")
val cleaned = names
    .map { it.trim() }
    .filter { it.isNotEmpty() }
    .distinct()

val csv = cleaned.joinToString(", ")
// cleaned == ["app", "api"]
// csv == "app, api"
```

- `map`: đổi từng phần tử thành giá trị mới.
- `filter`: chỉ giữ phần tử thỏa điều kiện.
- `distinct`: loại phần tử trùng.
- `joinToString`: biến collection thành chuỗi theo separator.
- `forEach`: lặp để thực hiện side effect, ví dụ đăng ký task.

Những phép trên thường trả về collection mới, **không tự sửa** collection gốc.

### `val` và `mutableListOf` không mâu thuẫn

```kotlin
val destinations = mutableListOf("dev")
destinations.add("qa")          // Hợp lệ: thay đổi nội dung list
// destinations = mutableListOf("prod") // Không hợp lệ: gán lại val
```

Khi thiết kế build, nên ưu tiên `listOf`/`mapOf` và các phép biến đổi thuần nếu không cần mutation. Điều này làm cấu hình dễ đọc và tránh sự phụ thuộc khó đoán giữa nhiều plugin/task.

## 6. Collection ứng dụng vào Gradle tasks

### 6.1. Đăng ký nhiều task từ một `List`

Đây là `build.gradle.kts` tối thiểu, độc lập:

```kotlin
val environments = listOf("dev", "qa", "prod")

environments.forEach { env ->
    val suffix = env.replaceFirstChar { it.uppercase() }
    tasks.register("describe$suffix") {
        val message = "Environment: $env"
        doLast {
            println(message)
        }
    }
}
```

Gradle đăng ký ba task: `describeDev`, `describeQa`, `describeProd`. Chạy:

```bash
./gradlew describeQa -q
```

Stdout của task action:

```text
Environment: qa
```

**Tại sao hoạt động?** `forEach` và `tasks.register` được gọi lúc **Configuration**. `doLast` lưu một action, chỉ in ra khi Gradle chạy task tương ứng. `val message` được xây khi task được cấu hình, rồi action chỉ sử dụng `String` đã chuẩn bị.

Nếu tên environment đến từ cấu hình người dùng, cần kiểm soát allowed values, tên task hợp lệ và thứ tự ổn định; đừng tạo task với dữ liệu ngẫu nhiên hoặc thay đổi ngoài kiểm soát.

### 6.2. Map cho cấu hình có khóa

```kotlin
val descriptions = mapOf(
    "dev" to "Local developer build",
    "qa" to "Quality assurance",
    "prod" to "Production build"
)

val selected = "qa"
val description = descriptions[selected] ?: "Unknown environment"
// description == "Quality assurance"
```

Vì một khóa **có thể không tồn tại**, `descriptions[selected]` là `String?`, mặc dù `descriptions` được khai báo là `Map<String, String>`.

Nếu khóa là **bắt buộc**, `descriptions.getValue(selected)` ném exception khi không có; chỉ dùng khi bạn chủ động muốn báo lỗi nếu cấu hình không hợp lệ. Nếu muốn giải thích lỗi tốt hơn, dùng:

```kotlin
val description = requireNotNull(descriptions[selected]) {
    "Unsupported environment '$selected'. Allowed: ${descriptions.keys}"
}
```

Đoạn này chọn hướng **fail fast** thay vì âm thầm dùng fallback khi chọn môi trường triển khai ngoài danh sách. Trong dự án thực tế, lỗi cấu hình deployment cần được phát hiện sớm.

### 6.3. Collection trong khối `dependencies`

Đây là đoạn `build.gradle.kts` có áp dụng Java plugin:

```kotlin
plugins {
    id("java")
}

repositories {
    mavenCentral()
}

val libraries = listOf(
    "org.slf4j:slf4j-api:2.0.17",
    "org.apache.commons:commons-lang3:3.14.0"
)

dependencies {
    libraries.forEach { coordinate ->
        implementation(coordinate)
    }
}
```

Mỗi `coordinate` là `String`; `implementation(coordinate)` là lời gọi Gradle DSL cho dependency configuration `implementation`. Accessor này khả dụng ở ví dụ vì Java plugin được áp dụng. Có thể dùng map theo nhóm/version khi thật sự cần, nhưng với project dài hạn, **Version Catalog** hoặc cách khai báo dependency tường minh thường dễ kiểm soát nâng cấp hơn.

Tránh hiểu `List<String>` là Gradle `Configuration`. Collection thuần chỉ chứa dữ liệu; `dependencies { ... }` mới chuyển dữ liệu đó thành mô hình dependency của Gradle.

## 7. Nullability trong Kotlin: `String` khác `String?`

Kotlin thể hiện khả năng không có giá trị ngay trong type:

```kotlin
val requiredName: String = "catalog"
val optionalName: String? = null

// val invalid: String = null // Lỗi biên dịch
```

- `String` không chấp nhận `null`.
- `String?` có thể là chuỗi hoặc `null`.
- Compiler yêu cầu xử lý `null` trước khi gọi các phương thức trên một giá trị nullable.

### 7.1. Safe call `?.`

```kotlin
val raw: String? = null
val size: Int? = raw?.length
val normalized: String? = raw?.trim()?.uppercase()
// size == null; normalized == null
```

Nếu `raw == null`, chuỗi lời gọi có `?.` sẽ trả về `null` mà không gây `NullPointerException`.

### 7.2. Elvis operator `?:`

```kotlin
val raw: String? = null
val module: String = raw ?: "app"
// module == "app"
```

Vế phải của `?:` chỉ được sử dụng khi vế trái **là `null`**. Một nhầm lẫn khi chuyển từ Groovy sang Kotlin: **chuỗi rỗng `""`, số 0 và `false` không tự kích hoạt fallback**.

```kotlin
val raw: String? = " "
val nameA = raw ?: "default"                              // " "
val nameB = raw?.trim()?.takeIf { it.isNotEmpty() }
    ?: "default"                                           // "default"
```

Trong Kotlin, `takeIf { predicate }` trả về receiver nếu predicate đúng, hoặc `null` nếu sai. Kết hợp `?.trim()`, `takeIf` và `?:` giúp xử lý cả **giá trị thiếu** và **giá trị chỉ có khoảng trắng**.

### 7.3. `let`, `isNullOrBlank`, `requireNotNull`, `!!`

```kotlin
val optionalLabel: String? = "release"
optionalLabel?.let { label ->
    println(label.uppercase())
}

val missing: String? = null
val label = if (missing.isNullOrBlank()) "local" else missing
// label == "local"
```

- `?.let { ... }`: thực hiện block **chỉ khi giá trị không null**; phù hợp với cấu hình tùy chọn.
- `isNullOrBlank()`: kiểm tra `null`, chuỗi rỗng và chuỗi toàn whitespace.
- `requireNotNull(value) { "message" }`: yêu cầu giá trị bắt buộc, ném `IllegalArgumentException` có message rõ ràng khi null.
- `!!`: khẳng định bất chấp compiler rằng giá trị không null; nếu sai sẽ ném `NullPointerException`. **Hạn chế dùng trong build script**, vì lỗi không giải thích được người dùng thiếu property nào.

Kotlin cũng hỗ trợ `as?` (safe cast), nhưng không nên ép kiểu dữ liệu động vô cớ nếu có thể đọc property qua API trả về `Provider<String>` có kiểu chính xác hơn.

## 8. Gradle `Provider`: giá trị chưa có và giá trị nullable khác nhau

Trong build script, cấu hình thường đến từ `-P...`, `gradle.properties`, biến môi trường hoặc kết quả từ task khác. Gradle dùng `Provider<T>` và `Property<T>` để cung cấp dữ liệu theo cách **lazy** và có khả năng theo dõi dependency.

| Dạng | Ý nghĩa | Khi nào nên dùng |
| --- | --- | --- |
| `String` | Chuỗi đã có | Giá trị cố định hoặc đã xác định ở Configuration |
| `String?` | Chuỗi đã được đọc, có thể null | Xử lý một lựa chọn tùy chọn ngay lúc cấu hình |
| `Provider<String>` | Giá trị được cung cấp qua Gradle, có thể chưa có hoặc chưa được tính | Cấu hình lazy và nối tới task properties |
| `Property<String>` | Đầu vào/thuộc tính có thể `set`/`convention`; cũng là provider | Đặc biệt thích hợp cho input của custom task |

Ví dụ khai báo trong `build.gradle.kts`:

```kotlin
val channelProvider = providers.gradleProperty("releaseChannel")
val channelWithDefault = channelProvider.orElse("local")

val channelNow: String = channelWithDefault.get()
val optionalNow: String? = channelProvider.orNull
```

Giải thích:

- `providers.gradleProperty("releaseChannel")`: trả về `Provider<String>`; nếu property chưa có, provider không có giá trị.
- `.orElse("local")`: tạo **provider mới có fallback**, vẫn có thể dùng lazy.
- `.get()`: yêu cầu giá trị **ngay lúc gọi**. Nếu gọi trên provider rỗng không có default thì có thể ném exception.
- `.orNull`: lấy giá trị hiện tại hoặc `null` nếu absent; **đã truy xuất** provider tại thời điểm gọi.
- `.getOrElse("local")`: lấy giá trị hoặc fallback trực tiếp, trả về `String`.

Khi một giá trị cần chảy vào task, **ưu tiên truyền `Provider` cho `Property` của task** thay vì vội gọi `.get()` ở top-level. Cách này giúp Gradle duy trì thông tin về giá trị, dependency và Configuration Cache tốt hơn.

### Giá trị từ `-P` và `gradle.properties`

Ví dụ trong `gradle.properties`:

```properties
releaseChannel=qa
```

Hoặc truyền từ CLI:

```bash
./gradlew showRelease -PreleaseChannel=prod
```

Tương ứng:

```kotlin
val release = providers.gradleProperty("releaseChannel")
    .orElse("dev")
```

`providers.gradleProperty` tìm **Gradle project property từ các nguồn build hỗ trợ**. Nó không đọc bất kỳ `extra` property nào được thêm động qua `extra["name"]` và không tự duyệt các file `gradle.properties` của từng thư mục subproject. Nếu cần `Project.findProperty(...)`, phải nhớ đó là cơ chế lookup động khác và trả về `Any?`.

### Biến môi trường và bí mật

```kotlin
val deployToken = providers.environmentVariable("DEPLOY_TOKEN")
val tokenAvailable = deployToken.isPresent
```

`environmentVariable` tạo provider đọc biến môi trường; nếu biến không được đặt, provider có thể absent. **Không in token thật** trong log Gradle, báo cáo task hay lỗi configuration. Tài liệu mẫu chỉ nên dùng giá trị giả, còn secret thực cần được cấp qua kênh được quản lý. `isPresent` cho biết biến có giá trị theo API provider, không thay thế việc kiểm tra một token có thực sự hợp lệ.

## 9. Đọc một property dạng danh sách, xử lý rỗng và kiểm soát dữ liệu

Giả sử người dùng muốn chọn profiles bằng:

```bash
./gradlew listProfiles -Pprofiles=dev,qa,prod -q
```

Trong `build.gradle.kts`:

```kotlin
val rawProfiles: String? = providers.gradleProperty("profiles").orNull

val profiles: List<String> = rawProfiles
    ?.split(",")
    ?.map { it.trim() }
    ?.filter { it.isNotEmpty() }
    ?.distinct()
    ?.takeIf { it.isNotEmpty() }
    ?: listOf("dev")

tasks.register("listProfiles") {
    val text = profiles.joinToString(" | ")
    doLast {
        println("Profiles: $text")
    }
}
```

Nếu truyền `-Pprofiles=dev,qa,prod`, task in:

```text
Profiles: dev | qa | prod
```

Nếu không truyền `profiles`, hoặc truyền chuỗi rỗng/toàn dấu phẩy và khoảng trắng, `profiles` trở thành `listOf("dev")`.

Phân tích các bước:

1. `orNull` biến giá trị từ Gradle thành `String?`.
2. `?.split(",")` biến chuỗi thành `List<String>?`.
3. `?.map { it.trim() }` loại whitespace ở từng mục.
4. `?.filter { it.isNotEmpty() }` loại mục trống.
5. `?.distinct()` loại giá trị trùng, giữ thứ tự gặp lần đầu trong kết quả list.
6. `?.takeIf { it.isNotEmpty() } ?: listOf("dev")` rơi về cấu hình mặc định khi không có mục hợp lệ.

**Chú ý:** Với mục đích bảo mật hoặc chọn môi trường production, không nên tự động biến tên profile sai thành mặc định. Nên kiểm tra các giá trị cho phép và báo lỗi rõ ràng:

```kotlin
val allowed = setOf("dev", "qa", "prod")
require(profiles.all { it in allowed }) {
    "Unsupported profiles. Allowed: ${allowed.joinToString(", ")}"
}
```

Nếu viết đoạn này vào cùng file mẫu ở trên, hãy đặt sau khi `profiles` đã được tính và trước khi đăng ký task cần dùng nó.

## 10. Ví dụ đầy đủ, chạy được: string template + List + Map + nullable

Tạo một project Gradle mới hoặc dùng project Gradle đã có Wrapper, đặt hai file sau ở root. Ví dụ không yêu cầu Java source code hoặc dependency ngoài; task chỉ in dữ liệu.

**Tệp `settings.gradle.kts`:**

```kotlin
rootProject.name = "kotlin-values-demo"
```

**Tệp `build.gradle.kts`:**

```kotlin
val environments: List<String> = listOf("dev", "qa", "prod")

val descriptionByEnv: Map<String, String> = mapOf(
    "dev" to "Local",
    "qa" to "Quality assurance",
    "prod" to "Production"
)

val suppliedEnv: String? = providers.gradleProperty("environment").orNull
val selectedEnv: String = suppliedEnv
    ?.trim()
    ?.takeIf { it.isNotEmpty() }
    ?: "dev"

val selectedDescription = descriptionByEnv[selectedEnv] ?: "Unknown"

val report = listOf(
    "Project: ${rootProject.name}",
    "Available: ${environments.joinToString(", ")}",
    "Selected: $selectedEnv",
    "Description: $selectedDescription",
    "Uppercase: ${selectedEnv.uppercase()}"
).joinToString("\n")

tasks.register("showConfiguration") {
    val message = report
    doLast {
        println(message)
    }
}

environments.forEach { env ->
    val suffix = env.replaceFirstChar { it.uppercase() }
    tasks.register("show$suffix") {
        val message = "Preset: $env"
        doLast {
            println(message)
        }
    }
}
```

**Lệnh chạy Linux/macOS:**

```bash
./gradlew showConfiguration --no-configuration-cache -Penvironment=qa -q
./gradlew showProd --no-configuration-cache -q
```

**Lệnh tương đương trên Windows PowerShell:**

```powershell
.\gradlew.bat showConfiguration --no-configuration-cache -Penvironment=qa -q
.\gradlew.bat showProd --no-configuration-cache -q
```

Stdout từ **task action của lệnh đầu tiên**, khi chạy thành công:

```text
Project: kotlin-values-demo
Available: dev, qa, prod
Selected: qa
Description: Quality assurance
Uppercase: QA
```

Stdout từ **task action của lệnh thứ hai**:

```text
Preset: prod
```

Giải thích chi tiết:

- `environments` là `List<String>` để giữ thứ tự dev → qa → prod.
- `descriptionByEnv` là `Map<String, String>`. Lấy theo key trả về `String?`, nên dùng `?: "Unknown"`.
- `suppliedEnv` là `String?`, vì project property `environment` có thể không tồn tại.
- `selectedEnv` trở thành `String` sau xử lý null/rỗng và fallback.
- `report` là một chuỗi được nối từ `List<String>`; `joinToString("\n")` bảo đảm xuống dòng theo ký tự newline.
- `tasks.register("showConfiguration")` và vòng `forEach` đăng ký các task trong Configuration.
- Chỉ action của task được yêu cầu chạy ở Execution. Việc đăng ký `showDev` và `showQa` không khiến chúng tự chạy khi gọi `showProd`.
- `--no-configuration-cache` làm đường đi minh họa dễ quan sát; không bắt buộc với bản thân cú pháp Kotlin.

Nếu dùng `-Penvironment=unknown`, ví dụ sẽ in `Description: Unknown`. Đây là hành vi được chọn để **giải thích nullable map lookup**. Khi giá trị liên quan đến phát hành hoặc deploy, nên thay fallback đó bằng kiểm tra `requireNotNull`/allowed values để chặn sai cấu hình.

## 11. Ví dụ tốt hơn khi cần input lazy cho task

Đọc `Provider<String>` thành `String?` ở top-level có thể phù hợp để quyết định **cấu trúc build**, ví dụ đăng ký task theo danh sách profile. Nhưng với dữ liệu là **input của task**, Gradle khuyến khích khai báo `Property<T>` và kết nối provider trực tiếp.

Ví dụ dưới đây là một `build.gradle.kts` **độc lập** minh họa custom task typed:

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class PrintChannel : DefaultTask() {
    @get:Input
    abstract val channel: Property<String>

    @TaskAction
    fun printChannel() {
        println("Channel: ${channel.get()}")
    }
}

tasks.register<PrintChannel>("printChannel") {
    channel.convention(
        providers.gradleProperty("releaseChannel").orElse("local")
    )
}
```

Lệnh:

```bash
./gradlew printChannel -PreleaseChannel=qa -q
```

Stdout của action:

```text
Channel: qa
```

Ở ví dụ này:

- `channel` có kiểu `Property<String>`: Gradle quản lý đầu vào typed của task.
- `@get:Input` đánh dấu `channel` là giá trị đầu vào có thể theo dõi.
- `channel.convention(provider)` dùng giá trị mặc định nếu task property chưa được set; bản thân provider lấy `releaseChannel` hoặc fallback `local`.
- `channel.get()` được đọc trong `@TaskAction`, tức đúng lúc task thực thi.
- Dùng `Property` giúp task có API rõ ràng, dễ hỗ trợ Configuration Cache và kiểm tra input hơn so với đóng gói các phép đọc cấu hình động vào `doLast`.

`@Input` giúp Gradle theo dõi giá trị trong task model; chỉ khai báo `@Input` **không tự làm task có outputs hay cache kết quả**. Để tạo task thực sự sinh artifact có thể incremental/cache, còn cần khai báo outputs và tuân thủ quy tắc task implementation.

## 12. Khi nào nên dùng `Map`, `getValue`, `?:`, hoặc `requireNotNull`?

Đây là bốn hành vi khác nhau, chọn theo ý nghĩa nghiệp vụ:

```kotlin
val endpoints = mapOf(
    "dev" to "https://dev.example.invalid",
    "qa" to "https://qa.example.invalid"
)

val selected = "prod"

val nullableEndpoint: String? = endpoints[selected]
val fallbackEndpoint: String = endpoints[selected] ?: "disabled"

// endpoints.getValue(selected)
// -> lỗi khi key "prod" không tồn tại

// requireNotNull(endpoints[selected]) {
//     "Unsupported environment: $selected"
// }
// -> lỗi rõ ràng khi key "prod" không tồn tại
```

- **`endpoints[selected]`**: chấp nhận key không tồn tại; caller xử lý `String?`.
- **`?: "disabled"`**: có fallback rõ ràng; thích hợp khi hệ thống có mặc định thực sự an toàn.
- **`getValue(selected)`**: bắt buộc key đã có; exception mặc định khi thiếu.
- **`requireNotNull(...)`**: bắt buộc key có và cho phép thông báo lỗi cụ thể về cấu hình.

Các URL `.example.invalid` ở ví dụ là địa chỉ minh họa, không phải endpoint thật. Không nhúng URL có token hoặc thông tin nội bộ nhạy cảm trực tiếp trong source được commit.

## 13. Các lỗi Kotlin DSL thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `Too many characters in a character literal` | Viết `'hello'` như Groovy | Dùng `"hello"` cho `String` |
| `Unresolved reference` khi dùng `$moduleSuffix` | Nội suy nhầm tên biến dài hơn mong muốn | Dùng `${module}Suffix` |
| Muốn in `$HOME` nhưng Kotlin tìm biến `HOME` | Dấu `$` kích hoạt string template | Dùng `"\$HOME"` hoặc `"""${'$'}HOME"""` |
| Raw string hiển thị `\n` nguyên văn | `"""..."""` không xử lý escape | Dùng multiline thực hoặc chuỗi thường `"\n"` |
| `Only safe (?.) or non-null asserted (!!.) calls are allowed` | Đang gọi method trên `String?` | Dùng `?.`, `?:`, `let` hoặc kiểm tra null |
| Dùng `?:` nhưng property toàn whitespace vẫn được giữ | Elvis chỉ xử lý `null` | `trim()?.takeIf { it.isNotEmpty() } ?: default` với safe-call khi nullable |
| `Map.get(...)` không gán được vào `String` | Lookup có thể thiếu key, nên trả `String?` | Có fallback hoặc `requireNotNull` |
| Gọi `provider.get()` trên property chưa khai báo | Provider absent, không có fallback | Dùng `orElse`, `getOrElse`, `orNull` hoặc lỗi cấu hình có nghĩa |
| Đã khai báo `val list` nhưng `list.add(...)` không có | `listOf` tạo read-only `List` | Dùng phép `+`/transform hoặc `mutableListOf` khi cần mutation |
| Đổi `listOf` thành `setOf` khiến xử lý mất bản sao | Set không giữ phần tử trùng | Chọn List nếu duplicates có ý nghĩa |
| Dùng `implementation(...)` báo unresolved | Plugin/configuration tạo accessor chưa được áp dụng hoặc chưa sẵn | Kiểm tra plugin `java`/`java-library`, thời điểm khai báo và API |
| Đọc `project` trong `doLast` dẫn đến vấn đề Configuration Cache | Task action giữ tham chiếu state cấu hình không được phép | Dùng task `Property`/providers/inputs thay vì truy cập Project khi thực thi |
| Dùng `System.getenv` trực tiếp ở nhiều nơi | Dữ liệu môi trường được đọc thẳng trong configuration và khó quản lý | Ưu tiên `providers.environmentVariable(...)`; không log secrets |
| Task được tạo sai tên từ dữ liệu người dùng | Nội suy `$name` chưa chuẩn hóa/validate | Chuẩn hóa whitelist và thiết kế tên task ổn định |

### Một lỗi nguy hiểm: Elvis trong Kotlin khác “truthiness” của Groovy

```kotlin
val option: String? = ""
val chosen = option ?: "default"
// chosen == "", KHÔNG phải "default"
```

Muốn giá trị mặc định khi rỗng:

```kotlin
val chosen = option?.takeIf { it.isNotBlank() } ?: "default"
```

Trong Kotlin, `false` và `0` cũng là **giá trị không null hợp lệ**. Đừng dùng dấu `?:` như một phép `if value is falsy`.

### Một lỗi trong build thực tế: đọc nhiều lần nguồn cấu hình

```kotlin
// Kém rõ ràng: hỏi provider lặp lại ở nhiều biểu thức cấu hình
val a = providers.gradleProperty("stage").orNull
val b = providers.gradleProperty("stage").orNull
```

Khi nhiều nơi cần cùng một giá trị, nên định nghĩa `val stageProvider = providers.gradleProperty("stage")` rồi dùng provider đó, hoặc truyền nó vào task property. Việc này làm rõ quan hệ cấu hình và tránh lặp logic fallback. Nếu cần thay đổi cấu trúc build dựa trên giá trị, có thể đọc một lần ở Configuration, nhưng nên xem đó là lựa chọn có chủ đích.

## 14. Quy tắc thực hành và bài tập

Một số nguyên tắc giúp Kotlin DSL rõ ràng và ổn định:

1. Dùng `"..." ` cho chuỗi, `$name` hoặc `${expression}` để nội suy; dùng `"""..."""` và `trimIndent()` cho nhiều dòng.
2. Dùng `listOf`, `setOf`, `mapOf` để biểu diễn dữ liệu cấu hình; ưu tiên biến đổi `map`/`filter`/`distinct` thay vì mutation lan rộng.
3. Nhớ **`Map.get` trả nullable** ngay cả khi value type là `String`.
4. Với cấu hình tùy chọn, xử lý cả **null** lẫn **blank** nếu đó là điều nghiệp vụ mong muốn.
5. Dùng `providers.gradleProperty` và `providers.environmentVariable` cho dữ liệu môi trường; ưu tiên truyền `Provider` vào `Property` của task.
6. Đặt logic chọn task/đăng ký task trong Configuration; đặt công việc thực sự của task trong action. Không tự ý truy cập `Project` từ action cần hỗ trợ Configuration Cache.
7. Cấu hình quan trọng như môi trường release nên **validate và fail fast**; không âm thầm chọn mặc định bất kỳ.
8. Đặt text/danh sách chung vào version catalog hoặc convention plugin khi logic dài, nhưng chỉ khi điều đó làm giảm sự lặp và giữ nguồn sự thật rõ ràng.

### Bài tập 1: Nội suy

Cho:

```kotlin
val module = "inventory"
val version = "3"
val result = "${module}Api-v$version"
```

**Đáp án:** `inventoryApi-v3`. Dấu ngoặc nhọn cho phép Kotlin biết tên biến là `module`, còn phần `Api` là văn bản tiếp theo.

### Bài tập 2: List và Set

Cho:

```kotlin
val names = listOf("api", "web", "api", "core")
val result = names.distinct().filter { it != "core" }
```

**Đáp án:** `["api", "web"]`. `distinct()` loại bản sao theo thứ tự xuất hiện đầu tiên, sau đó `filter` loại `core`.

### Bài tập 3: Null và blank

Cho:

```kotlin
val raw: String? = "   "
val a = raw ?: "dev"
val b = raw?.trim()?.takeIf { it.isNotEmpty() } ?: "dev"
```

**Đáp án:** `a` giữ chuỗi ba dấu cách; `b == "dev"`. Elvis chỉ dùng fallback khi vế trái là `null`, còn `trim` và `takeIf` tạo ra `null` cho chuỗi không có ký tự có nghĩa.

### Bài tập 4: Map lookup

Cho:

```kotlin
val ports = mapOf("dev" to 8080, "qa" to 9090)
val prodPort = ports["prod"] ?: 8080
```

**Đáp án:** `prodPort == 8080` và có kiểu `Int`. `ports["prod"]` có kiểu `Int?` vì khóa không tồn tại. Nếu đây là cấu hình deployment, nên cân nhắc báo lỗi thay vì fallback về cổng dev.

### Bài tập 5: Lazy provider

`providers.gradleProperty("profile")` được khai báo nhưng không truyền `-Pprofile` và không có giá trị tương ứng. Điều gì xảy ra với `.get()`, `.orNull` và `.orElse("dev").get()`?

**Đáp án:** `.get()` trên provider absent có thể ném lỗi vì không có giá trị; `.orNull` trả `null`; `.orElse("dev").get()` trả `"dev"`. Việc `.get()` hoạt động sau khi có fallback không biến thao tác đọc thành lazy: nó vẫn truy xuất ngay tại thời điểm gọi.

## Tài liệu chính thức

- [Gradle Kotlin DSL Primer](https://docs.gradle.org/current/userguide/kotlin_dsl.html) — cú pháp script, type-safe accessors và Provider/Property.
- [Gradle Kotlin DSL Reference](https://docs.gradle.org/current/kotlin-dsl/index.html) — hàm và kiểu cụ thể trong Kotlin DSL/Gradle API.
- [Gradle Build File Basics](https://docs.gradle.org/current/userguide/build_file_basics.html) — build scripts và cấu trúc plugin/dependency.
- [Gradle Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html) — project properties, `providers.gradleProperty` và environment providers.
- [Gradle Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html) — mô hình Provider/Property và cách nối giá trị.
- [Gradle Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html) — ràng buộc khi task actions truy cập state của Project.
- [Kotlin: Strings](https://kotlinlang.org/docs/strings.html) — escaped strings, raw strings và templates.
- [Kotlin: Collections Overview](https://kotlinlang.org/docs/collections-overview.html) — List/Set/Map, read-only và mutable collections.
- [Kotlin: Null Safety](https://kotlinlang.org/docs/null-safety.html) — nullable types, safe call, Elvis, `let` và `!!`.
