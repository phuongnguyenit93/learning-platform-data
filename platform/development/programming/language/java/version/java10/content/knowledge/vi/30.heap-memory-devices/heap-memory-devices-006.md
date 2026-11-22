# Java 10 — Heap trên thiết bị bộ nhớ: yêu cầu tương thích với thao tác nguyên tử và truy cập bộ nhớ

## 1. Mục tiêu và kết luận chính

**JEP 316 — Heap Allocation on Alternative Memory Devices** được giới thiệu trong **Java 10**, cho phép **HotSpot JVM** đặt **Java object heap** trên một thiết bị nhớ thay thế DRAM, ví dụ một vùng **NV-DIMM/persistent memory** được hệ điều hành trình bày dưới dạng bộ nhớ ánh xạ qua hệ thống tệp.

Tính năng này có ý nghĩa thực tế khi một hệ thống sở hữu bộ nhớ nhiều tầng có dung lượng/giá/độ trễ khác nhau. Tuy nhiên, **không phải mọi loại thiết bị lưu trữ hoặc bộ nhớ đều có thể làm backing cho Java heap**.

**Yêu cầu thiết yếu của bài học:** thiết bị thay thế phải cung cấp **ngữ nghĩa truy cập như DRAM**, **bao gồm các thao tác nguyên tử (atomic operations)** mà JVM và Java Memory Model cần. Nếu không, những kỹ thuật như **compare-and-set (CAS), volatile access, đồng bộ monitor, GC và các đọc/ghi thông thường** có thể không còn được thực thi đúng. Chỉ việc thiết bị “có địa chỉ byte” hoặc “giữ dữ liệu khi mất điện” **chưa đủ**.

Tài liệu `java` của Oracle JDK **25 và 27** vẫn mô tả tùy chọn:

```bash
-XX:AllocateHeapAt=<filesystem-path>
```

Dòng trên là **cú pháp mô tả**, không phải lệnh shell độc lập. Khi được HotSpot hỗ trợ trên một hệ thống thích hợp, option dùng cơ chế **memory mapping** để cấp phát Java object heap tại một thiết bị bộ nhớ thay thế. Những vùng VM khác như **code heap, metaspace và thread stacks** vẫn nằm trong bộ nhớ thông thường theo thiết kế này. Các cờ **`-Xms`**, **`-Xmx`** và tùy chọn GC tiếp tục có ý nghĩa, nhưng vẫn cần kiểm tra tính tương thích trên cấu hình đích.

### Sau bài này bạn sẽ làm được

1. Giải thích JEP 316 và ranh giới của `-XX:AllocateHeapAt`.
2. Phân biệt **DRAM-like semantics**, **atomicity**, **coherence**, **visibility**, **ordering** và **durability**.
3. Hiểu vì sao bộ nhớ device dùng cho heap phải hỗ trợ các **atomic read–modify–write** phù hợp với CPU/JVM.
4. Nhận biết yêu cầu về **ánh xạ địa chỉ (mmap/DAX), alignment, truy cập đọc/ghi, dung lượng và quyền**.
5. Phân biệt sự bảo đảm của **Java Memory Model (JMM)** với đặc tính lưu trữ dữ liệu sau khi mất điện.
6. Nắm vai trò `AtomicInteger`, `synchronized`, `volatile`, `VarHandle.getAndAdd` và `compareAndSet`.
7. Biết GC có thể di chuyển đối tượng, cập nhật references; heap **không phải một database persistent**.
8. Đọc đúng các dấu hiệu cần kiểm tra trên Linux/HotSpot trước khi đặt heap trên thiết bị.
9. Thực hành ba chương trình Java 17+ độc lập và đối chiếu stdout.
10. Lập test matrix cho máy **thực sự có thiết bị**; không tuyên bố máy Windows thông thường đã kiểm chứng NV-DIMM.

**Special Note:** chỉ nêu các khả năng/API còn áp dụng trên Java hiện đại, không lấy ví dụ dựa trên Java 10 runtime cũ đã hết vòng đời bảo trì. Phân biệt **mốc lịch sử Java 10** với cách kiểm chứng/tuning trên JDK hiện nay.

## 2. JEP 316 giải quyết vấn đề nào?

Máy chủ truyền thống có DRAM để JVM cấp phát objects. Nhưng một số hệ thống có thêm **alternative memory devices**, ví dụ non-volatile dual in-line memory module (**NV-DIMM**) hoặc vùng memory-mapped có khả năng truy cập bằng CPU như RAM. Các thiết bị này có thể đem lại dung lượng khác, độ trễ khác và chi phí mỗi GiB khác DRAM.

JEP 316 cho phép người vận hành yêu cầu HotSpot:

```text
Java application
       |
       | new SomeObject(), new byte[...]
       v
   JVM object heap  -- memory mapping --> alternative memory device
       |
       +--> GC quản lý vòng đời object như Java heap bình thường

JVM code cache / metaspace / thread stacks --> DRAM thông thường
```

Đó là **thay đổi vị trí backing cho Java heap**, không phải thay đổi cách lập trình viên tạo Java object.

### 2.1. Tại sao cần thiết bị có ngữ nghĩa giống DRAM?

Java heap không chỉ được sử dụng cho **tuần tự đọc/ghi dữ liệu**. JVM còn phải:
- Đọc/ghi object fields và array elements;
- Dùng CPU loads/stores theo các kích thước và alignment được hỗ trợ;
- Thực hiện **atomic operations** khi cập nhật trạng thái giữa threads;
- Duy trì JMM visibility/ordering đối với volatile và synchronizers;
- Đọc/cập nhật object headers và metadata liên quan;
- Cho GC đánh dấu, di chuyển, compact và cập nhật references;
- Phối hợp JVM threads, safepoints, barriers và memory consistency.

Nếu một backing device không thể phục vụ những thao tác đó theo kỳ vọng, việc chỉ có một vùng dung lượng lớn không làm nó trở thành **heap-compatible memory**.

### 2.2. JEP 316 không phải đề xuất dùng SSD như RAM

Một ổ NVMe SSD truyền thống thường là **block storage**, xử lý I/O theo các lệnh và block. Điều đó không tự khiến nó có semantics của CPU-addressable DRAM hoặc hỗ trợ atomic memory instructions như các lệnh CPU được JVM kỳ vọng.

**Không** lấy đường dẫn `/mnt/ssd` rồi cho rằng vì `mmap` tồn tại nên JVM đã đặt heap vào memory bus của thiết bị và có thể làm CAS trực tiếp tại đó. Với một filesystem thông thường, các trang mapping có thể được backing bởi **page cache DRAM** thay vì truy cập trực tiếp thiết bị.

Cần phân biệt:
- **Filesystem mapping thông thường:** OS có thể dùng page cache và demand paging;
- **DAX-capable mapping:** một số device/filesystem được cấu hình để mapping trực tiếp vùng physical memory vào không gian địa chỉ tiến trình;
- **Block-device I/O:** không có cùng cam kết memory access như DRAM.

Phải kiểm tra topology và chế độ hoạt động thật; chỉ có một mount point chưa chứng minh đã có DAX.

## 3. Ba tầng tương thích phải đạt đồng thời

Đặt Java heap trên thiết bị bộ nhớ thay thế cần **đồng thời** thoả ba tầng:

| Tầng | Điều cần xác minh | Hậu quả nếu không đạt |
|---|---|---|
| **Hardware/CPU** | CPU có thể load/store và thực hiện những **atomic operations** với vùng memory đó theo đúng semantics mong đợi; có coherence/ordering cần thiết | Race, CAS sai, memory visibility không đúng, lỗi khó tái hiện hoặc crash |
| **Operating system / mapping** | Vùng memory được map hợp lệ, đủ dung lượng, quyền truy cập, alignment/page/FS và khả năng DAX nếu cần | JVM không khởi động, map thất bại, page cache DRAM thay vì thiết bị đích, fault hoặc performance sai kỳ vọng |
| **JDK/HotSpot và GC** | `AllocateHeapAt` được runtime/platform hỗ trợ, cấu hình heap/GC hợp lệ và các giả định runtime được đáp ứng | JVM từ chối cờ/map, không thể dùng heap, lỗi GC, hoặc fallback ngoài ý muốn |

