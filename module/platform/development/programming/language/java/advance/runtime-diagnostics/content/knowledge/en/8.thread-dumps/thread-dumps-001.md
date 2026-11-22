# 8.1 Thread dump cung cấp ảnh chụp gì và những gì không thể suy ra từ một ảnh

> **Java Advance – runtime-diagnostics** · **8. Thread dump**

## 1. Thread dump là ảnh chụp, không phải bản ghi toàn bộ diễn biến

Khi Java service treo, request chậm, CPU cao hoặc pool không còn nhận việc, **thread dump** là một trong những nguồn bằng chứng nhanh nhất. Một thread dump có thể hiển thị những thread hiện tồn tại, trạng thái JVM quan sát được của chúng, một phần hoặc toàn bộ **call stack** tại thời điểm thu thập và — tùy công cụ, VM, tùy chọn — thông tin monitor lock, ownable synchronizer, lock owner, deadlock hoặc metadata bổ sung.

Tuy nhiên, một dump **không phải video quay quá trình thực thi**. Nó không kể được thread đã ở trạng thái đó bao lâu, trước đó đã đi qua những bước nào, sẽ thoát ở thời điểm nào, đã dùng bao nhiêu CPU trong một khoảng lịch sử hay sự kiện nào *gây ra* lỗi. Nếu hình ảnh cho thấy một thread ở *WAITING*, điều đó có thể là **pool worker đang nghỉ đúng thiết kế**, cũng có thể là ứng dụng chưa nhận được tín hiệu cần thiết; ảnh đơn lẻ thường chưa phân biệt được.

Vì vậy câu hỏi trung tâm của bài là:

> **Ta được quyền kết luận điều gì ngay từ một ảnh thread dump, và điều gì vẫn chỉ là giả thuyết cần thêm bằng chứng?**

Sau bài này, bạn cần có thể:

1. Giải thích thời điểm chụp, phạm vi thu thập và ý nghĩa của Java Thread.State.
2. Đọc thread name, stack frame, lock identity/owner, monitor và ownable synchronizer trong output thường gặp.
3. Phân biệt *RUNNABLE* với “đang tiêu CPU”, *WAITING* với “bị treo”, *BLOCKED* với “mọi loại chờ”.
4. Nhận diện dấu hiệu đáng điều tra về contention/deadlock mà không tự suy ra root cause từ một trạng thái.
5. Biết vì sao một dump **không thể** xác lập duration, frequency, tiến trình thay đổi, CPU profile, throughput, p95/p99 hay mối quan hệ nhân quả.
6. Sử dụng các ảnh liên tiếp, JVM metrics, OS metrics, app logs, traces và JFR để kiểm chứng giả thuyết.
7. Hiểu giới hạn quan sát platform threads so với virtual threads ở các JDK khác nhau.
8. Thực hành một ví dụ Java 17+ in ra snapshot ThreadInfo có trạng thái kiểm chứng được.

## 2. Thread dump cho thấy gì?

Mỗi công cụ và JVM implementation có thể tạo định dạng khác nhau. Với HotSpot, phần thông tin điển hình gồm:

| Thành phần | Quan sát trực tiếp được | Điều **không tự suy ra được** |
| --- | --- | --- |
| Tên thread | Tên khi snapshot, ví dụ *http-nio-worker-42* | Tên luôn đại diện duy nhất cho request hoặc vai trò thực tế |
| Thread ID/metadata | Một hoặc nhiều ID, ưu tiên, daemon status, OS native ID nếu format hỗ trợ | Mọi ID đều cùng namespace hoặc có thể so trực tiếp giữa JVM |
| Java Thread.State | *RUNNABLE*, *BLOCKED*, *WAITING*, *TIMED_WAITING*… | Thời gian đã duy trì trạng thái hoặc thread đang “tốt/xấu” |
| Stack frames | Phương thức, class, đôi khi file/line hiện có trên stack | Toàn bộ lịch sử call, mọi exception đã xảy ra, thời gian của mỗi frame |
| Monitor info | Monitor đang giữ hoặc đang chờ nếu công cụ hỗ trợ | Ai giữ lock trong **quá khứ**, mức contention lịch sử, lock có lỗi |
| Ownable synchronizers | Một số khóa thuộc *java.util.concurrent* khi thu với tùy chọn thích hợp | Tất cả điều kiện chờ và mọi khóa đồng bộ trong hệ thống |
| Deadlock report | Chu trình khóa **được thuật toán/công cụ nhận diện** | Không có ứng dụng-level deadlock/livelock hoặc distributed deadlock khác |
| Thời gian chụp | Mốc capture/VM version/PID, nếu output hoặc metadata bên ngoài ghi | Tất cả thread được lấy ở cùng một nano-giây hoặc sự kiện trước đó |
| Trạng thái native/top frame | Có thể gợi ý chờ I/O, native call hoặc CPU hotspot | Tỷ lệ CPU sử dụng thực tế trong cửa sổ dài |

Cần kiểm tra **công cụ có thực sự xuất từng trường không**. Không phải file tên *thread-dump.txt* nào cũng chứa lock owners, Java state, JNI frames hoặc mọi virtual thread. Tài liệu API, version JVM và lệnh thu thập quan trọng không kém nội dung file.

### 2.1 Một snapshot không nhất thiết nguyên tử toàn JVM

Một thread dump do một số cơ chế HotSpot truyền thống có thể đi kèm xử lý ở VM safepoint, còn dạng *Thread.dump_to_file* dành cho virtual threads trên JDK 21 được tài liệu mô tả là **không nhất quán toàn cục tại một thời điểm duy nhất**. Nó thu nhiều thread theo quá trình duyệt; thread có thể tạo mới, chuyển trạng thái hoặc kết thúc trong lúc thu thập.

Ngay cả nếu một cách thu có tính nhất quán hơn, nó vẫn chỉ đại diện cho **một lần quan sát**. Không có lịch sử trước/sau chỉ nhờ một file. Khi chẩn đoán, phải ghi cả **thời điểm bắt đầu/kết thúc thu nếu có**, JVM instance, công cụ/version và cách capture.

## 3. Cách đọc một đoạn thread dump điển hình

Đây là **dữ liệu minh họa**, không phải output cố định của mọi JDK và không phải chứng cứ production:

~~~text
"checkout-worker-42" #42 prio=5 os_prio=0 tid=0x00007f0011223300 nid=0x2a
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.Inventory.reserve(Inventory.java:73)
    - waiting to lock <0x000000071234abcd> (a java.lang.Object)
    at com.example.CheckoutService.placeOrder(CheckoutService.java:120)

"pool-worker-7" #51 prio=5 os_prio=0 tid=0x00007f0011224400 nid=0x33
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
    at java.util.concurrent.LinkedBlockingQueue.take(LinkedBlockingQueue.java:...)

"timer-1" #60 prio=5 os_prio=0 tid=0x00007f0011225500 nid=0x3c
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(Native Method)
    at com.example.RetryTicker.pause(RetryTicker.java:18)
~~~

### 3.1 Thread name không phải request ID

Một worker thường xử lý nhiều request trong vòng đời. Tên *checkout-worker-42* có thể được gán khi thread khởi tạo, còn hiện tại nó đang chạy request nào chỉ biết nếu có thêm ngữ cảnh từ thread-local, log, tracing hoặc instrumentation được thiết kế phù hợp. Thread name có thể bị thay đổi hoặc trùng nhau.

