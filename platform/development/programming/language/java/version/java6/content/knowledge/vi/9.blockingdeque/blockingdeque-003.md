# putFirst, putLast và chờ khi hàng đợi đầy

## 1. Thêm vào đầu nào và xử lý đầy ra sao là hai quyết định

Giả sử bộ đệm công việc có sức chứa hai phần tử và hiện giữ `[A,B]`, với đầu trước ở bên trái.

Một công việc mới X có thể cần:

- Đứng trước các công việc hiện có: dùng `putFirst(X)`.
- Đứng sau các công việc hiện có: dùng `putLast(X)`.

Nhưng cả hai đầu đều chia sẻ **cùng sức chứa của deque**. Khi đã đủ hai phần tử, thêm vào đầu trước không được quyền vượt giới hạn chỉ vì công việc mới có ưu tiên cao hơn.

`BlockingDeque<E>` kết hợp khả năng thao tác hai đầu với các phương thức có thể chờ. `putFirst` và `putLast` chờ đến khi có chỗ rồi mới thêm phần tử, hoặc bị ngắt trong quá trình chờ. Xem [BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

Bài dùng các API hiện còn áp dụng trong Java hiện đại; ví dụ chạy với Java 17 trở lên. Mô hình cần theo là **sức chứa → đầu chèn → điều kiện có chỗ → hành động giải phóng chỗ → hoàn tất hoặc ngắt**.

## 2. Tạo deque có giới hạn rõ ràng

Ví dụ minh họa trong phương thức:

```java
BlockingDeque<String> jobs = new LinkedBlockingDeque<>(2);
```

Cần import hai kiểu từ `java.util.concurrent`. Tham số 2 là sức chứa tối đa cố định của cấu trúc này.

Nếu không truyền sức chứa, `LinkedBlockingDeque` dùng giới hạn `Integer.MAX_VALUE`. Giới hạn rất lớn đó không phải cơ chế điều tiết thích hợp cho mọi ứng dụng và không có nghĩa bộ nhớ thực tế vô hạn. Constructor sức chứa phải nhận số dương. Xem [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

Không nhầm với một cấu trúc mảng tự mở rộng có tham số “sức chứa ban đầu”. Trong `LinkedBlockingDeque<>(2)`, phần tử thứ ba thực sự phải chờ hoặc bị từ chối theo phương thức được chọn.

## 3. Hợp đồng của putFirst và putLast

| Phương thức | Khi có chỗ | Khi đầy | Khi hoàn tất bình thường |
| --- | --- | --- | --- |
| `putFirst(e)` | Thêm ở đầu trước | Chờ có chỗ | Phần tử đã được thêm |
| `putLast(e)` | Thêm ở đầu sau | Chờ có chỗ | Phần tử đã được thêm |

Cả hai trả `void` và có thể ném `InterruptedException`. Không có giá trị `false` để báo đầy và không có tham số timeout trên chính phương thức put.

`put(e)`, kế thừa theo cách dùng hàng đợi thông thường, tương đương `putLast(e)`. Đây là quan hệ được quy định trong [BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

Với dữ liệu đang là `[A,B]`:

```text
putFirst(X) đang chờ:
[A, B] -- takeLast() lấy B --> [A] -- chèn X --> [X, A]

putLast(X) đang chờ:
[A, B] -- takeFirst() lấy A --> [B] -- chèn X --> [B, X]
```

Không bắt buộc phải lấy ở cùng đầu với nơi producer muốn chèn. Lấy khỏi bất kỳ đầu nào đều có thể giải phóng một chỗ trong sức chứa chung.

Nếu có nhiều producer tranh chấp, chỗ vừa được giải phóng không phải lời hứa rằng một producer cụ thể sẽ được chạy trước. Không suy luận thứ tự phục vụ các luồng chỉ từ tên `putFirst/putLast`; tên đó quy định vị trí phần tử được chèn khi thao tác thành công.

## 4. Chờ không tạo ra thêm năng lực xử lý

Khi deque đầy, producer gọi put sẽ chậm lại theo khả năng giải phóng chỗ của consumer. Đây là một cách tạo áp lực ngược (`backpressure`) giữa bên tạo và bên xử lý công việc.

Cơ chế này giúp giới hạn số phần tử đang xếp hàng, nhưng không tự:

- Làm consumer xử lý nhanh hơn.
- Giới hạn số byte của từng công việc.
- Giới hạn toàn bộ số công việc đang được xử lý bên ngoài hàng đợi.
- Hoàn tất thao tác nếu không còn luồng nào có thể tạo chỗ trống.

Nếu không có consumer và không có ai xóa phần tử, một put có thể chờ vô thời hạn. Thời gian chờ là một phần quan trọng của độ trễ, dù thao tác nối nút ở hai đầu có chi phí nhỏ khi đã có chỗ.

Không đặt put vào chính luồng duy nhất sẽ chạy câu lệnh lấy phần tử sau đó:

```java
// Minh họa sai nếu jobs đã đầy và không có consumer khác:
jobs.putLast("X");
jobs.takeFirst(); // Không thể tới đây để tự giải phóng chỗ.
```

Đây là đoạn minh họa lỗi thiết kế, không phải chương trình độc lập.

## 5. Chương trình Java: giải phóng chỗ và ngắt producer

Ví dụ có hai trường hợp giải phóng chỗ và một trường hợp ngắt. Tín hiệu `aboutToPut` cho biết producer đã tới ngay trước lời gọi put; nó không khẳng định JVM đã đưa luồng vào trạng thái chờ vật lý nào.

Trong hai trường hợp đầu, trước khi consumer lấy phần tử, deque vẫn đầy và không có đường nào khác giải phóng chỗ. Do đó lời gọi put chưa thể hoàn tất bình thường.

Lưu tệp `BlockingPutDemo.java`:

```java
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;

public class BlockingPutDemo {
    static void insertionCase(boolean atFirst) throws Exception {
        String label = atFirst ? "putFirst" : "putLast";
        BlockingDeque<String> deque = new LinkedBlockingDeque<>(2);
        deque.putLast("A");
        deque.putLast("B");

        CountDownLatch aboutToPut = new CountDownLatch(1);
        FutureTask<Void> insertion = new FutureTask<>(() -> {
            aboutToPut.countDown();
            if (atFirst) {
                deque.putFirst("X");
            } else {
                deque.putLast("X");
            }
            return null;
        });

        Thread producer = new Thread(insertion, label + "-producer");
        producer.start();
        try {
            if (!aboutToPut.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Producer did not reach put");
            }

            System.out.println(label + ".full=" + deque);
            System.out.println(label + ".unfinished.before.take="
                    + !insertion.isDone());

            String removed = atFirst
                    ? deque.takeLast()
                    : deque.takeFirst();

            insertion.get(5, TimeUnit.SECONDS);
            producer.join();

            System.out.println(label + ".removed=" + removed);
            System.out.println(label + ".after=" + deque);
        } finally {
            producer.interrupt();
        }
    }

    static void interruptionCase() throws Exception {
        BlockingDeque<String> deque = new LinkedBlockingDeque<>(1);
        deque.putLast("A");
        CountDownLatch aboutToPut = new CountDownLatch(1);

        FutureTask<String> insertion = new FutureTask<>(() -> {
            aboutToPut.countDown();
            try {
                deque.putLast("X");
                return "inserted";
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return "interrupted";
            }
        });

        Thread producer = new Thread(insertion, "interrupted-producer");
        producer.start();
        try {
            if (!aboutToPut.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Producer did not reach put");
            }

            producer.interrupt();
            String result = insertion.get(5, TimeUnit.SECONDS);
            producer.join();

            System.out.println("interrupt.result=" + result);
            System.out.println("interrupt.after=" + deque);
        } finally {
            producer.interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        insertionCase(true);
        insertionCase(false);
        interruptionCase();
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 BlockingPutDemo.java
java BlockingPutDemo
```

Stdout khi các luồng hoàn thành theo phối hợp trong ví dụ:

```text
putFirst.full=[A, B]
putFirst.unfinished.before.take=true
putFirst.removed=B
putFirst.after=[X, A]
putLast.full=[A, B]
putLast.unfinished.before.take=true
putLast.removed=A
putLast.after=[B, X]
interrupt.result=interrupted
interrupt.after=[A]
```

Đọc kết quả:

1. Hai deque ban đầu đều đầy; X chưa thể được chèn trước khi có phần tử bị lấy ra.
2. Trường hợp đầu lấy B ở đuôi để tạo chỗ cho X ở đầu.
3. Trường hợp sau lấy A ở đầu để tạo chỗ cho X ở đuôi.
4. Trong trường hợp ngắt, không consumer nào tạo chỗ; X không được chèn và A vẫn còn.
5. `FutureTask.get` đưa lỗi từ công việc producer về luồng chính; timeout trong bài thử giúp phát hiện công việc không hoàn tất, không đặt timeout cho chính put. Xem [FutureTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html).

Chương trình không dùng sleep để suy đoán thứ tự. Dòng `unfinished.before.take` xác nhận công việc chưa hoàn thành tại thời điểm kiểm tra; nó không được dùng để tuyên bố producer nhất định đã bị hệ điều hành đưa vào trạng thái chờ cụ thể.

## 6. InterruptedException là một phần của hợp đồng chờ

Nếu luồng bị ngắt trong khi đang chờ để chèn, lời gọi có thể kết thúc bằng `InterruptedException`. Ứng dụng phải quyết định dừng công việc, truyền lỗi lên nơi gọi hoặc xử lý hủy phù hợp.

Hai cách tổ chức thường gặp:

- Phương thức của bạn có thể truyền `InterruptedException`: khai báo và để nơi điều phối xử lý.
- Đang ở ranh giới tác vụ cần kết thúc: bắt lỗi, khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` rồi rời tác vụ.

Ví dụ dùng cách thứ hai trong `interruptionCase`: producer trả trạng thái “interrupted” và không thử chèn lại.

Không bắt lỗi rồi tiếp tục lặp put vô hạn mà bỏ qua yêu cầu ngắt. Cũng không khôi phục cờ rồi lập tức thử lại mãi mà không có chính sách, vì lời gọi chờ kế tiếp có thể lại nhận tín hiệu ngắt.

Nếu ngắt chạy đua với việc chỗ trống vừa xuất hiện, không viết nghiệp vụ dựa trên giả định ngắt luôn thắng. Ví dụ cố ý giữ deque đầy đến cuối nên không có cuộc đua giải phóng chỗ đó.

## 7. Khi không muốn chờ vô hạn

Đối chiếu các lựa chọn khi chèn:

| Mục tiêu khi đầy | Đầu trước | Đầu sau |
| --- | --- | --- |
| Ném lỗi ngay khi không chèn được do sức chứa | `addFirst(e)` | `addLast(e)` |
| Trả false nếu hiện không chèn được | `offerFirst(e)` | `offerLast(e)` |
| Chờ có chỗ, không đặt thời hạn | `putFirst(e)` | `putLast(e)` |
| Chờ tối đa một thời hạn | `offerFirst(e,t,unit)` | `offerLast(e,t,unit)` |

Với offer có thời hạn, cần đọc kết quả boolean: false nghĩa là phần tử chưa được chèn do không có chỗ trong thời hạn. Việc bắt `InterruptedException` vẫn cần thiết đối với biến thể chờ có thời hạn.

Không viết kiểu “nếu remainingCapacity lớn hơn 0 thì chèn chắc chắn không chờ”. Giữa kiểm tra và lời gọi chèn, producer khác có thể lấy mất chỗ. Dùng chính thao tác put/offer phù hợp để diễn đạt điều kiện cần có.

Không tự xây một vòng lặp kiểm tra đầy liên tục khi API chờ đã đáp ứng yêu cầu. Vòng lặp đó dễ tiêu tốn CPU và làm chính sách hủy khó kiểm soát hơn.

## 8. Thứ tự xử lý phải theo cả đầu chèn và đầu lấy

`putLast` kết hợp `takeFirst` tạo mô hình hàng đợi FIFO theo cách sử dụng thông thường: phần tử vào trước được lấy trước.

`putFirst` kết hợp lấy ở đầu trước có thể đưa công việc mới lên trước công việc đang chờ. Điều đó hữu ích khi nghiệp vụ cho phép ưu tiên, nhưng không còn giữ cùng thứ tự FIFO cho toàn bộ công việc.

Nếu liên tục đưa công việc mới vào đầu, công việc cũ có thể bị trì hoãn. Thứ tự chờ của các producer và thứ tự phần tử trong deque cũng là hai khái niệm khác nhau.

Trước khi chọn phương thức, phát biểu đủ:

```text
Producer thêm ở đầu nào?
Consumer lấy ở đầu nào?
Khi đầy thì chờ, từ chối hay chờ có thời hạn?
Khi muốn dừng thì ai ngắt producer hoặc kết thúc consumer?
```

## 9. Tránh làm mất khả năng giải phóng chỗ

Một số thiết kế khiến put không thể tiến triển dù cấu trúc hoạt động đúng:

- Giữ một khóa của ứng dụng trong lúc put, trong khi consumer cần chính khóa ấy trước khi lấy phần tử.
- Dùng một nhóm luồng cố định mà mọi luồng đều đang làm producer chờ trên deque đầy, còn tác vụ consumer vẫn xếp hàng chưa được chạy.
- Dừng hết consumer trước nhưng vẫn để producer chèn không có thời hạn.
- Dùng cùng luồng cho put trên deque đầy và thao tác lấy chỉ xuất hiện ở câu lệnh sau.

Cần tổ chức tài nguyên và thứ tự dừng để vẫn có người giải phóng chỗ, hoặc có đường hủy/thời hạn phù hợp.

Theo [BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html), giao diện không tự cung cấp thao tác close/shutdown để báo không còn công việc. Nếu thiết kế dùng dấu kết thúc, phải giữ đúng thứ tự và số consumer; nếu dùng ngắt, phải để các tác vụ tôn trọng tín hiệu đó.

Deque cũng không nhận null. Không dùng null làm phần tử đánh dấu kết thúc; hãy chọn đối tượng biểu diễn rõ ràng hoặc một cơ chế điều phối riêng.

## 10. Tự kiểm tra

1. Deque sức chứa 2 có `[A,B]`; `putFirst(X)` có được vượt sức chứa vì X được đưa lên đầu không?
2. Consumer lấy ở đuôi có tạo chỗ cho producer đang muốn putFirst không?
3. Muốn chờ tối đa 200 ms ở đầu sau thì dùng putLast hay phương thức nào?
4. Vì sao kiểm tra remainingCapacity rồi put không phải một thao tác nguyên tử?
5. Nếu chỉ có một luồng và deque đầy, vì sao “put rồi take” có thể không tới được take?
6. Sau khi bắt InterruptedException để hủy tác vụ, vì sao không nên im lặng chèn lại vô hạn?

Định hướng: (1) không; (2) có, sức chứa là chung; (3) `offerLast(e,200,TimeUnit.MILLISECONDS)` và kiểm tra kết quả; (4) có thể bị luồng khác chen vào; (5) put đang chờ chính chỗ mà take chưa thể giải phóng; (6) làm mất chính sách hủy của nơi điều phối.

Hiểu putFirst/putLast là hiểu cả vị trí phần tử và điều kiện tiến triển của luồng chèn. Chọn đúng sức chứa, đầu thao tác và cách hủy giúp hàng đợi tạo áp lực ngược theo đúng thiết kế.
