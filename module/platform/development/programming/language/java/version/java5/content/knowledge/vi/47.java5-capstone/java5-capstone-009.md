# Xây dựng luồng xử lý có BlockingQueue và ExecutorService

## 1. Bài toán: nguồn tạo việc nhanh hơn nơi xử lý

Cần xây một luồng xử lý gồm một nơi tạo công việc và nhiều nơi xử lý. Nếu tạo một luồng mới cho mỗi phần tử hoặc đưa tất cả dữ liệu vào một hàng đợi không giới hạn, hệ thống có thể hết bộ nhớ trước khi xử lý xong.

Bài thực hành chọn mô hình:

```text
Luồng điều phối tạo Work
          |
  ArrayBlockingQueue có giới hạn
          |
     Ba tác vụ worker
          |
  Kết quả riêng của từng worker
          |
Luồng điều phối thu kết quả và sắp theo id
```

Hai công cụ có vai trò khác nhau:

- `BlockingQueue` vận chuyển thông điệp và tạo điều tiết khi nơi xử lý theo không kịp.
- `ExecutorService` chạy các tác vụ worker và quản lý vòng đời luồng.

Mục tiêu không chỉ là “nhiều luồng chạy được”. Lời giải cần có giới hạn đầu vào đang chờ, thu được lỗi worker, dừng đúng lúc, xử lý gián đoạn và không để producer chờ mãi khi consumer đã thất bại.

Ví dụ dùng Java 17+, không dùng API xem trước và không phụ thuộc một máy chủ ngoài.

## 2. Chọn thông điệp bất biến và phân chia dữ liệu

Công việc gồm `id` và một số nguyên cần bình phương. Worker tạo một `Result` mới, không sửa đối tượng đầu vào.

Bài sử dụng record để diễn tả dữ liệu, và hai loại thông điệp:

| Thông điệp | Ý nghĩa |
| --- | --- |
| `Work` | Một phần tử cần xử lý |
| `Stop.INSTANCE` | Tín hiệu kết thúc cho một worker |

Thông điệp dừng có kiểu riêng, không dùng `null`: BlockingQueue không chấp nhận phần tử null. Cũng không dành một giá trị số hợp lệ như 0 để làm tín hiệu nếu 0 có thể là dữ liệu nghiệp vụ.

