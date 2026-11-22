# Thực hành đánh giá G1 NUMA hoặc ánh xạ NVM khi có môi trường phù hợp

## 1. Mục tiêu, phạm vi và điều kiện tiên quyết

Java 14 bổ sung hai cải tiến liên quan tới **vị trí vật lý của bộ nhớ**, nhưng giải quyết **hai bài toán độc lập**:

1. **JEP 345 — NUMA-Aware Memory Allocation for G1:** giúp bộ gom rác **G1** khai thác tính cục bộ bộ nhớ trên máy có **Non-Uniform Memory Access (NUMA)** để giảm truy cập bộ nhớ từ xa trong những workload phù hợp.
2. **JEP 352 — Non-Volatile Mapped Byte Buffers:** cung cấp hai chế độ ánh xạ tệp đặc thù của JDK qua module **`jdk.nio.mapmode`** để ứng dụng làm việc với tệp được hỗ trợ bởi **bộ nhớ không mất dữ liệu (NVM/persistent memory)** khi hệ điều hành và filesystem cho phép.

**Đề bài thực hành:** đánh giá **G1 NUMA hoặc NVM mapping** khi có máy phù hợp. Không buộc phải có **cả hai loại phần cứng**. Đây là bài đánh giá hiệu năng có điều kiện, không phải bài khẳng định “Java 14 luôn nhanh hơn”.

**Chỉ giữ kiến thức hiện hành:** Những tính năng này vẫn được nhắc tới và hỗ trợ trong các JDK hiện đại. Ví dụ Java dùng **`javac --release 17`**, không dùng preview API hay cờ logging GC lỗi thời. JEP 345 được đưa vào JDK 14, còn `ExtendedMapMode` có từ JDK 14 và vẫn hiện diện trong JDK 17/21/25.

### Đầu ra học tập mong đợi

Sau bài thực hành, bạn có thể:

- Xác định hệ thống có **từ hai NUMA nodes khả dụng** hay không.
- So sánh **G1 với `UseNUMA` tắt/bật** trên cùng một JDK, workload và chính sách CPU/heap.
- Thu thập **throughput, latency, GC pauses và NUMA locality** thay vì chỉ nhìn một số đo thời gian.
- Xác định filesystem có thực sự hỗ trợ **NVM/DAX/MAP_SYNC** hay không.
- Thử ánh xạ `FileChannel.MapMode.READ_WRITE` và `ExtendedMapMode.READ_WRITE_SYNC`, gọi `MappedByteBuffer.force()` rồi xác minh dữ liệu.
- Biết khi nào nên **SKIP/UNSUPPORTED** thay vì báo PASS cho một hiệu năng chưa đo được.
- Viết báo cáo có **baseline, phương pháp, số lần chạy, biến kiểm soát và giới hạn kết luận**.

## 2. NUMA và NVM không phải cùng một thứ

| Khía cạnh | NUMA / G1 | NVM / mapped buffer |
| --- | --- | --- |
| Vấn đề chính | Chi phí truy cập RAM khác nhau theo CPU/node | Giữ dữ liệu qua mất điện nhờ persistent memory phù hợp |
| Thành phần Java | HotSpot G1 GC | `FileChannel`, `MappedByteBuffer`, `ExtendedMapMode` |
| Cấu hình | JVM option `-XX:+UseG1GC` và `-XX:+UseNUMA` | JPMS module `jdk.nio.mapmode` và map mode `READ_WRITE_SYNC` |
| Đòi hỏi nền tảng để đo đúng | Máy/VM có nhiều NUMA nodes và JVM hỗ trợ | OS, filesystem và thiết bị hỗ trợ ánh xạ NVM kiểu SYNC |
| Chỉ số ưu tiên | Throughput, p50/p95/p99, pause GC, local/remote allocation | ns/force, throughput, độ bền dữ liệu, tỷ lệ lỗi, read-back |
| Điều **không** hứa | Mọi ứng dụng đều nhanh hơn | Mọi file trên SSD đều là persistent-memory mapping |
| Khi thiếu điều kiện | Chạy smoke test, ghi **NOT_APPLICABLE** cho NUMA benchmark | Kiểm thử standard mapping, ghi **UNSUPPORTED** cho SYNC nếu bị từ chối |

**NUMA** là kiến trúc tổ chức bộ nhớ: CPU truy cập RAM gần node của mình thường nhanh hơn RAM thuộc node khác. RAM đó có thể vẫn là **volatile DRAM**. **NVM** là thuộc tính dữ liệu **không mất khi mất điện**; một hệ thống persistent memory có thể hoặc không có nhiều NUMA nodes.

Một ổ SSD dùng giao thức **NVMe** không mặc nhiên tương đương **NVM trực tiếp ánh xạ như RAM với DAX**. Không suy ra hỗ trợ `READ_WRITE_SYNC` chỉ vì đường dẫn thiết bị chứa chữ “nvme”.

## 3. Kiểm kê hệ thống trước khi chạy

### 3.1. Kiểm tra Java/JDK

Trên terminal:

```bash
java -version
javac -version
java -Xlog:help
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version
java --list-modules
```

Những câu cần trả lời:

- Đang chạy **HotSpot hoặc JVM khác**? Cờ `-XX` và cơ chế G1 NUMA trong bài dành cho **HotSpot có hỗ trợ**.
- JDK version, vendor và kiến trúc CPU là gì?
- GC được chọn có đúng G1 không?
- `-XX:+UseNUMA` có được JVM nhận và **thực sự kích hoạt** không? Không suy từ dòng command-line.
- Runtime có `jdk.nio.mapmode` không? **Có module không đồng nghĩa có NVM**.

Trên JDK tùy biến/`jlink`, module `jdk.nio.mapmode` hoặc `jdk.compiler` có thể đã bị loại. Không dùng sự tồn tại của một class làm bài test phần cứng.

### 3.2. Điều kiện cho G1 NUMA trên Linux

Một máy kiểm thử thích hợp thường là Linux nhiều socket/NUMA node với đủ RAM và quyền xem topology. Các lệnh tham khảo:

```bash
lscpu
lscpu -e=CPU,NODE
numactl --hardware
cat /sys/devices/system/node/online
```

`numactl` là công cụ hệ điều hành, có thể cần cài gói tương ứng theo distro. Nếu container/cgroup chỉ được phép sử dụng **một node** dù host có nhiều node, bài test không còn đại diện cho kịch bản nhiều NUMA nodes.

**Điều kiện tối thiểu để chấp nhận phép so sánh:** nhiều node memory khả dụng cho cùng một JVM, CPU được phân bố hợp lý, đủ bộ nhớ, JDK/collector có thực sự bật NUMA policy và các lần chạy cùng môi trường.

