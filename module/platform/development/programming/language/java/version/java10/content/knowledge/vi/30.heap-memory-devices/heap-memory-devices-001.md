# Mục tiêu đặt Java heap trên thiết bị có ngữ nghĩa bộ nhớ phù hợp

## 1. Bài học giải quyết vấn đề gì?

**Java 10 — JEP 316, Heap Allocation on Alternative Memory Devices** bổ sung khả năng để **HotSpot JVM cấp phát Java object heap trên một thiết bị bộ nhớ thay thế DRAM** mà người vận hành chỉ định. Ví dụ ban đầu của JEP là một thiết bị **NV-DIMM** hoặc một loại bộ nhớ không phải DRAM có thể được ánh xạ trực tiếp vào không gian địa chỉ của tiến trình.

Cờ JVM trọng tâm:

~~~text
-XX:AllocateHeapAt=<duong-dan-thu-muc>
~~~

HotSpot dùng đường dẫn trên hệ thống tệp để tạo vùng **file-backed memory mapping** cho Java object heap. Khi hệ thống tệp/thiết bị hỗ trợ **DAX (Direct Access)**, các load/store của CPU có thể truy cập thẳng thiết bị bộ nhớ đã ánh xạ, không cần đi qua bản sao của page cache thông thường.

**Vấn đề không phải** đặt Java heap lên một “ổ đĩa bất kỳ”. Thiết bị đích cần có **ngữ nghĩa truy cập bộ nhớ tương thích với DRAM**, bao gồm cả **ngữ nghĩa của thao tác nguyên tử (atomic operations)**. Từ góc nhìn của Java code, thao tác đọc, ghi, `volatile`, atomic update và đồng bộ hóa phải giữ đúng hành vi được JVM và Java Memory Model bảo đảm.

Điểm này vẫn có giá trị hiện nay: tài liệu lệnh `java` của Oracle **JDK 25 và JDK 26** tiếp tục mô tả `-XX:AllocateHeapAt`. Nhưng đây là **tùy chọn HotSpot phụ thuộc hệ điều hành, filesystem và thiết bị**, không phải tính năng Java SE mà mọi JVM bắt buộc hỗ trợ. Đừng khuyến nghị NV-DIMM của một nhà sản xuất cụ thể như một sản phẩm hiện còn phổ biến; NV-DIMM là **ví dụ kỹ thuật** trong JEP, còn thiết bị thực tế cần được xác minh.

Sau bài này, bạn có thể:

1. Giải thích **vì sao mục tiêu là mở rộng lựa chọn vị trí heap**, không phải biến Java heap thành dữ liệu bền vững.
2. Xác định **load/store, atomic semantics, DAX và mmap** khác nhau ở điểm nào.
3. Phân biệt phần **Java object heap** với **metaspace, code heap, thread stacks, direct buffers và native memory**.
4. Viết lệnh `-XX:AllocateHeapAt` cùng `-Xms`, `-Xmx`, GC flags đúng vị trí.
5. Biết cách xác minh **thư mục/thiết bị có DAX thực sự**, thay vì chỉ nhìn một đường dẫn hoặc một chương trình chạy thành công.
6. Hiểu giới hạn của tính **persistence**: đối tượng Java không tự được phục hồi sau restart, dù thiết bị có thể lưu dữ liệu khi mất điện.
7. Kiểm tra bằng ví dụ **Java 17+ có thể biên dịch**, kết quả giống nhau khi dùng heap thường hoặc heap file-backed.
8. Đánh giá rủi ro hiệu năng, vận hành, quyền tệp, container/NUMA và lập kế hoạch thử nghiệm có kiểm soát.

## 2. Vì sao cần bộ nhớ thay thế DRAM?

Các ứng dụng Java có thể có **heap rất lớn**, ví dụ để giữ dữ liệu phân tích, cache và nhiều cấu trúc trong bộ nhớ. DRAM có ưu điểm latency và bandwidth rất tốt, nhưng trong một số hệ thống, chi phí, mật độ dung lượng hoặc số khe cắm phần cứng giới hạn quy mô có thể dùng.

Thiết bị bộ nhớ có khả năng **CPU-addressable, load/store trực tiếp** có thể tạo thêm một tầng dung lượng. Những hệ thống phù hợp có thể chọn:

- **Đặt Java object heap trên tầng bộ nhớ dung lượng lớn hơn**, khi thiết bị cung cấp đúng ngữ nghĩa cho CPU/JVM.
- **Giữ những cấu trúc runtime khác trong DRAM** để tránh chuyển toàn bộ tiến trình tới một vùng nhớ có thể chậm hơn.
- Giữ nguyên **mã ứng dụng Java** và các thuật toán GC thích hợp, thay vì viết lại một bộ allocator ở tầng Java.

Nhưng đây là **bài toán đánh đổi**, không phải cấu hình “mặc định tốt hơn”:

| Mục tiêu | Khả năng tiềm năng | Đánh đổi cần đo |
| --- | --- | --- |
| Heap dung lượng lớn | Có thể dùng tầng memory khác DRAM có capacity cao | Latency/bandwidth có thể kém DRAM |
| Tách heap khỏi một phần DRAM | Một số object heap dùng thiết bị thay thế | Native/metaspace/stacks vẫn cần DRAM |
| Giữ Java code không đổi | JVM tự xử lý heap placement | Phụ thuộc HotSpot/OS/device, phải kiểm thử |
| GC vẫn sử dụng được | Heap vẫn chịu quản lý của collector | GC phải đọc/copy nhiều object trên thiết bị mới |
| Đơn giản hóa ứng dụng | Không yêu cầu app chuyển sang native API | Deployment, monitoring, bảo mật trở nên phức tạp hơn |

**Không có lợi ích hiệu năng được bảo đảm cho mọi ứng dụng.** Một workload phụ thuộc latency truy cập object hoặc allocation/GC bandwidth có thể chạy chậm hơn khi heap nằm trên thiết bị có độ trễ cao. Mục tiêu thường là **capacity/cost trade-off** theo số đo, không phải bảo đảm tăng tốc.

## 3. “Ngữ nghĩa bộ nhớ phù hợp” nghĩa là gì?

Điều kiện cốt lõi được Oracle mô tả: thiết bị thay thế phải có **cùng ngữ nghĩa như DRAM, bao gồm ngữ nghĩa của các thao tác nguyên tử**.

### 3.1. Truy cập theo địa chỉ bộ nhớ, không phải I/O từng block

