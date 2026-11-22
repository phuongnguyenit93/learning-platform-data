# Đo chi phí JFR và tác động tùy chọn JVM trên tải đại diện (Java 14+)

> **Mục tiêu:** biết xây phép đo công bằng giữa **JFR tắt**, **JFR `default`**, **JFR `profile`** và một cấu hình JVM thay đổi; kiểm tra tính đúng của kết quả, thu thập số liệu CPU/GC/latency/throughput và phân tích nhiễu đo. Hướng dẫn sử dụng các công cụ JDK 17+ đang được hỗ trợ: `java -XX:StartFlightRecording`, `jcmd JFR.*`, `jfr summary/print`, API `GarbageCollectorMXBean`. Ví dụ đã được biên dịch/chạy và xuất file `.jfr` trên OpenJDK 24. **Không dùng các cờ mở khóa JFR thương mại cũ hoặc kiến thức legacy.**

## 1. Vì sao đo chi phí JFR thay vì tin một tỷ lệ cố định?

**Java Flight Recorder (JFR)** ghi lại các sự kiện runtime như GC, allocation, CPU load, thread scheduling, lock contention và I/O. Ghi dữ liệu có chi phí CPU, memory buffering và file I/O; bản thân việc quan sát có thể thay đổi hệ thống được quan sát (*observer effect*).

Oracle mô tả cấu hình `default.jfc` thường có overhead thấp và được thiết kế để ghi liên tục; `profile.jfc` thu nhiều dữ liệu hơn, hữu ích khi cần profiling nhưng có thể tạo thêm chi phí. Tài liệu có dẫn mức overhead điển hình thấp cho nhiều ứng dụng, **không phải cam kết tốc độ hoặc giới hạn cho mọi workload**. Chỉ có thí nghiệm với dữ liệu và điều kiện tương ứng mới trả lời được JFR tốn bao nhiêu trên ứng dụng của bạn.

Các nguyên nhân khiến kết quả thay đổi:

- Tỷ lệ event xảy ra, threshold/period, stack traces, custom events; profiling dày hơn có thể tốn thêm.
- Ứng dụng CPU-bound, allocation-heavy, network-bound hoặc có nhiều lock contention cho chi phí khác nhau.
- Cách dùng JFR: từ startup, attach vào JVM đã warm, dump định kỳ, disk buffering, storage chậm/nhanh.
- Kích thước heap, GC, thread count, JDK vendor/build, CPU quota/cgroup, filesystem, container/VM.
- Số liệu đang đo là **thời gian xử lý trong ứng dụng** hay **tổng thời gian tiến trình từ start tới exit**.

**Không kết luận “JFR luôn dưới 1%” chỉ vì một tài liệu nêu mức điển hình**, cũng không kết luận nó tăng overhead lớn chỉ dựa một vòng lặp chạy 30 ms.

## 2. Thế nào là tải đại diện khi kiểm thử tương thích?

Một phép đo có giá trị cần gắn với hoạt động thực tế: tỷ lệ các loại HTTP requests, thao tác cơ sở dữ liệu, batch jobs, cache hits/misses, payload sizes, concurrency, thông lượng và các dependency bên ngoài. Vòng lặp CPU đơn thuần chỉ là demo để kiểm tra cú pháp đo.

| Thành phần | Cách đảm bảo đối chứng |
|---|---|
| Mã ứng dụng | Cùng build, commit, dependency và cùng input/dataset |
| Máy/VM/container | Cùng vCPU, quota, RAM, storage, network và giới hạn |
| JDK | Cùng vendor, version/build, OS/architecture |
| JVM flags | Cùng GC, heap, JIT, logging; trừ duy nhất yếu tố muốn đo |
| Tải đầu vào | Cùng request mix, concurrency, records/s, payload, warm cache |
| Thời gian | Warmup riêng, đo đủ dài, timestamp và thời lượng cố định |
| Nhiễu | Tránh background jobs, theo dõi throttling, nhiệt độ và I/O contention |
| Kết quả | Checksum/response correctness, error rate, timeout luôn được xác minh |

Chỉ đo CPU hoặc throughput trung bình là chưa đủ. Nếu có service thực, nên thu **p50/p95/p99 latency**, request errors, throughput, CPU utilization/time, GC pauses, allocation rate, heap/RSS và mức throttling. Khi có file `.jfr`, thêm số event/loại sự kiện, dung lượng recording và thời gian dump.