Trong một máy chỉ có một node, hoặc Windows với HotSpot đã **vô hiệu hóa NUMA support**, vẫn có thể chạy workload để kiểm chứng mã và GC logs, nhưng **không kết luận hiệu quả G1 NUMA**.

### 3.3. Điều kiện cho NVM/DAX

Trên Linux, cần xác minh **đường dẫn cụ thể** có phải tệp đặt trên filesystem hỗ trợ **DAX/MAP_SYNC** và thiết bị thích hợp hay không. Một số thông tin thu thập:

```bash
uname -a
findmnt -T /mnt/dax
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS
java --describe-module jdk.nio.mapmode
```

**`/mnt/dax` chỉ là đường dẫn ví dụ**: trên máy thật cần thay bằng mount được quản trị viên xác nhận hỗ trợ **fs-DAX**. Một tệp đặt trên `/tmp`, ổ SSD bình thường, tmpfs hoặc filesystem thiếu DAX có thể không hỗ trợ `MAP_SYNC`.

Không thử format/mount lại thiết bị NVM hoặc thay đổi filesystem của máy làm việc chỉ để chạy bài học. Phần hướng dẫn bên dưới **chỉ tạo file tạm trong thư mục đã được cho phép**, không đụng dữ liệu production.

## 4. G1 NUMA: Java 14 đã thay đổi gì và giới hạn ở đâu?

JEP 345 bổ sung **NUMA-aware memory allocation** cho G1, nhắm cải thiện sự gần nhau giữa luồng xử lý và những vùng heap memory được truy cập thường xuyên. Tính năng quan tâm đặc biệt tới **young generation** của G1, chẳng hạn Eden/Survivor, nơi rất nhiều đối tượng ngắn hạn được phân bổ và sao chép.

**Không hiểu sai:** “NUMA-aware” không có nghĩa **toàn bộ object luôn nằm ở node của thread tạo nó**, không có remote access nào, hoặc mọi old-generation region được quản lý y hệt. G1 còn phải cân bằng áp lực heap, GC pause, relocation, capacity, scheduling và cấu hình hệ thống.

Tính năng này phụ thuộc:

- Bản JVM/HotSpot và cách hỗ trợ `UseNUMA` trong phiên bản đang chạy.
- Số lượng **memory nodes thực sự khả dụng** cho process.
- Policy của kernel, process affinity và cpuset/mempolicy.
- Kích thước heap, áp lực phân bổ và phân bố luồng.
- Cách tác vụ sử dụng bộ nhớ (locality) và độ lớn working set.

Khi workload nhỏ đủ nằm trong bộ nhớ của một node, có thể **không thấy cải thiện**. Khi có remote memory access đáng kể và allocation phân bố trên nhiều nodes, tối ưu có cơ hội phát huy.

### `-XX:+UseNUMA` phải được xác minh sau khởi động

Hai cấu hình cần so:

```bash
java -XX:+UseG1GC -XX:-UseNUMA -version
java -XX:+UseG1GC -XX:+UseNUMA -version
```

Nhưng nhận option ≠ kích hoạt runtime. Trên hệ không có hỗ trợ NUMA, HotSpot có thể **chấp nhận flag nhưng vô hiệu hóa** sau khi kiểm tra OS/topology. Hãy xem **`-Xlog:gc+init=info`**, các dòng nói về `NUMA Support` và `-XX:+PrintFlagsFinal` trong điều kiện chạy thực tế.

Lệnh kiểm tra riêng:

```bash
java -XX:+UseG1GC -XX:+UseNUMA -Xlog:gc+init=info -version
```

Dòng `NUMA Support: Disabled` có nghĩa phép thử “NUMA bật” **không thực sự đang chạy chế độ mong muốn**, dù người thử truyền `-XX:+UseNUMA`. Trường hợp ấy kết quả nên đánh dấu **INVALID_COMPARISON/NOT_APPLICABLE**, không ghi rằng “bật NUMA không cải thiện hiệu năng”.

**Ghi chú về mặc định:** phiên bản JVM/collector có thể đặt mặc định `UseNUMA` khác nhau. Không dựa vào giả định “mặc định luôn tắt” hoặc “mặc định luôn bật”; trong benchmark hãy **chỉ định rõ cả `-XX:-UseNUMA` và `-XX:+UseNUMA`** rồi đối chiếu cấu hình được JVM thực tế chấp nhận.

## 5. Xây workload đa luồng có thể đo được

Bài dùng một chương trình Java 17+ tạo nhiều mảng `byte[]`, duy trì một số đối tượng còn sống trong từng thread và xuất checksum. Mục đích:

1. Tạo **áp lực phân bổ trên G1 young generation**.
2. Có thể thay đổi **số thread**, **số lần phân bổ/thread** và **kích thước object**.
3. Chống lỗi loại bỏ hoàn toàn workload bằng cách dùng dữ liệu mảng để tạo checksum.
4. Cố định các yếu tố chính cho lần chạy NUMA off/on.

**Đây là workload tổng hợp, không phải ứng dụng nghiệp vụ**. Nó cho thấy cách vận hành một benchmark có điều kiện, không tự bảo đảm kết quả đại diện cho mọi phần mềm Java.

