# 1.4 — Bản đồ log, chỉ số, stack trace, thread dump, heap dump và bản ghi JFR

## 1. Mục tiêu: chọn đúng bằng chứng cho đúng câu hỏi

Khi một ứng dụng Java chậm, báo lỗi, dùng nhiều CPU hoặc tăng bộ nhớ, sáu loại bằng chứng thường gặp là **log**, **metrics (chỉ số)**, **stack trace**, **thread dump**, **heap dump** và **Java Flight Recorder (JFR)**. Chúng quan sát cùng một tiến trình JVM nhưng ở độ phân giải và chiều thời gian khác nhau. Không có loại nào thay thế hoàn toàn loại khác.

Sau bài này, người học cần trả lời được: (1) mỗi loại bằng chứng đo hoặc ghi lại điều gì; (2) nên lấy loại nào trước cho từng triệu chứng; (3) cách đọc, kết hợp và kiểm chứng giả thuyết; (4) chi phí vận hành, giới hạn và rủi ro khi thu thập trên môi trường thật.

> Quy tắc điều tra: **triệu chứng → câu hỏi có thể kiểm chứng → bằng chứng phù hợp → giả thuyết → đối chiếu thêm bằng chứng**. Một ảnh chụp hoặc một biểu đồ đơn lẻ thường chưa đủ để kết luận nguyên nhân.

## 2. Bản đồ sáu loại bằng chứng

| Bằng chứng | Đơn vị quan sát | Chiều thời gian | Trả lời tốt nhất câu hỏi | Giới hạn cốt lõi |
| --- | --- | --- | --- | --- |
| **Log** | Một sự kiện nghiệp vụ hoặc kỹ thuật có ngữ cảnh | Các thời điểm ghi sự kiện | *Yêu cầu nào thất bại, đầu vào/nhánh xử lý nào liên quan?* | Chỉ thấy những gì đã được ghi; có thể thiếu hoặc nhiễu |
| **Metrics** | Giá trị tổng hợp: counter, gauge, histogram… | Chuỗi thời gian theo cửa sổ | *Lỗi/chậm/tải tăng từ khi nào, rộng đến đâu?* | Thường không chỉ ra yêu cầu hay dòng code cụ thể |
| **Stack trace** | Chuỗi lời gọi của một luồng tại thời điểm lỗi/quan sát | Một thời điểm | *Đường gọi nào dẫn đến lỗi hoặc vị trí thực thi hiện tại?* | Một stack không đại diện cho mọi thread hoặc lịch sử |
| **Thread dump** | Trạng thái và stack của nhiều Java thread trong JVM | Ảnh chụp tức thời; có thể lấy nhiều lần | *Thread nào BLOCKED/WAITING/RUNNABLE, đang đợi lock hay tài nguyên gì?* | Snapshot không chứng minh thread đã ở đó bao lâu |
| **Heap dump** | Đồ thị đối tượng trên Java heap và các quan hệ tham chiếu | Ảnh chụp bộ nhớ | *Đối tượng nào đang được giữ lại, ai giữ và vì sao GC chưa thu hồi?* | Nặng, nhạy cảm; không mô tả trực tiếp CPU hay toàn bộ native memory |
| **JFR recording** | Các event JVM/ứng dụng, khoảng thời gian, stack được lấy mẫu | Khoảng thời gian có timestamp | *Trong vài phút xảy ra điều gì về CPU, allocation, GC, lock, I/O?* | Có lấy mẫu/ngưỡng và cấu hình sự kiện; không ghi lại mọi lời gọi |

**Hai trục cần ghi nhớ:**

- **Snapshot so với timeline:** stack trace, thread dump, heap dump cho thấy trạng thái tại điểm lấy mẫu; metrics, log và JFR giúp xem diễn biến qua thời gian. Nhiều thread dump cách nhau vài giây tạo một chuỗi snapshot, vẫn không phải lịch sử hoàn chỉnh.
- **Độ rộng so với độ sâu:** metrics bao quát hệ thống; log giúp định vị request; stack trace đi vào đường gọi; thread dump đi vào phối hợp luồng; heap dump đi vào đồ thị đối tượng; JFR nối nhiều góc nhìn bằng sự kiện và thời gian.

