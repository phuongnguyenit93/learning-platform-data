# BlockingQueue: put, take và thao tác có thời hạn chờ

## 1. Hàng đợi còn là nơi phối hợp giữa các luồng

Một luồng tạo công việc, một luồng khác xử lý công việc. Nếu dùng một hàng đợi thông thường, bên xử lý phải biết làm gì khi chưa có phần tử; bên tạo phải biết làm gì khi không còn chỗ. Tự viết vòng lặp kiểm tra, ngủ rồi kiểm tra lại khiến chương trình vừa khó dừng vừa dễ dùng CPU không cần thiết.

`BlockingQueue<E>` bổ sung các thao tác có khả năng chờ điều kiện phù hợp. Bên tạo dữ liệu được gọi là bên sản xuất (producer); bên lấy dữ liệu để xử lý là bên tiêu thụ (consumer).

Với hàng đợi có giới hạn dung lượng, mô hình cơ bản là:

```text
Bên sản xuất
    → đưa công việc vào hàng đợi
        → bên tiêu thụ lấy công việc ra
            → xử lý công việc

Khi hết chỗ: bên đưa vào có thể chờ hoặc từ bỏ.
Khi chưa có phần tử để lấy: bên lấy ra có thể chờ hoặc từ bỏ.
```

Cần phân biệt **chờ để đưa/lấy dữ liệu** với **chờ công việc được xử lý xong**. Một lời gọi đưa vào thành công chưa nói công việc đã được xử lý. Một lời gọi lấy ra thành công cũng chưa nói việc xử lý sau đó sẽ thành công.

Bài này tập trung vào `put`, `take`, `offer` và `poll` có thời hạn chờ, cùng gián đoạn, dung lượng và điều kiện dừng. Các ví dụ dùng `ArrayBlockingQueue` để có dung lượng cố định và thứ tự FIFO rõ ràng.

`BlockingQueue` là giao diện; không suy ra mọi lớp triển khai đều lấy phần tử theo FIFO hoặc đều có một vùng lưu trữ với cùng cách hoạt động. Ví dụ dùng hàng đợi theo ưu tiên hoặc theo thời gian sẵn sàng sẽ có quy tắc chọn phần tử khác.

Các chương trình dưới đây độc lập, dùng Java 17 trở lên và không cần thư viện ngoài. Lưu đúng tên tệp, biên dịch và chạy trong thư mục chứa tệp. Kết quả nhiều luồng được thu lại trước khi in để không phụ thuộc vào thứ tự in giữa các luồng.

## 2. Chọn cách phản ứng khi thao tác chưa thực hiện được

Một nhóm phương thức cho phép chọn chính sách ngay tại điểm gọi:

| Nhu cầu | Báo bằng ngoại lệ nếu chưa làm được | Trả giá trị đặc biệt | Chờ không có timeout do bên gọi đặt | Chờ có timeout |
|---|---|---|---|---|
| Thêm phần tử | `add(e)` | `offer(e)` | `put(e)` | `offer(e, timeout, unit)` |
| Lấy và xóa đầu hàng đợi | `remove()` | `poll()` | `take()` | `poll(timeout, unit)` |
| Chỉ xem đầu hàng đợi | `element()` | `peek()` | Không có dạng tương ứng | Không có dạng tương ứng |

