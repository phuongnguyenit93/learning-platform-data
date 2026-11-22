# Đo khởi động ứng dụng với kho AppCDS trên JDK hiện đại

> **Java 10 — Thực hành tổng hợp.** **AppCDS** (Application Class-Data Sharing) được giới thiệu trong **JDK 10, JEP 310** để chia sẻ dữ liệu class ứng dụng, giảm một phần công việc nạp class ở các lần mở JVM tiếp theo. Đây không phải snapshot heap nghiệp vụ, không phải bảo đảm mọi ứng dụng đều khởi động nhanh hơn, và không đồng nhất với **AOT Cache** mới hơn. Bài này tập trung vào quy trình **dynamic AppCDS archive** còn được Oracle JDK 25 tài liệu hóa: dùng `-XX:ArchiveClassesAtExit` để tạo `app.jsa`, `-XX:SharedArchiveFile` để sử dụng; chứng minh lớp ứng dụng được tải từ archive; rồi đo **process-start-to-READY** với ba nhánh OFF / DEFAULT / APPCDS. Các ví dụ Java 17+ có thể chạy độc lập, không yêu cầu JDK 10 đã lỗi thời.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **CDS**, **AppCDS**, default/base CDS archive và dynamic AppCDS archive.
2. Giải thích **JDK 10 / JEP 310** và **JDK 13 / JEP 350** là hai mốc khác nhau: AppCDS và dynamic archiving.
3. Hiểu `-Xshare:off`, `-Xshare:auto` và vì sao `-Xshare:on` là chế độ test chứ không khuyến nghị mặc định production.
4. Biết các giai đoạn create archive, verify archive usage, benchmark startup và so sánh số liệu.
5. Biên dịch hai file Java17+ thành một JAR và dùng đúng **JAR classpath** nhất quán khi tạo và dùng kho.
6. Dùng `-Xlog:class+load=info` để kiểm chứng chính class ứng dụng đến từ `shared objects file (top)`.
7. Tách ba đối chứng **OFF / DEFAULT / APPCDS**, tránh gán lợi ích của default CDS cho riêng AppCDS.
8. Đo khoảng thời gian từ khởi chạy JVM process đến mốc `APP_READY`, không lẫn thời gian JVM exit.
9. Xây benchmark harness bằng `ProcessBuilder`, `System.nanoTime`, timeout watchdog, warmup, luân phiên thứ tự chạy và nhiều mẫu đo.
10. Tính p50, p95, min, max và phần trăm khác biệt APPCDS so với DEFAULT.
11. Phân biệt cold filesystem cache, warm OS cache, fresh JVM, Pod readiness và JIT warmup.
12. Hiểu hạn chế JDK build, classpath, modified JAR, module flags, custom classloaders, Java agents, containers và quyền archive.
13. Phân biệt dynamic AppCDS `.jsa` với **AOT cache `.aot` từ JDK 24/25**.
14. Diễn giải startup success/failure, memory footprint, ứng dụng thực tế và chi phí bảo trì.
15. Trả lời các bài tập và đánh giá tiêu chí GO/NO-GO.

## 2. Cơ chế hoạt động của CDS và AppCDS

### 2.1. Tại sao việc load class mất thời gian?

JVM mới thường phải khởi tạo runtime, classloaders, module layer, nạp bytecode từ runtime image/JAR, tạo metadata, verification/linking/initialization theo yêu cầu, sau đó mới đi vào code ứng dụng. Framework còn có dependency injection, quét component, tạo proxy, mở connections và load configuration.

**CDS** lưu sẵn những biểu diễn dữ liệu class để JVM **memory-map** và tận dụng ở lần mở sau. **AppCDS** mở rộng chia sẻ sang các lớp ứng dụng trong những điều kiện tương thích. Khi nhiều JVM dùng cùng shared archive, một số read-only metadata pages có thể chia sẻ ở OS level.

Nhưng:
- Không phải class nào cũng có thể/must được archive.
- AppCDS không bỏ qua nghiệp vụ startup, network hoặc DB.
- Không giữ arbitrary runtime heap objects như `HashMap` từ lần chạy trước.
- Không chứng minh tất cả methods đã JIT compile từ lần training.
- Không khôi phục một JVM đã crash.
- Có chi phí mở/map/verify archive nên lợi ích có thể nhỏ hoặc âm với ứng dụng rất nhỏ.

### 2.2. Default CDS thường đã bật

Oracle JDK 25 cho biết HotSpot distributions phổ biến thường có **default CDS archive** đi cùng JDK. Khi chạy không chỉ định `-Xshare:off`, JVM có thể nạp shared classes từ base archive.

| Nhánh đo | JVM options | Kết luận trực tiếp |
| --- | --- | --- |
| **OFF** | `-Xshare:off` | Không cố dùng CDS |
| **DEFAULT** | `-Xshare:auto`, không chỉ định `SharedArchiveFile` | Dùng CDS mặc định nếu hợp lệ |
| **APPCDS** | `-Xshare:auto -XX:SharedArchiveFile=app.jsa` | Dùng kho ứng dụng được tạo sẵn nếu hợp lệ |

