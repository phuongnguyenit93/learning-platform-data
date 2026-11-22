# Thread command trong jcmd

`jcmd` là công cụ chẩn đoán đi kèm JDK, cho phép gửi diagnostic command trực tiếp đến một JVM đang chạy. Trong nhóm lệnh liên quan đến thread, `Thread.print` là lệnh thường dùng nhất: nó in thread dump gồm các thread và stack trace tại thời điểm chụp. Thread dump giúp điều tra ứng dụng bị treo, request chậm, thread pool cạn, lock contention và deadlock.

Trên JDK 21 trở lên còn có `Thread.dump_to_file`, có thể tạo thread dump dạng text hoặc JSON và liệt kê cả platform thread lẫn virtual thread. Hai lệnh phục vụ mục tiêu khác nhau: `Thread.print` hữu ích khi cần stack trace truyền thống và thông tin lock; `Thread.dump_to_file` hữu ích khi cần xem số lượng lớn thread, đặc biệt virtual thread.

Thread dump là ảnh chụp chẩn đoán tại một thời điểm, không phải bản ghi đầy đủ lịch sử hoạt động. Khi điều tra sự cố, hãy kết hợp nhiều lần chụp, log ứng dụng, metric và Java Flight Recorder (JFR) để tìm nguyên nhân.

## 1. Thread dump là gì?

Thread dump là bản mô tả trạng thái của các thread trong JVM tại thời điểm yêu cầu. Với mỗi thread, bản dump thường có:

- Tên thread và một số thông tin nhận dạng.
- Trạng thái thread, ví dụ `RUNNABLE`, `BLOCKED` hoặc `WAITING`.
- Stack trace cho biết thread đang thực thi hoặc chờ tại những method nào.
- Thông tin monitor/lock mà thread đang giữ hoặc đang chờ, nếu loại dump và tùy chọn hỗ trợ.
- Thông tin bổ sung của JVM như daemon status, priority, thread ID và native thread ID tùy định dạng.

Thread dump giúp trả lời các câu hỏi:

- Thread nào đang xử lý request?
- Thread nào đang chờ monitor hoặc lock?
- Nhiều thread có bị chặn bởi cùng một lock không?
- Có vòng chờ deadlock giữa các thread không?
- Worker thread của executor đang bận, chờ việc hay bị mắc kẹt?
- Thread đang dành thời gian ở code ứng dụng, I/O hay thư viện bên ngoài?

Một thread dump không cho biết đầy đủ CPU usage theo thời gian, số lần một method được gọi hoặc nguyên nhân gốc của mọi độ trễ. Nó cho biết trạng thái và stack tại thời điểm chụp; cần ghép với các nguồn quan sát khác.

## 2. Tìm JVM process cần kiểm tra

Mở Terminal hoặc PowerShell trên cùng máy với JVM mục tiêu. Liệt kê các JVM mà `jcmd` có thể nhìn thấy:

```sh
jcmd -l
```

Lệnh hiển thị process ID (PID), main class và command line dùng để khởi chạy JVM. Không truyền PID hoặc command name cũng có tác dụng tương đương `jcmd -l`.

Ví dụ đầu ra minh họa:

```text
24680 com.example.OrderService
27110 com.example.WorkerMain
```

PID thay đổi theo mỗi lần khởi chạy. Hãy xác định đúng ứng dụng bằng main class, command line và thông tin triển khai; không chọn PID chỉ dựa trên vị trí trong danh sách.

Nếu cần xem thông tin hệ điều hành, có thể dùng công cụ phù hợp:

```sh
ps -ef
```

Trên Windows:

```powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
```

Trong môi trường container, `jcmd -l` không liệt kê JVM chạy trong một Docker process tách biệt khỏi namespace mà công cụ đang quan sát. Hãy tìm PID trong container bằng công cụ như `ps` và chạy `jcmd` trong đúng môi trường/container.

## 3. Điều kiện để jcmd kết nối được đến JVM

Theo tài liệu JDK, `jcmd` phải chạy trên cùng máy với JVM đích và dùng effective user/group ID giống tài khoản đã khởi chạy JVM.

Một số điều kiện thực tế:

- Dùng đúng máy hoặc đúng container nơi process đang chạy.
- Chạy bằng cùng tài khoản hệ điều hành với JVM mục tiêu, hoặc quyền tương đương theo chính sách hệ thống.
- Dùng công cụ `jcmd` thuộc JDK phù hợp với JVM đang kiểm tra.
- Xác nhận process còn sống và PID chưa bị tái sử dụng.
- Kiểm tra attach mechanism không bị vô hiệu hóa hoặc chặn bởi môi trường triển khai.
- Kiểm tra quyền truy cập và cấu hình bảo mật của runtime.

Nếu JVM chạy trong container, PID trên host có thể khác PID bên trong container. Dùng PID trong cùng namespace nơi `jcmd` được thực thi.

`jcmd` là công cụ chẩn đoán cục bộ, không phải lệnh gửi qua mạng đến một JVM tùy ý. Với máy từ xa, cần truy cập máy đích theo quy trình vận hành được phê duyệt rồi chạy công cụ tại đó.

## 4. Xem trợ giúp cho Thread.print

Danh sách diagnostic command phụ thuộc JVM và phiên bản HotSpot. Trước khi dùng tùy chọn, hỏi chính JVM mục tiêu:

```sh
jcmd 24680 help
```

Xem cú pháp riêng của lệnh:

```sh
jcmd 24680 help Thread.print
```

Trong ví dụ, `24680` là PID minh họa; thay bằng PID thực tế.

Theo JDK 21, `Thread.print` có các tùy chọn chính:

| Tùy chọn | Tác dụng |
|---|---|
| Không có tùy chọn | In thread dump với stack trace |
| `-l` | In thêm thông tin lock của `java.util.concurrent` |
| `-e` | In thông tin thread mở rộng |

Các tùy chọn boolean được truyền theo cú pháp key hoặc key=value. Ví dụ `-l` hoặc `-l=true` tùy cách gọi được công cụ chấp nhận. Cú pháp chính xác của JVM đang chạy luôn được xác nhận bằng `help Thread.print`.

## 5. Chụp thread dump cơ bản bằng Thread.print

Lệnh cơ bản:

```sh
jcmd 24680 Thread.print
```

JVM đích in thread dump vào output của lệnh `jcmd`. Kết quả thường bắt đầu bằng timestamp và tiêu đề dạng:

```text
2026-11-10 10:15:30
Full thread dump OpenJDK 64-Bit Server VM (17.0.x+... mixed mode):
```

Sau đó là các nhóm thread và stack trace. Tên JVM, phiên bản, timestamp, thread ID và số lượng thread thay đổi theo process; không coi ví dụ trên là output cố định.

Để lưu kết quả vào file từ shell:

```sh
jcmd 24680 Thread.print > thread-dump.txt
```

Trên PowerShell:

```powershell
jcmd 24680 Thread.print | Out-File -Encoding utf8 thread-dump.txt
```

Lưu file giúp so sánh nhiều lần chụp, tìm kiếm thread theo tên và chia sẻ kết quả cho nhóm điều tra. Đặt tên file có PID và timestamp nếu cần lưu nhiều bản để tránh ghi đè.

## 6. In thêm lock bằng Thread.print -l

Khi nghi ngờ thread bị kẹt do lock, dùng:

```sh
jcmd 24680 Thread.print -l
```

Tùy chọn `-l` yêu cầu in thêm thông tin về lock thuộc `java.util.concurrent`. Kết quả truyền thống cũng thể hiện các monitor mà thread đang chờ hoặc đang giữ khi JVM có thông tin tương ứng.

Các dấu hiệu thường gặp:

- `- waiting to lock`: thread đang chờ lấy một monitor.
- `- locked`: thread đang giữ monitor.
- `- waiting on`: thread đang chờ trên một object hoặc điều kiện tương ứng.
- `Locked ownable synchronizers`: danh sách synchronizer mà thread đang giữ, khi dump có hỗ trợ.

Tên dòng và cách trình bày cụ thể phụ thuộc JVM. Khi điều tra, hãy so sánh object/lock identity giữa thread đang chờ và thread đang giữ lock đó.

