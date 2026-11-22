# Thu gom đồng thời với các luồng ứng dụng trong GC độ trễ thấp (Java)

**Concurrent garbage collection** (*thu gom rác đồng thời*) là cơ chế cho phép **một phần đáng kể công việc của bộ thu gom rác (GC) diễn ra trong khi các luồng Java của ứng dụng vẫn tiếp tục chạy**. Đây là một trong những cách quan trọng để giảm các lần tạm dừng do GC và cải thiện độ trễ, nhất là **p95/p99/p99.9 response time** của dịch vụ có yêu cầu phản hồi đều đặn.

Trong ngữ cảnh **Java 15**, **ZGC (JEP 377)** và **Shenandoah (JEP 379)** đạt trạng thái dùng cho production trong các bản dựng có hỗ trợ chúng. Những bộ thu gom này thực hiện nhiều công đoạn khó như đánh dấu đối tượng còn sống và/hoặc di chuyển đối tượng **đồng thời với luồng ứng dụng**. **G1** cũng có pha đánh dấu đồng thời, nhưng vẫn chủ yếu thực hiện giải phóng vùng nhớ bằng **stop-the-world evacuation pauses**. Cả ba vẫn là lựa chọn có ý nghĩa trong Java hiện đại; chi tiết triển khai đã tiếp tục phát triển qua những bản JDK mới.

**Điểm cốt lõi:** *concurrent* **không có nghĩa mọi bước GC đều không tạm dừng ứng dụng**, và *low-latency* **không bảo đảm request không bao giờ chậm**. CPU tranh chấp, bộ nhớ thiếu, allocation stall, full/degenerate collection, safepoint khác và I/O có thể tạo độ trễ dù các pha GC thông thường rất ngắn.

## 1. Mutator, collector và stop-the-world

Trong thuật ngữ GC, **mutator** là luồng ứng dụng đang đọc/ghi object graph: tạo đối tượng, thay đổi tham chiếu, xử lý request, tính toán và cập nhật dữ liệu. **Collector** là phần runtime kiểm tra đối tượng còn reachable và thu hồi vùng nhớ không còn dùng.

Ví dụ:

```java
class Order {
    Object currentCustomer;
}

Order order = new Order();
order.currentCustomer = new Object();
order.currentCustomer = new Object(); // Thay đổi cạnh trong object graph.
```

Đây là mã minh họa, không phải chương trình có `main`. Dòng gán thứ hai thay đổi một tham chiếu. Nếu GC đang quét đồ thị đối tượng **cùng lúc**, nó phải bảo đảm không nhầm một object vẫn còn reachable là garbage chỉ vì các luồng ứng dụng vừa thay đổi graph.

Ba khái niệm cần tách biệt:

| Thuật ngữ | Nghĩa chính xác |
| --- | --- |
| **Stop-the-world (STW)** | Tạm dừng các luồng Java ứng dụng tại một điểm đồng bộ để JVM thực hiện công việc như GC |
| **Parallel GC work** | Nhiều **GC worker threads** cùng thực hiện công việc; ứng dụng **có thể vẫn bị dừng** |
| **Concurrent GC work** | GC làm việc **đồng thời với mutator threads đang chạy**; CPU, memory bandwidth được chia sẻ |

Một bộ thu gom có thể vừa **parallel** vừa **concurrent**, nhưng không phải hai khái niệm đồng nghĩa. Ví dụ G1 dùng nhiều GC worker song song trong những lần STW evacuation và cũng đánh dấu heap đồng thời ngoài các khoảng dừng ấy.

### Hình dung về timeline

```text
Thời gian ------------------------------------------------------------>

STW-focused:
Ứng dụng    RUN -------| PAUSE GC |------- RUN ------| PAUSE GC |----
Collector               [ GC workers ]                 [ GC workers ]

Mostly concurrent:
Ứng dụng    RUN --|P|-------------------- RUN -----|P|----- RUN ------
Collector        [concurrent mark ...]              [other GC phases]

Low-pause concurrent:
Ứng dụng    RUN --|p|--- RUN ---|p|---- RUN -----|p|--- RUN ----------
Collector       [mark + relocate + remap phần lớn concurrent]
```

`|P|` hoặc `|p|` chỉ **điểm dừng minh họa**, không phải cam kết rằng các pha, số lần hay độ dài pause của một collector luôn đúng như hình. Một chu kỳ GC thực tế có thể chứa nhiều pha đồng thời và nhiều điểm đồng bộ ngắn, và các trường hợp thiếu bộ nhớ có thể làm hành vi khác đáng kể.

**Kết luận:** mục tiêu của low-latency GC là **chuyển công việc tốn thời gian ra khỏi khoảng STW**, không xóa bỏ mọi hoạt động GC hay mọi loại pause của JVM.

## 2. Vì sao GC có thể chạy cùng lúc với ứng dụng?

Một GC cần xác định những đối tượng nào **còn sống** bằng cách theo dõi đường tham chiếu từ **GC roots** như stack, static references và các roots khác của runtime. Nhưng trong lúc collector đi qua object graph, mutator có thể:

1. Cấp phát đối tượng mới.
2. Thay một field từ tham chiếu A sang B.
3. Xóa một tham chiếu để object cũ trở nên unreachable.
4. Chuyển một object sang cấu trúc dữ liệu khác.
5. Truy cập object trong lúc GC đang di chuyển nó.

