# So sánh kết quả nhiều lần và tránh đánh đổi tính đúng để tăng tốc Gradle build

## 1. Build nhanh hơn chỉ có giá trị khi kết quả vẫn đúng

Một đội Java đang tối ưu Gradle có thể thấy số liệu như sau:

```text
Trước tối ưu: ./gradlew clean check → 28 giây
Sau tối ưu:   ./gradlew assemble    → 12 giây
```

Không thể kết luận build đã nhanh hơn 57%, vì **hai lệnh thực hiện công việc khác nhau**. `check` có thể chạy các verification tasks, trong khi `assemble` thường tập trung vào tạo artifacts. Nếu bỏ kiểm thử, bỏ phân tích chất lượng hoặc dùng output cũ, thời gian thấp đi không phải một cải thiện tương đương.

Ngay cả khi dùng cùng một lệnh, hai lần đo cũng có thể khác nhau do daemon JVM warm-up, operating-system file cache, Gradle dependency cache, số core CPU trống, tải server, network latency, Gradle Build Cache, Configuration Cache và tình trạng up-to-date của tasks.

Vì vậy bài học đặt **hai điều kiện bắt buộc** cho mọi tối ưu:

1. **Công bằng về phép đo**: so cùng workload và environment tương đương, chạy đủ số lần, phân biệt warm/cold/incremental/no-op, lưu những mẫu đo chứ không chọn một kết quả đẹp nhất.
2. **Giữ tính đúng**: outputs, API/ABI, tests, runtime behavior, dependency graph, security policy, task inputs/outputs và release artifacts vẫn đáp ứng hợp đồng đã xác định.

**Tiêu chí thành công:** chỉ chấp nhận tối ưu khi có **bằng chứng cải thiện hiệu năng lặp lại được** và **quality gates không suy giảm**. Những con số thời gian trong ví dụ ở đây là dữ liệu **minh họa**, không phải benchmark đã đo trên máy của người đọc.

### 1.1. Mô hình trước – sau đúng

```text
          Định nghĩa workload và correctness contract
                              |
                              v
                 Baseline A: nhiều lần chạy
                              |
                              v
                    Một thay đổi có chủ đích
                              |
                              v
                 Candidate B: nhiều lần chạy
                              |
                              v
           So sánh median / spread / p95 / noise
                              |
               +--------------+---------------+
               |                              |
               v                              v
        Correctness PASS                Correctness FAIL
         + speedup có thật                    |
               |                              v
               v                       REJECT / REVERT
        Chấp nhận có điều kiện
         + monitor CI regressions
```

Không nên chạy candidate B một lần trên một daemon đã warm và so với baseline A lần đầu tải dependencies từ Internet. Chênh lệch đó chủ yếu phản ánh **điều kiện thử nghiệm**, không phản ánh thay đổi build logic.

## 2. Những loại build phải được đo riêng

Đối với Gradle, từ “build time” chưa đủ chính xác. Cần chỉ rõ người dùng đang làm thao tác gì.

| Kịch bản | Định nghĩa thực tế | Tình huống đại diện |
| --- | --- | --- |
| **Cold start / cold daemon** | Gradle daemon mới khởi động; JIT và caches trong process chưa warm | CI runner mới, lần đầu mở IDE/build |
| **Clean build** | Xóa outputs của project bằng `clean` rồi thực hiện tasks | Build từ workspace không có `build/` |
| **Warm build** | Gradle daemon và một phần caches đã warm | Developer chạy command nhiều lần |
| **No-op / up-to-date build** | Không đổi source/config, tasks nên được bỏ qua nếu inputs/outputs không đổi | Developer nhấn Run/Test lại |
| **Incremental non-ABI change** | Sửa implementation mà public API không đổi | Đổi thân method Java |
| **Incremental ABI change** | Sửa chữ ký hoặc public API | Đổi interface, public method/field |
| **Cache-hit build** | Output không còn trong workspace nhưng có thể lấy từ Build Cache | CI khác reuse artifact |
| **Configuration-cache reuse** | Task graph được khôi phục từ Configuration Cache | Build lặp với cấu hình không đổi |
| **Test iteration** | Developer chỉ chạy tests liên quan | `:app:test` thay vì tất cả modules |
| **Full verification** | Chạy toàn bộ quality gate đã định nghĩa | `clean check` hoặc pipeline release |

Những kịch bản này **không thể dùng thay nhau để tạo tuyên bố phần trăm tăng tốc**.

### 2.1. `clean` không đồng nghĩa “cold hoàn toàn”

Lệnh:

```bash
./gradlew clean build
```

xóa outputs theo task `clean` của build, nhưng **không nhất thiết** xóa:

- Gradle User Home dependency caches.
- Build Cache local/remote.
- Gradle Daemon đang chạy và JIT state.
- OS file system caches.
- Docker layer caches hoặc CI caches khác.
- Configuration Cache ở `.gradle` nếu chưa bị invalidation.

Đây là “workspace clean build” chứ chưa chắc là cold-daemon hoặc cold-dependency build. Trong báo cáo cần ghi tên scenario cụ thể, tránh dùng chữ “cold” quá rộng.

### 2.2. `UP-TO-DATE`, `FROM-CACHE` và `SUCCESS`

- `UP-TO-DATE`: Gradle xác định inputs/outputs của task hiện tại không cần chạy lại.
- `FROM-CACHE`: task outputs được tái sử dụng từ Build Cache.
- `SUCCESS` / task được thực thi: task action chạy thành công.
- `NO-SOURCE`: một task có thể không có nguồn xử lý.
- `SKIPPED`: task bị skip theo cấu hình/hành vi task.

Nếu benchmark no-op nhưng một thay đổi làm `test` trở thành `SKIPPED` thay vì `UP-TO-DATE`, phải xem **nguyên nhân skip**. Nó có thể phản ánh việc bỏ kiểm thử chứ không phải tăng hiệu quả cache.

## 3. Viết giả thuyết trước khi tối ưu

Một phép thử tốt bắt đầu với **một giả thuyết có thể bác bỏ**.

Ví dụ:

> Việc chuyển configuration-time file scan của custom plugin sang Provider/task execution sẽ giảm median của `help` và `:app:test` trong chế độ warm, trong khi số tasks, test coverage, generated files và runtime output không đổi.

Giả thuyết nên nêu:

1. **Bottleneck**: configuration, dependency resolution, compilation, tests, I/O, GC hay network.
2. **Thay đổi duy nhất**: nâng Gradle/plugin, bật cache, tối ưu task inputs, cấu hình parallelism...
3. **Workload cụ thể**: `help`, `:app:test`, `check`, incremental edit, clean build.
4. **Chỉ số chính**: median elapsed time hoặc p95 (tùy nhu cầu).
5. **Guardrail**: tests, lint, artifact consistency, cache correctness, security.
6. **Tiêu chí đạt**: ví dụ giảm ít nhất 10% median với độ biến động chấp nhận được, trên cùng nhóm máy.
7. **Giới hạn**: JDK/Gradle versions và nền tảng được thử.

Không nên bắt đầu bằng “bật tất cả flags tối ưu rồi xem có nhanh không”, vì khi kết quả thay đổi rất khó biết yếu tố nào gây ra khác biệt.

## 4. Quy trình A/B có kiểm soát

### 4.1. Chốt baseline A và candidate B

- **A**: một commit hoặc tag có build logic hiện tại.
- **B**: commit chỉ chứa thay đổi tối ưu đang đánh giá, hoặc một bộ thay đổi được định nghĩa rõ.
- Cả hai phải chạy **cùng task targets**, test suites và input data.
- Dùng cùng Gradle Wrapper version, JDK, OS, CPU profile, worker count, memory settings và network policy **trừ yếu tố đang chủ động so sánh**.
- Không để candidate tự tải dependency versions khác do notation dynamic như `1.+` hoặc `latest.release`.
- Ghi `git rev-parse HEAD`, `./gradlew --version`, toolchain và môi trường CI.
- Không chạy song song các tác vụ benchmark nặng làm tranh chấp cùng CPU/disk.

Nếu B chính là **nâng Gradle** hoặc **nâng JDK**, phải ghi rõ version là biến độc lập; không giả vờ environment không thay đổi.

### 4.2. Dùng nhiều vòng thay vì đo một lần

Một protocol hợp lý để bắt đầu:

1. Chạy **warm-up 3–6 lượt** (không tính vào số liệu) cho scenario có daemon nóng.
2. Thu **10–20 lượt đo** cho mỗi scenario/biến thể, hoặc nhiều hơn nếu biến động lớn.
3. Luân phiên A/B theo block A→B→B→A hoặc thứ tự cân bằng để hạn chế nhiễu do thời gian.
4. Lưu **từng mẫu đo**, exit code, trạng thái tasks, cache hit/miss.
5. Tính median, spread (IQR hoặc độ lệch) và p95 khi mẫu đủ nhiều.
6. Nếu chênh lệch nhỏ so với noise, không kết luận cải thiện.
7. Lặp lại trên một máy/runner khác hoặc một khoảng thời gian khác nếu kết quả quan trọng.

3–6 warm-ups hay 10–20 samples là **gợi ý khởi đầu, không phải ngưỡng thống kê thần kỳ**. Độ dài phép thử phụ thuộc mục tiêu, noise và mức cải thiện kỳ vọng.

### 4.3. Vì sao thứ tự chạy có thể gây thiên lệch?

Nếu chạy 10 lần A trước rồi mới chạy 10 lần B:

- B có thể hưởng OS file cache tốt hơn.
- JIT có thể đã warm sau A.
- Server remote cache có thể được A populate.
- CPU có thể nóng/thermal throttle ở lượt sau.
- CI runner có thể bị thay workload/network giữa hai nhóm.

Phương án tốt hơn là thực hiện A/B theo block trên các environments tương đương, hoặc dùng Gradle Profiler với scenario/mutator được quản lý thống nhất. Tuy nhiên, **đừng chạy A và B đồng thời trên cùng host** nếu chúng tranh chấp nguồn lực.

### 4.4. Lập nhật ký phép đo

Một bảng kết quả nên có:

| Trường | Ví dụ minh họa |
| --- | --- |
| Baseline commit | `A_SHA` (hash commit thực tế) |
| Candidate commit | `B_SHA` |
| Gradle | Version từ Wrapper |
| Gradle daemon JVM | Vendor/version từ `--version` |
| Toolchain | Java 17 |
| OS/runner | Linux CI, 4 vCPU |
| Command/scenario | `check`, no-op hoặc clean |
| Build Cache | On/Off, local/remote |
| Configuration Cache | On/Off, reuse/miss |
| Parallel workers | `--max-workers=4` |
| Warm-ups/iterations | 5/15 |
| Wall-clock samples | CSV số liệu từ profiler |
| Correctness | JUnit PASS, artifacts checked |
| Anomalies | Dependency download, noisy runner |
| Quyết định | Accept, reject hoặc repeat |

**Không sao chép số liệu minh họa vào báo cáo thực**. Thay bằng kết quả của đúng machine/pipeline đã chạy.

## 5. Công cụ Gradle cho việc quan sát

### 5.1. `--profile`: báo cáo HTML cục bộ

```bash
./gradlew check --profile --console=plain
```

Gradle tạo HTML profile report thường ở:

```text
build/reports/profile/
```

Report có thông tin thời gian initialization/configuration/task execution ở mức khái quát. Nó là **một mẫu profile**, không phải công cụ tự làm benchmark thống kê với nhiều lượt. Khi chẩn đoán công việc chậm, nó là bước khởi đầu tiện lợi.

### 5.2. Build Scan: timeline và build cache insight

```bash
./gradlew check --scan --console=plain
```

Trong môi trường được cấu hình hỗ trợ Build Scan/Develocity và cho phép xuất bản thông tin, scan có thể cho thấy:

- Timeline và critical path.
- Tasks nào chạy, bị skip, up-to-date hoặc from-cache.
- Configuration và dependency resolution time.
- Test execution time.
- Cache hit/miss và lý do không cacheable.
- Worker parallelism, CPU/memory/GC, network download.

**Cảnh báo bảo mật:** Build Scan có thể gửi metadata về build, source paths, task names, dependencies hoặc môi trường lên dịch vụ scan. Chỉ dùng khi tổ chức cho phép, kiểm tra terms/redaction và data access; không tự upload scan của dự án nhạy cảm.

### 5.3. `--info`, `--debug` và `--dry-run`

```bash
./gradlew check --info --console=plain
./gradlew check --dry-run --console=plain
```

`--info` giúp chẩn đoán vì sao task được chạy/cache hit hoặc không. `--dry-run` chỉ hiển thị kế hoạch task, **không đo thời gian thực thi và không xác nhận tests pass**.

`--debug` có thể sinh logs lớn, tiết lộ thông tin cấu hình hoặc dữ liệu nhạy cảm. Không dùng debug làm mặc định khi benchmark; logs quá lớn cũng có thể **làm sai số đo** do I/O.

### 5.4. Gradle Profiler: benchmark nhiều lần

[Gradle Profiler](https://github.com/gradle/gradle-profiler) là công cụ riêng để chạy một hoặc nhiều scenarios lặp lại, thu mẫu và xuất CSV/HTML/JSON. Những flags hữu ích:

| Flag | Chức năng |
| --- | --- |
| `--benchmark` | Chế độ benchmark lặp nhiều builds |
| `--project-dir` | Thư mục root build |
| `--scenario-file` | File HOCON mô tả workload |
| `--warmups` | Số lượt warm-up |
| `--iterations` | Số lượt đo |
| `--output-dir` | Thư mục lưu reports |
| `--csv-format long` | CSV dạng một sample một dòng |
| `--cold-daemon` | Dùng Gradle daemon vừa khởi động |
| `--no-daemon` | Không tái sử dụng daemon theo cách thông thường |
| `--gradle-version` | So phiên bản Gradle cụ thể |
| `--measure-config-time` | Đo thêm chi tiết configuration time |
| `--profile jfr` | Lấy Java Flight Recorder profile khi tương thích |

Với CLI hiện hành, Gradle Profiler mặc định có thể dùng Gradle version từ **Wrapper** của project. Không coi thời gian chạy ứng dụng `gradle-profiler` là một phần Java application mà người dùng đang tạo.

**Không nhầm `gradle-profiler --benchmark` với `./gradlew --profile`.** Một cái orchestrate nhiều runs và samples; cái kia tạo profile report cho một Gradle invocation.

## 6. Bài thực hành Java 17: giữ output và tests làm tiêu chuẩn đúng

Ta tạo một Gradle Java application nhỏ có hành vi deterministic. Mục tiêu không phải chứng minh project nhỏ cần optimization, mà là có một **fixture runnable** để tập thao tác profiling và correctness gates.

### 6.1. Cây thư mục

```text
gradle-benchmark-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties        (tùy chọn, không chứa secrets)
├── performance.scenarios    (Gradle Profiler)
├── src/main/java/demo/
│   ├── Calculator.java
│   └── Main.java
├── src/test/java/demo/
│   └── CalculatorTest.java
└── tools/
    └── BenchmarkStats.java
```

Yêu cầu: Gradle Wrapper tương thích Java 17, JDK 17/toolchain được Gradle tìm thấy; Maven Central hoặc dependency cache để tải JUnit 5. Nếu project chưa có Wrapper, cần một Gradle tương thích đã cài để chạy `gradle wrapper` một lần.

### 6.2. `settings.gradle.kts`

```kotlin
rootProject.name = "gradle-benchmark-lab"
```

Không cần multi-project để giải thích đo lường. Khi chuyển sang codebase thật, dùng đúng root settings, dependency graph và CI task graph hiện có; đừng biến một single-project toy thành bằng chứng tăng tốc của một multi-module monorepo.

### 6.3. `build.gradle.kts`

```kotlin
plugins {
    application
}

group = "dev.learning"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

application {
    mainClass.set("demo.Main")
}

tasks.test {
    useJUnitPlatform()
}
```

Không thêm `-x test` hay `test { enabled = false }`. Build script giữ `test` là quality gate thực sự. `application` tạo `run`, còn các Java tasks cung cấp `classes`, `jar`, `test`, `check`.

### 6.4. `Calculator.java`

**File `src/main/java/demo/Calculator.java`:**

```java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static long sumOfSquares(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be non-negative");
        }

        long result = 0L;
        for (long i = 1; i <= n; i++) {
            result += i * i;
        }
        return result;
    }
}
```

Hàm tính tổng bình phương các số từ 1 tới `n`. Với `n=1000`, kết quả là `333833500`. Tính toán hoàn toàn deterministic trong phạm vi test; không phụ thuộc network, clock, locale hay random number generator.

**Lưu ý giới hạn:** `long` cũng có thể overflow nếu `n` quá lớn; API minh họa chỉ kiểm thử dải `0..1000`. Trong thư viện production, phải có contract giới hạn input hoặc dùng số lớn hơn khi yêu cầu.

### 6.5. `Main.java`

**File `src/main/java/demo/Main.java`:**

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
                "checksum=" + Calculator.sumOfSquares(1000)
        );
    }
}
```

Chương trình tạo một kết quả cụ thể có thể so sánh trước và sau tối ưu.

### 6.6. JUnit 5 kiểm tra nhiều inputs

**File `src/test/java/demo/CalculatorTest.java`:**

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

final class CalculatorTest {
    @Test
    void matchesClosedFormulaForSmallNonNegativeInputs() {
        for (int n = 0; n <= 1000; n++) {
            long expected = (long) n * (n + 1) * (2L * n + 1) / 6L;
            assertEquals(expected, Calculator.sumOfSquares(n), "n=" + n);
        }
    }

    @Test
    void rejectsNegativeInput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Calculator.sumOfSquares(-1)
        );
    }
}
```

