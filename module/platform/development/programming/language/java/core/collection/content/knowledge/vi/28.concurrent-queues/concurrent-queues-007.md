# SynchronousQueue và TransferQueue

## 1. Ba mốc khác nhau: được chấp nhận, có bên nhận, xử lý hoàn tất

Trong một quy trình chuyển công việc giữa các luồng, chữ “gửi thành công” có thể mang nhiều nghĩa:

1. Hàng đợi đã chấp nhận công việc để giữ hoặc chuyển tiếp.
2. Công việc đã được ghép với một bên nhận.
3. Bên nhận đã xử lý xong và có kết quả.

Nếu không xác định rõ mốc nào đang được xác nhận, chương trình có thể tiếp tục quá sớm hoặc chờ ở sai nơi.

Một hàng đợi có vùng đệm thường cho phép bên sản xuất gửi trước, bên tiêu thụ lấy sau. Một cơ chế chuyển giao trực tiếp yêu cầu thao tác gửi và thao tác nhận gặp nhau. Một cơ chế trả kết quả còn phải xác nhận cả phần xử lý sau khi nhận.

```text
Chấp nhận công việc
    → ghép với thao tác nhận
        → bên nhận thực hiện xử lý
            → công bố kết quả hoặc lỗi
```

`SynchronousQueue` tập trung vào chuyển giao trực tiếp: không có chỗ để giữ một phần tử chờ như hàng đợi dung lượng 1.

`TransferQueue` là giao diện bổ sung cách gửi có thể chờ bên nhận. Cài đặt thông dụng trong thư viện chuẩn là `LinkedTransferQueue`; nó cho phép cả gửi thông thường vào một hàng đợi không giới hạn dung lượng và gửi theo cách chờ được nhận.

Hai cơ chế giúp bên sản xuất biết thêm về điểm chuyển giao. Chúng chưa tự trở thành lời gọi xử lý nghiệp vụ đồng bộ đến lúc có kết quả.

Bài dùng Java 17 trở lên. Bốn chương trình bên dưới độc lập, không cần thư viện ngoài. Lưu đúng tên tệp, biên dịch và chạy từ thư mục chứa tệp. Kết quả được in từ luồng chính ở các điểm có phối hợp rõ, thay vì suy đoán từ thứ tự in giữa nhiều luồng.

## 2. SynchronousQueue: điểm gặp giữa bên gửi và bên nhận

### 2.1. Không phải hàng đợi có một ô

`SynchronousQueue<E>` không có dung lượng chứa nội bộ, kể cả một phần tử. Mỗi lần đưa vào thành công phải được ghép với một thao tác lấy tương ứng. Ngược lại, bên lấy cũng cần một bên làm dữ liệu sẵn sàng để chuyển giao. Xem [SynchronousQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html).

Mô hình khái niệm:

```text
Hàng đợi có vùng đệm:
gửi A → [ A được giữ ] → sau đó mới có bên lấy A

SynchronousQueue:
bên gửi A ── gặp ── bên nhận A
           không có ô giữ A giữa hai giai đoạn độc lập
```

Điều này không đòi hai luồng bắt đầu lời gọi đúng cùng một thời điểm trên đồng hồ. Một bên có thể đến trước và chờ bên còn lại.

Cũng không có nghĩa không dùng bộ nhớ nào: bên gửi đang chờ vẫn có thể giữ đối tượng cần chuyển, trạng thái lời gọi và tài nguyên của tác vụ. Không có vùng đệm phần tử không đồng nghĩa toàn bộ quy trình không có công việc tồn.

### 2.2. Chọn phương thức là chọn cách chờ đối tác

| Lời gọi trên SynchronousQueue | Ý nghĩa chính |
|---|---|
| `put(e)` | Chờ ghép được với thao tác nhận nếu cần |
| `offer(e)` | Chỉ chuyển nếu có thể ghép với bên nhận đang chờ; không giữ lại khi trả `false` |
| `offer(e, timeout, unit)` | Dành một khoảng chờ để có bên nhận |
| `take()` | Chờ có bên gửi để nhận phần tử |
| `poll()` | Thử nhận từ một bên đang làm phần tử sẵn sàng |
| `poll(timeout, unit)` | Dành một khoảng chờ cho phần tử được chuyển đến |

`offer` không thể thành công chỉ vì cấu trúc “đang rỗng”. Với cơ chế này, không có ô trống để chiếm; điều kiện cần là đối tác nhận.

`take` trả phần tử đã nhận. `put` hoàn tất bình thường xác nhận việc chuyển giao đã được ghép, không phải việc xử lý dữ liệu sau lời gọi nhận đã hoàn tất.

### 2.3. Chương trình chuyển giao và các phép quan sát

