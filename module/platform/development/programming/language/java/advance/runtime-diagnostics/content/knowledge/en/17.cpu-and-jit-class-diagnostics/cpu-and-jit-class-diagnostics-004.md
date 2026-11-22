# 17.4 Phân biệt thời gian riêng của phương thức với chi phí qua các lời gọi con

## Mục tiêu học tập

Khi đọc Java Flight Recorder (JFR), Java Mission Control (JMC), call tree, flame graph hoặc báo cáo CPU profiler, cùng một phương thức có thể xuất hiện với hai con số rất khác nhau: **self/exclusive** và **total/inclusive**. Một phương thức có self thấp nhưng total cao có thể là nơi **điều phối** những lời gọi tốn kém; một phương thức có self cao có thể thực sự tiêu nhiều CPU ở phần thân của nó. Nếu không phân biệt được hai cách tính, ta dễ tối ưu sai vị trí hoặc gán nhầm độ trễ của database, GC hay thread waiting cho một hàm Java.

Bài này đặt trong ngữ cảnh **CPU, JIT và lớp**: tập trung vào việc đọc mẫu stack của JFR, phân tích cấu trúc lời gọi và hiểu tác động của inlining/JIT, chứ không biến các số từ sampler thành thời gian thực thi chính xác từng lời gọi.

Sau bài này, bạn có thể:

1. Giải thích self/exclusive và total/inclusive, cách tính và mối quan hệ với cây lời gọi.
2. Đọc đúng Hot Methods, Call Tree và flame graph trên dữ liệu CPU samples.
3. Phân biệt chi phí CPU của phương thức với elapsed/wall-clock time, thời gian blocked/waiting và latency end-to-end.
4. Hiểu tại sao recursion, cùng phương thức xuất hiện ở nhiều nhánh, stack truncation, JIT inlining và sampling khiến số liệu dễ bị hiểu sai.
5. Truy từ phương thức total cao sang lời gọi con tạo chi phí và từ phương thức self cao tới đoạn mã cần đo/đánh giá.
6. Dùng JFR/JMC và số liệu bên ngoài để tạo giả thuyết hiệu suất có thể kiểm chứng; tránh kết luận root cause từ một thanh flame graph.

Phạm vi: Java 17+ (HotSpot/OpenJDK, ví dụ lệnh theo JDK 21). Tên cột, cách tổng hợp và đơn vị của profiler có thể khác nhau; luôn kiểm tra **dữ liệu đầu vào là sample count, estimated CPU time, instrumented wall time hay một loại metric khác**.

## 1. Mô hình cơ bản: phương thức và cây lời gọi

Xét một đường gọi đồng bộ:

~~~text
main()
  -> Controller.handle()
       -> Auth.check()
       -> Service.execute()
            -> Repository.query()
            -> Formatter.render()
~~~

Tại thời điểm thread đang chạy trong Repository.query(), stack có thể chứa main, Controller.handle, Service.execute và Repository.query(). Nếu bạn hỏi “code đang chạy **ở frame nào**?”, câu trả lời thường là frame ở **đỉnh stack** (leaf trong cây từ caller xuống callee). Nếu bạn hỏi “lời gọi Controller.handle() chịu trách nhiệm cho bao nhiêu công việc trên toàn nhánh?”, phải tính cả những hoạt động xảy ra trong các phương thức con.

Hai khái niệm:

- **Self time / exclusive cost (chi phí riêng):** phần thời gian hoặc số mẫu được quy cho chính phương thức đó, **không cộng công việc bên trong các lời gọi con** theo mô hình đo đang dùng.
- **Total time / inclusive cost (chi phí bao gồm):** phần thời gian hoặc số mẫu được quy cho phương thức đó **và toàn bộ lời gọi con** bên dưới nó trên đường gọi được xét.

Trong cây một thread thực thi tuần tự, không chồng lấp, dùng cùng một đồng hồ đo và dữ liệu instrument đầy đủ:

~~~text
inclusive(A) = exclusive(A)
             + inclusive(B) + inclusive(C) + ...
~~~

ở đây B, C là **những lời gọi con trực tiếp của đúng một lần gọi A**, không phải mọi method trùng tên trên toàn ứng dụng. Biểu thức này không tự áp dụng cho nhiều thread song song, lời gọi bất đồng bộ, vòng đệ quy đã gộp thành method-level row, hay dữ liệu sampling khi thiếu mẫu. Một phương thức gọi con nhiều lần thì tổng bao gồm các lần gọi tương ứng, nếu dữ liệu đo đủ và không đếm trùng.

**Nguyên tắc:** self trả lời “thời gian/mẫu nằm ở chính thân A bao nhiêu?”, inclusive trả lời “khi stack đi qua A, cả nhánh đó chiếm bao nhiêu?”. Chúng trả lời **hai câu hỏi khác nhau**, không phải hai phép đo mâu thuẫn.

## 2. Ví dụ tính theo thời gian elapsed, đồng bộ và không chồng lấp

Giả sử một request thực hiện đúng cấu trúc tuần tự sau. Các giá trị là **số liệu minh họa**, không phải JFR đã đo được:

~~~text
Controller.handle()       total 120 ms
├── Repository.load()      total  90 ms
│   └── Socket.read()      total  85 ms
└── Formatter.encode()     total  20 ms
~~~

Nếu không có lời gọi con khác và không xảy ra overlap:

| Phương thức | Total / inclusive wall time | Thời gian trong con trực tiếp | Self / exclusive wall time |
| --- | ---: | ---: | ---: |
| Controller.handle | 120 ms | 90 + 20 = 110 ms | 10 ms |
| Repository.load | 90 ms | 85 ms | 5 ms |
| Socket.read | 85 ms | 0 ms | 85 ms |
| Formatter.encode | 20 ms | 0 ms | 20 ms |

Tổng self của các node trong cây là 10 + 5 + 85 + 20 = **120 ms**, khớp thời lượng của lời gọi Controller.handle, với các giả định ở trên. Nhưng tổng các giá trị inclusive ở những hàng là 120 + 90 + 85 + 20 = **315 ms**: đó là **đếm lại cùng những khoảng thời gian** ở nhiều cấp caller/callee, không phải request kéo dài 315 ms.

Cách đọc đúng:

- Controller.handle có total 120 ms nhưng self chỉ 10 ms: tối ưu những lệnh riêng trong controller tối đa chỉ tác động tới một phần nhỏ thời gian nếu không thay đổi cách gọi con.
- Repository.load có total 90 ms nhưng self 5 ms: phần lớn thời gian do Socket.read bên dưới; nên điều tra network/database, connection handling hoặc mô hình truy vấn trước khi tối ưu vài dòng Java trong repository.
- Socket.read có self wall time 85 ms nhưng **không có nghĩa đã dùng 85 ms CPU**. Thread có thể đang chờ dữ liệu, tiêu rất ít CPU.
- Formatter.encode có self wall time 20 ms: nếu thực sự chạy CPU-bound, đây có thể là đối tượng tối ưu CPU; cần profiler đo CPU để xác minh.

