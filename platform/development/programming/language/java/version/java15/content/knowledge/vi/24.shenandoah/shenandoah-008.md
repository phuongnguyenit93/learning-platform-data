# Shenandoah: Dấu hiệu collector không theo kịp ứng dụng trong Java 15+

## 1. Mục tiêu và vấn đề cần nhận diện

**Shenandoah GC** là bộ thu gom rác có mục tiêu giảm độ dài các lần tạm dừng Java application threads bằng cách làm phần lớn công việc GC **đồng thời** với ứng dụng. Tuy nhiên, “pause ngắn” **không** có nghĩa GC luôn giải phóng bộ nhớ kịp tốc độ ứng dụng cấp phát, hay tất cả request đều phản hồi nhanh.

Khi ứng dụng tạo objects nhanh, giữ quá nhiều objects sống hoặc bị giới hạn CPU/heap, Shenandoah có thể **không hoàn tất chu kỳ concurrent đúng lúc để tạo đủ không gian cấp phát**. Triệu chứng có thể là tăng độ trễ do **allocation pacing**, áp lực heap, quá nhiều GC cycles, **Degenerated GC**, **Full GC**, giảm throughput hoặc cuối cùng là `OutOfMemoryError`. Mức độ và cơ chế cụ thể phụ thuộc vào JDK, chế độ Shenandoah và workload.

Bài tập trung trả lời **đề bài “Dấu hiệu collector không theo kịp ứng dụng”**, không phải bảng so sánh chung tất cả GC. Sau khi học, bạn có thể:

1. Nhận diện **tín hiệu cảnh báo sớm**: tốc độ cấp phát, heap headroom, live set, GC activity, CPU pressure, application p99.
2. Phân biệt **pacing** của mutators, **Degenerated GC** và **Full GC**; không đánh đồng chúng với một GC cycle bình thường.
3. Biết khi nào heap thật sự thiếu chỗ vì objects vẫn còn sống và khi nào concurrent GC chỉ thiếu thời gian/CPU.
4. Dùng logging `-Xlog`, JFR, JMX, heap và container metrics để **xác nhận bằng dữ liệu**, không suy từ một con số.
5. Chạy ví dụ Java biên dịch bằng `javac --release 15`, có bài toán tính xác định và hai workload cùng tổng cấp phát nhưng khác mức retention.
6. Hiểu **tình trạng hiện hành** của Shenandoah: Java 15 production; JDK 25 đưa **Generational Shenandoah** ra khỏi trạng thái experimental, nhưng không vì vậy mặc định chọn chế độ generational ở mọi JDK.
7. Chọn biện pháp phù hợp: giảm allocations/retention, tạo heap/CPU headroom, xử lý burst và thử tuning từng bước, tránh cờ legacy hay mẹo làm mất an toàn.

**Phạm vi:** Ví dụ có mục đích học/đọc GC logs, **không** cố ép hệ thống vào `Full GC` hoặc OOM và **không** thay thế load test đại diện production.

## 2. “GC không theo kịp” nghĩa chính xác là gì?

Một ứng dụng tạo objects (*mutators allocate*) trong khi Shenandoah đánh dấu, di chuyển hoặc giải phóng các đối tượng không còn được tham chiếu. Trong một khoảng thời gian:

- **Allocation rate** `A(t)`: bytes Java heap được cấp phát mỗi giây.
- **Live/retained set** `L(t)`: bytes của objects vẫn reachable; GC **không thể** thu hồi chúng.
- **Reclaim/reusable capacity**: khoảng trống thật sự được phục hồi để allocator tiếp tục dùng; **không** đồng nghĩa số bytes GC đã quét.
- **Headroom**: dung lượng cấp phát hữu dụng còn lại, có tính đến heap occupancy, reserve/generation và các giới hạn của collector.
- **Concurrent cycle duration**: thời gian GC cần để đi qua các pha và trả lại đủ vùng có thể dùng, trong lúc mutators tiếp tục cấp phát.
- **CPU supply**: số core và quota thực tế dành cho ứng dụng và các GC threads; chúng có thể cạnh tranh tài nguyên.

“**Không theo kịp**” là khi **mức cấp phát cần không gian mới trong cửa sổ thời gian đó nhanh hơn khả năng collector cung cấp các vùng dùng được**, khiến khoảng trống hữu dụng giảm sát ngưỡng. Nếu kéo dài, JVM phải điều chỉnh: hạn chế tốc độ cấp phát, thực hiện cơ chế cứu hộ hoặc không đáp ứng được yêu cầu cấp phát.

Đây là kết quả của **tương quan nhiều biến**, không thể rút từ riêng `GC count`. Một chương trình có hàng chục chu kỳ GC ngắn, live set ổn định và p99 request tốt vẫn có thể hoàn toàn bình thường. Ngược lại, chu kỳ GC không quá nhiều nhưng heap-after-GC cứ cao lên và requests bị chờ mới đáng lo.

### Minh họa tiến trình

```text
Ứng dụng:     alloc ---> alloc ---> alloc ---> alloc
                           |         |          |
GC Shenandoah:      concurrent mark/evac/reclaim ------->
                    ^                            ^
                    |                            |
                  bắt đầu                      có vùng được
                  cycle                        trả lại

Heap headroom:  [nhiều] --> [ít hơn] --> [rất ít] --> [hồi phục?]
                                                       |
  nếu hồi phục kịp   -> xử lý bình thường              |
  nếu không kịp      -> pacing / failure fallback / OOM
```

**Concurrent không có nghĩa GC không bao giờ pause.** Shenandoah vẫn có các đồng bộ ngắn, và khi không theo kịp trong những trường hợp nhất định, các bước fallback có thể tạo STW dài hơn đáng kể.

## 3. Bảng nhận diện các dấu hiệu — mức độ và cách xác minh

