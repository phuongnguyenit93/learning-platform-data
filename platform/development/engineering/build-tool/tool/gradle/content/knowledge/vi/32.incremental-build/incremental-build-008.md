# Kiểm chứng hành vi bằng hai lần build và thay đổi đầu vào có kiểm soát trong Gradle

## 1. Vì sao cần kiểm chứng build tăng dần bằng thí nghiệm?

Một build Gradle chạy thành công lần đầu chưa chứng minh build đã khai báo đầu vào, đầu ra và quan hệ task đúng. Lỗi thường chỉ lộ ra khi:

- Không thay source mà Gradle vẫn chạy lại toàn bộ tasks.
- Sửa một file đầu vào nhưng task bị báo `UP-TO-DATE` và giữ kết quả cũ.
- Đổi resource nhưng lại phải compile toàn bộ Java sources.
- Xóa output rồi task không tạo lại output.
- Task dùng một biến môi trường, config file hoặc version nhưng không khai báo đó là input.
- Bật build cache khiến kết quả `FROM-CACHE` bị hiểu nhầm là một lần thực thi mới.
- Script build in lời nhắn `"build finished"`, nhưng không ai biết bytecode hay artifact có đổi không.
- Dùng `--rerun-tasks` để “kiểm chứng build nhanh” khiến Gradle bỏ qua cơ chế up-to-date cần kiểm tra.
- Thử nghiệm khi IDE, CI hoặc process khác cùng chỉnh files, nên không còn một thay đổi có kiểm soát.
- So thời gian chạy của hai lần build mà không kiểm task outcomes hoặc bytes của outputs.

**Phương pháp đúng** không phải chỉ chạy `./gradlew build` hai lần rồi kết luận “lần hai nhanh hơn”. Ta cần một chuỗi thí nghiệm có **điều kiện đầu vào**, **lệnh thực thi**, **quan sát task outcome**, **kiểm bytes output** và **thay đúng một yếu tố**.

Một kịch bản chuẩn gồm:

1. **Lần 1 — baseline:** chạy clean build, đầu vào cố định, đầu ra được tạo.
2. **Lần 2 — không thay đổi:** chạy lại cùng tasks, cùng inputs, cùng Gradle/JDK; tasks có outputs được khai báo đúng thường báo `UP-TO-DATE`.
3. **Lần 3 — một thay đổi có kiểm soát:** sửa **một input đã khai báo**, chạy lại, kiểm task liên quan thực thi và kết quả phản ánh thay đổi.
4. **Lần 4 — ổn định lại:** chạy thêm lần nữa không đổi; task lại `UP-TO-DATE`.
5. **Negative/control cases:** sửa một file **không phải input**, đổi một property input, xóa/sửa output, thử build cache riêng.
6. **Báo cáo:** ghi task name, outcome, input diff, output diff/hash, Gradle/JDK version, các flags và giới hạn kết luận.

Bài này tập trung vào **Gradle incremental build và up-to-date checking**. Nó cũng phân biệt với **incremental task action** dùng `InputChanges`, **Java incremental compilation**, **build cache** và **configuration cache**.

## 2. Phân biệt năm cơ chế thường bị gọi chung là “build tăng dần”

| Cơ chế | Điều Gradle tối ưu | Dấu hiệu quan sát | Điều kiện |
| --- | --- | --- | --- |
| **Up-to-date checking** | Không thực thi task khi inputs/outputs không đổi | `UP-TO-DATE` | Task có inputs/outputs được mô hình hóa đúng, đã có lịch sử |
| **Incremental task processing** | Khi task cần chạy, chỉ xử lý **files thay đổi** | Task action vẫn chạy; log `ADDED/MODIFIED/REMOVED` nếu tự ghi | `@Incremental`/`@SkipWhenEmpty` + `InputChanges` |
| **Incremental Java compilation** | JavaCompile có thể chỉ compile phần source/classes chịu ảnh hưởng | `compileJava` thực thi nhưng compiler xử lý ít nguồn hơn | Java plugin, incremental compiler, source/classpath analysis |
| **Build cache** | Tải lại output của task cacheable từ lần build trước | `FROM-CACHE` | Task cacheable + cache enabled + key match |
| **Configuration cache** | Tái sử dụng Gradle task graph/configuration | Thông báo configuration cache reused | `--configuration-cache` và build logic tương thích |

**Ba tình huống hoàn toàn khác nhau:**

- `:renderGreeting UP-TO-DATE`: action **không chạy**, vì Gradle tin outputs hiện tại đã đúng.
- `:renderGreeting` (không có nhãn đặc biệt): action **đã thực thi**; bản thân task có thể làm toàn bộ công việc hoặc chỉ xử lý file delta, tùy implementation.
- `:renderGreeting FROM-CACHE`: action **không chạy** vì Gradle phục hồi outputs từ build cache.

Một task vừa thực thi **không đồng nghĩa** nó đã xử lý toàn bộ inputs. Một task `UP-TO-DATE` **không đồng nghĩa** code chưa từng được biên dịch: nó có thể đã biên dịch từ lần trước. Và `FROM-CACHE` không phải một tên khác của `UP-TO-DATE`.

## 3. Gradle quyết định `UP-TO-DATE` dựa vào đâu?

Trước khi task chạy, Gradle xác định các inputs đã khai báo: file contents/paths đã chuẩn hóa, properties, implementation và những dữ liệu khác có liên quan. Sau một lần thực thi thành công, Gradle lưu thông tin về inputs và outputs. Ở lần chạy kế tiếp, nếu fingerprints phù hợp và declared outputs vẫn hợp lệ, task có thể được bỏ qua.

Ví dụ một task:

```text
src/main/config/greeting.txt  --> renderGreeting --> build/generated/greeting.txt
          input file                                  output file
                 +---- prefix="MESSAGE=" @Input ----+
```

Nếu input là `Hello Gradle`, prefix là `MESSAGE=` và output đã tạo đúng `MESSAGE=HELLO GRADLE`, lần sau không đổi không cần chạy lại.

| Sự kiện | Task có cần xử lý lại? | Vì sao? |
| --- | --- | --- |
| Chạy lần đầu, chưa có output | Có | Chưa có previous task output/history |
| Chạy lần hai, không đổi | Thường không | Up-to-date check thành công |
| Đổi bytes file input | Có | Input fingerprint đổi |
| Đổi `prefix` đã khai báo là `@Input` | Có | Input value đổi |
| Đổi file README ngoài inputs | Thường không | Task không phụ thuộc README |
| Xóa declared output | Có, hoặc phục hồi từ cache nếu bật | Output không còn đúng trạng thái |
| Chỉnh nội dung declared output bằng tay | Có | Output fingerprint không khớp |
| Đổi task implementation | Thường có | Logic thực thi ảnh hưởng validity/cache key |
| Thêm file không thuộc input file tree | Thường không | File không nằm trong tracked inputs |
| Gọi `--rerun-tasks` | Có | Cố ý bỏ qua up-to-date checks |
| Gọi `clean` | Xóa outputs trong build directory | Không còn local outputs để xét up-to-date |
| Bật `--build-cache` sau clean | Có thể `FROM-CACHE` | Output hợp lệ được lấy lại từ cache |

**Quan trọng:** “Thường” thể hiện Gradle có nhiều yếu tố khác: task implementation, compiler options, environment/toolchain, config inputs, Gradle version, previous execution history và shared output correctness. Kết quả thật phải dựa vào logs và inspect files của chính build đó.

## 4. Điều kiện khoa học cho một phép thử sạch

Trước khi thử, chuẩn bị:

- **Một checkout hoặc sandbox riêng**, không sửa repository production tùy tiện.
- Gradle Wrapper thực được commit (hoặc tạo một lần bằng Gradle cài sẵn), kiểm `./gradlew --version`.
- JDK 17 khả dụng, project plugin/toolchain tương thích.
- Giữ **cùng working directory, cùng task names, cùng flags** giữa lần 1 và lần 2.
- Không chỉnh build scripts, `gradle.properties`, JDK/toolchain hoặc dependency versions giữa hai lần baseline.
- Không bật build cache trong thí nghiệm up-to-date đầu tiên: dùng `--no-build-cache`.
- Không dùng `--rerun-tasks` trong phép đo chính.
- Không để IDE/formatter/autogenerator sửa cùng input trong lúc kiểm.
- Thay đúng một file/giá trị mỗi lần; ghi lại nội dung trước và sau.
- Không suy thời gian tuyệt đối vì Gradle Daemon warm-up, filesystem, CPU, antiviruses và caches có thể làm thời gian thay đổi dù task graph giống nhau.

**Giả thuyết cần kiểm:**

