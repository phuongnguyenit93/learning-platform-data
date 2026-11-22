# Đối chiếu khả năng collector với tài liệu JDK đang triển khai (Java 11+)

## 1. Vì sao phải đối chiếu collector theo chính bản JDK đang chạy?

Trong chủ đề **GC độ trễ thấp**, không thể chọn thuật toán thu gom rác chỉ từ câu “Java hỗ trợ ZGC/Shenandoah” của một bài blog, một trang JEP hay tài liệu của một bản JDK khác. Cần xác minh **binary JDK thực sự triển khai**, gồm phiên bản và bản vá, vendor/build, hệ điều hành/CPU, tình trạng tính năng production hay experimental, cờ JVM được chấp nhận, collector **thực sự đang chạy** và **hiệu quả trên workload**.

Ví dụ, hai ứng dụng cùng viết cho **Java 11** có thể được triển khai bằng hai JDK 11u của những vendor khác nhau. Một build có thể được đóng gói kèm Shenandoah; build khác không. Trong khi đó, JDK 25 có Generational ZGC và Generational Shenandoah đã là product feature, nhưng điều này **không có nghĩa** binary Java 11 trước đó có những chế độ tương ứng.

Nguyên tắc:

> **JEP/tài liệu chứng minh khả năng thiết kế theo phiên bản; startup probe chứng minh binary có thể bật một collector; runtime logs/MXBeans chứng minh collector nào đang hoạt động; benchmark chứng minh có đạt SLO hay không.** Không thay một lớp bằng lớp khác.

Quy trình 5 lớp:

```text
[1] Runtime identity
    JDK major/update, vendor/build, VM, OS/architecture, container
        |
[2] Documentation
    GC Tuning Guide + release notes + vendor support matrix
        |
[3] Capability probe
    Khởi động JVM mới với cờ collector, xem exit code / stderr
        |
[4] Active collector
    GC logs, jcmd VM.flags, GarbageCollectorMXBean
        |
[5] Load test
    GC pause p99, request tail latency, throughput, CPU, heap, RSS
        |
        v
    Quyết định triển khai/canary có bằng chứng
```

Câu hỏi “**có thể bật**” khác câu hỏi “**có nên bật**”. Một VM chấp nhận `-XX:+UseZGC` không đồng nghĩa ZGC có thể xử lý workload của bạn với giới hạn CPU, bộ nhớ và độ trễ tốt hơn G1.

## 2. Các collector cần biết khi nhắm tới độ trễ thấp

| Collector | Đặc điểm | Trường hợp nên đánh giá | Trade-off phải đo |
| --- | --- | --- | --- |
| **G1** | Collector theo vùng heap, mostly concurrent và có các pha stop-the-world; có mục tiêu pause | Baseline mặc định của nhiều HotSpot server-class JDK 11+ | Mục tiêu `MaxGCPauseMillis` là mềm; tail pause vẫn có thể vượt mục tiêu |
| **ZGC** | Concurrent low-pause GC; trên JDK hiện đại là **generational** | P99/p99.9 latency rất chặt, heap lớn hoặc pause tail G1 khó đáp ứng | CPU cho concurrent GC, heap/headroom, allocation stalls, throughput và footprint |
| **Shenandoah** | Concurrent mark/evacuation/compaction nhằm giảm pause | Khi binary vendor **có hỗ trợ** và yêu cầu low-pause phù hợp | Vendor/build support, mode `satb`/`generational`, concurrent CPU/memory overhead |
| **Parallel** | Thông lượng cao với thu gom song song, vẫn có stop-the-world GC | Batch/offline hoặc hệ thống không có pause SLO chặt | Pause có thể lớn |
| **Serial** | Collector đơn giản, ít tài nguyên phụ trợ | Máy rất nhỏ/CPU ít khi đã kiểm tra tải | Không phù hợp mục tiêu pause nghiêm ngặt trên heap lớn |

**G1** được chọn mặc định trên nhiều cấu hình HotSpot từ các JDK hiện đại. Nhưng “mặc định” phụ thuộc ergonomics: CPU, RAM, container limit, VM implementation và cờ mà launch script truyền. Phải **quan sát thực tế** thay vì chỉ dựa trên kỳ vọng.

**ZGC/Shenandoah** làm phần lớn công việc đồng thời với ứng dụng; điều này giảm pause nhưng không làm chi phí GC biến mất. CPU concurrent GC cũng cạnh tranh với business threads, và thiếu heap headroom vẫn có thể gây stalls, fallback collections hoặc OOM. Không có cam kết “mọi pause đều nhỏ hơn 1 ms” cho mọi điều kiện.

**Không đề xuất CMS làm lựa chọn GC mới.** Concurrent Mark-Sweep đã bị deprecated ở JDK 9, rồi **bị loại bỏ ở JDK 14**. Tài liệu JDK 11 lịch sử có thể còn nói về `UseConcMarkSweepGC`, nhưng nó không phải giải pháp hiện hành để thiết kế triển khai mới. Sự tồn tại của tài liệu cũ không làm collector đã loại trở lại được.