Ví dụ, “heap đạt 90%” là **triệu chứng** từ metrics. Nó chưa chứng minh memory leak: ứng dụng có thể đang giữ cache hợp lệ, GC chưa chạy, hoặc heap tăng rồi ổn định. Cần xem heap **sau GC**, xu hướng nhiều cửa sổ và, khi hợp lý, retained objects trong heap dump.

## 3. Chuẩn bị ngữ cảnh trước khi thu thập

Ghi lại **service**, môi trường, phiên bản build/JDK, thời điểm bắt đầu và kết thúc bất thường, timezone, instance/pod, PID, tải (RPS), tỷ lệ lỗi và thay đổi gần nhất (deploy, cấu hình, lưu lượng). Đồng bộ thời gian giữa host, log và hệ thống giám sát để ghép sự kiện đúng.

- Phân biệt **PID của JVM trên host** với PID trong container; lệnh `jcmd` phải chạy nơi có thể attach đến JVM, thông thường cùng host và cùng effective user/group.
- Xác định **cửa sổ sự cố** và **mốc bình thường** để so sánh. Nếu biểu đồ là trung bình trên 5 phút còn log chính xác đến mili giây, phải quy về cùng cửa sổ khi kết luận.
- Chụp bằng chứng dễ thu và ít xâm lấn trước. Cần cân nhắc thời lượng, kích thước file, đĩa trống và ảnh hưởng lên latency khi lấy dump hay bật cấu hình ghi sâu.
- Gắn nhãn mỗi hiện vật bằng thời gian, instance, PID và phiên bản. Một `threads.txt` không có mốc thời gian rất dễ bị đem đối chiếu sai với `incident.jfr`.

## 4. Log: điều gì đã được ứng dụng ghi nhận?

Log là những bản ghi sự kiện có chủ đích: request bắt đầu/kết thúc, lỗi xử lý, retry, timeout, thay đổi trạng thái, tương tác hệ thống ngoài. Log lý tưởng có timestamp, level, service/instance, tên thao tác, `traceId`/`requestId`, mã lỗi, thời lượng và thông tin nghiệp vụ được phép lưu.

```text
2026-01-15T10:15:01.240Z WARN service=checkout traceId=7f21 operation=reserveStock durationMs=1800 result=timeout
2026-01-15T10:15:01.245Z ERROR service=checkout traceId=7f21 operation=placeOrder error=InventoryTimeout
```

Hai dòng **minh họa** này cho phép nối hai bước bằng `traceId=7f21` và nhận ra timeout upstream. Chúng **không** tự chứng minh nghẽn mạng, lock hay CPU; phải kiểm tra bằng số đo và bằng chứng ở service liên quan.

**Cách đọc và đặt log hữu ích:**

1. Tìm spike của lỗi hoặc request chậm, rồi lọc theo cùng service, thời điểm và trace ID.
2. Đọc chuỗi sự kiện theo thứ tự, phân biệt thông báo lỗi ban đầu với lỗi “hậu quả” xuất hiện ở lớp trên.
3. Giữ nguyên exception cùng `Caused by`; thông báo tổng quát như “request failed” thường chưa đủ.
4. Dùng structured logging và các trường tên ổn định; tránh ghép tự do khiến khó tìm/lọc.
5. Chọn mức `INFO`/`WARN`/`ERROR` theo ý nghĩa; `DEBUG` có thể giúp điều tra ngắn hạn nhưng tăng dung lượng và độ trễ.

**Không ghi** mật khẩu, token, số thẻ, payload nhạy cảm hoặc dữ liệu cá nhân không cần thiết. Sampling hoặc rate limit log có thể khiến không phải request nào cũng có đầy đủ log. Thiếu một dòng log **không** chứng minh sự kiện không xảy ra.

## 5. Metrics: quy mô, xu hướng và điểm bắt đầu bất thường

Metrics biểu diễn số đo theo thời gian:

- **Counter** chỉ tăng (ví dụ `requests_total`, `errors_total`); tính **tốc độ tăng trên một cửa sổ**, tránh so sánh trực tiếp giá trị tích lũy từ hai tiến trình khởi động khác nhau.
- **Gauge** có thể tăng giảm (ví dụ số thread hoạt động, hàng đợi, heap đang dùng, số connection).
- **Histogram** ghi phân bố quan sát (ví dụ request latency); hỗ trợ xem p50/p95/p99. **p99** nghĩa là khoảng 99% quan sát ở mức không vượt quá ngưỡng đó trong tập dữ liệu được xét, không phải thời gian của “request tệ nhất”.

