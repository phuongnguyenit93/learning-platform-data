# Epsilon và phép đo: Phân biệt chi phí cấp phát với chi phí thu gom (Java 11)

## 1. Mục tiêu và câu hỏi cốt lõi

Khi một ứng dụng Java chậm vì áp lực bộ nhớ, có ít nhất hai nhóm công việc phải phân biệt:

1. **Cấp phát (allocation)**: tạo object/array mới, đặt vị trí trong heap, quản lý đường cấp phát nhanh/chậm, khởi tạo dữ liệu và những chi phí liên quan.
2. **Thu gom (garbage collection — GC)**: xác định object không còn được dùng, thu hồi hoặc di chuyển vùng nhớ, cập nhật cấu trúc và thực hiện công việc của bộ thu gom.

Một lỗi phân tích thường gặp là thấy nhiều object được tạo rồi kết luận toàn bộ thời gian đó là **“thời gian GC”**. Việc tạo object vẫn tốn công **ngay cả khi không có lần thu gom nào xảy ra**. Ngược lại, chi phí GC không chỉ nằm ở những dòng báo pause: một collector hiện đại có thể làm việc đồng thời với ứng dụng và áp dụng các barrier/metadata bookkeeping trong lúc ứng dụng chạy.

**Epsilon GC (JEP 318)** được bổ sung vào OpenJDK 11 như một **no-op garbage collector**: JVM vẫn cấp phát object, nhưng **không thu hồi object đã chết**. Vì vậy, Epsilon là một **công cụ đối chứng** hữu ích để khảo sát đường cấp phát và phần chi phí gắn với bộ thu gom; nó **không** phải cách đơn giản để tính chính xác “chi phí GC = thời gian G1 − thời gian Epsilon”.

Sau bài học, bạn sẽ:

- Giải thích được **allocation cost** khác **collection cost** và **memory retention/live set** như thế nào.
- Biết Epsilon **làm** và **không làm** gì; hiểu nguy cơ `OutOfMemoryError` khi heap đầy.
- Biên dịch một chương trình Java 11, chạy riêng với **G1** và **Epsilon** trên cùng heap size, quan sát thời gian và GC logs.
- Phân loại chính xác **giá trị đầu ra bất biến** và **giá trị đo có thể thay đổi**.
- Sử dụng `GarbageCollectorMXBean`, `-Xlog:gc`, JFR và allocation metrics theo đúng giới hạn của từng nguồn.
- Thiết kế phép thử có warm-up, lặp lại, kiểm soát JIT, TLAB, escape analysis, heap pressure, CPU và môi trường.
- Tránh kết luận sai rằng Epsilon là lựa chọn production thích hợp cho service chạy lâu hoặc rằng số lần GC bằng toàn bộ overhead.

**Special Note về tính hiện hành:** JEP 318 và cơ chế Epsilon vẫn có giá trị để nghiên cứu/kiểm thử trong HotSpot/JDK tương thích. Các option `-XX` là **implementation-specific**, có thể thay đổi theo JVM/vendor/phiên bản. Bài không sử dụng CMS hay các option logging cũ đã lỗi thời để giải thích Java 11 hiện nay.

## 2. Từ source Java đến hai loại chi phí

Xem câu lệnh:

```java
byte[] data = new byte[4096];
data[0] = 7;
```

Ở mức ngôn ngữ, chương trình cần một mảng `byte[]` dài 4.096 phần tử và gán giá trị tại index 0. Tuy nhiên, chi phí thực thi có nhiều lớp:

| Nhóm | Thành phần có thể có | Có nhất thiết tạo GC pause không? |
| --- | --- | --- |
| **Allocation path** | Tính kích thước object, cấp phát trong TLAB hoặc đường chậm, cập nhật con trỏ allocation | **Không** |
| **Object initialization** | Zero-initialize bộ nhớ theo semantics Java, ghi phần tử, cache/memory bandwidth | **Không** |
| **Runtime/JIT effects** | Thực thi interpreter/JIT, inlining, escape analysis, safepoint polling | **Không** |
| **GC-related mutator work** | Write barrier, remembered set/card marking tùy collector | **Không nhất thiết**, nhưng thuộc chi phí liên quan collector |
| **STW collection** | Tạm dừng application threads để thu gom một pha | **Có** pause khi xảy ra |
| **Concurrent collection** | GC workers hoạt động song song với application | **Không nhất thiết dừng**, nhưng tiêu thụ CPU/băng thông |
| **Memory pressure** | Cache misses, page faults, heap commit, swap hoặc cgroup limit | **Không đồng nhất** với GC |
| **JVM startup** | Class loading, JIT, heap setup, runtime initialization | **Không đồng nhất** với cost của mỗi allocation |

**TLAB** là *Thread-Local Allocation Buffer*, vùng nhớ để một thread thực hiện nhiều lần cấp phát bằng đường nhanh khi còn chỗ. Khi TLAB đầy, JVM có thể phải tìm/cấp vùng mới hoặc thực hiện đường chậm. **Không phải cứ TLAB refill là GC**, và không phải mọi allocation đều đi qua cùng fast path.

**Escape analysis/scalar replacement:** JIT có thể không cấp phát object lên heap nếu chứng minh object không cần thoát khỏi phạm vi và có thể thay nó bằng scalar values. Khi đó **số lệnh `new` trong source không bằng số object heap thực sự được cấp phát**. Vì vậy benchmark phải xác nhận thao tác mình muốn đo thật sự xảy ra.

## 3. Heap allocation, live set và GC: ba đại lượng khác nhau

### 3.1. Allocation volume và allocation rate

- **Allocation volume**: tổng lượng bộ nhớ cấp phát trong một khoảng, thường tính byte.
- **Allocation rate**: lượng cấp phát mỗi giây, ví dụ MiB/s.
- Chúng phản ánh **churn**, không phải toàn bộ live heap.
- Một service có thể cấp phát hàng GiB mỗi phút nhưng live set chỉ vài trăm MiB nếu object chết nhanh và được GC thu hồi.

Ví dụ:

```text
Trong 60 giây:
  Java code yêu cầu nhiều arrays ngắn hạn
  Tổng allocation: 800 MiB (đo/ước lượng)
  Live data sau GC: 80 MiB

=> Allocation rate cao.
=> Không có đủ bằng chứng nói đây là memory leak.
```

### 3.2. Live set và retained memory

- **Live set**: những object còn reachable tại thời điểm quan sát theo tiêu chuẩn GC.
- **Retained size**: khối lượng object sẽ trở nên unreachable nếu một object/nhóm tham chiếu bị loại, phụ thuộc object graph.
- **Heap used** từ một thời điểm không phải tổng byte đã cấp phát suốt chương trình.
- Một đối tượng lớn có thể được tạo rồi bỏ ngay, làm tăng allocation volume nhưng **không** tăng retained heap lâu dài.