### 5.1. Toàn bộ `G1NumaLoad.java`

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class G1NumaLoad {
    private static volatile long observed;

    static long phase(int threads, int allocationsPerThread, int arrayKiB)
            throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<Long>> tasks = new ArrayList<>();
            for (int thread = 0; thread < threads; thread++) {
                final int worker = thread;
                tasks.add(executor.submit(() -> {
                    ArrayDeque<byte[]> recent = new ArrayDeque<>();
                    long sum = 0;
                    start.await();
                    for (int i = 0; i < allocationsPerThread; i++) {
                        byte[] bytes = new byte[arrayKiB * 1024];
                        bytes[0] = (byte) (worker + i);
                        bytes[bytes.length - 1] = (byte) (i >>> 8);
                        sum += (bytes[0] & 255) + (bytes[bytes.length - 1] & 255);
                        recent.addLast(bytes);
                        if (recent.size() > 64) recent.removeFirst();
                    }
                    return sum + recent.size();
                }));
            }
            start.countDown();
            long result = 0;
            for (Future<Long> future : tasks) result += future.get();
            observed = result;
            return result;
        } finally {
            executor.shutdown();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: G1NumaLoad <threads> <allocationsPerThread> <arrayKiB>");
        }
        int threads = Integer.parseInt(args[0]);
        int count = Integer.parseInt(args[1]);
        int arrayKiB = Integer.parseInt(args[2]);
        if (threads < 1 || threads > 32 || count < 100 || count > 100_000
                || arrayKiB < 1 || arrayKiB > 64) {
            throw new IllegalArgumentException(
                    "Use threads=1..32, count=100..100000, arrayKiB=1..64");
        }
        phase(threads, Math.min(2_000, count), arrayKiB);
        long begin = System.nanoTime();
        long checksum = phase(threads, count, arrayKiB);
        long elapsedNs = System.nanoTime() - begin;
        System.out.println("threads=" + threads);
        System.out.println("allocations=" + ((long) threads * count));
        System.out.println("checksum=" + checksum);
        System.out.println("checksumValid=" + (checksum != 0 && observed == checksum));
        System.out.println("elapsedMs=" + (elapsedNs / 1_000_000.0));
    }
}
```

Biên dịch:

```bash
javac --release 17 -encoding UTF-8 G1NumaLoad.java
```

Chạy smoke test nhẹ trên JDK bất kỳ có G1:

```bash
java -XX:+UseG1GC -XX:-UseNUMA -Xms128m -Xmx128m G1NumaLoad 2 2000 4
```

Ví dụ **đầu ra đã quan sát trên Windows/OpenJDK 24.0.2** (thời gian thay đổi theo máy):

```text
threads=2
allocations=4000
checksum=514016
checksumValid=true
elapsedMs=2.1433
```

**Không dùng `elapsedMs=2.1433` để kết luận NUMA nhanh hay chậm**. Đó là một lần chạy nhỏ trên môi trường **không có NUMA support được kích hoạt**, nhằm chứng minh ví dụ biên dịch, chạy và checksum chính xác.

### 5.2. Giải thích workload và giới hạn

- `ExecutorService.newFixedThreadPool(threads)` tạo nhiều worker; `CountDownLatch` cho worker bắt đầu giai đoạn phân bổ gần nhau về thời điểm.
- Mỗi worker cấp phát `byte[]` kích thước cấu hình; sửa byte đầu và byte cuối rồi đưa vào checksum.
- `ArrayDeque` giữ tối đa **64 mảng đang sống** trong mỗi worker, tạo tương tác giữa allocation, retention ngắn hạn và GC. Sau khi deque loại phần tử, mảng có thể được GC thu hồi.
- `observed` là một biến `volatile` giữ checksum cuối để tạo quan sát thực tế; checksum cũng được in.
- Có một giai đoạn **warm-up** trước pha đo, nhưng nó không tương đương một benchmark có JMH, warmup dài, kiểm soát JIT và thread setup chặt chẽ.
- `elapsedMs` đo **wall time của riêng pha** bằng `System.nanoTime()`; phép đo có thể gồm cả chi phí khởi tạo/shutdown thread pool trong `phase`.

Mỗi lần chạy thành công cùng tham số phải có **checksum tương ứng** và `checksumValid=true`. Thời gian và số lần GC là đại lượng **không cố định**.

**Tham số an toàn:** `threads` 1..32, `count` 100..100.000, `arrayKiB` 1..64. Kể cả trong khoảng này, khi nhân ba tham số có thể tạo tổng dung lượng phân bổ rất lớn. Chọn cấu hình phù hợp RAM và test host, không chạy tải nặng trên máy production.

## 6. Thực nghiệm G1 NUMA có đối chứng trên Linux nhiều node

Phần này **chỉ có giá trị so sánh NUMA thật** nếu Linux/JVM có nhiều NUMA nodes đang hoạt động và cho phép phân bổ từ các nodes đó. Không áp dụng quy trình hiệu năng này cho một host đã xác nhận `NUMA Support: Disabled`.

### 6.1. Giữ cùng các biến

Chọn:
- Cùng JDK binary/version/vendor.
- Cùng OS/kernel, BIOS, filesystem, cgroup/cpuset và NUMA topology.
- Cùng CPU affinity, số threads, số allocations, kích thước mảng.
- Cùng heap (`-Xms` = `-Xmx`) và collector G1.
- Cùng `AlwaysPreTouch` nếu chọn dùng; tránh so một bên bật, bên kia tắt.
- Cùng tải máy và thermal/power state hợp lý.
- Cùng logging level, cách thu metrics và số lần lặp.

**Biến chính:** **`-XX:-UseNUMA` đối chứng và `-XX:+UseNUMA` thử nghiệm**.

Trước mỗi phép đo, chạy:

```bash
numactl --hardware
java -XX:+UseG1GC -XX:+UseNUMA -Xlog:gc+init=info -version
```

Nếu HotSpot báo NUMA bị disable hoặc chỉ một node, **dừng so sánh lợi ích NUMA và chuyển sang báo cáo smoke test**.

### 6.2. Lệnh baseline và NUMA

Từ thư mục chứa `G1NumaLoad.class`, trên Linux test host có đủ RAM:

```bash
mkdir -p logs

java -XX:+UseG1GC -XX:-UseNUMA -Xms2g -Xmx2g \
  -XX:+AlwaysPreTouch \
  '-Xlog:gc*,gc+heap+numa=debug:file=logs/numa-off.log:uptime,level,tags' \
  G1NumaLoad 8 30000 16

java -XX:+UseG1GC -XX:+UseNUMA -Xms2g -Xmx2g \
  -XX:+AlwaysPreTouch \
  '-Xlog:gc*,gc+heap+numa=debug:file=logs/numa-on.log:uptime,level,tags' \
  G1NumaLoad 8 30000 16
```

Đây là **lệnh benchmark có điều kiện cho Linux nhiều NUMA nodes**, **không phải lệnh đã chạy trên Linux** trong lần biên soạn bài. Tham số có nghĩa:

| Tham số | Tác dụng |
| --- | --- |
| `-XX:+UseG1GC` | Chọn collector G1 tường minh |
| `-XX:-UseNUMA` / `-XX:+UseNUMA` | Tắt/bật tối ưu NUMA để so |
| `-Xms2g -Xmx2g` | Cố định heap khởi tạo và tối đa 2 GiB |
| `-XX:+AlwaysPreTouch` | Pre-touch bộ nhớ heap để giảm biến thiên first-touch khi chạy |
| `-Xlog:gc*,gc+heap+numa=debug` | Thu GC logs và log mức debug cho nhóm tag NUMA |
| `file=logs/numa-*.log` | Hai file log tách biệt |
| `8 30000 16` | 8 workers × 30.000 mảng/thread × 16 KiB/mảng |

Một pha đã tạo **3.840.000 KiB ~ 3,66 GiB dung lượng phân bổ**, cộng với warm-up và metadata; **đó là tổng bytes allocated, không phải peak retained heap**. Với 2 GiB heap, nhiều đối tượng ngắn hạn có thể tạo áp lực GC. Chi phí thực tế phụ thuộc GC/JIT và hệ thống.

**Không áp dụng mặc định `numactl --membind=0` để “chuẩn hóa” hai bản**: khóa toàn bộ bộ nhớ vào một node có thể triệt tiêu chính điều kiện cho phép G1 phân bổ cục bộ trên nhiều node. Nếu dùng CPU/memory affinity theo yêu cầu test, phải ghi lại và áp dụng **nhất quán**; chỉ đưa những nodes tương ứng vào phép so.

### 6.3. Đo thêm OS metrics và trạng thái JVM

Trong khi process đang chạy (cần workload đủ dài để có thể lấy mẫu):

```bash
numastat -p <PID>
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

