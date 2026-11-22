# Luồng Java, luồng hệ điều hành và trạng thái đồng bộ

Một chương trình Java có thể thực hiện nhiều công việc cùng lúc nhờ các luồng (thread). Tuy nhiên, từ góc nhìn của ứng dụng, một đối tượng Thread không hoàn toàn đồng nghĩa với một luồng mà hệ điều hành đang lập lịch. JVM cung cấp mô hình và trạng thái luồng ở mức Java; hệ điều hành quản lý việc cấp CPU cho các luồng native; cơ chế đồng bộ phối hợp quyền truy cập dữ liệu dùng chung giữa chúng.

Hiểu rõ ba lớp này giúp giải thích được vì sao một thread có thể ở trạng thái RUNNABLE nhưng chưa chạy trên CPU, vì sao BLOCKED khác WAITING, và vì sao một ứng dụng cần đưa các luồng về trạng thái ổn định trước khi tạo checkpoint bằng CRaC.

## 1. Tiến trình và luồng

**Tiến trình (process)** là một chương trình đang chạy với không gian địa chỉ và tập tài nguyên của riêng nó. Một tiến trình có thể chứa nhiều luồng.

**Luồng (thread)** là một đơn vị thực thi bên trong tiến trình. Các luồng trong cùng tiến trình thường chia sẻ heap, đối tượng, vùng nhớ tĩnh và nhiều tài nguyên của tiến trình. Mỗi luồng có ngăn xếp (stack), bộ đếm lệnh và trạng thái thực thi riêng.

Ví dụ, một máy chủ Java có thể có:

- Một luồng nhận kết nối và tiếp nhận yêu cầu.
- Nhiều luồng xử lý yêu cầu.
- Một luồng ghi log.
- Một luồng thực hiện tác vụ định kỳ.
- Các luồng nội bộ do JVM hoặc thư viện tạo ra.

Các luồng có thể tiến triển đồng thời. Trên máy có nhiều lõi CPU, một số luồng có thể thực sự chạy song song tại cùng một thời điểm. Trên máy chỉ có một lõi, hệ điều hành thường luân phiên cấp thời gian CPU cho các luồng để tạo cảm giác đồng thời.

## 2. Java thread và OS thread

Java biểu diễn luồng bằng lớp java.lang.Thread. Khi gọi start(), JVM đưa luồng vào quá trình thực thi. Phương thức run() chứa công việc của luồng; thông thường ứng dụng không gọi trực tiếp run() để tạo luồng mới, vì gọi trực tiếp chỉ là một lời gọi phương thức trên luồng hiện tại.

~~~java
public class ThreadExample {
    public static void main(String[] args) {
        Thread worker = new Thread(() -> {
            System.out.println(
                "Đang chạy trên: " + Thread.currentThread().getName()
            );
        }, "worker-1");

        worker.start();
    }
}
~~~

Hai lời gọi sau có ý nghĩa khác nhau:

- worker.start() yêu cầu JVM khởi chạy một luồng mới, sau đó luồng mới thực thi run().
- worker.run() thực thi thân phương thức ngay trên luồng đang gọi, không tạo luồng mới.

### Platform thread

Với **platform thread**, JVM thường gắn một Java thread với một luồng native do hệ điều hành quản lý. Trên các JVM phổ biến như HotSpot, mô hình này thường là ánh xạ một-một: một platform thread tương ứng với một OS thread.

Khi đó, hệ điều hành chịu trách nhiệm lập lịch OS thread lên các lõi CPU. JVM vẫn quản lý các khái niệm Java như tên luồng, stack trace, trạng thái Thread.State và các quy tắc đồng bộ của ngôn ngữ.

Mô hình một-một là cách triển khai phổ biến, không nên xem nó là quy tắc bắt buộc của đặc tả Java cho mọi JVM.

### Virtual thread

Từ Java 21, Java hỗ trợ **virtual thread** như một loại thread do JVM quản lý. Thay vì cần một OS thread riêng cho mỗi virtual thread, JVM có thể ghép nhiều virtual thread lên một số lượng nhỏ hơn các platform thread, còn gọi là carrier thread.

Virtual thread hữu ích cho ứng dụng có nhiều tác vụ đồng thời chủ yếu chờ I/O. Chúng giúp ứng dụng tạo nhiều đơn vị công việc nhẹ hơn mà không cần tạo số lượng OS thread tương ứng.

