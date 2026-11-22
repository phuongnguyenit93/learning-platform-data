# Song song hóa Full GC và mục tiêu giảm độ trễ xấu nhất — G1 trong Java 10+

## 1. Vấn đề: Full GC làm đứt quãng một ứng dụng đang chạy

Giả sử một dịch vụ Java có thời gian phản hồi phần lớn yêu cầu chỉ vài chục mili giây, nhưng thỉnh thoảng có một yêu cầu mất vài giây. Đo CPU và network chưa chắc chỉ ra nguyên nhân; một khả năng cần kiểm tra là **Stop-The-World (STW) Full Garbage Collection**.

**Garbage-First Garbage Collector (G1 GC)** được thiết kế để thu hồi bộ nhớ theo nhiều vùng (*region*) và thực hiện phần lớn công việc ở những chu kỳ nhỏ hơn, có một số công việc chạy đồng thời với ứng dụng. Mục tiêu của G1 là dung hòa throughput và pause time. Tuy nhiên, khi không thể thu hồi bộ nhớ đủ nhanh hoặc gặp tình huống không còn không gian phù hợp để phân bổ, G1 vẫn có thể phải thực hiện **Full GC**, thường là một đợt compaction toàn heap làm dừng các thread ứng dụng.

Trước Java 10, đường **Full GC fallback của G1** dùng thuật toán **mark–sweep–compact đơn luồng**. Trong các tình huống xấu, một thread phải làm công việc trên phạm vi lớn của heap, khiến thời gian dừng có thể đặc biệt dài. **JEP 307 — Parallel Full GC for G1**, được đưa vào **Java 10**, đã chuyển đường Full GC sang xử lý song song bằng nhiều GC worker nhằm **cải thiện worst-case latency** khi fallback Full GC thực sự xảy ra.

Đây là thay đổi về implementation của HotSpot JVM, không phải một API mà lập trình viên phải gọi để “bật” mỗi lần. Các thế hệ JDK hiện nay tiếp tục có cơ chế **G1 Full GC chạy song song**; kiến thức này vẫn hữu ích khi phân tích log và tối ưu độ trễ.

### Mục tiêu học tập

Sau bài này, bạn cần giải thích được:

1. Khác biệt giữa **parallel** và **concurrent**, giữa G1 young/mixed collection và Full GC.
2. Vì sao JEP 307 cải thiện tình huống xấu nhưng không biến Full GC thành một sự kiện không dừng ứng dụng.
3. Vì sao `-XX:ParallelGCThreads` liên quan đến Full GC của G1, đồng thời ảnh hưởng young/mixed collections.
4. Cách nhận diện `Pause Full (G1 Compaction Pause)` và số worker trong GC log trên JDK đang dùng.
5. Cách tạo một **thử nghiệm nhỏ để học GC**, tách biệt hoàn toàn với quy trình vận hành production.
6. Vì sao **ưu tiên ngăn Full GC lặp lại** thường tốt hơn chỉ tìm cách làm Full GC nhanh hơn.
7. Phương pháp phân tích worst-case pause và các chỉ số tail latency mà không suy diễn từ benchmark nhỏ.

## 2. G1 có những cơ chế thu gom nào?

G1 chia heap thành các region có kích thước thống nhất, tùy cấu hình JVM. Region được dùng linh hoạt cho các mục đích như Eden, Survivor, Old và các đối tượng rất lớn (*humongous objects*). Thay vì luôn quét toàn bộ heap cho từng lần thu gom, G1 có thể thu hồi **một tập region** được chọn.

| Cơ chế | Phạm vi/đặc điểm | Ứng dụng có dừng? | Mục đích |
| --- | --- | --- | --- |
| **Young GC** | Evacuate các vùng trẻ được chọn | **Có**, trong pause STW; nhiều GC worker có thể làm song song | Thu hồi đối tượng ngắn hạn |
| **Mixed GC** | Các vùng trẻ và một số vùng già được chọn | **Có**, theo pause STW song song | Thu hồi dần bộ nhớ ở old generation |
| **Concurrent marking** | Tìm đối tượng sống trong heap khi ứng dụng vẫn chạy ở một số pha | **Một số pha chạy đồng thời**; vẫn có remark/cleanup pause riêng | Chuẩn bị thông tin để thu hồi old regions |
| **Full GC của G1** | Thu gom/compaction trên phạm vi heap khi fallback | **Có — STW**; từ Java 10, phần full compaction được song song hóa | Cố phục hồi không gian khi các cơ chế thường lệ không đủ |

**Hai chữ dễ nhầm:**

- **Parallel:** có **nhiều worker** cùng làm một phần công việc GC; trong G1 Full GC, các thread ứng dụng vẫn bị dừng. “Parallel” không đồng nghĩa “không có pause”.
- **Concurrent:** một phần công việc GC chạy **chồng thời gian với application threads**. G1 concurrent marking có các pha concurrent, nhưng G1 không phải collector bảo đảm mọi công việc GC diễn ra mà không cần STW.

Trong tài liệu Oracle Java SE 27, G1 được mô tả là collector cố đáp ứng pause target với **xác suất cao**, **không phải real-time collector** bảo đảm từng pause ngắn hơn một ngưỡng tuyệt đối.

### Sơ đồ cơ chế thu hồi thường lệ và fallback

```text
Application allocations
         |
         v
 G1 young-only collections (STW, parallel evacuation)
         |
         +----> Concurrent marking of old regions
         |                |
         |                v
         |         Mixed collections
         |         (STW, selected old + young regions)
         |                |
         +----------------+
         |
         | Nếu không giải phóng đủ chỗ / evacuation thất bại /
         | áp lực phân bổ làm chậm hoàn thành chu kỳ
         v
 G1 Full GC fallback
   Stop-The-World toàn bộ application threads
   Parallel mark / compaction with GC workers (Java 10+)
         |
         v
 Application resumes, nếu còn khả năng hoạt động
```

Đây là sơ đồ khái niệm: HotSpot có thêm nhiều pha cụ thể và một số lý do Full GC khác. Không phải mọi ứng dụng đều sẽ đi qua đường Full GC.

## 3. JEP 307 thay đổi gì ở Java 10?