Nếu có vòng chờ giữa nhiều thread, HotSpot có thể in phần mô tả deadlock, chẳng hạn `Found one Java-level deadlock`. Hãy đọc toàn bộ chuỗi lock owner và waiter để xác định chu trình, không chỉ nhìn một dòng cảnh báo.

## 7. In thông tin mở rộng bằng Thread.print -e

Tùy chọn `-e` yêu cầu JVM in extended thread information:

```sh
jcmd 24680 Thread.print -e
```

Ví dụ kết hợp hai tùy chọn:

```sh
jcmd 24680 Thread.print -e -l
```

Thông tin mở rộng có thể hữu ích khi cần đối chiếu thread Java với thread hệ điều hành hoặc phân tích chi tiết hơn. Các trường cụ thể phụ thuộc phiên bản JDK và loại JVM.

Không nên bật mọi tùy chọn trong mọi lần chụp nếu chưa có mục tiêu rõ ràng. Bắt đầu bằng dump cơ bản, sau đó thêm lock hoặc extended information khi câu hỏi điều tra yêu cầu.

## 8. Thread state trong thread dump

Trạng thái Java thread được biểu diễn bởi `java.lang.Thread.State`. Những trạng thái thường thấy:

| State | Ý nghĩa | Ví dụ |
|---|---|---|
| `NEW` | Thread đã được tạo nhưng chưa start | Đã gọi constructor, chưa gọi `start()` |
| `RUNNABLE` | Thread đang chạy hoặc sẵn sàng chạy trong JVM | Đang thực thi code Java hoặc một số native operation |
| `BLOCKED` | Đang chờ lấy intrinsic monitor để vào synchronized block/method | Một thread khác đang giữ monitor |
| `WAITING` | Chờ vô thời hạn một thread/action khác | `Object.wait()`, `Thread.join()` không timeout, `LockSupport.park()` |
| `TIMED_WAITING` | Chờ trong thời gian giới hạn | `Thread.sleep()`, timed wait/join/park |
| `TERMINATED` | Thread đã kết thúc | Runnable hoàn tất hoặc kết thúc do exception |

Một số lưu ý quan trọng:

- `RUNNABLE` không đồng nghĩa thread luôn tiêu thụ CPU. Thread có thể đang ở native I/O hoặc đang chờ tài nguyên bên ngoài.
- `BLOCKED` trong mô hình Java thường liên quan đến việc chờ intrinsic monitor của `synchronized`.
- `WAITING` và `TIMED_WAITING` không nhất thiết là lỗi; worker thread nhàn rỗi trong executor thường đang park để chờ công việc.
- `Object.wait()` nhả monitor mà object tương ứng đang giữ; thread sau đó chờ được notify/interrupt hoặc điều kiện khác.
- Một thread `BLOCKED` lâu bất thường cần được đối chiếu với thread đang giữ monitor.

Không kết luận ứng dụng bị treo chỉ vì thấy nhiều thread `WAITING`. Cần đọc stack trace, lock owner, thời gian chờ và vai trò của thread trong kiến trúc ứng dụng.

## 9. Đọc cấu trúc một thread entry

Một entry truyền thống có thể trông như sau (đã rút gọn và minh họa):

```text
"demo-worker" #28 prio=5 os_prio=0 cpu=12.50ms elapsed=30.10s tid=0x... nid=0x... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderService.process(OrderService.java:42)
        - waiting to lock <0x00000000...> (a java.lang.Object)
```

Cách đọc:

- `"demo-worker"`: tên thread.
- `#28`: thread ID trong phần hiển thị của dump.
- `prio`: Java thread priority.
- `cpu` và `elapsed`: thống kê CPU/thời gian nếu JVM cung cấp.
- `tid`: địa chỉ/định danh cấu trúc thread nội bộ của VM.
- `nid`: native thread ID.
- `BLOCKED`: thread đang chờ monitor.
- Dòng `at ...`: stack frame; dòng trên cùng là vị trí hiện tại gần nhất.
- `waiting to lock`: monitor mà thread muốn lấy.

Một thread đang giữ monitor có thể có entry như:

```text
"demo-lock-owner" #27 ... TIMED_WAITING (sleeping)
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.LockDemo.lambda$main$0(LockDemo.java:18)
        - locked <0x00000000...> (a java.lang.Object)
```

