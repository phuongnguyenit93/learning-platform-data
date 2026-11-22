# Stack trace với jstack

**`jstack`** là công cụ chẩn đoán của JDK dùng để in stack trace của các thread trong một Java Virtual Machine (JVM) đang chạy. Kết quả thường được gọi là **thread dump**. Nó cho biết thread nào đang chạy, chờ, bị block, đang giữ lock nào và đang đi qua những method nào tại thời điểm thu thập.

Thread dump là một ảnh chụp trạng thái của JVM, rất hữu ích khi điều tra ứng dụng bị treo, phản hồi chậm, thread pool bị nghẽn, lock contention hoặc deadlock. Trong các JDK hiện đại, Oracle khuyến nghị dùng `jcmd` với command `Thread.print` cho chẩn đoán thông thường; `jstack` vẫn có thể gặp trong quy trình vận hành và tài liệu cũ nhưng được đánh dấu experimental/unsupported.

## 1. Stack trace và thread dump khác nhau thế nào?

**Stack trace** mô tả chuỗi lời gọi method của một thread tại một thời điểm. Mỗi frame thường cho biết class, method và vị trí source code nếu có.

Ví dụ:

```text
at com.example.service.OrderService.load(OrderService.java:42)
at com.example.web.OrderController.get(OrderController.java:18)
at java.base/java.lang.Thread.run(Thread.java:1583)
```

Có thể đọc từ trên xuống: thread đang ở frame đầu tiên và các frame phía dưới là những lời gọi dẫn tới vị trí hiện tại.

**Thread dump** là tập hợp stack trace của nhiều thread trong cùng JVM, thường kèm:

- Tên thread và trạng thái.
- Thread ID và native thread ID.
- Các stack frame của từng thread.
- Monitor hoặc synchronizer mà thread đang giữ/chờ.
- Thông tin phát hiện deadlock nếu có.

Một stack trace đơn lẻ giúp tìm vị trí thực thi của một thread. Thread dump giúp nhìn toàn bộ quan hệ giữa các thread và lock trong tiến trình.

## 2. Khi nào nên lấy thread dump?

Thread dump có ích khi cần trả lời các câu hỏi:

- Thread nào đang tiêu thụ CPU hoặc lặp trong một đoạn code?
- Vì sao request không hoàn tất?
- Thread có đang chờ database, network, queue hoặc lock không?
- Có thread nào bị block khi cố lấy intrinsic monitor không?
- Có deadlock giữa hai hoặc nhiều thread không?
- Thread pool có hết worker hay có quá nhiều thread đang chờ không?
- Ứng dụng có đang dừng ở cùng một vị trí qua nhiều lần lấy mẫu không?

Một thread dump chỉ cho thấy trạng thái tại một thời điểm. Để phân biệt một lần chờ bình thường với một thread bị kẹt lâu, thường cần lấy nhiều dump cách nhau vài giây và so sánh stack/state/lock.

## 3. Tìm PID của JVM

Trước khi gọi `jstack`, xác định đúng process Java.

Liệt kê JVM có thể quan sát:

```bash
jps -l
```

Output minh họa:

```text
18420 com.example.app.Main
29116 org.apache.catalina.startup.Bootstrap
```

Trong ví dụ, `18420` là PID/LVMID của ứng dụng cần kiểm tra. PID thay đổi theo mỗi lần chạy; không sao chép PID minh họa vào môi trường thật.

Nếu chạy trong container, PID nhìn từ host có thể khác PID trong PID namespace của container. Có thể cần chạy `jps` hoặc `jstack` bên trong container, dưới đúng tài khoản sở hữu JVM.

## 4. Cú pháp và tùy chọn jstack

Cú pháp trên JDK hiện đại:

```text
jstack [-l] [-e] <pid>
```

Trong đó:

