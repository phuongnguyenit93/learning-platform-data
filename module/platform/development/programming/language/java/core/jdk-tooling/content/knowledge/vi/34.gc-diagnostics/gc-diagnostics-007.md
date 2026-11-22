# Heap sizing trong Java: chọn kích thước heap theo workload và giới hạn bộ nhớ

**Heap sizing** là quá trình xác định dung lượng Java heap phù hợp để ứng dụng giữ được tập object đang sống, hấp thụ các đợt cấp phát và đạt mục tiêu latency/throughput mà không vượt giới hạn bộ nhớ của máy hoặc container.

Heap quá nhỏ khiến GC chạy dày, ứng dụng mất thời gian thu gom và có thể gặp **OutOfMemoryError**. Heap quá lớn chiếm ngân sách RAM dành cho các phần khác của JVM, các process cùng host và hệ điều hành. Kích thước tốt phải được đo bằng workload thực tế, sau đó xác nhận bằng GC log, heap metrics và hiệu năng ứng dụng.

## 1. Java heap là gì?

Java heap là vùng bộ nhớ JVM dùng để cấp phát phần lớn object và array được tạo trong ứng dụng. Garbage Collector (GC) xác định object còn reachable, thu hồi vùng nhớ của object không còn được sử dụng và tái sử dụng vùng heap đã thu hồi.

Ví dụ:

~~~java
Customer customer = new Customer();
byte[] payload = new byte[1024 * 1024];
~~~

Object `Customer` và array `payload` được cấp phát trên heap. Local variable và reference có thể nằm trong stack frame hoặc được tối ưu hóa bởi JIT, nhưng object mà chúng trỏ tới thường vẫn nằm trên heap.

Heap sizing tập trung vào dung lượng heap. Nó không trực tiếp đặt giới hạn cho toàn bộ bộ nhớ process.

### Heap khác gì với bộ nhớ process?

Một JVM còn cần nhiều vùng bộ nhớ khác:

| Vùng bộ nhớ | Nội dung |
|---|---|
| Java heap | Object và array của ứng dụng |
| Metaspace | Metadata của class và class loader |
| Code cache | Native code do JIT compiler sinh ra |
| Thread stacks | Stack riêng của từng platform thread |
| Direct buffers | Buffer ngoài heap, thường dùng cho I/O |
| GC và JVM native structures | Cấu trúc nội bộ, bảng tham chiếu, vùng hỗ trợ GC |
| JNI/native allocations | Bộ nhớ do native library hoặc code JNI cấp phát |
| Shared libraries và memory mappings | Thư viện, file và vùng nhớ ánh xạ |

Vì vậy, `-Xmx2g` không có nghĩa toàn bộ process chỉ dùng tối đa 2 GiB. Nếu container có giới hạn 2 GiB và heap đã được phép dùng gần hết giới hạn đó, JVM vẫn có thể bị hệ điều hành/container kết thúc do metaspace, thread stack, direct buffer hoặc native allocation làm tổng memory vượt giới hạn.

## 2. Phân biệt used, committed, reserved và max heap

Bốn khái niệm này thường xuất hiện trong log, JMX, `Runtime` API và công cụ chẩn đoán:

| Khái niệm | Ý nghĩa |
|---|---|
| **Used** | Dung lượng heap hiện đang được object sử dụng |
| **Committed** | Dung lượng heap JVM đã commit và có thể dùng ngay |
| **Reserved** | Không gian địa chỉ JVM đã reserve cho heap; không đồng nghĩa toàn bộ vùng này đang chiếm RAM vật lý |
| **Max** | Giới hạn heap tối đa JVM được phép sử dụng |

Trong Java Management API:

~~~java
Runtime runtime = Runtime.getRuntime();

long used = runtime.totalMemory() - runtime.freeMemory();
long committed = runtime.totalMemory();
long max = runtime.maxMemory();
~~~

- `totalMemory()` trả về dung lượng heap hiện tại JVM đã commit.
- `freeMemory()` trả về phần còn trống bên trong vùng heap đã commit.
- `maxMemory()` trả về giới hạn heap tối đa.

Do đó:

~~~text
used = committed - free
used <= committed <= max
~~~

Đây là quan hệ tổng quát để đọc các giá trị heap. Giá trị thực tế có thể thay đổi trong quá trình GC và điều chỉnh kích thước heap.

Ví dụ minh họa:

~~~text
used      = 420 MiB
committed = 768 MiB
reserved  = 2 GiB
max       = 2 GiB
~~~

Ứng dụng đang dùng khoảng 420 MiB object; JVM đã commit 768 MiB và có thể mở rộng heap tới tối đa 2 GiB. `reserved` không nên được hiểu là 2 GiB RAM vật lý đang bị chiếm.

## 3. Hai tùy chọn quan trọng: -Xms và -Xmx

### 3.1. -Xms: heap ban đầu và tối thiểu

`-Xms` đặt kích thước heap ban đầu và mức heap tối thiểu JVM giữ trong quá trình chạy.

Ví dụ:

~~~sh
java -Xms256m -jar app.jar
~~~

JVM khởi tạo với heap tối thiểu 256 MiB. Nếu không đặt `-Xms`, JVM chọn kích thước ban đầu theo ergonomics và môi trường.

### 3.2. -Xmx: heap tối đa

`-Xmx` đặt giới hạn tối đa của Java heap.

Ví dụ:

~~~sh
java -Xmx2g -jar app.jar
~~~

JVM không được mở rộng Java heap vượt quá 2 GiB. Nếu ứng dụng cần thêm heap nhưng GC không thu hồi đủ object, allocation có thể thất bại và phát sinh `OutOfMemoryError: Java heap space`.

### 3.3. Kết hợp Xms và Xmx

Ví dụ:

~~~sh
java -Xms512m -Xmx2g -jar app.jar
~~~

Heap ban đầu/tối thiểu là 512 MiB và có thể tăng đến 2 GiB.

| Cấu hình | Hành vi |
|---|---|
| `-Xms256m -Xmx2g` | Heap có thể tăng từ 256 MiB tới 2 GiB |
| `-Xms2g -Xmx2g` | Heap ban đầu, tối thiểu và tối đa đều là 2 GiB |
| Không đặt cả hai | JVM tự chọn giá trị theo ergonomics và môi trường |

Đặt `-Xms` bằng `-Xmx` thường được dùng cho service có tải ổn định và đã có ngân sách RAM rõ ràng. Cấu hình này giảm việc heap phải mở rộng/thu nhỏ, nhưng cũng khiến JVM giữ mức heap lớn ngay từ đầu.

Nếu cần giảm footprint khi ứng dụng idle hoặc chạy nhiều JVM trên cùng host, có thể giữ `-Xms` thấp hơn `-Xmx`. GC có thể điều chỉnh heap trong khoảng được phép theo mục tiêu của collector.

Các suffix `k`, `m` và `g` dùng để biểu diễn đơn vị kích thước. Ví dụ `-Xms512m`, `-Xmx2g`.

## 4. JVM tự chọn heap bằng ergonomics

Nếu không chỉ định `-Xms` và `-Xmx`, HotSpot dùng ergonomics để chọn giá trị ban đầu và tối đa dựa trên môi trường chạy.

Trong JDK 24, các giá trị phần trăm mặc định quan trọng là:

| Option | Default | Ý nghĩa |
|---|---:|---|
| `-XX:InitialRAMPercentage` | 1.5625% | Tỷ lệ RAM dùng để tính heap ban đầu |
| `-XX:MaxRAMPercentage` | 25% | Tỷ lệ RAM dùng để tính giới hạn heap tối đa |
| `-XX:MinRAMPercentage` | 50% | Tỷ lệ tối đa dùng cho heap trong môi trường có RAM rất nhỏ |

`MinRAMPercentage` có tên dễ gây nhầm: nó không phải phần trăm heap tối thiểu. Nó là tỷ lệ tối đa dành cho heap trong trường hợp heap nhỏ, khoảng 125 MiB theo tài liệu JDK.

JVM xác định lượng RAM tối đa dùng cho việc tính heap dựa trên giá trị nhỏ hơn giữa physical memory và các giới hạn môi trường mà JVM nhận diện được. Vì vậy, cùng một ứng dụng có thể nhận heap tối đa khác nhau khi chạy trên laptop, máy chủ hoặc container.

Có thể xem các flag hiện tại:

~~~sh
java -XX:+PrintFlagsFinal -version
~~~

Lọc các flag liên quan tới heap trên Linux/macOS:

~~~sh
java -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'InitialHeapSize|MaxHeapSize|InitialRAMPercentage|MaxRAMPercentage|MaxRAM'
~~~

