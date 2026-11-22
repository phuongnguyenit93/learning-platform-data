# Thread dump và chẩn đoán JVM bằng jstack

## 1. Thread dump là gì?

**Thread dump** là ảnh chụp trạng thái các thread của một tiến trình JVM tại một thời điểm. Nó thường chứa tên thread, trạng thái, stack trace của từng thread và thông tin về monitor hoặc lock mà thread đang giữ hay đang chờ.

Thread dump giúp điều tra:

- Ứng dụng phản hồi chậm hoặc bị treo.
- Thread bị BLOCKED khi chờ monitor.
- Deadlock giữa hai hoặc nhiều thread.
- Một thread chạy CPU cao hoặc lặp liên tục.
- Thread pool cạn worker, queue tăng hoặc request không hoàn tất.
- Tắc nghẽn khi truy cập database, network, file hoặc dịch vụ ngoài.
- Vấn đề đồng bộ trong ứng dụng dùng platform thread hoặc virtual thread.

Thread dump chỉ phản ánh một thời điểm. Một snapshot đơn lẻ có thể không đủ để kết luận nguyên nhân; nên so sánh nhiều snapshot cùng với CPU, log, metric và dữ liệu thời gian thực.

## 2. jstack là gì và khi nào nên dùng?

`jstack` là công cụ dòng lệnh trong JDK để attach vào một JVM đang chạy và in stack trace của các Java thread cùng một số thread nội bộ của VM. Công cụ cũng thực hiện phát hiện deadlock.

Trong JDK 24, cú pháp hiển thị bởi `jstack -h` là:

```text
Usage:
    jstack [-l][-e] <pid>

Options:
    -l  long listing. Prints additional information about locks
    -e  extended listing. Prints additional information about threads
    -? -h --help -help to print this help message
```

`jstack` hữu ích khi cần lấy nhanh thread dump từ một process đã biết PID, nhất là khi ứng dụng đang treo hoặc không có console tương tác.

Tuy nhiên, Oracle đánh dấu `jstack` là công cụ experimental/unsupported và khuyến nghị dùng `jcmd` cho chẩn đoán JVM mới vì có thêm chức năng và mức overhead thấp hơn. Hãy biết cách dùng `jstack` vì nó vẫn xuất hiện trong nhiều quy trình vận hành, nhưng ưu tiên `jcmd Thread.print` khi phù hợp với JDK đang chạy.

Tài liệu: [Oracle Java SE 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html).

## 3. Chuẩn bị trước khi lấy thread dump

Trước khi attach vào JVM, xác định đúng process và môi trường:

1. Xác định hostname hoặc container đang chạy ứng dụng.
2. Xác định PID hiện tại, không dùng PID cũ từ lần restart trước.
3. Xác định JDK/JVM vendor và phiên bản đang chạy.
4. Dùng tài khoản có quyền truy cập tiến trình; trên nhiều hệ điều hành, tài khoản chẩn đoán cần cùng effective user/group với tài khoản chạy JVM.
5. Chọn thư mục lưu dump có đủ dung lượng và quyền ghi.
6. Ghi lại thời điểm, triệu chứng, request hoặc job đang bị ảnh hưởng.

Có thể dùng `jps -l` để tìm JVM trên cùng môi trường:

```bash
jps -l
```

Nếu process nằm trong Docker hoặc Kubernetes, chạy công cụ trong container/pod hoặc xác định PID theo process namespace tương ứng. PID nhìn từ host có thể khác PID trong container.

Nếu có nhiều JDK, hãy dùng công cụ `jstack` hoặc `jcmd` từ JDK phù hợp với runtime đang chạy. Kiểm tra phiên bản công cụ:

```bash
jstack -h
jcmd -h
java -version
```

Không coi việc `jps` không hiển thị process là bằng chứng JVM đã dừng; cần xác minh bằng process manager hoặc công cụ hệ điều hành nếu cần.

## 4. Lấy thread dump bằng jstack

Cú pháp cơ bản:

```bash
jstack <PID>
```

Ví dụ:

```bash
jstack 18420
```

Lệnh attach vào JVM có PID 18420 và in thread dump ra standard output của terminal.

Để xem thêm thông tin lock:

```bash
jstack -l 18420
```

