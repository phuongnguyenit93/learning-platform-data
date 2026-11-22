# So sánh `add`, `offer`, `put` và `offer` có thời hạn

## 1. Cùng đưa dữ liệu vào hàng đợi, khác cách xử lý khi chưa có chỗ

`BlockingQueue<E>` là hàng đợi an toàn khi nhiều luồng cùng truy cập, thường nối bên tạo công việc với bên xử lý công việc. Với hàng đợi có giới hạn dung lượng, bên tạo có thể nhanh hơn bên xử lý: hàng đợi đầy và chưa thể nhận phần tử tiếp theo. Chọn phương thức thêm phần tử chính là chọn cách bên tạo phản ứng với tình huống đó.

Bốn phương thức đều đưa phần tử vào hàng đợi khi có thể; khác biệt chính nằm ở việc báo thất bại hay chờ chỗ trống:

| Phương thức | Khi có chỗ | Khi đầy do giới hạn dung lượng | Kết quả bình thường | Có khai báo `InterruptedException`? |
| --- | --- | --- | --- | --- |
| `add(e)` | Thêm phần tử | Ném `IllegalStateException` | `true` | Không |
| `offer(e)` | Thêm phần tử | Trả về `false` | `true` hoặc `false` | Không |
| `put(e)` | Thêm phần tử | Chờ đến khi có thể thêm | `void` | Có |
| `offer(e, timeout, unit)` | Thêm phần tử | Chờ chỗ trống trong khoảng thời gian cho phép; hết thời gian mà chưa thêm được thì trả `false` | `true` hoặc `false` | Có |

Đây là hợp đồng đang được dùng trong [Java SE `BlockingQueue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html). Không cần dùng API lỗi thời để thực hành nội dung này.

Trong bài, dùng `ArrayBlockingQueue` để có một hàng đợi giới hạn rõ ràng. Nó lưu phần tử theo thứ tự vào trước, ra trước (FIFO); dung lượng được cố định khi tạo. Đối chiếu tại [Java SE `ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html). Không suy ra mọi lớp triển khai `BlockingQueue` đều dùng FIFO hoặc đều có cùng giới hạn.

## 2. `add(e)`: không thêm được là một lỗi cần báo

Chữ ký:

```java
boolean add(E e)
```

Nếu còn chỗ, `add` thêm phần tử và trả `true`. Nếu không thêm được do dung lượng hiện tại, nó ném `IllegalStateException`; nó không trả `false` để biểu diễn tình huống đầy.

Dùng `add` khi việc hàng đợi đầy cho thấy một giả định của chương trình đã bị phá vỡ, chẳng hạn nạp số phần tử đã biết vào vùng đệm có đủ dung lượng. Nếu đầy là điều bình thường trong luồng xử lý, `offer` thường thể hiện ý định rõ hơn việc liên tục ném rồi bắt ngoại lệ.

Đoạn minh họa, chưa phải chương trình độc lập:

```java
BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
queue.add("A");
queue.add("B"); // IllegalStateException vì A vẫn chiếm chỗ duy nhất
```

Ngoại lệ ở dòng cuối không loại `A` ra và cũng không tự xếp `B` vào một danh sách chờ. Nếu muốn xử lý lại `B`, chương trình phải quyết định cách làm.

## 3. `offer(e)`: thử thêm, dùng kết quả để quyết định

Chữ ký:

```java
boolean offer(E e)
```

`offer(e)` không chờ chỗ trống khi hàng đợi đầy. Nó trả `true` nếu phần tử đã được nhận, `false` nếu chưa được nhận do thiếu chỗ tại lần thử đó.

Điều này phù hợp khi bên gọi có thể phản ứng ngay: từ chối nhận thêm, ghi số liệu quá tải, chuyển công việc sang nơi khác hoặc bỏ qua một cập nhật được phép bỏ. Không được tự hiểu rằng mọi công việc đều có thể bỏ.

Đoạn minh họa:

```java
if (!queue.offer(job)) {
    // job chưa vào hàng đợi: phải xử lý kết quả này theo yêu cầu ứng dụng.
    reportOverload(job);
}
```

Ở đây `queue`, `job`, `reportOverload` thuộc mã ứng dụng, không phải chương trình hoàn chỉnh. Điểm cần học là nhánh `false` phải có ý nghĩa nghiệp vụ. Viết `queue.offer(job);` rồi bỏ qua kết quả có thể làm công việc bị mất khỏi luồng xử lý mà bên gọi vẫn tưởng đã tiếp nhận.