Nhóm **RED** cho dịch vụ: **Rate** (lưu lượng), **Errors** (lỗi), **Duration** (độ trễ). Ghép thêm CPU tiến trình/host, GC pause, heap used/committed/max, thread count, connection pool và queue depth tùy triệu chứng.

Ví dụ phân tích có căn cứ:

1. RPS gần như không đổi, p99 tăng mạnh và thread pool bị chiếm kín: nghi ngờ **tranh chấp hoặc đợi downstream**, chưa thể chỉ từ metrics quyết định loại nào.
2. CPU process tăng gần ngưỡng trong khi p99 tăng: thu JFR CPU sampling, đối chiếu GC và thread dump; không tự khẳng định ứng dụng đang chạy vòng lặp vô hạn.
3. Heap used tăng theo tải rồi giảm sau GC: có thể là phân bổ bình thường. Nếu **đáy sau GC** liên tục tăng sau nhiều chu kỳ, nghi ngờ giữ đối tượng lâu và cân nhắc heap dump.
4. Tỷ lệ lỗi = số lỗi / số request trong cùng cửa sổ; chú ý mẫu số nhỏ và label cardinality. Không gắn raw user ID hoặc request ID làm label metrics vì số chuỗi tăng không giới hạn.

Một biểu đồ có độ phân giải 1 phút có thể che khuất đột biến 2 giây. Chú ý cách tổng hợp (`sum`, `avg`, `max`), mẫu số, phân phối latency và khoảng lấy mẫu. Metrics là **chỉ dẫn để chọn nơi đào sâu**, không phải bằng chứng duy nhất về nguyên nhân.

## 6. Stack trace: đường gọi tại một thời điểm

Stack trace có các frame với tên class, method, file và dòng, thường xuất hiện khi exception được ghi. Đọc từ thông báo exception và các `Caused by` để lần theo nguồn gốc, đồng thời xem các frame ứng dụng liên quan (nhiều frame framework chỉ là đường chuyển tiếp).

```text
java.lang.IllegalStateException: Could not create order
    at example.OrderService.create(OrderService.java:42)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at example.OrderService.readQuantity(OrderService.java:19)
```

Đây là **minh họa cấu trúc**, không phải stdout từ một chương trình trong bài. Dòng `OrderService.java:19` gợi nơi parse đầu vào; cần xem dữ liệu và cách xử lý lỗi ở đó, không quy lỗi cho `Integer.parseInt` chỉ vì frame thư viện xuất hiện. Với exception lồng nhau, phần `Caused by` thường giải thích nguyên nhân sâu hơn; `Suppressed` (ví dụ khi đóng resource) cũng có thể chứa manh mối.

**Phân biệt:** exception stack trace là đường gọi dẫn đến lỗi của **một thread**. Thread dump chứa stack và trạng thái **nhiều thread**, kể cả khi không có exception. Với async/`CompletableFuture`, ranh giới task/queue có thể làm mất sự liên tục của call stack; correlation ID và tracing giúp nối các bước.

Không kết luận “method X tiêu tốn 90% CPU” chỉ vì nó xuất hiện trong một stack trace. Cần CPU profiling/JFR qua nhiều mẫu.

## 7. Thread dump: nhiều luồng đang làm gì, chờ điều gì?

Dùng khi request bị treo, thread pool cạn, nghi deadlock, nhiều request chờ lock hoặc CPU cao nhưng chưa biết thread nào. Có thể xem thread name, trạng thái, stack, monitor và một số khóa liên quan.

Trạng thái Java cần hiểu đúng:

| `Thread.State` | Cách diễn giải thận trọng |
| --- | --- |
| `RUNNABLE` | Đủ điều kiện chạy từ góc nhìn JVM; có thể đang thực thi hoặc ở một số tác vụ native/I/O. Không mặc định là đang sử dụng CPU. |
| `BLOCKED` | Đang đợi vào monitor của `synchronized`; tìm thread đang giữ monitor và đường gọi liên quan. |
| `WAITING` | Đợi không thời hạn rõ ràng qua các cơ chế như `Object.wait`, `Thread.join`, `LockSupport.park`; thường bình thường với worker rỗi. |
| `TIMED_WAITING` | Đợi có thời hạn như `sleep` hoặc timed wait/park/join; cần xem frame để biết có bất thường hay không. |
| `NEW` / `TERMINATED` | Chưa start / đã hoàn tất, ít khi là tâm điểm của thread dump tiến trình đang chạy. |

