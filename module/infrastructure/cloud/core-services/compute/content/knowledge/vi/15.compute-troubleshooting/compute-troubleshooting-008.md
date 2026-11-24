# Ứng dụng treo: thread dump, deadlock và thời gian chờ phụ thuộc

Một ứng dụng compute có thể vẫn chạy nhưng không còn xử lý request: người dùng thấy màn hình quay liên tục, API không trả lời, queue backlog tăng hoặc health check thất bại. Trạng thái này thường được gọi là *application hang*. Nguyên nhân có thể nằm trong tiến trình như deadlock, thread pool cạn, lock contention hoặc vòng lặp chiếm CPU; cũng có thể nằm ở dependency như database, HTTP service, DNS, storage hoặc message broker.

Để chẩn đoán chính xác, cần kết hợp ba góc nhìn: **thread dump** cho biết các luồng đang thực hiện hoặc chờ điều gì; **deadlock analysis** tìm chu trình chờ tài nguyên không thể tự giải phóng; **dependency timeout analysis** xác định ứng dụng đang chờ dịch vụ bên ngoài ở giai đoạn nào. Bài học này tập trung vào cách thu thập bằng chứng, đọc dấu hiệu và khôi phục dịch vụ an toàn trên workload compute.

## 1. Nhận diện ứng dụng treo

Ứng dụng treo không nhất thiết là process đã chết. Process có thể vẫn tồn tại, port vẫn mở và CPU vẫn thấp, nhưng request không hoàn tất. Một số biểu hiện thường gặp:

- Request mới liên tục timeout hoặc có latency tăng mạnh.
- Health check không nhận được phản hồi trong thời hạn quy định.
- Số request đang xử lý tăng nhưng throughput giảm.
- Queue backlog hoặc tuổi message lâu nhất tăng.
- Thread pool, connection pool hoặc semaphore đạt giới hạn.
- CPU gần 100% do vòng lặp, lock spinning hoặc retry liên tục.
- CPU thấp bất thường vì phần lớn thread đang chờ lock, I/O hoặc dependency.
- Service chỉ phục hồi sau restart, nhưng sự cố lặp lại khi tải tăng.

Cần phân biệt hang với các trạng thái khác:

| Trạng thái | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Process crash | PID biến mất hoặc exit code khác 0 | Crash log, core dump, OOM killer, service manager |
| Application hang | Process còn sống nhưng công việc không tiến triển | Thread dump, lock, pool, dependency |
| Quá tải | Throughput vẫn có nhưng latency và queue tăng theo tải | CPU, memory, thread/connection pool, capacity |
| Dependency outage | Nhiều request dừng ở cùng một dịch vụ ngoài | Timeout, DNS, network, service health |
| Deadlock | Nhóm thread chờ lẫn nhau theo chu trình | Thread dump và lock ownership |
| Resource starvation | Tài nguyên hữu hạn đã bị giữ hết | Thread pool, DB connection, file descriptor, semaphore |

Một chỉ số đơn lẻ không đủ kết luận. CPU thấp có thể là dấu hiệu thread chờ, nhưng cũng có thể là ứng dụng không nhận traffic. CPU cao có thể do xử lý hợp lệ, nhưng cũng có thể do retry storm hoặc vòng lặp vô hạn.

## 2. Thread và thread dump là gì?

Thread là đơn vị thực thi bên trong process. Ứng dụng Java thường có nhiều thread cho request, background job, scheduler, garbage collection và các tác vụ runtime. Mỗi thread có stack riêng, thể hiện chuỗi phương thức đang chạy hoặc điểm mà thread đang chờ.

**Thread dump** là ảnh chụp trạng thái các thread tại một thời điểm, thường bao gồm:

- Tên và ID của thread.
- Trạng thái thread như RUNNABLE, BLOCKED, WAITING hoặc TIMED_WAITING.
- Stack trace của thread.
- Lock hoặc monitor mà thread đang giữ hay chờ.
- Thông tin về synchronizer, tùy công cụ và runtime.
- Thông tin deadlock mà JVM phát hiện được, nếu có.

Thread dump là bằng chứng tại thời điểm thu thập. Một dump đơn lẻ có thể không phân biệt được thread đang chờ bình thường hay bị kẹt lâu dài. Vì vậy, nên lấy nhiều dump cách nhau vài giây để quan sát trạng thái có thay đổi hay không.

## 3. Trạng thái thread trong Java