**JEP 307 — Parallel Full GC for G1** có mục tiêu chính: **cải thiện độ trễ G1 trong tình huống xấu nhất bằng cách làm Full GC song song**.

Trước mốc Java 10:

- Full GC fallback của G1 thực hiện **mark–sweep–compact bằng một thread**.
- Những đợt GC bình thường khác của G1 đã dùng song song hóa ở nhiều công việc.
- Khi bị buộc phải Full GC, toàn bộ ứng dụng có thể gặp một khoảng dừng dài.

Từ Java 10:

- Đường Full GC được **song song hóa**, dùng các GC worker thay vì phụ thuộc duy nhất vào một thread.
- Mức song song cơ bản liên quan tới `-XX:ParallelGCThreads`, cùng nhóm worker được dùng trong young/mixed collections.
- Mục tiêu là **giảm thời gian dừng** khi Full GC bất khả kháng, đặc biệt khi heap có nhiều công việc cần xử lý.

**JEP 307 không đặt mục tiêu** khiến Full GC của G1 bằng hoặc nhanh hơn Full GC của *Parallel GC collector* trong mọi workload. Đừng nhầm hai khái niệm:

- **G1 Full GC chạy song song**: một đường fallback của **G1 collector**.
- **Parallel GC**: một garbage collector khác, ưu tiên throughput với kiến trúc riêng.

Không nên bật `-XX:+UseParallelGC` rồi tuyên bố đang kiểm chứng JEP 307. Muốn quan sát G1, hãy dùng `-XX:+UseG1GC` để chọn đúng collector.

### Vì sao cải thiện nhưng không bảo đảm giới hạn latency?

Ngay cả khi có N worker:

1. Không phải tất cả pha compaction đều song song hoàn hảo.
2. Vẫn có overhead đồng bộ, phân chia công việc, scan root/metadata và các chi phí VM khác.
3. Có thể thiếu CPU thực do container quota hoặc host contention.
4. Băng thông bộ nhớ và lượng live object có thể trở thành nút thắt.
5. Heap lớn, phân mảnh nhiều hoặc tỷ lệ object sống cao tạo khối lượng công việc lớn.
6. Full GC vẫn phải **dừng ứng dụng**, nên một pause có thể vượt xa `MaxGCPauseMillis`.

Cải thiện **worst-case latency** ở đây là mục tiêu thực tế của một implementation, **không phải hard bound** như yêu cầu của một hệ thống real-time.

## 4. Các pha làm việc khi G1 Full GC song song

Có thể hình dung đường full compaction bằng các bước:

```text
Stop all application Java threads
          |
          v
1. Mark live objects
          |
2. Prepare compaction / calculate destination areas
          |
3. Adjust pointers / update references
          |
4. Compact heap / move live objects
          |
5. Reset metadata / finish bookkeeping
          |
Resume application threads
```

Trên một bản HotSpot JDK hiện đại đã được thử, `-Xlog:gc*=info` hiển thị các pha tên gần như:

```text
Phase 1: Mark live objects
Phase 2: Prepare compaction
Phase 3: Adjust pointers
Phase 4: Compact heap
Phase 5: Reset Metadata
```

**Cảnh báo về sự phụ thuộc implementation:** số pha, tên pha và khả năng song song của từng sub-phase có thể thay đổi theo phiên bản/build JDK. Không viết code nghiệp vụ phân tích hard-coded đúng “5 pha” như một hợp đồng Java SE. Điều mang tính nền tảng là Full GC của G1 vẫn **STW** và có nhiều GC worker thực hiện compaction khi đủ điều kiện.

### Song song không có nghĩa tăng tốc tuyến tính

Giả sử một phần của công việc Full GC không thể chạy song song hoặc bị giới hạn bởi băng thông nhớ. Dù tăng từ 1 lên 4 worker, không được giả định pause sẽ từ 400 ms xuống đúng 100 ms.

Một mô hình lý thuyết thường dùng để giải thích giới hạn là:

```text
S(N) <= 1 / ((1 - P) + P/N)

S(N): tốc độ tương đối so với 1 worker
P: phần công việc có thể song song hóa
N: số worker
```

Mô hình này chưa tính overhead thực, scheduling và memory bandwidth. Nó không phải công thức dự đoán chính xác duration của G1 trong production; dùng để hiểu vì sao “gấp đôi threads” **không bảo đảm** “giảm một nửa pause”.

## 5. Khi nào G1 bị buộc phải Full GC?

G1 cố gắng tránh Full GC bằng các pha young, concurrent marking và mixed collections, nhưng Full GC có thể xảy ra khi hệ thống không còn không gian hoặc không có kết quả thu hồi đủ nhanh.

Các tình huống cần kiểm tra:

- **Áp lực old generation**: tốc độ phân bổ/promote vượt khả năng concurrent marking và space reclamation.
- **Evacuation failure**: thiếu không gian đích để chuyển đối tượng sống trong một pause thông thường.
- **Humongous allocation / fragmentation**: cần một vùng liên tục đủ lớn cho object có kích thước vượt ngưỡng humongous.
- **Concurrent marking hoàn thành quá muộn**: G1 chưa sẵn sàng thu hồi old regions trước khi allocation pressure tăng cao.
- **Yêu cầu Full GC tường minh** từ ứng dụng hoặc công cụ quản trị, ví dụ `System.gc()`, nếu cờ/runtime cho phép và yêu cầu đó được xử lý bằng Full GC.
- **Một số nguyên nhân đặc thù VM**: tùy phiên bản, loại allocation hoặc tooling có thể tạo yêu cầu GC khác nhau.

**Không thể quy mọi Full GC về “heap quá nhỏ”.** Có thể còn liên quan tốc độ phân bổ, quá nhiều object sống lâu, đối tượng humongous, fragment, container limits và việc ép GC từ bên ngoài.

Một số log liên quan:

```text
Pause Young (Normal) (G1 Evacuation Pause)
Pause Young (Mixed) (G1 Evacuation Pause)
Pause Full (G1 Compaction Pause)
Pause Full (System.gc())
```

Đây là các **mẫu label**, không nhất thiết xuất hiện cùng nhau hoặc giống từng ký tự trên mọi JDK. Nội dung trong ngoặc có thể ghi loại/cause khác nhau. Để kết luận sự kiện nào đã xảy ra, hãy đọc **log thực tế**.