Thu thập với JDK 17+ (thay `<pid>` bằng PID thực tế):

```bash
jcmd -l
jcmd <pid> Thread.print -l > threads-t1.txt
```

Để phát hiện **tình trạng kéo dài**, nên có 2–3 dump cách nhau khoảng 5–10 giây trong lúc sự cố đang diễn ra; lưu thời gian của từng bản. So sánh xem thread và stack có liên tục ở cùng điểm chờ hay chỉ đi ngang qua đó. `-l` bổ sung thông tin khóa thuộc `java.util.concurrent` nếu JVM hỗ trợ. Nếu không attach được, kiểm tra PID, quyền chạy, container/namespace và danh sách lệnh của JVM bằng `jcmd <pid> help`.

**Cách phân tích:** nhóm thread theo tên và stack, nhận diện pool đang active/rỗi, dò chuỗi “waiting to lock” ↔ “locked” và thread nắm monitor; tìm vòng chờ nếu nghi deadlock. Một thread `WAITING` trong `ThreadPoolExecutor.getTask` có thể là worker **đang rỗi**, không phải deadlock. Nhiều thread `BLOCKED` trên cùng monitor hoặc cùng điểm chờ lặp lại mới là tín hiệu mạnh hơn.

Thread dump chỉ chụp các thời điểm nhất định. Không dùng một ảnh chụp để chứng minh độ dài của chờ lock hoặc nguyên nhân CPU; kết hợp JFR events, throughput và thời điểm các request chậm.

## 8. Heap dump: ai đang giữ bộ nhớ Java heap?

Heap dump (thường là HPROF) ghi đồ thị object, class, kích thước và đường tham chiếu tại một thời điểm. Nó đặc biệt hữu ích khi heap **sau GC** tiếp tục tăng, gặp `OutOfMemoryError: Java heap space` hoặc nghi cache/session/listener giữ object không còn cần thiết.

Từ một heap dump, trình phân tích như Eclipse Memory Analyzer (MAT) hỗ trợ:

1. **Class histogram:** class nào có nhiều instance hoặc dùng nhiều bộ nhớ.
2. **Shallow size:** kích thước của chính object; **retained size:** bộ nhớ có thể được giải phóng nếu object đó và các object chỉ còn reachable qua nó trở nên unreachable.
3. **Dominator tree:** object/nhánh nào giữ phần lớn heap; không đồng nhất “to nhất” với “lỗi” nếu dữ liệu đó là cache được thiết kế.
4. **Path to GC roots:** chuỗi tham chiếu từ GC root (static field, thread, JNI handle…) dẫn tới object nghi vấn; đây là manh mối về **vì sao object còn sống**.

Lệnh ví dụ cho HotSpot JDK 17+:

```bash
jcmd <pid> GC.heap_dump /var/tmp/incident-heap.hprof
```

