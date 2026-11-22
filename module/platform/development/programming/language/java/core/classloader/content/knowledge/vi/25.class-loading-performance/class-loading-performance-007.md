# Đo hiệu năng class loading với cùng JDK, classpath và tập lớp được sử dụng

## 1. Mục tiêu và nguyên tắc của một phép so sánh công bằng

Khi chẩn đoán class loader chậm, thời gian khởi động lâu, plugin load chậm hoặc ứng dụng mất nhiều thời gian trước request đầu tiên, rất dễ đo hai lần rồi kết luận “cấu hình A nhanh hơn B”. Nhưng thời gian đo chỉ có ý nghĩa nếu **hai lượt thực hiện cùng loại công việc trên cùng môi trường**, đặc biệt:

1. **Cùng bản JDK/JVM**: vendor, version, build, kiến trúc, chế độ JIT, collector và các JVM flags liên quan.
2. **Cùng classpath/module path**: nội dung artifact, phiên bản dependency, thứ tự các entry, module resolution và cơ chế parent delegation.
3. **Cùng tập lớp thật sự được yêu cầu sử dụng**: cùng tên binary, cùng defining loader theo thiết kế, cùng số lần tạo loader/định nghĩa lớp, cùng yêu cầu initialization và cùng đường đi của ứng dụng.
4. **Cùng điều kiện đo**: JVM process mới hay JVM đã warm-up, CPU/RAM, trạng thái page cache, concurrent load, GC, logging, dữ liệu đầu vào và số lần lặp.
5. **Chỉ thay đổi một yếu tố cần đánh giá** giữa A/B, rồi đối chiếu cả **thời gian** lẫn **bằng chứng class loading thực tế**.

Cần xác định chính xác **đang đo cái gì** trước khi chọn công cụ:

| Phép đo | Bắt đầu → kết thúc | Có thể bao gồm | Điều không được suy ra |
|---|---|---|---|
| **Process startup** | Trước lúc tạo process → thông báo ứng dụng ready | JVM startup, bootstrap, CDS, framework, class loading, I/O | Không tự suy ra riêng class loader mất bao lâu |
| **First-use latency** | Trước lần dùng tính năng → sau lần trả kết quả đầu | Load, verify/link, initialize, JIT, cache, I/O, business logic | Không xem toàn bộ là “class load time” |
| **Per-class resolution/initialization operation** | Trước → sau lần `Class.forName(...)` | Tra cứu loader, có thể load/link/initialize hoặc chỉ tìm class đã có | Không đồng nghĩa chi phí JVM load thuần túy |
| **Steady-state latency/throughput** | Sau warm-up, trong các đợt đo | Code đã nạp, JIT, GC, thread scheduling, logic ứng dụng | Không dùng để khẳng định cold-start nhanh |
| **Class count/metaspace** | Snapshot trước → sau | Số lớp được JVM ghi nhận, bộ nhớ metadata | Không đo thay cho latency; thay đổi counter không gán được cho class mục tiêu |

**Điều kiện kiểm soát quan trọng nhất của bài:** cùng JDK nhưng khác dependency JAR, hoặc cùng JAR nhưng lần A kích hoạt thêm nhiều class, thì kết quả không còn đo cùng một workload. Cần chứng minh **tập lớp được sử dụng tương đương**, chứ không chỉ ghi “classpath trông giống nhau”.

## 2. Class loading thực tế có nhiều lớp chi phí

Phép đo `Class.forName` hay `loader.loadClass` **không tự tách** chi phí đọc JAR, verification, linking, initialization và I/O ứng dụng. JVM có thể trì hoãn symbolic resolution; `Class.forName(name, true, loader)` chủ động yêu cầu initialize, còn `false` thì không. Một lớp đã được nạp thường được tra lại từ cùng loader mà không define class lần nữa.

Để A/B thực sự tương đương, audit riêng:

- **Class identity:** binary name cùng defining loader phù hợp với thiết kế, không chỉ string class name.
- **Search path:** thứ tự JAR, checksum và parent delegation; parent có thể chọn một version khác trước child.
- **Work unit:** số class definitions, lần initialize, resource/provider/bean setup và kết quả nghiệp vụ.
- **JVM state:** fresh process hay warm class/JIT/CDS, OS page cache và số concurrent loaders.