Nếu GC chạy hoàn toàn đồng thời mà **không có giao thức phối hợp**, nó có thể bỏ sót một tham chiếu còn sống, dẫn tới lỗi an toàn bộ nhớ. JVM vì thế sử dụng **barriers, metadata và các điểm đồng bộ** để duy trì tính đúng đắn.

### Read/write barriers

**Barrier** trong ngữ cảnh GC là đoạn công việc do JVM/compiler/runtime chèn quanh một số thao tác truy cập tham chiếu. Nó **không** có nghĩa là một hàng rào đồng bộ Java như `synchronized` hay một lời gọi method do lập trình viên phải tự viết.

- **Write barrier:** khi code thay đổi một tham chiếu, JVM có thể ghi nhận tham chiếu cũ/mới hoặc cập nhật metadata để collector không bỏ sót các cạnh cần xét.
- **Load/read barrier:** khi code lấy một tham chiếu để sử dụng, JVM có thể kiểm tra trạng thái object/reference, phục vụ relocation hoặc forwarding nếu collector cần.
- **Remembered sets / card tables:** lưu dấu tham chiếu giữa các vùng hoặc thế hệ heap, tránh phải quét toàn bộ heap cho mỗi collection.
- **Safepoints/handshakes:** những cơ chế runtime có thể dừng hoặc phối hợp với một số luồng trong thời gian ngắn khi phải kiểm tra roots, hoàn tất một pha hoặc đảm bảo trạng thái nhất quán.

Những chi tiết cụ thể **khác nhau giữa ZGC, Shenandoah và G1, đồng thời thay đổi giữa các JDK**. Đừng suy từ một ví dụ barrier rằng mọi collector chèn cùng một lệnh ở cùng một vị trí.

### Snapshot-at-the-beginning (SATB)

Một kỹ thuật thường gặp ở các collector như G1 và các mode Shenandoah là **SATB**: collector xử lý một ảnh chụp logic của các đối tượng reachable tại đầu chu kỳ marking, dù ứng dụng tiếp tục đổi tham chiếu.

Ví dụ khi một object A còn reachable tại đầu marking nhưng ứng dụng sau đó xóa tham chiếu cuối cùng, collector có thể **tạm giữ A là live trong chu kỳ hiện tại** để bảo đảm an toàn. Lần GC sau mới thu hồi A.

Hệ quả:

- Collector **không nhất thiết thu hồi mọi object vừa trở nên unreachable ngay trong chu kỳ đó**.
- Cần thêm metadata/barriers để giải quyết những thay đổi trong lúc concurrent marking.
- Có thể xuất hiện **floating garbage** — object đã chết nhưng vẫn chưa được thu hồi do thời điểm chụp logic.
- Đây là trade-off thiết kế có chủ ý nhằm tránh phải dừng toàn bộ ứng dụng lâu để chụp một heap snapshot vật lý.

**Không hiểu SATB là sao chép toàn bộ heap vào một bản snapshot riêng.** Nó là cách định nghĩa và duy trì một tập live logic trong lúc heap liên tục thay đổi.

## 3. G1: đồng thời đánh dấu, nhưng evacuation vẫn STW

**Garbage-First (G1)** là bộ thu gom mặc định trên phần lớn HotSpot server-class configurations. G1 tập trung vào throughput tương đối tốt và các mục tiêu pause time có xác suất đạt cao, đồng thời có **concurrent marking** để xác định live objects ở các old-generation regions.

Một vòng làm việc điển hình:

```text
Young collections (STW)
         |
         v
Concurrent Start (có một pause)
         |
         v
Concurrent root/heap marking <---- ứng dụng vẫn chạy
         |
         v
Remark/Cleanup (có các pause)
         |
         v
Mixed collections: evacuate vùng young + old phù hợp (STW)
```

Trong G1:

- **Concurrent mark** tìm đối tượng còn reachable trong lúc mutator tiếp tục chạy.
- **Young/Mixed evacuation pauses** vẫn tạm dừng các luồng ứng dụng để di chuyển object của collection set.
- Các pha **Remark** và một phần **Cleanup** có thể có STW synchronization.
- Nếu tình trạng bộ nhớ nghiêm trọng, G1 có thể cần một **Full GC** với thời gian dừng dài hơn.
- `-XX:MaxGCPauseMillis=...` là **mục tiêu mềm**, không phải upper bound tuyệt đối cho pause.

Vì vậy G1 là **mostly concurrent**, không nên mô tả G1 như một collector mà mọi bước thu hồi đều diễn ra đồng thời. Nếu yêu cầu ứng dụng là p99 <escape><</escape>10 ms, cần đo cả **tổng latency** và pause thực tế trước khi kết luận G1 có đáp ứng hay không.

Khi ứng dụng có nhu cầu về throughput lớn và deadline GC không quá chặt, G1 thường là baseline tốt để so sánh trước khi cân nhắc ZGC/Shenandoah.

## 4. ZGC: chuyển phần việc nặng sang concurrent phases

**ZGC (Z Garbage Collector)** được thiết kế cho **low pause time** và heap lớn. Từ Java 15, **JEP 377** đưa ZGC ra khỏi trạng thái experimental để sẵn sàng cho production trong các bản HotSpot hỗ trợ. Nhiều thao tác đánh dấu, relocation và quản lý vùng nhớ có thể diễn ra **trong khi mutators tiếp tục thực thi**; chỉ còn những khoảng đồng bộ ngắn.

