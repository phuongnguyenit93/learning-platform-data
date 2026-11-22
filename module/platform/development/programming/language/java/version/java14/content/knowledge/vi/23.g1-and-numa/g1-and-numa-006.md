# `-XX:+UseNUMA` với G1 và cách kiểm tra NUMA có thực sự hiệu lực (Java 14+)

> **Mục tiêu:** hiểu cờ `-XX:+UseNUMA` trong HotSpot/G1, phân biệt ba mức **đã yêu cầu bật cờ**, **giá trị cờ sau khởi tạo JVM**, và **tối ưu locality NUMA thực sự hoạt động trên hệ thống**. Bài học hướng dẫn xác minh qua `-XX:+PrintFlagsFinal`, Unified Logging `-Xlog:gc+init=info`, log `gc+heap+numa`, API `HotSpotDiagnosticMXBean` và thông tin topology hệ điều hành. Cơ chế NUMA-aware memory allocation cho G1 được bổ sung bởi **JEP 345 trong Java 14** và vẫn thuộc Java hiện đại; ví dụ chạy với JDK 17+ mà không dùng cờ GC logging đã lỗi thời.

## 1. NUMA là gì và vì sao G1 quan tâm?

**NUMA (Non-Uniform Memory Access)** là kiến trúc máy tính có nhiều vùng nhớ gắn với các node CPU khác nhau. Thread chạy trên CPU thuộc node A thường truy cập **bộ nhớ vật lý local** của node A với độ trễ thấp hơn so với bộ nhớ thuộc node B. Độ trễ thực tế phụ thuộc kiến trúc máy, trạng thái cache, interconnect, policy của OS và nơi thread được hệ điều hành lập lịch.

Ví dụ minh họa:

```text
NUMA node 0                        NUMA node 1
+----------------------+           +----------------------+
| CPU cores / sockets  |           | CPU cores / sockets  |
| Local memory bank    |           | Local memory bank    |
+-----------+----------+           +-----------+----------+
            \_____________________/
              Interconnect giữa node

Thread chạy ở node 0:
  - Đọc RAM của node 0: thường nhanh hơn
  - Đọc RAM của node 1: có thể tốn thêm độ trễ/traffic
```

Không phải máy nhiều core là máy có **nhiều NUMA node khả dụng**. Một laptop nhiều core có thể chỉ báo **một node**; một server nhiều socket cũng có thể được VM/container nhìn thấy chỉ một phần topology. Số node **phần cứng**, node **OS cung cấp**, và node **tiến trình Java có thể sử dụng** không nhất thiết giống nhau.

**G1 (Garbage-First Garbage Collector)** chia Java heap thành nhiều **heap regions**, trong đó young generation có vùng **Eden** và **Survivor**. JEP 345 bổ sung cơ chế bố trí những vùng nhớ phù hợp theo NUMA node để giảm tỷ lệ truy cập remote trong các workload thích hợp.

**Giới hạn phạm vi quan trọng:** JEP 345 tập trung ban đầu vào **NUMA-aware allocation cho young generation, đặc biệt Eden/Survivor**. Không suy ra `-XX:+UseNUMA` bảo đảm **mọi object trên heap**, Old generation, metaspace, direct memory, native stack hoặc mọi thao tác GC đều được ràng buộc ở node local. Hiệu quả còn phụ thuộc workload và khả năng của OS/JVM.

## 2. `UseNUMA` yêu cầu điều gì?

Trên HotSpot/JDK hiện hành, cờ JVM:

```bash
-XX:+UseNUMA    # Yêu cầu bật tối ưu NUMA
-XX:-UseNUMA    # Yêu cầu không dùng tối ưu NUMA
```

Với bài này, chọn collector rõ ràng:

```bash
java -XX:+UseG1GC -XX:+UseNUMA -version
```

`-XX:+UseG1GC` yêu cầu G1; `-XX:+UseNUMA` yêu cầu JVM thử dùng cơ chế NUMA. Đây là **JVM startup flags**; phải đặt trước tên class, `-jar` hoặc module main. `UseNUMA` không phải tham số `main(String[] args)` hay một property kiểu `-DUseNUMA=true`.