- `pid` là process ID của JVM đích.
- `-l` yêu cầu in thêm thông tin lock, bao gồm ownable synchronizers và các lock thuộc `java.util.concurrent`.
- `-e` yêu cầu in extended thread information trên các bản JDK hỗ trợ tùy chọn này.
- `-h` hoặc `-help` hiển thị trợ giúp.

Xem tùy chọn của JDK đang cài:

```bash
jstack -h
```

Trên JDK 24 được kiểm tra cho bài học này, trợ giúp hiển thị:

```text
Usage:
    jstack [-l][-e] <pid>

Options:
    -l  long listing. Prints additional information about locks
    -e  extended listing. Prints additional information about threads
    -? -h --help -help to print this help message
```

Không giả định mọi phiên bản hoặc JVM vendor có cùng tùy chọn. Luôn kiểm tra trợ giúp của đúng JDK và JVM đích.

## 5. Lấy thread dump cơ bản

Dùng PID của JVM:

```bash
jstack 18420
```

Lệnh in stack trace của các Java thread và thread nội bộ VM mà công cụ thu thập được. JVM tiếp tục chạy sau khi dump được in; lệnh không có nghĩa là dừng ứng dụng.

Có thể lưu output vào file để phân tích:

```bash
jstack 18420 > thread-dump-1.txt
```

Trong PowerShell:

```powershell
jstack 18420 | Out-File -Encoding utf8 thread-dump-1.txt
```

Nếu cần thông tin lock chi tiết hơn:

```bash
jstack -l 18420 > thread-dump-locks.txt
```

Nếu cần extended thread information:

```bash
jstack -e 18420 > thread-dump-extended.txt
```

Các file dump có thể chứa tên class nội bộ, package, đường dẫn source và thông tin vận hành. Hãy bảo vệ file trước khi chia sẻ.

## 6. Đọc cấu trúc thread dump

Một thread entry thường có header, trạng thái và stack trace.

Ví dụ minh họa:

```text
"worker-1" #35 prio=5 os_prio=0 tid=0x000001f5b47a5950 nid=14944 waiting on condition
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.worker.Poller.run(Poller.java:28)
```

Các trường thường gặp:

| Trường | Ý nghĩa |
| --- | --- |
| `"worker-1"` | Tên thread |
| `#35` | Java thread ID |
| `prio=5` | Java thread priority |
| `os_prio=0` | Priority ở mức hệ điều hành nếu có |
| `tid=...` | Địa chỉ/định danh cấu trúc thread trong VM |
| `nid=14944` | Native thread ID |
| `waiting on condition` | Mô tả ngắn trạng thái chờ ở mức VM |
| `Thread.State` | Trạng thái Java của thread |
| Các dòng `at ...` | Stack frames, từ vị trí hiện tại đi ngược qua lời gọi method |

Định dạng header thay đổi theo phiên bản JVM. JDK mới có thể bổ sung elapsed time, CPU time, allocated bytes hoặc extended thread fields. Không viết parser phụ thuộc cứng vào một định dạng thread dump cụ thể.

## 7. Ý nghĩa các trạng thái thread

Java định nghĩa các trạng thái trong `Thread.State`. Những trạng thái thường thấy trong dump:

| Trạng thái | Ý nghĩa | Cách đọc khi điều tra |
| --- | --- | --- |
| `RUNNABLE` | Thread có thể chạy trong JVM; có thể đang thực thi hoặc chờ tài nguyên hệ điều hành | Kiểm tra stack và CPU; không đồng nghĩa chắc chắn đang dùng CPU |
| `BLOCKED` | Thread đang chờ lấy intrinsic monitor để vào hoặc lấy lại synchronized block/method | Tìm thread đang giữ monitor đó |
| `WAITING` | Thread chờ vô thời hạn một hành động từ thread khác | Kiểm tra `Object.wait`, `Thread.join` hoặc `LockSupport.park` |
| `TIMED_WAITING` | Thread chờ có thời hạn | Kiểm tra `Thread.sleep`, `wait(timeout)`, `join(timeout)` hoặc timed park |
| `NEW` | Thread đã tạo nhưng chưa start | Thường không xuất hiện như một thread đang hoạt động trong dump |
| `TERMINATED` | Thread đã kết thúc | Không còn thực thi; thường không xuất hiện trong danh sách thread đang chạy |

