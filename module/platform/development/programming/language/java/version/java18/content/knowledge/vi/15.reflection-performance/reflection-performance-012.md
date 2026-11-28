# Ghi nhận bản JDK, JVM flag, phần cứng và dữ liệu đầu vào để benchmark có thể tái lập

## 1. Vì sao tốc độ reflection cần đi kèm dấu vết môi trường?

Trong module **JAVA_VERSION_JAVA18**, chương **Reflection và hiệu năng** xem xét cách đánh giá chi phí của `Method.invoke`, lời gọi Java thông thường và `MethodHandle` trên **JDK đang thực sự sử dụng**. Một con số như “reflection mất 8 ns/op” không đủ để kết luận nếu thiếu thông tin về JDK, tham số khởi động JVM, phần cứng và dữ liệu đầu vào.

Java 18 là bối cảnh lịch sử của module, không phải lời khuyên chỉ benchmark trên JDK 18. Hãy chạy lại trên JDK hiện đại mà dự án định triển khai, vì các tối ưu của VM, implementation reflection, JIT và GC tiếp tục phát triển theo phiên bản. Không sử dụng kết luận hiệu năng từ cơ chế triển khai đã lỗi thời làm chân lý cho các JDK mới.

**Benchmark có thể tái lập** không có nghĩa mọi lần chạy đều phải ra đúng cùng một giá trị nanosecond. Nó có nghĩa người khác có đủ **mã nguồn, cấu hình, dữ liệu, môi trường và quy trình** để lặp lại phép đo, kiểm chứng kết quả trong phạm vi biến động hợp lý và giải thích chênh lệch.

Trong bài này, ta xây một hồ sơ thí nghiệm (*benchmark manifest*) gồm:

1. **Định danh mã nguồn và công cụ:** commit, trạng thái working tree, phiên bản JMH và cấu hình build.
2. **Định danh JDK:** vendor, version đầy đủ, build/runtime/VM version, kiến trúc và đường dẫn runtime được chọn.
3. **JVM flag:** các đối số khởi động thực tế của JVM benchmark fork, lựa chọn heap/GC/JIT và các giá trị hiệu lực cần xác minh.
4. **Phần cứng và OS:** CPU, số lõi/luồng, bộ nhớ, OS, container/VM, giới hạn tài nguyên và yếu tố tải máy.
5. **Dữ liệu đầu vào:** seed, độ dài, phân phối, đường gọi, kiểu chữ ký, độ đa hình và kiểm tra tính đúng.
6. **Phương pháp đo:** warmup, measurement, forks, threads, mode, đơn vị, thống kê và file kết quả gốc.

Bài có ví dụ dùng **JMH** (Java Microbenchmark Harness) để tránh những sai lệch dễ gặp khi tự đo các lời gọi rất ngắn bằng `System.nanoTime()`. Tài liệu dùng các API Java/JMH còn thích hợp trên JDK hiện đại; những số liệu minh họa không được trình bày như kết quả đo thực tế.

## 2. Những biến số làm kết quả benchmark không ổn định

Một lời gọi reflection có thể thay đổi chi phí quan sát được vì nhiều nguyên nhân khác nhau:

| Nhóm biến số | Ví dụ | Ảnh hưởng có thể có |
| --- | --- | --- |
| JDK / VM | Vendor, build, HotSpot, bản cập nhật | Tối ưu JIT, cơ chế gọi reflection, runtime library khác nhau |
| JVM launch | `-Xms`/`-Xmx`, `-XX` flags, `--add-opens`, `-D` | Heap, JIT, GC, quyền reflection, đường code và profile |
| CPU | Model, kiến trúc, SMT, tần số, cache | Thời gian xử lý và tính ổn định giữa các lần chạy |
| OS / scheduler | Version, affinity, power plan, tác vụ nền | Jitter, context switching, CPU migration |
| Container / VM | CPU quota, cpuset, memory limit | Throttling và tài nguyên nhìn thấy bởi JVM |
| Dữ liệu | `null`/không-null, kích thước, phân phối, subtype | Chi phí logic đích, allocation và branch prediction |
| Cách gọi | Direct / `Method.invoke` / `invokeExact` | Chuyển đổi argument, boxing, inline, access check |
| Quy trình đo | Warmup, fork, iteration, threads | Khả năng JIT ổn định và độ tin cậy của thống kê |

Nếu thay **hai biến cùng lúc** rồi kết luận “JDK B nhanh hơn JDK A”, bạn khó biết nguyên nhân. Một phép so sánh có kiểm soát cần giữ nguyên những biến không phải đối tượng nghiên cứu và ghi nhận các biến không kiểm soát hoàn toàn.

### 2.1. Các mức độ tái lập

- **Tái lập cấu hình:** chạy đúng source commit, thư viện, bản JDK, options, dữ liệu và JMH command.
- **Tái lập phép đo:** cùng benchmark mode, số lần warmup/measurement, forks, threads và các điều kiện tải tương đối.
- **Tái lập kết luận:** nhiều lần chạy độc lập cho hiệu ứng cùng chiều, có độ lớn vượt biến động nhiễu và có kiểm tra tính đúng.

Một lần chạy với điểm số thấp nhất không thể thay cho các mức độ trên.

## 3. Ghi nhận danh tính JDK và JVM trước khi đo

Không chỉ ghi “Java 21” hoặc “Java 25”. Ít nhất cần phân biệt **JDK dùng biên dịch** và **java executable thực sự chạy các benchmark fork**.

### 3.1. Lệnh thu thập thông tin cơ bản

Chạy trong đúng môi trường sẽ chạy benchmark:

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

Nếu hệ thống có nhiều JDK, ghi rõ đường dẫn executable mà JMH dùng. Ví dụ khi JMH được chỉ định bằng `-jvm` hoặc bởi cấu hình build/CI, executable này phải trùng JDK dự định so sánh. `JAVA_HOME` là gợi ý cấu hình nhưng **không tự chứng minh** command `java` trên `PATH` trỏ vào JDK đó.

Các thuộc tính cần ghi nhận gồm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `java.version` | Phiên bản Java hiển thị của runtime |
| `java.runtime.version` | Version đầy đủ của runtime, thường có build metadata |
| `java.vendor` | Nhà cung cấp runtime |
| `java.vm.name` | Tên máy ảo |
| `java.vm.version` | Phiên bản VM |
| `java.vm.vendor` | Nhà cung cấp VM |
| `os.name`, `os.version`, `os.arch` | Môi trường hệ điều hành và kiến trúc JVM nhìn thấy |
| `java.home` | Đường dẫn đến runtime thực tế, cần cân nhắc ẩn thông tin máy nội bộ khi công bố |