## 3. Dòng thời gian tính năng — mốc OpenJDK không thay thế support matrix của vendor

| Phiên bản / mốc | G1 | ZGC | Shenandoah |
| --- | --- | --- | --- |
| **JDK 11** | G1 có sẵn, default trên nhiều máy chủ | **Experimental**, JEP 333; giới hạn platform/build | **Không mặc nhiên có trong mọi binary**. Một số JDK 11u vendor backport và opt-in khi build |
| **JDK 12** | Có | Đang tiếp tục phát triển | Shenandoah được tích hợp vào mainline theo JEP 189, ở trạng thái experimental |
| **JDK 15** | Có | **Production feature**, JEP 377 | Có ở những build/vendor cung cấp |
| **JDK 17 (LTS)** | Có | Non-generational ZGC ở mốc này | Hỗ trợ phụ thuộc build/vendor, nhiều OpenJDK builds có |
| **JDK 21 (LTS)** | Có | **Generational ZGC opt-in** theo JEP 439: `-XX:+ZGenerational` cùng `-XX:+UseZGC` | Không coi generational Shenandoah là mode thông thường ở mốc này |
| **JDK 23** | Có | **Generational ZGC trở thành mặc định** khi chọn ZGC; non-generational deprecated, JEP 474 | Build-specific |
| **JDK 24** | Có | **Non-generational mode bị loại bỏ**, JEP 490 | Generational Shenandoah **experimental**, JEP 404, nếu vendor build có |
| **JDK 25 (LTS)** | Có | Chỉ còn generational ZGC | Generational Shenandoah chuyển thành **product feature** theo JEP 521, nhưng **không có trong mọi binary** |
| **JDK 27** | Có trong Oracle HotSpot GC guide hiện hành | Có trong Oracle guide, generational | Phải xem vendor build và JDK release notes; không tự suy ra Oracle và mọi OpenJDK distro giống nhau |

Đây là bảng **đối chiếu quá trình phát triển**, không phải giấy chứng nhận hỗ trợ production cho một môi trường cụ thể. Chính xác nhất luôn là **version + update + vendor/build + OS/architecture + binary đang dùng**.

### Những chuyển đổi dễ làm script cũ sai

1. **ZGC JDK 11** là experimental: thường cần `-XX:+UnlockExperimentalVMOptions -XX:+UseZGC`, và không phải mọi CPU/OS/build hỗ trợ.
2. **ZGC JDK 15** thành production feature: nhưng cần dùng tài liệu của JDK phiên bản đang chạy để biết flags và hạn chế.
3. **Generational ZGC JDK 21** là opt-in bằng `-XX:+ZGenerational`; việc chỉ dùng `-XX:+UseZGC` trên JDK 21 chọn hành vi mặc định khác JDK 25.
4. **JDK 23** chuyển generational mode thành mặc định khi chọn ZGC.
5. **JDK 24+** bỏ hẳn non-generational ZGC. Cờ `ZGenerational` từ JDK 21 **không còn cần**, có thể trở thành obsolete/ignored; không dùng việc startup thành công để chứng minh cờ còn tác dụng.
6. **Generational Shenandoah**: JDK 24 experimental (JEP 404), JDK 25 product feature (JEP 521), nhưng **phải có Shenandoah trong binary** và chọn mode thích hợp.
7. Với **JDK 11u Shenandoah backport**, sự hỗ trợ khác nhau theo vendor/bản cập nhật; không nói “mọi Java 11 đều có” chỉ vì dự án Shenandoah có lịch sử hỗ trợ Java 11u.

Nâng major JDK mà giữ nguyên launch flags **không bảo đảm GC behavior giữ nguyên**, vì defaults và thuật toán của collector có thể được thay đổi ngay khi flags giống nhau.

## 4. Thu thập danh tính runtime: chính binary trong container/service

Trước khi chỉnh GC, ghi lại:

```bash
java -version
java -XshowSettings:properties -version
```

Lệnh thứ hai hiển thị nhiều properties và đường dẫn, nên **không đăng nguyên stdout lên kênh công khai** khi chưa xem xét thông tin nhạy cảm.

Checklist:

```text
Runtime inventory (thay bằng giá trị thật):
  java.runtime.version / patch level:
  java.vendor:
  java.vm.name / java.vm.version:
  java.home (đường dẫn runtime thật):
  OS name, architecture:
  Container image digest:
  CPU quota, memory limit:
  -Xms / -Xmx / GC options:
  Security/patch support status:
```

**Quan trọng với container/Kubernetes:** `java` trên laptop, build agent hoặc host có thể khác `java` trong image đang chạy. Một service có thể dùng `$JAVA_HOME/bin/java`, một launcher riêng hoặc một runtime image từ `jlink`. Đừng chỉ ghi “Java 11” theo `pom.xml`/`build.gradle` rồi khẳng định JDK production có cùng GC capabilities.

