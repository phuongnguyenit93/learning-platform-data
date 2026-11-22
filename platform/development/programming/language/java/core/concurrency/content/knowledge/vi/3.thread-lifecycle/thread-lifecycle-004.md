# Chuyển trạng thái Thread bởi `sleep()`, `join()` và `wait()` trong Java

## 1. Vì sao cần hiểu chuyển trạng thái?

Khi một ứng dụng Java thực hiện nhiều công việc đồng thời, có lúc một luồng **đang chạy hoặc sẵn sàng chạy**, có lúc luồng phải **chờ thời gian**, **chờ luồng khác kết thúc**, hoặc **chờ một điều kiện của dữ liệu dùng chung**. Ba API dễ gặp là:

- `Thread.sleep(...)`: **luồng đang thực thi** tạm dừng trong khoảng thời gian yêu cầu.
- `someThread.join(...)`: **luồng gọi `join`** chờ **luồng `someThread`** kết thúc, có thể kèm timeout.
- `lock.wait(...)`: **luồng đang giữ monitor của `lock`** tạm nhả monitor đó và chờ được đánh thức, có thể kèm timeout.

Cả ba có thể khiến một thread không tiếp tục chạy ngay, nhưng khác nhau về **ai chờ, chờ điều gì, có nhả monitor hay không, và điều kiện tiếp tục**. Phân biệt chúng giúp tránh khóa dữ liệu không cần thiết, nhầm lẫn vòng đời Thread, treo chương trình và lỗi mất tín hiệu.

Bài học xét concurrency của **Java nói chung**, tập trung vào API chuẩn của `java.lang.Thread` và `java.lang.Object`. Các trường hợp sử dụng framework không thuộc phạm vi bài này.

## 2. Sáu trạng thái quan sát bằng `Thread.State`

API `Thread.getState()` trả về một trong sáu giá trị dưới đây. Đây là **ảnh chụp trạng thái tại một thời điểm**, không phải lịch sử chuyển trạng thái hay cam kết thứ tự thực thi của bộ lập lịch.

| `Thread.State` | Ý nghĩa trong Java | Ví dụ |
| --- | --- | --- |
| `NEW` | Đối tượng Thread đã tạo nhưng chưa `start()` | `new Thread(task)` |
| `RUNNABLE` | Thread đang chạy hoặc sẵn sàng chạy ở mức JVM | Sau `start()`, khi không phải chờ theo các trạng thái khác |
| `BLOCKED` | Đang chờ chiếm monitor nội tại để đi vào `synchronized` (hoặc chiếm lại monitor) | Thread khác đang giữ monitor cần vào |
| `WAITING` | Đang chờ vô thời hạn một hành động của thread khác | `Object.wait()`, `Thread.join()` không timeout |
| `TIMED_WAITING` | Đang chờ với giới hạn thời gian | `Thread.sleep(500)`, `Thread.join(500)`, `Object.wait(500)` |
| `TERMINATED` | Phương thức `run()` đã kết thúc, kể cả kết thúc vì exception không được xử lý | Sau khi worker hoàn tất |

Không có trạng thái `SLEEPING` hay `JOINED` trong enum `Thread.State`. “Ngủ” qua `sleep` thể hiện bằng `TIMED_WAITING`; “đang join” thường là `WAITING` hoặc `TIMED_WAITING` của **luồng gọi `join`**, chứ không phải một trạng thái mới của worker.

Sơ đồ khái niệm (chỉ minh họa các đường thường gặp, không bao phủ mọi chuyển đổi):

```text
                  start()
     NEW -------------------------> RUNNABLE
                                      |
             sleep(duration)          | chờ monitor synchronized
             join(timeout)            +---------------------> BLOCKED
             wait(timeout)            |                           |
                   |                  |       lấy được monitor    |
                   v                  |<--------------------------+
              TIMED_WAITING <---------+
                   |        thời hạn hết / đánh thức / gián đoạn
                   +------------------> RUNNABLE (khi sẵn sàng)
                                      |
             join() / wait()          |   không có timeout
                   |                  |
                   v                  |
                WAITING --------------+
                  kết thúc chờ
                                      |
                                      | run() kết thúc
                                      v
                                  TERMINATED
```