Nếu A tạo một loader cho mỗi request còn B tái sử dụng một loader, chính việc thay đổi **số class definitions** là biến cần báo cáo, chứ không thể gọi hai workload có cùng số lớp nạp. Ngược lại, nếu chỉ đang thử tốc độ classpath lookup, đừng để một variant vô tình load thêm framework classes.

Bằng chứng `ClassLoadingMXBean` là số liệu toàn JVM; hãy kết hợp event logs và defining-loader diagnostics riêng để biết tập class mục tiêu thật sự được xử lý.

## 3. Thiết kế thí nghiệm: giả thuyết, biến và tiêu chí hợp lệ

Trước khi chạy, lập hồ sơ kiểm soát:

| Thành phần | Giữ cố định hoặc ghi rõ |
|---|---|
| JVM | `java -version`, `java -XshowSettings:properties -version`, `java -XX:+PrintFlagsFinal -version` khi cần; vendor/build/architecture |
| Ứng dụng | Commit/build ID; bytes của tất cả `.class`/JAR có thể được nạp |
| Classpath/module path | Danh sách entry **theo đúng thứ tự**, phiên bản và checksum artifact, `--module-path`/`--add-reads`/`--add-opens` nếu dùng |
| Loader topology | Bootstrap/platform/app loader; parent-child delegation; số loader mới mỗi lượt |
| Tập lớp mục tiêu | Tên binary + loader/source và sự kiện load/init; không so chỉ theo tên khi có nhiều loader |
| Workload | Cùng request/entry point/feature flags/input; cùng thao tác bắt buộc và cùng kết quả đúng |
| Runtime state | Cold JVM hay warmed JVM, vòng lặp warm-up, JIT, CDS, GC, memory flags |
| Host | CPU, RAM, load hệ thống, governor/container limits, file cache và I/O |
| Quan sát | Metric, đơn vị, ranh giới timer, số run, số bản phân phối và cách loại lỗi |

Ví dụ giả thuyết hợp lệ: “Với cùng bộ JAR và cùng 60 lớp plugin cần khởi tạo, thay đổi một chính sách tìm resource trong **cùng kiểu lifecycle loader** làm giảm median latency của lần load plugin”. Khi kiểm chứng, nếu log cho thấy A load 60 lớp còn B load 90 lớp, phải điều tra sự khác biệt trước khi nói chênh lệch do riêng chính sách tìm resource.

Ví dụ so sánh **không hợp lệ**:

- A chạy JDK 17, B chạy JDK 21; đồng thời khác CDS và dependency tree.
- A đo JVM lần đầu, B đo lời gọi lại `Class.forName` trong **cùng** JVM khi class đã load và initialize.
- A đo với `-Xlog:class+load=trace` ghi file, B tắt logging.
- A có 3 JAR trong classpath, B có 4 JAR hoặc thay thứ tự.
- A chạy request tạo 10 lazy-loaded classes, B chạy request ít tính năng hơn.
- A báo tỉ lệ nhanh hơn dựa trên **một lần chạy** khi CPU đang không ổn định.

Một so sánh có điều kiện có thể được thiết kế chủ đích khác biệt; cần ghi đó là **biến độc lập** (ví dụ JDK 17 so với 21), và giữ các yếu tố khác cố định. Trong bài này, bài toán yêu cầu **giữ nguyên JDK, classpath và tập lớp sử dụng**.

## 4. Ví dụ Java 17+: đo một thao tác nạp và khởi tạo tập lớp cố định

Ví dụ sau chạy bằng một file source Java, tạo ra ba class lồng nhau và cố định tên chúng. Mục tiêu là có một workload nhỏ, dễ lặp lại và có kết quả kiểm chứng được. Nó **không phải benchmark vi mô chuẩn** cho mọi implementation class loader.