| Quan sát | Mức cảnh báo | Vì sao có thể xảy ra | Bằng chứng cần đối chiếu |
| --- | --- | --- | --- |
| Allocation rate (MiB/s) tăng mạnh trong burst | **Sớm**, chưa đủ kết luận | Mutators đòi vùng cấp phát mới nhanh hơn | JFR allocation sampling, app traffic, bytes/request |
| Heap free/headroom giảm nhanh trong lúc GC đang chạy | **Sớm** | Chu kỳ thu gom chưa trả lại đủ vùng | GC log heap states, heap used/after-GC, max/committed |
| GC cycles bắt đầu dồn dập / diễn ra gần như liên tục | **Cảnh báo** nếu kèm áp lực | Heuristics cố làm việc thường xuyên để giữ trống | `-Xlog:gc` và `gc+ergo`, CPU/throttle |
| Mutator **allocation pacing** tăng / request chậm nhưng STW ngắn | **Cảnh báo rõ** | Collector cố hạn chế allocation để tạo thời gian thu gom | Shenandoah logs/stats nếu có, latency traces, CPU |
| Log có **Allocation Failure / cancelled cycle** | **Nghiêm trọng** trong ngữ cảnh liên quan | Một số allocations không đủ chỗ ở giai đoạn hiện tại | GC cause, thời điểm, heap, workload, JDK mode |
| **Degenerated GC** do allocation failure | **Nghiêm trọng** | Concurrent cycle chuyển sang xử lý STW | GC logs với cause; các pause và app p99 |
| **Full GC** do thiếu khả năng thu hồi | **Rất nghiêm trọng** | Collector phải dùng fallback toàn heap hoặc không còn tiến triển | GC logs + nguyên nhân Full; heap-after, live set |
| Allocation stalls, timeout ứng dụng, giảm throughput | **Ảnh hưởng thực tế** | Threads chờ bộ nhớ/CPU hoặc request queueing | Request latency, timeouts, JFR, GC+OS metrics |
| Heap-after-GC tăng đều dù collection chạy | **Nghi vấn retained data** | Objects còn reachable, cache/backlog/leak | Heap profiling, dominator tree, old/retained occupancy |
| `OutOfMemoryError` hoặc container OOM kill | **Sự cố** | Heap/native/cgroup vượt giới hạn | JVM error logs, heap dump nếu có, RSS/cgroup peak |

**Quan trọng:** Không xem mọi “Full GC” đều chứng minh “Shenandoah không theo kịp allocation”. Full GC còn có thể có **nguyên nhân khác** tùy chế độ/JDK/các yêu cầu từ ứng dụng. Phải xem **GC cause** và trạng thái trước/sau. Ngược lại, nếu log không có Full GC cũng **chưa** chứng minh ứng dụng không bị pacing latency.

## 4. Dấu hiệu 1: tốc độ cấp phát và headroom mất cân bằng

Đơn giản hóa bài toán bằng:

```text
Hmax       = heap max (MiB)
U          = heap occupancy ước lượng tại một thời điểm (MiB)
F_simple   = Hmax - U  (MiB)
A          = tốc độ cấp phát trung bình trong cửa sổ (MiB/s)
T_cycle    = thời gian đến khi có đủ vùng được thu hồi (s)

D_simple   = A × T_cycle  (MiB cấp phát khi đang chờ)
Nếu D_simple > F_simple: có cảnh báo về thiếu headroom.
```

**Đây chỉ là mô hình kiểm tra sức ép, KHÔNG phải điều kiện đủ/cần cho allocation failure trong Shenandoah.** Tại thời điểm chạy thực tế, heap used có thể bao gồm garbage có thể thu hồi, collector cấp phát vào generation/region nhất định, có reserve, fragmentation, refill và công việc thu gom không đều. Một phần vùng có thể được trả lại trong khi cycle còn diễn ra. Còn `T_cycle` dài không có nghĩa toàn bộ app bị pause lâu như vậy.

### Ví dụ tính có thể tái tạo

Giả sử:
- Heap maximum **512 MiB**;
- Heap occupancy ước lượng **430 MiB**;
- Còn `512 − 430 = 82 MiB` theo phép trừ đơn giản;
- Tốc độ cấp phát khi burst **120 MiB/s**;
- Một khoảng chờ GC tạo thêm chỗ dài **1 giây**.

Lượng cấp phát dự kiến: **120 MiB**. Mức thiếu so với headroom thô: `120 − 82 = 38 MiB`. Mô hình gắn **risk=true**.

Nếu giảm retention/occupancy còn **300 MiB** và giảm allocation còn **60 MiB/s** trong 1 giây:
- Headroom thô = `512 − 300 = 212 MiB`;
- Demand = **60 MiB**;
- Risk theo mô hình = **false**.

**Không được diễn giải** “rủi ro 38 MiB” là sẽ thiếu đúng 38 MiB RAM trong JVM, hoặc collector nhất định phải làm Full GC sau 1 giây. Giá trị được chọn để minh họa mối quan hệ **capacity × time**, không phải phép mô phỏng các heuristics thực của Shenandoah.

### Vì sao peak quan trọng hơn average?

Một service bình quân cấp phát 200 MiB/s nhưng trong 500 ms cao điểm có thể đạt 1,5 GiB/s. Trong thời gian đó, các yêu cầu khác cũng có thể làm CPU quá tải; collector concurrent có **ít CPU còn rảnh** hơn và mất thời gian hoàn thành cycle. Do vậy phải quan sát allocation **theo các khoảng ngắn phù hợp** với GC cycle và request SLO, không chỉ thống kê trung bình 24 giờ.

## 5. Dấu hiệu 2: pacing bắt đầu làm chậm application threads

**Allocation pacing** là cơ chế để Shenandoah **giảm tốc độ cấp phát của mutators** khi cần, cho collector thêm cơ hội bắt kịp. Đây là một trade-off có chủ đích: ứng dụng có thể chờ ở điểm cấp phát để tránh rơi vào fallback nặng hơn.

Một tình huống dễ nhầm:

```text
GC STW pause:       p99 = vài ms
HTTP response p99:  tăng từ 30 ms lên 180 ms
Allocation rate:    tăng mạnh
Heap headroom:      giảm
Pacing delays:      xuất hiện/tăng
```

Các số ở đây **chỉ là ví dụ giả định**. Khi pacing ảnh hưởng nhiều threads, bạn có thể thấy end-to-end latency tăng dù các GC pause events trong log vẫn ngắn. **Không đưa pacing delay vào GC STW pause** để tuyên bố “toàn bộ app bị GC dừng” — bản chất của hai khoảng thời gian khác nhau.

Những kiểm tra hữu ích:
- Có quan sát **pacing activity/delay** trong logs hoặc Shenandoah stats của **JDK/build đang chạy** không?
- Application traces có time spent/blocked trong vùng allocation hoặc request queueing liên quan không?
- CPU utilization của GC và mutators có tăng đồng thời? Cgroup CPU quota có bị throttle?
- Heap occupancy có hồi phục sau cycle, hay cứ tăng ngay cả khi allocator bị giảm tốc?
- Sau khi giảm burst/retention, pacing có giảm và app p99 có phục hồi không?

**Không chữa bằng cách vô hiệu hóa pacing mù quáng.** Việc loại bỏ/giảm cơ chế điều tiết có thể biến hiện tượng request chậm vừa phải thành allocation failure, Degenerated hoặc Full GC. Ngược lại, tăng mức pacing cũng có thể làm user latency xấu hơn. Phải đánh giá theo SLO **end-to-end** và chính sách throughput/footprint.

## 6. Dấu hiệu 3: Degenerated GC hoặc Full GC

### 6.1. Degenerated GC là fallback gì?

Ở những chế độ/bản triển khai Shenandoah hỗ trợ, khi **concurrent collection không hoàn thành hữu ích trước một allocation failure**, collector có thể **chuyển phần chu kỳ đang làm sang stop-the-world** để hoàn tất tiến trình thu gom nhanh hơn mà không tranh CPU với mutators.

Dòng log thường có ý nghĩa như:

```text
... Allocation Failure ...
... Pause Degenerated GC (...) ...
```

Đây là **mẫu để tìm ý nghĩa**, không phải bản ghi đầu ra được đảm bảo chữ nào cũng giống nhau trên mọi JDK. Cần xem log thực của runtime, GC phase, trigger và cause. Việc có Degenerated GC do allocation failure thường là **tín hiệu mạnh collector bị đẩy sát giới hạn** bởi allocation, heap headroom hoặc CPU supply trong khoảng đó.

**Không coi Degenerated GC là cơ chế vận hành thường xuyên nên chấp nhận** cho dịch vụ low-latency. Nó có thể tạo pauses dài, ảnh hưởng p99/p99.9. Tuy nhiên **một occurrence đơn lẻ** sau một burst cực đoan cần được đánh giá trong ngữ cảnh, không mặc định kết luận memory leak.

### 6.2. Full GC

Khi các biện pháp khác không đủ, Shenandoah có thể phải dùng **Full GC** theo cơ chế của phiên bản/chế độ cụ thể. Đây thường là một **stop-the-world event tốn kém** và có khả năng phá vỡ latency SLO.

```text
Concurrent cycle không theo kịp
             |
             v
   allocation failure / emergency
             |
             v
    Degenerated GC (nếu áp dụng)
             |
         tiến triển?
        /          \
       có          không
       |             |
  quay lại      Full GC / các
  bình thường   đường fallback khác
```

Sơ đồ là **mô hình trực quan**, không phải state machine ràng buộc mọi JDK. Trong Generational Shenandoah, các global/young/old cycles và đường fallback có khác biệt; xem JEP 521 cùng logs của build thực tế.

Phân tích Full GC cần ghi:
- Event có đúng loại **Shenandoah Full** và nguyên nhân `Allocation Failure` không?
- Heap used trước/sau Full có giảm đáng kể hay live set vẫn rất lớn?
- Có large objects, long-lived cache, queue backlog, fragmentation hoặc thiếu CPU headroom?
- Full GC có lặp lại và spacing giữa các lần giảm dần không?
- Request timeout, GC pause p99, throughput và CPU/cgroup có đồng thời xấu đi không?

Nếu Full GC không giải phóng đủ bytes vì quá nhiều objects còn sống, chạy thêm Full GC **không thể tự chữa**. Cần thay đổi lượng giữ dữ liệu, nâng capacity hợp lý hoặc sửa memory leak.

## 7. Dấu hiệu 4: hiệu suất giảm dù không có Full GC

Một hệ thống có thể “không theo kịp” **trước** khi đi tới Full GC. Dấu hiệu tại tầng ứng dụng:
- Throughput hoàn thành **request/s** giảm ở cùng mức tải.
- p95/p99/p99.9 response latency và timeouts tăng.
- Mức CPU concurrent GC tăng; CPU dành cho business logic giảm.
- Độ trễ tăng quanh những burst allocations, hoặc sau các thay đổi cache/retention.
- Pending requests/hàng đợi tăng dù các pausing events ngắn.
- Container CPU throttling khiến cả concurrent GC lẫn mutators chậm.
- Heap occupancy gần trần và các cycles bắt đầu sát nhau.

**Đừng gán nguyên nhân cho Shenandoah ngay.** Một request p99 cao cũng có thể do database, network, lock contention, disk I/O, CPU scheduling, JIT, thread pool hoặc backpressure. Cách đúng là dùng timestamp để đối chiếu **GC events + allocation + CPU + request traces**, rồi thay đổi có kiểm soát để xem độ trễ có phục hồi.

### GC pause p99 không phải application p99

| Metric | Đo cái gì? | Không suy ra được |
| --- | --- | --- |
| GC pause p99 | Phân vị của **các pause events** | Không phải phân vị **request durations** |
| Total concurrent GC time | Các pha chạy trong lúc app có thể tiếp tục | Không đồng nghĩa application đã bị dừng suốt thời gian đó |
| Request p99 | Tốc độ hoàn thành ở đuôi phân phối request | Không xác định GC là nguyên nhân nếu thiếu tracing |
| GC bean collection time | Số liệu quản trị theo collector | Không đảm bảo bằng STW pause time với concurrent collector |
| Allocation pacing | Thời gian/thao tác bị điều tiết tại allocation path | Có thể không xuất hiện trong biểu đồ STW pause |

Các chỉ số có mẫu số khác nhau; không lấy **GC p99 5 ms** để phủ nhận **API p99 500 ms**, hoặc khẳng định GC là nguyên nhân duy nhất.

## 8. Dấu hiệu 5: live set hoặc footprint thực tế tăng quá lớn

**Allocation rate cao** và **retention cao** là hai bài toán khác nhau.

- Workload A tạo 1 GiB objects ngắn hạn, các tham chiếu được thay liên tục → nhiều garbage có thể thu hồi, nhưng tốn công GC/CPU.
- Workload B tạo 1 GiB objects nhưng vẫn giữ các tham chiếu trong cache/queue → live set tăng, **GC không thể thu hồi objects vẫn reachable**.
- Một cache không giới hạn, queue backlog, session data giữ quá lâu hoặc `static Map` phát triển mãi có thể làm heap-after-GC tăng đều. Tăng số GC cycles không thay đổi tính reachable.

Hãy quan sát:
1. Heap occupancy **sau các cycles hoàn thành** có quay về mức nền ổn định không?
2. Old/live objects hoặc cache entries có liên tục tăng cùng request rate không?
3. Heap profiling cho thấy ai giữ references? Bounded cache có eviction/TTL đúng?
4. Có queue backlog hoặc retries đẩy retention lên theo thời gian?
5. `-Xmx` có đủ **live set + headroom** để GC concurrently chạy không?

**Footprint không chỉ Java heap**: metaspace, thread stacks, direct buffers, native GC metadata, code cache và JVM/OS pages vẫn chiếm RAM. `-Xmx256m` **không bảo đảm** process RSS ≤ 256 MiB hoặc container memory limit 256 MiB là đủ.

Một **container OOM kill** có thể xảy ra dù Java heap used còn dưới max. Khi đó kiểm tra RSS/cgroup peak và native memory, không chỉ heap graph.

## 9. Đọc đúng phiên bản Shenandoah: Java 15 và JDK hiện hành

### 9.1. Các mốc còn cần biết

| Mốc | Tình trạng |
| --- | --- |
| **Java 15** | **Shenandoah production** từ OpenJDK **JEP 379**, trong giai đoạn collector chủ yếu single-generation |
| **JDK 24** | **Generational Shenandoah** được giới thiệu dưới dạng **experimental** (JEP 404); không nên đưa các cờ experimental của mốc này thành mặc định vận hành chung |
| **JDK 25** | **Generational Shenandoah** trở thành **product feature** (JEP 521), có thể chọn khi build hỗ trợ |
| **JDK 25+ (dựa trên tài liệu launcher được tra cứu)** | Chế độ `satb` (single-generation) vẫn là **default**; muốn dùng generational phải **chọn rõ** chế độ trên bản JDK có hỗ trợ |

