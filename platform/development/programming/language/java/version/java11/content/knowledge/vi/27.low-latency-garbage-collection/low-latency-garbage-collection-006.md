# Chọn chế độ ZGC được JDK hiện hành hỗ trợ — Generational ZGC, cấu hình và kiểm chứng (Java 11+)

## 1. Kết luận thực hành: trên JDK hiện hành dùng chế độ nào?

**Nếu triển khai trên OpenJDK/HotSpot JDK 24 trở lên, kể cả JDK 25 LTS, JDK 26 và JDK 27 (phát hành 09/2026), lựa chọn ZGC được hỗ trợ là _Generational ZGC_.** Chỉ cần chọn collector bằng tham số JVM:

```bash
java -XX:+UseZGC -Xms512m -Xmx4g -jar app.jar
```

Đây là cú pháp **khởi động JVM**, không phải Java source. Thay `app.jar` bằng artifact thực và điều chỉnh kích thước heap theo tải/memory limit thực tế. Trên máy không đủ RAM hoặc container có memory limit nhỏ hơn `-Xmx4g` cộng native overhead, ví dụ số 4 GiB **không phù hợp**.

**Không thêm `-XX:+ZGenerational`, không thêm `-XX:-ZGenerational` vào lệnh khởi động trên JDK mới.** Từ **JDK 24**, non-generational ZGC đã bị **loại bỏ (JEP 490)**, và option `ZGenerational` không còn là công tắc chế độ được hỗ trợ. JDK 24 và một số build gần đó có thể chỉ **cảnh báo và bỏ qua** option cũ; các bản JDK mới hơn có thể **từ chối khởi động** vì option không còn nhận diện. Cách an toàn, tương thích với dòng JDK hiện hành là **loại hẳn option cũ**.

**Cũng không cần `-XX:+UnlockExperimentalVMOptions` để chạy ZGC trên JDK hiện hành.** ZGC đã được đưa vào sử dụng production từ **JDK 15 (JEP 377)**.

Điểm cần ghi nhớ:

- **ZGC** là **collector được lựa chọn** bằng `-XX:+UseZGC`.
- **Generational** là **mô hình quản lý heap nội tại của ZGC hiện hành**, không phải một flag cần tự bật từ JDK 24.
- Nếu không chọn collector, **G1 vẫn là mặc định** theo tài liệu HotSpot JDK 27, không phải ZGC.
- Chọn ZGC vì **mục tiêu latency** đã đo được; không mặc định coi ZGC vượt G1 về mọi mặt.
- **Kiểm tra JVM thực tế**, không suy đoán theo tên project, tên Java source, tên JAR hay biến môi trường không được áp dụng vào lệnh chạy.

### Lệnh kiểm tra nhanh

```bash
java -version
java -XX:+UseZGC -Xlog:gc -version
```

Trên OpenJDK HotSpot có ZGC, kết quả có dòng tương tự:

```text
[0.008s][info][gc] Using The Z Garbage Collector
openjdk version "24.0.2" 2025-07-15
...
```

Đây là **một stdout/stderr trích từ lần thử thực tế trên Zulu OpenJDK 24.0.2**; version, uptime, tên runtime sẽ khác. Dòng `Using The Z Garbage Collector` là tín hiệu quan trọng hơn số giây khởi tạo.

## 2. ZGC là gì, và tại sao “low latency” khác “high throughput”?

ZGC (*Z Garbage Collector*) là collector dành cho ứng dụng Java có yêu cầu **GC pause rất ngắn**, cố gắng thực hiện các công việc đắt đỏ của GC **đồng thời với application threads** thay vì dừng mọi threads trong thời gian dài.

```text
                          Java application threads
                            |  run  run  run
                            |   |    |    |
                            v   v    v    v

  G1 (mostly concurrent): [ concurrent work ] -- [ some STW phases ]
  ZGC (concurrent design): [ concurrent mark/relocate/barriers ... ]
                                            | short pauses |
```

Đây là sơ đồ khái quát, **không phải** timeline thời gian thực hay cam kết một giá trị pause cố định.

### Bốn đại lượng cần tách biệt

| Đại lượng | Câu hỏi trả lời | Ghi chú |
| --- | --- | --- |
| **GC stop-the-world pause** | Một pha GC ngăn application threads chạy trong bao lâu? | ZGC tối ưu mạnh cho điều này |
| **End-to-end request latency** | Một request hoàn thành sau bao lâu? | Còn ảnh hưởng I/O, lock, network, DB, scheduling, JIT... |
| **Throughput** | Hệ thống xử lý bao nhiêu request/giây hoặc đơn vị công việc/giây? | ZGC có thể đổi một phần throughput lấy low latency |
| **CPU/memory overhead** | Collector dùng bao nhiêu tài nguyên đồng thời với app? | Concurrent work, barriers, allocation headroom không miễn phí |

Nếu SLA đặt `p99.9 < 50 ms` cho HTTP request, việc chọn ZGC **không đảm bảo** mọi request đáp ứng SLA, vì một request có thể đợi database 500 ms dù GC chỉ pause một phần nghìn giây.

Theo hướng dẫn HotSpot, ZGC hướng tới **pauses cỡ dưới một mili-giây trong nhiều tình huống** và ít phụ thuộc kích thước heap; nhưng đây **không phải hard real-time bound** cho mọi OS, máy ảo, workload hoặc event. Phải đo thời gian pause và tail latency trên môi trường triển khai.

### Tại sao concurrent GC cần headroom?

Trong lúc ZGC đánh dấu, thu gom hoặc di chuyển objects, application threads **vẫn tiếp tục cấp phát**. Nếu live set đã gần `-Xmx` và app tạo objects quá nhanh, collector có thể không kịp cấp chỗ trống. Hệ quả có thể gồm **allocation stalls**, GC pressure, OOM hoặc latency tăng.

Vì vậy, tăng `-Xmx` hợp lý là một trong những tuning knobs hiệu quả nhất khi CPU và memory budget cho phép. Không chọn `-Xmx` chỉ vừa đủ với số byte object còn sống tại một snapshot.

## 3. Thế hệ của ZGC: young và old để làm gì?

Nhiều Java applications tuân theo **generational hypothesis**: đa số objects chết sớm, chỉ một phần nhỏ sống lâu. Generational ZGC khai thác đặc điểm ấy bằng cách theo dõi objects ở các thế hệ khác nhau, tối ưu lượng work cần làm.

```text
        Nhiều short-lived allocations
                    |
                    v
              Young generation
                    |
          +---------+----------+
          |                    |
          v                    v
   Không còn live        Còn live sau GC
      reclaim                 |
                              v
                      Promotion / aging
                              |
                              v
                       Old generation
                              |
                      Thu gom phù hợp
                              |
                              v
                       Reclaim old
                       unreachable data
```

ZGC vẫn thực hiện phần lớn công việc theo **mô hình concurrent, low-pause**. Các chi tiết triển khai như thời điểm thu gom young/old, heuristics, barriers, aging thresholds có thể tiến hóa giữa các JDK. Không tự áp đặt quy tắc “mọi object qua đúng N lần young GC thì vào old” hoặc “old GC là một full stop-the-world compact” — đó không phải contract chung của ZGC.

### Đọc tên cycles cho đúng

Trên OpenJDK 24.0.2 đã kiểm chứng, JMX `GarbageCollectorMXBean` báo tên:

```text
ZGC Major Cycles
ZGC Major Pauses
ZGC Minor Cycles
ZGC Minor Pauses
```