Hàng đợi hỗ trợ công bố dữ liệu giữa các luồng: các thao tác trước khi đưa một phần tử vào queue có quan hệ happens-before với thao tác sau khi phía kia lấy/truy cập phần tử đó, theo [BlockingQueue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Điều đó không làm mọi đối tượng bên trong phần tử tự an toàn nếu tiếp tục bị sửa. Nếu thông điệp chứa một mảng hoặc danh sách mutable, cần quy định quyền sở hữu hoặc sao chép phù hợp.

## 3. Queue có giới hạn và cách chờ

Trong bài:

```java
BlockingQueue<Message> queue = new ArrayBlockingQueue<>(8);
```

Dung lượng 8 là số thông điệp chờ tối đa, không phải số worker và không phải giới hạn tổng số kết quả.

Các cách thao tác chính:

| Thao tác | Khi chưa thể thực hiện |
| --- | --- |
| `add(e)` | Báo lỗi nếu đầy |
| `offer(e)` | Trả false nếu đầy |
| `put(e)` | Chờ đến khi có chỗ hoặc bị gián đoạn |
| `offer(e, timeout, unit)` | Chờ có thời hạn |
| `take()` | Chờ đến khi có phần tử hoặc bị gián đoạn |
| `poll(timeout, unit)` | Chờ có thời hạn rồi có thể trả null |

Khi producer nhanh hơn consumer, chờ ở queue làm tốc độ nhận thêm việc bị giới hạn bởi phía xử lý. Tuy nhiên, nếu consumer chết mà producer dùng `put()` vô hạn, producer có thể bị kẹt ở queue đầy.

Lời giải dùng `offer()` có thời hạn ngắn, định kỳ kiểm tra Future của worker và áp dụng một thời hạn tổng cho công việc. Đây là chờ có điều kiện, không phải vòng quay liên tục hỏi `queue.isEmpty()`.

`ArrayBlockingQueue` giữ thứ tự FIFO của phần tử và có dung lượng cố định, theo [ArrayBlockingQueue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html). Nó không bảo đảm các worker hoàn tất tính toán theo cùng thứ tự lấy việc.

Không viết `if (queue.remainingCapacity() > 0) queue.add(work)` để bảo đảm thêm thành công trong môi trường nhiều producer. Trạng thái có thể đổi giữa hai thao tác; dùng chính thao tác queue có hành vi chờ/thất bại phù hợp.

## 4. Tổ chức executor để tránh tự chặn nhau

Luồng main làm producer/điều phối; executor chỉ chạy ba worker dài hạn. Cả ba worker được gửi trước khi bắt đầu nhập dữ liệu.

Một thiết kế sai dễ gặp là dùng pool một luồng, gửi producer trước và consumer sau. Producer lấp đầy queue rồi chờ chỗ, trong khi consumer chưa có luồng để chạy. Số lượng công việc nằm trong queue không tự tạo thêm năng lực thực thi.

`Executors.newFixedThreadPool(3)` có hàng đợi tác vụ nội bộ không giới hạn. Trong bài chỉ gửi **ba tác vụ worker**, không gửi một task mới cho mỗi Work, nên số task nội bộ không tăng theo dữ liệu. Hợp đồng factory được mô tả trong [Executors API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html#newFixedThreadPool(int)).

Cần phân biệt:

```text
Hàng đợi tác vụ của executor:
    chỉ chứa các tác vụ worker đã submit

Hàng đợi Work của ứng dụng:
    chứa phần tử nghiệp vụ, được giới hạn ở 8
```

Nếu thay thiết kế thành mỗi Work lại `submit()` một tác vụ, phải xem lại giới hạn hàng đợi executor và cách từ chối/điều tiết; không mặc định queue ứng dụng vẫn giới hạn được toàn hệ thống.

## 5. Kết thúc bình thường khác với hủy do lỗi

BlockingQueue không có phương thức đóng chung để báo hết dữ liệu. Bài dùng tín hiệu dừng:

1. Producer gửi hết Work.
2. Sau đó gửi một Stop cho mỗi worker.
3. Mỗi worker lấy Stop thì trả kết quả và kết thúc.
4. Luồng điều phối chờ các Future hoàn tất.

Vì Work được đưa vào FIFO trước các Stop, tín hiệu dừng không đi trước những Work còn đang chờ. Tuy vậy, có worker lấy Stop khi worker khác vẫn xử lý phần tử đã lấy trước đó; phải chờ tất cả Future mới kết luận toàn bộ lô xong.

Nếu có nhiều producer, cần một nơi điều phối biết **tất cả producer đã xong** trước khi gửi Stop. Không để producer đầu tiên xong tự dừng toàn bộ consumer khi producer khác còn gửi dữ liệu.

Đường lỗi dùng cơ chế khác: hủy các Future, yêu cầu executor dừng và gián đoạn worker đang chờ. Không cố nhét các Stop bằng `put()` vô hạn trong `finally`, vì lúc lỗi có thể không còn worker nào đọc queue.

## 6. Thu lỗi bằng Future, không chỉ nhìn isDone

Tác vụ gửi bằng `submit()` có lỗi sẽ ghi nhận lỗi trong Future. Nếu bỏ qua Future, chương trình có thể không biết một worker đã dừng.

`isDone()` chỉ cho biết đã kết thúc theo một cách nào đó: thành công, ngoại lệ hoặc bị hủy. Nó không có nghĩa kết quả thành công.

Trong ví dụ, nếu thấy Future đã xong, điều phối gọi `get()` để làm lỗi hiện ra. Khi thu kết quả cuối, dùng `get()` có thời hạn còn lại. Lỗi tác vụ được đưa tới bên gọi qua `ExecutionException`; hủy có thể đưa `CancellationException`.

Hành vi chờ, lỗi và quan hệ hiển thị dữ liệu sau get được định nghĩa trong [Future API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

Mỗi worker dùng danh sách kết quả riêng. Điều phối chỉ đọc nó sau Future hoàn tất, nên không cần nhiều worker cùng thêm vào một `ArrayList` dùng chung.

## 7. Lời giải Java 17+ chạy đầy đủ

Thời hạn 30 giây là ngân sách cho phần công việc của ví dụ. Giai đoạn dọn executor có các lần chờ riêng; đây không phải cam kết thời gian thực rằng tiến trình luôn kết thúc trong đúng 30 giây.

Lưu thành `QueuePipelineDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class QueuePipelineDemo {
    private static final int WORKERS = 3;

    sealed interface Message permits Work, Stop {
    }

    record Work(int id, int value) implements Message {
    }

    enum Stop implements Message {
        INSTANCE
    }

    record Result(int id, int square) {
    }

    private static long remaining(long deadline) throws TimeoutException {
        long nanos = deadline - System.nanoTime();
        if (nanos <= 0) {
            throw new TimeoutException("Pipeline deadline exceeded");
        }
        return nanos;
    }

    private static void enqueue(
            BlockingQueue<Message> queue, Message message,
            List<Future<List<Result>>> workers, long deadline)
            throws InterruptedException, ExecutionException, TimeoutException {
        for (;;) {
            for (Future<List<Result>> worker : workers) {
                if (worker.isDone()) {
                    worker.get(); // Surface failure or cancellation.
                }
            }
            long wait = Math.min(
                    remaining(deadline), TimeUnit.MILLISECONDS.toNanos(50));
            if (queue.offer(message, wait, TimeUnit.NANOSECONDS)) {
                return;
            }
        }
    }

    private static void terminate(ExecutorService pool) {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
                    System.err.println("Workers did not terminate");
                }
            }
        } catch (InterruptedException interrupted) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    static List<Result> run(boolean injectFailure)
            throws InterruptedException, ExecutionException, TimeoutException {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(8);
        ExecutorService pool = Executors.newFixedThreadPool(WORKERS);
        List<Future<List<Result>>> workers = new ArrayList<>();
        boolean completed = false;
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(30);

        try {
            for (int i = 0; i < WORKERS; i++) {
                workers.add(pool.submit(() -> {
                    List<Result> local = new ArrayList<>();
                    for (;;) {
                        Message message = queue.take();
                        if (message == Stop.INSTANCE) {
                            return List.copyOf(local);
                        }
                        Work work = (Work) message;
                        if (injectFailure && work.id() == 7) {
                            throw new IllegalArgumentException("Injected failure");
                        }
                        local.add(new Result(work.id(),
                                Math.multiplyExact(work.value(), work.value())));
                    }
                }));
            }

            for (int value = 1; value <= 20; value++) {
                enqueue(queue, new Work(value, value), workers, deadline);
            }
            for (int i = 0; i < WORKERS; i++) {
                enqueue(queue, Stop.INSTANCE, workers, deadline);
            }

            List<Result> results = new ArrayList<>();
            for (Future<List<Result>> worker : workers) {
                results.addAll(worker.get(
                        remaining(deadline), TimeUnit.NANOSECONDS));
            }
            results.sort(Comparator.comparingInt(Result::id));
            completed = true;
            return List.copyOf(results);
        } finally {
            if (!completed) {
                for (Future<List<Result>> worker : workers) {
                    worker.cancel(true);
                }
                pool.shutdownNow();
            }
            terminate(pool);
        }
    }

    public static void main(String[] args) throws Exception {
        boolean injectFailure = args.length == 1 && args[0].equals("fail");
        try {
            List<Result> results = run(injectFailure);
            System.out.println("count=" + results.size());
            System.out.println("first=" + results.get(0));
            System.out.println("last=" + results.get(results.size() - 1));
            System.out.println("sum="
                    + results.stream().mapToInt(Result::square).sum());
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw interrupted;
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -Xlint:all -Werror QueuePipelineDemo.java
java QueuePipelineDemo
```

Stdout:

```text
count=20
first=Result[id=1, square=1]
last=Result[id=20, square=400]
sum=2870
```

Worker nào xử lý id nào có thể thay đổi qua từng lần chạy. Output vẫn ổn định vì điều phối thu đủ kết quả rồi sắp theo id.

`Math.multiplyExact()` báo lỗi nếu phép tính vượt phạm vi int; không âm thầm coi số bị tràn là kết quả đúng. Với dữ liệu 1 đến 20, các kết quả đều nằm trong phạm vi.

## 8. Phân tích đường thành công

### Queue chỉ giữ phần việc đang chờ

Tại một thời điểm có tối đa 8 thông điệp trong queue và tối đa 3 Work đang được các worker xử lý. Producer giữ thêm phần tử nó đang chuẩn bị/gửi.

Đó không phải giới hạn toàn bộ bộ nhớ: danh sách kết quả tăng theo số Work. Bài xử lý một lô nhỏ 20 phần tử. Nếu chuyển sang luồng dữ liệu dài hoặc vô hạn, phải thiết kế nơi tiêu thụ kết quả theo dòng hoặc một tầng có giới hạn riêng.

### Không chia sẻ danh sách mutable giữa worker

Mỗi lambda tạo `local` của riêng nó. Khi kết thúc, trả `List.copyOf(local)`. Điều phối ghép các kết quả sau `get()`, rồi trả bản sao không cho sửa cấu trúc.

### Tín hiệu dừng được đếm theo worker

Mỗi worker tiêu thụ một Stop rồi thoát ngay. Gửi một Stop cho ba worker sẽ để hai worker tiếp tục chờ ở `take()`.

### shutdown không tự đánh thức take

`shutdown()` ngừng nhận task mới nhưng không gián đoạn các tác vụ hiện đang chạy. Nếu worker còn chờ queue trống mà không có Stop, chỉ gọi shutdown chưa làm chúng thoát.

Sự khác nhau giữa shutdown, shutdownNow và awaitTermination được mô tả trong [ExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

## 9. Kiểm chứng consumer thất bại mà không treo producer

Chạy chế độ chèn lỗi:

```shell
java QueuePipelineDemo fail
```

Worker nhận id 7 sẽ ném `IllegalArgumentException`. Lệnh kết thúc với lỗi và không in bộ kết quả thành công của lô.

Kỳ vọng quan trọng:

```text
ExecutionException
  nguyên nhân: IllegalArgumentException: Injected failure
```

Đây là mô tả chuỗi nguyên nhân, không phải toàn bộ stack trace cố định. Vị trí lỗi được phát hiện có thể nằm ở kiểm tra Future trong enqueue hoặc lúc get kết quả cuối, tùy lịch chạy.

Khi thoát khỏi phần xử lý vì lỗi:

- Các Future còn hoạt động nhận yêu cầu hủy kèm gián đoạn.
- Pool nhận `shutdownNow()`.
- Worker đang `take()` phản ứng với `InterruptedException`.
- Chương trình không công bố lô thành công chỉ vì một số phần tử đã tính xong.

Không có hoàn tác nghiệp vụ tự động. Nếu thay phép bình phương bằng ghi cơ sở dữ liệu hoặc gọi API, các tác dụng phụ đã xảy ra không tự biến mất khi Future khác thất bại. Cần thiết kế giao dịch, khóa định danh chống lặp hoặc chính sách bù phù hợp.

## 10. Gián đoạn và shutdown là hợp tác

`cancel(true)` và `shutdownNow()` yêu cầu gián đoạn; chúng không cưỡng bức dừng một đoạn mã bất kỳ.

Một worker đang chờ bằng thao tác có hỗ trợ gián đoạn có thể thoát. Nếu tác vụ bỏ qua gián đoạn hoặc kẹt ở thư viện không đáp ứng, chương trình không được giả định đã dừng chỉ vì đã gửi yêu cầu.

Bài sử dụng `awaitTermination()` có thời hạn và thông báo nếu worker chưa kết thúc. Nếu luồng dọn tài nguyên bị gián đoạn, nó yêu cầu dừng và khôi phục trạng thái gián đoạn. Ở luồng main, `InterruptedException` trong phần công việc cũng được giữ lại cho bên gọi.

Không bắt `InterruptedException` rồi lặng lẽ quay lại vòng `take()` như chưa có gì xảy ra, nếu đó là tín hiệu hủy của thiết kế. Ngữ nghĩa gián đoạn nằm trong [Thread API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#interrupt()).

Mã quản lý shutdown viết tường minh để chạy từ JDK 17. Không sao chép trực tiếp cách try-with-resources cho ExecutorService từ tài liệu JDK mới hơn rồi kỳ vọng biên dịch trên JDK 17; đối chiếu [ExecutorService của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).

## 11. Những điều ví dụ không bảo đảm

- Queue trong bộ nhớ không phải hàng đợi bền vững; tiến trình chết có thể mất công việc.
- Một Work lấy khỏi queue không tự có cơ chế giao lại khi worker lỗi.
- Nhiều worker không bảo đảm thứ tự hoàn tất.
- Hủy tác vụ không tự hoàn tác tác dụng phụ.
- Dung lượng queue không giới hạn kích thước từng đối tượng hoặc tổng danh sách kết quả.
- Thời hạn chờ không thay thế timeout riêng của I/O bên ngoài.
- Tăng số worker không tự tăng năng lực của cơ sở dữ liệu hoặc dịch vụ đích.

Các ranh giới này giúp quyết định khi nào mô hình đơn giản phù hợp và khi nào cần một hệ thống điều phối hoặc hàng đợi khác.

## 12. Bài tập mở rộng và tiêu chí tự đánh giá

| Thay đổi/ca kiểm thử | Điều cần kiểm chứng |
| --- | --- |
| Queue có dung lượng 1 | Đầu vào vẫn được xử lý đủ, không dựa vào queue lớn |
| Chỉ có một worker | Có đúng một tín hiệu dừng và kết thúc được |
| Không có Work | Mỗi worker vẫn nhận tín hiệu dừng |
| Worker lỗi giữa lô | Điều phối quan sát lỗi và không kẹt ở queue đầy |
| Producer bị gián đoạn khi chờ | Các worker được yêu cầu dừng, không bỏ sót executor |
| Hàm xử lý bị trì hoãn | Thời hạn tổng và cleanup hoạt động theo hợp đồng |
| Nhiều producer | Chỉ gửi Stop sau khi toàn bộ producer kết thúc |
| Kết quả có kích thước lớn | Bổ sung giới hạn/tiêu thụ ở phía kết quả |

Tiêu chí đạt:

1. Lời giải chính biên dịch sạch và output thành công đúng.
2. Không dùng `Thread.sleep()` để đoán rằng tác vụ đã xong.
3. Không để Future của worker bị bỏ qua.
4. Không chờ vô hạn khi consumer đã lỗi.
5. Có người sở hữu trách nhiệm shutdown pool.
6. Nêu rõ cách kết thúc bình thường khác với cách hủy.
7. Phân biệt “không lặp trong lô chạy thành công” với bảo đảm giao nhận bền vững của một hệ thống thực tế.

## 13. Tự kiểm tra

1. Queue và ExecutorService có cùng nhiệm vụ không? **Không; một bên vận chuyển/điều tiết dữ liệu, một bên thực thi và quản lý tác vụ.**
2. Vì sao dùng queue giới hạn? **Để không tích lũy đầu vào đang chờ mà không có giới hạn.**
3. Vì sao dùng offer có thời hạn trong producer? **Để có cơ hội kiểm tra lỗi worker và thời hạn thay vì chờ mãi khi queue đầy.**
4. isDone có nghĩa worker thành công không? **Không; phải lấy kết quả hoặc lỗi.**
5. Vì sao gửi ba Stop? **Có ba worker và mỗi worker chỉ lấy một Stop trước khi thoát.**
6. shutdown có làm worker đang take thoát ngay không? **Không; cần tín hiệu kết thúc hoặc cơ chế hủy phù hợp.**
7. Queue FIFO có bảo đảm kết quả xong theo thứ tự không? **Không; các worker có thể xử lý với thời gian khác nhau.**
