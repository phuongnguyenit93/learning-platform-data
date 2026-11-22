# Cấu hình Gradle Build Cache cục bộ và từ xa: nguyên lý, ví dụ Java 17 và vận hành CI

## 1. Mục tiêu và phạm vi

Một build Java có thể mất thời gian biên dịch, kiểm thử và tạo những artifacts đã được tạo **đúng y hệt** ở lần chạy trước, trên một nhánh Git khác hoặc thậm chí trên máy CI khác. **Gradle Build Cache** giải quyết bài toán này bằng cách lưu **đầu ra của các task có thể cache** theo **cache key tính từ đầu vào**, rồi tái sử dụng đầu ra khi một build tiếp theo có đầu vào tương đương.

Chủ đề của bài là **cấu hình Build Cache tại máy local và máy chủ remote**, không phải tải dependency từ Maven Central. Hai mục tiêu thực tế:

1. Developer chạy lại build hoặc `clean` vẫn có thể lấy task outputs từ **local cache** khi input fingerprint khớp.
2. CI build đáng tin có thể **đẩy outputs** lên remote cache; developer và CI jobs khác **đọc lại** để giảm thời gian, không cần chạy task action.

Một sơ đồ:

```text
       Gradle task: inputs + implementation + output property names
                              |
                              v
                     Calculate cache key
                              |
                +-------------+-------------+
                |                           |
          local cache hit?                  no
                |                           |
             restore                        v
                |                   remote cache hit?
                |                      /         \
                |                    yes          no
                |                     |            |
                |                  restore      execute task
                |                     |            |
                |                populate local   store outputs
                |                     |            |
                +---------------------+------------+
                                      |
                                      v
                              output verified by build
```

Đây là mô hình khái niệm. Trước cache lookup, Gradle có thể xác định task đang **UP-TO-DATE** và không cần khôi phục gì. Chỉ các task đủ điều kiện caching mới được dùng cache, không phải mọi task có tên trong task graph.

### Bạn sẽ học được

- Phân biệt **UP-TO-DATE**, **FROM-CACHE**, `SUCCESS` và các loại cache khác.
- Bật hoặc tắt Build Cache bằng `--build-cache`, `--no-build-cache` và `org.gradle.caching=true`.
- Cấu hình `local { ... }` trong `settings.gradle.kts` và `settings.gradle`.
- Cấu hình `remote<HttpBuildCache> { ... }` và `remote(HttpBuildCache) { ... }`, HTTPS/credentials/read vs push.
- Viết **Java 17 custom task** sử dụng `@CacheableTask`, `@Input Property<String>` và `@OutputFile RegularFileProperty` để kiểm tra thực tế.
- Tái hiện local hit sau `clean` và thiết kế kiểm thử remote cache giữa hai build environments.
- Quản trị remote cache an toàn: trusted CI push, pull-only PR/developer, cache namespaces, ACL/TLS.
- Chẩn đoán misses, task không cacheable, lỗi HTTP, cache poisoning, dependency/toolchain drift và các bẫy vận hành.

## 2. Phân biệt Build Cache với những cơ chế dễ nhầm

| Cơ chế | Lưu/tái sử dụng gì? | Dấu hiệu quan sát |
| --- | --- | --- |
| **Task UP-TO-DATE** | Dùng chính outputs còn nằm trong project hiện tại khi inputs/outputs không đổi. | `UP-TO-DATE`; không cần tải cache entry. |
| **Local Build Cache** | Lưu task outputs cacheable trong directory cache trên **máy hiện tại**. | `FROM-CACHE` nếu outputs đã mất nhưng cache key hit. |
| **Remote Build Cache** | Lưu task outputs cacheable trên server dùng chung, thường qua HTTPS. | `FROM-CACHE` nếu entry đến từ remote; cần logs/metrics để biết nguồn. |
| **Configuration Cache** | Lưu cấu hình build/task graph để bỏ qua pha configuration khi inputs của configuration không đổi. | `Configuration cache entry reused` hoặc tương đương. |
| **Dependency Cache** | Lưu JAR/POM/module metadata tải từ repositories. | Dependency resolution có thể dùng artifacts đã tải. |
| **Incremental Compilation** | Compile phần source bị ảnh hưởng thay vì biên dịch tất cả. | Compiler/task logs và incremental analysis. |
| **Gradle Daemon** | Giữ một JVM Gradle để tránh startup overhead. | Daemon reused trong logs. |

**Build Cache không phải Configuration Cache.** Build Cache tối ưu **execution** bằng cách tái sử dụng task outputs. Configuration Cache tối ưu **configuration** bằng cách tái sử dụng task graph/configured state. Hai cơ chế có thể cùng bật nhưng cache key, dữ liệu và nguyên nhân cache miss khác nhau.

**Build Cache không phải dependency cache.** Local Build Cache không phải một Maven repository. Lệnh `--offline` chỉ bảo Gradle không tìm dependencies/distributions chưa sẵn qua mạng theo những cơ chế liên quan; nó không “tạo ra” cached task output cho input key chưa từng được build. Remote Build Cache cũng không thay thế Maven Central/Artifactory.

### 2.1. Đọc task outcome đúng

| Outcome của Gradle task | Diễn giải |
| --- | --- |
| `SUCCESS` | Task thực thi thành công, có thể sau cache miss. |
| `UP-TO-DATE` | Gradle thấy outputs hiện có phù hợp inputs nên không chạy task. |
| `FROM-CACHE` | Gradle phục hồi outputs từ một build cache entry; task action không chạy. |
| `NO-SOURCE` | Task cần source nhưng không có source phù hợp. |
| `SKIPPED` | Task được bỏ qua theo rule, ví dụ `onlyIf { false }`. |
| `FAILED` | Task thực thi nhưng lỗi. |

Task `clean` thường là task khác biệt và không đại diện cho cached compilation. Khi một command có nhiều tasks, hãy kiểm tra outcome của **task bạn muốn đo**, ví dụ `:writeGreeting` hoặc `:compileJava`, thay vì chỉ đọc `BUILD SUCCESSFUL`.

## 3. Build cache key được hình thành như thế nào?

Gradle không lưu entry theo mỗi `task.name`. Một cacheable task được định danh bằng **cache key** dựa trên những thành phần như:

- **Task implementation** và các task action implementations, gồm classpath của chúng.
- **Tên các output properties** được khai báo.
- **Tên và giá trị của input properties**.
- **Input files/content fingerprints**, cùng path sensitivity/classpath normalization khi được khai báo.
- Những yếu tố build logic/plugin/Gradle version có ảnh hưởng đến cách task thực thi.

Hai task có cùng tên nhưng khác source files, Java compiler version hoặc plugin implementation **không mặc nhiên chia sẻ key**. Ngược lại, cùng task input/implementation fingerprint có thể tái dùng outputs giữa những project directories khác nhau nếu task được mô hình hóa **relocatable**.

```text
key = HASH(taskImplementation,
           taskActions,
           inputPropertyNamesAndValues,
           inputFileFingerprints,
           outputPropertyNames,
           relevantClasspathAndTooling)
```

Công thức chỉ để hiểu, **không phải thuật toán SHA/key serialization nội bộ chính xác** của Gradle. Đừng tự viết SHA của source file rồi cho rằng đã tái tạo được Gradle build cache key.

### 3.1. Cache hit có nghĩa là task action có chạy không?

Không. Khi `FROM-CACHE`, Gradle khôi phục outputs mà không chạy lại task action. Điều này chính là lợi ích, nhưng nó đòi hỏi task **deterministic**, khai báo **đủ inputs/outputs** và không dựa vào side effects không được cache, ví dụ gửi email, gọi API thay đổi dữ liệu hoặc cập nhật database.

Một task ghi file và đồng thời gọi external API **không nên chỉ gắn `@CacheableTask`** nếu external side effect cần diễn ra mỗi lần. Khi task được phục hồi từ cache, external call sẽ không xảy ra.

## 4. Bật Gradle Build Cache

**Theo tài liệu Gradle, Build Cache không được bật mặc định cho các build invocations thông thường.** Có ba thao tác chủ yếu:

Chỉ bật trong một lần chạy:

```bash
./gradlew --build-cache :compileJava
```

Bật mặc định theo repository bằng **`gradle.properties`**:

```properties
org.gradle.caching=true
```

Chủ động tắt dù property đang bật:

```bash
./gradlew --no-build-cache :compileJava
```

Lệnh CLI có tác dụng cho invocation cụ thể; `gradle.properties` là policy mặc định để developer và CI không phải gõ `--build-cache` mỗi lần. Cấu hình `buildCache { ... }` trong **Settings** quyết định **cache backend** local/remote, nhưng bản thân việc khai báo backend **không thay thế thao tác bật Build Cache**.

### 4.1. Bật cache không ép tất cả tasks cacheable

Một custom `DefaultTask` thiếu `@CacheableTask` hoặc `outputs.cacheIf(...)` phù hợp sẽ không tự cache vì bạn bật flag. Gradle đã có những built-in cacheable task types như `JavaCompile`, `Test`, `Javadoc` và một số tasks khác; nhiều tác vụ `Copy`/`Exec`/`JavaExec`/`Jar` thường không được Gradle định nghĩa cacheable mặc định do chi phí/lợi ích hoặc semantics của chúng.

Hãy kiểm tra task thật. Không suy luận “toàn bộ build được cache” chỉ vì `--build-cache` đã xuất hiện trên command line.

## 5. Local Build Cache: cấu hình tối thiểu

Mặc định, Gradle có **`DirectoryBuildCache`** là local cache backend, nằm dưới **Gradle User Home** (thường `~/.gradle/caches/`, không nên hard-code tên subdirectory nội bộ). Khi Build Cache được bật, local backend mặc định đã được cấu hình; bạn **không cần** viết `buildCache.local` trừ khi muốn thay directory hoặc chính sách read/write.

### 5.1. Kotlin DSL: settings.gradle.kts

```kotlin
rootProject.name = "gradle-cache-lab"

buildCache {
    local {
        directory = File(rootDir, ".local-build-cache")
    }
}
```

Đặt cache directory **ngoài `build/`** để `clean` không xóa nó; `.local-build-cache` ở repository root phù hợp để quan sát trong lab. Thêm vào **`.gitignore`**:

```gitignore
.gradle/
.local-build-cache/
build/
**/build/
```

**Caution:** Trong repository sản xuất, dùng mặc định Gradle User Home hoặc cache directory được team chuẩn hóa sẽ tránh mỗi checkout tạo một cache lớn; thư mục local tại root chủ yếu phục vụ thí nghiệm và được ignore khỏi Git.

### 5.2. Groovy DSL: settings.gradle

```groovy
rootProject.name = 'gradle-cache-lab'

buildCache {
    local {
        directory = new File(rootDir, '.local-build-cache')
    }
}
```

Kotlin và Groovy thể hiện cùng một backend. **Chỉ chọn một Settings DSL cho project**, không đặt cả `settings.gradle` và `settings.gradle.kts` như hai bản cùng lúc rồi giả định Gradle sẽ kết hợp chúng.

### 5.3. Local enabled và push nghĩa là gì?

Theo API `DirectoryBuildCache`:

- `enabled`: cho phép **đọc/tái dùng** cache backend.
- `push`: cho phép **ghi/store** cache entries mới vào backend khi nó enabled.

Theo mặc định, **local cache enabled và push enabled**; remote thường **push disabled**. Muốn cache local **read-only** có thể đặt `push=false` theo DSL/Gradle version được hỗ trợ. Nếu `enabled=false`, không thể dùng nó để read/hit; việc ghi cũng không có ý nghĩa.

Cấu hình cụ thể cho local read-only (Groovy, phần cấu hình thay thế):

```groovy
buildCache {
    local {
        directory = new File(rootDir, '.local-build-cache')
        enabled = true
        push = false
    }
}
```

Đây là chính sách riêng, **không phải cấu hình khuyến nghị mặc định cho mọi developer**. Nếu đang học cache hit, giữ local push mặc định để lần đầu có thể lưu entry.

### 5.4. Directory và cleanup

Local cache có thể tăng kích thước theo số cacheable task fingerprints. Gradle định kỳ dọn entries không được dùng trong một thời gian để tiết kiệm ổ đĩa. Trong Gradle hiện hành, **Gradle User Home cleanup** có cơ chế cấu hình thời gian giữ entries qua init script/`caches` settings; không nên chèn các dòng cleanup không có trong API phiên bản đang dùng vào `build.gradle.kts`.

Với cache directory tùy chỉnh, không xóa bừa đang lúc Gradle chạy. Kiểm soát dung lượng, retention, backup policy và workspace cleanup của CI. Remote cache có lifecycle/eviction do backend/server quản lý, không tự theo policy dọn local.

## 6. Demo có thể chạy: cacheable Java 17 task + ứng dụng Java

Bài lab dùng một Gradle project và **`buildSrc`** nhỏ để chứa Java task type. `buildSrc` cung cấp build logic classpath, **không phải runtime dependency của app**. Custom task dùng Gradle API nên compile thông qua Gradle; ứng dụng Java 17 bên dưới có thể compile bằng `javac` độc lập.

### 6.1. Cấu trúc dự án

```text
gradle-cache-lab/
├── settings.gradle.kts
├── gradle.properties
├── .gitignore
├── build.gradle.kts
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/java/demo/cache/WriteGreetingTask.java
└── src/
    └── main/java/demo/cache/App.java
```

Chạy ví dụ với **Gradle Wrapper tương thích JDK 17**, có `gradlew`/`gradlew.bat` và wrapper files đã được tạo/commit. Nếu dùng Java toolchain 17, JDK 17 phải có sẵn hoặc được Gradle toolchain provisioning cấu hình. Việc ví dụ dùng toolchain không có nghĩa Gradle Wrapper tự động cài JDK trong mọi môi trường.

**`gradle.properties`:**

```properties
org.gradle.caching=true
```

**`settings.gradle.kts`:** dùng bản local ở mục 5.1.

### 6.2. buildSrc/build.gradle.kts

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(gradleApi())
}
```

`gradleApi()` cung cấp những classes như `DefaultTask`, `Property`, `RegularFileProperty` và task annotations. Không cần Maven Central để resolve một library bên ngoài cho task trong bài lab này. Gradle quản lý việc compile `buildSrc` trước khi main build script import type.

### 6.3. buildSrc/src/main/java/demo/cache/WriteGreetingTask.java

```java
package demo.cache;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

@CacheableTask
public abstract class WriteGreetingTask extends DefaultTask {
    @Input
    public abstract Property<String> getRecipient();

    @OutputFile
    public abstract RegularFileProperty getDestination();

    @TaskAction
    public void writeGreeting() throws IOException {
        String recipient = getRecipient().get().strip();
        if (recipient.isEmpty()) {
            throw new IllegalArgumentException(
                "recipient must not be blank"
            );
        }

        Path output = getDestination().get().getAsFile().toPath();
        Files.createDirectories(output.getParent());
        Files.writeString(
            output,
            "Hello, " + recipient + "!\n",
            StandardCharsets.UTF_8
        );
        getLogger().lifecycle("ACTION_EXECUTED=" + recipient);
    }
}
```

**Vì sao nó có khả năng cache?**

1. `@CacheableTask` **opt in** cho task output caching; annotation chỉ có giá trị khi outputs thực sự tái sử dụng được và inputs được khai báo đầy đủ.
2. `@Input Property<String>` khiến giá trị `recipient` tham gia input fingerprint.
3. `@OutputFile RegularFileProperty` khai báo đầu ra do task tạo để Gradle kiểm tra, lưu và phục hồi.
4. Task viết UTF-8 với newline `\n` cố định; output deterministic theo `recipient`.
5. Task action không đọc clock/network/random/hostname, không ghi file khác và không cần `Project` ở execution time.
6. `getLogger().lifecycle("ACTION_EXECUTED=...")` là **dấu hiệu quan sát**: xuất hiện khi action chạy; thường không xuất hiện nếu `UP-TO-DATE` hay `FROM-CACHE`.

Đây là **Gradle task class**, không phải Java standard-library chương trình độc lập. Bạn **không thể chỉ** `javac WriteGreetingTask.java` khi classpath không có Gradle API. Phần `App.java` ở dưới là ví dụ Java 17 có `main` chạy độc lập.

### 6.4. Root build.gradle.kts

```kotlin
import demo.cache.WriteGreetingTask

