# Kết thúc pipeline khi không có thao tác đóng hàng đợi

## 1. Hàng đợi rỗng chưa có nghĩa là pipeline đã xong

Một pipeline thường gồm bên tạo dữ liệu (producer), hàng đợi trung gian và bên xử lý dữ liệu (consumer). Với `BlockingDeque`, bên nhận có thể gọi `takeFirst()` để ngủ chờ khi chưa có dữ liệu.

Sau khi bên gửi cuối cùng hoàn tất, deque có thể trở thành rỗng. Tuy nhiên, bên nhận không thể nhìn vào trạng thái rỗng để biết:

- Đây chỉ là khoảng nghỉ giữa hai lần gửi.
- Một bên gửi vẫn đang tính toán phần tử tiếp theo.
- Tất cả bên gửi đã kết thúc vĩnh viễn.
- Một bên gửi đã gặp lỗi và không còn khả năng tạo dữ liệu.

`BlockingDeque` không có thao tác `close()` để chuyển sang trạng thái “không nhận thêm dữ liệu, lấy hết rồi kết thúc”. Cần tự thiết kế **giao thức kết thúc** giữa các thành phần. Tài liệu [BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html), là giao diện cha của `BlockingDeque`, nêu rõ việc đóng và dấu báo hết luồng dữ liệu thuộc cách phối hợp của ứng dụng.

Điểm cần giữ trong mô hình tư duy: **deque quản lý phần tử; bên điều phối quản lý vòng đời pipeline**. Một thao tác thêm hoặc lấy an toàn giữa nhiều luồng không tự biến toàn bộ chuỗi “ngừng gửi → xử lý hết → kết thúc” thành một thao tác nguyên tử.

## 2. Xác định mục tiêu kết thúc trước khi chọn kỹ thuật

Có hai mục tiêu khác nhau:

| Mục tiêu | Ý nghĩa | Cách phối hợp thường dùng |
| --- | --- | --- |
| Kết thúc có trật tự | Không nhận việc mới; xử lý hết việc đã chấp nhận; đợi các tác vụ hoàn tất | Dấu kết thúc, hoặc trạng thái hết bên gửi kết hợp lấy có thời gian chờ |
| Dừng do lỗi hoặc hủy | Yêu cầu các tác vụ thoát; quyết định riêng phần việc chưa hoàn tất | Ngắt hợp tác, hạn chót, ghi nhận lỗi và công việc dang dở |

Không gọi việc dừng do lỗi là “xử lý hết thành công”. Một pipeline có thể đã lấy hết phần tử khỏi deque nhưng vẫn còn phần việc đang xử lý, hoặc một phần dữ liệu đã thất bại.

Trong bài này, đường thành công dùng dấu kết thúc; đường lỗi dùng giới hạn thời gian chờ và yêu cầu ngắt các tác vụ do ví dụ sở hữu. Các cơ chế này vẫn áp dụng trong Java hiện nay. Mã đầy đủ sử dụng Java 17 trở lên.

## 3. Dấu kết thúc: dữ liệu điều khiển đi qua cùng hàng đợi

Dấu kết thúc, thường gọi là end-of-stream marker hoặc poison pill, là một phần tử đặc biệt do ứng dụng định nghĩa. Bên nhận lấy được nó thì rời vòng lặp thay vì xử lý như dữ liệu nghiệp vụ.

Ví dụ về ý tưởng:

```text
đầu deque                                      cuối deque
   [Data A] [Data B] [Data C] [End] [End]
       ↑ lấy bằng takeFirst()               thêm bằng putLast()
```

Để giao thức này đúng, cần xác định các điều kiện:

1. Tất cả bên gửi đã hoàn tất việc thêm dữ liệu trước khi phát dấu kết thúc.
2. Dữ liệu và dấu kết thúc cùng đi theo thứ tự FIFO: thêm ở cuối, lấy ở đầu.
3. Số dấu bằng số bên nhận tham gia giao thức, nếu mỗi bên nhận lấy một dấu rồi dừng.
4. Bên nhận không xử lý dấu như dữ liệu và không lấy thêm dữ liệu sau khi nhận dấu.
5. Có cách phát hiện lỗi hoặc hết thời gian, vì dấu có thể không tới được mọi bên nhận khi một thành phần hỏng.

Dấu không đóng deque về mặt API. Nếu mã khác vẫn giữ tham chiếu và tiếp tục thêm dữ liệu sau dấu, deque vẫn có thể chấp nhận. Việc ngăn gửi mới phải được bảo đảm bởi quyền sở hữu và giao thức của ứng dụng.

### Vì sao không dùng null hoặc một chuỗi tùy ý?

`BlockingDeque` không chấp nhận `null`; `null` của `poll` còn mang ý nghĩa “không lấy được phần tử”. Dùng chuỗi như `"END"` dễ đụng với dữ liệu thật.

Nên dùng kiểu thông điệp riêng. Ví dụ Java 17:

```java
// Các kiểu thành viên bên trong một lớp.
sealed interface Message permits Data, End {}

record Data(int value) implements Message {}

enum End implements Message {
    INSTANCE
}
```

`Data` chứa dữ liệu, còn `End.INSTANCE` có vai trò điều khiển. Dữ liệu số nguyên không thể bị hiểu nhầm là dấu. Một đối tượng enum có thể được thêm nhiều lần vào deque; mỗi lần thêm vẫn tạo một phần tử cần được lấy riêng.

## 4. Phối hợp nhiều bên gửi và nhiều bên nhận

### 4.1. Một bên gửi xong chưa đủ

Giả sử có hai bên gửi P1 và P2. Nếu P1 xong trước và tự thêm hai dấu cho hai bên nhận, cả hai bên nhận có thể dừng trong lúc P2 còn đang tạo dữ liệu. Phần dữ liệu P2 gửi sau đó không còn bên xử lý.

Cách đơn giản là có một bên điều phối:

```text
chạy các bên nhận
        ↓
chạy các bên gửi
        ↓
đợi TẤT CẢ bên gửi hoàn tất thành công
        ↓
bên điều phối phát đủ dấu kết thúc
        ↓
đợi TẤT CẢ bên nhận hoàn tất thành công
        ↓
xác nhận pipeline hoàn tất
```

Nếu một bên gửi thất bại, không đi tiếp như thể dữ liệu đã đầy đủ. Bên điều phối phải chuyển sang chính sách lỗi.

### 4.2. Hai bên nhận cần hai dấu trong giao thức này

Một dấu được lấy ra sẽ không còn trong deque. Nếu chỉ thêm một dấu cho hai bên nhận, một bên có thể dừng, bên còn lại tiếp tục mắc tại `takeFirst()`.

Không dựa vào công bằng của lịch chạy để phân phối dấu. Mỗi bên nhận thoát ngay sau dấu đầu tiên, nên không thể lấy mất dấu thứ hai; dấu còn lại dành cho một bên nhận chưa thoát.

Có thể thiết kế biến thể truyền lại một dấu, nhưng phải chứng minh việc truyền lại không mắc khi deque đầy, không thất lạc khi bên nhận lỗi và vẫn đúng khi số bên nhận thay đổi. Với số lượng bên nhận cố định, phát đủ dấu thường dễ kiểm tra hơn.

## 5. Đặc thù hai đầu của BlockingDeque

FIFO là điều kiện của giao thức minh họa, không phải điều kiện tự có của mọi cách dùng deque. Theo [hợp đồng BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html), ứng dụng có thể thêm và lấy ở cả hai đầu.

Các cách dùng dưới đây có thể làm dấu vượt qua dữ liệu:

| Cách dùng | Vấn đề với dấu kết thúc |
| --- | --- |
| Thêm dữ liệu và dấu bằng `putLast`, nhưng lấy bằng `takeLast` | Dấu mới thêm có thể được lấy trước dữ liệu cũ |
| Thêm dấu bằng `putFirst` trong khi dữ liệu còn chờ | Bên lấy ở đầu có thể dừng ngay, bỏ lại dữ liệu |
| Một số bên nhận lấy ở đầu, số khác lấy ở cuối | Không còn suy luận FIFO chung cho dấu |
| Dữ liệu ưu tiên được thêm vào đầu sau khi đã phát dấu | Thời điểm “không còn dữ liệu mới” đã bị phá vỡ |

Với pipeline dùng hai đầu để ưu tiên hoặc phân phối công việc, cần một giao thức vòng đời phù hợp với cách lấy thực tế. Không sao chép nguyên mẫu poison pill của hàng đợi FIFO rồi giả định vẫn đúng.

Ngay cả trong FIFO, dấu chỉ đi sau dữ liệu **đang nằm trong deque**. Một bên nhận có thể đã lấy dữ liệu và còn đang xử lý, trong khi bên nhận khác đã gặp dấu và thoát. Vì vậy vẫn phải đợi mọi bên nhận hoàn tất, không chỉ quan sát một dấu đã được nhận.

## 6. Ví dụ chạy đầy đủ: hai bên gửi, hai bên nhận

Ví dụ dùng:

- Hai bên gửi tạo các số từ 1 đến 6.
- Hai bên nhận cộng tổng và đếm số phần tử đã xử lý.
- Deque giới hạn dung lượng 2 để việc chờ chỗ trống là tình huống bình thường.
- Một bộ thực thi bốn luồng để cả bên gửi và bên nhận có thể hoạt động.
- Bên điều phối đợi hai bên gửi thành công trước khi thêm hai dấu.
- Các lần đợi kết quả hoặc thêm dấu có giới hạn thời gian; lỗi không bị biến thành kết quả thành công.

