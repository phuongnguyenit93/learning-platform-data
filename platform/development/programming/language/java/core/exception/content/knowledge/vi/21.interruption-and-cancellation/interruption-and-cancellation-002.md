# Quan hệ giữa interrupt flag và phương thức chờ có thể bị ngắt trong Java

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu interrupt là **tín hiệu yêu cầu hợp tác** với luồng đang chạy, không phải lệnh cưỡng bức kết thúc luồng.
- Phân biệt <code>thread.interrupt()</code>, <code>thread.isInterrupted()</code> và <code>Thread.interrupted()</code>, đặc biệt tác dụng **xóa cờ ngắt** của phương thức cuối.
- Giải thích điều gì xảy ra khi một luồng đang chờ ở <code>Thread.sleep()</code>, <code>Object.wait()</code>, <code>Thread.join()</code>, <code>BlockingQueue.take()</code>, <code>Condition.await()</code> hoặc <code>Lock.lockInterruptibly()</code> nhận interrupt.
- Biết rằng các phương thức chờ ném <code>InterruptedException</code> thường đã **xóa interrupt flag khi ném lỗi**; lựa chọn truyền ngoại lệ lên hoặc khôi phục cờ phải phù hợp hợp đồng phương thức.
- Viết code chờ/hủy an toàn, không để luồng quay vòng vô hạn, không nhả khóa chưa sở hữu và không vô tình nuốt yêu cầu hủy.
- Tự kiểm tra hành vi interrupt qua các chương trình Java 17+ có kết quả xác định.

## 2. Interrupt flag là gì?

Mỗi <code>Thread</code> trong Java có trạng thái ngắt (thường được gọi là **interrupt flag** hoặc *interrupted status*). Khi một luồng gọi <code>target.interrupt()</code>, nó gửi tín hiệu ngắt tới <code>target</code>.

Thông thường, nếu <code>target</code> đang chạy code tính toán không kiểm tra cờ, code **không tự động dừng**. Nếu luồng đang chờ trong một phương thức có hợp đồng phản ứng với interrupt, lời gọi chờ có thể kết thúc bằng <code>InterruptedException</code>, hoặc một hình thức phản ứng khác theo API đó.

Ví dụ trực giác:

~~~text
Luồng điều phối                     Luồng worker
       |                                  |
       |                          đang làm việc/chờ
       |                                  |
       +---- worker.interrupt() --------->|
                                          |
                            API kiểm tra trạng thái ngắt
                                          |
                         +----------------+----------------+
                         |                                 |
                  chờ interruptible                 tác vụ tính toán
                         |                                 |
             InterruptedException                  cần chủ động kiểm tra
                và thường xóa cờ                     isInterrupted()
                         |                                 |
             bắt/truyền/khôi phục                    quyết định dừng
                theo hợp đồng                        theo hợp đồng
~~~

Không nên coi cờ ngắt như một biến <code>boolean</code> do ứng dụng tùy tiện đặt/xóa. Java cung cấp API để gửi và quan sát trạng thái đó. Cũng không nên diễn giải rằng interrupt là ngoại lệ được “ném từ luồng A sang luồng B” một cách trực tiếp: <code>interrupt()</code> là **tín hiệu**, còn ngoại lệ có được ném hay không là quyết định của API đang chạy trong luồng nhận tín hiệu.

### Một luồng đang RUNNABLE có thể phớt lờ interrupt

~~~java
while (true) {
    doCpuWork();
}
~~~

Đây là **mã minh họa**; <code>doCpuWork()</code> chỉ đại diện cho tính toán. Nếu vòng lặp không kiểm tra trạng thái ngắt và công việc không gọi API có phản ứng với interrupt, lời gọi <code>thread.interrupt()</code> từ luồng khác không buộc vòng lặp phải dừng.

Mẫu hợp tác:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    doCpuWork();
}
~~~

Đây cũng là **mã minh họa** trong phương thức có sẵn <code>doCpuWork()</code>. Kiểm tra cờ giúp vòng lặp chọn dừng ở điểm phù hợp. Nếu công việc thực tế có thao tác ghi dữ liệu, trước khi kết thúc vẫn phải giải phóng tài nguyên và bảo vệ bất biến trạng thái.

## 3. Ba API quan trọng: gửi tín hiệu, kiểm tra và tiêu thụ cờ

| Biểu thức | Tác dụng | Có xóa interrupt flag không? |
| --- | --- | --- |
| <code>target.interrupt()</code> | Yêu cầu ngắt luồng <code>target</code>; hệ quả phụ thuộc trạng thái/API chờ | Không phải API dùng để xóa cờ |
| <code>target.isInterrupted()</code> | Đọc trạng thái ngắt của đối tượng luồng được chỉ định | **Không** |
| <code>Thread.interrupted()</code> | Đọc trạng thái ngắt của **luồng đang gọi** | **Có**: trả về trạng thái cũ rồi xóa |
| <code>Thread.currentThread().interrupt()</code> | Gửi tín hiệu ngắt tới **chính luồng hiện tại**; thường dùng để khôi phục cờ sau khi catch | Thiết lập tín hiệu ngắt, không xóa |

**Điểm dễ nhầm:** <code>Thread.interrupted()</code> là phương thức **static**. Nó luôn kiểm tra cờ của **luồng hiện tại**, bất kể bạn định dùng nó như một lời gọi trên đối tượng luồng nào. Để quan sát trạng thái của một đối tượng <code>Thread</code> cụ thể mà không xóa cờ, dùng <code>target.isInterrupted()</code>.

Một phép đọc không phá hủy trạng thái:

~~~java
boolean requested = Thread.currentThread().isInterrupted();
~~~

Một phép đọc đồng thời **tiêu thụ** trạng thái:

~~~java
boolean wasInterrupted = Thread.interrupted();
~~~

Nếu <code>Thread.interrupted()</code> trả về <code>true</code>, một lần đọc ngay sau đó thường trả về <code>false</code> nếu chưa nhận interrupt mới. Điều này ảnh hưởng trực tiếp tới những API chờ sau đó: chúng có thể không còn nhìn thấy yêu cầu ngắt vừa bị xóa.