**So sánh quan trọng nhất là DEFAULT → APPCDS.** OFF → APPCDS phản ánh cả default CDS và app-specific archive; không được nói toàn bộ chênh lệch do AppCDS.

### 2.3. Static và dynamic archives

- **Static archive:** có thể được tạo từ classlist qua `-XX:DumpLoadedClassList` và `-Xshare:dump` theo docs hiện hành, phù hợp khi cần kiểm soát danh sách class.
- **Dynamic archive:** từ JEP 350/JDK13, có thể ghi lúc ứng dụng kết thúc bằng `-XX:ArchiveClassesAtExit`, chỉ lưu các lớp thích hợp đã được nạp chưa có ở base archive.
- **Default archive:** thường được JDK đóng gói sẵn (và một số chế độ cung cấp các cách tạo lại).
- Dynamic archive nằm trên base/static archive; nguồn class load có thể biểu diễn là `shared objects file (top)`.

Đối với mục tiêu học và đo startup hôm nay, **dynamic archive** tránh một quy trình classlist thủ công không cần thiết. Cách static chưa biến mất khỏi HotSpot, nhưng không phải bước bắt buộc của lab.

### 2.4. Không nhầm Java heap với CDS

Archive không lưu lại input database, object graph tùy ý, kết quả API calls, sockets, sessions hay thread states. Nó cũng **không thay thế** persistence hoặc backup. Để phục hồi dữ liệu sau restart/crash phải dùng hệ lưu trữ có hợp đồng tương ứng, không lấy AppCDS làm database.

## 3. Dùng JDK còn được hỗ trợ, không tái lập cách cũ một cách máy móc

**JEP 310 trong Java 10** là xuất xứ tính năng. **Dynamic CDS qua JEP 350 trong Java 13** giúp workflow ngắn hơn. Oracle Java SE 25 vẫn tài liệu hóa:

~~~bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar demo.appcds.StartupApp
java -XX:SharedArchiveFile=app.jsa -cp app.jar demo.appcds.StartupApp
~~~

Đây là **mẫu lệnh** chỉ hoạt động sau khi tạo `app.jar` phù hợp, không phải yêu cầu cài Java10 runtime trong production.

Oracle Java SE 25 cũng có `-XX:+AutoCreateSharedArchive` để có thể tự tạo/nạp archive trong những trường hợp phù hợp. Nhưng nó có thể trộn lần tạo archive với lần chạy đầu, gây nhiễu benchmark. Bài học **tách archive-creation khỏi timing** và luôn ghi rõ JDK build đã dùng.

### 3.1. Khác với AOT cache JDK24/25

JEP483 trong JDK24 thêm **AOT class loading/linking cache**; JEP514 trong JDK25 đơn giản hóa việc tạo cache. Trên JDK25 có workflow mẫu:

~~~bash
java -XX:AOTCacheOutput=app.aot -cp app.jar demo.appcds.StartupApp
java -XX:AOTCache=app.aot -cp app.jar demo.appcds.StartupApp
~~~

Các lệnh `AOTCacheOutput/AOTCache` **không phải tương đương** với `ArchiveClassesAtExit/SharedArchiveFile`. Cache `.aot` và dynamic CDS `.jsa` khác lifecycle, format và tập tối ưu, dù đều phục vụ mục tiêu startup/warmup. Đừng gộp kết quả AOT vào nhánh APPCDS hay kỳ vọng JDK17 hiểu flags AOT của JDK25.

## 4. Định nghĩa thời gian đo

**Process-start-to-ready:**

\[
T_{\mathrm{ready}} = t(\mathrm{READY}) - t(\mathrm{trước\ khi\ tạo\ JVM})
\]

Mốc READY trong lab là **dòng stdout sau khi ứng dụng hoàn thành một lượng công việc xác định**. Trong HTTP service thật, READY nên đại diện trạng thái đã bind port, cấu hình xong và có thể phục vụ traffic theo readiness contract.

**Process-start-to-exit** khác: nó cộng cả công việc sau READY và shutdown hooks. Lệnh `time java Main` hoặc `Measure-Command` thường đo đến **exit**, không phải readiness cho service chạy lâu.

**Warm-OS-cache, fresh-JVM**: mỗi lần đo tạo JVM process mới nhưng OS có thể vẫn cache JDK/JAR/archive pages từ lần trước. Đó không phải cold node boot/image pull. Nếu muốn đo Kubernetes Pod scheduling-to-ready, cần thêm scheduling, image pull, container start, mounts, probes và service initialization ngoài Java.

## 5. Môi trường và cấu trúc project

Dùng **full HotSpot JDK 17+** được cập nhật, có `javac`, `jar`, `java` và quyền ghi file trong thư mục lab. Không cần Internet, root, Docker hay thư viện ngoài.

~~~text
appcds-lab/
├── src/
│   └── demo/
│       └── appcds/
│           ├── StartupApp.java
│           └── StartupBenchmark.java
├── out/
├── app.jar
└── app.jsa
~~~

Hai file nguồn đặt đúng tên/package. Tất cả commands tiếp theo chạy từ thư mục **appcds-lab**.