Không coi *checkout-worker-42* là request số 42. Nếu cần liên kết với requestId/traceId, hãy tạo correlation ID trong application logging/tracing đúng chính sách; một thread dump thường **không tự chứa** ID nghiệp vụ.

### 3.2 tid, nid, Java thread ID và PID là các định danh khác nhau

Trong một số output HotSpot:

- **tid=0x...** có thể là con trỏ/địa chỉ định danh thread nội bộ của VM, **không nhất thiết là Thread.getId()**.
- **nid=0x...** thường là native thread ID của hệ điều hành, biểu diễn hex; khi đối chiếu công cụ OS phải hiểu namespace/format.
- **#42** trong thread header cũng không được mặc định là PID hay request ID.
- **PID** là process JVM; nhiều native threads thuộc cùng PID, và PID trong container có thể khác PID host.

Format thay đổi theo JDK/OS/công cụ. Chỉ quy đổi native ID sang decimal khi bạn chắc chắn trường đó là **nid của đúng OS thread**. Java virtual thread không có ánh xạ một-một cố định tới native OS thread, vì nó có thể được mount/unmount trên các carrier threads.

### 3.3 Stack frame là vị trí trong ngăn xếp, không phải mốc thời gian

Một frame như:

~~~text
at com.example.Inventory.reserve(Inventory.java:73)
~~~

cho thấy đoạn method nằm trên stack tại ảnh thu thập. Nó **không** nói rằng dòng 73 vừa xảy ra lỗi, thread đã ở dòng 73 suốt 30 giây, code đó dùng nhiều CPU hoặc frame ấy tạo lock. Những frame bên dưới cho biết chuỗi lời gọi, không phải thời gian spent của từng frame.

Frame có thể bị rút gọn do giới hạn depth, tối ưu JIT/inlining, native call, công cụ thu thập hoặc thiếu debug line number. **Unknown Source** không tự chỉ ra code bị lỗi; có thể build không có line metadata.

### 3.4 waiting to lock và locked không giống nhau

- **waiting to lock**: thread hiện đang chờ giành một object monitor để vào *synchronized*.
- **locked**: thread đang giữ monitor tương ứng tại vị trí quan sát.
- Danh sách **Locked ownable synchronizers** (khi có) liên quan các kiểu khóa như *ReentrantLock*, không đồng nhất với toàn bộ *synchronized monitors*.
- *parking to wait for* thường xuất hiện với *LockSupport* và các cấu trúc *java.util.concurrent*; phải hiểu ngữ cảnh queue/condition.

Một thread có thể có *WAITING (parking)* trong queue của thread pool và hoàn toàn khỏe mạnh; thiếu việc để làm là chuyện bình thường. Muốn nói “lock contention gây request delay” cần chứng minh có worker đang chờ **lock liên quan đường request**, tỷ lệ chờ đáng kể và thời gian trùng sự cố.

## 4. Sáu Java Thread.State và giới hạn diễn giải

Các trạng thái sau là **trạng thái JVM** theo API *java.lang.Thread.State*, không phải trực tiếp trạng thái OS scheduler. Trong dump của các **live** threads, *NEW* và *TERMINATED* thường không hiện như một live thread bình thường vì chưa chạy/đã kết thúc.

| State | Nghĩa chuẩn | Tình huống thường thấy | **Không được kết luận chỉ từ state** |
| --- | --- | --- | --- |
| **NEW** | Thread đã được tạo nhưng chưa start | Object Thread mới | Có thread này trong danh sách live dump; thread leak |
| **RUNNABLE** | Thread có thể thực thi trong JVM, bao gồm trường hợp chờ tài nguyên OS | Java code chạy, I/O native, thread sẵn sàng CPU | “Đang chiếm 100% CPU” |
| **BLOCKED** | Chờ một **object monitor** để vào/re-enter *synchronized* | Một thread khác đang giữ cùng monitor | “Deadlock chắc chắn” hoặc “mọi loại lock wait đều BLOCKED” |
| **WAITING** | Chờ không có timeout được chỉ định | *Object.wait()*, *Thread.join()*, *LockSupport.park()*, queue take | “Treo vĩnh viễn” |
| **TIMED_WAITING** | Chờ với thời hạn | *Thread.sleep()*, timed wait/join/park | “Timeout đã xảy ra” hoặc “không hữu ích” |
| **TERMINATED** | Thread đã hoàn tất | Thread object sau khi kết thúc | Có thể đọc đầy đủ stack đang chạy từ live dump |

### 4.1 RUNNABLE **không bằng** đang tiêu CPU

Một thread ở *RUNNABLE* có thể đang:

- Thực thi Java bytecode/JIT.
- Đợi được OS cấp CPU.
- Ở native I/O call mà JVM state vẫn báo RUNNABLE (ví dụ một số dạng socket/native polling).
- Trong vòng lặp thực sự tiêu CPU.

Nếu có 50 thread RUNNABLE trong một ảnh, điều đó **không chứng minh** process đang dùng 50 cores hay 5000% CPU. Muốn tìm CPU hotspot, cần **OS per-thread CPU delta** (đúng native ID), **JFR execution samples**, async profiler hoặc metrics đối chiếu thời gian. Số lượng *RUNNABLE* là manh mối để ưu tiên điều tra, không phải định lượng CPU.

Thậm chí một frame nằm ở phương thức tính toán trong một ảnh chưa đủ bằng chứng đó là hotspot. Nó có thể xuất hiện do lấy mẫu đúng lúc thread đi qua phương thức trong vài microsecond.

### 4.2 BLOCKED chỉ mô tả monitor acquisition

*BLOCKED* là chờ object monitor gắn với *synchronized*. Một thread tranh *java.util.concurrent.locks.ReentrantLock* có thể đang **WAITING/parking**, không nhất thiết *BLOCKED*, vì cơ chế lock khác nhau.

Ví dụ:

~~~java
// Mảnh mã minh họa, không độc lập.
synchronized (sharedMonitor) {
    // Một thread khác muốn vào synchronized(sharedMonitor)
    // có thể hiện BLOCKED.
}
~~~

Điều đáng điều tra nếu có nhiều request threads cùng *BLOCKED* một monitor: ai giữ monitor đó, người giữ có đang làm I/O lâu hay chờ một lock khác, mức độ lặp lại qua các lần chụp, và liệu thread này có nằm trong critical path request không.

**Một ảnh BLOCKED chưa có duration.** Chỉ cần hai thread cùng vào một monitor trong đúng microsecond chụp là có thể thấy BLOCKED dù hệ thống khỏe.

### 4.3 WAITING có thể hoàn toàn là trạng thái “rảnh”

Các pool workers thường chờ task trong *BlockingQueue.take()* hoặc *LockSupport.park()*. Thread đang *WAITING* tại queue không nhất thiết bị mất tín hiệu. Nếu queue trống, đó chính là hành vi thiết kế.

Ngược lại, một thread quan trọng chờ mãi ở *CountDownLatch.await()* có thể là triệu chứng nếu sự kiện nhả latch không bao giờ tới; nhưng dump **không nói ai phải countDown**, có quên signal không, hoặc bao lâu đã chờ. Cần xem code, application logs và lịch sử.

