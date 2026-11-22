# Nhận diện nút thắt build logic, script compilation và buildSrc trong Gradle

## 1. Bài toán: tại sao task rất nhanh nhưng build vẫn chậm?

Một lần chạy `./gradlew :app:classes` có thể chỉ biên dịch vài Java classes, thậm chí mọi task đều `UP-TO-DATE`, nhưng người dùng vẫn phải đợi nhiều giây trước khi thấy kết quả. Không phải lúc nào `javac` hoặc JUnit là thủ phạm: thời gian còn có thể nằm ở **khởi động Gradle**, xử lý `settings.gradle(.kts)`, dựng và tải **build logic**, **biên dịch Gradle scripts**, áp dụng plugins, cấu hình các projects và resolve dependencies quá sớm.

Bài này tập trung đúng ba nguồn chi phí thường bị gộp chung:

1. **Build logic** — Java/Kotlin/Groovy code trong scripts, custom tasks, convention/binary plugins, init scripts và included builds.
2. **Script compilation** — chuyển `*.gradle.kts` hoặc `*.gradle` sang dạng thực thi/cached script; Kotlin DSL đặc biệt đáng quan sát ở cold builds và khi script classpath thay đổi.
3. **`buildSrc`** — Gradle build đặc biệt được compile trước project build scripts và đưa output lên classpath của các scripts đó; thay đổi của nó có thể làm phạm vi cache invalidation rộng.

Mục tiêu không phải “tắt hết plugins” hay “đổi Groovy thành Kotlin” theo cảm tính, mà là tạo **bằng chứng đo được**, cô lập nguyên nhân, tối ưu một biến mỗi lần và giữ tính đúng của build.

### 1.1. Những câu hỏi cần trả lời

- Thời gian bị mất ở **startup**, **settings/buildSrc**, **loading/configuration** hay **task execution**?
- Kotlin/Groovy build script có đang **compile lại** hay chỉ chạy configuration logic?
- Một thay đổi nhỏ trong `buildSrc` có làm nhiều scripts mất reuse không?
- Plugin nào đang được apply ở các modules không cần đến nó?
- Có eager task realization, filesystem scans, network calls hoặc dependency resolution trong configuration không?
- Có phải Configuration Cache miss vì `buildSrc`/environment/configuration inputs thay đổi?
- Chuyển convention plugins sang included build `build-logic` có thu hẹp scope không?
- Sau tối ưu, **p50/p90 wall-clock** và task outcomes có tốt hơn qua nhiều lần chạy tương đương không?

### 1.2. Đừng dùng một lần chạy làm kết luận

Build đầu tiên ở một checkout mới thường bao gồm Gradle distribution download, dependency/plugin resolution, Kotlin DSL script compilation, buildSrc compilation và daemon warmup. Lần chạy sau có thể reuse nhiều caches. So sánh “lần đầu trước tối ưu” với “lần thứ năm sau tối ưu” là **sai phương pháp**.

## 2. Sơ đồ vòng đời và vị trí nút thắt

Một phiên chạy có thể được hiểu như sau:

```text
./gradlew :app:classes
      |
      v
Wrapper / Gradle distribution / JVM / Daemon startup
      |
      v
Initialization & Settings scripts
      |
      +--> pluginManagement / included plugin builds
      |
      +--> Gradle automatic buildSrc detection and preparation
      |       compile Kotlin/Groovy/Java build logic when needed
      |
      v
Project build-script classpath construction
      |
      +--> script compilation/cache lookup
      +--> plugins applied and project configuration
      +--> task registration / dependency graph configuration
      |
      v
Task graph calculation
      |
      v
Task execution or avoidance
      +--> UP-TO-DATE / FROM-CACHE / NO-SOURCE
      +--> compileJava / test / resources / packaging
      |
      v
Report, logs and optional cache entry
```

Đây là **mô hình khái niệm**, không phải cam kết thứ tự mọi internal operation ở mọi bản Gradle. Composite builds và các plugin dùng trong `pluginManagement` có lifecycle sớm hơn, còn Configuration Cache có thể làm nhiều bước configuration được bỏ qua khi entry hợp lệ.

### 2.1. Các nhóm thời gian trong profile

| Nhóm trong Gradle profile | Điều cần kiểm tra |
| --- | --- |
| **Startup** | Wrapper download, JVM/daemon startup, init scripts, filesystem/OS pressure. |
| **Settings and buildSrc** | Settings evaluation; cấu hình/compile buildSrc; plugin builds cần chuẩn bị. |
| **Loading projects** | Số projects, included builds, project discovery. |
| **Configuring projects** | Script compilation/evaluation, plugin apply, eager tasks, dependency resolution, đọc filesystem/network. |
| **Task execution** | Java/Kotlin compilation, test, copying, packaging, custom task actions, cache misses. |

**Quan trọng:** `buildSrc:compileKotlin` là một task của **build logic build**, không phải `:app:compileJava` của ứng dụng. Nếu profile cho thấy buildSrc tốn nhiều thời gian, không được vội tối ưu compiler options của production Java module.

## 3. Bốn nguồn bằng chứng trước khi tối ưu

### 3.1. Built-in HTML profile: --profile

Tại root có Gradle Wrapper:

```bash
./gradlew help --profile
./gradlew :app:classes --profile
```

Gradle tạo HTML profile trong:

```text
build/reports/profile/
  profile-<timestamp>.html
```

Tên có timestamp và cách đặt có thể khác chút theo Gradle version. Mở file HTML được Gradle thông báo ở cuối lệnh, xem thời gian startup, Settings/buildSrc, project loading, configuration và task execution.

**Hạn chế:** Profile report miễn phí và rất tiện nhưng không hiển thị mọi script compilation operation, classloader hay method-level CPU cost như một profiler chuyên sâu. Nó có thể chỉ ra **vùng chậm**, không nhất thiết chỉ ngay dòng Kotlin DSL chậm nhất.

### 3.2. Build Scan / Develocity

```bash
./gradlew help --scan
./gradlew :app:classes --scan
```

Khi có cơ chế Build Scan tương thích với Gradle distribution/plugin và đã đáp ứng điều kiện publish, Build Scan có thể hiển thị performance timeline, plugin/script applications, configuration breakdown, dependency resolution, task outcomes, Build Cache và máy/JVM environment.

**Bảo mật:** `--scan` có thể **công bố dữ liệu build tới dịch vụ ngoài/enterprise server**, bao gồm metadata project, môi trường và dependency details. Chỉ dùng sau khi hiểu privacy policy, consent/configuration và chính sách dữ liệu tổ chức; với dự án bảo mật, ưu tiên HTML `--profile` nội bộ hoặc Develocity instance được duyệt.

Nếu scan cho thấy nhiều modules chậm ở plugin apply hoặc dependency resolution trong configuration, đó là cơ sở để đi tới plugin/convention/Settings code cụ thể. Đừng lấy tổng task execution time thay cho total wall-clock time.

### 3.3. Console diagnostics: --info, --debug và --stacktrace

```bash
./gradlew help --info
./gradlew :app:classes --info
./gradlew -p buildSrc tasks --all
```

`--info` có thể cho thấy Kotlin script compilation/cache reuse, plugin resolution, buildSrc tasks chạy hay bị skip và lý do task không UP-TO-DATE. Các chuỗi log **thay đổi theo Gradle version**; không viết parser dựa vào đúng một message string.

`--debug` tạo log rất lớn, có thể chứa paths, URLs và data nhạy cảm; chỉ bật cục bộ khi `--info` chưa đủ, không làm mặc định CI. `--stacktrace` có ích cho **failure**, không phải profiler CPU.

### 3.4. Gradle Profiler và JVM profiler

Gradle Profiler hỗ trợ benchmarks lặp nhiều iterations, warmups và scenarios như thay source file hoặc đổi ABI trước build. Với vấn đề plugin/apply hoặc Kotlin script compilation khó tìm từ profile report, có thể kết hợp **Java Flight Recorder, async-profiler, JProfiler hoặc YourKit** nếu team được phép.