plugins {
    id("java")
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.cache.App")
}

tasks.register<WriteGreetingTask>("writeGreeting") {
    group = "build"
    description = "Generate a deterministic text file"

    recipient.set(
        providers.gradleProperty("who").orElse("Gradle")
    )
    destination.set(
        layout.buildDirectory.file("generated/greeting.txt")
    )
}
```

Task `writeGreeting` là task riêng, output nằm dưới `build/generated/` nên Gradle `clean` có thể xóa output **nhưng không xóa `.local-build-cache/`**. Provider `gradleProperty("who")` cho phép đổi input qua `-Pwho=...`, giúp kiểm tra cache key đổi khi đầu vào đổi.

### 6.5. src/main/java/demo/cache/App.java

```java
package demo.cache;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Hello, Cache!");
    }
}
```

Đây là Java 17-compatible standard-library source, có thể kiểm tra bằng `javac/java` mà không cần Gradle:

```bash
mkdir -p manual-out
javac --release 17 -d manual-out src/main/java/demo/cache/App.java
java -cp manual-out demo.cache.App
```

**Stdout chính xác:**

```text
Hello, Cache!
```

Với Gradle:

```bash
./gradlew -q run
```

Output ứng dụng vẫn là:

```text
Hello, Cache!
```

`run` là `JavaExec` task và không nên mặc định kết luận nó sẽ `FROM-CACHE`. Để thực hành local cache, hãy quan sát **`writeGreeting`** (đã đánh dấu `@CacheableTask`) hoặc task built-in `compileJava`.

## 7. Kiểm chứng local Build Cache qua ba lượt chạy

Từ project mới, nơi chưa có cache entry cho task:

### Lượt A — task action được thực thi

```bash
./gradlew --build-cache writeGreeting --info
```

Trong một môi trường sạch, task `:writeGreeting` có outcome `SUCCESS` và log marker:

```text
ACTION_EXECUTED=Gradle
```

Đọc file (Linux/macOS):

```bash
cat build/generated/greeting.txt
```

Stdout file chính xác:

```text
Hello, Gradle!
```

PowerShell tương đương:

```powershell
Get-Content -LiteralPath build/generated/greeting.txt
```

Nếu trước đó cùng task key đã được cache, lượt A có thể là `FROM-CACHE` ngay; muốn kiểm thử cold start, dùng một **cache directory mới** hoặc môi trường cô lập theo policy, không xóa global cache của developer.

### Lượt B — output vẫn còn nên UP-TO-DATE

```bash
./gradlew --build-cache writeGreeting --info
```

Khi không đổi task inputs/implementation/output file, outcome kỳ vọng:

```text
> Task :writeGreeting UP-TO-DATE
```

Task action không cần chạy, nhưng **chưa chứng minh cache entry được restore**. Đây là Gradle up-to-date check đối với outputs **đang còn** trên filesystem.

### Lượt C — xóa outputs bằng clean, lấy từ local cache

```bash
./gradlew --build-cache clean writeGreeting --info
```

Nếu trước đó entry đã được ghi vào `.local-build-cache` và không thay inputs, outcome kỳ vọng:

```text
> Task :writeGreeting FROM-CACHE
```

`clean` xóa directory `build/`; nó không xóa cache local ở `.local-build-cache/` trong root của lab. Gradle tra cache key, phục hồi `build/generated/greeting.txt` mà không gọi `WriteGreetingTask.writeGreeting()`.

Kiểm tra lại:

```bash
cat build/generated/greeting.txt
```

Stdout file:

```text
Hello, Gradle!
```

**Đây là một kết quả có điều kiện**, không phải cam kết mọi máy luôn in đúng Gradle task log. Nếu task implementation hoặc Gradle version/inputs thay đổi, entry bị eviction, backend bị disable hoặc `--no-build-cache` đang có hiệu lực, task có thể `SUCCESS` thay vì `FROM-CACHE`. File content do Java task viết thì vẫn phải đúng khi build thành công.

### 7.1. Lượt D — đổi input buộc tạo key mới

```bash
./gradlew --build-cache writeGreeting -Pwho=Team --info
```

Lần đầu với `who=Team`, task thường chạy `SUCCESS` vì `@Input` đổi. File sẽ chứa:

```text
Hello, Team!
```

Sau đó:

```bash
./gradlew --build-cache writeGreeting -Pwho=Team --info
```

Nếu output vẫn còn, outcome `UP-TO-DATE`. Nếu chạy `clean` rồi `writeGreeting -Pwho=Team`, có thể `FROM-CACHE` từ entry của input Team. Đây là cách kiểm tra **cache key phụ thuộc input**, không chỉ cache tồn tại hay không.

### 7.2. Tắt Build Cache để phân biệt behavior

```bash
./gradlew --no-build-cache clean writeGreeting --info
```

Vì outputs đã bị xóa và cache tắt, action phải chạy lại (`SUCCESS`) trong lab, thay vì phục hồi cached output. `--no-build-cache` không tắt up-to-date checks, nên nếu không `clean` và outputs vẫn còn, task vẫn có thể `UP-TO-DATE`.

### 7.3. Vì sao không dùng --rerun-tasks để đo cache hit?

`--rerun-tasks` buộc task thực thi lại thay vì dựa vào những work avoidance checks thông thường. Nó phù hợp để debug hoặc xác minh task có thể chạy lại, **không thích hợp để đo cache hit**. Để kiểm tra `FROM-CACHE`, giữ cache backend và dùng `clean` hoặc xóa output được kiểm soát, không kết hợp `--rerun-tasks`.

## 8. Groovy DSL đầy đủ cho cùng demo

Giữ nguyên hai Java sources (`WriteGreetingTask.java`, `App.java`). Chọn **`settings.gradle`** thay `settings.gradle.kts`:

```groovy
rootProject.name = 'gradle-cache-lab'

buildCache {
    local {
        directory = new File(rootDir, '.local-build-cache')
    }
}
```

**`buildSrc/build.gradle`:**

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation gradleApi()
}
```

**`build.gradle`:**

```groovy
import demo.cache.WriteGreetingTask

plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.App'
}

tasks.register('writeGreeting', WriteGreetingTask) {
    group = 'build'
    description = 'Generate a deterministic text file'
    recipient.set(providers.gradleProperty('who').orElse('Gradle'))
    destination.set(layout.buildDirectory.file('generated/greeting.txt'))
}
```

**`gradle.properties`** và `.gitignore` giữ nguyên. Các commands `./gradlew --build-cache writeGreeting`, `./gradlew --build-cache clean writeGreeting`, `./gradlew -q run` có cùng semantics. Không đặt cả hai bản Kotlin/Groovy build script trong cùng một Gradle root rồi giả định Gradle sẽ chọn bản “đúng”.

## 9. Remote Build Cache khác local ở đâu?

**Local cache** phù hợp tái sử dụng trên một developer machine hoặc một CI runner giữ lại Gradle User Home. **Remote cache** cho phép **nhiều máy/runner** tìm cùng task outputs, nên lợi ích lớn khi CI workers là ephemeral hoặc team có nhiều developer.

Mô hình:

```text
            Trusted CI (write/read)
                       |
                       | PUT cache entry if allowed
                       v
           HTTPS Build Cache Server
             /                    \
        GET hit                  GET hit
          /                         \
 Developer A (read-only)       PR CI (read-only)
  local L1 cache                local L1 cache
```

Gradle gọi local cache trước; nếu local miss và remote được enable, nó gọi remote. Khi remote hit, Gradle lưu output đã lấy về vào local cache; build sau có thể hit local mà không gọi remote nữa. Kết quả task trên console đều có thể là `FROM-CACHE`, nên cần `--info`/Build Scan/server metrics để xác định cache source.

### 9.1. Thứ tự đọc local/remote

Khi Build Cache được bật và cả hai backends được enable:

1. Gradle tính key cho cacheable task.
2. Task có outputs UP-TO-DATE thì có thể bỏ qua cache lookup.
3. Nếu cần reuse outputs, Gradle kiểm tra **local cache** trước.
4. Khi local miss, nó kiểm tra **remote cache**.
5. Nếu remote có entry, Gradle phục hồi output và **đưa entry vào local cache**.
6. Nếu không có entry, task thực thi, rồi outputs đủ điều kiện được store vào caches có `push=true`.