Các ký hiệu `<PID>` là **vị trí thay bằng process ID thật**, không phải lệnh đã chạy độc lập. `numastat` và `jcmd` có thể không được cài hoặc không đủ quyền trong container; xem tài liệu OS/JDK tương ứng.

Chỉ dùng `numastat -p` khi JVM vẫn đang chạy. Với workload quá nhanh, thêm cơ chế đồng bộ/thu sample hoặc sử dụng benchmark kéo dài **có kiểm soát**; không giả mạo metric nếu không lấy được PID kịp.

Đối chiếu với GC log:

- `gc+init`: collector, heap, GC workers và **NUMA Support**.
- `gc+heap+numa`: thông tin phân bổ vùng và tương tác NUMA nếu build/JDK thực sự phát log ở mức tương ứng.
- `gc=info` / `gc*`: thời gian GC, loại GC, số lần dừng, heap trước/sau.
- Các công cụ OS: local/remote node pages, CPU locality, page faults, memory policy nếu khả dụng.

**Chú ý về phiên bản logging:** Tag availability và mức log có thể thay đổi giữa JDK builds; dùng `java -Xlog:help` để kiểm tra. **Không dùng những cờ `-XX:+PrintGCDetails` hoặc `-XX:+PrintGCDateStamps` của thời logging cũ** làm tài liệu chính cho Java 17+; dùng Unified Logging `-Xlog`.

### 6.4. Đọc kết quả không thiên lệch

Tối thiểu, so:

| Chỉ số | Baseline NUMA off | NUMA on | Cách kết luận |
| --- | --- | --- | --- |
| Tổng operations | Cùng giá trị | Cùng giá trị | Nếu khác, **INVALID** |
| Checksum | Cùng giá trị | Cùng giá trị | Nếu khác, **FAIL tính đúng đắn** |
| Median elapsedMs | Đo nhiều vòng | Đo nhiều vòng | Thấp hơn có thể là cải thiện latency của workload |
| Throughput ops/s | `ops / elapsedSeconds` | Như baseline | Cao hơn có thể là cải thiện throughput |
| GC pause p95/p99 | Trích log nhiều lần | Trích log nhiều lần | Cần đúng metric/đủ mẫu |
| GC count | Theo log | Theo log | Chỉ là dấu hiệu bổ sung |
| Local/remote memory | Theo numastat nếu phù hợp | Theo numastat | Chứng minh thay đổi placement/locality |
| NUMA Support activated | OFF hợp lệ | ON **phải enabled** | Không enabled => không so NUMA |
| Hệ điều hành/heap/flags | Ghi lại | Giữ y hệt trừ UseNUMA | Nếu lệch, **INVALID** |

Công thức phần trăm thay đổi throughput:

```text
improvement_percent =
    (throughput_on / throughput_off - 1) * 100
```

Công thức giảm elapsed time (nhỏ hơn tốt hơn):

```text
time_reduction_percent =
    (elapsed_off - elapsed_on) / elapsed_off * 100
```

**Không nhầm hai phần trăm**: tăng throughput 25% không tương đương giảm thời gian 25% (với lượng công việc cố định nó tương đương giảm 20%).

Chạy warmup và **nhiều lần lặp độc lập**, ví dụ 7–15 lần mỗi cấu hình, hoán đổi thứ tự thử on/off để giảm thiên lệch theo nhiệt độ/tải theo thời gian. Thu median và phân tán (IQR hoặc khoảng biến thiên), không lựa chọn “run nhanh nhất” cho bản muốn chứng minh tốt. Với kết quả sát nhau hơn nhiễu, kết luận **không đủ bằng chứng cải thiện**, không khẳng định tăng tốc.

### 6.5. Những dấu hiệu bài test G1 không hợp lệ

- JVM không nhận/không kích hoạt NUMA policy mặc dù truyền `-XX:+UseNUMA`.
- Host chỉ có một node hoặc process bị khóa vào một node.
- So sánh Windows với Linux rồi quy cải thiện cho `UseNUMA`.
- Hai bản chạy JDK khác version hoặc vendor, có collector khác nhau.
- Heap sizes/CPU affinity/GC logs hoặc workload không đồng nhất.
- Chạy một lần và lấy thời gian vài mili giây làm kết luận về multi-node NUMA.
- Hai bản có checksum/operations khác nhau.
- Không đo hệ thống thật, nhưng gán “NUMA improved X%” chỉ dựa trên tài liệu của người khác.

## 7. NVM: `FileChannel.map` và hai mode mở rộng

Đối với NVM, JEP 352 giới thiệu `jdk.nio.mapmode.ExtendedMapMode`:

```java
import jdk.nio.mapmode.ExtendedMapMode;
```

Hai mode có kiểu **`FileChannel.MapMode`**:

| Mode | Mục đích |
| --- | --- |
| `ExtendedMapMode.READ_ONLY_SYNC` | Map chỉ đọc một file backed by non-volatile RAM |
| `ExtendedMapMode.READ_WRITE_SYNC` | Map đọc/ghi một file backed by non-volatile RAM |
| `FileChannel.MapMode.READ_WRITE` | Baseline ánh xạ file đọc/ghi thông thường; không yêu cầu NVM-specific MAP_SYNC |

**Đúng API:** `FileChannel.map(mode, position, size)` trả về `MappedByteBuffer`. Không tồn tại một `NvmFileChannel` hoặc phương thức `mapNvm()` tiêu chuẩn.

Mục tiêu `READ_WRITE_SYNC` là hỗ trợ map trên NVM với ngữ nghĩa đồng bộ phù hợp. Javadoc cho biết trên Linux implementation dùng `MAP_SHARED_VALIDATE` và `MAP_SYNC`; với buffer mapped theo `READ_WRITE_SYNC`, `force()` dùng cơ chế **cache-line writeback** thay vì flush qua file-device như cách truyền thống.