Tùy chọn `-l` yêu cầu công cụ tìm ownable synchronizer và in thêm thông tin về các lock thuộc `java.util.concurrent.locks`. Nếu bỏ `-l`, thread dump vẫn có thông tin monitor nhưng không có đầy đủ thông tin ownable synchronizer.

Để xem extended thread information:

```bash
jstack -e 18420
```

Trên JDK 24, `-e` có thể bổ sung các trường thông tin như CPU time, elapsed time, lượng bộ nhớ đã cấp phát và số class được định nghĩa, tùy khả năng của JVM.

Có thể kết hợp hai tùy chọn:

```bash
jstack -l -e 18420
```

Luôn chạy `jstack -h` trên đúng JDK đang dùng để xác nhận tùy chọn được hỗ trợ. Không sao chép tùy chọn từ tài liệu JDK cũ sang JDK mới mà chưa kiểm tra.

## 5. Lưu thread dump vào file

`jstack` mặc định in kết quả ra stdout. Có thể chuyển hướng để lưu lại phục vụ so sánh và phân tích:

Linux/macOS:

```bash
jstack -l <PID> > thread-dump-01.txt 2>&1
```

Windows PowerShell:

```powershell
jstack -l <PID> | Out-File -Encoding utf8 thread-dump-01.txt
```

Đặt tên file theo service, thời điểm và số thứ tự để dễ đối chiếu, ví dụ:

```text
orders-api_2026-11-10_191500_dump-01.txt
orders-api_2026-11-10_191510_dump-02.txt
orders-api_2026-11-10_191520_dump-03.txt
```

Nên giữ ít nhất ba snapshot trong một lần điều tra khi triệu chứng có tính lặp hoặc thay đổi theo thời gian. Khoảng cách 5–10 giây là điểm bắt đầu thực tế; điều chỉnh theo tốc độ sự cố và chi phí attach. Không chạy lệnh liên tục với tần suất cao trên hệ thống đang quá tải.

Thread dump có thể chứa tên thread, tên class, package, đường dẫn và thông tin kiến trúc nội bộ. Lưu và chia sẻ theo chính sách bảo mật của tổ chức.

## 6. Dùng jcmd Thread.print như lựa chọn ưu tiên

`jcmd` là công cụ chẩn đoán đa năng được khuyến nghị cho các JVM hiện đại. Trước tiên, xem process:

```bash
jcmd -l
```

Lấy thread dump:

```bash
jcmd <PID> Thread.print
```

In thêm thông tin lock:

```bash
jcmd <PID> Thread.print -l
```

In extended thread information:

```bash
jcmd <PID> Thread.print -e
```

Trước khi dùng một diagnostic command, có thể hỏi JVM mục tiêu về cú pháp hỗ trợ:

```bash
jcmd <PID> help Thread.print
```

Trong JDK 24, `Thread.print` có impact được xếp loại Medium và chi phí phụ thuộc số lượng thread. Với ứng dụng có rất nhiều thread, hãy theo dõi thời gian thực thi và ảnh hưởng trong lúc capture.

Có thể lưu thread dump ra file bằng `Thread.dump_to_file`:

```bash
jcmd <PID> Thread.dump_to_file -format=plain thread-dump.txt
```

Hoặc dùng JSON cho công cụ phân tích tự động:

```bash
jcmd <PID> Thread.dump_to_file -format=json thread-dump.json
```

Tùy chọn `-overwrite` cho phép ghi đè file đã tồn tại. Chỉ dùng khi chủ đích ghi đè đã rõ ràng; nếu không, chọn tên file mới để giữ bằng chứng của lần capture trước.

## 7. Cách đọc cấu trúc một thread dump

Một thread dump thường có phần header mô tả thời điểm và JVM, sau đó là các entry của từng thread.

Ví dụ rút gọn:

```text
2026-11-10 19:15:00
Full thread dump OpenJDK 64-Bit Server VM (24.0.2+12 mixed mode):

"blocked-worker" #18 prio=5 os_prio=0 tid=0x000001 nid=0x42 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.OrderService.reserve(OrderService.java:84)
    at com.example.OrderController.submit(OrderController.java:51)
    - waiting to lock <0x00000001> (a java.lang.Object)

"lock-owner" #17 prio=5 os_prio=0 tid=0x000002 nid=0x41 waiting on condition
   java.lang.Thread.State: WAITING (parking)
    at java.util.concurrent.CountDownLatch.await(CountDownLatch.java:230)
    at com.example.OrderService.holdReservation(OrderService.java:112)
```

