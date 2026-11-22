# Monitor của mỗi đối tượng trong Java và cơ chế đồng bộ

Trong Java, **mỗi đối tượng có thể được dùng làm khóa đồng bộ nội tại (intrinsic lock, thường gọi là monitor)**. Khi một luồng đi vào khối `synchronized` gắn với đối tượng đó, nó phải sở hữu monitor của đối tượng trước khi thực thi phần code được bảo vệ. Cơ chế này giúp phối hợp truy cập dữ liệu dùng chung và tạo bảo đảm về khả năng nhìn thấy thay đổi giữa các luồng.

> “Mỗi đối tượng có monitor” là mô hình lập trình và ngữ nghĩa mà Java cung cấp. JVM có thể tối ưu cách biểu diễn và cấp phát khóa ở mức triển khai; không nên suy luận rằng mọi instance đều phải có một cấu trúc monitor riêng được cấp phát sẵn trong bộ nhớ.

## 1. Monitor gắn với **đối tượng nào**?

Ví dụ:

~~~java
Object lockA = new Object();
Object lockB = new Object();

synchronized (lockA) {
    // Luồng đang giữ monitor của lockA.
}

synchronized (lockB) {
    // Một monitor khác, độc lập với lockA.
}
~~~

- Hai luồng cùng dùng **chính xác cùng một đối tượng** `lockA` sẽ phải cạnh tranh cùng một intrinsic lock: tại một thời điểm tối đa một luồng sở hữu monitor ấy để thực thi đoạn `synchronized` tương ứng.
- Một luồng giữ monitor của `lockA` không tự động ngăn luồng khác đi vào `synchronized (lockB)`. Hai khóa khác nhau không bảo vệ lẫn nhau.
- Mỗi đối tượng Java có thể làm khóa, kể cả instance của lớp do ta tạo, mảng và đối tượng `Class`. `null` không phải đối tượng; `synchronized (null)` gây `NullPointerException`.
- Biến tham chiếu **không sở hữu monitor riêng**. Hai biến cùng trỏ đến một instance sẽ dùng cùng khóa; hai instance khác nhau có khóa khác nhau.

Một ví dụ quan trọng về đối tượng được khóa:

| Cú pháp | Monitor phải sở hữu |
| --- | --- |
| `synchronized (someObject) { ... }` | Đối tượng mà `someObject` trỏ tới |
| `synchronized void method()` (phương thức instance) | `this` của instance đang gọi |
| `static synchronized void method()` | Đối tượng `SomeClass.class` tương ứng với lớp khai báo |

Bởi vậy, phương thức `static synchronized` **không khóa mọi instance** theo nghĩa khóa của `this`. Nó khóa đối tượng `Class`; đồng bộ tĩnh và đồng bộ instance thường là hai monitor khác nhau.

## 2. Khi đi vào và rời `synchronized` xảy ra điều gì?

Giả sử nhiều luồng cùng chạy:

~~~java
synchronized (lock) {
    // Truy cập trạng thái dùng chung do lock bảo vệ.
}
~~~

Trình tự logic:

1. Luồng yêu cầu quyền sở hữu monitor của `lock`.
2. Nếu monitor rảnh, luồng giành khóa và chạy phần thân. Nếu một luồng khác đang giữ nó, luồng hiện tại không thể vào phần thân ngay và có thể chuyển sang trạng thái `BLOCKED`.
3. Khi rời khối, kể cả khi thoát do exception, luồng nhả khóa theo ngữ nghĩa của `synchronized`; một luồng đang chờ khóa có thể tiếp tục cạnh tranh để giành monitor.
4. Java **không hứa hẹn công bằng/FIFO** về luồng nào sẽ giành khóa tiếp theo.

Monitor là **reentrant**: một luồng đã sở hữu monitor có thể vào `synchronized` khác trên cùng đối tượng mà không tự chặn chính mình. JVM theo dõi mức lồng nhau và khóa chỉ được nhả hoàn toàn sau khi luồng thoát hết các mức khóa tương ứng.

~~~java
class ReentrantExample {
    synchronized void outer() {
        inner(); // Cùng luồng tiếp tục đi vào monitor của this.
    }

    synchronized void inner() {
        // Có thể thực hiện dù outer() đang giữ chính monitor này.
    }
}
~~~

Nhớ rằng chỉ code thực sự dùng **cùng monitor** mới được bảo vệ. Một hàm đọc hoặc ghi trường dùng chung mà bỏ qua khóa sẽ không tự động được an toàn chỉ vì hàm khác có `synchronized`.

## 3. Monitor giải quyết hai vấn đề: loại trừ tương hỗ và visibility