### 3.3. Collection cost

GC có thể gồm:

- **Pause time** của các pha stop-the-world (STW).
- **Concurrent CPU work** trên các GC threads.
- **Barrier/remembered-set maintenance** khi mutator đang làm việc, tùy collector.
- **Object copying, marking, reference processing, class metadata interactions** theo thuật toán.
- **Safepoint/coordination overhead** và hệ quả đối với latency.
- **Cache/memory bandwidth competition** với application threads.

**Không có một phép trừ số học đơn giản** giữa hai bộ thu gom đủ để tách các thành phần đó. Lượng live data, layout heap và quyết định JIT/GC có thể khác khi thay collector.

## 4. Epsilon GC là gì? (JEP 318)

**Epsilon — A No-Op Garbage Collector** là một bộ thu gom trong HotSpot có **allocator** nhưng không có cơ chế thu hồi vùng heap đã cấp phát cho objects. Nó được giới thiệu từ **JDK 11** như tính năng thử nghiệm, phục vụ:

- Làm **đối chứng** khi nghiên cứu các overhead của collectors khác.
- Đo **memory footprint/pressure** bằng cách để allocation tích lũy, từ đó thử giới hạn heap của một workload hữu hạn.
- Chạy **short-lived jobs** có tổng allocation nằm trong giới hạn heap, khi xác định rõ không cần thu gom trong tuổi thọ process.
- Thử một số tính chất của ứng dụng và hạ tầng JVM khi không có GC reclamation.

Epsilon **không** thay thế G1, Parallel, ZGC hay collectors production được lựa chọn theo workload. Nếu chương trình chạy lâu và liên tục cấp phát, mọi object không còn reachable vẫn **không được thu hồi**, nên heap cuối cùng sẽ hết và JVM có thể kết thúc với `OutOfMemoryError`. Việc nâng `-Xmx` chỉ trì hoãn điểm cạn heap, không làm Epsilon trở thành collector thu gom được.

### 4.1. Epsilon vẫn làm những gì?

| Hành vi | Với Epsilon |
| --- | --- |
| Cấp phát object/array | **Có** |
| Cần quản lý vùng heap | **Có** |
| Khởi tạo mảng, ghi field, tính checksum | **Có** |
| Sử dụng CPU, caches, memory bandwidth | **Có** |
| TLAB/allocator fast path và slow path | **Có**, implementation có thể khác G1 |
| Mở rộng/commit bộ nhớ theo heap policy | Có thể, tùy cờ và JVM |
| Thu hồi object unreachable | **Không** |
| Thực hiện GC cycles để reclaim heap | **Không** |
| Không bao giờ hết bộ nhớ | **Sai** |
| Đảm bảo application không có pause nào | **Sai**: JIT/safepoint/OS/I/O vẫn có thể gây gián đoạn |

**Epsilon là “no-op” ở việc thu hồi**, không phải “zero-cost memory allocation” hay “zero-latency JVM”.

### 4.2. Vì sao Epsilon hữu ích khi đo?

Nó loại bỏ cơ chế **GC reclamation** khỏi một kịch bản thử nghiệm có kiểm soát. Nếu workload tồn tại được trong heap mà không cần reclaim, Epsilon cho biết điều gì xảy ra khi chương trình vẫn thực hiện các allocations, business work và JVM activities khác nhưng không chạy các GC collection cycles thông thường.

Điều đó giúp trả lời **“allocation path và business work có đáng kể ngay cả khi không collect không?”** nhưng chưa trả lời **“G1 mất chính xác bao nhiêu thời gian riêng cho GC?”**.

### 4.3. Cách bật Epsilon trên HotSpot

Dùng các option quen thuộc của Java 11:

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -version
```

Đây là **lệnh kiểm tra runtime**, không phải benchmark. Trên HotSpot có Epsilon, `-XX:+UnlockExperimentalVMOptions` mở nhóm experimental flags và `-XX:+UseEpsilonGC` chọn Epsilon. Nếu JVM không hỗ trợ, lệnh có thể từ chối cờ; không tự tắt lỗi rồi báo phép đo đã chạy với Epsilon.

Trong phép đo hãy thêm heap limits và GC logging; ví dụ hoàn chỉnh ở mục 8. Không bật Epsilon cho production JVM đang xử lý request thật nếu chưa có chứng minh tổng allocation, failure behavior và chính sách OOME phù hợp. Tránh chạy “thử” trên service có dữ liệu quan trọng.

## 5. Mô hình thời gian: vì sao không lấy hiệu G1 − Epsilon làm chi phí GC?

Một mô hình khái niệm:

```text
T_wall(G1)
 = T_business
 + T_allocator(G1)
 + T_JIT_runtime
 + T_GC_STW
 + T_GC_concurrent_interference
 + T_barriers(G1)
 + T_OS_scheduler_memory
 + các thành phần chồng lấn/phụ thuộc khác

T_wall(Epsilon)
 = T_business'
 + T_allocator(Epsilon)
 + T_JIT_runtime'
 + T_OS_scheduler_memory'
 + chi phí riêng của Epsilon
