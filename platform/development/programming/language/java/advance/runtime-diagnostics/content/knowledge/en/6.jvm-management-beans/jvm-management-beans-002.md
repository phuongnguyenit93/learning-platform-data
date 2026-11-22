# 6.2 RuntimeMXBean: uptime, thông tin VM và đối số đầu vào

Khi một dịch vụ Java xảy ra lỗi, câu hỏi đầu tiên thường là **“JVM nào đang chạy, đã chạy bao lâu, được khởi động với những tham số gì?”**. Một container có thể đã restart nhưng tên pod vẫn như cũ; một lần deploy có thể dùng JDK khác dự kiến; một thay đổi `-Xmx` có thể chưa đến được tiến trình. `java.lang.management.RuntimeMXBean` cung cấp dữ liệu trực tiếp từ **JVM hiện tại** để kiểm tra các giả thuyết này.

Bài học thuộc nhóm **MXBeans cho runtime diagnostics**. Trọng tâm là cách lấy, hiểu và sử dụng đúng `getUptime()`, `getStartTime()`, thông tin implementation/specification, `getInputArguments()`, process identity, classpath và system properties; phân biệt thông tin chắc chắn với thông tin chỉ xấp xỉ; kiểm soát dữ liệu nhạy cảm; và đối chiếu với công cụ JVM/OS.

**Sau bài học, bạn có thể:**

- Sử dụng `ManagementFactory.getRuntimeMXBean()` trong Java 17+.
- Phân biệt JVM uptime với thời gian hệ điều hành đã chạy, thời lượng request, wall-clock time và các lần restart.
- Đọc đúng `getVmName()`/`getVmVersion()`, VM specification, management spec và PID.
- Hiểu chính xác `getInputArguments()` thể hiện gì, đặc biệt nó **không chứa đối số gửi tới `main`** và **không nhất thiết phản ánh toàn bộ command line của launcher**.
- Thu thập một bản ghi runtime đã chọn lọc, tránh lộ secret; truy cập cùng dữ liệu qua platform MBeanServer/JMX khi thích hợp.
- Chọn bằng chứng để xác minh sự khác nhau giữa cấu hình mong muốn và cấu hình JVM thực tế.

## 1. RuntimeMXBean là gì và lấy ở đâu?

`RuntimeMXBean` là interface quản lý runtime của Java Virtual Machine, nằm trong module `java.management`, package `java.lang.management`. Mỗi JVM có một MXBean quản lý runtime tương ứng.

Cách lấy trong cùng tiến trình:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;

RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
```

Đây là đoạn mã đặt trong method hoặc initializer, không phải chương trình có `main` độc lập. Lời gọi là truy vấn runtime **của tiến trình Java đang chạy đoạn mã này**, chứ không tự kết nối đến một PID khác.

Để truy cập dưới dạng JMX, MXBean này được đăng ký trong platform MBeanServer với `ObjectName`:

```text
java.lang:type=Runtime
```

Có thể lấy tên qua `runtime.getObjectName()` hoặc hằng `ManagementFactory.RUNTIME_MXBEAN_NAME`. Với ứng dụng quản trị, `MBeanServerConnection` đến JVM đích có thể tạo proxy `RuntimeMXBean`, nhưng quyền truy cập, xác thực và kết nối JMX phải được cấu hình an toàn.

### 1.1. Những dữ liệu RuntimeMXBean cung cấp

| Nhóm | API chính | Ý nghĩa |
| --- | --- | --- |
| **Thời gian** | `getStartTime()` | Epoch milliseconds biểu diễn thời điểm JVM bắt đầu **xấp xỉ** |
| | `getUptime()` | Số mili giây JVM đã hoạt động |
| **Danh tính JVM** | `getPid()`, `getName()` | PID của tiến trình và chuỗi tên do implementation quyết định |
| **VM implementation** | `getVmName()`, `getVmVendor()`, `getVmVersion()` | Tên, vendor, phiên bản của triển khai VM |
| **VM specification** | `getSpecName()`, `getSpecVendor()`, `getSpecVersion()` | Thông tin specification mà VM tuân theo |
| **Management** | `getManagementSpecVersion()` | Phiên bản specification quản lý của VM |
| **Đối số JVM** | `getInputArguments()` | Danh sách argument chuyển tới VM, **khác** `main(args)` |
| **Đường dẫn** | `getClassPath()`, `getLibraryPath()` | Java system class path và Java native library path |
| **Bootstrap path** | `isBootClassPathSupported()`, `getBootClassPath()` | Chỉ có ý nghĩa nếu VM hỗ trợ cơ chế boot class path |
| **Properties** | `getSystemProperties()` | Bản đồ các Java system properties có key/value là String |
| **JMX identity** | `getObjectName()` | `java.lang:type=Runtime` |

RuntimeMXBean chủ yếu cung cấp **metadata và thời gian**, không phải tất cả hiệu năng của JVM. Nếu câu hỏi là CPU utilization, thread deadlock, heap sau GC hoặc collection pause, hãy dùng lần lượt MXBean khác, JFR, GC logs hay công cụ phù hợp; không suy đoán chúng từ một số `getUptime()`.

## 2. Đọc uptime và start time đúng ngữ nghĩa

### 2.1. `getUptime()` tính bằng mili giây, reset theo JVM

`runtime.getUptime()` trả kiểu `long`, đơn vị **milliseconds**, tính thời lượng JVM đang chạy kể từ khi khởi động. Ví dụ `905_400L` tương đương 15 phút 5,4 giây. Đây là **JVM uptime**, không phải:

- uptime của node/host hoặc Linux `/proc/uptime`;
- tuổi của container, pod hay thời gian tính từ khi Deployment được tạo;
- thời gian một request, session hoặc một job bắt đầu;
- số nanoseconds từ `System.nanoTime()`;
- tổng thời gian JVM từng chạy qua các lần restart.

Một pod giữ tên hoặc workload identity nhưng container/JVM restart sẽ khiến uptime của **JVM mới** bắt đầu lại từ mức nhỏ. Một PID cũng có thể được tái sử dụng ở lần chạy khác; đừng dùng PID đơn lẻ làm danh tính không đổi theo thời gian.

Nếu đọc uptime định kỳ, bạn có thể thấy giá trị tăng qua mỗi mẫu. Nếu nó **giảm đột ngột** trong cùng chuỗi monitoring, cần kiểm tra có phải series đã chuyển sang JVM khác, process restart, PID reuse, thay đổi nhãn mục tiêu hay collector nối nhầm nguồn. Uptime giảm không đủ để khẳng định crash nếu chưa có identity của tiến trình.

### 2.2. `getStartTime()` là thời điểm JVM start **xấp xỉ**

`runtime.getStartTime()` cũng trả kiểu `long` nhưng là **epoch milliseconds**, không phải uptime. Đổi thành instant:

```java
import java.time.Instant;