Các điều kiện:
- Dùng cùng **JDK build** khi tạo và sử dụng archive.
- Dùng đúng **cùng app.jar** khi training/benchmark.
- Không thay `-cp app.jar` bằng `-cp out` giữa các pha.
- Không tự bật JVM logs/JFR chỉ cho một nhánh.
- Nếu có `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`/`_JAVA_OPTIONS`, ghi lại chúng vì có thể thêm flags hoặc output.

## 6. File 1: StartupApp.java, chương trình có mốc READY xác định

Tạo `src/demo/appcds/StartupApp.java`:

~~~java
package demo.appcds;

import java.io.IOException;
import java.time.LocalDate;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Pattern;
import java.util.stream.IntStream;

/** A small deterministic application with an observable readiness point. */
public final class StartupApp {
    private StartupApp() {}

    public static void main(String[] args) throws IOException {
        Map<String, Integer> values = new TreeMap<>();
        values.put("java", 10);
        values.put("cds", 3);
        values.put("archive", 1);

        long valid = values.keySet().stream()
                .filter(k -> Pattern.matches("[a-z]+", k)).count();
        int sum = IntStream.rangeClosed(1, 1000).sum();
        String date = LocalDate.of(2026, 1, 1)
                .plusDays(1).toString();

        System.out.println("APP_READY entries=" + values.size()
                + " keys=" + valid + " sum=" + sum + " date=" + date);

        // Chỉ trong benchmark: giữ process còn sống tới khi
        // parent trả lời. Thời gian đo được dừng ở dòng READY.
        if (args.length == 1 && "--wait".equals(args[0])) {
            System.in.read();
        }
    }
}
~~~

Hợp đồng chương trình:
- `TreeMap` có 3 keys và mọi key thỏa pattern chỉ có chữ thường.
- `IntStream.rangeClosed(1,1000).sum()` bằng **500500**.
- `LocalDate.of(2026,1,1).plusDays(1)` là **2026-01-02**, không dựa vào local timezone.
- Không có argument `--wait`: app in READY, kết thúc bình thường để có thể ghi archive lúc exit.
- Có `--wait`: app in READY rồi đọc một byte stdin, cho phép harness **dừng đồng hồ trước shutdown**.

**Stdout chính xác khi chạy bình thường, một dòng:**

~~~text
APP_READY entries=3 keys=3 sum=500500 date=2026-01-02
~~~

Kết quả này đã được kiểm thử trên JDK24.0.2. Trên run chẩn đoán có JVM logs, thêm nhiều dòng log là bình thường; không coi logs là stdout của ứng dụng.

## 7. File 2: StartupBenchmark.java, harness đo thật

Tạo `src/demo/appcds/StartupBenchmark.java`. Mã chạy Java17+ không có dependencies ngoài Java SE:

~~~java
package demo.appcds;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public final class StartupBenchmark {
    private static final String READY =
            "APP_READY entries=3 keys=3 sum=500500 date=2026-01-02";
    private static final List<String> MODES =
            List.of("off", "default", "appcds");

    private StartupBenchmark() {}

    static long measure(Path jar, Path archive, String mode,
                        ScheduledExecutorService watchdog)
            throws Exception {
        String exe = System.getProperty("os.name")
                .startsWith("Windows") ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"),
                "bin", exe);

        List<String> cmd = new ArrayList<>();
        cmd.add(java.toString());

        switch (mode) {
            case "off" -> cmd.add("-Xshare:off");
            case "default" -> cmd.add("-Xshare:auto");
            case "appcds" -> {
                cmd.add("-Xshare:auto");
                cmd.add("-XX:SharedArchiveFile=" + archive);
            }
            default -> throw new IllegalArgumentException(mode);
        }

        Collections.addAll(cmd, "-cp", jar.toString(),
                "demo.appcds.StartupApp", "--wait");

        ProcessBuilder builder = new ProcessBuilder(cmd);
        builder.redirectError(ProcessBuilder.Redirect.INHERIT);

        long start = System.nanoTime();
        Process process = builder.start();
        ScheduledFuture<?> killer = watchdog.schedule(
                process::destroyForcibly, 15, TimeUnit.SECONDS);

        try {
            try (BufferedReader reader = process.inputReader(
                    StandardCharsets.UTF_8)) {

                String line = reader.readLine();
                long readyNanos = System.nanoTime() - start;

                if (!READY.equals(line)) {
                    throw new IOException("no READY marker in " + mode
                            + "; received: " + line);
                }

                try (OutputStream input = process.getOutputStream()) {
                    input.write('\n');
                    input.flush();
                }

                if (!process.waitFor(5, TimeUnit.SECONDS)
                        || process.exitValue() != 0) {
                    throw new IOException("child failed: " + mode);
                }

                return readyNanos;
            }
        } finally {
            killer.cancel(false);
            if (process.isAlive()) process.destroyForcibly();
        }
    }

    static double medianMillis(List<Long> nanos) {
        List<Long> sorted = new ArrayList<>(nanos);
        Collections.sort(sorted);
        int n = sorted.size();
        return n % 2 == 1
                ? sorted.get(n / 2) / 1_000_000.0
                : (sorted.get(n / 2 - 1) / 2.0
                        + sorted.get(n / 2) / 2.0) / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2 || args.length > 3) {
            throw new IllegalArgumentException(
                    "usage: StartupBenchmark app.jar app.jsa [rounds]");
        }

        Path jar = Path.of(args[0]).toAbsolutePath().normalize();
        Path archive = Path.of(args[1]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(jar)
                || !Files.isRegularFile(archive)) {
            throw new IllegalArgumentException("jar/archive missing");
        }

        int rounds = args.length == 3
                ? Integer.parseInt(args[2]) : 12;
        if (rounds < 3 || rounds > 200) {
            throw new IllegalArgumentException("rounds must be 3..200");
        }

        Map<String, List<Long>> samples = new LinkedHashMap<>();
        for (String mode : MODES) samples.put(mode, new ArrayList<>());

        ScheduledExecutorService watchdog =
                Executors.newSingleThreadScheduledExecutor(task -> {
                    Thread t = new Thread(task, "watchdog");
                    t.setDaemon(true);
                    return t;
                });

        try {
            for (int round = -2; round < rounds; round++) {
                for (int j = 0; j < 3; j++) {
                    String mode = MODES.get(Math.floorMod(round + j, 3));
                    long elapsed = measure(jar, archive, mode, watchdog);
                    if (round >= 0) samples.get(mode).add(elapsed);
                }
            }
        } finally {
            watchdog.shutdownNow();
        }

        System.out.println("mode,n,p50_ms,p95_ms,min_ms,max_ms");

        for (Map.Entry<String, List<Long>> entry :
                samples.entrySet()) {
            List<Long> copy = new ArrayList<>(entry.getValue());
            Collections.sort(copy);
            int n = copy.size();
            double p95 = copy.get((int) Math.ceil(0.95 * n) - 1)
                    / 1_000_000.0;

            System.out.printf(Locale.ROOT,
                    "%s,%d,%.3f,%.3f,%.3f,%.3f%n",
                    entry.getKey(), n, medianMillis(copy), p95,
                    copy.get(0) / 1_000_000.0,
                    copy.get(n - 1) / 1_000_000.0);
        }

        double baseline = medianMillis(samples.get("default"));
        double candidate = medianMillis(samples.get("appcds"));

        System.out.printf(Locale.ROOT,
                "appcds_vs_default_p50_improvement_pct=%.1f%n",
                100.0 * (baseline - candidate) / baseline);
    }
}
~~~