Tạo file **`BenchClassLoad.java`**:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public final class BenchClassLoad {
    private static final String[] TARGETS = {
        "BenchClassLoad$Alpha",
        "BenchClassLoad$Beta",
        "BenchClassLoad$Gamma"
    };

    private static final class Alpha {
        static int marker = 11;
    }

    private static final class Beta {
        static int marker = 22;
    }

    private static final class Gamma {
        static int marker = 33;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 0) {
            throw new IllegalArgumentException("Run without arguments");
        }

        // Lấy bean trước khi bắt đầu timer, để giảm nhiễu setup.
        ClassLoadingMXBean mx =
                ManagementFactory.getClassLoadingMXBean();
        ClassLoader loader =
                BenchClassLoad.class.getClassLoader();

        long beforeCount = mx.getTotalLoadedClassCount();
        long startNs = System.nanoTime();

        long signature = 17L;
        for (String name : TARGETS) {
            // true: yêu cầu initialize lớp lần đầu khi thích hợp.
            Class<?> type = Class.forName(name, true, loader);
            signature = signature * 31 + type.getName().length();
        }

        long elapsedNs = System.nanoTime() - startNs;
        long loadedDelta =
                mx.getTotalLoadedClassCount() - beforeCount;

        System.out.println("targets=" + TARGETS.length);
        System.out.println("signature=" + signature);
        System.out.println("duration_ns=" + elapsedNs);
        System.out.println("jvm_loaded_delta=" + loadedDelta);
    }
}
```

Biên dịch một lần trên JDK 17+:

```bash
javac BenchClassLoad.java
```

Chạy nhiều **JVM process độc lập**, luôn từ cùng thư mục và cùng classpath:

```bash
java -cp . BenchClassLoad
java -cp . BenchClassLoad
java -cp . BenchClassLoad
```

Trong mỗi process, hai dòng sau có giá trị đúng như nhau:

```text
targets=3
signature=526276
```

Hai dòng còn lại là **số đo động**. Ví dụ kiểu hiển thị:

```text
duration_ns=<giá trị nanosecond đo được>
jvm_loaded_delta=<số lớp JVM nạp thêm trong khoảng đo>
```

Các dòng trong dấu ngoặc nhọn ở trên là **mô tả trường output**, không phải chuỗi literal do Java in; khi chạy, chúng là các số nguyên thực tế và có thể khác nhau giữa các lượt. Chương trình đo **thời gian thực thi ba lời gọi `Class.forName(..., true, loader)`**, bao gồm chi phí tra cứu, nạp/verify/link/initialize khi chưa thực hiện, chứ **không tách riêng** I/O hay VM define-class time. Số `jvm_loaded_delta` là **toàn JVM**, có thể bao gồm cả lớp hỗ trợ từ JDK được nạp trong khoảng đó; không nhất thiết đúng bằng 3.

Tính `signature` giúp xác nhận đoạn loop dùng đủ ba class đã định danh: với độ dài tên `BenchClassLoad$Alpha` = 20, `...$Beta` = 19, `...$Gamma` = 20, phép cập nhật từ 17 tạo ra kết quả 526276. Nhưng chữ ký này chỉ là **sanity check ở code**, chưa chứng minh nguồn bytes/loader identity của lớp trong ứng dụng phức tạp. Với tập lớp thật, cần kiểm tra class loading log riêng.

### Vì sao mỗi lượt nên là JVM process mới?

Cùng một loader không “load lần đầu” class đã define rồi. Nếu đặt hai vòng đo liên tiếp trong cùng `main`, vòng thứ hai sẽ thường đo **lấy class đã load/initialized** chứ không làm lại công việc của vòng đầu. Muốn đo first-use/class-loading cold theo vòng đời JVM, hãy chạy các process mới, cùng cấu hình. Đừng dùng `System.gc()` để xem như “reset” toàn bộ class đã load; GC không bắt JVM quên những lớp vẫn được giữ bởi loader sống.

Trong ví dụ, JVM mới bảo đảm namespace ứng dụng được tạo lại. Tuy nhiên **OS disk page cache** có thể đã ấm từ lần đầu và JVM startup state vẫn khác giữa process. Vì vậy gọi đây là *fresh JVM* hoặc *first-use per process* chính xác hơn gọi *true cold hardware/disk start*.

### Thu thập nhiều lần chạy

Bash/macOS/Linux, từ thư mục chứa `.class`:

```bash
for i in $(seq 1 20); do
  java -cp . BenchClassLoad
done
```

Nếu chỉ cần lưu các phép đo thời gian:

```bash
for i in $(seq 1 20); do
  java -cp . BenchClassLoad