## 6. Vì sao Full GC liên quan trực tiếp đến “tail latency”?

Một số ứng dụng báo thời gian phản hồi qua trung bình. Ví dụ hầu hết request 20 ms nhưng có request ngẫu nhiên 2 giây khi JVM Full GC. Average có thể chỉ tăng nhẹ; người dùng đang gặp request bị pause sẽ thấy lỗi latency rất rõ.

Cần phân biệt:

- **Average latency**: trung bình thời gian phản hồi.
- **p95/p99/p99.9**: thời gian phản hồi mà 95%/99%/99.9% request đạt hoặc thấp hơn.
- **Maximum latency**: request lâu nhất trong khoảng đo.
- **GC pause real time**: thời gian JVM dừng application threads vì GC; không phải toàn bộ response latency của từng request.
- **Worst-case GC latency** trong JEP 307: tập trung cải thiện các khoảng dừng Full GC đặc biệt xấu, **không** nói mọi request đều được bảo đảm một ngưỡng.

Nếu một đợt Full GC xảy ra khi nhiều request đang chờ thực thi, có thể tạo **cụm request cùng chậm**. Nhưng tương quan về thời gian chưa tự chứng minh tất cả request chậm đều do GC. Cần đối chiếu GC log với thời gian request tracing, CPU steal/throttling, lock contention, disk I/O và các yếu tố ngoài JVM.

### “Giảm Full GC time” và “giảm Full GC frequency” là hai mục tiêu khác

- JEP 307 giảm **chi phí fallback** mỗi khi Full GC phải xảy ra.
- Tuning ứng dụng/heap/G1 để **không rơi vào fallback** thường đem lại lợi ích tail latency bền vững hơn.
- Một ứng dụng có Full GC dài 200 ms **50 lần/phút** có thể xấu hơn ứng dụng gặp một Full GC dài 400 ms hiếm khi xảy ra, tùy SLO.

Đừng chỉ tối ưu **độ dài của một pause** mà bỏ qua số lần, tần suất, mức sử dụng heap và chất lượng đáp ứng của hệ thống.

## 7. Cờ ParallelGCThreads và cái giá khi tăng song song

Trong HotSpot, `-XX:ParallelGCThreads=N` đặt số worker tối đa dùng cho công việc GC song song được các collector hỗ trợ. JEP 307 sử dụng số worker liên quan tới các lần thu gom young/mixed của G1.

Ví dụ chạy thử:

```bash
java -XX:+UseG1GC -XX:ParallelGCThreads=4 -Xms64m -Xmx64m -Xlog:gc*=info -cp . G1FullGcParallelDemo
```

Câu lệnh chỉ minh họa môi trường đã biên dịch class demo và sử dụng một heap nhỏ phục vụ kiểm tra, **không phải cấu hình đề xuất cho sản phẩm thực tế**.

**Đánh đổi cần nhớ:**

- Tăng số worker có thể rút ngắn một số pha khi đủ CPU và công việc.
- Quá nhiều worker có thể tăng overhead phối hợp và contention, làm giảm lợi ích.
- VM có thể giới hạn số worker thực sự sử dụng theo kích thước heap, tài nguyên host hoặc ergonomics của phiên bản.
- Khi JVM chạy trong container, số CPU có thể bị giới hạn bởi quota/cpuset, không tương ứng số core của host.
- Cờ này **không chỉ tác động Full GC** mà còn tác động đến các pause song song khác của G1.
- Không nhầm với `-XX:ConcGCThreads` — cờ về số thread dành cho **concurrent marking**, không phải “bật parallel Full GC”.

Một chiến lược kiểm thử thích hợp là so sánh 1, 2, 4 worker **trên cùng workload và môi trường**, đo duration, CPU và tail latency. Không chọn giá trị chỉ vì log thông báo nhiều worker hơn.

### Bảng so sánh các tùy chọn

| Tùy chọn | Vai trò | Điều không nên hiểu |
| --- | --- | --- |
| `-XX:+UseG1GC` | Chọn G1 trong HotSpot | Không ép tất cả pause phải ngắn |
| `-XX:ParallelGCThreads=N` | Mức song song của nhiều hoạt động GC STW | Không chỉ dành cho Full GC |
| `-XX:ConcGCThreads=N` | Số thread của công việc G1 concurrent marking | Không thay trực tiếp số full compaction workers |
| `-XX:MaxGCPauseMillis=N` | **Mục tiêu mềm** để G1 chọn kích thước công việc một số pause | **Không giới hạn cứng Full GC** |
| `-Xmx...` | Giới hạn heap tối đa | Không sửa memory leak hoặc bảo đảm không có Full GC |
| `-Xms...` | Heap ban đầu | Không quyết định chính sách full compaction |
| `-XX:G1HeapRegionSize=...` | Kích thước region, ảnh hưởng humongous allocations | Không có một region size đúng cho mọi workload |
| `-Xlog:gc*=info` | Log sự kiện GC và thông tin liên quan | Không làm chương trình nhanh hơn |

Nên bắt đầu bằng **mặc định G1 và một heap size hợp lý**, sau đó thay từng cấu hình với bằng chứng đo. Tài liệu Oracle khuyên tránh cố định young size bằng `-Xmn` hoặc các cờ tương tự vì điều đó cản trở cơ chế điều chỉnh pause của G1.

## 8. MaxGCPauseMillis không phải giới hạn thời gian của Full GC

Một hiểu lầm nguy hiểm:

```text
-XX:MaxGCPauseMillis=200
=> Mọi GC pause, kể cả Full GC, sẽ không vượt 200 ms
```

**Suy luận này sai.** `MaxGCPauseMillis` là **soft target** mà G1 cố đạt bằng việc điều chỉnh quy mô collection set ở các đợt thu gom thường lệ. Khi rơi vào đường Full GC fallback cần compaction rộng hơn, việc dừng ứng dụng có thể vượt xa target này.

Ví dụ:

- Ứng dụng đặt target 200 ms.
- Young/mixed GCs có thể thường đạt gần target.
- Một Full GC hiếm gặp kéo dài 1.5 giây.
- Không có sự “vi phạm hợp đồng Java” vì target vốn không phải hard guarantee.

