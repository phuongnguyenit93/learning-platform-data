# SynchronousQueue và chuyển giao trực tiếp

## 1. Mô hình: gặp nhau để trao công việc, không gửi vào kho

Trong nhiều hàng đợi, luồng tạo việc (producer) có thể đặt công việc vào vùng đệm rồi tiếp tục trước khi luồng xử lý (consumer) đến nhận. `SynchronousQueue<E>` chọn một mô hình khác: mỗi lần giao dữ liệu phải ghép với một lần nhận tương ứng. Không có chỗ lưu đệm bên trong, kể cả một chỗ.

Hãy hình dung hai người trao một tài liệu tận tay. Nếu chưa có người nhận, người giao phải chờ hoặc bỏ lần giao theo chính sách đã chọn; không có chiếc khay để đặt tài liệu xuống. Nếu người nhận đến trước, họ cũng có thể chờ người giao. Điểm hai bên ghép được với nhau thường được gọi là điểm hẹn đồng bộ (rendezvous).

`SynchronousQueue` vẫn thực hiện giao diện `BlockingQueue`, nhưng mục đích chính là chuyển giao trực tiếp (direct handoff), không phải tích lũy một danh sách công việc đang chờ. API này vẫn áp dụng trong Java hiện đại; ví dụ trong bài chạy được với Java 17 trở lên.

## 2. Luồng giao và nhận gặp nhau như thế nào?

```text
Trường hợp bên giao đến trước:
Producer: put(job) ----- chờ ----- ghép cặp ------ tiếp tục
Consumer:                    take() --- nhận job -- xử lý

Trường hợp bên nhận đến trước:
Consumer: take() ------- chờ ----- ghép cặp ------ xử lý job
Producer:                    put(job) --- tiếp tục
```

Hai bên không phải bắt đầu ở cùng một thời điểm đồng hồ. Chỉ cần thao tác của chúng có cơ hội ghép với nhau: một bên có thể chờ trước rất lâu. Sau khi chuyển giao thành công, các luồng tiếp tục theo lịch chạy của JVM và hệ điều hành; không có cam kết producer hay consumer sẽ chạy câu lệnh kế tiếp trước.

Producer đưa vào một tham chiếu đối tượng, không tự tạo bản sao độc lập của đối tượng đó. Sau khi `put` thành công, consumer đã nhận phần tử qua thao tác lấy, nhưng chưa chắc đã thực hiện xong nghiệp vụ. Nếu cần biết kết quả xử lý, phải có tín hiệu hoàn tất riêng, chẳng hạn `Future`, `CompletableFuture` hoặc một giao thức phản hồi.

## 3. Ý nghĩa các phương thức giao và nhận

| Thao tác | Khi ghép được bên đối ứng | Khi chưa có bên đối ứng |
| --- | --- | --- |
| `put(e)` | Chuyển `e` cho bên nhận và hoàn tất | Chờ bên nhận, có thể bị ngắt |
| `offer(e)` | Trả `true` nếu giao ngay được cho bên nhận đang chờ | Trả `false`, không để lại `e` cho tương lai |
| `offer(e, timeout, unit)` | Trả `true` nếu giao được trong lần chờ | Hết thời gian mà chưa giao được thì trả `false` |
| `take()` | Nhận phần tử từ bên giao và trả về | Chờ bên giao, có thể bị ngắt |
| `poll()` | Nhận phần tử nếu đang có bên giao cung cấp được | Trả `null` |
| `poll(timeout, unit)` | Trả phần tử nếu nhận được trong lần chờ | Hết thời gian mà chưa nhận được thì trả `null` |

Thao tác có chờ như `put`, `take`, timed `offer` và timed `poll` khai báo `InterruptedException`. `offer` không thời hạn và `poll` không thời hạn chỉ thử ghép ngay; chúng không tự đợi bên kia xuất hiện.

Điểm dễ nhầm là `offer(e)` không luôn trả `false` chỉ vì dung lượng bằng 0: nếu bên nhận phù hợp đang chờ, việc chuyển giao vẫn thành công. Tương tự, `poll()` có thể nhận dữ liệu từ producer đang chờ dù `size()` luôn bằng 0.