### Ví dụ Java 17+: quan sát cách cờ được thay đổi

Lưu tệp **InterruptFlagDemo.java**:

~~~java
public class InterruptFlagDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();

        current.interrupt();
        System.out.println("Sau interrupt(): " + current.isInterrupted());

        try {
            Thread.sleep(1_000);
            System.out.println("Sleep hoàn tất");
        } catch (InterruptedException e) {
            System.out.println("Sleep ném InterruptedException");
            System.out.println("Cờ trong catch: " + current.isInterrupted());
        }

        current.interrupt();
        System.out.println("Trước interrupted(): " + current.isInterrupted());
        System.out.println("Thread.interrupted(): " + Thread.interrupted());
        System.out.println("Sau interrupted(): " + current.isInterrupted());
    }
}
~~~

Biên dịch và chạy bằng Java 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 InterruptFlagDemo.java
java InterruptFlagDemo
~~~

Kết quả stdout trong lần chạy thông thường:

~~~text
Sau interrupt(): true
Sleep ném InterruptedException
Cờ trong catch: false
Trước interrupted(): true
Thread.interrupted(): true
Sau interrupted(): false
~~~

**Giải thích từng bước:**

1. <code>current.interrupt()</code> đặt cờ ngắt cho chính luồng <code>main</code>, vì <code>current</code> tham chiếu đến <code>Thread.currentThread()</code>.
2. <code>Thread.sleep(1_000)</code> thấy luồng hiện tại đã bị ngắt và ném <code>InterruptedException</code> thay vì ngủ đủ thời gian yêu cầu.
3. Theo hợp đồng của <code>Thread.sleep()</code>, **interrupted status được xóa khi ngoại lệ đó được ném**. Vì vậy trong <code>catch</code>, <code>current.isInterrupted()</code> trả về <code>false</code> nếu không có interrupt mới.
4. Chương trình chủ động đặt cờ lại một lần nữa để minh họa <code>Thread.interrupted()</code>.
5. <code>Thread.interrupted()</code> trả về <code>true</code> và đồng thời xóa cờ, nên phép <code>isInterrupted()</code> cuối trả về <code>false</code>.

Ví dụ cố tình không khôi phục cờ trong khối <code>catch</code> đầu tiên để hiển thị rõ hợp đồng của <code>sleep()</code>. Trong code nghiệp vụ, quyết định khôi phục hay truyền <code>InterruptedException</code> phải theo các quy tắc ở phần sau.

## 4. InterruptException và trạng thái ngắt là hai kênh báo hiệu khác nhau

<code>InterruptedException</code> là **checked exception**. Một số phương thức chờ sử dụng nó để thông báo rằng yêu cầu ngắt đã cắt ngang thao tác chờ.

Một diễn biến điển hình:

~~~text
Cờ = false
   |
   | Luồng khác gọi interrupt()
   v
Cờ = true
   |
   | Luồng đang gọi phương thức chờ interruptible
   v
Phương thức phát hiện interrupt
   |
   | ném InterruptedException
   v
Cờ = false (với hợp đồng các phương thức chờ chuẩn đang xét)
   |
   +--> catch: truyền ngoại lệ lên
   |
   +--> catch: khôi phục cờ và rời thao tác
   |
   +--> catch: xử lý theo hợp đồng đặc biệt
~~~

Điểm quan trọng là **một ngoại lệ đã có thể mang thông tin “tác vụ bị ngắt” dù interrupt flag tại thời điểm bắt là <code>false</code>**. Nếu code chỉ nhìn cờ sau khi catch mà bỏ qua đối tượng <code>InterruptedException</code>, nó có thể kết luận sai rằng không có yêu cầu hủy.

Theo tài liệu Java, <code>InterruptedException</code> thường đi kèm việc trạng thái ngắt bị xóa khi ném, nhưng hãy xét hợp đồng của API cụ thể. Không áp dụng quy tắc này cho **mọi API có chữ “interrupt”**: ví dụ <code>LockSupport.park()</code> phản ứng bằng cách trở về và không tự xóa cờ theo cách <code>Thread.sleep()</code> làm.

Nếu có một interrupt mới tới **sau khi** phương thức đã ném ngoại lệ nhưng trước lúc code kiểm tra cờ, trạng thái quan sát được cũng có thể thay đổi. Các ví dụ độc lập dưới đây kiểm soát số lượng tín hiệu để kết quả dễ hiểu; code đa luồng thực tế cần xét khả năng có nhiều yêu cầu ngắt.

## 5. Các phương thức chờ thường gặp và phản ứng với interrupt

| API | Khi nhận interrupt trong lúc chờ | Điều cần nhớ |
| --- | --- | --- |
| <code>Thread.sleep(...)</code> | Ném <code>InterruptedException</code>, xóa cờ theo hợp đồng | Không tự nhả lock/monitor mà luồng đang giữ |
| <code>Object.wait(...)</code> | Ném <code>InterruptedException</code>, xóa cờ theo hợp đồng | Chỉ gọi khi sở hữu monitor; tạm nhả monitor rồi lấy lại trước khi thoát |
| <code>Thread.join(...)</code> | Luồng **đang join** có thể nhận <code>InterruptedException</code> và cờ của nó bị xóa | Không có nghĩa luồng được join đã bị ngắt hoặc kết thúc |
| <code>BlockingQueue.take()</code> | Có thể ném <code>InterruptedException</code> khi đang chờ phần tử | Không biến thành một kết quả phần tử hợp lệ; cần kết thúc/xử lý đúng |
| <code>BlockingQueue.put(...)</code> | Có thể ném <code>InterruptedException</code> khi chờ chỗ trống | Với queue có dung lượng hữu hạn, kiểm tra tính nhất quán của luồng sản xuất |
| <code>Condition.await()</code> | Có thể ném <code>InterruptedException</code> | Nhả rồi lấy lại lock gắn với Condition trước khi phương thức kết thúc theo hợp đồng |
| <code>Lock.lockInterruptibly()</code> | Có thể ném <code>InterruptedException</code> trước khi lấy được khóa | Nếu không lấy được khóa thì **không gọi <code>unlock()</code>** |
| <code>Lock.tryLock(timeout, unit)</code> | Có thể ném <code>InterruptedException</code> trong khi đợi | Chỉ <code>unlock()</code> sau khi nhận được kết quả lấy khóa thành công |
| <code>CountDownLatch.await()</code>, <code>Semaphore.acquire()</code> | Là các lời gọi chờ có thể bị ngắt | Cần duy trì quy ước về kết quả/permit và hủy tác vụ |

