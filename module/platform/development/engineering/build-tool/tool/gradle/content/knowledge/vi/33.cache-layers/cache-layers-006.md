# Dùng Provider, ValueSource và Build Service đúng mục đích trong Gradle

Trong một build Gradle lớn, các giá trị dùng để cấu hình nhiệm vụ có thể đến từ `gradle.properties`, biến môi trường, file cấu hình, output của một task khác, kết quả lệnh hệ thống hoặc dịch vụ dùng chung như HTTP client/database connection. Nếu đọc tất cả ngay trong `build.gradle.kts` bằng `System.getenv(...)`, `file(...).readText()` và `project.tasks.getByName(...)`, bạn dễ tạo build chậm, không thể tái sử dụng Configuration Cache, bỏ sót task dependencies hoặc đưa state không an toàn vào task outputs.

Gradle cung cấp ba công cụ liên quan nhưng **không thay thế cho nhau**:

- **`Provider<T>` và `Property<T>`**: mô hình **giá trị được tính/cấu hình theo nhu cầu**, có thể nối output task này với input task khác và tránh đọc giá trị sớm.
- **`ValueSource<T, P>`**: mô hình **nguồn thông tin bên ngoài** với quy tắc fingerprint dành cho Configuration Cache; thích hợp khi built-in providers không đủ, đặc biệt khi giá trị ngoại sinh cần quyết định **build configuration**.
- **`BuildService<P>`**: đối tượng **chia sẻ tài nguyên/trạng thái trong một Gradle build**, có vòng đời do Gradle quản lý và có thể giới hạn số task dùng đồng thời; không phải kho lưu output giữa các build invocations.

Bài thuộc phần **Các lớp cache** của *Build Tool Gradle* và tập trung đúng mục tiêu **“Dùng Provider, ValueSource và Build Service đúng mục đích”**. Bạn sẽ biết chúng ảnh hưởng tới Configuration Cache, Build Cache, up-to-date checks như thế nào; hiểu lý do không dùng `get()` bừa bãi; viết một ví dụ **Gradle Kotlin DSL + Java 17 hoàn chỉnh** với cả ba loại API; thực hành đổi Gradle property, biến môi trường, xem cache hit/miss và task logs; học cách thiết kế service concurrency, tránh đưa dữ liệu không ổn định vào cache, kiểm thử và chẩn đoán lỗi.

## 1. Bản đồ “các lớp cache” trước khi chọn API

Gradle có nhiều cơ chế tránh làm lại công việc:

| Cơ chế | Cache cái gì? | Tín hiệu thực tế | API trong bài liên quan |
| --- | --- | --- | --- |
| **Configuration Cache** | Kết quả configuration phase: task graph, configured task state và dependency information | `Configuration cache entry stored/reused` hoặc lý do invalidation | `Provider` lazy wiring, `ValueSource` config-input tracking, `BuildService` references/parameters |
| **Build Cache** | Outputs của tasks/artifact transforms được phép cache | Task `FROM-CACHE` | `@Input`, `@OutputFile`, `@CacheableTask`, provider task outputs |
| **Up-to-date checks** | Local task input/output fingerprints từ lần build trước | Task `UP-TO-DATE` | Declared task inputs/outputs và dependency provenance |
| **Incremental task action** | Thay vì xử lý toàn bộ inputs, task chỉ xử lý phần thay đổi | Task có thể vẫn `EXECUTED` | `InputChanges` và incremental annotations |
| **Dependency resolution cache** | Metadata/artifacts hoặc kết quả dependency resolution theo quy tắc Gradle | Download/resolve được reuse | `Configuration`, repository/dependency metadata, không phải BuildService |

**Provider không phải một cache mới. ValueSource không phải remote Build Cache. BuildService không giữ một Java object “sống mãi” sau khi Gradle invocation kết thúc.**

Chúng chủ yếu giúp Gradle **có đúng thông tin để các cache sẵn có hoạt động an toàn**. Dùng đúng API có thể làm Configuration Cache hit, nhưng không đảm bảo mọi task sẽ `UP-TO-DATE` hoặc `FROM-CACHE`.

Theo tài liệu Gradle 9.x, Configuration Cache vẫn là cơ chế riêng với Build Cache: cấu hình có thể được reuse trong khi task action vẫn chạy vì input đổi, hoặc task outputs có thể được phục hồi từ Build Cache sau khi configuration không được reuse.

## 2. Quy tắc lựa chọn trong 10 giây

| Câu hỏi | Dùng gì? | Vì sao? |
| --- | --- | --- |
| “Đọc `-Precipient=Team` và truyền cho task” | `providers.gradleProperty("recipient")` + task `Property<String>` | Gradle đã có built-in provider, không cần code ValueSource |
| “Đọc một env var” | `providers.environmentVariable("CI")` | Có API built-in, không cần `System.getenv` trong script |
| “Đọc nội dung file cấu hình dạng text” | `providers.fileContents(...).asText` | Giá trị có source semantics và có thể nối lazy vào task |
| “Dùng output file của task A cho task B” | `TaskProvider.flatMap { it.outputFile }` | Giữ **task dependency provenance** |
| “Quyết định task set theo một kết quả CLI/phân tích env phức tạp” | Custom `ValueSource`, có thể `get()` ở configuration khi thực sự cần | Gradle theo dõi giá trị nguồn bên ngoài để quyết định Configuration Cache reuse |
| “Nhiều tasks chia sẻ một connection/client/cache trong cùng build” | `BuildService` | Một service được Gradle quản lý, có giới hạn concurrency và lifecycle |
| “Chỉ một task chạy với license server tại một thời điểm” | `BuildService` + `maxParallelUsages.set(1)` | Gradle scheduler giới hạn **các tasks đã khai báo dùng service** |
| “Cache file generated và chia sẻ giữa CI machines” | `@CacheableTask` + Build Cache; input/output declarations chính xác | BuildService state không phải output cache |
| “Muốn phát hiện mọi task completion khi Configuration Cache bật” | Build Service + `BuildEventsListenerRegistry.onTaskCompletion` | Build listeners cấu hình truyền thống có thể không chạy lại trên cache hit |

## 3. Provider và Property: đọc theo nhu cầu, không đọc càng sớm càng tốt

Gradle dùng hai giao diện:

- `Provider<T>`: đại diện giá trị **chỉ đọc**; có thể query `get()`/`orNull`/`isPresent`, transform bằng `map`, nối provider bằng `flatMap`, dùng fallback `orElse`.
- `Property<T>`: **cấu hình được**; kế thừa `Provider<T>`, có `set(value)` và `set(provider)` hoặc `convention(value/provider)`.

Ví dụ:

~~~kotlin
val recipient: Provider<String> =
    providers.gradleProperty("recipient").orElse("Gradle")

val message: Provider<String> =
    recipient.map { name -> "Hello, " + name + "!" }
~~~

**Đây là mảnh Kotlin DSL**, dùng được trong Gradle project, không tự tạo task/output nếu đứng một mình. `recipient` mô tả nơi lấy giá trị; `message` là một provider khác được tính dựa trên giá trị đó.

`Property` thường xuất hiện trong một custom task:

~~~kotlin
abstract class PrintMessage : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @TaskAction
    fun printMessage() {
        println(message.get())
    }
}

tasks.register<PrintMessage>("printMessage") {
    message.set(
        providers.gradleProperty("recipient")
            .orElse("Gradle")
            .map { "Hello, " + it + "!" }
    )
}
~~~

Mảnh trên cần các imports `DefaultTask`, `Property`, `Input` và `TaskAction` hoặc Kotlin DSL default imports tương ứng. Đây là cách kết nối provider **vào task input property**. Khi action thực thi, `message.get()` là điều bình thường vì đó là thời điểm task sử dụng input đã khai báo.

### `set` và `convention` khác nhau

~~~kotlin
message.convention("Hello, World!")
message.set(providers.gradleProperty("message"))
~~~

- `convention` đặt giá trị mặc định, thường cho phép cấu hình override.
- `set` chỉ định explicit value/provider, ghi đè default convention.
- `finalizeValue()` chốt giá trị ngay, `finalizeValueOnRead()` chốt ở lần đọc đầu, `disallowChanges()` ngăn thay đổi tiếp theo theo API contract.

**Không gọi `finalizeValue()` sớm chỉ vì muốn build “ổn định”**: nó có thể ép provider tính giá trị trước khi một plugin khác cấu hình xong. Dùng finalization khi đã hiểu ownership/lifecycle của property.

## 4. `map`, `flatMap`, `zip` và `orElse`

| Method | Input/output | Tình huống thường dùng |
| --- | --- | --- |
| `map { transform }` | `Provider<A> -> Provider<B>` | Chuyển tên/version thành chuỗi, đổi text thành số |
| `flatMap { providerB }` | `Provider<A> -> Provider<B>` khi transform trả **Provider** | Lấy property output từ TaskProvider hoặc một model provider |
| `zip(other) { a, b -> ... }` | Kết hợp hai providers | Tạo một string/config phụ thuộc hai nguồn |
| `orElse(value/provider)` | Provider có fallback nếu không có value | Mặc định an toàn cho optional Gradle/env property |
| `get()` | Buộc lấy giá trị hiện tại | Task action hoặc quyết định cấu hình thật sự cần |
| `orNull`/`isPresent` | Kiểm tra absence | Chỉ khi cần phân nhánh; đọc ở config phase vẫn có thể tạo config input |

Ví dụ `map`:

~~~kotlin
val rawVersion = providers.gradleProperty("libVersion")
    .orElse("1.0.0")

