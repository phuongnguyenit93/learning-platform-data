# Quy tắc null và tín hiệu kết thúc xử lý

## 1. Ba tình huống cần phân biệt

Khi một luồng lấy công việc từ `BlockingQueue`, có ba câu hỏi khác nhau: lúc này có phần tử lấy được không, từ nay có còn công việc mới không, và những công việc đã nhận có xử lý xong chưa. Một tín hiệu duy nhất không tự trả lời cả ba câu hỏi.

`null` do `poll()` trả về chỉ mô tả lần lấy chưa thành công. Tín hiệu kết thúc luồng dữ liệu nói rằng theo giao thức ứng dụng sẽ không còn công việc mới phía sau. Còn việc toàn bộ xử lý đã hoàn tất cần được xác nhận bằng vòng đời consumer, kết quả tác vụ hoặc một cơ chế theo dõi hoàn tất riêng.

Phân biệt chúng giúp tránh hai lỗi phổ biến: consumer dừng quá sớm khi hàng đợi chỉ tạm rỗng, hoặc consumer chờ mãi sau khi producer đã kết thúc.

## 2. BlockingQueue không chấp nhận phần tử null

Mọi cách thêm phần tử như `add(null)`, `offer(null)`, `put(null)` và timed `offer` với phần tử `null` đều không hợp lệ và ném `NullPointerException`. Không dùng `null` làm thông điệp kết thúc.

| Phương thức lấy | Ý nghĩa khi không lấy được phần tử | Có trả `null` như tín hiệu kết thúc luồng dữ liệu không? |
| --- | --- | --- |
| `poll()` | Trả `null` khi lần thử không lấy được phần tử | Không |
| `poll(timeout, unit)` | Trả `null` nếu hết thời gian chờ mà chưa lấy được phần tử | Không |
| `take()` | Chờ phần tử hoặc có thể ném `InterruptedException` | Không |
| `remove()` | Ném `NoSuchElementException` khi không lấy được phần tử đầu | Không |