Tệp `SynchronousHandoffDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;

public class SynchronousHandoffDemo {
    public static void main(String[] args) throws Exception {
        var queue = new SynchronousQueue<String>();
        System.out.println("initialSize=" + queue.size());
        System.out.println("remainingCapacity=" + queue.remainingCapacity());
        System.out.println("offerWithoutReceiver=" + queue.offer("unused"));
        System.out.println("pollWithoutSender=" + queue.poll());

        var started = new CountDownLatch(1);
        var pool = Executors.newSingleThreadExecutor();
        try {
            var sender = pool.submit(() -> {
                started.countDown();
                queue.put("A");
                return "handoff completed";
            });
            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("sender did not start");
            }

            System.out.println("sizeBeforeReceive=" + queue.size());
            System.out.println("emptyBeforeReceive=" + queue.isEmpty());
            System.out.println("peekBeforeReceive=" + queue.peek());
            System.out.println("received=" + queue.take());
            System.out.println("sender=" + sender.get(10, TimeUnit.SECONDS));

            System.out.println("timedOfferWithoutReceiver=" +
                    queue.offer("B", 30, TimeUnit.MILLISECONDS));
            System.out.println("timedPollWithoutSender=" +
                    queue.poll(30, TimeUnit.MILLISECONDS));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SynchronousHandoffDemo.java
java SynchronousHandoffDemo
```

Stdout:

```text
initialSize=0
remainingCapacity=0
offerWithoutReceiver=false
pollWithoutSender=null
sizeBeforeReceive=0
emptyBeforeReceive=true
peekBeforeReceive=null
received=A
sender=handoff completed
timedOfferWithoutReceiver=false
timedPollWithoutSender=null
```

Ban đầu không có bên nhận, nên `offer("unused")` trả `false` và phần tử không được giữ lại. Không có bên gửi, nên `poll()` trả `null`.

Sau đó tác vụ gửi gọi `put("A")`, còn luồng chính gọi `take()`. Cặp lời gọi ghép với nhau: luồng chính nhận A, bên gửi có thể hoàn tất.

Cổng `started` nằm trước `put`. Nó cho biết tác vụ đã đi đến điểm đó, không chứng minh luồng chắc chắn đã chuyển sang trạng thái chờ tại một thời điểm cụ thể. Dù bên nào đi đến thao tác hàng đợi trước, chương trình vẫn có đủ hai bên để chuyển giao.

Ở cuối chương trình, bên gửi trước đã hoàn tất và không có đối tác mới. Lần `offer` có timeout trả `false`; lần `poll` có timeout trả `null`.

Không in thời gian đã trôi vì bài kiểm tra nhánh kết quả, không hứa độ chính xác của lịch thực thi.

### 2.4. Vì sao size luôn 0 mà vẫn chuyển được dữ liệu?

Với các phương thức quan sát kiểu collection, `SynchronousQueue` hoạt động như một collection rỗng:

- `size()` là 0.
- `isEmpty()` là `true`.
- `remainingCapacity()` là 0.
- `peek()` là `null`.
- Iterator không cung cấp một danh sách phần tử đang chờ để duyệt.

Trong chương trình, các kết quả trước khi nhận vẫn như vậy dù tác vụ gửi đã bắt đầu. Không thể dùng chúng để đếm bên gửi đang chờ, đo tổng công việc của hệ thống hay kết luận không có hoạt động chuyển giao.

Đừng viết “nếu size bằng 0 thì không gọi take”. Với `SynchronousQueue`, chính thao tác lấy mới tham gia vào việc nhận dữ liệu.

Tương tự, `clear()` không phải một thao tác hủy mọi bên đang chờ. Quy trình dừng phải dùng cơ chế thích hợp cho tác vụ đang thực hiện, chẳng hạn gián đoạn có hợp tác.

## 3. TransferQueue: chọn chờ được nhận hoặc chỉ xếp hàng

### 3.1. Phân biệt giao diện và lớp triển khai

```text
BlockingQueue
    ├── SynchronousQueue
    └── TransferQueue
            └── LinkedTransferQueue
```

Sơ đồ thể hiện khả năng qua giao diện, không khẳng định mọi đường là quan hệ lớp cha trực tiếp.

`SynchronousQueue` không triển khai giao diện `TransferQueue`; nó không có phương thức `transfer` chỉ vì hành vi `put` cũng đòi một lần nhận.

`TransferQueue<E>` mở rộng `BlockingQueue<E>`, thêm các phép chuyển giao và thông tin về bên nhận đang chờ. Giao diện này không tự quy định mọi cài đặt phải không giới hạn dung lượng. Xem [TransferQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TransferQueue.html).

Trong bài, lớp cụ thể được dùng là `LinkedTransferQueue`. Đây là một hàng đợi dựa trên nút liên kết, không có giới hạn capacity đặt qua constructor. Đừng nhầm nó với `LinkedBlockingQueue`, vốn có constructor cho phép chỉ định dung lượng.

### 3.2. Các phép gửi có ý nghĩa khác nhau

| Phép gọi | Điều bên gửi yêu cầu | Có giữ dữ liệu để chờ bên nhận không? |
|---|---|---|
| `put(e)`, `offer(e)` thông thường trên LinkedTransferQueue | Hàng đợi chấp nhận dữ liệu | Có thể giữ để bên nhận đến sau; không chờ xác nhận nhận |
| `transfer(e)` | Chờ chuyển được phần tử cho bên nhận | Có thể chờ việc nhận, kể cả khi chưa có bên nhận lúc gọi |
| `tryTransfer(e)` | Chỉ chuyển ngay cho bên nhận đang chờ | Nếu thất bại trả `false`, không xếp phần tử lại để chờ |
| `tryTransfer(e, timeout, unit)` | Chờ việc nhận trong một khoảng | Có thể chờ; hết thời gian thì báo thất bại theo hợp đồng |