**Không dùng chỉ `Runtime.version().feature()`** để thay định danh JDK đầy đủ: feature number không phân biệt các bản build hoặc các vendor. Khi so sánh JDK trong CI, lưu đầy đủ output `java -version` cùng version của công cụ JMH.

### 3.2. API chụp metadata của VM trong tiến trình

Một helper thu thập metadata ngay trong JVM đang chạy:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.time.Instant;
import java.util.List;

public final class VmSnapshot {
    public static void main(String[] args) {
        RuntimeMXBean vm = ManagementFactory.getRuntimeMXBean();

        System.out.println("timestamp.utc=" + Instant.now());
        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("java.runtime.version="
                + System.getProperty("java.runtime.version"));
        System.out.println("java.vendor="
                + System.getProperty("java.vendor"));
        System.out.println("java.vm.name="
                + System.getProperty("java.vm.name"));
        System.out.println("java.vm.version="
                + System.getProperty("java.vm.version"));
        System.out.println("os.name="
                + System.getProperty("os.name"));
        System.out.println("os.version="
                + System.getProperty("os.version"));
        System.out.println("os.arch="
                + System.getProperty("os.arch"));
        System.out.println("available.processors="
                + Runtime.getRuntime().availableProcessors());

        List<String> vmArgs = vm.getInputArguments();
        for (int i = 0; i < vmArgs.size(); i++) {
            System.out.println("vm.inputArgument[" + i + "]=" + vmArgs.get(i));
        }
    }
}
```

Chạy ví dụ:

```bash
javac -encoding UTF-8 VmSnapshot.java
java -Xms512m -Xmx512m VmSnapshot
```

`RuntimeMXBean.getInputArguments()` cho biết các VM input arguments được runtime ghi nhận; nó **không đồng nghĩa** mọi cờ hiệu lực hoặc toàn bộ command line của application. Một giá trị mặc định do VM chọn có thể không xuất hiện trong danh sách đối số. Ngược lại, một flag có thể được cấp qua biến môi trường JVM, script hoặc test harness; cần giữ cả command line khởi chạy thực tế và effective flag khi quan trọng.

**Quan trọng với JMH:** chạy `VmSnapshot` như chương trình riêng chỉ chứng minh môi trường của **tiến trình snapshot**, không chắc giống mọi fork do JMH tạo. Để audit benchmark, ghi lại command/config của JMH và output thông tin VM trong *fork thực tế* hoặc dùng log fork có thể kiểm chứng.

## 4. Ghi nhận JVM arguments và effective flags

### 4.1. Phân biệt flag yêu cầu và flag thực tế

Giả sử ghi `-Xmx1g`. Đó là yêu cầu về maximum heap, không cho biết mọi hành vi khác của VM. Cùng một flag có thể ảnh hưởng khác nhau khi collector, số CPU, container limit hoặc JDK build thay đổi.

Các nguồn thông tin bổ sung nhau:

- **Launch command:** shell script, build task và câu lệnh JMH, bao gồm `-jvm`, `-jvmArgs`, `-jvmArgsAppend` khi có.
- **VM input arguments:** `ManagementFactory.getRuntimeMXBean().getInputArguments()` của đúng tiến trình.
- **Effective VM flags:** các flag JDK hiện tại hỗ trợ, giá trị cuối và nguồn gốc `default`/`ergonomic`/`command line` nếu công cụ in ra.
- **Runtime properties:** `java.version`, `java.vm.version` và các `-D` property liên quan.

Ví dụ quan sát flags (chạy trên chính JDK định benchmark):

```bash
java -XX:+PrintFlagsFinal -version
```

Output có thể rất dài. Nếu muốn đối chiếu một JVM fork có `-Xms1g -Xmx1g`, dùng *cùng các option* trong lệnh kiểm tra thay vì chỉ đọc flags từ lệnh `java -version` mặc định:

```bash
java -Xms1g -Xmx1g -XX:+PrintFlagsFinal -version
```

Một lệnh như trên vẫn là **tiến trình chẩn đoán riêng**, nên chưa chứng minh VM benchmark fork mang đúng mọi option. JMH thường hiển thị thông tin JVM, JVM args, forks, warmup/measurement trong báo cáo; lưu nguyên bản log để đối chiếu với manifest.

### 4.2. Những flag cần ghi khi có ảnh hưởng

| Nhóm | Dữ liệu cần lưu | Vì sao |
| --- | --- | --- |
| Bộ nhớ | `-Xms`, `-Xmx`, heap thực tế | Allocation và GC |
| Collector | GC đã chọn, `-XX` flag liên quan | Pause, throughput, allocation pressure |
| JIT | `-XX:-TieredCompilation` hoặc cờ compiler khác nếu chủ động đặt | Warmup và inlining |
| CPU | `-XX:ActiveProcessorCount` nếu dùng | VM có thể ra quyết định theo số CPU active |
| Module/access | `--add-opens`, `--add-exports`, `--add-modules` | Đường truy cập reflection/MethodHandle |
| Hệ thống | `-D` properties, locale/charset nếu tác động workload | Hành vi thư viện và dữ liệu |
| Agent | `-javaagent`, profiler/coverage nếu có | Instrumentation thay đổi code được đo |

Không khuyến nghị bật/tắt ngẫu nhiên cờ tối ưu chỉ để cho ra kết quả đẹp. Đặc biệt, **so sánh hai JDK trên hai tập JVM flags khác nhau** là phép đo đồng thời của JDK và config, không phải riêng JDK. Nếu một flag không tồn tại trên một JDK, ghi rõ và thiết kế thí nghiệm thay thế thay vì lờ đi.

### 4.3. Lưu thông tin mà không làm lộ dữ liệu nội bộ

Command line hoặc VM args đôi khi chứa token, mật khẩu, URL nội bộ và absolute path. Khi công bố benchmark, **xóa/che giá trị bí mật** nhưng vẫn giữ ý nghĩa cấu hình (ví dụ `-Dservice.token=<redacted>`). Không gửi nguyên `-D` properties hoặc dump môi trường công ty ra nguồn công khai khi chưa kiểm tra.

Trong bản lưu nội bộ, cân nhắc chỉ cấp quyền truy cập cho người cần tái lập. Khi cần chứng minh kết quả, kết hợp fingerprint/hash của dữ liệu hoặc cấu hình với một nơi lưu an toàn thay vì đưa payload nhạy cảm vào báo cáo.

## 5. Ghi nhận phần cứng, OS, container và điều kiện máy

Ngay cả khi source và flag giống nhau, hai máy khác CPU hoặc hai lần chạy dưới tải khác nhau có thể cho phân phối kết quả khác nhau. “Máy 8 core” là thông tin quá ít.

### 5.1. Thông tin phần cứng tối thiểu

| Thuộc tính | Cần ghi |
| --- | --- |
| CPU | Tên model, vendor, kiến trúc, thế hệ/microarchitecture nếu xác định được |
| Core / thread | Số core vật lý, logical processors, SMT/hyper-threading có bật hay không |
| Tần số | Base/max theo thiết kế và trạng thái power management liên quan; không xem số GHz là tần số thực của mọi phép đo |
| Bộ nhớ | RAM khả dụng, topology/NUMA nếu workload nhạy cảm |
| Môi trường | Máy thật hay VM/cloud/container, giới hạn vCPU, RAM, quota |
| Hệ điều hành | Tên, phiên bản/build, kiến trúc, scheduler policy |
| Nguồn điện | AC/battery, power plan, CPU governor, turbo, mức throttling được quan sát |
| Tải nền | IDE, CI jobs, trình duyệt, antivirus, service khác có đang chiếm CPU/RAM hay không |

Không cần đo mọi thông số bằng thiết bị chuyên dụng cho một benchmark học tập. Nhưng nên **ghi rõ cái nào biết, cái nào chưa biết**, tránh bịa tần số CPU hay giả định một vCPU tương đương một core vật lý.

### 5.2. Linux: lệnh khảo sát môi trường

```bash
uname -a
lscpu
free -h
locale
```

Nếu hệ thống hỗ trợ CPU affinity và governor:

```bash
taskset -pc <PID_JVM_DANG_CHAY>
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
```

Lệnh `cat` có thể báo “No such file” trên VM/container hoặc CPU driver không cung cấp giao diện đó. Việc thiếu file **không** chứng minh CPU không có power management; ghi trạng thái “không truy xuất được”.

Trên Linux dùng cgroup v2, kiểm tra nếu có:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/memory.max
```