Theo tài liệu Oracle JDK hiện hành, **giá trị mặc định của `UseNUMA` còn phụ thuộc garbage collector**. Vì vậy không nên dạy quy tắc tuyệt đối rằng mọi JDK/mọi GC có cùng default; hãy đọc **giá trị trên JVM thực tế**.

**Điều kiện cốt lõi:** truyền `-XX:+UseNUMA` thành công **không đủ để khẳng định** JVM đã phát hiện nhiều node và tối ưu NUMA đang chạy. Trong lúc khởi tạo, JVM có thể tắt hoặc không sử dụng cơ chế NUMA do hạn chế nền tảng, topology chỉ một node, affinity của tiến trình, trạng thái kernel, container, đặc điểm của collector hoặc cấu hình hệ thống.

Từ Java 14, G1 có hỗ trợ NUMA được bổ sung qua JEP 345, lúc giới thiệu nhắm đến môi trường Linux phù hợp. **Không chuyển câu “máy có nhiều CPU” thành kết luận “NUMA đang hoạt động”**; phải kiểm chứng trên bản JDK và OS thực tế.

## 3. Ba tầng xác minh: yêu cầu, giá trị cuối, hiệu lực thực tế

| Tầng | Cần trả lời | Bằng chứng | Điều chưa thể kết luận |
|---|---|---|---|
| 1. **Đã yêu cầu** | Command line/process có `-XX:+UseNUMA` không? | Startup script, container JVM args, `jcmd <pid> VM.command_line` | JVM có thực sự bật NUMA không |
| 2. **Cờ sau init** | `UseNUMA` cuối cùng là `true` hay `false`? G1 có đang dùng không? | `-XX:+PrintFlagsFinal`; `HotSpotDiagnosticMXBean`; `jcmd <pid> VM.flags -all` | Allocation có đúng local node hoặc performance đã tốt hơn không |
| 3. **Hỗ trợ runtime/hiệu quả** | JVM báo NUMA Support thế nào, thấy nhiều node và việc phân bố ra sao? | `-Xlog:gc+init=info`, `gc+heap+numa=debug`, OS topology, benchmark | Không thể chứng minh hiệu quả chỉ qua một dòng log |

**Phân biệt `origin` của flag với giá trị:** trong bảng cờ hoặc `VMOption.getOrigin()`, nhãn `command line`/`VM_CREATION` cho biết cờ từng được **đưa từ câu lệnh khởi chạy**. Nó **không** có nghĩa `UseNUMA` hiện tại chắc chắn là `true`. Mỗi lần kiểm tra phải đọc cả **value** và ngữ cảnh.

Ví dụ đã kiểm chứng trên máy Windows OpenJDK 24: command line có `-XX:+UseNUMA` nhưng `-XX:+PrintFlagsFinal` hiện **`UseNUMA = false {command line}`** và GC init log ghi `NUMA Support: Disabled`. Đây là một trường hợp hợp lệ cho thấy yêu cầu không trở thành hỗ trợ hiệu dụng.

## 4. Kiểm tra cấu hình bằng `-XX:+PrintFlagsFinal`

Cách nhanh, không cần viết mã Java:

```bash
# Xem giá trị mặc định trên JVM đang dùng:
java -XX:+PrintFlagsFinal -version

# Ép dùng G1 và yêu cầu NUMA, rồi xem giá trị sau init:
java -XX:+UseG1GC -XX:+UseNUMA -XX:+PrintFlagsFinal -version

# So sánh baseline không yêu cầu NUMA:
java -XX:+UseG1GC -XX:-UseNUMA -XX:+PrintFlagsFinal -version
```

Đầu ra `PrintFlagsFinal` dài, chỉ cần lọc các dòng có `UseG1GC` và `UseNUMA`. Trên Linux/Bash:

```bash
java -XX:+UseG1GC -XX:+UseNUMA -XX:+PrintFlagsFinal -version 2>&1 \
  | grep -E '[[:space:]](UseG1GC|UseNUMA)[[:space:]]'
```

Trên Windows PowerShell:

```powershell
java -XX:+UseG1GC -XX:+UseNUMA -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String -Pattern 'UseG1GC|UseNUMA'
```

Chú ý lọc `UseNUMA` cũng có thể khớp `UseNUMAInterleaving`; đọc **tên flag đầy đủ** để không nhầm chúng. Một ví dụ hiển thị từ máy thử:

```text
bool UseG1GC = true  {product} {command line}
bool UseNUMA = false  {product} {command line}
```

**Ý nghĩa:** G1 được chọn; yêu cầu NUMA có ở command line nhưng sau khởi tạo `UseNUMA=false`. Output thực tế có spacing và nhãn origin khác giữa các JDK, nên bảng là trích dẫn ý nghĩa, **không phải format ổn định để parse bằng vị trí cột**.

Nếu `UseG1GC=false`, trước hết kiểm tra JVM đã chọn collector nào. Không đánh giá NUMA-aware G1 khi ứng dụng lại chạy bằng collector khác. Một số công cụ `-XX:+PrintFlagsFinal -version` cho thấy startup flags của **JVM mới** chứ **không phải process Java production đang chạy**; để xem đúng production process dùng `jcmd`/JMX trong phạm vi cho phép.

### `-XX:+PrintCommandLineFlags` có vai trò khác

`-XX:+PrintCommandLineFlags` có thể hiện các startup flags đã chọn, nhưng **không** thay cho kiểm tra trạng thái sau init. Ví dụ một startup flag được chấp nhận nhưng NUMA không khả dụng vẫn có thể tạo ra `UseNUMA=false` sau khi JVM đánh giá môi trường.

## 5. Kiểm tra bằng Unified Logging: `gc+init` và `gc+heap+numa`

Để thấy G1 thực sự nhận diện môi trường thế nào, bật Unified Logging:

```bash
java -XX:+UseG1GC -XX:+UseNUMA \
  -Xlog:gc+init=info,gc+heap+numa=debug \
  -version
```

Lệnh trên là **Bash**; trên Windows PowerShell có thể viết một dòng:

```powershell
java -XX:+UseG1GC -XX:+UseNUMA "-Xlog:gc+init=info,gc+heap+numa=debug" -version
```

Hai nhóm log có mục đích khác nhau:

- `gc+init=info`: thông tin **khởi tạo GC**, bao gồm loại GC, số CPU, heap region size và trong các bản HotSpot hỗ trợ có dòng **`NUMA Support: Enabled`** hoặc **`NUMA Support: Disabled`**.
- `gc+heap+numa=debug`: thông tin **chi tiết liên quan NUMA của G1** khi cơ chế hoạt động và có dữ liệu log phù hợp. Một số bản/điều kiện sẽ cần có GC thực tế hoặc mức log chi tiết hơn để sinh log tương ứng.

**Không xem việc không xuất hiện log `gc+heap+numa` trong lệnh `-version` là lỗi.** `-version` khởi động JVM rồi thoát rất nhanh, không tạo nhiều allocation hoặc GC cycles; log NUMA chi tiết có thể không có. Với ứng dụng thật, chạy một workload có GC và dùng file log nếu muốn so sánh:

```bash
java -XX:+UseG1GC -XX:+UseNUMA \
  -Xlog:gc+init=info,gc+heap+numa=debug:file=g1-numa.log:time,uptime,level,tags \
  -jar app.jar
```

`app.jar` là tên **placeholder của JAR ứng dụng tự có**, không phải artifact được tạo trong bài; thay bằng JAR thật trước khi chạy. Log file chứa thông tin môi trường/GC, cần quyền ghi và chính sách lưu/xóa phù hợp.

**Cách đọc log đúng:**

1. Xác định có `NUMA Support: Enabled/Disabled` trong log init và ghi lại JDK, OS, collector.
2. Khi `Enabled` và hệ thống có nhiều node khả dụng, có thể tìm các thống kê `gc,heap,numa` theo node nếu phiên bản JVM phát ra.
3. Nếu `Disabled`, cờ `UseNUMA` có thể đang false; trước khi khẳng định một lỗi Java, kiểm tra NUMA topology, affinity, giới hạn container/VM và khả năng hỗ trợ của OS.
4. Nếu không có thông tin chi tiết, dùng `java -Xlog:help` để kiểm tra các tag/kết hợp tag được JVM hỗ trợ; tăng log tạm thời ở môi trường thử nghiệm khi cần. Không bật trace dày trong production mà không xem xét overhead.

Dòng log `NUMA Support: Enabled` là bằng chứng **bộ phận NUMA của JVM đã được bật**; nó **không phải** một số đo chứng minh p95 latency hoặc throughput tốt hơn.