Đây là ví dụ theo **wall-clock instrumentation**. Đừng mang các con số wall này gắn nhãn là CPU samples của JFR.

### Tại sao phương thức total cao không nhất thiết là thủ phạm?

Controller là điểm bao ngoài của request nên tự nhiên có total cao. Với request handler, thread root, servlet dispatch, executor worker, framework interceptor hoặc một vòng xử lý, inclusive thường cao vì **đầu mối gọi nhiều công việc**, không phải do thân method tự chậm. Hãy mở rộng các node con tới điểm chi phí tập trung; sau đó xét liệu đây là CPU computation, blocking I/O, scheduling hay waiting.

## 3. Công thức đọc kết quả từ CPU sampling

JFR thường hỗ trợ **stack sampling** để tìm các đường thực thi nóng. Khi lấy mẫu, công cụ quan sát stack của những thread phù hợp tại các thời điểm, tạo các event như jdk.ExecutionSample (theo cấu hình/JDK). Mỗi mẫu là một snapshot, không phải một lời gọi method hoàn chỉnh có start/end.

Giả sử có N mẫu được chọn trong một time window và mỗi mẫu là một chuỗi stack từ caller đến frame đang thực thi. Với phương thức M, nếu tổng hợp theo **method identity** (không theo từng node đường gọi):

- **Self samples(M):** số mẫu mà M là frame thực thi/leaf được quy cho mẫu.
- **Inclusive samples(M):** số mẫu có M xuất hiện ở bất kỳ vị trí phù hợp nào trong stack, theo quy tắc aggregation của công cụ.
- **Self share(M):** self samples(M) / N, nếu N là đúng tập mẫu và cùng bộ lọc.
- **Inclusive share(M):** inclusive samples(M) / N, nếu mỗi mẫu chỉ được tính một lần cho method M ở phép tổng hợp đó.

Ví dụ có 100 samples:

| Method | Self samples | Inclusive samples | Cách hiểu |
| --- | ---: | ---: | --- |
| Controller.handle | 3 | 80 | Rất thường nằm trên stack, nhưng ít mẫu dừng ở phần thân của chính nó |
| Repository.lookup | 2 | 60 | Nhánh gọi con của repository nổi bật |
| Parser.parse | 35 | 35 | Nhiều mẫu có Parser.parse là frame thực thi |
| Hash.compute | 25 | 25 | Hotspot self đáng xem |
| Thread.run | 0 | 100 | Root bao toàn bộ thread được chọn, không có nghĩa Thread.run tốn CPU riêng |

Các hàng chỉ minh họa cách đọc, không yêu cầu self sum của 5 hàng bằng 100 vì bảng không liệt kê đủ mọi method. **Inclusive share của nhiều method có thể cùng cao và tổng vượt 100%**: một sample có thể đồng thời đóng góp cho Controller.handle, Repository.lookup và Hash.compute vì cả ba nằm trên một stack.

Cũng không được phát biểu “inclusive 80 samples = 80 ms CPU” nếu profiler không đưa mô hình chuyển đổi có căn cứ. Sampling có thể không đều, bị trễ hoặc ưu tiên một số thread; sample count trước hết là **tần suất quan sát tương đối**, không phải bộ đếm chính xác thời gian thực thi.

### Self ở Hot Methods và self ở Call Tree có thể khác phạm vi

Một hàng trong **Hot Methods** có thể gom các mẫu của cùng method từ **mọi đường gọi**. Một node trong **Call Tree** thường gắn với **một đường gọi cụ thể**. Cùng method có thể xuất hiện nhiều lần ở các node khác nhau, mỗi node có inclusive/self riêng. Vì vậy không so một dòng Hot Methods với một node Call Tree rồi gọi chúng mâu thuẫn nếu bạn chưa đồng nhất phạm vi.

## 4. Ba góc nhìn: Hot Methods, Call Tree và flame graph

### 4.1. Hot Methods: “self ở đâu tập trung?”

Một danh sách hot methods thường giúp tìm những frame thường xuất hiện ở nơi thực thi thực tế hoặc có exclusive cost cao. Sử dụng nó để tìm các phép toán, vòng lặp, parser, serializer, hashing, regex, compression hoặc các thư viện có thể chiếm CPU.

Cần kiểm tra:

- Cột dùng self, total hay count? Tool có gom theo thread, method, stack path hay class?
- Các method có overload/tên giống nhau không? Phân biệt class, signature, classloader nếu cần.
- Số samples đủ đại diện không? Có sample bias hoặc missing stacks không?
- CPU thực tế của process/thread có cao trong khoảng đó không?
- Method có JIT inlining, compiled/native frames hoặc bị thiếu metadata làm hiển thị khác dự kiến không?

Hot method self cao **gợi ý** vùng tính toán nóng, nhưng chưa đo mức cải thiện khi sửa và chưa chứng minh đó là critical path của request bị chậm.

### 4.2. Call Tree, top-down: “chi phí đi qua nhánh nào?”

Bắt đầu từ entry/root (Thread.run, request dispatcher, task/executor hoặc method được chọn), đi xuống các caller→callee. Ở mỗi node:

1. Xem inclusive share của node so với mẫu đã chọn.
2. Xem self share của node.
3. Nếu inclusive cao nhưng self thấp, **mở rộng con**.
4. Tiếp tục tìm node con có self cao hoặc nhánh chiếm phần đáng kể.
5. Xác minh đây là path thuộc workload cần tối ưu, không phải background worker/GC/compiler thread.

**Tỷ lệ trên nhánh:** Một node con chiếm 70% mẫu **của cha** có thể chỉ chiếm 7% tổng samples toàn recording nếu cha chỉ chiếm 10%. Hãy xem denominator ở từng cột/view, tránh đọc tỷ lệ theo cha thành phần trăm CPU toàn hệ thống.

### 4.3. Bottom-up / caller tree: “phương thức nóng được gọi từ đâu?”

Bắt đầu từ một method self cao (ví dụ Parser.parse), mở các caller phía trên để biết ai kích hoạt nó: endpoint A, batch B hay framework C. Cách này hữu ích khi cùng method được gọi từ nhiều đường nhưng **chỉ một đường** gây bottleneck.

Ví dụ Parser.parse có 40 samples self toàn ứng dụng:
- 30 samples thuộc endpoint /import với payload rất lớn;
- 10 samples thuộc endpoint /preview với payload nhỏ.