Instant approximateJvmStart =
        Instant.ofEpochMilli(runtime.getStartTime());
```

Theo API, kết quả là **thời điểm xấp xỉ** JVM bắt đầu. Không nên mô tả nó là nano giây chính xác tuyệt đối. Thời gian của process launcher, thời điểm JVM được tạo và thời gian ứng dụng bắt đầu phục vụ traffic có thể khác nhau.

Cũng không nên coi:

```text
getStartTime() + getUptime() == System.currentTimeMillis()
```

là một đẳng thức luôn đúng ở mức mili giây. Các lệnh được gọi ở những thời điểm khác nhau; start time là xấp xỉ; wall clock có thể được NTP điều chỉnh, và độ phân giải/semantics của các đồng hồ không giống nhau. Hãy ghi lại cả thời điểm **lấy mẫu** nếu cần so theo thời gian.

### 2.3. Chuyển đơn vị để hiển thị

Ví dụ với `getUptime() = 905400`:

```text
905400 milliseconds
= 905.4 seconds
= 15 minutes + 5 seconds + 400 milliseconds
```

Trong Java:

```java
long uptimeMs = runtime.getUptime();
long minutes = uptimeMs / 60_000;
long remainingSeconds = (uptimeMs % 60_000) / 1_000;
long remainingMs = uptimeMs % 1_000;
```

Đây là snippet đặt trong code có biến `runtime`; giá trị thật phụ thuộc JVM tại lúc đọc. Dùng `Duration.ofMillis(uptimeMs)` nếu cần biểu diễn duration theo API thời gian Java. Không gắn timestamp hoặc timezone vào **duration**: 15 phút uptime vẫn là 15 phút ở mọi múi giờ.

### 2.4. Dùng start time và uptime để ghép timeline

Giả sử một hệ thống ghi JVM start xấp xỉ `2026-10-29T08:00:00Z` và một sự kiện ở JVM uptime `225_600 ms`. Ta có thể ước lượng:

```text
estimated_event_utc = approximate_jvm_start_utc + event_uptime_ms

