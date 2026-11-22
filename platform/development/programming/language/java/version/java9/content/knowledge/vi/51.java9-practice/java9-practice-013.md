# Đọc log JVM và đo tác động của thay đổi trên dữ liệu đại diện — Java 9+

## 1. Mục tiêu thực hành

Sau khi sửa thuật toán, cấu trúc dữ liệu, cấu hình JVM hoặc cách quản lý bộ nhớ, câu hỏi không phải chỉ là **“chương trình có chạy nhanh hơn không?”**. Cần kiểm tra đồng thời:

1. **Đúng chức năng:** baseline và phiên bản thay đổi cho cùng kết quả khi xử lý cùng dữ liệu.
2. **Hiệu năng đầu cuối:** thời gian hoàn thành tác vụ, throughput và độ trễ phân vị có cải thiện không.
3. **Chi phí tài nguyên:** CPU, cấp phát bộ nhớ, heap, GC và pause có thay đổi bất lợi không.
4. **Điều kiện thử nghiệm:** kích cỡ, phân bố và dữ liệu có đại diện cho tình huống ứng dụng sẽ gặp không.
5. **Khả năng giải thích:** các dòng **JVM log/JFR** có ủng hộ giả thuyết nguyên nhân chậm không, hay chỉ là hiện tượng trùng thời điểm.

Từ **Java 9**, JVM có **Unified Logging** với tùy chọn `-Xlog` để ghi các nhóm sự kiện như GC, safepoint, nạp lớp và môi trường runtime. Đây vẫn là công cụ chuẩn trong JDK hiện hành. **Java Flight Recorder (JFR)**, `jcmd` và bộ công cụ `jfr` cũng còn được duy trì trong JDK hiện đại. Bài ưu tiên **JDK 17+** để ví dụ biên dịch/chạy trực tiếp, tránh hướng dẫn các cờ logging cũ không nên dùng cho dự án mới.

> **Điểm cần nhớ:** log là bằng chứng kỹ thuật về hoạt động JVM; **không phải phép đo hiệu năng duy nhất**. Một biến thể có ít GC hơn chưa chắc nhanh hơn, và một kết quả thử nghiệm một lần trên dữ liệu nhân tạo chưa đủ để kết luận về hệ thống thực.

## 2. Lập giả thuyết và tiêu chí đánh giá trước khi chạy

Tình huống minh họa: ứng dụng phải kiểm tra hàng nghìn mã định danh có thuộc một tập hợp đã biết hay không.

- **Baseline A:** lưu dữ liệu trong `ArrayList<String>`, tìm mỗi truy vấn bằng `List.contains`. Trung bình phải so sánh nhiều phần tử; độ phức tạp tìm kiếm thường là O(n).
- **Candidate B:** xây một `HashSet<String>` từ cùng danh sách, kiểm tra bằng `Set.contains`. Thường gần O(1) trung bình với hàm băm/phân phối phù hợp, nhưng tốn thêm bộ nhớ và thời gian xây index.
- **Giả thuyết:** nếu tập khóa không đổi và được tra cứu rất nhiều lần, xây `HashSet` trước có thể giảm thời gian xử lý batch truy vấn.
- **Ràng buộc:** hai cách phải trả **cùng số lần tìm thấy**, xử lý cùng tập input, không được bỏ qua bước tính toán hoặc trả kết quả giả.
- **Trade-off:** ví dụ đo **chi phí tra cứu sau khi tập dữ liệu đã được xây xong**, chưa tính chi phí xây set. Với workload chỉ có một truy vấn, có nhiều cập nhật liên tục, hoặc thiếu bộ nhớ, chưa chắc nên chọn B.

### Dữ liệu “đại diện” là gì?

Dữ liệu đại diện phải tương thích về **quy mô, phân bố, hành vi và môi trường** với workload thực tế, không chỉ có thật nhiều phần tử. Cần xác định tối thiểu:

| Thuộc tính | Cần ghi nhận | Bộ dữ liệu minh họa |
| --- | --- | --- |
| Số phần tử trong tập tra cứu | Kích thước nhỏ/vừa/lớn, số phần tử duy nhất, tần suất cập nhật. | 4.000 mã duy nhất. |
| Số truy vấn | Số truy vấn mỗi request/batch, tốc độ sinh truy vấn, số lần tái sử dụng index. | 12.000 truy vấn mỗi batch. |
| Tỷ lệ tìm thấy | Truy vấn trúng/miss có thể có chi phí khác nhau. | Sinh gần 40% hit / 60% miss bằng seed cố định. |
| Độ dài/kiểu khóa | Chuỗi ngắn/dài, Unicode, phân phối hash, khả năng đụng hash. | Chuỗi ASCII `id-N` ngắn. |
| Phân bố lặp lại | Hot keys hay truy cập đều, tuần tự hay ngẫu nhiên. | Chọn ngẫu nhiên đều trong miền. |
| Tính đồng thời | Số thread/request cùng lúc, khóa, contention, saturation. | **Một thread**, chưa mô phỏng production concurrency. |
| Giới hạn runtime | JDK/vendor/version, CPU quota, memory limit, GC, OS/container. | Cùng JVM, `-Xms128m -Xmx128m` khi đối chiếu. |
| Chỉ số chấp nhận | Kết quả đúng, median/p95 latency, throughput, memory, CPU, GC. | Batch time và GC đếm thời gian trong phép thử. |

