# 1.2 Quan hệ giữa ứng dụng, JVM, JDK, hệ điều hành và tài nguyên máy

Khi một dịch vụ Java chậm, treo, tiêu thụ nhiều bộ nhớ hoặc bị dừng đột ngột, dấu hiệu nhìn thấy ở ứng dụng có thể bắt nguồn từ một lớp khác. Muốn chẩn đoán đúng, cần hiểu ứng dụng đang chạy **bên trong một JVM**, JVM là thành phần thực thi của một **tiến trình hệ điều hành**, còn tiến trình đó cạnh tranh hoặc bị giới hạn bởi **CPU, bộ nhớ, đĩa, mạng và các giới hạn tài nguyên**. **JDK** cung cấp bộ công cụ để xây dựng, khởi chạy và quan sát hệ thống ấy.

Mục tiêu của bài: phân biệt trách nhiệm từng lớp; lần theo đường đi từ mã Java đến tài nguyên máy; giải thích vì sao số liệu ở các lớp không nhất thiết bằng nhau; và biết phải kiểm tra lớp nào trước khi quy kết nguyên nhân sự cố.

## 1. Mô hình các lớp và chiều phụ thuộc

```text
Yêu cầu bên ngoài / người dùng / hệ thống khác
                  |
                  v
ỨNG DỤNG JAVA: mã nghiệp vụ, framework, thư viện, pool, hàng đợi
                  |
       chạy bên trong tiến trình chứa
                  v
JVM: class loading, interpreter/JIT, heap/GC,
     runtime threads, JNI, quản lý vùng nhớ của JVM
                  |
         sử dụng dịch vụ hệ thống
                  v
HỆ ĐIỀU HÀNH: lập lịch CPU, virtual memory, threads,
              files, sockets, I/O, quyền và giới hạn
                  |
      sử dụng hoặc phân phối tài nguyên
                  v
MÁY THẬT / MÁY ẢO / CONTAINER: CPU, RAM, lưu trữ, mạng,
                               quota và tài nguyên chia sẻ

JDK: javac, java, jcmd, jfr, jstack, jmap, ...
  ├─ chứa runtime cần để chạy ứng dụng (có JVM)
  └─ cung cấp công cụ đứng ngoài tiến trình để biên dịch,
     khởi chạy, thu thập và phân tích bằng chứng.
```

Sơ đồ mô tả **phụ thuộc khi chạy**, không phải mỗi khối đều là một tiến trình riêng. Trong trường hợp phổ biến, lệnh `java` khởi tạo một tiến trình hệ điều hành chứa JVM và ứng dụng. JVM cũng có mã native và thư viện native chạy trong cùng tiến trình. Ứng dụng có thể tương tác với hệ điều hành qua Java API hoặc mã native/JNI. Phần lớn công cụ JDK như `jcmd` chạy dưới dạng **tiến trình công cụ riêng**, kết nối tới JVM đích nếu điều kiện quyền và khả năng attach cho phép.

| Lớp | Sở hữu hoặc quyết định điều gì? | Bằng chứng chẩn đoán tiêu biểu |
| --- | --- | --- |
| Ứng dụng | Luồng yêu cầu, thuật toán, kết nối DB, thread pool, cache, retry, timeout, khóa ứng dụng | Log/tracing, latency, error rate, số yêu cầu đang chờ, kích thước pool |
| JVM | Nạp lớp, thực thi bytecode/mã JIT, heap, GC, metaspace, JIT code cache, nhiều loại thread | GC log, JFR, thread dump, thông số heap, JVM flags |
| JDK/toolchain | Trình biên dịch, launcher, thư viện/runtime đi kèm, công cụ quan sát | `java -version`, `javac -version`, `jcmd`; phiên bản JDK chạy thực tế |
| Hệ điều hành | Tiến trình/PID, lập lịch thread, bộ nhớ ảo, file descriptor, socket, filesystem, permission | CPU theo PID/TID, RSS, I/O, giới hạn mở file, kernel log |
| Máy/VM/container | Số lõi và RAM thực khả dụng, tài nguyên chia sẻ, quota CPU, giới hạn bộ nhớ | CPU throttling, memory pressure, cgroup limits, I/O latency, host metrics |

**Quy tắc suy luận:** chỉ nhìn thấy hiện tượng ở lớp A không đủ để kết luận nguyên nhân thuộc A. Ví dụ, HTTP timeout có thể do khóa ứng dụng, GC pause, CPU bị throttling, truy vấn DB chậm hoặc mạng mất kết nối.

