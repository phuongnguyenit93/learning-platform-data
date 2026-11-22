# Thiết kế đường dừng và đường lỗi cho nhóm tác vụ

## 1. Nhóm tác vụ cần một người chịu trách nhiệm kết thúc

Giả sử một yêu cầu tổng hợp báo cáo phải lấy dữ liệu từ ba nguồn. Chạy ba tác vụ song song mới chỉ giải quyết đường thành công. Thiết kế còn phải trả lời: một nguồn lỗi thì có tiếp tục chờ hai nguồn còn lại không; người dùng hủy yêu cầu thì ai hủy các tác vụ con; hết thời gian thì phần việc đang chạy có thực sự dừng không; tài nguyên đã mở được đóng ở đâu?

**Đường dừng** là chuỗi hành động đưa nhóm tác vụ từ trạng thái đang làm việc sang trạng thái kết thúc có kiểm soát. **Đường lỗi** là cách phát hiện, chuyển và giải thích sự cố cho nơi gọi, đồng thời xử lý các tác vụ còn lại. Hai đường này gặp nhau ở việc yêu cầu hủy, giải phóng tài nguyên và xác minh phần việc đã kết thúc.

Có ba vai trò cần tách rõ:

- **Tác vụ con** thực hiện một phần việc, trả kết quả hoặc báo lỗi và hợp tác khi bị yêu cầu dừng.
- **Bộ điều phối** gửi việc, giữ các `Future`, quan sát kết quả và quyết định kết quả chung.
- **Chủ sở hữu tài nguyên** quyết định đóng executor, kết nối, tệp hoặc đối tượng dùng chung. Bộ điều phối có thể đồng thời là chủ sở hữu, nhưng không mặc nhiên luôn như vậy.

Một `ExecutorService` và một danh sách `Future` không tự tạo ra chính sách “một tác vụ lỗi thì hủy các tác vụ anh em”. Bộ điều phối phải thực hiện chính sách đó.

Các API trong bài thuộc `java.util.concurrent`, xuất hiện từ nền tảng Java 5 và vẫn áp dụng trong Java hiện đại. Ví dụ hoàn chỉnh dùng cú pháp Java 17, biên dịch bằng `--release 17`; không yêu cầu API thử nghiệm.

## 2. Chốt hợp đồng trước khi chọn API

### 2.1. Điều kiện thành công và điều kiện dừng

Với một nhóm hữu hạn, hãy ghi rõ hợp đồng bằng ngôn ngữ nghiệp vụ:

| Chính sách | Khi nào thành công? | Khi một tác vụ lỗi? | Phần việc còn lại |
| --- | --- | --- | --- |
| Tất cả phải thành công | Mọi kết quả bắt buộc đã có và hợp lệ | Nhóm thất bại ngay khi bộ điều phối quan sát lỗi | Yêu cầu hủy những việc chưa hoàn tất |
| Thu thập kết quả độc lập | Đã có trạng thái của từng tác vụ hoặc hết ngân sách | Ghi nhận lỗi riêng theo từng tác vụ | Tiếp tục những việc còn giá trị |
| Một kết quả hợp lệ là đủ | Đã có một kết quả đáp ứng tiêu chí | Có thể thử tiếp các tác vụ khác | Hủy phần còn lại khi có kết quả đạt yêu cầu |
| Theo ngưỡng | Đã đạt số lượng kết quả hợp lệ đã định | Chỉ thất bại khi không còn khả năng đạt ngưỡng | Dừng khi đã có quyết định cuối cùng |

Chẳng hạn, ba phép tính độc lập đều cần thiết để tạo báo cáo thì dùng chính sách thứ nhất. Ba máy chủ sao chép cùng dữ liệu có thể phù hợp với chính sách thứ ba. Không thể chọn chính sách chỉ vì các tác vụ đều dùng cùng một loại executor.

“Dừng sớm khi lỗi” (fail-fast) có nghĩa là phản ứng sớm sau khi quan sát lỗi. Nó không bảo đảm các luồng khác ngừng chạy đúng cùng thời điểm và không bảo đảm phát hiện lỗi theo một thứ tự tuyệt đối giữa các luồng.

