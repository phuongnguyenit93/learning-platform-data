# ClassLoadingMXBean: tổng lớp đã nạp, lớp hiện có và lớp đã dỡ trong JVM

`java.lang.management.ClassLoadingMXBean` là một **MXBean thuộc Java Management API** để quan sát **tình hình class loading của toàn bộ JVM**. Nó không tự nạp, dỡ hoặc giải phóng class: nhiệm vụ của nó là **cung cấp số liệu tổng hợp** và một tùy chọn bật/tắt verbose output về hoạt động nạp/dỡ lớp.

Các chỉ số cơ bản:

1. `getTotalLoadedClassCount()` — **tổng số class đã được JVM nạp từ lúc bắt đầu chạy** (bộ đếm tích lũy).
2. `getLoadedClassCount()` — **số class hiện đang được JVM coi là loaded** tại thời điểm lấy mẫu.
3. `getUnloadedClassCount()` — **tổng số class đã được JVM dỡ từ lúc bắt đầu chạy** (bộ đếm tích lũy).
4. `isVerbose()`/`setVerbose(boolean)` — trạng thái và điều khiển verbose class-loading output (phạm vi JVM, không phải riêng một loader).

Điểm đặc biệt quan trọng với hệ thống plugin: **ba số liệu này có phạm vi toàn JVM**, không phân loại sẵn theo tên plugin, JAR, ClassLoader instance hay module. Muốn tìm class nào/loader nào đang giữ bộ nhớ, cần kết hợp công cụ khác (JFR, JVM logging, thread dumps, JMX, classloader statistics và heap analysis).

Bài này giải thích API chính xác, sự khác biệt giữa ba bộ đếm, cách đọc chúng trong ứng dụng và qua JMX, cách tính biến thiên/đánh giá classloader leaks, những giới hạn không thể suy ra từ một snapshot, và một ví dụ Java 17+ **tải một class bằng hai loaders độc lập** để quan sát số liệu tăng.

## 1. Vì sao cần quan sát class loading?

JVM nạp class khi chương trình cần dùng class ấy, thông qua hệ thống class loaders và các quy tắc JVMS. Ngoài mã ứng dụng, JVM có thể nạp thêm:

- Core Java/platform/library classes.
- Class của ứng dụng và dependency JARs.
- Dynamic proxies, lambda-related implementations, generated adapters hoặc bytecode do framework sinh.
- Class riêng từ plugin loaders, OSGi/container classloader hierarchies hoặc modular environments.
- Các class được nạp do reflection, `ServiceLoader` và dependency resolution khi cần.

Nếu một dịch vụ liên tục deploy/redeploy plugin, tạo classloader mới hoặc sinh class động, **tổng số class đã nạp** có thể tăng nhanh. Nếu các loader cũ không thể được thu gom, **số class hiện loaded** cũng có thể tích lũy, kéo theo sử dụng native metadata/metaspace và các tài nguyên khác.

`ClassLoadingMXBean` giúp trả lời những câu hỏi đầu tiên:

~~~text
Tổng số class từng được nạp tăng bao nhiêu?
              |
Hiện tại còn bao nhiêu class loaded?
              |
Đã có bao nhiêu class thực sự unloaded?
              |
Xu hướng qua nhiều phút/giờ/deploy là gì?
~~~

Nhưng nó **không trả về danh sách các class** hoặc nguyên nhân tại sao một loader chưa được GC. Chẩn đoán leak cần nhiều lớp bằng chứng hơn một biểu đồ class count.

## 2. Vị trí của ClassLoadingMXBean trong Java Management

Từ Java 5, JMX platform management cung cấp bean cho class loading. Trên Java 17, API thuộc module chuẩn `java.management`:

~~~text
Module java.management
   |
   +-- java.lang.management.ManagementFactory
   |
   +-- java.lang.management.ClassLoadingMXBean
   |
   +-- java.lang.management.MemoryMXBean
   +-- java.lang.management.MemoryPoolMXBean
   +-- java.lang.management.ThreadMXBean
   ...
~~~

Lấy một bean toàn JVM:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

ClassLoadingMXBean bean =
        ManagementFactory.getClassLoadingMXBean();
~~~

Đây là **mảnh API minh họa**, có thể đặt trong `main`/method để dùng. Một JVM có **một instance class-loading management bean theo hợp đồng**, và bean này cũng được đăng ký trong **platform MBeanServer**.

ObjectName chuẩn:

~~~text
java.lang:type=ClassLoading
~~~

Có thể lấy từ:

~~~java
System.out.println(bean.getObjectName());
~~~

`ClassLoadingMXBean` kế thừa `PlatformManagedObject`, nên method `getObjectName()` trả đối tượng JMX `ObjectName` tương ứng.

### Ba counters cốt lõi

| Method | Kiểu trả về | Nghĩa |
|---|---|---|
| `getLoadedClassCount()` | `int` | Hiện tại JVM có bao nhiêu class đang loaded |
| `getTotalLoadedClassCount()` | `long` | Tổng class đã nạp kể từ lúc JVM bắt đầu |
| `getUnloadedClassCount()` | `long` | Tổng class đã unloaded kể từ lúc JVM bắt đầu |