**Local default push=true, remote default push=false.** Đây là một mặc định tốt: developer không vô tình đẩy outputs từ máy cá nhân vào kho chung chỉ vì có URL cache.

## 10. Cấu hình remote HttpBuildCache bằng Kotlin DSL

Đây là cấu hình **thay thế `settings.gradle.kts` local-only** của mục 5, không phải file thứ hai. Nó dùng:
- Local cache directory trong project cho lab.
- URL remote tùy chọn từ Gradle property `remoteCacheUrl`.
- Username/password từ **environment secrets**.
- Remote push chỉ khi environment `CACHE_PUSH_ALLOWED` có giá trị chính xác `true`.
- HTTPS và Gradle trust store mặc định; không disable TLS verification.

**`settings.gradle.kts`:**

```kotlin
import org.gradle.caching.http.HttpBuildCache

rootProject.name = "gradle-cache-lab"

val remoteUrl = providers.gradleProperty("remoteCacheUrl").orNull
val remoteUser = providers.environmentVariable("REMOTE_CACHE_USER").orNull
val remotePassword =
    providers.environmentVariable("REMOTE_CACHE_PASSWORD").orNull

// Biến này chỉ được cấp trong trusted CI job.
val allowRemotePush =
    providers.environmentVariable("CACHE_PUSH_ALLOWED").orNull == "true"

buildCache {
    local {
        directory = File(rootDir, ".local-build-cache")
    }

    if (!remoteUrl.isNullOrBlank()) {
        remote<HttpBuildCache> {
            url = uri(remoteUrl)
            isPush = allowRemotePush

            if (!remoteUser.isNullOrBlank()
                    && !remotePassword.isNullOrBlank()) {
                credentials {
                    username = remoteUser
                    password = remotePassword
                }
            }
        }
    }
}
```

**Tính runnable của ví dụ:** Khi không khai báo `remoteCacheUrl`, chỉ local cache được dùng và không có network call tới remote. Khi có URL, nó phải trỏ tới **một remote Gradle Build Cache HTTP backend thực sự**, chứ không phải một directory web trống. Nếu server yêu cầu Basic Auth, phải cung cấp cả hai environment credentials.

**Không coi `CACHE_PUSH_ALLOWED=true` là bằng chứng job đáng tin.** Đó chỉ là **tín hiệu** mà Settings script đọc. Trên CI thật phải dùng protected branch/tag, job permissions, approval và **server-side write ACL**, không cho một untrusted PR tự đặt env var rồi được server chấp nhận PUT.

### 10.1. Ví dụ invocation pull-only của developer

Khi đã có URL backend và access được cấp:

```bash
./gradlew -PremoteCacheUrl=https://cache.example.org/cache/ \
  --build-cache clean writeGreeting
```

Địa chỉ `cache.example.org` chỉ là **placeholder minh họa địa chỉ HTTPS**, không phải một server có sẵn. Nếu muốn chạy lab offline/local, **bỏ `-PremoteCacheUrl=...`**; không có URL sẽ không cấu hình remote.

Credentials nên truyền qua environment/secret manager, ví dụ CI variables có tên `REMOTE_CACHE_USER` và `REMOTE_CACHE_PASSWORD`. **Không ghi password trực tiếp vào repository `settings.gradle.kts`, `gradle.properties` được commit hoặc command-line output.**

### 10.2. Remote push của trusted CI

Trong trusted CI có quyền upload, môi trường được cấp **`CACHE_PUSH_ALLOWED=true`** và write credentials; chạy cùng `./gradlew --build-cache ...`. Nếu chỉ cần đọc, để biến này absent hoặc khác `true`.

Với server đã có ACL:
- **Trusted main/release CI**: được GET + PUT.
- **Developer và untrusted PR CI**: chỉ GET, không PUT.
- **Unknown external jobs**: không có credentials hoặc bị giới hạn namespace.
- **Secrets**: được cấp bởi CI secret manager, không đi vào pull request code/logs.

### 10.3. Cấu hình Kotlin rút gọn cho backend public nội bộ không yêu cầu Basic Auth

Nếu môi trường test có một backend đã được bảo vệ ở network layer và không dùng Basic Auth, cấu hình tối thiểu chỉ cần:

```kotlin
import org.gradle.caching.http.HttpBuildCache

buildCache {
    remote<HttpBuildCache> {
        url = uri("https://cache.example.org/cache/")
        isPush = false
    }
}
```

Đoạn này là **snippet thêm vào Settings thích hợp**, không phải lời khuyên cho phép public anonymous GET/PUT. Trong sản xuất, authentication + authorization ở server vẫn được khuyến nghị. Có thể bảo vệ bằng mTLS/reverse proxy/ACL tương thích nếu cơ sở hạ tầng dùng giải pháp khác.

## 11. Cấu hình remote bằng Groovy DSL

Dùng nội dung sau thay `settings.gradle` local-only:

```groovy
import org.gradle.caching.http.HttpBuildCache

rootProject.name = 'gradle-cache-lab'

def remoteUrl = providers.gradleProperty('remoteCacheUrl').orNull
def remoteUser = providers.environmentVariable('REMOTE_CACHE_USER').orNull
def remotePassword =
    providers.environmentVariable('REMOTE_CACHE_PASSWORD').orNull

def allowRemotePush =
    providers.environmentVariable('CACHE_PUSH_ALLOWED').orNull == 'true'

buildCache {
    local {
        directory = new File(rootDir, '.local-build-cache')
    }

    if (remoteUrl) {
        remote(HttpBuildCache) {
            url = uri(remoteUrl)
            push = allowRemotePush

            if (remoteUser && remotePassword) {
                credentials {
                    username = remoteUser
                    password = remotePassword
                }
            }
        }
    }
}
```

So sánh:
- Kotlin: `remote<HttpBuildCache> { ... }` và `isPush = allowRemotePush`.
- Groovy: `remote(HttpBuildCache) { ... }` và `push = allowRemotePush`.
- Cả hai: `url` là remote cache URL; `credentials` dùng username/password khi backend cần authentication.
- Hai bản giữ default local cache push; remote push bị quyết định bằng biến môi trường trusted.

### 11.1. Đặt cấu hình ở đâu?

**Build Cache backend configuration nằm trong Settings**, không phải `repositories { ... }` của `build.gradle.kts`. Những DSL blocks khác nhau có chức năng riêng:

```kotlin
repositories {
    mavenCentral() // Nơi resolve dependencies.
}
```

```kotlin
buildCache {
    local { ... }           // Nơi Gradle lấy/lưu task outputs.
    remote<HttpBuildCache> { ... }
}
```

Đừng để `remoteCacheUrl` thành URL một Maven repository hay thêm Maven `credentials` vào block build cache một cách ngẫu nhiên. HTTP Build Cache API mong đợi **GET/PUT entries theo cache keys** chứ không phải Maven GAV/POM layout.

## 12. Remote HTTP backend phải hỗ trợ gì?

Gradle `HttpBuildCache` thao tác theo giao thức:
- **GET `<base-url>/<cache-key>`**: khi có entry, trả HTTP `2xx` với cache entry body.
- **GET 404**: nghĩa là cache miss, không phải task bị lỗi.
- **PUT `<base-url>/<cache-key>`**: gửi entry khi push được bật và backend cho phép; HTTP `2xx` biểu diễn store thành công.
- **PUT 413 Payload Too Large**: server có thể từ chối entry quá lớn; Gradle không nhất thiết coi đây là một lỗi build, nhưng entry đó sẽ **không hữu ích cho các consumer sau**.
- **401/403**: thường có vấn đề authentication/authorization hoặc job không có quyền.
- **5xx, timeout, reset**: backend/network failure, Gradle có logic retry/disable remote trong invocation theo loại lỗi.

Không thể lấy một Nginx static file server chỉ hỗ trợ GET làm remote Build Cache nếu không có cơ chế PUT/storage semantics tương thích. Cần một cache node/backend đúng API (ví dụ Gradle Build Cache Node/Develocity hoặc giải pháp tương thích).

### 12.1. Redirects và proxy

Gradle docs mô tả redirects `3xx`, nhưng khi PUT, **307/308** là những codes cho phép giữ method PUT và body trong quá trình follow. Các redirect types khác có thể khiến request thành GET, nên reverse proxy của cache nên tránh redirect PUT bằng các mã không phù hợp.

