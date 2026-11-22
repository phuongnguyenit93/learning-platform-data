# Mục tiêu thu gom với thời gian dừng thấp của Shenandoah GC (Java 15+)

## 1. Shenandoah giải quyết vấn đề gì?

**Shenandoah** là garbage collector (*GC*) của HotSpot/OpenJDK, được thiết kế để **giảm thời gian ứng dụng phải dừng trong các đợt thu gom rác**. Điểm khác biệt cốt lõi là Shenandoah cố gắng thực hiện nhiều công việc nặng của GC **đồng thời (*concurrently*) với các Java application threads**, bao gồm **đánh dấu đối tượng còn sống, di chuyển đối tượng và cập nhật tham chiếu**.

Giả sử một Java service nhận yêu cầu liên tục. Khi một collector giữ tất cả application threads dừng trong thời gian dài để xử lý nhiều object trong heap, các request đang chạy cũng có thể bị trì hoãn. Shenandoah giảm phần công việc cần làm khi ứng dụng dừng, nhờ đó hướng đến **tail latency thấp và ít phụ thuộc trực tiếp vào tổng kích thước heap** hơn so với một số chiến lược thu gom dựa nhiều vào các pha STW.

Điều này **không có nghĩa**:

- Không bao giờ có **stop-the-world (STW)** pause.
- Có bảo đảm cứng rằng mọi pause **luôn dưới 1 ms hoặc 10 ms**.
- CPU, RAM và throughput sẽ miễn phí khi kích hoạt.
- Một request p99 thấp chắc chắn là do Shenandoah.
- Một ứng dụng không còn nguy cơ **Full GC, allocation failure hoặc OutOfMemoryError**.

**Mục tiêu thực tế** là giảm các khoảng dừng làm gián đoạn ứng dụng **trong khi vẫn thu hồi được rác đủ nhanh dưới tải thực**. Nếu tốc độ ứng dụng cấp phát nhanh hơn năng lực collector, hoặc heap không đủ headroom, Shenandoah có thể phải dùng các cơ chế cứu vãn gây pause dài hơn.

Bài tập trung vào **Shenandoah trong ngữ cảnh Java 15 và các JDK hiện đại**, chỉ dùng cơ chế/kiến thức còn áp dụng. Java 15 chuyển Shenandoah từ experimental thành **production feature** qua JEP 379, nhưng khả năng có sẵn vẫn **phụ thuộc bản phân phối JDK**.

## 2. Phân biệt GC pause và thời gian một chu kỳ GC

Hai từ thường xuất hiện trong GC log:

- **Pause/STW phase**: application threads phải tạm dừng ở một số thời điểm đồng bộ với JVM.
- **Concurrent phase/cycle**: GC thực hiện công việc **cùng lúc ứng dụng đang chạy**, sử dụng CPU và memory bandwidth của máy.

Giả sử GC log mô tả:

~~~text
Pause Init Mark      0.15 ms
Concurrent Marking   5.00 ms
Pause Final Mark     0.30 ms
Concurrent Evacuation ...
~~~

Đây là **ví dụ minh họa**, không phải kết quả của mọi phiên bản Shenandoah. Không thể cộng `5.00 ms` của `Concurrent Marking` rồi kết luận ứng dụng đã bị STW 5 ms trong pha đó.

**Một chu kỳ GC kéo dài 100 ms theo thời gian đồng hồ không đồng nghĩa ứng dụng bị dừng 100 ms.** Trong khi đó, một pause ngắn trong chu kỳ vẫn có thể ảnh hưởng tới request latency khi request đúng lúc phải đợi.

### 2.1. Các loại độ trễ cần theo dõi

| Chỉ số | Câu hỏi nó trả lời | Cách đo phù hợp |
| --- | --- | --- |
| **GC pause duration** | Một đợt JVM dừng ứng dụng để GC dài bao lâu? | `-Xlog:gc*,safepoint`, JFR `jdk.GCPhasePause` hoặc công cụ phân tích GC log. |
| **GC cycle duration** | Một chu kỳ concurrent GC mất bao lâu? | GC logs/JFR GC events; **không** đồng nhất với pause. |
| **Request end-to-end latency** | Người dùng đợi bao lâu từ lúc gửi đến khi nhận phản hồi? | Application tracing, server metrics, load generator đúng cách. |
| **p99 / p99.9 request latency** | Những request chậm nhất có vượt mục tiêu không? | Histogram request latency với đủ số mẫu. |
| **Throughput** | Service xử lý thành công bao nhiêu operation/giây? | Completed requests/s, batch records/s, cùng error rate. |
| **CPU và RSS** | Chi phí GC concurrent có làm ứng dụng quá tải CPU/memory không? | Process/container monitoring và native memory analysis. |

**Không thay một metric bằng metric khác.** Ví dụ, `GarbageCollectorMXBean.getCollectionTime()` không phải một histogram của STW pauses. Với collector có các pha concurrent, tổng `getCollectionTime()` hoặc thời gian của các bean khác nhau không trực tiếp bằng tổng thời gian toàn bộ application threads bị dừng.

## 3. Vì sao Shenandoah có thể giảm STW pause?

### 3.1. Mô hình heap regions và thu gom có di chuyển

Shenandoah quản lý heap theo các **regions**. Một số regions có nhiều rác có thể được chọn vào **collection set**. Những object còn sống trong các regions đó được **evacuate/relocate** tới vùng khác để thu hồi không gian và tránh phân mảnh.

Với collector thực hiện công việc di chuyển object chủ yếu trong STW phase, pause có thể tăng khi phải di chuyển lượng lớn live data. Shenandoah được thiết kế để **di chuyển object một cách concurrent**, trong khi Java threads vẫn có thể tiếp tục công việc.

Để làm điều này an toàn, JVM sử dụng những **barriers** thích hợp trên các thao tác tham chiếu và cơ chế phối hợp giữa GC threads và application threads. Một barrier là logic JVM thực hiện ở một số điểm đọc/ghi tham chiếu để bảo đảm ứng dụng luôn nhìn thấy đối tượng/tham chiếu đúng khi GC đang đánh dấu hoặc di chuyển chúng.

**Đổi lại:** barriers và concurrent work **có chi phí CPU/memory bandwidth**, nên Shenandoah không mặc nhiên có throughput tốt nhất.