Tối ưu Parser.parse có thể tác động cả hai, nhưng điều tra ngữ cảnh /import giúp biết có nên streaming hoặc giảm parse lặp. Nếu bạn chỉ nhìn Hot Methods, dễ bỏ qua **lời gọi nào** làm tăng nhu cầu xử lý.

### 4.4. Flame graph: chiều rộng không bằng số lần gọi

Trong flame graph CPU sampling:

- Mỗi stack sample đóng góp vào việc tổng hợp chiều rộng của các frame trên đường gọi.
- Một node cha rộng do bao nhiều stack samples; một node lá rộng do xuất hiện thường xuyên ở phần thực thi.
- Độ cao thể hiện độ sâu stack; không phải thời lượng.
- Trục ngang thường là bố cục gộp stack, **không phải dòng thời gian** như timeline event.
- Màu sắc trong nhiều flame graph chỉ hỗ trợ phân biệt/nhóm, **không mặc định là mức cảnh báo hoặc nhiệt độ CPU**.

Nếu có 60% mẫu đi qua Controller.handle và 35% có Parser.parse ở leaf, không thể nói controller mất 60% CPU **ngoài** 35% CPU của parser. Hai phần có quan hệ bao hàm, không được cộng như hai khoản độc lập.

## 5. Cách kiểm tra phép tính theo sample stack cụ thể

Giả sử 20 stack samples, đã gom các stack giống nhau. Mỗi dòng được viết **leaf → root**; tần suất là số samples:

| Tần suất | Stack (leaf → root) |
| ---: | --- |
| 6 | Parser.parse → Service.handle → Thread.run |
| 4 | Sorter.sort → Service.handle → Thread.run |
| 3 | Hash.compute → Cache.lookup → Service.handle → Thread.run |
| 2 | Service.handle → Thread.run |
| 5 | Scheduler.idle → Thread.run |

Kết quả:

| Method | Self samples | Inclusive samples | Giải thích |
| --- | ---: | ---: | --- |
| Parser.parse | 6 | 6 | Chỉ xuất hiện ở leaf |
| Sorter.sort | 4 | 4 | Chỉ xuất hiện ở leaf |
| Hash.compute | 3 | 3 | Chi phí riêng của hash |
| Cache.lookup | 0 | 3 | Chỉ là caller của hash trong mẫu này |
| Service.handle | 2 | 15 | Góp mặt ở 6 + 4 + 3 + 2 samples |
| Scheduler.idle | 5 | 5 | 5 mẫu còn lại ở nhánh khác |
| Thread.run | 0 | 20 | Root của mọi stack được chọn |

**Kiểm tra bảo toàn ở node Service.handle:** self 2 + inclusive của ba nhánh con (6 + 4 + 3) = 15. Nhưng nếu cộng inclusive của Service.handle (15) với inclusive của các con (6 + 4 + 3) bạn đã đếm trùng.

Ví dụ này cố ý dùng **mẫu tổng hợp giả lập**, không phải thời gian CPU thực hay output mặc định của JMC. Với sản phẩm thật, phải biết công cụ đang tính theo mẫu/stack, trọng số, số lượng samples và bộ lọc thread/time window.

## 6. Điểm dễ sai: đệ quy và phương thức xuất hiện nhiều lần

### 6.1. Một method ở hai cấp của cùng stack

Ví dụ recursion:

~~~text
Worker.run()
  -> Factorial.compute(5)
       -> Factorial.compute(4)
            -> Factorial.compute(3)
~~~

Nếu một sample có stack chứa Factorial.compute **ba lần**, khi tổng hợp theo **method identity**, inclusive samples của Factorial.compute thường nên tính **một sample có method đó** (để không vượt quá số samples vì recursion). Nhưng khi hiển thị **call tree theo đường gọi**, ba node Factorial.compute tại ba độ sâu là ba invocation/path khác nhau; cùng sample có thể góp vào inclusive của từng node.

Hai kiểu biểu diễn phục vụ hai mục đích:

- **Method aggregate:** “Method Factorial.compute xuất hiện trong bao nhiêu samples?”. Cần tránh đếm trùng method trong cùng stack nếu định nghĩa inclusive là số samples có method.
- **Call-path/node aggregate:** “Ở độ sâu/lời gọi cụ thể này, có bao nhiêu samples thuộc nhánh?”. Có thể hiển thị nhiều node cùng method, và các node này bao nhau.

Đối chiếu cách tool hiển thị recursion; đừng khẳng định mọi profiler đều dùng công thức tổng hợp giống nhau, đặc biệt khi method-level rows và call-path nodes dùng cách tính khác.

### 6.2. Một method được gọi bởi nhiều cha

~~~text
RequestA.handle() -> JsonParser.parse()
RequestB.handle() -> JsonParser.parse()
~~~

Hot Methods gom JsonParser.parse self samples trên cả RequestA/RequestB. Call Tree tách hai nhánh. Inclusive của RequestA và RequestB chỉ bao những samples thuộc nhánh tương ứng; inclusive của JsonParser.parse trong Hot Methods có thể gom hai tập này. Để quyết định sửa parser hay chỉ tối ưu RequestB, cần xem caller distribution, payload và SLO theo route.

### 6.3. Vòng lặp gọi nhiều lần không bằng “chi phí một lời gọi”

Một vòng lặp gọi decode() 100.000 lần có thể tạo nhiều CPU samples dù mỗi lần decode rẻ. Profiler sampling không tự cho bạn count chính xác hoặc độ dài riêng **mỗi invocation**. Muốn quyết định nên giảm số lời gọi, memoize hay tối ưu body, cần bổ sung invocation count, allocation metrics, benchmark phù hợp và đo với workload thực. “Self 20%” không cho biết decode() được gọi 10 hay 10 triệu lần.

## 7. CPU time khác wall-clock elapsed time

Đây là ranh giới quan trọng nhất khi nói “chi phí qua lời gọi con” trong module CPU/JIT:

- **Wall-clock/elapsed:** thời gian trôi qua từ lúc lời gọi bắt đầu đến kết thúc, có thể gồm CPU running, waiting I/O, locks, sleep, scheduling và tác động thread khác.
- **Thread CPU time:** thời gian CPU thực tế được OS quy cho thread, không bao gồm đa phần thời gian thread blocked/sleeping; chi tiết theo OS/JVM.
- **Process CPU time:** tổng CPU mà các threads trong process tiêu thụ; trong 1 giây wall có thể dùng hơn 1 giây CPU nếu chạy trên nhiều core.
- **JFR execution samples:** các mẫu stack thực thi được ghi theo cấu hình; tỷ lệ mẫu giúp định vị nơi chạy code, **không tự là đồng hồ đo duration chính xác**.