```

Dấu phẩy trên biểu thị các đại lượng **có thể không giống nhau** giữa hai lần chạy:

- Allocator và layout/placement có thể khác.
- Một collector có write barriers, card table/remembered set; collector khác thì không cùng cơ chế.
- Heap commit/page faults, locality, TLAB behavior và object lifetime khác.
- JIT warm-up, code generation, CPU frequency, caching và lịch chạy OS có nhiễu.
- G1 có thể không phải lúc nào cũng thực hiện collection trong đoạn đo ngắn; Epsilon lại tiếp tục tích lũy memory và có thể làm pressure cao hơn.
- GC concurrency có thể **chồng lấn** thời gian mutator, khiến “tổng GC CPU time” không bằng một lượng wall time có thể trừ trực tiếp.

**Kết luận đúng:** so sánh là một *controlled experiment* để phân tách ảnh hưởng hệ thống theo giả thuyết. **Kết luận sai:** nếu G1 mất 10 ms, Epsilon mất 8 ms thì “GC cost = 2 ms”. Hai bộ chạy khác nhau về nhiều cơ chế, và 2 ms có thể nằm trong nhiễu.

### 5.1. Ba câu hỏi đo riêng

1. **Cấp phát nhiều không?** Đo *allocation rate* bằng công cụ phù hợp, không suy chỉ từ heap-used delta.
2. **GC có hoạt động không?** Kiểm tra GC count, GC logs/JFR GC events và khoảng thời gian tương ứng.
3. **GC ảnh hưởng người dùng bao nhiêu?** Đo p95/p99 latency, throughput, mutator utilization, STW pause và concurrent CPU trong điều kiện gần production.

## 6. Chuẩn bị môi trường thử nghiệm

Trước khi chạy:

```bash
java -version
javac -version
```

Ghi lại **vendor, Java version, OS/architecture, CPU limits, GC được chọn và heap options**. Dùng cùng JVM executable cho các lượt G1/Epsilon; không so Java 11 Epsilon trên một máy với Java 25 G1 trên máy khác rồi gán mọi chênh lệch cho GC.

Với Java 11, tùy chọn `javac --release 11` đảm bảo ví dụ dùng API và classfile tương thích Java 11. Khi chạy với JDK mới hỗ trợ target này, vẫn ghi rõ runtime JDK thực tế: biên dịch target 11 **không tự biến runtime mới thành JDK 11**.

### 6.1. Kiểm soát heap và JVM options

Ví dụ các giá trị cho **demo ngắn**:

```text
-Xms128m
-Xmx128m
-Xlog:gc
```

- `-Xms128m`: initial heap size.
- `-Xmx128m`: max Java heap size.
- `-Xlog:gc`: Unified JVM Logging từ Java 9+, ghi log về GC.
- G1: `-XX:+UseG1GC`.
- Epsilon: `-XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC`.

Giữ `-Xms` và `-Xmx` giống nhau trong cặp so sánh, nhưng hiểu **cùng heap limit chưa làm mọi yếu tố khác giống nhau**. Nếu chạy container, phải tính thêm giới hạn cgroup và native memory ngoài Java heap.

**Không** dùng các flag GC logging cũ của Java 8 làm mặc định cho Java 11; `-Xlog` là hướng đang áp dụng trên các JDK hiện đại.

## 7. Java 11 mẫu: tạo allocation thật, không tự giả định kết quả GC

Tạo file **`EpsilonCostDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public final class EpsilonCostDemo {
    private static volatile byte[] last;

    static long gcCount() {
        long total = 0;
        for (GarbageCollectorMXBean gc
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = gc.getCollectionCount();
            if (count < 0) {
                return -1;
            }
            total += count;
        }
        return total;
    }

    public static void main(String[] args) {
        int arrays = args.length > 0
                ? Integer.parseInt(args[0]) : 12000;
        int bytes = args.length > 1
                ? Integer.parseInt(args[1]) : 4096;
        if (arrays <= 0 || bytes <= 0) {
            throw new IllegalArgumentException(
                    "positive values required");
        }

        long beforeGC = gcCount();
        long t0 = System.nanoTime();
        long checksum = 0;

        for (int i = 0; i < arrays; i++) {
            byte[] a = new byte[bytes];
            a[0] = (byte) i;
            last = a;
            checksum += a[0] & 0xff;
        }

        long elapsed = System.nanoTime() - t0;
        long afterGC = gcCount();

        System.out.println("arrays=" + arrays);
        System.out.println("array_payload_bytes=" + bytes);
        System.out.println("requested_payload_bytes="
                + ((long) arrays * bytes));
        System.out.println("checksum=" + checksum);
        System.out.println("last_array_length=" + last.length);
        System.out.println("elapsed_ms="
                + (elapsed / 1000000.0));
        System.out.println("gc_count_delta="
                + (beforeGC >= 0 && afterGC >= 0
                   ? Long.toString(afterGC - beforeGC)
                   : "unavailable"));
    }
}
```

Đây là chương trình **độc lập**, chỉ dùng những API có trong Java 11. Nó tạo mảng `byte[]` có kích thước tham số, ghi vào một `volatile` static field để đối tượng **escape**, và tính checksum để công việc có thể được quan sát. Vòng lặp không giữ lại mọi mảng: sau lần gán tiếp theo, mảng trước có thể trở thành unreachable.

### 7.1. Giải thích chi tiết

1. `arrays`: số lần tạo array trong vòng lặp; mặc định **12.000**.
2. `bytes`: payload length của mỗi `byte[]`; mặc định **4.096**.
3. `new byte[bytes]`: mỗi vòng yêu cầu tạo một array và zero-initialization theo semantics Java.
4. `a[0] = (byte) i`: thay đổi dữ liệu để có checksum ổn định.
5. `last = a`: volatile write khiến array reference phải có hiệu ứng quan sát được, làm khó cho JIT việc loại bỏ toàn bộ allocations như một benchmark vô nghĩa.
6. `checksum += a[0] & 0xff`: dùng byte như giá trị không dấu để phép tính xác định.
7. `System.nanoTime()`: đo elapsed duration của **đoạn vòng lặp**, không phải CPU time hay chỉ GC time.
8. `gcCount()`: cộng số lần collection do các `GarbageCollectorMXBean` báo; trả `-1` nếu có counter không xác định.
9. Chương trình in **đầu vào và checksum** (xác định) tách khỏi **elapsed_ms/gc_count_delta** (có thể thay đổi).
10. Không dùng `System.gc()` để “tạo điều kiện giống nhau”; explicit GC sẽ là tác nhân nhiễu khác và Epsilon không reclaim memory chỉ vì gọi nó.

**Tính đúng của demo:** `last` chỉ giữ reference tới **mảng cuối** khi loop xong. Các mảng trước không nhất thiết còn reachable. Với G1, chúng có thể được thu hồi nếu collector cần; với Epsilon chúng **không được thu hồi** trong thời gian process tồn tại, dù không còn reachable.

### 7.2. Payload bytes khác actual allocated bytes

Với mặc định:

```text
12000 * 4096 = 49,152,000 payload bytes
```

Đây là **số byte payload do vòng lặp yêu cầu**, không phải tổng Java heap allocation chính xác:

- Mỗi array có **object header**, length metadata và alignment.
- JVM/JDK có thể tự cấp phát thêm objects ngoài vòng lặp.
- JIT/allocator có thể có cơ chế riêng; field `volatile` giúp việc cấp phát có thể quan sát nhưng không biến payload bytes thành một phép đo tổng heap của process.
- `System.nanoTime()` và `ManagementFactory` có overhead; lần lấy thông tin đầu có thể kích hoạt class loading/JMX initialization.

Vì vậy, dòng `requested_payload_bytes` **không phải** một allocation profiler counter; nó là tính toán số học từ tham số và source.

## 8. Chạy đúng hai phiên so sánh

### 8.1. Biên dịch

```bash
javac --release 11 -encoding UTF-8 EpsilonCostDemo.java
```

Tên file phải trùng public class. Chạy trong thư mục chứa `EpsilonCostDemo.class`, hoặc dùng `-cp` trỏ đúng thư mục.

### 8.2. G1: có cơ chế thu gom thực sự

```bash
java -Xms128m -Xmx128m -XX:+UseG1GC -Xlog:gc EpsilonCostDemo
```

G1 có thể tạo các dòng `GC(n) Pause Young ...` khi cần thu gom. **Không bảo đảm** GC count luôn dương trong mọi môi trường; phụ thuộc JVM/heap, workload và lúc đo.

### 8.3. Epsilon: có allocation nhưng không reclaim

```bash
java -Xms128m -Xmx128m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xlog:gc EpsilonCostDemo
```

Ở một HotSpot hỗ trợ Epsilon, log có thể chứa `Using Epsilon` và các thông báo về heap usage. **Dòng `[gc] Heap: ... used` không chứng minh đã có thu gom**; đây có thể chỉ là thông báo thống kê heap Epsilon.

### 8.4. Output: giá trị nào cố định, giá trị nào thay đổi?

Phần **xác định từ Java source**, khi chạy mặc định thành công:

```text
arrays=12000
array_payload_bytes=4096
requested_payload_bytes=49152000
checksum=1526416
last_array_length=4096
```

Chương trình còn in hai dòng **giá trị đo không cố định**:

```text
elapsed_ms=<số đo thực tế của lần chạy>
gc_count_delta=<số nguyên hoặc unavailable>
```

Hai dòng trên là **mô tả định dạng**, không phải stdout cố định. Nếu chạy với `-Xlog:gc`, log JVM có thể xuất hiện trước/sau các dòng ứng dụng, nên **không** so nguyên output terminal byte-for-byte.

Một lần **đã chạy kiểm chứng** với OpenJDK 24, biên dịch `--release 11` và heap 128 MiB:

| Điều kiện | `requested_payload_bytes` | `checksum` | Ví dụ kết quả GC | Ví dụ elapsed |
| --- | ---: | ---: | --- | --- |
| G1 | 49.152.000 | 1.526.416 | `gc_count_delta=1`, một young GC pause trong log | khoảng 8 ms |
| Epsilon | 49.152.000 | 1.526.416 | `gc_count_delta=0`, log `Using Epsilon` và heap usage | khoảng 8 ms |

**Đây là một phép chạy minh họa, không phải benchmark đáng tin về hiệu năng.** Kết quả khác trên Java 11/runtime khác là bình thường. Không suy rằng G1 và Epsilon luôn bằng nhau hoặc Epsilon luôn nhanh hơn. Trong phép chạy mẫu, thời gian gần bằng nhau dù G1 đã có một GC pause nhỏ; điều này cho thấy vì sao kết luận đơn giản từ một lượt chạy dễ sai.

### 8.5. Vì sao `GarbageCollectorMXBean` chưa đủ đo GC cost?

`GarbageCollectorMXBean.getCollectionCount()` trả số collection theo bean; có thể trả **-1** nếu không xác định. `getCollectionTime()` trả **thời gian collection tích lũy xấp xỉ** (milliseconds) hoặc -1. Đây là **counters coarse-grained**, không phải bản ghi chính xác mọi pause/pha concurrent trên mọi collector.

Ngoài ra, chương trình cộng count từ nhiều beans; với các collector khác nhau, counters có thể có semantics riêng hoặc một số operation có liên hệ chéo. Không mặc định lấy tổng count làm “số distinct pause” với mọi JVM.

Muốn tìm **thời gian và loại pause**, đối chiếu `-Xlog:gc`/JFR GC events. Muốn biết **concurrent GC CPU**, cần tools có phân tích thread CPU/runtime phù hợp. Chỉ nhìn `getCollectionTime()` không tự có được phân tách hoàn chỉnh.

## 9. Epsilon sẽ cạn heap nếu tiếp tục cấp phát

Khi G1 chạy cùng một workload với đủ heap, các array cũ có thể không còn reachable và được reclaim. Với Epsilon, vùng heap dùng cho những array cũ **không bao giờ được trả lại để tái sử dụng bởi bộ thu gom**.

### 9.1. Thử trong tiến trình phụ có giới hạn

Chỉ trong thư mục test và sẵn sàng nhận tiến trình thất bại:

```bash
java -Xms64m -Xmx64m -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xlog:gc EpsilonCostDemo 20000 4096
```

Vòng lặp yêu cầu khoảng **81.920.000 byte payload**, vượt giới hạn heap **64 MiB** chưa tính object headers/runtime. Trên HotSpot có Epsilon và các allocations thực sự được thực hiện, JVM sẽ cạn khả năng cấp phát và kết thúc lỗi; **không hứa một exception message hay exit code duy nhất** trên mọi JVM.

Đây là **kịch bản cố ý gây OOME**, không phải phép chạy thành công. Không chạy với dữ liệu/nghiệp vụ thật, không cấu hình như service production. Một container có giới hạn memory hoặc OOM killer của OS có thể giết process vì memory pressure theo cách khác, nên phân biệt **Java heap OOME** với **OS/cgroup OOM kill**.

### 9.2. Vì sao Epsilon rất khác memory leak?

- Trong **G1**, object đã chết được thu gom khi GC chạy; heap usage có thể tăng/giảm theo cycle.
- Trong **Epsilon**, ngay cả object **không còn reachable** vẫn chiếm không gian đã cấp phát vì **không có reclamation**.
- Vì vậy, **Epsilon heap tăng liên tục không chứng minh application leak**.
- Ngược lại, service có retained-memory leak khi chạy G1 phải được khảo sát bằng live heap, heap dump/retained graph, object lifetime và GC logs phù hợp.

Epsilon là công cụ cố tình tạo điều kiện **không thu gom**, nên không thể dùng đặc điểm của nó làm định nghĩa memory leak.

## 10. Phân biệt chi phí cấp phát và thu gom qua các nguồn dữ liệu

| Nguồn đo | Trả lời tốt | Không tự chứng minh |
| --- | --- | --- |
| `System.nanoTime()` quanh loop | Wall elapsed của đoạn code | GC-only time, CPU riêng của thread |
| `GarbageCollectorMXBean` | Collection count/time xấp xỉ theo bean | Mọi pause, concurrent interference, allocation bytes |
| `-Xlog:gc` | Thời điểm, loại, duration của GC phases/events có log | Tổng allocation volume chính xác |
| `MemoryMXBean.getHeapMemoryUsage().getUsed()` | Heap used tại một thời điểm | Cumulative allocated bytes |
| `com.sun.management.ThreadMXBean` | Allocation bytes **xấp xỉ theo thread** khi JVM hỗ trợ | Toàn bộ hệ thống hay retained bytes |
| **JFR** | Timeline GC, allocation events theo setting, CPU/threads | Mỗi allocation tuyệt đối hoặc zero overhead |
| JMH | Microbenchmark có harness, warm-up, nhiều iterations/forks | Tự suy ra GC overhead chỉ từ một score |
| Heap dump/heap histograms | Những object còn sống ở snapshot, retained references | Mọi allocation đã chết trước snapshot |
| OS metrics | RSS, page faults, CPU, memory pressure | Phân tách Java heap vs native vs GC tự động |

### 10.1. `MemoryMXBean`: heap used không phải allocation total

```java
long used = ManagementFactory
        .getMemoryMXBean()
        .getHeapMemoryUsage()
        .getUsed();
