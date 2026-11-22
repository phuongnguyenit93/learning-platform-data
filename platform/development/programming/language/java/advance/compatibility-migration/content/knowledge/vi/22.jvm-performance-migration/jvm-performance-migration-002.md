
# Thay đổi Garbage Collector mặc định và các GC không còn hỗ trợ

Nâng cấp Java không chỉ thay đổi ngôn ngữ, API hoặc định dạng bytecode. Đối với một hệ thống chạy lâu dài, **Garbage Collector (GC) và cơ chế lựa chọn GC của JVM** có thể ảnh hưởng trực tiếp đến thời gian phản hồi, mức sử dụng CPU, bộ nhớ, thời gian dừng ứng dụng (*stop-the-world pause*), khả năng mở rộng và mức ổn định của dịch vụ.

Một ứng dụng Java 8 từng chạy ổn với **Parallel GC** có thể chuyển sang **G1 GC** khi đổi sang một bản JDK mới và không chỉ định collector tường minh. Một cấu hình còn giữ `-XX:+UseConcMarkSweepGC` có thể khiến JVM mới không khởi động vì **Concurrent Mark Sweep (CMS) đã bị loại bỏ**. Cùng lúc, các tùy chọn GC logging, cách JVM phát hiện bộ nhớ/CPU của container và những thuật toán GC khả dụng theo bản phân phối cũng có thể thay đổi.

Điểm cần hiểu trong *Java Advance Compatibility Migration*, chương *JVM và hiệu năng*, là: **tính tương thích của GC không phải chỉ là “ứng dụng có chạy hay không”**. Một migration đúng phải xác định collector đang hoạt động, loại bỏ cờ không còn được hỗ trợ, kiểm tra workload thực tế, và ghi nhận tác động lên cả throughput lẫn tail latency.

Bài học này sử dụng chủ yếu thuật ngữ và ví dụ của **HotSpot/OpenJDK-based JVM**. Một số JVM khác, chẳng hạn OpenJ9, có tên GC, cờ và chiến lược lựa chọn khác; không được áp dụng máy móc mọi ví dụ HotSpot cho chúng.

## 1. GC là gì và vì sao đổi GC có thể đổi hành vi ứng dụng?

Garbage Collector quản lý việc thu hồi vùng nhớ của các đối tượng Java không còn reachable. Tuy nhiên, GC không chỉ là một thao tác “dọn rác” chạy ngẫu nhiên. Collector phải phối hợp với các thread ứng dụng để:

- Theo dõi hoặc xác định object graph đang còn được tham chiếu.
- Tìm các object không còn reachable.
- Thu hồi hoặc tái sử dụng vùng nhớ.
- Đôi khi di chuyển đối tượng để chống phân mảnh.
- Phối hợp với những thao tác yêu cầu tính nhất quán của heap.
- Điều tiết lượng công việc GC và tài nguyên CPU/bộ nhớ.

Tùy thuật toán, một phần công việc được thực hiện khi các **application threads tạm dừng** (*stop-the-world, STW*) hoặc **đồng thời** với ứng dụng (*concurrent*). Collector thường phải cân bằng ba mục tiêu có thể xung đột:

1. **Throughput:** tỷ lệ thời gian CPU dành cho công việc hữu ích của ứng dụng.
2. **Latency:** độ dài và phân bố các khoảng dừng do GC hoặc cơ chế runtime liên quan.
3. **Memory footprint:** lượng heap và bộ nhớ bổ sung cần thiết để đạt hai mục tiêu trên.

Không có collector “nhanh nhất” cho tất cả workload.

### 1.1. Throughput và pause time khác nhau

Giả sử một batch job xử lý được 100.000 bản ghi/giây với tổng thời gian GC nhỏ nhưng thỉnh thoảng dừng vài trăm mili giây. Đây có thể là lựa chọn phù hợp cho batch throughput.

Ngược lại, API xử lý request trực tuyến có thể yêu cầu latency ở phân vị 99 (**p99**) thấp. Collector có nhiều pause ngắn có thể phù hợp hơn một collector đạt throughput cao nhưng thỉnh thoảng có pause dài.

Không nên chỉ đo “tổng số lần GC”:

| Chỉ số | Điều phản ánh | Hạn chế nếu xem đơn lẻ |
|---|---|---|
| Throughput ứng dụng | Công việc hữu ích hoàn thành | Có thể tốt dù tail latency xấu |
| GC pause p50/p95/p99/max | Phân bố thời gian dừng | Không nói hết CPU overhead |
| Tổng GC time | Thời gian GC trong một cửa sổ đo | Có thể không phản ánh tác động concurrent CPU |
| Allocation rate | Tốc độ phát sinh object | Không đo trực tiếp live set |
| Live set/old occupancy | Dữ liệu còn sống lâu | Cần đối chiếu heap sizing |
| CPU utilization | Chi phí xử lý toàn tiến trình | Có thể bị container throttling |
| RSS/native memory | Tổng bộ nhớ process sử dụng | Khác với heap used và `-Xmx` |
| Request p99 | Trải nghiệm latency ứng dụng | Còn phụ thuộc network, DB, locks và I/O |

### 1.2. GC là lựa chọn của JVM, không phải API Java SE bất biến

Không có quy tắc Java SE nào bảo đảm mọi JVM đều dùng G1 hay Parallel GC. Collector được chọn theo **JVM implementation, phiên bản, platform, tài nguyên và flags**.

Vì vậy:

- Không được mặc định mọi Java 8 đều dùng Parallel GC.
- Không được mặc định mọi Java 17 hoặc Java 21 đều luôn dùng G1.
- Không được mặc định cùng `java -version` major thì collector giống nhau trên mọi vendor/build.
- Không được suy ra collector thực tế từ POM hoặc Gradle settings nếu startup script khác.
- Không được coi sự có mặt của một GC trong tài liệu JDK là bằng chứng build cụ thể đang hỗ trợ nó.

## 2. Những collector thường gặp trong HotSpot

### 2.1. Serial GC

**Serial GC** sử dụng phương pháp đơn giản, phù hợp với những cấu hình heap nhỏ hoặc môi trường hạn chế CPU. Một số giai đoạn thu gom dùng ít thread GC hơn các collector song song.

Thường được chọn hoặc được JVM chọn trong hoàn cảnh tài nguyên thấp, nhưng việc lựa chọn cụ thể phải đo trên runtime thực.

Cờ HotSpot điển hình:

~~~bash
java -XX:+UseSerialGC -jar app.jar
~~~

Không phải vì “Serial” mà nó luôn chậm; với workload nhỏ, overhead của collector phức tạp có thể không đáng. Nhưng nó không được thiết kế để đáp ứng cùng mục tiêu latency của các collector đồng thời trên heap lớn.

### 2.2. Parallel GC

**Parallel GC** hướng tới throughput, sử dụng nhiều thread cho các pha thu gom tương ứng.

Cờ điển hình:

~~~bash
java -XX:+UseParallelGC -jar app.jar
~~~

Đây là một lựa chọn thường gặp với batch, workload có thể chấp nhận pause và cần tối đa hóa throughput. Không nên hiểu “Parallel” là hoàn toàn không có stop-the-world pause; nhiều giai đoạn quan trọng vẫn cần dừng ứng dụng.

### 2.3. G1 GC

**Garbage-First (G1) GC** chia heap thành các region và lập kế hoạch thu gom theo mục tiêu pause, sử dụng cả concurrent work và những pha STW. G1 được thiết kế cân bằng throughput với pause-time predictability trên nhiều cấu hình heap.

Cờ điển hình:

~~~bash
java -XX:+UseG1GC -jar app.jar
~~~

G1 là mặc định phổ biến của HotSpot trên nhiều cấu hình JDK hiện đại. Tuy nhiên, `-XX:MaxGCPauseMillis` là **mục tiêu điều chỉnh**, không phải SLA hay giới hạn pause cứng.

### 2.4. Concurrent Mark Sweep (CMS)

**CMS** là collector lịch sử hướng tới giảm những pause dài bằng concurrent marking/sweeping, thường xuất hiện trong cấu hình Java 8 cũ:

~~~text
-XX:+UseConcMarkSweepGC
~~~