2026-10-29T08:00:00Z + 225600 ms
= 2026-10-29T08:03:45.600Z
```

Đây là phép ghép **mốc gốc của cùng một JVM**. Nó cần đúng process instance và mang theo uncertainty của start time và đồng hồ. Nếu đồng hồ hệ thống từng nhảy giờ, đừng dùng công thức như một đồng hồ UTC hoàn hảo; khi log GC có cả UTC và JVM uptime cùng sự kiện, cặp mốc đó thường tốt hơn cho việc kiểm tra chéo.

Đừng cộng JVM uptime vào thời điểm host boot hoặc thời điểm pod được tạo. Hai mốc đó có thể trước lúc JVM start hàng phút hoặc hàng giờ.

### 2.5. Thời lượng operation: ưu tiên `System.nanoTime()`

`getUptime()` phù hợp cho câu hỏi “JVM đã tồn tại bao lâu?”, không đủ độ hạt và ngữ nghĩa để đo chính xác một request ngắn. Với thời lượng task bên trong cùng JVM:

```java
long beginNs = System.nanoTime();
try {
    // Thao tác cần đo.
} finally {
    long elapsedNs = System.nanoTime() - beginNs;
    // Lưu elapsedNs như elapsed duration; không xem beginNs là epoch timestamp.
}
```

Đây là snippet trong method, không chạy độc lập. `nanoTime()` có gốc tùy ý và dành cho elapsed duration; không ghép trực tiếp hai giá trị `nanoTime()` từ JVM khác nhau.

## 3. VM implementation, VM specification và Java version

### 3.1. VM implementation

Ba method:

- `getVmName()`, tương ứng `java.vm.name`: tên triển khai VM.
- `getVmVendor()`, tương ứng `java.vm.vendor`: nhà cung cấp triển khai.
- `getVmVersion()`, tương ứng `java.vm.version`: phiên bản triển khai VM.

Ví dụ trên một HotSpot build có thể có tên VM chứa “64-Bit Server VM”. **Output thay đổi theo vendor/build/JDK**: đừng hard-code tên để quyết định loại JVM, và không suy ra version JDK chỉ bằng việc cắt chuỗi VM name.

Tách biệt với thông tin Java runtime/library version, chẳng hạn `System.getProperty("java.version")` hoặc `Runtime.version()`. Chúng trả ngữ nghĩa khác với `java.vm.version`. Khi chẩn đoán khác biệt giữa hai pod, lưu cả runtime build, VM version, image digest và flags có liên quan.

### 3.2. VM specification

Ba method:

- `getSpecName()`: tên specification của Java VM.
- `getSpecVendor()`: vendor của specification.
- `getSpecVersion()`: version của specification.

**Specification** là giao ước JVM cần tuân theo; **implementation** là sản phẩm cụ thể đang chạy. Hai JVM có thể tuân theo cùng specification nhưng khác vendor, GC implementation, compiler, flags được hỗ trợ hoặc cách chẩn đoán.

Ví dụ một đội deploy JDK 17 của hai vendor: `getSpecVersion()` có thể giống nhau, nhưng `getVmName()` hoặc `getVmVersion()` khác. Vì thế khi phân tích một lỗi liên quan JIT, GC hoặc native library, chỉ ghi “Java 17” thường chưa đủ bối cảnh.

### 3.3. Management specification

`getManagementSpecVersion()` cho phiên bản Java management interface specification mà VM hỗ trợ. Nó **không phải** version ứng dụng, không phải JDK update version và không thay cho thông tin vendor/VM build. Dùng khi cần kiểm tra khả năng tương thích công cụ quản lý; đừng nhầm với `getSpecVersion()`.

## 4. Nhận diện đúng tiến trình với PID và tên JVM

### 4.1. `getPid()` và `getName()`

`getPid()` (có từ Java 10) trả process ID của JVM hiện tại. Điều này giúp nối dữ liệu nội bộ với `jcmd`, OS metrics, pod/container info và artifact chẩn đoán.

`getName()` trả **chuỗi tên JVM do implementation quyết định**. Một số JVM có thể dùng dạng `pid@hostname`, nhưng hợp đồng API cho phép chuỗi tùy ý. Không nên viết code phụ thuộc vào việc cắt chuỗi bằng ký tự `@` để lấy PID: từ Java 10 trở lên hãy dùng `getPid()` trực tiếp.

**Đối với container:** PID nhìn từ JVM trong PID namespace có thể khác PID của cùng tiến trình trên host. PID số 1 xuất hiện ở nhiều container là điều bình thường; nó không định danh duy nhất JVM trên toàn cluster.

### 4.2. Khóa nhận diện một đời JVM

Một bản ghi hữu ích cho điều tra thường kết hợp:

```text
service / environment
+ node / host hoặc cluster
+ pod / container ID (nếu có)
+ process ID
+ approximate JVM start time
+ deployment/build/image digest
```

Đây là **bộ trường nhận diện để điều tra**, không phải một khóa UUID bảo đảm không trùng trong mọi trường hợp. Khi so timestamp hoặc uptime giữa các lần thu thập, phải biết chúng thuộc **cùng đời JVM**. Nếu service restart, nên bắt đầu một chuỗi metric uptime riêng hoặc gắn nhãn identity phù hợp để tránh nối hai vòng đời khác nhau.

## 5. `getInputArguments()`: cần hiểu chính xác nó trả gì

`runtime.getInputArguments()` trả một `List<String>` chứa **đối số đã được chuyển cho JVM**. Ví dụ quen thuộc trên HotSpot có thể gồm `-Xms`, `-Xmx`, `-XX:...`, `-Dname=value`, `--add-opens` hoặc `-javaagent` tùy cách startup.

Quan trọng hơn là các **giới hạn hợp đồng**:

1. **Không bao gồm đối số `String[] args` gửi vào `main`.** Hai tập dữ liệu ở hai tầng khác nhau.
2. **Không bảo đảm chứa tất cả tùy chọn của lệnh `java`.** Launcher tiêu thụ một số option để xác định class/JAR/module entry point.
3. **JVM có thể nhận option từ nhiều nguồn**: java launcher, biến môi trường hoặc configuration files tùy implementation.
4. **Một list rỗng là hợp lệ.** Nếu không có JVM input arguments, API trả list rỗng.
5. Danh sách giúp nhìn **đối số được chuyển lúc khởi động**, không bảo đảm phản ánh toàn bộ trạng thái flag đã có thể thay đổi sau startup, default flags hoặc giới hạn tài nguyên thực tế do cgroup/OS.

### 5.1. Phân biệt JVM arguments, launcher options và application arguments

Xem lệnh minh họa:

```bash
java -Xms64m -Xmx256m -Dapp.mode=demo \
     -cp . RuntimeMxBeanInspect --request-id=R42
```

Trong lệnh này:

| Phần | Nhóm ý nghĩa | Cần lấy từ đâu? |
| --- | --- | --- |
| `-Xms64m` | JVM initial heap option | Có thể xuất hiện trong `getInputArguments()` |
| `-Xmx256m` | JVM maximum heap option | Có thể xuất hiện trong `getInputArguments()` |
| `-Dapp.mode=demo` | JVM system property option | Có thể xuất hiện trong input args; giá trị hiệu lực xem thêm `System.getProperty` |
| `-cp .` | Launcher chọn classpath | `getClassPath()`/launcher command; đừng giả định là VM argument |
| `RuntimeMxBeanInspect` | Tên main class | Launcher/application launch metadata |
| `--request-id=R42` | Đối số chương trình nhận qua `main(String[] args)` | Tham số `args` của `main`, không phải `getInputArguments()` |

Nếu đổi lệnh thành `java -jar app.jar --request-id=R42`, quy tắc phân biệt vẫn tương tự: `--request-id` là app argument. Với Spring Boot, app server hay framework riêng, phần sau entry point có thể còn đi qua bộ parser của framework, **không** tự biến thành JVM flag.

### 5.2. Vì sao danh sách argument chưa đủ để khẳng định cấu hình heap?

Thấy `-Xmx256m` trong `getInputArguments()` là bằng chứng option được chuyển, nhưng không đủ kết luận:

- cgroup memory limit của container là bao nhiêu;
- JVM dùng effective heap max là bao nhiêu khi option khác cùng tham gia;
- một flag có được chỉnh động sau startup hay không;
- phần nào của RSS là heap, metaspace, thread stacks hoặc native memory;
- heap đang dùng bao nhiêu tại thời điểm lỗi.

Để biết heap usage/effective max, hỏi `MemoryMXBean` hoặc `MemoryPoolMXBean`; để xem flags HotSpot và cấu hình VM thực, `jcmd <pid> VM.flags` hoặc công cụ tương đương có thể phù hợp. `getInputArguments()` đặc biệt hữu ích để **tìm sai khác lúc launch** (ví dụ pod B thiếu `-XX:...` so với pod A), nhưng không thay thế cho các phép đo trạng thái.

### 5.3. Cảnh báo về bí mật trong arguments

Danh sách có thể chứa:

- `-Dpassword=...`, `-Dapi.token=...`, connection string hoặc đường dẫn đến file nhạy cảm;
- `-javaagent` và `-agentpath` có tham số chứa token/endpoint;
- option riêng của ứng dụng/framework bị truyền lẫn lúc khởi động;
- thông tin host, tên tài khoản hoặc đường dẫn nội bộ.

**Không in thẳng `getInputArguments()` ra stdout, telemetry, log, issue hay công cụ chat.** Không phải lúc nào regex “che các chuỗi chứa password” cũng đủ: secret có thể nằm trong option lạ, được encode, là một arg ngay sau flag hoặc nằm trong URL. Thu thập **những trường đã phê duyệt theo allowlist**, ví dụ cờ “có/không” hoặc category/number đã xác minh an toàn.

Ví dụ nếu chỉ cần biết JVM có nhận option `-Xmx`:

```java
boolean hasExplicitXmx = runtime.getInputArguments().stream()
        .anyMatch(arg -> arg.startsWith("-Xmx"));
