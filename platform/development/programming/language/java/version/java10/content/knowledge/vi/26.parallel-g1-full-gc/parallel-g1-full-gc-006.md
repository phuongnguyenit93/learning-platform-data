# Java 10 — G1 Full GC song song: phân biệt song song nội bộ và đồng thời với ứng dụng

## 1. Trọng tâm của bài học

Một câu thường gặp khi tìm hiểu Java 10 là: **“G1 Full GC đã được xử lý song song; vậy các luồng ứng dụng có chạy trong lúc Full GC không?”**

**Trả lời ngắn:** **Không.** Trong G1, **Full GC dạng compaction là stop-the-world (STW)**: các luồng ứng dụng (*mutator threads*) bị tạm dừng trong khoảng Full GC. **Song song (*parallel*)** ở đây nghĩa là **nhiều GC worker cùng làm các phần việc thu gom/compact trong lúc thế giới ứng dụng đã dừng**, không phải GC và ứng dụng cùng chạy.

Java 10 đưa vào **JEP 307 — Parallel Full GC for G1**, chuyển cơ chế Full GC dự phòng của G1 từ thuật toán một luồng sang cơ chế **parallel mark–sweep–compact**. Mục đích là giảm thời gian của **một khoảng dừng Full GC bắt buộc**, nhất là khi heap lớn. Đây vẫn là cơ chế còn áp dụng trên HotSpot JDK hiện đại.

Điểm dễ nhầm nằm ở chỗ bản thân **G1 cũng có những pha concurrent** — ví dụ **concurrent marking** khi ứng dụng vẫn đang hoạt động. Vì vậy cần phân biệt **ba trục**:

1. **Parallel**: nhiều GC worker làm việc cùng nhau.
2. **Concurrent with application**: GC có những công việc diễn ra trong khi mutator threads tiếp tục chạy.
3. **Stop-the-world**: mutator threads phải chờ ở safepoint; GC có thể dùng **một hoặc nhiều worker** trong khoảng dừng ấy.

Một pha vừa có thể **parallel**, vừa có thể **concurrent với ứng dụng** (như một phần của concurrent marking). Một pha **parallel** hoàn toàn có thể là **STW** (G1 Full GC, young/mixed evacuation). Ba khái niệm này **không phải các từ đồng nghĩa**.

Bài này hướng dẫn:

- Nắm chính xác JEP 307 của Java 10 và tình huống kích hoạt G1 Full GC;
- So sánh G1 Full GC với concurrent marking, young collection và mixed collection;
- Nhận diện GC worker, mutator, safepoint qua log;
- Hiểu vai trò `-XX:ParallelGCThreads`, `-XX:ConcGCThreads` và `-XX:MaxGCPauseMillis`;
- Chạy ba ví dụ Java 17+ độc lập với kết quả có thể kiểm chứng;
- Đọc dấu hiệu `Pause Full`, `Concurrent Mark Cycle`, `Pause Remark`, `Pause Cleanup`;
- Chẩn đoán Full GC ngoài ý muốn mà không chỉ tăng số GC worker;
- Hiểu những giới hạn: tốc độ không tăng tuyến tính, concurrent không có nghĩa không bao giờ dừng.

**Lưu ý phiên bản:** JEP 307 xuất hiện từ **Java 10**; ví dụ chọn **Java 17+** vì đó là nền JDK phù hợp cho thực hành hiện đại. Đã kiểm thử mã và lệnh trên **OpenJDK 24.0.2** với `javac --release 17`. Không sử dụng logging flags đã lỗi thời của các JDK cũ làm hướng dẫn chính.

## 2. Từ vựng: song song, đồng thời, STW

### 2.1. Parallel — song song giữa các worker

Một công việc GC có thể được chia cho nhiều **GC worker threads**. Hình dung công việc dọn 10 vùng heap:

```text
Thời gian -->
GC Worker 1:  [ mark vùng A ][ compact vùng D ]
GC Worker 2:  [ mark vùng B ][ compact vùng E ]
GC Worker 3:  [ mark vùng C ][ compact vùng F ]
```

Nhiều worker **có thể cùng tiến hành** những phần việc khác nhau nhờ nhiều CPU. Vì thế, thời gian *wall-clock* của pha có thể ngắn hơn phương pháp một worker, nếu đủ parallelism và công việc có thể chia tốt.

Nhưng câu trên **chưa trả lời** ứng dụng có đang chạy hay không. Điều đó phụ thuộc GC phase.

### 2.2. Concurrent — GC làm việc chồng thời gian với ứng dụng

Một **concurrent GC phase** chạy trong khi các luồng ứng dụng có thể tiếp tục thực hiện công việc. Ví dụ:

```text
Thời gian ------------------------------------------------->

Mutator A:    [request][allocate][process][request]...
Mutator B:    [compute][allocate][wait][compute]...
GC marking:            [--- concurrent mark ---]
```

Đây là khái niệm **chồng lấp hoạt động giữa GC và ứng dụng**, **không** phải bảo đảm cùng lúc có đủ CPU vật lý cho mọi thread. Khi số lõi hạn chế, GC threads và mutators có thể cạnh tranh CPU, bộ nhớ/cache, ảnh hưởng throughput.

G1 được mô tả là **mostly concurrent**: có công việc GC thực hiện cạnh ứng dụng, **nhưng vẫn có nhiều STW pauses**. Vì vậy “G1 hỗ trợ concurrent” **không** suy ra “G1 không bao giờ làm ứng dụng dừng”.

### 2.3. Stop-the-world — mutators chờ

Trong một STW pause, JVM đưa các mutator đến trạng thái an toàn (thường thông qua **safepoint**) rồi thực hiện công việc GC cần một heap được ổn định theo quy tắc của pha.

```text
Thời gian ------------------------------------------------->

Mutator A:  [RUN] |           PAUSED           | [RUN]
Mutator B:  [RUN] |           PAUSED           | [RUN]
GC Worker 1:      | [mark][adjust][compact]    |
GC Worker 2:      | [mark][adjust][compact]    |
                    <---- STW Full GC ----->
```

Trong cùng khoảng STW, GC worker 1 và 2 **làm song song với nhau**. Điều đó **không** có nghĩa GC worker đang chạy **đồng thời với mutator**.

**Công thức ghi nhớ:**

> **Parallel GC workers ≠ concurrent GC with application.** Để phân biệt, luôn hỏi **ai đang chạy**, **ai bị dừng** và **đang ở pha GC nào**.

## 3. Vì sao Java 10 thêm G1 Parallel Full GC?

**OpenJDK JEP 307 — Parallel Full GC for G1** giải quyết một điểm yếu của G1 trước Java 10: **Full GC dự phòng của G1 từng sử dụng một luồng**, nên khi JVM buộc phải compact toàn heap, độ trễ có thể rất lớn.