Cần phân biệt:

| Đặc điểm | Platform thread | Virtual thread |
|---|---|---|
| Đơn vị được hệ điều hành lập lịch trực tiếp | OS thread tương ứng | Carrier platform thread |
| Quản lý vòng đời | JVM và hệ điều hành | Chủ yếu do JVM quản lý |
| Chi phí khi tạo số lượng lớn | Thường cao hơn | Thường thấp hơn |
| Phù hợp | Tác vụ CPU, tác vụ cần kiểm soát thread native | Nhiều tác vụ đồng thời, thường xuyên chờ I/O |

Virtual thread không làm cho một tác vụ CPU-bound chạy nhanh hơn số lõi CPU có sẵn. Chúng cải thiện khả năng tổ chức nhiều tác vụ chờ đợi; năng lực xử lý CPU vẫn bị giới hạn bởi phần cứng.

## 3. Hệ điều hành lập lịch luồng như thế nào?

Hệ điều hành không lập lịch theo khái niệm Thread.State của Java. Nó lập lịch các thực thể thực thi native của nền tảng.

Ở mức khái quát, một OS thread có thể:

- **Runnable/ready:** đã sẵn sàng chạy và đang chờ được cấp CPU.
- **Running:** đang được thực thi trên một lõi CPU.
- **Blocked/sleeping:** đang chờ một sự kiện, tài nguyên hoặc thao tác I/O.
- **Stopped/terminated:** đã bị dừng hoặc đã kết thúc, tùy cách hệ điều hành biểu diễn.

Tên gọi và tập trạng thái cụ thể phụ thuộc hệ điều hành. Linux, Windows và các hệ điều hành khác không nhất thiết dùng cùng một hệ phân loại.

Bộ lập lịch có thể tạm dừng một thread đang chạy để cấp CPU cho thread khác. Việc chuyển CPU từ thread này sang thread khác gọi là **context switch**. Khi chuyển đổi, hệ thống phải lưu và khôi phục ngữ cảnh thực thi. Context switch là chi phí cần tính đến khi ứng dụng tạo quá nhiều thread hoặc thường xuyên tranh chấp tài nguyên.

Ví dụ, một máy có 4 lõi CPU có thể chạy tối đa khoảng 4 luồng CPU-bound đồng thời tại một thời điểm, nếu mỗi lõi chỉ thực thi một luồng. Ứng dụng vẫn có thể có hàng trăm thread; phần lớn trong số đó có thể đang chờ I/O, chờ khóa hoặc chờ được cấp CPU.

### Không đồng nhất trạng thái Java với trạng thái OS

Thread.State là trạng thái quan sát ở mức Java. Nó không phải bản sao trực tiếp của trạng thái scheduler trong hệ điều hành.

Một Java thread ở RUNNABLE có thể đang thực thi hoặc đang sẵn sàng thực thi nhưng chưa được OS cấp CPU. Vì vậy, RUNNABLE không có nghĩa là thread chắc chắn đang sử dụng CPU tại thời điểm quan sát.

Tương tự, BLOCKED trong Java có nghĩa cụ thể là thread đang chờ lấy intrinsic lock để vào một vùng synchronized. Nó không đồng nghĩa với mọi dạng blocked hoặc sleeping mà hệ điều hành ghi nhận.

Khi phân tích hiệu năng, cần kết hợp thread dump, mức sử dụng CPU, số lượng thread, thời gian chờ và công cụ quan sát của hệ điều hành. Chỉ nhìn một giá trị Thread.State thường chưa đủ để kết luận nguyên nhân.

## 4. Sáu trạng thái của Java thread

Enum java.lang.Thread.State định nghĩa sáu trạng thái. Đây là các trạng thái phục vụ quan sát và chẩn đoán; chúng không mô tả toàn bộ mọi chi tiết bên trong JVM hoặc hệ điều hành.