val majorVersion = rawVersion.map { it.substringBefore(".") }
~~~

`flatMap` phù hợp với task outputs:

~~~kotlin
// Project đã có Java plugin và task jar.
val builtJar = tasks.named<Jar>("jar")

tasks.register<Copy>("copyJar") {
    from(builtJar.flatMap { it.archiveFile })
    into(layout.buildDirectory.dir("distribution"))
}
~~~

`archiveFile` là `RegularFileProperty` của `Jar` task. Việc nối Provider giữ thông tin **task nào tạo file**, nên Gradle có thể suy ra task dependency. Nếu chuyển quá sớm thành `archiveFile.get().asFile` hoặc tự viết string path `build/libs/foo.jar`, bạn có thể mất provenance.

`zip` kết hợp hai providers; cú pháp mô hình:

~~~kotlin
val first = providers.gradleProperty("first").orElse("Ada")
val last = providers.gradleProperty("last").orElse("Lovelace")

val fullName = first.zip(last) { f, l -> f + " " + l }
~~~

Điểm quan trọng là **mô tả chuỗi tính toán** thay vì đọc cả hai rồi tạo một String ngay trong configuration phase.

## 5. Sai lầm phổ biến: gọi `get()` trong configuration phase vô điều kiện

Mảnh **không nên lạm dụng**:

~~~kotlin
val endpoint = providers.environmentVariable("API_ENDPOINT")
    .orElse("http://localhost")
    .get()

tasks.register("someTask") {
    // Giá trị đã bị đọc sớm và đóng thành String.
}
~~~

Đọc env var tại configuration time khiến nó có thể trở thành **Configuration Cache input**. Nếu đổi endpoint, Gradle có thể phải **reconfigure** dù chỉ một task cần giá trị khi chạy. Tệ hơn, một phép tính nặng đọc file/process/network tại configuration time làm mọi invocation chậm, kể cả lúc chạy task không cần nguồn đó.

Hướng tốt hơn:

~~~kotlin
abstract class UseEndpoint : DefaultTask() {
    @get:Input
    abstract val endpoint: Property<String>

    @TaskAction
    fun use() {
        println("Endpoint: " + endpoint.get())
    }
}

tasks.register<UseEndpoint>("useEndpoint") {
    endpoint.set(
        providers.environmentVariable("API_ENDPOINT")
            .orElse("http://localhost")
    )
}
~~~

Đây là **mảnh task type**; muốn chạy độc lập cần imports tương ứng và project setup. Provider được truyền vào task input; với Configuration Cache, Gradle có thể giữ calculation và đánh giá khi task cần thay vì reconfigure toàn build mỗi khi giá trị đổi.

**Ngoại lệ có chủ đích:** nếu giá trị env **quyết định bạn phải register những tasks nào, apply plugin nào, chọn dependency repositories nào**, thì cần biết nó trong configuration phase. Khi đó `get()` có thể hợp lý, nhưng phải theo dõi giá trị ấy bằng API Gradle và tránh phép tính quá nặng.

### “Provider = không bao giờ tính trong configuration phase” là sai

Configuration Cache có thể **serialize provider by value hoặc by computation** theo source và usage. Một provider có thể bị đọc khi Gradle lưu task graph vào Configuration Cache. Hãy hiểu Provider là **mô hình deferred value & dependency**, không hứa mọi computation đều trì hoãn đến đúng `@TaskAction`.

Nguồn: [Gradle Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html), [Provider API](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/Provider.html).

## 6. Dùng built-in providers trước khi tự viết ValueSource

Gradle đã có các APIs theo nguồn dữ liệu:

~~~kotlin
val name = providers.gradleProperty("recipient")
    .orElse("Gradle")

val isCi = providers.environmentVariable("CI")
    .map { it.equals("true", ignoreCase = true) }
    .orElse(false)

val javaHome = providers.systemProperty("java.home")

val configText = providers.fileContents(
    layout.projectDirectory.file("config/channel.txt")
).asText
~~~

Bốn đoạn là **mảnh minh họa**, chưa có `config/channel.txt` nếu bạn không tự tạo; không ép `configText.get()` khi file chưa tồn tại.

Những nguồn phổ biến:

| API | Đọc gì? | Ghi chú |
| --- | --- | --- |
| `providers.gradleProperty("x")` | Gradle project property `-Px=...` hoặc sources khác Gradle quản lý | Ưu tiên khi biến là tùy chọn build policy |
| `providers.environmentVariable("X")` | Một env variable | Không cần gọi `System.getenv` trong buildscript |
| `providers.environmentVariablesPrefixedBy("CI_")` | Map env vars theo prefix | Hữu ích khi danh sách keys thay đổi |
| `providers.systemProperty("x")` | Java system property `-Dx=...` | Khác Gradle project property |
| `providers.systemPropertiesPrefixedBy("foo.")` | Map system properties theo prefix | Theo dõi additions/removals phù hợp prefix |
| `providers.fileContents(file).asText` | Nội dung text file | Có thể dùng `map` để parse |
| `providers.exec { ... }` | Output của một command (khi phù hợp) | Cân nhắc chi phí, output/exit semantics và Configuration Cache |
| `providers.of(MyValueSource::class) { ... }` | Nguồn custom | Dùng khi nguồn/normalization phức tạp hơn built-in providers |

**Không tạo custom ValueSource cho mọi `-Pfoo`**. Điều đó thêm API class và làm khó bảo trì. Bắt đầu bằng built-in Provider và task properties.

### `providers.exec` và `ExecOperations`

Khi một task cần thực thi command để tạo output, dùng **task action** với injected `ExecOperations` hoặc Gradle-supported task type, khai báo inputs/outputs để task caching đúng. `providers.exec` hoặc ValueSource dùng `ExecOperations` phù hợp khi cần một giá trị của command làm **configuration input**, chẳng hạn kiểm tra Git revision/version. Không chạy shell tùy ý ở mọi configuration chỉ vì dễ viết một dòng `ProcessBuilder`.

## 7. ValueSource giải quyết bài toán nào?

Một `ValueSource<T, P>` là abstraction cho dữ liệu đến từ bên ngoài Gradle model. Nó được dùng khi bạn cần:

- Đọc/chuẩn hóa nhiều env/system properties theo quy tắc phức tạp.
- Gọi một CLI nhanh lấy version/commit ID phục vụ quyết định cấu hình.
- Parse file dạng custom format mà `providers.fileContents(...).asText.map(...)` chưa thích hợp.
- Làm **Configuration Cache theo dõi giá trị đã xử lý**, không nhất thiết tất cả raw inputs của computation.

Gradle coi giá trị **trả về từ `obtain()`** là phần tử quan trọng:

~~~text
External state
  - file / env / system property / short CLI
          |
          v
      ValueSource.obtain()
          |
          v
      normalized returned value
          |
   queried during configuration?
     yes                    no
      |                      |
      v                      v
Config Cache input         Provider can be wired
(recompute on builds)      to task input lazily
~~~

Khi một ValueSource được query ở **configuration phase**, Gradle kiểm tra **giá trị kết quả** trong lần build sau: `obtain()` được gọi lại để xác nhận Configuration Cache entry còn hợp lệ. Nếu kết quả giống, entry có thể reuse dù raw external state đã thay đổi; nếu khác, entry invalidated. Đó là **điểm khác** so với một số built-in environment/file providers dùng trực tiếp khi configuration.

**Giữ `obtain()` nhanh, deterministic và không có side effects.** Nó có thể chạy lại mỗi invocation để kiểm tra config cache, kể cả invocation không cần thực thi task action. Nếu mỗi `obtain()` gọi một dịch vụ mạng chậm, bạn có thể làm mất phần lớn lợi ích Configuration Cache.