Điều này rất khác câu chuyện của **ZGC**. Không được suy từ việc “JDK 25 đã có Generational Shenandoah production” rằng cờ `-XX:+UseShenandoahGC` chắc chắn **mặc định generational**.

### 9.2. Cờ chạy hợp lệ khi build hỗ trợ

Một ví dụ Shenandoah chuẩn:

```bash
java -XX:+UseShenandoahGC -Xms128m -Xmx256m \
  ShenandoahPressureSignsDemo --load 120000 1024
```

Trên **JDK 25+ có hỗ trợ Generational Shenandoah**, có thể yêu cầu chế độ generational:

```bash
java -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xms128m -Xmx256m \
  ShenandoahPressureSignsDemo --load 120000 1024
```

Lệnh thứ hai là hướng dẫn **theo JEP 521/JDK 25+**, **không phải lệnh đã chạy kiểm chứng trong bài** (môi trường thử hiện tại là OpenJDK 24 và sử dụng mặc định của bản build). Trên JDK 24 generational còn experimental; đừng cố sao chép cờ thử nghiệm chỉ để chuyển chế độ khi production chưa được phê duyệt. Bản build/vendor/OS có thể không hỗ trợ Shenandoah; khi gặp flag không được chấp nhận thì xem tài liệu của chính runtime, **không âm thầm fallback rồi báo đang đo Shenandoah**.

Trong Generational Shenandoah, chế độ heuristics được hỗ trợ chủ yếu là **adaptive**; điều chỉnh thủ công các tuning options của phiên bản single-generation phải được xem lại theo JDK thực tế. **Ưu tiên heuristics mặc định và đo workload trước khi chỉnh chi tiết.**

## 10. Quan sát bằng GC Unified Logging, JFR và số liệu ứng dụng

### 10.1. Bật log để tìm chính xác cause, pacing và fallback

Với HotSpot/JDK có Shenandoah:

```bash
java -XX:+UseShenandoahGC \
  -Xms128m -Xmx256m \
  '-Xlog:gc*,gc+ergo=debug,gc+stats=info:file=shenandoah.log:uptime,level,tags' \
  ShenandoahPressureSignsDemo --load 120000 1024
```

Lệnh có các chức năng:
- `gc*`: sự kiện GC/phases, gồm bắt đầu/kết thúc cycles, heap states và pause events tùy bản build.
- `gc+ergo=debug`: thêm quyết định heuristic khi tương ứng; giúp tìm vì sao GC khởi động sớm/muộn.
- `gc+stats=info`: thống kê của Shenandoah nếu runtime phát sự kiện tương ứng; những nhóm/tên dòng có thể thay đổi theo phiên bản.
- `file=shenandoah.log:uptime,level,tags`: ghi vào file với timestamp tương đối, level và tags.

**Lệnh trên đã được thử thực tế với OpenJDK 24 và tạo GC logs.** Trong môi trường PowerShell có thể dùng dấu nháy kép quanh giá trị `-Xlog:...`; trên Unix shell dùng nháy đơn như trên.

Sau khi ghi log, tìm các chủ đề (không phụ thuộc chuỗi cứng duy nhất):
- **Concurrent cycle**: collector có đang liên tục làm việc không?
- **Allocation Failure** / cancellation: có giai đoạn nào không đủ không gian cấp phát?
- **Degenerated GC** hoặc **Full GC**: có fallback STW không, và vì cause gì?
- **Pacing**/stats: mutator có bị giảm tốc?
- **Before/after heap occupancy**, free regions và những dấu hiệu thiếu headroom.
- **GC duration/cause** so với thời điểm request p99 tăng.

Ví dụ tìm nhanh:

```bash
grep -Ei 'Degenerated|Full GC|Allocation Failure|Pacing|Concurrent' shenandoah.log
```

Đây là lệnh **gợi ý quan sát** trong shell có `grep`, không phải tiêu chí QA “bắt buộc phải tìm thấy” mọi từ khóa. Nếu workload không gây allocation failure thì **đó là kết quả bình thường**, không phải chương trình hoặc log bị lỗi.

**Không parse cố định tên event của Shenandoah Java 15 rồi áp dụng nguyên xi cho Generational Shenandoah JDK 25+.** Đọc tài liệu và logs tương ứng phiên bản; xem cả `-Xlog:gc+stats` trên những bản build có hỗ trợ summary.

### 10.2. Java Flight Recorder

Có thể dùng JFR để theo dõi allocations, GC phases, thread states và CPU:

```bash
java -XX:+UseShenandoahGC \
  -Xms128m -Xmx256m \
  -XX:StartFlightRecording=filename=shenandoah.jfr,settings=profile,dumponexit=true \
  ShenandoahPressureSignsDemo --load 120000 8192
```

Phân tích bằng JDK Mission Control hoặc công cụ `jfr` đi cùng JDK. Tùy version và cấu hình recording, các event có thể gồm `jdk.GarbageCollection`, `jdk.GCPhasePause`, allocation sampling và thread/CPU events. **Không giả định mọi sự kiện pacing hoặc allocation stall đều bật mặc định hay xuất hiện với cùng tên trên tất cả builds**.

Để tìm nguyên nhân:
- Đối chiếu GC timestamps với request trace và CPU/OS metrics.
- Dùng allocation profiling để tìm class/call path tạo nhiều bytes.
- Nếu heap-after-GC tăng, dùng heap profiling/heap dump để thấy dominator/retained references.
- Tìm CPU throttling hoặc I/O thay vì mặc định mọi request chậm đều do GC.

### 10.3. JMX/MXBeans: hữu ích nhưng không đủ

Java hỗ trợ `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage()` và `ManagementFactory.getGarbageCollectorMXBeans()` để lấy:
- Heap `used`, `committed`, `max`.
- GC bean `getName()`, `getCollectionCount()`, `getCollectionTime()`.

**Đừng suy:** `getCollectionTime()==0` chứng minh “GC không tốn thời gian”, hoặc sum của collection times luôn bằng tổng STW pause. Với GC concurrent, giá trị có thể đại diện các loại sự kiện khác nhau/độ phân giải mili giây và một số metrics có thể là `-1` khi không hỗ trợ.

Muốn đánh giá collector “không theo kịp” nên kết hợp **GC cause logs**, **application latency/throughput**, **allocation rate**, **heap headroom**, **CPU quotas**, **RSS/cgroup**.

## 11. Chương trình Java 15 độc lập: tính toán cảnh báo và thử allocations

Chương trình có hai mode:

- **`--model`:** tính headroom thô và allocation demand trong một “cycle window” giả định. Output hoàn toàn xác định, **không đo GC thật**.
- **`--load count slots`:** tạo `count` mảng, mỗi mảng **8192 bytes**, ghi đè vào ring buffer kích thước `slots`. Hai lần chạy với cùng `count` có **cùng tổng payload bytes allocated**, nhưng số bytes còn giữ trong ring khác nhau. In số lượng, tổng payload bytes, dung lượng retained payload, throughput vòng lặp và heap/GC MXBeans. **Không chủ ý ép OOM hay Full GC**.