CMS đã bị **deprecated trong JDK 9** và **bị loại bỏ trong JDK 14**. Vì vậy một startup configuration từng hợp lệ trên JDK cũ có thể không còn được HotSpot mới chấp nhận.

Cần coi CMS là công nghệ legacy trong các dự án migration hiện đại. Không nên cố giữ `UseConcMarkSweepGC` hoặc các tuning flags CMS như một chiến lược lâu dài.

### 2.5. ZGC

**Z Garbage Collector (ZGC)** được thiết kế hướng tới pause rất ngắn, thực hiện nhiều công việc đồng thời với ứng dụng. Cờ thường gặp trên các HotSpot builds có hỗ trợ:

~~~bash
java -XX:+UseZGC -jar app.jar
~~~

ZGC từng xuất hiện ở trạng thái experimental trong một số release và trở thành production feature trong JDK 15 theo JEP 377. Tính năng thế hệ (*generational*) và cách chọn mode của ZGC tiếp tục thay đổi ở các JDK sau; không giả định cùng một bộ flags có tác dụng giống nhau trên mọi version.

ZGC không phải lựa chọn tốt nhất cho mọi batch nhỏ. Hãy đánh giá CPU headroom, bộ nhớ và throughput cùng với pause-time.

### 2.6. Shenandoah

**Shenandoah GC** cũng hướng tới low-pause bằng nhiều công việc concurrent, có mặt trong một số OpenJDK-based builds:

~~~bash
java -XX:+UseShenandoahGC -jar app.jar
~~~

Shenandoah được giới thiệu như một collector experimental từ JDK 12 (JEP 189) và chuyển thành production feature trong JDK 15 (JEP 379) tại những distribution/build hỗ trợ nó. Không phải mọi nhà phân phối hoặc platform đều đóng gói, bật hoặc hỗ trợ Shenandoah giống nhau.

### 2.7. Bảng so sánh định hướng

| Collector | Trọng tâm thường gặp | Điều phải lưu ý khi migration |
|---|---|---|
| Serial | Đơn giản, chi phí thấp với môi trường nhỏ | Có thể tăng pause với heap/workload lớn |
| Parallel | Throughput | STW pauses có thể dài hơn mục tiêu API latency |
| G1 | Cân bằng throughput và thời gian dừng | Heuristics, region sizing, pause targets khác theo version |
| CMS | Low-pause legacy | Đã bị loại khỏi HotSpot từ JDK 14 |
| ZGC | Very low pause | Kiểm tra availability, mode, CPU/memory overhead |
| Shenandoah | Low pause/concurrent work | Phụ thuộc distribution/build và version |

Bảng là **định hướng**, không phải xếp hạng hiệu năng hay lời hứa rằng một collector luôn vượt trội.

## 3. Mốc thay đổi GC đáng nhớ khi nâng JDK

Các mốc dưới đây là những sự kiện kỹ thuật phổ biến của nhánh OpenJDK/HotSpot; một vendor có thể có backport, khác biệt chính sách hoặc JVM implementation khác.

| JDK / giai đoạn | Diễn biến quan trọng | Ý nghĩa khi migration |
|---|---|---|
| JDK 8 và các bản cũ | Parallel GC phổ biến là lựa chọn mặc định trên nhiều máy server-class; CMS có thể chọn tường minh | Cần ghi cấu hình thật thay vì suy từ version |
| JDK 9 | G1 trở thành collector mặc định cho cấu hình HotSpot phù hợp (JEP 248) | Ứng dụng không ghi GC flag có thể đổi collector |
| JDK 9 | CMS được đánh dấu deprecated (JEP 291) | Bắt đầu kế hoạch bỏ CMS và tuning tương ứng |
| JDK 9 | Unified JVM Logging được đưa vào sử dụng | Phải chuyển cách thu thập và phân tích GC log cũ |
| JDK 11 | ZGC có ở trạng thái experimental trên các platform/build hỗ trợ | Không coi là lựa chọn phổ quát |
| JDK 12 | Shenandoah có ở trạng thái experimental trong các build hỗ trợ | Kiểm tra build và cờ kích hoạt |
| JDK 14 | CMS bị loại bỏ (JEP 363) | Cấu hình `UseConcMarkSweepGC` legacy có thể làm JVM startup thất bại |
| JDK 15 | ZGC và Shenandoah đạt trạng thái production feature ở những build hỗ trợ | Có thêm lựa chọn low-pause |
| JDK 17 | G1 thường được chọn mặc định trên HotSpot server-class nếu không bị override | Migration Java 8 → 17 cần đánh giá lại GC |
| JDK 21 | G1 tiếp tục là mặc định phổ biến của HotSpot; Generational ZGC được giới thiệu (JEP 439) | Không nhầm cờ chọn ZGC với cấu hình thế hệ ở mọi release |
| Các release sau | Thuật toán, mode và flags có thể tiếp tục phát triển | Kiểm chứng trên đúng JDK vendor/build, không copy bảng cũ |

**Điểm quan trọng:** thay đổi mặc định không có nghĩa Parallel GC bị loại bỏ. Parallel, G1 và Serial có thể tiếp tục tồn tại đồng thời, trong khi **CMS là trường hợp bị loại thực sự** khỏi HotSpot từ JDK 14.

### 3.1. Vì sao JDK 9 chọn G1 mặc định?

JEP 248 thay đổi default collector sang G1 nhằm cải thiện trải nghiệm về pause time cho nhiều ứng dụng mà không bắt người vận hành phải tự chọn GC. Nhưng đó là **default ergonomics**, không phải cam kết G1 luôn thắng về throughput.

Một batch job trước đây tối ưu kỹ cho Parallel GC có thể cần tiếp tục chọn Parallel một cách tường minh sau khi đã benchmark. Ngược lại, một API chịu áp lực p99 có thể hưởng lợi từ default G1 nhưng vẫn phải đo bằng workload.

### 3.2. CMS deprecated khác CMS removed

**Deprecated** nghĩa là công nghệ được cảnh báo không nên tiếp tục phụ thuộc, nhưng có thể vẫn sử dụng được ở release cụ thể.

**Removed** nghĩa là implementation hoặc cờ lựa chọn không còn được cung cấp theo cách cũ. Khi chuyển tới JDK có CMS đã bị loại, ứng dụng phải bỏ hoặc thay cấu hình CMS.

Sự khác biệt này ảnh hưởng kế hoạch migration:

1. Trong giai đoạn deprecated, thu thập benchmark trên lựa chọn thay thế.
2. Xác định mọi nguồn cấu hình CMS.
3. Chuyển GC, kiểm tra heap và tuning strategy.
4. Xóa flags CMS đã lỗi thời.
5. Kiểm thử startup và behavior trên JDK đích.

Không nên đợi tới khi JVM production không khởi động mới xử lý.

## 4. Thay đổi GC mặc định không tương đương đổi flag

Ví dụ lệnh không chỉ định GC:

~~~bash
java -Xms1g -Xmx2g -jar orders.jar
~~~

Collector được JVM quyết định dựa trên các heuristics và runtime configuration. Khi nâng JDK, kết quả có thể đổi.

Lệnh chọn rõ:

~~~bash
java -XX:+UseG1GC -Xms1g -Xmx2g -jar orders.jar
~~~

thể hiện ý định dùng G1, nhưng vẫn phải kiểm tra collector có được hỗ trợ và có được JVM chấp nhận không.

### 4.1. Khi nào nên để JVM chọn mặc định?

Có thể để default nếu:

- Sản phẩm không có yêu cầu collector riêng.
- Workload đã được kiểm chứng trên JDK/runtime đích.
- Không có policy đặc biệt về tail latency, throughput hoặc footprint buộc chọn collector khác.
- Có monitoring và kế hoạch đánh giá sau update.
- Môi trường runtime/resource profile được quản lý nhất quán.

Ưu điểm: giảm cấu hình và tận dụng các cải tiến ergonomics của JVM. Nhược điểm: collector được chọn có thể thay đổi khi JDK hoặc container limits thay đổi.

### 4.2. Khi nào nên chọn GC tường minh?

Có thể pin collector nếu:

- Benchmark chứng minh collector cụ thể đáp ứng mục tiêu tốt hơn.
- Có cam kết về tail latency với workload và heap nhất định.
- Sản phẩm phải giữ hành vi ổn định qua giai đoạn chuyển JDK.
- Một plugin/agent/provider có tương tác đặc biệt cần được kiểm tra.
- Lộ trình rollout cần tách thay đổi JDK khỏi thay đổi GC.

