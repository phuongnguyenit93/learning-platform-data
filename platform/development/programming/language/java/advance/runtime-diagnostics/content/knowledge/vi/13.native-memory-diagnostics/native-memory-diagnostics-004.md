# 13.4 Dùng VM.native_memory để đọc báo cáo theo nhóm sử dụng bộ nhớ

## Mục tiêu học tập

Trong một tiến trình Java, `-Xmx` chỉ giới hạn **Java heap**, trong khi JVM còn dùng bộ nhớ cho metaspace, thread stacks, JIT-compiled code, cấu trúc GC và những vùng native khác. Bài này hướng dẫn cách dùng lệnh chẩn đoán **`VM.native_memory`** của `jcmd` để đọc báo cáo **Native Memory Tracking (NMT)** trên **HotSpot JVM**.

Học xong, bạn có thể:

- Bật NMT ở mức `summary` hoặc `detail` ngay từ lúc JVM khởi động, xác định PID và lấy báo cáo an toàn.
- Giải thích chính xác `reserved`, `committed`, `malloc`, `mmap` và cách đọc tổng so với các nhóm sử dụng bộ nhớ.
- Nhận biết các nhóm `Java Heap`, `Class`, `Thread`, `Code`, `GC`, `Compiler`, `Internal` và các nhóm khác mà JVM thực tế hiển thị.
- Dùng `baseline` và `summary.diff` / `detail.diff` để theo dõi sự thay đổi dưới cùng điều kiện tải.
- Nhận diện giới hạn của NMT và kết hợp với số đo heap, thread, metaspace và RSS của hệ điều hành trước khi kết luận memory leak.

**Phạm vi:** các ví dụ lệnh dành cho HotSpot Java 17 trở lên. Tên nhóm, lượng bộ nhớ, câu chữ trong kết quả, khả năng attach và chi tiết phân loại có thể thay đổi theo JDK, hệ điều hành, collector và cấu hình. NMT là tính năng chẩn đoán của HotSpot; không mặc định áp dụng nguyên xi cho mọi JVM khác.

## 1. Vì sao Java heap không phải toàn bộ bộ nhớ tiến trình?

Xét một service chạy với `-Xmx512m`. Con số 512 MiB thường là **giới hạn kích thước Java heap**, không phải giới hạn tuyệt đối cho toàn bộ tiến trình. Ngoài heap, HotSpot cần những vùng bộ nhớ khác:

| Nhóm tiêu biểu | Công dụng thường gặp |
| --- | --- |
| Java Heap | Chỗ lưu phần lớn đối tượng Java, do garbage collector quản lý |
| Class / Metaspace | Metadata của lớp, phương thức và cấu trúc hỗ trợ nạp lớp |
| Thread | Ngăn xếp native và dữ liệu nội bộ liên quan các luồng |
| Code | Bộ nhớ mã máy được JIT biên dịch và cơ sở hạ tầng code cache |
| GC | Các cấu trúc phục vụ bộ thu gom, tùy collector |
| Compiler | Dữ liệu nội bộ của bộ biên dịch JIT |
| Internal, Symbol, Module, Other… | Các hạng mục khác trong HotSpot, tùy phiên bản |

Ngoài những vùng JVM theo dõi, tiến trình còn có thư viện native được nạp, bộ nhớ từ mã JNI hoặc thư viện bên thứ ba, ánh xạ tệp và các cấp phát không thuộc phạm vi NMT. Vì vậy:

~~~text
Java heap usage ≠ NMT committed ≠ process RSS ≠ giới hạn RAM/container
~~~

- **Heap used** là dung lượng các đối tượng/vùng heap đang được tính là đã sử dụng theo công cụ heap, chịu ảnh hưởng thời điểm GC.
- **NMT committed** phản ánh bộ nhớ đã được HotSpot commit/cấp phát trong các hạng mục NMT theo dõi; nó không cho biết chính xác mọi trang thực sự đang nằm trong RAM.
- **RSS / working set** là khái niệm mức trang bộ nhớ cư trú của hệ điều hành; nó còn chịu ảnh hưởng chia sẻ trang, mapped files, thư viện native và những thứ NMT không bao quát.

Một báo cáo NMT tăng có thể chỉ cho thấy JVM đã commit thêm không gian để vận hành; chưa đủ để khẳng định có leak hay rằng lượng RAM thực tế tăng đúng bằng số báo cáo.

## 2. NMT là gì, bật ở đâu và tốn gì?