## 6. Ví dụ Java 17+ đọc `UseG1GC` và `UseNUMA` từ JVM đang chạy

`com.sun.management.HotSpotDiagnosticMXBean` và `VMOption` là API quản lý của HotSpot trong JDK hiện đại. Chúng cho phép đọc giá trị cờ của **đúng JVM đang chạy mã** cùng nguồn cấu hình (`VMOption.Origin`). Đây là cách nhìn **trực tiếp hơn** so với lấy output của một process Java khác chạy `-version`.

Tạo tệp **`G1NumaInspector.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.VMOption;

public class G1NumaInspector {
    static void printOption(HotSpotDiagnosticMXBean mx, String name) {
        VMOption option = mx.getVMOption(name);
        System.out.println(name + "=" + option.getValue()
            + " origin=" + option.getOrigin());
    }

    public static void main(String[] args) {
        HotSpotDiagnosticMXBean mx =
            ManagementFactory.getPlatformMXBean(HotSpotDiagnosticMXBean.class);

        printOption(mx, "UseG1GC");
        printOption(mx, "UseNUMA");

        List<String> gcNames = ManagementFactory.getGarbageCollectorMXBeans()
            .stream().map(GarbageCollectorMXBean::getName)
            .sorted().toList();
        System.out.println("gcNames=" + gcNames);
    }
}
```

Biên dịch, chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 G1NumaInspector.java

# Baseline:
java G1NumaInspector

# Yêu cầu G1 + NUMA; đồng thời hiển thị log init:
java -XX:+UseG1GC -XX:+UseNUMA -Xlog:gc+init=info G1NumaInspector

# Đối chứng không dùng NUMA:
java -XX:+UseG1GC -XX:-UseNUMA -Xlog:gc+init=info G1NumaInspector
```

**Đầu ra đã kiểm chứng trên Windows OpenJDK 24 (phần stdout Java, không gồm các dòng GC log)**:

```text
# Lần chạy mặc định:
UseG1GC=true origin=ERGONOMIC
UseNUMA=false origin=DEFAULT
gcNames=[G1 Concurrent GC, G1 Old Generation, G1 Young Generation]

# Lần chạy yêu cầu -XX:+UseG1GC -XX:+UseNUMA:
UseG1GC=true origin=VM_CREATION
UseNUMA=false origin=VM_CREATION
gcNames=[G1 Concurrent GC, G1 Old Generation, G1 Young Generation]

# Lần chạy đối chứng -XX:+UseG1GC -XX:-UseNUMA:
UseG1GC=true origin=VM_CREATION
UseNUMA=false origin=VM_CREATION
gcNames=[G1 Concurrent GC, G1 Old Generation, G1 Young Generation]
```

Khi chạy lần hai, Unified Logging in thêm **`NUMA Support: Disabled`** trong phần `gc,init` trên máy thử. Dòng này là quan sát có thật cho **máy Windows JDK 24 này**, **không** phải quy tắc rằng `-XX:+UseNUMA` luôn không hoạt động trên mọi máy.

**Giải thích kỹ:**

- `UseG1GC=true`: JVM dùng G1. Danh sách `gcNames` có các GarbageCollectorMXBean mang tên G1, cung cấp chứng cứ bổ sung về collector đang hoạt động.
- `UseNUMA=false`: cờ ở JVM đang chạy **không được bật sau init**, nên không có cơ sở nói tối ưu NUMA của G1 đang hiệu lực.
- `origin=VM_CREATION`: cho biết lựa chọn được đưa từ phía khởi chạy; **không** phủ định giá trị `false` cuối cùng.
- `origin=ERGONOMIC`, `DEFAULT`: những giá trị được chọn theo cơ chế JVM hoặc mặc định ở lần chạy không chỉ định cờ.
- Tên `gcNames` và chi tiết `Origin` là **phụ thuộc phiên bản JVM**; không dùng làm điều kiện kiểm thử tuyệt đối trên mọi nhà cung cấp JDK.
- `HotSpotDiagnosticMXBean` dành cho **HotSpot-compatible JVM**. Đừng giả định mọi JVM khác triển khai đầy đủ bean hoặc các tên flag tương tự.

Đây là một chương trình Java độc lập có thể compile/run, nhưng **không tự chứng minh có nhiều NUMA node**. Để kết luận việc NUMA tối ưu thực sự được kích hoạt, vẫn cần đối chiếu log `gc+init`, topology và nếu quan trọng thì thống kê allocation/benchmark.

## 7. Xem cấu hình của **process đang chạy** bằng `jcmd`

Trong vận hành dịch vụ, lệnh `java -version` hay `java -XX:+PrintFlagsFinal -version` chỉ kiểm tra **một process kiểm tra riêng**. Nếu muốn biết service production thực sự chạy với flags nào, có thể dùng `jcmd` trên host/JVM có quyền tương ứng:

```bash
# Liệt kê JVM process mà công cụ có thể thấy:
jcmd -l

