# Java 10 – G1 Full GC song song: Vai trò của số luồng GC và tài nguyên CPU được cấp

> **Phạm vi:** Java 10 → **G1 Full GC song song** → **Vai trò của số luồng GC và tài nguyên CPU được cấp**. **JEP 307** (Java 10) song song hóa con đường **Full GC dự phòng** của G1, nhưng hiệu quả phụ thuộc CPU thật sự được cấp, số GC workers, lượng dữ liệu sống và tình trạng cấp phát heap. Bài trình bày các quy tắc còn áp dụng trên **JDK 17+ và các JDK hiện đại**, tránh mẹo/cờ logging đã lỗi thời; chương trình cuối bài đã được biên dịch và chạy trên HotSpot JDK hiện có.

## 1. Mục tiêu học tập

Kết thúc bài, bạn có thể:

1. Giải thích vì sao G1 cố gắng tránh Full GC và **JEP 307** đã thay đổi điều gì từ Java 10.
2. Hiểu **Full GC vẫn là stop-the-world** dù bên trong nó có nhiều worker hoạt động song song.
3. Phân biệt ba tập công việc: **STW parallel GC**, **concurrent marking** và **concurrent refinement**.
4. Biết vai trò của `-XX:ParallelGCThreads=N` và `-XX:ConcGCThreads=N`, không nhầm với `-XX:ActiveProcessorCount=N`.
5. Phân biệt **CPU host**, **CPU khả dụng với tiến trình**, **quota/cpuset container**, **CPU thực được scheduler cấp** và **logical processors**.
6. Hiểu vì sao số GC worker tối đa **không đồng nghĩa** số core chuyên dụng, số worker thực đang chạy hoặc số lần tăng tốc.
7. Nhận ra tình trạng **oversubscription**, CPU throttling và diminishing returns khi đặt quá nhiều worker.
8. Hiểu tác động của tăng/giảm worker đến **pause time, throughput, CPU consumption, marking progress và tail latency**.
9. Biết JVM tự chọn các giá trị mặc định theo tài nguyên/heap và vì sao nên **đo trước khi chỉnh**.
10. Bật `-Xlog:gc*=info`, phân tích `Pause Full` và `Using N workers of M for full compaction` trên HotSpot.
11. Viết và chạy ví dụ Java 17+ với 2 CPU được JVM nhận diện, 2 STW workers và 1 concurrent marking worker.
12. Hiểu vì sao `System.gc()` chỉ nên dùng làm **kịch bản kiểm thử có kiểm soát**, không phải phương án xử lý thiếu heap trong production.
13. Đọc log để tìm nguyên nhân Full GC thực: allocation failure, evacuation failure, humongous object, exhausted heap hay explicit request.
14. Tổ chức thí nghiệm A/B công bằng trong Kubernetes, VM hoặc máy vật lý với CPU/memory limits giống nhau.
15. Xây dựng chính sách tuning thận trọng, tránh sửa các cờ GC dựa vào một benchmark nhỏ.

**Kết luận một câu:** `ParallelGCThreads` quyết định **giới hạn worker cho công việc GC dừng ứng dụng**, còn **CPU thực được scheduler cấp** quyết định bao nhiêu công việc có thể tiến triển đồng thời. Tăng worker có thể rút ngắn G1 Full GC nhưng **không tạo CPU mới, không làm Full GC thành concurrent và không giải quyết nguyên nhân thiếu bộ nhớ**.

## 2. JEP 307 của Java 10 thay đổi điều gì?

G1 (Garbage-First) chia Java heap thành **regions** và cố gắng thu hồi bộ nhớ theo các đợt ngắn hơn, nhiều công đoạn diễn ra concurrent với ứng dụng. Tuy nhiên, nếu không thể thu hồi đủ nhanh hoặc không thể hoàn thành evacuation trong điều kiện bộ nhớ hiện có, JVM có thể phải thực hiện **Full GC dự phòng**, một thao tác tốn kém.

Trước Java 10, fallback Full GC trong G1 dùng thuật toán **mark-sweep-compact đơn luồng**. **JEP 307 – Parallel Full GC for G1**, được đưa vào **JDK 10**, song song hóa thuật toán này nhằm cải thiện **worst-case latency**.

So sánh khái niệm:

~~~text
G1 trước thay đổi của JEP 307:
  Mutators tạm dừng
  [ 1 GC worker đánh dấu / dọn / compact toàn heap ]
  Mutators tiếp tục

G1 từ JDK 10:
  Mutators tạm dừng
  [Worker 1] [Worker 2] ... [Worker N]
       cùng thực hiện các pha Full GC có thể song song
  Đồng bộ, xử lý phần còn lại, kết thúc pause
  Mutators tiếp tục
~~~

Sơ đồ chỉ diễn đạt **mức độ song song**; không khẳng định mọi subphase chạy đồng thời hoặc chia đều workload hoàn hảo. Một số việc vẫn tuần tự hoặc phải chờ barrier. Chính điều đó giải thích tại sao **N workers không mang lại tốc độ N lần**.

### 2.1. Ba điều cần nhớ từ chính mục tiêu JEP

- **Mục tiêu:** giảm thời gian tạm dừng tệ nhất nếu G1 buộc phải dùng Full GC.
- **Không phải mục tiêu:** làm tất cả Full GC biến mất; cũng không cam kết G1 Full GC luôn nhanh bằng Parallel GC collector trong mọi workload.
- **Phạm vi thread control:** `-XX:ParallelGCThreads` điều khiển tập parallel workers được G1 dùng cho Full GC và **các pause Young/Mixed**, không phải một setting chỉ dành riêng cho Full GC.

Oracle JDK 10 Release Notes và JEP 307 đều ghi nhận thay đổi này. Trên JDK hiện đại, G1 vẫn sử dụng các worker cho GC pauses và song song hóa Full GC; ta không cần cờ cũ đặc biệt để “bật JEP 307”.

## 3. Phân biệt Full GC, Young/Mixed GC và concurrent marking

Nhiều vấn đề tuning xuất phát từ việc gộp mọi GC thành một loại duy nhất.

| Loại công việc | Ứng dụng có bị dừng? | Mục đích chính | Loại luồng liên quan |
| --- | --- | --- | --- |
| **Young GC pause** | Có, STW | Di chuyển object trong collection set young | Parallel GC workers |
| **Mixed GC pause** | Có, STW | Thu young + một phần old regions sau marking | Parallel GC workers |
| **Concurrent marking** | Chủ yếu chạy cùng ứng dụng | Đánh giá khả năng sống của object để G1 chọn old regions | Concurrent marking workers |
| **Concurrent refinement** | Có thể chạy cùng ứng dụng | Xử lý remembered-set/card refinement | Refinement threads, cơ chế riêng |
| **Full GC fallback** | **Có, STW toàn ứng dụng** | Thu hồi/compact diện rộng khi đường thường không đủ | Parallel workers của G1 Full GC |

Bảng là mô hình tổng quát: G1 còn có các pha ngắn như Remark/Cleanup hoặc các hoạt động phụ, nên “concurrent marking” không có nghĩa mọi phần trong chu kỳ marking đều không dừng ứng dụng.

### 3.1. “Parallel” không có nghĩa “Concurrent”

- **Parallel:** nhiều GC workers cùng tiến hành công việc GC; trong Full GC, **application threads đã dừng**.
- **Concurrent:** công việc GC tiến hành **cùng lúc với application threads**, cùng cạnh tranh CPU.
- **Stop-the-world (STW):** các Java mutator threads tạm dừng ở safepoint thích hợp, dù JVM vẫn có thể dùng nhiều native GC workers.

Một Full GC gồm 8 workers vẫn là **Full GC STW**. Khi nó kéo dài 2 giây, application vẫn chịu một pause khoảng đó; 8 workers không biến thành 8 background threads để ứng dụng tiếp tục phục vụ request.

### 3.2. Parallel Full GC không làm G1 trở thành Parallel GC collector

`-XX:+UseG1GC` chọn **G1**. `-XX:+UseParallelGC` chọn **Parallel collector**, vốn là một collector khác với thuật toán/mục tiêu khác. Tên “G1 Full GC song song” chỉ mô tả đường Full GC của **G1**.

Tương tự, `ZGC`/`Shenandoah` có mô hình thu gom khác. Không dùng kết quả cờ/tham số của G1 để suy diễn đúng cho các collector khác; mỗi collector có ergonomics và cấu hình riêng.

## 4. Ba nhóm số luồng cần phân biệt