Đây là ví dụ minh họa cấu trúc, không phải output cố định của một JVM cụ thể.

Các trường thường gặp:

| Trường | Ý nghĩa |
|---|---|
| Tên trong dấu ngoặc kép | Tên thread do ứng dụng hoặc JVM đặt |
| `#18` | Thread ID ở mức Java trong dump |
| `daemon` | Thread daemon; không tự giữ JVM sống khi các non-daemon thread đã kết thúc |
| `prio` | Priority của thread |
| `tid` | Địa chỉ cấu trúc thread trong JVM |
| `nid` | Native thread ID do hệ điều hành cấp |
| `java.lang.Thread.State` | Trạng thái thread theo Java |
| `at ...` | Một frame trong stack trace, thường gồm class, method và file/dòng |
| `- locked <...>` | Object monitor mà thread đang giữ |
| `- waiting to lock <...>` | Monitor mà thread đang chờ để vào synchronized block/method |

`tid` và `nid` là thông tin phục vụ chẩn đoán. Không nhầm `nid` với thread ID Java; trên một số hệ điều hành có thể dùng native thread ID để đối chiếu với công cụ hệ điều hành.

Stack trace được đọc từ frame trên xuống dưới: frame đầu thường là vị trí hiện tại hoặc vị trí đang chờ của thread; các frame tiếp theo cho biết đường gọi đã dẫn tới đó. Nếu class được biên dịch có line number (mặc định), số dòng giúp tìm đúng mã nguồn.

## 8. Hiểu các trạng thái thread

Các trạng thái trong `java.lang.Thread.State`:

| Trạng thái | Ý nghĩa | Dấu hiệu thường gặp |
|---|---|---|
| `NEW` | Thread đã tạo nhưng chưa start | Chưa có stack thực thi |
| `RUNNABLE` | Thread đang thực thi trong JVM hoặc sẵn sàng chạy | Stack có thể nằm trong code Java hoặc native |
| `BLOCKED` | Thread chờ lấy intrinsic monitor | `waiting to lock`, `on object monitor` |
| `WAITING` | Thread chờ vô thời hạn một hành động từ thread khác | `Object.wait`, `LockSupport.park`, `CountDownLatch.await`, `join` không timeout |
| `TIMED_WAITING` | Thread chờ có thời hạn | `Thread.sleep`, `wait(timeout)`, `parkNanos`, `join(timeout)` |
| `TERMINATED` | Thread đã kết thúc | Không còn là thread đang hoạt động |

Một số điểm dễ hiểu nhầm:

- `RUNNABLE` không đồng nghĩa chắc chắn CPU đang chạy. Thread có thể đang ở native call hoặc chờ I/O ở tầng hệ điều hành.
- `BLOCKED` là trạng thái chờ intrinsic monitor, thường xuất hiện khi vào `synchronized`.
- `WAITING` và `TIMED_WAITING` không tự động là lỗi. Worker thread chờ queue hoặc thread nền chờ tín hiệu là hành vi bình thường.
- `WAITING` do `LockSupport.park` thường liên quan `ReentrantLock`, `Condition`, `ForkJoinPool` hoặc cơ chế đồng bộ khác.
- Không thể kết luận deadlock chỉ từ số lượng thread `BLOCKED`; cần xem ai đang giữ lock, ai đang chờ lock và chuỗi phụ thuộc.

Khi điều tra CPU cao, tìm thread `RUNNABLE` có stack giống nhau qua nhiều snapshot và đối chiếu với CPU usage của process. Khi điều tra latency, tìm các thread lặp lại ở cùng lock, I/O call, queue wait hoặc database driver.

## 9. Phân tích monitor và lock

Một phần quan trọng của thread dump là quan hệ giữa thread và lock.

Các dòng thường gặp:

```text
- locked <0x00000001> (a java.lang.Object)
- waiting to lock <0x00000002> (a java.lang.Object)
- waiting on <0x00000003> (a java.lang.Object)
- parking to wait for <0x00000004> (a java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject)
```