Giả sử hai luồng cùng tăng một biến:

~~~java
count++;
~~~

Lệnh này về mặt logic gồm đọc giá trị, tính giá trị mới rồi ghi lại. Nó không tự động là một thao tác nguyên tử. Hai luồng có thể cùng đọc một giá trị cũ và làm mất một lần tăng.

Ví dụ hoàn chỉnh, chạy với Java 17 trở lên:

**Tệp `MonitorCounterDemo.java`**

~~~java
public class MonitorCounterDemo {
    static final class Counter {
        private int count;

        synchronized void increment() {
            count++;
        }

        synchronized int get() {
            return count;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable task = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("So lan tang: " + counter.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MonitorCounterDemo.java
java MonitorCounterDemo
~~~

Kết quả:

~~~text
So lan tang: 20000
~~~

Cả hai luồng gọi `increment()` trên **cùng instance `counter`**, nên chúng phải lần lượt nắm monitor của instance đó. `count++` được bảo vệ như một vùng tới hạn; không bị mất cập nhật giữa hai luồng này. `get()` cũng đi qua monitor ấy. `join()` bảo đảm main chờ cả hai luồng kết thúc trước khi in kết quả.

Ngoài loại trừ tương hỗ, `synchronized` có quy tắc **happens-before** của Java Memory Model: thao tác **mở khóa một monitor** happens-before thao tác **khóa lại chính monitor đó** xảy ra sau. Nhờ đó, các ghi trước khi nhả khóa được nhìn thấy đúng qua lần giành khóa tiếp theo cùng monitor. Điều kiện “cùng monitor” rất quan trọng; khóa một đối tượng khác không tạo ra quan hệ này.

Không nên quy mọi hiệu ứng visibility cho monitor nếu ví dụ còn dùng `Thread.start()`/`Thread.join()`: bản thân các thao tác vòng đời luồng này cũng có quy tắc happens-before riêng. Điều cốt lõi của `synchronized` là code đọc và ghi dữ liệu chung tuân thủ **cùng một chính sách khóa**.

## 4. Monitor còn cho phép **chờ một điều kiện** qua `wait` / `notify` / `notifyAll`

Ngoài quyền sở hữu khóa, mỗi đối tượng cung cấp các thao tác phối hợp luồng kế thừa từ `java.lang.Object`:

- `wait()`: luồng hiện tại chờ tín hiệu/điều kiện trên đối tượng, **tạm nhả monitor của chính đối tượng đó** trong thời gian chờ.
- `notify()`: đánh thức **một** luồng đang chờ trên đối tượng đó, nếu có; không đảm bảo chọn luồng nào.
- `notifyAll()`: đánh thức **tất cả** luồng đang chờ trên đối tượng đó để chúng có cơ hội kiểm tra điều kiện.

Muốn gọi các phương thức này trên `obj`, luồng gọi phải **đang sở hữu monitor của `obj`** (ví dụ đang ở trong `synchronized (obj)` hay synchronized instance method của `obj`). Nếu không, `IllegalMonitorStateException` được ném ra. Có được monitor của **đối tượng khác** là chưa đủ.

Luồng gọi `wait()` phải lấy lại monitor của đối tượng trước khi thoát khỏi `wait()` và tiếp tục chạy. `notify()` và `notifyAll()` **không lập tức nhả khóa**: luồng được đánh thức chỉ có thể tiếp tục sau khi monitor sẵn có để giành lại.

Có thể hình dung hai lý do chờ khác nhau:

| Tình huống | Ý nghĩa |
| --- | --- |
| Luồng muốn vào `synchronized` nhưng monitor đang bị giữ | Chờ **giành khóa**; thường quan sát ở trạng thái `BLOCKED` |
| Luồng đã có monitor rồi gọi `wait()` | Nhả monitor tương ứng và chờ **điều kiện/tín hiệu**; `WAITING` hoặc `TIMED_WAITING` với wait có timeout |
| Luồng được `notifyAll()` đánh thức | Phải **giành lại monitor**; có thể tạm `BLOCKED` trước khi thoát `wait()` |

Các trạng thái trên giúp đọc thread dump; thứ tự scheduling cụ thể vẫn phụ thuộc JVM/hệ điều hành.

## 5. Ví dụ điều kiện thực tế: hộp thư một phần tử

Một luồng gửi giá trị, luồng khác nhận. Cả `send()` và `receive()` đồng bộ trên **chính instance `Mailbox`**. Điều kiện được biểu diễn bằng `message == null`:

**Tệp `MonitorWaitNotifyDemo.java`**

~~~java
public class MonitorWaitNotifyDemo {
    static final class Mailbox {
        private Integer message;

        synchronized void send(int value) throws InterruptedException {
            while (message != null) {
                wait();             // Chờ hộp thư trống; nhả monitor của this.
            }
            message = value;
            notifyAll();            // Báo trạng thái hộp thư đã thay đổi.
        }

        synchronized int receive() throws InterruptedException {
            while (message == null) {
                wait();             // Chờ có dữ liệu; nhả monitor của this.
            }
            int result = message;
            message = null;
            notifyAll();            // Báo hộp thư lại trống.
            return result;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Mailbox mailbox = new Mailbox();
        int[] received = {-1};

        Thread reader = new Thread(() -> {
            try {
                received[0] = mailbox.receive();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        reader.start();

        mailbox.send(42);
        reader.join();

        System.out.println("Nhan duoc: " + received[0]);
    }
}
~~~

Chạy:

~~~bash
javac MonitorWaitNotifyDemo.java
java MonitorWaitNotifyDemo
~~~

Kết quả khi không có yêu cầu ngắt luồng:

~~~text
Nhan duoc: 42
~~~

Giải thích luồng chạy:

1. Nếu `reader` vào `receive()` trước, nó thấy `message == null` rồi `wait()`; việc chờ nhả monitor để luồng main có thể vào `send()`.
2. `send(42)` lưu giá trị và gọi `notifyAll()` trong khi giữ monitor. Khi `send()` rời phương thức, nó nhả monitor; `reader` lấy lại monitor, kiểm tra điều kiện và nhận `42`.
3. Nếu main chạy `send(42)` trước, `reader` sẽ thấy dữ liệu đã sẵn có nên không cần đợi. Vì trạng thái điều kiện được lưu trong `message`, tín hiệu không phải vật chứa dữ liệu.
4. Sau `reader.join()`, main đọc kết quả đã ghi. Kết quả in ra độc lập với thứ tự hai luồng được lập lịch trong trường hợp không bị ngắt.

**Vì sao phải dùng `while` thay cho `if` quanh `wait()`?** Một luồng có thể thức dậy mà chưa có điều kiện mong muốn (*spurious wakeup*), hoặc luồng khác đã thay đổi điều kiện trong khoảng thời gian luồng đang tìm cách giành lại monitor. Luôn kiểm tra lại **predicate của trạng thái** dưới cùng monitor. Với nhiều kiểu người chờ/điều kiện, `notifyAll()` thường dễ lập luận đúng hơn `notify()`, dù có thể làm nhiều luồng thức dậy kiểm tra rồi lại chờ.

Khi `wait()` bị ngắt, nó ném `InterruptedException` sau khi lấy lại monitor theo ngữ nghĩa API; ứng dụng nên truyền ngoại lệ lên nơi điều phối hoặc xử lý hủy tác vụ rõ ràng. Ví dụ trên khôi phục cờ ngắt cho luồng con ở ranh giới `Runnable`. Trong ứng dụng thực tế, nên có đường đi xử lý kết quả bị hủy/thất bại thay vì mặc định nhận được một thông điệp.

## 6. Phân biệt rõ `wait`, `notify`, `sleep` và tranh chấp khóa

| Hoạt động | Cần sở hữu monitor? | Có nhả monitor đang giữ? | Mục đích |
| --- | --- | --- | --- |
| Vào `synchronized (obj)` | Phải giành monitor `obj` | Không | Bảo vệ vùng tới hạn |
| `obj.wait()` | Có, của `obj` | Có, **chỉ monitor của `obj`** | Chờ điều kiện trên `obj` |
| `obj.notify()` / `notifyAll()` | Có, của `obj` | Không | Thông báo cho luồng đang chờ |
| `Thread.sleep(...)` | Không | Không | Tạm ngừng theo thời gian |

Một lưu ý dễ bỏ sót: nếu luồng đang giữ nhiều monitor lồng nhau, `obj.wait()` chỉ nhả monitor của `obj`, **không nhả các monitor khác** mà luồng đó đang giữ. Việc giữ các khóa khác trong lúc chờ có thể làm chương trình bế tắc.

Các biến thể `wait(long timeout)` / `wait(long timeout, int nanos)` có thể kết thúc khi hết thời gian, được thông báo hoặc bị đánh thức không có lý do xác định; vì vậy vẫn cần vòng `while` kiểm tra điều kiện. `wait(0)` là chờ vô thời hạn, không phải “chờ 0 mili giây rồi trả về”.

## 7. Những sai lầm phổ biến và cách tránh

**Sai: khóa một đối tượng mới mỗi lần gọi.**

~~~java
synchronized (new Object()) {
    // Mỗi lần thường là một khóa mới, không phối hợp với các lời gọi khác.
}
~~~

Muốn phối hợp giữa các luồng, chia sẻ cùng một lock ổn định, chẳng hạn trường `private final Object lock = new Object();`. Tránh khóa trên chuỗi literal, đối tượng `Class` công khai hoặc đối tượng mà code bên ngoài có thể tự ý khóa nếu điều đó gây tranh chấp ngoài dự kiến.

**Sai: gọi `wait()` khi không sở hữu khóa của đúng đối tượng.**

~~~java
Object lock = new Object();
lock.wait(); // IllegalMonitorStateException khi chạy.
~~~

Cách dùng đúng (đoạn dưới chỉ minh họa cú pháp; muốn chương trình hữu ích phải có điều kiện và luồng gửi tín hiệu):

~~~java
synchronized (lock) {
    while (!conditionIsTrue()) {
        lock.wait();
    }
}
~~~

Ở đây `conditionIsTrue()` là tên **minh họa**, không phải phương thức đã được định nghĩa trong ví dụ runnable ở trên.

**Sai: tưởng `notify()` chuyển ngay khóa sang luồng nhận.** Luồng báo vẫn giữ monitor cho tới khi rời `synchronized`; luồng nhận phải cạnh tranh lại để giành khóa.

**Sai: đặt `wait()` trong `if` hoặc phụ thuộc hoàn toàn vào “tín hiệu”.** Tín hiệu không lưu trữ thành một “vé” cho người đến sau. Phải có trạng thái điều kiện được bảo vệ, cập nhật trạng thái trước khi báo và kiểm tra trong `while`.

**Sai: đọc/ghi dữ liệu chung bằng các khóa khác nhau.** Nếu người viết dùng `lockA` nhưng người đọc dùng `lockB`, chúng không bảo đảm loại trừ tương hỗ hoặc happens-before qua hai monitor ấy. Thiết kế một quy ước “trường nào được bảo vệ bởi khóa nào” rồi áp dụng nhất quán, bao gồm cả đọc.

**Sai: giữ khóa trong lúc chạy tác vụ chậm, I/O hoặc gọi code không kiểm soát.** Các luồng khác phải chờ lâu hơn; nếu các luồng lấy nhiều khóa theo thứ tự ngược nhau, còn có nguy cơ deadlock. Thu hẹp vùng tới hạn và cố định thứ tự giành nhiều khóa khi cần.

**Sai: cho rằng monitor tự bảo đảm mọi thứ.** Intrinsic lock không mặc nhiên bảo đảm fairness, phát hiện deadlock, timeout khi giành khóa bằng `synchronized`, hay đánh thức đúng một loại người chờ khi nhiều điều kiện dùng chung wait-set. Với hàng đợi, ứng dụng thực tế thường thuận tiện hơn khi dùng `BlockingQueue`; với nhu cầu khóa có timeout/interruptible acquisition hoặc nhiều condition queue riêng, cân nhắc `ReentrantLock` và `Condition` từ `java.util.concurrent.locks`. Đây là các công cụ bổ sung, không làm thay đổi cơ chế monitor của `Object`.

## 8. Tự kiểm tra hiểu biết

1. Hai biến `a` và `b` cùng trỏ đến một instance: `synchronized(a)` và `synchronized(b)` có tranh chấp cùng khóa không? **Có**, vì khóa gắn với đối tượng, không gắn với tên biến.
2. Hai instance của cùng lớp có mặc nhiên chặn nhau khi gọi `synchronized` instance method? **Không**; mỗi instance có monitor riêng. `static synchronized` lại dùng đối tượng `Class`.
3. Tại sao chỉ dùng `volatile` cho `count` chưa đủ để thực hiện `count++` an toàn? **Vì** visibility không biến thao tác đọc–sửa–ghi nhiều bước thành nguyên tử.
4. Sau `notifyAll()`, luồng đang `wait()` có chạy tiếp ngay không? **Không**; nó còn phải lấy lại monitor và kiểm tra lại điều kiện.
5. Dùng `Thread.sleep()` ở trong `synchronized` có giúp luồng khác giành monitor ấy không? **Không**; `sleep` không nhả khóa.

## Kết luận

Monitor là cơ chế đồng bộ nội tại gắn với **danh tính một đối tượng Java**. `synchronized` dùng monitor ấy để bảo vệ vùng tới hạn và thiết lập quy tắc visibility; `wait`/`notify`/`notifyAll` dùng cùng monitor để phối hợp theo điều kiện. Khi thiết kế code đa luồng, hãy xác định rõ **đối tượng khóa nào được chia sẻ, trạng thái nào do khóa đó bảo vệ, và điều kiện nào phải kiểm tra lại dưới khóa**.