```

Đây là **trích đoạn Java 11**, cần import `java.lang.management.ManagementFactory`. Dòng trả số byte heap used **tại thời điểm đo**, không cho biết bao nhiêu byte được tạo trong cả khoảng. Với G1, GC có thể thu hồi object trước khi đọc used. Với Epsilon, used thường tăng nhanh do không reclaim; nhưng đây vẫn không phải số byte cấp phát chính xác của một vòng lặp.

### 10.2. `com.sun.management.ThreadMXBean`: số byte được cấp phát

Trên HotSpot hỗ trợ `jdk.management`, có thể đọc thông tin allocation theo thread. Ví dụ **trích đoạn**, không phải chương trình độc lập:

```java
java.lang.management.ThreadMXBean base =
        ManagementFactory.getThreadMXBean();
if (base instanceof com.sun.management.ThreadMXBean) {
    com.sun.management.ThreadMXBean bean =
            (com.sun.management.ThreadMXBean) base;

    if (bean.isThreadAllocatedMemorySupported() &&
            bean.isThreadAllocatedMemoryEnabled()) {
        long threadId = Thread.currentThread().getId();
        long allocated = bean.getThreadAllocatedBytes(threadId);
        // allocated >= 0 nếu measurement hợp lệ.
    }
}
```

Đây là **API mở rộng phụ thuộc JVM**, không phải một hợp đồng cho mọi Java SE implementation; còn cần module `jdk.management` trong runtime image. `getThreadAllocatedBytes` trả **ước lượng tích lũy theo thread**, và phép đo có thể bị disabled/unsupported. Với JDK mới có virtual threads, cần kiểm tra semantics của API theo version, không tự áp hướng dẫn Java 11 cho mọi thread model hiện đại.

Nếu muốn đo **delta allocation** cho loop, lấy snapshot trước/sau cùng thread và kiểm tra kết quả >=0; không đồng nhất nó với array payload length hoặc `heapUsedAfter - heapUsedBefore`.

**Không sử dụng `getCurrentThreadAllocatedBytes()` trong mã yêu cầu tương thích mọi bản Java 11**, vì API convenience method có lịch sử bổ sung khác nhau giữa update releases; dùng `getThreadAllocatedBytes(Thread.currentThread().getId())` phù hợp khi extension hỗ trợ.

### 10.3. JFR và GC logs

Java 11 có JDK Flight Recorder tích hợp. Bật một recording ngắn để phân tích GC/CPU, ví dụ **trích đoạn lệnh**:

```bash
java -XX:StartFlightRecording=filename=run.jfr,duration=30s,settings=profile -Xms128m -Xmx128m -XX:+UseG1GC EpsilonCostDemo
```

Lệnh chỉ nên dùng khi JFR khả dụng và permission/file path phù hợp; file có thể được ghi khi recording kết thúc theo policy. Với chương trình chạy rất ngắn, phiên `duration=30s` có thể không tạo data mong muốn trước khi app thoát. Để test startup-to-exit nhỏ, dùng `-XX:StartFlightRecording=filename=run.jfr,dumponexit=true,settings=default` hoặc dùng `jcmd JFR.dump` trên ứng dụng chạy đủ lâu.

JFR có các event GC và allocation như `jdk.GarbageCollection`, `jdk.ObjectAllocationInNewTLAB`/`jdk.ObjectAllocationOutsideTLAB` tùy cài đặt. Không mặc định những event này ghi **đủ mọi allocation**; profile/threshold/sampling khác nhau theo JDK và settings. Với các trường/units cụ thể, kiểm tra schema thực của file và JDK.

### 10.4. GC logging phù hợp Java 11

```bash
java -Xms128m -Xmx128m -XX:+UseG1GC -Xlog:gc*:file=g1-gc.log:uptime,level,tags EpsilonCostDemo
```

Tham số ghi log kiểu Unified Logging, có thể có nhiều tag/pha GC. Với production, thêm file rotation và quota để log không làm đầy disk:

```bash
java -Xms128m -Xmx128m -XX:+UseG1GC -Xlog:gc*:file=g1-gc.log:uptime,level,tags:filecount=5,filesize=10m EpsilonCostDemo
```

Đây là **lệnh mẫu**: quyền ghi vào thư mục hiện hành cần hợp lệ và pattern `filecount/filesize` có thể được điều chỉnh theo volume. Không tự phân tích GC log của Epsilon như có stop-the-world collection chỉ vì output mang tag `gc`; Epsilon có thể in thống kê mức heap dùng.

## 11. Thiết kế benchmark đúng: tách microbenchmark và system benchmark

Chương trình `EpsilonCostDemo` chứng minh **cách quan sát**, nhưng tự nó **chưa** là phép benchmark đủ tin cậy. Để đo hiệu năng:

### 11.1. Tránh những lỗi làm benchmark vô nghĩa

- **Không warm-up:** JIT chưa tối ưu mã, lần đo đầu có class loading và compilation.
- **Chỉ đo một lần:** noise từ OS scheduler, CPU frequency, page faults, antivirus, VM background work.
- **Kết luận từ `System.currentTimeMillis()`:** độ phân giải/semantics không phù hợp cho microbenchmark ngắn; dùng `System.nanoTime()` cho elapsed.
- **Object không escape:** JIT có thể loại bỏ allocations, sai mục tiêu.
- **Đặt logging trong hot loop:** chi phí I/O che mất allocation.
- **Đo khi heap gần OOME:** Epsilon memory pressure tăng theo thời gian, làm các lượt sau không còn điều kiện tương đương.
- **Trộn JVM versions/vendors:** thay đổi JIT/allocator/GC khác nhau; không quy hết về collector.
- **Đổi `-Xmx` không kiểm soát:** khác heap size làm GC policy khác, không so công bằng.
- **Đo `System.gc()` rồi tuyên bố chi phí GC thực tế:** explicit GC không phản ánh chính sách thu gom dưới tải thông thường.
- **Chạy một process hàng trăm iterations Epsilon:** heap chỉ tăng, không có reset; phải restart JVM cho mỗi fork hợp lý.
- **Dùng heap-used delta làm allocation rate:** với collector thực tế, GC đã reclaim có thể làm delta nhỏ hoặc âm.

### 11.2. JMH cho microbenchmark đáng tin hơn

**Java Microbenchmark Harness (JMH)** hỗ trợ warm-up, measurement iterations, forks, blackholes và các profiler hooks. Nó hữu ích để giảm sai lệch do JIT và đo thao tác nhỏ, nhưng **vẫn không tự tách allocation cost khỏi GC cost** nếu thiết kế đo không phù hợp.

Một kế hoạch JMH cần:

1. Xác định chính xác method đang benchmark.
2. Dùng `Blackhole` hoặc cơ chế escape hợp lệ để không loại bỏ công việc.
3. Đo allocation bằng profiler/ThreadMXBean/JFR có giới hạn và so score.
4. Warm-up đủ, dùng nhiều forks **mỗi fork là một JVM mới**.
5. Bảo đảm mỗi fork Epsilon có **ngân sách heap đủ lớn cho tổng allocations của cả warm-up + measurement**; nếu OOME thì giảm work/fork hoặc tăng heap có kiểm soát, không xóa hết pha warm-up cho vừa heap.
6. Chạy cùng JVM/flags/workload khi đổi collector, và xem variation/confidence intervals.
7. Quan sát GC count và pause logs bên cạnh score.

**Lưu ý:** JMH là **thư viện/harness cần thêm dependency**, không thuộc Java standard library. Bài này ưu tiên mẫu không cần dependency; nếu dùng JMH thật, cấu hình build/Maven/Gradle và plugin đúng phiên bản JDK/JMH hiện hành.

### 11.3. System benchmark cho ứng dụng thực

Sau microbenchmark, đo **end-to-end** tại throughput và load đại diện:

- p50/p95/p99 request latency, error rate, throughput.
- CPU usage và CPU time của GC workers (nếu công cụ đo hỗ trợ).
- GC pause time distribution, số collections, memory reclaimed, old-gen pressure.
- Allocation rate và live-set after GC.
- Heap/committed/native memory, RSS, page faults và container limits.
- Warm-up của JIT, class loading, background threads, storage/network.
- Số lần chạy, độ lệch chuẩn/confidence interval thay vì chỉ một điểm số.

Epsilon chỉ thích hợp nếu workload hoàn tất trước khi heap cạn. Nó **không** là cấu hình thử nghiệm tốt cho một server load test kéo dài nhiều giờ mà không có giới hạn allocation.

## 12. Các trường hợp quan sát thường gặp và cách diễn giải

### Trường hợp A: G1 có nhiều young GC, Epsilon không thu gom

**Quan sát:** cùng vòng loop tạo arrays; G1 log có `Pause Young`, Epsilon log chỉ có `Using Epsilon`/heap usage, thời gian Epsilon vẫn không bằng 0.

**Diễn giải:** vòng loop vẫn thực hiện allocation và khởi tạo; GC young pauses là **một phần** chi phí của G1. Không thể từ đây suy toàn bộ khác biệt elapsed do pause, vì còn allocator, barriers, JIT và memory layout.

### Trường hợp B: Epsilon chạy chậm hơn trong một lần thử

**Có thể xảy ra.** Nếu Epsilon phải commit nhiều trang mới, heap pressure cao, cache locality kém hoặc OS scheduler làm nhiễu, elapsed có thể cao hơn G1. Điều này **không** chứng minh “GC làm chương trình nhanh hơn” theo mọi điều kiện; chỉ ra phép đo cần phân tích lại các biến chưa được kiểm soát.

### Trường hợp C: G1 `gc_count_delta=0` trong đoạn loop

**Không** có nghĩa allocation miễn phí; có thể heap đủ lớn hoặc GC xảy ra ngoài cửa sổ đọc MXBean. Nếu GC không xảy ra trong đoạn đo, bạn vẫn đo được allocation + application work. Dùng GC logs/timestamps để xác nhận sự kiện và xem toàn bộ process lifecycle.

### Trường hợp D: Epsilon OOME trước khi có kết quả

Chương trình không đủ heap để hoàn thành allocation. **Không** lấy elapsed của một run đã fail OOME so với một run G1 thành công. So sánh chỉ có ý nghĩa khi cả hai hoàn tất **cùng nghiệp vụ**; run OOME chỉ minh họa heap exhaustion, không phải hiệu năng.

### Trường hợp E: Allocation rate cao nhưng heap sau GC thấp

Object có thể rất ngắn hạn, collector thu hồi được. Đây có thể là **allocation churn**, gây GC work hoặc memory bandwidth, nhưng chưa phải retained-memory leak. Kiểm tra GC pressure và p99 latency để quyết định tối ưu.

### Trường hợp F: Live heap tăng lâu dài dưới G1

Khi sau full/major GC hoặc các khoảng ổn định live set vẫn tăng, cần điều tra retained references, caches, queues, resource lifecycle. Epsilon không thể giúp kết luận leak vì nó **chủ động không reclaim**, khiến heap tăng ngay cả với ứng dụng không leak.

## 13. TLB, TLAB, memory bandwidth và barrier: nhóm chi phí chồng lấn

### 13.1. TLAB và cấp phát nhanh

Trong HotSpot, nhiều object nhỏ được cấp phát trong **TLAB**. Khi thread còn vùng nhớ, cấp phát có thể gần như cập nhật một pointer và zero-initialize theo cơ chế runtime. Nhưng:

- TLAB refill cần tương tác allocator/heap policy.
- Object header/alignment và initialize vẫn có chi phí.
- Dữ liệu ghi sau allocation có thể gây cache writes.
- Các kiểu allocation đặc biệt, rất lớn hoặc không phù hợp TLAB có đường xử lý khác.

**Epsilon cũng có allocator/TLAB behavior.** Đừng suy rằng Epsilon bỏ luôn TLAB hoặc mọi allocation chậm như `malloc` mỗi lần; đó là mô hình sai.

### 13.2. Write barriers thuộc overhead của collector nhưng xuất hiện trên mutator path

Ví dụ khi một object field được cập nhật, một collector cần cập nhật metadata (như card table/remembered sets) để theo dõi references giữa vùng/đời object. Một phần cost có thể xảy ra **ngay tại thread ứng dụng**, không tạo GC pause riêng. Nó nằm giữa khái niệm **allocation path** và **collection bookkeeping**.

Vì vậy phép đo muốn tách “allocation cost thuần” khỏi “GC-related mutator overhead” phải xác định cụ thể **thành phần nào** được tính vào từng nhóm; Epsilon không đưa ra một phép tách chuẩn duy nhất.

### 13.3. Epsilon và sự không tương đương của heap state

Ở G1, object chết được reclaim và các vùng heap tái sử dụng, ảnh hưởng cache/memory locality. Ở Epsilon, allocation pointer liên tục đi về phía cuối heap. Cùng một vòng loop có thể truy cập các trang vật lý khác nhau, gây khác page faults và cache behavior. **Cùng `-Xmx` không có nghĩa cùng state của heap từng millisecond.**

## 14. Dùng dữ liệu đo để quyết định tối ưu code

Mục tiêu cuối không phải tìm “GC xấu bao nhiêu” mà là giảm chi phí user thấy và chi phí hạ tầng.

### 14.1. Khi allocation cost mới là vấn đề chính

Dấu hiệu:

- Allocation rate rất cao, throughput kém **ngay cả khi không có GC pause** đáng kể.
- CPU profile cho thấy object construction, array zeroing, serialization/formatting.
- Memory bandwidth/cache misses lớn ở workload xử lý mảng, buffer.
- GC count thấp nhưng allocation-heavy hot loop vẫn chiếm CPU.

Hướng xử lý:

- Bỏ allocation không cần thiết ở hot path.
- Dùng stream/buffer reuse có kiểm soát khi đúng semantics và không tạo data races.
- Tránh tạo temporary String/collection trong loop không cần.
- Chọn cấu trúc dữ liệu phù hợp và đo lại sau tối ưu.
- Đừng pool mọi object nhỏ tùy ý: object pooling có thể tăng contention/retention và làm GC khó hơn.

### 14.2. Khi collection cost mới nổi bật

Dấu hiệu:

- GC logs/JFR có nhiều pause dài trùng thời điểm p99 latency spike.
- Mutator time/throughput giảm khi collector làm việc dưới heap pressure.
- Heap utilization, old-gen occupancy và live set khiến collector phải hoạt động thường xuyên.
- GC workers dùng CPU đáng kể trong thời gian cao tải.

Hướng xử lý:

- Giảm allocation rate và **retention** không cần thiết nếu có.
- Kiểm tra heap sizing, GC algorithm phù hợp SLA và JDK hiện hành.
- Xem object lifetime, cache/queue không giới hạn, memory leak thật.
- Đối chiếu CPU contention; một collector concurrent có thể cải thiện pause nhưng tăng CPU overhead khác.
- Đo lại throughput, p95/p99 và memory footprint trước khi chấp nhận tuning.

### 14.3. Đừng thay business semantics chỉ để giảm allocations

Một tối ưu hóa “không cấp phát nữa” có thể đổi thread safety, thứ tự kết quả, lifetime buffer hoặc làm dữ liệu bị ghi đè. Mọi phép tối ưu phải giữ tính đúng của chương trình và test regression, không chỉ có điểm số microbenchmark đẹp hơn.

## 15. Lộ trình thí nghiệm A/B có thể lặp lại

| Bước | Cách làm | Bằng chứng cần giữ |
| --- | --- | --- |
| 1. Cố định code | Một build `EpsilonCostDemo.class` hoặc application artifact giống nhau | Hash build, source/commit |
| 2. Cố định runtime | Cùng JDK/vendor, CPU/memory limits, OS | `java -version`, flags |
| 3. Chọn workload | N loops, array size, thời gian đủ ngắn cho Epsilon | Inputs, checksum, success |
| 4. Chọn heap | Cùng `-Xms/-Xmx`; đủ Epsilon hoàn tất | Heap size, logs |
| 5. G1 baseline | Nhiều runs/forks, warm-up có kiểm soát | elapsed, GC logs, p95/p99 |
| 6. Epsilon control | Nhiều **fresh JVMs**, không reuse heap tích lũy | elapsed, used heap, no GC reclaim |
| 7. Phân tích GC | Correlate pause/concurrent activity với application timing | GC logs/JFR, CPU |
| 8. Phân tích allocation | Thread allocation counters/JFR hay tool phù hợp | Allocated bytes/rate |
| 9. Kiểm tra nhiễu | JIT, TLAB, CPU throttling, page faults, OS scheduling | Profiling/host metrics |
| 10. Kết luận | Nêu giả thuyết, confidence, limitations | Báo cáo có thể tái lập |

**Cảnh báo về thứ tự chạy:** chạy G1 10 lần rồi Epsilon 10 lần có thể bị ảnh hưởng bởi nhiệt độ CPU hoặc tải máy thay đổi theo thời gian. Nên randomize hoặc xen kẽ các lần chạy độc lập, đồng thời đảm bảo mỗi run không dùng lại state không kiểm soát.

**Cảnh báo về JIT warm-up:** Epsilon không reclaim nên không thể warm-up vô hạn trong một JVM. Đánh giá tổng allocations của toàn fork bao gồm warm-up; nếu không vừa heap, rút ngắn workload hoặc dùng harness/forks phù hợp và trình bày giới hạn, đừng so một bên đã warm-up với một bên chưa.

## 16. Những sai lầm thường gặp

| Sai lầm | Vì sao sai? | Thực hành đúng |
| --- | --- | --- |
| “Không có GC thì allocation miễn phí” | Allocator/zeroing/cache/heap vẫn có cost | Đo allocation path riêng |
| “Epsilon không tạo object” | Epsilon **vẫn cấp phát** | Epsilon chỉ không reclaim |
| “Epsilon chạy nhanh hơn = chi phí GC chính xác” | Khác allocator/barriers/JIT/heap state | Coi là control experiment, không trừ trực tiếp |
| “Không GC thì không bao giờ dừng” | JVM vẫn có JIT, safepoints, OS pauses | Đo latency thực |
| “Epsilon heap tăng là memory leak” | No reclamation ngay cả khi object dead | Dùng retained/live heap analysis |
| “GC count=0 thì allocation rate=0” | Hai counter khác nhau | Đo allocation bytes/rate |
| “Tổng payload array = total allocated heap” | Thiếu headers/alignment/JVM allocations | Dùng profiler/counters thích hợp |
| “Heap used delta = allocated bytes” | GC có thể reclaim trước snapshot | Đo cumulative allocation |
| “Mọi `new` trong source đều cấp phát” | JIT có thể scalar-replace hoặc eliminate | Đảm bảo escape/observability, benchmark đúng |
| “Đổi heap size không ảnh hưởng fairness” | GC policy/page faults thay đổi | Kiểm soát `-Xms/-Xmx` |
| “Chạy Epsilon lâu cho chắc” | Heap tích lũy đến OOME | Short, bounded runs và fresh JVM |
| “JMH đo được GC overhead tuyệt đối tự động” | Score gồm nhiều thành phần | Thiết kế workload + profiler + phân tích |
| “Dùng `System.gc()` làm chuẩn” | Explicit GC là can thiệp khác | Quan sát GC theo workload thật |
| “Đo một lần đủ” | Nhiễu/JIT/OS khiến kết quả ngẫu nhiên | Warm-up, forks, thống kê |
| “Tất cả GC time đều là STW” | Concurrent GC và barriers vẫn tốn CPU | Phân tích pause + concurrent + mutator |
| “Có dòng `gc` trong Epsilon log = đã thu gom” | Epsilon có heap usage reports | Phân biệt logging vs reclamation |
| “Epsilon chạy production luôn tốt” | Không reclaim, OOME tất yếu với allocation tích lũy | Chỉ dùng nếu lifecycle/heap budget được chứng minh |
| “Có thể chạy option HotSpot trên mọi JVM vendor” | `-XX` không portable | Kiểm tra runtime/options chính xác |

## 17. Bài luyện tập và đáp án

**Bài 1.** Java tạo 12.000 arrays, mỗi array có payload 4.096 byte. Số `requested_payload_bytes` bằng bao nhiêu?

**Đáp án:** `12000 * 4096 = 49,152,000` byte payload. Con số đó **không** bao gồm object header, alignment và allocations của JVM/JDK.

**Bài 2.** Epsilon chạy vòng lặp tạo mảng với `gc_count_delta=0` nhưng mất 8 ms. Mâu thuẫn không?

**Đáp án:** Không. Epsilon vẫn cấp phát, khởi tạo mảng, chạy vòng loop, tương tác caches/memory/OS. Không có GC collection không đồng nghĩa không có công việc.

**Bài 3.** G1 chạy 10 ms, Epsilon 8 ms trên hai process. Kết luận GC của G1 tốn đúng 2 ms?

**Đáp án:** Không. Hai collector khác allocator/barriers/heap state; JIT/OS có nhiễu. Dùng GC logs/JFR và benchmark lặp lại để xác định ảnh hưởng, không lấy chênh lệch làm số chính xác.

**Bài 4.** Vì sao sau khi loop xong G1 có thể dùng ít heap hơn Epsilon dù cả hai chạy cùng source?

**Đáp án:** G1 có khả năng reclaim các mảng cũ unreachable; Epsilon không reclaim. Sự khác nhau về heap used không tự chứng minh ứng dụng leak.

**Bài 5.** `GarbageCollectorMXBean.getCollectionTime()` có luôn bằng tổng thời gian pause mà người dùng thấy không?

**Đáp án:** Không. Nó là khoảng collection elapsed time tích lũy xấp xỉ theo bean, có thể thiếu/khác semantics và không tự phân biệt concurrent/stw. Cần log/JFR/latency.

**Bài 6.** Bật Epsilon trong service cấp phát liên tục nhưng tăng `-Xmx` gấp đôi. Có giải quyết OOME vĩnh viễn không?

**Đáp án:** Không. Chỉ tăng ngân sách trước khi cạn; memory không được tái sử dụng. Với service dài hạn, dùng collector thực sự.

**Bài 7.** Một benchmark có hàng triệu `new Object()` nhưng JIT loại hết allocations. Điểm số có đo đúng allocation path không?

**Đáp án:** Không. Cần phương pháp đảm bảo allocation được quan sát, ví dụ reference escape/harness Blackhole, kết hợp xác nhận allocated bytes.

**Bài 8.** Có nên dùng heap-used delta thay cho allocation rate khi G1 thu gom liên tục?

**Đáp án:** Không. Delta chỉ khác biệt heap used tại hai thời điểm, có thể gần zero khi đã reclaim rất nhiều objects. Dùng thread allocation counters/JFR/profiler phù hợp.

**Bài 9.** Vì sao nên chạy mỗi lượt Epsilon trên JVM mới khi làm benchmark nhiều lượt?

**Đáp án:** Epsilon không reclaim nên heap used tích lũy; state ở lượt sau không tương đương. Fresh JVM giúp giới hạn biến trạng thái heap và tránh OOME bất ngờ, song vẫn cần quản lý warm-up.

**Bài 10.** Dùng Epsilon thấy không có GC pause, nhưng p99 của ứng dụng vẫn cao. Kiểm tra tiếp gì?

**Đáp án:** CPU contention, JIT compilation, blocking I/O, locks, page faults, heap commit, kernel scheduling, logging, business work và allocation/zeroing, ngoài GC.

## 18. Checklist khi viết báo cáo kết quả

- [ ] Đã phân biệt **allocation**, **collection**, **live heap/retention**?
- [ ] Đã nêu Epsilon không thu hồi và sẽ hết heap nếu tiếp tục cấp phát?
- [ ] JVM vendor/version, OS, CPU limit, heap flags và input có cố định?
- [ ] Hai run thành công cùng workload và không OOME?
- [ ] Output ứng dụng/logic giống nhau, không chỉ thời gian khác nhau?
- [ ] Có bằng chứng `-Xlog:gc` về GC/heap usage và collector thực sự dùng?
- [ ] Đã ghi thời gian đo là wall elapsed, không gán nhầm thành GC-only time?
- [ ] Có phân tích pause/STW và concurrent GC khi cần?
- [ ] Có đo cumulative allocated bytes/rate, không dùng heap-used delta thay thế?
- [ ] Có giải thích JIT/escape analysis/TLAB/zeroing và kiểm tra allocation thật?
- [ ] Benchmark có warm-up, forks/fresh JVM, nhiều lượt, kiểm soát nhiễu?
- [ ] Epsilon có heap budget đủ cho tất cả warm-up + measurement?
- [ ] Các event JFR/logs không bị hiểu sai thành exact allocation census?
- [ ] Không mang cờ GC legacy hoặc tính năng JVM không hỗ trợ vào cấu hình Java 11?
- [ ] Kết luận có nêu giới hạn, không tuyên bố số “GC overhead chính xác” khi chỉ nhìn hai thời gian?

## 19. Ghi nhớ nhanh và tài liệu tham khảo

**Mô hình ba lớp:**

```text
Tạo object: allocation path + initialization + application logic
        |
        v
