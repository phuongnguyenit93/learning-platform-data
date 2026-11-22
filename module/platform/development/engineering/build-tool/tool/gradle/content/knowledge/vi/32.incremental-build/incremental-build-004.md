# Đầu ra chồng lấn, tác vụ không khai báo và nguyên nhân mất tính tăng dần trong Gradle

Một Gradle build nhanh không chỉ nhờ CPU mạnh hoặc `--parallel`; yếu tố cốt lõi là Gradle **biết chính xác công việc nào phụ thuộc vào những dữ liệu nào và task nào sở hữu những output nào**. Nếu một task có thể chứng minh inputs, implementation và outputs không thay đổi, Gradle thường có thể bỏ qua thao tác lặp lại (`UP-TO-DATE`). Nếu task đã opt-in và đủ điều kiện build cache, Gradle còn có thể phục hồi outputs từ cache (`FROM-CACHE`), thay vì chạy action.

Tính tăng dần bị phá vỡ khi task ghi vào thư mục do task khác sở hữu, quên khai báo file/giá trị ảnh hưởng tới output, đọc output của producer bằng đường dẫn thô, thực thi side effect ngoài danh sách outputs, hoặc dùng dữ liệu không ổn định như giờ hiện tại/network mà không mô hình hóa. Hậu quả có hai hướng tưởng như đối nghịch: **chạy lại quá nhiều** (build chậm, cache misses) hoặc **không chạy lại khi cần** (kết quả cũ và build sai).

Bài thuộc phần **Build tăng dần** của *Build Tool Gradle* và tập trung đúng chủ đề **“Đầu ra chồng lấn, tác vụ không khai báo và nguyên nhân mất tính tăng dần”**. Bạn sẽ tìm hiểu Gradle snapshots và task ownership, input/output annotations, overlapping outputs, implicit task dependencies, validation, một ví dụ **Gradle Kotlin DSL + Java 17 chạy được**, cách tái hiện `UP-TO-DATE` và sửa lỗi, sự khác biệt giữa incremental execution và Build Cache, cùng quy trình chẩn đoán CI.

## 1. “Build tăng dần” có ba cơ chế cần phân biệt

| Khái niệm | Điều Gradle làm | Dấu hiệu thường thấy | Điều kiện chính |
| --- | --- | --- | --- |
| **Up-to-date checks** | Bỏ qua chạy actions của task vì inputs/outputs không đổi so với lần thực thi thành công | `UP-TO-DATE` | Task có outputs được khai báo; trạng thái inputs/outputs phù hợp |
| **Build Cache** | Khôi phục output đã lưu từ lần thực thi khác có cache key tương đương | `FROM-CACHE` | Cache bật; task cacheable; inputs/implementation/output contract phù hợp |
| **Incremental task action** | Task action vẫn chạy nhưng chỉ xử lý các file thay đổi | Thường `EXECUTED`; log tùy task | Task hỗ trợ `InputChanges`/incremental input API |

**Quan trọng:** up-to-date check không đồng nghĩa Build Cache, và một task `EXECUTED` vẫn có thể thực hiện **incremental processing bên trong**. Ngược lại, Gradle có thể chạy `JavaCompile` nhưng compiler chỉ compile các classes bị ảnh hưởng.

Một số status thường thấy:

- `UP-TO-DATE`: task action được bỏ qua, outputs đang được coi là hợp lệ tại chỗ.
- `FROM-CACHE`: outputs được lấy từ cache, task action không chạy.
- `EXECUTED`: task action đã chạy (có thể xử lý toàn bộ hoặc chỉ thay đổi).
- `NO-SOURCE`: task được bỏ qua khi nguồn được mô hình là rỗng.
- `SKIPPED`: task bị skip theo điều kiện khác, không tương đương up-to-date.
- `FAILED`: task action hoặc validation thất bại.

**Không kết luận “incremental build bị hỏng” chỉ vì một task không hiện `UP-TO-DATE`**: cần xem task đó có action/outputs không, có `--rerun-tasks` không, có input thay đổi không, và nó được thiết kế để chạy luôn hay không.

## 2. Gradle quyết định một task có thể bỏ qua bằng cách nào?

Một task thông thường có mô hình:

~~~text
Declared inputs
  - strings/booleans/numbers
  - files/directories + normalization
  - classpath / compile classpath
  - nested inputs
  - task implementation/logic
         |
         v
     Task action
         |
         v
Declared outputs
  - output file(s)
  - output directory/directories
~~~

Trước khi chạy task, Gradle lấy **fingerprints** của inputs: nội dung, đường dẫn đã chuẩn hóa, giá trị properties, cùng thông tin cần thiết về implementation. Sau khi action chạy thành công, Gradle ghi nhận trạng thái outputs. Trong lần build sau, nó so sánh fingerprints và trạng thái outputs. Khi không có thay đổi có ý nghĩa, task có thể **UP-TO-DATE**.

Ví dụ: nguồn Java thay đổi ⇒ `compileJava` phải cập nhật classes; chỉ sửa một unrelated Markdown file mà `compileJava` không khai báo làm input thì task này không có lý do chạy lại chỉ vì file đó thay đổi.

Hai điều kiện căn bản:

1. **Tất cả dữ liệu ảnh hưởng tới kết quả phải nằm trong declared inputs**.
2. **Tất cả file/directory mà task ghi như sản phẩm phải nằm trong declared outputs và có ownership rõ ràng**.

Nếu bỏ sót (1), task có thể trả lại output **cũ sai**. Nếu phá (2), Gradle không thể quản lý caching, cleanup và parallel execution đáng tin cậy.

Nguồn chính thức: [Gradle Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html).

## 3. Vì sao Gradle cần biết task nào sở hữu output?

Giả sử task A tạo:

~~~text
build/generated/api/model.json
~~~

Task B tạo:

~~~text
build/generated/reports/summary.json
~~~

Nếu A khai báo output directory **`build/generated`** và B cũng khai báo **`build/generated`**, cả hai đều tuyên bố sở hữu một cây thư mục chung. Vậy:

- File nào do A tạo, file nào do B tạo?
- Nếu A lấy outputs từ Build Cache, Gradle có được xóa file B không?
- Nếu B tạo file mới giữa lúc A đang snapshot, thay đổi có thuộc A không?
- Nếu hai tasks chạy song song, có race/partial file không?
- Khi input của A thay đổi nhưng B không đổi, cleanup nên xóa phần nào?

Gradle khó trả lời an toàn. **Overlapping outputs** vì vậy có thể làm **task output caching tự động bị vô hiệu hóa** với các tasks liên quan và làm cleanup/parallel execution trở nên rủi ro. Đây là vấn đề về **ownership và correctness**, không chỉ performance.

Cách tách đúng:

~~~text
build/generated/api/        <- task A sở hữu riêng
build/generated/reports/    <- task B sở hữu riêng
build/assembled/            <- task Sync/Copyright đóng vai trò hợp nhất
~~~

Trong đó một **task tổng hợp** nhận outputs của A và B làm inputs, rồi ghi vào một destination riêng. Gradle có thể xác định owner của mỗi output.

### Một sắc thái cần nhớ

Gradle Incremental Build docs có nêu: với một `@OutputDirectory`, **một số file mới được thêm vào directory sau lần chạy trước có thể được bỏ qua khi kiểm tra up-to-date**, để những task độc lập có thể có output cùng cây trong trường hợp legacy. Do đó **không nói “cứ có overlap thì mọi task chắc chắn luôn OUT-OF-DATE”**.

Nhưng điều này **không** làm overlapping outputs trở thành thiết kế tốt. Tài liệu Build Cache cảnh báo caching bị vô hiệu hóa khi output directories chồng lấn, vì Gradle không thể đảm bảo nhận diện/khôi phục stale outputs đúng. **Up-to-date và Build Cache có chính sách/giới hạn khác nhau.**