Thông thường Java object heap được JVM đặt trong một vùng **virtual address space**; CPU thực thi các thao tác load/store lên các địa chỉ mà JVM quản lý.

Một thiết bị thích hợp phải hỗ trợ đường truy cập được OS/JVM ánh xạ như bộ nhớ:

~~~text
Java object reference
        |
        v
HotSpot object heap (virtual addresses)
        |
        v
OS memory mapping
        |
        v
CPU load/store tới physical backing memory
~~~

Đây **không** phải mô hình thông thường của:

~~~text
Ổ SSD thông thường → read()/write() block I/O → deserialize object
~~~

SSD hoặc ổ đĩa thông thường có thể chứa một **file mmap**, nhưng việc dùng `mmap()` không tự chứng minh các trang của file được map trực tiếp lên một **memory-like device**. Nếu không có DAX, truy cập có thể qua **page cache của DRAM** và chịu I/O, page faults hoặc flush. Do đó, “mmap được” **chưa đủ** để kết luận “tương đương DRAM”.

### 3.2. Tính nguyên tử (atomic operations) là yêu cầu bắt buộc

HotSpot và Java Memory Model phải dựa vào các hoạt động đồng bộ hóa thích hợp để thực thi Java code, ví dụ:

- `AtomicInteger.incrementAndGet()` và các compare-and-set (CAS) phù hợp.
- `volatile` read/write với các quy tắc visibility/ordering.
- `synchronized`, locks và các mối quan hệ **happens-before**.
- Các phép đọc/ghi object fields theo hợp đồng Java và kiến trúc JVM.

Nếu thiết bị chỉ hỗ trợ **đọc/ghi theo block** mà không cung cấp cách OS/CPU duy trì những ngữ nghĩa trên qua mapping, nó **không phải** backing memory phù hợp cho Java object heap theo mục tiêu của JEP 316.

Cần phân biệt **atomic semantics** với **persistence**:

- **Atomicity/visibility/ordering của Java** giải quyết đúng đắn của những thao tác giữa các luồng đang chạy.
- **Durability** giải quyết dữ liệu đã được ghi tới thiết bị có sống sót sau crash/power failure và có thể phục hồi hay không.
- Một thao tác `volatile` hoặc CAS thành công **không phải lời cam kết dữ liệu đã durable sau mất điện**.

### 3.3. DAX là một cơ chế backing, không phải chính Java API

Ở Linux, **filesystem DAX (fsdax)** cho phép một số filesystem ánh xạ file trên thiết bị memory-like **trực tiếp** vào không gian user, bỏ qua page cache ở đường truy cập phù hợp.

Cần đồng thời có:

1. Thiết bị và driver/OS hỗ trợ.
2. Filesystem/mount và **DAX state của file** phù hợp.
3. Directory có khả năng tạo và mmap vùng lưu heap.
4. Dung lượng, quyền, page alignment và các điều kiện liên quan.
5. JDK/HotSpot build và collector hỗ trợ cấu hình được triển khai.

**Một thư mục tên `/mnt/pmem` không chứng minh nó có PMEM hoặc DAX**; đó chỉ là tên do người quản trị đặt. `df -h`, `lsblk` và `findmnt` hỗ trợ nhận diện thiết bị/FS, nhưng muốn xác nhận DAX ở mức file trên filesystem hiện đại còn cần kiểm tra **trạng thái active DAX của inode** (`S_DAX` qua `statx` hoặc công cụ tương thích).

## 4. Điều gì được đặt trên thiết bị thay thế, điều gì vẫn cần DRAM?

Theo tài liệu `java` hiện hành, `-XX:AllocateHeapAt` áp dụng cho **Java object heap**. Các cấu trúc khác như **code heap, metaspace và thread stacks** vẫn nằm ở DRAM theo mô hình mà JEP mô tả.

~~~text
+-------------------- JVM process --------------------+
|                                                   |
|  Java object heap                                 |
|  (new Object(), byte[], collections, ...)        |
|                   |                               |
|                   v                               |
|      Alternative memory device / fsdax            |
|                                                   |
|  Metaspace, code heap/JIT code, thread stacks     |
|  GC/JVM native bookkeeping, native libraries      |
|                   |                               |
|                   v                               |
|                 DRAM                              |
+---------------------------------------------------+
~~~

Đây là **sơ đồ khái niệm**, không diễn giải chi tiết mỗi page mapping/allocator trên mọi phiên bản HotSpot. Một số cấu trúc GC/native và file caches có thể có cơ chế memory riêng; không khẳng định một tỷ lệ byte vật lý chính xác chỉ từ hình minh họa.

| Thành phần | Bản chất | Có phải toàn bộ được đưa vào alternative heap? |
| --- | --- | --- |
| `new byte[1024]` | Java array object trên heap | **Thuộc Java object heap** |
| `new MyObject()` | Java object bình thường | **Thuộc Java object heap** |
| `AtomicInteger` object | Java object cùng trường dữ liệu | **Object thuộc heap**, nguyên tử do JVM bảo đảm |
| `ByteBuffer.allocateDirect(1 << 20)` | Java wrapper trên heap, **payload direct memory** ngoài heap | **Không** chuyển toàn bộ direct payload theo `AllocateHeapAt` |
| Class metadata | Metaspace | **Không** |
| Mã máy JIT compile | Code cache/code heap | **Không** |
| Java/native thread stacks | Stack memory | **Không** |
| Native `malloc()` của thư viện JNI | Native memory | **Không** |
| `MappedByteBuffer` ánh xạ file tùy ý | Mapping do Java/library yêu cầu | **Không phải** Java object heap được đặt bằng `AllocateHeapAt` |

Vì vậy, một ứng dụng heap 16 GiB và direct buffers 4 GiB vẫn cần lập ngân sách cho **4 GiB direct memory và những chi phí native khác** ngay cả khi heap được đặt trên thiết bị thay thế.

**Không** lấy `-Xmx` làm giới hạn RSS hay hard memory limit toàn tiến trình. Kernel/container có thể hạch toán những file-backed pages theo cách khác, tùy OS/cgroup; cần đo trên môi trường đích.

## 5. `-XX:AllocateHeapAt`: cú pháp và vòng đời mapping

Dạng cờ:

~~~text
-XX:AllocateHeapAt=<path>
~~~

Theo flag description của HotSpot, `path` là **đường dẫn tới thư mục** mà JVM có thể tạo **temporary backing file** cho Java heap. Trong tài liệu Oracle, nó được mô tả tổng quát là đường dẫn tới filesystem của thiết bị.