### 2.2. Những trạng thái không nên nhập làm một

Đối với nơi gọi, nên phân biệt ít nhất:

- Thành công: có đủ kết quả đã kiểm tra.
- Thất bại: một thao tác không thực hiện được; giữ nguyên nguyên nhân.
- Hết thời gian: ngân sách chờ đã hết; trạng thái thực tế ở hệ thống ngoài có thể chưa rõ.
- Bị hủy: một bên có quyền chủ động yêu cầu ngừng công việc.
- Chưa xác minh đã dừng: đã yêu cầu hủy nhưng còn phần việc không chịu kết thúc.

Trạng thái cuối cùng đặc biệt quan trọng. Trả lỗi cho người dùng và xác nhận tác vụ đã ngừng là hai việc khác nhau. Ví dụ, một lệnh ghi dữ liệu từ xa có thể thành công sau khi phía gọi đã hết thời gian chờ.

## 3. Phân biệt tín hiệu dừng, trạng thái Future và sự kết thúc thực tế

### 3.1. `cancel(true)` là yêu cầu hợp tác

Với tác vụ được gửi vào executor thông thường, `future.cancel(true)` cố gắng hủy tác vụ; nếu đang chạy, cơ chế thực thi có thể gửi tín hiệu ngắt (interrupt) đến luồng thực hiện. Luồng đó phải có cơ hội quan sát tín hiệu và thoát khỏi công việc.

Một `Future` đã bị hủy có thể trả `isDone() == true` trong khi mã tác vụ vẫn còn chạy hoặc đang giải phóng tài nguyên. Vì vậy, không dùng `isDone()` làm bằng chứng rằng kết nối đã đóng hay mọi tác động bên ngoài đã chấm dứt. [Tài liệu Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html)

Tín hiệu ngắt không tự hoàn tác dữ liệu, không tự chạy một giao dịch bù và không thay thế hợp đồng hủy riêng của thư viện I/O.

### 3.2. Tác vụ chờ phải thoát được; tác vụ tính toán phải kiểm tra được

Một tác vụ có thể truyền `InterruptedException` lên trên thì nên để ngoại lệ đó đi qua sau khi hoàn tất việc dọn dẹp:

```java
// Đoạn minh họa, không phải chương trình độc lập.
static String awaitInput(java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
```

Nếu tầng hiện tại không thể ném tiếp ngoại lệ kiểm tra này, cần khôi phục trạng thái ngắt và kết thúc phần việc theo hợp đồng. Không khôi phục rồi tiếp tục vòng lặp chờ như chưa có gì xảy ra.

```java
// Đoạn minh họa: thích hợp ở biên Runnable kết thúc khi bị ngắt.
public void run() {
    try {
        processUntilFinished(); // Phương thức này có thể ném InterruptedException.
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        releaseResources();
    }
}
```

Với vòng lặp tính toán dài, đặt điểm kiểm tra ở các ranh giới đủ nhỏ:

```java
// Đoạn minh họa.
static long sumSquares(int[] values) throws InterruptedException {
    long total = 0;
    for (int value : values) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("calculation cancelled");
        }
        total += (long) value * value;
    }
    return total;
}
```

`isInterrupted()` không xóa trạng thái ngắt; `Thread.interrupted()` kiểm tra rồi xóa trạng thái của luồng hiện tại. Các phương thức chờ có khả năng bị ngắt thường ném `InterruptedException` và xóa trạng thái đó. Ở biên xử lý không truyền ngoại lệ lên nữa, khôi phục trạng thái để tầng trên còn nhận ra yêu cầu dừng. [Tài liệu Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html)

Không giữ khóa độc quyền trong suốt một lời gọi bên ngoài chậm. Tác vụ đang chờ lấy khóa nội tại bằng `synchronized` không tự thoát khỏi việc chờ lấy khóa chỉ vì được interrupt. Khi khả năng hủy là yêu cầu bắt buộc, phải chọn cơ chế chờ và API hỗ trợ điều đó.