Proxy có thể cache GET, chặn PUT, giới hạn body size, cắt timeout hoặc biến URL có slash cuối thành redirect. Khi test một endpoint, kiểm tra **cả GET và PUT** với credentials/role tương ứng, không chỉ xem trang chủ trên browser.

### 12.2. HTTP expect-continue

Backend có thể hỗ trợ `Expect: 100-continue` giúp biết trước có nên gửi payload lớn. Gradle `HttpBuildCache` có property `isUseExpectContinue` (Kotlin) hoặc `useExpectContinue` (Groovy). Nó hữu ích nếu server thường reject lớn hoặc redirects, nhưng một số proxies không hỗ trợ ổn định.

Tùy chọn **bổ sung** khi đã kiểm tra server:

```kotlin
remote<HttpBuildCache> {
    url = uri("https://cache.example.org/cache/")
    isPush = false
    isUseExpectContinue = true
}
```

Không tự bật vì cho rằng luôn cải thiện performance; thử với backend thật và đo latency.

### 12.3. TLS: không bật allowUntrustedServer để chữa certificate error

Nếu `https://` endpoint dùng certificate chưa được JVM trust store tin cậy, giải pháp chuẩn là:
1. Sử dụng certificate có chain hợp lệ và hostname đúng.
2. Cập nhật Java trust store hoặc cấu hình trust store được quản lý.
3. Kiểm tra reverse proxy/TLS termination.

Gradle có flag `isAllowUntrustedServer` và `isAllowInsecureProtocol` nhưng bật chúng có thể cho phép man-in-the-middle hoặc giả danh cache server. **Không đưa những flags đó vào ví dụ production.** Cần xác thực server thật vì cache entry có thể chứa code/artifacts thực thi được.

## 13. Tại sao remote cache là một ranh giới bảo mật?

Gradle security guidance nhấn mạnh **Build Cache entries không được Gradle tự ký hoặc xác minh chữ ký**. Khi một job đọc output từ remote cache, nó **tin vào ACL và tính toàn vẹn của chính backend**. Nếu untrusted PR có quyền PUT vào cache chung, kẻ tấn công có thể tạo entry chứa compiled class/artifact độc hại mà job đáng tin dùng lại.

**Chính sách nên áp dụng:**

- Remote backend dùng **HTTPS** với certificate đáng tin.
- GET/PUT có authentication/authorization, tối thiểu theo vai trò.
- Chỉ trusted CI jobs được **push** (theo protected branch/tag, approval, server-side ACL).
- Developer/untrusted PR CI **pull-only**, hoặc dùng cache namespace tách biệt nếu threat model đòi hỏi.
- Không chia sẻ write namespace từ fork/untrusted branch với release CI.
- Không cache tasks có secret-dependent outputs hoặc không khai báo đúng inputs.
- Giữ audit/access logs, metrics và retention controls trên backend.
- Không cho remote cache endpoint công khai trên Internet mà không được bảo vệ.

**Tối ưu tốc độ không quan trọng hơn độ tin cậy.** Một cache hit trên outputs bị nhiễm độc có thể nghiêm trọng hơn một build chậm.

### 13.1. Cờ isPush không thay thế server-side quyền

Ví dụ Settings script đặt `isPush = false` khi chạy trên máy developer là một lớp phòng ngừa, nhưng nếu credentials có quyền ghi bị lộ, một process khác vẫn có thể gọi HTTP PUT. Vì vậy **backend phải từ chối PUT từ read-only identities**. Ngay cả CI job mang biến `CACHE_PUSH_ALLOWED=true` cũng không nên có quyền write tới mọi namespace/repository.

### 13.2. Credentials và log hygiene

- Không hard-code `REMOTE_CACHE_PASSWORD` vào Git.
- Không in secrets ra `--info` logs/script println hoặc debug output.
- Không đặt tokens vào URL query parameters vì proxy/server logs có thể lưu URL.
- Không dùng project property `-PremoteCachePassword=...` với giá trị thật trong CLI nếu process list/CI logs ghi lại nó.
- Dùng secret manager/environment with masking, short-lived credentials khi backend hỗ trợ.
- Không đưa private tokens vào source files hoặc output của cacheable tasks; cache outputs có thể được phân phối tới machines khác.

## 14. Chiến lược CI phổ biến: CI ghi, developer đọc

Một pipeline thực tế có thể được chia thành:
- **PR CI:** `./gradlew --build-cache check`, remote pull-only, không nhận write secrets.
- **Main/Release CI:** `./gradlew --build-cache clean check`, được cấp remote push khi đã trusted.
- **Developer:** remote pull-only, local push mặc định; tránh upload outputs từ trạng thái working tree không được review.
- **Nightly:** đo cache hit/miss, refresh verified inputs, kiểm tra plugin/toolchain compatibility.

Mô hình cache 2 tầng:

```text
Trusted CI runner #1
  local L1 miss --> compile task --> push remote L2
                              |
                              v
                     Remote shared cache
                              |
                  +-----------+-----------+
                  |                       |
            Developer L1 miss       CI runner #2 L1 miss
                  |                       |
                  +----- GET remote ------+
                           |
                    restore FROM-CACHE
                           |
                   store entry into L1
```

Để cache **có giá trị giữa máy**, task inputs cần được cấu hình đúng và thường **relocatable**. Không phụ thuộc ngầm absolute paths, timestamps, hostnames, timezone, random seeds hoặc environment variables không khai báo.

### 14.1. Trình tự kiểm chứng remote giữa hai workspaces

Giả sử đã có backend thật `https://cache.example.org/cache/` và two allowed identities:

1. **Trusted CI A:** checkout commit X, dùng Gradle/JDK/plugin versions đã chốt, bật remote push, chạy `clean writeGreeting`. Kiểm tra logs/server metrics cho cache PUT và entry được store.
2. **Developer/CI B:** checkout **cùng source commit X** vào workspace mới, local cache trống, cấu hình remote GET và `isPush=false`, chạy cùng task cùng `-Pwho=Gradle`.
3. Trên B, nếu cache key khớp và remote có entry, `:writeGreeting FROM-CACHE`; output file có `Hello, Gradle!`.
4. Chạy lại trên B khi output còn sẽ `UP-TO-DATE`.
5. Nếu xóa output bằng `clean`, B có thể lấy từ **local** vì entry remote đã được copy về local ở bước 2.

**Điểm rất dễ đo sai:** Nếu B đã có local cache entry thì `FROM-CACHE` **không chứng minh remote GET đã xảy ra**. Muốn thử remote hit phải dùng một local cache directory **mới/được cô lập**, kiểm tra server logs hoặc Build Scan. Đừng xóa global Gradle User Home của developer để tạo tình huống này.

### 14.2. Tách cache identities theo trust level

Một remote cache backend có thể có:
- Namespace trusted `main` hoặc `release`: CI được PUT, consumers trusted/untrusted được GET theo chính sách.
- Namespace thử nghiệm PR: write policy riêng, không dùng làm nguồn của release.
- Project/repository-specific namespaces nếu hệ thống có nhiều tổ chức/nhóm với ACL khác nhau.

Gradle DSL chỉ biết URL/cache server/credentials; **namespace isolation thực tế do backend/path/account/ACL quản trị**. Đừng coi việc đặt tên cache URL là một bảo đảm bảo mật nếu cả hai URLs lại trỏ cùng quyền write bên dưới.

## 15. Custom task cần đúng annotations để thực sự cacheable

Trong bài lab:
- `@CacheableTask`: cho phép task output caching.
- `@Input`: scalar/provider input tham gia key.
- `@OutputFile`: file mà task tạo và Gradle cần lưu/khôi phục.
- `RegularFileProperty` và `Property<String>`: lazy configuration, input tracking, hỗ trợ Configuration Cache tốt hơn truy cập trực tiếp Project trong action.

Nếu custom task có file input, dùng property đúng loại và **path sensitivity**:

```java
import org.gradle.api.file.ConfigurableFileCollection;
import org.gradle.api.tasks.InputFiles;
import org.gradle.api.tasks.PathSensitive;
import org.gradle.api.tasks.PathSensitivity;

@InputFiles
@PathSensitive(PathSensitivity.RELATIVE)
public abstract ConfigurableFileCollection getSources();
```