done | awk -F= '/^duration_ns=/{print $2}' > timings-ns.txt
```

PowerShell (Windows), mỗi iteration cũng tạo JVM mới:

```powershell
1..20 | ForEach-Object {
    java -cp . BenchClassLoad
}
```

Đây là ví dụ **thu thập thô**, chưa có phép so sánh A/B hay suy luận ý nghĩa thống kê. Đối với thí nghiệm có A/B, thực hiện cả hai điều kiện với cùng số process, ngẫu nhiên hóa hoặc xen kẽ thứ tự `A/B/B/A` để giảm thiên lệch do máy nóng lên và các tác động thời gian.

## 5. Xác minh cùng classpath, JDK và class set

### A. Cố định JVM thực sự được dùng

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

Giữ output nguyên văn và ghi `java.home`, `java.version`, `java.vendor`, `os.arch`, JVM flags. Đảm bảo `java` và `javac` không trỏ hai JDK khác nhau do `PATH`/`JAVA_HOME`, CI image hoặc IDE launcher. Trường hợp build JDK khác runtime JDK có thể làm không còn tương thích hoặc khác cách thực thi.

Nếu muốn khảo sát riêng startup theo mặc định, giữ cùng **CDS mode** và cùng cờ `-Xshare`/archive. Bật/tắt CDS giữa hai điều kiện làm công việc class metadata thay đổi; đây là **một biến thí nghiệm khác**. Các cờ `-XX` là implementation-specific, nên phải xác minh trên JVM đang chạy.

### B. Chứng minh classpath không đổi

Với demo, `-cp .` và cùng bộ bốn file `BenchClassLoad.class`, `BenchClassLoad$Alpha.class`, `BenchClassLoad$Beta.class`, `BenchClassLoad$Gamma.class` là cấu hình đầu vào nhỏ nhất. Khi dùng JAR thật:

- Ghi **đường dẫn và thứ tự** từng classpath entry; thứ tự ảnh hưởng khi nhiều JAR chứa cùng tên binary class.
- Ghi version và checksum SHA-256 của JAR/class bytes. Chỉ cùng tên file hay cùng số version trên manifest chưa bảo đảm nội dung giống nhau.
- Nếu dùng Gradle/Maven, phân biệt `compileClasspath`, `runtimeClasspath`, classpath của test, plugin runtime và classpath do launcher tự tạo.
- Nếu dùng `--module-path`, kiểm soát module graph, module descriptors, resolution và tùy chọn `--add-reads`, `--add-opens`.
- Với Spring Boot executable JAR, kiểm tra `BOOT-INF/lib`/`BOOT-INF/classes`; launcher riêng có thể không biểu diễn classpath giống `java -cp ...`.
- Trong hệ thống plugin, cùng JAR nhưng **parent delegation khác** có thể dùng bytes từ loader cha thay cho bản trong plugin. Ghi cả loader topology.

Ví dụ dùng lệnh kiểm tra checksum ngoài Java code:

```bash
sha256sum path/to/dependency.jar
```

Trên Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 path/to/dependency.jar
```

Dòng `path/to/dependency.jar` chỉ là placeholder, thay bằng JAR thực tế. Không thay đổi thứ tự classpath hoặc xóa cache khi đang thu thập số đo trừ khi đó là biến chủ đích của thí nghiệm.

### C. Xác minh tập lớp được sử dụng bằng logging riêng

Trên HotSpot JDK 17+, một **lượt audit độc lập** có thể dùng:

```bash
java -Xlog:class+load=info:file=class-load-%p.log:uptime,level,tags -cp . BenchClassLoad
```

Trong log, tìm ba tên:

```text
BenchClassLoad$Alpha
BenchClassLoad$Beta
BenchClassLoad$Gamma
```

Chúng có thể xuất hiện cùng nhiều lớp Java khác. Kiểm tra **nguồn load**, số dòng phù hợp, thời điểm và loader identity (nếu log/diagnostic command của runtime có cung cấp). Chỉ so ba tên chưa đủ nếu giữa hai điều kiện có thêm 200 class framework hoặc một class được định nghĩa nhiều lần bởi loader khác nhau.

Nếu đang khảo sát khởi tạo:

```bash
java -Xlog:class+load=info,class+init=info:file=class-events-%p.log:uptime,level,tags -cp . BenchClassLoad
```

`class+load` và `class+init` phản ánh hai giai đoạn khác nhau. Dùng cùng kiểu event khi đếm, không ghép tổng loaded của điều kiện A với initialized của B.

**Không dùng lượt bật verbose logging làm lượt đo hiệu năng chính:** ghi log cho từng class tăng CPU/I/O và có thể tác động mạnh đến thời gian. Thực hiện audit để chứng minh workload/class set; sau đó đo timing với logging **giống nhau và tối thiểu** ở cả hai nhánh (thường tắt log class mức info/debug). Nếu bật JFR/profiler, cũng giữ **cùng cấu hình instrument** cho các lượt đem so trực tiếp.