Ý tưởng công nghệ ở mức khái niệm:

1. Runtime tổ chức heap và thông tin trạng thái object/reference phục vụ tracing và relocation.
2. Các **barrier và metadata** cho phép Java code vẫn sử dụng tham chiếu an toàn trong lúc GC cập nhật trạng thái.
3. Collector chạy nhiều pha đánh dấu/di chuyển **cùng lúc với ứng dụng**.
4. Một số thời điểm phối hợp roots hoặc chuyển pha vẫn cần pause hoặc handshake.
5. Memory bị thu hồi/tái sử dụng khi collector chứng minh an toàn, không nhất thiết đúng thời điểm object vừa mất tham chiếu cuối.

**Không phải mọi thao tác Java đều có barrier giống nhau**, và các chi tiết về colored pointers, barriers hay cách tổ chức generations phụ thuộc bản JDK. Khi học cơ chế, tập trung vào bất biến: **ứng dụng được nhìn thấy một mô hình object graph hợp lệ trong lúc collector làm việc**.

### Các mốc còn quan trọng

| Phiên bản | Thay đổi | Điều cần nhớ |
| --- | --- | --- |
| Java 15 — JEP 377 | ZGC chính thức là collector production | Chọn bằng `-XX:+UseZGC`, không cần cờ mở khóa experimental trước đây |
| Java 21 — JEP 439 | Generational ZGC được đưa vào để tối ưu đối tượng có vòng đời ngắn | Bước phát triển của ZGC, không phải mọi JDK cũ có cùng cơ chế |
| Java 23 — JEP 474 | Generational mode trở thành mặc định cho ZGC | Đánh dấu sự chuyển đổi hành vi mặc định |
| **Java 24 — JEP 490** | Loại bỏ **non-generational ZGC** | ZGC hiện đại chỉ có generational mode; `ZGenerational` option đã bị loại bỏ |

**Không đưa `-XX:+ZGenerational` hoặc `-XX:-ZGenerational` vào một hướng dẫn chạy ZGC trên JDK 24+**. Những câu lệnh đó thuộc một giai đoạn chuyển đổi cũ và không còn là cấu hình đúng trong runtime hiện đại. Để bật ZGC trên JDK hiện nay, bắt đầu bằng:

```bash
java -XX:+UseZGC -Xmx2g -jar app.jar
```

`app.jar` là tên minh họa cho ứng dụng của bạn; không phải file đi kèm bài. Cờ `-Xmx2g` chỉ là ví dụ, **không phải kích thước heap được khuyến nghị cho mọi workload**.

### Heap headroom là điều kiện thiết yếu

Collector concurrent thu hồi rác **trong lúc ứng dụng vẫn cấp phát**. Nếu tốc độ cấp phát nhanh hơn tốc độ thu hồi và heap không đủ chỗ, application thread có thể bị buộc chờ collector — **allocation stall**. Điều này có thể xảy ra **ngay cả khi log GC pause thông thường cực ngắn**.

Một heap ZGC phải đủ chứa:

- **Live set**: những object vẫn reachable và phải giữ lại.
- **Headroom cho cấp phát mới** khi concurrent collection chưa hoàn tất.
- Tài nguyên cho những giai đoạn relocation và metadata/collector overhead phù hợp.
- Khả năng hấp thụ allocation burst của workload.

Thực hành tốt là đo live set, allocation rate, event stalls và RSS/container memory cùng lúc. Không chỉ đặt `-Xmx` bằng live-set size rồi mong GC “tự thu hồi tức thì”.

## 5. Shenandoah: concurrent marking và concurrent evacuation

**Shenandoah** là collector hướng tới **độ trễ thấp**, nổi bật ở khả năng thực hiện cả đánh dấu lẫn di chuyển/thu hồi object theo mô hình concurrent trong khi ứng dụng vẫn chạy. **JEP 379** đưa Shenandoah thành tính năng production trong **OpenJDK 15**; tuy nhiên **khả năng có sẵn của nó phụ thuộc nhà phân phối JDK, hệ điều hành và bản dựng JVM**.

Một ý tưởng về các pha trong triển khai Shenandoah SATB truyền thống:

```text
Start / Initial Mark (có phối hợp ngắn)
       |
       v
Concurrent Marking ----------> mutator vẫn làm việc
       |
       v
Final Mark (một pause ngắn)
       |
       v
Concurrent Evacuation -------> mutator vẫn truy cập object
       |
       v
Concurrent Reference Update và cleanup theo cơ chế của mode
       |
       v
Sẵn sàng chu kỳ kế tiếp
```

Sơ đồ là **mô hình học tập**, không phải danh sách pha cứng cho mọi mode và mọi phiên bản. Các biến thể Shenandoah có thể khác nhau về barriers và cách cập nhật tham chiếu.