Nguồn: [Gradle Build Cache Concepts – The Case Against Overlapping Outputs](https://docs.gradle.org/current/userguide/build_cache_concepts.html).

## 4. Ba trường hợp output overlap thường gặp

### Trường hợp A — Cùng một file

~~~text
Task generateA -> build/generated/version.txt
Task generateB -> build/generated/version.txt
~~~

Đây là conflict trực tiếp. Nếu A và B có input khác nhau, ai là source of truth? Mọi task run order đều có thể ghi đè giá trị.

### Trường hợp B — Cùng một output directory

~~~text
Task generateJava  -> @OutputDirectory build/generated
Task generateKotlin -> @OutputDirectory build/generated
~~~

Dù files thực tế không cùng tên, cả hai tasks cùng claim ownership thư mục. Snapshot/cleanup/cache có thể không an toàn. Hãy tách:

~~~text
build/generated/java/
build/generated/kotlin/
~~~

### Trường hợp C — Một directory bao phủ output file của task khác

~~~text
Task generateBundle -> @OutputDirectory build/generated
Task generateManifest -> @OutputFile build/generated/manifest.json
~~~

Task generateManifest ghi dưới output tree mà generateBundle tuyên bố sở hữu. Đây cũng là **overlap**, không được chữa bằng cách đổi tên file nhưng vẫn để parent directory trùm cả hai.

**Quy tắc:** mỗi output root nên có **một task owner rõ ràng**. Nếu nhiều producers, để mỗi producer ghi một root riêng và có một aggregator hợp nhất có dependency đúng.

## 5. Anti-pattern: hai Copy tasks cùng destination

Mảnh Gradle Kotlin DSL **cố ý không an toàn**:

~~~kotlin
tasks.register<Copy>("copyA") {
    from("src/data/a")
    into(layout.buildDirectory.dir("generated/shared"))
}

tasks.register<Copy>("copyB") {
    from("src/data/b")
    into(layout.buildDirectory.dir("generated/shared"))
}
~~~

Hai `Copy` tasks có cùng destination. Nếu B ghi `settings.json`, A cũng ghi `settings.json`, task cuối cùng thắng. Nếu chúng ghi file khác nhau, vẫn có vấn đề output directory ownership; không nên kỳ vọng Build Cache hỗ trợ cả hai như các outputs độc lập.

Không dùng `mustRunAfter("copyA")` để giải quyết gốc rễ: sắp xếp thứ tự chỉ giảm một loại race, **không tạo output ownership riêng**, và `mustRunAfter` không làm task A tự được chọn khi chỉ chạy B.

Sửa:

~~~kotlin
val copyA = tasks.register<Sync>("copyA") {
    from("src/data/a")
    into(layout.buildDirectory.dir("generated/a"))
}

val copyB = tasks.register<Sync>("copyB") {
    from("src/data/b")
    into(layout.buildDirectory.dir("generated/b"))
}

tasks.register<Sync>("assembleData") {
    from(copyA)
    from(copyB)
    into(layout.buildDirectory.dir("assembled/data"))
}
~~~

Đây là **mảnh buildscript** cần source directories thật. `assembleData` có destination riêng; `from(copyA)`/`from(copyB)` đưa task outputs như inputs của aggregator và giữ thông tin task dependencies.

Nếu files của A và B có **cùng relative path**, khi hợp nhất phải đặt policy rõ: duplicate strategy/renaming hoặc namespace theo source, không để kết quả phụ thuộc ordering ngẫu nhiên.

### Sync khác Copy ở điểm nào?

`Sync` giúp destination phản ánh tập files nguồn: có thể xóa outputs không còn trong input set. Nó hợp lý cho final assembly directory có một owner. Nhưng **`Sync` cũng không an toàn nếu hai Sync tasks cùng destination**. Chỉ chuyển tên task từ Copy sang Sync không tự chữa output overlap.

## 6. Task không khai báo inputs: sai theo hướng “bỏ qua quá nhiều”

Một task đọc file cấu hình:

~~~kotlin
tasks.register("badGenerate") {
    val output = layout.buildDirectory.file("generated/result.txt")
    outputs.file(output)

    doLast {
        val source = file("config/greeting.txt")
        output.get().asFile.apply {
            parentFile.mkdirs()
            writeText(source.readText())
        }
    }
}
~~~

Đây là **mảnh minh họa lỗi**, không nên dùng trong build thực. Task đã khai báo output, nhưng **quên input `config/greeting.txt`**. Nếu lần thứ hai file source thay đổi mà task vẫn được coi là up-to-date theo những inputs đã khai báo, output có thể **giữ nội dung cũ**.

Đây là lỗi **false UP-TO-DATE**: build nhanh theo số liệu nhưng sai.

Sửa tối thiểu ở mức ad-hoc task:

~~~kotlin
tasks.register("generateFromFile") {
    val source = layout.projectDirectory.file("config/greeting.txt")
    val destination =
        layout.buildDirectory.file("generated/result.txt")

    inputs.file(source)
        .withPathSensitivity(PathSensitivity.NONE)
    outputs.file(destination)

    doLast {
        val file = destination.get().asFile
        file.parentFile.mkdirs()
        file.writeText(
            source.asFile.readText(Charsets.UTF_8),
            Charsets.UTF_8
        )
    }
}
~~~

Đây là **mảnh cấu hình** cần file nguồn tồn tại; để script compile tự đủ cần import:

~~~kotlin
import org.gradle.api.tasks.PathSensitivity
~~~

Việc khai báo `inputs.file(...)` giúp Gradle fingerprint nội dung file. `PathSensitivity.NONE` phù hợp khi chỉ **nội dung** file quyết định kết quả, không quan tâm basename/absolute path. Với input directory có relative tree structure, `PathSensitivity.RELATIVE` thường đúng hơn.

**Lưu ý Configuration Cache:** với ad-hoc task, không nên gọi Project APIs như `project.file(...)`, `project.layout`, `project.providers` từ **task action**. Cách production an toàn hơn là custom task class với typed properties, action chỉ đọc properties (phần 10).

## 7. Task không khai báo outputs: sai theo hướng “chạy lại quá nhiều”

Ví dụ:

~~~kotlin
tasks.register("badAlwaysWrite") {
    doLast {
        val file = layout.buildDirectory
            .file("generated/message.txt")
            .get()
            .asFile

        file.parentFile.mkdirs()
        file.writeText("hello")
    }
}
~~~

Đây là **mảnh minh họa lỗi**. Gradle không biết task sở hữu output nào. Với task có action mà không có declared outputs/up-to-date predicate, Gradle thường phải **chạy lại** vì không có bằng chứng outputs hiện tại còn đúng.

**Không suy từ đó rằng mọi lifecycle task không có output đều chạy action:** nhiều lifecycle tasks `build`/`check` không có own task actions và có thể hiện `UP-TO-DATE`/không hoạt động; chúng chỉ điều phối dependencies. Điều ta đang bàn là **task thật sự tạo file/side effect nhưng không khai báo kết quả**.

Sửa cần:

- Một `@OutputFile` hoặc `@OutputDirectory` đúng.
- Đầy đủ `@Input`/`@InputFile` ảnh hưởng tới output.
- Task action chỉ ghi vào output được khai báo.
- Không có writes chồng lấn với task khác.

Nếu task có **side effect ngoài filesystem** (gửi email, deploy server, publish release), đừng gắn một dummy output file chỉ để Gradle cho `UP-TO-DATE`. Side effect có semantics khác và thường phải chạy khi yêu cầu, với idempotency/authorization riêng.

## 8. Undeclared dependency: consumer dùng file từ task khác nhưng Gradle không biết

Một dạng lỗi thường gặp:

~~~text
Producer task -> build/generated/message.txt
Consumer task -> đọc build/generated/message.txt
Gradle task graph -> KHÔNG có edge consumer dependsOn producer
~~~

Nếu producer chưa chạy, consumer đọc file không tồn tại. Nếu chúng chạy song song, consumer có thể đọc file mới ghi một nửa hoặc file từ lần build trước.

Mảnh **cố tình sai**:

~~~kotlin
val generateMessage = tasks.register("generateMessage") {
    // generates build/generated/message.txt
}

tasks.register<Copy>("badUseMessage") {
    from(layout.buildDirectory.file("generated/message.txt"))
    into(layout.buildDirectory.dir("copied"))
}
~~~

Task `badUseMessage` chỉ nhận một **path-based provider** mà không có quan hệ task producer. Nó có thể thiếu inferred dependency. Trong các phiên bản Gradle hiện đại, validation có thể báo:

~~~text
Gradle detected a problem with the following location:
Task ':badUseMessage' uses this output of task ':generateMessage'
without declaring an explicit or implicit dependency.
~~~

Đây là **dạng thông báo minh họa**; log cụ thể tùy version/task setup.

### Fix ưu tiên: truyền TaskProvider hoặc output Provider có provenance

Với producer task có formal outputs:

~~~kotlin
val generateMessage = tasks.register<GenerateMessage>("generateMessage") {
    // destination: RegularFileProperty annotated @OutputFile
}

tasks.register<Copy>("useMessage") {
    from(generateMessage)
    into(layout.buildDirectory.dir("copied"))
}
~~~

`from(generateMessage)` nhận TaskProvider như một buildable FileCollection source và Gradle có thể nhận diện **producer task phải chạy trước**. Trong custom task typed property, cũng có thể dùng `from(generateMessage.flatMap { it.destination })` để giữ task provenance.

Nếu bạn dùng raw `File` do `archiveFile.get().asFile` trả về quá sớm rồi truyền vào task khác, có thể **mất build dependency metadata**. Tốt hơn giữ Provider:

~~~kotlin
val builtJar = tasks.named<Jar>("jar")

tasks.register<Copy>("copyJarCorrectly") {
    from(builtJar.flatMap { it.archiveFile })
    into(layout.buildDirectory.dir("dist"))
}
~~~

Đây là **mảnh cho project có Java Jar task**. Truyền `archiveFile` provider giúp bảo toàn task dependency.

Gradle docs [Validating Plugins — Implicit dependencies](https://docs.gradle.org/current/userguide/validation_problems.html) ưu tiên Provider và Task outputs hơn raw paths.

## 9. Ba quan hệ task dễ nhầm

| Quan hệ | Gradle behavior | Dùng khi |
| --- | --- | --- |
| `dependsOn(task)` | Khi consumer được chọn, producer cũng được chạy trước | Consumer cần output/work của producer |
| `mustRunAfter(task)` | Chỉ bảo đảm thứ tự **nếu cả hai đều được chọn** | Tasks độc lập nhưng không được chạy cùng lúc |
| `shouldRunAfter(task)` | Ưu tiên thứ tự mềm, có thể bị bỏ để tránh deadlock | Thứ tự mong muốn nhưng không bắt buộc |
| `finalizedBy(task)` | Thực hiện finalizer sau task được finalizing theo semantics Gradle | Dọn dẹp/kết thúc một lifecycle operation |

Nếu task B **cần dữ liệu do task A sản xuất**, `mustRunAfter(A)` không đủ: khi chỉ chạy B, A không được tự động chọn. Cần `dependsOn` hoặc tốt hơn là **input FileCollection/Provider có producer dependency**.

Ngược lại, đừng thêm `dependsOn` bừa bãi giữa hai independent tasks chỉ để buộc thứ tự: điều đó có thể làm mất parallelism, thêm công việc không cần và che architecture problem. Chọn quan hệ đúng semantic.

## 10. Ví dụ chạy được: Java 17 sử dụng resource do Gradle task tạo

Ví dụ dưới đây thể hiện **ownership rõ, declared input/output, inferred task dependency**, và cách kiểm chứng up-to-date behavior. Custom Gradle task class có typed `Property<String>` + `RegularFileProperty`. Task sản xuất một `greeting.txt`, `processResources` copy nó vào Java classpath, rồi ứng dụng Java 17 đọc file và in lời chào.

### 10.1. Thư mục

~~~text
incremental-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/demo/app/Main.java
~~~

Bạn cần Gradle Wrapper hoạt động với JDK/toolchain Java 17. Không cần dependencies từ Maven Central. Nếu Gradle runtime/Java 17 chưa được cài hoặc auto-provisioned phù hợp, phải chuẩn bị trước.

### 10.2. `settings.gradle.kts`

~~~kotlin
rootProject.name = "incremental-demo"
~~~

### 10.3. `build.gradle.kts` — file đầy đủ

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction
import org.gradle.language.jvm.tasks.ProcessResources

plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.app.Main")
}

@CacheableTask
abstract class GenerateGreeting : DefaultTask() {

    @get:Input
    abstract val recipient: Property<String>

    @get:OutputFile
    abstract val destination: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = destination.get().asFile
        output.parentFile.mkdirs()
        output.writeText(
            "Hello, " + recipient.get() + "!\n",
            Charsets.UTF_8
        )
    }
}