### 7.1. Mỗi sample gồm những gì?

- Parent là JVM đang chạy `StartupBenchmark`.
- Nó dùng `java.home` của chính parent để gọi **java executable cùng JDK**.
- Bắt đầu đo `System.nanoTime` **trước** khi tạo child JVM.
- Lấy dòng đầu tiên child in ra stdout; yêu cầu **chính xác `APP_READY`**.
- Khi nhận marker, dừng đồng hồ, gửi newline vào stdin để child hoàn tất rồi xác nhận exit 0.
- Một watchdog daemon thread kill child nếu quá 15 giây, tránh treo ở `readLine()`; failures không bị ghi làm sample hợp lệ.
- Child stderr kế thừa terminal để lỗi JVM có cơ hội xuất hiện; stdout giữ đơn nhất cho marker.

Chi phí được đo là **OS process launch + JVM init + công việc ứng dụng trước READY + độ trễ parent nhận pipe**. Không tự gọi đây là thời gian “class verification thuần” hoặc time-to-ready của toàn Kubernetes Pod.

### 7.2. Warmup và thứ tự đo

Harness chạy 2 vòng warmup không lưu kết quả; sau đó chạy `rounds` vòng, mỗi vòng có ba nhánh. Thứ tự xoay:

~~~text
Vòng 0: off → default → appcds
Vòng 1: default → appcds → off
Vòng 2: appcds → off → default
~~~

Luân phiên giảm thiên lệch do OS cache và việc một nhánh luôn chạy sau. Nhưng không loại bỏ toàn bộ biến động do CPU power state, antivirus, background work và host load. Đối với benchmark production, dùng nhiều trials/hosts và có thể randomize order theo seed được ghi lại.

### 7.3. Thống kê có ý nghĩa

Harness in:
- `p50_ms`: median của những startup samples.
- `p95_ms`: nearest-rank percentile, index `ceil(0.95*N)-1`.
- `min_ms` và `max_ms`.
- Improvement p50 `100×(p50_default−p50_appcds)/p50_default`.

**N=12** rất ít để ước lượng p95/p99 dài hạn: p95 nearest-rank tại vị trí `ceil(0.95×12)=12`, tức maximum của 12 observations. Nên dùng nhiều samples/trials hơn khi đưa ra quyết định vận hành.

## 8. Build JAR và chạy ba chế độ

Đứng tại thư mục gốc lab:

~~~bash
javac --release 17 -d out src/demo/appcds/StartupApp.java src/demo/appcds/StartupBenchmark.java
jar --create --file app.jar -C out .
jar --list --file app.jar
~~~

JAR phải có `demo/appcds/StartupApp.class` và `demo/appcds/StartupBenchmark.class`. Dùng classpath JAR trong mọi giai đoạn; không đổi sang thư mục non-empty `out` sau khi đã tạo archive.