Kiểm tra OS/architecture/cgroup limit, vì khả năng hỗ trợ và hiệu quả của collector phụ thuộc platform. Cùng JDK major version nhưng build x86_64/Linux, Windows hoặc AArch64 có thể không có đúng cùng flags/modes/độ trưởng thành.

## 5. Đối chiếu đúng tài liệu: ba loại bằng chứng không thể thay nhau

### Tài liệu version-specific

Đọc **GC Tuning Guide** của **đúng major JDK** (ví dụ Oracle HotSpot guide Java 11 hoặc Java 25/27). Đọc thêm release notes/migration guide để biết cờ đã đổi, mode được thêm/bỏ, bug fixes và hạn chế của phiên bản.

### Vendor/build matrix

Với GC không được build vào mọi distro, đặc biệt **Shenandoah**, xem tài liệu vendor, bản phát hành, kiến trúc CPU, OS và support policy. Một JEP đã được tích hợp vào OpenJDK mainline **không buộc tất cả vendor binaries** phải ship tính năng đó. Ví dụ một số OpenJDK 11u vendors bật Shenandoah nhưng Oracle JDK không cung cấp.

### Runtime probe

Dùng chính `java` binary thực tế để thử cờ. Chỉ khi JVM khởi động thành công và reporting xác nhận active GC mới có bằng chứng collector khả dụng ở môi trường đó. Nhưng điều này **không chứng minh** pause/throughput SLA.

**Thứ tự khuyến nghị:** Đọc đúng tài liệu → thử binary → xác minh collector thực → benchmark. Nếu ba nguồn mâu thuẫn, kiểm tra bạn đã so sánh đúng binary/major/vendor/OS chưa trước khi kết luận tài liệu sai.

## 6. Startup probe: kiểm tra bản JDK có nhận collector hay không

Trên môi trường giống production, thử **ba JVM độc lập**:

```bash
java -XX:+UseG1GC -version
java -XX:+UseZGC -version
java -XX:+UseShenandoahGC -version
```

**Không gộp nhiều `Use...GC` trên cùng một JVM**. Mỗi dòng là một process riêng; kiểm tra **exit code**, stderr, cảnh báo “flag is obsolete/ignored”, lỗi “Unrecognized VM option”, “JVM not configured with ... GC” và các hạn chế platform.

Với **JDK 11 và ZGC experimental**, nếu build hỗ trợ, thử:

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseZGC -version
```

Trên các build Shenandoah đời cũ, vendor docs có thể yêu cầu `UnlockExperimentalVMOptions`; chỉ dùng khi tài liệu **đúng version** ghi nhận. Unlock flag **không thể thêm collector bị loại khỏi binary khi build**.

Trên **JDK 25+ có Generational Shenandoah**, thử:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -version
```

Với **JDK 24 Generational Shenandoah experimental**, kiểm tra thêm `-XX:+UnlockExperimentalVMOptions` cùng các ràng buộc phù hợp của build; không copy nguyên sang JDK 25 khi không còn cần experimental gate.

**Cẩn trọng:** Không thêm `-XX:+IgnoreUnrecognizedVMOptions` vào capability test. Nó có thể khiến một cờ GC không được nhận vẫn bị **bỏ qua**, gây kết quả “test pass giả”. Nếu cần xác minh nghiêm túc, một startup thất bại phải được báo nguyên nhân, không bị che.

**Một lần `java -version` thành công với flag không xác định được benchmark:** JVM khởi động được có thể vẫn gặp allocation stalls, thiếu CPU/RAM, OOM hoặc p99 latency xấu khi chạy tải thực.

## 7. Runtime active collector: GC logs, VM flags và MXBeans

Để kiểm tra collector đang hoạt động:

```bash
java -Xlog:gc=info -XX:+UseG1GC -version
```

Khi GC logging được bật, HotSpot thường hiển thị collector đã chọn, ví dụ `Using G1`. Log format khác nhau theo collector/JDK; không dùng một regex bất biến cho mọi phiên bản.

Trên một JVM process thật và bạn có quyền diagnostic attach:

```bash
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

Thay `<PID>` bằng process ID thật. `VM.command_line` có thể lộ `-Dsecret` hoặc đường dẫn nhạy cảm; chỉ chia sẻ log đã được rà soát. `VM.flags` giúp xem flags có hiệu lực, `GC.heap_info` cung cấp chi tiết heap/collector tùy implementation.

**`java.lang.management.GarbageCollectorMXBean`** là API Java 11 có thể liệt kê tên các collector beans **đang hoạt động**, không phải bảng mọi collector có sẵn trên binary. Một GC có thể có nhiều beans cho phases/generations; không suy số MXBean thành “số collectors đang hỗ trợ”.

## 8. Ví dụ Java 11 runnable: nhận diện GC thực sự được JVM chọn

Chương trình sau dùng chỉ **public Java 11 APIs**, kiểm tra tên `GarbageCollectorMXBean` theo quy tắc tương thích với nhiều HotSpot JVM, so sánh family tìm được với đối số và kiểm tra maximum heap dương. Nó **không dùng internal classes hay JDK-specific reflective hacks**.

Lưu file **`CollectorCapabilityDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.Locale;

