# `getCpuLoad()` cho môi trường vận hành Java — đo, diễn giải và giám sát CPU hiện đại

> **Mục tiêu:** dùng đúng `com.sun.management.OperatingSystemMXBean.getCpuLoad()` để quan sát mức sử dụng CPU **gần đây** của môi trường nơi JVM đang chạy; chuyển tỷ lệ `0.0–1.0` thành %, xử lý giá trị âm khi metric không khả dụng và tránh nhầm nó với `getProcessCpuLoad()` hoặc load average. Bài tập trung vào vận hành dịch vụ trên server, máy ảo và container, cùng chương trình Java 17+ hoàn chỉnh. `getCpuLoad()` là API được đưa vào **Java 14** và **vẫn được hỗ trợ trong Java SE 17/21/25/26**; không sử dụng phương thức `getSystemCpuLoad()` đã deprecated từ Java 14 làm lựa chọn chính.

## 1. Vì sao cần `getCpuLoad` trong vận hành?

Khi một ứng dụng Java đang chạy, thông tin CPU giúp người vận hành trả lời những câu hỏi như: môi trường thực thi có đang bận hay không, mức tải có cùng tăng với độ trễ dịch vụ, tình trạng CPU cao là do **JVM hiện tại** hay có cả tác nhân khác, và có cần thu thập thêm số liệu GC, CPU throttling, thread hoặc tài nguyên container không.

Ví dụ một dịch vụ HTTP báo latency tăng đồng thời có spike CPU. Nếu chỉ xem thông số từ ứng dụng Java, rất dễ nhầm lẫn:

- **Môi trường đang bận:** có thể từ JVM, các tiến trình khác hoặc tổng hoạt động CPU thuộc phạm vi hệ điều hành/container mà JVM nhìn thấy.
- **Riêng JVM đang bận:** theo dõi bằng `getProcessCpuLoad()`, không phải `getCpuLoad()`.
- **Hàng đợi/runnable entities tăng:** có thể thấy ở `getSystemLoadAverage()`, nhưng con số này **không phải CPU percentage**.
- **CPU quota bị throttling:** phải kiểm tra metric từ OS/cgroup/orchestrator; chỉ một CPU load ratio không đủ chứng minh throttling.

`getCpuLoad()` phù hợp làm một **tín hiệu quan sát** trong hệ thống giám sát, không phải phép đo toàn diện về hiệu năng, dung lượng hoặc nguyên nhân sự cố.

## 2. Đúng interface và đúng module: `com.sun.management.OperatingSystemMXBean`

Java có **hai interface trùng tên** mà bạn cần phân biệt:

| Interface | Module | Vai trò |
|---|---|---|
| `java.lang.management.OperatingSystemMXBean` | `java.management` | Interface quản lý chuẩn có `getAvailableProcessors()`, `getSystemLoadAverage()`, tên OS, kiến trúc... |
| `com.sun.management.OperatingSystemMXBean` | `jdk.management` | Interface mở rộng của JDK, kế thừa interface trên và cung cấp **`getCpuLoad()`**, `getProcessCpuLoad()`, `getProcessCpuTime()` và metric tài nguyên khác |

**`getCpuLoad()` không được khai báo trong interface chuẩn `java.lang.management.OperatingSystemMXBean`.** Nếu biến của bạn có kiểu interface chuẩn, trình biên dịch không thấy phương thức ấy cho đến khi bạn truy cập một bean triển khai interface mở rộng.

Cách truy cập phù hợp với JDK/HotSpot hiện đại:

```java
import java.lang.management.ManagementFactory;
import com.sun.management.OperatingSystemMXBean;

var standardBean = ManagementFactory.getOperatingSystemMXBean();

if (standardBean instanceof OperatingSystemMXBean extended) {
    double ratio = extended.getCpuLoad();
    // ratio >= 0.0 && ratio <= 1.0: dữ liệu hợp lệ theo hợp đồng API.
    // ratio < 0.0: dữ liệu không có sẵn, không được coi là 0%.
}
```

Đây là **snippet** trong một phương thức, không phải chương trình Java hoàn chỉnh. Syntax pattern matching cho `instanceof` đã ổn định từ Java 16 và hoàn toàn hợp lệ trong JDK 17+. Kiểm tra kiểu giúp chương trình có nhánh fallback khi JVM được sử dụng không cung cấp bean mở rộng tương ứng.