Đây chỉ là **snippet minh họa thêm getter vào một task type có xử lý file inputs**, không phải code độc lập chạy với `javac` mà không có Gradle API. `PathSensitivity.RELATIVE` dùng khi task output không phụ thuộc absolute checkout path mà chỉ phụ thuộc relative file paths/content. Nếu output thật sự phụ thuộc tuyệt đối vào file path, khai báo RELATIVE sẽ gây **cache hit sai**; chọn normalization theo semantics thật.

### 15.1. Những task không nên được cache

- Task gửi email hoặc gọi service có side effects quan trọng.
- Task upload artifact/deploy release mà mỗi lần chạy cần thực sự ghi remote state.
- Task generate dữ liệu phụ thuộc thời gian/random nhưng không kiểm soát seed/clock.
- Task lấy secrets/network state không được khai báo/không nên cache.
- Task tạo output chứa absolute machine paths rồi dùng output ở máy khác.

`@CacheableTask` không làm task deterministic. Nếu một output phụ thuộc hidden inputs, cache entry có thể bị tái sử dụng sai, nghiêm trọng hơn cache miss.

### 15.2. Output overlap và đường dẫn

Không để hai independent cacheable tasks cùng ghi vào một output file hoặc cùng untracked directory. Output ownership mơ hồ làm Gradle khó kiểm soát up-to-date checks, caching và restoration. Mỗi task nên khai báo output file/directory riêng, ví dụ `build/generated/<taskName>/`.

### 15.3. Thêm doLast/doFirst vào task có thể ảnh hưởng cache key

Gradle tính task action implementations vào cache key. Nếu thêm `doLast { println(...) }` vào `JavaCompile` hoặc task cacheable khác, task implementation fingerprint có thể thay đổi, làm tăng misses. Với build logic lớn, nên dùng task types hoặc convention plugins có hành vi ổn định thay vì mỗi module chèn closures vào cacheable tasks.

## 16. Dependency versions, Gradle version, JDK và environment

Một remote hit chỉ xảy ra khi các fingerprints quan trọng tương đương. Những nguyên nhân thường làm key khác:

- JDK/compiler/toolchain vendor/version hoặc plugin version đổi.
- `buildSrc` hoặc included build logic thay implementation classpath.
- Gradle Wrapper version thay, làm task API/implementation khác.
- Java source changes hoặc generated sources thay.
- Annotation processor dependencies/options đổi.
- Một input environment/file property bị cấu hình khác.
- Absolute paths được đưa vào task inputs thay vì normalized paths.
- Build script thêm task actions khác.
- Một dependency dynamic version như `1.+` resolve khác.

**Version catalog không tự bảo đảm resolved dependencies giống nhau**; dependency locking/verification và repository controls là những lớp hữu ích khác khi cần reproducible builds.

### 16.1. Java toolchain của demo

Root `build.gradle.kts` đặt Java 17 toolchain; buildSrc cũng đặt 17. Nếu buildSrc compiled classes target Java 17 nhưng Gradle Daemon chạy trên JVM cũ hơn, plugin/task class không load được. Gradle 9.x yêu cầu Java runtime tối thiểu theo compatibility matrix; luôn kiểm tra `./gradlew --version` và `javaToolchains`.

Đổi compiler JDK có thể làm JavaCompile task cache key đổi, vì compiler toolchain tham gia inputs/task behavior. Không nên “ép cache hit” bằng cách bỏ qua compiler version khi output thực tế có thể khác.

### 16.2. Cross-platform cache relocatability

Cache entry từ Linux có thể không tái dùng được trên Windows nếu:
- Input file paths được normalized sai (dấu slash, case-sensitivity).
- Task output chứa absolute Unix paths.
- Compiler/toolchain, OS-specific resources hoặc line endings khác.
- Task chạy native binaries hay dùng platform-dependent flags.

**Không đòi mọi task phải cross-OS cacheable.** Trước tiên bảo đảm correctness; chỉ chia sẻ cache giữa OS/architectures nếu task có inputs/outputs rõ và test relocatability thực tế.

## 17. Build Cache, buildSrc và composite builds

Gradle docs có quy tắc đặc biệt: **included builds** trong composite build thường nhận cấu hình build cache từ top-level build, và `buildSrc` được xử lý tương tự một included build. Nhưng **plugin builds** include qua `pluginManagement` có lifecycle sớm hơn, nên precedence của build cache configuration có ngoại lệ.

Do đó:
- Không tự giả định `buildSrc/settings.gradle.kts` có thể override hiệu quả cache policy top-level ở mọi composite invocation.
- Nếu build logic nằm trong `build-logic` được include ở `pluginManagement`, kiểm tra behavior của Gradle version chính xác.
- Đừng sửa `buildSrc`/`build-logic` chỉ để đạt remote cache hit khi nguyên nhân là khác implementation fingerprint.
- Khi đo cache hit giữa projects, log build logic version, included build code và Gradle Wrapper.