Nguồn: [Configuration Cache Requirements — Value Sources](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html#config_cache:requirements:external_processes).

## 8. Khung khai báo ValueSource đúng

Kotlin DSL:

~~~kotlin
import org.gradle.api.provider.ValueSource
import org.gradle.api.provider.ValueSourceParameters

abstract class NormalizedChannelSource :
    ValueSource<String, ValueSourceParameters.None> {

    override fun obtain(): String {
        val raw = System.getenv("DEMO_CHANNEL")
            ?.trim()
            ?.lowercase()

        return when (raw) {
            "prod", "production" -> "production"
            else -> "development"
        }
    }
}
~~~

Đây là **một class hoàn chỉnh**, có thể đặt trong Gradle Kotlin DSL script nếu project dùng Gradle version phù hợp. `ValueSourceParameters.None` được dùng vì không cần parameters từ Gradle model; source chủ động đọc một env var theo quy tắc normalization.

Đăng ký Provider:

~~~kotlin
val channelProvider =
    providers.of(NormalizedChannelSource::class) {}
~~~

Đọc giá trị:

~~~kotlin
val selectedChannel = channelProvider.get()
~~~

Khi `get()` xuất hiện trong buildscript configuration phase, Gradle theo dõi **giá trị normalization**. Ví dụ:

| Raw `DEMO_CHANNEL` | `obtain()` trả | Ý nghĩa với Configuration Cache |
| --- | --- | --- |
| Không đặt | `development` | Thiết lập ban đầu |
| `dev` | `development` | Raw đổi nhưng normalized value không đổi |
| `prod` | `production` | Normalized value đổi ⇒ configuration cần tính lại |
| `production` | `production` | Có thể reuse sau `prod` nếu các config inputs khác không đổi |
| `PROD` | `production` | Normalize chữ hoa/thường |

**Đừng lấy kết luận “ValueSource đọc env trực tiếp là Configuration Cache unsafe”**. Gradle tài liệu hóa việc đọc `System.getenv` **bên trong `obtain()`**: raw env access không được track riêng theo cơ chế automatic detection; returned value mới là config input khi source được query ở configuration time.

Tuy nhiên điều này chỉ an toàn khi **returned value thật sự phản ánh mọi thay đổi external state có thể làm config khác**. Nếu `obtain()` trả constant trong khi build policy ngầm thay đổi theo external state, cache reuse có thể sai.

## 9. ValueSource có parameters: nhận cấu hình từ Gradle một cách managed

Khi phải parametrise nguồn:

~~~kotlin
import org.gradle.api.provider.Property
import org.gradle.api.provider.ValueSource
import org.gradle.api.provider.ValueSourceParameters

abstract class EnvValueSource :
    ValueSource<String, EnvValueSource.Parameters> {

    interface Parameters : ValueSourceParameters {
        val key: Property<String>
    }

    override fun obtain(): String {
        val keyName = parameters.key.get()
        return System.getenv(keyName)?.trim().orEmpty()
    }
}

val sourceProvider = providers.of(EnvValueSource::class) {
    parameters {
        key.set("DEMO_CHANNEL")
    }
}
~~~

**Đây là mảnh đầy đủ về cách khai báo ValueSource** nhưng không tạo task; nếu chỉ đọc một env var thì `providers.environmentVariable("DEMO_CHANNEL")` đơn giản hơn nhiều. Hãy dùng pattern tham số khi nguồn phức tạp hoặc cần reusable implementation.

Các điểm API:

- Tham số thường là managed `Property<T>`, `RegularFileProperty`, collections hoặc nested model phù hợp.
- Parameters được Gradle isolate/snapshot trước khi `obtain()` xử lý; không tự viết một mutable singleton rồi cho ValueSource giữ reference.
- **Không tự implement `getParameters()`**; Gradle tạo implementation.
- `obtain()` trả giá trị nên effectively immutable, serializable/ổn định theo requirements.
- Có thể khai báo `ValueSourceParameters.None` khi không cần parameters.
- Theo Gradle docs, Gradle synchronized calls tới `obtain()` của cùng ValueSource instance; không phải lời hứa rằng mọi global external system đều thread-safe.
- Với process invocation có thể inject `ExecOperations` vào ValueSource implementation theo Gradle-supported service injection; không inject tùy ý mọi Gradle services vào ValueSource parameters.

### Vì sao không dùng ValueSource để làm một “Task trá hình”?

ValueSource không có model task inputs/outputs và task outcome semantics như `DefaultTask`/`@OutputFile`. Nó thích hợp tính **một giá trị** để build biết cấu hình ra sao, không thích hợp để build một ZIP/JAR/large generated source tree. Những outputs đó phải là **tasks** có inputs/outputs; sau đó Provider chuyển chúng tới consumer.

## 10. Build Service dùng để làm gì?

Một `BuildService<P>` chứa trạng thái hoặc tài nguyên dùng chung trong **một Gradle build invocation**:

- Một network client/session được dùng lại giữa các tasks.
- Một database/test server cần start và stop có lifecycle rõ.
- Bộ đếm hoặc in-memory cache của dữ liệu **không làm thay đổi task output nếu chưa mô hình hóa input**.
- Shared concurrency quota để giới hạn tasks truy cập một API có quota/licensing.
- Một listener tương thích Configuration Cache để nhận task completion events.

Gradle đăng ký service qua:

~~~kotlin
val serviceProvider =
    gradle.sharedServices.registerIfAbsent(
        "mySharedService",
        MySharedService::class
    ) {
        maxParallelUsages.set(1)
    }
~~~

**Mảnh này cần class `MySharedService` đã khai báo**. `registerIfAbsent` thường **chỉ đăng ký**, không tạo service instance ngay. Service được tạo khi task dùng. Nếu không task nào dùng, service có thể không được tạo.

`maxParallelUsages.set(1)` giới hạn **số tasks đăng ký dùng service được Gradle chạy đồng thời**. Nó không sắp thứ tự task theo tên, không thay `dependsOn`, không chặn các process bên ngoài Gradle và không tự đảm bảo thread safety nếu trong một task có nhiều threads cùng gọi client.

## 11. BuildService lifecycle và phạm vi

Mô hình:

~~~text
Gradle build start
      |
      v
BuildServiceRegistry.registerIfAbsent(...)
      | provider exists; service may not exist yet
      |
      v
Task first uses service
      | Gradle constructs service
      |
      v
Tasks use instance / concurrency guard
      |
      v
AutoCloseable.close() when instance discarded
      |
      v
End of invocation
~~~

**Service instance không phải persistent cache data.** Khi bật Configuration Cache:

- Gradle **serialize BuildService parameters**, không serialize live service instance như một object để resume vào lần build sau.
- Service có thể được **recreated** ở execution time hoặc lần chạy cache hit.
- Theo Gradle docs, một service được lấy ở configuration time còn có thể bị destroy/recreate trong cùng invocation, vì thế tránh dùng service instance identity hoặc counter state làm dữ liệu cấu hình cố định.
- Gradle có trường hợp đặc biệt cho `OperationCompletionListener` được đăng ký với build events listener API.
- `AutoCloseable.close()` là cách release resource; không giả định close xảy ra ngay đúng lúc task cuối cùng kết thúc.

BuildService **scoped theo build, không phải machine-wide/global service**. Các Gradle invocations khác nhau, composite included builds hoặc CI jobs không thể mặc nhiên dùng một Java service instance làm lock chung. Nếu nhiều builds cùng truy cập một repository/database/file, cần lock/transaction/lease ở cấp external system hoặc orchestrator.

## 12. Hai cách cho Task dùng BuildService

### Cách A — `@ServiceReference`, Gradle tự kết nối

Khai báo trong custom task class:

~~~kotlin
@get:ServiceReference("consoleAudit")
abstract val auditService: Property<ConsoleAuditService>
~~~

Gradle tìm service phù hợp bằng **type**, và tên `consoleAudit` khi annotation chỉ định. Không cần tự set provider hoặc gọi `usesService` trên từng task khi matching rõ ràng. Điều này cũng giúp Gradle nhận biết task uses service để áp dụng `maxParallelUsages`.

**Không đánh dấu cùng một service property bằng `@Input`**: BuildService instance **không** phải portable task input value. Service annotations được Gradle hỗ trợ cho task là `@ServiceReference` hoặc `@Internal` theo hướng dẫn chính thức.

### Cách B — `@Internal`, nối provider và `usesService`

Trong task class:

~~~kotlin
@get:Internal
abstract val auditService: Property<ConsoleAuditService>
~~~

Khi đăng ký task:

~~~kotlin
tasks.register<AuditTask>("auditOne") {
    auditService.set(serviceProvider)
    usesService(serviceProvider)
}
~~~

Cần **cả hai** khi dùng `@Internal`:

1. `auditService.set(serviceProvider)` để task nhận được instance lúc execute.
2. `usesService(serviceProvider)` để Gradle scheduler biết task dùng service và thực thi concurrency quota.

Nếu quên `usesService`, task vẫn có thể gọi service provider, nhưng `maxParallelUsages` **không đảm bảo được áp dụng đúng cho task đó**. Nếu có nhiều services cùng type, `@ServiceReference` không tên có thể ambiguous; chỉ định tên rõ hoặc set provider tường minh.

Nguồn: [Gradle Shared Build Services](https://docs.gradle.org/current/userguide/build_services.html).

## 13. Ví dụ hoàn chỉnh: Provider + ValueSource + BuildService + Java 17

Ví dụ này tạo một Gradle `application` nhỏ, có **hai luồng độc lập**:

1. **Build data flow**: Gradle project property `recipient` được đọc qua built-in Provider; `DEMO_CHANNEL` được chuẩn hóa qua custom ValueSource. Hai giá trị trở thành `@Input` của task cacheable tạo `greeting.txt`; `processResources` nhận output qua TaskProvider; Java 17 đọc resource từ classpath.
2. **Shared resource flow**: hai task audit dùng BuildService tên `consoleAudit` để ghi console logs; service có `maxParallelUsages=1`. Các audit tasks không cần tạo artifact persistent nên không được gắn output/cache giả.

Từ đó bạn có thể đo khác biệt: **Configuration Cache** lưu cấu hình/ValueSource result, **Build Cache/up-to-date** tối ưu generated file, **BuildService** chia sẻ runtime state/concurrency khi tasks thực thi.

### 13.1. Yêu cầu

- Gradle Wrapper **9.x** hoặc phiên bản tương thích với các API `ServiceReference`, `ValueSource`, Kotlin DSL, Configuration Cache.
- JDK 17 toolchain có sẵn hoặc được provisioning đúng cách theo Gradle setup.
- Không cần third-party libraries, Maven Central hay credentials.
- CLI/shell: ví dụ Bash cho Linux/macOS, PowerShell cho Windows.

### 13.2. Cây thư mục

~~~text
provider-service-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/demo/app/Main.java
~~~

Gradle Wrapper phải là wrapper files hợp lệ được tạo bằng Gradle installation phù hợp. Không sao chép/viết tay `gradle-wrapper.jar`.

### 13.3. `settings.gradle.kts` — đầy đủ

~~~kotlin
rootProject.name = "provider-service-demo"
~~~

### 13.4. `build.gradle.kts` — toàn bộ file

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.provider.ValueSource
import org.gradle.api.provider.ValueSourceParameters
import org.gradle.api.services.BuildService
import org.gradle.api.services.BuildServiceParameters
import org.gradle.api.services.ServiceReference
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction
import org.gradle.language.jvm.tasks.ProcessResources

plugins {
    application
}

// A. Provider: task inputs có nguồn lazy từ Gradle property.
val recipientProvider =
    providers.gradleProperty("recipient").orElse("Gradle")

// B. ValueSource: normalized external state dùng khi configuration.
abstract class DemoChannelSource :
    ValueSource<String, ValueSourceParameters.None> {

    override fun obtain(): String {
        val raw = System.getenv("DEMO_CHANNEL")
            ?.trim()
            ?.lowercase()

        return when (raw) {
            "prod", "production" -> "production"
            else -> "development"
        }
    }
}

val channelProvider =
    providers.of(DemoChannelSource::class) {}

// Có chủ đích: config cần biết channel để cấu hình task.
// ValueSource result trở thành Configuration Cache input.
val chosenChannel = channelProvider.get()

// C. Output-producing task: cacheable chỉ vì outputs deterministic.
@CacheableTask
abstract class GenerateGreeting : DefaultTask() {

    @get:Input
    abstract val recipient: Property<String>

    @get:Input
    abstract val channel: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val file = outputFile.get().asFile
        file.parentFile.mkdirs()

        file.writeText(
            "Hello, " + recipient.get() +
                "! [channel=" + channel.get() + "]\n",
            Charsets.UTF_8
        )
    }
}

val generateGreeting =
    tasks.register<GenerateGreeting>("generateGreeting") {
        recipient.set(recipientProvider)
        channel.set(chosenChannel)
        outputFile.set(
            layout.buildDirectory.file(
                "generated/greeting/greeting.txt"
            )
        )
    }

// ProcessResources consumes formal output of GenerateGreeting.
// Gradle preserves the implicit task dependency.
tasks.named<ProcessResources>("processResources") {
    from(generateGreeting)
}

// D. BuildService: một tài nguyên in log shared trong build.
abstract class ConsoleAuditService :
    BuildService<BuildServiceParameters.None>,
    AutoCloseable {

    fun record(label: String) {
        println("Audit service: " + label)
    }

    override fun close() {
        // Không có external resource cần giải phóng trong demo.
    }
}

gradle.sharedServices.registerIfAbsent(
    "consoleAudit",
    ConsoleAuditService::class
) {
    maxParallelUsages.set(1)
}

abstract class AuditTask : DefaultTask() {

    @get:Input
    abstract val label: Property<String>

    @get:ServiceReference("consoleAudit")
    abstract val auditService: Property<ConsoleAuditService>

    @TaskAction
    fun audit() {
        auditService.get().record(label.get())
    }
}

tasks.register<AuditTask>("auditOne") {
    label.set("one")
}

tasks.register<AuditTask>("auditTwo") {
    label.set("two")
}

tasks.register("auditBoth") {
    dependsOn("auditOne", "auditTwo")
}

// E. Java 17 application uses generated classpath resource.
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.app.Main")
}
~~~