- H1: input/output giữ nguyên ⇒ `renderGreeting` ở lần 2 là `UP-TO-DATE`.
- H2: chỉ thay `greeting.txt` ⇒ `renderGreeting` chạy lại, output đổi tương ứng.
- H3: chỉ thay README ngoài inputs ⇒ `renderGreeting` vẫn `UP-TO-DATE`.
- H4: chỉ thay `prefix` ⇒ `renderGreeting` chạy lại.
- H5: xóa/sửa output ⇒ task không được báo `UP-TO-DATE` sai.
- H6: Java resource thay đổi ⇒ `processResources` và `jar` bị ảnh hưởng, còn `compileJava` không cần recompile nếu code/compiler classpath giữ nguyên.

Chỉ khi observations phù hợp các giả thuyết, có bằng chứng tốt về **khai báo inputs/outputs và task wiring**. Nó vẫn chưa chứng minh toàn bộ monorepo không có hidden inputs.

## 5. Demo đầy đủ: một custom task với inputs/outputs rõ ràng

Dùng **Gradle Kotlin DSL**, Java plugin để có `clean` và `compileJava` ở phần sau, thêm custom task xử lý text. Đoạn task dùng managed properties và annotations chính thức của Gradle; không cần thêm third-party Gradle plugin.

### 5.1. Cây thư mục

```text
incremental-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── data/
│   └── greeting.txt
├── src/
│   └── main/
│       ├── java/demo/Main.java
│       └── resources/banner.txt
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
```

Hai phần thực hành trong cùng project nhưng **độc lập về task inputs**:

- `renderGreeting` chỉ phụ thuộc `data/greeting.txt` và property `prefix`, tạo `build/generated/greeting.txt`.
- Java plugin `compileJava`/`processResources`/`jar` dùng `src/main/java`/`src/main/resources`.

Điều này giúp làm một **thay đổi có kiểm soát** và quan sát task nào không liên quan vẫn up to date.

### 5.2. `settings.gradle.kts`

```kotlin
rootProject.name = "incremental-lab"
```

### 5.3. Toàn bộ `build.gradle.kts`

```kotlin
import java.nio.charset.StandardCharsets
import java.util.Locale

import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.JavaExec

plugins {
    java
}

group = "org.example"
version = "1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

// Type có thể chuyển sang build-logic/buildSrc khi muốn tái sử dụng.
@CacheableTask
abstract class RenderGreetingTask : DefaultTask() {

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val greetingFile: RegularFileProperty

    @get:Input
    abstract val prefix: Property<String>

    @get:OutputFile
    abstract val resultFile: RegularFileProperty

    @TaskAction
    fun render() {
        val inputText = greetingFile.get().asFile
            .readText(StandardCharsets.UTF_8)
            .trimEnd('\r', '\n')

        val rendered =
            prefix.get() + inputText.uppercase(Locale.ROOT) + "\n"

        val output = resultFile.get().asFile
        output.parentFile.mkdirs()
        output.writeText(rendered, StandardCharsets.UTF_8)

        logger.lifecycle("RENDER_GREETING_EXECUTED")
    }
}

tasks.register<RenderGreetingTask>("renderGreeting") {
    group = "verification"
    description = "Turns one controlled text input into a report"

    greetingFile.set(
        layout.projectDirectory.file("data/greeting.txt")
    )

    prefix.set(
        providers.gradleProperty("messagePrefix")
            .orElse("MESSAGE=")
    )

    resultFile.set(
        layout.buildDirectory.file("generated/greeting.txt")
    )
}

tasks.register<JavaExec>("runApp") {
    group = "application"
    description = "Runs the small Java 17 example"
    mainClass.set("demo.Main")
    classpath = sourceSets.main.get().runtimeClasspath
}
```

**Tại sao đây là build script đầy đủ?**

1. `plugins { java }` tạo tasks Java compilation, `classes`, `jar`, `check`, `build` và `clean`.
2. `java.toolchain=17` chọn compiler Java 17, không bắt máy phải chạy Gradle Daemon bằng chính JDK 17 nếu Gradle compatibility cho phép JDK khác.
3. `@CacheableTask` cho phép Gradle build cache lưu/phục hồi outputs của task khi cache được bật; **không bật cache mặc định**.
4. `greetingFile` là `RegularFileProperty` có `@InputFile`; đối với **một file**, `PathSensitivity.NONE` nói file path không ảnh hưởng nội dung output, phù hợp vì code chỉ đọc bytes.
5. `prefix` là `Property<String>` có `@Input`. Thay prefix cũng phải làm task chạy lại dù file không đổi.
6. `resultFile` là `@OutputFile`; Gradle biết file phải tồn tại và không được vô tình thay đổi.
7. `render()` chỉ đọc declared inputs, viết declared output; output deterministic nếu cùng input bytes/prefix/implementation.
8. `Locale.ROOT` tránh uppercase phụ thuộc locale máy (đặc biệt với chữ cái có uppercase đặc thù).
9. `trimEnd('\r', '\n')` loại newline cuối để output luôn có đúng một `\n`; demo dùng input một dòng.
10. `logger.lifecycle(...)` là **dấu hiệu action thật sự chạy**; khi task `UP-TO-DATE` hoặc `FROM-CACHE`, dòng đó không được in bởi task action.
11. `providers.gradleProperty("messagePrefix").orElse("MESSAGE=")` giữ property lazy, cho phép dùng CLI `-PmessagePrefix=...` làm thí nghiệm.
12. `resultFile.set(layout.buildDirectory.file(...))` đặt output ổn định, không hardcode đường tuyệt đối.
13. `runApp` là `JavaExec` dùng Java source set runtimeClasspath, không cần runnable JAR.
14. `renderGreeting` **không tự nằm trong `build`**. Ta gọi trực tiếp để chứng minh độc lập; nếu muốn CI chạy cùng build, plugin/lifecycle phải nối task rõ ràng theo chính sách.

### 5.4. File input ban đầu `data/greeting.txt`

```text
Hello Gradle
```

Lưu **UTF-8 không BOM** với một newline cuối. Nếu editor tạo CRLF, hàm `trimEnd` vẫn cho cùng nội dung logic; nhưng file bytes khác có thể khiến Gradle nhận input change và rerun. Đó là hành vi hợp lý vì content fingerprint đã đổi.

### 5.5. Java source `src/main/java/demo/Main.java`

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        try (InputStream input =
                 Main.class.getResourceAsStream("/banner.txt")) {
            if (input == null) {
                throw new IOException("Missing banner.txt");
            }

            String banner = new String(
                input.readAllBytes(), StandardCharsets.UTF_8
            ).trim();

            System.out.println("BANNER=" + banner);
            System.out.println("SUM=" + Math.addExact(2, 3));
        }
    }
}
```

Code dùng Java 17-compatible APIs, không cần thư viện ngoài. `Main.class.getResourceAsStream` đọc **classpath resource** do Gradle `processResources` tạo, không đọc trực tiếp file ở source directory khi runtime.

### 5.6. Resource ban đầu `src/main/resources/banner.txt`

```text
Hello Resource
```

Khi chạy `runApp`, stdout chương trình ban đầu là:

```text
BANNER=Hello Resource
SUM=5
```

**Các dòng trên chỉ là stdout do `Main.main` tạo**, không phải toàn bộ Gradle console output. Khi dùng `./gradlew -q runApp`, Gradle thường chỉ in stdout của app và những warnings cần thiết; không nên kiểm một console transcript tùy phiên bản thay cho kiểm output.

## 6. Thực nghiệm A — lần build đầu tạo output

Linux/macOS, tại root project:

```bash
./gradlew --version
./gradlew clean renderGreeting --no-build-cache --console=plain
cat build/generated/greeting.txt
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat clean renderGreeting --no-build-cache --console=plain
Get-Content build\generated\greeting.txt
```

**Đầu ra chính xác của file `build/generated/greeting.txt`**:

```text
MESSAGE=HELLO GRADLE
```

Trong output Gradle, tìm dấu hiệu:

```text
> Task :renderGreeting
RENDER_GREETING_EXECUTED
```

Đây là **trích đoạn mong đợi**, không phải toàn bộ log. Gradle có thể in `clean`, startup messages, deprecation notes hoặc số lượng actionable tasks.

**Dữ liệu cần ghi nhận:**

- File `data/greeting.txt` đang chứa `Hello Gradle`.
- Property `messagePrefix` đang dùng default `MESSAGE=`.
- File output tồn tại, nội dung một dòng đúng.
- `renderGreeting` có task action được thực thi, dấu `RENDER_GREETING_EXECUTED` xuất hiện.
- Không bật build cache vì dùng `--no-build-cache`.
- Không cần `compileJava` vì `renderGreeting` không phụ thuộc Java source set.

Lần đầu sau `clean` thường phải chạy action vì output đã bị xóa. Nếu build outputs tồn tại ở nơi khác/đã được Gradle khôi phục bởi cơ chế khác, kiểm task graph và flags thay vì kết luận dựa vào một thời gian chạy.

## 7. Thực nghiệm B — chạy lại y hệt, không đổi bất cứ input nào

**Không dùng `clean` trong lần 2. Không sửa input, output, build script hoặc Gradle flags.**

Linux/macOS:

```bash
./gradlew renderGreeting --no-build-cache --console=plain
cat build/generated/greeting.txt
```

PowerShell:

```powershell
.\gradlew.bat renderGreeting --no-build-cache --console=plain
Get-Content build\generated\greeting.txt
```

Outcome kỳ vọng:

```text
> Task :renderGreeting UP-TO-DATE
```

File output vẫn có:

```text
MESSAGE=HELLO GRADLE
```

**Điểm kiểm chứng không phải “task được gọi lại” mà là action không chạy**: dòng `RENDER_GREETING_EXECUTED` không xuất hiện ở lần 2. Gradle vẫn đánh giá task state nhưng tránh thực thi `@TaskAction`.

Nếu không có `UP-TO-DATE`:

1. Kiểm lệnh có vô tình kèm `clean`, `--rerun-tasks` hoặc đổi `-PmessagePrefix` không.
2. Kiểm file input/output có bị IDE, antivirus, code generator hoặc script khác sửa không.
3. Chạy `--info` để xem “Task ... is not up-to-date because ...”.
4. Kiểm buildscript/task implementation thay đổi không.
5. Kiểm annotated properties có đúng `@InputFile`, `@Input`, `@OutputFile` không.
6. Kiểm output file có bị delete/modify sau lần đầu không.
7. Kiểm Gradle task validation problems; chúng có thể disable optimizations.

Không lấy task `build`/`check` không có action làm thước đo. Task lifecycle có thể báo trạng thái khác tùy Gradle version; chọn **task thực sự có declared outputs** để kiểm chứng.

## 8. Thực nghiệm C — thay đúng một input, chạy lại

Giờ chỉ đổi `data/greeting.txt` từ:

```text
Hello Gradle
```

sang:

```text
Hello Java
```

Không sửa bất cứ file nào khác. Hai chuỗi có độ dài khác nhau giúp dễ phân biệt cả khi filesystem timestamp resolution thấp.

Linux/macOS:

```bash
printf 'Hello Java\n' > data/greeting.txt
./gradlew renderGreeting --no-build-cache --console=plain
cat build/generated/greeting.txt
```

PowerShell 5.1+:

```powershell
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'data\greeting.txt'),
    "Hello Java" + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