JEP 307 chuyển hoạt động Full GC sang **parallel mark–sweep–compact**, huy động nhiều GC workers để rút ngắn khoảng dừng. Số worker liên quan đến `-XX:ParallelGCThreads`, cũng ảnh hưởng các pha STW khác như young/mixed evacuation.

### 3.1. G1 vốn đã có những hoạt động khác nhau

G1 (Garbage-First) chia heap thành **regions**. Trong hoạt động bình thường, G1 cố gắng thu gom phần có lợi nhất bằng những **collection pauses nhỏ hơn**, thay vì liên tục thực hiện full-heap compaction.

Một vòng hoạt động tiêu biểu:

1. Young collections thu gom các young regions bằng **STW parallel evacuation**.
2. Khi cần phân tích old generation, G1 bắt đầu một **concurrent marking cycle**.
3. Trong marking cycle, mutators có thể tiếp tục chạy ở những pha concurrent, nhưng sẽ có **các STW pauses** ở điểm thích hợp.
4. Sau marking, G1 dùng nhiều **mixed collections** để thu hồi thêm một số old regions, vẫn qua **STW evacuation**.
5. Khi những cơ chế trên không đủ thu hồi nhanh hoặc không đủ vùng trống để cấp phát, **Full GC có thể xảy ra như phương án dự phòng**.

Full GC theo JEP 307 nằm ở **bước 5**, không phải một tên khác của concurrent marking tại bước 2.

### 3.2. Parallel Full GC không biến G1 thành “Fully Concurrent Collector”

JEP 307 **không**:
- Cho phép mutators tiếp tục chạy xuyên suốt Full GC;
- Xóa bỏ các STW pauses trong G1;
- Bảo đảm mọi Full GC luôn đáp ứng mục tiêu pause time;
- Biến một thuật toán thu gom toàn heap thành concurrent compaction;
- Loại bỏ nguyên nhân thiếu bộ nhớ hoặc fragmentation;
- Thay thế nhiệm vụ của concurrent marking thông thường.

Cải tiến đúng là **giảm chi phí của một trường hợp xấu** nhờ tăng parallelism **bên trong** Full GC. Thiết kế vận hành G1 vẫn ưu tiên **tránh đi vào Full GC**.

## 4. So sánh các loại công việc G1

| Hoạt động G1 | Ứng dụng có tiếp tục chạy trong hoạt động chính? | GC workers có thể song song? | Dấu hiệu |
|---|---|---|---|
| Young evacuation pause | **Không** — STW | Có | `Pause Young` |
| Mixed evacuation pause | **Không** — STW | Có | `Pause Young (Mixed)` hoặc tên pause tương đương theo JDK |
| Concurrent marking | **Có trong các đoạn concurrent** | Có thể có nhiều marking workers | `Concurrent Mark Cycle`, `Concurrent Mark From Roots` |
| Remark | **Không** — STW | JVM có thể song song hóa các phần việc | `Pause Remark` |
| Cleanup pause | **Không** trong phần pause | Có thể dùng parallel work tùy giai đoạn | `Pause Cleanup` |
| **Full GC / G1 Compaction Pause** | **Không** — STW | **Có, từ JDK 10 theo JEP 307** | `Pause Full`, `G1 Compaction Pause` hoặc `System.gc()` |
| Concurrent refinement / nhớ tập tham chiếu | **Có thể đồng thời với ứng dụng** | Có GC threads theo cấu hình | Các log `gc+remset`/`gc+phases` hoặc tài liệu phiên bản |

**Lưu ý quan trọng:** dòng “Concurrent Mark Cycle” trong log là **tên một chu kỳ**, không phải cam kết rằng **mọi nano giây và mọi subphase của chu kỳ đều concurrent**. Chẳng hạn `Pause Remark` và `Pause Cleanup` vẫn là STW dù nằm trong quá trình hoàn tất đánh dấu.

Đồng thời, tên log chính xác có thể khác theo phiên bản HotSpot. Khi chẩn đoán, hãy đọc **type**, **cause**, **duration**, **phase** và **GC ID**, thay vì đòi mọi JDK in đúng một chuỗi.

### 4.1. G1 young/mixed song song từ trước — Java 10 đổi điểm nào?

G1 đã sử dụng các worker song song cho **evacuation ở các lần young/mixed collection** trước Java 10. JEP 307 giải quyết **đường Full GC** vốn có vấn đề độ trễ do sử dụng một worker.

Do đó phát biểu “Java 10 đưa xử lý song song lần đầu vào G1” là **sai**. Chính xác là “Java 10 làm **G1 Full GC** song song, bổ sung cho những khả năng song song và đồng thời đã có của G1”.

## 5. Bên trong G1 Full GC: Mark–Sweep–Compact

Một Full GC được thực hiện nhằm thu hồi bộ nhớ trên **toàn heap** khi hoạt động incremental thông thường không đáp ứng được. Full GC có thể xử lý các vấn đề như thiếu không gian hoặc fragmentation, nhưng phải đánh đổi một **STW pause**, đôi khi kéo dài.

Với thuật toán Full GC song song của G1, các bước khái niệm gồm:

1. **Mark live objects**: xác định những đối tượng còn có thể truy cập từ roots; có thể phân chia công việc giữa nhiều GC workers.
2. **Prepare for compaction**: tính toán bố trí mới/điểm đích cho các đối tượng còn sống.
3. **Adjust pointers**: cập nhật các tham chiếu theo vị trí mới của đối tượng.
4. **Compact heap**: di chuyển/cô đọng dữ liệu sống, giải phóng vùng trống.

Các tên phase trên thể hiện cách triển khai HotSpot và có thể xuất hiện trong `-Xlog:gc+phases=info`. Trình tự chi tiết và phần việc serial/phụ có thể thay đổi giữa các JDK. **Không nên khẳng định mọi câu lệnh của Full GC đều song song**; các phần việc bắt buộc tuần tự hoặc đồng bộ vẫn tồn tại.

### 5.1. Parallel chỉ giảm thời gian công việc, không giảm số lần ứng dụng bị dừng

Giả sử một Full GC cần 800 đơn vị công việc. Một worker làm trong 800 đơn vị thời gian lý tưởng; bốn worker có thể chia công việc, nhưng **không** đảm bảo chỉ còn 200, vì:

- Một số phần bắt buộc tuần tự;
- Chia việc và đồng bộ GC workers có overhead;
- Các worker cùng truy cập memory bandwidth/cache;
- Cấu hình heap, CPU quota, NUMA và hệ điều hành khác nhau;
- Số vùng có live objects có thể phân bố không đều;
- JVM có thể chọn số worker hoạt động thấp hơn cấu hình tối đa.

**Không áp dụng phép suy “thêm 2× GC threads → pause giảm 2×”**. Cần đo tổng thể độ trễ thực trên workload.

### 5.2. Vì sao Full GC vẫn nguy hiểm với latency?