# Hiện command line JVM thực đang chạy:
jcmd <pid> VM.command_line

# Hiện VM flags của JVM đích:
jcmd <pid> VM.flags

# Khi cần đầy đủ cờ và giá trị đã tính:
jcmd <pid> VM.flags -all
```

`<pid>` là **ký hiệu để thay bằng số process ID**, không gõ nguyên dấu ngoặc. Quyền attach, container namespace và cấu hình bảo mật của JVM có thể hạn chế `jcmd`. Nếu JVM chạy trong container, thực hiện trong cùng namespace hoặc qua phương pháp quan sát được hỗ trợ, không giả định `jcmd -l` ngoài host luôn nhìn thấy đủ PIDs.

Cách đọc:

- `VM.command_line` xác minh `-XX:+UseNUMA` đã thực sự nằm trong lệnh khởi chạy của service chưa.
- `VM.flags -all` kiểm tra **giá trị cuối** của `UseNUMA` và `UseG1GC`; thông tin format/độ chi tiết có thể thay đổi theo JDK.
- Log `gc+init` của **chính service đó** xác định `NUMA Support` thay vì dùng log của process test khác.
- Kiểm tra môi trường OS/VM/container đang thấy bao nhiêu node. Mục tiêu là **đối chiếu cùng một deployment**, không kết hợp cờ của host A với benchmark từ host B.

Nếu tool ghi `unknown diagnostic command` hoặc attach bị từ chối, hãy xem `jcmd <pid> help` và chính sách môi trường trước khi sửa script. Một số môi trường cố ý tắt cơ chế attach vì lý do bảo mật.

## 8. Điều kiện OS, topology và container làm `UseNUMA` mất hiệu lực

### Trên Linux: xác minh NUMA topology đúng môi trường chạy

Một số lệnh **chẩn đoán**, không bắt buộc phải có sẵn trong mọi container:

```bash
# Nút NUMA OS công bố (nếu có sysfs):
cat /sys/devices/system/node/online

# Nếu đã cài numactl:
numactl --hardware

# Khi chạy ứng dụng và có numastat:
numastat -p <pid>