Một số điểm quan trọng:

- `RUNNABLE` không chứng minh thread đang chiếm CPU. Thread có thể ở trạng thái native I/O hoặc chờ tài nguyên bên dưới.
- `BLOCKED` thường liên quan đến intrinsic monitor của `synchronized`.
- `WAITING` không tự động là lỗi. Worker chờ queue rỗng hoặc thread chờ điều kiện có thể là hành vi bình thường.
- `TIMED_WAITING` do `Thread.sleep` có thể hoàn toàn bình thường.
- Cần đọc stack trace và trạng thái lock cùng nhau, không kết luận chỉ từ một nhãn state.

## 8. Đọc stack frame và tìm vị trí code

Stack frame thường có dạng:

```text
at package.ClassName.methodName(FileName.java:123)
```

Ví dụ:

```text
at com.example.payment.PaymentService.charge(PaymentService.java:87)
at com.example.web.PaymentController.submit(PaymentController.java:34)
```

Cách phân tích:

1. Đọc frame trên cùng để biết thread đang ở đâu.
2. Theo dõi các frame phía dưới để biết chuỗi lời gọi.
3. Tìm frame đầu tiên thuộc code của ứng dụng.
4. Mở đúng file và dòng source.
5. Xem thread state và lock quanh frame đó để hiểu vì sao thread dừng tại vị trí này.

Một số frame có thể không có source line:

- `Native Method`: đang ở native method hoặc JNI.
- `Unknown Source`: JVM không có thông tin source line.
- `Generated/lambda frame`: code được compiler hoặc runtime tạo tự động.
- `Reflection` hoặc framework frame: lời gọi đi qua reflection/proxy/framework trước khi vào code ứng dụng.

Đừng bỏ qua các frame thư viện. Ví dụ thread có thể đang chờ ở `SocketInputStream.read` hoặc JDBC driver; frame ứng dụng phía dưới giúp xác định request nào đã tạo ra thao tác I/O đó.

## 9. Phân biệt BLOCKED, WAITING và RUNNABLE trong thực tế

### BLOCKED: chờ intrinsic monitor

Ví dụ:

```text
"request-12" #48
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.cache.Cache.refresh(Cache.java:71)
        - waiting to lock <0x000000011f019920> (a java.lang.Object)
```

Thread đang chờ monitor có địa chỉ tương ứng. Dùng thông tin `- locked` ở thread khác để tìm chủ sở hữu monitor.

### WAITING: chờ điều kiện

Ví dụ:

```text
"queue-worker" #52
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
        at java.util.concurrent.LinkedBlockingQueue.take(LinkedBlockingQueue.java:...)
```

Worker có thể đang chờ phần tử mới trong queue. Đây thường là trạng thái bình thường khi không có công việc.

### TIMED_WAITING: chờ có thời hạn

Ví dụ:

```text
"heartbeat" #53
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.monitor.Heartbeat.run(Heartbeat.java:25)
```

Thread đang ngủ để chờ chu kỳ tiếp theo. Nếu thread cần phản hồi ngay nhưng liên tục ngủ hoặc chờ timeout dài, hãy kiểm tra logic và cấu hình thời gian.

### RUNNABLE: thực thi hoặc hoạt động ở native

Ví dụ:

```text
"worker-cpu" #54
   java.lang.Thread.State: RUNNABLE
        at com.example.math.Matrix.multiply(Matrix.java:112)
        at com.example.service.Analytics.run(Analytics.java:58)
```