### 4.1. `-XX:ParallelGCThreads=N`

Theo Java launcher và tài liệu G1 hiện hành, đây là số **parallel GC worker threads tối đa/được cấu hình** cho công việc tại các GC pauses. G1 có thể **sử dụng ít worker hơn mức tối đa** tùy lượng công việc, heap size và ergonomics.

Ví dụ:

~~~bash
java -XX:+UseG1GC -XX:ParallelGCThreads=2 -jar service.jar
~~~

Với JEP 307, con đường Full GC sử dụng các worker parallel được cấu hình theo cơ chế này. Nhưng cùng cờ `ParallelGCThreads` cũng có thể ảnh hưởng pause Young/Mixed, reference processing và các GC tasks liên quan theo implementation.

**Không có một cờ “chỉ đặt thread riêng cho G1 Full GC” phổ thông tách biệt hoàn toàn khỏi Young/Mixed GC.** Nếu giảm `ParallelGCThreads` để tránh CPU throttling của Full GC, hãy đo lại pause thường ngày, vì Young/Mixed cũng có thể chậm hơn.

### 4.2. `-XX:ConcGCThreads=N`

Ví dụ:

~~~bash
java -XX:+UseG1GC -XX:ConcGCThreads=1 -jar service.jar
~~~

Cờ này giới hạn số threads cho **concurrent GC work**, đặc biệt concurrent marking; những công việc này diễn ra khi ứng dụng còn hoạt động, nên có thể **cạnh tranh CPU với request threads**. Default thường liên quan đến `ParallelGCThreads`, được tài liệu hiện hành mô tả xấp xỉ **một phần tư** của số parallel GC threads; con số thực phụ thuộc ergonomics, JVM và cấu hình.

**Sai lầm phổ biến:** đặt `ConcGCThreads=8` và kết luận Full GC chắc chắn dùng 8 workers. Full GC dùng nhóm **parallel STW GC workers**; không thể suy “threads Full GC” từ `ConcGCThreads`.

### 4.3. Concurrent refinement có thể có tuning riêng

G1 còn xử lý các remembered sets/cards khi ứng dụng đang chạy. Những hoạt động này có thể dùng **concurrent refinement threads**, chịu chi phối của cơ chế/tùy chọn khác (ví dụ `-XX:G1ConcRefinementThreads` trên JDK có hỗ trợ).

Vì vậy không thể nói “mọi thread concurrent của G1 đều bằng `ConcGCThreads`”. Cần đọc đúng log/tag và tài liệu JDK target trước khi thay các cờ nâng cao.

### 4.4. `-XX:ActiveProcessorCount=N` không phải số GC threads

Ví dụ:

~~~bash
java -XX:ActiveProcessorCount=2 -XX:+UseG1GC -jar service.jar
~~~

Cờ này **ghi đè số processor mà JVM dùng để tính một số ergonomic defaults**, trong đó có GC và một số thread pools. Nó cũng ảnh hưởng kết quả `Runtime.getRuntime().availableProcessors()` trong ví dụ HotSpot.

Nó **không**:

- Cấp thêm CPU vật lý;
- Đảm bảo container sở hữu riêng N cores;
- Thay đổi CPU quota/cpuset do hệ điều hành hoặc Kubernetes áp;
- Biến `ParallelGCThreads` đang đặt tường minh thành đúng N;
- Chặn các thread khác của ứng dụng/JIT/native code;
- Bảo đảm Full GC dùng N workers trong mọi pause.

**Sơ đồ phụ thuộc:**

~~~text
Tài nguyên CPU thật / quota / cpuset
        |
        v
JVM nhận diện số processor
        |  (có thể override bằng -XX:ActiveProcessorCount)
        v
Ergonomics chọn GC workers mặc định
        |  (hoặc user override ParallelGCThreads/ConcGCThreads)
        v
GC workers tối đa được cấu hình
        |
        v
GC task chọn workers thực sự cho mỗi pause
        |
        v
OS scheduler cấp CPU trong điều kiện tranh chấp/throttling
        |
        v
Pause wall-clock + tổng CPU time + application latency
~~~

Không đảo chiều mũi tên cuối: **số thread được cấu hình không sinh ra quyền sử dụng CPU thật**.

## 5. JVM tính mặc định `ParallelGCThreads` thế nào?

JDK hiện đại thường chọn số worker theo **số CPU khả dụng với tiến trình**, giới hạn bởi các heuristics của collector và kích thước heap.

Trong Oracle G1 GC Tuning Guide hiện hành:

- Nếu số CPU threads JVM nhìn thấy **không quá 8**, giá trị heuristic ban đầu của `ParallelGCThreads` thường dựa trực tiếp trên số đó.
- Nếu CPU threads **lớn hơn 8**, giá trị được tính bằng cách tăng thêm một phần số threads vượt ngưỡng (tài liệu mô tả hệ số khoảng **5/8 cho phần vượt 8**).
- Trước mỗi pause, số workers được sử dụng còn có thể bị **giới hạn theo heap capacity**: không vượt quá mức phù hợp với `HeapSizePerGCThread` và các yếu tố ergonomics khác.
- `ConcGCThreads` mặc định thường xấp xỉ `ParallelGCThreads / 4`, theo mô tả của tài liệu hiện hành.

Đây là **mô tả heuristic của tài liệu**, không phải API bất biến bạn nên sao chép để dự đoán một con số chính xác trên mọi JVM/JDK/GC phase. Khi cần biết giá trị thực, **xem các flags/log của JVM đang chạy**.

### 5.1. Giá trị cấu hình ≠ worker thực trong một pause

Trong log minh họa:

~~~text
[info][gc,init] Parallel Workers: 2
[info][gc,task] GC(0) Using 2 workers of 2 for full compaction
~~~

Dòng đầu cho biết mức worker configured/initialized; dòng thứ hai xác nhận **số worker được dùng trong một Full GC cụ thể**. Với một heap nhỏ hơn hoặc các pha khác, JVM có thể chọn ít worker hơn mức cấu hình.

**Không nên suy** từ `-XX:ParallelGCThreads=8` rằng mọi Full GC luôn có 8 cores xử lý đồng thời hoặc tất cả tám GC workers đều bận như nhau.

### 5.2. G1 thường không cần tuning thủ công ngay từ đầu

Oracle GC tuning guide nhấn mạnh G1 được thiết kế cân bằng latency/throughput theo heuristics. Khi không có bằng chứng CPU allocation/GC bottleneck, giữ default thường là một **baseline hợp lý**. Chỉ chỉnh nếu có số liệu cho thấy CPU nhận diện sai, CPU throttling, pause bị kéo dài do thiếu worker hoặc overhead do quá nhiều worker.

Việc cố định quá nhiều flags làm giảm khả năng JVM tự điều chỉnh khi heap/CPU hoặc runtime version thay đổi.

## 6. CPU host khác CPU mà JVM thực sự sử dụng được

Các môi trường triển khai khác nhau có thể khiến số CPU vật lý và CPU “nhìn thấy” không giống nhau.

| Tầng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| CPU host | Máy có 32 logical CPUs | Tổng năng lực của máy; chưa nói ứng dụng dùng được bao nhiêu |
| Affinity / cpuset | Process chỉ được chạy trên 4 logical CPUs | Giới hạn những CPU scheduler được phép sử dụng |
| Container CPU quota | Pod được cấp trung bình 2 CPU | Giới hạn tổng CPU time trong chu kỳ quota; có thể bị throttling |
| Kubernetes CPU request | Pod request 2 CPU | Tín hiệu scheduling/đảm bảo tương đối, không đồng nghĩa hard limit |
| Kubernetes CPU limit | Pod bị giới hạn CPU ở mức cấu hình | Cgroup quota/throttling tùy node/OS |
| JVM processor count | `availableProcessors()` trả 2 | Số CPU mà JVM dùng trong ergonomics; không phải giấy phép “dùng 2 core độc quyền” |
| GC workers cấu hình | `ParallelGCThreads=2` | Upper/configured bound cho STW GC tasks |
| GC workers thực dùng | `Using 2 workers of 2` | Thực tế một pha GC |
| CPU time thực cấp | Cgroup usage/throttling, process CPU | Bao nhiêu CPU đã được scheduler cho chạy |

### 6.1. Container awareness của HotSpot

HotSpot hiện đại có hỗ trợ **đọc thông tin container/cgroup** khi tính memory/CPU ergonomics. Tuy nhiên, hành vi cụ thể còn phụ thuộc JDK build, OS, cgroup version, cpuset/quota và cách triển khai.