Dù trong pause có nhiều workers, **toàn bộ mutators vẫn chờ** cho đến khi STW Full GC hoàn tất. Nếu Full GC kéo dài 500 ms, các request đang cần thực thi code Java sẽ bị đình lại trong khoảng tương ứng, dù collector có dùng nhiều core.

Trong hệ thống đòi hỏi p99 latency thấp, một Full GC hiếm có thể vẫn làm hỏng SLA. Vì vậy **mục tiêu đầu tiên của tuning G1 thường là ngăn việc đi vào Full GC**, chứ không phải coi Full GC song song là đã giải quyết triệt để.

## 6. Concurrent marking: GC và ứng dụng cùng hoạt động, nhưng không phải không có pause

G1 dùng **concurrent marking** để xác định dữ liệu sống trong old generation và chọn các regions phù hợp cho mixed collections. Một chu kỳ có thể có:

- **Concurrent Start / Initial Mark pause**: đánh dấu điểm khởi đầu, gắn với một young collection STW.
- **Concurrent Mark**: một phần việc phân tích reachability thực hiện trong khi mutators vẫn tiến hành.
- **Remark pause**: hoàn tất đánh dấu/reference processing và những công việc cần STW.
- **Cleanup pause**: xác định thông tin cần cho giai đoạn thu hồi tiếp theo; có các hoạt động khác theo version.
- **Mixed collections** sau khi có kết quả marking: STW evacuation các young regions và tập old regions đã chọn.

Ở những khoảng concurrent, GC có thể dùng CPU cạnh ứng dụng. Đây là cái giá để giảm STW pause, không phải “miễn phí về CPU”.

### 6.1. Snapshot-at-the-Beginning (SATB)

G1 sử dụng một cách tiếp cận concurrent marking được gọi là **Snapshot-At-The-Beginning** (SATB). Nó hình dung heap tại thời điểm đánh dấu bắt đầu và sử dụng cơ chế theo dõi thay đổi tham chiếu để bảo toàn thông tin liveness theo thiết kế của collector.

Giải thích ở mức ứng dụng:

- Các mutator có thể tiếp tục sửa object graph khi GC đang đánh dấu;
- Collector cần cơ chế để việc thay đổi tham chiếu không làm bỏ sót đối tượng còn sống theo snapshot;
- Vì mô hình snapshot có thể giữ lại một số đối tượng đã trở thành rác trong thời gian marking, việc giải phóng có thể diễn ra ở chu kỳ sau;
- STW `Remark` giúp hoàn tất những phần việc cần trạng thái nhất quán.

Điều này lý giải vì sao concurrent marking **khác** với việc đóng băng toàn heap để làm Full GC.

### 6.2. Thời gian của một concurrent cycle không phải là một STW pause duy nhất

Giả sử log cho:

```text
GC(12) Concurrent Mark Cycle 50.0ms
GC(12) Pause Remark 2.0ms
GC(12) Pause Cleanup 0.2ms
```

Đây là **dữ liệu giả định để giải thích**, không phải output của chương trình bên dưới. Tổng 50 ms của cycle **không đồng nghĩa** ứng dụng bị dừng 50 ms. Các STW pauses cần được tìm riêng và các GC IDs/log tags cho biết subphase nào thuộc cycle.

Ngược lại, log:

```text
GC(13) Pause Full (G1 Compaction Pause) 500.0ms
```

là **minh họa giả định** cho một Full GC STW kéo dài khoảng 500 ms. Trong thời gian đó mutators không chạy Java work bình thường.

## 7. Điều gì khiến G1 phải làm Full GC?

Theo tài liệu Oracle G1 tuning hiện đại, một Full GC thường xuất hiện khi:
- Ứng dụng cấp phát hoặc promote vào old generation quá nhanh;
- Concurrent marking chưa kịp hoàn thành và mở đường cho space reclamation;
- Evacuation thất bại do không đủ khoảng trống để di chuyển live objects;
- Nhiều **humongous objects** làm heap khó tìm các vùng liên tiếp cần thiết;
- Có yêu cầu tường minh từ `System.gc()` hoặc công cụ bên ngoài, tùy flags;
- Có áp lực bộ nhớ hay tình trạng fragmentation mà những vòng young/mixed thông thường không xử lý kịp.

**Đừng suy rằng mọi Full GC đều là bằng chứng chắc chắn của memory leak.** Nó có thể xuất hiện bởi áp lực cấp phát, live set lớn, heap sizing, humongous allocations, một công cụ gọi GC thủ công, hoặc lỗi cấu hình. Cần xem **GC cause** và lịch sử các collection trước đó.

### 7.1. Dấu hiệu thực tế trong log

Trong tình huống áp lực heap, G1 có thể ghi:

```text
Pause Young ... (G1 Evacuation Pause)
Evacuation Failure: Allocation
Pause Full (G1 Compaction Pause)
```

Đây là **mẫu khái niệm**, không bảo đảm ba dòng xuất hiện liền nhau hay theo đúng cách viết ở mọi JDK. Khi đọc log thật, tìm các sự kiện `Evacuation Failure`, `Pause Full` và các thông số heap trước/sau.

Nếu cause là `System.gc()`, hãy kiểm tra application code, thư viện hoặc công cụ quản trị đã gọi GC, thay vì kết luận lỗi đột biến từ workload.

### 7.2. Full GC không bảo đảm cứu được OutOfMemoryError

Full GC cố thu hồi/compact heap, nhưng nếu **live set vẫn vượt quá dung lượng heap** hoặc không thể có đủ vùng trống theo yêu cầu allocation, JVM có thể vẫn ném `OutOfMemoryError`.

Nhiều GC workers **không tạo ra thêm RAM**. Song song hóa giúp giảm thời gian xử lý; nó không biến dữ liệu sống thành dữ liệu chết và không thay kích thước heap đã cấu hình.

## 8. Công cụ quan sát trên JDK hiện đại

Từ JDK 9, **Unified Logging** là cách hiện đại để xem GC. Những tùy chọn hữu ích:

| Tùy chọn | Công dụng |
|---|---|
| `-Xlog:gc=info` | Dòng tổng hợp các sự kiện GC, young/mixed/concurrent cycle/full |
| `-Xlog:gc*=info` | Nhiều log categories liên quan GC, gồm task/phases khi được bật |
| `-Xlog:gc+phases=info` | Tách thời gian của những pha GC |
| `-Xlog:gc+task=info` | Kiểm tra số GC workers sử dụng ở một số collection |
| `-Xlog:safepoint=info` | Thông tin safepoint, thời gian tạm dừng VM |
| `-Xlog:gc+cpu=info` | User/Sys/Real time để hỗ trợ phân tích pause |
| `-Xlog:gc*=debug` | Chi tiết cao để chẩn đoán khi cần, log có thể rất lớn |

**Không dùng** `-XX:+PrintGCDetails` hoặc `-XX:+PrintGCTimeStamps` làm ví dụ chuẩn cho Java 17+, vì đó là kiểu logging cũ và không phải hướng dẫn ưu tiên hiện nay.