### 8.1. Baseline tắt CDS

~~~bash
java -Xshare:off -cp app.jar demo.appcds.StartupApp
~~~

Lệnh in dòng READY, rồi thoát. Chỉ một lần chưa phải benchmark.

### 8.2. CDS mặc định

~~~bash
java -Xshare:auto -cp app.jar demo.appcds.StartupApp
~~~

Chế độ auto cho phép default CDS khi hỗ trợ; **không chỉ định archive ứng dụng**, nên đây là baseline phù hợp cho lợi ích tăng thêm.

### 8.3. Tạo dynamic AppCDS archive

~~~bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar demo.appcds.StartupApp
~~~

Sau khi thoát thành công, kiểm tra `app.jsa` tồn tại và kích thước không bằng 0. **Đừng đo thời gian của lệnh tạo archive như một lần khởi động APPCDS thường lệ**: nó vừa chạy application vừa ghi archive lên disk.

Trên Windows PowerShell, nếu tự ghép đường dẫn archive từ biến, hãy truyền nguyên một argument `("-XX:ArchiveClassesAtExit="+$archivePath)`. Cú pháp nối dòng shell có thể khác; các lệnh trên cố ý viết một dòng.

### 8.4. Dùng archive

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -cp app.jar demo.appcds.StartupApp
~~~

Ứng dụng vẫn in đúng READY. Nhưng **output này chưa chứng minh** HotSpot thực sự dùng top archive: cần bước log xác nhận.

## 9. Bắt buộc xác minh class nguồn từ archive

Dùng diagnostic run riêng:

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -Xlog:class+load=info -cp app.jar demo.appcds.StartupApp
~~~

Tìm chính class `demo.appcds.StartupApp` với đoạn:

~~~text
demo.appcds.StartupApp source: shared objects file (top)
~~~

Trong thử nghiệm với OpenJDK24.0.2, class ứng dụng đã thực sự nạp từ **shared objects file (top)**. Tiền tố timestamp và format log không cố định; bài chỉ nêu phần text cần kiểm tra.

Nếu chỉ thấy `java.lang.Object source: shared objects file`, đó có thể là default/base archive, **không xác nhận AppCDS của StartupApp**.

Có thể dùng diagnostics CDS:

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -Xlog:cds=info -cp app.jar demo.appcds.StartupApp
~~~

Hoặc fail-fast để kiểm tra trong môi trường test:

~~~bash
java -Xshare:on -XX:SharedArchiveFile=app.jsa -cp app.jar demo.appcds.StartupApp
~~~

Theo Oracle JDK25, `-Xshare:on` chỉ dành cho test/diagnostics; archive không load được có thể làm process exit. **Không bật `-Xshare:on` trong production một cách vô điều kiện.**

**Không đưa verbose logs vào timing runs**, vì class load logs có thể in hàng nghìn dòng, làm tăng I/O và khiến dòng đầu của stdout không còn là APP_READY.

## 10. Chạy benchmark thực tế

Chỉ sau khi archive hợp lệ và logs xác nhận:

~~~bash
java -cp app.jar demo.appcds.StartupBenchmark app.jar app.jsa 12
~~~

Với `rounds=12`, harness chạy 2 warmup rounds rồi 12 sample/arm, tổng 36 measured child JVMs và 6 warmup child JVMs. Output gồm một header cố định, ba dòng với số thực, và một dòng improvement.

**Header stdout cố định:**

~~~text
mode,n,p50_ms,p95_ms,min_ms,max_ms
~~~

Ví dụ định dạng, **không phải output literal**:

~~~text
off,12,<p50_ms>,<p95_ms>,<min_ms>,<max_ms>
default,12,<p50_ms>,<p95_ms>,<min_ms>,<max_ms>
appcds,12,<p50_ms>,<p95_ms>,<min_ms>,<max_ms>
appcds_vs_default_p50_improvement_pct=<percent>
~~~

Các dấu ngoặc trong khối trên là placeholders mô tả schema, **không phải Java tự in nguyên**. Mili-giây tùy JDK, OS, CPU, file cache, load và quyền filesystem. Bài không cam kết một tốc độ cố định.

### 10.1. Tính phần trăm cải thiện

\[
I = 100 \times \frac{p50_{\mathrm{default}} - p50_{\mathrm{appcds}}}{p50_{\mathrm{default}}}
\]

Giả sử một bộ số **minh họa**:

| Nhánh | p50 (ms) | p95 (ms) |
| --- | ---: | ---: |
| OFF | 115 | 150 |
| DEFAULT | 80 | 105 |
| APPCDS | 72 | 100 |

Chênh lệch **APPCDS so với DEFAULT** bằng `(80−72)/80×100=10%`. Nếu chỉ so OFF với APPCDS sẽ ra ~37%, nhưng đó là **tổng** CDS + AppCDS, không đúng khi muốn đo riêng AppCDS.

Nếu APPCDS p50 là 90 ms, improvement từ DEFAULT 80 ms là **−12,5%**, tức ứng dụng chậm hơn trên metric đó. Kết quả âm không tự chứng minh lỗi JVM; phải kiểm archive usage, nhiễu, working set và môi trường.