Không nhầm `getLoadedClassCount()` với `getTotalLoadedClassCount()`: **loaded hiện tại** có thể giảm sau khi một số class được unload, còn **total loaded** là tổng tích lũy suốt vòng đời JVM và không giảm.

## 3. Mối quan hệ giữa tổng đã nạp, hiện có và đã dỡ

Về mặt diễn giải, các chỉ số mô tả:

~~~text
              Classes từng được loaded
                         |
               +---------+----------+
               |                    |
          Vẫn loaded          Đã unloaded
               |                    |
  getLoadedClassCount()  getUnloadedClassCount()
               \                    /
                \                  /
         getTotalLoadedClassCount()
             (tích lũy)
~~~

Trong một ảnh chụp lý tưởng cùng thời điểm:

~~~text
Total loaded ≈ Currently loaded + Total unloaded
~~~

Tại sao dùng dấu **`≈` thay vì bắt buộc `==` cho ba lời gọi liên tiếp**?

- Ba method được gọi **lần lượt**, không phải một API atomic snapshot của cả ba counters.
- JVM có thể load hoặc unload class giữa những lần đọc.
- Việc nạp lớp có thể diễn ra ngầm do compiler/JIT, reflection, instrumentation hoặc thread khác.
- Các implementation có thể có chi tiết đo lường khác nhau; ứng dụng không nên phụ thuộc vào invariant **đo được chính xác** trong mọi race.

Do đó, không lấy một mẫu rồi throw exception chỉ vì phép cộng số học **không tuyệt đối bằng nhau**. Khi cần phân tích xu hướng, lấy mẫu theo chu kỳ, lưu timestamp và phân biệt số liệu tích lũy với số liệu tức thời.

### Minh họa bằng số giả định

Giả sử một JVM ở thời điểm T1:

| Chỉ số | T1 |
|---|---:|
| Total loaded | 12.000 |
| Currently loaded | 11.850 |
| Total unloaded | 150 |

Đây là **số liệu ví dụ**, không phải output cố định của bất kỳ chương trình nào.

Sau một đợt tải plugins, tại T2:

| Chỉ số | T2 |
|---|---:|
| Total loaded | 12.500 |
| Currently loaded | 12.300 |
| Total unloaded | 200 |

Ta có:

- `Δtotal = 500`: JVM đã nạp thêm 500 class trong khoảng thời gian quan sát.
- `Δunloaded = 50`: thêm 50 class đã unload.
- `Δcurrent = 450`: số class hiện tại nhiều hơn 450.
- Chưa thể kết luận 450 class ấy thuộc plugin cụ thể nào hoặc là leak, vì hệ thống có thể đang warm up và cache class một cách hợp lệ.

Đừng dùng `getTotalLoadedClassCount()` làm “số class còn chiếm metaspace hiện tại”; đó là **counter tích lũy**.

## 4. Code đọc metrics đơn giản

Mảnh Java:

~~~java
ClassLoadingMXBean bean =
        ManagementFactory.getClassLoadingMXBean();

long total = bean.getTotalLoadedClassCount();
int current = bean.getLoadedClassCount();
long unloaded = bean.getUnloadedClassCount();

System.out.println("total=" + total);
System.out.println("current=" + current);
System.out.println("unloaded=" + unloaded);
~~~

Đây là đoạn minh họa, cần hai imports `ClassLoadingMXBean` và `ManagementFactory`. Output là **số thực tế của JVM**, phụ thuộc JDK, command-line flags, classpath, những lớp đã warm up và việc JVM có unload class hay không.

**Không có bộ số “total=1234/current=...” cố định** cho mọi máy. Khi viết bài học hoặc test, hãy kiểm tra **quan hệ, biến thiên hoặc định dạng**, không hard-code các số counters.

### Đọc đúng kiểu số

- `getTotalLoadedClassCount()` trả `long`.
- `getUnloadedClassCount()` trả `long`.
- `getLoadedClassCount()` trả `int`.

Đừng ép cả ba sang `int` hoặc parse chuỗi log để làm metrics nếu có thể gọi trực tiếp API. Với thời gian dài, các counters tích lũy có thể lớn.

### Quan sát theo mốc thời gian

~~~java
record Sample(
        long nanoTime,
        long totalLoaded,
        int currentlyLoaded,
        long unloaded) {
}

static Sample sample(ClassLoadingMXBean bean) {
    return new Sample(
            System.nanoTime(),
            bean.getTotalLoadedClassCount(),
            bean.getLoadedClassCount(),
            bean.getUnloadedClassCount());
}
~~~

Đây là **mảnh minh họa**, phù hợp khi `ClassLoadingMXBean` đã import. `System.nanoTime()` dành cho **thời gian trôi qua trong cùng process**, không phải wall-clock timestamp hay thời gian Unix. Nếu cần log sự kiện theo lịch, ghi thêm `Instant.now()`.

## 5. Ví dụ Java 17+ hoàn chỉnh: nạp một class từ hai loaders

Thí nghiệm dùng:

- Một class `experiment.Marker` được compile vào thư mục plugin riêng.
- Một host class `ClassLoadingLab` chỉ có trên application classpath.
- Hai `URLClassLoader` độc lập, cùng có root tới `out/plugin`.
- Hai runtime `Class<?>` cùng binary name nhưng khác defining loader.
- `ClassLoadingMXBean` được lấy mẫu trước và sau khi cả hai class được loaded.

