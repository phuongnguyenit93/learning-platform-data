# Giữ môi trường, dữ liệu và cách đo có thể tái lập khi kiểm thử và tối ưu Java 11+

## 1. Vì sao cần khả năng tái lập?

Một thay đổi khiến chương trình chạy nhanh hơn trên máy của lập trình viên nhưng chậm đi trong CI hoặc trên production **không tự động là lỗi của JVM**. Thường có những biến chưa được kiểm soát: bộ dữ liệu, phiên bản JDK, cache, CPU, concurrency, GC, compiler, timezone, charset hoặc chính quy trình đo.

**Tái lập một phép thử** là để người khác có thể biết chính xác **cái gì được thử**, **điều kiện nào được dùng**, **dữ liệu nào được xử lý**, **metric nào được báo cáo**, **phép tính nào dẫn đến kết luận** và **sai số của phép đo**.

Phân biệt:

- **Functional determinism**: cùng input và contract, chương trình trả output tương đương hoặc trùng byte-for-byte theo yêu cầu.
- **Repeatability**: chạy lại trong cùng cấu hình cho kết quả nhất quán ở mức phù hợp; với hiệu năng đây thường là một **phân phối**, không phải một số cố định.
- **Reproducibility**: người khác dựng lại môi trường, dữ liệu, protocol và thu được kết quả có thể kiểm chứng.
- **Comparability A/B**: hai phiên bản khác nhau ở **biến chủ động đang nghiên cứu**, không đồng thời đổi JDK, dataset, collector và workload rồi quy mọi chênh lệch cho thuật toán.
- **Auditability**: có commit, build logs, fixture SHA-256, lệnh thực thi, raw results và điều kiện loại mẫu để kết luận có thể được kiểm tra.

Bài thuộc nhóm **Kiểm thử và tối ưu**, áp dụng cho source/API baseline **Java 11** và JDK hiện hành. Các ví dụ độc lập đã được biên dịch bằng `javac --release 11`. **Chỉ dùng kiến thức vẫn có giá trị ngày nay**: UTF-8 explicit, injected `Clock`, seeded `Random`, hash data, JMH, đo bằng `nanoTime` đúng nghĩa, kiểm soát JVM/GC và thống kê nhiều lần chạy.

> Yêu cầu output chức năng chính xác từng byte là hợp lý với fixture cố định. Yêu cầu mọi lần chạy benchmark trả đúng **292.200 ns** thì không hợp lý: scheduler, cache, frequency, JIT, GC và noise khác nhau.

## 2. Xác định điều cần chứng minh trước khi chạy

| Câu hỏi | Cách kiểm chứng phù hợp | Không được suy ra |
| --- | --- | --- |
| Parser B có cùng kết quả với A? | Unit/property tests, golden fixtures, checksum | B chắc nhanh hơn |
| Một phép tính có đúng ở mốc thời gian hết hạn? | `Clock.fixed`, kiểm tra boundary | Latency production đã tốt |
| Một method Java chạy nhanh hơn? | JMH: warm-up, forks, nhiều iterations | HTTP p99 cũng nhanh hơn |
| API end-to-end có đạt SLO? | Load test thực tế, request latency/errors, tài nguyên | Một microbenchmark đủ chứng minh |
| GC có tạo spikes không? | JFR/GC logs đối chiếu p99 timeline | GC là nguyên nhân duy nhất |
| Cùng build có thể tạo lại đúng artifact? | Reproducible-build tooling, digest | Timing các runtime giống nhau |
| Candidate cải thiện 10%? | Baseline A/B, phân phối nhiều trials, variance | Một run 10% đủ kết luận |

Trước khi đo, viết **hypothesis** và acceptance rule. Ví dụ: “Với 100.000 JSON records và cùng input hash, candidate B giảm median parse time ít nhất 10% qua ba JVM forks, không tăng RSS trên 15% và không đổi output.” Con số này là **một mục tiêu giả định**, không phải benchmark thực tế.

Bỏ bước correctness để “đo nhanh trước” nguy hiểm: B có thể nhanh hơn do bỏ validation, thay đổi thứ tự, truncation hoặc không thực sự xử lý cùng số records.

## 3. Ma trận các biến cần ghi

| Lớp | Giá trị phải biết | Rủi ro khi khác |
| --- | --- | --- |
| Source | Git commit, dirty tree, generated code | Thực chất đang chạy code khác |
| JDK | vendor, version/update/build, JVM implementation | JIT, GC, stdlib, tzdb khác |
| Build | Maven/Gradle wrapper, plugin, dependency lock | Dependency trôi theo ngày |
| OS/CPU | OS/kernel, CPU architecture/model, core count | Timer, CPU và scheduler khác |
| Container | Image digest, cgroup CPU/RAM quota, throttling | CPU/RSS và GC behavior khác |
| JVM | `-Xms`, `-Xmx`, GC, `-XX`, `-D` options | Allocation/GC/latency khác |
| Input | Seed, dataset version/hash, schema, distribution | Workload không còn tương đương |
| Locale/TZ | Locale, `ZoneId`, charset, tzdb | Ngày, dấu thập phân, sort khác |
| File system | Working directory, line ending, page cache | Data và I/O latency khác |
| Concurrency | Thread count, task order, queue/backpressure | Interleavings và contention khác |
| Test protocol | Warm-up, repetitions, forks, run order | JIT state và noise bias |
| Instrumentation | Logging, JFR, profiler, tracing agent | Overhead khác |
| Metrics | Sample count, histogram/quantile algorithm | p99 không cùng định nghĩa |

Không phải tất cả cần **giống nhau tuyệt đối** khi chính biến cần nghiên cứu là JDK hoặc collector. Hãy **ghi rõ biến chủ động**, giữ các biến còn lại tương đương đến mức hợp lý và mô tả điều kiện nào không kiểm soát được.

## 4. Lưu một manifest cho từng experiment

Một bản mô tả có cấu trúc giúp người khác dựng lại phép thử:

```yaml
experiment_id: parser-comparison-2026-11-07
question: "B có giảm p99 parse latency của A không?"
source:
  git_commit: "<hash thực tế>"
  working_tree: clean
build:
  source_release: 11
  toolchain: "<vendor JDK version/build>"
  dependency_lock: "<file hoặc digest thực tế>"
runtime:
  java_version: "<actual version>"
  image_digest: "<OCI digest nếu chạy container>"
  jvm_args: ["-Xms512m", "-Xmx2g", "-XX:+UseG1GC"]
host:
  os_arch: "<actual OS/architecture>"
  cpu_limit: "<actual CPU quota>"
  memory_limit: "<actual limit>"
data:
  schema_version: 1
  seed: 20261107
  records: 100000
  charset: UTF-8
  newline: LF
  sha256: "<hash tính sau khi sinh fixture>"
measurement:
  mode: "JMH / end-to-end (chọn một, không nhập nhằng)"
  warmup: "<duration và số iterations>"
  forks: "<số JVM processes>"
  trials: "<số lần đo độc lập>"
  metric: "<p99, throughput, avg ns/op...>"
  rule: "<acceptance đã định trước>"
artifacts:
  results: "<raw results path>"
  gc_logs: "<path nếu có>"
  notes: "<known sources of noise>"
```

Đây là **mẫu YAML để viết báo cáo**, không phải file được Java tự động đọc. Các dấu `<...>` phải được thay bằng giá trị **đã thực sự chạy**. **Không** lưu secrets (password, access token, API key) vào manifest hoặc file public.

Tối thiểu phải lưu: source commit, JDK/build, VM flags, dataset hash/seed, exact command, protocol, raw results, thời gian đo, errors/timeouts và assumptions.

## 5. Khóa JDK/toolchain và dependency đúng

### 5.1. `--release 11` cần thiết khi Java 11 là baseline

```bash
javac --release 11 Example.java
```

Theo Oracle `javac`, `--release 11` ràng buộc language rules, class file target và **public JDK API surface** của Java 11. Chỉ dùng `-source 11 -target 11` với compiler JDK mới **không đủ bảo đảm** code không gọi một API chỉ có sau Java 11.

**Không nhầm compile target với runtime:** class biên dịch `--release 11` vẫn có thể chạy trên JDK 17/21/25/27. Garbage collector, JIT, charset default, CPU detection và runtime implementations do **JDK thực tế đang chạy** quyết định.

### 5.2. “Java 11” chưa đủ xác định môi trường

Hai bản JDK 11 ở hai vendor/update releases có thể khác backported fixes, TLS, time zone data, native libraries hoặc ergonomics. Ghi vendor, feature/update/build, architecture và JVM implementation; khi benchmark so thuật toán A/B, cố định JDK thực sự chạy.

### 5.3. Build reproducibility khác test reproducibility

- Pin dependencies, plugin versions và toolchain.
- Dùng Maven/Gradle Wrapper và versioned configuration.
- Dùng dependency locking/verification nếu công cụ hỗ trợ.
- Ghi source digest, artifact digest; tránh floating `latest`.
- Không đồng nhất một image tag như `latest` với một **immutable OCI digest**.
- Với bit-for-bit JAR, còn phải kiểm file timestamps, entry order, generated UUID, timestamps của build và metadata khác.

Một build bit-for-bit bằng nhau **không bảo đảm hiệu năng giống nhau** trên hai CPU hosts.

## 6. Tạo fixture tái lập từ seed

`java.util.Random` trong Java 11 là pseudo-random generator có thuật toán được đặc tả. Theo Javadoc, hai instances khởi tạo cùng seed và được gọi **cùng thứ tự method calls** tạo cùng sequence.

```java
Random r = new Random(20261107L);
int value = r.nextInt(1000);
```

Điều đó không có nghĩa:

- Seed cố định điều khiển được thứ tự scheduling của nhiều threads.
- Mọi thư viện RNG tự chế hoặc version đều có cùng thuật toán.
- `ThreadLocalRandom` có thể set seed cố định như `Random`.
- `SecureRandom` nên dùng fixed seed cho token/key bảo mật.
- Dữ liệu **được tạo đúng với production** chỉ vì có hash và seed.

Đối với fixture, ghi thêm thuật toán tạo, call sequence, generator code version, size, schema, phân phối và **SHA-256 bytes**.

### Cần kiểm soát phân phối dữ liệu

Hai datasets đều 100.000 rows nhưng có thể rất khác:

- 80% small records vs uniform sizes.
- Duplicate keys nhiều vs unique keys.
- Null percentage.
- Sorted keys vs random order.
- Cache hit rate và locality.
- Unicode/non-ASCII và abnormal values.
- Payload compression ratio.

Một parser hay cache có thể đổi hạng performance khi đổi phân phối. Vì vậy “cùng record count” chưa đủ để so benchmark.

## 7. Demo Java 11 hoàn chỉnh: fixture UTF-8 + seed + SHA-256

Program dưới đây **không cần mạng và thư viện ngoài**, tạo tám CSV records với seed cố định, file temp riêng, SHA-256, Unicode-safe UTF-8, số với `Locale.ROOT` và timestamp UTC.

**Tên file:** `ReproFixtureDemo.java`.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.Locale;
import java.util.Random;

public final class ReproFixtureDemo {
    private static byte[] fixture(long seed) {
        Random random = new Random(seed);
        StringBuilder csv = new StringBuilder("id,value\n");

        for (int id = 1; id <= 8; id++) {
            csv.append(id).append(',')
               .append(random.nextInt(1000)).append('\n');
        }
        return csv.toString().getBytes(StandardCharsets.UTF_8);
    }

    private static String sha256(byte[] bytes) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(bytes);

        char[] digits = "0123456789abcdef".toCharArray();
        char[] hex = new char[hash.length * 2];