Cách đọc:

- `locked`: thread hiện đang sở hữu monitor đó.
- `waiting to lock`: thread chưa vào được synchronized block/method vì monitor đang do thread khác giữ.
- `waiting on`: thread đang chờ trên monitor, thường qua `Object.wait()`. Khi gọi `wait`, thread nhả monitor và chỉ tiếp tục sau khi được notify/unpark theo cơ chế tương ứng và lấy lại lock.
- `parking to wait for`: thread đang park để chờ synchronizer hoặc tín hiệu.

Nếu có nhiều thread cùng chờ một lock:

1. Tìm dòng `waiting to lock` hoặc `parking`.
2. Tìm thread đang sở hữu lock hoặc synchronizer.
3. Xem stack của thread sở hữu lock để biết nó đang thực hiện công việc gì.
4. Kiểm tra lock có bị giữ quá lâu, có gọi I/O trong vùng synchronized hay không.
5. So sánh nhiều dump để xác định tình trạng có kéo dài hay chỉ là tranh chấp ngắn hạn.

Với `ReentrantLock` hoặc các lock trong `java.util.concurrent`, dùng `jstack -l` hoặc `jcmd Thread.print -l` để có thêm thông tin ownable synchronizer.

## 10. Phát hiện deadlock

Deadlock xảy ra khi một nhóm thread chờ lẫn nhau theo vòng phụ thuộc, khiến không thread nào trong vòng có thể tiếp tục.

Ví dụ logic:

- Thread A giữ Lock 1 và chờ Lock 2.
- Thread B giữ Lock 2 và chờ Lock 1.
- A không thể tiếp tục cho tới khi B nhả Lock 2.
- B không thể tiếp tục cho tới khi A nhả Lock 1.

Một đoạn báo cáo deadlock có thể trông như sau:

```text
Found one Java-level deadlock:
=============================
"worker-A":
  waiting to lock monitor <0x00000001>,
  which is held by "worker-B"
"worker-B":
  waiting to lock monitor <0x00000002>,
  which is held by "worker-A"

Found 1 deadlock.
```

Đây là ví dụ minh họa. Output thực tế sẽ có ID monitor, loại object và stack trace cụ thể.

Khi thấy báo cáo deadlock:

1. Xác định tất cả thread trong vòng.
2. Đối chiếu lock mà từng thread đang giữ với lock mà nó đang chờ.
3. Tìm vị trí mã nguồn trong stack trace.
4. Kiểm tra thứ tự acquire lock ở các đường code khác nhau.
5. Sửa bằng cách thống nhất thứ tự lấy lock, giảm vùng critical section hoặc dùng thiết kế đồng bộ phù hợp.
6. Chạy lại test cạnh tranh và kiểm tra bằng thread dump mới.

JVM có thể phát hiện nhiều deadlock Java-level liên quan monitor và các synchronizer mà nó nhận diện. Không có thông báo deadlock không chứng minh hệ thống hoàn toàn không có vấn đề liveness: một thread có thể chờ mãi một latch không được mở, một future không hoàn tất, một message không tới hoặc một I/O không trả về.

## 11. Chẩn đoán ứng dụng treo hoặc phản hồi chậm

Một quy trình hữu ích là lấy nhiều dump thay vì chỉ một:

```bash
jcmd <PID> Thread.print -l > dump-01.txt
jcmd <PID> Thread.print -l > dump-02.txt
jcmd <PID> Thread.print -l > dump-03.txt
```

Chạy các lệnh cách nhau một khoảng ngắn, chẳng hạn 5–10 giây, rồi so sánh cùng thread qua từng file.

Các mẫu thường gặp:

| Mẫu qua nhiều dump | Khả năng cần điều tra |
|---|---|
| Một thread `RUNNABLE` giữ nguyên stack và CPU tăng | Vòng lặp, tính toán dài, retry nóng hoặc xử lý quá nhiều dữ liệu |
| Nhiều thread `BLOCKED` cùng chờ một monitor | Lock contention hoặc critical section giữ quá lâu |
| Nhiều thread chờ ở cùng JDBC/socket read | Database hoặc dịch vụ ngoài chậm, pool hoặc network có vấn đề |
| Nhiều worker `WAITING` ở queue | Queue rỗng có thể bình thường; nếu request tồn đọng thì kiểm tra producer/consumer và worker pool |
| Thread `TIMED_WAITING` trong sleep | Có thể là polling, backoff hoặc lịch chạy định kỳ; kiểm tra tần suất và thời gian chờ |
| Main thread chờ `Future.get()` | Tìm task tương ứng và thread đang thực thi task đó |
| Tất cả request thread đều chờ connection pool | Kiểm tra số connection, leak, transaction kéo dài và thời gian query |