## 2. Từ mã nguồn đến tiến trình đang chạy: JDK và JVM khác nhau thế nào?

Luồng thông thường:

1. `javac` trong JDK biên dịch tệp `.java` thành bytecode `.class` (hoặc qua công cụ build tạo JAR).
2. Lệnh `java` chọn runtime, tạo tiến trình và khởi động JVM; class loader nạp các class cần thiết.
3. JVM xác minh, liên kết, khởi tạo lớp theo nhu cầu; thực thi bytecode bằng interpreter và có thể biên dịch các đoạn nóng thành mã máy qua JIT. Không phải mọi phương thức đều luôn được JIT.
4. Khi chạy, JVM/ứng dụng yêu cầu hệ điều hành cấp CPU, trang nhớ, thread, file, socket và I/O. Hệ điều hành phân phối các yêu cầu đó trên phần cứng hoặc hạ tầng ảo hóa.
5. JDK tools có thể giúp quan sát tiến trình đang chạy. Chúng không tự động sửa lỗi nghiệp vụ hay thay thế metric ứng dụng.

**Phân biệt quan trọng:**

- **JVM** là máy ảo thực thi Java bytecode; HotSpot là một triển khai thông dụng. JVM không đồng nghĩa toàn bộ JDK.
- **JDK** là bộ phát triển chứa công cụ biên dịch và một runtime phù hợp để chạy chương trình. Không nhất thiết cần `javac` trên máy production; image runtime tối giản có thể không có `jcmd` hay `javac`.
- **JRE** là cách gọi môi trường chạy Java; lịch sử có bản phân phối JRE độc lập, nhưng khi chẩn đoán hiện đại hãy kiểm tra **runtime/JDK thực tế mà tiến trình đang dùng**, không suy diễn từ tên thư mục hay `JAVA_HOME`.
- Hai máy có cùng mã ứng dụng nhưng khác phiên bản JVM, cấu hình JVM, hệ điều hành hoặc quota tài nguyên có thể có hành vi hiệu năng khác nhau. Nếu bytecode được biên dịch cho phiên bản Java mới hơn runtime đích hỗ trợ, có thể gặp `UnsupportedClassVersionError` khi nạp class.

Lệnh `java -version` trong shell cho biết **lệnh `java` mà shell tìm thấy**, có thể khác runtime của tiến trình dịch vụ đã khởi động trước đó. Khi điều tra, đối chiếu đường dẫn thực thi, command line, môi trường và PID cụ thể; không dùng kết quả một terminal làm bằng chứng chắc chắn cho mọi JVM trên máy.

## 3. Tài nguyên đi qua các lớp như thế nào?

### 3.1 CPU: công việc của ứng dụng, thread JVM và lịch chạy của OS

Ứng dụng tạo công việc; JVM thực thi mã Java, GC và JIT; hệ điều hành lên lịch các thread lên CPU. Vì thế CPU cao của tiến trình Java có thể đến từ:

- Vòng lặp/tính toán nghiệp vụ, parsing/serialization, mã thư viện hoặc lock contention kèm spin.
- GC hoặc JIT compiler của JVM, bên cạnh thread ứng dụng.
- Số thread runnable cao trong khi CPU quota hoặc số CPU thực cấp thấp.

**Platform thread** Java thường tương ứng với một native OS thread; bộ lập lịch OS quyết định khi nào thread đó được chạy. **Virtual thread** (Java 21+) không ánh xạ 1:1 tới OS thread: nhiều virtual thread được JVM lên lịch trên một tập carrier platform threads. Không suy ra số native threads từ số virtual threads.

`Runtime.getRuntime().availableProcessors()` phản ánh số bộ xử lý mà JVM coi là khả dụng cho tiến trình, có thể bị ảnh hưởng bởi CPU affinity, cgroup/container quota hoặc `-XX:ActiveProcessorCount`; không mặc nhiên bằng tổng số lõi của host. Công cụ báo “100% CPU” cũng cần ngữ cảnh: đó có thể là một lõi, một tiến trình hoặc phần trăm của quota tùy cách công cụ quy đổi.

Với latency tăng, cần xem đồng thời: CPU theo tiến trình/thread, số CPU được phép dùng, CPU throttling, GC/JIT activity và thời gian chờ I/O. Một thread ở trạng thái `RUNNABLE` trong thread dump Java không chứng minh nó đang chiếm trọn một lõi CPU ở đúng thời điểm lấy mẫu.