**Đừng đánh đồng kiểm thử trên JDK thông thường với xác nhận ba tầng.** Một chương trình `AtomicInteger` chạy đúng trên DRAM là kiểm tra **code/JMM behavior**, chưa kiểm chứng chipset/firmware/NVDIMM/OS DAX.

### 3.1. RAM-like access gồm những gì?

Về mặt thiết kế, Java heap cần bộ nhớ mà CPU có thể truy cập qua các địa chỉ hợp lệ, với các bảo đảm giống DRAM ở những thao tác VM thực sự sử dụng:
- **Load/store** đọc/ghi chính xác và ổn định;
- **Atomic access** cho các kích cỡ/kiểu thao tác được CPU và VM hỗ trợ;
- **Atomic read–modify–write**, ví dụ các primitive để triển khai CAS;
- **Memory ordering** và **visibility** tương ứng với kiến trúc/JMM;
- Truy cập đồng thời an toàn giữa nhiều CPU cores/threads;
- **Alignment** thích hợp để các thao tác yêu cầu alignment không phá hợp đồng;
- Mapping vẫn hợp lệ trong vòng đời tiến trình và đủ tài nguyên.

Lưu ý “giống DRAM” là yêu cầu **ngữ nghĩa quan sát được**, không phải bắt thiết bị có cùng tốc độ hoặc cùng công nghệ chế tạo DRAM.

## 4. Atomicity: vì sao là điều kiện bắt buộc cho heap?

**Atomicity** nói rằng một thao tác được đặc tả là nguyên tử phải xuất hiện đối với các threads như một đơn vị không bị quan sát ở trạng thái giữa không hợp lệ, theo đúng memory model/API.

Ví dụ cập nhật counter trong `AtomicInteger`:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();
counter.incrementAndGet();
```

Đây là **mảnh code** trong method. `incrementAndGet()` phải bảo đảm tăng atomically, kể cả khi nhiều threads gọi cùng lúc.

JVM có thể thực thi atomic operation bằng CPU instructions hoặc cơ chế triển khai phù hợp. Trên một thiết bị alternative memory, **hardware/memory subsystem phải cho VM duy trì các bảo đảm đó**.

### 4.1. CAS — Compare And Set

**CAS** có cấu trúc logic:

```text
if (memory_location == expected) {
    memory_location = replacement;
    return true;
}
return false;
```

Sơ đồ này chỉ nhằm giải thích. Phép đọc–kiểm tra–ghi phải là **một atomic update** đối với các threads cùng truy cập đúng location; **không** được triển khai bằng ba câu lệnh Java thông thường chạy không khóa.

`AtomicInteger.compareAndSet(expected, replacement)` và `VarHandle.compareAndSet(...)` có contract atomic. Nếu thiết bị nhớ không cho phép các thao tác atomic cần thiết trên vùng backing, HotSpot không thể đơn giản coi memory đó là một Java heap DRAM-like an toàn.

### 4.2. Atomicity không đồng nghĩa mọi phép cộng Java đều atomic

```java
int x = 0;
x++;
```

Đây là **mảnh code**. `x++` có thể đọc–tính–ghi qua nhiều bước; không trở thành atomic chỉ vì `x` nằm trên NV-DIMM hoặc trên DRAM.

Để tăng counter đồng thời:
- `AtomicInteger.incrementAndGet()`;
- `synchronized` / `ReentrantLock` bảo vệ shared variable;
- `VarHandle.getAndAdd(...)` cho một field hợp lệ;
- Hoặc một thiết kế không chia sẻ mutable state.

**Đủ atomic hardware** là điều kiện để JVM *có thể* thực thi những hợp đồng đồng bộ Java, **không có nghĩa mọi thao tác không đồng bộ của user code tự nhiên an toàn**.

### 4.3. Atomic field access còn có giới hạn kiểu và kiến trúc

Java spec định nghĩa rất cụ thể những access nào atomic, những access nào là synchronization action. Theo **JLS `17.7**, một read/write non-volatile `long` hoặc `double` có thể không bắt buộc atomic theo mô hình ngôn ngữ trong một số hoàn cảnh; volatile `long`/`double` có các bảo đảm mạnh hơn.

Không nên mô tả:
- “Mọi load/store của mọi kích cỡ, ở mọi địa chỉ, trên mọi kiến trúc đều atomic”;
- “Mọi thiết bị DAX tự động hỗ trợ CAS của mọi độ rộng”;
- “CPU có CAS là đủ cho tất cả correctness của JVM”.

Ngược lại, **JVM và hardware phải cung cấp các bảo đảm được Java SE và HotSpot implementation yêu cầu** trên các loại biến/địa chỉ hợp lệ. Đó mới là tiêu chí tương thích.

## 5. Visibility, ordering và cache coherence

Đúng atomic update vẫn chưa đủ nếu các CPU cores **không nhìn thấy cập nhật theo những thứ tự được Java yêu cầu**.

Ví dụ producer/consumer:

```java
final class Message {
    int payload;
    volatile boolean ready;
}
```

Producer:

```java
message.payload = 73;
message.ready = true;
```

Consumer:

```java
if (message.ready) {
    int x = message.payload;
}
```

Ba đoạn trên là **mảnh code** đặt trong class/method hợp lệ. Nếu consumer đọc được `ready == true` qua volatile read tương ứng, quan hệ **happens-before** cho phép nó quan sát dữ liệu đã publish trước volatile write, ví dụ `payload == 73`.

### 5.1. Volatile có nghĩa gì?

Một volatile write/read có memory effects theo Java Memory Model:
- Có yêu cầu **visibility** và **ordering** giữa threads;
- Không tạo mutual exclusion;
- Không biến `volatileCounter++` thành atomic increment;
- Không tự lưu nội dung xuống persistent storage bền vững khi mất điện.

Khi heap ở memory device thay thế, những bảo đảm JMM phải tiếp tục đúng, như với DRAM. Về triển khai, CPU cache coherence, fences, atomic instructions và memory subsystem tham gia đạt hợp đồng.

### 5.2. Cache coherence không phải “mỗi load phải đọc thẳng chip”

Nhiều kiến trúc dùng CPU cache giữa core và thiết bị backing. Ngữ nghĩa DRAM-like **không** đòi mỗi Java read lập tức xuống physical module.

Điều cần có là cơ chế khiến các accesses quan sát được **theo semantics JMM**, kể cả khi có caching/buffers/reordering hợp lệ. JVM/JIT có thể dùng memory barriers hoặc CPU instructions theo kiến trúc để thực hiện điều đó.

**Không** yêu cầu lập trình viên tự gọi file I/O để “đồng bộ cache” chỉ vì heap chuyển sang NV-DIMM; nếu thiết bị đã tương thích DRAM-like, Java synchronization code tiếp tục được kỳ vọng có đúng semantics.

### 5.3. Memory ordering khác durability

Cụm “flush” dễ gây nhầm:

- **Memory fence / volatile ordering:** ràng buộc cách operations được quan sát và sắp thứ tự giữa **threads đang chạy**;
- **Persistent flush / durability:** bảo đảm dữ liệu đã tới miền lưu trữ bền vững trước sự cố điện/crash.

Một volatile write không phải transaction commit xuống thiết bị không mất dữ liệu. `AtomicInteger.compareAndSet` không phải lệnh fsync. Đây là hai bài toán **khác nhau** dù cùng dùng từ “memory consistency”.

## 6. Java heap trên non-volatile device không trở thành persistent database

Một thiết bị NV-DIMM có thể giữ các bits khi mất điện, nhưng **Java heap theo JEP 316 được HotSpot quản lý như vùng nhớ đối tượng trong tiến trình hiện tại**.

HotSpot GC có thể:
- Cấp phát đối tượng mới;
- Di chuyển đối tượng giữa địa chỉ/regions;
- Viết lại references;
- Thu hồi/reuse vùng nhớ;
- Cập nhật object headers/mark state;
- Thay đổi layout/metadata theo JDK build và GC.