`SynchronousQueue` không cho phép phần tử `null`; thêm `null` ném `NullPointerException`. Do đó, `null` do `poll` trả về có nghĩa là lần lấy chưa nhận được dữ liệu, không phải một thông điệp rỗng hợp lệ.

Thời hạn trong timed `offer`/`poll` là giới hạn chờ ghép bên đối ứng, không phải thời gian xử lý dữ liệu. Không diễn giải nó thành bảo đảm cứng rằng mọi công việc sẽ hoàn tất trước đúng mốc đồng hồ. Các hành vi trên được quy định trong [SynchronousQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html).

## 4. Vì sao size luôn bằng 0 mà vẫn có thể có luồng đang chờ?

`SynchronousQueue` hoạt động như một collection rỗng khi quan sát bằng nhiều phương thức collection thông thường:

| Quan sát | Kết quả | Điều không được suy ra |
| --- | --- | --- |
| `size()` | Luôn `0` | Không chứng minh là không có producer đang chờ giao |
| `remainingCapacity()` | Luôn `0` | Không chứng minh một lần `offer` chắc chắn thất bại |
| `isEmpty()` | Luôn `true` | Không chứng minh hệ thống không có công việc đang được chuyển giao hoặc xử lý |
| `peek()` | Luôn `null` | Không dự đoán được kết quả của lần `poll` tiếp theo |
| `iterator()` | Không có phần tử để duyệt | Không phải cách kiểm tra các luồng đang chờ |
| `contains(x)` | Luôn `false` | Không phải bằng chứng rằng `x` chưa từng được chuyển giao |

Luồng đang chờ giao vẫn có thể đang giữ tham chiếu tới dữ liệu cùng những tài nguyên khác. “Không có vùng đệm” không có nghĩa là “không có dữ liệu nào tồn tại trong bộ nhớ” hoặc “không cần cấu trúc đồng bộ nội bộ”.

Đừng viết `if (!queue.isEmpty()) { queue.take(); }` để quyết định nhận: điều kiện luôn sai với `SynchronousQueue`. Nếu muốn thử nhận ngay, gọi `poll()` và kiểm tra kết quả của chính lần gọi. Nếu muốn chờ, gọi `take()` hoặc timed `poll`.

`clear()` không hủy các luồng đang chờ và không có ý nghĩa dọn danh sách công việc tồn đọng, vì không có danh sách đệm như vậy. Để dừng các tác vụ đang chờ, cần một cơ chế hủy riêng.

## 5. Ví dụ chạy đầy đủ: đã nhận khác đã xử lý xong

Chương trình sau minh họa giao thất bại khi chưa có người nhận, sau đó chuyển giao thành công giữa hai luồng. Một tín hiệu riêng cố ý giữ consumer chưa xử lý xong, giúp quan sát khác biệt giữa nhận dữ liệu và hoàn tất công việc.

Lưu trong `DirectHandoffDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class DirectHandoffDemo {
    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected handoff result");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        SynchronousQueue<String> channel = new SynchronousQueue<>();

        System.out.println("size=" + channel.size()
                + ", remaining=" + channel.remainingCapacity());
        check(!channel.offer("no-receiver"));
        System.out.println("offer without receiver: false");
        check(channel.poll() == null);
        System.out.println("poll without sender: null");
        check(!channel.offer("timed", 20, TimeUnit.MILLISECONDS));
        System.out.println("timed offer without receiver: false");

        CountDownLatch receivedSignal = new CountDownLatch(1);
        CountDownLatch allowProcessing = new CountDownLatch(1);
        AtomicReference<String> received = new AtomicReference<>();
        AtomicBoolean processed = new AtomicBoolean(false);

        Thread consumer = new Thread(() -> {
            try {
                String job = channel.take();
                received.set(job);
                receivedSignal.countDown();

                allowProcessing.await();
                processed.set(true);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        channel.put("job-1");
        receivedSignal.await();

        check("job-1".equals(received.get()));
        check(!processed.get());
        System.out.println("received: " + received.get());
        System.out.println("after handoff: processed=" + processed.get());
        System.out.println("after handoff: size=" + channel.size());

        allowProcessing.countDown();
        consumer.join();
        check(processed.get());
        System.out.println("after consumer finishes: processed=" + processed.get());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 DirectHandoffDemo.java
java DirectHandoffDemo
```

Stdout:

```text
size=0, remaining=0
offer without receiver: false
poll without sender: null
timed offer without receiver: false
received: job-1
after handoff: processed=false
after handoff: size=0
after consumer finishes: processed=true
```

Ba phép thử đầu xảy ra trước khi consumer được tạo và không có producer khác, nên kết quả thất bại là xác định. Lần timed `offer` không để lại chuỗi `timed` để consumer lấy về sau. Chương trình không yêu cầu đo được thời gian chính xác bằng 20 ms.

`consumer.start()` chỉ lên lịch cho consumer, không bảo đảm nó đã chạy tới `take()`. Vì main dùng `put`, nếu consumer chưa đến thì main chờ; nếu consumer đến trước thì consumer chờ. Cả hai lịch chạy đều có thể ghép thành công, không cần dùng `sleep` để đoán bên kia đã sẵn sàng.

`receivedSignal` xác nhận consumer đã ghi nhận giá trị vào biến `received`; không dùng nó để thay thế cơ chế chuyển giao. `allowProcessing` giữ bước xử lý lại cho đến khi main đã in `processed=false`. Sau khi mở tín hiệu này và `join()` consumer, main mới kiểm tra `processed=true`.

Ví dụ nhờ đó cho thấy: `put` đã hoàn tất, `size()` vẫn bằng 0, và bước xử lý của consumer vẫn có thể chưa hoàn tất. Không dùng trạng thái hàng đợi để thay thế tín hiệu hoàn tất nghiệp vụ.

## 6. Khác gì hàng đợi có một chỗ?

| Tình huống | `new ArrayBlockingQueue<>(1)` | `new SynchronousQueue<>()` |
| --- | --- | --- |
| Chưa có consumer, producer gọi `offer(A)` | Có thể lưu A vào chỗ trống và trả `true` | Trả `false` nếu không có bên nhận chờ ghép |
| Producer gọi `put(A)` khi chưa có ai nhận | Có thể hoàn tất sau khi đặt A vào vùng đệm | Chờ cho đến khi A được nhận hoặc lời gọi bị ngắt |
| Sau khi thêm thành công và consumer chưa lấy | Có thể quan sát `size()==1` | Không có trạng thái giữ A như phần tử đệm |
| Nhu cầu chính | Tách thời điểm sản xuất và tiêu thụ bằng một vùng đệm nhỏ | Ghép trực tiếp một lần giao với một lần nhận |

`SynchronousQueue` không phải `ArrayBlockingQueue` có dung lượng 1. Cũng không tạo nó bằng cách truyền số 0 cho `ArrayBlockingQueue`, vì constructor đó yêu cầu dung lượng dương.

Một vùng đệm giúp hấp thụ một khoảng chênh nhịp ngắn giữa hai bên. Chuyển giao trực tiếp buộc producer phải gặp khả năng nhận ngay trong giao thức; đây có thể là điều mong muốn khi không muốn tích lũy công việc ở tầng đó.

## 7. Công bằng giữa các luồng chờ

```java
// Đoạn khai báo minh họa.
SynchronousQueue<String> normal = new SynchronousQueue<>();
SynchronousQueue<String> fair = new SynchronousQueue<>(true);
```

Mặc định là chính sách không công bằng (`fair=false`), không bảo đảm thứ tự phục vụ các luồng đang chờ. Với `fair=true`, các luồng chờ được cạnh tranh quyền tiếp cận theo FIFO.

Đừng dựa vào một thứ tự cụ thể trong chế độ mặc định chỉ vì một vài lần chạy in ra cùng kết quả. Cũng không dùng `fair=true` để kết luận mọi nghiệp vụ sẽ hoàn tất theo thứ tự bắt đầu: công bằng lúc ghép không kiểm soát thời gian xử lý sau khi nhận, tốc độ từng consumer hay lịch chạy tiếp theo.

## 8. Chờ, hủy và vòng phụ thuộc khiến hệ thống đứng lại

Đoạn sau không tạo một cuộc chuyển giao hợp lệ giữa hai bên độc lập:

```java
// Đoạn minh họa lỗi: cùng một luồng làm cả hai bước liên tiếp.
SynchronousQueue<String> queue = new SynchronousQueue<>();
queue.put("work");
String value = queue.take();
```