**Với CLI chạy ngắn**, tổng thời gian startup/shutdown rất quan trọng. **Với dịch vụ chạy lâu**, steady-state latency và throughput thường quan trọng hơn phần startup; cần đo riêng hai góc nhìn.

## 3. Thiết kế ma trận thí nghiệm không lẫn yếu tố

| Case | JFR | JVM flags cố định/biến đổi | Trả lời câu hỏi |
|---|---|---|---|
| **A: off** | Không có active recording | `-Xms256m -Xmx256m -XX:+UseG1GC` | Baseline |
| **B: default** | `settings=default` | Giống hệt A | JFR mặc định thêm chi phí bao nhiêu? |
| **C: profile** | `settings=profile` | Giống hệt A | Profiling dày hơn ảnh hưởng thế nào? |
| **D: heap128** | Off | `-Xms128m -Xmx128m -XX:+UseG1GC` | Hai cấu hình heap-size khác nhau ảnh hưởng ra sao? |

So **B/A** hoặc **C/A** mới cô lập được yếu tố JFR. So **D/A** đánh giá ảnh hưởng của **cấu hình heap-size 128 MB so với 256 MB** — vì cả `-Xms` và `-Xmx` đều thay đổi, không nói đây là thử nghiệm của đúng một *flag* đơn lẻ. Không so C với D rồi quy sai khác cho riêng JFR.

Có thể mở rộng thành thử nghiệm **2 × 2** (heap 128/256 × JFR off/on) nếu cần kiểm tra *interaction effects*, nhưng phải lập ma trận và cách phân tích rõ ràng, không trộn ngẫu nhiên nhiều biến.

Chạy tối thiểu **vài lượt độc lập mỗi case**, ví dụ 5–10 lượt, có warmup thích hợp, xen kẽ A–B–C–D rồi D–C–B–A để tránh bias do thứ tự. Nếu variance lớn, cần nhiều lần đo và báo spread/độ tin cậy; không chọn run tốt nhất để quảng bá một phần trăm overhead.

## 4. Cách bật/tắt JFR đúng trên JDK hiện hành

Java Flight Recorder hiện có trong JDK thông thường, không cần `-XX:+UnlockCommercialFeatures` hay flag `-XX:+FlightRecorder` từ tài liệu Java rất cũ. Các lệnh dưới đây là **minh họa Bash**, với `service.jar` phải được thay bằng artifact thật.

```bash
# A: cùng JVM, không chạy recording JFR
java -Xms256m -Xmx256m -XX:+UseG1GC -jar service.jar

# B: recording default; ghi file khi JVM kết thúc bình thường
java -Xms256m -Xmx256m -XX:+UseG1GC \
  -XX:StartFlightRecording=filename=default.jfr,dumponexit=true,settings=default \
  -jar service.jar

# C: recording profile (không đổi JVM heap/GC)
java -Xms256m -Xmx256m -XX:+UseG1GC \
  -XX:StartFlightRecording=filename=profile.jfr,dumponexit=true,settings=profile \
  -jar service.jar
```

`settings=default` và `settings=profile` chọn cấu hình chuẩn từ `JAVA_HOME/lib/jfr`. `filename=...` và `dumponexit=true` quyết định đường dẫn recording đầu ra lúc JVM thoát phù hợp. Cần cấp quyền ghi thư mục, kiểm tra không bị đầy đĩa, lưu `.jfr` an toàn và **xác minh file tồn tại**, không chỉ dựa vào startup log.

Đối với server đang chạy, có thể mở recording theo **giai đoạn đo** với `jcmd`:

```bash
jcmd -l
jcmd 12345 JFR.check
jcmd 12345 JFR.start name=load-sample settings=default
# Phát tải đại diện và lấy metric trong cùng cửa sổ.
jcmd 12345 JFR.dump name=load-sample filename=load-sample.jfr
jcmd 12345 JFR.stop name=load-sample
jcmd 12345 JFR.check
```

`12345` chỉ là PID ví dụ: phải thay bằng PID thật. `JFR.dump` tạo snapshot file **không tự dừng recording**; `JFR.stop` mới dừng. `jcmd` cần quyền attach phù hợp và namespace PID đúng trong môi trường container.

Khi muốn đo overhead của **việc ghi JFR** trong steady state, không nên bật `profile` chỉ sau một đoạn warmup cho riêng case C nhưng lại bật default từ startup cho B mà không ghi lại sự khác biệt; hãy thiết kế cùng phạm vi quan sát. Khi đánh giá chi phí **dump file định kỳ**, tính cả disk I/O/dump theo lịch tương đương production.