Đường dẫn phải ghi được bởi **tiến trình JVM đích** và đủ dung lượng. Đây là thao tác có **impact cao**: có thể gây pause và sử dụng CPU, RAM, I/O, dung lượng lớn; mặc định `GC.heap_dump` yêu cầu full GC trừ khi dùng tùy chọn `-all`. Hãy cân nhắc thời điểm/ủy quyền vận hành trước khi dùng trên production. Tùy chọn tự tạo dump khi JVM gặp Java heap OOM:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/tmp/app-oom.hprof -jar app.jar
```

Cần cấu hình từ khi khởi động và bảo đảm nơi lưu trữ. Heap dump không giải thích trực tiếp **native/off-heap memory**, file descriptor hoặc CPU cao; không tự kết luận mọi OOM đều là heap leak. Một ảnh chụp đơn lẻ cũng không chứng minh **tốc độ tăng**: đối chiếu metrics hoặc so sánh hai dump hợp lý nếu chi phí cho phép.

**Bảo mật:** heap dump có thể chứa token, session, mật khẩu và dữ liệu người dùng trong object. Chỉ truyền/lưu ở nơi có kiểm soát truy cập, có quy định xóa và hạn chế chia sẻ.

## 9. JFR: dòng thời gian sự kiện và mẫu quan sát của JVM

**Java Flight Recorder** tạo file `.jfr` chứa các sự kiện theo thời gian, như CPU execution samples, allocation, GC, monitor contention, thread park, I/O và một số thông tin môi trường; **sự kiện thực tế phụ thuộc cấu hình và ngưỡng**. JFR mạnh khi cần trả lời câu hỏi “trước, trong và sau spike đã xảy ra điều gì?”, hoặc xem tương quan giữa CPU, GC, lock và code path.

- `default.jfc` thường thích hợp ghi liên tục với overhead thấp; `profile.jfc` thu thập sâu hơn cho khoảng điều tra ngắn và có thể tốn tài nguyên hơn.
- “Sampled” không phải mọi lời gọi method đều được ghi; event dưới ngưỡng hoặc chưa bật có thể không xuất hiện. **Vắng event không chứng minh không có hoạt động.**
- Dùng JDK Mission Control (JMC) để xem timeline, flame graph, allocation và khóa theo thời gian; có thể sàng lọc bằng lệnh `jfr` mà không cần giao diện.

Ví dụ ghi vòng 1 phút vào file khi JVM đang chạy:

```bash
jcmd <pid> JFR.start name=incident settings=profile.jfc duration=60s filename=incident.jfr
jcmd <pid> JFR.check
```

Khi ghi xong và file đã xuất hiện, phân tích:

```bash
jfr summary incident.jfr
jfr print --events jdk.ExecutionSample,jdk.JavaMonitorEnter incident.jfr
```

`jfr summary` cho biết loại event, số lượng, kích thước; `jfr print` xuất các event được lọc. Việc có bản ghi `jdk.JavaMonitorEnter` hay không phụ thuộc profile/ngưỡng và việc tranh chấp thực sự xảy ra trong khoảng ghi.

Nếu cần **ghi vòng đệm liên tục và lấy một lát cắt khi có sự cố**, dùng quy trình khác:

```bash
jcmd <pid> JFR.start name=rolling settings=default.jfc maxage=10m maxsize=200m
jcmd <pid> JFR.dump name=rolling filename=incident-window.jfr maxage=5m
jcmd <pid> JFR.stop name=rolling
```

`JFR.dump` ghi snapshot của recording ra file **mà không tự dừng recording**; `JFR.stop` dừng recording đã đặt tên. Giới hạn `maxage`/`maxsize` chỉ lưu phần gần đây, tránh tạo tệp không kiểm soát. File được tạo theo đường dẫn được JVM đích sử dụng; nên dùng đường dẫn tuyệt đối khi làm việc với service.

JFR hỗ trợ tìm **đường gọi nóng, allocation rate, GC pauses, lock contention kéo dài**. Heap dump bổ sung khả năng xác định **đối tượng còn được giữ lại**; JFR allocation event và heap dump trả lời hai câu hỏi khác nhau: “được tạo ở đâu?” so với “vì sao vẫn còn sống?”.

## 10. Tình huống thực hành Java 17+: request bị đợi monitor

Ví dụ tạo hai thread: `lock-holder` giữ một monitor trong 60 giây; `lock-waiter` chờ vào cùng monitor. Mục đích là **nhìn thấy sự khác biệt giữa triệu chứng, thread state và event JFR**, không mô phỏng toàn bộ server HTTP.

Tạo file **`LockContentionDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class LockContentionDemo {
    private static final Object MONITOR = new Object();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch acquired = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (MONITOR) {
                acquired.countDown();
                try {
                    Thread.sleep(60_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lock-holder");

        Thread waiter = new Thread(() -> {
            synchronized (MONITOR) {
                // Chạy tiếp sau khi holder nhả monitor.
            }
        }, "lock-waiter");

        holder.start();
        acquired.await();
        waiter.start();

        System.out.println("Ready: inspect threads for 60 seconds.");
        holder.join();
        waiter.join();
        System.out.println("Finished.");
    }
}
```

Biên dịch và chạy với JDK 17+ trong terminal thứ nhất:

```bash
javac LockContentionDemo.java
java LockContentionDemo
```

**Stdout của chương trình** (hai dòng, cách nhau khoảng một phút; không tính thông báo của shell/JDK bên ngoài):

```text
Ready: inspect threads for 60 seconds.
Finished.
```

Trong 60 giây chờ, mở terminal thứ hai và chạy:

```bash
jcmd -l
jcmd <pid> Thread.print -l > threads-during-wait.txt
```

Tìm đúng PID có main class `LockContentionDemo`. Trong thread dump lấy khi cả hai thread còn sống, kỳ vọng `lock-holder` ở `TIMED_WAITING` do `Thread.sleep`, còn `lock-waiter` ở `BLOCKED` khi xin vào cùng monitor. Địa chỉ object, tên frame native và thứ tự xuất hiện tùy JVM, vì vậy **không coi dump là stdout cố định**. Nếu lấy quá sớm hoặc sau 60 giây, có thể chưa thấy hoặc không còn thấy `BLOCKED`.

Muốn quan sát cùng tình huống bằng JFR **từ lúc JVM khởi động**, chạy phiên khác:

```bash
java -XX:StartFlightRecording=filename=locks.jfr,settings=profile.jfc,dumponexit=true LockContentionDemo
jfr summary locks.jfr
jfr print --events jdk.JavaMonitorEnter locks.jfr
```

Đợi chương trình kết thúc rồi mới đọc `locks.jfr`. Việc thu được monitor event phụ thuộc cấu hình, ngưỡng và phiên bản JVM; nếu không có event, xem `jfr summary` và profile thay vì kết luận không có chờ lock. Bài demo dùng `sleep` **trong** vùng `synchronized` để chủ động giữ monitor; trong code sản xuất nên giữ critical section ngắn, hạn chế I/O/blocking trong lock.

**Giải thích bằng chứng của demo:**

- **Log/stdout:** xác nhận demo bắt đầu và kết thúc; không định lượng được riêng thời gian chờ lock.
- **Metrics (nếu instrument):** thấy thời gian hoàn thành tác vụ tăng; vẫn chưa chỉ rõ monitor.
- **Thread dump:** cho thấy mối quan hệ `BLOCKED` và `TIMED_WAITING` ở thời điểm chụp.
- **JFR:** có thể thấy monitor contention và mốc sự kiện qua thời gian nếu event được ghi.
- **Heap dump:** không phải lựa chọn ưu tiên vì bài toán không phải giữ object quá lâu.
- **Exception stack trace:** không xuất hiện vì không có exception; điều này không có nghĩa chương trình không bị chậm.

## 11. Chọn bằng chứng theo triệu chứng: ba kịch bản điều tra

### A. p99 latency tăng, CPU và heap không tăng đáng kể

1. **Metrics:** khoanh thời điểm spike, service/instance, RPS, p99, queue depth, số connection và timeout rate. So với baseline.
2. **Log và traceId:** tìm những request chậm, xác định bước nào mất thời gian; phân biệt chậm ở chính JVM và chậm do downstream.
3. **Thread dump 2–3 lần:** nếu nhiều thread `BLOCKED` cùng monitor, `WAITING` trên semaphore/connection pool hoặc cùng stack I/O, lập giả thuyết cụ thể.
4. **JFR trong cửa sổ trùng khớp:** tìm monitor enter, thread park, socket/file I/O và tương quan với spike.
5. **Kết luận có điều kiện:** chỉ gọi là “lock contention gây latency” khi dữ liệu thời gian, thread chờ và nơi giữ lock nhất quán. Nếu trace chỉ ra downstream chậm, mở rộng điều tra ở downstream.

### B. Heap used sau GC tăng qua nhiều giờ

1. **Metrics:** vẽ heap used trước/sau GC, old generation, GC frequency/pause, tải và cache size. Kiểm tra có thay đổi cấu hình hoặc batch job.
2. **Log/JFR:** xác định giai đoạn tăng, hoạt động cấp phát, chỗ tạo object; phân biệt **allocation rate cao** với **retention cao**.
3. **Heap dump có kiểm soát:** đọc dominator tree và path to GC roots của object lớn/tăng bất thường; kiểm tra map/cache/static field/listener/session.
4. **Xác nhận:** so với hành vi kỳ vọng và thời hạn sống dữ liệu; sau sửa, xem đáy heap sau GC có ổn định không. Không kết luận leak chỉ dựa vào class có nhiều instance.

### C. CPU tăng mạnh nhưng không có nhiều exception

1. **Metrics:** xác nhận CPU của JVM hay của cả host, và GC CPU có tăng không; đối chiếu số request/tải.
2. **JFR CPU samples:** xem phương thức và stack có tỷ trọng mẫu cao trong đúng khoảng xảy ra spike; chú ý sample bias.
3. **Thread dump:** dùng bổ trợ nhận diện thread lặp lại ở cùng vùng code, nhưng `RUNNABLE` không tự chứng minh thread tiêu thụ CPU.
4. **Log:** tìm retry loop, xử lý batch bất thường hoặc thay đổi hành vi; kiểm chứng bằng thử nghiệm tải/profiling và kết quả sau thay đổi.

## 12. Những sai lầm phổ biến và cách tránh

| Kết luận vội | Vì sao sai | Kiểm chứng phù hợp |
| --- | --- | --- |
| “Có `ERROR` trong log nên chính dòng đó làm chậm hệ thống.” | Lỗi có thể là **hậu quả** của timeout hoặc nghẽn phía khác. | So timestamp, trace, metrics và JFR/thread dump. |
| “Latency trung bình bình thường nên không chậm.” | Tail latency có thể tăng trong khi average ổn định. | Xem p95/p99, timeout và phân bố theo route. |
| “Một thread `RUNNABLE` tức là đang ăn CPU.” | Trạng thái Java không phản ánh đầy đủ lịch CPU/native I/O. | CPU process/thread và JFR execution samples. |
| “Nhiều `WAITING` nghĩa là deadlock.” | Worker pool rỗi thường ở `WAITING`. | Đọc frame, lock ownership, dump lặp lại và tiến độ công việc. |
| “Heap lớn chứng minh memory leak.” | Cache/tải và chu kỳ GC có thể khiến heap lớn hợp lệ. | Xu hướng sau GC, retention và GC roots. |
| “Heap dump chỉ ra nơi object được tạo.” | Nó tập trung vào **object còn sống và tham chiếu hiện tại**. | JFR allocation stack + heap retained graph. |
| “Không thấy event JFR nghĩa là không xảy ra.” | Event có thể disabled, bị ngưỡng lọc hoặc ngoài cửa sổ ghi. | Kiểm tra cấu hình, `jfr summary` và thời điểm. |
| “Cần thu mọi dump ngay khi sự cố.” | Heap dump có thể gây pause và lộ dữ liệu nhạy cảm. | Bắt đầu bằng metrics/log; chọn bằng chứng ít tác động nhất đủ trả lời câu hỏi. |

## 13. Checklist mang vào một sự cố thực tế

- [ ] Nêu rõ triệu chứng đo được, mức ảnh hưởng, thời điểm, baseline và giả thuyết đang kiểm tra.
- [ ] Xác nhận đúng service, instance, PID, JDK, timezone và phiên bản triển khai.
- [ ] Đọc metrics trước để định vị quy mô, xu hướng và cửa sổ bất thường.
- [ ] Dùng log/trace để nối các request hoặc công việc liên quan; tránh ghi lộ dữ liệu.
- [ ] Chọn stack trace cho lỗi đường gọi, thread dump cho chờ/tranh chấp, heap dump cho giữ object, JFR cho diễn biến CPU/GC/lock/allocation.
- [ ] Ghi tên file, khoảng thời gian, PID, quyền truy cập, impact và kích thước hiện vật.
- [ ] Đối chiếu **ít nhất hai tín hiệu độc lập** trước khi tuyên bố nguyên nhân.
- [ ] Sau thay đổi, xác minh cùng metrics và cùng điều kiện tải đã cải thiện; lưu lại điều chưa chắc chắn.

**Tài liệu đối chiếu chính thức cho JDK 17:**

- [Oracle — `jcmd` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print`, `GC.heap_dump`, `JFR.start`, `JFR.dump`.
- [Oracle — `jfr` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `summary`, `print`, `metadata`.
- [Oracle — Java SE 17 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/): tình huống chẩn đoán và thu thập bằng chứng.

**Điểm cần nhớ:** metrics cho biết *có vấn đề ở đâu và khi nào*; logs/trace cho biết *request hoặc thao tác nào liên quan*; stack trace cho biết *đường gọi*; thread dump cho biết *thread đang làm/chờ gì*; heap dump cho biết *object nào còn được giữ*; JFR cho biết *những sự kiện JVM nào diễn ra trong khoảng thời gian điều tra*. Chúng phát huy tác dụng mạnh nhất khi ghép đúng thời gian và kiểm chứng chéo.