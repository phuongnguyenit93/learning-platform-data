# Các trạng thái NEW, RUNNABLE và TERMINATED trong vòng đời Thread

Trong Java, `Thread` biểu diễn một luồng thực thi. Luồng trải qua các trạng thái vòng đời từ lúc được tạo, bắt đầu thực thi cho đến khi kết thúc. `Thread.State` là enum mô tả trạng thái **quan sát được** của một luồng tại một thời điểm. Bài này tập trung vào ba trạng thái quan trọng:

- **`NEW`**: đối tượng `Thread` đã được tạo nhưng luồng chưa được khởi động bởi `start()`.
- **`RUNNABLE`**: luồng đã khởi động, có thể đang chạy trong JVM **hoặc sẵn sàng để được lập lịch chạy**. Đây không đồng nghĩa đang chiếm CPU ở đúng thời điểm kiểm tra.
- **`TERMINATED`**: luồng đã hoàn tất thực thi, dù kết thúc bình thường hay do ngoại lệ/lỗi chưa được xử lý thoát khỏi `run()`.

Ba trạng thái này giúp hiểu vì sao `new Thread(...)` chưa chạy tác vụ, `start()` khác `run()`, và vì sao một `Thread` đã `TERMINATED` không thể khởi động lại.

## 1. Đối tượng Thread và luồng thực thi không phải một

Việc xây dựng `new Thread(runnable)` tạo đối tượng Java lưu các thông tin cần cho một luồng, **chưa bắt đầu chạy tác vụ trên luồng mới**. Đối tượng ban đầu có trạng thái `NEW`.

```java
Thread worker = new Thread(() -> {
    System.out.println("Worker started");
}, "my-worker");

// worker.getState() == Thread.State.NEW
worker.start();
```

Đây là trích đoạn minh họa cần đặt trong phương thức hoặc lớp hợp lệ, chưa phải chương trình độc lập. Lời gọi `start()` yêu cầu JVM bắt đầu thực thi `run()` trên luồng mới. Thời điểm CPU thực sự chạy tác vụ được bộ lập lịch quyết định; `start()` không có nghĩa tác vụ đã hoàn thành.

Nếu gọi trực tiếp `worker.run()`, Java thực hiện phương thức đó **ngay trên luồng gọi** (ví dụ `main`) thay vì khởi tạo luồng mới. Nếu trước đó chưa `start()`, đối tượng `worker` vẫn ở `NEW` sau khi gọi `run()` trực tiếp.

## 2. Bảng ý nghĩa và chuyển trạng thái

| Trạng thái | Điều kiện | `isAlive()` khi quan sát ổn định | Điều gì xảy ra tiếp theo? |
|---|---|---|---|
| `NEW` | Tạo đối tượng, chưa `start()`. | `false` | `start()` thành công → `RUNNABLE`. |
| `RUNNABLE` | Đủ điều kiện chạy hoặc đang thực thi trong JVM. | `true` | Có thể tiếp tục RUNNABLE, đi qua các trạng thái chờ, rồi TERMINATED. |
| `TERMINATED` | `run()` đã kết thúc. | `false` | Trạng thái cuối; không thể `start()` lại. |

Java 17 định nghĩa **sáu** giá trị của enum `Thread.State`: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`. Ba trạng thái còn lại xuất hiện khi luồng còn sống nhưng đang chờ khóa hoặc chờ điều kiện/thời hạn. Chúng là ngữ cảnh để hiểu vòng đời, không phải trọng tâm của bài.

### NEW: chưa có hoạt động thực thi của luồng mới

Đối tượng ở `NEW` có thể được cấu hình (đặt tên, gắn uncaught exception handler, và với platform thread có thể đặt chế độ daemon) trước `start()`. Nếu không bao giờ gọi `start()`, tác vụ không tự động chạy. `run()` được gọi như phương thức thông thường không chuyển `Thread` sang RUNNABLE.

### RUNNABLE: sẵn sàng hoặc đang chạy

Tên `RUNNABLE` dễ gây hiểu nhầm. **`Thread.State` không có trạng thái `RUNNING` riêng.** JVM gộp việc “đang chạy” và “sẵn sàng chạy” vào RUNNABLE; thread đang tranh CPU có thể vẫn báo RUNNABLE dù chưa được hệ điều hành cấp CPU ngay lúc quan sát.

Đừng dùng `getState() == RUNNABLE` để kết luận thread đang xử lý hữu ích hay dùng bao nhiêu CPU. Trạng thái này cũng không đưa ra cam kết thứ tự thực thi giữa các luồng.

### TERMINATED: đã kết thúc

`TERMINATED` xuất hiện khi phương thức `run()` đã hoàn tất:

- Chạy hết thân phương thức hoặc `return` bình thường.
- Một ngoại lệ/lỗi chưa được xử lý khiến luồng kết thúc.

Không thể “reset” về NEW hoặc RUNNABLE. Gọi lại `start()` trên một thread đã bắt đầu, kể cả đã `TERMINATED`, gây `IllegalThreadStateException`. Muốn thực hiện tác vụ mới, hãy tạo đối tượng `Thread` mới hoặc giao việc cho cơ chế thực thi được quản lý.

## 3. Sơ đồ vòng đời

```text
new Thread(task)
      |
      v
     NEW
      |
      | start() thành công, chỉ một lần
      v
   RUNNABLE <------> BLOCKED / WAITING / TIMED_WAITING
      |                (khi luồng tạm chờ)
      |
      | run() trở về hoặc kết thúc bởi lỗi chưa xử lý
      v
  TERMINATED
      |
      +-- start() lần nữa: IllegalThreadStateException