| Trạng thái | Ý nghĩa | Ví dụ thường gặp |
|---|---|---|
| NEW | Đã tạo đối tượng Thread nhưng chưa gọi start() | new Thread(task) |
| RUNNABLE | Đang chạy hoặc sẵn sàng chạy trong JVM | Đang thực thi run() hoặc chờ được cấp CPU |
| BLOCKED | Đang chờ lấy monitor lock để vào khối/phương thức synchronized | Thread khác đang giữ cùng monitor |
| WAITING | Đang chờ vô thời hạn một thread khác thực hiện hành động đánh thức | Object.wait(), Thread.join() không timeout, LockSupport.park() |
| TIMED_WAITING | Đang chờ trong một khoảng thời gian giới hạn | Thread.sleep(), wait(timeout), join(timeout), parkNanos() |
| TERMINATED | Đã kết thúc thực thi | Phương thức run() kết thúc hoặc thoát do exception không được xử lý |

Một luồng thường đi qua các chuyển trạng thái sau:

~~~text
NEW
  |
  | start()
  v
RUNNABLE <-----------------------------+
  |                                    |
  | chờ monitor                        | lấy được monitor
  v                                    |
BLOCKED --------------------------------
  |
  | wait/join/park hoặc thao tác có timeout
  v
WAITING hoặc TIMED_WAITING
  |
  | được đánh thức, hết timeout,
  | bị interrupt hoặc điều kiện chờ thay đổi
  v
RUNNABLE
  |
  | run() kết thúc
  v
TERMINATED
~~~

Sơ đồ thể hiện các chuyển trạng thái thường gặp, không phải máy trạng thái đầy đủ cho mọi tình huống. Chẳng hạn, thread đang ở WAITING do Object.wait() phải lấy lại monitor trước khi tiếp tục thực thi sau khi được đánh thức.

### Quan sát trạng thái

Có thể lấy trạng thái hiện tại bằng getState():

~~~java
Thread worker = new Thread(() -> {
    // Công việc của thread
}, "worker");

System.out.println(worker.getState()); // NEW
worker.start();
System.out.println(worker.getState()); // Có thể là RUNNABLE hoặc trạng thái khác
~~~

Kết quả sau start() phụ thuộc lịch thực thi. Thread có thể đã chạy, đang chờ khóa hoặc đã kết thúc trước khi thread gọi getState() đọc trạng thái.

getState() chỉ cung cấp một ảnh chụp tại thời điểm gọi. Không dùng nó làm cơ chế đồng bộ, ví dụ không nên liên tục kiểm tra getState() để quyết định lúc nào thread khác được phép sửa dữ liệu. Hãy dùng lock, condition, latch, semaphore, future hoặc một cơ chế phối hợp rõ ràng.

## 5. Đồng bộ hóa giữa các luồng

Khi nhiều thread đọc và ghi cùng một dữ liệu, chương trình cần kiểm soát ba vấn đề:

1. **Tính nguyên tử (atomicity):** một thao tác có bị xen giữa bởi thread khác hay không.
2. **Tính hiển thị (visibility):** thay đổi của thread này có được thread khác nhìn thấy hay không.
3. **Thứ tự thực thi (ordering):** JVM và CPU có được phép sắp xếp lại các thao tác hay không.

Nếu bỏ qua các vấn đề này, chương trình có thể gặp race condition, dữ liệu không nhất quán hoặc lỗi chỉ xuất hiện khi tải cao.

### Race condition

Xét bộ đếm được hai thread cùng tăng:

~~~java
class Counter {
    int value = 0;

    void increment() {
        value++;
    }
}
~~~

Biểu thức value++ không phải một thao tác nguyên tử. Về khái niệm, nó gồm đọc giá trị, cộng một và ghi lại. Hai thread có thể cùng đọc giá trị 10, cùng tính ra 11 rồi cùng ghi 11. Kết quả cuối là 11 dù đã có hai lần tăng; một lần cập nhật bị mất.

Có thể bảo vệ thao tác bằng synchronized:

~~~java
class Counter {
    private int value = 0;

    synchronized void increment() {
        value++;
    }

    synchronized int getValue() {
        return value;
    }
}
~~~

Chỉ một thread tại một thời điểm có thể thực thi một phương thức hoặc khối synchronized trên cùng monitor. Việc thoát khỏi vùng synchronized cũng tạo quan hệ hiển thị bộ nhớ với lần lấy cùng monitor tiếp theo.

### Monitor và synchronized

Mỗi đối tượng Java có thể được dùng làm monitor. Khi một thread đi vào khối synchronized (lock), nó phải lấy monitor của đối tượng lock. Nếu thread khác đang giữ monitor đó, thread đến sau chuyển sang trạng thái BLOCKED.

