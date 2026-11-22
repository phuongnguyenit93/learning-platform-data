# Các điểm mở rộng beforeExecute, afterExecute và terminated

## 1. Mở rộng ở đúng ranh giới vòng đời

Một nhóm luồng tùy chỉnh có thể cần đo thời lượng công việc, gán và dọn ngữ cảnh theo tác vụ, ghi nhận lỗi hoặc chốt thống kê khi dừng. Không nên đưa những trách nhiệm dùng chung này vào mọi tác vụ bằng cách sao chép cùng một đoạn mã.

`ThreadPoolExecutor` cung cấp ba phương thức `protected` để lớp con can thiệp ở các ranh giới đó:

- `beforeExecute`: ngay trước khi một luồng thực thi gọi Runnable được giao.
- `afterExecute`: sau khi Runnable đã được thực thi qua vòng xử lý của executor, kể cả trường hợp lỗi thoát khỏi phần chạy.
- `terminated`: tại ranh giới executor kết thúc.

Đây thường được gọi là các điểm móc mở rộng (hook). Chúng giúp bổ sung cơ chế quan sát và quản lý môi trường thực thi, không thay toàn bộ thuật toán hàng đợi, số luồng hoặc chính sách từ chối.

Các API này vẫn áp dụng trong Java hiện nay. Ví dụ chính dùng Java 17 trở lên.

## 2. Ba chữ ký và đối tượng mà chúng quan sát

```java
protected void beforeExecute(Thread thread, Runnable task)
protected void afterExecute(Runnable task, Throwable failure)
protected void terminated()
```

Các chữ ký trên để đọc hợp đồng, không phải các phương thức độc lập ngoài lớp.

| Điểm mở rộng | Phạm vi | Luồng thực hiện | Ứng dụng thường gặp |
|---|---|---|---|
| beforeExecute | Một Runnable được luồng nhóm chuẩn bị chạy | Chính luồng sẽ thực thi Runnable đó | Ghi mốc bắt đầu, gán ngữ cảnh, kiểm tra môi trường |
| afterExecute | Một Runnable vừa được thực thi | Chính luồng đã thực thi Runnable đó | Đo thời lượng, phát hiện lỗi, dọn trạng thái |
| terminated | Vòng đời cả executor | Không giả định cố định một luồng cụ thể | Chốt thống kê, phát tín hiệu kết thúc ngắn gọn |

Với submit, Runnable nhìn thấy ở hook thường là lớp bọc FutureTask, không trực tiếp là Callable/Runnable nghiệp vụ ban đầu. Nếu cần mã công việc hoặc thuộc tính nghiệp vụ, thiết kế một lớp bọc/nhận dạng rõ ràng thay vì suy từ tên lớp nội bộ hay `toString()`.

## 3. Thứ tự thực thi thông thường

Trong luồng của nhóm:

```text
Lấy một Runnable để xử lý
    → beforeExecute(thread, task)
    → task.run()
    → afterExecute(task, failure)
    → nhận công việc kế tiếp hoặc kết thúc luồng
```

Khi đủ điều kiện dừng toàn bộ nhóm:

```text
Không còn công việc/luồng theo điều kiện kết thúc
    → terminated()
    → hoàn tất công bố trạng thái kết thúc của executor
```