### 3.2 Bộ nhớ: heap chỉ là một phần của tiến trình

Không đồng nhất `-Xmx` với “RAM tối đa của ứng dụng”. Những vùng đáng chú ý gồm:

| Khái niệm | Ý nghĩa | Cách hiểu khi chẩn đoán |
| --- | --- | --- |
| Java heap | Nơi lưu phần lớn object Java; chịu quản lý của GC | `-Xmx` là giới hạn heap tối đa, không phải tổng RAM tiến trình |
| Metaspace | Metadata của lớp trong native memory | Có thể tăng do nạp lớp/class loader; không thuộc heap |
| Code cache | Mã máy do JIT biên dịch và metadata liên quan | Có tiêu thụ bộ nhớ ngoài heap |
| Thread stacks | Stack native cho platform threads, theo cấu hình/runtime | Nhiều platform threads có thể làm tăng nhu cầu native memory |
| Direct/native memory | Ví dụ direct buffers, JNI/native libraries, native allocations | Có thể gây áp lực bộ nhớ dù heap còn chỗ |
| RSS của tiến trình | Các trang bộ nhớ hiện đang cư trú trong RAM theo cách OS hạch toán | Không đồng nghĩa heap used, cũng không đồng nghĩa tổng bộ nhớ đã reserve |
| Bộ nhớ container/host | Giới hạn/quota và phần bộ nhớ hệ thống hạch toán | Có thể gồm các thành phần như page cache; cách hạch toán tùy OS/cgroup |

Các đại lượng dễ bị nhầm:

- **Used heap**: dung lượng đối tượng/không gian heap đang sử dụng theo cách metric JVM đo tại thời điểm lấy mẫu.
- **Committed heap**: phần dung lượng heap JVM đã cam kết có thể dùng từ OS; có thể lớn hơn used.
- **Max heap**: giới hạn tối đa JVM dự định cho heap; không phải lượng RAM đang chiếm thực tế.
- **Reserved virtual address space**: không có nghĩa toàn bộ số byte đó đang ở RAM.
- **RSS**: metric ở tầng OS cho các trang resident; có thể gồm vùng mapping/shared và không thể suy ra bằng phép cộng giản đơn mọi số trong JVM.

Ví dụ: container giới hạn 512 MiB, JVM đặt `-Xmx400m`. Khi heap, metaspace, code cache, native buffers, thread stacks và bộ nhớ hệ thống cùng tăng, container **vẫn có thể vượt giới hạn** và tiến trình bị kill dù heap chưa dùng hết 400 MiB. Đây là lý do phải xem cả JVM heap **và** tổng memory usage / giới hạn container.

Cần tách ba trường hợp:

1. `OutOfMemoryError: Java heap space`: JVM không cấp được yêu cầu trên heap trong giới hạn/cơ chế GC hiện tại; điều tra object retention, allocation rate, heap sizing.
2. Lỗi native resource (chẳng hạn `OutOfMemoryError: unable to create native thread` hoặc lỗi cấp phát direct buffer): điều tra native memory, thread count, giới hạn OS; không mặc định tăng `-Xmx`.
3. Tiến trình bị OS/container kết thúc bằng `SIGKILL`: JVM có thể không kịp sinh Java exception hay heap dump. Exit code 137 trong nhiều môi trường thường biểu thị SIGKILL nhưng **không tự chứng minh OOM kill**; cần đối chiếu kernel/cgroup/container event.

### 3.3 File, socket, network và I/O

Java `Files`, `Socket`, JDBC driver, NIO selector hoặc thư viện logging cuối cùng vẫn phụ thuộc tài nguyên OS và hệ thống bên ngoài. Mỗi kết nối hoặc tệp mở có thể tiêu thụ file descriptor/handle và buffer, trong khi độ trễ I/O chịu ảnh hưởng đĩa, filesystem, thiết bị mạng, DNS, server đích và quota.

Khi gặp “Too many open files”, hãy kiểm tra số descriptor đang dùng so với soft/hard limit của **đúng tiến trình**, cùng lifecycle đóng resource. Khi kết nối DB cạn, phân biệt pool ứng dụng bị dùng hết với số socket OS, cổng mạng, độ trễ server DB và lỗi timeout. “Java treo” có thể chỉ là các thread đang đợi syscall hoặc phản hồi từ dịch vụ khác.

### 3.4 Container và máy chủ: nhìn đúng phạm vi

Container **chia sẻ kernel** với host nhưng có thể dùng namespace và cgroup để cô lập định danh tiến trình và giới hạn tài nguyên. Vì vậy:

- PID nhìn bên trong container có thể khác PID nhìn từ host. Luôn biết lệnh đo đang chạy ở namespace nào.
- Chỉ số CPU/RAM của host và container không hoán đổi trực tiếp. Một host còn RAM không bảo đảm container chưa tới `memory.max`.
- Trên Linux cgroup v2, `memory.max` biểu diễn memory limit (chuỗi `max` nghĩa là không đặt giới hạn ở tầng file đó), `memory.current` là mức sử dụng được hạch toán, `memory.events` cho biết một số sự kiện memory pressure/OOM; `cpu.max` mô tả quota/period. Đường dẫn và cơ chế có thể khác ở cgroup v1, runtime hoặc hệ điều hành khác.
- Nhiều bản HotSpot hiện đại nhận biết giới hạn container, nhưng phải xác minh JVM version, flags và môi trường thực tế. Cấu hình cố định hoặc flags có thể làm kết quả khác dự tính.

Thứ tự kiểm tra hợp lý: **tiến trình cụ thể → container/VM của tiến trình → host → hệ thống phụ thuộc**. Không gán nguyên nhân cho host nếu chỉ thấy số liệu của container, và ngược lại.

## 4. Thực hành quan sát trên một chương trình Java

Ví dụ sau chạy độc lập với Java 17+, chỉ **đọc các chỉ số của JVM/tiến trình hiện tại**; không stress CPU hay cố tình gây tràn bộ nhớ. Lưu vào tệp `RuntimeLayersDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;

public class RuntimeLayersDemo {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();
        MemoryUsage heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("availableProcessors=" + runtime.availableProcessors());
        System.out.println("heap.used.bytes=" + heap.getUsed());
        System.out.println("heap.committed.bytes=" + heap.getCommitted());
        System.out.println("heap.max.bytes=" + heap.getMax());
        System.out.println("live.java.threads=" + threads.getThreadCount());
    }
}
```

Biên dịch và chạy:

```bash
javac RuntimeLayersDemo.java
java -Xmx256m RuntimeLayersDemo
```

Chương trình in ra tám dòng bắt đầu bằng `pid=`, `java.version=`, `os.name=`, `availableProcessors=`, `heap.used.bytes=`, `heap.committed.bytes=`, `heap.max.bytes=` và `live.java.threads=`. **Giá trị chính xác phụ thuộc máy và JVM**, nên không gán một stdout cố định. Với HotSpot thông thường, `heap.max.bytes` phản ánh heap max do JVM quyết định với tùy chọn `-Xmx256m`; giá trị có thể không bằng chính xác một con số thập phân “256 MB” mà người đọc tự giả định. Giá trị `heap.max.bytes` bằng `-1`, nếu xuất hiện với một implementation/kiểu pool tương ứng, nghĩa là maximum không được xác định.

Giải thích kết quả:

- `pid` là định danh tiến trình theo cách runtime nhìn thấy. Trong container, đối chiếu namespace khi so với công cụ host.
- `java.version` cho biết runtime **đang thực thi chính chương trình**, hữu ích hơn khi chỉ đọc phiên bản `java` của shell khác.
- `availableProcessors` không là phép đo tải CPU thực tế; nó là thông tin JVM dùng để quyết định tài nguyên xử lý khả dụng.
- Ba giá trị heap cung cấp góc nhìn JVM về heap; không đo tổng native memory hoặc RSS.
- `ThreadMXBean.getThreadCount()` phản ánh số live Java platform threads được MXBean theo dõi; không thay thế phép đếm mọi OS thread hay số virtual thread.

Để đối chiếu một JVM đang chạy lâu hơn, nên quan sát một service thật qua nhiều mẫu theo thời gian thay vì một lệnh chạy quá nhanh để attach công cụ. Mẫu số chỉ có ý nghĩa khi ghi kèm thời điểm, PID, phiên bản JVM và giới hạn tài nguyên tương ứng.

## 5. Công cụ của JDK và hệ điều hành bổ sung cho nhau

Ví dụ trên Linux/HotSpot, thay `PID` bằng PID của **đúng tiến trình**; các lệnh phụ thuộc quyền, khả năng attach và môi trường. Không chạy tất cả lệnh như một “bài thuốc” khi chưa biết câu hỏi cần trả lời.