Tuy nhiên, **pin GC không có nghĩa pin toàn bộ heuristics**. Cùng G1 nhưng qua hai JDK có thể vẫn khác region sizing, remembered-set, scheduling, logging hoặc footprint. Phải đo lại trên JDK đích.

### 4.3. Default có thể bị ảnh hưởng bởi tài nguyên

Trên JVM triển khai cơ chế server-class machine hoặc container awareness, CPU count, available memory và cách JVM nhìn thấy resource limits có thể ảnh hưởng collector/heap/GC thread ergonomics.

Do đó, một JDK trên máy 32 core có thể chọn hành vi khác cùng JDK trong container giới hạn rất thấp. Không nên viết “Java 17 chắc chắn dùng G1 trong mọi Pod” mà chưa xem log runtime.

## 5. Cách xác định GC thực sự đang chạy

Đây là bước bắt buộc trước và sau khi migration.

### 5.1. Xem startup log của JVM

Với HotSpot hiện đại:

~~~bash
java -Xlog:gc=info -version
~~~

Trong nhiều build, log có thể hiển thị collector được lựa chọn, ví dụ một dòng dạng:

~~~text
[info][gc] Using G1
~~~

Đây là ví dụ minh họa. Tên/log tag hoặc cách báo có thể khác theo JDK và cấu hình.

Nếu cần thông tin ban đầu chi tiết hơn:

~~~bash
java -Xlog:gc+init=info -version
~~~

`java -version` chỉ xác nhận runtime version. **GC log hoặc runtime flags mới hỗ trợ xác định collector đã chọn**.

### 5.2. Xem command-line flags

Trên HotSpot:

~~~bash
java -XX:+PrintCommandLineFlags -version
~~~

Và khi cần tìm flags sau khi JVM áp dụng ergonomics:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Đầu ra có thể rất dài. Có thể lọc theo shell:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 \
  | grep -E 'UseG1GC|UseParallelGC|UseSerialGC|UseZGC|UseShenandoahGC'
~~~

Trên PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String 'UseG1GC|UseParallelGC|UseSerialGC|UseZGC|UseShenandoahGC'
~~~

Đọc cả **giá trị flag**, không chỉ tên có xuất hiện. Một dòng `UseG1GC = false` không có nghĩa JVM đang dùng G1.

### 5.3. Xem JVM đang chạy bằng jcmd

Khi được phép chẩn đoán process:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

`VM.command_line` cho thấy launcher arguments, còn `VM.flags` giúp kiểm tra flags có hiệu lực hoặc được hiển thị. `GC.heap_info` có thể cung cấp thông tin heap/collector tùy JVM.

Một số lệnh `jcmd` khác có thể tạo overhead đáng kể hoặc yêu cầu quyền cao. Không chạy diagnostic nặng trên production nếu chưa đánh giá chi phí.

### 5.4. Sử dụng MXBeans từ Java

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public final class GcRuntimeInfo {
    public static void main(String[] args) {
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("name=" + bean.getName());
            System.out.println("collections=" +
                    bean.getCollectionCount());
            System.out.println("collectionTimeMs=" +
                    bean.getCollectionTime());
        }
    }
}
~~~

Tên bean thường cho biết các nhóm thu gom cụ thể, ví dụ young/old của collector, nhưng **đây không phải API chuẩn hóa để trả về một GC ID duy nhất cho mọi JVM**. Một số metric có thể trả `-1` nếu JVM không hỗ trợ.

Không dùng tên MXBean dạng string làm quy tắc kinh doanh hoặc logic tự động chuyển collector.

### 5.5. Không ghi log thông tin nhạy cảm

Dump toàn bộ JVM command line có thể chứa tham số mang token, password hoặc URL nội bộ. Hệ thống quan sát nên trích xuất **các JVM GC flags cần thiết** và redaction dữ liệu nhạy cảm trước khi lưu hoặc chia sẻ.

## 6. Các cờ CMS cũ có thể phá startup

Nhiều hệ thống Java 8 có startup template như:

~~~bash
java \
  -XX:+UseConcMarkSweepGC \
  -XX:CMSInitiatingOccupancyFraction=70 \
  -XX:+UseCMSInitiatingOccupancyOnly \
  -Xms2g \
  -Xmx2g \
  -jar orders.jar
~~~

Trên JDK đã loại CMS, những tùy chọn liên quan có thể không được nhận diện hoặc không còn được hỗ trợ. JVM có thể kết thúc sớm trước khi ứng dụng được gọi.

Một thông báo điển hình:

~~~text
Unrecognized VM option 'UseConcMarkSweepGC'
Error: Could not create the Java Virtual Machine.
~~~

Thông báo và hành vi chính xác phụ thuộc release/vendor, nhưng **startup failure** là rủi ro thực tế.

### 6.1. Những flags legacy cần tìm

Một số tên thường xuất hiện trong hệ thống cũ:

| Flag / nhóm | Liên quan | Hành động migration |
|---|---|---|
| `-XX:+UseConcMarkSweepGC` | Chọn CMS | Loại bỏ và chọn collector hiện được hỗ trợ |
| `-XX:+UseParNewGC` | Cơ chế young generation legacy | Kiểm tra tính hợp lệ trên JDK đích; không chuyển máy móc |
| `-XX:CMSInitiatingOccupancyFraction=...` | CMS scheduling | Bỏ nếu đã bỏ CMS; không áp trực tiếp cho G1 |
| `-XX:+UseCMSInitiatingOccupancyOnly` | CMS initiation policy | Bỏ và đánh giá lại mục tiêu tuning |
| `-XX:+CMSClassUnloadingEnabled` | Cờ CMS legacy | Không giả định còn cần hoặc còn tồn tại |
| `-XX:+ExplicitGCInvokesConcurrent` | Hành vi khi gọi explicit GC | Kiểm chứng semantics theo collector/JDK, không giữ theo thói quen |
| `-XX:+UseG1GC` | Chọn G1 | Còn thường được hỗ trợ, nhưng phải test |
| `-XX:+UseParallelGC` | Chọn Parallel | Còn thường được hỗ trợ, không phải CMS replacement tự động |
| `-XX:+UseSerialGC` | Chọn Serial | Chỉ dùng khi phù hợp workload |
| `-XX:+UseZGC` | Chọn ZGC | Kiểm tra availability và policy theo JDK |

Không phải mọi flag trong bảng đều chắc chắn bị loại cùng release. Mục đích bảng là giúp **phân loại legacy flags**, sau đó đối chiếu tài liệu và runtime thực tế.

### 6.2. Không chỉ thay một dòng CMS thành G1

Sai lầm:

~~~text
Bỏ -XX:+UseConcMarkSweepGC
Thêm -XX:+UseG1GC
Giữ nguyên toàn bộ CMS tuning
~~~

Các collector khác nhau về heap layout, heuristics và ý nghĩa tuning. Nhiều CMS-specific flags không liên quan đến G1 hoặc không được chấp nhận.

Một cách tiếp cận tốt hơn:

1. Loại bỏ toàn bộ cờ chọn/tuning đặc thù CMS.
2. Giữ những ràng buộc chung cần thiết như `-Xmx` khi phù hợp.
3. Chạy G1 với mặc định trước khi tinh chỉnh.
4. Thu thập baseline pause, throughput, memory.
5. Chỉ thêm tuning flag G1 khi có bằng chứng.
6. Chạy canary và so sánh cùng workload.

### 6.3. Vì sao IgnoreUnrecognizedVMOptions nguy hiểm?

Một số JVM có cơ chế bỏ qua option không nhận diện. Đừng dùng tùy chọn kiểu `-XX:+IgnoreUnrecognizedVMOptions` để “chữa” startup hàng loạt.

Hành vi bỏ qua cờ có thể:

- Che khuất cấu hình không còn hiệu lực.
- Khiến collector khác được chọn ngoài ý muốn.
- Giữ lại những giả định sai về heap/GC.
- Gây sai khác giữa môi trường.
- Làm mất tín hiệu lỗi hữu ích trong migration.

Đối với GC selection hoặc memory safety, **fail rõ ràng** thường dễ kiểm soát hơn việc silently ignore một cờ thiết yếu.