```

Đây là snippet trong method. Kết quả là bằng chứng **có chuỗi option bắt đầu bằng `-Xmx` trong list**, không chứng minh max heap runtime hay rằng các cơ chế cấu hình khác không có tác dụng.

## 6. Chương trình Java 17+ chạy được: lấy snapshot runtime an toàn

Chương trình dưới đây đọc RuntimeMXBean và **chỉ in metadata ít nhạy cảm**: PID, tên/version VM, approximate start UTC, uptime, số lượng input args, sự hiện diện của option `-Xmx`, cờ hỗ trợ boot class path và `ObjectName`. Nó cố ý **không** in nguyên văn input args, toàn bộ system properties hoặc classpath. Lưu file đúng tên **`RuntimeMxBeanInspect.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.time.Duration;
import java.time.Instant;

public class RuntimeMxBeanInspect {
    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();

        Instant start = Instant.ofEpochMilli(runtime.getStartTime());
        Duration uptime = Duration.ofMillis(runtime.getUptime());

        boolean hasXmx = runtime.getInputArguments().stream()
                .anyMatch(value -> value.startsWith("-Xmx"));

        System.out.println("objectName=" + runtime.getObjectName());
        System.out.println("pid=" + runtime.getPid());
        System.out.println("vmName=" + runtime.getVmName());
        System.out.println("vmVendor=" + runtime.getVmVendor());
        System.out.println("vmVersion=" + runtime.getVmVersion());
        System.out.println("startUtcApproximately=" + start);
        System.out.println("uptime=" + uptime);
        System.out.println("vmArgCount=" + runtime.getInputArguments().size());
        System.out.println("hasExplicitXmx=" + hasXmx);
        System.out.println("mainArgCount=" + args.length);
        System.out.println("bootClassPathSupported="
                + runtime.isBootClassPathSupported());
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac RuntimeMxBeanInspect.java
java -Xms64m -Xmx256m -Dapp.mode=demo \
     -cp . RuntimeMxBeanInspect --request-id=R42
```

Output minh họa **về hình dạng**, các giá trị VM/PID/start/uptime/version phụ thuộc máy và thời điểm:

```text
objectName=java.lang:type=Runtime
pid=12345
vmName=OpenJDK 64-Bit Server VM
vmVendor=Eclipse Adoptium
vmVersion=17.0.x+...
startUtcApproximately=2026-10-29T08:00:00.000Z
uptime=PT1.234S
vmArgCount=3
hasExplicitXmx=true
mainArgCount=1
bootClassPathSupported=false
```

**Đây không phải stdout cố định**: dòng `pid`, tên/version/vendor, uptime/start và số input arguments có thể khác; VM có thể nhận option bổ sung từ môi trường. Dòng `mainArgCount=1` xuất phát từ một đối số chương trình trong command đã cho. Trên HotSpot JDK 17 thông thường, `-Xmx256m` sẽ hiện trong `getInputArguments()` và boot class path mechanism cũ không được hỗ trợ, nhưng đừng biến hai điều này thành giả định cho mọi JVM.

Ý nghĩa chẩn đoán:

- `startUtcApproximately` và `uptime` giúp xác định đời JVM khi cần đối chiếu restart.
- `vmName`/`vmVendor`/`vmVersion` xác định VM implementation, không đủ để xác định toàn bộ image hoặc dependency build.
- `vmArgCount` là số argument chuyển tới VM, khác `mainArgCount`.
- `hasExplicitXmx` là quan sát một option được truyền, không phải phép đọc heap max thực.
- `ObjectName` cho phép tra cùng MXBean qua JMX nếu có kết nối tới đúng JVM.

Khi tích hợp vào service, nên thu snapshot này ở startup hoặc endpoint quản trị có xác thực, gắn với deployment identity và có mức truy cập phù hợp. Không nên trả toàn bộ runtime info công khai qua HTTP.

## 7. Ví dụ Java 17+ có stdout chính xác: chuyển uptime sang UTC

Để thấy rõ đơn vị mà không phụ thuộc máy đang chạy, hãy dùng dữ liệu học tập cố định. Lưu **`UptimeTimelineDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;

public class UptimeTimelineDemo {
    public static void main(String[] args) {
        Instant approximateStart =
                Instant.parse("2026-10-29T08:00:00Z");
        long eventUptimeMillis = 225_600L;

        Instant estimatedEvent =
                approximateStart.plusMillis(eventUptimeMillis);

        System.out.println("jvmStartUtc=" + approximateStart);
        System.out.println("eventUptimeMs=" + eventUptimeMillis);
        System.out.println("duration="
                + Duration.ofMillis(eventUptimeMillis));
        System.out.println("estimatedEventUtc=" + estimatedEvent);
    }
}
```

Chạy:

```bash
javac UptimeTimelineDemo.java
java UptimeTimelineDemo
```

**Stdout chính xác** trên Java 17+:

```text
jvmStartUtc=2026-10-29T08:00:00Z
eventUptimeMs=225600
duration=PT3M45.6S
estimatedEventUtc=2026-10-29T08:03:45.600Z
```

`Duration` thể hiện **khoảng** 3 phút 45,6 giây. `Instant` thể hiện **thời điểm** UTC. Chương trình chỉ mô phỏng phép quy đổi; nếu lấy `approximateStart` từ `getStartTime()` thật, độ chính xác của mốc và clock skew của máy cần được xét khi ghép log từ nhiều node.

## 8. Classpath, native library path và system properties

### 8.1. `getClassPath()` không phải toàn bộ dependency graph

`getClassPath()` tương đương `System.getProperty("java.class.path")` và mô tả Java classpath mà **system class loader** sử dụng để tìm class. Trên Linux/macOS đường dẫn thường phân cách bằng `:`, còn Windows bằng `;` (dùng `File.pathSeparator` khi cần tách theo platform).

Nó **không bảo đảm liệt kê**:

- tất cả JAR trong custom class loader, plugin framework hoặc nested/fat JAR;
- toàn bộ module path và resolved module graph của JPMS;
- runtime class động sinh từ agent, proxy hoặc framework;
- các thư viện native do OS loader sử dụng.

Trong bài toán `ClassNotFoundException`/`NoClassDefFoundError`, `getClassPath()` giúp kiểm tra bước đầu nhưng vẫn cần xét đúng defining class loader, resource URL, module layer và artifact version.

### 8.2. `getLibraryPath()` là Java native library path

`getLibraryPath()` tương đương `System.getProperty("java.library.path")`. Nó có ích khi chẩn đoán `System.loadLibrary(...)` hoặc `UnsatisfiedLinkError`, nhưng cần phân biệt với đường tìm kiếm phụ thuộc `.so`/`.dll` của OS loader như `LD_LIBRARY_PATH` hoặc Windows DLL search order. Một thư viện JNI có thể nằm trong path nhưng vẫn lỗi vì thiếu thư viện native thứ cấp hoặc không đúng kiến trúc/ABI.

### 8.3. `getBootClassPath()` có thể không được hỗ trợ

Đừng gọi thẳng `getBootClassPath()` trên JDK hiện đại với giả định nó luôn hoạt động. API cung cấp `isBootClassPathSupported()` để kiểm tra trước; nếu không hỗ trợ, `getBootClassPath()` có thể ném `UnsupportedOperationException`. Đặc biệt từ hệ thống module Java 9+, không dùng boot class path cũ làm cách chuẩn để hiểu các module JDK. Phải hỏi đúng JDK/VM đang chạy.

Mẫu an toàn:

```java
if (runtime.isBootClassPathSupported()) {
    String bootPath = runtime.getBootClassPath();
    // Chỉ sử dụng khi cần và không ghi công khai đường dẫn nhạy cảm.
} else {
    // Cơ chế boot class path không được VM hỗ trợ.
}
```

Đây là snippet trong method có biến `runtime`; không phải chương trình độc lập.

### 8.4. `getSystemProperties()` không phải environment variables

`getSystemProperties()` trả map các Java system properties có key và value kiểu String, tương ứng dữ liệu từ `System.getProperties()`. Property với key/value không phải String bị bỏ qua. Dữ liệu có thể bao gồm:

- `java.home`, `java.version`, `java.vm.name`;
- `user.dir`, `file.encoding`, `user.timezone` nếu có;
- các property `-D...` do launcher hay code thêm/sửa;
- credential hoặc URL nếu ứng dụng cấu hình sai cách.

**System properties khác process environment** (đọc bằng `System.getenv()`). Một biến `JAVA_HOME` ở environment không mặc định đồng nghĩa `java.home` hoặc executable của JVM đã chạy. Thêm nữa, system property có thể bị chương trình thay đổi **sau lúc startup**; snapshot `getSystemProperties()` không phải log bất biến của các `-D` khởi đầu.

Để so một nhóm property được phép, ưu tiên allowlist:

```java
String javaVersion = runtime.getSystemProperties()
        .get("java.version");
String javaHome = runtime.getSystemProperties()
        .get("java.home");
```

Đây là snippet không chạy độc lập. Ngay cả đường dẫn `java.home` hoặc hostname cũng có thể nhạy cảm trong một môi trường cụ thể. Không dump `getSystemProperties()` nguyên map lên endpoint công khai, log pipeline hoặc ticket.

## 9. Dùng RuntimeMXBean qua JMX

### 9.1. Trong cùng JVM: platform MBeanServer

JMX đưa `RuntimeMXBean` ra dưới tên `java.lang:type=Runtime`, cho phép đọc thuộc tính thông qua `MBeanServer`. Ví dụ có thể chạy độc lập trên Java 17+:

Lưu **`RuntimeJmxLocalDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RuntimeJmxLocalDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                ManagementFactory.RUNTIME_MXBEAN_NAME);

        Object uptime = server.getAttribute(name, "Uptime");
        Object start = server.getAttribute(name, "StartTime");
        Object vmName = server.getAttribute(name, "VmName");

        System.out.println("registered=" + server.isRegistered(name));
        System.out.println("uptimeIsLong=" + (uptime instanceof Long));
        System.out.println("startIsLong=" + (start instanceof Long));
        System.out.println("vmNameIsString=" + (vmName instanceof String));
    }
}
```

Biên dịch/chạy:

```bash
javac RuntimeJmxLocalDemo.java
java RuntimeJmxLocalDemo
```

**Stdout chính xác** với platform MXBean theo JDK 17 chuẩn:

```text
registered=true
uptimeIsLong=true
startIsLong=true
vmNameIsString=true
```

Các thuộc tính `Uptime` và `StartTime` ánh xạ sang `Long`, `VmName` là String. `getInputArguments()` được ánh xạ sang `String[]` khi truy cập qua MBeanServer; một map `getSystemProperties()` có thể được biểu diễn dưới dạng JMX `TabularData`. Do đó, đừng giả định Java collection bên trong MXBean giữ nguyên loại khi đi qua JMX open types.

### 9.2. Truy cập JVM khác bằng proxy

Nếu đã có `MBeanServerConnection` **tới đúng JVM đích**:

```java
RuntimeMXBean remote =
        ManagementFactory.getPlatformMXBean(
                connection, RuntimeMXBean.class);