Không chờ chỗ trống không đồng nghĩa với không bao giờ chờ ở cấp triển khai. Ví dụ một phương thức có thể phải giành khóa nội bộ trong lúc có tranh chấp. Vì vậy không dùng từ “tức thời” như một bảo đảm độ trễ tuyệt đối, và không xem `offer` là thuật toán không khóa.

## 4. `put(e)`: bên tạo chờ để hàng đợi nhận được phần tử

Chữ ký:

```java
void put(E e) throws InterruptedException
```

`put` thích hợp khi cần truyền áp lực ngược (backpressure): hàng đợi đầy khiến bên tạo chậm lại, thay vì tiếp tục dồn thêm dữ liệu. Nó không trả cờ thành công; khi lời gọi trở về bình thường, phần tử đã được đưa vào hàng đợi.

Trong thời gian chờ, luồng bị tạm dừng để đợi điều kiện phù hợp, không cần tự viết vòng lặp kiểm tra dung lượng liên tục. Khi bên xử lý lấy phần tử ra, một bên tạo có thể tiến hành thêm. Nếu có nhiều bên tạo cạnh tranh, một chỗ vừa trống không bảo đảm thuộc về luồng cụ thể nào theo hợp đồng giao diện.

`put` không có thời hạn chờ do người gọi truyền vào. Nếu không có ai giải phóng chỗ và luồng không bị ngắt, nó có thể chờ mãi. Tính an toàn khi truy cập đồng thời không bảo đảm toàn bộ chương trình sẽ luôn tiến triển.

Đoạn sau có thể treo ngay ở dòng thứ hai trong một chương trình chỉ có luồng này:

```java
queue.put("A"); // Giả sử queue có dung lượng 1 và ban đầu trống.
queue.put("B"); // Đợi chỗ, nhưng cùng luồng chưa thể chạy đến take bên dưới.
queue.take();
```

Muốn dùng `put`, cần bảo đảm bên xử lý có thể chạy độc lập. Cũng cần kiểm tra trường hợp các luồng dùng chung một nhóm luồng đều bị giữ lại để chờ thêm, trong khi các tác vụ lấy dữ liệu còn nằm trong chính nhóm luồng đó và chưa có cơ hội chạy.

## 5. `offer(e, timeout, unit)`: chỉ dành một khoảng chờ cho việc tiếp nhận

Chữ ký:

```java
boolean offer(E e, long timeout, TimeUnit unit)
        throws InterruptedException
```

Phương thức trả `true` nếu thêm được phần tử; trả `false` nếu khoảng chờ kết thúc mà chưa thêm được. Nếu bị ngắt trong lúc chờ, nó có thể kết thúc bằng `InterruptedException`, không phải bằng `false`.

Ví dụ minh họa một chính sách tiếp nhận:

```java
boolean accepted = queue.offer(job, 200, TimeUnit.MILLISECONDS);
if (!accepted) {
    reportOverload(job);
}
```

Nếu hàng đợi có chỗ ngay, phương thức không cố tình ngủ đủ 200 ms. Nếu chỗ trống xuất hiện sớm, nó có thể thành công sớm. Nếu không xuất hiện chỗ, bên gọi nhận `false` sau khi khoảng chờ cho phép đã hết và luồng được lập lịch để tiếp tục chạy.

Không lấy 200 ms làm cam kết rằng hàm sẽ trả về đúng ở mốc 200 ms theo đồng hồ: lập lịch luồng, tranh chấp và công việc thực tế trong triển khai ảnh hưởng đến thời điểm quan sát được. Cũng không dùng thời gian này để giới hạn thời gian xử lý `job`: nó chỉ liên quan đến bước đưa công việc vào hàng đợi.

Với `ArrayBlockingQueue`, thời hạn bằng 0 hoặc âm không tạo một khoảng đợi chỗ trống dương: lần thử vẫn có thể thành công nếu còn chỗ. Tuy vậy, lời gọi có thời hạn vẫn có hợp đồng ngắt luồng và không nên được xem là hoàn toàn đồng nhất với `offer(e)` trong mọi tình huống.

## 6. Ví dụ chạy được: quan sát đủ bốn cách