Sau một lần JVM dừng bất thường:
- Không có hợp đồng **khởi động JVM mới rồi dùng lại nguyên bộ object graph**;
- Các địa chỉ/pointers của object không phải stable persistent IDs;
- Metadata được GC/JVM quản lý không phải định dạng ổn định để khôi phục giao dịch;
- Việc có một file-backed mapping không biến dữ liệu heap thành database có ACID hoặc crash recovery.

**JEP 316 hướng tới khả năng đặt heap trên thiết bị nhớ khác, không cung cấp Java heap persistence API.**

Nếu bài toán cần dữ liệu tồn tại sau restart, dùng **database, file format, log/transaction protocol** hoặc các API mapped storage có hợp đồng durability riêng. Đừng lấy `-XX:AllocateHeapAt` thay cho backup hoặc data persistence.

### 6.1. JEP 352 / mapped buffers là cơ chế khác

Java 14 có **JEP 352 — Non-Volatile Mapped Byte Buffers**, liên quan các map modes đặc thù như `jdk.nio.mapmode.ExtendedMapMode.READ_WRITE_SYNC` trên nền tảng được hỗ trợ.

Ở JDK 25, lớp `ExtendedMapMode` vẫn được tài liệu hóa. Nó cung cấp khả năng lập trình **một vùng mapped file** và cơ chế `MappedByteBuffer.force()` cho durability theo điều kiện của API/platform.

**Phân biệt rõ:**

| Mục tiêu | JEP 316 — AllocateHeapAt | JEP 352 / MappedByteBuffer |
|---|---|---|
| Phạm vi | **Toàn bộ Java object heap** | **Vùng file được map có chủ đích** |
| Ai quản lý? | JVM + GC | Ứng dụng quản lý dữ liệu trong mapped buffer |
| API cho từng object `new` | Không cần thay source | Đọc/ghi buffer hoặc cấu trúc mã hóa riêng |
| Durability mặc định | **Không** tự cung cấp | Có API force/map mode phù hợp, với điều kiện được đặc tả |
| Reuse object graph sau JVM restart | Không | Phải tự thiết kế format/recovery nếu cần |
| Yêu cầu thiết bị | DRAM-like memory/atomic semantics | Tùy map mode/API/OS và mục tiêu persistence |

Đây là sự phân biệt còn rất quan trọng trên Java mới: **volatile Java heap placement** không đồng nghĩa **persistent data model**.

## 7. Vì sao `synchronized` cũng cần memory semantics?

Một Java monitor dùng:

```java
synchronized (accountLock) {
    balance -= amount;
}
```

Đây là mảnh code trong method. Java `synchronized` có:
- Mutual exclusion theo monitor;
- Happens-before giữa monitor unlock và lần lock tiếp theo trên cùng monitor;
- Cơ chế VM để bảo toàn object/monitor state.

Khi object heap đặt trên alternative memory, JVM vẫn phải thực thi đúng Java monitor contract. Việc object/lock fields có thể nằm trên heap và một số VM structures nằm ngoài heap **không hạ thấp** yêu cầu correctness.

**Không thể nói:** “Hardware chỉ cần hỗ trợ đọc/ghi thường, vì lock đều nằm trong DRAM.” JVM object headers, references, atomic states và những compiler/runtime optimizations có thể dựa vào các thao tác trên vùng heap. Thiết kế tương thích cần xét **toàn bộ các thao tác JVM yêu cầu**, không chỉ một class demo.

## 8. `VarHandle` và atomic memory-access modes

`java.lang.invoke.VarHandle` có từ Java 9 và vẫn được hỗ trợ trên Java hiện đại. Nó mô tả nhiều access modes:

| Mode | Ý nghĩa tổng quát |
|---|---|
| `get` / `set` | Plain memory access |
| `getOpaque` / `setOpaque` | Opaque access với coherence/ordering hạn chế |
| `getAcquire` | Acquire read semantics |
| `setRelease` | Release write semantics |
| `getVolatile` / `setVolatile` | Volatile semantics |
| `compareAndSet` | Conditional atomic update |
| `compareAndExchange` | Atomic exchange trả giá trị quan sát |
| `getAndAdd` | Atomic read–modify–write cộng số |
| `getAndSet` | Atomic exchange |

**Không** chọn mode chỉ vì tên nghe “nhanh hơn”. Semantics của plain/opaque/acquire/release/volatile khác nhau, phải phù hợp yêu cầu synchronization của code.

### 8.1. Vì sao thử `VarHandle.getAndAdd` có ý nghĩa?

Nếu nhiều threads gọi `getAndAdd` lên một field hỗ trợ access mode, kết quả phải đúng theo Java API. Trên thiết bị thay thế, JVM vẫn phải duy trì bảo đảm đó.

Nhưng một ví dụ chạy đúng 20.000 increments **không phải chứng nhận phần cứng**. Nó chỉ là **smoke test hành vi ở cấu hình đang chạy**. Hardware validation cần tài liệu thiết bị/CPU/OS và các thử nghiệm stress có phạm vi rộng hơn.

### 8.2. CPU có thể không hỗ trợ mọi atomic width

Một số ISA/platform có điều kiện riêng cho alignment, kích thước operand hoặc loại atomic instructions. JVM có thể dùng cách triển khai khác nhau để đạt API semantics. Vì vậy:
- Đừng giả định có native lock-free atomic 128-bit trên mọi thiết bị;
- Đừng tự cast một địa chỉ byte bất kỳ thành atomic word;
- Đừng tự viết JNI/Unsafe memory access theo giả định alignment không được xác minh;
- Nếu dùng native libraries tương tác với cùng vùng nhớ, phải kiểm tra **ABI, memory ordering, synchronization và lifetime**.

Trong Java thuần, để **đúng contract**, ưu tiên API Java SE như `AtomicInteger`, `VarHandle` và `Lock`, thay vì sử dụng internal VM implementation.

## 9. Chương trình đầy đủ 1 — atomic increment và monitor lock

Tạo tệp **`AtomicHeapDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicHeapDemo {
    static final class LockedCounter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        final int threads = 4;
        final int iterations = 20_000;

        AtomicInteger atomic = new AtomicInteger();
        LockedCounter locked = new LockedCounter();
        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[threads];

        for (int i = 0; i < threads; i++) {
            workers[i] = new Thread(() -> {
                try {
                    start.await();
                    for (int j = 0; j < iterations; j++) {
                        atomic.incrementAndGet();
                        locked.increment();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            workers[i].start();
        }

        start.countDown();
        for (Thread worker : workers) {
            worker.join();
        }

        int expected = threads * iterations;

        System.out.println("expected=" + expected);
        System.out.println("atomic=" + atomic.get());
        System.out.println("locked=" + locked.get());
        System.out.println("bothCorrect=" +
                (atomic.get() == expected &&
                 locked.get() == expected));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 -encoding UTF-8 AtomicHeapDemo.java
java AtomicHeapDemo
```

**Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2:**

```text
expected=80000
atomic=80000
locked=80000
bothCorrect=true
```

### 9.1. Cách đọc kết quả

- Bốn threads × 20.000 increments = **80.000**;
- `AtomicInteger` cho atomic increment;
- `LockedCounter` bảo vệ cả update/read bằng cùng monitor;
- `CountDownLatch` phối hợp bắt đầu, `join()` đợi worker kết thúc;
- Hai kết quả bằng nhau như mong đợi trên JVM đúng contract.

**Đây là kiểm thử Java application correctness trên heap thông thường.** Chương trình không biết `-XX:AllocateHeapAt` có đang hoạt động, không xác nhận trang nhớ thuộc PMEM, và không thay thế test phần cứng.

### 9.2. Khi muốn chạy trên thiết bị thay thế

Sau khi OS/JDK/device đã được kỹ sư hệ thống xác minh, có thể chạy **cùng class file** với HotSpot option chỉ định đường dẫn hợp lệ. Không cần thay `new AtomicInteger()` hoặc `synchronized` trong Java code **nếu thiết bị thật sự có semantics đúng như DRAM**.

Đây chính là lợi ích được mô tả của JEP 316: **giữ nguyên Java source và ngữ nghĩa lập trình khi đổi backing của object heap**.

### 9.3. Vì sao không chỉ test `int++`?