long remoteUptimeMs = remote.getUptime();
```

Đây là snippet cần `connection` có sẵn, không phải chương trình kết nối đầy đủ. Remote JMX cần cơ chế kết nối và quyền phù hợp. Không mở JMX remote không xác thực ra Internet, không vô hiệu hóa bảo mật chỉ để lấy uptime. Tùy implementation và môi trường, remote management có thể cần TLS, xác thực, firewall, port cố định hoặc cơ chế agent/sidecar được vận hành phê duyệt.

**Đúng JVM quan trọng hơn cách truy cập:** một proxy hợp lệ nhưng đang trỏ nhầm JVM sẽ đưa ra uptime/VM flags của tiến trình khác, dẫn tới kết luận sai.

### 9.3. RuntimeMXBean read-only không phải công cụ sửa JVM flag

Các method được nêu trong bài dùng để **đọc metadata**. Không có `RuntimeMXBean.setUptime(...)` hay `setInputArguments(...)`. Muốn thay configuration của ứng dụng/VM phải dùng cơ chế quản lý tương ứng, và nhiều option chỉ có hiệu lực sau restart. Đừng suy diễn từ việc MXBean có thể truy cập qua JMX rằng nó cho sửa mọi flag.

## 10. Đối chiếu với `jcmd`, process metadata và hệ giám sát

Khi gặp sự cố production, nên đối chiếu RuntimeMXBean với **bằng chứng độc lập**:

| Câu hỏi | RuntimeMXBean | Nguồn kiểm chứng |
| --- | --- | --- |
| JVM nào đang chạy? | `getPid()`, `getVmName()`, `getVmVersion()` | `jcmd <pid> VM.version`, executable path, image digest |
| Đã chạy bao lâu? | `getUptime()`, `getStartTime()` | Process/container restart timestamps, GC log UTC+uptime |
| Đã truyền flag nào? | `getInputArguments()` | `jcmd <pid> VM.command_line` và `VM.flags` |
| Heap limit thực là bao nhiêu? | Input args có thể chứa `-Xmx` | `MemoryMXBean`, `jcmd VM.flags`, container memory limit |
| Classpath/native path? | `getClassPath()`, `getLibraryPath()` | Artifact/source của class, OS library dependencies |
| Main args là gì? | **Không lấy được từ `getInputArguments()`** | App startup logs/launch metadata đã lọc, main args trong code |
| Có bao nhiêu luồng/GC pause? | **Không phải chức năng chính** | `ThreadMXBean`, `GarbageCollectorMXBean`, JFR/GC logs |
| System properties hiện tại? | `getSystemProperties()` | Cấu hình app và process startup, theo allowlist |

Ví dụ các lệnh trên JVM mục tiêu (cần quyền và JDK tools, `12345` là PID minh họa):

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 help
```