Lưu tệp đúng tên **`ShenandoahPressureSignsDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.Locale;

public final class ShenandoahPressureSignsDemo {
    private static volatile byte[][] keepAlive;
    private static volatile long checksum;

    public static void main(String[] args) {
        if (args.length == 0 || "--model".equals(args[0])) {
            model();
        } else if ("--load".equals(args[0])) {
            int count = args.length > 1
                    ? Integer.parseInt(args[1]) : 120000;
            int slots = args.length > 2
                    ? Integer.parseInt(args[2]) : 1024;
            if (count < 10000 || count > 500000 || slots < 256
                    || slots > 8192 || slots > count) {
                throw new IllegalArgumentException(
                        "invalid count or slots");
            }
            load(count, slots);
        } else {
            throw new IllegalArgumentException(
                    "Usage: ShenandoahPressureSignsDemo "
                    + "[--model | --load count slots]");
        }
    }

    private static void model() {
        final int maxMiB = 512;
        final int usedMiB = 430;
        final int allocationMiBPerSecond = 120;
        final int cycleMillis = 1000;

        int headroomMiB = maxMiB - usedMiB;
        int demandMiB = allocationMiBPerSecond * cycleMillis / 1000;

        System.out.println("model heap maximum (MiB): " + maxMiB);
        System.out.println("model free headroom (MiB): " + headroomMiB);
        System.out.println("model demand during cycle (MiB): " + demandMiB);
        System.out.println("model deficit (MiB): "
                + Math.max(0, demandMiB - headroomMiB));
        System.out.println("model pressure risk: "
                + (demandMiB > headroomMiB));

        int improvedUsedMiB = 300;
        int improvedAllocationMiBPerSecond = 60;
        int improvedHeadroom = maxMiB - improvedUsedMiB;
        int improvedDemand = improvedAllocationMiBPerSecond
                * cycleMillis / 1000;

        System.out.println("improved free headroom (MiB): "
                + improvedHeadroom);
        System.out.println("improved demand during cycle (MiB): "
                + improvedDemand);
        System.out.println("improved pressure risk: "
                + (improvedDemand > improvedHeadroom));
    }

    private static void load(int count, int slots) {
        final int allocationSize = 8192;
        byte[][] retained = new byte[slots][];
        long start = System.nanoTime();

        for (int i = 0; i < count; i++) {
            byte[] bytes = new byte[allocationSize];
            bytes[0] = (byte) (i & 0xff);
            retained[i % slots] = bytes;
        }

        long elapsed = System.nanoTime() - start;
        keepAlive = retained;

        long sum = 0;
        for (byte[] bytes : retained) {
            sum += bytes[0] & 0xff;
        }
        checksum = sum;

        MemoryUsage heap = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage();
        System.out.println("operations: " + count);
        System.out.println("retained slots: " + slots);
        System.out.printf(Locale.ROOT,
                "allocated payload (MiB): %.1f%n",
                count * (double) allocationSize / 1048576.0);
        System.out.printf(Locale.ROOT,
                "retained payload (MiB): %.1f%n",
                slots * (double) allocationSize / 1048576.0);
        System.out.printf(Locale.ROOT,
                "loop throughput (ops/s): %.1f%n",
                count * 1000000000.0 / elapsed);
        System.out.printf(Locale.ROOT,
                "heap used/committed/max (MiB): %.1f / %.1f / %.1f%n",
                mib(heap.getUsed()), mib(heap.getCommitted()),
                mib(heap.getMax()));

        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("GC bean: " + gc.getName()
                    + " count=" + gc.getCollectionCount()
                    + " timeMs=" + gc.getCollectionTime());
        }

        if (checksum == Long.MIN_VALUE) {
            System.out.println("unexpected checksum");
        }
    }

    private static double mib(long bytes) {
        return bytes / 1048576.0;
    }
}
```

### 11.1. Biên dịch và chạy mode tính toán

Với một JDK hỗ trợ mục tiêu Java 15:

```bash
javac --release 15 ShenandoahPressureSignsDemo.java
java ShenandoahPressureSignsDemo --model
```

**Stdout chính xác của mode này, đã chạy kiểm thử:**

```text
model heap maximum (MiB): 512
model free headroom (MiB): 82
model demand during cycle (MiB): 120
model deficit (MiB): 38
model pressure risk: true
improved free headroom (MiB): 212
improved demand during cycle (MiB): 60
improved pressure risk: false
```

Tám dòng này là kết quả **toán học minh họa**, không phải sự kiện GC/fallback được quan sát. Ví dụ chỉ chuyển các số đã chọn thành dấu hiệu thiếu headroom thô; collector thực tế có heuristics, reserve và phase behavior phức tạp hơn.

### 11.2. Chạy hai workload Shenandoah với cùng tổng cấp phát

Sau khi đã biên dịch, chạy với Java runtime có Shenandoah:

```bash
# Giu lai 1024 mang, ~8 MiB payload.
java -XX:+UseShenandoahGC -Xms128m -Xmx256m \
  '-Xlog:gc*,gc+ergo=debug,gc+stats=info:file=shenandoah-1024.log:uptime,level,tags' \
  ShenandoahPressureSignsDemo --load 120000 1024

# Giu lai 8192 mang, ~64 MiB payload.
java -XX:+UseShenandoahGC -Xms128m -Xmx256m \
  '-Xlog:gc*,gc+ergo=debug,gc+stats=info:file=shenandoah-8192.log:uptime,level,tags' \
  ShenandoahPressureSignsDemo --load 120000 8192
```

Trong cả hai lần:
- `120000 × 8192 / 1048576 = 937,5 MiB` **payload của mảng** được cấp phát.
- Với `slots=1024`, lượng payload còn tham chiếu khoảng **8,0 MiB**.
- Với `slots=8192`, lượng payload còn tham chiếu khoảng **64,0 MiB**.

**Các dòng có thể dự đoán/đối chiếu chính xác**:

```text
# --load 120000 1024
operations: 120000
retained slots: 1024
allocated payload (MiB): 937.5
retained payload (MiB): 8.0

# --load 120000 8192
operations: 120000
retained slots: 8192
allocated payload (MiB): 937.5
retained payload (MiB): 64.0
```

Đây là **trích các dòng ổn định**, không phải toàn bộ stdout. Các dòng tiếp theo gồm `loop throughput`, `heap used/committed/max` và GC bean names/counters; kết quả thay đổi theo JDK, CPU/JIT, OS và thời điểm đo.