**Native Memory Tracking** ghi nhận việc HotSpot quản lý các cấp phát bộ nhớ nội bộ của mình, gom chúng theo nhóm (subsystem/category). Đây là cơ chế rất hữu ích khi tiến trình có vấn đề footprint hoặc native out-of-memory nhưng heap Java không giải thích được toàn bộ tình huống.

NMT **mặc định tắt**. Phải bật từ **lúc khởi động JVM**:

~~~sh
# Ít chi tiết hơn, phù hợp khi chủ yếu cần xu hướng theo nhóm:
java -XX:NativeMemoryTracking=summary -Xms128m -Xmx512m -jar app.jar

# Ghi dữ liệu chi tiết hơn về vị trí cấp phát native bên trong VM:
java -XX:NativeMemoryTracking=detail -Xms128m -Xmx512m -jar app.jar
~~~

`app.jar` chỉ là tên JAR minh họa; thay bằng ứng dụng của bạn. Với Spring Boot, VM option phải đứng **trước** `-jar`. Nếu chạy Docker/Kubernetes, thiết lập tùy chọn JVM trong cấu hình thực sự được dùng để tạo tiến trình Java, rồi xác minh trên đúng PID trong container.

Các mức:

| Mức | Thông tin có thể lấy | Khi nào chọn |
| --- | --- | --- |
| `off` | Không có dữ liệu NMT; đây là mặc định | Không cần quan sát NMT |
| `summary` | Tổng và phân bố các nhóm bộ nhớ | Bước đầu khi điều tra tăng footprint |
| `detail` | Các nhóm như summary và thông tin native call site / virtual memory map | Khi summary xác định được nhóm cần truy sâu |

**Không thể khởi động NMT từ trạng thái off bằng `jcmd` cho một JVM đã chạy.** Cũng không thể biến tracking level `summary` thành `detail` chỉ bằng yêu cầu report. Lệnh `VM.native_memory shutdown` tắt tracking cho tiến trình; theo cơ chế HotSpot được tài liệu hóa, không thể khởi động lại bằng `jcmd` sau đó. Muốn đổi mức, hãy khởi động lại JVM với cờ phù hợp.

NMT có overhead về CPU và bộ nhớ: tài liệu Oracle ghi nhận có thể làm hiệu năng giảm cỡ 5–10% trong một số trường hợp. Đây **không phải con số cố định**; benchmark theo workload và thời gian thu thập thực tế. Theo dõi ở mức `detail` có thể tốn thêm chi phí và tạo output lớn. Tránh bật mọi nơi một cách vô điều kiện.

## 3. Tìm đúng tiến trình và gọi `VM.native_memory`

Sử dụng `jcmd` thuộc JDK tương thích với JVM đích. Cần có quyền truy cập tiến trình và cơ chế attach hoạt động. Trong container, PID hiển thị trong container có thể khác PID mà hệ điều hành host nhìn thấy.

~~~sh
# Liệt kê các JVM có thể attach từ môi trường hiện tại.
jcmd -l

# Thay <pid> bằng PID thực tế tìm được.
jcmd <pid> VM.native_memory summary

# Đọc số theo KiB để không mất những nhóm nhỏ do làm tròn:
jcmd <pid> VM.native_memory summary scale=KB

# Dùng MB nếu cần tổng quan gọn:
jcmd <pid> VM.native_memory summary scale=MB
~~~

Nếu `jcmd -l` không thấy ứng dụng, kiểm tra JDK/JRE path, quyền truy cập, user sở hữu process, namespace của container, hạn chế attach (`-XX:+DisableAttachMechanism`) và việc ứng dụng còn chạy hay không. Không cố lấy số từ PID của một process khác.

### 3.1 Ví dụ một phần báo cáo thật

Đo trên một chương trình Java nhỏ với HotSpot **JDK 24**, `-Xms32m -Xmx128m` và `NativeMemoryTracking=summary`, lệnh `summary scale=MB` cho một đoạn output như sau:

~~~text
Native Memory Tracking:

(Omitting categories weighting less than 1MB)

Total: reserved=1575MB, committed=132MB

-                 Java Heap (reserved=128MB, committed=34MB)
-                     Class (reserved=1024MB, committed=0MB)
-                    Thread (reserved=23MB, committed=1MB)
-                      Code (reserved=242MB, committed=7MB)
-                        GC (reserved=75MB, committed=73MB)
~~~

Đây là **trích đoạn minh họa**, không bao gồm tất cả nhóm và không phải footprint tiêu chuẩn của JDK 17/21 hay mọi ứng dụng. Số `Class committed=0MB` ở đây là **làm tròn đơn vị MB**, không có nghĩa JVM không sử dụng byte nào cho metadata lớp. Ở bản report đầy đủ, các nhóm nhỏ vẫn xuất hiện khi dùng `scale=KB`. Không cộng các dòng của trích đoạn rồi mong khớp `Total` vì đã lược bớt nhóm.