Những đường dẫn này không có trên mọi cấu hình cgroup. `cpu.max` có thể chứa quota/period hoặc `max`. Nếu benchmark trong container, ghi cả limits được áp dụng lẫn `Runtime.availableProcessors()` mà JVM nhìn thấy; chúng không nhất thiết phản ánh toàn bộ CPU vật lý của host.

### 5.3. Windows: lệnh khảo sát môi trường

Trong PowerShell:

```powershell
Get-CimInstance Win32_Processor |
    Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed

Get-CimInstance Win32_ComputerSystem |
    Select-Object Manufacturer, Model, TotalPhysicalMemory

Get-CimInstance Win32_OperatingSystem |
    Select-Object Caption, Version, BuildNumber

powercfg /getactivescheme
```

`MaxClockSpeed` và tên power plan là thông tin cấu hình, không phải đo tần số tức thời trong từng phép thử. Nếu kết quả thay đổi khi máy chuyển sang battery, lúc thermal throttling hoặc khi có tác vụ nền nặng, ghi nhận điều đó rồi chạy lại trong điều kiện kiểm soát hơn.

### 5.4. Kiểm soát điều kiện chạy trước mỗi trial

- Dùng cùng máy cho phép so sánh A/B ban đầu, khi có thể.
- Chọn power plan và điều kiện cấp nguồn nhất quán; tránh đo lần A khi máy mát và lần B khi CPU đang giảm xung do nhiệt.
- Không chạy đồng thời nhiều benchmark CPU-bound trên cùng host nếu chúng tranh tài nguyên.
- Ghi rõ số thread benchmark, affinity/CPU quota nếu đặt, và tránh hiểu nhầm `availableProcessors()` là số core vật lý.
- Nếu cần so sánh chéo máy, trình bày kết quả theo **từng cấu hình máy**; không gộp nanoseconds/op từ hai CPU khác nhau thành một số duy nhất.

Đừng tự động tắt turbo, SMT hay GC chỉ để “làm sạch kết quả”: thao tác như vậy đổi môi trường so với production. Nếu cần nghiên cứu các cờ này, coi mỗi lựa chọn là **một cấu hình thí nghiệm khác** và lưu chúng riêng.

## 6. Dữ liệu đầu vào: phần thường bị quên nhất của benchmark reflection

Tốc độ lời gọi phụ thuộc cả vào **phương thức được gọi** và **dữ liệu đưa vào**. Nếu đo `Method.invoke` với một String cố định nhưng đo `MethodHandle` với một nguồn dữ liệu thay đổi, đó không còn là phép so sánh công bằng.

### 6.1. Hợp đồng cho dataset

Một hồ sơ input nên có:

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| Loại dữ liệu | `ascii`, `vietnamese` | Nhận diện đường xử lý Unicode khác nhau |
| Kích thước | `16` / `256` UTF-16 code units | Tránh so đầu vào dài/ngắn khác nhau |
| Số phần tử | `1024` | Xác định working set |
| Seed | `123456789` | Có thể sinh lại cùng dữ liệu |
| Generator | Tên/phiên bản code tạo dữ liệu | Seed đơn lẻ chưa mô tả thuật toán |
| Tần suất | Phân phối đồng đều hoặc skewed | Ảnh hưởng cache/branch prediction |
| Kiểu receiver | Monomorphic hay polymorphic | Ảnh hưởng JIT dispatch/inlining |
| Method signature | `String prefix(String)` | Boxing, varargs và overload tạo chi phí khác |
| Kiểu giá trị đặc biệt | `null`, chuỗi rỗng, non-ASCII | Kiểm soát trường hợp ngoại lệ |
| Fingerprint | SHA-256 của dataset bytes đã chuẩn hóa | Phát hiện dữ liệu đầu vào lệch khỏi manifest |

Không chỉ lưu một mẫu `"hello"` rồi suy kết luận cho `String` dài 10 KB, cho `null`, primitive parameters hoặc phương thức ném exception. Nếu dữ liệu có nhiều trường hợp, dùng `@Param` để chạy thành **các nhóm kết quả khác nhau**.

### 6.2. Đảm bảo setup không bị tính vào phép đo

Những việc như:

- `Class.getMethod(...)`,
- tạo `MethodHandle`,
- gọi `setAccessible/trySetAccessible` nếu được phép,
- sinh mảng dữ liệu bằng random,
- đọc file fixture và tính checksum,