Kiểm tra file JFR sau chạy bằng công cụ hiện hành:

```bash
jfr summary default.jfr
jfr summary profile.jfr
jfr print --events jdk.CPULoad,jdk.GarbageCollection default.jfr
jfr view default.jfr
```

`jfr summary` cho biết event types, counts và kích thước; `jfr print` hiển thị các event đã có, `jfr view` có các báo cáo tổng hợp. **Không dùng `jfr summary` trong vùng timed benchmark**, vì bản thân nó cũng tiêu thụ CPU và I/O. Một event không xuất hiện có thể do bị disabled, threshold, sampling, recording quá ngắn, chứ **không nhất thiết** hiện tượng ấy hoàn toàn vắng mặt.

## 5. Chương trình Java 17+ chạy được để kiểm tra quy trình

Đây là **workload tổng hợp** có CPU work và allocation, giữ 64 mảng byte, dùng biến `volatile` để tránh JIT đơn giản loại bỏ toàn bộ thao tác, cùng checksum để phát hiện case chạy sai. Nó chứng minh cách tạo phép đo kỹ thuật, **không đại diện** cho ứng dụng HTTP/DB/CI cụ thể.

Lưu mã sau thành **`JfrCostWorkload.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Locale;

public final class JfrCostWorkload {
    private static volatile Object escape;

    private static long work(int iterations, int blockBytes) {
        byte[][] ring = new byte[64][];
        long checksum = 0L;
        for (int i = 0; i < iterations; i++) {
            byte[] block = new byte[blockBytes];
            long x = i + 1L;
            for (int j = 0; j < 64; j++) {
                x ^= x << 13;
                x ^= x >>> 7;
                x ^= x << 17;
            }
            block[0] = (byte) x;
            block[blockBytes - 1] = (byte) (x >>> 8);
            ring[i & 63] = block;
            checksum += (block[0] & 255L) +
                        257L * (block[blockBytes - 1] & 255L);
        }
        escape = ring;
        return checksum;
    }

    private static long gcCount() {
        long sum = 0L;
        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = gc.getCollectionCount();
            if (count >= 0L) {
                sum += count;
            }
        }
        return sum;
    }

    public static void main(String[] args) {
        int iterations = Integer.parseInt(args[0]);
        int blockBytes = Integer.parseInt(args[1]);
        if (iterations <= 0 || blockBytes < 2) {
            throw new IllegalArgumentException(
                "iterations > 0 and blockBytes >= 2 required");
        }

        for (int i = 0; i < 3; i++) {
            work(Math.min(iterations, 20_000), blockBytes);
        }
        long before = gcCount();
        long started = System.nanoTime();
        long checksum = work(iterations, blockBytes);
        long elapsedNanos = System.nanoTime() - started;
        long collections = gcCount() - before;

        System.out.println("iterations=" + iterations);
        System.out.println("blockBytes=" + blockBytes);
        System.out.println("checksum=" + checksum);
        System.out.println("gcCollections=" + collections);
        System.out.printf(Locale.ROOT, "elapsedMs=%.3f%n",
            elapsedNanos / 1_000_000.0);
        System.out.printf(Locale.ROOT, "operationsPerSecond=%.1f%n",
            iterations * 1_000_000_000.0 / elapsedNanos);
    }
```

Biên dịch:

```bash
javac -encoding UTF-8 JfrCostWorkload.java
java -Xms128m -Xmx128m -XX:+UseG1GC JfrCostWorkload 250000 2048
```

Ba trường đầu ra sau đã kiểm tra **chính xác** trên OpenJDK 24 với lệnh smoke test:

```text
iterations=250000
blockBytes=2048
checksum=8223925148
```

Chương trình còn in `gcCollections=...`, `elapsedMs=...` và `operationsPerSecond=...` bằng số cụ thể tại runtime; **những con số này thay đổi theo máy và lượt**, vì vậy không có một stdout thời gian “đúng” cho mọi lần chạy.

Cơ chế đo: `System.nanoTime()` lấy elapsed time của hàm `work` **sau ba vòng warmup ngắn**; `GarbageCollectorMXBean.getCollectionCount()` lấy chênh lệch số collection được JVM cung cấp; throughput tính `iterations / elapsedSeconds`. Đừng nhầm `gcCollections` với tổng pause time hoặc GC wall-time chuẩn hóa xuyên mọi collector.