Để xử lý vấn đề, hãy ưu tiên **đọc nguyên nhân Full GC** và đánh giá live set/allocation pressure. Chỉ giảm `MaxGCPauseMillis` sẽ không trực tiếp chữa fallback Full GC, và đôi khi còn tạo tradeoff khiến workload khó phục hồi không gian hơn.

Nếu sản phẩm cần pause thấp hơn rất nhiều với SLO nghiêm ngặt, cần benchmark collector/phương án runtime phù hợp (ví dụ ZGC trên JDK hỗ trợ), cấu trúc ứng dụng và tiêu chí throughput/footprint; không coi G1 là collector real-time.

## 9. Chương trình Java 10+ mô phỏng yêu cầu Full GC để đọc log

**Phần này là một thí nghiệm được kiểm soát.** Nó gọi `System.gc()` nhằm tạo một sự kiện chẩn đoán dễ nhận diện trên HotSpot/G1 với bộ cờ phù hợp. **Không thêm lời gọi này vào ứng dụng production chỉ để thử cải thiện độ trễ.** Gọi Full GC thủ công thường làm ứng dụng dừng lâu hơn, chứ không phải cách tối ưu.

Tạo file **`G1FullGcParallelDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public final class G1FullGcParallelDemo {
    private static volatile byte[][] keepAlive;

    public static void main(String[] args) {
        byte[][] blocks = new byte[8][];
        for (int i = 0; i < blocks.length; i++) {
            blocks[i] = new byte[256 * 1024];
            blocks[i][0] = (byte) i;
        }
        keepAlive = blocks;

        boolean hasG1 = false;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (bean.getName().contains("G1")) {
                hasG1 = true;
            }
        }
        System.out.println("g1CollectorPresent=" + hasG1);
        System.out.println("requestExplicitGC=true");
        System.gc();
        System.out.println("retainedBlocks=" + keepAlive.length);
        keepAlive = null;
        System.out.println("completed=true");
    }
}
```

Biên dịch bằng JDK có hỗ trợ mục tiêu Java 10:

```bash
javac --release 10 G1FullGcParallelDemo.java
```

Chạy thí nghiệm với HotSpot JDK hiện đại:

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m -XX:ParallelGCThreads=4 -Xlog:gc*=info G1FullGcParallelDemo
```

**Các dòng output của chương trình** đã được kiểm chứng:

```text
g1CollectorPresent=true
requestExplicitGC=true
retainedBlocks=8
completed=true
```

Các dòng này không cần việc Full GC có đúng số mili giây nào. Chúng chỉ xác nhận chọn collector chứa tên G1, gửi yêu cầu GC, các block được giữ sống qua yêu cầu, rồi chạy hết chương trình.

### Trích đoạn GC log trong lần chạy được kiểm chứng

Bên cạnh stdout của chương trình, HotSpot đã ghi:

```text
[info][gc     ] Using G1
[info][gc,init] Parallel Workers: 4
[info][gc,start] GC(0) Pause Full (System.gc())
[info][gc,task] GC(0) Using 4 workers of 4 for full compaction
[info][gc,phases,start] GC(0) Phase 1: Mark live objects
[info][gc,phases,start] GC(0) Phase 2: Prepare compaction
[info][gc,phases,start] GC(0) Phase 3: Adjust pointers
[info][gc,phases,start] GC(0) Phase 4: Compact heap
[info][gc,phases,start] GC(0) Phase 5: Reset Metadata
[info][gc] GC(0) Pause Full (System.gc()) 5M->3M(64M) 1.768ms
```

Đây là **trích đoạn rút gọn từ một lần chạy**: đã bỏ timestamp, độ rộng cột và những dòng log xen giữa để dễ đọc. **Số GC(0), 1.768 ms, 5M→3M, tên/số pha và số worker** là kết quả **của môi trường thử**, không phải một expected stdout dùng cho tất cả JDK.

Kết luận có căn cứ từ trích đoạn:

1. `Using G1`: JVM chọn G1 đúng yêu cầu.
2. `Parallel Workers: 4`: bộ worker song song được cấu hình theo giá trị thử.
3. `Pause Full (System.gc())`: yêu cầu thử dẫn tới một **Full GC**, không phải một young collection.
4. `Using 4 workers of 4 for full compaction`: HotSpot trong lần chạy này thực sự dùng **bốn worker** cho full compaction.
5. Có các pha mark, prepare, adjust, compact và cleanup/reset metadata.
6. Sau đó chương trình tiếp tục: đó là **STW pause**, không phải JVM ngừng vĩnh viễn.

**Tính portable của thí nghiệm:** `System.gc()` là một yêu cầu/hint theo hợp đồng API, JVM có quyền quyết định cách đáp ứng. Nếu môi trường dùng `-XX:+DisableExplicitGC`, cờ concurrent cho explicit GC hoặc một implementation khác, yêu cầu này không nhất thiết tạo Full GC như trên. Vì vậy muốn học cụ thể JEP 307, chạy trên **HotSpot G1, đúng cờ đã nêu**, và xác minh log thay vì khẳng định mặc định mọi JDK.

## 10. Giải thích vì sao giữ đối tượng còn sống

Trong chương trình:

```java
private static volatile byte[][] keepAlive;
```

Các mảng được giữ qua một static field để vẫn có tham chiếu sống khi `System.gc()` chạy. Điều này giúp minh họa rằng GC không được thu hồi những block đang còn reachable chỉ vì đã được yêu cầu Full GC.

```java
System.out.println("retainedBlocks=" + keepAlive.length);
```

In `8` sau sự kiện GC cho thấy code còn giữ được tham chiếu hợp lệ. Tuy nhiên, đây **không phải kiểm chứng toàn bộ tính đúng đắn của JVM** và không phải benchmark Full GC có ý nghĩa về hiệu năng: dữ liệu chỉ khoảng vài MB, thời gian dừng có thể cực nhỏ, overhead JVM/JIT/log đã chiếm tỷ trọng đáng kể.

### Tại sao không cấp phát hàng GB chỉ để ép Full GC?

Không cần thiết và dễ gây rủi ro cho máy chạy thử. Một workload cố tình gây thiếu bộ nhớ có thể ném `OutOfMemoryError`, gây thrashing hoặc ảnh hưởng các tiến trình khác. Để học hành vi song song, dùng **explicit GC trong môi trường thử nhỏ** và xem worker log là đủ.

Để đánh giá Full GC khi **heap pressure thật**, cần một workload mô phỏng allocation rate/live set giống sản phẩm và công cụ đo kiểm có giới hạn tài nguyên; không biến thí nghiệm học thành stress test vô kiểm soát.

## 11. Kiểm chứng số worker và thứ tự so sánh đúng

Trong một thí nghiệm riêng, có thể chạy cùng chương trình với các cấu hình:

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m -XX:ParallelGCThreads=1 -Xlog:gc*=info G1FullGcParallelDemo

java -XX:+UseG1GC -Xms64m -Xmx64m -XX:ParallelGCThreads=4 -Xlog:gc*=info G1FullGcParallelDemo
```