```

Một thread có thể từ RUNNABLE chuyển sang `BLOCKED` khi chờ monitor `synchronized`, `WAITING` khi chờ điều kiện không thời hạn (ví dụ `CountDownLatch.await()`), hoặc `TIMED_WAITING` khi `Thread.sleep(...)`. Khi hết chờ, nó có thể quay về RUNNABLE rồi tiếp tục công việc. Không phải luồng nào cũng trải qua mọi trạng thái; một tác vụ ngắn có thể đi từ NEW qua RUNNABLE tới TERMINATED rất nhanh.

Không có API an toàn để đặt trạng thái theo ý muốn như `setState(TERMINATED)`. Muốn dừng, cần phối hợp để `run()` tự trả về (tín hiệu dừng, interrupt được xử lý đúng, hoặc hủy tác vụ có kiểm soát). `Thread.stop()` đã lỗi thời và không an toàn.

## 4. Ví dụ 1: thấy rõ NEW → RUNNABLE → TERMINATED

Để quan sát trạng thái, cần ngăn worker kết thúc quá nhanh trước khi `main` kịp kiểm tra. Ví dụ sau dùng `CountDownLatch` làm tín hiệu đã bắt đầu và `AtomicBoolean` làm tín hiệu dừng. Worker tạm chạy vòng lặp chủ động, vì vậy không phải đợi bằng `sleep()` với thời gian ước đoán.

Tạo file **`ThreadStateLifecycle.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class ThreadStateLifecycle {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean stop = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            started.countDown();
            while (!stop.get()) {
                Thread.onSpinWait();
            }
        }, "lifecycle-worker");

        System.out.println("Before start: "
                + worker.getState() + ", alive=" + worker.isAlive());

        worker.start();
        started.await();

        System.out.println("While worker is spinning: "
                + worker.getState() + ", alive=" + worker.isAlive());

        stop.set(true);
        worker.join();

        System.out.println("After join: "
                + worker.getState() + ", alive=" + worker.isAlive());
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac ThreadStateLifecycle.java
java ThreadStateLifecycle
```

Kết quả dự kiến trong lần chạy bình thường:

```text
Before start: NEW, alive=false
While worker is spinning: RUNNABLE, alive=true
After join: TERMINATED, alive=false
```

**Giải thích theo thứ tự:**

1. `new Thread(...)` tạo đối tượng nhưng chưa thực thi: `NEW`, `isAlive() == false`.
2. `worker.start()` bắt đầu luồng. Worker phát tín hiệu `started.countDown()` và tiếp tục quay trong `while (!stop.get())`. `started.await()` giúp `main` chỉ kiểm tra sau khi worker báo bắt đầu.
3. Worker không chờ monitor, ngủ hay đợi latch ở trong vòng lặp, nên khi chưa nhận tín hiệu dừng, trạng thái quan sát là RUNNABLE. Có thể nó đang chiếm CPU hoặc đang được chờ cấp CPU.
4. `stop.set(true)` phát tín hiệu với bảo đảm hiển thị bộ nhớ của `AtomicBoolean`. Worker thoát vòng lặp và kết thúc `run()`.
5. `worker.join()` đợi việc kết thúc hoàn tất. Sau khi `join()` trả về bình thường, `getState()` là `TERMINATED`, `isAlive()` là `false`.

**Chú ý:** vòng lặp dùng `Thread.onSpinWait()` là cách cố ý tạo RUNNABLE để học, có thể tiêu tốn CPU. Không sử dụng vòng lặp chờ bận không giới hạn trong chương trình thực tế. Nếu thay bằng `Thread.sleep()` hoặc `await()`, trạng thái có thể là `TIMED_WAITING` hoặc `WAITING` và kết quả kiểm tra sẽ khác.

## 5. Ví dụ 2: gọi run() không thay thế start()

Ví dụ này chỉ dùng một `Thread`, nhưng chạy nội dung `Runnable` hai cách khác nhau để thấy sự khác biệt.

Tạo file **`StartVersusRun.java`**:

```java
public class StartVersusRun {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            System.out.println("Current thread: "
                    + Thread.currentThread().getName());
        }, "demo-worker");

        System.out.println("Initial state: " + worker.getState());

        worker.run();
        System.out.println("After direct run(): " + worker.getState());

        worker.start();
        worker.join();
        System.out.println("After start() and join(): " + worker.getState());

        try {
            worker.start();
        } catch (IllegalThreadStateException e) {
            System.out.println("Restart rejected: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

```bash
javac StartVersusRun.java
java StartVersusRun
```

Đầu ra khi luồng khởi chạy thông thường có tên `main`:

```text
Initial state: NEW
Current thread: main
After direct run(): NEW
Current thread: demo-worker
After start() and join(): TERMINATED
Restart rejected: IllegalThreadStateException
```

Lần gọi `worker.run()` đầu tiên chỉ thực thi `Runnable` trên luồng `main`, nên `worker` vẫn NEW. Lần gọi `worker.start()` mới thực sự bắt đầu `demo-worker`. `join()` giúp dòng kiểm tra cuối được chạy khi worker đã xong. Cố gắng `start()` lần hai bị từ chối vì một đối tượng `Thread` chỉ có một vòng đời thực thi.

## 6. Ví dụ 3: ngoại lệ cũng dẫn đến TERMINATED

`TERMINATED` không có nghĩa tác vụ đã thành công; nó chỉ nói **luồng đã kết thúc**. Đoạn sau chủ động ném ngoại lệ, ghi nhận qua `UncaughtExceptionHandler`, rồi chờ hoàn tất bằng `join()`.

Tạo file **`FailedThreadLifecycle.java`**:

```java
public class FailedThreadLifecycle {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            throw new IllegalStateException("intentional");
        }, "failing-worker");

        worker.setUncaughtExceptionHandler((thread, error) -> {
            System.out.println(thread.getName()
                    + " failed: " + error.getMessage());
        });

        System.out.println("Before start: " + worker.getState());
        worker.start();
        worker.join();
        System.out.println("After failure: " + worker.getState());
    }
}
```

```bash
javac FailedThreadLifecycle.java
java FailedThreadLifecycle
```

Kết quả:

```text
Before start: NEW
failing-worker failed: intentional
After failure: TERMINATED
```

Handler ghi lại nguyên nhân; nó không làm thread trở lại RUNNABLE hay tự động chạy lại công việc. Trong ứng dụng thực tế, cần ghi nhận kết quả/lỗi riêng và quyết định có thử lại bằng **một tác vụ hoặc Thread mới** hay không.

## 7. getState(), isAlive() và join(): dùng đúng mục đích

### getState() là ảnh chụp, không phải khóa đồng bộ

`thread.getState()` trả về trạng thái tại thời điểm gọi. Đến lệnh kế tiếp trạng thái đã có thể khác. Ví dụ, một worker chạy rất nhanh có thể đã `TERMINATED` ngay sau `start()`, dù bạn vừa dự đoán nó RUNNABLE. Đây là lý do không nên viết logic kiểu:

```java
// Trích đoạn minh họa; worker được giả định đã khai báo.
while (worker.getState() != Thread.State.TERMINATED) {
    // Thăm dò liên tục: tốn CPU, không phải chiến lược đợi tốt.
}
```

Dùng `getState()` để ghi log hoặc hỗ trợ điều tra, không dùng làm cơ chế phối hợp luồng. Với nhu cầu chờ kết thúc, `join()` phù hợp hơn.

### isAlive() không có nghĩa là đang RUNNABLE

`isAlive()` cho biết thread **đã bắt đầu và chưa kết thúc**. Ở thời điểm ổn định, NEW và TERMINATED cho `false`; RUNNABLE cho `true`. Tuy nhiên, `isAlive() == true` không có nghĩa trạng thái là RUNNABLE: thread đang `WAITING`, `TIMED_WAITING` hay `BLOCKED` cũng còn sống.

`isAlive()` và `getState()` là hai phép đọc độc lập; nếu trạng thái chuyển giữa hai lần gọi, hai giá trị lấy được không nhất thiết là cùng một ảnh chụp nguyên tử. Ví dụ 1 chủ động giữ worker chưa kết thúc để phép quan sát dễ hiểu.

### join() là điểm đợi hoàn thành

`worker.join()` khiến **luồng gọi** chờ đến khi worker kết thúc, trừ trường hợp việc đợi bị interrupt. Nó hoạt động với cả daemon và user thread. `join()` có ý nghĩa về đồng bộ hóa: Java Memory Model bảo đảm các hành động của worker trước khi kết thúc *happens-before* với các hành động sau khi luồng khác phát hiện việc kết thúc qua `join()`. Tương tự, hành động trước `Thread.start()` trên luồng khởi tạo có quan hệ *happens-before* với các hành động trong thread mới.

Do đó, khi cần xử lý kết quả sau tác vụ, hãy dùng cơ chế hoàn thành/đồng bộ phù hợp (`join()`, `Future`, `CountDownLatch`…), tránh dựa vào việc thăm dò trạng thái và hy vọng dữ liệu đã sẵn sàng.

## 8. Những lỗi thiết kế thường gặp

| Hiểu sai hoặc thao tác sai | Hậu quả | Cách làm tốt hơn |
|---|---|---|
| `new Thread(task)` đã bắt đầu chạy | `task` chưa được thực thi, vẫn NEW. | Gọi `start()` khi thực sự muốn khởi chạy. |
| `thread.run()` tương đương `thread.start()` | Tác vụ chạy trên luồng gọi, không tạo concurrency. | Gọi `start()` đúng một lần. |
| RUNNABLE có nghĩa đang chiếm CPU | Đoán sai hiệu năng và nguyên nhân tắc nghẽn. | Quan sát CPU bằng profiler/thread dump theo thời gian. |
| Ngay sau `start()` nhất định thấy RUNNABLE | Task có thể chạy xong hoặc chuyển sang WAITING rất nhanh. | Dùng tín hiệu đồng bộ nếu muốn tạo thí nghiệm ổn định. |
| `TERMINATED` là một thread có thể dùng lại | `start()` lần nữa ném `IllegalThreadStateException`. | Tạo Thread mới cho lần chạy khác. |
| TERMINATED nghĩa là kết quả thành công | Ngoại lệ chưa xử lý cũng kết thúc thread. | Quản lý lỗi/kết quả riêng khỏi trạng thái. |
| `getState()` là công cụ chờ task | Race condition, vòng đợi bận và mã khó bảo trì. | Dùng `join()` hoặc công cụ đồng bộ thích hợp. |
| `isAlive()` có nghĩa worker đang RUNNABLE | Worker có thể đang bị BLOCKED/WAITING. | Kiểm tra mục đích quan sát và hiểu sáu trạng thái enum. |

**Không nhầm với daemon/user thread:** `isDaemon()` cho biết một thuộc tính khác về việc luồng có giữ JVM sống khi JVM kết thúc thông thường hay không. Daemon thread và user thread đều có thể có trạng thái NEW, RUNNABLE, TERMINATED; chế độ daemon **không** nằm trong enum `Thread.State`.

Nếu cần chẩn đoán, có thể đọc trạng thái bằng `getState()`, đặt tên thread dễ nhận diện, và dùng thread dump (chẳng hạn `jcmd <pid> Thread.print` trên JDK thích hợp). Một lần đo không đủ chứng minh deadlock, tiêu thụ CPU hay độ tiến triển; cần quan sát diễn biến và các mối quan hệ khóa/tín hiệu.

## 9. Tự kiểm tra

1. **Tạo `new Thread(...)` nhưng không gọi `start()` thì trạng thái là gì?** NEW.
2. **Gọi trực tiếp `run()` có làm đối tượng NEW chuyển thành RUNNABLE không?** Không; đó chỉ là lời gọi phương thức trên luồng hiện tại.
3. **Vì sao Java không có `Thread.State.RUNNING`?** JVM dùng RUNNABLE cho cả đã sẵn sàng và đang thực thi theo mô hình trạng thái của nó.
4. **Một thread đang `WAITING` có `isAlive() == true` không?** Có, nếu đã bắt đầu và chưa kết thúc.
5. **Sau `worker.join()` hoàn tất bình thường, trạng thái worker là gì?** TERMINATED.
6. **Một ngoại lệ chưa xử lý có thể đưa thread đến TERMINATED không?** Có; TERMINATED chỉ nói thread đã kết thúc, không xác nhận thành công.
7. **Vì sao không dùng vòng lặp kiểm tra `getState()` để đợi kết quả?** Vì trạng thái là ảnh chụp thay đổi liên tục, thăm dò dễ tốn CPU và không thay thế cơ chế đồng bộ.
8. **Gọi lại `start()` trên thread đã TERMINATED được không?** Không; tạo Thread mới.

**Ghi nhớ:** `NEW` = chưa bắt đầu; `RUNNABLE` = đang hoặc sẵn sàng chạy; `TERMINATED` = đã kết thúc và không thể khởi động lại cùng đối tượng. Dùng `start()` để khởi chạy, `join()` để chờ, `getState()` chủ yếu để quan sát.