Trên Windows PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version | Select-String 'InitialHeapSize|MaxHeapSize|InitialRAMPercentage|MaxRAMPercentage|MaxRAM'
~~~

### 4.1. Điều chỉnh heap theo phần trăm RAM

Ví dụ đặt heap tối đa bằng 60% RAM JVM được phép dùng để tính sizing:

~~~sh
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

Đặt heap ban đầu bằng 15%:

~~~sh
java -XX:InitialRAMPercentage=15 -XX:MaxRAMPercentage=60 -jar app.jar
~~~

Các tỷ lệ này là đầu vào cho ergonomics. Hãy kiểm tra `InitialHeapSize` và `MaxHeapSize` thực tế bằng `VM.flags` hoặc `PrintFlagsFinal`.

`-XX:MaxRAM` có thể dùng để đặt giới hạn RAM đầu vào cho việc tính heap sizing. Ví dụ:

~~~sh
java -XX:MaxRAM=512m -XX:InitialRAMPercentage=12.5 -XX:MaxRAMPercentage=50 -XshowSettings:vm -version
~~~

Trong trường hợp kiểm thử này:

- MaxRAM được đặt là 512 MiB.
- InitialRAMPercentage là 12.5%, tương ứng InitialHeapSize 64 MiB.
- MaxRAMPercentage là 50%, tương ứng MaxHeapSize 256 MiB.

`MaxRAM` không đặt hard memory limit cho process ở hệ điều hành. Nó chỉ điều chỉnh lượng RAM mà JVM dùng làm cơ sở cho ergonomics. Giới hạn process/container vẫn do hệ điều hành hoặc nền tảng quản lý.

## 5. Heap sizing trong Docker và Kubernetes

Khi chạy JVM trong Linux container, JVM có thể đọc giới hạn memory và CPU của container để chọn tài nguyên. Trong JDK 24, `UseContainerSupport` được bật mặc định trên Linux.

Ví dụ container có memory limit 2 GiB. JVM dùng `MaxRAMPercentage` để tính giới hạn heap theo lượng RAM mà nó nhận diện từ môi trường. Với mặc định 25%, heap tối đa có thể vào khoảng 512 MiB nếu giới hạn 2 GiB là cơ sở tính sizing.

Không nên hiểu rằng heap luôn được phép chiếm toàn bộ container memory. Container còn phải chứa:

- Metaspace và code cache.
- Thread stacks.
- Direct buffers và native memory.
- Cấu trúc nội bộ của GC/JVM.
- Thư viện native và memory mapping.
- Process phụ hoặc sidecar nếu chúng dùng chung ngân sách memory ở cấp pod/host.

Ví dụ minh họa: container có giới hạn 2 GiB và bạn đã đo được cần dành khoảng 512 MiB cho native memory cùng headroom. Ngân sách còn lại cho heap tối đa là khoảng 1.5 GiB. Khi đó có thể cân nhắc:

~~~sh
java -Xms512m -Xmx1536m -jar app.jar
~~~

Đây chỉ là ví dụ ngân sách, không phải công thức áp dụng cho mọi ứng dụng. Hãy đo non-heap/native memory dưới tải thật; nếu mức dùng thực tế cao hơn, cần giảm Xmx hoặc tăng memory limit.

### 5.1. Kiểm tra container support

Có thể bật log để xem JVM phát hiện giới hạn container như thế nào:

~~~sh
java -Xlog:os+container=trace -XX:+PrintFlagsFinal -version
~~~

Kiểm tra các flag:

~~~sh
java -XX:+PrintFlagsFinal -version | grep -E 'UseContainerSupport|MaxRAM|MaxRAMPercentage|MaxHeapSize'
~~~

Trên JDK 24, `UseContainerSupport` chỉ áp dụng cho Linux. Nếu JVM không nhận diện được giới hạn container, heap có thể được tính dựa trên RAM của host và vượt ngân sách container. Hãy kiểm tra log/container metrics khi triển khai trong môi trường này.

Không dùng `-XX:MaxRAMPercentage` một cách máy móc. Tỷ lệ phù hợp phụ thuộc vào heap live set, native memory, thread count, direct buffers, sidecar và giới hạn thực tế của container.

## 6. Lập ngân sách bộ nhớ trước khi đặt Xmx

Một cách thực tế là bắt đầu từ memory limit của process/container và trừ phần không dành cho Java heap.