Lưu nguyên chương trình vào `QueueInsertDemo.java`. Chương trình dùng cú pháp và API chạy trên Java 17 trở lên.

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public class QueueInsertDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);

        System.out.println("add A: " + queue.add("A"));
        try {
            queue.add("B");
        } catch (IllegalStateException ex) {
            System.out.println("add B: " + ex.getClass().getSimpleName());
        }

        System.out.println("offer B: " + queue.offer("B"));
        System.out.println("timed offer B: "
                + queue.offer("B", 20, TimeUnit.MILLISECONDS));
        System.out.println("take: " + queue.take());

        System.out.println("timed offer C: "
                + queue.offer("C", 20, TimeUnit.MILLISECONDS));

        CountDownLatch started = new CountDownLatch(1);
        FutureTask<Void> insertion = new FutureTask<>(() -> {
            started.countDown();
            queue.put("D");
            return null;
        });
        Thread producer = new Thread(insertion, "producer");
        producer.start();
        started.await();

        // C còn trong queue: put D chỉ có thể hoàn thành sau khi C bị lấy ra.
        System.out.println("before freeing slot: " + queue.peek());
        System.out.println("take: " + queue.take());
        insertion.get();
        producer.join();
        System.out.println("after put: " + queue.take());
        System.out.println("empty: " + queue.isEmpty());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 QueueInsertDemo.java