**JDK 25 — JEP 521** bổ sung **Generational Shenandoah** như một tính năng chính thức, phù hợp với workload có nhiều object ngắn hạn. Trên bản JDK 25+ **có hỗ trợ Shenandoah**, có thể thử:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xmx2g -jar app.jar
```

Đây là ví dụ lựa chọn collector cho ứng dụng đã có; **không phải** câu lệnh cho JDK 17 hoặc Java 15. Một bản JDK không tích hợp Shenandoah có thể từ chối cờ. Nếu chạy JDK 17 hoặc một bản cũ hơn, hãy dùng chế độ Shenandoah được runtime đó hỗ trợ chứ không bê nguyên các flag của JDK 25.

Khi bật Shenandoah cơ bản trên một runtime có hỗ trợ:

```bash
java -XX:+UseShenandoahGC -Xmx2g -jar app.jar
```

**Không nhầm Shenandoah với một collector “không bao giờ STW”.** Nó vẫn có các điểm đồng bộ; khi bộ nhớ cạn hoặc collector không theo kịp mutator, có thể xuất hiện **degenerated/full collection hoặc allocation pressure**, tùy mode và phiên bản.

## 6. So sánh tính concurrent và ưu tiên thiết kế

| Tiêu chí | G1 | ZGC hiện đại | Shenandoah |
| --- | --- | --- | --- |
| Mục tiêu nổi bật | Cân bằng throughput và pause goal | Giảm GC pause rất thấp, scale heap | Giảm GC pause qua công việc concurrent |
| Marking | Có concurrent marking | Phần lớn concurrent | Phần lớn concurrent |
| Evacuation đối tượng | **Chủ yếu STW** cho young/mixed | Có concurrent relocation | Có concurrent evacuation |
| Stop-the-world | Có; evacuation là phần quan trọng | Có các pause/synchronization ngắn | Có các pause/synchronization ngắn |
| CPU của collector | Tranh chấp ở concurrent phases; STW có GC workers | Concurrent threads chia sẻ CPU với mutators | Concurrent threads chia sẻ CPU với mutators |
| Heap headroom | Cần phù hợp live set/allocation | Rất quan trọng khi GC chạy song song cấp phát | Rất quan trọng với concurrent evacuation |
| Khi GC không theo kịp | Evacuation failure / Full GC có thể xảy ra | Allocation stalls, pressure và lỗi thiếu bộ nhớ có thể xảy ra | Degenerated/full collection hoặc các cơ chế fallback |
| Khả dụng | Thường có mặc định trong HotSpot | Phụ thuộc bản dựng/platform | Phụ thuộc bản dựng/platform nhiều hơn |
| Mốc Java 15 | Đã có | JEP 377 production | JEP 379 production trong OpenJDK |

Bảng là **định hướng**, không có ý nghĩa “ZGC luôn nhanh nhất” hoặc “Shenandoah luôn cần ít bộ nhớ nhất”. Kết quả thực tế phụ thuộc **live set, allocation rate, heap size, CPU quota, workload, build và hệ điều hành**.

### Khi nào cân nhắc?

- **Dịch vụ online nhạy cảm tail latency:** thử ZGC/Shenandoah nếu p99 bị tác động mạnh bởi GC pause và có CPU/RAM headroom phù hợp.
- **Batch throughput và không có SLO rất thấp:** G1 hoặc Parallel GC có thể đem lại tổng throughput/chi phí tốt hơn; phải benchmark.
- **Container bị giới hạn CPU mạnh:** GC concurrent cạnh tranh CPU với mutators, có thể giảm latency thực tế hoặc làm task chậm nếu thiếu quota.
- **Ứng dụng ít cấp phát:** thay đổi collector chưa chắc cải thiện rõ; điều chỉnh code hoặc xử lý I/O mới là vấn đề chính.
- **Workload tạo nhiều object ngắn hạn:** generational collector có thể giảm công việc quét không cần thiết; cần kiểm tra mode và JDK thực tế.

## 7. Ví dụ Java 17+ có thể chạy: quan sát mutator và GC activity

Chương trình **không tự triển khai thuật toán GC**. Java runtime thực hiện GC; mã chỉ tạo workload dễ kích hoạt GC và một luồng ứng dụng chạy đồng thời để **quan sát**:

1. Một luồng mutator tăng bộ đếm `AtomicLong`.
2. Luồng `main` liên tục cấp phát nhiều `byte[]` ngắn hạn.
3. `byte[][] recent` giữ một cửa sổ nhỏ các object; các phần tử bị thay thế dần có cơ hội được GC thu hồi.
4. `GarbageCollectorMXBean.getCollectionCount()` đọc bộ đếm những lần collection mà JVM công bố.
5. Chương trình in các thông tin cơ bản; **GC log mới là nơi xem các pha concurrent/STW**.

**Giới hạn giải thích rất quan trọng:** việc bộ đếm mutator tăng trong khoảng cấp phát và bộ đếm GC tăng **không đủ để chứng minh một pha GC cụ thể đã chồng lên một công việc ứng dụng nào tại từng thời điểm**. Muốn xác định các pha thật, phải xem GC logs/JFR và phân tích timestamp.

Lưu file **`ConcurrentGcDemo.java`** ở UTF-8:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public class ConcurrentGcDemo {
    private static long collectionCount() {
        long total = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long n = bean.getCollectionCount();
            if (n > 0) {
                total += n;
            }
        }
        return total;
    }

    public static void main(String[] args) throws Exception {
        AtomicBoolean running = new AtomicBoolean(true);
        AtomicLong work = new AtomicLong();
        CountDownLatch started = new CountDownLatch(1);

        Thread background = new Thread(() -> {
            started.countDown();
            while (running.get()) {
                long n = work.incrementAndGet();
                if ((n & 4095L) == 0) {
                    Thread.yield();
                }
            }
        }, "application-mutator");

        background.start();
        started.await();

        long beforeWork = work.get();
        long beforeGc = collectionCount();

        byte[][] recent = new byte[128][];
        for (int i = 0; i < 64_000; i++) {
            byte[] block = new byte[8192];
            block[0] = (byte) i;
            recent[i % recent.length] = block;
        }

        long afterWork = work.get();
        long afterGc = collectionCount();
        running.set(false);
        background.join();

        System.out.println("allocatedMiB=500");
        System.out.println("mutatorProgressed=" + (afterWork > beforeWork));
        System.out.println("retainedSlots=" + recent.length);
        System.out.println("gcDetected=" + (afterGc > beforeGc));
        System.out.println("gcBeansPresent=" +
                !ManagementFactory.getGarbageCollectorMXBeans().isEmpty());
    }
}
```