Bảng mô tả hành vi thông thường của các API Java chuẩn. Một phương thức chờ có thể hoàn tất vì điều kiện bình thường, timeout, có phần tử mới, hoặc interrupt; loại kết quả cụ thể do hợp đồng của từng phương thức quy định. Không suy từ tên phương thức rằng mọi lời gọi chờ đều phản ứng giống nhau.

### Các phương thức chờ không cùng một kiểu

- <code>ReentrantLock.lock()</code> dùng cách lấy khóa **không thể hủy bằng <code>InterruptedException</code> trong lúc đợi**; nếu nhận interrupt trong khi đợi, nó tiếp tục chờ và duy trì/khôi phục thông tin interrupt theo hợp đồng.
- <code>ReentrantLock.lockInterruptibly()</code> cho phép hủy việc đợi bằng <code>InterruptedException</code>.
- <code>Condition.awaitUninterruptibly()</code> không ném <code>InterruptedException</code> từ interrupt đang đợi; nó tiếp tục chờ cho tới khi thỏa điều kiện thức dậy theo hợp đồng, đồng thời bảo toàn trạng thái ngắt để người gọi có thể nhận biết sau khi trở về.
- <code>LockSupport.park()</code> có thể trở về vì interrupt **mà không xóa interrupt flag** và không ném <code>InterruptedException</code> theo cách <code>sleep()</code> làm.

Vì vậy, quan hệ giữa flag và hành vi chờ là **hợp đồng của API chờ**, không phải một quy tắc “mọi lời gọi blocking đều ném ngoại lệ” của JVM.

## 6. Thread.sleep(): nhận interrupt nhưng không giải phóng khóa

<code>Thread.sleep</code> là phương thức static làm **luồng hiện tại** tạm ngừng thực thi trong khoảng thời gian yêu cầu, trừ khi bị ngắt hoặc gặp điều kiện khác được API quy định.

Hai điểm rất quan trọng:

1. Khi bị ngắt trong lúc sleep, phương thức ném <code>InterruptedException</code> và xóa cờ ngắt theo hợp đồng.
2. <code>sleep()</code> **không tự giải phóng monitor hoặc Lock** mà luồng đang sở hữu.

Ví dụ minh họa trong một lớp có <code>monitor</code>:

~~~java
synchronized (monitor) {
    Thread.sleep(1_000);
}
~~~

Đoạn trên **chưa phải chương trình Java độc lập** và phương thức chứa nó phải xử lý/khai báo <code>InterruptedException</code>. Luồng giữ monitor trong thời gian sleep. Nếu sleep bị ngắt, trước khi ra khỏi khối <code>synchronized</code>, control flow sẽ đi theo ngữ nghĩa Java của việc thoát khối; monitor được nhả **do rời khỏi khối synchronized**, không phải do <code>sleep()</code> tự nhả khi bắt đầu chờ.

Tương tự:

~~~java
lock.lock();
try {
    Thread.sleep(1_000);
} finally {
    lock.unlock();
}
~~~

Đây là **mã minh họa** với biến <code>lock</code> kiểu <code>Lock</code> và phương thức có hợp đồng checked exception phù hợp. Nếu <code>sleep()</code> ném lỗi, <code>finally</code> nhả khóa. Giữ khóa khi ngủ thường làm tăng thời gian các luồng khác phải đợi và cần được xem xét lại trong thiết kế.

## 7. Object.wait(): tạm nhả monitor rồi lấy lại trước khi kết thúc

<code>Object.wait()</code> chỉ được gọi khi luồng hiện tại **sở hữu monitor** của đối tượng đang đợi, thường bên trong <code>synchronized (monitor)</code>. Nếu không sở hữu monitor, lời gọi có thể ném <code>IllegalMonitorStateException</code>.

Đoạn minh họa:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    consume();
}
~~~

Các biến <code>monitor</code>, <code>ready</code> và phương thức <code>consume()</code> là thành phần minh họa. Phương thức bao ngoài phải xử lý hoặc khai báo <code>InterruptedException</code>.

Khác với <code>sleep()</code>, <code>wait()</code> **tạm nhả monitor của đối tượng được đợi**, cho phép luồng khác vào vùng đồng bộ để cập nhật điều kiện và gọi <code>notify()</code>/<code>notifyAll()</code>. Trước khi <code>wait()</code> trả về hoặc ném <code>InterruptedException</code>, luồng phải lấy lại monitor đó theo ngữ nghĩa của API.

Một luồng có thể thức dậy vì tín hiệu, timeout (nếu dùng overload có thời hạn), interrupt hoặc *spurious wakeup*. Vì thế, điều kiện phải được kiểm tra trong **vòng <code>while</code>**, không mặc định dùng <code>if</code> một lần rồi tiếp tục.

Khi nhận interrupt trong lúc chờ:

- <code>wait()</code> ném <code>InterruptedException</code> sau bước lấy lại monitor cần thiết.
- Interrupted status bị xóa khi ném ngoại lệ.
- Nếu code để exception thoát khỏi khối <code>synchronized</code>, monitor được giải phóng theo quy tắc thoát khỏi vùng synchronized.
- Nếu code bắt ngoại lệ **ngay bên trong** vùng synchronized, tại thời điểm catch nó vẫn đang sở hữu monitor; cần quyết định rời khối hoặc xử lý sao cho không giữ monitor quá lâu.

