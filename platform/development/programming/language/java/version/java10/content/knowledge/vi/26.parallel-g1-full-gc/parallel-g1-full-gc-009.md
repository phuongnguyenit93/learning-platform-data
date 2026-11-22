# Giới hạn bảo đảm về thời gian dừng trong G1 Parallel Full GC (Java 10+)

## 1. Câu hỏi cốt lõi: có thể cam kết “GC không bao giờ dừng quá 50 ms” không?

**Không.** Với G1 (Garbage-First Garbage Collector), cờ `-XX:MaxGCPauseMillis=50` chỉ đặt **mục tiêu thời gian dừng mềm** (*soft pause-time goal*). HotSpot cố gắng điều chỉnh những hoạt động GC thông thường để đáp ứng mục tiêu với xác suất cao, **không bảo đảm tất cả các lần dừng đều tối đa 50 ms**.

Ngay cả khi sử dụng **Parallel Full GC for G1**, được đưa vào **Java 10 qua JEP 307**, một lần **Full GC vẫn là stop-the-world (STW)**: các luồng ứng dụng phải dừng trong khi nhiều GC worker cùng thực hiện công việc dọn dẹp/compaction. Việc **song song hóa công việc bên trong Full GC** có thể giảm thời gian dừng so với cách làm đơn luồng trước Java 10, nhưng **không biến Full GC thành concurrent collection**, không tạo hard deadline và không thay thế cơ chế quản lý độ trễ của ứng dụng.

### Ba kết luận quan trọng nhất

1. **`-XX:MaxGCPauseMillis=N` không phải SLA.** Một lần G1 pause có thể dài hơn N ms, cả với Young/Mixed GC lẫn khi xảy ra Full GC.
2. **Parallel không có nghĩa không dừng ứng dụng.** Nhiều worker xử lý Full GC cùng lúc, nhưng luồng ứng dụng vẫn phải chờ kết thúc STW.
3. **Chiến lược chính là hạn chế Full GC**, chứ không chỉ cố tăng số GC worker: thiết lập heap hợp lý, giảm áp lực cấp phát/giữ đối tượng, để concurrent marking hoàn tất kịp, và theo dõi log/latency trên workload thật.

Trong bài, “**giới hạn bảo đảm về thời gian dừng**” được hiểu chính xác là **G1 không cung cấp giới hạn cứng cho mọi pause**. Nếu sản phẩm có yêu cầu latency nghiêm ngặt, cần đo, lựa chọn GC/runtime và thiết kế hệ thống tương ứng; không thể lấy một flag thay cho bằng chứng về SLO.

## 2. G1 bình thường làm việc như thế nào?

G1 chia Java heap thành nhiều **region** và cố gắng thu hồi những region có hiệu quả cao trước. Nó dùng một số công việc chạy **đồng thời với ứng dụng** (*concurrent*) để theo dõi đối tượng sống và lên kế hoạch reclaim, cùng các đợt **STW evacuation** để di chuyển đối tượng còn sống ra vùng được chọn.

Những khái niệm quan trọng:

| Cơ chế | Ứng dụng có dừng không? | Vai trò |
| --- | --- | --- |
| **Young GC / G1 Evacuation Pause** | Có, STW | Thu hồi young regions; sao chép live objects bằng GC workers |
| **Mixed GC** | Có, STW | Evacuate young regions cùng một số old regions được chọn |
| **Concurrent marking** | Phần lớn chạy cùng ứng dụng, nhưng có các điểm STW | Phân tích live data và chuẩn bị thu hồi old regions |
| **Remark/Cleanup** | Có những giai đoạn STW | Hoàn tất xử lý của concurrent cycle và chuẩn bị collection set |
| **Full GC / G1 Compaction Pause** | **Có, STW toàn heap** | Fallback khi G1 không thể thu hồi đủ bộ nhớ theo cơ chế thông thường hoặc có yêu cầu khác |

G1 cố chia công việc reclaim thành những bước nhỏ để tăng khả năng đạt mục tiêu pause. Những bước nhỏ này vẫn có chi phí và vẫn có thể kéo dài hơn dự đoán.

### 2.1. Phân biệt “concurrent” và “parallel”

- **Concurrent:** GC thực hiện công việc cùng lúc các luồng ứng dụng còn hoạt động. Việc này giảm phần việc phải làm trong pause, nhưng có thể tiêu thụ thêm CPU.
- **Parallel:** nhiều GC worker cùng thực hiện một công việc GC; nó **có thể** diễn ra trong một STW pause.
- **Stop-the-world:** các luồng thực thi Java của ứng dụng bị tạm dừng để GC hoàn thành giai đoạn cần tính nhất quán.

Vì vậy, “**G1 Parallel Full GC**” không hề mâu thuẫn với “**Full GC vẫn dừng toàn bộ ứng dụng**”.

### 2.2. G1 không phải real-time collector

Tài liệu **Java SE 27 — Garbage-First (G1) Garbage Collector** khẳng định G1 **không phải real-time collector**. Nó cố đạt pause-time target với xác suất cao trong một giai đoạn hoạt động dài, **không bảo đảm tuyệt đối cho từng lần pause**.

Điều này là bản chất của bộ thu gom nhằm cân bằng **throughput, heap efficiency và latency**, không phải lỗi riêng của Java 10 hay của một bản JDK cụ thể.

## 3. Java 10 đã thay đổi gì? JEP 307

Trước **Java 10**, G1 khi phải thực hiện fallback Full GC dùng thuật toán mark-sweep-compact theo hướng **một luồng**. Vì Full GC có thể quét và compact toàn heap, đây là tình huống gây pause dài đặc biệt bất lợi khi G1 đã được chọn để giảm độ trễ.

**JEP 307 — Parallel Full GC for G1**, delivered trong Java 10, đưa tính song song vào các pha của **G1 Full GC**. Từ đó, nhiều GC worker có thể tham gia công việc marking, tính vị trí compact và di chuyển/xử lý đối tượng trong một lần Full GC.

### 3.1. Điều được cải thiện