Nếu cùng stack xuất hiện trong nhiều dump và CPU của thread cao, có thể có vòng lặp tốn CPU. Nếu stack ở native I/O, trạng thái RUNNABLE không nhất thiết có nghĩa thread đang tính toán.

## 10. Đọc thông tin monitor và lock với jstack -l

Tùy chọn `-l` bổ sung thông tin lock, bao gồm ownable synchronizers mà dump cơ bản có thể không hiển thị đầy đủ.

Ví dụ:

```text
"worker-A" #35
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.LockDemo.first(LockDemo.java:40)
        - waiting to lock <0x000000011f019920> (a java.lang.Object)
        - locked <0x000000011f019910> (a java.lang.Object)
```

Cách đọc:

- `waiting to lock`: thread đang chờ lấy monitor có địa chỉ được hiển thị.
- `locked`: thread đang giữ monitor.
- Địa chỉ object giúp liên kết phần đang chờ với phần đang giữ cùng một monitor trong dump.
- Tên class sau địa chỉ cho biết loại object được dùng làm lock.

Với `java.util.concurrent.locks`, chẳng hạn `ReentrantLock`, thông tin ownable synchronizer giúp hiểu thread nào đang giữ synchronizer và thread nào đang chờ. Dùng `jstack -l` hoặc `jcmd <pid> Thread.print -l` khi cần thông tin này.

Không kết luận deadlock chỉ vì một thread có `waiting to lock`. Cần xác định chu trình phụ thuộc: A chờ lock do B giữ, trong khi B chờ lock do A giữ, hoặc một chu trình dài hơn.

## 11. Phát hiện deadlock

Deadlock xảy ra khi một nhóm thread chờ tài nguyên theo chu trình và không thread nào có thể tiếp tục.

Ví dụ:

- Thread A giữ lock X và chờ lock Y.
- Thread B giữ lock Y và chờ lock X.
- A không thể lấy Y khi B chưa nhả Y.
- B không thể lấy X khi A chưa nhả X.

Dùng:

```bash
jstack -l 18420
```

Nếu HotSpot phát hiện Java-level deadlock, phần cuối output có thể chứa:

```text
Found one Java-level deadlock:
"left-worker":
  waiting to lock monitor ... (object ..., a java.lang.Object),
  which is held by "right-worker"
"right-worker":
  waiting to lock monitor ... (object ..., a java.lang.Object),
  which is held by "left-worker"
```

Đây là dấu hiệu rõ ràng về chu trình lock. Với deadlock phức tạp hơn, phần báo cáo có thể liệt kê nhiều thread và monitor trong cùng chu trình.

Nếu không có dòng deadlock report, điều đó không chứng minh ứng dụng không bị treo. Có thể nguyên nhân là I/O, network, queue, external service, starvation hoặc một dạng chờ không được phát hiện như Java-level monitor deadlock.

## 12. Ví dụ thực hành Java 17: tạo deadlock có chủ đích

Ví dụ dưới đây tạo hai thread, mỗi thread giữ một lock rồi chờ lock còn lại. Mục đích là quan sát thread state và deadlock report. Không chạy ví dụ này trong ứng dụng production.

Tạo cấu trúc:

```text
project/
  src/
    com/example/diagnostics/
      DeadlockTarget.java
  out/
```

Tệp **`src/com/example/diagnostics/DeadlockTarget.java`**:

```java
package com.example.diagnostics;

import java.util.concurrent.CountDownLatch;

public final class DeadlockTarget {
    private static final Object FIRST = new Object();
    private static final Object SECOND = new Object();
    private static final CountDownLatch READY = new CountDownLatch(2);

    private DeadlockTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        Thread left = new Thread(
            () -> lock(FIRST, SECOND),
            "left-worker"
        );
        Thread right = new Thread(
            () -> lock(SECOND, FIRST),
            "right-worker"
        );

        left.start();
        right.start();

        System.out.println("PID=" + ProcessHandle.current().pid());
        Thread.sleep(120_000);
    }

    private static void lock(Object first, Object second) {
        synchronized (first) {
            READY.countDown();

            try {
                READY.await();
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return;
            }

            synchronized (second) {
                System.out.println("unreachable");
            }
        }
    }
}
```