Các trạng thái Java thường gặp:

| Trạng thái | Ý nghĩa | Dấu hiệu cần chú ý |
|---|---|---|
| RUNNABLE | Thread đang chạy trong JVM hoặc có thể đang chờ tài nguyên ở mức hệ điều hành | Stack lặp lại tại cùng vị trí qua nhiều dump có thể là vòng lặp hoặc native call bị kẹt |
| BLOCKED | Thread đang chờ lấy intrinsic monitor để vào synchronized | Nhiều thread chờ cùng một lock có thể cho thấy lock contention |
| WAITING | Thread chờ vô thời hạn một thread khác hoặc điều kiện được đánh thức | Object.wait, Thread.join, LockSupport.park |
| TIMED_WAITING | Thread chờ có thời hạn | sleep, timed wait, timed park hoặc join có timeout |
| NEW | Thread đã tạo nhưng chưa start | Có thể là trạng thái bình thường trong một số thời điểm |
| TERMINATED | Thread đã kết thúc | Không còn tham gia xử lý |

RUNNABLE không có nghĩa thread chắc chắn đang tiêu thụ CPU. JVM dùng trạng thái này cho thread đang thực thi và một số trường hợp đang chờ tài nguyên ở mức native/OS. Hãy đối chiếu stack, CPU theo thread và nhiều lần lấy dump.

Các thread WAITING cũng không mặc định là lỗi. Thread pool worker chờ queue rỗng, scheduler chờ lịch tiếp theo hoặc thread chờ tín hiệu đều có thể là trạng thái bình thường. Điều quan trọng là thread nào đang giữ tài nguyên cần thiết và request có tiến triển hay không.

## 4. Thu thập thread dump trên JVM

Trước khi restart một JVM đang treo, hãy thu thập thread dump nếu tình trạng cho phép. Việc này giữ lại bằng chứng mà restart sẽ xóa khỏi bộ nhớ.

### 4.1. Dùng jcmd

Tìm PID của JVM và in thread dump:

~~~bash
jcmd -l
jcmd <pid> Thread.print -l > thread-dump-1.txt
~~~

Tùy JDK và quyền người dùng, lệnh attach cần chạy dưới cùng user hoặc có quyền phù hợp với process. Dùng lệnh trợ giúp của jcmd để kiểm tra tùy chọn được phiên bản JVM hỗ trợ.

### 4.2. Dùng jstack

~~~bash
jstack -l <pid> > thread-dump-1.txt
~~~

Tùy phiên bản JDK và trạng thái JVM, jstack có thể không attach được. Không nên liên tục chạy các lệnh attach nặng trên máy đang quá tải; hãy thu thập có kiểm soát và lưu output ra nơi đủ dung lượng.

### 4.3. Dùng tín hiệu SIGQUIT trên Linux

Với HotSpot JVM trên Linux, có thể gửi SIGQUIT:

~~~bash
kill -3 <pid>
~~~

Thông thường JVM in thread dump ra standard error của process, thường được chuyển vào log của service manager hoặc container runtime. SIGQUIT trong trường hợp này yêu cầu JVM xuất dump, không phải tín hiệu kết thúc JVM. Vị trí output phụ thuộc cách service được khởi chạy và redirect stdout/stderr.

### 4.4. Lấy nhiều dump để so sánh

Một quy trình thường dùng là lấy ba dump, cách nhau khoảng 5–10 giây, nếu hệ thống có thể chịu được:

~~~bash
jcmd <pid> Thread.print -l > thread-dump-1.txt
sleep 5
jcmd <pid> Thread.print -l > thread-dump-2.txt
sleep 5
jcmd <pid> Thread.print -l > thread-dump-3.txt
~~~

Khoảng thời gian trên chỉ là ví dụ. Với request có thời gian xử lý dài, có thể cần khoảng cách khác. Mục tiêu là xác định thread có tiếp tục thay đổi stack, lock và trạng thái hay bị giữ nguyên.

Bảo vệ thread dump như dữ liệu vận hành nhạy cảm: stack có thể chứa tên người dùng, URL nội bộ, câu SQL, đường dẫn file hoặc giá trị ứng dụng vô tình đưa vào tên thread/argument. Hạn chế quyền đọc, không đính kèm công khai và áp dụng retention phù hợp.

## 5. Đọc thread dump theo trình tự

Khi mở dump, đừng bắt đầu bằng cách đọc từng dòng từ đầu đến cuối. Hãy xác định dấu hiệu có giá trị cao trước:

1. Tìm phần JVM báo deadlock, nếu có.
2. Đếm thread theo trạng thái và nhóm theo tên/pool.
3. Tìm nhiều thread có stack trace giống nhau.
4. Tìm thread BLOCKED và lock mà chúng đang chờ.
5. Xác định thread nào đang giữ lock đó.
6. Tìm stack liên quan tới network, database, file I/O hoặc pool acquisition.
7. So sánh cùng thread qua các dump để xem stack có tiến triển hay không.
8. Đối chiếu với CPU theo thread, request latency, pool metrics và application log.

Một thread dump có thể rất dài. Dùng công cụ tìm kiếm theo BLOCKED, deadlock, tên pool, tên package hoặc lớp đang được nghi ngờ. Khi phân tích, luôn giữ nguyên tên thread và ID để đối chiếu giữa các dump.

### 5.1. Ví dụ thread đang chờ lock

Một đoạn dump minh họa:

~~~text
"api-worker-17" #82 prio=5 os_prio=0 tid=0x... nid=0x... BLOCKED
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderService.updateInventory(OrderService.java:142)
        - waiting to lock <0x00000006c1234560>
        - locked <0x00000006c1234500>
        at com.example.OrderService.process(OrderService.java:91)
~~~

Thread api-worker-17 đang chờ monitor có ID kết thúc bằng 4560 và đang giữ monitor có ID kết thúc bằng 4500. Cần tìm thread khác đang giữ monitor mà thread này muốn lấy. Nếu nhiều worker cùng chờ một monitor, request có thể xếp hàng dù CPU không cao.

### 5.2. Ví dụ thread chờ dependency

~~~text
"http-client-worker-4" #63 prio=5 os_prio=0 tid=0x... nid=0x... WAITING
   java.lang.Thread.State: TIMED_WAITING
        at java.util.concurrent.CompletableFuture.get(...)
        at com.example.InventoryClient.fetch(InventoryClient.java:88)
        at com.example.OrderService.process(OrderService.java:120)
~~~

Stack cho thấy thread chờ kết quả future. Điều đó chưa chứng minh deadlock. Cần kiểm tra ai hoàn tất future, request tới dependency có timeout hay không, connection pool có cạn không và thread thực hiện callback có còn khả dụng không.

## 6. Deadlock là gì?

Deadlock xảy ra khi hai hay nhiều thread giữ tài nguyên mà thread khác cần, tạo thành chu trình chờ không thể tự phá vỡ. Ví dụ:

- Thread A giữ lock L1 và chờ lock L2.
- Thread B giữ lock L2 và chờ lock L1.
- A không thể tiếp tục để nhả L1 vì đang chờ L2.
- B không thể tiếp tục để nhả L2 vì đang chờ L1.

~~~mermaid
flowchart LR
    A[Thread A giữ Lock L1] -->|chờ| L2[Lock L2]
    L2 --> B[Thread B đang giữ Lock L2]
    B -->|chờ| L1[Lock L1]
    L1 --> A
~~~

Trong chu trình này, không thread nào tự tiến triển. Request sử dụng các thread đó sẽ bị treo hoặc timeout.

### 6.1. Ví dụ deadlock trong Java

Đoạn mã sau minh họa hai luồng lấy hai lock theo thứ tự ngược nhau:

~~~java
public class DeadlockExample {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();

    public static void main(String[] args) {
        Thread first = new Thread(() -> {
            synchronized (LOCK_A) {
                pause();
                synchronized (LOCK_B) {
                    System.out.println("first completed");
                }
            }
        }, "first-thread");

        Thread second = new Thread(() -> {
            synchronized (LOCK_B) {
                pause();
                synchronized (LOCK_A) {
                    System.out.println("second completed");
                }
            }
        }, "second-thread");

        first.start();
        second.start();
    }

