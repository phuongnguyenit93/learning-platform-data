# ArrayBlockingQueue và dung lượng cố định

## 1. Hình dung một khay đựng công việc có số chỗ hữu hạn

`ArrayBlockingQueue<E>` là hàng đợi an toàn cho nhiều luồng, dùng mảng bên trong và có dung lượng được ấn định lúc tạo. Luồng tạo việc (producer) đưa phần tử vào cuối hàng đợi; luồng xử lý (consumer) lấy phần tử ở đầu. Phần tử được lấy theo thứ tự vào trước, ra trước (FIFO).

Hãy hình dung một khay có 3 chỗ. Khi cả 3 chỗ đều đang chứa công việc, việc thứ tư không được tự động làm khay lớn thêm. Chương trình phải chọn: từ chối nhận ngay, chờ có chỗ, hoặc chờ có thời hạn. Sau khi consumer lấy một công việc ra, chỗ đó dùng được cho lần thêm tiếp theo.

Giới hạn này giúp ứng dụng bộc lộ tình trạng bên tạo việc nhanh hơn bên xử lý. Một hàng đợi luôn tăng kích thước có thể che giấu quá tải bằng cách giữ thêm dữ liệu; một hàng đợi hữu hạn buộc bên gọi xử lý tình huống không còn chỗ. Khi producer thực sự giảm nhịp vì phải chờ, đó là một cách tạo điều tiết ngược (backpressure). Chỉ khai báo dung lượng hữu hạn chưa đủ để tạo một chính sách điều tiết hoàn chỉnh.

Đây là API còn sử dụng trong Java hiện đại. Các ví dụ dưới đây dùng cú pháp và API có thể biên dịch bằng Java 17 trở lên.

## 2. Khởi tạo và ý nghĩa của dung lượng

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

// Đoạn khai báo minh họa.
BlockingQueue<String> jobs = new ArrayBlockingQueue<>(100);
```

`100` là số phần tử tối đa đang nằm trong hàng đợi, không phải số byte, số luồng, số công việc đã hoàn tất hay kích thước ban đầu có thể tự tăng. Giá trị phải lớn hơn 0; truyền 0 hoặc số âm làm constructor ném `IllegalArgumentException`.

Hàng đợi bắt đầu rỗng nhưng có 100 vị trí lưu tham chiếu. Sau khi tạo, API không có phương thức đổi dung lượng của chính hàng đợi đó. `clear()` xóa dữ liệu đang chờ, không thu nhỏ hay mở rộng dung lượng. Nếu cần một giới hạn khác, phải lập kế hoạch thay hàng đợi và chuyển việc an toàn; chỉ gán lại một biến tham chiếu không bảo đảm các producer/consumer đang giữ tham chiếu cũ sẽ chuyển sang hàng đợi mới.

Có ba dạng constructor đáng biết:

| Constructor | Ý nghĩa |
| --- | --- |
| `new ArrayBlockingQueue<E>(capacity)` | Hàng đợi rỗng, chính sách công bằng mặc định là `false` |
| `new ArrayBlockingQueue<E>(capacity, fair)` | Hàng đợi rỗng, chọn chính sách công bằng khi tranh chấp |
| `new ArrayBlockingQueue<E>(capacity, fair, collection)` | Nạp dữ liệu ban đầu theo thứ tự duyệt của collection; dung lượng phải đủ chứa dữ liệu đó |

`null` không được dùng làm phần tử. Constructor nhận collection cũng yêu cầu collection và các phần tử của nó khác `null`. Các hợp đồng constructor và tính cố định của dung lượng được mô tả trong [ArrayBlockingQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

## 3. Phân biệt ba con số

Với một trạng thái không bị thay đổi đồng thời:

```text
capacity = số chỗ cố định khi tạo
size = số phần tử hiện đang xếp hàng
remainingCapacity = số chỗ còn trống