Không nên mặc định “container có CPU limit=2 thì `availableProcessors()` chắc chắn luôn đúng 2 trên mọi Java version, mọi cgroup”. Hãy kiểm bằng:

~~~bash
java -XX:+UseG1GC -XshowSettings:system -version
java -XX:+UseG1GC -Xlog:os+container=info -version
~~~

Những lệnh trên là **kiểm tra tùy runtime**: một số thông tin/tag có thể khác hoặc không hỗ trợ trên một OS/JDK cụ thể. Trên Linux có thể kiểm cgroup CPU quota/cpuset và metrics CPU throttling từ môi trường chạy. Với Java source, dùng `Runtime.getRuntime().availableProcessors()` để xem JVM đang báo bao nhiêu.

### 6.2. `ActiveProcessorCount` thay nhận diện, không thay quota

Nếu host có 32 CPUs nhưng workload bị giới hạn 2 CPU:

~~~bash
java -XX:+UseG1GC -XX:ActiveProcessorCount=2 -jar service.jar
~~~

Cấu hình này giúp JVM tính một số default thread pools như thể có 2 CPUs. Nhưng nếu cgroup thực chỉ cho 1 CPU, chương trình vẫn có thể **bị throttled dù JVM tin có 2**. Ngược lại, nếu process có 8 cores thật mà bạn đặt count=1, một số heuristics sẽ giả định tài nguyên ít hơn, có thể giảm khả năng song song.

Vì vậy giá trị `ActiveProcessorCount` nên **phản ánh đúng ngân sách CPU dành cho ứng dụng**, không phải một cách ép tăng tốc Full GC.

### 6.3. CPU request không thay thế CPU limit

Trong Kubernetes, request ảnh hưởng cách scheduler đặt pod và cách chia sẻ tài nguyên theo cấu hình, còn limit thường được thực thi bằng quota. Một pod có request cao nhưng limit thấp vẫn có thể gặp throttling. Nếu không đặt limit, có thể tận dụng CPU rảnh của node nhưng cũng chịu tranh chấp với các workloads khác.

Luôn ghi lại cả **requests, limits, cpuset, CPU usage, throttling và node contention** khi benchmark G1. Không dùng riêng `kubectl top` tại một thời điểm để kết luận “có đủ CPU”.

## 7. Tại sao nhiều worker không tự làm Full GC nhanh hơn?

Tổng thời gian Full GC có thể phân tích thành các nhóm chi phí:

~~~text
T_full_pause ≈ T_setup
             + T_parallel_work_effective(N, CPU)
             + T_sync_and_sequential
             + T_scheduling_and_memory_stalls
             + T_finalize
~~~

Đây là **mô hình minh họa**, không phải công thức chính xác của HotSpot. Trong đó:

- `T_parallel_work_effective` có thể giảm khi có thêm workers và CPU sẵn có.
- `T_sync_and_sequential` không biến mất khi tăng N.
- `T_scheduling_and_memory_stalls` có thể **tăng** khi quá nhiều worker tranh CPU/cache/memory bandwidth.
- `T_setup`/`T_finalize` còn có overhead cố định.

### 7.1. Amdahl's law như một mô hình trực giác

Giả sử **80% công việc có thể song song hoàn hảo**, **20% còn lại tuần tự**, và không tính chi phí đồng bộ. Với N=4:

~~~text
Speedup lý tưởng tối đa = 1 / (0.20 + 0.80/4)
                       = 1 / 0.40
                       = 2.5 lần
~~~

Đây là **ví dụ toán học giả định**, không phải số đo của G1. Trong thực tế, speedup còn thấp hơn nếu memory bandwidth, work imbalance, cgroup quota hoặc pause synchronization trở thành bottleneck.

### 7.2. Khi tăng worker có thể hữu ích

- Full GC phải xử lý nhiều dữ liệu sống, có đủ công việc song song.
- JVM thật sự được phép dùng thêm CPU cores.
- CPU không bị throttling hay tranh chấp nghiêm trọng.
- Kết quả log cho thấy Full GC có dùng mức workers mới và wall time giảm.
- Độ trễ những pauses khác không xấu đi đáng kể.
- Memory bandwidth/cache/NUMA vẫn còn dư địa.

### 7.3. Khi tăng worker có thể phản tác dụng

- Container chỉ có quota 1 CPU nhưng cấu hình `ParallelGCThreads=16`.
- Nhiều JVM cùng tranh cùng vài physical cores.
- Heap nhỏ và G1 đã giới hạn workers theo quy mô heap.
- Nhiều nhiệm vụ rất nhỏ làm scheduling/synchronization overhead tăng.
- CPU throttling làm pause **wall-clock** dài dù tổng GC CPU time không giảm.
- Đường GC bị giới hạn bởi memory bandwidth hoặc khối lượng phần tuần tự.

**Không có định luật “gấp đôi workers → Full GC nhanh gấp đôi”.**

## 8. CPU throttling trong container có thể kéo dài STW pause

Giả sử một pod bị giới hạn CPU quota tương đương **2 cores**, nhưng một bản cấu hình ép tối đa **8 parallel GC threads**. Khi Full GC xảy ra, JVM có thể tạo nhiều GC workers runnable cùng lúc; hệ điều hành chỉ cấp tổng CPU time theo quota. Nếu các workers dùng hết quota sớm, cgroup có thể bị **throttled cho đến chu kỳ tiếp theo**.

Hệ quả:

- GC pause đo theo **thời gian thực** có thể tăng.
- Application đã STW, nên request latency vẫn bị kéo dài.
- CPU time cộng dồn của nhiều GC threads có thể cao nhưng không quy đổi thành thời gian thực nhanh tương ứng.
- Cùng cấu hình chạy trên host không limit có thể khác nhiều so với pod có quota.
- Đổi số worker mà không ghi nhận throttling/CPU quota sẽ gây kết luận sai.

### 8.1. CPU time và wall-clock time là hai đại lượng khác

~~~text
CPU time GC workers (cộng từ các luồng) = tổng thời gian CPU đã chạy.
Wall-clock pause                          = thời gian người dùng thực sự chờ.
~~~

Hai luồng cùng chạy mỗi luồng 100 ms có thể tiêu thụ tổng cộng khoảng 200 ms CPU nhưng wall-clock chỉ khoảng 100 ms nếu có 2 cores thật sự. Nếu chỉ 1 core khả dụng, thời gian thực có thể tiến gần tổng CPU time, chưa tính scheduling overhead. Đây là ví dụ lý tưởng hóa; trong JVM thực còn các pha tuần tự và đồng bộ.

### 8.2. Đặt worker theo đúng CPU budget

Khi phát hiện oversubscription, một lộ trình có thể là:

1. Kiểm JVM nhìn thấy bao nhiêu CPU.
2. Kiểm container CPU quota/request/cpuset.
3. Kiểm parallel/concurrent GC worker flags và log số worker thực.
4. Giữ heap/GC configuration ổn định, chạy A/B với số worker vừa CPU budget.
5. Theo dõi Full GC **p95/p99**, Young/Mixed pauses, throughput, CPU throttling và heap occupancy.
6. Nếu vấn đề chủ yếu do **Full GC liên tục**, tìm nguyên nhân thiếu bộ nhớ/cấp phát thay vì chỉ giảm workers.

**Không đưa ra một “công thức N=quota CPU” áp dụng tuyệt đối:** GC có thể chọn ít workers hơn N và hiệu quả phụ thuộc workload.

## 9. `ConcGCThreads` và chi phí CPU khi ứng dụng vẫn chạy

Full GC STW là câu chuyện khác với **concurrent marking** của G1.

Concurrent marking dùng CPU khi application đang tiếp tục cấp phát object và phục vụ request. Nếu cấp quá ít `ConcGCThreads`:

- Marking có thể tiến triển chậm, đặc biệt với allocation rate cao.
- G1 có thể không xác định và thu hồi được các vùng old đủ sớm.
- Áp lực heap/free regions có thể tăng, góp phần dẫn tới evacuation/Full GC trong tình huống xấu.

Nếu cấp quá nhiều `ConcGCThreads`:

- Marking có thể nhanh hơn **nếu có CPU thực**.
- Nhưng có thể lấy CPU từ application threads, gây giảm throughput hoặc tăng request latency.
- Nếu container CPU quota thấp, marking và application đồng thời có thể bị throttling.

### 9.1. Số luồng concurrent không sửa trực tiếp thuật toán Full GC