Cách đọc:

- Kiểm tra log `Using N workers ... for full compaction` để xem VM **thực sự dùng bao nhiêu worker**.
- So sánh **real time của Full GC**, không chỉ CPU user time.
- Chạy nhiều lần với CPU quota và điều kiện tương tự.
- So lượng live data, heap size, loại allocation, cấu hình và phiên bản JDK.
- Nếu thấy kết quả 1 worker nhanh hơn trên bài test cực nhỏ, **không phải JEP 307 thất bại**; overhead song song có thể chiếm tỷ trọng lớn khi công việc quá ít.

**Không hứa kết quả có thứ tự:** chạy cấu hình 4 worker không bảo đảm pause ngắn hơn 1 worker trong mọi run. JEP 307 đặc biệt nhắm cải thiện tình huống Full GC nặng, nơi chia việc nhiều thread có cơ hội giúp giảm phần dừng dài.

Cũng không nên chỉ so `-XX:ParallelGCThreads` trên workload tự nhiên mà không biết có Full GC hay không: nếu cả hai run đều **không có Full GC**, thử nghiệm chưa kiểm chứng được phần cải tiến này.

## 12. Từ GC log đến dấu hiệu “Full GC xấu”

Trên JDK hiện đại, Oracle khuyên bắt đầu bằng:

```bash
-Xlog:gc*=debug
```

hoặc mức thông tin vừa đủ như:

```bash
-Xlog:gc*=info
```

và tăng độ chi tiết khi cần. Một log chuẩn có thể chứa:

- **Cause** của GC: allocation failure, humongous allocation, explicit request, v.v.
- **Loại collection**: Young, Mixed, Concurrent Mark hoặc Pause Full.
- **Heap before/after**, kích thước heap, vùng humongous.
- **Duration** của pause.
- **Số GC worker** hoặc thời gian từng pha.
- Các thông tin hệ điều hành và CPU time của GC.

Ví dụ một mẫu được Oracle dùng để nhận diện:

```text
Pause Full (G1 Compaction Pause)
```

Trong bài chẩn đoán, tìm sự kiện này và phân tích **những event liền trước**, đặc biệt evacuation failure, concurrent marking chưa hoàn thành hoặc mức old/humongous occupancy.

Đừng chỉ nhìn dòng Full GC cuối rồi kết luận giải pháp là tăng worker.

### Thêm timestamp hữu ích trong production

Ví dụ với unified logging:

```bash
java -XX:+UseG1GC -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar app.jar
```

Đây là minh họa launcher; cần thay `app.jar` bằng artifact thật, đảm bảo quyền ghi log và chính sách rotation/thu thập log. Không tắt logging để che các Full GC; nhưng cần quản lý lượng log phù hợp.

Khi có timestamp, có thể tương quan với request traces, p99 response latency, CPU load và container memory/CPU pressure.

### CPU time không phải wall-clock pause

GC log có thể ghi:

```text
User=...
Sys=...
Real=...
```

- `User` là tổng thời gian CPU user-mode, **có thể lớn hơn Real** khi nhiều worker chạy song song.
- `Sys` là thời gian CPU kernel.
- `Real` gần với thời gian thực trôi qua trong sự kiện.

**Không lấy User CPU time làm thời gian STW mà người dùng chịu.** Cần đối chiếu wall-clock pause và response-time tail. Nếu Real lớn bất thường so với CPU times, kiểm tra scheduling/CPU throttling, swap/I/O và hạ tầng.

## 13. Ngăn Full GC lặp lại: chiến lược đáng ưu tiên

Ngay cả khi JEP 307 làm Full GC nhanh hơn, **tránh fallback** vẫn là mục tiêu hiệu năng quan trọng. Tài liệu G1 tuning của Oracle nhấn mạnh giải pháp phụ thuộc nguyên nhân thực.

### 13.1. Kiểm tra live set và allocation rate

Nếu ứng dụng giữ quá nhiều object sống lâu, Full GC có thể không giải phóng nhiều. Cần xác định:

- Cache có giới hạn kích thước/TTL không?
- Collection trong heap có tăng không giới hạn?
- Request có tạo quá nhiều object tạm?
- Dữ liệu lẽ ra được stream nhưng lại load toàn bộ vào RAM?
- Có reference leak, listener/session không được giải phóng?

Nếu `usedAfterFullGC` tiếp tục tăng qua nhiều sự kiện, đó là dấu hiệu **cần điều tra live set**, không phải bằng chứng tự động về memory leak. Có thể có growth hợp lệ của dữ liệu ứng dụng hoặc bộ nhớ cache.

### 13.2. Heap headroom và cấu hình -Xmx

Một heap quá nhỏ so với live set và allocation pressure có thể gây Full GC. Tăng `-Xmx` **khi còn RAM và giới hạn container phù hợp** có thể tạo thêm thời gian cho concurrent marking hoàn thành.

Nhưng không tăng `-Xmx` vô hạn: heap lớn có tradeoff footprint, thời gian thu hồi và giới hạn bộ nhớ vật lý. Nếu ứng dụng thật sự leak, tăng heap thường chỉ trì hoãn sự cố.

### 13.3. Concurrent marking bắt đầu đủ sớm