### 3.3. Đóng executor và hủy Future là hai thao tác khác nhau

- `shutdown()` ngừng nhận việc mới nhưng cho phần việc đã gửi tiếp tục.
- `shutdownNow()` cố gắng ngắt việc đang chạy và lấy các việc chưa bắt đầu khỏi hàng đợi.
- `awaitTermination(...)` chờ executor kết thúc sau khi đã yêu cầu shutdown và trả về kết quả chờ.

`shutdownNow()` không chờ các luồng thực sự dừng. Các phần tử nó trả lại là công việc đã bị lấy khỏi hàng đợi; không nên suy diễn rằng mọi `Future` ứng với chúng đều tự được chuyển sang trạng thái hủy. Khi đang sở hữu danh sách `Future`, hãy yêu cầu hủy từng phần tử trong danh sách. [Tài liệu ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html)

## 4. Quan sát lỗi đúng nơi và đúng thứ tự

### 4.1. Giữ Future và đọc kết quả

Một tác vụ gửi bằng `submit` có thể ném ngoại lệ nhưng lỗi nằm trong kết quả bất đồng bộ. Nếu chỉ gửi việc rồi bỏ `Future`, nơi gọi có thể không bao giờ biết công việc đã thất bại.

Khi `get()` ném `ExecutionException`, lấy nguyên nhân qua `getCause()`. Khi chính luồng chờ bị ngắt, đó là `InterruptedException`, không phải lỗi nghiệp vụ của tác vụ con. Khi `Future` bị hủy, `get()` ném `CancellationException`. Bộ điều phối phải giữ được các khác biệt này khi chuyển thành kết quả chung.

Không bắt mọi ngoại lệ rồi trả một danh sách rỗng: nơi gọi không phân biệt được “không có dữ liệu” với “không đọc được dữ liệu”.

### 4.2. Chờ theo thứ tự gửi có thể trì hoãn phát hiện lỗi

Giả sử A chạy chậm, B lỗi ngay và C đang chờ. Đoạn mã gọi `a.get()` trước rồi mới đến `b.get()` có thể chưa nhìn thấy lỗi của B trong khi đang chờ A.

`ExecutorCompletionService` cho phép lấy các `Future` đã hoàn tất qua một hàng đợi. Bộ điều phối quan sát việc đã hoàn tất mà không buộc phải chờ theo thứ tự gửi. Sau khi nhận được một `Future`, vẫn phải gọi `get()` để phân biệt thành công, lỗi và hủy. [Tài liệu ExecutorCompletionService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html)

Lỗi đầu tiên được quan sát không nhất thiết là lỗi xảy ra sớm nhất theo thời gian thực. Nếu cần thu thập thêm lỗi để chẩn đoán, chỉ thu thập trong một ngân sách hữu hạn; không chờ vô hạn chỉ để có đủ mọi stack trace.

### 4.3. Lỗi khi gửi việc cũng cần đường dọn dẹp

Có thể gửi thành công A rồi bị từ chối khi gửi B. Khi đó không có nghĩa là “nhóm chưa chạy”: A đã có thể đang truy cập cơ sở dữ liệu.