### Biên dịch và chạy với các collector

Ví dụ trên **Java 17+** dùng API chuẩn và không cần thư viện ngoài:

```bash
javac -encoding UTF-8 ConcurrentGcDemo.java

java -Xms128m -Xmx128m -XX:+UseZGC -Xlog:gc ConcurrentGcDemo

java -Xms128m -Xmx128m -XX:+UseG1GC -Xlog:gc ConcurrentGcDemo

java -Xms128m -Xmx128m -XX:+UseShenandoahGC -Xlog:gc ConcurrentGcDemo
```

Các lệnh là các **lượt chạy tách biệt**, không phải bật ba collector cùng lúc. Lệnh Shenandoah cần bản JDK có tích hợp collector đó. `-Xms128m -Xmx128m` là **heap nhỏ có chủ đích để dễ kích hoạt GC trong demo**, **không phải** cấu hình khuyến nghị cho một ứng dụng production đang có mức cấp phát tương tự.

**Đầu ra từ các lượt chạy đã kiểm chứng trên JDK 24** với ZGC, G1 và Shenandoah:

```text
allocatedMiB=500
mutatorProgressed=true
retainedSlots=128
gcDetected=true
gcBeansPresent=true
```

Các giá trị trong demo đã được xác minh với cấu hình trên. Tuy nhiên:

- `allocatedMiB=500` là **tổng dữ liệu mảng 64.000 × 8 KiB đã cấp phát**, không phải 500 MiB đang còn live hoặc 500 MiB RSS.
- `retainedSlots=128` là **số slot của mảng tham chiếu**, không chứng minh tất cả các object cũ còn sống; đa số mảng được thay thế trở nên có thể thu gom.
- `mutatorProgressed=true` cho thấy luồng nền được chạy trong khoảng công việc; không phải phép đo thời gian tạm dừng GC.
- `gcDetected=true` cho thấy các GC MXBeans đã ghi nhận collection trong lượt chạy. Tần suất GC **không cố định**; trên heap lớn hơn, một JVM khác hoặc một lần chạy quá nhanh, kết quả có thể khác.
- `gcBeansPresent=true` cho thấy runtime cung cấp GC management beans; số bean và cách tính collection tùy triển khai.
- `GarbageCollectorMXBean.getCollectionCount()` có thể trả `-1` nếu count không được hỗ trợ; demo bỏ qua giá trị âm. Counters không đủ thay cho detailed GC event logs.

Chương trình chủ đích là **minh họa và quan sát**, không phải benchmark chính thức để so throughput hay pause p99. Để benchmark, cần warmup, nhiều lần chạy, tải ổn định, phân phối request latency và số liệu CPU/RAM/container.

## 8. Đọc GC log để phân biệt pause với concurrent work

Bật **Unified Logging** của HotSpot:

```bash
java -Xms128m -Xmx128m -XX:+UseZGC -Xlog:gc*:file=zgc.log:uptime,level,tags ConcurrentGcDemo

java -Xms128m -Xmx128m -XX:+UseG1GC -Xlog:gc*:file=g1.log:uptime,level,tags ConcurrentGcDemo
```

`gc*:file=...` ghi những sự kiện GC và pha có tag liên quan vào file; cú pháp thuộc JVM HotSpot, không phải API Java language. Với Shenandoah (nếu hỗ trợ), đổi `-XX:+UseZGC` thành `-XX:+UseShenandoahGC` và chọn file log khác.

Ví dụ một phần log **từng quan sát trên JDK 24** với ZGC:

```text
[0.009s][info][gc] Using The Z Garbage Collector
[0.061s][info][gc] GC(0) Major Collection (Warmup)
[0.145s][info][gc] GC(1) Minor Collection (High Usage)
[0.148s][info][gc] Allocation Stall (main) 47.105ms
```

Các timestamp và thời lượng trên là **số quan sát của một lần chạy**, không phải output cố định hay giới hạn độ trễ của ZGC. Đặc biệt, dòng **`Allocation Stall (main)`** xảy ra khi luồng ứng dụng không còn đủ chỗ cấp phát trong lúc collector đang làm việc; nó nhắc ta rằng **một concurrent collector không bảo đảm request luôn không bị chặn**.