G1 dùng cơ chế liên quan **Initiating Heap Occupancy Percent (IHOP)** để quyết định thời điểm bắt đầu concurrent marking; trên JDK hiện đại có cơ chế adaptive IHOP.

Nếu allocation rate tăng nhanh khiến marking không kịp hoàn thành, cần quan sát log và đánh giá:

- Dung lượng heap/headroom.
- `-XX:ConcGCThreads` nếu concurrent marking thiếu CPU.
- `-XX:G1ReservePercent` và thông tin về buffer theo adaptive IHOP.
- Các flag IHOP trực tiếp **chỉ khi có bằng chứng cần can thiệp**.

Đừng copy một giá trị IHOP cứng từ bài blog cũ rồi áp vào mọi ứng dụng. HotSpot có heuristics hiện đại; cấu hình không phù hợp có thể làm GC chạy quá sớm hoặc quá muộn, khiến throughput và pause time xấu hơn.

### 13.4. Humongous objects và fragmentation

Trong G1, object lớn (thường theo ngưỡng khoảng **một nửa kích thước region**) được xem là *humongous* và có cách phân bổ đặc biệt, có thể gây fragmentation.

Gợi ý chẩn đoán:

```text
Humongous regions: X->Y
```

Nếu số humongous regions lớn và liên quan Full GC, có thể đánh giá lại kích thước mảng/buffer hoặc `-XX:G1HeapRegionSize`. Tuy nhiên, tăng region size làm thay đổi những tradeoff khác, **không phải một cách chữa chung**.

### 13.5. Tránh Full GC tường minh không có lý do

Nếu log có:

```text
Pause Full (System.gc())
```

hãy tìm thành phần gọi `System.gc()`: mã ứng dụng, thư viện, công cụ quản lý, test hook hoặc agent.

Trong production, việc gọi GC tường minh theo lịch thường **không giúp ngăn GC xấu** và có thể làm ứng dụng ngừng phục vụ. Nếu không thể sửa nguồn gọi, Oracle nêu những lựa chọn VM riêng như `-XX:+DisableExplicitGC` hoặc `-XX:+ExplicitGCInvokesConcurrent` trong điều kiện phù hợp. Đây là cấu hình phải đánh giá theo workload và tương tác với thư viện/tooling; **không bật bừa như phương thuốc cho mọi Full GC**.

## 14. Đánh giá kết quả trên production: đo đúng worst-case

Một thí nghiệm hiệu năng có ý nghĩa nên đặt câu hỏi:

1. **Đã có Full GC không?** Nếu không, không thể kết luận parallel Full GC đã tạo lợi ích trực tiếp.
2. **Full GC có bao nhiêu lần?** Tần suất theo phút/giờ và theo giai đoạn tải.
3. **Pause duration ra sao?** Trung bình, p95/p99 của chính Full GC nếu đủ mẫu, lớn nhất trong cửa sổ đo.
4. **Đã có bao nhiêu application requests bị chậm?** Tương quan timestamp GC với p99/p99.9 response latency và tracing.
5. **GC worker có bao nhiêu?** Cấu hình và số worker thực sự sử dụng.
6. **Heap sau Full GC còn bao nhiêu?** Nếu vẫn gần đầy, cần xem lượng live data.
7. **Concurrent marking có kịp không?** Thời gian và sự kiện của old-generation reclamation.
8. **CPU có bị hạn chế?** Quota/container limits, host scheduling, NUMA hoặc memory bandwidth.
9. **Cấu hình test có sát production?** Live set, allocation rate, dependency/JDK build và môi trường triển khai.
10. **Có đổi thứ khác đồng thời không?** Không nên đổi heap, worker threads và GC collector cùng lúc rồi quy toàn bộ khác biệt cho JEP 307.

### Ví dụ báo cáo so sánh có trách nhiệm

Thay vì viết:

> “Parallel Full GC giúp giảm mọi pause 4 lần.”

Nên báo cáo kiểu:

```text
JDK/HotSpot build: <ghi rõ>
GC collector: G1
Workload: <mô tả>
CPU quota / Xmx / heap occupancy: <ghi rõ>
ParallelGCThreads: <giá trị>
Full GC count: <đo thực>
Full GC duration distribution: <đo thực>
Max observed Full GC pause: <đo thực>
Request p99/p99.9: <đo thực>
Conclusion: <nêu tương quan và giới hạn>
```

Các trường trong mẫu là hướng dẫn **cách trình bày một kết quả đo**, không phải output đã đo của một hệ thống cụ thể.

## 15. Khi Full GC gây OutOfMemoryError hoặc vẫn không giải phóng được đủ

Song song hóa Full GC **không có khả năng tạo ra bộ nhớ mới** nếu live set đã chiếm hầu hết heap. Sau Full GC, có thể vẫn không còn đủ chỗ cấp phát, dẫn đến `OutOfMemoryError` hoặc lỗi cấp phát tiếp theo.

Ví dụ hai trường hợp:

- **GC trả về nhiều bộ nhớ nhưng app liên tục tạo object nhanh:** cần xem allocation rate, young/mixed cycles, throughput và headroom.
- **GC trả về rất ít bộ nhớ vì nhiều object vẫn reachable:** cần xem cache giữ dữ liệu, dữ liệu hoạt động hợp lệ, reference chains hoặc leak.

Đừng kỳ vọng tăng `ParallelGCThreads` làm giảm live set hoặc sửa lỗi logic giữ tham chiếu.

**Thêm worker** có thể giúp xử lý nhanh hơn một lượng công việc nhất định; nó **không thể thay thế** capacity planning, điều tra memory leak hoặc thiết kế data lifecycle.

## 16. So sánh G1 Full GC với những collector khác mà không nhập nhằng

Có hai đối chiếu hữu ích:

### G1 và Parallel GC

- G1 tối ưu cân bằng throughput/latency bằng thu gom incremental và concurrent marking.
- Parallel GC nhấn mạnh throughput và sử dụng thuật toán riêng, có các pha stop-the-world song song.
- JEP 307 chỉ làm **fallback Full GC của G1 chạy song song**; nó không biến G1 thành Parallel GC hoặc sao chép tất cả đặc tính của collector đó.
- JEP 307 nói rõ **không đặt mục tiêu** thắng hoặc bằng Parallel collector Full GC trong mọi workload.