JVM profiling giúp phân biệt CPU-bound (type-safe accessor generation, reflection, plugin algorithm) với blocking I/O (filesystem, HTTP repo). **Đừng suy ra “Kotlin compiler chậm” chỉ vì JVM CPU cao**; cần call stacks, profile phases và một thí nghiệm kiểm soát.

## 4. Phương pháp đo: giữ điều kiện tương đương

Một tập phép đo đáng tin phải ghi:

| Biến | Cần cố định hoặc ghi lại |
| --- | --- |
| Git source | Full commit SHA và trạng thái working tree. |
| Gradle | Wrapper distribution version, không đổi giữa hai mẫu. |
| Java | Daemon JVM, Java toolchains, vendor/version. |
| Tasks | Chính xác CLI tasks và flags, ví dụ `help` vs `:app:classes`. |
| Daemon | Cold/warm status, heap, parallel workers. |
| Dependencies | Repositories/versions; lần đầu có network fetch hay chưa. |
| Caches | Kotlin/Groovy script, Configuration Cache, task Build Cache, dependency cache. |
| OS/hardware | CPU, disk, RAM, antivirus, container resources. |
| Project state | Number of projects, generated sources, same inputs. |
| Metrics | Wall-clock time, configuration fraction, cache hit/miss, p50/p90. |

### 4.1. Đo hai workflow, không dùng duy nhất clean build

**Configuration-focused** (task nhỏ):

```bash
./gradlew help --no-configuration-cache --profile
./gradlew help --no-configuration-cache --profile
```

**Developer iteration**:

```bash
./gradlew :app:classes --no-configuration-cache --profile
./gradlew :app:classes --no-configuration-cache --profile
```

Hai lệnh giống nhau chạy liên tiếp cho bạn quan sát warm-up và các cache được reuse. Các HTML profile files sẽ có timestamps khác. Nếu bật Build Cache, task outcomes có thể khác; ghi lại thay vì ngầm loại bỏ.

**Configuration Cache**:

```bash
./gradlew help --configuration-cache --profile
./gradlew help --configuration-cache --profile
```

Nếu build logic đáp ứng requirements, lần đầu thường tạo entry và lần sau có thể reuse. Đọc thông báo/scan để phân biệt `Configuration cache entry stored` và `reused`; không lấy việc `:help` chạy nhanh làm bằng chứng duy nhất.

### 4.2. Cold vs warm: định nghĩa rõ

- **Cold daemon:** JVM Gradle mới; vẫn có thể reuse dependency/script/build caches trên disk.
- **Cold script cache:** Gradle chưa có compiled script/accessor phù hợp với classpath/inputs.
- **Cold dependency cache:** libraries/plugins chưa được download/resolve.
- **Cold buildSrc outputs:** build logic classes chưa được build/cache.
- **Warm steady state:** cùng source, Gradle daemon/caches đã sẵn; không có network fetch không mong muốn.
- **Change scenario:** sửa đúng một script/convention/class có kiểm soát rồi chạy lại.

`./gradlew --stop` có thể dừng Gradle daemons tương ứng và làm một số bước startup lần sau chậm, nhưng **không xóa compiled Kotlin scripts hoặc dependencies**. Đừng gọi việc chạy sau `--stop` là “cold hoàn toàn”.

**Không xóa `~/.gradle` để tạo cold benchmark**: ngoài script caches còn có distributions, dependency metadata, local build cache và các dữ liệu dùng chung cho những projects khác.

### 4.3. Đo đa lần và tránh số liệu giả

Một ví dụ **số liệu giả lập để học cách phân tích**, không phải số đo từ repository của bạn:

| Scenario | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline warm (`ms`) | 1210 | 1180 | 1260 | 1220 | 1190 |
| After refactor (`ms`) | 740 | 730 | 765 | 750 | 745 |

Median baseline là `1210 ms`; median sau refactor là `745 ms`. Phần trăm giảm theo median là khoảng `38.4%`. Đây chỉ là **toán học từ dữ liệu minh họa**; không công bố là một benchmark Gradle thực tế.

Khi đo thật, dùng nhiều lần warmups, median và độ phân tán, cùng CPU/disk utilization. Nếu cải thiện nhỏ hơn nhiễu giữa runs, chưa có cơ sở kết luận.

## 5. Java 17 program để tính median từ dữ liệu thời gian giả lập

Đây là chương trình Java độc lập, dùng khi bạn đã thu wall-clock measurements từ profile/CI. Có thể chạy mà không cần Gradle; code và output được xác định chính xác.

Tạo **`PerfSummary.java`**:

```java
import java.util.Arrays;
import java.util.Locale;

public final class PerfSummary {
    private PerfSummary() {
    }

    static long median(long[] samples) {
        if (samples.length == 0) {
            throw new IllegalArgumentException("No samples");
        }
        long[] sorted = samples.clone();
        Arrays.sort(sorted);
        int middle = sorted.length / 2;
        if ((sorted.length & 1) == 1) {
            return sorted[middle];
        }
        return (sorted[middle - 1] + sorted[middle]) / 2;
    }

    public static void main(String[] args) {
        // Synthetic measurements, NOT production benchmarks.
        long[] before = {1210, 1180, 1260, 1220, 1190};
        long[] after = {740, 730, 765, 750, 745};

        long b = median(before);
        long a = median(after);
        double saved = 100.0 * (b - a) / b;

        System.out.println("baseline.median=" + b + " ms");
        System.out.println("optimized.median=" + a + " ms");
        System.out.printf(
            Locale.ROOT,
            "median.saving=%.1f%%%n",
            saved
        );
    }
}
```

Chạy bằng Java 17+:

```bash
javac --release 17 PerfSummary.java
java PerfSummary
```

Stdout chính xác:

```text
baseline.median=1210 ms
optimized.median=745 ms
median.saving=38.4%
```

Nếu số samples là số chẵn, hàm `median` đang làm phép chia nguyên trung bình nên làm tròn xuống với giá trị .5; để phục vụ báo cáo phân tích chính xác hơn nên dùng `double` hoặc thống kê chuyên dụng. Lab dùng **5 samples** nên không có vấn đề này.

Không tự động lấy thời gian từ `System.currentTimeMillis()` ở task action của build script: việc thêm instrumentation vào build logic có thể làm thay đổi những gì bạn đang đo. Hãy dùng profiler/CI logs bên ngoài hoặc measurement wrapper riêng khi cần.

## 6. Script compilation trong Gradle là chi phí nào?

### 6.1. Groovy DSL và Kotlin DSL đều là code

- **Groovy DSL**: `settings.gradle`, `build.gradle`, `*.gradle`. Gradle compile/cache Groovy scripts.
- **Kotlin DSL**: `settings.gradle.kts`, `build.gradle.kts`, `*.gradle.kts`. Gradle compile Kotlin scripts và có **type-safe accessors** cho model/plugin APIs.
- Cả hai chạy code trong configuration lifecycle; bản thân một `build.gradle.kts` ngắn cũng có thể gọi plugin nặng.
- Cả hai hưởng lợi từ script compilation caching; đổi script classpath/định nghĩa model có thể làm cache mất hiệu lực.

Theo Kotlin DSL Primer chính thức, Kotlin DSL có thể chậm hơn Groovy DSL **lần đầu** (clean checkout, ephemeral CI) vì Kotlin script compilation. Một thay đổi trong `buildSrc` cũng có thể invalidate build-script caching. Tuy nhiên **warm build** có caching khác và không thể suy ra “Kotlin luôn chậm hơn Groovy” từ một lần chạy.

### 6.2. Type-safe accessors và plugin block

Kotlin DSL thường sử dụng:

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

`java { ... }` là typed accessor đóng góp bởi plugin và model. Những accessors có thể được biên dịch/tạo lại khi script classpath hoặc các model elements cần thiết thay đổi. Nếu thay plugin declarations/dependencies thường xuyên, thời gian lần đầu sẽ nổi bật hơn so với script đã cache.

Với Groovy:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Đây là **hai ngôn ngữ build scripts khác nhau**, nhưng cả hai cấu hình Java plugin/toolchain giống nhau. Đừng trộn cú pháp `id 'java-library'` vào file `.gradle.kts` và xem compile error là performance problem.

### 6.3. Script compilation vs script evaluation

Hai bước thường bị nhầm:

| Bước | Ý nghĩa | Ví dụ biểu hiện |
| --- | --- | --- |
| **Script compilation** | Biên dịch `build.gradle.kts`/`build.gradle` thành code có thể chạy và cache. | Chi phí nổi bật ở cold builds hoặc classpath change. |
| **Script evaluation** | Chạy code script để apply plugins, register/configure tasks, resolve early dependencies. | Chậm **mỗi khi configuration chạy**, dù script compilation đã cache. |
| **Precompiled script plugin compilation** | Build `*.gradle.kts` dưới `buildSrc/src/main/kotlin` hoặc included build. | Task `compileKotlin`/plugin preprocessing trong build logic. |
| **Main source compilation** | `:app:compileJava` hoặc `:lib:compileKotlin` biên dịch application/library. | Task execution, không phải script compilation. |

Nếu `--profile` báo configuration chậm **kể cả warm** mà `--info` cho thấy scripts reused, có thể bottleneck là **plugin apply hoặc eager work** chứ không phải compiler Kotlin DSL.

### 6.4. Cache directories chỉ để nhận biết, không chỉnh tay

Gradle lưu version-specific script caches trong Gradle User Home. Với các phiên bản hiện hành, có các thư mục nội bộ như:

```text
~/.gradle/caches/<gradle-version>/kotlin-dsl/
~/.gradle/caches/<gradle-version>/scripts/
```

Thư mục `kotlin-dsl` liên quan compiled Kotlin scripts/accessors và `scripts` liên quan compiled Groovy scripts. **Không xóa/sửa những files này để “tối ưu”**: Gradle tự quản lý cache và version-specific layouts có thể thay đổi.

## 7. buildSrc: tại sao một thay đổi nhỏ có thể tạo hiệu ứng lớn?

`buildSrc` là một build đặc biệt tại **root của main build**, được Gradle tự nhận diện:

```text
my-repo/
├── settings.gradle.kts
├── build.gradle.kts
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/kotlin/java-conventions.gradle.kts
├── lib/build.gradle.kts
└── app/build.gradle.kts
```

Khi buildSrc có Kotlin/Java/Groovy code, Gradle chuẩn bị/biên dịch outputs của build đặc biệt này và đưa code lên **classpath các project build scripts**. Vì classpath này được sử dụng rộng, việc đổi implementation/dependencies trong buildSrc có thể khiến **script compilation/configuration caches** của nhiều projects cần invalidation, kể cả projects không dùng trực tiếp helper vừa đổi.

Không được hiểu buildSrc là `include(":buildSrc")` thông thường, cũng không tự cho rằng buildSrc JAR nằm trong runtime JAR của ứng dụng.

### 7.1. Ba loại chi phí riêng biệt từ buildSrc

1. **BuildSrc build cost:** Gradle cấu hình buildSrc, chạy `compileJava`/`compileKotlin`/tác vụ precompiled plugin, xử lý dependencies.
2. **Classpath impact:** compiled output/dependencies của buildSrc trở thành một phần của main scripts' classpath, có thể invalidated compiled scripts/cache khi đổi.
3. **Configuration impact:** conventions/plugins chạy khi được apply vào modules; nếu làm eager work thì warm configuration vẫn chậm.

Tối ưu chỉ mục 1 bằng cách giảm JavaCompile time **không tự giải quyết** mục 2 và 3. Nếu `buildSrc` compile UP-TO-DATE nhưng plugins vẫn enumerate file trees và resolve configurations mỗi lần, cần tối ưu **thời điểm thực hiện work**.

### 7.2. Đừng quy mọi chậm trễ ở buildSrc cho Kotlin

BuildSrc có thể chậm do:
- Plugin dependencies được resolve qua repository chậm.
- BuildSrc source files/classpath đổi quá thường xuyên.
- Precompiled script plugins nhiều, generated accessors và Kotlin compilation.
- Custom task/plugin chạy filesystem/network work trong configuration.
- Dependency conflicts và classloader overhead.
- Java/Kotlin compiler daemon startup/caching state.
- Root build có nhiều project scripts cần re-evaluate sau buildSrc change.

Đọc profile phase, task list và cache diagnostics trước khi chọn sửa. Có thể do proxy/Maven mirror hoặc JDK memory, chứ không phải do số dòng Kotlin.

## 8. Thí nghiệm Gradle Java 17: buildSrc convention plugin và multi-project

Bài lab cố tình nhỏ nhưng đầy đủ để người học có thể:
1. Chạy build ổn định.
2. Quan sát **buildSrc compilation/Gradle script compilation** lần đầu và warm.
3. Thay một convention plugin để xem invalidation.
4. Chuyển sang included build `build-logic` rồi đo lại theo cùng điều kiện.

### 8.1. Cây thư mục

```text
gradle-perf-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── java/example/build/
│       │   ├── BuildLabel.java
│       │   └── PrintLabelTask.java
│       └── kotlin/
│           └── java-conventions.gradle.kts
├── lib/
│   ├── build.gradle.kts
│   └── src/main/java/example/lib/Greeting.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/example/app/Main.java
```

Yêu cầu: Gradle Wrapper hỗ trợ Java 17 và có JDK 17 toolchain. Nếu chưa có Wrapper, dùng Gradle installation phù hợp để chạy `gradle wrapper`, commit `gradlew`/`gradlew.bat`, `gradle/wrapper/*` rồi dùng Wrapper. Không sửa Gradle version giữa các lần profiling.

**`settings.gradle.kts`**:

```kotlin
rootProject.name = "gradle-perf-lab"
include(":lib", ":app")
```

**Root `build.gradle.kts`:** có thể là file trống; conventions sẽ được apply ở modules. Dùng explicit per-module plugins thay vì một root `subprojects { apply(...) }` không cần thiết.

### 8.2. buildSrc/build.gradle.kts

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    mavenCentral()
}
```

`kotlin-dsl` hỗ trợ Kotlin-based build logic, Kotlin sources và precompiled script plugins. BuildSrc sẽ tự có Gradle API/tooling dependencies phù hợp theo plugin. Vì bài lab không cần external libraries ngoài Kotlin toolchain của `kotlin-dsl`, Maven Central dùng để resolve compiler/plugin dependencies khi cache chưa có.

**Không thêm `includeBuild("buildSrc")`**: Gradle tự nhận diện folder tên đặc biệt ở root.

### 8.3. Java 17 helper trong buildSrc

**`buildSrc/src/main/java/example/build/BuildLabel.java`:**

```java
package example.build;

import java.util.Locale;
import java.util.Objects;

public final class BuildLabel {
    private BuildLabel() {
    }

    public static String label(String module) {
        String normalized = Objects.requireNonNull(module)
            .strip()
            .toUpperCase(Locale.ROOT);
        return normalized + ":JAVA17";
    }

    public static void main(String[] args) {
        System.out.println(label(" app "));
    }
}
```

Java 17 code này dùng Java standard library, có thể biên dịch/chạy **ngoài Gradle**:

```bash
mkdir -p manual-build
javac --release 17 -d manual-build \
  buildSrc/src/main/java/example/build/BuildLabel.java
java -cp manual-build example.build.BuildLabel
```

Stdout **chính xác**:

```text
APP:JAVA17
```

Việc chạy `javac` chứng minh Java helper hợp lệ, **không chứng minh Gradle đã compile precompiled plugin**. Dưới đây là task type dùng Gradle API để được Gradle build/execute trong buildSrc context.

### 8.4. Custom task type dùng Property API

**`buildSrc/src/main/java/example/build/PrintLabelTask.java`:**

```java
package example.build;

import org.gradle.api.DefaultTask;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.TaskAction;

public abstract class PrintLabelTask extends DefaultTask {
    @Input
    public abstract Property<String> getLabel();

    @TaskAction
    public void printLabel() {
        System.out.println("BUILD_LABEL=" + getLabel().get());
    }
}
```

Đây là **Gradle task type**, cần Gradle API classpath từ build logic build. Nó có `@Input Property<String>` để khai báo task state, và task action chỉ đọc property. Do không có declared output, task này không nhằm mô phỏng `FROM-CACHE`; nó chỉ giúp đo **configuration vs execution** và tránh đọc `Project` trong task action.

### 8.5. Precompiled script plugin

**`buildSrc/src/main/kotlin/java-conventions.gradle.kts`:**

```kotlin
import example.build.BuildLabel
import example.build.PrintLabelTask

plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.register<PrintLabelTask>("showConvention") {
    label.set(BuildLabel.label(project.name))
}
```

BuildSrc với `kotlin-dsl` sẽ compile `java-conventions.gradle.kts` thành plugin ID **`java-conventions`**. Convention applies `java-library` và Java 17 toolchain. `tasks.register` không eagerly realize task; value của label được tính nhẹ khi task được cấu hình, còn `@TaskAction` không giữ tham chiếu `Project`.

**Lưu ý:** Nếu plugin chỉ làm `BuildLabel.label(project.name)`, thay helper implementation có thể vẫn làm buildSrc compiled classpath đổi — chính là tình huống để quan sát invalidation. Trong production, ưu tiên Provider/Property khi data đến từ mutable properties/files.

### 8.6. Library module

**`lib/build.gradle.kts`:**

```kotlin
plugins {
    id("java-conventions")
}
```

**`lib/src/main/java/example/lib/Greeting.java`:**

```java
package example.lib;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Hello, " + name.strip() + "!";
    }
}
```

### 8.7. Application module

**`app/build.gradle.kts`:**

```kotlin
plugins {
    id("application")
    id("java-conventions")
}

dependencies {
    implementation(project(":lib"))
}

application {
    mainClass.set("example.app.Main")
}
```

**`app/src/main/java/example/app/Main.java`:**

```java
package example.app;

import example.lib.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message(" Gradle "));
        System.out.println("JAVA=" + Runtime.version().feature());
    }
}
```

Dưới Gradle Java toolchain 17, `:app:run` dùng Java 17 launcher và in:

```text
Hello, Gradle!
JAVA=17
```

`runtime.version().feature()` trả Java major của JVM chạy app; nếu gọi thủ công bằng `java` từ PATH khác với toolchain, dòng JAVA có thể không phải 17.

### 8.8. Chạy và kiểm chứng bài lab

```bash
./gradlew --version
./gradlew -q javaToolchains

./gradlew :app:classes
./gradlew -q :app:showConvention
./gradlew -q :app:run
```

Stdout của riêng `:app:showConvention`:

```text
BUILD_LABEL=APP:JAVA17
```

Stdout của riêng `:app:run`:

```text
Hello, Gradle!
JAVA=17
```

`:app:classes` có output task logs thay đổi theo cache/JDK/Gradle version, nên không hard-code toàn bộ output. Không dùng `java -jar app/build/libs/...jar` khi app chưa có executable manifest; `application` plugin tạo `run` để chạy main class trên classpath.

### 8.9. Biên dịch/chạy production Java source độc lập

Cùng source Java 17 không phụ thuộc Gradle APIs, nên có thể chạy bằng JDK 17:

```bash
mkdir -p manual-app
javac --release 17 -d manual-app \
  lib/src/main/java/example/lib/Greeting.java \
  app/src/main/java/example/app/Main.java
java -cp manual-app example.app.Main
```

Khi `java` trong shell là JDK 17:

```text
Hello, Gradle!
JAVA=17
```

Lệnh manual này **không hề compile buildSrc hoặc Gradle scripts**, vì vậy nó phù hợp để minh họa ranh giới giữa compilation source ứng dụng và Gradle build-logic overhead. Nếu manual `javac` chạy nhanh nhưng Gradle build chậm, hãy nhìn profile phases; chưa đủ để kết luận Gradle có bug.

## 9. Trình tự profiling trên Demo A: biết mình đang đo gì

### 9.1. Bước 1 — baseline cold/warm với help

```bash
./gradlew help --no-configuration-cache --profile
./gradlew help --no-configuration-cache --profile
```

Lần đầu có thể compile buildSrc scripts và resolve Kotlin/compiler dependencies. Lần sau thường reuse buildSrc outputs/compiled scripts nếu không đổi. Mở cả hai HTML profiles và so phần `Settings and buildSrc`, `Configuring projects` và total time.

### 9.2. Bước 2 — quan sát buildSrc như build riêng

```bash
./gradlew -p buildSrc tasks --all
./gradlew -p buildSrc build --info
```

Tên tasks `compileKotlin`/`compileJava`/precompiled script processing phụ thuộc plugin/Gradle version; dùng `tasks --all` để biết danh sách thực tế, không suy ra tất cả Gradle releases đều đặt cùng tên.

`buildSrc build` có thể chạy tests nếu có plugin `check`/tests; bài lab này chưa tạo test sources. Output tasks `UP-TO-DATE` không chứng minh main build configuration cũng được reuse, vì chúng thuộc hai tầng khác.

### 9.3. Bước 3 — kiểm tra task executions thật

```bash
./gradlew :app:classes --no-configuration-cache --profile
./gradlew :app:classes --no-configuration-cache --profile
```

Nếu `:app:compileJava` `UP-TO-DATE` nhưng cả build vẫn chậm, time overhead có thể ở Settings/buildSrc/project configuration. Nếu profile chủ yếu ở `Task execution` và JavaCompile task thực sự chạy, đó là một vấn đề compile/task khác — đừng quy ngay cho scripts.

### 9.4. Bước 4 — bật Configuration Cache để so

```bash
./gradlew :app:classes --configuration-cache --profile
./gradlew :app:classes --configuration-cache --profile
```

Entry hợp lệ có thể skip phần lớn configuration lần sau. Nếu lần thứ hai vẫn cấu hình lại, đọc lý do Gradle nêu (input changed, problems, Gradle version, environment), rồi mới sửa scripts. **Bật Configuration Cache có thể gặp incompatibility ở plugins cũ**, không ép bỏ `--configuration-cache-problems=fail` chỉ để pass.

### 9.5. Bước 5 — thay đúng một file buildSrc

Tạo một commit/backup cho lab riêng của bạn; sửa một **giá trị output harmless** trong `BuildLabel.java`, ví dụ đổi suffix display từ `:JAVA17` thành `:JDK17`, rồi chạy lại cùng lệnh `help`, `:app:classes`, profile và inspect cache reuse.

Thay đổi như vậy có thể khiến:
- BuildSrc `compileJava` thực thi lại.
- Main project build-script classpath thay đổi.
- Kotlin DSL script compilation/cache entries có thể invalidate.
- Configuration Cache entry không được reuse.
- Java application `:app:compileJava` vẫn có thể UP-TO-DATE vì source/dependencies của app không đổi.

**Không sửa thêm plugin versions/Gradle Wrapper/JDK/other scripts trong cùng phép đo.** Nếu đổi nhiều biến, không thể quy nguyên nhân.

### 9.6. Bước 6 — quay lại baseline và đo migration

Khi so với included `build-logic`, dùng cùng Java sources, plugin behavior, CLI tasks, Java/Gradle versions và machine. Chạy nhiều warm runs và một change scenario ở convention logic. Không dùng những numbers giả lập trong `PerfSummary.java` để thay benchmark thực.

## 10. Groovy DSL tương đương cho Demo A

Bạn có thể xây **cùng ý tưởng** bằng Groovy scripts/precompiled plugin, giữ nguyên `Greeting.java`, `Main.java` và hai Java buildSrc helper classes.

**`settings.gradle`**:

```groovy
rootProject.name = 'gradle-perf-lab'
include 'lib', 'app'
```

**`buildSrc/build.gradle`**:

```groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    mavenCentral()
}
```

**`buildSrc/src/main/groovy/java-conventions.gradle`**:

```groovy
import example.build.BuildLabel
import example.build.PrintLabelTask

plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.register('showConvention', PrintLabelTask) {
    label.set(BuildLabel.label(project.name))
}
```

**`lib/build.gradle`**:

```groovy
plugins {
    id 'java-conventions'
}
```

**`app/build.gradle`**:

```groovy
plugins {
    id 'application'
    id 'java-conventions'
}

dependencies {
    implementation project(':lib')
}

