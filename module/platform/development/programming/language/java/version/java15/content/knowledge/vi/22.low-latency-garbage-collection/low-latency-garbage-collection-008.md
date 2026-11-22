# Đối chiếu tính năng với bản phân phối JDK triển khai — GC độ trễ thấp (Java 15+)

## 1. Tại sao phải đối chiếu bản phân phối JDK?

Trong nhóm **GC độ trễ thấp**, Java 15 đánh dấu việc **ZGC** và **Shenandoah** trở thành các tính năng production của OpenJDK (JEP 377 và JEP 379). Tuy nhiên, một tính năng đã xuất hiện trong OpenJDK **không đồng nghĩa mọi JDK binary đều đóng gói, bật hoặc hỗ trợ nó trên mọi nền tảng**.

Khi vận hành ứng dụng, câu hỏi đúng là:

> Runtime thực tế của service (nhà phát hành, JVM, phiên bản build, hệ điều hành và kiến trúc) có collector/chế độ GC cần dùng không, có được nhà cung cấp hỗ trợ không, và có đáp ứng SLO với workload thật không?

Ví dụ, máy phát triển có thể chạy Azul Zulu, CI dùng Eclipse Temurin, còn container production dùng runtime khác. Dù cùng phiên bản Java SE, tên VM flags, các collector khả dụng và chính sách hỗ trợ có thể khác, đặc biệt với JVM **không phải HotSpot** như OpenJ9.

Bài này hướng dẫn đối chiếu theo **bằng chứng từ chính runtime** thay vì đoán từ tên Java hoặc benchmark trên một máy không liên quan. Chỉ sử dụng API, flag và GC mode còn áp dụng trong JDK hiện đại; không hướng dẫn dùng cấu hình GC legacy đã bị loại bỏ.

## 2. Những dữ liệu phải ghi trước khi so sánh GC

| Thuộc tính | Cần kiểm tra | Tác dụng |
| --- | --- | --- |
| Java major/update/build | `java.version`, `java.runtime.version`, `java.vm.version` | Xác định chính xác phiên bản runtime |
| Distribution/vendor | `java.vendor`, package hoặc Docker image | Biết nhà cung cấp và chính sách hỗ trợ |
| JVM implementation | `java.vm.name`, `java.vm.vendor` | Phân biệt HotSpot với OpenJ9/VM khác |
| Hệ điều hành/CPU | `os.name`, `os.arch` | Feature có thể phụ thuộc nền tảng |
| Runtime path | Binary `java` thực sự khởi động service | Tránh nhầm JDK máy dev với production |
| Image identity | Container image digest/base image | Đảm bảo benchmark đúng artifact |
| GC flag | Các tham số `-XX`, `-Xms`, `-Xmx` | Xác nhận GC được cấu hình thế nào |
| Vendor support | Release notes, support matrix, lifecycle | Biết tính năng có được hỗ trợ vận hành |
| Kết quả đo | p99/p99.9 latency, GC pause, CPU, RSS, throughput | Quyết định collector có hiệu quả không |

Hai mức kết luận phải **tách riêng**:

- **Available:** runtime nhận flag và khởi động với collector đó.
- **Supported:** vendor xác nhận hỗ trợ collector/chế độ/nền tảng ở build tương ứng.

Và phải có mức thứ ba: **Meets SLO**, nghĩa là hệ thống đã được đo trên workload thực. Một GC có mặt trong binary chưa chắc được hỗ trợ thương mại hoặc đạt yêu cầu vận hành.

## 3. Các collector cần biết khi đánh giá latency