Với thread `RUNNABLE` có stack không đổi, Oracle khuyến nghị xem xét lấy thêm dump để xác định thread có đang loop liên tục hay không. Nếu vẫn không rõ, có thể dùng `jhsdb jstack --mixed` để xem thêm native frame trong trường hợp phù hợp.

Đừng quy mọi trạng thái `RUNNABLE` thành CPU spike. Kết hợp thread dump với process CPU, native stack, log và metric để xác nhận.

## 12. Lấy thread dump khi không truy cập được console

Nếu ứng dụng chạy nền hoặc output console được chuyển hướng, có thể dùng `jstack` hoặc `jcmd`.

Trên Linux, HotSpot hỗ trợ gửi `SIGQUIT` để yêu cầu JVM in thread dump ra standard output của process:

```bash
kill -QUIT <PID>
```

Trên Windows, tại console của ứng dụng có thể dùng tổ hợp `Ctrl+Break` để yêu cầu HotSpot in thread dump.

Lệnh gửi tín hiệu không đồng nghĩa với việc dừng ứng dụng. Tuy nhiên, cần biết stdout/stderr của service đang đi tới đâu để tìm file log chứa dump. Không dùng `kill -9` hoặc `SIGKILL` để lấy thread dump; tín hiệu đó kết thúc process và không cho JVM cơ hội in dữ liệu chẩn đoán.

Nếu service do systemd hoặc Windows Service quản lý, hãy xác định log destination của service trước khi gửi tín hiệu. Với ứng dụng trong container, kiểm tra log qua container runtime hoặc orchestrator.

## 13. Thread dump với virtual thread trên Java 21+

Từ Java 21, virtual thread là một loại thread được JVM scheduler quản lý thay vì gắn cố định với một OS thread trong suốt vòng đời. Một JVM có thể có số lượng virtual thread rất lớn.

Điều này ảnh hưởng tới cách đọc thread dump:

- Platform thread tương ứng với OS thread và thường có mặt trong dump truyền thống.
- Virtual thread có thể unmount khỏi carrier khi chờ blocking I/O; lúc đó carrier thread có thể chạy virtual thread khác.
- Một dump truyền thống và dump virtual-thread-oriented có thể thể hiện các khía cạnh khác nhau.
- Không nên chỉ nhìn số platform thread để suy ra số lượng task đồng thời của ứng dụng dùng virtual thread.

Trong JDK 24, có thể tạo dump virtual thread bằng:

```bash
jcmd <PID> Thread.dump_to_file -format=plain virtual-threads.txt
jcmd <PID> Thread.dump_to_file -format=json virtual-threads.json
```

Theo tài liệu Java SE 24, dump này liệt kê virtual thread bị block trong network I/O và virtual thread được tạo qua `ExecutorService`. Nó không bao gồm object address, lock, JNI statistics, heap statistics và một số thông tin có trong traditional thread dump. Vì vậy, cần đọc mô tả đúng phiên bản JDK thay vì giả định một định dạng dump bao phủ mọi virtual thread.

Có thể kiểm tra thêm scheduler và I/O poller:

```bash
jcmd <PID> Thread.vthread_scheduler
jcmd <PID> Thread.vthread_pollers
```

Để điều tra virtual thread bị pin vào carrier hoặc vấn đề concurrency kéo dài, JDK Flight Recorder có các event như:

- `jdk.VirtualThreadStart`
- `jdk.VirtualThreadEnd`
- `jdk.VirtualThreadPinned`
- `jdk.VirtualThreadSubmitFailed`

Các event và cấu hình mặc định phụ thuộc phiên bản JDK. Dùng JFR/JDK Mission Control để phân tích chuỗi sự kiện theo thời gian; thread dump chỉ là snapshot.