Hai worker giữ lock theo thứ tự ngược nhau. CountDownLatch bảo đảm cả hai đã giữ lock đầu tiên trước khi thử lấy lock thứ hai.

Biên dịch:

```bash
javac --release 17 -d out src/com/example/diagnostics/DeadlockTarget.java
```

Chạy:

```bash
java -cp out com.example.diagnostics.DeadlockTarget
```

Output đầu tiên:

```text
PID=19092
```

PID ở đây chỉ là ví dụ từ một lần chạy; hãy dùng PID thật mà chương trình in ra.

Mở terminal thứ hai:

```bash
jstack -l 19092
```

Output quan trọng có dạng:

```text
"left-worker" #35
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.diagnostics.DeadlockTarget.lock(DeadlockTarget.java:...)
        - waiting to lock <0x...> (a java.lang.Object)
        - locked <0x...> (a java.lang.Object)

"right-worker" #36
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.diagnostics.DeadlockTarget.lock(DeadlockTarget.java:...)
        - waiting to lock <0x...> (a java.lang.Object)
        - locked <0x...> (a java.lang.Object)

Found one Java-level deadlock:
"left-worker":
  waiting to lock monitor ... which is held by "right-worker"
"right-worker":
  waiting to lock monitor ... which is held by "left-worker"
```

Địa chỉ monitor, thread ID và số dòng có thể thay đổi theo lần biên dịch/chạy. Điều cần nhận ra là hai worker đều BLOCKED, mỗi thread đang giữ một object và chờ object do thread kia giữ.

Dừng chương trình thử nghiệm bằng Ctrl+C ở terminal chạy ứng dụng. Deadlock không tự giải quyết chỉ vì đã lấy thread dump.

## 13. Lấy nhiều thread dump để tìm vấn đề kéo dài

Một thread có thể WAITING hoặc BLOCKED trong thời gian ngắn mà không có lỗi. Để biết trạng thái có kéo dài hay không, hãy lấy một số dump cách nhau vài giây.

Ví dụ trên Linux/macOS:

```bash
jstack -l 18420 > dump-1.txt
sleep 5
jstack -l 18420 > dump-2.txt
sleep 5
jstack -l 18420 > dump-3.txt
```

PowerShell:

```powershell
jstack -l 18420 | Out-File -Encoding utf8 dump-1.txt
Start-Sleep -Seconds 5
jstack -l 18420 | Out-File -Encoding utf8 dump-2.txt
Start-Sleep -Seconds 5
jstack -l 18420 | Out-File -Encoding utf8 dump-3.txt
```

So sánh:

- Thread có giữ nguyên stack trace qua các lần dump không?
- Thread có luôn BLOCKED trên cùng monitor không?
- Thread có liên tục chờ cùng một queue hoặc external call không?
- Thread RUNNABLE có lặp lại cùng một đoạn code không?
- Số lượng thread cùng trạng thái có tăng không?
- Thread giữ lock có tiến triển hay cũng bị chờ ở nơi khác?

Ba dump giống nhau có thể chỉ ra trạng thái bị kẹt lâu, nhưng vẫn cần đối chiếu metrics, log, CPU và dependency để xác định nguyên nhân gốc.

Không tạo vòng lặp lấy dump quá dày. Thread dump lớn có thể làm tăng tải và tạo nhiều file không cần thiết.

## 14. Dùng jcmd Thread.print trong JDK hiện đại

Oracle khuyến nghị dùng `jcmd` thay cho `jstack` trong chẩn đoán JVM hiện đại. `Thread.print` in stack trace của các thread và hỗ trợ tùy chọn lock/extended information.