Tính đúng không chỉ là một stdout sample. Test kiểm tra một khoảng đầu vào cùng hợp đồng xử lý input âm. Khi candidate dùng một thuật toán nhanh hơn (ví dụ thay vòng lặp bằng công thức), **cả hai tests phải tiếp tục pass**, đồng thời cần đánh giá overflow/behavior với input lớn theo contract thực.

### 6.7. Chạy verification và xác nhận stdout

Từ root `gradle-benchmark-lab`, Linux/macOS:

```bash
./gradlew clean check --no-build-cache --no-configuration-cache --console=plain
./gradlew run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat clean check --no-build-cache --no-configuration-cache --console=plain
.\gradlew.bat run --quiet
```

**Stdout chính xác do `demo.Main` in:**

```text
checksum=333833500
```

Lệnh `clean check` phải thực sự chạy tests trong fixture đã tạo. Nếu task `test` báo `NO-SOURCE` thì source layout/test detection đang sai, không được tính là correctness PASS.

### 6.8. Kiểm tra trực tiếp bằng `javac`/`java`

Mặc dù app được Gradle quản lý, Java code không phụ thuộc thư viện ngoài, nên có thể biên dịch độc lập:

Linux/macOS:

```bash
mkdir -p build/manual-classes
javac -d build/manual-classes src/main/java/demo/Calculator.java src/main/java/demo/Main.java
java -cp build/manual-classes demo.Main
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force build\manual-classes | Out-Null
javac -d build\manual-classes src\main\java\demo\Calculator.java src\main\java\demo\Main.java
java -cp build\manual-classes demo.Main
```

Kết quả vẫn là `checksum=333833500`. Đây là kiểm tra độc lập của Java source chính; **không thay thế** `:test` vì JUnit và Gradle pipeline còn kiểm tra các phần khác.

## 7. Thực hành các kịch bản trước khi tối ưu

### 7.1. Kịch bản A — clean workspace build

```bash
./gradlew clean check --no-build-cache --no-configuration-cache --console=plain
```

Ở đây ta cố tình tắt cả Build Cache và Configuration Cache để đo task execution của build từ outputs mới, **không tắt tests**. Đây vẫn không phải cold-dependency hay cold-daemon build.

Không chạy một lần rồi chốt con số. Dùng Gradle Profiler trong mục 8 để lặp workload tương đương.

### 7.2. Kịch bản B — no-op build

```bash
./gradlew check --no-build-cache --no-configuration-cache --console=plain
./gradlew check --no-build-cache --no-configuration-cache --console=plain
```

Nếu không có thay đổi, Gradle có thể báo `UP-TO-DATE` cho compilation/tests và chỉ có phần khởi tạo/cấu hình. No-op build trả lời câu hỏi: “developer chạy lại cùng command sau khi không sửa gì có phải chờ bao lâu?”.

**Không dùng no-op sau khi task `test` đã được vô hiệu hóa** để chứng minh tối ưu testing. Phải đọc task outcomes.

### 7.3. Kịch bản C — thay đổi implementation giữ ABI

Trong `Calculator.sumOfSquares`, giả sử đổi thuật toán vòng lặp thành một implementation khác **vẫn giữ cùng public signature**. Đây là non-ABI change. Trong một multi-project build, Gradle có thể tránh compile downstream modules khi ABI không đổi.

Không phải mọi non-ABI change đều bảo toàn behavior. Test từ `0..1000` là guardrail; nếu candidate trả kết quả sai, reject dù compile task nhanh hơn.

### 7.4. Kịch bản D — thay đổi API

Một thay đổi như chuyển tên method `sumOfSquares` thành `sumSquares` hoặc đổi visibility có thể phá contract. Build tool phải phát hiện/recompile các consumers cần thiết. Nếu sau tối ưu build bỏ qua recompilation sai, đó là **regression về tính đúng**, không phải một thành công về compile avoidance.

Đo non-ABI và ABI workloads riêng, vì chúng đòi hỏi lượng công việc khác nhau.

### 7.5. Kịch bản E — Build Cache on/off

```bash
./gradlew clean check --no-build-cache --console=plain
./gradlew clean check --build-cache --console=plain
```

Hai lệnh ở trên **không phải phép A/B hoàn hảo** nếu warm-up, cache population và configuration state khác. Chúng giúp minh họa flags. Để so sánh đúng, phải định nghĩa trạng thái cache cold/hit cho từng scenario, tách lần populate cache khỏi lần đo và kiểm soát environment.

Với `--build-cache`, những tasks đủ điều kiện có thể báo `FROM-CACHE`. Nhưng chỉ vì có cache hit cũng không đảm bảo build nhanh hơn: tải/giải nén outputs qua remote network có thể tốn hơn chạy task rẻ tại máy.

### 7.6. Kịch bản F — Configuration Cache on/off

```bash
./gradlew help --configuration-cache --console=plain
./gradlew help --configuration-cache --console=plain
./gradlew help --no-configuration-cache --console=plain
```

Hai invocation đầu minh họa lưu và sử dụng configuration cache khi inputs không đổi và build logic tương thích. Lệnh thứ ba là đối chứng không dùng cache. `help` hữu ích để cô lập overhead configuration, nhưng không thể đại diện đầy đủ cho `check`.

Nếu lần đầu báo configuration-cache incompatibility, cần sửa build logic/plugin. **Không dùng `--configuration-cache-problems=warn` như quality gate lâu dài**, vì warning mode có thể che vi phạm và dẫn tới kết quả không đúng khi cache được dùng lại.

## 8. Dùng Gradle Profiler đo nhiều lượt