Một đoạn log G1 khác:

```text
[0.007s][info][gc] Using G1
[0.061s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 48M->2M(128M) 1.022ms
```

`Pause Young (Normal) (G1 Evacuation Pause)` thể hiện một STW collection. G1 còn có những log `Concurrent Mark Cycle` ở workload kích hoạt old-generation marking; chương trình demo chủ yếu tạo object ngắn hạn nên **không bắt buộc** sinh ra chu kỳ marking old-generation ở mọi lần chạy.

Khi xem log đầy đủ, tìm những nhóm thông tin như:

| Dấu hiệu | Diễn giải |
| --- | --- |
| `Using ...` | Collector thực sự được runtime khởi động |
| `Pause ...` | Một event ghi nhận khoảng GC stop-the-world hoặc một pause phase |
| `Concurrent ...` | Một pha GC chạy đồng thời với Java threads theo cơ chế collector |
| `Allocation Stall` | Mutator bị chờ vì áp lực cấp phát/GC không theo kịp |
| `Full GC`, `Degenerated GC` hoặc fallback tương tự | Tình huống cần điều tra về pressure và latency, tên cụ thể tùy collector |
| `before->after(capacity)` | Heap usage trước/sau event, không phải toàn bộ RSS của tiến trình |

**Phân biệt ba dạng thời gian:** thời lượng **pha concurrent** (GC làm việc cùng ứng dụng), thời lượng **GC pause** (ứng dụng dừng) và **application response latency** (toàn bộ thời gian request, gồm CPU, queueing, locks, GC, I/O). Một pha concurrent kéo dài 100 ms **không đồng nghĩa** ứng dụng bị dừng 100 ms.

## 9. Đo và tối ưu đúng chỉ tiêu

Một hệ thống có SLO đòi hỏi p99 response <escape><</escape>50 ms không nên chọn GC chỉ vì một thông điệp quảng cáo “pause dưới 1 ms”. Cần đo:

1. **GC pause duration và percentile:** p50/p95/p99/max của các pause, theo collector và JDK thực tế.
2. **Mutator allocation rate:** MiB/s hoặc GiB/s, đặc biệt spike khi nhận batch/request lớn.
3. **Live set và heap occupancy:** bao nhiêu memory phải giữ; collector có đủ headroom để bắt kịp không?
4. **Allocation stalls và GC fallback:** có luồng ứng dụng phải chờ GC hoặc Full GC do pressure không?
5. **Throughput và CPU utilization:** concurrent GC dùng CPU cạnh tranh với request handlers.
6. **Process RSS/container memory:** `-Xmx` không bao gồm mọi native allocation, thread stacks, JIT code cache và metadata.
7. **End-to-end latency:** bao gồm queueing, scheduling, locks, DB/network, safepoint khác và GC pauses.
8. **Heap resize/commit/uncommit:** có thể ảnh hưởng latency do hoạt động cấp phát/trả memory với OS.
9. **Tình huống worst-case:** đột biến traffic, service startup, full heap, phụ thuộc JNI/native hay cgroup CPU quota.

Có thể dùng **Java Flight Recorder (JFR)**, GC unified logs, `jcmd` và hệ thống metrics để quan sát. Với production, lưu GC log có rotation và giới hạn dung lượng, tránh bật mức `trace` quá chi tiết cho thời gian dài mà chưa đánh giá overhead.

### Hướng điều chỉnh từ ít rủi ro đến nhiều rủi ro

- **Đo trước rồi mới đổi collector.** Ghi baseline workload, CPU/RAM/SLO, bản JDK và các JVM flags.
- Giảm **allocation rate** bằng thiết kế dữ liệu hợp lý; tránh tạo hàng triệu object tạm vô ích trong hot path.
- Giảm **live set** và memory retention ngoài dự kiến: cache vô hạn, listener không gỡ, map giữ key dài hạn.
- Đảm bảo **heap headroom** cho concurrent collector. Với ZGC, `-Xmx` thường là tham số tuning quan trọng.
- Kiểm tra **CPU quota**, số core và tình trạng tranh chấp CPU giữa mutator/GC worker threads.
- Xem xét `-Xms`, `-Xmx` và chiến lược commit/uncommit phù hợp latency-memory trade-off. Không mặc định `Xms=Xmx` luôn tốt; đó là trade-off có thể giúp tránh một số hành động cấp phát memory động nhưng tăng mức chiếm RAM.
- Tránh gọi `System.gc()` trong hot path để “bắt rác chạy ngay”; lời gọi explicit có thể thay đổi hành vi/độ trễ và không bảo đảm memory được giải phóng ngay.
- Nếu cần đổi collector, **A/B test** với cùng ứng dụng và workload, nhiều lần chạy sau warmup.

**Không nên tối ưu GC bằng cách tự điều chỉnh `ConcGCThreads`, barriers hoặc các flags chuyên sâu trước khi có số liệu.** Các bộ thu gom hiện đại có ergonomic heuristics; can thiệp quá sớm có thể giảm throughput và làm tăng latency.

## 10. Các tình huống concurrent GC vẫn chậm

### 10.1. Allocation rate cao hơn reclamation