Đây là **tên beans trong runtime cụ thể**, không phải danh sách cứng của Java SE. Những JVM providers hoặc version khác có thể đặt tên/thể hiện metadata khác. Một **Minor Cycle** thường liên hệ hoạt động young, còn **Major Cycle** liên hệ work rộng hơn; đừng tự đồng nhất mọi `Major` với stop-the-world **Full GC** của collector khác.

### Tại sao generational thường cải thiện hiệu suất?

Thay vì cần xem toàn heap trong những lần thu gom liên quan objects mới, collector có thể tập trung vào thế hệ trẻ nơi nhiều objects nhanh chóng chết, giảm công việc không cần thiết ở old generation khi workload hợp với giả thuyết thế hệ.

Tuy nhiên, nếu app có đặc tính **gần như mọi object sống rất lâu**, lợi ích generational có thể khác một app nhiều temporary objects. Cần đo trên **workload thật**, không chỉ dựa vào khẩu hiệu “generational luôn nhanh hơn”.

## 4. Bảng tương thích phiên bản: tránh sao chép lệnh đã lỗi thời

Đây là **bảng chuyển đổi để xác định cấu hình hiện hành**, không phải hướng dẫn triển khai lại các chế độ đã bị loại bỏ.

| JDK | Thay đổi liên quan ZGC | Ý nghĩa cho cấu hình ngày nay |
| --- | --- | --- |
| **JDK 11** | ZGC bắt đầu ở giai đoạn experimental (JEP 333), chưa có generational | Chỉ nên xem là nền tảng lịch sử của module Java 11, **không** dùng cách bật experimental cũ cho JDK mới |
| **JDK 15** | ZGC trở thành collector production, `-XX:+UseZGC` không cần unlock experimental (JEP 377) | Đây là cơ sở cho startup flag hiện hành |
| **JDK 21 LTS** | Generational ZGC được giới thiệu (JEP 439), khi đó là opt-in mode | Với môi trường JDK 21 phải quản lý rõ version; option từng dùng ở JDK 21 **không được copy sang 24+** |
| **JDK 23** | Generational ZGC trở thành default của ZGC (JEP 474) | Không cần flag riêng để bật generational trong JDK 23 |
| **JDK 24** | Non-generational mode bị xóa (JEP 490), option `ZGenerational` không còn có hiệu lực | **`-XX:+UseZGC` chọn Generational ZGC** |
| **JDK 25 LTS** | ZGC chỉ còn generational mode | Phù hợp triển khai LTS mới với `-XX:+UseZGC` |
| **JDK 26 / JDK 27 (09/2026)** | ZGC generational-only tiếp tục được hỗ trợ | Dùng `-XX:+UseZGC`, bỏ flag `ZGenerational` cũ |

**Hai nhầm lẫn cần tránh:**

1. **Java source target ≠ JDK runtime.** Ứng dụng biên dịch `javac --release 11` có thể chạy trên JDK 25/27; khi chạy, chính JVM JDK 25/27 quyết định collector và GC options. Không vì source target Java 11 mà phải dùng ZGC experimental của năm 2018.
2. **JDK 21 LTS còn được sử dụng ≠ non-generational ZGC còn được hỗ trợ trên JDK mới.** Nếu đang vận hành JDK 21, hãy kiểm tra đúng tài liệu JDK 21 trước khi thay flags; nếu đang xây deployment mới trên JDK 24+, chỉ dùng chế độ generational duy nhất.

### Mẫu cấu hình cần bỏ khi nâng cấp

Các ví dụ sau **không nên tồn tại trong cấu hình JDK 24+**:

```text
-XX:+ZGenerational
-XX:-ZGenerational
-XX:+UnlockExperimentalVMOptions     (nếu chỉ để bật ZGC)
```

`-XX:+UnlockExperimentalVMOptions` là một HotSpot flag vẫn có các tình huống sử dụng khác, **nhưng không cần để bật ZGC trên JDK hiện hành**. Nếu nó chỉ được thêm vì hướng dẫn ZGC rất cũ, nên bỏ để giảm rủi ro vô tình bật thêm experimental settings không mong muốn.

### Lỗi hay gặp khi nâng cấp

Trên JDK 24.0.2 thử nghiệm:

```text
OpenJDK 64-Bit Server VM warning:
  Ignoring option ZGenerational; support was removed in 24.0
```

Ở một số build JDK mới hơn, có thể nhận `Unrecognized VM option 'ZGenerational'` và JVM không khởi động. **Không dựa vào việc phiên bản này có thể chỉ cảnh báo rồi chạy** để coi flag đó hợp lệ; loại nó khỏi scripts, manifests, Helm values và `JAVA_TOOL_OPTIONS`.

## 5. Có phải G1 mặc định, muốn dùng ZGC phải bật?

**Có, theo tài liệu HotSpot JDK 27:** G1 là collector mặc định. ZGC cần được chọn rõ bằng `-XX:+UseZGC` nếu muốn đo/trải nghiệm nó.

So sánh khái quát:

| Tiêu chí | G1 | Generational ZGC |
| --- | --- | --- |
| Vị thế | Collector mặc định trong HotSpot JDK 27 | Collector low-latency được chọn rõ |
| Mục tiêu chính | Cân bằng throughput và pause-time goal | GC pauses rất ngắn ở nhiều heap sizes |
| Hành vi GC | Mostly concurrent, có các STW evacuation phases | Concurrent design, short pauses |
| CPU overhead | Tùy workload; thường tốt cho mục tiêu cân bằng | Concurrent GC/barriers có thể lấy CPU từ application |
| Heap headroom | Cần đủ cho live set và evacuation | Cần thêm headroom khi app vẫn allocate trong GC cycle |
| Khi phù hợp | Server thông thường, throughput tốt, p99 hợp lý | SLA latency nghiêm ngặt đã chứng minh G1 không đạt |
| “Luôn tốt hơn”? | Không | Không |

Không nên chọn theo cảm tính “ZGC mới hơn chắc chắn nhanh hơn”, và cũng không nên quay lại collector không còn được duy trì để cứu throughput. **Mục tiêu là chọn collector đang được hỗ trợ và phù hợp SLA đo được**.

### Quy tắc quyết định tối giản

```text
              Thu thập metrics G1 baseline
                           |
                 p99/p99.9 có đạt SLA?
                       /       \
                     Có         Không
                     |           |
       G1 có thể đủ dùng         GC pauses có là phần đáng kể?
                                    /          \
                                  Không         Có
                                   |            |
                        Điều tra app/IO       Benchmark ZGC
                        DB/lock/network          |
                                                v
                              CPU/RSS/throughput/latency có đạt?
                                         /            \
                                        Có            Không
                                         |              |
                                Cân nhắc ZGC       Tuning/giữ G1/
                                                 thay đổi workload
```

Nếu tail latency chủ yếu do mạng hoặc query chậm, ZGC có thể giảm GC pauses nhưng **không chữa được bottleneck thực sự**.

## 6. Lệnh khởi động ZGC đúng cho JDK 24–27

### 6.1. Ví dụ tối thiểu

```bash
java -XX:+UseZGC -Xmx2g -jar app.jar
```

Tham số `-XX:+UseZGC` phải đi **trước** `-jar`. Bất kỳ arguments nào sau `app.jar` là **application arguments**, không được HotSpot xử lý như JVM options.

**Sai:**