Đây là **file Gradle Kotlin DSL đầy đủ**, không cần thêm build-logic hoặc third-party plugins. Các comments A–E chỉ giải thích luồng dữ liệu, không tham gia runtime.

**Một số quyết định cố ý:**

- `recipientProvider` được **truyền** vào `@Input Property`, không gọi `get()` tại configuration time. Task outcome phụ thuộc `recipient`.
- `DemoChannelSource` được query `get()` **có chủ đích trong configuration**. Điều này cho phép bạn nhìn thấy behavior của ValueSource/Configuration Cache khi env thay đổi. Với project chỉ cần channel tại task execution, có thể nối trực tiếp `channel.set(channelProvider)` để hạn chế reconfiguration.
- `GenerateGreeting` có một output file riêng. Action chỉ ghi file này, dựa trên hai `@Input` và UTF-8; `@CacheableTask` có semantics hợp lý.
- `processResources.from(generateGreeting)` giữ quan hệ task producer và không ghi chồng output root của generator.
- `ConsoleAuditService` **không** được đánh dấu làm input của `GenerateGreeting`; nó không ảnh hưởng bytes của generated resource.
- `AuditTask` chỉ in log, không có `@OutputFile` hoặc `@CacheableTask`. Đây là **side-effect task** và có thể chạy mỗi khi được yêu cầu; đừng gắn fake output để ép `UP-TO-DATE`.
- `@ServiceReference("consoleAudit")` cho Gradle tự inject service và nhận biết task uses service.
- `maxParallelUsages=1` áp dụng cho tasks dùng cùng service; thứ tự auditOne/auditTwo **không được đảm bảo** nếu không có ordering rule riêng.

### 13.5. `src/main/java/demo/app/Main.java` — đầy đủ

~~~java
package demo.app;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws Exception {
        try (InputStream input = Main.class.getClassLoader()
                .getResourceAsStream("greeting.txt")) {

            if (input == null) {
                throw new IllegalStateException(
                    "Missing generated classpath resource greeting.txt"
                );
            }

            String message = new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
            ).stripTrailing();

            System.out.println(message);
        }
    }
}
~~~

Java 17 dùng JDK APIs có sẵn; không phụ thuộc external libraries. Khi Gradle `processResources` copy generated `greeting.txt` vào `build/resources/main`, Application plugin `run` sẽ thấy file qua runtimeClasspath.

### 13.6. Lần đầu chạy Java app

Tại project root:

~~~bash
./gradlew clean run --configuration-cache --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean run --configuration-cache --console=plain
~~~

**Stdout chính xác do `Main.main` in** (khi `DEMO_CHANNEL` chưa đặt và không có `-Precipient`):

~~~text
Hello, Gradle! [channel=development]
~~~

Gradle có thể in thêm task/status lines; đừng coi toàn bộ terminal chỉ có một dòng. Những task quan trọng:

~~~text
:generateGreeting   -> build/generated/greeting/greeting.txt
:processResources   -> build/resources/main/greeting.txt
:run                -> Java reads classpath resource
~~~

`generateGreeting` tạo output với content:

~~~text
Hello, Gradle! [channel=development]
~~~

`processResources` nhận output file qua `TaskProvider`, nên Gradle biết generator phải chạy khi resource cần được tạo.

Configuration Cache **lần đầu** có thể ghi `Configuration cache entry stored` khi build logic tương thích và entry chưa tồn tại. Đây là **dạng status kỳ vọng**, không phải chuỗi Java stdout.

### 13.7. Chạy lại không đổi

~~~bash
./gradlew run --configuration-cache --console=plain
~~~

Khi không có file/script/system thay đổi và requested task set phù hợp:

- Configuration Cache có thể được **reused**; với ValueSource đã query ở config phase, Gradle vẫn có thể gọi `obtain()` để kiểm tra normalized channel.
- `generateGreeting` thường `UP-TO-DATE`.
- `processResources` thường `UP-TO-DATE`.
- `run` thực thi Java application như lệnh yêu cầu; không cần nó `UP-TO-DATE` để chứng minh cache đã hoạt động.

**Không dùng `clean` giữa hai lần đo up-to-date** vì `clean` xóa outputs. Nếu cache bật sẵn ở môi trường, một task có thể `FROM-CACHE`; hãy phân biệt điều đó với local up-to-date.

### 13.8. Đổi `-Precipient`: Provider ảnh hưởng task input

~~~bash
./gradlew run -Precipient=Team --configuration-cache --console=plain
~~~

Stdout:

~~~text
Hello, Team! [channel=development]
~~~

`recipientProvider` là một **task input provider**. Khi `-Precipient` đổi, generator input fingerprint thay đổi; output phải cập nhật. Một Gradle phiên bản/cấu hình tương thích có thể reuse Configuration Cache vì provider được kết nối lazy với task, thay vì code gọi `recipientProvider.get()` để tính task graph lúc configuration.

Chạy lại đúng input:

~~~bash
./gradlew run -Precipient=Team --configuration-cache --console=plain
~~~

Generator thường `UP-TO-DATE`.

### 13.9. Đổi `DEMO_CHANNEL`: ValueSource config input

Linux/macOS Bash:

~~~bash
DEMO_CHANNEL=prod ./gradlew run -Precipient=Team \
    --configuration-cache --console=plain
~~~

PowerShell:

~~~powershell
$env:DEMO_CHANNEL = "prod"
.\gradlew.bat run -Precipient=Team --configuration-cache --console=plain
~~~

Stdout Java:

~~~text
Hello, Team! [channel=production]
~~~

Trong ví dụ, `DemoChannelSource.obtain()` trả `production`, khác `development` ở entry cũ. Vì `channelProvider.get()` đã được gọi **trong configuration phase**, Gradle phải tính lại configuration nếu config cache entry hiện tại ghi nhận giá trị cũ. Gradle không được reuse task graph mang `development` một cách mù quáng.

Giữ env `prod` và chạy lại: có thể reuse Configuration Cache.

Đổi env từ `prod` sang `production`: ValueSource **vẫn trả `production`**. Theo behavior được tài liệu hóa, raw env thay đổi nhưng returned value không đổi, nên Configuration Cache có thể tiếp tục reuse nếu những inputs khác không đổi.

### 13.10. Quay về development

Linux/macOS:

~~~bash
DEMO_CHANNEL=dev ./gradlew run -Precipient=Team \
    --configuration-cache --console=plain
~~~

PowerShell:

~~~powershell
$env:DEMO_CHANNEL = "dev"
.\gradlew.bat run -Precipient=Team --configuration-cache --console=plain
~~~