Nếu hệ thống cấp phát 2 GiB/s nhưng collector không thu hồi đủ nhanh và heap thiếu headroom, các thread có thể bị **allocation stall**. ZGC log có thể cho thấy pause GC ngắn nhưng một request vẫn chậm. Cách xử lý: kiểm tra allocation rate, live set, heap limit, CPU và burst pattern; **không chỉ** nhìn average GC pause.

### 10.2. CPU bị tranh chấp

Collector concurrent phải chiếm CPU. Trong container chỉ có 1–2 CPU quota, ứng dụng và GC có thể cùng tranh nhau thời gian xử lý. P99 application latency có thể xấu đi dù số lần STW giảm.

### 10.3. Áp lực từ object sống lâu và cache

Một cache giữ nhiều object reachable làm **live set lớn**, giảm khả năng thu hồi. Đổi collector không sửa được thiết kế cache giữ tham chiếu quá lâu. Cần kiểm tra retention paths, TTL/size bounds và dữ liệu không còn cần.

### 10.4. Các pause không do GC

JVM có thể có safepoints vì lý do khác; application thread còn có thể block vì I/O, lock contention, page faults, scheduler, DNS, disk và network. GC pause p99 đẹp không đồng nghĩa request p99 đẹp.

### 10.5. Fallback của collector

Dưới áp lực heap cao hoặc điều kiện bất lợi, collector có thể chọn cơ chế đặc biệt như allocation stall, degenerated/full collection hoặc out-of-memory. **Chọn low-pause collector không xóa luật rằng heap hữu hạn.** Khi thiếu bộ nhớ, cần tối ưu workload/heap chứ không cố “tắt STW bằng một flag”.

## 11. Không nhầm concurrent với generational

Hai chiều thiết kế **độc lập về ý nghĩa**:

- **Concurrent vs STW:** công việc GC có được thực hiện khi mutators vẫn chạy không?
- **Generational vs non-generational:** heap/thuật toán có phân biệt vòng đời ngắn/dài của object để thu gom hiệu quả hơn không?

Một collector có thể **generational và concurrent** (ví dụ ZGC hiện đại), **generational nhưng mostly STW evacuation** (G1), hoặc **concurrent trong mô hình non-generational** (một số phiên bản trước của các collector).

Ở **JDK 24+**, ZGC **chỉ còn generational mode**. Ở **JDK 25+**, generational Shenandoah là một mode được đưa thành production feature trong các bản dựng có Shenandoah. Bởi vậy, cách nói “ZGC luôn nongenerational” hoặc “Shenandoah chỉ là một thế hệ” **không còn đúng nếu áp vào Java mới**.

Lập trình viên Java thông thường không trực tiếp chọn “object nào được GC”. JVM tự theo dõi reachability; thay đổi collector chủ yếu thông qua **runtime JVM options**, không phải thay mã nghiệp vụ.

## 12. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| Concurrent nghĩa là **không có pause** | Có thể vẫn có safepoints, handshakes, short STW phases hoặc fallback |
| Parallel GC threads nghĩa là app vẫn chạy | Nhiều GC worker có thể chạy song song **trong STW** |
| G1 làm toàn bộ evacuation đồng thời | G1 có concurrent marking nhưng young/mixed evacuation chủ yếu **STW** |
| ZGC pause ngắn nghĩa là request không có latency spike | Allocation stall, CPU contention và các nguyên nhân khác vẫn có thể gây spike |
| GC concurrent không dùng CPU của ứng dụng | GC threads **cạnh tranh** CPU/memory bandwidth với mutators |
| Không thấy GC event trong demo nghĩa là collector lỗi | Heap, allocation rate và thời gian demo có thể chưa đủ để kích hoạt GC |
| `gcDetected=true` là bằng chứng GC đồng thời từng nano giây với mutator | Cần log timestamp/JFR để thấy pha và overlap |
| ZGC Java 24+ vẫn cần `-XX:+ZGenerational` | Option đã bị loại bỏ; ZGC chỉ còn generational mode |
| `-XX:+UseShenandoahGC` có trên mọi JDK | Tùy bản dựng/platform, phải kiểm tra |
| Generational và concurrent là cùng khái niệm | Hai chiều thiết kế khác nhau |
| `System.gc()` luôn khởi chạy low-latency GC đúng lúc muốn | Không có cam kết như vậy; explicit GC có thể gây tác dụng phụ |
| Giảm GC pause là chắc chắn tăng throughput | Concurrent GC có thể tốn thêm CPU và giảm tổng throughput |
| GC có thể sửa leak do code giữ tham chiếu | Object còn reachable vẫn được giữ, phải sửa retention |
| `-XX:MaxGCPauseMillis` là deadline cứng | Với G1, nó là **mục tiêu mềm**, có thể không đạt mọi lần |

## 13. Checklist thực tế khi lựa chọn GC độ trễ thấp