```bash
java -jar app.jar -XX:+UseZGC
```

Trong trường hợp này flag thường đi tới `String[] args` của ứng dụng, nên JVM có thể vẫn sử dụng G1. Luôn kiểm tra startup logs hoặc VM flags thực tế.

### 6.2. Ví dụ có heap và GC logs

```bash
java \
  -XX:+UseZGC \
  -Xms512m \
  -Xmx4g \
  -Xlog:gc*,safepoint:file=logs/zgc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
```

Cú pháp trên dùng dấu nối dòng `\` cho **POSIX shells**; không copy nguyên dạng sang PowerShell/CMD. **Thư mục `logs/` phải tồn tại và process phải có quyền ghi** trước khi startup. Nếu chạy container, dùng volume và log rotation theo policy.

Ở PowerShell, dùng **một dòng**:

```powershell
java -XX:+UseZGC -Xms512m -Xmx4g -Xlog:gc*,safepoint:file=logs/zgc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
```

Ví dụ `-Xms512m/-Xmx4g` chỉ mang tính tham khảo; container có memory limit thấp hơn có thể OOM kill ngay khi ứng dụng cần dùng tới memory. Với workload mới, đo live set và allocation spikes rồi mới chọn `-Xmx`.

### 6.3. Bài kiểm tra ngay cả khi chưa có app.jar

```bash
java -XX:+UseZGC -Xms64m -Xmx256m -Xlog:gc -version
```

Nếu thấy:

```text
[...][info][gc] Using The Z Garbage Collector
```

và exit status bằng 0, JVM hiện tại **chấp nhận flag và chọn ZGC**. Nhưng chỉ chạy `-version` chưa chứng minh GC hoạt động dưới tải sản phẩm hay phù hợp latency SLA; cần thử chương trình thực tế.

### 6.4. Đặt options qua hệ thống vận hành

JVM arguments thường xuất hiện trong:

- service startup scripts và process manager;
- Dockerfile `ENTRYPOINT` hoặc `CMD`;
- Kubernetes `command`/`args`, JVM heap sizing;
- Helm charts, environment variables như `JAVA_TOOL_OPTIONS`;
- application server startup hoặc buildpack configuration.

**Không** để hai nơi cùng đặt collector mâu thuẫn nhau như `-XX:+UseZGC` và `-XX:+UseG1GC` rồi mong JVM tự chọn theo ý định. Đặt một nơi quản lý flags có version control, test startup command trong CI và ghi lại VM flags đang chạy.

## 7. Kiểm chứng đúng JVM/JDK/collector trước khi benchmark

### 7.1. `java -version` và binary path

```bash
java -version
java -XX:+UseZGC -Xlog:gc -version
```

Đối với deployment, hãy xác định **đường dẫn Java binary thực sự chạy service**, chứ không chỉ phiên bản `java` trong shell developer. Trong container/Kubernetes, `java -version` của image/runtime mới là điều kiện liên quan.

Các yếu tố cần ghi:

- Java vendor/major/update version và JVM implementation;
- OS/architecture/container memory+CPU limits;
- flags đầy đủ, đặc biệt collector, `-Xms`, `-Xmx`, `SoftMaxHeapSize`;
- runtime logs cho biết collector nào thực sự được chọn.

### 7.2. `-XX:+PrintFlagsFinal`

```bash
java -XX:+UseZGC -Xmx256m -XX:+PrintFlagsFinal -version
```

Tìm các entries như:

```text
bool UseZGC = true
bool UseG1GC = false
size_t SoftMaxHeapSize = ...
```

Trình bày trên là **dạng rút gọn**; output thực có cột, metadata, origin flags, whitespace và giá trị bytes. Đừng parse logs bằng regex quá phụ thuộc layout nếu muốn chạy qua nhiều JDK vendors.

### 7.3. `jcmd` với tiến trình đang chạy

Nếu cùng máy và có attach permission:

```bash
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

Thay `<PID>` bằng process ID phù hợp; đây là **shell placeholder**, không phải phần literal của lệnh.

- `VM.command_line` giúp thấy JVM args lúc startup.
- `VM.flags` cho biết VM flags đang sử dụng (mức chi tiết tùy phiên bản).
- `GC.heap_info` cung cấp thông tin heap/GC nếu hỗ trợ.
- Chạy `jcmd` cần tools/JVM/permissions tương ứng; không assume có trong mọi custom JRE image.
- Một container có nhiều Java processes có thể có `PID 1` không phải JVM hoặc có namespace PID riêng; xác định đúng process.

Không chỉ dựa vào `jcmd -l` và một JAR name nếu có nhiều Java processes; kiểm tra exact PID/container instance.

### 7.4. Unified GC logging

```bash
java -XX:+UseZGC -Xmx2g -Xlog:gc* -jar app.jar
```

`-Xlog:gc*` cung cấp nhiều sự kiện GC hơn `-Xlog:gc`, nhưng cũng làm log volume tăng. Khi cần phân tích mức độ chi tiết hơn, bổ sung tags/levels có chủ đích:

```text
-Xlog:gc=info
-Xlog:gc*,safepoint
-Xlog:gc+heap=debug
```

Cú pháp và event tags là đặc trưng HotSpot Unified Logging; **format log có thể thay đổi giữa JDKs**. Tránh dashboard phụ thuộc vào một chuỗi exact như `GC(3) Minor Collection` mà không kiểm tra schema/parser.

## 8. Java 11 demo đầy đủ: kiểm tra collector được chọn mà không đoán từ log

Đây là **chương trình độc lập** dùng Java management APIs để đọc collector state. Nó được **biên dịch với `javac --release 11`**, nhưng chạy trên **JDK 24.0.2** với hai flags chọn ZGC/G1. Điều này minh họa rằng **bytecode target Java 11 không khóa GC mode ở Java 11**.

Chương trình dùng:

- `Runtime.version().feature()`: major JDK runtime.
- `GarbageCollectorMXBean`: danh sách tên GC beans.
- `com.sun.management.HotSpotDiagnosticMXBean`: HotSpot-specific API đọc `UseZGC` và `UseG1GC`.
- `MemoryMXBean`: snapshot Java heap.

`HotSpotDiagnosticMXBean` thuộc module `jdk.management`, **không phải Java SE API độc lập với mọi JVM implementations**. Bài đang nói về HotSpot/OpenJDK có ZGC; với runtime khác, không được coi ví dụ này là phương pháp portable không điều kiện.

### File `ZgcModeProbe.java`

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import com.sun.management.HotSpotDiagnosticMXBean;

public final class ZgcModeProbe {
    private static String option(
            HotSpotDiagnosticMXBean bean, String name) {
        try {
            return bean.getVMOption(name).getValue();
        } catch (IllegalArgumentException ex) {
            return "<unsupported>";
        }
    }

    public static void main(String[] args) {
        HotSpotDiagnosticMXBean hotSpot =
                ManagementFactory.getPlatformMXBean(
                        HotSpotDiagnosticMXBean.class);

        System.out.println(
                "jdkFeature=" + Runtime.version().feature());
        System.out.println(
                "useZgc=" + option(hotSpot, "UseZGC"));
        System.out.println(
                "useG1gc=" + option(hotSpot, "UseG1GC"));

        List<String> names = new ArrayList<>();
        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            names.add(gc.getName());
        }
        Collections.sort(names);
        System.out.println("collectorBeans=" + names);

        byte[][] liveWindow = new byte[32][];
        long checksum = 0;