Cú pháp cơ bản:

```bash
jcmd 18420 Thread.print
```

In thêm lock:

```bash
jcmd 18420 Thread.print -l
```

In extended thread information:

```bash
jcmd 18420 Thread.print -e
```

Kết hợp cả hai:

```bash
jcmd 18420 Thread.print -l -e
```

Trợ giúp command trên JVM đích:

```bash
jcmd 18420 help Thread.print
```

Trong JDK 24 được kiểm tra, trợ giúp cho biết:

- Command: `Thread.print`.
- Mô tả: in tất cả thread cùng stack trace.
- Impact: Medium, phụ thuộc số lượng thread.
- `-l`: in thông tin `java.util.concurrent` locks.
- `-e`: in extended thread information.

`jcmd` dùng cùng cơ chế attach cục bộ. Chọn đúng PID và tài khoản chạy JVM; kiểm tra trợ giúp của JVM đích vì command options có thể khác theo phiên bản.

## 15. jstack và jhsdb jstack

Hai trường hợp sử dụng khác nhau:

| Công cụ | Đầu vào | Mục đích |
| --- | --- | --- |
| `jstack <pid>` | JVM đang chạy | In thread dump từ tiến trình |
| `jcmd <pid> Thread.print` | JVM đang chạy | Chẩn đoán thread bằng diagnostic command được khuyến nghị |
| `jhsdb jstack --exe ... --core ...` | Executable Java và core dump | Phân tích thread stack sau khi JVM đã crash hoặc core dump được tạo |

Ví dụ phân tích core dump:

```bash
jhsdb jstack --exe /path/to/java --core /path/to/core
```

Đường dẫn executable phải tương ứng với JVM đã tạo core dump. Phân tích core dump có yêu cầu file và môi trường phù hợp; không dùng cú pháp PID của jstack để thay cho thao tác postmortem.

## 16. Quyền attach và lỗi thường gặp

`jstack` cần attach được vào JVM đích. Các điều kiện thường gặp:

- JVM phải là process Java phù hợp với công cụ.
- Công cụ cần quyền hệ điều hành để attach.
- Thường phải chạy dưới cùng user sở hữu JVM hoặc tài khoản có quyền tương ứng.
- JVM có thể tắt Attach Mechanism bằng cấu hình khởi động.
- Container, PID namespace, sandbox hoặc security policy có thể giới hạn attach.
- Trên Windows, môi trường debug/native tooling và đường dẫn runtime phù hợp có thể ảnh hưởng khả năng lấy dump.