~~~text
Process / container memory limit
       |
       +-- Native memory, metaspace, code cache
       |
       +-- Thread stacks and direct buffers
       |
       +-- GC/JVM structures and libraries
       |
       +-- Safety headroom
       |
       v
Maximum budget available for Java heap
~~~

Có thể dùng công thức ước lượng:

~~~text
Heap budget <= Process memory limit
               - measured non-heap/native usage
               - safety headroom
~~~

Ví dụ:

| Thành phần | Ngân sách minh họa |
|---|---:|
| Container limit | 2048 MiB |
| Native, metaspace, stacks, direct buffers | 300 MiB |
| JVM/GC overhead và thư viện | 100 MiB |
| Headroom cho biến động tải | 200 MiB |
| Còn lại cho heap | 1448 MiB |

Trong ví dụ này, Xmx khoảng 1.4 GiB có thể là điểm bắt đầu để thử nghiệm. Sau đó cần chạy workload đại diện và xác nhận heap có đủ chỗ cho live set, allocation bursts và GC.

Đừng chọn Xmx chỉ dựa trên tổng RAM máy. Nếu nhiều JVM cùng chạy trên host, mỗi process cần một phần ngân sách riêng và phải cộng cả native memory.

## 7. Chọn Xms và Xmx theo workload

### 7.1. Service có tải ổn định

Nếu service có tải ổn định, ngân sách memory rõ ràng và muốn tránh heap resize, có thể đặt Xms gần hoặc bằng Xmx.

~~~sh
java -Xms1g -Xmx1g -jar service.jar
~~~

Cần bảo đảm container có đủ memory cho heap 1 GiB cộng toàn bộ native/non-heap và headroom.

### 7.2. Ứng dụng có tải biến động

Nếu ứng dụng có thời gian idle và các đợt tăng tải, đặt Xms thấp hơn Xmx để JVM có khoảng mở rộng.

~~~sh
java -Xms256m -Xmx1536m -jar worker.jar
~~~

Theo dõi heap committed, GC pause và RSS để xác nhận việc tăng/giảm heap không gây vấn đề.

### 7.3. Batch job

Batch job có thể cần heap lớn trong một giai đoạn xử lý dữ liệu. Hãy sizing theo kích thước batch lớn nhất, số object giữ lại cùng lúc, mức độ streaming và số worker song song.

Nếu batch có thể chia nhỏ hoặc xử lý theo streaming, giảm số object sống đồng thời có thể hiệu quả hơn chỉ tăng Xmx.

### 7.4. Ứng dụng cache nhiều dữ liệu

Cache giữ object reachable nên GC không thể thu hồi các object đó. Nếu cache chiếm phần lớn heap, cần đặt giới hạn cache, TTL hoặc eviction policy. Tăng Xmx chỉ trì hoãn vấn đề khi cache tăng không giới hạn.

## 8. Đo heap live set và allocation trước khi sizing

Heap sizing nên dựa trên các số liệu dưới workload đại diện:

- Heap used và committed theo thời gian.
- Heap occupancy sau các GC cycle.
- Live set: dữ liệu còn reachable sau khi GC thu hồi object chết.
- Allocation rate: lượng object được cấp phát theo thời gian.
- Promotion rate: object được chuyển sang old generation.
- Tần suất và thời lượng GC pause.
- Số lần Full GC và lý do kích hoạt.
- Process RSS/container memory usage.
- Request latency, throughput và error rate.

Heap used cao trong lúc workload đang chạy chưa chắc là vấn đề. Điều quan trọng là GC có thu hồi đủ memory không, live set có ổn định không và heap có còn headroom cho đợt allocation tiếp theo không.

Nếu heap sau mỗi GC ngày càng tăng trong khi workload tương đương, hãy điều tra object bị giữ tham chiếu hoặc cache tăng liên tục. Tăng Xmx không sửa được memory leak; nó chỉ kéo dài thời gian trước khi heap đầy.

Không dùng một lần đo hoặc một đỉnh heap ngắn để đặt cấu hình vĩnh viễn. Hãy thu thập dữ liệu qua nhiều chu kỳ tải, gồm cả peak traffic và các batch job.

## 9. Kiểm tra heap hiện tại bằng jcmd

Tìm PID của JVM:

~~~sh
jcmd -l
~~~

Xem flag hiện tại:

~~~sh
jcmd <pid> VM.flags
~~~