| Collector | Vai trò | Flag trên HotSpot hiện đại | Cần chú ý |
| --- | --- | --- | --- |
| **G1** | Cân bằng hiệu suất và pause; baseline quan trọng | `-XX:+UseG1GC` | Thường mặc định trên HotSpot Server VM |
| **ZGC** | Collector đồng thời, ưu tiên giảm thời gian tạm dừng | `-XX:+UseZGC` | Kiểm tra GC worker CPU, memory headroom, allocation stalls |
| **Shenandoah** | Collector đồng thời, ưu tiên pause thấp | `-XX:+UseShenandoahGC` | Không được suy ra mọi bản JDK có đóng gói Shenandoah |
| **Generational Shenandoah** | Shenandoah quản lý object theo thế hệ | `-XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational` | Tính năng production từ JDK 25, nếu build hỗ trợ |
| **Parallel GC** | Hướng throughput | `-XX:+UseParallelGC` | Cần đo nếu latency SLO rất nghiêm ngặt |
| **Serial GC** | Đơn giản, có thể phù hợp heap nhỏ | `-XX:+UseSerialGC` | Không phải mặc định ưu tiên cho service tải lớn, tail latency thấp |

**Đừng đổi GC chỉ vì nghe “low latency”.** Nếu G1 đáp ứng p99, CPU/memory hiệu quả hơn thì có thể giữ G1. ZGC/Shenandoah thường hữu ích khi GC pause gây ảnh hưởng rõ tới tail latency, nhưng vẫn có chi phí concurrency và memory khác. Cần benchmark mới biết lựa chọn đúng.

### 3.1. Lộ trình ZGC và Shenandoah ảnh hưởng đến cấu hình

| Mốc phát hành | Thay đổi | Hành động thực tế |
| --- | --- | --- |
| Java 15 — JEP 377 | ZGC thành production | Có thể cân nhắc trên binary có hỗ trợ |
| Java 15 — JEP 379 | Shenandoah thành production trong OpenJDK | Vẫn phải kiểm tra distribution và platform |
| Java 21 — JEP 439 | Generational ZGC được giới thiệu | Cơ sở của ZGC hiện đại |
| Java 23 — JEP 474 | Generational ZGC trở thành mặc định | Không giả định ZGC là collector non-generational |
| **Java 24 — JEP 490** | **Chế độ non-generational ZGC bị loại bỏ** | Không dùng flag cũ để bật lại mode đã gỡ |
| Java 25 — JEP 521 | Generational Shenandoah thành production | Có thể chọn mode tường minh nếu runtime hỗ trợ |

**Trong HotSpot JDK 24 trở lên, ZGC dùng generational mode và non-generational mode không còn tồn tại.** Cấu hình phù hợp là `-XX:+UseZGC` khi binary có ZGC. Không chép flag liên quan non-generational ZGC từ tài liệu cũ rồi hy vọng JDK hiện đại sẽ nhận.

Với Shenandoah, các tài liệu JDK 27 vẫn mô tả `ShenandoahGCMode` mặc định là `satb` (single-generation). Nếu cần generational Shenandoah, phải cấu hình mode **`generational`** trên runtime JDK 25+ có feature, chứ không cho rằng nâng JDK tự bật mode đó.

## 4. Quy trình kiểm tra từng bước

### Bước 1 — xác định đúng runtime của service

Chạy trong container hoặc máy chủ dùng để khởi động ứng dụng:

```bash
java -version
java -XshowSettings:properties -version
```

Ghi lại `java.home`, `java.vendor`, `java.version`, `java.vm.name`, `java.vm.version`, `os.name`, `os.arch`. Với Kubernetes/Docker, ghi image digest; với systemd/process manager, kiểm tra entrypoint và `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`.

**Máy host không nhất thiết dùng cùng JDK với container.** Không dùng kết quả `java -version` trên laptop để chứng minh JDK trong production có Shenandoah.

### Bước 2 — tra đúng vendor và build

Đối chiếu tài liệu GC của major JDK với **release notes của vendor/build cụ thể**, support status theo OS/architecture, chu kỳ patch/security update và giới hạn container.