## 7. Tìm mọi nguồn JVM GC flags

Một cờ GC không nhất thiết nằm trong startup script chính. Nó có thể đến từ:

- `JAVA_OPTS` hoặc biến do service wrapper/framework cung cấp.
- `JAVA_TOOL_OPTIONS`.
- `JDK_JAVA_OPTIONS` trên launcher hỗ trợ.
- `_JAVA_OPTIONS` ở những môi trường triển khai có sử dụng.
- Dockerfile hoặc container entrypoint.
- Kubernetes Deployment/Helm values/Kustomize overlays.
- Systemd unit, Windows service configuration.
- CI/CD job, test runner và integration test task.
- Maven Surefire/Failsafe `argLine`.
- Gradle `Test` hoặc `JavaExec` `jvmArgs`.
- Script của application server hoặc plugin host.
- Nền tảng PaaS inject JVM options.
- Run configuration của IDE hoặc cấu hình profile.

Dùng ripgrep trong repository để tìm:

~~~bash
rg -n --hidden --glob '!**/.git/**' -- \
  'UseConcMarkSweepGC|UseParNewGC|CMSInitiating|UseG1GC|UseParallelGC|UseZGC|UseShenandoahGC|PrintGC' .
~~~

Tìm source chỉ là bước đầu. Cần so sánh với **JVM arguments thực tế** của process đang chạy. Một server có thể ghép nhiều biến và tùy chọn ở các tầng khác nhau.

### 7.1. Cảnh giác với cấu hình trùng nhau

Một flag trong Docker image có thể bị ghi đè hoặc mâu thuẫn với manifest deployment. Cùng một ứng dụng có thể dùng G1 trong test và Parallel trong production mà team không biết.

Khi rà soát, lập bảng:

| Nguồn | Môi trường | GC flag | JVM version | Chủ sở hữu |
|---|---|---|---|---|
| Gradle Test task | CI | Explicit G1 | Build JDK | Build team |
| Docker entrypoint | Staging | Không có | Runtime JDK | Platform |
| Helm values | Production | Parallel | Runtime JDK | SRE |
| App server startup | Batch | CMS legacy | Runtime JDK cũ | Ops |

Các dòng chỉ là ví dụ quản lý, không phải cấu hình được khuyến nghị.

## 8. GC logging cũng thay đổi khi nâng JDK

Từ JDK 9, **Unified JVM Logging** là cơ chế chuẩn để thu thập nhiều thông tin runtime, bao gồm GC.

Cấu hình GC logging cũ trên Java 8 có thể chứa:

~~~text
-verbose:gc
-XX:+PrintGCDetails
-XX:+PrintGCDateStamps
-Xloggc:/var/log/app/gc.log
-XX:+UseGCLogFileRotation
-XX:NumberOfGCLogFiles=5
-XX:GCLogFileSize=20M
~~~

Một phần các tùy chọn legacy có thể được ánh xạ, cảnh báo hoặc không còn được hỗ trợ tùy JDK. Không nên giữ nguyên cả cụm mà chưa kiểm tra.

### 8.1. Ví dụ Unified Logging

Với HotSpot hiện đại:

~~~bash
java \
  -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -Xms1g \
  -Xmx2g \
  -jar app.jar
~~~

Đây là ví dụ cấu hình; thư mục `logs` phải tồn tại và process cần quyền ghi.

Các thành phần:

- `gc*`: chọn các log tag có liên quan đến GC theo wildcard của Unified Logging.
- `safepoint`: ghi thêm những sự kiện safepoint được chọn.
- `file=...`: output file.
- `time,uptime,level,tags`: decorators.
- `filecount` và `filesize`: cấu hình rotation ở output.
  
Cú pháp và tag levels cần được kiểm tra với đúng JDK. Lệnh:

~~~bash
java -Xlog:help
~~~

cho phép xem khả năng logging của runtime tương ứng.

### 8.2. GC log format không phải API bất biến

Một parser hoặc dashboard viết riêng cho GC log Java 8/CMS có thể không hiểu GC log G1 của JDK 17 hoặc log của ZGC.

Rủi ro:

- Log parser không match event.
- Dashboards hiển thị 0 pause dù JVM vẫn GC.
- Alert rule dùng pattern legacy trở thành vô dụng.
- Dữ liệu histogram trước/sau bị so sánh sai.
- Nhận nhầm concurrent events là STW.
- Sai đơn vị mili giây/giây.

Khi migration, phải nâng **logging pipeline và dashboard** cùng với runtime, không chỉ đổi JVM flags.

### 8.3. Dữ liệu log nào cần thu thập?

Tối thiểu cho benchmark:

- GC start/end time và duration.
- Pause reason/type.
- Heap before/after, committed và capacity.
- Young/old collection events khi collector có khái niệm tương ứng.
- Concurrent phase times.
- Allocation pressure và memory occupancy.
- Safepoint time nếu tác động latency.
- CPU context và container limits.

Không lấy số lượng pause giữa hai collector có kiến trúc khác nhau làm một chỉ số chất lượng duy nhất.

## 9. Kích thước heap và GC là hai quyết định liên quan

Các cờ phổ biến:

~~~bash
java -Xms1g -Xmx4g -jar app.jar
~~~

- `-Xms`: initial Java heap size.
- `-Xmx`: maximum Java heap size.

Chúng không kiểm soát toàn bộ memory footprint của tiến trình. Ngoài heap còn có:

- Metaspace và class metadata.
- Thread stacks.
- Direct/native buffers.
- JIT code cache.
- GC native structures.
- JNI/native libraries.
- Memory của runtime/framework khác.

Một container memory limit 4 GiB không có nghĩa có thể đặt `-Xmx4g` rồi mong mọi thứ an toàn. Process còn cần **native headroom**.

### 9.1. Thay GC có thể đổi memory overhead

Các collector có metadata, thread pools và cơ chế concurrent riêng. Cùng `-Xmx` nhưng RSS, peak memory và CPU khác nhau.

Với G1, remembered sets và region metadata chiếm thêm bộ nhớ. Với ZGC/Shenandoah, cơ chế concurrent work và memory mapping có thể tạo dấu hiệu khác trong những metric của hệ điều hành.

Không kết luận “collector A dùng ít RAM hơn collector B” chỉ từ `heap used` tại một thời điểm. Cần đo **RSS, heap, native memory và workload** đồng thời.

### 9.2. Xms bằng Xmx có luôn tốt?

Không. Đặt `-Xms` bằng `-Xmx` có thể giảm nhu cầu resize heap ở một số workload nhưng cũng có thể tăng footprint, commit memory và ảnh hưởng startup/resource sharing.

Quyết định phụ thuộc:

- Latency requirement.
- Container memory limit.
- Startup/warmup behavior.
- Có nhiều JVM chạy trên cùng node không?
- Live set và allocation rate.
- Collector được chọn.
- Cơ chế commit/uncommit memory của JVM/GC version.

Hãy đo thay vì áp một công thức chung.

### 9.3. MaxRAMPercentage và container

HotSpot cung cấp các tùy chọn ergonomic như:

~~~bash
java -XX:MaxRAMPercentage=65.0 -jar app.jar
~~~

Ý nghĩa phụ thuộc cơ chế tính available RAM của JVM. Trên JDK hiện đại có container awareness, giới hạn cgroup có thể ảnh hưởng heap sizing và số GC threads.

Không dùng đồng thời nhiều cơ chế heap sizing mà không hiểu ưu tiên thực tế. Khi `-Xmx` được chỉ định tường minh, nó tác động trực tiếp tới maximum heap và có thể làm kỳ vọng từ `MaxRAMPercentage` không đúng.

## 10. Container awareness và CPU ergonomics

Sau khi chuyển ứng dụng lên Kubernetes hoặc thay JDK trong container, GC có thể hoạt động khác dù config tương đối giống nhau.

Một số JDK HotSpot hỗ trợ phát hiện giới hạn container qua `-XX:+UseContainerSupport` (mặc định được bật trong nhiều release hiện đại). Mức hỗ trợ, xử lý cgroups và backport khác nhau theo release/vendor.

Với container, cần ghi:

- CPU limit/quota và CPU request.
- Memory limit.
- cgroup version.
- JVM-reported active processor count.
- Maximum heap thực tế.
- Số GC/concurrent worker threads.
- CPU throttling statistics.
- RSS và OOMKilled events.

### 10.1. CPU limit ảnh hưởng GC như thế nào?

Collector concurrent dùng CPU để đánh dấu/thu hồi song song với ứng dụng. Nếu container bị CPU throttling, background GC có thể không theo kịp allocation rate, dẫn tới tăng latency hoặc pressure.

G1/Parallel/ZGC có mô hình worker khác nhau. Tăng số GC threads không tự động cải thiện hiệu năng nếu quota CPU không đủ.

Khi cần thử nghiệm có kiểm soát, HotSpot có thể cung cấp:

~~~text
-XX:ActiveProcessorCount=4
~~~

Flag này thay đổi cách một số heuristics nhận diện số CPU; phải được dùng có chủ đích, kiểm chứng trên JDK tương ứng. Không dùng nó để “tăng CPU thật” vượt quota của container.

### 10.2. Vì sao cùng JDK có thể chọn GC khác nhau?

Nếu JVM nhận diện môi trường với tài nguyên rất nhỏ, các heuristics có thể chọn giải pháp khác với server nhiều CPU/RAM. Vì vậy khi chỉ nhìn JDK version, không thể khẳng định 100% default collector.

Mỗi kết quả benchmark phải ghi **runtime resource profile**, không chỉ `java -version`.

## 11. So sánh GC theo workload và SLO

Trước khi đổi collector, xác định yêu cầu sản phẩm.

### 11.1. Batch/throughput-oriented

Một job phân tích dữ liệu có thể ưu tiên:

- Tổng thời gian hoàn thành.
- Throughput record/s.
- CPU efficiency.
- Heap occupancy ổn định.
- Không OOM khi dataset lớn.

Nếu p99 request latency không phải mục tiêu chính, Parallel GC vẫn có thể là ứng viên benchmark hợp lệ trên JDK hỗ trợ.

### 11.2. Online API/tail-latency-oriented

Một API cần phản hồi nhanh có thể ưu tiên:

- p95/p99/p99.9 response time.
- GC pause duration.
- Số request bị ảnh hưởng bởi pause.
- Error rate, timeout, retry amplification.
- Latency trong load peak và khi autoscaling.

G1 hoặc low-pause collectors có thể phù hợp tùy workload, nhưng kết luận cần benchmark. Không nên tuyên bố “ZGC luôn tối ưu cho API” nếu CPU headroom, heap size hoặc throughput không đáp ứng.

### 11.3. Memory-constrained services

Với nhiều JVM nhỏ trên một node, mục tiêu có thể là:

- RSS nhỏ.
- Không bị OOMKill.
- Startup nhanh.
- Không dùng quá nhiều worker threads.
- Throughput vừa đủ.

Serial hoặc G1 có thể là ứng viên tùy điều kiện. Không sử dụng collector low-latency phức tạp mặc định chỉ vì nó “mới nhất”.

## 12. MaxGCPauseMillis là mục tiêu chứ không phải bảo đảm

Một cấu hình G1 thường thấy:

~~~bash
java \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -Xms2g \
  -Xmx4g \
  -jar app.jar
~~~

`MaxGCPauseMillis` là **mục tiêu** để GC ergonomics cân bằng công việc trong những pause thích hợp. Nó không bắt buộc mọi pause dưới 200 ms và không phải giới hạn latency request.

Nếu đặt giá trị quá thấp:

- Collector có thể tăng tần suất pause.
- Throughput có thể giảm.
- Memory pressure có thể tăng.
- Background/concurrent work tăng.
- Một số full GC hoặc safepoint khác vẫn có thể kéo dài.

Tối ưu nên dựa trên phân bố pause và SLO, không đơn giản giảm số này liên tục.

### 12.1. Full GC khác young/mixed pause

Đặc biệt với G1, cần phân biệt:

- Young evacuation pause.
- Mixed collection pause.
- Concurrent mark/cleanup phases.
- Full GC hoặc failure mode cần STW lớn hơn.
- Safepoints khác không nhất thiết được tính như GC pause.

Nếu dashboard gộp mọi event thành “GC pause”, khó xác định nguyên nhân. Khi có full GC dài, cần xem allocation pressure, live set, evacuation failure, humongous objects, heap sizing và fragmentation theo collector/JDK đang dùng.

### 12.2. Allocation rate và live set

Một ứng dụng tạo nhiều object ngắn hạn có thể phát sinh GC đều đặn nhưng vẫn đáp ứng latency. Một ứng dụng giữ nhiều object sống lâu có thể gây áp lực old generation và không có dư địa thu hồi.

Vì vậy, tối ưu GC có thể cần sửa:

- Cache sizing và TTL.
- Object retention leaks.
- Large temporary allocations.
- Batch buffer lifetimes.
- Direct buffer usage.
- ThreadLocal giữ dữ liệu.
- Data structures gây memory overhead.

**Chuyển GC không chữa được memory leak logic**. Nó có thể thay đổi triệu chứng hoặc thời điểm lỗi, nhưng không khiến dữ liệu còn reachable tự biến mất.

## 13. ZGC và Shenandoah: giảm pause nhưng không miễn phí

Các collector low-pause hướng tới việc chuyển nhiều công việc khỏi giai đoạn dừng ứng dụng. Điều này thường đem lại trade-off:

- Cần CPU headroom cho concurrent work.
- Có thể cần thêm memory headroom.
- Thuật toán phối hợp với application threads có chi phí riêng.
- Throughput có thể khác collector hướng throughput.
- Native memory và cách accounting có thể thay đổi.
- Những mode thế hệ thay đổi cách xử lý đối tượng sống ngắn/dài.
- Mức availability còn phụ thuộc JDK distribution và build flags.

### 13.1. Không so sánh một cấu hình ZGC với cấu hình CMS cũ rồi kết luận

CMS đã bị loại và cấu hình của nó thường chứa nhiều tuning legacy. Khi benchmark collector mới:

- Chạy cùng JDK version (nếu collector cùng khả dụng) để tách biến GC.
- Chạy cùng artifact, dependency, dữ liệu đầu vào.
- Giữ resource limits tương đương.
- Cho workload warmup đủ.
- Chạy lặp lại nhiều lần.
- Báo cả throughput, latency, RSS và CPU.
- Tách ảnh hưởng của JVM upgrade khỏi ảnh hưởng của GC replacement.

### 13.2. Generational ZGC

JDK 21 giới thiệu **Generational ZGC** như một lựa chọn khi dùng ZGC. Ví dụ lịch sử ở JDK hỗ trợ mode này:

~~~bash
java -XX:+UseZGC -XX:+ZGenerational -jar app.jar
~~~

Không nên xem đây là một cặp cờ vĩnh viễn cho mọi Java mới. Cách chọn mode và sự tồn tại của các flags có thể thay đổi khi ZGC phát triển qua các release sau. Hãy đọc `java -XX:+PrintFlagsFinal -version`, release notes và startup log của **JDK đích**.

Nếu một flag thế hệ đã trở thành mặc định hoặc bị loại, giữ cờ cũ có thể vô nghĩa hoặc làm startup lỗi. Đây cũng là nguyên tắc chung cho mọi option GC.

## 14. Quy trình kiểm kê và thay GC cho ứng dụng cũ

Một checklist migration thực tế có thể tổ chức theo các giai đoạn.

~~~mermaid
flowchart TD
    A["Ghi JDK, collector, flags và workload baseline"] --> B["Tìm flags legacy và nguồn cấu hình"]
    B --> C["Chọn JDK/GC target có hỗ trợ"]
    C --> D["Loại flags không còn hợp lệ"]
    D --> E["Startup test và xác nhận GC thực tế"]
    E --> F["Chạy benchmark / integration test"]
    F --> G{"SLO, memory, CPU và startup đạt?"}
    G -->|Có| H["Canary và rollout có giám sát"]
    G -->|Không| I["Phân tích logs, heap, CPU, workload"]
    I --> C
    H --> J["Ghi evidence, guardrail và rollback"]
~~~

### Bước 1 — Chụp baseline có thể tái hiện

Trước khi nâng:

- JDK vendor, version, build.
- OS/architecture và container image.
- Process startup command và GC flags có hiệu lực.
- Collector được chọn thực tế.
- `-Xms`, `-Xmx` và các memory options.
- CPU/memory limits, cgroup version.
- Application artifact hash.
- Workload, dataset và traffic profile.
- GC logs, latency histograms, throughput, CPU, RSS.
- Log parser/dashboard version.

Không phải mọi project cần cùng mức chi tiết, nhưng thiếu baseline sẽ khó trả lời “GC mới tốt hơn hay xấu hơn”.

### Bước 2 — Phân loại mọi GC flag

Chia thành:

1. **Lựa chọn collector**: `UseG1GC`, `UseParallelGC`, `UseConcMarkSweepGC`...
2. **Heap sizing**: `Xms`, `Xmx`, `MaxRAMPercentage`.
3. **Tuning collector-specific**: CMS, G1, ZGC, Shenandoah options.
4. **Logging/diagnostics**: `PrintGCDetails`, `-Xlog:gc...`.
5. **Ergonomics/resource**: processor count, GC workers.
6. **Khác**: safepoint, explicit GC behavior, native-memory diagnostics.

Một cờ hợp lệ với collector cũ không nhất thiết hợp lệ hoặc cần thiết với collector mới.

### Bước 3 — Xác nhận hỗ trợ của JDK đích

Kiểm tra:

- Collector có trong build không?
- JVM chấp nhận flag không?
- Có experimental unlock requirement không, nếu release cụ thể yêu cầu?
- Có mode generational/mode-specific flag nào cần biết?
- Có caveat về OS/CPU?
- Có tác động với custom runtime?
- Support policy của vendor có giới hạn không?

Test startup sớm; đừng để lỗi option chỉ xuất hiện trong production rollout.

### Bước 4 — Chuyển từ cấu hình cũ sang baseline sạch

Nếu chuyển CMS sang G1, thay cấu hình đặc thù CMS bằng **G1 baseline đơn giản**. Ví dụ:

~~~bash
java \
  -XX:+UseG1GC \
  -Xms2g \
  -Xmx4g \
  -Xlog:gc*:file=logs/gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

Đây là mẫu minh họa; tên file và memory size phải điều chỉnh theo hệ thống. Chạy với các default G1 thích hợp trước khi thêm tuning.

### Bước 5 — Kiểm tra startup và collector thực sự

Xác nhận:

- Không có warning/error về JVM options.
- GC log nêu collector mong đợi.
- Heap sizing khớp expectation.
- Container limits được JVM nhận đúng.
- Metrics pipeline đọc được log mới.
- Không còn legacy flags được inject từ nơi khác.

### Bước 6 — Benchmark dưới tải đại diện

Nên có:

- Warmup.
- Steady-state load.
- Peak traffic.
- Long-running soak test.
- Batch job có allocation profile riêng.
- Load khi service phụ thuộc chậm hoặc mất kết nối.
- Restart/rolling deploy behavior.
- Test gần ngưỡng memory limit.

So sánh theo bảng metric và cùng cửa sổ đo; tránh lấy hai giờ cao điểm khác nhau rồi coi đó là GC A/B test chuẩn.

### Bước 7 — Canaries và giám sát

Triển khai một tỷ lệ nhỏ instance hoặc một môi trường staged, quan sát:

- GC pause p99/max.
- Request p99 và timeout.
- CPU throttling.
- Memory/RSS và OOMKill.
- GC overhead.
- Thread count, allocation pressure.
- Startup/readiness/termination time.
- Business throughput và error rate.

Nếu không đạt SLO, có kế hoạch quay lại collector đã được hỗ trợ trên JDK đích, hoặc rollback toàn bộ runtime tùy phạm vi.

## 15. Tách ba loại thay đổi để dễ chẩn đoán

Một lần migration có thể thay đồng thời:

1. **JDK version**.
2. **Collector**.
3. **Heap/resource configuration**.

Nếu đổi cả ba cùng lúc, khó quy nguyên nhân.

Ví dụ bộ thí nghiệm:

| Thử nghiệm | JDK | GC | Heap/resource | Mục tiêu |
|---|---|---|---|---|
| A | JDK cũ | Collector cũ | Baseline | Đối chứng |
| B | JDK mới | GC gần tương đương còn được hỗ trợ | Giống baseline nếu phù hợp | Tách ảnh hưởng JDK |
| C | JDK mới | Collector mục tiêu | Giống B | Tách ảnh hưởng GC |
| D | JDK mới | Collector mục tiêu | Heap/CPU tuning mới | Đo hiệu quả tuning |

Không phải lúc nào B thực hiện được: ví dụ CMS đã bị loại trên JDK 14+, nên không thể chạy CMS trên JDK mới để tách biến hoàn toàn. Khi đó cần ghi rõ hạn chế thực nghiệm và dùng nhiều baseline hỗ trợ.

### 15.1. Một bản JVM update nhỏ cũng có thể tác động

JVM update có thể sửa GC bug hoặc thay heuristics, logging, container detection. Không chỉ major version mới ảnh hưởng performance.

Với hệ thống nhạy hiệu năng, nên benchmark cả những bản update quan trọng trong cùng dòng JDK khi rollout.

## 16. Ví dụ migration Java 8 với CMS sang Java 17 với G1

Giả sử một dịch vụ đơn hàng cũ có startup:

~~~bash
java \
  -XX:+UseConcMarkSweepGC \
  -XX:+UseCMSInitiatingOccupancyOnly \
  -XX:CMSInitiatingOccupancyFraction=65 \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -Xloggc:logs/gc-old.log \
  -Xms2g \
  -Xmx4g \
  -jar orders.jar
~~~

### 16.1. Nhận diện vấn đề

- CMS không còn được cung cấp trên HotSpot JDK 17.
- CMS-specific initiation flags không còn phù hợp.
- Old GC logging options phải được đánh giá lại.
- GC log parser có thể chỉ hiểu CMS.
- SLO hiện tại cần ghi nhận trước khi chuyển.
- Application/server/framework phải hỗ trợ Java 17, độc lập với GC.

### 16.2. Chuyển sang G1 baseline

~~~bash
java \
  -XX:+UseG1GC \
  -Xms2g \
  -Xmx4g \
  -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar orders.jar
~~~

Không copy hai cờ CMS occupancy sang G1. Chưa cần tự đặt `G1HeapRegionSize` hay GC thread counts nếu chưa có bằng chứng.

### 16.3. Chạy test

- Startup với đúng JDK runtime/container image.
- API smoke test.
- Traffic benchmark có số request và payload đại diện.
- Heap pressure test.
- Long-running soak test.
- GC log parser test.
- Error/latency/CPU/RSS comparison.
- Canary và rollback plan.

### 16.4. Kết quả đánh giá có thể khác nhau

**Trường hợp tốt:** G1 giảm những pause dài, p99 API cải thiện, throughput giảm không đáng kể.

**Trường hợp cần tối ưu:** G1 có nhiều mixed pauses, CPU overhead tăng hoặc memory pressure cao; cần phân tích live set, allocation và heap sizing.

**Trường hợp không đạt:** throughput batch giảm vượt ngưỡng; có thể benchmark Parallel GC như một ứng viên được hỗ trợ và chọn phù hợp.

Không tự nhận định “G1 nhanh hơn CMS” cho mọi ứng dụng. Đây là một migration có tiêu chí và dữ liệu cụ thể.

## 17. Ví dụ migration Java 8 Parallel sang Java 21 mặc định

Giả sử batch job Java 8 không có `UseParallelGC` nhưng chạy trên cấu hình mà HotSpot đã chọn Parallel GC.

Khi chuyển sang Java 21 không ghi GC flag, default của HotSpot trong môi trường phù hợp có thể là G1.

Vấn đề không phải một flag bị remove, mà là **thay đổi lựa chọn mặc định**.

### 17.1. Quy trình kiểm chứng

1. Chạy baseline Java 8; ghi collector thực tế.
2. Chạy Java 21 với không có GC flag; ghi collector thực tế.
3. Giữ dataset và CPU/memory limits tương đương.
4. So sánh batch duration, CPU, RSS và GC total time.
5. Nếu cần, thử Java 21 với `-XX:+UseParallelGC`.
6. Chọn collector dựa trên mục tiêu và kiểm thử dài hạn.
7. Cập nhật tài liệu để đội vận hành biết hệ thống đang pin GC hay dùng default.

