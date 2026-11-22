# Tạo task sinh mã hoạt động đúng với up-to-date check và build cache

## 1. Mục tiêu bài thực hành

Một Gradle task sinh mã không chỉ cần tạo được tệp `GeneratedGreeting.java`. Nó phải **khai báo đầy đủ những gì quyết định nội dung**, mô tả **đúng output**, **sinh kết quả xác định**, và **kết nối output với task biên dịch** để Gradle có thể tối ưu hóa mà không phá correctness.

Sau bài thuộc **Build Tool Gradle → Thực hành tổng hợp**, bạn sẽ biết:

1. Dùng `@Input Property<String>` để mô hình hóa cấu hình đầu vào, `@OutputDirectory DirectoryProperty` để mô hình hóa thư mục sinh mã.
2. Viết một task type `@CacheableTask` với `@TaskAction`, sinh Java source **UTF-8/LF**, ổn định, tránh timestamp, đường dẫn tuyệt đối và input không khai báo.
3. Dùng `tasks.register`, Gradle `Provider` và `sourceSets.main.java.srcDir(taskProvider)` để `compileJava` có **producer dependency** đúng.
4. Xây dựng Java 17+ app/JUnit tests sử dụng class **được sinh** thật, không copy tệp giả vào `src/main/java`.
5. Phân biệt `UP-TO-DATE` (reuse output local) với `FROM-CACHE` (restore từ build cache).
6. Kiểm tra input thay đổi qua `-Pgreeting=Hi`, đổi output đúng và làm task invalidation đúng.
7. Xác định vì sao một task luôn execute, cache miss, có dependency warning, hoặc để lại stale Java source.
8. Hiểu file inputs, path normalization, `InputChanges`, Configuration Cache, build cache remote và test task type bằng TestKit.

Lab dùng **Gradle Groovy DSL**, **Java 17+** và Gradle Wrapper (ví dụ bản 9.9.0 tương thích). Nội dung code là project single-module có thể tự tạo ở workspace riêng. Tài liệu Gradle chính thức được đặt cuối bài để đối chiếu API và phiên bản.

**Điểm cần nhớ:** một annotation không “làm task an toàn” nếu bạn khai báo sai inputs/outputs. Task trả `UP-TO-DATE` trong khi source đầu ra đáng lẽ phải đổi còn nguy hiểm hơn task chậm.

## 2. Vòng đời của task: source của Gradle đi đâu?

```text
Gradle property:
-Pgreeting=Hello
      |
      | @Input Property<String> greeting
      v
:generateGreetingSource
  @CacheableTask / @TaskAction
      |
      | @OutputDirectory
      v
build/generated/sources/greeting/main/java/
  demo/generated/GeneratedGreeting.java
      |
      | SourceDirectorySet.srcDir(TaskProvider)
      | => Gradle suy ra dependency
      v
:compileJava
      |
      +--> :run => "Hello, Team!"
      |
      +--> :compileTestJava => :test
```

Generator sẽ viết một Java class có method:

```java
package demo.generated;

public final class GeneratedGreeting {
    private GeneratedGreeting() {}

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Khi đổi `-Pgreeting=Hi`, nội dung generated Java source sẽ trở thành `return "Hi, " + name + "!";`, và `App.main` in `Hi, Team!`.

Output path là **source directory**, không phải Java `.class`. `compileJava` biên dịch cả `src/main/java` và directory sinh mã; output của compiler nằm trong `build/classes/java/main`. Không trộn trách nhiệm của generator với compiler.

## 3. Phân biệt ba kết quả task

| Outcome | Ý nghĩa | Task action có chạy? | Khi nào có thể xuất hiện |
| --- | --- | --- | --- |
| Không có hậu tố (task `SUCCESS`) | Task vừa thực thi thành công. | Có. | First build, inputs/implementation thay đổi, output mất mà không có cache entry. |
| `UP-TO-DATE` | Snapshot inputs và outputs **trong workspace** hợp lệ; task không cần chạy. | Không. | Chạy lần hai cùng inputs, outputs còn nguyên. |
| `FROM-CACHE` | Gradle khôi phục outputs từ **local/remote build cache** có key phù hợp. | Không. | Sau clean/output bị xóa và cache entry đã warm. |
| `NO-SOURCE` | Task xử lý source mà chưa có source files. | Thường không. | Ví dụ processResources khi không có resources. |
| `SKIPPED` | Bỏ qua do condition/skip policy. | Không. | `onlyIf` false hoặc condition khác. |
| `FAILED` | Task/validation/compiler gặp lỗi. | Tùy giai đoạn. | Input sai, thiếu output permission, lỗi Java source. |

**Up-to-date checks** hoạt động kể cả khi **không bật build cache**. Chúng theo dõi input/output snapshots của workspace. `@CacheableTask` chỉ cho biết task type **được phép** tham gia caching; để Gradle tìm/store cached outputs, cần `--build-cache` hoặc `org.gradle.caching=true`, và task không bị caching disabled vì validation/implementation issues.

`clean` xóa build outputs trong project, **không xóa local build cache** trong Gradle User Home. Vì vậy sau khi cache đã có entry, chạy `clean generateGreetingSource --build-cache` thường cho `FROM-CACHE` (nếu key đúng), không phải `UP-TO-DATE`.

**Không nhầm “incremental build” với `InputChanges`:** Incremental build nói chung tránh việc không cần thiết. API `InputChanges` dành cho task xử lý từng file mới/đã sửa/đã xóa trong một action riêng. Task chỉ tạo một Java file như bài này **không cần** API đó để có UP-TO-DATE và FROM-CACHE.

## 4. Hợp đồng input/output cho generator

### 4.1. Cái gì là input?

Một input là **giá trị hoặc file ảnh hưởng bytes được sinh**. Task đơn giản này chỉ cần:

```groovy
@Input
abstract Property<String> getGreeting()
```

`Property<String>` là Gradle managed property, có thể nhận `Provider` để lazy cấu hình. `@Input` cho Gradle biết tính fingerprint của giá trị `Hello`/`Hi`.

Nếu generator thật còn đọc template, schema, flags, package name, generator tool version, environment hoặc classpath, phải khai báo **tất cả** thứ ảnh hưởng output:

| Đầu vào | Khai báo điển hình | Cảnh báo |
| --- | --- | --- |
| Chuỗi, số, boolean | `@Input Property<T>` | Đừng đọc một value khác bên trong TaskAction. |
| Template file | `@InputFile RegularFileProperty` | Thêm `@PathSensitive` phù hợp khi muốn cache relocatable. |
| Directory schema | `@InputDirectory DirectoryProperty` | Tracked content và relative paths theo normalization. |
| Bộ file schema | `@InputFiles ConfigurableFileCollection` | Cần stable order khi sinh output, tránh file system enumeration order. |
| Generator classpath | `@Classpath` hoặc `@CompileClasspath` | Tùy ý nghĩa của classpath, không bỏ qua generator binary version. |
| Một input optional | `@Optional` đi cùng input annotation | Missing/available cases vẫn phải có semantics đúng. |
| Chỉ state nội bộ không ảnh hưởng bytes | `@Internal` khi thực sự phù hợp | Không dùng @Internal để “che” một real input. |

Gradle còn theo dõi task type/implementation/action classpath khi có thể. Nếu implementation code đổi, build cache key hoặc up-to-date validity có thể đổi dù value `Hello` giữ nguyên.

### 4.2. Cái gì là output?

```groovy
@OutputDirectory
abstract DirectoryProperty getOutputDirectory()
```

Tất cả source generated của **một task này** nằm trong:

```text
build/generated/sources/greeting/main/java/
```

Trong đó là `demo/generated/GeneratedGreeting.java`. Một task sở hữu **một output directory riêng**; không khai toàn bộ `build/` là output, không ghi đè `src/main/java`, không cho hai tasks ghi chung `build/generated/sources`.

`DirectoryProperty` được cấu hình bằng `layout.buildDirectory.dir(...)`. Đây là Gradle managed output, giúp tracking, caching và truyền dependency metadata cho consumer.

### 4.3. Cùng input phải sinh cùng bytes

Để task cacheable đúng:

- Không chèn `Instant.now()`, random UUID, build number, CI job id chưa khai báo vào generated source.
- Không embed absolute project path, username, hostname hoặc secrets.
- Dùng **UTF-8** và xuống dòng **LF** nhất quán, tránh platform charset/line endings.
- Với multiple schema/template files, sort theo relative path khi render; không dựa thứ tự trả về của file system.
- Nếu generator dùng external tools, xác định version/arguments/toolchain và khai báo inputs phù hợp.
- Không đọc `System.getenv('PREFIX')` trong TaskAction mà không model nó như input; dùng Gradle Providers khi cấu hình.
- Nếu muốn cache cross-machine, output không được phụ thuộc working directory trừ khi đường dẫn ấy là input có chủ đích (thường nên bỏ khỏi output).

**`@CacheableTask` là lời cam kết về reproducibility và relocatability.** Một task sai input model có thể restore source cũ với cache key trông hợp lệ.

## 5. Dự án Java 17+ hoàn chỉnh

### 5.1. Chuẩn bị thư mục

```text
generated-source-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/App.java
    └── test/java/demo/AppTest.java

Sau lần build:
build/
└── generated/sources/greeting/main/java/
    └── demo/generated/GeneratedGreeting.java
```

Cần **JDK 17+** và Wrapper Gradle tương thích đã tạo từ nguồn tin cậy. Wrapper được sinh bằng `gradle wrapper`/`gradle init` trong một trusted Gradle installation; chỉ tạo file build.gradle **không tự sinh** Gradle Wrapper files. Với repository chưa đáng tin, kiểm `gradle-wrapper.jar`, launcher scripts và distribution checksum trước khi chạy `./gradlew`.

### 5.2. File settings.gradle

```groovy
rootProject.name = 'generated-source-lab'
```

### 5.3. File build.gradle đầy đủ

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    id 'application'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.App'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

@CacheableTask
abstract class GenerateGreetingSource extends DefaultTask {
    @Input
    abstract Property<String> getGreeting()

    @OutputDirectory
    abstract DirectoryProperty getOutputDirectory()

    @TaskAction
    void generate() {
        String prefix = greeting.get()

        // The lab allows only ASCII letters, avoiding Java injection.
        if (!(prefix ==~ /[A-Za-z]{1,40}/)) {
            throw new GradleException(
                'greeting must contain 1..40 ASCII letters')
        }

        File javaFile = outputDirectory
            .file('demo/generated/GeneratedGreeting.java')
            .get()
            .asFile
        javaFile.parentFile.mkdirs()

        // Generate stable UTF-8 bytes with LF line endings.
        String source =
            'package demo.generated;\n' +
            '\n' +
            'public final class GeneratedGreeting {\n' +
            '    private GeneratedGreeting() {}\n' +
            '\n' +
            '    public static String greet(String name) {\n' +
            '        return "' + prefix + ', " + name + "!";\n' +
            '    }\n' +
            '}\n'

        javaFile.setText(source, 'UTF-8')
        logger.lifecycle('Generated GeneratedGreeting.java')
    }
}

def greetingProvider =
    providers.gradleProperty('greeting').orElse('Hello')

def greetingGenerator =
    tasks.register('generateGreetingSource', GenerateGreetingSource) {
        greeting.set(greetingProvider)
        outputDirectory.set(
            layout.buildDirectory.dir(
                'generated/sources/greeting/main/java'))
    }

// Pass the TaskProvider (producer), NOT just a String path.
sourceSets {
    main {
        java {
            srcDir(greetingGenerator)
        }
    }
}

tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'expectedGreeting', greetingProvider.get()
}
```

**Phân tích từng yếu tố:**