size + remainingCapacity = capacity
```

Ví dụ dung lượng 3:

| Sau thao tác | Nội dung theo FIFO | `size()` | `remainingCapacity()` |
| --- | --- | --- | --- |
| Vừa tạo | `[]` | 0 | 3 |
| Thêm A | `[A]` | 1 | 2 |
| Thêm B, C | `[A, B, C]` | 3 | 0 |
| Lấy A | `[B, C]` | 2 | 1 |
| Thêm D | `[B, C, D]` | 3 | 0 |

Khi nhiều luồng đang thay đổi hàng đợi, hai lời gọi `size()` và `remainingCapacity()` là hai quan sát khác thời điểm. Không lấy tổng hai kết quả bất kỳ rồi kết luận hàng đợi đã vi phạm dung lượng.

Tương tự, `remainingCapacity() > 0` không đặt trước một chỗ cho luồng hiện tại. Một producer khác có thể chiếm chỗ trước khi luồng này thêm phần tử. Quyết định tiếp nhận nên dựa vào kết quả của thao tác thêm, không dựa vào kiểm tra trước:

```java
// Đoạn minh họa trong phương thức; jobs là BlockingQueue<String>.
String job = "report";
if (!jobs.offer(job)) {
    System.out.println("Queue is full; job was not accepted");
}
```

`offer` thất bại không tự lưu công việc ở nơi khác và không tự thử lại. Nhánh thất bại phải có quyết định phù hợp với ứng dụng: báo từ chối, ghi vào nơi lưu bền vững, thử lại có kiểm soát, hoặc bỏ việc nếu yêu cầu cho phép.

## 4. Cơ chế mảng vòng và tái sử dụng chỗ

Có thể hiểu cách lưu như một mảng vòng: vị trí thêm và vị trí lấy dịch dần, tới cuối mảng thì quay về đầu. Những chỗ đã giải phóng được dùng lại. “Vòng” nói về cách sử dụng vị trí trong mảng, không có nghĩa là công việc cũ tự động bị ghi đè khi hàng đợi đầy.

```text
Dung lượng 3
Thêm: A, B, C       Thứ tự lấy: A -> B -> C
Lấy: A             Còn: B -> C
Thêm: D            Thứ tự lấy tiếp: B -> C -> D
```

Không cần tăng mảng để thêm `D` sau khi đã lấy `A`, và `B` vẫn được lấy trước `C`, `D`. Bên sử dụng nên dựa vào hợp đồng FIFO và giới hạn dung lượng, không truy cập hay phụ thuộc vào chỉ số lưu nội bộ.

## 5. Khi đầy: phương thức thêm quyết định hành vi

| Phương thức | Khi có chỗ | Khi đầy | Có thể bị ngắt khi chờ? |
| --- | --- | --- | --- |
| `add(e)` | Thêm, trả `true` | Ném `IllegalStateException` | Không có cơ chế chờ chỗ trống |
| `offer(e)` | Thêm, trả `true` | Trả `false` | Không có cơ chế chờ chỗ trống |
| `put(e)` | Thêm và kết thúc | Chờ đến khi thêm được hoặc bị ngắt | Có, `InterruptedException` |
| `offer(e, timeout, unit)` | Thêm, trả `true` | Chờ có giới hạn; hết thời gian mà chưa thêm được thì trả `false` | Có, `InterruptedException` |

`put` không âm thầm làm tăng dung lượng và không loại phần tử cũ để nhận phần tử mới. Nó cũng không tự trả `false`, vì kiểu trả về của nó là `void`. Với timed `offer`, thời hạn là ngân sách chờ chỗ trống, không phải thời hạn hoàn tất xử lý công việc sau khi được nhận.

Nếu mã đang ở tầng có thể chuyển yêu cầu ngắt lên, khai báo `throws InterruptedException`. Nếu bắt ngoại lệ trong một tác vụ không chuyển được lên, cần tuân theo chính sách hủy; thường là khôi phục cờ bằng `Thread.currentThread().interrupt()` rồi kết thúc tác vụ. Nuốt ngoại lệ và lặp lại `put` vô hạn có thể làm mất tác dụng của yêu cầu dừng.

Ở phía lấy, `poll()` trả `null` khi rỗng; `take()` chờ phần tử; `poll(timeout, unit)` chỉ chờ có thời hạn. Vì không cho phép phần tử `null`, giá trị `null` của `poll` biểu thị chưa lấy được dữ liệu.

## 6. Ví dụ chạy đầy đủ: đầy, từ chối và dùng lại chỗ

Lưu mã sau trong `FixedCapacityDemo.java`. Các kiểm tra dùng `AssertionError` trực tiếp nên không cần tùy chọn `-ea`.

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

public class FixedCapacityDemo {
    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected queue state");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ArrayBlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        System.out.println("initial: size=" + queue.size()
                + ", remaining=" + queue.remainingCapacity());

        check(queue.offer("A"));
        queue.put("B");
        System.out.println("full: " + queue);
        check(!queue.offer("C"));
        System.out.println("offer when full: false");

        try {
            queue.add("C");
            throw new AssertionError("add must fail when full");
        } catch (IllegalStateException expected) {
            System.out.println("add when full: IllegalStateException");
        }

        check(!queue.offer("C", 20, TimeUnit.MILLISECONDS));
        System.out.println("timed offer when full: false");

        String first = queue.take();
        check("A".equals(first));
        System.out.println("take: " + first);

        queue.put("C");
        System.out.println("after reuse: " + queue);
        check(queue.size() == 2);
        check(queue.remainingCapacity() == 0);

        check("B".equals(queue.take()));
        check("C".equals(queue.take()));
        System.out.println("after drain: size=" + queue.size()
                + ", remaining=" + queue.remainingCapacity());

        ArrayBlockingQueue<String> handoff = new ArrayBlockingQueue<>(1);
        handoff.put("seed");

        Thread producer = new Thread(() -> {
            try {
                handoff.put("next");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        producer.start();
        check("seed".equals(handoff.take()));
        check("next".equals(handoff.take()));
        producer.join();
        System.out.println("capacity-one sequence: seed, next");
        check(handoff.remainingCapacity() == 1);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 FixedCapacityDemo.java
java FixedCapacityDemo
```