        for (int i = 0; i < 5000; i++) {
            byte[] bytes = new byte[32 * 1024];
            bytes[0] = (byte) i;
            checksum += bytes[0];
            liveWindow[i % liveWindow.length] = bytes;
        }

        MemoryMXBean memory =
                ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();

        System.out.println(
                "maxHeapPositive=" + (heap.getMax() > 0));
        System.out.println(
                "activeWindowSlots=" + liveWindow.length);
        System.out.println("checksum=" + checksum);
    }
}
```

### Lệnh biên dịch/chạy

```bash
javac --release 11 --add-modules jdk.management ZgcModeProbe.java

java --add-modules jdk.management -XX:+UseZGC -Xms64m -Xmx256m ZgcModeProbe

java --add-modules jdk.management -XX:+UseG1GC -Xms64m -Xmx256m ZgcModeProbe
```

Vì đây là **HotSpot-specific diagnostic exercise**, nếu runtime không có `HotSpotDiagnosticMXBean`, chương trình cần có nhánh fallback/null check hoặc chỉ chạy với HotSpot family. Các lệnh đã được thử với **Zulu OpenJDK 24.0.2** và hoạt động.

### Stdout đã xác minh: ZGC (JDK 24.0.2)

```text
jdkFeature=24
useZgc=true
useG1gc=false
collectorBeans=[ZGC Major Cycles, ZGC Major Pauses, ZGC Minor Cycles, ZGC Minor Pauses]
maxHeapPositive=true
activeWindowSlots=32
checksum=4700
```

### Stdout đã xác minh: G1 (cùng JDK và kích thước heap)

```text
jdkFeature=24
useZgc=false
useG1gc=true
collectorBeans=[G1 Concurrent GC, G1 Old Generation, G1 Young Generation]
maxHeapPositive=true
activeWindowSlots=32
checksum=4700
```

**Kết luận đúng từ hai output:**

1. **`useZgc=true`** và **`useG1gc=false`** cho thấy HotSpot nhận flag chọn ZGC.
2. Names chứa `ZGC Minor/Major Cycles` phản ánh collector generational hiện hành ở runtime thử.
3. Với `-XX:+UseG1GC`, flags và bean names chuyển sang G1 trong cùng môi trường.
4. Chương trình biên dịch với Java **11 source/API baseline** nhưng đang chạy trên **JDK 24**; GC mode được JVM runtime quyết định.
5. `checksum=4700` chỉ chứng minh vòng lặp allocation đã được tính và sử dụng; **không** đo p99 GC pause, throughput hay memory footprint của server.
6. Bean names **không phải Java SE stable strings**; đừng parse nguyên văn trên mọi JDK. Với môi trường production, dùng VM flags và logs/JFR chính thức làm bằng chứng chính.

### Giới hạn cần ghi rõ

- `HotSpotDiagnosticMXBean.getVMOption("UseZGC")` có thể báo option unsupported ở JVM không cung cấp flag tương ứng; không assume mọi Java runtime hỗ trợ ZGC.
- JVM vendor/port có thể thay đổi số lượng và tên GC beans.
- `getHeapMemoryUsage().getMax()` có thể âm nếu runtime không xác định giá trị max; ví dụ này đặt `-Xmx256m` nên trong thử nghiệm `maxHeapPositive=true`.
- Lệnh `java -XX:+UseZGC` trên một JVM/platform không hỗ trợ ZGC có thể **thất bại ngay tại startup**; đừng âm thầm tự thay sang collector khác trong production mà không biết SLA đã thay đổi.

## 9. Mẫu cấu hình log có xoay vòng đã kiểm chứng

Trên JDK 24.0.2, câu lệnh sau chạy thành công và tạo một file `zgc-<pid>.log` trong thư mục làm việc:

```bash
java -XX:+UseZGC \
  -Xms64m \
  -Xmx256m \
  -XX:SoftMaxHeapSize=192m \
  -Xlog:gc*,safepoint:file=zgc-%p.log:time,uptime,level,tags:filecount=3,filesize=4M \
  -version
```

Các chữ trong tên file như `%p` được HotSpot thay bằng process ID. Định dạng log được cấu hình với decorations `time,uptime,level,tags`; rotate theo `filecount` và `filesize`.

Một phần output file đã ghi trong môi trường thử:

```text
[...][info][gc,init] Initializing The Z Garbage Collector
[...][info][gc,init] Version: 24.0.2+12 (release)
[...][info][gc,init] NUMA Support: Disabled
[...][info][gc,init] CPUs: 28 total, 28 available
```

**Các `...` chỉ là viết tắt timestamp/uptime và không phải bytes nguyên văn của log.** Giá trị CPUs, memory, NUMA phụ thuộc máy và container. Việc `-version` tạo file log chỉ xác nhận cấu hình được chấp nhận; muốn phân tích GC cycles/pauses cần chạy workload thực sự có allocations.

### Lưu ý khi chạy PowerShell

Cú pháp nối dòng `\` phía trên dành cho Unix shell. Trong PowerShell hãy đặt thành **một dòng** hoặc dùng backtick nối dòng của PowerShell một cách cẩn thận:

```powershell
java -XX:+UseZGC -Xms64m -Xmx256m -XX:SoftMaxHeapSize=192m -Xlog:gc*,safepoint:file=zgc-%p.log:time,uptime,level,tags:filecount=3,filesize=4M -version
```

Đừng gửi log đến một path mà JVM không thể tạo hoặc không có quyền. Trong container, nếu logs đi vào filesystem tạm, pod restart có thể làm mất log; cân nhắc stdout/stderr collection và log rotation do platform quản lý.

## 10. Heap sizing với ZGC: `-Xmx` là tuning knob quan trọng nhất

### 10.1. `-Xmx` là giới hạn cứng của Java heap

```bash
java -XX:+UseZGC -Xmx4g -jar app.jar
```

Collector chỉ được dùng tối đa khoảng **4 GiB Java heap** (theo quy tắc thực thi). `-Xmx` **không** giới hạn toàn bộ memory của process JVM.

Ví dụ một service có:

- Java heap;
- metaspace, class metadata;
- thread stacks và native thread state;
- JIT code cache;
- direct/off-heap buffers;
- GC metadata/native allocations;
- mmap và các native libraries khác.

Nếu container limit đúng bằng `-Xmx`, process có thể bị **OOMKilled** do các vùng ngoài heap. Luôn dành memory budget cho total process RSS và peak overhead.

### 10.2. Cần headroom cho concurrent allocation

Trong lúc ZGC thu gom đồng thời, ứng dụng tiếp tục tạo objects. Nếu free space không đủ cho allocation spikes, **allocation stalls** có thể xuất hiện. Khi thấy stalls/GC quá bận hoặc OOM:

1. Kiểm tra live-set và allocation rate.
2. Xem `-Xmx` có đủ cho live data **cộng** allocation headroom hay không.
3. Kiểm tra total memory limit của node/container.
4. Xem leak/cache growth hoặc burst allocations.
5. Đo GC CPU và application CPU, không chỉ số lần GC.
6. Chỉ tăng `-Xmx` khi có budget và biết vấn đề không phải giữ tham chiếu không giới hạn.

**Không đặt một tỷ lệ headroom cố định cho tất cả apps.** Tỷ lệ phụ thuộc workload, allocation burst, số CPUs và sự phân bố object lifetimes.

### 10.3. `-Xms` liên quan initial/min heap

```bash
java -XX:+UseZGC -Xms512m -Xmx4g -jar app.jar
```

`-Xms` đặt mức heap ban đầu/tối thiểu cho JVM HotSpot; `-Xmx` đặt maximum. Cấu hình `-Xms < -Xmx` thường cho ZGC cơ hội điều chỉnh committed memory theo nhu cầu; chính sách uncommit/các flags khác cũng ảnh hưởng.

Nếu **`-Xms == -Xmx`**, JVM không uncommit heap xuống dưới mức tối thiểu ấy. Điều này có thể giảm biến động commit/uncommit pages, nhưng cũng có thể giữ memory footprint lớn; không mặc định coi cấu hình ấy là tốt cho cloud cost hoặc container density.

### 10.4. `-XX:SoftMaxHeapSize` là mục tiêu mềm, không phải hard limit

```bash
java -XX:+UseZGC -Xms512m -Xmx4g -XX:SoftMaxHeapSize=3g -jar app.jar
```

Đọc đúng:

- `-Xmx4g`: trần Java heap.
- `SoftMaxHeapSize=3g`: ZGC cố gắng vận hành trong giới hạn mềm khoảng 3 GiB.
- Khi allocation pressure đòi hỏi, ZGC **được phép vượt soft max** để tránh stalls, miễn không vượt `-Xmx`.

**Không lấy soft max làm quota Kubernetes** hoặc điều kiện “JVM tuyệt đối không dùng hơn 3 GiB”. Monitoring nên quan sát heap used/committed và process RSS riêng.

### 10.5. Memory uncommit: giảm footprint khi idle

ZGC có thể trả những heap pages không còn cần thiết cho OS. Theo tài liệu và HotSpot flags:

```text
-XX:+ZUncommit
-XX:ZUncommitDelay=300
```

Ở các build HotSpot mới thử nghiệm, `ZUncommit` được bật mặc định và delay mặc định là **300 giây**. Đây là **tunable theo version**, không nên hard-code mặc định ấy vào mọi JVM vendor nếu chưa kiểm tra.

`-XX:ZUncommitDelay=...` giảm thời gian chờ trước khi JVM trả pages chưa dùng, nhưng commit/uncommit liên tục có chi phí CPU/memory latency. Đối với workload bursty, đặt delay quá thấp có thể gây churn.

**Hai điểm dễ nhầm:**

1. **Java heap used giảm** sau GC không có nghĩa **process RSS giảm ngay**.
2. **-Xms = -Xmx** khiến heap không thể được uncommit xuống thấp hơn floor đã đặt; nếu mục tiêu trả memory khi idle, cần xem lại `-Xms` và uncommit policy.

## 11. Kích thước heap trong container/Kubernetes

### 11.1. Tại sao container memory limit khác `-Xmx`?

Giả sử pod container có memory limit **6 GiB**, đặt `-Xmx6g` sẽ không còn budget rõ ràng cho native allocations. Ngay cả nếu Java heap không đầy, RSS có thể vượt container limit.

Mô hình budget:

```text
Container memory limit
  = Java heap peak
  + metaspace/code cache
  + thread/native stacks
  + direct/off-heap buffers
  + GC/JIT/native runtime overhead
  + các native allocations khác
  + safety margin