**Điều không đúng:** chỉ cần import `ExtendedMapMode` là mọi file đều hỗ trợ. `map(...)` có thể ném `UnsupportedOperationException` khi implementation không hỗ trợ, hoặc gặp `IOException` do OS/filesystem/đường dẫn/quyền. Phải chẩn đoán môi trường, không tự chuyển toàn bộ lỗi I/O thành “NVM unavailable”.

### `force()` và durability

`MappedByteBuffer.force()`/`force(index,length)` yêu cầu ghi các thay đổi trên buffer xuống storage theo hợp đồng API. Với mapping SYNC trên nền tảng hỗ trợ, cơ chế cache-line writeback có ý nghĩa với NVM.

**Nhưng**:
- `force` không biến một chuỗi nhiều lệnh `put` thành **giao dịch atomic**.
- Dữ liệu đọc lại ngay trong cùng OS **chưa chứng minh** khả năng phục hồi sau mất điện.
- Thứ tự ghi các metadata quan trọng, checksum, commit marker và recovery vẫn là trách nhiệm ứng dụng.
- Mức bền vững thực phụ thuộc kiến trúc CPU, device, kernel, filesystem và tầng storage.
- Với file nhạy cảm, quản lý quyền truy cập, retention và mã hóa như một lưu trữ bền vững thực sự.

**`READ_ONLY_SYNC` không cho phép ghi.** Trong bài thử hiệu năng ghi, dùng `READ_WRITE_SYNC`; với phân tích dữ liệu chỉ đọc, mới xét `READ_ONLY_SYNC`.

## 8. Ví dụ Java 17+ kiểm chứng NVM theo khả năng thực tế

Chương trình thực hiện hai phép thử **cùng một cơ chế ghi**:

- `standard`: dùng `FileChannel.MapMode.READ_WRITE`.
- `sync`: dùng `ExtendedMapMode.READ_WRITE_SYNC`.

Ở cả hai mode, chương trình tạo **file tạm mới** trong thư mục người dùng chỉ định, ánh xạ 4096 byte, lặp nhiều lần ghi **2 số nguyên (8 byte)** và gọi `force(0,8)` sau mỗi lần ghi, rồi đọc lại giá trị cuối.

**Tuyệt đối không chạy trên một đường dẫn file production có sẵn**; ví dụ chỉ tạo file temp trong thư mục đã được cho phép, và chỉ xóa file temp do chính nó tạo. Không format/mount hay phá dữ liệu hiện có.

### 8.1. Toàn bộ `NvmMappedProbe.java`

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import jdk.nio.mapmode.ExtendedMapMode;

public class NvmMappedProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: NvmMappedProbe <standard|sync> <directory> <iterations>");
        }
        boolean sync = switch (args[0]) {
            case "standard" -> false;
            case "sync" -> true;
            default -> throw new IllegalArgumentException(
                    "Mode must be standard or sync");
        };
        Path dir = Path.of(args[1]);
        int iterations = Integer.parseInt(args[2]);
        if (!Files.isDirectory(dir) || iterations < 1 || iterations > 100_000) {
            throw new IllegalArgumentException(
                    "Provide an existing directory and iterations 1..100000");
        }
        FileChannel.MapMode mode = sync
                ? ExtendedMapMode.READ_WRITE_SYNC
                : FileChannel.MapMode.READ_WRITE;
        Path file = Files.createTempFile(dir, "nvm-eval-", ".bin");
        try {
            long durationNs;
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                MappedByteBuffer mapped = channel.map(mode, 0, 4096);
                long start = System.nanoTime();
                for (int i = 1; i <= iterations; i++) {
                    mapped.putInt(0, i);
                    mapped.putInt(4, ~i);
                    mapped.force(0, 8);
                }
                durationNs = System.nanoTime() - start;
            } catch (UnsupportedOperationException ex) {
                System.out.println("requestedMode=" + mode);
                System.out.println("status=UNSUPPORTED");
                return;
            } catch (IOException ex) {
                System.out.println("requestedMode=" + mode);
                System.out.println("status=IO_ERROR");
                System.out.println("errorClass=" + ex.getClass().getSimpleName());
                return;
            }

            int stored;
            int complement;
            try (FileChannel reader = FileChannel.open(
                    file, StandardOpenOption.READ)) {
                var bytes = java.nio.ByteBuffer.allocate(8);
                while (bytes.hasRemaining() && reader.read(bytes) != -1) { }
                bytes.flip();
                stored = bytes.getInt();
                complement = bytes.getInt();
            }

            System.out.println("requestedMode=" + mode);
            System.out.println("status=OK");
            System.out.println("iterations=" + iterations);
            System.out.println("readBackValid=" +
                    (stored == iterations && complement == ~stored));
            System.out.println("nsPerForce=" +
                    (durationNs / (double) iterations));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

**Các điểm an toàn trong chương trình:**

1. Chỉ chấp nhận mode `standard` hoặc `sync`; không tự chuyển sang mode thường nếu mode SYNC bị từ chối.
2. Yêu cầu **thư mục đích đã tồn tại**, tránh tự tạo đường dẫn không được kiểm soát.
3. `Files.createTempFile` tạo file mới với tên riêng; `finally` chỉ xóa đúng file đó.
4. `FileChannel.map` được gọi với offset 0, length 4096; tệp được mở READ/WRITE.
5. `putInt(0,i)` và `putInt(4,~i)` ghi hai giá trị kiểm soát có thể xác minh.
6. `force(0,8)` được gọi sau mỗi lần ghi để mô phỏng một pattern yêu cầu persistence per record.
7. `IOException` và `UnsupportedOperationException` được báo riêng, **không âm thầm biến thành OK**.
8. Sau khi đóng channel, ví dụ mở file để đọc lại hai số và xác minh invariant. `readBackValid` chỉ là functional check, **không phải power-failure test**.

**Giới hạn tài nguyên:** `MappedByteBuffer` có vòng đời mapping riêng với `FileChannel`; đóng channel **không luôn unmap ngay**. Trên một số OS/filesystem, xóa file vẫn mapped có thể thất bại; khi đó chương trình có thể ném lỗi tại `Files.deleteIfExists`. Đây là giới hạn của ví dụ Java 17 dùng mapping, không được giải quyết bằng việc gọi API nội bộ `sun.misc.Unsafe` để ép unmap trong bài học.

### 8.2. Biên dịch và chạy ở nơi bất kỳ

`ExtendedMapMode` là API trong module JDK có tên **`jdk.nio.mapmode`**. Với classpath/unnamed module, phân giải tường minh:

```bash
javac --release 17 --add-modules jdk.nio.mapmode NvmMappedProbe.java
java --add-modules jdk.nio.mapmode NvmMappedProbe standard . 50
java --add-modules jdk.nio.mapmode NvmMappedProbe sync . 50
```

Lệnh dùng thư mục hiện hành `.` làm nơi tạo **tệp thử nghiệm tạm**. Chỉ chạy ở một thư mục test mà bạn có quyền thao tác, không ở thư mục production. Kiểm thử trên Windows/OpenJDK 24.0.2 nhận được:

**Mode tiêu chuẩn:**

```text
requestedMode=READ_WRITE
status=OK
iterations=50
readBackValid=true
nsPerForce=178208.0
```

**Mode SYNC:**

```text
requestedMode=READ_WRITE_SYNC
status=UNSUPPORTED
```

Ở đây, **`UNSUPPORTED` là kết quả hợp lệ** khi không có hỗ trợ NVM/DAX. `nsPerForce=178208.0` là **quan sát từ một lần chạy máy Windows test với 50 lần force**, **không phải** con số benchmark chung, không dùng so hiệu năng ổ NVM.

Trên Linux có hỗ trợ thực, `sync` có thể trả `status=OK`; nhưng bài này **chưa đo `READ_WRITE_SYNC` thành công trên DAX vật lý**. Nếu thấy `IO_ERROR`, đọc lỗi và kiểm tra filesystem/permission/kernel/mount; không tự coi mọi `IOException` là “chỉ thiếu phần cứng”.

### 8.3. So sánh NVM khi có mount DAX thật

Chỉ trên môi trường được xác nhận có fs-DAX:

```bash
java --add-modules jdk.nio.mapmode NvmMappedProbe standard /mnt/dax 5000
java --add-modules jdk.nio.mapmode NvmMappedProbe sync /mnt/dax 5000
```

**Yêu cầu phương pháp:**

- Cả hai chạy trên **cùng mount/file system/device**, chỉ khác `MapMode`.
- Cùng kích thước vùng 4096, payload 8 byte, số lần ghi và `force(0,8)`.
- Dữ liệu sau đọc lại có `readBackValid=true` cho cả hai.
- Lặp nhiều lần, có giai đoạn warm-up và hoán đổi thứ tự hai mode. Chương trình demo **chưa tự làm full warmup/benchmark harness**.
- Thu **latency per force** (median/p95 nếu có instrument theo từng lần), throughput records/s, CPU/IO behavior.
- Đo riêng chi phí tạo mapping và chi phí `force` nếu ứng dụng thực có pattern khác.
- So sánh read/write throughput không được đánh đồng với độ bền crash-consistency.

**Một lần `nsPerForce` nhỏ hơn chưa đủ để chứng minh NVM tốt hơn.** Các mode có cơ chế flush khác nhau, và các phiên bản JDK/filesystem có thể khác; đòi hỏi thêm số liệu thống kê và thử nghiệm phục hồi để kết luận.

### 8.4. Đo độ bền thực sự: bài thử nâng cao

Bài test chức năng `readBackValid=true` chỉ xác nhận **giá trị nhìn thấy sau khi write/force rồi mở lại trong cùng OS**. Nó **không** xác minh:

- Dữ liệu còn đúng sau mất nguồn.
- Record nhiều field được ghi atomically.
- Không có torn writes trong trường hợp crash đúng lúc ghi.
- Thứ tự commit metadata/payload đúng.
- Có recovery nếu header/checksum hỏng.

Nếu hệ thống cần durability thật, xây **thiết kế record** gồm version, checksum, transaction/commit marker hoặc log, rồi thử **controlled crash/restart** trên thiết bị được cấp phép và môi trường test có backup. **Không cắt điện tùy tiện** một hệ thống đang phục vụ người dùng.

## 9. G1 NUMA và NVM: có thể phối hợp không?

Có thể tồn tại trên một máy nhưng **không phải cùng một cơ chế**:

- **G1 NUMA** quản lý cách **HotSpot phân bổ heap object** trên các memory nodes.
- **NVM mapped file** cung cấp **vùng byte được ánh xạ tới một file** qua `FileChannel`.
- `MappedByteBuffer` là một dạng **direct/mapped memory** nằm ngoài Java heap theo cách quản lý cấp phát của object thông thường; G1 không tự chuyển file mapped đó thành heap region.
- **`-XX:AllocateHeapAt=path`** (nếu JDK/OS hỗ trợ) là một tùy chọn HotSpot riêng cho việc đặt Java heap trên một thiết bị bộ nhớ thay thế. Nó **không đồng nghĩa** với `ExtendedMapMode.READ_WRITE_SYNC`, không thay cho lời gọi `FileChannel.map`, và yêu cầu đánh giá/điều kiện riêng.
- Bật `UseNUMA` không tự cấp `MAP_SYNC`, và có NVM không tự làm G1 heap placement theo NUMA.

**Một đánh giá nên đổi một biến chính mỗi lần.** Nếu vừa thay collector, vừa thay filesystem, vừa chuyển heap sang NVM, khó xác định nguyên nhân thay đổi throughput hoặc latency.

## 10. Ma trận kiểm thử theo loại môi trường

| Môi trường | G1 smoke | NUMA effect benchmark | Standard mapping | NVM SYNC benchmark |
| --- | --- | --- | --- | --- |
| Windows thông thường, JVM NUMA disabled | Có | **NOT_APPLICABLE** | Có | **UNSUPPORTED** nếu mode bị từ chối |
| Linux một NUMA node, filesystem bình thường | Có | **NOT_APPLICABLE** | Có | Thường không khả dụng; phải thử mới biết |
| Linux nhiều NUMA nodes, không có DAX | Có | Có, **nếu JVM báo NUMA enabled** | Có | **UNSUPPORTED/SKIP** nếu không DAX |
| Linux một NUMA node nhưng có fs-DAX | Có | **NOT_APPLICABLE** | Có | Có thể benchmark SYNC nếu map thành công |
| Linux nhiều NUMA nodes và fs-DAX | Có | Có | Có | Có, đo **độc lập từng tính năng** |
| VM/container chưa xác định topology | Có | Chưa đủ dữ liệu | Có | Chưa đủ dữ liệu | 

**Lưu ý:** Đây là điều kiện **được phép thử**, không phải kết quả được đo sẵn. Ví dụ Linux nhiều NUMA nodes vẫn phải xác nhận kernel/JVM/container thực sự kích hoạt NUMA; một mount được gọi là “DAX” vẫn phải qua phép thử `map` thực tế.