Nếu chỉ chạy code có data race như hai threads cùng `x++` mà không khóa, kết quả không ổn định **ngay cả trên DRAM hoàn toàn chuẩn**. Dùng test đó để kết luận thiết bị nhớ “không hỗ trợ atomic” sẽ sai.

Hãy viết test dùng operations **được API Java bảo đảm atomic** rồi kiểm tra kết quả. Đồng thời kiểm tra behavior của synchronized và volatile, vì phần cứng/JVM compatibility rộng hơn một primitive.

## 10. Chương trình đầy đủ 2 — volatile publication và happens-before

Tạo tệp **`VolatileHeapDemo.java`**:

```java
public class VolatileHeapDemo {
    static final class Shared {
        int payload;
        volatile boolean ready;
    }

    public static void main(String[] args)
            throws InterruptedException {
        Shared shared = new Shared();

        Thread producer = new Thread(() -> {
            shared.payload = 73;
            shared.ready = true;
        });
        producer.start();

        long deadline =
                System.nanoTime() + 5_000_000_000L;

        while (!shared.ready &&
                System.nanoTime() < deadline) {
            Thread.onSpinWait();
        }

        if (!shared.ready) {
            throw new IllegalStateException(
                    "producer timeout");
        }

        int value = shared.payload;
        producer.join();

        System.out.println("ready=" + shared.ready);
        System.out.println("payload=" + value);
        System.out.println("publishedCorrect=" +
                (value == 73));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 VolatileHeapDemo.java
java VolatileHeapDemo
```

**Stdout đã kiểm chứng trên OpenJDK 24.0.2:**

```text
ready=true
payload=73
publishedCorrect=true
```

### 10.1. Điều gì được bảo đảm?

Trong producer:
1. Ghi `payload = 73`;
2. Ghi `ready = true` bằng volatile write.

Consumer quan sát `ready == true` bằng volatile read rồi đọc `payload`. Theo JMM, volatile write/read tương ứng thiết lập quan hệ **happens-before**, nên dữ liệu đã publish được nhìn thấy.

**Quan trọng:** chính `volatile` giải thích khả năng publication đúng trong ví dụ, không phải `Thread.join()` vì `join()` chỉ được gọi **sau khi** `payload` đã được đọc. `Thread.onSpinWait()` là gợi ý cho CPU trong vòng chờ, **không** tự tạo memory synchronization.

### 10.2. Đây không phải kiểm thử khả năng chống mất điện

Giá trị `payload=73` được quan sát trong **cùng một lần chạy của JVM**. Chương trình không xác minh rằng một thiết bị NV-DIMM đã flush dữ liệu bền vững hoặc rằng JVM mới sau restart có thể khôi phục `Shared`.

**Volatile visibility không đồng nghĩa persistent durability.**

### 10.3. Demo có timeout để tránh vô hạn

Vòng chờ có thời hạn ~5 giây để phát hiện lỗi scheduling/hang trong môi trường test. Một hệ thống thực tế thường nên dùng `CountDownLatch`/`Future`/`BlockingQueue` thay vì spin chờ dài. Đây là demo về memory ordering, không phải kiến trúc xử lý event khuyến nghị.

## 11. Chương trình đầy đủ 3 — `VarHandle.getAndAdd` và CAS

Tạo tệp **`VarHandleHeapDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.concurrent.CountDownLatch;

public class VarHandleHeapDemo {
    static final class Counter {
        volatile long value;
    }

    static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                    Counter.class, "value", long.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                try {
                    start.await();
                    for (int j = 0; j < 5_000; j++) {
                        VALUE.getAndAdd(counter, 1L);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            workers[i].start();
        }

        start.countDown();
        for (Thread worker : workers) {
            worker.join();
        }

        long result =
                (long) VALUE.getVolatile(counter);

        boolean swapped =
                VALUE.compareAndSet(
                    counter, 20_000L, 20_001L);

        System.out.println("getAndAddResult=" + result);
        System.out.println("casSucceeded=" + swapped);
        System.out.println("afterCas=" +
                (long) VALUE.getVolatile(counter));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 VarHandleHeapDemo.java
java VarHandleHeapDemo
```

**Stdout đã kiểm chứng:**

```text
getAndAddResult=20000
casSucceeded=true
afterCas=20001
```

### 11.1. Giải thích

- Bốn threads, mỗi thread gọi `getAndAdd(..., 1L)` 5.000 lần;
- Trên một field `long` hỗ trợ access mode, `getAndAdd` thực hiện **atomic read–modify–write**;
- `getVolatile` lấy giá trị bằng volatile read semantics;
- `compareAndSet` chỉ cập nhật `20000 → 20001` nếu giá trị bằng expected tại thời điểm CAS;
- Các workers đã `join()` nên main chỉ CAS sau khi mọi increments kết thúc.

### 11.2. Tại sao dùng `long` nhưng không khẳng định mọi long write đều atomic?

Đây là `VarHandle.getAndAdd` và `getVolatile` — **những access modes có contract riêng**. Không so sánh chúng với một non-volatile `long` bình thường và kết luận mọi access đều có cùng atomic/ordering guarantees trên mọi JVM/CPU.

Để kiểm tra thiết bị thật sự có đúng memory semantics, cần kết hợp test chương trình với tài liệu của **CPU ISA**, **thiết bị**, **firmware**, **OS mapping** và HotSpot platform.

### 11.3. Không viết native CAS bừa bãi

Nếu ứng dụng dùng JNI/native code để truy cập cùng vùng thiết bị, không tự viết assembly atomic cho một địa chỉ tùy ý khi chưa biết:
- Alignment;
- Operand width;
- Memory mapping/type;
- Cache coherence;
- ISA instruction support;
- Synchronization protocol với JVM.

Một đoạn code native không đúng có thể phá toàn bộ hệ thống dù phần Java code phía trên đúng.

## 12. Alignment và memory access granularity

**Alignment** là yêu cầu địa chỉ/độ rộng của một số CPU operations:
- Một primitive hoặc atomic operation có thể yêu cầu địa chỉ phù hợp với độ rộng được hỗ trợ;
- Unaligned access có thể chậm, không atomic hoặc không hợp lệ tùy kiến trúc/operation;
- JVM và OS cần đặt heap/mapping sao cho internal layout hoạt động đúng;
- Page alignment trong `mmap`/DAX khác với alignment của một object field/atomic word.

**Không** dùng `sun.misc.Unsafe`/internal object offsets để tự tạo những địa chỉ unaligned và lấy chạy được trên máy này làm bằng chứng thiết bị tương thích. Cách làm hiện đại là dùng API chuẩn (`Atomic*`, `VarHandle`, `ByteBuffer`, Foreign Function & Memory API khi bài toán thực sự là native memory) với scope/hợp đồng được đặc tả.

### 12.1. Atomicity không đòi mọi kích thước truy cập là một lệnh

JVM có thể dùng các kỹ thuật implementation khác nhau để đạt API guarantee. Điều quan trọng là **các operations có atomic contract phải đúng**. Không suy rằng Java `AtomicLong` luôn ánh xạ đúng một lệnh CPU duy nhất trên mọi nền tảng.

### 12.2. Byte addressability không đủ

Một thiết bị có thể cho chương trình đọc từng byte nhưng:
- Không có coherent multi-core access;
- Không hỗ trợ những atomic RMW cần thiết;
- Có alignment restrictions chưa được đáp ứng;
- Cho mapping qua page cache thay vì direct memory;
- Không ổn định khi CPU cache line flush hoặc khi thiết bị lỗi.

Trong những trường hợp này, thiết bị **không được tự động xem là Java heap-compatible** chỉ vì có thể `mmap` một file trên filesystem.

## 13. Những vùng nhớ nào được `AllocateHeapAt` tác động?

Theo Oracle JDK 25/27 `java` man page:

- **Java object heap** có thể được backing bởi alternative memory device được chỉ định;
- **Code heap** (ví dụ vùng mã do JIT tạo), **metaspace** và **thread stacks** tiếp tục ở DRAM;
- Các cờ như `-Xms`, `-Xmx` và những garbage collection options vẫn có ý nghĩa.

Một sơ đồ:

```text
Process Java
   |
   +-- Java object heap          --> alternative DRAM-like device
   |     +-- regular Java objects
   |     +-- arrays / instance fields
   |     +-- GC-managed object data
   |
   +-- metaspace / class data    --> DRAM
   +-- JIT code cache            --> DRAM
   +-- thread stacks             --> DRAM
   +-- other native allocations  --> theo OS/runtime/allocator riêng
```

**Đừng kết luận** toàn bộ RSS hoặc toàn bộ native memory của JVM đã được chuyển lên NVDIMM. Trong thực tế, GC structures, JNI/native libraries, direct buffers, OS memory/page cache và các subsystem khác có chính sách riêng.

### 13.1. `ByteBuffer.allocateDirect` không tự chuyển sang thiết bị đó

`ByteBuffer.allocateDirect(...)` thường cấp phát **off-heap/direct memory**, không phải một Java object heap backing theo ý nghĩa `AllocateHeapAt`, dù wrapper Java là object trên heap.

Nếu cần quản lý riêng off-heap data hoặc persistent mapped files, phải chọn API/allocator phù hợp. Không gọi `AllocateHeapAt` rồi mặc định mọi direct buffers đều do PMEM mount quản lý.

### 13.2. `-Xms`/`-Xmx` vẫn phải tính theo dung lượng thiết bị

Ví dụ cấu hình:

```bash
java -Xms512m -Xmx2g -XX:AllocateHeapAt=/mnt/pmem-heap -jar app.jar
```

Đây là **lệnh minh họa dành cho hệ thống HotSpot đã xác minh support**, không phải lệnh có thể chạy trên bất kỳ laptop nào. Nó yêu cầu:
- `/mnt/pmem-heap` thực sự chỉ tới filesystem phù hợp;
- Mapping được phép và đủ chỗ cho heap;
- Hệ điều hành/driver/firmware/CPU đáp ứng memory semantics;
- JDK và collector được kiểm thử trên platform đó.

Không đặt `-Xmx2g` chỉ vì thấy có `2G` trống ở một mount. Cần xem reservation, backing capacity, GC overhead, OS quotas, native DRAM và workload peak.

## 14. Quy trình kiểm tra trước khi cấu hình trên Linux

Đây là checklist cho **một máy đã có thiết bị/mount được quản trị cấp**. **Không tạo/mount/format thiết bị bằng lệnh trong bài** vì những thao tác đó có thể xóa dữ liệu và cần quy trình quản trị riêng.

### 14.1. Xác nhận JDK và option

```bash
java -version
java -XX:+PrintFlagsFinal -version 2>&1 | grep AllocateHeapAt
```

Trên **OpenJDK 24.0.2 Windows x64**, kiểm tra `PrintFlagsFinal` xác nhận có flag product `AllocateHeapAt` với **giá trị mặc định trống**. Việc thấy flag **không chứng minh** môi trường ấy có PMEM/DAX hoặc chức năng này được hỗ trợ đầy đủ trên một OS cụ thể.

### 14.2. Xem mount point

```bash
findmnt -T /mnt/pmem-heap -o SOURCE,TARGET,FSTYPE,OPTIONS
df -h /mnt/pmem-heap
ls -ld /mnt/pmem-heap
```

Ba lệnh là **kiểm tra đọc thông tin**:
- `findmnt` cho biết mount/FS/options;
- `df` cho dung lượng được filesystem báo;
- `ls -ld` cho quyền sở hữu/quyền truy cập directory.

**Không đủ để chứng nhận DAX và atomic semantics**. Cần thông tin chuyên sâu từ **hệ thống quản lý PMEM/ndctl/daxctl, OS/kernel và vendor documentation**. Một mount option có chữ `dax` hoặc một thiết bị tên `pmem` vẫn không tự chứng minh mọi CPU atomic ops hoạt động đúng trên region đang dùng.

### 14.3. Kiểm tra DAX và đường truyền memory thực tế

Linux NVDIMM/PMEM documentation mô tả **DAX (Direct Access)**: ánh xạ trực tiếp file system/PMEM memory, bỏ qua page cache theo cấu hình phù hợp.

Nhưng:
- Cấu hình DAX có thể khác giữa namespace **fsdax**, **devdax**, driver và filesystem;
- Không phải mọi filesystem type hoặc mount có thể cung cấp DAX;
- Một block device hoặc tmpfs không có nghĩa là đúng phần cứng;
- DAX hỗ trợ mapping không tự bảo đảm atomic/ordering của CPU được đáp ứng theo Java heap contract.

Hãy yêu cầu admin xác nhận bằng tài liệu/thiết bị và kiểm tra runtime mapping. **Đừng tự thay tên path** rồi kết luận đã chuyển Java heap thật sang một tier mới.

### 14.4. Phân quyền đường dẫn

Thư mục dùng cho VM heap mapping cần:
- Quyền phù hợp với UID/GID của process;
- Dung lượng/permission/quota phù hợp;
- Không bị những process khác can thiệp hoặc sửa file backing ngoài ý muốn;
- Chính sách bảo mật đối với dữ liệu heap có thể chứa bí mật.

Vì Java heap có thể chứa token, session, credentials hoặc PII, nếu backing non-volatile hoặc file-backed, cần xác định rõ **data remanence, cleanup, access control và incident handling**. Không mặc định JVM exit tự xóa vĩnh viễn mọi dữ liệu trên phương tiện vật lý.

## 15. Chạy trên thiết bị thật và chứng minh heap đã được map

Sau khi phần cứng và filesystem đã được xác nhận:

```bash
java -Xms512m -Xmx2g \
  -XX:AllocateHeapAt=/mnt/pmem-heap \
  -Xlog:gc+heap=info \
  -cp . AtomicHeapDemo
```

Đây là **mẫu Linux cho môi trường có PMEM được cấu hình**, không phải đầu ra đã được xác minh trong máy Windows dùng để biên dịch demo.

### 15.1. Cần kiểm chứng những gì?

1. JVM **khởi động thành công** và chương trình trả kết quả đúng;
2. Flag `AllocateHeapAt` thực sự được HotSpot nhận và không bị bỏ qua;
3. Memory mappings/định vị pages thực tế phản ánh backing **thiết bị dự kiến**;
4. `-Xms`/`-Xmx` và GC logs phù hợp;
5. Không có page faults/I/O errors hoặc OOM không dự đoán được;
6. Độ trễ và throughput của ứng dụng chấp nhận được.

Không đủ khi chỉ thấy:

```text
bothCorrect=true
```

Đó mới là **functional smoke test**. Muốn chứng minh placement, cần quan sát mapping/OS-level evidence và phần cứng đích. Tùy Linux distro/JDK/kernel, có thể dùng công cụ như `/proc/<pid>/maps`, `smaps`, `numastat`, các công cụ DAX/PMEM của hệ thống và profiler. Những công cụ này có giới hạn quan sát riêng; phải hiểu cách JVM tạo backing mapping.

### 15.2. Thất bại khi mapping không hợp lệ

Nếu path bị thiếu, không có quyền, filesystem không hỗ trợ kiểu mapping cần thiết hoặc device capacity không đủ, JVM có thể **không khởi động hoặc báo lỗi cấp phát/map memory**.

Không ép JVM “cứ chạy và hy vọng atomicity vẫn đúng” khi hardware/OS không đạt yêu cầu. Hãy giải quyết bằng cấu hình máy, filesystem và runtime được vendor hỗ trợ, hoặc **quay lại heap DRAM mặc định**.

### 15.3. Không giả định mọi JDK/OS có cùng support

Flag `-XX:AllocateHeapAt` được tài liệu hóa trên Oracle JDK 25/27, nhưng advanced `-XX` options là đặc tính **HotSpot**, không phải tính năng bắt buộc của mọi JVM implementation hoặc OS.

Do đó:
- Kiểm tra `java -version` và `PrintFlagsFinal` trên JVM thật;
- Đọc tài liệu đúng version/vendor/OS;
- Thử tại staging có phần cứng đại diện;
- Không copy một đường dẫn Linux DAX sang Windows/macOS mà coi hỗ trợ tương đương.

## 16. Test matrix cho tính tương thích thao tác nguyên tử

Một kiểm chứng nghiêm túc nên có **nhiều tầng**, từ correctness đến performance:

| Nhóm test | Nội dung | Mục đích |
|---|---|---|
| **Device documentation** | Hỗ trợ CPU atomic RMW, coherence, addressing và alignment trên region | Đảm bảo có nền tảng cho DRAM-like semantics |
| **OS mapping** | DAX/PMEM/permissions/capacity; kiểm tra mapping thật | Đảm bảo JVM heap backing đi đúng nơi |
| **Atomic counters** | `AtomicInteger.incrementAndGet` qua nhiều threads | Smoke test atomic read–modify–write |
| **CAS** | `AtomicInteger.compareAndSet`, `VarHandle.compareAndSet` | Kiểm tra conditional atomic updates |
| **Volatile publication** | Producer writes + volatile ready flag + reader | Kiểm tra visibility/ordering theo JMM |
| **Monitor locking** | `synchronized` bảo vệ shared state | Kiểm tra multi-thread mutual exclusion |
| **Array/object access** | Allocation, mutation, traversal, GC pressure | Kiểm tra regular Java heap behavior |
| **GC relocation** | Long-running allocations với collector đích | Kiểm tra GC hoạt động với heap backing |
| **Stress + topology** | Nhiều cores/sockets, NUMA, tải cạnh tranh | Phát hiện vấn đề chỉ xuất hiện dưới contention |
| **Restart/crash** | Kiểm tra phục hồi bằng **data layer riêng**, không đọc heap stale | Xác nhận không nhầm heap với persistence |
| **Benchmark** | p95/p99 latency, throughput, RSS, page faults, CPU | Đánh giá hiệu quả thực tế |

**Không tuyên bố PASS bằng một test loop ngắn**. Những lỗi coherence/atomic thường hiếm và phụ thuộc topology/load; kết quả đúng trên 1 core chưa chứng minh đúng trên multi-socket NUMA.

### 16.1. Không làm phép thử phá dữ liệu trên thiết bị production

Không format device, không tùy tiện sửa file heap backing đang được JVM sử dụng, không làm power-loss test trên dữ liệu thật. Hãy dùng staging, dữ liệu tổng hợp và kế hoạch rollback.

### 16.2. Kiểm tra Java Memory Model bằng công cụ phù hợp

**OpenJDK jcstress** là bộ công cụ kiểm thử concurrency được thiết kế để kiểm tra những memory-ordering outcomes. Nó có thể hữu ích trong môi trường nghiên cứu/validation, nhưng:
- Không thay tài liệu hardware/firmware;
- Không chứng minh mọi pattern atomic nếu chỉ chạy ít lần;
- Không tự xác nhận toàn bộ heap thực sự nằm ở thiết bị thay thế;
- Không nên đánh đồng một test “PASS” với chứng chỉ phần cứng.

Các chương trình 9–11 trong bài là smoke tests dễ học, **không phải chứng nhận JMM/device compatibility**.

## 17. Atomic access vs persistent atomic update

Sự khác biệt thiết yếu:

**Atomic memory access (concurrent threads):**
- Một phép cập nhật được nhìn thấy như nguyên tử theo API/JMM;
- Quan trọng trong Java application đang chạy;
- Ví dụ `AtomicInteger.compareAndSet`.

**Persistent atomic update (across crash/power loss):**
- Dữ liệu ở trạng thái nhất quán và bền vững sau failure;
- Cần thứ tự durability, flush/barrier cho miền lưu trữ, log/recovery/transaction;
- Không được JEP 316 tự động cung cấp cho Java heap.

Ví dụ tưởng tượng: hai fields `balanceA` và `balanceB` được Java thread cập nhật dưới một lock. Nếu mất điện giữa hai writes vào NVM, không có đảm bảo của `synchronized` rằng data bits đã được persist như **một giao dịch khôi phục nguyên tử**. Lock giúp consistency giữa live threads, **không** tương đương transaction log.

Đây là lý do không được quảng bá `AllocateHeapAt` như tính năng “JVM có persistent objects” chỉ vì media là non-volatile.

## 18. Những sai lầm về độ bền và hiệu năng

### 18.1. “Thiết bị non-volatile nghĩa object vẫn sống qua restart”

Sai. JVM mới có object identity, GC state, class metadata và heap layout riêng. Muốn dữ liệu sống qua restart, cần persistent representation và recovery protocol.

### 18.2. “Dùng NVM sẽ nhanh hơn DRAM”

Không có bảo đảm. Alternative memory có thể:
- Dung lượng cao hơn;
- Giá thành khác;
- Độ trễ load/store cao hơn;
- Throughput/bandwidth thấp hơn;
- NUMA distance khác;
- Chi phí flush, page faults hoặc mapping khác;
- Hiệu ứng CPU cache và GC pattern không thuận lợi.

Đánh giá theo workload; JEP 316 không phải tuyên bố thay mọi DRAM bằng NVM là tăng hiệu năng.

### 18.3. “JVM chạy được tức là đúng thiết bị”

Không hẳn. Mappings và filesystem page-cache behavior có thể khác kỳ vọng; còn có thể VM không dùng option do khác runtime/flag behavior. Cần kiểm tra OS mapping và flags.

### 18.4. “Atomic CAS đúng trong demo chứng minh support”

Không. Demo có thể chạy trên DRAM, trong page cache hoặc ít concurrency. Cần xác minh hardware/OS/JVM từ nhiều tầng.

### 18.5. “Tăng `-Xmx` sẽ tạo thêm dung lượng device”

Không. `-Xmx` chỉ đặt giới hạn Java heap, không tăng physical capacity/mount quota. Nếu không đủ backing memory, mapping/allocation có thể thất bại hoặc hệ thống chịu memory pressure.

## 19. Phân biệt NV-DIMM, DAX, MappedByteBuffer, Foreign Memory API

| Công nghệ/khái niệm | Phạm vi | Yêu cầu riêng |
|---|---|---|
| **NV-DIMM / persistent memory media** | Phần cứng nhớ | Đặc tính điện, load/store/atomic/coherence được vendor công bố |
| **Linux DAX** | OS/filesystem mapping | Được cấu hình cho direct mapping của PMEM, không phải mọi block filesystem |
| **`-XX:AllocateHeapAt` (JEP 316)** | **HotSpot Java object heap backing** | Thiết bị có DRAM-like semantics; JVM/OS hỗ trợ |
| **`ByteBuffer.allocateDirect`** | Off-heap/direct buffer | Không tự trở thành JEP 316 heap allocation |
| **`FileChannel.map` / `MappedByteBuffer`** | Vùng file mapping do app quản lý | Mapping mode, lifetime, file safety và durability theo API |
| **`ExtendedMapMode.READ_WRITE_SYNC` (JEP 352)** | Persistent memory mapped file | OS/JDK support, force/flush semantics phù hợp |
| **Foreign Function & Memory API** | Truy cập native/off-heap segments | Lifetime/alignment/ownership/access modes; không phải chuyển Java heap |
| **Database/log-backed persistence** | Dữ liệu tồn tại qua restart | Transaction, recovery, integrity và durability |

**Chọn đúng công cụ:**
- Muốn **đặt Java heap trên thiết bị nhớ khác** mà vẫn chạy Java objects theo GC/JMM? Xem `AllocateHeapAt`.
- Muốn **quản lý bytes ngoài heap**? Xem direct buffers/mapped buffers/FFM API.
- Muốn **dữ liệu khôi phục sau crash**? Dùng một persistence layer có transaction/recovery semantics được thiết kế cho điều đó.

Không gộp ba yêu cầu vào một cờ JVM.

## 20. JVM GC trên thiết bị bộ nhớ thay thế

Garbage collector vẫn là một thành phần quan trọng:
- Objects được cấp phát qua JVM allocation path;
- GC cần đọc object graph, mark live objects;
- Một số collectors di chuyển/compact objects;
- References có thể được cập nhật và các regions được tái sử dụng.

Vì thế backing memory phải hỗ trợ:
- Regular reads/writes số lượng lớn;
- Memory ordering và atomic operations mà GC/runtime cần;
- Những truy cập theo page/alignment được JVM và OS hỗ trợ;
- Đủ dung lượng/throughput cho allocation và GC workloads.

### 20.1. Những cờ GC thông thường vẫn có ý nghĩa