- Tận dụng nhiều CPU worker thay vì bắt một worker xử lý toàn bộ Full GC.
- Có thể giảm **wall-clock pause duration** của Full GC khi lượng công việc phù hợp và phần overhead song song hóa được bù lại.
- Giảm tác động của một số tình huống fallback Full GC so với phiên bản G1 đơn luồng lịch sử.

### 3.2. Điều không được bảo đảm

- **Không** xóa bỏ STW.
- **Không** biến Full GC thành một concurrent GC.
- **Không** bảo đảm Full GC luôn nhanh hơn trong mọi kích thước heap, số CPU, container quota hay cấu trúc object graph.
- **Không** bảo đảm pause ≤ `MaxGCPauseMillis`.
- **Không** bảo đảm application response time ≤ GC pause target.
- **Không** xử lý tận gốc các nguyên nhân heap cạn, promotion/evacuation failure hoặc humongous-object fragmentation.

Vì vậy, nếu sản phẩm bị Full GC kéo dài, giải pháp lâu dài thường không đơn giản là “bật cờ parallel” — G1 trên JDK mới đã có cơ chế này. Bạn cần xác định **vì sao Full GC xảy ra** và **mức độ ảnh hưởng tới latency**.

### 3.3. `-XX:ParallelGCThreads` ảnh hưởng thế nào?

```text
-XX:ParallelGCThreads=N
```

Cờ này đặt số GC worker tối đa cho các pha **parallel stop-the-world** trong các collector có hỗ trợ, bao gồm công việc Young/Mixed và Full GC của G1. Với G1 hiện hành, số worker thực dùng có thể còn được **điều chỉnh bởi JVM ergonomics** theo CPU/heap và điều kiện của từng pause.

**Quan trọng:** tăng `ParallelGCThreads` không phải giải pháp “giảm pause tuyến tính”. Các yếu tố giới hạn:

- mức song song thực sự của thuật toán;
- khối lượng đối tượng sống và tham chiếu phải duyệt;
- phối hợp/synchronization overhead giữa workers;
- hiệu năng bộ nhớ, cache, NUMA và bandwidth;
- CPU quota/throttling trong container;
- các pha không thể chia đều hoàn toàn.

Trong ví dụ phòng thử nghiệm sẽ dùng `-XX:ParallelGCThreads=2` **chỉ để dễ quan sát** log, không phải lời khuyên đặt 2 threads cho production.

### 3.4. Khác với `-XX:ConcGCThreads`

`-XX:ConcGCThreads` điều khiển một phần số thread **concurrent marking**; nó không phải cùng một tham số với GC worker count cho Full GC STW. Khi concurrent marking bị tụt lại sau tốc độ cấp phát, có thể cần điều tra số concurrent workers, nhưng không nên tùy tiện tăng cả hai loại thread nếu chưa đo CPU và GC phases.

## 4. `-XX:MaxGCPauseMillis` là mục tiêu, không phải hard bound