Stdout:

```text
initial: size=0, remaining=2
full: [A, B]
offer when full: false
add when full: IllegalStateException
timed offer when full: false
take: A
after reuse: [B, C]
after drain: size=0, remaining=2
capacity-one sequence: seed, next
```

Trong phần đầu, chỉ một luồng thay đổi `queue`, nên các trạng thái in ra xác định. Lần timed `offer` chạy khi hàng đợi đầy và chưa có consumer; vì vậy nó trả `false`. Chương trình không đo hay yêu cầu thời gian thực tế đúng 20 ms.

Sau khi lấy `A`, thêm `C` thành công và thứ tự còn lại là `[B, C]`. Khi lấy hết dữ liệu, dung lượng trống trở lại 2: việc hàng đợi rỗng không làm mất sức chứa đã cấp.

Phần `handoff` có dung lượng 1 và đã chứa `seed` khi producer bắt đầu. Producer chỉ có thể đưa `next` vào sau khi `seed` được lấy ra. Lịch chạy quyết định producer có thực sự đến `put` trước lần `take` đầu hay không; ví dụ không dựa vào `sleep` hoặc khẳng định producer đã chờ bao lâu. Chuỗi dữ liệu và kết quả cuối vẫn xác định. `join()` bảo đảm luồng producer đã kết thúc trước khi `main` kết thúc phần ví dụ.

## 7. FIFO của dữ liệu khác công bằng giữa các luồng

```java
// Hai hàng đợi này đều giữ thứ tự FIFO của phần tử.
ArrayBlockingQueue<String> normal = new ArrayBlockingQueue<>(10);
ArrayBlockingQueue<String> fair = new ArrayBlockingQueue<>(10, true);
```

`fair=true` quy định thứ tự tiếp cận của các luồng đang chờ thêm/lấy theo chính sách công bằng. Mặc định `false` không bảo đảm thứ tự phục vụ các luồng chờ, nhưng không biến dữ liệu thành một hàng đợi không FIFO.

Công bằng có thể giảm thông lượng để đổi lấy việc giảm biến động và hạn chế một luồng phải chờ lép vế kéo dài. Không bật chỉ vì tên `fair` nghe có vẻ tốt hơn; hãy đo với tải thực tế và yêu cầu độ trễ. Chính sách này không cam kết các công việc hoàn tất theo FIFO: hai consumer có thể lấy theo thứ tự A rồi B nhưng xử lý B nhanh hơn A.

## 8. Dung lượng cố định bảo vệ được điều gì?

Giới hạn dung lượng bảo đảm số phần tử còn nằm trong hàng đợi không vượt mức cấu hình. Nó không tự giới hạn toàn bộ tài nguyên của hệ thống:

- Phần tử là tham chiếu tới đối tượng. Hai công việc có thể giữ lượng dữ liệu chênh lệch lớn; 100 phần tử không có nghĩa là một mức RAM cố định.
- Công việc đã được consumer lấy ra đang xử lý không còn tính trong `size()`. Với nhiều consumer, số việc đang chờ cộng số việc đang xử lý có thể lớn hơn dung lượng hàng đợi.
- Producer đang chờ `put` vẫn có thể giữ công việc chưa đưa được vào. Nếu tạo vô hạn producer, bộ nhớ và số luồng vẫn có thể tăng ở ngoài hàng đợi.
- Dữ liệu tồn đọng ở tầng mạng, cơ sở dữ liệu, hàng đợi khác hoặc cơ chế thử lại không tự bị giới hạn bởi `ArrayBlockingQueue` này.