Tài liệu: [Oracle Java SE 24 — Virtual Threads](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html).

## 14. Dùng jhsdb khi cần native stack hoặc core dump

Nếu thread dump Java chưa giải thích được trạng thái thread, có thể cần xem native frame hoặc phân tích core dump.

Với process đang chạy, `jhsdb jstack` có thể tạo mixed stack gồm Java frame và native C/C++ frame:

```bash
jhsdb jstack --mixed --pid <PID>
```

Với core file:

```bash
jhsdb jstack --exe <path-to-java> --core <core-file>
```

Mixed stack có thể giúp hiểu thread đang nằm trong JNI, native library hoặc một hàm nội bộ của HotSpot. Ví dụ, stack native có thể cho thấy thread đang chờ condition variable hoặc đang cố vào monitor.

`jhsdb` sử dụng Serviceability Agent và có cách attach khác với `jcmd`. Đây là công cụ chẩn đoán sâu; nên ưu tiên core dump hoặc môi trường thử nghiệm khi có thể, và đọc kỹ hướng dẫn của hệ điều hành/JDK trước khi attach vào production.

Không dùng `jhsdb` như lệnh lấy dump định kỳ thay cho `jcmd Thread.print`.

## 15. Ví dụ thực hành: tạo thread ở nhiều trạng thái

Ví dụ Java 17+ dưới đây tạo bốn thread để quan sát các trạng thái:

- `lock-owner`: giữ một monitor và chờ tín hiệu, ở trạng thái `WAITING`.
- `blocked-worker`: chờ vào monitor của `lock-owner`, ở trạng thái `BLOCKED`.
- `waiting-worker`: chờ một latch chưa được mở, ở trạng thái `WAITING`.
- `timed-worker`: ngủ trong một khoảng thời gian, ở trạng thái `TIMED_WAITING`.

Tạo file `ThreadDumpDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadDumpDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ownerHasLock = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                ownerHasLock.countDown();
                await(releaseOwner);
            }
        }, "lock-owner");

        Thread blocked = new Thread(() -> {
            try {
                ownerHasLock.await();
                synchronized (LOCK) {
                    // Runs after lock-owner releases LOCK.
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "blocked-worker");

        Thread waiting = new Thread(
            () -> await(neverReleased), "waiting-worker");

        Thread timed = new Thread(
            () -> sleep(120_000), "timed-worker");

        owner.start();
        ownerHasLock.await();
        blocked.start();
        waiting.start();
        timed.start();

        long deadline =
            System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

        while (blocked.getState() != Thread.State.BLOCKED
                && System.nanoTime() < deadline) {
            Thread.sleep(10);
        }

        if (blocked.getState() != Thread.State.BLOCKED) {
            throw new IllegalStateException(
                "blocked-worker did not reach BLOCKED");
        }

        System.out.println("READY");

        try {
            Thread.sleep(120_000);
        } finally {
            releaseOwner.countDown();
            neverReleased.countDown();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ThreadDumpDemo.java
java ThreadDumpDemo
```

Stdout:

```text
READY
```

Chương trình giữ các thread ở những trạng thái cần quan sát trong tối đa khoảng hai phút. Mở terminal thứ hai, tìm PID:

```bash
jps -l
```

Sau đó lấy dump:

```bash
jstack -l <PID>
```

Hoặc dùng lệnh được khuyến nghị:

```bash
jcmd <PID> Thread.print -l
```

Tìm các thread `lock-owner`, `blocked-worker`, `waiting-worker` và `timed-worker`. Stack và trạng thái cụ thể là dữ liệu runtime, vì vậy vị trí frame và các giá trị ID sẽ khác nhau giữa các lần chạy.

Khi kết thúc thời gian demo, chương trình mở các latch để giải phóng thread đang chờ và kết thúc bình thường.