**Không đồng nhất** “wait đã nhả monitor khi chờ” với “sau khi catch không còn giữ monitor”. Hai thời điểm này khác nhau.

## 8. Thread.join(): ngắt luồng đang chờ, không ngắt luồng được chờ

Xét:

~~~java
Thread worker = new Thread(() -> compute());
worker.start();
worker.join();
~~~

Đây là **mã minh họa**, giả định có <code>compute()</code> và phương thức gọi xử lý hoặc khai báo <code>InterruptedException</code>.

Lời gọi <code>worker.join()</code> khiến **luồng gọi join** chờ <code>worker</code> kết thúc. Nếu luồng gọi join bị interrupt, chính lời gọi <code>join()</code> có thể ném <code>InterruptedException</code>; điều đó **không chứng minh** <code>worker</code> đã kết thúc, cũng không tự động gọi <code>worker.interrupt()</code>.

Do đó, handler của luồng quản lý cần quyết định chính sách:

- Dừng chờ và báo rằng tác vụ quản lý bị hủy.
- Truyền <code>InterruptedException</code> cho tầng điều phối nếu chữ ký cho phép.
- Nếu trách nhiệm dọn dẹp yêu cầu đợi worker kết thúc, thiết kế một quy trình hủy/đợi riêng, không tự động nuốt interrupt hoặc chờ vô thời hạn.

Không viết một vòng lặp <code>while (worker.isAlive()) worker.join()</code> rồi bỏ qua mọi <code>InterruptedException</code> nếu hệ thống muốn hỗ trợ hủy. Điều đó biến yêu cầu ngắt thành tín hiệu bị bỏ quên.

## 9. BlockingQueue.take(): chương trình Java 17+ với interrupt từ luồng khác

<code>BlockingQueue.take()</code> chờ một phần tử có sẵn. Khi queue rỗng, worker có thể block; nếu nhận interrupt theo hợp đồng, lời gọi chờ ném <code>InterruptedException</code> và worker phải quyết định xử lý yêu cầu hủy.

Ví dụ dưới đây dùng <code>LinkedBlockingQueue</code> rỗng và một <code>CountDownLatch</code> để điều phối thứ tự. Điều kiện đồng bộ cố ý **không phụ thuộc** vào việc worker đã kịp park/block tại chính xác thời điểm nào: nếu interrupt đến ngay trước khi <code>take()</code> bắt đầu, thao tác interruptible này vẫn nhận tín hiệu.

Tạo tệp **InterruptibleQueueDemo.java**:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;

public class InterruptibleQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            ready.countDown();

            try {
                String item = queue.take();
                System.out.println("Worker nhận: " + item);
            } catch (InterruptedException original) {
                System.out.println("Worker nhận InterruptedException");
                System.out.println("Cờ sau khi catch: "
                        + Thread.currentThread().isInterrupted());

                Thread.currentThread().interrupt();
                System.out.println("Cờ sau khi restore: "
                        + Thread.currentThread().isInterrupted());
            }
        }, "queue-worker");

        worker.start();
        ready.await();

        worker.interrupt();
        worker.join();

        System.out.println("Worker đã kết thúc: " + !worker.isAlive());
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 InterruptibleQueueDemo.java
java InterruptibleQueueDemo
~~~

Stdout của ví dụ (khi không có nguồn gửi interrupt khác):

~~~text
Worker nhận InterruptedException
Cờ sau khi catch: false
Cờ sau khi restore: true
Worker đã kết thúc: true
~~~

Phân tích:

1. <code>queue</code> bắt đầu rỗng và không có code nào thêm phần tử. Vì thế <code>take()</code> không thể hoàn thành bằng cách nhận một phần tử.
2. <code>ready.countDown()</code> cho phép <code>main</code> gửi interrupt sau khi worker đã khởi chạy. Nó **không chứng minh** worker đã hoàn toàn đi vào trạng thái chờ; ví dụ không yêu cầu điều đó để có kết quả đúng.
3. <code>worker.interrupt()</code> làm lời gọi <code>take()</code> đang chờ, hoặc chuẩn bị đi vào chờ, phản ứng bằng <code>InterruptedException</code>.
4. Khi vào <code>catch</code>, trạng thái ngắt của worker đã bị xóa theo cách xử lý interrupt của <code>take()</code>, vì vậy in <code>false</code>.
5. Worker khôi phục cờ bằng <code>Thread.currentThread().interrupt()</code> để bảo toàn tín hiệu cho code quản lý phía trên nếu có; in <code>true</code>.
6. Lambda kết thúc, <code>main</code> dùng <code>join()</code> để chờ worker thực sự dừng rồi mới in dòng cuối.

**Không diễn giải nhầm:** cờ được khôi phục thành <code>true</code> không khiến worker “sống tiếp” hay quay trở lại chờ. Trong ví dụ, worker kết thúc vì code đã thoát khỏi lambda. Quyết định kết thúc là do logic ứng dụng.

### Vì sao không bắt rồi lặp lại ngay?

Một dạng dễ gây lỗi:

~~~java
while (true) {
    try {
        process(queue.take());
    } catch (InterruptedException ignored) {
        // Lặp lại ngay, coi như chưa có yêu cầu hủy.
    }
}
~~~

Đoạn này là **mã minh họa cố ý sai**, giả định biến <code>queue</code> và <code>process()</code> có sẵn. Nó âm thầm bỏ yêu cầu ngắt. Với một worker phục vụ hệ thống có chính sách shutdown bằng interrupt, vòng lặp có thể làm tác vụ tiếp tục sau khi đã có tín hiệu dừng.

Nếu bắt rồi **khôi phục cờ nhưng vẫn lặp lại**, một số API chờ interruptible sẽ lập tức ném <code>InterruptedException</code> ở lần tiếp theo, có thể gây vòng quay nhanh tiêu thụ CPU. Vì vậy khi muốn tôn trọng yêu cầu hủy, thường cần **rời vòng lặp hoặc truyền ngoại lệ**, không chỉ restore rồi tiếp tục vô hạn.

## 10. Hai chiến lược đúng trong catch: truyền tiếp hoặc khôi phục