**Đã kiểm thử thực tế:** chương trình biên dịch bằng `javac --release 15` và chạy trên **OpenJDK 24** với `-XX:+UseShenandoahGC`. Cả hai lần chạy thành công, hai file GC logs được tạo. Ở một lượt đo, `slots=1024` cho khoảng 39,2 MiB heap used và 8 GC cycles; `slots=8192` cho khoảng 141,0 MiB heap used và 10 GC cycles. Đây là **số đo một lần duy nhất**, không phải bằng chứng “retention lớn chắc chắn làm collector kém hơn theo số cycles”.

### 11.3. Ranh giới giải thích ví dụ

- **`allocated payload`** được tính từ số vòng × `8192`; JVM còn object headers/alignment và allocations khác. Nó không phải số allocation bytes chính xác do JFR đo.
- **`retained payload`** chỉ là những mảng còn trong ring và vẫn reachable tại cuối vòng; không phải toàn bộ live set JVM.
- **`heap used`** là snapshot của MemoryMXBean, gồm nhiều thứ ngoài retained payload.
- **`loop throughput`** là operations/s của vòng cấp phát ngắn, **không** phải request throughput của service production.
- **`GC bean count/time`** không trực tiếp đo “reclaim MiB/s” hoặc p99 application response latency.
- **Không có Degenerated/Full trong workload này cũng hoàn toàn bình thường.** Mục tiêu không phải buộc JVM vào trạng thái nguy hiểm để cho ra một dòng log đáng sợ.

Chỉ khi kết hợp **load đại diện, đủ thời gian warmup/measurement, nhiều trial, timestamps và GC logs/JFR** mới có thể kết luận collector có thực sự không theo kịp ứng dụng.

## 12. Quy trình chẩn đoán khi thấy Shenandoah không theo kịp

### Bước 1 — Khoanh đúng loại sự cố

Xác định trong cùng khoảng thời gian:
- p99 request có tăng không? Throughput/error rate thay đổi thế nào?
- Heap used/after-GC, free headroom và live set biến động ra sao?
- Có pacing activity, `Allocation Failure`, `Degenerated GC` hoặc `Full GC` không?
- Có `OutOfMemoryError` hay container OOM kill không?

Phân biệt **symptom** với **cause**. Một đợt GC cycles dày nhưng ứng dụng vẫn đạt SLO có thể chưa cần “sửa GC”.

### Bước 2 — Đo allocation rate và root của allocation

Dùng JFR hoặc allocation profiler để tìm:
- Class, stack/call path và endpoint tạo nhiều bytes nhất.
- Temporary arrays/strings, serialization/deserialization, copies, boxing, DTO mapping.
- Bursts theo giờ cao điểm, retry storms, batch concurrency và object size.
- Allocation rate **per request** và **per second**; không chỉ tổng bytes.

Nếu allocation rate tăng do một bản cập nhật code, hãy kiểm tra đường code đó trước khi mở rộng heap vô hạn.

### Bước 3 — Đo retention và live set

Tìm những objects **không được thu hồi**:
- Cache không giới hạn, TTL/eviction lỗi.
- Hàng đợi xử lý tồn đọng; số inflight requests quá lớn.
- Session state, global maps, static references, listeners, thread locals.
- Data buffer lifetime quá dài hoặc các bản sao dư thừa.
- Request contexts vẫn bị giữ sau khi hoàn tất.

Dùng heap dump/retained size/dominator tree theo chính sách an toàn dữ liệu để xác định references giữ object. **Không kỳ vọng GC xóa object còn reachable**.

### Bước 4 — Đo CPU headroom thực

Concurrent GC cần CPU trong lúc mutators đang chạy:
- CPU quota Kubernetes/container có bị throttling không?
- Node có bị tranh chấp cores/NUMA/memory bandwidth?
- Số threads cấp phát có quá nhiều so với CPU budget?
- Concurrent phases có bị kéo dài khi traffic tăng?
- GC CPU có chiếm tài nguyên business làm p99/throughput giảm?

Thêm heap có thể **mua thêm thời gian**, nhưng nếu collector bị thiếu CPU nghiêm trọng, tốc độ hoàn thành chu kỳ vẫn có thể không đủ.

### Bước 5 — Kiểm tra heap và memory budget

Giá trị `-Xmx` phải đủ cho **live set và khoảng trống dùng trong lúc concurrent collection**, nhưng cũng phải nằm trong ngân sách RAM của process/container. Theo dõi:
- `heap used / committed / max` theo thời gian.
- Process RSS, native/off-heap, thread stacks, metaspace, code cache.
- Container/cgroup peak so với limit; khi dùng `-Xms = -Xmx`, footprint committed có thể cao ngay từ đầu.

Không tăng `-Xmx` đến đúng memory limit rồi nghĩ JVM đã có đủ RAM cho mọi thành phần khác.

### Bước 6 — Thử thay đổi **một** nguyên nhân mỗi lượt

Ví dụ trình tự:
1. Hạn chế concurrency/burst và giảm duplicated allocations.
2. Sửa bounded queue/cache/lifetime để giảm live set.
3. Nếu thiếu heap headroom thật và còn RAM budget, thử tăng heap hợp lý.
4. Nếu thiếu CPU cho concurrent GC, cân nhắc CPU quota hoặc tuning threads **sau khi** đã đo.
5. Đối chiếu `gc+ergo`, `gc+stats` và các fallback events với application traces.

**Không** đồng thời thay JDK, mode generational, heap max, số threads, cache và workload rồi kết luận cách nào có tác dụng.

### Bước 7 — Kiểm chứng lại trên load đại diện

Giữ cố định:
- JDK build/vendor/GC mode và flags;
- CPU quota, RAM/cgroup, container placement, dataset và request mix;
- Warmup, measurement time, load generator và instrumentation;
- Number of trials, peak/burst shape và error-rate threshold.

Báo cáo đồng thời **application p99/p99.9 + throughput + GC pacing/degenerated/full counts + heap/CPU/RSS**. Một cải thiện chỉ có ý nghĩa khi **đạt SLO** mà không chuyển sự cố sang CPU, RAM hoặc tỷ lệ lỗi.

## 13. Hướng xử lý theo nguyên nhân — đừng tối ưu mù

| Chẩn đoán có bằng chứng | Điều nên thử | Điều không nên làm |
| --- | --- | --- |
| Allocation rate cao vì tạo nhiều objects tạm | Giảm unnecessary copies/allocations, profile hotspot, cân nhắc buffer reuse có quản lý | Pool mọi object nhỏ không đo đạc; pooling có thể tăng live set |
| Live set tăng vì cache/backlog | Bounded cache, eviction TTL, limit queue/inflight, release references | Gọi `System.gc()` liên tục để “xóa” reachable objects |
| Burst vượt headroom trong GC cycle | Admission control, backpressure, giảm batch concurrency, tăng heap nếu đủ RAM | Chỉ tăng `-Xmx` mà quên cgroup peak |
| GC concurrent thiếu CPU | Tăng CPU quota/headroom, kiểm tra throttling, tối ưu mutator, thử GC threads theo dữ liệu | Mặc định “thêm GC threads là tốt” |
| Pacing kéo dài dù ít Full GC | Đo pacing delay và app tail, xem nguyên nhân pressure | Tắt pacing để che latency mà không xử lý allocation |
| Degenerated/Full do Allocation Failure lặp lại | Đối chiếu GC cause, start timing, live set, heap/free và CPU; giảm pressure | Bỏ qua vì “Shenandoah low-pause nên Full GC không đáng kể” |
| Request p99 cao nhưng GC logs ổn | Xem DB/I/O/locks/thread pools/CPU | Gán mọi request chậm cho GC |
| Java heap ổn mà container OOM | Đo native memory, RSS/cgroup, direct buffers/stacks | Chỉ xem `MemoryMXBean.getHeapMemoryUsage()` |
| GenShen vs single-gen khác hiệu năng | So cùng build với mode được hỗ trợ và workload đại diện | Tin rằng mode mặc định giống ZGC hoặc dùng cờ experimental cũ |