Một số lỗi phổ biến:

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Unable to open socket file` | Attach mechanism không sẵn sàng, sai user hoặc môi trường tạm khác nhau | Kiểm tra user, JVM options và temp directory |
| `Access is denied` | Không đủ quyền truy cập process | Dùng tài khoản được phép và kiểm tra policy |
| `No such process` | PID sai hoặc JVM đã kết thúc | Chạy lại `jps -l` hoặc kiểm tra process hệ điều hành |
| `Not a Java process` | PID trỏ tới process không phải JVM tương thích | Xác nhận PID trước khi chạy |
| Không có deadlock report | Không có Java-level deadlock được phát hiện tại thời điểm lấy mẫu | Kiểm tra nhiều dump, I/O, queue, CPU và external dependency |
| Thiếu thông tin lock | Dùng dump cơ bản hoặc command không bật lock details | Dùng `jstack -l` hoặc `jcmd Thread.print -l` |
| Không thấy process trong container | Khác PID namespace hoặc user | Chạy công cụ trong container hoặc đúng namespace |
| Thread dump quá lớn | JVM có nhiều thread hoặc stack sâu | Lưu ra file, thu thập trong thời gian kiểm soát và lọc khi phân tích |

Không cố vượt qua cơ chế bảo vệ attach hoặc chạy dưới tài khoản khác nếu chưa được cấp quyền.

## 17. Các giới hạn và lưu ý vận hành

Thread dump rất hữu ích nhưng không phải công cụ giải thích mọi sự cố:

- Nó là snapshot, không phải bản ghi liên tục.
- Nó không cho biết toàn bộ lịch sử của thread trước thời điểm dump.
- Nó không hiển thị đầy đủ local variable values như debugger.
- Một stack frame RUNNABLE không tự chứng minh thread đang tiêu thụ CPU.
- Không có deadlock report không loại trừ mọi kiểu treo hoặc starvation.
- Thread dump lớn có thể ảnh hưởng thời gian phản hồi tùy số lượng thread.
- Output có thể chứa package nội bộ, đường dẫn và thông tin vận hành nhạy cảm.
- `jstack` là công cụ experimental/unsupported trong tài liệu JDK; có thể thay đổi hoặc bị loại bỏ trong tương lai.

Với ứng dụng production, ưu tiên `jcmd Thread.print`, JFR, Java Mission Control, metrics và log. Chọn phương pháp phù hợp với mức độ khẩn cấp và overhead cho phép.

## 18. Quy trình phân tích thread dump đề xuất

Khi nhận báo cáo ứng dụng bị treo hoặc chậm:

1. Xác định đúng JVM bằng `jps -l` hoặc công cụ quản lý process.
2. Ghi lại PID, JDK version, thời điểm, host/container và triệu chứng.
3. Dùng `jcmd <pid> Thread.print -l` để lấy dump đầu tiên.
4. Nếu cần, lấy thêm hai dump cách nhau vài giây.
5. Tìm các thread `BLOCKED` và monitor chúng đang chờ.
6. Tìm `Found one Java-level deadlock` trong phần cuối output.
7. Kiểm tra thread `RUNNABLE` có CPU cao và stack lặp lại không.
8. Kiểm tra các thread `WAITING` trong queue, pool, future hoặc lock.
9. Đối chiếu stack frame với source code, log, metrics và trạng thái dependency.
10. Nếu cần dữ liệu sâu hơn theo thời gian, dùng JFR hoặc công cụ giám sát phù hợp.
11. Lưu dump an toàn, lọc dữ liệu nhạy cảm trước khi chia sẻ.
12. Đề xuất sửa nguyên nhân gốc; lấy dump không tự giải phóng thread bị deadlock.

## 19. Ghi nhớ

- Stack trace là chuỗi frame của một thread; thread dump là tập stack trace và trạng thái của nhiều thread trong JVM.
- Dùng `jstack <pid>` để in thread dump; `-l` bổ sung thông tin lock và `-e` mở rộng thông tin thread trên JDK hỗ trợ.
- Header thường có tên thread, Java thread ID, native thread ID và trạng thái.
- `RUNNABLE` không luôn có nghĩa thread đang dùng CPU.
- `BLOCKED` thường chỉ ra thread đang chờ intrinsic monitor.
- `WAITING` và `TIMED_WAITING` có thể là hành vi bình thường; cần đọc stack frame để hiểu nguyên nhân.
- `jstack -l` có thể hiển thị lock và báo Java-level deadlock.
- Lấy nhiều dump cách nhau vài giây để phân biệt snapshot nhất thời với trạng thái kéo dài.
- Oracle khuyến nghị `jcmd <pid> Thread.print` cho chẩn đoán hiện đại; `jstack` là experimental/unsupported.
- Bảo vệ thread dump vì output có thể tiết lộ cấu trúc nội bộ của ứng dụng.

Hiểu cách đọc thread header, trạng thái, stack frame và lock giúp bạn biến một thread dump thành bằng chứng để điều tra deadlock, nghẽn luồng và ứng dụng phản hồi chậm.

## Tài liệu tham khảo

- [Oracle Java SE 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 24 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)
- [Oracle Java SE 11 — jstack and jcmd diagnostics](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html)