val generateGreeting =
    tasks.register<GenerateGreeting>("generateGreeting") {
        recipient.set(
            providers.gradleProperty("recipient")
                .orElse("Gradle")
        )

        destination.set(
            layout.buildDirectory.file(
                "generated/greeting/greeting.txt"
            )
        )
    }

tasks.named<ProcessResources>("processResources") {
    // Truyền TaskProvider: task output + producer dependency.
    from(generateGreeting)
}
~~~

**Giải thích:**

1. `application` cung cấp Java plugin, `processResources`, `classes` và `run`.
2. `@CacheableTask` cho custom task class **opt-in Build Cache**; không phải mọi custom task đều cacheable mặc định.
3. `recipient` là `@Input Property<String>`: khi `-Precipient` đổi, Gradle biết đầu ra cần thay đổi.
4. `destination` là `@OutputFile RegularFileProperty`: một file output rõ owner.
5. Task action đọc typed inputs, ghi duy nhất file declared output dưới `build/generated/greeting/`.
6. `tasks.register` trả về `TaskProvider`; tránh task realization sớm.
7. `processResources.from(generateGreeting)` đọc **formal output** của producer, giữ implicit dependency và copy vào `build/resources/main/` — nơi `processResources` mới là owner.
8. `run` của Application plugin dùng classes/resources runtime; thường tự phụ thuộc vào `classes`/`processResources` qua Java source set model, nên không cần thêm `dependsOn("generateGreeting")` bằng tay.

**Tại sao hai output locations khác nhau?**

~~~text
:generateGreeting
    owns build/generated/greeting/greeting.txt

:processResources
    owns build/resources/main/greeting.txt

:run
    consumes runtime classpath containing build/resources/main
~~~

Không có task thứ hai ghi trực tiếp vào output file của `generateGreeting`. Sự copy sang Java resources là bước **consumer task** có destination khác.

**Chú ý:** `@CacheableTask` ở đây chỉ phù hợp vì action xác định, chỉ phụ thuộc input `recipient` và tạo đúng một file. Nếu sau này action dùng current time, network response hoặc env variables mà không khai báo, **phải sửa inputs hoặc bỏ caching**. `@CacheableTask` không “làm cho task đúng” một cách thần kỳ.

### 10.4. `src/main/java/demo/app/Main.java` — file đầy đủ

~~~java
package demo.app;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws Exception {
        try (InputStream in = Main.class.getClassLoader()
                .getResourceAsStream("greeting.txt")) {

            if (in == null) {
                throw new IllegalStateException(
                    "Missing generated resource greeting.txt"
                );
            }

            String message = new String(
                in.readAllBytes(),
                StandardCharsets.UTF_8
            ).stripTrailing();

            System.out.println(message);
        }
    }
}
~~~

Mã Java 17 dùng `InputStream.readAllBytes()` và `String.stripTrailing()`, không có thư viện bên ngoài. `getResourceAsStream("greeting.txt")` lấy file từ **Java runtime classpath**, sau khi `processResources` copy file vào resources output.

### 10.5. Lần chạy thứ nhất

Linux/macOS:

~~~bash
./gradlew clean run --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean run --console=plain
~~~

**Stdout Java**:

~~~text
Hello, Gradle!
~~~

Gradle task log có thể kèm:

~~~text
> Task :generateGreeting
> Task :processResources
> Task :compileJava
> Task :classes
> Task :run
~~~

Đây là các **tên task thường thấy**, không bảo đảm thứ tự in/trạng thái tuyệt đối vì Gradle scheduling và task graph có thể khác. Quan hệ quan trọng là `generateGreeting` chạy trước `processResources` cần output của nó.

File dự kiến:

~~~text
build/generated/greeting/greeting.txt
build/resources/main/greeting.txt
~~~

Cả hai có nội dung:

~~~text
Hello, Gradle!
~~~

### 10.6. Lần chạy thứ hai: kiểm tra UP-TO-DATE

~~~bash
./gradlew run --console=plain
~~~

Với inputs, outputs, Gradle version và môi trường không đổi, `generateGreeting` và `processResources` thường được gắn trạng thái **`UP-TO-DATE`**. `compileJava` cũng có thể up-to-date nếu Java source không đổi.

Task `run` chạy lại Java application vì là một JavaExec task được dùng để thực sự chạy chương trình, không nên kỳ vọng nó luôn `UP-TO-DATE` như task tạo file.

Để chỉ đo generator:

~~~bash
./gradlew generateGreeting --console=plain
./gradlew generateGreeting --console=plain
~~~

Lần đầu có thể là `UP-TO-DATE` nếu trước đó `run` đã xây output; lần thứ hai **thường `UP-TO-DATE`** nếu không ai thay file hoặc inputs.

**Một task `UP-TO-DATE` không chứng minh nó không có bug về undeclared inputs.** Nếu bạn quên khai báo một input thật, Gradle có thể kết luận sai “không đổi”; cần review contract trước khi tin status.

### 10.7. Đổi input làm output được cập nhật

~~~bash
./gradlew run -Precipient=Team --console=plain
~~~

Stdout Java:

~~~text
Hello, Team!
~~~