Khi không còn chỗ, `offer` trả `false`; khi không có phần tử để lấy, `poll` trả `null`. Dạng có timeout dùng cùng các giá trị đó nếu không thực hiện được trong thời gian chờ. `put` không trả một cờ thành công; `take` trả phần tử lấy được. Xem [bảng phương thức của BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

### 2.1. Giá trị đặc biệt khác lỗi đầu vào

`false` không có nghĩa mọi lỗi của `offer` đều được chuyển thành `false`. Ví dụ, đưa `null` vào `BlockingQueue` gây `NullPointerException`. Các lỗi về kiểu hoặc thuộc tính phần tử còn phụ thuộc quy định của lớp triển khai.

Việc không cho phép phần tử `null` giúp phân biệt kết quả `poll` không có dữ liệu với một dữ liệu thật. Không dùng `null` làm thông điệp kết thúc đặt trong hàng đợi.

Cũng cần đọc đúng overload: `remove()` lấy đầu hàng đợi và có thể ném lỗi khi rỗng; `remove(Object)` tìm và xóa một phần tử phù hợp. Chúng không có cùng mục đích.

### 2.2. Chương trình với thao tác không chờ điều kiện

Tệp `QueueMethodFormsDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueueMethodFormsDemo {
    public static void main(String[] args) {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        System.out.println("offerA=" + queue.offer("A"));
        System.out.println("offerB=" + queue.offer("B"));
        System.out.println("peek=" + queue.peek());

        try {
            queue.add("B");
        } catch (IllegalStateException ex) {
            System.out.println("fullAdd=" + ex.getClass().getSimpleName());
        }
        System.out.println("remove=" + queue.remove());
        System.out.println("emptyPoll=" + queue.poll());
        try {
            queue.element();
        } catch (java.util.NoSuchElementException ex) {
            System.out.println("emptyElement=" + ex.getClass().getSimpleName());
        }
        try {
            queue.offer(null);
        } catch (NullPointerException ex) {
            System.out.println("nullOffer=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 QueueMethodFormsDemo.java
java QueueMethodFormsDemo
```

Stdout:

```text
offerA=true
offerB=false
peek=A
fullAdd=IllegalStateException
remove=A
emptyPoll=null
emptyElement=NoSuchElementException
nullOffer=NullPointerException
```

Dung lượng chỉ là 1. A được thêm thành công, B chưa thể thêm nên `offer` trả `false`. `peek` chỉ xem A; vì A vẫn còn nên `add("B")` ném `IllegalStateException`.

Sau khi `remove()` lấy A, `poll()` trả `null` vì rỗng. `element()` trên hàng đợi rỗng ném `NoSuchElementException`. Lần đưa `null` bị từ chối bằng ngoại lệ riêng.

Các kết quả này được tạo trong một luồng, không có tranh chấp. Chúng giúp nhận ra chính sách của từng phương thức trước khi thêm phần chờ giữa các luồng.

“Không chờ” ở đây nghĩa là không đợi hàng đợi có chỗ hoặc có phần tử. Đừng suy ra một lời gọi không có timeout luôn là thuật toán không khóa hoặc không thể mất thời gian do phối hợp nội bộ.

## 3. put và take: chờ điều kiện thay đổi

### 3.1. put chờ chỗ, take chờ phần tử

Với `ArrayBlockingQueue`, dung lượng được ấn định khi tạo và phần tử được lấy theo FIFO. Nếu đầy, `put(e)` chờ có chỗ để thêm; nếu rỗng, `take()` chờ có phần tử để lấy. Nếu điều kiện đã phù hợp, chúng có thể hoàn thành mà không cần chờ một luồng khác. Xem [ArrayBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

Đừng hiểu “blocking” là chương trình tự tạo thêm luồng. Chính luồng đang gọi phương thức có thể phải chờ. Nếu luồng đó đang phục vụ một yêu cầu, khả năng phục vụ của nó cũng bị giữ trong thời gian chờ.

Một lần `take` thành công loại phần tử khỏi hàng đợi. Hai bên tiêu thụ không cùng nhận một lần lấy của cùng phần tử còn nằm trong hàng đợi. Tuy vậy, ứng dụng có thể chủ động thêm cùng một đối tượng nhiều lần; cấu trúc này không phải set loại trùng.

### 3.2. Chương trình phối hợp đưa và lấy

Tệp `WaitingPutTakeDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class WaitingPutTakeDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        queue.put("first");
        var producerStarted = new CountDownLatch(1);
        var consumerStarted = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(2);

        try {
            var producer = pool.submit(() -> {
                producerStarted.countDown();
                queue.put("second");
                return "put completed";
            });
            if (!producerStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("producer did not start");
            }

            System.out.println("takenFirst=" + queue.take());
            System.out.println("producer=" + producer.get(10, TimeUnit.SECONDS));
            System.out.println("takenSecond=" + queue.take());

            var consumer = pool.submit(() -> {
                consumerStarted.countDown();
                return queue.take();
            });
            if (!consumerStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("consumer did not start");
            }
            queue.put("third");
            System.out.println("consumer=" + consumer.get(10, TimeUnit.SECONDS));
            System.out.println("empty=" + queue.isEmpty());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 WaitingPutTakeDemo.java
java WaitingPutTakeDemo
```

Stdout:

```text
takenFirst=first
producer=put completed
takenSecond=second
consumer=third
empty=true
```

Hàng đợi ban đầu chứa `"first"`. Bên sản xuất muốn đưa `"second"` vào. Luồng chính lấy `"first"`, nhường chỗ; sau khi tác vụ sản xuất hoàn tất, luồng chính lấy `"second"`.

Ở phần sau, bên tiêu thụ gọi `take` trên hàng đợi hiện không có dữ liệu. Luồng chính đưa `"third"` vào và bên tiêu thụ nhận được nó.

Các cổng `producerStarted`, `consumerStarted` dùng để biết tác vụ đã đi đến điểm trước lời gọi hàng đợi. Cổng được mở không chứng minh luồng lập tức chuyển sang trạng thái chờ ngay ở lệnh tiếp theo. Lịch thực thi có thể khiến luồng chính làm thay đổi điều kiện trước khi lời gọi hàng đợi thật sự bắt đầu.

Kết quả đúng của chương trình không cần đoán thời điểm đó: việc đưa `"second"` không thể hoàn thành trước khi chỗ của `"first"` được giải phóng, và bên tiêu thụ cuối chỉ nhận dữ liệu sau khi dữ liệu đã được đưa vào.

Timeout 10 giây ở cổng và `Future.get` là giới hạn để phát hiện thí nghiệm không tiến triển. Nó không làm cho các lời gọi `put` và `take` trong tác vụ tự có timeout 10 giây.

### 3.3. Chờ không có timeout vẫn cần một lối kết thúc

Một lời gọi `take()` có thể tiếp tục chờ nếu không còn ai đưa dữ liệu. Một lời gọi `put()` có thể tiếp tục chờ nếu hàng đợi đầy và không còn ai lấy dữ liệu. Chương trình phải xác định bên nào còn có thể làm điều kiện thay đổi.

Các cách kết thúc thường cần xem xét là gián đoạn luồng, thông điệp kết thúc theo một quy ước, hoặc thay lời gọi bằng dạng có timeout để định kỳ kiểm tra trạng thái. Chọn cách nào tùy vòng đời của quy trình.

Không chuyển sang `put` chỉ vì muốn “không mất dữ liệu” mà bỏ qua khả năng bên tiêu thụ đã dừng. Dữ liệu chưa mất khỏi biến ở bên sản xuất không đồng nghĩa hệ thống còn tiến triển được.

## 4. offer và poll có thời hạn chờ

### 4.1. Đọc kết quả theo ba nhánh

Với `offer(e, timeout, unit)`:

- `true`: phần tử đã được đưa vào.
- `false`: không đưa được phần tử trong thời gian chờ theo phép gọi.
- `InterruptedException`: luồng bị gián đoạn trong thao tác chờ.

Với `poll(timeout, unit)`:

- Trả phần tử khác `null`: phần tử đã được lấy và xóa khỏi hàng đợi.
- `null`: không lấy được phần tử trong thời gian chờ.
- `InterruptedException`: thao tác chờ bị gián đoạn.

Không gom nhánh gián đoạn thành nhánh hết thời gian. Một nhánh là chính sách về thời gian, nhánh kia thường là yêu cầu hủy hoặc dừng từ cơ chế quản lý luồng.

Hai phương thức này không dùng `TimeoutException` để báo timeout. Đừng nhầm với `Future.get(timeout, unit)`, vốn là một API chờ kết quả khác.

### 4.2. Chương trình với điều kiện đầy và rỗng ổn định

Tệp `TimedQueueDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class TimedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        queue.put("A");

        boolean accepted = queue.offer("B", 40, TimeUnit.MILLISECONDS);
        System.out.println("fullTimedOffer=" + accepted);
        System.out.println("existing=" + queue.take());

        String missing = queue.poll(40, TimeUnit.MILLISECONDS);
        System.out.println("emptyTimedPoll=" + missing);

        System.out.println("availableTimedOffer=" +
                queue.offer("C", 1, TimeUnit.SECONDS));
        System.out.println("availableTimedPoll=" +
                queue.poll(1, TimeUnit.SECONDS));

        System.out.println("zeroTimedOffer=" +
                queue.offer("D", 0, TimeUnit.NANOSECONDS));
        System.out.println("zeroTimedPoll=" +
                queue.poll(0, TimeUnit.NANOSECONDS));
        System.out.println("zeroTimedPollEmpty=" +
                queue.poll(0, TimeUnit.NANOSECONDS));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TimedQueueDemo.java
java TimedQueueDemo
```

Stdout:

```text
fullTimedOffer=false
existing=A
emptyTimedPoll=null
availableTimedOffer=true
availableTimedPoll=C
zeroTimedOffer=true
zeroTimedPoll=D
zeroTimedPollEmpty=null
```

Khi hàng đợi có A và không có bên lấy trong lúc `offer("B", ...)`, kết quả là `false`. A vẫn còn. Sau khi lấy A, không có bên sản xuất trong lúc `poll(...)`, nên kết quả là `null`.

Khi điều kiện phù hợp, dạng có timeout vẫn có thể thực hiện ngay: C được đưa vào và lấy ra mà không phải dùng hết một giây. Timeout là giới hạn cho việc chờ điều kiện, không phải yêu cầu phải ngủ đúng bằng thời gian đó.

Ở các lời gọi có thời gian 0, hàng đợi vẫn được thử theo điều kiện hiện tại: D được đưa vào khi có chỗ, rồi lấy ra khi có dữ liệu. Khi đã rỗng, lần `poll` tiếp trả `null`. Không dùng 0 với ý nghĩa “chờ mãi”.

Không in số mili giây đã trôi trong stdout, vì thời gian thực tế phụ thuộc môi trường thực thi. Điều được kiểm tra ở đây là nhánh kết quả và dữ liệu còn lại, không phải một con số thời gian chính xác.

### 4.3. TimeUnit và giới hạn của độ chính xác

`TimeUnit.MILLISECONDS` và `TimeUnit.SECONDS` làm cùng một số 50 mang ý nghĩa khác nhau. Viết rõ đơn vị ở điểm gọi giúp tránh nhầm giây với mili giây.

Đơn vị nanosecond không hứa hệ điều hành hoặc bộ lập lịch có thể đánh thức luồng chính xác đến nanosecond. Xem [ý nghĩa và giới hạn độ phân giải của TimeUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html).

Một luồng được đánh thức còn phải được cấp CPU và hoàn tất phần phối hợp cần thiết trước khi bên gọi quan sát kết quả. Vì vậy, không lấy timeout như một cam kết thời gian thực cứng rằng phương thức chắc chắn trở về trước một thời điểm trên đồng hồ.

### 4.4. Timeout không hoàn tác một thao tác đã thành công

Nếu `offer` trả `true`, công việc đã được thêm; việc bên gọi sau đó nhận ra yêu cầu gốc đã quá hạn không tự xóa công việc khỏi hàng đợi.

Nếu `poll` trả một phần tử, phần tử đó đã bị lấy ra. Một lỗi xảy ra trong bước xử lý sau không tự đưa nó về vị trí cũ.

Từ đó cần xác định “quá hạn” ở tầng nào:

- Hết thời gian được phép chờ chỗ trong hàng đợi.
- Hết thời gian được phép chờ để lấy một công việc.
- Công việc đã nằm trong hàng đợi quá lâu.
- Yêu cầu toàn bộ phải hoàn tất trước một hạn nghiệp vụ.

Đây là những chính sách riêng. Chỉ truyền timeout vào `offer` không giải quyết ba chính sách còn lại.

## 5. InterruptedException và cách giữ đúng tín hiệu dừng

### 5.1. Gián đoạn là một nhánh điều khiển

`put`, `take` và các dạng `offer`/`poll` có thời hạn chờ khai báo `InterruptedException`. Một lời gọi đang chờ có thể được yêu cầu ngừng chờ bằng `interrupt()`.

Gián đoạn không phải `Thread.stop`: nó không cưỡng bức kết thúc mọi mã xử lý của một luồng. Đoạn mã nhận tín hiệu phải có cách phản ứng phù hợp.

Có hai cách xử lý phổ biến:

1. Phương thức còn có thể báo lỗi lên bên gọi: truyền tiếp `InterruptedException`.
2. Ở ranh giới như `Runnable.run`, không truyền ngoại lệ kiểm tra được lên trên: khôi phục trạng thái gián đoạn, rồi kết thúc tác vụ theo chính sách.

Khôi phục cờ rồi tiếp tục gọi thao tác chờ trong một vòng lặp vô hạn thường không thể hiện một quyết định dừng hợp lý. Tác vụ phải quyết định có thoát, dọn tài nguyên hay báo kết quả gì.

### 5.2. Chương trình gián đoạn một bên lấy dữ liệu

Tệp `InterruptQueueDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class InterruptQueueDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        var started = new CountDownLatch(1);
        var outcome = new AtomicReference<String>();

        Thread consumer = new Thread(() -> {
            started.countDown();
            try {
                queue.take();
                outcome.set("unexpected item");
            } catch (InterruptedException ex) {
                boolean cleared = !Thread.currentThread().isInterrupted();
                Thread.currentThread().interrupt();
                outcome.set("failure=" + ex.getClass().getSimpleName()
                        + ", cleared=" + cleared
                        + ", restored=" + Thread.currentThread().isInterrupted());
            }
        }, "queue-consumer");

        consumer.start();
        try {
            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("consumer did not start");
            }
            consumer.interrupt();
            consumer.join(10_000);
            if (consumer.isAlive()) {
                throw new IllegalStateException("consumer did not stop");
            }
            System.out.println(outcome.get());
            System.out.println("queueEmpty=" + queue.isEmpty());
            System.out.println("consumerAlive=" + consumer.isAlive());
        } finally {
            consumer.interrupt();
            consumer.join(10_000);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 InterruptQueueDemo.java
java InterruptQueueDemo
```

Stdout:

```text
failure=InterruptedException, cleared=true, restored=true
queueEmpty=true
consumerAlive=false
```

Không có bên sản xuất nào đưa phần tử vào hàng đợi. Luồng chính yêu cầu gián đoạn sau cổng `started`. Tín hiệu có thể đến trước khi `take` thật sự chờ hoặc trong lúc nó đang chờ; cả hai tình huống đều phù hợp với thí nghiệm.

Ở ví dụ dùng `ArrayBlockingQueue` này, khi bắt ngoại lệ, cờ gián đoạn đã được xóa. Tác vụ kiểm tra điều đó, gọi `interrupt()` trên chính mình để khôi phục cờ, ghi kết quả rồi kết thúc.

Cách sử dụng `InterruptedException` có thể bao gồm việc kiểm tra và xóa trạng thái bằng `Thread.interrupted()`. Xem [InterruptedException Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html).

`isInterrupted()` chỉ đọc trạng thái; `Thread.interrupted()` đọc rồi xóa trạng thái của luồng hiện tại. Không gọi phương thức thứ hai chỉ để ghi nhật ký nếu không muốn tiêu thụ tín hiệu. Xem [hợp đồng kiểm tra trạng thái của Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#interrupted()).

### 5.3. Mẫu sai: biến gián đoạn thành “chưa có dữ liệu”

Đoạn sau là mã minh họa sai, không phải chương trình độc lập:

```java
// SAI: mất tín hiệu dừng và tiếp tục chờ vô hạn.
while (true) {
    try {
        handle(queue.take());
    } catch (InterruptedException ex) {
        System.out.println("try again");
    }
}
```

Nếu chủ sở hữu luồng muốn dừng tác vụ, vòng lặp lại nuốt tín hiệu và bắt đầu chờ tiếp. Một thông báo nhật ký không thay thế việc thực hiện chính sách hủy.

Một mẫu xử lý ở ranh giới tác vụ có thể là:

```java
// Mã minh họa trong thân một Runnable, chưa phải chương trình độc lập.
try {
    while (!Thread.currentThread().isInterrupted()) {
        handle(queue.take());
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
```

Ở mẫu này, nhánh bắt nằm ngoài vòng lặp nên tác vụ rời vòng xử lý khi thao tác chờ bị gián đoạn. Hàm `handle` và việc dọn tài nguyên còn phải tuân theo thiết kế ứng dụng; tín hiệu gián đoạn không tự hoàn tác công việc đã làm dở.

### 5.4. Dừng bộ thực thi khác với đóng hàng đợi

Gọi `shutdown()` trên `ExecutorService` không tự chèn một thông điệp vào hàng đợi của ứng dụng và không tự khiến một vòng `take()` đang chờ biết rằng nguồn dữ liệu đã hết.

`shutdownNow()` cố gắng ngăn tác vụ chưa chạy và dừng các tác vụ đang chạy, thường qua gián đoạn; nó không cam kết mọi mã sẽ dừng nếu mã đó không hợp tác. Xem [vòng đời của ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).

Trong các chương trình minh họa, phần `finally` dùng `shutdownNow()` để yêu cầu dọn các tác vụ còn lại nếu thí nghiệm thất bại. Đó không phải giao thức xử lý hoàn tất mọi công việc của một hệ thống thật.

## 6. Dung lượng, áp lực ngược và khả năng tiến triển

### 6.1. Giới hạn hàng đợi chỉ có tác dụng khi chính sách đi kèm phù hợp

Nếu bên sản xuất nhanh hơn bên tiêu thụ, công việc chờ tăng lên. Một hàng đợi có giới hạn buộc ứng dụng thể hiện điều sẽ xảy ra khi đầy:

| Lựa chọn | Hệ quả cần chấp nhận |
|---|---|
| `put` | Bên sản xuất có thể phải chờ đến khi có chỗ hoặc bị gián đoạn |
| `offer` | Bên sản xuất nhận ngay kết quả không thêm được theo điều kiện dung lượng |
| `offer` có timeout | Bên sản xuất chỉ dành một khoảng chờ cho lần thêm này |
| Chuyển dữ liệu sang nơi khác khi không thêm được | Cần một chính sách dung lượng và lỗi cho nơi nhận thay thế |

Việc làm chậm bên sản xuất khi bên tiêu thụ không theo kịp thường được gọi là áp lực ngược (backpressure). Hàng đợi có giới hạn tạo một điểm để áp dụng chính sách đó; nó không tự chọn giúp ứng dụng nên bỏ, thử lại, báo lỗi hay lưu bền.

Nếu `offer` trả `false` mà bên gọi bỏ qua, dữ liệu có thể bị bỏ quên. Nếu bên gọi thử lại vô hạn với một timeout mới mỗi lần, giới hạn chờ tổng thể có thể biến mất. Nếu chuyển mọi công việc thất bại vào một danh sách không giới hạn, vấn đề dung lượng chỉ được dời sang nơi khác.

### 6.2. Không mặc định mọi hàng đợi đều có giới hạn nhỏ

`LinkedBlockingQueue` cho phép chỉ định dung lượng. Nếu dùng constructor không tham số, giới hạn mặc định là `Integer.MAX_VALUE`, không phải một giới hạn nhỏ giúp điều tiết tải thực tế. Xem [constructor và dung lượng của LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html).

Bộ nhớ có thể cạn trước khi chạm một giới hạn số lượng rất lớn. Kích thước mỗi phần tử, dữ liệu mà nó giữ tham chiếu và số công việc đang được xử lý đều cần được tính đến khi chọn dung lượng.

Đừng suy ra `put` sẽ tạo áp lực ngược hữu ích chỉ từ việc biến có kiểu `BlockingQueue`. Cần xem lớp triển khai và cách tạo đối tượng.

### 6.3. remainingCapacity không đặt chỗ trước

Đoạn minh họa dưới đây không đảm bảo lần thêm sẽ thành công ngay:

```java
// Mã minh họa có khoảng trống giữa kiểm tra và hành động.
if (queue.remainingCapacity() > 0) {
    queue.put(job);
}
```

Sau khi bên này thấy còn chỗ, bên khác có thể lấy chỗ đó. `put` vẫn có thể phải chờ. Tương tự, kiểm tra `isEmpty()` rồi `take()` không đảm bảo việc lấy không chờ.

Nếu muốn thử mà không chờ điều kiện, dùng chính `offer` hoặc `poll` rồi xử lý kết quả. Nếu muốn chờ giới hạn, dùng dạng có timeout. Việc kiểm tra trước không thay thế chính sách của thao tác thực tế.

`size` và `remainingCapacity` vẫn hữu ích để quan sát tải, nhưng không phải vé giữ chỗ cho một bước sau.

### 6.4. Tránh giữ tài nguyên mà bên làm thay đổi điều kiện cần đến

Một tình huống thiết kế có thể không tiến triển:

```text
Bên sản xuất giữ khóa L → gọi put trên hàng đợi đầy → chờ
Bên tiêu thụ cần khóa L → mới có thể đi đến bước take
```

Hàng đợi không thể tự giải phóng một khóa ngoài mà mã ứng dụng đang giữ. Cần thu hẹp vùng giữ tài nguyên hoặc thay cách phối hợp.

Một tình huống khác là dùng cùng một nhóm thực thi nhỏ cho nhiều tác vụ sản xuất và tiêu thụ. Nếu tất cả luồng đều bị giữ bởi các bên `put` đang chờ, còn tác vụ tiêu thụ chưa được chạy, không còn ai nhường chỗ.

Không cần tránh mọi lời gọi chặn; cần chỉ rõ ai còn có thể làm điều kiện thay đổi trong lúc lời gọi ấy chờ.

### 6.5. FIFO của phần tử khác công bằng của luồng

`ArrayBlockingQueue` dùng FIFO cho phần tử. Constructor có cờ công bằng còn điều khiển thứ tự cấp quyền cho các bên đang chờ theo chính sách của lớp.

Hai vấn đề khác nhau: thứ tự công việc được lấy không tự nói luồng nào được chạy trước, và một luồng lấy công việc trước có thể xử lý xong sau luồng khác. Công bằng cũng có chi phí; không đặt cờ chỉ vì tên nghe có vẻ luôn tốt hơn.

## 7. Giao thức kết thúc: thông điệp dừng phải được thiết kế

### 7.1. BlockingQueue không tự biết bên sản xuất đã hết việc

Một lần `poll` trả `null` chỉ nói lần lấy đó không nhận được dữ liệu trong thời gian chờ. Nó không chứng minh không còn bên sản xuất nào sẽ thêm dữ liệu sau này.

Giao diện không có một thao tác đóng chung dùng để thông báo vĩnh viễn hết dữ liệu. Một cách thường dùng là thông điệp kết thúc riêng do ứng dụng nhận diện.

Không dùng một chuỗi có thể trùng dữ liệu thật như `"STOP"` nếu miền dữ liệu cho phép chuỗi đó. Không dùng `null`. Một kiểu thông điệp rõ ràng giúp tách công việc và tín hiệu kết thúc.

### 7.2. Chương trình một bên sản xuất, một bên tiêu thụ

Tệp `ProducerConsumerStopDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ProducerConsumerStopDemo {
    sealed interface Message permits Data, Stop {}
    record Data(int value) implements Message {}
    enum Stop implements Message { INSTANCE }
    record Totals(int count, int sum) {}

    static Totals consume(BlockingQueue<Message> queue)
            throws InterruptedException {
        int count = 0;
        int sum = 0;
        while (true) {
            Message message = queue.take();
            if (message == Stop.INSTANCE) {
                return new Totals(count, sum);
            }
            Data data = (Data) message;
            count++;
            sum += data.value();
        }
    }

    public static void main(String[] args) throws Exception {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(2);
        var pool = Executors.newSingleThreadExecutor();

        try {
            var result = pool.submit(() -> consume(queue));
            queue.put(new Data(10));
            queue.put(new Data(20));
            queue.put(new Data(30));
            queue.put(Stop.INSTANCE);

            Totals totals = result.get(10, TimeUnit.SECONDS);
            System.out.println("processed=" + totals.count());
            System.out.println("sum=" + totals.sum());
            System.out.println("queueEmpty=" + queue.isEmpty());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ProducerConsumerStopDemo.java
java ProducerConsumerStopDemo
```

Stdout:

```text
processed=3
sum=60
queueEmpty=true
```

`Message` chỉ có hai dạng: `Data` chứa số cần xử lý và `Stop.INSTANCE` biểu thị kết thúc. Với đúng một bên tiêu thụ, bên sản xuất đưa ba dữ liệu rồi một tín hiệu dừng.

Vì ví dụ dùng `ArrayBlockingQueue` FIFO và không có bên sản xuất khác, bên tiêu thụ gặp ba dữ liệu trước khi gặp tín hiệu dừng. Nó trả về tổng thay vì tiếp tục `take`.

Dung lượng 2 nhỏ hơn tổng số thông điệp. Chương trình vẫn tiến triển vì bên tiêu thụ được chạy độc lập, lấy dữ liệu và giải phóng chỗ trong lúc bên sản xuất đưa tiếp.

Đây là thí nghiệm với đường xử lý thành công đã xác định. Trong ứng dụng thật, nếu bên tiêu thụ hỏng, bên sản xuất có thể bị giữ trong `put`; cần có cơ chế báo lỗi, hủy và xử lý dữ liệu chưa hoàn tất.

### 7.3. Nhiều bên tiêu thụ cần đủ tín hiệu hoặc một giao thức khác

Nếu có ba bên tiêu thụ và mỗi bên thoát khi gặp một tín hiệu dừng, một tín hiệu chỉ đánh thức và kết thúc được một bên nhận nó. Hai bên còn lại có thể tiếp tục chờ.

Một giao thức phổ biến là gửi một tín hiệu cho mỗi bên tiêu thụ, nhưng chỉ sau khi bảo đảm mọi bên sản xuất đã kết thúc và không thêm dữ liệu nữa. Số bên tiêu thụ, thứ tự chèn và cách xử lý lỗi phải được biết rõ.

Đừng để một bên sản xuất tự gửi tín hiệu dừng khi những bên sản xuất khác còn hoạt động. Dữ liệu đưa sau tín hiệu có thể bị bỏ lại nếu các bên tiêu thụ đã thoát.

Cách “bên tiêu thụ lấy tín hiệu rồi đặt lại cho bên khác” cũng có thêm điều kiện: bước đặt lại có thể chờ, tác vụ có thể bị gián đoạn hoặc dừng giữa chừng. Không mặc định nó là lời giải không cần phối hợp.

### 7.4. Dừng có xử lý hết và dừng ngay là hai yêu cầu khác nhau

Nếu muốn xử lý hết dữ liệu đã chấp nhận, cần một thứ tự dừng cho phép các bên tiêu thụ tiếp tục làm việc đến khi nguồn đóng theo quy ước.

Nếu muốn dừng ngay, phải quyết định dữ liệu còn trong hàng đợi và công việc đang xử lý sẽ đi đâu: bỏ, lưu lại, chuyển giao hoặc báo chưa hoàn tất. Gửi một tín hiệu không tự thu hồi công việc đã được lấy ra.

Một cờ `volatile boolean running` cũng không tự đánh thức một luồng đang chờ trong `take()`. Phải có hành động làm lời gọi đó thoát hoặc chuyển sang một dạng chờ có giới hạn phù hợp.

Không giải quyết việc đánh thức bằng vòng lặp kiểm tra cờ liên tục mà bỏ hết khả năng chờ của hàng đợi.

## 8. Chuyển giao dữ liệu và tính nhìn thấy giữa các luồng

Hành động của bên sản xuất trước khi đặt một đối tượng vào `BlockingQueue` có quan hệ happens-before với hành động sau khi luồng khác truy cập hoặc lấy chính phần tử đó. Điều này cho phép hàng đợi làm điểm chuyển giao dữ liệu giữa các luồng. Xem [bảo đảm chuyển giao dữ liệu của BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Ví dụ suy luận: bên sản xuất hoàn tất khởi tạo công việc rồi mới `put`; bên tiêu thụ `take` được công việc đó rồi đọc dữ liệu đã khởi tạo. Không cần tự thêm một cờ “đã khởi tạo” chỉ để thay thế điểm chuyển giao mà hàng đợi đã cung cấp.

Cần giữ đúng ranh giới:

- Bảo đảm này gắn với đối tượng được chuyển qua hàng đợi.
- Hàng đợi không tạo một bản sao sâu của đối tượng.
- Việc bên sản xuất tiếp tục sửa đối tượng sau khi đưa vào không tự được đồng bộ với mọi lần đọc sau ở bên tiêu thụ.
- Hàng đợi không tự làm một `ArrayList` hoặc một cấu trúc con có thể sửa bên trong trở thành đối tượng dùng chung an toàn.

Trong `ProducerConsumerStopDemo`, dữ liệu là các record đơn giản có trường số không bị sửa sau khi tạo. Bên sản xuất chuyển giao thông điệp rồi không tiếp tục can thiệp dữ liệu của thông điệp đó.

Một quy ước dễ xem xét là bên sản xuất xây dựng dữ liệu xong trước khi gửi; bên nhận sở hữu phần việc sau khi lấy, hoặc dữ liệu được giữ bất biến nếu cần nhiều bên cùng đọc. Khi phải chia sẻ trạng thái thay đổi, thiết kế cơ chế đồng bộ cho chính trạng thái ấy.

Một lần lấy thành công cũng chỉ nói phần tử đã được chuyển khỏi hàng đợi đến bên nhận. Muốn bên gửi biết xử lý hoàn tất cần một kênh trả kết quả, xác nhận hoặc một cơ chế khác. Đừng gán ý nghĩa đó cho việc `put` đã trả về.

## 9. Thời hạn cho nhiều bước và các giới hạn cần giữ rõ

### 9.1. Không cấp lại toàn bộ ngân sách ở mỗi lần thử

Giả sử một yêu cầu chỉ được dành tổng cộng 300 mili giây cho giai đoạn chờ. Nếu mỗi lần `offer` thất bại lại gọi tiếp với 300 mili giây, tổng thời gian chờ có thể vượt xa ý định ban đầu.

Cần chọn mốc bắt đầu và trừ thời gian đã dùng trước khi quyết định chờ tiếp. `System.nanoTime()` được dùng để đo khoảng thời gian trong cùng JVM, không phải timestamp để ghi ngày giờ hoặc so giữa các máy. Xem [System.nanoTime Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()).

Phương thức dưới đây là một đoạn tích hợp minh họa, chưa phải chương trình độc lập. Cần đặt nó trong một lớp có import `BlockingQueue` và `TimeUnit`; `startedAt` lấy từ `System.nanoTime()` tại đầu giai đoạn được tính ngân sách:

```java
static boolean offerWithinBudget(
        BlockingQueue<String> queue,
        String item,
        long startedAt,
        long budgetNanos) throws InterruptedException {

    long elapsed = System.nanoTime() - startedAt;
    long remaining = budgetNanos - elapsed;
    if (remaining <= 0) {
        return false;
    }
    return queue.offer(item, remaining, TimeUnit.NANOSECONDS);
}
```

Đoạn này chọn chính sách không thử đưa thêm khi ngân sách đã hết, kể cả nếu hiện tại có chỗ. Đây là quyết định của hàm tích hợp, khác với một lời gọi `offer` có timeout 0 vẫn có thể thử điều kiện hiện tại.

Giả định ngân sách không âm, có độ dài hợp lý và các mốc đo thuộc cùng JVM. Không dùng việc cộng vào một timestamp ngày giờ để thay cho phép đo khoảng thời gian.

### 9.2. Ngân sách của thao tác xếp hàng chưa là hạn của toàn bộ công việc

Thời gian sau khi nhận phần tử còn có thể gồm chờ trong hàng đợi, chờ tài nguyên khác, thực hiện I/O và xử lý kết quả. Muốn kiểm soát tổng thể, từng giai đoạn phải nhận phần ngân sách còn lại hoặc kiểm tra cùng một hạn theo mô hình của ứng dụng.

Ngay cả khi không cấp lại ngân sách, JVM và bộ lập lịch vẫn không được biến thành hệ thống thời gian thực cứng. Một cơ chế timeout giúp ứng dụng bỏ chờ theo chính sách; nó không bảo đảm mọi tài nguyên ngoài hoặc mọi tác vụ đã bắt đầu đều bị dừng đúng thời điểm.

### 9.3. Tránh dùng một lần hết thời gian để kết luận nguồn đã đóng

Một bên tiêu thụ dùng `poll(1, SECONDS)` có thể định kỳ kiểm tra yêu cầu dừng, ghi nhận trạng thái hoặc thực hiện công việc bảo trì. Nếu nhận `null`, nó cần quyết định bước tiếp theo theo giao thức chung.

Dừng chỉ vì một lần không nhận dữ liệu có thể làm hỏng một nguồn sản xuất theo đợt. Ngược lại, lặp mãi sau khi nguồn thực sự đã kết thúc cũng để lại tác vụ không cần thiết.

Vì vậy, timeout và điều kiện hoàn tất nguồn cần được mô hình hóa riêng. Tín hiệu nguồn đã hết nên do một bên có đủ thông tin xác nhận, thay vì được suy ra từ tốc độ hiện tại.

### 9.4. Quan sát theo từng giai đoạn

Khi hệ thống chậm, phân biệt:

- Thời gian chờ chỗ để được chấp nhận.
- Thời gian công việc nằm trong hàng đợi.
- Thời gian xử lý sau khi đã lấy.
- Số lần thêm bị từ chối hoặc hết thời gian.
- Số lần bị gián đoạn và nguyên nhân yêu cầu dừng.
- Số công việc đang xử lý, tách khỏi số còn trong hàng đợi.

Hàng đợi rỗng không chứng minh mọi công việc đã hoàn tất: các bên tiêu thụ có thể đã lấy hết nhưng vẫn đang làm. Hàng đợi không đầy cũng không chứng minh hệ thống không bị quá tải ở một tầng khác.

Các thí nghiệm trong bài kiểm chứng hợp đồng thao tác và cách phối hợp có kiểm soát. Chúng không thay thế việc đo tải ứng dụng hoặc chứng minh tất cả lịch thực thi có thể có đều không gặp vấn đề.

## 10. Lỗi thường gặp và thực hành

### 10.1. Nhận diện lỗi từ chính sách đã chọn

| Mẫu sử dụng | Vấn đề | Hướng xem xét |
|---|---|---|
| `put` trong luồng không được phép chờ lâu | Luồng có thể bị giữ khi đầy | Dùng chính sách từ chối hoặc chờ có giới hạn phù hợp |
| Bỏ qua kết quả `offer` | Không biết công việc có được chấp nhận không | Xử lý rõ nhánh `false` |
| Bắt gián đoạn rồi tiếp tục vòng lặp | Có thể làm mất yêu cầu dừng | Truyền tiếp hoặc khôi phục cờ và thoát theo chính sách |
| Dùng `null` làm thông điệp dừng | Không hợp lệ với BlockingQueue | Dùng kiểu hoặc đối tượng thông điệp riêng |
| Thấy `poll` trả `null` rồi kết luận hết việc | Nguồn có thể vẫn thêm sau đó | Dùng giao thức kết thúc nguồn |
| Kiểm tra `remainingCapacity` rồi coi đã giữ chỗ | Luồng khác có thể chiếm chỗ trước | Dựa vào kết quả thao tác thực tế |
| Cấp lại toàn bộ timeout khi thử lại | Tổng thời gian không còn bị giới hạn như dự định | Tính ngân sách còn lại |
| Chỉ gọi `shutdown` rồi chờ consumer tự thoát `take` | Hàng đợi không nhận tín hiệu nguồn kết thúc | Thiết kế cách đánh thức và kết thúc tác vụ |

Các hướng trên là quyết định về hành vi ứng dụng. Không có một phương thức duy nhất phù hợp với mọi loại công việc hoặc mọi yêu cầu mất dữ liệu, độ trễ và dừng hệ thống.

### Bài 1: chọn phương thức đúng với yêu cầu

Một hàng đợi có giới hạn dung lượng. Với mỗi yêu cầu sau, hãy chọn phương thức và nhánh xử lý:

1. Nếu chưa có chỗ thì trả về cho bên gọi ngay, để bên gọi báo quá tải.
2. Cho phép chờ chỗ tối đa trong một khoảng cụ thể.
3. Tác vụ nền được phép chờ dữ liệu đến nhưng phải dừng được.
4. Chỉ muốn xem phần tử đầu, không lấy nó ra.

Hướng giải thích: dùng `offer`, `offer` có timeout, `take` với chính sách gián đoạn hoặc kết thúc, và `peek`. Cần nêu rõ giá trị trả về hoặc ngoại lệ của từng nhánh.

### Bài 2: kết quả nào xảy ra khi đầy và rỗng?

Với dung lượng 1, lần lượt đưa A vào, thử đưa B bằng `offer` có timeout khi không có bên lấy, lấy A rồi `poll` có timeout khi không có bên thêm.

Giải thích vì sao lần đưa B nhận `false`, lần lấy sau nhận `null`, và vì sao không có `TimeoutException` từ hai phương thức hàng đợi đó.

Sau đó thêm trường hợp luồng bị gián đoạn trong lúc chờ. Nhánh này phải được mô tả riêng, không đổi tên nó thành hết thời gian.

### Bài 3: tìm nơi không còn khả năng tiến triển

Một nhóm thực thi có hai luồng. Hai tác vụ sản xuất đều đang `put` vào hàng đợi đầy; tác vụ tiêu thụ được xếp trong cùng nhóm nhưng chưa chạy.

Hãy chỉ ra ai có thể tạo chỗ trống ở trạng thái đó. Việc tăng dung lượng có sửa được quan hệ phụ thuộc một cách chắc chắn không?

Hướng giải thích: tăng dung lượng có thể làm tình huống đến muộn hơn, nhưng không thay thế thiết kế bảo đảm bên tiêu thụ có thể chạy. Cần xem bố trí luồng, chính sách chờ và quan hệ giữa các tác vụ.

### Bài 4: dừng nhiều bên tiêu thụ

Có hai bên sản xuất và ba bên tiêu thụ. Một bên sản xuất vừa hoàn tất và muốn gửi thông điệp dừng.

- Nó đã có đủ thông tin rằng nguồn hết dữ liệu chưa?
- Nếu mỗi bên tiêu thụ thoát khi lấy tín hiệu, cần tổ chức số tín hiệu thế nào?
- Nếu một bên tiêu thụ hỏng khi hàng đợi đầy, bên gửi tín hiệu có thể bị giữ ở đâu?

Hướng giải thích: phải phối hợp hoàn tất của mọi bên sản xuất, rồi thiết kế việc kết thúc đủ các bên tiêu thụ. Cần một đường báo lỗi và hủy, không chỉ đường thành công có thông điệp dừng.

### Bài 5: chuyển giao và xử lý hoàn tất

Bên sản xuất tạo một đối tượng, đưa vào hàng đợi rồi tiếp tục sửa các trường của nó. Bên tiêu thụ lấy đối tượng và đồng thời đọc các trường đó.

Vì sao tính an toàn của hàng đợi chưa đủ để kết luận việc sửa và đọc sau đó an toàn? Nếu bên gửi muốn biết xử lý đã xong, nó cần thêm thông tin gì?

Hướng giải thích: điểm chuyển giao bảo đảm tính nhìn thấy cho phần việc trước khi gửi; nó không làm mọi thay đổi tiếp theo được đồng bộ. Cần dữ liệu bất biến, chuyển quyền sử dụng hoặc đồng bộ riêng, cùng kênh xác nhận nếu phải theo dõi kết quả xử lý.

### Các câu hỏi cần trả lời trước khi dùng thao tác chờ

1. Bên gọi có được phép giữ luồng trong lúc chờ không?
2. Ai có thể làm điều kiện chờ thay đổi?
3. Dung lượng có thực sự được giới hạn theo mục tiêu vận hành không?
4. Nhánh hết thời gian và nhánh gián đoạn được xử lý ra sao?
5. Nguồn kết thúc bằng giao thức nào, ai có quyền xác nhận kết thúc?
6. Có đang giữ khóa hoặc tài nguyên mà bên còn lại cần không?
7. Thành công đang được hiểu là đã xếp hàng, đã lấy hay đã xử lý xong?
8. Đối tượng sau khi chuyển giao có tiếp tục bị nhiều bên sửa không?

Dùng đúng `put`, `take` và dạng có timeout cần cả lựa chọn phương thức lẫn một câu trả lời rõ về tiến triển, quyền sở hữu dữ liệu và vòng đời tác vụ.