1. `@CacheableTask` áp trên **task type**, giúp task đủ điều kiện cache khi build cache enabled và validation không chặn.
2. `@Input Property<String>` cho biết `prefix` thực sự ảnh hưởng source bytes.
3. `@OutputDirectory DirectoryProperty` nói với Gradle generator sở hữu directory `build/generated/sources/greeting/main/java`.
4. `@TaskAction` là nơi sinh file, **không sinh source trong configuration phase** hay trong `settings.gradle`.
5. Regex `[A-Za-z]{1,40}` giới hạn input demo để tránh chèn raw Java code bằng một chuỗi có `"`, newline hoặc dấu chấm phẩy. Generator production có thể cần escape Java literal đầy đủ nếu muốn hỗ trợ Unicode/special characters.
6. `javaFile.setText(source, 'UTF-8')` và các `\n` cố định giúp output bytes tương đương trên Windows/Linux cho cùng input.
7. `providers.gradleProperty('greeting').orElse('Hello')` tạo input có mặc định; người học override bằng `-Pgreeting=Hi`.
8. `tasks.register` thay vì eager `tasks.create` để cấu hình task lazily.
9. `sourceSets.main.java.srcDir(greetingGenerator)` dùng TaskProvider mang theo output + build dependency. Compiler không phải đoán ai tạo file.
10. `java.toolchain=17` chọn JDK 17 compiler/test launcher theo cấu hình, và `options.release=17` yêu cầu target Java 17 API/bytecode. Toolchain cần có JDK phù hợp hoặc provisioning config.
11. `test.systemProperty('expectedGreeting', ...)` đảm bảo JUnit tests có kỳ vọng nhất quán khi `-Pgreeting` đổi. Đọc provider trong **configuration** ở lab này là có chủ đích; TaskAction chỉ đọc các managed task properties, không truy cập Project/Gradle model.

**Đây là một file build.gradle hoàn chỉnh**, không dán thêm các fragment có cùng tên task ở phần sau vào cùng project.

### 5.4. File src/main/java/demo/App.java

```java
package demo;

import demo.generated.GeneratedGreeting;

public final class App {
    private App() {
    }

    public static String message(String name) {
        return GeneratedGreeting.greet(name);
    }

    public static void main(String[] args) {
        String recipient = args.length == 0 ? "Team" : args[0];
        System.out.println(message(recipient));
    }
}
```

Source chính chủ động import `demo.generated.GeneratedGreeting`. **Không tự tạo GeneratedGreeting.java trong `src/main/java`** — mục tiêu là để Gradle phải chạy/restore task generator trước khi JavaCompile.

### 5.5. File src/test/java/demo/AppTest.java

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void supportsDefaultRecipient() {
        String prefix = System.getProperty(
                "expectedGreeting", "Hello");
        assertEquals(prefix + ", Team!", App.message("Team"));
    }

    @Test
    void supportsOtherRecipient() {
        String prefix = System.getProperty(
                "expectedGreeting", "Hello");
        assertEquals(prefix + ", Gradle!", App.message("Gradle"));
    }
}
```

Hai JUnit Jupiter tests kiểm generated behavior. Với `-Pgreeting=Hi`, Gradle truyền `expectedGreeting=Hi` vào Test JVM, nên tests vẫn có nghĩa và không chỉ pass ở mặc định.

### 5.6. Chạy build lần đầu

Linux/macOS:

```bash
./gradlew clean test run --build-cache --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test run --build-cache --console=plain
```

**Stdout riêng của Java main** khi không truyền argument:

```text
Hello, Team!
```

Gradle còn hiển thị các tasks `generateGreetingSource`, `compileJava`, `test`, `run` và các log khác; đây **không phải toàn bộ transcript Gradle**. Trong môi trường đúng, hai tests dự kiến PASS; không tuyên bố đã chạy tests thực trên máy người dùng.

Chạy với một người nhận khác:

```bash
./gradlew -q run --args="Gradle" --build-cache
```

Stdout Java:

```text
Hello, Gradle!
```

Lệnh `run` là JavaExec/in app, thường **không** cacheable như task tạo file outputs. Việc `run` in stdout không chứng minh task `generateGreetingSource` đã execute; kiểm task outcome riêng.

### 5.7. Generated source chính xác

Đọc file trên Linux/macOS:

```bash
cat build/generated/sources/greeting/main/java/demo/generated/GeneratedGreeting.java
```

PowerShell:

```powershell
Get-Content .\build\generated\sources\greeting\main\java\demo\generated\GeneratedGreeting.java
```

Với `greeting=Hello`, content đúng là:

```java
package demo.generated;