### 17.2. Đừng chỉ đo thời gian GC

Một job với ít pause hơn chưa chắc hoàn thành nhanh hơn. Concurrent collector có thể tiêu thụ CPU trong lúc ứng dụng chạy. Benchmark tổng throughput mới phản ánh kết quả nghiệp vụ.

Ngược lại, một job kết thúc nhanh hơn vài phần trăm nhưng làm CPU node bị quá tải và ảnh hưởng dịch vụ khác có thể không phải lựa chọn vận hành tốt.

## 18. Ví dụ container: thay JDK làm heap và GC threads đổi

Một service có container memory limit 2 GiB và CPU quota 1 vCPU. Trước đó JVM cũ có hành vi container detection khác bản mới.

Sau khi nâng:

- JVM có thể nhận diện memory limit khác.
- Max heap mặc định có thể đổi.
- GC thread ergonomics thay đổi do active processor count.
- Collector mặc định có thể khác.
- CPU throttling xuất hiện khi concurrent work tăng.
- RSS tiến gần OOMKill dù heap used vẫn dưới `-Xmx`.

### 18.1. Cách phân tích

Ghi ở cả hai runtime:

~~~bash
java -version
java -XX:+PrintCommandLineFlags -version
java -XX:+PrintFlagsFinal -version
~~~

Với JDK hỗ trợ:

~~~bash
java -XshowSettings:system -version
~~~

Kết hợp cgroup/container metrics, GC logs và process RSS. Không chỉ đọc memory limit từ YAML rồi giả định JVM nhìn thấy cùng giá trị.

### 18.2. Hướng giải quyết

- Xác định heap limit phù hợp native headroom.
- Kiểm chứng CPU quota/requests.
- Cân nhắc GC phù hợp tài nguyên.
- Giảm allocation hoặc memory retention nếu cần.
- Đánh giá concurrency/worker thread settings dựa trên đo đạc.
- Chạy load/soak test với đúng resource limits production.

## 19. Các công cụ đo thay vì dựa vào cảm giác

### 19.1. GC logs

Nguồn dữ liệu quan trọng để phân tích pause, heap occupancy, GC reasons và concurrent phases. Cần parser hỗ trợ đúng JDK và collector.

### 19.2. JDK Flight Recorder (JFR)

JFR có thể cung cấp các event liên quan đến:

- GC pauses và phases.
- Allocation.
- Object statistics theo cấu hình.
- CPU/thread activity.
- Lock contention.
- JVM configuration.

Ví dụ với JDK/HotSpot hỗ trợ và môi trường test được phép:

~~~bash
jcmd <pid> JFR.start name=gc-migration settings=profile duration=5m filename=gc-migration.jfr
~~~

Cú pháp, permission và overhead cần được xác minh theo runtime. Đừng bật profile nặng hoặc thu dữ liệu nhạy cảm trong production thiếu phê duyệt.

### 19.3. Micrometer/JMX/OpenTelemetry metrics

Ứng dụng có thể xuất GC metrics từ JVM qua JMX hoặc thư viện monitoring, nhưng tên series/collector có thể khác giữa GC/JDK.

Nếu dashboard alert dùng chuỗi tên như “G1 Young Generation”, chuyển collector làm series đó biến mất. Cần test instrumentation và dashboard sau migration.

### 19.4. OS/container metrics

GC metrics phải đi cùng:

- Process CPU và system CPU.
- Cgroup throttled time.
- RSS.
- Container memory working set.
- Major page faults nếu liên quan.
- Disk I/O và network.
- Pod restart/OOMKilled.
- Node pressure.

Nếu p99 tăng do CPU throttling hoặc database latency, chỉ nhìn GC log có thể dẫn tới chỉnh heap sai hướng.

## 20. Những chỉ số đánh giá GC migration

Một bảng đánh giá có thể như sau (toàn bộ số liệu chỉ minh họa):

| Chỉ số | Baseline | JDK/GC mới | Tiêu chí |
|---|---:|---:|---|
| Throughput (req/s) | 2.500 | 2.480 | Không giảm quá mức được duyệt |
| Application p99 (ms) | 210 | 170 | Nhỏ hơn SLO |
| GC pause p99 (ms) | 95 | 38 | Giảm hoặc đạt ngưỡng |
| GC pause max (ms) | 620 | 180 | Không vượt budget dự kiến |
| Process CPU (%) | 55 | 61 | Không gây throttling |
| Process RSS (GiB) | 2.8 | 3.0 | Còn headroom |
| OOMKilled | 0 | 0 | Không xuất hiện |
| Batch completion | 9m40s | 9m45s | Trong giới hạn chấp nhận |

Không dùng bảng ví dụ này làm threshold chung. SLO và resource budget phải do hệ thống xác định.

### 20.1. Đừng dùng p50 để chứng minh tail latency

Collector có thể khiến median gần như không đổi nhưng vẫn có vài pause rất dài. Với dịch vụ có SLA nghiêm ngặt, cần quan sát p95/p99/max và các request bị timeout.

### 20.2. Đừng xem GC count cao luôn là xấu

Nhiều pause ngắn có thể là hoạt động bình thường của một collector. Cần đo **tổng tác động** lên throughput, latency và footprint, không chỉ số lần.

### 20.3. So sánh phân bố với cùng workload

Trong thời gian benchmark, đảm bảo:

- Số lượng request/s hoặc batch size tương tự.
- Tỉ lệ read/write và payload sizes tương tự.
- Cache warmup tương tự.
- Database/network dependencies ổn định.
- Số replica và autoscaling được kiểm soát.
- JVM warmup/JIT có thời gian phù hợp.
- Không cùng lúc thay business logic lớn.

## 21. Bộ kiểm thử nên có khi chuyển GC

### 21.1. Startup tests

Kiểm tra:

- JVM chấp nhận tất cả flags.
- Collector được lựa chọn đúng.
- Heap/resource settings hợp lệ.
- GC logging hoạt động.
- Không bị cảnh báo legacy flags hoặc sai distribution.
- Server/plugin/Java agent khởi động thành công.

### 21.2. Functionality tests

GC về nguyên tắc phải bảo toàn semantic Java heap, nhưng runtime hoặc native integration lỗi có thể được bộc lộ khi thay JDK:

- API và batch business flows.
- Serialization/database integration.
- JNI/JNA/native libraries nếu dùng.
- Java agents/bytecode instrumentation.
- Plugins và dynamic class loading.
- Reference processing, cleaners và resource lifecycle theo thiết kế.

Không nên dựa vào `System.gc()` như một cơ chế bắt buộc để “dọn tài nguyên nghiệp vụ”. Explicit GC có thể bị bỏ qua hoặc có hành vi khác theo options và collector.

### 21.3. Performance tests

- Steady-state throughput.
- Latency distribution.
- Peak load.
- Heap occupancy/live set.
- Allocation rate.
- GC pause histogram.
- CPU/RSS.
- Soak test nhiều giờ theo yêu cầu.
- Memory limit/CPU throttling behavior.
- Startup/warmup.

### 21.4. Rollback tests

Cần biết liệu có thể:

- Quay về collector khác **trên cùng JDK đích**.
- Quay lại JDK/runtime image trước đó.
- Quay lại server/framework config.
- Khôi phục GC log parser/dashboard.
- Giữ data compatibility nếu rollback artifact.

Rollback GC thường là thay JVM flags và restart, nhưng trong thực tế nó có thể gắn với thay đổi container image/JDK/heap; cần xác nhận quy trình.

## 22. GC config là cấu hình vận hành có version

Mỗi hệ thống nên giữ một hồ sơ:

~~~yaml
service: orders-api
runtime:
  vendor: "Approved OpenJDK-based distribution"
  version: "Target JDK release and update"
deployment:
  type: "container"
  cpu_limit: "Recorded from deployment"
  memory_limit: "Recorded from deployment"
gc:
  selection: "G1"
  explicit_flag: "-XX:+UseG1GC"
  heap_initial: "2g"
  heap_max: "4g"
  logging: "-Xlog:gc*,safepoint:..."
  reason: "Approved after performance comparison"
validation:
  startup: "PASS"
  load_test: "PASS"
  soak_test: "PASS"
  canary: "PENDING"