        for (int i = 0; i < hash.length; i++) {
            int value = hash[i] & 0xff;
            hex[i * 2] = digits[value >>> 4];
            hex[i * 2 + 1] = digits[value & 15];
        }
        return new String(hex);
    }

    public static void main(String[] args) throws Exception {
        long seed = 20261107L;
        byte[] first = fixture(seed);
        byte[] again = fixture(seed);
        byte[] changed = fixture(seed + 1);

        Path directory =
                Files.createTempDirectory("repro-fixture-");
        Path file = directory.resolve("fixture.csv");

        try {
            Files.write(file, first, StandardOpenOption.CREATE_NEW);

            System.out.println("sameSeedEqual=" +
                    Arrays.equals(first, again));
            System.out.println("differentSeedDifferent=" +
                    !Arrays.equals(first, changed));
            System.out.println("recordCount=" +
                    (Files.readAllLines(file,
                            StandardCharsets.UTF_8).size() - 1));
            System.out.println("readbackIdentical=" +
                    Arrays.equals(first, Files.readAllBytes(file)));
            System.out.println("fixtureSha256=" + sha256(first));
            System.out.println("numeric=" +
                    String.format(Locale.ROOT, "%.2f", 12.5));

            Instant instant =
                    Instant.parse("2026-11-07T10:15:30Z");
            System.out.println("timestamp=" +
                    DateTimeFormatter.ISO_INSTANT
                            .withZone(ZoneOffset.UTC)
                            .format(instant));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 ReproFixtureDemo.java
java ReproFixtureDemo
```

**Stdout đã kiểm chứng bằng JDK 24.0.2, compile `--release 11`:**

```text
sameSeedEqual=true
differentSeedDifferent=true
recordCount=8
readbackIdentical=true
fixtureSha256=4adc1819d08de95e2c733b9a49dd64e6cfc6b27afdeabe33367ea1b1e9beb33b
numeric=12.50
timestamp=2026-11-07T10:15:30Z
```

Đã chạy lại với hai môi trường JVM:

```text
Run A: -Duser.language=fr -Duser.country=FR -Duser.timezone=Asia/Tokyo
Run B: -Duser.language=vi -Duser.country=VN -Duser.timezone=UTC
```

**Hai lần có toàn bộ output giống nhau**, vì file format, seed, UTC và Locale được chỉ định tường minh.

### Vì sao phải chọn LF tường minh?

Nếu dùng `System.lineSeparator()`, CSV có thể viết `\r\n` trên Windows, `\n` trên Unix. Data nhìn giống nhau nhưng hash khác. Một fixture dùng để kiểm checksum phải quy định line ending, encoding, BOM/Unicode normalization và dấu newline cuối file.

### Vì sao không dùng default charset?

`new String(bytes)` và `text.getBytes()` dùng default charset. Ở Java 11, default charset có thể phụ thuộc môi trường. Theo **JEP 400**, từ JDK 18, default charset cho Java SE APIs được chuẩn hóa UTF-8 (có compatibility behavior được tài liệu mô tả). Dùng `StandardCharsets.UTF_8` explicit giúp kiểm soát dù chạy target Java 11 hay bản JDK mới.

**Lưu ý nuance:** `Files.readString(Path)` và `Files.writeString(Path,...)` được bổ sung trong Java 11 **đã mặc định UTF-8 theo contract**. Không suy rộng rằng tất cả Java 11 file APIs đều dùng default OS charset.

### Hash là kiểm bytes, không kiểm business correctness

SHA-256 phát hiện thay đổi byte-level (thứ tự records, whitespace, charset, newline...). Nhưng một dataset **sai ngay từ đầu** vẫn có SHA-256 ổn định. Phải xác nhận schema và expected answers riêng.

## 8. Thời gian: inject `Clock` để tránh tests phụ thuộc đồng hồ thật

### 8.1. Test thời gian không nên chờ thực

Một test expiry có logic:

```java
boolean expired = !Instant.now().isBefore(deadline);
```

có thể pass/fail tại boundary vì OS scheduling, CI delays hoặc lúc test chạy. Trong production, việc đọc clock thật có thể hợp lệ, nhưng trong test nên inject `java.time.Clock`:

```java
static boolean expired(Instant deadline, Clock clock) {
    return !clock.instant().isBefore(deadline);
}
```

Đây là snippet, imports `java.time.Clock` và `java.time.Instant`.

### 8.2. Ví dụ độc lập `Clock.fixed`

**Tên file:** `FixedClockDemo.java`.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public final class FixedClockDemo {
    public static boolean expired(
            Instant deadline, Clock clock) {
        return !clock.instant().isBefore(deadline);
    }

    public static void main(String[] args) {
        Instant deadline =
                Instant.parse("2026-11-07T10:15:30Z");

        Clock exact = Clock.fixed(deadline, ZoneOffset.UTC);
        Clock before =
                Clock.offset(exact, Duration.ofSeconds(-1));
        Clock after =
                Clock.offset(exact, Duration.ofSeconds(1));

        System.out.println(
                "beforeExpired=" + expired(deadline, before));
        System.out.println(
                "atBoundaryExpired=" + expired(deadline, exact));
        System.out.println(
                "afterExpired=" + expired(deadline, after));
        System.out.println(
                "fixedInstant=" + exact.instant());
    }
}
```

Chạy:

```bash
javac --release 11 FixedClockDemo.java
java FixedClockDemo
```

**Stdout đã được kiểm chứng:**

```text
beforeExpired=false
atBoundaryExpired=true
afterExpired=true
fixedInstant=2026-11-07T10:15:30Z
```

Đoạn này kiểm rõ **boundary rule**: hết hạn khi `now >= deadline`. Nếu ứng dụng quy định khác, đổi assertion theo contract. Không cần `Thread.sleep` hay đặt đồng hồ hệ điều hành.

**Không** thay `Clock.fixed` bằng cách đổi `Locale.setDefault`/`TimeZone.setDefault` toàn cục giữa nhiều parallel tests: global state dễ gây cross-test interference, và các đối tượng formatter/cache có thể đã được tạo từ trước.

## 9. Locale và timezone: chúng có thể là input thực sự

### 9.1. Decimal separators

```java
String s = String.format(Locale.ROOT, "%.2f", 12.5);
// "12.50"
```

Nếu output là một protocol/CSV machine-readable, hãy quy định locale explicit. Nếu là UI tiền tệ cho người dùng, locale của người dùng là input nghiệp vụ: test những locales cần hỗ trợ thay vì ép mọi người dùng về `Locale.ROOT`.

### 9.2. Timezone và tzdb

Đối với timestamp bất biến, lưu `Instant`/ISO-8601 UTC. Đối với lịch hẹn theo giờ địa phương, giữ `ZoneId` có tên và test DST/changes của timezone database. Đừng gộp ý nghĩa thời gian “10:00 sáng địa phương” với “10:00Z”.

Trên hai JDK versions khác nhau, tzdb/CLDR có thể đổi quy tắc lịch/format. `@since` của `java.time` không đồng nghĩa mọi quy tắc thời gian giống nhau mãi.

### 9.3. Charset và console không giống file

Console có encoding/terminal behavior riêng. Để kiểm fixture, hash **bytes file** trực tiếp, không copy/paste output console rồi coi là bằng chứng byte equality. Với JSON/CSV cố định, dùng explicit UTF-8 và canonical formatting rules.

## 10. File paths và fixtures không nên phụ thuộc working directory

Code:

```java
Path file = Path.of("test-data", "input.csv");
```

là relative path; nội dung thực được tìm theo current working directory, có thể khác giữa IDE, Maven, container và CI.

Đề xuất:

- Resource fixture được versioned cùng source hoặc có checksum.
- Mỗi test tự tạo thư mục tạm riêng và dọn bằng `finally`/JUnit temporary directory.
- Không ghi đè file production hay một temp file chung có thể bị race.
- Nếu test cần giữ artifact khi fail, lưu ở output directory có TTL/quota.
- Dùng `try-with-resources` với streams/channels để tránh test sau bị ảnh hưởng bởi file handle.
- Không giả định case-sensitivity, Unicode normalization và path separators giống nhau trên mọi OS.
- File system benchmark phải nói rõ cold-cache hay warm-cache, local disk hay network storage.

`CREATE_NEW` ở demo tránh vô tình ghi đè một file sẵn có. `Files.readAllLines(...UTF_8)` giữ input encoding rõ ràng, nhưng với dataset lớn nên dùng streaming thay vì load toàn bộ file.

## 11. Ví dụ độc lập ghi metadata của JVM đang chạy

Mục đích là ghi **môi trường thực tế**, không hard-code giả định “máy này luôn có tám processors”. Dùng APIs Java 11:

**Tên file:** `EnvAuditDemo.java`.

```java
import java.lang.management.ManagementFactory;
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public final class EnvAuditDemo {
    public static void main(String[] args) {
        System.out.println(
                "java.version=" +
                System.getProperty("java.version"));
        System.out.println(
                "java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println(
                "os.name=" + System.getProperty("os.name"));
        System.out.println(
                "os.arch=" + System.getProperty("os.arch"));
        System.out.println(
                "processors=" +
                Runtime.getRuntime().availableProcessors());
        System.out.println(
                "charset=" + Charset.defaultCharset().name());
        System.out.println(
                "locale=" + Locale.getDefault().toLanguageTag());
        System.out.println(
                "zone=" + ZoneId.systemDefault().getId());
        System.out.println(
                "vmArgs=" + ManagementFactory
                        .getRuntimeMXBean()
                        .getInputArguments());
    }
}
```

Compile:

```bash
javac --release 11 EnvAuditDemo.java
```

Chạy trên **PowerShell**, quote JVM options để shell truyền nguyên argument:

```powershell
java '-Duser.language=fr' '-Duser.country=FR' '-Duser.timezone=Asia/Tokyo' '-Dfile.encoding=UTF-8' '-XX:ActiveProcessorCount=2' EnvAuditDemo
```

**Một kết quả đã kiểm chứng trên Azul JDK 24.0.2 / Windows 11:**

```text
java.version=24.0.2
java.vendor=Azul Systems, Inc.
os.name=Windows 11
os.arch=amd64
processors=2
charset=UTF-8
locale=fr-FR
zone=Asia/Tokyo
vmArgs=[-Duser.language=fr, -Duser.country=FR, -Duser.timezone=Asia/Tokyo, -Dfile.encoding=UTF-8, -XX:ActiveProcessorCount=2]
```

Đây là **output môi trường quan sát được**, không phải golden output của mọi máy. Dùng nó để **ghi nhận biến môi trường thực**, không assert `os.name` hay vendor phải giống test machine mẫu.

**Cảnh báo bảo mật:** `getInputArguments()` có thể chứa `-Dpassword`, token hoặc đường dẫn nội bộ. Trong sản phẩm thật, **redact hoặc allowlist** JVM options trước khi xuất log/manifest; không gửi toàn bộ raw options cho third-party.

**`ActiveProcessorCount=2` không tạo CPU quota vật lý.** Trên HotSpot, nó ảnh hưởng số processors được JVM nhận diện/ergonomic policy, nhưng cgroup limits, affinity và CPU throttling thực tế vẫn cần được đo.

## 12. Concurrent tests: fixed seed không đảm bảo thứ tự xử lý

Ví dụ hai threads cùng đọc một `Random(42)` shared instance. Các lần gọi vào generator tạo sequence theo state, nhưng **thứ tự thread nhận từng giá trị** phụ thuộc interleaving. Vì thế “same seed” chưa đủ để mỗi request/thread nhận đúng một dữ liệu cố định.

### Các cách cải thiện

- Gán seed theo **logical task ID**, không theo native thread ID:
  
  ```java
  static Random randomForCase(long caseId) {
      return new Random(20261107L ^ (caseId * 1000003L));
  }
  ```
  
  Đây là **method snippet** chứ không phải full class. Nếu workflow cho phép gán task theo ID, mapping input độc lập scheduling.

- Dùng `CountDownLatch`, `CyclicBarrier` hoặc `Future` để điều phối phases thay vì `Thread.sleep(500)` và hy vọng race không xảy ra.
- Không nhóm dataset theo iteration order của `HashMap` nếu cần order xác định: dùng comparator/sort tường minh hoặc `LinkedHashMap` với insertion order được kiểm soát.
- Với `Collections.shuffle`, dùng `Random(seed)` và một danh sách đầu vào có **thứ tự ban đầu cố định**.
- Dùng concurrency tests để kiểm **invariants** và data races thay vì assert một interleaving không thuộc contract.

**Không** ép `SecureRandom` về seed công khai để “có thể tái lập” việc tạo session token. Data fixtures và crypto security là mục tiêu khác nhau.

## 13. Đo elapsed time đúng bằng `System.nanoTime()`

`System.nanoTime()` là high-resolution elapsed-time source với **origin tùy ý** trong JVM. Nó **không phải Unix timestamp**. Javadoc nói đơn vị nanosecond **không đồng nghĩa** timer resolution bằng một nanosecond.

Cách đúng:

```java
long start = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - start;
```

`doWork()` là hàm do ứng dụng định nghĩa (snippet). Lấy **hiệu** của hai giá trị trong cùng JVM để đo khoảng thời gian.

Không làm:

```java
long timestamp = System.nanoTime(); // Không phải epoch nanos.
```

Với timeouts, dùng:

```java
if (System.nanoTime() - started >= timeoutNanos) {
    // Timeout.
}
```

thay vì so với `started + timeoutNanos` có thể overflow. `System.currentTimeMillis()` biểu diễn wall-clock milliseconds và có thể bị điều chỉnh; không nên là timer chính cho microbenchmark.

### Đo đúng một lần vẫn chưa phải benchmark

Việc tính `elapsedNanos` không loại trừ:

- JIT compilation và inlining;
- dead-code elimination/constant folding;
- classloading/startup;
- GC/CPU scheduling;
- OS page cache;
- measurement overhead;
- CPU frequency và thermal throttling;
- benchmark không dùng output hoặc không làm tương đương work.

## 14. Demo Java 11: time smoke test có kiểm correctness

**Tên file:** `TimingSmokeDemo.java`.

```java
public final class TimingSmokeDemo {
    private static volatile long sink;

    private static long sumSquares(int limit) {
        long sum = 0;
        for (int i = 1; i <= limit; i++) {
            sum += (long) i * i;
        }
        return sum;
    }

    public static void main(String[] args) {
        for (int i = 0; i < 4000; i++) {
            sink = sumSquares(1000 + i % 64);
        }

        long start = System.nanoTime();
        long checksum = 0;
        for (int i = 0; i < 1000; i++) {
            checksum ^= sumSquares(1000 + i % 64);
        }
        long elapsedNanos = System.nanoTime() - start;
        sink = checksum;

        System.out.println("referenceCorrect=" +
                (sumSquares(1000) == 333833500L));
        System.out.println("elapsedPositive=" +
                (elapsedNanos > 0));
        System.out.println("checksum=" + checksum);
        System.out.println("elapsedNanos=" + elapsedNanos);
    }
}
```

Chạy:

```bash
javac --release 11 TimingSmokeDemo.java
java TimingSmokeDemo
```

**Một kết quả đã chạy:**

```text
referenceCorrect=true
elapsedPositive=true
checksum=6593356
elapsedNanos=292200
```

**Ba dòng đầu thể hiện logic của fixture và kiểm tra đo thời gian; dòng cuối thay đổi qua các runs.** Không trích `292200` để tuyên bố “mỗi lần tính cần chính xác 292.200 ns”.

Đây chỉ là **smoke test**, không có nhiều JVM forks, không so A/B, không đưa ra phân phối hoặc confidence interval. `volatile sink` giúp có observable side effect nhưng không thay thế một benchmark harness được thiết kế đúng.

## 15. Dùng OpenJDK JMH cho microbenchmark nghiêm túc

**JMH (Java Microbenchmark Harness)** là công cụ được OpenJDK duy trì để benchmark methods/operations trên JVM. Dự án chính thức khuyên dùng một JMH project riêng, cấu hình annotation processing chính xác và học các JMH Samples trước khi công bố kết quả.

JMH hỗ trợ:

- `@Benchmark`: code region đang đo.
- `@State`/`@Setup`: dữ liệu và lifecycle của fixture.
- Warm-up iterations, measurement iterations.
- JVM forks (chạy processes độc lập).
- `@Param`: dataset sizes có kiểm soát.
- Throughput/average time/sample time/single-shot modes.
- `Blackhole` hoặc return value để giảm nguy cơ compiler loại bỏ work.
- Export results JSON/CSV để xử lý bằng scripts.

### Mẫu benchmark có fixture theo seed

**Đây là class JMH, không phải standalone Java SE code**. Cần dependencies JMH và annotation processor phù hợp; không thể compile chỉ với JDK thuần.

```java
import java.util.Random;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 10, time = 1)
@Fork(3)
public class SumBenchmark {
    @Param({"256", "8192"})
    public int size;

    private int[] data;

    @Setup(Level.Trial)
    public void setup() {
        Random random = new Random(20261107L);
        data = new int[size];
        for (int i = 0; i < data.length; i++) {
            data[i] = random.nextInt(1000);
        }
    }

    @Benchmark
    public long sumArray() {
        long sum = 0;
        for (int value : data) {
            sum += value;
        }
        return sum;
    }
}
```

**Giải thích thiết kế:**

- Data được tạo trong `@Setup(Level.Trial)`, nên benchmark **không đo chi phí tạo fixture**. Nếu mục tiêu chính là đo cả việc tạo array, phải đưa chi phí đó vào method được đo — hai câu hỏi khác nhau.
- `@State(Scope.Thread)` tránh shared mutable fixture ngoài ý muốn trong concurrent benchmark.
- `@Fork(3)` yêu cầu ba JVM forks, giảm phụ thuộc JIT/heap state của một process.
- `@Warmup`/`@Measurement` cố định số iterations theo protocol mẫu. Không có một con số iterations luôn đúng; chọn bằng thử nghiệm stabilisation.
- Benchmark method trả `long` để JMH tiêu thụ output.
- `Random(seed)` tạo dataset ổn định; nếu muốn đo nhiều phân phối, dùng các parameters/generators khác nhưng vẫn ghi seed/contract.

Với Maven project được sinh theo JMH archetype chính thức, workflow thường là:

```bash
mvn -B -DskipTests package
java -jar target/benchmarks.jar -f 3 -wi 5 -i 10 -w 1s -r 1s -rf json -rff results.json
```

Các lệnh là **mẫu**, không phải tuyên bố một Maven project Java bình thường luôn có `target/benchmarks.jar`. Chọn một **JMH version đã kiểm chứng**, pin nó và cấu hình annotation processor theo project; xem `java -jar target/benchmarks.jar -h` để kiểm exact options của bản đó.

**JMH không tự cứu benchmark sai thiết kế**: nếu candidate bỏ bớt work, workload không đại diện hoặc dataset size khác, một con số JMH chính xác vẫn không đo đúng câu hỏi.

## 16. Benchmark dịch vụ thực cần end-to-end load test

JMH đo method/operator ở phạm vi JVM. Với HTTP/DB service, latency còn chịu:

- DNS/network/TLS;
- connection pool;
- request queue/thread pool;
- serialization/deserialization;
- database query/indexes;
- disk I/O;
- locks/contention;
- GC/JIT;
- load generator.

Nếu mục tiêu là **p99 API response time**, phải dùng load test với traffic shape đã biết và đo end-to-end latency, throughput, errors/timeouts, CPU/RSS/GC cùng nhau.

### Open-loop và closed-loop

- **Closed-loop**: client thường chờ response rồi mới gửi tiếp. Khi server chậm, client tự giảm offered load, có thể che tail latency dưới overload.
- **Open-loop**: arrival rate được lập kế hoạch độc lập với response completion, giúp nghiên cứu queueing theo mô hình phù hợp.

Chọn mô hình theo traffic thực, không có một lựa chọn luôn đúng. **Coordinated omission** là rủi ro bỏ qua độ trễ của những requests đáng lẽ đến trong khoảng thời gian hệ thống bị treo.

### Database workload phải có trạng thái được kiểm soát

Khi đo endpoint có DB:

- Schema/migration version và index.
- Row count, distribution, skew.
- Query plans/statistics.
- Cache warm/cold, transaction state.
- Connection pool và concurrency.
- Background jobs, replication lag.
- Cách reset data giữa runs.

Một run B hưởng DB cache nóng, run A cold-cache không chứng minh B code nhanh hơn.

## 17. Warm-up, forks và thứ tự A/B

**JIT compiler** cần execution profiles; ứng dụng cần load classes và warm caches. Đo request đầu tiên có thể chủ yếu phản ánh startup. Nhưng không có số warm-up iterations chung cho mọi app: phải chọn dựa vào workload state và metrics.

**Một JVM process có state**: code cache, heap, JIT profiles, static caches. Đo candidate A rồi B ngay trên cùng JVM có thể tạo carry-over. Với microbenchmark, JMH forks giúp giảm vấn đề này. Với end-to-end service cần chuẩn bị restart/reset rõ ràng.

### Thứ tự chạy có thể tạo bias

Nếu luôn chạy A trước B, máy có thể nóng lên, CPU throttling hoặc page cache đã đổi. Có thể thiết kế:

```text
Trial 1: A -> B
Trial 2: B -> A
Trial 3: A -> B
Trial 4: B -> A
```

Khi randomize thứ tự, lưu seed và order plan. Tránh xem một phép thử A/B gồm đúng một run mỗi phía là evidence đủ cho cải thiện nhỏ.

### Thống nhất logging/profiling

Bật JFR hoặc `-Xlog:gc*` ở candidate A mà tắt ở B tạo instrumentation overhead không cân bằng. Khi compare, thu metrics ở cùng mức, hoặc có một run profiling **riêng** để điều tra nguyên nhân.

## 18. Đo bao nhiêu, báo percentile nào?

Với latency:

- **p50**: median.
- **p95/p99/p99.9**: phần đuôi phân phối.
- **Mean**: dễ bị outliers kéo.
- **Max**: rất nhạy với số mẫu và thời lượng thử.
- **Throughput**: work hoàn thành trên thời gian, cần nói có tính error requests không.
- **RSS/CPU/GC**: để hiểu trade-offs.

Không lấy trung bình của p99 riêng từng worker rồi gọi là p99 của **toàn bộ requests**; phải gộp raw samples hoặc histograms đúng cách.

### Size mẫu p99.9

Với chỉ 100 requests, p99.9 không có độ tin cậy thực tế để đưa ra quyết định; cần nhiều observations và thời lượng đại diện. Histogram buckets, coordinated omission, retries và timeouts đều ảnh hưởng báo cáo quantiles.

### Một benchmark claim cần biết variance

Một kết quả:

```text
A mean = 20 ms, B mean = 18 ms
relative latency reduction = (20 - 18) / 20 = 10%
```

đúng **về số học** nhưng không đủ chứng minh cải thiện ổn định nếu run-to-run noise ±15%. Báo số trials, distribution/dispersion, uncertainty và practical significance theo SLO. Không bỏ “outliers” chỉ vì chúng làm xấu kết quả; exclusion policy phải được xác định trước.

**Đừng dùng một p-value đơn lẻ làm giấy bảo đảm.** Repeated runs có thể phụ thuộc chung host, cache hoặc traffic, và multiple comparisons cũng ảnh hưởng interpretation.

## 19. Dùng JFR/GC logs để giải thích chứ không thay metric ứng dụng

Java 11 có `jdk.jfr.Recording` và các GC/allocation/thread events phù hợp để phân tích JVM. Nhưng **không phải mọi JFR event của JDK 25 đã có ở Java 11**; kiểm tra đúng event types và settings runtime.

HotSpot GC logs:

```bash
java -Xms512m -Xmx2g -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

Lệnh dùng một dòng, không phụ thuộc shell nối dòng. Cần quyền ghi file. Log format thay đổi theo JDK, parser phải tương thích. Theo workload, GC logs/JFR có thể giải thích pause spikes, allocation pressure hoặc heap retention; không tự thay response-time histograms.

Giữ cùng:

- GC collector/config nếu so **code**.
- `-Xms/-Xmx` và container memory.
- CPU quotas/available processors.
- JFR recording settings.
- Log level và exporters.
- Thời lượng warm-up/measurement.

**Không** tự gọi `System.gc()` trước từng operation để “làm phép đo sạch”: lời gọi là request/hint, có thể làm lệch behavior, thậm chí không tạo collection mong đợi.

## 20. CI: deterministic gates khác performance alarms

### Deterministic hard gates

Phù hợp chạy liên tục:

- `javac --release 11` hoặc build cấu hình target API phù hợp.
- Unit/integration tests với seeded fixtures.
- Golden file checksum.
- Fixed clocks, charset, locale, timezone explicit.
- API contract/edge cases.
- Dependency integrity và reproducible data generation.
- Không gọi dịch vụ ngoài không kiểm soát khi đó không phải chủ đề đang test.

### Performance gate

CI runners chung có noisy neighbors và CPU throttling. Một ns/op tăng 1% trong một run không nhất thiết là regression. Có thể tách sang dedicated runner/benchmark lab và yêu cầu:

- n trials và n forks đủ;
- baseline history;
- variance threshold/confirmation run;
- raw results artifact;
- alert khi vượt noise budget;
- dedicated service load test khi cần.

**Performance regression tests không cần một “ngưỡng 0% biến thiên” phi thực tế**; thay vào đó có phương pháp thống kê và SLO threshold rõ.

### Artifact retention

Giữ source commit, exact commands, wrapper/lock files, fixture hash, raw CSV/JSON results, GC logs/JFR traces, plots tạo từ raw data và notes. **JFR/heap dumps/VM args có thể chứa thông tin nhạy cảm**: kiểm soát quyền truy cập, scrub credentials và TTL.

## 21. Những tình huống thường gây mất tính tái lập

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| CSV khác trên Windows/Linux | CRLF/LF hoặc charset | UTF-8 + LF rõ |
| Test expiry fail gần midnight/DST | Clock/zone phụ thuộc môi trường | `Clock.fixed`/`ZoneId` explicit |
| Hash đổi dù cùng seed | Input order/call sequence khác | Sort, lock generator version, log seed |
| Thread A và B nhận random khác | Interleaving | Seed theo logical task, không shared stream |
| CI dùng dependency mới | Floating version/cache | Pin và verify artifacts |
| Test đọc sai file | Relative working dir | Root test dir explicit |
| Bench nhanh bất thường | JIT bỏ work/constant folding | JMH, consume result, realistic data |
| Bench tăng latency không rõ lý do | GC, CPU throttling, caches | Capture JVM/environment metrics |
| Run B luôn tốt hơn do cache | Run order bias | Reset/warm-up, đảo order |
| p99 chạy lại đổi nhiều | Quá ít samples/histogram | Nhiều trials, đủ sample |
| Application RAM cao dù heap nhỏ | Native/direct memory | Đo RSS/nonheap và quota |
| Runtime khác baseline | Compile target vs JVM khác | Log `java -version` của process thực |
| Test cạnh tranh file tạm | Shared path | Temp directory per test |
| Log khác vì console language | Default locale/charset | Explicit formatting và UTF-8 |
| Concurrent test chỉ PASS nếu `sleep` | Race/timeouts | Synchronization + invariants |
| Performance đẹp nhưng errors tăng | Chỉ đếm success latency | Report errors/timeouts cùng throughput |
| Tốn CPU hơn khi bật profiler | Instrumentation khác | Measure tương đương hoặc tách profiling |

### Vì sao tăng sleep không sửa flaky concurrency test?

Một `Thread.sleep(2000)` không bảo đảm thread B đã sẵn sàng hoặc công việc xong khi CI quá tải. Dùng `CountDownLatch`, `Future.get(timeout)`, barriers, event loops có contract phù hợp. Nếu behavior có async timeout, test boundary/timeout bằng clock/executor controls thay vì sleep kéo dài vô hạn.

## 22. Quy trình A/B có thể lặp lại, từng bước

1. **Hypothesis:** định nghĩa câu hỏi và practical threshold.
2. **Correctness contract:** outputs/exception behavior/order/mutability/Unicode giống nhau ở những chỗ bắt buộc.
3. **Source:** pin commit, working tree clean, build dependencies.
4. **Runtime:** pin JDK vendor/build, image digest, GC/JVM flags.
5. **Data:** generator code + seed, schema, distribution, size và SHA-256.
6. **Environment:** CPU/OS/container limits, charset, locale, zone, file system conditions.
7. **Measurement protocol:** chọn JMH hay load test, warm-up, forks/trials, operation boundary.
8. **Test đúng trước:** contract tests pass.
9. **Thử A/B:** nhiều trials, đảo order hoặc randomize có log.
10. **Thu metrics:** raw latency/throughput, CPU/RSS/GC/errors.
11. **Thống kê:** medians/quantiles/variability, không cherry-pick.
12. **Kết luận:** ghi phạm vi đã chứng minh, tác động tài nguyên và limitations; giữ artifacts để người khác rerun.

Mẫu kết luận đúng:

```text
Trên runtime <vendor/version/build>, source <commit>,
dataset SHA-256 <hash>, traffic <profile>, resource budget
<CPU/RAM>, với protocol <warmup/forks/trials>,
candidate B cải thiện <metric> khoảng <value> so baseline A,
variability <interval>. Correctness tests pass.
Các kết quả chưa được xác minh ở <unmeasured workloads>.
```

Dấu `<...>` là placeholder **trong template báo cáo**, phải điền số thực và nguồn. Đừng đưa một kết luận giả định thành dữ liệu benchmark thật.

## 23. 25 câu hỏi tự luyện tập có đáp án

**1. Một unit test cần output chính xác, một benchmark có cần nanoseconds chính xác mỗi lần không?**

Không. Functional output có thể deterministic; timing là phân phối có noise.

**2. Chỉ ghi Java 11 đã đủ mô tả runtime chưa?**

Chưa. Cần vendor/update/build, JVM/architecture, flags.

**3. Cùng source và seed có đủ không?**

Chưa. Data generation call order, locale/TZ, dependencies, scheduler, platform và I/O còn khác.

**4. `Random(42)` có an toàn tạo security tokens?**

Không. Nó là PRNG tái lập, không phải nguồn bí mật an toàn.

**5. Hai threads dùng chung seeded Random có đảm bảo mỗi thread nhận cùng values?**

Không; thứ tự calls được gán cho threads phụ thuộc scheduler.

**6. Vì sao SHA-256 fixture có ích?**

Giúp phát hiện khác biệt bytes, không thay thế correctness/representativeness.

**7. Tại sao Java 11 cần khai báo charset explicit?**

Default charset có thể tùy OS/locale. Từ JDK 18, JEP 400 đổi default UTF-8; explicit format tránh khác biệt.

**8. `Files.readString(Path)` trong Java 11 dùng charset nào mặc định?**

UTF-8 theo API contract, dù default charset JVM khác.

**9. Vì sao dùng `Locale.ROOT` với CSV numeric?**

Giữ dấu thập phân/format giao thức độc lập locale người dùng.

**10. Tại sao local date/time test dễ flaky?**

Phụ thuộc clock, zone, DST và thời điểm chạy; inject `Clock` và đặt boundary inputs.

**11. `System.nanoTime()` có phải Unix timestamp không?**

Không; chỉ dùng hiệu giữa hai lần trong cùng JVM để đo elapsed.

**12. Vì sao `nanoTime` không đảm bảo độ chính xác 1 nanosecond?**

Đơn vị nanoseconds khác resolution/accuracy của timer thực.

**13. `--release 11` tốt hơn `-source 11 -target 11` ở điểm nào?**

Kiểm cả API platform Java 11, không chỉ language/class-file target.

**14. Chạy `--release 11` trên JDK 24 có chứng minh đã test runtime Java 11 không?**

Không; phải test trên oldest supported Java 11 runtime và dependencies.

**15. Khi nào dùng JMH?**

Khi muốn microbenchmark JVM operations có warm-up, forks, state và generated harness.

**16. JMH có bảo đảm hai benchmarks làm cùng việc không?**

Không; người thiết kế phải xác nhận equivalent work và realistic data.

**17. Vì sao setup ngoài `@Benchmark`?**

Để không tính chi phí khởi tạo fixture nếu câu hỏi chỉ là chi phí operation.

**18. `@Fork(3)` giúp gì?**

Giảm phụ thuộc vào JIT/heap history của một JVM, tạo các runs độc lập hơn.

**19. p99 của service có thể suy ra từ JMH ns/op không?**

Không; service còn queues, network, DB, locks, errors và concurrency.

**20. Có nên tính global p99 bằng trung bình p99 của 5 workers?**

Không. Phải gộp samples/histograms theo phương pháp đúng.

**21. Vì sao đổi thứ tự thử A/B?**

Để giảm bias do thời gian, CPU nhiệt, shared cache và background tasks.

**22. `-XX:ActiveProcessorCount=2` đảm bảo máy có 2 CPU cores vật lý cho test?**

Không; còn host quota, affinity, throttling và noisy neighbors.

**23. `System.gc()` trước mỗi run có làm GC/memory ổn định tuyệt đối không?**

Không; có thể không thực hiện GC như kỳ vọng và làm méo workload.

**24. Test flake do nhiều threads có thể giải bằng cách sleep dài hơn không?**

Không bảo đảm. Dùng coordination primitives/contract invariants, kiểm race đúng.

**25. Một báo cáo hiệu năng đủ thuyết phục gồm gì?**

Baseline/candidate, commit/JDK/toolchain, fixture hash, workload, warm-up/forks/trials, raw results, phân phối, uncertainty, resource trade-offs, correctness và phạm vi kết luận.

## 24. Nguồn kỹ thuật chính thức còn áp dụng

- [Oracle Java SE 11 — `Random`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Random.html): seed và thuật toán pseudo-random được chỉ định.
- [Oracle Java SE 11 — `SplittableRandom`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/SplittableRandom.html): seeded sequences và split.
- [Oracle Java SE 11 — `Clock`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/time/Clock.html): `fixed`, `offset` và `systemUTC`.
- [Oracle Java SE 11 — `System.nanoTime`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/System.html): elapsed-time source, arbitrary origin, độ phân giải và overflow.
- [Oracle Java SE 11 — `Files`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): UTF-8 text read/write, file resource handling.
- [Oracle Java SE 11 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8.
- [Oracle Java SE 11 — `Locale`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Locale.html): locale-sensitive APIs.
- [Oracle Java SE 11 — `ZoneId`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/time/ZoneId.html): timezone data.
- [Oracle Java SE 11 — `MessageDigest`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/MessageDigest.html): SHA-256.
- [Oracle Java SE 11 — `RuntimeMXBean`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/RuntimeMXBean.html): Java process arguments.
- [Oracle JDK 25 — `javac`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release` và Java platform API.
- [OpenJDK JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): cơ sở compiler release flag.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset từ Java 18.
- [Oracle JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): charset/timezone/locale khi đổi JDK.
- [OpenJDK JMH official project](https://github.com/openjdk/jmh): benchmark harness, Maven archetype, annotation processing, design.
- [OpenJDK JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples): forks, warm-up, Blackhole, state và measurement modes.
- [OpenJDK JMH Blackhole sample](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java): tránh dead-code elimination.
- [Oracle JDK 25 — `java` tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): JVM flags/unified logging.
- [Oracle Java SE 11 — `Recording`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): JFR events/profiling và lifecycle.

**Tóm tắt:** Khóa source/toolchain, fixture/seed/hash và dữ liệu ngữ cảnh (UTF-8, Locale, timezone, working directory, `Clock`) để **test đúng đắn** có thể tái lập. Với **đo hiệu năng**, cần warm-up, forks, nhiều trials, A/B có đối chứng và phân tích variation; JMH phù hợp microbenchmarks, load test phù hợp end-to-end. Luôn giữ raw results, JVM flags và môi trường để người khác có thể kiểm chứng được, thay vì chỉ công bố một con số đẹp.