~~~bash
java -XX:+UseG1GC -XX:ConcGCThreads=1 -jar service.jar
~~~

Cờ này **không phải** phương án “chỉ dùng 1 worker Full GC”. Muốn kiểm soát số parallel STW worker, xem `ParallelGCThreads`. Tuy vậy, hai loại threads có **tác động liên đới**: nếu concurrent marking không kịp, Full GC có thể xuất hiện thường xuyên hơn; nếu STW tasks thiếu worker, pause có thể dài hơn.

### 9.2. Đừng giải quyết CPU starvation bằng cách tăng một cờ riêng lẻ

Với CPU quota 1–2 cores, việc tăng đồng thời application thread pool, ForkJoinPool, JIT compiler threads và concurrent GC threads có thể làm tổng runnable threads vượt xa tài nguyên thực. Cần nhìn **toàn bộ tiến trình** chứ không riêng GC. `ActiveProcessorCount` ảnh hưởng một số ergonomics của những thread pools đó, nên bất kỳ override nào cũng cần test performance ở mức ứng dụng.

## 10. Ví dụ Java 17+ độc lập: đọc CPU và GC worker settings

Chương trình dưới đây:

- Cấp phát **4 blocks**, mỗi block 1 MiB, đủ nhỏ cho demo.
- Đọc `Runtime.availableProcessors()`.
- Dùng `HotSpotDiagnosticMXBean` đọc giá trị **`ParallelGCThreads`** và **`ConcGCThreads`**.
- In dữ liệu/checksum ổn định trước và sau lệnh yêu cầu GC.
- Gọi `System.gc()` **một lần** để tạo một event GC có thể phân tích qua GC log ở cấu hình thử nghiệm.
- Không giả định rằng nội dung heap sau GC được thay thế hoặc application object bị biến mất; các `blocks` vẫn còn được giữ reference.

**Phạm vi portability:** `com.sun.management.HotSpotDiagnosticMXBean` là API chẩn đoán trong module `jdk.management` của các JDK hỗ trợ, phù hợp với demo HotSpot, **không phải portable contract cho mọi Java VM implementation**. Đọc JVM flags ở đây phục vụ quan sát, không phải business logic.

Lưu đúng file **`G1FullGcCpuDemo.java`**:

~~~java
import com.sun.management.HotSpotDiagnosticMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;

public final class G1FullGcCpuDemo {
    static String vmOption(String name) {
        var bean = ManagementFactory.getPlatformMXBean(
                HotSpotDiagnosticMXBean.class);
        return bean.getVMOption(name).getValue();
    }

    static long checksum(List<byte[]> payload) {
        long sum = 0;
        for (byte[] block : payload) {
            sum += block.length;
        }
        return sum;
    }

    public static void main(String[] args) {
        var blocks = new ArrayList<byte[]>();
        for (int i = 0; i < 4; i++) {
            blocks.add(new byte[1024 * 1024]);
        }
        System.out.println("processors=" +
                Runtime.getRuntime().availableProcessors());
        System.out.println("parallel-threads=" +
                vmOption("ParallelGCThreads"));
        System.out.println("concurrent-threads=" +
                vmOption("ConcGCThreads"));
        System.out.println("bytes-held=" + checksum(blocks));
        System.gc();
        System.out.println("after-gc-bytes-held=" + checksum(blocks));
        System.out.println("explicit-gc-requested=true");
    }
}
~~~

### 10.1. Biên dịch

~~~bash
javac --release 17 -encoding UTF-8 G1FullGcCpuDemo.java
~~~

### 10.2. Chạy với CPU/GC workers được cố định cho demo

~~~bash
java -XX:+UseG1GC \
     -XX:ActiveProcessorCount=2 \
     -XX:ParallelGCThreads=2 \
     -XX:ConcGCThreads=1 \
     -XX:-DisableExplicitGC \
     -XX:-ExplicitGCInvokesConcurrent \
     -Xms64m -Xmx64m \
     -Xlog:gc*=info:file=gc.log \
     G1FullGcCpuDemo
~~~