### 8.1. Cách đọc `Pause Full`

Ví dụ cấu trúc:

```text
[...][info][gc,start] GC(0) Pause Full (System.gc())
[...][info][gc,task ] GC(0) Using 2 workers of 2 for full compaction
[...][info][gc     ] GC(0) Pause Full (System.gc()) ... 1.981ms
[...][info][safepoint] Safepoint "G1CollectFull", ...
```

Đây là **trích đoạn đã kiểm thử trên OpenJDK 24.0.2**; các timestamps, byte count và duration phải coi là số phụ thuộc môi trường.

Cách phân tích:
- `Pause Full`: đây là **STW Full GC**;
- `System.gc()`: lý do tường minh của demo, không phải cấp phát thất bại;
- `Using 2 workers of 2`: trong collector đang có **hai GC workers cho Full compaction**;
- `Safepoint "G1CollectFull"`: JVM đã bước vào safepoint để thực hiện Full GC;
- Khoảng `1.981ms` là **một số đo cụ thể**, không phải mức trần hoặc kết quả sẽ lặp lại.

**Hai worker trong dòng log không chứng minh ứng dụng đã chạy đồng thời với GC**. Ngược lại, `Pause Full` và safepoint xác nhận đây là khoảng dừng ứng dụng.

### 8.2. Cách đọc concurrent cycle

Ví dụ dạng log đã quan sát:

```text
GC(4) Pause Young (Concurrent Start) (G1 Evacuation Pause)
GC(5) Concurrent Mark Cycle
GC(5) Pause Remark ...
GC(5) Pause Cleanup ...
GC(5) Concurrent Mark Cycle ...
```

Trong môi trường thử nghiệm, chu kỳ có đoạn concurrent và **những pauses Remark/Cleanup**. Dòng `Concurrent Mark Cycle` cuối thường tóm tắt thời gian chu kỳ, không phải một Full GC STW.

**Không đánh đồng** độ dài cycle với độ dài một lần pause: hãy đọc riêng các sự kiện `Pause`.

## 9. Ví dụ chạy đầy đủ 1 — Full GC song song nhưng STW

Tạo tệp **`G1FullPauseDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class G1FullPauseDemo {
    public static void main(String[] args) {
        List<byte[]> live = new ArrayList<>();

        // Giữ 16 blocks thực sự còn tham chiếu.
        for (int i = 0; i < 16; i++) {
            live.add(new byte[512 * 1024]);
        }

        System.out.println(
                "beforeFull retainedBlocks=" + live.size());

        // Dùng để minh họa Full GC trên JVM được cấu hình phù hợp.
        // KHÔNG dùng mẹo này để "tối ưu" luồng nghiệp vụ production.
        System.gc();

        System.out.println(
                "afterFull retainedBlocks=" + live.size());

        // Bỏ references đến 16 blocks.
        live.clear();

        System.gc();

        System.out.println(
                "afterRelease retainedBlocks=" + live.size());
    }
}
```

Biên dịch:

```bash
javac --release 17 -encoding UTF-8 G1FullPauseDemo.java
```

Chạy với G1, heap nhỏ và số worker được chỉ định rõ:

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1 -Xlog:gc*,safepoint=info G1FullPauseDemo
```

**Stdout từ chương trình** (loại trừ các dòng Unified GC Logging):

```text
beforeFull retainedBlocks=16
afterFull retainedBlocks=16
afterRelease retainedBlocks=0
```

**Một số dòng GC log quan sát được trên OpenJDK 24.0.2:**

```text
Using G1
GC(0) Pause Full (System.gc())
GC(0) Using 2 workers of 2 for full compaction
GC(0) Phase 1: Mark live objects
GC(0) Phase 3: Adjust pointers
GC(0) Phase 4: Compact heap
GC(0) Pause Full (System.gc()) 17M->17M(64M) 1.981ms
Safepoint "G1CollectFull", ...
GC(1) Pause Full (System.gc())
GC(1) Using 2 workers of 2 for full compaction
GC(1) Pause Full (System.gc()) 17M->1M(64M) 1.446ms
```

Đây là **trích đoạn lọc**, bỏ log prefixes và những phase phụ; thời gian/dung lượng là quan sát cụ thể, không phải stdout bắt buộc trên mọi máy.

### 9.1. Tại sao Full GC đầu không giảm live data?

Trong `System.gc()` thứ nhất, `List<byte[]> live` vẫn chứa 16 arrays. Các arrays còn reachable nên GC **không được tự ý hủy chúng**. Dòng `17M->17M` phản ánh kết quả của lần chạy thử, không phải cam kết chính xác dung lượng heap.

Sau `live.clear()`, arrays đã không còn được giữ bởi danh sách. Full GC thứ hai có thể thu hồi phần bộ nhớ đó; log mẫu giảm xuống `1M`. Mốc 1M phụ thuộc JVM.

### 9.2. Điều gì chứng minh “parallel” và “STW”?

- **Parallel**: `Using 2 workers of 2 for full compaction`.
- **STW**: `Pause Full` và `Safepoint "G1CollectFull"`.

Hai dấu hiệu xuất hiện trong **cùng một Full GC** — đó chính là nội dung quan trọng nhất của bài.

### 9.3. Lưu ý về `System.gc()`

Đây là **một thí nghiệm tách biệt**, không phải khuyến nghị gọi `System.gc()` trong ứng dụng thật.

Trong những cấu hình HotSpot G1 thông thường, `System.gc()` có thể kích hoạt `Pause Full (System.gc())`. Tuy nhiên:
- `-XX:+DisableExplicitGC` có thể khiến yêu cầu explicit GC bị bỏ qua;
- `-XX:+ExplicitGCInvokesConcurrent` có thể thay cách đáp ứng yêu cầu thành cơ chế concurrent phù hợp;
- Thư viện/framework/VM khác có thể áp dụng lựa chọn khác;
- Chỉ log thực tế mới nói rõ JVM đã thực hiện collection nào.

**Vì thế không viết test “mọi lần gọi `System.gc()` đều gây Full GC”**. Ở demo, flags được cố ý đặt để quan sát hành vi cụ thể trên JDK đã kiểm chứng.

## 10. Ví dụ chạy đầy đủ 2 — G1 concurrent marking vẫn có các pause

Tạo tệp **`G1ConcurrentCycleDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class G1ConcurrentCycleDemo {
    public static void main(String[] args)
            throws InterruptedException {

        List<byte[]> survivors = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 6000; i++) {
            byte[] chunk = new byte[96 * 1024];
            chunk[0] = (byte) i;

            // Một phần objects sống lâu hơn,
            // các blocks khác sớm trở thành garbage.
            if (i % 10 == 0) {
                survivors.add(chunk);
                if (survivors.size() > 140) {
                    survivors.remove(0);
                }
            }

            checksum += chunk[0];
        }

        // Chờ ngắn để các hoạt động concurrent có dịp hoàn tất.
        Thread.sleep(150);

        System.out.println("iterations=6000");
        System.out.println("survivors=" + survivors.size());
        System.out.println("checksum=" + checksum);
    }
}
```

Biên dịch:

```bash
javac --release 17 -encoding UTF-8 G1ConcurrentCycleDemo.java
```

Chạy với G1. Các flags `IHOP` dưới đây **chỉ nhằm làm tăng khả năng xuất hiện marking cycle trong môi trường demo**:

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m -XX:MaxGCPauseMillis=20 -XX:InitiatingHeapOccupancyPercent=10 -XX:-G1UseAdaptiveIHOP -Xlog:gc=info G1ConcurrentCycleDemo
```