### 4.4 TIMED_WAITING không đồng nghĩa timeout

*Thread.sleep(1000)* đặt thread vào *TIMED_WAITING* trong khoảng ngủ; hiện trạng này không nói đã ngủ bao lâu. Với chờ network có timeout, cần xem logic cụ thể và trace để biết timeout đã xảy ra hay còn đang chờ.

Không coi mọi thread sleeping là vô dụng. Timer, backoff, retry scheduler hoặc heartbeat có thể chờ đúng lịch. Một thread sleeping ở thời điểm chụp có thể hoạt động liên tục trong các khoảng khác.

### 4.5 Trạng thái Java không tương đương trạng thái hệ điều hành

Java Thread.State không cung cấp trực tiếp:

- OS scheduling state chính xác.
- Tỷ lệ CPU đã dùng.
- Mức I/O latency hoặc network packet state.
- Memory allocation rate của thread.
- Phân bố thời gian runnable/waiting theo lịch sử.

Cần OS tools/JFR/metrics nếu muốn dữ liệu này. Một vài dump HotSpot có thêm trường *cpu=...* hoặc *elapsed=...* ở header, nhưng **đó là dữ liệu do phiên bản và công cụ cung cấp**, không phải một thuộc tính luôn có của Java Thread.State. Nếu thấy *cpu=*, kiểm tra đơn vị và ý nghĩa; cumulative CPU time **không phải CPU% tức thời**.

## 5. Thread dump có thể gợi ý điều gì đáng tin?

Cần tách **quan sát** (evidence) khỏi **giả thuyết** (hypothesis) và **kết luận nhân quả**.

| Dữ liệu trong một dump | Phát biểu có thể chấp nhận | Suy luận vượt bằng chứng |
| --- | --- | --- |
| Thread A hiện BLOCKED trên monitor X | Tại thời điểm quan sát, A đang chờ monitor X | A đã chờ X hàng phút |
| Thread B hiện giữ monitor X | B được công cụ ghi đang sở hữu X | B giữ X từ đầu incident hoặc cố ý không nhả |
| A WAITING ở queue take | A đang chờ task/điều kiện theo stack | Pool bị deadlock |
| Nhiều worker cùng stack frame | Nhiều thread được bắt gặp ở cùng đường code | Phương thức ấy là CPU hotspot |
| Một thread RUNNABLE trong socket read | JVM ghi RUNNABLE và stack liên quan I/O | Thread đang ăn CPU |
| Stack ở *Thread.sleep* | Thread đang ngủ có thời hạn ở thời điểm chụp | Thread đã timeout hoặc sleep quá lâu |
| Output báo **Found one Java-level deadlock** | Công cụ đã nhận diện chu trình deadlock theo khả năng detector | Đây là tất cả vấn đề đồng bộ trong process |
| Dump không báo deadlock | Detector không phát hiện chu trình thuộc phạm vi hỗ trợ | Không có lock starvation/livelock/distributed deadlock |
| ThreadInfo lock owner là “main” | Monitor đang được main giữ khi quan sát | main là root cause của latency production |
| Không thấy thread X | X không có trong phạm vi/đúng lúc thu hoặc đã kết thúc | X chưa từng tồn tại hoặc request chưa bao giờ chạy |
| 500 threads có mặt | Ít nhất phạm vi output có nhiều thread | 500 requests đang xử lý cùng lúc |
| Thread name chứa “payment” | Name đó được gán cho thread | Frame chắc chắn là payment request của khách hàng cụ thể |

**Từ một ảnh, kết luận đáng tin phải dùng ngôn ngữ có thời điểm:** “Tại thời điểm chụp, các worker này đang…” thay vì “service luôn…”, “nhiều phút qua…” hoặc “do… nên…”.

## 6. Deadlock, contention, starvation và livelock: vì sao không đánh đồng?

### 6.1 Deadlock là quan hệ chu trình, không chỉ có thread BLOCKED

Một **monitor deadlock** điển hình:

~~~text
Thread A giữ monitor X, đang chờ monitor Y
Thread B giữ monitor Y, đang chờ monitor X
                        |
                        v
                  chu trình chờ nhau
~~~

Nếu công cụ có **deadlock detector** và in thông báo chu trình, đó là bằng chứng mạnh của deadlock thuộc phạm vi detector. Nếu bạn chỉ nhìn thấy hai thread BLOCKED rời rạc mà không có owner/graph, chưa được khẳng định deadlock.

**Không thấy deadlock report chưa loại trừ mọi deadlock.** Detector có thể chỉ kiểm tra monitor/ownable synchronizer trong JVM; không nhận diện “chờ phản hồi từ service B trong khi B chờ service A”, các condition/latch protocol không tạo lock cycle, thread starvation hay deadlock liên quan virtual threads tùy API/version.

### 6.2 Contention có thể là bình thường

Contention là nhiều thread tranh một tài nguyên. Một *synchronized* ngắn đôi khi khiến thread BLOCKED rất ngắn mà không ảnh hưởng service. Cần xem:

- Bao nhiêu thread bị ảnh hưởng?
- Chờ bao lâu và với tỷ lệ nào?
- Có lặp lại ở cùng lock qua các ảnh?
- Owner làm gì khi giữ lock?
- Request latency, queue length, throughput có biến động đồng thời không?

Một ảnh có *BLOCKED* là **tín hiệu**, không phải phép đo mức contention theo thời gian.

### 6.3 Starvation có thể không có lock cycle

**Thread pool starvation**: tất cả worker bận/chờ tác vụ con, hàng đợi không được xử lý. Dump có thể thấy workers ở *Future.get()* hoặc queue/condition nhưng chưa đủ chứng minh. Cần queue depth, active thread count, task submission/completion rate và code dependency giữa tasks.

**Livelock**: các thread liên tục thay đổi trạng thái/hoạt động nhưng không đạt tiến triển nghiệp vụ. Một dump có thể cho RUNNABLE; cần nhiều mẫu + progress counters/traces để xác lập “có hoạt động nhưng không tiến triển”.

### 6.4 “Không tìm thấy Java-level deadlock” không có nghĩa “không treo”

Ứng dụng có thể treo vì:

- Deadlock ở database/distributed resource ngoài JVM.
- Socket read không có timeout.
- Task phụ thuộc một callback không xảy ra.
- Thread pool không có worker sẵn vì nested blocking.
- Cạn connection pool hoặc semaphore permits.
- JVM/OS chịu CPU throttling hoặc resource starvation.

Những trường hợp này không nhất thiết tạo một chu trình monitor bị detector nhận diện. Đừng chấm dứt điều tra chỉ dựa vào một dòng “No deadlocks found”.

## 7. Một ảnh **không thể** trả lời những câu hỏi theo thời gian

### 7.1 Không có “đã chờ bao lâu” từ state/stack thuần túy

Một dòng *WAITING* chỉ mô tả **đang chờ**. Dù thread name giống nhau, nếu không có thông tin thời gian độc lập, bạn không biết nó bắt đầu chờ lúc nào. Dữ liệu *elapsed* ở header một số HotSpot builds thường phản ánh tuổi đời thread, **không phải thời gian ở state hiện tại**.