Theo Oracle man page, `-Xmx`, `-Xms` và các GC-related flags vẫn hoạt động như trước khi heap được đặt trên thiết bị thay thế.

Tuy nhiên **không có bảo đảm** mọi combination collector/JDK/OS/device đều đã được vendor kiểm thử cùng mức. Khi nâng cấp JDK hoặc đổi GC:
- Dùng tài liệu đúng release;
- Kiểm tra allocation/GC logs;
- Chạy stress ở staging trên hardware thật;
- Đo CPU, memory bandwidth, pause time và throughput.

### 20.2. Không dựa vào địa chỉ ổn định của object

Trong Java, references là những giá trị logic trỏ tới objects do JVM quản lý, không phải stable device offsets phục vụ persistence. GC có thể di chuyển objects; không lưu “địa chỉ object” thành dữ liệu persistent rồi mong JDK sau restart giải mã và dùng được.

## 21. Benchmark tối thiểu nhưng có ý nghĩa

Khi muốn biết tier bộ nhớ thay thế có phù hợp, đo **cùng application build, cùng JDK, cùng GC và cùng workload**, chỉ đổi placement khi có thể.

Những chỉ số cần quan sát:
- Throughput của transactions/requests;
- p50/p95/p99 latency (đặc biệt khi có CAS/locks cạnh tranh);
- GC pause distribution, allocation rate, live set;
- CPU time, memory bandwidth và NUMA locality;
- Page faults, stalls, DAX/PMEM device metrics;
- Startup/readiness time;
- Actual memory placement và tỷ lệ pages ở tier mong muốn;
- Performance trong giai đoạn warm-up và steady state;
- Tác động khi nhiều JVM cùng dùng thiết bị.

Không chỉ so một vòng `System.nanoTime()` và kết luận “PMEM nhanh hơn”. Benchmark dễ chịu ảnh hưởng JIT, dead-code elimination, CPU scaling, data locality và GC.

### 21.1. Atomic contention cần đo riêng

Nhiều threads cùng cập nhật **một AtomicInteger** có thể tạo một hot cache line và gây contention. Hiệu năng có thể giảm dù hardware semantics vẫn **đúng**.

Với counters thống kê không cần snapshot hoàn toàn chính xác tại mọi nano giây, `LongAdder` có thể giảm contention trong workload phù hợp; nhưng nó có contract snapshot khác `AtomicLong`.

**Đúng và nhanh là hai trục khác nhau**. Không đánh đổi JMM correctness lấy throughput.

### 21.2. Thao tác trên object graph khác stream byte thẳng

GC và ứng dụng Java truy cập nhiều pointer-chasing structures; bộ nhớ có độ trễ lớn hơn DRAM có thể ảnh hưởng khác với benchmark `System.arraycopy` hoặc quét array tuần tự.

Nên dùng workload gần ứng dụng thật: maps, caches, graph, services, GC allocations, contention và đủ working set để phản ánh memory tier.

## 22. Security và operational safety

Nếu heap chứa dữ liệu nhạy cảm và backing device có khả năng non-volatile, cần đánh giá:
- Quyền truy cập vào mount point và backing files;
- Quy trình làm sạch/hủy dữ liệu sau khi tiến trình kết thúc;
- Encryption-at-rest hoặc memory encryption nếu hệ thống hỗ trợ;
- Audit ai có thể đọc device/filesystem;
- Chính sách crash dump/swap/core dumps;
- Phân tách dữ liệu giữa tenants hoặc container workloads.

Không hứa rằng **JVM tự xóa sạch mọi byte** trên vật lý NVM khi exit. Cũng không dùng đường dẫn ghi trên mount nhạy cảm mà chưa được cấp phép.

Thay đổi heap placement là **thao tác hạ tầng**; cần kiểm soát vận hành, backup/rollback cho dữ liệu thực tế và quy trình staging trước deployment.

## 23. Checklist tương thích trước khi bật `AllocateHeapAt`

- [ ] Runtime là **HotSpot/JDK build** có hỗ trợ `-XX:AllocateHeapAt` trên OS/architecture đích?
- [ ] Thiết bị được công bố có **DRAM-like load/store semantics**?
- [ ] Có hỗ trợ atomic operations/CAS/RMW cần thiết theo CPU/JVM trên vùng mapped?
- [ ] Multi-core cache coherence/visibility/ordering đạt yêu cầu tương ứng?
- [ ] Có kiểm tra alignment/operand width phù hợp?
- [ ] Hệ điều hành/driver/kernel và filesystem cung cấp mapping/DAX phù hợp?
- [ ] Mount/path tồn tại, đúng thiết bị, có quyền ghi và dung lượng?
- [ ] Không nhầm filesystem/page cache thông thường với physical PMEM backing?
- [ ] Có kiểm tra `PrintFlagsFinal`/JDK documentation của runtime thật?
- [ ] Có xác minh `-Xms`/`-Xmx` hợp lệ với device capacity?
- [ ] Java objects/arrays và GC chạy đúng trong staging?
- [ ] `AtomicInteger`, `VarHandle.getAndAdd`/CAS, `synchronized` và `volatile` hoạt động đúng?
- [ ] Có chạy stress đa lõi/sockets, có contention và GC pressure?
- [ ] Có xác nhận mapping/placement bằng OS-level evidence, không chỉ nhìn stdout?
- [ ] Có đo p99 latency/throughput, GC, page faults và NUMA effects?
- [ ] Đã phân biệt memory visibility trong runtime với persistent durability sau crash?
- [ ] Không mong JVM restart đọc lại nguyên object graph từ persistent media?
- [ ] Code heap/metaspace/thread stacks/native memory có đủ DRAM không?
- [ ] Có kế hoạch access control, data cleanup và security?
- [ ] Khi thay JDK/OS/GC/firmware, có chạy lại compatibility tests?
- [ ] Có phương án rollback về heap DRAM bình thường khi tier bộ nhớ thất bại?

**Mẫu nhận xét code review:**

> “`-XX:AllocateHeapAt` chỉ phù hợp nếu thiết bị có ngữ nghĩa bộ nhớ như DRAM, đặc biệt các atomic operations. Path tới một SSD filesystem thông thường không đủ. Cần xác nhận loại mapping, tính hỗ trợ CPU/device và kiểm thử JMM/GC thực tế trước khi bật trong production.”

**Mẫu nhận xét về persistence:**

> “Dùng NV-DIMM làm backing cho Java heap không biến object graph thành trạng thái có thể khôi phục sau JVM crash. Nếu yêu cầu restart recovery, cần một persistent format/transaction layer riêng.”

## 24. Sai lầm phổ biến và cách sửa

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “JEP 316 chuyển toàn bộ JVM sang NVDIMM.” | Chỉ **Java object heap** theo cơ chế này; code cache, metaspace, stacks vẫn ở DRAM. |
| “Có NV-DIMM là đủ; không cần atomic operations.” | **Sai**. Cần semantics giống DRAM, gồm atomic operations. |
| “Mmap được là heap-compatible.” | Không. Cần memory semantics, mapping, OS/JVM support. |
| “SSD có `mmap` cũng giống DAX persistent memory.” | Không mặc định. Block storage thường khác CPU-addressable memory. |
| “`AtomicInteger` chỉ cần byte-addressable storage.” | Không. Atomic RMW/coherence/ordering theo JVM contract cần được đáp ứng. |
| “CAS chạy đúng một lần chứng minh thiết bị phù hợp.” | Không. Cần phần cứng, stress và OS mapping verification. |
| “`volatile` nghĩa ghi dữ liệu bền vững sau mất điện.” | Không. Volatile là memory visibility/ordering giữa threads. |
| “`compareAndSet` là transaction log.” | Không. Atomic memory update khác crash-consistent durable transaction. |
| “JEP 316 tạo persistent Java objects.” | Không. JVM/GC vẫn quản lý heap như volatile object heap. |
| “Địa chỉ Java object không bao giờ đổi.” | Không. GC có thể di chuyển objects. |
| “Tắt GC để giữ object offsets sau restart là giải pháp.” | Không phải mô hình persistence có hợp đồng; không đề xuất. |
| “Mọi atomic operand widths đều hỗ trợ trên mọi device.” | Sai. Phụ thuộc ISA/alignment/JVM implementation. |
| “Nếu `long` load bình thường đã có vẻ atomic thì mọi `VarHandle` mode đều hợp lệ.” | Không. API modes có semantics riêng, phải do JVM/platform cung cấp. |
| “`synchronized` không liên quan vì monitors nằm ở DRAM.” | JVM cần đúng monitor/object state/happens-before cho toàn heap. |
| “Tăng `-Xmx` giúp tăng dung lượng vật lý NVDIMM.” | Không. Flag chỉ điều khiển giới hạn heap. |
| “Thấy `AllocateHeapAt` trong flags là đã sử dụng PMEM.” | Không. Phải chỉ định path và kiểm tra mapping thực tế. |
| “Tự động dùng JEP 316 trên Windows/macOS như Linux DAX.” | Cần xác minh hỗ trợ theo OS/JDK; không giả định. |
| “Heap trên PMEM sẽ luôn nhanh hơn DRAM.” | Không có bảo đảm; latency/bandwidth/GC có thể chậm hơn. |
| “`DirectByteBuffer` cũng tự đi vào cùng heap device.” | Không. Đây là off-heap API có cơ chế backing khác. |
| “Không cần dọn dữ liệu vì JVM exit tự xóa vĩnh viễn trên NVM.” | Không có bảo đảm ấy. Đánh giá security/data remanence riêng. |