**Stdout chính xác của chương trình đã kiểm thử:**

```text
iterations=6000
survivors=140
checksum=3272
```

**Trích đoạn log đã quan sát trên OpenJDK 24.0.2:**

```text
GC(4) Pause Young (Concurrent Start) (G1 Evacuation Pause)
GC(5) Concurrent Mark Cycle
GC(5) Pause Remark ...
GC(5) Pause Cleanup ...
GC(5) Concurrent Mark Cycle ...
```

Trong lần thử này:
- Có các marking cycles;
- Có các STW `Remark` và `Cleanup` pauses;
- **Không có** Full GC trong log của lần chạy ấy.

### 10.1. Ý nghĩa

Chương trình tạo allocations liên tục và giữ một số block để G1 có thông tin cần phân tích. `-XX:InitiatingHeapOccupancyPercent=10` và `-XX:-G1UseAdaptiveIHOP` làm thay đổi heuristics nhằm minh họa marking sớm.

**Không có bảo đảm** mọi môi trường sẽ xuất hiện cùng GC IDs, cùng số cycles, cùng các sự kiện hay cùng thời lượng. JDK/CPU/heap/chiến lược JIT có thể thay kết quả GC. Những dòng `iterations`, `survivors`, `checksum` thuộc logic Java là cố định; **GC log không phải test golden-file cố định**.

### 10.2. Tại sao không đem flags IHOP trong demo vào production?

Oracle khuyến nghị trước tiên dùng **G1 mặc định**, cấu hình heap và pause target theo nhu cầu. Việc tắt adaptive IHOP và ép threshold 10% có thể làm quá nhiều marking cycles, tăng CPU overhead hoặc throughput cost. Nó chỉ thích hợp trong demo hoặc khi chẩn đoán dựa trên đo đạc và hiểu dữ liệu.

Nếu mục tiêu production là tránh Full GC, hãy phân tích allocation rate, live set, humongous regions và thời gian concurrent mark hoàn thành thay vì sao chép một con số IHOP từ ví dụ.

## 11. Hai nhóm GC threads: `ParallelGCThreads` và `ConcGCThreads`

Hai JVM options thường gây nhầm:

| Flag | Điều khiển | Trong G1 |
|---|---|---|
| `-XX:ParallelGCThreads=N` | Giới hạn/số workers dành cho công việc GC **song song trong các STW pauses** | Young/mixed evacuation; Full GC compaction |
| `-XX:ConcGCThreads=M` | Số workers cho các pha **concurrent marking** | Work diễn ra chồng lấp với hoạt động ứng dụng |
| `-XX:MaxGCPauseMillis=T` | **Mục tiêu mềm** cho độ dài pauses mà G1 cố đạt trong chiến lược thông thường | Không bảo đảm Full GC ngắn hơn T |
| `-XX:+UseG1GC` | Chọn G1 | Tránh phụ thuộc cấu hình JVM chọn GC mặc định trong demo |

**Chú ý:** số worker **thực sự** được dùng có thể khác số tối đa được cấu hình vì JVM còn xét kích thước heap, số CPU khả dụng, cgroups/container quota và heuristics. Dòng `Using X workers` trong GC log phản ánh quyết định thực tế của một collection.

### 11.1. Parallel workers không phải application threads

Đặt `-XX:ParallelGCThreads=8` **không** tạo 8 threads chạy business logic và cũng không biến Full GC thành đồng thời với application. Những worker đó phục vụ GC.

Đặt `-XX:ConcGCThreads=2` **không** buộc Full GC dùng 2 workers. Đó là cấu hình khác cho công việc concurrent.

### 11.2. Tăng GC workers có thể làm chậm hệ thống

Những lựa chọn không hợp lý có thể gây:
- CPU oversubscription trên container chỉ có quota 2 cores;
- Overhead chia việc/đồng bộ cao;
- Memory bandwidth contention;
- Ít CPU hơn cho mutators trong các pha concurrent;
- Kết quả tệ hơn cho throughput hoặc p99 latency.

Tương tự, giảm `ConcGCThreads` quá thấp có thể khiến concurrent marking không kịp hoàn tất trước khi heap chịu áp lực, tăng nguy cơ Full GC. Không có một mức threads tối ưu cho mọi ứng dụng.

## 12. Ví dụ chạy đầy đủ 3 — kiểm tra cấu hình GC workers của HotSpot

Chương trình sau dùng `HotSpotDiagnosticMXBean` để đọc những VM options thực tế đang áp dụng. Đây là **API quản trị HotSpot-specific**, không phải phương thức portable cho mọi JVM implementation.

Tạo **`G1WorkerConfigDemo.java`**:

```java
import com.sun.management.HotSpotDiagnosticMXBean;
import java.lang.management.ManagementFactory;

public class G1WorkerConfigDemo {
    public static void main(String[] args) {
        HotSpotDiagnosticMXBean vm =
                ManagementFactory.getPlatformMXBean(
                    HotSpotDiagnosticMXBean.class);

        System.out.println("g1=" +
                vm.getVMOption("UseG1GC").getValue());

        System.out.println("parallelGcThreads=" +
                vm.getVMOption("ParallelGCThreads").getValue());

        System.out.println("concurrentGcThreads=" +
                vm.getVMOption("ConcGCThreads").getValue());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 G1WorkerConfigDemo.java
java -XX:+UseG1GC -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1 G1WorkerConfigDemo
```

**Stdout đã kiểm chứng trên OpenJDK 24.0.2:**

```text
g1=true
parallelGcThreads=2
concurrentGcThreads=1
```

Ý nghĩa:
- `g1=true` xác nhận JVM đang dùng G1.
- `parallelGcThreads=2` là giá trị flag dành cho GC parallel workers;
- `concurrentGcThreads=1` là giá trị flag dành cho GC concurrent workers.

**Cần tách rõ:** chương trình kiểm tra **cấu hình**, không tự đo những workers nào thực sự chạy ở từng collection. Để kiểm chứng Full GC dùng mấy worker, xem `-Xlog:gc+task=info` khi Full GC xảy ra. Để quan sát concurrent marking, xem `-Xlog:gc=info` và các log mark phases.

Nếu VM không có bean hoặc flag tương ứng, chương trình có thể không áp dụng; đó là giới hạn của công cụ quản trị HotSpot, **không** phải lỗi cú pháp Java của `Runtime` hay `Thread`.