Bộ input demo là **synthetic, có thể lặp lại**, **chưa mặc nhiên đại diện cho production**. Khi áp dụng thực tế hãy dùng dữ liệu đã được ẩn danh/khử thông tin cá nhân, tái tạo phân bố độ dài khóa, hit/miss, hot-key, kích thước và tính đồng thời từ telemetry thật.

## 3. Unified JVM Logging: đọc `-Xlog` đúng cú pháp

Cú pháp khái quát trong JDK hiện hành:

```text
-Xlog[:what[:output[:decorators[:output-options]]]]
```

| Thành phần | Tác dụng | Ví dụ |
| --- | --- | --- |
| `what` | Chọn tag và mức log. | `gc=info`, `gc*=info`, `safepoint=info`. |
| `output` | Nơi ghi; mặc định stdout. | `stdout`, `stderr`, `file=baseline-gc.log`. |
| `decorators` | Thời gian, cấp độ, tag, PID… hiển thị đầu mỗi dòng. | `time,uptime,level,tags`. |
| `output-options` | Giới hạn kích thước/rotation, v.v. | `filecount=3,filesize=5M`. |

Lệnh xem **tag và cấp độ được JVM đang dùng hỗ trợ**:

```bash
java -Xlog:help
```

Các level thường dùng: `error`, `warning`, `info`, `debug`, `trace`, `off`. Tag không phải API có định dạng sự kiện cố định bất biến: thông điệp chi tiết có thể khác tùy JDK, bộ thu gom GC và môi trường.

### 3.1. Tag chính xác và wildcard

- `-Xlog:gc=info` chọn sự kiện với tag-set **đúng bằng `gc`** ở level info trở lên.
- `-Xlog:gc*=info` chọn các tag-set **có chứa `gc`** (ví dụ `gc,heap`, `gc,init`), nhờ wildcard `*`.
- `-Xlog:gc*,safepoint=info` là **hai selector cách nhau bằng dấu phẩy**: log các tag-set chứa `gc` và các tag-set có đúng tag `safepoint` ở mức info.
- `-Xlog:gc+heap=debug` chọn sự kiện có **đồng thời** hai tag `gc` và `heap` (không phải hoặc).
- `-Xlog:class+load=info` giúp xem các lớp được nạp; `-Xlog:os+container=info` hữu ích khi cần chẩn đoán cấu hình container theo khả năng hỗ trợ của platform/JDK.

Không nhầm dấu `+` (cùng một tag-set), dấu `,` (nhiều lựa chọn), và `*` (match tag-set chứa các tag được chọn).

### 3.2. Ghi log tách khỏi kết quả chương trình

Lệnh chuẩn cho bài này:

```bash
java -Xms128m -Xmx128m \
  '-Xlog:gc*,safepoint=info:file=baseline-gc.log:time,uptime,level,tags:filecount=3,filesize=5M' \
  JvmImpactLab list 4000 12000 42
```