`BlockingQueue` dành `null` làm giá trị báo không lấy được trong các phương thức `poll`. Việc cấm lưu phần tử `null` giúp bên gọi không phải đoán kết quả `null` là dữ liệu thật hay là một lần lấy thất bại. Quy tắc này và việc hàng đợi không có thao tác đóng tích hợp được nêu trong [BlockingQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Giới hạn trên kiểm tra chính phần tử đưa vào hàng đợi. Nếu đưa một đối tượng `Job` khác `null` nhưng trường `payload` bên trong bằng `null`, hàng đợi không tự kiểm tra mọi trường của `Job`. Tính hợp lệ của dữ liệu bên trong cần được lớp dữ liệu hoặc tầng nghiệp vụ kiểm tra riêng.

## 3. Rỗng không có nghĩa là hết việc

```java
// Đoạn minh họa lỗi; queue là BlockingQueue<String>.
String job = queue.poll();
if (job == null) {
    return; // Có thể dừng quá sớm nếu producer sắp tạo thêm việc.
}
```

Một producer có thể đang đọc dữ liệu, chờ mạng hoặc chưa được lập lịch chạy. Trong lúc đó hàng đợi rỗng là trạng thái bình thường. Tăng thời hạn `poll` từ 1 giây lên 10 giây không biến kết quả `null` thành bằng chứng producer đã kết thúc.

Ngược lại, `queue.isEmpty()` không chứng minh công việc đã hoàn tất: consumer có thể đã lấy phần tử ra và đang xử lý. Thao tác lấy xóa phần tử khỏi hàng đợi trước khi nghiệp vụ phía sau hoàn tất.

Do đó, cần thiết kế rõ giao thức vòng đời: ai được tạo việc, khi nào ngừng nhận việc mới, ai thông báo hết luồng dữ liệu, và ai đợi các consumer xử lý xong.

## 4. Dùng một thông điệp kết thúc khác null

Một cách phổ biến là đưa vào hàng đợi một giá trị đặc biệt mà consumer hiểu là “không còn công việc phía sau”. Giá trị này thường được gọi là dấu kết thúc (end marker) hoặc poison pill. Nó không có hành vi đặc biệt từ JVM; ứng dụng tự quy định ý nghĩa.

Nên phân biệt dữ liệu và tín hiệu bằng kiểu dữ liệu rõ ràng. Ví dụ dùng `Work` cho việc thật và `End.INSTANCE` cho dấu kết thúc. Cả hai đều là phần tử khác `null` của cùng giao thức `Message`.

Không chọn bừa chuỗi `"STOP"`, số `-1` hay một đối tượng nghiệp vụ bình thường làm dấu kết thúc nếu dữ liệu hợp lệ có thể trùng giá trị đó. Consumer có thể nhầm việc thật thành yêu cầu dừng. Kiểu tín hiệu riêng giúp tránh va chạm và giải thích mục đích ngay trong mã.

### Thứ tự gửi là một phần của tính đúng đắn

Với hàng đợi FIFO và một producer, quy trình kết thúc bình thường có thể là:

1. Chặn việc nhận thêm yêu cầu mới vào luồng công việc đó.
2. Đưa toàn bộ công việc đã nhận vào hàng đợi.
3. Đưa dấu kết thúc vào sau các công việc.
4. Consumer xử lý từng việc và thoát khi lấy được dấu kết thúc.
5. Bên điều phối đợi consumer kết thúc và kiểm tra kết quả.

Nếu gửi dấu kết thúc rồi vẫn đưa công việc mới phía sau, consumer có thể đã thoát trước khi lấy việc mới. Nếu hàng đợi không FIFO, chẳng hạn một hàng đợi ưu tiên, không được tự áp dụng lập luận “được thêm sau thì sẽ lấy sau”; phải thiết kế lại thứ tự và giao thức phù hợp.

### Nhiều consumer cần đủ tín hiệu

Một phần tử được lấy bởi một consumer, không được tự phát cho tất cả. Nếu có `N` consumer và mỗi consumer dừng khi lấy một dấu kết thúc, bên điều phối cần gửi `N` dấu. Trong mô hình này consumer dừng ngay nên không có consumer nào lấy hai dấu để làm thiếu dấu cho bên khác.

Số consumer cần ổn định hoặc được theo dõi đúng trong suốt quá trình kết thúc. Nếu tùy ý thêm consumer mới sau khi đã gửi đủ dấu cho nhóm cũ, consumer mới có thể chờ mãi. Đây là yêu cầu của giao thức ứng dụng, không phải thứ `BlockingQueue` tự quản lý.

## 5. Ví dụ chạy đầy đủ: hai consumer và dấu kết thúc có kiểu

Ví dụ dùng hàng đợi FIFO `ArrayBlockingQueue`, một producer là luồng main và hai consumer. Mỗi công việc tính bình phương một số. Một `enum` có duy nhất giá trị `End.INSTANCE` làm dấu kết thúc, tách biệt với `Work`.

`sealed interface` giới hạn các kiểu thông điệp được phép; `record` chứa dữ liệu công việc; kiểm tra `instanceof Work work` đọc công việc đã nhận. Đây đều là cú pháp dùng được trên Java 17 mà không cần bật tính năng thử nghiệm.

Lưu vào `QueueEndSignalDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueueEndSignalDemo {
    sealed interface Message permits Work, End {}

    record Work(int value) implements Message {}

    enum End implements Message {
        INSTANCE
    }

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected result");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(2);
        List<Integer> results =
                Collections.synchronizedList(new ArrayList<>());

        try {
            queue.offer(null);
            throw new AssertionError("null must be rejected");
        } catch (NullPointerException expected) {
            System.out.println("offer(null): NullPointerException");
        }

        check(queue.poll() == null);
        System.out.println("poll(empty): null, not an end signal");

        Runnable consume = () -> {
            try {
                while (true) {
                    Message message = queue.take();
                    if (message == End.INSTANCE) {
                        return;
                    }
                    if (message instanceof Work work) {
                        results.add(work.value() * work.value());
                    } else {
                        throw new AssertionError("Unknown message");
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        int consumerCount = 2;
        Thread[] consumers = new Thread[consumerCount];
        for (int i = 0; i < consumerCount; i++) {
            consumers[i] = new Thread(consume, "consumer-" + i);
            consumers[i].start();
        }

        for (int value = 1; value <= 5; value++) {
            queue.put(new Work(value));
        }

        for (int i = 0; i < consumerCount; i++) {
            queue.put(End.INSTANCE);
        }

        for (Thread consumer : consumers) {
            consumer.join();
        }

        List<Integer> sorted = new ArrayList<>(results);
        Collections.sort(sorted);
        check(sorted.equals(List.of(1, 4, 9, 16, 25)));
        System.out.println("results: " + sorted);
        System.out.println("consumers stopped: " + consumerCount);
        System.out.println("queue empty: " + queue.isEmpty());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 QueueEndSignalDemo.java
java QueueEndSignalDemo
```

Stdout:

```text
offer(null): NullPointerException
poll(empty): null, not an end signal
results: [1, 4, 9, 16, 25]
consumers stopped: 2
queue empty: true
```

Phép thử `poll()` diễn ra trước khi tạo producer/consumer khác, nên nó nhận `null` một cách xác định. Chương trình vẫn tiếp tục tạo công việc sau đó, minh họa vì sao `null` không phải “hết dữ liệu vĩnh viễn”.

Main đưa cả năm `Work` vào trước, sau đó mới đưa hai dấu `End.INSTANCE`. `ArrayBlockingQueue` giữ FIFO nên không có dấu nào vượt lên trước những công việc còn xếp hàng. Một consumer có thể đang xử lý việc cuối khi consumer kia đã nhận dấu và thoát; main vẫn đợi cả hai bằng `join()`.

Hai consumer có thể xử lý xong các số theo thứ tự khác nhau. Danh sách kết quả được đồng bộ khi thêm, và chỉ được sao chép/sắp xếp sau khi cả hai luồng đã kết thúc. Vì vậy stdout cuối là ổn định mà không khẳng định thứ tự hoàn tất nghiệp vụ luôn FIFO.

Trong ví dụ, xử lý một việc là thao tác đồng bộ ngay trong consumer và không có lỗi ngoài giao thức được chủ động tạo ra. Nếu consumer chuyển việc sang tác vụ bất đồng bộ khác rồi thoát, chỉ `join()` consumer không đủ để chứng minh những tác vụ con ấy đã hoàn tất; phải đợi kết quả của chúng riêng.

## 6. Nhiều producer: cần bên điều phối thời điểm kết thúc

Nếu có nhiều producer, việc một producer đã gửi hết việc của mình không chứng minh mọi producer khác cũng đã xong. Không để mỗi producer tùy ý gửi dấu kết thúc toàn cục ngay khi nó hoàn thành.

```text
Producer A: Work A1 -> kết thúc
Producer B: đang tính toán ---------> Work B1

Gửi End ngay sau khi A kết thúc:
Consumer có thể đọc End rồi thoát trước khi B đưa B1 vào.
```

Một cách điều phối là đợi tất cả producer kết thúc thành công bằng `join`, `Future` hoặc một cơ chế đếm hoàn tất, đồng thời bảo đảm không có producer mới được phép bắt đầu. Sau đó bên điều phối mới gửi đủ dấu cho các consumer.

Việc “producer đã kết thúc” cũng cần phân biệt thành công với thất bại. Nếu producer lỗi giữa chừng, không nên gửi dấu kết thúc rồi báo toàn bộ công việc đã thành công. Ứng dụng phải truyền lỗi hoặc đưa ra kết quả cho biết luồng dữ liệu bị hủy/mất một phần, tùy yêu cầu.

## 7. Kết thúc bình thường khác với hủy bằng ngắt luồng

| Cơ chế | Mục tiêu thường gặp | Điều cần hiểu rõ |
| --- | --- | --- |
| Dấu kết thúc trong FIFO | Ngừng sau những công việc đã xếp trước dấu | Cần đúng thứ tự producer và đủ dấu cho consumer |
| `interrupt()` | Yêu cầu tác vụ hợp tác dừng, kể cả lúc đang chờ `take`/`put` | Có thể còn công việc chưa xử lý; tác vụ phải phản hồi đúng |
| Timed `poll` kèm trạng thái vòng đời | Định kỳ kiểm tra yêu cầu kết thúc hoặc hủy | Một lần `null` không đủ để quyết định kết thúc |

`take()` và `put()` có thể ném `InterruptedException`. Nếu tầng hiện tại cho phép, chuyển ngoại lệ lên bên gọi. Nếu bắt trong `Runnable` không chuyển được lên, khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` rồi kết thúc tác vụ là một chính sách thường dùng.

Không nuốt ngoại lệ rồi tiếp tục chờ vô hạn. Cũng không khẳng định rằng ngắt một consumer đã tự đưa lại công việc nó đang xử lý vào hàng đợi: hàng đợi không tự biết công việc đó đã xử lý được bao nhiêu. Thử lại, bù trừ hoặc ghi nhận thất bại cần được thiết kế riêng.

Một cờ `volatile boolean stopped` có thể công bố yêu cầu dừng, nhưng không tự đánh thức luồng đang chờ trong `take()`. Nếu chọn giao thức bằng cờ, cần ghép nó với cơ chế chờ/hủy phù hợp; không chỉ đổi cờ rồi mong consumer đang bị chặn sẽ kiểm tra ngay.

## 8. Các lỗi trong quá trình dừng thường bị bỏ sót

- **Gửi dấu bằng `offer` rồi bỏ qua kết quả:** hàng đợi hữu hạn có thể đang đầy, `offer` trả `false`, consumer không bao giờ nhận được dấu. Dùng chính sách gửi có xác nhận và xử lý thất bại.
- **Chờ gửi dấu khi consumer đã lỗi và thoát:** `put` có thể kẹt khi hàng đợi đầy mà không còn ai lấy. Bên điều phối cần biết lỗi consumer và có chính sách hủy có giới hạn.
- **Chỉ gửi một dấu cho nhiều consumer:** một bên thoát, các bên còn lại có thể chờ mãi ở `take`.
- **Dùng `clear()` để dừng:** thao tác này xóa việc đang chờ nhưng không đánh thức consumer đang đợi dữ liệu và không biểu thị kết thúc hợp lệ.
- **Dùng `isEmpty()` để báo thành công:** dữ liệu có thể đã được lấy ra nhưng đang xử lý hoặc đã thất bại.
- **Kết thúc tiến trình để thay cho giao thức dừng:** việc tiến trình thoát không bảo đảm đã lưu kết quả hay hoàn tất công việc.

Dấu kết thúc cũng cần được vận chuyển theo cơ chế thực của từng loại hàng đợi. Với `SynchronousQueue`, không có vùng đệm để đặt dấu rồi rời đi; chính lần gửi dấu phải ghép với một consumer đang nhận. Với hàng đợi ưu tiên hoặc trì hoãn, phải xem quy tắc lấy dữ liệu trước khi dùng một dấu như điểm kết thúc.

## 9. Dừng executor không tự đóng hàng đợi do ứng dụng sở hữu

Nếu consumer là một vòng lặp dài bên trong tác vụ của `ExecutorService`, gọi `shutdown()` không tự đóng `BlockingQueue` mà consumer đang đọc. `shutdown()` ngừng nhận thêm tác vụ mới của executor và cho các tác vụ đã nộp tiếp tục; vòng lặp consumer chưa có điều kiện thoát vẫn có thể chạy/chờ mãi.

`shutdownNow()` cố gắng ngắt các tác vụ đang chạy, nên consumer phải xử lý ngắt đúng; đây không phải lệnh cưỡng chế bảo đảm mọi nghiệp vụ đã dừng ngay. `awaitTermination` có thể dùng để đợi executor kết thúc và phải kiểm tra kết quả của lần đợi. Chi tiết vòng đời được mô tả trong [ExecutorService — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html).

Trong kết thúc bình thường, hãy làm cho vòng consumer kết thúc bằng giao thức đã chọn, đợi kết quả xử lý, rồi giải phóng tài nguyên tương ứng. Trong hủy do lỗi, phải thể hiện rõ công việc nào chưa hoàn tất thay vì báo thành công chỉ vì các luồng đã dừng.

## 10. Tự kiểm tra

1. Vì sao không dùng `queue.put(null)` để báo hết việc? Vì `BlockingQueue` cấm phần tử `null` và ném `NullPointerException`.
2. Một lần timed `poll` trả `null` có chứng minh không còn producer không? Không; nó chỉ cho biết lần chờ đó chưa lấy được dữ liệu.
3. Có ba consumer, mỗi bên dừng khi lấy một dấu. Theo giao thức trong bài cần bao nhiêu dấu? Ba, sau khi tất cả producer đã hoàn thành việc gửi.
4. Producer A đã xong nhưng producer B còn chạy. Có nên gửi dấu kết thúc toàn cục ngay không? Không; cần đợi hoặc điều phối đầy đủ các producer.
5. Hàng đợi rỗng có nghĩa mọi việc đã xử lý thành công không? Không; có thể có việc đang xử lý hoặc đã lỗi sau khi lấy ra.
6. Đổi một cờ dừng có tự đánh thức `take()` không? Không; cần cơ chế đánh thức/hủy hoặc cách chờ có thời hạn thích hợp.