Đoạn warmup ngắn chỉ giúp trình diễn API, **không đủ** để kết luận JIT đã ổn định trong mọi workload. Đối với bài đo thật, tăng warmup, chạy lâu hơn, dùng nhiều JVM forks và xác nhận kết quả nghiệp vụ như throughput, p99 và error rate từ nguồn đo độc lập.

## 6. PowerShell đo nhiều case và xuất CSV

Script này đã được thử trên **Windows PowerShell 5.1 và OpenJDK 24** với bản smoke test dùng `rounds=1`, `iterations=250000`; ba biến thể JFR off/default/profile cùng biến thể heap-size đều tạo được kết quả, JFR file tồn tại, và CSV có bốn dòng. Script đầy đủ bên dưới chạy **5 rounds** và nhiều iterations hơn để minh họa cách giảm nhiễu; điều chỉnh cho workload/máy thật trước khi dùng làm benchmark.

Tạo file **`run-experiment.ps1`** trong thư mục đã có `JfrCostWorkload.class`:

```powershell
# run-experiment.ps1 - Windows PowerShell 5.1+
$ErrorActionPreference = 'Stop'
$iterations = 5000000   # Điều chỉnh để đo đủ dài trên máy của bạn
$blockBytes = 2048
$rounds = 5
$outDir = Join-Path (Get-Location) 'measurements'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$results = [System.Collections.Generic.List[object]]::new()
$referenceChecksum = $null

for ($round = 1; $round -le $rounds; $round++) {
    if ($round % 2 -eq 1) {
        $order = @('off', 'default', 'profile', 'heap128')
    } else {
        $order = @('heap128', 'profile', 'default', 'off')
    }
    foreach ($mode in $order) {
        $jvm = @('-Xms256m', '-Xmx256m', '-XX:+UseG1GC')
        if ($mode -eq 'heap128') {
            $jvm = @('-Xms128m', '-Xmx128m', '-XX:+UseG1GC')
        }
        $recordingPath = $null
        if ($mode -eq 'default' -or $mode -eq 'profile') {
            $recordingPath = Join-Path $outDir ("$mode-r$round.jfr")
            $jvm += "-XX:StartFlightRecording=filename=$recordingPath,dumponexit=true,settings=$mode"
        }
        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        $lines = & java @jvm -cp . JfrCostWorkload $iterations $blockBytes 2>&1
        $exit = $LASTEXITCODE
        $timer.Stop()
        if ($exit -ne 0) { throw "Java failed in mode $mode : $lines" }

        $data = @{}
        foreach ($line in $lines) {
            $s = [string]$line
            if ($s -match '^(iterations|blockBytes|checksum|gcCollections|elapsedMs|operationsPerSecond)=(.+)$') {
                $data[$Matches[1]] = $Matches[2]
            }
        }
        if ($data.Count -ne 6) {
            throw "Missing stdout fields for $mode : $lines"
        }
        if ($null -eq $referenceChecksum) {
            $referenceChecksum = $data['checksum']
        } elseif ($data['checksum'] -ne $referenceChecksum) {
            throw "Workload checksum changed: $mode"
        }
        $jfrSize = 0L
        if ($null -ne $recordingPath) {
            if (-not (Test-Path -LiteralPath $recordingPath)) {
                throw "Missing JFR file: $recordingPath"
            }
            $jfrSize = (Get-Item -LiteralPath $recordingPath).Length
        }
        $results.Add([pscustomobject]@{
            Round = $round
            Mode = $mode
            Checksum = [long]$data['checksum']
            InnerMs = [double]::Parse($data['elapsedMs'],
                [System.Globalization.CultureInfo]::InvariantCulture)
            WallMs = [math]::Round($timer.Elapsed.TotalMilliseconds, 2)
            GcCollections = [long]$data['gcCollections']
            JfrBytes = $jfrSize
        })
    }
}
$results | Export-Csv -Path (Join-Path $outDir 'runs.csv') -NoTypeInformation -Encoding UTF8
$results | Format-Table Round,Mode,Checksum,InnerMs,WallMs,GcCollections,JfrBytes -AutoSize

# Trung vị cho mỗi case: chỉ có ý nghĩa khi đủ nhiều rounds.
$medians = @{}
foreach ($group in ($results | Group-Object Mode)) {
    $sorted = @($group.Group | ForEach-Object { $_.InnerMs } | Sort-Object)
    $mid = [int][math]::Floor($sorted.Count / 2)
    if ($sorted.Count % 2 -eq 1) {
        $median = [double]$sorted[$mid]
    } else {
        $median = ([double]$sorted[$mid - 1] +
                   [double]$sorted[$mid]) / 2.0
    }
    $medians[$group.Name] = $median
}
$baselineMs = $medians['off']
foreach ($mode in @('off', 'default', 'profile', 'heap128')) {
    $deltaPct = 100.0 * ($medians[$mode] / $baselineMs - 1.0)
    '{0}: medianInnerMs={1:N3}, deltaVsOff={2:N2}%' -f
        $mode, $medians[$mode], $deltaPct
}
```