`tryTransfer(e)` không phải tên khác của `offer(e)`. Trên `LinkedTransferQueue`, `offer` có thể nhận dữ liệu khi chưa có người lấy, còn `tryTransfer` không làm điều đó nếu phải trả `false`.

Tương tự, `offer(e, timeout, unit)` trên `LinkedTransferQueue` không biến thành lời gọi chờ người nhận. Vì lớp không bị giới hạn dung lượng, timeout đó không tạo một giới hạn chờ được nhận. Phải chọn đúng `tryTransfer` có timeout nếu đó là yêu cầu.

### 3.3. Chương trình không có bên nhận

Tệp `BufferedTransferChoicesDemo.java`:

```java
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TransferQueue;

public class BufferedTransferChoicesDemo {
    public static void main(String[] args) throws InterruptedException {
        TransferQueue<String> queue = new LinkedTransferQueue<>();
        queue.put("A");
        System.out.println("offerB=" + queue.offer("B"));
        System.out.println("timedOfferC=" +
                queue.offer("C", 1, TimeUnit.SECONDS));
        System.out.println("buffered=" + queue);
        System.out.println("taken=" + queue.take() + ","
                + queue.take() + "," + queue.take());

        System.out.println("immediateTransfer=" + queue.tryTransfer("X"));
        System.out.println("afterImmediateFailure=" + queue.poll());
        System.out.println("timedTransfer=" +
                queue.tryTransfer("Y", 30, TimeUnit.MILLISECONDS));
        System.out.println("afterTimedFailure=" + queue.poll());
        System.out.println("remainingCapacity=" + queue.remainingCapacity());
        System.out.println("waitingConsumer=" + queue.hasWaitingConsumer());
        System.out.println("waitingConsumerCount=" +
                queue.getWaitingConsumerCount());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BufferedTransferChoicesDemo.java
java BufferedTransferChoicesDemo
```

Stdout:

```text
offerB=true
timedOfferC=true
buffered=[A, B, C]
taken=A,B,C
immediateTransfer=false
afterImmediateFailure=null
timedTransfer=false
afterTimedFailure=null
remainingCapacity=2147483647
waitingConsumer=false
waitingConsumerCount=0
```

Không có luồng tiêu thụ nào trong chương trình. A, B, C vẫn được chấp nhận qua `put` và `offer`, rồi luồng chính lấy chúng theo thứ tự đã gửi.

Điều quan trọng là lời gọi đưa A vào đã kết thúc trước khi chương trình bắt đầu lấy A. `LinkedTransferQueue.put` không cần một đối tác nhận xuất hiện ngay để hoàn tất.

Ngược lại, `tryTransfer("X")` không có bên nhận đang chờ nên trả `false`. X không xuất hiện ở lần `poll` sau. Lần chuyển Y có timeout cũng thất bại và không để Y lại trong hàng đợi.