### Cách A — truyền InterruptedException lên tầng gọi

Nếu method được phép khai báo checked exception, cách đơn giản thường là **để <code>InterruptedException</code> lan truyền**:

~~~java
String awaitNextItem(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

Đoạn này là **mã minh họa trong một lớp có import phù hợp**, không phải chương trình độc lập. Tầng gọi sẽ nhận trực tiếp nguyên nhân yêu cầu chờ bị ngắt và chịu trách nhiệm quyết định hủy hoặc tiếp tục.

Trong trường hợp chỉ truyền ngoại lệ lên ngay, không bắt rồi gọi <code>Thread.currentThread().interrupt()</code> một cách máy móc nếu không có lý do rõ ràng. Hợp đồng checked exception đã cung cấp tín hiệu cho bên gọi; code tầng trên có thể thiết kế chính sách riêng.

### Cách B — không thể ném checked exception: restore và kết thúc

Giao diện <code>Runnable.run()</code> không cho phép khai báo <code>throws InterruptedException</code>. Khi worker nhận interrupt trong một thao tác chờ, một mẫu hợp lý là:

~~~java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String task = queue.take();
            process(task);
        }
    } catch (InterruptedException original) {
        Thread.currentThread().interrupt();
    } finally {
        releaseOwnedResources();
    }
}
~~~

Đây là **mã minh họa trong một lớp implements Runnable** có <code>queue</code>, <code>process(...)</code> và <code>releaseOwnedResources()</code> phù hợp.

- Việc <code>take()</code> ném ngoại lệ khiến control flow ra ngoài vòng lặp.
- <code>catch</code> khôi phục tín hiệu vì phương thức không thể truyền checked exception lên trên.
- <code>finally</code> giải phóng tài nguyên do worker sở hữu.
- Sau <code>catch/finally</code>, <code>run()</code> kết thúc. Code không lặp lại thao tác chờ như thể tín hiệu chưa từng tồn tại.

Có tình huống hợp đồng ứng dụng yêu cầu **chuyển lỗi thành unchecked exception**. Khi ấy nên truyền ngoại lệ gốc vào cause, ví dụ:

~~~java
catch (InterruptedException original) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Tác vụ bị ngắt", original);
}
~~~

Đây chỉ là **khối catch minh họa** trong ngữ cảnh phù hợp. Cần quyết định rõ ngoại lệ loại nào mô tả hủy tác vụ; <code>IllegalStateException</code> ở đây minh họa cơ chế, không phải mẫu tên bắt buộc. Việc đặt cờ lại giữ thông tin cho code kiểm tra trạng thái ngắt, còn cause bảo toàn dấu vết <code>InterruptedException</code> đã ném.

### Khi nào không nên restore?

Nếu một API của bạn **thực sự tiêu thụ yêu cầu interrupt** theo hợp đồng được công bố, thực hiện xong quy trình phục hồi và quyết định tiếp tục công việc, nó có thể xử lý theo chính sách riêng. Nhưng đó phải là quyết định có lý do, không phải một <code>catch (InterruptedException ignored)</code> chung.

Một trường hợp phổ biến không cần tự restore ở tầng trung gian là khi **truyền <code>InterruptedException</code> lên ngay** cho tầng đã nhận trách nhiệm hủy. Không có một quy tắc yêu cầu mọi catch đều vừa restore vừa throw checked exception.

## 11. Khác nhau giữa Thread.interrupted() và isInterrupted() trong vòng lặp

Hãy xem:

~~~java
while (!Thread.interrupted()) {
    doWork();
}
~~~

Đây là **mã minh họa**. Nó dùng lời gọi static để tiêu thụ interrupt flag. Khi vòng lặp thoát vì <code>Thread.interrupted()</code> đã trả về <code>true</code>, cờ đã bị **xóa**. Đây có thể là thiết kế có chủ đích của một thành phần tiêu thụ tín hiệu; nhưng dễ làm mất thông tin mà những tầng sau cần quan sát.

Trong một worker muốn để các đoạn cleanup hoặc caller biết yêu cầu ngắt đã xảy ra, thường rõ ràng hơn:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    doWork();
}
~~~

<code>isInterrupted()</code> không xóa cờ. Việc rời vòng lặp không tự xóa yêu cầu dừng.

Nếu cần truy vấn trạng thái của **luồng khác** từ bộ quản lý, dùng <code>worker.isInterrupted()</code>. Tuy nhiên, đọc cờ không chứng minh công việc đã ngừng, tài nguyên đã được nhả, hay luồng đã chết. Để chờ kết thúc, phải dùng cơ chế đồng bộ phù hợp như <code>join()</code> hoặc completion API.

Một số thư viện/framework có thể tự xử lý interrupt trong các phương thức chờ. Vì vậy, **một giá trị <code>false</code> đọc sau này không chứng minh chưa từng có interrupt**. Đối với kiểm thử và quan sát, cần biết API nào đã nhận và có thể đã tiêu thụ tín hiệu.

## 12. Lock.lockInterruptibly(): interrupt trước khi lấy khóa

<code>java.util.concurrent.locks.Lock</code> cung cấp cách lấy khóa có thể bị ngắt qua <code>lockInterruptibly()</code>. Với <code>ReentrantLock</code>, nếu luồng bị interrupt khi đang đợi khóa hoặc có trạng thái ngắt tại thời điểm vào lời gọi, phương thức ném <code>InterruptedException</code> và xóa trạng thái ngắt theo hợp đồng.

Mẫu đúng:

~~~java
lock.lockInterruptibly();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Đây là **mã minh họa** trong một phương thức khai báo/xử lý <code>InterruptedException</code>, có <code>lock</code> và <code>updateSharedState()</code>. <code>lockInterruptibly()</code> đặt **trước** <code>try</code> để nếu lời gọi bị ngắt trước khi lấy khóa, <code>finally</code> không chạy và không nhả một khóa chưa sở hữu.

### Ví dụ Java 17+ độc lập: hủy lúc đang tranh khóa