### G1 và collector hướng low-latency hơn

Một số JDK hiện đại hỗ trợ các collector có mô hình concurrent khác, chẳng hạn ZGC, để nhắm các pause ngắn hơn dưới điều kiện và tradeoff riêng.

- Không thể nói “G1 có parallel Full GC nên ngang ZGC về latency”.
- Không thể nói “chỉ bật ZGC là production chắc chắn nhanh hơn”; throughput, footprint, JDK support và workload phải được đo.
- Nếu SLO cực kỳ nhạy với tail pause, lựa chọn GC là một phần của thiết kế, không chỉ là thay đổi một cờ.

Mọi quyết định nên dựa trên **JDK đang được hỗ trợ** và benchmark thực tế, không dùng cấu hình GC cũ không còn được khuyến nghị.

## 17. Những câu nói dễ sai và cách sửa

**Sai 1 — “Full GC của G1 từ Java 10 không còn STW.”**

**Sửa:** Full GC vẫn dừng các application threads. JEP 307 **song song hóa các pha của công việc Full GC** để giảm thời gian dừng.

**Sai 2 — “Parallel nghĩa là cùng chạy với ứng dụng.”**

**Sửa:** Parallel nói về số GC worker; concurrent mới nói một phần công việc GC có thể chạy chồng với ứng dụng.

**Sai 3 — “Đặt `MaxGCPauseMillis=100` thì Full GC tối đa 100ms.”**

**Sửa:** Đây là mục tiêu mềm, không có hard guarantee cho Full GC.

**Sai 4 — “Tăng ParallelGCThreads từ 2 lên 8 bảo đảm Full GC nhanh gấp 4.”**

**Sửa:** Speedup phụ thuộc tính song song, overhead, live data, memory bandwidth, CPU quota và heap.

**Sai 5 — “ParallelGCThreads chỉ ảnh hưởng Full GC.”**

**Sửa:** Nó còn ảnh hưởng các pause song song của young/mixed collection trong G1.

**Sai 6 — “Cứ có Full GC thì phải tăng -Xmx.”**

**Sửa:** Phải xem nguyên nhân: fragmentation, humongous, allocation rate, marking, explicit GC hoặc live set.

**Sai 7 — “Gọi System.gc() sẽ giữ độ trễ ổn định.”**

**Sửa:** Nó có thể tạo STW pause. Chỉ dùng làm **thí nghiệm kiểm tra có chủ đích**, không thêm vào production như tối ưu.

**Sai 8 — “Full GC nhanh hơn nghĩa là không thể OOM.”**

**Sửa:** Nếu object vẫn sống, GC không thu hồi được chúng chỉ vì chạy nhanh hơn.

**Sai 9 — “Chỉ đo average request latency là đủ.”**

**Sửa:** Full GC thường gây tail spikes; cần p99/p99.9 và timestamps GC.

**Sai 10 — “Nhìn log Parallel Workers: 4 là đủ biết mọi pha Full GC dùng bốn threads.”**

**Sửa:** Cần xem dòng *Using N workers for full compaction* và/hoặc log chi tiết; một số pha có serial portions, worker counts phụ thuộc môi trường.

**Sai 11 — “Bản log có năm pha thì mọi JDK đều có đúng năm pha.”**

**Sửa:** Phân chia và tên pha là implementation detail, có thể đổi.

**Sai 12 — “Trộn `-XX:+UseParallelGC` với thử nghiệm JEP 307 vẫn đúng.”**

**Sửa:** Cờ đó chọn collector khác. Để quan sát G1, dùng `-XX:+UseG1GC`.

**Sai 13 — “Để tránh Full GC nên cố định young generation thật nhỏ.”**

**Sửa:** Cấu hình `-Xmn` quá cứng làm mất linh hoạt điều chỉnh young size của G1; Oracle thường khuyên để mặc định và dựa vào log.

**Sai 14 — “GC log có User CPU time 2s nên request bị dừng 2s.”**

**Sửa:** Với song song, CPU user time có thể vượt thời gian thực. Đọc Real time và đối chiếu request traces.

**Sai 15 — “Một stress test nhỏ đo 1.7ms Full GC chứng minh cải tiến worst-case cho production.”**

**Sửa:** Không. Thử nghiệm demo chỉ chứng minh **Full GC và worker song song có hoạt động**. Chứng minh hiệu năng cần tải đại diện, so sánh nhiều run và dữ liệu phân bố latency.

## 18. Checklist trước khi tối ưu

- [ ] JVM thật sự dùng G1, xác nhận qua `java --version` và GC log.
- [ ] JDK/HotSpot đang được hỗ trợ; không sao chép cờ GC đã hết hiệu lực.
- [ ] Phân biệt pause Young/Mixed, Concurrent Marking và Full GC.
- [ ] Biết rằng Full GC vẫn là **Stop-The-World** dù có nhiều worker.
- [ ] Kiểm tra `Pause Full` và cause trong unified GC log.
- [ ] Có timeline đối chiếu request p99/p99.9 với GC pauses.
- [ ] Xem số **ParallelGCThreads** cấu hình và số worker dùng thực.
- [ ] Đã đọc heap occupancy trước/sau Full GC.
- [ ] Kiểm tra evacuation failure và concurrent marking đủ thời gian không.
- [ ] Đã phân tích humongous objects/fragmentation nếu log có dấu hiệu.
- [ ] Kiểm tra các lệnh gọi `System.gc()`/công cụ bên ngoài.
- [ ] Không coi `MaxGCPauseMillis` là hard bound Full GC.
- [ ] Không kỳ vọng nhiều worker luôn giảm pause theo tỷ lệ.
- [ ] Đo cả Full GC **tần suất** và **độ dài**; ưu tiên tránh fallback khi có thể.
- [ ] Xác nhận heap, CPU quota và bộ nhớ host/container có headroom phù hợp.
- [ ] Không sửa nhiều cờ GC cùng lúc rồi suy luận nguyên nhân.
- [ ] Nếu so collector khác, benchmark throughput, latency và footprint.
- [ ] Không gọi `System.gc()` trong production vì mục đích “bật parallel Full GC”.