nên đặt ở `@Setup(Level.Trial)` **nếu mục tiêu là đo chi phí invocation ở trạng thái đã resolve**. Ngược lại, nếu production phải resolve method cho mỗi request, hãy có benchmark riêng đo **lookup + invoke** và nêu rõ khác biệt trong nhãn kết quả.

Không trộn “lookup mỗi lần” vào benchmark reflection, trong khi đối thủ MethodHandle được cache sẵn; điều đó so hai pipeline khác nhau chứ không chỉ phương thức gọi.

### 6.3. Seed chưa đủ: phải có fingerprint

Dùng random có seed cố định giúp tái tạo dữ liệu trong cùng generator. Nhưng nếu thay implementation generator, thuật toán, bảng ký tự hoặc bước chuẩn hóa, cùng seed vẫn có thể tạo dataset khác.

Ví dụ tính SHA-256 cho tập String:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

static String fingerprint(String[] inputs) throws Exception {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    for (String item : inputs) {
        byte[] bytes = item.getBytes(StandardCharsets.UTF_8);
        digest.update(ByteBuffer.allocate(Integer.BYTES)
                .putInt(bytes.length).array());
        digest.update(bytes);
    }
    return HexFormat.of().formatHex(digest.digest());
}
```

Thêm **độ dài byte của từng phần tử** trước payload để các tập dữ liệu khác nhau không trùng chỉ vì cách nối phần tử, ví dụ `["ab", "c"]` so với `["a", "bc"]`. Ghi fingerprint vào manifest theo cùng quy tắc serialization và thứ tự phần tử. Với dữ liệu nhạy cảm, lưu hash và mô tả phân phối thay vì công bố raw records.

## 7. Dùng JMH để đo reflection và MethodHandle theo cùng quy trình

[JMH](https://openjdk.org/projects/code-tools/jmh/) là công cụ chuyên đo Java microbenchmark. Các annotation giúp xác định warmup, measurement, fork, mode và tham số. Nó **không tự làm thí nghiệm trở nên đúng** nếu benchmark code thiếu tính tương đương hoặc dữ liệu không đại diện.

### 7.1. Ba đường gọi phải thực hiện cùng hành vi

Ví dụ so:

1. `direct` — lời gọi Java thông thường.
2. `reflection` — `Method.invoke` với `Method` đã resolve từ setup.
3. `methodHandle` — `MethodHandle.invokeExact` với handle đã resolve từ setup.

Cả ba gọi cùng `Target.prefix(String)` và nhận cùng `String`; không dùng target trả primitive ở một nhánh nhưng Object ở nhánh khác, vì boxing/unboxing có thể tạo độ lệch. Mã đích đủ nhỏ để thấy khác biệt đường gọi nhưng cũng có thể được JIT inline/optimize khác nhau; vì vậy **kết quả là hiệu năng của cấu hình benchmark này**, không phải hằng số overhead chung cho toàn bộ reflection.

### 7.2. Ví dụ JMH có tham số và seed cố định

Lưu class minh họa vào **source set của một dự án JMH đã cấu hình dependency và annotation processor**; nó không biên dịch chỉ với JDK thuần vì có import `org.openjdk.jmh.*`.

```java
package bench;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.util.SplittableRandom;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Fork(3)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
public class ReflectionCallBenchmark {
    @Param({"ascii", "vietnamese"})
    public String dataset;

    @Param({"16", "256"})
    public int length;

    @Param({"123456789"})
    public long seed;

    public static final class Target {
        public String prefix(String value) {
            return value.substring(0, 1);
        }
    }

    private Target target;
    private Method method;
    private MethodHandle handle;
    private String[] samples;
    private int cursor;

    @Setup(Level.Trial)
    public void setup() throws Throwable {
        target = new Target();
        method = Target.class.getMethod("prefix", String.class);
        handle = MethodHandles.lookup().findVirtual(
                Target.class, "prefix",
                MethodType.methodType(String.class, String.class));

        SplittableRandom random = new SplittableRandom(seed);
        samples = new String[1024];
        char[] vietnamese = {'ă', 'â', 'đ', 'ê', 'ộ', 'ú'};

        for (int i = 0; i < samples.length; i++) {
            StringBuilder text = new StringBuilder(length);
            for (int j = 0; j < length; j++) {
                if ("ascii".equals(dataset)) {
                    text.append((char) ('a' + random.nextInt(26)));
                } else if ("vietnamese".equals(dataset)) {
                    text.append(vietnamese[random.nextInt(vietnamese.length)]);
                } else {
                    throw new IllegalArgumentException(dataset);
                }
            }
            samples[i] = text.toString();
        }

        // Kiểm tra correctness trước khi benchmark được đo.
        String input = samples[0];
        String expected = target.prefix(input);
        String reflective = (String) method.invoke(target, input);
        String viaHandle = (String) handle.invokeExact(target, input);
        if (!expected.equals(reflective) || !expected.equals(viaHandle)) {
            throw new AssertionError("Ba đường gọi không tương đương");
        }
    }

    private String nextInput() {
        return samples[(cursor++) & (samples.length - 1)];
    }

    @Benchmark
    public String direct() {
        return target.prefix(nextInput());
    }

    @Benchmark
    public String reflection() throws Exception {
        return (String) method.invoke(target, nextInput());
    }