Chạy trong thư mục đó:

```powershell
javac -encoding UTF-8 .\JfrCostWorkload.java
.\run-experiment.ps1
Import-Csv .\measurements\runs.csv |
    Format-Table Round,Mode,InnerMs,WallMs,GcCollections,JfrBytes
jfr summary .\measurements\default-r1.jfr
```

Mỗi vòng có thứ tự đảo chiều để giảm drift theo thời gian. Script kiểm tra `$LASTEXITCODE`, đủ sáu trường đầu ra, checksum **phải giống nhau**, recording `.jfr` **phải tồn tại** ở case được bật; lỗi làm dừng thử nghiệm thay vì báo số liệu sai. Với đường dẫn có dấu cách, toàn bộ tùy chọn JFR được thêm như **một tham số JVM**.

`measurements/runs.csv` lưu:

| Cột | Ý nghĩa |
|---|---|
| `Round`, `Mode` | Nhận diện lượt và case |
| `Checksum` | Kiểm tra kết quả các case thực sự tương đương |
| `InnerMs` | Thời gian đoạn `work` **trong JVM**, không bao gồm startup/dump |
| `WallMs` | Thời gian PowerShell chờ cả process từ start đến exit |
| `GcCollections` | Chênh lệch các GC collection counts trong đoạn đo |
| `JfrBytes` | Kích thước `.jfr` sau khi JVM thoát (0 với case off) |

**Không suy ra rằng `JfrBytes=0` ở case off nghĩa là JVM chưa từng khởi tạo JFR**; đó chỉ là case script không chủ động ghi một recording. Muốn biết service thật có recording khác đang chạy không, dùng `jcmd PID JFR.check`.

### Số liệu đã quan sát chỉ nhằm smoke test

Một lượt chạy ngắn với 250.000 iterations trên **OpenJDK 24 Windows**:

| Case | Checksum | `gcCollections` | `elapsedMs` | JFR file |
|---|---:|---:|---:|---|
| off, heap 128 MB | 8.223.925.148 | 6 | 34,011 | Không |
| default, heap 128 MB | 8.223.925.148 | 7 | 50,518 | Có |
| profile, heap 128 MB | 8.223.925.148 | 7 | 48,758 | Có |
| off, heap 256 MB | 8.223.925.148 | 4 | 43,029 | Không |

**Đây không phải phép đo overhead đáng tin:** thời gian chỉ vài chục ms, một run mỗi case, JIT/cache/OS noise chưa kiểm soát. Một lượt thử khác đã cho các thời gian khác hẳn dù checksum giống nhau. **Không tính hay công bố “JFR chậm X%” từ bảng đó.** Trong bảng smoke test này cấu hình heap mặc định của lần chạy ban đầu là **128 MB**; ma trận của script chính sử dụng **256 MB** cho A/B/C và 128 MB riêng cho D. Không được ghép tùy tiện các số của hai ma trận để tính chênh lệch.

## 7. Phân tích kết quả công bằng: thời gian, throughput, độ nhiễu

Với số lượng operations cố định và checksum bằng nhau:

```text
Runtime overhead (%) =
    100 * (median_elapsed_JFR / median_elapsed_off - 1)

Throughput loss (%) =
    100 * (1 - throughput_JFR / throughput_off)

Ví dụ giả định: median off = 1000 ms, JFR = 1030 ms.
Runtime overhead = 3,0%.
Throughput loss (cùng số operations) ≈ 2,91%.
Đây KHÔNG phải kết quả của máy thử.
```

**Chọn cùng một mẫu số:** so `InnerMs` của B với `InnerMs` của A, hoặc so `WallMs` của B với `WallMs` A. Không so `InnerMs` của một case với `WallMs` của case khác.