Ví dụ **chỉ dành cho Linux host đã được cấu hình backing device đúng**:

~~~bash
java -Xms512m -Xmx2g -XX:AllocateHeapAt=/mnt/dax-heap -cp app.jar com.example.Main
~~~

Ở đây:

- `/mnt/dax-heap` **phải tồn tại** và là thư mục trên filesystem phù hợp. Đây **không phải** tên file `.jar`, `.jsa`, `.hprof` hay một Java heap dump mà bạn đặt trước.
- JVM dùng filesystem này để tạo/mmap vùng backing cho **object heap**.
- `-Xms512m` chỉ định **initial Java heap**.
- `-Xmx2g` giới hạn **maximum Java heap**, không phải dung lượng tối đa của toàn tiến trình.
- `-cp app.jar com.example.Main` xác định ứng dụng thực; ví dụ giả định class có `main` trong JAR.
- Cờ JVM phải được đặt **trước main class** hoặc trước `-jar`.

Đặt cờ sau main class là **sai vị trí**:

~~~bash
# JVM option hợp lệ về vị trí:
java -XX:AllocateHeapAt=/mnt/dax-heap -cp app.jar com.example.Main

# Không đúng ý nghĩa JVM option: đây chỉ là đối số truyền vào main()
java -cp app.jar com.example.Main -XX:AllocateHeapAt=/mnt/dax-heap
~~~

### 5.1. Không được coi backing file là nơi lưu dữ liệu bền vững

Java object heap vẫn là **managed runtime memory**:

- JVM có thể di chuyển object trong GC.
- Địa chỉ và representation nội bộ của object không phải định dạng lưu trữ cố định cho nhiều lần khởi động.
- Khi JVM kết thúc, không có hợp đồng Java SE nào cho phép “mở lại heap cũ và lấy Java object trước đó”.
- Nếu backing device **về phần cứng** có khả năng giữ dữ liệu sau mất điện, điều đó **không tự biến object graph thành persistent database**.

Không dùng `AllocateHeapAt` thay thế database, checkpoint, serialization, durable logging hoặc cơ chế transaction.

### 5.2. Không có bảo đảm mọi filesystem đều cấp được heap mong muốn

Một đường dẫn có thể thất bại vì:

- Thư mục không tồn tại, không ghi được hoặc bị mount read-only.
- Device không đủ dung lượng/quota hoặc không hỗ trợ mapping phù hợp.
- JVM/GC/OS không hỗ trợ yêu cầu cụ thể.
- Các giới hạn hệ điều hành hoặc container chặn việc mmap/commit.
- Các tùy chọn memory/huge pages không tương thích với cấu hình hiện tại.

Nếu JVM không thể tạo vùng heap như yêu cầu, việc khởi tạo có thể thất bại; không dựa vào giả định “JVM sẽ luôn tự fallback về DRAM” nếu chưa xác minh log và hành vi JDK.

## 6. Phân biệt `AllocateHeapAt`, `AllocateDirect`, memory mapping và AOT/CDS

Những từ “map”, “file”, “heap”, “device” rất dễ bị trộn.

| Kỹ thuật/cờ | Dùng để làm gì? | Không có nghĩa là |
| --- | --- | --- |
| `-XX:AllocateHeapAt=/mnt/dax-heap` | Đặt **Java object heap** bằng file-backed mapping | Tạo persistent Java objects hoặc heap dump |
| `ByteBuffer.allocateDirect(...)` | Cấp phát **direct buffer memory** ngoài Java heap | Chuyển toàn bộ object heap sang thiết bị khác |
| `FileChannel.map(...)` | Tạo mapping **file cụ thể** cho ứng dụng | JVM dùng file đó làm Java heap |
| `-XX:SharedArchiveFile=...jsa` | Chỉ định **CDS/AppCDS class-data archive** | Chỉ định nơi toàn bộ object heap sống |
| `-XX:AOTCache=...aot` (JDK mới) | Nạp cache tối ưu hóa khởi động AOT | Thay thế live object heap |
| `-XX:HeapDumpPath=...hprof` | Chỉ định đường dẫn **heap dump** khi được bật | Di chuyển heap đang chạy |
| `-Xmx2g` | Giới hạn dung lượng **Java heap** | Chọn thiết bị backing vật lý |

**Quan trọng:** `-XX:AllocateHeapAt` không phải phiên bản khác của **AppCDS**. AppCDS dùng archive metadata class để tối ưu khởi động; còn JEP 316 nhắm tới **vị trí vùng memory chứa Java objects đang hoạt động**.

### 6.1. MappedByteBuffer có thể hỗ trợ dữ liệu bền vững không?

Đó là **bài toán khác**. File mapping cho phép ứng dụng thao tác một vùng dữ liệu trực tiếp trên file; để có tính bền vững thực tế còn cần giao thức flush/synchronization, thứ tự ghi, consistency và recovery.

Ngay cả khi có API file mapping hỗ trợ thao tác trên file bền vững, nó **không** tự biến Java object heap do GC quản lý thành một persistent object store. Không dùng `MappedByteBuffer.force()` với kỳ vọng nó “flush” toàn bộ Java heap của `AllocateHeapAt`.

## 7. Mục tiêu tương thích Java Memory Model

Java code phải thấy **cùng hành vi logic** khi có/không có `-XX:AllocateHeapAt` nếu cấu hình chạy thành công.

Ví dụ:

~~~java
AtomicInteger counter = new AtomicInteger();
counter.incrementAndGet();
~~~

`AtomicInteger` phải cập nhật nguyên tử theo hợp đồng API. Việc đổi backing device không cho phép hai luồng vô tình mất increment.

Các tình huống quan trọng:

1. **Atomic read-modify-write**: CAS, getAndAdd, incrementAndGet phải giữ hợp đồng.
2. **Visibility/ordering**: `volatile`, locks, latches tạo quan hệ happens-before đúng như khi heap ở DRAM.
3. **Garbage collection**: di chuyển/thu hồi object phải giữ tính đúng đắn của reference graph.
4. **Không gian địa chỉ**: Java object references vẫn là tham chiếu hợp lệ do JVM quản lý; code ứng dụng không tự tính physical address.
5. **Lỗi JVM/platform**: thiết bị/OS không thể đáp ứng những điều kiện này thì không nên chọn làm backing heap.

**Atomicity khác durability:** `AtomicInteger.incrementAndGet()` bảo đảm tính nguyên tử đối với các luồng trong cùng tiến trình theo API, không bảo đảm số tăng đã được flush bền vững tới media sau khi mất điện.