    @Benchmark
    public String methodHandle() throws Throwable {
        return (String) handle.invokeExact(target, nextInput());
    }
}
```

**Giải thích thiết kế:**

- `@State(Scope.Thread)` tách trạng thái và con trỏ input theo thread, tránh vô tình đo lock contention.
- `@Param` tạo các tổ hợp dataset/kích thước riêng, không trộn kết quả ASCII và tiếng Việt thành một trung bình duy nhất.
- `seed` được khai báo thành benchmark parameter để xuất hiện trong tên/tham số kết quả; dữ liệu tạo trong `@Setup` không thuộc vùng đo.
- Cả ba benchmark lấy input qua cùng `nextInput()` và gọi cùng receiver/method logic.
- Return value của `@Benchmark` được JMH harness xử lý để tránh việc bỏ hoàn toàn kết quả không được dùng; không cần `System.out.println` trong đường đo.
- Handle có signature `(Target, String)String` nên `invokeExact` phải dùng đúng kiểu receiver, argument và return tại call site.
- `Target.prefix` chỉ đọc ký tự đầu và không xử lý emoji/surrogate; dataset được giới hạn ở ASCII và các ký tự tiếng Việt BMP nên mọi sample đều không rỗng và có ký tự đầu hợp lệ.

Bài đo **chi phí đường gọi ở trạng thái đã resolve** cùng với chi phí logic `prefix`. Đừng dùng nó để kết luận “MethodHandle luôn nhanh hơn reflection” hoặc “direct luôn rẻ hơn N lần” trên mọi JDK/call site; hãy lấy phân phối thực đo và kiểm tra các giả thuyết.

### 7.3. Các giới hạn phải nêu khi công bố kết quả

Dù setup tương đồng, JIT có thể inline `direct` khác với `reflection` hoặc `methodHandle`; điều này là một phần của hành vi thực tế dưới workload cụ thể. `String.substring` có thể tạo allocation hoặc được tối ưu; nếu hiệu năng logic đích lấn át chi phí gọi, sự khác biệt đường gọi sẽ bị che.

Ngoài benchmark latency cho invocation đã cache, ứng dụng có thể cần benchmark riêng cho:

- Lookup lặp lại (`getMethod`, `findVirtual`) so với lookup cache.
- Polymorphic receiver và phân phối method khác nhau.
- Primitive return/argument khiến reflection boxing/unboxing.
- Kích thước payload thực tế và logic target nặng hơn.
- Access/module configuration tương ứng môi trường triển khai.
- Exception path khi method ném lỗi hoặc argument sai.

Không so trực tiếp một score `ns/op` của benchmark “lookup + invoke” với score của benchmark “invoke đã resolve” và gọi đó là chi phí reflection thuần túy.

## 8. Chạy JMH và lưu kết quả gốc

### 8.1. Chuẩn bị bộ benchmark

JMH cần dependency `jmh-core` và annotation processor `jmh-generator-annprocess`, hoặc dự án tạo bằng JMH archetype/Gradle plugin có cấu hình tương đương. Pin **phiên bản JMH đã thử nghiệm** trong build file, lưu version đó vào manifest và bảo đảm code sinh từ annotation processor được đưa vào artifact benchmark.

Ví dụ ở mục 7 phải được đặt trong **một dự án JMH đang hoạt động**, không phải chỉ chạy `javac ReflectionCallBenchmark.java` bằng JDK thuần rồi kỳ vọng các annotation JMH có sẵn. Lưu source commit và build command đã tạo benchmark JAR.

Ví dụ giả sử dự án tạo executable `target/benchmarks.jar`:

```bash
java -jar target/benchmarks.jar ".*ReflectionCallBenchmark.*" \
    -f 3 -t 1 -wi 5 -w 1s -i 8 -r 1s \
    -rf json -rff results-reflection.json
```

Trong Windows PowerShell, gõ lệnh trên một dòng, không dùng dấu `\` để tiếp tục dòng như Bash:

```powershell
java -jar target/benchmarks.jar ".*ReflectionCallBenchmark.*" -f 3 -t 1 -wi 5 -w 1s -i 8 -r 1s -rf json -rff results-reflection.json
```

Các cờ JMH chính:

| Cờ | Ý nghĩa |
| --- | --- |
| `-f 3` | Ba JVM **fork** cho mỗi benchmark case |
| `-t 1` | Một JMH worker thread; giữ workload single-thread |
| `-wi 5`, `-w 1s` | Năm warmup iterations, mỗi iteration khoảng một giây |
| `-i 8`, `-r 1s` | Tám measurement iterations, mỗi iteration khoảng một giây |
| `-rf json` | Xuất định dạng kết quả JSON |
| `-rff results-reflection.json` | Chỉ định đường dẫn output result |
| `-jvm <path-to-java>` | Dùng Java executable cụ thể cho JVM benchmark fork (nếu cần) |

`@Fork`, `@Warmup` và `@Measurement` trong source cũng mô tả mặc định; khi dùng tùy chọn CLI, hãy giữ cấu hình thực tế từ **log lệnh đã chạy** và báo cáo JMH. Không suy luận từ source annotation khi CLI đã override nó.

Nếu so sánh hai JDK, chạy cùng artifact và cùng JMH options bằng đường `-jvm` trỏ tới từng Java executable; lưu hai JSON riêng biệt, không ghi đè file của lần trước. Nếu target JDK không chạy được bytecode hoặc dependency trong JAR, cần build một artifact tương thích đã được cố định — không bí mật thay code giữa hai lần chạy.

### 8.2. JVM arguments cho fork phải được ghi rõ

Nếu chủ đích kiểm tra fixed heap cho mọi JMH fork, một cách làm rõ là cấu hình tại annotation:

```java
@Fork(value = 3, jvmArgsAppend = {"-Xms1g", "-Xmx1g"})
```

Dòng này là **biến thể** thay cho `@Fork(3)` của ví dụ, không phải annotation bổ sung lên cùng một class. Bạn cũng có thể dùng cấu hình JMH CLI tương đương nếu harness cho phép. Điều quan trọng là ghi đúng arguments mà JVM fork nhận được.

Không đánh đồng `-Xms1g -Xmx1g` ở shell **cha** với heap của mỗi JVM **con** do JMH fork. Hãy xác minh JMH log/VM args trong fork. Khi cấu hình khác nhau giữa hai JDK, tách riêng phép so sánh “JDK + flags” với phép so sánh “chỉ JDK”.

### 8.3. Đừng đo bằng wall clock bao quanh toàn bộ JMH run

Thời gian từ lúc chạy command đến khi kết thúc bao gồm startup VM, compile benchmark, warmup, fork, đo và ghi báo cáo. Nó **không** phải latency của một lần gọi reflection.

Hãy đọc `Mode.AverageTime` và đơn vị `ns/op` của từng case trong JMH. Nếu workload được phân nhóm bằng `@Param`, mỗi tổ hợp `dataset`/`length`/`seed` phải có metric riêng.

### 8.4. Thu thập thêm allocation/GC khi cần

JMH có profiler `gc` để quan sát số liệu GC và allocation trong cấu hình được hỗ trợ:

```bash
java -jar target/benchmarks.jar ".*ReflectionCallBenchmark.*" \
    -f 3 -t 1 -wi 5 -w 1s -i 8 -r 1s \
    -prof gc -rf json -rff results-reflection-gc.json