### D. Phân biệt target set với thống kê toàn JVM

Trong ví dụ, `TARGETS` là **tập class chủ đích**. `ClassLoadingMXBean.getTotalLoadedClassCount()` là **tổng class đã load từ khi JVM bắt đầu**; delta trong timer có thể tăng vì lớp trợ giúp khác. `getLoadedClassCount()` là số class hiện load, `getUnloadedClassCount()` là tổng đã unload. Các giá trị này **không định danh class nào, JAR nào hay loader nào**.

Vì vậy nên lưu hai loại bằng chứng:

1. **Danh sách mục tiêu**: các tên/class identity cần được tác vụ sử dụng, số lượt load/initialize dự kiến, kết quả checksum/chức năng.
2. **Dữ liệu process**: counter tổng JVM, log event load/unload, CPU/GC và footprint trong điều kiện đo.

Nếu hai process có delta loaded khác nhau, đừng vội “chuẩn hóa thời gian bằng cách chia cho loaded count”, vì các class có chi phí rất khác nhau, nhiều lớp đã nạp trước timer, và loader có thể có cache. Hãy điều tra lớp khác nhau trước.

## 6. Chọn công cụ theo câu hỏi đo

| Công cụ | Dùng khi nào | Giới hạn |
|---|---|---|
| `System.nanoTime()` | Đo khoảng thời gian elapsed nhỏ, cùng phạm vi rõ | Timer overhead/JIT/scheduling; một mẫu quá nhiễu |
| Java Flight Recorder (JFR) | Quan sát startup, class loading, CPU, allocation, GC, các event được bật | Event/overhead phụ thuộc cấu hình; không phải mọi class event đều mặc định bật |
| `-Xlog:class+load`/`class+init` | Audit lớp thực sự nạp/khởi tạo và nguồn nạp | Logging thêm overhead; output khổng lồ nếu app nhiều class |
| `ClassLoadingMXBean` | Counters loaded/current/unloaded toàn JVM | Không định danh lớp; không phải đo latency |
| `jcmd <pid> VM.classloader_stats` | Snapshot loader/class count tại runtime | Snapshot; bản thân attach/diagnostic có thể có overhead |
| `jcmd <pid> VM.metaspace` | Phân tích memory metadata trong HotSpot | Footprint không tương đương thời gian load |
| JMH | Benchmark **steady-state micro-operations**, có warm-up/forks/measurement được cấu hình | Nếu mục tiêu là first load một lần của JVM, JMH method chạy lặp lại thường đo class **đã load** |
| OS profiler/CPU profiler | Tìm I/O, CPU và method hot trong loading/initialization | Profiling là quan sát có overhead; không thay A/B kiểm soát |