Thay đổi `recipient` từ `Gradle` sang `Team` khiến fingerprint `@Input` thay đổi. Gradle chạy lại `generateGreeting`, rồi `processResources` nhận nội dung mới, application đọc đúng resource.

Tiếp tục:

~~~bash
./gradlew run -Precipient=Team --console=plain
~~~

Với cùng input `Team` và outputs còn nguyên, generator thường `UP-TO-DATE`. Đổi lại:

~~~bash
./gradlew run -Precipient=Gradle --console=plain
~~~

stdout Java trở về:

~~~text
Hello, Gradle!
~~~

Bạn vừa quan sát được **input → task output → downstream resources → runtime behavior** mà không hard-code producer task path trong Java code.

### 10.8. Xóa một output để kiểm tra phát hiện missing output

Xóa có chủ đích **chỉ file của bài demo**:

~~~bash
./gradlew clean run --console=plain
~~~

`clean` xóa toàn bộ `build/`, nên lần tiếp theo Gradle cần tạo output trở lại; build có thể lấy từ Build Cache nếu cache được bật và có entry tương thích. Lệnh này không chứng minh nhiệm vụ luôn **EXECUTED**, vì `FROM-CACHE` cũng có thể xảy ra.

Để quan sát tác động của missing output riêng, xóa `build/generated/greeting/greeting.txt` bằng công cụ của OS trên bài tập (chỉ file demo đó), rồi chạy `./gradlew generateGreeting --info`. Gradle sẽ coi output không còn hợp lệ và cần **recreate**, trừ khi cache phục hồi được.

**Không dùng một lệnh xóa recursive rộng trên repository thực** chỉ để kiểm tra up-to-date. Chỉ thao tác trong demo hoặc trên một output đã xác nhận an toàn.

### 10.9. `--rerun-tasks` khác `--build-cache`

~~~bash
./gradlew generateGreeting --rerun-tasks --console=plain
~~~

`--rerun-tasks` yêu cầu thực thi task actions lại, bỏ qua up-to-date checks thông thường và build-cache reuse cho các tasks được rerun. Nó hữu ích để so sánh kết quả của một lần chạy thực tế, nhưng **không phải cách sửa build declaration sai**.

~~~bash
./gradlew generateGreeting --build-cache --console=plain
~~~

`--build-cache` bật cache usage; vì `GenerateGreeting` được đánh dấu `@CacheableTask`, Gradle có thể lưu/phục hồi output nếu các điều kiện cacheability và fingerprint phù hợp. **Không cam kết sẽ thấy `FROM-CACHE`**: nếu outputs đang up-to-date, Gradle có thể skip trước; nếu cache trống hoặc task class/inputs khác, task vẫn chạy.

**Không dùng `--rerun-tasks` cho benchmark hit-rate Build Cache**, vì nó cố ý làm kết quả không phản ánh cơ chế reuse bình thường.

## 11. Mã custom task: chú thích nào cho đúng?

Gradle task property annotations mô hình hóa những dữ liệu mà action dùng:

| Annotation | Loại property thường dùng | Ý nghĩa |
| --- | --- | --- |
| `@Input` | `Property<String>`, `Property<Boolean>`, number, enum... | Giá trị ảnh hưởng kết quả |
| `@InputFile` | `RegularFileProperty` | Một file input, Gradle kiểm tra tồn tại/loại |
| `@InputFiles` | `ConfigurableFileCollection` | Nhiều files/directories input |
| `@InputDirectory` | `DirectoryProperty` | Một directory input |
| `@OutputFile` | `RegularFileProperty` | Một file output do task sở hữu |
| `@OutputDirectory` | `DirectoryProperty` | Một directory output do task sở hữu |
| `@Classpath` | FileCollection/classpath | Runtime classpath, order có ý nghĩa |
| `@CompileClasspath` | FileCollection/compile classpath | Chuẩn hóa giảm rebuild do private implementation changes |
| `@Nested` | Nested model | Quét properties có annotations trong object con |
| `@Internal` | Property không phải tracked input/output | Chỉ dùng khi thật sự nội bộ |
| `@Optional` | Input/output property có thể thiếu | Tắt validation cần value trong trường hợp phù hợp |
| `@LocalState` | File/directory local state | Không phải portable output; xử lý khi cache restore |
| `@Destroys` | File/directory bị xóa | Khai báo destructive work, không là output task theo cùng cách |

**Không đặt `@Input` lên `RegularFileProperty` để “theo dõi file”**. `@Input` xem file như một opaque value/path, **không fingerprint nội dung file** theo đúng mục đích. Hãy dùng `@InputFile` hoặc `@InputFiles` với path normalization thích hợp.

**Không đánh dấu một property tác động đến output bằng `@Internal`** chỉ để dập validation warning; như vậy Gradle thiếu thông tin và có thể UP-TO-DATE sai.

Với task type Kotlin:

~~~kotlin
abstract class TransformConfig : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val source: RegularFileProperty

    @get:OutputFile
    abstract val destination: RegularFileProperty
}
~~~

Đây là **mảnh class**, cần imports `DefaultTask`, `InputFile`, `OutputFile`, `PathSensitive`, `PathSensitivity`, `RegularFileProperty` và action/registration mới thực thi được. Mục đích là minh họa **annotations phải gắn vào getter** trong Kotlin (`@get:InputFile`), chứ không phải chỉ đặt tùy tiện lên backing field.

## 12. Path sensitivity và nguyên nhân rebuild giả

Gradle fingerprint file inputs cần biết **phần nào của đường dẫn ảnh hưởng kết quả**:

| `PathSensitivity` | Khi nên dùng | Lưu ý |
| --- | --- | --- |
| `NONE` | Chỉ nội dung một file quan trọng, location không quan trọng | Hai files có cùng nội dung nhưng tên khác có thể được coi tương đương |
| `RELATIVE` | Input directory tree có relative paths quan trọng | Phù hợp cho resource directories, templates trees |
| `NAME_ONLY` | Chỉ basename và content quan trọng | Ít phù hợp khi có subdirectories trùng tên |
| `ABSOLUTE` | Absolute path thực sự là input của output | Kém portable giữa máy/CI workspaces |

Ví dụ, producer đọc `src/templates/email/welcome.txt`; nếu output phụ thuộc vào relative path trong template tree, dùng `RELATIVE` cho directory input. Nếu producer chỉ đọc một file config bằng nội dung, `NONE` có thể giảm false misses khi move project giữa workspaces.

Đối với Java classpaths, dùng `@Classpath` hoặc `@CompileClasspath` thay cho `@InputFiles` bình thường khi semantics đúng. Gradle có normalization riêng cho archives/class entries, có thể bỏ qua timestamps hoặc những private ABI details mà Java compile không cần.

**Không chọn PathSensitivity.NONE mù quáng**: nếu output có chứa tên source file hoặc relative directory, việc bỏ path khỏi fingerprint làm **false up-to-date** khi đổi tên file.

## 13. File input bị thiếu và consumer/producer dependency

Một task khai báo:

~~~kotlin
@get:InputFile
abstract val inputFile: RegularFileProperty
~~~

thường cần **một file thực sự tồn tại trước khi action chạy**. Nếu file được task khác tạo, hãy set property bằng **output Provider của producer**.

Ví dụ mảnh setup:

~~~kotlin
val producer = tasks.named<GenerateGreeting>("generateGreeting")

tasks.register<SomeConsumer>("consumeGreeting") {
    sourceFile.set(producer.flatMap { it.destination })
}
~~~

Đây là **mảnh minh họa**, `SomeConsumer` phải là custom task type đã có `sourceFile: RegularFileProperty` annotated `@InputFile`. Quan trọng là `flatMap { it.destination }` giữ provenance và Gradle có thể suy ra producer dependency.

Không thay bằng:

~~~kotlin
// Sai thiết kế:
sourceFile.set(
    layout.buildDirectory.file("generated/greeting/greeting.txt")
)
~~~

nếu Gradle không biết task nào tạo file đó. Nó có thể báo validation **implicit dependency**, **input file doesn't exist**, hoặc chỉ đọc file cũ trong một build chưa được validate đủ.

### `@Optional` không phải cách bỏ qua sai task graph

Nếu một file **thực sự tùy chọn**, bạn có thể dùng `@Optional`/`@InputFiles` theo API thích hợp. Nhưng nếu file **bắt buộc** do producer tạo, việc đánh dấu optional để làm build không fail sẽ che mất producer dependency. Hãy sửa graph.

## 14. `@CacheableTask`: chỉ thêm sau khi output có tính quyết định

Custom task types **không cacheable mặc định**. `@CacheableTask` là một cam kết của tác giả rằng output portable và được quyết định bởi declared inputs, implementation và những yếu tố Gradle đã model.