Một bản phân phối dùng OpenJDK/HotSpot có thể lược bỏ collector ở thời điểm build hoặc không hỗ trợ collector trên một platform. Một vendor có thể backport hoặc tùy chỉnh feature. Vì vậy, **tài liệu upstream chỉ chứng minh tính năng được thiết kế**, không xác nhận nội dung của mọi binary.

Nếu `java.vm.name` cho thấy JVM không phải HotSpot, dừng việc sao chép flag `-XX:+UseZGC`/`-XX:+UseShenandoahGC` và chuyển sang tài liệu GC tương ứng của VM đó.

### Bước 3 — smoke test collector trên đúng JVM

Với **HotSpot** có khả năng hỗ trợ các GC này, thử ba process riêng:

```bash
java -XX:+UseG1GC -Xlog:gc=info -version
java -XX:+UseZGC -Xlog:gc=info -version
java -XX:+UseShenandoahGC -Xlog:gc=info -version
```

Kết quả phải gồm:

1. **Exit code** bằng 0; không lỗi `Unrecognized VM option` hoặc `Could not create the Java Virtual Machine`.
2. **Startup GC log** xác nhận `Using G1`, `Using The Z Garbage Collector`, hoặc `Using Shenandoah`.
3. Runtime/build và điều kiện chạy được ghi lại.

Nếu flag bị từ chối, đánh dấu **UNAVAILABLE** trong ma trận cho artifact đang thử. **Không được âm thầm xóa flag rồi tuyên bố collector đã được bật.** Nếu cần thử startup với heap rõ ràng:

```bash
java -XX:+UseZGC -Xms256m -Xmx256m -Xlog:gc=info -version
```

`256m` chỉ phục vụ smoke test, không phải khuyến nghị heap production. Startup thành công với `-version` chưa chứng minh tốc độ thu gom hoặc latency trong ứng dụng thật.

### Bước 4 — nếu cần generational Shenandoah

Trên HotSpot **JDK 25+** có Shenandoah generational:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xms256m -Xmx256m -Xlog:gc=info -version
```

Kiểm tra process khởi động, log và tài liệu hỗ trợ của vendor. Trên một binary không hỗ trợ, phải báo không khả dụng. **Không dùng tùy chọn mở khóa experimental để lách qua thiếu hỗ trợ production.**

### Bước 5 — xác nhận GC trong ứng dụng đang chạy

Có thể xem GC log của chính service hoặc dùng `jcmd` khi hệ thống cho phép attach:

```text
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

Đổi `<PID>` thành process ID thực. Công cụ attach có yêu cầu về quyền và namespace; trong container hạn chế attach, cần dựa vào startup log, application metrics hoặc khả năng quan sát đã triển khai, **không tùy tiện nới quyền bảo mật**.

Bên trong Java, `ManagementFactory.getGarbageCollectorMXBeans()` trả danh sách các management bean của collector. Dùng nó để đối chiếu runtime, nhưng không hardcode tên bean làm quy tắc portable: một collector có thể có nhiều bean, và tên của chúng tùy JDK/JVM.

## 5. Chương trình Java 17+ kiểm tra distribution và GC đang hoạt động

Chương trình sau sử dụng API Java chuẩn để in phiên bản, vendor, implementation, GC beans và những tham số được truyền vào JVM.

Tạo file **`GcDistributionProbe.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.util.List;
import java.util.stream.Collectors;

public class GcDistributionProbe {
    public static void main(String[] args) {
        RuntimeMXBean rt = ManagementFactory.getRuntimeMXBean();
        System.out.println("javaVersion=" + Runtime.version().feature());
        System.out.println("javaVendor=" + System.getProperty("java.vendor"));
        System.out.println("vmName=" + System.getProperty("java.vm.name"));
        System.out.println("vmVersion=" + System.getProperty("java.vm.version"));
        List<String> names = ManagementFactory.getGarbageCollectorMXBeans().stream()
                .map(GarbageCollectorMXBean::getName)
                .sorted()
                .collect(Collectors.toList());
        System.out.println("gcBeans=" + String.join(", ", names));
        System.out.println("jvmArgs=" + rt.getInputArguments());
    }
}
```