**Cần chú ý trade-off:** tăng heap có thể giảm tần suất GC/pressure nhưng tăng RSS/cost; tăng GC CPU có thể giúp concurrent cycle hoàn tất sớm nhưng làm mutators chậm; giảm pacing có thể cải thiện latency ngắn hạn nhưng tăng nguy cơ fallback. Bởi vậy phải theo mục tiêu **latency + throughput + footprint + reliability**.

## 14. Gợi ý dashboard và cảnh báo vận hành

Thay vì tạo alert dựa trên một log pattern, hãy đặt **multi-signal**:

| Nhóm tín hiệu | Metric gợi ý | Dùng để |
| --- | --- | --- |
| Request | p95/p99/p99.9, timeout/error rate, throughput | Đo tác động thật tới người dùng |
| Allocation | MiB/s, bytes/request, top allocation paths | Xác định áp lực đầu vào |
| Heap | used/max, after-GC occupancy, headroom, live set | Phân biệt temporary garbage với retention |
| Shenandoah GC | concurrent cycles, cause, Degenerated/Full, pacing | Xác định cơ chế không theo kịp |
| CPU | app CPU, GC CPU, cgroup throttled time | Kiểm tra GC có đủ CPU không |
| OS/container | RSS, native memory, cgroup current/peak/limit | Tránh OOM kill và kiểm soát footprint |
| Backlog | queue depth, inflight requests, retry rate | Tìm nguồn burst và retention |

Một chiến lược alert có thể là: **application p99 tăng vượt SLO + heap headroom giảm + có pacing/fallback events** trong cùng thời gian. Đây là ví dụ điều kiện nhiều tín hiệu, **không phải ngưỡng cảnh báo tuyệt đối**. Mỗi workload cần threshold và cửa sổ quan sát dựa trên baseline, sample volume và capacity thật.

**Các alert hữu ích cần biết hướng xử lý:** báo “Full GC” không nói đủ. Alert nên kèm JDK/GC mode, cause, heap snapshot, allocation rate, CPU quota và liên kết dashboard traces/logs. Tránh alert storm khi nhiều events cùng một nguyên nhân.

## 15. Những hiểu nhầm thường gặp

1. **“Shenandoah concurrent nên không có stop-the-world.”** Sai. Vẫn có pauses và đôi khi fallback STW.
2. **“GC pause p99 thấp nghĩa là app không bị GC làm chậm.”** Sai. Mutator pacing/GC CPU có thể tăng end-to-end latency.
3. **“Cứ có Degenerated GC là JVM bug.”** Không. Đây có thể là phản ứng với allocation failure/pressure; cần cause và heap metrics.
4. **“Full GC luôn do memory leak.”** Sai. Có thể do pressure, fragmentation, cấu hình hoặc nguyên nhân khác; phải xem GC cause.
5. **“GC cycle count tăng nghĩa collector không theo kịp.”** Chưa đủ; có thể phục vụ allocation rate cao ổn định.
6. **“Một concurrent cycle 100 ms là 100 ms STW pause.”** Sai; phần concurrent chạy trong lúc app có thể tiếp tục.
7. **“Heap used bằng live set.”** Không tại mọi thời điểm; có garbage chưa được thu hồi.
8. **“GC có thể thu hồi object vẫn nằm trong cache reachable.”** Không; phải sửa retention/eviction.
9. **“Tăng Xmx luôn chữa allocation stalls.”** Không nếu thiếu CPU, live set tăng vô hạn hoặc container thiếu RAM.
10. **“Xmx bằng container limit là an toàn.”** Sai vì còn native/off-heap và overhead JVM.
11. **“Bỏ pacing sẽ khiến Shenandoah nhanh hơn về mọi mặt.”** Không; có thể tăng allocation failure và Full GC.
12. **“Tăng ConcGCThreads luôn làm API nhanh hơn.”** Không; cạnh tranh CPU có thể làm throughput và p99 xấu đi.
13. **“Có thể so hai JDK khác version rồi quy mọi thay đổi cho collector.”** Sai; thay đổi compiler, runtime, GC implementation và defaults cùng lúc.
14. **“JDK 25 mặc định Generational Shenandoah vì nó đã production.”** Sai theo tài liệu launcher hiện hành: cần chọn mode generational rõ ràng khi build hỗ trợ.
15. **“Tìm thấy từ Pacing trong log là đủ định lượng app latency.”** Không; cần actual delay và request traces, phương pháp đo theo JDK.
16. **“GC bean collectionTime=0 chứng minh GC không làm gì.”** Sai; độ phân giải/hợp đồng metrics không đủ.
17. **“Hai workload cấp phát cùng MiB thì phải có GC cycles giống nhau.”** Sai; retention, timing, CPU/JIT và scheduling khác.
18. **“Chỉ cần GC logs, không cần application metrics.”** Sai; SLO do ứng dụng, không phải GC log, quyết định.
19. **“Mọi dự án nên ép xảy ra OOM/Full GC để kiểm thử Shenandoah.”** Không cần; có thể phân tích các dấu hiệu bằng load có giới hạn, mô hình và fault injection trong môi trường an toàn.
20. **“Dùng nhiều cờ tuning bí truyền từ bài viết cũ sẽ tốt hơn default.”** Không có cơ sở; ưu tiên default heuristics và JDK documentation phù hợp.

## 16. Bài tập và câu trả lời

**Câu 1.** Shenandoah báo pause p99 rất ngắn nhưng HTTP p99 tăng 5 lần khi traffic burst. Có thể khẳng định không liên quan tới GC không?

**Đáp án:** **Không.** Pacing hoặc concurrent GC tranh CPU có thể tăng request latency dù STW pause nhỏ. Cần đối chiếu pacing/activity, allocation rate, heap headroom và traces.

**Câu 2.** Trong log xuất hiện Degenerated GC kèm Allocation Failure. Đây có phải dấu hiệu collector có thể đã không kịp đáp ứng tốc độ cấp phát?

**Đáp án:** **Có, là dấu hiệu mạnh** trong bối cảnh đó. Nhưng cần kiểm tra workload, cause, heap live/used, GC timing và CPU; một sự kiện đơn lẻ không tự chứng minh leak hoặc lỗi collector.