public class CollectorCapabilityDemo {
    private static String detectFamily() {
        StringBuilder names = new StringBuilder();
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            names.append(' ')
                 .append(bean.getName().toLowerCase(Locale.ROOT));
        }
        String all = names.toString();

        if (all.contains("shenandoah")) return "Shenandoah";
        if (all.contains("zgc") || all.contains("z garbage")) return "ZGC";
        if (all.contains("g1")) return "G1";
        if (all.contains("parallel") ||
                all.contains("ps scavenge")) return "Parallel";
        if (all.contains("copy") ||
                all.contains("marksweepcompact")) return "Serial";
        return "Unknown";
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Use: CollectorCapabilityDemo <expectedFamily>");
        }

        String detected = detectFamily();
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

        System.out.println("detectedFamily=" + detected);
        System.out.println("expectedMatches=" + detected.equals(args[0]));
        System.out.println("gcBeansFound=" +
                !ManagementFactory.getGarbageCollectorMXBeans().isEmpty());
        System.out.println("heapMaximumPositive=" + (heap.getMax() > 0));
    }
}
```

Biên dịch (JDK 11 trở lên):

```bash
javac --release 11 CollectorCapabilityDemo.java
```

**Chạy với G1:**

```bash
java -Xms64m -Xmx256m -XX:+UseG1GC CollectorCapabilityDemo G1
```

**Stdout trên bản HotSpot test có G1:**

```text
detectedFamily=G1
expectedMatches=true
gcBeansFound=true
heapMaximumPositive=true
```

**Thử ZGC nếu binary hỗ trợ:**

```bash
java -Xms64m -Xmx256m -XX:+UseZGC CollectorCapabilityDemo ZGC
```

**Stdout trên OpenJDK 24 được thử nghiệm:**

```text
detectedFamily=ZGC
expectedMatches=true
gcBeansFound=true
heapMaximumPositive=true
```

**Thử Shenandoah nếu binary hỗ trợ:**

```bash
java -Xms64m -Xmx256m -XX:+UseShenandoahGC CollectorCapabilityDemo Shenandoah
```

**Stdout trên OpenJDK 24 có tích hợp Shenandoah:**

```text
detectedFamily=Shenandoah
expectedMatches=true
gcBeansFound=true
heapMaximumPositive=true
```

**Đã thử thực tế:** `javac --release 11` biên dịch thành công chính ví dụ này trên OpenJDK 24; chạy riêng từng cờ G1, ZGC, Shenandoah đều trả đúng bốn dòng nêu trên. Đây là **minh chứng của bản OpenJDK 24 đang thử**, không phải bảo đảm binary JDK 11/JDK 25 của bạn hỗ trợ đủ ba lựa chọn.

### Giới hạn của ví dụ

- Tên MXBeans có thể thay đổi theo vendor/JDK; logic `detectFamily` là **heuristic**, trả `Unknown` khi không nhận ra. `Unknown` **không có nghĩa VM không làm GC**.
- `detectedFamily=ZGC` **không phân biệt** ZGC generational/non-generational tại những version hỗ trợ cả hai; cần kiểm tra **JDK version, flags và logs**.
- `detectedFamily=Shenandoah` cũng không tự nói `satb` hay `generational`; phải kiểm tra `ShenandoahGCMode` có hiệu lực.
- `expectedMatches=true` không chứng minh p99 pause thấp hơn G1 hoặc throughput tốt; mới chỉ đối chiếu **collector đang chạy**.
- `heapMaximumPositive=true` không xác minh RAM container đủ cho heap + metaspace + thread stacks + direct buffers + native memory, và không phải phép đo RSS.

## 9. Cấu hình G1 theo tài liệu đúng version

G1 là baseline thường phù hợp để bắt đầu, với default ergonomics và heap bound hợp lý. Một cấu hình **minh họa** trên shell Unix:

```bash
java -Xms256m -Xmx1g -XX:+UseG1GC \
     -XX:MaxGCPauseMillis=100 \
     -Xlog:gc*,safepoint:file=gc-g1.log:time,uptime,level,tags:filecount=5,filesize=10m \
     -jar service.jar