Stdout:

~~~text
Hello, Team! [channel=development]
~~~

Điều cần nhớ: `DEMO_CHANNEL` được đọc bên trong **ValueSource.obtain()`, không đọc trực tiếp từ task action. Task chỉ nhận `@Input channel`, nên output bytes vẫn có fingerprint đúng.

Sau bài tập PowerShell, nếu muốn xóa giá trị chỉ trong shell session:

~~~powershell
Remove-Item Env:\DEMO_CHANNEL
~~~

Lưu ý một số CLI/IDE/daemon environments có policies hoặc caches riêng; với bài tập, hãy dựa vào **giá trị được task in và Configuration Cache report** thay vì chỉ suy từ lệnh shell.

### 13.11. Chạy BuildService audit tasks

~~~bash
./gradlew auditBoth --configuration-cache \
    --parallel --max-workers=4 --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat auditBoth --configuration-cache --parallel --max-workers=4 --console=plain
~~~

Hai dòng stdout do `ConsoleAuditService.record()` in sẽ là:

~~~text
Audit service: one
Audit service: two
~~~

**Hai dòng trên là tập các nội dung kỳ vọng, không cam kết thứ tự.** Gradle scheduler có thể chọn task `auditTwo` trước `auditOne`. Trong cùng build instance, service được đăng ký một lần theo tên `consoleAudit`; Gradle giới hạn **một task sử dụng nó đồng thời** theo `maxParallelUsages.set(1)`.

Vì action chỉ `println` rất nhanh, log không đủ để đo concurrency limit trực quan. Muốn benchmark, thêm instrument/timing có kiểm soát vào riêng một môi trường test, không lấy thứ tự console làm bằng chứng của mutual exclusion.

Chạy lại `auditBoth`: audit tasks vẫn có thể thực thi vì **không có declared outputs** để up-to-date/cache. Configuration Cache vẫn có thể reuse task graph khi thích hợp. Điều đó **không phải cache failure**.

### 13.12. Chạy audit riêng không làm Java app chạy

~~~bash
./gradlew auditOne --console=plain
~~~

Chỉ task auditOne (và dependencies nếu có) được yêu cầu, không có `:run`, `:processResources` hay JavaCompile chỉ vì chúng cùng build. BuildService chỉ được tạo khi có task dùng service thực sự. **Service không phải một global listener tự động khiến mọi task chạy.**

## 14. Bài thử riêng: khi nào nên nối ValueSource lazily?

Trong ví dụ, ta viết:

~~~kotlin
val channelProvider = providers.of(DemoChannelSource::class) {}
val chosenChannel = channelProvider.get()

tasks.register<GenerateGreeting>("generateGreeting") {
    channel.set(chosenChannel)
}
~~~

Đó là **thiết kế cố ý để minh họa ValueSource dùng làm Configuration Cache input**. Nhưng nếu channel không ảnh hưởng việc chọn plugin/task/repository mà chỉ ảnh hưởng bytes output của generator, có thể đơn giản hóa:

~~~kotlin
val channelProvider = providers.of(DemoChannelSource::class) {}

tasks.register<GenerateGreeting>("generateGreeting") {
    channel.set(channelProvider)
}
~~~

**Đây là phương án thay thế fragment tương ứng** trong demo, không được paste thêm một registration trùng tên bên cạnh registration cũ. Với variant này, Gradle có thể giữ Configuration Cache reusable khi normalized channel đổi, vì task sẽ resolve input provider lúc cần và task fingerprint vẫn phát hiện value mới. Trên những Gradle versions cụ thể, provider chains có thể được compute/serialize theo policy; hãy kiểm chứng bằng `--configuration-cache` logs chứ không khẳng định mọi biến thể đều tuyệt đối lazy.

### Quy tắc chọn

- Cần value để **quyết định build configuration**: dùng ValueSource và query ở configuration time có chủ đích; chấp nhận cache invalidation khi returned value đổi.
- Chỉ cần value làm **task input**: nối Provider trực tiếp tới task property, không `get()` sớm.
- Nguồn chỉ một env/project property: ưu tiên built-in provider, không custom ValueSource.
- Nguồn là **shared resource** như DB/network client: dùng BuildService, không biến client object thành Provider<String> hoặc một ValueSource result.

## 15. BuildService không phải một `@Input`

Trong demo:

~~~kotlin
@get:ServiceReference("consoleAudit")
abstract val auditService: Property<ConsoleAuditService>
~~~

Task action gọi service để **in log**. Không thể coi `ConsoleAuditService` là một immutable value có thể fingerprint. Gradle docs nêu task properties chứa service phải dùng `@ServiceReference` hoặc `@Internal`, không dùng `@Input`.

Nếu một task tạo output phụ thuộc vào remote database data lấy qua service, output **không deterministic từ client identity**. Bạn cần mô hình hóa **data version/snapshot/hash** của response thành input, hoặc thiết kế task không cacheable và không dựa vào stale up-to-date outputs.

Ví dụ chống mẫu:

~~~kotlin
// Mảnh anti-pattern:
// @get:Input
// abstract val databaseClient: Property<MyDatabaseService>
~~~

Không dùng `@Input` cho service object. Một connection không thể là cache key phản ánh nội dung DB.

### Đừng dùng shared mutable counter để tạo file cacheable

Nếu một service tăng counter mỗi lần task chạy, file output chứa counter sẽ tùy scheduling và service lifetime. `@CacheableTask` không thể biến counter đó thành deterministic input. Khi build rerun hoặc cache restore, service có thể bị recreate với counter reset.

Chỉ dùng service state làm output khi đã thiết kế một **deterministic, reproducible mapping từ declared inputs** hoặc intentionally disable caching/up-to-date cho side-effect task tương ứng. In log audit trong demo không gây lỗi dữ liệu đầu ra Java.

## 16. `maxParallelUsages` không phải `dependsOn` và không phải distributed lock

Giả sử ba tasks A/B/C cùng dùng một server chỉ cho phép tối đa hai sessions:

~~~kotlin
val service = gradle.sharedServices.registerIfAbsent(
    "limitedClient",
    LimitedClientService::class
) {
    maxParallelUsages.set(2)
}
~~~

Đây là **mảnh cấu hình**, chưa có class `LimitedClientService`, cho thấy cơ chế scheduler: tối đa hai tasks **đã khai báo sử dụng** `limitedClient` cùng lúc.

Ba hiểu lầm:

1. **Task dependency:** A/B/C không tự phụ thuộc nhau. Giới hạn concurrency không tạo quan hệ đầu ra/đầu vào; nếu B cần A tạo file, vẫn phải có `Provider`/`dependsOn`.
2. **Global quota:** ba Gradle invocations/CI jobs khác nhau có thể mỗi invocation đăng ký service riêng. Nếu external API chỉ cho phép hai clients trên toàn cluster, cần quota/lease/lock bên ngoài Gradle.
3. **Thread safety:** một task duy nhất có thể dùng Worker API/multiple threads. Service implementation vẫn phải xử lý shared mutable state an toàn; limit task count không chứng minh từng method thread-safe.

Đừng dùng `maxParallelUsages=1` làm workaround vĩnh viễn cho overlapping task outputs. Đúng hơn là tách output ownership và producer/consumer graph; service quota dùng cho **external resource concurrency**.

## 17. BuildService Parameters và cleanup

Một service thực tế có cấu hình managed:

~~~kotlin
abstract class ApiClientService :
    BuildService<ApiClientService.Parameters>,
    AutoCloseable {

    interface Parameters : BuildServiceParameters {
        val endpoint: Property<String>
    }

    fun endpoint(): String = parameters.endpoint.get()

    override fun close() {
        // Close HTTP connection pool / server handle if created.
    }
}

val client = gradle.sharedServices.registerIfAbsent(
    "apiClient",
    ApiClientService::class
) {
    parameters.endpoint.set(
        providers.gradleProperty("apiEndpoint")
            .orElse("https://example.invalid")
    )
    maxParallelUsages.set(2)
}
~~~

**Đây là mảnh cấu hình service**, chưa có task dùng nó và URL `example.invalid` chỉ là ví dụ không trỏ đến API hoạt động. Nó minh họa:

- Parameters là managed interface extending `BuildServiceParameters`.
- Provider có thể nối vào parameter để tránh đọc property quá sớm.
- Service có `AutoCloseable` cho cleanup.
- Task consumers cần `@ServiceReference` hoặc `@Internal + usesService` như phần 12.
- Endpoint/config parameters được lưu trong Configuration Cache; **không đưa secret token plaintext vào parameters/console** nếu không kiểm soát bảo mật dữ liệu cache và Gradle logs.

Khi dùng HTTP client thật, thường cần initialize lazily khi first request, và `close()` giải phóng connection pool. Không mở network socket ngay trong configuration phase bằng `client.get()` khi không cần.

### Vòng đời trên Configuration Cache hit

Gradle serializes service **parameters**, không phải các live client sockets. Trên cache hit, provider/registration có thể được khôi phục, **service instance được tạo mới khi cần**. Đây là lý do không dùng BuildService như object để lưu “số lần build trước”.

## 18. Task dùng `@Internal`: đừng quên `usesService`

Nếu không dùng `@ServiceReference`, một custom task có thể được nối tường minh.

Mảnh dựa trên `ConsoleAuditService` của demo:

~~~kotlin
abstract class ExplicitAuditTask : DefaultTask() {

    @get:Input
    abstract val label: Property<String>

    @get:Internal
    abstract val auditService: Property<ConsoleAuditService>

    @TaskAction
    fun audit() {
        auditService.get().record(label.get())
    }
}

val serviceProvider = gradle.sharedServices.registerIfAbsent(
    "explicitAudit",
    ConsoleAuditService::class
) {
    maxParallelUsages.set(1)
}

tasks.register<ExplicitAuditTask>("explicitAuditOne") {
    label.set("explicit")
    auditService.set(serviceProvider)
    usesService(serviceProvider)
}
~~~

Đây là **mảnh bổ sung**, cần import `org.gradle.api.tasks.Internal` và class `ConsoleAuditService` sẵn có. Không đặt trùng tên task với demo. Với `@Internal`, `usesService(serviceProvider)` bắt buộc để Gradle biết task dùng service và áp dụng concurrency limit.

**Đừng đánh dấu auditService `@Input`** chỉ để validation hết warning. Service reference không đại diện input data.

## 19. ValueSource và BuildService không được dùng để vòng vo vượt cache tracking

Một vấn đề tinh tế: theo tài liệu Configuration Cache hiện tại, không nên đưa `Provider<BuildService>` hoặc provider dẫn xuất của nó vào một `ValueSourceParameters` rồi **query ValueSource đó ở configuration time** và giả định Gradle tự fingerprint service state.

Ví dụ chống mẫu:

~~~kotlin
// Chỉ minh họa tình huống giới hạn API;
// không phải runnable file, các class thuộc project thật.
val client = gradle.sharedServices.registerIfAbsent(
    "client",
    MyClientService::class
) {}

val source = providers.of(MyValueSource::class) {
    parameters {
        input.set(client.map { it.liveValue() })
    }
}

// value.get() ở configuration có thể không được
// Configuration Cache hỗ trợ theo cách mong đợi.
~~~

**Không lấy BuildService instance làm nguồn quyết định Configuration Cache invalidation**. Service tồn tại theo vòng đời task invocation, không phải một tracked external state fingerprint. Nếu cần quyết định cấu hình theo API version, hãy dùng ValueSource trực tiếp đọc **một giá trị bất biến/định nghĩa được** (và chấp nhận chi phí query), hoặc built-in providers/Gradle properties.

Gradle có workaround cụ thể khi kết hợp service/ValueSource providers, nhưng nó có giới hạn về transient values; chỉ sử dụng khi đã đọc docs và kiểm thử cả cache miss/hit. Không dùng workaround như policy chung cho mọi build.

Nguồn: [Configuration Cache Requirements — Build Services](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html), [Configuration Cache Status](https://docs.gradle.org/current/userguide/configuration_cache_status.html).

## 20. Provider và dữ liệu bí mật: tránh eager capture

Credential là trường hợp cần tách **giá trị dùng khi task chạy** khỏi **configuration của toàn build**.

Không nên:

~~~kotlin
// Chống mẫu:
val password = System.getenv("REPO_PASSWORD")
println("Password: " + password)
~~~

Đây là lỗi bảo mật độc lập với cache; log/Git/CI console không phải nơi lưu secrets.

Ưu tiên typed providers:

~~~kotlin
val repoPassword =
    providers.environmentVariable("REPO_PASSWORD")
~~~

và nối vào task/plugin credentials APIs được thiết kế cho secret management. Đừng `get()` sớm hoặc giữ secrets trong String fields/closures của task nếu không bắt buộc.

**Configuration Cache có thể serialize task state**, bao gồm những values reachable từ scheduled task. Gradle mã hóa dữ liệu cache trên disk, nhưng không nên coi cache encryption là lý do để đưa secrets vào log hoặc chia sẻ cả cache directory/key. Build Cache cũng có thể lưu output file chứa secret nếu task tạo sai artifact và bật caching.

Với tasks upload/publish/deploy, thường không coi operation đó là cacheable output task; secret dùng để authenticate không đồng nghĩa mọi bytes được tạo ra đều phụ thuộc mật khẩu. Tách **auth context** và **deterministic artifact contents**.

## 21. Không nên dùng `providers.provider { ... }` để lách Input Tracking

Gradle cung cấp:

~~~kotlin
val x = providers.provider {
    "value"
}
~~~

Đây là một generic provider factory. Tuy tiện, các lazy closures có thể **capture Project/Script object**, đọc dữ liệu ngoài Gradle chưa được track hoặc bị Configuration Cache không serialize được.

Chống mẫu:

~~~kotlin
val configValue = providers.provider {
    project.file("config/env.txt").readText()
}
~~~

Vấn đề: closure gắn với `project`/buildscript state; nếu được đưa vào cached task graph, Gradle có thể báo unsupported references, hoặc input reading semantics không đúng.

Đúng hơn với file text:

~~~kotlin
val configText = providers.fileContents(
    layout.projectDirectory.file("config/env.txt")
).asText
~~~

và nối `configText` vào `@Input Property<String>` hoặc sử dụng nó trong ValueSource nếu cần parse phức tạp ảnh hưởng configuration.

**Generic provider { } không sai hoàn toàn**, nhưng ưu tiên built-in sources và managed properties trước. Khi dùng closure custom, chỉ capture immutable/serializable state phù hợp và hiểu nó được tính/fingerprint thế nào.

## 22. Lỗi điển hình: Project API trong task action

Chống mẫu:

~~~kotlin
tasks.register("badTask") {
    doLast {
        val value = project.findProperty("recipient")
        val file = project.file("build/result.txt")
        file.writeText(value.toString())
    }
}
~~~

Đoạn này có thể vi phạm Configuration Cache vì task action truy cập `Project` model (và không khai báo inputs/outputs đúng), gây lỗi tương thích hoặc task output không được track.

Sửa theo hướng task class:

~~~kotlin
abstract class GoodTask : DefaultTask() {
    @get:Input
    abstract val recipient: Property<String>

    @get:OutputFile
    abstract val destination: RegularFileProperty

    @TaskAction
    fun write() {
        val file = destination.get().asFile
        file.parentFile.mkdirs()
        file.writeText(recipient.get(), Charsets.UTF_8)
    }
}

tasks.register<GoodTask>("goodTask") {
    recipient.set(
        providers.gradleProperty("recipient").orElse("Gradle")
    )
    destination.set(
        layout.buildDirectory.file("results/recipient.txt")
    )
}
~~~

**Đây là mảnh** cần imports `Property`/`RegularFileProperty`/annotations, đã được minh họa đầy đủ trong demo. Task action chỉ đọc task properties và ghi declared output; thuận với Configuration Cache/Build Cache hơn code đọc `project` trong action.

## 23. “ValueSource chạy mỗi build” có thể gây chậm như thế nào?

Khi `ValueSource` được query trong configuration:

~~~text
Build 1:
  ValueSource.obtain() -> v1
  configure graph
  store entry with v1

Build 2:
  ValueSource.obtain() -> v1
  reuse graph
  execute tasks

Build 3:
  ValueSource.obtain() -> v2
  invalidate entry
  configure graph
  store entry with v2
~~~

Nếu `obtain()` gọi `git rev-parse HEAD` nhanh, chi phí thường chấp nhận được khi thật sự cần commit ID để quyết định version/task set. Nếu gọi một API chậm trong vài giây thì **mỗi build** vẫn có network overhead để check cache entry — đúng là dùng Configuration Cache nhưng không đạt hiệu quả mong muốn.

Tốt hơn khi:

- Chuyển external data thành **CI/Gradle property** và wire Provider.
- Cố định input bằng commit ID/file hash đã biết.
- Làm network operation trong một task có input/output contract rõ.
- Dùng BuildService cho client reuse ở execution time khi nhiều tasks cùng gọi API.
- Chỉ query ValueSource trong configuration khi thật sự cần value để cấu hình.

Đừng che network failure bằng cách ValueSource âm thầm trả default làm release version sai. Với release logic, source value phải được validate/fail rõ khi không thể xác định version.

## 24. BuildService và Build Events Listener

Một số legacy build logic đăng ký callback kiểu:

~~~kotlin
gradle.taskGraph.whenReady {
    // ...
}
~~~

hoặc `BuildListener`/`TaskExecutionListener`, kỳ vọng chúng chạy ở mọi Gradle invocation. **Configuration Cache hit có thể bỏ qua configuration phase**, nên callbacks đăng ký lúc configuration không được gọi lại theo cách bạn mong đợi; nhiều listener APIs cũng không tương thích Configuration Cache.

Cách chính thức để nghe task completion khi bật Configuration Cache là:

1. Build Service implementation implements `OperationCompletionListener`.
2. Đăng ký nó bằng `gradle.sharedServices.registerIfAbsent(...)`.
3. Gọi `BuildEventsListenerRegistry.onTaskCompletion(serviceProvider)` từ plugin có injected registry.
4. Xử lý `TaskFinishEvent`, không gọi `Project` model từ callback sai lifecycle.

Đây là **kiến trúc mở rộng**, không nằm trong demo nhỏ và cần một plugin/project build class để inject `BuildEventsListenerRegistry`. Nó thích hợp cho metrics/loggers/CI reports khi cần quan sát execution events, **không thay thế task dependencies hoặc producer output wiring**.

Nguồn: [Gradle Shared Build Services](https://docs.gradle.org/current/userguide/build_services.html), [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html).

## 25. Provider-backed task outputs và implicit dependency

Giả sử một task tạo manifest:

~~~kotlin
abstract class GenerateManifest : DefaultTask() {
    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val out = outputFile.get().asFile
        out.parentFile.mkdirs()
        out.writeText("manifest\n")
    }
}

val manifestTask = tasks.register<GenerateManifest>(
    "generateManifest"
) {
    outputFile.set(
        layout.buildDirectory.file("generated/manifest.txt")
    )
}

tasks.register<Copy>("packageManifest") {
    from(manifestTask.flatMap { it.outputFile })
    into(layout.buildDirectory.dir("package"))
}
~~~

Đây là **mảnh task wiring** cần imports, nhưng đủ logic minh họa: `manifestTask.flatMap { it.outputFile }` giữ Provider và task provenance. Gradle có thể tự đưa `generateManifest` vào task graph khi `packageManifest` cần input.

Một đường dẫn raw tương đương text:

~~~kotlin
from(file("build/generated/manifest.txt"))
~~~

không chứa task dependency metadata. Nếu `packageManifest` không khai báo phụ thuộc producer, Gradle có thể báo implicit dependency validation problem hoặc lấy file cũ. Dùng Provider thay vì hard-coded file path.

**Provider không tự tạo task dependency khi nguồn Provider chỉ là một constant path vô danh.** Chỉ những providers/task outputs có provenance phù hợp mới giúp Gradle suy ra producer. Đây là giới hạn quan trọng; “dùng Provider là tự động dependsOn” cũng là một phát biểu sai.

## 26. Cấu hình inputs/outputs để Build Cache đúng

Một custom task cần:

~~~kotlin
@CacheableTask
abstract class DeterministicTask : DefaultTask() {
    @get:Input
    abstract val options: Property<String>

    @get:OutputFile
    abstract val destination: RegularFileProperty

    @TaskAction
    fun generate() {
        val file = destination.get().asFile
        file.parentFile.mkdirs()
        file.writeText(options.get(), Charsets.UTF_8)
    }
}
~~~

Đoạn là **mảnh class** cần imports và task registration. `@CacheableTask` là **cam kết** rằng output phụ thuộc đầy đủ declared inputs và implementation.

Nếu action đọc:
- System time.
- Random number.
- Network response.
- Environment variable không khai báo.
- Mutable BuildService counter.
- File bên ngoài task inputs.
- Hostname/JDK/locale ảnh hưởng output nhưng không mô hình hóa.

thì task có thể trả sai `UP-TO-DATE` hoặc `FROM-CACHE`. Sửa bằng cách declare nguồn dưới dạng task input (nếu nguồn ổn định) hoặc không cache task nếu về bản chất là side effect.

**Không đánh đồng:** ValueSource có thể fingerprint **cấu hình**, nhưng nếu task output sử dụng một data source khác mà không có `@Input`, Build Cache vẫn sai. Một ValueSource được query khi configuration **không thay thế** task input declarations.

## 27. Cách kiểm tra từng loại cache

### 27.1. Configuration Cache

~~~bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

Với một build tương thích, lần đầu có thể `Configuration cache entry stored`, lần hai `Reusing configuration cache` nếu inputs không đổi. Nếu một ValueSource được query ở configuration của task set đó, nó có thể được gọi để xác minh source value.

### 27.2. Up-to-date checks

~~~bash
./gradlew generateGreeting --no-build-cache --console=plain
./gradlew generateGreeting --no-build-cache --console=plain
~~~

Với cùng `recipient`/channel và output còn nguyên, generator thường `UP-TO-DATE`. `--no-build-cache` tách kiểm tra local reuse khỏi Build Cache restore.

### 27.3. Build Cache

~~~bash
./gradlew generateGreeting --build-cache --console=plain
~~~

Task có `@CacheableTask` có thể ghi/đọc Build Cache nếu caching policy cho phép. **Không khẳng định một invocation chắc chắn hiện `FROM-CACHE`**: nếu local output đã up-to-date, Gradle không cần restore; nếu chưa có entry, task sẽ execute và tạo cache entry khi phù hợp.

### 27.4. BuildService

~~~bash
./gradlew auditBoth --parallel --max-workers=4 \
    --configuration-cache --console=plain
~~~

Service có thể được Gradle khởi tạo và dùng bởi các task audit, nhưng không có persistent file output. Việc audit tasks chạy lại là **expected side effect behavior**, không phải Build Cache miss cần sửa.

### 27.5. Chẩn đoán

~~~bash
./gradlew run --configuration-cache --info --console=plain
~~~

Kiểm tra lý do Configuration Cache invalidation và task up-to-date/caching decisions. Chia sẻ logs cần lọc secrets; không bật verbose/debug để lộ token hoặc internal URLs.

## 28. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Task input đổi nhưng Configuration Cache bị invalidated toàn build | `get()` ở configuration time | Wire Provider vào task property nếu config không cần value |
| Env đổi mà task output không đổi | Task thiếu `@Input` hoặc đã capture constant sai | Nối env Provider/ValueSource vào declared task input |
| `ValueSource.obtain()` chạy mọi invocation | ValueSource queried at configuration, Gradle cần kiểm tra cache fingerprint | Giữ obtain() nhanh; chỉ query khi config thực sự cần |
| Config cache reuse dù raw env đổi | Normalized ValueSource result không đổi | Đúng khi config behavior chỉ phụ thuộc normalized result |
| Config cache reuse nhưng business result sai | ValueSource returned value không phản ánh hidden input | Sửa normalization/tracking contract |
| Build Cache trả output sai | Task cacheable dùng input không khai báo | Declare mọi input/determinism hoặc tắt caching |
| Task luôn executed | Không có declared outputs/side-effect task | Nếu tạo file, thêm `@OutputFile`; nếu chỉ audit, bình thường |
| `Provider.get()` fails for absent value | Không có property/env và không có fallback | Dùng `orElse`, validate required input hoặc `orNull` đúng chỗ |
| Raw `project.file(...)` trong task action gây CC problem | Task action truy cập Project model | Dùng typed properties và injected services |
| File consumer thiếu producer dependency | Dùng raw output path | `TaskProvider.flatMap { it.outputFile }` |
| BuildService counter resets giữa builds | Service instance có lifecycle per build | Không dùng làm persistent cache; lưu state qua external store nếu cần |
| `maxParallelUsages=1` không ngăn hai CI jobs | Limit chỉ áp dụng trong Gradle build | Lock/lease quota ở external system |
| `maxParallelUsages` không hoạt động với `@Internal` property | Quên `usesService(provider)` | Gọi `usesService` và set service Provider |
| `@ServiceReference` không được inject | Service name/type mismatch | So registry name, annotation name, service class |
| Nhiều services cùng type gây ambiguity | Annotation không ghi service name | Chỉ định tên hoặc nối provider tường minh |
| `BuildService` bị tạo hai lần khi CC | Lấy service trong config phase và lifecycle CC recreate | Tránh `get()` tại config, không dựa instance identity |
| `@Input` trên service property không supported | Service object không là task input | Dùng `@ServiceReference` hoặc `@Internal` |
| Plugin metrics listener không hoạt động trên cache hit | Callback đăng ký ở configuration không chạy lại | `BuildEventsListenerRegistry.onTaskCompletion` + service |
| ValueSource phụ thuộc BuildService tại config time | Một giới hạn CC được Gradle tài liệu hóa | Tách external source khỏi service hoặc xem workaround có giới hạn |
| Build chậm do provider/ValueSource gọi network | Eager query hoặc expensive `obtain()` | Chuyển network work vào task, cache data có chủ đích |
| `providers.fileContents(...).asText` lỗi missing file | File thực sự không tồn tại | Tạo file, dùng conditional provider đúng semantics |
| Input file path thay đổi và cache misses | Normalization/path sensitivity không phù hợp | Dùng `@InputFile` + `@PathSensitive` đúng |
| Gradle task output chồng lấn | Nhiều tasks ghi cùng directory | Tách output roots, aggregation task |
| Service connection không đóng | Không implement `AutoCloseable` hoặc lifecycle ngoài Gradle | Thiết kế close/release rõ |
| Plugin classloader/provider không serialize | Captured Project/Gradle/Script in task closure | Dùng isolated task type/managed properties |

## 29. Quy trình đưa một thay đổi vào build logic

1. **Xác định dữ liệu**: là một giá trị, một external source hay một stateful shared resource?
2. **Chọn API thấp nhất đủ dùng**: built-in Provider trước, custom ValueSource khi cần, BuildService chỉ khi thật sự chia sẻ state/resource.
3. **Xác định lifecycle**: giá trị cần lúc configuration hay execution?
4. **Giữ task inputs typed**: `Property<T>`/`RegularFileProperty` và annotations.
5. **Giữ output provenance**: task output Provider đưa vào task consumer.
6. **Chỉ dùng `@CacheableTask` khi deterministic**; không cache deployment/audit side effects.
7. **Tạo service bằng `registerIfAbsent`**, không `new` thủ công rồi giữ global singleton.
8. **Kết nối service đúng**: `@ServiceReference` hoặc `@Internal + usesService`.
9. **Giới hạn concurrency khi resource yêu cầu**, không dùng service để che overlapping file outputs.
10. **Không dùng service instance làm persisted state**; biết rằng CC có thể recreate instance.
11. **Chạy clean/no-change/changed-input tests**.
12. **Chạy `--configuration-cache` hai lần**, quan sát reuse và errors.
13. **Thay external state đã normalization**, kiểm tra invalidation có đúng không.
14. **Chạy audit/tasks với concurrency**, xác minh quyền truy cập shared resource.
15. **Thử Build Cache ở workspace sạch** khi task thực sự cacheable.
16. **Ghi tests bằng Gradle TestKit** cho regression nếu logic nằm trong custom Gradle plugin.

## 30. Bài tập thực hành

### Bài A — Provider với fallback

Tại demo, dùng:

~~~bash
./gradlew run -Precipient=Alice --configuration-cache
~~~

Kỳ vọng Java stdout khi không có `DEMO_CHANNEL`:

~~~text
Hello, Alice! [channel=development]
~~~

Thử bỏ `-Precipient` rồi chạy lại. Giải thích tại sao fallback `orElse("Gradle")` được dùng và vì sao generator cần declared `@Input recipient`.

### Bài B — ValueSource normalization

Thử ba môi trường:

~~~bash
DEMO_CHANNEL=dev ./gradlew run --configuration-cache
DEMO_CHANNEL=prod ./gradlew run --configuration-cache
DEMO_CHANNEL=production ./gradlew run --configuration-cache
~~~

Mô tả cache entry có thể reuse/invalidate dựa trên **normalized return value**, không chỉ raw env. So sánh behavior của `providers.environmentVariable("DEMO_CHANNEL")` dùng trực tiếp ở configuration time (raw value được track khác).

### Bài C — Eager vs lazy

Chuyển:

~~~kotlin
val chosenChannel = channelProvider.get()
channel.set(chosenChannel)
~~~

thành:

~~~kotlin
channel.set(channelProvider)
~~~

trong đúng task registration. Chạy lại hai lần có `--configuration-cache`. Nêu lý do khi value chỉ là task input, cấu hình không cần biết nó để tạo task graph. Không paste hai dòng vào hai chỗ để tạo duplicate task registration.

### Bài D — BuildService dùng sai

Bỏ `usesService(provider)` ở một `@Internal`-based service consumer; giải thích vì sao scheduler không thể đảm bảo quota. Giữ `@ServiceReference`-based task của demo không cần explicit `usesService`.

### Bài E — Build Cache khác Configuration Cache

Chạy:

~~~bash
./gradlew clean run --configuration-cache --build-cache
./gradlew run --configuration-cache --build-cache
~~~

Đọc riêng **Configuration Cache entry status** và **GenerateGreeting task outcome**. Vì sao Configuration Cache hit không đồng nghĩa `:run` up-to-date? Vì sao cacheable generator có thể `UP-TO-DATE` mà không `FROM-CACHE`?

## 31. Câu hỏi tự kiểm tra

**Câu 1.** Provider khác Property thế nào?

**Đáp:** `Provider<T>` là giá trị chỉ đọc có thể truy vấn; `Property<T>` kế thừa Provider và cho phép set/convention một value hoặc provider.

**Câu 2.** Khi nào `map`, khi nào `flatMap`?

**Đáp:** `map` khi function trả giá trị; `flatMap` khi function trả Provider để không tạo nested Provider và giữ dependency chain.

**Câu 3.** `providers.gradleProperty("x")` có cần custom ValueSource không?

**Đáp:** Không. Đây là built-in Provider; dùng trực tiếp trừ khi có computation external phức tạp.

**Câu 4.** Một ValueSource đọc `System.getenv` trong `obtain()` và được query khi configuration. Cái gì được theo dõi cho Config Cache?

**Đáp:** **Returned value** của ValueSource, không nhất thiết từng raw getenv call bên trong.

**Câu 5.** Tại sao ValueSource.obtain() cần nhanh?

**Đáp:** Khi ValueSource là config input, Gradle có thể gọi lại mỗi build để xác minh entry; operation chậm làm cache hit vẫn chậm.

**Câu 6.** BuildService có sống qua hai invocation `./gradlew` không?

**Đáp:** Không nên giả định. Service scoped theo Gradle build và instance được tạo/recreated theo lifecycle, kể cả khi Configuration Cache được reuse.

**Câu 7.** `maxParallelUsages=1` có tương đương một distributed mutex không?

**Đáp:** Không. Nó giới hạn tasks trong scheduler đã đăng ký dùng service, không khóa nhiều CI jobs/invocations.

**Câu 8.** Vì sao `@ServiceReference("consoleAudit")` có lợi?

**Đáp:** Gradle tự kết nối service theo tên/type, biết task dùng nó và áp dụng concurrency cap mà không cần set provider/`usesService` thủ công.

**Câu 9.** Task có `@Internal Property<BuildService>` cần gì nữa?

**Đáp:** Set service provider vào property và `usesService(serviceProvider)` để Gradle áp dụng usage/concurrency.

**Câu 10.** Nếu BuildService counter quyết định nội dung output, task cacheable có an toàn không?

**Đáp:** Không, nếu counter không được mô hình hóa thành deterministic input; cache/up-to-date có thể sai.

**Câu 11.** Tại sao provider của task output giúp suy ra task dependency?

**Đáp:** Task output Provider có provenance: Gradle biết producer task; raw string path thì không.

**Câu 12.** Có thể đọc Provider.get() khi configuration không?

**Đáp:** Có khi configuration quyết định task graph/plugin/repository và cần giá trị; cần chấp nhận config input và dùng Gradle-managed source API. Không gọi get sớm khi chỉ task action cần giá trị.

**Câu 13.** Configuration Cache hit có bảo đảm `GenerateGreeting` FROM-CACHE không?

**Đáp:** Không. Cache config và cache outputs khác nhau. Generator có thể UP-TO-DATE/FROM-CACHE/EXECUTED tùy inputs/outputs/caching.

**Câu 14.** Có nên đưa password vào `@Input` cho mọi remote publishing task?

**Đáp:** Không máy móc. Secret management, task output semantics và khả năng lưu thông tin nhạy cảm trong Configuration/Build Cache phải được xem xét riêng.

**Câu 15.** ValueSource và BuildService loại nào phù hợp kiểm tra một Git commit hash phục vụ configuration?

**Đáp:** ValueSource hoặc built-in provider for process output. BuildService dành cho resource/client shared giữa tasks, không phải fingerprint configuration từ một long-lived instance.

**Câu 16.** Vì sao audit tasks trong demo vẫn chạy khi Configuration Cache reused?

**Đáp:** Vì audit là side effect console không có persistent output contract để up-to-date/cache, còn Configuration Cache chỉ tránh cấu hình lại build.

## 32. Checklist trước khi đưa lên CI

- [ ] Đã phân biệt Provider/Property, ValueSource và BuildService theo trách nhiệm.
- [ ] Không dùng ValueSource cho một Gradle property đơn giản đã có built-in provider.
- [ ] Không `get()` sớm với provider chỉ phục vụ task input.
- [ ] Provider transformations dùng `map`/`flatMap`/`zip`/`orElse` đúng semantics.
- [ ] Task outputs được nối bằng Provider có producer provenance.
- [ ] Task khai báo `@Input`/`@OutputFile`/`@OutputDirectory` đủ.
- [ ] ValueSource trả immutable/serializable value và không có side effects.
- [ ] ValueSource queried at configuration được giữ nhanh, cho phép CC recomputation.
- [ ] ValueSource returned value phản ánh đúng external state ảnh hưởng build configuration.
- [ ] Không lấy BuildService instance làm config fingerprint hoặc persisted cache.
- [ ] Service parameters được truyền qua managed properties, không bằng global mutable singleton.
- [ ] Task dùng `@ServiceReference` hoặc `@Internal + usesService` đúng.
- [ ] `maxParallelUsages` được set theo resource quota và có tests.
- [ ] Không coi service quota là distributed lock hoặc dependency graph.
- [ ] Shared service instance có cleanup khi cần, không giữ socket sau build.
- [ ] Không dùng shared counter/network response ẩn để quyết định cacheable output.
- [ ] Không để credentials/secrets rò rỉ qua logs, outputs hoặc cache.
- [ ] Không chạm Project/Gradle model trong task action trái CC requirements.
- [ ] Configuration Cache được test trên cả miss/hit và khi external values thay đổi.
- [ ] Build Cache/up-to-date được test độc lập với Configuration Cache.
- [ ] Không dựa vào thứ tự audit logs để suy ra task ordering.
- [ ] Custom Gradle plugins/tasks có TestKit regression tests.
- [ ] Dùng Gradle Wrapper và JDK/toolchain phù hợp project, tránh “works only on my machine”.

## 33. Tài liệu Gradle chính thức

- [Gradle — Configuring Tasks Lazily](https://docs.gradle.org/current/userguide/lazy_configuration.html): Provider/Property, `map`/`flatMap`, lazy task outputs và inferred task dependencies.
- [Gradle — Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): chaining providers, managed properties, fallback.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): cấu hình được cache, build lifecycle, serialization, security, khác Build Cache.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): ValueSource, environment/files/process values, BuildService caveats, Project/Gradle references không an toàn trong task actions.
- [Gradle — Debugging Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_debugging.html): invalidation reasons và cách chuyển eager env access thành lazy provider.
- [Gradle — Using Shared Build Services](https://docs.gradle.org/current/userguide/build_services.html): `BuildService`, `ServiceReference`, `Internal` + `usesService`, `maxParallelUsages`, `AutoCloseable` và lifecycle.
- [Gradle — ValueSource API](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.provider/-value-source/index.html): generic parameters, `obtain()` và config-cache input semantics.
- [Gradle — Provider API](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/Provider.html): deferred value, transformations, Configuration Cache representation.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): `@Input`/`@OutputFile`, local up-to-date và tracking.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task output caching và `@CacheableTask`.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): task input/output ownership và lazy design.
- [Gradle — TestKit](https://docs.gradle.org/current/userguide/test_kit.html): functional tests cho custom Gradle plugins/tasks.