Một điểm dễ gây hiểu nhầm: tổng `reserved=1575MB` vượt xa `-Xmx128m` nhưng `committed` chỉ `132MB`. Một vùng địa chỉ ảo dành trước, chẳng hạn compressed class space, có thể lớn dù mức bộ nhớ thực tế được commit còn rất nhỏ.

### 3.2 Đọc `reserved` và `committed`

**Reserved** là không gian địa chỉ ảo JVM dành sẵn cho mục đích tương lai. **Committed** thể hiện phạm vi bộ nhớ JVM đã commit/cấp phát để có thể dùng theo cơ chế tương ứng. Với các vùng ánh xạ, có thể reserve lớn ngay từ đầu và commit dần; committed không đồng nghĩa với RSS hay byte đang chứa dữ liệu có ích.

Ví dụ dòng:

~~~text
Java Heap (reserved=128MB, committed=34MB)
~~~

được đọc như sau: HotSpot dành trước khoảng 128 MiB địa chỉ ảo cho Java heap, trong đó khoảng 34 MiB đã được commit tại thời điểm đo. **Không** được suy ra rằng “34 MiB object Java còn sống” hay “34 MiB trang RAM chắc chắn đang resident”. Để xem tình trạng đối tượng/heap used, hãy dùng bộ đo heap riêng, ví dụ:

~~~sh
jcmd <pid> GC.heap_info
~~~

Tương tự, phần `Class` có thể reserve một vùng địa chỉ ảo lớn cho compressed class space; chỉ số `committed` nhỏ hơn nhiều là bình thường. Nên phân tích xu hướng `committed` dưới điều kiện tải tương đương thay vì báo động chỉ từ `reserved` lớn.

### 3.3 Đọc `malloc`, `mmap`, `arena` và dấu `#`

Trong báo cáo chi tiết của một nhóm có thể có các dòng:

~~~text
-       Sample Category (reserved=4000KB, committed=3000KB)
                       (malloc=1000KB #200)
                       (mmap: reserved=3000KB, committed=2000KB)
~~~

**Đây là số liệu giả định để tập đọc cú pháp**, tên `Sample Category` không phải nhóm chuẩn do JVM phát ra.

- `malloc=1000KB #200`: ví dụ nhóm còn có khoảng 1.000 KiB được cấp phát qua đường malloc mà NMT theo dõi, với bộ đếm 200 allocation blocks theo cách VM thống kê. `#200` **không phải 200 đối tượng Java**.
- `mmap: reserved=3000KB, committed=2000KB`: phần địa chỉ ảo/committed qua cơ chế mapping trong báo cáo của JVM; không đồng nghĩa file mapping hay RSS.
- Một số nhóm có `arena`: bộ nhớ phân phối qua các arena/chunk nội bộ; không thể đọc mỗi chunk như một object Java riêng.
- Tổng của từng nhóm đã bao hàm các dòng con; **không cộng `malloc` và `mmap` lần nữa vào tổng nhóm hoặc Total**. Những phần `Metadata`, `Class space` hoặc phân tích nhỏ hơn nằm dưới `Class` cũng là breakdown, không phải nhóm bổ sung độc lập.

Khi dùng `scale=MB`, số lượng nhỏ có thể bị làm tròn về 0; dùng `scale=KB` cho điều tra chênh lệch nhỏ. Không suy ra số byte chính xác từ con số hiển thị đã bị làm tròn.

## 4. Đọc từng nhóm sử dụng bộ nhớ: dấu hiệu và câu hỏi cần đặt

Tên và số nhóm thay đổi theo JDK. Bảng sau là cách hiểu các hạng mục thường gặp trong báo cáo HotSpot:

| Nhóm | Nội dung điển hình | Khi `committed` tăng, nên kiểm tra |
| --- | --- | --- |
| **Java Heap** | Dung lượng heap JVM reserve/commit cho đối tượng | Heap committed có mở rộng do tải/GC? Bao nhiêu là heap **used** hoặc live set thực? |
| **Class** | Metadata lớp, Metaspace, compressed class space tùy cấu hình | Có nạp class/classloader mới? Class unloading có diễn ra? App tạo proxy/class động? |
| **Thread** | Thread stacks và cấu trúc nội bộ cho luồng | Tổng số thread tăng? Có thread pool không giới hạn, thread bị giữ không kết thúc? |
| **Code** | Code cache, mã máy JIT và các vùng liên quan | JIT đang warmup, nhiều method được biên dịch, code cache tiến đến giới hạn? |
| **GC** | Các cấu trúc do collector dùng | Collector nào đang chạy, heap size và workload có tăng, chính sách GC thay đổi? |
| **Compiler** | Cấu trúc làm việc của JIT compiler | Warmup/biên dịch kéo dài hoặc thay đổi số tác vụ biên dịch? |
| **Internal** | Dữ liệu nội bộ JVM không thuộc nhóm trên | Có thay đổi cấu hình/agent/runtime? Cần `detail` hoặc số đo bổ sung |
| **Symbol** | Các bảng/chuỗi symbol JVM | Class loading, metadata và runtime structure phát triển thế nào? |
| **Native Memory Tracking** | Bộ nhớ tự NMT dùng để theo dõi | Overhead của chính việc bật tracking, đặc biệt khi lên `detail` |
| **Other** | Cấp phát HotSpot được gắn vào nhóm còn lại | Không mặc định kết luận đó là direct buffer/JNI hay leak; cần kiểm tra ngữ cảnh và công cụ khác |

Một số JVM còn hiển thị `Arena Chunk`, `Logging`, `Arguments`, `Module`, `GCCardSet` hoặc nhóm riêng cho tính năng mới. Không có nhóm nào hiện ra cũng **không** chứng minh tính năng tương ứng hoàn toàn không dùng bộ nhớ: có thể số quá nhỏ, bị lược trong `scale=MB`, hoặc được phân loại khác.

### 4.1 `Java Heap`: reserve/commit khác dùng bao nhiêu object

Cấu hình `-Xms`/`-Xmx`, chính sách commit/uncommit và garbage collector quyết định phần NMT `Java Heap`. Khi Java code cấp phát thêm một mảng nhưng vùng heap **đã committed có đủ chỗ**, `committed` có thể **không thay đổi**. NMT không phải profiler cho allocation rate, object count, heap histogram hay retained size.

Nếu mục tiêu là điều tra Java heap leak, đối chiếu `GC.heap_info`, đường post-GC heap used, heap dump hoặc JFR allocation/GC events. Không dùng con số `Java Heap committed` như số byte còn sống.

### 4.2 `Class`: hiểu Compressed Class Space và Metaspace

Một báo cáo có thể reserve khoảng 1 GiB không gian địa chỉ cho class space nhưng chỉ commit vài MiB, tùy `-XX:CompressedClassSpaceSize` và việc sử dụng compressed class pointers. `Class` có thể hiển thị thêm số instance classes, array classes, metadata used/free/waste và class space.

Điều tra `Class committed` tăng kéo dài nên đối chiếu số lớp được nạp, classloader còn sống, class unloading và tình huống framework sinh proxy/code động. Dùng `jcmd <pid> VM.metaspace` khi JVM hỗ trợ để kiểm tra metaspace sâu hơn. Không khẳng định leak chỉ vì số lớp tăng trong quá trình warmup hợp lệ.

### 4.3 `Thread`: số luồng và stack

Báo cáo `Thread` thường cho biết `threads #...` cùng `stack: reserved=..., committed=...`. Số thread càng nhiều có thể khiến tổng **reserved** của stacks tăng mạnh dù committed vẫn thấp; mức stack tùy nền tảng và `-Xss`. `Thread` còn có dữ liệu ngoài stack.

Đối chiếu thread count và thread dump với `jcmd <pid> Thread.print`. Nếu pool liên tục tạo thread, kiểm tra backpressure, pool sizing, thread termination và thread leak; không kết luận từ riêng `Thread reserved`.

### 4.4 `Code`, `GC` và `Compiler`

- **Code** thường thay đổi trong giai đoạn JIT compile/warmup; cần phân biệt code cache đạt trạng thái ổn định với tăng mãi.
- **GC** phụ thuộc collector và heap/config; cấp phát cấu trúc thu gom không có nghĩa Java heap leak.
- **Compiler** có thể biến động khi JVM biên dịch phương thức; mức tăng tạm thời quanh warmup không mặc định bất thường.

Điều tra theo đồng hồ cùng lúc với tải ứng dụng, CPU, GC pause, thay đổi số luồng và cấu hình JVM.

## 5. Kỹ thuật baseline và diff: tìm nhóm tăng qua thời gian

Một ảnh chụp tức thời chỉ cho biết **trạng thái tại thời điểm đó**. Để xem xu hướng, NMT có baseline.

### 5.1 Lấy baseline sau khi ứng dụng đã warmup

~~~sh
# Khi request rate, cache và JIT đã qua giai đoạn khởi động:
jcmd <pid> VM.native_memory baseline

# Sau một khoảng tải đủ đại diện, so với baseline:
jcmd <pid> VM.native_memory summary.diff scale=KB

# Chụp snapshot hiện tại khi cần đối chiếu giá trị tuyệt đối:
jcmd <pid> VM.native_memory summary scale=KB
~~~

`summary.diff` hiển thị giá trị hiện tại kèm phần tăng/giảm so với baseline. Dấu `+` là tăng, `-` là giảm, còn không có delta có thể là bằng 0 hoặc bị làm tròn dưới đơn vị hiển thị. Ví dụ **minh họa giả định**:

~~~text
Total: reserved=640000KB +16000KB, committed=155000KB +12000KB
- Thread (reserved=52000KB +16000KB, committed=5000KB +1000KB)
- Class  (reserved=110000KB, committed=12000KB +500KB)
~~~

Một mức tăng của `Thread` gợi ý cần kiểm tra số thread; tăng của `Class` gợi ý đối chiếu quá trình nạp lớp. Đây là **giả thuyết điều tra**, không phải kết luận leak. Vì `reserved` và `committed` có thể đi theo hướng khác nhau, hãy xem cả hai và cả diễn biến thời gian.

Lặp phép đo ở nhiều mốc, ví dụ sau 5, 10, 30 phút dưới workload tương đương. Đừng lấy baseline quá sớm rồi nhầm giai đoạn class loading/JIT warmup bình thường với leak. Trước khi thay baseline mới, ghi lại báo cáo cần giữ để so sánh.

### 5.2 Khi nào cần `detail.diff`?

Nếu đã khởi động JVM với `-XX:NativeMemoryTracking=detail`, dùng:

~~~sh
jcmd <pid> VM.native_memory detail scale=KB
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory detail.diff scale=KB
~~~

`detail` có thể cung cấp thêm virtual memory map và vị trí gọi cấp phát bên trong **mã native của HotSpot**. Các địa chỉ, symbol và call stack tùy JVM/build/OS; đây **không phải** full Java allocation stack trace và không thể truy mọi `malloc` trong thư viện bên thứ ba.

Nếu JVM khởi động ở mức `summary`, chạy `detail` hoặc `detail.diff` sẽ không tự “nâng cấp” dữ liệu. Trên một HotSpot JDK 24 được kiểm tra, `VM.native_memory detail` trả:

~~~text
Detail tracking is not enabled
~~~

Muốn có detail, khởi động lại với cờ `NativeMemoryTracking=detail`. Dùng mức thấp nhất đủ trả lời câu hỏi, rồi mới nâng mức ở một lần chạy có kiểm soát.

## 6. Thực hành Java 17+: tạo báo cáo cho một tiến trình có thể điều khiển

Ví dụ sau giữ JVM đang chạy để bạn quan sát bằng terminal thứ hai, sau đó cấp phát thêm 16 mảng Java mỗi mảng có payload 1 MiB. Mục tiêu là **quan sát NMT trước/sau dưới cùng JVM**, đồng thời thấy vì sao số object cấp phát **không bắt buộc** trùng với thay đổi `Java Heap committed`.

Lưu tệp **NativeMemoryDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public final class NativeMemoryDemo {
    private static volatile byte[][] retained;

    public static void main(String[] args) throws Exception {
        BufferedReader console = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        System.out.println("READY: press Enter to allocate");
        console.readLine();

        byte[][] chunks = new byte[16][];
        for (int i = 0; i < chunks.length; i++) {
            chunks[i] = new byte[1_048_576];
        }
        retained = chunks;

        System.out.println("RETAINED: 16 arrays, 16 MiB payload");
        System.out.println("Press Enter to exit");
        console.readLine();
    }
}
~~~

**Terminal A:** biên dịch và chạy (giữ terminal mở, chưa nhấn Enter):

~~~sh
javac --release 17 NativeMemoryDemo.java
java -Xms32m -Xmx128m -XX:NativeMemoryTracking=summary NativeMemoryDemo
~~~

Stdout ban đầu chính xác là:

~~~text
READY: press Enter to allocate
~~~

**Terminal B:** xác định PID thật của tiến trình `NativeMemoryDemo` rồi lấy baseline:

~~~sh
jcmd -l
jcmd <pid> VM.native_memory summary scale=KB
jcmd <pid> VM.native_memory baseline
~~~

Quay lại **Terminal A**, nhấn Enter **một lần** để yêu cầu cấp phát. Chương trình in thêm:

~~~text
RETAINED: 16 arrays, 16 MiB payload
Press Enter to exit
~~~

Trong khi Terminal A vẫn giữ process sống, chạy ở **Terminal B**:

~~~sh
jcmd <pid> VM.native_memory summary.diff scale=KB
jcmd <pid> VM.native_memory summary scale=MB
jcmd <pid> GC.heap_info
~~~

Bây giờ so sánh. 16 MiB là **payload** của các mảng; thực tế object còn có header/alignment và chi phí các cấu trúc khác. Trường static `retained` giữ các mảng reachable. Nhưng không được kỳ vọng `summary.diff` bắt buộc có `Java Heap committed +16384KB`: JVM có thể đã commit đủ chỗ trước lần cấp phát, hoặc commit thêm một lượng khác tùy collector. `GC.heap_info` cung cấp góc nhìn heap khác với NMT.

Sau khi quan sát xong, nhấn Enter lần nữa ở **Terminal A** để kết thúc bình thường. Ví dụ trên được biên dịch với `javac --release 17` và chạy kiểm tra trên HotSpot; ba dòng do chương trình in ra đúng như mô tả. Kết quả `jcmd` sẽ thay đổi theo JVM và máy.

### 6.1 Nếu muốn thử detail

Hãy khởi động một lần mới, với cùng chương trình nhưng thay tùy chọn JVM:

~~~sh
java -Xms32m -Xmx128m -XX:NativeMemoryTracking=detail NativeMemoryDemo
~~~

Trong lúc chương trình chờ nhập ở Terminal A:

~~~sh
jcmd -l
jcmd <pid> VM.native_memory detail scale=KB
jcmd <pid> VM.native_memory baseline
~~~

Sau khi nhấn Enter cấp phát ở Terminal A:

~~~sh
jcmd <pid> VM.native_memory detail.diff scale=KB
~~~

Không so trực tiếp chi phí chạy giữa hai lần này mà thiếu workload giống nhau: `detail` có overhead khác `summary`, quá trình JIT/GC cũng thay đổi từng run.

## 7. Đọc NMT khi có sự cố: kết hợp với nguồn bằng chứng nào?

| Triệu chứng | NMT có thể giúp gì? | Cần kiểm tra thêm |
| --- | --- | --- |
| RSS/working set tăng, Java heap used sau GC ổn định | Xem nhóm HotSpot committed nào tăng, đặc biệt Thread/Class/Code/GC | Dữ liệu RSS theo OS/container, JNI và thư viện native, direct buffers, mapped files |
| NMT `Class committed` tăng liên tục | Khoanh vùng metadata/class space | Số classloader/classes, `VM.metaspace`, class unloading và vòng đời tạo proxy |
| NMT `Thread reserved` tăng mạnh | Xem `threads #...`, stack reservation/commit | Thread dump, thread pool metrics, `-Xss`, resource limits |
| NMT `Java Heap committed` cao | Kiểm tra heap reservation/commitment thực tế | Heap used/live set, GC logs, heap dump, object histogram |
| NMT `GC committed` hoặc `Code committed` tăng | Xác định nhóm subsystem chịu trách nhiệm | Collector/version/config, workload, JIT compilation/code cache |
| NMT ổn định nhưng RSS vẫn tăng | NMT không giải thích hết thay đổi; có thể do phân bổ ngoài phạm vi hoặc hành vi resident pages | OS memory maps/working set, native profiler, JNI/direct/mapped memory, cgroup stats |

**Không có phép suy luận “RSS − NMT committed = chính xác native memory bị leak”.** Hai hệ đo dùng định nghĩa khác nhau, một số vùng có thể được tính khác, và mức cư trú vật lý không khớp số byte committed. Hãy tìm một cơ chế giữ bộ nhớ cụ thể và kiểm chứng nó bằng nguồn phù hợp.

### Công cụ bổ sung và câu hỏi tương ứng

- `jcmd <pid> GC.heap_info`: heap hiện trạng; GC logs và các heap metrics cho xu hướng heap used/committed.
- `jcmd <pid> VM.metaspace`: kiểm tra metaspace khi lệnh được JVM hỗ trợ.
- `jcmd <pid> Thread.print` và thread metrics: số luồng, trạng thái luồng và nghi vấn thread không kết thúc.
- JFR/JMC hoặc Java heap profiler: phân tích Java allocation/GC, thời gian pause và stack cấp phát Java; chúng không thay thế NMT native subsystem breakdown.
- `BufferPoolMXBean` / JMX buffer pool: thêm góc nhìn về các direct/mapped buffer do API Java quản lý; số này không tự bao trùm mọi cấp phát JNI.
- Các công cụ bộ nhớ của hệ điều hành (Windows Process Explorer/Performance Monitor, Linux `/proc/<pid>/smaps_rollup` và `pmap`, container memory metrics): quan sát RSS, mapping, shared/private memory ngoài phạm vi NMT.

Một lỗi như `OutOfMemoryError: Java heap space`, `OutOfMemoryError: Metaspace`, `unable to create native thread` hoặc tiến trình bị OS/container OOM kill có cơ chế khác nhau. Cần ghép thông điệp lỗi, dấu thời gian và số liệu đúng vùng bộ nhớ. Chỉ tăng `-Xmx` không giải quyết mọi sự cố native memory.

## 8. Quy trình điều tra footprint bất thường bằng NMT

1. **Lấy bối cảnh:** ghi JDK vendor/version, collector, `-Xms/-Xmx`, `-Xss`, giới hạn container và số luồng hiện có. Xác nhận JVM là HotSpot hỗ trợ NMT.
2. **Bật NMT cho lần khởi động có kế hoạch:** bắt đầu `summary` khi cần biết nhóm nào tăng; dùng `detail` nếu cần native allocation call sites và chấp nhận overhead.
3. **Warmup và đặt baseline:** đợi ứng dụng đạt trạng thái tải đại diện; ghi load rate, latency, thread count, heap used/committed và RSS cùng timestamp.
4. **Thu nhiều diff:** lấy `summary.diff scale=KB` ở các mốc phù hợp; lưu cả giá trị hiện tại và delta so với baseline. Không dựa vào một snapshot duy nhất.
5. **Khoanh vùng hạng mục:** nếu `Thread` tăng, kiểm số luồng; nếu `Class` tăng, kiểm classloader/metaspace; nếu `Java Heap` tăng, đối chiếu GC/heap; nếu `Other/Internal` tăng, dùng detail hoặc profiler khác để kiểm chứng.
6. **Kiểm tra vùng NMT không bao quát:** nếu OS memory tăng nhưng báo cáo NMT ổn định, điều tra JNI và các native library, direct/mapped buffers, file mappings và chi phí resident pages.
7. **Thử thay đổi và đo lại:** dùng tải tương đương, đối chiếu committed, RSS, latency và throughput. Kết luận chỉ khi tìm thấy nguyên nhân giữ/cấp phát bộ nhớ và sự thay đổi số liệu phù hợp giả thuyết.

**Chú ý an toàn vận hành:** việc attach có thể bị giới hạn; lệnh `VM.native_memory` có tác động chẩn đoán, và mức `detail` có thể tạo log rất dài. Với production, lựa chọn cửa sổ đo, mức tracking và cách thu output theo quy trình vận hành đã được phê duyệt; không khởi động lại dịch vụ hoặc bật NMT diện rộng chỉ để lấy một ví dụ.

## 9. Các hiểu nhầm phổ biến

1. **“`reserved=2GB` nghĩa là tiến trình đang ăn 2GB RAM.”** Sai: reserved là không gian địa chỉ ảo; cần xem committed và RSS trong ngữ cảnh.
2. **“`committed=500MB` chính là RSS.”** Sai: NMT committed không phải metric resident pages của OS, và NMT không phủ toàn bộ process.
3. **“`Java Heap committed=200MB` nghĩa là object Java đang chiếm 200MB.”** Sai: phần đã commit có thể chứa không gian chưa dùng; cần xem used/live set bằng công cụ heap.
4. **“`Class reserved=1GB` chứng tỏ metaspace leak.”** Sai: compressed class space có thể reserve lớn từ đầu và commit rất ít.
5. **“`malloc #5000` nghĩa là có 5000 đối tượng Java.”** Sai: đó là bộ đếm cấp phát ở tầng native/NMT theo ngữ cảnh dòng báo cáo.
6. **“Có thể bật `detail` bằng `jcmd` khi JVM đã chạy với NMT off.”** Sai: phải bật tracking level phù hợp ngay khi khởi động JVM.
7. **“`summary.diff` có dấu `+` chắc chắn là leak.”** Sai: warmup, tải tăng, cache hợp lệ, thread/class loading và chuyển trạng thái heap đều có thể làm số tăng.
8. **“NMT chắc chắn thấy mọi malloc từ JNI và thư viện ngoài JVM.”** Sai: NMT có giới hạn phạm vi, cần công cụ native/OS để quan sát phần bên ngoài HotSpot.
9. **“Một nhóm nhỏ hiện `0MB` nghĩa là hoàn toàn không dùng bộ nhớ.”** Sai: đổi sang `scale=KB`; output đã làm tròn hoặc lược các nhóm nhỏ.
10. **“Cứ tăng `-Xmx` là hết native OOM.”** Sai: tăng heap thậm chí còn cạnh tranh thêm ngân sách bộ nhớ của container/host với vùng native.

## 10. Bài tập vận dụng có lời giải

**Tình huống A — đọc một dòng.** Báo cáo ghi `Java Heap (reserved=1024MB, committed=256MB)`. JVM đang dùng 256 MiB object sống?

**Giải:** Không thể kết luận. JVM reserve 1024 MiB không gian địa chỉ và commit khoảng 256 MiB cho heap. Cần metric heap used/live set, GC observations để biết còn bao nhiêu đối tượng sống.

**Tình huống B — nghi vấn thread.** Ở workload ổn định, `Thread reserved` tăng 400 MiB trong 30 phút, `Thread (threads #...)` cũng tăng đều. Việc cần làm tiếp?

**Giải:** Điều tra số lượng và vòng đời thread, `Thread.print`, thread pool, giới hạn concurrency và tài nguyên được giữ. Chưa thể khẳng định leak chỉ từ reserved; trước hết xác định thread nào không kết thúc và tại sao.

**Tình huống C — RSS tăng nhưng NMT không tăng.** RSS tăng 600 MiB; `summary.diff` gần như 0 ở mọi nhóm. Có thể khẳng định JVM không phải nguyên nhân?

**Giải:** Chưa. NMT chỉ theo dõi những phần HotSpot hỗ trợ; một lượng cấp phát JNI/thư viện bên thứ ba hoặc resident pages/mapping có thể nằm ngoài phạm vi. Phải dùng số đo OS, profiler native và thông tin về direct/mapped memory để tìm nguồn tăng.

**Tình huống D — chọn tracking level.** Một lần chạy với `NativeMemoryTracking=summary`, `jcmd <pid> VM.native_memory detail` báo tracking detail chưa bật. Cách xử lý?

**Giải:** Khởi động lại JVM với `-XX:NativeMemoryTracking=detail` cho lần quan sát tiếp theo; sau warmup mới lấy baseline rồi `detail.diff`. NMT không cho bật/nâng mức detail động bằng `jcmd`.

**Tình huống E — khác biệt thời gian.** Sau khi khởi động 20 giây, `Class committed` và `Code committed` tăng; sau 10 phút cả hai ổn định. Có phải leak?

**Giải:** Không có bằng chứng leak từ quan sát này. Class loading và JIT warmup thường làm committed tăng đầu đời tiến trình rồi đạt trạng thái ổn định. Đặt baseline sau warmup, theo dõi tiếp dưới workload tương đương và đối chiếu hiệu năng thực.

## 11. Ghi nhớ thao tác

~~~sh
# Bật từ khi tạo process:
java -XX:NativeMemoryTracking=summary -jar app.jar

# Đọc trạng thái:
jcmd -l
jcmd <pid> VM.native_memory summary scale=KB

# Đo tăng/giảm:
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff scale=KB

# Nếu JVM đã khởi động với NativeMemoryTracking=detail:
jcmd <pid> VM.native_memory detail scale=KB
jcmd <pid> VM.native_memory detail.diff scale=KB
~~~

**Cách đọc đúng:** bắt đầu từ **Total reserved/committed**, xem các **nhóm cấp cao nhất**, dùng dòng con `malloc/mmap/arena` để hiểu cơ chế, lấy **baseline/diff** để theo dõi xu hướng, rồi xác minh bằng heap/thread/metaspace/OS metrics. Mỗi dấu hiệu cần một giả thuyết có thể kiểm chứng. NMT mạnh nhất ở câu hỏi **“HotSpot đang reserve/commit bộ nhớ vào nhóm nào và nhóm nào thay đổi?”**, chứ không tự trả lời toàn bộ câu hỏi “tại sao RSS tăng?” hoặc “đối tượng Java nào đang leak?”.

### Tài liệu tham khảo

- Oracle, *Java 21 Native Memory Tracking*: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
- Oracle, *Java 21 Diagnostic Tools – Native Memory Tracking*: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle, *The jcmd Command*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- OpenJDK / Java troubleshooting, *Troubleshooting Memory Leaks*: https://ops.java/troubleshooting/articles/memory-leaks/