Gradle Profiler là công cụ độc lập. Cài hoặc build từ [repository chính thức](https://github.com/gradle/gradle-profiler) theo release/documentation tương thích, bảo đảm lệnh `gradle-profiler` có trong PATH. Nó **không** phải Gradle built-in task và không xuất hiện chỉ vì project dùng Java plugin.

### 8.1. File `performance.scenarios`

Trong root `gradle-benchmark-lab`, tạo:

```hocon
default-scenarios = ["clean_check", "no_op_check", "incremental_non_abi"]

clean_check {
    title = "Clean check"
    tasks = ["check"]
    cleanup-tasks = ["clean"]
}

no_op_check {
    title = "No-op check"
    tasks = ["check"]
}

incremental_non_abi {
    title = "Incremental non-ABI change"
    tasks = ["check"]
    apply-non-abi-change-to = "src/main/java/demo/Calculator.java"
}
```

Đây là cú pháp **HOCON của Gradle Profiler**, không phải một file Gradle Kotlin/Groovy script.

- `clean_check` gọi `clean` như cleanup trước workload `check`.
- `no_op_check` chạy `check` liên tiếp sau warm-up; nếu inputs/outputs ổn định, nhiều tasks có thể up-to-date.
- `incremental_non_abi` sử dụng mutator của Gradle Profiler sửa phần thân method Java giữa iterations. Vì source bị mutate, phải chạy trong **checkout/worktree thử nghiệm riêng**, không dùng repository có thay đổi chưa commit.

Khi dùng mutator, kiểm tra thông tin diff và test results; một mutator nhằm mô phỏng change type **không thay thế xác nhận behavior của ứng dụng**.

### 8.2. Chạy benchmark

Từ root project đã có Gradle Profiler CLI:

```bash
gradle-profiler --benchmark \
  --project-dir . \
  --scenario-file performance.scenarios \
  --warmups 5 \
  --iterations 15 \
  --csv-format long \
  --output-dir benchmark-results
```

PowerShell, viết một dòng để tránh khác biệt ký hiệu nối dòng:

```powershell
gradle-profiler --benchmark --project-dir . --scenario-file performance.scenarios --warmups 5 --iterations 15 --csv-format long --output-dir benchmark-results
```

Lưu ý:

- 5 warm-ups và 15 measured iterations là **cấu hình mẫu**, không phải khẳng định mọi project đủ số liệu thống kê.
- Gradle Profiler tạo CSV/JSON/HTML trong output directory, có thể dùng để lưu toàn bộ samples.
- Với scenario sử dụng mutator, Profiler có thể điều chỉnh source trong quá trình chạy, nên kiểm tra worktree sau benchmark.
- Không chạy song song với một benchmark khác nặng trên cùng machine.
- Gradle Profiler thường dùng một Gradle User Home riêng trong project cho phép thử; lưu rõ cơ chế cache và đường dẫn đang dùng để không vô tình so với setup khác.
- Nó có thể cần network tải Gradle distribution và dependencies lần đầu; tách thời gian setup khỏi measured samples.
- Một file HOCON và lệnh CLI này không tự đảm bảo QA pass. Quality gate vẫn phải chạy và kiểm tra outputs.

### 8.3. Phân biệt warm-daemon và cold-daemon benchmark

Để đo chi phí khởi động daemon, Gradle Profiler có tùy chọn:

```bash
gradle-profiler --benchmark --project-dir . --cold-daemon --warmups 2 --iterations 10 check
```

Đây là một scenario khác với warm-daemon default. Phải ghi tên riêng trong báo cáo, không cộng các mẫu cold-daemon với warm-daemon thành một median chung.

Nếu chỉ muốn đo **một lần đầu khởi động**, Profiler còn có `--single-shot`. Một sample đơn lẻ hữu ích để quan sát startup path, nhưng **không đủ** kết luận hồi quy hiệu năng có ý nghĩa thống kê.

### 8.4. So sánh Gradle versions

Nếu giả thuyết là nâng Gradle làm nhanh hơn, Profiler có thể chọn nhiều versions bằng `--gradle-version` hoặc cấu hình version theo scenario. Giữ JDK/OS/inputs nhất quán.

Đừng so version A trên Java 17 với version B trên Java 21 nếu mục tiêu chỉ là ảnh hưởng Gradle version. Nếu phải đổi JDK vì compatibility, ghi rõ đó là **combined migration**, không quy toàn bộ speedup cho Gradle.

### 8.5. Đọc kết quả Profiler

Output của Gradle Profiler có thể gồm:

```text
benchmark-results/
├── benchmark.html
├── benchmark.csv
└── benchmark.json
```

Khi báo cáo, lưu:

- Đủ tất cả samples, không chỉ fastest run.
- Median/mean và variation của từng scenario.
- Số iterations và warm-ups.
- Exit status/correctness của builds.
- Toolchain và baseline/candidate identifiers.
- Notes về cache, dependency downloads, CI noise.

**Không giả định filename luôn cố định trong mọi version/cấu hình**; hãy xem output thực tế của tool. CSV có thể ở định dạng `wide` hay `long` tùy flag.

## 9. Chọn thống kê phù hợp thay vì săn thời gian thấp nhất

### 9.1. Median

**Median** là giá trị trung tâm khi sắp xếp samples. Nó ít nhạy hơn mean với một số outlier. Vì độ trễ build thường có outliers do GC, tải máy hoặc network, median hữu ích làm số liệu chính.

Ví dụ dataset **tự tạo để học**, đơn vị milliseconds:

```text
Baseline A:
1200, 1300, 1250, 1400, 1350, 1230, 1280, 1310, 1260, 1290

Candidate B:
900, 950, 920, 990, 960, 910, 930, 940, 970, 980
```

Sau khi sắp xếp, baseline median = **1285 ms**, candidate median = **945 ms**. Phần giảm tương đối theo median:

```text
(1285 - 945) / 1285 × 100% ≈ 26.46%
```

Đây là **tốc độ cải thiện minh họa**, không phải kết quả Gradle đo thật.

### 9.2. P95 và tail latency

**P95** (95th percentile) là ngưỡng mà phần lớn samples nằm dưới hoặc bằng. Nó có ích khi đội muốn giảm những lần build chậm nhất ảnh hưởng trải nghiệm developer.

Với **nearest-rank method** và mỗi nhóm 10 samples, P95 nằm ở vị trí `ceil(0.95 × 10) = 10` trong dãy đã sắp xếp:

- Baseline P95 = **1400 ms**.
- Candidate P95 = **990 ms**.

**Cẩn thận:** Với chỉ 10 samples, P95 thực chất bằng maximum trong mẫu, rất không ổn định. Để đánh giá tail latency nghiêm túc, cần nhiều mẫu hơn và phải ghi rõ percentile method. P95 của một bộ 10 lượt không phải kết luận đáng tin về 95% hành vi dài hạn.

### 9.3. Mean, standard deviation và outliers

- **Mean** cho trung bình số học, nhưng có thể bị vài lần GC/network spike kéo lên.
- **Standard deviation** mô tả độ phân tán theo một quy ước; hữu ích nhưng không thay thế việc nhìn distribution.
- **IQR** (P75 − P25) tương đối bền với outliers.
- **P95** nhấn mạnh tail.
- **Min** thường chỉ cho biết lần may mắn nhất, không phải trải nghiệm điển hình.
- **Max** có thể hữu ích cho tìm outlier, nhưng rất nhạy với noise.

Không tự xóa slow samples chỉ vì chúng làm candidate B trông tệ. Nếu outlier do sự kiện ngoại lai có bằng chứng (CI host bị restart, dependency server 503), ghi lý do loại bỏ và chạy lại cả hai nhóm theo policy thống nhất.

### 9.4. Speedup ratio khác percentage reduction

Nếu A median = 20 s, B median = 15 s:

- **Time reduction** = (20−15)/20 = **25%**.
- **Speedup factor** = 20/15 = **1.33×**.

Không viết “nhanh hơn 33%” khi thực ra đang nói “thời gian giảm 25%” mà không giải thích phương pháp tính. Với các báo cáo team, dùng **time reduction (%)** cùng số giây rõ ràng.

## 10. Java 17 program tính median và P95 từ mẫu minh họa

Để tránh sai phép tính khi học, tạo một chương trình Java độc lập. Nó tính thống kê đơn giản từ **hai mảng dữ liệu minh họa cố định**, không tự lấy số liệu Gradle Profiler.

**File `tools/BenchmarkStats.java`:**

```java
import java.util.Arrays;
import java.util.Locale;

public final class BenchmarkStats {
    private BenchmarkStats() {
    }

    private static double median(long[] input) {
        long[] sorted = input.clone();
        Arrays.sort(sorted);

        int middle = sorted.length / 2;
        if (sorted.length % 2 == 1) {
            return sorted[middle];
        }
        return ((double) sorted[middle - 1] + sorted[middle]) / 2.0;
    }

    private static long percentile95(long[] input) {
        long[] sorted = input.clone();
        Arrays.sort(sorted);

        int rank = (int) Math.ceil(0.95 * sorted.length);
        return sorted[Math.max(0, rank - 1)];
    }

    public static void main(String[] args) {
        long[] baseline = {
                1200, 1300, 1250, 1400, 1350,
                1230, 1280, 1310, 1260, 1290
        };
        long[] candidate = {
                900, 950, 920, 990, 960,
                910, 930, 940, 970, 980
        };

        double a = median(baseline);
        double b = median(candidate);
        double reduction = 100.0 * (a - b) / a;

        System.out.printf(
                Locale.ROOT,
                "baseline median=%.1f ms, p95=%d ms%n",
                a, percentile95(baseline)
        );
        System.out.printf(
                Locale.ROOT,
                "candidate median=%.1f ms, p95=%d ms%n",
                b, percentile95(candidate)
        );
        System.out.printf(
                Locale.ROOT,
                "median time reduction=%.2f%%%n",
                reduction
        );
    }
}
```

Chạy từ root project với Java 17:

Linux/macOS:

```bash
mkdir -p tools/out
javac -d tools/out tools/BenchmarkStats.java
java -cp tools/out BenchmarkStats
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force tools\out | Out-Null
javac -d tools\out tools\BenchmarkStats.java
java -cp tools\out BenchmarkStats
```

**Stdout chính xác:**

```text
baseline median=1285.0 ms, p95=1400 ms
candidate median=945.0 ms, p95=990 ms
median time reduction=26.46%
```

Đây là code độc lập, không phụ thuộc Gradle runtime. Nếu dùng số liệu thực, cần đọc CSV mà Profiler sinh ra rồi tính toán với cùng phương pháp, giữ cả source samples và recording metadata.

### 10.1. Không dùng chương trình này làm bằng chứng thống kê tự động

Java helper không tự thực hiện benchmark, không thực hiện test hypothesis và không loại bỏ confounders. Nó minh họa phép tính trên các mẫu được cung cấp. Để ra quyết định production cần **số liệu thực**, sample count phù hợp, đối chứng A/B và correctness gates.

## 11. Chỉ số đo phải đi cùng điều kiện chất lượng

Một báo cáo tối ưu nên có **hai bảng song song**.

### 11.1. Performance metrics

| Chỉ số | Điều cần ghi |
| --- | --- |
| Total wall-clock time | Median, p95, n samples |
| Configuration time | Có/không Configuration Cache reuse |
| Task execution time | Các tasks thực thi và critical path |
| Compile time | Java/Kotlin compile tasks theo scenario |
| Test time | Số tests thực chạy và test duration |
| Cache hit rate | Local/remote, `FROM-CACHE` |
| Skipped/up-to-date | Số lượng và lý do |
| Remote cache cost | GET/PUT latency, transfer bytes |
| CPU/memory/GC | Resource pressure và possible regressions |
| Developer workflow | No-op/incremental/test-only |
| CI workflow | Clean/check/release trên runners tương đương |

### 11.2. Correctness metrics

| Guardrail | Không được suy giảm |
| --- | --- |
| Unit tests | Cùng tests, assertions và outcomes |
| Integration tests | Cùng environment và coverage |
| Static analysis | Checkstyle/PMD/SpotBugs/lint không bị bỏ |
| Source compilation | Không bỏ modules hoặc source sets |
| Public API/ABI | Không vô tình đổi contract |
| Runtime behavior | Output, exit code, side effects đúng |
| JAR/distribution content | Cùng files cần thiết, không bỏ resources |
| Dependency graph | Không âm thầm đổi versions/scopes |
| Security | Không cache secrets hoặc mở quyền ghi cache |
| Reproducibility | Từ clean checkout vẫn tạo artifact hợp lệ |
| Build cache correctness | Cache hit cho output đúng với inputs |
| Configuration cache correctness | Không ignore violations lâu dài |
| Test reports | Không làm mất test XML/reports cần cho CI |

Nếu một dòng guardrail FAIL, cần **REJECT** hoặc sửa lại thay đổi, cho dù median cải thiện rõ rệt.

## 12. Những cách “tăng tốc” sai hoặc gây đánh đổi tính đúng

### 12.1. Bỏ tests bằng `-x test`

```bash
./gradlew build -x test
```

Lệnh này có thể nhanh hơn `./gradlew build` vì không chạy test task. Nó là **một workload khác**, không được dùng để khẳng định tối ưu full build. Có thể hợp lý trong một developer workflow có kiểm thử riêng, nhưng release gate phải tiếp tục chạy đúng tests.

### 12.2. Tắt test task

```kotlin
tasks.test {
    enabled = false
}
```

Task báo `SKIPPED`, không kiểm thử. Nếu mục tiêu là cải thiện test execution time, phải tối ưu phân luồng tests, test fixtures, forks hoặc giảm I/O **mà vẫn giữ tests hợp lệ**, không vô hiệu hóa chúng.

### 12.3. Che thất bại test

```kotlin
tasks.test {
    ignoreFailures = true
}
```

Thiết lập này cho phép build tiếp tục dù tests thất bại. Có thể hữu ích trong một workflow riêng chỉ thu thập reports, nhưng **không phù hợp làm quality gate bắt buộc**. Không được gọi job xanh nếu test failures bị ẩn.

### 12.4. Buộc task UP-TO-DATE bằng điều kiện giả

Anti-pattern:

```kotlin
tasks.named("compileJava") {
    outputs.upToDateWhen { true }
}
```

Đoạn trên không có nghĩa Gradle đã chứng minh compiler outputs hợp lệ. Ép Gradle tin tasks up-to-date mà không dựa trên inputs/outputs đúng có thể làm build dùng artifacts cũ. Không dùng như giải pháp hiệu năng.

### 12.5. Custom task khai báo thiếu input

Ví dụ nguy hiểm: task đọc `config/templates/schema.json` nhưng chỉ khai báo `source.java` là input. Khi schema thay đổi, Gradle có thể không chạy task lại hoặc restore cached output sai.

Cách đúng là khai báo **toàn bộ inputs thực sự ảnh hưởng outputs**:

```kotlin
tasks.register("generateSchemaReport") {
    val schema = layout.projectDirectory.file("config/templates/schema.json")
    inputs.file(schema)
        .withPathSensitivity(PathSensitivity.RELATIVE)

    val report = layout.buildDirectory.file("reports/schema.txt")
    outputs.file(report)

    doLast {
        val text = schema.asFile.readText(Charsets.UTF_8)
        val out = report.get().asFile
        out.parentFile.mkdirs()
        out.writeText(text, Charsets.UTF_8)
    }
}
```

Đây là **mảnh task minh họa** yêu cầu file `config/templates/schema.json` tồn tại. Nó chưa phải một custom cacheable task type cho production và không nên dùng để tự tuyên bố Configuration Cache compatibility. Với task phức tạp, ưu tiên typed task class và `Property`/`RegularFileProperty` thay vì truy cập project model ở execution phase.

Kết luận: muốn incremental/cache đúng, Gradle phải biết **cái gì thực sự thay đổi kết quả**.

### 12.6. Đánh lừa benchmark bằng thay đổi target

```text
A: ./gradlew clean check
B: ./gradlew :app:compileJava
```

Hai lệnh phục vụ hai mục tiêu khác nhau. Phải so A và B với **cùng task set** hoặc đặt tên là hai separate developer workflows. Không tổng hợp vào một chỉ số “build time”.

### 12.7. Tắt lint/static checks

Lấy `spotbugsMain` hoặc `checkstyleMain` khỏi CI graph có thể tiết kiệm thời gian, nhưng mất quality coverage. Nếu muốn giảm thời gian, hãy tìm incremental analysis, lọc phạm vi phù hợp, cache chuẩn, chạy kiểm tra song song hoặc phân tầng workflows **mà release gate vẫn chạy đầy đủ**.

### 12.8. Sử dụng `--offline` làm kết quả tối ưu chung

```bash
./gradlew check --offline
```

Offline mode phù hợp khi tất cả dependencies có sẵn trong cache, giúp tránh network. Nhưng nếu clean checkout trên CI không có cache, lệnh có thể fail. Không gọi đây là tối ưu đảm bảo cho mọi môi trường. Cần test online clean state khi đánh giá release reproducibility.

## 13. Tối ưu hợp lệ: chọn đúng nguyên nhân gây chậm

### 13.1. Gradle/JDK/plugin updates

Nâng Gradle/JDK/plugin versions có thể mang lại cải tiến hiệu năng, bug fixes và support cache. Nhưng cũng có thể thay đổi behavior hoặc compatibility. Cần giữ baseline/candidate rõ và chạy tests, dependency verification, build logic/plugin compatibility cùng published artifact smoke tests.

**Không tự động bật một tính năng experimental trên production** chỉ vì benchmark nhỏ nhất cho kết quả nhanh; kiểm tra support matrix và regression risk.

### 13.2. Configuration Cache

`--configuration-cache` có thể giảm configuration overhead cho builds lặp. Nhưng build logic cần tương thích; nếu có problems, Gradle mặc định fail (và tài liệu khuyến nghị không lạm dụng `problems=warn`).

Correctness gate:

1. Chạy khi chưa có entry để build cache state.
2. Chạy lại xem “Configuration cache entry reused”.
3. Thay đổi một configuration input có liên quan.
4. Đảm bảo cache invalidates và task graph phản ánh thay đổi.
5. Đọc problems report và sửa code thay vì suppress warnings lâu dài.

### 13.3. Build Cache

`--build-cache` có thể reuse outputs khi inputs và task implementation phù hợp. Muốn đúng cần tasks deterministic, inputs/outputs khai báo đầy đủ, không cache secret-derived outputs và quản lý remote cache trust.

Một tăng cache-hit rate do bỏ khai báo input quan trọng là **sai**. Nó có thể làm build rất nhanh nhưng dùng stale artifacts.

### 13.4. Parallel execution

`--parallel` cho phép một số work chạy song song. Nó có thể giảm critical path nhưng tăng CPU/memory/disk contention và làm lộ race conditions trong tasks dùng shared mutable state.

Nên đo nhiều configurations, ví dụ:

```bash
./gradlew check --parallel --max-workers=4
./gradlew check --no-parallel --max-workers=4
```

Dùng cùng quality gate và môi trường; tách cold/no-op/incremental scenarios. Nếu outputs không ổn định hoặc test flakiness xuất hiện, phải sửa synchronization/task dependencies thay vì coi build pass nhanh một lần là thành công.

### 13.5. Heap/GC tuning

Tăng `org.gradle.jvmargs` có thể giảm GC pauses trong build cần memory; quá lớn có thể khiến OS swap, tăng memory footprint hoặc ảnh hưởng CI parallel jobs. Đo heap/GC bằng profile/JFR, không tự đặt `-Xmx8g` cho mọi runner.

### 13.6. Dependency resolution optimization

Giảm repository thừa, không resolve dependencies trong configuration phase, cố định versions, dùng version catalog/constraints hợp lý và tránh network calls trong plugin apply có thể giảm độ trễ. Nhưng đừng bỏ dependency verification, cắt repository bắt buộc hoặc ép version sai chỉ để resolve nhanh.

### 13.7. Test execution tối ưu đúng cách

- Tách test tasks theo unit/integration suites với quy tắc rõ.
- Cân nhắc `maxParallelForks` phù hợp CPU và memory.
- Tắt hoặc giảm log I/O quá mức nhưng vẫn giữ báo cáo bắt buộc.
- Sửa flaky tests/thời gian chờ không cần thiết.
- Dùng Test Fixtures/temporary directories ổn định.
- Cân nhắc test distribution hoặc impacted tests trong developer workflow, nhưng **full release gate vẫn có coverage**.

Một CI nhanh hơn nhưng luôn bỏ 30% integration tests không phải tối ưu cùng nghĩa.

## 14. Cache hit không chứng minh correctness

### 14.1. Build Cache

Task được đánh dấu `FROM-CACHE` nghĩa Gradle đã phục hồi output khớp theo cache key mà nó biết. Nếu custom task **thiếu declared inputs** hoặc remote cache bị poisoning, có thể có kết quả sai.

Chính sách cần:

- Declared inputs/outputs đủ.
- Deterministic task actions.
- Source path normalization khi có thể.
- Không cache secret outputs.
- Remote cache server read/write access kiểm soát.
- CI có cách chạy `--no-build-cache --rerun-tasks` để so kết quả khi cần.
- Nếu nghi cache lỗi, rebuild từ checkout tin cậy và so correctness trước khi bật lại shared cache.

### 14.2. Configuration Cache

Configuration Cache có thể skip configuration phase, nhưng những plugin giữ state hoặc truy cập model không đúng giai đoạn có thể gây errors/incorrect behavior. Đừng persist `--configuration-cache-problems=warn` để CI xanh; cần sửa build logic và kiểm tra invalidation khi inputs thay đổi.

### 14.3. Up-to-date checks

Up-to-date không phải “không làm gì tùy ý”. Nó dựa vào mô hình inputs/outputs/implementation Gradle biết. Một task dùng clock hoặc external service nhưng không khai báo có thể bị skip sai.

Nếu không thể mô hình hóa đầy đủ inputs (ví dụ kiểm tra dịch vụ thời gian thực), có thể không nên cache/up-to-date task đó. Tính đúng được ưu tiên hơn một cache hit giả tạo.

## 15. Kiểm tra artifact đầu ra, không chỉ exit code

Một build báo `BUILD SUCCESSFUL` có thể vẫn tạo artifact khác dự kiến vì cấu hình đã thay đổi. Correctness contract cần chọn những điều thực sự bất biến.

### 15.1. API/ABI và behavior

- Unit tests cho business logic và edge cases.
- Integration/contract tests qua public APIs.
- Compiler warnings và static analysis không bị bỏ.
- Kiểm thử classloading/runtime classpath phù hợp.
- Nếu thay compiler/toolchain, kiểm tra bytecode target/version.
- Nếu output phụ thuộc nguồn dữ liệu ngoài, kiểm tra fixtures và reproducibility.

### 15.2. JAR/distribution content

Sau khi chạy:

```bash
./gradlew clean build --no-build-cache --no-configuration-cache
jar tf build/libs/gradle-benchmark-lab-1.0.0.jar
```

Trong lab, tìm ít nhất:

```text
demo/Calculator.class
demo/Main.class
```

Nếu đổi build logic làm JAR mất `Main.class` hoặc resources bắt buộc, cải thiện build time không hợp lệ. Với release thực, nên dùng checksums, API compatibility checks, integration tests và artifact verification phù hợp.

**Byte-for-byte equality** hữu ích khi hai builds chỉ khác một optimization thuần nội bộ; nhưng có trường hợp metadata/timestamp/timestamps của toolchain làm hash khác mà behavior vẫn đúng. Cần xác định trước mức “same output” được yêu cầu: byte-identical, ABI-identical, behavior-equivalent hay distribution-equivalent. Không dùng checksum equality đơn độc thay tests.

### 15.3. Kiểm tra test reports

Gradle Java Test task thường tạo JUnit XML ở `build/test-results/test` và HTML report trong `build/reports/tests/test`. Một optimized pipeline không nên vô tình xóa/gạt report mà CI cần đọc.

Nếu `:test` báo `NO-SOURCE` hoặc chỉ chạy 0 tests trong project vốn có tests, quality gate phải coi đây là vấn đề cần điều tra.

## 16. So sánh thời gian trên CI và máy developer

### 16.1. Developer workloads

Developer thường quan tâm:

- No-op command lặp lại.
- Compile một module sau sửa non-ABI.
- IDE import/sync.
- Test một class/module.
- Gradle Daemon warm.
- Local Build Cache hit.

Nếu tối ưu chỉ làm clean CI nhanh hơn nhưng khiến no-op local chậm hơn, cần nêu trade-off rõ. Không lấy một metric duy nhất đại diện mọi người dùng.

### 16.2. CI workloads

CI thường quan tâm:

- Build từ checkout mới.
- Download dependency/cache availability.
- Tests và verification đầy đủ.
- Artifact publish/sign.
- Remote Build Cache GET/PUT cost.
- Parallel runners và CI queue time.
- Network/cold container setup.

Tổng “pipeline latency” có thể bao gồm thời gian chờ queue, provision runner, pull container image và upload artifacts. **Đó không hoàn toàn là Gradle execution time**. Khi tối ưu Gradle, cần tách phần Gradle đo được khỏi overhead của CI platform.

### 16.3. Hosted runners có độ biến động lớn

Hosted CI có thể chạy trên máy khác nhau, noisy neighbors, storage/network khác nhau. Nếu performance regression nhỏ, một lần run CI không đủ xác nhận. Với benchmark quan trọng, dùng fixed-size runners/dedicated hosts hoặc tăng samples, record hardware identifiers và so distribution thay vì chỉ một pipeline tổng.

### 16.4. Chi phí của remote Build Cache

Remote cache có thể giảm compile time nhưng tốn:

- Latency GET/PUT.
- Packing/unpacking artifacts.
- CPU hashing inputs.
- Network transfer.
- Storage và retention.
- Server maintenance/security.

Vì vậy metric tốt không chỉ là “cache hit % cao”, mà là **net wall-clock time tiết kiệm** và tính đúng. Với task rất nhỏ, cache lookup có thể đắt hơn tự chạy task.

## 17. Một mẫu báo cáo tối ưu có thể dùng trong PR

### 17.1. Bảng minh họa (không phải số liệu đo thật)

| Scenario | Baseline median | Candidate median | Time reduction | Correctness |
| --- | ---: | ---: | ---: | --- |
| Clean check | 54 s | 48 s | 11.1% | PASS |
| No-op check | 7.0 s | 4.5 s | 35.7% | PASS |
| Incremental non-ABI | 19 s | 17 s | 10.5% | PASS |
| Integration tests | 34 s | 34 s | 0.0% | PASS |

Đây là **số liệu giả định chỉ để minh họa cách báo cáo**. Báo cáo thật phải lưu sample CSV, n, warm-ups, p95/spread và machine metadata, và chỉ điền PASS khi có evidence.

### 17.2. Template kết luận chuẩn

```text
Hypothesis:
  Reduce configuration overhead without changing verification scope.

Baseline / candidate:
  A commit: [commit hash obtained from actual repository]
  B commit: [commit hash obtained from actual repository]

Workload:
  :app:check (warm daemon, no-op)
  :app:check (incremental non-ABI change)
  clean check (workspace clean)

Environment:
  Gradle Wrapper version, Gradle JVM, JDK toolchain,
  OS/CPU/RAM, workers, cache settings, dependency state

Sampling:
  warm-ups: [real count]
  measured iterations: [real count]
  samples: [actual CSV/JSON report path]

Results:
  median, p95, IQR for A and B
  relative time reduction
  uncertainty / notable outliers

Correctness:
  tests actually executed and passed
  artifact/output behavior checked
  lint/static analysis not bypassed
  no cache/configuration issues
  CI release gate passed

Decision:
  Accept / Reject / Repeat, with rationale
```

Dấu ngoặc trong template là các trường phải **điền bằng dữ liệu thật**, không phải output runtime hoặc giá trị đã được xác minh.

### 17.3. Thresholds: tránh quyết định dựa trên một con số

Một đội có thể đặt ví dụ:

- Candidate giảm median ít nhất 10%.
- P95 không tăng quá mức cho phép.
- Không phát sinh flaky tests mới.
- Không làm thay đổi release artifact contract.
- Không có failure của Config Cache, security scan hoặc dependency verification.
- Hiệu quả lặp được trên CI runner chuẩn.

Các ngưỡng cần dựa vào baseline variability, mức độ phức tạp và chi phí thay đổi. Đừng chấp nhận một tối ưu làm code khó bảo trì/khó debug chỉ vì nhanh hơn 1% trong khoảng nhiễu đo.

## 18. Chẩn đoán vì sao kết quả đo không ổn định

| Hiện tượng | Nguyên nhân thường gặp | Hướng điều tra |
| --- | --- | --- |
| Lần đầu chậm, sau đó nhanh | Daemon/JIT/dependency downloads | Tách warm-up khỏi measured iterations |
| No-op nhanh bất thường | Tasks UP-TO-DATE hoặc SKIPPED | Xem task outcomes và quality scope |
| No-op vẫn compile/test | Inputs thay đổi, outputs không ổn định | `--info`, inspect task input tracking |
| Candidate nhanh khi chạy sau A | OS cache/daemon warmed | Cân bằng A/B order |
| Candidate chậm trên CI nhưng nhanh local | Runner, JVM, network, cache policy khác | So môi trường, build scan |
| `FROM-CACHE` khi lẽ ra cần compile | Key collision/thiếu input hoặc cache state hợp lệ? | Xem task inputs, verify outputs |
| Cache hit % tăng nhưng total time tăng | Lookup/upload overhead hoặc task rẻ | Xem transfer/pack latency |
| `--parallel` giảm time nhưng tests flaky | Race/shared state | Sửa task dependencies, stop claim |
| Configuration Cache reuse không ổn định | Dynamic versions/environment inputs | Config Cache report và Providers |
| Candidate `check` có ít tasks hơn A | Verification bị bỏ hoặc module không included | So task graph/coverage |
| Test failures bị ẩn | `ignoreFailures=true` hoặc pipeline ignore exit code | Khôi phục failing gate |
| `NO-SOURCE` bất ngờ | Source path sai hoặc tests không được discover | Kiểm tra test reports và source sets |
| Benchmark p95 dao động mạnh | Quá ít samples / noise | Tăng iterations, theo dõi distribution |
| Cùng Gradle flags nhưng thời gian khác nhiều | JDK/Gradle plugin versions | Chốt toolchain và wrapper |
| Benchmark kéo dài đột biến | CI noisy neighbor, GC, disk pressure | Record CPU/RAM/GC; rerun |
| Warm measurement lại tải dependencies | Cache isolation/TTL/network | Log dependency resolution |
| Profiling làm build chậm | Instrumentation overhead | Tách profile run và benchmark run |
| Gradle Profiler làm thay đổi source | Mutator đang active | Dùng disposable worktree, kiểm tra diff |
| Tối ưu build làm JAR thiếu class | Đổi task graph/packaging sai | So artifact contents và tests |
| Dependency phiên bản thay đổi | Dynamic constraints/repositories | Lock/pin versions và inspect graph |
| `--configuration-cache-problems=warn` làm xanh | Problems bị chuyển thành warnings | Dùng fail mode, sửa incompatibility |
| Chỉ tối ưu `help`, không cải thiện build | Bottleneck không nằm ở configuration | Đo workload thực tế |

### 18.1. Quy trình debug từng bước

1. Xác nhận **cùng command/task targets** A/B.
2. Xác nhận build có **cùng correctness gate** và tests thực sự chạy.
3. Xác nhận environment, Gradle Wrapper/JVM, plugins và dependency versions.
4. Phân loại clean/no-op/incremental/cache-hit.
5. Dùng `--profile` hoặc Build Scan xem bottleneck.
6. Dùng Gradle Profiler benchmark nhiều lần, warm-ups nhất quán.
7. Thu samples và thống kê median/p95/variance.
8. Xem outcomes `UP-TO-DATE`, `FROM-CACHE`, `SKIPPED`.
9. Khi nghi stale output, chạy correctness build `--no-build-cache --rerun-tasks` trên checkout tin cậy.
10. Nếu correctness fail, rollback tối ưu; nếu kết quả không rõ ràng, tăng bằng chứng và chạy lại.

## 19. Các lệnh Gradle cần nhớ

| Lệnh | Mục đích |
| --- | --- |
| `./gradlew --version` | Chốt Gradle và Gradle JVM |
| `./gradlew clean check` | Verification từ workspace clean theo build hiện tại |
| `./gradlew check --profile` | Local HTML profile |
| `./gradlew check --info` | Diagnose task execution/up-to-date/cache |
| `./gradlew check --scan` | Build Scan khi chính sách cho phép |
| `./gradlew check --build-cache` | Bật Build Cache |
| `./gradlew check --no-build-cache` | Không dùng Build Cache |
| `./gradlew help --configuration-cache` | Thử Configuration Cache |
| `./gradlew help --no-configuration-cache` | Đối chứng config không reuse |
| `./gradlew check --parallel` | Thử task parallelism |
| `./gradlew check --max-workers=4` | Cố định số workers |
| `./gradlew check --dry-run` | Chỉ xem task graph, không kiểm thử thật |
| `./gradlew check --no-build-cache --rerun-tasks` | Ép task thực thi lại để kiểm chứng outputs |
| `./gradlew tasks --all` | Kiểm tra targets/verification tasks tồn tại |
| `gradle-profiler --benchmark ...` | Benchmark nhiều lượt bằng Profiler |
| `gradle-profiler --profile jfr ...` | CPU/GC profiling qua JFR (khi hỗ trợ) |

Dùng chính xác command tương ứng với dự án. Trong multi-project build, cần cân nhắc `:app:check`, `:library:check` hoặc root `check` theo policy; task scope khác nhau không thể so sánh trực tiếp.

## 20. Checklist ra quyết định trước khi merge

1. Đã nêu rõ bottleneck và giả thuyết chưa?
2. Có baseline và candidate commits riêng chưa?
3. Có cùng task graph/verification scope chưa?
4. Gradle Wrapper/plugin versions có được chốt chưa?
5. Java toolchain và Gradle daemon JVM có được ghi rõ chưa?
6. Cache flags và tình trạng cache của hai bên có tương đương không?
7. Clean, no-op và incremental scenarios có được tách riêng không?
8. Có warm-up và đủ measured iterations không?
9. Có lưu raw CSV/JSON/logs đã redact không?
10. Có báo median và spread, không chỉ fastest run không?
11. Có xác định p95 method và cỡ mẫu đủ cho tail chưa?
12. Có loại trừ noise/outliers theo quy tắc minh bạch không?
13. Có chứng cứ tests thực sự đã chạy và pass không?
14. Có kiểm tra `NO-SOURCE` hoặc `SKIPPED` bất ngờ không?
15. Static analysis/security/dependency checks có còn không?
16. Public API, runtime behavior và artifact content có đúng không?
17. Custom tasks có khai báo tất cả inputs/outputs không?
18. Cache hits có phục hồi outputs đúng không?
19. Configuration Cache có violations/warnings bị bỏ qua không?
20. Remote Build Cache có quyền ghi và provenance được bảo vệ không?
21. Candidate có tạo flakiness/race khi parallel không?
22. Developer workflows có cải thiện hoặc ít nhất không suy giảm quá mức không?
23. CI performance có kết quả lặp lại trên runner chuẩn không?
24. Chi phí maintenance/cấu hình có tương xứng gain không?
25. Có rollback/monitor plan khi production regress không?

**Quyết định:** Chỉ chấp nhận optimization nếu tất cả correctness gates trọng yếu đều PASS và performance gain có bằng chứng vượt noise phù hợp với mục tiêu.

## 21. Bài tập thực hành

**Bài tập A — nhận diện so sánh sai.** Một kỹ sư so `clean check` với `assemble` rồi báo giảm 40%. Hãy chỉ ra các sai khác về workload và thiết kế lại phép thử.

**Bài tập B — tạo lab.** Tạo `gradle-benchmark-lab` đầy đủ theo mục 6, chạy `clean check` và `run`; xác nhận stdout `checksum=333833500`.

**Bài tập C — test correctness.** Đổi một phép toán trong `Calculator.sumOfSquares` làm hàm sai với `n=2`. Chạy `test` và giải thích vì sao tối ưu phải bị reject dù runtime nhanh hơn.

**Bài tập D — profile.** Chạy `./gradlew check --profile` và tìm HTML report. Những phần nào thuộc configuration, phần nào thuộc task execution?

**Bài tập E — no-op.** Chạy `check` hai lần liên tiếp với cùng inputs, giải thích `UP-TO-DATE` và vì sao lần đó không kiểm chứng toàn bộ tests đã được chạy lại.

**Bài tập F — Build Cache.** Bật `--build-cache`, phân biệt `FROM-CACHE` với `UP-TO-DATE`. Vì sao hai tình huống có performance khác nhau?

**Bài tập G — Config Cache.** Chạy `help --configuration-cache` hai lần. Nếu plugin báo problem, tại sao không nên giữ `problems=warn` vĩnh viễn?

**Bài tập H — Profiler.** Tạo `performance.scenarios` và chạy `gradle-profiler --benchmark` với warm-ups/iterations. Lưu CSV và giải thích ý nghĩa mỗi scenario.

**Bài tập I — non-ABI vs ABI.** Thử thay thân method và thay public signature trong hai branches riêng. Tại sao lượng recompilation khác nhau?

**Bài tập J — thống kê.** Chạy `tools/BenchmarkStats.java`, xác nhận median 1285 và 945. Tính time reduction 26.46% và nêu vì sao P95 từ 10 samples còn yếu.

**Bài tập K — đổi thứ tự.** Giả sử B luôn chạy sau A trên cùng runner. Thiết kế lịch A→B→B→A để giảm order bias; liệt kê noise còn có thể tồn tại.

**Bài tập L — tối ưu task graph.** Một candidate làm `check` không chạy `test`. Vì sao không được so median với baseline?

**Bài tập M — thiếu declared input.** Custom generator đọc JSON schema nhưng chỉ khai báo Java sources làm input. Dự đoán behavior khi schema đổi và sửa task model.

**Bài tập N — parallel flakiness.** Bật `--parallel` được median tốt hơn nhưng integration tests thỉnh thoảng fail. Có nên merge không? Nêu cách sửa race và kiểm chứng.

**Bài tập O — remote cache.** Tỷ lệ `FROM-CACHE` cao nhưng build chậm hơn do network. Nêu metrics cần xem và cách so sánh đúng.

**Bài tập P — artifact equivalence.** So manifest/JAR entries/API/behavior và checksums của baseline vs candidate; xác định tiêu chí nào thực sự bắt buộc.

**Bài tập Q — CI dashboard.** Thiết kế biểu đồ median và p95 cho clean/no-op/incremental, ghi Gradle/JDK/commit/caches, phát hiện regressions có guardrails.

**Bài tập R — release gate.** Một optimization khiến test failures bị ignore nhưng pipeline xanh. Hãy sửa cấu hình và giải thích vì sao cần giữ failure signal.

### Câu hỏi tự kiểm tra

1. Vì sao một lần chạy nhanh không đủ kết luận build đã được tối ưu?
2. `clean` có xóa Daemon/OS caches không?
3. Cold daemon khác clean workspace ở đâu?
4. No-op khác incremental change như thế nào?
5. Non-ABI change có thể tránh downstream recompilation nhờ cơ chế nào?
6. Vì sao dùng cùng task targets khi so A/B?
7. Warm-up được dùng để giảm loại nhiễu gì?
8. Tại sao chạy toàn bộ A trước rồi toàn bộ B có thể thiên lệch?
9. Median có lợi gì khi có outliers?
10. P95 có ý nghĩa gì và tại sao 10 samples thường chưa đủ?
11. Time reduction (%) khác speedup factor ở đâu?
12. `--profile` của Gradle khác Gradle Profiler như thế nào?
13. Build Scan có thể cung cấp thông tin gì về critical path?
14. Vì sao cần phê duyệt khi upload Build Scan của dự án nhạy cảm?
15. Gradle Profiler dùng `performance.scenarios` định nghĩa những gì?
16. `cleanup-tasks` trong scenario không đồng nghĩa xóa dependency cache vì sao?
17. `--cold-daemon` đo yếu tố khác default warm daemon như thế nào?
18. `--build-cache` và `--configuration-cache` tối ưu hai giai đoạn khác nhau ra sao?
19. `FROM-CACHE` có chứng minh task output đúng khi inputs khai báo thiếu không?
20. Vì sao `-x test` không được xem là cải thiện full verification?
21. `ignoreFailures=true` gây nguy cơ gì cho release quality gate?
22. Vì sao `--dry-run` không dùng để xác nhận correctness?
23. Vì sao test task `NO-SOURCE` bất ngờ phải được điều tra?
24. Vì sao một build nhanh hơn nhưng JAR mất classes là regression?
25. `--rerun-tasks --no-build-cache` giúp kiểm tra điều gì?
26. Bật parallel có thể tạo race condition nào?
27. Vì sao Configuration Cache warning mode không nên là policy lâu dài?
28. Tại sao cache hit rate cao chưa chắc cải thiện elapsed time?
29. CI queue time có phải Gradle execution time không?
30. Khi một phép đo nằm trong noise, quyết định hợp lý là gì?

## 22. Tài liệu chính thức

- [Gradle — Improve the Performance of Gradle Builds](https://docs.gradle.org/current/userguide/performance.html)
- [Gradle — Best Practices for Performance](https://docs.gradle.org/current/userguide/best_practices_performance.html)
- [Gradle — Build Cache Performance](https://docs.gradle.org/current/userguide/build_cache_performance.html)
- [Gradle — Inspect Builds: Build Scan, Profile Report](https://docs.gradle.org/current/userguide/inspect.html)
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Enabling Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_enabling.html)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle Profiler — GitHub](https://github.com/gradle/gradle-profiler)

**Ghi nhớ:** Đánh giá tối ưu Gradle cần **cùng workload + nhiều lượt đo + thống kê rõ + các correctness gates không đổi**. Tách clean/no-op/incremental/cold/cache-hit; dùng `--profile` để chẩn đoán và Gradle Profiler để thu mẫu; báo median, tail và độ biến động chứ không chọn thời gian thấp nhất. Không “tăng tốc” bằng cách bỏ tests, giấu lỗi, khai báo thiếu inputs hoặc dùng stale cache. Build chỉ thật sự tốt hơn khi **nhanh hơn một cách lặp lại được và vẫn tạo đúng sản phẩm**.