    private static void pause() {
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Nếu first-thread lấy LOCK_A trước khi second-thread lấy LOCK_B, sau đó mỗi thread chờ lock còn lại, deadlock có thể xảy ra. Thread.sleep trong ví dụ chỉ làm tăng khả năng tái hiện tình huống; nguyên nhân là thứ tự lấy lock không nhất quán.

### 6.2. Nhận diện deadlock trong thread dump

JVM có thể phát hiện một số chu trình monitor/synchronizer và in phần thông báo như Found one Java-level deadlock. Khi thấy thông báo này:

- Xác định các thread tham gia.
- Ghi lại lock mà mỗi thread đang giữ và đang chờ.
- Tìm đoạn code tương ứng từ stack trace.
- Xác định thứ tự lấy lock ở các code path khác nhau.
- Kiểm tra lock có được giữ trong lúc gọi network, database hoặc callback hay không.

Không có dòng deadlock trong dump không chứng minh ứng dụng không bị treo. Thread pool starvation, dependency timeout, lock contention hoặc deadlock ở thư viện native có thể không được báo bằng cơ chế phát hiện deadlock Java-level.

## 7. Các dạng tắc nghẽn dễ nhầm với deadlock

### 7.1. Lock contention

Nhiều thread tranh cùng một lock nhưng một thread vẫn có thể lấy lock và tiến triển. Đây là contention, không nhất thiết là deadlock. Dấu hiệu là nhiều thread BLOCKED trên cùng monitor và một thread đang giữ lock.

Cách xử lý có thể gồm rút ngắn vùng critical section, giảm chia sẻ trạng thái, phân mảnh lock hoặc dùng cấu trúc dữ liệu concurrent phù hợp. Không nên chỉ tăng số thread vì điều đó có thể làm số thread chờ lock tăng thêm.

### 7.2. Thread pool starvation

Thread pool starvation xảy ra khi tất cả worker trong pool bị chiếm bởi tác vụ đang chờ một công việc khác cần chính pool đó để chạy. Ví dụ, một task trong pool gọi đồng bộ Future.get() cho task con được submit vào cùng pool hữu hạn; nếu mọi worker đều làm vậy, task con không còn worker để chạy.

Dấu hiệu thường gặp:

- Pool active count đạt giới hạn.
- Queue task tăng nhưng throughput không tăng.
- Nhiều thread cùng chờ Future.get, join hoặc semaphore.
- Không có chu trình monitor lock rõ ràng.

Biện pháp: tránh chờ đồng bộ task con trên cùng pool, tách pool theo loại công việc, dùng composition bất đồng bộ hoặc giới hạn mức lồng nhau. Tách pool cũng cần sizing và backpressure; tạo quá nhiều pool có thể làm cạn tài nguyên.

### 7.3. Connection pool exhaustion

Nếu ứng dụng không lấy được connection từ DB/HTTP pool, request có thể chờ trước khi gửi truy vấn hoặc request thật. Nguyên nhân có thể là pool quá nhỏ, connection leak, query chậm hoặc dependency không trả connection.

Kiểm tra active/idle/pending connection, thời gian chờ acquire, số connection bị giữ lâu và log timeout. Tăng pool size khi database đã quá tải có thể làm sự cố nặng hơn.

### 7.4. Queue hoặc semaphore bị nghẽn

Worker có thể chờ semaphore, bounded queue hoặc rate limiter. Nếu producer tạo công việc nhanh hơn consumer xử lý, queue tăng liên tục. Nếu consumer giữ permit quá lâu hoặc không release khi có exception, các thread khác có thể chờ vô hạn.

Kiểm tra queue depth, enqueue/dequeue rate, permit usage, thời gian giữ permit và đường xử lý exception.

## 8. Phân tích thời gian chờ phụ thuộc

Một request có thể chờ nhiều giai đoạn trước khi nhận kết quả. Chỉ đặt một timeout tổng ở lớp ngoài có thể chưa đủ nếu một thao tác bên trong không có timeout hoặc không hỗ trợ cancellation.

Với HTTP client, các giai đoạn có thể gồm:

1. DNS resolution.
2. Chờ lấy connection từ pool.
3. TCP connect.
4. TLS handshake.
5. Gửi request.
6. Chờ response/read.
7. Đọc body và xử lý kết quả.

Với database, các giai đoạn có thể gồm chờ connection, thực hiện query, chờ lock, truyền dữ liệu và commit transaction. Với queue, có thể là chờ message, giữ lease/visibility timeout, xử lý và acknowledge.

### 8.1. Các loại timeout cần phân biệt

| Timeout | Giới hạn điều gì? | Ví dụ lỗi nếu không cấu hình |
|---|---|---|
| DNS timeout | Thời gian phân giải tên | Request treo khi resolver không phản hồi |
| Connection pool acquire timeout | Thời gian chờ connection rảnh | Request xếp hàng khi pool cạn |
| Connect timeout | Thời gian thiết lập TCP | Chờ lâu khi endpoint không reachable |
| TLS handshake timeout | Thời gian thương lượng TLS | Chờ khi proxy hoặc peer không hoàn tất handshake |
| Read/response timeout | Thời gian chờ dữ liệu phản hồi | Thread bị giữ khi server xử lý hoặc mạng bị treo |
| Write timeout | Thời gian gửi dữ liệu | Upload hoặc socket write bị kẹt |
| Query/statement timeout | Thời gian thực thi câu lệnh DB | Query hoặc lock wait kéo dài |
| Request/call deadline | Tổng thời gian cho một thao tác nghiệp vụ | Các bước cộng dồn vượt thời gian client chấp nhận |
| Transaction timeout | Thời gian tối đa của transaction | Transaction giữ lock/connection quá lâu |

Tên gọi và ý nghĩa chính xác phụ thuộc thư viện. Một read timeout có thể là timeout giữa hai lần đọc dữ liệu thay vì giới hạn tổng thời gian của toàn bộ response. Cần đọc tài liệu client và kiểm thử hành vi timeout thực tế.

### 8.2. Timeout theo deadline tổng

Giả sử API có deadline 2 giây. Nếu mỗi dependency được phép chờ 2 giây độc lập, một request gọi tuần tự ba dịch vụ có thể kéo dài nhiều giây. Nên truyền deadline còn lại qua các tầng và phân bổ ngân sách thời gian cho từng bước.

Ví dụ minh họa:

| Giai đoạn | Ngân sách ví dụ |
|---|---:|
| Xác thực và xử lý đầu vào | 150 ms |
| Chờ connection và gọi service A | 500 ms |
| Gọi database | 700 ms |
| Hoàn tất response và dự phòng | 300 ms |
| Tổng | 1.650 ms |

Phần còn lại của deadline dành cho biến động và overhead. Đây chỉ là ví dụ; timeout cần dựa trên SLO, latency thực tế và khả năng phục hồi của dependency. Không nên cộng các timeout độc lập vượt quá deadline của request.

### 8.3. Retry có thể làm sự cố nặng hơn

Retry hữu ích với lỗi tạm thời, nhưng retry không giới hạn hoặc đồng loạt có thể tạo retry storm. Khi dependency đã quá tải, nhiều client retry cùng lúc làm tăng tải và kéo dài sự cố.

Nguyên tắc:

- Chỉ retry lỗi được xác định là tạm thời.
- Dùng exponential backoff và jitter.
- Đặt giới hạn số lần retry và tổng retry budget.
- Chỉ retry thao tác idempotent hoặc có idempotency key.
- Tôn trọng deadline còn lại; không bắt đầu retry khi không còn thời gian hữu ích.
- Không retry đồng thời ở mọi tầng nếu điều đó nhân số request.
- Ghi nhận số lần retry và nguyên nhân để phát hiện retry storm.

## 9. Circuit breaker, bulkhead và backpressure

Timeout giới hạn thời gian chờ; các mẫu thiết kế khác giúp ngăn một dependency lỗi làm sập toàn bộ ứng dụng.

### 9.1. Circuit breaker

Circuit breaker có các trạng thái phổ biến:

- **Closed:** cho request đi qua và theo dõi lỗi.
- **Open:** tạm chặn request tới dependency khi tỷ lệ lỗi vượt ngưỡng.
- **Half-open:** cho một số request thử để xác định dependency đã phục hồi chưa.

Circuit breaker cần ngưỡng, cửa sổ đo, thời gian open và chính sách half-open phù hợp. Nếu cấu hình quá nhạy, hệ thống có thể chặn dependency khỏe; nếu quá lỏng, nó không ngăn được sự cố lan rộng.

### 9.2. Bulkhead

Bulkhead tách tài nguyên theo dependency hoặc loại công việc. Ví dụ, API gọi dịch vụ thanh toán và dịch vụ đề xuất dùng hai pool riêng. Khi dịch vụ đề xuất chậm, nó không chiếm hết worker dành cho thanh toán.

Bulkhead có thể áp dụng cho thread pool, connection pool, semaphore, queue hoặc giới hạn concurrency. Tách biệt cần đi kèm quota và capacity planning.

### 9.3. Backpressure

Backpressure giới hạn tốc độ nhận công việc khi downstream không theo kịp. Thay vì nhận vô hạn rồi để queue và memory tăng, hệ thống có thể giảm producer rate, từ chối sớm với mã phù hợp hoặc đưa công việc vào queue bền vững có giới hạn.

Theo dõi queue depth, queue age, rejection rate và consumer throughput để xác định điểm nghẽn.

## 10. Công cụ hệ điều hành để bổ sung bằng chứng

Thread dump cho thấy trạng thái bên trong JVM, nhưng cần thêm dữ liệu từ OS để biết process đang sử dụng CPU, memory, disk và network ra sao.

### Linux

~~~bash
# Tổng quan process và CPU/memory
top -H -p <pid>

# Danh sách thread của process
ps -L -p <pid> -o pid,tid,psr,stat,pcpu,comm

# CPU và I/O theo khoảng thời gian
pidstat -p <pid> -t 1
iostat -xz 1

# Memory và paging
vmstat 1

# Socket và trạng thái kết nối
ss -tanp

# Giới hạn file descriptor
cat /proc/<pid>/limits
ls /proc/<pid>/fd | wc -l
~~~

top -H và ps -L giúp xác định thread nào tiêu thụ CPU. pidstat có thể cho thấy thread/process hoạt động theo thời gian. iostat giúp nhận diện storage latency; ss hỗ trợ xem kết nối TCP và trạng thái socket. Cần cài công cụ tương ứng và chạy với quyền đủ để xem process.

### Windows

Có thể dùng Task Manager, Resource Monitor, Performance Monitor và Process Explorer để xem CPU theo thread, handle, wait chain và I/O. Event Viewer giúp đối chiếu service failure và lỗi hệ điều hành. Với ứng dụng JVM, vẫn nên lấy thread dump bằng công cụ JDK phù hợp trên Windows.

Không nên kết luận deadlock chỉ từ CPU thấp hoặc số thread cao. Hãy ghép OS metrics với thread dump và dependency telemetry.

## 11. Quy trình điều tra ứng dụng treo

Một quy trình thực tế nên giữ bằng chứng trước khi thay đổi trạng thái process.

### Bước 1: Xác định phạm vi và tác động

- Sự cố ảnh hưởng một instance hay toàn bộ service?
- Tất cả request hay chỉ một endpoint/job?
- Bắt đầu lúc nào và có trùng với deploy, scale, restart hoặc thay đổi cấu hình không?
- Error rate, latency, throughput và queue backlog thay đổi ra sao?
- Có backend khỏe khác để chuyển traffic không?

### Bước 2: Kiểm tra dependency và resource pool

- DB connection pool có pending request hoặc active connection đạt max không?
- HTTP client pool có connection đang leased quá lâu không?
- DNS, connect, TLS và response latency có bất thường không?
- Queue depth, message age và consumer count có thay đổi không?
- Có semaphore, rate limiter hoặc bounded queue bị đầy không?

### Bước 3: Thu thập thread dump nhiều lần

- Ghi PID, thời điểm, host/instance ID và phiên bản ứng dụng.
- Lấy 2–3 thread dump cách nhau một khoảng phù hợp.
- Lưu file với quyền hạn chế.
- Không restart ngay nếu có thể thu thập bằng chứng an toàn.
- Nếu attach không thành công, ghi lại lỗi và dùng phương pháp phù hợp khác.

### Bước 4: Phân nhóm thread

- Tìm deadlock report.
- Đếm RUNNABLE, BLOCKED, WAITING, TIMED_WAITING.
- Nhóm stack giống nhau theo pool và call site.
- Tìm thread giữ lock, chờ lock hoặc chờ future.
- Xem thread nào tiêu thụ CPU cao qua OS metrics.

### Bước 5: Liên kết với log và trace

Dùng request ID, trace ID, thread name, timestamp và instance ID để tìm request cuối cùng. Kiểm tra log cho biết request đang chờ DB, HTTP client, queue, DNS hay lock. Trace có thể cho thấy span nào chiếm phần lớn thời gian.

### Bước 6: Chọn biện pháp giảm tác động

Tùy nguyên nhân, có thể chuyển traffic khỏi instance, tạm giảm concurrency, ngừng nhận job mới, mở rộng capacity, giảm tải dependency hoặc restart có drain. Không tăng thread pool, connection pool hoặc timeout một cách mù quáng; điều đó có thể đẩy áp lực sang tài nguyên khác.

### Bước 7: Xác minh sau khắc phục

Theo dõi latency, error rate, throughput, active threads, pool wait time, queue age và dependency health. Xác nhận request mới hoàn tất và backlog giảm. Lưu bằng chứng trước/sau để phục vụ phân tích nguyên nhân gốc.

## 12. Ví dụ điều tra: API treo do DB connection pool cạn

Giả sử API Java bắt đầu timeout sau khi lưu lượng tăng. CPU chỉ khoảng 25%, số thread HTTP worker gần đạt giới hạn và DB connection pool báo active=max, pending tăng.

Một số thread dump có nhiều worker ở stack tương tự:

~~~text
"http-nio-8080-exec-31" #91
   java.lang.Thread.State: TIMED_WAITING
        at java.util.concurrent.locks.AbstractQueuedSynchronizer...
        at com.zaxxer.hikari.pool.HikariPool.getConnection(...)
        at com.example.OrderRepository.load(OrderRepository.java:74)
        at com.example.OrderService.getOrder(OrderService.java:52)
~~~

Đây là dấu hiệu worker đang chờ connection từ pool. Chưa đủ để kết luận pool leak. Cần kiểm tra:

1. Connection active có được giữ bởi transaction dài hoặc query chậm không?
2. Có đường code nào không đóng connection/result set khi exception không?
3. Database có lock wait, CPU cao hoặc số connection gần giới hạn không?
4. Connection acquire timeout có được cấu hình không?
5. Thread dump có thread khác đang giữ connection nhưng chờ HTTP call hoặc lock không?
6. Pool metrics có cho thấy connection được trả về sau khi request hoàn tất không?

Biện pháp có thể là sửa connection leak, tối ưu query, rút ngắn transaction hoặc giới hạn concurrency. Chỉ tăng pool size khi database còn capacity và giới hạn kết nối tổng thể cho phép. Nếu DB đã quá tải, tăng connection có thể làm latency tệ hơn.

## 13. Ví dụ điều tra: deadlock do thứ tự lock

Giả sử một API có latency tăng đột ngột, request không hoàn tất và CPU gần như idle. Ba thread dump cho thấy hai thread giữ nguyên trạng thái:

- inventory-worker-1 giữ lock Inventory và chờ lock Order.
- order-worker-2 giữ lock Order và chờ lock Inventory.

Nếu JVM dump xác nhận chu trình deadlock, việc chờ thêm thường không giúp hai thread tự phục hồi. Cần giữ thread dump, xác định code path và giảm tác động bằng cách chuyển traffic hoặc restart instance theo quy trình an toàn nếu không có cách phục hồi tại runtime.

Khắc phục lâu dài:

- Quy định thứ tự lấy lock nhất quán ở mọi code path.
- Không gọi network/database khi đang giữ lock nội bộ.
- Giữ critical section ngắn.
- Tránh gọi callback hoặc code không kiểm soát trong vùng synchronized.
- Dùng timeout/try-lock khi nghiệp vụ cho phép và xử lý trường hợp không lấy được lock.
- Viết kiểm thử concurrency và theo dõi lock contention trong môi trường tải đại diện.

## 14. Phòng ngừa ứng dụng treo

Thiết kế ứng dụng nên giới hạn thời gian chờ và tài nguyên từ đầu:

- Đặt timeout rõ ràng cho DNS, pool acquisition, connect, TLS, read/write, query và request.
- Truyền deadline còn lại giữa các service thay vì đặt timeout độc lập không giới hạn.
- Dùng retry có backoff, jitter và giới hạn; tránh retry không idempotent.
- Tách thread pool và connection pool theo dependency/loại workload khi cần.
- Giới hạn queue, concurrency và số request in-flight.
- Tránh chờ đồng bộ trên task con của cùng thread pool hữu hạn.
- Không giữ lock trong lúc gọi dependency bên ngoài.
- Thiết kế job idempotent, checkpoint và cancellation.
- Thiết lập graceful shutdown để drain request và worker trước restart.
- Theo dõi pool utilization, wait time, active thread, blocked thread và queue age.
- Dùng load test để tìm ngưỡng concurrency và điểm bão hòa trước production.

### 14.1. Cấu hình timeout theo SLO

Timeout nên dựa trên SLO và latency phân vị của dependency, không chọn ngẫu nhiên. Ví dụ, nếu SLO API là 1 giây, không thể để một dependency có read timeout 10 giây mà không có cơ chế hủy hoặc deadline tổng. Cần phân bổ ngân sách thời gian cho từng bước, dành phần dự phòng cho serialization, network và response.

Timeout quá ngắn có thể gây lỗi giả khi tải bình thường tăng nhẹ; timeout quá dài làm thread và connection bị giữ lâu. Hãy đo p50, p95, p99, timeout rate và retry rate trước khi điều chỉnh.

### 14.2. Quan sát thread và pool

Các metric hữu ích cho JVM service:

- Thread count theo trạng thái và tên pool.
- Active/idle thread và queue size của executor.
- Rejected task count.
- Lock contention hoặc monitor blocked time khi công cụ hỗ trợ.
- DB/HTTP pool active, idle, pending và acquire latency.
- Request in-flight, latency và timeout theo dependency.
- GC pause, heap occupancy và allocation rate.
- CPU theo process/thread và OS load average.

Nếu thread count tăng liên tục, cần xem thread leak hoặc pool không giới hạn. Nếu thread count ổn định nhưng active worker chạm trần và queue tăng, có thể là saturation. Nếu nhiều thread chờ cùng một lock, hãy phân tích lock owner.

## 15. An toàn khi thu thập và xử lý bằng chứng

Thread dump, heap dump, core dump và log có thể chứa dữ liệu nhạy cảm. Trước khi thu thập hoặc chia sẻ:

- Lưu trong thư mục chỉ nhóm xử lý sự cố được đọc.
- Không đưa dump lên ticket hoặc kho công khai.
- Không gửi nguyên file cho bên ngoài khi chưa kiểm tra chính sách dữ liệu.
- Giới hạn thời gian lưu và xóa bản sao sau khi hết mục đích.
- Ghi nhận thời điểm, PID, instance ID, phiên bản JVM và người thu thập.
- Tránh chạy profiler hoặc dump nặng khi hệ thống đang ở trạng thái rất thiếu tài nguyên.
- Heap dump có thể lớn và chứa object nhạy cảm; chỉ tạo khi có giả thuyết memory cụ thể và đủ dung lượng.

Khi cần restart khẩn cấp để khôi phục dịch vụ, hãy cân bằng giữa việc giữ bằng chứng và tác động tới người dùng. Nếu có thể, thu thập nhanh các thread dump và metrics tối thiểu trước khi restart.

## 16. Checklist chẩn đoán ứng dụng treo

- [ ] Đã xác định phạm vi, thời điểm bắt đầu và workload bị ảnh hưởng.
- [ ] Đã đối chiếu deploy/change, log, metrics và traces.
- [ ] Đã kiểm tra CPU, memory, disk I/O, network và process/thread count.
- [ ] Đã kiểm tra thread pool, DB/HTTP connection pool, queue và semaphore.
- [ ] Đã thu thập nhiều thread dump với timestamp và PID rõ ràng.
- [ ] Đã tìm deadlock report, thread BLOCKED và lock owner.
- [ ] Đã tìm các nhóm thread có stack giống nhau hoặc chờ future/dependency.
- [ ] Đã kiểm tra DNS, pool acquire, connect, TLS, read/write và query timeout.
- [ ] Đã xác minh retry, backoff, deadline và cancellation.
- [ ] Đã kiểm tra idempotency/checkpoint của worker nếu có job bị gián đoạn.
- [ ] Đã chọn biện pháp giảm tác động phù hợp và tránh tăng pool mù quáng.
- [ ] Đã xác minh latency, error rate, throughput và backlog sau khắc phục.
- [ ] Thread dump/log được bảo vệ và lưu theo chính sách.
- [ ] Đã ghi nguyên nhân gốc, hành động sửa và cách phòng ngừa tái diễn.

## 17. Kết luận

Ứng dụng treo có thể bắt nguồn từ deadlock, lock contention, thread pool starvation, connection pool exhaustion hoặc dependency chậm. Thread dump cho biết thread đang chạy hay chờ ở đâu; nhiều dump liên tiếp giúp phân biệt trạng thái tạm thời với trạng thái không tiến triển. Deadlock cần được xác nhận bằng chu trình lock và code path; thread chờ dependency cần được đối chiếu với timeout, pool metrics, log và trace.

Để xử lý hiệu quả, hãy giữ bằng chứng trước restart khi có thể, kiểm tra cả JVM lẫn hệ điều hành, xác định đúng tài nguyên đang bị giữ và áp dụng deadline cho mọi dependency. Kết hợp lock ordering, pool isolation, bounded queue, retry có giới hạn, backpressure và graceful shutdown giúp workload compute tránh bị treo dây chuyền và phục hồi có kiểm soát.