public final class GeneratedGreeting {
    private GeneratedGreeting() {}

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Nếu `greeting=Hi`, chỉ Java string constant liên quan lời chào khác:

```java
public static String greet(String name) {
    return "Hi, " + name + "!";
}
```

Fragment thứ hai là **trích riêng một method**, không phải một Java class standalone. Cả hai bytes được sinh từ cùng template ổn định của task type, khác nhau ở tracked input.

### 5.8. Task graph: compiler tự phụ thuộc generator

```bash
./gradlew compileJava --dry-run --console=plain
```

Task graph của lab phải bao gồm `:generateGreetingSource` trước `:compileJava`:

```text
:generateGreetingSource
          |
          v
:compileJava
          |
          v
:classes => :run / :test / :jar ...
```

`--dry-run` dùng để xem task graph, **không execute task actions** và không chứng minh Java đã compile hay tests pass. Chạy `compileJava` không có dry-run trên clean checkout để verify wiring thật.

### 5.9. Vì sao sourceSet cần TaskProvider?

Đoạn đúng trong build.gradle:

```groovy
sourceSets {
    main {
        java {
            srcDir(greetingGenerator)
        }
    }
}
```

Gradle hiểu `greetingGenerator` là **producer task** của directory input cho Java source set. Khi compiler, source jar (nếu có) hoặc tool đọc source set, task dependency có thể được suy ra thông qua output file collection.

Anti-pattern:

```groovy
// Sai nếu chỉ khai path, không có producer/build dependency.
sourceSets {
    main {
        java {
            srcDir('build/generated/sources/greeting/main/java')
        }
    }
}
```

Ở ví dụ sai, compiler biết thư mục nhưng không biết **task nào phải tạo nó trước**. Build có thể vô tình pass trên máy đã có generated files, rồi fail trên clean CI hoặc khi Gradle chạy parallel. Có thể cần `builtBy` hoặc `dependsOn` explicit khi API đặc thù không nhận TaskProvider, nhưng tốt nhất là **truyền đúng producer output/task provider**; `mustRunAfter` chỉ là ordering rule, không tự thêm task vào graph.

`srcDir(...)` là **bổ sung** source directory; gán `srcDirs = [...]` có thể **thay** toàn bộ dirs và vô tình bỏ mất `src/main/java`.

## 6. Bộ thí nghiệm task outcomes

Các kết quả dưới đây là **kỳ vọng có điều kiện**, không giả vờ đã thực thi trong một CI runner cụ thể. Outcome có thể khác nếu cache đã warm, implementation thay đổi, cache bị eviction hoặc plugin policy tắt cache.

### 6.1. Lần đầu: action execute và cache được warm

```bash
./gradlew clean generateGreetingSource \
  --build-cache --console=plain
```

Nếu chưa có cache entry cho cùng input/implementation, task action chạy và `logger.lifecycle` in:

```text
Generated GeneratedGreeting.java
```

Task outcome thường:

```text
> Task :generateGreetingSource
```

Sau khi task thành công, Gradle có thể store outputs vào local build cache. Nếu cache đã warm, ngay lần này có thể `FROM-CACHE`. Để xem chắc action lần đầu, dùng `--no-build-cache` trên một clean workspace rồi bật cache ở invocation tiếp theo để warm.

### 6.2. Cùng workspace không thay đổi gì

```bash
./gradlew generateGreetingSource \
  --build-cache --console=plain
```

Kỳ vọng:

```text
> Task :generateGreetingSource UP-TO-DATE
```

Action **không** chạy nên dòng `Generated GeneratedGreeting.java` không xuất hiện từ task. Đây không phải FROM-CACHE.

### 6.3. Clean output nhưng cache còn

Sau khi đã có cache entry hợp lệ:

```bash
./gradlew clean generateGreetingSource \
  --build-cache --console=plain
```

Kỳ vọng:

```text
> Task :generateGreetingSource FROM-CACHE
```

`clean` đã làm mất output local; cache restore trả source về `build/generated/...` mà không cần chạy TaskAction. Nếu task vẫn execute, xem `--info` để biết nguyên nhân cache miss/cache disabled, không tự khẳng định task sai.

### 6.4. Đổi tracked input thành Hi

```bash
./gradlew generateGreetingSource \
  -Pgreeting=Hi --build-cache --console=plain
./gradlew -q run -Pgreeting=Hi --build-cache
```

**Stdout Java main**:

```text
Hi, Team!
```

Task `generateGreetingSource` sẽ không UP-TO-DATE so với output Hello; nếu cache Hi đã có thì nó có thể FROM-CACHE, nếu chưa thì execute để tạo Java file mới. Chạy test:

```bash
./gradlew test -Pgreeting=Hi --build-cache --console=plain
```

Do Test JVM nhận `expectedGreeting=Hi`, hai assertions có thể pass khi generated class và compiler wiring đúng.

### 6.5. Hi lần hai rồi quay về Hello

```bash
./gradlew generateGreetingSource -Pgreeting=Hi \
  --build-cache --console=plain
./gradlew generateGreetingSource -Pgreeting=Hello \
  --build-cache --console=plain
```

Lệnh đầu thường UP-TO-DATE (sau lần Hi). Lệnh hai không còn UP-TO-DATE so với output Hi; nếu cache Hello đã có thì FROM-CACHE, nếu không task execute lại. **Cache key có tính input**, không chỉ tên task `generateGreetingSource`.

### 6.6. Tắt cache mà vẫn UP-TO-DATE

```bash
./gradlew clean generateGreetingSource \
  --no-build-cache --console=plain
./gradlew generateGreetingSource \
  --no-build-cache --console=plain
```

Lần hai có thể `UP-TO-DATE` dù không có build cache, vì local fingerprint/output vẫn đúng. `--no-build-cache` không vô hiệu hóa up-to-date checks.

### 6.7. Buộc action chạy để kiểm lập lại

```bash
./gradlew generateGreetingSource \
  --rerun-tasks --no-build-cache --console=plain
```

`--rerun-tasks` ép tasks trong graph execute; `--no-build-cache` loại restore cache khỏi thí nghiệm. Dùng để kiểm generator tạo cùng bytes với cùng input chứ không chỉ restore từ cache. Không bật `--rerun-tasks` cho mọi CI run rồi kỳ vọng vẫn thấy UP-TO-DATE.

### 6.8. Input không hợp lệ phải fail

```bash
./gradlew generateGreetingSource \
  -Pgreeting=Hello123 --no-build-cache --console=plain
```

Task action **dự kiến FAIL** với thông báo:

```text
greeting must contain 1..40 ASCII letters
```

Lỗi là có chủ ý: regex của lab chỉ cho ASCII letters, để ngăn người dùng đưa thẳng dấu nháy/Java code fragment vào generated literal. Generator production muốn hỗ trợ Unicode/dấu câu phải **escape Java string literal đầy đủ** hoặc dùng model/templating engine đảm bảo an toàn.

## 7. Check cache key và hidden inputs

### 7.1. Up-to-date snapshots

Gradle theo dõi fingerprints:

- Tracked input property names/values.
- Input file content/normalized path khi task dùng file inputs.
- Task implementation/actions/classpath mà Gradle có thể track.
- Output files/directories và trạng thái local sau lần chạy thành công.

Nếu không có declared output, Gradle thường không thể bỏ qua task bằng up-to-date checks. Nếu declared output mà thực tế task ghi **ngoài** output directory, Gradle có thể cache thiếu dữ liệu và trả kết quả sai. Cũng không được khai một directory khổng lồ nhiều task dùng chung.

### 7.2. Build cache key

Cache key không chỉ là hash của `GeneratedGreeting.java` hoặc duy nhất `-Pgreeting`. Nó liên quan task implementation, names/values của tracked inputs, classpath/plugin/Gradle implementation và output property names. Cùng giá trị Hello có thể cache miss hợp lệ sau khi sửa task code hoặc nâng Gradle/plugin.

Gradle chỉ cache những task có policy cho phép. `@CacheableTask` là opt-in ở task type; custom type không tự cacheable chỉ vì có input/output. `outputs.cacheIf` tồn tại cho trường hợp conditional cacheability, nhưng với task type luôn deterministic nên dùng `@CacheableTask` rõ ràng hơn.

### 7.3. Hidden input ví dụ sai

```groovy
// PHẢN VÍ DỤ: TaskAction có input không được track.
@TaskAction
void generate() {
    String prefix = System.getenv('GREETING_PREFIX')
    // ...write generated source based on prefix...
}
```

Nếu environment đổi nhưng Gradle task không khai input, Gradle có thể trả UP-TO-DATE/FROM-CACHE dù output đáng lẽ thay. Mô hình đúng là `providers.environmentVariable('GREETING_PREFIX')` nối vào một `@Input Property<String>` khi cấu hình task, hoặc tránh dùng environment nếu không cần.

**Tương tự:** `new Date()`, random, locale, git SHA, current branch, network response hoặc file chưa declare đều có thể là hidden input. Nếu chúng ảnh hưởng output, cần khai báo; với các giá trị biến động khó kiểm soát, tốt hơn là thiết kế generator không phụ thuộc chúng.

### 7.4. Path normalization cho file inputs

Nếu có template/schema, dùng getter như **fragment bổ sung** sau (không phải class standalone):

```groovy
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity

@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
abstract RegularFileProperty getTemplateFile()
```

Muốn chạy thật, phải thêm getter vào task class, cấu hình `templateFile`, dùng nội dung template trong TaskAction và cập nhật output logic. `RELATIVE` hữu ích khi thư mục workspaces khác nhau mà relative path/content tương đương; `ABSOLUTE` có thể ngăn cross-machine cache reuse; `NAME_ONLY` có thể nguy hiểm khi hai folders có file cùng tên nhưng semantics khác.

Một file input thuộc **compiler classpath** thường thích hợp với `@Classpath`/`@CompileClasspath` thay vì generic `@InputFiles`, tùy generator semantics.

### 7.5. Không embed output location

Output property là **đích ghi**, không nhất thiết là input logic. Khi generator viết absolute output directory vào comment hoặc Java constant, cùng input ở hai workspaces sinh bytes khác nhau, phá relocatability:

```groovy
// PHẢN VÍ DỤ: tránh chèn path tuyệt đối vào Java source.
String path = outputDirectory.get().asFile.absolutePath
```

Lab không làm thế; nó chỉ ghi package/class/method fixed và prefix đã declare.

## 8. Output ownership và stale files

Trong lab, generator **luôn ghi một file cố định** nên overwrite cùng file là đủ. Generator thực tế đọc danh sách schemas có thể thay tập outputs:

```text
Inputs lần 1: User.yaml, Order.yaml
Outputs: User.java, Order.java

Inputs lần 2: User.yaml
Outputs đúng: User.java
Bug: User.java, Order.java (stale)
```

Nếu `Order.java` bị bỏ khỏi schema mà vẫn còn trong generated directory, `compileJava` có thể compile class không còn hợp lệ. Một `@OutputDirectory` không tự hiểu mapping nghiệp vụ file nào phải bị xóa.

Giải pháp:

1. Mỗi generator task sở hữu **output dir riêng**.
2. Khi thực thi full-regeneration action, chỉ xóa **directory do task sở hữu**, rồi sinh lại trọn output set.
3. Hoặc implement incremental mapping với `InputChanges`, xử lý `REMOVED` để xóa tệp corresponding.
4. Nếu generator phức tạp, tạo deterministic manifest file trong output, so previous/new output sets rồi dọn obsolete files.
5. Đừng xóa output trong **configuration phase**; side effect có thể chạy ngay khi `./gradlew help`, phá Configuration Cache.
6. Đừng xóa một parent directory chứa output của **task khác**.
7. Với temp staging, kiểm platform-specific atomic move/permissions và đảm bảo temp files không rò rỉ khỏi declared output model.

Gradle snapshot behavior với `@OutputDirectory` có nuance đối với file thêm từ ngoài. Không nên dựa vào “Gradle sẽ tự dọn mọi file lạ” để bảo đảm source set sạch. **Task action phải tạo và quản lý đúng toàn bộ output set.**

## 9. InputChanges là tùy chọn, không phải điều kiện có cache

Một task với `@Input` và `@OutputDirectory` có thể UP-TO-DATE/FROM-CACHE mà không cần `InputChanges`. Nếu xử lý 10.000 schema files, incremental action có thể tiết kiệm bằng cách chỉ regenerate files bị sửa:

```groovy
// FRAGMENT cho một task type khác, chưa phải runnable class.
@Incremental
@PathSensitive(PathSensitivity.RELATIVE)
@InputFiles
abstract ConfigurableFileCollection getSchemas()

@TaskAction
void generate(InputChanges changes) {
    changes.getFileChanges(schemas).each { change ->
        // ADDED/MODIFIED: regenerate corresponding output.
        // REMOVED: delete stale corresponding output.
        // Non-incremental fallback: process all source schemas.
    }
}
```

Cần import `InputChanges`, `@Incremental`, file types/changes, configure schemas, declare output directory và implement full algorithm. Không copy fragment này vào class lab vốn đã có một `@TaskAction` vì đó là **một task model khác**.

Với một generator rất đơn giản, full regeneration khi input đổi là đủ; optimization này không tự tăng correctness nếu chưa test removed files, schema renames và non-incremental fallback.

## 10. Configuration Cache và Dependency Cache không phải Build Cache

| Cơ chế | Reuse gì? | Dấu hiệu chính |
| --- | --- | --- |
| Up-to-date state | Valid local task output và input/output fingerprints. | `UP-TO-DATE`. |
| **Build Cache** | Cached outputs của task theo implementation/input key. | `FROM-CACHE`. |
| **Configuration Cache** | Configured task graph/model giữa invocations. | “Reusing configuration cache” nếu supported. |
| **Dependency Cache** | Maven/Gradle artifacts và remote metadata downloads. | Ít tải dependencies hơn; không có task FROM-CACHE chỉ do dependency download reuse. |

Có thể kiểm Configuration Cache riêng:

```bash
./gradlew generateGreetingSource \
  --configuration-cache --build-cache --console=plain
./gradlew generateGreetingSource \
  --configuration-cache --build-cache --console=plain
```

Lab TaskAction chỉ dùng managed properties/File APIs/Gradle logger, không dùng `project.file`, `project.version` hoặc `gradle.taskGraph` trong action. Đây là pattern thân thiện với Configuration Cache; tuy nhiên toàn bộ build/plugins/Gradle version vẫn phải tương thích, và nếu có report failure cần xử lý thật.

`--configuration-cache` **không sửa** task thiếu input và cũng không có nghĩa output đã được restored từ Build Cache. `compileJava` và `run` có semantics khác nhau.

## 11. Debug task luôn chạy hoặc không dùng cache

Lệnh khởi đầu:

```bash
./gradlew generateGreetingSource \
  --build-cache --info --console=plain
```

`--info` giúp thấy vì sao task không UP-TO-DATE hoặc caching disabled/hit/miss theo Gradle version. `--debug` chi tiết hơn, có thể chứa paths/credentials trong logs; không tự đưa lên public issue nếu code công ty nhạy cảm.

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm và sửa |
| --- | --- | --- |
| Mỗi lần đều execute | Task không có declared output. | Bổ sung `@OutputDirectory`/`@OutputFile`, xem task validation. |
| Mỗi lần đều execute | Output bị tool khác sửa/xóa. | Một task một dir; kiểm cleanup tools/IDE/CI. |
| Mỗi lần đều execute | Hidden input/clock/random trong generator. | Chuyển thành tracked input hoặc loại bỏ. |
| Caching disabled | Không có `@CacheableTask` hoặc validation/implementation tracking issue. | Đọc `--info`, sửa task type/model. |
| Sau clean không FROM-CACHE | Cache disabled/miss, entry chưa warm, key khác hoặc bị eviction. | Warm cùng inputs, bật cache, kiểm task implementation. |
| `-Pgreeting=Hi` nhưng generated Java còn Hello | Prefix không thực sự nối vào `@Input`. | Dùng `greeting.set(provider)`, không đọc hidden env. |
| compileJava không chờ generator | Naked source path thiếu producer dependency. | `srcDir(generatorTaskProvider)`. |
| Compiler báo không tìm thấy GeneratedGreeting | Output path/package không khớp hoặc generator chưa chạy. | So `demo/generated/GeneratedGreeting.java`, inspect task graph. |
| Java source thay rồi nhưng compiled class không đổi | Compiler source path/input wiring sai hoặc generated bytes thực chưa đổi. | Inspect source file, compileJava outcome và cache/input snapshots. |
| File generated cũ vẫn còn | Input file set giảm nhưng task không cleanup obsolete outputs. | Full regenerate hoặc `InputChanges.REMOVED`. |
| Cache khác nhau giữa OS | Encoding/newlines/absolute path/locale ảnh hưởng. | UTF-8/LF, stable sort, normalized path inputs. |
| Task compile FROM-CACHE nhưng generator UP-TO-DATE | Hai task có snapshots/cache key riêng. | Hành vi bình thường. |
| Test task fail khi prefix đổi | JUnit expected Hello hard-coded. | Truyền expectedGreeting từ cùng Gradle property. |
| `run` vẫn execute | JavaExec không phải output cacheable task. | Đọc outcome generator, không dựa vào stdout JavaExec. |
| Configuration Cache fail | Task action hoặc plugin dùng Project/Gradle model không đúng. | Managed properties, build report và supported plugin APIs. |
| Two tasks overlap outputs | Output dirs trùng nhau gây race và cache invalidation. | Độc lập directory cho mỗi generator. |
| Build cache có secrets | Generator đưa token/credential vào source. | Không đưa secrets vào output; hạn chế remote cache quyền truy cập. |

**Không** sửa thủ công Gradle internal state trong `.gradle/` để buộc một outcome. Hãy thay input/đổi điều kiện build có kiểm soát.

## 12. Kiểm bytes để chứng minh deterministic

Task outcome đẹp chưa đủ. Một generator cacheable đúng phải:

- Tạo đúng file path/package/class signature.
- Sinh cùng **bytes** từ cùng input khi **action được chạy thật**.
- Đổi bytes đúng khi `-Pgreeting` đổi.
- Không sinh file ngoài declared output.
- Không đưa date/time/path/secret vào bytes.
- Compile/Test tiêu thụ source generated thực.
- Sau clean + warm cache, restored file có cùng bytes như output lần execution hợp lệ.

### 12.1. SHA-256 trên Linux

```bash
sha256sum \
  build/generated/sources/greeting/main/java/demo/generated/GeneratedGreeting.java
```

macOS:

```bash
shasum -a 256 \
  build/generated/sources/greeting/main/java/demo/generated/GeneratedGreeting.java
```

Windows PowerShell:

```powershell
Get-FileHash .\build\generated\sources\greeting\main\java\demo\generated\GeneratedGreeting.java -Algorithm SHA256
```

Không bịa expected SHA: actual bytes/source line endings phải được đọc sau khi sinh trên machine thực. Đây là test deterministic output, **không** phải `verification-metadata.xml` cho Maven dependencies.

### 12.2. Hai workspaces / hai máy

1. Lấy cùng commit, verified Wrapper/JDK/plugin settings.
2. Cấu hình cùng `-Pgreeting=Hello`.
3. **Tắt cache** và **buộc task action chạy** trên cả hai:
   `./gradlew generateGreetingSource --no-build-cache --rerun-tasks`.
4. Lấy SHA-256 generated file và so sánh bytes.
5. Nếu khác, tìm hidden input, locale/encoding, sorting, paths/tool versions.
6. Sau khi output equality đã được xác nhận, thử local/remote Build Cache để kiểm FROM-CACHE khi output bị clean.

**Không** chỉ restore cùng cache entry vào hai machines rồi tuyên bố generator thực sự deterministic cross-platform: khi đó generator có thể chưa chạy ở một trong hai machines.

## 13. Local và remote build cache trên CI

Bật cache theo invocation:

```bash
./gradlew test --build-cache
```

Hoặc `gradle.properties`:

```properties
org.gradle.caching=true
```

Bỏ cache cho một invocation:

```bash
./gradlew test --no-build-cache
```

Remote cache có thể chia sẻ output giữa developers/CI nodes; vì vậy tính đúng đắn và bảo mật quan trọng hơn tỷ lệ hit:

- **Trusted CI writer**, developer/untrusted PR reader theo chính sách; không cho untrusted code dễ dàng đẩy poisoned artifacts vào shared trusted cache.
- HTTPS/auth, scope permissions, retention và quota.
- Không cache generated files chứa passwords, tokens, khách hàng hoặc dữ liệu cá nhân.
- Reproducible output/path normalization và version pinning.
- Cache miss không tự là bug, có thể do task implementation/Gradle/JDK/plugin version hoặc input changes.
- Dependency locking/verification và Gradle Wrapper validation bảo vệ **những đầu vào khác**, không thể thay bằng Build Cache.

**Phân biệt:** Build Cache key định danh task execution state để tái dùng **outputs**; dependency verification so checksum/PGP của **downloaded dependencies**; dependency lockfile cố định resolved **versions**. Một FROM-CACHE label không chứng minh mọi dependency đều được security review.

## 14. Functional testing với Gradle TestKit

Khi generator được đóng gói thành convention/binary plugin trong `buildSrc`, `build-logic` hoặc plugin project, nên viết TestKit functional tests:

1. Build temp project, apply plugin, run `generateGreetingSource`, assert `TaskOutcome.SUCCESS` và source content.
2. Run again unchanged, assert `TaskOutcome.UP_TO_DATE`.
3. Warm isolated build cache, clean outputs, run again, assert `TaskOutcome.FROM_CACHE`.
4. Đổi input và assert Java source content/key/outcome mới.
5. Xóa input schema và assert stale outputs được dọn.
6. Biên dịch generated source từ clean checkout và chạy tests.
7. Chuyển project sang path khác để kiểm relocatability.
8. Test Configuration Cache reuse nếu plugin có cam kết tương thích.

Một fragment trong **Gradle plugin TestKit test** (không phải class standalone):

```java
import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.TaskOutcome;

// result is a BuildResult returned by GradleRunner.build().
TaskOutcome outcome = result.task(":generateGreetingSource")
        .getOutcome();

if (outcome != TaskOutcome.UP_TO_DATE) {
    throw new AssertionError("Expected task UP_TO_DATE");
}
```

Biến `result` chỉ tồn tại sau khi test tạo `GradleRunner`. Không copy fragment này vào `src/test/java/demo/AppTest.java` của lab; app tests kiểm generated Java behavior, còn TestKit tests kiểm Gradle task behavior.

## 15. Lỗi thiết kế cần tránh

| Anti-pattern | Vì sao sai | Thay thế |
| --- | --- | --- |
| Generator viết trong `doLast` nhưng không declare outputs | Không có snapshot/cache đúng. | Typed task với @Input/@OutputDirectory. |
| `@CacheableTask` nhưng output dùng `Instant.now()` | Cùng input có nhiều outputs; cache sai. | Sinh deterministic bytes. |
| Task action đọc env/system property ẩn | Input change không invalidate đúng. | Providers + tracked Property. |
| Nhiều generators dùng một output directory | Output overlap/races. | Mỗi task một directory. |
| Sinh source vào `src/main/java` | Ghi đè committed sources, khó clean. | `build/generated/sources/...`. |
| Chỉ dùng `srcDir('build/generated/...')` | Không carry producer dependency. | `srcDir(taskProvider)`. |
| `mustRunAfter(generator)` thay dependency | Không tự đưa generator vào graph. | Model output/input relationship. |
| Chỉ `dependsOn(generator)` nhưng không declare output | Ordering có thể đúng, cache vẫn sai. | Declare output và pass TaskProvider. |
| Generated Java nhét raw user input bất kỳ | Có thể injection/compile fail. | Validate/escape Java literals. |
| Platform charset/line endings | Cùng input bytes khác giữa OS. | UTF-8/LF. |
| Generator quên dọn stale files | Compiler thấy Java class không còn trong schema. | Full regenerate hoặc InputChanges handling. |
| Dùng `@Internal` cho source-affecting property | Gradle không fingerprint input đó. | `@Input`. |
| Tắt cache rồi kỳ vọng FROM-CACHE | Cache thực sự disabled. | Bật `--build-cache` khi thử restore. |
| Chạy `clean` rồi kỳ vọng UP-TO-DATE | Local output mất. | Nếu cache warm, FROM-CACHE có thể xảy ra. |
| `--rerun-tasks` trong mọi test speed | Ép execute, che optimization. | Chỉ dùng để kiểm correctness riêng. |
| Thấy `run` SUCCESS rồi coi generator không cache | JavaExec khác generator. | Xem `:generateGreetingSource` outcome. |
| Đưa secrets vào generated source/cache | Có nguy cơ leakage qua source/JAR/remote cache. | Không generate secrets; protect CI/cache. |

## 16. Bài tập thực hành

**Bài 1:** Task type cần annotation nào để cache output? **`@CacheableTask`**, khi deterministic/relocatable.

**Bài 2:** Value `greeting` làm đổi Java source, khai báo ra sao? **`@Input Property<String>`**.

**Bài 3:** Generated source dir khai báo ra sao? **`@OutputDirectory DirectoryProperty`**; path dưới `layout.buildDirectory`.

**Bài 4:** Task chạy lần thứ hai không đổi input/output, kỳ vọng gì? **UP-TO-DATE**.

**Bài 5:** Sau clean, cache đã có Hello, task có thể trả gì? **FROM-CACHE**.

**Bài 6:** `--no-build-cache` có tự tắt UP-TO-DATE không? **Không**.

**Bài 7:** `-Pgreeting=Hi` làm stdout Java main thành gì? **`Hi, Team!`**.

**Bài 8:** Tại sao JUnit tests dùng `expectedGreeting`? Để test đúng input mới, không hard-code Hello.

**Bài 9:** Tại sao `srcDir(greetingGenerator)` hơn hard-code path? Giữ producer task dependency.

**Bài 10:** Task generator ghi Java source trong configuration phase có tốt không? **Không**; dùng TaskAction khi execute.

**Bài 11:** Nếu generator đọc template mà không declare @InputFile? Gradle có thể UP-TO-DATE sai khi template đổi.

**Bài 12:** Muốn share cache cross-machine, file inputs nên có gì? Path normalization phù hợp (thường RELATIVE cho template), không embed absolute paths.

**Bài 13:** Dùng InputChanges có bắt buộc để thấy FROM-CACHE? **Không**.

**Bài 14:** Schema Order bị xóa, `Order.java` còn. Giải quyết? Cleanup stale outputs hoặc xử lý InputChanges.REMOVED.

**Bài 15:** Hai generators viết chung folder dẫn tới gì? Output overlap/caching incorrect/race.

**Bài 16:** `--rerun-tasks --no-build-cache` hữu ích vì sao? Buộc action thật tạo output để kiểm deterministic bytes.

**Bài 17:** Cùng cache entry restore trên hai machines, hashes bằng nhau: đủ chứng minh generator deterministic không? **Chưa**, phải chạy action trên cả hai.

**Bài 18:** Cache key có phải chỉ chứa scalar `greeting`? **Không**, còn implementation/classpath/tracked inputs và output property names.

**Bài 19:** Gradle output `UP-TO-DATE` nhưng Java source không khớp schema mới, nên xử lý gì? Kiểm hidden input, generated output cleanup, wiring/task snapshots.

**Bài 20:** Có nên cho untrusted PR push remote cache chung của release CI không? **Không mặc định**; cần access controls để tránh cache poisoning.

### Checklist hoàn thành bài

- [ ] Code `GenerateGreetingSource` có @CacheableTask, @Input, @OutputDirectory và @TaskAction.
- [ ] Task dùng managed providers/properties; không đọc clock/env/network ẩn.
- [ ] Source Java sinh ổn định UTF-8/LF dưới unique output directory.
- [ ] `compileJava` tự phụ thuộc generator bằng sourceSet TaskProvider.
- [ ] App import đúng package/class generated; clean build không cần file pre-existing.
- [ ] Hai JUnit tests PASS khi input Hello và khi input Hi.
- [ ] Cùng workspace chạy lần 2 có thể UP-TO-DATE.
- [ ] Sau clean và warm cache có thể FROM-CACHE.
- [ ] Thay prefix invalidates đúng task và output bytes/Java stdout.
- [ ] Không có stale generated classes, output overlap, secret leakage.
- [ ] Cache miss được chẩn đoán bằng `--info`; không ngộ nhận mọi miss là bug.
- [ ] Nếu đóng gói thành plugin, có TestKit tests cho outcomes, deterministic output và relocatability.

## 17. Tài liệu chính thức

- **Gradle Incremental Build:** input/output snapshots, @Input/@OutputDirectory và task dependency inference: https://docs.gradle.org/current/userguide/incremental_build.html
- **Gradle Build Cache:** --build-cache, @CacheableTask, cache keys, local/remote cache: https://docs.gradle.org/current/userguide/build_cache.html
- **Gradle Best Practices for Tasks:** unique outputs, lazy providers, cacheable tasks, tracked inputs: https://docs.gradle.org/current/userguide/best_practices_tasks.html
- **Gradle Implementing Custom Tasks:** managed properties, task types, @TaskAction: https://docs.gradle.org/current/userguide/implementing_custom_tasks.html
- **Gradle Advanced Tasks:** InputChanges, @Incremental, PathSensitivity, removed file handling: https://docs.gradle.org/current/userguide/custom_tasks.html
- **Gradle Building Java & JVM Projects:** source sets, srcDir vs srcDirs, compileJava: https://docs.gradle.org/current/userguide/building_java_projects.html
- **Gradle Lazy Configuration:** TaskProvider and producer→consumer wiring: https://docs.gradle.org/current/userguide/lazy_configuration.html
- **Gradle Optimizations:** UP-TO-DATE vs FROM-CACHE semantics: https://docs.gradle.org/current/userguide/gradle_optimizations.html
- **Gradle Build Cache Debugging:** cache misses, up-to-date prerequisites, --info diagnostics: https://docs.gradle.org/current/userguide/build_cache_debugging.html
- **Gradle Configuration Cache:** task action constraints và Providers: https://docs.gradle.org/current/userguide/configuration_cache.html
- **Gradle TestKit:** functional tests for custom plugin tasks: https://docs.gradle.org/current/userguide/test_kit.html
- **Gradle Java Testing:** JUnit Platform, Java 17 toolchain/test task: https://docs.gradle.org/current/userguide/java_testing.html

**Kết luận:** Một task sinh mã Gradle đúng không phải chỉ viết ra một file Java. Task cần **khai đầy đủ inputs/outputs**, tạo deterministic/relocatable bytes, giữ unique output directory và nối **TaskProvider** vào source set để compiler biết producer. Khi inputs/outputs local không đổi, Gradle có thể **UP-TO-DATE**; khi output local bị clean nhưng cache đã warm và key khớp, Gradle có thể **FROM-CACHE**. Lab dùng Java 17+, JUnit và `-Pgreeting` cho phép kiểm chứng bằng generated source, stdout, JUnit tests, task outcomes và SHA-256 thực tế — không chỉ bằng một dòng build SUCCESSFUL.