Tạo tệp **InterruptibleLockDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch ready = new CountDownLatch(1);

        lock.lock();
        try {
            Thread contender = new Thread(() -> {
                ready.countDown();
                try {
                    lock.lockInterruptibly();
                    try {
                        System.out.println("Contender đã lấy khóa");
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException original) {
                    System.out.println("Contender bị ngắt khi đợi khóa");
                    System.out.println("Cờ khi catch: "
                            + Thread.currentThread().isInterrupted());
                    Thread.currentThread().interrupt();
                    System.out.println("Cờ sau restore: "
                            + Thread.currentThread().isInterrupted());
                }
            }, "contender");

            contender.start();
            ready.await();

            contender.interrupt();
            contender.join();

            System.out.println("Main vẫn giữ khóa: "
                    + lock.isHeldByCurrentThread());
        } finally {
            lock.unlock();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 InterruptibleLockDemo.java
java InterruptibleLockDemo
~~~

Stdout:

~~~text
Contender bị ngắt khi đợi khóa
Cờ khi catch: false
Cờ sau restore: true
Main vẫn giữ khóa: true
~~~

**Vì sao kết quả xác định?**

- Luồng <code>main</code> lấy khóa trước khi tạo luồng contender, nên contender không thể lấy khóa khi <code>main</code> còn giữ.
- <code>ready</code> bảo đảm contender đã được khởi chạy; interrupt có thể xảy ra ngay trước hoặc trong <code>lockInterruptibly()</code>, và cả hai thời điểm đều dẫn tới <code>InterruptedException</code> với cách triển khai này.
- Contender chưa lấy được khóa, nên nhánh <code>catch</code> không gọi <code>unlock()</code>. Nếu gọi nhả khóa sai, <code>ReentrantLock</code> sẽ ném <code>IllegalMonitorStateException</code>.
- Sau khi <code>contender.join()</code> hoàn tất, <code>main</code> vẫn sở hữu khóa và in <code>true</code>, sau đó mới nhả trong <code>finally</code>.

Nếu thay lời gọi bằng <code>lock.lock()</code>, việc đợi sẽ **không ném InterruptedException theo cùng cơ chế**. Trong ví dụ này, luồng main đang giữ khóa; nếu main đợi contender bằng <code>join()</code> trong khi contender chờ khóa không thể hủy, chương trình có thể bị kẹt do quan hệ chờ vòng. Đây là lý do phải lựa chọn hợp đồng lấy khóa phù hợp với chính sách hủy.

## 13. Condition.await(): khi bị ngắt, phải lấy lại khóa trước khi thoát

<code>Condition</code> thường gắn với một <code>ReentrantLock</code>. Khi một luồng gọi <code>condition.await()</code> trong khi sở hữu khóa, lời gọi tạm nhả khóa đó để luồng khác có thể thay đổi điều kiện và đánh thức nó.

Một mẫu thường dùng:

~~~java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    consume();
} finally {
    lock.unlock();
}
~~~

Đây là **mã minh họa** với <code>lock</code>, <code>condition</code>, <code>ready</code> và <code>consume()</code> được cung cấp bởi lớp bao ngoài; phương thức phải xử lý/khai báo <code>InterruptedException</code>.

Lưu ý:

- <code>Condition.await()</code> có thể bị ngắt bằng <code>InterruptedException</code>.
- <code>ReentrantLock</code> sẽ được lấy lại trước khi lời gọi <code>await()</code> hoàn tất bằng cách ném lỗi theo hợp đồng của Condition; vì vậy khi đi vào <code>finally</code>, code vẫn có quyền nhả lần giữ khóa đã lấy trước đó.
- Điều kiện phải được kiểm tra trong <code>while</code> vì tín hiệu đánh thức không bảo đảm bất biến vẫn còn đúng tại thời điểm luồng lấy lại khóa, và có thể có *spurious wakeup*.
- Nếu bắt ngoại lệ ngay bên trong vùng khóa để khôi phục hoặc chuyển lỗi, đừng giữ khóa quá lâu sau khi đã quyết định hủy.

Khác với <code>lockInterruptibly()</code>, một luồng gọi <code>await()</code> **đã sở hữu khóa trước khi chờ**. Do đó việc <code>await()</code> ném <code>InterruptedException</code> không có nghĩa không cần <code>unlock()</code>: trong cấu trúc chuẩn, <code>finally</code> vẫn phải giải phóng khóa sau khi nó được lấy lại.

Với <code>awaitUninterruptibly()</code>, interrupt không làm phát sinh <code>InterruptedException</code> để chấm dứt việc chờ theo cơ chế này; cờ ngắt vẫn được bảo toàn/khôi phục theo hợp đồng của implementation. Không dùng biến thể này cho một tác vụ mà chính sách yêu cầu hủy chờ kịp thời.

## 14. LockSupport.park(): trường hợp không ném InterruptedException

<code>java.util.concurrent.locks.LockSupport.park()</code> là primitive cấp thấp thường được các thư viện đồng bộ hóa dùng để đỗ luồng. Nó có thể trả về khi luồng bị interrupt, nhưng **không ném <code>InterruptedException</code>** và **không xóa interrupt flag** chỉ vì trở về do interrupt.

Minh họa trong một phương thức:

~~~java
java.util.concurrent.locks.LockSupport.park();
boolean interrupted = Thread.currentThread().isInterrupted();
~~~

Đoạn này là **mã minh họa**, không phải ví dụ chạy độc lập vì <code>park()</code> có thể chờ vô thời hạn nếu không có nguyên nhân thức dậy. Nếu <code>park()</code> trả về do cờ ngắt đang bật, <code>interrupted</code> thường là <code>true</code> cho tới khi code chủ động tiêu thụ cờ hoặc một cơ chế khác thay đổi trạng thái.

Vì cờ vẫn bật, việc gọi <code>park()</code> lặp lại mà không xử lý interrupt có thể trả về ngay, tạo vòng quay không mong muốn. Các thuật toán dùng <code>LockSupport</code> phải tự quản lý điều kiện chờ, permit, trạng thái ngắt và các lần thức dậy bất thường.

Sự khác biệt này nhấn mạnh rằng **interruptible wait** có nhiều kiểu: ném checked exception và xóa flag, trở về bình thường với flag được giữ, hoặc tiếp tục chờ trong biến thể uninterruptible.

## 15. Tính hủy hợp tác: kết thúc có trật tự

Một yêu cầu ngắt thường xuất hiện khi hệ thống muốn dừng worker, đóng ứng dụng hoặc hủy một task:

~~~text
Bộ điều phối muốn dừng
          |
          | worker.interrupt()
          v
Worker đang tính toán hoặc chờ
          |
          +--- isInterrupted() thấy true ------+
          |                                    |
          +--- wait ném InterruptedException --+
                                               |
                                               v
                                   Đặt chính sách kết thúc
                                               |
                                    finally/close/cleanup
                                               |
                                               v
                                        Worker kết thúc
~~~

Tín hiệu interrupt **không tự động rollback dữ liệu hoặc đóng mọi tài nguyên**. Nếu tác vụ đang thực hiện nhiều bước, cần thiết kế trạng thái trung gian sao cho ngừng ở điểm hợp lệ, hoàn tất cleanup, hoặc ghi nhận một kết quả hủy rõ ràng.

Một số nguyên tắc thực hành:

- Không dùng <code>Thread.stop()</code> để ép dừng một luồng: hành vi ngắt cưỡng bức không an toàn đối với bất biến dữ liệu.
- Đừng giữ khóa quá lâu khi chờ I/O hoặc một điều kiện mà chính sách cần hủy sớm.
- Với thao tác có tác dụng phụ, không tự động thử lại chỉ vì nhận interrupt: công việc có thể đã hoàn thành một phần.
- Nếu API async của bạn có trạng thái cancelled riêng, hãy phân biệt tín hiệu interrupt với kết quả hủy đã được xác nhận.
- Khi muốn dừng worker, có thể kết hợp một cờ điều khiển ứng dụng và interrupt để đánh thức thao tác chờ; tránh giả định mọi API blocking đều được ngắt bằng cùng cơ chế.

### Future.cancel(true) không đồng nghĩa worker chắc chắn đã dừng

Khi sử dụng <code>Future</code>, <code>cancel(true)</code> có thể yêu cầu interrupt luồng đang thực thi task nếu implementation hỗ trợ. Nó **không cưỡng bức** mọi đoạn code chấp nhận hủy; một task cố tình bỏ qua interrupt hoặc đang chờ trong API không phản ứng tương ứng có thể còn chạy. Đừng dùng trạng thái <code>Future.isCancelled()</code> như bằng chứng duy nhất rằng các tác dụng phụ đang chạy đã chấm dứt tại đúng thời điểm.

Ngược lại, một task tự phát sinh <code>InterruptedException</code> rồi được lưu như lỗi trong cơ chế future chưa chắc đã trở thành trạng thái “cancelled” trừ khi hợp đồng của framework định nghĩa như vậy.

## 16. Những lỗi thường gặp với interrupt flag và API chờ

### Lỗi 1 — catch InterruptedException rồi im lặng

~~~java
try {
    Thread.sleep(500);
} catch (InterruptedException ignored) {
    // Không thông báo và tiếp tục công việc như bình thường.
}
~~~

Đây là **mã minh họa cố ý không khuyến nghị**. Sau khi <code>sleep()</code> ném ngoại lệ, cờ đã bị xóa. Lỗi bị nuốt, và các tầng sau không nhận được yêu cầu dừng. Nếu việc tiếp tục thật sự được phép theo hợp đồng, cần ghi rõ logic xử lý riêng; trong phần lớn worker có chính sách hủy, nên truyền lỗi hoặc restore và kết thúc.

### Lỗi 2 — tưởng isInterrupted() xóa cờ

~~~java
boolean first = Thread.currentThread().isInterrupted();
boolean second = Thread.currentThread().isInterrupted();
~~~

Hai lần đọc không tự thay đổi trạng thái; nếu không có lời gọi/API khác tác động, chúng quan sát cùng một giá trị. Khác với <code>Thread.interrupted()</code> vốn xóa cờ.

### Lỗi 3 — dùng Thread.interrupted() chỉ để ghi log

~~~java
System.out.println("Interrupted: " + Thread.interrupted());
~~~

Đây là **mã minh họa**. Dòng log có tác dụng phụ: nếu cờ đang bật, nó bị xóa. Nếu chỉ muốn quan sát, dùng <code>Thread.currentThread().isInterrupted()</code> để giữ tín hiệu.

### Lỗi 4 — restore nhưng tiếp tục chờ ngay

~~~java
while (true) {
    try {
        queue.take();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
}
~~~

Đây là **mã cố ý sai**, với <code>queue</code> có sẵn. Sau restore, lần <code>take()</code> tiếp theo có thể ném ngay, khiến vòng lặp quay nhanh. Nếu interrupt có nghĩa hủy, nên rời vòng lặp; nếu thiết kế cần tiếp tục, phải có chính sách tiêu thụ tín hiệu rõ ràng, không dùng cách trên.

### Lỗi 5 — cho rằng sleep() hoặc join() nhả mọi khóa

<code>sleep()</code> không nhả monitor/lock. <code>join()</code> không tự nhả những khóa tùy ý mà luồng gọi đang giữ. Chờ khi đang giữ khóa mà worker cần có thể dẫn tới deadlock. <code>Object.wait()</code> chỉ tạm nhả monitor tương ứng của đối tượng được wait; <code>Condition.await()</code> làm tương tự với lock gắn với condition theo hợp đồng.

### Lỗi 6 — unlock() sau khi lockInterruptibly thất bại

~~~java
try {
    lock.lockInterruptibly();
    work();
} finally {
    lock.unlock();
}
~~~

Đây là **mã minh họa cố ý sai** khi <code>lock</code> là <code>ReentrantLock</code>: nếu <code>lockInterruptibly()</code> ném trước khi lấy được khóa, <code>finally</code> vẫn chạy và có thể ném <code>IllegalMonitorStateException</code>. Mẫu đúng là lấy khóa trước, rồi mới vào <code>try/finally</code> để nhả khóa.

### Lỗi 7 — xem interrupt là ngoại lệ luôn được ném

Một vòng lặp CPU không kiểm tra cờ có thể tiếp tục chạy. <code>LockSupport.park()</code> có thể trở về mà không ném <code>InterruptedException</code>. <code>ReentrantLock.lock()</code> có thể tiếp tục chờ. Cần tra đúng hợp đồng API.

### Lỗi 8 — đánh đồng tín hiệu ngắt với hoàn tất hủy

<code>worker.interrupt()</code> chỉ gửi tín hiệu. Sau đó cần đợi hoặc quan sát bằng <code>join()</code>, <code>Future</code>, latch hoặc cơ chế quản lý phù hợp nếu muốn biết worker đã kết thúc. Không kiểm tra cờ rồi khẳng định cleanup đã xong.

### Lỗi 9 — bắt Exception quá rộng và xử lý như lỗi nghiệp vụ

~~~java
try {
    performTask();
} catch (Exception error) {
    reportFailure(error);
}
~~~

Đây là **mã minh họa**. Nếu bên trong có <code>InterruptedException</code> bị bắt qua <code>Exception</code>, tín hiệu hủy có thể bị mất. Đặc biệt khi dùng các wrapper hoặc framework xử lý exception, cần phân biệt thất bại nghiệp vụ thông thường với yêu cầu ngắt của luồng.

## 17. Kiểm thử những gì?

Một bộ kiểm thử có giá trị nên phân biệt **trạng thái cờ**, **ngoại lệ được ném**, **quyền sở hữu khóa** và **kết quả hủy**:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Gọi <code>interrupt()</code> rồi <code>isInterrupted()</code> | Cờ bật; phép đọc không xóa |
| Gọi <code>Thread.interrupted()</code> khi cờ đang bật | Trả về <code>true</code> và xóa cờ |
| Cờ bật trước <code>sleep()</code> | <code>InterruptedException</code> và cờ bị xóa |
| Worker bị ngắt trong <code>BlockingQueue.take()</code> | Lời gọi chờ báo ngắt, worker theo chính sách kết thúc |
| Catch và restore | Cờ được đặt lại nếu code chủ động gọi <code>interrupt()</code> |
| Ngắt khi <code>lockInterruptibly()</code> chưa lấy khóa | Không nhả khóa chưa sở hữu |
| Ngắt trong <code>Condition.await()</code> | Khóa được lấy lại theo hợp đồng rồi giải phóng đúng từ <code>finally</code> |
| Ngắt luồng đang gọi <code>join()</code> | Không kết luận luồng đích đã dừng |
| Tác vụ thực thi không kiểm tra cờ | Không giả định nó tự dừng chỉ vì nhận interrupt |
| <code>park()</code> trở về vì interrupt | Không nhầm với đường ném <code>InterruptedException</code> của sleep |

Với kiểm thử đa luồng, nên dùng <code>CountDownLatch</code>, queue hoặc cơ chế đồng bộ tương đương để đặt thứ tự kiểm chứng thay vì chỉ gọi <code>Thread.sleep()</code> để “chờ cho đủ lâu”. Nếu một lỗi có thể khiến test bị kẹt, cần giới hạn thời gian chờ phù hợp và dọn tài nguyên sau phép thử.

Đối với kiểm tra trạng thái cờ ngay sau khi nhận <code>InterruptedException</code>, xác định rõ có luồng nào khác đang gửi interrupt tiếp hay không. Nếu có tín hiệu ngắt mới, việc quan sát <code>true</code> không phủ nhận hợp đồng rằng phương thức chờ đã xóa trạng thái cho lần interrupt nó xử lý.

## 18. Checklist áp dụng trong dự án

Khi một phương thức gọi API blocking, hãy tự hỏi:

1. **API này có thể bị ngắt không?** Nó ném <code>InterruptedException</code>, trả về sớm nhưng giữ cờ, hay tiếp tục chờ?
2. **Cờ ở đâu sau khi bị ngắt?** Kiểm tra hợp đồng API, đừng dự đoán từ tên phương thức.
3. **Hợp đồng tầng hiện tại là gì?** Có thể khai báo <code>throws InterruptedException</code> và chuyển lên không?
4. **Nếu phải catch**, nên khôi phục cờ và rời thao tác, hay có quy tắc xử lý tín hiệu riêng thực sự hợp lệ?
5. **Có tránh mất cờ do gọi <code>Thread.interrupted()</code> không chủ đích** không?
6. **Có đang giữ khóa hoặc tài nguyên khi chờ** không? API nào nhả tạm, API nào không?
7. **Khi chờ khóa bị ngắt**, code đã tránh gọi <code>unlock()</code> nếu chưa sở hữu khóa chưa?
8. **Việc hủy có để lại dữ liệu cập nhật dở dang không?** Tài nguyên và bất biến có được bảo vệ bởi <code>finally</code>/giao thức cập nhật phù hợp không?
9. **Có cơ chế xác nhận hoàn tất** như <code>join()</code> hay completion state, thay vì chỉ dựa vào tín hiệu <code>interrupt()</code> không?
10. **Kiểm thử có phân biệt** ngoại lệ, cờ ngắt và sự hoàn tất thực tế của task không?

**Điều cốt lõi:** interrupt flag là **trạng thái tín hiệu hợp tác của luồng**. Một phương thức chờ có thể phản ứng với tín hiệu bằng <code>InterruptedException</code> rồi xóa cờ, hoặc bằng cách khác theo hợp đồng. Khi bắt <code>InterruptedException</code>, ứng dụng phải quyết định rõ **truyền tiếp**, **khôi phục tín hiệu rồi thoát**, hoặc **xử lý có chủ đích**. Quản lý đúng quan hệ đó giúp hệ thống ngừng công việc có trật tự mà không âm thầm bỏ qua yêu cầu hủy.