- `-Xms128m -Xmx128m` cố định heap ban đầu/tối đa trong thử nghiệm, để A/B có điều kiện cùng phạm vi. **Không** khuyến nghị 128 MB cho mọi dịch vụ.
- `file=...` đưa log JVM vào file, để stdout của chương trình không bị trộn với sự kiện GC.
- `time` là thời gian theo đồng hồ, `uptime` là thời gian từ lúc JVM khởi động; `level,tags` giúp đọc ngữ cảnh.
- `filecount=3,filesize=5M` giới hạn số file được rotation (kích cỡ xấp xỉ). **Chú ý**: file đã tồn tại có thể bị ghi đè khi cấu hình output trùng tên; đặt tên theo lần chạy nếu cần lưu lịch sử.
- Với **Windows PowerShell**, đặt toàn bộ lệnh trên **một dòng** và giữ phần `-Xlog:...` trong dấu nháy đơn như ví dụ; trong Bash/Zsh dấu `\` cuối dòng mới là ký hiệu tiếp dòng.

Nếu chỉ muốn xem GC trên terminal:

```bash
java -Xlog:gc=info -version
```

Chương trình không cần thay đổi source để bật logging vì đây là **cấu hình lúc khởi động JVM**. Mức `trace` có thể sinh rất nhiều log và ảnh hưởng kết quả; không bật rộng trên production chỉ để đo tốc độ.

### 3.3. Đọc một dòng GC thật

Ví dụ đã quan sát khi kiểm thử trên OpenJDK 24.0.2 với G1:

```text
[0.038s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 35M->1M(64M) 0.598ms
```

Phân tích:

| Đoạn | Diễn giải |
| --- | --- |
| `[0.038s]` | Khoảng 38 ms từ lúc JVM khởi động (**uptime**, không phải thời gian xử lý request). |
| `[info][gc]` | Level info và tag `gc`. |
| `GC(0)` | Mã sự kiện GC giúp ghép các dòng liên quan đến cùng một đợt. |
| `Pause Young ...` | Loại collection/pause do collector báo, **không** có nghĩa mọi GC trên JDK khác giống hệt. |
| `35M->1M(64M)` | Heap used xấp xỉ trước/sau GC; 64 MB là **heap capacity được báo**, không phải RSS của toàn bộ tiến trình. |
| `0.598ms` | Thời lượng pause của sự kiện đó theo định dạng collector/log, không phải latency đầu cuối của request. |

**Không cộng bừa mọi dòng chứa `GC(0)`**: với `gc*`, các dòng `gc,phases`/`gc,heap`/`gc,cpu` có thể cùng mô tả các pha của **một** đợt GC. Cần biết loại event và định dạng bản JDK đang dùng trước khi đếm/đo pause. Nếu log không có GC pause trong đoạn đo thì không tự kết luận “không hề có allocation”; có thể các object được cấp phát trước đoạn đo hoặc chưa gây collection.

### 3.4. Những trường khác thường xuất hiện

| Nhóm sự kiện | Có thể rút ra điều gì | Không được tự kết luận |
| --- | --- | --- |
| `gc,init` | JVM dùng collector gì, thông số heap, CPU/memory mà JVM thấy. | Không đồng nghĩa OS/VM có tất cả tài nguyên đó sẵn cho ứng dụng. |
| `gc` | Những collection/pause được ghi với thời lượng và biến động heap. | Không trực tiếp chỉ ra method nào cấp phát nhiều nhất. |
| `gc,heap` | Thông tin heap/generation/region tùy collector. | Không phải tổng RSS/native memory của tiến trình. |
| `gc,cpu` | CPU time mà collector ghi nhận theo pha. | Không thể thay thước đo CPU toàn ứng dụng. |
| `safepoint` | Các sự kiện đưa thread đến safepoint, thời gian liên quan. | Không được đồng nhất mọi safepoint là GC. |
| `class,load` | Những class được nạp và nguồn theo JDK. | Không suy ra đây là nguyên nhân chậm khi thiếu đối chiếu. |
| `os,container` | Một phần thông tin giới hạn tài nguyên/container. | Không bảo đảm chính sách cgroup/OS tương tự trên mọi máy. |

JVM log là **nguồn chẩn đoán**, không phải format JSON ổn định. Khi muốn phân tích tự động, dùng parser tương thích với chính kiểu GC/JDK và kiểm tra sample log; không viết regex bắt buộc mọi JVM phải có cùng wording.

## 4. Chương trình đo A/B Java 17+: hai thuật toán, một bộ dữ liệu

Lưu **`JvmImpactLab.java`**. Chương trình có ba yếu tố để giữ phép thử kiểm chứng được:

- `SplittableRandom(seed)` sinh **cùng chuỗi query** cho mỗi process A và B.
- `expectedHits` đối chiếu kết quả tìm kiếm, phát hiện biến thể trả sai.
- Có warmup, 7 vòng đo nguyên batch và lưu giá trị vào `volatile sink`; dùng `System.nanoTime()` đo khoảng thời gian trong cùng process.

Đây là **bài thực hành đo cấp batch**, không phải JMH microbenchmark dùng để công bố hiệu năng. Nó không mô phỏng network, cơ sở dữ liệu, nhiều thread hoặc phân bố request thực tế.

### 4.1. Source hoàn chỉnh

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.SplittableRandom;

public final class JvmImpactLab {
    private static final int WARMUP = 3;
    private static final int ROUNDS = 7;
    private static volatile long sink;

    private JvmImpactLab() {}

    public static void main(String[] args) {
        if (args.length != 4 || (!args[0].equals("list") && !args[0].equals("set"))) {
            throw new IllegalArgumentException(
                    "Usage: java JvmImpactLab list|set keys queries seed");
        }
        String mode = args[0];
        int keys = Integer.parseInt(args[1]);
        int count = Integer.parseInt(args[2]);
        long seed = Long.parseLong(args[3]);
        if (keys <= 0 || keys > 100_000 || count <= 0) {
            throw new IllegalArgumentException("Invalid dataset size");
        }

        List<String> items = new ArrayList<>(keys);
        for (int i = 0; i < keys; i++) {
            items.add("id-" + i);
        }
        Set<String> index = new HashSet<>(items);
        String[] queries = new String[count];
        SplittableRandom random = new SplittableRandom(seed);
        long expectedHits = 0;
        for (int i = 0; i < count; i++) {
            boolean hit = random.nextInt(10) < 4;
            int indexInDomain = random.nextInt(keys) + (hit ? 0 : keys);
            queries[i] = "id-" + indexInDomain;
            if (hit) {
                expectedHits++;
            }
        }

        long[] sampleNanos = new long[ROUNDS];
        long gcBefore = -1;
        long gcTimeBefore = -1;
        long gcAfter = -1;
        long gcTimeAfter = -1;
        for (int pass = 0; pass < WARMUP + ROUNDS; pass++) {
            if (pass == WARMUP) {
                gcBefore = gcCount();
                gcTimeBefore = gcTime();
            }
            long start = System.nanoTime();
            long hits = 0;
            for (String query : queries) {
                if (mode.equals("list") ? items.contains(query) : index.contains(query)) {
                    hits++;
                }
            }
            long elapsed = System.nanoTime() - start;
            if (hits != expectedHits) {
                throw new AssertionError("Mismatch: " + hits + " vs " + expectedHits);
            }
            sink = hits;
            if (pass >= WARMUP) {
                sampleNanos[pass - WARMUP] = elapsed;
            }
        }
        gcAfter = gcCount();
        gcTimeAfter = gcTime();
        Arrays.sort(sampleNanos);
        long median = sampleNanos[sampleNanos.length / 2];
        long p95Batch = sampleNanos[
                (int) Math.ceil(sampleNanos.length * 0.95) - 1];
        System.out.printf(Locale.ROOT,
                "mode=%s keys=%d queries=%d seed=%d hits=%d misses=%d%n",
                mode, keys, count, seed, expectedHits, count - expectedHits);
        System.out.printf(Locale.ROOT,
                "median_batch_ms=%.3f p95_batch_ms=%.3f%n",
                median / 1_000_000.0, p95Batch / 1_000_000.0);
        System.out.printf(Locale.ROOT,
                "gc_count_delta=%d gc_time_ms_delta=%d%n",
                gcAfter - gcBefore, gcTimeAfter - gcTimeBefore);
        System.out.println("checksum=" + sink);
    }

    private static long gcCount() {
        long count = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionCount();
            if (value >= 0) count += value;
        }
        return count;
    }

    private static long gcTime() {
        long millis = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionTime();
            if (value >= 0) millis += value;
        }
        return millis;
    }
}
```

**Giải thích phép đo:**

1. Tạo 4.000 ID duy nhất từ `id-0` đến `id-3999`. Tập truy vấn có cả ID trúng và ID ngoài phạm vi; `seed=42` giữ input nhất quán.
2. Tạo `ArrayList` và `HashSet` **trước** khi đo. Điều này cố tình đo phần **lookup-only**. Để đánh giá đầy đủ chi phí candidate B, phải đo riêng thời gian/heap xây set và vòng đời cập nhật.
3. `WARMUP=3` để JVM có cơ hội JIT/khởi tạo lazy trước các vòng mẫu; **3 lần không bảo đảm JIT đã ổn định**.
4. `ROUNDS=7` tạo 7 duration của **toàn batch 12.000 truy vấn**. Median và “p95 batch” được tính sau khi sort; với chỉ 7 mẫu, chỉ số p95 này chính là giá trị lớn nhất và **rất thiếu ổn định**. Nó **không** là p95 latency của từng request.
5. `gcCount()/gcTime()` dùng `GarbageCollectorMXBean` đọc chênh lệch số lần/thời gian GC được implementation cung cấp. Những số này có thể bằng 0 ngay cả khi đã cấp phát đối tượng; chúng không thay CPU profiler và không bảo đảm cộng được thời gian của các collector concurrent thành tổng pause chính xác.

### 4.2. Biên dịch

Trong thư mục có `JvmImpactLab.java`:

```bash
javac -encoding UTF-8 --release 17 JvmImpactLab.java
```

### 4.3. Chạy baseline và candidate trong hai JVM riêng

Dùng cùng JDK, seed, heap và cấu hình logging:

```bash
java -Xms128m -Xmx128m \
  '-Xlog:gc*,safepoint=info:file=baseline-gc.log:time,uptime,level,tags:filecount=3,filesize=5M' \
  JvmImpactLab list 4000 12000 42

java -Xms128m -Xmx128m \
  '-Xlog:gc*,safepoint=info:file=candidate-gc.log:time,uptime,level,tags:filecount=3,filesize=5M' \
  JvmImpactLab set 4000 12000 42
```

**Windows PowerShell (mỗi lệnh một dòng):**

```powershell
java -Xms128m -Xmx128m '-Xlog:gc*,safepoint=info:file=baseline-gc.log:time,uptime,level,tags:filecount=3,filesize=5M' JvmImpactLab list 4000 12000 42
java -Xms128m -Xmx128m '-Xlog:gc*,safepoint=info:file=candidate-gc.log:time,uptime,level,tags:filecount=3,filesize=5M' JvmImpactLab set 4000 12000 42
```

**Kết quả kiểm thử thực tế trên một lượt chạy OpenJDK 24.0.2/Windows, biên dịch `--release 17`:**

```text
# Baseline (list)
mode=list keys=4000 queries=12000 seed=42 hits=4753 misses=7247
median_batch_ms=40.159 p95_batch_ms=46.242
gc_count_delta=0 gc_time_ms_delta=0
checksum=4753

# Candidate (set)
mode=set keys=4000 queries=12000 seed=42 hits=4753 misses=7247
median_batch_ms=0.667 p95_batch_ms=1.011
gc_count_delta=0 gc_time_ms_delta=0
checksum=4753
```

Đây là **log kết quả quan sát được**, không phải stdout cố định trên mọi máy. Các giá trị **`keys/queries/seed/hits/misses/checksum`** là kết quả input cố định của demo; **time và GC delta thay đổi** theo JDK, CPU, scheduling, tập dữ liệu và tình trạng máy. Dấu comment trong khối kết quả chỉ để phân biệt hai lần chạy, chương trình thực không in hai dòng `# Baseline`/`# Candidate`.

Trong một lượt chạy này, median batch của B nhỏ hơn rõ rệt. Điều đó **phù hợp với giả thuyết** về tra cứu khi set đã xây xong, **không chứng minh** phiên bản B luôn nhanh hơn 60 lần trong sản phẩm thật. So sánh này chưa tính chi phí xây index, memory footprint, mutation, concurrency hay dữ liệu phân bố khác. Chênh lệch quan sát được cần lặp lại trên workload thật và nhiều JVM process.

## 5. Hướng dẫn đọc log theo hai lần chạy A/B

Trong thư mục đã chạy chương trình, mở `baseline-gc.log` và `candidate-gc.log`. Nếu môi trường Unix:

```bash
grep -E 'Using |GC\\(|safepoint' baseline-gc.log
grep -E 'Using |GC\\(|safepoint' candidate-gc.log
```

Windows PowerShell:

```powershell
Select-String -Path baseline-gc.log -Pattern 'Using ','GC\(','safepoint'
Select-String -Path candidate-gc.log -Pattern 'Using ','GC\(','safepoint'
```

**Cẩn thận với cách diễn giải:**

- Các dòng `[gc,init]` cho biết JVM nhận thấy bao nhiêu processor, heap khởi tạo thế nào và collector nào được chọn. Kiểm tra A/B có cùng cấu hình hoặc phân tích khác biệt có chủ đích.
- Nếu không có `GC(n) Pause...` trong đoạn đo, điều đó chỉ cho biết **không thấy event collection tương ứng** ở ngưỡng đã chọn. Tác vụ vẫn có thể cấp phát object mà chưa gây GC.
- Dòng GC ở `uptime=0.01s` là thời gian từ lúc start JVM, **không đồng nhất với cửa sổ đo `nanoTime` trong main**. Muốn đối chiếu chính xác phải thêm dấu mốc cho pha warmup/measurement, dùng JFR timestamps hoặc instrumentation.
- Một thay đổi giảm pause nhưng làm CPU tăng/throughput giảm không tự động là cải thiện. Phải nhìn tiêu chí mục tiêu (SLO) của ứng dụng.
- Tài liệu `-Xlog:help` trên chính JDK đang chạy là nguồn xác nhận tag và định dạng. Các collector/JDK có thể khác nhau về event.

**Kịch bản demo này** chủ yếu đo CPU lookup, ít cấp phát trong vòng đo. Vì vậy trên lần thử đã xuất hiện `gc_count_delta=0` ở cả hai biến thể; **đó là kết quả hợp lý**, không phải lỗi thiếu log.

## 6. Khi cần thấy GC thật: ví dụ cấp phát có kiểm soát

Để học cách nhận biết **pause và heap trước/sau GC** mà không phụ thuộc may rủi vào chương trình tra cứu ít allocation, chạy một ví dụ *riêng*. Đây là **tải nhân tạo chỉ nhằm quan sát log**, không phải workload đại diện cho production và không dùng nó để chứng minh cách nào nhanh hơn.

Lưu file **`GcLogDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GcLogDemo {
    public static void main(String[] args) {
        List<byte[]> live = new ArrayList<>(256);
        long checksum = 0;
        for (int i = 0; i < 25_000; i++) {
            byte[] block = new byte[16 * 1024];
            block[0] = (byte) i;
            live.add(block);
            if (live.size() == 256) {
                checksum += live.get(0)[0];
                live.clear();
            }
        }
        checksum += live.size();
        System.out.println("allocations=25000 checksum=" + checksum);
    }
}
```

Biên dịch/chạy với heap nhỏ **chỉ cho thí nghiệm**:

```bash
javac -encoding UTF-8 --release 17 GcLogDemo.java
java -Xms64m -Xmx64m \
  '-Xlog:gc=info:file=gc-demo.log:uptime,level,tags:filecount=2,filesize=5M' \
  GcLogDemo
```

**Stdout của mã đã kiểm thử:**

```text
allocations=25000 checksum=168
```

**Một vài dòng log quan sát được trên OpenJDK 24.0.2/G1 (minh họa, thời lượng không cố định):**

```text
[0.008s][info][gc] Using G1
[0.038s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 35M->1M(64M) 0.598ms
[0.040s][info][gc] GC(1) Pause Young (Normal) (G1 Evacuation Pause) 30M->1M(64M) 0.373ms
[0.046s][info][gc] GC(2) Pause Young (Normal) (G1 Evacuation Pause) 37M->5M(64M) 1.408ms
```

Phân tích kết quả: nhiều block byte[] mới được cấp phát, một nhóm nhỏ được giữ tạm rồi thả, làm GC có cơ hội xuất hiện khi heap 64 MB. Dòng `GC(0)` là một lần thu gom; `35M->1M` là thay đổi heap used, không phải “ứng dụng đã giải phóng 34 MB RAM vật lý”; `0.598ms` không phải thời gian trung bình của cả chương trình. Collector khác có tên event khác, và GC có thể xảy ra số lần khác tùy JDK/hardware. **Không dùng tăng áp lực GC kiểu này để “tối ưu” hệ thống thực**: chỉ nhằm học đọc log.

## 7. Java Flight Recorder (JFR): gắn quan sát với CPU, allocation, GC

Unified Logging hữu ích cho sự kiện JVM nhưng không cho đầy đủ **call stack của code gây allocation/hot method**. JFR là cơ chế ghi sự kiện profiling tích hợp trong JDK hiện đại. Dùng JFR để bổ sung: GC, allocation, CPU samples, locks, thread, I/O tùy settings và quyền truy cập. Vì sampling và threshold, **không phải mọi method/allocation đều xuất hiện**.

### 7.1. Ghi JFR ngay khi khởi động

Ví dụ cho chương trình đã biên dịch:

```bash
java -Xms128m -Xmx128m \
  '-XX:StartFlightRecording=filename=baseline.jfr,settings=profile,dumponexit=true' \
  JvmImpactLab list 4000 12000 42
```

Sau khi JVM thoát bình thường:

```bash
jfr summary baseline.jfr
jfr print --events jdk.GarbageCollection baseline.jfr
```

**Ý nghĩa:** `profile` bật thêm một số sự kiện so với cấu hình mặc định, `filename` chọn file, `dumponexit=true` xuất recording khi JVM thoát; `jfr summary` liệt kê loại event và số lượng. Với một chương trình chỉ chạy vài trăm mili giây, **JFR có thể thu được rất ít CPU samples**, khiến so sánh tỷ lệ CPU không đáng tin. Tăng độ dài/độ đại diện của workload, áp dụng nhiều lượt đo, hoặc profile ứng dụng đang chạy lâu hơn.

Nếu JFR ghi stack trace/đường dẫn/class name/SQL metadata, xem file như **dữ liệu vận hành có thể nhạy cảm**: lưu nơi được cấp quyền và có vòng đời xóa thích hợp. JFR có overhead, nên đo performance chính với chính sách instrumentation nhất quán giữa A và B; không chỉ bật JFR ở một phía.

### 7.2. Bật khi ứng dụng đang chạy qua `jcmd`

Với ứng dụng Java thực chạy lâu:

```bash
jcmd -l
jcmd <PID> help JFR.start
jcmd <PID> JFR.start name=impact settings=profile duration=60s filename=impact.jfr
jcmd <PID> JFR.check
```

`<PID>` là **ký hiệu phải thay bằng PID hợp lệ** từ `jcmd -l`; các dòng này là **cú pháp tích hợp vào môi trường có process đang chạy**, không phải lệnh độc lập có thể chạy nguyên văn. `jcmd` thường cần cùng máy/quyền user và JVM cho phép attach. Không thực hiện trên tiến trình production nếu chưa được cấp phép vì profiling/logging có chi phí và rủi ro lộ thông tin.

Unified Logging cũng có thể điều chỉnh runtime qua lệnh **`jcmd <PID> VM.log`**. Trước khi thay đổi, dùng:

```bash
jcmd <PID> help VM.log
jcmd <PID> VM.log list
```

Lưu ý tùy phiên bản JDK, cách đặt output/selector và quyền thao tác có thể thay đổi; dùng phần help thực tế của JVM để cấu hình. Nếu không cần phân tích production, ưu tiên bật `-Xlog` từ startup trong môi trường kiểm thử để A/B có cùng cấu hình.

### 7.3. JFR và GC log bổ sung cho nhau

| Câu hỏi | JVM Unified Logging | JFR / profiler |
| --- | --- | --- |
| JVM đã khởi động với GC nào? | `-Xlog:gc*,gc+init=info` hoặc `-Xlog:gc*=info`. | Event cấu hình JVM/GC khi được bật. |
| GC nào đã xảy ra và pause bao lâu? | Các dòng `GC(n) Pause...`, tag `gc`. | `jdk.GarbageCollection`, GC phases theo event settings. |
| Method nào tiêu CPU? | Không phải chức năng chính của `-Xlog:gc`. | CPU sampling/profiling, cần workload đủ dài. |
| Object nào gây allocation? | Heap/GC logs chủ yếu chỉ cho mức tổng hợp. | Allocation events/call stack có thể cung cấp manh mối. |
| Lock contention/thread state? | Một số tag JVM có thể hỗ trợ chẩn đoán. | Các sự kiện lock/thread tùy configuration. |
| Hệ thống có đạt latency SLO không? | Không đủ, cần metric end-to-end. | JFR bổ trợ, nhưng cần đo latency ở tầng ứng dụng. |

**Không lấy việc có JFR event làm bằng chứng nhân quả**: cần gắn event với khoảng thời gian workload, tái lập kết quả và kiểm soát biến khác.

## 8. Đo “tác động của thay đổi” đúng phương pháp

Một workflow kỹ thuật thực dụng:

### Bước 1 — Định nghĩa câu hỏi trước khi chạy

Ví dụ: “Thay cách tra cứu ID từ `List.contains` sang `HashSet.contains` có giảm median thời gian xử lý batch trên 4.000 key và 12.000 query, trong khi kết quả đúng và chi phí xây index/memory chấp nhận được không?”

Viết trước **điều kiện chấp nhận**: số hit/miss và checksum khớp, median giảm rõ trong nhiều lượt, heap không vượt budget, không làm p95 request/SLO xấu đi.

### Bước 2 — Chọn dataset đại diện

- Dùng snapshot được ẩn danh, hoặc synthetic với **phân bố mô phỏng thực tế** (độ dài key, tỷ lệ hit, hot keys, skew, cập nhật).
- Tạo **test matrix** cho dữ liệu nhỏ/vừa/lớn, nhiều/một thread, tỷ lệ miss 0%/50%/90% khi phù hợp.
- Giữ input giống nhau giữa A và B: cùng seed/dataset version, số request, bước nghiệp vụ.
- Tránh dữ liệu luôn là trường hợp thuận lợi nhất: `HashSet` thường thắng về lookup nhưng có chi phí index và RAM; cần đưa cả khởi tạo/lifecycle vào bài toán khi đáng kể.

### Bước 3 — Kiểm soát môi trường và chỉ thay một biến

Cùng máy/CPU quota/OS/JDK/GC/heap, không chạy tác vụ gây nhiễu, không so sánh JDK 17 vs JDK 26 cùng lúc với việc đổi thuật toán. Ghi rõ `java -version`, cấu hình startup, số worker thread, giới hạn container và dataset hash. Khi cần đánh giá tác động của **đổi GC**, giữ code/dữ liệu không đổi và thay đúng cấu hình GC.

### Bước 4 — Warm-up và nhiều phép lặp độc lập

JIT compilation, class loading, allocation, OS page cache và clock throttling có thể làm lần đầu khác nhiều so với steady-state. Demo có **3 warmup + 7 batch samples** để học phương pháp, **chưa đủ** để kết luận robust. Trong kiểm thử nghiêm túc:

- Tăng thời gian warmup cho phù hợp; kiểm tra JIT/steady state nếu đo operation nhỏ.
- Chạy nhiều **JVM process độc lập** (forks), không chỉ lặp rất nhiều vòng trong một process.
- Cân bằng thứ tự chạy `A-B-B-A` hoặc thứ tự ngẫu nhiên để giảm bias do máy nóng/tải môi trường.
- Lưu **cả phân bố**, ít nhất median/min/max và p95/p99 khi có đủ số request mẫu thật; so sánh variability, không chỉ một con số đẹp.
- Với microbenchmark về throughput/latency per-op của Java code, ưu tiên **JMH** (Java Microbenchmark Harness) thay vì tự viết `for` loop; JMH quản lý warmup, measurement, forks, dead-code elimination và nhiều sai lệch phổ biến tốt hơn bài demo này.

### Bước 5 — Quan sát nhiều trục đo

| Chỉ số | Nguồn quan sát | Cách hiểu đúng |
| --- | --- | --- |
| Correctness/checksum | Test/đầu ra của workload | **Phải khớp** trước khi so sánh tốc độ. |
| Batch wall time | `System.nanoTime()` đo cùng pha | Thời gian trôi qua cho toàn batch, không phải CPU time. |
| Throughput | Số yêu cầu thành công / thời gian | Chỉ có ý nghĩa với tải và concurrency giống nhau. |
| Request latency p50/p95/p99 | Application metrics (nhiều request thật) | Không thay bằng “p95” của 7 **batch durations**. |
| GC pause | `-Xlog:gc`/JFR GC events | Thời gian pause từng event/pha; chú ý tag và collector. |
| GC count/time delta | `GarbageCollectorMXBean` | Số liệu tổng hợp/ước lượng, có thể không báo hết GC concurrent/pause. |
| CPU, allocation hotspots | JFR, profiler, OS metrics | Tương quan với pha thử nghiệm, có overhead và sampling. |
| Heap used vs RSS | GC log, heap telemetry vs OS/process metrics | Heap chỉ là một phần bộ nhớ process. |
| Khởi tạo index | `nanoTime` quanh xây set + heap metric | Quan trọng nếu tạo set thường xuyên; demo lookup-only chưa bao gồm. |

### Bước 6 — Viết kết luận có điều kiện

Mẫu kết luận tốt:

> “Trên JDK X, CPU quota Y, heap Z, bộ dataset version D (N key, Q query, phân bố H/M), phiên bản B giữ nguyên kết quả, giảm median batch wall time trong R JVM forks. GC log không chỉ ra GC là nút thắt ở pha đo; vì build index và memory footprint chưa được tính, **chỉ kết luận cho tra cứu trên tập đã dựng**, chưa ngoại suy sang request/production.”

Khi hai đường đo chồng lấn mạnh, khác biệt nhỏ hơn nhiễu hoặc correctness không khớp, kết luận **chưa đủ bằng chứng**; không “chọn số tốt nhất” từ nhiều lượt để tạo cảm giác có cải thiện.

## 9. Tính mức cải thiện có đơn vị rõ ràng

Nếu đo thời gian cho **cùng lượng công việc** (cùng số truy vấn, cùng kết quả):

```text
speedup = median_baseline_ms / median_candidate_ms
time_reduction_% = (median_baseline_ms - median_candidate_ms)
                   / median_baseline_ms * 100
```

Từ **một lượt thử minh họa** ở mục 4:

```text
baseline median batch = 40.159 ms
candidate median batch =  0.667 ms

speedup ≈ 60.2×
time reduction ≈ 98.3%
```

Các phép tính này mô tả **lượt chạy cụ thể trên máy thử**, không phải kỳ vọng chung cho Java. Cần đối chiếu variance, nhiều process, chi phí xây index, memory và workload thật. Với latency end-to-end, cải thiện một phần lookup không đảm bảo thời gian request giảm cùng tỷ lệ (network, DB, serialization và các khâu khác có thể chi phối).

**Không dùng phần trăm cải thiện nếu hai workload khác nhau**: 1000 request ở baseline và 1200 request ở candidate, hoặc khác tỷ lệ hit, không thể so trực tiếp thời gian batch rồi gán nguyên nhân cho code.

## 10. Bẫy thường gặp khi đọc log và đo hiệu năng

| Dấu hiệu | Sai lầm phổ biến | Hướng xử lý |
| --- | --- | --- |
| Log chứa `Using G1` nhưng không có `GC(n) Pause` | Kết luận JVM không hề cấp phát. | Không có GC event không chứng minh không allocation; dùng JFR allocation/heap telemetry và workload lâu hơn. |
| `gc_count_delta=0` trong chương trình | Tin rằng JVM “không có vấn đề memory”. | Chỉ là collector không báo collection trong cửa sổ đo; kiểm tra RAM, allocation rate và memory lifecycle riêng. |
| Thấy `35M->1M(64M)` | Đồng nhất 64M với toàn bộ RSS. | Đó là heap capacity, chưa tính code cache, metaspace, thread stacks, direct/native memory. |
| Thấy `0.598ms` trong log | Kết luận mỗi request có latency 0.598ms. | Đây là một pause event của GC, không phải request latency. |
| Dùng `-Xlog:gc` mà thiếu dòng `[gc,heap]` | Cho rằng JVM không có heap metrics. | `gc` không tự match `gc,heap`; dùng `gc*` hoặc selector phù hợp khi cần. |
| Mức log `trace` chậm hơn nhiều | Quy toàn bộ chênh lệch cho thuật toán. | Chi phí I/O/log có thể gây nhiễu; giữ logging A/B giống nhau, chọn mức vừa đủ. |
| A nhanh hơn B ở lượt đầu nhưng ngược ở lượt sau | Dựa vào cold start/JIT/scheduling. | Warmup, nhiều forks, luân phiên thứ tự chạy và báo cáo phân bố. |
| B nhanh hơn nhưng output/checksum khác A | So sánh hai công việc khác nhau. | Dừng kết luận hiệu năng; sửa sai chức năng trước. |
| `HashSet.contains` nhanh trong demo | Kết luận luôn tốt hơn `List.contains`. | Đưa chi phí xây set, RAM, cập nhật, key distribution và dữ liệu thật vào mô hình. |
| JFR trống CPU samples với chương trình rất ngắn | Cho rằng CPU không thực thi code. | Recording ngắn, sampling không đủ; kéo dài workload hoặc profile dịch vụ thực. |
| Chỉ lấy p95 trên 7 phép đo batch | Tưởng là p95 latency của 12.000 request. | Thống kê batch khác thống kê per-request; thu đủ request measurements cho SLO. |
| Khác số CPU/heap trong `gc,init` giữa hai lượt | Không kiểm soát container quota/hardware/JVM config. | Chuẩn hóa môi trường, ghi config hoặc nêu rõ biến khác biệt. |
| Dùng `System.currentTimeMillis()` cho microbenchmark | Độ phân giải/đồng hồ có thể thay đổi. | Dùng `System.nanoTime()` cho khoảng thời gian; JMH cho phép đo vi mô chính xác hơn. |
| So sánh GC log của hai JDK/collector bằng một regex cứng | Định dạng và loại event khác nhau. | Chọn parser phù hợp và giải thích sự kiện theo đúng bản JDK. |

## 11. Checklist thực hành hoàn chỉnh

1. **Biên dịch code demo:** `javac -encoding UTF-8 --release 17 JvmImpactLab.java`.
2. **Chạy cùng dataset** ở A (`list`) và B (`set`), cùng `keys=4000, queries=12000, seed=42`.
3. **Kiểm tra correctness:** hai kết quả phải cùng `hits=4753, misses=7247, checksum=4753`.
4. **Ghi và đọc Unified Log:** `baseline-gc.log`, `candidate-gc.log`; phân biệt `gc`, `gc,init` và `safepoint`.
5. **Đo đúng đơn vị:** median/p95 của **batch**, không đổi nhãn thành request p95.
6. **Chạy `GcLogDemo`** với heap 64 MB để thấy pause GC thực tế; đừng coi dữ liệu thử này là production.
7. **Thu JFR** khi cần tìm allocation/CPU hotspots; kéo dài workload đủ để profiler có mẫu.
8. **Lặp nhiều JVM forks** và cân bằng thứ tự thử A/B để giảm nhiễu.
9. **Đánh giá trade-off:** thời gian xây set, memory footprint, cập nhật và cạnh tranh nhiều thread; kiểm tra trên bộ dữ liệu có phân bố thực.
10. **Viết kết luận có điều kiện** cùng JDK/GC, input, môi trường, số lần lặp, phạm vi đo và các giới hạn đã biết.

## 12. Câu hỏi ôn tập

1. **Vì sao `-Xlog:gc` khác `-Xlog:gc*`?**  
   `gc` chỉ khớp tag-set chính xác; `gc*` khớp các tag-set **chứa gc**, bao gồm những dòng mang tag phụ như `gc,init` hoặc `gc,heap`.

2. **`GC(0) 35M->1M(64M) 0.598ms` nói được gì?**  
   Một sự kiện GC được báo, heap used trước/sau và thời lượng event. Nó không đo RSS toàn process hay latency request.

3. **Vì sao hai biến thể phải in cùng checksum?**  
   Vì không thể kết luận hiệu năng khi hai phiên bản cho kết quả khác nhau hoặc không xử lý cùng công việc.

4. **Một lượt đo cho thấy B nhanh gấp 60 lần. Có nên công bố ngay không?**  
   Không. Cần nhiều lượt và workload đại diện, kiểm soát JIT/forks/CPU, xem chi phí xây set/RAM, xác minh đúng chức năng và báo khoảng biến thiên.

5. **`gc_count_delta=0` có nghĩa không cấp phát?**  
   Không. JVM có thể đã cấp phát mà chưa cần chạy collection trong khoảng đo.

6. **JFR dùng khi nào?**  
   Khi cần tìm CPU/allocation/lock/GC event có chiều sâu hơn `-Xlog`, với recording đủ dài, quyền hợp lệ và đánh giá overhead.

7. **Khi cần latency p95 của request, có thể dùng p95 của 7 vòng batch không?**  
   Không. Phải đo nhiều request thực với phân bố latency tương ứng.

8. **Thay đổi nào có thể làm A/B không còn công bằng?**  
   Khác JDK, GC, heap, quota CPU, seed, size, tỷ lệ hit/miss, concurrency, trạng thái máy, logging/profiling hoặc phần công việc được tính thời gian.

## 13. Tài liệu chính thức và công cụ được duy trì

- [Java SE 26 — `java` command, JVM Unified Logging](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): cú pháp `-Xlog`, tags, levels, decorators, rotation, log GC và cách cấu hình hiện hành.
- [Java SE 26 — `jcmd`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): `VM.log`, `JFR.start`, `JFR.dump`, `JFR.check` khi chẩn đoán JVM đang chạy.
- [Java SE 26 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): `getCollectionCount()`, `getCollectionTime()`, giới hạn ý nghĩa của số liệu quản lý JVM.
- [Java SE 26 — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html#nanoTime()): phép đo khoảng thời gian có độ phân giải cao, không phải mốc wall-clock.
- [OpenJDK JMH](https://github.com/openjdk/jmh): harness hiện hành cho phép đo microbenchmark nghiêm túc với warmup, forks và các cơ chế giảm sai lệch.