### 10.2. Đọc p50 và p95 đúng cách

p50 giảm có thể hữu ích cho CLI/autoscaling, nhưng service còn yêu cầu:
- p95/p99 time-to-ready nếu đủ samples;
- thời gian first successful request sau READY;
- độ ổn định startup và error/timeout rate;
- CPU startup peaks;
- GC và post-ready warmup;
- memory footprint nhiều replicas;
- chi phí tạo và phát hành archives.

Không lấy một sample may mắn để kết luận. Không báo p99 từ 12 lần đo như một tail SLO đáng tin.

## 11. Tại sao benchmark có thể cho kết quả sai?

### 11.1. Thay JDK/JAR giữa các arm

Archive gắn với cấu hình JDK/runtime/app. Nếu thay một dependency hoặc regenerate `app.jar` sau khi tạo kho, AppCDS có thể bị vô hiệu; JVM `-Xshare:auto` vẫn có thể chạy ứng dụng, khiến người đo tưởng kho đang có hiệu lực.

**Khắc phục:** pin JDK build, cùng JAR SHA-256, classpath/module flags; tạo lại kho khi thay artifacts và xác minh class source.

### 11.2. Classpath/module path không tương thích

Oracle Java SE25 nêu các hạn chế đối với CDS:
- Non-empty directories trên classpath/module-path không phải lúc nào được hỗ trợ.
- Classpath lúc training cần tương thích với classpath lúc runtime.
- JAR files bị sửa sau archive creation có thể khiến archive không load được.
- Một số module options cần khớp để archived module graph hoạt động.
- Một số flags như `--patch-module` có thể vô hiệu sharing.

Bài lab dùng JAR để tránh các sai khác không cần thiết.

### 11.3. Java agents/custom classloaders

Framework có thể sinh proxy bytecode, custom class loader, lazy classes, class redefinition, instrumentation. Không đảm bảo tất cả classes đều eligible. Một archive được tạo từ workload chưa chạm startup path chính sẽ có lợi ích hạn chế.

**Khắc phục:** training representative startup path, xem class load sources và diagnostics, dùng packaging hướng dẫn bởi framework đang sử dụng; không giả định Spring Boot fat JAR với nested JAR hoạt động y hệt JAR đơn giản của lab.

### 11.4. JVM processes mới nhưng OS caches nóng

Mỗi sample tạo JVM mới, nhưng page cache của JDK image/JAR/`app.jsa` có thể vẫn nóng. Điều này mô phỏng “warm filesystem cache, new JVM process”, không phải host cold boot.

Nếu mục tiêu là latency khi autoscaler tạo Pod mới:
- Phân biệt node đã có image và node phải pull image.
- Đo image pull, container create, service bind, readiness, dependency connect.
- Giữ resource limits, CPU quotas, heap/GC/flags tương đương giữa arms.

### 11.5. Logging và đo lường làm thay đổi workload

Verbose class/CDS logging, JFR profile, tracing hoặc stdout formatting có overhead. Trên ứng dụng nhỏ, overhead có thể cùng cỡ với cải thiện AppCDS. Do đó **diagnostic runs** và **timing runs** nên tách riêng. Nếu cần instrumentation trong benchmark, giữ tương đương trên cả ba arms.

### 11.6. Concurrency và tail statistics

p95 theo nearest-rank với 12 samples thực chất là sample max; để đánh giá p99, dùng số mẫu lớn hơn nhiều và lặp trên nhiều time windows. Balanced rotation giảm order bias nhưng không thay được random trials và kiểm soát background load.

### 11.7. Quy mô và mục tiêu ứng dụng

Một CLI ngắn chạy hàng nghìn lần/ngày, một server lâu dài chỉ restart mỗi tháng và một serverless function có cold starts liên tục có **giá trị kinh tế của vài ms khác nhau**. Chỉ áp AppCDS nếu cải thiện khởi động vượt chi phí archive generation, deployment, versioning và security.

## 12. Memory footprint không đồng nhất startup time

CDS/AppCDS có thể giúp chia sẻ một số metadata pages giữa nhiều JVM. Tuy nhiên:
- **RSS** riêng mỗi process có thể đếm lặp shared pages.
- **PSS** cho phép phân bổ shared pages theo process, hữu ích khi đo aggregate memory.
- **cgroup memory.current** tính theo phạm vi cgroup, khác phép cộng RSS.
- `Runtime.maxMemory()` hay heap-used chỉ đo một phần memory.

Nếu mục tiêu là giảm memory khi chạy 10 JVM replicas, hãy đo **PSS/cgroup usage cùng workload**, không lấy p50 startup làm bằng chứng tiết kiệm memory.

## 13. AOT cache là phép thử riêng trên JDK25+

Đối với JDK25, `-XX:AOTCacheOutput=app.aot` và `-XX:AOTCache=app.aot` là một workflow AOT khác. Nó có thể lưu thêm dữ liệu liên quan class loading/linking và những artifacts chuẩn bị sẵn theo version. Cần:
- training workload phù hợp;
- kiểm tra JDK/OS/CPU/app artifact compatibility;
- xác minh cache được nạp (`-Xlog:aot`);
- so với DEFAULT và không trộn với dynamic CDS `app.jsa`.