Tài liệu chính thức [Gradle Build Cache](https://docs.gradle.org/current/userguide/build_cache.html) có phần **Build cache, composite builds and buildSrc** để tra đúng precedence.

## 18. Phân biệt build cache miss và configuration cache miss

Ví dụ:

```bash
./gradlew --configuration-cache --build-cache clean writeGreeting
./gradlew --configuration-cache --build-cache clean writeGreeting
```

Có thể đồng thời thấy:
- **Configuration Cache reused**: Gradle không cấu hình lại toàn bộ task graph.
- **`:writeGreeting FROM-CACHE`**: task output được phục hồi từ Build Cache sau `clean`.

Nhưng một cache hit không bắt buộc kéo theo cache hit còn lại:
- Build script đổi, configuration cache invalidated, nhưng task outputs vẫn có thể hit Build Cache nếu implementation/inputs không đổi.
- Configuration cache reused, nhưng Java source thay, `compileJava` cần chạy lại và có thể không tìm thấy Build Cache entry.

**Hai caching layers độc lập về mục đích**; không gọi chung là “Gradle cache” khi debug vì sẽ không biết lớp nào gây chậm.

## 19. HTTP error handling và chiến lược fail-open/fail-closed

Remote cache là tối ưu hóa hiệu năng, không nên là dependency bắt buộc cho correctness của một build thường ngày nếu source/dependency inputs vẫn có thể giải quyết. Gradle có logic retry các network failures và có thể disable remote backend trong phần còn lại của invocation khi backend lỗi.

Các HTTP tình huống:

| HTTP/hiện tượng | Ý nghĩa thường gặp | Cách xử lý |
| --- | --- | --- |
| GET `200` | Entry tồn tại. | Xác nhận restored outputs/task outcome và trust backend. |
| GET `404` | Cache miss bình thường. | Task tự execute; nếu miss bất ngờ, so cache keys. |
| PUT `2xx` | Store được backend chấp nhận. | Xem logs/metrics/retention để chắc entry còn dùng được. |
| PUT `413` | Entry quá lớn. | Backend limits/entry size, không coi là một cache hit về sau. |
| `401` | Credentials không hợp lệ/chưa cung cấp. | Kiểm tra secret injection và authentication scheme. |
| `403` | Role không được PUT/GET. | Điều chỉnh ACL đúng trust policy; không cấp write tùy tiện. |
| `5xx`/timeout | Server/proxy/network lỗi. | Kiểm tra backend health, retry policy, fallback local. |
| TLS trust error | Certificate/hostname/CA chain không đáng tin. | Sửa certificate/trust store, không disable TLS validation. |
| GET trả bytes sai/corrupt | Cache storage/proxy bị hỏng hoặc bị tấn công. | Không chấp nhận như output hợp lệ, điều tra cache namespace/ACL. |

Tùy loại lỗi và Gradle version, build có thể tiếp tục bằng task execution hay báo lỗi. **Không hứa mọi HTTP failure luôn fail-open.** Với release/security-sensitive pipelines, có thể đặt yêu cầu riêng cho verified cache backend, thậm chí không dùng remote cache trong những bước cần thực thi bắt buộc như signing/publishing.

## 20. Debug cache miss bằng --info và caching.debug

### 20.1. Bước 1 — kiểm tra task có UP-TO-DATE trước

Theo Gradle debugging guide:
1. Chạy `clean` rồi task để tạo outputs.
2. Chạy lại không `clean`, không đổi source.
3. Kiểm tra task output có `UP-TO-DATE` không.

Nếu không UP-TO-DATE, rất có thể inputs/outputs thiếu hoặc có hidden variable. Cache remote sẽ không giải quyết nguyên nhân này.

```bash
./gradlew clean writeGreeting --info
./gradlew writeGreeting --info
```

### 20.2. Bước 2 — kiểm tra local cache độc lập

```bash
./gradlew --build-cache clean writeGreeting --info
./gradlew --build-cache clean writeGreeting --info
```

Trong môi trường ổn định, lần đầu tạo cache entry, lần sau có thể `FROM-CACHE`. Nếu không, kiểm tra `@CacheableTask`, build cache enabled state, task outputs và log reasons như “Caching disabled for task ...”.

### 20.3. Bước 3 — xem cache key/fingerprints

Gradle có cờ debug chi tiết:

```bash
./gradlew --build-cache writeGreeting \
  -Dorg.gradle.caching.debug=true --info
```

Output có thể chứa “Build cache key for task ...”, input file fingerprints và names/values của input properties tùy task/Gradle version. Dùng log này để so giữa hai builds, tìm input hash thay đổi đầu tiên. **Không in hoặc gửi debug log có paths/secrets nhạy cảm lên chỗ công khai**; chỉ dùng trong môi trường đã kiểm soát.

### 20.4. Bước 4 — so sánh local và remote

Nếu local cache hit nhưng remote không:
- Remote backend URL có đúng format `https://host/cache/` không?
- Remote có enabled? Build Cache đã bật?
- Trusted producer job có `push=true` và write credentials không?
- PUT có `2xx` hay bị `401/403/413`?
- Entry đã bị eviction trên remote chưa?
- Local cache hit khiến Gradle **không cần gọi remote**, nên server không thấy GET?
- Task implementation/Gradle/JDK/input fingerprint của B có khác A?

Để chứng minh remote hit, dùng local cache mới/empty và logs/metrics server. Không xóa toàn bộ `~/.gradle` của người dùng như một thủ thuật debug.

### 20.5. Develocity/Build Scan metrics

Build Scan/Develocity có thể cung cấp:
- Task execution timeline.
- Cache hits/misses, origins, task avoidance.
- Input fingerprints/task classloader hashes, so sánh builds.
- Build time/caching statistics và cache server performance.

Đây là công cụ bổ sung; **Build Cache không bắt buộc phải mua Develocity**. Có thể dùng local/remote Gradle cache backend chuẩn và `--info`/diagnostic flags để học hoặc vận hành quy mô nhỏ.

## 21. Cache eviction, lưu trữ và chi phí vận hành

Một cache không có retention/quota sẽ tăng theo thời gian. Thiết kế phù hợp:
- Local cache: giới hạn khoảng thời gian giữ entries và dung lượng/đường dẫn theo Gradle User Home cleanup policy.
- Remote cache: size limits, object retention/eviction, backup strategy, storage latency và billing.
- CI ephemeral runners: local cache có thể mất sau mỗi job; remote cache đem lại nhiều giá trị.
- Developer machines: local cache có thể đủ nhanh, remote tăng network overhead nếu hit rate thấp.
- Artifact size: không phải task output nào cũng đáng cache; lưu một output khổng lồ đôi khi tốn thời gian upload/download hơn recompute.

**Không nhầm local Build Cache với các thư mục khác trong `~/.gradle`.** Xóa cả Gradle User Home có thể xóa dependency artifacts, downloaded Gradle distributions, caches và daemon state ngoài ý định; chỉ quản trị đúng cache backend dưới sự kiểm soát.

### 21.1. Chi phí mạng và khả năng hồi phục

Remote cache hiệu quả nếu:

```text
expected saved time from avoided task execution
  > expected cache lookup + download + decompression time
    + infrastructure/maintenance cost
```

Một remote entry 500 MB tải chậm hơn biên dịch tác vụ 2 giây sẽ không có lợi. Ngược lại, một bộ compiled outputs/test outputs tốn vài phút nhưng nhỏ và dùng chung nhiều lần có thể tiết kiệm lớn.

Đánh giá bằng dữ liệu: cache hit rate **không phải KPI duy nhất**; cần đo tổng wall-clock build time, CPU time avoided, network bytes, cache server latency và reliability.

## 22. Câu hỏi thường gặp

### 22.1. Có cần tự cấu hình local {} để bắt đầu dùng cache không?

Không. Gradle có local `DirectoryBuildCache` được chuẩn bị sẵn, nhưng **Build Cache phải được bật** bằng `--build-cache` hoặc `org.gradle.caching=true`. Viết `local { directory = ... }` chỉ để đổi location/chính sách và dễ quan sát trong lab.

### 22.2. Tại sao chạy lại task báo UP-TO-DATE, không FROM-CACHE?

Vì outputs của task vẫn còn và Gradle xác minh inputs/outputs không đổi. Nếu muốn chứng minh cached output restoration, dùng `clean` trong môi trường local cache vẫn còn, không dùng `--rerun-tasks`.

### 22.3. Tại sao sau clean vẫn SUCCESS?

Có thể chưa có cache entry, task không cacheable, key thay đổi, backend disabled, local cache đã bị eviction hoặc remote không có entry. Xem `--info` và `-Dorg.gradle.caching.debug=true`; đừng chẩn đoán chỉ từ stdout “BUILD SUCCESSFUL”.

### 22.4. Remote cache tự động đẩy outputs từ developer không?

Không theo mặc định: **remote push bị tắt**, local push bật. Remote `isPush/push` phải được cấu hình đúng và server phải cấp quyền write. Nên chỉ trusted CI được PUT.

### 22.5. Thêm remote URL có làm mọi build nhanh hơn không?

Không chắc. Cần cacheable tasks, tương thích inputs/implementation, đủ cache hits và network latency phù hợp. Cache server lỗi có thể thêm overhead. Dùng metric trước/sau khi triển khai.

### 22.6. Có thể dùng S3/GCS trực tiếp thay HttpBuildCache không?

Core Gradle hỗ trợ local directory và remote `HttpBuildCache`. Với backend khác, cần plugin/custom Build Cache implementation hoặc một HTTP cache service đặt trước object storage; không tự biến `s3://...` thành URL hợp lệ cho `HttpBuildCache`.

### 22.7. Có cần bảo vệ remote cache dù chỉ là artifacts trung gian không?

Có. Cache output có thể được Gradle dùng thay task execution, nên độc hại/corrupted entries ảnh hưởng downstream build. Bảo vệ URL, credentials, writable identities, namespaces và TLS như một thành phần supply chain.

### 22.8. Task không có declared output có cache được không?

Task output caching dựa vào outputs có thể lưu/khôi phục. Task không khai báo outputs thường không có gì để cache. Một task có side effects nhưng không có output file không nên được “cứu” bằng `@CacheableTask`.

### 22.9. Build Cache có ảnh hưởng kết quả của Java unit tests không?

Task `Test` có thể là cacheable theo Gradle task metadata, nhưng một test suite phụ thuộc network/time/random/external DB mà chưa khai báo inputs có thể khiến cache reuse không an toàn. Với integration tests có side effects, hãy định nghĩa cách vô hiệu caching hoặc task inputs phù hợp, không đánh dấu tùy tiện mọi test task là cacheable.

### 22.10. Can thiệp cache directory có an toàn không?

Không nên sửa trực tiếp files trong Gradle cache. Chúng được quản lý theo key/metadata và cleanup; sửa một entry có thể làm cache corruption, giảm integrity. Dùng Gradle APIs/cấu hình và backend admin tools. Nếu cần reset, làm trên cache directory riêng của lab sau khi chắc không có Gradle process đang dùng.

## 23. Các lỗi điển hình và hướng xử lý

| Triệu chứng | Khả năng cao | Khắc phục |
| --- | --- | --- |
| `--build-cache` mà task vẫn `SUCCESS` | Chưa có entry/key khác/task không cacheable. | Xem `--info`, task annotations và cache key. |
| Lần 2 `UP-TO-DATE` chứ không `FROM-CACHE` | Output còn nguyên. | Dùng `clean` với cache directory ngoài `build/`. |
| `clean` xóa luôn cache thử nghiệm | Đặt local cache bên trong `build/`. | Dời directory ra ngoài `build/` hoặc về Gradle User Home. |
| Local hit, remote không GET | Local được ưu tiên. | Dùng local cache trống và server metrics. |
| Remote chỉ GET được, PUT 403 | User role read-only hoặc `push` chưa cho phép. | Trusted CI có server ACL write, không cấp cho PR. |
| PUT trả 413 | Server giới hạn payload. | Điều chỉnh policy/object size, cân nhắc task caching value. |
| HTTPS certificate error | CA/trust store/hostname sai. | Sửa certificate/trust store, không bật allowUntrustedServer. |
| Remote backend có URL nhưng Gradle không gọi | Build Cache chưa bật, local hit hoặc remote config bị bỏ qua. | Kiểm tra Settings và `--build-cache`/logs. |
| Cùng Git SHA mà remote miss | Gradle/JDK/plugin/input fingerprint khác. | So build cache keys và toolchain/dependency graph. |
| Windows/Linux không share được cache | Absolute path hoặc OS-specific outputs. | @PathSensitive RELATIVE khi thực sự đúng, test relocatability. |
| Output sai dù FROM-CACHE | Hidden input/poisoned entry/task không deterministic. | Dừng dùng entry, sửa task inputs và kiểm tra remote trust. |
| CI build kéo output từ untrusted branch | Chung write namespace và ACL sai. | Tách trust levels, chỉ trusted jobs được PUT. |
| Cache server timeout khiến build chậm | Network/proxy/backend health. | Metrics/retry/fallback; giảm overhead hoặc tạm disable remote. |
| Cache quá lớn | Retention/quota không phù hợp. | Gradle cleanup policy cho local, server eviction cho remote. |
| `NoSuchMethodError` khi đổi Gradle | Plugin/buildSrc implementation khác, không phải cache corruption mặc định. | Kiểm tra Gradle/Plugin version, stacktrace trước khi xóa cache. |
| `Configuration cache reused` nhưng task `SUCCESS` | Hai caches khác mục đích. | Kiểm tra Build Cache key độc lập. |
| Cacheable task tạo file ngoài @OutputFile | Output side effect chưa khai báo. | Khai báo đúng outputs hoặc không cache task. |
| `run` không FROM-CACHE | JavaExec thường không được cache mặc định. | Quan sát JavaCompile/custom cacheable task. |
| Build cache hit quá ít | Task work rẻ, input/implementation liên tục đổi. | Đo miss reasons, tránh random/timestamp/unstable code. |

## 24. Checklist cấu hình production

### Thiết kế tasks

- [ ] Task nào cacheable? Có `@CacheableTask` hoặc policy cache phù hợp?
- [ ] Inputs/outputs được khai báo đầy đủ, không có hidden state?
- [ ] Task outputs deterministic, không có external side effects quan trọng?
- [ ] File path sensitivity đúng semantics, hỗ trợ relocatability khi cần?
- [ ] Test `UP-TO-DATE`, `FROM-CACHE` và input-change misses?
- [ ] Java/JDK/Gradle/plugin/dependency versions được chốt?

### Local cache

- [ ] Bật `org.gradle.caching=true` hoặc `--build-cache` theo policy?
- [ ] Local cache directory tồn tại/được Gradle quản lý, nằm ngoài `build/` nếu dùng custom location?
- [ ] Không commit cache entries vào Git?
- [ ] Có cleanup/retention phù hợp và không xóa nhầm cả Gradle User Home?
- [ ] Có chứng minh `FROM-CACHE` sau `clean` trong lab?

### Remote cache

- [ ] Có remote Build Cache backend tương thích GET/PUT theo key?
- [ ] URL dùng HTTPS, certificate được trust, không bật insecure/untrusted flags?
- [ ] Authentication/read/write ACL phân quyền tại server?
- [ ] Chỉ trusted CI được push; developer/PR pull-only?
- [ ] Tách namespace theo trust boundary/project khi cần?
- [ ] Server metrics/audit/retention/quota, proxy/redirect/body-size/timeouts được kiểm tra?
- [ ] Khi remote unavailable, workflow xử lý có chủ đích và không sai artifact?

### Quan sát và bảo trì

- [ ] Có baseline không cache, local hit và remote hit thực sự?
- [ ] Có log Gradle/JDK/cache key/task outcome để debug?
- [ ] Không đưa secrets lên debug logs hoặc cached task outputs?
- [ ] Cache hit rate được đo cùng wall-clock/network cost, không tối ưu mù?
- [ ] Configuration Cache, dependency cache và Build Cache được theo dõi phân biệt?

## 25. Bảng ghi nhớ ngắn

| Vấn đề | Cách giải quyết |
| --- | --- |
| Bật Build Cache một lần | `./gradlew --build-cache ...` |
| Bật trong project | `org.gradle.caching=true` |
| Tắt tạm thời | `--no-build-cache` |
| Cấu hình backend | `buildCache { ... }` trong `settings.gradle(.kts)` |
| Local cache mặc định | DirectoryBuildCache trong Gradle User Home |
| Local cache custom directory | `local { directory = File(rootDir, ".local-build-cache") }` |
| Remote cache backend | `remote<HttpBuildCache>` (Kotlin) / `remote(HttpBuildCache)` (Groovy) |
| URL remote | HTTPS endpoint tương thích GET/PUT cache-key |
| Remote push Kotlin | `isPush = allowRemotePush` |
| Remote push Groovy | `push = allowRemotePush` |
| Remote credentials | `credentials { username = ...; password = ... }`, lấy từ secrets |
| Local hit vs remote hit | Local được lookup trước, remote chỉ khi local miss |
| Cacheable custom task | `@CacheableTask`, `@Input`, `@OutputFile` |
| UP-TO-DATE | Output vẫn còn, inputs/outputs không đổi |
| FROM-CACHE | Cache entry hit, output được restore, action không chạy |
| Cache key debug | `-Dorg.gradle.caching.debug=true` và `--info` |
| Cross-machine reuse | Input fingerprints/classpath tương đương, task relocatable |
| Security policy | Trusted CI push, PR/developer pull-only, server ACL/TLS |
| Không nhầm | Build Cache != Configuration Cache != Dependency Cache |

**Kết luận:** Local Build Cache là cách đơn giản nhất để tránh lặp lại task execution khi output đã bị xóa nhưng inputs vẫn giống nhau; remote Build Cache mở rộng lợi ích đó ra nhiều machines, teams và CI runners. Bật cache **không biến mọi task thành cacheable**: correctness đến từ việc khai báo đủ task inputs/outputs và deterministic behavior. Cấu hình local/remote thuộc **Settings**; remote cần một HTTP cache backend, credentials và write permissions được kiểm soát. Hãy bắt đầu bằng ví dụ local `SUCCESS -> UP-TO-DATE -> FROM-CACHE`, sau đó cho **trusted CI** push và các jobs khác pull-only, quan sát cache key/misses bằng diagnostics và bảo vệ cache như một phần supply-chain infrastructure.

### Tài liệu chính thức

- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): enable, local DirectoryBuildCache, remote HttpBuildCache, load/store ordering, credentials, composite builds.
- [Gradle — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): cache key và reproducible/relocatable task outputs.
- [Gradle — Debugging Build Cache Misses](https://docs.gradle.org/current/userguide/build_cache_debugging.html): incremental/up-to-date, caching debug fingerprints, task implementation.
- [Gradle — Task Output Caching](https://docs.gradle.org/current/userguide/build_cache.html#sec:task_output_caching): @CacheableTask và task inputs/outputs.
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): remote cache ACL, TLS, untrusted PR risks và cache poisoning.
- [Gradle — HttpBuildCache API](https://docs.gradle.org/current/javadoc/org/gradle/caching/http/HttpBuildCache.html): URI, credentials, push, TLS và expect-continue.
- [Gradle — Gradle-managed Directories and Caches](https://docs.gradle.org/current/userguide/directory_layout.html): Gradle User Home và cleanup/retention.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): phân biệt caching task outputs với configuration graph.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): UP-TO-DATE, task input/output tracking.
- [Gradle — Build Cache Performance](https://docs.gradle.org/current/userguide/build_cache_performance.html): đánh giá tác động và cache misses.