application {
    mainClass = 'example.app.Main'
}
```

`groovy-gradle-plugin` là plugin phát triển precompiled Groovy script plugins; file nằm ở `src/main/groovy/java-conventions.gradle`. Không dùng file `.gradle.kts` trong Groovy plugin source set mà vẫn đòi plugin ID giống như trước.

Khi chạy `./gradlew -q :app:showConvention` và `-q :app:run`, output của Java task/app vẫn:

```text
BUILD_LABEL=APP:JAVA17
```

và:

```text
Hello, Gradle!
JAVA=17
```

Nếu muốn so cold Groovy vs Kotlin, phải công khai hai builds tương đương về plugins/tasks/inputs; **không chỉ đổi extension file** rồi kết luận Groovy nhanh hơn, vì `groovy-gradle-plugin` và `kotlin-dsl` có compilation behavior khác và warm states khác.

## 11. Những anti-pattern gây chậm configuration

### 11.1. Eager task creation và realization

**Không nên** nếu chỉ cần khai báo task cho tương lai:

```kotlin
// build.gradle.kts — ví dụ khái niệm.
tasks.create("generateReport") {
    group = "verification"
    doLast { println("report") }
}
```

`tasks.create` tạo/configure task eagerly trong configuration phase. Nếu một project có hàng nghìn tasks, việc tạo mọi task dù không dùng có thể gây chi phí không cần thiết.

**Nên dùng** task configuration avoidance:

```kotlin
tasks.register("generateReport") {
    group = "verification"
    doLast { println("report") }
}
```

`tasks.register` trả TaskProvider, cho phép cấu hình lazily. Đừng lập tức gọi `tasks.named("generateReport").get()` trong configuration để ép realize task trở lại.

Nếu cần cấu hình nhiều tasks theo type:

```kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
```

Đây là snippet khi dự án áp dụng Java plugin và có JUnit Platform dependencies. `configureEach` tránh eager configuration của mọi task so với một số pattern `all { ... }`; bản thân test task vẫn phải được thực thi khi nằm trong task graph.

### 11.2. Filesystem scan trong project configuration

**Không nên**:

```kotlin
// Chạy ngay trong configuration, kể cả lệnh ./gradlew help.
val allJavaFiles = fileTree("src/main/java").files
println("JAVA_SOURCE_COUNT=" + allJavaFiles.size)
```

Đoạn trên duyệt file tree trong configuration. Trên nhiều modules/cold disks, nó tốn I/O, làm thêm configuration inputs và có thể ảnh hưởng Configuration Cache reuse.

**Tốt hơn** nếu mục tiêu thật là copy inputs:

```kotlin
tasks.register<Copy>("copyJavaSources") {
    from(layout.projectDirectory.dir("src/main/java"))
    into(layout.buildDirectory.dir("copied-sources"))
}
```

Gradle có thể trì hoãn file resolution tới task execution. Chỉ khi task `copyJavaSources` được yêu cầu mới cần xử lý source tree; `./gradlew help` không phải scan Java sources để in số liệu vô ích. Đây là thiết kế khác behavior ban đầu (copy files thay vì luôn print count), phù hợp khi scan chỉ phục vụ một task; nếu bắt buộc đếm, viết task riêng với declared file inputs.

### 11.3. Dependency resolution trong configuration

**Không nên**:

```kotlin
// Giải quyết classpath ngay cả khi compile/test task không chạy.
val jars = configurations.getByName("compileClasspath").files
println("JARS=" + jars.size)
```

Mỗi lần cấu hình project sẽ cần resolve dependencies, có thể chạm repository metadata hoặc lock/mirror; `help` cũng bị chậm.

**Nên mô hình hóa deferred inputs** cho task cần chúng:

```kotlin
val compileClasspath = configurations.named("compileClasspath")

tasks.register<Copy>("stageDependencies") {
    from(compileClasspath)
    into(layout.buildDirectory.dir("staged-dependencies"))
}
```

Đoạn này chỉ minh họa với project đã áp dụng Java plugin và có configuration `compileClasspath`. `from` nhận Provider/Configuration, không ép truy cập `.files` ngay tại configuration. Nếu cần một custom task đọc resolved jars, dùng file collection task input và xử lý trong task action khi đã được khai báo phù hợp.

### 11.4. Network/API call trong Plugin.apply

**Không nên**:

```java
// Minh họa anti-pattern, không phải class đầy đủ.
public void apply(Project project) {
    // Gọi HTTP trực tiếp ở đây: mỗi lần apply plugin có thể chặn configuration.
}
```

Plugin.apply thường chạy trong configuration phase. Đừng gọi network, đọc secrets, chạy shell, scan large directories hoặc parse huge files một cách synchronous ở đây.

**Nên** đăng ký typed task với Provider inputs, thực hiện remote call (nếu task có lý do chính đáng) trong task execution, khai báo timeout/retry/security và tránh cache nếu có external side effects. Lazy task registration không giúp nếu chính plugin.apply vẫn làm expensive work ngay lập tức.

### 11.5. Áp plugins rộng hơn nhu cầu

`subprojects { apply(plugin = "some-heavy-plugin") }` có thể làm mọi module tốn plugin configuration, dù chỉ vài module dùng tính năng đó. Ưu tiên convention plugin được apply explicit ở đúng modules. Với plugin do người khác phát triển, xem task/plugin apply timeline trong Build Scan; đừng kết luận plugin “nặng” nếu nó bị apply đúng một lần và chi phí nhỏ.

### 11.6. Groovy dynamic logic trong plugin lớn

Groovy DSL script rất tiện, nhưng **plugin implementation phức tạp** có thể hưởng lợi từ Java/Kotlin statically compiled classes hoặc Groovy `@CompileStatic` khi dynamic behavior không cần thiết. Không có nghĩa Groovy DSL là anti-pattern. Thay đổi ngôn ngữ của toàn bộ scripts chỉ vì nghi ngờ chậm không có cơ sở nếu chưa profile.

## 12. buildSrc vs included build-logic: nguyên nhân và lựa chọn

Gradle Best Practices hiện hành thường ưu tiên **included build `build-logic`** cho reusable conventions/plugins trong repository lớn, thay vì buildSrc. Lý do quan trọng nhất trong bài này là **phạm vi classpath/invalidation**.

### 12.1. Mô hình tác động

**buildSrc**:

```text
buildSrc compile output + its dependencies
               |
               +--> common project build-script classpath
                         |
          +--------------+---------------+
          |              |               |
         :app           :lib             :tools
      script/cache    script/cache     script/cache
```

**included build**:

```text
build-logic plugins
   |
   +--> java-conventions applied in :app, :lib
   |
   +--> publishing-conventions applied only in :lib
   |
   +--> android-conventions applied only in :mobile