Cách khác nếu JDK hỗ trợ nền tảng MXBean này:

```java
OperatingSystemMXBean extended =
    ManagementFactory.getPlatformMXBean(OperatingSystemMXBean.class);
```

Kết quả có thể cần kiểm tra null khi môi trường không có interface hỗ trợ. Nếu lập trình thành module JPMS riêng, khai báo phụ thuộc thích hợp trong `module-info.java`, ví dụ `requires jdk.management;` và `requires java.management;` khi sử dụng cả hai. Đây là **API công khai được JDK cung cấp trong module `jdk.management`**, không cần hack reflection hoặc `--add-opens` để truy cập.

## 3. Ý nghĩa chính xác của `getCpuLoad()`

Chữ ký:

```java
double getCpuLoad()
```

Theo Oracle JavaDoc, phương thức trả về **“recent CPU usage”** của **operating environment** nơi JVM đang chạy, với hai dạng kết quả:

| Giá trị trả về | Diễn giải |
|---|---|
| `0.0` | Trong cửa sổ quan sát tương ứng, tất cả CPU được quan sát đều idle |
| `0.25` | Tỷ lệ hoạt động CPU gần đây khoảng **25%** theo cách implementation định nghĩa |
| `0.80` | Khoảng **80%** |
| `1.0` | Các CPU được quan sát bận hoàn toàn trong khoảng thời gian đó |
| **Giá trị âm** | **Không có số liệu CPU recent hợp lệ**, phải coi là unavailable |

`getCpuLoad` trả một **tỷ lệ** chứ không trả “phần trăm nguyên” hay “số CPU core đã sử dụng”. Nếu muốn hiển thị %, lấy **`ratio * 100.0`** sau khi xác nhận đầu vào hợp lệ. Không nhân thêm `getAvailableProcessors()` chỉ để hiển thị **% CPU toàn môi trường**.

Ví dụ:

```text
getCpuLoad() = 0.32
=> sử dụng CPU gần đây xấp xỉ 32.0% của môi trường được JVM quan sát.
```

**Cửa sổ lấy mẫu là implementation-specific:** nó thường liên quan đến khoảng từ lần gọi `getCpuLoad()` / `getSystemCpuLoad()` trước đó. Lần gọi đầu tiên có thể có khoảng quan sát chưa xác định. Quan trọng hơn, **những client khác cùng đọc metric này có thể ảnh hưởng kỳ quan sát** và kết quả. Vì vậy:

- Đừng coi phương thức là snapshot tức thời tại một nanosecond.
- Đừng khẳng định nó luôn đo đúng một giây hay đúng thời gian của `Thread.sleep` bạn chọn.
- Đừng so sánh hai số đọc liên tiếp cực sát nhau rồi khẳng định đó là xu hướng CPU thực.
- Đừng dựa vào một spike đơn lẻ để tự động tăng/giảm tài nguyên hoặc restart dịch vụ.

Nên mô tả metric thành **CPU load ratio gần đây của operating environment**, gắn timestamp và thông tin môi trường khi đưa vào monitoring.

### Xử lý số âm thay vì đoán lỗi

Oracle quy định nếu không có số liệu khả dụng thì kết quả **âm**. Không nên thay giá trị âm bằng `0.0`, vì như vậy sẽ sai lệch metric thành “idle 0%”.

```java
static boolean validCpuRatio(double r) {
    return Double.isFinite(r) && r >= 0.0 && r <= 1.0;
}
```

Đây là một **hàm minh họa độc lập** đặt trong class Java. Điều kiện `Double.isFinite` và cận trên `<= 1.0` là lớp phòng vệ thêm trước dữ liệu không hợp lệ ngoài hợp đồng thông thường (ví dụ implementation hoặc instrumentation bị lỗi). Nếu phép đo không hợp lệ, hãy **không xuất một gauge 0% giả**, thay vào đó đánh dấu unavailable/skip sample hoặc phát metric riêng về khả năng thu thập.

## 4. Không nhầm `getCpuLoad` với các metric CPU khác