**Không** đổi `-XX:SharedArchiveFile` sang tên `app.aot` để giả vờ tạo AOT cache, hoặc nói AppCDS đã bảo đảm JIT compiled code luôn sẵn ở startup.

## 14. Đưa AppCDS vào CI và production

Một pipeline hợp lý:

1. Pin JDK distribution/build và app artifact SHA.
2. Build/test ứng dụng **không phụ thuộc** AppCDS.
3. Chạy training có workload đại diện; tạo archive file.
4. Xác minh file nonempty, class sources từ archive, startup exit code và correctness.
5. Thực hiện OFF/DEFAULT/APPCDS A/B trên cùng infrastructure, nhiều trials.
6. Thu số liệu sample raw + p50/p95, startup errors, CPU, PSS/memory.
7. Đóng gói archive cùng app JAR/JDK image tương thích, bảo vệ quyền và integrity.
8. Dùng `-Xshare:auto`/fallback policy khi archive lỗi; không dùng `-Xshare:on` làm production mặc định.
9. Khi nâng app/JDK, **tạo lại** và kiểm tra archive; có rollback.
10. Đo readiness/service SLO thật sau deployment.

### 14.1. Security và operational concerns

Archive không được để untrusted users sửa. Khi đưa kho vào container image/volume, cần đúng ownership, filesystem permissions, integrity, versioning, rollback policy. Trên read-only filesystem, training tại runtime có thể không tạo được file; trong trường hợp đó cần tạo archive ở build/initialization stage rồi phát hành artifact được bảo vệ.

**Không lấy một AppCDS archive được tạo trên developer laptop và mặc định dùng lại qua mọi JDK production images.**

### 14.2. GO/NO-GO

**GO to pilot** chỉ khi class sharing thật, correctness, latency distribution, error rate và archive lifecycle đều được xác nhận, đồng thời lợi ích startup quan trọng với sản phẩm. **NO-GO** khi không có cải thiện đáng tin hoặc phát sinh chi phí/bất ổn không phù hợp. Các mức như “cải thiện tối thiểu 5%” là policy riêng, không phải Java guarantee.

## 15. Bài tập có đáp án

### Bài 1 — Lịch sử

**Đề:** AppCDS được giới thiệu ở JDK10 hay JDK13?

**Đáp án:** AppCDS từ **JDK10/JEP310**; JDK13/JEP350 bổ sung **dynamic CDS archives**.

### Bài 2 — Ba đối chứng

**Đề:** Tại sao phải thêm DEFAULT ngoài OFF/APPCDS?

**Đáp án:** Default CDS có thể đã giúp JDK khởi động nhanh. DEFAULT→APPCDS mới đo lợi ích **tăng thêm** của app archive.

### Bài 3 — Tạo kho

**Đề:** `-XX:ArchiveClassesAtExit=app.jsa` dùng khi nào?

**Đáp án:** Lúc training; JVM ghi archive khi thoát thành công. Không đưa chi phí dump vào latency production startup.

### Bài 4 — Dùng kho

**Đề:** Chỉ tạo `app.jsa` rồi chạy `java -Xshare:auto -cp app.jar Main` có dùng AppCDS chưa?

**Đáp án:** Chưa chỉ định archive ứng dụng; cần `-XX:SharedArchiveFile=app.jsa` và xác minh logs.

### Bài 5 — Lớp từ default CDS

**Đề:** Log thấy `java.lang.Object` nạp từ shared objects file. Có chứng minh `StartupApp` dùng top archive không?

**Đáp án:** Không. Kiểm chính `demo.appcds.StartupApp source: shared objects file (top)`.

### Bài 6 — Stdout

**Đề:** App chính in gì trên dòng READY?

**Đáp án:** `APP_READY entries=3 keys=3 sum=500500 date=2026-01-02`.

### Bài 7 — Readiness

**Đề:** App in READY ở 80 ms và exit ở 120 ms. Harness đo khoảng nào?

**Đáp án:** Khoảng 80 ms cộng parent/IPC overhead, không đợi 120 ms để tính readiness.

### Bài 8 — Improvement

**Đề:** DEFAULT p50 80 ms, APPCDS p50 72 ms. Cải thiện bao nhiêu?

**Đáp án:** `(80−72)/80×100=10%` theo p50.

### Bài 9 — Kết quả âm

**Đề:** DEFAULT 80 ms, APPCDS 92 ms. Improvement?

**Đáp án:** `(80−92)/80×100=−15%`, chậm hơn 15% theo p50 trong mẫu đó; kiểm archive usage và measurement noise.

### Bài 10 — P95 với 12 samples

**Đề:** Nearest-rank p95 ở N=12 rơi vào mẫu nào?

**Đáp án:** `ceil(0.95×12)=12`, sample cuối sau sort, tức max; quá ít để suy ra p95 dài hạn.

### Bài 11 — JDK mismatch

**Đề:** Archive tạo JDK24 dùng trên JDK25 có được cam kết?

**Đáp án:** Không. Regenerate trên JDK build thực dùng, verify logs và test.