Nếu identity của monitor ở dòng `waiting to lock` trùng với monitor ở dòng `locked`, thread thứ hai đang chờ thread thứ nhất nhả lock.

Đừng dựa vào một dòng stack trace để kết luận nguyên nhân. Hãy lần theo các frame trong code ứng dụng và đối chiếu mọi thread liên quan.

## 10. Ví dụ Java 17+ tạo lock contention để thực hành

Chương trình dưới đây tạo một thread giữ monitor trong một khoảng thời gian và một thread khác chờ monitor đó. Nó in PID để có thể gọi `jcmd` từ terminal thứ hai.

Tạo file `ThreadCommandDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadCommandDemo {
    private static final Object LOCK = new Object();
    private static final CountDownLatch OWNER_READY =
            new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                OWNER_READY.countDown();
                try {
                    Thread.sleep(TimeUnit.MINUTES.toMillis(1));
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-lock-owner");

        Thread waiter = new Thread(() -> {
            try {
                OWNER_READY.await();
                synchronized (LOCK) {
                    System.out.println("Lock acquired");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-lock-waiter");

        owner.start();
        OWNER_READY.await();
        waiter.start();

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(5);
        while (waiter.getState() != Thread.State.BLOCKED
                && System.nanoTime() < deadline) {
            Thread.sleep(10);
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        new CountDownLatch(1).await();
    }
}
```

Biên dịch và chạy:

```sh
javac ThreadCommandDemo.java
java ThreadCommandDemo
```

Output ban đầu:

```text
PID=24680
```

PID trong thực tế sẽ khác. Chương trình giữ main thread chờ vô thời hạn để JVM tiếp tục chạy. Sau khoảng một phút, owner nhả monitor và waiter có thể in:

```text
Lock acquired
```

Mở terminal thứ hai và thay PID bằng giá trị thực tế:

```sh
jcmd 24680 Thread.print -l
```

Tìm hai thread có tên `demo-lock-owner` và `demo-lock-waiter`. Thread owner đang `TIMED_WAITING` trong `Thread.sleep` nhưng vẫn giữ monitor; thread waiter ở trạng thái `BLOCKED` vì đang cố vào synchronized block.

Dừng chương trình bằng Ctrl+C sau khi hoàn tất thực hành. Không dùng đoạn demo này trên production; đây là chương trình chủ động tạo contention để giúp đọc dump.

## 11. Cách nhận diện deadlock

Deadlock xảy ra khi hai hoặc nhiều thread giữ tài nguyên mà thread khác cần, tạo thành một chu trình chờ không thể tự tiến triển.

Ví dụ logic:

- Thread A giữ lock X và chờ lock Y.
- Thread B giữ lock Y và chờ lock X.
- A không thể lấy Y cho đến khi B nhả Y.
- B không thể nhả Y vì đang chờ X do A giữ.

Khi nghi ngờ deadlock:

1. Chụp dump bằng `Thread.print -l`.
2. Tìm phần thông báo deadlock nếu JVM phát hiện.
3. Ghi lại thread nào đang giữ lock nào.
4. Xác định thread nào đang chờ lock đó.
5. Lần theo chuỗi cho đến khi thấy vòng quay trở về thread ban đầu.
6. Tìm vị trí code lấy nhiều lock và kiểm tra thứ tự acquire.
7. Chụp thêm dump để xác nhận chu trình vẫn tồn tại.

Các hướng sửa thường gặp:

- Quy định một thứ tự lấy lock thống nhất trong toàn bộ code.
- Thu hẹp vùng synchronized để giảm thời gian giữ lock.
- Tránh gọi code bên ngoài hoặc thực hiện I/O khi đang giữ lock.
- Dùng timeout hoặc cơ chế phối hợp phù hợp khi dùng explicit lock.
- Tách trạng thái chia sẻ hoặc dùng concurrency utility có hợp đồng rõ ràng.

Một thread chờ lock trong thời gian ngắn không phải deadlock. Deadlock cần có chu trình phụ thuộc; hãy phân biệt với lock contention tạm thời hoặc một thread chậm chưa nhả lock.

## 12. Phân biệt BLOCKED, WAITING và TIMED_WAITING khi điều tra