### Trạng thái QA nên dùng

| Trạng thái | Điều kiện |
| --- | --- |
| **PASS_FUNCTIONAL** | Ví dụ chạy và các assertions/read-back đúng |
| **PASS_BENCHMARK** | Đủ phần cứng, baseline/test hợp lệ, chạy lặp, thống kê được ghi |
| **UNSUPPORTED** | JVM/OS/FS từ chối mode hoặc không có feature |
| **NOT_APPLICABLE** | Môi trường không có nhiều NUMA nodes hoặc không có NVM |
| **INVALID_COMPARISON** | Khác JDK/heap/workload, NUMA không active hoặc thiếu dữ liệu |
| **FAIL** | Checksum sai, dữ liệu đọc lại không đúng, lỗi I/O không xử lý, hoặc sai yêu cầu |
| **INCONCLUSIVE** | Số liệu biến thiên/thiếu mẫu, không đủ chứng cứ tốt hơn/xấu hơn |

**Không dùng `PASS_BENCHMARK` chỉ vì `javac`/`java` chạy được.** Ví dụ trên Windows hiện tại chứng minh **PASS_FUNCTIONAL** cho standard mapping và workload G1, **UNSUPPORTED** với SYNC, và **NOT_APPLICABLE** cho so sánh G1 NUMA.

## 11. Cách viết báo cáo benchmark có thể tái lập

Một báo cáo tốt cần ghi:

1. **Mục tiêu:** đang tìm throughput cao hơn, GC pause thấp hơn, hay latency per `force` thấp hơn?
2. **Hệ thống:** OS/kernel, JDK vendor/build, CPU/NUMA topology, RAM, storage và filesystem.
3. **Bằng chứng hỗ trợ:** `NUMA Support enabled` trong GC log, hoặc `READ_WRITE_SYNC map` thành công trên mount DAX.
4. **Cấu hình:** cờ `-XX`, `-Xms/-Xmx`, số thread, kích thước object, number of iterations, affinity.
5. **Baseline:** G1 NUMA off hoặc `READ_WRITE`, giải thích vì sao baseline hợp lệ.
6. **Variant:** G1 NUMA on hoặc `READ_WRITE_SYNC`; các biến khác giữ cố định.
7. **Phương pháp:** warm-up, số lần lặp, thứ tự xen kẽ, cách đo, version script/code.
8. **Độ đúng:** checksum, read-back, hành vi lỗi, invariant/transaction.
9. **Kết quả thống kê:** median, phân tán, p95/p99 khi phù hợp, GC pause và số GC, throughput/latency.
10. **Giới hạn:** môi trường test, số mẫu, không có kiểm thử power-loss hoặc không giống production.
11. **Kết luận có điều kiện:** quyết định giữ/tắt feature, nhu cầu thêm dữ liệu, rủi ro regressions.

Ví dụ về **một dòng kết quả không đủ điều kiện kết luận**:

```text
G1: 4000 allocations, elapsedMs=2.1433, NUMA disabled
NVM: standard=OK, sync=UNSUPPORTED
Kết luận: xác minh code chạy; chưa có benchmark NUMA/NVM hợp lệ.
```

Đây là **kết quả diễn giải từ lần kiểm chứng trên máy Windows**, không phải thành tích phần cứng NVM.

Một báo cáo production-grade nên có nhiều lần chạy và file raw logs. Đừng tạo số liệu giả cho cột “on” chỉ để bảng đủ hàng.

## 12. Lỗi thường gặp

| Sai lầm | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| Tưởng NUMA = NVM | Khác kiến trúc và mục tiêu | Tách benchmark theo tính năng |
| Thấy `UseNUMA` trên command line và mặc định đã active | JVM có thể disable theo OS/node count | Xem `gc+init`, flag cuối và OS topology |
| So GC trên Windows với Linux nhiều NUMA nodes | Khác OS/JDK/scheduler | So trên cùng host và cùng môi trường |
| Đo một lần rồi kết luận nhanh hơn X% | Nhiễu JIT/GC/thermal | Warm-up, lặp nhiều lần, median/IQR |
| Chọn workload không tạo GC | Không đo được tác động GC | Kiểm tra GC log, điều chỉnh áp lực phân bổ |
| Chỉ đo wall time bỏ qua GC logs | Không giải thích nguyên nhân | Thu pause, count, heap và locality |
| Khóa `--membind=0` chỉ một node khi muốn đo nhiều node | Triệt tiêu một phần cơ chế NUMA | Chọn affinity/mempolicy phù hợp, giữ đồng nhất |
| Bật NUMA nhưng khác heap/JDK giữa hai mẫu | Không cô lập biến | Cùng tất cả config, chỉ đổi `UseNUMA` |
| Gọi SSD NVMe là NVM DAX | `MAP_SYNC` có thể không hỗ trợ | Xác minh filesystem và thiết bị |
| Import được `ExtendedMapMode` rồi coi như supported | Có API không đồng nghĩa phần cứng | Thử `FileChannel.map` thực tế |
| Catch mọi `IOException` rồi im lặng dùng mapping thường | Che lỗi tệp/permission | Báo IO_ERROR và chẩn đoán |
| Không gọi `MappedByteBuffer.force()` | Khó đánh giá flush theo contract | Force theo phạm vi muốn đo |
| Coi `force` là transaction atomic | Crash có thể làm hỏng record nhiều field | Checksum/commit/recovery |
| Chạy benchmark trên thư mục dữ liệu quan trọng | Rủi ro dữ liệu người dùng | Chỉ dùng thư mục test và tempfile |
| So `standard` trên SSD với `sync` trên thiết bị khác | Không còn một biến độc lập | Cùng mount/device khi có thể |
| Đo `nsPerForce` một lần trên Windows và gọi kết quả NVM | Mode SYNC không active | Báo smoke/UNSUPPORTED |
| Không kiểm tra checksum/readBack | Không biết code tính đúng | Có assertions và trạng thái FAIL rõ |
| Nhầm `-XX:AllocateHeapAt` với FileChannel NVM | Khác tầng quản lý bộ nhớ | Phân tích riêng trước khi sử dụng |
| Dùng `PrintGCDetails`/logging cũ | Hướng dẫn không phù hợp Java mới | Dùng Unified Logging `-Xlog` |
| Không ghi hạn chế/không đủ quyền đọc OS metrics | Kết luận vượt dữ liệu | Ghi NOT_APPLICABLE/INCONCLUSIVE |

## 13. Câu hỏi ôn tập có đáp án