Mục tiêu là kiểm tra **sự kiện và quan hệ có thể dự đoán** thay vì in số counters tuyệt đối không thể đoán trước giữa các JDK.

### 5.1. Cấu trúc project

~~~text
project/
  src/
    plugin/
      experiment/
        Marker.java
    host/
      ClassLoadingLab.java
  out/
    plugin/
    host/
~~~

### 5.2. File `src/plugin/experiment/Marker.java`

~~~java
package experiment;

public final class Marker {
    public String id() {
        return "marker";
    }
}
~~~

Class chỉ dùng core `java.base` types, không có dependency của host. Như vậy việc chọn `ClassLoader.getPlatformClassLoader()` làm parent cho hai plugin loaders trong thí nghiệm này không gây thiếu shared host API.

### 5.3. File `src/host/ClassLoadingLab.java`

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class ClassLoadingLab {
    private static final String PLUGIN_CLASS = "experiment.Marker";

    record Sample(long total, int current, long unloaded) {
    }

    static Sample read(ClassLoadingMXBean bean) {
        return new Sample(
                bean.getTotalLoadedClassCount(),
                bean.getLoadedClassCount(),
                bean.getUnloadedClassCount());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ClassLoadingLab <plugin-dir>");
        }

        ClassLoadingMXBean bean =
                ManagementFactory.getClassLoadingMXBean();

        URL url = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();

        Sample before = read(bean);

        try (URLClassLoader loaderA = new URLClassLoader(
                    "plugin-A", new URL[] {url},
                    ClassLoader.getPlatformClassLoader());
             URLClassLoader loaderB = new URLClassLoader(
                    "plugin-B", new URL[] {url},
                    ClassLoader.getPlatformClassLoader())) {

            Class<?> first = loaderA.loadClass(PLUGIN_CLASS);
            Class<?> second = loaderB.loadClass(PLUGIN_CLASS);

            Sample after = read(bean);

            System.out.println("mxbean name correct: "
                    + bean.getObjectName().getCanonicalName()
                        .equals("java.lang:type=ClassLoading"));

            System.out.println("same binary name: "
                    + first.getName().equals(second.getName()));
            System.out.println("same runtime class: "
                    + (first == second));

            System.out.println("A defines its class: "
                    + (first.getClassLoader() == loaderA));
            System.out.println("B defines its class: "
                    + (second.getClassLoader() == loaderB));

            System.out.println("total loaded grew by at least two: "
                    + (after.total() >= before.total() + 2));

            System.out.println("unloaded count nondecreasing: "
                    + (after.unloaded() >= before.unloaded()));

            System.out.println("current loaded count positive: "
                    + (after.current() > 0));
        }
    }
}
~~~

**Chi tiết quan trọng:**

1. `getClassLoadingMXBean()` cung cấp một bean quan sát **toàn JVM**, không riêng loader A/B.
2. `Sample before` được lấy **trước** khi tạo và dùng hai URLClassLoader.
3. Parent là platform loader, không có class `experiment.Marker` trên application classpath; cả A và B phải tự tìm `experiment/Marker.class` dưới URL root.
4. `loaderA.loadClass` và `loaderB.loadClass` định nghĩa hai runtime classes với **cùng binary name** nhưng khác defining loaders. Do vậy `first == second` là `false`.
5. Hai class definitions mới đóng góp vào **total loaded**; có thể còn những class khác do JVM tải trong quá trình thí nghiệm, nên kiểm tra `>= 2` chứ **không** kiểm tra đúng bằng 2.
6. `getUnloadedClassCount()` là counter tích lũy, không giảm trong một JVM; khi còn giữ `first`/`second`/loaders trong khối, **không** khẳng định chúng đã unloaded.
7. `getLoadedClassCount()` ở trạng thái JVM hoạt động là giá trị dương; không so `after.current() - before.current() == 2` do concurrency/unloading có thể thay đổi giá trị hiện tại.

### 5.4. Compile và chạy bằng JDK 17+

Từ thư mục `project`, chạy bằng Bash trên Linux/macOS hoặc môi trường Bash tương thích:

~~~bash
mkdir -p out/plugin out/host

javac -d out/plugin src/plugin/experiment/Marker.java

javac -d out/host src/host/ClassLoadingLab.java

java -cp out/host ClassLoadingLab out/plugin
~~~

**Không thêm `out/plugin` vào application classpath**, nếu không parent/caller có thể nhìn thấy class trước và không còn đảm bảo hai child loaders tự định nghĩa.

Trên Windows PowerShell, tạo output directories bằng `New-Item -ItemType Directory -Force` rồi chạy `javac`/`java` tương ứng. Vì classpath host chỉ có **một** phần tử, không cần dấu phân cách `:` hoặc `;`.

### 5.5. Stdout dự kiến

~~~text
mxbean name correct: true
same binary name: true
same runtime class: false
A defines its class: true
B defines its class: true
total loaded grew by at least two: true
unloaded count nondecreasing: true
current loaded count positive: true
~~~