.\gradlew.bat renderGreeting --no-build-cache --console=plain
Get-Content build\generated\greeting.txt
```

Dùng `WriteAllText` với UTF-8 không BOM thay vì `Set-Content` mặc định của Windows PowerShell 5.1, vốn có thể tạo BOM/encoding khác ý định. Nếu PowerShell phiên bản mới dùng UTF-8 mặc định, `WriteAllText` vẫn loại bỏ sự mơ hồ về encoding.

Outcome kỳ vọng:

```text
> Task :renderGreeting
RENDER_GREETING_EXECUTED
```

Output file **phải đổi** thành:

```text
MESSAGE=HELLO JAVA
```

**Bằng chứng đã thuyết phục gồm cả hai:**

- Task thực thi lại vì declared input đổi.
- Nội dung output phản ánh **đúng** input mới, không bị stale.

Chỉ thấy task thực thi **chưa đủ**: action có thể chạy nhưng viết output sai. Chỉ thấy output đổi **chưa đủ**: có thể một process khác viết đè file. Cần kết hợp task outcome, input diff và output content.

### 8.1. Lần 4 — không đổi sau lần sửa

```bash
./gradlew renderGreeting --no-build-cache --console=plain
```

Kỳ vọng:

```text
> Task :renderGreeting UP-TO-DATE
```

Lần thứ tư chứng minh Gradle đã ghi nhận new input/output fingerprints sau lần thứ ba. Nếu task cứ chạy mọi lần, cần tìm một input hoặc output không ổn định.

### 8.2. Bảng kết quả chuẩn

| Lượt | File `greeting.txt` | Prefix | Expected `renderGreeting` | File output |
| --- | --- | --- | --- | --- |
| 1 | `Hello Gradle` | `MESSAGE=` | Executed | `MESSAGE=HELLO GRADLE` |
| 2 | Không đổi | Không đổi | `UP-TO-DATE` | `MESSAGE=HELLO GRADLE` |
| 3 | `Hello Java` | Không đổi | Executed | `MESSAGE=HELLO JAVA` |
| 4 | Không đổi | Không đổi | `UP-TO-DATE` | `MESSAGE=HELLO JAVA` |
| 5 | Không đổi | `NOTE=` | Executed | `NOTE=HELLO JAVA` |
| 6 | Không đổi | `NOTE=` | `UP-TO-DATE` | `NOTE=HELLO JAVA` |

**Lưu ý:** bảng này thể hiện baseline khi cache disabled và chỉ một process dùng workspace. Nếu dùng build cache, một lượt sau khi output mất có thể `FROM-CACHE` thay vì executed.

## 9. Thực nghiệm D — đổi `@Input` không phải file

Task còn có property `prefix`, được đánh dấu `@Input`. Vì vậy dù `data/greeting.txt` không đổi, thay prefix phải khiến task chạy lại:

```bash
./gradlew renderGreeting -PmessagePrefix=NOTE= \
  --no-build-cache --console=plain
cat build/generated/greeting.txt
```

PowerShell:

```powershell
.\gradlew.bat renderGreeting -PmessagePrefix=NOTE= --no-build-cache --console=plain
Get-Content build\generated\greeting.txt
```

Kết quả file:

```text
NOTE=HELLO JAVA
```

Nếu chạy lại **cùng** `-PmessagePrefix=NOTE=`:

```text
> Task :renderGreeting UP-TO-DATE
```

Nếu sau đó **bỏ `-PmessagePrefix`**, task input trở về default `MESSAGE=`, nên thường chạy lại và output trở về `MESSAGE=HELLO JAVA`.

Điều này chứng minh Gradle theo dõi **giá trị input**, không chỉ files. Ví dụ tương tự áp dụng cho compiler flags, target Java version, environment variables được khai báo qua Providers hoặc task options ảnh hưởng outputs.

**Không đặt property quan trọng trong `System.getenv(...)` chỉ bên trong task action** mà quên `@Input`. Nếu output phụ thuộc environment nhưng Gradle không biết, up-to-date checking có thể bỏ qua một thay đổi có ý nghĩa.

## 10. Thực nghiệm E — negative control: thay một file không phải input

Sau khi đã chạy với default `MESSAGE=` trở lại, tạo/chỉnh `README.md`, trong khi custom task **không đọc README**:

Linux/macOS:

```bash
printf 'Notes for incremental lab\n' > README.md
./gradlew renderGreeting --no-build-cache --console=plain
```

PowerShell:

```powershell
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'README.md'),
    "Notes for incremental lab" + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
.\gradlew.bat renderGreeting --no-build-cache --console=plain
```

Kỳ vọng task vẫn `UP-TO-DATE`, **nếu không có plugin/configuration bổ sung nào khai báo README là input hoặc làm đổi task implementation/configuration**.

Không nên đưa `inputs.dir(projectDir)` bừa bãi vào custom task: nó có thể khiến mọi file trong project, kể cả outputs, README, IDE caches hay Git metadata, trở thành inputs. Khi đó unrelated changes sẽ tạo cache misses và thậm chí output-in-input feedback loop.

**Quy tắc:** input phạm vi hẹp phản ánh **tất cả và chỉ những giá trị ảnh hưởng output**. Quá thiếu input gây stale output; quá nhiều input gây unnecessary rerun.

## 11. Thực nghiệm F — xóa hoặc can thiệp vào declared output

Task cũng theo dõi `build/generated/greeting.txt` vì được khai báo `@OutputFile`. Trên một workspace sạch sau khi baseline đã ổn định, xóa riêng file đó:

Linux/macOS:

```bash
rm build/generated/greeting.txt
./gradlew renderGreeting --no-build-cache --console=plain
cat build/generated/greeting.txt
```

PowerShell:

```powershell
Remove-Item -LiteralPath build\generated\greeting.txt
.\gradlew.bat renderGreeting --no-build-cache --console=plain
Get-Content build\generated\greeting.txt
```

Với build cache disabled, Gradle không thể đánh dấu task `UP-TO-DATE` dựa trên một output bị mất; action dự kiến chạy lại để tạo file.

Một thử nghiệm khác là **sửa bytes output trực tiếp** rồi gọi lại task. Task có thể được thực thi lại vì output fingerprint không khớp. Nhưng tuyệt đối **không chỉnh output production để “kích hoạt” task một cách tùy tiện**; đây chỉ là bài test về correctness trong sandbox.

**Điểm cần nhớ:** nếu task không khai báo output, Gradle không có đủ cơ sở để bỏ qua công việc và kiểm correctness của output. Nếu một task tạo nhiều files nhưng chỉ khai báo một phần, cơ chế tracking/caching có thể đưa ra quyết định sai.

## 12. Bài thực hành Java 17: source đổi và resource đổi tác động khác nhau

Custom task `renderGreeting` cho bạn quan sát một input rõ ràng. Bây giờ dùng **Gradle Java plugin** để kiểm tra phản ứng có chọn lọc của task graph:

```text
src/main/java/demo/Main.java
        |
        v
     compileJava ------> build/classes/java/main/demo/Main.class
        |
        +--------+
                 |