Đặt cả quá trình gửi việc bên trong vùng được bảo vệ bởi `try/finally`. Mỗi lần gửi thành công thì lưu `Future` ngay, để đường dọn dẹp nhìn thấy mọi công việc đã được nhận. Với executor có giới hạn tài nguyên, `RejectedExecutionException` là một kết quả cần xử lý; không tự gửi lại vô hạn. [Tài liệu ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

## 5. Một ngân sách cho cả nhóm và một ngân sách cho dọn dẹp

### 5.1. Không cấp lại toàn bộ thời gian cho từng tác vụ

Nếu nhóm có ngân sách 3 giây, chờ lần lượt mỗi `Future` tối đa 3 giây có thể khiến tổng thời gian chờ dài hơn hợp đồng. Hãy tính phần thời gian còn lại trước mỗi lần chờ:

```java
// Đoạn minh họa cho một ngân sách ngắn, hữu hạn.
long started = System.nanoTime();
long budget = java.util.concurrent.TimeUnit.SECONDS.toNanos(3);

// Trước mỗi lần chờ:
long remaining = budget - (System.nanoTime() - started);
if (remaining <= 0) {
    throw new java.util.concurrent.TimeoutException("group deadline");
}
```

Dùng `System.nanoTime()` để đo khoảng thời gian trôi qua trong cùng JVM. Không dùng đồng hồ lịch có thể bị điều chỉnh để tính khoảng chờ này; cũng không gửi giá trị `nanoTime()` sang một máy khác như một mốc thời gian toàn cục.

Ngân sách phải có điểm bắt đầu rõ ràng: từ khi nhận yêu cầu, từ khi bắt đầu gửi nhóm hay từ khi bắt đầu chờ. Ví dụ dưới đây tính từ trước khi gửi các tác vụ của nhóm. Các lời gọi mạng bên trong cũng phải có thời hạn riêng phù hợp; bộ điều phối không thể bảo đảm thời hạn cứng nếu một thư viện giữ luồng trong thao tác không thể ngắt.

### 5.2. Hết thời gian chờ chưa tự hủy phần việc

`Future.get(timeout, unit)` hoặc `CompletionService.poll(timeout, unit)` giới hạn việc chờ của nơi gọi. Muốn nhóm dừng, bộ điều phối còn phải chạy chính sách hủy trong `finally`.

Dành một ngân sách khác cho dọn dẹp. Ví dụ: công việc có tối đa 5 giây, sau đó dành tối đa 2 giây để chờ phản hồi hủy. Đây là hợp đồng “ngân sách công việc cộng ngân sách dọn dẹp”, không phải cam kết trả lời trong đúng 5 giây.

Nếu dọn dẹp hết thời gian mà tác vụ vẫn chưa dừng, phải làm trạng thái đó quan sát được. Không đổi thông báo thành “đã dừng tất cả”. Với executor dùng chung, cần cơ chế theo dõi riêng cho nhóm thay vì dùng sự kết thúc của toàn executor làm tiêu chí.

## 6. Ví dụ hoàn chỉnh: tất cả phải thành công, lỗi thì hủy phần còn lại

Chương trình sau có một bộ điều phối, hai luồng thực thi và ba tác vụ. Nó không công bố kết quả từng phần. Chỉ sau khi nhận đủ ba kết quả thành công mới cộng và trả tổng.

Các chế độ:

- `ok`: ba phép tính trả về ngay.
- `fail`: một tác vụ báo lỗi; một tác vụ khác chờ trên latch không bao giờ được mở.
- `timeout`: ba tác vụ đều chờ trên latch không được mở.
- `interrupt`: luồng điều phối được đặt trạng thái ngắt trước khi gọi nhóm.

Latch ở đây chỉ tạo tình huống chờ có khả năng bị ngắt, không đại diện cho lỗi mạng và không yêu cầu phải đoán tốc độ lập lịch. `CountDownLatch.await()` có thể bị ngắt nên phù hợp để kiểm tra đường hủy hợp tác. [Tài liệu CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

Tạo tệp `GroupStopDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletionService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class GroupStopDemo {
    static int runAll(List<Callable<Integer>> tasks, long timeoutMillis)
            throws InterruptedException, ExecutionException, TimeoutException {
        if (timeoutMillis <= 0 || timeoutMillis > 60_000) {
            throw new IllegalArgumentException("timeout must be 1..60000 ms");
        }
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("coordinator interrupted");
        }

        ExecutorService executor = Executors.newFixedThreadPool(2);
        CompletionService<Integer> completed =
                new ExecutorCompletionService<>(executor);
        List<Future<Integer>> submitted = new ArrayList<>();
        long started = System.nanoTime();
        long budget = TimeUnit.MILLISECONDS.toNanos(timeoutMillis);

        try {
            for (Callable<Integer> task : tasks) {
                if (Thread.currentThread().isInterrupted()) {
                    throw new InterruptedException("submission interrupted");
                }
                submitted.add(completed.submit(task));
            }

            int total = 0;
            for (int i = 0; i < submitted.size(); i++) {
                long remaining = budget - (System.nanoTime() - started);
                if (remaining <= 0) {
                    throw new TimeoutException("group deadline");
                }
                Future<Integer> done =
                        completed.poll(remaining, TimeUnit.NANOSECONDS);
                if (done == null) {
                    throw new TimeoutException("group deadline");
                }
                total += done.get();
            }
            return total;
        } finally {
            if (!stopOwnedExecutor(executor, submitted)) {
                System.err.println("CLEANUP_INCOMPLETE");
            }
        }
    }

    static boolean stopOwnedExecutor(
            ExecutorService executor, List<? extends Future<?>> submitted) {
        for (Future<?> future : submitted) {
            future.cancel(true);
        }
        executor.shutdownNow();

        long started = System.nanoTime();
        long budget = TimeUnit.SECONDS.toNanos(2);
        boolean interrupted = false;
        try {
            while (true) {
                long remaining = budget - (System.nanoTime() - started);
                if (remaining <= 0) {
                    return executor.isTerminated();
                }
                try {
                    return executor.awaitTermination(
                            remaining, TimeUnit.NANOSECONDS);
                } catch (InterruptedException e) {
                    interrupted = true;
                }
            }
        } finally {
            if (interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }

    static Callable<Integer> waitingTask(CountDownLatch gate) {
        return () -> {
            gate.await();
            return 99;
        };
    }

    public static void main(String[] args) {
        String mode = args.length == 0 ? "fail" : args[0];
        CountDownLatch gate = new CountDownLatch(1);
        List<Callable<Integer>> tasks = switch (mode) {
            case "ok", "interrupt" ->
                    List.of(() -> 10, () -> 20, () -> 30);
            case "timeout" ->
                    List.of(waitingTask(gate),
                            waitingTask(gate),
                            waitingTask(gate));
            case "fail" ->
                    List.of(() -> 10,
                            () -> {
                                throw new IllegalStateException(
                                        "upstream unavailable");
                            },
                            waitingTask(gate));
            default -> throw new IllegalArgumentException(
                    "use ok, fail, timeout or interrupt");
        };

        if (mode.equals("interrupt")) {
            Thread.currentThread().interrupt();
        }
        long timeoutMillis = mode.equals("timeout") ? 100 : 5_000;

        try {
            System.out.println("SUCCESS: " + runAll(tasks, timeoutMillis));
        } catch (ExecutionException e) {
            System.out.println("FAILED: " + e.getCause().getMessage());
        } catch (TimeoutException e) {
            System.out.println("TIMED_OUT");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.out.println("INTERRUPTED: "
                    + Thread.currentThread().isInterrupted());
        } catch (CancellationException e) {
            System.out.println("CANCELLED");
        } catch (RejectedExecutionException e) {
            System.out.println("REJECTED");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 GroupStopDemo.java
java GroupStopDemo ok
java GroupStopDemo fail
java GroupStopDemo timeout
java GroupStopDemo interrupt
```

Stdout tương ứng, trong điều kiện chạy thông thường:

```text
SUCCESS: 60
FAILED: upstream unavailable
TIMED_OUT
INTERRUPTED: true
```

Không có dòng log từ từng tác vụ nên stdout không phụ thuộc thứ tự các luồng in thông báo. Trong chế độ `ok` và `fail`, ngân sách 5 giây vẫn là thời hạn thật: môi trường bị treo hoặc quá tải lâu có thể dẫn đến `TIMED_OUT`. Với các tác vụ hợp tác trong ví dụ, không dự kiến có `CLEANUP_INCOMPLETE` trên stderr.

### 6.1. Các điểm thiết kế đáng kiểm tra trong mã

1. Executor được tạo riêng trong `runAll`, nên phương thức này có quyền đóng nó.
2. Kiểm tra trạng thái ngắt trước khi tạo executor tránh gửi việc cho một yêu cầu đã bị hủy từ trước. Kiểm tra thêm khi gửi nhóm giúp giảm phần việc được gửi sau khi có tín hiệu dừng.
3. `submitted` được cập nhật sau từng lần gửi thành công. Nếu lần gửi tiếp theo lỗi, `finally` vẫn biết các tác vụ đã tồn tại.
4. `CompletionService.poll` dùng phần ngân sách còn lại, tránh đợi theo thứ tự danh sách đầu vào.
5. `done.get()` chuyển lỗi tác vụ thành `ExecutionException`. Phương thức không nuốt lỗi hoặc tự biến lỗi thành giá trị 0.
6. `finally` chạy trên cả đường thành công, lỗi và hết thời gian. Các kết quả đã hoàn tất không bị đảo ngược chỉ vì gọi `cancel` sau đó.
7. Việc hủy từng `Future` diễn ra trước khi shutdown executor, kể cả với công việc chưa kịp chạy.
8. Thời gian dọn dẹp có giới hạn riêng. Nếu luồng điều phối bị ngắt trong lúc chờ dọn dẹp, helper ghi nhận, tiếp tục chờ trong phần ngân sách còn lại rồi khôi phục trạng thái ngắt.
9. Helper không ném một `InterruptedException` mới để thay thế nguyên nhân lỗi đang đi ra khỏi `runAll`. Nó bảo toàn tín hiệu ngắt bằng trạng thái của luồng.
10. Nếu không xác minh được executor đã dừng, ví dụ ghi dấu hiệu riêng trên stderr. Trong dịch vụ thật, thay bằng log có mã nhóm, số việc còn chạy và cảnh báo phù hợp.

Việc cố ý tiếp tục chờ một khoảng ngắn sau khi bị ngắt là quyết định của chính sách dọn dẹp, không phải mẫu bắt `InterruptedException` áp dụng ở mọi nơi. Một hệ thống cần phản hồi hủy nhanh hơn có thể giảm ngân sách này hoặc giao việc xác minh kết thúc cho thành phần quản lý vòng đời.

`runAll` trong ví dụ chỉ dùng cho một danh sách nhỏ, đã có sẵn. Giới hạn 60 giây là kiểm tra đầu vào riêng của ví dụ. Với luồng công việc lớn, cần thêm giới hạn số tác vụ đang chờ và cơ chế điều tiết tốc độ gửi; hai luồng thực thi không đồng nghĩa hàng đợi công việc cũng có giới hạn.

## 7. Đường lỗi của các tác vụ phối hợp không chỉ nằm ở Future

### 7.1. Latch: “đã kết thúc” khác “đã thành công”

Nếu dùng một latch đếm số tác vụ đã kết thúc, mỗi tác vụ đã bắt đầu nên `countDown()` trong `finally`, để lỗi không bỏ quên một lượt báo hoàn tất. Tuy nhiên, tác vụ bị hủy trước khi bắt đầu sẽ không chạy `finally`. Không thiết kế latch với giả định mọi việc đã gửi chắc chắn sẽ được chạy.

Đồng thời, latch về 0 chỉ chứng minh các lượt đếm đã xảy ra; nó không chứa kết quả và không tự truyền ngoại lệ. Muốn biết nhóm thành công phải quan sát thêm các kết quả hoặc trạng thái lỗi đã công bố an toàn.

Với nhiều vòng đồng bộ, một tác vụ rời cuộc chơi có thể làm các tác vụ còn lại chờ mãi. Khi dùng barrier hoặc cơ chế đăng ký bên tham gia, phải định nghĩa cách báo hỏng, rời nhóm và thời hạn chờ; không chỉ sửa đường thành công.

### 7.2. Hàng đợi: lỗi ở một phía có thể làm phía kia mắc kẹt

Trong mô hình sản xuất–tiêu thụ:

- Bên sản xuất lỗi thì bên tiêu thụ có thể mắc ở `take()`.
- Bên tiêu thụ lỗi thì bên sản xuất có thể mắc ở `put()` khi hàng đợi đầy.
- Bộ điều phối không thể chỉ quan sát tác vụ đã lỗi rồi bỏ các `Future` khác.

`BlockingQueue` không có sẵn thao tác đóng chung cho mọi triển khai. Một phần tử báo kết thúc có thể dùng cho đường hoàn tất bình thường, nhưng phải có chính sách cho số bên tiêu thụ và hàng đợi đầy. Không để đường dọn dẹp lại chặn vô hạn khi cố `put` một tín hiệu kết thúc vào hàng đợi mà không còn ai đọc. Khi lỗi hoặc hủy, cơ chế ngắt các bên đang chờ và thời hạn hữu hạn thường là phần cần thiết của giao thức. [Tài liệu BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

### 7.3. Tránh tự chờ trên chính nguồn luồng đã cạn

Nếu hai tác vụ cha chiếm hết hai luồng của một executor rồi mỗi tác vụ lại gửi tác vụ con vào chính executor đó và chờ con, các tác vụ con có thể không bao giờ được chạy.

Đường lỗi có thời hạn giúp thoát khỏi một số lần chờ, nhưng không sửa thiết kế phụ thuộc vòng này. Đặt bộ điều phối ở ngoài nhóm luồng đang bị các tác vụ con sử dụng, hoặc thiết kế chuỗi phụ thuộc sao cho không chiếm luồng chỉ để chờ công việc chưa có chỗ chạy.

## 8. Dọn dẹp tài nguyên và xử lý tác động bên ngoài

### 8.1. Đóng ở nơi sở hữu, theo thứ tự ngược khi cần

Tác vụ tự mở một tệp hoặc kết nối riêng thì nên đóng tài nguyên đó trong `try-with-resources` hoặc `finally`. Bộ điều phối không nên đóng ngẫu nhiên một tài nguyên dùng chung trong khi tác vụ khác vẫn đang dùng.

Nếu executor được ứng dụng cấp chung cho nhiều yêu cầu, đường lỗi của một nhóm chỉ hủy các `Future` thuộc nhóm đó. Gọi `shutdownNow()` lên executor dùng chung có thể hủy công việc không liên quan; quyền đóng phải nằm ở nơi quản lý vòng đời ứng dụng.

Trình tự thường cần là: ngừng tạo công việc mới cho nhóm; yêu cầu hủy phần việc chưa xong; chờ hữu hạn; xác minh tác vụ đã rời tài nguyên; sau đó đóng tài nguyên dùng chung thuộc phạm vi nhóm. Thứ tự cụ thể phụ thuộc hợp đồng thư viện, nhất là khi thao tác đóng tài nguyên chính là cách đánh thức một lời gọi đang chặn.

### 8.2. Lỗi chính không được biến mất sau lỗi dọn dẹp

Một tác vụ lỗi đọc dữ liệu và thao tác đóng kết nối cũng lỗi. Nơi gọi vẫn cần biết lỗi đọc ban đầu. Khi phải dọn dẹp thủ công, có thể gắn lỗi đóng làm ngoại lệ bị nén bằng `addSuppressed` thay vì ném lỗi đóng đè lên lỗi gốc. `try-with-resources` hỗ trợ quan hệ này cho tài nguyên phù hợp.

Không in cùng một stack trace ở mọi tầng rồi vẫn ném tiếp. Gắn ngữ cảnh ở tầng hiểu được nó, còn nơi chịu trách nhiệm kết quả chung quyết định cách ghi log cuối cùng. Trong ví dụ, thông báo trên stdout chỉ để thấy các nhánh chạy; ứng dụng thật thường giữ cả kiểu lỗi và chuỗi nguyên nhân.

### 8.3. Hủy không phải hoàn tác

Giả sử A đã ghi đơn hàng, B đang trừ kho, C báo lỗi thanh toán. Hủy A và B không bảo đảm đơn hàng và số lượng tồn kho trở lại trạng thái ban đầu.

Trước khi cho phép chạy song song các thao tác có tác động, xác định:

- Thao tác nào chỉ đọc và có thể bỏ kết quả.
- Thao tác nào có thể đã hoàn tất dù phía gọi hết thời gian.
- Thao tác nào cần giao dịch, thao tác bù hoặc bước đối soát.
- Thao tác nào cho phép thử lại với khóa chống thực hiện trùng (idempotency key).

Không tự thử lại toàn nhóm khi chưa biết thao tác đã gây tác động hay chưa. Nếu có chính sách thử lại, các lần thử phải cùng chia ngân sách tổng và có điều kiện rõ ràng để tránh nhân số yêu cầu trong lúc hệ thống đang lỗi.

## 9. Kiểm chứng đường dừng như một phần của chức năng

Đừng chỉ thử “ba tác vụ đều trả về”. Những ca sau giúp phát hiện lỗi vòng đời:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Tất cả thành công | Có đủ kết quả; executor riêng kết thúc |
| Một tác vụ lỗi sớm, tác vụ khác đang chờ | Nguyên nhân lỗi được chuyển ra; tác vụ chờ nhận yêu cầu hủy |
| Hết ngân sách | Không tiếp tục chờ đủ ngân sách mới cho từng tác vụ; chạy dọn dẹp |
| Ngắt bộ điều phối | Không nuốt tín hiệu ngắt; nhóm đã gửi được xử lý |
| Bị từ chối ở giữa quá trình gửi | Các tác vụ gửi trước đó vẫn được thu hồi |
| Tác vụ bị hủy trước khi bắt đầu | Không chờ vào một `finally` chưa từng có cơ hội chạy |
| Tác vụ không phản hồi interrupt | Báo chưa xác minh dừng sau thời hạn dọn dẹp |
| Tác vụ đóng tài nguyên cũng lỗi | Nguyên nhân gốc còn nguyên; lỗi đóng có thể truy ra |
| Tác động bên ngoài đã xảy ra | Có phương án đối soát hoặc chống thực hiện trùng |
| Một nhóm lỗi khi dùng executor chung | Các nhóm khác vẫn hoạt động |

Để thử thứ tự “đã bắt đầu rồi mới hủy”, dùng latch báo đã bắt đầu và chờ latch đó trước khi yêu cầu hủy. Không dựa vào `Thread.sleep(100)` rồi cho rằng mọi máy đều đã đến cùng một điểm.

Khi thử một tác vụ cố ý bỏ qua interrupt, phải có cơ chế giải phóng riêng trong môi trường kiểm thử, chẳng hạn một latch mở trong `finally` của ca thử. Nếu không, ca thử có thể để lại luồng sống và làm cả quá trình kiểm thử không thoát.

## 10. Bài tập vận dụng

1. Chạy bốn chế độ của `GroupStopDemo`. Chỉ ra dòng nào quyết định kết quả nghiệp vụ và dòng nào yêu cầu phần việc còn lại dừng.
2. Đổi chính sách thành “thu thập mọi kết quả độc lập”. Thiết kế kiểu kết quả chứa mã tác vụ, giá trị hoặc lỗi; vẫn giữ ngân sách chung và đường hủy khi chính nơi gọi dừng.
3. Thêm một tài nguyên giả có bộ đếm mở/đóng vào tác vụ chờ. Dùng latch để bảo đảm tác vụ đã mở tài nguyên rồi mới hủy; xác minh bộ đếm trở về 0 sau khi xác nhận kết thúc.
4. Viết lại `runAll` để nhận executor dùng chung từ ngoài. Xác định thao tác nào phải bỏ, và cần bổ sung tín hiệu gì để biết chính các tác vụ của nhóm đã rời khỏi mã xử lý.
5. Với bài toán tạo đơn hàng, mô tả trạng thái “hết thời gian nhưng chưa rõ thao tác từ xa đã thành công chưa”. Chọn cách đối soát và điều kiện thử lại trước khi viết mã.

Một lời giải đạt yêu cầu phải giải thích được ai quyết định dừng, ai nhận tín hiệu, ai đóng tài nguyên và bằng chứng nào cho thấy phần việc thực tế đã kết thúc. Chỉ gọi `cancel(true)` rồi trả lỗi chưa đủ để trả lời bốn điều đó.