Biên dịch với JDK 17 trở lên:

```bash
javac --release 17 GcDistributionProbe.java
```

Chạy từng phép kiểm tra thành một process riêng:

```bash
java -cp . GcDistributionProbe
java -XX:+UseG1GC -cp . GcDistributionProbe
java -XX:+UseZGC -cp . GcDistributionProbe
java -XX:+UseShenandoahGC -cp . GcDistributionProbe
```

**Đây không phải phép đổi GC động:** collector được chọn lúc JVM khởi động. Nếu muốn so sánh hai GC, cần khởi động hai process khác nhau và đo dưới điều kiện giống nhau.

### 5.1. Output đã xác minh trên một Azul Zulu JDK 24 cụ thể

Chương trình đã được biên dịch bằng `javac --release 17` và chạy trên **Azul Zulu JDK 24.0.2+12** với VM `OpenJDK 64-Bit Server VM`. Đây là output quan sát thực tế của binary đó, **không phải giá trị cố định trên mọi JDK**.

**Mặc định:**

```text
javaVersion=24
javaVendor=Azul Systems, Inc.
vmName=OpenJDK 64-Bit Server VM
vmVersion=24.0.2+12
gcBeans=G1 Concurrent GC, G1 Old Generation, G1 Young Generation
jvmArgs=[]
```

**Chọn ZGC:**

```text
javaVersion=24
javaVendor=Azul Systems, Inc.
vmName=OpenJDK 64-Bit Server VM
vmVersion=24.0.2+12
gcBeans=ZGC Major Cycles, ZGC Major Pauses, ZGC Minor Cycles, ZGC Minor Pauses
jvmArgs=[-XX:+UseZGC]
```

**Chọn Shenandoah:**

```text
javaVersion=24
javaVendor=Azul Systems, Inc.
vmName=OpenJDK 64-Bit Server VM
vmVersion=24.0.2+12
gcBeans=Shenandoah Cycles, Shenandoah Pauses
jvmArgs=[-XX:+UseShenandoahGC]
```

**Chọn G1 tường minh:**

```text
javaVersion=24
javaVendor=Azul Systems, Inc.
vmName=OpenJDK 64-Bit Server VM
vmVersion=24.0.2+12
gcBeans=G1 Concurrent GC, G1 Old Generation, G1 Young Generation
jvmArgs=[-XX:+UseG1GC]
```

**Đọc kết quả:** Trên **artifact đã kiểm chứng này**, cả G1, ZGC và Shenandoah đều hoạt động; điều đó không chứng minh mọi bản Zulu, mọi hệ điều hành hoặc mọi JDK khác đều có đầy đủ các GC. Tên GC beans thay đổi theo collector và implementation, thậm chí một collector có thể tạo nhiều beans. Trong CI hãy lưu output thực tế, không so sánh toàn bộ text này như một chuẩn bất biến.

`GcDistributionProbe` là **công cụ kiểm tra runtime identity**, không phải benchmark. Nó không tạo lượng allocation lớn và không đo phân phối pause, nên chưa thể kết luận hiệu năng của bất kỳ GC nào.

## 6. Cách lập ma trận đối chiếu distribution × collector

Không nên lập bảng tĩnh như “nhà cung cấp A luôn có Shenandoah, nhà cung cấp B luôn không có”, vì nội dung build và chính sách hỗ trợ có thể thay đổi. Dùng bảng **điền bằng kết quả kiểm chứng**:

| Trường | Ví dụ cách ghi |
| --- | --- |
| Service/environment | `orders-api / staging` |
| Distribution/JVM | `java.vendor` + `java.vm.name` thực |
| JDK/build | `24.0.2+12` hoặc bản sản xuất hiện tại |
| OS/CPU/container | `Linux/AArch64`, image digest, cgroup limits |
| GC được thử | G1 / ZGC / Shenandoah / Generational Shenandoah |
| VM flags | Nguyên văn `-XX` flags |
| Startup outcome | `PASS` hoặc `FAIL`, exit code |
| GC evidence | Dòng `Using ...` trong log và GC beans |
| Vendor support | Release notes và chính sách hỗ trợ tương ứng |
| Benchmark | p99/p99.9, throughput, CPU, RSS, GC pause/stall |
| Kết luận | `ACCEPT`, `REJECT` hoặc `NEED_MORE_TESTS` |

Ma trận phải gắn với **artifact bất biến**: image digest, JDK build/update, OS/architecture. Nâng base image, chuyển vendor hoặc đổi kiến trúc CPU có thể làm thay đổi tính khả dụng và đặc tính collector; khi đó cần chạy lại smoke test và benchmark.

Một startup **PASS** nhưng p99 request vượt SLO vẫn là kết quả **không chấp nhận triển khai**. Ngược lại, một GC được vendor hỗ trợ nhưng binary image đang thiếu collector cũng phải coi là **không khả dụng cho artifact đó**.

## 7. Benchmark latency đúng cách

Giữ một cấu hình **G1 baseline** rồi so ZGC/Shenandoah với **cùng ứng dụng, cùng tải và cùng resource budget**.

Những phép đo quan trọng:

| Nhóm | Giá trị cần xem |
| --- | --- |
| Độ trễ ứng dụng | p95, p99, p99.9 request latency và error rate |
| GC pauses | Pause count, max pause, phân phối pause, safepoint durations |
| Throughput | Requests/second hoặc operations/second |
| CPU | Application CPU và concurrent GC threads |
| Memory | Heap used/committed, native memory, process RSS |
| Cấp phát | Allocation rate, allocation stalls, tỷ lệ object sống lâu |
| Khả năng hồi phục | Peak load, startup/warmup, GC pressure, OOMKilled |

**Vì sao không chỉ đo GC pause?** ZGC/Shenandoah có thể giảm thời gian stop-the-world nhưng tiêu tốn CPU đồng thời, memory headroom hoặc làm ứng dụng gặp allocation stalls trong một số điều kiện. Một số dịch vụ đạt p99 tốt hơn với G1 do throughput/CPU phù hợp hơn.

**Vì sao không cho `-Xmx` bằng toàn bộ container RAM?** JVM còn native memory, metaspace, direct buffers, thread stacks, code cache và overhead của collector. Cần giữ headroom và quan sát RSS để tránh container OOMKill dù GC pause thấp.

### 7.1. GC log và JFR còn được hỗ trợ

Trên HotSpot, ví dụ bật unified GC logging:

```bash
java -XX:+UseZGC -Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags -jar app.jar
```

Để thu Java Flight Recorder trên runtime có JFR:

```bash
java -XX:StartFlightRecording=duration=120s,filename=gc-review.jfr,settings=profile -jar app.jar
```

Các lệnh là **ví dụ đo kiểm**. Cần kiểm soát dung lượng log, rotation/retention, overhead recording và quyền truy cập file trong production. Dùng GC log cùng application metrics để phân tích p99, chứ không chỉ nhìn một dòng “pause 1 ms”.

Không ép `System.gc()` liên tục để benchmark: đó không phản ánh nhịp GC tự nhiên của workload, và cách xử lý explicit GC tùy collector/flags.

## 8. Container và chính sách rollout

Đối với Docker/Kubernetes, runtime cần được kiểm tra **bên trong đúng image** sẽ triển khai. `java -version` trên host không chứng minh JDK của container. Cần lưu image digest và các thông số cgroup, CPU quota, memory limit, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` và entrypoint.

Một cấu hình **thử nghiệm** trên HotSpot có ZGC có thể là:

```bash
java -XX:+UseZGC -Xms512m -Xmx512m -Xlog:gc=info -jar app.jar
```

Với **generational Shenandoah** trên build JDK 25+ có hỗ trợ:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xms512m -Xmx512m -Xlog:gc=info -jar app.jar
```