Giả sử trong một request 200 ms:
- 18 ms CPU tính toán trên thread request;
- 160 ms chờ network/DB;
- 22 ms khác (đợi queue, scheduling, serialization trên thread khác hoặc hoạt động xen kẽ).

Một CPU flame graph có thể làm phần 18 ms nổi bật và **không thể hiện trực tiếp** 160 ms chờ. Nếu gán 70% CPU samples cho Parser.parse, điều đó không nghĩa parser gây 70% của 200 ms end-to-end latency.

Ngược lại, trong profiler instrumented wall time, Repository.load có total 160 ms vì chờ I/O, còn self của Socket.read có thể rất lớn theo wall. Hai báo cáo cùng nói “time” nhưng dùng **khác đồng hồ đo**. Luôn ghi đơn vị và nguồn.

### 7.1. Không lấy tổng thời gian con khi các con chạy song song

Nếu một phương thức dispatch hai tasks chạy đồng thời, mỗi task mất 80 ms wall và cha hoàn tất sau 100 ms wall, tổng durations của các con có thể là 160 ms > 100 ms. Công thức “inclusive cha = self + tổng inclusive con” theo **mốc wall-clock không chồng lấp** không còn đúng cho mô hình công việc song song.

Cần phân biệt:
- **Critical-path latency:** nhánh thực thi nối tiếp dài nhất mà người dùng phải chờ.
- **Total CPU work:** tổng CPU trên các tasks/threads; có thể lớn hơn wall duration.
- **Sum of child durations:** lượng công việc gộp, có thể đếm overlap và không phản ánh response time.

Ví dụ StructuredTaskScope, CompletableFuture, executor pools và virtual threads càng cần nhìn trace/context liên kết thay vì tưởng stack của một thread chứa mọi công việc bất đồng bộ. JFR stack của một sampled thread không tự nối các call chains xuyên thread.

### 7.2. Thread state là một bộ lọc quan trọng

HotSpot JFR method profiling theo execution sampling thiên về threads đang thực thi Java code; threads đang sleeping, waiting for lock hoặc blocking I/O có thể không được phản ánh tương xứng trong các event mẫu chạy CPU. Để tìm bottleneck thời gian chờ, hãy xem event chờ/park/monitor/socket/file và distributed traces, không chỉ Hot Methods.

Nếu CPU thấp nhưng p99 cao, **đừng kết luận code Java không có bottleneck** từ một flame graph thưa; ứng dụng có thể chờ pool, DB, network, disk hoặc bị backpressure. Tùy JFR configuration, có thể có NativeMethodSample và các event khác; không gom chúng với ExecutionSample khi chưa hiểu semantics.

## 8. JFR và JMC: biết chắc số liệu bạn đang xem

### 8.1. JFR có thể chứa những nguồn dữ liệu nào?

Một bản ghi có thể chứa:
- jdk.ExecutionSample: snapshots của thread thực thi Java, kèm stack trong phạm vi đã thu.
- jdk.NativeMethodSample: một số snapshots liên quan native code (phạm vi/cách ghi theo JVM).
- jdk.CPULoad và jdk.ThreadCPULoad: góc nhìn sử dụng CPU qua thời gian.
- jdk.ThreadPark, jdk.JavaMonitorEnter, jdk.SocketRead, jdk.FileRead...: sự kiện chờ/I/O **nếu đã bật và vượt threshold**.
- JIT/classloading/compilation/deoptimization events **nếu cấu hình cho phép**, có thể giúp hiểu thời đoạn warm-up.
- GC events: hoạt động GC, đôi khi cần bổ sung GC logs để diễn giải pause/concurrent phases.

Danh sách không có nghĩa file của bạn chứa tất cả. Nhiều event có thresholds, periods, filters và stack trace settings riêng. Nếu không có jdk.ExecutionSample, bạn không thể tạo lại CPU call tree đáng tin chỉ từ tổng jdk.CPULoad.

### 8.2. Đọc đúng nhãn/đơn vị trong JMC

Trong các phiên bản JMC thường có khu vực Code/Hot Methods/Call Tree. Ở từng view:

1. Chọn recording và time range đúng với incident hoặc khoảng tải đại diện.
2. Kiểm tra thread/event filters: service worker, request threads, background jobs, GC/JIT worker nếu được tách biệt.
3. Xem cột **Self** hay **Total**, **Samples** hay **Estimated time**, % theo toàn view hay theo parent.
4. Chú ý số mẫu N, thông báo thiếu dữ liệu và truncated stacks.
5. Với method total cao, mở rộng children; với method self cao, kiểm tra leaf stacks và callers.
6. So với CPU process, thread CPU, RPS, payload và p99; tránh chọn method do traffic peak mà không có regression.
7. Ghi rõ phiên bản JMC, tên view, settings .jfc và khoảng thời gian khi chia sẻ kết quả.

Không phải JMC nào cũng có đúng các nhãn cột hay thuật toán nội suy time giống nhau. Đừng mô tả mỗi số trong cột “Time” như thời gian thực thi hoàn chỉnh của method nếu nguồn chỉ là sampled stacks.

### 8.3. Top-down và bottom-up không phải hai tập chi phí khác

Top-down gom stacks theo prefix caller → callee; bottom-up gom theo hậu tố callee → caller. Cả hai có thể được tạo từ **cùng tập samples**, chỉ khác phép nhóm. Nếu tổng self samples toàn view thay đổi giữa hai tab, kiểm tra filter, stack truncation, grouping, hidden threads hoặc conversion, thay vì mặc định đây là chứng cứ mới.

## 9. JIT inlining và compiled code làm thay đổi cách nhìn

### 9.1. Inlining là gì trong bối cảnh profiler?

JIT có thể **inline** một lời gọi: mã máy của method con được gộp vào code đã biên dịch của caller, giảm overhead gọi hàm và mở ra các tối ưu khác. Cấu trúc **Java source call graph** vẫn có lời gọi logic, nhưng ranh giới machine instructions không nhất thiết còn là một call instruction rõ ràng.

Phụ thuộc profiler/JVM/compiler metadata, stack trace có thể tái tạo **logical inlined frames** ở mức nào đó hoặc trình bày khác với source-level stack. Vì vậy:

- Không kết luận “method B không chạy” chỉ vì không thấy B như một frame riêng trong một view.
- Không kết luận “caller A dùng toàn bộ CPU” nếu B đã inline và công cụ không phân rã được frame như mong muốn.
- Không khẳng định “B self bằng 0” nghĩa thân B thực thi miễn phí; có thể bị gộp vào caller hoặc thiếu mẫu.
- Không tin mỗi sample trỏ chính xác line number khi thông tin ánh xạ compiled code không đầy đủ.