src/main/resources/banner.txt
        |        |
        v        v
  processResources --> build/resources/main/banner.txt
                 |
                 v
               classes
                 |
                 v
                jar --> build/libs/incremental-lab-1.0.jar
```

Đây là **sơ đồ khái niệm**, không phải danh sách dependencies theo đúng thứ tự của mọi Gradle version. `jar` có main source set outputs làm inputs; Java/plugin wiring xử lý compiler/resources producer tasks tương ứng.

### 12.1. Baseline Java build lần 1

```bash
./gradlew clean jar --no-build-cache --console=plain
./gradlew -q runApp
```

PowerShell:

```powershell
.\gradlew.bat clean jar --no-build-cache --console=plain
.\gradlew.bat -q runApp
```

Khi dependencies/toolchain hợp lệ, các tasks liên quan `compileJava`, `processResources` và `jar` sẽ tạo outputs. Stdout **của Java `Main`** là:

```text
BANNER=Hello Resource
SUM=5
```

Lệnh `runApp` là JavaExec task do build script tạo, **không phải Java plugin built-in `run`**. Nó dùng runtimeClasspath nên tự có class/resources của main source set.

### 12.2. Baseline Java build lần 2, không đổi

```bash
./gradlew jar --no-build-cache --console=plain
```

Kỳ vọng các work tasks có declared outputs phù hợp như:

```text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :jar UP-TO-DATE
```

Đây là **các task lines chọn lọc**, không phải transcript đầy đủ. `classes`/`assemble` là lifecycle tasks và có thể có outcome khác do không có action hoặc Gradle version. Tập trung vào **work tasks** ở trên.

### 12.3. Chỉ sửa Java resource, không sửa source

Đổi nội dung duy nhất của `src/main/resources/banner.txt` thành:

```text
Hello Updated
```

Linux/macOS:

```bash
printf 'Hello Updated\n' > src/main/resources/banner.txt
./gradlew jar --no-build-cache --console=plain
./gradlew -q runApp
```

PowerShell:

```powershell
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'src\main\resources\banner.txt'),
    "Hello Updated" + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
.\gradlew.bat jar --no-build-cache --console=plain
.\gradlew.bat -q runApp
```

**Kỳ vọng chọn lọc:**

| Task | Outcome dự kiến | Vì sao |
| --- | --- | --- |
| `compileJava` | `UP-TO-DATE` | Java source/compile classpath không đổi |
| `processResources` | Executed | Resource content đổi |
| `classes` | Lifecycle | Phụ thuộc compilation/resources outcomes |
| `jar` | Executed | Contents của JAR thay đổi do resource đổi |
| `runApp` | Executed khi gọi | JavaExec chạy chương trình; không phải compile task |

Stdout từ `Main.main`:

```text
BANNER=Hello Updated
SUM=5
```

**Không được kết luận resource change phải kích hoạt Java compilation.** Với Java plugin baseline, resources nằm trong processed resource outputs và không phải input của `compileJava`. Nếu project thật có generated Java source từ resources, annotation processors hoặc task graph bổ sung, phụ thuộc có thể khác; hãy xem graph thay vì khẳng định tuyệt đối.

### 12.4. Chỉ sửa Java source, không sửa resource

Trong `Main.java`, sửa đúng một chỗ:

```java
// Trước:
System.out.println("SUM=" + Math.addExact(2, 3));

// Sau:
System.out.println("SUM=" + Math.addExact(2, 4));
```

Chạy:

```bash
./gradlew jar --no-build-cache --console=plain
./gradlew -q runApp
```

Kỳ vọng:

- `compileJava` thực thi vì Java source thay đổi.
- `processResources` vẫn `UP-TO-DATE` vì `banner.txt` không đổi.
- `jar` thực thi do compiled class output thay đổi.
- Java stdout đổi thành:

```text
BANNER=Hello Updated
SUM=6
```

**Cẩn thận:** Java compiler có thể compile **chỉ những classes bị ảnh hưởng**, tùy dependency analysis. `compileJava` không có `UP-TO-DATE` không chứng minh **toàn bộ Java source files** đều được biên dịch lại. Đó là khác biệt giữa **task-level incremental build** và **incremental compilation bên trong JavaCompile**.

### 12.5. Chạy lại sau Java change

```bash
./gradlew jar --no-build-cache --console=plain
```

Các tasks `compileJava`, `processResources` và `jar` thường sẽ `UP-TO-DATE` khi input/output ổn định. Nếu `jar` chạy lại dù source không đổi, kiểm manifest metadata, generated files, archive timestamp/order settings, task inputs và plugin logic thay vì cho rằng JavaCompile luôn có lỗi.

## 13. Phân biệt `UP-TO-DATE` và build cache bằng một thử nghiệm riêng

Sau khi hoàn thành phép thử với `--no-build-cache`, bạn có thể kiểm build cache. Gradle build cache mặc định có thể được bật bằng `--build-cache` hoặc `org.gradle.caching=true`; không phải mọi task đều cacheable.

Task `RenderGreetingTask` được đánh dấu `@CacheableTask`. Một cách thử:

```bash
./gradlew renderGreeting --build-cache --console=plain
./gradlew clean --console=plain
./gradlew renderGreeting --build-cache --console=plain
```

Nếu cache đã lưu được kết quả, inputs/task implementation/cache key khớp và Gradle local cache khả dụng, lần sau `clean` có thể hiển thị:

```text
> Task :renderGreeting FROM-CACHE
```

Nhưng **không được coi `FROM-CACHE` là điều tất yếu**:

- Task phải cacheable, không bị disable caching.
- Build cache phải được bật và có entry phù hợp.
- Inputs, implementation/classpath và relevant environment phải khớp.
- Cache entry không bị eviction/cleanup.
- Task output metadata hợp lệ.
- Nếu Gradle nhận classloader/implementation không thể được snapshot, caching có thể bị tắt.
- Gradle có thể thực thi task thay vì FROM-CACHE nếu cache miss.
- Nếu output vẫn hiện diện và không đổi, task có thể `UP-TO-DATE` trước khi cần lookup cache.

Trong thí nghiệm chính luôn dùng `--no-build-cache` để phân biệt “task không chạy do up-to-date state” và “task không chạy vì được phục hồi từ cache”.

### 13.1. JavaCompile và Jar không có cùng cacheability

Theo Gradle Build Cache docs, `JavaCompile` là một task type có hỗ trợ build cache. `Jar`/`Copy` thường là thao tác đóng gói/copy và **không được cacheable mặc định** vì thường rẻ hơn phục hồi cache. Vì thế sau `clean jar --build-cache` bạn có thể thấy `compileJava FROM-CACHE` nhưng `jar` vẫn thực thi.

**Đừng viết policy bắt mọi task xuất hiện `FROM-CACHE`.** Mục tiêu là correctness và tiết kiệm thời gian hợp lý, không phải một tỉ lệ cache hit bằng 100% bằng cách đánh dấu bừa tasks là cacheable.

### 13.2. Configuration cache không thay thế up-to-date

```bash
./gradlew renderGreeting --configuration-cache --no-build-cache
./gradlew renderGreeting --configuration-cache --no-build-cache
```

Configuration cache giúp Gradle reuse configured task graph nếu compatible. Task `renderGreeting` vẫn có thể `UP-TO-DATE`, nhưng đó là **một cơ chế khác**. Không suy vì console ghi `configuration cache reused` nên compiled outputs đã được cache hoặc mọi task action đều không chạy.

## 14. `--info`: điều tra vì sao Gradle chạy lại

Khi một task không `UP-TO-DATE` dù kỳ vọng, dùng:

```bash
./gradlew renderGreeting --no-build-cache --info --console=plain
```

Các kiểu lý do thường gặp:

- “Task has not declared any outputs despite executing actions”.
- “No history is available”.
- “Input property ... has changed”.
- “Output property ... file has been removed”.
- “Task ... is not up-to-date because ...”.
- Build script/task implementation classpath changed.
- Task property validation problem.

**Đó là các dạng thông báo minh họa**, wording cụ thể phụ thuộc Gradle version. Không chỉ grep một chuỗi tiếng Anh cố định; tìm phần lý do Gradle báo về task chính xác.

Nếu một task có outputs nhưng không được tối ưu, xem:

1. Có getter thiếu annotation `@Input`/`@Internal`?
2. File input có khai báo `@PathSensitive`/normalization phù hợp?
3. Task có đọc file khác ngoài `greetingFile` không?
4. File output có nằm ngoài declared output property không?
5. Task có action side effect khiến Gradle coi state tracking không khả dụng?
6. Có plugin nào thêm `outputs.upToDateWhen { false }` không?
7. Task có `doNotTrackState`/`@UntrackedTask`?
8. Có inputs from environment mà task không khai báo?
9. Có task khác ghi chung output path không?
10. File được generate bởi task khác nhưng dependency/provider relationship thiếu?

**Đừng sử dụng `--debug` vô điều kiện trong CI chứa secrets.** Debug logs có thể chứa cấu hình/repository details; ưu tiên `--info` và redaction.

## 15. Incremental action với `InputChanges`: khi task đã phải chạy, xử lý file nào?

Thí nghiệm `renderGreeting` vừa rồi chỉ có **một input file**. Mỗi khi input đổi, task action xử lý file đó; nó không cần `InputChanges`. Với một task xử lý **hàng nghìn files**, cần loại tối ưu khác: task vẫn chạy khi có đổi, nhưng chỉ xử lý files bị thêm/sửa/xóa.

Theo Gradle, một **incremental task action**:

- Có một tham số `InputChanges` trong method gắn `@TaskAction`.
- Khai báo ít nhất một file input `@Incremental` hoặc `@SkipWhenEmpty`.
- Dùng `changes.getFileChanges(inputDir)` để lấy `ADDED`, `MODIFIED`, `REMOVED`.
- Kiểm `changes.isIncremental`. Khi false, phải xử lý **toàn bộ inputs** như một lượt xây lại.
- Quản lý outputs tương ứng với files bị xóa, nếu không có stale files.
- Khi task đã `UP-TO-DATE`, action **không chạy**, nên không in file changes.

### 15.1. Full example: incremental uppercase mỗi file

Đây là **một task class bổ sung**, có thể chèn vào `build.gradle.kts` sau các imports cần thiết, rồi đăng ký task `uppercaseFiles`. Nó sử dụng Java/Kotlin APIs của Gradle:

```kotlin
import java.io.File
import java.util.Locale
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.FileType
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.ChangeType
import org.gradle.work.Incremental
import org.gradle.work.InputChanges