~~~java
private final Object lock = new Object();

void update() {
    synchronized (lock) {
        // Vùng tới hạn: truy cập dữ liệu dùng chung
    }
}
~~~

Các điểm cần nhớ:

- Monitor có tính **reentrant**: thread đang giữ monitor có thể vào lại một vùng synchronized khác bảo vệ bởi chính monitor đó.
- Khối synchronized trên cùng một đối tượng loại trừ lẫn nhau giữa các thread.
- synchronized trên phương thức instance sử dụng monitor của this.
- static synchronized sử dụng monitor của đối tượng Class tương ứng.
- Các thread dùng những monitor khác nhau không tự động loại trừ lẫn nhau.

Không nên giữ monitor trong thời gian dài, đặc biệt khi thực hiện I/O, gọi dịch vụ bên ngoài hoặc chờ một thao tác có thời gian không xác định. Điều đó làm tăng thời gian thread khác phải chờ và có thể tạo deadlock.

### wait, notify và notifyAll

wait(), notify() và notifyAll() là các phương thức của Object, hoạt động trên monitor của đối tượng.

- wait() yêu cầu thread đang giữ monitor nhường monitor đó và chuyển sang tập thread đang chờ trên đối tượng.
- notify() đánh thức một thread đang chờ trên monitor đó.
- notifyAll() đánh thức tất cả thread đang chờ trên monitor đó.
- Thread được đánh thức phải cạnh tranh để lấy lại monitor. Nó chỉ tiếp tục sau khi lấy lại được monitor.

Ví dụ:

~~~java
final class StartGate {
    private boolean open = false;

    public synchronized void awaitOpen() throws InterruptedException {
        while (!open) {
            wait();
        }
    }

    public synchronized void open() {
        open = true;
        notifyAll();
    }
}
~~~

Điều kiện được kiểm tra trong vòng while, không phải if, vì:

- Thread có thể được đánh thức dù điều kiện ứng dụng vẫn chưa đúng (spurious wakeup).
- notifyAll() có thể đánh thức nhiều thread nhưng chỉ một số thread phù hợp với điều kiện.
- Một thread khác có thể thay đổi điều kiện trước khi thread vừa thức lấy lại được monitor.

wait() phải được gọi khi thread đang giữ monitor của chính đối tượng nhận lời gọi; nếu không, JVM ném IllegalMonitorStateException.

**wait() khác sleep():**

| Đặc điểm | Object.wait() | Thread.sleep() |
|---|---|---|
| Thuộc về | Object | Thread |
| Yêu cầu giữ monitor trước khi gọi | Có | Không |
| Nhường monitor của đối tượng đang đồng bộ | Có | Không |
| Cách kết thúc chờ | notify/notifyAll, interrupt hoặc timeout | Hết thời gian hoặc interrupt |
| Dùng để | Phối hợp theo điều kiện | Tạm dừng thread trong một khoảng thời gian |

Nếu một thread gọi sleep() khi đang giữ monitor, nó vẫn giữ monitor trong suốt thời gian ngủ. Vì vậy, dùng sleep() để chờ thread khác thay đổi dữ liệu có thể khiến chính thread kia không lấy được lock để thực hiện thay đổi.

### volatile

volatile phù hợp khi một biến cần được đọc/ghi trực tiếp giữa nhiều thread và thao tác không cần một chuỗi cập nhật phức hợp phải nguyên tử.

~~~java
class ServiceState {
    private volatile boolean running = true;

    void stop() {
        running = false;
    }

    void runLoop() {
        while (running) {
            doOneUnitOfWork();
        }
    }

    private void doOneUnitOfWork() {
        // Xử lý một phần công việc
    }
}
~~~

Khi một thread ghi biến volatile, thread khác đọc cùng biến volatile có thể quan sát giá trị mới theo quy tắc bộ nhớ của Java. volatile cũng thiết lập các ràng buộc thứ tự cần thiết cho những thao tác liên quan.

Tuy nhiên, volatile không biến value++ thành thao tác nguyên tử. Nếu cần tăng/giảm an toàn giữa nhiều thread, có thể dùng AtomicInteger, lock hoặc synchronized, tùy yêu cầu.

### Lock và các công cụ phối hợp khác