java QueueInsertDemo
```

Kết quả chuẩn:

```text
add A: true
add B: IllegalStateException
offer B: false
timed offer B: false
take: A
timed offer C: true
before freeing slot: C
take: C
after put: D
empty: true
```

Giải thích thứ tự quan sát:

1. `A` chiếm chỗ duy nhất nên `add B` báo lỗi, hai lần `offer B` đều không nhận được `B`. Trong khoảng thử có thời hạn, không có luồng nào lấy `A` ra.
2. Luồng chính lấy `A`, nên `offer` có thời hạn nhận `C` ngay khi còn chỗ.
3. Luồng tạo thực hiện `put D`. Vì `C` vẫn chiếm chỗ, `D` không thể được thêm trước khi luồng chính lấy `C` ra.
4. `insertion.get()` chờ tác vụ thêm hoàn tất và chuyển ngoại lệ của tác vụ về luồng chính nếu có. Sau đó lấy ra `D` và hàng đợi trống.

`CountDownLatch` chỉ thông báo luồng tạo đã đi đến điểm trước `put`; nó không chứng minh luồng đó đã chuyển sang trạng thái chờ ở đúng một thời điểm. Ví dụ không dùng `sleep` để đoán thứ tự luồng, không in từ hai luồng cạnh tranh, và không phụ thuộc vào thời lượng chính xác của lần chờ 20 ms để tạo stdout.

## 7. Ngắt luồng là một kết quả cần xử lý riêng

`put` và `offer` có thời hạn khai báo `InterruptedException`. Đây là đường hủy/chấm dứt việc chờ, khác với việc `offer` trả `false` do hết thời gian.

Ở lớp có thể để bên gọi quyết định, truyền ngoại lệ ra ngoài. Phương thức sau là đoạn mã để đặt trong một lớp Java phù hợp:

```java
static boolean enqueue(BlockingQueue<String> queue, String job)
        throws InterruptedException {
    return queue.offer(job, 200, TimeUnit.MILLISECONDS);
}
```

Ở biên của `Runnable`, nếu quyết định ngừng công việc sau khi bị ngắt, khôi phục cờ ngắt rồi thoát:

```java
Runnable producer = () -> {
    try {
        queue.put(job);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }
};
```

Đoạn này giả định `queue` và `job` là các biến đã khai báo, có thể được lambda sử dụng. Không bắt `InterruptedException` rồi lập tức lặp lại mãi mà bỏ qua yêu cầu dừng. Cũng không biến mọi trường hợp bị ngắt thành thông báo “queue đầy”: đó là hai sự kiện khác nhau.

## 8. Giới hạn và lỗi dễ nhầm

### Phần tử không hợp lệ không được biến thành `false`

`BlockingQueue` không nhận phần tử `null`: thử thêm `null` gây `NullPointerException`. `offer` trả `false` cho trường hợp không có chỗ, không có nghĩa nó bắt và che mọi lỗi đầu vào. Kiểu phần tử hoặc ràng buộc riêng của lớp triển khai cũng có thể gây ngoại lệ tương ứng. Đối số `TimeUnit` phải là giá trị hợp lệ, chẳng hạn `TimeUnit.MILLISECONDS`.

### Không kiểm tra chỗ trước rồi mặc định lần thêm sẽ thành công

Đoạn sau có khoảng đua giữa kiểm tra và hành động:

```java
if (queue.remainingCapacity() > 0) {
    queue.add(job);
}
```

Luồng khác có thể lấy mất chỗ trước khi `add` chạy. Nếu yêu cầu là thử tiếp nhận rồi phản hồi ngay, gọi `offer(job)` và dựa vào chính kết quả của thao tác đó. Sự an toàn của từng thao tác không biến hai thao tác riêng thành một thao tác nguyên tử.

### Chọn đúng loại hàng đợi trước khi bàn về “đầy”

`ArrayBlockingQueue` giúp quan sát tình huống đầy vì có dung lượng hữu hạn cố định. Với một hàng đợi không đặt giới hạn dung lượng hữu dụng cho ứng dụng, bên tạo có thể không bị chậm lại theo cách mong muốn; lượng dữ liệu chờ có thể gây áp lực bộ nhớ. Đổi `offer` thành `put` không tự tạo ra giới hạn dung lượng còn thiếu.

### Thêm thành công khác với xử lý thành công

`true` hoặc việc `put` trở về bình thường chỉ nói rằng phần tử đã được đưa vào hàng đợi. Chúng không bảo đảm bên xử lý đã lấy phần tử, xử lý xong, lưu dữ liệu bền vững hay trả kết quả. Một luồng khác thậm chí có thể lấy phần tử ra ngay sau khi nó được thêm, trước khi bên tạo kiểm tra lại `size()`.

### Không dùng vòng lặp thử lại gây quay bận

```java
while (!queue.offer(job)) {
    // Không làm gì: có thể tiêu tốn CPU khi hàng đợi luôn đầy.
}
```

Nếu chính sách là chờ chỗ, dùng `put`; nếu chỉ chờ một khoảng cho phép, dùng `offer` có thời hạn. Nếu cần thử lại theo chính sách riêng, phải có giới hạn và cách chờ/hủy phù hợp, thay vì quay bận vô hạn.

## 9. Cách chọn trong một tình huống thực tế

Giả sử các luồng đọc dữ liệu đưa công việc vào hàng đợi, còn các luồng xử lý lấy công việc ra:

| Yêu cầu đối với bên tạo | Lựa chọn thể hiện ý định |
| --- | --- |
| Hàng đợi đầy cho thấy một giả định của chương trình sai | `add` và xử lý lỗi ở mức phù hợp |
| Không dành thời gian đợi chỗ; cần biết ngay công việc có được nhận hay không | `offer` và xử lý nhánh `false` |
| Chấp nhận chậm lại cho đến khi có chỗ, đồng thời hỗ trợ ngắt việc chờ | `put` |
| Chỉ chấp nhận đợi tiếp nhận trong một khoảng cho phép | `offer` có thời hạn, xử lý cả `false` và `InterruptedException` |

Hãy quyết định trước công việc chưa được nhận sẽ đi đâu và ai chịu trách nhiệm với nó. Sau đó chọn phương thức biểu diễn đúng quyết định ấy. Bốn tên phương thức không thay thế cho một chính sách xử lý quá tải rõ ràng.

## 10. Tự kiểm tra

1. Hàng đợi dung lượng 1 đang chứa `A`. `offer("B")` trả `false`: `B` đã được giữ lại để thêm sau chưa?
2. `offer("B", 1, TimeUnit.SECONDS)` gặp chỗ trống sau một khoảng rất ngắn: có phải đợi hết một giây mới trả về không?
3. Vì sao `put` trong cùng luồng với thao tác lấy phần tử có thể khiến chương trình không tiến triển?
4. `offer` trả `true` có chứng minh công việc đã xử lý thành công không?
5. Vì sao `remainingCapacity()` không phải một cách đặt chỗ trước?

Gợi ý trả lời: (1) Chưa, `B` không được thêm. (2) Không, có thể thêm và trả về sớm. (3) Luồng bị giữ ở `put`, chưa thể chạy tới thao tác giải phóng chỗ. (4) Không, mới chỉ tiếp nhận vào hàng đợi. (5) Giá trị quan sát có thể thay đổi vì luồng khác trước lần thêm thực tế.