| Phương thức | Giá trị | Hỏi đáp về vấn đề gì? |
|---|---|---|
| **`getCpuLoad()`** | Tỷ lệ `[0,1]` hoặc âm nếu unavailable | **Operating environment** của JVM sử dụng CPU gần đây ra sao? |
| **`getProcessCpuLoad()`** | Tỷ lệ `[0,1]` hoặc âm | **Tiến trình JVM** gần đây sử dụng CPU ra sao? |
| **`getProcessCpuTime()`** | Tổng thời gian CPU bằng **nanosecond** hoặc `-1` | Tổng CPU time đã dùng của JVM; không phải CPU ratio trực tiếp |
| **`getAvailableProcessors()`** | Số lượng processor mà JVM xem là có thể sử dụng, `>= 1` | Sức chứa processor được JVM nhìn thấy, có thể chịu ảnh hưởng môi trường |
| **`getSystemLoadAverage()`** | System load trung bình 1 phút hoặc âm nếu không khả dụng | Mức độ runnable/running work và hàng đợi, **không phải % CPU** |

Ví dụ minh họa cách đọc chung:

```java
double environment = extended.getCpuLoad();
double jvmProcess  = extended.getProcessCpuLoad();
long processCpuNs  = extended.getProcessCpuTime();
int cpuCount       = standardBean.getAvailableProcessors();
double loadAverage = standardBean.getSystemLoadAverage();
```

Đây là **snippet** có sẵn `extended` và `standardBean` với đúng kiểu tương ứng. Không dùng các biểu thức ấy như một lời hứa mọi JVM đều hỗ trợ tất cả metric.

### 4.1. Environment load so với process load

Giả sử `getCpuLoad() = 0.80`, nhưng `getProcessCpuLoad() = 0.05`. Dữ liệu này gợi ý **môi trường CPU bận hơn nhiều so với phần hoạt động của một JVM**, nên cần điều tra process khác, workload ngoài JVM hoặc cách tính CPU theo container. Tuy vậy vì hai phương thức có **cửa sổ quan sát và cách normalization cụ thể phụ thuộc implementation**, đừng coi hiệu `0.80 - 0.05` là chính xác “75% CPU do process khác” nếu chưa kiểm tra hệ thống.

Ngược lại, nếu cả hai cùng cao kéo dài, JVM có thể đóng góp nhiều vào mức bận CPU; phân tích bổ sung bằng profiler, thread metrics, GC logs hoặc OS monitoring để biết code/thread nào gây tải. Không quy mọi CPU bận cho garbage collector chỉ từ `getProcessCpuLoad()`.

### 4.2. Load average không phải tỷ lệ `0–1`

`getSystemLoadAverage()` là trung bình số runnable entities chạy hoặc xếp hàng trong khoảng thời gian định nghĩa, phụ thuộc OS. Giá trị của nó có thể **lớn hơn 1.0**, và không thể đơn giản nhân 100 để gọi là “CPU 150%”. Trên một số OS (ví dụ một số phiên bản môi trường Windows), API có thể trả **giá trị âm** khi không hỗ trợ.

Nếu đọc load average, cần diễn giải trong quan hệ với số processor khả dụng và đặc thù OS; **không** đưa nó vào cùng cột dashboard với `getCpuLoad()` mà không gắn đơn vị.

### 4.3. Process CPU time không phải phần trăm

`getProcessCpuTime()` trả tổng thời gian CPU của JVM tính bằng **nanosecond**, có thể tăng nhanh hơn wall-clock trên process nhiều thread chạy song song. Muốn suy ra CPU utilization từ chênh lệch hai lần đọc, cần tính đến elapsed wall-clock time và mẫu số số CPU/CPU quota **phù hợp môi trường**. Việc tự chia `cpuTimeDelta / wallTimeDelta` mà không normalize sẽ không tự ra tỷ lệ tương đương `getProcessCpuLoad()`.

**Khi chỉ cần giám sát CPU gần đây của JVM, ưu tiên `getProcessCpuLoad()`**. Dùng `getProcessCpuTime()` để quan sát thời gian CPU tích lũy hoặc khi có nhu cầu tính và kiểm tra mô hình rõ ràng.

## 5. Chương trình Java 17+ hoàn chỉnh, có kiểm thử đầu ra cố định

Chương trình tạo hai chế độ:

- **Mặc định:** chỉ kiểm thử bộ chuyển đổi ratio → percentage bằng input cố định để có **stdout xác định** trên mọi máy.
- **`--live`:** lấy bean của JVM đang chạy, đọc số processor khả dụng rồi lấy **ba mẫu `getCpuLoad()` và `getProcessCpuLoad()`**, cách nhau 750 ms trong demo. Kết quả thực tế sẽ thay đổi theo tải máy, OS/JDK và các client cùng quan sát.

Tạo tệp **`CpuLoadOperationsDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.Locale;
import com.sun.management.OperatingSystemMXBean;

public class CpuLoadOperationsDemo {
    static String formatRatio(double ratio) {
        if (!Double.isFinite(ratio) || ratio < 0.0 || ratio > 1.0) {
            return "unavailable";
        }
        return String.format(Locale.ROOT, "%.1f%%", ratio * 100.0);
    }

    static void testFormatter() {
        System.out.println("negative=" + formatRatio(-1.0));
        System.out.println("zero=" + formatRatio(0.0));
        System.out.println("quarter=" + formatRatio(0.25));
        System.out.println("full=" + formatRatio(1.0));
        System.out.println("nan=" + formatRatio(Double.NaN));
        System.out.println("aboveOne=" + formatRatio(1.1));
    }

    static void sampleEnvironment() throws InterruptedException {
        var standard = ManagementFactory.getOperatingSystemMXBean();
        if (!(standard instanceof OperatingSystemMXBean mx)) {
            System.out.println("extendedMxBean=unavailable");
            return;
        }

        int processors = standard.getAvailableProcessors();
        System.out.println("availableProcessors=" + processors);
        for (int i = 1; i <= 3; i++) {
            Thread.sleep(750);
            double environment = mx.getCpuLoad();
            double process = mx.getProcessCpuLoad();
            System.out.println("sample" + i + " environment=" +
                formatRatio(environment) + " process=" +
                formatRatio(process));
        }
    }

    public static void main(String[] args) throws InterruptedException {
        testFormatter();
        if (args.length == 1 && "--live".equals(args[0])) {
            sampleEnvironment();
        }
    }
}
```

Biên dịch/running với JDK 17+:

```bash
javac -encoding UTF-8 CpuLoadOperationsDemo.java

# Kiểm thử định dạng có stdout cố định:
java CpuLoadOperationsDemo

# Quan sát operating environment thật, số liệu KHÔNG cố định:
java CpuLoadOperationsDemo --live
```

**Stdout chính xác của `java CpuLoadOperationsDemo` đã kiểm chứng trên OpenJDK 24:**

```text
negative=unavailable
zero=0.0%
quarter=25.0%
full=100.0%
nan=unavailable
aboveOne=unavailable
```

Cách diễn giải:

- `negative=unavailable`: giá trị `-1.0` không có dữ liệu; **không** được xuất là `-100%` hay `0%`.
- `zero=0.0%`: hợp đồng `0.0` tương ứng idle trong khoảng quan sát.
- `quarter=25.0%`: minh họa quy đổi `0.25 * 100`.
- `full=100.0%`: giá trị tối đa hợp lệ `1.0`.
- `nan=unavailable` và `aboveOne=unavailable`: lớp kiểm tra đầu vào từ chối các giá trị không hợp lệ, dù JavaDoc thông thường chỉ hứa `[0,1]` hoặc âm.

**Ví dụ một lần chạy thật `--live` trên Windows/OpenJDK 24:**

```text
negative=unavailable
zero=0.0%
quarter=25.0%
full=100.0%
nan=unavailable
aboveOne=unavailable
availableProcessors=28
sample1 environment=100.0% process=3.1%
sample2 environment=32.8% process=0.3%
sample3 environment=34.8% process=0.3%
```

Đây là **kết quả quan sát của máy thử**, không phải stdout được bảo đảm cho người học. Máy khác có CPU count khác và các tỷ lệ thay đổi liên tục; có thể thấy `unavailable` nếu không có dữ liệu. Đặc biệt mẫu đầu tiên `100.0%` trong ví dụ chỉ phản ánh kết quả đầu tiên của JVM/OS trong lần đo đó; **không** suy ra “server luôn bận 100%” khi chạy demo.

Không dùng `Thread.sleep(750)` như quy tắc “chuẩn lấy mẫu 750 ms” của API. Sleep chỉ làm khoảng cách giữa các lần gọi đủ dễ quan sát; **cửa sổ nội bộ** vẫn do implementation quản lý.