Đường quay lại sau `wait` **có thể phải qua `BLOCKED`** để giành lại monitor trước khi tiếp tục. Sau khi một thread hoàn thành, không thể gọi lại `start()` trên cùng đối tượng. `RUNNABLE` không nhất thiết có nghĩa thread đang chiếm CPU tại thời điểm quan sát; trạng thái thực tế thay đổi rất nhanh.

## 3. `Thread.sleep()`: tạm dừng luồng hiện tại theo thời gian

### 3.1. API và điều kiện tiếp tục

`Thread.sleep(long millis)` và `Thread.sleep(long millis, int nanos)` là **phương thức static**. Chúng tác động tới **luồng hiện tại đang gọi**, không phải một đối tượng Thread được chỉ định. Không nên viết `worker.sleep(100)` để diễn đạt ý định “cho worker ngủ”: Java cho phép gọi static qua biến tham chiếu ở mức cú pháp nhưng thao tác vẫn diễn ra trên **luồng gọi**, gây hiểu lầm. Viết rõ `Thread.sleep(100)`.

Trong thời gian ngủ do `Thread.sleep(500)`, trạng thái thường quan sát được của luồng ngủ là `TIMED_WAITING`. Khi khoảng thời gian chờ hoàn tất, luồng trở thành ứng viên được tiếp tục chạy; **không có bảo đảm nó chạy đúng sau 500 ms**, bởi độ chính xác đồng hồ và lịch trình CPU phụ thuộc JVM/hệ điều hành.

`sleep` không phải công cụ đợi một điều kiện nghiệp vụ trở thành đúng. Sau khoảng thời gian đó, điều kiện bên ngoài có thể vẫn sai. Nếu cần phản ứng với sự kiện hoặc dữ liệu thay đổi, dùng điều phối phù hợp (monitor với `wait/notifyAll`, `BlockingQueue`, latch, condition, future...).

### 3.2. `sleep` **không nhả monitor** đang giữ

Đây là điểm khác biệt then chốt với `Object.wait()`. Một thread đang trong `synchronized(lock)` vẫn **sở hữu monitor của `lock`** nếu gọi `Thread.sleep` bên trong khối. Thread khác muốn vào `synchronized(lock)` có thể chuyển sang `BLOCKED` cho đến khi monitor được nhả.

Ví dụ hoàn chỉnh, tạo tệp `SleepKeepsMonitorDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class SleepKeepsMonitorDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        CountDownLatch entered = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (lock) {
                entered.countDown();
                try {
                    Thread.sleep(150);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                System.out.println("worker: vẫn giữ lock");
            }
        }, "sleep-worker");

        worker.start();
        entered.await();

        synchronized (lock) {
            System.out.println("main: đã lấy lock");
        }
        worker.join();
    }
}
```

Chạy với Java 17 trở lên:

```bash
javac SleepKeepsMonitorDemo.java
java SleepKeepsMonitorDemo
```

Kết quả khi worker không bị interrupt:

```text
worker: vẫn giữ lock
main: đã lấy lock
```

`entered.countDown()` được gọi khi worker đang ở bên trong `synchronized(lock)`. `main` chỉ tiếp tục sau `entered.await()` rồi cố gắng lấy cùng monitor. Trong lúc `worker` ngủ, nó **vẫn giữ lock**, vì vậy main không thể in trước dòng của worker. Nếu đo trạng thái main đúng khi đang chờ chiếm monitor, có thể thấy `BLOCKED`; worker trong khoảng ngủ thường là `TIMED_WAITING`. Không dùng `getState()` để khẳng định sẽ bắt gặp hai trạng thái này tại một thời điểm bất kỳ.

Trong thực tế, tránh ngủ lâu khi giữ monitor chung: việc này có thể làm mọi luồng khác cần monitor phải chờ theo, giảm throughput và tăng latency.

### 3.3. Khi bị ngắt