**JIT không làm định nghĩa self/inclusive mất ý nghĩa**, nhưng làm phép quy trách nhiệm từ machine code về từng Java method/line **phụ thuộc cách công cụ thu stack và metadata**.

### 9.2. Warm-up, tiered compilation và deoptimization

Một method có thể chạy interpreter, C1 rồi C2 (tùy HotSpot/compiler flags và điều kiện), được inline, deoptimize hoặc recompile khi profile thay đổi. Điều này ảnh hưởng sample distribution, branch costs và kết quả benchmark.

Khi so hai recordings:

- Có cùng JDK/vendor, JVM flags, collector và trạng thái warm-up chưa?
- Có startup, lazy class loading, JIT compilation, code cache pressure hoặc deoptimization trong một bản mà bản kia không có?
- Có cùng request mix/payload/concurrency, cache state và CPU quota?
- Có đủ thời lượng **steady-state** hoặc đang cố tình điều tra startup?
- Có classloading/compilation events và logs để hỗ trợ giải thích không?

Không sửa logic method dựa trên 10 giây CPU samples trong lúc app đang tải class, rồi ngoại suy kết quả cho steady-state.

### 9.3. Stack depth và giới hạn metadata

Nếu stack quá sâu và ghi bị truncate, một sample có thể thiếu caller ở gần root hoặc thiếu thông tin trên một số frame. Điều này làm inclusive của ancestor thấp hơn thực tế hoặc khiến call tree bị tách thành nhánh “unknown”. Độ sâu stack JFR có thể cấu hình (ví dụ FlightRecorderOptions=stackdepth theo JDK/version), nhưng tăng depth làm tăng chi phí/dung lượng. Kiểm tra JDK help/docs và đo overhead trước khi đổi production settings.

Không nên bổ sung option JIT diagnostic “trên mọi service” chỉ để profile đẹp hơn; một số flags ảnh hưởng compiler metadata, memory hoặc code generation. Chọn công cụ/độ sâu theo giả thuyết và dùng A/B nếu muốn so chính xác.

## 10. Đọc self cao và inclusive cao thành quyết định kỹ thuật

| Self (riêng) | Inclusive (bao gồm) | Cách hiểu bước đầu | Bằng chứng/hành động tiếp theo |
| --- | --- | --- | --- |
| Cao | Cao | Method hoặc node đang thực thi nhiều việc ở thân nó và nhánh nó | Xem CPU samples/lines, vòng lặp, thuật toán, allocation, workload |
| Thấp | Cao | Method thường làm caller/dispatcher, chi phí dồn ở con | Mở Call Tree, tìm con hotspot hay blocking |
| Cao | Thấp | Thường **bất khả thi nếu cùng thước đo, cùng tập samples, cùng phạm vi**, vì inclusive phải ≥ self | Kiểm tra đang so khác thread/time range, units, recursion grouping hoặc columns |
| Thấp | Thấp | Ít được quan sát trong tập samples đã chọn | Có thể không phải ưu tiên CPU; vẫn có thể quan trọng với tail latency/blocked I/O |

Trong profiling của **một call path**, một node total cao/self thấp tự nhiên dẫn bạn xuống con; nhưng “đi xuống cho đến self cao” không đủ nếu mục tiêu là wall-clock latency và con đang chờ network. Hãy phân loại bản chất của con trước khi sửa code.

### 10.1. Mục tiêu giảm inclusive cần can thiệp đúng chỗ

Muốn giảm inclusive của Service.handle, có nhiều lựa chọn khác nhau:
- Giảm self: cải thiện thuật toán chạy trực tiếp trong Service.handle.
- Giảm inclusive child: sửa Parser.parse/Serializer.encode/Repository.query thật sự tốn chi phí.
- Giảm **số lần gọi con**: cache, batch, tránh N+1 queries, gom request, tránh parse lặp.
- Thay đổi đường gọi/parallelism: giảm wall critical path, nhưng có thể tăng total CPU work hoặc tăng áp lực downstream.
- Giảm waiting: giải quyết contention, pool saturation, network/DB latency (không nhất thiết giảm CPU self của method Java).

Cần chọn theo loại chi phí và SLO, không phải chỉ nhìn chữ “Total”.

## 11. Các tình huống dễ đánh lừa người đọc profiler

### 11.1. Controller total 95%, self 1%

Một nhóm nhìn tổng 95% và quyết định viết lại controller. Nhưng call tree cho thấy 70% samples đi qua Serializer.encode và 24% qua Crypto.hash, phần thân controller chỉ 1%. Quyết định tốt hơn là kiểm tra caller-specific CPU, response size, serialization overhead và hashing strategy. Chỉ thay controller orchestration nếu nó gọi con quá nhiều hoặc gọi sai chỗ.

### 11.2. Parser self 40%, nhưng CPU process chỉ 5%

40% **trên tập execution samples nhỏ** không có nghĩa parser lấy 40% năng lực CPU của máy. Trong workload mostly-blocked, ít CPU được sử dụng, parser có thể nổi bật vì các samples khác thưa. Trước khi tối ưu, xem process CPU/quota, sample count, latency traces và nhu cầu tải. Nếu mục tiêu p99 do DB, tối ưu parser có thể không đáng kể.

### 11.3. Framework dispatcher inclusive 100%

Thread.run hoặc framework dispatch thường có total gần 100% của mẫu trong thread được chọn vì nó là ancestor của mọi lần chạy. Đây không phải “framework bug”. Chọn nhánh con theo request/job, tìm leaf hotspots hoặc child wait. Cột self của dispatcher mới cho thấy bản thân nó được sample như leaf bao nhiêu trong cấu hình tương ứng.

### 11.4. Một phương thức recursive xuất hiện ở nhiều node

Method-level Hot Methods ghi inclusive 30 samples, Call Tree có ba node recursion mỗi node inclusive 30/20/10. Không cộng 30+20+10 để nói method tạo 60 samples độc lập. Một sample có thể đi qua các node này. Quyết định có cần tối ưu recursion phải dựa vào số samples self, depth, input size, allocation/stack growth và alternative algorithm.

### 11.5. CPU không cao nhưng request chậm vì chờ

Repository.load total wall time 300 ms, self CPU sampling gần 0. Điều này không mâu thuẫn: thread có thể chờ database/network. Cần JFR socket/file/park/monitor events, distributed tracing và downstream metrics, thay vì tăng CPU hoặc viết lại một vòng lặp Java không liên quan.

### 11.6. Hot method thay đổi sau warm-up

A xuất hiện nóng ở startup do classloading/JIT, B nóng ở steady state do payload parsing. Nếu gộp recording dài vào một chart toàn cục, có thể nhận định sai. Tách thời đoạn và quyết định bạn đang tối ưu cold start hay steady-state throughput.