- `InnerMs` không tính Java startup, JFR initialization, shutdown và ghi dump lúc exit. Nó có ích để đánh giá khối lượng xử lý bên trong JVM, nhưng là cái nhìn **không đầy đủ** của CLI thời gian ngắn.
- `WallMs` bao gồm startup, warmup, thực thi, in kết quả, flush/dump file `.jfr`, shutdown và chi phí khởi chạy process từ shell. Nếu cần tối ưu trải nghiệm chạy công cụ CLI, đây có thể là metric quan trọng hơn.
- `JfrBytes` phản ánh dung lượng artifact, **không** quy đổi trực tiếp thành % CPU hoặc heap occupancy.
- `GcCollections` từ nhiều MXBeans có thể được định nghĩa khác nhau theo GC implementation; nên đọc GC pause/duration qua log/JFR cùng các metrics ứng dụng.

**Điều kiện bác bỏ kết luận:** checksum khác nhau, request mix lệch, error rate khác, thiếu file JFR, sample quá ngắn, CPU throttling, máy bị thermal throttling, GC/OOM bất thường hoặc chênh lệch bé hơn biến động giữa các run. Báo cả variance/percentiles, số lần đo, điều kiện đo, timestamp và các run bị loại kèm lý do.

Một trường hợp `median JFR - median off` nhỏ hơn dao động tự nhiên của baseline không đủ chứng minh JFR có overhead đáng kể. Nên tăng duration/repetitions và dùng cách làm thống kê thích hợp. **Không chọn kết quả có lợi nhất** hoặc xóa outlier thiếu tiêu chí trước đó.

## 8. Kiểm tra nội dung recording để biết mình đang đo thứ gì

Sau khi có JFR, xem `jfr summary` và đối chiếu event config. Một số event hữu ích:

| Nhóm | Các event có thể dùng | Cảnh báo diễn giải |
|---|---|---|
| CPU | `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.ExecutionSample` | Sampling không biểu diễn chính xác thời gian CPU của mọi thread |
| GC | `jdk.GarbageCollection` và events GC/heap tương ứng | Đọc pause/time theo đúng event, không suy từ size file |
| Allocation | `jdk.ObjectAllocationSample` | Sample, không phải tổng số cấp phát nếu chưa hiểu weighting |
| I/O | `jdk.FileRead`, `jdk.FileWrite`, `jdk.SocketRead`, `jdk.SocketWrite` | Threshold có thể lọc thao tác ngắn |
| Contention | `jdk.JavaMonitorEnter`, `jdk.ThreadPark` | Không thấy event không tự chứng minh không có contention |

`default.jfc` và `profile.jfc` là cấu hình có sẵn; nội dung chính xác và số lượng events phụ thuộc phiên bản JDK. Nếu cần tăng độ chi tiết một trường hợp, **tạo config `.jfc` riêng** bằng `jfr configure`, không sửa file cấu hình chuẩn trong JDK.

```bash
jfr configure --input default.jfc --output custom.jfc
jfr help configure
jfr summary measurements/default-r1.jfr
jfr print --events jdk.GarbageCollection measurements/default-r1.jfr
```

Các tùy chọn `eventName#enabled`, `eventName#threshold`, `eventName#period`, `eventName#stackTrace` có thể ảnh hưởng mạnh tới số lượng event và chi phí recording. **Giảm threshold hoặc tăng period sampling** là một thay đổi điều kiện đo, nên được thử riêng; không bật tất cả event/stack traces chỉ vì muốn “nhiều dữ liệu”.

Nếu một recording có thời lượng quá ngắn, `jfr summary` có thể hiển thị duration được làm tròn thành `0 s` dù file hợp lệ. Kiểm tra thêm event count, file size, thời điểm start/end và thời gian workload, không tự kết luận JFR lỗi vì dòng duration tròn số này.

## 9. So sánh tác động của tùy chọn JVM mà không nhầm với JFR

Tùy chọn JVM cũng cần thiết kế đối chứng:

- `-Xms` và `-Xmx`: thay đổi heap có thể ảnh hưởng GC frequency, RSS, resizing, OOM, latency. Demo `heap128` thay **cả hai**, nên gọi là so **hai cấu hình heap-size**, không gọi “chỉ thay một flag”.
- `-XX:+UseG1GC` hoặc collector hiện hành khác: có thể ảnh hưởng throughput và pause, nhưng số GC MXBeans giữa các loại collector không nhất thiết tương đương.
- `-XX:MaxGCPauseMillis` là **mục tiêu heuristic** của G1, không phải bảo đảm tối đa pause. Đo p95/p99 và GC log để đánh giá.
- `-XX:ActiveProcessorCount` làm thay đổi cách JVM nhìn số CPU cho ergonomics/GC; khi thử phải phù hợp CPU quota thực tế.
- `-XX:StartFlightRecording`, `settings=default/profile/custom` và event threshold là một nhóm biến **riêng**, cần giữ nguyên khi đánh giá heap/GC.