Các trạng thái này thường bị hiểu nhầm:

**BLOCKED** thường chỉ việc chờ intrinsic monitor. Hãy tìm thread đang giữ monitor và stack trace của nó. Nếu owner bị kẹt trong code ứng dụng hoặc I/O trong khi vẫn giữ lock, các waiter có thể tích tụ.

**WAITING** thường là chờ một điều kiện hoặc tín hiệu. Ví dụ worker của thread pool park để đợi task; đây có thể là trạng thái bình thường. Nếu mọi worker đều chờ một future mà không có thread nào hoàn tất future, cần xem dependency giữa các task.

**TIMED_WAITING** thường có thời hạn. Sleep có thể là retry/backoff có chủ ý; timed wait có thể là timeout đang đếm. Kiểm tra stack trace và khoảng thời gian giữa các dump để biết trạng thái có tiến triển hay không.

`RUNNABLE` cũng cần được đọc cẩn thận. Một thread có stack ở socket read hoặc native method có thể đang chờ I/O dù state vẫn là RUNNABLE. Hãy xem frame đầu tiên thuộc code ứng dụng và frame thư viện bên dưới.

## 13. Chụp nhiều dump để phân biệt lỗi tạm thời và lỗi kéo dài

Một dump đơn lẻ chỉ cho thấy một thời điểm. Khi ứng dụng chậm hoặc treo, hãy chụp một vài dump cách nhau một khoảng ngắn, ví dụ 5–10 giây tùy tình huống:

```sh
jcmd 24680 Thread.print -l > dump-1.txt
```

Đợi một khoảng thời gian rồi:

```sh
jcmd 24680 Thread.print -l > dump-2.txt
```

Và tiếp tục:

```sh
jcmd 24680 Thread.print -l > dump-3.txt
```

So sánh:

- Thread có giữ nguyên stack trace qua các lần chụp không?
- Cùng một monitor có tiếp tục bị nhiều thread chờ không?
- Thread owner có thay đổi trạng thái không?
- Thread pool có worker nào hoàn thành task không?
- Stack trace có tiến triển hay mọi thread đều đứng ở cùng một điểm?

Nếu thread chuyển stack hoặc lock owner thay đổi, hệ thống có thể đang tiến triển nhưng chậm. Nếu cùng một chu trình lock hoặc cùng một vị trí chờ lặp lại qua nhiều dump, cần điều tra sâu hơn.

Không chụp liên tục với tần suất quá dày. `Thread.print` có impact mức Medium, phụ thuộc số lượng thread; việc thu thập quá thường xuyên có thể làm tăng tải và tạo thêm log lớn.

## 14. Lưu thread dump thành file bằng Thread.dump_to_file

JDK 21+ có lệnh `Thread.dump_to_file` để tạo thread dump trực tiếp thành file, ở dạng text hoặc JSON:

```sh
jcmd 24680 Thread.dump_to_file -format=text thread-dump.txt
```

Dạng JSON:

```sh
jcmd 24680 Thread.dump_to_file -format=json thread-dump.json
```

Lệnh này liệt kê platform thread và virtual thread. Định dạng dump này phù hợp khi cần kiểm tra số lượng lớn virtual thread hoặc đưa dữ liệu vào công cụ phân tích tự động.

Cần hiểu trade-off: tài liệu JDK 21 ghi rõ định dạng này không chứa object address, lock, JNI statistics, heap statistics và một số thông tin có trong thread dump truyền thống. Khi cần phân tích monitor/lock contention, dùng `Thread.print -l`; khi cần inventory virtual thread, dùng `Thread.dump_to_file`.

File được ghi trên máy của JVM đích. Chọn đường dẫn mà tài khoản chạy JVM có quyền ghi và bảo đảm dung lượng lưu trữ đủ. Với file đã tồn tại, chỉ bật tùy chọn overwrite nếu thật sự muốn thay thế nội dung cũ và cú pháp đó được `help Thread.dump_to_file` xác nhận trên JDK đang dùng.

## 15. Phân tích virtual thread