### 3.2. Chu kỳ đơn thế hệ (SATB) điển hình

Cấu trúc khái quát của Shenandoah ở chế độ truyền thống `satb`:

~~~text
Application threads đang xử lý request
           |
           v
[Pause Init Mark]              <- STW ngắn để bắt đầu một số công việc
           |
           v
[Concurrent Mark]              <- mark live objects khi app chạy
           |
           v
[Pause Final Mark]             <- STW ngắn để kết thúc mark/chọn set
           |
           v
[Concurrent Evacuation]        <- move live objects khi app chạy
           |
           v
[Concurrent Update References] <- chỉnh references tới objects đã move
           |
           v
[Cleanup / hoàn tất chu kỳ]    <- một số điểm đồng bộ ngắn
           |
           v
Ứng dụng tiếp tục với heap đã thu hồi vùng rác
~~~

Đây là **sơ đồ khái niệm**, không phải danh sách chính xác của mọi pha trong mọi phiên bản: nhiều điểm đồng bộ, xử lý roots, chọn collection set, cleanup, class unloading và reference processing có thể hiện diện dưới những tên log khác nhau. Đừng dựng parser chỉ dựa vào sơ đồ này.

### 3.3. Từng nhóm pha đóng vai trò gì?

| Pha/nhóm công việc | Shenandoah làm gì? | Ảnh hưởng tới pause |
| --- | --- | --- |
| **Init Mark** | Khởi động chu kỳ đánh dấu và phối hợp với roots/thread state. | Thường có **STW pause ngắn**. |
| **Concurrent Mark** | Duyệt đồ thị tham chiếu để xác định object còn sống trong khi app chạy. | Không phải toàn bộ thời gian đó là STW, nhưng tốn CPU. |
| **Final Mark** | Hoàn tất marking và xác định regions cần thu gom. | Có thể có **STW pause ngắn**. |
| **Concurrent Evacuation** | Di chuyển live objects từ collection set sang vị trí mới trong khi app tiếp tục. | Giảm lượng object movement cần làm trong STW. |
| **Reference updating** | Đồng bộ/cập nhật các tham chiếu tới objects được dời. | Phần lớn có thể concurrent; một số bước chuyển trạng thái có thể pause. |
| **Cleanup** | Thu hồi những vùng đã sẵn sàng và chuẩn bị vòng tiếp. | Tùy pha có thể concurrent hoặc cần đồng bộ. |

Ở các JDK mới, việc xử lý stack roots và nhiều công việc liên quan đã được cải tiến; **không khẳng định mọi root scanning vẫn bắt buộc diễn ra hoàn toàn trong một pause dài như tài liệu JDK rất cũ**.

### 3.4. SATB và barriers có ý nghĩa gì?

`satb` là viết tắt của **snapshot-at-the-beginning**, một kỹ thuật hỗ trợ concurrent marking. Khi ứng dụng sửa graph tham chiếu đồng thời với GC, collector cần duy trì thông tin đủ để không bỏ sót live objects.

**Barriers** giúp GC theo dõi những cập nhật/tham chiếu quan trọng, đồng thời hỗ trợ di chuyển object. Đây là cơ chế **trong JVM**, người viết code Java thông thường không tự gọi `barrier()` để hỗ trợ Shenandoah.

Sự đánh đổi quan trọng:

- Ít thời gian phải dừng tập trung hơn.
- Nhiều công việc phân tán cùng application threads.
- Có thể tăng CPU overhead ở hot paths và tiêu thụ heap headroom.
- Khi thiếu CPU, concurrent cycle có thể chậm, ảnh hưởng throughput hoặc dẫn tới allocation pressure.

Đừng đoán hiệu năng chỉ từ thiết kế. Cần đo trên workload thật.

## 4. Không bảo đảm “pause bằng 0”: những failure modes phải biết

**Low-pause** là **mục tiêu tối ưu**, không phải hợp đồng hard real-time. Ngay cả Shenandoah cũng có những tình huống sau.

### 4.1. Cấp phát nhanh hơn GC thu hồi

Trong một dịch vụ tạo ra nhiều object tạm thời, allocation rate có thể tăng đột biến. Shenandoah vẫn phải thu gom concurrent để tạo vùng trống cho các allocation tiếp theo. Nếu không có đủ free regions hoặc CPU để hoàn thành chu kỳ đúng lúc, ứng dụng có thể gặp:

- **Allocation stall/slowdown**.
- Các chu kỳ GC được khởi động dồn dập.
- **Degenerated GC**, một cơ chế cứu vãn có thể thực hiện nhiều công việc hơn trong STW.
- **Full GC** như phương án cuối ở những tình huống nhất định.
- `OutOfMemoryError` khi không thể đáp ứng phân bổ bộ nhớ.

Không phải mọi JVM sẽ ghi đúng cùng tên sự kiện trong mọi build/mode. Hãy dùng **GC log của runtime đang chạy** để nhận diện sự kiện, không kết luận chỉ dựa vào số lượng collection beans.

### 4.2. Heap quá sát live set

Nếu **live set** (dữ liệu còn sống mà ứng dụng thực sự cần) chiếm gần hết heap, Shenandoah còn rất ít không gian để di chuyển objects và hấp thụ cấp phát mới trong khi concurrent GC vẫn đang chạy.

Ví dụ minh họa:

~~~text
Xmx = 512 MiB
live set at peak = 480 MiB
free headroom ~ 32 MiB (chưa trừ overhead khác)
allocation rate lớn + bursts
      |
      +--> concurrent GC khó theo kịp, rủi ro stalls/degeneration
~~~

Đây là **số học minh họa**, không phải phép tính chính xác free heap hay một ngưỡng tuning chuẩn. Heap còn chịu ảnh hưởng fragmentation, committed space, object layout, GC policy và các yếu tố khác.

Vì vậy, một hướng xử lý hợp lý là:

1. Đo live set sau GC và allocation rate.
2. Xem **heap headroom** ở peak load.
3. Kiểm tra có memory leak, cache growth hoặc object giữ sống quá lâu không.
4. Điều chỉnh heap và workload nếu phù hợp với memory budget.
5. Benchmark lại dưới GC logs và request latency.

Không tăng `-Xmx` tùy ý vượt **container memory limit** hoặc bỏ qua RSS, metaspace, direct memory và thread stacks.

### 4.3. CPU concurrency không miễn phí