Output trên dựa vào class file đúng, không có bản `experiment.Marker` ở parent, hai URLClassLoader khác nhau và JVM tuân thủ counters `ClassLoadingMXBean`. **Số đếm thực tế không được in**, vì chúng có thể thay đổi theo JDK/OS/classpath/GC.

### 5.6. Vì sao đóng loaders không đồng nghĩa class unloading?

Khi thoát khối `try-with-resources`, các `URLClassLoader` đóng các tài nguyên file/JAR đã mở. Điều này **không buộc** VM dỡ `experiment.Marker` ngay khi kết thúc khối.

Để có cơ hội class unloading, phải không còn strong references tới:

- Loader instances, `Class<?>` hoặc objects do class ấy tạo.
- Threads, scheduled tasks, TCCL hoặc `ThreadLocal` trỏ tới loader.
- Reflection `Method`/`Constructor`, `MethodHandle`, service providers hoặc caches của framework.
- JNI global references, listeners, callbacks hoặc registries giữ plugin generation.

Kể cả khi mọi reference đã giải phóng, JVM có thể chọn thời điểm GC/unloading khác nhau. **`System.gc()` không phải cam kết unload class**, và việc `getUnloadedClassCount()` không tăng ngay **không chứng minh có leak**.

## 6. Thu thập metrics theo chu kỳ trong service thật

Trong production, snapshot một lần không đủ. Nên lấy mẫu tại chu kỳ xác định (ví dụ 10–60 giây tùy nhu cầu) và kèm timestamp:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.time.Instant;

public final class ClassLoadingSnapshot {
    public static void main(String[] args) {
        ClassLoadingMXBean bean =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("timestamp=" + Instant.now());
        System.out.println("loaded_current="
                + bean.getLoadedClassCount());
        System.out.println("loaded_total="
                + bean.getTotalLoadedClassCount());
        System.out.println("unloaded_total="
                + bean.getUnloadedClassCount());
    }
}
~~~

Đây là **chương trình độc lập** để lấy snapshot hiện tại. Chạy:

~~~bash
javac ClassLoadingSnapshot.java
java ClassLoadingSnapshot
~~~

Output là **timestamp và những số liệu động**, ví dụ minh họa:

~~~text
timestamp=2026-10-24T12:00:00Z
loaded_current=1200
loaded_total=1200
unloaded_total=0
~~~

Các con số/timestamp **chỉ mang tính minh họa**, không phải stdout cố định. Điều quan trọng là API/field names và tính thời điểm.

**Lưu ý:** chạy `java ClassLoadingSnapshot` nhiều lần tạo **nhiều JVM khác nhau**, vì vậy không tạo chuỗi timeseries của **cùng một process**. Để đo xu hướng của ứng dụng đang chạy, thu metrics từ **bên trong JVM đó** hoặc dùng JMX/metrics exporter gắn tới cùng process.

### Lưu delta thay vì chỉ lưu giá trị tuyệt đối

Nếu có hai mẫu T1/T2:

~~~text
total_loads_per_interval  = totalLoaded(T2) - totalLoaded(T1)
unloads_per_interval      = unloaded(T2) - unloaded(T1)
current_loaded_change     = currentlyLoaded(T2) - currentlyLoaded(T1)
rate_total_loads_per_sec  = deltaTotal / elapsedSeconds
~~~

Tính rate bằng **thời gian thực tế giữa hai lần sample**. Đừng dùng “tổng class từng loaded” để suy ra classload rate trực tiếp nếu không có mẫu trước.

**Counter reset:** tất cả chỉ số tích lũy bắt đầu lại khi JVM restart. Khi làm time-series, gắn **process identity / start time** và xử lý reset; không tính delta âm giữa hai JVM thành “JVM unload hàng ngàn class”.

### Sơ đồ dashboard

~~~text
JVM process (PID + startTime)
         |
         +-- loaded_class_count (gauge)
         |
         +-- total_loaded_class_count (cumulative counter)
         |
         +-- total_unloaded_class_count (cumulative counter)
         |
         +-- load_rate = delta(total) / delta(time)
         |
         +-- unload_rate = delta(unloaded) / delta(time)
         |
         +-- metaspace_used / committed (nguồn memory MXBean khác)
         |
         +-- loader count / GC / deployment events (nguồn bổ sung)
~~~

`getLoadedClassCount()` phù hợp như **gauge**; `getTotalLoadedClassCount()` và `getUnloadedClassCount()` phù hợp như **counters**. Đừng publish tất cả ba metric theo kiểu counter hoặc đánh đồng class count với byte-size memory.

## 7. Đọc ClassLoadingMXBean qua JMX

`ClassLoadingMXBean` có ObjectName cố định:

~~~text
java.lang:type=ClassLoading
~~~

Trong `MBeanServer`, những attributes tương ứng thường là:

| Attribute JMX | Java method |
|---|---|
| `LoadedClassCount` | `getLoadedClassCount()` |
| `TotalLoadedClassCount` | `getTotalLoadedClassCount()` |
| `UnloadedClassCount` | `getUnloadedClassCount()` |
| `Verbose` | `isVerbose()`, `setVerbose(boolean)` |