### 11.7. Flame graph rộng của GC/JIT có bị tính vào CPU request?

JVM có GC threads, compiler threads, service threads và native runtime activity. CPU process tổng bao gồm nhiều thành phần, còn jdk.ExecutionSample có phạm vi khác. Không thể dùng một call tree Java app samples để khẳng định toàn bộ process CPU đã được phân bổ theo methods. Đối chiếu jdk.CPULoad, jdk.ThreadCPULoad, GC logs và metrics runtime trước khi nêu tỷ lệ CPU toàn process.

## 12. Thực hành đọc JFR trên JDK 21

Các lệnh sau là ví dụ cho môi trường có JDK tools, JVM cho phép attach và đường dẫn file ghi/đọc có quyền hợp lệ. Không chạy profiling nặng trên production mà chưa đánh giá chi phí.

### 12.1. Thu recording có execution samples

~~~bash
java -version
jcmd -l
PID=12345          # Thay bằng PID thật của JVM cần điều tra
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" help JFR.start
jcmd "$PID" JFR.start name=cpu_path_probe settings=profile \
  disk=true duration=2m filename=/var/tmp/cpu-path-probe.jfr
~~~

Giải thích:

- settings=profile thường cung cấp method profiling chi tiết hơn default, tùy JDK và cấu hình thực tế; không đảm bảo mọi event đều được bật.
- duration=2m là khoảng **thu** minh họa, không phải lời khuyên thời lượng cố định cho mọi workload.
- filename là đường dẫn từ ngữ cảnh JVM, cần quyền ghi và không gian đủ. Kiểm tra recording thực sự đã kết thúc/được xuất trước khi mở file.
- Để so hai runs, dùng **cùng settings và thời đoạn cùng tải**, có warm-up phù hợp; recording lâu hơn không tự tạo tỷ lệ đúng nếu event settings khác.

### 12.2. Kiểm tra dữ liệu có chứa event cần xem

~~~bash
jfr summary /var/tmp/cpu-path-probe.jfr
jfr metadata /var/tmp/cpu-path-probe.jfr
jfr print --events jdk.ExecutionSample --stack-depth 64 \
  /var/tmp/cpu-path-probe.jfr
~~~

Nếu output quá lớn, hãy xem sample nhỏ trong môi trường có kiểm soát, rồi phân tích bằng JMC hoặc tool có khả năng lọc/time-range. jfr print với stack-depth chỉ **giới hạn phần in ra**, không khôi phục các frame vốn không được lưu ở recording.

Các checks tối thiểu:
- jdk.ExecutionSample count > 0 và stack traces hữu ích.
- Timestamp cover đúng CPU spike/test window.
- Số thread thực thi, loại event và settings/period phù hợp.
- Đã tách CPU computation khỏi blocked/waiting theo yêu cầu bài toán.
- Không đọc event count của một run settings=profile rồi so thẳng với settings=default như thể cùng tốc độ sampling.

Nếu tool phiên bản hiện tại có các predefined views qua jfr view, xem danh sách bằng help trước khi dùng; tên view có thể thay đổi.

### 12.3. Kết hợp CPU và sự kiện chờ

~~~bash
jfr print --events jdk.CPULoad /var/tmp/cpu-path-probe.jfr
jfr print --events jdk.ThreadCPULoad /var/tmp/cpu-path-probe.jfr
jfr print --events jdk.JavaMonitorEnter /var/tmp/cpu-path-probe.jfr
jfr print --events jdk.ThreadPark /var/tmp/cpu-path-probe.jfr
~~~

Lệnh chỉ in event có trong file; không có event không chứng minh không có CPU/chờ. Monitor và park events có thresholds/cấu hình riêng. Với network I/O có thể xem jdk.SocketRead/jdk.SocketWrite nếu recording chứa các events này; cần so với request traces, DB/network metrics và SLA.

### 12.4. Trong JMC: phân tích từng nhánh

1. Chọn recording và time selection trùng đoạn SLO/thử nghiệm.
2. Trong Code/Hot Methods, sắp xếp theo **self samples/cost** nếu view hỗ trợ; xác nhận tên cột và đơn vị.
3. Chọn một method hot và mở Call Tree/Stack Trace; xác định **các caller** gây ra phần lớn samples.
4. Từ entry/endpoint quan trọng, đi top-down theo **inclusive**, mở con cho đến các leaf nóng.
5. Với leaf nóng, phân loại CPU compute hay block/native call; đừng bỏ qua waiting và tải.
6. Thử lọc theo request worker thread/job nếu điều đó khớp mục tiêu; đồng thời kiểm tra các threads khác.
7. Đối chiếu CPU process/quota, p99, RPS, GC, allocation và thời điểm peak.
8. Ghi lại số mẫu, time range, profiler settings và quan hệ parent→child thay vì chỉ chụp ảnh một thanh màu.

Vị trí tab và tên column có thể đổi theo JMC version; trọng tâm là **phép nhóm và semantics**, không phải thao tác nhấp chuột cụ thể.

## 13. Ví dụ Java 17+: tính self và inclusive từ stack samples giả lập

Chương trình độc lập sau minh họa thuật toán **tổng hợp theo method identity**. Nó không đọc .jfr và không tự đo CPU; đầu vào là các nhóm sample stacks được tạo cố định để phép tính dễ kiểm chứng. Các stack ghi từ **leaf đến root**; mỗi stack có số samples tương ứng.

Điểm quan trọng: một frame có thể xuất hiện nhiều lần trong cùng stack vì recursion. Ở aggregation theo method identity, chương trình chỉ cộng **một lần cho mỗi method trên một sample** khi tính inclusive; self lấy frame leaf. Đây là một định nghĩa nhất quán để minh họa, không khẳng định mọi profiler hiển thị recursion y hệt.

