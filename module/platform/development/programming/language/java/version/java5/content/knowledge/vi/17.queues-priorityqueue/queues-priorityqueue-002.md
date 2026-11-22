# Phân biệt add, offer và cách biểu diễn thất bại

`Queue` cung cấp hai cách đưa một phần tử vào hàng đợi: `add(e)` và `offer(e)`. Cả hai đều có thể thêm thành công và trả `true`. Khác biệt quan trọng nằm ở cách biểu diễn việc **không thể thêm vì giới hạn dung lượng**:

- `add(e)` ném `IllegalStateException`.
- `offer(e)` trả `false`.

`offer` phù hợp khi hàng đợi đầy là tình huống bình thường mà chương trình cần xử lý theo một nhánh điều khiển rõ ràng. Tuy nhiên, `false` không thay thế mọi ngoại lệ: phần tử không hợp lệ vẫn có thể gây lỗi.

## 1. Cùng mục đích, khác hợp đồng thất bại

Hai phương thức đều có kiểu trả về `boolean`:

```java
boolean add(E element);
boolean offer(E element);
```

Đây là chữ ký minh họa của API, không phải mã đặt trực tiếp vào một lớp triển khai thông thường.

| Tình huống | add(e) | offer(e) |
| --- | --- | --- |
| Thêm được phần tử hợp lệ | Trả `true` | Trả `true` |
| Hàng đợi giới hạn dung lượng không còn chỗ | Ném `IllegalStateException` | Trả `false` |
| Phần tử null nhưng triển khai cấm null | Có thể ném `NullPointerException` | Có thể ném `NullPointerException` |
| Kiểu phần tử không được triển khai chấp nhận | Có thể ném `ClassCastException` | Có thể ném `ClassCastException` |
| Thuộc tính phần tử vi phạm điều kiện thêm | Có thể ném `IllegalArgumentException` theo hợp đồng triển khai | Có thể ném `IllegalArgumentException` theo hợp đồng triển khai |

Các lỗi đầu vào phụ thuộc loại hàng đợi và điều kiện cụ thể. Không dùng bảng này để kết luận mọi triển khai đều kiểm tra mọi lỗi theo cùng thứ tự.

Với hợp đồng thêm phần tử của `Queue`, `add` không dùng `false` để báo hàng đợi đầy. Việc cả hai đều trả `boolean` không có nghĩa mọi giá trị trả về đều có cùng vai trò.

## 2. Vì sao cần offer?

Giả sử một hệ thống tiếp nhận công việc chỉ lưu tối đa 100 công việc đang chờ. Việc công việc thứ 101 chưa có chỗ có thể là trạng thái vận hành dự kiến.

Cách diễn đạt tự nhiên:

```java
// Đoạn minh họa, giả sử pending và job đã được khai báo.
if (pending.offer(job)) {
    System.out.println("accepted");
} else {
    System.out.println("queue full; apply the rejection policy");
}
```

Nhánh `else` cần tương ứng với chính sách thật: báo từ chối cho bên gửi, lưu nơi khác, bỏ theo quy định hoặc thử lại với giới hạn phù hợp. Nếu bỏ qua giá trị trả về, chương trình có thể tưởng công việc đã được tiếp nhận trong khi hàng đợi không có nó.

Với `add`, bên gọi thể hiện kỳ vọng rằng việc không thêm được là lỗi cần đi qua luồng ngoại lệ:

```java
// Đoạn minh họa, không phải chương trình độc lập.
try {
    pending.add(job);
} catch (IllegalStateException e) {
    System.out.println("queue capacity was exceeded");
}
```

Cả hai đều có thể dùng được về mặt kỹ thuật. Quyết định tốt dựa trên ý nghĩa thất bại trong hợp đồng hệ thống, không chỉ dựa vào việc muốn ít dòng mã hơn.

## 3. PriorityQueue: không có giới hạn cứng do initialCapacity đặt ra

`PriorityQueue` sắp xếp phần tử theo thứ tự tự nhiên hoặc `Comparator`. Với kiểu số và thứ tự mặc định, phần tử nhỏ nhất ở đầu hàng đợi.

Điểm cần lưu ý với `add` và `offer`:

- `PriorityQueue` không có giới hạn dung lượng cố định theo hợp đồng như một hàng đợi bounded.
- Dung lượng lưu trữ bên trong tự tăng khi cần.
- Đối số `initialCapacity` là dung lượng ban đầu, không phải số phần tử tối đa.
- Với phần tử hợp lệ được thêm thành công, cả `add` và `offer` đều trả `true`.

Ví dụ:

```java
java.util.Queue<Integer> queue = new java.util.PriorityQueue<>(1);
queue.offer(30);
queue.offer(10);
queue.add(20);
```

Ba phần tử vẫn được thêm dù dung lượng ban đầu là 1. Không nên dùng `new PriorityQueue<>(100)` rồi kỳ vọng `offer` tự trả `false` ở phần tử thứ 101.