## 16. Lỗi thường gặp khi chạy jstack

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `jstack` không được nhận diện | PATH không chứa JDK/bin hoặc chỉ cài runtime rút gọn | Kiểm tra `JAVA_HOME`, PATH và `jstack -h` |
| `Unable to open socket file` hoặc attach thất bại | Sai PID, JVM đã dừng, khác user/group hoặc attach bị vô hiệu hóa | Xác minh process, tài khoản và tùy chọn JVM |
| `Not enough permissions` | Tài khoản hiện tại không có quyền truy cập JVM | Chạy bằng service account được phép theo chính sách |
| Không tìm thấy PID trong `jps` | JVM nằm trong container/namespace khác hoặc `jps` không liệt kê được | Tìm PID bằng công cụ OS trong đúng môi trường |
| Dump không có thông tin lock cần thiết | Chỉ chạy dump mặc định | Dùng `jstack -l` hoặc `jcmd Thread.print -l` |
| Output quá lớn | Ứng dụng có rất nhiều thread hoặc stack sâu | Lưu ra file, lọc theo thread name và xem xét dump virtual thread riêng |
| Windows báo thiếu `dbgeng.dll` | Thiếu thành phần Debugging Tools for Windows cần cho attach của công cụ | Kiểm tra yêu cầu nền tảng và cài thành phần phù hợp |
| JVM không phản hồi khi attach | JVM hoặc OS đang ở trạng thái rất bất thường | Thu thập log, cân nhắc core dump và `jhsdb` theo quy trình chẩn đoán |

Các diagnostic command và tùy chọn có thể khác giữa vendor hoặc JDK release. Khi lệnh thất bại, đọc nguyên văn lỗi, kiểm tra `jstack -h` và `jcmd <PID> help` trước khi thay đổi cấu hình.

## 17. Quy trình chẩn đoán thực tế

Khi ứng dụng bị treo hoặc phản hồi chậm:

1. Ghi lại thời điểm, request/job bị ảnh hưởng, CPU, memory, latency và số lượng request.
2. Xác định đúng host/container và PID JVM.
3. Kiểm tra vendor/version của runtime.
4. Lấy ba thread dump cách nhau một khoảng ngắn bằng `jcmd <PID> Thread.print -l`.
5. So sánh các thread `RUNNABLE`, `BLOCKED`, `WAITING` và `TIMED_WAITING`.
6. Nếu có deadlock report, lần theo chuỗi thread giữ lock và chờ lock.
7. Nếu nhiều thread chờ cùng một dependency, kiểm tra database, network, connection pool, queue và timeout.
8. Nếu `RUNNABLE` lặp lại ở cùng stack, đối chiếu CPU usage và xem xét native stack/JFR.
9. Với virtual thread, dùng thêm `Thread.dump_to_file`, scheduler diagnostics và JFR theo khả năng của JDK.
10. Sau khi sửa, lấy dump mới và chạy load/concurrency test để xác nhận trạng thái đã thay đổi.

Một thread dump tốt phải được gắn với PID, thời điểm, phiên bản JDK, môi trường, triệu chứng và metric liên quan. Thiếu bối cảnh có thể khiến cùng một trạng thái thread bị diễn giải sai.

## 18. Tổng kết

Thread dump là công cụ chẩn đoán quan trọng để hiểu JVM đang làm gì tại một thời điểm. Nó cho biết thread nào đang chạy, thread nào đang chờ, stack nào lặp lại và lock nào có thể gây tắc nghẽn.

Những điểm cần nhớ:

- `jstack <PID>` lấy stack trace của thread trong JVM.
- `jstack -l` bổ sung thông tin ownable synchronizer và lock.
- `jstack -e` hiển thị extended thread information trên JDK hỗ trợ tùy chọn này.
- Oracle khuyến nghị `jcmd <PID> Thread.print` cho chẩn đoán mới.
- `BLOCKED` thường liên quan monitor; `WAITING` và `TIMED_WAITING` có thể là trạng thái bình thường.
- Dùng nhiều dump để phân biệt trạng thái nhất thời với vấn đề kéo dài.
- Deadlock cần được phân tích qua vòng phụ thuộc giữa thread và lock.
- Với virtual thread, kiểm tra đúng khả năng của JDK release và bổ sung JFR khi cần.
- Với native stack hoặc core dump, dùng `jhsdb jstack` trong quy trình chẩn đoán phù hợp.
- Bảo vệ thread dump như dữ liệu vận hành nội bộ và không lưu ở nơi công khai.

**Tài liệu tham khảo chính thức:**

- [Oracle Java SE 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle Java SE 24 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)
- [Oracle Java SE 24 — Virtual Threads](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html)
- [Oracle Java SE 21 — The jstack Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstack.html)