Ngoài intrinsic lock của synchronized, Java cung cấp các công cụ trong java.util.concurrent:

- ReentrantLock: lock tường minh, hỗ trợ tryLock(), khả năng cấu hình fairness và Condition.
- CountDownLatch: cho một hoặc nhiều thread chờ đến khi một số công việc hoàn tất.
- Semaphore: giới hạn số thread được phép truy cập một tài nguyên cùng lúc.
- CyclicBarrier và Phaser: phối hợp các thread theo từng chặng.
- CompletableFuture: mô tả chuỗi công việc bất đồng bộ và cách kết hợp kết quả.
- Các lớp atomic như AtomicInteger và AtomicReference: cung cấp thao tác nguyên tử cho dữ liệu phù hợp.

Ví dụ dùng CountDownLatch để chờ một nhóm công việc hoàn thành:

~~~java
int taskCount = 3;
CountDownLatch done = new CountDownLatch(taskCount);

for (int i = 0; i < taskCount; i++) {
    new Thread(() -> {
        try {
            performTask();
        } finally {
            done.countDown();
        }
    }).start();
}

done.await();
System.out.println("Tất cả công việc đã hoàn tất");
~~~

Trong ứng dụng thực tế, thường nên giao công việc cho ExecutorService thay vì tự tạo thread mới cho từng yêu cầu. Thread pool giúp giới hạn số thread, tái sử dụng tài nguyên và quản lý vòng đời tác vụ tập trung hơn.

## 6. Interrupt và kết thúc thread có kiểm soát

Java không khuyến khích cưỡng bức dừng một thread đang thực thi. Cách thông dụng là yêu cầu thread tự dừng bằng **interrupt** hoặc một cờ trạng thái dùng chung.

interrupt() gửi tín hiệu ngắt đến thread. Tác động phụ thuộc vào việc thread đang làm gì:

- Nếu thread đang chờ trong sleep(), wait() hoặc join(), thao tác thường kết thúc bằng InterruptedException.
- Nếu thread không ở một thao tác chờ có thể ngắt, cờ interrupt được đặt để thread kiểm tra và phản hồi.
- Interrupt không tự động giết thread.

Ví dụ:

~~~java
class Worker implements Runnable {
    @Override
    public void run() {
        while (!Thread.currentThread().isInterrupted()) {
            doOneUnitOfWork();
        }

        cleanUp();
    }

    private void doOneUnitOfWork() {
        // Công việc cần có thời gian thực thi hữu hạn
    }

    private void cleanUp() {
        // Giải phóng tài nguyên do worker sở hữu
    }
}
~~~

Khi xử lý InterruptedException, ứng dụng nên quyết định rõ việc dừng hay truyền tín hiệu ngắt lên tầng gọi. Nếu không thể ném exception tiếp, có thể khôi phục cờ interrupt bằng Thread.currentThread().interrupt() trước khi kết thúc hoặc trả quyền điều khiển.