`Thread.sleep` khai báo `throws InterruptedException`. Nếu thread bị interrupt trước hoặc trong khi ngủ, lời gọi ném `InterruptedException`; khi exception được ném theo cơ chế này, **cờ interrupt đã được xóa**. Mã nhận exception thường truyền tiếp hoặc khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` rồi thoát một cách có kiểm soát. Bắt exception và tiếp tục vòng lặp vô hạn có thể làm yêu cầu hủy không còn tác dụng.

## 4. `Thread.join()`: caller chờ một Thread khác kết thúc

### 4.1. Ai chuyển sang trạng thái chờ?

Cho hai thread: `main` và `worker`. Khi main gọi `worker.join()`:

- **main** là luồng chờ: nó thường vào `WAITING` nếu `join()` không timeout, hoặc `TIMED_WAITING` nếu dùng `join(timeout)`.
- **worker** vẫn tiếp tục vòng đời của riêng nó. Worker có thể `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` hoặc đã `TERMINATED` tùy lúc quan sát; **`join` không làm worker tự ngủ hoặc dừng**.
- Khi worker kết thúc, main có thể tiếp tục sau `join()`. Trong trường hợp `join` có timeout, main cũng có thể tiếp tục vì hết thời gian dù worker vẫn sống.

Đây là lỗi dễ mắc: “`worker.join()` khiến worker chuyển sang `WAITING`” là **sai đối tượng**. Người đợi là thread gọi `join`.

### 4.2. Ví dụ thứ tự hoàn thành xác định

Tạo tệp `JoinOrderDemo.java`:

```java
public class JoinOrderDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            System.out.println("worker: hoàn thành");
        }, "worker");

        worker.start();
        worker.join();

        System.out.println("main: tiếp tục sau join");
    }
}
```

```bash
javac JoinOrderDemo.java
java JoinOrderDemo
```

Kết quả:

```text
worker: hoàn thành
main: tiếp tục sau join
```

`start()` khởi động worker, còn `join()` khiến main đợi worker kết thúc. Vì vậy thứ tự hai dòng được bảo đảm bởi cấu trúc chương trình; nó không phụ thuộc việc main hay worker được CPU chạy trước. Nếu bỏ `join()`, thứ tự hai dòng không còn được bảo đảm.

### 4.3. `join(timeout)` có thể trở về khi worker chưa hoàn thành

`worker.join(200)` yêu cầu chờ **tối đa khoảng 200 ms** để worker kết thúc. Sau khi lời gọi trả về bình thường, cần kiểm tra `worker.isAlive()` nếu nghiệp vụ phải biết worker thực sự đã xong:

```java
worker.join(200);
if (worker.isAlive()) {
    System.out.println("Worker chưa hoàn thành ở thời điểm kiểm tra");
}
```

Đây là đoạn minh họa đặt trong ngữ cảnh đã có biến `worker` và xử lý `InterruptedException`. Dòng thông báo có thể xuất hiện hoặc không, tùy thời gian thực thi. Không được coi việc `join(timeout)` trả về là bằng chứng chắc chắn worker đã `TERMINATED`. Tham số `millis = 0` của `join(0)` có nghĩa là **chờ vô thời hạn**, không phải “không chờ”.

`Thread.join()` có thể bị interrupt khi caller đang chờ. Khi đó **caller** nhận `InterruptedException`; điều này tự nó không hủy hoặc ngắt worker. Nếu muốn yêu cầu worker dừng, cần gửi tín hiệu riêng, ví dụ `worker.interrupt()` với hợp đồng hủy phù hợp.

### 4.4. Quan hệ happens-before

Khi một thread kết thúc, các hành động nó đã thực hiện có quan hệ *happens-before* với hành động của thread khác phát hiện được việc kết thúc đó qua `join()` thành công. Nhờ vậy, mã sau `worker.join()` có thể quan sát các ghi của worker đã kết thúc theo bảo đảm của Java Memory Model.

Tuy nhiên, `join` là cơ chế chờ **kết thúc thread**, không phải cơ chế bảo vệ một cấu trúc dữ liệu khi nhiều thread vẫn đang sửa nó đồng thời. Nếu các thread khác vẫn cập nhật dữ liệu chung, vẫn cần đồng bộ phù hợp.

## 5. `Object.wait()`: nhả monitor và chờ điều kiện

### 5.1. `wait` là phương thức của `Object`, không phải `Thread`

Các overload phổ biến là `lock.wait()`, `lock.wait(long timeout)` và `lock.wait(long timeout, int nanos)`. Mỗi đối tượng Java có monitor nội tại để dùng với `synchronized`, `wait`, `notify`, `notifyAll`.

Muốn gọi `lock.wait()`, **luồng hiện tại phải đang giữ monitor của chính `lock`**, thông thường bằng:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

Đây là đoạn minh họa với `lock` và `ready` đã được khai báo. Nếu gọi `lock.wait()` khi không sở hữu monitor của `lock`, Java ném `IllegalMonitorStateException`. Giữ monitor của một đối tượng **khác** không đáp ứng điều kiện.

Khác `sleep`, khi gọi `lock.wait()` hợp lệ, luồng đang chờ sẽ **nhả monitor của chính `lock`** và chuyển sang chờ. Nhờ đó một luồng khác có thể vào `synchronized(lock)`, thay đổi trạng thái được bảo vệ và gửi thông báo.

### 5.2. `wait`, `notify` và `notifyAll` phối hợp ra sao?

Giả sử consumer cần đợi producer đặt `ready = true`:

1. Consumer vào `synchronized(lock)`, kiểm tra điều kiện `ready`.
2. Nếu chưa sẵn sàng, consumer gọi `lock.wait()`. Nó nhả monitor `lock` và chờ (thường thấy `WAITING`).
3. Producer lấy monitor `lock`, cập nhật `ready = true` rồi gọi `lock.notifyAll()`.
4. `notifyAll()` **không lập tức nhả monitor** của producer và cũng không bảo đảm consumer chạy ngay.
5. Producer rời `synchronized(lock)` để nhả monitor; consumer phải **lấy lại monitor `lock`** trước khi `wait()` trả về. Trong lúc giành lại monitor, consumer có thể `BLOCKED`.
6. Consumer kiểm tra lại `ready` bằng `while` rồi xử lý điều kiện đã thỏa.

Luồng chờ không được bảo đảm chạy ngay khi nhận thông báo: nó còn phải tranh quyền chiếm monitor với các thread khác. `wait()` có thể trở về bởi thông báo, timeout (với overload có thời hạn), ngắt, hoặc **spurious wakeup**. Vì vậy luôn kiểm tra điều kiện trong **vòng `while`**, không dùng một câu `if` duy nhất.

### 5.3. Ví dụ producer–consumer đầy đủ, không bị mất tín hiệu

Tạo tệp `WaitNotifyDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class WaitNotifyDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        boolean[] ready = {false};
        CountDownLatch consumerEntered = new CountDownLatch(1);

        Thread consumer = new Thread(() -> {
            synchronized (lock) {
                while (!ready[0]) {
                    System.out.println("consumer: đang chờ");
                    consumerEntered.countDown();
                    try {
                        lock.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                System.out.println("consumer: đã nhận điều kiện");
            }
        }, "consumer");

        consumer.start();
        consumerEntered.await();

        synchronized (lock) {
            ready[0] = true;
            lock.notifyAll();
            System.out.println("producer: đã phát tín hiệu");
        }

        consumer.join();
        System.out.println("main: hoàn thành");
    }
}
```

```bash
javac WaitNotifyDemo.java
java WaitNotifyDemo
```

Kết quả khi không có interrupt:

```text
consumer: đang chờ
producer: đã phát tín hiệu
consumer: đã nhận điều kiện
main: hoàn thành
```

**Vì sao kết quả xác định?** Consumer in thông báo và gọi `consumerEntered.countDown()` khi đang giữ `lock`. Main đợi latch rồi mới thử lấy `lock`. Consumer phải đi đến `lock.wait()` và nhả monitor trước khi main có thể đặt `ready[0] = true`, vì vậy không có khoảng trống giữa kiểm tra điều kiện và nhả monitor để mất thông báo. Producer in trong lúc giữ monitor nên consumer không thể in “đã nhận điều kiện” trước nó. Cuối cùng, `join()` đặt dòng “main: hoàn thành” sau khi consumer kết thúc.

Biến `ready` được đọc/ghi **chỉ trong `synchronized(lock)`**, tạo quan hệ nhìn thấy dữ liệu qua việc nhả/chiếm monitor; dùng mảng một phần tử ở đây chỉ để có một holder có thể được lambda tham chiếu, không phải cơ chế đồng bộ. Trong ứng dụng thật, nên dùng đối tượng trạng thái có tên rõ ràng.

**Vì sao vẫn dùng `while`?** Java cho phép wakeup không có `notify/notifyAll` tương ứng, hoặc một thread khác có thể làm điều kiện trở lại sai trước lúc consumer lấy monitor. Vòng `while` buộc kiểm tra lại mệnh đề thật sự cần đáp ứng.

### 5.4. `wait(timeout)` và kết quả đánh thức

Trong `synchronized(lock)`, `lock.wait(500)` đặt thời hạn chờ. Thread thường là `TIMED_WAITING` trong lúc đợi, nhưng **trở về không chứng minh điều kiện đã đúng**. Cần kiểm tra điều kiện một lần nữa. `wait(0)` có nghĩa là chờ vô thời hạn.

Tương tự, `notify()` thường đánh thức **một** thread chờ trên monitor đó, nhưng không chọn theo thứ tự bạn mong muốn. `notifyAll()` đánh thức tất cả thread đang chờ trên monitor đó; chúng tiếp tục cạnh tranh để lấy lại monitor và tự kiểm tra điều kiện. Với nhiều loại điều kiện cùng dùng một monitor, `notifyAll()` thường giảm rủi ro đánh thức nhầm thread không thể tiến triển, dù có thể làm nhiều thread thức dậy và tranh chấp hơn. Chọn chiến lược phù hợp với bất biến thực tế.

### 5.5. `wait` chỉ nhả monitor đang được đợi

Nếu một thread đang giữ cả `lockA` và `lockB`, rồi gọi `lockA.wait()`, nó nhả monitor `lockA` nhưng **vẫn giữ `lockB`**. Do đó đặt `wait` trong cấu trúc khóa lồng nhau dễ gây bế tắc nếu producer cần `lockB` để tạo điều kiện đánh thức. `wait` cũng không tự nhả các loại khóa khác như `ReentrantLock`. Khi dùng `ReentrantLock`, hãy dùng `Condition.await/signal` tương ứng thay vì pha trộn với `Object.wait/notify` trên một đối tượng không liên quan.

## 6. So sánh trực tiếp ba API

| Câu hỏi | `Thread.sleep(100)` | `worker.join()` | `lock.wait()` |
| --- | --- | --- | --- |
| API nằm ở đâu? | Phương thức static của `Thread` | Phương thức instance của `Thread` | Phương thức instance của `Object` |
| Ai chờ? | Thread hiện tại | Thread gọi `join` | Thread đang giữ monitor `lock` và gọi `wait` |
| Chờ điều gì? | Khoảng thời gian được yêu cầu | Một thread đích kết thúc; hoặc timeout | Thông báo/interrupt/spurious wakeup; hoặc timeout |
| Trạng thái thường quan sát | `TIMED_WAITING` | `WAITING` hoặc `TIMED_WAITING` | `WAITING` hoặc `TIMED_WAITING` |
| Cần sở hữu monitor? | Không | Không | Có, phải giữ monitor của chính đối tượng gọi `wait` |
| Có nhả monitor đã giữ? | Không | Không tự nhả các monitor caller đang giữ | Có, nhả monitor của đối tượng gọi `wait` |
| Cần kiểm tra điều kiện sau khi trở về? | Nếu nghiệp vụ dựa điều kiện: có | Với timeout: kiểm tra `isAlive()` | Có, dùng `while` cho điều kiện được bảo vệ |
| Khi caller bị interrupt trong lúc chờ? | `InterruptedException` | `InterruptedException` | `InterruptedException` |
| Mục đích chính | Trì hoãn thời gian, mô phỏng chờ khi học | Điều phối kết thúc vòng đời thread | Phối hợp điều kiện giữa các thread qua monitor |

**Đặc biệt với `join`:** đối tượng `worker` là **đích được chờ**, không phải “thread bị đưa vào WAITING”. Trạng thái chờ thuộc về caller. **Đặc biệt với `wait`:** thread nhả monitor của đối tượng chờ, nhưng khi `wait` trả về thì thread đã lấy lại monitor đó. **Đặc biệt với `sleep`:** thread có thể ngủ trong `synchronized` mà vẫn giữ monitor.

## 7. Bị interrupt khi đang `sleep`, `join` hoặc `wait`

Cả ba API đều có thể ném `InterruptedException` khi thread thực hiện lời gọi bị ngắt. Ngắt là **tín hiệu hợp tác**: nó không phải thao tác cưỡng chế dừng JVM thread một cách tức thì. Lời gọi đang chờ có thể ném exception và thông thường xóa trạng thái interrupt trước khi chuyển quyền cho `catch`.

Tạo tệp `SleepInterruptDemo.java` để thấy rõ tác động lên **luồng đang ngủ**:

```java
import java.util.concurrent.CountDownLatch;