Lưu thành file **MethodCostSamples.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public class MethodCostSamples {

    record Sample(long count, String... leafToRoot) {}

    public static void main(String[] args) {
        List<Sample> samples = List.of(
                new Sample(6, "parse", "handle", "run"),
                new Sample(4, "sort", "handle", "run"),
                new Sample(3, "hash", "lookup", "handle", "run"),
                new Sample(2, "handle", "run"),
                new Sample(5, "idle", "run"),
                new Sample(2, "recur", "recur", "run")
        );

        // Giá trị [0] = self samples; [1] = inclusive samples.
        Map<String, long[]> counts = new HashMap<>();
        long total = 0;

        for (Sample sample : samples) {
            total += sample.count();
            String[] stack = sample.leafToRoot();
            if (stack.length == 0) {
                continue;
            }

            counts.computeIfAbsent(stack[0], key -> new long[2])[0]
                    += sample.count();

            // Deduplicate cùng method trên một stack (ví dụ recursion).
            Set<String> present = new HashSet<>();
            for (String method : stack) {
                if (present.add(method)) {
                    counts.computeIfAbsent(method, key -> new long[2])[1]
                            += sample.count();
                }
            }
        }

        System.out.println("samples=" + total);
        for (String method :
                List.of("handle", "parse", "lookup", "recur", "run")) {
            long[] pair = counts.get(method);
            System.out.printf(
                    Locale.ROOT,
                    "%s: self=%d, inclusive=%d%n",
                    method, pair[0], pair[1]);
        }
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac MethodCostSamples.java
java MethodCostSamples
~~~

Stdout xác định chính xác bởi đầu vào cố định:

~~~text
samples=22
handle: self=2, inclusive=15
parse: self=6, inclusive=6
lookup: self=0, inclusive=3
recur: self=2, inclusive=2
run: self=0, inclusive=22
~~~

Giải thích phép tính:
- 6 + 4 + 3 + 2 + 5 + 2 = 22 mẫu.
- handle ở 6 + 4 + 3 + 2 = 15 mẫu; là leaf ở đúng 2 mẫu.
- lookup xuất hiện trên 3 mẫu có hash ở leaf; self của lookup bằng 0.
- recur có hai frame cùng tên trên 2 mẫu; inclusive theo method identity là **2**, không phải 4. Call tree path vẫn có thể cho thấy hai node recur lồng nhau.
- run xuất hiện ở mọi stack: inclusive 22 dù self 0.

Dù có 22 samples, tổng inclusive của tất cả methods trên mọi dòng sẽ lớn hơn 22 do **cùng sample góp cho nhiều ancestors**. Đó là đặc điểm của số liệu call stack, không phải phép đo sai. Chương trình không suy ra wall time, CPU nanoseconds hay số lần method được gọi trong ứng dụng thật.

### 13.1. Nếu muốn tổng hợp theo từng node call tree

Thay vì map theo tên method, phải dùng **đường gọi đầy đủ** (ví dụ run→handle→lookup) làm key cho node. Một method có thể xuất hiện ở nhiều vị trí; mỗi vị trí có self/inclusive riêng. Với recursion, hai frame recur cùng tên là hai node khác nhau trên một đường. Tổng hợp theo path cần giữ identity của node chứ không chỉ deduplicate tên method.

Cần tránh biến bài toán path-level thành method-level bằng cách cộng nhầm các hàng đã bao hàm nhau. Muốn biến samples thành estimated CPU, cần hiểu công cụ, sampling period/weighting và giới hạn điều tra, không chỉ lấy số mẫu nhân một hằng số tùy ý.

## 14. Ví dụ quyết định: tối ưu caller hay callee?

Giả sử trong 10 phút peak load:
- Service.handle xuất hiện trong 60% execution samples và chỉ 2% samples ở leaf;
- Json.encode nằm dưới Service.handle với 35% self samples;
- Cache.lookup chỉ có 2% self nhưng 20% inclusive do Hash.compute;
- process CPU gần quota, RPS/payload ổn định và p99 tăng.

**Cách đọc:**
1. Service.handle inclusive cao: chưa chứng minh nó tự chậm. Mở rộng children.
2. Json.encode self 35%: kiểm tra type/size payload, serialization hot path, allocations và có thể giảm serialization lặp.
3. Cache.lookup inclusive 20% nhưng self 2%: đi tiếp tới Hash.compute và kiểm tra key/data volume, concurrency và cache design.
4. Xác nhận CPU quota/throttling: nếu quá tải CPU, tối ưu compute hoặc scale hợp lý là giả thuyết mạnh. Nếu CPU không cao, tìm I/O/wait.
5. Chạy benchmark so sánh có kiểm soát, đo throughput/p99/CPU và cùng sampling settings.
6. Không cộng 60 + 35 + 20 thành 115% CPU: các tập samples chồng lấp trong call paths.

Kết luận điều tra nên là **“nhánh Service.handle chứa phần lớn samples; phần self nổi bật nằm ở Json.encode và Hash.compute”**, chưa phải **“Service.handle đã được chứng minh gây toàn bộ p99”**.

## 15. Từ số mẫu tới cơ hội tối ưu: bằng chứng bổ sung

### 15.1. CPU bound

Khi process CPU cao, worker threads đang chạy, sample counts đủ và hot leaf method phù hợp:
- Xem thuật toán và độ phức tạp theo kích thước input.
- Kiểm tra boxing, regex, collections, compression, serialization, repeated parsing.
- Kiểm tra JIT warm-up, intrinsics/inlining, allocations và code path khác nhau giữa inputs.
- Dùng JMH hoặc benchmark phù hợp cho micro-level; end-to-end load test để xác nhận cải thiện thực.

**Lưu ý:** một microbenchmark nhanh hơn không đảm bảo service p99 tốt hơn khi bottleneck là network, DB hay queue.

### 15.2. Waiting / I/O bound

Khi method inclusive wall cao nhưng CPU self thấp:
- Kiểm tra socket/file/lock/park events và thread dumps.
- So traces với database/downstream latency, connection pool, rate limits và retries.
- Tìm synchronous fan-out, N+1 calls, timeout/retry và backlog.
- Ưu tiên giảm số roundtrips, bounded concurrency, caching đúng vòng đời hoặc tối ưu dependency.

Thay đổi parallelism có thể giảm wall time nhưng tăng total CPU và pressure. Đo cả throughput, error rate, resource usage và downstream SLO.

### 15.3. Allocation/GC bound

Khi nhiều samples ở allocation-heavy code, cần phân biệt:
- Method tạo nhiều objects nhưng được GC nhanh và không gây pressure đáng kể.
- Method tạo nhiều allocations làm tăng GC CPU/pause/throughput cost.
- Object được giữ lâu làm tăng live set/retention.

Dùng allocation profile, GC events/logs, heap post-GC trend và workload normalization. **Self CPU samples cao không chứng minh memory leak**; object retention cần bằng chứng riêng.

## 16. Thiết kế phép đo đáng tin

### 16.1. Baseline và candidate phải so cùng điều kiện

Ghi lại:
- JDK/vendor, JVM flags, GC, JFR settings, sampling interval/stack depth;
- CPU/memory limits, số replicas/cores, host contention và throttling;
- Build version, cache/warm-up state, thread pool và dependency behavior;
- Requests/s, request mix, payload size, batch volume, concurrency;
- Duration, exact time window, samples count, CPU, throughput, p95/p99, error rate.

Một bản ghi 30 giây low traffic và một bản ghi 10 phút peak không nên dùng để kết luận “self share tăng 2 lần” nếu số samples quá nhỏ hoặc mix công việc khác. Normalize theo requests/bytes/jobs khi phù hợp và luôn xem **mức tác động tuyệt đối**.

### 16.2. Kiểm tra thay đổi ở cả hai thang đo

Nếu đã tối ưu Hash.compute:
- **Cơ chế:** self samples/định lượng CPU của Hash.compute giảm ở workload tương đương?
- **Hệ thống:** process CPU/RPS, throughput/p99, error rate có cải thiện không?
- **Giá phải trả:** memory, allocations, GC, thread contention hoặc downstream calls có tăng không?
- **Tính lặp lại:** kết quả ổn qua nhiều runs, không chỉ một lần khác thường?

Nếu self share giảm chỉ vì tổng CPU samples ở những methods khác tăng, có thể không hề giảm CPU thực. Cần đánh giá absolute process CPU hoặc công việc trên mỗi request, thay vì chỉ một phần trăm tương đối.

### 16.3. Ước lượng lợi ích và giới hạn Amdahl

Nếu một phần code chiếm 20% CPU công việc hiện tại và bạn làm nó nhanh gấp 2, giới hạn lợi ích **trong mô hình tuần tự, CPU-bound và workload không đổi** là:

~~~text
Speedup <= 1 / ((1 - 0.20) + (0.20 / 2))
        = 1 / 0.90
        ≈ 1.11 lần
~~~

Con số 1,11 không có nghĩa p99 toàn hệ thống chắc chắn cải thiện 11%: hệ thống có concurrency, waiting, CPU quotas, caches, JIT, downstream bottlenecks và tail latency. Đặc biệt, dùng **inclusive share của caller** làm phần việc có thể tăng tốc độc lập thường thổi phồng lợi ích vì nhiều children không bị tác động bởi thay đổi.

## 17. Bốn sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai | Sửa cách đọc |
| --- | --- | --- |
| “Total của handler 90%, phải tối ưu thân handler.” | Handler bao toàn nhánh; self có thể thấp | Mở rộng children và xác định CPU/wait bottleneck |
| “Self method B là 30 ms vì có 30 samples.” | Sample count không là đồng hồ đo ms chính xác | Giữ đơn vị samples; đối chiếu sampling/CPU metrics |
| “Cộng tất cả total của các methods = tổng thời gian CPU.” | Parent/child bao nhau; recursion/grouping đếm trùng | Tổng theo các vùng không chồng lấp hoặc dùng self với cùng phạm vi |
| “Không thấy method sau JIT nghĩa method không chạy.” | Inlining, stack reconstruction, filter và sample bias | Kiểm tra compiled frames, JVM/JIT/recording settings |

Các sai lầm khác:

- So cột % trong một node với % toàn file nhưng không đọc denominator.
- So Hot Methods theo method identity với Call Tree theo path identity.
- Gán p99 wall latency cho execution samples mà không kiểm tra I/O, locks, queue và GC.
- Kết luận self=0 nghĩa method vô dụng hoặc không có work; method có thể chỉ gọi con hoặc bị ảnh hưởng cách attribution.
- Suy ra invocation count từ sample count.
- Gộp threads khác vai trò hoặc startup với steady-state rồi kết luận hotspot.
- Bỏ qua overload, lambda synthetic methods, dynamic proxies, classloader và recursion khi nhóm theo tên.
- Dựa vào ảnh flame graph không có time window, sample count, settings và CPU process metrics.
- Tối ưu phần self rất nhỏ trong khi phần inclusive chủ yếu là downstream wait.
- So recordings ở hai JDK/profile settings khác nhau mà không đánh giá sampling và JIT differences.

## 18. Checklist trước khi kết luận

- [ ] Tôi xác định data source: instrumented wall time, thread CPU time, process CPU hay JFR execution samples.
- [ ] Tôi hiểu self là chi phí quy cho thân method/node, inclusive là chi phí bao cả các lời gọi con trong scope tương ứng.
- [ ] Tôi biết đang xem Hot Methods theo method identity hay Call Tree theo call path.
- [ ] Tôi không cộng inclusive của cha và con thành một tổng CPU/thời gian mới.
- [ ] Tôi đã xem recursion và method được gọi từ nhiều callers.
- [ ] Tôi kiểm tra số samples, event settings, threshold, stack depth, thread và time filters.
- [ ] Tôi kiểm tra các hạn chế của JIT inlining, compilation, warm-up và missing frames khi cần.
- [ ] Tôi phân biệt CPU computation với blocking/waiting và latency end-to-end.
- [ ] Tôi đối chiếu method hotspots với process CPU, CPU quota/throttling, GC, RPS, p99 và workload.
- [ ] Với inclusive cao/self thấp, tôi đã mở con và tìm nơi thực sự tập trung chi phí.
- [ ] Với self cao, tôi đã kiểm tra thuật toán, invocation count và mức lợi ích thực tế có thể đạt.
- [ ] Tôi có giả thuyết cạnh tranh, benchmark/load test tương đương, guardrails và rollback.
- [ ] Kết luận ghi đúng mức chắc chắn: quan sát sample ≠ đo CPU time chính xác ≠ root cause đã được chứng minh.

## 19. Kết luận

Hai con số tự bổ sung nhau:

**Self/exclusive** giúp biết code đang được quy trách nhiệm trực tiếp ở method nào. **Inclusive/total** giúp biết đường gọi nào đang bao phần lớn chi phí, để tiếp tục lần xuống các methods con hoặc lần ngược callers.

Đối với JFR method profiling, phần lớn kết quả từ Call Tree/Hot Methods dựa trên **sampled stacks**, vì vậy ưu tiên nói “mẫu xuất hiện ở đâu” trước khi chuyển thành tuyên bố “mất bao nhiêu mili-giây”. CPU samples không tự giải thích thời gian chờ network/lock hoặc tail latency; JIT inlining và stack reconstruction cũng có thể tác động tới cách các method được hiển thị.

Quy trình điều tra đáng tin:

**Xác nhận loại metric → chọn đúng thread và time window → xem self/inclusive → mở call path → xác định CPU hoặc waiting → đối chiếu JFR/OS/APM và tải → thử một thay đổi có kiểm soát → đo lại SLO.**

### Tài liệu tham khảo

- Oracle Java 17 — Troubleshoot Performance Issues Using JFR, phần Code Execution Performance/Call Tree: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle JDK 21 — jfr command (summary, metadata, print, view): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle JDK 21 — jcmd JFR.start/JFR.check/VM.flags: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java SE 21 — Java Flight Recorder API/settings: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- OpenJDK JDK Mission Control project: https://github.com/openjdk/jmc