Shenandoah dùng CPU để mark, evacuate và cập nhật references cùng thời điểm application đang chạy. Nếu container chỉ có **2 vCPU** nhưng ứng dụng đã gần 100% CPU, GC threads cạnh tranh tài nguyên có thể khiến **request latency tệ hơn**, dù thời gian STW pauses rất thấp.

Điều cần theo dõi là **end-to-end latency và throughput tại một tải xác định**, không phải chỉ một dòng log `Pause ... 0.2ms`.

### 4.4. Safepoints và những nguồn chậm khác

Không phải mọi lần Java thread bị chậm đều do GC. Application locks, database/network, thread scheduling, JIT compilation, class loading và các safepoint operations khác có thể làm response chậm.

Bởi vậy, khi thấy p99 request xấu, cần đối chiếu timestamp giữa:

- Traces/request latency.
- GC pauses và safepoints.
- CPU saturation/queue.
- Database và external dependencies.

Nếu **request p99 cao nhưng GC pauses hiếm và rất ngắn**, đổi collector chưa chắc giải quyết được nguyên nhân thực.

## 5. Java 15 và JDK hiện đại: trạng thái Shenandoah nào còn áp dụng?

Đây là phần quan trọng để tránh lấy hướng dẫn lỗi thời từ Java 12–14.

### 5.1. Shenandoah đã là production feature từ Java 15

**JEP 379** đưa Shenandoah từ experimental thành production feature trong **JDK 15**. Khi bản phân phối HotSpot có Shenandoah, cách bật cơ bản:

~~~bash
java -XX:+UseShenandoahGC -jar app.jar
~~~

**Không cần thêm `-XX:+UnlockExperimentalVMOptions` chỉ để bật Shenandoah bản production trên JDK 15+.** Các hướng dẫn buộc unlock experimental cho **toàn bộ Shenandoah** là không còn đúng với JDK hiện đại.

**Tuy nhiên:** không phải mọi JDK vendor/build đều có Shenandoah. Cần kiểm tra `java -version` và thử flag trên **đúng JDK distribution** của môi trường triển khai. Việc Java API hoặc tài liệu có tên Shenandoah không cam kết binary thực tế đã tích hợp nó.

### 5.2. Shenandoah SATB và Generational Shenandoah

Ở JDK 25, có hai lựa chọn đáng phân biệt khi build hỗ trợ:

| Mode | Ý nghĩa chính | Phạm vi áp dụng |
| --- | --- | --- |
| **`satb` / single-generation** | Một thế hệ, snapshot-at-the-beginning concurrent mark, evacuate và update references. | Mode truyền thống, dùng được trên các bản build tương thích. |
| **`generational`** | Phân biệt dữ liệu trẻ/già để khai thác giả định nhiều object chết sớm; hướng tới tối ưu throughput, heap usage và spike resilience. | Được chuẩn hóa là production feature từ **JDK 25 (JEP 521)**, khi build hỗ trợ. |

Trên **JDK 25**, cú pháp bật generational mode:

~~~bash
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -jar app.jar
~~~