Sơ đồ là mô hình của triển khai chuẩn; không coi nó như một giao thức “after chắc chắn luôn cứu được mọi lỗi trước đó”. Nếu beforeExecute ném lỗi trước khi gọi task.run, afterExecute không phải một khối finally do ứng dụng có thể dựa vào để luôn được gọi cho cặp đó. Các hook tự ném lỗi có thể làm luồng thực thi kết thúc bất thường và có thể được thay thế. [ThreadPoolExecutor: Hook methods](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

Điều đó quan trọng khi gán ngữ cảnh: phần chuẩn bị trong before phải có đường xử lý nếu chính nó thất bại giữa chừng; không mặc định một after ở tương lai sẽ luôn dọn hộ.

## 4. beforeExecute: chuẩn bị cho từng tác vụ, không phải tạo luồng

Ví dụ dùng beforeExecute để ghi `System.nanoTime()` vào ThreadLocal. Giá trị này gắn với luồng đang chuẩn bị chạy một tác vụ, nên afterExecute của chính luồng đó có thể lấy lại để tính thời lượng.

Nó khác ThreadFactory:

- Factory được gọi khi cần tạo luồng, một lần tạo có thể phục vụ nhiều tác vụ.
- beforeExecute được gọi khi vòng xử lý của executor sắp thực thi một Runnable.

Có thể dùng before để khởi tạo dữ liệu theo tác vụ, nhưng cần biết dữ liệu lấy từ đâu và ai sở hữu nó. Luồng nhóm không tự nhận được mọi thông tin của người gửi chỉ vì người đó đã submit.

Theo hướng dẫn API về việc lồng nhiều lớp kế thừa, lớp con thường gọi `super.beforeExecute(thread, task)` ở **cuối** phần override. Với afterExecute, hướng dẫn là gọi super ở **đầu** phần override. Cần giữ hợp đồng của lớp cha thực tế, đặc biệt nếu lớp cha trung gian có logic riêng. [beforeExecute](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#beforeExecute(java.lang.Thread,java.lang.Runnable)).

## 5. afterExecute và bẫy failure bằng null

Tham số Throwable của afterExecute phản ánh một lỗi không được bắt thoát khỏi Runnable đang chạy. Một Runnable gửi trực tiếp bằng execute có thể ném RuntimeException hoặc Error và làm tham số này có giá trị.

Nhưng FutureTask thường giữ lỗi tính toán bên trong. Do đó một Callable gửi bằng submit có thể thất bại mà `failure == null` trong afterExecute: lớp bọc đã trả về bình thường, còn Future giữ trạng thái lỗi.

Mô hình cần dùng khi muốn quan sát cả hai đường:

```text
afterExecute nhận failure khác null?
    ├─ Có → ghi nhận lỗi trực tiếp
    └─ Không → task có là Future và đã done?
                   ├─ Có → lấy kết quả để phát hiện lỗi/hủy
                   └─ Không → không chờ mù quáng trong hook
```

`get()` trên Future đã done giúp tìm ExecutionException và nguyên nhân gốc, hoặc CancellationException. Không gọi get không thời hạn trên một Future chưa xong ngay trong hook; một RunnableFuture tùy biến có thể có hợp đồng khác với lớp bọc một lần thông thường.

Nếu việc lấy kết quả bị ngắt, khôi phục cờ ngắt khi không truyền tiếp được theo chữ ký hook. Đừng nuốt tín hiệu ngắt chỉ để thống kê trông như hoàn thành. [afterExecute](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#afterExecute(java.lang.Runnable,java.lang.Throwable)).

## 6. Chương trình đầy đủ: đo từng tác vụ và phát hiện lỗi submit

Thí nghiệm gửi ba tác vụ theo thứ tự vào executor một luồng: thành công, thất bại, thành công. Các hook ghi số lượt, phân loại lỗi và xóa mốc thời gian khỏi ThreadLocal. Kết quả thống kê chỉ được in sau `awaitTermination` thành công.

Lưu thành `ExecutorHooksDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class ExecutorHooksDemo {
    static final class ObservedExecutor extends ThreadPoolExecutor {
        private final ThreadLocal<Long> startedAt = new ThreadLocal<>();
        final AtomicInteger beforeCalls = new AtomicInteger();
        final AtomicInteger afterCalls = new AtomicInteger();
        final AtomicInteger terminatedCalls = new AtomicInteger();
        final AtomicLong measuredTasks = new AtomicLong();
        final AtomicLong totalNanos = new AtomicLong();
        final ConcurrentLinkedQueue<String> outcomes =
                new ConcurrentLinkedQueue<>();

        ObservedExecutor() {
            super(1, 1, 0, TimeUnit.MILLISECONDS,
                    new ArrayBlockingQueue<Runnable>(8));
        }

        @Override
        protected void beforeExecute(Thread thread, Runnable task) {
            startedAt.set(System.nanoTime());
            beforeCalls.incrementAndGet();
            super.beforeExecute(thread, task);
        }

        @Override
        protected void afterExecute(Runnable task, Throwable failure) {
            super.afterExecute(task, failure);
            try {
                Long start = startedAt.get();
                if (start != null) {
                    totalNanos.addAndGet(System.nanoTime() - start);
                    measuredTasks.incrementAndGet();
                }

                Throwable observed = failure;
                if (observed == null
                        && task instanceof Future<?> future
                        && future.isDone()) {
                    try {
                        future.get();
                    } catch (CancellationException ex) {
                        observed = ex;
                    } catch (ExecutionException ex) {
                        observed = ex.getCause();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        observed = ex;
                    }
                }

                outcomes.add(observed == null
                        ? "success"
                        : observed.getClass().getSimpleName());
                afterCalls.incrementAndGet();
            } finally {
                startedAt.remove();
            }
        }

        @Override
        protected void terminated() {
            try {
                terminatedCalls.incrementAndGet();
            } finally {
                super.terminated();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ObservedExecutor pool = new ObservedExecutor();
        try {
            Future<Integer> first = pool.submit(() -> 21);
            Future<Integer> failed = pool.submit(() -> {
                throw new IllegalArgumentException("bad task");
            });
            Future<Integer> third = pool.submit(() -> 42);

            System.out.println("first result: "
                    + first.get(10, TimeUnit.SECONDS));
            try {
                failed.get(10, TimeUnit.SECONDS);
                throw new AssertionError("Expected ExecutionException");
            } catch (ExecutionException ex) {
                System.out.println("caller saw: "
                        + ex.getCause().getClass().getSimpleName());
            }
            System.out.println("third result: "
                    + third.get(10, TimeUnit.SECONDS));

            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Executor did not terminate");
            }

            System.out.println("before calls: " + pool.beforeCalls.get());
            System.out.println("after calls: " + pool.afterCalls.get());
            System.out.println("measured tasks: " + pool.measuredTasks.get());
            System.out.println("outcomes: " + pool.outcomes);
            System.out.println("terminated calls: "
                    + pool.terminatedCalls.get());
        } finally {
            for (Runnable task : pool.shutdownNow()) {
                if (task instanceof Future<?> future) {
                    future.cancel(false);
                }
            }
            try {
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Cleanup did not terminate");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 ExecutorHooksDemo.java
java ExecutorHooksDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
first result: 21
caller saw: IllegalArgumentException
third result: 42
before calls: 3
after calls: 3
measured tasks: 3
outcomes: [success, IllegalArgumentException, success]
terminated calls: 1
```

### Đọc bằng chứng

Ba tác vụ submit được quan sát bởi before và after. Tác vụ giữa thất bại, nhưng lỗi được lớp bọc giữ lại; afterExecute phải đọc Future đã done để thấy IllegalArgumentException. Luồng main cũng nhận lỗi qua Future, nên ví dụ minh họa hai bên quan sát cùng lần thực thi chứ không phải chạy lại tác vụ.

`totalNanos` được thu để minh họa đo thời lượng nhưng không được in như một hằng số mong đợi, vì thời gian phụ thuộc lịch chạy/máy. Các mốc đo bắt đầu tại before, không phải lúc submit, nên số đo không bao gồm thời gian chờ trong queue và cũng không phải thời gian CPU thuần.

Executor chỉ có một luồng nên thứ tự outcomes theo ba tác vụ là cố định trong thí nghiệm này. Đổi sang nhiều luồng có thể làm thứ tự ghi outcomes thay đổi; không viết kiểm tra so sánh đúng chuỗi thứ tự đó cho mọi cấu hình.

## 7. Vì sao không chỉ get xong rồi đọc ngay bộ đếm after?

FutureTask có thể công bố kết quả trước khi vòng xử lý của ThreadPoolExecutor gọi và hoàn thành afterExecute. Nơi gọi nhận được kết quả từ get rồi đọc ngay bộ đếm after có thể chạy sớm hơn phần ghi thống kê.

Cần phân biệt:

```text
Callable hoàn thành / Future có kết quả
    → Future.get có thể trở về ở luồng khác
    → phần sau task.run của executor tiếp tục
    → afterExecute cập nhật thống kê
```

Ví dụ chờ executor kết thúc trước khi đọc thống kê cuối cùng. Nếu ứng dụng cần báo cáo hook hoàn thành cho từng công việc mà chưa dừng toàn bộ executor, phải thiết kế tín hiệu riêng gắn với hợp đồng đó; không dùng một get của Future làm bằng chứng mọi phần mở rộng phía sau đều đã chạy xong.

Đây là hệ quả của các ranh giới trong [mã nguồn ThreadPoolExecutor](https://raw.githubusercontent.com/openjdk/jdk/jdk-25-ga/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java), không phải lý do thêm sleep để chờ “chắc là đủ”.

## 8. terminated: chốt vòng đời, không phải after cho từng công việc

terminated phục vụ thông báo hoặc thống kê khi executor đi tới kết thúc. Nó không được gọi sau từng tác vụ hoặc chỉ vì hàng đợi tạm thời rỗng.

Không cố định giả định “terminated luôn chạy trên luồng cuối của nhóm”. Một executor trống có thể đi tới điều kiện kết thúc trong luồng gọi shutdown; các lịch chạy khác có thể đưa việc hoàn tất vào luồng khác. Logic trong hook không nên phụ thuộc tên luồng cụ thể.

Thân terminated cần ngắn và không mắc phụ thuộc ngược. Không submit thêm việc vào chính executor đã dừng để rồi chờ việc đó trong hook. Cũng không gọi awaitTermination của chính executor ở đó: hook đang ở ranh giới chuyển sang trạng thái kết thúc, nên chờ ngược có thể gây tự mắc kẹt hoặc kéo dài việc dừng.

Nếu cần gửi thống kê qua mạng, cân nhắc bàn giao một bản chụp nhỏ sang một cơ chế có vòng đời độc lập và giới hạn rõ. Không để việc dừng executor phụ thuộc một lời I/O không có hạn chót trong callback. Gọi super.terminated theo hợp đồng lớp cha. [terminated](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#terminated()).

## 9. Hook không quan sát mọi cách công việc đi qua hệ thống

Các before/after này gắn với vòng xử lý tác vụ của các luồng trong ThreadPoolExecutor. Vì thế:

- Công việc bị từ chối và không chạy không tự đi qua before/after như một tác vụ thành công.
- Công việc bị lấy khỏi queue trước khi chạy không có phần thực thi bình thường để hook theo dõi.
- Với CallerRunsPolicy, công việc chạy trực tiếp trên luồng gọi qua handler, không tự đi qua vòng worker có hai hook đó.
- Một FutureTask bị hủy nhưng còn trong queue có thể được worker lấy ra và gọi run; thân Callable không chạy nữa, nhưng hook vẫn quan sát Runnable lớp bọc được xử lý. Đếm hook không luôn bằng số công việc nghiệp vụ thực sự bắt đầu.
- Một lớp bọc tùy chỉnh có thể giữ hoặc biến đổi lỗi; tham số Throwable không phải toàn bộ lịch sử lỗi ở mọi lớp bên trong.

Nếu mục tiêu là thống kê mọi công việc từ lúc người gửi yêu cầu, cần kết hợp ranh giới giao việc, từ chối, hủy, bắt đầu và hoàn tất. Không đặt tên một bộ đếm after là “mọi yêu cầu đã xử lý thành công” chỉ vì nó tăng sau task.run.

## 10. Hook phải an toàn với đồng thời và với lỗi của chính nó

Nhiều luồng nhóm có thể cùng gọi before/after. Dùng trạng thái theo luồng cho dữ liệu gắn với một lượt thực thi, và cấu trúc an toàn luồng cho bộ đếm/kết quả dùng chung. Tránh một trường `long startedAt` chung bị các tác vụ ghi đè lên nhau.

Dọn ThreadLocal trong finally ở after giúp không giữ mốc hoặc ngữ cảnh sang công việc tiếp theo. Nếu hook gán ngữ cảnh nghiệp vụ, cần khôi phục trạng thái cũ hoặc remove theo hợp đồng; không xóa mù trạng thái do lớp khác sở hữu.

Phần ghi log, đo lường hay thu thập lỗi cũng có thể gặp lỗi. Cần xác định chính sách của hạ tầng quan sát: không để một lỗi log thông thường vô tình làm chết luồng hoặc khiến Future của công việc không được chạy. Nhưng cũng không bắt mọi Throwable rồi che giấu tình trạng tài nguyên nghiêm trọng như thể hệ thống vẫn khỏe.

Nếu before thất bại trước task.run, Future của công việc có thể chưa được hoàn tất theo đường chạy bình thường. Nếu after ném lỗi, nó có thể làm luồng kết thúc sau khi công việc đã hoàn tất. Do vậy các hook cần được kiểm tra riêng với những lỗi quan sát có thể xảy ra, đặc biệt khi mở rộng từ một lớp executor tùy chỉnh khác.

## 11. Tự kiểm tra và thực hành

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| after nhận null nghĩa nghiệp vụ thành công | FutureTask có thể đang giữ lỗi bên trong |
| after luôn dọn được mọi lỗi từ before | Nếu before ném lỗi trước task.run, không dựa vào cặp after đó |
| get trả rồi mọi thống kê after đã xong | Future có thể công bố kết quả trước khi after hoàn tất |
| Hook chạy tuần tự vì chỉ có một executor | Nhiều worker có thể gọi hook đồng thời |
| terminated được gọi khi queue rỗng | Nó gắn với vòng đời kết thúc, không phải một lúc nhàn rỗi |
| Bộ đếm before là tổng mọi yêu cầu nhận vào | Việc từ chối hoặc chạy qua handler có đường khác |

Tự kiểm tra:

1. Vì sao ví dụ phải thử get trên Future đã done trong afterExecute? **Để lấy lỗi do lớp bọc submit giữ mà Throwable trực tiếp không chứa.**
2. Vì sao dùng ThreadLocal cho mốc bắt đầu? **Mỗi luồng cần mốc của lượt chạy tương ứng, không dùng một trường bị ghi đè chung.**
3. Vì sao không in thời gian cố định trong output? **Độ dài chạy không phải hằng số của cơ chế hook.**
4. Vì sao đọc thống kê sau awaitTermination? **Để không cạnh tranh với after/terminated còn đang cập nhật.**

Thực hành: đổi tác vụ thất bại thành tác vụ trả `0`, dự đoán outcomes và kết quả main cần thay đổi thế nào. Sau đó tăng nhóm lên hai luồng và so sánh bộ đếm tổng thay vì ép thứ tự outcomes. Cuối cùng, phân tích riêng một tác vụ bị từ chối khi queue đầy: nó cần được ghi nhận ở ranh giới nào nếu before/after không được gọi cho nó?