| Câu hỏi | Công cụ JVM/JDK | Công cụ OS / container |
| --- | --- | --- |
| Đúng Java process và tham số khởi động? | `jcmd -l`; `jcmd PID VM.command_line`; `jcmd PID VM.flags` | `ps -p PID -o pid,ppid,args`; kiểm tra executable/container |
| Heap đang ra sao? | `jcmd PID GC.heap_info`; JMX/MXBeans, GC log | RSS và memory limit để đối chiếu |
| Thread nào chờ/chạy? | `jcmd PID Thread.print`; JFR | `top -H -p PID` hoặc `ps -L` để nhìn native thread |
| Native memory chiếm ở đâu? | `jcmd PID VM.native_memory summary` **chỉ hữu dụng khi bật NMT từ khi khởi động** | `/proc/PID/status`, `/proc/PID/smaps_rollup` khi được phép |
| CPU cao hay bị giới hạn? | JFR CPU samples, GC/JIT events | CPU theo PID/TID, cgroup `cpu.max` và throttling counters |
| Thiếu file descriptor, I/O nghẽn? | Log ứng dụng, stack trace, pool metric | `/proc/PID/fd`, `lsof -p PID`, `ss`, disk/network metrics |

Ví dụ lệnh điều tra ban đầu:

```bash
java -version
jcmd -l
jcmd PID VM.command_line
jcmd PID VM.flags
jcmd PID GC.heap_info
jcmd PID Thread.print
ps -p PID -o pid,ppid,%cpu,%mem,rss,nlwp,args
```

**Giới hạn khi dùng công cụ:** `jcmd` thường cần phù hợp phiên bản/quyền OS user và cơ chế attach; runtime image tối giản hoặc tiến trình trong container khác có thể không có hoặc không cho attach. NMT (`-XX:NativeMemoryTracking=summary` hoặc `detail` với HotSpot hỗ trợ) tạo overhead và phải bật khi khởi động để nhận thống kê tương ứng. Đừng mô tả “NMT chưa bật” là “native memory bằng 0”. JFR có thể cho mẫu CPU, allocation, GC và thread scheduling theo khoảng thời gian, nhưng cần đọc đúng loại event và chi phí thu thập.

Trên Windows, thay lệnh `/proc`/`ps` bằng Task Manager, Resource Monitor, Performance Monitor hoặc PowerShell `Get-Process`; nguyên tắc vẫn là liên kết **cùng PID, cùng khoảng thời gian, cùng môi trường**. Không áp dụng lệnh Linux nguyên xi cho Windows.

## 6. Chẩn đoán xuyên lớp: đi từ hiện tượng đến bằng chứng

Một quy trình có thể lặp lại:

1. **Định danh:** ghi dịch vụ, bản build, runtime/JDK thực chạy, PID, host/container, command line, thời điểm và triệu chứng. Kiểm tra mã lỗi và phạm vi ảnh hưởng.
2. **Đo phía ứng dụng:** latency p50/p95/p99, throughput, error rate, request queue, pool/DB connections, lock/wait và log/trace có correlation ID.
3. **Đo JVM cùng khoảng thời gian:** heap used/committed/max, allocation/GC pause, GC CPU, số platform threads, thread dump/JFR khi có dấu hiệu phù hợp.
4. **Đo OS/container/host:** CPU theo PID/TID, throttling, RSS và memory limit, số thread/FD, I/O wait, disk, network, OOM/kernel events. So sánh cùng đơn vị và cùng thời điểm.
5. **Lập giả thuyết có thể kiểm chứng:** dấu hiệu nào ủng hộ, dấu hiệu nào bác bỏ; thay đổi tải, cấu hình hoặc code ở môi trường an toàn; quan sát hệ quả. Tránh tăng heap, thread pool hay retry một cách mù quáng.

Bảng suy luận nhanh:

| Triệu chứng | Những khả năng cần phân biệt | Bằng chứng để tách nguyên nhân |
| --- | --- | --- |
| API timeout, CPU thấp | Đang đợi DB/mạng, khóa hoặc pool cạn; không nhất thiết JVM “chậm” | Trace, pool queue, thread dump, socket/network và downstream latency |
| API chậm, CPU tiến trình cao | Code nóng, GC, JIT, busy loop | CPU sample/JFR, GC events, thread CPU theo TID |
| CPU host còn rảnh nhưng service chậm | CPU quota/throttling, I/O, lock, downstream | Cgroup CPU metrics, run queue, trace và thread states |
| Heap used tăng sau nhiều đợt GC | Object giữ lâu/leak hoặc cache tăng có chủ đích | GC trend, heap dump khi phù hợp, object graph, traffic |
| Container bị kill, không có Java OOME | Có thể vượt giới hạn cgroup hoặc bị SIGKILL vì lý do khác | Container termination reason, kernel/cgroup OOM events, memory.current/limit |
| `Too many open files` | FD leak, quá nhiều kết nối hoặc limit quá thấp | FD count theo PID, `RLIMIT_NOFILE`, vòng đời resource |