Object sống / chết theo references
        |
        +--> G1: có thể reclaim object unreachable khi collect
        |
        +--> Epsilon: không reclaim, heap used tích lũy tới OOME
```

**Kết luận quan trọng:** Epsilon cho một **negative/control case không thu gom** để xem ứng dụng vẫn phải trả chi phí cấp phát và bộ nhớ. GC thực tế bao gồm pause, concurrent work, barriers và các ảnh hưởng gián tiếp. **Chênh lệch thời gian Epsilon/G1 không phải phép đo GC cost chính xác**; phải kết hợp allocation bytes, GC logs/JFR, benchmark lặp lại và user-visible latency.

**Nguồn chính thức và vẫn phù hợp với JDK hiện đại:**

- [OpenJDK JEP 318 — Epsilon: A No-Op Garbage Collector](https://openjdk.org/jeps/318): mục tiêu, no-op reclamation, performance testing, memory pressure.
- [Oracle JDK 11 Release Notes — JEP 318](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): Epsilon là no-op experimental collector, các trường hợp sử dụng.
- [Oracle Java SE 11 — Java launcher/GC options](https://docs.oracle.com/en/java/javase/11/tools/java.html): `-XX:+UseG1GC`, `-Xms`/`-Xmx`, JVM options.
- [Oracle Java SE 11 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): collection count và approximate collection time.
- [Oracle Java SE 11 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryUsage.html): used/committed/max.
- [Oracle Java SE 11 — `com.sun.management.ThreadMXBean`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): allocated bytes theo thread, JVM-dependent.
- [OpenJDK JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158): `-Xlog` được dùng từ Java 9+.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR được tích hợp vào OpenJDK 11 để phân tích JVM events.
- [OpenJDK JMH](https://github.com/openjdk/jmh): harness microbenchmark, warm-up và forks.
- [Oracle Java SE 25 — Java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): những tùy chọn JVM hiện còn được mô tả, để kiểm tra sự khác biệt khi nâng cấp.