### Vì sao phải kiểm thử số cố định và live tách nhau?

Kiểm thử bộ chuyển đổi là bài kiểm tra **logic ứng dụng**: xử lý cận, sentinel và format. Kiểm thử `getCpuLoad()` live là một bài kiểm tra **khả năng quan sát môi trường**: giá trị thay đổi theo scheduling, Windows/Linux, CPU của các process khác và tải hiện tại.

Một unit test không nên assert chính xác `getCpuLoad() == 0.32` hay `getProcessCpuLoad() == 0.05`. Một integration test có thể chỉ xác nhận rằng đầu ra là một ratio hợp lệ hoặc một trạng thái unavailable, và hệ thống giám sát xử lý đúng cả hai nhánh.

## 6. Tần suất sampling và thiết kế collector cho production

### 6.1. Dùng scheduler để lấy mẫu định kỳ

Mẫu thiết kế (snippet) dùng `ScheduledExecutorService`:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

ScheduledExecutorService poller =
    Executors.newSingleThreadScheduledExecutor();

poller.scheduleAtFixedRate(() -> {
    try {
        double ratio = extended.getCpuLoad();
        if (Double.isFinite(ratio) && ratio >= 0.0 && ratio <= 1.0) {
            metrics.recordGauge("app_operating_cpu_load_ratio", ratio);
        } else {
            metrics.incrementCounter("app_cpu_sample_unavailable");
        }
    } catch (RuntimeException ex) {
        logger.warn("CPU metric sampling error", ex);
    }
}, 0, 5, TimeUnit.SECONDS);