“Không giới hạn” trong hợp đồng này không phải bảo đảm bộ nhớ vô hạn. Việc cấp phát vẫn phụ thuộc tài nguyên JVM; không thiết kế cơ chế kiểm soát tải dựa trên hy vọng hệ thống sẽ báo hết bộ nhớ để từ chối công việc.

Thứ tự thêm cũng không biến `PriorityQueue` thành FIFO. Muốn quan sát thứ tự ưu tiên, dùng `poll` liên tiếp; không dùng thứ tự iterator hoặc kết quả `toString()` làm bằng chứng rằng toàn bộ hàng đợi đã được sắp xếp để duyệt tuần tự.

## 4. Ví dụ hoàn chỉnh: thấy rõ true, false và ngoại lệ

Chương trình dưới đây dùng:

- `PriorityQueue` để thấy dung lượng ban đầu không phải giới hạn cứng.
- `ArrayBlockingQueue` dung lượng 2 để tạo tình huống đầy có kết quả xác định.
- Cả hai loại hiện vẫn được dùng trong Java; ví dụ chạy trên Java 17+.

Lưu thành `QueueInsertionDemo.java`:

```java
import java.util.PriorityQueue;
import java.util.Queue;
import java.util.concurrent.ArrayBlockingQueue;

public class QueueInsertionDemo {
    public static void main(String[] args) {
        Queue<Integer> priority = new PriorityQueue<>(1);
        System.out.println("priority offer 30: " + priority.offer(30));
        System.out.println("priority offer 10: " + priority.offer(10));
        System.out.println("priority add 20: " + priority.add(20));
        System.out.println("priority size: " + priority.size());
        System.out.println("priority poll: " + priority.poll());
        System.out.println("priority poll: " + priority.poll());
        System.out.println("priority poll: " + priority.poll());

        Queue<String> bounded = new ArrayBlockingQueue<>(2);
        System.out.println("bounded add A: " + bounded.add("A"));
        System.out.println("bounded offer B: " + bounded.offer("B"));
        System.out.println("bounded offer C: " + bounded.offer("C"));
        System.out.println("bounded size: " + bounded.size());

        try {
            bounded.add("D");
        } catch (IllegalStateException e) {
            System.out.println("bounded add D: IllegalStateException");
        }

        System.out.println("bounded poll: " + bounded.poll());
        System.out.println("bounded offer C after poll: " + bounded.offer("C"));
        System.out.println("bounded poll: " + bounded.poll());
        System.out.println("bounded poll: " + bounded.poll());
        System.out.println("bounded empty poll: " + bounded.poll());

        try {
            priority.offer(null);
        } catch (NullPointerException e) {
            System.out.println("priority offer null: NullPointerException");
        }

        try {
            priority.add(null);
        } catch (NullPointerException e) {
            System.out.println("priority add null: NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 QueueInsertionDemo.java
java QueueInsertionDemo
```

Stdout:

```text
priority offer 30: true
priority offer 10: true
priority add 20: true
priority size: 3
priority poll: 10
priority poll: 20
priority poll: 30
bounded add A: true
bounded offer B: true
bounded offer C: false
bounded size: 2
bounded add D: IllegalStateException
bounded poll: A
bounded offer C after poll: true
bounded poll: B
bounded poll: C
bounded empty poll: null
priority offer null: NullPointerException
priority add null: NullPointerException
```

### Đọc kết quả theo hợp đồng

`PriorityQueue<>(1)` nhận đủ ba phần tử. Các lần lấy đầu hàng đợi trả `10, 20, 30`, theo thứ tự ưu tiên mặc định chứ không phải thứ tự thêm `30, 10, 20`.

Với hàng đợi dung lượng 2, `A` và `B` được tiếp nhận. `offer("C")` trả `false`, nên `C` chưa nằm trong hàng đợi. `add("D")` ném ngoại lệ vì không còn chỗ.

Sau khi `poll()` lấy `A` ra, có một chỗ trống và lần `offer("C")` mới thành công. Điều này cho thấy kết quả `false` phản ánh trạng thái tại lần gọi đó, không có nghĩa phần tử ấy bị cấm vĩnh viễn.

Hai lời gọi với `null` minh chứng rằng đổi từ `add` sang `offer` không biến một đầu vào không hợp lệ thành `false`: `PriorityQueue` cấm `null` và cả hai đều ném lỗi.

## 5. Biểu diễn thất bại phải giữ được ý nghĩa

Có ba tình huống cần phân biệt:

| Loại kết quả | Điều bên gọi nên hiểu |
| --- | --- |
| `true` | Phần tử được thêm thành công |
| `false` từ `offer` vì thiếu chỗ | Phần tử chưa được tiếp nhận; áp dụng chính sách tải |
| Ngoại lệ vì dữ liệu/điều kiện không hợp lệ | Xem lại đầu vào hoặc hợp đồng API; không coi mặc nhiên là hàng đợi đầy |

Nếu viết một phương thức bao quanh `offer`, có thể trả `boolean` để chuyển tiếp việc có tiếp nhận hay không:

```java
static boolean trySubmit(Queue<String> pending, String job) {
    return pending.offer(job);
}
```

Đoạn này giả định đã import `Queue` và nằm trong một lớp. Nó không nuốt ngoại lệ đầu vào. Người gọi phải hiểu `false` là từ chối tiếp nhận theo hợp đồng hàng đợi, không phải “mọi lỗi đều đã được xử lý”.

Tránh bắt `RuntimeException` hoặc `Exception` rồi luôn trả `false`. Cách đó có thể che lỗi như `null`, phần tử không so sánh được hoặc lỗi trong comparator và làm hệ thống chẩn đoán nhầm thành thiếu dung lượng.

Với `PriorityQueue`, các phần tử phải phù hợp cơ chế so sánh. Khi dựa trên thứ tự tự nhiên, kiểu phần tử cần có khả năng so sánh phù hợp; một `Comparator` tùy chỉnh cũng cần đáp ứng hợp đồng so sánh. `offer` không có trách nhiệm sửa dữ liệu hay sửa comparator thay người gọi.

## 6. offer không đồng nghĩa với chờ đến khi có chỗ

`Queue.offer(e)` thông thường thử thêm ngay; nó không mang hợp đồng chờ vô hạn cho hàng đợi đầy.

`BlockingQueue` cung cấp thêm các lựa chọn:

| API | Khi không còn chỗ |
| --- | --- |
| `add(e)` | Báo lỗi bằng ngoại lệ |
| `offer(e)` | Trả `false` ngay theo hợp đồng |
| `put(e)` | Chờ có chỗ, có thể bị ngắt |
| `offer(e, timeout, unit)` | Chờ trong giới hạn thời gian, có thể bị ngắt |

`put` và `offer` có timeout không thuộc interface `Queue`. Trong chương trình, biến `bounded` được khai báo là `Queue<String>` nên chỉ sử dụng các thao tác tương ứng của `Queue`, dù đối tượng thực tế là `ArrayBlockingQueue`.

Việc chọn chờ, từ chối ngay hoặc chuyển công việc đi nơi khác là quyết định điều phối tải. Không thay một API này bằng API khác mà bỏ qua việc bên gọi có thể bị giữ lại bao lâu.

## 7. Không kiểm tra size rồi giả định lần thêm chắc chắn thành công

Mã kiểu sau có thể sai khi nhiều luồng cùng thêm:

```java
// Minh họa cách suy luận không an toàn khi có truy cập đồng thời:
// if (queue.size() < capacity) {
//     queue.add(job);
// }
```

Một luồng khác có thể dùng chỗ trống sau bước kiểm tra. Hãy dùng kết quả của chính thao tác thêm theo hợp đồng của triển khai, chẳng hạn `offer` trên một hàng đợi đồng thời thích hợp.

`PriorityQueue` thông thường không an toàn cho việc nhiều luồng truy cập khi có luồng sửa dữ liệu. Chọn `offer` thay `add` không làm nó tự trở thành thread-safe. Ví dụ trong bài chạy trên một luồng để quan sát rõ các kết quả.

## 8. Quyết định dùng add hay offer

- Dùng `offer` khi không thể tiếp nhận vì giới hạn dung lượng là nhánh được dự kiến, và bên gọi sẽ xử lý `false`.
- Dùng `add` khi muốn việc vi phạm kỳ vọng thêm thành công được báo qua ngoại lệ.
- Với `PriorityQueue`, đừng kỳ vọng khác biệt “đầy” chỉ vì dung lượng ban đầu nhỏ.
- Kiểm tra dữ liệu theo hợp đồng triển khai; `offer` không phải API “không bao giờ ném lỗi”.
- Không bỏ qua kết quả `offer` nếu mất công việc là điều không được phép.

Mục tiêu là biểu diễn đúng lý do không tiếp nhận và giữ cho bên gọi có đủ thông tin để quyết định.

## 9. Tự kiểm tra

1. Hàng đợi dung lượng 2 đã chứa hai phần tử: `offer` và `add` báo không còn chỗ thế nào?
2. `new PriorityQueue<>(2)` có từ chối phần tử thứ ba bằng `false` không?
3. Đổi `priority.add(null)` thành `priority.offer(null)` có tránh được lỗi không?
4. Sau `offer(job) == false`, có được ghi nhận rằng công việc đã tiếp nhận không?
5. `Queue` có định nghĩa `put` không?

Đáp án:

1. `offer` trả `false`; `add` ném `IllegalStateException` theo hợp đồng hàng đợi bounded tương ứng.
2. Không; dung lượng ban đầu không phải giới hạn tối đa.
3. Không; `PriorityQueue` cấm `null`, cả hai ném `NullPointerException`.
4. Không; phải xử lý việc chưa tiếp nhận.
5. Không; đó là thao tác của `BlockingQueue`.

## Tài liệu đối chiếu

Xem hợp đồng [Queue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Queue.html), cách tăng dung lượng của [PriorityQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html) và các thao tác khi đầy của [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).