**512 MB chỉ là ví dụ**, không phải heap khuyến nghị cho mọi service. Phải chọn theo SLO, allocation, RAM và container limits thực tế.

Một quy trình rollout tốt nên gồm smoke test GC flags trong CI, benchmark staging, canary deployment, theo dõi CPU/memory/p99, rồi mới rollout rộng. Nếu runtime không nhận flag, deployment phải **FAIL**; không tự xóa flag để JVM âm thầm chọn collector khác. Cần có khả năng rollback về artifact/cấu hình đã kiểm chứng.

## 9. Các tình huống điển hình

### 9.1. Máy phát triển có Shenandoah, production không có

JDK máy dev chạy `-XX:+UseShenandoahGC` thành công nhưng container khác vendor/build không chấp nhận option.

**Cách xử lý:** đối chiếu image digest, `java.vm.name`, vendor, release notes và support status của container; chọn binary được hỗ trợ hoặc collector khác có benchmark tương ứng. Không kết luận “Java 15 có Shenandoah nên production chắc cũng có”.

### 9.2. Nâng lên JDK 24+ nhưng còn flag non-generational ZGC

Một script cũ chứa tùy chọn dành cho non-generational ZGC, vốn **đã bị loại bỏ** trong JDK 24 (JEP 490).

**Cách xử lý:** xóa cờ obsolete/removed theo tài liệu migration và thử `-XX:+UseZGC` ở chế độ generational hiện hành. Chạy lại benchmark, không cố bật lại chế độ đã bị gỡ.

### 9.3. JDK 25 có Shenandoah nhưng vẫn chạy G1

Nếu chỉ nâng JDK mà không chọn GC, JVM có thể vẫn dùng G1. Chế độ generational Shenandoah cũng không mặc nhiên trở thành GC default.

**Cách xử lý:** thử `-XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational` trên đúng build, kiểm tra log và support matrix. Khi có bằng chứng startup và performance phù hợp mới cho phép triển khai.

### 9.4. ZGC pause ngắn nhưng container OOMKilled

`-Xmx` và collector concurrent có thể làm tăng áp lực CPU hoặc memory so với dự kiến; process RSS vượt container limit dù heap nhìn có vẻ ổn.

**Cách xử lý:** kiểm tra heap used/committed, native memory, direct buffers, thread stacks, allocation stalls, CPU quota và GC worker count. Không lấy pause thấp làm chứng cứ hệ thống hoàn toàn khỏe.

### 9.5. Ứng dụng chạy JVM không phải HotSpot

Các flags `-XX:+UseZGC` và `-XX:+UseShenandoahGC` là kiểu cấu hình HotSpot và **không portable cho mọi JVM**.

**Cách xử lý:** xác định JVM implementation từ runtime trước, tra tài liệu chính thức của implementation đó rồi xây cấu hình và benchmark riêng.

## 10. Các nhầm lẫn cần tránh