`jcmd VM.command_line` có thể tiết lộ secret từ command line; chỉ sử dụng trong môi trường được phép, tránh xuất nguyên văn vào nơi chia sẻ rộng. Một số image runtime tối giản không có `jcmd`, một số tiến trình không cho attach, và PID trong container namespace có thể khác. Khi đó RuntimeMXBean được nhúng trong app hoặc JMX connector có kiểm soát có thể thuận tiện hơn.

### 10.1. Đối chiếu metrics uptime khi có restart

Một monitoring system có thể scrape uptime theo chu kỳ; thí dụ:

```text
instance=A at 10:00:00Z: uptime=600000 ms
instance=A at 10:00:30Z: uptime=630000 ms
instance=A at 10:01:00Z: uptime=10000 ms
```

Giá trị giảm là **dấu hiệu cần điều tra**: có thể JVM mới đã thay JVM cũ. Phải kiểm tra PID, JVM start, container ID và restart events, vì nhãn `instance=A` có thể được tái sử dụng cho đời process mới. Nếu hai mẫu đến từ collector khác hoặc scrape timestamp bị trễ, cần kiểm tra ingest-time vs event-time.

Việc đổi uptime sang “thời điểm JVM start” bằng cách lấy `wallNow - uptime` chỉ là phép ước lượng, nhạy với clock skew/step và thời gian đọc; dùng `getStartTime()` làm nguồn trực tiếp tốt hơn, sau đó đối chiếu với event log.

### 10.2. Tại sao đừng ghép uptime của hai JVM khác nhau?

Nếu A có uptime 900000 ms và B có uptime 300000 ms, không thể kết luận A sinh request trước B. Uptime là thời lượng tính từ mốc riêng. Để ghép nguyên nhân giữa các node cần timestamp UTC có offset rõ, trace IDs, version/instance identity và uncertainty. Uptime giúp phân biệt vòng đời JVM, không thay thế distributed tracing.