```

Đây là mô hình phân bổ tài nguyên, không phải công thức cộng tuyệt đối cho mọi kernel/cgroup accounting. Cần đo thực tế bằng JFR/JMX, NMT khi phù hợp, metrics của container và OS.

### 11.2. CPU limits cũng quan trọng

ZGC dùng concurrent GC workers. Nếu container chỉ được cấp rất ít CPU nhưng allocation rate cao, concurrent work có thể cạnh tranh CPU với application và không thu gom kịp. Việc đổi collector **không thay thế** kế hoạch CPU sizing.

Khi so ZGC với G1 trong Kubernetes:

- đặt giống nhau CPU requests/limits và memory limits;
- kiểm tra CPU throttling;
- dùng cùng image base và JDK version;
- kiểm tra throughput và p99.9;
- đừng chỉ lấy duration GC pause để chọn.

### 11.3. `-XX:MaxRAMPercentage` vs `-Xmx`

HotSpot có thể tính heap ergonomics theo percentage của available RAM/container memory nếu không đặt `-Xmx`; nhưng giá trị default phụ thuộc JDK/runtime và container awareness.

Hai cách chọn budget có thể áp dụng:

```bash
# Cách A: đặt trực tiếp, dễ audit
java -XX:+UseZGC -Xmx2g -jar app.jar

# Cách B: để JVM tính theo RAM percentage (cần test runtime)
java -XX:+UseZGC -XX:MaxRAMPercentage=60 -jar app.jar
```

**Đừng vô tình áp dụng cả hai rồi nghĩ cả hai cùng có tác dụng theo tỷ lệ đơn giản.** Khi `-Xmx` đã được đặt rõ, kiểm tra runtime value bằng `-XX:+PrintFlagsFinal`. Không chọn 60% chỉ vì là số đẹp; allocation headroom và off-heap overhead có thể khiến tỉ lệ phù hợp khác đáng kể.

## 12. Chọn chế độ không phải là chỉnh thủ công young/old generations

Sau JDK 24, generational ZGC **tự động** xử lý young/old generations và heuristics trong khuôn khổ collector. Người dùng không phải (và không còn được) bật/tắt generational mode bằng `ZGenerational`.

Những tên flags quen từ G1/Parallel GC **không có cùng tác dụng tương ứng** với ZGC; ví dụ không áp dụng một “G1NewSizePercent” rồi cho rằng đó là ZGC young size. Các options collector-specific cần được kiểm tra trong `java -XX:+PrintFlagsFinal` và tài liệu đúng JDK.

### Thứ tự tuning đáng ưu tiên

1. **Xác nhận ZGC mode đang chạy**.
2. **Đo latency, throughput, CPU/RSS** trên workload đại diện.
3. **Đặt `-Xmx` đủ live set + concurrent allocation headroom**.
4. Tùy memory goal, đánh giá `-Xms`, `SoftMaxHeapSize` và uncommit.
5. Nếu vẫn có bottleneck, phân tích GC logs/JFR cùng CPU throttling/allocation hotspots.
6. Chỉ cân nhắc advanced tuning options khi có bằng chứng; giữ nguyên adaptive heuristics nếu hoạt động tốt.

Cách làm này tránh “tuning bằng cách bật càng nhiều flags càng tốt”. ZGC được thiết kế để tự điều chỉnh generation sizes, GC thread allocation và tenuring trong các phạm vi mà runtime hỗ trợ.

## 13. Khi nào ZGC là lựa chọn phù hợp?

### 13.1. Nên benchmark ZGC nếu

- Dịch vụ có yêu cầu tail latency nghiêm ngặt.
- GC pauses đang đóng góp đáng kể vào p99/p99.9.
- Heap lớn khiến GC pause của cấu hình hiện tại khó chấp nhận.
- Hệ thống có CPU/memory headroom cho concurrent GC.
- Workload có đủ thời gian warm-up và chạy lâu để đo chênh lệch đáng tin.
- Deployment có JDK/platform HotSpot tương thích ZGC.

### 13.2. Có thể vẫn giữ G1 nếu

- G1 đã đạt SLA với throughput/CPU/memory tốt.
- Ứng dụng chủ yếu là batch/throughput-oriented.
- Heap/workload nhỏ, overhead ZGC không mang lợi ích rõ.
- Latency chủ yếu do DB/network/lock contention.
- Container CPU/memory rất hạn chế và ZGC không chứng minh được ưu thế.
- Vận hành có ít khả năng quan sát/bảo trì một collector mới hơn hiện tại.

**Không có quy tắc “heap trên X GiB bắt buộc dùng ZGC”**. Collector lựa chọn theo SLA thực tế, chứ không đơn thuần là một ngưỡng heap.

### 13.3. Không đánh đồng JDK mới với collector mới

JDK 27 có thể tiếp tục để **G1 làm mặc định**. Nâng JDK không có nghĩa hệ thống tự chuyển sang ZGC. Muốn chọn ZGC phải thấy đúng `UseZGC=true` hoặc bằng chứng tương đương trong startup logs.

## 14. Phương pháp benchmark G1 vs ZGC công bằng

Đây là quy trình so sánh collector, **không phải một công thức kết luận trước kết quả**.

### 14.1. Giữ các điều kiện cố định

- Cùng source commit/JAR/container image (trừ VM flags).
- Cùng JDK major/update/vendor nếu có thể.
- Cùng CPU/RAM/container limits, NUMA config và OS.
- Cùng số clients, request mix, payload size và concurrency.
- Cùng warm-up, thời lượng đo và background load.
- Cùng observability overhead.
- Ít nhất vài lần chạy để giảm tác động nhiễu đo lường.

### 14.2. Hai bộ cấu hình tương đương

```bash
# G1 baseline
java -XX:+UseG1GC -Xms1g -Xmx4g -Xlog:gc*:file=g1.log -jar app.jar