```

Nếu profiler/instrumentation làm thay đổi phép đo, lưu kết quả có profiler thành **một run riêng**; không gộp nhầm với run baseline không profiler. Chỉ so sánh metric allocation hoặc GC khi profiler có hỗ trợ trên JDK/OS đang dùng và đọc đúng đơn vị của nó.

## 9. Manifest tối thiểu cho một thí nghiệm có thể tái lập

Một file báo cáo JMH có điểm số và một số thông tin VM, nhưng **không thay thế** bản ghi source revision, phần cứng, chính sách nguồn điện, container quota và fingerprint của input. Hãy lưu thêm một manifest trong thư mục kết quả benchmark của dự án.

Ví dụ cấu trúc YAML **mẫu để điền số liệu thật** (không phải kết quả đã chạy):

```yaml
schema: reflection-benchmark-record-v1

experiment:
  id: "run-001"
  timestampUtc: "<ISO-8601 UTC>"
  purpose: "Direct vs Method.invoke vs MethodHandle.invokeExact"
  notes: "<tải nền, điều kiện máy, giả thuyết>"

source:
  repositoryRevision: "<git commit SHA>"
  workingTreeClean: "<true | false>"
  benchmarkClass: "bench.ReflectionCallBenchmark"
  jmhVersion: "<version pinned trong build>"
  buildCommand: "<lệnh build thật>"
  artifactSha256: "<checksum của benchmark JAR>"

jdk:
  javaExecutable: "<path Java dùng bởi JMH fork>"
  javaVersion: "<java.version>"
  runtimeVersion: "<java.runtime.version>"
  vendor: "<java.vendor>"
  vmName: "<java.vm.name>"
  vmVersion: "<java.vm.version>"

jvm:
  forkJvmArguments: ["<các JVM args thực tế>"]
  effectiveGc: "<GC đã được chọn>"
  effectiveHeapMinBytes: "<giá trị thực tế>"
  effectiveHeapMaxBytes: "<giá trị thực tế>"
  otherRelevantFlags: ["<flag=value>"]

system:
  osName: "<tên>"
  osVersion: "<version/build>"
  osArch: "<kiến trúc>"
  cpuModel: "<model>"
  physicalCores: "<số core hoặc unknown>"
  logicalProcessors: "<số logical CPU>"
  availableProcessorsInJvm: "<giá trị Runtime.availableProcessors()>"
  ramBytes: "<RAM>"
  containerOrVm: "<none | thông tin giới hạn>"
  cpuAffinity: "<CPU set hoặc default>"
  powerPlanOrGovernor: "<giá trị hoặc unknown>"
  backgroundLoad: "<mô tả>"

dataset:
  generatorRevision: "<commit chứa code sinh dữ liệu>"
  seed: 123456789
  alphabet: ["ascii", "vietnamese"]
  lengthsUtf16: [16, 256]
  samplesPerCase: 1024
  datasetSha256: "<hash theo quy tắc serialization đã mô tả>"
  receiverDistribution: "monomorphic Target"
  invocationSignature: "String prefix(String)"

measurement:
  mode: "AverageTime"
  unit: "ns/op"
  forks: 3
  threads: 1
  warmupIterations: 5
  warmupTime: "1s"
  measurementIterations: 8
  measurementTime: "1s"
  resultFile: "results-reflection.json"