Lưu tệp **PipelineCompletionDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class PipelineCompletionDemo {
    sealed interface Message permits Data, End {}

    record Data(int value) implements Message {}

    enum End implements Message {
        INSTANCE
    }

    private static Void produce(
            BlockingDeque<Message> deque, int first, int last)
            throws InterruptedException {
        for (int value = first; value <= last; value++) {
            deque.putLast(new Data(value));
        }
        return null;
    }

    private static Void consume(
            BlockingDeque<Message> deque,
            AtomicInteger count,
            AtomicInteger sum,
            AtomicInteger ended) throws InterruptedException {
        while (true) {
            Message message = deque.takeFirst();
            if (message == End.INSTANCE) {
                ended.incrementAndGet();
                return null;
            }

            Data data = (Data) message;
            sum.addAndGet(data.value());
            count.incrementAndGet();
        }
    }

    private static void stopAfterFailure(ExecutorService pool) {
        pool.shutdownNow();
        try {
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Workers did not terminate");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.err.println("Cleanup wait interrupted");
        }
    }

    public static void main(String[] args) throws Exception {
        int consumerCount = 2;
        BlockingDeque<Message> deque = new LinkedBlockingDeque<>(2);
        AtomicInteger count = new AtomicInteger();
        AtomicInteger sum = new AtomicInteger();
        AtomicInteger ended = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            List<Future<Void>> consumers = new ArrayList<>();
            for (int i = 0; i < consumerCount; i++) {
                consumers.add(pool.submit(
                        () -> consume(deque, count, sum, ended)));
            }

            List<Future<Void>> producers = List.of(
                    pool.submit(() -> produce(deque, 1, 3)),
                    pool.submit(() -> produce(deque, 4, 6)));

            for (Future<Void> producer : producers) {
                producer.get(5, TimeUnit.SECONDS);
            }

            for (int i = 0; i < consumerCount; i++) {
                if (!deque.offerLast(End.INSTANCE, 5, TimeUnit.SECONDS)) {
                    throw new TimeoutException("Cannot enqueue end marker");
                }
            }

            for (Future<Void> consumer : consumers) {
                consumer.get(5, TimeUnit.SECONDS);
            }

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Executor did not terminate");
            }

            System.out.println("processed: " + count.get());
            System.out.println("sum: " + sum.get());
            System.out.println("consumers ended: " + ended.get());
            System.out.println("deque empty: " + deque.isEmpty());
            System.out.println("executor terminated: " + pool.isTerminated());
        } finally {
            if (!pool.isTerminated()) {
                stopAfterFailure(pool);
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac PipelineCompletionDemo.java
java PipelineCompletionDemo
```

Stdout khi thành công:

```text
processed: 6
sum: 21
consumers ended: 2
deque empty: true
executor terminated: true
```

### Vì sao ví dụ kết thúc được?

Các `Future` của bên gửi hoàn tất thành công nghĩa là sáu lần thêm dữ liệu đã hoàn tất. Sau thời điểm này, không còn bên gửi nào thêm `Data`.

Hai dấu được thêm ở cuối, sau mọi dữ liệu còn chờ. Mỗi bên nhận lấy từ đầu và thoát ngay khi nhận một dấu. Việc gọi `get` trên tất cả `Future` của bên nhận bảo đảm quá trình xử lý trong các tác vụ đó đã hoàn tất thành công.

Chương trình chỉ in sau các bước kiểm tra trên nên tổng và số lượng là xác định. Thứ tự từng số được xử lý, số lượng mỗi bên nhận xử lý và thời điểm mỗi bên nhận nhận dấu vẫn phụ thuộc lịch chạy; chương trình không giả định chúng cố định.

### Giới hạn cần hiểu từ mã mẫu

Năm giây là giới hạn cho **từng lần đợi**, không phải hạn chót chung năm giây cho cả pipeline. Khi ứng dụng cần một hạn chót chung, phải tính thời gian còn lại rồi truyền vào từng thao tác chờ.

Nếu `produce` hoặc `consume` ném lỗi, `Future.get` truyền lỗi thông qua `ExecutionException`. Ví dụ để lỗi đi ra khỏi `main`, đồng thời `finally` yêu cầu dừng bộ thực thi. Nếu một tác vụ chưa báo lỗi nhưng mắc chờ, lần `get` có thời gian chờ sẽ giúp bên điều phối không đợi vô hạn.

Đường dọn dẹp chỉ cố gắng ngắt và đợi có giới hạn. Nếu thay phép cộng bằng mã không phản hồi ngắt, ví dụ không thể bảo đảm cưỡng chế mã đó kết thúc; nó báo khi các luồng chưa dừng. Phần việc dang dở cần chính sách riêng của ứng dụng.

## 7. Deque đầy không được làm bước kết thúc mắc vĩnh viễn

Dấu kết thúc cũng chiếm dung lượng như một phần tử bình thường. Với deque giới hạn, phát dấu có thể phải đợi bên nhận lấy bớt phần tử.

Không cần dành sẵn số ô trống bằng số bên nhận trong ví dụ: trong lúc bên điều phối lần lượt thêm dấu, các bên nhận vẫn hoạt động và giải phóng dung lượng. Điều kiện cần là chúng còn có khả năng tiến triển.

Điểm nguy hiểm xuất hiện khi mọi bên nhận đã lỗi nhưng bên điều phối vẫn `putLast(End)` vô hạn vào deque đầy. Vì vậy ví dụ dùng `offerLast` có thời gian chờ và kiểm tra kết quả. Nếu không phát đủ dấu, pipeline thất bại; không được in “đã kết thúc thành công”.

Không thay bằng `addLast` rồi bỏ qua ngoại lệ khi đầy, hoặc `offerLast` không chờ rồi bỏ qua `false`. Cả hai cách đều có thể làm thiếu dấu và để một bên nhận chờ mãi.

## 8. Một lựa chọn khác: hết bên gửi kết hợp poll có thời gian chờ

Không phải pipeline nào cũng thuận tiện đưa phần tử điều khiển vào luồng dữ liệu. Có thể dùng trạng thái “không còn bên gửi” với `pollFirst` có thời gian chờ, nhưng phải thiết kế khả năng nhìn thấy giữa các luồng và thứ tự kiểm tra.

Phác thảo sau chỉ đúng khi:

- Bên điều phối chỉ đặt `producersDone` sau khi mọi bên gửi hoàn tất thành công.
- Sau khi cờ được đặt, tuyệt đối không có lần thêm dữ liệu mới.
- `producersDone` là `AtomicBoolean`.
- Mỗi bên nhận tự xử lý tuần tự và không gửi công việc sang một tác vụ nền khác.

```java
// Đoạn thân bên nhận; không phải chương trình độc lập.
while (true) {
    Message message = deque.pollFirst(100, TimeUnit.MILLISECONDS);
    if (message != null) {
        process(message);
        continue;
    }

    if (producersDone.get() && deque.isEmpty()) {
        break;
    }
}
```

`process` do ứng dụng cung cấp; `InterruptedException` từ thao tác chờ phải được truyền lên hoặc xử lý tại ranh giới tác vụ.

Vì sao còn kiểm tra deque sau khi đọc cờ? Một lần `poll` có thể trả `null`, rồi bên gửi thêm phần tử cuối cùng, rồi bên điều phối đặt cờ. Nếu chỉ kiểm tra cờ sau `poll == null` và dừng ngay, bên nhận có thể bỏ sót dữ liệu vừa được thêm. Khi đã đọc được `true`, kiểm tra rỗng tiếp theo chỉ đủ ý nghĩa vì giao thức cấm mọi lần thêm trong tương lai.

Cách này có độ trễ phản hồi liên quan thời gian chờ và vẫn cần xử lý lỗi bên gửi. Không đặt cờ “hoàn tất thành công” trong `finally` của một bên gửi đã thất bại rồi coi dữ liệu là đầy đủ. Khi một thành phần lỗi, bên quản lý cần ghi nhận lỗi và chuyển cả pipeline sang chính sách dừng do lỗi.

## 9. ExecutorService.shutdown không đóng deque

Bộ thực thi và deque là hai đối tượng có vòng đời khác nhau.

- `shutdown()` ngừng nhận **tác vụ mới vào bộ thực thi**; các tác vụ đã nhận vẫn được thực thi. Nó không chèn dấu và không đánh thức bên nhận đang `takeFirst()`.
- `awaitTermination` đợi bộ thực thi kết thúc; nó không tự làm cho vòng lặp bên nhận thoát.
- `shutdownNow()` cố gắng ngắt tác vụ đang chạy; nó không phải giao thức xử lý hết dữ liệu và không bảo đảm mọi tác vụ đều phản hồi.
- Danh sách tác vụ chưa chạy mà `shutdownNow()` trả về thuộc hàng chờ của bộ thực thi, không phải các phần tử đang trong `BlockingDeque` nghiệp vụ.

Các khác biệt này được mô tả trong [ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

Một lỗi bố trí tài nguyên khác là đưa mọi bên gửi vào một nhóm luồng đã bị lấp đầy bởi các bên nhận đang chờ dữ liệu, khiến bên gửi không bao giờ được chạy. Chiều ngược lại cũng có thể xảy ra: mọi luồng chạy bên gửi đang chờ deque đầy, còn bên nhận chưa được cấp luồng. Hãy bảo đảm các thành phần phụ thuộc nhau có khả năng được thực thi đồng thời, hoặc dùng cách tổ chức thực thi không tạo vòng chờ đó.

## 10. Pipeline nhiều giai đoạn cần kết thúc từng liên kết

Với cấu trúc:

```text
Nguồn → deque A → nhóm xử lý 1 → deque B → nhóm xử lý 2 → Kết quả
```

Dấu của deque A chỉ cho nhóm xử lý 1 biết nguồn đã kết thúc. Nó chưa chứng minh nhóm này đã hoàn tất mọi kết quả cần ghi vào deque B.

Cách phối hợp dễ hiểu:

1. Ngừng nguồn và xác nhận mọi tác vụ nguồn hoàn tất.
2. Kết thúc nhóm xử lý 1 qua giao thức của deque A.
3. Đợi tất cả tác vụ nhóm 1 hoàn tất việc ghi kết quả vào B.
4. Phát đủ dấu cho nhóm 2 trên deque B.
5. Đợi toàn bộ nhóm 2 hoàn tất.

Không để tác vụ đầu tiên của nhóm 1 gặp dấu tự tuyên bố B đã hết dữ liệu: các tác vụ khác của nhóm 1 có thể vẫn còn đang xử lý. Số dấu cho mỗi liên kết tính theo số bên nhận ở giai đoạn tiếp theo, không nhất thiết bằng số bên nhận ở giai đoạn trước.

Nếu tác vụ nhóm 1 giao xử lý cho tác vụ con rồi trả về trước khi tác vụ con hoàn tất, việc đợi nhóm 1 cũng chưa đủ. Phạm vi “hoàn tất” phải bao gồm mọi công việc có thể còn tạo dữ liệu xuống dòng sau.

## 11. Kiểm tra giao thức trước khi đưa vào ứng dụng

Những câu hỏi cần trả lời bằng luồng điều khiển cụ thể:

- Ai có quyền quyết định không còn dữ liệu mới? Có bên gửi nào ngoài phạm vi quản lý không?
- Ai phát dấu, phát lúc nào và bao nhiêu dấu?
- Mọi bên nhận có dùng đúng đầu deque mà giao thức yêu cầu không?
- Nếu deque đầy hoặc một bên nhận chết, bên phát dấu thoát bằng cách nào?
- Nếu bên gửi lỗi, lỗi được thông báo ở đâu?
- Đã đợi công việc đang xử lý hoàn tất hay mới chỉ nhìn thấy deque rỗng?
- Khi hủy giữa chừng, dữ liệu đã lấy nhưng chưa hoàn tất được bỏ, lưu lại hay thử lại thế nào?

Deque trong bộ nhớ không tự cung cấp khôi phục sau khi tiến trình chết, xác nhận xử lý bền vững hay bảo đảm đúng một lần. Nếu nghiệp vụ cần những thuộc tính đó, giao thức hoàn tất còn phải phối hợp với lưu trữ, giao dịch hoặc cơ chế thông điệp phù hợp.

## 12. Thực hành

1. Thay số bên nhận thành 3 trong ví dụ và cấp đủ luồng cho cả ba bên nhận cùng hai bên gửi. Giữ số dấu bằng số bên nhận; kiểm tra tổng vẫn là 21 và số bên nhận kết thúc là 3.
2. Dùng deque dung lượng 1. Giải thích vì sao vẫn có thể phát tuần tự nhiều dấu khi các bên nhận còn hoạt động.
3. Trên giấy, đổi `takeFirst` thành `takeLast` và vẽ một lịch xen kẽ khiến dấu được nhận trước dữ liệu. Không dùng kết quả một lần chạy làm bằng chứng giao thức vẫn đúng.
4. Cho một bên gửi ném ngoại lệ trước khi tạo đủ dữ liệu. Kiểm tra chương trình báo thất bại và đi qua đường dọn dẹp, không in bộ kết quả thành công.
5. Mở rộng thành hai giai đoạn. Xác định chính xác điều kiện trước khi bên điều phối được phát dấu vào deque thứ hai.

Giao thức kết thúc đúng phải chứng minh được cả ba điều: không còn bên gửi có thể thêm việc, việc đã chấp nhận đã được xử lý theo chính sách, và mọi tác vụ thuộc pipeline đã kết thúc hoặc đã được báo lỗi rõ ràng.