Khi phù hợp:

~~~kotlin
@CacheableTask
abstract class GenerateReport : DefaultTask() {
    @get:Input
    abstract val reportTitle: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText(reportTitle.get(), Charsets.UTF_8)
    }
}
~~~

Đây là **mảnh class**; thiếu imports/registration nếu chạy riêng. Task chỉ đọc `reportTitle` và ghi duy nhất output file.

Không nên cacheable nếu task phụ thuộc mà không model hóa:

- System time/ngày hiện tại.
- Random number seed không khai báo.
- External HTTP/DB response có thể thay đổi.
- Machine-dependent absolute paths ghi vào output.
- Environment variables, locale/timezone/JDK hoặc tool version ảnh hưởng kết quả nhưng không tracked.
- File trong shared directory bị task khác tùy ý thay đổi.
- Secret/token được nhúng vào artifacts có nguy cơ bị lưu vào remote Build Cache.

Nếu mục đích chỉ là ghi log mỗi lần hoặc triển khai/đẩy release, đó có thể là **side-effect task** cần semantics khác; không cache nó bằng một marker file giả.

## 15. Output directory rộng quá mức: cache/cleanup không đáng tin

Ví dụ một codegen task khai báo:

~~~kotlin
@get:OutputDirectory
abstract val outputRoot: DirectoryProperty
~~~

và set:

~~~kotlin
outputRoot.set(layout.buildDirectory)
~~~

Đây là **bad configuration** vì task tự nhận sở hữu **toàn bộ `build/`** — nơi JavaCompile, test, jar, reports và nhiều task khác cũng ghi outputs. Gradle không thể phân biệt ownership an toàn.

Giới hạn:

~~~kotlin
outputRoot.set(
    layout.buildDirectory.dir("generated/schema-codegen")
)
~~~

Mỗi producer có output namespace riêng; task consumer khai báo file input/provider thay vì đọc một shared root.

Không dùng project root hay `src/main/java` làm output root của codegen: đó là source directory do developer/VCS quản lý. Gradle `clean`, generator và IDE có thể xóa/đè source thật. Với generated Java source, hãy dùng một path trong `build/generated/sources/...` rồi đăng ký generated source directory bằng TaskProvider để compile task biết producer dependency.

## 16. Khi nhiều generated files cần hợp nhất

Một cấu trúc tốt:

~~~text
:generateOpenApi
    output -> build/generated/openapi/

:generateProtobuf
    output -> build/generated/protobuf/

:assembleGenerated
    inputs <- both task outputs
    output -> build/assembled/generated/
~~~

Mảnh Kotlin DSL:

~~~kotlin
val openApi = tasks.register<Sync>("generateOpenApi") {
    from("src/spec/openapi")
    into(layout.buildDirectory.dir("generated/openapi"))
}

val protobuf = tasks.register<Sync>("generateProtobuf") {
    from("src/spec/protobuf")
    into(layout.buildDirectory.dir("generated/protobuf"))
}

tasks.register<Sync>("assembleGenerated") {
    from(openApi)
    from(protobuf)
    into(layout.buildDirectory.dir("assembled/generated"))
}
~~~

Mảnh này minh họa directory ownership và phụ thuộc; **không thật sự chạy OpenAPI/Protobuf compilers**. Nếu bạn đang dùng codegen plugins thật, để compiler/codegen task của mỗi plugin tạo output riêng và truyền typed output Providers cho aggregator.

Tránh trùng relative paths: thêm `into("openapi")`/`into("protobuf")` trong từng `from(...)` CopySpec nếu cần namespacing, hoặc cấu hình duplicate policy. **Không để loại file nào tùy ý ghi đè loại khác**.

### Về “một output directory có một task owner”

Đây là **best practice và điều kiện thuận lợi cho caching**, không phải khẳng định Gradle luôn fail ngay khi output directories chồng lấn. Một số legacy builds vẫn chạy, nhưng Gradle Build Cache và cleanup không thể đưa ra bảo đảm mạnh như với discrete outputs. Bảo toàn tính đúng trước khi bật parallel/cache.

## 17. Tác vụ không khai báo: Gradle không thể fingerprint điều nó không nhìn thấy

Nội dung “tác vụ không khai báo” trong bài này bao gồm **hai lớp lỗi khác nhau**:

1. **Task đã tồn tại nhưng thao tác I/O không được khai báo**: action đọc file, environment, network, hoặc ghi output ngoài `@OutputFile`/`@OutputDirectory`. Đây là **undeclared inputs/outputs**.
2. **Task A tạo tài nguyên, Task B dùng tài nguyên đó nhưng build graph không khai báo dependency**. Đây là **implicit/undeclared task dependency**.

Đừng đồng nhất với việc một task hoàn toàn không được register trong build script. Nếu bạn gõ `./gradlew nonexistent` và nhận “task not found”, đó là **task registration/selection error**, không phải incremental-build modeling error.

### Side effect không thuộc outputs

Ví dụ một task action dùng:

~~~kotlin
doLast {
    val token = System.getenv("BUILD_TOKEN")
    // Gọi một API bên ngoài với token.
}
~~~

Đây là **mảnh minh họa thiếu logic API**, không phải full runnable example. Nếu task còn tạo file output phụ thuộc remote response nhưng remote state không là declared input, cached/up-to-date decisions có thể sai.

Không được viết token vào `@Input` rồi tự động gửi remote cache: secrets có thể rò rỉ qua metadata/logging/cache keys hoặc artifacts tùy cách task làm. Với nhiệm vụ external deployment, thiết kế side-effect task rõ và chọn cách đánh dấu cache/up-to-date phù hợp, không giả vờ nó deterministic.

## 18. Gradle validation: lỗi nào là nguyên nhân mất tối ưu?

Gradle kiểm tra property annotations và task graph. Ví dụ:

- `@Input` áp vào file property thay vì `@InputFile`.
- Required input property chưa có value.
- Input path chỉ directory nhưng được khai báo `@InputFile`.
- Consumer dùng output của producer mà thiếu task dependency.
- Task không được phép ghi output path (file/directory không writable).
- Task properties không được annotation đủ trong custom task type.
- Task dùng annotation sai type hoặc đặt annotation vào setter/backing field thay vì getter.
- Unknown task implementation type/unsupported cacheable property.

Gradle có thể in **validation problem** trong console/report và dừng build. Không phải mọi cảnh báo validation đều làm task fail ngay trên mọi Gradle version; nhưng tài liệu Gradle nói các task có vấn đề validation có thể bị **tắt nhiều tối ưu quan trọng**: không up-to-date, không Build Cache, không chạy parallel/incremental an toàn.

Đối với custom plugin/task type trong một Gradle plugin build, dùng:

~~~bash
./gradlew validatePlugins
~~~

`validatePlugins` được plugin development tooling cung cấp. Đây là **lệnh dành cho plugin project đã áp dụng `java-gradle-plugin`**, không phải mọi project Java đều có task đó.