~~~java
try {
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Không nên bắt InterruptedException rồi bỏ qua nếu tác vụ cần hỗ trợ dừng có kiểm soát. Việc nuốt tín hiệu interrupt có thể làm quá trình shutdown hoặc điều phối ứng dụng bị treo.

## 7. Các vấn đề đồng bộ thường gặp

### Deadlock

Deadlock xảy ra khi các thread chờ nhau theo một chu trình và không thread nào có thể tiếp tục.

Ví dụ:

- Thread A giữ lock X và chờ lock Y.
- Thread B giữ lock Y và chờ lock X.

Hai thread không thể lấy được lock còn lại để thoát khỏi vùng tới hạn.

Cách giảm nguy cơ:

- Quy định một thứ tự lấy lock thống nhất trong toàn ứng dụng.
- Tránh gọi mã bên ngoài khi đang giữ lock.
- Giữ vùng synchronized ngắn.
- Dùng tryLock() với timeout khi phù hợp.
- Thu thập thread dump khi ứng dụng có dấu hiệu đứng.

### Starvation và livelock

**Starvation** xảy ra khi một thread liên tục không có cơ hội lấy tài nguyên cần thiết vì các thread khác luôn được ưu tiên hoặc chiếm tài nguyên.

**Livelock** xảy ra khi các thread vẫn hoạt động và liên tục phản ứng với nhau nhưng không tạo ra tiến triển hữu ích. Ví dụ, hai thread cùng nhường đường cho nhau theo một quy tắc khiến cả hai cứ lặp lại hành động nhường.

Các hiện tượng này khác deadlock: trong deadlock, các thread thường bị chặn chờ; trong livelock, chúng vẫn chạy nhưng không hoàn thành công việc.

## 8. Quan sát và chẩn đoán thread

Khi ứng dụng chậm hoặc không phản hồi, cần xác định thread đang chạy CPU, chờ monitor, chờ I/O hay chờ một điều kiện ứng dụng.

Một số công cụ hữu ích:

- jcmd <pid> Thread.print: lấy thread dump của tiến trình Java.
- jstack <pid>: lấy stack trace của các thread, nếu công cụ phù hợp với môi trường JDK.
- ThreadMXBean: lấy thông tin thread từ chương trình và có thể hỗ trợ phát hiện deadlock.
- Công cụ của hệ điều hành: đối chiếu mức sử dụng CPU, số lượng OS thread và trạng thái native thread.

Khi đọc thread dump, chú ý:

- Nhiều thread ở BLOCKED cùng chờ một monitor có thể cho thấy điểm tranh chấp lock.
- Thread ở WAITING hoặc TIMED_WAITING chưa chắc có vấn đề; đó có thể là trạng thái chờ bình thường.
- Một thread ở RUNNABLE chưa chắc đang tiêu thụ CPU; cần đối chiếu stack trace và số liệu CPU.
- Stack trace lặp lại ở cùng một vị trí qua nhiều lần lấy mẫu có thể giúp tìm vòng lặp dài hoặc điểm nghẽn.

Không kết luận deadlock chỉ từ việc thấy nhiều thread đang chờ. Hãy tìm chu trình phụ thuộc lock hoặc dùng công cụ phát hiện deadlock.

## 9. Liên hệ với CRaC: đưa thread về điểm ổn định trước checkpoint

CRaC (Coordinated Restore at Checkpoint) cho phép lưu trạng thái của một tiến trình Java để khôi phục tiến trình đó ở lần chạy sau. Vì checkpoint liên quan đến trạng thái bộ nhớ và thực thi của tiến trình, vòng đời thread và trạng thái đồng bộ cần được tính đến trong thiết kế ứng dụng.

Một checkpoint được tạo khi ứng dụng đang xử lý dở công việc có thể mang theo những trạng thái khó phối hợp với hệ thống bên ngoài sau khi restore. Ví dụ:

- Một thread đang giữ lock trong khi cập nhật dữ liệu dùng chung.
- Một nhóm thread đang chờ nhau hoặc chờ một điều kiện chưa được đáp ứng.
- Một tác vụ đang xử lý yêu cầu nhưng giao dịch bên ngoài chưa hoàn tất.
- Một thread đang giữ kết nối hoặc tài nguyên native cần được tạo lại sau restore.
- Một thread nền đang chạy lịch định kỳ dựa trên thời gian hoặc trạng thái bên ngoài.

Mục tiêu của bước chuẩn bị checkpoint là đưa ứng dụng về một **điểm ổn định (quiescent point)**: không nhận thêm công việc mới, công việc đang chạy đã hoàn tất hoặc được dừng theo quy trình, và tài nguyên bên ngoài đã được xử lý phù hợp.

Một trình tự thường dùng:

1. Ngừng nhận yêu cầu hoặc tác vụ mới.
2. Báo cho worker dừng nhận việc và hoàn tất phần việc đang xử lý.
3. Chờ các tác vụ đang chạy kết thúc bằng cơ chế phối hợp có timeout.
4. Hoàn tất hoặc rollback giao dịch đang mở theo chính sách ứng dụng.
5. Đóng hoặc giải phóng kết nối, file handle và tài nguyên bên ngoài cần khởi tạo lại.
6. Thực hiện checkpoint.
7. Sau restore, tạo lại tài nguyên bên ngoài, khởi động lại worker và cho phép nhận công việc.

Không nên dùng vòng lặp kiểm tra Thread.getState() hoặc sleep() để đoán rằng mọi thread đã dừng. Hãy dùng tín hiệu và điều kiện do ứng dụng quản lý, chẳng hạn CountDownLatch, Phaser, trạng thái shutdown, hoặc giao thức pause/resume của worker.

### Resource callback của CRaC

API CRaC cung cấp Resource để ứng dụng đăng ký công việc cần thực hiện trước checkpoint và sau restore. Ví dụ dưới đây minh họa vòng đời của một client kết nối ra ngoài; các phương thức xử lý yêu cầu là phần ứng dụng tự triển khai.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class BackendResource implements Resource {
    private ExternalClient client;

    public BackendResource() {
        client = createClient();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        stopAcceptingNewRequests();
        awaitInFlightRequests();
        client.close();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = createClient();
        resumeAcceptingRequests();
    }

    private ExternalClient createClient() {
        // Tạo client theo cấu hình của ứng dụng
        return new ExternalClient();
    }

    private void stopAcceptingNewRequests() {
        // Đóng cổng nhận việc mới hoặc chuyển service sang trạng thái pause
    }

    private void awaitInFlightRequests() throws Exception {
        // Chờ công việc đang chạy kết thúc với timeout phù hợp
    }

    private void resumeAcceptingRequests() {
        // Cho phép service nhận việc sau khi tài nguyên đã sẵn sàng
    }
}
~~~

Ví dụ là khung minh họa; ExternalClient và các phương thức điều phối cần được thay bằng lớp thực tế của ứng dụng. Nếu có nhiều resource phụ thuộc nhau, cần thiết kế thứ tự đóng và mở lại sao cho resource phụ thuộc được khởi tạo trước khi worker sử dụng chúng.

### Quản lý thread pool qua checkpoint

Một ExecutorService đã gọi shutdown() sẽ không nhận tác vụ mới. Vì vậy, nếu muốn tiếp tục sử dụng pool sau restore, không nên mặc định gọi shutdown() rồi mong pool tự hoạt động lại. Có thể chọn một trong hai hướng:

- Dùng cơ chế pause riêng của ứng dụng: ngừng submit tác vụ, chờ tác vụ đang chạy hoàn tất, giữ cấu trúc pool theo cách được runtime hỗ trợ và tiếp tục sau restore.
- Đóng pool trước checkpoint và tạo một pool mới trong giai đoạn sau restore.

Lựa chọn phụ thuộc loại executor, JDK có CRaC, hệ điều hành và cách ứng dụng quản lý worker. Cần kiểm tra hành vi của runtime mục tiêu thay vì giả định mọi thread native hoặc tài nguyên của thư viện đều có thể tiếp tục sử dụng an toàn.

Ngoài thread pool, hãy rà soát ThreadLocal. Dữ liệu gắn với thread có thể chứa thông tin theo request, transaction hoặc security context. Cần xóa dữ liệu theo vòng đời công việc để tránh mang trạng thái cũ sang tác vụ khác hoặc sang giai đoạn sau restore.

## 10. Nguyên tắc thiết kế cần ghi nhớ

- Dùng start() để khởi chạy thread; gọi trực tiếp run() không tạo thread mới.
- Phân biệt platform thread với virtual thread và hiểu thread nào được hệ điều hành lập lịch trực tiếp.
- Không xem Thread.State là bản đồ trạng thái OS thread.
- RUNNABLE có thể là đang chạy hoặc đang chờ CPU; BLOCKED là chờ intrinsic monitor.
- Dùng synchronized, lock hoặc công cụ java.util.concurrent để bảo vệ dữ liệu dùng chung.
- wait() nhường monitor; sleep() không nhường monitor.
- Kiểm tra điều kiện chờ trong vòng while khi dùng wait().
- volatile bảo đảm quy tắc hiển thị và thứ tự phù hợp, nhưng không làm thao tác ghép như count++ trở thành nguyên tử.
- Dùng interrupt và giao thức shutdown để kết thúc thread có kiểm soát.
- Khi chẩn đoán, kết hợp thread dump với số liệu CPU và quan sát của hệ điều hành.
- Trước checkpoint CRaC, phối hợp worker về điểm ổn định, xử lý tác vụ đang chạy và quản lý tài nguyên cần tạo lại sau restore.

Khi hiểu mối quan hệ giữa Java thread, OS thread và monitor, việc đọc thread dump, xử lý tranh chấp tài nguyên và chuẩn bị ứng dụng cho checkpoint/restore sẽ có cơ sở rõ ràng hơn.