**Câu 1.** Tính năng nào trong Java 14 liên quan G1 NUMA?  
**Đáp án:** **JEP 345**, hỗ trợ NUMA-aware allocation cho G1 trên hệ phù hợp.

**Câu 2.** Cần những điều kiện tối thiểu gì để benchmark G1 NUMA?  
**Đáp án:** JVM hỗ trợ và **kích hoạt NUMA**, máy có nhiều memory nodes khả dụng, cùng JDK/workload/heap/affinity và số liệu quan sát được.

**Câu 3.** Vì sao `-XX:+UseNUMA` được JVM chấp nhận vẫn chưa đủ?  
**Đáp án:** JVM có thể disable sau khi kiểm tra OS/topology, nên cần xác minh `NUMA Support` trong startup log và nodes của process.

**Câu 4.** NVM trong JEP 352 có giống ổ SSD NVMe không?  
**Đáp án:** Không. JEP 352 nhắm persistent-memory mapped files với support của OS/filesystem (đặc biệt MAP_SYNC/DAX), không mặc nhiên là SSD NVMe.

**Câu 5.** Mode nào trong module `jdk.nio.mapmode` hỗ trợ ghi?  
**Đáp án:** `ExtendedMapMode.READ_WRITE_SYNC`. `READ_ONLY_SYNC` chỉ đọc.

**Câu 6.** Vì sao cần `MappedByteBuffer.force()`?  
**Đáp án:** Để yêu cầu ghi các thay đổi mapped xuống storage theo hợp đồng API; mode SYNC dùng cơ chế cache-line writeback khi có hỗ trợ.

**Câu 7.** Nếu máy không hỗ trợ SYNC mapping, kết quả bài test nên là gì?  
**Đáp án:** `UNSUPPORTED` hoặc `NOT_APPLICABLE`, không ghi kết quả “NVM cải thiện X%”.

**Câu 8.** `readBackValid=true` sau `force` có chứng minh dữ liệu sống sót khi mất điện không?  
**Đáp án:** Không. Cần crash/restart/power-loss recovery test có kiểm soát và kiểm tra invariant, checksum.

**Câu 9.** Vì sao cần cùng thư mục DAX cho mode standard và sync khi so hiệu năng?  
**Đáp án:** Để tránh khác biệt thiết bị, filesystem, caching và I/O path chi phối kết quả.

**Câu 10.** Median và nhiều lần lặp giúp ích gì?  
**Đáp án:** Giảm tác động của những lần đo nhiễu/JIT/thermal, cho cái nhìn ổn định hơn một lần chạy.

**Câu 11.** Nếu G1 NUMA không có cải thiện ở một workload nhỏ, có kết luận feature vô ích không?  
**Đáp án:** Không. Working set có thể vừa một node hoặc không đủ remote memory access; cần kiểm tra workload và topology.

**Câu 12.** Làm thế nào để phát hiện benchmark làm sai chức năng ứng dụng?  
**Đáp án:** So operations/checksum, exception path, dữ liệu read-back và invariant trước khi so tốc độ.

**Câu 13.** `-XX:AllocateHeapAt=path` có phải gọi `READ_WRITE_SYNC` không?  
**Đáp án:** Không. Đây là cơ chế HotSpot tùy chọn đặt heap trên storage/memory device khác, không phải API map file SYNC của ứng dụng.

**Câu 14.** Có nên cho phép benchmark tự xóa các file trong mount thật không?  
**Đáp án:** Chỉ được tạo/xóa **file tạm riêng do bài test sở hữu**; không xóa, format hay mount lại tài nguyên production.

**Câu 15.** Khi nào dùng trạng thái `INCONCLUSIVE`?  
**Đáp án:** Khi phép đo có biến thiên lớn, thiếu mẫu hoặc thiếu metrics để kết luận tốt/xấu, dù chương trình chạy đúng.

## 14. Tổng kết và tài liệu tham khảo chính thức

**Quy trình ra quyết định:**

```text
Bắt đầu
  |
  +-- Có máy nhiều NUMA nodes và HotSpot G1 hỗ trợ thật?
  |       |
  |       +-- Có  -> So UseNUMA off/on với cùng workload,
  |       |          thu GC logs + OS locality + thống kê lặp
  |       |
  |       +-- Không -> G1 smoke test, ghi NOT_APPLICABLE
  |
  +-- Có thiết bị NVM với filesystem hỗ trợ DAX/MAP_SYNC?
          |
          +-- Có  -> So READ_WRITE và READ_WRITE_SYNC
          |          trên cùng mount, force + readback,
          |          kiểm tra độ bền nếu có yêu cầu
          |
          +-- Không -> Standard mapping smoke test,
                     SYNC=UNSUPPORTED/NOT_APPLICABLE
```

**Kết luận:** Đánh giá G1 NUMA hay NVM mapping chỉ có ý nghĩa khi biết **feature đã thật sự được kích hoạt** và môi trường phần cứng/hệ điều hành **có điều kiện tương ứng**. Với máy không đủ điều kiện, việc compile/run ví dụ và ghi chính xác `UNSUPPORTED`/`NOT_APPLICABLE` vẫn là kết quả kiểm thử **đúng đắn và có giá trị học tập**. Không suy đoán benchmark từ việc chương trình chỉ chạy thành công.

**Tài liệu chính thức, phù hợp với Java hiện đại:**

- [OpenJDK JEP 345 — NUMA-Aware Memory Allocation for G1](https://openjdk.org/jeps/345): phạm vi và mục tiêu hỗ trợ NUMA trong G1 từ Java 14.
- [Oracle JDK 25 — Significant Changes in JDK 14](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-14.html): ghi nhận G1 NUMA và NVM mapping trong Java 14.
- [Oracle Java SE 25 — java command / `UseNUMA` / Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cấu hình collector, NUMA và `-Xlog` trong JVM mới.
- [Oracle Java SE 25 — HotSpot Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/): GC ergonomics và quy trình tuning dựa trên workload.
- [OpenJDK JEP 352 — Non-Volatile Mapped Byte Buffers](https://openjdk.org/jeps/352): chế độ ánh xạ NVM qua FileChannel từ Java 14.
- [Oracle Java SE 25 — `ExtendedMapMode`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html): `READ_ONLY_SYNC`, `READ_WRITE_SYNC`, `MAP_SYNC` và giới hạn platform.
- [Oracle Java SE 25 — `MappedByteBuffer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/MappedByteBuffer.html): `force()`, `force(index,length)`, phạm vi và durability.
- [Oracle Java SE 17 — `FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): ánh xạ file, quyền và hành vi của buffer.
- [Oracle Java SE 17 — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): đo thời gian đã trôi qua trong cùng tiến trình.