Đây là lệnh cho **POSIX shell**, dùng ký tự `\` để nối dòng. Với Windows PowerShell, có thể ghi toàn bộ flags trên **một dòng** để tránh khác biệt cú pháp:

~~~powershell
java -XX:+UseG1GC -XX:ActiveProcessorCount=2 -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1 -XX:-DisableExplicitGC -XX:-ExplicitGCInvokesConcurrent -Xms64m -Xmx64m "-Xlog:gc*=info:file=gc.log" G1FullGcCpuDemo
~~~

Lưu ý:

- `-XX:+UseG1GC` chọn G1 tường minh, tránh phụ thuộc ergonomics chọn collector.
- `-XX:ActiveProcessorCount=2` tạo môi trường quan sát ổn định về **số CPU JVM tin là khả dụng**, không thay giới hạn OS.
- `-XX:ParallelGCThreads=2` và `-XX:ConcGCThreads=1` cố định hai nhóm thread khác nhau.
- `-Xms64m -Xmx64m` tạo heap hữu hạn để demo tái lập; đây không phải gợi ý heap size cho production.
- `-XX:-DisableExplicitGC` và `-XX:-ExplicitGCInvokesConcurrent` giúp lệnh `System.gc()` trong **môi trường HotSpot đã thử** dẫn tới Full GC STW, thay vì bị bỏ qua/chuyển thành concurrent theo một số cấu hình.
- `-Xlog:gc*=info:file=gc.log` ghi log ra file **riêng**, vì unified logging có thể thay thứ tự/timestamps và làm stdout thay đổi.
- Các cờ explicit-GC ở đây **chỉ dành cho kiểm thử**; không sao chép nguyên sang production để định kỳ tạo Full GC.

### 10.3. Stdout chính xác đã kiểm chứng

~~~text
processors=2
parallel-threads=2
concurrent-threads=1
bytes-held=4194304
after-gc-bytes-held=4194304
explicit-gc-requested=true
~~~

Giải thích:

1. `processors=2`: JVM thấy 2 processors theo override của bài thử.
2. `parallel-threads=2`: cờ điều khiển upper/configured bound cho STW parallel GC workers đang là 2.
3. `concurrent-threads=1`: concurrent marking worker setting là 1.
4. `bytes-held=4194304`: bốn mảng 1 MiB có tổng byte content bằng 4 × 1.048.576; **không phải lượng heap tổng** vì object headers/ArrayList/JVM metadata còn có overhead.
5. `after-gc-bytes-held=4194304`: chương trình vẫn giữ tham chiếu đến các mảng, nên không kỳ vọng GC thu hồi chúng.
6. `explicit-gc-requested=true`: code **đã gọi** `System.gc()`; dòng này **không tự chứng minh** Full GC đã chạy. Bằng chứng thật là GC log ở bước tiếp theo.

### 10.4. Kiểm tra Full GC và workers trong log

Trên POSIX:

~~~bash
grep -E 'CPUs:|Parallel Workers:|Pause Full|Using [0-9]+ workers' gc.log
~~~

Trên Windows PowerShell:

~~~powershell
Select-String -Path .\gc.log -Pattern "CPUs:|Parallel Workers:|Pause Full|Using [0-9]+ workers"
~~~

Trong bản HotSpot đã thử, các dòng liên quan có nội dung:

~~~text
[info][gc,init] CPUs: 28 total, 2 available
[info][gc,init] Parallel Workers: 2
[info][gc,start] GC(0) Pause Full (System.gc())
[info][gc,task] GC(0) Using 2 workers of 2 for full compaction
[info][gc] GC(0) Pause Full (System.gc()) 10M->9M(64M) 2.496ms
~~~

**Đây là trích log đã rút bớt phần timestamps/tags khoảng trắng**, không phải stdout và **không phải kỳ vọng chính xác trên mọi máy**. Đặc biệt:

- `28 total` là số CPU host của môi trường thử, **không** phải giá trị universal.
- `2 available` đến từ cấu hình JVM thử.
- `Using 2 workers of 2` là bằng chứng **hai workers đã được sử dụng** cho full compaction trong pause cụ thể.
- `2.496ms` chỉ là **một mẫu đo** trên một workload rất nhỏ, không phải benchmark hay SLA.
- `10M->9M(64M)` là heap summary của lần thử; có thể khác theo JDK, heap layout, allocation và GC ergonomics.

### 10.5. Kết quả này chứng minh điều gì và không chứng minh điều gì?

**Có thể kết luận:** Java code chạy trên JDK hiện có; HotSpot đã nhận `ActiveProcessorCount=2`, sử dụng hai parallel workers cho một `Pause Full (System.gc())`; output trước/sau GC có cùng logic.

**Không thể kết luận:** hai workers luôn nhanh hơn một worker 2 lần; một service production sẽ thường gặp Full GC; `System.gc()` luôn tạo Full GC trên mọi JVM; hay 2 processors đồng nghĩa OS cấp riêng 2 cores vật lý. Demo chỉ kiểm **cơ chế** trong điều kiện kiểm soát.

## 11. Cách xem flags và GC threads của JVM thực tế

### 11.1. Xem option values ở startup

~~~bash
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version
~~~

Có thể lọc tên các options như `ParallelGCThreads`, `ConcGCThreads`, `ActiveProcessorCount`. Với POSIX:

~~~bash
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version 2>&1 |
    grep -E 'ParallelGCThreads|ConcGCThreads|ActiveProcessorCount'
~~~

Nếu có container CPU quota, lặp với JVM chạy **bên trong container**, không chỉ host. `PrintFlagsFinal` hiển thị trạng thái option của JVM ở thời điểm khởi tạo; vẫn cần log để biết **số workers thật được kích hoạt** trong GC pause.

### 11.2. Xem GC log theo pha

~~~bash
java -XX:+UseG1GC \
     -Xlog:gc*=info:file=gc.log:uptimemillis,level,tags \
     -jar service.jar
~~~

Khi cần phân tích sâu trong môi trường thử:

~~~bash
java -XX:+UseG1GC \
     -Xlog:gc+phases=debug,gc+task=debug:file=gc-detail.log \
     -jar service.jar
~~~

Đọc `-Xlog:help` trên JDK target nếu một tổ hợp tag/level không phù hợp. Ghi log chi tiết có overhead và tạo file lớn; bật ở điều kiện được kiểm soát, cấu hình log rotation/bảo vệ dữ liệu khi cần.

Các dấu hiệu đáng chú ý:

- `Pause Young (Normal)`: young GC thông thường.
- `Pause Young (Mixed)` hoặc tên phase tương đương: mixed collection.
- `Concurrent Mark Cycle`: G1 đang làm công việc concurrent.
- `Pause Full (...)`: **Full GC STW**.
- `Using N workers of M`: công việc song song cụ thể sử dụng N workers trong số M.
- `To-space exhausted`/`Evacuation Failure`/`Allocation Failure`/`G1 Humongous Allocation`: có thể là tín hiệu dẫn tới áp lực GC, cần đối chiếu phase/context.

Những chuỗi chính xác có thể thay theo JDK và log level. Không parse cứng **từng chữ** của log như một API ổn định giữa mọi bản Java. Với hệ thống quan sát thật, dùng parser/metrics tương thích JDK version và cross-check với raw events.

### 11.3. `jcmd` khi tiến trình còn sống

~~~bash
jcmd <PID> VM.flags
jcmd <PID> VM.info
jcmd <PID> GC.heap_info
~~~

Đây là cú pháp minh họa — thay `<PID>` bằng process ID thật. Phạm vi command phụ thuộc bản JDK và attach permissions. `jcmd` giúp kiểm runtime flags, môi trường và heap, nhưng vẫn không chứng minh 8 workers được sử dụng trong **mỗi** Full GC; để biết điều đó, dùng GC log.

## 12. So sánh một số cấu hình trong môi trường có 2 CPUs

Giả định **CPU budget thực sự là khoảng 2 cores** và cùng workload/heap/JDK.

| Cấu hình | Kỳ vọng cần đo | Không được kết luận sẵn |
| --- | --- | --- |
| **A. JVM tự chọn** | Baseline về pauses, CPU, workers; nên đo trước | Default luôn sai vì host nhiều CPU |
| **B. `ActiveProcessorCount=2`, threads auto** | JVM suy heuristics theo 2 CPUs, có thể giảm oversubscription | JVM có thêm CPU so với quota |
| **C. `ParallelGCThreads=2, ConcGCThreads=1`** | Baseline tường minh hai nhóm GC workers | Mọi pause chắc dùng 2 workers |
| **D. `ParallelGCThreads=4, ConcGCThreads=1`** | Có thể cải thiện workload lớn hoặc gặp throttling | Bốn threads chắc nhanh gấp đôi |
| **E. `ParallelGCThreads=1, ConcGCThreads=1`** | Giảm parallel overhead/CPU tranh chấp, có thể tăng STW duration | Giảm CPU luôn cải thiện latency |
| **F. Chỉ tăng `ConcGCThreads`** | Có thể giảm marking duration nhưng cạnh tranh CPU với app | Trực tiếp tăng workers Full GC |
| **G. Nâng CPU limit lên 4 cores thật** | Có thể cho phép parallel work tiến nhanh hơn | Mọi Full GC cải thiện tương ứng 2 lần |

Dấu hiệu cần đo ở mọi phương án: **Full GC duration, Full GC count, young/mixed pauses, concurrent marking duration, total GC CPU, request p95/p99, throttling, memory footprint và application throughput**.

### 12.1. CPU scaling có điểm tối ưu, không phải càng nhiều càng tốt

Giả sử CPU budget được tăng từ 2 lên 4 cores và đồng thời cho JVM nhận diện đúng 4. Full GC có thể dùng nhiều worker hơn; nhưng nếu bottleneck là 1 GB dữ liệu sống phải copy/scan với memory bandwidth bão hòa, tốc độ không tăng tuyến tính. Nếu ứng dụng bị thiếu heap và phải Full GC liên tục, thêm CPU có thể giảm độ dài từng pause mà **không giảm số pause**.

### 12.2. Thêm worker làm thay đổi nhiều pha

Một thí nghiệm thay `ParallelGCThreads` ảnh hưởng không chỉ Full GC mà cả những công việc parallel trong pauses khác. Vì vậy, nếu duration Full GC giảm nhưng Young/Mixed pauses hoặc throughput tệ đi, **không được chỉ chọn một metric Full GC** để kết luận tuning thành công.

## 13. Thực nghiệm A/B đúng phương pháp

Để kết luận số GC threads phù hợp, cần so sánh dưới điều kiện được kiểm soát.

### 13.1. Cố định những điều kiện quan trọng

1. **Cùng JDK build/vendor**, vì G1 heuristics thay đổi giữa versions.
2. **Cùng workload**: số request, allocation rate, dữ liệu sống, số user, cùng code path.
3. **Cùng `-Xms`/`-Xmx` và heap layout** (trừ khi chính heap là biến độc lập cần nghiên cứu).
4. **Cùng GC collector** và tập flags khác.
5. **Cùng container requests/limits/cpuset**, node type và mức tranh CPU.
6. **Cùng điều kiện warm-up/JIT**, so sánh sau giai đoạn ổn định hoặc ghi rõ startup.
7. **Nhiều lần chạy**, không chỉ một Full GC ép bằng `System.gc()`.
8. **Thống kê p50/p95/p99** của pauses có đủ mẫu, cùng application latency/throughput.
9. **Xem nguyên nhân Full GC** chứ không gộp mọi event GC.
10. **Giữ log phù hợp** và quan sát side effects của logging/JFR.

### 13.2. Các chỉ số nên ghi

| Metric | Công dụng |
| --- | --- |
| Full GC count và cause | Xem Full GC có hiếm hay diễn ra thường xuyên |
| Full GC wall time p50/p95/p99 | Đánh giá thời gian STW gây tail latency |
| Full compaction workers used | Xác minh tuning thực có tác động trong từng pause |
| Young/Mixed GC pauses | Đo tác động phụ khi thay `ParallelGCThreads` |
| Concurrent marking duration | Đo mức tiến triển khi thay `ConcGCThreads` |
| Application throughput, request p95/p99 | Mục tiêu sản phẩm, không chỉ GC |
| CPU user/system và thread utilization | Biết workers có bận thực sự không |
| Cgroup `throttled_usec`/throttling metrics | Phát hiện CPU quota cản trở thực thi |
| Heap occupancy, live-set size, promotion | Giải thích áp lực bộ nhớ dẫn tới Full GC |
| Evacuation failures/humongous allocations | Tìm nguyên nhân chưa giải quyết |
| Total allocated bytes / allocation rate | Đánh giá churn làm GC bận |
| Node/pod CPU contention | Phân biệt vấn đề ứng dụng với host |

### 13.3. Đánh giá theo tỷ lệ GC time và pause budget

Nếu một service có Full GC kéo dài 2 giây nhưng chỉ xảy ra vài lần mỗi tuần, tác động có thể chủ yếu tới **tail latency của những request trùng thời điểm**. Nếu Full GC xảy ra nhiều lần mỗi phút, **tần suất** và **nguyên nhân thiếu bộ nhớ** cần được xử lý trước. Không nên chọn số GC workers chỉ nhằm tối ưu một trị số pause đơn lẻ trong khi tổng GC overhead vẫn cao.

## 14. Câu hỏi đầu tiên khi gặp Full GC: vì sao nó xảy ra?

G1 được thiết kế để thường xuyên thu hồi bằng young/mixed collections và concurrent marking, không xem Full GC là đường đi “bình thường nên được tuning cho thật nhanh”. JEP 307 chỉ giảm phần tệ nhất khi fallback xảy ra.

Các nhóm nguyên nhân đáng điều tra:

1. **Heap không đủ so với live set:** quá nhiều đối tượng vẫn còn reachable.
2. **Allocation rate cao:** ứng dụng tạo rác nhanh hơn mức GC kịp giải phóng.
3. **Evacuation failure/to-space exhaustion:** không còn đủ destination regions khi phải di chuyển object.
4. **Old generation occupancy cao:** concurrent marking/mixed collection không kịp.
5. **Humongous objects:** object lớn chiếm nhiều regions, hạn chế cách thu hồi và có thể dẫn tới pressure/fragmentation.
6. **Thay đổi workload đột ngột:** batch task, load spike, cache warm-up, số lượng concurrent requests.
7. **Explicit GC request:** `System.gc()` hoặc thư viện gọi, cần kiểm log cause.
8. **Memory leak hoặc cache growth:** giữ reference lâu hơn dự định.

### 14.1. Giảm Full GC có thể có lợi hơn tăng Full GC workers

Giả sử một service đang có 50 Full GC mỗi giờ. Giảm một pause từ 1 giây xuống 700 ms bằng nhiều CPU hơn không loại bỏ sự gián đoạn thường xuyên. Nếu nguyên nhân là heap thiếu/objects sống quá nhiều, sửa quản lý dữ liệu, giảm allocation rate hoặc tăng heap phù hợp có thể **giảm tần suất Full GC** và cải thiện toàn diện.

Trước khi chỉnh `ParallelGCThreads`, xem:

- Có bộ nhớ thực để tăng `-Xmx` trong giới hạn container không?
- Tỷ lệ live objects/caches có bình thường không?
- G1 có đủ thời gian cho concurrent marking/mixed reclaim không?
- Có evacuation failures hoặc humongous allocation patterns không?
- Có explicit requests cần loại bỏ không?

Không tăng `-Xmx` vượt memory limit container, vì JVM còn native memory, metaspace, thread stacks, code cache và OS memory overhead. Heap tăng có thể giảm pressure, nhưng cũng có thể tăng lượng live data phải xử lý trong Full GC.

## 15. Humongous objects và Full GC: không phải chỉ do thread count

Trong G1, object có kích thước lớn hơn **một nửa kích thước region** được coi là **humongous** theo quy tắc thông dụng. Những object này dùng một hay nhiều humongous regions và có cách cấp phát/thu hồi khác object bình thường.

Hệ quả:

- Một số humongous allocations có thể kích hoạt concurrent marking sớm.
- Cần đủ contiguous regions để thỏa yêu cầu cấp phát.
- Nếu không có đủ không gian phù hợp, có thể xuất hiện GC nghiêm trọng, kể cả Full GC.
- Oracle mô tả **di chuyển humongous objects** là last-resort và có thể rất chậm trong tình huống đặc biệt.
- Thêm `ParallelGCThreads` **không tự sửa** chiến lược cấp phát humongous hoặc tình trạng fragmentation.

Gợi ý xử lý chỉ sau khi có số liệu: phân tích kích thước object, thiết kế buffer/chunking, giảm peak memory, xem kích thước regions (`G1HeapRegionSize`) và heap headroom. **Không** tăng region size một cách máy móc: nó tác động tới ngưỡng humongous và cấu trúc G1, có thể làm tình hình khác xấu đi.

## 16. Pause target, GC workers và những giới hạn không thể vượt

### 16.1. `-XX:MaxGCPauseMillis` là mục tiêu mềm

G1 sử dụng pause-time goal như `-XX:MaxGCPauseMillis` để điều chỉnh work trong các collection pauses thông thường. Nhưng đây **không phải deadline hard-real-time**.

~~~bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar service.jar
~~~

Không được hiểu lệnh trên là “mọi pause, đặc biệt Full GC, sẽ tối đa 200 ms”. Full GC fallback có thể kéo dài đáng kể nếu heap/live set lớn hoặc CPU hạn chế. Chỉ tăng `ParallelGCThreads` cũng không bảo đảm đáp ứng pause goal.

### 16.2. CPU budget có thể quan trọng hơn một flag

Nếu ứng dụng có SLO tail latency chặt, giới hạn CPU có thể làm cả **concurrent marking** và **STW work** chậm. Khi heap pressure lớn, hệ quả vòng lặp có thể là:

~~~text
CPU budget thấp / throttling
           ↓
Concurrent marking tiến triển chậm
           ↓
G1 thiếu thời gian thu hồi old regions
           ↓
Heap pressure/evacuation failure tăng
           ↓
Full GC fallback (STW)
           ↓
Pause dài hơn do CPU vẫn thiếu
           ↓
Request tail latency tăng
~~~

Đây là **một chuỗi nguyên nhân có thể xảy ra**, không phải mọi Full GC đều do thiếu CPU. Nếu live set thật vượt khả năng heap, tăng CPU cũng không tạo thêm bộ nhớ có thể sử dụng.

### 16.3. GC worker có dùng thêm native memory không?

Mỗi GC worker là native thread và có overhead thread/stack, nhưng số thread cấu hình không đồng nghĩa từng worker đang chiếm trọn một CPU, cũng không đồng nghĩa chi phí bộ nhớ chỉ là stack cố định. Với container memory rất nhỏ, tất cả thành phần native memory/heap phải được theo dõi; đừng coi thêm GC threads là miễn phí về memory footprint.

## 17. `System.gc()`: chỉ là công cụ thử nghiệm, không phải lời khuyên tuning

`System.gc()` là một **yêu cầu** thu gom mà VM có thể xử lý hoặc bỏ qua theo cấu hình. Với G1/HotSpot:

- `-XX:+DisableExplicitGC` có thể khiến explicit requests bị bỏ qua.
- `-XX:+ExplicitGCInvokesConcurrent` có thể khiến explicit GC đi theo đường concurrent thay vì Full GC STW.
- Trên JDK/collector khác, behavior có thể khác.
- Một request có thể không tương đương tình huống Full GC do heap thực sự cạn kiệt.
- Demo ở phần 10 chọn flags explicit để **quan sát một Full GC** và log hai workers.

**Không đưa `System.gc()` vào scheduled job production để “dọn rác trước khi thiếu RAM”.** Nó có thể tạo STW pause lớn, làm mất hiệu quả của G1 ergonomics và khiến ứng dụng có latency bất ngờ. Với lỗi thiếu bộ nhớ, cần phân tích allocation/leak/GC logs và heap sizing.

### 17.1. Nếu không thấy Full GC sau `System.gc()`

Đừng vội nghĩ JEP 307 không hoạt động. Kiểm:

1. Có đang chạy G1 không?
2. `DisableExplicitGC` có được bật không?
3. `ExplicitGCInvokesConcurrent` có được bật không?
4. JVM khác HotSpot hay JDK version khác không?
5. GC log có ghi nguyên nhân `System.gc()` và tên pause nào không?
6. Cờ GC có bị launcher/container entrypoint sửa hoặc thay sau không?

Trong tình huống cần mô phỏng Full GC, hãy chạy trên **workload thử** với flags được xác nhận và kiểm log; đừng cố ép heap production tới OOM chỉ để chứng minh parallelism.

## 18. Case study: container 2 CPU nhưng JVM thấy nhiều hơn

Giả sử một dịch vụ có cấu hình môi trường:

~~~text
Host:                  32 logical CPUs
Pod CPU limit:          2 CPU (quota)
Heap:                   Xmx 2 GiB
JVM availableProcessors: 16 (quan sát giả định cần xác minh)
ParallelGCThreads:      13 (ví dụ do heuristics/cấu hình)
ConcGCThreads:           3
Observed:               frequent CPU throttling during G1 activity
~~~

**Đây là kịch bản giả định để học cách phân tích, không phải kết quả đo từ một cluster thật.** Đặc biệt số 13 chỉ minh họa nguy cơ oversubscription, **không phải công thức default bắt buộc** cho 16 CPU trên mọi JDK.

Quy trình:

1. Xác nhận JDK build, G1 được chọn và CPU quota/cpuset thực.
2. Xem `Runtime.availableProcessors()`, flags và GC init logs.
3. Nếu nhận diện CPU không phản ánh resource budget, kiểm container support và cân nhắc `-XX:ActiveProcessorCount=2`.
4. So sánh baseline với cấu hình explicit `ParallelGCThreads=2`/`ConcGCThreads=1` nếu có lý do; không coi đây là tối ưu mặc định.
5. Đo GC task workers thực, throttling, Full GC count/duration và request latency.
6. Nếu marking chậm do CPU thiếu, cũng xem concurrency/request parallelism và CPU budget của toàn pod.
7. Nếu Full GC vẫn diễn ra nhiều, tìm nguyên nhân live set/heap pressure; không dừng ở chỉnh GC threads.

### 18.1. Lưu ý về CPU quota và burst

Container quota thường tính CPU time trên chu kỳ. Một workload có thể burst trong thời gian ngắn rồi bị throttled; `availableProcessors()` chỉ là **thông số heuristic**, không truyền tải toàn bộ hình dạng quota/burst/scheduler contention. Tối ưu GC trong container cần quan sát metrics cgroup thực tế.

### 18.2. Nhiều JVM trên cùng một node

Nếu nhiều JVM đều được cấu hình `ParallelGCThreads=8` trên node 8 CPU, Full GC của các JVM có thể xảy ra cùng lúc (ví dụ sau traffic spike). OS scheduler phải phân phối CPU, và pause wall-time tăng so với lúc chỉ một JVM chạy. Vì vậy A/B test một tiến trình cô lập có thể **không đại diện** cho môi trường chạy nhiều pods.

## 19. Case study: Full GC rất ít nhưng mỗi lần dài

Giả định một service có heap lớn, Full GC xảy ra rất hiếm, nhưng mỗi lần kéo dài nhiều giây:

- Trước tiên xác định **nguyên nhân** của Full GC (explicit, evacuation failure, allocation/humongous pressure).
- Kiểm heap **live occupancy**, headroom, số regions và tình trạng memory limit.
- Kiểm workers được dùng trong log: ví dụ max 8 nhưng thực chỉ 4 do heap-size ergonomics.
- Kiểm CPU scheduler/NUMA/memory bandwidth.
- Nếu tài nguyên CPU dư và phần parallel work lớn, thử tăng workers trong một thí nghiệm được kiểm soát.
- Nếu Full GC do memory leak/too-small heap, việc thêm workers có thể chỉ **giảm biểu hiện** chứ không ngăn Full GC tiếp diễn.
- Nếu service đáp ứng latency SLO ngay cả khi Full GC hiếm, ưu tiên tránh fallback; song song hóa chỉ là lớp giảm thiệt hại.

**Tại sao không dùng một benchmark `System.gc()` ngắn để đặt production flags?** Những conditions về live set, fragmentation, roots, dirty cards và heap pressure khác hẳn một demo 4 MiB, nên kết quả scaling có thể không tương quan.

## 20. Những lỗi suy luận thường gặp

| Nhầm lẫn | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “G1 Full GC sau Java 10 là concurrent” | Full GC vẫn STW | “Parallel” chỉ các GC workers chạy đồng thời |
| “`ParallelGCThreads` chỉ ảnh hưởng Full GC” | Còn ảnh hưởng Young/Mixed STW tasks | Đo lại toàn bộ pause distribution |
| “`ConcGCThreads` là workers Full GC” | Nó dành concurrent work | Dùng `ParallelGCThreads` cho STW parallel work |
| “`ActiveProcessorCount=8` cấp thêm 8 cores” | Chỉ ghi đè thông tin CPU JVM dùng cho heuristics | Kiểm CPU quota/cpuset thực |
| “JVM nhìn 16 CPUs thì container được 16 CPUs” | Quota/cpuset/affinity có thể thấp hơn | Quan sát cgroups và CPU throttling |
| “Config 8 workers nghĩa pause dùng đúng 8” | G1 có thể dùng ít hơn | Đọc `Using N workers of M` |
| “8 workers nhanh gấp 8 lần” | Synchronization, tuần tự, bandwidth | Benchmark wall-time và CPU |
| “Tăng workers luôn giảm Full GC pause” | CPU throttling/overhead có thể làm dài hơn | Thử từng thay đổi dưới resource budget |
| “`MaxGCPauseMillis=200` bảo đảm Full GC <200 ms” | Chỉ là soft goal cho GC ergonomics | Theo dõi log/SLO và tránh fallback |
| “G1 có Full GC nhiều là do worker quá ít” | Có thể thiếu heap/leak/evacuation failures | Phân tích cause/live set |
| “`System.gc()` luôn tạo Full GC” | Có thể bị disable hoặc concurrent behavior | Dùng flags thử và kiểm GC log |
| “Có `Pause Full` nghĩa JEP307 bị tắt” | Song song hóa không loại bỏ Full GC | Kiểm số workers trong log |
| “`ParallelGCThreads=2` làm JVM chỉ có 2 threads” | App/JIT/GC khác còn nhiều threads | Quan sát tổng CPU/thread usage |
| “Thêm concurrent threads không ảnh hưởng request” | Concurrent work cạnh tranh CPU với app | Đo latency/throughput |
| “Giảm threads = giảm GC pause” | Thiếu worker làm công việc lâu hơn | Tìm điểm tối ưu qua benchmark |
| “Tăng Xmx luôn chữa được” | Có native memory limit, live set/leak | Sizing theo dữ liệu và container limit |
| “Chạy trên host giống trong pod” | Quota, cgroups, contention khác | Test môi trường triển khai thật |
| “Một dòng `processors=2` chứng minh 2 core độc quyền” | Runtime API là tín hiệu heuristic | Kiểm scheduler/cgroup |
| “CPU usage cao chứng minh GC tối ưu” | Có thể toàn GC overhead mà app chậm | Đo application throughput/pause |
| “Nên hard-code số workers ở mọi JDK” | Ergonomics/JDK/heap thay đổi | Giữ default trừ khi có bằng chứng tuning |

## 21. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** JEP nào của Java 10 song song hóa G1 Full GC?

**Đáp án:** **JEP 307 – Parallel Full GC for G1**. Nó cải thiện fallback Full GC worst-case latency bằng cách dùng nhiều workers thay cho algorithm đơn luồng trước đó.

**Câu 2.** G1 Full GC song song có còn STW không?

**Đáp án:** **Có**. Parallel workers thực hiện GC khi application mutator threads đã dừng.

**Câu 3.** `ParallelGCThreads=4` có cam kết 4 CPU core được cấp không?

**Đáp án:** Không. Nó đặt số GC parallel workers theo cấu hình, không cấp CPU vật lý/quota.

**Câu 4.** Cờ nào liên quan đến concurrent marking?

**Đáp án:** `-XX:ConcGCThreads=N`. Nó không trực tiếp đặt số workers Full GC.

**Câu 5.** `ActiveProcessorCount=2` làm gì?

**Đáp án:** Ghi đè số processor JVM dùng cho các heuristics như GC/thread pools; không tăng hay sửa CPU limit của OS/Kubernetes.

**Câu 6.** Tại sao `ParallelGCThreads` có thể khác số workers thực trong log?

**Đáp án:** G1 chọn workers cho từng GC task/pause theo workload, heap capacity và ergonomics, có thể thấp hơn giới hạn.

**Câu 7.** Với 2 CPU quota, ép 16 GC workers có chắc nhanh hơn 2 workers không?

**Đáp án:** Không. Quá nhiều runnable workers có thể bị throttling, tranh CPU và tốn overhead.

**Câu 8.** Full GC thường xuyên có nghĩa chỉ cần tăng `ParallelGCThreads`?

**Đáp án:** Không. Phải tìm nguyên nhân như heap pressure, evacuation failure, live set, humongous objects hoặc explicit GC.

**Câu 9.** `-XX:MaxGCPauseMillis=200` có giới hạn cứng Full GC 200 ms không?

**Đáp án:** Không. Đó là pause target mềm; Full GC fallback có thể lâu hơn đáng kể.

**Câu 10.** Vì sao `ConcGCThreads` quá cao có thể làm app chậm?

**Đáp án:** Concurrent GC workers chạy trong lúc app hoạt động, nên cạnh tranh CPU với business threads.

**Câu 11.** Vì sao `ConcGCThreads` quá thấp cũng rủi ro?

**Đáp án:** Marking/reclamation progress có thể không kịp allocation pressure, làm tăng nguy cơ fallback.

**Câu 12.** `ParallelGCThreads` ảnh hưởng những loại collection nào?

**Đáp án:** Các parallel STW tasks của G1, gồm Full GC fallback và những tasks của Young/Mixed pauses; không chỉ Full GC.

**Câu 13.** Tên collector “Parallel GC” và “G1 Full GC song song” có giống nhau không?

**Đáp án:** Không. `UseParallelGC` chọn collector khác; `UseG1GC` chọn G1 có đường Full GC song song từ Java 10.

**Câu 14.** Trong log `Using 2 workers of 2 for full compaction`, điều gì được xác minh?

**Đáp án:** Full-compaction task cụ thể sử dụng 2 workers trong số 2 workers được cấu hình cho task, không chứng minh tăng tốc 2 lần.

**Câu 15.** Tại sao cộng CPU time của 2 GC workers có thể lớn hơn pause wall-time?

**Đáp án:** Vì hai workers có thể chạy đồng thời trên các CPU thực tế khác nhau; tổng CPU time là tổng lượng thời gian tính trên từng worker.

**Câu 16.** Khi nào `System.gc()` không tạo Full GC như ví dụ?

**Đáp án:** Khi explicit GC bị vô hiệu, được chuyển thành concurrent hoặc collector/runtime có behavior khác; phải đọc flags và GC log.

**Câu 17.** Bài demo giữ tham chiếu đến 4 mảng. Vì sao `after-gc-bytes-held` vẫn bằng `4194304`?

**Đáp án:** Vì bốn mảng vẫn reachable, và chương trình đo tổng `length` chứ không đo free heap; GC không làm mất object đang được dùng.

**Câu 18.** Nếu pod có CPU request 4 nhưng CPU limit 2, nên dùng số nào để nhận diện khả năng thực thi khi throttling?

**Đáp án:** Phải xem cả request/limit, cgroup quota/cpuset, throttling và đo runtime; CPU limit 2 có thể giới hạn tổng CPU thực tế dù request lớn hơn.

**Câu 19.** Điều gì có thể khiến giảm `ParallelGCThreads` cải thiện latency?

**Đáp án:** Khi môi trường thiếu CPU và cấu hình hiện tại tạo quá nhiều workers/overhead/throttling. Nhưng có thể làm Young/Mixed/Full work chậm hơn nếu CPU thật dư.

**Câu 20.** Nếu business cần p99 thấp, tối ưu quan trọng hơn là Full GC nhanh hay ít Full GC?

**Đáp án:** Thường cần **tránh Full GC thường xuyên** trước; đồng thời cải thiện fallback latency nếu không thể loại bỏ hoàn toàn. Đánh giá theo SLO thực.

**Câu 21.** Tại sao cần benchmark trong đúng Kubernetes container thay vì chỉ trên host?

**Đáp án:** Vì quota/cpuset, CPU contention, cgroups, heap/native memory limits và JDK container awareness ảnh hưởng workers, scheduling và pauses.

**Câu 22.** Trong demo, output `processors=2` có chứng minh máy host chỉ có 2 CPUs không?

**Đáp án:** Không. Log thử ghi `28 total, 2 available` do `ActiveProcessorCount=2`; số total tùy host.

## 22. Checklist vận hành và tuning

Trước khi thay một cờ G1/CPU trong production, kiểm tra:

1. **Có đúng G1 không?** Kiểm `UseG1GC`/GC startup log.
2. **Full GC có xảy ra thật không?** Kiểm cause/time/frequency chứ không chỉ tổng CPU.
3. **JDK version/build nào đang chạy?** Tài liệu ergonomics phải khớp.
4. **Đã xem heap occupancy/live set, allocation rate, evacuation failures và humongous allocation chưa?**
5. **JVM `availableProcessors()` báo bao nhiêu?**
6. **CPU host, cgroup quota/cpuset, requests/limits và throttling ra sao?**
7. **`ParallelGCThreads`/`ConcGCThreads` đang là bao nhiêu?** Có override từ startup scripts không?
8. **Full GC log có ghi workers thực không?** Có ít hơn configured max không?
9. **Tác động đến Young/Mixed pauses và concurrent marking đã được đo chưa?**
10. **Đã theo dõi application throughput, p95/p99 request latency và GC wall-time chưa?**
11. **Đã so baseline defaults trước khi thử override thủ công chưa?**
12. **Đã kiểm case nhiều JVM/pods tranh CPU trên cùng node chưa?**
13. **Đã giữ `-Xms/-Xmx`, workload, CPU limit và version ổn định khi benchmark chưa?**
14. **Kết quả có được lặp nhiều lần và có confidence đủ để quyết định không?**
15. **Cờ `MaxGCPauseMillis` được hiểu là soft goal, không phải hard deadline chưa?**
16. **Có tránh dùng `System.gc()` như cơ chế production tuning không?**
17. **Có kế hoạch rollback khi chỉnh threads làm latency hoặc throughput xấu đi không?**
18. **Có cảnh báo Full GC count/duration, CPU throttling và memory pressure không?**
19. **Có ghi lại rationale của mọi cờ GC thủ công để review sau khi nâng JDK không?**
20. **Nếu không còn lợi ích rõ ràng, có thể bỏ override để JVM tự điều chỉnh lại không?**

## 23. Tài liệu chính thức và nguồn đọc thêm còn áp dụng

1. [OpenJDK JEP 307 – Parallel Full GC for G1](https://openjdk.org/jeps/307): Java 10 song song hóa fallback Full GC, mục tiêu giảm worst-case latency, dùng các parallel workers liên quan Young/Mixed.
2. [Oracle JDK 10 Release Notes – JEP 307](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): xác nhận thay đổi này được đưa vào JDK 10 và mô tả thuật toán Full GC trước/sau.
3. [Oracle Java SE 25 – Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): STW/concurrent phases, heuristic `ParallelGCThreads` và `ConcGCThreads`, worker constraints, Full GC và G1 heap behavior.
4. [Oracle Java SE 25 – G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): diagnostics, heap sizing, avoidance of Full GC, pauses và advanced tuning.
5. [Oracle Java SE 17 – java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:ParallelGCThreads`, `-XX:ConcGCThreads`, `-XX:ActiveProcessorCount`, `UseContainerSupport`, `UseG1GC`, `-Xlog`, `DisableExplicitGC`, `ExplicitGCInvokesConcurrent`.
6. [Oracle Java SE 25 – java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): các flags vẫn có trên runtime hiện đại, unified logging và container-aware options.
7. [OpenJDK – G1 GC Overview / ops.java](https://ops.java/performance/jvm/articles/g1-intro/): kiến trúc G1, CPU overhead của concurrent phases, latency/throughput tradeoffs.
8. [Java SE 17 – HotSpotDiagnosticMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html): quan sát VM options bằng public diagnostic API trên JVM hỗ trợ.
9. [Java SE 17 – Runtime.availableProcessors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#availableProcessors()): số processors JVM báo là khả dụng cho tiến trình.
10. [Oracle Java SE 17 – jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.flags`, `VM.info`, `GC.heap_info` và các commands tùy phiên bản.
11. [OpenJDK Java HotSpot Container Support](https://openjdk.org/jeps/8182070): nguồn gốc và động cơ hỗ trợ nhận diện tài nguyên CPU/memory container.
12. [OpenJDK JEP 307 issue JDK-8172890](https://bugs.openjdk.org/browse/JDK-8172890): tracker của cải tiến G1 Full GC song song.

**Tóm tắt:** Java 10 làm G1 Full GC **song song** nhờ JEP 307, giảm rủi ro pause tệ nhất nhưng **không làm mất STW**. `ParallelGCThreads` kiểm soát parallel workers cho GC pauses; `ConcGCThreads` phục vụ concurrent work; `ActiveProcessorCount` tác động heuristics CPU chứ không cấp thêm CPU. Vì vậy phải xem **CPU budget/quota/cpuset/throttling**, worker thực trong GC log, heap pressure và SLO thực để tuning. Khi Full GC xảy ra liên tục, **tìm cách giảm nguyên nhân fallback** trước khi chỉ cố tăng số GC threads.