Nếu thấy thread đã sống 3 giờ và đang BLOCKED, không được nói “nó bị BLOCKED 3 giờ”. Thread có thể vừa bị BLOCKED trước lúc chụp 1 ms.

### 7.2 Không có “bao nhiêu lần” từ một stack

Một ảnh chụp ở *cache.get()* không cho biết method được gọi 10 lần hay 10 triệu lần. Nó không chứa frequency, throughput, invocation counter hoặc time series. JFR method profiling, application metrics và sampling profiler phù hợp hơn để xác định phân bố thời gian thực thi.

### 7.3 Không có p95/p99 hoặc phân bố độ trễ

Thread dump cho biết trạng thái thread, không phải histogram request duration. Muốn biết p99 latency, cần recording của request timings và tính percentile từ một cửa sổ đủ mẫu. *300 threads WAITING* không thể quy ra p99 = 300 ms.

### 7.4 Không tự chứng minh một hàm dùng CPU cao

Một stack frame “hot” trong snapshot có thể do:

- Một method thật sự chạy lâu.
- Một method chạy rất nhanh nhưng tình cờ bị chụp.
- Thread đang chờ native I/O.
- Worker đang chạy task không thuộc triệu chứng.

Nên dùng **nhiều stack samples có phương pháp**, JFR execution sampling, async profiler hoặc OS CPU delta. Cẩn thận bias của sampling và stack collection overhead.

### 7.5 Không chứng minh nhân quả

Nếu thread A đang chờ lock X và request B đang chậm, dump không tự chứng minh X gây B chậm. Cần liên kết theo thread/request/task, thời gian, lock owner và phép đối chứng. Tương quan giữa một lần chụp và một incident cũng có thể do bạn chỉ lấy dump sau khi sự cố xuất hiện.

### 7.6 Không đo được ai đã kết thúc trước lúc chụp

Một thread/task/exception hoàn tất ngay trước capture thường không còn stack hiện hành trong dump. Không thấy nó không chứng minh nó chưa chạy. Một thread mới có thể xuất hiện ngay sau capture. Khi incident là transient spike 50 ms, một ảnh lấy sau đó có thể trông hoàn toàn bình thường.

### 7.7 Không xác nhận tất cả thread trên mọi JDK

Khả năng liệt kê **platform threads**, **virtual threads**, native threads hoặc JVM internal threads khác nhau theo tool/version. Có bản dump truyền thống không bao gồm mọi virtual thread đang unmounted. Không lấy số lượng “Threads:” từ một công cụ rồi đồng nhất với tổng mọi Java tasks hoặc mọi OS threads.

## 8. Thu thập thread dump: điều kiện, công cụ và tác động

Một phép chẩn đoán có giá trị bắt đầu bằng việc xác định **đúng JVM đích**: PID trong đúng namespace, user thực thi, JDK/tool version, thời điểm và instance. Không thử các lệnh vào một PID lạ.

### 8.1 Lệnh jcmd cho HotSpot platform threads

Trên host/container có đúng JVM, có JDK tool và đủ quyền attach:

~~~bash
jcmd -l
jcmd <PID> help Thread.print
jcmd <PID> Thread.print
~~~

Thay *<PID>* bằng process ID đã xác minh; text này là placeholder trong tài liệu, không phải cú pháp shell được chạy nguyên văn. Trong Docker/Kubernetes, PID nhìn từ host có thể khác PID trong container; *jcmd -l* cũng có giới hạn discoverability giữa các process namespaces. Không kết luận JVM chết chỉ vì không thấy PID trong output jcmd -l.

Với HotSpot bản JDK 17/21 có hỗ trợ option, khi cần thông tin ownable synchronizer:

~~~bash
jcmd <PID> Thread.print -l
~~~

Nếu muốn thông tin mở rộng và command help của VM đích xác nhận:

~~~bash
jcmd <PID> Thread.print -e
~~~

**Không mặc định mọi JDK có cùng option/format.** Chạy *jcmd <PID> help Thread.print* trước. Tài liệu jcmd đánh giá Thread.print có tác động **medium**, phụ thuộc số thread; với JVM có rất nhiều thread, output có thể rất lớn và gây overhead/ảnh hưởng latency trong lúc sự cố. Không đặt vòng lặp lấy dump liên tục mỗi vài mili giây.

### 8.2 jstack và control-break

Ở những JDK/VM phù hợp, *jstack <PID>* là một đường thu thread stack khác. Trên HotSpot Linux, tín hiệu QUIT hoặc Control+\ tại console có thể yêu cầu thread dump được in vào luồng output của JVM; trên Windows một số môi trường hỗ trợ Control+Break. Các cách này phụ thuộc OS, phiên bản, quyền và cách container/log pipeline thu stdout/stderr.

**Chỉ dùng theo quy trình cho phép:** tín hiệu có thể tạo output rất lớn, có thể bị container/logging config xử lý khác, và một số JVM có policy riêng. Không nhầm **kill -QUIT** với **kill -KILL**: tín hiệu KILL có thể chấm dứt process và mất bằng chứng; tuyệt đối không dùng để “thử xem thread dump”.

### 8.3 Thu thập bằng ThreadMXBean

Trong chương trình Java, API chuẩn có thể lấy *ThreadInfo*, stack và lock metadata theo mức hỗ trợ. Ví dụ sau đây chỉ là **mảnh mã minh họa**:

~~~java
java.lang.management.ThreadMXBean bean =
        java.lang.management.ManagementFactory.getThreadMXBean();

java.lang.management.ThreadInfo[] infos =
        bean.dumpAllThreads(false, false);
~~~

Với Java 17, đây là một cách thu các live platform threads trong JVM hiện tại, **không phải một remote client tự động**. Có thể truy cập qua JMX được cấu hình an toàn, nhưng phải hiểu permission, connection và capability.

Một số method *dumpAllThreads(true, true)* yêu cầu hỗ trợ theo *isObjectMonitorUsageSupported()* và *isSynchronizerUsageSupported()*; không giả định VM nào cũng hỗ trợ mọi lock detail. Bật contention timing là thao tác khác với đọc snapshot và có thể phát sinh overhead.

### 8.4 Lưu output và metadata

Với *Thread.print*, có thể chuyển hướng stdout của **lệnh jcmd phía người gọi** sang file:

~~~bash
jcmd <PID> Thread.print -l > thread-01.txt
~~~

Còn các diagnostic command ghi file **ở phía JVM đích** thì đường dẫn được giải quyết trong filesystem/namespace của JVM đó, không nhất thiết là cwd của terminal đang gọi. Không phỏng đoán đường file trong container; kiểm tra path, quyền và dung lượng.

Một file thread dump có thể chứa tên thread, đường dẫn, class, stack frame, hostname, chi tiết khóa hoặc thông tin có ích cho kẻ tấn công. Hãy lưu vào vị trí bảo vệ, loại dữ liệu nhạy cảm trước khi chia sẻ và quy định retention.

### 8.5 Khi không attach được

Đừng đi từ “jcmd failed” tới “JVM deadlocked” ngay. Attach có thể thất bại vì:

- Sai PID hoặc process restart.
- JDK/jcmd không có trong minimal image.
- Khác effective user/group hoặc quyền OS.
- Khác PID/mount namespace trong container.
- Attach mechanism bị vô hiệu hoặc VM implementation không tương thích.
- JVM quá bận hoặc kênh attach không phản hồi đúng lúc.

Khi đó dùng telemetry/log/JFR đã bật sẵn, hướng chẩn đoán OS được phép hoặc kênh hỗ trợ của platform team. Không tùy tiện chmod */tmp*, bật privileged container hoặc mở quyền JMX chỉ để có dump.

## 9. Virtual threads từ Java 21+: không coi dump truyền thống là toàn bộ

**Ví dụ Java 17 ở phần sau dùng platform threads.** Java 21 đưa virtual threads thành tính năng chính thức; đây là một điểm cần đặc biệt chú ý khi áp dụng khái niệm snapshot trong ứng dụng mới.

Virtual thread là Java thread được JVM quản lý, có thể **mount** lên carrier platform thread và **unmount** khi chờ. Nhiều virtual threads không tương đương số lượng native OS threads. Nếu chỉ đếm carrier threads trong một dump truyền thống, bạn có thể bỏ qua rất nhiều tác vụ logic đang chờ.

Theo hướng dẫn JDK 21:

- *Thread.print* truyền thống không phải công cụ đầy đủ để mô tả tất cả virtual threads.
- **jcmd Thread.dump_to_file** có thể thu dump dạng text/JSON có phạm vi virtual threads rộng hơn; nội dung và định dạng **khác** dump truyền thống và không chứa tất cả object-address/monitor/native/heap details.
- Dạng dump này không phải snapshot nguyên tử nhất quán của toàn bộ virtual threads và không tự thực hiện mọi deadlock detection.
- **ThreadMXBean.dumpAllThreads()** của API management trên JDK hỗ trợ virtual threads mô tả **platform threads**, không tự bảo đảm gồm mọi virtual thread.
- Nếu điều tra virtual-thread pinning, scheduler starvation, socket I/O hoặc JVM-level events, JFR và công cụ hỗ trợ virtual threads có thể hữu ích hơn.

Với JDK 21 và công cụ có hỗ trợ, kiểm tra cú pháp trước:

~~~bash
jcmd <PID> help Thread.dump_to_file
~~~

Ví dụ theo **hướng dẫn virtual threads của Oracle JDK 21**, đường file nằm ở phía JVM đích:

~~~bash
jcmd <PID> Thread.dump_to_file -format=json threads.json
~~~

**Version caveat:** các bản JDK khác có thể chấp nhận tên tùy chọn/format khác (ví dụ *plain* thay *text* ở tài liệu đời sau). Chạy *help* của VM thực tế; không chuyển nguyên command giữa JDK 17, 21 và JDK mới mà không kiểm tra. **JDK 17 không có virtual threads chuẩn**, và không nên yêu cầu Thread.dump_to_file ở đó như một command luôn tồn tại.

Một virtual-thread dump thiếu monitor details không có nghĩa ứng dụng không dùng monitors. Một platform-thread dump không thấy virtual threads đang chờ không có nghĩa chúng đã kết thúc. **Phạm vi quan sát là một phần của bằng chứng**.

## 10. Lab Java 17+: tạo snapshot BLOCKED, WAITING, TIMED_WAITING

Lab này tạo ba **platform threads** với trạng thái có kiểm soát, sau đó dùng **ThreadMXBean.getThreadInfo()** để lấy ảnh chụp tại một thời điểm. Mục đích là thấy *state + lock owner* đúng về mặt kỹ thuật, không phải tạo deadlock thực sự.

- Thread *demo-blocked* muốn vào synchronized trên *MONITOR*, trong khi main cố ý giữ monitor lúc snapshot.
- Thread *demo-waiting* chờ *CountDownLatch* chưa được giải phóng.
- Thread *demo-sleeping* đang *Thread.sleep(60_000)* (thời gian đủ dài để lấy snapshot).
- Main kiểm tra các state, lấy ThreadInfo, in trạng thái, rồi **giải phóng tất cả** trong *finally*.

Tạo file **ThreadSnapshotDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;

public final class ThreadSnapshotDemo {
    private static final Object MONITOR = new Object();
    private static final CountDownLatch RELEASE = new CountDownLatch(1);