## 13. `-XX:MaxGCPauseMillis` không phải cam kết Full GC dưới một ngưỡng

G1 cố gắng đạt mục tiêu pauses với xác suất cao cho **các hoạt động thông thường** bằng mô hình dự đoán chi phí collection set.

Ví dụ:

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -Xmx2g MyApp
```

Đây là **lệnh minh họa**, `MyApp` là class có sẵn. Ý nghĩa của `200` là **mục tiêu mềm**, không phải giới hạn hard real-time. Đặc biệt, một **Full GC dự phòng** vẫn có thể lâu hơn nhiều.

JEP 307 giúp giảm thời gian trong những tình huống Full GC, nhưng không biến Full GC thành một pause được điều khiển bởi mục tiêu `MaxGCPauseMillis` như thể VM có thể tự dừng compaction ở đúng 200 ms.

### 13.1. p99 latency của ứng dụng

Giả sử một HTTP request có 20 ms logic xử lý nhưng rơi đúng lúc JVM Full GC STW kéo dài 400 ms. Latency request có thể cao hơn rất nhiều so với 20 ms. Dù Full GC có dùng 4 worker, **mutator vẫn phải chờ**.

Khi điều tra latency spikes:
1. So timestamp request latency với `Pause Full` log;
2. Xem độ dài safepoint/Full GC thực tế;
3. Xác định nguyên nhân Full GC — áp lực heap hay explicit GC;
4. Xem heap occupancy và allocation pattern trước đó;
5. Kiểm tra các tác động ngoài GC như container CPU throttling và I/O.

Không quy mọi spike cho GC, nhưng cũng không loại bỏ GC chỉ vì log cho thấy nhiều workers.

### 13.2. User / Sys / Real time

`-Xlog:gc+cpu=info` có thể cho:

```text
User=0.20s Sys=0.00s Real=0.05s
```

Đây là **ví dụ giả định**:
- **User** là CPU time tiêu thụ trong user mode trên các threads liên quan;
- **Sys** là CPU time dùng cho hệ điều hành;
- **Real** là wall-clock elapsed time.

`User > Real` có thể gợi ý công việc sử dụng **nhiều lõi/threads**, nhưng **không phải bằng chứng duy nhất** rằng GC concurrent với ứng dụng. Với một Full GC STW có nhiều workers, User có thể lớn hơn Real, trong khi mutators **vẫn bị dừng**.

## 14. Phân biệt “Parallel GC” (tên một collector) với “G1 có parallel Full GC”

Java HotSpot có một collector khác được gọi là **Parallel GC** (thường chọn bằng `-XX:+UseParallelGC`). Nó **không phải** G1.

| Câu nói | Nghĩa |
|---|---|
| “Ứng dụng dùng Parallel GC” | Chọn **collector Parallel GC** |
| “G1 Full GC dùng nhiều workers” | **G1 collector** đang làm **Full GC song song** |
| “G1 concurrent marking” | G1 đang thực hiện marking **cùng lúc với mutators** trong pha concurrent |
| “G1 young collection song song” | GC workers song song hóa **một STW young pause** |

**Không nhầm tên collector với đặc tính của một pha.** Parallel GC nhìn chung ưu tiên throughput với các STW collections; G1 cân bằng pauses/throughput bằng marking concurrent và incremental STW collections. Đây chỉ là khác biệt tổng quan; chọn collector cho production cần benchmark workload thực tế.

Các low-latency collectors như **ZGC** có những cơ chế concurrent khác. Không nên suy rằng chúng và G1 Full GC JEP 307 có cùng lịch trình GC hoặc cùng pause semantics.

## 15. Sơ đồ tổng hợp: hai tình huống rất khác nhau

### 15.1. G1 Full GC — parallel bên trong STW

```text
                        STW FULL GC
                  <-------------------->
Application T1:   RUN |      PAUSE      | RUN
Application T2:   RUN |      PAUSE      | RUN
GC worker #1:         |  MARK / COMPACT |
GC worker #2:         |  MARK / COMPACT |
GC worker #3:         |  MARK / COMPACT |
                       => parallel workers
                      => NOT concurrent with app
```

### 15.2. G1 concurrent marking — chồng thời gian với ứng dụng

```text
                   initial       remark      cleanup
                   STW           STW          STW
Application:   RUN |PAUSE| RUN RUN |PAUSE| RUN |PAUSE| RUN
Marking:           [start]====== concurrent ======[done]
                                   ^
                       GC có thể làm việc cùng app