## 8. Chương trình Java 17+ độc lập để kiểm chứng ngữ nghĩa

Chương trình sau cố ý không đọc một địa chỉ vật lý nào. Nó kiểm tra tính đúng đắn của **array object trên Java heap**, **atomic update qua nhiều thread**, và phân biệt **direct buffer memory** ngoài Java heap.

Lưu toàn bộ vào file **HeapDeviceSemanticsDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class HeapDeviceSemanticsDemo {
    private static final class SharedLedger {
        final AtomicInteger completed = new AtomicInteger();
        final int[] values = {10, 20, 30};
    }

    public static void main(String[] args)
            throws InterruptedException {

        SharedLedger ledger = new SharedLedger();
        int workers = 4;
        int incrementsPerWorker = 1_000;

        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(workers);

        for (int id = 0; id < workers; id++) {
            Thread thread = new Thread(() -> {
                try {
                    start.await();
                    for (int i = 0; i < incrementsPerWorker; i++) {
                        ledger.completed.incrementAndGet();
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            }, "worker-" + id);

            thread.start();
        }

        start.countDown();
        finished.await();

        ByteBuffer buffer = ByteBuffer.allocateDirect(32);

        int sum = 0;
        for (int value : ledger.values) {
            sum += value;
        }

        System.out.println("array sum: " + sum);
        System.out.println("atomic count: "
                + ledger.completed.get());
        System.out.println("count valid: "
                + (ledger.completed.get()
                   == workers * incrementsPerWorker));
        System.out.println("direct buffer: " + buffer.isDirect());
    }
}
~~~

### 8.1. Biên dịch và chạy với heap mặc định

~~~bash
javac HeapDeviceSemanticsDemo.java
java -Xms64m -Xmx64m HeapDeviceSemanticsDemo
~~~

**Stdout đã xác minh trên OpenJDK 21:**

~~~text
array sum: 60
atomic count: 4000
count valid: true
direct buffer: true
~~~

Các giá trị này do logic chương trình quyết định, không phụ thuộc thứ tự thread hoàn thành trong điều kiện bình thường: mọi lần `incrementAndGet()` nguyên tử, và `finished.await()` đợi các thread kết thúc.

### 8.2. Chạy với file-backed heap để kiểm tra cờ

Trên Linux, có thể làm **smoke test cú pháp** với một thư mục **được phép ghi** trên filesystem thông thường:

~~~bash
java -Xms64m -Xmx64m -XX:AllocateHeapAt=/tmp HeapDeviceSemanticsDemo
~~~

Với cấu hình được hệ điều hành/JVM chấp nhận, stdout chức năng vẫn là:

~~~text
array sum: 60
atomic count: 4000
count valid: true
direct buffer: true
~~~

Lệnh này đã được kiểm tra thành công trên **OpenJDK 21/Linux** với `/tmp` làm backing.

**CẢNH BÁO:** `/tmp` **không chứng minh JVM đang dùng NV-DIMM, DAX hay physical memory khác DRAM**. Nó chỉ kiểm tra rằng JVM trên máy thử nghiệm chấp nhận cờ và có thể sử dụng file-backed mapping tại directory đó. Không dùng kết quả này làm bằng chứng hardware placement.

### 8.3. Chạy trên thiết bị memory-like thực sự

**Chỉ sau khi đội vận hành đã cấu hình** filesystem/DAX phù hợp và xác minh đường dẫn, ví dụ `/mnt/dax-heap`:

~~~bash
java -Xms64m -Xmx64m -XX:AllocateHeapAt=/mnt/dax-heap HeapDeviceSemanticsDemo
~~~

Cả hai lần chạy cần có kết quả **logic** giống nhau. Nhưng việc đúng stdout **không đủ** để kết luận backing device đã được sử dụng như mong muốn; phải đối chiếu mount/device mapping và metrics/log của hệ điều hành.

### 8.4. Direct buffer không thuộc cùng bài toán

Chương trình tạo:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(32);
~~~

`buffer.isDirect()` trả true. **Đối tượng Java wrapper `ByteBuffer`** là một Java object, nhưng **payload direct buffer** thường được cấp phát ngoài Java heap. `AllocateHeapAt` không phải một cờ để chuyển mọi native/direct allocation sang cùng thiết bị.

## 9. Quy trình chuẩn bị Linux filesystem và thiết bị

**Không chạy lệnh định dạng ổ đĩa hoặc mount DAX một cách tùy tiện trên máy production.** Cần được quản trị viên hệ thống xác nhận thiết bị, tính tương thích và kế hoạch bảo toàn dữ liệu. Bài này chỉ sử dụng các lệnh **đọc/kiểm tra** và giả định một mount đã được cấu hình đúng.

### 9.1. Nhận diện thiết bị và mount

~~~bash
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS
findmnt -T /mnt/dax-heap
df -h /mnt/dax-heap
~~~

- `lsblk`: xem các block devices/filesystem và mountpoint.
- `findmnt`: xem filesystem chứa đường dẫn.
- `df`: xem thông tin dung lượng filesystem tại thời điểm đọc.

Những lệnh này có giá trị ban đầu, nhưng **không tự chứng minh file mappings đang active DAX**. Filesystem có thể dùng `ext4`, `xfs` hoặc hình thức hỗ trợ DAX khác tùy kernel; tên filesystem **không đủ**.

### 9.2. Kiểm tra trạng thái DAX thực

Theo tài liệu Linux kernel về **Direct Access for files**, cần phân biệt:

- **`FS_XFLAG_DAX`**: cờ persistent/configuration của inode hoặc directory, được kế thừa trong một số trường hợp.
- **`S_DAX`**: trạng thái DAX **đang có hiệu lực** của file khi inode được nạp.
- **`STATX_ATTR_DAX`**: thuộc tính mà `statx(2)` có thể trả để xác nhận **S_DAX**.

Ví dụ trên hệ thống có tiện ích phù hợp (khả năng cụ thể tùy bản Linux/util-linux):

~~~bash
statx /mnt/dax-heap/some-probe-file
~~~

Dòng trên chỉ là **mẫu công cụ để kiểm tra**, không bảo đảm hệ Linux nào cũng có executable `statx` trong PATH. Nếu tiện ích không có, dùng `statx(2)` qua công cụ phù hợp, `xfs_io` khi filesystem là XFS, hoặc công cụ monitoring của filesystem/kernel. Quan trọng là **xác minh active DAX của file**, không chỉ một tùy chọn mount trên giấy.

**Không tự tạo/ghi đè file quan trọng** để làm probe. Có thể dùng một file kiểm thử riêng trong directory được cấp phép, không đụng backing file mà JVM đang sử dụng. Khi đã kiểm chứng device layer, xem thêm log JVM và tài nguyên để xác định mapping heap.

### 9.3. Kiểm tra filesystem có đủ dung lượng và quyền

Với cấu hình `-Xmx2g`, cần lập kế hoạch cho device backing capacity **đủ lớn** theo yêu cầu JVM/OS và overhead, không chỉ cho `-Xms512m`. Mức cần đặt chỗ/commit cụ thể phụ thuộc HotSpot, filesystem, sparse allocation, huge-page settings và chế độ map.

Kiểm tra:

- Directory tồn tại, writable đối với **user chạy JVM**.
- Filesystem không read-only, không hết quota/free space.
- Quyền mount/container không chặn mmap cần thiết.
- Có kế hoạch giám sát dung lượng filesystem, health của thiết bị và lỗi media.
- Không chia sẻ thư mục backing giữa các tiến trình theo cách khiến quyền/ownership hoặc dữ liệu nhạy cảm bị lộ.

## 10. GC và heap flags vẫn giữ vai trò bình thường

Oracle mô tả các cờ heap/GC quen thuộc như `-Xms`, `-Xmx` và GC-related flags **tiếp tục hoạt động** khi heap được đặt trên thiết bị thay thế.

Ví dụ:

~~~bash
java -Xms1g -Xmx4g -XX:+UseG1GC -XX:AllocateHeapAt=/mnt/dax-heap -jar app.jar
~~~

Ý nghĩa:

- `-Xms1g`: initial heap.
- `-Xmx4g`: max heap.
- `-XX:+UseG1GC`: dùng G1 nếu JVM/OS hỗ trợ cấu hình.
- `-XX:AllocateHeapAt=...`: chọn backing directory cho object heap.
- `-jar app.jar`: launch ứng dụng.

Đừng kết luận tất cả các GC algorithms, modes, huge-page settings và flags **đều hỗ trợ mọi kết hợp** chỉ vì Oracle nói heap/GC flags tiếp tục hoạt động. Việc hỗ trợ cụ thể có thể khác theo JDK, OS và GC. **Kiểm tra collector được chọn, JVM start thành công và bộ nhớ thực tế.**

### 10.1. Vì sao GC có thể nhạy cảm với thiết bị backing?

GC phải:

- Truy cập các object/headers/references trên heap.
- Đánh dấu object còn sống.
- Di chuyển/copy object trong nhiều collector.
- Đọc/ghi dữ liệu metadata phục vụ heap management.

Một thiết bị có latency cao hơn DRAM hoặc bandwidth thấp hơn có thể làm các pha GC kéo dài. Khi live set lớn hoặc tỷ lệ copy cao, tác động có thể rõ hơn so với một workload truy cập dữ liệu tuần tự.

**Không có số phần trăm slowdown/speedup chung**. GC thời gian thực tế cần được đo theo collector và workload, gồm pause p95/p99, total GC time, application throughput và CPU utilization.

### 10.2. `-XX:+AlwaysPreTouch` cần cân nhắc

~~~bash
java -Xms2g -Xmx2g -XX:+AlwaysPreTouch -XX:AllocateHeapAt=/mnt/dax-heap -jar app.jar
~~~

`AlwaysPreTouch` yêu cầu JVM truy cập các trang heap trong giai đoạn khởi tạo để chúng được hiện thực hóa sớm. Trên vùng backing rất lớn hoặc chậm, thao tác này có thể gây **chi phí startup đáng kể**, thêm pressure lên device capacity/commit. Nó không phải cờ bắt buộc của JEP 316.

Dùng chỉ khi muốn so sánh chiến lược pre-touch và hiểu tác động startup/steady-state; không tự bật cho mọi deployment.

## 11. Dữ liệu trên thiết bị không mất điện không đồng nghĩa Java object persistence

Thiết bị **non-volatile memory** có thể giữ bit sau khi mất điện, nhưng **JVM heap là trạng thái thực thi tạm thời của tiến trình**.

Một Java object không đơn thuần là các bytes dữ liệu:

- Nó có identity/reference được quản lý theo JVM run.
- Header, layout, class metadata, GC card table/barriers và các thành phần hỗ trợ có phụ thuộc runtime.
- Đối tượng có thể được **di chuyển** bởi collector.
- Quan hệ tham chiếu và class loading graph không được định nghĩa như một định dạng lưu trữ độc lập cho lần chạy sau.
- Các thao tác `volatile`, CAS và `synchronized` liên quan đến **memory ordering/atomicity**, không đặt ra durable commit protocol.

Ví dụ:

~~~java
static class Counter {
    int value = 10;
}
~~~

Ngay cả khi instance `Counter` tồn tại trên một vùng persistent-memory-backed heap, Java SE **không định nghĩa** việc lần khởi động JVM tiếp theo tự lấy lại object `Counter` này và tiếp tục tăng `value` từ 10.

**Muốn dữ liệu thật sự bền vững**, hãy dùng database, durable storage API, serialization/checkpoint hoặc giải pháp persistent-memory được thiết kế **rõ ràng cho persistence/consistency/recovery**. `AllocateHeapAt` không đáp ứng yêu cầu đó.

### 11.1. Rủi ro dữ liệu còn tồn tại vật lý

Bộ nhớ bền vững có thể giữ một số bytes của heap sau khi tiến trình kết thúc hoặc bị crash. Dù JVM không cung cấp object recovery API, dữ liệu nhạy cảm có thể vẫn tồn tại ở mức media hoặc các vùng lưu trữ tạm.

Biện pháp vận hành:

- Chỉ cho phép user đáng tin tạo/mmap backing files.
- Cấu hình quyền thư mục và isolation phù hợp.
- Kiểm soát lifecycle, khóa mount/device, encryption khi có chính sách.
- Thiết kế cơ chế sanitization/decommission của thiết bị theo yêu cầu bảo mật.
- Không coi việc **unlink/delete file** hoặc JVM exit là phương pháp **secure erase** thiết bị.
- Không đặt dữ liệu nhạy cảm vào môi trường chia sẻ với principal không tin cậy chỉ vì đường dẫn là “temporary”.

Đây là rủi ro của **physical media/data remanence**, khác với tính bền vững có thể lập trình của Java objects.

## 12. Allocation path phải đúng thiết bị, không phải chỉ đúng tên

Một lỗi thường gặp:

~~~bash
mkdir -p /mnt/pmem
java -XX:AllocateHeapAt=/mnt/pmem -jar app.jar
~~~

Lệnh tạo directory **không hề tạo NV-DIMM hay bật DAX**. Nếu `/mnt/pmem` nằm trên một filesystem thường, JVM có thể dùng file-backed mapping với **page cache/DRAM/I/O behavior khác**, hoặc không thành công vì ràng buộc nền tảng. Tên `pmem` chỉ là một nhãn.

Một bài kiểm tra hợp lệ cần trả lời:

1. `/mnt/dax-heap` thuộc **filesystem/device nào**?
2. Thiết bị đó có CPU-addressable mapping và atomic semantics được OS hỗ trợ không?
3. **Active DAX state** có hiệu lực cho backing file không?
4. JVM đã **nhận option** và mapping heap tại directory mong đợi không?
5. File-backed pages có đang dùng **thiết bị vật lý** mong muốn hay chỉ page cache?
6. Dung lượng/độ trễ/bandwidth/GC overhead và quota có phù hợp workload không?

Không có một API Java chuẩn đơn giản kiểu `System.out.println(heapOnNvdimm())` để xác nhận cả sáu điều kiện trên. Phải đối chiếu **HotSpot flags/logs, OS mapping, filesystem và device metrics**.

## 13. Vị trí vật lý: NUMA và thiết bị chậm hơn DRAM

Trên máy nhiều socket/NUMA node, locality và đường liên kết CPU-memory ảnh hưởng latency và bandwidth.

Một thiết bị bộ nhớ thay thế có thể:

- Gắn gần một socket hơn socket khác.
- Có bandwidth đọc/ghi không cân đối.
- Có độ trễ cao hơn DRAM.
- Chịu contention khi nhiều JVM cùng sử dụng.
- Có giới hạn capacity, wear/lifespan hay tình trạng health tùy công nghệ.

Do đó nên đo:

- **Throughput** application và GC.
- **Latency** p50/p95/p99, thời gian hoàn thành request.
- **GC pause time** và % CPU của GC threads.
- **Page faults**, memory mapping, NUMA locality.
- **Device utilization, read/write bandwidth**.
- **RSS/cgroup memory usage** và host memory pressure.
- **Startup time** với/không với pre-touch.

Với một ứng dụng nhỏ và ít đối tượng, lợi ích từ dung lượng lớn có thể không đáng chi phí triển khai. Với workload rất nhạy latency, heap chậm hơn có thể phản tác dụng; một chiến lược lưu **một phần dữ liệu trong cache ngoài heap/ngoài JVM** có thể cần cân nhắc nhưng thuộc thiết kế ứng dụng khác.

**Không tự suy ra** memory-like device nhanh hơn SSD trong mọi cách truy cập. DAX giảm đi một số đường I/O/page-cache overhead, nhưng hiệu năng tổng vẫn phụ thuộc công nghệ và truy cập thực.

## 14. Container và giới hạn bộ nhớ

Đặt heap trên một alternative backing filesystem **không đồng nghĩa** có thể vượt `-Xmx`, cgroup hard limit hay toàn bộ ngân sách bộ nhớ của workload.

Những điều cần kiểm tra:

- `-Xmx` vẫn giới hạn Java object heap.
- Cgroup có thể hạch toán file-backed mappings và memory pages theo quy tắc kernel đang dùng.
- CPU/NUMA/persistent-memory device có thể được mount vào container nhưng cần quyền và tính tương thích cụ thể.
- Container memory limit và host accounting khác nhau; không dự đoán “đặt heap trên PMEM sẽ miễn toàn bộ container memory usage”.
- Non-heap/native còn nằm trong ngân sách của process/container.

Nếu deploy trên Kubernetes, hãy xem memory requests/limits, mount point, quyền đọc/ghi, access mode và node affinity cho thiết bị phù hợp. Không cho rằng mọi node trong cluster có cùng filesystem DAX chỉ vì `/mnt/dax-heap` được mount ở một node.

**Gợi ý vận hành:** workload dùng thiết bị đặc biệt cần scheduling tới node có đúng hardware/driver, bên cạnh memory capacity và permission. Nếu container được chuyển sang node không có device đó, startup với `AllocateHeapAt` có thể thất bại.

## 15. Chẩn đoán nhanh khi lệnh không chạy đúng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và hướng xử lý |
| --- | --- | --- |
| JVM không nhận `AllocateHeapAt` | JVM không phải HotSpot hoặc bản JDK không hỗ trợ | `java -version`, `-XX:+PrintFlagsFinal`, đối chiếu tài liệu đúng build |
| Không thể tạo heap backing | Directory thiếu, không có quyền ghi, read-only mount | Kiểm tra `findmnt`, quyền directory, quota và stderr |
| Startup thất bại vì thiếu không gian | Device không đủ capacity cho heap mapping | Đo free space/quota và yêu cầu `-Xmx` |
| Chạy được nhưng không thấy DAX | Chỉ là filesystem thường hoặc DAX chưa active | Xem `S_DAX`/`STATX_ATTR_DAX`, mapping/device |
| Chạy được nhưng performance thấp | Thiết bị chậm hơn DRAM, page faults, GC copy bandwidth | Benchmark và đo NUMA/device/GC |
| RSS cao dù heap đặt ngoài DRAM | Metaspace, native/direct buffers, page accounting | NMT + RSS/cgroup + device mapping |
| GC pause tăng | Live set/copy/mark trên thiết bị latency cao | GC log `-Xlog:gc*`, JFR và workload |
| Dữ liệu mất sau JVM restart | Heap không có hợp đồng persistence | Dùng durable storage/checkpoint được thiết kế đúng |
| JVM chạy trên node A nhưng fail trên B | Hardware/filesystem/permission không đồng nhất | Scheduling/node affinity, kiểm tra mount và JDK |
| Lệnh test `/tmp` thành công nhưng PMEM không hoạt động | Test chỉ chứng minh flag/mmap thông thường | Xác minh DAX active và hardware backing |
| Có file còn lại sau crash | Lifecycle/sanitization và persistent media | Xem data-remanence policy, không coi file còn là heap phục hồi |
| `AtomicInteger` hoạt động sai | Sai môi trường/JVM/hardware, bug hoặc concurrency khác | Không dùng thiết bị đó; kiểm thử đúng đắn trước benchmark |

### Dùng những lệnh kiểm tra nào?

~~~bash
java -version
java -XX:+PrintFlagsFinal -version
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS
findmnt -T /mnt/dax-heap
df -h /mnt/dax-heap
~~~

Với Java app có sẵn, muốn xem thông tin GC:

~~~bash
java -Xlog:gc*=info -Xms512m -Xmx2g -XX:AllocateHeapAt=/mnt/dax-heap -jar app.jar
~~~

Dạng log tùy JDK/GC, không có một dòng stdout cố định. **Đừng dùng GC log thay cho kiểm tra DAX/device mapping**; GC log cho biết GC behavior, không chứng minh physical backing của mọi page.

Để kiểm tra cờ `AllocateHeapAt` có trong build HotSpot, dùng `-XX:+PrintFlagsFinal` và tìm tên cờ. **Sự hiện diện của cờ chỉ xác nhận JVM hỗ trợ flag, không xác nhận thiết bị.**

## 16. Benchmark: đánh giá đúng mục tiêu đặt heap

Muốn biết alternative heap có phù hợp, so sánh hai cấu hình **trên cùng ứng dụng, cùng JDK, cùng CPU và tải tương đương**.

| Nhóm | Lệnh minh họa | Ý nghĩa |
| --- | --- | --- |
| A: Heap mặc định | `java -Xms2g -Xmx2g -jar app.jar` | Baseline thường trên DRAM |
| B: Heap alternative | `java -Xms2g -Xmx2g -XX:AllocateHeapAt=/mnt/dax-heap -jar app.jar` | Dùng đường mapping tới device được xác minh |
| C: Heap alternative + pre-touch | Như B, thêm `-XX:+AlwaysPreTouch` | Đo startup/commit khác biệt |
| D: Heap nhỏ hơn trên DRAM | `java -Xms1g -Xmx1g -jar app.jar` | Đánh giá tác động capacity khác size, **không dùng thay so sánh A/B chính** |

Đo ít nhất:

1. **Application throughput** và request latency p50/p95/p99.
2. **Java heap committed/used** và live set behavior.
3. **GC pause** p95/p99, số chu kỳ full/mixed/young, total GC time.
4. **Device bandwidth, latency, faults** theo công cụ OS.
5. **Host DRAM usage** của phần native/metaspace/stack.
6. **Time to startup** khi dùng `AlwaysPreTouch` hoặc khi memory mappings lớn.
7. **Capacity utilization/quotas** của device backing.
8. **Failure behavior** khi storage/device gặp lỗi.

Nếu heap ở alternative device cho throughput kém hơn nhưng cho phép chạy workload **trước đây không đủ DRAM**, nó vẫn có thể hữu ích về năng lực hệ thống. Ngược lại, nếu bộ nhớ thay thế có cost/latency không tốt, giữ heap ở DRAM có thể là lựa chọn tốt nhất.

**Đừng so** 2 GiB heap alternative với 512 MiB heap DRAM rồi quy mọi khác biệt cho vị trí memory. Heap size thay đổi sẽ ảnh hưởng GC, số pause và khả năng sống của object.

### Kịch bản thực nghiệm không đủ bằng chứng

Chạy một lần:

~~~bash
java -XX:AllocateHeapAt=/tmp HeapDeviceSemanticsDemo
~~~

rồi nhận `count valid: true`. Kết quả đó **chỉ xác minh đúng đắn chức năng và chấp nhận flag**. Nó không đo memory latency, không xác nhận DAX, không chứng minh JVM lưu đối tượng vào NVDIMM, không chứng minh performance tốt hơn DRAM.

## 17. An toàn, quyền truy cập và quản trị vòng đời

Vì heap là nơi chứa dữ liệu nhạy cảm (chuỗi, token, thông tin người dùng, object caches), filesystem dùng làm backing cần các biện pháp phù hợp:

- Directory và mount chỉ cho **principal được cấp quyền** truy cập.
- Không mở rộng write permission cho user không tin cậy.
- Không coi tệp tạm của heap là cấu trúc được phép sao chép/phân tích tùy ý.
- Bảo vệ crash artifacts, core dumps, heap dumps hoặc log chứa thông tin nhạy cảm.
- Có chính sách xóa dữ liệu ở mức **media** khi decommission nếu thiết bị có khả năng lưu bytes qua mất điện.
- Theo dõi sức khỏe thiết bị, lỗi mapping và capacity alerts.
- Không chia sẻ device giữa nhiều JVM không tin cậy mà thiếu isolation.
- Không tự chạy `mkfs`/`mount`/`ndctl` tác động phần cứng trên production khi chỉ cần chẩn đoán.

Ngay cả khi backing file tạm được JVM unlink, **việc unlink không tương đương secure erase**. Phân biệt vòng đời file/mapping ở hệ điều hành với nhu cầu bảo mật dữ liệu vật lý của tổ chức.

## 18. Câu hỏi và bài tập tự kiểm tra

### Bài 1 — mục tiêu chính của JEP 316

**Hỏi:** JEP 316 ở Java 10 dùng để đặt phần nào của JVM trên alternative memory device?

**Đáp án:** Chủ yếu là **Java object heap**. Nó không đặt toàn bộ process, metaspace, code heap, native thread stacks hoặc mọi direct buffer payload lên thiết bị đó.

### Bài 2 — ngữ nghĩa tối thiểu

**Hỏi:** Một ổ lưu trữ có thể `mmap` file nhưng không có cơ chế truy cập memory-like/atomic semantics tương thích DRAM. Có thể mặc định dùng nó làm backing Java heap phù hợp không?

**Đáp án:** **Không.** `mmap` một file chỉ là cơ chế ánh xạ; cần kiểm tra device/OS/filesystem có cung cấp **load/store và atomic semantics** như yêu cầu.

### Bài 3 — `volatile` có đảm bảo persistence?

**Hỏi:** Thay DRAM bằng non-volatile memory rồi gọi `volatile` write. Có thể khẳng định sau power failure một JVM mới sẽ đọc lại object graph đó không?

**Đáp án:** **Không.** Java Memory Model đảm bảo visibility/ordering giữa các luồng đang chạy; JEP 316 không bổ sung hợp đồng phục hồi heap sau restart.

### Bài 4 — so output của Java code

**Hỏi:** Ví dụ `HeapDeviceSemanticsDemo` chạy với heap thường và heap file-backed, trong điều kiện bình thường phải in `atomic count` bao nhiêu?

**Đáp án:** **4000**, vì 4 thread × 1000 lần `AtomicInteger.incrementAndGet()`; output đúng không chứng minh physical backing.

### Bài 5 — directory hay heap dump?

**Hỏi:** `-XX:AllocateHeapAt=/mnt/dax-heap` có giống `-XX:HeapDumpPath=/mnt/dax-heap/report.hprof` không?

**Đáp án:** **Không.** `AllocateHeapAt` chọn filesystem directory/backing mapping cho **heap sống**; `HeapDumpPath` chọn đường dẫn lưu **snapshot heap dump** khi được bật.

### Bài 6 — direct buffer

**Hỏi:** `ByteBuffer.allocateDirect(1024)` có bảo đảm 1024 byte payload nằm cùng alternative Java object heap không?

**Đáp án:** **Không.** Direct buffer payload thường nằm ngoài Java heap; chỉ wrapper object thuộc heap Java.

### Bài 7 — kiểm tra DAX

**Hỏi:** Directory `/mnt/pmem` dùng filesystem ext4. Có đủ chứng cứ rằng một file trong đó active DAX không?

**Đáp án:** **Không.** Phải kiểm tra backing device, hỗ trợ/mount settings và **active `S_DAX`** của file theo hướng dẫn Linux kernel.

### Bài 8 — `-Xmx` có còn hoạt động?

**Hỏi:** Đã dùng `-XX:AllocateHeapAt` thì `-Xmx4g` còn giới hạn heap không?

**Đáp án:** **Có.** Các cờ heap và GC cơ bản tiếp tục dùng để điều khiển kích thước/collector; placement không có nghĩa heap vô hạn.

### Bài 9 — tại sao GC có thể chậm hơn?

**Hỏi:** Thiết bị có bandwidth thấp hơn DRAM. G1 phải copy nhiều live objects. Hiệu năng có chắc tăng không?

**Đáp án:** **Không.** GC phải đọc/ghi objects trên thiết bị backing; độ trễ/bandwidth có thể làm pause hoặc throughput xấu hơn. Cần benchmark thật.

### Bài 10 — lựa chọn nền tảng

**Hỏi:** Một người nói “Tôi có NVMe SSD, nên dùng `AllocateHeapAt` chắc chắn sẽ nhanh như RAM”. Điều gì chưa được chứng minh?

**Đáp án:** **Khả năng memory-like CPU load/store, atomic semantics, filesystem DAX và physical backing**. Một SSD thông thường là **block storage**, không được coi là bộ nhớ DRAM chỉ vì có thể chứa file.

## 19. Checklist vận hành trước khi áp dụng

- [ ] Đã xác minh JDK/HotSpot/OS hỗ trợ `-XX:AllocateHeapAt` trong đúng build.
- [ ] Đã biết rõ thiết bị, driver, filesystem, mountpoint và quyền ghi.
- [ ] Đã kiểm tra **ngữ nghĩa truy cập bộ nhớ và atomics** thích hợp.
- [ ] Đã xác minh **active DAX** ở file/FS level nếu đây là yêu cầu deployment.
- [ ] Đã xác định `-XX:AllocateHeapAt` trỏ tới **thư mục**, không phải heap dump.
- [ ] Đã lập ngân sách device capacity theo `-Xms`, `-Xmx` và overhead.
- [ ] Đã lập ngân sách DRAM cho metaspace, code cache, native/direct buffers và thread stacks.
- [ ] Đã kiểm tra startup, GC, object allocations, concurrency/atomics và kết quả ứng dụng.
- [ ] Đã ghi nhận benchmark A/B cùng JDK, heap size, workload và CPU.
- [ ] Đã phân biệt **JMM atomicity** với **persistence/durability**.
- [ ] Đã xác minh file/mapping permissions, data sanitization và device health.
- [ ] Đã có phương án fallback hoặc loại bỏ cấu hình nếu device/mount không sẵn sàng.
- [ ] Đã đánh giá container/node affinity nếu chạy nhiều máy.
- [ ] Không sử dụng thành công của bài thử `/tmp` làm bằng chứng “đã dùng PMEM”.

## 20. Tóm tắt và tài liệu chính thức

**Ghi nhớ theo ba tầng:**

1. **Java/JVM layer:** `-XX:AllocateHeapAt` đặt **Java object heap** trên backing memory được chỉ định; `-Xmx`, `-Xms` và GC flags vẫn có vai trò.
2. **Hardware/OS layer:** thiết bị phải cho phép CPU **load/store và atomic operations với ngữ nghĩa như DRAM**; DAX là cơ chế có thể bypass page cache và map trực tiếp physical device vào user address space.
3. **Application/persistence layer:** Java objects vẫn là **heap do GC quản lý**, không tự sống lại qua JVM restart. **Atomicity/visibility ≠ durability**; persistence cần thiết kế storage/recovery riêng.

Tài liệu vẫn có giá trị:

1. [OpenJDK — JEP 316: Heap Allocation on Alternative Memory Devices (JDK 10)](https://openjdk.org/jeps/316).
2. [Oracle Java SE 17 — The java Command, `-XX:AllocateHeapAt`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
3. [Oracle Java SE 25 — The java Command, `-XX:AllocateHeapAt`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
4. [Oracle Java SE 26 — The java Command, `-XX:AllocateHeapAt`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
5. [Linux kernel — Direct Access for files (DAX)](https://docs.kernel.org/filesystems/dax.html).
6. [NVDIMM kernel docs — Persistent Memory / Filesystems](https://nvdimm.docs.kernel.org/).
7. [Java SE 17 — `AtomicInteger` và memory effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html).
8. [Java SE 17 — `ByteBuffer.allocateDirect`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html#allocateDirect(int)).
9. [Linux kernel — Memory management và memory mappings](https://docs.kernel.org/admin-guide/mm/index.html).

**Kết luận:** Mục tiêu đặt Java heap trên thiết bị bộ nhớ thay thế từ Java 10 là **thêm lựa chọn về dung lượng và vị trí của object heap mà vẫn giữ đúng ngữ nghĩa bộ nhớ như DRAM**. Cờ `-XX:AllocateHeapAt` chỉ là bước cấu hình JVM; để dùng đúng, phải xác minh **thiết bị + OS/filesystem DAX + atomic semantics + JVM mapping + ngân sách DRAM còn lại**, rồi đo cả hiệu năng và tính đúng đắn. Không được nhầm **một file mmap thành công** với **PMEM/DAX thật**, hoặc nhầm **non-volatile hardware** với **persistent Java object graph**.