Tìm `InitialHeapSize` và `MaxHeapSize` cùng collector đang dùng.

Xem thông tin heap:

~~~sh
jcmd <pid> GC.heap_info
~~~

Một output G1 có thể có dạng:

~~~text
garbage-first heap   total reserved 98304K, committed 65536K, used 42429K
  region size 1024K, 2 young (2048K), 1 survivors (1024K)
Metaspace       used 145K, committed 384K, reserved 1114112K
~~~

Các con số thay đổi theo JVM và workload. Đọc các cột reserved, committed và used đúng nghĩa; Metaspace được báo riêng vì nó không nằm trong Java heap.

Xem thông tin JVM:

~~~sh
jcmd <pid> VM.info
~~~

Các command diagnostic cần chạy trên cùng máy và bằng cùng effective user/group đã khởi chạy JVM. Nếu không attach được, kiểm tra PID, user và quyền truy cập.

### 9.1. Histogram và heap dump khi cần điều tra sâu

Khi cần tìm class đang chiếm nhiều heap:

~~~sh
jcmd <pid> GC.class_histogram
~~~

Khi cần phân tích object graph và reference:

~~~sh
jcmd <pid> GC.heap_dump filename=heap.hprof
~~~

Đây là các thao tác có tác động cao. Histogram có thể cần thời gian tùy kích thước heap; heap dump có thể yêu cầu Full GC và tạo file lớn. Chỉ chạy khi có mục tiêu điều tra, đủ disk và có thể chấp nhận ảnh hưởng latency.

Mở file `.hprof` bằng một công cụ phân tích heap như Eclipse Memory Analyzer hoặc JDK Mission Control phù hợp với định dạng và phiên bản file.

## 10. Ví dụ thực hành: đo max heap và kiểm tra bằng jcmd

Ví dụ Java sau giữ lại 8 array, mỗi array 4 MiB. Chương trình in giới hạn heap do JVM cung cấp và tổng dung lượng payload được giữ lại. Tham số `--hold` giữ JVM chạy thêm 30 giây để có thể attach bằng `jcmd`.