Đối chiếu các flags thực của JVM, không chỉ ghi lại script muốn chạy:

```bash
# Một JVM kiểm tra mới, KHÔNG phải process service hiện chạy:
java -Xms256m -Xmx256m -XX:+UseG1GC -XX:+PrintFlagsFinal -version

# Nếu có PID thật và quyền attach:
jcmd 12345 VM.command_line
jcmd 12345 VM.flags -all
jcmd 12345 JFR.check
```

Nếu sử dụng Unified Logging để quan sát GC, dùng `-Xlog` hiện hành và giữ log options **giống nhau** giữa các case. Đừng bật `-Xlog:gc*=debug` chỉ cho JFR-on rồi quy mọi overhead cho JFR.

```bash
java -Xms256m -Xmx256m -XX:+UseG1GC \
  -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags \
  -jar service.jar
```

Đây là lệnh minh họa cho ứng dụng `service.jar` thực; file log, cường độ logging và đường dẫn cũng có chi phí. Tính tương thích nghĩa là **ứng dụng chạy đúng và có SLA chấp nhận được** ở cấu hình muốn triển khai; một flag làm ứng dụng nhanh hơn trong microbenchmark có thể làm p99 tệ hơn trên workload thực.

## 10. Quy trình kiểm thử tương thích cho ứng dụng thật

1. **Chốt baseline:** chọn cùng version ứng dụng, JDK, GC, heap, CPU quota, config, load generator và sample dataset; ghi `java -version`/startup args.
2. **Functional check:** chạy test nghiệp vụ trước benchmark; mọi case phải cho kết quả đúng và không tăng lỗi. Với demo là checksum; với service là response codes, dữ liệu/transaction.
3. **Warmup:** khởi động JVM, làm nóng JIT/cache/dependency. Không thu số liệu steady-state trong giai đoạn còn class loading/JIT bùng lên nếu bài toán không nhắm đo startup.
4. **Case A:** đo không JFR recording. Ghi timestamp, request count, latency histogram, throughput, CPU/GC/memory.
5. **Case B/C:** chạy chính tải ấy với `settings=default` rồi `settings=profile` trên instance/fork tương đương. Ghi file JFR và xác minh readback bằng `jfr summary`.
6. **Case D:** tắt JFR rồi đổi riêng cấu hình heap (hoặc một JVM option được chọn) để đánh giá hệ quả của tuning.
7. **Lặp & xen kẽ:** ít nhất vài lượt mỗi case; ghi variance. Với dịch vụ production, cân nhắc canary/isolated load test và thời gian đủ lâu; không chạy stress experiment gây ảnh hưởng người dùng.
8. **Phân tích:** so p95/p99, throughput, resource utilization, JFR event count, GC stats và phần trăm chênh lệch với baseline.
9. **Kết luận có điều kiện:** ghi JDK/OS/workload và confidence; không dùng kết quả này làm chân lý chung cho mọi app.
10. **Rollback:** có cách tắt recording hoặc trả về flags gốc khi SLO/CPU/file footprint vượt ngưỡng.

Một kịch bản đo thực tế có thể dùng tải thông thường, gần saturation và spike ngắn; xác định request mix và mục tiêu của từng kịch bản trước, tránh trộn nhiều mức tải trong một số trung bình.

## 11. Bảo mật và an toàn dữ liệu `.jfr`

Recording có thể chứa tên class/method, stack traces, thread names, file paths, JVM options, thông tin host hoặc event tự tạo. Nó không phải file vô hại khi chia sẻ:

- Giới hạn quyền đọc/ghi và vị trí lưu; tránh upload `.jfr` production vào kho công khai.
- Đặt retention, `maxsize`/`maxage` hợp lý cho continuous recording, theo dõi dung lượng disk và vòng đời file.
- Với nhu cầu chia sẻ, cân nhắc `jfr scrub` nếu phiên bản JDK hỗ trợ, **và tự rà soát file sau scrub**, không giả định mọi metadata nhạy cảm đã bị xóa.
- Không bật `path-to-gc-roots=true` vô điều kiện: thu GC roots có thể tốn thời gian và gây pause.
- Không giảm mọi event thresholds/periods hoặc bật stack traces dày tại production khi chưa đánh giá.
- Giữ quyền `jcmd`/attach theo chính sách bảo mật của môi trường; không mở cổng diagnostic không có xác thực.