    public static void main(String[] args) throws Exception {
        Thread waiting = new Thread(() -> {
            try {
                RELEASE.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-waiting");

        Thread sleeping = new Thread(() -> {
            try {
                Thread.sleep(60_000L);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-sleeping");

        Thread blocked = new Thread(() -> {
            synchronized (MONITOR) {
                // Chỉ tiến vào đây sau khi main thả MONITOR.
            }
        }, "demo-blocked");

        try {
            waiting.start();
            sleeping.start();
            awaitState(waiting, Thread.State.WAITING);
            awaitState(sleeping, Thread.State.TIMED_WAITING);

            synchronized (MONITOR) {
                blocked.start();
                awaitState(blocked, Thread.State.BLOCKED);

                ThreadMXBean mx = ManagementFactory.getThreadMXBean();
                long[] ids = {blocked.getId(), waiting.getId(), sleeping.getId()};
                ThreadInfo[] infos = mx.getThreadInfo(ids, 8);

                for (ThreadInfo info : infos) {
                    if (info == null) {
                        throw new IllegalStateException("Thread ended too soon");
                    }
                    System.out.println(info.getThreadName() + "=" + info.getThreadState());
                }
                System.out.println("blockedOwnerIsMain="
                        + Thread.currentThread().getName().equals(
                                infos[0].getLockOwnerName()));
                System.out.println("blockedHasLockName="
                        + (infos[0].getLockName() != null));
            }
        } finally {
            RELEASE.countDown();
            sleeping.interrupt();
            for (Thread thread : new Thread[] {blocked, waiting, sleeping}) {
                if (thread.getState() != Thread.State.NEW) {
                    thread.join(2_000L);
                }
            }
        }
    }

    private static void awaitState(Thread thread, Thread.State desired)
            throws InterruptedException {
        for (int attempt = 0; attempt < 200; attempt++) {
            if (thread.getState() == desired) {
                return;
            }
            Thread.sleep(10L);
        }
        throw new IllegalStateException("Did not reach " + desired
                + ": " + thread.getState());
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 ThreadSnapshotDemo.java
java ThreadSnapshotDemo
~~~

**Stdout của chương trình đã được thử trên JDK HotSpot:**

~~~text
demo-blocked=BLOCKED
demo-waiting=WAITING
demo-sleeping=TIMED_WAITING
blockedOwnerIsMain=true
blockedHasLockName=true
~~~

Đây là 5 dòng **stdout từ chương trình**; một số JDK mới có thể cảnh báo biên dịch riêng vì *Thread.getId()* đã được thay thế/deprecated ở version mới, nhưng Java 17 vẫn biên dịch được. Runtime có thể khác về scheduling/timing, vì vậy method *awaitState* kiểm tra trong cửa sổ giới hạn để tránh giả định một phép sleep ngắn là đủ.

### 10.1 Vì sao demo chứng minh được lock owner?

Main giữ *MONITOR* khi khởi chạy thread *demo-blocked*; thread đó cố gắng vào cùng monitor, nên nó bị *BLOCKED*. *ThreadMXBean.getThreadInfo(ids, 8)* trả một **ThreadInfo snapshot**; trường *getLockOwnerName()* hiển thị main đang giữ monitor và *getLockName()* có giá trị không null. Khi main ra khỏi synchronized block, monitor được nhả, thread blocked có thể tiếp tục.

Nếu viết demo không giữ main trong synchronized tại thời điểm snapshot, trạng thái *BLOCKED* có thể đã biến mất trước khi đo. Đó là một ví dụ nhỏ của bản chất **ảnh chụp không ghi lại trạng thái đã qua**.

### 10.2 Vì sao waiting không phải deadlock?

Thread *demo-waiting* đang đợi *CountDownLatch*. Main giải phóng latch bằng *RELEASE.countDown()* ở finally; đó là đường tiến triển rõ ràng. Chỉ nhìn một dump giữa chương trình, bạn thấy WAITING, nhưng không biết một chút nữa main có release hay không.

Tương tự, *demo-sleeping* đang TIMED_WAITING với thời hạn dài; cuối chương trình main interrupt để không đợi hết 60 giây. Dòng *TIMED_WAITING* không chứng minh chương trình có lỗi timeout.

### 10.3 Vì sao không gọi đây là deadlock?

Ở thời điểm ảnh được lấy, main **giữ monitor** và **đang tiến hành snapshot**; nó không chờ monitor do demo-blocked sở hữu. Không có chu trình *A chờ B, B chờ A*. Thread blocked có lối thoát khi main rời synchronized block. Nếu chỉ thấy *demo-blocked=BLOCKED* mà kết luận “deadlock”, đó là suy luận sai.

### 10.4 Cách mở rộng lab nếu cần (không áp dụng production)

Bạn có thể lấy hai snapshot với các thời điểm khác nhau trong **lab** để quan sát trạng thái thay đổi sau khi main nhả monitor. Nhưng chụp liên tục có thể tác động scheduling; cũng không biến thread dump thành profiler chuẩn. Hãy giữ test nhỏ, giới hạn số thread và bảo đảm tất cả thread được cleanup.

## 11. Chuỗi snapshot: chuyển từ ảnh đơn sang bằng chứng xu hướng

Một cách hữu ích là thu **một số** dump có đánh dấu thời gian trong giai đoạn triệu chứng đang diễn ra, ví dụ ba đến năm ảnh cách nhau vài giây **nếu mức tác động và tải cho phép**. Đây là hướng dẫn khám phá, không phải một “chuẩn phải chụp đúng 3 ảnh cách 5 giây”. Khoảng cách phải phù hợp độ dài hiện tượng, overhead công cụ và traffic.

Ví dụ lập bảng:

| Thời điểm UTC | Thread identity | State | Top frames | Lock/owner | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| 10:00:00 | pool-worker-7 | BLOCKED | Inventory.reserve | monitor X / worker-1 | Snapshot 1 |
| 10:00:05 | pool-worker-7 | BLOCKED | Inventory.reserve | monitor X / worker-1 | Snapshot 2 |
| 10:00:10 | pool-worker-7 | RUNNABLE | Checkout.reply | — | Snapshot 3 |

**Diễn giải đúng:** ba ảnh ủng hộ giả thuyết worker-7 bị ảnh hưởng bởi lock X trong giai đoạn có triệu chứng và sau đó tiến triển. Nhưng **không đo được chính xác tổng thời gian BLOCKED bằng 10 giây**: thread có thể tạm chuyển trạng thái rồi quay lại giữa các lần thu.

Khi so snapshot phải đối chiếu **cùng process instance và thread identity**, không chỉ tên thread. Thread ID có thể tái sử dụng theo lifecycle, PID reset sau restart, thread pool có thể tạo lại worker cùng tên. Nếu dump đến từ nhiều pod/JVM, tuyệt đối không gộp frame và owner ID như thể thuộc một lock graph chung.

### 11.1 Quy trình điều tra từ triệu chứng đến kết luận

1. **Khóa phạm vi incident:** service, pod/host, PID/JVM start time, thời điểm, tải, route, error/latency metrics.
2. **Lấy mẫu đầu:** công cụ hỗ trợ, quyền attach đúng, lưu metadata và cân nhắc overhead.
3. **Phân nhóm thread:** request workers, timers, pool helpers, GC/JIT/internal, event-loop, virtual threads (nếu JVM hỗ trợ).
4. **Xem state + stack + owner:** ưu tiên thread liên quan triệu chứng, không bị dẫn dắt bởi thread ngủ bình thường.
5. **Kiểm tra mối quan hệ:** nếu BLOCKED, tìm owner và stack của owner; nếu parked, tìm condition/queue và code phát tín hiệu.
6. **Lấy thêm ảnh có kiểm soát:** so stack signature, lock identity, trạng thái và dấu tiến triển; không lặp dồn dập vào JVM quá tải.
7. **Đối chiếu nguồn khác:** JFR execution/thread park/monitor events, OS CPU per-thread, GC pause, app log/trace, queue/dependency metrics.
8. **Nêu giả thuyết và mức chắc chắn:** nói điều đã nhìn thấy vs điều suy ra; đề xuất phép kiểm có khả năng bác bỏ giả thuyết.
9. **Chọn hành động ít xâm lấn:** kiểm tra before/after, giới hạn quyền truy cập và retention của dump.

### 11.2 Từ nhiều ảnh vẫn không được thần thánh hóa

Ngay cả ba snapshot cùng một stack chưa chứng minh thread **không bao giờ tiến triển**. Nó có thể lặp một đoạn code nhanh rất nhiều lần. Muốn chứng minh thiếu tiến triển nghiệp vụ, hãy so **progress counter**, queue completion, span timings, logs hoặc trạng thái dữ liệu tương ứng.

Để xác định CPU hotspot, sampling statistical trên một cửa sổ đủ dài hoặc JFR/async profiler thường đáng tin hơn việc tự đếm vài thread-dump lines; chúng cung cấp phương pháp và trọng số theo mẫu, dù vẫn có bias/overhead cần xem xét.

## 12. Kết hợp thread dump với các nguồn chứng cứ khác

| Câu hỏi cần trả lời | Thread dump đóng góp | Nguồn cần kết hợp |
| --- | --- | --- |
| Request chậm đang kẹt ở đâu? | Call stack của worker, state, lock/park hint | TraceId, request logs, dependency timings |
| Có monitor contention không? | BLOCKED, waiting to lock, owner | Repeated snapshots, JFR monitor-enter events, latency |
| CPU process tăng cao vì thread nào? | Gợi ý stack tương ứng thời điểm | OS per-thread CPU delta, JFR/profiler |
| Có deadlock không? | Lock graph/detector trong phạm vi hỗ trợ | ThreadMXBean deadlock detection, code lock order, logs |
| Thread pool starvation? | Workers đồng loạt ở blocking call | Active/queue/complete rates, pool config, traces |
| GC pause gây p99 spike? | Có thể thiếu thông tin hoặc chỉ thấy VM threads | GC Unified Logging/JFR, pause histogram, metrics |
| Native socket đang chờ? | Top frames/native states gợi ý | Network spans, socket states, dependency metrics |
| Memory leak? | Stack thường không đủ để xác lập object retention | Heap usage trend, JFR allocation, heap dump có kiểm soát |
| Request lỗi đã kết thúc? | Thường không còn stack task đó | Application error logs, traces, exceptions |
| Virtual thread pinning/stall? | Tùy dump có virtual-thread coverage | Virtual-thread-specific dump, JFR pinning/scheduler events |
| Một operation đã chờ 30 giây? | Ảnh có thể thấy đang chờ | Timestamp trong app logs, spans, JFR duration |

Không yêu cầu một thread dump tự chứa toàn bộ observability context. Kết quả tốt là một **mảnh bằng chứng cụ thể** hỗ trợ hoặc loại trừ giả thuyết.

## 13. Bốn tình huống diễn giải trước–sau

### Tình huống A – 40 HTTP workers có WAITING trong pool

**Ảnh đơn:** nhiều worker có frame *LinkedBlockingQueue.take()* và state WAITING.

**Suy luận sai:** “40 workers đã deadlock”.

**Đọc đúng:** các thread chờ task; có thể hoàn toàn bình thường nếu queue trống. Cần đối chiếu request rate, queue depth, active threads, completed tasks và thread naming. Nếu request không được xử lý dù task đã enqueue, mới xem pool configuration, điều kiện đánh thức và submission behavior.

### Tình huống B – 20 threads BLOCKED cùng một monitor

**Ảnh đơn:** các request workers cùng *waiting to lock <X>*; một thread khác *locked <X>*.

**Suy luận sai:** “Cùng một lock chắc chắn gây mọi p99 spike 2 giây”.

**Đọc đúng:** có dấu contention tại lúc chụp. Kiểm tra owner đang ở đâu trên stack, liệu I/O được gọi trong synchronized block không, các worker có liên quan route chậm, và contention có kéo dài qua ảnh tiếp theo hoặc JFR monitor events không.

**Kết luận sau kiểm chứng có thể:** “Ở các ảnh 10:00:00 và 10:00:05 nhiều checkout workers chờ monitor X; owner chạy network call trong critical section; trace cho thấy latency tăng cùng thời gian. Đây là bằng chứng mạnh cần đo duration/đánh giá code path.” Vẫn tránh khẳng định thời gian BLOCKED chính xác nếu chưa đo.

### Tình huống C – CPU process 300%, một RUNNABLE ở JSON parser

**Ảnh đơn:** một worker RUNNABLE với stack JSON parser.

**Suy luận sai:** “JSON parser đang dùng 300% CPU”.

**Đọc đúng:** một thread Java RUNNABLE không thể được quy ngay thành toàn bộ CPU của process. CPU có thể do thread khác, GC/JIT/native hoặc scheduling. Phải xem per-thread CPU time theo delta, JFR samples/profiler trong cùng cửa sổ, và map native thread IDs cẩn thận.

Nếu nhiều execution samples trên cùng frame với trọng số đáng kể và CPU deltas tương ứng, giả thuyết hotspot mới có thêm bằng chứng.

### Tình huống D – Service timeout khi thanh toán, dump chỉ có TIMED_WAITING timers

**Ảnh đơn:** timer threads ngủ theo lịch; không thấy payment worker.

**Suy luận sai:** “Payment request không chạy hoặc đã hoàn toàn ổn”.

**Đọc đúng:** request có thể đã timeout/kết thúc trước khi chụp, hoặc chạy trên virtual threads không nằm trong phạm vi dump. Cần app logs, tracing, dependency metrics và capture trong đúng khoảng sự cố. Không phải thread dump nào cũng phù hợp để chẩn đoán một spike đã qua.

## 14. Cách viết một báo cáo có căn cứ

Một đoạn báo cáo nên chia **facts → hypotheses → tests → limitations**.

**Ví dụ tốt:**

> Lúc 10:01:20 UTC trên JVM checkout pod-4, snapshot do jcmd Thread.print -l cho thấy 18 request worker ở BLOCKED tại Inventory.reserve và cùng chờ monitor X. Một thread inventory-maintainer được ghi đang giữ X và có stack ở một external-call method. Đây là dấu hiệu monitor contention khi request latency tăng. Chưa biết thời lượng giữ lock hay chắc chắn đây là nguyên nhân p99. Sẽ đối chiếu thêm 2 snapshot có đánh dấu thời gian, trace spans và JFR monitor-enter durations trong cửa sổ sự cố.

**Ví dụ không nên viết:**

> Thread dump chứng minh inventory-maintainer giữ khóa 10 phút làm toàn bộ API treo vì đang RUNNABLE, chắc chắn cần restart JVM.

Ví dụ sau vượt quá khả năng ảnh đơn: không có duration, thiếu tiến trình thời gian và chưa kiểm tra scope của ảnh hay nguyên nhân khác.

Mẫu metadata tối thiểu nên lưu cùng dump:

~~~text
Incident:
Service/version:
Host / pod / container:
JVM PID and JVM start time:
JDK version / VM implementation:
Capture command and tool version:
Timestamp with timezone:
Capture file/format/location:
Thread count and known coverage caveats:
Observed states/stack signatures/locks:
Related app metrics/logs/traces:
Hypotheses and evidence level:
Next safe validation:
Data classification/retention:
~~~

Không lưu credentials hoặc chi tiết khách hàng trong báo cáo. Nếu phải chia sẻ stack traces từ production, kiểm soát quyền xem và redaction.

## 15. Những lỗi phân tích lặp lại nhiều nhất

| Nhận định sai | Vì sao sai | Diễn giải/việc cần làm |
| --- | --- | --- |
| “RUNNABLE = 100% CPU” | RUNNABLE là JVM state, có thể đợi OS/I/O | Dùng per-thread CPU delta/JFR |
| “WAITING = thread treo” | Queue workers thường chờ việc | Xem frame, queue state và progress |
| “TIMED_WAITING = timeout đã xảy ra” | Chỉ là chờ có thời hạn | Xem deadline và application result |
| “BLOCKED = deadlock” | Chờ monitor có thể ngắn; deadlock cần cycle | Tìm owner/graph, nhiều mẫu, detector |
| “ReentrantLock contention luôn BLOCKED” | Contended LockSupport/Condition có thể WAITING | Nhìn stack và ownable synchronizers |
| “Thread sống 2 giờ nên BLOCKED 2 giờ” | Thread age khác duration state | Cần timing/profiling/time series |
| “Không có deadlock report = không deadlock” | Detector có giới hạn và loại deadlock khác | Phân tích dependencies và tool coverage |
| “Thấy cùng stack 3 lần = không tiến triển” | Thread có thể đi vòng qua stack đó nhiều lần | So progress counters/trace/events |
| “Không thấy request thread = request chưa chạy” | Task có thể kết thúc, bị đổi worker/virtual | App traces, đúng time window, dump type |
| “Một frame ở JSON parser = CPU hotspot” | Không có phân bố hoặc CPU duration | Profiler/JFR và OS CPU |
| “nid là Java Thread.getId” | Native/Java IDs có namespace khác | Tra tool/version và mapping |
| “Mỗi thread name ứng với một request” | Worker thường xử lý nhiều requests | Trace/context correlation |
| “Dump là ảnh atomically toàn JVM” | Một số cơ chế thu non-atomic và tốn thời gian | Ghi phương pháp và capture window |
| “Một dump luôn gồm mọi virtual thread” | Công cụ và JDK quyết định coverage | Xác minh Thread.dump_to_file/JFR |
| “Không có stack sâu nghĩa code không gọi hàm đó” | Stack có thể bị cắt/tối ưu/native frame | Kiểm tra depth, symbol/debug metadata |
| “Nhiều threads nghĩa nhiều requests active” | Pool helpers, GC/JIT/internal, idle workers cũng hiện | Phân loại roles và metrics |
| “Có thread dump thì restart là biện pháp rõ ràng” | Snapshot chỉ là bằng chứng, restart làm mất trạng thái | Hình thành giả thuyết, đánh giá impact |
| “Thread.print không ảnh hưởng service” | Dump rất lớn có overhead/I/O | Chụp có kiểm soát, tránh loop dày |
| “Không thấy lock nghĩa không có lock” | Tool/format có thể không in locked synchronizers | Bật options phù hợp, hiểu coverage |

## 16. Câu hỏi tự kiểm tra có đáp án

### 1. Một thread RUNNABLE có nghĩa đang dùng một CPU core liên tục không?

**Không.** Đây là Java state; thread có thể không được scheduler cấp CPU, có thể ở native I/O hoặc chỉ thoáng qua ở Java code. CPU time/rate phải được đo từ các counter theo thời gian hoặc profiler.

### 2. Thread pool có 100 threads WAITING trong LinkedBlockingQueue.take: sự cố hay bình thường?

**Chưa thể kết luận.** Nếu không có tasks chờ, đây có thể là idle bình thường. Nếu queue có backlog nhưng không có workers xử lý, cần kiểm tra queue/pool metrics và thread lifecycle.

### 3. Có một thread BLOCKED là đã có deadlock?

**Không.** Một thread chờ monitor chủ sở hữu đang dùng hợp lệ có thể tiến triển ngay khi monitor được nhả. Deadlock đòi hỏi chu trình chờ hoặc điều kiện kẹt đặc thù có bằng chứng.

### 4. Tại sao ReentrantLock tranh chấp có thể hiện WAITING?

Vì nhiều đường đồng bộ dựa trên *AbstractQueuedSynchronizer/LockSupport.park*, không phải Java object monitor dùng *synchronized*. Enum BLOCKED mô tả chờ monitor, không bao phủ mọi loại đồng bộ.

### 5. Header có *elapsed=3600s* và state BLOCKED, kết luận chờ lock một giờ được không?

**Không.** *Elapsed* dạng đó thường là tuổi đời thread theo thông tin VM, không phải thời gian nó đã ở state BLOCKED. Muốn timing cần instrumentation hoặc theo dõi lịch sử.

### 6. Ba snapshot cách nhau 5 giây đều thấy cùng stack, có đo được 10 giây blocked không?

**Không chính xác.** Đây là ba thời điểm quan sát, thread có thể rời rồi quay lại cùng stack giữa các lần đo. Chỉ có thể nói “bị quan sát ở trạng thái đó tại ba mốc”, và kết hợp các nguồn khác để ước tính duration.

### 7. Không thấy deadlock report có loại trừ các yêu cầu tương hỗ giữa hai microservices không?

**Không.** JVM lock detector không tự phát hiện chu trình phụ thuộc qua network/service. Cần distributed tracing, queue/dependency logs và kiểm tra thiết kế giao thức.

### 8. Stack trace có frame socket read trong RUNNABLE, có chứng minh CPU đang bị socket read chiếm không?

**Không.** Có thể thread chờ I/O ở native method mà Java Thread.State vẫn RUNNABLE. Hãy xem network timing và OS thread CPU.

### 9. Vì sao virtual threads đòi hỏi chú ý loại dump?

Vì virtual threads không ánh xạ một-một với OS threads, có thể unmount. Dump truyền thống tập trung platform threads/carrier có thể thiếu các virtual threads đang chờ; JDK 21 có *Thread.dump_to_file* hỗ trợ phạm vi khác nhưng có hạn chế riêng.

### 10. Nếu thread không còn trong dump mới, nó đã hoàn thành thành công?

**Không chắc.** Nó có thể kết thúc do exception, bị thay bằng thread khác, dump không bao phủ hoặc process restart. Cần app logs/traces/task completion evidence.

### 11. Thread dump có tính được p99 request latency không?

**Không.** Dump là snapshot của stacks/states, không phải tập duration measurements. Dùng metrics hoặc tracing với một cửa sổ đủ số mẫu.

### 12. Khi nào một lock graph trong dump là bằng chứng mạnh?

Khi dump có **owner/waiter identity đáng tin**, nhiều thread cùng chờ khóa có liên quan, hoặc detector báo một **chu trình deadlock** thuộc phạm vi hỗ trợ. Để khẳng định lock contention là root cause của latency, vẫn cần liên hệ thời gian, request và mức kéo dài/tần suất.

### 13. Vì sao hai thread có cùng top frame chưa chắc làm cùng công việc?

Cùng method có thể được gọi bởi các requests/tasks khác nhau, state khác nhau, hoặc đều đang ở một queue wait chung. Cần ngữ cảnh từ thread name, full stack, trace, queue/task identity.

### 14. Khi chụp dump service production, ưu tiên điều gì trước?

Xác minh **đúng JVM**, quyền/công cụ, chi phí và bảo mật; lấy một snapshot có metadata, rồi đánh giá cần thêm mẫu hay nguồn khác. Không tạo dump liên tục hoặc restart mà chưa kiểm tra tác động.

## 17. Tài liệu đối chiếu chính thức

- **Java SE 17 – Thread.State**, hợp đồng 6 trạng thái JVM: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- **Java SE 17 – ThreadMXBean**, ThreadInfo, lock monitoring và deadlock detection: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- **Java SE 17 – ThreadInfo**, Thread State, lock owner, stack: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- **Oracle JDK 21 – jcmd**, *Thread.print* options và impact: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **Oracle JDK 17 – Diagnostic Tools**, thread dumps, jstack, signal và hỗ trợ locks: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- **Oracle JDK 17 – Troubleshoot Process Hangs and Loops**, giải thích deadlock/monitor waiting: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-process-hangs-and-loops.html
- **Oracle JDK 21 – Virtual Threads**, công cụ tạo virtual-thread dumps: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html

Cú pháp, tiêu đề, phạm vi virtual-thread coverage, lock details, chi phí và consistency của dump **phụ thuộc công cụ và phiên bản JVM**. Khi dùng vào incident thực, kiểm tra tài liệu và *help* từ JDK đang chạy.

## Ghi nhớ

**Thread dump là bằng chứng vị trí và trạng thái ở một hoặc vài thời điểm, không phải bằng chứng lịch sử hay root cause hoàn chỉnh.** Một ảnh có thể chỉ ra thread hiện ở đâu, trạng thái Java, stack frames và đôi khi lock/owner; nó **không thể** một mình đo duration, CPU percentage, throughput, p99, số lần xảy ra, toàn bộ virtual threads hoặc quan hệ nhân quả.

Phương pháp đúng là **nói rõ quan sát → đề xuất giả thuyết → lấy thêm mẫu đúng phạm vi → đối chiếu CPU/JFR/GC/app metrics/logs/traces → kiểm chứng → mới kết luận**.