Virtual thread là thread được quản lý bởi Java runtime thay vì ánh xạ cố định một-một với OS thread. Một ứng dụng có thể tạo số lượng virtual thread rất lớn, vì vậy dump truyền thống có thể không phải cách thuận tiện nhất để kiểm tra toàn bộ chúng.

Với JDK 21+:

```sh
jcmd 24680 Thread.dump_to_file -format=text virtual-threads.txt
```

Hoặc:

```sh
jcmd 24680 Thread.dump_to_file -format=json virtual-threads.json
```

Định dạng này giúp kiểm tra thread name, trạng thái và stack trace của platform/virtual thread theo cách dễ phân tích hơn. JSON hữu ích khi muốn lọc theo thread name, trạng thái hoặc stack frame bằng script/tool.

Để điều tra virtual thread:

- Tìm các thread cùng chờ một endpoint hoặc tài nguyên.
- Kiểm tra stack trace tại điểm chờ I/O, lock hoặc future.
- Phân biệt số lượng virtual thread lớn với số lượng carrier/platform thread.
- Xem xét pinning và sự kiện virtual thread qua JFR nếu cần.
- Kiểm tra code đồng bộ và native call có thể làm giảm khả năng scheduler giải phóng carrier thread.

Thread dump file dạng text/JSON không có đầy đủ lock/object details của dump truyền thống. Dùng đúng định dạng theo câu hỏi điều tra, không coi hai loại dump thay thế hoàn toàn cho nhau.

## 16. So sánh Thread.print với công cụ liên quan

| Công cụ | Mục đích | Khi nên dùng |
|---|---|---|
| `jcmd PID Thread.print` | Thread dump truyền thống, stack trace | Điều tra thread state, stack và deadlock |
| `jcmd PID Thread.print -l` | Thêm thông tin lock của java.util.concurrent | Điều tra lock contention và deadlock |
| `jcmd PID Thread.dump_to_file` | Thread dump text/JSON gồm platform và virtual thread | Kiểm tra virtual thread hoặc phân tích bằng tool |
| `jstack PID` | In stack trace của thread JVM | Phương án chụp dump truyền thống khác |
| `kill -QUIT PID` trên Linux | Yêu cầu JVM in thread dump ra standard output/log | Khi không thể attach bằng jcmd và biết rõ log destination |
| `ThreadMXBean` | Chụp thông tin thread từ trong ứng dụng | Giám sát hoặc chẩn đoán tích hợp trong code |
| `JFR` | Ghi lại sự kiện JVM theo thời gian | Điều tra sự cố chập chờn, thread scheduling và contention kéo dài |

`jcmd` là lựa chọn được Oracle khuyến nghị cho nhiều tác vụ chẩn đoán JVM. Dù dùng công cụ nào, hãy xác định đúng process và bảo vệ file kết quả.

## 17. Dùng ThreadMXBean khi cần chẩn đoán từ trong ứng dụng

Nếu muốn tích hợp quan sát thread vào một endpoint nội bộ hoặc công cụ giám sát, Java Management API cung cấp `ThreadMXBean`.