```

`service.jar` là tên ứng dụng giả định, không phải file được bài tạo. Trên Windows PowerShell, dùng một dòng hoặc cú pháp xuống dòng riêng, không dùng `\` kiểu Bash.

**`-XX:MaxGCPauseMillis=100` là mục tiêu mềm, không phải deadline cứng cho mọi GC pause**. Hạ số này quá thấp có thể khiến GC chạy thường xuyên, tăng overhead và vẫn không đạt mục tiêu. Trong nhiều trường hợp G1 nên được thử **với default settings trước**, sau đó dùng số liệu để điều chỉnh.

Đặc biệt, tránh **cố định young-generation size** bằng `-Xmn` hoặc flags tỷ lệ khi không cần thiết. G1 tự điều chỉnh young generation để cân bằng pause-time target, việc ép size có thể ngăn cơ chế này hoạt động tốt.

### Không đánh giá chỉ theo average pause

G1 có thể có pause p50 đẹp nhưng p99.9 xấu trong traffic burst hoặc nhiều humongous objects. Dùng GC logs cùng application traces để hiểu **tail** và nguyên nhân. Nếu G1 vẫn đáp ứng SLO ở các tải quan trọng, đổi sang ZGC chỉ vì tên collector “low latency” chưa chắc có lợi.

## 10. Cấu hình ZGC theo JDK 11, 21 và 24+

**JDK 11 (historical experimental capability check):**

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseZGC \
     -Xms512m -Xmx2g -jar service.jar
```

Chỉ dùng nếu binary JDK 11 thực sự hỗ trợ và đã hiểu trạng thái experimental cùng chính sách vendor. Không coi đây là khuyến nghị production mới: ZGC đã có production status ở các JDK sau (JEP 377), và các JDK hiện đại có mode khác.

**JDK 21 Generational ZGC opt-in:**

```bash
java -Xms512m -Xmx2g \
     -XX:+UseZGC -XX:+ZGenerational \
     -Xlog:gc*:file=gc-zgc.log:time,uptime,level,tags:filecount=5,filesize=10m \
     -jar service.jar
```

**JDK 24+ Generational ZGC:** 

```bash
java -Xms512m -Xmx2g -XX:+UseZGC \
     -Xlog:gc*:file=gc-zgc.log:time,uptime,level,tags:filecount=5,filesize=10m \
     -jar service.jar
```

`ZGenerational` không còn là cờ cần thiết trên JDK 24+; mode không-generational đã bị loại. Nếu script upgrade từ JDK 21 còn cờ cũ, bỏ/kiểm tra warnings và so sánh GC logs sau nâng cấp.

**Tuning ZGC không giống G1.** Cần đánh giá heap headroom, concurrent CPU, allocation stalls, native/RSS và giới hạn container. Không mang mọi tham số `MaxGCPauseMillis`/young-gen của G1 sang ZGC chỉ vì muốn giảm pause.

## 11. Cấu hình Shenandoah: đầu tiên phải chắc binary có collector

Một binary HotSpot có Shenandoah có thể dùng:

```bash
java -Xms512m -Xmx2g -XX:+UseShenandoahGC \
     -Xlog:gc*:file=gc-shenandoah.log:time,uptime,level,tags:filecount=5,filesize=10m \
     -jar service.jar
```

**Generational Shenandoah trên JDK 25+ nếu binary đã cung cấp:**

```bash
java -Xms512m -Xmx2g -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -jar service.jar
```

Chỉ đưa `-XX:ShenandoahGCMode=generational` khi vendor docs của đúng JDK xác nhận hỗ trợ. JDK 24 mode này là **experimental** theo JEP 404, còn JDK 25 chuyển thành **product** theo JEP 521; thay đổi trạng thái không có nghĩa **mặc định** chuyển sang generational. Với JDK 11u, ngay cả sự tồn tại của Shenandoah cũng phụ thuộc build-time opt-in/vendor.

Ví dụ nếu Oracle JDK 25 hoặc một runtime đóng gói không có `UseShenandoahGC`, thêm `-XX:+UnlockExperimentalVMOptions` **không cài đặt GC mới vào VM**. Chọn distro được hỗ trợ, hoặc sử dụng G1/ZGC đã có và benchmark; không tự sửa production JDK vendor thiếu quy trình security/support.

## 12. Đọc GC logs và phân biệt pause-time với end-to-end latency

Java 11 có **Unified JVM Logging** từ Java 9. Có thể cấu hình:

```bash
java -Xms256m -Xmx1g -XX:+UseG1GC \
     -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags:filecount=5,filesize=10m \
     -jar service.jar
```

Các dòng dưới đây chỉ là **sơ đồ cách log mô tả events**, không phải stdout đã đo hay format bất biến:

```text
[...][info][gc] Using G1
[...][info][gc] GC(...) Pause Young (...) ...ms
[...][info][safepoint] Safepoint "...", ...ms
```

GC logs của ZGC/Shenandoah có thể thể hiện concurrent cycles, pause phases, allocation stalls hoặc fallbacks khác G1. **Đừng dùng regex parser của G1 để đọc mọi collector**; chọn logging tags, metrics và parser theo version.

Phân biệt bốn thước đo:

1. **GC pause**: thời gian dừng ứng dụng do một pha GC.
2. **Safepoint latency**: thời gian đưa threads tới safepoint và thực hiện một operation; không phải mọi safepoint đều xuất phát từ GC.
3. **Application request latency**: toàn bộ đường đi request, gồm locks, queues, network, database, scheduler, OS và GC.
4. **GC concurrent CPU**: phần tài nguyên collector dùng dù pause ngắn; có thể cạnh tranh với application threads khi CPU bị quota.

Một collector có pause p99 = 1 ms không có nghĩa HTTP p99.9 ≤10 ms. Nếu request latency vẫn cao, kiểm tra **CPU throttling, locks, thread scheduling, I/O, queue depth và downstream services** trước khi quy lỗi cho GC.

## 13. Thiết kế benchmark đủ công bằng để quyết định GC

Các số liệu nên thu cùng nhau:

| Chỉ số | Vì sao quan trọng |
| --- | --- |
| GC pause p50/p95/**p99/p99.9**, max | Không giấu tail bằng trung bình |
| HTTP/queue latency p95/**p99/p99.9** | Quan sát tác động thực lên service |
| Throughput, successful requests/second | Chống việc giảm pause bằng cách hy sinh công suất |
| CPU user/system, GC CPU | Concurrent collector có thể cần CPU nhiều |
| `-Xms/-Xmx`, live set, RSS, native memory | Kiểm soát footprint và container OOM |
| Allocation rate và object lifetime | Collector phù hợp workload ngắn/dài |
| GC cycle frequency, stalls, fallback/full GC | Phát hiện kịch bản thất bại khi chịu áp lực |
| OS/arch, CPU/memory quota, kernel/cgroup | Tính tái lập và tính khả dụng |
| JDK exact build, flags, image digest | Ngăn so sánh các version khác nhau |
| Warm-up, thử tải nhiều lượt | Tránh kết luận từ một spike/tải chưa ổn định |

**Ví dụ SLO giả định** (không phải giá trị chuẩn của JDK):

```text
Request p99.9 latency <= 80 ms tại 10,000 req/s
GC stop-the-world pause p99 <= 10 ms
CPU <= 4 vCPU; container memory <= 4 GiB
Không có OOM, allocation stalls nghiêm trọng hoặc throughput giảm quá mức
```

Đây là một ví dụ đặt điều kiện đo, **không** phải lời bảo đảm G1/ZGC/Shenandoah đáp ứng những số này. Chỉ đưa ra quyết định khi có kết quả trên **workload của ứng dụng** và các tiêu chí chấp nhận đã rõ.

Để công bằng, cố định hoặc ghi nhận **application version, traffic pattern, peak concurrency, heap bounds, CPU quota, memory limit, JDK patch, OS, warm-up**. Nếu để ZGC có heap 8 GiB còn G1 2 GiB, có thể đó là trade-off có chủ ý, nhưng không nói kết quả chứng minh “thuật toán nhanh hơn” khi tài nguyên khác nhau.

## 14. Compatibility gate trong CI và trước rollout

Checklist có thể tích hợp vào pipeline triển khai:

```text
[ ] Ghi java -version và path java binary của service
[ ] Xác minh vendor, build, OS/architecture, image digest, CPU/RAM limit
[ ] Đọc GC Tuning Guide đúng major version, vendor release notes
[ ] Kiểm tra collectors/flags cần thiết đã được binary hỗ trợ
[ ] Thử startup với G1, ZGC, Shenandoah (từng process riêng)
[ ] Kiểm tra exit code, stderr, obsolete/ignored flags
[ ] Chạy app với flags thật; xác nhận active collector/mode qua log/MXBean
[ ] Chạy load tests: p99/p99.9 GC pauses và request latency
[ ] Đo throughput, GC CPU, RSS, allocation stalls/OOM dưới burst
[ ] Triển khai canary, so sánh với baseline và chuẩn bị rollback
```

**Báo cáo nên tách ba kết luận:** `AVAILABLE` (binary chấp nhận collector), `ACTIVE` (đang chạy), `MEETS_SLO` (đã đo đạt). Không gộp cả ba vào một chữ “supported”.

**Không chấp nhận failure im lặng:** Nếu flag bị ignore hoặc cảnh báo obsolete, phải xử lý; không thêm `IgnoreUnrecognizedVMOptions` để làm xanh CI. Khi JDK upgrade, lỗi ở compatibility gate là tín hiệu cần cập nhật launch scripts và tài liệu.

Một số built-in flags được ghi với tên/giá trị khác nhau qua JDK; `java -XX:+PrintFlagsFinal -version` giúp kiểm tra các flags mà HotSpot cung cấp, nhưng chỉ xuất hiện trong danh sách **chưa đủ** để khẳng định collector có thể chạy và ổn định trên nền tảng đó. Hãy thử khởi động thực và xem active collector.

## 15. Ba ví dụ migration cụ thể

### 15.1. Từ JDK 11 lên JDK 17

Ứng dụng JDK 11 dùng G1 có thể tiếp tục thử baseline G1 ở JDK 17. ZGC đã được nâng lên production feature từ JDK 15, nên **đánh giá bằng tài liệu JDK 17** chứ không giữ kết luận “experimental” của JDK 11. Shenandoah vẫn phải xác minh vendor/build.

### 15.2. Từ JDK 17 lên JDK 21

JDK 21 có **Generational ZGC** opt-in. So sánh ZGC mode cũ với mode mới dưới workload đại diện; không lấy kết quả ZGC JDK 17 rồi gọi đó là “generational” theo tài liệu JDK 21.

### 15.3. Từ JDK 21 lên JDK 25 hoặc 27

JDK 23 đã chuyển ZGC generational sang mặc định, JDK 24 loại non-generational. Một service giữ `-XX:+UseZGC` từ trước có thể đổi hành vi sau nâng major JDK **dù không đổi flag**. Cần xóa `-XX:+ZGenerational` obsolete và đo lại.

Generational Shenandoah là một đường thay đổi **riêng**: JDK 24 experimental, JDK 25 product, **không phải mặc định trên mọi build**. Đừng suy từ “JDK 25” thành “Shenandoah Generational đang chạy”.

## 16. Tình huống xử lý khi Shenandoah được mô tả trong JEP nhưng JVM từ chối

Một nhóm muốn bật Generational Shenandoah:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -version
```

Nhưng VM báo “Unrecognized VM option” hoặc “JVM not configured to use Shenandoah”.

**Cách điều tra:**

1. Xác nhận **đúng binary** qua `java -version` và đường dẫn thực.
2. Kiểm tra runtime production/container không dùng một Java khác shell/IDE/build tool.
3. Kiểm tra vendor support matrix: có thể phiên bản đã tích hợp JEP nhưng binary vendor không ship Shenandoah.
4. Thử `java -XX:+UseShenandoahGC -version` **không có mode** để tách lỗi thiếu collector khỏi lỗi mode không hỗ trợ.
5. Kiểm tra cờ `ShenandoahGCMode=generational` và experimental requirements của phiên bản.
6. Nếu collector không có, dùng một binary vendor được hỗ trợ **hoặc** quay về G1/ZGC trên JDK đã được phê duyệt, rồi đo lại benchmark.

**Không sửa bằng** `-XX:+IgnoreUnrecognizedVMOptions` hoặc thêm `UnlockExperimentalVMOptions` một cách mù quáng. Nếu collector không được build vào binary, không có flag nào có thể tạo ra mã GC đã bị loại tại build time.

Tương tự, trên JDK 11 nếu ZGC chỉ chạy sau khi unlock experimental, điều đó không chứng minh sẵn sàng production. Trên JDK 24+, nếu ZGenerational cũ bị ignore, hãy bỏ cờ và kiểm tra lại mode theo tài liệu hiện hành.

## 17. Sai lầm phổ biến khi đối chiếu GC

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Đọc GC guide JDK 25 để cấu hình JDK 11 | Flags/modes có thể chưa tồn tại | Đọc đúng major/update/vendor |
| Chỉ biết Java target của Maven/Gradle | Runtime process có thể chạy binary khác | Kiểm tra JDK trong container/process |
| JEP đã “delivered” nghĩa mọi vendor binary đều có | Build-time/OS/arch khác nhau | Probe đúng binary |
| Nghĩ G1 luôn được chọn trên mọi máy | Ergonomics có thể chọn Serial/khác | Xem logs, VM flags và MXBean |
| Nghĩ mọi Oracle JDK đều có Shenandoah | Availability khác theo vendor | Vendor matrix + startup probe |
| Dùng `UseZGC` Java 11 và cho là production-ready | JDK 11 ZGC experimental | Phân biệt lịch sử và bản đang deploy |
| Giữ `ZGenerational` JDK 21 trên JDK 24+ | Flag obsolete, mode mới mặc định | Bỏ cờ, xác minh behavior |
| Nghĩ Shenandoah generational mặc định trên JDK 25 | Mode cần chọn, build phải hỗ trợ | Xem `ShenandoahGCMode` và flags |
| Dùng `IgnoreUnrecognizedVMOptions` trong smoke test | Có thể “thành công giả” | Fail fast với flag invalid |
| Coi G1 `MaxGCPauseMillis` là SLA cứng | Chỉ là mục tiêu mềm | Đo pause thật |
| Coi MXBean là danh sách GC có thể bật | MXBean cho GC đang chạy | Dùng startup probe để biết availability |
| Nghĩ ZGC không cần CPU vì concurrent | Concurrent GC cần tài nguyên | Đo headroom, stalls và throughput |
| So sánh G1/ZGC với heap/CPU khác nhau mà không báo | Benchmark khó so sánh | Kiểm soát điều kiện, ghi mọi khác biệt |
| Chỉ dùng pause average | Che mất tail | Đo p99, p99.9, max |
| GC pause thấp nhưng request p99 vẫn cao, liền đổi GC | Vấn đề có thể do I/O, locks, CPU | Điều tra request path |
| Copy `UseConcMarkSweepGC` từ hướng dẫn cũ | CMS removed JDK 14 | Không dùng cho cấu hình mới |

## 18. Câu hỏi tự kiểm tra

**Câu 1:** JDK của một vendor chứa mã nguồn Shenandoah. Có thể khẳng định `-XX:+UseShenandoahGC` chạy được không?

**Đáp án:** Không. Cần xem feature có được build và ship trong binary/architecture cụ thể hay không, sau đó probe và xác nhận active collector.

**Câu 2:** Chạy `java -XX:+UseZGC -version` exit 0 có chứng minh SLO request p99.9 không?

**Đáp án:** Không. Đó chỉ là startup probe; phải chạy tải thực, đo latency, throughput, CPU, RSS và failures.

**Câu 3:** Vì sao `ZGenerational` có ích ở JDK 21 nhưng không cần trên JDK 25?

**Đáp án:** JDK 21 cho phép opt-in generational, JDK 23 đặt generational làm mặc định và JDK 24 loại non-generational mode. Cờ cũ không còn có vai trò chọn mode trên JDK 25.

**Câu 4:** Tại sao đặt `-XX:MaxGCPauseMillis=100` không bảo đảm mọi lần GC G1 dừng dưới 100 ms?

**Đáp án:** Đây là pause-time goal mềm; GC phải đánh đổi với heap, throughput và tình trạng workload.

**Câu 5:** `GarbageCollectorMXBean` của một JVM ZGC có cho biết G1/Shenandoah có được build vào đó không?

**Đáp án:** Không. Nó hiển thị các bean của collector đang hoạt động; availability của collector khác cần probe/đối chiếu docs.

**Câu 6:** Generational Shenandoah JDK 24 và JDK 25 khác gì?

**Đáp án:** JDK 24 experimental (JEP 404), JDK 25 product feature (JEP 521), nhưng chỉ dùng được khi vendor binary hỗ trợ.

**Câu 7:** Nếu GC pause p99 là 1 ms mà request p99.9 là 300 ms, có nên kết luận GC gây chậm?

**Đáp án:** Không. Kiểm tra locks, queueing, CPU throttling, downstream I/O, safepoints và các nguồn latency khác.

**Câu 8:** Đổi từ Java 21 lên Java 25 mà launch flags giữ nguyên có đồng nghĩa collector behavior giữ nguyên không?

**Đáp án:** Không. Defaults/modes có thể đổi dù flag giống nhau, như ZGC generational.

**Câu 9:** Vì sao phải dùng cùng workload, heap bound và CPU quota trong benchmark?

**Đáp án:** Nếu tài nguyên/tải khác nhau, không phân biệt được lợi ích của thuật toán GC với lợi ích do cấp thêm tài nguyên.

**Câu 10:** Khi G1 đã đạt SLO và chi phí hợp lý, có cần chuyển sang collector khác không?

**Đáp án:** Không nhất thiết. Giữ baseline ổn định, chỉ thử collector khác nếu có mục tiêu cải thiện cụ thể và benchmark chứng minh trade-off có lợi.

**Ghi nhớ:** Hãy đối chiếu **đúng JDK/vendor/build/OS/CPU/container** trước khi bật low-pause GC. **G1** là baseline phổ biến; **ZGC** từ experimental Java 11 đến production JDK 15 và generational-only JDK 24+; **Shenandoah** phụ thuộc binary vendor, Generational Shenandoah product từ JDK 25. Xác minh khả năng bằng **startup probe**, collector thực bằng **GC log/MXBeans/VM flags**, hiệu quả bằng **p99/p99.9 latency, throughput, CPU và RSS**. Không suy từ JEP sang binary và không nhầm flag được nhận với một SLO đã được chứng minh.

**Tài liệu chính thức / nguồn còn áp dụng:** [Oracle JDK 11 — Available Collectors](https://docs.oracle.com/en/java/javase/11/gctuning/available-collectors1.html); [Oracle JDK 25 — GC Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html); [Oracle JDK 27 — Available Collectors](https://docs.oracle.com/en/java/javase/27/gctuning/available-collectors.html); [Oracle JDK 25 — Java Command Options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html); [OpenJDK JEP 333 — ZGC Experimental](https://openjdk.org/jeps/333); [JEP 377 — ZGC Production](https://openjdk.org/jeps/377); [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439); [JEP 474 — ZGC Generational Default](https://openjdk.org/jeps/474); [JEP 490 — Remove Non-Generational ZGC](https://openjdk.org/jeps/490); [JEP 189 — Shenandoah](https://openjdk.org/jeps/189); [JEP 404 — Generational Shenandoah Experimental](https://openjdk.org/jeps/404); [JEP 521 — Generational Shenandoah Product](https://openjdk.org/jeps/521); [OpenJDK Shenandoah Project](https://wiki.openjdk.org/display/shenandoah/Main).