Ví dụ:

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=50 MyApplication
```

Lệnh trên là **minh họa cấu hình**; `MyApplication` chỉ là tên class ví dụ, không có trong bài thực hành. Ý nghĩa:

> Đặt **mục tiêu khoảng 50 ms cho những GC pauses mà G1 đang điều chỉnh**; JVM cố tối ưu kích thước collection set và các quyết định GC dựa trên mô hình chi phí để tiến gần mục tiêu.

Nó **không** có nghĩa:

> JVM sẽ chặn mọi GC pause ở đúng 50 ms, và một lần Full GC sẽ tự dừng khi hết 50 ms.

### 4.1. Vì sao GC không thể “dừng giữa chừng” để giữ hẹn?

Trong một STW phase, JVM phải duy trì tính đúng đắn của heap/object references. Khi đã bắt đầu một công việc buộc phải hoàn tất để an toàn — nhất là **Full GC compact cả heap** — nó không thể đơn giản mở ứng dụng trở lại với những con trỏ chưa được sửa chỉ vì hết thời gian mục tiêu.

G1 **dự đoán** chi phí của những lần thu gom bình thường, điều chỉnh lượng vùng cần thu và nhiều tham số động. Đây là **adaptive heuristic**, không phải bộ lập lịch hard real-time có khả năng preempt mọi thao tác GC một cách an toàn theo deadline.

### 4.2. Young/Mixed vẫn có thể vượt mục tiêu

Ngay cả ở Young/Mixed GC, thời gian thực có thể lớn hơn prediction do:

- object survival cao bất ngờ, phải sao chép nhiều live objects;
- nhiều references/remembered-set entries và root scanning;
- reference processing hoặc class unloading tốn thời gian;
- OS scheduling, CPU throttling, page fault hoặc memory pressure;
- concurrent work chưa theo kịp, gây khối lượng xử lý lớn hơn;
- bộ nhớ không đủ để evacuation bình thường.

Do đó, một log Young GC có pause **1,92 ms** dù target **1 ms** là hoàn toàn có thể xảy ra; JVM không xem đó là vi phạm một hard deadline.

### 4.3. Full GC không được cam kết bởi pause target

**Fallback Full GC là trường hợp đặc biệt khó kiểm soát**: nó có thể cần xét và compact một phần rất lớn hoặc toàn bộ heap, tùy lượng live data, heap fragmentation, bộ nhớ và khả năng song song hóa.

JEP 307 làm quá trình đó có thể **ngắn hơn bằng cách chia công việc cho nhiều worker**, nhưng `MaxGCPauseMillis` không biến Full GC thành tập các pause nhỏ tự động bảo đảm không quá N ms.

Một người vận hành thấy:

```text
-XX:MaxGCPauseMillis=50
GC(...) Pause Full (...) ... 470.123ms
```

không được kết luận ngay rằng HotSpot “đã bỏ qua một hard constraint” hoặc “GC bug”. Đây là **ví dụ giả định** về một Full GC kéo dài, cần điều tra nguyên nhân; G1 vốn không cam kết mọi Full GC dưới 50 ms.

### 4.4. Mặc định 200 ms không phải SLA mặc định

Tài liệu G1 của JDK hiện đại nêu **`-XX:MaxGCPauseMillis=200`** là **default goal**, không phải “mỗi 200 ms ứng dụng sẽ chạy ít nhất một lần”, cũng không phải “GC luôn phải xong trong 200 ms”.

Hãy đo latency của **chính ứng dụng**; không dùng giá trị default 200 ms làm kết luận rằng sản phẩm đã đạt SLO.

## 5. Vì sao G1 vẫn phải chạy Full GC?

Thiết kế của G1 ưu tiên **tránh Full GC** bằng các chu kỳ concurrent marking và incremental region reclamation. Nhưng đây là hệ thống hữu hạn: khi ứng dụng cấp phát/giữ bộ nhớ nhanh hơn G1 có thể dọn, nó có thể cần **Full GC** để tìm và compact lại vùng trống.

### 5.1. Evacuation failure do thiếu vùng đích

Trong một lần Young/Mixed evacuation, G1 cần vùng đích để chuyển live objects. Nếu heap không có đủ vùng đích, GC có thể gặp **Evacuation Failure: Allocation**.

Đây là một dấu hiệu nguy cơ: nếu G1 không thể reclaim đủ để tiếp tục cấp phát, nó có thể phải thực hiện Full GC fallback. Trong log JDK mới, failure có thể còn liên quan **Pinned** objects được giữ cố định bởi một số native/JNI interactions; hai dạng nguyên nhân cần đọc theo log cụ thể.

**Không suy rằng cứ một Evacuation Failure là ngay lập tức có Full GC**: G1 còn các bước xử lý/fallback khác. Phải đọc chuỗi sự kiện và kết quả thực tế.

### 5.2. Concurrent marking không hoàn thành kịp

G1 muốn hoàn tất marking trong khi ứng dụng đang chạy để xác định old regions có thể reclaim. Nếu tốc độ cấp phát/promotion tăng nhanh hoặc marking bắt đầu quá muộn, G1 có thể không có đủ thông tin/thời gian để reclaim old gen trước khi heap gần đầy.

Dấu hiệu có thể gồm:

- old generation occupancy tăng liên tục;
- nhiều mixed/young pauses nối nhau;
- concurrent cycle kéo dài;
- evacuation failures hoặc Full GC vì allocation failure;
- lượng free regions thấp khi ứng dụng vẫn cần cấp phát.

Mục tiêu tuning là **để quá trình reclaim bắt kịp tốc độ tạo live data**, không phải chỉ chỉnh pause target.

### 5.3. Humongous objects và fragmentation

G1 chia heap thành regions; một **humongous object** thường là đối tượng có kích thước **lớn hơn một nửa G1 region**, được cấp phát trong các regions đặc biệt. Những object lớn/giữ lâu có thể khiến số vùng trống liên tiếp không đủ, trong khi tổng lượng memory chưa hoàn toàn dùng hết.

Vì vậy, có thể xuất hiện:

- humongous region count tăng;
- không có dãy region trống đủ dài;
- Full GC do áp lực cấp phát/fragmentation;
- OutOfMemoryError nếu Full GC không giải phóng đủ chỗ.

Không tự tăng `-XX:G1HeapRegionSize` như một “bí quyết” cho mọi workload. Phải xem **humongous-region metrics, kích thước object và throughput/latency** để cân nhắc giảm số object humongous hoặc điều chỉnh region size.

### 5.4. Full GC do yêu cầu chủ động

Một lời gọi `System.gc()` hoặc một công cụ bên ngoài có thể yêu cầu full-heap collection. Nhưng `System.gc()` chỉ là **yêu cầu**, không phải hợp đồng “mỗi lần gọi chắc chắn sinh đúng một Full GC STW” trên mọi JVM/cấu hình.

HotSpot có các tùy chọn như:

- `-XX:+ExplicitGCInvokesConcurrent`: có thể chuyển hướng explicit GC sang concurrent cycle trong các tình huống được hỗ trợ.
- `-XX:+DisableExplicitGC`: bỏ qua lời yêu cầu explicit GC.

**Không thêm `System.gc()` vào code production để “tránh Full GC lâu”**. Đó có thể là nguồn kích hoạt pause không cần thiết. Bài thực hành bên dưới dùng lời gọi này **chỉ để tạo một sự kiện có thể chẩn đoán**, và sẽ giải thích rõ vì sao không dùng nó làm chiến lược GC.

## 6. Đọc log để phân biệt pause target và kết quả thật

JDK hiện đại hỗ trợ **unified logging**. Một cấu hình thường dùng:

```bash
java -XX:+UseG1GC -Xlog:gc*=info:file=gc.log:uptime,level,tags MyApplication
```

Đây là lệnh mẫu, `MyApplication` là tên class tượng trưng. Cần kiểm tra syntax/quoting của shell và quyền ghi file log ở môi trường đang dùng.

Trong GC log, cần phân biệt:

| Dấu hiệu | Cách hiểu |
| --- | --- |
| `Pause Young (Normal) (G1 Evacuation Pause)` | STW young collection |
| `Pause Young (Mixed) (G1 Evacuation Pause)` | Mixed collection có young và một số old regions |
| `Pause Full (G1 Compaction Pause)` | Full GC fallback compact heap |
| `Pause Full (System.gc())` | Full GC được ghi nhận khi JVM xử lý explicit GC request ở dạng STW |
| `Using N workers of M for full compaction` | Số workers JVM dùng cho công việc Full GC song song |
| `Evacuation Failure: Allocation` | Không đủ vùng đích để di chuyển object khi evacuation |
| `Humongous regions: X->Y` | Thay đổi số regions bị chiếm bởi humongous objects |
| `User=... Sys=... Real=...` | CPU user/system và wall-clock time giúp chẩn đoán pause |

**Thời lượng cuối dòng `Pause ... 3.590ms` là số đo pause thực tế của sự kiện đó**, không phải mục tiêu từ flag. Thời lượng tổng thể request còn chịu ảnh hưởng ứng dụng, network, I/O, thread scheduling và các thời điểm safepoint khác.

### 6.1. Ví dụ về một log vượt pause target

Giả sử JVM chạy với:

```text
-XX:MaxGCPauseMillis=1
-XX:ParallelGCThreads=2
```

Một đoạn log **đã quan sát thực tế với OpenJDK 24.0.2**:

```text
GC(6) Pause Full (System.gc())
GC(6) Using 2 workers of 2 for full compaction
GC(6) Pause Full (System.gc()) 32M->25M(64M) 3.590ms
```

**Kết luận đúng:** JVM đã dùng 2 workers trong Full GC, nhưng pause thực tế là **3,590 ms**, lớn hơn **mục tiêu mềm 1 ms**. Không có hard guarantee nào bị vi phạm; GC vẫn phải hoàn tất một công việc an toàn.

**Không kết luận sai** rằng mọi lần Full GC đều dài 3,590 ms hoặc 2 workers luôn tối ưu. Con số thay đổi theo JDK, CPU, heap, object graph và môi trường. Trong log thực còn prefix thời gian, mức log và tags.

### 6.2. Một Young GC cũng có thể vượt target

Cùng lần thử đó, log Young GC ghi nhận:

```text
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 3M->3M(64M) 1.920ms
```

Đây là **quan sát của lần chạy cụ thể**, minh họa target 1 ms là **mục tiêu mềm đối với cả những pause thông thường**. Đặt một mục tiêu cực nhỏ không làm JVM ngừng GC khi chạm mốc thời gian.

### 6.3. Xem `Real` khi phân tích chậm vì OS

Tài liệu Oracle khuyên xem dòng `gc+cpu=info`:

```text
User=0.19s Sys=0.00s Real=0.01s
```

Đây là **ví dụ minh họa từ tài liệu**, không phải số đo của chương trình trong bài. Khi `Real` cao bất thường so với thời gian CPU đã dùng, có thể cần xem tình trạng CPU bị chia sẻ/quota, OS scheduling, page faults hoặc I/O. Ngược lại, với nhiều GC threads, tổng `User` time có thể **lớn hơn** wall-clock `Real`; đó không phải bằng chứng thời gian bị tính sai.

## 7. Chương trình Java 17+ độc lập để kiểm tra giới hạn mềm

Chương trình tạo một lượng đối tượng còn tham chiếu, ghi các số đếm **xác định**, và **yêu cầu** GC tường minh một lần chỉ để quan sát log trong lab.

**Cảnh báo:** Không đưa `System.gc()` vào mã nghiệp vụ production. Mục tiêu demo không phải benchmark, không chứng minh mọi môi trường đều sinh Full GC, cũng không đưa ra tỷ lệ tăng tốc khi thay số worker.

Lưu file **`G1PauseDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public final class G1PauseDemo {
    public static void main(String[] args) {
        List<byte[]> retained = new ArrayList<>();
        for (int i = 0; i < 96; i++) {
            byte[] block = new byte[256 * 1024];
            block[0] = (byte) i;
            retained.add(block);
        }

        System.out.println("retainedBlocks=" + retained.size());
        System.out.println("retainedMiB=" + (retained.size() * 256 / 1024));

        System.gc(); // Chi dung cho demo/chan doan, khong su dung de tune production.

        System.out.println("explicitGcRequested=true");
        System.out.println("retainedStillReachable=" + !retained.isEmpty());
    }
}
```

### 7.1. Biên dịch

```bash
javac --release 17 -encoding UTF-8 G1PauseDemo.java
```

### 7.2. Chạy với cấu hình thí nghiệm có mục tiêu cực thấp

```bash
java -Xms64m -Xmx64m -XX:+UseG1GC \
     -XX:MaxGCPauseMillis=1 -XX:ParallelGCThreads=2 \
     "-Xlog:gc*=info:file=g1-demo.log:uptime,level,tags" \
     G1PauseDemo