### Ví dụ: độ trễ tăng dù ứng dụng không sửa code

Giả sử deployment mới giữ nguyên ứng dụng, nhưng giảm CPU quota của container. Một số request bắt đầu timeout; host vẫn có CPU rảnh. Đừng kết luận “GC bị lỗi” từ timeout. Hãy kiểm tra: CPU quota và throttling có tăng không; `availableProcessors`/JVM ergonomics có thay đổi không; CPU time của GC và mã ứng dụng ra sao; request queue có tích lũy do throughput giảm không. Nếu metrics cho thấy throttling tăng cùng lúc latency xấu đi, đây là **bằng chứng mạnh cho giới hạn CPU**, cần xác nhận bằng thử nghiệm kiểm soát quota hoặc tải. Không được suy ra chỉ từ một chỉ số CPU.

### Ví dụ: heap bình thường nhưng container OOM

Giả sử heap used dao động 200–300 MiB và không cho thấy Java heap OOME, nhưng pod được báo `OOMKilled`. Điều tra cần kết hợp memory limit, peak memory, native allocations, metaspace, direct buffers, thread stacks, page cache và cgroup OOM events. Tăng `-Xmx` có thể khiến giới hạn container bị chạm sớm hơn; giảm heap chưa chắc giải quyết nếu nguồn tiêu thụ là native memory hoặc page cache. Quyết định cuối cùng phải dựa trên tổng ngân sách bộ nhớ và bằng chứng thực tế.

## 7. Sai lầm thường gặp khi định vị nguyên nhân

- **“JDK, JVM và tiến trình Java là một.”** JDK là bộ công cụ + runtime; JVM là thành phần thực thi; tiến trình OS là đơn vị được OS lập lịch và hạch toán tài nguyên. Quan hệ gần gũi nhưng vai trò khác nhau.
- **“`-Xmx` bằng tổng RAM Java dùng.”** JVM còn metadata, code cache, stacks, native allocations; container/OS có hạch toán riêng.
- **“Heap còn trống nên không thể OOM.”** Native allocation, OS process limit, cgroup limit hoặc lỗi khác vẫn có thể xảy ra.
- **“CPU 100% nghĩa là chiếm toàn bộ máy.”** Phải biết số core, cách công cụ tính phần trăm, CPU quota và CPU affinity.
- **“Thread WAITING là deadlock.”** WAITING/TIMED_WAITING có thể là trạng thái bình thường của thread trong pool; phải xem lock graph, stack, thời gian chờ và tiến triển công việc.
- **“Có cùng bytecode thì hiệu năng luôn giống nhau.”** JVM/JDK version, GC, flags, CPU architecture, kernel, container quota và tải hệ thống ảnh hưởng kết quả.
- **“Exit 137 chắc chắn là OOM.”** Thường liên quan SIGKILL; cần sự kiện hệ thống/container để xác nhận nguyên nhân.
- **“Một metric đủ xác định thủ phạm.”** Mọi metric đều có scope, đơn vị, thời gian lấy mẫu và giới hạn quan sát. Hãy liên kết ít nhất một dấu hiệu ứng dụng với bằng chứng JVM và OS phù hợp.

## 8. Cách tự kiểm tra hiểu đúng mô hình

Với một Java service thực tế, hãy tự trả lời: (1) PID và runtime chính xác là gì? (2) bao nhiêu CPU/RAM được **cấp phép** cho tiến trình/container, so với host? (3) heap dùng bao nhiêu, còn các phần ngoài heap và RSS thế nào? (4) request đang tính toán, chờ JVM pause hay chờ I/O/downstream? (5) hai phép đo nào ở **hai lớp khác nhau** có thể xác nhận hoặc bác bỏ giả thuyết đang có?

**Ghi nhớ:** chẩn đoán Java có chất lượng bắt đầu từ việc nối chuỗi **ứng dụng → JVM trong tiến trình → hệ điều hành → tài nguyên thực/ảo**, đồng thời dùng **JDK như bộ công cụ quan sát**. Chỉ quy kết nguyên nhân sau khi bằng chứng tại các lớp liên quan nhất quán với nhau.