# Xem giới hạn CPU/NUMA affinity của process:
taskset -pc <pid>
```

- File `/sys/devices/system/node/online` hiển thị các node online của **kernel**, nhưng không nhất thiết cho biết mọi node đó đều khả dụng với process.
- `numactl --hardware` mô tả NUMA node, CPU và khoảng cách memory theo OS; nó không khẳng định G1 đang dùng NUMA.
- `numastat -p` giúp quan sát thống kê sử dụng bộ nhớ theo node của process; phân bố khác không tự chứng minh G1 đạt tối ưu hoặc mọi object được đặt trên node mong muốn.
- `taskset` kiểm tra CPU affinity; kết hợp kiểm tra `cpuset.cpus.effective` và `cpuset.mems.effective` của cgroup nếu đang ở container.
- Một container bị giới hạn CPU/memory vào một nhóm node, hoặc OS bị cấu hình NUMA interleave/affinity đặc biệt, có thể khiến topology JVM thấy khác host vật lý.

**Nếu chỉ có một NUMA node hoạt động/khả dụng**, chạy `-XX:+UseNUMA` thường không đem lại lợi ích locality liên node. JVM có thể vô hiệu hóa hỗ trợ; đây là hành vi hợp lý, không nhất thiết là lỗi cấu hình.

### Trên Windows và các JVM khác

Tính năng G1 NUMA trong JEP 345 ban đầu nhằm vào Linux; hiệu lực và hỗ trợ trên Windows hoặc môi trường khác **phải xem log/flags của đúng JDK**. Việc HotSpot cho phép bạn truyền `-XX:+UseNUMA` trên Windows không tự đảm bảo hoạt động đa-node.

Trong bài test trên Windows OpenJDK 24, yêu cầu `-XX:+UseNUMA` được parser chấp nhận nhưng GC init vẫn ghi `NUMA Support: Disabled` và `UseNUMA=false`. Vì thế không đưa ra hướng dẫn “thấy command line thì đã bật NUMA” cho mọi OS.

Các máy ảo hoặc container có thể ẩn topology của máy chủ. Nếu bạn thực sự cần đánh giá lợi ích NUMA, hãy test trên host nhiều node **được process sử dụng**, có workload và heap đại diện thay vì máy desktop/laptop chỉ một node.

## 9. Khi nào `UseNUMA=true` vẫn chưa đủ chứng minh cải thiện?

Giả sử trong JVM mục tiêu, cả `UseG1GC=true` và `UseNUMA=true`; log init báo `NUMA Support: Enabled`. Đây là bằng chứng rằng tính năng có thể hoạt động. Tuy nhiên **hiệu năng** còn phụ thuộc:

- **Heap size và live set:** heap rất nhỏ so với RAM của một node có thể đã có locality tốt; phân phối liên node ít lợi ích.
- **Đường truy cập bộ nhớ:** ứng dụng chỉ đọc dữ liệu local, hoặc ngược lại chia sẻ object nhiều giữa các thread, có thể có kết quả khác nhau.
- **Scheduling và CPU affinity:** thread di chuyển giữa node khiến local/remote memory accesses thay đổi.
- **Tần suất allocation và GC:** workload nhiều allocation/evacuation có đặc điểm khác dịch vụ hầu như không allocate.
- **Node count và interconnect:** số node, topology, băng thông, latency, memory bandwidth thực tế ảnh hưởng kết quả.
- **Container limits/THP/large pages/policy OS:** có thể làm việc placement theo node khác kỳ vọng.
- **Các JVM flags khác:** `-Xms`, `-Xmx`, GC selection, page size và chính sách thread ảnh hưởng workload.

Vì vậy cần **đo trên đúng môi trường**, ít nhất hai cấu hình đối chứng:

```text
A: -XX:+UseG1GC -XX:-UseNUMA    (baseline)
B: -XX:+UseG1GC -XX:+UseNUMA    (candidate)

Giữ nguyên: JDK/build, hardware, container/affinity,
            -Xms/-Xmx, traffic, dataset, thời lượng đo.

Theo dõi: throughput, p95/p99 latency, CPU, GC pause,
          tần suất GC, memory usage và NUMA stats (nếu có).