### Bài 12 — App JAR sửa

**Đề:** Rebuild app.jar sau training. Có cần tạo lại `app.jsa`?

**Đáp án:** Có; JAR content/classpath mismatch có thể invalid archive.

### Bài 13 — Logs và timing

**Đề:** Chỉ bật `-Xlog:class+load=info` trong APPCDS khi đo p50 có công bằng không?

**Đáp án:** Không. I/O/logging overhead làm bias, còn làm marker không ở dòng stdout đầu. Diagnostic riêng.

### Bài 14 — Container

**Đề:** Harness đo startup 60 ms có nghĩa Pod scheduling-to-ready là 60 ms?

**Đáp án:** Không; Pod còn image pull, container creation, mounts, probes và các bước khác.

### Bài 15 — Dynamic CDS vs AOT

**Đề:** Có thể thay `SharedArchiveFile=app.jsa` bằng `SharedArchiveFile=app.aot` để dùng AOT JDK25 không?

**Đáp án:** Không. AOT workflow dùng `AOTCache`, artifact khác và cần kiểm tra riêng.

### Bài 16 — Persistence

**Đề:** `HashMap` được tạo trong training có tự được khôi phục nhờ AppCDS không?

**Đáp án:** Không; arbitrary heap state không được persist trong AppCDS.

### Bài 17 — Multiple JVM footprint

**Đề:** Vì sao cộng RSS của 10 JVM có thể đánh giá sai sharing savings?

**Đáp án:** Shared pages có thể bị đếm tại mỗi process; cân nhắc PSS/cgroup memory và CPU.

### Bài 18 — Availability

**Đề:** p50 cải thiện 20% nhưng một lần startup fail do archive mismatch. Có nên deploy ngay?

**Đáp án:** Không. Cần giải quyết compatibility, fallback, correctness, error monitoring, release lifecycle và rollback.

## 16. Checklist kết thúc thực hành

- [ ] Hiểu AppCDS được giới thiệu Java10 và vẫn còn áp dụng trên JDK hiện đại.
- [ ] Không dùng JDK10 đã EOL làm runtime production.
- [ ] Đã build đúng hai file Java17+ và đóng JAR.
- [ ] Giữ nguyên JDK/JAR/classpath giữa training và benchmark.
- [ ] Có archive `app.jsa` nonempty, được tạo ngoài timing runs.
- [ ] `-Xlog:class+load` xác nhận StartupApp đến từ shared objects file (top).
- [ ] Thử OFF, DEFAULT và APPCDS với cùng workload.
- [ ] Biết OFF→APPCDS không phải lợi ích riêng của app archive.
- [ ] Không dùng `-Xshare:on` làm production default.
- [ ] Có READY marker đúng và mốc đo rõ ràng.
- [ ] Harness có watchdog, child exit check, warmup, luân phiên ba arms.
- [ ] Có N samples mỗi arm và không bỏ error samples.
- [ ] Đọc p50/p95 và số sample đủ cẩn trọng.
- [ ] Không dùng verbose classload/CDS logs ở timing run.
- [ ] Phân biệt warm filesystem cache với cold host/image.
- [ ] Chú ý container CPU quota/memory, Pod readiness và background load.
- [ ] Có memory PSS/cgroup metrics nếu mục tiêu là footprint.
- [ ] Không gọi dynamic CDS là persistent Java heap hoặc AOT cache.
- [ ] Regenerate archive khi đổi JDK/build/JAR/module options.
- [ ] Có kiểm tra integrity, quyền file và rollback.
- [ ] Quyết định áp dụng dựa vào lợi ích đo trên ứng dụng thật, không phải một con số giả định.

## 17. Kết luận

Để đánh giá startup bằng AppCDS chính xác: **tạo kho, chứng minh thực sự sử dụng kho, rồi đo**. Một kết quả có ý nghĩa phải so ba nhóm OFF/DEFAULT/APPCDS, lấy **DEFAULT làm baseline** cho phần đóng góp bổ sung của AppCDS, dùng nhiều JVM processes mới và ghi đúng time-to-ready, sample count, p50/p95, errors cùng môi trường đo.

Đây vẫn là thực hành hợp lệ trên HotSpot JDK25 theo tài liệu Oracle, nhưng **AOT cache trên JDK24/25 là một hướng bổ sung riêng**. Không có tỷ lệ speedup được bảo đảm; với service thực, chỉ quyết định sau khi kiểm tra startup SLO, correctness, archive lifecycle và vận hành an toàn.

## 18. Tài liệu chính thức

- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): giới thiệu AppCDS từ JDK10.
- [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): dynamic archiving từ JDK13.
- [Oracle Java SE 25 — The java Command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `ArchiveClassesAtExit`, `SharedArchiveFile`, classpath constraints, `-Xshare` và logging.
- [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): default CDS, AppCDS và memory sharing.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache JDK24.
- [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): đơn giản hóa AOT workflow JDK25.
- [Oracle Java SE 25 — ProcessBuilder API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ProcessBuilder.html): child process invocation.
- [Oracle Java SE 25 — System.nanoTime API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()): monotonic elapsed time.