1. **“OpenJDK 15 có hai GC production thì mọi JDK 15+ đều có.”** Sai: binary và OS/architecture quyết định khả dụng.
2. **“Cùng Java version là cùng JVM và GC flags.”** Sai: vendor, build và VM implementation khác nhau.
3. **“Flag có trong tài liệu nghĩa là image đang chạy đã hỗ trợ.”** Sai: phải thử startup trên image thật.
4. **“Non-generational ZGC vẫn là lựa chọn hiện hành.”** Sai: JDK 24 đã loại bỏ chế độ đó.
5. **“JDK 25 tự bật generational Shenandoah.”** Sai: phải chọn mode/collector và kiểm tra build.
6. **“`java -version` nhận flag thì đã đạt p99 SLO.”** Sai: đó chỉ là kiểm tra khả năng khởi động.
7. **“GC pause thấp nghĩa request latency chắc chắn thấp.”** Sai: còn CPU, stalls và các bottleneck khác.
8. **“`gcBeans` luôn trả cùng một chuỗi cố định.”** Sai: các bean có thể khác giữa JVM/version.
9. **“`-Xmx` bằng container limit không sao.”** Sai: còn native allocations và overhead.
10. **“Có thể đổi GC đang chạy bằng lời gọi Java API.”** Sai: muốn chọn collector khác thường phải restart process.
11. **“Khi option lỗi cứ bỏ flag và tiếp tục production.”** Sai: đó là configuration drift cần báo lỗi.
12. **“Cứ mở experimental flags sẽ bật được feature bị thiếu.”** Sai: phải dùng tính năng production thực sự được vendor hỗ trợ.
13. **“Một lần benchmark đủ chọn collector.”** Sai: cần tải đại diện, nhiều lần chạy, warmup và metric đầy đủ.

## 11. Checklist đánh giá trước khi deploy

- [ ] Đã xác định đúng **vendor, JVM implementation, JDK build, OS/arch và image digest**?
- [ ] Đã kiểm tra runtime của **service/container**, không chỉ máy dev?
- [ ] Đã tra release notes và support matrix của vendor cho build/nền tảng tương ứng?
- [ ] Đã startup-test từng GC flag, lưu exit code và log `Using ...`?
- [ ] Không dùng ZGC non-generational mode đã bị loại bỏ từ JDK 24?
- [ ] Nếu dùng Generational Shenandoah, đã xác nhận JDK 25+ và mode có trong build?
- [ ] Đã xác nhận GC đang chạy bằng startup log và/hoặc MXBeans?
- [ ] Đã giữ G1 làm baseline và so cùng workload/resource budget?
- [ ] Đã đo p99/p99.9, pause time, CPU, throughput, allocation stalls và RSS?
- [ ] Heap/native memory có đủ headroom so với container limit?
- [ ] Có log/JFR, canary, rollback và regression test khi đổi JDK image?
- [ ] Có báo trạng thái riêng **Available / Vendor Supported / Meets SLO**?

**Kết luận:** Đối chiếu GC độ trễ thấp phải gắn với **bản phân phối JDK đang triển khai**, không chỉ với một JEP hoặc tên Java release. Một collector chỉ đáng chọn khi **binary có nó, vendor hỗ trợ môi trường đó, JVM thật sự chọn đúng collector và workload thực tế đạt SLO**. Đây là phương pháp an toàn và còn áp dụng cho Java 15+ cũng như các JDK hiện đại.

## 12. Nguồn chính thức còn hiệu lực

- [Oracle JDK 27 — HotSpot GC Tuning Guide](https://docs.oracle.com/en/java/javase/27/gctuning/): lựa chọn GC, giới hạn và tối ưu.
- [Oracle JDK 27 — Java command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): flags G1, ZGC, Shenandoah, generational mode, `-Xlog`.
- [Oracle JDK 24 — Significant Changes](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html): loại bỏ non-generational ZGC (JEP 490).
- [JEP 377 — ZGC Production](https://openjdk.org/jeps/377) và [JEP 379 — Shenandoah Production](https://openjdk.org/jeps/379): cột mốc Java 15.
- [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439), [JEP 474 — Generational Mode by Default](https://openjdk.org/jeps/474), [JEP 490 — Remove Non-Generational Mode](https://openjdk.org/jeps/490).
- [JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): chế độ sản phẩm kể từ JDK 25.
- [Java SE 27 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): quan sát GC qua API quản trị.
- [Java SE 27 — ManagementFactory](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/ManagementFactory.html): lấy danh sách GC beans và runtime bean.

Các API và phương pháp trên còn được hỗ trợ hiện nay; không hướng dẫn triển khai tính năng GC legacy hoặc cờ đã bị gỡ khỏi JDK hiện đại.