## 25. Câu hỏi ôn tập có đáp án

**1.** JEP nào đưa heap trên thiết bị nhớ thay thế vào Java 10?

**Đáp án:** **JEP 316 — Heap Allocation on Alternative Memory Devices**.

**2.** Flag của HotSpot tên gì?

**Đáp án:** `-XX:AllocateHeapAt=<filesystem-path>`, với path trỏ đến filesystem/mount phù hợp.

**3.** Có thể dùng bất kỳ ổ SSD được mount làm heap DRAM-like không?

**Đáp án:** Không. SSD/block storage hoặc mmap qua page cache không tự cung cấp điều kiện memory device như DRAM.

**4.** Yêu cầu quan trọng nhất đối với thiết bị nhớ thay thế là gì?

**Đáp án:** Cùng **memory access semantics như DRAM, bao gồm atomic operations**, cùng các điều kiện CPU/OS/JVM liên quan.

**5.** Vì sao atomic operations quan trọng?

**Đáp án:** JVM và code Java có những contract về atomic updates, CAS, monitor/JMM; thiết bị phải cho phép VM bảo toàn correctness giữa threads.

**6.** Có đủ nếu thiết bị cho đọc/ghi từng byte không?

**Đáp án:** Không. Cần đúng atomic RMW, coherence, ordering, alignment và mapping.

**7.** `volatile int x; x++;` có atomic không?

**Đáp án:** Không. `volatile` không biến compound increment thành nguyên tử.

**8.** `AtomicInteger.incrementAndGet()` giải quyết vấn đề gì?

**Đáp án:** Atomic increment một giá trị với memory effects theo Java API.

**9.** `VarHandle.getAndAdd` và `compareAndSet` được dùng để làm gì?

**Đáp án:** Atomic read–modify–write và conditional atomic update theo contract của VarHandle.

**10.** `synchronized` có còn cần thiết trên NV-DIMM heap không?

**Đáp án:** Có nếu shared-state invariant cần mutual exclusion/happens-before; JEP 316 không thay đổi Java Memory Model.

**11.** `volatile` bảo đảm object sẽ được phục hồi sau mất điện không?

**Đáp án:** Không. Visibility/ordering của live threads khác persistent durability.

**12.** Có thể restart JVM và dùng nguyên object references trong PMEM không?

**Đáp án:** Không có contract như vậy. GC/JVM object graph không phải persistent database.

**13.** Những vùng nào được Oracle mô tả vẫn ở DRAM khi dùng `AllocateHeapAt`?

**Đáp án:** Code heap, metaspace và thread stacks, bên cạnh các memory structures khác theo VM policy.

**14.** `ByteBuffer.allocateDirect` có tự chuyển sang vùng `AllocateHeapAt` không?

**Đáp án:** Không. Nó là off-heap allocation.

**15.** Một chương trình CAS chạy đúng trên laptop Windows chứng minh Linux PMEM device phù hợp không?

**Đáp án:** Không. Nó chỉ chứng minh code chạy đúng trên runtime/memory đã thử.

**16.** Muốn xác nhận JVM thật sự map heap lên PMEM phải kiểm tra gì?

**Đáp án:** Flag, mount/DAX/OS mapping, hardware topology, process mappings và hành vi của ứng dụng/JVM trên máy đích.

**17.** Vì sao vẫn phải test GC?

**Đáp án:** GC đọc/ghi object graphs, có thể di chuyển objects và cập nhật references; backing memory phải hỗ trợ các access patterns đó.

**18.** Nếu muốn dữ liệu bền vững sau crash nên dùng gì?

**Đáp án:** Persistent storage APIs/database hoặc mapped-file design có flush/transaction/recovery riêng; `AllocateHeapAt` không tự cung cấp.

**19.** Có thể mặc định mọi JDK/OS hỗ trợ option giống nhau không?

**Đáp án:** Không. `-XX` là HotSpot-specific advanced option; xác minh version, vendor, OS/architecture và device.

**20.** Làm sao đo thiết bị có thật sự giúp ứng dụng?

**Đáp án:** Benchmark trên workload đại diện, so cùng JDK/GC, đo latency/throughput/GC/NUMA/memory placement, không chỉ chạy một microbenchmark ngắn.

## 26. Tài liệu chính thức và tham khảo

- [OpenJDK JEP 316 — Heap Allocation on Alternative Memory Devices](https://openjdk.org/jeps/316): mục đích Java 10, thiết bị DRAM-like và sử dụng heap trên alternative device.
- [Oracle JDK 27 — The java Command: `-XX:AllocateHeapAt`](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): xác nhận cờ và điều kiện **same semantics as DRAM, including atomic operations** vẫn được tài liệu hóa.
- [Oracle JDK 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:AllocateHeapAt`, phạm vi Java object heap và những VM structures còn ở DRAM.
- [Oracle JDK 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cờ vẫn có trên nhánh JDK LTS.
- [Oracle Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-17.html): Java Memory Model, atomicity và happens-before.
- [Oracle Java SE 24 — `VarHandle`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/VarHandle.html): `getVolatile`, `getAndAdd`, `compareAndSet` và các access modes.
- [Oracle Java SE 25 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic updates của Java SE.
- [Oracle Java SE 25 — `ExtendedMapMode`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html): READ_WRITE_SYNC và persistence-oriented mappings của JEP 352.
- [Oracle Java SE 25 — `FileChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html): mapped files, force/durability và giới hạn theo hệ điều hành.
- [Linux NVDIMM documentation](https://nvdimm.docs.kernel.org/): phân loại thiết bị, fsdax/devdax và các yêu cầu filesystem mapping.
- [Linux kernel LIBNVDIMM documentation](https://www.kernel.org/doc/html/latest/driver-api/nvdimm/nvdimm.html): định nghĩa PMEM, DAX và direct mapping.
- [Oracle Labs — Non-Volatile Memory and Java, Part 3](https://labs.oracle.com/pls/apex/f?p=LABS:0:0:APPLICATION_PROCESS=GETDOC_INLINE:::DOC_ID:1304): phân biệt lợi ích capacity của JEP 316 với kiến trúc dữ liệu persistent/recovery.

**Kết luận:** **Đặt Java heap trên thiết bị nhớ thay thế không làm hạ thấp Java Memory Model.** Thiết bị phải có **ngữ nghĩa truy cập như DRAM, đặc biệt atomic operations**, đồng thời OS mapping và HotSpot runtime phải hỗ trợ. `AtomicInteger`, `volatile`, `VarHandle` và `synchronized` vẫn phải hoạt động đúng; tính đúng đắn đó **không phải** bảo đảm dữ liệu sẽ sống qua mất điện. Khi triển khai, xác minh hardware + OS/DAX + JVM, kiểm tra memory placement thật, đo GC/latency và luôn có phương án dùng heap DRAM thông thường.