// Quản lý poller.shutdown() lúc ứng dụng dừng.
```

Đây là **pseudocode Java có chú thích**, **không phải chương trình standalone**: `metrics` và `logger` là giao diện quan sát của ứng dụng chưa được định nghĩa. Nó chỉ minh họa chiến lược thu thập, xử lý lỗi và giải phóng scheduler. Tần suất **5 giây** là ví dụ, không phải yêu cầu hay giá trị cố định của Javadoc.

Thiết kế collector thực tế nên:

1. Dùng một thành phần lấy mẫu có kiểm soát, tránh quá nhiều thread gọi `getCpuLoad()` với các nhịp xung đột.
2. Chọn interval phù hợp với mức độ biến động, chi phí quan sát và dashboard/alert; không poll cực dày chỉ vì API rẻ.
3. Lưu **timestamp** hoặc xuất qua hệ thống telemetry để xác định độ mới của mẫu.
4. Nếu metric unavailable, đánh dấu rõ hoặc bỏ mẫu và theo dõi tình trạng collector; không ghi mặc định `0.0`.
5. Thiết kế filter/aggregation để chống alert nhiễu từ spike nhất thời, chẳng hạn xét nhiều mẫu liên tiếp và kết hợp latency/throughput.
6. Khi cần bảo đảm thời gian lấy mẫu, lưu cả khoảng thời gian thực tế và đánh giá scheduler delay, GC pause và clock scheduling.
7. Dọn scheduler khi shutdown để tránh thread/task bị rò tài nguyên.

**Nhắc lại:** một client khác gọi `getCpuLoad()` hoặc alias deprecated `getSystemCpuLoad()` có thể ảnh hưởng cửa sổ quan sát. Không xem các khoảng lấy mẫu của các monitoring agent là hoàn toàn độc lập trên mọi JDK.

### 6.2. Đặt tên, đơn vị và trạng thái metric rõ ràng

Một dashboard nên ghi rõ:

| Tên metric minh họa | Đơn vị lưu trữ | Quy tắc |
|---|---|---|
| `app_operating_cpu_load_ratio` | Ratio `[0,1]` | Dữ liệu từ `getCpuLoad()` đã kiểm tra hợp lệ |
| `app_jvm_process_cpu_load_ratio` | Ratio `[0,1]` | Dữ liệu từ `getProcessCpuLoad()` |
| `app_available_processors` | Count | `getAvailableProcessors()`, có thể thay đổi |
| `app_cpu_sample_unavailable` | Counter | Tăng khi giá trị CPU không hợp lệ/không có |
| `app_jvm_process_cpu_time_seconds_total` | Seconds | Chuyển `getProcessCpuTime()` từ ns sang s **khi >= 0** |

Các tên trên là **gợi ý minh họa**, **không phải** tên metric chuẩn bắt buộc của JMX/Prometheus/Micrometer. Nếu đang dùng framework observability, cần xem metric có sẵn trước khi tự xuất bản bộ chỉ số riêng để tránh trùng dữ liệu hay khác cách normalize.

**Đừng trộn dữ liệu ratio `0.42` với percentage `42` trong cùng metric.** Chọn lưu ratio và hiển thị % ở dashboard, hoặc lưu percent với đơn vị ghi rõ, nhưng phải nhất quán giữa dashboard, alert rules và tài liệu.

## 7. Container, VM và sự khác nhau giữa environment và physical host

Oracle Java SE 26 mô tả `OperatingSystemMXBean` mở rộng là thông tin về **operating environment**: nó có thể là **native OS, hệ điều hành ảo hóa hoặc môi trường được container quản lý**. Đây là lý do tên mới `getCpuLoad()` phù hợp hơn tên lịch sử `getSystemCpuLoad()`.

Một số bối cảnh:

- **Bare metal:** môi trường JVM quan sát thường gắn với tài nguyên hệ điều hành/CPU thực tế đang khả dụng.
- **Virtual machine:** số processor và CPU load có thể phản ánh CPU ảo. Host hypervisor còn có scheduling/CPU contention ngoài tầm nhìn của JVM.
- **Container/Kubernetes:** CPU limits, quota, cpuset/cgroup và phiên bản JDK/OS có thể ảnh hưởng cách JVM nhìn thấy và báo CPU. **Không mặc định số từ `getCpuLoad()` luôn là phần trăm tổng CPU của host vật lý hoặc luôn là phần trăm đúng của quota container**; xác minh trên JDK vendor/version và runtime thật.

Ví dụ: service Java chạy trong container có quota 2 vCPU trên host 32 logical CPUs. Nếu số CPU load hiển thị khác số host dashboard, có thể là **khác phạm vi quan sát** chứ chưa chắc lỗi tính %. Hãy so sánh tài liệu và thực nghiệm của JDK cụ thể với cgroup CPU usage/quota/throttling metrics.

### Cần kiểm tra gì khi nghi ngờ container CPU metrics?

- `java -version` để xác định vendor/build, vì các bản có thể khác về hỗ trợ cgroups và normalization.
- `getAvailableProcessors()` để biết JVM thấy bao nhiêu logical processors khả dụng, **không** dùng làm bằng chứng duy nhất về physical topology.
- Trên các bản HotSpot phù hợp, `java -XshowSettings:system -version` có thể hiển thị chi tiết container/OS; tùy JDK/OS và cấu hình, thông tin có thể hạn chế.
- Metrics ở lớp orchestrator như CPU usage, quota, throttled time, saturation, số pod/CPU request nếu dùng Kubernetes; đối chiếu đúng đơn vị và khoảng lấy mẫu.
- `getProcessCpuLoad()` và GC pause metrics để phân biệt tải của JVM với môi trường.

Không kết luận “CPU yếu nên tăng heap” từ một mình `getCpuLoad()`. Cấu hình heap, GC, thread pool, CPU quota và giới hạn container phải được phân tích cùng workload.

## 8. Cách đọc trong JMX, monitoring agent và health checks

### 8.1. Local Java code vs JMX

`ManagementFactory.getOperatingSystemMXBean()` truy cập MXBean trong JVM hiện tại. MXBean này cũng được đăng ký trong platform `MBeanServer` với **ObjectName**:

```text
java.lang:type=OperatingSystem
```

JMX-compatible tools và monitoring agents có thể quan sát dữ liệu của bean từ platform MBeanServer. Tuy nhiên **không giả định tên method Java và tên attribute JMX giống hệt nhau**, vì JMX MXBean expose getter theo mô hình attributes (ví dụ getter `getCpuLoad()` tương ứng attribute tên `CpuLoad` khi implementation công bố). Xem metadata thực từ agent/JMX trước khi viết rule dashboard.

Khi dùng giám sát **từ xa**, bảo vệ JMX endpoint bằng authentication, TLS, network ACL/tunnel và chính sách tài khoản thích hợp; không mở unauthenticated JMX tới Internet để đọc CPU.

### 8.2. Health check và autoscaling

CPU load là một chỉ số quan sát hữu ích nhưng **không phải phép thử liveness duy nhất**. Một process CPU thấp vẫn có thể deadlock, backlog hoặc lỗi kết nối; CPU cao có thể là hoạt động batch dự kiến. Không dùng một số `getCpuLoad()` để tự động quyết định process healthy/unhealthy.

Với autoscaling, phối hợp load ratio, saturation, request rate, response latency và CPU limit/throttling ở đúng tầng hệ thống. Số liệu CPU nội bộ có thể không tương thích trực tiếp với metrics của autoscaler nếu **mẫu số và phạm vi** khác nhau. Chỉ dùng làm điều kiện mở rộng khi đã kiểm chứng normalization.

### 8.3. Ghi log an toàn và tránh nhầm dữ liệu thiếu

Khi metric không khả dụng, logger nên ghi ví dụ `cpuLoad=unavailable` và có thể ghi JDK/OS context ở mức được phép; **không** in nguyên process environment, access tokens, container secrets hoặc thông tin khách hàng. Tránh log mỗi 100 ms một message lỗi để không tạo log storm.

Nếu một agent quan sát load âm, đừng ghi `0` để “đẹp biểu đồ”. Một missing sample và một sample `0.0` có **ngữ nghĩa khác nhau**: một bên là thiếu dữ liệu, một bên là idle thực sự trong cửa sổ quan sát tương ứng.

## 9. Ví dụ diễn giải một sự cố trong vận hành

Giả sử dashboard báo latency HTTP p99 cao và CPU load của environment tăng:

```text
Mốc T1: getCpuLoad()        = 0.84  -> 84% environment
         getProcessCpuLoad() = 0.12  -> 12% JVM
         Request p99        = tăng