Nếu không có luồng khác nhận, luồng hiện tại chờ ở `put` và không chạy đến được `take`. Đây là khác biệt thiết yếu so với việc đưa một phần tử vào hàng đợi có vùng đệm còn trống.

Một biến thể khó thấy hơn xảy ra khi chỉ có một luồng trong bộ thực thi: tác vụ producer đang chiếm luồng đó và chờ ở `put`, còn tác vụ consumer chưa được chạy. Việc đã nộp consumer vào cùng bộ thực thi không có nghĩa là consumer đang có luồng để chạy.

`take()` cũng có thể chờ mãi nếu mọi producer đã kết thúc mà không có giao thức dừng. Hàng đợi không cung cấp thao tác `close()` tích hợp để tự báo hết dữ liệu. Nếu dùng thông điệp kết thúc, cần nhớ chính thông điệp đó cũng phải gặp người nhận; nó không được gửi trước rồi nằm lại trong vùng đệm.

Khi bắt `InterruptedException`, hãy làm theo chính sách hủy của tác vụ: chuyển ngoại lệ lên nếu được, hoặc khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` và kết thúc tác vụ nếu đó là cách hủy đã chọn. Không nuốt ngoại lệ rồi lặp lại vô hạn. Khi ứng dụng cần khả năng thử và từ bỏ, timed `offer`/`poll` thường giúp biểu diễn rõ một lần chờ có giới hạn.

## 9. Dữ liệu được công bố an toàn, nhưng đối tượng không tự bất biến

Những thay đổi được producer thực hiện trước khi giao đối tượng qua `BlockingQueue` được công bố cho consumer theo hợp đồng nhất quán bộ nhớ của concurrent collection. Consumer không cần tự thêm `volatile` cho từng trường chỉ để đọc trạng thái đã được chuẩn bị trước lần giao thành công.

Tuy nhiên, nếu producer tiếp tục sửa đối tượng sau khi giao trong khi consumer cũng đọc/sửa nó, cơ chế hàng đợi không tự bảo vệ các thay đổi về sau. Cần chọn rõ quyền sở hữu sau chuyển giao, dùng dữ liệu bất biến hoặc đồng bộ riêng. Nhận một tham chiếu an toàn không biến mọi hành vi tương lai trên đối tượng thành an toàn.

## 10. Một ứng dụng: giao tác vụ trực tiếp trong ThreadPoolExecutor

`SynchronousQueue` có thể làm hàng đợi tác vụ cho `ThreadPoolExecutor`. Khi không thể giao trực tiếp tác vụ cho worker đang chờ, executor có thể tạo worker mới nếu chưa vượt `maximumPoolSize`; nếu không thể tiếp nhận tiếp theo cấu hình và trạng thái của nó thì đi vào chính sách từ chối.

Điều này không có nghĩa `execute()` tự chờ `put` cho đến khi worker rảnh. Cũng không có nghĩa không có vùng đệm thì không thể quá tải: cấu hình cho phép tăng số luồng rất lớn có thể chuyển sự tăng trưởng từ số việc đệm sang số luồng. Cần chọn giới hạn luồng và hành vi từ chối theo nhu cầu thực tế; xem phần direct handoff trong [ThreadPoolExecutor — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

## 11. Tự kiểm tra

1. `size()==0` có chứng minh `offer(x)` sẽ thất bại không? Không; một consumer đang chờ có thể nhận trực tiếp.
2. Timed `offer(x, ...)` trả `false`. Một consumer đến sau có lấy được `x` từ lần gửi đó không? Không; lần giao đó không lưu `x` lại.
3. `put(x)` hoàn tất có đồng nghĩa công việc đã xử lý thành công không? Không; nó xác nhận chuyển giao, không xác nhận kết quả nghiệp vụ.
4. `peek()==null` có chứng minh lần `poll()` ngay sau chắc chắn không nhận được gì không? Không; `peek` luôn trả `null` còn `poll` có thể ghép với bên giao.
5. Vì sao dùng một luồng gọi `put` rồi `take` có thể đứng lại ngay câu đầu? Vì `put` cần một bên nhận khác đang thực hiện thao tác tương ứng.
6. Dung lượng đệm bằng 0 có bảo đảm tổng bộ nhớ hoặc tổng số luồng bị giới hạn không? Không; các luồng đang chờ và dữ liệu chúng giữ vẫn tiêu thụ tài nguyên.