```

**Hai sơ đồ là khái niệm**, không mô phỏng chính xác độ dài và cách JVM lên lịch từng subphase. G1 thực tế còn có các young collections xuất hiện trong marking cycle và những hoạt động concurrent khác.

## 16. Cách chẩn đoán khi Full GC xuất hiện ngoài ý muốn

### 16.1. Bước một: xác định cause, không chỉ số lượng threads

Chạy với Unified Logging phù hợp:

```bash
java -XX:+UseG1GC -Xlog:gc*=info -Xmx2g MyApp
```

Đây là lệnh minh họa, không phải chương trình đầy đủ. Tìm:
- `Pause Full (System.gc())` hay `Pause Full (G1 Compaction Pause)`;
- `Evacuation Failure: Allocation` và những collections trước Full GC;
- Mức old/humongous occupancy;
- Thời gian marking cycles;
- Lúc nào application bắt đầu có allocation/promotion spikes.

**Đừng giải quyết bằng cách chỉ tăng `ParallelGCThreads`** trước khi hiểu vì sao Full GC xảy ra.

### 16.2. Bước hai: nhìn heap và phân bổ live objects

Các nguyên nhân thường gặp:
- Live set tiến sát `-Xmx`;
- Quá nhiều cache/object giữ tham chiếu lâu;
- Allocation rate hoặc promotion rate cao;
- Humongous objects chiếm nhiều regions và gây fragmentation;
- Concurrent marking bắt đầu quá muộn hoặc không hoàn thành kịp;
- Heap bị cấp quá ít so với yêu cầu ứng dụng.

Lưu ý: **Memory leak** là một giả thuyết cần điều tra bằng heap dump/profiler, không phải kết luận trực tiếp từ một dòng `Pause Full`.

### 16.3. Bước ba: ưu tiên giải pháp ở mức workload và heap

Những lựa chọn có cơ sở:
1. Giảm allocation không cần thiết hoặc số đối tượng sống lâu;
2. Điều chỉnh `-Xmx` khi có headroom RAM thật;
3. Rà soát humongous allocations, kích thước buffers/arrays;
4. Xem khả năng concurrent mark kịp thời;
5. Đánh giá `-XX:ConcGCThreads` hoặc timing của IHOP **sau khi có dữ liệu**;
6. So sánh throughput, latency và memory footprint trước/sau.

Oracle G1 tuning guide khuyến nghị bắt đầu từ cấu hình mặc định, điều chỉnh heap và pause target khi cần. Đừng ép một young generation size cố định bằng `-Xmn` hoặc `-XX:NewRatio` làm mất khả năng G1 điều chỉnh pause như mặc định.

### 16.4. Explicit Full GC do ứng dụng gọi

Nếu log cho thấy cause `System.gc()`:
- Tìm code/thư viện/tool đã gọi explicit GC;
- Cân nhắc loại bỏ yêu cầu không cần thiết;
- Các lựa chọn `-XX:+DisableExplicitGC` hoặc `-XX:+ExplicitGCInvokesConcurrent` tồn tại trên HotSpot G1 nhưng có **hệ quả ứng dụng**; không bật mù quáng khi chưa hiểu yêu cầu của thư viện/native memory;
- Dùng staging và benchmark trước khi thay chính sách production.

Full GC **được gọi tường minh** khác Full GC xảy ra do evacuation failure; hai trường hợp cần cách xử lý khác nhau.

## 17. Quan sát đúng thay vì rút kết luận từ một dòng

Một bộ kiểm tra nên bao gồm:

| Câu hỏi QA | Bằng chứng |
|---|---|
| JVM đang dùng G1? | `Using G1` / VM flags |
| Có Full GC? | `Pause Full` trong GC log |
| Full GC STW? | Dòng `Pause Full` và safepoint tương ứng |
| Có bao nhiêu Full compaction workers? | `Using N workers ... for full compaction` hoặc task log |
| Có concurrent marking? | `Concurrent Mark Cycle` và các marking log |
| Trong concurrent cycle có STW không? | `Pause Remark`, `Pause Cleanup`, Concurrent Start pause |
| Full GC do ai kích hoạt? | GC cause: `System.gc()`, allocation failure... |
| Heap còn bao nhiêu sau GC? | Số liệu trước/sau và regions |
| Latency có cải thiện sau tuning? | Benchmark p50/p95/p99 và GC pauses |
| Cấu hình đã được áp dụng? | `-XX:+PrintFlagsFinal` hoặc HotSpot MXBean; log runtime |

Không lấy **GC worker count** để suy ra application concurrency. Không lấy **elapsed time của Concurrent Mark Cycle** làm thời lượng STW pause. Không lấy **số heap sau GC thấp** để suy ra mọi đối tượng đã được giải phóng hoặc không có leak.

### 17.1. Cảnh giác với log sampling và JFR

**Java Flight Recorder (JFR)** là công cụ còn phù hợp với JDK hiện đại để phân tích GC events, safepoints và application performance. Khi dùng JFR:
- Xem event duration của pauses thay vì chỉ xem toàn bộ GC cycle;
- Đặt cạnh latency của ứng dụng trong cùng time window;
- Phân biệt young pause, old/full GC và marking work;
- Xác minh các profile overhead/setting của recording.

JFR hữu ích khi logs quá chi tiết hoặc cần correlation với request/application events, nhưng nó cũng không biến Full GC thành concurrent activity.

## 18. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “G1 Full GC song song nên app không dừng.” | **Sai**. Full GC song song là **STW**, nhiều GC workers cùng làm. |
| “Parallel = concurrent.” | Sai. Parallel mô tả nhiều workers; concurrent mô tả GC chồng với mutators. |
| “G1 là concurrent GC nên không có safepoint pauses.” | G1 **mostly concurrent**, vẫn có young/mixed/remark/cleanup/full STW pauses. |
| “Có 8 GC workers nghĩa app cùng chạy với 8 GC threads.” | Không: workers của một Full GC có thể chạy khi app đã bị dừng. |
| “JDK 10 mới đưa mọi dạng song song vào G1.” | JEP 307 chỉ mới **song song hóa Full GC**, không phải young/mixed song song lần đầu. |
| “Concurrent marking chính là Full GC.” | Không. Marking giúp chuẩn bị mixed collections; Full GC là đường compact dự phòng. |
| “Concurrent Mark Cycle 100 ms nghĩa app bị dừng 100 ms.” | Không. Phải đếm các STW pauses bên trong. |
| “G1 Full GC theo JEP 307 bảo đảm pause dưới 200 ms.” | Không. `MaxGCPauseMillis` là **mục tiêu mềm**, Full GC có thể dài. |
| “Tăng `ParallelGCThreads` luôn làm pause ngắn tuyến tính.” | Overhead, CPU quota, memory bandwidth và công việc tuần tự giới hạn lợi ích. |
| “`ConcGCThreads` là số luồng Full GC.” | Không. Nó dùng cho những công việc concurrent như marking. |
| “Mọi `System.gc()` luôn tạo Full GC.” | Có flags làm JVM bỏ qua hoặc dùng concurrent GC. |
| “Không thấy Full GC trong một lần test nghĩa hệ thống không bao giờ có.” | Không. Workload/heap/traffic khác có thể kích hoạt. |
| “Không có Full GC nghĩa ứng dụng không bao giờ bị STW.” | Vẫn có young/mixed/remark/cleanup pauses. |
| “Một dòng `User > Real` chứng minh mutators chạy cùng GC.” | Không. Full GC STW song song cũng có thể có tổng CPU time lớn hơn wall time. |
| “G1 Parallel Full GC và `-XX:+UseParallelGC` là một.” | Không. Một là khả năng của **G1**, một là **collector khác**. |
| “Chỉ cần tăng heap là chắc chắn hết GC.” | Heap lớn có thể giúp, nhưng live set/fragmentation/behavior và RAM vẫn cần xét. |
| “Full GC luôn là memory leak.” | Không. Có nhiều nguyên nhân, kể cả explicit GC và cấp phát quá nhanh. |

## 19. Checklist review code và JVM tuning

- [ ] Tài liệu có nói rõ **G1 Full GC song song là STW**?
- [ ] Có phân biệt G1 Full GC với G1 concurrent marking?
- [ ] Có chỉ ra JEP 307 **đến từ Java 10**, nhưng G1 đã có các pha khác trước đó?
- [ ] Có phân biệt GC workers với application mutator threads?
- [ ] Có phân biệt `ParallelGCThreads` và `ConcGCThreads`?
- [ ] Có kiểm tra GC thực tế đang dùng thay vì giả định theo version JDK?
- [ ] Có quan sát `Pause Full` và `Using N workers` qua log?
- [ ] Có nhận diện `Pause Remark` và `Pause Cleanup` trong concurrent marking cycle?
- [ ] Có hiểu `MaxGCPauseMillis` là soft target, không phải SLA cứng?
- [ ] Có tránh sử dụng `System.gc()` làm mẹo tối ưu production?
- [ ] Có tránh sử dụng logging flags lỗi thời khi chạy JDK 17+?
- [ ] Có phân biệt GC cause do `System.gc()` với pressure/evacuation failure?
- [ ] Có kiểm tra allocation/promotion/live set/humongous objects?
- [ ] Có đánh giá CPU quota/container/cgroups khi đặt workers?
- [ ] Có đo throughput và p99 latency thay vì chỉ nhìn một GC pause?
- [ ] Có so sánh cùng workload, heap, JDK và runtime trước/sau thay đổi?
- [ ] Có tránh áp một con số IHOP/concurrent threads của bài demo vào production?
- [ ] Có ghi nhận phiên bản JDK vì log và heuristics có thể thay đổi?

Nhận xét review hữu ích:

> “Bài viết ghi ‘G1 parallel Full GC chạy cùng ứng dụng’. Điều này sai: JEP 307 song song hóa **các GC workers bên trong STW Full GC**. Concurrent với ứng dụng là những pha khác như concurrent marking. Nên sửa mô tả và dẫn GC logs minh họa.”

Nhận xét khác:

> “Tăng `ParallelGCThreads` có thể làm Full GC ngắn hơn, nhưng không giải quyết nguyên nhân các Full GC xuất hiện. Hãy kiểm tra `Pause Full` cause và áp lực old generation trước khi tuning.”

## 20. Câu hỏi tự kiểm tra có đáp án

**1.** JEP nào đưa G1 Parallel Full GC vào JDK 10?

**Đáp án:** **JEP 307 — Parallel Full GC for G1**.

**2.** G1 Full GC có chạy đồng thời với các mutators không?

**Đáp án:** **Không**; đó là **STW Full GC**. Nhiều GC workers có thể chạy song song **với nhau**.

**3.** Hai GC workers cùng compact heap có tự chứng minh ứng dụng tiếp tục chạy không?

**Đáp án:** Không. Cần biết pha có STW hay concurrent. Full GC của G1 là STW.

**4.** Những hoạt động G1 nào có thể chạy cùng mutators?

**Đáp án:** Những công việc như concurrent marking/refinement trong các pha được thiết kế concurrent. Nhưng marking cycle vẫn có các STW pauses.

**5.** `Pause Remark` là STW hay concurrent?

**Đáp án:** **STW pause**, dù nó thuộc một concurrent marking cycle.

**6.** Tại sao `Concurrent Mark Cycle 50ms` không đồng nghĩa 50ms ứng dụng bị dừng?

**Đáp án:** Vì đó là tổng một chu kỳ có những đoạn GC chạy đồng thời với mutators; cần tính riêng `Pause` events.

**7.** `-XX:ParallelGCThreads` và `-XX:ConcGCThreads` dùng cho việc gì?

**Đáp án:** Cái đầu cho những GC workers trong STW parallel work; cái sau cho concurrent work như marking.

**8.** `-XX:MaxGCPauseMillis=200` có bảo đảm một G1 Full GC không vượt 200ms không?

**Đáp án:** Không. Đó là pause target mềm, Full GC có thể rất dài.

**9.** Vì sao `System.gc()` không phải công cụ đo Full GC tin cậy tuyệt đối?

**Đáp án:** Các flags hoặc cách JVM triển khai có thể bỏ qua/chuyển yêu cầu sang concurrent. Cần kiểm tra log.

**10.** Dấu hiệu log nào trực tiếp cho biết Full GC sử dụng nhiều workers?

**Đáp án:** Ví dụ `Using 2 workers of 2 for full compaction`.

**11.** Những dòng nào phản ánh STW trong demo?

**Đáp án:** `Pause Full (System.gc())` và safepoint `G1CollectFull`.

**12.** Có thể có `Pause Young` khi G1 không làm Full GC không?

**Đáp án:** Có. Young/mixed evacuation thường là STW collections độc lập với Full GC.

**13.** Vì sao tăng số worker không bảo đảm thời gian giảm tuyến tính?

**Đáp án:** Công việc tuần tự, coordination, memory bandwidth, CPU limits và imbalance có overhead.

**14.** Full GC luôn do memory leak không?

**Đáp án:** Không. Có thể do allocation pressure, live set, humongous fragmentation, concurrent marking chưa kịp hoặc explicit GC.

**15.** Khi ứng dụng đang gặp `Pause Full (G1 Compaction Pause)` lặp lại, nên làm gì trước?

**Đáp án:** Tìm GC cause và heap/allocation patterns, xem concurrent mark có hoàn thành kịp không, đánh giá heap headroom; không chỉ tăng `ParallelGCThreads`.

**16.** `-XX:+UseParallelGC` có phải flag bật G1 Parallel Full GC không?

**Đáp án:** Không. Nó chọn **collector Parallel GC**. Muốn chọn G1, dùng `-XX:+UseG1GC`; parallel Full GC là khả năng tích hợp từ Java 10.

**17.** `User=0.2s Real=0.05s` có khẳng định Full GC là concurrent với ứng dụng không?

**Đáp án:** Không. Nhiều workers trong một STW pause cũng có thể tiêu thụ tổng CPU time lớn hơn wall-clock time.

**18.** Tại sao vẫn cần theo dõi p99 latency khi G1 đã song song hóa Full GC?

**Đáp án:** Vì mutators vẫn chờ trong STW pause; Full GC hiếm nhưng dài vẫn có thể làm hỏng SLA.

## 21. Nguồn chính thức

- [OpenJDK JEP 307 — Parallel Full GC for G1](https://openjdk.org/jeps/307): mục tiêu và cải tiến **Java 10**; Full GC song song trong G1.
- [Oracle JDK 25 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): G1 là collector **generational, incremental, parallel, mostly concurrent, stop-the-world**, các pha young/mixed, concurrent mark, remark/cleanup, Full GC fallback.
- [Oracle JDK 25 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): nguyên nhân Full GC, evacuation failure, humongous objects, `MaxGCPauseMillis`, `ParallelGCThreads` và `ConcGCThreads`.
- [Oracle JDK 27 — Garbage-First G1 Collector](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html): mô hình G1 và các khuyến nghị mới trên JDK hiện đại.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): JVM options, Unified Logging, ý nghĩa các flags.
- [Dev.java — The G1 Garbage Collector](https://dev.java/learn/jvm/tool/garbage-collection/g1gc-overview/): giới thiệu hành vi G1, soft pause goal và lưu ý performance.
- [Oracle Java SE 25 — `HotSpotDiagnosticMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html): truy vấn VM options để kiểm tra cấu hình HotSpot.
- [Oracle Java SE 25 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/25/jfapi/): khả năng quan sát GC và safepoint theo thời gian.

**Ghi nhớ cuối cùng:** **G1 Full GC song song từ Java 10 (JEP 307), nhưng đó vẫn là một STW pause.** Parallel mô tả **GC workers cùng làm việc**; concurrent mô tả **GC và ứng dụng chồng lấp thời gian**. G1 có concurrent marking và những STW pauses khác nhau; đừng coi chúng là Full GC. Trong production, ưu tiên **tránh Full GC** và đo nguyên nhân/latency thực tế thay vì tin rằng tăng workers sẽ làm ứng dụng không còn dừng.