## 11. Kịch bản điều tra điển hình

### Kịch bản A — “Deploy xong mà JVM vẫn dùng cấu hình cũ”

**Triệu chứng:** thay startup option trong manifest rồi rollout, nhưng service phản ứng như chưa thay.

**Bằng chứng cần lấy:**

1. Định danh JVM thật: pod/container ID, `getPid()`, `getStartTime()` và build/image digest.
2. `getInputArguments()` cho biết VM arguments đang thấy; không log toàn list nếu có secret.
3. `getSystemProperties()` (allowlist) cho giá trị property hiện tại.
4. `jcmd VM.command_line`/`VM.flags`, hoặc startup metadata từ platform, để đối chiếu launch/effective flags.

**Diễn giải:** nếu JVM start time cũ hơn mốc rollout, pod có thể chưa được thay hoặc nhìn nhầm instance; nếu đúng JVM mới nhưng thiếu flag, cần kiểm tra Helm/manifest, entrypoint, script, option injection và JVM launcher. Nếu đã có `-Xmx` nhưng heap max không đúng kỳ vọng, xem effective flag và cgroup, không chỉ so chuỗi startup.

### Kịch bản B — “Một pod chết liên tục, pod khác bình thường”

**Triệu chứng:** pod A có uptime vài giờ, pod B chỉ vài giây; error rate B tăng.

**Điều tra:** lấy JVM start + PID + container restart count và timestamps. Kiểm tra lỗi ở startup, OOMKilled/exit code, startup dependencies, readiness/liveness probes. Dữ liệu uptime thấp cho thấy đời JVM ngắn nhưng **không tự xác định nguyên nhân**; có thể do rollout hợp lệ, crash, OOM, probe restart hoặc tái lên lịch.

### Kịch bản C — “Một hệ thống có cùng Java version nhưng hiệu năng khác”

**Triệu chứng:** hai instance báo `java.version=17` nhưng GC/cpu/latency khác.

**Bằng chứng:** so `getVmName()`, `getVmVendor()`, `getVmVersion()`, JDK image digest và relevant `getInputArguments()`; sau đó dùng Memory/GC/OS MXBeans, JFR, CPU và cgroup metrics. Cùng VM specification không bảo đảm cùng implementation, flags, workload hoặc resource limits.

### Kịch bản D — “Sự kiện GC xảy ra trước hay sau restart?”

**Triệu chứng:** GC log ghi uptime 12 phút, monitoring hiện uptime 20 giây.

**Phân tích:** có thể hai nguồn thuộc hai đời JVM. Ghép theo PID, JVM start time, log rotation, UTC decorators và container ID. Nếu không nhận diện được cùng JVM, **không** nối hai uptime thành timeline liên tục. Một log từ process cũ vẫn có thể được collector gửi tới sau khi process mới bắt đầu.

## 12. Quy trình thu thập runtime snapshot cho incident

1. **Xác định câu hỏi.** Ví dụ “Pod nhận traffic hiện chạy JVM version nào?”, “Có restart sau deploy?”, “JVM đã nhận `-Xmx` chưa?”.
2. **Chọn identity chính xác.** Ghi host/node, container ID, PID, start time và image/build revision; không chỉ ghi tên service.
3. **Thu ít trường nhất đủ trả lời.** `getUptime`/`getStartTime` và VM metadata thường đủ cho restart/version; chỉ đọc selected flags/properties khi câu hỏi cần.
4. **Gắn mốc thu thập.** Ghi thời điểm UTC của collector/app khi đo và đơn vị `ms`. Nếu có nhiều node, kiểm tra clock synchronization.
5. **Lọc dữ liệu nhạy cảm trước khi xuất.** Không hiển thị raw VM arguments, toàn system properties, đường dẫn chứa secrets hoặc tên người dùng nếu không được phép.
6. **Đối chiếu nguồn thứ hai.** JDK tools, process/container metadata, GC log hoặc deployment history có thể phân biệt giả thuyết.
7. **Diễn giải giới hạn.** `getStartTime` chỉ xấp xỉ; `getInputArguments` thiếu một số launcher options; `getName` là implementation-defined; path/flag không chứng minh trạng thái hiệu lực của mọi subsystem.
8. **Lưu kết luận và hành động.** Ví dụ “JVM instance mới lúc 08:00Z, bản VM A, input args có `-Xmx`; sự cố còn cần heap max/GC evidence” rõ ràng hơn “đã kiểm tra Java”.

### 12.1. Đề xuất schema ngắn gọn cho một snapshot

Ví dụ minh họa an toàn, **không phải dữ liệu thật**:

```json
{
  "event_time_utc": "2026-10-29T08:03:45.600Z",
  "service": "checkout",
  "instance": "checkout-1",
  "jvm_pid": 12345,
  "jvm_start_utc_approx": "2026-10-29T08:00:00Z",
  "jvm_uptime_ms": 225600,
  "vm_name": "OpenJDK 64-Bit Server VM",
  "vm_vendor": "example-vendor",
  "vm_version": "example-build",
  "vm_argument_count": 3,
  "has_explicit_xmx": true,
  "input_arguments_redacted": true
}
```

Các tên/phiên bản ở trên chỉ làm placeholder dạng dữ liệu mô phỏng và **không phải giá trị để dán vào production**. Đưa trường `jvm_start_utc_approx` và `jvm_uptime_ms` cùng nhau giúp người đọc không nhầm giữa epoch và elapsed time. Khi ghi từ môi trường thật, thêm container ID/boot ID hoặc event source theo thiết kế telemetry.

## 13. Những lỗi diễn giải cần tránh