# ZGC experiment
java -XX:+UseZGC -Xms1g -Xmx4g -Xlog:gc*:file=zgc.log -jar app.jar
```

Ví dụ giả định thư mục làm việc có quyền ghi và đủ memory. **`-Xms1g -Xmx4g` chỉ là số minh họa**, không phải giá trị production đề xuất. Cần so sánh cùng total memory constraints, không chỉ cùng `-Xmx` mà bỏ qua native footprint.

### 14.3. Metrics bắt buộc

| Nhóm | Metric | Vì sao |
| --- | --- | --- |
| **Application** | p50/p95/p99/p99.9 response latency | Mục tiêu người dùng |
| **Throughput** | requests/s hoặc jobs/s hoàn thành | Xem giá đổi latency lấy throughput |
| **GC** | GC pause distribution, tổng/đỉnh pause | Kiểm tra lý do chọn ZGC |
| **ZGC** | Major/minor activity, allocation stalls, concurrent CPU | Phát hiện thiếu headroom |
| **Memory** | heap used/committed, live-set trend, process RSS | Tránh memory regression |
| **CPU** | process CPU, GC threads CPU, container throttling | Concurrent GC có thể lấy CPU |
| **Reliability** | OOM, restarts, error rate, timeouts | Collector phải hỗ trợ vận hành ổn định |
| **Workload** | allocation rate, object lifetime, active sessions | Giải thích chênh lệch |

### 14.4. Cách đọc kết quả

Ví dụ giả định:

```text
G1: p99.9 request latency = 120ms, throughput = 20k req/s
ZGC: p99.9 request latency = 75ms, throughput = 18k req/s
```

**Đây là số giả định minh họa phép đánh đổi, không phải benchmark đã chạy.** Nếu SLA đòi p99.9 dưới 80 ms và 18k req/s vẫn đáp ứng capacity, ZGC có thể phù hợp. Nếu throughput tối thiểu là 19k req/s, cấu hình này **chưa đạt** dù tail latency tốt hơn.

Không lấy tổng lượng GC pauses giảm rồi bỏ qua việc ZGC tăng CPU hoặc làm throughput tụt quá giới hạn.

### 14.5. Không microbenchmark bằng `System.gc()`

Một loop gọi `System.gc()` liên tục không mô phỏng allocation profile của một REST service. Collector-specific behavior với explicit GC có thể khác và các flags như `-XX:+DisableExplicitGC` có thể vô hiệu hóa lời gọi.

Tốt hơn: load test có đường phân bố object lifetime gần production, đo app latency và logs/JFR dưới tải thực tế.

## 15. Quan sát ZGC qua JFR/JMX

### 15.1. Unified GC logging là bằng chứng ở mức JVM

```bash
java -XX:+UseZGC -Xlog:gc*,safepoint -jar app.jar
```

Khi cần phân tích cụ thể:

- Các GC cycles minor/major diễn ra khi nào?
- GC phải dừng application threads trong những pha nào?
- Có allocation stall không?
- CPU có bị throttling lúc concurrent GC không?
- Sau thu gom, heap used còn bao nhiêu so với max?
- Log volume có quá lớn khi bật `gc*` không?

Định dạng log và tên phases thay đổi theo JVM version. **Không hứa mọi ZGC log phải có chính xác tên “Minor Collection (Allocation Rate)”**. Các công cụ parser cần hỗ trợ runtime tương ứng.

### 15.2. JFR bổ sung timeline application-level

JFR có thể giúp liên hệ GC events với:

- thread scheduling/CPU usage;
- allocation hotspots;
- application custom events;
- latency spans do ứng dụng ghi;
- safepoint events khi bật/phù hợp.

**JFR không đo thay response-time histograms của ứng dụng.** Để quyết định collector, cần phối hợp cả tail latency từ load generator/metrics và timeline GC.

### 15.3. JMX/MXBeans là dữ liệu của JVM thực tế

`GarbageCollectorMXBean` cung cấp GC names, collection counts/times nếu runtime hỗ trợ. Không so trực tiếp số “minor cycles” của ZGC với “young GC count” của G1 như cùng một đơn vị work.

Đối với generational ZGC, một số MXBeans có tên `Minor/Major Cycles` và `Pauses` cùng tồn tại. **Đừng cộng mọi bean count rồi tuyên bố đó là tổng số physical GC cycles**, vì cùng một sự kiện có thể có nhiều view/phase.

### 15.4. GC logs và JFR có thể thiếu bối cảnh nghiệp vụ

Một burst allocations 2 GiB có thể đến từ batch đang chạy hợp lệ hoặc một bất thường; GC chỉ nói xảy ra allocation pressure. Muốn biết root cause, thêm metrics như queue depth, active sessions, request class, cache entry count và workload phase.

## 16. Các sai lầm cấu hình thường gây lỗi

### Sai lầm 1 — Dùng `ZGenerational` trên JDK 24+

```text
-XX:+UseZGC -XX:+ZGenerational
```

Đây là **mẫu cần loại khỏi cấu hình**, không phải lệnh khuyến nghị. ZGC hiện hành không có mode switch này. Trên JDK 24 có thể warning ignored; trên JDK mới hơn có thể startup failure.

**Sửa:**

```bash
java -XX:+UseZGC -jar app.jar
```

### Sai lầm 2 — Tưởng ZGC được chọn chỉ vì JDK đủ mới

```bash
java -jar app.jar
```

Theo JDK 27 HotSpot docs, collector mặc định là **G1**, trừ khi flags/cấu hình cụ thể khác. Muốn ZGC, phải chọn rõ.

### Sai lầm 3 — Đặt `-XX:+UseZGC` sau `-jar app.jar`

Flags JVM ở sai vị trí không có tác dụng như mong muốn. Đặt flags trước `-jar`/main class.

### Sai lầm 4 — Dùng các experimental flags cũ

`-XX:+UnlockExperimentalVMOptions` **không cần thiết** để bật ZGC từ JDK 15. Nó không phải một cách chọn generational hiện hành; đừng dùng chỉ vì tutorial cho Java 11 đầu tiên nói phải unlock.

### Sai lầm 5 — Coi `SoftMaxHeapSize` là hard ceiling

ZGC có thể vượt soft max tới `-Xmx`. Nếu muốn bảo vệ container, đặt hợp lý cả memory limit và `-Xmx`, kèm margin cho native memory.

### Sai lầm 6 — Dùng `-Xmx` bằng container memory limit

JVM còn nhiều vùng ngoài Java heap. Cấu hình này tạo rủi ro OOMKilled ở thời điểm heap chưa đầy.

### Sai lầm 7 — Ép `-Xms=-Xmx` để “tiết kiệm RAM”

Việc cố định floor cao có thể **giữ nhiều heap committed hơn**, không phải giảm memory footprint. Nếu muốn tối ưu latency và chấp nhận memory footprint, có thể đánh giá cấu hình đó; nếu muốn density/return unused memory, cân nhắc floor thấp và uncommit.

### Sai lầm 8 — So ZGC với G1 ở những JDKs khác nhau

Chạy G1 trên Java 11 nhưng ZGC trên Java 27 rồi kết luận collector mới nhanh hơn là một thí nghiệm **nhiễu**, vì cả JIT, libraries, GC algorithms và container ergonomics khác nhau. So trong cùng một JDK trước, sau đó mới thử migration matrix.

### Sai lầm 9 — Thấy GC pause thấp là đủ quyết định

ZGC có thể giảm pauses nhưng làm throughput giảm hoặc CPU overhead tăng. Quyết định theo SLA end-to-end.

### Sai lầm 10 — Giữ parse rules dựa trên tên GC bean cố định

JMX bean names và log format thay đổi. Với automated tooling, test đúng JDK versions hỗ trợ, dựa thêm flags/metadata, không assume mọi ZGC runtime in đúng một string.

## 17. Tình huống thực tế và cách chọn

### A. Payment API có p99.9 bị đẩy lên khi có GC pauses

1. Chứng minh ứng dụng đang dùng G1, không phải ZGC.
2. So correlation giữa GC pauses và request spikes.
3. Chạy cùng JDK/app với ZGC, cùng memory limit.
4. Đặt `-Xmx` đủ headroom, đánh giá CPU.
5. Đo lại p99.9, timeouts, error rate và throughput.
6. Nếu có cải thiện rõ, lên kế hoạch canary/staged rollout.

**Không hứa “ZGC đảm bảo mọi thanh toán dưới 10ms”** — giao dịch còn network/database/lock.

### B. Batch ETL tạo nhiều temporary objects, không có pause SLA nghiêm

G1/Parallel collector có thể có throughput tốt hơn; ZGC chỉ đáng chọn nếu workload thực có bottleneck latency. Tránh bật ZGC chỉ vì “nhiều allocations” mà không đo cost.

### C. Service cần tối ưu RAM trên container nhỏ

Đầu tiên kiểm tra heap live set, direct memory, thread count, memory limit. ZGC cần headroom cho concurrent GC và có collector overhead. Với mục tiêu chi phí/density thuần túy, so với G1 trước khi quyết định.

### D. App cũ từ JDK 21 nâng lên JDK 25

Cấu hình cũ có thể chứa:

```text
-XX:+UseZGC
-XX:+ZGenerational
```

Trên JDK 25, bỏ dòng thứ hai. Dùng `-XX:+UseZGC`, chạy integration/load tests, kiểm tra startup flags, GC logs và latency. **Không dùng `-XX:-ZGenerational` để quay về collector đã bị xóa**.

### E. JDK 27 startup báo unrecognized `ZGenerational`

Kiểm tra mọi nguồn JVM args, gồm service scripts, `JAVA_TOOL_OPTIONS`, Docker/Kubernetes manifests và launcher configuration. Xóa option ấy khỏi **lệnh chạy thực tế**, sau đó xác nhận `java -XX:+UseZGC -Xlog:gc -version` hoạt động.

### F. ZGC đã bật nhưng latency vẫn cao

Tách:

- GC pauses có cao không?
- Có allocation stalls vì headroom thiếu không?
- CPU throttling xảy ra khi concurrent GC chạy?
- Network/DB có phải nguồn p99 chính?
- Thread pool queue/backpressure, locks hoặc I/O có vấn đề?
- Heap used/live set có tăng không giới hạn do retention?

Không nên vô tội vạ tăng `-Xmx` nếu nguyên nhân là deadlock, thread starvation hoặc slow query.

## 18. Checklist triển khai ZGC hiện hành

Trước khi chốt config production, kiểm tra:

- [ ] Runtime là HotSpot/OpenJDK build có hỗ trợ ZGC trên OS/architecture tương ứng.
- [ ] JDK version rõ ràng; trên JDK 24+ hiểu ZGC là **generational-only**.
- [ ] Chỉ dùng `-XX:+UseZGC` để chọn ZGC, không mang `ZGenerational` cũ.
- [ ] Collector flags đứng trước `-jar`.
- [ ] `-Xmx` đủ cho live set và concurrent allocation headroom.
- [ ] Container memory limit có margin cho non-heap memory.
- [ ] `-Xms`/`SoftMaxHeapSize`/uncommit phù hợp latency và memory footprint goals.
- [ ] GC logs được thu, giới hạn dung lượng và không làm lộ dữ liệu nhạy cảm.
- [ ] `UseZGC=true` hoặc `Using The Z Garbage Collector` được xác nhận.
- [ ] Đo p50/p95/p99/p99.9, throughput, CPU, RSS, heap used/committed, allocation stalls.
- [ ] Benchmark G1 vs ZGC trên cùng JDK/workload/infrastructure.
- [ ] Có canary/rollback, test startup errors và quan sát sau deploy.
- [ ] Sửa tận gốc memory leaks/allocation hotspots thay vì chỉ thay collector để che triệu chứng.

Checklist này là **đề xuất quy trình vận hành**, không phải yêu cầu JVM đòi tất cả các mục mới khởi động.

## 19. Câu hỏi tự kiểm tra — có đáp án

**1.** Trên JDK 27, muốn chạy ZGC generational cần option nào?

**Đáp án:** `-XX:+UseZGC`. ZGC của dòng JDK 24+ chỉ còn generational mode.

**2.** Có cần thêm `-XX:+ZGenerational` không?

**Đáp án:** Không. Option `ZGenerational` đã bị loại bỏ như mode switch từ JDK 24; trên JDK mới có thể bị bỏ qua hoặc gây unrecognized-option error.

**3.** Nếu không đặt GC flags, JDK 27 HotSpot mặc định dùng gì?

**Đáp án:** G1, theo Oracle HotSpot JDK 27 tuning guide.

**4.** ZGC còn experimental không?

**Đáp án:** Không. ZGC được đưa vào production từ JDK 15.

**5.** `-XX:+UnlockExperimentalVMOptions` có bắt buộc để bật ZGC trên JDK 25 không?

**Đáp án:** Không; không cần để chọn ZGC hiện hành.

**6.** Java source biên dịch `--release 11`, chạy trên JDK 27, thì mode ZGC theo Java 11 hay 27?

**Đáp án:** Theo **JVM runtime JDK 27** và JVM startup flags, không theo source compatibility target.

**7.** Generational ZGC phân chia heap theo ý tưởng nào?

**Đáp án:** Phân biệt objects ngắn đời/young và objects sống lâu/old, dùng đặc điểm đa số allocations nhanh chóng chết để tối ưu GC work.

**8.** ZGC có đảm bảo request p99.9 dưới một mili-giây không?

**Đáp án:** Không. GC pause chỉ là một thành phần latency; network/DB/locks/OS/JIT và CPU saturation vẫn ảnh hưởng.

**9.** Vì sao ZGC cần headroom trên heap?

**Đáp án:** Vì application vẫn allocate khi collector chạy concurrent, cần chỗ trống để phục vụ allocations trong thời gian thu gom.

**10.** `SoftMaxHeapSize=3g -Xmx4g` có cấm ZGC vượt 3 GiB heap không?

**Đáp án:** Không. 3 GiB là soft target; ZGC có thể vượt tới 4 GiB khi cần tránh stalls.

**11.** `-Xmx4g` có nghĩa process JVM không bao giờ dùng hơn 4 GiB RSS không?

**Đáp án:** Không. Native threads, metaspace, code cache, direct buffers, GC metadata... nằm ngoài Java heap.

**12.** `-Xms=-Xmx` có khiến ZGC trả nhiều memory cho OS khi idle hơn không?

**Đáp án:** Không. Nó giữ heap minimum cao và có thể hạn chế uncommit.

**13.** Làm sao kiểm tra nhanh JVM có chọn ZGC không?

**Đáp án:** `java -XX:+UseZGC -Xlog:gc -version`, tìm `Using The Z Garbage Collector`; cũng có thể xem `UseZGC` bằng `PrintFlagsFinal`/`jcmd` hoặc HotSpot MXBean.

**14.** Một chương trình dùng `HotSpotDiagnosticMXBean` có portable sang mọi JVM không?

**Đáp án:** Không. Đây là API cụ thể của HotSpot/JDK, nên chỉ dùng khi runtime có module `jdk.management` và triển khai hỗ trợ.

**15.** Thấy `ZGC Minor Cycles` bean chứng minh tất cả GC pauses đều là minor GC không?

**Đáp án:** Không. Bean names là metadata implementation-specific; cần phân tích log/JFR/collection types và không cộng các counters tùy ý.

**16.** Vì sao phải so ZGC và G1 trong cùng JDK?

**Đáp án:** Để tránh kết quả bị ảnh hưởng bởi thay đổi JIT/runtime/libraries/GC implementation giữa các JDK khác nhau.

**17.** Nếu ZGC giảm GC pause nhưng throughput giảm quá mức SLA, có nên dùng không?

**Đáp án:** Chưa chắc. Cần xét cả latency, throughput, CPU, RSS và reliability budgets.

**18.** Có thể chuyển collector sau khi JVM đã chạy bằng `System.setProperty("UseZGC", "true")` không?

**Đáp án:** Không. Collector được chọn khi JVM startup qua VM options; Java system properties không thay đổi collector của process đang chạy.

**19.** Container limit 2 GiB có nên đặt `-Xmx2g` không?

**Đáp án:** Không nên mặc định. Cần chừa memory cho native/non-heap allocations và overhead, đo thực tế.

**20.** Khi app có leak giữ references không giới hạn, đổi G1 sang ZGC có sửa leak không?

**Đáp án:** Không. Collector chỉ reclaim unreachable objects; nếu app vẫn giữ strong references, memory vẫn có thể tăng đến OOM.

**21.** Vì sao `-XX:+UseZGC` sau `-jar app.jar` không bật ZGC?

**Đáp án:** Vì đó là application argument, không phải JVM startup option được parse trước `-jar`.

**22.** `-XX:ZUncommitDelay` giảm có phải luôn cải thiện latency không?

**Đáp án:** Không. Uncommit sớm có thể giảm footprint khi idle nhưng tăng commit/uncommit churn ở workload bursty.

**23.** Nếu `ZGenerational` trên JDK 24 chỉ bị warning và ignored, vì sao vẫn phải bỏ?

**Đáp án:** Nó không còn chọn mode nào; các JDK mới hơn có thể từ chối. Cấu hình sạch dùng `-XX:+UseZGC` và tránh phụ thuộc obsolete option behavior.

**24.** ZGC hiện hành có tự động điều chỉnh generation sizes không?

**Đáp án:** Có, theo design adaptive của Generational ZGC; không cần tự tách young/old bằng flag `ZGenerational`.

**25.** KPI quan trọng nhất để chọn ZGC cho một dịch vụ web là gì?

**Đáp án:** KPI theo mục tiêu hệ thống: end-to-end tail latency cùng throughput/CPU/memory/reliability. GC pause distribution là dữ liệu chẩn đoán, không phải thay thế SLA ứng dụng.

## 20. Nguồn tham khảo chính thức và còn áp dụng

1. [Oracle JDK 27 — HotSpot VM Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/27/gctuning/): tài liệu hiện hành (09/2026), xác nhận collector lựa chọn và yêu cầu benchmark.
2. [Oracle JDK 27 — Available Collectors](https://docs.oracle.com/en/java/javase/27/gctuning/available-collectors.html): G1 mặc định, dùng `-XX:+UseZGC` để chọn ZGC, định hướng chọn theo latency.
3. [Oracle JDK 27 — java command options](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `UseZGC`, `-Xms`/`-Xmx`, unified logging, JVM flags.
4. [Oracle JDK 24 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html): generational-only từ JDK 24, `SoftMaxHeapSize`, uncommit và heap sizing.
5. [Oracle JDK 24 — Significant Changes](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html): xác nhận non-generational ZGC bị xóa theo JEP 490.
6. [OpenJDK JEP 490 — Remove the Non-Generational Mode](https://openjdk.org/jeps/490): cơ chế chuyển sang generational-only ở JDK 24.
7. [OpenJDK JEP 474 — Generational Mode by Default](https://openjdk.org/jeps/474): JDK 23 chọn generational default.
8. [OpenJDK JEP 439 — Generational ZGC](https://openjdk.org/jeps/439): cơ sở thiết kế collector generational.
9. [OpenJDK JEP 377 — ZGC Production](https://openjdk.org/jeps/377): ZGC được đưa vào sử dụng production từ JDK 15.
10. [Oracle JDK 15 release notes](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): `-XX:+UseZGC` không cần experimental unlock.
11. [Oracle Java SE 11 — java tool](https://docs.oracle.com/en/java/javase/11/tools/java.html): cú pháp unified GC logging còn hữu ích trên JDK mới.
12. [Oracle Java SE 11 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): quan sát collector metadata với JMX.
13. [Oracle Java SE 11 — HotSpotDiagnosticMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html): đọc VM options và HotSpot diagnostics.
14. [Oracle JDK 27 release notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác định JDK 27 phát hành 15/09/2026, không nhầm với tài liệu tương lai/draft.

### Ghi nhớ sau bài học

**JDK 24–27: chọn ZGC bằng `-XX:+UseZGC`, và collector chạy ở _Generational ZGC_ duy nhất.** Không thêm các cờ `ZGenerational` đã bị loại bỏ. Giữ G1 làm baseline, kiểm chứng collector bằng logs/VM flags, sizing `-Xmx` theo live set cộng headroom, phân biệt `SoftMaxHeapSize` với hard max, đo p99/p99.9 cùng throughput/CPU/RSS và chỉ quyết định dựa trên workload thực tế.