```

Nên chạy nhiều lượt đủ thời gian warmup, cân bằng thứ tự A/B và so sánh thống kê thay vì một lần đo. Không bật `UseNUMA` vào production chỉ vì một benchmark cũ khác topology báo lợi ích.

**Đặc biệt:** NUMA placement có thể cải thiện một số workload nhưng cũng có chi phí/ảnh hưởng khác. Cấu hình JVM không phải “càng nhiều cờ tối ưu càng nhanh”.

## 10. Những nhầm lẫn thường gặp và cách sửa

| Nhầm lẫn/triệu chứng | Nguyên nhân | Cách kiểm tra đúng |
|---|---|---|
| `-XX:+UseNUMA` nằm trên startup args nên nghĩ đã hoạt động | JVM có thể tắt tính năng trong khởi tạo | Đọc `UseNUMA` sau init và `NUMA Support` ở `gc+init` |
| `UseNUMA=false {command line}` bị coi là nghịch lý | `origin` là **nguồn yêu cầu**, không phải bảo đảm giá trị cuối | Đọc field `value=false` và lý do môi trường |
| Chạy `-XX:+PrintFlagsFinal -version` rồi suy ra chính service production | Đây là **một process khác** | Dùng `jcmd <pid>` và logs của service |
| `UseG1GC=false` nhưng tiếp tục phân tích G1 NUMA | Collector thực tế không phải G1 | Kiểm tra `UseG1GC` và GC names |
| Không thấy `gc+heap+numa` khi chỉ dùng `-version` | Không có workload/GC cycles phù hợp | Chạy app thực, bật log đủ mức rồi xem |
| Có 2 socket vật lý nhưng chỉ thấy 1 node | OS/VM/container/affinity có thể giới hạn topology | Kiểm tra node online và node khả dụng cho process |
| Thấy `NUMA Support: Enabled` rồi tuyên bố tăng throughput | Enabled không phải benchmark | A/B test cùng workload/hardware |
| Bật `UseNUMA` nghĩa là mọi bộ nhớ Java đều local | JEP 345 hướng vào các cơ chế allocation G1, không toàn bộ memory | Không đánh đồng với pin toàn heap/OS affinity |
| Dùng log flag GC cũ `PrintGCDetails` thay cho `-Xlog` | Tài liệu cũ/lỗi thời | Ưu tiên Unified Logging hiện hành |
| Dùng cờ `-DUseNUMA=true` | System property không phải HotSpot tuning flag | Dùng `-XX:+UseNUMA` trước main class |
| Test Windows rồi khẳng định Linux y hệt | Hỗ trợ NUMA phụ thuộc OS và topology | Kiểm thử trên nền tảng được triển khai |
| Dùng JDK/GC khác nhau ở A và B | Kết quả benchmark không so được | Giữ các yếu tố khác cố định |
| Thấy nhiều RAM dùng ở node 1 là “đúng/ sai” ngay | Thống kê node không biểu diễn toàn bộ behavior của G1 | Kết hợp logs, latency và workload |

## 11. Checklist chốt cấu hình NUMA của G1

1. Ghi rõ **JDK vendor/version/build**, OS, container topology, heap size và mục tiêu performance.
2. Kiểm tra NUMA nodes **thực sự khả dụng cho process**, không chỉ số socket phần cứng.
3. Dùng `-XX:+UseG1GC` nếu bài toán cần đánh giá G1, và yêu cầu `-XX:+UseNUMA`.
4. Đọc `-XX:+PrintFlagsFinal` / `HotSpotDiagnosticMXBean` / `jcmd VM.flags -all` để biết **giá trị cuối** `UseG1GC` và `UseNUMA`.
5. Dùng `-Xlog:gc+init=info` để xem `NUMA Support`; không chỉ dựa vào dòng command line.
6. Khi phù hợp, bật `-Xlog:gc+heap+numa=debug` trong workload có GC; xem log theo node và chi phí logging.
7. Nếu disabled, kiểm tra OS/JVM hỗ trợ, affinity, cpuset, node count và các giới hạn VM/container trước khi coi đây là lỗi code.
8. Nếu enabled, **A/B benchmark** với cấu hình baseline `-XX:-UseNUMA` và cùng workload đại diện.
9. Theo dõi throughput, p95/p99, CPU, memory locality, GC pause và regression.
10. Không dựa vào `UseNUMAInterleaving` hay các cờ GC cũ theo bài viết cũ để thay thế kiểm chứng `UseNUMA` của G1.
11. Không hard-code câu chữ/format log, GC MXBean names hoặc origin làm hợp đồng ứng dụng; dùng chúng để **chẩn đoán**, không quyết định nghiệp vụ.
12. Chỉ triển khai khi kết quả đo chứng minh lợi ích và có phương án rollback rõ ràng.

## Tài liệu tham khảo chính thức

- OpenJDK, **JEP 345 — NUMA-Aware Memory Allocation for G1**, tích hợp trong Java 14: https://openjdk.org/jeps/345
- Oracle Java SE 25, **The java Command**, `-XX:+UseNUMA`, `-XX:+UseG1GC`, `-XX:+PrintFlagsFinal` và `-Xlog`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- Oracle Java SE 25, **Garbage-First (G1) Garbage Collector**, giới thiệu collector và heap regions: https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html
- Oracle Java SE 25, **G1 Tuning Guide**, khuyến nghị thiết lập mặc định và đo trước khi tuning: https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html
- Oracle Java SE 25, **jcmd Command**, `VM.command_line` và `VM.flags`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html
- Oracle Java SE 25 API, **HotSpotDiagnosticMXBean**: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html
- Oracle Java SE 25 API, **VMOption** và `getOrigin()`: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/VMOption.html