Mốc T2: getCpuLoad()        = 0.92  -> 92% environment
         getProcessCpuLoad() = 0.76  -> 76% JVM
         Request p99        = tiếp tục tăng
```

Đây là **số liệu giả định để học cách phân tích**, không phải một phép đo đã thực hiện.

- Tại **T1**, environment CPU bận nhưng phần CPU do JVM báo tương đối thấp; kiểm tra process khác, thời gian throttling, noisy neighbor, contention của VM hoặc phạm vi dữ liệu khác nhau.
- Tại **T2**, JVM process load tăng theo; điều tra JVM thread activity, profiler, JFR, GC pressure, hot methods và inbound traffic.
- **Không khẳng định** riêng Java method `getCpuLoad` xác định được thủ phạm, vì nó là một tín hiệu tổng hợp với cửa sổ quan sát implementation-specific.
- Nếu các số đọc ở khoảng cách quá gần hoặc từ nhiều agent khác nhau, cần chuẩn hóa kỳ lấy mẫu trước khi so xu hướng.

Phân tích tốt kết hợp **nhiều nguồn độc lập** để kiểm tra giả thuyết, không suy ra nguyên nhân trực tiếp từ tỷ lệ.

## 10. Lỗi phổ biến cần tránh

| Nhầm lẫn / triệu chứng | Vì sao sai | Cách sửa |
|---|---|---|
| Gọi `getCpuLoad()` trên `java.lang.management.OperatingSystemMXBean` rồi lỗi compile | Phương thức nằm trong **`com.sun.management` extension** | Dùng đúng kiểu interface mở rộng hoặc kiểm tra `instanceof` |
| Dùng `getSystemCpuLoad()` làm API hiện đại | Đã **deprecated từ Java 14** | Dùng `getCpuLoad()` |
| Nhận `0.47` rồi hiển thị “0.47%” | Đây là ratio, chưa phải percent | Chuyển thành **47.0%** |
| Nhận `-1.0` rồi hiển thị “-100%” | Giá trị âm là unavailable | Bỏ mẫu/đánh dấu thiếu dữ liệu |
| Bất cứ CPU metric âm nào cũng coi là JVM crash | Có thể không hỗ trợ hoặc tạm thiếu số liệu | Xử lý degrade và quan sát tính khả dụng metric |
| `getCpuLoad()` là CPU chỉ riêng Java | Đây là **operating environment** | Dùng `getProcessCpuLoad()` cho JVM |
| `getSystemLoadAverage()` trả % CPU | Nó là load average 1 phút, có thể >1 | Gắn nhãn và diễn giải riêng |
| `getProcessCpuTime()` là phần trăm tức thời | Đây là cumulative CPU nanoseconds | Dùng delta/normalization đúng hoặc `getProcessCpuLoad()` |
| Lần đầu `getCpuLoad()` luôn chính xác cho “giây vừa qua” | Khoảng quan sát lần đầu không xác định | Dùng nhiều mẫu có timestamp, đừng suy luận cửa sổ cố định |
| Nhiều agent đọc metric nhưng tin mọi mẫu hoàn toàn độc lập | Lời gọi khác có thể đổi observation period | Điều phối sampling, kiểm tra khi số liệu bất thường |
| Container `getCpuLoad` luôn bằng phần trăm host CPU | JDK mô tả **operating environment** | Xác nhận cgroup/VM/host và phiên bản JDK |
| CPU load=1.0 tức ứng dụng chắc chắn gặp lỗi | Tải cao có thể do workload dự kiến | So cùng latency, saturation, throttling và SLO |
| Lấy một spike rồi autoscale/restart ngay | Một mẫu nhiễu không đủ chẩn đoán | Smoothing và điều kiện nhiều tín hiệu |
| Hiển thị `NaN`/`Infinity` như metric bình thường | Chúng không phải tỷ lệ hợp lệ | Dùng `Double.isFinite` và kiểm tra range |
| Dùng tên metric gợi ý như quy chuẩn JMX | Tên ví dụ do ứng dụng đặt | Xem exporter/JMX metadata chính thức |
| Mở remote JMX không xác thực để dễ monitor | Tăng nguy cơ lộ control/metric | Dùng kết nối được bảo vệ và quyền tối thiểu |

## 11. Checklist trước khi đưa `getCpuLoad` vào production

1. Kiểm tra **JDK vendor/build, OS và môi trường container/VM** mà dịch vụ thực sự chạy.
2. Dùng `com.sun.management.OperatingSystemMXBean`, không nhầm với interface chuẩn `java.lang.management`.
3. Chọn `getCpuLoad()` — API hiện hành từ Java 14 — thay `getSystemCpuLoad()` deprecated.
4. Xử lý kết quả: `[0,1]` là ratio hợp lệ; **âm → unavailable**; kiểm tra các giá trị ngoài range.
5. Hiển thị % bằng `ratio * 100` nếu cần, giữ đơn vị nhất quán giữa metrics, charts và alerts.
6. Lấy mẫu định kỳ, lưu timestamp; hiểu cửa sổ đo implementation-specific và sự ảnh hưởng giữa nhiều caller.
7. Phân biệt environment load với process load, process CPU time và load average.
8. Kiểm tra scope trong container/VM, CPU quota, cpuset, throttling và số processor mà JVM nhìn thấy.
9. Không thay missing sample thành `0%`; theo dõi tính khả dụng metric riêng nếu quan trọng.
10. Đừng điều chỉnh JVM/GC/CPU quota hoặc tự restart chỉ dựa trên một CPU sample.
11. Thiết kế collector lifecycle, tránh poll quá dày và bảo vệ JMX/telemetry endpoints.
12. Test format/sentinel bằng input cố định; kiểm thử integration chỉ assert tính hợp lệ/trạng thái, **không assert % thực tế của máy**.
13. Khi có sự cố, kết hợp CPU với latency, throughput, GC/JFR, thread, tài nguyên container và OS metrics.
14. Chỉ dùng các API và cú pháp Java đang áp dụng; không đưa `SecurityManager`, workaround reflection hay các getter CPU deprecated vào đường chính.

## Tài liệu tham khảo chính thức

- Oracle Java SE 26 API, **`com.sun.management.OperatingSystemMXBean`** — `getCpuLoad()`, `getProcessCpuLoad()`, giá trị âm, nghĩa của operating environment: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- Oracle Java SE 21 API, **`com.sun.management.OperatingSystemMXBean`** — xác nhận `getCpuLoad` vẫn được hỗ trợ trên JDK LTS: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- Oracle Java SE 17 API, **`com.sun.management.OperatingSystemMXBean`** — các phương thức stable cho Java 17+: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- Oracle Java SE 26 API, **`java.lang.management.OperatingSystemMXBean`** — `getAvailableProcessors` và `getSystemLoadAverage`: https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html
- Oracle Java SE 26 API, **`ManagementFactory`** — local/remote MXBeans và `ObjectName`: https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html