public class SleepInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            ready.countDown();
            try {
                Thread.sleep(10_000);
            } catch (InterruptedException e) {
                System.out.println("catch: interrupted=" +
                        Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("restored: interrupted=" +
                        Thread.currentThread().isInterrupted());
            }
        }, "worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();
        System.out.println("main: worker đã kết thúc");
    }
}
```

```bash
javac SleepInterruptDemo.java
java SleepInterruptDemo
```

Kết quả:

```text
catch: interrupted=false
restored: interrupted=true
main: worker đã kết thúc
```

Ngay cả khi main ngắt worker trước khi worker thực sự bước vào `sleep`, `sleep` vẫn phát hiện interrupt và ném exception; vì vậy ví dụ không cần trông cậy vào việc main “canh đúng 10 giây”. `isInterrupted()` trong `catch` là `false` vì cờ đã bị xóa khi `InterruptedException` được ném. Mã khôi phục cờ để tầng gọi có thể nhận biết yêu cầu ngắt.

Đối với `join`, nếu main bị interrupt lúc đang chờ `worker.join()`, **main** mới là thread nhận `InterruptedException`; worker không tự bị interrupt. Đối với `wait`, thread đang đợi monitor nhận `InterruptedException`; trước khi ném exception, Java phải hoàn tất việc lấy lại monitor theo hợp đồng `wait`.

Không nuốt `InterruptedException` rồi tiếp tục chờ vô hạn nếu chức năng cần hỗ trợ hủy. Nếu không thể khai báo `throws InterruptedException`, mẫu xử lý phổ biến là khôi phục cờ ngắt và kết thúc task hoặc chuyển trạng thái hủy lên tầng điều phối. Cũng không gọi `Thread.stop()` để giải quyết một thread đang chờ; đây là API đã lỗi thời và không an toàn.

## 8. Trạng thái nào xuất hiện sau khi được đánh thức?

Không thể áp dụng máy móc quy tắc “`wait` xong là `RUNNABLE` ngay”:

- `sleep`: hết thời gian hoặc bị interrupt, thread có thể sẵn sàng chạy trở lại; các monitor mà nó đang giữ vẫn được giữ cho đến lúc rời khối `synchronized`.
- `join`: worker kết thúc hoặc khoảng chờ hết hạn, caller được phép tiếp tục; caller vẫn phải được lên lịch CPU.
- `wait`: sau `notify/notifyAll`, hết thời hạn, spurious wakeup hoặc interrupt, thread còn phải **giành lại monitor của đối tượng `wait`**. Nếu monitor đang do người khác giữ, nó có thể được quan sát ở `BLOCKED` trước khi quay lại thực thi.
- Nếu không được báo thức, không hết thời gian, không bị interrupt và không có spurious wakeup, `wait()` vô thời hạn có thể tiếp tục chờ mãi. Đây là lý do chương trình cần đảm bảo một đường thay đổi điều kiện và báo thức rõ ràng.

`Thread.getState()` là công cụ chẩn đoán. Ví dụ, `System.out.println(worker.getState())` có thể giúp quan sát, nhưng kết quả là một snapshot và có thể thay đổi ngay sau đó. **Không sử dụng vòng lặp canh `getState() == WAITING` để thay thế giao thức điều phối đúng**. Khi cần kiểm chứng trình tự, dùng latch, monitor hoặc `Future` như trong các ví dụ thay vì phụ thuộc lịch biểu CPU.

## 9. Lỗi phổ biến và nguyên nhân

### 9.1. Nhầm đối tượng chờ khi gọi `join`

**Nhận định sai:** “Gọi `worker.join()` làm worker ngủ.”

**Đúng:** caller của `worker.join()` chờ worker hoàn thành; worker vẫn chạy bình thường. Nếu worker lại chờ caller bằng một cơ chế khác, có thể tạo vòng chờ (deadlock). Hãy vẽ quan hệ ai chờ ai trước khi thêm lời gọi `join`.

### 9.2. Ngủ khi giữ monitor để đợi thread khác thay đổi dữ liệu

```java
synchronized (lock) {
    while (!ready) {
        Thread.sleep(100);
    }
}
```

Đoạn mã minh họa trên có lỗi thiết kế: nếu luồng producer cũng cần `synchronized(lock)` để đổi `ready`, consumer vẫn giữ lock trong các lần `sleep` và kiểm tra nên producer không thể vào để làm điều kiện đúng. **Sửa bằng `lock.wait()` trong vòng `while`** để nhả monitor lúc đợi, hoặc dùng cơ chế đồng bộ cấp cao phù hợp.

### 9.3. Gọi `wait()` ở ngoài `synchronized`

```java
lock.wait(); // IllegalMonitorStateException nếu caller không giữ monitor của lock
```

Phải gọi bên trong `synchronized(lock)` (hoặc khi thực sự sở hữu monitor đó). Việc khai báo biến `lock` là `final` không làm thread sở hữu monitor.

### 9.4. Dùng `if` thay `while` để đợi điều kiện

```java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    useReadyData();
}
```

Đây là đoạn minh họa có rủi ro. `wait` có thể trở về mà điều kiện vẫn sai; cần thay `if` bằng `while` và giữ việc kiểm tra điều kiện cùng dữ liệu dùng chung trong vùng được bảo vệ. `useReadyData()` là công việc do ứng dụng định nghĩa.

### 9.5. Gọi `notify` quá sớm hoặc không giữ cùng monitor

Nếu producer gọi `notifyAll` trên một đối tượng khác với đối tượng consumer chờ, consumer không được đánh thức. Nếu không lưu điều kiện trong dữ liệu và báo hiệu trước khi consumer bắt đầu đợi, thông báo có thể bị mất. Giao thức “kiểm tra điều kiện + `wait`” dưới **cùng monitor**, và producer “đổi điều kiện + `notifyAll`” dưới **cùng monitor**, giúp tránh lỗ hổng này.

### 9.6. Quên rằng timeout không đồng nghĩa với hoàn thành

`worker.join(100)` có thể trả về dù worker chưa kết thúc. `lock.wait(100)` có thể trả về dù producer chưa báo hiệu. `Thread.sleep(100)` chỉ làm thread đợi khoảng thời gian, không đảm bảo một sự kiện cụ thể đã xảy ra. Sau timeout, hãy kiểm tra mệnh đề thực sự cần thiết, không mặc định điều kiện đã đúng.

### 9.7. Quên vòng đời và khả năng bị ngắt

Không xử lý `InterruptedException` có thể làm ứng dụng hủy task không sạch hoặc chờ không dứt. Với `join` trên thread không bao giờ kết thúc, caller có thể bị chặn mãi. Với `wait`, nếu không còn luồng nào có thể thay đổi điều kiện và đánh thức, có nguy cơ treo nghiệp vụ. Cần thiết kế đường thoát, timeout và cleanup phù hợp.

## 10. Thực tế nên dùng API nào?

**`sleep`** phù hợp khi bài toán thật sự cần trì hoãn thời gian hoặc mô phỏng tác vụ chờ trong môi trường học tập. Không dùng nó làm cách “đồng bộ đại khái” giữa các thread.

**`join`** phù hợp khi một thread quản lý cần chắc chắn rằng một thread khác đã kết thúc, chẳng hạn đóng một worker trước khi kết thúc chương trình. Nếu task do `ExecutorService` quản lý và cần kết quả hoặc lỗi, `Future.get()` thường diễn đạt ý định tốt hơn.

**`wait/notifyAll`** thích hợp để hiểu cơ chế monitor nguyên thủy và khi bạn thật sự cần tự quản lý một điều kiện được bảo vệ bởi `synchronized`. Trong mã ứng dụng thực tế, các cấu trúc như `BlockingQueue`, `CountDownLatch`, `Semaphore`, `Condition` hay `CompletableFuture` thường giúp diễn đạt mục đích rõ và giảm lỗi giao thức. Chúng có cơ chế chờ riêng, không nên gọi chéo `Object.wait` trên một đối tượng tùy ý rồi cho rằng sẽ nhận tín hiệu từ các cấu trúc đó.

Với **virtual thread** (Java 21+), các phương thức `sleep` và `join` vẫn có ý nghĩa đợi tương ứng, và các trạng thái `Thread.State` vẫn là trạng thái của thread Java. Cơ chế JVM có thể tháo virtual thread khỏi carrier trong nhiều tình huống chờ để tiết kiệm OS thread; điều đó **không thay đổi quy tắc monitor**: `sleep` không nhả monitor, `wait` phải giữ rồi nhả monitor của đối tượng, `notifyAll` không nhả monitor ngay. Trong Java 21, thao tác chặn khi đang ở vùng `synchronized` có thể gây pinning carrier; các phiên bản Java mới có cải tiến, nhưng cần đo trên JDK và thư viện thực tế. Đừng dùng virtual thread để thay thế quy tắc đồng bộ dữ liệu.

## 11. Tự kiểm tra

**Câu 1.** Main gọi `Thread.sleep(300)` khi đang trong `synchronized(lock)`, và một worker khác cố vào `synchronized(lock)`. Hai thread có thể ở trạng thái gì?

**Trả lời:** Main thường `TIMED_WAITING` do `sleep` nhưng vẫn giữ monitor của `lock`. Worker có thể `BLOCKED` vì chờ monitor. Trạng thái quan sát là snapshot và tùy thời điểm.

**Câu 2.** Main gọi `worker.join()` trong khi worker đang chạy. Thread nào đang chờ và điều gì xảy ra khi worker kết thúc?

**Trả lời:** Main là caller nên thường `WAITING`; worker tiếp tục công việc. Khi worker kết thúc, main có thể tiếp tục sau `join()`.

**Câu 3.** Consumer gọi `lock.wait()` trong `synchronized(lock)`. Tại sao producer có thể thay đổi dữ liệu và gọi `notifyAll()` trên cùng lock?

**Trả lời:** `wait` nhả monitor của `lock`, cho producer cơ hội chiếm nó. Producer cập nhật dữ liệu và phát tín hiệu; consumer phải chiếm lại monitor trước khi trở về từ `wait`, rồi kiểm tra điều kiện bằng `while`.

**Câu 4.** `lock.wait(100)` trả về bình thường. Có thể khẳng định producer đã báo thức và điều kiện đã đúng chưa?

**Trả lời:** Không. Có thể hết thời gian, thông báo hoặc spurious wakeup; cần kiểm tra lại điều kiện.

**Câu 5.** `worker.join(100)` trả về, worker chắc chắn `TERMINATED` chưa?

**Trả lời:** Chưa. `join(timeout)` có thể hết thời hạn. Kiểm tra `worker.isAlive()` để biết worker còn sống ở thời điểm kiểm tra.

**Câu 6.** Vì sao `Thread.sleep` không giúp tránh mất thông báo như mô hình `while (!ready) lock.wait()`?

**Trả lời:** `sleep` không gắn kiểm tra điều kiện với việc nhả monitor, cũng không được `notify` đánh thức như protocol monitor. Nếu ngủ trong `synchronized`, thread còn giữ monitor làm producer không thể cập nhật điều kiện.

## 12. Kết luận

Ba lời gọi cùng có thể khiến luồng tạm dừng nhưng phục vụ **ba nhu cầu khác nhau**:

- `sleep(duration)`: **luồng hiện tại chờ thời gian**, thường `TIMED_WAITING`, không nhả monitor đang giữ.
- `other.join()`: **luồng gọi chờ `other` kết thúc**, thường `WAITING` hoặc `TIMED_WAITING`, không làm `other` chuyển sang trạng thái chờ.
- `lock.wait()`: **luồng đang sở hữu monitor `lock` nhả chính monitor đó và chờ điều kiện được đánh thức**, thường `WAITING`; sau khi được đánh thức còn phải lấy lại monitor và kiểm tra điều kiện.

Nắm được **ai chờ, chờ cái gì, monitor nào được nhả và điều kiện nào cho phép tiếp tục** là nền tảng để đọc đúng vòng đời Thread và thiết kế chương trình concurrency an toàn trong Java.