Dấu `\` trong khối trên là ký tự nối dòng của shell kiểu Bash; trên PowerShell có thể nhập trên một dòng.

**Phải nhớ giới hạn theo phiên bản:**

- **JDK 15**: Shenandoah production, nhưng **không có Generational Shenandoah production theo JEP 521**.
- **JDK 24**: Generational Shenandoah được thử nghiệm theo **JEP 404**, cần `-XX:+UnlockExperimentalVMOptions` khi dùng `ShenandoahGCMode=generational`.
- **JDK 25**: JEP 521 bỏ trạng thái experimental của generational mode; có thể bật mode mà **không cần unlock experimental** trên các build phù hợp.
- Với **JDK 25**, single-generation `satb` vẫn là mode mặc định trong tài liệu/cấu hình tương ứng; generational là **opt-in**. Không suy đoán default của tất cả JDK tương lai; kiểm tra đúng phiên bản đã triển khai.
- Không áp một flag generational mà không kiểm tra `java -version`, bản build và support matrix.

**Lưu ý:** “generational” không đồng nghĩa với “GC không còn cần concurrent phases” hoặc tự động đáp ứng SLO. Hãy đo cả `satb` và `generational` trên cùng JDK phù hợp nếu muốn so sánh.

### 5.3. Đừng bỏ qua collector mặc định

G1 vẫn là collector mặc định trên phần lớn cấu hình server HotSpot. **Shenandoah không tự trở thành mặc định của Java chỉ vì JEP 379 chuyển nó sang production.**

Để chọn collector có trách nhiệm:

1. Đo G1/default làm baseline.
2. Bật Shenandoah và đo cùng workload.
3. Nếu JDK hỗ trợ, so sánh mode generational khi có mục tiêu rõ.
4. Đối chiếu kết quả request p99/p99.9, throughput, CPU, RSS, GC pause và tình huống áp lực bộ nhớ.
5. Chọn cấu hình **đáp ứng mục tiêu toàn ứng dụng**, không chỉ GC pause thấp nhất.

## 6. Mục tiêu “pause thấp” phải được chuyển thành những con số

Một ví dụ **SLO giả định** cho dịch vụ API:

| Đại lượng | Mục tiêu ví dụ | Cách hiểu |
| --- | --- | --- |
| **Request p99** | `< 50 ms` tại 10.000 requests/s | Phần lớn request phải hoàn thành trước 50 ms tại tải xác định. |
| **Request p99.9** | `< 150 ms` | Quan sát tail cực chậm, cần đủ sample. |
| **GC pause p99** | `< 5 ms` | Chỉ xét pause GC thực trong cửa sổ đo, không phải concurrent cycle. |
| **Max GC pause** | `< 25 ms` trong run được đo | Xác định rõ worst-case và test peak load. |
| **Throughput** | ≥ 10.000 successful requests/s | Không đạt nếu hệ thống chỉ hoàn thành một phần và tăng timeout. |
| **CPU** | Nằm trong quota và có headroom | Concurrent GC phải chia sẻ core với ứng dụng. |
| **Memory/RSS** | Không vượt container budget | Heap và non-heap đều tính vào giới hạn thực. |
| **Error rate** | Dưới ngưỡng nghiệp vụ | Không đạt nếu OOM, crash, timeout vượt ngân sách. |

**Các ngưỡng trong bảng chỉ là ví dụ để thực hành**, không phải thông số chuẩn hoặc bảo đảm của Shenandoah.

### 6.1. Percentile và số lượng mẫu

- **p50**: median, mô tả trường hợp điển hình.
- **p95**: đuôi chậm hơn.
- **p99**: 1% request/pause chậm nhất.
- **p99.9**: 0,1% chậm nhất, cần lượng mẫu lớn và nhiều vòng đo.

Nếu một lần benchmark chỉ tạo ra **20 GC pauses**, số đo “p99 pause” gần như bị chi phối bởi giá trị lớn nhất và khó đại diện cho distribution dài hạn. Hãy công bố **số lần GC, duration, load và run count** cùng số percentile.

**GC pause p99 ≠ request p99.** Một pause có thể ảnh hưởng nhiều request đang chờ, và request latency còn nhiều nguyên nhân khác.

### 6.2. SLO là điều kiện loại trừ, không phải khẩu hiệu

Nếu mục tiêu request p99 dưới 50 ms là **bắt buộc**, một cấu hình Shenandoah có GC pause p99 bằng 0,2 ms nhưng request p99 là 90 ms vẫn **không đạt SLO**. Nếu Parallel/G1 đạt tất cả mục tiêu với chi phí thấp hơn, không có lý do mặc định phải đổi sang Shenandoah.

Lựa chọn collector nên dựa trên **đường biên khả dụng** của:

~~~text
latency + throughput + errors + CPU + RSS + memory headroom
~~~

Không lấy một metric “đẹp” để che những metric đang vượt ngân sách.

## 7. Bật Shenandoah và ghi GC log đúng cách

### 7.1. Xác nhận JDK có hỗ trợ

Trước tiên:

~~~bash
java -version
java -XX:+UseShenandoahGC -Xlog:gc -version
~~~

Trên bản build phù hợp, GC log có thể cho biết JVM đang dùng Shenandoah, ví dụ:

~~~text
[info][gc] Using Shenandoah
~~~

Đây là **một phần log minh họa**; timestamp và tag layout phụ thuộc cấu hình log. Nếu JVM báo `Unrecognized VM option` hoặc collector không có, **đừng cố dùng flag lạ để vượt qua**. Chọn một JDK distribution có hỗ trợ hoặc dùng collector được môi trường đó cung cấp.

### 7.2. Unified logging với GC và safepoint

Ví dụ chạy ứng dụng:

~~~bash
java -Xms512m -Xmx512m \
     -XX:+UseShenandoahGC \
     -Xlog:gc*,safepoint:file=shenandoah-gc.log:time,uptime,level,tags \
     -jar app.jar
~~~

Các thành phần:

- `-XX:+UseShenandoahGC`: chọn collector.
- `-Xms512m -Xmx512m`: heap khởi đầu/tối đa bằng nhau **cho phép đo cụ thể**. Không mặc định là cấu hình tối ưu cho mọi ứng dụng.
- `-Xlog:gc*`: ghi các sự kiện GC theo tags.
- `safepoint`: ghi thêm hoạt động safepoint để đối chiếu những khoảng dừng không hoàn toàn chỉ là GC.
- `file=...`: lưu log riêng để phân tích, thay vì chỉ ghi terminal.
- `time,uptime,level,tags`: thêm thông tin thời gian và nhãn thuận tiện đối chiếu với request traces.

**Nếu chạy lâu:** cần cấu hình log rotation, retention và chi phí I/O. Thêm logging quá chi tiết vào môi trường latency nhạy cảm có thể có overhead; nên đánh giá trước.

### 7.3. Đọc đúng “Pause” và “Concurrent” trong log

Một số dòng **thực tế quan sát được** trên JDK 24/ Azul Zulu với Shenandoah:

~~~text
GC(0) Pause Init Mark (unload classes) 0.152ms
GC(0) Concurrent marking (unload classes) 0.960ms
~~~

Các giá trị này đến từ **một lần thử ngắn**, chỉ chứng minh log có các loại pha khác nhau. `0.152ms` là pause; `0.960ms` là thời gian pha concurrent, **không phải một pause khác 0.960ms**.

Khi phân tích dữ liệu đầy đủ, tìm thêm:

- Các dòng `Pause Init Mark`, `Pause Final Mark`, `Pause ...` khác.
- `Concurrent marking`, `Concurrent evacuation` và công việc concurrent khác.
- `Degenerated GC` hoặc `Pause Full` nếu xuất hiện.
- `Allocation Failure`, heap occupancy, free space, trigger/recovery.
- Các lần hoạt động của GC khi tải tăng.

Không dựa chỉ vào một dòng `Using Shenandoah` để kết luận chương trình đã đạt mục tiêu pause.

### 7.4. Java Flight Recorder

Có thể bật **Java Flight Recorder (JFR)**:

~~~bash
java -Xms512m -Xmx512m -XX:+UseShenandoahGC \
     -XX:StartFlightRecording=filename=shenandoah.jfr,settings=profile,dumponexit=true \
     -jar app.jar
~~~

Sau khi file đã ghi:

~~~bash
jfr summary shenandoah.jfr
jfr print --events jdk.GCPhasePause shenandoah.jfr
~~~

Tìm events **`jdk.GCPhasePause`** để quan sát các pause, liên kết với **`jdk.GarbageCollection`**, safepoint và những sự kiện CPU/threads/allocations khác. Không mặc định sự kiện `jdk.GarbageCollection` duration bằng thời gian ứng dụng bị dừng.

Một bản thử nghiệm JDK 24 đã tạo `sh-pass.jfr` với các event `jdk.GCPhasePause` và `jdk.GarbageCollection`, xác nhận chuỗi công cụ hoạt động. Nhưng **JFR recording vẫn có overhead**, đặc biệt `settings=profile`, nên khi benchmark có thể thử với/không bật hoặc dùng settings phù hợp để đánh giá sai lệch.

## 8. Ví dụ Java chạy được: workload cấp phát và quan sát GC

Chương trình học tập dưới đây sinh nhiều đối tượng ngắn hạn, giữ lại một số đối tượng trong vùng `retained` và lấy mẫu độ trễ **một thao tác cấp phát xử lý nhỏ**. Nó in các chỉ số để người học thử cùng file dưới nhiều collector.

**Giới hạn quan trọng:** chương trình **không** đo p99 request của một HTTP server thật; các giá trị `sampledOperationP99Ns` cũng **không phải GC pause p99**. Để đánh giá mục tiêu pause của Shenandoah, phải kết hợp **GC logs/JFR** với workload và SLO của ứng dụng thực.

### 8.1. Mã hoàn chỉnh: `ShenandoahPauseProbe.java`

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Locale;

public final class ShenandoahPauseProbe {
    private static volatile long blackhole;

    static final class Result {
        final long operations, elapsedNanos;
        final long[] samples;
        final int sampleCount;
        final long beanGcCount, beanGcMillis;

        Result(long operations, long elapsedNanos, long[] samples,
               int sampleCount, long beanGcCount, long beanGcMillis) {
            this.operations = operations;
            this.elapsedNanos = elapsedNanos;
            this.samples = samples;
            this.sampleCount = sampleCount;
            this.beanGcCount = beanGcCount;
            this.beanGcMillis = beanGcMillis;
        }
    }

    private static long mxBeanCount(boolean time) {
        long sum = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = time ? bean.getCollectionTime() : bean.getCollectionCount();
            if (value >= 0) sum += value;
        }
        return sum;
    }

    private static Result run(int durationMs, boolean sample) {
        byte[][] retained = new byte[2048][];
        long[] durations = sample ? new long[120_000] : new long[0];
        int nSamples = 0;
        long operations = 0;
        long checksum = 0;
        long beforeCount = mxBeanCount(false);
        long beforeTime = mxBeanCount(true);
        long begin = System.nanoTime();
        long deadline = begin + durationMs * 1_000_000L;

        while (System.nanoTime() < deadline) {
            boolean takeSample = sample && ((operations & 127L) == 0)
                    && nSamples < durations.length;
            long start = takeSample ? System.nanoTime() : 0L;

            byte[] data = new byte[512 + (int) (operations & 1023L)];
            data[0] = (byte) operations;
            data[data.length - 1] = (byte) (operations >>> 8);
            if ((operations & 63L) == 0) {
                retained[(int) ((operations >>> 6) & 2047L)] = data;
            }
            checksum += data[0] + data[data.length - 1];
            if (takeSample) {
                durations[nSamples++] = System.nanoTime() - start;
            }
            operations++;
        }

        long elapsed = System.nanoTime() - begin;
        blackhole = checksum;
        Arrays.sort(durations, 0, nSamples);
        return new Result(operations, elapsed, durations, nSamples,
                mxBeanCount(false) - beforeCount,
                mxBeanCount(true) - beforeTime);
    }

    private static long percentile(Result r, double fraction) {
        if (r.sampleCount == 0) return -1;
        int pos = Math.max(0, Math.min(r.sampleCount - 1,
                (int) Math.ceil(r.sampleCount * fraction) - 1));
        return r.samples[pos];
    }

    public static void main(String[] args) {
        int warmupMs = args.length > 0 ? Integer.parseInt(args[0]) : 500;
        int measurementMs = args.length > 1 ? Integer.parseInt(args[1]) : 1500;
        if (warmupMs < 100 || measurementMs < 100) {
            throw new IllegalArgumentException("Each phase must be >= 100ms");
        }

        StringBuilder names = new StringBuilder();
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (names.length() != 0) names.append(", ");
            names.append(bean.getName());
        }
        System.out.println("gcBeans=" + names);

        run(warmupMs, false);
        Result r = run(measurementMs, true);
        double opsPerSecond = 1_000_000_000.0 * r.operations / r.elapsedNanos;
        long p50 = percentile(r, .50);
        long p95 = percentile(r, .95);
        long p99 = percentile(r, .99);

        System.out.printf(Locale.ROOT, "operationsPerSecond=%.1f%n", opsPerSecond);
        System.out.println("samples=" + r.sampleCount);
        System.out.println("sampledOperationP50Ns=" + p50);
        System.out.println("sampledOperationP95Ns=" + p95);
        System.out.println("sampledOperationP99Ns=" + p99);
        System.out.println("gcBeanCountDelta=" + r.beanGcCount);
        System.out.println("gcBeanTimeDeltaMs=" + r.beanGcMillis);
        System.out.println("probeValid=" + (r.sampleCount > 0
                && opsPerSecond > 0 && p50 <= p95 && p95 <= p99));
    }
}
~~~

### 8.2. Biên dịch và chạy

Biên dịch bằng JDK 17+ có thể chọn target Java 15; dùng đúng file/class:

~~~bash
javac --release 15 -encoding UTF-8 ShenandoahPauseProbe.java
~~~

Chạy Shenandoah với **256 MiB fixed heap**:

~~~bash
java -Xms256m -Xmx256m -XX:+UseShenandoahGC \
     -Xlog:gc*,safepoint:file=shenandoah-gc.log:time,uptime,level,tags \
     ShenandoahPauseProbe 300 1100
~~~

Để có baseline G1 cùng phiên bản JDK/heap:

~~~bash
java -Xms256m -Xmx256m -XX:+UseG1GC \
     -Xlog:gc*,safepoint:file=g1-gc.log:time,uptime,level,tags \
     ShenandoahPauseProbe 300 1100
~~~

Dùng **hai file log khác nhau**, không chạy song song trên một máy bận khi muốn so sánh công bằng. Thử nhiều lần và thay đổi thứ tự chạy để giảm bias do warm-up/OS caching.

**Kết quả đã kiểm chứng trên JDK 24, Azul Zulu**, sau khi compile thành công với `--release 15`:

~~~text
gcBeans=Shenandoah Pauses, Shenandoah Cycles
operationsPerSecond=6329236.5
samples=54392
sampledOperationP50Ns=100
sampledOperationP95Ns=200
sampledOperationP99Ns=400
gcBeanCountDelta=155
gcBeanTimeDeltaMs=100
probeValid=true
~~~

Đây là **stdout chính xác từ một lần chạy cụ thể**, không phải con số sẽ lặp lại trên máy người học. Phần numeric biến động theo CPU, JIT, OS scheduler, heap và trạng thái máy.

Trong cùng phép thử, cấu hình G1 cũng trả **`probeValid=true`** và tạo GC log. JDK 24 hỗ trợ Shenandoah generational trong build được thử khi bật experimental mode, đồng thời chương trình chạy thành công. Tuy nhiên, không dùng các số liệu cực ngắn này để xếp hạng Shenandoah và G1.

### 8.3. Những gì `ShenandoahPauseProbe` thật sự đo

| Trường trong stdout | Cách tính | Giới hạn |
| --- | --- | --- |
| `gcBeans` | Tên `GarbageCollectorMXBean` ở JVM. | Bean names khác theo collector/JDK. |
| `operationsPerSecond` | Số iterations hoàn thành chia cho thời gian đo. | Không phải requests/s của service thật. |
| `samples` | Số operation latencies được lấy mẫu, tối đa 120.000. | Sampling có thể thiên lệch khi đầy buffer. |
| `sampledOperationP50Ns/P95Ns/P99Ns` | Percentile của operation duration lấy mẫu bằng `nanoTime`. | Không phải STW GC pause; timer/JIT overhead lớn ở đơn vị nanosecond. |
| `gcBeanCountDelta` | Tổng chênh lệch collection count của các MXBeans không âm. | Có thể có nhiều beans cho concurrent cycles và pauses; không suy số pause trực tiếp. |
| `gcBeanTimeDeltaMs` | Tổng chênh lệch `getCollectionTime()`. | **Không phải tổng STW pause** và có thể không so sánh được giữa collectors. |
| `probeValid` | Kiểm tra samples và tính thứ tự percentile hợp lệ. | Chỉ xác nhận phép đo hình thức, **không xác nhận đạt SLO**. |

**Để đo p99 GC pause thật**, cần trích xuất **sự kiện pause** từ `shenandoah-gc.log` hoặc JFR, không tính từ `sampledOperationP99Ns` hoặc `gcBeanTimeDeltaMs`.

## 9. Quy trình đo đúng mục tiêu low-pause trong ứng dụng thật

### 9.1. Bước 1 — Xác định workload và môi trường

Ghi lại:

- JDK vendor/version/build và OS/container image.
- CPU cores/quota, bộ nhớ tối đa của process/container.
- `-Xms`, `-Xmx`, JVM flags, GC mode.
- Allocation rate, live set, cache size, request/message sizes.
- Số thread, connection pool và downstream dependencies.
- Request arrival rate (offered load), completed throughput, errors/timeouts.

Đảm bảo các ứng viên chạy **cùng ứng dụng và input**. Nếu môi trường này dùng `satb` nhưng môi trường khác dùng `generational`, ghi rõ mode thay vì chỉ ghi chung “Shenandoah”.

### 9.2. Bước 2 — Warm-up và steady-state

Một benchmark hợp lệ nên có:

1. **Warm-up** để JIT, class loading và cache gần trạng thái ổn định.
2. **Steady-state load** ở mức mục tiêu.
3. **Burst load** cao hơn mức bình thường.
4. **Sustained high allocation** để xem GC có theo kịp hay không.
5. **Memory pressure test** có kiểm soát để tìm nguy cơ degenerated/full GC.
6. **Repeated trials** nhằm đánh giá biến động của kết quả.

Không đánh giá production dựa trên một lần thử 1–2 giây như trong ví dụ học tập.

### 9.3. Bước 3 — Cùng lúc thu thập GC và application metrics

Cần ít nhất:

- **Histogram STW pause**: p50/p95/p99/max, số lần.
- **Concurrent GC cycle time**: không đồng nhất với pause; giúp nhận diện GC chạy quá lâu.
- **End-to-end request latency**: p50/p95/p99/p99.9 theo load.
- **Success throughput và error rate**.
- **CPU utilization và throttling**, đặc biệt trong containers.
- **RSS và heap usage**, tình trạng memory headroom.
- **Degenerated/Full GC count**, allocation stalls, OOM events.

Khi phân tích, đối chiếu timestamp của GC pause với request latency spike. Nếu GC chỉ có vài pause 0,3 ms nhưng request p99 là 300 ms vì network, cần giải quyết bottleneck thực trước khi đổi GC mode.

### 9.4. Bước 4 — Đo được mục tiêu nhưng có ổn định không?

Một phép thử có p99 đẹp nhưng có vài **Full GC pause** dài hoặc OOM dưới tải tăng là dấu hiệu chưa ổn định. Cần xét:

- **Worst-case pause/max**, không chỉ p99.
- P99.9 và tail sau nhiều giờ.
- Spike lúc heap gần đầy.
- CPU quota/GC concurrency.
- Memory regression sau deploy lâu ngày.
- Kết quả sau restart/warm-up.

Trong workload cực nhạy về latency, đôi khi **một lần pause dài hiếm** đã ảnh hưởng nhiều request, ngay cả khi thống kê p99 GC pause vẫn thấp.

### 9.5. Bước 5 — Quy tắc chọn collector

Áp các ngưỡng SLO như **điều kiện loại trừ**. Nếu Shenandoah:

- Đạt request p99/p99.9 tại tải mục tiêu,
- Không vượt CPU/RSS budget,
- Không có GC fallback bất thường,
- Đáp ứng throughput và operational constraints,

thì nó là **ứng viên phù hợp**. Nếu default G1 đạt cùng các điều kiện với chi phí thấp hơn, **không bắt buộc đổi**.

## 10. Tuning Shenandoah theo nguyên nhân, không theo mẹo cũ

Một trình tự hợp lý:

### 10.1. Kiểm tra heap headroom trước

Nếu log có allocation failures/degeneration và heap gần đầy, xem:

- Live set sau GC có quá lớn so với `-Xmx` không.
- Có giữ object quá lâu do cache hoặc memory leak không.
- Allocation rate có tăng do code mới không.
- Có đủ CPU cho GC concurrent không.
- Container memory limit có cho phép tăng heap an toàn không.

Tăng heap chỉ là **một lựa chọn** và phải cân đối RSS, native memory, startup và cost. Không dùng một tỷ lệ headroom chung như “luôn phải 30%” nếu chưa có measurements.

### 10.2. Heuristics và số thread

Shenandoah có cơ chế **heuristics** quyết định khi nào kích hoạt chu kỳ GC và nên thu gom bao nhiêu. Với mode `satb`, một số bản build hỗ trợ `-XX:ShenandoahGCHeuristics=adaptive` và lựa chọn khác. **`adaptive` là lựa chọn mặc định phổ biến**, thường nên làm baseline thay vì chỉnh thủ công.

Ở Generational Shenandoah theo tài liệu JDK 25, `adaptive` là heuristics được hỗ trợ cho mode đó. **Đừng chép tùy ý `static`/`compact` từ hướng dẫn single-generation rồi áp vào generational mode**.

Có thể cấu hình CPU/GC worker count nếu cần, nhưng mỗi thay đổi phải gắn với bằng chứng từ log và đo lại latency/throughput. Điều chỉnh quá ít GC threads có thể khiến concurrent GC không theo kịp; quá nhiều có thể tranh CPU với application.

### 10.3. Không ép `System.gc()` như một công cụ tuning

`System.gc()` chỉ là yêu cầu gợi ý GC, không phải cách đo đạc hoặc “dọn rác ngay để app nhanh”. Gọi bừa bãi ở hot path có thể tăng overhead hoặc làm xấu latency. Không thêm `System.gc()` vào code production để thử “sửa” spikes.

Trong thử nghiệm benchmark, nên để collector hoạt động theo allocation pressure thực, hoặc chỉ tạo kịch bản explicit GC khi mục đích kiểm thử thật sự đòi hỏi.

### 10.4. Cấu hình ít nhất và đo lặp lại

Bắt đầu với:

~~~bash
java -Xms512m -Xmx512m -XX:+UseShenandoahGC -jar app.jar
~~~

Sau khi baseline, thay đổi **mỗi lần một giả thuyết có số đo**, ví dụ:

- Đổi heap size khi live set/headroom là nguyên nhân.
- Chọn generational mode khi runtime hỗ trợ và allocation profile gợi ý lợi ích.
- Điều chỉnh concurrency/CPU budget khi GC không theo kịp hoặc application bị CPU starvation.
- Thay đổi code/caching nếu tạo quá nhiều object hoặc giữ bộ nhớ quá lâu.

Không bật hàng chục cờ nội bộ không được kiểm chứng chỉ vì tìm thấy trong một bài hướng dẫn JVM cũ.

## 11. Shenandoah khác G1, ZGC, Parallel GC như thế nào?

| Collector | Mục tiêu chính | Điểm cần so sánh khi chọn |
| --- | --- | --- |
| **Shenandoah** | Giảm STW pause bằng concurrent mark/evacuation/reference update. | Pause tail, CPU/barrier overhead, headroom, mode, availability trên JDK build. |
| **G1** | Cân bằng throughput, footprint, pause target trên nhiều workloads; thường là HotSpot default. | Evacuation pauses, p99 response, khả năng đạt mục tiêu khi tải lớn. |
| **ZGC** | Collector concurrent hướng low-latency với các thuật toán triển khai riêng. | Pause, throughput, CPU, memory và phiên bản JDK; JDK 24+ đã generational. |
| **Parallel GC** | Ưu tiên throughput, chấp nhận STW pauses dài hơn trong nhiều workloads. | Phù hợp batch/non-latency-sensitive; cần xem tổng thời gian và p99. |

**Không có collector “tốt nhất” cho tất cả.** Cùng một ứng dụng có thể thấy Shenandoah giúp giảm GC pause nhưng tăng CPU và giảm throughput; ứng dụng khác có thể hưởng lợi rõ ràng ở p99 request.

Từ góc nhìn thiết kế, **Shenandoah không đơn giản là “G1 có pause target thấp hơn”**. Nó sử dụng cơ chế concurrent movement/update references để giảm những phần việc nặng trong STW. Nhưng low-pause và high-throughput luôn có trade-off phải đo.

### 11.1. Giữ Java version cố định khi benchmark

Không nên so sánh:

~~~text
G1 trên JDK 17
Shenandoah SATB trên JDK 21
Shenandoah generational trên JDK 25
~~~

rồi kết luận hiệu năng khác nhau **chỉ do collector**. JIT, class library, scheduler, code generation và GC implementation đều có thể thay đổi.

Để so sánh collector, trước tiên dùng **cùng JDK build/hardware/workload**, chỉ đổi collector/mode và ghi tất cả flags. Nếu muốn đo tác động của nâng JDK, tạo thí nghiệm riêng với phiên bản JDK là biến có kiểm soát.

## 12. Câu hỏi và lỗi thường gặp

| Nhận định sai | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Shenandoah không có STW.” | Vẫn có những pha đồng bộ và có thể fallback. | Shenandoah **giảm** STW, không loại bỏ mọi pause. |
| “Concurrent cycle mất 50 ms nên Java threads dừng 50 ms.” | Concurrent chạy cùng application. | Đọc các sự kiện **Pause** riêng. |
| “Pause log 0,2 ms nghĩa p99 request luôn 0,2 ms.” | Request latency còn queue, DB, CPU, network. | Đo end-to-end p99 và correlation. |
| “Heap lớn thì pause bắt buộc tăng tuyến tính.” | Shenandoah chuyển nhiều công việc sang concurrent. | Không suy tuyến tính, vẫn phải đo roots, threads và fallback. |
| “`-XX:+UseShenandoahGC` luôn chạy trên mọi JDK.” | Vendor/build có thể không tích hợp Shenandoah. | Kiểm tra binary thực tế. |
| “Shenandoah Java 15 vẫn là experimental.” | JEP 379 đã đưa lên production. | Không dùng unlock experimental chỉ để bật collector. |
| “Generational Shenandoah đã là production ở Java 15.” | JEP 521 đưa mode này thành product feature ở JDK 25. | Chọn cấu hình theo JDK version. |
| “Ở JDK 24 generational dùng giống JDK 25.” | JDK 24 còn experimental. | Nếu thử JDK 24 phải dùng unlock experimental và coi là thí nghiệm version-specific. |
| “`getCollectionTime()` là tổng STW.” | Bean có thể phản ánh concurrent cycles. | Dùng GC log hoặc JFR pause events. |
| “Shenandoah pause ngắn => không thể Full GC/OOM.” | Khi heap/CPU thiếu có thể degenerate/fallback. | Theo dõi allocation pressure và log errors. |
| “Chỉ xem `-Xmx` là đủ cho container.” | RSS còn metaspace, stacks, native buffers. | Đo memory thực và headroom. |
| “p99 không đổi nên GC không gây ảnh hưởng.” | Có thể thay đổi p99.9 hoặc max spike. | Đo nhiều percentile và worst cases. |
| “Tăng `-Xmx` luôn giảm pause.” | Có thể tăng footprint/cost và không giải quyết leak/CPU. | Dựa vào live set/allocations/pressure. |
| “Shenandoah luôn cho throughput cao hơn G1.” | Concurrent barriers/cycles tiêu thụ CPU. | Đo throughput tại load mục tiêu. |
| “Dùng một toy benchmark 1 giây để chọn production GC.” | Quá ngắn, JIT/OS noise và không đo request SLO. | Benchmark app thật, warm-up, lặp và nhiều profile tải. |

## 13. Bài tập tự kiểm tra

**Câu 1.** Vì sao Shenandoah hướng tới pause thấp hơn dù vẫn phải dọn rất nhiều objects?

**Trả lời:** Nó chuyển nhiều công việc mark, evacuation và update references sang concurrent phases thay vì làm hết trong thời gian dừng ứng dụng. Các barriers và đồng bộ JVM giúp ứng dụng vẫn chạy đúng khi objects được di chuyển.

**Câu 2.** Một GC log ghi `Pause Init Mark 0.2ms` và `Concurrent Marking 40ms`. JVM có bị dừng 40.2ms không?

**Trả lời:** Không được kết luận như vậy. `Concurrent Marking` chạy đồng thời với application threads; tổng STW phải tính riêng từ các pause events thực tế.

**Câu 3.** Shenandoah có loại bỏ mọi khả năng `Full GC` và `OutOfMemoryError` không?

**Trả lời:** Không. Nếu allocation pressure lớn, live set quá cao so với heap hoặc GC không theo kịp, JVM có thể gặp stalls, degenerated/full GC hoặc OOM.

**Câu 4.** Có được dùng `-XX:+UnlockExperimentalVMOptions` như yêu cầu bắt buộc để bật Shenandoah trên Java 15 không?

**Trả lời:** Không. Shenandoah được chuyển thành production feature ở JDK 15. **Riêng Generational Shenandoah** trên JDK 24 là experimental và cần unlock khi thử; trên JDK 25 mode này là production feature theo JEP 521.

**Câu 5.** Nếu GC pause p99 chỉ 1 ms nhưng request p99 180 ms, có thể kết luận service đã đạt SLO 50 ms không?

**Trả lời:** Không. SLO request tính end-to-end; phải xem các bottlenecks khác và request traces, không dùng GC pause thay thế.

**Câu 6.** Hai metrics `sampledOperationP99Ns` và `gcBeanTimeDeltaMs` trong ví dụ có đo GC pause p99 không?

**Trả lời:** Không. Một cái đo thời gian thao tác code được lấy mẫu; cái kia là thống kê thô từ MXBeans. GC pause p99 cần được lấy từ GC logs/JFR pause events.

**Câu 7.** Tại sao một dịch vụ có 2 vCPU có thể phản hồi chậm hơn với Shenandoah dù GC pauses thấp?

**Trả lời:** Concurrent GC threads và barriers dùng CPU chung với ứng dụng; nếu CPU quota đã căng, app có thể bị tranh CPU, chậm tiến độ xử lý.

**Câu 8.** Khi nào nên cân nhắc Generational Shenandoah?

**Trả lời:** Khi JDK distribution/version hỗ trợ (JDK 25+ theo JEP 521) và workload có allocation profile khiến phân chia objects trẻ/già có triển vọng. Phải đo cùng baseline và kiểm tra các SLO, không chỉ bật vì nó mới.

## 14. Ghi nhớ

- **Shenandoah nhắm đến GC pauses thấp** bằng cách chuyển **mark, evacuation và reference updates** sang các pha concurrent với ứng dụng.
- **Low-pause không có nghĩa zero-pause hay hard real-time.** Vẫn có STW ngắn và các failure modes như degenerated/full GC, OOM dưới áp lực.
- **Pause duration khác concurrent cycle duration**; không cộng toàn bộ chu kỳ vào thời gian ứng dụng bị dừng.
- **Heap headroom và CPU quota cực kỳ quan trọng**: concurrent GC cần tài nguyên để theo kịp tốc độ cấp phát.
- **JDK 15** đưa Shenandoah thành **production feature** (JEP 379), nhưng sự hiện diện phụ thuộc JDK vendor/build.
- **JDK 25** chuẩn hóa **Generational Shenandoah** (JEP 521); JDK 24 generational từng là experimental, tránh copy flag cũ mù quáng.
- **Đo GC pause bằng GC logs/JFR**, đo request p99/p99.9 bằng telemetry của ứng dụng; kết hợp throughput, CPU, RSS và errors.
- **Không chọn collector chỉ dựa vào một phép thử nhỏ**. Benchmark workload thật, so sánh dưới cùng điều kiện, thử spike và xác định quy tắc SLO trước khi rollout.

### Tài liệu đáng tin cậy và còn áp dụng

- [OpenJDK JEP 379 – Shenandoah: A Low-Pause-Time Garbage Collector (Production)](https://openjdk.org/jeps/379): Shenandoah chuyển thành product feature ở Java 15.
- [OpenJDK JEP 521 – Generational Shenandoah](https://openjdk.org/jeps/521): JDK 25 đưa generational mode thành product feature.
- [OpenJDK JEP 404 – Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404): ngữ cảnh JDK 24 và lý do thay đổi.
- [OpenJDK Shenandoah Project Wiki](https://wiki.openjdk.org/display/shenandoah/Main): thiết kế concurrent mark/evacuation/update references, tuning và availability.
- [OpenJDK mainline Java Launcher Options](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md): `UseShenandoahGC`, `ShenandoahGCMode` và heuristics theo bản source.
- [Inside Java – The Arrival of Java 15](https://inside.java/2020/09/15/the-arrival-of-java-15/): Shenandoah production trong Java 15, G1 vẫn mặc định.
- [Red Hat – A beginner's guide to the Shenandoah garbage collector](https://developers.redhat.com/articles/2024/05/28/beginners-guide-shenandoah-garbage-collector): phases, design và trade-offs.
- [Red Hat OpenJDK 25 Release Notes – Generational Shenandoah](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/release_notes_for_red_hat_build_of_openjdk_25.0.1/openjdk25-features): mode generational ở JDK 25.
- [Oracle Java 25 – Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html): mục tiêu và cách đo hiệu năng GC/latency trên HotSpot.