Ví dụ đọc thread info và kiểm tra deadlock:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public class ThreadMonitor {
    public static void main(String[] args) {
        ThreadMXBean bean =
                ManagementFactory.getThreadMXBean();

        ThreadInfo[] threads =
                bean.dumpAllThreads(true, true);

        for (ThreadInfo info : threads) {
            System.out.println(
                    info.getThreadName() + " : " + info.getThreadState());
        }

        long[] deadlocked = bean.findDeadlockedThreads();
        System.out.println(
                "Deadlocked threads: "
                + (deadlocked == null ? 0 : deadlocked.length));
    }
}
```

Biên dịch và chạy:

```sh
javac ThreadMonitor.java
java ThreadMonitor
```

Output phụ thuộc thread của process; không có số lượng cố định. `dumpAllThreads(true, true)` yêu cầu thông tin monitor và synchronizer đang giữ nếu JVM hỗ trợ. `findDeadlockedThreads()` tìm chu trình deadlock liên quan monitor hoặc ownable synchronizer mà implementation có thể phát hiện.

Đây là ví dụ minh họa API quản trị, không phải cách thay thế mọi khả năng của `jcmd`. Khi expose dữ liệu này qua ứng dụng, hãy giới hạn quyền truy cập vì thread name và stack trace có thể tiết lộ cấu trúc nội bộ.

## 18. Khi nào nên dùng Java Flight Recorder?

Thread dump cho ảnh chụp tại một thời điểm. Nếu lỗi xảy ra không đều hoặc chỉ kéo dài vài mili giây, một vài dump có thể không bắt được nguyên nhân.

Java Flight Recorder ghi các event theo thời gian, có thể giúp điều tra:

- Thread start/end.
- Thread park và unpark.
- Monitor enter/contention.
- CPU sampling và execution samples.
- Virtual thread lifecycle/pinning events trên JDK hỗ trợ.
- Các event GC, allocation và I/O liên quan.

Có thể kiểm tra recording đang chạy:

```sh
jcmd 24680 JFR.check
```

Bắt đầu recording có thời hạn:

```sh
jcmd 24680 JFR.start name=ThreadInvestigation settings=profile duration=2m filename=thread-investigation.jfr
```

Sau khi hoàn tất, mở file bằng Java Mission Control hoặc dùng `jfr print` để xem event phù hợp. Cấu hình `profile` thu thập nhiều dữ liệu hơn `default` và có overhead cao hơn; chỉ dùng trong khoảng thời gian phù hợp với mục tiêu điều tra.

JFR phù hợp để hiểu diễn biến theo thời gian; thread dump phù hợp để xem stack và lock tại một thời điểm. Hai nguồn dữ liệu bổ sung cho nhau.

## 19. Lỗi thường gặp khi chạy Thread command

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Could not find process` | PID sai, process đã dừng hoặc công cụ không nhìn thấy process | Chạy `jcmd -l` và xác định lại PID |
| `AttachNotSupportedException` | Attach mechanism bị vô hiệu hóa, process/container không cho attach hoặc runtime không hỗ trợ | Kiểm tra JVM flags, container namespace và quyền hệ điều hành |
| Không thấy JVM trong `jcmd -l` | JVM chạy trong container riêng hoặc user khác | Chạy trong container/namespace đích và dùng đúng tài khoản |
| `Operation not permitted` hoặc access denied | User/group không phù hợp hoặc policy hệ thống chặn | Dùng đúng tài khoản vận hành và kiểm tra quyền |
| `Unknown diagnostic command` | JVM mục tiêu không hỗ trợ lệnh hoặc tên command sai | Dùng `jcmd PID help` và `help Thread.print` |
| Không nhận tùy chọn `-l`/`-e` | Khác phiên bản JVM hoặc cú pháp option sai | Kiểm tra trợ giúp command trên JVM đích |
| Dump quá lớn | Process có rất nhiều thread hoặc stack sâu | Lưu ra file, dùng filter và phân tích theo thread name/state |
| Không thấy virtual thread mong đợi | Dùng loại dump không phù hợp hoặc runtime khác phiên bản | Dùng `Thread.dump_to_file` trên JDK 21+ |
| Không có phần deadlock | Không có deadlock tại thời điểm chụp hoặc dạng dump không cung cấp thông tin cần thiết | Chụp `Thread.print -l` và đối chiếu nhiều lần |
| Ứng dụng chậm hơn khi chụp | Dump có impact phụ thuộc số lượng thread | Giảm tần suất, giới hạn số lần và chọn thời điểm phù hợp |
| File dump không được tạo | Đường dẫn không tồn tại hoặc JVM user không có quyền ghi | Dùng đường dẫn tuyệt đối có quyền ghi và kiểm tra dung lượng |
| Không thể phân biệt thread pool nhàn rỗi với thread bị kẹt | Chỉ nhìn state mà không đọc stack/context | Đối chiếu task, queue, lock owner và nhiều snapshot |

Không kết luận rằng JVM hỏng chỉ vì một lệnh attach thất bại. Xác định rõ PID, tài khoản, container namespace, runtime version và command availability trước khi đổi phương pháp thu thập.

## 20. Quy trình điều tra sự cố bằng Thread command

Khi ứng dụng bị treo hoặc request chậm:

1. Xác định thời điểm và triệu chứng: toàn bộ ứng dụng không phản hồi hay chỉ một endpoint.
2. Tìm đúng PID bằng `jcmd -l` hoặc công cụ hệ điều hành.
3. Kiểm tra command có sẵn bằng `jcmd PID help Thread.print`.
4. Chụp dump đầu tiên bằng `Thread.print -l`.
5. Lưu file cùng timestamp và thông tin JDK.
6. Tìm thread ở `BLOCKED`, stack trace lặp lại, lock owner và deadlock report.
7. Chụp thêm một hoặc hai dump cách nhau vài giây để xác nhận trạng thái kéo dài.
8. Nếu ứng dụng dùng nhiều virtual thread, chụp thêm `Thread.dump_to_file` dạng text/JSON.
9. Nếu sự cố chập chờn, cân nhắc JFR để thu thập sự kiện theo thời gian.
10. Đối chiếu với log, request ID, thread pool metrics và CPU/memory metrics.
11. Xác định code hoặc tài nguyên gây chờ.
12. Sửa nguyên nhân, thêm test tái hiện và xác nhận bằng dữ liệu sau thay đổi.

Trong báo cáo sự cố, ghi rõ JDK version, PID, thời điểm chụp, lệnh đã dùng và nơi lưu dump. Không gửi thread dump lên nơi công khai vì stack trace có thể chứa tên class nội bộ, package, endpoint và thông tin triển khai.

## 21. Lưu trữ và chia sẻ thread dump an toàn

Thread dump không thường chứa giá trị biến cục bộ như debugger, nhưng vẫn có thể tiết lộ:

- Tên class, package và method nội bộ.
- Đường dẫn code hoặc thư viện.
- Tên thread có chứa tenant, request hoặc job identifier.
- Hostname, endpoint hoặc tên dịch vụ trong stack trace.
- Cấu trúc executor, framework và kiến trúc triển khai.

Vì vậy:

- Lưu dump trong thư mục chẩn đoán có quyền truy cập hạn chế.
- Dùng tên file có PID và timestamp, tránh ghi đè.
- Không đính kèm dump đầy đủ vào issue công khai.
- Che dữ liệu nhạy cảm nếu phải chia sẻ ra ngoài tổ chức.
- Xóa bản sao tạm theo chính sách lưu trữ sau khi kết thúc điều tra.
- Ghi lại lệnh và phiên bản JDK để người khác có thể tái lập.

## 22. Checklist

- [ ] Đã xác định đúng JVM PID và môi trường/container.
- [ ] Đã dùng đúng tài khoản hệ điều hành để attach.
- [ ] Đã xem `jcmd PID help Thread.print` để xác nhận cú pháp.
- [ ] Đã chụp dump cơ bản bằng `Thread.print`.
- [ ] Đã dùng `-l` khi cần phân tích lock.
- [ ] Đã dùng `-e` khi cần extended thread information.
- [ ] Đã hiểu các trạng thái RUNNABLE, BLOCKED, WAITING và TIMED_WAITING.
- [ ] Đã lần theo lock owner và waiter thay vì chỉ nhìn một thread.
- [ ] Đã chụp nhiều snapshot nếu cần xác nhận trạng thái kéo dài.
- [ ] Đã dùng `Thread.dump_to_file` trên JDK 21+ khi cần kiểm tra virtual thread.
- [ ] Đã cân nhắc JFR cho vấn đề xảy ra không liên tục.
- [ ] Đã lưu dump với timestamp và bảo vệ quyền truy cập.
- [ ] Đã đối chiếu kết quả với log, metrics và code ứng dụng.

## 23. Tài liệu tham khảo

- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java 21 Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle Java 21 Core Libraries — Virtual Threads, Viewing Virtual Threads in jcmd Thread Dumps: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- Java SE 21 API — `java.lang.management.ThreadMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html

`Thread.print` là lệnh cốt lõi để chụp stack trace và điều tra trạng thái thread trong một JVM đang chạy. Dùng `-l` khi cần xem lock, `-e` khi cần thông tin mở rộng, và `Thread.dump_to_file` trên JDK 21+ khi cần inventory platform/virtual thread. Kết hợp nhiều snapshot, JFR và log ứng dụng để tìm nguyên nhân thay vì kết luận từ một trạng thái đơn lẻ.