abstract class UppercaseFilesTask : DefaultTask() {

    @get:Incremental
    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val inputDir: DirectoryProperty

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun convert(changes: InputChanges) {
        val targetRoot = outputDir.get().asFile

        // Khi không có previous history hoặc output bị thay đổi,
        // Gradle có thể yêu cầu non-incremental processing.
        if (!changes.isIncremental) {
            targetRoot.deleteRecursively()
            targetRoot.mkdirs()
        }

        for (change in changes.getFileChanges(inputDir)) {
            if (change.fileType == FileType.DIRECTORY) continue

            val target = File(targetRoot, change.normalizedPath)

            if (change.changeType == ChangeType.REMOVED) {
                target.delete()
            } else {
                target.parentFile.mkdirs()
                target.writeText(
                    change.file.readText(Charsets.UTF_8)
                        .uppercase(Locale.ROOT),
                    Charsets.UTF_8
                )
            }

            logger.lifecycle(
                "FILE_CHANGE {} {}",
                change.changeType, change.normalizedPath
            )
        }
    }
}

tasks.register<UppercaseFilesTask>("uppercaseFiles") {
    inputDir.set(layout.projectDirectory.dir("docs/input"))
    outputDir.set(layout.buildDirectory.dir("docs/output"))
}
```

**Lưu ý khi thêm vào baseline:** nhóm `import` phải đặt ở **đầu file `build.gradle.kts`**; không copy nguyên block imports vào giữa plugin/tasks definitions trong một Kotlin source file. Bạn có thể chuyển class này sang `build-logic` hoặc `buildSrc` khi dùng ở nhiều modules. Hai task `renderGreeting` và `uppercaseFiles` hoạt động độc lập.

**Giới hạn của demo:** task chỉ đọc text files trong directory `docs/input`; không xử lý binary files. `deleteRecursively()` chỉ được dùng cho **outputDir do chính task sở hữu**, không trỏ output vào project root hoặc shared directory để tránh xóa nhầm. `@PathSensitive(RELATIVE)` giữ đường tương đối để biết output file tương ứng; với input dir nhiều files, `PathSensitivity.NONE` có thể làm Gradle không xác định file paths như bạn kỳ vọng.

### 15.2. Thí nghiệm với hai file

Tạo:

```text
docs/input/a.txt   -> apple
docs/input/b.txt   -> banana
```

Chạy:

```bash
./gradlew uppercaseFiles --no-build-cache --console=plain
./gradlew uppercaseFiles --no-build-cache --console=plain
```

Lần 1 (không có history) `changes.isIncremental` thường false, Gradle báo từng file như `ADDED` để task xử lý toàn bộ. Lần 2 không đổi ⇒ task `UP-TO-DATE`; `convert(...)` không được gọi.

Sửa **chỉ `docs/input/a.txt`** thành `apricot` rồi gọi:

```bash
./gradlew uppercaseFiles --no-build-cache --console=plain
```

Lượt này, nếu incremental state hợp lệ, action chạy với `changes.isIncremental=true` và phần thay đổi thường chỉ có `MODIFIED a.txt`. `b.txt` không cần xử lý lại; output `build/docs/output/b.txt` vẫn là `BANANA`. Nếu xóa `b.txt`, input change sẽ có `REMOVED b.txt` và task xóa output tương ứng.

**Không khẳng định mọi lượt có đúng `MODIFIED`:** nếu thiếu execution history, output bị xóa/chỉnh, đổi non-file input hoặc thay task implementation, Gradle có thể buộc non-incremental execution và trả tất cả files như `ADDED`. Đó là hành vi được `InputChanges` API mô tả.

## 16. Thế nào là kiểm chứng chính xác, không dựa vào thời gian?

Một phép thử tốt có **oracle**, tức kỳ vọng có thể kiểm bằng dữ liệu:

| Thí nghiệm | Oracle task outcome | Oracle outputs |
| --- | --- | --- |
| `renderGreeting` lần đầu | Action executed | `MESSAGE=HELLO GRADLE` |
| Lần hai không đổi | `UP-TO-DATE` | Giống baseline |
| Đổi input sang Hello Java | Action executed | `MESSAGE=HELLO JAVA` |
| Chạy lại không đổi | `UP-TO-DATE` | Giống lần 3 |
| Chỉ đổi `README.md` | `UP-TO-DATE` | Không đổi |
| Đổi `messagePrefix` | Action executed | Prefix mới được dùng |
| Xóa output | Action executed khi cache tắt | Output được tái tạo |
| Java resource change | `processResources` và `jar` chạy | JAR/resource đổi; compileJava thường up-to-date |
| Java source change | `compileJava` và `jar` chạy | Bytecode/Java output đổi |
| Lần nữa sau clean có cache hit | Có thể `FROM-CACHE` | Output tương ứng cache key |
| `uppercaseFiles` một file đổi | Incremental action (nếu state hợp lệ) | Chỉ output liên quan đổi |

**Không dùng performance làm oracle chính.** Một build 1,5 giây so với 1 giây không chứng minh task inputs/outputs được khai báo đúng. Ngược lại, build nhanh hơn nhưng stale output là lỗi nghiêm trọng.

### 16.1. Kiểm kết quả bằng file content

Bash:

```bash
test "$(cat build/generated/greeting.txt)" = "MESSAGE=HELLO JAVA"
```

PowerShell:

```powershell
if ((Get-Content -Raw build\generated\greeting.txt).Trim() -ne 'MESSAGE=HELLO JAVA') {
    throw 'Rendered greeting differs from the expected value'
}
```

**Hai snippets trên chỉ áp dụng khi input đang là `Hello Java` và không dùng prefix khác.** Nếu bạn vừa chạy với `-PmessagePrefix=NOTE=`, expected string phải đổi cho phù hợp. Luôn ghi trạng thái thực của input và flags cùng assertions.

### 16.2. Hash để phân biệt output đổi hay không

Linux:

```bash
sha256sum build/generated/greeting.txt
sha256sum build/libs/incremental-lab-1.0.jar
```

macOS có thể dùng `shasum -a 256`. Windows PowerShell:

```powershell
Get-FileHash build\generated\greeting.txt -Algorithm SHA256
Get-FileHash build\libs\incremental-lab-1.0.jar -Algorithm SHA256
```

So hashes sau từng bước. Nhưng SHA-256 khác **chỉ chứng minh bytes khác**, không nói vì sao Gradle rerun. Và một task có output trùng bytes sau khi chạy lại vẫn có thể hợp lệ khi input changed nhưng transform không thay nội dung. Phải đọc inputs, task logs và outputs cùng nhau.

## 17. Một ma trận kiểm soát thay đổi để tránh kết luận sai

| Biến | Giữ nguyên trong baseline? | Khi nào thay? |
| --- | --- | --- |
| Gradle Wrapper version | Có | Không đổi giữa hai lần baseline |
| JDK/toolchain | Có | Test riêng compatibility nếu cần |
| Build script/plugin versions | Có | Test riêng tác động task implementation |
| Task name và flags | Có | `-PmessagePrefix` chỉ ở test riêng |
| Project path | Có | Không move project giữa baseline |
| File `data/greeting.txt` | Có | Chỉ ở lần 3 |
| File `README.md` | Có | Chỉ ở negative control |
| Output `build/generated/greeting.txt` | Có sau lần 1 | Chỉ ở test output corruption |
| File `src/main/resources/banner.txt` | Có | Chỉ ở Java resource test |
| Java source `Main.java` | Có | Chỉ ở Java source test |
| Build cache | Tắt trong baseline | Test riêng bằng `--build-cache` |
| Configuration cache | Tùy, giữ ổn định | Test riêng để tách cơ chế |
| Concurrent IDE/build processes | Không | Không nên tồn tại trong test |

**Một thay đổi mỗi lần** giúp gắn nguyên nhân với kết quả. Nếu vừa đổi resource, compiler args, Gradle Wrapper và cache flags, bạn không thể biết cái nào khiến JavaCompile rerun.

## 18. Tại sao `UP-TO-DATE` đôi khi không xuất hiện dù output đúng?

Có nhiều nguyên nhân hợp lệ:

1. **Task không có declared outputs:** Gradle không thể chứng minh kết quả cũ còn đúng.
2. **Task có inputs phi ổn định:** timestamp, random ID, environment value hoặc dynamic version chưa được pin.
3. **Task implementation/classpath đổi:** task action code là phần của inputs.
4. **Output bị xóa/chỉnh:** một process khác chạm declared output.
5. **Task bị cấu hình `outputs.upToDateWhen { false }`** hoặc `doNotTrackState`.
6. **File paths quá rộng:** `inputs.dir(".")` khiến logs, outputs, editor files thành inputs.
7. **File path normalization không phù hợp:** cùng bytes nhưng đường tuyệt đối khác và task dùng ABSOLUTE sensitivity.
8. **Nhiều tasks ghi chung output:** Gradle không thể xác định độc quyền/correctness.
9. **Gradle/Java/plugin/tool versions đổi:** impacts task implementation/input snapshots.
10. **Task validation warnings:** Gradle có thể tắt optimizations nếu task properties không hợp lệ.
11. **Phụ thuộc generated inputs thiếu task producer link:** task chạy với state không nhất quán.
12. **Đã dùng `--rerun-tasks` hoặc chạy `clean`** theo thói quen.
13. **File watcher / filesystem timestamp limitations:** khi metadata stat chưa đổi, một số thay đổi khó nhận diện; cần kiểm bytes/mtime trong điều kiện controlled test.
14. **Compilation task thật sự bị ảnh hưởng bởi transitive classpath change:** JavaCompile không chỉ phụ thuộc chính .java file.

### 18.1. `@InputFile` khác `@InputFiles`

- `@InputFile`: một file đơn; dùng `RegularFileProperty`.
- `@InputFiles`: nhiều files; dùng `ConfigurableFileCollection`.
- `@InputDirectory`: một directory tree; dùng `DirectoryProperty`.
- `@Classpath`: một classpath có order/ABI semantics.
- `@CompileClasspath`: Java compile classpath, cho phép normalization loại thay đổi không quan trọng tới compilation.
- `@Input`: giá trị non-file như prefix, targetVersion.
- `@OutputFile`: file output; `@OutputDirectory`: output directory.
- `@Optional`: property có thể vắng mặt, không tự biến file sai path thành hợp lệ.

Chọn đúng annotation **quan trọng hơn thêm nhiều `dependsOn`**. Gradle cần biết không chỉ tasks chạy theo thứ tự nào, mà inputs/outputs nào thực sự ảnh hưởng kết quả.

### 18.2. `PathSensitivity`

| Giá trị | Dùng khi nào? | Tác động |
| --- | --- | --- |
| `NONE` | Một file mà chỉ bytes quan trọng | Không quan tâm đường file |
| `RELATIVE` | Directory/file tree mà relative paths là một phần output mapping | Bỏ absolute root nhưng giữ relative paths |
| `NAME_ONLY` | Chỉ basename quan trọng (khá hiếm) | Có thể bỏ mất cấu trúc thư mục cần thiết |
| `ABSOLUTE` | Kết quả thực sự phụ thuộc absolute path (rất hạn chế) | Dễ gây cache misses khác máy |

Với `renderGreeting`, tên `data/greeting.txt` không xuất hiện trong output nên `NONE` đúng. Với `uppercaseFiles`, output giữ cấu trúc tương đối của inputs nên `RELATIVE` đúng.

## 19. `--rerun-tasks`, `clean` và `--refresh-dependencies` khác nhau

| Lệnh/flag | Nó tác động gì? | Dùng để kiểm điều gì? |
| --- | --- | --- |
| `--rerun-tasks` | Buộc tasks được chọn thực thi thay vì dùng up-to-date/cache | Kiểm code path/action, không để đo up-to-date |
| `clean` | Xóa Gradle build outputs | Tạo baseline không có local outputs; dùng có chủ đích |
| `--no-build-cache` | Không lấy/ghi build cache | Tách up-to-date khỏi FROM-CACHE |
| `--build-cache` | Cho phép task output caching | Kiểm cache hit khi output mất |
| `--refresh-dependencies` | Re-resolve/check dependency metadata/artifacts theo Gradle cache rules | Điều tra dependency resolution, không bắt task compile mỗi lần |
| `--offline` | Chỉ dùng dependency metadata/artifacts đang cached | Kiểm offline availability, không đo incremental correctness |
| `--info` | Log thêm lý do task execution/resolution | Điều tra vì sao task rerun |
| `--console=plain` | Console output đơn giản | Dễ ghi task outcomes trong CI |
| `--dry-run` | Mô phỏng task graph | Không chứng minh task action/up-to-date thật sự chạy |
| `--configuration-cache` | Tái sử dụng Gradle configuration model | Kiểm configuration phase, khác build cache |
| `--scan` | Xuất build scan (nếu được chấp thuận) | Điều tra timeline/task inputs; xem policy dữ liệu trước khi upload |

**Đặc biệt:** gọi `./gradlew clean build` **mọi lần** sẽ xóa outputs, khiến bạn không quan sát được up-to-date checking giữa hai lượt build cùng workspace. Muốn baseline, chỉ clean **lượt đầu**; lượt thứ hai phải chạy **không clean**.

**Cũng không dùng `--rerun-tasks` ở lượt thứ hai** — nó vô hiệu đúng cơ chế mà bạn định kiểm.

## 20. Viết TestKit functional test để kiểm hành vi tự động

Đối với shared Gradle plugin có nhiều custom task classes, nên tự động hóa phép thử bằng **Gradle TestKit**. TestKit dùng `GradleRunner` chạy Gradle build thực trong một temporary project, có thể:

1. Tạo `settings.gradle.kts` và `build.gradle.kts` fixture.
2. Tạo input text ban đầu.
3. Chạy task lần đầu, assert outcome `SUCCESS`.
4. Chạy task lần hai, assert `UP_TO_DATE`.
5. Thay input text, chạy lại, assert `SUCCESS` và output mới.
6. Chạy lại nữa, assert `UP_TO_DATE`.
7. Xóa output, chạy lại và xác nhận output được phục hồi/chạy action hợp lệ.
8. Kiểm việc thay untracked file không làm task rerun.
9. Dùng `--build-cache` ở một **test khác**, không trộn với thí nghiệm up-to-date.
10. Kiểm `--configuration-cache` nếu custom task/plugin cần hỗ trợ.

Một test outline (phần này là **mảnh trong một test class**, không độc lập nếu chưa có TestKit/JUnit setup):

```java
BuildResult first = runner.withArguments(
    "renderGreeting", "--no-build-cache"
).build();
assertEquals(
    TaskOutcome.SUCCESS,
    first.task(":renderGreeting").getOutcome()
);