### 7.1. Ví dụ đọc MBeanServer ngay trong JVM

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxClassLoadingSample {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();
        ObjectName key =
                new ObjectName("java.lang:type=ClassLoading");

        Object loaded =
                server.getAttribute(key, "LoadedClassCount");
        Object total =
                server.getAttribute(key, "TotalLoadedClassCount");
        Object unloaded =
                server.getAttribute(key, "UnloadedClassCount");

        System.out.println("loaded numeric: "
                + (loaded instanceof Number));
        System.out.println("total numeric: "
                + (total instanceof Number));
        System.out.println("unloaded numeric: "
                + (unloaded instanceof Number));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac JmxClassLoadingSample.java
java JmxClassLoadingSample
~~~

Stdout dự kiến:

~~~text
loaded numeric: true
total numeric: true
unloaded numeric: true
~~~

Đây là một cách minh họa **JMX attribute access**, không cần viết riêng MXBean implementation. Đừng kỳ vọng JMX tự trả danh sách những class đang loaded; các attributes này vẫn là counters tổng JVM.

### 7.2. Xem qua JConsole/JMX client

Với process Java đã chạy và cho phép attach/JMX theo môi trường:

1. Khởi động **JConsole** từ JDK hoặc một JMX client đã cấu hình phù hợp.
2. Kết nối đúng process/JVM.
3. Mở phần **MBeans**, tìm `java.lang:type=ClassLoading`.
4. Đọc `LoadedClassCount`, `TotalLoadedClassCount`, `UnloadedClassCount` và `Verbose`.
5. Ghi lại mốc trước/sau khi deploy hoặc unload plugin, rồi so với memory/GC/logs.

Kết nối **remote JMX** phải được bảo vệ đúng authentication, authorization và network policy; không bật JMX port công khai chỉ để đọc counters. Trong một số container/production environments, attach có thể bị vô hiệu hóa hoặc cần cấu hình riêng.

## 8. `isVerbose()` và `setVerbose(boolean)`

Bên cạnh counters, bean cung cấp:

~~~java
boolean enabled = bean.isVerbose();
bean.setVerbose(true);
~~~

Đây là mảnh API, yêu cầu `bean` là `ClassLoadingMXBean`. `setVerbose(true)` yêu cầu VM bật thêm output khi class load/unload; `setVerbose(false)` tắt ở phạm vi **toàn JVM**.

**Những điểm cần nhớ:**

- Đây **không phải** setting chỉ cho một classloader hoặc plugin.
- Thay đổi ảnh hưởng đến các threads/code khác trong cùng process.
- Format và nơi phát output là **implementation-dependent**, không thể cam kết mỗi JDK in một format giống nhau.
- Có thể gây output/log volume đáng kể, ảnh hưởng hiệu năng và khả năng quan sát log.
- Theo hợp đồng API Java 17, có thể phát sinh `SecurityException` nếu môi trường có security manager và không đủ `ManagementPermission("control")`.
- Nhiều thread có thể gọi `setVerbose`, nhưng chúng thay đổi **một global setting**, không phải một setting tách biệt per caller.

Không nên đặt:

~~~java
bean.setVerbose(true);
~~~

trong mọi request handler chỉ để debug một plugin; thao tác đó tạo side effect toàn JVM. Trong môi trường production, ưu tiên JVM logging/JFR có cấu hình, thời hạn và chính sách quan sát rõ ràng.

### Bật class loading logs trên HotSpot Java 17

Ví dụ:

~~~bash
java -Xlog:class+load=info,class+unload=info \
     -cp out/host ClassLoadingLab out/plugin
~~~

Đây là **lệnh chẩn đoán trên HotSpot/JDK phù hợp**. Output sẽ có thêm nhiều log lines, không còn giống stdout gọn ở phần ví dụ. Việc log ở mức `info` thường giúp thấy nhiều class đã load và nguồn của chúng, nhưng có thể không giải thích đầy đủ **tại sao** mỗi class được giữ sống.

JDK khác có logging flags/format khác; luôn kiểm tra hỗ trợ của runtime thực.

## 9. Dùng metrics để nhận diện classloader leak

Một tình huống điển hình:

~~~text
Plugin generation 1 -> loader A -> 100 classes
Plugin generation 2 -> loader B -> 100 classes
Plugin generation 3 -> loader C -> 100 classes
...
Host vẫn giữ reference tới A, B, C
       |
       v
getLoadedClassCount() tăng dài hạn
getTotalLoadedClassCount() tăng dài hạn
getUnloadedClassCount() tăng ít hoặc không tăng
Metaspace có thể tăng
~~~

Tuy nhiên, **đây mới là tín hiệu nghi ngờ, không phải bằng chứng cuối cùng**.

### 9.1. Mô hình phân tích trước/sau deploy

| Thời điểm | Total | Current | Unloaded | Ghi chú |
|---|---:|---:|---:|---|
| Trước deploy | 10.000 | 9.900 | 100 | Baseline |
| Sau deploy plugin | 10.300 | 10.200 | 100 | Nạp class plugin |
| Sau undeploy, chờ và GC quan sát | 10.350 | 10.050 | 300 | Một phần đã unload |
| Sau nhiều redeploy | 12.500 | 11.900 | 600 | Cần điều tra xu hướng |

Tất cả **giá trị ở bảng là dữ liệu giả định để học cách đọc**, không phải kết quả thực nghiệm.

Đặc biệt, chỉ từ ví dụ này không thể khẳng định chính xác class nào bị giữ hoặc GC có tạo class unloading ngay. Cần quan sát **trong cùng JVM** và so sánh với deployment events, memory pools, classloader statistics, heap dump và lifecycle của plugin.

### 9.2. Vì sao total luôn tăng không đồng nghĩa leak?

`TotalLoadedClassCount` là counter tích lũy nên **sẽ không giảm**, kể cả khi JVM unload tất cả class thuộc plugin cũ. Một hệ thống khỏe mạnh vẫn có thể tăng total hàng giờ vì:

- Framework khởi tạo những features mới.
- Dynamic proxies/lambdas/generated classes xuất hiện khi tải workload mới.
- Plugins được cập nhật hợp lệ.
- New application code paths được chạm lần đầu.
- JVM/app warm-up chưa kết thúc.

Tín hiệu đáng quan tâm hơn là **current loaded class count** tiếp tục tăng sau nhiều chu kỳ ổn định và không giảm khi lifecycle/GC đủ điều kiện, đặc biệt khi metaspace và số lượng loader cũng tăng.

### 9.3. Vì sao unloaded chưa tăng không khẳng định leak?

Class unloading thường gắn với **garbage collection và điều kiện reachability của defining loader**. Không có bảo đảm `close()` hoặc `System.gc()` khiến count tăng ngay. JVM flags, collector, memory pressure và references còn giữ class/loader đều ảnh hưởng.

Không đặt test:

~~~java
System.gc();
assert bean.getUnloadedClassCount() > before;
~~~

làm **điều kiện pass bắt buộc** cho mọi JDK; đây là anti-pattern vì GC/unloading không deterministic.

## 10. Khi số class tăng, cần tìm holder ở đâu?

`ClassLoadingMXBean` chỉ có tổng số liệu toàn JVM; nó không chỉ ra cache, thread hay plugin loader nào giữ classes. Nếu `LoadedClassCount` cùng metaspace và số loader tăng qua nhiều chu kỳ redeploy, hãy khảo sát các nguồn giữ phổ biến: static registries của host, listener/callback, queued task, TCCL của thread pool, `ThreadLocal`, provider cache, JNI references và plugin-owned executors.

Để phân biệt chúng, kết hợp `jcmd VM.classloader_stats`/JFR với heap dump và **Path to GC Roots**; xác nhận holder vẫn không cần thiết sau khi plugin stop rồi mới kết luận là leak. Bài về JFR, heap dump và GC roots hướng dẫn chứng minh retention, còn bài này tập trung **đếm class và lập chuỗi thời gian các metrics**.
## 11. Kết hợp với metaspace và memory metrics

Một class được loaded tiêu thụ metadata/memory ở JVM, nhưng **không có phép quy đổi cố định “1 class = X bytes metaspace”**. Size phụ thuộc methods, constant pool, annotations, class structure, runtime implementation và nhiều yếu tố.

`ClassLoadingMXBean` **không có** method kiểu:

~~~java
bean.getMetaspaceBytes();
~~~

Đây là **API không tồn tại**, chỉ để cảnh báo ngộ nhận. Để đo memory, dùng `MemoryPoolMXBean`, `MemoryMXBean`, JVM tools hoặc JFR.

Ví dụ đọc các memory pools có tên chứa Metaspace (phù hợp HotSpot, **không portable theo tên pool**):

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;

for (MemoryPoolMXBean pool
        : ManagementFactory.getMemoryPoolMXBeans()) {
    if (pool.getName().contains("Metaspace")) {
        MemoryUsage usage = pool.getUsage();
        if (usage != null) {
            System.out.println(usage.getUsed());
        }
    }
}
~~~

Đây là mảnh minh họa; tên pool có thể khác theo JVM, và output bytes phụ thuộc runtime. Không dùng số `Metaspace used` để suy ra số class bị leak một cách một-một.

### Khi nào cần thêm công cụ?

| Câu hỏi | Công cụ / tín hiệu |
|---|---|
| Tổng số class đã được load? | `ClassLoadingMXBean.getTotalLoadedClassCount()` |
| Hiện tại còn bao nhiêu class? | `getLoadedClassCount()` |
| Đã unload bao nhiêu? | `getUnloadedClassCount()` |
| Class nào được load từ JAR nào? | Unified JVM class-loading logs, JFR/JVM-specific tools |
| Bao nhiêu classloaders đang sống? | JFR, `jcmd`/VM-specific classloader stats hoặc heap analysis |
| Metaspace đang tăng? | `MemoryPoolMXBean`/JVM memory metrics |
| Tại sao plugin loader không unload? | Heap dump reference paths, thread/TCCL inspection, native references |
| Classloader có đang giữ JAR handles? | Lifecycle log, URLClassLoader close, OS file handle tools |

## 12. Sự khác biệt giữa class loading, linking và initialization

Một source Java được compile thành `.class` **không đồng nghĩa JVM đã loaded nó**. Loader phải tìm định nghĩa phù hợp, JVM phải link/verify/resolve theo quy tắc và class có thể được initialized khi active use.

~~~text
Source .java
     |
   javac
     |
 .class file / JAR entry
     |
 ClassLoader.loadClass(...)
     |
 JVM class loading
     |
 Linking (verify/prepare/resolve theo nhu cầu)
     |
 Initialization (static init nếu được yêu cầu)
     |
 Instance/method execution
~~~

`ClassLoadingMXBean` quan sát **class loading/unloading counts**, không cung cấp một counter riêng cho mọi bước verification, linking hoặc initialization. Đừng dùng “totalLoaded tăng 1” để kết luận constructor của class đã chạy.

Ví dụ:

~~~java
Class<?> type =
        Class.forName("experiment.Marker", false, pluginLoader);
~~~

Đây là mảnh minh họa với `pluginLoader` phù hợp. Lời gọi có thể load/link class nhưng **không yêu cầu class initialize** do `initialize=false`. TotalLoaded có thể tăng, dù static initializer chưa chạy.

### Class identity với nhiều loaders

Hai loaders có thể nạp cùng tên class nhưng tạo **hai runtime types** riêng:

~~~text
("experiment.Marker", LoaderA) !=
("experiment.Marker", LoaderB)
~~~

`ClassLoadingMXBean` **không gộp hai types chỉ vì tên giống nhau** thành một entry logic theo tên. Nó đo các runtime classes được nạp trong JVM. Đây là lý do số loaded classes tăng khi tạo plugin loaders định nghĩa các bản riêng của cùng dependency.

Không vì thế mà tạo một loader mới cho mỗi request: nhiều bản class definitions trùng có thể gây tăng memory và classloading overhead.

## 13. Những sai lầm thường gặp khi dùng ClassLoadingMXBean

1. **“Total loaded là số class còn trong bộ nhớ.”** Sai: đó là số tích lũy kể từ khi JVM khởi động.
2. **“Unloaded là số class đã được xóa khỏi JAR.”** Sai: đây là count runtime class unloading, không liên quan xóa file JAR.
3. **“Loaded hiện tại không bao giờ giảm.”** Sai: JVM có thể unload classes khi điều kiện GC/reachability thỏa.
4. **“`ClassLoadingMXBean` trả class names.”** Sai: nó cung cấp counts, không phải danh sách class/JAR/loader.
5. **“`ClassLoadingMXBean` thuộc từng ClassLoader.”** Sai: chỉ số có phạm vi **toàn JVM**.
6. **“Một class name chỉ được đếm đúng một lần trong toàn JVM.”** Sai: cùng binary name do loaders khác nhau define là runtime types khác nhau.
7. **“Ba lời gọi đọc counters là một atomic snapshot.”** Sai: class loading/unloading có thể xảy ra giữa chúng.
8. **“`getTotalLoadedClassCount()` phải giảm khi GC.”** Sai: nó là counter tích lũy.
9. **“Unloaded count chưa tăng sau `System.gc()` là leak chắc chắn.”** Sai: GC/unloading không được cam kết đồng bộ ngay.
10. **“Loaded count tăng một lần sau startup chứng tỏ leak.”** Sai: warm-up và feature loading bình thường cũng tăng.
11. **“Metaspace bytes có thể tính bằng loaded classes × một hằng số.”** Sai: metadata footprint biến động.
12. **“`setVerbose(true)` chỉ bật log cho current thread.”** Sai: global JVM setting.
13. **“`setVerbose(true)` luôn in trên stdout theo cùng format.”** Sai: output format/stream do JVM implementation quyết định.
14. **“Đọc bean bằng JMX bắt buộc mở một server remote.”** Sai: có thể lấy trong cùng JVM qua `ManagementFactory` hoặc platform MBeanServer.
15. **“Bean có thể bắt JVM unload đúng một class cụ thể.”** Sai: không có API unload từng class theo tên.
16. **“Plugin loader close tương đương class unloading.”** Sai: close handles và unloading là hai cơ chế khác.
17. **“Đếm class đủ để chẩn đoán mọi memory leak.”** Sai: còn threads, heap objects, native memory, metaspace và classloader reachability.
18. **“Nhiều tiến trình có thể cộng counters mà không cần identity.”** Sai: cần gắn PID/JVM start time để xử lý counter reset và tránh nhầm process.
19. **“Một `Class<?>` từ loader A có thể tái dùng như class của loader B.”** Sai: runtime class identity phụ thuộc defining loader.
20. **“`getLoadedClassCount()` phản ánh số file `.class` trong package/JAR.”** Sai: nó đếm runtime classes đang loaded, không quét filesystem.

## 14. Checklist observability trước khi kết luận classloader leak

- [ ] Lấy bean đúng qua `ManagementFactory.getClassLoadingMXBean()`.
- [ ] Ghi rõ cả ba chỉ số: total loaded, current loaded, total unloaded.
- [ ] Phân biệt **counter tích lũy** với **gauge tức thời**.
- [ ] Gắn sample timestamp, PID/process identity và JVM start time.
- [ ] Lấy nhiều mẫu ở cùng một JVM, không lấy nhiều lần chạy `java` khác nhau.
- [ ] Tính delta và rate đúng khoảng thời gian.
- [ ] So sánh trước/sau deployment, redeploy, shutdown theo cùng workload.
- [ ] Cho JVM đủ thời gian GC/unloading khi đánh giá xu hướng; không ép một lần GC là test pass.
- [ ] Quan sát Metaspace và số loaders từ nguồn phù hợp nếu nghi leak.
- [ ] Lưu log class sources/loader IDs khi cần tìm plugin cụ thể.
- [ ] Kiểm tra caches, TCCL, threads, scheduled tasks, callbacks, registries, JNI refs.
- [ ] Có cơ chế drain rồi đóng URLClassLoader nếu dùng plugin JAR.
- [ ] Không bật `setVerbose(true)` vô thời hạn trên JVM nhiều traffic.
- [ ] Giới hạn quyền truy cập JMX; tránh remote exposure không bảo vệ.
- [ ] Không hard-code expected counters của bất kỳ JVM cụ thể nào.
- [ ] Nếu ứng dụng modular, phân biệt class loading stats với module readability/opens/exports.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `getTotalLoadedClassCount()` và `getLoadedClassCount()` khác nhau như thế nào?

**Đáp án:** Total là tổng lớp từng loaded kể từ lúc JVM khởi động; current là số lớp hiện loaded tại thời điểm đọc. Total không giảm vì class unloading.

**Câu 2.** `getUnloadedClassCount()` tăng sau một giai đoạn có nghĩa gì?

**Đáp án:** JVM đã unload thêm class trong giai đoạn đó. Chưa thể xác định class hoặc loader cụ thể nào nếu không có thêm nguồn chẩn đoán.

**Câu 3.** Có thể suy ra classloader bị leak chỉ vì TotalLoaded liên tục tăng không?

**Đáp án:** Không. Total là cumulative, tăng theo hoạt động hợp lệ. Cần xem current, unloaded, metaspace, loader count và retention/lifecycle theo thời gian.

**Câu 4.** `LoadedClassCount` có phân theo plugin JAR không?

**Đáp án:** Không. Đây là số liệu toàn JVM. Muốn truy class/loader cụ thể cần logs, JFR, jcmd hoặc heap analysis.

**Câu 5.** Hai URLClassLoader định nghĩa cùng `experiment.Marker`. Có hai runtime class types không?

**Đáp án:** Có. Cùng binary name nhưng khác defining loader tạo hai `Class<?>` khác identity; chúng đóng góp vào classloading counters.

**Câu 6.** `URLClassLoader.close()` có bảo đảm `UnloadedClassCount` tăng ngay không?

**Đáp án:** Không. Close file/JAR handles, còn class unloading phụ thuộc references/GC.

**Câu 7.** `setVerbose(true)` có thay đổi riêng một plugin không?

**Đáp án:** Không. Nó thay đổi verbose class-loading output của toàn JVM; nhiều threads có thể bị ảnh hưởng.

**Câu 8.** Cần ObjectName nào khi đọc qua JMX?

**Đáp án:** `java.lang:type=ClassLoading`, với attributes như `LoadedClassCount`, `TotalLoadedClassCount` và `UnloadedClassCount`.

**Câu 9.** Vì sao ba counters đọc liên tiếp đôi khi không khớp phép tính `total == current + unloaded` một cách chính xác?

**Đáp án:** Vì các lời gọi không tạo một atomic snapshot; JVM có thể load/unload giữa các lần đọc.

**Câu 10.** Sau một tuần, current loaded và metaspace tăng sau mỗi redeploy, unloaded hầu như không tăng. Bước kế tiếp là gì?

**Đáp án:** Điều tra retention: heap dump, loader statistics, threads/TCCL, static caches, service providers, JNI refs và plugin lifecycle. Counters là tín hiệu, chưa đủ làm kết luận cuối.

## 16. Sơ đồ quyết định chẩn đoán

~~~text
                 Quan sát class loading trong JVM
                              |
                  ManagementFactory.get...
                              |
                  ClassLoadingMXBean
                      /       |       \
                     /        |        \
            total loaded    current    unloaded
             (counter)       (gauge)   (counter)
                    \         |        /
                     \        |       /
                       Samples + time
                              |
                       Tính deltas/rates
                              |
                    Có tăng bất thường?
                        /           \
                      Không          Có
                       |             |
                  Lưu baseline     Xem Metaspace,
                                   loader count,
                                   deployment events
                                       |
                               Nghi vấn retention?
                                   /        \
                                 Không       Có
                                   |          |
                              Tiếp tục       Heap dump,
                              quan sát       TCCL/threads/
                                             callbacks
                                                   |
                                           Sửa lifecycle,
                                           đo lại sau deploy
~~~

**Kết luận:** `ClassLoadingMXBean` là công cụ **đo ba mặt của class loading**: **tổng nạp**, **đang loaded**, **đã dỡ**. Bộ đếm tích lũy giúp đo khối lượng hoạt động; gauge hiện tại giúp quan sát retention; nhưng việc xác định classloader leak phải dựa vào **xu hướng nhiều mẫu cùng JVM** và các công cụ chẩn đoán loader/memory chuyên biệt. Không lấy việc total tăng hoặc GC chưa unload ngay làm kết luận một chiều.

### Tài liệu chính thức

- [Java SE 17 — ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html)
- [Java SE 17 — ManagementFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [Java SE 17 — PlatformManagedObject / ObjectName](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/PlatformManagedObject.html)
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java SE 17 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html)
- [Java 17 HotSpot — Unified JVM Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