- [ ] Xác định **SLO thực tế**: p99/p99.9 response time, throughput và acceptable pauses.
- [ ] Thu baseline cùng **JDK build, OS, CPU quota, RAM limit và heap flags**.
- [ ] Phân biệt **GC pause** với allocation stall và end-to-end latency.
- [ ] Thử G1 trước nếu chưa có yêu cầu pause cực thấp và đang dùng HotSpot mặc định.
- [ ] Thử ZGC khi response time rất nhạy GC; để đủ heap headroom.
- [ ] Thử Shenandoah nếu bản JDK/platform hỗ trợ; đừng mặc định có ở mọi distribution.
- [ ] Kiểm tra version flags: **JDK 24+ ZGC generational-only**; **JDK 25+ Shenandoah generational** là tùy chọn khi hỗ trợ.
- [ ] Ghi GC unified logs; dùng JFR/metrics cho percentile và correlation với requests.
- [ ] Xem CPU cost, RAM/RSS, overhead, allocation rate và live-set growth.
- [ ] Chạy benchmark có warmup và tải đại diện, không dùng demo 500 MiB allocation như kết quả production.
- [ ] Có cảnh báo với Full/Degenerated GC, allocation stalls, OOM và p99 tăng.
- [ ] Tránh tự gọi `System.gc()` hoặc cấu hình cờ lỗi thời để giải quyết tạm thời.

## 14. Bài tập và đáp án

**Câu 1.** Một GC dùng 8 worker threads để thu hồi rác, nhưng tất cả Java application threads đều bị pause trong lúc đó. Đây có phải concurrent GC theo nghĩa “ứng dụng tiếp tục chạy” không?

**Câu 2.** G1 có `Concurrent Mark` nhưng log vẫn in `Pause Young (G1 Evacuation Pause)`. Hai quan sát có mâu thuẫn không?

**Câu 3.** Một dịch vụ có GC pause p99 = 1 ms nhưng request p99 = 150 ms. Có thể kết luận GC là nguyên nhân duy nhất không?

**Câu 4.** Một ứng dụng sử dụng ZGC và `-Xmx128m`, liên tục cấp phát nhanh hơn tốc độ collector thu hồi. Tại sao vẫn có `Allocation Stall`?

**Câu 5.** Khi nâng cấp từ Java 21 sang JDK 25, có nên giữ nguyên `-XX:-ZGenerational` để chạy nongenerational ZGC không?

**Câu 6.** Muốn chạy generational Shenandoah trên JDK 17, có nên copy nguyên `-XX:ShenandoahGCMode=generational` từ hướng dẫn JDK 25 không?

**Câu 7.** Demo Java ở trên in `mutatorProgressed=true` và `gcDetected=true`. Có chứng minh chắc chắn một pha GC đã chạy song song với mutator ở từng thời điểm cụ thể không?

**Câu 8.** Một cache giữ tham chiếu tới hàng triệu object không còn phục vụ nghiệp vụ. Thay G1 sang ZGC có làm những object còn reachable được thu hồi không?

**Đáp án:**

1. **Không.** Đó là GC work song song giữa các GC threads, nhưng không concurrent với mutator threads.
2. **Không.** G1 dùng concurrent marking cho một phần công việc và vẫn có STW evacuation ở các young/mixed collections.
3. **Không.** Có thể do I/O, locks, CPU contention, allocation stall hoặc nhiều yếu tố khác. Cần correlation logs/traces.
4. Vì heap không còn đủ chỗ cấp phát trong lúc GC chạy, mutator phải đợi hoặc hệ thống gặp áp lực bộ nhớ. Cần headroom/giảm allocation/điều chỉnh CPU và heap.
5. **Không.** Từ JDK 24 non-generational ZGC bị loại bỏ và tùy chọn `ZGenerational` không còn hợp lệ. Chọn `-XX:+UseZGC` và đo trên JDK mới.
6. **Không.** Generational Shenandoah chính thức ở JDK 25; khả dụng còn phụ thuộc bản dựng. Dùng mode được phiên bản JVM thực sự hỗ trợ.
7. **Chưa.** Cần GC log/JFR với timeline để nhận diện các pha `Concurrent ...` và khoảng dừng của mutators.
8. **Không.** GC không thu hồi object vẫn còn reachable. Cần thiết kế lại cache, TTL/size limit hoặc bỏ tham chiếu giữ thừa.

## Tài liệu chính thức còn áp dụng

- [OpenJDK — JEP 377: ZGC (Production)](https://openjdk.org/jeps/377): ZGC trở thành collector production ở Java 15.
- [OpenJDK — JEP 379: Shenandoah (Production)](https://openjdk.org/jeps/379): Shenandoah chuyển sang production ở Java 15.
- [Oracle Java SE 15 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/15/gctuning/z-garbage-collector.html): cách dùng ZGC tại mốc Java 15.
- [Oracle Java SE 25 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): concurrent marking, stop-the-world evacuation, pause goals.
- [Oracle Java SE 24 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html): concurrent low-pause GC, heap headroom và generational-only từ JDK 24.
- [OpenJDK — JEP 439 / JEP 474 / JEP 490](https://openjdk.org/jeps/490): Generational ZGC và việc loại bỏ non-generational ZGC ở JDK 24.
- [OpenJDK — JEP 521: Generational Shenandoah](https://openjdk.org/jeps/521): mode generational trở thành production feature ở JDK 25.
- [Oracle Java SE 25 — java command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+UseZGC`, `-XX:+UseG1GC`, GC tuning flags.
- [Oracle Java SE 25 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html): chọn và theo dõi collector phù hợp workload.
- [Oracle Java SE 25 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): counters của GC được Java Management API công bố.
- [Oracle — JDK Flight Recorder](https://docs.oracle.com/en/java/javase/25/jfapi/flight-recorder-api-programmers-guide.html): nền tảng thu thập sự kiện/đo lường runtime.