**Câu 3.** Tại sao Full GC không giải phóng nhiều bộ nhớ nếu cache vẫn giữ hàng triệu đối tượng?

**Đáp án:** GC không thu hồi objects còn reachable. Phải điều chỉnh cache eviction/TTL, bỏ references và giới hạn retention.

**Câu 4.** Heap max 512 MiB, used 430 MiB, nhu cầu 120 MiB trong 1 giây. Mô hình đơn giản báo gì?

**Đáp án:** Headroom thô = **82 MiB**, demand **120 MiB**, thiếu **38 MiB**, nên đặt cờ **pressure risk**. Đây không phải định luật dự đoán chính xác allocation failure của Shenandoah.

**Câu 5.** Hai workload cùng cấp phát 937,5 MiB payload nhưng ring giữ 8,0 và 64,0 MiB. Có thể kết luận workload giữ 64,0 MiB là một “memory leak” không?

**Đáp án:** **Không.** Đây là retention **có chủ đích** trong ví dụ; cần xem vòng đời và yêu cầu nghiệp vụ. Cùng số bytes được tạo không đồng nghĩa cùng live set hoặc GC cost.

**Câu 6.** Nhìn `GC bean: Shenandoah Pauses timeMs=0` có thể kết luận không có pause nào không?

**Đáp án:** **Không.** Metrics có độ phân giải và định nghĩa của provider; 0 ms có thể là làm tròn hoặc không phản ánh tất cả sự kiện. Xem logs/JFR cho từng pause.

**Câu 7.** Nếu `-Xmx` tăng làm giảm Degenerated GC nhưng container bắt đầu OOM kill, điều gì cần kiểm tra?

**Đáp án:** RSS/cgroup peak cùng native/off-heap, thread stacks và memory budget. Heap không được dùng hết toàn bộ hạn mức container.

**Câu 8.** Tại sao giảm số threads làm allocation có thể giúp collector bắt kịp?

**Đáp án:** Nó hạ peak allocation pressure, có thể giảm CPU contention và tăng thời gian cho concurrent phases; nhưng cũng có thể giảm throughput. Thử trong giới hạn SLO và đo đủ metrics.

**Câu 9.** Generational Shenandoah trên JDK 25 có phải được bật tự động khi dùng `-XX:+UseShenandoahGC`?

**Đáp án:** Theo tài liệu launcher JDK 25, default mode là `satb`; khi build hỗ trợ, dùng `-XX:ShenandoahGCMode=generational` để chọn generational. Chữ “product feature” không đồng nghĩa “default”.

**Câu 10.** Khi nào có thể dùng `-Xlog:gc+stats` để hỗ trợ chẩn đoán?

**Đáp án:** Khi bản JDK/build hỗ trợ các thống kê tương ứng, nó có thể cho summary về cycles, fallbacks hoặc pacing. Không coi tên/định dạng dòng output là hợp đồng ổn định xuyên tất cả phiên bản.

**Câu 11.** Có nên xem CPU throttling là nguyên nhân độc lập có thể làm collector không theo kịp không?

**Đáp án:** **Có.** Concurrent GC cần CPU. Nếu quota thấp hoặc node saturated, một cycle có thể kéo dài, tăng áp lực headroom dù allocation rate không đổi.

**Câu 12.** Chỉ một lần chạy demo `--load 120000 8192` có thể kết luận Shenandoah “không theo kịp” trên production workload không?

**Đáp án:** **Không.** Đây là workload ngắn để minh họa counters và logs, không có đủ warmup, request mix, nhiều trials hay SLO metrics. Chỉ kết luận từ đo đạc ứng dụng thật và correlation có kiểm soát.

**Tiêu chí đạt:** Bạn có thể mô tả và xác minh các dấu hiệu **pacing → allocation failure → Degenerated/Full GC** (khi tương ứng với JDK mode), phân biệt pressure với retention, đọc được log/metrics và chọn biện pháp không làm tệ đi latency, throughput hoặc footprint.

## 17. Nguồn chuẩn còn giá trị hiện nay

- [OpenJDK JEP 379 – Shenandoah: A Low-Pause-Time Garbage Collector (Production)](https://openjdk.org/jeps/379): mốc production từ Java 15.
- [OpenJDK JEP 404 – Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404): mốc phát triển generational ở JDK 24, không phải cờ khuyên dùng cho mọi phiên bản.
- [OpenJDK JEP 521 – Generational Shenandoah](https://openjdk.org/jeps/521): JDK 25 chuyển generational mode thành product feature.
- [OpenJDK Shenandoah Wiki – Shenandoah GC](https://wiki.openjdk.org/display/shenandoah/Main): khái niệm pacing, Degenerated, Full GC, heap và allocation pressure; đọc cùng tài liệu phiên bản thực tế.
- [OpenJDK JDK – java launcher manual source](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md): `-XX:+UseShenandoahGC`, `ShenandoahGCMode`, `ShenandoahGCHeuristics` và default hiện hành.
- [Red Hat OpenJDK 25 – Generational Shenandoah](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/release_notes_for_red_hat_build_of_openjdk_25.0.1/openjdk25-features): xác nhận JDK 25 cung cấp generational mode.
- [Red Hat OpenJDK 21 – Shenandoah GC Basic Configuration](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/21/html/using_shenandoah_garbage_collector_with_red_hat_build_of_openjdk_21/shenandoah-gc-basic-configuration): cú pháp `-Xlog:gc`, `-Xlog:gc+ergo`, `-Xlog:gc+stats`; kiểm tra lại trên runtime thực.
- [OpenJDK JEP 158 – Unified JVM Logging](https://openjdk.org/jeps/158): hệ thống logging với tags/levels/decorators.
- [Java SE 25 – GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): count/time và giới hạn provider.
- [Java SE 25 – MemoryMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/nonheap metrics qua MXBean.
- [Java SE 25 – MemoryUsage](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html): ý nghĩa used/committed/max.
- [Java SE 25 – java command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): JVM flags, recording và các tùy chọn runtime.
- [Java Mission Control (OpenJDK)](https://openjdk.org/projects/jmc/): công cụ phân tích JFR/GC events, allocation và CPU.
- [Java SE 25 – Java Flight Recorder API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/module-summary.html): cơ chế instrumentation còn được hỗ trợ.

**Ghi nhớ:** Dấu hiệu Shenandoah không theo kịp không phải đơn thuần “GC chạy nhiều”. Cần nhìn **allocation rate, live set, heap headroom, pacing, allocation failures, Degenerated/Full GC, CPU và request latency** cùng thời gian. Khi collector thực sự bị đẩy sát giới hạn, cách xử lý bền vững thường bắt đầu từ **giảm lượng cấp phát/retention, kiểm soát burst và cung cấp heap/CPU headroom hợp lý**, sau đó mới tuning collector theo phiên bản JDK đã chọn.