```

Một thay đổi trong buildSrc có thể invalidated script/classloader caches rộng. Với included build được chia nhỏ và các plugins chỉ apply ở nơi cần, Gradle có thể tránh invalidation cho những projects không cần plugin vừa thay đổi.

**Tuy nhiên:** đây không phải lời hứa “migrate là nhanh X%”. Included builds có overhead cấu hình/compile, plugin classpaths khác nhau nếu mỗi module apply một tổ hợp plugins khác, và có trường hợp buildSrc nhỏ/ổn định vẫn đơn giản hơn. Đo thực nghiệm trước và sau.

### 12.2. Bảng quyết định

| Tiêu chí | buildSrc | Included build-logic |
| --- | --- | --- |
| Cơ chế tham gia | Auto-detect khi folder nằm ở root. | Explicit `includeBuild`/`pluginManagement.includeBuild`. |
| Availability của classes | Có trên project build-script classpath. | Plugin classes ở classpath nơi plugin được resolve/apply. |
| Scope thay đổi | Có thể invalidate nhiều scripts/configuration caches. | Có thể giới hạn theo plugin/subproject dependencies. |
| Chi phí thiết lập | Thấp, hợp prototype/utility nhỏ. | Cần Settings riêng và plugin resolution config. |
| Chia build logic thành nhiều modules | Có thể tổ chức, nhưng classpath chung vẫn đáng chú ý. | Dễ chia plugins thành subprojects độc lập. |
| Settings plugins | Không nên giả định buildSrc dùng được sớm cho Settings. | Có thể include riêng trong `pluginManagement`. |
| Testing | `./gradlew -p buildSrc check` khi có tests. | `./gradlew -p build-logic check` hoặc tasks tương ứng. |
| Chia sẻ giữa repositories | Không tự publish. | Có thể publish/reuse plugin artifacts. |

## 13. Di chuyển lab từ buildSrc sang build-logic

Giữ **application/library Java sources**, behavior của convention plugin và tasks. Chuyển các build logic sources:

```text
gradle-perf-lab/
├── settings.gradle.kts
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/
│       ├── java/example/build/
│       │   ├── BuildLabel.java
│       │   └── PrintLabelTask.java
│       └── kotlin/java-conventions.gradle.kts
├── lib/
│   ├── build.gradle.kts
│   └── src/main/java/example/lib/Greeting.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/example/app/Main.java
```

**Root `settings.gradle.kts`:**

```kotlin
pluginManagement {
    includeBuild("build-logic")

    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "gradle-perf-lab"
include(":lib", ":app")
```

**`build-logic/settings.gradle.kts`:**

```kotlin
rootProject.name = "build-logic"
```

**`build-logic/build.gradle.kts`:**

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    mavenCentral()
}
```

**`build-logic/src/main/kotlin/java-conventions.gradle.kts`:** giữ nguyên plugin script từ mục 8.5.

**`app/build.gradle.kts` và `lib/build.gradle.kts`:** giữ nguyên `plugins { id("java-conventions") }` và application/project dependency.

Giữ source files `BuildLabel.java` và `PrintLabelTask.java` ở `build-logic/src/main/java` để plugin compile với helper. **Đây là included build mới, không phải module `:build-logic` của root**. Với included plugin build, khai báo trong `pluginManagement { includeBuild("build-logic") }` làm plugin ID khả dụng sớm cho `plugins {}` của root modules.

### 13.1. Một khác biệt cần test khi migration

Trước khi migrate, root scripts có thể viết `import example.build.BuildLabel` trực tiếp vì class từ buildSrc có mặt trên script classpath. Sau khi chuyển vào included build, class **không tự xuất hiện** ở mọi script; chỉ plugin classpaths được resolve theo mechanism mới. Do đó nên gọi behavior qua convention plugin/extension/task type đã áp dụng, không giữ direct imports từ buildSrc mà không thiết kế lại.

Trong lab, root/module scripts **không direct import BuildLabel**, nên migration đơn giản. Nếu repository thực có hàng trăm direct imports, xử lý chúng là một phần quan trọng của migration.

### 13.2. Thực hiện phép so có kiểm soát

Sau migration, chạy chính các workflow:

```bash
./gradlew help --no-configuration-cache --profile
./gradlew help --no-configuration-cache --profile

./gradlew :app:classes --configuration-cache --profile
./gradlew :app:classes --configuration-cache --profile
```

Rồi sửa một helper nhỏ/one convention plugin như thí nghiệm cũ. Lưu report paths, Gradle version, scripts recompiled và cache reuse. **Không ghi nhận gains từ lần đầu chuyển đổi (có nhiều files mới) làm steady-state benchmark**.

### 13.3. Settings plugin caveat

Gradle Best Practices có ghi chú riêng: nếu build-logic chứa **Settings plugins** phải được include trong `pluginManagement` sớm, đôi khi ảnh hưởng khả năng caching. Với hệ thống lớn, có thể dùng **một included build Settings logic tối giản** tách khỏi build-logic project plugins để giảm overhead. Lab chỉ có Project convention plugin nên không cần mô hình hóa trường hợp đặc biệt này.

## 14. Groovy DSL cho included build migration

Đối với Gradle build dùng Groovy, root **`settings.gradle`**:

```groovy
pluginManagement {
    includeBuild('build-logic')

    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = 'gradle-perf-lab'
include 'lib', 'app'
```

**`build-logic/build.gradle`**:

```groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    mavenCentral()
}
```

**`build-logic/src/main/groovy/java-conventions.gradle`**: giữ cùng nội dung Groovy convention plugin ở mục 10. Các Java helper/task types nằm tại `build-logic/src/main/java`.

Java source code từ `app`/`lib` vẫn như cũ; output `:app:showConvention` vẫn `BUILD_LABEL=APP:JAVA17` và app vẫn in `Hello, Gradle!` + `JAVA=17` khi toolchain là Java 17.

## 15. Vì sao bật Configuration Cache không tự sửa build logic xấu?

`--configuration-cache` lưu task graph/configuration state để lần sau có thể bỏ qua configuration. Điều này có thể giúp nhiều ngay cả khi configuration code chưa tối ưu, nhưng:

- Entry phải hợp lệ với build configuration inputs (Settings, scripts, buildSrc code, included builds, file/env values).
- Khi thay buildSrc hoặc build scripts, entry có thể invalidate, làm configuration phase chạy lại.
- Plugins/task actions phải đáp ứng requirements về serialization, `Project` references và external inputs.
- Sự phụ thuộc vào network/side effects vẫn là vấn đề correctness và reproducibility.
- CI ephemeral agents có thể không tái sử dụng local Configuration Cache như máy developer nếu không có chính sách lưu trữ được hỗ trợ.

**Đừng đẩy lỗi sang Configuration Cache bằng cách cố ignore inputs**. Nếu một file được đọc ở configuration time và thay đổi mỗi commit, nên thiết kế task để đọc nó **lazily** khi task thực sự cần, hoặc đưa vào task input Provider.

### 15.1. Configuration-time file read vs Provider

**Eager**:

```kotlin
// Build script dùng file trong configuration dù task không cần.
val policyText = file("policy.txt").readText()
```

**Deferred**:

```kotlin
val policy = providers.fileContents(
    layout.projectDirectory.file("policy.txt")
).asText
```

Provider có thể được nối vào `@Input Property<String>` của task. Nếu chỉ gọi `policy.get()` ngay ở top-level script, bạn đã đọc nó ở configuration time lần nữa — không có lợi ích deferral.

Gradle instrumentation có thể theo dõi nhiều configuration-time reads, vì vậy không nên tuyên bố mọi `file.readText()` sẽ làm stale cache. Tuy nhiên đọc eager có overhead và có thể làm thay đổi file trở thành lý do cache entry invalidation; deferred Provider giúp thu hẹp phạm vi tác động.

### 15.2. Task action không nên capture Project

**Không nên**:

```kotlin
tasks.register("badAction") {
    doLast {
        println(project.name) // Task action dùng Project at execution time.
    }
}
```

Trong task action, `Project` là Gradle model object không phù hợp với Configuration Cache serialization và isolated execution contract. Cách tốt hơn là đưa data vào typed task `@Input Property`. `PrintLabelTask.java` trong lab minh họa cách này; project name được tính trong configuration và task action chỉ đọc `getLabel().get()`.

## 16. Build Cache khác Configuration Cache và script cache

| Loại | Dùng vào mục đích gì? | buildSrc sửa thì sao? |
| --- | --- | --- |
| **Script compilation cache** | Reuse compiled Kotlin/Groovy build scripts/accessors. | Classpath/script changes có thể yêu cầu compile lại. |
| **Configuration Cache** | Reuse project/task graph configuration. | buildSrc sources/outputs là configuration inputs, có thể invalidate. |
| **Task Build Cache** | Reuse cacheable task outputs khi input keys tương đương. | Task implementation classpath có thể đổi; app JavaCompile không nhất thiết đổi. |
| **Dependency cache** | Reuse downloaded jars/POM/metadata. | Chỉ resolve lại khi cần/metadata policy. |
| **Incremental compilation** | Compile portions bị ảnh hưởng của build logic/app. | Class ABI/implementation change khác nhau theo compiler. |
| **Daemon** | Reuse Gradle JVM/classloading/JIT. | Restart daemon không tự xóa script caches. |

Một task `:app:compileJava UP-TO-DATE` không chứng minh Configuration Cache reusable. Một `Configuration cache entry reused` không chứng minh app JavaCompile đã `FROM-CACHE`. **Luôn ghi rõ lớp cache** trước khi chẩn đoán.

## 17. Bảng triệu chứng -> vùng cần điều tra

| Triệu chứng đo được | Vùng có khả năng chậm | Phép thử kế tiếp |
| --- | --- | --- |
| Lần đầu checkout rất chậm, lần hai nhanh | Gradle Wrapper/deps, Kotlin/Groovy script compilation, buildSrc compile. | Warm-up cùng tasks, xem profile/--info, tránh đổi nhiều inputs. |
| `help` chậm cả khi tasks up-to-date | Settings/buildSrc/configuration, plugin apply. | `help --profile` và Build Scan configuration. |
| Mỗi lần sửa buildSrc, nhiều scripts compile lại | Shared script classpath/caches invalidated. | Chỉ sửa buildSrc, so cache logs và migration thử. |
| `:app:compileJava` chạy lại thường xuyên | Source/generated code/toolchain/task inputs hoặc Build Cache key. | `--info`, task outputs, input fingerprints. |
| BuildSrc `compileKotlin` chiếm nhiều thời gian khi cold | Precompiled plugin/script Kotlin compilation, dependencies. | `-p buildSrc build --info`, compiler profiling, dependency resolution. |
| `buildSrc` UP-TO-DATE nhưng Configuring projects vẫn lớn | Plugin apply, eager tasks, file/network IO. | Build Scan plugin applications, remove eager work. |
| Build Scan “Dependency resolution during configuration” cao | `configurations.*.files`/`resolvedConfiguration` được gọi sớm. | Search build logic và chuyển sang deferred task inputs. |
| Configuration Cache luôn miss | Dynamic env/file/Settings/buildSrc inputs, plugins incompatible. | Đọc Gradle cache invalidation reason và requirements report. |
| Warm daemon nhanh nhưng CI fresh runner chậm | Disk caches/Gradle dist/plugins không được persist. | CI cache policy, avoid network/setup time, measure isolated stages. |
| Chuyển sang included build nhưng không cải thiện | Convention plugin quá chung, plugin combinations/classpath changes, tasks vẫn eager. | Profile lần nữa và chia plugin scopes hợp lý. |
| Java app run nhanh ngoài Gradle nhưng Gradle chậm | Startup/config/script/plugin overhead hoặc Gradle tasks khác. | So separate execution vs total build profile. |
| CPU cao ở Kotlin compiler process | Script/precompiled plugin compilation hoặc buildSrc sources. | JFR/Gradle Profiler, check buildSrc changes. |
| CPU thấp nhưng wall-clock cao | Blocking I/O, network, file locks, daemon startup. | Build Scan stages, network/mirror/AV investigation. |
| Memory/GC spikes khi configure | Plugin object graphs, eager task realization, heap pressure. | JVM profiler/JFR và reduce eager configuration. |

## 18. Debug checklist theo từng lớp

### 18.1. Startup

- [ ] Gradle Wrapper đã download trước khi đo steady-state?
- [ ] Daemon warm/cold được ghi rõ?
- [ ] Init scripts của user/CI có làm I/O/network không?
- [ ] Cùng JDK và JVM options khi so hai runs?
- [ ] Disk/antivirus/container CPU quota có bóp tốc độ không?

### 18.2. Script compilation

- [ ] Có lần đầu compile `build.gradle.kts`/`settings.gradle.kts` không?
- [ ] Script classpath/plugin versions đổi giữa các runs?
- [ ] Kotlin DSL type-safe accessors bị tạo lại do model/classpath changes?
- [ ] `buildSrc` code/metadata thay đổi dù app source không đổi?
- [ ] Kết quả `--info`/profile/JVM profiler có ủng hộ giả thuyết?

### 18.3. buildSrc

- [ ] `buildSrc` là root special build, không phải subproject?
- [ ] Build logic compile tasks có thật sự chạy hay UP-TO-DATE?
- [ ] Repositories/plugins của buildSrc có đang tải dependencies mạng?
- [ ] Helper đã được tách thành convention plugin với scope đúng?
- [ ] Direct helper imports vào scripts có tăng classpath coupling?
- [ ] Thử included `build-logic` trên branch/fixture riêng, đo cùng baseline?

### 18.4. Configuration

- [ ] Plugins chỉ apply nơi cần?
- [ ] `tasks.register`/`configureEach` thay cho eager create/all khi phù hợp?
- [ ] Không có dependency resolution trong configuration?
- [ ] Không có scan nhiều file/network call trong Plugin.apply?
- [ ] Task actions dùng typed Property/Provider inputs?
- [ ] Configuration Cache có usable/reusable và không stale?

### 18.5. Task execution

- [ ] Thời gian thật nằm ở `compileJava`, `test`, code generation hay packaging?
- [ ] Task inputs/outputs khai báo đầy đủ, có UP-TO-DATE/FROM-CACHE?
- [ ] Parallel workers phù hợp phần cứng?
- [ ] Không cố tối ưu script compilation trong khi bottleneck là test/network?

## 19. Lỗi thường gặp và cách xử lý

| Lỗi/quan sát | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Plugin [id: 'java-conventions'] was not found` | File plugin sai source set, `kotlin-dsl`/`groovy-gradle-plugin` chưa apply, hoặc included build chưa được include. | Kiểm tra `src/main/kotlin/*.gradle.kts`/`src/main/groovy/*.gradle` và root Settings. |
| `Unresolved reference: java` trong plugin script | Java plugin chưa apply ở `plugins {}`/type-safe accessors chưa có. | Áp dụng `java-library` rồi cấu hình JavaExtension. |
| `NoSuchMethodError` khi áp plugin | Version conflict Gradle/plugin/buildSrc classpath. | Kiểm tra compatibility trước khi xóa caches. |
| `compileKotlin` chậm bất ngờ | Kotlin compiler dependencies, K2 compatibility, daemon cold, nhiều plugin sources. | Profile buildSrc separately, check Gradle/Kotlin versions. |
| BuildSrc source đổi khiến project caches miss | Shared script classpath changed. | Xác minh bằng controlled edit và profile; tách included build nếu có lợi. |
| `--configuration-cache` fail | Plugin/tasks capture Project hoặc unsupported configuration operation. | Dùng Providers/Property, đọc CC report. |
| `Configuration cache entry cannot be reused` | Inputs mới/đã đổi (env, file, buildSrc, properties, settings). | Đọc lý do invalidation; tránh fake ignore inputs. |
| `tasks.register` nhưng task vẫn eager | Code gọi `get()`, `tasks.all`, hoặc plugin làm eager mutation. | Dùng TaskProvider/configureEach, đo task realization. |
| `--profile` không chỉ ra method chậm | HTML report ở level phases/tasks, không method-level. | Build Scan/Gradle Profiler/JFR. |
| Build Scan không tạo được | Policy/consent, plugin setup hoặc network. | Dùng `--profile` offline, không ép xuất build data. |
| `:app:run` fail Java class version | Gradle/JDK toolchain/runtime mismatch. | `./gradlew --version`, `javaToolchains`, JDK compatibility matrix. |
| `java -jar` báo no main manifest | App jar không cấu hình executable manifest. | Dùng `./gradlew :app:run` hoặc đúng classpath. |
| Script cache bị xóa thủ công, build chậm hơn | Cold Kotlin/Groovy script compilation. | Để Gradle quản lý caches, warm-up lại. |
| Plugin apply chỉ tốn ít nhưng build vẫn chậm | Task execution/startup/dependency resolution là bottleneck. | Tách phase và đo lại trước khi refactor. |
| CI 1 nhanh CI 2 chậm | Khác runner CPU/disk, Gradle User Home, dependencies hoặc daemon. | Ghi environment và chuẩn hóa cache policy. |
| Included build plugin không resolve | `pluginManagement.includeBuild` chưa cấu hình hoặc wrong plugin ID. | Bổ sung đúng Settings và plugin source. |
| Project script import BuildLabel mất sau migration | Included plugin không phơi trực tiếp class cho mọi scripts. | Đưa behavior vào plugin/extension API. |
| `--scan` gửi dữ liệu không mong muốn | Scan publish tới external server. | Dùng approved server hoặc `--profile`. |
| Groovy/Kotlin cold benchmark lệch nhiều | Script compilation, plugin builds và caches khác. | Warm/steady-state cùng tasks, báo metadata đầy đủ. |

## 20. Bộ lệnh điều tra nhanh

```bash
# 1. Môi trường:
./gradlew --version
./gradlew -q javaToolchains

# 2. Profile configuration overhead:
./gradlew help --no-configuration-cache --profile
./gradlew help --no-configuration-cache --profile

# 3. Profile actual developer workflow:
./gradlew :app:classes --profile

# 4. Build logic riêng:
./gradlew -p buildSrc tasks --all
./gradlew -p buildSrc build --info

# 5. Inspect plugin/script/dependency logs:
./gradlew help --info

# 6. Cache reuse:
./gradlew :app:classes --configuration-cache
./gradlew :app:classes --configuration-cache

# 7. Optional external/enterprise scan (after privacy approval):
./gradlew help --scan
```

Nếu đã migrate và không còn buildSrc, hai lệnh `-p buildSrc` không còn áp dụng; dùng `./gradlew -p build-logic tasks --all` và `build` (hoặc task tương ứng). Các examples đều yêu cầu Gradle Wrapper sẵn và môi trường JDK/plugin dependencies phù hợp.

## 21. Bảng ghi nhớ ra quyết định

| Nếu quan sát | Ưu tiên thử |
| --- | --- |
| Startup cao | Warm daemon, Gradle/JVM compatibility, init scripts, disk/network. |
| Settings/buildSrc cao lần đầu | Warm caches, profile buildSrc compilation và plugin dependencies. |
| Settings/buildSrc cao mỗi lần | Tìm Settings custom logic, buildSrc changes, dependency resolution. |
| Kotlin script compilation lặp | So classpaths/scripts/accessors/`buildSrc` invalidation. |
| Project configuration cao | Plugin applications, eager tasks, network/I/O, dependency resolve sớm. |
| App source compile cao | Java compiler/incremental compilation/task cache, không lạm tối ưu scripts. |
| Cache entry không reused | Xem nguyên nhân Configuration Cache miss, không vô hiệu input tracking. |
| buildSrc làm invalidate diện rộng | Thử included build-logic, chia conventions theo module và đo lại. |
| Groovy/Kotlin script được cho là chậm | Controlled warm/cold benchmark; không dựa vào thành kiến. |
| Performance regression sau plugin upgrade | Bisect plugin version với Gradle/JDK/inputs cố định. |
| CI khác developer | So Gradle User Home/cache, daemon, network, runner resources. |
| Mục tiêu bảo mật của Build Scan | Chỉ publish sau approval hoặc dùng local HTML profile. |

## 22. Những nguyên tắc tối ưu bền vững

1. **Profile trước**, không thay đổi Gradle Wrapper/plugin ecosystem ngay khi chưa có baseline.
2. **Đo đúng workflow**: một lần `help` nhanh không chứng minh full `check` nhanh; một lần `clean build` không phản ánh developer iteration.
3. **Kiểm soát warm/cold states**, JDK, daemon, dependencies và caches; lặp nhiều samples.
4. **Phân loại phase** trước khi đọc source code để tránh tối ưu sai chỗ.
5. **Ưu tiên declarative, lazy configuration**: `tasks.register`, `configureEach`, Providers/typed task properties.
6. **Không resolve dependencies hoặc scan filesystem sớm** nếu task không cần chúng.
7. **Chỉ apply plugins nơi thật sự cần**, đóng gói conventions có phạm vi rõ.
8. **Tách build logic khỏi application code**; không để buildSrc runtime dependencies rò vào app.
9. **Đánh giá classpath coupling của buildSrc**, thử included build-logic khi vấn đề có thể kiểm chứng.
10. **Tận dụng Configuration Cache** khi plugin/task đáp ứng requirements, không tắt correctness checks.
11. **Giữ script caches** cho warm builds, không xóa toàn bộ Gradle User Home vì một warning.
12. **Tôn trọng bảo mật khi dùng Build Scan**, kiểm soát dữ liệu công bố.
13. **Chứng minh sau khi tối ưu**: cùng tasks, cùng environment, same behavior, p50/p90 cải thiện ngoài nhiễu.
14. **Nếu không cải thiện, rollback thay đổi**; architecture đẹp hơn nhưng performance không cải thiện vẫn có thể có giá trị bảo trì, cần tách lý do.

## 23. Tự kiểm tra kiến thức

1. **`:app:compileJava UP-TO-DATE` nhưng tổng build chậm ở đâu?** — Có thể startup, Settings, buildSrc hoặc project configuration, không phải JavaCompile.
2. **`--profile` có chỉ ra từng method chậm trong Kotlin DSL không?** — Không, nó chủ yếu breakdown phases/tasks; cần scan/profiler sâu hơn.
3. **Script compilation và script evaluation khác gì?** — Compilation chuyển script thành code có thể cache; evaluation chạy code cấu hình dự án.
4. **buildSrc là `:buildSrc` subproject?** — Không, nó là Gradle build đặc biệt tại root.
5. **Sửa buildSrc class có thể invalidated scripts không dùng helper trực tiếp?** — Có, vì shared script classpath.
6. **Có chắc sửa buildSrc làm mọi production Java tasks rerun?** — Không; task up-to-date/build cache logic độc lập.
7. **Vì sao cùng source có cold Kotlin build chậm hơn warm?** — Lần đầu có script/accessor compilation, plugin/dependency resolution, JVM warmup.
8. **Tại sao `tasks.create` có thể gây chậm?** — Nó eagerly tạo/configure task dù task không được dùng.
9. **Vì sao `configurations.compileClasspath.files` tại top-level nguy hiểm?** — Resolve dependencies ngay trong configuration, kể cả lệnh `help`.
10. **Có phải cứ bật Configuration Cache là build logic hết chậm?** — Không, entry có thể miss hoặc plugin incompatible; vẫn nên tối ưu expensive configuration.
11. **Migration buildSrc -> build-logic cần thay gì?** — Explicit include trong Settings và xử lý direct helper imports/classpaths.
12. **Nên báo metric nào?** — Total wall-clock, phase breakdown, repeated p50/p90, cache reuse, Gradle/JDK/environment.
13. **Profile script compilation chậm có nên xóa ~/.gradle/caches?** — Không; xóa caches khiến compilation lạnh và mất dependencies.
14. **Có nên publish `--scan` trên source nội bộ?** — Chỉ sau khi xác minh chính sách chia sẻ dữ liệu và endpoint.

**Kết luận:** Tìm nút thắt build Gradle là một bài toán **đo nguyên nhân theo lifecycle**, không phải tìm task có thời gian lớn nhất rồi tối ưu bừa. Phân biệt chi phí script compilation lần đầu, script evaluation/configuration lặp lại và buildSrc compile/classpath invalidation. Dùng `--profile` để tìm phase, Build Scan/Gradle Profiler để đi sâu, `--info` để nhận biết recompilation và cache reuse. Tối ưu bằng lazy task configuration, Provider API, giới hạn plugin applications và included `build-logic` khi có lợi; sau đó chạy benchmark đa lần, giữ nguyên semantics của Java build và xác minh độ cải thiện thực.

### Tài liệu chính thức và công cụ tham khảo

- [Gradle — Improve the Performance of Gradle Builds](https://docs.gradle.org/current/userguide/performance.html): baseline, profile, task/configuration performance, lazy configuration.
- [Gradle — Build Scan and Profile Reports](https://docs.gradle.org/current/userguide/inspect.html): `--scan`, `--profile`, phases, settings/buildSrc và Gradle Profiler.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): build-logic included build vs buildSrc, classpath invalidation.
- [Gradle — Kotlin DSL Primer](https://docs.gradle.org/current/userguide/kotlin_dsl.html): compiled scripts, accessors, first-use overhead và IDE synchronization.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration inputs, buildSrc/included builds, reuse.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): Provider/Property APIs, task action serialization.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): tasks.register, named, configureEach.
- [Gradle — Sharing Build Logic using buildSrc](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): buildSrc detection and script classpath.
- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html): precompiled script conventions.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): plugin-producing included builds.
- [Gradle — Gradle-managed Directories and Caches](https://docs.gradle.org/current/userguide/directory_layout.html): version-specific script caches.
- [Gradle Profiler](https://github.com/gradle/gradle-profiler): repeatable benchmarks và change scenarios.