ownership:
  team: "Platform"
  review_trigger: "Next JDK upgrade"
~~~

Các giá trị là placeholder. Một config thực tế phải có **version và test evidence chính xác**, không chứa bí mật.

### 22.1. Khi nào cần đánh giá lại?

- Nâng major JDK.
- Nâng JDK update có thay GC/ergonomics.
- Chuyển JVM distribution.
- Đổi container CPU/memory limits.
- Đổi workload/dataset lớn.
- Nâng framework làm allocation profile thay đổi.
- Thay logging/monitoring agent.
- Có SLO mới về latency.
- Có cảnh báo GC flags deprecated/obsolete/removed.

## 23. Guardrails trong CI và startup

### 23.1. Kiểm tra legacy flags

Một guardrail đơn giản có thể tìm CMS flags:

~~~bash
rg -n --hidden -- \
  'UseConcMarkSweepGC|UseParNewGC|CMSInitiating|CMSClassUnloadingEnabled' \
  deploy scripts build.gradle pom.xml
~~~

Nếu repository có tài liệu chứa ví dụ CMS, cần giới hạn phạm vi quét thực tế; đừng chặn toàn bộ occurrence trong README.

Một CI check tốt nên đối chiếu allowlist được duyệt và báo lỗi khi một JVM option bị loại vẫn có trong **startup production config**.

### 23.2. Startup smoke test với JDK đích

Thay vì chỉ parse file cấu hình, hãy chạy JVM/runtime đích với đúng flags trong môi trường CI phù hợp để phát hiện cờ không nhận diện.

Với application server, cần thử startup script/server image; không chỉ dùng `java -version` vì server có thể inject flags từ nơi khác.

### 23.3. Không dùng một cờ “ignore unknown options” để qua CI

Giải pháp đó che giấu lỗi compatibility và làm giảm ý nghĩa của startup smoke test. Cần sửa tập flags và ghi kết quả collector thực tế.

## 24. Những sai lầm thường gặp

### 24.1. “Nâng Java tự động cải thiện GC”

Không bảo đảm. JDK mới có thể có nhiều cải tiến, nhưng hiệu quả phụ thuộc workload và tài nguyên. Có trường hợp throughput giảm hoặc footprint tăng.

### 24.2. “Java 17/21 chắc chắn dùng G1 trong mọi trường hợp”

Không tuyệt đối. JVM vendor, flags, tài nguyên và ergonomics có thể ảnh hưởng. Cần xác nhận runtime log.

### 24.3. “CMS bị deprecated nghĩa là vẫn dùng mãi được”

Không đúng. CMS đã bị loại khỏi HotSpot ở JDK 14. Phải bỏ cấu hình liên quan khi chuyển tới JDK đó hoặc sau.

### 24.4. “Parallel GC đã bị bỏ vì G1 trở thành mặc định”

Sai. **Default đổi** khác với **implementation bị loại**. Đừng đánh đồng hai khái niệm.

### 24.5. “Đổi CMS sang G1 rồi giữ CMS flags”

Sai. Collector-specific tuning không áp dụng nguyên vẹn cho collector khác và có thể phá startup.

### 24.6. “-XX:MaxGCPauseMillis là giới hạn pause tối đa”

Sai. Đây là mục tiêu điều chỉnh, không phải SLA hard bound.

### 24.7. “ZGC không có stop-the-world pause”

Nói vậy là quá tuyệt đối. ZGC thiết kế pause rất ngắn, nhưng hệ thống vẫn có các safepoint/stop-the-world activities trong phạm vi kỹ thuật tương ứng. Không được khẳng định thời gian dừng bằng 0.

### 24.8. “Collector low-pause luôn dùng ít CPU hơn”

Không nhất thiết. Concurrent GC cần CPU headroom và có trade-off throughput/memory riêng.

### 24.9. “Xmx bằng container memory limit là an toàn”

Không. Process còn native memory, thread stacks, code cache, GC structures và nhiều thứ khác.

### 24.10. “GC log cũ vẫn được parser mới tự hiểu”

Không thể mặc định. Unified Logging, tags, levels và event structure khác nhau giữa GC/JDK.

### 24.11. “JDK mới không chạy vì code Java sai”

Một startup failure có thể xảy ra **trước khi main() chạy** do unsupported JVM option. Cần xem lỗi launcher.

### 24.12. “Đổi collector chữa được memory leak”

Không. Nếu ứng dụng vẫn giữ reference, GC không được tự thu hồi object đó.

### 24.13. “Chỉ cần benchmark một lần”

Không đủ. JVM warmup/JIT, load variability và environment noise có thể ảnh hưởng kết quả. Nên chạy lặp và xem phân bố.

### 24.14. “MXBean name là API portable để chọn GC”

Không. Tên collector MXBeans là implementation-specific, không nên hardcode logic nghiệp vụ.

### 24.15. “Cùng major JDK sẽ có mọi GC giống nhau”

Không chắc, đặc biệt giữa HotSpot/OpenJ9, custom builds, OS/CPU khác nhau và GC feature changes.

## 25. Checklist migration GC

### Trước khi nâng

- [ ] Đã ghi JVM vendor, version, update và platform.
- [ ] Đã xác nhận collector đang chạy thực tế.
- [ ] Đã ghi mọi GC-related startup flags.
- [ ] Đã tìm flags từ Docker/Kubernetes/server/CI/test.
- [ ] Đã ghi heap sizing, CPU/memory limits và cgroup.
- [ ] Đã thu GC logs và application p99/throughput baseline.
- [ ] Đã xác định SLO và tiêu chí rollback.

### Compatibility của JDK đích

- [ ] Đã kiểm tra collector mong muốn được runtime hỗ trợ.
- [ ] Đã loại CMS/legacy flags bị bỏ.
- [ ] Đã phân biệt deprecated và removed.
- [ ] Đã kiểm tra cờ logging mới/legacy.
- [ ] Đã xác nhận bộ parser GC log/monitoring hỗ trợ format mới.
- [ ] Đã chạy startup smoke test với đúng JVM flags.
- [ ] Đã đối chiếu heap/GC thread ergonomics dưới container limits.

### Performance và chức năng

- [ ] Đã chạy functional regression tests.
- [ ] Đã đo throughput, latency p95/p99/max.
- [ ] Đã phân tích pause STW và concurrent GC overhead.
- [ ] Đã theo dõi RSS/native memory và CPU throttling.
- [ ] Đã chạy workload có allocation pressure đại diện.
- [ ] Đã chạy soak test và peak-load test nếu hệ thống yêu cầu.
- [ ] Đã kiểm tra agent/native integration và plugins nếu có.
- [ ] Đã chạy canary trước rollout rộng.

### Hoàn tất

- [ ] Đã cập nhật JVM flags ở mọi môi trường cần thay.
- [ ] Đã xác nhận collector thực tế sau deploy.
- [ ] Đã cập nhật startup scripts, Helm/Docker/service configs.
- [ ] Đã lưu benchmark evidence theo artifact/JDK/GC.
- [ ] Đã thêm guardrail không tái đưa CMS flags trở lại.
- [ ] Đã cập nhật runbook quan sát và rollback.
- [ ] Đã gắn owner và lịch đánh giá lại khi nâng JDK tiếp theo.

## Kết luận

**Collector mặc định** và **collector còn được hỗ trợ** là hai câu hỏi khác nhau. G1 trở thành mặc định phổ biến của HotSpot từ JDK 9 theo JEP 248; điều đó không đồng nghĩa Parallel GC biến mất. Trái lại, CMS đã bị deprecated từ JDK 9 và bị loại bỏ trong JDK 14, khiến các startup flags legacy có thể làm ứng dụng không khởi động trên JDK mới.

Một quy trình chuyển đổi Java đáng tin cậy phải: **ghi nhận GC thực tế và toàn bộ flags → loại bỏ tùy chọn không còn hỗ trợ → chọn collector phù hợp workload → cập nhật GC logging → kiểm chứng hiệu năng, heap và container limits → triển khai có giám sát và rollback**. Tính tương thích JVM không chỉ được đo bằng việc bytecode có chạy, mà còn ở việc ứng dụng giữ được throughput, latency, memory headroom và độ ổn định đáp ứng yêu cầu vận hành.