Dùng `java -Xlog:help` để xem tag trên JVM đang chạy. Các lệnh `jcmd` dưới đây là ví dụ đọc snapshot, thay `<pid>` bằng PID JVM thực và cần có quyền attach:

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace
```

Khi đo **wall-clock process startup** bên ngoài JVM, nên dùng launcher/script đo từ khi tạo process tới mốc “ready” nhất quán; `System.nanoTime()` bên trong `main` **không bao gồm** giai đoạn JVM bootstrap đã xảy ra trước `main`.

## 7. Warm-up, JIT, CDS, GC và OS page cache

**Warm-up/JIT:** Nếu phép đo là gọi lại một class lookup/API nhiều lần sau khi class đã nạp, chạy warm-up đủ dài và đo steady-state. Dùng JMH với forks phù hợp để giảm nhiễu và tránh JIT loại bỏ phép đo. Nhưng nếu mục tiêu là **load class lần đầu**, mỗi process chỉ có một cold first-use cho cùng loader; việc “warm-up” bằng cách gọi chính class mục tiêu trước sẽ làm mất hiện tượng cần đo. Tách rõ hai loại benchmark này.

**CDS:** Class Data Sharing có thể giảm một phần công việc loading của các lớp phù hợp. Giữ giống nhau trạng thái archive/`-Xshare` và runtime image; không thể quy mọi lợi ích startup cho custom class loader khi CDS thay đổi đồng thời.

**Garbage collection:** Một số lượt có GC gần hoặc trong khoảng timer. Cần so tương quan thời điểm GC với ngoại lệ trong phân phối; không đơn giản xóa mọi lượt chậm vì chúng chậm. Cấu hình heap, collector và allocation pattern phải giống nhau.

**OS cache và I/O:** Khi classpath nằm trên disk, filesystem cache có thể khiến những lần đọc JAR sau nhanh hơn. Muốn mô phỏng startup production, xác định trạng thái cold/warm cache tương ứng và tái hiện công bằng. Không đo lượt A ngay sau reboot và lượt B sau nhiều lần đọc JAR rồi coi đó là hiệu năng JVM A/B.

**CPU scheduling/thermal:** CPU governor, turbo boost, thermal throttling, container quota, dịch vụ nền và tải máy gây nhiễu. Trên CI shared runners, biến thiên có thể lớn; nên chạy nhiều lượt, ghi host metadata và báo phân phối thay vì số duy nhất.

**Class initialization side effects:** `<clinit>` có thể làm I/O, đọc config, init logging hay đăng ký driver. Nếu profile cho thấy thời gian nằm ở static initializer thì tối ưu class loader search sẽ không giải quyết phần lớn độ trễ. Phải đặt timer/phân tích sao cho biết giai đoạn nào đang chiếm chi phí.

## 8. Từ số đo thô tới kết luận

Giả sử thử nghiệm A và B chỉ khác một chính sách tìm class resource; **các con số dưới đây hoàn toàn minh họa, không phải kết quả đo một ứng dụng có thật**:

| Điều kiện | JDK / classpath / target set | Median first-use latency | P95 |
|---|---|---:|---:|
| A | Cùng JDK 17 / cùng hash JAR / 60 lớp mục tiêu | 48 ms | 64 ms |
| B | Cùng JDK 17 / cùng hash JAR / 60 lớp mục tiêu | 41 ms | 58 ms |

Trong ví dụ này, chênh lệch median là `48 - 41 = 7 ms`, tương đương `7 / 48 ≈ 14,6%`. Tuy vậy để kết luận “B cải thiện hiệu năng”, còn phải kiểm tra số run, phân phối, nhiễu hệ thống, JIT, I/O, logging, không có class set mới phát sinh và đúng tính năng trả cùng kết quả.

Báo cáo tốt không chỉ ghi một tỷ lệ phần trăm. Nó nêu:

- **Workload:** thao tác được đo, class names và defining-loader semantics, số loader/class, kết quả chức năng.
- **Setup:** JVM version/vendor, flags, dependency hashes/classpath ordering, module path, machine, cache state.
- **Method:** điểm bắt đầu/kết thúc timer, warm-up hoặc fresh process, số forks/runs, thứ tự A/B và các run lỗi.
- **Kết quả:** median, P95, khoảng phân tán (min/max hoặc IQR), unit, raw data/path log để người khác tái hiện.
- **Bằng chứng phụ:** audit class loading/initialization, GC/counter, nơi phần lớn thời gian tiêu tốn theo profiler.
- **Giới hạn:** tác động JIT/cache còn lại, độ đại diện của synthetic benchmark với workload production.

Nên ưu tiên **median** và percentile trong dữ liệu lệch/phân tán, cùng biểu đồ phân phối theo run nếu cần. Số liệu ít hoặc phân phối chồng lấp mạnh có thể chưa đủ chứng minh thay đổi thật. Với phép đo có overhead instrumentation, so A/B **cùng một bộ công cụ/setting**.

## 9. Các lỗi đo phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Khác JDK, vendor hoặc JVM flags | Compilation, GC, CDS và runtime behavior khác | Chốt runtime image và lưu `java -version`/flags |
| Cùng tên dependency nhưng JAR khác | Binary được nạp có thể không giống nhau | So SHA-256 và runtime class source |
| Đổi thứ tự classpath | Class cùng tên có thể được tìm ở entry khác | Giữ đúng ordered classpath |
| Quên parent/child loader topology | Cùng class name chưa chắc cùng runtime class | Ghi defining loader, delegation và số loader |
| A load 50 lớp, B load 80 lớp | Khác workload nên latency không cùng ý nghĩa | Audit class set, chức năng và thứ tự |
| Vòng đo đầu và vòng sau cùng process | Class ở vòng hai đã load/initialized | Fresh JVM cho first-use; warm-up riêng cho steady state |
| Tính thời gian `main` là JVM startup | Bootstrap đã xảy ra trước `main` | Đo từ launcher ngoài process tới ready |
| Bật class trace chỉ ở A | Logging thay đổi CPU/I/O | Audit riêng, giống logging ở mọi lượt đo |
| Đọc `getTotalLoadedClassCount()` là số lớp của plugin | Counter chứa toàn JVM | Lọc event theo class/loader hoặc có instrumentation đúng phạm vi |
| Dùng `System.gc()` để “reset” class | GC không unload những lớp còn được loader giữ | Thiết kế vòng đời loader/process phù hợp |
| Chỉ chạy một lần, lấy số nhanh nhất | Nhiễu và cache bias | Lặp nhiều lần, báo median, P95, raw data |
| Chỉ báo “B nhanh hơn 25%” | Không biết tác vụ, runtime và biến thay đổi | Ghi protocol, workload và checksums |
| Tối ưu dựa trên số class giảm bất kỳ | Ít class không tự đồng nghĩa latency thấp hoặc chức năng giống | Kiểm tra mục tiêu và đo trực tiếp latency/CPU |

## 10. Checklist tái lập

Trước khi chấp nhận so sánh A/B:

- [ ] Đã xác định cần đo **process startup**, **first-use** hay **steady state**, ranh giới timer rõ ràng.
- [ ] JDK/JVM vendor, version, build, flags, collector, CDS và kiến trúc **giống nhau**.
- [ ] Classpath/module path **cùng entry, thứ tự và checksum artifact**; class loader topology được ghi.
- [ ] Cùng tập class mục tiêu được gọi, nạp, khởi tạo; kiểm tra bằng log audit riêng.
- [ ] Cùng số lượt loader/class-definition, cùng feature flags và dữ liệu đầu vào.
- [ ] Logging/profiler/JFR được bật cùng cách ở các lượt đo và không làm sai phép so sánh.
- [ ] Trạng thái JVM (fresh/warmed), JIT, page cache, GC, tải CPU/RAM có quy tắc kiểm soát.
- [ ] Có nhiều run độc lập, lưu raw data, median/P95 và đơn vị.
- [ ] Các phép đo có thể được người khác chạy lại với đúng commands và artifacts.
- [ ] Kết luận nói rõ điều **đã đo**, điều **chưa tách riêng được** và phạm vi áp dụng.

## 11. Câu hỏi tự kiểm tra

**1.** Vì sao gọi `Class.forName("X", true, loader)` hai lần liên tiếp trong cùng JVM không tương đương hai phép đo cold loading?  
**Đáp án:** Lần thứ hai có thể chỉ tra cứu lớp đã define và initialize. Muốn first-use cold của cùng defining loader thì cần lifecycle/loader hoặc JVM mới; đồng thời phải giữ workload tương đương.

**2.** Có thể kết luận A nhanh hơn B nếu B vô tình load thêm 100 class framework?  
**Đáp án:** Không thể quy chênh lệch riêng cho thay đổi mong muốn; trước hết cần phân loại nguyên nhân khiến tập lớp thực sử dụng khác nhau.

**3.** Vì sao giữ cùng tên JAR chưa đủ bảo đảm cùng classpath?  
**Đáp án:** Nội dung JAR, thứ tự entry, đường dẫn và loader delegation có thể khác; cần kiểm tra artifact hashes và runtime source.

**4.** Dùng `-Xlog:class+load` để lấy timing benchmark có rủi ro nào?  
**Đáp án:** Logging làm tăng CPU/I/O, làm nhiễu thời gian; nên audit riêng và đo với cùng logging level/cấu hình tối thiểu ở các điều kiện.

**5.** Nếu `jvm_loaded_delta` của chương trình mẫu là 8 thay vì 3, có nghĩa code không chỉ nạp ba class mục tiêu?  
**Đáp án:** Vòng gọi vẫn xác định ba target names; counter toàn JVM có thể bao gồm lớp Java/runtime khác được tải trong khoảng đo. Cần xem class load log để định danh.

## Tài liệu tham khảo

- [Java SE 17 — `Class.forName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): phân biệt yêu cầu initialize khi tìm lớp.
- [Java SE 17 — `ClassLoadingMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): counter class loaded/unloaded toàn JVM.
- [JDK 17 `java` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog`, class load/initialization/unloading tags, cấu hình classpath, `-Xshare`.
- [Java Language Specification 17, chương 12](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization và unloading.
- [Java Microbenchmark Harness (OpenJDK JMH)](https://github.com/openjdk/jmh): công cụ cho microbenchmark với warm-up, measurement và forks; cần chọn đúng cho câu hỏi steady-state hay cold first-use.