```

Các chuỗi `<...>` là **placeholder**, không phải số đo hoặc giá trị mà bạn được phép tự bịa. Khi tạo report thật, điền dữ liệu lấy từ JVM và máy chạy. Nếu metadata chưa thu thập được, ghi `unknown` hoặc `not recorded`, không tự suy ra từ tên máy.

### 9.1. Một run nên có những artifact nào?

| Artifact | Dùng để |
| --- | --- |
| `manifest.yaml` (hoặc JSON) | Định danh mã, runtime, hardware, data và điều kiện chạy |
| `results-reflection.json` | Score JMH, unit, error/chi tiết phép đo theo phiên bản JMH |
| Console log JMH | JVM args, JMH options, fork progress, cảnh báo |
| Output `java -version` | Định danh executable, vendor và build |
| Output effective flag | Xác nhận GC/heap/JIT khi cần |
| Input fingerprint | Phát hiện lệch dữ liệu so với baseline |
| Commit/tag hoặc source archive | Cho phép build lại đúng benchmark |

Trong hệ thống lưu trữ artifacts, nên đặt chúng chung theo `experiment.id` hoặc timestamp, ví dụ mỗi run có một thư mục riêng. Đừng chỉ giữ ảnh chụp biểu đồ mà xóa log/JSON thô; khi cần phân tích outlier hoặc đổi phương pháp thống kê, dữ liệu gốc có giá trị hơn ảnh.

### 9.2. Truy vết bản JDK đang thực sự đo

Một lỗi thường gặp là lưu `java -version` từ terminal cha, nhưng JMH dùng Java executable khác khi fork. Có thể ghi nhận đầy đủ:

- `java -version` của shell/build.
- `-jvm` hoặc đường Java executable được JMH chọn.
- Output `java.version`, `java.vm.version` và VM arguments trong benchmark fork (từ log/harness hoặc snapshot gắn với đúng fork).
- Hash của artifact benchmark dùng trong lần chạy.

Với CI runner, giữ thêm image ID/digest của container hoặc cấu hình máy ảo nếu có. Chỉ ghi “Ubuntu latest” hoặc “JDK latest” không đủ để lặp lại sau khi image/tag thay đổi.

## 10. Cách đọc số liệu và so sánh hai bản JDK

### 10.1. Không so sánh chéo case

Ví dụ JMH trả score cho bốn tập dữ liệu:

| Benchmark | Dataset | Length | Unit |
| --- | --- | --- | --- |
| `direct` | `ascii` | 16 | `ns/op` |
| `reflection` | `ascii` | 16 | `ns/op` |
| `methodHandle` | `ascii` | 16 | `ns/op` |
| `reflection` | `vietnamese` | 256 | `ns/op` |

Chỉ so `direct`, `reflection` và `methodHandle` **trong cùng tổ hợp** `dataset/length/seed/JDK/flags/hardware/threads`. Hàng `reflection` ở `vietnamese/256` không là đối chứng hợp lệ cho `direct` ở `ascii/16`.

### 10.2. Hiệu số, tỷ số và độ không chắc chắn

Nếu score trung bình lần A là `a` ns/op và B là `b` ns/op trong cùng case, có thể mô tả:

- **Chênh lệch tuyệt đối:** `b - a` ns/op.
- **Tỷ số:** `b / a`, với điều kiện `a > 0`.
- **Phần trăm thay đổi:** `100 × (b - a) / a` %.

Những phép tính này có ý nghĩa mô tả, **không tự chứng minh** khác biệt là đáng tin cậy. Cần xem spread giữa iterations/forks, error interval mà JMH báo, outliers và các lần chạy độc lập. Đừng khẳng định thắng thua chỉ vì hai số làm tròn khác nhau hoặc khoảng tin cậy được diễn giải không đúng.

### 10.3. Kiểm tra độ ổn định của fork và warmup

- Nếu kết quả warmup còn xu hướng tăng/giảm mạnh ở cuối giai đoạn, thời gian warmup có thể chưa đủ.
- Nếu các fork cho phân bố rất khác, xem GC, code cache/JIT, CPU frequency, affinity, tải nền hoặc dữ liệu.
- Nếu kích thước sample quá nhỏ và phương thức target cực ngắn, chi phí harness/input selection có thể chiếm tỷ trọng đáng kể.
- Nếu score thay đổi rõ khi bật profiler hoặc thêm log, điều đó cho thấy instrumentation làm thay đổi workload đo.
- Nếu benchmark chỉ chạy một fork, không nên khẳng định sự ổn định giữa các JVM khởi tạo độc lập.

Dùng warmup nhiều hơn khi workload thực tế có trạng thái JIT ổn định chậm, nhưng phải **ghi lại** cấu hình mới. Không thay thời gian warmup sau khi nhìn kết quả rồi chỉ công bố run đẹp nhất.

### 10.4. So sánh JDK 18 và JDK hiện đại

Java 18 có [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416), thay đổi triển khai nền của core reflection. Do đó, việc đo `Method.invoke`, `MethodHandle` và direct call giữa các JDK có thể chịu ảnh hưởng cách runtime hiện thực hóa reflection và tối ưu call site. Đây là lý do nên benchmark **JDK đang triển khai**, không suy từ một con số của JDK 18.

Ngay trên cùng một JDK, `Method` được giữ trong một trường `static final` có thể được JIT tối ưu khác với `Method` lưu trong một field thông thường hoặc được lookup mỗi lần. Nếu production sử dụng một kiểu cache/call site khác ví dụ JMH, hãy thêm benchmark đại diện cho chính kiểu đó trước khi đưa ra quyết định.

Để đánh giá khác biệt giữa các JDK:

1. Cố định commit, dataset fingerprint, JMH version và artifact build khi tương thích.
2. Chạy các fork bằng `-jvm` trỏ tới JDK A, lưu manifest/JSON A.
3. Chạy bằng JDK B trên cùng máy và cấu hình tương đương, lưu manifest/JSON B.
4. Kiểm tra effective flags (GC, heap, tiered compilation) và ghi những khác biệt mặc định không thể tránh.
5. Lặp lại theo nhiều đợt; nếu cần giảm ảnh hưởng drift thời gian, xen kẽ run A/B ở cùng điều kiện máy thay vì luôn chạy toàn bộ A rồi mới B.
6. So sánh từng case cùng seed/length/dataset và mô tả bất định; không tuyên bố mọi reflection workload được cải thiện chỉ từ một microbenchmark.

Nếu mục tiêu là so **default configuration** của mỗi JDK thì giữ flag mặc định và ghi rõ đây là phép so “JDK với default riêng”. Nếu mục tiêu là cô lập ảnh hưởng runtime/JIT, thử cấu hình các flag tương đương khi được cả hai JDK hỗ trợ và ghi rõ những điểm không thể tương đương. Hai câu hỏi đó khác nhau và không nên trộn kết luận.

## 11. Những cách benchmark sai dễ tạo kết luận giả

### 11.1. Tự đo một lần bằng System.nanoTime

Ví dụ sau không phải microbenchmark đáng tin cậy:

```java
long start = System.nanoTime();
method.invoke(target, input);
long elapsed = System.nanoTime() - start;
```

Nó đo cả overhead đồng hồ, thiếu warmup và không có thống kê. Một phép gọi có thể bị JIT/GC/scheduler ảnh hưởng mạnh. `System.nanoTime()` rất hữu ích cho đo thời gian trong ứng dụng ở mức thích hợp, nhưng không thay JMH khi cần so sự khác biệt vài ns/op của invocation path.

### 11.2. Thay đổi dataset hoặc logic đích giữa hai nhánh

Đo reflection với input có ký tự Unicode, còn direct với chuỗi ASCII là thiếu kiểm soát. Đo target trả `int` rồi so với target trả `String` cũng kéo thêm chi phí boxing vào một phía. Với MethodHandle, `invoke` và `invokeExact` có hợp đồng chuyển đổi kiểu khác nhau; hãy ghi rõ API đang đo thay vì chỉ ghi “MethodHandle”.

### 11.3. Dead-code elimination và constant folding

Nếu result không được dùng, compiler/JIT có thể tối ưu bỏ phép tính. Ngược lại, input là một constant biết sẵn có thể cho phép compiler tính trước kết quả. JMH hỗ trợ tiêu thụ return value hoặc `Blackhole`; thêm dataset động nhưng có seed giúp giảm nguy cơ benchmark đo một đường tối ưu phi thực tế.

Việc JIT inline là một phần của performance Java; không mặc định tắt JIT để “công bằng”. Hãy chọn workload gần với production và phân tích hành vi tối ưu hóa.

### 11.4. Đổi môi trường khi đang so sánh

Một phía chạy trên pin, phía kia cắm nguồn; một phía có antivirus quét, phía kia không; một phía nằm trong container có CPU quota, phía kia chạy host — mỗi tình huống đều làm kết luận thiếu căn cứ. Khi không kiểm soát được hoàn toàn, ghi lại và diễn giải chênh lệch thận trọng.

### 11.5. Lấy kết quả tốt nhất làm kết quả đại diện

Chọn một fork có score đẹp nhất sẽ giấu biến động hệ thống. Hãy giữ tất cả kết quả theo fork/iteration ở mức JMH cung cấp, nêu rõ phép tổng hợp đã dùng và không loại outlier tùy tiện sau khi nhìn ra hướng kết quả mong muốn.

## 12. Checklist để người khác có thể chạy lại

Trước khi dùng kết quả microbenchmark làm bằng chứng cho một quyết định hiệu năng, hãy xác nhận:

- [ ] Có commit/tag và trạng thái working tree, phiên bản JMH và hash artifact benchmark.
- [ ] Có Java executable thực sự chạy **JMH fork**, đầy đủ vendor/runtime version/VM version.
- [ ] Có launch command, arguments của JVM benchmark và các effective flags quan trọng (heap, GC, compiler/module) đã đối chiếu.
- [ ] Có OS build, kiến trúc, model CPU, số logical processor, RAM và mô tả VM/container/CPU quota nếu có.
- [ ] Có ghi nhận nguồn điện, power plan/governor/affinity và tải nền hoặc giới hạn kiểm soát.
- [ ] Có mô tả đầy đủ input generator, seed, `@Param`, số lượng, length, phân phối và fingerprint.
- [ ] Có kiểm tra correctness cho ba đường gọi trước khi đo.
- [ ] Có mode, unit, threads, forks, warmup và measurement đầy đủ.
- [ ] Có console log, JMH result JSON và manifest cùng ID của một run.
- [ ] Không trộn benchmark case khác dataset, target logic, JDK, CPU hoặc flags.
- [ ] Không chỉ báo một số trung bình; đã xem biến động và giới hạn của kết quả.
- [ ] Dữ liệu nhạy cảm đã được che trước khi gửi artifact ra ngoài nhóm.

Một quy tắc đơn giản: nếu người khác nhận bảng score nhưng **không biết dùng JDK nào, JVM nào, CPU nào và dataset nào**, kết quả chưa đủ để tái lập hoặc tranh luận về nguyên nhân.

### 12.1. Mẫu tóm tắt run dành cho review

Có thể thêm một đoạn mô tả ngắn vào báo cáo:

> Benchmark `ReflectionCallBenchmark` tại commit `<commit>`, chạy với JMH `<version>` trên `<JDK vendor/version/build>`, VM `<name/version>`, máy `<CPU/OS>`; `3` forks, `1` thread, `5` warmup iterations và `8` measurement iterations. Input được sinh từ seed `123456789` theo các case `ascii`/`vietnamese`, length `16`/`256` với dataset fingerprint ghi trong manifest. Toàn bộ JVM flags và kết quả `ns/op` nằm trong artifacts của run; phép so sánh chỉ áp dụng cho đúng workload/điều kiện đó.

Các placeholder phải được thay bằng **dữ liệu thật**. Mẫu này tạo bối cảnh tối thiểu cho người review; manifest và JSON mới là bằng chứng chi tiết.

## 13. Bài thực hành có tiêu chí kiểm chứng

### Bài A — xác định hai JDK không chỉ bằng major version

Chọn hai bản JDK mà dự án được phép dùng. Chạy `java -version` và `javac -version`, ghi đầy đủ vendor/build và executable path. So sánh hai môi trường có cùng major version nhưng khác patch/vendor nếu có; giải thích vì sao ghi “Java 21” chưa đủ.

**Đạt khi:** có đủ thông tin để chọn lại đúng runtime và biết phiên bản nào là compile toolchain, phiên bản nào chạy benchmark fork.

### Bài B — VM arguments có thật trong fork

Chạy một benchmark JMH với heap mặc định, rồi một run khác cố định `-Xms`/`-Xmx` cho fork. Ghi nhận command, arguments, GC và các flags hiệu lực có thể kiểm tra; không chỉ thay heap của process khởi chạy JMH.

**Đạt khi:** biết xác nhận flag ở đúng tiến trình đo và gắn mỗi cấu hình với một manifest/result JSON riêng.

### Bài C — đổi dataset, giữ nguyên method

Dùng `ReflectionCallBenchmark` với `ascii`/`vietnamese` và `length=16`/`256`. Giữ target method, forks, threads và JDK không đổi. Sinh lại input bằng cùng seed và kiểm tra fingerprint.

**Đạt khi:** các nhóm case được tách rõ; bạn không dùng score của `ascii/16` làm baseline cho `vietnamese/256`.

### Bài D — so lookup với invoke đã resolve

Tạo một benchmark riêng thực hiện `Target.class.getMethod("prefix", String.class)` trong vùng đo, và một benchmark khác dùng `Method` đã cache từ setup. Cả hai phải gọi cùng target và dùng cùng input. Đặt tên biểu thị rõ `lookupPlusInvoke` với `cachedInvoke`.

**Đạt khi:** giải thích được rằng số đo thêm lookup không thể được diễn giải là overhead riêng của `Method.invoke`.

### Bài E — xem biến động giữa forks

Chạy cùng case nhiều lần, lưu nguyên JSON. So sánh mean, spread giữa forks và các điều kiện CPU/OS. Nếu kết quả không ổn định, ghi nhận giả thuyết (throttling, GC, warmup, scheduler) và chạy lại sau khi kiểm soát đúng một biến.

**Đạt khi:** không chọn fork đẹp nhất để báo cáo và có thể mô tả độ không chắc chắn.

### Bài F — tạo hồ sơ tái lập hoàn chỉnh

Với một run hoàn tất, cung cấp:

- Source commit + build artifact fingerprint.
- JMH command và bộ options thực tế.
- JDK/VM version + JVM args/effective flags quan trọng.
- CPU/OS/limits và điều kiện tải.
- Dataset generator, seed, parameters + hash.
- Log và `results-reflection.json`.

Đưa hồ sơ cho người khác chạy lại trên cùng loại môi trường. Nếu kết quả khác, kiểm tra **các biến cấu hình và phân phối** trước khi kết luận một JDK hay một API chậm hơn.

**Tiêu chí hoàn thành toàn bài:** bạn không chỉ tạo được score JMH cho `Method.invoke`, `MethodHandle.invokeExact` và direct call, mà còn có một hồ sơ kiểm tra được mô tả **ai đã đo, trên runtime/VM nào, bằng flag nào, trên phần cứng nào, với dữ liệu gì và bằng quy trình nào**. Đây là tiêu chuẩn làm việc có ích lâu dài trên JDK hiện đại; không lệ thuộc vào một kết luận tốc độ đã cũ.

### Tài liệu tham khảo

- [JMH — OpenJDK Code Tools](https://openjdk.org/projects/code-tools/jmh/): công cụ, annotation và mục tiêu đo Java microbenchmark.
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi nền của core reflection từ Java 18 và tác động cần kiểm chứng bằng phép đo.
- [Java SE RuntimeMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/RuntimeMXBean.html): `getInputArguments()` và metadata JVM.
- [Java SE Runtime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html): `availableProcessors()` và thông tin runtime.
- [Java launcher — Java SE](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-X`, `-XX` và các tùy chọn khởi động.
- [Java SE Method](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html): hợp đồng `Method.invoke`.
- [Java SE MethodHandle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact` và kiểu của call site.
- [Java SE MessageDigest](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/MessageDigest.html): SHA-256 để kiểm chứng fingerprint dữ liệu hoặc artifact.