1. **Nhầm `getUptime()` với host uptime.** JVM có thể restart nhiều lần trong một lần OS boot.
2. **Nhầm `getStartTime()` với thời điểm ứng dụng healthy.** Từ VM start đến readiness có thể có hàng chục giây warm-up.
3. **Đổi uptime ra UTC bằng cách cộng vào start time của JVM khác.** Hai đồng hồ elapsed khác gốc không so trực tiếp.
4. **Cho rằng `getName()` luôn có dạng `pid@host`.** API không bảo đảm format; dùng `getPid()`.
5. **Đọc `getInputArguments()` như toàn bộ command line.** Launcher options/entrypoint có thể thiếu.
6. **Tìm đối số `main` trong danh sách VM args.** Application arguments là lớp khác.
7. **Dựa vào tên property `-Xmx` để khẳng định heap usage.** Cần dữ liệu MemoryMXBean/VM flags thực.
8. **Giả định tất cả `java.*` properties chỉ đặt một lần lúc khởi động.** Một số property có thể bị ứng dụng cập nhật.
9. **In toàn bộ `getSystemProperties()` hoặc VM arguments ra log.** Có thể chứa password/token/URL nhạy cảm.
10. **Gọi `getBootClassPath()` mà không kiểm tra support.** Có thể ném `UnsupportedOperationException`.
11. **Nghĩ `getClassPath()` là module path và toàn bộ custom classloader path.** JPMS và framework loader có cơ chế riêng.
12. **Cho rằng hai VM cùng `getSpecVersion()` phải có cùng hành vi.** Implementation, build và flags có thể khác.
13. **Đổi system timezone để “sửa” uptime.** Uptime là duration, không có timezone.
14. **Chỉ ghép số PID mà không có container/start time.** PID có thể được reuse và namespace khác nhau.
15. **Dùng remote JMX không kiểm soát bảo mật.** Exposure của management interface có thể dẫn đến rò rỉ dữ liệu và nguy cơ lớn hơn.
16. **Tăng tần suất scrape tới mức không cần thiết.** Runtime metadata ít đổi; thu quá nhiều có thể tốn chi phí pipeline và làm dữ liệu khó đọc.

## 14. Checklist và bài tập tự kiểm tra

- [ ] Đã lấy đúng `RuntimeMXBean` của JVM mục tiêu?
- [ ] `getUptime()` được ghi **mili giây**; `getStartTime()` là **epoch milliseconds xấp xỉ**?
- [ ] Đã phân biệt JVM start, container start, OS boot và app readiness?
- [ ] Đã ghi PID cùng container/node identity để tránh nhầm JVM?
- [ ] Đã ghi VM implementation name/vendor/version và phân biệt với specification?
- [ ] Đã hiểu `getInputArguments()` khác `main(args)` và không phải toàn bộ launcher command?
- [ ] Đã đối chiếu option startup với effective flags/metrics khi cần?
- [ ] Có điều kiện kiểm tra trước khi gọi `getBootClassPath()`?
- [ ] Đã hạn chế các giá trị `-D`, paths, properties và thông tin nhạy cảm?
- [ ] Nếu truy cập qua JMX, đã xác định đúng ObjectName/connection và kiểm soát bảo mật?
- [ ] Đã gắn timestamp UTC, source identity và metadata cho snapshot?
- [ ] Kết luận có phân biệt điều API xác nhận được với giả thuyết cần thêm dữ liệu?

**Bài tập 1:** Một monitoring snapshot lúc 10:00 có `getUptime()=300_000 ms` và `getStartTime()` tương ứng xấp xỉ 09:55. Lúc 10:02, cùng nhãn pod có uptime 20_000 ms. Hãy nêu ít nhất hai giả thuyết (restart/replacement và nối nhầm nguồn), cùng bằng chứng cần thu để phân biệt. Không khẳng định crash chỉ từ sự thay đổi uptime.

**Bài tập 2:** Dịch vụ được launch bằng `java -Xmx512m -Dapp.mode=prod -jar app.jar --tenant=A`. Hãy phân loại `-Xmx512m`, `-Dapp.mode=prod`, `-jar app.jar` và `--tenant=A`. Giải thích vì sao `getInputArguments()` có thể cho biết một số VM flags nhưng không chứa `--tenant=A`, và cách xác minh effective heap max.

**Bài tập 3:** Hai service cùng `getSpecVersion()=17` nhưng có `getVmVendor()` khác nhau. Bạn cần thêm bằng chứng gì trước khi kết luận một lỗi JIT hoặc GC do vendor? Trả lời theo thứ tự: VM build → flags → workload/resource limits → metrics/JFR/GC events.

## Tài liệu tham khảo

- Oracle Java SE 17, [`RuntimeMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html): ngữ nghĩa và giới hạn của `getUptime()`, `getStartTime()`, `getInputArguments()`, thông tin VM, classpath và system properties.
- Oracle Java SE 17, [`ManagementFactory` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): lấy platform MXBean, `RUNTIME_MXBEAN_NAME` và truy cập qua `MBeanServerConnection`.
- Oracle Java SE 17, [`java.lang.management` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/package-summary.html): mô hình platform MXBeans, đơn vị đo và đối tượng quản lý.
- Oracle Java SE 17, [`jcmd` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): xác minh `VM.version`, `VM.command_line`, `VM.flags` trên HotSpot JVM phù hợp.
- Oracle Java SE 17, [`Instant` và `Duration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): biểu diễn thời điểm tuyệt đối và khoảng thời gian.
- Oracle Java SE 17, [`ProcessHandle` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html): PID và thông tin tiến trình khi cần đối chiếu thêm.

**Nguyên tắc sử dụng:** dùng `RuntimeMXBean` để nhận diện **một đời JVM và bối cảnh startup**, rồi chọn phép đo khác khi cần chứng minh heap, CPU, GC, thread contention hoặc nguyên nhân crash. Giá trị của snapshot nằm ở việc đọc đúng đơn vị, đúng tiến trình, đúng giới hạn API và không làm lộ cấu hình nhạy cảm.