## 12. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao sai | Cách sửa |
|---|---|---|
| “JFR luôn dưới 1%” | Overhead phụ thuộc workload/settings | Đo cùng ứng dụng và tải đại diện |
| Chỉ chạy một lần trong 30–50 ms | JIT/GC/OS noise rất lớn | Warmup, đo đủ dài, nhiều rounds |
| So profile/heap128 với baseline heap256 | Đổi hai yếu tố cùng lúc | So B/A, C/A; D/A là thí nghiệm heap riêng |
| Ghi mảng tương đương workload HTTP thực | Thiếu network/DB/concurrency/queueing | Dùng workload E2E thật |
| Checksum sai nhưng vẫn so runtime | Các case không làm cùng việc | Dừng benchmark, sửa đầu vào |
| Lấy `JfrBytes` làm % CPU overhead | File size không đại diện trực tiếp CPU | Đo CPU, latency, throughput |
| Không thấy event là không có vấn đề | Event có thể off/threshold/sampling | Xem config và recording coverage |
| Tính `WallMs`/`InnerMs` thành một tỷ lệ overhead | Hai đồng hồ đo khác giai đoạn | So cùng loại metric |
| Chỉ đo average, bỏ p99/error rate | Tail latency có thể xấu đáng kể | Theo dõi SLO và phân phối |
| Thay JVM flags và bật JFR trong cùng case | Không biết thay đổi nào gây chênh lệch | Cô lập yếu tố hoặc lập thử nghiệm đa yếu tố |
| Phân tích file bằng `jfr summary` trong lúc timed section | Tool phân tích dùng tài nguyên | Phân tích offline sau đo |
| Chỉ tin flag command-line mà không kiểm tra recording | Start/dump/config có thể sai | `JFR.check` và file `jfr summary` |
| Ghi `profile` liên tục trong production vô hạn | Có thể tăng overhead/đĩa | Đo theo SLO, đặt retention/limits |
| Dùng cờ JFR thương mại cũ | Lỗi thời với JFR hiện đại | Dùng `-XX:StartFlightRecording` |
| Chia sẻ `.jfr` chưa duyệt | Có thể chứa metadata nhạy cảm | Bảo vệ/quét/scrub trước chia sẻ |

## 13. Checklist kết luận

- [ ] Nguồn/bản JDK và JVM options đã được ghi chính xác.
- [ ] Tải và input đại diện, checksum/đáp án nghiệp vụ giống nhau.
- [ ] A/B/C thay duy nhất recording settings; D là cấu hình JVM riêng.
- [ ] Có warmup, thời lượng đo đủ dài, nhiều rounds/forks và kiểm tra noise.
- [ ] Có throughput, latency p50/p95/p99, error rate, GC và resource metrics.
- [ ] So cùng loại thời gian, không trộn startup với steady-state.
- [ ] `.jfr` tồn tại, đọc được và đúng events/settings cần phân tích.
- [ ] Có số đo trung vị/spread, cách loại outlier và môi trường chi tiết.
- [ ] Không phát biểu phần trăm overhead từ một smoke test ngắn.
- [ ] Có chính sách dung lượng/bảo mật JFR và kế hoạch rollback.
- [ ] Dùng các công cụ/flag còn hỗ trợ trong JDK hiện tại.

## Tài liệu chính thức

- Oracle Java SE 25, **The java Command** — `-XX:StartFlightRecording`, `settings`, `dumponexit`, JVM options: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- Oracle Java SE 25, **The jcmd Command** — `JFR.check`, `JFR.start`, `JFR.dump`, `JFR.stop`, `VM.flags`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html
- Oracle Java SE 25, **The jfr Command** — `jfr summary`/`print`/`configure`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html
- Oracle Java SE 25, **Troubleshoot Performance Issues Using Flight Recorder** — overhead tùy app, events, threshold: https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle Java SE 24, **Flight Recorder Configurations** — `default.jfc`/`profile.jfc`: https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html
- Official Java Developer, **Configuring the JDK Flight Recorder**: https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/
- Oracle Java SE 25, **GarbageCollectorMXBean**: https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html