## 19. Câu hỏi tự kiểm tra và đáp án

**1. JEP nào bổ sung G1 Parallel Full GC vào Java 10?**

**Đáp án:** **JEP 307 — Parallel Full GC for G1**.

**2. Vì sao một G1 collector thường được gọi là “mostly concurrent” vẫn cần Full GC?**

**Đáp án:** Young/mixed và concurrent marking có thể không thu hồi đủ nhanh hoặc gặp các tình huống allocation/fragmentation buộc phải dùng fallback whole-heap compaction.

**3. “Parallel Full GC” có nghĩa application threads vẫn chạy trong Full GC không?**

**Đáp án:** Không. Full GC vẫn STW, chỉ công việc collector được chia cho nhiều GC worker.

**4. Java 10 thay đổi gì so với fallback Full GC trước đó?**

**Đáp án:** Đường mark–sweep–compact của G1 Full GC chuyển từ đơn luồng sang song song nhằm cải thiện worst-case pause.

**5. Có phải JEP 307 hứa Full GC luôn nhanh hơn Parallel GC collector?**

**Đáp án:** Không. JEP này không đặt mục tiêu ngang hiệu năng Parallel collector Full GC trong mọi use case.

**6. `-XX:ParallelGCThreads=4` có bảo đảm thời gian Full GC chia 4 không?**

**Đáp án:** Không. Số worker và speedup phụ thuộc CPU, khối lượng công việc, overhead, bandwidth, các pha không song song và VM ergonomics.

**7. Cờ `-XX:ConcGCThreads` khác gì `-XX:ParallelGCThreads`?**

**Đáp án:** Cờ thứ nhất chủ yếu giới hạn worker cho concurrent marking; cờ thứ hai ảnh hưởng các công việc GC song song trong pause, gồm Full GC.

**8. `-XX:MaxGCPauseMillis=200` có giới hạn cứng Full GC ở 200ms không?**

**Đáp án:** Không. Đây là soft target, Full GC có thể lâu hơn nhiều.

**9. Vì sao không nên gọi System.gc() định kỳ trong production để tối ưu latency?**

**Đáp án:** Nó có thể gây Full GC STW hoặc ảnh hưởng chu kỳ thu gom, làm tăng latency. Thí nghiệm dùng nó chỉ để quan sát log.

**10. Log nào chứng minh G1 Full GC thực sự dùng nhiều worker?**

**Đáp án:** Ví dụ `Using 4 workers of 4 for full compaction` trong `-Xlog:gc*=info` trên HotSpot hỗ trợ.

**11. Tại sao một lần Full GC ngắn trong demo không chứng minh workload production hết tail latency?**

**Đáp án:** Demo có heap nhỏ, live set nhỏ, CPU và môi trường khác. Cần số liệu nhiều run, thời gian thực, p99/p99.9 và trạng thái GC khi tải thật.

**12. Nếu Full GC xong heap vẫn gần đầy, tăng worker giải quyết được không?**

**Đáp án:** Không giải quyết bản chất: object vẫn reachable không thể bị thu hồi. Cần xem live set, caches, retention/leak và capacity.

**13. Một lượng humongous allocations lớn có thể liên quan Full GC như thế nào?**

**Đáp án:** Chúng dùng các region liên tiếp, có thể tạo fragmentation/thiếu chỗ cấp phát. Cần xem log vùng humongous và thiết kế allocation/region size.

**14. Biện pháp nào thường có tác động tốt hơn đến tail latency: giảm Full GC time hay tránh Full GC?**

**Đáp án:** Tùy workload, nhưng với G1, **ngăn fallback Full GC thường đáng ưu tiên** vì Full GC vẫn là một STW toàn heap, dù đã song song hóa.

**15. Tại sao log GC có User time lớn hơn Real time?**

**Đáp án:** Nhiều GC workers có thể dùng CPU đồng thời; User tính tổng CPU time của các thread, còn Real là thời gian thực của pause.

**16. Làm sao so sánh hiệu quả tăng ParallelGCThreads?**

**Đáp án:** Giữ nguyên JDK, heap, workload và CPU quotas, chạy nhiều lần, đọc worker logs và real pause duration, đánh giá p99/p99.9, throughput, CPU/memory, không dựa vào một mẫu.

## 20. Tài liệu chính thức và kiến thức còn hiệu lực

1. [OpenJDK JEP 307 — Parallel Full GC for G1](https://openjdk.org/jeps/307): mục tiêu cải thiện worst-case latency, song song hóa Full GC, phạm vi và non-goals.
2. [Oracle Java SE 25 — Garbage-First G1 GC](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): chu kỳ young/mixed/concurrent và full heap compaction fallback.
3. [Oracle Java SE 25 — G1 GC Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector-tuning.html): cách phân tích Full GC, evacuation failure, IHOP, humongous allocations và GC logging.
4. [Oracle Java SE 27 — G1 GC](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html): G1 không phải real-time collector, giới hạn pause-time và thuật toán incremental.
5. [OpenJDK JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248): mốc G1 trở thành collector mặc định trên server-class systems từ JDK 9.
6. [OpenJDK JEP 523 — Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523): cập nhật mặc định ở JDK 27, nhưng cờ explicit vẫn có giá trị trong thí nghiệm.
7. [dev.java — The G1 Garbage Collector](https://dev.java/learn/jvm/tool/garbage-collection/g1gc-overview/): giải thích G1 hiện đại và tradeoff.
8. [Oracle Java SE 25 — Unified JVM Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xlog:gc*=info`, logging theo tags và levels.

**Kết luận:** Từ Java 10, JEP 307 cho phép **G1 Full GC dùng nhiều worker** để giảm các khoảng dừng tệ nhất của đường fallback trước đây chủ yếu đơn luồng. Tuy nhiên Full GC **vẫn là Stop-The-World**; nhiều worker không tạo ra hard latency bound, và `MaxGCPauseMillis` cũng không bảo đảm một mức tối đa tuyệt đối. Cách vận hành đúng là **đo log, xác minh worker và pause thật**, sau đó ưu tiên giảm nguyên nhân khiến G1 phải Full GC. Tối ưu có giá trị nhất là tối ưu có số liệu và giữ nguyên tính đúng đắn của ứng dụng.