Ví dụ có 100 chỗ và 4 consumer mỗi bên giữ một công việc thì có thể có 100 việc đang xếp hàng cùng 4 việc đang xử lý. Nếu một consumer tự lấy thêm một lô vào bộ nhớ riêng, mức đang xử lý/cầm giữ còn phụ thuộc thiết kế lô đó.

`put` thành công chỉ xác nhận đã đưa phần tử vào, chưa xác nhận consumer đã xử lý, lưu dữ liệu hay trả kết quả. Hàng đợi ở bộ nhớ cũng không thay thế nơi lưu công việc bền vững khi tiến trình bị dừng.

## 9. Chọn dung lượng và tránh chờ vô hạn

Dung lượng lớn hơn hấp thụ được một đợt tăng tải ngắn, nhưng có thể làm công việc chờ lâu hơn và giữ nhiều dữ liệu hơn. Nếu tốc độ nhận dài hạn luôn cao hơn tốc độ xử lý dài hạn, tăng dung lượng chỉ dời thời điểm đầy; cần giảm tải vào, tăng khả năng xử lý, hoặc từ chối bớt công việc.

Để chọn mức ban đầu, hãy quan sát tốc độ đến, thời gian xử lý, mức tăng tải ngắn cần chịu được, độ trễ xếp hàng cho phép và bộ nhớ của một công việc thực tế. Theo dõi số lần `offer` thất bại, thời gian chờ khi thêm, độ sâu hàng đợi và thời gian từ lúc nhận đến lúc bắt đầu xử lý. Không suy từ một ảnh chụp `size()` đơn lẻ rằng hệ thống luôn đủ tải.

Một lỗi thiết kế dễ gặp là dùng cùng một luồng để thêm quá nhiều việc bằng `put` rồi mới bắt đầu lấy. Hàng đợi đầy khiến luồng đó dừng ở `put`; nó không đến được đoạn lấy để giải phóng chỗ. Tương tự, nếu mọi luồng của một bộ thực thi đều đang chờ thêm vào hàng đợi trong khi tác vụ consumer còn chờ chính bộ thực thi ấy cấp luồng, hệ thống có thể không tiến triển.

Vì vậy, trước khi chọn `put`, cần trả lời: bên nào đang chạy để lấy dữ liệu ra, nó có cần tài nguyên mà producer đang giữ hay không, và ai có quyền hủy việc chờ. Timed `offer` giới hạn một lần chờ nhưng vẫn cần xử lý nhánh thất bại; nó không tự sửa mọi vòng phụ thuộc tài nguyên.

Hàng đợi không có thao tác `close()` tích hợp báo “không còn công việc”. Một consumer dùng `take()` trên hàng đợi đã rỗng có thể chờ mãi sau khi producer kết thúc. Cần giao thức dừng riêng, chẳng hạn ngắt luồng hoặc thông điệp kết thúc được thiết kế đúng số consumer và đúng thứ tự nhận việc.

## 10. Kiểm tra nhanh

1. `new ArrayBlockingQueue<>(8)` đang chứa 2 phần tử. Nó có tự thu nhỏ còn 2 chỗ không? Không; dung lượng vẫn là 8.
2. Hàng đợi đầy, gọi `offer(x)` trả `false`. `x` có bị thêm vào rồi đợi xử lý không? Không; lần gọi đó không tiếp nhận `x`.
3. Consumer lấy một phần tử khỏi hàng đợi đầy. Chỗ vừa giải phóng dùng được cho lần thêm tiếp theo không? Có.
4. `fair=false` có làm `ArrayBlockingQueue` mất FIFO của dữ liệu không? Không; nó liên quan tới thứ tự phục vụ luồng chờ.
5. `size()==0` có chứng minh mọi công việc đã xử lý xong không? Không; consumer có thể đã lấy việc ra và vẫn đang xử lý.
6. Tăng dung lượng có giải quyết quá tải kéo dài khi bên tạo luôn nhanh hơn bên xử lý không? Không; cần một quyết định về tốc độ nhận và khả năng xử lý.