Các bảo đảm về hết thời gian hoặc gián đoạn không để phần tử tiếp tục nằm chờ được mô tả rõ trong [các phép chuyển của LinkedTransferQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedTransferQueue.html#tryTransfer(E,long,java.util.concurrent.TimeUnit)).

`remainingCapacity()` ở đây là `Integer.MAX_VALUE`, biểu thị lớp không bị giới hạn dung lượng theo capacity. Nó không đo bộ nhớ còn lại và không chứng minh nguồn tài nguyên vô hạn.

Các phép đếm bên nhận trả 0 hoặc `false` vì trong thí nghiệm không có bên nhận nào. Trong một quy trình thật có nhiều luồng, chúng chỉ là quan sát trạng thái tại một thời điểm, không phải quyền giữ chỗ.

## 4. transfer xác nhận chuyển giao, không xác nhận xử lý xong

### 4.1. Điểm dễ hiểu sai nhất

Xét đường gọi:

```text
Bên sản xuất: transfer(work) ── hoàn tất khi việc chuyển giao đã ghép
                                 │
Bên tiêu thụ:               take() nhận work
                                 → xử lý
                                 → tạo kết quả
```

Mã xử lý nằm sau `take()`. Bên gửi có thể được tiếp tục trước khi phần xử lý đó chạy đến kết quả.

Thậm chí không nên suy ra rằng mọi câu lệnh ngay sau `take` ở bên nhận đều đã chạy trước khi `transfer` ở bên gửi trở về. Hai luồng được lập lịch độc lập sau khi chuyển giao đã được ghép.

Nếu nghiệp vụ cần kết quả, hãy mô hình hóa một đường phản hồi riêng. Một cách ở mức ứng dụng là gửi cùng đối tượng công việc một `CompletableFuture` để bên xử lý công bố kết quả hoặc lỗi.

### 4.2. Chương trình tách nhận và xử lý bằng cổng chờ

Tệp `ReceiptAndReplyDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TransferQueue;

public class ReceiptAndReplyDemo {
    record Work(String text, CompletableFuture<Integer> reply) {}

    public static void main(String[] args) throws Exception {
        TransferQueue<Work> queue = new LinkedTransferQueue<>();
        var received = new CountDownLatch(1);
        var allowProcessing = new CountDownLatch(1);
        var work = new Work("java", new CompletableFuture<>());
        var pool = Executors.newFixedThreadPool(2);

        try {
            var consumer = pool.submit(() -> {
                Work item = queue.take();
                received.countDown();
                try {
                    if (!allowProcessing.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("processing gate timeout");
                    }
                    item.reply().complete(item.text().length());
                    return "consumer finished";
                } catch (Exception ex) {
                    item.reply().completeExceptionally(ex);
                    throw ex;
                }
            });
            var producer = pool.submit(() -> {
                queue.transfer(work);
                return "receipt confirmed";
            });

            System.out.println("transfer=" + producer.get(10, TimeUnit.SECONDS));
            if (!received.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("receipt gate timeout");
            }
            System.out.println("replyDoneBeforeProcessing=" + work.reply().isDone());

            allowProcessing.countDown();
            System.out.println("result=" + work.reply().get(10, TimeUnit.SECONDS));
            System.out.println("consumer=" + consumer.get(10, TimeUnit.SECONDS));
        } finally {
            allowProcessing.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ReceiptAndReplyDemo.java
java ReceiptAndReplyDemo
```

Stdout:

```text
transfer=receipt confirmed
replyDoneBeforeProcessing=false
result=4
consumer=consumer finished
```

`Work` chứa chuỗi cần xử lý và một future dành cho phản hồi. Bên tiêu thụ lấy được công việc, mở cổng `received`, rồi chưa được phép xử lý đến khi luồng chính mở `allowProcessing`.

Bên sản xuất gọi `transfer(work)`. Luồng chính đợi lời gọi đó hoàn tất, sau đó xác nhận bên nhận đã đi qua cổng nhận. Tuy vậy, future phản hồi vẫn chưa hoàn tất vì cổng xử lý còn đóng.

Kết quả `replyDoneBeforeProcessing=false` không dựa vào việc ngủ một khoảng rồi hy vọng bên kia chưa chạy xong. Nó dựa trên điều kiện rõ ràng: chương trình chưa cho phép xử lý.

Sau khi mở cổng, bên tiêu thụ tính độ dài chuỗi `"java"` và hoàn tất future bằng 4. Luồng chính nhận kết quả qua `get`, rồi đợi tác vụ tiêu thụ kết thúc.

### 4.3. Bốn trạng thái cần quản lý nếu có đường phản hồi

Một ứng dụng có thể cần phân biệt:

1. Chưa chuyển giao được.
2. Đã có bên nhận, đang chờ xử lý.
3. Xử lý hoàn tất với kết quả.
4. Xử lý thất bại hoặc bị hủy.

`transfer` giải quyết ranh giới chuyển giao, không thay thế mọi trạng thái còn lại.

`CompletableFuture` hỗ trợ công bố kết quả hoặc hoàn tất bằng lỗi. Nếu quên hoàn tất đường lỗi, bên chờ có thể giữ một future không còn ai chịu trách nhiệm kết thúc. Xem [CompletableFuture Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

Ví dụ bắt các ngoại lệ thông thường sau khi đã nhận để báo lỗi vào future, rồi để tác vụ thất bại. Đây là mẫu học về hai mốc, không phải một hệ thống phục hồi đầy đủ cho mọi lỗi, dừng tiến trình hoặc mất nguồn tài nguyên.

### 4.4. Timeout phản hồi khác timeout chuyển giao

Nếu bên gửi đợi phản hồi 1 giây rồi hết thời gian, công việc có thể đã được nhận và vẫn đang xử lý. Một lần hết thời gian ở `Future.get` không tự lấy công việc khỏi tay bên tiêu thụ.

Ngược lại, nếu chuyển giao có timeout chưa thành công, chưa nên chờ kết quả như thể đã có người chịu trách nhiệm xử lý.

Cần gắn chính sách hủy với trạng thái thực tế. Không tự gửi lại mọi công việc chỉ vì chưa có phản hồi: lần xử lý đầu có thể vẫn đang tiếp tục, dẫn đến thực hiện trùng.

Với các thao tác bên ngoài cần tránh lặp, mã nhận diện công việc và cơ chế xử lý lặp là quyết định ở mức nghiệp vụ. Một cấu trúc chuyển giao trong bộ nhớ không tự cung cấp việc xử lý đúng một lần trên toàn hệ thống.

## 5. Hết thời gian và gián đoạn phải là các nhánh riêng

### 5.1. Kết quả timeout

Trên `SynchronousQueue`:

- `offer(e, timeout, unit)` trả `false` khi không chuyển được trong thời gian chờ.
- `poll(timeout, unit)` trả `null` khi không nhận được phần tử trong thời gian chờ.

Trên `TransferQueue`, dạng `tryTransfer` có timeout trả `false` nếu không chuyển được theo thời gian chờ. Với `LinkedTransferQueue` trong ví dụ, phần tử của lần thất bại đó không bị để lại để một bên khác nhận sau.

Không đổi ý nghĩa của `false` thành “đã xếp hàng để xử lý sau”. Nếu ứng dụng muốn một nhánh dự phòng xếp hàng, phải viết và chấp nhận chính sách đó rõ ràng.

Timeout không phải thời gian phải chờ đủ nếu đối tác đã sẵn sàng. Nó cũng không phải cam kết thời gian thực cứng về thời điểm luồng chắc chắn được CPU và trở về với bên gọi.

### 5.2. Kết quả gián đoạn

`SynchronousQueue.put`, `take`, các dạng chờ có timeout, cũng như `transfer` và `tryTransfer` có timeout, có thể báo `InterruptedException`.

Đây thường là đường điều khiển để tác vụ hợp tác với yêu cầu dừng. Không nuốt ngoại lệ rồi lặp lại việc chuyển giao vô hạn mà không xét yêu cầu hủy.

Nếu phương thức có thể truyền tiếp ngoại lệ, giữ nguyên nhánh đó cho bên gọi quyết định. Nếu ở ranh giới tác vụ không truyền được ngoại lệ kiểm tra, có thể khôi phục cờ gián đoạn rồi kết thúc theo chính sách.

### 5.3. Chương trình hủy một lần transfer chưa có người nhận

Tệp `InterruptedTransferDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TransferQueue;
import java.util.concurrent.atomic.AtomicReference;

public class InterruptedTransferDemo {
    public static void main(String[] args) throws Exception {
        TransferQueue<String> queue = new LinkedTransferQueue<>();
        var started = new CountDownLatch(1);
        var outcome = new AtomicReference<String>();

        Thread sender = new Thread(() -> {
            started.countDown();
            try {
                queue.transfer("cancelled");
                outcome.set("unexpected receipt");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                outcome.set("failure=" + ex.getClass().getSimpleName()
                        + ", restored=" + Thread.currentThread().isInterrupted());
            }
        }, "transfer-sender");

        sender.start();
        try {
            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("sender did not start");
            }
            sender.interrupt();
            sender.join(10_000);
            if (sender.isAlive()) {
                throw new IllegalStateException("sender did not stop");
            }
            System.out.println(outcome.get());
            System.out.println("remainingElement=" + queue.poll());
            System.out.println("senderAlive=" + sender.isAlive());
        } finally {
            sender.interrupt();
            sender.join(10_000);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 InterruptedTransferDemo.java
java InterruptedTransferDemo
```

Stdout:

```text
failure=InterruptedException, restored=true
remainingElement=null
senderAlive=false
```

Không có bên tiêu thụ nào có thể nhận phần tử trong thí nghiệm. Luồng chính yêu cầu gián đoạn, rồi đợi bên gửi kết thúc trước khi kiểm tra hàng đợi.

Cổng `started` nằm trước lời gọi `transfer`; tín hiệu có thể đến trước khi lời gọi bắt đầu chờ hoặc trong khi chờ. Chương trình không dùng trạng thái luồng quan sát được để ép một lịch thực thi duy nhất.

Kết quả cho thấy nhánh `InterruptedException` được xử lý, cờ được khôi phục và không còn phần tử `"cancelled"` để `poll` nhận sau đó.

Điều kiện “không có người nhận” giúp kết quả thí nghiệm rõ ràng. Nếu trong ứng dụng thật việc chuyển giao đã thành công rồi mới có yêu cầu dừng, không được xem tín hiệu đến sau như một thao tác hoàn tác phần xử lý đã giao.

### 5.4. Tách chính sách bỏ chờ và chính sách thu hồi công việc

Bỏ chờ một lần chuyển chưa thành công khác với thu hồi một công việc đã được người khác nhận. Bỏ chờ phản hồi cũng khác với dừng hoạt động xử lý hoặc I/O.

Hãy ghi rõ mỗi timeout áp dụng cho giai đoạn nào, ai còn giữ quyền sử dụng công việc và ai phải hoàn tất đường phản hồi. Nếu có nhiều lần thử, dùng một ngân sách tổng phù hợp thay vì tự cấp lại toàn bộ thời gian ở mọi bước.

Không dùng `clear`, `remove` hoặc một lần quan sát kích thước để thay cho giao thức hủy và xác nhận của ứng dụng. Những thao tác collection không mô hình hóa đầy đủ một công việc đã chuyển đến luồng khác.

## 6. Thông tin bên nhận đang chờ: quan sát chưa là đặt chỗ

`TransferQueue` có:

- `hasWaitingConsumer()`: có bên tiêu thụ đang chờ nhận qua `take` hoặc `poll` có thời hạn hay không.
- `getWaitingConsumerCount()`: ước lượng số bên đang chờ.

Các số liệu này hữu ích để quan sát hoặc đưa ra một lựa chọn có thể chấp nhận sai lệch. Chúng không bảo đảm trạng thái còn giữ nguyên đến lời gọi tiếp theo.

Đoạn minh họa dưới đây có khoảng trống giữa kiểm tra và hành động, chưa phải chương trình độc lập:

```java
// Không được suy ra transfer sẽ không chờ từ lần kiểm tra này.
if (queue.hasWaitingConsumer()) {
    queue.transfer(item);
}
```

Sau lần kiểm tra, một bên sản xuất khác có thể ghép với người nhận đó; người nhận cũng có thể hết thời gian hoặc bị gián đoạn. Lời gọi `transfer` của bên này vẫn có thể phải chờ.

Nếu đúng nhu cầu là chỉ chuyển ngay khi ghép được, gọi `tryTransfer(item)` và xử lý kết quả của chính lời gọi. Không dùng lần quan sát trước để biến một phép chờ thành một phép không chờ.

Tương tự, không chờ bằng vòng lặp liên tục gọi `getWaitingConsumerCount()` để cố tạo độ chính xác. Số đếm được mô tả là ước lượng và có thể tốn công hơn một phép kiểm tra đơn giản; nó không phải cơ chế đồng bộ điều khiển.

Một lối viết có thể phù hợp khi nghiệp vụ chấp nhận dự phòng xếp hàng là:

```java
// Mã minh họa trong một phương thức, chưa phải chương trình độc lập.
// Chính sách: không chuyển ngay được thì chấp nhận xếp hàng để nhận sau.
if (!queue.tryTransfer(item)) {
    queue.put(item);
}
```

Phải hiểu chính sách ở nhánh sau: nó từ bỏ yêu cầu nhận ngay và cho phép giữ dữ liệu. Đây không còn là một quy tắc “không có bên nhận thì từ chối”.

Nếu cần ưu tiên, hạn thời gian hoặc giới hạn dữ liệu tồn, nhánh dự phòng phải đáp ứng những yêu cầu ấy thay vì chỉ bảo đảm lời gọi có vẻ thành công.

## 7. Dung lượng, áp lực ngược và khả năng tiến triển

### 7.1. SynchronousQueue buộc bên gửi gặp bên nhận, nhưng chưa giới hạn mọi tài nguyên

Khi bên sản xuất gọi `put`, nó không thể gửi trước nhiều phần tử vào một vùng đệm nội bộ. Đây là điểm chuyển giao buộc nguồn phối hợp với bên nhận.

Tuy nhiên, nếu ứng dụng liên tục tạo tác vụ hoặc luồng sản xuất mới, mỗi tác vụ đang chờ vẫn có thể giữ một đối tượng công việc. Công việc tồn đã chuyển từ một hàng đợi phần tử sang các tác vụ bị giữ.

Vì vậy, không thể kết luận “capacity bằng 0 nên hệ thống không thể tích lũy dữ liệu”. Cần kiểm soát cả số bên gửi hoạt động, kích thước công việc và số việc đang xử lý.

### 7.2. LinkedTransferQueue không có giới hạn capacity mặc định để chống tích lũy

Gửi qua `put` hoặc `offer` trên `LinkedTransferQueue` cho phép nguồn đi trước bên nhận. Nếu nguồn nhanh hơn trong thời gian dài, dữ liệu chờ có thể tăng cho đến khi tài nguyên không còn đáp ứng.

Dùng `transfer` khiến một bên sản xuất chờ được nhận cho từng lần gửi. Nhưng nếu có rất nhiều bên sản xuất độc lập, hoặc bên tiêu thụ lấy xong lại đẩy công việc sang nơi khác không giới hạn, tổng tải chưa chắc đã được giới hạn theo ý định.

Muốn giới hạn số công việc chưa hoàn tất đến lúc xử lý xong, ranh giới cấp quyền phải kéo dài qua cả giai đoạn xử lý và hoàn tất. Chỉ điều kiện “đã nhận” là một ranh giới sớm hơn.

### 7.3. Ai có thể làm lời gọi đang chờ hoàn tất?

Một thiết kế có thể không tiến triển nếu gửi và nhận bị xếp sai tài nguyên. Ví dụ suy luận:

```text
Nhóm thực thi chỉ có một luồng.
Tác vụ gửi bắt đầu: transfer(work) → chờ người nhận.
Tác vụ nhận được xếp sau trong cùng nhóm.
Không còn luồng rảnh để chạy tác vụ nhận.
```

Thay `transfer` bằng `SynchronousQueue.put` vẫn có cùng quan hệ chờ. Cần cho đối tác có thể chạy, hoặc đổi giao thức.

Một tình huống khác: bên gửi giữ khóa L rồi chờ người nhận, trong khi người nhận phải lấy khóa L mới đi đến lời gọi nhận. Cấu trúc chuyển giao không thể tự giải phóng khóa ngoài của ứng dụng.

Trước khi chọn một phương thức chờ, cần xác định đối tác nào có thể xuất hiện, đối tác đó cần tài nguyên gì và liệu những tài nguyên ấy có bị bên chờ giữ hay không.

## 8. Thứ tự, tính nhìn thấy dữ liệu và vòng đời

### 8.1. Đừng gán một thứ tự toàn cục chưa được hứa

`SynchronousQueue` có tùy chọn công bằng khi tạo. Bật cờ cho chính sách cấp quyền FIFO cho các bên chờ theo hợp đồng lớp; mặc định không hứa thứ tự công bằng đó.

Điều này không làm mọi bên xử lý hoàn tất theo thứ tự đã nhận. Hai công việc có độ dài xử lý khác nhau vẫn có thể hoàn tất ngược nhau.

Với `LinkedTransferQueue`, hợp đồng mô tả FIFO đối với từng bên sản xuất. Trong dữ liệu A, B, C của chương trình chỉ có một bên gửi nên thứ tự dễ kiểm chứng. Với nhiều bên gửi, không suy ra thứ tự số mã, thời gian nghiệp vụ hay thứ tự hoàn tất từ một danh sách kết quả quan sát được.

Nếu thứ tự toàn cục là yêu cầu nghiệp vụ, hãy định nghĩa mốc và cách xác lập nó; không chỉ dựa vào tên queue.

### 8.2. Điểm chuyển giao bảo đảm tính nhìn thấy theo chiều gửi sang nhận

Các hành động trước khi đặt đối tượng vào hàng đợi đồng thời có quan hệ happens-before với hành động sau khi luồng khác truy cập hoặc lấy phần tử đó. Bên gửi nên hoàn tất xây dựng dữ liệu trước khi chuyển giao. Xem [bảo đảm bộ nhớ của BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Hàng đợi chuyển tham chiếu, không tự sao chép sâu. Nếu bên gửi tiếp tục sửa dữ liệu sau khi gửi và bên nhận cùng đọc hoặc sửa, cần quy tắc sở hữu hay đồng bộ cho chính dữ liệu đó.

Không suy ra chiều ngược rằng mọi cập nhật trong phần xử lý của bên nhận đã được bên gửi nhìn thấy chỉ vì `transfer` kết thúc. Phần xử lý có thể còn chưa chạy.

Trong ví dụ phản hồi, future là một cơ chế riêng để công bố kết quả hoàn tất. Hành động của tác vụ có quan hệ happens-before với hành động sau khi lấy kết quả bằng `Future.get()`. Xem [bảo đảm của Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html).

### 8.3. Quan sát LinkedTransferQueue cũng không tạo ảnh chụp giao dịch

`size()` của `LinkedTransferQueue` cần duyệt và không nên được xem như một con số giữ chỗ chính xác trong lúc dữ liệu thay đổi. Iterator có tính nhất quán yếu; các thao tác xử lý nhiều phần tử không tự thành một giao dịch chung.

Cần quan sát đúng mốc: số dữ liệu đang chờ nhận, số bên tiêu thụ đang đợi, số lần gửi đang chờ và số công việc đang xử lý là những đại lượng khác nhau.

Riêng `SynchronousQueue.size()` luôn 0 nên dùng đồ thị số phần tử xếp hàng sẽ không thể hiện các bên gửi đang chờ. Một chỉ số có vẻ “hàng đợi rỗng” không chứng minh hệ thống rảnh.

### 8.4. Nguồn kết thúc phải có giao thức riêng

Hai dạng cấu trúc không tự có một thao tác đóng nguồn chung cho mọi ứng dụng. Có thể cần gián đoạn, tín hiệu kết thúc hoặc một cơ chế quản lý vòng đời rõ.

Với `SynchronousQueue`, tín hiệu kết thúc cũng phải được ghép với người nhận. Nếu người nhận đã dừng, cố `put` tín hiệu không giới hạn có thể làm bên điều phối chờ tiếp.

Với nhiều bên tiêu thụ, một tín hiệu chỉ được một bên nhận. Phải quyết định số tín hiệu, thời điểm mọi bên sản xuất đã hoàn tất và cách xử lý nếu một bên đã hỏng.

Với công việc có future phản hồi, quá trình dừng còn phải giải quyết các phản hồi chưa hoàn tất. Không chỉ làm tác vụ nhận thoát rồi để người gửi chờ mãi.

## 9. Chọn theo mốc cần xác nhận

| Nhu cầu | Hướng phù hợp để xem xét | Điều vẫn cần thêm |
|---|---|---|
| Chuyển trực tiếp, không giữ phần tử trong vùng đệm giữa hai bên | `SynchronousQueue` | Đối tác phải có khả năng chạy; chính sách hủy/dừng |
| Đôi khi chỉ xếp hàng, đôi khi chờ được nhận | `TransferQueue` với cài đặt phù hợp, chẳng hạn `LinkedTransferQueue` | Chọn đúng phương thức và giới hạn tải ở mức ứng dụng |
| Chỉ chấp nhận khi chuyển ngay được cho bên đang chờ | `tryTransfer(e)`, hoặc `SynchronousQueue.offer(e)` theo cấu trúc đang dùng | Xử lý rõ nhánh thất bại |
| Chờ người nhận trong một khoảng | `tryTransfer` có timeout, hoặc timed `offer` của SynchronousQueue | Ngân sách thời gian và nhánh gián đoạn |
| Cần dữ liệu được xếp chờ với dung lượng hữu hạn | Một hàng đợi có giới hạn phù hợp | Chính sách đầy và vận hành |
| Cần kết quả xử lý | Giao thức phản hồi, ví dụ future trong thông điệp | Hoàn tất cả đường thành công, lỗi, hủy |
| Cần độ bền sau khi tiến trình dừng | Nguồn lưu trữ hoặc hệ thống thông điệp phù hợp | Quy tắc xác nhận, phục hồi, xử lý lặp |

Bảng không coi một lớp là nhanh hơn hoặc mạnh hơn trong mọi bối cảnh. Cơ chế đúng là cơ chế có mốc hoàn tất khớp với điều bên gọi thực sự cần biết.

Một vài lỗi gọi API nên nhận ra ngay:

- Gọi `offer` có timeout trên `LinkedTransferQueue` rồi tưởng đã chờ người nhận.
- Gọi `tryTransfer` thất bại nhưng tưởng phần tử vẫn được giữ để nhận sau.
- Dùng `hasWaitingConsumer` như một quyền giữ trước người nhận.
- Coi `transfer` hoàn tất là bằng chứng xử lý đã thành công.
- Coi `size=0` của `SynchronousQueue` là hệ thống không có tác vụ đang chờ.
- Dừng hoặc gửi lại công việc mà không biết nó đã được nhận hay chưa.

Những lỗi này chủ yếu là nhầm trạng thái và trách nhiệm. Tên phương thức chỉ hữu ích khi được nối với đúng mốc trong quy trình.

## 10. Thực hành và tự kiểm tra

### Bài 1: “rỗng” nhưng gửi không được

Tạo một `SynchronousQueue`, gọi `size`, `isEmpty`, rồi thử `offer("A")` khi không có bên nhận.

Vì sao `size=0`, `isEmpty=true` nhưng `offer` lại trả `false`? Nếu thay bằng hàng đợi có vùng đệm còn chỗ, điều kiện nào đã khác?

Hướng giải thích: `SynchronousQueue` không có ô lưu trữ để giữ A. Sự hiện diện của đối tác nhận, không phải số ô còn trống, là điều kiện chuyển giao.

### Bài 2: chọn đúng phép gửi trên LinkedTransferQueue

Không có bên tiêu thụ. Hãy dự đoán sự khác nhau giữa:

1. `put("A")`.
2. `offer("B", 1, SECONDS)`.
3. `tryTransfer("C")`.
4. `tryTransfer("D", 1, SECONDS)`.

Hướng giải thích: A và B có thể được xếp để nhận sau; C không được xếp khi chuyển ngay thất bại; D chờ khả năng chuyển trong một khoảng rồi không bị giữ lại nếu hết thời gian theo hợp đồng lớp.

Không chạy `transfer` không timeout trên cùng một luồng rồi mong đoạn mã phía sau tự đi đến `take`; luồng ấy sẽ không tạo được đối tác cho chính nó.

### Bài 3: nhận chưa là xử lý xong

Giữ cổng xử lý đóng như `ReceiptAndReplyDemo`. Bên gửi đã hoàn tất `transfer`.

Có thể đọc kết quả xử lý từ một biến thường và coi như chắc chắn đã có giá trị mới không? Cơ chế nào trong ví dụ được dùng để công bố phần hoàn tất thực sự?

Hướng giải thích: phần xử lý vẫn chưa được cho phép bắt đầu. Future phản hồi mô hình hóa mốc kết quả riêng; điểm chuyển giao không thay thế mốc đó.

### Bài 4: cuộc đua sau hasWaitingConsumer

Bên P1 thấy `hasWaitingConsumer=true`. Trước khi P1 gửi, P2 chuyển phần tử cho người nhận đó.

Vì sao P1 vẫn có thể chờ nếu gọi `transfer`? Nếu yêu cầu của P1 là chỉ thử chuyển ngay thì phải dùng kết quả của thao tác nào?

Hướng giải thích: quan sát không đặt chỗ. Dùng `tryTransfer` để quyết định chuyển được ngay hay không trong chính thao tác cần thực hiện.

### Bài 5: dừng một quy trình có phản hồi

Nhiều công việc đã được nhận nhưng chưa hoàn tất future. Bên quản lý yêu cầu dừng các bên tiêu thụ.

Cần xử lý gì với những người đang đợi kết quả? Nếu một người đã hết thời gian chờ, có thể tự suy ra công việc đã ngừng chạy không? Nếu gửi lại, làm thế nào nhận diện lần thực hiện trước?

Hướng giải thích: phải quản lý vòng đời xử lý và phản hồi, bao gồm lỗi/hủy. Timeout của bên chờ chưa là xác nhận dừng công việc. Nhận diện và xử lý lặp thuộc giao thức nghiệp vụ.

### Các câu hỏi trước khi chốt một thiết kế chuyển giao

1. Bên gửi cần biết được chấp nhận, được nhận hay xử lý xong?
2. Cấu trúc có vùng đệm không; phương thức đang gọi có chờ việc nhận không?
3. Nếu chuyển thất bại, phần tử còn được giữ ở đâu?
4. Đối tác cần tài nguyên và luồng nào để có thể xuất hiện?
5. Kết quả hết thời gian và gián đoạn được xử lý khác nhau thế nào?
6. Các số đo size hoặc số người chờ có đang bị dùng như quyền giữ chỗ không?
7. Sau khi nhận, ai được phép sửa dữ liệu và ai công bố kết quả?
8. Khi dừng, ai chịu trách nhiệm kết thúc các lần gửi và phản hồi còn chờ?

Khi ba mốc chấp nhận, chuyển giao và xử lý hoàn tất được tách rõ, người học có thể chọn đúng phương thức và giải thích được cả thành công, timeout, hủy lẫn đường dừng của quy trình.