BuildResult second = runner.withArguments(
    "renderGreeting", "--no-build-cache"
).build();
assertEquals(
    TaskOutcome.UP_TO_DATE,
    second.task(":renderGreeting").getOutcome()
);

// Thay đúng input file trong thư mục project tạm.
Files.writeString(
    tempDir.resolve("data/greeting.txt"),
    "Hello Java\n",
    StandardCharsets.UTF_8
);

BuildResult third = runner.withArguments(
    "renderGreeting", "--no-build-cache"
).build();
assertEquals(
    TaskOutcome.SUCCESS,
    third.task(":renderGreeting").getOutcome()
);
```

**Điều kiện để triển khai test thật:** `runner` phải là `GradleRunner.create()` đã có `withProjectDir(tempDir.toFile())` và `withPluginClasspath()` khi test plugin; có import `BuildResult`, `TaskOutcome`, JUnit assertions; fixture có task class/plugin hoàn chỉnh; đảm bảo `tempDir` là directory thật. `GradleRunner.withArguments` thay arguments mỗi lần, không thêm dồn; đoạn trên thể hiện ý định nhưng không phải một full test class standalone.

Với test build cache, không cố assert `FROM_CACHE` nếu task không cacheable, local cache trống hoặc cache loading bị vô hiệu. Nên kiểm khả năng cache sau khi thực sự populate cache entry và xóa output ở sandbox.

## 21. Checklist dành cho một custom Gradle task đúng chuẩn

- [ ] Task có inputs đúng và đủ, không đọc hidden environment hoặc file ngoài input model.
- [ ] Task có declared outputs đầy đủ, chỉ ghi vào files/dirs do task sở hữu.
- [ ] Task action deterministic với cùng inputs; nếu không, giải thích vì sao không thể cache.
- [ ] `@InputFile`/`@InputDirectory` được dùng đúng type, có path sensitivity hợp lý.
- [ ] `@Input` cho flags/properties thực sự ảnh hưởng output.
- [ ] Files do task khác tạo được nối qua Provider/TaskProvider, không chỉ hardcode path string.
- [ ] Chạy baseline lần 1 sau clean, output được tạo chính xác.
- [ ] Chạy lại không sửa input, task báo `UP-TO-DATE`.
- [ ] Sửa **đúng một input**, task chạy lại và output đổi đúng.
- [ ] Chạy thêm lần nữa, task `UP-TO-DATE` với new fingerprints.
- [ ] Sửa unrelated file, task không rerun ngoài ý muốn.
- [ ] Đổi input property, task rerun.
- [ ] Xóa/sửa output, task không báo `UP-TO-DATE` sai.
- [ ] Nếu dùng `InputChanges`, có `@Incremental` và xử lý ADDED/MODIFIED/REMOVED.
- [ ] Khi `changes.isIncremental=false`, task xử lý toàn bộ inputs, không để stale outputs.
- [ ] Chỉ bật `@CacheableTask` khi inputs/outputs deterministic/complete.
- [ ] Có test build cache riêng; không đòi mọi Copy/Jar task phải `FROM-CACHE`.
- [ ] Có Gradle TestKit hoặc CI smoke test cho tasks quan trọng.
- [ ] Có `--info` logs khi có unexpected rerun, không giấu nguyên nhân bằng `--rerun-tasks`.
- [ ] Gradle Wrapper và JDK/toolchains được pin nhất quán khi so kết quả.
- [ ] Không dùng `clean` trong lượt đo second build up-to-date.
- [ ] Chỉ kết luận sau khi so cả task outcomes lẫn output content/hash.
- [ ] Không đưa secrets, absolute machine paths hoặc timestamps ngẫu nhiên vào cacheable output.
- [ ] Có CI gate kiểm outputs thật, không chỉ một dòng `BUILD SUCCESSFUL`.
- [ ] Khi build gồm nhiều modules, chỉ kiểm tasks thật sự liên quan input thay đổi.

## 22. Những lỗi trong đo lường và chẩn đoán thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm chứng |
| --- | --- | --- |
| Lần 2 `renderGreeting` vẫn chạy | Đổi input/implementation/output; no history; flags khác | `--info`, so SHA-256 inputs/outputs |
| Lần 2 task `UP-TO-DATE` nhưng output sai | Input quan trọng chưa khai báo; task cũ đã tạo output sai | Kiểm action và complete input model; negative test |
| Sửa input nhưng task không chạy | File không được khai báo là input hoặc bị lọc khỏi file tree | Xem `@InputFile`/`@InputFiles`/includes |
| Sửa README khiến task rerun | Inputs quá rộng, như project root dir | Thu hẹp input scope |
| File resource đổi nhưng `compileJava` chạy | Generated source/compiler classpath/task implementation bị ảnh hưởng | `--info` và actual dependency graph |
| File resource đổi nhưng `jar` up-to-date sai | `jar` chưa nhận processed resource output đúng | Kiểm Java plugin/sourceSets/packaging |
| `java -cp` không thấy banner | Chỉ thêm classes dir, thiếu build/resources/main | Bổ sung resource output trong classpath |
| `FROM-CACHE` xuất hiện dù định đo up-to-date | Build cache đang bật, output local không hiện diện | Dùng `--no-build-cache`, giữ output |
| `NO-SOURCE` ở `compileJava` | Không có Java sources matching source set | Kiểm `src/main/java` và `sourceSets` |
| `SKIPPED` | `onlyIf`, explicit skip/conditional logic | Đọc task condition và task graph |
| Task chạy lại sau `clean` | Output cũ bị xóa | Dự kiến; không dùng clean giữa hai baseline |
| `--rerun-tasks` khiến mọi task chạy lại | Flag cố ý vô hiệu up-to-date | Bỏ flag trong experiment |
| `--refresh-dependencies` không ép JavaCompile chạy | Nó tác động resolution cache, không trực tiếp task execution | Dùng đúng công cụ theo mục tiêu |
| Java source thay đổi nhưng không thấy jar output | Chạy `classes` thay vì `jar` hoặc output ở path khác | Gọi `jar` và inspect `build/libs` |
| Task action không được gọi nhưng output vẫn có | `UP-TO-DATE` hoặc `FROM-CACHE` | Xem task outcome và file content |
| Gradle reports `UP-TO-DATE` dù chỉ đổi timestamp | Bytes/fingerprint không thay đổi, optimization có thể bỏ qua | So content hash; timestamp không luôn là input |
| Chạy hai builds trên hai workspaces, outcome khác | Chưa có local execution history; paths/toolchains khác | So cùng workspace trước, rồi test cache relocatability |
| Cache hit nhưng output không đúng | Hidden input, non-deterministic output hoặc cache key thiếu dữ liệu | Hoàn thiện inputs, vô hiệu cache tới khi sửa |
| Incremental file processor để sót file đã xóa | Không xử lý `ChangeType.REMOVED` | Xóa mapped output, test removal |
| `InputChanges.isIncremental=false` sau sửa | Không có history/output bị xóa/non-file input đổi | Xử lý full rebuild đúng |
| Task luôn chạy do mutable timestamp | Build action viết timestamp hiện tại vào tracked input/output | Loại volatile data hoặc model đúng |
| Nhiều tasks cùng ghi output dir | Overlapping outputs làm tracking thiếu tin cậy | Phân vùng output riêng từng task |
| Configuration cache reused nhưng task rerun | Hai optimization mechanisms khác nhau | Đọc cả config-cache và task outcomes |
| Test case không ổn định | IDE/daemon/antivirus/concurrency sửa file trong lúc đo | Sandbox độc lập, one change at a time |
| Task validation disables optimizations | Sai getter annotations, missing nested annotations, @Internal sai | Sửa Gradle task validation warnings |

### 22.1. Quy trình debug thực hành

```bash
./gradlew --version
./gradlew renderGreeting --no-build-cache --info --console=plain
./gradlew jar --no-build-cache --info --console=plain
./gradlew tasks --all
./gradlew jar --dry-run
```

Dùng `--dry-run` để xem graph nhưng **không** dùng nó làm bằng chứng incremental execution. Khi một task thực thi không như dự kiến, cần đọc **lý do** trong `--info` và so input/output snapshots, không chỉ nhìn `BUILD SUCCESSFUL`.

## 23. Bài tập để tự luyện

### Bài 1 — tăng độ khó của input properties

Thêm `Property<Boolean>` tên `trimWhitespace` vào `RenderGreetingTask` và gắn `@Input`; khi true thì trim, khi false giữ whitespace (định nghĩa rõ normalization). Chạy hai lần với same value, đổi property bằng `-P...` rồi kiểm action rerun. Không chỉ thêm property vào task DSL mà quên dùng nó trong action/annotation.

### Bài 2 — xác nhận input không cần thiết

Thêm `inputs.file("README.md")` vào task, chạy, sau đó sửa README. Quan sát task rerun dù output transform không dùng README. Gỡ khai báo sai. Từ đó hiểu tại sao declared inputs **quá rộng** làm chậm build.

### Bài 3 — phát hiện hidden input

Viết tạm task action lấy giá trị `System.getenv("BUILD_LABEL")` để thêm vào report, nhưng không khai báo `@Input`, rồi đổi env value giữa hai lượt build. Quan sát stale result có thể xảy ra. Sửa bằng `providers.environmentVariable("BUILD_LABEL")` nối tới `Property<String>` có `@Input`. Đừng biến exercise này thành build logic production trước khi có tests.

### Bài 4 — phân biệt cache và up-to-date

Dùng `--build-cache`, populate cache, `clean` rồi build lại. Kiểm có `FROM-CACHE` hay cache miss. Ghi điều kiện và Gradle/JDK versions; không tự khẳng định FROM-CACHE phải xuất hiện.

### Bài 5 — Java source và resource

Chạy `jar` hai lần; sửa chỉ `banner.txt`, xác nhận `compileJava` up-to-date và `processResources`/`jar` chạy. Tiếp theo sửa Java source và xác nhận `compileJava` chạy. Kiểm `jar tf build/libs/incremental-lab-1.0.jar` để xem class/resource có mặt.

### Bài 6 — incremental task có 3 files

Dùng `uppercaseFiles` với `a.txt`/`b.txt`/`c.txt`. Sau lần baseline, sửa một file, thêm một file, xóa một file qua các lượt riêng. Quan sát `InputChanges` và outputs tương ứng; test cả một lượt `changes.isIncremental=false` bằng cách xóa output directory do task sở hữu.

## 24. Câu hỏi tự kiểm tra

1. **Lần 2 không sửa input mà task báo `UP-TO-DATE` nói lên điều gì?** Gradle thấy inputs/outputs hợp lệ theo task model và không thực thi action.
2. **Một task `UP-TO-DATE` có thể tạo output mới ở lần hiện tại không?** Không, action đã bỏ qua; output phải có từ lần trước (hoặc task outcome khác như FROM-CACHE khi phục hồi).
3. **Vì sao chạy `clean build` cả hai lần làm mất ý nghĩa phép thử?** Clean xóa local outputs trước mỗi build.
4. **`--rerun-tasks` có phù hợp kiểm chứng incremental up-to-date không?** Không; nó buộc tasks chạy lại.
5. **`--no-build-cache` giúp gì?** Loại trừ khả năng output được lấy từ build cache.
6. **Thay một input làm task chạy đã chứng minh correctness chưa?** Chưa; phải kiểm kết quả output đúng.
7. **`@InputFile` mô tả gì?** File mà bytes/path normalization ảnh hưởng output.
8. **`@OutputFile` dùng để làm gì?** Gradle biết output tồn tại và có thể fingerprint/reuse nó.
9. **`PathSensitivity.NONE` thích hợp khi nào?** Một file mà vị trí không ảnh hưởng kết quả transform.
10. **`PathSensitivity.RELATIVE` thích hợp khi nào?** File tree mà đường tương đối có ý nghĩa cho mapping output.
11. **Khi Java resource đổi, `compileJava` có bắt buộc phải chạy?** Không trong baseline nếu Java source/classpath không đổi.
12. **Khi `compileJava` chạy, có phải compiler compile mọi source file không?** Không nhất thiết; incremental compilation có thể xử lý phần ảnh hưởng.
13. **`FROM-CACHE` có đồng nghĩa action chạy không?** Không, output được restore.
14. **Task action dùng `InputChanges` có chạy khi `UP-TO-DATE` không?** Không.
15. **`InputChanges.isIncremental=false` nghĩa gì?** Không thể tin delta; phải xử lý tất cả inputs theo full mode.
16. **Thay README không phải input mà task rerun, nghi ngờ gì?** Input scope quá rộng hoặc implementation/env đổi.
17. **Xóa output làm task rerun có đúng không?** Có, hoặc lấy từ cache khi được bật và có hit.
18. **Task không khai báo output có đáng kỳ vọng `UP-TO-DATE` không?** Thông thường không.
19. **Hai build có thời gian 3 giây và 2 giây có chứng minh tính tăng dần?** Không; cần task outcomes/input-output evidence.
20. **Configuration cache reused chứng minh build cache hit chưa?** Không; hai loại cache khác nhau.
21. **Vì sao phải giữ cùng Gradle Wrapper/JDK giữa baseline?** Tránh thay đổi tool implementation/compiler inputs.
22. **Vì sao cần negative control?** Để xác nhận unrelated files không vô tình trở thành inputs.
23. **Dùng `--info` để kiểm gì?** Lý do Gradle coi task out-of-date hoặc thiếu inputs/outputs.
24. **Chỉ kiểm `BUILD SUCCESSFUL` có đủ không?** Không, task có thể skip sai hoặc tạo stale output.
25. **Một kết luận đúng của bài là gì?** “Với input/output/task implementation cố định, lần 2 renderGreeting UP-TO-DATE; khi chỉ đổi greeting.txt, task chạy và output khớp”, không phải “mọi Gradle build luôn tăng tốc”.

## 25. Checklist kết luận và báo cáo thí nghiệm

Một report ngắn nhưng đầy đủ nên có:

- **Environment:** Gradle Wrapper version, Java version/toolchain, OS, checkout/commit.
- **Task under test:** path, type, declared inputs/outputs.
- **Commands:** chính xác flags, có/không `clean`, `--no-build-cache`.
- **Baseline input:** bytes/contents và hash nếu cần.
- **First build:** task execution evidence + output path/contents.
- **Second build:** `UP-TO-DATE` evidence và output không đổi.
- **Controlled change:** đúng tên file/property, before/after content.
- **Third build:** executed/cache labels và correct output update.
- **Fourth build:** `UP-TO-DATE` sau thay đổi.
- **Negative control:** unrelated file đổi mà task giữ up-to-date.
- **Output invalidation:** output bị xóa/sửa thì Gradle phát hiện đúng.
- **Java split check:** resource changes vs source changes, expected tasks.
- **Cache check:** tách biệt `FROM-CACHE` và `UP-TO-DATE`.
- **Risks:** external hidden inputs, overlapping outputs, non-deterministic task actions.
- **Conclusions:** claim dựa vào evidence; điều chưa được kiểm chứng ghi rõ.

Ví dụ câu kết luận có thể kiểm:

> Với `renderGreeting`, sau `clean` action chạy và tạo `MESSAGE=HELLO GRADLE`. Không thay input ở lượt 2, Gradle đánh dấu `UP-TO-DATE`. Khi chỉ đổi `data/greeting.txt` thành `Hello Java`, task thực thi lại, output thành `MESSAGE=HELLO JAVA`. Lượt kế tiếp không đổi, task trở lại `UP-TO-DATE`. Thử nghiệm chạy với `--no-build-cache` nên kết quả không dựa vào cache restore.

Đó là một kết luận **cụ thể, có thể tái lập**. Không ngoại suy rằng mọi task trong hệ thống đều incremental nếu chỉ thử một task.

## 26. Ghi nhớ

- **Hai lần build không đổi** là phép thử cơ bản để quan sát `UP-TO-DATE`.
- **Một thay đổi đầu vào có kiểm soát** kiểm tra Gradle có invalidation đúng task hay không.
- **Kiểm cả task outcome và output bytes**, không chỉ thời gian hoặc `BUILD SUCCESSFUL`.
- **Không chạy clean hai lần baseline**, không bật `--rerun-tasks` và không trộn build cache trong phép thử chính.
- **`@InputFile`, `@Input`, `@OutputFile` mô tả hợp đồng** để Gradle fingerprint.
- **Java resource change khác Java source change**: `processResources` và `compileJava` có inputs riêng.
- **`UP-TO-DATE` khác `FROM-CACHE` và khác incremental action `InputChanges`**.
- **Khi task chạy incremental**, nó vẫn có thể chỉ xử lý những files đổi nhờ `@Incremental` và `InputChanges`.
- **`--info` giúp tìm nguyên nhân rerun**, còn `--dry-run` chỉ cho biết task graph, không có bằng chứng thực thi.
- **Build tốt là build đúng trước rồi mới build nhanh**: tối ưu không có giá trị nếu outputs bị stale hoặc thiếu inputs.

## Tài liệu chính thức

- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): task inputs/outputs, fingerprints, up-to-date checks, invalidation và task states.
- [Gradle — Incremental Builds Advanced](https://docs.gradle.org/current/userguide/incremental_builds.html): task dependencies/outputs, incremental work, file change tracking và history.
- [Gradle — Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): `@Input`, `@InputFile`, `@OutputFile`, managed properties, task implementation.
- [Gradle — Advanced Tasks](https://docs.gradle.org/current/userguide/custom_tasks.html): `InputChanges`, `@Incremental`, non-incremental mode, file changes.
- [Gradle — Task Optimization Basics](https://docs.gradle.org/current/userguide/gradle_optimizations.html): `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED` task outcomes.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): opt-in caching, `@CacheableTask`, cache keys, JavaCompile vs Copy/Jar.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `compileJava`, `processResources`, `classes`, `jar` và Java source sets.
- [Gradle — InputChanges API](https://docs.gradle.org/current/javadoc/org/gradle/work/InputChanges.html): `getFileChanges`, `isIncremental` và change types.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): file path normalization và output contract.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration model vs build cache và task output reuse.
- [Gradle — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html): đọc `--info` và lý do task không up-to-date.