```

Dấu `\` nối dòng dành cho **POSIX shell**. Với PowerShell/Windows CMD, chạy trên một dòng:

```powershell
java -Xms64m -Xmx64m -XX:+UseG1GC -XX:MaxGCPauseMillis=1 -XX:ParallelGCThreads=2 "-Xlog:gc*=info:file=g1-demo.log:uptime,level,tags" G1PauseDemo
```

**Vì sao dùng `1 ms`?** Chỉ để làm rõ ranh giới của một **soft goal** bằng một thí nghiệm nhỏ. Đây là target cực thấp, không phải khuyến nghị cho server production. Tương tự, `-Xms64m -Xmx64m` và `ParallelGCThreads=2` chỉ dành cho lab, không phải thông số mặc định tốt cho mọi ứng dụng.

### 7.3. Stdout chính xác của chương trình

```text
retainedBlocks=96
retainedMiB=24
explicitGcRequested=true
retainedStillReachable=true
```

Các dòng trên được xác định bởi code, **không phụ thuộc việc JVM có thực thi Full GC hay không**. `retainedMiB=24` là tổng dung lượng **payload của 96 byte arrays**, không phải số đo heap footprint toàn phần: Java object headers, alignment, ArrayList và những đối tượng khác làm heap sử dụng thực tế lớn hơn.

### 7.4. Đọc GC log

Trên POSIX shell:

```bash
grep -E "Pause Full|Pause Young|full compaction" g1-demo.log
```

Trên PowerShell:

```powershell
Select-String -Path g1-demo.log -Pattern 'Pause Full','Pause Young','full compaction'
```

Với **OpenJDK 24.0.2, Windows**, lần chạy thử ghi:

```text
GC(6) Pause Full (System.gc())
GC(6) Using 2 workers of 2 for full compaction
GC(6) Pause Full (System.gc()) 32M->25M(64M) 3.590ms
```

Những dòng này là **đoạn log được lược bỏ prefix** để tập trung vào tín hiệu. Mỗi lần chạy có thể có GC IDs, worker count, heap usage, pause duration khác.

**Tại sao không bảo đảm tái hiện đúng Full GC trên mọi runtime?**

- `System.gc()` là **yêu cầu**, có thể bị bỏ qua hoặc xử lý concurrent theo JVM options.
- Một số JVM/distribution/version có hành vi khác HotSpot thử nghiệm.
- GC ergonomics và CPU/thread availability có thể khác.
- Thứ tự/độ dài GC events thay đổi theo môi trường.

Nếu chạy demo mà không thấy `Pause Full`, không được sửa tài liệu để tuyên bố JVM hỏng. Kiểm tra `UseG1GC`, startup flags, chính sách xử lý explicit GC và GC log. Mục tiêu của bài là **quan sát**, không cưỡng bức một tình huống OOM nguy hiểm để tạo log Full GC.

### 7.5. Kết luận từ demo

- Program stdout chứng minh dữ liệu mô phỏng đã được tạo.
- GC log, **không phải stdout**, chứng minh sự kiện GC nào đã xảy ra.
- Trong phép thử, một Full GC sử dụng **2 workers** mà vẫn dài hơn `MaxGCPauseMillis=1`.
- Full GC song song có thể rút ngắn công việc STW, nhưng **không có giới hạn cứng** về pause duration.
- Demo nhỏ **không phải bằng chứng** về hiệu năng ứng dụng production; phải đo thêm trên workload thực.

## 8. Thiết lập `MaxGCPauseMillis` như thế nào mới có ý nghĩa?

Một mục tiêu độ trễ có ích nên được chọn theo **SLO của ứng dụng**, không phải theo cảm tính rằng “càng nhỏ càng tốt”.

Ví dụ một API cần p99 response time dưới 200 ms. Đây là SLO **phần lớn request**, không phải hard deadline của GC. Trong budget 200 ms còn có:

- thời gian CPU xử lý business logic;
- network, database, disk I/O;
- scheduling, thread contention;
- safepoint/GC pauses và overhead GC concurrent;
- serialization/deserialization;
- queueing, retries và downstream dependencies.

Nếu đặt `-XX:MaxGCPauseMillis=50`, đó là **một tín hiệu cho G1 hướng tới pause ngắn**, chứ không cấp cho ứng dụng “chính xác 150 ms cho các phần còn lại”.

### 8.1. Phân biệt ba tầng yêu cầu

| Tầng | Ví dụ | Có được G1 bảo đảm bởi một flag không? |
| --- | --- | --- |
| **GC target** | `MaxGCPauseMillis=50` | Không, soft goal |
| **Observed GC behavior** | p99 GC pause = 34 ms, max = 410 ms trong một cửa sổ đo | Phải thu số liệu thực, không suy ra từ flag |
| **Application SLO** | p99 HTTP request < 200 ms | Phải đo request latency end-to-end; không do GC flag tự bảo đảm |

Các con số trong bảng là **minh họa giả định**, không phải benchmark thực tế. Khi viết acceptance criteria, ghi rõ **workload, cửa sổ thời gian, percentile, tài nguyên và số lượng lần đo**.

### 8.2. Vì sao giảm target quá thấp có thể gây tác dụng ngược?

G1 có thể thu nhỏ young generation hoặc collection set để giảm mỗi pause. Khi làm vậy, ứng dụng có thể gặp:

- GC thường xuyên hơn;
- tăng CPU/GC overhead;
- ít thời gian hữu ích cho business code;
- promotion pressure hoặc old-gen pressure lớn hơn trong một số workload;
- throughput thấp hơn dù một số Young GC ngắn hơn.

Nếu G1 không thể đạt mục tiêu vì live set và memory pressure, **tiếp tục giảm target không tự giúp Full GC ít xảy ra**. Cần nhìn cả số lần GC, phân bố pause, CPU và throughput.

### 8.3. Tránh khóa young generation bằng cờ cũ một cách máy móc

Tài liệu Oracle G1 tuning hiện hành khuyên **không cố định young generation size** bằng những lựa chọn như `-Xmn`/`-XX:NewRatio` nếu muốn cơ chế adaptive pause-time control hoạt động tốt.

Nếu bạn ép young generation kích thước cố định, G1 mất một trong những phương tiện chính để điều chỉnh độ dài pause. Hãy bắt đầu bằng **default ergonomics** với heap size và pause goal hợp lý, chỉ tinh chỉnh sâu sau khi log xác định vấn đề.

## 9. Khi thấy Full GC: điều tra nguyên nhân, không chỉ thêm threads

### 9.1. Quy trình chẩn đoán đầu tiên

1. Bật log GC vừa đủ, ví dụ `-Xlog:gc*=info` hoặc lưu file log có rotation phù hợp.
2. Tìm cụm **`Pause Full`**, đặc biệt `Pause Full (G1 Compaction Pause)` nếu là fallback.
3. Xem **nguyên nhân**: `Allocation Failure`, `System.gc()`, công cụ bên ngoài, fragmentation hay nhiều đợt evacuation không đủ chỗ.
4. Đọc occupancy trước/sau GC, old generation/humongous regions và số free regions.
5. Xem concurrent marking cycle có hoàn tất kịp trước khi heap gần đầy không.
6. Kiểm tra live set, allocation rate, promotion rate và retained objects từ application.
7. Đánh giá CPU quota/throttling, OS memory pressure và GC worker count.
8. Đối chiếu GC events với latency spikes của user requests.
9. Chạy benchmark A/B **mỗi lần chỉ thay một nhóm biến** để đo tác động thực.
10. Nếu heap liên tục không đủ để chứa live set, tăng worker count không giải quyết OutOfMemoryError.

### 9.2. Khi old gen tăng quá nhanh

Đầu tiên xem **ứng dụng có giữ quá nhiều đối tượng sống** không. Những ví dụ:

- cache không giới hạn hoặc eviction chính sách kém;
- queue backlog tăng liên tục;
- batch/load dữ liệu quá lớn trong một request;
- retention ngoài dự kiến do static collections/listeners;
- heap quá nhỏ so với live set theo tải thực;
- allocations và promotions tăng đột ngột sau thay đổi code.

Nếu nguyên nhân ở logic lưu trữ/retention, chỉnh GC flags chỉ có thể che triệu chứng tạm thời. Cần profiling allocation/heap và sửa vòng đời đối tượng.

### 9.3. Cho concurrent marking đủ thời gian

Oracle G1 tuning gợi ý điều tra:

- heap headroom, `-Xmx`;
- tốc độ allocation vào old generation;
- số concurrent marking workers `-XX:ConcGCThreads`;
- adaptive IHOP và reserve headroom;
- số/khối lượng humongous objects.

**Không có “bộ flags tăng tốc chuẩn” áp dụng cho mọi ứng dụng.** Ví dụ `G1ReservePercent`/IHOP có trade-offs và phải dựa trên log. Chỉ thử khi đã xác nhận concurrent marking không hoàn tất kịp; sau đó đo lại pause tails và throughput.

### 9.4. Khi xuất hiện humongous allocations

Dùng thông tin `Humongous regions: X->Y` trong GC log để biết mức độ. Nếu số region bị humongous objects chiếm cao, có thể:

- giảm cấp phát mảng/object cực lớn;
- chia nhỏ đối tượng/buffers nếu hợp lệ nghiệp vụ;
- giảm retention/lifetime của những objects ấy;
- cân nhắc thay `G1HeapRegionSize` trên cơ sở profile;
- tăng heap có kiểm soát nếu memory budget cho phép.

Không tăng region size chỉ vì “đọc được trên Internet”. Thay đổi region size ảnh hưởng cả chi phí region management và evacuation. Benchmark cần phản ánh workload thực tế.

### 9.5. Khi `System.gc()` gây pause

Tìm `Pause Full (System.gc())` trong log; truy ra nơi gọi trong ứng dụng/thư viện hoặc công cụ vận hành. Một số trường hợp dùng `System.gc()` như “dọn bộ nhớ định kỳ” là antipattern, có thể tạo STW không cần thiết.

Có thể đánh giá `-XX:+ExplicitGCInvokesConcurrent` hoặc `-XX:+DisableExplicitGC` **nếu hiểu hệ quả và có bằng chứng cần thiết**. Nhưng không nên bật tùy chọn bỏ explicit GC mù quáng khi ứng dụng/thư viện có hợp đồng hành vi phụ thuộc nó. Mọi thay đổi cần qua test và tài liệu HotSpot của phiên bản mục tiêu.

## 10. Theo dõi và đánh giá SLO/latency

### 10.1. Những metric nên thu

| Nhóm số liệu | Ý nghĩa |
| --- | --- |
| Số lần `Pause Full` và tổng thời gian | Full GC có còn là fallback bất thường hay xảy ra thường xuyên? |
| Histogram pause duration (p50/p95/p99/max) | Đuôi độ trễ có vấn đề không? |
| Young/Mixed pause frequency | GC có phải đang chạy quá dày? |
| Old occupancy, allocation/promotion rate | Heap có đủ headroom không? |
| Humongous region count, evacuation failures | Có fragmentation/thiếu vùng đích? |
| Concurrent marking duration | G1 có hoàn tất marking kịp không? |
| GC CPU & process CPU | Tuning có đổi latency lấy throughput không? |
| End-to-end request p95/p99/p99.9 | Người dùng thực sự trải nghiệm độ trễ ra sao? |

Nếu Full GC chỉ xảy ra 1 lần trên 10 triệu request, chỉ nhìn p99 request latency có thể **không phát hiện tail xấu nhất**. Khi có yêu cầu availability/latency rất nghiêm, nên theo dõi cả **max pause**, sự kiện ngoài percentile và phân phối theo tải.

### 10.2. GC logs và JFR

JDK Flight Recorder (**JFR**) hỗ trợ quan sát GC pauses, allocation và nhiều sự kiện runtime; GC unified logging giúp nhìn chi tiết từng phase. Nên kết hợp:

- **JFR/metrics** để liên hệ pause với request latency và CPU;
- **GC log** để xác định Full GC, nguyên nhân và các phases;
- **heap/allocation profiler** để tìm source tạo/giữ objects;
- **load test** trên heap, CPU quota và deployment settings gần production.

Đừng dùng thời lượng `System.gc()` trong ví dụ nhỏ làm benchmark cho một server xử lý hàng nghìn request.

### 10.3. Đọc pause đúng loại

Một log Young GC dài hơn goal không tự chứng minh Full GC xảy ra. Ngược lại, một Full GC dài không được “sửa” chỉ bằng cách giảm `MaxGCPauseMillis`.

Mỗi kết quả phân tích phải nêu rõ **loại GC event**, **thời gian thực tế**, **nguyên nhân**, **heap trước/sau** và **bối cảnh tải**.

### 10.4. Safepoint và latency end-to-end

GC pause chỉ là **một phần** của thời gian ngừng thực thi mà ứng dụng có thể trải nghiệm. Safepoint synchronization, OS scheduling, CPU starvation, locks, blocking I/O và tầng mạng có thể cộng thêm vào độ trễ.

Do đó, một sản phẩm có `MaxGCPauseMillis=50` mà vẫn có request 2 giây không chứng minh GC là nguyên nhân; phải **đối chiếu timeline**. Tương tự, một GC pause 500 ms có thể ảnh hưởng nhiều request khác nhau tùy workload và lịch phục vụ.

## 11. Tác động của cấu hình CPU và heap

### 11.1. Giới hạn CPU trong container

Trong container, `-XX:ParallelGCThreads` có thể bị giới hạn bởi CPU mà JVM thấy hoặc cấu hình thủ công, nhưng ngay cả khi thông báo có nhiều workers, thực tế **CPU quota và throttling** có thể khiến workers không cùng tiến nhanh như mong đợi.

Kiểm tra container CPU limit, cgroup stats, host load và JVM ergonomics. **Đừng suy rằng 8 workers sẽ luôn nhanh hơn 2 workers bốn lần**.

### 11.2. Heap quá nhỏ

Một heap rất nhỏ so với live set khiến GC thường xuyên, promotion pressure cao và dễ rơi vào Full GC. Ở đầu kia, tăng heap có thể làm memory footprint lớn hơn và một số kiểu GC mất thời gian lâu hơn nếu phải xử lý nhiều live objects.

Không đưa công thức “Xmx càng lớn thì pause chắc chắn càng nhỏ” vào quy trình vận hành. Chọn heap dựa trên **live set, allocation rate, container memory budget và SLO**.

### 11.3. `Xms`, `Xmx` và pretouch

Tài liệu Oracle nêu `-Xms` bằng `-Xmx` có thể tránh công việc mở rộng/thu nhỏ heap trong runtime; `-XX:+AlwaysPreTouch` chuyển một phần chi phí cấp phát trang vật lý sang startup. Đây là **trade-off**: có thể làm khởi động chậm hơn/tăng resident memory sớm, nhưng giúp giảm biến động do cấp phát page trong runtime.

Chỉ sử dụng nếu đã xác định OS memory operations đóng góp đáng kể vào pause/latency. Không coi `AlwaysPreTouch` là giải pháp áp dụng mặc định cho mọi container nhỏ.

## 12. Tại sao Full GC song song vẫn có giới hạn vật lý?

G1 Full GC không chỉ “làm một phép tính” có thể chia hoàn toàn đều trên N CPU. Nó phải duyệt object graph, xác định đối tượng còn sống, sắp xếp/compact dữ liệu, cập nhật references và bảo đảm tính nhất quán heap.

Điều đó đặt ra các giới hạn:

1. **Công việc không phân chia đồng đều.** Có pha hoặc cấu trúc object graph làm một số workers bận hơn workers khác.
2. **Băng thông bộ nhớ hữu hạn.** Nhiều worker cùng di chuyển dữ liệu có thể bão hòa memory bandwidth.
3. **Synchronization overhead.** GC worker phải phối hợp và cập nhật metadata chính xác.
4. **Số lượng live objects.** Full GC không thể tránh chi phí xử lý nhiều dữ liệu còn sống.
5. **Thời gian JVM tới safepoint/OS.** Pause thực có thể chịu ảnh hưởng ngoài thuật toán compact.
6. **GC workers cũng dùng CPU.** Tăng parallelism có thể ảnh hưởng throughput toàn hệ thống và workloads khác.
7. **Heap fragmentation và humongous data.** Không thể giải quyết mọi vấn đề bằng cách tăng thread.

Vì thế JEP 307 là cải tiến **giảm tác động của fallback Full GC** chứ không phải **bằng chứng hard latency guarantee**.

## 13. Chiến lược khi sản phẩm cần độ trễ rất thấp

Nếu yêu cầu sản phẩm là “p99 request latency dưới 100 ms”, hãy xác định phương án theo số liệu. Nếu yêu cầu là “không bao giờ có pause quá 10 ms”, cần nhận ra G1 không cung cấp hard guarantee đó, và các công nghệ GC low-latency cũng phải đánh giá **theo phạm vi cam kết thực sự**.

Những bước cần xem xét:

- giảm allocation và retention ở ứng dụng;
- chọn heap đủ headroom;
- tránh Full GC fallback;
- tối ưu từng đợt Young/Mixed GC dựa trên log;
- đo GC pause tail cùng request latency;
- thử nghiệm collector khác nếu yêu cầu đặt trọng tâm vào latency rất thấp (ví dụ ZGC trên JDK hỗ trợ), nhưng **không mặc định nó là hard real-time collector**;
- tính tới trade-off CPU, heap footprint, throughput và cost;
- thử trên đúng JDK/OS/CPU/container workload được triển khai.

**Không nên so “collector A max pause = x ms” từ một benchmark trên Internet với “collector B max pause = y ms” trên một máy khác rồi xem là kết luận.** Đo cùng workload, cùng phần cứng, cùng ràng buộc và đủ thời gian.

## 14. Những lỗi thường gặp

**Lỗi 1 — Coi `MaxGCPauseMillis=50` là bảo đảm 50 ms.**  
Sai: đây là **soft goal**, G1 không cung cấp hard bound cho từng pause.

**Lỗi 2 — Coi Full GC song song là concurrent với ứng dụng.**  
Sai: các GC workers chạy song song **trong một STW phase**.

**Lỗi 3 — Nghĩ Java 10 đã xóa Full GC của G1.**  
Sai: JEP 307 song song hóa fallback Full GC, không loại bỏ nó.

**Lỗi 4 — Giảm target càng thấp càng tốt.**  
Sai: có thể tăng GC frequency/overhead và làm throughput kém đi; Full GC vẫn có thể dài.

**Lỗi 5 — Tăng `ParallelGCThreads` là sẽ giảm pause tuyến tính.**  
Sai: chịu giới hạn bởi CPU, work distribution, object graph và memory bandwidth.

**Lỗi 6 — Nhầm `ParallelGCThreads` với `ConcGCThreads`.**  
Hai nhóm tham số liên quan các công việc parallel STW và concurrent marking khác nhau.

**Lỗi 7 — Thấy `Pause Full` rồi chỉ chỉnh target.**  
Sai: phải điều tra heap occupancy, allocation rate, fragmentation và concurrent marking.

**Lỗi 8 — Coi `System.gc()` là cách dọn bộ nhớ định kỳ.**  
Sai trong hầu hết ứng dụng: có thể kích hoạt STW Full GC ngoài mong đợi.

**Lỗi 9 — Coi một Young GC dài là bằng chứng đã có Full GC.**  
Sai: log có nhãn sự kiện khác nhau, cần đọc đúng loại pause.

**Lỗi 10 — Dùng stdout ứng dụng để đo GC pause.**  
Sai: stdout không chứa toàn bộ GC events; cần GC log/JFR.

**Lỗi 11 — G1 không đạt 1 ms trong lab nên JVM bị lỗi.**  
Không đúng: mục tiêu cực thấp chỉ là tín hiệu tuning, không phải deadline.

**Lỗi 12 — Coi p99 GC pause là p99 HTTP response time.**  
Sai: hai metric khác phạm vi, cần quan sát request end-to-end.

**Lỗi 13 — Ép young generation bằng `-Xmn` để “ổn định” pause.**  
Có thể vô hiệu hóa khả năng G1 điều chỉnh young size theo mục tiêu pause.

**Lỗi 14 — Cứ Full GC song song là không thể OOME.**  
Sai: nếu live set quá lớn hoặc không có vùng cấp phát phù hợp, Full GC vẫn có thể không giải phóng đủ.

**Lỗi 15 — Bật nhiều GC threads dù container thiếu CPU.**  
Có thể tăng overhead và contention, không chứng minh cải thiện latency.

**Lỗi 16 — Coi kết quả demo ở một JDK là cam kết toàn bộ hệ sinh thái Java.**  
Sai: mục đích demo là chứng minh cơ chế/log, số đo thay đổi theo phiên bản và môi trường.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `-XX:MaxGCPauseMillis=100` có bảo đảm mỗi GC pause ≤ 100 ms không?  
**Đáp án:** Không. Đó là soft pause-time goal, không phải hard deadline.

**Câu 2.** G1 Full GC song song có cho phép các luồng ứng dụng tiếp tục chạy trong suốt Full GC không?  
**Đáp án:** Không. Đây vẫn là stop-the-world; chỉ công việc GC được chia cho nhiều worker.

**Câu 3.** JEP nào đưa Parallel Full GC cho G1 vào Java 10?  
**Đáp án:** **JEP 307 — Parallel Full GC for G1**.

**Câu 4.** Log `Using 2 workers of 2 for full compaction` cho biết điều gì?  
**Đáp án:** JVM sử dụng 2 workers trong một lần Full GC compaction; không cho biết pause có đạt target hay không.

**Câu 5.** Nếu target 1 ms nhưng log Full GC là 3,590 ms, có phải JVM vi phạm một hard guarantee không?  
**Đáp án:** Không. Target không phải bảo đảm cứng.

**Câu 6.** Nếu log không có `Pause Full` nhưng p99 request latency cao, có thể khẳng định G1 Full GC là nguyên nhân không?  
**Đáp án:** Không. Cần đối chiếu Young/Mixed pauses, OS/CPU, ứng dụng và downstream.

**Câu 7.** Vì sao Full GC có thể xảy ra trước khi heap hoàn toàn hết mọi byte trống?  
**Đáp án:** Fragmentation, humongous objects và thiếu vùng liên tiếp/có thể dùng cho evacuation/cấp phát có thể gây vấn đề.

**Câu 8.** `System.gc()` có luôn tạo Full GC STW trên mọi JVM không?  
**Đáp án:** Không. JVM có thể bỏ qua hoặc dùng cơ chế concurrent; trong bài chỉ sử dụng nó để quan sát trên HotSpot lab.

**Câu 9.** Với evacuation failure, có phải lần GC kế tiếp chắc chắn luôn là Full GC không?  
**Đáp án:** Không. Evacuation failure là dấu hiệu nguy cơ; cần xem log cụ thể và trạng thái heap.

**Câu 10.** Vì sao G1 không phải real-time collector?  
**Đáp án:** Nó hướng tới pause target với xác suất cao, nhưng không có cơ chế bảo đảm tuyệt đối cho mọi lần pause.

**Câu 11.** Với p99 API 200 ms, đặt `MaxGCPauseMillis=50` có đủ để ký SLA không?  
**Đáp án:** Không. Phải đo end-to-end latency và kiểm soát network, business logic, DB, OS và GC, cùng tỷ lệ vi phạm.

**Câu 12.** Bước đầu tiên hợp lý khi thấy Full GC thường xuyên là gì?  
**Đáp án:** Thu GC log/metrics, xem nguyên nhân và allocation/live-set pressure; không vội tăng `ParallelGCThreads`.

## 16. Ghi nhớ

1. **Java 10/JEP 307** đưa **Parallel Full GC for G1** vào HotSpot; cơ chế này **vẫn còn áp dụng** trên JDK mới.
2. Parallel Full GC **vẫn dừng toàn bộ luồng ứng dụng**. Song song hóa chỉ giảm khả năng một worker phải làm hết công việc.
3. **`-XX:MaxGCPauseMillis` là soft goal**, không bảo đảm giới hạn cứng cho mọi Young/Mixed/Full GC.
4. **G1 không phải real-time collector.** Nhu cầu hard deadline không thể được đáp ứng chỉ bằng cách thêm một JVM flag.
5. Full GC có thể đến từ memory pressure, evacuation failure, marking không kịp, humongous fragmentation hoặc explicit GC request.
6. **Đọc log thật**: `Pause Full`, `Using N workers for full compaction`, `Evacuation Failure`, heap before/after và duration.
7. `-XX:ParallelGCThreads` không tạo tăng tốc tuyến tính; `-XX:ConcGCThreads` có vai trò khác.
8. Mục tiêu vận hành là **tránh Full GC fallback và đáp ứng SLO ứng dụng bằng số liệu**, không “ép Full GC xong trong N ms”.
9. Code lab minh họa vượt mục tiêu 1 ms, **không** đưa `System.gc()` hoặc cấu hình lab vào production như mẹo tối ưu.
10. Tuning phải cân bằng latency, throughput, memory footprint, CPU và chi phí vận hành trên workload thực tế.

## Tài liệu tham khảo chính thức và hiện hành

- OpenJDK **JEP 307 — Parallel Full GC for G1**, delivered in Java 10: https://openjdk.org/jeps/307
- Oracle Java SE 27 — **Garbage-First (G1) Garbage Collector** (G1 is not a real-time collector, Full GC fallback, ergonomics): https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html
- Oracle Java SE 27 — **Garbage-First Garbage Collector Tuning** (soft goal, Full GC diagnosis, humongous objects, logs): https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html
- Dev.java — **The G1 Garbage Collector**, mục tiêu pause mềm và các trade-offs: https://dev.java/learn/jvm/tool/garbage-collection/g1gc-overview/
- Oracle Java SE — **The java Command**, `-XX:MaxGCPauseMillis` và unified logging `-Xlog`: https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- Java SE 27 — **JDK Flight Recorder**, quan sát các sự kiện runtime/GC: https://docs.oracle.com/en/java/javase/27/jfapi/
- OpenJDK **JEP 423 — Region Pinning for G1**, bối cảnh evacuation failure với pinned objects: https://openjdk.org/jeps/423