Tạo file `HeapSizingProbe.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapSizingProbe {
    private static final int MIB = 1024 * 1024;
    private static final List<byte[]> retained = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        Runtime runtime = Runtime.getRuntime();
        System.out.println("maxHeapMiB=" + runtime.maxMemory() / MIB);

        for (int i = 0; i < 8; i++) {
            retained.add(new byte[4 * MIB]);
        }

        System.out.println("retainedMiB=" + (retained.size() * 4));

        if (args.length > 0 && "--hold".equals(args[0])) {
            System.out.println("heap-probe-ready");
            Thread.sleep(30_000);
        }
    }
}
~~~

Biên dịch bằng Java 17 trở lên:

~~~sh
mkdir -p out
javac --release 17 -d out HeapSizingProbe.java
~~~

Chạy với heap ban đầu 32 MiB và tối đa 96 MiB:

~~~sh
java -Xms32m -Xmx96m -cp out HeapSizingProbe
~~~

Stdout chính xác:

~~~text
maxHeapMiB=96
retainedMiB=32
~~~

Kết quả xác nhận `Runtime.maxMemory()` phản ánh giới hạn 96 MiB và chương trình giữ lại 32 MiB payload. Used heap thực tế còn bao gồm object, collection và các cấu trúc phụ của JVM.

Để kiểm tra một JVM đang chạy, thêm `--hold`:

~~~sh
java -Xms32m -Xmx96m -cp out HeapSizingProbe --hold
~~~

Stdout:

~~~text
maxHeapMiB=96
retainedMiB=32
heap-probe-ready
~~~

Mở terminal thứ hai, tìm PID:

~~~sh
jcmd -l
~~~

Xem flag:

~~~sh
jcmd <pid> VM.flags
~~~

Kiểm tra heap:

~~~sh
jcmd <pid> GC.heap_info
~~~

Trong thử nghiệm với JDK 24.0.2, chương trình biên dịch bằng `javac --release 17` và in đúng hai dòng stdout của chế độ chạy bình thường. Ở chế độ `--hold`, `jcmd VM.flags` xác nhận `InitialHeapSize=33554432` và `MaxHeapSize=100663296`; `GC.heap_info` báo G1 heap reserved 96 MiB, committed 55 MiB và used khoảng 42 MiB tại thời điểm đo. Used và committed có thể thay đổi giữa các lần chạy.

Có thể kiểm tra sizing theo phần trăm với lệnh:

~~~sh
java -XX:MaxRAM=512m -XX:InitialRAMPercentage=12.5 -XX:MaxRAMPercentage=50 -XshowSettings:vm -version
~~~

Trong JDK 24.0.2, lệnh này báo max heap 256 MiB; `PrintFlagsFinal` xác nhận initial heap 64 MiB và max heap 256 MiB.

## 11. Dùng GC log để xác nhận heap sizing

Bật unified GC logging:

~~~sh
java -Xms256m -Xmx1536m "-Xlog:gc*:file=gc.log:time,uptime,level,tags" -jar app.jar
~~~

GC log giúp quan sát:

- Collector được JVM chọn.
- Heap occupancy trước/sau từng GC.
- Pause duration và loại GC.
- Heap capacity/committed thay đổi ra sao.
- Full GC có xuất hiện hay không.
- Allocation failure hoặc evacuation failure.
- Các dấu hiệu GC liên tục nhưng thu hồi rất ít memory.

Một dòng log minh họa:

~~~text
[info][gc] GC(12) Pause Young (Normal) 512M->128M(1024M) 18.5ms
~~~

Cách đọc thường gặp:

- `512M`: heap occupancy trước GC.
- `128M`: occupancy sau GC.
- `1024M`: heap capacity tại thời điểm event.
- `18.5ms`: thời gian pause.

Đây là ví dụ minh họa format; nội dung log thực tế thay đổi theo collector và JDK.

Nếu heap thường xuyên gần Xmx, GC không giải phóng đủ object hoặc có nhiều Full GC, hãy kiểm tra live set, allocation rate và khả năng leak. Nếu heap còn nhiều headroom nhưng pause vẫn dài, nguyên nhân có thể liên quan tới cấu hình collector, object graph, humongous allocation hoặc workload chứ không đơn thuần là thiếu Xmx.

## 12. Heap sizing với G1 GC

G1 là collector mặc định của HotSpot trên các cấu hình server-class hiện đại và được thiết kế để cân bằng throughput với pause time tương đối ổn định.

G1 tự điều chỉnh young generation và collection work dựa trên hành vi ứng dụng. Khi sizing bằng G1:

- Bắt đầu với ergonomic defaults.
- Đặt Xmx nếu cần giới hạn heap theo ngân sách.
- Có thể đặt mục tiêu pause bằng `-XX:MaxGCPauseMillis` khi có yêu cầu latency rõ ràng.
- Tránh cố định young generation bằng `-Xmn` hoặc `-XX:NewRatio` nếu chưa có dữ liệu chứng minh cần thiết.
- Đo lại throughput và pause sau mỗi thay đổi.

Ví dụ:

~~~sh
java -Xms512m -Xmx2g -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar app.jar
~~~

`MaxGCPauseMillis=200` là mục tiêu/hint cho collector, không phải cam kết mọi pause đều dưới 200 ms. Mục tiêu pause chặt hơn có thể khiến GC chạy thường xuyên hơn và làm giảm throughput.

Nếu G1 không đạt yêu cầu, hãy xem GC log và tuning guide trước khi thay đổi nhiều flag cùng lúc.

## 13. Phân biệt thiếu heap và memory leak

Hai tình huống này có thể cùng gây `OutOfMemoryError`, nhưng cách xử lý khác nhau.

| Dấu hiệu | Heap quá nhỏ | Memory leak hoặc giữ object quá lâu |
|---|---|---|
| Live set sau GC | Ổn định nhưng gần giới hạn | Tăng dần qua các chu kỳ tương đương |
| GC | Chạy thường xuyên vì headroom ít | Thu hồi ngày càng ít dù GC chạy |
| Heap usage | Dao động quanh mức cao | Đáy sau GC tăng theo thời gian |
| Histogram/heap dump | Object count có thể ổn định | Một số class/collection tăng không ngừng |
| Cách xử lý | Cân nhắc Xmx hoặc giảm allocation/live set | Tìm reference giữ object, sửa lifecycle/cache |

Một ứng dụng có thể vừa có heap quá nhỏ vừa có memory leak. Hãy so sánh nhiều snapshot hoặc recording tại các thời điểm khác nhau với workload tương đương.

## 14. Các loại OutOfMemoryError liên quan tới sizing

| Thông báo | Vùng bộ nhớ / nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| `Java heap space` | Không còn đủ Java heap để cấp phát object | Xem Xmx, live set, allocation rate, histogram và heap dump |
| `GC overhead limit exceeded` | JVM dành phần lớn thời gian cho GC nhưng thu hồi được rất ít memory | Kiểm tra live set, leak, allocation pressure và GC log |
| `Metaspace` | Class metadata vượt giới hạn hoặc classloader giữ class quá lâu | Kiểm tra class loading, classloader và Metaspace |
| `Direct buffer memory` | Không đủ bộ nhớ cho direct buffer ngoài heap | Kiểm tra direct buffer lifecycle và giới hạn direct memory |
| `unable to create native thread` | Thiếu tài nguyên native hoặc vượt giới hạn thread/process | Kiểm tra thread count, stack size và OS/container limits |

Không tăng Xmx để xử lý mọi loại OutOfMemoryError. Ví dụ, `Metaspace` và `Direct buffer memory` nằm ngoài Java heap.

Có thể bật heap dump tự động khi gặp OOME:

~~~sh
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./dumps -Xmx1g -jar app.jar
~~~

Tạo trước thư mục đích, bảo đảm JVM có quyền ghi và đủ dung lượng. Heap dump có thể chứa dữ liệu nhạy cảm; hãy bảo vệ file và xóa theo chính sách lưu trữ.

## 15. Quy trình heap sizing thực tế

1. Xác định memory limit của máy, container và ngân sách dành cho từng JVM.
2. Ước lượng native/non-heap memory và headroom cần giữ lại.
3. Chạy workload đại diện để thu heap usage, live set, allocation rate và GC behavior.
4. Kiểm tra Xms/Xmx hiện tại bằng `jcmd <pid> VM.flags`.
5. Kiểm tra heap committed/used bằng `jcmd <pid> GC.heap_info`.
6. Thu GC log qua peak traffic, batch job và thời gian idle.
7. Chọn Xmx theo live set, burst headroom và giới hạn process/container.
8. Chọn Xms theo startup footprint, độ ổn định của tải và ngân sách memory.
9. Thay đổi một nhóm flag nhỏ, giữ nguyên workload và đo lại.
10. So sánh GC pause, throughput, latency, process RSS và container memory.
11. Theo dõi sau triển khai để phát hiện tải thực tế khác với bài kiểm thử.
12. Điều tra memory leak nếu live set sau GC tăng liên tục.

### Checklist

- [ ] Đã phân biệt Java heap với tổng bộ nhớ process.
- [ ] Đã hiểu used, committed, reserved và max heap.
- [ ] Đã xác định Xms và Xmx hiện tại.
- [ ] Đã kiểm tra MaxRAM và các RAM percentage flags.
- [ ] Đã xác minh JVM có nhận diện giới hạn container hay không.
- [ ] Đã tính ngân sách cho metaspace, thread stacks, direct buffers và native memory.
- [ ] Đã đo live set và allocation rate dưới workload đại diện.
- [ ] Đã thu GC log qua peak load.
- [ ] Đã phân biệt thiếu heap với memory leak.
- [ ] Đã xác nhận GC pause, throughput và latency sau khi thay đổi.
- [ ] Đã có headroom cho biến động tải và process/container overhead.
- [ ] Đã bảo vệ heap dump và diagnostic files.

Heap sizing hiệu quả bắt đầu từ live set và memory budget thực tế. Dùng Xms để điều khiển mức heap ban đầu/tối thiểu, Xmx hoặc RAM percentage để giới hạn heap tối đa, sau đó xác nhận bằng `jcmd`, GC log và workload đại diện. Khi heap đủ chỗ cho object đang sống và các đợt cấp phát mà vẫn chừa RAM cho native memory, JVM có thể duy trì GC behavior, latency và throughput ổn định hơn.

## Tài liệu tham khảo

- [Oracle JDK 24 — The java Command: -Xms, -Xmx and RAM percentage options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Oracle JDK 24 — Ergonomics and heap sizing strategy](https://docs.oracle.com/en/java/javase/24/gctuning/ergonomics.html)
- [Oracle JDK 24 — G1 Garbage Collector and heap sizing](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html)
- [Oracle JDK 24 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-garbage-collector-tuning.html)
- [Oracle JDK 24 — Diagnostic Tools and jcmd](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)