Nguồn: [Gradle — Validating Plugins](https://docs.gradle.org/current/userguide/validation_problems.html).

## 19. Gradle up-to-date validation không thay thế data correctness tests

Giả sử test chỉ kiểm tra task có trạng thái `UP-TO-DATE` sau hai lần chạy. Điều đó **chưa đủ** để chứng minh task khai báo chính xác.

Cần ít nhất bốn tình huống:

1. **Cold build**: task tạo output đúng.
2. **No-change build**: task được skip hợp lý, output vẫn đúng.
3. **Relevant input changed**: task chạy lại và output phản ánh input mới.
4. **Relevant output deleted/tampered**: task tạo lại/khôi phục output, không tiếp tục dùng file sai.

Nếu có Build Cache:

5. **Restore from cache in clean workspace**: output restored tương đương về nội dung, không chứa absolute path/machine-specific artifacts ngoài contract.
6. **Parallel/concurrent runs**: không overlap hoặc race với task khác.
7. **Incremental input changes**: chỉ thay source cần thiết và kiểm tra outputs tương ứng.
8. **CI clean checkout**: không phụ thuộc file sót từ build trước.

Khi chỉ thấy `UP-TO-DATE` mà generated file chứa sai data, **đó có thể là lỗi nghiêm trọng hơn việc task luôn chạy**.

## 20. Sự khác nhau giữa snapshot nội dung và timestamps

Gradle sử dụng fingerprints có xét file paths, file contents và metadata phù hợp. Tùy filesystem watcher, cache state và loại input, Gradle có thể dùng metadata như size/lastModified để tránh băm lại khi có thể tin cậy; các thay đổi nguồn thực sự vẫn phải được phát hiện theo cơ chế file snapshots của Gradle.

Vì thế không nên:

- Thay đổi file content rồi cố “giữ nguyên size/timestamp” để kiểm thử một trường hợp không đại diện workflow bình thường.
- Ghi output bằng một công cụ ngoài Gradle rồi nghĩ mọi up-to-date check chắc chắn phát hiện.
- Gắn source directory quá rộng như toàn bộ repository vào mọi task inputs, khiến thay đổi README/.git làm regenerate vô ích.
- Chỉ dùng file modification time thủ công để quyết định build đúng hay sai.

**Input snapshots phải phản ánh đúng semantic dependency.** Một task generate một JSON theo schema và template chỉ cần khai báo schema/template files và options, không phải toàn bộ `projectDir`.

## 21. Gradle file system watching và continuous build

Gradle Virtual File System (VFS) retention có thể tái sử dụng file snapshots giữa các builds và theo dõi thay đổi để giảm chi phí I/O. Continuous build:

~~~bash
./gradlew compileJava --continuous
~~~

cho Gradle theo dõi thay đổi **trong declared inputs** và chạy lại task graph khi có events phù hợp. Nếu custom task **không khai báo file nguồn** mà action âm thầm đọc, VFS/continuous build không có contract để biết file đó cần trigger công việc.

Tuy nhiên VFS watching không đồng nghĩa task output caching; và `--continuous` không “chữa” missing task dependencies hoặc overlapping outputs. Nó chỉ phản ứng tốt khi task models đã đúng.

## 22. Cache misses do input/implementation quá rộng

Một số tasks **đúng về mặt dữ liệu** nhưng luôn OUT-OF-DATE do khai báo inputs không hợp lý:

~~~kotlin
// Mảnh anti-pattern:
inputs.dir(layout.projectDirectory)
~~~

Nếu task chỉ cần `src/templates` mà theo dõi cả root project, thay đổi `README.md`, `build.gradle.kts` hoặc generated directories có thể làm fingerprint thay đổi, thậm chí tạo feedback loop nếu output nằm trong input tree.

Sửa:

~~~kotlin
inputs.dir(layout.projectDirectory.dir("src/templates"))
    .withPathSensitivity(PathSensitivity.RELATIVE)
~~~

Đây là **mảnh cho ad-hoc task** đọc template directory và không viết output vào chính folder đó. Nếu input thật có nhiều nguồn, khai báo đúng các nguồn riêng và type/normalization phù hợp; không cắt bớt input thực chỉ để có cache hit đẹp.

### Feedback loop: output nằm trong input directory

~~~text
Task input  -> project root
Task output -> project root/build/generated/data.json
~~~

Mỗi lần task chạy, nó có thể tự làm thay đổi input snapshot của lần sau. Đó là một trong các nguyên nhân task mãi không up-to-date.

Tránh bằng cách:
- Input chỉ là source files cần thiết, ví dụ `src/templates`.
- Output chỉ ghi vào `build/generated/my-task`.
- Không để generated outputs nằm trong input tree của chính task.
- Không thêm toàn bộ Gradle output caches vào task input.

## 23. Nondeterministic outputs: cùng input, khác kết quả

Task tạo output:

~~~kotlin
// Mảnh anti-pattern:
val line = "Built at " + java.time.Instant.now().toString()
~~~

Nếu output thực sự chứa giờ build, giờ **phải được mô hình hóa là một input thay đổi** hoặc task **không được coi cacheable/up-to-date** theo kiểu deterministic. Điều tương tự xảy ra với:

- `UUID.randomUUID()` mỗi lần chạy.
- Absolute workspace path nhúng vào file.
- Hostname/user name lấy từ máy.
- HTTP response không được version/hash.
- Unstable file iteration order.
- ZIP/TAR timestamps/order không được chuẩn hóa phù hợp với Gradle version.
- Toolchain versions/locale ảnh hưởng output nhưng không tracked.

**Không đơn giản thêm `@CacheableTask` rồi nghĩ Gradle sẽ tự phát hiện output nondeterminism**. Build cache giả định cùng cache key ⇒ outputs tương đương. Nếu tác giả vi phạm hợp đồng, cache có thể khuếch đại lỗi từ máy này sang máy khác.

Gradle 9.x có những mặc định cho reproducible archives tốt hơn các versions cũ; với older Wrappers hoặc custom archive tasks, kiểm tra `isPreserveFileTimestamps`/`isReproducibleFileOrder` theo tài liệu và test bytes thật thay vì suy đoán.

## 24. Build Cache và remote cache không sửa đúng mô hình input/output

Khi có task cacheable, Gradle Build Cache có thể:
- Lưu outputs sau lần thực thi.
- Phục hồi outputs ở workspace khác nếu implementation/inputs tương đương.
- Giúp CI và developer reuse cùng artifacts.

Nhưng nếu task khai báo thiếu inputs, cache key không thay đổi khi input ẩn thay đổi; một kết quả **sai** có thể được dùng lại ở nhiều máy. Nếu tasks chồng lấn outputs, Gradle có thể **từ chối cache** vì không có ownership rõ ràng.

**Thứ tự đúng:**
1. Correctness và deterministic outputs.
2. Inputs/outputs/dependency graph được khai báo đầy đủ.
3. Up-to-date checks và changed-input tests PASS.
4. Cacheability của task type được xem xét và opt-in phù hợp.
5. Local Build Cache.
6. Remote Build Cache/CI sharing.

Không bật remote cache để “bù” cho task luôn chạy; nó chỉ giúp khi task thực sự safe và cacheable.

## 25. Debug bằng `--info` và task outcomes

Lệnh:

~~~bash
./gradlew generateGreeting --info --console=plain
~~~

Gradle có thể cung cấp lý do task không up-to-date, ví dụ theo nhóm:

~~~text
Task has not declared any outputs
Value of input property ... has changed
Output property ... file has been removed
Task output caching is disabled
~~~

Đây là **các dạng thông tin minh họa**, không cam kết từng chữ/định dạng trên mọi version. Đọc **lý do** thay vì chỉ đếm tasks executed.

Những câu hỏi chẩn đoán:

- Có declared output chưa?
- Input/property nào thay đổi?
- Output nào bị task khác ghi/xóa?
- Có buildscript/plugin/task implementation thay đổi?
- Có `--rerun-tasks` hoặc cleanup trước đó không?
- Task có đủ điều kiện `@CacheableTask` và `--build-cache` không?
- Có overlapping output warning hoặc validation problem không?
- Task lấy input từ raw file path thay vì producer Provider không?
- Có non-file side effect hoặc nondeterministic data không?

### So sánh hai lần chạy cùng điều kiện

~~~bash
./gradlew clean generateGreeting --console=plain
./gradlew generateGreeting --console=plain
~~~

Nếu lần hai vẫn `EXECUTED`, dùng `--info` rồi kiểm tra inputs/outputs. Nếu đã bật Build Cache, lần đầu có thể `FROM-CACHE` khi cache có entry; muốn đo chỉ cơ chế up-to-date, có thể tắt cache trong thí nghiệm:

~~~bash
./gradlew generateGreeting --no-build-cache --console=plain
./gradlew generateGreeting --no-build-cache --console=plain
~~~

Một task action chỉ log/không có output có thể được thiết kế chạy mỗi lần; không ép mọi task thành `UP-TO-DATE`.

## 26. Báo cáo Build Cache misses

Gradle có tài liệu chuyên về [Build Cache Debugging](https://docs.gradle.org/current/userguide/build_cache_debugging.html) và [Common Caching Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html). Đọc task input comparison/Build Scan hoặc Develocity khi được dự án cho phép sử dụng, để phân biệt:

- Task implementation hash changed.
- Classpath changed.
- Declared input value changed.
- File path normalization chưa phù hợp.
- Output is overlapping.
- Task caching disabled by default or reason.
- Non-relocatable outputs.
- Cache key khác giữa CI và local do OS/JDK/tooling.
- Task validation failed.

**Task không cacheable nhưng vẫn UP-TO-DATE bình thường** là trường hợp hợp lệ. Trước khi cố làm một `Copy` task cacheable, nhớ rằng copying đơn giản nhiều khi rẻ hơn IO/caching overhead và Gradle built-in tasks có chính sách cacheability theo từng loại.

## 27. Configuration Cache không phải Build Cache

Một nhầm lẫn thường gặp là tưởng:

~~~bash
./gradlew help --configuration-cache
~~~

sẽ giúp mọi tasks có outputs từ cache. **Configuration Cache** lưu/reuse **kết quả configuration của build**, không phải task output files.

| Feature | Tối ưu điều gì? |
| --- | --- |
| **Configuration Cache** | Bỏ qua nhiều công việc cấu hình dự án/Gradle task graph ở build sau |
| **Build Cache** | Phục hồi task output files nếu cache key match |
| **Up-to-date checks** | Skip task action khi local inputs/outputs còn hợp lệ |
| **Incremental processing** | Chỉ xử lý file changes bên trong task action |

Một custom task có thể **UP-TO-DATE** nhưng **không tương thích Configuration Cache**, ví dụ action gọi `project.file(...)` hoặc đọc Project model khi task action đang chạy. Ngược lại, task có thể Configuration Cache-compatible nhưng không cacheable hoặc luôn phải chạy vì là side effect task.

Ở demo `GenerateGreeting`, action chỉ đọc typed properties và ghi file đã khai báo, không gọi `Project` API; đây là một thiết kế thuận với Configuration Cache hơn kiểu ad-hoc `doLast { project.file(...) }`.

## 28. Tính song song và output overlap

Trong một multi-project build:

~~~bash
./gradlew build --parallel --max-workers=4
~~~

Gradle có thể chạy tasks độc lập đồng thời. Nếu chúng có output directories chồng lấn, filesystem races có thể gây:

- File bị xóa giữa lúc task khác đọc.
- Artifact chứa dữ liệu từ hai task không cùng version.
- Unstable/incomplete generated code.
- CI flaky failures chỉ xuất hiện khi nhiều workers.
- Thời gian chạy không xác định do lock contention.

**Đừng sửa bằng cách tắt parallelism mãi mãi nếu có thể tách outputs**. Giảm concurrency có thể là biện pháp tạm thời để tái hiện/làm CI ổn định, nhưng vấn đề ownership vẫn còn ảnh hưởng caching/cleanup.

Nếu resource không thể phân tách và **bản chất không phải task output** (một external DB, service, thiết bị), bạn cần Build Service/task-level coordination hoặc resource isolation thích hợp; không giả vờ một output marker file là resource lock.

## 29. Duplicate outputs trong một task cũng cần policy

Một `Copy`/`Sync` task có thể nhận nhiều sources có relative path trùng:

~~~text
sourceA/config.json
sourceB/config.json
=> destination/config.json
~~~

Đây **không phải** overlapping outputs giữa hai **tasks** (vì chỉ một task có destination), nhưng vẫn có conflict nội bộ trong quá trình assembly. Gradle có `duplicatesStrategy` và các per-CopySpec configurations.

Có thể:
- Reject duplicates khi chúng biểu thị lỗi.
- Rename source files trước khi copy.
- Đặt mỗi nguồn trong subdirectory riêng.
- Chọn explicit override policy khi đó là hành vi sản phẩm mong muốn.

**Không coi việc gom hai producers vào một Sync task là đủ nếu bản thân Sync vẫn ghi đè file tên trùng mà không có policy**.

## 30. `@SkipWhenEmpty` và `@Incremental`

Với custom task xử lý collection của files:

~~~kotlin
@get:InputFiles
@get:SkipWhenEmpty
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sources: ConfigurableFileCollection
~~~

Là **mảnh Kotlin task property** cần imports/class khai báo đầy đủ. `@SkipWhenEmpty` cho phép Gradle bỏ task khi tất cả relevant source files rỗng và có semantics incremental input tương ứng.

Nếu task cần biết từng file added/modified/removed, thiết kế `@Incremental`/`@SkipWhenEmpty` cùng `InputChanges`:

~~~kotlin
@TaskAction
fun process(changes: InputChanges) {
    for (change in changes.getFileChanges(sources)) {
        // Xử lý ADDED / MODIFIED / REMOVED theo FileChange.
    }
}
~~~

Đây là **mảnh mô tả API**, không phải runnable task nếu thiếu source property, imports và output handling. Quan trọng là **incremental task action** khác `UP-TO-DATE`: một task có thể chạy, nhưng xử lý thay đổi nhỏ hơn cả input set.

Nếu task ghi output vào cùng directory đang là `sources`, việc track changed files rất dễ trở thành self-triggering loop. Tách input/output roots.

## 31. JavaCompile và annotation processing có thể làm mất tính tăng dần

Với Java, `JavaCompile` là task đặc biệt, Gradle có incremental compilation mechanisms. Những nguyên nhân thường gặp khiến nhiều classes compile lại hơn dự kiến:

- Thay đổi **public ABI** ảnh hưởng nhiều downstream classes.
- Thay đổi annotation processor hoặc processor metadata khiến incremental processing không được hỗ trợ.
- Compiler options hoặc Java toolchain thay đổi.
- Annotation processor khai báo sai classpath/trộn implementation processor với compile classpath.
- Một generated source bị viết/đụng bởi nhiều tasks.
- Buildscript hoặc Java compile task inputs bị khai báo quá rộng.

Đối với generated code, plugin/processor nên để Gradle hiểu generated sources/task dependencies, không cho hai generators ghi chung `build/generated/sources`. Nếu buộc phải combine, tạo dedicated output roots và aggregate step.

**Không khẳng định “chỉ thay một Java source luôn compile đúng một file”**. Java compilation phải xét dependency graph, ABI và annotation processing semantics; Gradle có quyền recompile nhiều hơn để đảm bảo correctness.

## 32. Không lạm dụng `outputs.upToDateWhen`

Một số tutorials dùng:

~~~kotlin
tasks.named("someTask") {
    outputs.upToDateWhen { false }
}
~~~

Mảnh này cố ý tắt up-to-date reuse cho task. Nó có thể hữu ích trong một bài debug cực hẹp, nhưng không giải quyết:

- Missing inputs.
- Missing output ownership.
- Implicit dependency.
- Nondeterministic action.
- Overlapping outputs.
- Cache safety.

Nếu mọi task đều `upToDateWhen { false }`, build chậm là điều hiển nhiên. Nên bỏ hook khi hoàn tất debug và quay lại mô hình inputs/outputs đúng. Tài liệu Gradle cũng khuyên không dùng custom up-to-date logic để thay thế declarations chính xác.

## 33. Cách phân loại nguyên nhân theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm chứng |
| --- | --- | --- |
| Task luôn `EXECUTED` | Không có outputs/outputs đổi mỗi lần | `--info`, kiểm tra annotations |
| Task `UP-TO-DATE` nhưng file stale | Thiếu input, task đọc nguồn ẩn | Thay một relevant input và so output |
| `FROM-CACHE` trả output sai | Cacheable task thiếu input hoặc nondeterministic | Inspect cache key/task implementation/inputs |
| Cache disabled due to overlapping outputs | Hai tasks claim same root/file | Audit output paths và tách |
| `No matching input file`/input missing | Consumer không có producer dependency | Truyền TaskProvider/output Provider |
| Validation implicit dependency | Consumer đọc raw output path của task khác | `from(producerTask)` hoặc `flatMap` output |
| Task nặng chạy lại khi chỉ sửa README | Inputs dir quá rộng | Đổi từ project root sang relevant source dir |
| Generator chạy lại lần nữa sau chính nó | Output nằm dưới input tree | Tách roots |
| `Copy`/`Sync` kết quả chập chờn | Nhiều writers/duplicate relative paths | Một owner mỗi destination, duplicate policy |
| `--parallel` làm CI flaky | Race outputs/shared resources | Tách task outputs; giới hạn concurrency nếu cần |
| Gradle plugin `validatePlugins` fail | Task properties sai annotations/types | Sửa task class metadata |
| Thay Java version rebuild nhiều tasks | Toolchain/ABI/compiler inputs thay đổi | Kiểm tra `javaToolchains` và compile report |
| Build Cache trống | Cache chưa có entry hoặc task chưa cacheable | `--build-cache`, task type/annotations |
| `run` luôn chạy | JavaExec application là side-effect/không có persistent output contract | Điều này không nhất thiết là lỗi |
| `clean` làm build không UP-TO-DATE | Outputs vừa bị xóa | Không dùng clean giữa hai lần đo reuse |
| Remote CI cache không hit | Fingerprints khác hoặc caching policy | Gradle Build Cache debugging/input comparison |

**Triệu chứng chỉ là giả thuyết ban đầu.** Phải xem actual task inputs/outputs và logs mới chẩn đoán được nguyên nhân cụ thể.

## 34. Quy trình kiểm tra một task mới trong pull request

1. **Đọc task implementation**: action đọc những giá trị/files nào? Ghi vào những files nào?
2. **Đối chiếu annotations**: mọi dữ liệu ảnh hưởng output đã được khai báo? Có `@Internal` sai không?
3. **Xem output ownership**: có task khác khai báo directory bao phủ cùng location không?
4. **Kiểm tra path sensitivity**: absolute paths có thật sự cần thiết không?
5. **Tìm producer dependencies**: input file được tạo từ task nào? Có TaskProvider/Provider link không?
6. **Không cache side effects**: deployment, remote mutations hoặc secrets phải có policy riêng.
7. **Chạy clean build**: output bytes/content đúng?
8. **Chạy lại no-change**: có `UP-TO-DATE` hợp lý?
9. **Đổi một input liên quan**: task re-execute, output đổi đúng?
10. **Đổi unrelated input**: task nên giữ `UP-TO-DATE` nếu contract cho phép?
11. **Xóa output**: task tự tái tạo/phục hồi đúng?
12. **Thử Build Cache**: chỉ sau khi task deterministic và cacheable.
13. **Thử `--parallel`**: không có race/shared output root.
14. **Thử Configuration Cache**: task actions không chạm Project/Gradle model sai phase.
15. **Chạy validation**: `validatePlugins` cho plugin task types; xem problems reports nếu Gradle báo.
16. **Chạy trên CI workspace sạch**: không dùng file sót từ local.

### Kiểm tra cần có trong automated tests

Với custom Gradle plugin, dùng **Gradle TestKit** để chạy một fixture build, kiểm tra task outcome `TaskOutcome.UP_TO_DATE` sau lần không đổi, `SUCCESS` khi đổi input, output bytes đúng và task graph có producer dependency. Tình huống **missing output + cache enabled** có thể cho `FROM_CACHE`; fixture test nên phân biệt expected outcomes theo điều kiện.

`GradleRunner`/TestKit giúp biến kiểm tra này thành regression tests, nhưng test fixture cần được dựng đầy đủ (settings/build scripts, source files) chứ không chỉ assert log text tùy Gradle version.

## 35. Bài tập tự kiểm tra

**Câu 1.** Một task có `@Input` và `@OutputFile` đúng, lần chạy thứ hai hiển thị `UP-TO-DATE`. Có nghĩa Build Cache đã hoạt động không?

**Đáp:** Không. Up-to-date là trạng thái local, Build Cache là cơ chế lưu/phục hồi outputs khác. Một task có thể up-to-date dù không cacheable.

**Câu 2.** Hai tasks cùng khai báo `@OutputDirectory build/generated` nhưng tạo hai files khác tên. Có an toàn để remote cache không?

**Đáp:** Không nên. Ownership overlapping có thể vô hiệu hóa output caching và gây vấn đề cleanup/parallelism. Tách output directories.

**Câu 3.** Task đọc `config/greeting.txt` nhưng không khai báo file đó làm input. Có thể xảy ra chuyện gì?

**Đáp:** False `UP-TO-DATE` khi config đổi nhưng Gradle không biết; output stale/sai.

**Câu 4.** Task tạo file nhưng quên `@OutputFile`. Kết quả gì thường xảy ra?

**Đáp:** Task action không có output contract để up-to-date check; thường bị chạy lại, không cacheable như mong muốn.

**Câu 5.** `mustRunAfter` có tương đương `dependsOn` không?

**Đáp:** Không. `mustRunAfter` chỉ sắp thứ tự khi cả hai được chọn; `dependsOn` yêu cầu producer được chạy khi consumer chạy.

**Câu 6.** Vì sao `from(taskProvider)` tốt hơn `from(file("build/generated/x.txt"))`?

**Đáp:** Nó giữ provenance của output và Gradle có thể suy ra producer task dependency.

**Câu 7.** Có phải cứ output overlap thì task chắc chắn luôn không `UP-TO-DATE`?

**Đáp:** Không. Gradle có quy tắc kiểm tra output directories tinh tế hơn. Nhưng output caching/ownership bị ảnh hưởng nghiêm trọng, nên vẫn cần sửa.

**Câu 8.** `--rerun-tasks` có chữa missing inputs không?

**Đáp:** Không. Nó ép actions chạy lại, có thể che stale output trong một lần, nhưng build model vẫn sai.

**Câu 9.** Tại sao task `run` ở Java demo chạy lại trong khi `generateGreeting` UP-TO-DATE?

**Đáp:** `run` thực thi ứng dụng, không phải task tạo persistent output để skip như generator. Hai loại task có semantics khác.

**Câu 10.** `@CacheableTask` có đủ để task ghi timestamp hoặc HTTP response được cache an toàn không?

**Đáp:** Không. Cần khai báo mọi input ảnh hưởng output, deterministic behavior và chính sách secrets/cache.

**Câu 11.** Nếu input directory khai báo là project root, output nằm trong `build/`, có rủi ro gì?

**Đáp:** Output nằm trong input tree, có thể tạo self-invalidation hoặc rebuilds quá rộng khi files thay đổi.

**Câu 12.** `@Input` áp lên `RegularFileProperty` có fingerprint nội dung file đúng cách không?

**Đáp:** Không. Dùng `@InputFile`/`@InputFiles` và path sensitivity hợp lý.

**Câu 13.** Vì sao `Sync` không chữa được overlap nếu hai Sync tasks cùng destination?

**Đáp:** Hai tasks vẫn cùng sở hữu output root. Cần một Sync aggregator và các producer destinations riêng.

**Câu 14.** Gradle Configuration Cache và Build Cache khác nhau thế nào?

**Đáp:** Configuration Cache reuse phần cấu hình/task graph; Build Cache reuse task outputs. Up-to-date checks lại là local skip.

**Câu 15.** Sau khi sửa code của custom task, dù declared inputs không đổi, task có thể chạy lại không?

**Đáp:** Có. Task implementation/action code tham gia xác định correctness/caching; thay implementation có thể invalidation.

**Câu 16.** Nếu `processResources` cần file do `generateGreeting` tạo, có phải thêm `dependsOn` thủ công?

**Đáp:** Không khi `from(generateGreeting)` dùng TaskProvider outputs đúng: Gradle giữ inferred dependency. Nếu chỉ dùng raw path, cần sửa wiring để bảo toàn provenance.

## 36. Checklist trước khi bật Build Cache/parallel trong CI

- [ ] Mỗi task tạo output đã có `@OutputFile`/`@OutputDirectory` đúng.
- [ ] Không có hai tasks khai báo output root chồng lấn.
- [ ] Task không ghi file ngoài declared outputs.
- [ ] Các file/values làm thay đổi output đều là declared inputs.
- [ ] File input annotations đúng loại và path sensitivity đúng semantic.
- [ ] Không có Project API access ở task action gây lỗi Configuration Cache.
- [ ] Consumer files liên kết tới producer TaskProvider/output Provider.
- [ ] Không dùng `mustRunAfter` để thay dependency dữ liệu.
- [ ] Producer tasks sở hữu output roots riêng; aggregator có destination riêng.
- [ ] Duplicate relative paths có policy rõ khi merge outputs.
- [ ] Không dùng output path nằm trong input tree.
- [ ] Output không phụ thuộc thời gian/ngẫu nhiên/network ngoài declared inputs.
- [ ] `@CacheableTask` chỉ bật khi output deterministic và safe.
- [ ] Side-effect tasks (deploy/publish/email) không giả vờ tạo marker cacheable.
- [ ] Chạy cold/no-change/changed-input/missing-output tests.
- [ ] Phân biệt `UP-TO-DATE`, `FROM-CACHE`, `EXECUTED` và `NO-SOURCE`.
- [ ] `--rerun-tasks` chỉ là diagnostic, không phải “fix”.
- [ ] Build scan/`--info` không lộ secrets hoặc artifact nội bộ khi chia sẻ.
- [ ] Gradle plugin task types được validation.
- [ ] CI clean workspace và parallel runs không tranh outputs.

## 37. Nguồn tham khảo chính thức

- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): input/output snapshots, annotations, up-to-date, inferred dependencies, output directory handling.
- [Gradle — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): overlapping outputs, task ownership, cache behavior và relocation.
- [Gradle — Common Caching Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html): overlapping outputs và nondeterministic task outputs.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cacheable task types, Build Cache operation, `@CacheableTask`.
- [Gradle — Build Cache Debugging](https://docs.gradle.org/current/userguide/build_cache_debugging.html): so sánh task inputs, cách chẩn đoán cache misses.
- [Gradle — Validating Plugins](https://docs.gradle.org/current/userguide/validation_problems.html): incorrect input annotations, implicit task dependencies, runtime validation, missing inputs.
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): `dependsOn`, `mustRunAfter`, `finalizedBy` và task selection.
- [Gradle — Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `TaskProvider`, lazy configuration.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): path sensitivity, typed properties và task correctness.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): khác Build Cache, task action constraints và configuration reuse.
- [Gradle — Gradle TestKit](https://docs.gradle.org/current/userguide/test_kit.html): functional tests của custom Gradle plugins/tasks.
